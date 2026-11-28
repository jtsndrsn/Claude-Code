# PORR project: conversation summary

Summary of the long working conversation that built, researched and deployed the PORR
(Pre-Open Range Reversal) MNQ futures strategy. No keys, passphrases or account IDs are recorded
here; those live only in Render environment variables and the session's credential store.

Unless stated otherwise, every P&L figure is a backtest at **10 MNQ**, **$0.74 per contract per
side** commission, no slippage, on Databento 1-second MNQ data:
- "2025-26" = Feb 2025 - Nov 6 2026 (457 days);
- "2021-23" = Nov 2021 - Jul 2023 (452 days);
- Aug 2023 - Jan 2025 is not in the data and is treated as no trading;
- "all 44 months" = both periods together.

Detailed tables live in `research/RESULTS.md`; this file is the narrative and the index.

---

## 1. What the strategy is (current: v3.4)

- **Range:** high/low of 07:00-08:30 CT.
- **Trade window:** 08:30-11:00 CT, flatten at 11:00.
- **Normal days: fade the lines.**
  - Sell limit at the range high + 10 ticks; buy limit at the range low - 10 ticks.
  - One trade per side.
  - SL 175 ticks. TP 500 (1000 when the trade is with the daily EMA50 trend).
  - Breakeven: at +100 the stop moves to +50.
- **VIX-drop days: trade breakouts instead.**
  - Applies when VIX closed more than 0.9 points lower than the day before.
  - Stop orders 10 ticks beyond each line, max 2 trades.
  - SL 300, TP 1200; breakeven at +200 moves the stop to +100.
- **Momentum filter:** skip the LONG fade when yesterday's daily MACD histogram (12/26/9) is above 0
  AND +DI is above -DI (DMI 14).
- **Limit-move guard (v3.3/3.4):** no trades on a day when either of these holds:
  - the range high/low is within 0.5% of CME's 7% overnight limit;
  - the move is 5%+ and the high/low was pinned flat into the open.
- **Backtest (v3.0 settings, all 44 months):**

  | Measure | Value |
  |---|---|
  | Trades | 1,105 |
  | Net | +$211,661 |
  | Max drawdown | $23,760 |
  | Win rate (breakeven counts as a win) | 68.1% |
  | 2021-23 | +$4.8k |
  | 2025-26 | +$206.9k |

  Exits:

  | Exit | Trades | P&L |
  |---|---|---|
  | TP | 65 | +$212.5k |
  | Breakeven stop | 595 | +$172.9k |
  | SL | 318 | -$333.6k |
  | 11:00 close | 127 | +$159.8k |

---

## 2. Live setup (no secrets)

- **Signal path:** TradingView Pine strategy (`strategies/porr.pine`) sends JSON alerts through a
  webhook to the bridge (`porr_bot/bridge.py`) on Render. The bridge places orders on a **Webull paper
  futures account**.
- **Render:**
  - Web Service, Starter plan, Ohio.
  - Root `porr_bot`; disk mounted at `/var/data`.
  - Health check `/`; live status page `/status`, optionally protected by a key.
  - Auto-deploy off; deploys from branch `main`.
  - Settings, env var names and emails: `porr_bot/DEPLOYMENT.md`.
- **The bridge:**
  - treats Webull fills as the source of truth and places TP/SL from the actual fill price;
  - moves the stop to breakeven when it receives the alert;
  - flattens at 11:00;
  - survives restarts via saved state;
  - sends heartbeat, warning and daily P&L emails.
- **Contract cap:** the bridge trades `min(alert qty, PORR_MAX_CONTRACTS)`. The user keeps it at
  **1 contract** on paper and multiplies results by 10 mentally.
- **Status:** still paper trading; not live.

### Operational issues hit and fixed
- **403 "bad passphrase":**
  - Cause: Render env var edits need **Save & Deploy**; Manual Deploy alone discards unsaved edits.
  - Fix: Save & Deploy, update the passphrase input in TradingView, re-create the alert.
  - Passphrases that appeared in screenshots were rotated.
- **400 / ACCOUNT_ACCESS_DENIED:**
  - Cause: the Webull paper Futures account ID had changed.
  - Fix: find the current ID with `wb_check.py` in the Render Shell and update the env var. The
    procedure is in DEPLOYMENT.md.
- **Alerts after 11:00 CT** return 200 but are ignored (trade window closed).
- **Only 1 contract traded although the alert said 10:** this is the `PORR_MAX_CONTRACTS` cap,
  working as intended.
- **Paper orders do appear in the Webull app.** An earlier note saying otherwise was corrected.
- **Copying the script from GitHub's "Files changed" diff view** pasted only fragments (Pine error at
  line 17). Use the raw file or the attached script.
- **TradingView alerts must be re-created after every script change** (they keep the old version),
  and the alert should run on a **1-minute chart**.

---

## 3. Version history and why

| Version | Change | Why |
|---|---|---|
| v1.1 | Defaults TP 400 / SL 400, entry delay 24, no breakeven | starting point |
| v1.2 | Range-size label, mid-range line, optional TP at the opposite line | visuals / option |
| v1.3 / 1.3.1 / 1.3.2 | Skip a line once broken; end-of-day close fixes; exits always as prices | stop fading pullbacks from outside the range; fix a bug where the trend TP was cut to the normal TP |
| v1.4 | Net P&L on exit marks | visuals |
| v2.0 | 07:00-08:30 range, SL 100 / TP 500, breakeven 100 -> 50, delay 10, trend TP 750 (daily EMA50), VIX switch to breakouts | 4,800 + 396-combo optimisation on 2025-26 1-second data; fading VIX-drop days lost money |
| v2.1 | Breakout SL 300 (was 200) | better in 2025 and 2026 |
| v2.2 | Webhook alerts to the Webull bridge | automation |
| v3.0 "balanced" | SL 175, trend TP 1000, breakout stops 10 ticks beyond the lines with TP 1200, long-only momentum filter | ~80,000-variation search; on 2025-26: +$206.9k / DD $3.9k / 72.4% vs v2.2 +$138.2k / $9.3k / 58% |
| v3.1 | Developing range lines in the last 5 minutes before 08:30; working-order lines and price tags | user wanted a visual reference before the open and to see orders |
| v3.2 | TradingView-style position box (target zone / stop zone, stop zone follows breakeven); Colors settings group; range lines more transparent | the v3.1 TP/SL plot drew a slanted line when breakeven moved the stop |
| v3.3 | Limit-move guard (skip when the range is within 0.5% of the 7% limit) | 2026-11-23: NQ locked at the 7% up-limit before the open; the range high was the limit and the short was run over at 08:30 |
| v3.4 | Guard also catches a range pinned at the limit (5%+ move and high/low held flat 10+ min) | on 2026-11-23 the chart's daily close (25,288.25) made the move look like +6.3%; CME's 15:00 settlement (~25,120) is the real reference |

All v3.x chart and guard changes leave backtest results unchanged: the guard never triggers in the
data.

### Pull requests (all merged into `main`)
1. **#1:** v2.2 strategy, bot, research and bridge.
2. **#2:** v3.0 and the status page.
3. **#3:** 2021-23 research and the paper account-ID note.
4. **#4:** open-timing research and deployment notes.
5. **#5:** `docs/HANDOFF.md` for new strategy work.
6. **#7:** v3.1 and v3.2 visuals.
7. **#8:** v3.3 and v3.4 limit-move guard.

---

## 4. Research run in this conversation (results and verdicts)

### 4.1 v3.0 search and growth plan (before the 2021-23 data)
- **v3 settings compared, 2025-26:**

  | Settings | Net | Max DD | Notes |
  |---|---|---|---|
  | v3 balanced | +$206.9k | $3.9k | |
  | v3 without the momentum filter | +$193.2k | $5.6k | |
  | v3 "max" (breakout SL 400, BE 100/40, delay 8) | +$222.8k | $7.5k | more drawdown, not adopted |

- **Out-of-sample check:** settings chosen on 2025 alone earned $79-90k in 2026, against $77.6k
  for v2.2.
- **Rejected:** trailing stops, partial TP, time stops, 1-minute RSI filter, time-of-day cutoff,
  re-entries, one side only, other trend sources, other VIX thresholds, most day filters (VIX level,
  gap, overnight range, ATR, daily RSI/ADX, day of week). The symmetric momentum filter on shorts
  also tested worse.
- **$5k growth plan:**
  - 2 MNQ, +2 MNQ per $1k profit up to 20 MNQ;
  - then 2 NQ, +1 NQ per $10k, max 5 NQ.
  - Result on 2025-26: v3 ends at about $903k (largest drawdown $19.3k); v2.2 at about $579k.
  - On all 44 months: the lowest balance dipped to $1,223, an ~80% drawdown, because 2021-23 is
    weak. Small early accounts are fragile.

### 4.2 2021-23 data added (Nov 2021 - Jul 2023)
- **v2.2 vs v3 on both periods:**

  | Version | 2021-23 | All 44 months | Max DD |
  |---|---|---|---|
  | v2.2 | +$5.5k | +$143.6k | |
  | v3 | +$4.8k (2022: -$11.8k) | +$211.7k | $23.8k |

- **Where v3's 2021-23 result came from:** fades lost (2022 bear market), while breakouts were
  positive in every year and both directions.
- **Fades by trend regime:**

  | Period | Downtrend | Uptrend |
  |---|---|---|
  | 2021-23 | -$13.5k (PF 0.81) | break-even |
  | 2025-26 | +$42.7k | +$107.7k |

- **40,000-variation search on 2021-23 only:**
  - Best there: VIX threshold 0.5, counter-trend-only fades, range 07:30-08:30 or 08:30-08:45,
    SL 300-400. These made about +$120k in 2021-23 but only $13-115k in 2025-26 (tuned to 2022).
    **Not adopted.**
  - VIX threshold sweep on v3 (all 44 months):

    | VIX threshold | Net | Max DD |
    |---|---|---|
    | 0.4 | +$214.9k | $15.9k |
    | 0.5 | +$213.7k | |
    | 0.7 | +$224.1k | $17.6k |
    | 0.9 (kept) | +$211.7k | $23.8k |

    Results jump between neighbouring values. **Option if NQ enters a long downtrend: 0.5-0.6.**
    The user chose not to let 2022 drive the settings.
- **Distance from the daily EMA50** (above / below / near, bands of 250-1500 ticks, approach side,
  "sticky" switching that requires N days to change zone): v3 was flat in every zone in 2022-23 and
  strong in every zone in 2025-26. Zone-switched settings lost to plain v3 out of sample.
  **Rejected.** TradingView continuous charts without back-adjustment shift the price-to-EMA distance
  by 70-100 points after rolls.
- **More trades per day** (repeat fades, max 2/3/4/6): +$160-174k vs +$211.7k. Breakout max 3-4
  changed nothing. **Rejected.**

### 4.3 Breakout targets and exit time
- **How breakouts end:** of 289 breakout trades, 46% exit at breakeven, 28% SL, 24% at the 11:00
  close, and only 2% at TP.
- **How far they run:** +1200 ticks was reached before 11:00 on only 7% of trades (11% in 2025-26).
- **The "breakeven, then reach TP" pattern** (the user's 2026-11-12 trade): 10 of 132 breakeven
  exits went on to reach the TP; 5 of those retested the line first.
- **TP and breakeven grid:**

  | Breakout settings | Net | Max DD |
  |---|---|---|
  | TP 800 | +$212.3k | $21.9k |
  | TP 1200 (kept) | +$211.7k | $23.8k |
  | TP 1600 | +$217.6k | |
  | Looser breakeven / no breakeven | helps 2021-23, costs 2025-26 $5-9k | |

  TP 800 is equivalent to 1200 and is hit far more often. **Offered as the default, not changed.**
- **Holding open trades past 11:00:**

  | Hold until | Net | Max DD |
  |---|---|---|
  | 12:00 | +$211.9k (TP 800) / +$204.8k (TP 1200) | |
  | 13:00 | +$205.7k / +$198.6k | +$2-9k higher |
  | TP / SL / 15:00 (1-minute bars) | 126 trades: +$158.9k -> +$137.6k (-$21k) | $24.0k -> $31.5k |

  **Keep the 11:00 flatten.**

### 4.4 London session range
- **Test:** London Stock Exchange hours (08:00-16:30 London) as the range, trading until
  15:30 CT, on 1-minute bars.
- **Result:** +$40.8k with v3 settings vs +$211.7k for PORR. Wider stops did not fix it;
  fades-only and breakouts-only were both about break-even.
- **Verdict: rejected.** The range is too wide, and the edge is specific to the 08:30 open.

### 4.5 Fast stop-outs (losses that never got near breakeven)
- **How many:** 193 of 1,105 trades (17%), costing -$199k. Median 266 s to the stop; most of the
  quickest filled in the first minute after 08:30.
- **News on the 16 quickest:**
  - Powell at Jackson Hole exactly at 09:00 CT (stopped out in 3 s);
  - hot CPI (2022-10-13);
  - tariff crash (2025-04-07);
  - hot PPI;
  - the day after FOMC;
  - the rest were ordinary open fills.
- **Skip rules tested** (fair value gaps into the line, fill in the first 2 minutes, big 1-minute
  candle, fast approach, 07:30 news shock, open in the top 20% of the range, VIX over 25): all helped
  2021-23 and hurt 2025-26.
- **Rules that helped both periods (both small):**
  - skip fades when VIX is over 30: +$5.5k;
  - skip breakouts triggered 1-6 minutes after the open: +$6.8k, likely noise.
- **No warning sign found:** FOMC days, 09:00 CT releases, prior-day high/low sweeps, daily RSI,
  trend direction.
- **Verdict: no filter adopted.** The conditions behind fast losses also produce the winners.

### 4.6 Open timing
- **Range line broken in 08:30-08:35:** fades filled on that opening break average $53 per trade
  (-$20.2k in 2021-23, +$41.6k in 2025-26). Days with no break in the first 5 minutes average $317.
- **Breakouts that also take out the overnight high/low at the open:** average $533, positive in
  both periods.
- **New range high/low in 08:25-08:30:** the same line breaks first 84-91% of the time, but the
  move continues only about 50% of the time. Fading into it was not worse.
- **The 15 minutes before the open** (trend, 1-minute RSI, RSI slope): direction is a coin flip
  (correlation -0.05). A strong pre-open move predicts a ~30% larger first-5-minute range, not its
  direction.
- **Verdict: no filter.** (The 08:15-08:30 study was not saved to RESULTS.md, at the user's choice.)

### 4.7 Breakeven trigger 175 instead of 100
- **Result:** +$184.2k (win 58%, DD $28.9k) vs +$211.7k (68%, $23.8k). Worse in both periods.
- **Verdict: keep 100 -> +50.**

### 4.8 3-minute vs 1-minute chart
- **Live behaviour:** the same, because orders and the breakeven alert act on every tick.
- **TradingView's backtest:** looks worse on 3-minute, because on historical bars the breakeven
  only moves after a bar closes.
- **Verdict:** keep the alert on a 1-minute chart; use 3-minute only for viewing.

### 4.9 Monthly re-optimisation (walk-forward)
- **Test:** each month, pick the best settings of the prior 1/3/6 months (from 16k combinations or
  9 v3 variants) and trade them for the month.
- **Result:** +$41k to +$166k vs +$211.7k for fixed v3, and inconsistent between methods.
- **Verdict: rejected.**

### 4.10 Trade spreadsheet and extending past the Databento data
- **Spreadsheet:** `PORR_v3_backtest_trades.xlsx` lists every trade (date, entry/exit time,
  Long/Short, result, P&L, cumulative balance, drawdown) with a summary tab. It was sent in chat and
  is not in the repo.
- **Nov 9-16 2026** were added from Webull 1-minute bars:
  - The 1-minute method matched 52 of 55 trade results against the 1-second data for Sep-Nov 2026.
  - Result: +$5,646, bringing the total to +$217,307.

### 4.11 Entry-break rules (from the user's 5-second chart observations)
All on 1-second data, v3 settings:

| Rule | Result | Verdict |
|---|---|---|
| Exit when a 5-second candle closes X ticks through the entry with no recapture within N s | -$66k to -$134k | rejected |
| Same trigger, but move TP to entry +3 ticks | -$45k to -$116k | rejected |
| Same trigger, then tighten the stop to -25/-50/-75/-100 on the retest of the entry | -$7.5k to -$96k | rejected |

- **Why they all fail:** fades fill while price is still pushing, so a break against the entry is
  normal on winners too.
- **Volume** (Databento 1-second volume): the surge right after entry is the same for winners and
  losers (about 2.9x). No usable signal.

### 4.12 Overnight 7% price limit (2026-11-23)
- **History:** in 860 mornings the largest overnight move was -6.0% (2025-04-07); the limit was
  never reached.
- **Action:** added the guard (v3.3, refined in v3.4).

### 4.13 Overnight gap vs the first trade
- **Setup:** gap = 08:30 open vs the prior 15:00 CT close; 780 first trades.
- **Gaps of 1-1.8%:** win rate 73-75% and SL 24-26%, against 67% / 32% for gaps under 1%. Both
  periods are positive.
- **Bigger gaps** turn would-be stop-outs into breakeven exits (BE 54% -> 60-66%), with fewer TPs.
- **Verdict: no filter needed.**
- **Win-rate convention:** breakeven exits count as wins (they lock +50 / +100 ticks); "SL" means
  full stops only.

### 4.14 More profit from breakeven trades
- **How far breakeven fades run before coming back:** median peak +144 ticks; 26% reach +200,
  12% reach +300.
- **Exits tested at TP 500/1000** (all lose overall; they help 2021-23 and drawdown):

  | Exit rule | Change vs v3 |
  |---|---|
  | Trail 50-300 ticks | -$6k to -$112k |
  | Step stop | -$44k to -$86k |
  | Stall exit (no new high for 1-10 min) | -$14k to -$77k |

- **Smaller fixed fade target:**

  | Fade TP / with-trend TP | Net | Max DD | 2021-23 |
  |---|---|---|---|
  | 150/300 to 300/600 | +$143k to +$188k | | |
  | **400/800** | **+$210.1k** (-$1.5k) | **$16.3k** (vs $23.8k) | **+$21.3k** (vs +$4.8k) |
  | 500/1000 (now) | +$211.7k | $23.8k | +$4.8k |

  400/800 costs about $18k in 2025-26.
- **Trailing and stall exits re-run at TP 400/800:** now worse in **both** periods (-$8k to -$116k).
  Plain breakeven is still the best exit.

### 4.15 Two-step entry confirmation (MACD / RSI)
- **Test:** after the line touch, wait for 1-minute MACD or RSI confirmation, then enter at market.
  Ranked by net / max drawdown.

  | Entry | Net / DD |
  |---|---|
  | v3 | 8.9 |
  | **v3 with fade TP 400/800** | **12.9** |
  | RSI >= 70-90 at the touch | 5.9-6.6 |
  | MACD histogram turn | 6.3 |
  | MACD on the signal side / crossing | 2.8-3.1 |
  | RSI hook | 5.2-5.8 |
  | RSI + MACD | 5.6-6.0 |

- **Why:** confirmation enters after the bounce has started, at a worse price, so the profit factor
  drops from 1.61 to 1.2-1.3. RSI of 80-90 at a touch almost never happens.
- **Verdict: rejected.** The best profit-to-drawdown change found is fade TP 400/800.

---

## 5. Decisions made
- **Settings:** keep v3 (v3.0 settings) unchanged: VIX threshold 0.9, 1 trade per side, breakeven
  100 -> 50, 11:00 flatten.
- **Breakout TP:** keep 1200 for now (800 is equivalent).
- **Account:** keep paper trading at 1 contract.
- **Don't let 2022 drive the settings;** no monthly re-optimisation.
- **Chart:** v3.1-v3.2 visuals and the v3.3-v3.4 limit-move guard are merged and in use.
- **Research notes:** all of the above are recorded in `research/RESULTS.md`, except the 08:15-08:30
  pre-open study, which the user declined to save.

- **2026-11-27, v3.5:** fade TP changed to 400 / with-trend TP 800 (from 500 / 1000), owner decision.

## 6. Ideas rejected (summary)
- **Exits:** trailing stops, step stops, stall exits, partial TP, time stops, holding past 11:00,
  breakeven trigger 175.
- **Entries:** early exits / TP +3 / tightened stop on 5-second breaks; MACD/RSI confirmation;
  re-entries or more trades per day.
- **Day filters:** news, gap, ATR, VIX level, day of week, fast approach, fair value gaps, opening
  break, pre-open trend/RSI.
- **Different setups:** zone-based settings by EMA50 distance, the London-session range, monthly
  re-optimisation, settings tuned only on 2021-23.

## 7. Open questions / pending
- **Fade TP 400/800 vs 500/1000:** same net, much smaller drawdown, better 2022. Awaiting the user's
  decision.
- **Breakout TP 800 vs 1200:** offered, not changed.
- **VIX threshold 0.5-0.6** if NQ stays in a prolonged downtrend: offered, not changed.
- **Optional "skip fades when VIX is over 30" setting:** offered (small, rarely triggers); not built.
- **Daily data capture:** offered a bridge job that saves each morning's Webull 1-minute bars (with
  volume) plus RSI/MACD/Stochastics next to the trades on the Render disk. Not built yet.
- **Chart defaults:** the user will supply preferred colors and transparency for the defaults.
- **Data:** the Databento 1-second data ends Nov 6 2026; later days need Webull 1-minute bars or a
  new (paid) Databento download, which needs the user's approval.

## 8. Planned next
- Decide on fade TP 400/800 and update the Pine default if chosen, followed by a PR, re-pasting the
  script and re-creating the alert.
- Keep forward-testing on paper; compare paper results (x10) with the backtest.
- A separate, new strategy will be explored in a new conversation starting from `docs/HANDOFF.md`.
