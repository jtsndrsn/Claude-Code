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
