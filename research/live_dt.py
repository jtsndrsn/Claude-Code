"""Live check Nov 9 - Nov 27 2026 on Webull 1-minute bars: v3 vs downtrend-mode candidates."""
import json, numpy as np, pandas as pd, datetime as dt
src = open('downtrend.py').read().split("BASE = {d: dayrun")[0]
exec(src)                                     # sys2 initialised, V3, dayrun(), DEFS, SEGS
S = '/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad'
r = pd.read_csv(S+'/ext2/mnq_1m_ext2.csv'); r = r[r.symbol == 'MNQZ6']
t = pd.to_datetime(r.ts).dt.tz_localize('UTC').dt.tz_convert('America/Chicago')
r['d'] = t.dt.strftime('%Y-%m-%d'); r['sec'] = t.dt.hour*3600 + t.dt.minute*60
# extend the daily close / EMA series with Webull 15:00 CT closes
d0, c0, _, _ = SEGS[1]; closes = r[r.sec == 14*3600+59*60].set_index('d').close
dates = list(d0) + [d for d in sorted(closes.index) if d > d0[-1]]
cl = np.concatenate([c0, [closes[d] for d in dates[len(d0):]]])
def ema(c, n):
    a = 2/(n+1); o = np.empty(len(c)); o[0] = c[0]
    for i in range(1, len(c)): o[i] = a*c[i] + (1-a)*o[i-1]
    return o
e20, e50 = ema(cl, 20), ema(cl, 50)
vix = pd.read_csv(S+'/ext2/vix.csv', parse_dates=['DATE']).set_index('DATE').CLOSE
mom = json.load(open(S+'/ext2/mom_ext2.json'))
def mkday(g):
    o,h,l,c = (g[k].to_numpy() for k in ('open','high','low','close')); tt = g.sec.to_numpy()
    up = np.abs(h-o) <= np.abs(o-l); P = np.empty((len(tt),4)); P[:,0]=o; P[:,3]=c
    P[:,1]=np.where(up,h,l); P[:,2]=np.where(up,l,h)
    return dict(sym='MNQZ6', t=tt, h=h, l=l, P=P.ravel(), T=np.repeat(tt,4), G=np.tile([True,False,False,False],len(tt)))
rows = []
for d in sorted(set(r.d)):
    if not ('2026-11-09' <= d <= '2026-11-27') or dt.date.fromisoformat(d).weekday() >= 5 or d == '2026-11-26': continue
    g = r[(r.d == d) & (r.sec >= 25200) & (r.sec < 39600)]
    if len(g) < 200: continue
    j = max(i for i, x in enumerate(dates) if x < d)
    f = dict(close=cl[j], e20=e20[j], e50=e50[j], e50_5=e50[j-5], r20=cl[j]/cl[j-20]-1)
    sys2.D[d] = mkday(g)
    sys2.F[d] = {'trend': {'D50': 1 if cl[j] > e50[j] else -1}, 'levels': {}}
    v = vix[vix.index < d]; sys2.VCH[d] = (v.iloc[-1]-v.iloc[-2], v.iloc[-1])
    sys2.DF[d] = {'d_macd_hist': mom[d]['d_macd_hist'], 'd_di_trend': mom[d]['d_di_trend']}
    sys2.RSI[d] = (np.array([]), np.array([]))
    flags = {k[:2]: fn(f) for k, fn in DEFS.items()}
    base = dayrun(d, {}); b4 = dayrun(d, {'longmod': {'sl': 150}}); e1 = dayrun(d, {'vix_th': 0.6})
    s = lambda x: round(sum(y[0] for y in x))
    desc = lambda x: ', '.join(f"{'L' if y[2]>0 else 'S'} {y[3]} {y[1]} {y[0]:+.0f}" for y in x) or 'no trade'
    rows.append(dict(date=d, vix_chg=round(sys2.VCH[d][0],2), r20=f"{100*f['r20']:+.1f}%", D1=flags['D1'], D2=flags['D2'], D3=flags['D3'],
                     v3=s(base), D3_SL150=s(b4) if flags['D3'] else s(base), D2_VIX06=s(e1) if flags['D2'] else s(base), trades=desc(base)))
x = pd.DataFrame(rows); print(x.to_string(index=False))
print('\ntotals: v3', x.v3.sum(), '| D3 + long SL 150', x.D3_SL150.sum(), '| D2 + VIX 0.6', x.D2_VIX06.sum())
x.to_csv('live_dt.csv', index=False)
