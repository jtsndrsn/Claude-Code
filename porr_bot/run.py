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
from datetime import datetime, time
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

    real = WebullBroker(key, secret, wb["account_id"], cfg.symbol, sandbox=sandbox)
    broker = PaperBroker(cfg.tick) if paper else real
    feed = WebullFeed(real.trade, cfg.symbol)
    eng = Engine(cfg, broker)
    zone = ZoneInfo(tz)
    poll = float(wb.get("poll_seconds", 1.0))
    last_bar = datetime.now(zone).replace(second=0, microsecond=0)
    stop_file = os.path.join(HERE, "STOP")

    while True:
        if os.path.exists(stop_file):
            log.warning("STOP file found: cancelling and flattening")
            eng._cancel_entries()
            if eng.pos:
                eng._flatten("EOD")
            break
        now = datetime.now(zone)
        for bar in feed.closed_bars_since(last_bar):
            eng.on_bar(bar)
            last_bar = bar.end
        px = feed.last_price()
        if paper:
            broker.on_price(now, px)
        for f in broker.poll_fills():
            eng.on_fill(f)
        eng.on_price(now, px)
        for f in broker.poll_fills():
            eng.on_fill(f)
        _time.sleep(poll)


def main() -> None:
    ap = argparse.ArgumentParser(description="PORR v1.0 bot")
    ap.add_argument("mode", choices=["replay", "live"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--csv", help="TradingView 1-minute export for replay")
    ap.add_argument("--tz", default="America/Chicago")
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
    else:
        live(cfg, raw, a.tz)


if __name__ == "__main__":
    main()
