"""Full engine (porr_bot v2.0 defaults) vs fast simulator on the combined fade + VIX-breakout system."""
import sys, csv, bisect, json
from datetime import date, datetime, time
sys.path.insert(0, ".")
import bt_1s
from bt_1s import days, Mem, CT
from engine import Config
from broker import PaperBroker
from feeds import bar_ticks
from webull_bt import report
F = json.load(open("../db/features.json"))
vix = {}
for r in csv.DictReader(open("../ext/vix.csv")): vix[datetime.strptime(r["DATE"], "%m/%d/%Y").date()] = float(r["CLOSE"])
vd = sorted(vix)
def vchg(d):
    i = bisect.bisect_left(vd, date.fromisoformat(d)); return vix[vd[i-1]] - vix[vd[i-2]]
cfg = Config(trade_log="", contracts=10, max_contracts_cap=10, max_trades=10)   # all other settings = v2.0 defaults
b = PaperBroker(cfg.tick); e = Mem(cfg, b); e.out = []
for d, sym, bars in days():
    e.set_day_context(breakout=vchg(d) < -cfg.vix_drop, trend=F[d]["trend"]["D50"])
    for bar in bars:
        if (not e.range_done and not e.eod_done and e.day == bar.start.date() and e.range_high is not None
                and bar.start.time() >= cfg.range_end):
            e.range_done = True
        for i, px in enumerate(bar_ticks(bar)):
            b.on_price(bar.start, px, gap=(i == 0))
            for f in b.poll_fills(): e.on_fill(f)
            e.on_price(bar.start, px)
            for f in b.poll_fills(): e.on_fill(f)
        e.on_bar(bar)
    if bars:
        last = bars[-1]
        e.on_price(datetime.combine(last.start.date(), time(13, 0), CT), last.close)
        for f in b.poll_fills(): e.on_fill(f)
res, rows = report(e.out)
print("ENGINE trades", res["trades"], "net", round(res["net"]), "dd", round(res["max_dd"]))
