"""Daily MACD(12,26,9) histogram and DMI(14) trend per trading day, from the PREVIOUS completed session.
Session = 17:00 CT (prev day) .. 16:00 CT, front = highest-volume contract, additive back-adjust at rolls.
usage: python3 daily_mom.py <mnq_1m.csv> <out.json>"""
import sys, json, bisect
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
ohlc = defaultdict(dict)
with open(sys.argv[1]) as fh:
    fh.readline()
    for line in fh:
        ts, sym, o, h, l, c, v = line.rstrip("\n").split(",")
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).astimezone(CT)
        sd = (dt + timedelta(hours=7)).date()
        o, h, l, c, v = float(o), float(h), float(l), float(c), int(v)
        x = ohlc[sd].get(sym)
        if x is None: ohlc[sd][sym] = [o, h, l, c, v]
        else: x[1] = max(x[1], h); x[2] = min(x[2], l); x[3] = c; x[4] += v
dates = sorted(d for d in ohlc if d.weekday() < 5)
front = {d: max(ohlc[d], key=lambda s: ohlc[d][s][4]) for d in dates}
ser = []; adj = 0.0; prev = None
for d in reversed(dates):
    s = front[d]
    if prev and s != prev and prev in ohlc[d]: adj += ohlc[d][prev][3] - ohlc[d][s][3]
    o, h, l, c, v = ohlc[d][s]; ser.append((d, h + adj, l + adj, c + adj)); prev = s
ser.reverse()
dd = [x[0] for x in ser]; H = np.array([x[1] for x in ser]); L = np.array([x[2] for x in ser]); C = np.array([x[3] for x in ser])
def ema(a, n):
    out = np.empty_like(a); k = 2 / (n + 1); out[0] = a[0]
    for i in range(1, len(a)): out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out
def rma(a, n):
    out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)): out[i] = (out[i - 1] * (n - 1) + a[i]) / n
    return out
macd = ema(C, 12) - ema(C, 26); hist = macd - ema(macd, 9)
tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
upm = H - np.roll(H, 1); dnm = np.roll(L, 1) - L; upm[0] = dnm[0] = 0
pdm = np.where((upm > dnm) & (upm > 0), upm, 0); ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0)
atr = rma(tr, 14); pdi = 100 * rma(pdm, 14) / atr; ndi = 100 * rma(ndm, 14) / atr
out = {}
for i, d in enumerate(dd):
    if i == 0: continue
    out[d.isoformat()] = {"d_macd_hist": round(float(hist[i - 1]), 2), "d_di_trend": int(pdi[i - 1] > ndi[i - 1]), "warm": i}
json.dump(out, open(sys.argv[2], "w")); print("days", len(out), dd[0], dd[-1])
