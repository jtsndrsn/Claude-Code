"""Backtest PORR on Webull 1-minute bars saved by the fetch agents."""
import sys, json, glob, logging, csv
from collections import defaultdict, Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, "/home/user/Claude-Code/porr_bot")
from engine import Config, Engine, Bar
from broker import PaperBroker
from feeds import bar_ticks
logging.disable(logging.CRITICAL)
CT = ZoneInfo("America/Chicago")
WB = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/wb"

def load():
    """Read every saved file and place bars by their OWN timestamp and symbol, so a file that was
    mapped to the wrong day by the fetch agents can't put bars on the wrong date."""
    want = {}
    for line in open(WB + "/calls.txt"):
        d, sym, _, _ = line.strip().split("|")
        want[d] = sym
    paths = set()
    for part in sorted(glob.glob(WB + "/files_part*.txt")):
        for line in open(part):
            line = line.strip()
            if line and not line.split("|", 2)[2].startswith("ERROR"):
                paths.add(line.split("|", 2)[2])
    got = defaultdict(dict)   # (sym, date) -> {ts: Bar}
    for path in paths:
        for blk in json.loads(open(path).read()):
            for b in blk["result"]:
                ts = datetime.strptime(b["time"], "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(CT)
                if time(7, 0) <= ts.time() < time(13, 0):
                    got[(blk["symbol"], ts.date().isoformat())][ts] = Bar(ts, float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"]))
    days = {}
    for d, sym in want.items():
        bars = got.get((sym, d), {})
        days[d] = (sym, [bars[k] for k in sorted(bars)])
    return days

class Mem(Engine):
    def _log_trade(self, p, f, pnl):
        self.out.append(dict(day=p.entry_ts.date().isoformat(), entry_ts=p.entry_ts, exit_ts=f.ts, tag=p.tag, dir=p.dir,
                             qty=p.qty, entry=p.entry, exit=f.price, kind=f.tag, ticks=pnl, be=p.be_done))

def run(days, **kw):
    cfg = Config(trade_log="", **kw)
    b = PaperBroker(cfg.tick); e = Mem(cfg, b); e.out = []
    for d in sorted(days):
        sym, bars = days[d]
        for bar in bars:
            for i, px in enumerate(bar_ticks(bar)):
                b.on_price(bar.start, px, gap=(i == 0))
                for f in b.poll_fills(): e.on_fill(f)
                e.on_price(bar.start, px)
                for f in b.poll_fills(): e.on_fill(f)
            e.on_bar(bar)
        if bars:  # end of trade window: flatten at the last bar's close (13:00 CT)
            last = bars[-1]
            t_end = datetime.combine(last.start.date(), cfg.trade_end, CT)
            e.on_price(t_end, last.close)
            for f in b.poll_fills(): e.on_fill(f)
    return e.out

def report(tr, comm_side=0.70, pv=2.0, tick=0.25):
    rows = []
    for t in tr:
        net = t["ticks"] * tick * pv * t["qty"] - 2 * comm_side * t["qty"]
        rows.append({**t, "net": net})
    eq = peak = dd = 0.0; curve = []
    for r in rows:
        eq += r["net"]; peak = max(peak, eq); dd = max(dd, peak - eq); curve.append(eq)
    wins = [r for r in rows if r["net"] > 0]; losses = [r for r in rows if r["net"] <= 0]
    gw = sum(r["net"] for r in wins); gl = -sum(r["net"] for r in losses)
    out = dict(trades=len(rows), win_pct=100 * len(wins) / max(1, len(rows)), net=eq, max_dd=dd,
               pf=gw / gl if gl else float("inf"), avg_win=gw / max(1, len(wins)), avg_loss=-gl / max(1, len(losses)),
               comm=sum(2 * comm_side * r["qty"] for r in rows),
               exits=Counter(("BE-stop" if (r["kind"] == "SL" and r["be"]) else r["kind"]) for r in rows),
               longs=(sum(1 for r in wins if r["dir"] > 0), sum(1 for r in rows if r["dir"] > 0)),
               shorts=(sum(1 for r in wins if r["dir"] < 0), sum(1 for r in rows if r["dir"] < 0)))
    months = defaultdict(lambda: [0, 0.0])
    for r in rows:
        m = r["day"][:7]; months[m][0] += 1; months[m][1] += r["net"]
    byday = defaultdict(float)
    for r in rows: byday[r["day"]] += r["net"]
    out["months"] = dict(sorted(months.items()))
    out["best_day"] = max(byday.items(), key=lambda x: x[1]) if byday else None
    out["worst_day"] = min(byday.items(), key=lambda x: x[1]) if byday else None
    out["green_days"] = (sum(1 for v in byday.values() if v > 0), len(byday))
    return out, rows

if __name__ == "__main__":
    days = load()
    have = [d for d in days if days[d][1]]
    print("days loaded:", len(days), "with bars:", len(have), min(have), "->", max(have))
    short = [d for d in sorted(days) if len(days[d][1]) < 330]
    print("days with <330 bars (07:00-13:00):", [(d, len(days[d][1])) for d in short])
    USER = dict(trade_end=time(13, 0), tp_ticks=200, sl_ticks=200, use_be=True, be_trigger=175, be_offset=100,
                use_line_tp=False, use_trend_tp=False, use_flip=False, contracts=10, max_contracts_cap=10,
                max_trades=10, one_per_level=True, skip_broken=False, allow_long=True, allow_short=True, entry_delay=20)
    res, rows = report(run(days, **USER))
    for k, v in res.items(): print(f"{k}: {v}")
    with open(WB + "/../bt/trades_user.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["entry_time", "exit_time", "side", "qty", "entry", "exit", "exit_type", "ticks", "net_usd"])
        for r in rows:
            w.writerow([r["entry_ts"], r["exit_ts"], "Long" if r["dir"] > 0 else "Short", r["qty"], r["entry"], r["exit"],
                        "BE-stop" if (r["kind"] == "SL" and r["be"]) else r["kind"], round(r["ticks"], 2), round(r["net"], 2)])
