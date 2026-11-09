"""Stream Databento ohlcv-1s CSV from stdin; keep outright MNQ contracts, 07:00-13:00 CT.
Writes date,symbol,ts_utc,open,high,low,close,volume to argv[1]."""
import sys, re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago"); UTC = ZoneInfo("UTC")
outright = re.compile(r"^MNQ[FGHJKMNQUVXZ]\d$")
win = {}
def window(dstr):
    w = win.get(dstr)
    if w is None:
        d = date.fromisoformat(dstr)
        s = datetime.combine(d, time(7, 0), CT).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        e = datetime.combine(d, time(13, 0), CT).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        w = win[dstr] = (s, e)
    return w
out = open(sys.argv[1], "w")
out.write("date,symbol,ts,open,high,low,close,volume\n")
n = kept = 0
inp = sys.stdin
inp.readline()
for line in inp:
    n += 1
    p = line.rstrip("\n").split(",")
    sym = p[9]
    if not outright.match(sym):
        continue
    ts = p[0][:19]
    s, e = window(ts[:10])
    if s <= ts < e:
        out.write(f"{ts[:10]},{sym},{ts},{p[4]},{p[5]},{p[6]},{p[7]},{p[8]}\n")
        kept += 1
    if n % 5_000_000 == 0:
        print("rows", n, "kept", kept, "at", ts, flush=True)
out.close()
print("DONE rows", n, "kept", kept, flush=True)
