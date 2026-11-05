#!/usr/bin/env python3
"""decor_sweep.py - MEM-RECLAIM w2a: count the decor tiles the generator places, per depth.

Runs tools/levelgen.py generate() + tests/room_model.py render_room() (which calls the
tools/decorgen.py deriver, == Z80 decor_room by world.py W13) over N seeds x 8 depths and
counts, for every per-level object of assets/gfx/tiles/tileset_ids.inc, how many rooms
placed it (frame-1 ids in ROOM_MAP; frame-2 ids reached through ANIM_LIST glyph swaps;
GLOW through render_room's open-exit pass, here forced open). Prints every object with ZERO
placements: the dead-art candidates.  Needs a build (game_lib reads build/tome-of-the-dead.sym).

    python3 tools/decor_sweep.py [seeds=2000]
"""
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "tools"))
import levelgen as G            # noqa: E402
import room_model as RM         # noqa: E402
from game_lib import S          # noqa: E402

COMMON_DECOR = {S[k]: k for k in ("T_CHAIN", "T_WALL_DITHER", "T_WALL_PATCH", "T_WALL_FADE")}
PAT = re.compile(r"TS(\d)_([A-Z_]+?)_(?:F(\d)_)?R(\d)C(\d)\s+EQU (\d+)")


def objects():
    """depth -> {id: object name} for ids 32..59 (+ the frame of each id)."""
    out = defaultdict(dict)
    for line in open(os.path.join(REPO, "assets/gfx/tiles/tileset_ids.inc")):
        m = PAT.match(line)
        if m:
            d, name, f, _r, _c, v = m.groups()
            if name != "LECTERN":               # ids 60..63 = floor items; T6 swaps it in
                out[int(d)][int(v)] = name
    return out


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 2000
    obj = objects()
    hits = {d: defaultdict(int) for d in range(1, 9)}
    rooms = defaultdict(int)
    idhit = {d: defaultdict(int) for d in range(1, 9)}
    common = {d: defaultdict(int) for d in range(1, 9)}
    off = S["LVL_FLAGS"] - RM.BASE
    for d in range(1, 9):
        for seed in range(1, n + 1):
            blk = bytearray(G.generate(d, seed * 7919 & 0xFFFF or 1))
            blk[off] |= S["LF_GRATE_OPEN"]          # the open exit (+ GLOW) after the boss dies
            for r in range(9):                      # the 3 x 3 room grid (levelgen)
                o = RM.OFF_DESC + r * S["RD_STRIDE"]
                if not blk[o + S["RD_FLAGS"]] & S["RDF_PRESENT"]:
                    continue
                al = []
                m = RM.render_room(bytes(blk), r, anim=al)
                rooms[d] += 1
                seen = {t for t in m if 32 <= t < 60}
                for t in m:
                    if t in COMMON_DECOR:
                        common[d][t] += 1
                for k in range(0, len(al), 4):      # glyph swaps: AL_TYPE >= 16 = alternate id
                    if al[k + 2] >= 16:
                        seen.add(al[k + 2])
                names = {obj[d][t] for t in seen if t in obj[d]}
                for t in seen:
                    idhit[d][t] += 1
                for nm in names:
                    hits[d][nm] += 1
                for t in seen - set(obj[d]):
                    hits[d][f"?id{t}"] += 1
    dead = []
    for d in range(1, 9):
        allnames = sorted(set(obj[d].values()))
        row = ", ".join(f"{nm} {hits[d][nm]}" for nm in allnames)
        print(f"D{d} ({rooms[d]} rooms): {row}")
        for nm in allnames:
            if not hits[d][nm]:
                ids = sorted(t for t, v in obj[d].items() if v == nm)
                dead.append((d, nm, ids))
        for t in sorted(obj[d]):
            if not idhit[d][t] and obj[d][t] not in [x[1] for x in dead if x[0] == d]:
                dead.append((d, f"{obj[d][t]} (single id)", [t]))
        for t in COMMON_DECOR:
            if not common[d][t]:
                dead.append((d, f"common {COMMON_DECOR[t]}", [t]))
    print("ZERO placements:", "; ".join(f"D{d} {nm} ids {ids}" for d, nm, ids in dead) or "none")


if __name__ == "__main__":
    main(sys.argv)
