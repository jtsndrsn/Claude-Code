"""Backtest PORR on Databento 1-second bars (front-month MNQ by daily volume, 07:00-13:00 CT)."""
import sys, csv, logging
from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, "/home/user/Claude-Code/porr_bot")
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from engine import Config, Bar
from broker import PaperBroker
from feeds import bar_ticks
from webull_bt import Mem, report
logging.disable(logging.CRITICAL)
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
SEC = timedelta(seconds=1)
SRC = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/db/mnq_1s_rth.csv"

def days():
    """Yield (date, symbol, [Bar]) per day, front month = highest volume that day."""
    cur, rows = None, defaultdict(list)
    def flush():
        vol = {s: sum(r[5] for r in v) for s, v in rows.items()}
        sym = max(vol, key=vol.get)
        bars = [Bar(datetime.fromisoformat(r[0]).replace(tzinfo=UTC).astimezone(CT), r[1], r[2], r[3], r[4], SEC)
                for r in sorted(rows[sym])]
        return cur, sym, bars
    with open(SRC) as fh:
        fh.readline()
        for line in fh:
            d, sym, ts, o, h, l, c, v = line.rstrip("\n").split(",")
            if d != cur:
                if cur is not None: yield flush()
                cur, rows = d, defaultdict(list)
            rows[sym].append((ts, float(o), float(h), float(l), float(c), int(v)))
    if cur is not None: yield flush()

def run(**kw):
    cfg = Config(trade_log="", **kw)
    b = PaperBroker(cfg.tick); e = Mem(cfg, b); e.out = []
    syms = {}
    for d, sym, bars in days():
        syms[d] = sym
        for bar in bars:
            # 1-second bars only exist when something traded: close the range on the first bar
            # at/after the range end even if no trade printed in the very last second.
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
            e.on_price(datetime.combine(last.start.date(), cfg.trade_end, CT), last.close)
            for f in b.poll_fills(): e.on_fill(f)
    return e.out, syms

USER = dict(trade_end=time(13, 0), tp_ticks=200, sl_ticks=200, use_be=True, be_trigger=175, be_offset=100,
            use_line_tp=False, use_trend_tp=False, use_flip=False, contracts=10, max_contracts_cap=10,
            max_trades=10, one_per_level=True, skip_broken=False, allow_long=True, allow_short=True, entry_delay=20)

if __name__ == "__main__":
    tr, syms = run(**USER)
    res, rows = report(tr)
    print("days:", len(syms), min(syms), "->", max(syms))
    rolls = []; prev = None
    for d in sorted(syms):
        if syms[d] != prev: rolls.append((d, syms[d])); prev = syms[d]
    print("front-month switches:", rolls)
    for k, v in res.items(): print(f"{k}: {v}")
    out = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt/trades_1s_user.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["entry_time", "exit_time", "side", "qty", "entry", "exit", "exit_type", "ticks", "net_usd"])
        for r in rows:
            w.writerow([r["entry_ts"], r["exit_ts"], "Long" if r["dir"] > 0 else "Short", r["qty"], r["entry"], r["exit"],
                        "BE-stop" if (r["kind"] == "SL" and r["be"]) else r["kind"], round(r["ticks"], 2), round(r["net"], 2)])
    print("trades file:", out)
