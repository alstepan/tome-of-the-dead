#!/usr/bin/env python3
"""B3B-12 review: per depth, the seeds whose generation fails (no lair / restart
cap) and the longest run of consecutive failing seeds over all 65,536 (16-bit
wrap). level_gen fails (B = 1) only if 16 consecutive seeds fail; level_new
then retries from seed + 16, so it needs a run < 32 to finish in <= 2 calls.
Measured 2026-10-04: D1-D7 0 failing seeds; D8 41,096 failing, longest run 18.
After L1 (2026-10-05, lair always on the bottom row): 0 failing seeds at every depth.
Usage: python3 tools/levelgen_runs.py   (~10 s on 8 cores)
"""
import os
import sys
import multiprocessing as mp
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "tools")
import levelgen as G
def fails(depth, s):
    rng = G.Rng(s, depth)
    try:
        for _ in range(G.MAX_RESTARTS):
            try:
                G.attempt(rng, depth); return False
            except G.Restart:
                pass
        return True
    except G.Reseed:
        return True
def scan(d):
    f = [fails(d, s) for s in range(65536)]
    best = run = 0
    for x in f + f:                       # wraparound
        run = run + 1 if x else 0
        best = max(best, min(run, 65536))
    return d, sum(f), best
if __name__ == "__main__":
    with mp.Pool(8) as p:
        for d, n, best in p.map(scan, range(1, 9)):
            print(f"D{d}: failing seeds {n}, longest run of consecutive failing seeds {best}", flush=True)
