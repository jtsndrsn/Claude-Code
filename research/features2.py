import os
"""Per-day levels (pre-open ranges, overnight, previous day) and trend states from the 1-minute data.
Saves db/features.json: {date: {sym, levels:{name:[hi,lo]}, trend:{name:+1/-1/0}}}"""
import json, glob, sys
from collections import defaultdict
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastsim import load_days, range_levels
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
S = os.environ.get("PORR_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
D = load_days(S + "/db2/cache_1s.npz")
days = sorted(D); sym_of = {d: D[d]["sym"] for d in days}
need = set(sym_of.values())
# ---- 1-minute bars per symbol (CT time)
m1 = defaultdict(list)   # sym -> [(dt_ct, o,h,l,c,v)]
with open(S + "/db2/mnq_1m.csv") as fh:
    fh.readline()
    for line in fh:
        ts, sym, o, h, l, c, v = line.rstrip("\n").split(",")
        if sym in need:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).astimezone(CT)
            m1[sym].append((dt, float(o), float(h), float(l), float(c), int(v)))
print("1m loaded", {s: len(v) for s, v in m1.items()})

import bisect
keys = {s: [r[0] for r in v] for s, v in m1.items()}
def rng(sym, a, b):
    k = keys[sym]; return m1[sym][bisect.bisect_left(k, a):bisect.bisect_left(k, b)]
def hilo(sym, a, b):
    xs = rng(sym, a, b)
    if not xs: return None
    return [max(r[2] for r in xs), min(r[3] for r in xs)]

# ---- continuous back-adjusted daily RTH closes (close of 14:59 bar), roll on day the front changes
daily = {}   # date -> (sym, close)
for s in need:
    by = {}
    for r in m1[s]:
        if time(8, 30) <= r[0].time() < time(15, 0):
            by[r[0].date()] = r[4]          # last RTH close of the day for this symbol
    for dd, c in by.items():
        daily.setdefault(dd, {})[s] = c
# front symbol per calendar day: use sym_of where known, else carry
cont = []  # (date, adjusted close) built backwards later
seq = sorted(daily)
front = {}
cur = sym_of[days[0]]
for dd in seq:
    k = dd.isoformat()
    if k in sym_of: cur = sym_of[k]
    front[dd] = cur
# Webull 2024 warm-up (daily closes of older contracts)
wb = {}
for f in glob.glob(S + "/wb_daily/*.json"):
    try:
        data = json.load(open(f))
        for blk in data:
            for b in blk["result"]:
                dd = datetime.strptime(b["time"][:10], "%Y-%m-%d").date()
                wb.setdefault(dd, {})[blk["symbol"]] = float(b["close"])
    except Exception as e:
        print("skip", f, e)
# build adjusted series backwards from the latest contract
closes = []  # list of (date, close) oldest..newest, adjusted to the latest contract
adj = 0.0; prev_sym = None
allc = dict(daily)
for dd, m in wb.items():
    if dd < seq[0]:
        allc.setdefault(dd, {}).update(m)
wb_front_order = ["MNQH4", "MNQM4", "MNQU4", "MNQZ4", "MNQH5"]
def front_for(dd):
    if dd in front: return front[dd]
    # older dates: highest-priority contract that has a close and is not expired (simple calendar rule)
    for s in wb_front_order:
        exp = {"MNQH4": date(2024, 3, 15), "MNQM4": date(2024, 6, 21), "MNQU4": date(2024, 9, 20),
               "MNQZ4": date(2024, 12, 20), "MNQH5": date(2025, 3, 21)}[s]
        if dd <= exp - timedelta(days=8) and s in allc.get(dd, {}): return s
    return None
series = []
for dd in sorted(allc, reverse=True):
    s = front_for(dd)
    if s is None or s not in allc[dd]: continue
    if prev_sym is not None and s != prev_sym:
        # roll: shift older contract onto the newer one using both closes on this day, if available
        if prev_sym in allc[dd] and s in allc[dd]:
            adj += allc[dd][prev_sym] - allc[dd][s]
    series.append((dd, allc[dd][s] + adj)); prev_sym = s
series.reverse()
print("daily series", series[0][0], "->", series[-1][0], len(series))

def ema(vals, n):
    a = 2 / (n + 1); e = None; out = []
    for v in vals:
        e = v if e is None else a * v + (1 - a) * e
        out.append(e)
    return out
dates = [x[0] for x in series]; vals = [x[1] for x in series]
e20d, e50d = ema(vals, 20), ema(vals, 50)
# weekly closes (last daily close of each ISO week)
wk = {}
for dd, v in series: wk[dd.isocalendar()[:2]] = (dd, v)
wks = sorted(wk.values()); wv = [v for _, v in wks]
e10w, e20w = ema(wv, 10), ema(wv, 20)

def last_before(lst_dates, lst_vals, lst_emas, dd):
    """trend sign using the last value strictly before date dd"""
    lo, hi = 0, len(lst_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst_dates[mid] < dd: lo = mid + 1
        else: hi = mid
    i = lo - 1
    if i < 0: return 0
    return 1 if lst_vals[i] > lst_emas[i] else -1

feat = {}
for d in days:
    dd = date.fromisoformat(d); s = sym_of[d]; day = D[d]
    lv = {}
    for name, a, b in (("PRE60", 7*3600+1800, 8*3600+1800), ("PRE30", 8*3600, 8*3600+1800), ("PRE90", 7*3600, 8*3600+1800)):
        r = range_levels(day, a, b)
        if r: lv[name] = list(r)
    prev = dd - timedelta(days=3 if dd.weekday() == 0 else 1)
    on = hilo(s, datetime.combine(prev, time(17, 0), CT), datetime.combine(dd, time(8, 30), CT))
    if on: lv["ON"] = on
    # previous trading day RTH: walk back to a day with RTH bars
    pd_ = None; p = dd - timedelta(days=1)
    for _ in range(5):
        pd_ = hilo(s, datetime.combine(p, time(8, 30), CT), datetime.combine(p, time(15, 0), CT))
        if pd_: break
        p -= timedelta(days=1)
    if pd_: lv["PD"] = pd_
    # hourly EMA50 on this symbol's own hourly closes up to 08:00 CT today
    hrs = {}
    for r in rng(s, datetime.combine(dd, time(8, 0), CT) - timedelta(days=10), datetime.combine(dd, time(8, 0), CT)):
        hrs[r[0].replace(minute=0)] = r[4]
    hv = [hrs[k] for k in sorted(hrs)]
    h50 = ema(hv, 50)
    tr = {"D20": last_before(dates, vals, e20d, dd), "D50": last_before(dates, vals, e50d, dd),
          "W10": last_before([x[0] for x in wks], wv, e10w, dd), "W20": last_before([x[0] for x in wks], wv, e20w, dd),
          "H50": (1 if hv[-1] > h50[-1] else -1) if len(hv) >= 50 else 0}
    feat[d] = dict(sym=s, levels=lv, trend=tr)
json.dump(feat, open(S + "/db2/features.json", "w"))
print("features", len(feat), "missing ON", sum('ON' not in f['levels'] for f in feat.values()),
      "missing PD", sum('PD' not in f['levels'] for f in feat.values()),
      "trend zeros", {k: sum(f['trend'][k] == 0 for f in feat.values()) for k in ['D20','D50','W10','W20','H50']})
