import os, tempfile, unittest
from datetime import datetime, time
from zoneinfo import ZoneInfo
from broker import PaperBroker
from bridge import Bridge

CT = ZoneInfo("America/Chicago")
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=CT)

class FakeClockBridge(Bridge):
    clock = T0
    def now(self): return self.clock

def mk(**kw):
    log = os.path.join(tempfile.mkdtemp(), "t.csv")
    b = FakeClockBridge(PaperBroker(0.25), "pw", max_qty=10, trade_log=log, **kw)
    return b, log

def px(b, p):
    b.broker.on_price(b.clock, p, gap=False); b.tick_loop_once()

PLACE_LONG = dict(pass_="pw")
def place(b, tag="Long", side="BUY", typ="LIMIT", price=1000, mid="1", **kw):
    m = {"pass": "pw", "id": mid, "action": "place", "tag": tag, "side": side, "type": typ, "price": price,
         "qty": 10, "tp": 20, "sl": 20, "be_trig": 8, "be_off": 4, "use_be": True}
    m.update(kw); return b.handle(m)

class BridgeTest(unittest.TestCase):
    def test_passphrase_and_duplicates(self):
        b, _ = mk()
        self.assertEqual(b.handle({"pass": "bad", "action": "flatten"}), "forbidden")
        self.assertEqual(place(b), "placed")
        self.assertEqual(place(b), "duplicate")
        self.assertEqual(place(b, mid="2"), "unchanged")
        self.assertEqual(place(b, mid="3", price=999), "placed")      # moved

    def test_fill_places_tp_sl_from_actual_fill_and_cancels_other_side(self):
        b, log = mk()
        place(b); place(b, tag="Short", side="SELL", price=1010, mid="2")
        b.broker.on_price(b.clock, 1003, gap=False)
        px(b, 999.75)                                   # long limit 1000 fills (1 tick through)
        self.assertEqual(b.pos.tag, "Long"); self.assertNotIn("Short", b.working)
        px(b, 1005.25)                                  # TP 20 ticks = 1005
        self.assertIsNone(b.pos)
        row = open(log).read().splitlines()[1].split(",")
        self.assertEqual((row[2], row[7], float(row[6])), ("Long", "TP", 1005.0))

    def test_breakeven_and_stop_out(self):
        b, log = mk()
        place(b); b.broker.on_price(b.clock, 1003, gap=False); px(b, 999.75)
        self.assertEqual(b.handle({"pass": "pw", "id": "be", "action": "breakeven", "tag": "Long"}), "moved")
        self.assertEqual(b.pos.sl_price, 1001.0)                      # entry 1000 + 4 ticks
        px(b, 1002); px(b, 1000.75)
        self.assertIsNone(b.pos)
        self.assertIn("SL", open(log).read())

    def test_no_new_entries_while_in_position_and_eod_flatten(self):
        b, log = mk()
        place(b); b.broker.on_price(b.clock, 1003, gap=False); px(b, 999.75)
        self.assertEqual(place(b, tag="Short", side="SELL", price=1010, mid="9"), "ignored: in a position")
        b.clock = T0.replace(hour=11, minute=0)
        px(b, 1001); px(b, 1001)
        self.assertIsNone(b.pos)
        self.assertIn("EOD", open(log).read())

    def test_breakout_stop_entry(self):
        b, _ = mk()
        place(b, tag="BO Long", typ="STOP", price=1010, tp=40, sl=60)
        b.broker.on_price(b.clock, 1005, gap=False); px(b, 1010.25)
        self.assertEqual((b.pos.tag, b.pos.entry), ("BO Long", 1010))

    def test_qty_cap(self):
        b, _ = mk(); b.max_qty = 1
        place(b); self.assertEqual(b.working["Long"][1]["qty"], 1)

if __name__ == "__main__":
    unittest.main()
