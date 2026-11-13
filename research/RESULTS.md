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

## Breakout stop-loss check (v2.1)
TP 800 / BE 200->100 kept, breakout SL varied (96 VIX-drop days; system = fade A on other days):
| Breakout SL | 2025 | 2026 | Breakout total | Win % | System total | Max DD |
|---|---|---|---|---|---|---|
| 200 | +$15,257 | +$28,058 | +$43,315 | 60% | +$130,240 | $7,819 |
| 250 | +$19,475 | +$27,058 | +$46,533 | 65% | +$133,458 | $9,990 |
| 300 (v2.1 default) | +$21,200 | +$30,558 | +$51,758 | 68% | +$138,683 | $9,240 |
Scaling the BE trigger with the stop (1R) was worse in every case; the fixed 200-tick BE trigger is what helps.

## v3.0 search (~80,000 variations)
Simulator `sys2.py` (fade + VIX-drop breakout system, new options, day/entry filters; reproduces v2.2 within $30 of the
bot engine), batch runner `g2.py`, account-growth model `grow.py`. 10 MNQ, $0.74/side commission.

| | Net | Max DD | Win % | PF | 2025 | 2026 | Losing months |
|---|---|---|---|---|---|---|---|
| v2.2 | +$138,161 | $9,268 | 58.0 | 1.79 | +$60,547 | +$77,614 | 2/22 |
| v3.0 balanced | +$206,890 | $3,948 | 72.4 | 2.32 | +$106,803 | +$100,087 | 1/22 |
| v3.0 without the momentum filter | +$193,234 | $5,572 | 70.6 | 2.05 | +$93,366 | +$99,869 | 1/22 |

v3.0: SL 175 (BE still 100 -> +50), with-trend TP 1000, breakout stops 10 ticks beyond the lines with TP 1200,
skip LONG fades when the prior day's MACD histogram > 0 and +DI > -DI (the same rule for shorts: +$175k, worse).
- Stop loss is the main lever: 120-200 all beat 100 (a 100-tick stop stopped trades out before breakeven).
- Rejected (all lowered profit): trailing stops, partial take-profits, time stops, 1-min RSI entry filter,
  time-of-day cutoff, re-entries, one side only, other trend sources, VIX thresholds other than 0.9,
  and day filters on VIX level, gap, overnight range, ATR, daily RSI/ADX, day of week.
- Out-of-sample: settings chosen on 2025 alone earned $79k-90k in 2026 (v2.2: $77.6k) with lower drawdown.
  The momentum filter was found on both years and only helped 2025: the least proven part.
- Growth plan ($5k, 2 MNQ +2 per $1k profit to 20 MNQ, then 2 NQ +1 per $10k to 5 NQ, NQ $2.00/side):
  v3.0 ends at ~$903k (largest drawdown $19.3k), v2.2 at ~$579k ($44.5k).

## 2021-23 data (Nov 2021 - Jul 2023, 452 days) - added Nov 2026
Databento 1-second MNQ for Nov 2021 - Jul 2023; the Aug 2023 - Dec 2024 gap is treated as no trading.
`sys2.py` loads both periods (`PORR_ONLY=old|new` restricts to one). 10 MNQ, $0.74/side.

| | 2021-23 | 2025-26 | All 44 months | Max DD |
|---|---|---|---|---|
| v2.2 | +$5,465 | +$138,161 | +$143,626 | |
| v3.0 balanced (kept) | +$4,771 (2022: -$11.8k) | +$206,890 | +$211,661 | $23,760 |

- v3 in 2021-23: fades lost (2022 bear market), VIX-drop breakouts made money in every year and both directions.
- 40,000-variation search on 2021-23 only: best there was VIX threshold 0.5 (more breakout days), counter-trend-only
  fades, range 7:30-8:30 or 8:30-8:45, SL 300-400 (~+$120k in 2021-23). Those settings earned only $13k-115k in
  2025-26 (some negative) - tuned to 2022. Not adopted.
- v3 VIX threshold sweep (all 44 months): 0.4 +$214.9k DD $15.9k; 0.5 +$213.7k; 0.7 +$224.1k DD $17.6k;
  0.9 (kept) +$211.7k DD $23.8k. Lower thresholds help 2021-23 a lot, cost 2025-26 some, and results jump between
  neighbouring values. Option to revisit if NQ enters a long downtrend: 0.5-0.6.
- Daily EMA50 distance zones (above/below/near, bands 250-1500 ticks, approach side, sticky N-day switching;
  `g3.py` per-day P&L + `reg*.py`): v3 was flat in every zone in 2022-23 and strong in every zone in 2025-26, so
  distance from the EMA does not explain the bad period. Zone-switched settings chosen on one period lost to plain v3
  on the other. Not adopted. Note: TradingView continuous charts without back-adjustment (B-ADJ) shift the
  price-to-EMA distance by ~70-100 pts for weeks after each roll.
- More trades per day (repeat fades allowed, max 2/3/4/6): +$160k-174k vs +$211.7k; breakout max 3-4 changes nothing.
- Decision: keep v3.0 balanced unchanged; don't let 2022 drive the settings.

## Breakout targets and exit time (Nov 2026)
289 v3 breakout trades on 208 VIX-drop days (`bo_reach.py`). Exits: BE +100 46%, SL 28%, 11:00 close 24%, TP 2%.
- Price reached +1200 ticks from entry before 11:00 on 7% of trades (2025-26: 11%, 2021-23: 3%); before the
  300-tick stop level on 5%. Favorable move reached: 200 ticks 70%, 400 45%, 600 30%, 800 20%, 1000 10%.
- After a BE stop, price came back to the line on 100/132 trades but went on to the original TP on only 10 (5 after
  a retest, like 2026-11-12).
- Breakout TP/BE grid (all 44 months): TP 800 +$212.3k DD $21.9k vs TP 1200 +$211.7k DD $23.8k (equivalent);
  TP 1600 +$217.6k; looser/no BE mainly helps 2021-23 and costs 2025-26 $5-9k. Kept TP 1200 / BE 200->100 for now.
- Holding open trades past 11:00 (no new entries; `xe` option in `sys2.py`): to 12:00 +$211.9k (TP 800) /
  +$204.8k (TP 1200); to 13:00 +$205.7k / +$198.6k with DD up $2-9k. Kept the 11:00 flatten. Data ends 13:00.

## Fast stop-outs study (Nov 2026)
`ff_build.py` writes every v3 trade with pre-entry context (`ff_trades.csv`); `ff_an*.py`, `ff_rules.py` analyse it.
Fast fail = stopped out without ever reaching half the BE trigger (fades 50 ticks, breakouts 100).
- 193 of 1,105 trades (17%), -$199k; 149 fades, 44 breakouts; median 266 s to the stop, 25% within 108 s.
  Most of the quickest filled in the first minute after the 08:30 open.
- News on the 16 quickest (Webull calendar): Powell Jackson Hole at 09:00 CT (2025-08-22, stopped in 3 s), hot CPI
  (2022-10-13), tariff crash VIX 45 (2025-04-07), hot PPI (2026-06-11), day after FOMC (2026-03-19); the rest were
  ordinary open fills (ISM/ADP/PCE days or no news).
- Skip-rule tests (change in net, 2021-23 / 2025-26): 3+ FVGs into the line +$14.5k / -$27.2k; fill in first 2 min
  +$19.4k / -$51.2k; 1m bar >150 ticks in last 15 min +$10.8k / -$86.0k; run >260 ticks into the line +$8.4k / -$38.2k;
  07:30 news shock >3x +$17.5k / -$54.2k; open in top 20% of range +$15.8k / -$34.7k; VIX >25 +$9.6k / -$5.7k.
  Only two helped both periods, both small: skip fades when VIX >30 (+$1.8k / +$3.7k, 71 trades) and skip breakouts
  triggering 1-6 min after the open (+$4.2k / +$2.7k, likely noise).
- No warning sign: FOMC days (0 fast fails, profitable), fills at the 09:00 CT releases (net positive), prior-day
  high/low sweeps, open vs prior-day range, daily RSI, trend direction.
- Conclusion: the conditions behind fast losses (open burst, displacement, news shocks) also produce the winners;
  no filter adopted. Candidate if ever needed: skip fades when VIX >30.
