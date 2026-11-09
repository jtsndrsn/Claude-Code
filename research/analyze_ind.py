import csv, statistics
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt"
def load(n):
    rows = list(csv.DictReader(open(f"{S}/trades_ind_{n}.csv")))
    for r in rows:
        for k, v in r.items():
            if k not in ("date", "dow", "side", "kind"): r[k] = float(v) if v not in ("", "None") else None
        d = 1 if r["side"] == "L" else -1
        # direction-aware: >0 means the indicator is on the trade's side (e.g. long with RSI>50)
        r["rsi_dir"] = (r["d_rsi"] - 50) * d; r["stoch_dir"] = (r["d_stoch"] - 50) * d
        r["pctb_dir"] = (r["d_pctb"] - 0.5) * d; r["macdh_dir"] = r["d_macd_hist"] * d
        r["m5rsi_dir"] = (r["m5_rsi"] - 50) * d if r["m5_rsi"] is not None else None
        r["m5stoch_dir"] = (r["m5_stoch"] - 50) * d if r["m5_stoch"] is not None else None
        r["di_with"] = 1.0 if (r["d_di_trend"] == 1) == (d == 1) else 0.0
    return rows
feats = ["d_rsi", "rsi_dir", "d_stoch", "stoch_dir", "d_willr", "d_pctb", "pctb_dir", "d_macd_hist", "macdh_dir", "d_adx",
         "m5_rsi", "m5rsi_dir", "m5_stoch", "m5stoch_dir", "vwap_dist_t"]
cats = ["d_macd_above_sig", "d_macd_hist_rising", "macd_with_trade", "rsi_with_trade", "di_with"]
for name in ("A", "B"):
    R = load(name); W = [r for r in R if r["net"] > 0]; Lz = [r for r in R if r["net"] < 0]
    print(f"\n===== Setup {name}: winners {len(W)} vs losers {len(Lz)} — mean value | quintile avg $/trade [2025|2026], * = negative both years")
    for f in feats:
        vw = [r[f] for r in W if r[f] is not None]; vl = [r[f] for r in Lz if r[f] is not None]
        xs = sorted(r[f] for r in R if r[f] is not None); cuts = [xs[int(len(xs) * q / 5)] for q in range(1, 5)]
        bins = []
        for k in range(5):
            g = [r for r in R if r[f] is not None and sum(r[f] >= c for c in cuts) == k]
            a5 = [r["net"] for r in g if r["date"] < "2026"]; a6 = [r["net"] for r in g if r["date"] >= "2026"]
            m5 = statistics.mean(a5) if a5 else 0; m6 = statistics.mean(a6) if a6 else 0
            bins.append(f"{m5:+4.0f}|{m6:+4.0f}{'*' if m5 < 0 and m6 < 0 else ' '}")
        print(f"{f:13} win {statistics.mean(vw):8.2f} lose {statistics.mean(vl):8.2f} | cuts {[round(c,1) for c in cuts]} | " + " ".join(bins))
    for f in cats:
        out = []
        for v in (0.0, 1.0):
            g = [r for r in R if r[f] == v]
            a5 = [r["net"] for r in g if r["date"] < "2026"]; a6 = [r["net"] for r in g if r["date"] >= "2026"]
            out.append(f"{int(v)}: n{len(g)} win% {100*sum(r['net']>0 for r in g)/len(g):.0f} ${statistics.mean(a5):+.0f}|{statistics.mean(a6):+.0f}")
        print(f"{f:20}", "   ".join(out))
