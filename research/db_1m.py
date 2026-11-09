"""Stream Databento ohlcv-1s CSV from stdin -> 1-minute OHLCV for every outright MNQ contract, all hours.
Output: ts_minute_utc,symbol,open,high,low,close,volume (sorted by minute as the input is time-ordered)."""
import sys, re
outright = re.compile(r"^MNQ[FGHJKMNQUVXZ]\d$")
out = open(sys.argv[1], "w"); out.write("ts,symbol,open,high,low,close,volume\n")
cur = None; agg = {}
def flush():
    for sym, (o, h, l, c, v) in sorted(agg.items()):
        out.write(f"{cur},{sym},{o},{h},{l},{c},{v}\n")
inp = sys.stdin; inp.readline(); n = 0
for line in inp:
    p = line.split(",")
    sym = p[9].strip()
    if not outright.match(sym): continue
    m = p[0][:16]
    if m != cur:
        if cur is not None: flush()
        cur, agg = m, {}
    o, h, l, c, v = float(p[4]), float(p[5]), float(p[6]), float(p[7]), int(p[8])
    a = agg.get(sym)
    if a is None: agg[sym] = [o, h, l, c, v]
    else:
        if h > a[1]: a[1] = h
        if l < a[2]: a[2] = l
        a[3] = c; a[4] += v
    n += 1
    if n % 5_000_000 == 0: print("rows", n, "at", m, flush=True)
if cur is not None: flush()
out.close(); print("DONE", n, flush=True)
