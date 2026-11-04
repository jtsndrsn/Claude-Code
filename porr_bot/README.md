# PORR bot (Pre-Open Range Reversal v1.2)

Runs the TradingView strategy `strategies/porr.pine` (v1.2) automatically on Webull futures.

## Status

| Part | Status |
|---|---|
| Strategy engine (range, entries, TP/SL, breakeven, trend TP, flip, end-of-day close, max trades) | Done, unit-tested |
| Replay backtest from TradingView CSV export | Done |
| Paper broker (simulated fills) | Done |
| Webull live futures prices / 1-min bars | Done. Real-time MNQZ6 data confirmed on the account; bars match TradingView exactly |
| Webull orders (place / replace stop / cancel) | Uses SDK calls confirmed to exist; **not yet run against Webull** |
| Webull fill detection | Push events + order-detail polling; response field names **must be checked in the sandbox** |

**Do not trade real money with this yet.** Order of rollout: replay → sandbox → paper (live prices, simulated fills) → live with 1 contract.

## How it trades

Webull's API does **not** support bracket/OCO orders for futures, so the bot manages them itself:
entry limits at both lines; when one fills it cancels the other, places a TP limit and an SL stop,
moves the stop to breakeven, and cancels the remaining leg when one exits. At 15:00 CT it cancels
everything and closes at market.

## Setup

```bash
pip install -r requirements.txt
cp config.example.toml config.toml   # then edit
python -m unittest -v                # engine tests
```

### Replay on TradingView data
On a **1-minute** MNQ chart: Export chart data → CSV. Then:

```bash
python run.py replay --config config.toml --csv MNQ_1m.csv
```

Trades go to `trades.csv`. Compare with the Strategy Tester's List of Trades.

### Live (after the Webull pieces are finished)
1. Apply for Webull OpenAPI access and create an App Key / Secret (Webull website → OpenAPI Management).
2. Set `WEBULL_APP_KEY` and `WEBULL_APP_SECRET` environment variables.
3. Put your `account_id` in `config.toml`. Keep `sandbox = true` and `paper = true` to start.
4. `python run.py live --config config.toml`

### Emergency stop
Create a file named `STOP` in this folder. The bot cancels its orders, closes any position at market and exits.

## Where it can run
OneDrive only stores files; it can't run programs. Options: a Windows PC that's on during market
hours (Task Scheduler), or a small always-on cloud VM (e.g. Azure B1s). You can keep `config.toml` and
`trades.csv` in a OneDrive folder so you can see them from anywhere.
