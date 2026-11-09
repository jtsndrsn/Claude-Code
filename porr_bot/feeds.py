"""Price feeds.

  CsvReplayFeed - replays 1-minute bars exported from TradingView (for testing the engine and
                  comparing it with the Pine strategy).
  WebullFeed    - live futures snapshot + 1-minute bars from Webull OpenAPI.
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
    """Live Webull futures data via the official SDK (DataClient.futures_market_data).

    Confirmed working on this account: real-time (delay_minutes 0) snapshot and 1-minute bars for
    MNQZ6, and the bars match the TradingView export to the tick.
    """

    MAX_BARS = 1200          # API limit per request

    def __init__(self, api_client, symbol: str, tz: str = "America/Chicago"):
        from webull.data.data_client import DataClient
        self.md = DataClient(api_client).futures_market_data
        self.symbol, self.tz = symbol, ZoneInfo(tz)

    def last_price(self) -> float:
        res = self.md.get_futures_snapshot(self.symbol, "US_FUTURES")
        if res.status_code != 200:
            raise RuntimeError(f"snapshot failed {res.status_code}: {res.text}")
        return float(res.json()[0]["price"])

    def closed_bars_since(self, after: datetime | None, count: int | None = None) -> list[Bar]:
        """Completed 1-minute bars with start >= `after`, oldest first."""
        now = datetime.now(self.tz)
        if count is None:
            mins = 5 if after is None else int((now - after).total_seconds() // 60) + 2
            count = max(2, min(self.MAX_BARS, mins))
        res = self.md.get_futures_history_bars(self.symbol, "US_FUTURES", "M1", count=str(count))
        if res.status_code != 200:
            raise RuntimeError(f"bars failed {res.status_code}: {res.text}")
        out = []
        for b in res.json()[0]["result"]:
            start = datetime.strptime(b["time"], "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(self.tz)
            bar = Bar(start, float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"]))
            if bar.end <= now and (after is None or start >= after):   # skip the bar still forming
                out.append(bar)
        out.sort(key=lambda x: x.start)
        return out


# ---------------------------------------------------------------------------------------------
# Daily context for the engine (live): VIX regime + daily EMA trend
VIX_CSV_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

def vix_change_before(day, url: str = VIX_CSV_URL) -> float | None:
    """VIX close of the last trading day before `day` minus the close of the day before that."""
    import urllib.request
    rows = []
    with urllib.request.urlopen(url, timeout=30) as resp:
        for line in resp.read().decode().splitlines()[1:]:
            d, _, _, _, c = line.split(",")
            m, dd, y = d.split("/")
            rows.append((f"{y}-{m}-{dd}", float(c)))
    prior = [c for d, c in rows if d < day.isoformat()]
    return prior[-1] - prior[-2] if len(prior) >= 2 else None


def daily_trend(md, symbol: str, day, length: int = 50) -> int:
    """+1 if the last daily close before `day` is above its EMA(length), -1 if below.
    `md` is DataClient(...).futures_market_data. Uses the contract's own daily history."""
    res = md.get_futures_history_bars(symbol, "US_FUTURES", "D", count=str(length * 4))
    if res.status_code != 200:
        raise RuntimeError(f"daily bars failed {res.status_code}: {res.text}")
    bars = sorted(res.json()[0]["result"], key=lambda b: b["time"])
    closes = [float(b["close"]) for b in bars if b["time"][:10] < day.isoformat()]
    if not closes: return 0
    a = 2 / (length + 1); e = closes[0]
    for c in closes[1:]: e = a * c + (1 - a) * e
    return 1 if closes[-1] > e else -1
