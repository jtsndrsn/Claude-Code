"""Stream Databento ohlcv-1s CSV (stdin) -> 30-second bars per outright MNQ contract, all hours.
Writes sym,t30_unix,open,high,low,close,volume to argv[1]."""
import sys, re
from datetime import datetime, timezone
outright = re.compile(r"^MNQ[FGHJKMNQUVXZ]\d$")
out = open(sys.argv[1], "w")
cur = {}  # sym -> [t, o, h, l, c, v]
def emit(s, b):
    out.write(f"{s},{b[0]},{b[1]},{b[2]},{b[3]},{b[4]},{b[5]}\n")
inp = sys.stdin
inp.readline()
n = 0
epoch_cache = {}
for line in inp:
    n += 1
    p = line.split(",")
    if len(p) < 10:
        continue
    s = p[9].rstrip("\n")
    if not outright.match(s):
        continue
    key = p[0][:16]  # YYYY-MM-DDTHH:MM
    base = epoch_cache.get(key)
    if base is None:
        base = int(datetime.fromisoformat(key).replace(tzinfo=timezone.utc).timestamp())
        if len(epoch_cache) > 100000: epoch_cache.clear()
        epoch_cache[key] = base
    t = base + (30 if int(p[0][17:19]) >= 30 else 0)
    o, h, l, c, v = float(p[4]), float(p[5]), float(p[6]), float(p[7]), int(p[8])
    b = cur.get(s)
    if b is None or b[0] != t:
        if b is not None: emit(s, b)
        cur[s] = [t, o, h, l, c, v]
    else:
        if h > b[2]: b[2] = h
        if l < b[3]: b[3] = l
        b[4] = c; b[5] += v
    if n % 10_000_000 == 0:
        print("rows", n, p[0][:19], flush=True)
for s, b in cur.items(): emit(s, b)
out.close(); print("DONE", n, flush=True)
