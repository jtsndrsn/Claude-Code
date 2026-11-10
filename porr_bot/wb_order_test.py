"""Webull TEST-environment (sandbox) order check: proves the bot's order calls work and shows the exact
order-status fields Webull returns, so fill detection can be finalised. SANDBOX ONLY - the host is
hard-coded, so this can never touch a real account.

Usage (PowerShell), with the PAPER/sandbox key:
    $env:WB_KEY = "<paper app key>";  $env:WB_SECRET = "<paper app secret>"
    python wb_order_test.py <futures_account_id>
Sandbox market data only supports MES, so the test trades 1 MES contract.
"""
import json
import logging
import os
import sys
import time
import uuid

logging.disable(logging.CRITICAL)
HOST = "api.sandbox.webull.com"
key, secret = os.environ.get("WB_KEY"), os.environ.get("WB_SECRET")
if not key or not secret or len(sys.argv) < 2:
    sys.exit("Set WB_KEY / WB_SECRET (paper key) and pass the sandbox FUTURES account_id.")
acct = sys.argv[1]

from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.trade.trade_client import TradeClient

api = ApiClient(key, secret, "us"); api.add_endpoint("us", HOST)
tc = TradeClient(api); md = DataClient(api).futures_market_data


def show(label, res):
    try: body = res.json()
    except Exception: body = res.text
    print(f"\n--- {label}: HTTP {res.status_code}\n{json.dumps(body, indent=1)[:1500]}")
    return body


def safe(label, fn):
    try:
        return show(label, fn())
    except Exception as e:
        print(f"\n--- {label}: FAILED {str(e)[:300]}")


snap = safe("MESmain snapshot", lambda: md.get_futures_snapshot("MESmain", "US_FUTURES"))
try:
    px = float(snap[0]["price"])
except Exception:
    sys.exit("No MES price from the sandbox; stopping.")
print(f"\nMES price {px}")

# which contract symbol do orders accept? try the front month first, then the alias
def order(sym, side, otype, **prices):
    o = {"combo_type": "NORMAL", "client_order_id": uuid.uuid4().hex, "symbol": sym, "instrument_type": "FUTURES",
         "market": "US", "order_type": otype, "quantity": "1", "side": side, "time_in_force": "DAY",
         "entrust_type": "QTY", **{k: str(v) for k, v in prices.items()}}
    return o


def r4(x): return round(round(x * 4) / 4, 2)

sym = None
for cand in ("MESZ6", "MESmain"):
    o = order(cand, "BUY", "LIMIT", limit_price=r4(px - 50))
    body = safe(f"place LIMIT BUY {cand} far below market", lambda: tc.order_v3.place_order(acct, [o]))
    if body is not None and not (isinstance(body, dict) and body.get("error_code")):
        sym, lim = cand, o; break
if not sym:
    sys.exit("\nNo order symbol accepted - paste the output to Claude.")
cid = lim["client_order_id"]
time.sleep(1.5)
safe("detail of resting limit", lambda: tc.order_v3.get_order_detail(acct, cid))
safe("replace limit price", lambda: tc.order_v3.replace_order(acct, [{"client_order_id": cid, "quantity": "1", "limit_price": str(r4(px - 60))}]))
time.sleep(1.5)
safe("cancel limit", lambda: tc.order_v3.cancel_order(acct, cid))

st = order(sym, "SELL", "STOP_LOSS", stop_price=r4(px - 50))
safe("place STOP_LOSS SELL far below market", lambda: tc.order_v3.place_order(acct, [st]))
time.sleep(1.5)
safe("replace stop price", lambda: tc.order_v3.replace_order(acct, [{"client_order_id": st["client_order_id"], "quantity": "1", "stop_price": str(r4(px - 40))}]))
time.sleep(1.5)
safe("cancel stop", lambda: tc.order_v3.cancel_order(acct, st["client_order_id"]))

mk = order(sym, "BUY", "MARKET")
safe("place MARKET BUY 1", lambda: tc.order_v3.place_order(acct, [mk]))
for i in range(10):
    time.sleep(2)
    d = safe(f"detail of market buy (check {i + 1})", lambda: tc.order_v3.get_order_detail(acct, mk["client_order_id"]))
    if d and "FILLED" in json.dumps(d).upper():
        break
cl = order(sym, "SELL", "MARKET")
safe("place MARKET SELL 1 (close)", lambda: tc.order_v3.place_order(acct, [cl]))
time.sleep(3)
safe("detail of closing sell", lambda: tc.order_v3.get_order_detail(acct, cl["client_order_id"]))
print("\nDone. Paste everything above back to Claude (no key or secret is printed).")
