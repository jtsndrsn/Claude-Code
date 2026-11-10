import os, tempfile, unittest
from datetime import date
from report import summarize, build_message, load_trades

ROWS = """entry_time,exit_time,tag,dir,qty,entry,exit,exit_type,pnl_ticks
2026-11-02 08:35:00-06:00,2026-11-02 09:10:00-06:00,Long,1,10,100,101,TP,500
2026-11-04 08:40:00-06:00,2026-11-04 08:55:00-06:00,Short,-1,10,100,101,SL,-100
2026-11-06 08:31:00-06:00,2026-11-06 09:40:00-06:00,BO Long,1,10,100,101,TP,800
2026-11-06 09:50:00-06:00,2026-11-06 10:20:00-06:00,BO Short,-1,10,100,101,SL,-300
2026-10-30 08:31:00-05:00,2026-10-30 09:40:00-05:00,Long,1,10,100,101,TP,200
"""

class ReportTest(unittest.TestCase):
    def test_day_week_month(self):
        p = os.path.join(tempfile.mkdtemp(), "t.csv"); open(p, "w").write(ROWS)
        s = summarize(load_trades(p), date(2026, 11, 6))
        # per trade: ticks * $0.50 * 10 - $14.80 commission (Webull $0.74 per side)
        self.assertAlmostEqual(s["today"], (800 * 5 - 14.8) + (-300 * 5 - 14.8))     # 2472
        self.assertAlmostEqual(s["week"], s["today"] + (500 * 5 - 14.8) + (-100 * 5 - 14.8))
        self.assertEqual(s["week_n"], 4)
        self.assertEqual(s["month_n"], 4)                                            # Oct 30 excluded
        subj, body = build_message(s, date(2026, 11, 6), "paper", "BREAKOUT (VIX drop)")
        self.assertIn("today +$2,470.40", subj)
        self.assertIn("BO Long", body)

    def test_no_trades(self):
        s = summarize([], date(2026, 11, 6))
        self.assertIn("No trades today.", build_message(s, date(2026, 11, 6), "paper")[1])

if __name__ == "__main__":
    unittest.main()
