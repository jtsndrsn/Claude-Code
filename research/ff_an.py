import pandas as pd, numpy as np
df=pd.read_csv('ff_trades.csv'); df['dirs']=df.dirn.map({1:'L',-1:'S'})
ff=df[df.fast_fail==1]
print("fast fails",len(ff),"of",len(df),f"({100*len(ff)/len(df):.0f}%) cost ${-ff.pnl.sum():,.0f}; by type",ff.type.value_counts().to_dict(),"by period",ff.period.value_counts().to_dict())
print("secs to stop percentiles (10/25/50/75):",ff.secs_to_sl.quantile([.1,.25,.5,.75]).round().tolist())
print("\nQuickest 25:")
cols=['date','type','dirs','entry_min','secs_to_sl','mfe','pnl','news730','fomc','vix','vixchg','range_atr','toward5','bigbar15','fvg15','rsi1m','line_beyond_pd','prior_sweep','open_vs_pd','with_trend']
print(ff.sort_values('secs_to_sl')[cols].head(25).round(2).to_string(index=False))
