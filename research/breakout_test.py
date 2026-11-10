import sys, csv, bisect, json, itertools
from datetime import date, datetime
sys.path.insert(0, '.')
from fastsim import load_days, sim_day, sim_day_breakout
D = load_days(); F = json.load(open('../db/features.json'))
vix = {}
for r in csv.DictReader(open('../ext/vix.csv')): vix[datetime.strptime(r['DATE'], '%m/%d/%Y').date()] = float(r['CLOSE'])
vd = sorted(vix)
def vchg(d):
    i = bisect.bisect_left(vd, date.fromisoformat(d)); return vix[vd[i-1]] - vix[vd[i-2]]
DROP = [d for d in sorted(D) if vchg(d) < -0.9]
def st(x):
    eq = pk = dd = 0
    for t in x: eq += t * 5 - 14; pk = max(pk, eq); dd = max(dd, pk - eq)
    return round(eq), round(dd), len(x)
res = []
for mode, off, sl, rr, be, mt in itertools.product(["stop", "retest"], [0, 10, 20, 40, 80], [60, 100, 150, 200], [1, 1.5, 2, 3, 4], [False, True], [1, 2]):
    cfg = dict(trade_start=8*3600+1800, trade_end=11*3600, mode=mode, offset=off, sl=sl, tp=round(sl*rr), max_trades=mt,
               be_trig=sl if be else None, be_off=sl//2)
    y = {"2025": [], "2026": []}
    for d in DROP:
        hi, lo = F[d]["levels"]["PRE90"]
        y[d[:4]] += [t[4] for t in sim_day_breakout(D[d], hi, lo, cfg)]
    res.append(dict(mode=mode, off=off, sl=sl, rr=rr, be=be, mt=mt, y25=st(y["2025"]), y26=st(y["2026"]), all=st(y["2025"] + y["2026"])))
json.dump(res, open('breakout_grid.json', 'w'))
both = [r for r in res if r["y25"][0] > 0 and r["y26"][0] > 0]
print("VIX-drop days:", len(DROP), "(2025:", sum(d < '2026' for d in DROP), "2026:", sum(d >= '2026' for d in DROP), ")")
print("configs profitable in both years:", len(both), "of", len(res))
def row(r): return f"{r['mode']:6} off{r['off']:3} SL{r['sl']:3} RR{r['rr']:<3} BE{int(r['be'])} max{r['mt']} | 2025 ${r['y25'][0]:6} | 2026 ${r['y26'][0]:6} | all ${r['all'][0]:6} dd ${r['all'][1]:5} n{r['all'][2]}"
print("\nTop 15 by worst-year profit:")
for r in sorted(both, key=lambda r: -min(r['y25'][0], r['y26'][0]))[:15]: print(row(r))
# chosen on 2025 alone
print("\nBest 5 chosen on 2025 only -> 2026:")
for r in sorted(res, key=lambda r: -r['y25'][0])[:5]: print(row(r))
import statistics
from collections import defaultdict
for dim in ["mode", "off", "sl", "rr", "be", "mt"]:
    g = defaultdict(list)
    for r in res: g[r[dim]].append(r["all"][0])
    print(dim, {k: round(statistics.median(v)) for k, v in sorted(g.items(), key=lambda x: str(x[0]))})
