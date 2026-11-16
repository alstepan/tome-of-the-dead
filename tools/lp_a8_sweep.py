#!/usr/bin/env python3
"""LARGER-D T7: levelgen sweep for tests/lp.py A8S / A8R fixtures (pure Python, no emulator).

A8S fixture (depth, seed, X, s0, x0): room X's 4 entries (the depth's widest kind) carry the LP_POS cell
(s0, x0) on a storey with NO free window, the hero arrives (x 1, width 3) on the other storey: try 0 fails
for every unit, the FIRST unit's slide scans the whole storey and fails (it spends the slide budget), and
all 4 units spend 8 stream tries each (LP_CALLS == 32, none placed).
A8R fixture (depth, seed, r, s0, x0, x1): room r has 2 entries (widest kind) with saved cells (s0, x0),
(s0, x1): unit 0's slide fails ONLY because unit 1's saved cell is reserved (it succeeds without the
reservation), unit 1 comes back exactly at x1.

usage: tools/lp_a8_sweep.py a8s [depth] | a8r [depth]   (prints candidate tuples, first 12)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import levelgen as G                                    # noqa: E402

L = G.L
HX, HW = 1, 3


def setup(depth, seed):
    blk = G.generate(depth, seed, f3=True)
    lp = bytearray(G.lp_budget(blk, f3=True))
    kinds = [lp[G.lp_off("LP_KINDS") + i] for i in range(8)]
    k = max(kinds, key=lambda q: G.k3_info(q)[0])      # the widest kind of the depth (first on ties)
    return blk, lp, k


def a8s(depth, seeds):
    hits = []
    for seed in seeds:
        blk, lp0, k = setup(depth, seed)
        w, _, fly = G.k3_info(k)
        hp = G.k3_hp(k, depth)
        st, lair, sanct = (blk[G.LH[n]] for n in ("LVL_START", "LVL_LAIR", "LVL_SANCTUM"))
        rooms = [r for r in range(G.NCELL) if G._rd(blk, r, "RD_FLAGS") & L["RDF_PRESENT"]
                 and r not in (st, lair, sanct)]
        for X in rooms:
            for s0 in (0, 1):
                x0 = 2
                lp = bytearray(lp0)
                ro = G.lp_off("LP_REC") + X * L["LR_STRIDE"]
                po = G.lp_off("LP_POS") + X * L["LR_MAX"]
                lp[ro] = L["LR_VISITED"] | 4
                for i in range(4):
                    lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i] = k, hp
                    lp[po + i] = G.lp_pos_byte(x0, s0, False, 1 if fly else None)
                seen = []
                orig = G._slide

                def spy(*a, **kw):
                    res = orig(*a, **kw)
                    seen.append(a[11][0])              # lp_slide passes its scan flag as the 12th argument
                    return res
                G._slide = spy
                try:
                    _, out = G.lp_enter(blk, bytes(lp), X, 1 - s0, HX, HW, f3=True, parked=[])
                finally:
                    G._slide = orig
                if not out and G.LP_CALLS == 32 and seen and seen[0]:
                    hits.append((depth, seed, X, s0, x0))
    return hits


def a8r(depth, seeds):
    hits = []
    for seed in seeds:
        blk, lp0, k = setup(depth, seed)
        w, _, fly = G.k3_info(k)
        st, lair, sanct = (blk[G.LH[n]] for n in ("LVL_START", "LVL_LAIR", "LVL_SANCTUM"))
        for r in range(G.NCELL):
            if not G._rd(blk, r, "RD_FLAGS") & L["RDF_PRESENT"] or r in (st, lair, sanct):
                continue
            for s0 in (0, 1):
                for x0 in (2, 5):
                    for x1 in range(2, 28):
                        if abs(x1 - x0) < w:
                            continue
                        lp = bytearray(lp0)
                        ro = G.lp_off("LP_REC") + r * L["LR_STRIDE"]
                        po = G.lp_off("LP_POS") + r * L["LR_MAX"]
                        lp[ro] = L["LR_VISITED"] | 2
                        for i, x in enumerate((x0, x1)):
                            lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i] = k, 5
                            lp[po + i] = G.lp_pos_byte(x, s0, False, 1 if fly else None)
                        hs = 1 - s0
                        _, out = G.lp_enter(blk, bytes(lp), r, hs, HX, HW, f3=True, parked=[])
                        if not any(o[2] == s0 and o[3] == x1 for o in out):
                            continue
                        # unit 0 must fail ONLY because of the reservation: slide with no reservation works
                        placed = []
                        free = G.lp_slide(blk, r, s0, x0, w, fly, hs, HX, HW, placed, L["LP_GAP2"], [0])
                        t0 = G.lp_legal(blk, r, s0, x0, w, fly, hs, HX, HW, placed, L["LP_GAP2"], ret=True)
                        rsv = [(s0, x1, x1 + w - 1)]
                        held = G.lp_slide(blk, r, s0, x0, w, fly, hs, HX, HW, placed + rsv, L["LP_GAP2"], [0])
                        if t0 != "ok" and free is not None and held is None:
                            hits.append((depth, seed, r, s0, x0, x1))
    return hits


if __name__ == "__main__":
    mode = sys.argv[1]
    depths = [int(sys.argv[2])] if len(sys.argv) > 2 else ([7, 6, 5] if mode == "a8s" else [1])
    n = 0
    for d in depths:
        hs = (a8s if mode == "a8s" else a8r)(d, range(1, 600))
        for h in hs[:12]:
            print(h, flush=True)
        n += len(hs)
        print(f"depth {d}: {len(hs)} candidates", flush=True)
