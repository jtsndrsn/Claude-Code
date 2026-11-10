#!/usr/bin/env bash
# PORR bot - paper trading (live Webull prices, simulated fills, no orders sent).
# cron example (server clock in CT):  25 6 * * 1-5  /path/to/porr_bot/start_paper.sh
cd "$(dirname "$0")"
mkdir -p logs
python3 run.py live --config config.toml >> "logs/paper_$(date +%F).log" 2>&1
