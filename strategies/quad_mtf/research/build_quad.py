"""30s bar CSV (agg30.py output) -> continuous back-adjusted front-month MNQ + QuadRotation values
on 30S/1/5/15/240/1D, mapped onto the 30s timeline.

For each timeframe two versions are stored:
  live : value of the still-forming higher-TF bar at each 30s close (what you see watching that chart)
  conf : value of the last closed higher-TF bar (no repaint)
Usage: python build_quad.py in.csv out.npz
"""
import sys
import numpy as np
import pandas as pd

K = [(9, 3), (14, 3), (40, 4), (60, 10)]   # (%K length, %D smoothing); Stoch 4 smoothK = 1
W = [0.2, 0.6, 1.4, 1.8]
MONTHS = "FGHJKMNQUVXZ"
TFS = ["30S", "1", "5", "15", "240", "1D"]


def load(path):
    df = pd.read_csv(path, names=["sym", "t", "o", "h", "l", "c", "v"])
    df = df.sort_values(["t", "sym"]).reset_index(drop=True)
    ct = pd.to_datetime(df.t, unit="s", utc=True).dt.tz_convert("America/Chicago")
    # CME session date: 17:00 CT starts next day's session
    df["sess"] = (ct + pd.Timedelta(hours=7)).dt.strftime("%Y-%m-%d")
    df["ctsec"] = ct.dt.hour * 3600 + ct.dt.minute * 60 + ct.dt.second
    return df


def expiry_key(sym, sess_year):
    m = MONTHS.index(sym[3]); d = int(sym[4])
    y = sess_year - sess_year % 10 + d
    if y < sess_year - 1: y += 10
    return y * 12 + m


def continuous(df):
    vol = df.groupby(["sess", "sym"]).v.sum().reset_index()
    front = {}
    last_key = -1
    for s, g in vol.groupby("sess"):
        sym = g.loc[g.v.idxmax(), "sym"]
        k = expiry_key(sym, int(s[:4]))
        if k < last_key:                     # never roll back to an earlier contract
            sym = prev; k = last_key
        front[s] = sym; prev = sym; last_key = k
    df["front"] = df.sess.map(front)
    cont = df[df.sym == df.front].copy().reset_index(drop=True)
    # back-adjust: at each roll, shift all earlier prices by (new - old) at the last common bar
    sess_list = sorted(front)
    adj = pd.Series(0.0, index=sess_list)
    piv = df.pivot_table(index="t", columns="sym", values="c")
    cum = 0.0
    for i in range(len(sess_list) - 1, 0, -1):
        s0, s1 = sess_list[i - 1], sess_list[i]
        adj[s1] = cum
        if front[s0] != front[s1]:
            a, b = front[s0], front[s1]
            ts = df[(df.sess == s0)].t.unique()
            both = piv.loc[piv.index.isin(ts), [a, b]].dropna()
            if len(both):
                cum += both.iloc[-1][b] - both.iloc[-1][a]
    adj[sess_list[0]] = cum
    off = cont.sess.map(adj).values
    for c in "ohlc":
        cont[c] = cont[c] + off
    return cont


def group_ids(cont, tf):
    t = cont.t.values
    if tf == "30S":
        key = t // 30
    elif tf in ("1", "5", "15"):
        key = t // (60 * int(tf))
    elif tf == "240":
        since17 = (cont.ctsec.values - 17 * 3600) % 86400
        key = pd.factorize(cont.sess)[0] * 10 + since17 // 14400
    else:
        key = pd.factorize(cont.sess)[0]
    chg = np.r_[True, key[1:] != key[:-1]]
    return np.cumsum(chg) - 1


def quad_tf(cont, gid):
    h, l, c = cont.h.values, cont.l.values, cont.c.values
    G = gid[-1] + 1
    gs = pd.Series(gid)
    rh = pd.Series(h).groupby(gs).cummax().values     # running high of forming bar
    rl = pd.Series(l).groupby(gs).cummin().values
    last = np.r_[gid[1:] != gid[:-1], True]
    H = pd.Series(h).groupby(gs).max().values; L = pd.Series(l).groupby(gs).min().values
    C = c[last]
    live_d = []; fin_d = []
    for k, d in K:
        Hs, Ls = pd.Series(H), pd.Series(L)
        if k > 1:
            pmax = Hs.rolling(k - 1).max().shift(1).values; pmin = Ls.rolling(k - 1).min().shift(1).values
        else:
            pmax = np.full(G, -np.inf); pmin = np.full(G, np.inf)
        HH = np.maximum(pmax[gid], rh); LL = np.minimum(pmin[gid], rl)
        with np.errstate(invalid="ignore", divide="ignore"):
            raw_live = 100 * (c - LL) / (HH - LL)
        fHH = np.maximum(pmax, H); fLL = np.minimum(pmin, L)
        with np.errstate(invalid="ignore", divide="ignore"):
            raw_fin = 100 * (C - fLL) / (fHH - fLL)
        if d > 1:
            psum = pd.Series(raw_fin).rolling(d - 1).sum().shift(1).values
        else:
            psum = np.zeros(G)
        live_d.append((psum[gid] + raw_live) / d)
        fin_d.append((psum + raw_fin) / d)
    def avg(v):
        return sum((v[i] - 50) * W[i] for i in range(4)) / 4 + 50
    live = (live_d[0], live_d[3], avg(live_d))
    fin = (fin_d[0], fin_d[3], avg(fin_d))
    # confirmed: final of current bar if this 30s bar closes it, else previous bar's final
    gprev = np.where(last, gid, gid - 1)
    conf = tuple(np.where(gprev >= 0, f[np.maximum(gprev, 0)], np.nan) for f in fin)
    return live, conf


def main(src, out):
    df = load(src)
    cont = continuous(df)
    store = {k: cont[k].values for k in ["t", "o", "h", "l", "c", "ctsec"]}
    store["sess"] = cont.sess.to_numpy(dtype="U10")
    for tf in TFS:
        gid = group_ids(cont, tf)
        live, conf = quad_tf(cont, gid)
        for name, vals in (("live", live), ("conf", conf)):
            for line, v in zip(("s1", "s4", "avg"), vals):
                store[f"{tf}_{name}_{line}"] = v.astype(np.float32)
        print(tf, "bars", gid[-1] + 1, flush=True)
    np.savez_compressed(out, **store)
    print("rows", len(cont), "sessions", cont.sess.nunique())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
