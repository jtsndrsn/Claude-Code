"""Account-growth plan: $5,000 start, 2 MNQ, +2 MNQ per $1,000 cumulative profit up to 20 MNQ;
then NQ (1 NQ = 10 MNQ): 2 NQ, +1 NQ per further $10,000 profit, max 5 NQ.
Size follows CURRENT cumulative profit (drops back after losses). NQ commission assumed $2.00/side."""
MNQ_T, NQ_T, MNQ_C, NQ_C = 0.5, 5.0, 0.74, 2.00
def size(cum):
    m = 2 + 2 * max(0, int(cum // 1000))
    if m < 20: return ("MNQ", m)
    # 20 MNQ reached at +$9,000 -> 2 NQ; +1 NQ per further $10,000
    nq = 2 + max(0, int((cum - 9000) // 10000))
    return ("NQ", min(5, nq))
def grow(trades, start=5000.0, ratchet=False):
    cum = 0.0; peak_bal = start; dd = 0.0; dd_pct = 0.0; low_bal = start; best = 0.0
    first_nq = None; first_max = None; months = {}
    for d, tk, mult, kind, dirn in trades:
        if mult <= 0: continue
        inst, q = size(best if ratchet else cum)
        q = q * mult
        pnl = tk * (MNQ_T if inst == "MNQ" else NQ_T) * q - 2 * (MNQ_C if inst == "MNQ" else NQ_C) * q
        cum += pnl; best = max(best, cum); bal = start + cum
        if inst == "NQ" and first_nq is None: first_nq = d
        if inst == "NQ" and q >= 5 and first_max is None: first_max = d
        peak_bal = max(peak_bal, bal); dd = max(dd, peak_bal - bal); dd_pct = max(dd_pct, (peak_bal - bal) / peak_bal)
        low_bal = min(low_bal, bal); months[d[:7]] = months.get(d[:7], 0) + pnl
    return dict(end=round(start + cum), profit=round(cum), max_dd=round(dd), max_dd_pct=round(100 * dd_pct, 1),
                lowest=round(low_bal), first_nq=first_nq, first_5nq=first_max,
                losing_months=sum(1 for v in months.values() if v < 0), months=len(months))
