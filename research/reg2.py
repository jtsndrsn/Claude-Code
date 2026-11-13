exec(open('reg.py').read())
ok=np.array([d>='2022-01-01' or d>'2024' for d in days])
def sticky(X,N):
    """trend label changes only after N consecutive days beyond +/-X; inside band keep last label (no flipping)"""
    lab=np.zeros(len(days),int); cur=0; run=0; rs=0
    for i in range(len(days)):
        s=1 if dist[i]>X else (-1 if dist[i]<-X else 0)
        if s!=0 and s==rs: run+=1
        else: rs=s; run=1 if s!=0 else 0
        if s!=0 and run>=N: cur=s
        lab[i]=cur
    return lab
def schemes():
    for X in [250,500,750,1000,1500]:
        raw,mem=labels(X)
        yield f"3-zone X={X}",raw
        yield f"4-zone(approach side) X={X}",np.where(raw==0,10*mem,raw)
        for N in [1,3,5]: yield f"sticky 2-zone X={X} N={N}",sticky(X,N)
    yield "plain above/below EMA",np.sign(dist).astype(int)
def pick(mask,train):
    s=P[:,mask&train].sum(1); return int(np.argmax(s))
def evaluate(lab,train,test,base=0):
    tot=np.zeros(test.sum()); cfg={}
    out=np.zeros(len(days))
    for r in np.unique(lab):
        m=(lab==r)&ok
        if (m&train).sum()<10: b=base
        else: b=pick(m,train)
        cfg[r]=b; out[m]=P[b,m]
    return out,cfg
res=[]
for tr_name,train,test in [('old->new',old,new),('new->old',new,old)]:
    v3=P[0].copy(); v3[~ok]=0
    single=int(np.argmax(P[:,train&ok].sum(1)))
    print(f"\n=== train {tr_name}: test-period v3 {v3[test&ok].sum():.0f} dd {dd(v3[test&ok]):.0f} | single best-on-train config: {P[single,test&ok].sum():.0f} dd {dd(P[single,test&ok]):.0f}")
    for name,lab in schemes():
        out,cfg=evaluate(lab,train,test)
        x=out[test&ok]; flips=int((np.diff(lab[ok])!=0).sum())
        res.append((tr_name,name,x.sum(),dd(x),flips))
    for r in sorted([r for r in res if r[0]==tr_name],key=lambda r:-r[2])[:10]:
        print(f"  {r[1]:32} test net {r[2]:8.0f} dd {r[3]:7.0f} zone changes {r[4]}")
    print("  worst:",[ (r[1],round(r[2])) for r in sorted([r for r in res if r[0]==tr_name],key=lambda r:r[2])[:3]])
