#!/usr/bin/env python3
"""B3B-6: generator determinism + invariants over 1000 seeds x depths 1..8.
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
                for r in range(9):
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
                    if ex & D["RDX_D"] and (r >= 6 or not rd(b, r + 3, "RD_EXITS") & D["RDX_U"]):
                        bad.append((f3, depth, seed, r, "down exit without the up exit below"))
    print(f"H1 vertical links: {n} up exits checked, {len(bad)} bad {bad[:4]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(levelcheck.run(1000, 8) | h1_links())
