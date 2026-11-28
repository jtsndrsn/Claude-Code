"""PORR v3.5 research: downtrend-day mode. Normal days = v3. Downtrend defined from data known before 08:30."""
import json, bisect, numpy as np, pandas as pd, sys2
from fastsim import sim_day_breakout, TICK
sys2.init()
V3 = dict(json.load(open('s9_params.json'))[0], tp=400, ttp=800)   # v3.5
# ---------- daily series (RTH 15:00 CT closes, back-adjusted per segment) ----------
def seg(f):
    s = json.load(open(f)); d = [x[0] for x in s]; c = np.array([x[1] for x in s])
    def ema(n):
        a = 2/(n+1); o = np.empty(len(c)); o[0] = c[0]
        for i in range(1, len(c)): o[i] = a*c[i] + (1-a)*o[i-1]
        return o
    return d, c, ema(20), ema(50)
SEGS = [seg('ema_features2.json'), seg('ema_features.json')]     # 2021-23, 2023-26
def feat(day):
    for d, c, e20, e50 in SEGS:
        j = bisect.bisect_left(d, day) - 1                        # last close strictly before the day
        if 0 <= j < len(d) and d[j] < day and (day[:4] == d[j][:4] or int(day[:4]) - int(d[j][:4]) <= 1) and j >= 0 and d[-1] >= day[:10] or (0 <= j < len(d) and d[j] < day and day <= d[-1]):
            return dict(close=c[j], e20=e20[j], e50=e50[j], e50_5=e50[j-5] if j >= 5 else np.nan,
                        r20=c[j]/c[j-20]-1 if j >= 20 else np.nan, warm=j)
    return None
DEFS = {
 'D1 close<EMA50 & EMA50 falling 5d': lambda f: f['close'] < f['e50'] and f['e50'] < f['e50_5'],
 'D2 20-day return < -5%':            lambda f: f['r20'] < -0.05,
 'D3 close<EMA20 & close<EMA50':      lambda f: f['close'] < f['e20'] and f['close'] < f['e50'],
}
days = sorted(sys2.D)
F = {d: feat(d) for d in days}
WARM = {d: (F[d] is not None and F[d]['warm'] >= 50) for d in days}      # EMA50 needs ~50 days of history
# ---------- one-day simulation with options ----------
cap = []; _o = sys2._exit; LONGMOD = {}
def _spy(P, G, T, k, dirn, entry, sl, tpx, *a):
    if dirn > 0 and LONGMOD:
        sl = LONGMOD.get('sl', sl/TICK) * TICK; tpx = LONGMOD.get('tp', tpx/TICK) * TICK
    r = _o(P, G, T, k, dirn, entry, sl, tpx, *a); cap.append(int(T[k])); return r
sys2._exit = _spy
def dayrun(d, o):
    """o: dict of options. Returns list of (pnl, kind, dirn, setup)."""
    p = V3; day = sys2.D[d]; out = []
    vth = o.get('vix_th', p['vix_th'])
    bo_day = sys2.VCH[d][0] < -vth or o.get('bo_all', False)
    mm = (day['t'] >= p['rs']) & (day['t'] < p['re'])
    if not mm.any(): return out
    hi, lo = float(day['h'][mm].max()), float(day['l'][mm].min())
    if bo_day:
        if o.get('bo_short_only'): hi = 1e12
        bc = dict(trade_start=p['re'], trade_end=p['te'], **dict(sys2.BO_DEFAULT, **p['brk']))
        for x in sim_day_breakout(day, hi, lo, bc): out.append((x[4]*5 - 14.8, x[3], x[0], 'BO'))
        return out
    LONGMOD.clear(); LONGMOD.update(o.get('longmod', {}))
    q = dict(p, side=-1) if o.get('skip_long') else p
    cap.clear(); res = sys2.fade_day(d, q); LONGMOD.clear()
    for (dirn, ticks, kind, wt, ts), t0 in zip(res, cap):
        if sys2.day_mult(d, p, dirn) <= 0: continue
        if o.get('skip_long_early') and dirn > 0 and ts < 30600 + 120: continue
        out.append((ticks*5 - 14.8, kind, dirn, 'F'))
    return out
BASE = {d: dayrun(d, {}) for d in days}
tot = sum(x[0] for v in BASE.values() for x in v); print('baseline v3.5 net', round(tot), 'trades', sum(len(v) for v in BASE.values()))
VARIANTS = {
 'a  skip long fades':                 {'skip_long': True},
 'b1 long fades TP 300':               {'longmod': {'tp': 300}},
 'b2 long fades TP 350':               {'longmod': {'tp': 350}},
 'b3 long fades SL 120':               {'longmod': {'sl': 120}},
 'b4 long fades SL 150':               {'longmod': {'sl': 150}},
 'c  breakout mode every day':         {'bo_all': True},
 'd1 short breakouts only (VIX days)': {'bo_short_only': True},
 'd2 short breakouts only, every day': {'bo_all': True, 'bo_short_only': True},
 'e1 VIX threshold 0.6':               {'vix_th': 0.6},
 'e2 VIX threshold 0.5':               {'vix_th': 0.5},
 'f  skip long fades filled 08:30-08:32': {'skip_long_early': True},
}
VR = {k: {} for k in VARIANTS}
def stats(rows):
    p = np.array([r[0] for r in rows]) if rows else np.zeros(0)
    if len(p) == 0: return dict(n=0, net=0, dd=0, win=0)
    c = np.cumsum(p); dd = (np.maximum.accumulate(np.maximum(c, 0)) - c).max()
    return dict(n=len(p), net=p.sum(), dd=dd, win=100*(p > 0).mean())
res = []
for dname, fn in DEFS.items():
    dt = {d for d in days if WARM[d] and fn(F[d])}
    n_old = sum(1 for d in dt if d < '2024'); n_new = len(dt) - n_old
    print(f"\n######## {dname}: downtrend days 2021-23 {n_old} / {sum(1 for d in days if d<'2024' and WARM[d])}, 2025-26 {n_new} / {sum(1 for d in days if d>'2024' and WARM[d])}")
    def combo(var):
        allrows, dto, dtn = [], [], []
        for d in days:
            rows = BASE[d]
            if d in dt and var is not None:
                if d not in VR[var]: VR[var][d] = dayrun(d, VARIANTS[var])
                rows = VR[var][d]
            allrows += rows
            if d in dt: (dto if d < '2024' else dtn).extend(rows)
        return stats(allrows), stats(dto), stats(dtn)
    b_all, b_o, b_n = combo(None)
    print(f"{'variant (downtrend days only)':38} | {'DT 2021-23 net':>14} {'dd':>7} {'win':>4} {'n':>4} | {'DT 2025-26 net':>14} {'dd':>7} {'win':>4} {'n':>4} | {'44-mo net':>10} {'max DD':>7} | both?")
    def line(lab, a, o, n):
        both = o['net'] > b_o['net'] and n['net'] > b_n['net']
        print(f"{lab:38} | {o['net']:+14,.0f} {o['dd']:7,.0f} {o['win']:4.0f} {o['n']:4} | {n['net']:+14,.0f} {n['dd']:7,.0f} {n['win']:4.0f} {n['n']:4} | {a['net']:+10,.0f} {a['dd']:7,.0f} | {'YES' if both else ''}")
        res.append((dname, lab, o['net']-b_o['net'], n['net']-b_n['net'], a['net'], a['dd'], both))
    line('v3.5 (no change)', b_all, b_o, b_n)
    for var in VARIANTS: line(var, *combo(var))
pd.DataFrame(res, columns=['def','variant','d_old','d_new','net44','dd44','both']).to_csv('dt35_results.csv', index=False)
