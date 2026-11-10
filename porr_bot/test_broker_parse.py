import json, unittest
from broker import WebullBroker

def fake():
    b = WebullBroker.__new__(WebullBroker)       # skip the network setup
    b.tags, b.sides, b.qtys, b._done = {"c1": "Long"}, {"c1": "BUY"}, {"c1": 10}, set()
    return b

class ParseTest(unittest.TestCase):
    def test_order_detail_filled(self):
        d = {"client_order_id": "c1", "combo_type": "NORMAL",
             "orders": [{"client_order_id": "c1", "status": "FILLED", "filled_quantity": "10", "filled_price": "27012.25"}]}
        f = fake()._parse_event(d)
        self.assertEqual((f.tag, f.side, f.qty, f.price), ("Long", "BUY", 10, 27012.25))

    def test_order_detail_not_filled(self):
        d = {"client_order_id": "c1", "orders": [{"status": "SUBMITTED", "filled_quantity": "0", "filled_price": "0"}]}
        self.assertIsNone(fake()._parse_event(d))

    def test_event_payload_json_string(self):
        ev = json.dumps({"client_order_id": "c1", "order_status": "FILLED", "scene_type": "FINAL_FILLED",
                         "filled_qty": "10", "filled_price": "27000.5"})
        self.assertEqual(fake()._parse_event(ev).price, 27000.5)

    def test_partial_fill_event_ignored(self):
        ev = {"client_order_id": "c1", "order_status": "SUBMITTED", "scene_type": "FILLED", "filled_qty": "3", "filled_price": "1"}
        self.assertIsNone(fake()._parse_event(ev))

if __name__ == "__main__":
    unittest.main()
