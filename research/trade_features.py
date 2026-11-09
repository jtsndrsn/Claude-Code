"""Every trade of setups A and B with market context at entry. Writes bt/trades_ctx_<A|B>.csv"""
import sys, json, csv, bisect
import numpy as np
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from fastsim import load_days, sim_day
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad"
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC"); TK = 0.25
D = load_days(); F = json.load(open(S + "/db/features.json"))
# VIX daily closes
vix = {}
for row in csv.DictReader(open(S + "/ext/vix.csv")):
    vix[datetime.strptime(row["DATE"], "%m/%d/%Y").date()] = float(row["CLOSE"])
vdates = sorted(vix)
def vix_prev(dd, k=1):
    i = bisect.bisect_left(vdates, dd) - k
    return vix[vdates[i]] if i >= 0 else None
# 1-minute data per symbol for session ranges, gap and ATR
need = {F[d]["sym"] for d in F}
m1 = {}
with open(S + "/db/mnq_1m_all.csv") as fh:
    fh.readline()
    for line in fh:
        ts, sym, o, h, l, c, v = line.rstrip("\n").split(",")
        if sym in need:
            m1.setdefault(sym, []).append((datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).astimezone(CT), float(o), float(h), float(l), float(c), int(v)))
keys = {s: [r[0] for r in v] for s, v in m1.items()}
def rng(s, a, b):
    k = keys[s]; return m1[s][bisect.bisect_left(k, a):bisect.bisect_left(k, b)]
def session_ranges(s, dd, n=14):
    """high-low of the n previous RTH sessions (08:30-15:00) for ATR."""
    out = []; p = dd - timedelta(days=1)
    while len(out) < n and p > dd - timedelta(days=40):
        xs = rng(s, datetime.combine(p, time(8, 30), CT), datetime.combine(p, time(15, 0), CT))
        if xs: out.append(max(x[2] for x in xs) - min(x[3] for x in xs))
        p -= timedelta(days=1)
    return out
def shock(day, sec_from, secs=60):
    t = day["t"]; m = (t >= sec_from) & (t < sec_from + secs)
    if not m.any(): return 0.0
    return (day["h"][m].max() - day["l"][m].min()) / TK

SETUPS = {"A": dict(sl=100, rr=5), "B": dict(sl=150, rr=4)}
for name, sp in SETUPS.items():
    cfg = dict(trade_start=8*3600+1800, trade_end=11*3600, delay=10, sl=sp["sl"], tp=sp["sl"]*sp["rr"], max_trades=10,
               one_per_level=True, skip_broken=False, be_trig=sp["sl"], be_off=sp["sl"]//2)
    rows = []
    for d in sorted(D):
        f = F[d]; day = D[d]; hi, lo = f["levels"]["PRE90"]; sg = f["trend"]["D50"]
        tmd = {1: 1.5 if sg > 0 else 1.0, -1: 1.5 if sg < 0 else 1.0}
        trades = sim_day(day, hi, lo, cfg, tp_mult_dir=tmd)
        if not trades: continue
        dd = date.fromisoformat(d); s = f["sym"]
        atr = session_ranges(s, dd); atr14 = sum(atr) / len(atr) if atr else None
        prevs = session_ranges(s, dd, 1); prev_rng = prevs[0] if prevs else None
        # gap: 08:30 open vs previous RTH close
        p = dd - timedelta(days=1); prev_close = None
        for _ in range(5):
            xs = rng(s, datetime.combine(p, time(8, 30), CT), datetime.combine(p, time(15, 0), CT))
            if xs: prev_close = xs[-1][4]; break
            p -= timedelta(days=1)
        t = day["t"]; i830 = int(np.searchsorted(t, 8*3600+1800)); open830 = day["P"][i830*4] if i830 < len(t) else None
        on = f["levels"].get("ON")
        for k, x in enumerate(trades):
            dirn, entry, exitp, kind, ticks, es, xs_, be = x
            net = ticks * 0.5 * 10 - 14
            j = int(np.searchsorted(t, es))
            def px_at(sec):
                i = int(np.searchsorted(t, sec)); i = min(max(i - 1, 0), len(t) - 1); return day["P"][i*4 + 3]
            mv5 = (entry - px_at(es - 300)) / TK * (-dirn)    # ticks price travelled TOWARD the line in last 5 min (+ = fast approach)
            mv15 = (entry - px_at(es - 900)) / TK * (-dirn)
            w = (t >= es - 900) & (t < es); vol15 = ((day["h"][w].max() - day["l"][w].min()) / TK) if w.any() else 0
            rows.append(dict(date=d, dow=dd.strftime("%a"), side="L" if dirn > 0 else "S", with_trend=int(dirn == sg),
                             entry_min=round((es - (8*3600+1800)) / 60, 1), trade_no=k + 1, kind=kind, ticks=round(ticks, 2), net=net,
                             win=int(net > 0), range_t=round((hi - lo) / TK), on_range_t=round((on[0] - on[1]) / TK) if on else None,
                             range_atr=round((hi - lo) / atr14, 3) if atr14 else None, atr14_t=round(atr14 / TK) if atr14 else None,
                             prev_rng_atr=round(prev_rng / atr14, 3) if (prev_rng and atr14) else None,
                             gap_t=round((open830 - prev_close) / TK) if (open830 and prev_close) else None,
                             open_pos=round((open830 - lo) / (hi - lo), 3) if (open830 and hi > lo) else None,
                             approach5=round(mv5), approach15=round(mv15), vol15_t=round(vol15),
                             shock0730=round(shock(day, 7*3600+1800)), shock0900=round(shock(day, 9*3600)),
                             after0900=int(es >= 9*3600), vix=vix_prev(dd), vix_chg=round(vix_prev(dd) - vix_prev(dd, 2), 2) if vix_prev(dd, 2) else None))
    with open(S + f"/bt/trades_ctx_{name}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(name, len(rows), "trades, net", round(sum(r["net"] for r in rows)), "losers", sum(r["net"] < 0 for r in rows))
