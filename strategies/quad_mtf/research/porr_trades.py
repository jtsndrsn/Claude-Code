"""Rebuild PORR v3.0 trades (research/sys2.py engine) with entry/exit times, then attach QuadRotation
values (all 6 timeframes, live + confirmed) from build_quad.py output at the last 30s bar closed before entry.
Usage: python porr_trades.py <porr_data_dir> <quad_old.npz> <quad_new.npz> <out.csv>
porr_data_dir holds db/ and db2/ (cache_1s.npz, mnq_1m.csv, mom.json) and ext/vix.csv."""
import sys, os, csv, json, bisect
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
sys.path.insert(0, "/home/user/Claude-Code/research")
import sys2
from fastsim import load_days, sim_day_breakout

CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
S, QOLD, QNEW, OUT = sys.argv[1:5]

V3 = dict(sys2.BASE, sl=175, tp=500, ttp=1000, bt=100, bo=50, tsrc="D50", vix_th=0.9,
          brk=dict(mode="stop", offset=10, sl=300, tp=1200, be_trig=200, be_off=100, max_trades=2),
          dayf=[("agree2", 1, 2, 0.0)])          # skip long fades when prior-day MACD hist > 0 and +DI > -DI


def daily_trend(path):
    """D50: previous session close vs EMA50 of session closes (front contract, back-adjusted)."""
    ohlc = {}
    with open(path) as fh:
        fh.readline()
        for line in fh:
            ts, sym, o, h, l, c, v = line.rstrip("\n").split(",")
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).astimezone(CT)
            sd = (dt + timedelta(hours=7)).date()
            x = ohlc.setdefault(sd, {}).get(sym)
            if x is None: ohlc[sd][sym] = [float(c), int(v)]
            else: x[0] = float(c); x[1] += int(v)
    dates = sorted(d for d in ohlc if d.weekday() < 5)
    front = {d: max(ohlc[d], key=lambda s: ohlc[d][s][1]) for d in dates}
    closes = []; adj = 0.0; prev = None
    for d in reversed(dates):
        s = front[d]
        if prev and s != prev and prev in ohlc[d]: adj += ohlc[d][prev][0] - ohlc[d][s][0]
        closes.append(ohlc[d][s][0] + adj); prev = s
    closes.reverse(); C = np.array(closes)
    e = np.empty_like(C); k = 2 / 51; e[0] = C[0]
    for i in range(1, len(C)): e[i] = k * C[i] + (1 - k) * e[i - 1]
    return {d.isoformat(): (1 if C[i - 1] > e[i - 1] else -1) for i, d in enumerate(dates) if i >= 50}


def setup():
    D = {}; F = {}; DF = {}
    for sub in ("db", "db2"):
        D.update(load_days(f"{S}/{sub}/cache_1s.npz"))
        for d, tr in daily_trend(f"{S}/{sub}/mnq_1m.csv").items(): F[d] = {"trend": {"D50": tr}}
        for d, m in json.load(open(f"{S}/{sub}/mom.json")).items():
            DF[d] = {"d_macd_hist": m["d_macd_hist"], "d_di_trend": m["d_di_trend"], "dow": None}
    D = {d: v for d, v in D.items() if d in F}
    vix = {}
    for r in csv.DictReader(open(f"{S}/ext/vix.csv")):
        vix[datetime.strptime(r["DATE"], "%m/%d/%Y").date()] = float(r["CLOSE"])
    vd = sorted(vix); VCH = {}
    for d in D:
        i = bisect.bisect_left(vd, date.fromisoformat(d)); VCH[d] = (vix[vd[i - 1]] - vix[vd[i - 2]], vix[vd[i - 1]])
    RSI = {}
    for d, day in D.items():
        t = day["t"]; c = day["P"].reshape(-1, 4)[:, 3]
        m = t // 60; last = np.flatnonzero(np.diff(m, append=m[-1] + 1))
        RSI[d] = ((m[last] + 1) * 60, sys2._rsi(c[last]))
    sys2.D, sys2.F, sys2.DF, sys2.VCH, sys2.RSI = D, F, DF, VCH, RSI


EXIT_T = []
_orig_exit = sys2._exit
def _exit_spy(P, G, T, k, *a):
    r = _orig_exit(P, G, T, k, *a); EXIT_T.append(int(T[r[0]])); return r
sys2._exit = _exit_spy


def trades():
    p = V3; bo = dict(sys2.BO_DEFAULT, **p["brk"]); rows = []
    bo_cfg = dict(trade_start=p["re"], trade_end=p["te"], entry_end=p["te"], **bo)
    for d in sorted(sys2.D):
        day = sys2.D[d]
        if sys2.VCH[d][0] < -p["vix_th"]:
            tt = day["t"]; mm = (tt >= p["rs"]) & (tt < p["re"])
            if not mm.any(): continue
            hi, lo = float(day["h"][mm].max()), float(day["l"][mm].min())
            for x in sim_day_breakout(day, hi, lo, bo_cfg):
                rows.append(dict(date=d, type="breakout", dir=x[0], kind=x[3], ticks=x[4], t_in=x[5], t_out=x[6], with_trend=None))
            continue
        EXIT_T.clear()
        res = sys2.fade_day(d, p)
        for (dirn, ticks, kind, wt, ts), tx in zip(res, EXIT_T):
            if sys2.day_mult(d, p, dirn) <= 0: continue
            rows.append(dict(date=d, type="fade", dir=dirn, kind=kind, ticks=ticks, t_in=ts, t_out=tx, with_trend=int(wt)))
    df = pd.DataFrame(rows)
    df["net"] = df.ticks * sys2.TUSD * 10 - 2 * sys2.COMM_SIDE * 10
    df["mins"] = (df.t_out - df.t_in) / 60
    return df


def attach_quad(df):
    cols = None
    for path in (QOLD, QNEW):
        zf = np.load(path); t = zf["t"]
        tfs = ["30S", "1", "5", "15", "240", "1D"]
        keys = [f"{tf}_{m}_{ln}" for tf in tfs for m in ("live", "conf") for ln in ("s1", "s4", "avg")]
        cols = keys
        z = {k: zf[k] for k in keys}
        for i, r in df.iterrows():
            dd = date.fromisoformat(r.date)
            if (dd.year < 2024) != ("old" in os.path.basename(path)): continue
            ent = datetime(dd.year, dd.month, dd.day, tzinfo=CT) + timedelta(seconds=int(r.t_in))
            u = int(ent.timestamp())
            j = int(np.searchsorted(t, u - 30, side="right")) - 1     # last 30s bar fully closed before entry
            if j < 0 or u - t[j] > 600: continue
            for k in keys: df.at[i, k] = float(z[k][j])
    return df, cols


if __name__ == "__main__":
    setup()
    df = trades()
    for per, m in (("2021-23", df.date < "2024"), ("2025-26", df.date > "2024")):
        g = df[m]; print(per, "trades", len(g), "net", round(g.net.sum()), "by kind", g.kind.value_counts().to_dict())
    df, cols = attach_quad(df)
    df.to_csv(OUT, index=False); print("saved", OUT, len(df))
