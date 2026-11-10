"""Brokers the engine can trade through.

  PaperBroker  - simulated fills; used for replay backtests and live paper trading.
  WebullBroker - Webull US OpenAPI (official `webull-openapi-python-sdk`).

Every broker exposes the same calls:
  place_limit(tag, side, qty, price) -> order_id
  place_stop(tag, side, qty, stop)   -> order_id
  place_market(tag, side, qty)       -> order_id
  replace_stop(order_id, stop)
  cancel(order_id)
  poll_fills() -> list[Fill]
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import uuid
from datetime import datetime

from engine import Fill

log = logging.getLogger("porr.broker")


# ---------------------------------------------------------------------------------------------
class PaperBroker:
    """Fills orders against a price stream.

    Limit orders need price to trade `limit_through_ticks` THROUGH the limit to fill (same as the
    Pine `backtest_fill_limits_assumption = 1`). Stops fill at the price that triggered them.
    """

    def __init__(self, tick: float = 0.25, limit_through_ticks: int = 1):
        self.tick = tick
        self.through = limit_through_ticks
        self.orders: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._pending: list[Fill] = []
        self.last: float | None = None
        self.ts: datetime | None = None

    def _new(self, **o) -> str:
        oid = f"P{next(self._ids)}"
        self.orders[oid] = o
        return oid

    def place_limit(self, tag, side, qty, price):
        return self._new(tag=tag, side=side, qty=qty, type="LIMIT", price=price)

    def place_stop(self, tag, side, qty, stop):
        return self._new(tag=tag, side=side, qty=qty, type="STOP", price=stop)

    def place_market(self, tag, side, qty):
        oid = f"P{next(self._ids)}"
        self._pending.append(Fill(oid, tag, side, qty, self.last, self.ts))
        return oid

    def replace_stop(self, order_id, stop):
        if order_id in self.orders:
            self.orders[order_id]["price"] = stop

    def cancel(self, order_id):
        self.orders.pop(order_id, None)

    def on_price(self, ts: datetime, price: float, gap: bool = True) -> None:
        """Advance the simulation to a new price; fills are collected for poll_fills().

        gap=False means price moved continuously from the previous price (simulated path inside
        a bar), so a stop fills AT its stop price. gap=True (default, e.g. a bar open or a live
        price jump) fills a stop at the new price, i.e. with slippage.
        """
        self.last, self.ts = price, ts
        for oid, o in list(self.orders.items()):
            buy = o["side"] == "BUY"
            px = o["price"]
            if o["type"] == "LIMIT":
                hit = price <= px - self.through * self.tick if buy else price >= px + self.through * self.tick
                fill_px = px
            else:  # STOP
                hit = price >= px if buy else price <= px
                fill_px = price if gap else px
            if hit:
                del self.orders[oid]
                self._pending.append(Fill(oid, o["tag"], o["side"], o["qty"], fill_px, ts))

    def poll_fills(self) -> list[Fill]:
        out, self._pending = self._pending, []
        return out


# ---------------------------------------------------------------------------------------------
class WebullBroker:
    """Webull US OpenAPI futures orders.

    Verified from Webull docs: client creation, order_v3.place_order / replace_order /
    cancel_order, the futures order payload (symbol, instrument_type FUTURES, order_type,
    limit_price, quantity, side, time_in_force, entrust_type QTY, combo_type NORMAL), and the
    TradeEventsClient order-status stream.

    Confirmed from the SDK's own samples: "SELL" side and "stop_price" for STOP_LOSS orders
    (equity samples), get_order_detail for polling.

    NOT verified (test in the sandbox before going live) - marked VERIFY below:
      * the order-status event / order-detail field names used in _parse_event()
    """

    def __init__(self, app_key: str, app_secret: str, account_id: str, symbol: str,
                 sandbox: bool = True, region: str = "us", order_events: bool = True):
        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient
        from webull.trade.trade_events_client import TradeEventsClient

        self.symbol = symbol
        self.account_id = account_id
        api = ApiClient(app_key, app_secret, region)
        api.add_endpoint(region, "api.sandbox.webull.com" if sandbox else "api.webull.com")
        self.api_client = api
        self.trade = TradeClient(api)
        self.open_ids: list[str] = []                # working orders, polled round-robin
        self._seen_detail = False
        self._done: set[str] = set()
        self.tags: dict[str, str] = {}               # client_order_id -> engine tag
        self.sides: dict[str, str] = {}
        self.qtys: dict[str, int] = {}
        self._fills: "queue.Queue[Fill]" = queue.Queue()

        # Order status push (gRPC). VERIFY: sandbox host override if the SDK needs one.
        # Order-status push stream. Optional: it is a persistent connection, and some Webull accounts
        # allow only one. With order_events=False fills are found by polling order detail instead.
        if order_events:
            self.events = TradeEventsClient(app_key, app_secret, region)
            self.events.on_events_message = self._on_event
            threading.Thread(target=self.events.do_subscribe, args=([account_id],), daemon=True).start()

    # -- orders --------------------------------------------------------------------------------
    def _place(self, tag, side, qty, order_type, **prices) -> str:
        coid = uuid.uuid4().hex
        order = {
            "combo_type": "NORMAL",
            "client_order_id": coid,
            "symbol": self.symbol,
            "instrument_type": "FUTURES",
            "market": "US",
            "order_type": order_type,
            "quantity": str(qty),
            "side": side,
            "time_in_force": "DAY",
            "entrust_type": "QTY",
            **{k: str(v) for k, v in prices.items()},
        }
        self.tags[coid], self.sides[coid], self.qtys[coid] = tag, side, qty
        res = self.trade.order_v3.place_order(self.account_id, [order])
        if res.status_code != 200:
            raise RuntimeError(f"place_order failed {res.status_code}: {res.text}")
        self.open_ids.append(coid)
        log.info("Webull placed %s %s %s %s %s", tag, side, qty, order_type, prices)
        return coid

    def place_limit(self, tag, side, qty, price):
        return self._place(tag, side, qty, "LIMIT", limit_price=price)

    def place_stop(self, tag, side, qty, stop):
        return self._place(tag, side, qty, "STOP_LOSS", stop_price=stop)

    def place_market(self, tag, side, qty):
        return self._place(tag, side, qty, "MARKET")

    def replace_stop(self, order_id, stop):
        res = self.trade.order_v3.replace_order(
            self.account_id, [{"client_order_id": order_id, "quantity": str(self.qtys[order_id]),
                               "stop_price": str(stop)}])
        if res.status_code != 200:
            raise RuntimeError(f"replace_order failed {res.status_code}: {res.text}")

    def cancel(self, order_id):
        if order_id in self.open_ids:
            self.open_ids.remove(order_id)
        res = self.trade.order_v3.cancel_order(self.account_id, order_id)
        if res.status_code != 200:
            log.warning("cancel_order %s -> %s %s", order_id, res.status_code, res.text)

    # -- fills ---------------------------------------------------------------------------------
    def _on_event(self, event_type, subscribe_type, payload, raw_message):
        try:
            fill = self._parse_event(payload)
            if fill and fill.order_id not in self._done:
                self._done.add(fill.order_id)
                self._fills.put(fill)
        except Exception:                            # never kill the stream thread
            log.exception("Could not parse order event: %s", raw_message)

    def _parse_event(self, payload) -> Fill | None:
        # VERIFY: field names below are best guesses until checked against a sandbox event.
        log.debug("order event: %s", payload)
        p = payload if isinstance(payload, dict) else getattr(payload, "__dict__", {})
        coid = p.get("client_order_id")
        if coid in self._done:
            return None
        status = str(p.get("order_status") or p.get("status") or "").upper()
        if coid not in self.tags or status != "FILLED":
            return None
        price = float(p.get("filled_price") or p.get("avg_filled_price") or p.get("price"))
        qty = int(float(p.get("filled_quantity") or p.get("filled_qty") or self.qtys[coid]))
        return Fill(coid, self.tags[coid], self.sides[coid], qty, price, datetime.now().astimezone())

    def _poll_one(self) -> None:
        """Fallback if a push event is missed: check ONE working order per call (Order Detail is
        rate-limited to 2 requests / 2 s), rotating through the working orders."""
        if not self.open_ids:
            return
        coid = self.open_ids.pop(0)
        self.open_ids.append(coid)
        res = self.trade.order_v3.get_order_detail(self.account_id, coid)
        if res.status_code != 200:
            return
        data = res.json()
        if not self._seen_detail:                    # VERIFY: log the real shape once
            log.info("order detail sample: %s", data)
            self._seen_detail = True
        fill = self._parse_event(_find_order(data, coid) or {})
        if fill and coid not in self._done:
            self._done.add(coid)
            self._fills.put(fill)

    def poll_fills(self) -> list[Fill]:
        try:
            self._poll_one()
        except Exception:
            log.exception("order detail poll failed")
        out = []
        while not self._fills.empty():
            f = self._fills.get_nowait()
            if f.order_id in self.open_ids:
                self.open_ids.remove(f.order_id)
            out.append(f)
        return out


def _find_order(obj, coid):
    """Return the dict inside `obj` that carries this client_order_id (response shape unverified)."""
    if isinstance(obj, dict):
        if obj.get("client_order_id") == coid:
            return obj
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            hit = _find_order(v, coid)
            if hit:
                return hit
    return None
