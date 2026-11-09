# PORR optimisation on Databento 1-second MNQ data (Feb 2025 - Nov 2026)

Data: Databento GLBX.MDP3 `ohlcv-1s`, MNQ front month by daily volume, 457 trading days.
Trend warm-up: Webull daily bars for 2024 contracts (back-adjusted continuous series).
Simulator: `fastsim.py`, verified trade-for-trade against `porr_bot/engine.py`
(710 trades / +$34,035 and 709 trades / +$39,689 on two different configs).
All figures: 10 MNQ contracts, $0.70/contract/side commission, no slippage unless stated.

## Method
1. Stage 1 - 4,800 combos: level source (PRE60 07:30-08:30, PRE30 08:00-08:30, PRE90 07:00-08:30,
   ON overnight 17:00-08:30, PD previous-day RTH) x SL (100-400) x R:R (1-5) x entry delay (0-40)
   x breakeven mode x skip-broken. Ranked on 2025 (in-sample), checked on 2026 (out-of-sample).
2. Stage 2 - 396 combos: the 12 most robust stage-1 configs x trend overlay (daily EMA20/50,
   weekly EMA10/20, hourly EMA50; "filter" = with-trend only, "boost" = 1.5x TP with trend)
   x trade-window end (11:00 / 12:00 / 13:00).

## Findings
- Only 940 of 4,800 stage-1 configs were profitable in both years: the edge is narrow.
- Level source: PRE90 (07:00-08:30) > PRE60 > ON (unstable: lost 2025, won 2026) > PRE30 > PD.
- Smaller stops (100-150 ticks) with large targets (R:R 3-5) and breakeven "+1R -> lock +0.5R" form
  a stable family that is profitable in both years across the whole neighbourhood.
- Trend FILTER (skip counter-trend trades) hurt every config tested (-$30k to -$40k median).
- Trend BOOST (1.5x TP on with-trend trades) helped; daily EMA50 best (33/36 configs improved).
- Ending the trade window at 11:00 was slightly better than 12:00/13:00.
- Clean out-of-sample check: the #1 stage-1 config chosen on 2025 alone
  (PRE90 SL150 RR5 d10 BE 1R->0.5R skip on) made +$42.1k in 2025 and +$24.8k in 2026.

## Candidates
| | 2025 | 2026 | Total | Max DD | PF | Win % | Trades | Total w/ 1-tick slippage |
|---|---|---|---|---|---|---|---|---|
| A balanced | +$35,873 | +$36,594 | +$72,467 | $8,670 | 1.47 | 53.6 | 657 | +$65,897 |
| B max profit | +$41,146 | +$46,588 | +$87,734 | $18,032 | 1.42 | 56.4 | 644 | +$81,294 |
| Current settings | +$17,615 | +$16,420 | +$34,035 | $16,643 | 1.11 | 56.6 | 710 | +$26,935 |

A: range 07:00-08:30, trade 08:30-11:00, SL 100, TP 500, BE trigger 100 -> stop +50, entry delay 10,
   one trade per level, skip-broken off, with-trend TP 750 on daily EMA50.
B: same but SL 150, TP 600, BE trigger 150 -> stop +75, with-trend TP 900.

Stage 2 used both years to pick among robust configs, so A/B carry some selection bias; forward-test
in paper before trading size.

## Losing-trade analysis (Setups A and B)
Every trade with market context at entry: `trades_setupA_with_context.csv`, `trades_setupB_with_context.csv`
(range size vs ATR, gap, overnight range, approach speed, 07:30 news shock, VIX level/change,
daily MACD/RSI/Stoch/%B/ADX/Williams %R, 5-min RSI/Stoch at entry, VWAP distance, day of week).
News events (Webull macro calendar) for the 34 worst and 35 best Setup-A days: `news_*_days_setupA.csv`.

- Losers are almost all full stops (302 of 305 for A); 35 days had two stops.
- Most features show no stable difference between winners and losers. Big news shocks, gaps,
  fast approaches and high volatility are, if anything, GOOD for this strategy (skipping them lost money).
- News: worst and best days have the same mix of scheduled events (best days had slightly more CPI/PMI);
  scheduled news did not predict losses.
- Consistent signals across both setups and both years:
  * Trades where daily momentum AGREES with the trade (daily MACD histogram / DI / RSI on the trade's side)
    earn much less per trade than trades against daily momentum (A: +$64/+$12 vs +$147/+$217 per trade).
    Skipping them lowers total profit but cuts drawdown; skipping only when MACD and DI BOTH agree keeps
    ~95% of profit with lower drawdown.
  * Skip the day if VIX fell more than ~0.9 points the previous day: A +$72.5k -> +$85.0k (dd $8.7k -> $8.4k),
    B +$87.7k -> +$101.8k (dd $18.0k -> $14.6k). Helped 2026 in both setups, neutral/positive in 2025.
- Pierce-and-reclaim entries (enter after price trades through the line and back) performed about the same
  as Setup A, not better.
- Fear & Greed index could not be included (CNN blocks automated access).

## Breakout mode on VIX-drop days (VIX closed >0.9 pts lower the previous day)
96 such days (56 in 2025, 40 in 2026). Every one broke at least one range line before 11:00;
46 broke only one side. Fading these days lost money (A -$14.5k, B -$16.9k).
800 breakout configs tested (`breakout_test.py`): buy stop at range high / sell stop at range low
("stop") or limit back at the line after a break ("retest"), offset 0-80, SL 60-200, R:R 1-4, BE on/off,
1-2 trades per day. 284 were profitable in both years; entering right AT the line with a stop order,
wider stops (150-200) and bigger targets (R:R 3-4) were best.

| Combined system (fade normal days, breakout on VIX-drop days) | 2025 | 2026 | Total | Max DD | Losing months |
|---|---|---|---|---|---|
| A, skip VIX-drop days | +$39,613 | +$47,312 | +$86,925 | $8,072 | 4/22 |
| A + breakout (stop @ line, SL 200 / TP 800, BE 200->100, max 2) | +$54,870 | +$75,370 | +$130,240 | $7,819 | 1/22 |
| A + breakout picked on 2025 only (stop @ line, SL 150 / TP 450, no BE) | +$58,981 | +$54,485 | +$113,466 | $7,432 | 3/22 |
| B, skip VIX-drop days | +$41,559 | +$63,056 | +$104,615 | $13,031 | 7/22 |
| B + breakout (stop @ line, SL 200 / TP 800, BE 200->100, max 2) | +$56,816 | +$91,114 | +$147,930 | $8,587 | 4/22 |
| B + breakout picked on 2025 only | +$60,927 | +$70,229 | +$131,156 | $11,096 | 3/22 |
