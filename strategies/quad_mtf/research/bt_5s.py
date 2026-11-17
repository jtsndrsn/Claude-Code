"""5-second QuadRotation continuation test.
Long when Stoch 1, Stoch 4 and the weighted Average are all above 85 (first 5s bar they all are);
short when all three are below 15. Entry at the open of the next 1s bar after the signal bar closes.
TP 200 ticks, SL 100 ticks, optional breakeven: at +100 ticks move the stop to entry + 3 ticks.
Exits simulated on 1s bars; if stop and target fall in the same 1s bar, the stop counts.
10 MNQ ($5/tick), $0.74/side/contract. One trade at a time.
Data: research/build_cache.py output (1s front month, 07:00-13:00 CT per day).
Usage: python bt_5s.py cache_old.npz cache_new.npz
"""
import sys
import numpy as np
import pandas as pd

TICK = 0.25; TUSD = 5.0; COMM = 0.74 * 2 * 10
K = [(9, 3), (14, 3), (40, 4), (60, 10)]
W = [0.2, 0.6, 1.4, 1.8]
START, END = 8 * 3600 + 30 * 60, 13 * 3600      # entries 08:30 until data ends at 13:00 CT


def quad(h, l, c):
    H, L, C = pd.Series(h), pd.Series(l), pd.Series(c)
    ds = []
    for k, d in K:
        hh = H.rolling(k).max(); ll = L.rolling(k).min()
        raw = 100 * (C - ll) / (hh - ll)
        ds.append(raw.rolling(d).mean().values)
    avg = sum((ds[i] - 50) * W[i] for i in range(4)) / 4 + 50
    return ds[0], ds[3], avg


def day_trades(t, p, cfg):
    o, h, l, c = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
    b = t // 5                                   # 5s bucket (clock aligned)
    last = np.r_[b[1:] != b[:-1], True]
    first = np.r_[True, b[1:] != b[:-1]]
    gid = np.cumsum(first) - 1
    bh = pd.Series(h).groupby(gid).max().values; bl = pd.Series(l).groupby(gid).min().values
    bc = c[last]; bend = b[last] * 5 + 5           # 5s bar close time
    s1, s4, av = quad(bh, bl, bc)
    hi, lo = cfg["hi"], cfg["lo"]
    up = (s1 > hi) & (s4 > hi) & (av > hi); dn = (s1 < lo) & (s4 < lo) & (av < lo)
    sig = np.zeros(len(bc), int)
    sig[up & ~np.r_[False, up[:-1]]] = 1
    sig[dn & ~np.r_[False, dn[:-1]]] = -1
    if cfg.get("fade"): sig = -sig
    out = []; free_at = -1
    for j in np.flatnonzero(sig):
        if bend[j] < START or bend[j] >= END - 5: continue
        e = int(np.searchsorted(t, bend[j]))        # first 1s bar after the 5s bar closed
        if e >= len(t) or e <= free_at or t[e] - bend[j] > 10: continue
        d = sig[j]; px = o[e]
        sl = cfg["sl"] * TICK; tp = cfg["tp"] * TICK
        hh, ll = h[e:], l[e:]
        fav = (hh - px) if d == 1 else (px - ll)     # best move within each 1s bar
        adv = (px - ll) if d == 1 else (hh - px)     # worst move within each 1s bar
        stop = np.full(len(hh), -sl)
        if cfg.get("be"):
            k = np.flatnonzero(fav >= cfg["be"] * TICK)
            if len(k): stop[k[0] + 1:] = cfg["be_off"] * TICK   # stop moves after the trigger bar
        hit_s = np.flatnonzero(-adv <= stop); hit_t = np.flatnonzero(fav >= tp)
        js = hit_s[0] if len(hit_s) else 10**9; jt = hit_t[0] if len(hit_t) else 10**9
        if js == 10**9 and jt == 10**9:
            x = len(hh) - 1; r = d * (c[e + x] - px); kind = "EOD"
        elif js <= jt:
            x = js; r = stop[js] - cfg.get("slip", 0) * TICK; kind = "SL" if stop[js] < 0 else "BE"
        else:
            x = jt; r = tp; kind = "TP"
        free_at = e + x
        out.append((d, r / TICK * TUSD - COMM, kind, int(t[e]), int(t[e + x]) - int(t[e])))
    return out


def run(path, cfg):
    z = np.load(path); rows = []
    for d in z["_days"]:
        for x in day_trades(z[d + "_t"].astype(np.int64), z[d + "_p"], cfg):
            rows.append((d, *x))
    return pd.DataFrame(rows, columns=["date", "dir", "net", "kind", "t_in", "secs"])


def summary(df):
    if df.empty: return "no trades"
    p = df.net.values; eq = np.cumsum(p); dd = (np.maximum.accumulate(eq) - eq).max()
    pf = p[p > 0].sum() / -p[p < 0].sum() if (p < 0).any() else np.inf
    k = df.kind.value_counts(normalize=True).mul(100).round(0).to_dict()
    return (f"n={len(p):5d} ({len(p)/df.date.nunique():.1f}/day) win={np.mean(p>0)*100:4.1f}% PF={pf:4.2f} "
            f"net=${p.sum():9.0f} avg=${p.mean():6.1f} maxDD=${dd:7.0f} exits {k}")


if __name__ == "__main__":
    base = dict(hi=85, lo=15, tp=200, sl=100)
    variants = [("as specified, no BE", dict(base)),
                ("as specified, BE 100 -> +3", dict(base, be=100, be_off=3)),
                ("BE, 1 tick slippage on stops", dict(base, be=100, be_off=3, slip=1)),
                ("reverse (fade), BE", dict(base, be=100, be_off=3, fade=True))]
    for name, cfg in variants:
        print(f"\n=== {name}")
        for path in sys.argv[1:]:
            df = run(path, cfg)
            lab = "2021-23" if "db2" in path else "2025-26"
            print(f"  {lab}: {summary(df)}", flush=True)
            for dn, g in df.groupby("dir"):
                print(f"      {'long ' if dn == 1 else 'short'} {summary(g)}")
