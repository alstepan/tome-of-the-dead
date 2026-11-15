#!/usr/bin/env python3
"""B3B-6: generator determinism + invariants over 1000 seeds x depths 1..8 (LARGER-D: 3 x 4 grid, ids 0..11).
H1 (try_climb .x0 / .xs, bank7.asm): the no-step exit from an arrival end and the exit dest
r -/+ 3 rely on RD_UPCOL(r) == RD_DNCOL(r - 3) with both exit bits set, and on no top-row room
having an up exit (a dest above the grid = the D1 entrance shaft, never an exit). Checked here
explicitly on the same seeds (plain and f3); tests/levelgen_z80.py compares the Z80 block
byte-exact with this model, so the invariant carries to the game."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelcheck
import levelgen as G
from levelcheck import rd, D


def h1_links(nseeds=1000, dmax=8):
    bad = []
    n = 0
    for f3 in (False, True):
        for depth in range(1, dmax + 1):
            for i in range(nseeds):
                seed = (i * 0x9E37 + depth * 0x3D) & 0xFFFF or 1
                b = G.generate(depth, seed, f3=f3)
                for r in range(G.NCELL):
                    if not rd(b, r, "RD_FLAGS") & 1:
                        continue
                    ex = rd(b, r, "RD_EXITS")
                    if ex & D["RDX_U"]:
                        n += 1
                        if r < 3:
                            bad.append((f3, depth, seed, r, "up exit in a top-row room"))
                        elif not (rd(b, r - 3, "RD_EXITS") & D["RDX_D"]
                                  and rd(b, r - 3, "RD_DNCOL") == rd(b, r, "RD_UPCOL") != 0):
                            bad.append((f3, depth, seed, r, "RD_UPCOL(r) != RD_DNCOL(r-3)"))
                    if ex & D["RDX_D"] and (r >= G.BOT or not rd(b, r + 3, "RD_EXITS") & D["RDX_U"]):
                        bad.append((f3, depth, seed, r, "down exit without the up exit below"))
    print(f"H1 vertical links: {n} up exits checked, {len(bad)} bad {bad[:4]}")
    return 1 if bad else 0


# K11 (larger_depths.md 2.1 rev 3): the GEN_RNG draw count per seed (the branch draw `b` in the DFS included) and the final
# GEN_RNG state are pinned; T4's Z80 port must reproduce both. (depth, seed, rnd calls, restarts, final GEN_RNG)
K11 = [(1, 4660, 208, 0, 37201), (2, 3855, 493, 1, 30998), (4, 30583, 400, 0, 19643), (5, 48879, 417, 0, 54893),
       (7, 66, 401, 0, 61521), (8, 40503, 416, 0, 21507), (8, 10794, 493, 0, 28051), (3, 49374, 260, 0, 10104)]


def k11():
    bad = []
    for d, sd, calls, rs, x in K11:
        b = G.generate(d, sd)
        got = (G.LAST[1], G.LAST[0], int.from_bytes(b[G.LH["GEN_RNG"]:G.LH["GEN_RNG"] + 2], "little"))
        if got != (calls, rs, x):
            bad.append((d, sd, got, (calls, rs, x)))
    print(f"K11 draw counts: {len(K11) - len(bad)}/{len(K11)} pinned seeds match {bad[:3]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(levelcheck.run(1000, 8) | h1_links() | k11())
