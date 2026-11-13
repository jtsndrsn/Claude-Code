import numpy as np, sys2, collections
from fastsim import sim_day_breakout, TICK
sys2.init()
cfg=dict(mode="stop",offset=10,sl=300,tp=1200,be_trig=200,be_off=100,max_trades=2,trade_start=30600,trade_end=39600)
R=[]
for d in sorted(sys2.D):
    if not sys2.VCH[d][0] < -0.9: continue
    day=sys2.D[d]; tt=day["t"]; mm=(tt>=25200)&(tt<30600)
    if not mm.any(): continue
    hi,lo=float(day["h"][mm].max()),float(day["l"][mm].min())
    P,T=day["P"],day["T"]
    for dirn,entry,px,kind,ticks,t0,t1,be in sim_day_breakout(day,hi,lo,cfg):
        a=int(np.searchsorted(T,t0)); e11=int(np.searchsorted(T,39600)); x=int(np.searchsorted(T,t1))
        seg=(P[a:e11]-entry)*dirn/TICK
        tp_hit=np.where(seg>=1200)[0]; sl_hit=np.where(seg<=-300)[0]
        mfe=seg.max() if len(seg) else 0
        tp_before_sl= len(tp_hit)>0 and (len(sl_hit)==0 or tp_hit[0]<sl_hit[0])
        after=(P[x:e11]-entry)*dirn/TICK
        line=hi if dirn>0 else lo
        R.append(dict(d=d,dirn=dirn,kind=kind,ticks=ticks,mfe=mfe,tp11=len(tp_hit)>0,tpb4sl=tp_before_sl,
                      after_tp=(after>=1200).any() if len(after) else False,
                      retest=((P[x:e11]-line)*dirn<=0).any() if len(after) else False,
                      old=d<'2024'))
print("breakout trades",len(R),"on",len({r['d'] for r in R}),"days")
for lab,f in [("all",lambda r:True),("2021-23",lambda r:r['old']),("2025-26",lambda r:not r['old'])]:
    S=[r for r in R if f(r)]; n=len(S)
    c=collections.Counter(r['kind'] for r in S)
    print(f"\n== {lab}: {n} trades | exits {dict(c)}")
    print(f" price reached +1200 ticks from entry before 11:00 (any path): {sum(r['tp11'] for r in S)} ({100*sum(r['tp11'] for r in S)/n:.0f}%)")
    print(f" ... before the original 300-tick stop level: {sum(r['tpb4sl'] for r in S)} ({100*sum(r['tpb4sl'] for r in S)/n:.0f}%)")
    be=[r for r in S if r['kind']=='BE']
    if be:
        print(f" BE exits {len(be)}: later reached TP by 11:00 {sum(r['after_tp'] for r in be)}; came back to the line first {sum(r['retest'] for r in be)}; both {sum(r['after_tp'] and r['retest'] for r in be)}")
    m=np.array([r['mfe'] for r in S])
    print(" max favorable move before 11:00 (ticks), share of trades reaching:",{k:f"{100*(m>=k).mean():.0f}%" for k in [200,400,600,800,1000,1200,1600]})
