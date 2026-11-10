"""Staged parameter search for PORR on 1-second data. In-sample: 2025. Out-of-sample: 2026."""
import sys, json, itertools, time
from multiprocessing import Pool
sys.path.insert(0, "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/bt")
from fastsim import load_days, sim_day
S = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad"
QTY, TICK_USD, COMM_RT = 10, 0.5, 1.40
D = F = None
def init():
    global D, F
    D = load_days(); F = json.load(open(S + "/db/features.json"))

def stats(trades):
    eq = peak = dd = 0.0; gw = gl = 0.0; w = 0
    for tk in trades:
        pnl = tk * TICK_USD * QTY - COMM_RT * QTY
        eq += pnl; peak = max(peak, eq); dd = max(dd, peak - eq)
        if pnl > 0: gw += pnl; w += 1
        else: gl -= pnl
    n = len(trades)
    return dict(n=n, net=round(eq), dd=round(dd), win=round(100 * w / n, 1) if n else 0,
                pf=round(gw / gl, 2) if gl else None)

def run(p):
    """p: dict(level, sl, rr, delay, be, skip, trend, tmode, end, onep). Returns stats for 2025 / 2026 / all."""
    cfg = dict(trade_start=8*3600+1800, trade_end=p["end"]*3600, delay=p["delay"], sl=p["sl"], tp=round(p["sl"]*p["rr"]),
               max_trades=10, one_per_level=p.get("onep", True), skip_broken=p["skip"], be_trig=None)
    tp = cfg["tp"]
    if p["be"] == "1R0":   cfg.update(be_trig=p["sl"], be_off=2)              # +1R -> stop to entry (+2 ticks)
    elif p["be"] == "TP85": cfg.update(be_trig=round(tp*0.875), be_off=round(tp*0.5))   # user's style 175/100 of 200
    elif p["be"] == "1R05": cfg.update(be_trig=p["sl"], be_off=round(p["sl"]*0.5))     # +1R -> lock +0.5R
    per = {"2025": [], "2026": []}
    for d in sorted(D):
        f = F[d]; lv = f["levels"].get(p["level"])
        if not lv: continue
        al = ash = True; tmd = None
        tr = p.get("trend")
        if tr:
            sg = f["trend"][tr]
            if p["tmode"] == "filter":            # only trade in the trend's direction
                al, ash = sg >= 0, sg <= 0
            elif p["tmode"] == "boost":           # with-trend trades get a 1.5x TP
                tmd = {1: 1.5 if sg > 0 else 1.0, -1: 1.5 if sg < 0 else 1.0}
        res = sim_day(D[d], lv[0], lv[1], cfg, allow_long=al, allow_short=ash, tp_mult_dir=tmd)
        per[d[:4]] += [x[4] for x in res]
    return dict(p=p, y25=stats(per["2025"]), y26=stats(per["2026"]), all=stats(per["2025"] + per["2026"]))

def grid(params, procs=4):
    with Pool(procs, initializer=init) as pool:
        return pool.map(run, params, chunksize=8)

if __name__ == "__main__":
    stage = sys.argv[1]
    t = time.time()
    if stage == "1":
        P = [dict(level=lv, sl=sl, rr=rr, delay=dl, be=be, skip=sk, end=13)
             for lv, sl, rr, dl, be, sk in itertools.product(["PRE60", "PRE30", "PRE90", "ON", "PD"], [100, 150, 200, 300, 400],
                                                             [1, 1.5, 2, 3, 4, 5], [0, 10, 20, 40], ["off", "1R0", "1R05", "TP85"], [False, True])]
    else:
        P = json.load(open(sys.argv[2]))
    R = grid(P)
    json.dump(R, open(S + f"/bt/grid_stage{stage}.json", "w"))
    print("runs", len(R), "secs", round(time.time() - t))
