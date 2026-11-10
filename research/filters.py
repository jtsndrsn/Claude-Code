import csv, statistics, itertools
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt"
def load(n):
    rows = list(csv.DictReader(open(f"{S}/trades_ctx_{n}.csv")))
    for r in rows:
        for k, v in r.items():
            if k not in ("date", "dow", "side", "kind"): r[k] = float(v) if v not in ("", "None") else None
    return rows
def st(rows):
    eq = pk = dd = 0
    for r in rows: eq += r["net"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    return round(eq), round(dd)
# day-level filters only (everything known by 08:30 CT), thresholds picked from 2025 data only
def q(rows, f, p):
    xs = sorted(r[f] for r in rows if r[f] is not None and r["date"] < "2026"); return xs[int(len(xs) * p)]
for name in ("A", "B"):
    R = load(name)
    base5 = st([r for r in R if r["date"] < "2026"]); base6 = st([r for r in R if r["date"] >= "2026"])
    print(f"\nSetup {name}: base 2025 ${base5[0]} dd{base5[1]} | 2026 ${base6[0]} dd{base6[1]}")
    cands = {
        "skip Mondays": lambda r: r["dow"] == "Mon",
        "skip if VIX fell >0.9 yesterday": lambda r: r["vix_chg"] is not None and r["vix_chg"] < -0.94,
        "skip if VIX rose >0.9 yesterday": lambda r: r["vix_chg"] is not None and r["vix_chg"] > 0.93,
        "skip if VIX > 20": lambda r: r["vix"] is not None and r["vix"] > 20,
        "skip if VIX < 15": lambda r: r["vix"] is not None and r["vix"] < 15,
        "skip if 08:30 open in bottom 40% of range": lambda r: r["open_pos"] is not None and r["open_pos"] < 0.39,
        "skip if 08:30 open in top 20% of range": lambda r: r["open_pos"] is not None and r["open_pos"] > 0.79,
        "skip if range < 0.19 ATR (tight)": lambda r: r["range_atr"] is not None and r["range_atr"] < 0.19,
        "skip if range > 0.40 ATR (wide)": lambda r: r["range_atr"] is not None and r["range_atr"] > 0.40,
        "skip if big 07:30 news shock (>140t)": lambda r: r["shock0730"] > 140,
        "skip if quiet 07:30 (<34t)": lambda r: r["shock0730"] < 34,
        "skip if |gap| > 600t": lambda r: r["gap_t"] is not None and abs(r["gap_t"]) > 600,
        "skip if prev day range > 1.33 ATR": lambda r: r["prev_rng_atr"] is not None and r["prev_rng_atr"] > 1.33,
        "skip if ATR14 low (<1020t)": lambda r: r["atr14_t"] is not None and r["atr14_t"] < 1020,
        "skip counter-trend trades": lambda r: r["with_trend"] == 0,
        "skip with-trend trades": lambda r: r["with_trend"] == 1,
        "skip 2nd trade of day": lambda r: r["trade_no"] == 2,
        "skip entries after 09:00": lambda r: r["after0900"] == 1,
        "skip entries in first 2 min": lambda r: r["entry_min"] < 2,
        "skip fast approach (>210t in 15m)": lambda r: r["approach15"] > 210,
    }
    print(f"{'filter':42} {'skipped':>7} {'2025 $':>8} {'2025 dd':>7} {'2026 $':>8} {'2026 dd':>7}  verdict")
    for lab, fn in cands.items():
        keep = [r for r in R if not fn(r)]
        a = st([r for r in keep if r["date"] < "2026"]); b = st([r for r in keep if r["date"] >= "2026"])
        d5, d6 = a[0] - base5[0], b[0] - base6[0]
        verdict = "HELPS both years" if d5 > 0 and d6 > 0 else ("hurts both" if d5 < 0 and d6 < 0 else "mixed")
        print(f"{lab:42} {len(R)-len(keep):7} {a[0]:8} {a[1]:7} {b[0]:8} {b[1]:7}  {verdict} ({d5:+}/{d6:+})")
