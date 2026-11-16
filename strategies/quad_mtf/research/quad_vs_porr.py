"""Do QuadRotation readings at entry predict PORR v3 trades that hit the stop quickly?
Values are trade-aligned: long = value, short = 100 - value (low = oversold vs the trade direction)."""
import sys
import numpy as np, pandas as pd
df = pd.read_csv(sys.argv[1])
df["per"] = np.where(df.date < "2024", "21-23", "25-26")
tfs = ["30S", "1", "5", "15", "240", "1D"]
feats = [f"{tf}_{m}_{ln}" for tf in tfs for m in ("live", "conf") for ln in ("s1", "s4", "avg")]
for f in feats:
    df[f] = np.where(df.dir == 1, df[f], 100 - df[f])

def auc(x, y):  # P(feature of a positive > feature of a negative)
    x = np.asarray(x); y = np.asarray(y); m = ~np.isnan(x); x, y = x[m], y[m]
    r = pd.Series(x).rank().values; n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else np.nan

for typ in ("fade", "breakout"):
    g = df[df.type == typ].copy()
    sl = g[g.kind == "SL"]
    cut = sl.mins.median()
    g["quick"] = ((g.kind == "SL") & (g.mins <= cut)).astype(int)
    print(f"\n##### {typ}: {len(g)} trades, {len(sl)} SL, quick = SL within {cut:.1f} min (median)")
    for per in ("21-23", "25-26"):
        h = g[g.per == per]; s = h[h.kind == "SL"]
        print(f"  {per}: n={len(h)} SL={len(s)} quick={h.quick.sum()} SL minutes median {s.mins.median():.1f}")
    res = []
    for f in feats:
        a = [auc(g[g.per == p][f], g[g.per == p].quick) for p in ("21-23", "25-26")]
        means = [g[(g.quick == 1)][f].mean(), g[(g.kind == "SL") & (g.quick == 0)][f].mean(), g[g.kind != "SL"][f].mean()]
        res.append((f, *a, *means))
    r = pd.DataFrame(res, columns=["feature", "auc_21_23", "auc_25_26", "mean_quickSL", "mean_slowSL", "mean_notSL"])
    r["consistent"] = np.where((r.auc_21_23 - .5) * (r.auc_25_26 - .5) > 0, np.minimum(abs(r.auc_21_23 - .5), abs(r.auc_25_26 - .5)), 0)
    print(r.sort_values("consistent", ascending=False).head(12).round(3).to_string(index=False))
    df.loc[g.index, "quick"] = g.quick
df.to_csv(sys.argv[2], index=False)
