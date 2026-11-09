import sys, time, csv
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from fastsim import load_days, range_levels, sim_day
t = time.time(); D = load_days(); print("load", round(time.time() - t, 1), "s")
cfg = dict(trade_start=8*3600+1800, trade_end=13*3600, delay=20, sl=200, tp=200, be_trig=175, be_off=100,
           max_trades=10, one_per_level=True, skip_broken=False)
t = time.time(); trades = []
for d in sorted(D):
    lv = range_levels(D[d], 7*3600+1800, 8*3600+1800)
    if lv: trades += [(d,) + x for x in sim_day(D[d], lv[0], lv[1], cfg)]
print("sim", round(time.time() - t, 2), "s")
net = sum(x[5] * 0.5 * 10 - 14 for x in trades)
print("trades", len(trades), "net", round(net), "wins", sum(x[5]*5-14 > 0 for x in trades))
ref = list(csv.DictReader(open("/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt/trades_1s_user.csv")))
print("engine trades", len(ref), "net", round(sum(float(r['net_usd']) for r in ref)))
# per-day diff
from collections import defaultdict
a = defaultdict(float); b = defaultdict(float)
for x in trades: a[x[0]] += x[5]
for r in ref: b[r['entry_time'][:10]] += float(r['ticks'])
diff = [(d, a[d], b[d]) for d in sorted(set(a) | set(b)) if abs(a[d] - b[d]) > 0.01]
print("days differing:", len(diff), diff[:10])
