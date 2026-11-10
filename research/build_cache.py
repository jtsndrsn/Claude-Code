"""1s RTH csv -> per-day numpy arrays for the front contract (by day volume). Saves db/cache_1s.npz."""
import numpy as np
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
SRC = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/db/mnq_1s_rth.csv"
OUT = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/db/cache_1s.npz"
store = {}; syms = {}
def flush(d, rows):
    vol = {s: sum(r[5] for r in v) for s, v in rows.items()}
    sym = max(vol, key=vol.get); rs = sorted(rows[sym])
    off = datetime.fromisoformat(rs[0][0]).replace(tzinfo=UTC).astimezone(CT).utcoffset().total_seconds()
    sec = np.array([(int(r[0][11:13]) * 3600 + int(r[0][14:16]) * 60 + int(r[0][17:19]) + off) % 86400 for r in rs], dtype=np.int32)
    arr = np.array([r[1:5] for r in rs], dtype=np.float64)
    store[d + "_t"] = sec; store[d + "_p"] = arr; syms[d] = sym
cur = None; rows = defaultdict(list)
with open(SRC) as fh:
    fh.readline()
    for line in fh:
        d, sym, ts, o, h, l, c, v = line.rstrip("\n").split(",")
        if d != cur:
            if cur: flush(cur, rows)
            cur, rows = d, defaultdict(list)
        rows[sym].append((ts, float(o), float(h), float(l), float(c), int(v)))
flush(cur, rows)
store["_days"] = np.array(sorted(syms)); store["_syms"] = np.array([syms[d] for d in sorted(syms)])
np.savez(OUT, **store); print("days", len(syms))
