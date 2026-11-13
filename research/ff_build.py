"""All v3 trades with pre-entry context -> ff_trades.csv"""
import json, csv, bisect, numpy as np, sys2
from fastsim import sim_day_breakout, TICK
sys2.init()
V3 = json.load(open('s9_params.json'))[0]
FOMC = set("""2021-11-03 2021-12-15 2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17
2025-10-29 2025-12-10 2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28""".split())
# adjusted daily closes (both segments) for daily RSI / EMA distance / returns
ser = json.load(open('ema_features2.json')) + json.load(open('ema_features.json')); ser.sort()
sd = [x[0] for x in ser]; cl = np.array([x[1] for x in ser]); em = np.array([x[2] for x in ser])
def rsi_series(c, n=14):
    d = np.diff(c); up = np.where(d > 0, d, 0.); dn = np.where(d < 0, -d, 0.); out = np.full(len(c), np.nan)
    au, ad = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(c)):
        if i > n: au = (au * (n - 1) + up[i - 1]) / n; ad = (ad * (n - 1) + dn[i - 1]) / n
        out[i] = 100 - 100 / (1 + au / ad) if ad else 100
    return out
drsi = rsi_series(cl)
days = sorted(sys2.D)
pdr = {d: (sys2.F[d]['levels']['PD'][0] - sys2.F[d]['levels']['PD'][1]) / TICK if 'PD' in sys2.F[d]['levels'] else np.nan for d in days}
def bars1m(day):
    t = day["t"]; P = day["P"].reshape(-1, 4); m = t // 60
    idx = np.flatnonzero(np.diff(m, prepend=m[0] - 1)); ends = np.append(idx[1:], len(t))
    return np.array([(m[a] * 60, P[a, 0], day["h"][a:b].max(), day["l"][a:b].min(), P[b - 1, 3]) for a, b in zip(idx, ends)])
rows = []
for di, d in enumerate(days):
    day = sys2.D[d]; tt = day["t"]; P = day["P"]; T = day["T"]; lv = sys2.F[d]['levels']
    mm = (tt >= 25200) & (tt < 30600)
    if not mm.any(): continue
    hi, lo = float(day["h"][mm].max()), float(day["l"][mm].min())
    B = bars1m(day); bt_ = B[:, 0]
    j = bisect.bisect_left(sd, d) - 1
    # ---- day context (known before 8:30)
    prev = [pdr[x] for x in days[max(0, di - 14):di] if x[:4] == d[:4] or True]
    atr = np.nanmean(prev) if prev else np.nan
    i830 = int(np.searchsorted(T, 30600))
    if i830 >= len(P): continue
    o830 = P[i830]
    pdh, pdl = lv.get('PD', [np.nan, np.nan]); onh, onl = lv['ON']
    b730 = B[(bt_ >= 27000) & (bt_ < 27060)]; bpre = B[(bt_ >= 25200) & (bt_ < 27000)]
    shock = (b730[0, 2] - b730[0, 3]) / max(np.median(bpre[:, 2] - bpre[:, 3]), TICK) if len(b730) and len(bpre) else np.nan
    b900 = B[(bt_ >= 32400) & (bt_ < 32460)]; bpre9 = B[(bt_ >= 30600) & (bt_ < 32400)]
    ctx = dict(date=d, period='old' if d < '2024' else 'new', dow=['Mon','Tue','Wed','Thu','Fri'][__import__('datetime').date.fromisoformat(d).weekday()],
               fomc=int(d in FOMC), vix=sys2.VCH[d][1], vixchg=sys2.VCH[d][0],
               range_t=(hi - lo) / TICK, range_atr=(hi - lo) / TICK / atr if atr else np.nan, pd_range_atr=pdr[d] / atr if atr else np.nan,
               on_range_atr=(onh - onl) / TICK / atr if atr else np.nan,
               news730=shock, open_pos=(o830 - lo) / (hi - lo) if hi > lo else np.nan,
               open_vs_pd=1 if o830 > pdh else (-1 if o830 < pdl else 0),
               range_in_pd=int(hi <= pdh and lo >= pdl), d_rsi=drsi[j], ema_dist=(cl[j] - em[j]) / TICK,
               ret5=(cl[j] - cl[j - 5]) / TICK if j >= 5 else np.nan, d_macd=(sys2.DF.get(d) or {}).get('d_macd_hist'),
               d_di=(sys2.DF.get(d) or {}).get('d_di_trend'), trend=sys2.F[d]['trend'].get('D50', 0))
    # ---- trades
    trades = []
    if sys2.VCH[d][0] < -V3['vix_th']:
        bc = dict(trade_start=30600, trade_end=39600, **dict(sys2.BO_DEFAULT, **V3['brk']))
        for dirn, entry, px, kind, ticks, t0, t1, be in sim_day_breakout(day, hi, lo, bc):
            trades.append(('breakout', dirn, entry, t0, kind, ticks, V3['brk']['sl'], V3['brk']['be_trig'], hi if dirn > 0 else lo))
    else:
        for dirn, ticks, kind, wt, ts in sys2.fade_day(d, V3):
            if sys2.day_mult(d, V3, dirn) <= 0: continue
            line = lo if dirn > 0 else hi
            entry = line - dirn * V3['delay'] * TICK
            trades.append(('fade', dirn, entry, ts, kind, ticks, V3['sl'], V3['bt'], line))
    for typ, dirn, entry, t0, kind, ticks, sl, bet, line in trades:
        k = int(np.searchsorted(T, t0)); e11 = int(np.searchsorted(T, 39600))
        fav = (P[k:e11] - entry) * dirn / TICK
        sl_i = np.flatnonzero(fav <= -sl); x = sl_i[0] if len(sl_i) else len(fav) - 1
        mfe = fav[:x + 1].max() if x >= 0 else 0
        secs = int(T[k + x] - T[k]) if kind == 'SL' else np.nan
        # pre-entry intraday
        q = bisect.bisect_right(bt_, t0) - 1      # current 1m bar
        last5 = B[max(0, q - 5):q]; last15 = B[max(0, q - 15):q]
        toward5 = (last5[0, 1] - P[k]) * dirn / TICK if len(last5) else np.nan   # fade long: price falling into line (+)
        toward15 = (last15[0, 1] - P[k]) * dirn / TICK if len(last15) else np.nan
        bigbar = (last15[:, 2] - last15[:, 3]).max() / TICK if len(last15) else np.nan
        # FVGs in last 15 bars in the direction of the move into the entry (against the fade, with a breakout)
        mv = -dirn if typ == 'fade' else dirn
        fvg = 0
        for a in range(max(2, q - 15), q):
            if mv > 0 and B[a, 3] > B[a - 2, 2]: fvg += 1
            if mv < 0 and B[a, 2] < B[a - 2, 3]: fvg += 1
        ri = bisect.bisect_right(sys2.RSI[d][0], t0) - 1; r1 = sys2.RSI[d][1][ri] if ri >= 14 else np.nan
        swept_pd = int((dirn > 0 and lo < pdl) or (dirn < 0 and hi > pdh)) if typ == 'fade' else int((dirn > 0 and hi > pdh) or (dirn < 0 and lo < pdl))
        pd_beyond = int((line < pdl) if dirn > 0 else (line > pdh)) if typ == 'fade' else int((line > pdh) if dirn > 0 else (line < pdl))
        rows.append(dict(ctx, type=typ, dirn=dirn, with_trend=int(ctx['trend'] == dirn), entry_min=(t0 - 30600) / 60,
                         kind=kind, ticks=ticks, pnl=ticks * 5 - 14.8, mfe=mfe, secs_to_sl=secs,
                         fast_fail=int(kind == 'SL' and mfe < bet / 2), toward5=toward5, toward15=toward15, bigbar15=bigbar,
                         fvg15=fvg, rsi1m=r1, line_beyond_pd=pd_beyond, prior_sweep=swept_pd))
w = csv.DictWriter(open('ff_trades.csv', 'w'), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
import collections
print(len(rows), 'trades', collections.Counter((r['type'], r['kind']) for r in rows), 'fast fails', sum(r['fast_fail'] for r in rows))
print('net', round(sum(r['pnl'] for r in rows)))
