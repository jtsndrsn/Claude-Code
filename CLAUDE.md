# Project notes for Claude

PORR (Pre-Open Range Reversal) MNQ futures strategy: TradingView Pine script plus a Python bot and webhook bridge.

- Live setup (Render URL, settings, env var names, TradingView alert, emails): see `porr_bot/DEPLOYMENT.md`
- Bot usage: `porr_bot/README.md`; research and backtest results: `research/RESULTS.md`
- Strategy: `strategies/porr.pine` (v3.0)
- Tests: `cd porr_bot && python -m unittest`
- Never put secrets in the repo or ask for them in chat; they live in Render environment variables.
- User preference: keep explanations brief.
