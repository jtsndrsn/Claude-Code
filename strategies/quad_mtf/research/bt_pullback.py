"""Trend-pullback test: higher TFs (240m / 1D) set direction, fast-TF Quad alignment in the opposite
extreme is the entry. Uptrend + fast TFs oversold -> long; downtrend + fast TFs overbought -> short.
Trend uses confirmed (closed-bar) values. Same execution/costs as bt_align.py.
Usage: python bt_pullback.py old.npz new.npz out.csv
"""
import sys, itertools
import numpy as np
import pandas as pd
from bt_align import load, run, fwd, pf, STOPS, TGTS, RTH

SLOPE_BARS = 480   # 30s bars = 4 hours


def trend(D, kind):
    """+1 up, -1 down, 0 none."""
    a240, a1d = D["240_conf_avg"], D["1D_conf_avg"]
    def lvl(a): return np.where(a >= 50, 1, -1) * ~np.isnan(a)
    def slope(a):
        prev = np.r_[np.full(SLOPE_BARS, np.nan), a[:-SLOPE_BARS]]
        return np.sign(np.nan_to_num(a - prev))
    if kind == "240 lvl": return lvl(a240)
    if kind == "240 slope": return slope(a240)
    if kind == "1D lvl": return lvl(a1d)
    if kind == "1D slope": return slope(D["1D_conf_s4"])
    if kind == "240+1D lvl":
        x, y = lvl(a240), lvl(a1d); return np.where(x == y, x, 0)
    if kind == "240 red>50": return lvl(D["240_conf_s4"])
    raise ValueError(kind)


def signals(D, tfs, line, mode, trig, tr, ob=80, os_=20):
    vals = np.vstack([D[f"{tf}_{mode}_{line}"] for tf in tfs])
    valid = ~np.isnan(vals).any(0)
    aob = valid & (vals >= ob).all(0); aos = valid & (vals <= os_).all(0)
    pob = np.r_[False, aob[:-1]]; pos = np.r_[False, aos[:-1]]
    if trig == "onset":
        s_short, s_long = aob & ~pob, aos & ~pos
    else:
        s_short, s_long = ~aob & pob, ~aos & pos
    rth = (D["ctsec"] >= RTH[0]) & (D["ctsec"] < RTH[1])
    out = [(i, -1) for i in np.flatnonzero(s_short & rth & (tr == -1))]
    out += [(i, 1) for i in np.flatnonzero(s_long & rth & (tr == 1))]
    return sorted(out)


FAST = [("30S-15m", ["30S", "1", "5", "15"]), ("1m-15m", ["1", "5", "15"]),
        ("1m-5m", ["1", "5"]), ("5m-15m", ["5", "15"])]
TRENDS = ["240 lvl", "240 slope", "240 red>50", "1D lvl", "1D slope", "240+1D lvl"]


def main(paths, out_csv):
    data = {p.split("/")[-1].replace(".npz", ""): load(p) for p in paths}
    trs = {k: {t: trend(D, t) for t in TRENDS} for k, D in data.items()}
    rows = []
    for tname, (fname, tfs), line, mode, trig in itertools.product(TRENDS, FAST, ["avg", "s1"], ["live", "conf"], ["onset", "release"]):
        sg = {k: signals(D, tfs, line, mode, trig, trs[k][tname]) for k, D in data.items()}
        print(f"{tname:10s} {fname:7s} {line:3s} {mode:4s} {trig:7s} | " + " | ".join(
            f"{k}: sig={len(v):5d} {fwd(data[k], v)}" for k, v in sg.items()), flush=True)
        for st, tg in itertools.product(STOPS, TGTS):
            r = {"trend": tname, "fast": fname, "line": line, "mode": mode, "trig": trig, "stop": st, "tgt": tg}
            for k, D in data.items():
                p = run(D, sg[k], st, tg)
                r[f"{k}_n"] = len(p); r[f"{k}_win"] = round(np.mean(p > 0) * 100, 1) if len(p) else 0
                r[f"{k}_pf"] = round(pf(p), 2) if len(p) else 0; r[f"{k}_tot"] = round(p.sum())
            rows.append(r)
    df = pd.DataFrame(rows)
    df["min_pf"] = df[[c for c in df.columns if c.endswith("_pf")]].min(axis=1)
    df = df.sort_values("min_pf", ascending=False)
    df.to_csv(out_csv, index=False)
    print("\nTop 25 by worst-period PF:")
    print(df.head(25).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:-1], sys.argv[-1])
