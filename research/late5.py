import pandas as pd, numpy as np, sys2
from fastsim import TICK
sys2.init()
rows=[]
for d,day in sys2.D.items():
    t=day['t']; a=(t>=25200)&(t<30300); b=(t>=30300)&(t<30600)
    if not a.any() or not b.any(): continue
    ha,la=day['h'][a].max(),day['l'][a].min(); hb,lb=day['h'][b].max(),day['l'][b].min()
    P,T=day['P'],day['T']; i830=int(np.searchsorted(T,30600)); i900=int(np.searchsorted(T,32400))
    if i900>=len(P): continue
    hi,lo=max(ha,hb),min(la,lb)
    g='late HIGH' if hb>ha and not lb<la else 'late LOW' if lb<la and not hb>ha else 'both' if hb>ha else 'none'
    up=1 if g=='late HIGH' else -1 if g=='late LOW' else 0
    # what happened next: first 30 min move in the late-break direction; which line got broken first after 8:30
    mv30=(P[i900]-P[i830])*up/TICK if up else np.nan
    seg=P[i830:int(np.searchsorted(T,39600))]
    fh=np.flatnonzero(seg>hi); fl=np.flatnonzero(seg<lo)
    first='HIGH' if len(fh) and (not len(fl) or fh[0]<fl[0]) else 'LOW' if len(fl) else 'neither'
    rows.append(dict(date=d,late=g,mv30=mv30,first_break=first,rng=(hi-lo)/TICK))
x=pd.DataFrame(rows)
print("days by 08:25-08:30 behaviour:",x.late.value_counts().to_dict())
for g in ['late HIGH','late LOW']:
    s=x[x.late==g]; same='HIGH' if 'HIGH' in g else 'LOW'
    print(f"{g}: first line broken after open = same side {100*(s.first_break==same).mean():.0f}%, opposite {100*((s.first_break!=same)&(s.first_break!='neither')).mean():.0f}%, neither {100*(s.first_break=='neither').mean():.0f}% | 8:30->9:00 move in that direction: median {s.mv30.median():.0f} ticks, continued {100*(s.mv30>0).mean():.0f}%")
s=x[x.late=='none']; print(f"none: first break HIGH {100*(s.first_break=='HIGH').mean():.0f}% LOW {100*(s.first_break=='LOW').mean():.0f}%")
df=pd.read_csv('ff_trades.csv').merge(x[['date','late']],on='date'); df['win']=(df.pnl>0).astype(int)
def rel(r):
    if r.late in ('none','both'): return r.late
    up=1 if r.late=='late HIGH' else -1
    if r.type=='fade': return 'fade INTO the late move' if r.dirn==-up else 'fade on the other line'
    return 'breakout WITH the late move' if r.dirn==up else 'breakout AGAINST the late move'
df['rel']=df.apply(rel,axis=1)
for typ in ['fade','breakout']:
    s=df[df.type==typ]
    g=s.groupby('rel').apply(lambda z:pd.Series(dict(trades=len(z),win=round(100*z.win.mean()),fastfail=round(100*z.fast_fail.mean()),avg=round(z.pnl.mean()),
        y2123=round(z[z.period=='old'].pnl.sum()),y2526=round(z[z.period=='new'].pnl.sum()))),include_groups=False)
    print(f"\n-- {typ}s (all: win {round(100*s.win.mean())}%, fast-fail {round(100*s.fast_fail.mean())}%, avg ${round(s.pnl.mean())})"); print(g.to_string())
