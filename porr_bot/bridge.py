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
                 trade_log: str = "trades.csv", tz: str = "America/Chicago", trade_end: time = time(11, 0),
                 state_path: str | None = None, notify=None):
        self.broker, self.passphrase, self.tick, self.max_qty = broker, passphrase, tick, max_qty
        self.trade_log, self.tz, self.trade_end = trade_log, ZoneInfo(tz), trade_end
        self.state_path = state_path
        self.notify = notify or (lambda subject, body: log.warning("NOTIFY %s: %s", subject, body))
        self.lock = threading.RLock()
        self.working: dict[str, tuple[str, dict]] = {}       # tag -> (order_id, intent)
        self.pos: Pos | None = None
        self.seen: set[str] = set()
        self.eod_done_for = None
        self.last_alert: datetime | None = None
        self.heartbeat_for = None
        self.silence_warned_for = None

    # ------------------------------------------------------------------ state on disk (restart recovery)
    def save(self) -> None:
        if not self.state_path:
            return
        p = self.pos
        st = {"working": {t: [oid, it] for t, (oid, it) in self.working.items()},
              "pos": None if p is None else {"tag": p.tag, "dir": p.dir, "qty": p.qty, "entry": p.entry, "tp_id": p.tp_id,
                                             "sl_id": p.sl_id, "sl_price": p.sl_price, "intent": p.intent,
                                             "entry_ts": p.entry_ts.isoformat(), "be_done": p.be_done},
              "eod_done_for": self.eod_done_for.isoformat() if self.eod_done_for else None}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(st, fh)
        os.replace(tmp, self.state_path)

    def restore(self) -> None:
        """Load the saved state after a restart and reconcile it with Webull."""
        if not self.state_path or not os.path.exists(self.state_path):
            self._check_untracked_position(); return
        with open(self.state_path) as fh:
            st = json.load(fh)
        for tag, (oid, it) in st.get("working", {}).items():
            self.working[tag] = (oid, it); self.broker.adopt(oid, tag, it["side"], it["qty"])
        if st.get("eod_done_for"):
            self.eod_done_for = datetime.fromisoformat(st["eod_done_for"]).date() if "T" in st["eod_done_for"] else \
                datetime.strptime(st["eod_done_for"], "%Y-%m-%d").date()
        q = st.get("pos")
        if q:
            self.pos = Pos(q["tag"], q["dir"], q["qty"], q["entry"], q["tp_id"], q["sl_id"], q["sl_price"], q["intent"],
                           datetime.fromisoformat(q["entry_ts"]), q["be_done"])
            exit_side = "SELL" if q["dir"] > 0 else "BUY"
            for oid, tg in ((q["tp_id"], "TP"), (q["sl_id"], "SL")):
                if oid: self.broker.adopt(oid, tg, exit_side, q["qty"])
            # make sure the stop is still working on Webull; if not (and we still hold the position) re-place it
            try:
                open_ids = self.broker.open_order_ids()
                net = self.broker.net_position()
                if q["sl_id"] not in open_ids and (net is None or abs(net) > 0):
                    for _ in range(3):                       # let a missed exit fill show up first
                        for f in self.broker.poll_fills(): self.on_fill(f)
                    if self.pos is not None and self.pos.sl_id not in self.broker.open_order_ids():
                        p = self.pos
                        p.sl_id = self.broker.place_stop("SL", exit_side, p.qty, p.sl_price)
                        self.notify("PORR bridge: stop re-placed after restart",
                                    f"{p.tag} {p.qty} @ {p.entry}: stop was missing on Webull, re-placed at {p.sl_price}.")
            except Exception as e:
                self.notify("PORR bridge: CHECK POSITION", f"Restart recovery could not verify orders on Webull: {e}")
        log.warning("state restored: position=%s working=%s", self.pos and self.pos.tag, list(self.working))
        self.save()

    def _check_untracked_position(self) -> None:
        try:
            net = self.broker.net_position()
            if net:
                self.notify("PORR bridge: UNTRACKED POSITION",
                            f"Webull shows {net} contracts but the bridge has no saved state. Check the account now.")
        except Exception:
            log.exception("could not read positions")

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
            self.last_alert = self.now()
            log.info("alert %s", {k: v for k, v in msg.items() if k != "pass"})
            res = ("unknown action" if act not in ("place", "cancel", "breakeven", "flatten") else
                   self._place(msg) if act == "place" else self._cancel(msg.get("tag")) if act == "cancel" else
                   self._breakeven(msg.get("tag")) if act == "breakeven" else self._flatten_all("EOD"))
            self.save()
            return res

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
            self.save()

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
                self.save()
        # morning checks (weekdays): "I'm up" at 08:20, and a warning if no alerts have arrived by 08:40
        if now.weekday() < 5:
            if now.time() >= time(8, 20) and self.heartbeat_for != now.date() and now.time() < self.trade_end:
                self.heartbeat_for = now.date()
                self.notify("PORR bridge: up and waiting", f"{now:%Y-%m-%d %H:%M} CT - connected, "
                            f"position: {self.pos.tag if self.pos else 'none'}, working orders: {list(self.working) or 'none'}.")
            start = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now.time() >= time(8, 40) and now.time() < self.trade_end and self.silence_warned_for != now.date() \
                    and (self.last_alert is None or self.last_alert < start):
                self.silence_warned_for = now.date()
                self.notify("PORR bridge: NO ALERTS from TradingView",
                            "No TradingView alert has arrived since 08:00 CT. Check that the TradingView alert is active "
                            "and the chart is open/connected. The bridge will still flatten at the window end.")


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
    sandbox = str(os.environ.get("WEBULL_SANDBOX", wb.get("sandbox", True))).lower() in ("1", "true", "yes")
    wb["sandbox"] = sandbox
    if sandbox:
        k, s = os.environ.get("WEBULL_PAPER_APP_KEY"), os.environ.get("WEBULL_PAPER_APP_SECRET")
        acct = os.environ.get("WEBULL_PAPER_ACCOUNT_ID") or wb.get("paper_account_id")
        log.warning("BRIDGE -> WEBULL PAPER account")
    else:
        k, s = os.environ.get("WEBULL_APP_KEY"), os.environ.get("WEBULL_APP_SECRET")
        acct = os.environ.get("WEBULL_ACCOUNT_ID") or wb.get("account_id")
        log.warning("BRIDGE -> LIVE ACCOUNT - REAL ORDERS")
    if not k or not s: sys.exit("Webull key/secret environment variables are not set (see README).")
    symbol = os.environ.get("PORR_SYMBOL", cfg.symbol)
    max_qty = int(os.environ.get("PORR_MAX_CONTRACTS", cfg.max_contracts_cap))
    data_dir = os.environ.get("DATA_DIR", ".")
    os.makedirs(data_dir, exist_ok=True)
    trade_log = os.path.join(data_dir, os.path.basename(cfg.trade_log))
    email = dict(raw.get("email", {}))
    if os.environ.get("EMAIL_TO"):                         # Render: email settings from environment
        email.update(enabled=True, to=os.environ["EMAIL_TO"], **{"from": os.environ.get("EMAIL_FROM", os.environ["EMAIL_TO"])})
    def notify(subject, body):
        log.warning("%s: %s", subject, body)
        if email.get("enabled"):
            from report import send_email
            try: send_email(email, subject, body)
            except Exception: log.exception("notify email failed")
    broker = WebullBroker(k, s, acct, symbol, sandbox=sandbox, order_events=wb.get("order_events", False))
    bridge = Bridge(broker, pw, cfg.tick, max_qty, trade_log, br.get("tz", "America/Chicago"), cfg.trade_end,
                    state_path=os.path.join(data_dir, "bridge_state.json"), notify=notify)
    bridge.restore()
    port = a.port or int(os.environ.get("PORT", br.get("port", 80)))
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
                daily_report(trade_log, email, now.date(), "Webull paper (bridge)" if sandbox else "LIVE (bridge)")
                last_report = now.date()
        except Exception:
            log.exception("loop error (continuing)")
        _time.sleep(float(br.get("poll_seconds", 2.5)))


if __name__ == "__main__":
    main()
