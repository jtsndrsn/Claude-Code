"""PORR v2.0 strategy engine (broker-agnostic).

Mirrors strategies/porr.pine v2.0:
  * Range = high/low of the 1-minute bars inside the range window (default 07:30-08:30 CT).
  * From the trade-window open, rest a BUY limit at range low (- entry delay) and a SELL limit
    at range high (+ entry delay). First fill cancels the other (manual OCA).
  * On fill: TP limit + SL stop as two separate orders (Webull futures has no OCO/bracket
    support, so this engine cancels the other leg itself).
  * Breakeven: once price runs `be_trigger` ticks in favour, the stop is moved to entry + offset.
  * Optional with-trend TP (EMA on N-minute closes) and optional flip after a FULL stop-out.
  * End of trade window: cancel everything and flatten at market.

The engine never talks to a broker API directly. It calls a Broker object (see broker.py),
and is driven by three inputs: on_bar() for each closed 1-minute bar, on_price() for each
price update, and on_fill() for each fill reported by the broker.
"""
from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

log = logging.getLogger("porr.engine")

ENTRY_TAGS = ("Long", "Short", "Flip Long", "Flip Short", "BO Long", "BO Short")


@dataclass
class Bar:
    start: datetime          # bar open time, timezone-aware (exchange/strategy time zone)
    open: float
    high: float
    low: float
    close: float
    length: timedelta = timedelta(minutes=1)   # bar duration (1-second data: timedelta(seconds=1))

    @property
    def end(self) -> datetime:
        return self.start + self.length


@dataclass
class Fill:
    order_id: str
    tag: str                 # "Long" / "Short" / "Flip Long" / "Flip Short" / "TP" / "SL" / "EOD" / "EXTRA"
    side: str                # "BUY" / "SELL"
    qty: int
    price: float
    ts: datetime


@dataclass
class Config:
    symbol: str = "MNQZ6"
    tick: float = 0.25
    range_start: time = time(7, 0)
    range_end: time = time(8, 30)
    trade_start: time = time(8, 30)
    trade_end: time = time(11, 0)
    flat_at_end: bool = True
    tp_ticks: int = 500
    sl_ticks: int = 100
    use_be: bool = True
    use_line_tp: bool = False        # TP at the opposite range line (overrides tp/trend TP; not flips)
    be_trigger: int = 100
    be_offset: int = 50
    use_trend_tp: bool = True
    tp_trend_ticks: int = 750
    trend_minutes: int = 1440       # used only when no external daily trend is given
    trend_len: int = 50
    use_flip: bool = False
    flip_tp: int = 100
    flip_sl: int = 100
    contracts: int = 10
    max_trades: int = 4
    one_per_level: bool = True
    skip_broken: bool = False        # skip a line for the day once price trades through it unfilled
    allow_long: bool = True
    allow_short: bool = True
    entry_delay: int = 10
    # Safety: hard cap on contracts per order, regardless of `contracts`.
    # VIX regime: after VIX closes > vix_drop points lower, trade BREAKOUTS of the range instead
    use_vix_switch: bool = True
    vix_drop: float = 0.9
    bo_tp: int = 800
    bo_sl: int = 300
    bo_use_be: bool = True
    bo_be_trigger: int = 200
    bo_be_offset: int = 100
    bo_max_trades: int = 2
    max_contracts_cap: int = 1
    trade_log: str = "trades.csv"


@dataclass
class Position:
    tag: str
    dir: int                 # +1 long, -1 short
    qty: int
    entry: float
    tp_ticks: int
    sl_ticks: int
    best: float
    tp_id: str | None = None
    sl_id: str | None = None
    sl_price: float = 0.0
    be_done: bool = False
    entry_ts: datetime | None = None
    use_be: bool = False
    be_trigger: int = 0
    be_offset: int = 0


class Engine:
    def __init__(self, cfg: Config, broker):
        self.cfg = cfg
        self.broker = broker
        self.qty = min(cfg.contracts, cfg.max_contracts_cap)
        if self.qty < cfg.contracts:
            log.warning("contracts=%s capped to max_contracts_cap=%s", cfg.contracts, self.qty)
        # day state
        self.day = None
        self.range_high: float | None = None
        self.range_low: float | None = None
        self.range_done = False
        self.trades_today = 0
        self.used: set[str] = set()
        self.flip_armed: set[str] = set()
        self.broken: set[str] = set()                 # "Long"/"Short" lines price broke through
        self.eod_done = False
        # orders / position
        self.working: dict[str, str] = {}          # entry tag -> order id
        self.pos: Position | None = None
        self.last_price: float | None = None
        # trend (EMA of N-minute closes)
        self._tf_bucket = None
        self._tf_close: float | None = None
        self.ema: float | None = None
        self.trend_close: float | None = None       # last CLOSED trend-timeframe close
        self.trend_ema: float | None = None         # EMA as of that close

    # ------------------------------------------------------------------ helpers
    def _t(self, ts: datetime) -> time:
        return ts.time()

    def in_range(self, ts: datetime) -> bool:
        return self.cfg.range_start <= self._t(ts) < self.cfg.range_end

    def in_trade(self, ts: datetime) -> bool:
        return self.cfg.trade_start <= self._t(ts) < self.cfg.trade_end

    def set_day_context(self, breakout: bool | None = None, trend: int | None = None) -> None:
        """Daily inputs computed outside the engine: breakout = VIX-drop day (from the VIX close
        series), trend = +1/-1 from the daily EMA. Call before the range is final each day."""
        self.breakout_day = bool(breakout) and self.cfg.use_vix_switch
        self.ext_trend = trend

    @property
    def trend_up(self) -> bool:
        if getattr(self, "ext_trend", None) is not None: return self.ext_trend > 0
        return self.trend_ema is not None and self.trend_close > self.trend_ema

    @property
    def trend_dn(self) -> bool:
        if getattr(self, "ext_trend", None) is not None: return self.ext_trend < 0
        return self.trend_ema is not None and self.trend_close < self.trend_ema

    # ------------------------------------------------------------------ bars
    def on_bar(self, bar: Bar) -> None:
        """Call once per CLOSED 1-minute bar, in time order."""
        self._update_trend(bar)
        if self.in_range(bar.start):
            if self.day != bar.start.date():
                self._reset_day(bar.start.date())
                self.range_high, self.range_low = bar.high, bar.low
            else:
                self.range_high = max(self.range_high, bar.high)
                self.range_low = min(self.range_low, bar.low)
            if self._t(bar.end) >= self.cfg.range_end or bar.end.date() != bar.start.date():
                self.range_done = True
                log.info("Range final %s: high=%s low=%s", self.day, self.range_high, self.range_low)

    def _update_trend(self, bar: Bar) -> None:
        n = self.cfg.trend_minutes
        midnight = bar.start.replace(hour=0, minute=0, second=0, microsecond=0)
        bucket = (bar.start.date(), int((bar.start - midnight).total_seconds() // 60) // n)
        if self._tf_bucket is not None and bucket != self._tf_bucket:
            self._close_trend_bar(self._tf_close)
        self._tf_bucket = bucket
        self._tf_close = bar.close
        # bar that ends exactly on the boundary closes the bucket now
        end_min = int((bar.end - midnight).total_seconds() // 60)
        if end_min % n == 0:
            self._close_trend_bar(bar.close)
            self._tf_bucket = None

    def _close_trend_bar(self, close: float | None) -> None:
        if close is None:
            return
        a = 2.0 / (self.cfg.trend_len + 1)
        self.ema = close if self.ema is None else a * close + (1 - a) * self.ema
        self.trend_close, self.trend_ema = close, self.ema

    def _reset_day(self, day) -> None:
        log.info("New day %s", day)
        self.day = day
        self.range_high = self.range_low = None
        self.range_done = False
        self.trades_today = 0
        self.used.clear()
        self.flip_armed.clear()
        self.broken.clear()
        self.eod_done = False

    # ------------------------------------------------------------------ prices
    def on_price(self, ts: datetime, price: float) -> None:
        """Call on every price update (tick or snapshot poll)."""
        self.last_price = price
        if self.pos:
            self._manage_position(price)

        if self.in_trade(ts):
            self._manage_entries(price)
        elif self.range_done and not self.eod_done and self._t(ts) >= self.cfg.trade_end:
            self._end_of_day()

    def _manage_entries(self, price: float) -> None:
        c, tick = self.cfg, self.cfg.tick
        if self.range_done and self.range_high is not None:
            # A line is broken once price trades 1 tick through its entry level while we are not in a
            # trade from that side (incl. after our own stop-out there) and no order of ours is
            # resting there that could be mid-fill.
            short_now = self.pos is not None and self.pos.dir < 0
            long_now = self.pos is not None and self.pos.dir > 0
            if price >= self.range_high + c.entry_delay * tick + tick and not short_now \
                    and "Short" not in self.working:
                self.broken.add("Short")
            if price <= self.range_low - c.entry_delay * tick - tick and not long_now \
                    and "Long" not in self.working:
                self.broken.add("Long")
        can = (self.range_done and self.pos is None and self.trades_today < c.max_trades
               and self.range_high is not None)
        if not can:
            self._cancel_entries()
            return
        if getattr(self, "breakout_day", False):
            self._manage_breakout(price)
            return
        long_lvl = self.range_low - c.entry_delay * tick
        short_lvl = self.range_high + c.entry_delay * tick
        wanted = {
            "Long": (c.allow_long and not (c.one_per_level and "Long" in self.used)
                     and not (c.skip_broken and "Long" in self.broken), "BUY", long_lvl,
                     price > long_lvl),
            "Short": (c.allow_short and not (c.one_per_level and "Short" in self.used)
                      and not (c.skip_broken and "Short" in self.broken), "SELL", short_lvl,
                      price < short_lvl),
            "Flip Short": (c.use_flip and "Flip Short" in self.flip_armed and "Flip Short" not in self.used,
                           "SELL", self.range_low, price < self.range_low),
            "Flip Long": (c.use_flip and "Flip Long" in self.flip_armed and "Flip Long" not in self.used,
                          "BUY", self.range_high, price > self.range_high),
        }
        for tag, (allowed, side, lvl, right_side) in wanted.items():
            if not allowed:
                self._cancel_entry(tag)
            elif tag not in self.working and right_side:
                # Only place when price is on the correct side of the level, so it fills on a
                # touch instead of instantly at market. Once working, it stays until filled.
                self.working[tag] = self.broker.place_limit(tag, side, self.qty, self._round(lvl))
                log.info("Resting %s %s %s @ %s", tag, side, self.qty, lvl)

    def _manage_breakout(self, price: float) -> None:
        """VIX-drop day: buy stop at the range high, sell stop at the range low, one trade per side,
        placed only while price is still inside the range."""
        c = self.cfg
        if self.trades_today >= c.bo_max_trades:
            self._cancel_entries()
            return
        for tag, side, lvl, inside, allow in (("BO Long", "BUY", self.range_high, price < self.range_high, c.allow_long),
                                              ("BO Short", "SELL", self.range_low, price > self.range_low, c.allow_short)):
            if not allow or tag in self.used:
                self._cancel_entry(tag)
            elif tag not in self.working and inside:
                self.working[tag] = self.broker.place_stop(tag, side, self.qty, self._round(lvl))
                log.info("Breakout stop %s %s %s @ %s", tag, side, self.qty, lvl)

    def _cancel_entry(self, tag: str) -> None:
        oid = self.working.pop(tag, None)
        if oid:
            self.broker.cancel(oid)

    def _cancel_entries(self) -> None:
        for tag in list(self.working):
            self._cancel_entry(tag)

    def _manage_position(self, price: float) -> None:
        p, c, tick = self.pos, self.cfg, self.cfg.tick
        p.best = max(p.best, price) if p.dir > 0 else min(p.best, price)
        if p.use_be and not p.be_done and (p.best - p.entry) * p.dir >= p.be_trigger * tick:
            new_stop = self._round(p.entry + p.dir * p.be_offset * tick)
            p.be_done = True
            if (price - new_stop) * p.dir <= 0:
                # Price already back through the breakeven level: a stop there would be
                # rejected / trigger instantly, so just get out.
                log.info("Breakeven level already crossed; closing at market")
                self._flatten("SL")
            else:
                self.broker.replace_stop(p.sl_id, new_stop)
                p.sl_price = new_stop
                log.info("Breakeven: stop moved to %s", new_stop)

    # ------------------------------------------------------------------ fills
    def on_fill(self, f: Fill) -> None:
        if f.tag in ENTRY_TAGS:
            self._on_entry_fill(f)
        elif f.tag in ("TP", "SL", "EOD") and self.pos:
            self._on_exit_fill(f)

    def _on_entry_fill(self, f: Fill) -> None:
        self.working.pop(f.tag, None)
        if self.pos is not None:
            # Both sides filled in a fast market: close the extra one immediately.
            log.error("Second entry %s filled while in a position; closing it", f.tag)
            self.broker.place_market("EXTRA", "SELL" if f.side == "BUY" else "BUY", f.qty)
            return
        self._cancel_entries()                       # manual OCA
        c = self.cfg
        d = 1 if f.side == "BUY" else -1
        use_be, be_t, be_o = c.use_be, c.be_trigger, c.be_offset
        if f.tag.startswith("BO"):
            tp, sl = c.bo_tp, c.bo_sl
            use_be, be_t, be_o = c.bo_use_be, c.bo_be_trigger, c.bo_be_offset
        elif f.tag.startswith("Flip"):
            tp, sl = c.flip_tp, c.flip_sl
        else:
            with_trend = (d > 0 and self.trend_up) or (d < 0 and self.trend_dn)
            tp = c.tp_trend_ticks if (c.use_trend_tp and with_trend) else c.tp_ticks
            if c.use_line_tp:
                target = self.range_high if d > 0 else self.range_low
                tp = max(1, round((target - f.price) * d / c.tick))
            sl = c.sl_ticks
        self.trades_today += 1
        self.used.add(f.tag)
        p = Position(f.tag, d, f.qty, f.price, tp, sl, best=f.price, entry_ts=f.ts,
                     use_be=use_be, be_trigger=be_t, be_offset=be_o)
        exit_side = "SELL" if d > 0 else "BUY"
        p.sl_price = self._round(f.price - d * sl * c.tick)
        p.tp_id = self.broker.place_limit("TP", exit_side, f.qty, self._round(f.price + d * tp * c.tick))
        p.sl_id = self.broker.place_stop("SL", exit_side, f.qty, p.sl_price)
        self.pos = p
        log.info("Filled %s %s @ %s  TP %s ticks / SL %s ticks", f.tag, f.qty, f.price, tp, sl)

    def _on_exit_fill(self, f: Fill) -> None:
        p, c = self.pos, self.cfg
        # cancel the other leg (manual OCO)
        for oid in (p.tp_id, p.sl_id):
            if oid and oid != f.order_id:
                self.broker.cancel(oid)
        pnl_ticks = (f.price - p.entry) * p.dir / c.tick
        full_stop = f.tag == "SL" and not p.be_done and pnl_ticks <= -(p.sl_ticks - 1)
        if full_stop and p.tag == "Long":
            self.flip_armed.add("Flip Short")
        if full_stop and p.tag == "Short":
            self.flip_armed.add("Flip Long")
        log.info("Exit %s %s @ %s (%+.0f ticks)", p.tag, f.tag, f.price, pnl_ticks)
        self._log_trade(p, f, pnl_ticks)
        self.pos = None

    # ------------------------------------------------------------------ end of day
    def _end_of_day(self) -> None:
        self._cancel_entries()
        if self.pos and self.cfg.flat_at_end:
            self._flatten("EOD")
        self.range_done = False                      # retire today's levels
        self.eod_done = True

    def _flatten(self, tag: str) -> None:
        p = self.pos
        for oid in (p.tp_id, p.sl_id):
            if oid:
                self.broker.cancel(oid)
        p.tp_id = p.sl_id = None
        self.broker.place_market(tag, "SELL" if p.dir > 0 else "BUY", p.qty)

    # ------------------------------------------------------------------ misc
    def _round(self, px: float) -> float:
        t = self.cfg.tick
        return round(round(px / t) * t, 10)

    def _log_trade(self, p: Position, f: Fill, pnl_ticks: float) -> None:
        path = self.cfg.trade_log
        if not path:
            return
        new = not os.path.exists(path)
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["entry_time", "exit_time", "tag", "dir", "qty", "entry", "exit", "exit_type", "pnl_ticks"])
            w.writerow([p.entry_ts, f.ts, p.tag, p.dir, p.qty, p.entry, f.price, f.tag, round(pnl_ticks, 2)])
