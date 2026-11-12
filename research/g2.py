"""python3 g2.py params.json out.json  - runs sys2.job over a list of param dicts on 4 processes."""
import sys, json, time
from multiprocessing import Pool
import sys2
def _init(): sys2.init()
if __name__ == "__main__":
    P = json.load(open(sys.argv[1])); t = time.time()
    with Pool(4, initializer=_init) as pool:
        R = pool.map(sys2.job, P, chunksize=16)
    for r in R:
        for k, v in list(r.items()):
            if hasattr(v, "item"): r[k] = v.item()
    json.dump(R, open(sys.argv[2], "w"))
    print("runs", len(R), "secs", round(time.time() - t), "errors", sum(1 for r in R if "err" in r))
