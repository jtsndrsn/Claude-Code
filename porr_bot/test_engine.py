"""Scenario tests for the PORR engine using the paper broker.  Run: python -m unittest -v"""
import csv
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from broker import PaperBroker
from engine import Bar, Config, Engine
from feeds import bar_ticks

CT = ZoneInfo("America/Chicago")
DAY = datetime(2026, 11, 2, tzinfo=CT)


def range_bars():
    """07:30-08:29 bars: range high 1010, low 1000."""
    bars = []
    t = DAY.replace(hour=7, minute=30)
    for i in range(60):
        hi = 1010 if i == 10 else 1006
        lo = 1000 if i == 40 else 1004
        bars.append(Bar(t + timedelta(minutes=i), 1005, hi, lo, 1005))
    return bars


def trade_bars(path, start=(8, 30)):
    """path: list of (o, h, l, c) starting at `start`."""
    t = DAY.replace(hour=start[0], minute=start[1])
    return [Bar(t + timedelta(minutes=i), *ohlc) for i, ohlc in enumerate(path)]


def flat_until(hour, minute, price=1005, start=(8, 30)):
    t0 = DAY.replace(hour=start[0], minute=start[1])
    n = int((DAY.replace(hour=hour, minute=minute) - t0).total_seconds() // 60)
    return [(price, price, price, price)] * n


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.log = os.path.join(tempfile.mkdtemp(), "trades.csv")

    def run_bars(self, cfg, bars):
        broker = PaperBroker(cfg.tick)
        eng = Engine(cfg, broker)
        for bar in bars:
            for i, px in enumerate(bar_ticks(bar)):
                broker.on_price(bar.start, px, gap=(i == 0))
                for f in broker.poll_fills():
                    eng.on_fill(f)
                eng.on_price(bar.start, px)
                for f in broker.poll_fills():
                    eng.on_fill(f)
            eng.on_bar(bar)
        return eng

    def trades(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as fh:
            return list(csv.DictReader(fh))

    def cfg(self, **kw):
        base = dict(tp_ticks=20, sl_ticks=20, use_be=False, contracts=1, max_contracts_cap=1, entry_delay=0,
                    trend_minutes=15, trade_log=self.log)
        base.update(kw)
        return Config(**base)

    def test_range_is_built(self):
        eng = self.run_bars(self.cfg(), range_bars())
        self.assertTrue(eng.range_done)
        self.assertEqual((eng.range_high, eng.range_low), (1010, 1000))

    def test_long_touch_hits_tp(self):
        path = [(1003, 1003, 999.5, 1001), (1001, 1006, 1001, 1006)]
        self.run_bars(self.cfg(), range_bars() + trade_bars(path))
        t = self.trades()
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["tag"], t[0]["exit_type"], float(t[0]["entry"]), float(t[0]["exit"])),
                         ("Long", "TP", 1000.0, 1005.0))

    def test_bare_touch_does_not_fill(self):
        # Touches 1000 exactly but never trades through it -> no fill (fill-through rule).
        path = [(1003, 1003, 1000, 1002)] * 3
        self.run_bars(self.cfg(), range_bars() + trade_bars(path))
        self.assertEqual(self.trades(), [])

    def test_short_touch_hits_sl(self):
        path = [(1008, 1010.5, 1008, 1010), (1010, 1016, 1010, 1015)]
        self.run_bars(self.cfg(), range_bars() + trade_bars(path))
        t = self.trades()
        self.assertEqual((t[0]["tag"], t[0]["exit_type"]), ("Short", "SL"))
        self.assertLessEqual(float(t[0]["pnl_ticks"]), -20)

    def test_stop_then_flip_short_on_retest(self):
        path = [
            (1003, 1003, 999.5, 999.5),   # long fills @1000
            (999.5, 999.5, 994, 994),     # stopped (SL 995)
            (994, 996, 994, 996),         # flip short rests @1000
            (996, 1000.5, 996, 1000),     # retest fills flip short @1000
            (1000, 1000, 994.5, 995),     # flip TP 20 ticks -> 995
        ]
        self.run_bars(self.cfg(use_flip=True, flip_tp=20, flip_sl=20), range_bars() + trade_bars(path))
        t = self.trades()
        self.assertEqual([(x["tag"], x["exit_type"]) for x in t], [("Long", "SL"), ("Flip Short", "TP")])
        self.assertEqual(float(t[1]["entry"]), 1000.0)

    def test_no_flip_when_disabled(self):
        path = [(1003, 1003, 999.5, 999.5), (999.5, 999.5, 994, 994), (994, 1001, 994, 1000)]
        self.run_bars(self.cfg(), range_bars() + trade_bars(path))
        self.assertEqual([x["tag"] for x in self.trades()], ["Long"])

    def test_breakeven_moves_stop(self):
        path = [
            (1003, 1003, 999.5, 1001),    # long @1000
            (1001, 1005, 1001, 1004),     # +20 ticks -> BE trigger
            (1004, 1004, 999, 999),       # back down: stopped at BE (entry + 3 ticks)
        ]
        eng = self.run_bars(self.cfg(tp_ticks=80, use_be=True, be_trigger=20, be_offset=3),
                            range_bars() + trade_bars(path))
        t = self.trades()
        self.assertEqual(t[0]["exit_type"], "SL")
        self.assertIsNone(eng.pos)
        self.assertNotIn("Flip Short", eng.flip_armed)   # BE stop never arms a flip

    def test_eod_flatten(self):
        path = [(1003, 1003, 999.5, 1001)] + flat_until(15, 1, 1002, start=(8, 31))
        eng = self.run_bars(self.cfg(tp_ticks=80), range_bars() + trade_bars(path))
        t = self.trades()
        self.assertEqual(t[0]["exit_type"], "EOD")
        self.assertIsNone(eng.pos)
        self.assertFalse(eng.range_done)

    def test_one_trade_per_level_and_max_trades(self):
        path = [
            (1003, 1003, 999.5, 1001), (1001, 1006, 1001, 1006),   # long TP
            (1003, 1003, 999.5, 1001), (1001, 1006, 1001, 1006),   # low touched again: no 2nd long
        ]
        self.run_bars(self.cfg(), range_bars() + trade_bars(path))
        self.assertEqual(len(self.trades()), 1)

    def test_trend_tp_on_with_trend_long(self):
        # Steady uptrend before the range -> 15m closes above EMA -> long uses the trend TP.
        t0 = DAY.replace(hour=4, minute=0)
        warm = [Bar(t0 + timedelta(minutes=i), 900 + i * 0.25, 900 + i * 0.25, 900 + i * 0.25, 900 + i * 0.25)
                for i in range(210)]   # 04:00-07:29, rising
        path = [(1003, 1003, 999.5, 1001), (1001, 1011, 1001, 1011)]
        eng = self.run_bars(self.cfg(tp_ticks=20, use_trend_tp=True, tp_trend_ticks=40, trend_len=5),
                            warm + range_bars() + trade_bars(path))
        self.assertTrue(eng.trend_close is not None)
        t = self.trades()
        self.assertEqual((t[0]["exit_type"], float(t[0]["exit"])), ("TP", 1010.0))

    def test_contract_cap(self):
        eng = Engine(Config(contracts=10, max_contracts_cap=2, trade_log=""), PaperBroker())
        self.assertEqual(eng.qty, 2)


if __name__ == "__main__":
    unittest.main()
