import csv, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, ".")
from bt_1s import days
T = 0.25
trades = list(csv.DictReader(open("trades_1s_user.csv")))
byday = {}
for t in trades:
    byday.setdefault(t["entry_time"][:10], []).append(t)
viol, cats, be_ticks = [], Counter(), Counter()
for d, sym, bars in days():
    for t in byday.get(d, []):
        ent, ext = datetime.fromisoformat(t["entry_time"]), datetime.fromisoformat(t["exit_time"])
        dirn = 1 if t["side"] == "Long" else -1
        e = float(t["entry"])
        seg = [b for b in bars if ent <= b.start <= ext]
        # MFE in ticks over the trade's 1-second bars (entry bar included; conservative = may overstate)
        mfe = max(((b.high - e) if dirn > 0 else (e - b.low)) for b in seg) / T if seg else 0
        # MFE excluding the entry bar and the exit bar (pure in-trade seconds)
        mid = [b for b in seg if ent < b.start < ext]
        mfe_mid = max([((b.high - e) if dirn > 0 else (e - b.low)) / T for b in mid] or [0])
        kind, ticks = t["exit_type"], float(t["ticks"])
        if kind == "BE-stop": be_ticks[ticks] += 1
        reached = mfe_mid >= 175
        cats[(kind, "MFE>=175" if reached else "MFE<175")] += 1
        if reached and kind == "SL":
            viol.append((t["entry_time"], t["side"], e, t["exit"], round(mfe_mid, 1)))
        if kind == "BE-stop" and mfe < 175:
            viol.append(("BE without trigger", t["entry_time"], round(mfe, 1)))
print("exit type vs max favorable move (in-trade seconds):")
for k, v in sorted(cats.items()): print(" ", k, v)
print("BE-stop exit ticks:", dict(be_ticks))
print("violations:", len(viol))
for v in viol[:20]: print(" ", v)
