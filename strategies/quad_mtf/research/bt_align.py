"""Backtest the Quad MTF alignment signal on 30s bars.
Overbought alignment -> short, oversold alignment -> long (reversal idea).
Entry at the next 30s bar's open; stop/target grid, max hold, one trade at a time.
10 MNQ ($20/pt), $0.74/side/contract commission. Ties inside a 30s bar count as stop.
Usage: python bt_align.py old.npz new.npz
"""
import sys, itertools
import numpy as np

PT = 20.0; COMM = 0.74 * 2 * 10
STOPS = [15, 25, 40, 60]
TGTS = [15, 25, 40, 60, 100]
MAXHOLD = 240           # 30s bars = 120 min
RTH = (8 * 3600 + 30 * 60, 15 * 3600)

def load(p):
    z = np.load(p, allow_pickle=False)
    return {k: z[k] for k in z.files}

def signals(D, tfs, line, mode, trig, ob=80, os_=20, minn=None):
    n = len(D["t"])
    need = len(tfs) if minn is None else minn
    vals = np.vstack([D[f"{tf}_{mode}_{line}"] for tf in tfs])
    valid = ~np.isnan(vals).any(0)
    obc = (vals >= ob).sum(0); osc = (vals <= os_).sum(0)
    aob = valid & (obc >= need); aos = valid & (osc >= need)
    prev_ob = np.r_[False, aob[:-1]]; prev_os = np.r_[False, aos[:-1]]
    if trig == "onset":
        s_short = aob & ~prev_ob; s_long = aos & ~prev_os
    else:  # release: alignment just ended
        s_short = ~aob & prev_ob; s_long = ~aos & prev_os
    rth = (D["ctsec"] >= RTH[0]) & (D["ctsec"] < RTH[1])
    out = [(i, -1) for i in np.flatnonzero(s_short & rth)] + [(i, 1) for i in np.flatnonzero(s_long & rth)]
    return sorted(out)

def run(D, sigs, stop, tgt):
    t, o, h, l, c, sess = D["t"], D["o"], D["h"], D["l"], D["c"], D["sess"]
    n = len(t); busy_until = -1; pnl = []
    for i, d in sigs:
        e = i + 1
        if e >= n or e <= busy_until or sess[e] != sess[i] or t[e] - t[i] > 120:
            continue
        end = min(n, e + MAXHOLD)
        same = sess[e:end] == sess[e]
        end = e + (np.argmin(same) if not same.all() else len(same))
        px = o[e]
        hh, ll = h[e:end], l[e:end]
        if d == 1:
            hs = np.flatnonzero(ll <= px - stop); ht = np.flatnonzero(hh >= px + tgt)
        else:
            hs = np.flatnonzero(hh >= px + stop); ht = np.flatnonzero(ll <= px - tgt)
        js = hs[0] if len(hs) else 10**9; jt = ht[0] if len(ht) else 10**9
        if js == 10**9 and jt == 10**9:
            j = end - e - 1; r = d * (c[e + j] - px)
        elif js <= jt:
            j = js; r = -stop
        else:
            j = jt; r = tgt
        busy_until = e + j
        pnl.append(r * PT - COMM)
    return np.array(pnl)

def stats(p):
    if len(p) == 0: return "n=0"
    w = p[p > 0].sum(); ls = -p[p < 0].sum()
    pf = w / ls if ls else np.inf
    return f"n={len(p):5d} win={np.mean(p>0)*100:5.1f}% avg=${p.mean():7.1f} PF={pf:4.2f} tot=${p.sum():9.0f}"

def fwd(D, sigs, horizons=(10, 30, 60, 120)):
    """Mean favourable move (pts, signal direction) at N minutes after entry."""
    c, o, n = D["c"], D["o"], len(D["c"])
    res = []
    for m in horizons:
        k = m * 2; v = [d * (c[min(n - 1, i + k)] - o[min(n - 1, i + 1)]) for i, d in sigs if i + k < n]
        res.append(f"{m}m:{np.mean(v):+5.1f}")
    return " ".join(res)

CONFIGS = [
    ("30S-15m", ["30S", "1", "5", "15"]),
    ("1m-15m", ["1", "5", "15"]),
    ("all 6", ["30S", "1", "5", "15", "240", "1D"]),
]

def pf(p):
    w = p[p > 0].sum(); ls = -p[p < 0].sum()
    return w / ls if ls else np.inf

def main(paths, out_csv=None):
    data = {p.split("/")[-1].replace(".npz", ""): load(p) for p in paths}
    rows = []
    for (name, tfs), line, mode, trig in itertools.product(CONFIGS, ["avg", "s1"], ["live", "conf"], ["onset", "release"]):
        sg = {k: signals(D, tfs, line, mode, trig) for k, D in data.items()}
        print(f"{name:8s} {line:3s} {mode:4s} {trig:7s} | " + " | ".join(
            f"{k}: sig={len(v):5d} fwd {fwd(data[k], v)}" for k, v in sg.items()), flush=True)
        for st, tg in itertools.product(STOPS, TGTS):
            r = {"cfg": name, "line": line, "mode": mode, "trig": trig, "stop": st, "tgt": tg}
            for k, D in data.items():
                p = run(D, sg[k], st, tg)
                r[f"{k}_n"] = len(p); r[f"{k}_win"] = round(np.mean(p > 0) * 100, 1) if len(p) else 0
                r[f"{k}_pf"] = round(pf(p), 2) if len(p) else 0; r[f"{k}_tot"] = round(p.sum())
            rows.append(r)
    import pandas as pd
    df = pd.DataFrame(rows)
    pfc = [c for c in df.columns if c.endswith("_pf")]
    df["min_pf"] = df[pfc].min(1)
    df = df.sort_values("min_pf", ascending=False)
    if out_csv: df.to_csv(out_csv, index=False)
    print("\nTop 15 by worst-period PF:")
    print(df.head(15).to_string(index=False))

if __name__ == "__main__":
    args = sys.argv[1:]
    out = args.pop() if args[-1].endswith(".csv") else None
    main(args, out)
