# Quad MTF alignment backtest

Data: Databento MNQ 1s -> 30s bars, continuous back-adjusted front month, all hours for indicator calc.
Periods: 2021-11 to 2023-07 ("old") and 2025-02 to 2026-11 ("new"). Signals RTH 08:30-15:00 CT only.
Trade: overbought alignment -> short, oversold -> long, next 30s open, stop/target grid (15-60 / 15-100 pts),
max hold 120 min, one trade at a time, 10 MNQ, $0.74/side. Ties in a 30s bar count as stop. No slippage.
Lines: avg (white) or s1 (green); live (forming HTF bar) or conf (closed HTF bars); trigger at alignment onset or release.
Code: `research/agg30.py` -> `build_quad.py` -> `bt_align.py`.

## Findings (2026-11-16)
- 30S-15m and 1m-15m alignment: no reversal edge. Mean move after signal is ~0 in 2025-26 and against the
  fade in 2021-23 (-4 to -6 pts at 60-120 min). No stop/target combo has PF > 1.1 in both periods.
- All 6 timeframes (incl. 240m and 1D), Stoch 1, confirmed bars: the only setup positive in both periods
  (+12 / +7 pts mean at 60 min). Best combos PF 1.1-1.4, but only ~60-80 trades per period and picked from
  480 combos, so treat as weak.

## Trend pullback (2026-11-16) — `research/bt_pullback.py`
Higher TFs set direction (confirmed bars); fast-TF alignment in the opposite extreme is the entry
(uptrend + fast oversold -> long, downtrend + fast overbought -> short). 6 trend rules x 4 fast sets x
line/mode/trigger x stop/target grid = 3,840 combos.
- Baseline (enter every 10 min in trend direction, no pullback): PF 0.94-1.00. So the trend filter alone
  has no edge; the pullback adds it.
- Best trend rule: 240m avg and 1D avg both >= 50 (up) or both < 50 (down); 23% of its combos are
  profitable in both periods vs <= 8% for every other rule.
- Best setup: 240m+1D trend, 5m and 15m avg (white) both in the opposite extreme, confirmed bars, enter on
  alignment onset, stop 60 / target 15. With 1 tick slippage/side: 2021-23 n=169 PF 1.61 +$15.1k
  maxDD $2.4k; 2025-26 n=158 PF 1.40 +$10.5k maxDD $4.1k (10 MNQ, ~21 months each).
  Stop 60 / target 25: PF 1.25 / 1.36.
- Caveat: chosen from many combos; about 90 trades a year. Needs forward/paper testing.
