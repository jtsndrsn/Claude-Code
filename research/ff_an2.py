import pandas as pd, numpy as np
df=pd.read_csv('ff_trades.csv')
num=['entry_min','toward5','toward15','bigbar15','fvg15','rsi1m','news730','vix','vixchg','range_t','range_atr','pd_range_atr','on_range_atr','open_pos','d_rsi','ema_dist','ret5','d_macd']
cat=['dow','fomc','open_vs_pd','range_in_pd','line_beyond_pd','prior_sweep','with_trend','dirn']
def show(sub,lab):
    base=sub.fast_fail.mean()
    print(f"\n######## {lab}: {len(sub)} trades, fast-fail {100*base:.0f}%, avg ${sub.pnl.mean():.0f}")
    out=[]
    for f in num+cat:
        s=sub[f]
        if f in num:
            try: b=pd.qcut(s,5,duplicates='drop')
            except Exception: continue
        else: b=s
        g=sub.groupby(b,observed=True)
        for k,x in g:
            if len(x)<25: continue
            o=x[x.period=='old']; n=x[x.period=='new']
            out.append((f,str(k),len(x),100*x.fast_fail.mean(),x.pnl.mean(),
                        100*o.fast_fail.mean() if len(o) else np.nan,100*n.fast_fail.mean() if len(n) else np.nan,
                        o.pnl.mean() if len(o) else np.nan,n.pnl.mean() if len(n) else np.nan))
    o=pd.DataFrame(out,columns=['feat','bucket','n','ff%','avg$','ff%old','ff%new','avg$old','avg$new'])
    o['lift']=o['ff%']/(100*base)
    # consistent: both periods above base by 30%+
    print("-- highest fast-fail buckets (both periods shown):")
    print(o.sort_values('ff%',ascending=False).head(18).round(1).to_string(index=False))
    print("-- lowest:")
    print(o.sort_values('ff%').head(8).round(1).to_string(index=False))
show(df[df.type=='fade'],'FADES')
show(df[df.type=='breakout'],'BREAKOUTS')
