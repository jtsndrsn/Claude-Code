"""Add daily (MACD, RSI, Stoch, %B, ADX, Williams %R) and intraday-at-entry (5m RSI, 5m Stoch, VWAP distance)
indicators to bt/trades_ctx_<A|B>.csv -> bt/trades_ind_<A|B>.csv. Daily values use data up to the PREVIOUS day."""
import json, glob, csv, bisect, sys
import numpy as np
from collections import defaultdict
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from fastsim import load_days
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad"
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC"); TK = 0.25
F = json.load(open(S + "/db/features.json")); D = load_days()
# ---- daily OHLC per contract: Globex session 17:00(prev)-16:00, from 1m (Databento) + Webull daily (2024)
need = {F[d]["sym"] for d in F}
ohlc = defaultdict(dict)   # date -> sym -> [o,h,l,c,v]
m1 = defaultdict(list)
with open(S + "/db/mnq_1m_all.csv") as fh:
    fh.readline()
    for line in fh:
        ts, sym, o, h, l, c, v = line.rstrip("\n").split(",")
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).astimezone(CT)
        sd = (dt + timedelta(hours=7)).date()          # 17:00 CT belongs to the next session date
        o, h, l, c, v = float(o), float(h), float(l), float(c), int(v)
        x = ohlc[sd].get(sym)
        if x is None: ohlc[sd][sym] = [o, h, l, c, v]
        else: x[1] = max(x[1], h); x[2] = min(x[2], l); x[3] = c; x[4] += v
        if sym in need: m1[sym].append((dt, h, l, c, v))
for f in glob.glob(S + "/wb_daily/*.json"):
    for blk in json.load(open(f)):
        for b in blk["result"]:
            dd = date.fromisoformat(b["time"][:10])
            if dd < date(2025, 2, 1):
                ohlc[dd][blk["symbol"]] = [float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"]), int(float(b.get("volume", 0) or 0))]
# front = highest-volume contract per session date (weekday sessions only)
dates = sorted(d for d in ohlc if d.weekday() < 5)
front = {d: max(ohlc[d], key=lambda s: ohlc[d][s][4]) for d in dates}
# back-adjust (additive) at each roll, newest contract = reference
ser = []; adj = 0.0; prev = None
for d in reversed(dates):
    s = front[d]
    if prev and s != prev and prev in ohlc[d]:
        adj += ohlc[d][prev][3] - ohlc[d][s][3]
    o, h, l, c, v = ohlc[d][s]; ser.append((d, o + adj, h + adj, l + adj, c + adj)); prev = s
ser.reverse()
dd_ = [x[0] for x in ser]; O = np.array([x[1] for x in ser]); H = np.array([x[2] for x in ser]); L = np.array([x[3] for x in ser]); C = np.array([x[4] for x in ser])
def ema(a, n):
    out = np.empty_like(a); k = 2 / (n + 1); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out
def rma(a, n):
    out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = (out[i - 1] * (n - 1) + a[i]) / n
    return out
macd = ema(C, 12) - ema(C, 26); sig = ema(macd, 9); hist = macd - sig
dlt = np.diff(C, prepend=C[0]); up = rma(np.clip(dlt, 0, None), 14); dn = rma(np.clip(-dlt, 0, None), 14)
rsi = 100 - 100 / (1 + up / np.where(dn == 0, 1e-9, dn))
ll = np.array([L[max(0, i - 13):i + 1].min() for i in range(len(C))]); hh = np.array([H[max(0, i - 13):i + 1].max() for i in range(len(C))])
k_raw = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll); stoch_k = np.convolve(k_raw, np.ones(3) / 3, mode="full")[:len(C)]
willr = -100 * (hh - C) / np.where(hh - ll == 0, 1, hh - ll)
sma20 = np.array([C[max(0, i - 19):i + 1].mean() for i in range(len(C))]); sd20 = np.array([C[max(0, i - 19):i + 1].std() for i in range(len(C))])
pctb = (C - (sma20 - 2 * sd20)) / np.where(sd20 == 0, 1, 4 * sd20)
tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
upm = H - np.roll(H, 1); dnm = np.roll(L, 1) - L; upm[0] = dnm[0] = 0
pdm = np.where((upm > dnm) & (upm > 0), upm, 0); ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0)
atr = rma(tr, 14); pdi = 100 * rma(pdm, 14) / atr; ndi = 100 * rma(ndm, 14) / atr
dx = 100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1, pdi + ndi); adx = rma(dx, 14)
def prev_idx(d):
    return bisect.bisect_left(dd_, d) - 1
mkeys = {s: [r[0] for r in v] for s, v in m1.items()}
for name in ("A", "B"):
    rows = list(csv.DictReader(open(f"{S}/bt/trades_ctx_{name}.csv")))
    for r in rows:
        d = date.fromisoformat(r["date"]); i = prev_idx(d); dirn = 1 if r["side"] == "L" else -1
        r.update(d_macd_hist=round(hist[i], 2), d_macd_hist_rising=int(hist[i] > hist[i - 1]), d_macd_above_sig=int(macd[i] > sig[i]),
                 d_rsi=round(rsi[i], 1), d_stoch=round(stoch_k[i], 1), d_willr=round(willr[i], 1), d_pctb=round(pctb[i], 2),
                 d_adx=round(adx[i], 1), d_di_trend=int(pdi[i] > ndi[i]))
        # trade-direction-aware versions: is the daily momentum WITH this trade? (+1 with / -1 against)
        r["macd_with_trade"] = int(np.sign(hist[i]) == dirn)
        r["rsi_with_trade"] = int((rsi[i] - 50) * dirn > 0)
        # intraday at entry: 5-minute bars from the 1s data up to the entry second
        day = D[r["date"]]; t = day["t"]; es = 8*3600+1800 + float(r["entry_min"]) * 60
        m = t < es; tt = t[m]; cl = day["P"].reshape(-1, 4)[:, 3][m]; hh5 = day["h"][m]; ll5 = day["l"][m]
        b = (tt // 300); ub, idx = np.unique(b, return_index=True)
        last = np.append(idx[1:] - 1, len(tt) - 1)
        c5 = cl[last]; h5 = np.maximum.reduceat(hh5, idx); l5 = np.minimum.reduceat(ll5, idx)
        if len(c5) > 15:
            dl = np.diff(c5); u = rma(np.clip(dl, 0, None), 14)[-1]; v_ = rma(np.clip(-dl, 0, None), 14)[-1]
            r["m5_rsi"] = round(100 - 100 / (1 + u / (v_ if v_ else 1e-9)), 1)
            lo14, hi14 = l5[-14:].min(), h5[-14:].max(); r["m5_stoch"] = round(100 * (c5[-1] - lo14) / ((hi14 - lo14) or 1), 1)
        else:
            r["m5_rsi"] = r["m5_stoch"] = None
        # VWAP from 1m volume since 08:30 (session) up to entry
        s = F[r["date"]]["sym"]; k = mkeys[s]
        a0 = bisect.bisect_left(k, datetime.combine(d, time(8, 30), CT)); a1 = bisect.bisect_left(k, datetime.combine(d, time(0, 0), CT) + timedelta(seconds=es))
        seg = m1[s][a0:a1]
        if seg:
            pv = sum((x[1] + x[2] + x[3]) / 3 * x[4] for x in seg); vv = sum(x[4] for x in seg)
            vw = pv / vv if vv else None
            ent = float(r["ticks"]) and None
            r["vwap_dist_t"] = round(((cl[-1] if len(cl) else 0) - vw) / TK * dirn) if vw else None   # + = entry on the 'cheap' side of VWAP for this trade? (sign: price above vwap for longs)
        else:
            r["vwap_dist_t"] = None
    with open(f"{S}/bt/trades_ind_{name}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(name, "rows", len(rows))
