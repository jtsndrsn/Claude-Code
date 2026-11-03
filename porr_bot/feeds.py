"""Price feeds.

  CsvReplayFeed - replays 1-minute bars exported from TradingView (for testing the engine and
                  comparing it with the Pine strategy).
  WebullFeed    - live futures data from Webull OpenAPI. NOT FINISHED: Webull's docs list the
                  endpoints (GET /market-data/futures/snapshots/list and
                  /market-data/futures/bars/list) but not the SDK method names / parameters,
                  and futures data needs a paid OpenAPI market-data subscription. Fill in the two
                  methods once the subscription is active and the parameters are confirmed.
"""
from __future__ import annotations

import csv
from datetime import datetime
from zoneinfo import ZoneInfo

from engine import Bar


class CsvReplayFeed:
    """Reads a TradingView "Export chart data" CSV (1-minute chart).

    Needs columns `time, open, high, low, close`. `time` may be a unix timestamp (seconds) or an
    ISO date-time. Bars are converted to `tz`.
    """

    def __init__(self, path: str, tz: str = "America/Chicago"):
        self.path, self.tz = path, ZoneInfo(tz)

    def bars(self):
        with open(self.path, newline="") as fh:
            for row in csv.DictReader(fh):
                row = {k.strip().lower(): v for k, v in row.items()}
                t = row["time"].strip()
                if t.replace(".", "").isdigit():
                    ts = datetime.fromtimestamp(float(t), self.tz)
                else:
                    ts = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(self.tz)
                yield Bar(ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))


def bar_ticks(bar: Bar):
    """Same 4-price path TradingView's default backtester uses inside a bar."""
    if abs(bar.high - bar.open) <= abs(bar.open - bar.low):
        return [bar.open, bar.high, bar.low, bar.close]
    return [bar.open, bar.low, bar.high, bar.close]


class WebullFeed:
    """Live Webull futures data. TODO once the futures market-data subscription is active."""

    def __init__(self, api_client, symbol: str):
        self.api, self.symbol = api_client, symbol

    def last_price(self) -> float:
        # GET /market-data/futures/snapshots/list  (SDK method / params to be confirmed)
        raise NotImplementedError("Webull futures snapshot call not wired up yet")

    def closed_bars_since(self, after: datetime) -> list[Bar]:
        # GET /market-data/futures/bars/list  (1-minute bars; SDK method / params to be confirmed)
        raise NotImplementedError("Webull futures bars call not wired up yet")
