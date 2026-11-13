"""Event-driven PORR simulator on 1-second bars (numpy). Mirrors porr_bot/engine.py + PaperBroker:
4-price path per bar (O,H,L,C or O,L,H,C), limits fill 1 tick through at the limit, stops fill at the
stop (or at the bar open if it gaps through), orders placed on a tick work from the next tick."""
import numpy as np
TICK = 0.25
CACHE = "/tmp/claude-0/-home-user-Claude-Code/5e83bea1-15df-515d-8b9d-19cf28b4057a/scratchpad/db/cache_1s.npz"

def load_days(cache=CACHE):
    z = np.load(cache)
    days = list(z["_days"]); syms = list(z["_syms"])
    out = {}
    for d, s in zip(days, syms):
        t = z[d + "_t"]; p = z[d + "_p"]               # p: open, high, low, close
        o, h, l, c = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
        up_first = np.abs(h - o) <= np.abs(o - l)        # same rule as feeds.bar_ticks
        P = np.empty((len(t), 4)); P[:, 0] = o; P[:, 3] = c
        P[:, 1] = np.where(up_first, h, l); P[:, 2] = np.where(up_first, l, h)
        out[d] = dict(sym=s, t=t, h=h, l=l, P=P.ravel(), T=np.repeat(t, 4),
                      G=np.tile(np.array([True, False, False, False]), len(t)))
    return out

def _first(mask, start):
    """first index >= start where mask is True, else -1."""
    if start >= len(mask): return -1
    idx = np.flatnonzero(mask[start:])
    return int(idx[0]) + start if len(idx) else -1

def range_levels(day, start_s, end_s):
    m = (day["t"] >= start_s) & (day["t"] < end_s)
    if not m.any(): return None
    return float(day["h"][m].max()), float(day["l"][m].min())

def sim_day(day, hi, lo, cfg, allow_long=True, allow_short=True, tp_mult=1.0, tp_mult_dir=None):
    """Returns list of (dir, entry, exit, kind, ticks, entry_sec, exit_sec, be_hit)."""
    P, G, T = day["P"], day["G"], day["T"]
    t0, t1 = cfg["trade_start"], cfg["trade_end"]
    i = int(np.searchsorted(T, t0)); end = int(np.searchsorted(T, t1))
    if i >= end: return []
    P = P[:end]; G = G[:end]; T = T[:end]
    d_ = cfg["delay"] * TICK
    L, S = lo - d_, hi + d_
    sl, tp = cfg["sl"] * TICK, cfg["tp"] * TICK * tp_mult
    be_on = cfg.get("be_trig") is not None
    if be_on:
        trig, off = cfg["be_trig"] * TICK, cfg["be_off"] * TICK
    used = {1: False, -1: False}; broken = {1: False, -1: False}
    allowed = {1: allow_long, -1: allow_short}
    out = []; n = 0
    above_L = P > L; fillL = P <= L - TICK          # long arms when price above, fills 1 tick through
    below_S = P < S; fillS = P >= S + TICK
    while i < len(P) and n < cfg["max_trades"]:
        cand = []
        for side, arm_m, fill_m, lvl in ((1, above_L, fillL, L), (-1, below_S, fillS, S)):
            if not allowed[side] or broken[side] or (cfg["one_per_level"] and used[side]):
                continue
            a = _first(arm_m, i)
            if cfg["skip_broken"]:
                b = _first(fill_m, i)                  # price beyond the level before we could arm
                if b != -1 and (a == -1 or b < a):
                    broken[side] = True; continue
            if a == -1: continue
            f = _first(fill_m, a + 1)
            if f != -1: cand.append((f, side, lvl))
        if not cand: break
        k, dirn, entry = min(cand)
        used[dirn] = True; n += 1
        tpx = tp * (tp_mult_dir.get(dirn, 1.0) if tp_mult_dir else 1.0)
        tp_px = entry + dirn * tpx; sl_px = entry - dirn * sl
        seg = P[k + 1:]
        if dirn > 0:
            tp_hit = seg >= tp_px + TICK; sl_hit = seg <= sl_px
        else:
            tp_hit = seg <= tp_px - TICK; sl_hit = seg >= sl_px
        m_tp = _first(tp_hit, 0); m_sl = _first(sl_hit, 0)
        exit_rel, kind, be_hit = None, None, False
        if be_on:
            fav = (P[k:] - entry) * dirn
            tt = _first(fav >= trig, 0)                 # trigger tick (relative to k)
            first = min([x for x in (m_tp, m_sl) if x != -1], default=-1)   # rel to k+1
            if tt != -1 and (first == -1 or first + 1 > tt):
                be_hit = True
                bes = entry + dirn * off
                seg2 = P[k + tt + 1:]
                if dirn > 0: be_m = seg2 <= bes; tp2 = seg2 >= tp_px + TICK
                else: be_m = seg2 >= bes; tp2 = seg2 <= tp_px - TICK
                a1 = _first(tp2, 0); a2 = _first(be_m, 0)
                if a1 != -1 and (a2 == -1 or a1 < a2): exit_rel, kind = k + tt + 1 + a1, "TP"
                elif a2 != -1: exit_rel, kind = k + tt + 1 + a2, "BE"
            elif first != -1:
                exit_rel = k + 1 + first; kind = "TP" if first == m_tp else "SL"
        else:
            first = min([x for x in (m_tp, m_sl) if x != -1], default=-1)
            if first != -1: exit_rel = k + 1 + first; kind = "TP" if first == m_tp else "SL"
        if exit_rel is None:
            x = len(P) - 1; px = P[x]; kind = "EOD"
        else:
            x = exit_rel
            if kind == "TP": px = tp_px
            elif kind == "SL": px = P[x] if G[x] else sl_px
            else: px = P[x] if G[x] else bes
        out.append((dirn, entry, px, kind, (px - entry) * dirn / TICK, int(T[k]), int(T[x]), be_hit))
        if cfg["skip_broken"]:                          # crossing the other line while in this trade
            other = -dirn; seg_in = P[k:x + 1]
            if (other == -1 and (seg_in >= S + TICK).any()) or (other == 1 and (seg_in <= L - TICK).any()):
                broken[other] = True
        i = x                                           # orders re-placed on the exit tick
    return out


def sim_day_reclaim(day, hi, lo, cfg, tp_mult_dir=None):
    """Confirmation entry: price must first trade `pierce` ticks beyond the line, then we enter
    (stop order) when it trades back to the line. Long at the range low, short at the range high."""
    P, G, T = day["P"], day["G"], day["T"]
    i = int(np.searchsorted(T, cfg["trade_start"])); end = int(np.searchsorted(T, cfg["trade_end"]))
    if i >= end: return []
    P = P[:end]; G = G[:end]; T = T[:end]
    pr = cfg["pierce"] * TICK; sl, tp = cfg["sl"] * TICK, cfg["tp"] * TICK
    used = {1: False, -1: False}; out = []; n = 0
    while i < len(P) and n < cfg["max_trades"]:
        cand = []
        for side, lvl in ((1, lo), (-1, hi)):
            if used[side]: continue
            beyond = (P <= lvl - pr) if side > 0 else (P >= lvl + pr)
            a = _first(beyond, i)
            if a == -1: continue
            back = (P >= lvl) if side > 0 else (P <= lvl)
            f = _first(back, a + 1)
            if f != -1: cand.append((f, side, lvl))
        if not cand: break
        k, dirn, lvl = min(cand)
        entry = P[k] if G[k] else lvl                    # stop entry: slips to the open on a gap
        used[dirn] = True; n += 1
        tpx = tp * (tp_mult_dir.get(dirn, 1.0) if tp_mult_dir else 1.0)
        tp_px = entry + dirn * tpx; sl_px = entry - dirn * sl
        trig, off = cfg["be_trig"] * TICK, cfg["be_off"] * TICK
        seg = P[k + 1:]
        tp_hit = (seg >= tp_px + TICK) if dirn > 0 else (seg <= tp_px - TICK)
        sl_hit = (seg <= sl_px) if dirn > 0 else (seg >= sl_px)
        m_tp, m_sl = _first(tp_hit, 0), _first(sl_hit, 0)
        fav = (P[k:] - entry) * dirn; tt = _first(fav >= trig, 0)
        first = min([x for x in (m_tp, m_sl) if x != -1], default=-1)
        exit_rel = None; kind = None; bes = entry + dirn * off
        if tt != -1 and (first == -1 or first + 1 > tt):
            seg2 = P[k + tt + 1:]
            be_m = (seg2 <= bes) if dirn > 0 else (seg2 >= bes)
            tp2 = (seg2 >= tp_px + TICK) if dirn > 0 else (seg2 <= tp_px - TICK)
            a1, a2 = _first(tp2, 0), _first(be_m, 0)
            if a1 != -1 and (a2 == -1 or a1 < a2): exit_rel, kind = k + tt + 1 + a1, "TP"
            elif a2 != -1: exit_rel, kind = k + tt + 1 + a2, "BE"
        elif first != -1:
            exit_rel = k + 1 + first; kind = "TP" if first == m_tp else "SL"
        if exit_rel is None: x = len(P) - 1; px = P[x]; kind = "EOD"
        else:
            x = exit_rel
            px = tp_px if kind == "TP" else (P[x] if G[x] else (sl_px if kind == "SL" else bes))
        out.append((dirn, entry, px, kind, (px - entry) * dirn / TICK, int(T[k]), int(T[x]), kind == "BE"))
        i = x
    return out


def _manage_exit(P, G, k, dirn, entry, sl, tpx, be_trig, be_off):
    """exit after an entry at tick k. Returns (x, px, kind)."""
    tp_px = entry + dirn * tpx; sl_px = entry - dirn * sl
    seg = P[k + 1:]
    tp_hit = (seg >= tp_px + TICK) if dirn > 0 else (seg <= tp_px - TICK)
    sl_hit = (seg <= sl_px) if dirn > 0 else (seg >= sl_px)
    m_tp, m_sl = _first(tp_hit, 0), _first(sl_hit, 0)
    first = min([x for x in (m_tp, m_sl) if x != -1], default=-1)
    if be_trig is not None:
        fav = (P[k:] - entry) * dirn; tt = _first(fav >= be_trig, 0)
        if tt != -1 and (first == -1 or first + 1 > tt):
            bes = entry + dirn * be_off; seg2 = P[k + tt + 1:]
            be_m = (seg2 <= bes) if dirn > 0 else (seg2 >= bes)
            tp2 = (seg2 >= tp_px + TICK) if dirn > 0 else (seg2 <= tp_px - TICK)
            a1, a2 = _first(tp2, 0), _first(be_m, 0)
            if a1 != -1 and (a2 == -1 or a1 < a2): return k + tt + 1 + a1, tp_px, "TP"
            if a2 != -1:
                x = k + tt + 1 + a2; return x, (P[x] if G[x] else bes), "BE"
            return len(P) - 1, P[-1], "EOD"
    if first == -1: return len(P) - 1, P[-1], "EOD"
    x = k + 1 + first
    if first == m_tp: return x, tp_px, "TP"
    return x, (P[x] if G[x] else sl_px), "SL"


def sim_day_breakout(day, hi, lo, cfg):
    """Breakout mode: buy stop above the range high (+offset), sell stop below the range low (-offset).
    mode 'stop'   : enter on the break.
    mode 'retest' : after price breaks `offset` ticks beyond the line, enter with a limit back AT the line.
    One trade per side; the opposite side can still trigger after the first trade ends (max_trades)."""
    P, G, T = day["P"], day["G"], day["T"]
    i = int(np.searchsorted(T, cfg["trade_start"])); end = int(np.searchsorted(T, cfg["trade_end"]))
    if i >= end: return []
    eend = int(np.searchsorted(T, cfg["entry_end"])) if cfg.get("entry_end") else end
    P = P[:end]; G = G[:end]; T = T[:end]
    off = cfg["offset"] * TICK; sl = cfg["sl"] * TICK; tpx = cfg["tp"] * TICK
    bt = cfg["be_trig"] * TICK if cfg.get("be_trig") else None; bo = cfg.get("be_off", 0) * TICK
    used = {1: False, -1: False}; out = []; n = 0
    while i < len(P) and n < cfg["max_trades"]:
        cand = []
        for side in (1, -1):
            if used[side]: continue
            line = hi if side > 0 else lo
            trig = line + side * off
            if cfg["mode"] == "stop":
                # stop order must be placed while price is still inside (below a buy stop)
                inside = (P < trig) if side > 0 else (P > trig)
                a = _first(inside, i)
                if a == -1: continue
                hit = (P >= trig) if side > 0 else (P <= trig)
                f = _first(hit, a + 1)
                if f != -1 and f < eend: cand.append((f, side, P[f] if G[f] else trig))
            else:  # retest
                beyond = (P >= trig) if side > 0 else (P <= trig)
                a = _first(beyond, i)
                if a == -1: continue
                back = (P <= line - TICK) if side > 0 else (P >= line + TICK)     # limit at the line, 1 tick through
                f = _first(back, a + 1)
                if f != -1 and f < eend: cand.append((f, side, line))
        if not cand: break
        k, dirn, entry = min(cand)
        used[dirn] = True; n += 1
        x, px, kind = _manage_exit(P, G, k, dirn, entry, sl, tpx, bt, bo)
        out.append((dirn, entry, px, kind, (px - entry) * dirn / TICK, int(T[k]), int(T[x]), kind == "BE"))
        i = x
    return out
