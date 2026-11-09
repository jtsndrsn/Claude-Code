"""PORR bot runner.

  python run.py replay --csv MNQ_1m.csv            # backtest on exported TradingView bars
  python run.py live   --config config.toml        # live (Webull) - see README before using

Safety: live mode trades the SANDBOX unless config says `sandbox = false`, and creating a file
named STOP next to this script cancels orders, flattens and exits.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time as _time
import tomllib
from dataclasses import fields
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from broker import PaperBroker
from engine import Config, Engine
from feeds import CsvReplayFeed, bar_ticks

log = logging.getLogger("porr")
HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path: str | None) -> tuple[Config, dict]:
    raw = {}
    if path:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    strat = raw.get("strategy", {})
    kwargs = {}
    for f in fields(Config):
        if f.name in strat:
            v = strat[f.name]
            if isinstance(f.default, time):
                v = time.fromisoformat(v)
            kwargs[f.name] = v
    return Config(**kwargs), raw


def replay(cfg: Config, csv_path: str, tz: str) -> Engine:
    broker = PaperBroker(cfg.tick)
    eng = Engine(cfg, broker)
    for bar in CsvReplayFeed(csv_path, tz).bars():
        for i, px in enumerate(bar_ticks(bar)):
            broker.on_price(bar.start, px, gap=(i == 0))
            for f in broker.poll_fills():
                eng.on_fill(f)
            eng.on_price(bar.start, px)
            for f in broker.poll_fills():          # market orders sent during on_price
                eng.on_fill(f)
        eng.on_bar(bar)
    return eng


def live(cfg: Config, raw: dict, tz: str) -> None:
    from broker import WebullBroker
    from feeds import WebullFeed

    wb = raw.get("webull", {})
    key, secret = os.environ.get("WEBULL_APP_KEY"), os.environ.get("WEBULL_APP_SECRET")
    if not key or not secret:
        sys.exit("Set WEBULL_APP_KEY and WEBULL_APP_SECRET environment variables.")
    sandbox = wb.get("sandbox", True)
    paper = wb.get("paper", True)
    log.warning("LIVE MODE  sandbox=%s  paper_fills=%s  symbol=%s", sandbox, paper, cfg.symbol)

    if paper:
        # Paper trading: LIVE Webull prices (production market data), simulated fills, no orders sent,
        # no trading connection at all.
        from webull.core.client import ApiClient
        api = ApiClient(key, secret, "us"); api.add_endpoint("us", "api.webull.com")
        broker = PaperBroker(cfg.tick)
        feed = WebullFeed(api, cfg.symbol, tz)
    else:
        real = WebullBroker(key, secret, wb["account_id"], cfg.symbol, sandbox=sandbox)
        broker = real
        feed = WebullFeed(real.api_client, cfg.symbol, tz)
    eng = Engine(cfg, broker)
    poll = float(wb.get("poll_seconds", 2.0))
    stop_file = os.path.join(HERE, "STOP")

    # Warm up: last ~20 hours of 1-minute bars rebuild today's range and the trend EMA.
    # NOTE: trades already taken today (before a restart) are not known to the engine.
    warm = feed.closed_bars_since(None, count=WebullFeed.MAX_BARS)
    for bar in warm:
        eng.on_bar(bar)
    next_bar = warm[-1].end if warm else datetime.now(ZoneInfo(tz)).replace(second=0, microsecond=0)
    log.info("Warm-up: %d bars, range_done=%s high=%s low=%s", len(warm), eng.range_done,
             eng.range_high, eng.range_low)

    ctx_day = None
    while True:
        today = datetime.now(ZoneInfo(tz)).date()
        if ctx_day != today and datetime.now(ZoneInfo(tz)).time() >= time(6, 30):
            # once a day before the range ends: VIX regime (breakout day?) and daily EMA trend
            try:
                from feeds import vix_change_before, daily_trend
                chg = vix_change_before(today)
                trend = daily_trend(feed.md, cfg.symbol, today, cfg.trend_len)
                eng.set_day_context(breakout=chg is not None and chg < -cfg.vix_drop, trend=trend)
                log.info("Day context %s: VIX change %s -> %s day, daily trend %+d", today, chg,
                         "BREAKOUT" if eng.breakout_day else "fade", trend)
                ctx_day = today
            except Exception:
                log.exception("could not load day context (VIX / trend); retrying")
        # One session per run: once the trade window is over and we're flat, stop (a scheduler
        # starts the bot again the next morning).
        now_ct = datetime.now(ZoneInfo(tz))
        if wb.get("exit_after_session", True) and eng.eod_done and eng.pos is None and \
                now_ct.time() >= (datetime.combine(now_ct.date(), cfg.trade_end) + timedelta(minutes=5)).time():
            log.warning("Trade window over and flat: exiting for today")
            from report import daily_report
            daily_report(cfg.trade_log, raw.get("email", {}), now_ct.date(),
                         "paper" if paper else ("sandbox" if sandbox else "LIVE"),
                         regime="BREAKOUT (VIX drop)" if eng.breakout_day else "fade")
            break
        if os.path.exists(stop_file):
            log.warning("STOP file found: cancelling and flattening")
            eng._cancel_entries()
            if eng.pos:
                eng._flatten("EOD")
            break
        try:
            now = datetime.now(ZoneInfo(tz))
            if now >= next_bar + timedelta(minutes=1, seconds=2):   # a new bar has closed
                for bar in feed.closed_bars_since(next_bar):
                    eng.on_bar(bar)
                    next_bar = bar.end
            px = feed.last_price()
            if paper:
                broker.on_price(now, px)
            for f in broker.poll_fills():
                eng.on_fill(f)
            eng.on_price(now, px)
            for f in broker.poll_fills():
                eng.on_fill(f)
        except Exception:
            log.exception("loop error (will retry)")
        _time.sleep(poll)


def main() -> None:
    ap = argparse.ArgumentParser(description="PORR v2.0 bot")
    ap.add_argument("mode", choices=["replay", "live", "report"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--csv", help="TradingView 1-minute export for replay")
    ap.add_argument("--tz", default="America/Chicago")
    ap.add_argument("--date", help="report: day to report (default today)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg, raw = load_config(a.config)
    if a.mode == "replay":
        if not a.csv:
            sys.exit("--csv is required for replay")
        replay(cfg, a.csv, a.tz)
        print(f"Done. Trades written to {cfg.trade_log}")
    elif a.mode == "report":
        from report import daily_report
        day = date.fromisoformat(a.date) if a.date else datetime.now(ZoneInfo(a.tz)).date()
        print(daily_report(cfg.trade_log, raw.get("email", {}), day, "report"))
    else:
        live(cfg, raw, a.tz)


if __name__ == "__main__":
    main()
