"""Webull API connection check - tells you what a key can do, without printing any secrets.

Usage (PowerShell):
    $env:WB_KEY = "<app key>";  $env:WB_SECRET = "<app secret>"
    python wb_check.py
Tries the production host and the test (sandbox) host and reports, for each:
  - can it log in and list accounts (and which accounts: paper / futures / ...)
  - can it read MNQ futures market data (snapshot + 1-minute bars)
"""
import logging
import os
import sys

logging.disable(logging.CRITICAL)            # the SDK logs request headers; keep the output clean
key, secret = os.environ.get("WB_KEY"), os.environ.get("WB_SECRET")
if not key or not secret:
    sys.exit("Set WB_KEY and WB_SECRET first (see the top of this file).")
SYMBOL = os.environ.get("WB_SYMBOL", "MNQZ6")

from webull.core.client import ApiClient
from webull.data.data_client import DataClient


def short(e):
    s = str(e)
    for marker in ("Code:", "error_code"):
        if marker in s:
            return s[s.index(marker):][:160]
    return s[:160]


for host in ("api.webull.com", "api.sandbox.webull.com"):
    print(f"\n=== {host} ===")
    api = ApiClient(key, secret, "us")
    api.add_endpoint("us", host)
    # 1) accounts (may trigger the 2FA approval in the Webull app the first time: approve it there)
    try:
        from webull.trade.trade_client import TradeClient
        tc = TradeClient(api)
        acct = getattr(tc, "account_v2", None) or getattr(tc, "account")
        res = acct.get_account_list()
        if res.status_code == 200:
            data = res.json()
            rows = data if isinstance(data, list) else data.get("data", data)
            print("  accounts: OK")
            for a in rows if isinstance(rows, list) else [rows]:
                if isinstance(a, dict):
                    print("   -", {k: a.get(k) for k in ("account_id", "account_type", "account_label", "account_class") if k in a})
        else:
            print("  accounts: HTTP", res.status_code, res.text[:160])
    except Exception as e:
        print("  accounts: FAILED -", short(e))
    # 2) futures market data
    try:
        md = DataClient(api).futures_market_data
        r = md.get_futures_snapshot(SYMBOL, "US_FUTURES")
        print("  MNQ snapshot:", "OK price " + str(r.json()[0].get("price")) if r.status_code == 200 else f"HTTP {r.status_code} {r.text[:120]}")
        r = md.get_futures_history_bars(SYMBOL, "US_FUTURES", "M1", count="3")
        print("  MNQ 1-min bars:", f"OK ({len(r.json()[0]['result'])} bars)" if r.status_code == 200 else f"HTTP {r.status_code} {r.text[:120]}")
    except Exception as e:
        print("  MNQ market data: FAILED -", short(e))
print("\nDone. Paste this output (it contains no key or secret) back to Claude.")
