"""python3 g3.py params.json out.npz - per-day net P&L ($, 10 MNQ) per config."""
import sys, json, time, numpy as np
from multiprocessing import Pool
import sys2
DAYS=None
def _init():
    global DAYS; sys2.init(); DAYS=sorted(sys2.D)
def job(p):
    idx={d:i for i,d in enumerate(DAYS)}; v=np.zeros(len(DAYS),np.float32); n=np.zeros(len(DAYS),np.int16)
    try:
        for d,tk,mult,kind,dirn in sys2.run(p):
            if mult<=0: continue
            q=sys2.QTY*mult; v[idx[d]]+=tk*sys2.TUSD*q-2*sys2.COMM_SIDE*q; n[idx[d]]+=1
    except Exception as e: v[:]=np.nan
    return v,n
if __name__=="__main__":
    P=json.load(open(sys.argv[1])); t=time.time()
    sys2.init(); days=sorted(sys2.D)
    with Pool(4,initializer=_init) as pool: R=pool.map(job,P,chunksize=16)
    np.savez_compressed(sys.argv[2],pnl=np.stack([r[0] for r in R]),n=np.stack([r[1] for r in R]),days=np.array(days),params=np.array([json.dumps(p) for p in P]))
    print("runs",len(R),"secs",round(time.time()-t))
