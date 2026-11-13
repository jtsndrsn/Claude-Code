import json,numpy as np,bisect,sys
Z=np.load(sys.argv[1] if len(sys.argv)>1 else 's9.npz'); P=Z['pnl'].astype(np.float64); P=np.nan_to_num(P,nan=-1e9); days=list(Z['days']); prm=[json.loads(s) for s in Z['params']]
ser=[]
for f in ['ema_features2.json','ema_features.json']: ser+=json.load(open(f))
ser.sort(); sd=[x[0] for x in ser]
dist=np.zeros(len(days)); slope=np.zeros(len(days))
for i,d in enumerate(days):
    j=bisect.bisect_left(sd,d)-1
    dist[i]=(ser[j][1]-ser[j][2])/0.25
    slope[i]=(ser[j][2]-ser[j-5][2])/0.25 if j>=5 else 0
old=np.array([d<'2024' for d in days]); new=~old
def dd(x):
    e=np.cumsum(x); return float((np.maximum.accumulate(np.maximum(e,0))-e).max())
def t(s): return f"{s//3600}:{s%3600//60:02d}"
def desc(p):
    b=p.get('brk')
    return (f"R{t(p['rs'])}-{t(p['re'])} end{t(p['te'])} dl{p['delay']} sl{p['sl']} tp{p['tp']}/{p['ttp']} be{p.get('bt')}/{p.get('bo')} "
            f"skip{int(p['skip'])} tf{p.get('tfilter',0)} mom{int(bool(p.get('dayf')))} vix{p['vix_th']} brk{(b['offset'],b['sl'],b['tp']) if b else None}")
def labels(X,hyst=True,conf=1):
    """+1 above, -1 below, 0 near. hyst: near band keeps prior trend label unless never set... (returns raw and side-memory)"""
    raw=np.where(dist>X,1,np.where(dist<-X,-1,0))
    mem=np.zeros(len(days),int); last=0
    for i in range(len(days)):
        if i>0 and days[i][:4]!=days[i-1][:4] and days[i]>'2024' and days[i-1]<'2024': last=0
        if raw[i]!=0: last=raw[i]
        mem[i]=last           # side price last came from (+1 came down from above, -1 came up from below)
    return raw,mem
