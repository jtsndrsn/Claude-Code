@echo off
REM PORR bot - paper trading (live Webull prices, simulated fills, no orders sent).
REM Schedule this with Windows Task Scheduler for 06:25 CT on weekdays.
cd /d %~dp0
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
python run.py live --config config.toml >> logs\paper_%TODAY%.log 2>&1
