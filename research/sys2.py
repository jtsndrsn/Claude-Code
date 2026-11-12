"""Full PORR system simulator for the big search: fade days + VIX-drop breakout days, with new
options (time stop, trailing stop after breakeven, partial take-profit, entry filters, day filters).
Per-trade result = ticks per contract (weighted over partial legs) and a size multiplier."""
import sys, json, csv, bisect
from datetime import date, datetime
import numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from fastsim import load_days, _first, sim_day_breakout, TICK
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad"
R = "/home/user/Claude-Code/research"
D = F = DF = VCH = RSI = None
QTY, TUSD, COMM_SIDE = 10, 0.5, 0.74


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.clip(d, 0, None); dn = np.clip(-d, 0, None)
    au = np.zeros_like(c); ad = np.zeros_like(c)
    a = 1.0 / n
    for i in range(1, len(c)):
        au[i] = au[i - 1] + a * (up[i] - au[i - 1]); ad[i] = ad[i - 1] + a * (dn[i] - ad[i - 1])
    rs = np.where(ad > 0, au / np.maximum(ad, 1e-12), 100.0)
    return 100 - 100 / (1 + rs)


def init():
    global D, F, DF, VCH, RSI
    D = load_days(); F = json.load(open(S + "/db/features.json"))
    vix = {}
    for r in csv.DictReader(open(S + "/ext/vix.csv")):
        vix[datetime.strptime(r["DATE"], "%m/%d/%Y").date()] = float(r["CLOSE"])
    vd = sorted(vix); VCH = {}
    for d in D:
        i = bisect.bisect_left(vd, date.fromisoformat(d)); VCH[d] = (vix[vd[i - 1]] - vix[vd[i - 2]], vix[vd[i - 1]])
    DF = {}
    for r in csv.DictReader(open(R + "/trades_setupA_with_context.csv")):
        if r["date"] in DF: continue
        g = {}
        for k in ("range_atr", "atr14_t", "gap_t", "on_range_t", "prev_rng_atr", "d_macd_hist", "d_rsi", "d_adx",
                  "d_di_trend", "d_stoch", "d_pctb", "d_willr"):
            try: g[k] = float(r[k])
            except (ValueError, KeyError): g[k] = None
        g["dow"] = r["dow"]; DF[r["date"]] = g
    RSI = {}
    for d, day in D.items():                       # 1-minute RSI(14) from 1-second closes
        t = day["t"]; c = day["P"].reshape(-1, 4)[:, 3]
        m = t // 60; last = np.flatnonzero(np.diff(m, append=m[-1] + 1))
        RSI[d] = ((m[last] + 1) * 60, _rsi(c[last]))


def _exit(P, G, T, k, dirn, entry, sl, tpx, bt, bo, trail, tstop, end_i):
    """exit after entry at tick k. Returns (x, px, kind, be_hit)."""
    fav = (P[k:end_i] - entry) * dirn
    n = len(fav)
    sl_i = _first(fav[1:] <= -sl, 0); sl_i = sl_i + 1 if sl_i != -1 else -1
    tp_i = _first(fav[1:] >= tpx + TICK, 0); tp_i = tp_i + 1 if tp_i != -1 else -1
    tt = _first(fav >= bt, 0) if bt is not None else -1
    first = min([x for x in (sl_i, tp_i) if x != -1], default=-1)
    ts_i = -1
    if tstop:
        ts_i = int(np.searchsorted(T[k:end_i], T[k] + tstop))
        if ts_i >= n: ts_i = -1
    if tt != -1 and (first == -1 or first > tt) and (ts_i == -1 or tt <= ts_i):
        f2 = fav[tt:]
        if trail:
            rm = np.maximum.accumulate(f2); stopf = np.maximum(bo, rm - trail)
        else:
            stopf = np.full(len(f2), float(bo))
        hit_s = _first(f2[1:] <= stopf[:-1], 0); hit_t = _first(f2[1:] >= tpx + TICK, 0)
        if hit_t != -1 and (hit_s == -1 or hit_t < hit_s):
            return k + tt + 1 + hit_t, entry + dirn * tpx, "TP", True
        if hit_s != -1:
            x = k + tt + 1 + hit_s; lvl = entry + dirn * stopf[hit_s]
            return x, (P[x] if G[x] else lvl), "BE", True
        return end_i - 1, P[end_i - 1], "EOD", True
    if ts_i != -1 and (first == -1 or first > ts_i):
        x = k + ts_i; return x, P[x], "TIME", False
    if first == -1:
        return end_i - 1, P[end_i - 1], "EOD", False
    x = k + first
    if first == tp_i: return x, entry + dirn * tpx, "TP", False
    return x, (P[x] if G[x] else entry - dirn * sl), "SL", False


def fade_day(d, p):
    day = D[d]; P, G, T = day["P"], day["G"], day["T"]
    t = day["t"]; m = (t >= p["rs"]) & (t < p["re"])
    if not m.any(): return []
    hi, lo = float(day["h"][m].max()), float(day["l"][m].min())
    if p.get("rmin") and (hi - lo) / TICK < p["rmin"]: return []
    if p.get("rmax") and (hi - lo) / TICK > p["rmax"]: return []
    i = int(np.searchsorted(T, p["ts"])); end = int(np.searchsorted(T, p["te"]))
    if i >= end: return []
    dl = p["delay"] * TICK; L, Sv = lo - dl, hi + dl
    trend = F[d]["trend"].get(p.get("tsrc", "D50"), 0)
    used = {1: False, -1: False}; broken = {1: False, -1: False}
    out = []; n = 0
    Pe = P[:end]
    above_L = Pe > L; fillL = Pe <= L - TICK; below_S = Pe < Sv; fillS = Pe >= Sv + TICK
    rt, rv = RSI[d]
    while i < end and n < p["mt"]:
        cand = []
        for side, arm_m, fill_m, lvl in ((1, above_L, fillL, L), (-1, below_S, fillS, Sv)):
            if broken[side] or (p["onep"] and used[side]): continue
            if p.get("side") and p["side"] != side: continue
            a = _first(arm_m, i)
            if p["skip"]:
                b = _first(fill_m, i)
                if b != -1 and (a == -1 or b < a): broken[side] = True; continue
            if a == -1: continue
            f = _first(fill_m, a + 1)
            if f != -1: cand.append((f, side, lvl))
        if not cand: break
        k, dirn, entry = min(cand)
        used[dirn] = True
        # ---- entry filters (order cancelled just before the fill -> level counts as used)
        ok = True
        if p.get("appr"):            # approach: ticks moved toward the line in the last 5 minutes
            j = int(np.searchsorted(T, T[k] - 300)); mv = (P[j] - P[k]) * dirn / TICK
            lo_a, hi_a = p["appr"]
            if (lo_a is not None and mv < lo_a) or (hi_a is not None and mv > hi_a): ok = False
        if ok and p.get("rsi"):      # 1m RSI at entry: long needs RSI <= x, short RSI >= 100-x
            q = int(np.searchsorted(rt, T[k], side="right")) - 1
            if q >= 14:
                r_ = rv[q]
                if (dirn > 0 and r_ > p["rsi"]) or (dirn < 0 and r_ < 100 - p["rsi"]): ok = False
        if ok and p.get("tod") and T[k] > p["ts"] + p["tod"] * 60: ok = False
        if not ok:
            i = k + 1; continue
        n += 1
        with_t = trend == dirn
        tpk = p["ttp"] if with_t else p["tp"]
        if p.get("linetp"): tpk = max(4, round(((hi if dirn > 0 else lo) - entry) * dirn / TICK))
        x, px, kind, beh = _exit(P, G, T, k, dirn, entry, p["sl"] * TICK, tpk * TICK,
                                 p["bt"] * TICK if p.get("bt") else None, p.get("bo", 0) * TICK,
                                 p.get("trail", 0) * TICK if p.get("trail") else 0, p.get("tstop", 0) * 60, end)
        ticks = (px - entry) * dirn / TICK
        if p.get("ptp"):             # partial: fraction exits at ptp ticks if reached before the main exit
            ptp, frac = p["ptp"]
            hit = _first(((P[k + 1:x + 1] - entry) * dirn) >= ptp * TICK + TICK, 0)
            leg = ptp if hit != -1 else ticks
            ticks = frac * leg + (1 - frac) * ticks
        out.append((dirn, ticks, kind, with_t, int(T[k])))
        if p["skip"]:
            other = -dirn; seg = P[k:x + 1]
            if (other == -1 and (seg >= Sv + TICK).any()) or (other == 1 and (seg <= L - TICK).any()): broken[other] = True
        i = x
    return out


def day_mult(d, p, dirn=None):
    """size multiplier from day filters: list of (feature, lo, hi, mult) - mult applies when lo <= v < hi."""
    m = 1.0
    g = DF.get(d)
    for feat, lo, hi, mult in p.get("dayf", []):
        if feat == "vix": v = VCH[d][1]
        elif feat == "vixchg": v = VCH[d][0]
        elif feat == "agree":                       # daily MACD histogram agrees with trade direction
            if g is None or g["d_macd_hist"] is None or dirn is None: continue
            v = 1.0 if np.sign(g["d_macd_hist"]) == dirn else 0.0
        elif feat == "agree2":                      # MACD and DI both agree
            if g is None or g["d_macd_hist"] is None or g["d_di_trend"] is None or dirn is None: continue
            v = 1.0 if (np.sign(g["d_macd_hist"]) == dirn and g["d_di_trend"] == dirn) else 0.0
        elif feat == "dow":
            if g is None: continue
            if g["dow"] == lo: m *= mult
            continue
        elif feat == "absgap":
            if g is None or g["gap_t"] is None: continue
            v = abs(g["gap_t"])
        else:
            if g is None or g.get(feat) is None: continue
            v = g[feat]
        if lo <= v < hi: m *= mult
    return m


BO_DEFAULT = dict(mode="stop", offset=0, sl=300, tp=800, be_trig=200, be_off=100, max_trades=2)


def run(p):
    """p: fade params + vix_th + brk (breakout dict) + dayf. Returns per-trade list [(day, ticks, mult, kind, dir)]."""
    trades = []
    bo = dict(BO_DEFAULT, **p.get("brk", {}))
    bo_cfg = dict(trade_start=p.get("bo_ts", 8 * 3600 + 1800), trade_end=p.get("bo_te", 11 * 3600), **bo)
    vth = p.get("vix_th", 0.9)
    for d in sorted(D):
        if vth is not None and VCH[d][0] < -vth:
            hi, lo = F[d]["levels"]["PRE90"]
            for x in sim_day_breakout(D[d], hi, lo, bo_cfg):
                trades.append((d, x[4], p.get("bo_mult", 1.0), "BO-" + x[3], x[0]))
            continue
        for dirn, ticks, kind, wt, ts in fade_day(d, p):
            trades.append((d, ticks, day_mult(d, p, dirn), kind, dirn))
    return trades


def stats(trades, qty=QTY):
    eq = pk = dd = 0.0; gw = gl = 0.0; w = n = 0; y = {"2025": 0.0, "2026": 0.0}
    months = {}
    for d, tk, mult, kind, dirn in trades:
        if mult <= 0: continue
        q = qty * mult
        pnl = tk * TUSD * q - 2 * COMM_SIDE * q
        eq += pnl; pk = max(pk, eq); dd = max(dd, pk - eq); n += 1
        y[d[:4]] += pnl; months[d[:7]] = months.get(d[:7], 0) + pnl
        if pnl > 0: gw += pnl; w += 1
        else: gl -= pnl
    return dict(n=n, net=round(eq), dd=round(dd), win=round(100 * w / n, 1) if n else 0,
                pf=round(gw / gl, 2) if gl else 99, y25=round(y["2025"]), y26=round(y["2026"]),
                lm=sum(1 for v in months.values() if v < 0))


def job(p):
    try:
        return dict(p=p, **stats(run(p)))
    except Exception as e:
        return dict(p=p, err=str(e))


BASE = dict(rs=7 * 3600, re=8 * 3600 + 1800, ts=8 * 3600 + 1800, te=11 * 3600, delay=10, sl=100, tp=500, ttp=750,
            bt=100, bo=50, mt=4, onep=True, skip=False, vix_th=0.9)

if __name__ == "__main__":
    init()
    import time as _t
    t0 = _t.time(); r = job(dict(BASE)); print(r, round(_t.time() - t0, 1), "s")


def bo_job(q):
    """breakout-only results on VIX-drop days (threshold q['vix_th'])."""
    bo_cfg = dict(trade_start=8 * 3600 + 1800, trade_end=q.get("te", 11 * 3600), mode=q["mode"], offset=q["offset"],
                  sl=q["sl"], tp=q["tp"], be_trig=q.get("bt"), be_off=q.get("bo", 0), max_trades=q["mt"])
    tr = []
    for d in sorted(D):
        if VCH[d][0] < -q.get("vix_th", 0.9):
            hi, lo = F[d]["levels"][q.get("lv", "PRE90")]
            tr += [(d, x[4], 1.0, x[3], x[0]) for x in sim_day_breakout(D[d], hi, lo, bo_cfg)]
    return dict(p=q, **stats(tr))
