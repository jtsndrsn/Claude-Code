import pandas as pd, numpy as np, sys2
from fastsim import TICK
sys2.init()
rows=[]
for d,day in sys2.D.items():
    t=day['t']; m=(t>=25200)&(t<30600); o5=(t>=30600)&(t<30900)
    if not m.any() or not o5.any(): continue
    hi,lo=day['h'][m].max(),day['l'][m].min(); onh,onl=sys2.F[d]['levels']['ON']
    h5,l5=day['h'][o5].max(),day['l'][o5].min()
    rows.append(dict(date=d,rng_hi5=int(h5>hi),rng_lo5=int(l5<lo),on_hi5=int(h5>onh),on_lo5=int(l5<onl)))
x=pd.DataFrame(rows); df=pd.read_csv('ff_trades.csv').merge(x,on='date')
df['win']=(df.pnl>0).astype(int)
def lab(r,a,b):
    return {(0,0):'none',(1,0):'new HIGH only',(0,1):'new LOW only',(1,1):'both'}[(r[a],r[b])]
for a,b,name in [('rng_hi5','rng_lo5','PORR range line broken in 8:30-8:35'),('on_hi5','on_lo5','overnight (session) high/low broken in 8:30-8:35')]:
    df['g']=df.apply(lambda r:lab(r,a,b),axis=1)
    # relation of trade to the break: for fades, break on the trade's own line (long fade + new low) = 'same side'
    df['rel']=np.where(df.g.isin(['none','both']),df.g,
        np.where(((df.g=='new LOW only')&(df.dirn==1)&(df.type=='fade'))|((df.g=='new HIGH only')&(df.dirn==-1)&(df.type=='fade'))
                 |((df.g=='new HIGH only')&(df.dirn==1)&(df.type=='breakout'))|((df.g=='new LOW only')&(df.dirn==-1)&(df.type=='breakout')),'trade on the broken side','trade on the other side'))
    df['early']=np.where(df.entry_min<5,'filled 8:30-8:35','filled after 8:35')
    print(f"\n######## {name}  (days: {x.groupby([a,b]).size().to_dict()})")
    for typ in ['fade','breakout']:
        s=df[df.type==typ]
        g=s.groupby(['rel','early']).apply(lambda z:pd.Series(dict(trades=len(z),win=round(100*z.win.mean()),fastfail=round(100*z.fast_fail.mean()),
            avg=round(z.pnl.mean()),old=round(z[z.period=='old'].pnl.sum()),new=round(z[z.period=='new'].pnl.sum()))),include_groups=False)
        print(f"-- {typ}s (all: win {round(100*s.win.mean())}%, fast-fail {round(100*s.fast_fail.mean())}%, avg ${round(s.pnl.mean())})"); print(g.to_string())
