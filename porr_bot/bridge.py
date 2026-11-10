"""TradingView -> Webull bridge.

TradingView runs the PORR strategy (it has the market data) and sends an alert whenever it wants an
order placed, moved or cancelled. This server receives those alerts (webhook) and mirrors them on
Webull. Webull is the source of truth for fills: when an entry fills, the bridge itself places the
TP (limit) and SL (stop) from the ACTUAL fill price, cancels the other entry, and logs the trade.

Alert messages (JSON, sent by strategies/porr.pine with "Webhook bridge" enabled):
  {"pass": "...", "id": "...", "action": "place",  "tag": "Long", "side": "BUY", "type": "LIMIT"|"STOP",
   "price": 26840.25, "qty": 10, "tp": 500, "sl": 100, "be_trig": 100, "be_off": 50, "use_be": true}
  {"pass": "...", "id": "...", "action": "cancel", "tag": "Long"}
  {"pass": "...", "id": "...", "action": "breakeven", "tag": "Long"}
  {"pass": "...", "id": "...", "action": "flatten"}

Safety rules (independent of TradingView):
  * wrong/missing passphrase -> ignored; duplicate alert id -> ignored
  * never more than one position; a second entry fill is closed immediately
  * quantity capped by max_contracts_cap
  * at the trade-window end (default 11:00 CT) everything is cancelled and flattened, alert or not

Run:  python bridge.py --config config.toml        (env BRIDGE_PASSPHRASE + Webull keys, see README)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import threading
import time as _time
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from engine import Fill

log = logging.getLogger("porr.bridge")
ENTRY_TAGS = ("Long", "Short", "Flip Long", "Flip Short", "BO Long", "BO Short")


@dataclass
class Pos:
    tag: str
    dir: int
    qty: int
    entry: float
    tp_id: str | None
    sl_id: str | None
    sl_price: float
    intent: dict
    entry_ts: datetime
    be_done: bool = False


class Bridge:
    def __init__(self, broker, passphrase: str, tick: float = 0.25, max_qty: int = 1,
                 trade_log: str = "trades.csv", tz: str = "America/Chicago", trade_end: time = time(11, 0)):
        self.broker, self.passphrase, self.tick, self.max_qty = broker, passphrase, tick, max_qty
        self.trade_log, self.tz, self.trade_end = trade_log, ZoneInfo(tz), trade_end
        self.lock = threading.RLock()
        self.working: dict[str, tuple[str, dict]] = {}       # tag -> (order_id, intent)
        self.pos: Pos | None = None
        self.seen: set[str] = set()
        self.eod_done_for = None

    # ------------------------------------------------------------------ helpers
    def _r(self, px: float) -> float:
        return round(round(px / self.tick) * self.tick, 10)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    # ------------------------------------------------------------------ alerts
    def handle(self, msg: dict) -> str:
        if not self.passphrase or msg.get("pass") != self.passphrase:
            log.warning("rejected alert (bad passphrase)")
            return "forbidden"
        mid = str(msg.get("id", ""))
        with self.lock:
            if mid and mid in self.seen:
                return "duplicate"
            if mid:
                self.seen.add(mid)
                if len(self.seen) > 5000: self.seen = set(list(self.seen)[-2000:])
            act = msg.get("action")
            log.info("alert %s", {k: v for k, v in msg.items() if k != "pass"})
            if act == "place": return self._place(msg)
            if act == "cancel": return self._cancel(msg.get("tag"))
            if act == "breakeven": return self._breakeven(msg.get("tag"))
            if act == "flatten": return self._flatten_all("EOD")
            return "unknown action"

    def _place(self, m: dict) -> str:
        tag = m.get("tag")
        if tag not in ENTRY_TAGS: return "bad tag"
        if self.pos is not None: return "ignored: in a position"
        if self.now().time() >= self.trade_end: return "ignored: after trade window"
        qty = max(1, min(int(m.get("qty", 1)), self.max_qty))
        side, otype, px = m["side"], m["type"], self._r(float(m["price"]))
        old = self.working.get(tag)
        if old and old[1].get("price") == px and old[1].get("type") == otype:
            return "unchanged"
        if old:
            self.broker.cancel(old[0])
        oid = (self.broker.place_limit(tag, side, qty, px) if otype == "LIMIT"
               else self.broker.place_stop(tag, side, qty, px))
        self.working[tag] = (oid, {**m, "price": px, "qty": qty})
        return "placed"

    def _cancel(self, tag) -> str:
        old = self.working.pop(tag, None)
        if old:
            self.broker.cancel(old[0]); return "cancelled"
        return "nothing to cancel"

    def _breakeven(self, tag) -> str:
        p = self.pos
        if p is None or p.be_done or (tag and tag != p.tag) or not p.intent.get("use_be", True):
            return "ignored"
        new_stop = self._r(p.entry + p.dir * float(p.intent.get("be_off", 0)) * self.tick)
        if (p.sl_price - new_stop) * p.dir >= 0:            # never loosen the stop
            return "ignored: stop already tighter"
        self.broker.replace_stop(p.sl_id, new_stop)
        p.sl_price, p.be_done = new_stop, True
        log.info("breakeven: stop moved to %s", new_stop)
        return "moved"

    def _flatten_all(self, why: str) -> str:
        for tag in list(self.working):
            self._cancel(tag)
        if self.pos is not None:
            p = self.pos
            for oid in (p.tp_id, p.sl_id):
                if oid: self.broker.cancel(oid)
            p.tp_id = p.sl_id = None
            self.broker.place_market("EOD", "SELL" if p.dir > 0 else "BUY", p.qty)
            log.warning("flatten (%s)", why)
        return "flattened"

    # ------------------------------------------------------------------ fills (Webull = truth)
    def on_fill(self, f: Fill) -> None:
        with self.lock:
            if f.tag in ENTRY_TAGS:
                self._on_entry(f)
            elif f.tag in ("TP", "SL", "EOD") and self.pos is not None:
                self._on_exit(f)

    def _on_entry(self, f: Fill) -> None:
        w = self.working.pop(f.tag, None)
        intent = w[1] if w else {}
        if self.pos is not None:
            log.error("second entry %s filled while in a position: closing it", f.tag)
            self.broker.place_market("EXTRA", "SELL" if f.side == "BUY" else "BUY", f.qty)
            return
        for tag in list(self.working):                     # manual OCA
            self._cancel(tag)
        d = 1 if f.side == "BUY" else -1
        tp, sl = float(intent.get("tp", 100)), float(intent.get("sl", 100))
        exit_side = "SELL" if d > 0 else "BUY"
        sl_px = self._r(f.price - d * sl * self.tick)
        tp_id = self.broker.place_limit("TP", exit_side, f.qty, self._r(f.price + d * tp * self.tick))
        sl_id = self.broker.place_stop("SL", exit_side, f.qty, sl_px)
        self.pos = Pos(f.tag, d, f.qty, f.price, tp_id, sl_id, sl_px, intent, f.ts or self.now())
        log.info("filled %s %s @ %s -> TP %s / SL %s ticks", f.tag, f.qty, f.price, tp, sl)

    def _on_exit(self, f: Fill) -> None:
        p = self.pos
        for oid in (p.tp_id, p.sl_id):
            if oid and oid != f.order_id: self.broker.cancel(oid)
        ticks = (f.price - p.entry) * p.dir / self.tick
        kind = "SL" if f.tag == "SL" else f.tag
        log.info("exit %s %s @ %s (%+.0f ticks)", p.tag, kind, f.price, ticks)
        if self.trade_log:
            new = not os.path.exists(self.trade_log)
            with open(self.trade_log, "a", newline="") as fh:
                w = csv.writer(fh)
                if new: w.writerow(["entry_time", "exit_time", "tag", "dir", "qty", "entry", "exit", "exit_type", "pnl_ticks"])
                w.writerow([p.entry_ts, f.ts or self.now(), p.tag, p.dir, p.qty, p.entry, f.price, kind, round(ticks, 2)])
        self.pos = None

    # ------------------------------------------------------------------ housekeeping loop
    def tick_loop_once(self) -> None:
        for f in self.broker.poll_fills():
            self.on_fill(f)
        now = self.now()
        with self.lock:
            if now.time() >= self.trade_end and self.eod_done_for != now.date() and now.weekday() < 5:
                self._flatten_all("trade window end")
                self.eod_done_for = now.date()


def make_handler(bridge: Bridge):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                msg = json.loads(self.rfile.read(min(n, 10000)) or b"{}")
                res = bridge.handle(msg)
                code = 403 if res == "forbidden" else 200
            except Exception as e:                          # never crash the server on a bad alert
                log.exception("bad alert"); res, code = f"error: {e}", 400
            self.send_response(code); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(res.encode())

        def do_GET(self):                                   # health check
            p = bridge.pos
            body = json.dumps({"ok": True, "position": None if p is None else {"tag": p.tag, "dir": p.dir, "entry": p.entry},
                               "working": list(bridge.working)})
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a): pass
    return H


def main() -> None:
    import sys
    from run import load_config
    from broker import WebullBroker
    ap = argparse.ArgumentParser(description="PORR TradingView -> Webull bridge")
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg, raw = load_config(a.config)
    wb, br = raw.get("webull", {}), raw.get("bridge", {})
    pw = os.environ.get("BRIDGE_PASSPHRASE")
    if not pw: sys.exit("Set the BRIDGE_PASSPHRASE environment variable (same text as in the TradingView script).")
    if wb.get("sandbox", True):
        k, s, acct = os.environ.get("WEBULL_PAPER_APP_KEY"), os.environ.get("WEBULL_PAPER_APP_SECRET"), wb["paper_account_id"]
        log.warning("BRIDGE -> WEBULL PAPER account")
    else:
        k, s, acct = os.environ.get("WEBULL_APP_KEY"), os.environ.get("WEBULL_APP_SECRET"), wb["account_id"]
        log.warning("BRIDGE -> LIVE ACCOUNT - REAL ORDERS")
    if not k or not s: sys.exit("Webull key/secret environment variables are not set (see README).")
    broker = WebullBroker(k, s, acct, cfg.symbol, sandbox=wb.get("sandbox", True), order_events=wb.get("order_events", False))
    bridge = Bridge(broker, pw, cfg.tick, cfg.max_contracts_cap, cfg.trade_log, br.get("tz", "America/Chicago"), cfg.trade_end)
    port = a.port or int(br.get("port", 80))
    srv = ThreadingHTTPServer((br.get("host", "0.0.0.0"), port), make_handler(bridge))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("listening on port %s", port)
    last_report = None
    while True:
        try:
            bridge.tick_loop_once()
            now = bridge.now()
            if bridge.eod_done_for == now.date() and bridge.pos is None and last_report != now.date() and \
                    now.time() >= (datetime.combine(now.date(), cfg.trade_end) + timedelta(minutes=5)).time():
                from report import daily_report
                daily_report(cfg.trade_log, raw.get("email", {}), now.date(),
                             "Webull paper (bridge)" if wb.get("sandbox", True) else "LIVE (bridge)")
                last_report = now.date()
        except Exception:
            log.exception("loop error (continuing)")
        _time.sleep(float(br.get("poll_seconds", 1.0)))


if __name__ == "__main__":
    main()
