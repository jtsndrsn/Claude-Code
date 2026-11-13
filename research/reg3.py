exec(open('reg2.py').read().split("res=[]")[0])
names=['v3','v3 no breakouts','v3 breakout EVERY day','v3 vix0.5','v3 vix0.7','v3 with-trend fades only','v3 counter-trend fades only','no-brk with-trend','no-brk counter-trend']
for X in [500,1000,1500]:
    raw,mem=labels(X); lab=np.where(raw==0,10*mem,raw)
    print(f"\n## X={X}: net old(2022-23) / new(2025-26) per zone")
    for r,zn in [(1,'ABOVE'),(-1,'BELOW'),(10,'NEAR from above'),(-10,'NEAR from below')]:
        m=(lab==r)&ok
        print(f" {zn:16} ({(m&old).sum()}/{(m&new).sum()} days): "+" | ".join(f"{names[i]} {P[i,m&old].sum()/1000:.0f}k/{P[i,m&new].sum()/1000:.0f}k" for i in range(9)))
# CV with only v3 variants per zone
print()
for tr_name,train,test in [('old->new',old,new),('new->old',new,old)]:
    rs=[]
    for name,lab in schemes():
        out=np.zeros(len(days))
        for r in np.unique(lab):
            m=(lab==r)&ok; b=int(np.argmax(P[:9,m&train].sum(1))) if (m&train).sum()>=10 else 0; out[m]=P[b,m]
        x=out[test&ok]; rs.append((x.sum(),dd(x),name))
    rs.sort(reverse=True); print(tr_name,"v3 =",round(P[0,test&ok].sum()),"| best:",[(n,round(a),round(b)) for a,b,n in rs[:4]],"| median scheme",round(np.median([a for a,b,n in rs])))
