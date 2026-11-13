import pandas as pd, numpy as np
df=pd.read_csv('ff_trades.csv')
F=df.type=='fade'; B=df.type=='breakout'
rules={
 'fade: >=3 FVGs into line (last 15m)':F&(df.fvg15>=3),
 'fade: >=4 FVGs into line':F&(df.fvg15>=4),
 'fade: >=5 FVGs into line':F&(df.fvg15>=5),
 'fade: fill in first 2 min after open':F&(df.entry_min<2),
 'fade: fill in first 1 min':F&(df.entry_min<1),
 'fade: VIX > 25':F&(df.vix>25),
 'fade: VIX > 30':F&(df.vix>30),
 'fade: big 1m bar >150 ticks last 15m':F&(df.bigbar15>150),
 'fade: price ran >260 ticks into line in 15m':F&(df.toward15>260),
 'fade: 7:30 news shock >3x':F&(df.news730>3),
 'fade: open in top 20% of range':F&(df.open_pos>0.8),
 'fade: Monday':F&(df.dow=='Mon'),
 'breakout: triggered in first 6 min':B&(df.entry_min<6),
 'breakout: triggered 1-6 min':B&(df.entry_min>=1)&(df.entry_min<6),
 'breakout: triggered first 3 min':B&(df.entry_min<3),
 'breakout: 7:30 news shock >4x':B&(df.news730>4),
 'breakout: range 200-270 ticks':B&(df.range_t>200)&(df.range_t<270),
}
print(f"{'rule':44} {'skipped':>7} {'fast-fails caught':>17} | {'change 2021-23':>14} {'change 2025-26':>14} | both better?")
for k,m in rules.items():
    x=df[m]; o=-x[x.period=='old'].pnl.sum(); n=-x[x.period=='new'].pnl.sum()
    print(f"{k:44} {m.sum():7} {int(x.fast_fail.sum()):6} of {int(df[df.type==x.type.iloc[0]].fast_fail.sum()) if len(x) else 0:<9} | {o:+14,.0f} {n:+14,.0f} | {'YES' if o>0 and n>0 else ''}")
