# PORR live setup (reference)

Secrets (API keys, passphrase, Gmail App Password) are stored ONLY in Render's environment variables,
never in this repo or in chat.

## Overview
TradingView (PORR v2.2 strategy alerts) -> webhook -> bridge on Render -> Webull PAPER account (MNQ futures).
No PC or Claude session needs to be running.

## Render (bridge host)
- URL / webhook: https://claude-code-pl6a.onrender.com/   (GET shows {"ok": true, "position": ..., "working": [...]})
- Service type: Web Service, plan Starter ($7/mo, 0.5 CPU / 512 MB), region Ohio
- Repo `jtsndrsn/Claude-Code`, branch `claude/eager-archimedes-jz42ll` (switch to `main` once PR #1 is merged)
- Root Directory `porr_bot`; Build `pip install -r requirements.txt`;
  Start `python bridge.py --config config.render.toml`
- Disk: mount `/var/data`, 1 GB (trades.csv + bridge_state.json)
- Health Check Path `/`; Pre-Deploy Command empty
- Auto-Deploy OFF: after a code update, use Manual Deploy outside 08:30-11:00 CT
- Environment variables:
  - PYTHON_VERSION=3.12.7, DATA_DIR=/var/data, WEBULL_SANDBOX=true
  - WEBULL_PAPER_ACCOUNT_ID=ERJU7AQIVIN376DVI2L8E1OUBA
  - PORR_SYMBOL=MNQZ6 (roll each quarter: H/M/U/Z), PORR_MAX_CONTRACTS=1
  - secrets: WEBULL_PAPER_APP_KEY, WEBULL_PAPER_APP_SECRET, BRIDGE_PASSPHRASE
  - email: EMAIL_TO, EMAIL_FROM (the user's Gmail), SMTP_PASSWORD (Gmail App Password, 16 letters, no spaces)
    created at https://myaccount.google.com/apppasswords

## TradingView
- Chart: MNQ, 1-minute timeframe (not 1 second)
- Script: strategies/porr.pine v2.2. Inputs "Webhook bridge": Send order alerts ON, passphrase = BRIDGE_PASSPHRASE
- Properties: On realtime bar tick ON
- One alert: Condition PORR, "alert() function calls only", Webhook URL above, open-ended
- Re-create the alert after any script or input change

## Daily emails (weekdays, CT)
- 08:20 "up and waiting"; 08:40 warning if no alerts since 08:00
- 11:00 flatten; after 11:05 daily P&L (today / week / month)
- Also: "stop re-placed after restart", "UNTRACKED POSITION", "CHECK POSITION"

## Webull
- OpenAPI: paper key works only on sandbox (api.sandbox.webull.com); live market-data needs the
  $228/mo CME OpenAPI subscription (not bought; the bridge does not need it)
- Account allows 1 websocket connection; bridge polls order status every 2.5 s (paper limit 30/min)
- Fees $0.74 per contract per side

## Going live later
Set WEBULL_SANDBOX=false, add WEBULL_APP_KEY / WEBULL_APP_SECRET / WEBULL_ACCOUNT_ID in Render,
start with PORR_MAX_CONTRACTS=1.
