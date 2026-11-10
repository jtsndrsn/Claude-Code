import csv, sys, statistics
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt"
def load(n):
    rows = list(csv.DictReader(open(f"{S}/trades_ctx_{n}.csv")))
    for r in rows:
        for k, v in r.items():
            if k in ("date", "dow", "side", "kind"): continue
            r[k] = float(v) if v not in ("", "None") else None
    return rows
num = ["entry_min", "range_t", "on_range_t", "range_atr", "atr14_t", "prev_rng_atr", "gap_t", "open_pos", "approach5",
       "approach15", "vol15_t", "shock0730", "shock0900", "vix", "vix_chg"]
cat = ["dow", "side", "with_trend", "trade_no", "after0900"]
for name in ("A", "B"):
    R = load(name)
    print(f"\n===== Setup {name}: {len(R)} trades, avg ${statistics.mean(r['net'] for r in R):.0f}/trade =====")
    print("feature (quintile bins): avg $/trade per bin [2025 | 2026]   -- consistent sign in both years marked *")
    for f in num:
        xs = sorted(r[f] for r in R if r[f] is not None)
        if not xs: continue
        cuts = [xs[int(len(xs) * q / 5)] for q in range(1, 5)]
        def b(v): return sum(v >= c for c in cuts)
        out = []
        for k in range(5):
            g = [r for r in R if r[f] is not None and b(r[f]) == k]
            g5 = [r["net"] for r in g if r["date"] < "2026"]; g6 = [r["net"] for r in g if r["date"] >= "2026"]
            a5 = statistics.mean(g5) if g5 else 0; a6 = statistics.mean(g6) if g6 else 0
            mark = "*" if (a5 < 0 and a6 < 0) else ""
            out.append(f"{a5:+5.0f}|{a6:+5.0f}{mark}")
        lab = [f"<{cuts[0]:g}"] + [f"{cuts[i]:g}-{cuts[i+1]:g}" for i in range(3)] + [f">{cuts[3]:g}"]
        print(f"{f:13}", "  ".join(f"[{l}] {o}" for l, o in zip(lab, out)))
    for f in cat:
        vals = sorted({r[f] for r in R}, key=str)
        out = []
        for v in vals:
            g = [r for r in R if r[f] == v]
            g5 = [r["net"] for r in g if r["date"] < "2026"]; g6 = [r["net"] for r in g if r["date"] >= "2026"]
            out.append(f"{v}: n{len(g)} {statistics.mean(g5) if g5 else 0:+.0f}|{statistics.mean(g6) if g6 else 0:+.0f}")
        print(f"{f:13}", "  ".join(out))
