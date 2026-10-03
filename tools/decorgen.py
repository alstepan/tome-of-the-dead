#!/usr/bin/env python3
"""decorgen.py - reference decor deriver for Stage 3B (B3B-9; Z80 = src/decor_gen.asm).

decorate(m, depth, seed, live=True) -> (m', anim)
  m     576 tile ids (rows 0..17 x 32) of a room as build_room_map leaves it
        (structure + potions, before decor)
  anim  ANIM_LIST bytes: n x 4 (AL_COL, AL_ROW, AL_TYPE, AL_PHASE); [] if not live
        (the Z80 only writes ANIM_LIST when building into ROOM_MAP).

Algorithm (all of it must match decor_room byte-for-byte)
---------------------------------------------------------
RNG: private 16-bit xorshift 7,9,8 (same step as levelgen's GEN_RNG, own state
x = RD_SEED; never GEN_RNG / RNG_STATE), rnd(n) = step, then (x & $FF) mod n.
Menu = 7 common objects + the depth's per-level objects (tileset_ids.inc order).
TRIES = 12 attempts; EVERY attempt makes exactly 4 rnd calls, in this order,
whether or not it places anything:
    o   = rnd(N)                       menu index
    col = cmin + rnd(33 - w - 2*cmin)  cmin = 0 wall-class, 1 air-class
    s   = rnd(2)
    r0  = rmin + rnd(7 - h - rmin)     rmin = 1 wall-class, 0 air-class
    row = 9*s + r0                     (so the object sits in rows 9s..9s+5:
                                        never the 2 rows above a floor)
Then (no more rng): reject if the budgets would be exceeded (large animated
objects <= 2, glyph-swap cells <= 4, attr-cycle cells <= 8, wall-class cells
<= 6); reject unless every footprint cell is exactly the base tile (T_AIR for
air-class, T_BRICK for wall-class: so never door / arch / lintel / jamb /
ladder / pit / cap / rubble / potion cells, and wall decor never touches a
passage) and no in-bounds cell of the 1-cell ring around the footprint is a
ladder cell (T_LAD_L..T_HOLE_R).  Placed objects are row-major ids
base + dy*w + dx (tiled: all base).  Solidity follows the cell class: wall-class
ids go on T_BRICK only, air-class on T_AIR only (designer, game.md 1.2).

ANIM_LIST contract for B3B-10 (AL_TYPE): 1 .. 15 = attr cycle kind (1 flame
$46 -> $42 -> $06, 2 candle); >= 16 = glyph swap, the value is the ALTERNATE
tile id (the map keeps frame 1; decor_tick toggles map id <-> AL_TYPE).
AL_PHASE = (col + row) & 7 of the object's top-left (an object swaps in step).
Entries are emitted per object, row-major.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import levelgen as G  # noqa: E402

D = G.D
ROOT = G.ROOT
TRIES = 12
ROWS, COLS = D["PLAY_ROWS"], 32
T_AIR, T_BRICK = D["T_AIR"], D["T_BRICK"]
T_LAD_L, T_HOLE_R = D["T_LAD_L"], D["T_HOLE_R"]
MAX_LARGE, MAX_GLYPH, MAX_ATTR, MAX_WALL = 2, 4, 8, 6

# flags byte of an object record
F_WALL, F_TILED, F_GROW0, F_GLAST, F_AROW1, F_AALL, F_AT2, F_LARGE = 1, 2, 4, 8, 16, 32, 64, 128

# common objects (all depths): name, base, w, h, flags
COMMON = [
    ("CANDLES", D["T_CANDLES"], 1, 1, F_AALL | F_AT2),
    ("SKULLS", D["T_SKULLS"], 1, 1, 0),
    ("CHAIN", D["T_CHAIN"], 1, 2, F_TILED),
    ("TORCH_SMALL", D["T_TORCH_T"], 1, 2, F_AALL),
    ("WALL_DITHER", D["T_WALL_DITHER"], 1, 1, F_WALL),
    ("WALL_PATCH", D["T_WALL_PATCH"], 1, 1, F_WALL),
    ("WALL_FADE", D["T_WALL_FADE"], 1, 1, F_WALL),
]
# (T_DRIP1/2 are left out until B3B-13: ids 17/18 still hold the PROTO zap glyphs.)
WALL_OBJ = ("PILLAR", "PATCH_A", "PATCH_B")
TILED_OBJ = ("BOOKSHELF", "WINDOW_BAR")
ANIM_FLAGS = {"TORCH_TALL": F_GROW0 | F_AROW1 | F_LARGE, "BRAZIER_BIG": F_GROW0 | F_AROW1 | F_LARGE,
              "TORCH_SLIM": F_GROW0 | F_AROW1 | F_LARGE, "BRAZIER": F_GROW0 | F_LARGE,
              "CAULDRON": F_GLAST | F_LARGE}


def level_objects():
    """depth -> [(name, base, w, h, flags)] parsed from tileset_ids.inc (the single
    source of the per-level ids); asserts the id layout the Z80 relies on."""
    objs = {}
    pat = re.compile(r"TS(\d)_([A-Z_]+?)_(?:F(\d)_)?R(\d)C(\d)\s+EQU (\d+)")
    for line in (ROOT / "assets/gfx/tiles/tileset_ids.inc").read_text().splitlines():
        m = pat.match(line)
        if not m:
            continue
        d, name, f, r, c, v = m.groups()
        if name == "LECTERN":
            continue
        objs.setdefault((int(d), name), {}).setdefault(int(f or 1), {})[(int(r), int(c))] = int(v)
    out = {d: [] for d in range(1, 9)}
    for (d, name), fr in objs.items():
        g = fr[1]
        h = max(r for r, c in g) + 1
        w = max(c for r, c in g) + 1
        base = g[(0, 0)]
        fl = ANIM_FLAGS.get(name, 0)
        if name in WALL_OBJ:
            fl |= F_WALL
        if name in TILED_OBJ:
            fl |= F_TILED
            assert all(v == base for v in g.values()), (d, name)
        else:
            assert all(g[(r, c)] == base + r * w + c for r in range(h) for c in range(w)), (d, name)
        if fl & F_AALL or fl & F_LARGE:
            pass
        if 2 in fr:                       # glyph frames: alt = base + area + k (k-th swapped cell)
            diff = [(r, c) for (r, c) in sorted(g) if fr[2][(r, c)] != g[(r, c)]]
            assert all(r == 0 for r, c in diff), (d, name)
            assert [fr[2][k] for k in diff] == [base + w * h + k for k in range(len(diff))], (d, name)
            want = w if fl & F_GROW0 else 1
            assert len(diff) == want, (d, name, diff)
            if fl & F_GLAST:
                assert diff == [(0, w - 1)], (d, name)
        else:
            assert not fl & (F_GROW0 | F_GLAST), (d, name)
        if fl & F_AROW1:
            assert h >= 2
        out[d].append((name, base, w, h, fl))
    for d in out:
        assert len(out[d]) >= 4
    return out


LEVEL = level_objects()
for _o in COMMON:
    assert _o[2] == 1 or not _o[4] & (F_AALL), _o      # attr-all objects are w = 1 (area == h)
RECORDS = COMMON + [o for d in range(1, 9) for o in LEVEL[d]]
LEVEL_FIRST = {}
_i = len(COMMON)
for _d in range(1, 9):
    LEVEL_FIRST[_d] = _i
    _i += len(LEVEL[_d])
LEVEL_FIRST[9] = _i                       # end sentinel


def menu(depth):
    return COMMON + LEVEL[depth]


class Rng:
    def __init__(self, seed):
        self.x = seed or 1

    def rnd(self, n):
        x = self.x
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        self.x = x
        return (x & 0xFF) % n


def counts(w, h, fl):
    """(glyph cells, attr cells) an object adds to the room budgets."""
    area = w * h
    g = w if fl & F_GROW0 else (1 if fl & F_GLAST else 0)
    a = (w if fl & F_AROW1 else 0) + (area if fl & F_AALL else 0)
    return g, a


def decorate(m, depth, seed, live=True):
    m = list(m)
    anim = []
    rng = Rng(seed)
    mn = menu(depth)
    nl = ng = na = nw = 0
    for _ in range(TRIES):
        name, base, w, h, fl = mn[rng.rnd(len(mn))]
        wall = fl & F_WALL
        cmin, rmin = (0, 1) if wall else (1, 0)
        col = cmin + rng.rnd(33 - w - 2 * cmin)
        s = rng.rnd(2)
        row = 9 * s + rmin + rng.rnd(7 - h - rmin)
        area = w * h
        dg, da = counts(w, h, fl)
        large = 1 if fl & F_LARGE else 0
        if nl + large > MAX_LARGE or ng + dg > MAX_GLYPH or na + da > MAX_ATTR:
            continue
        if wall and nw + area > MAX_WALL:
            continue
        req = T_BRICK if wall else T_AIR
        ok = True
        for rr in range(row - 1, row + h + 1):
            for cc in range(col - 1, col + w + 1):
                if not (0 <= rr < ROWS and 0 <= cc < COLS):
                    continue
                t = m[rr * COLS + cc]
                if row <= rr < row + h and col <= cc < col + w:
                    ok &= t == req
                else:
                    ok &= not T_LAD_L <= t <= T_HOLE_R
        if not ok:
            continue
        ph = (col + row) & 7
        alt = base + area
        i = base
        for dy in range(h):
            for dx in range(w):
                m[(row + dy) * COLS + col + dx] = i
                if not fl & F_TILED:
                    i += 1
                typ = 0
                if dy == 0 and (fl & F_GROW0 or (fl & F_GLAST and dx == w - 1)):
                    typ, alt = alt, alt + 1
                elif dy == 1 and fl & F_AROW1 or fl & F_AALL:
                    typ = 2 if fl & F_AT2 else 1
                if typ and live:
                    anim += [col + dx, row + dy, typ, ph]
        nl += large
        ng += dg
        na += da
        nw += area if wall else 0
    return m, anim


def emit_asm():
    out = ["; GENERATED by tools/decorgen.py --asm (edit the tool, re-run, paste)",
           "; record (3 B): base id | w + h*4 | flags (bit0 wall, 1 tiled, 2 glyph row 0, 3 glyph last col,",
           ";                 4 attr row 1, 5 attr all, 6 attr type 2, 7 large animated)",
           "dg_start:       ; first per-level record of depth 1..8, then the end"]
    out.append("                DEFB " + ", ".join(str(LEVEL_FIRST[d]) for d in range(1, 10)))
    out.append("dg_recs:")
    for i, (name, base, w, h, fl) in enumerate(RECORDS):
        tag = f"{i:2d} " + ("common " if i < len(COMMON) else f"D{[d for d in range(1, 9) if LEVEL_FIRST[d] <= i < LEVEL_FIRST[d+1]][0]} ") + name
        out.append(f"                DEFB {base:3d}, {w + h * 4:3d}, ${fl:02X}      ; {tag}")
    out.append(f"DG_NCOM         EQU {len(COMMON)}")
    out.append(f"DG_NREC         EQU {len(RECORDS)}")
    return "\n".join(out)


if __name__ == "__main__":
    if "--asm" in sys.argv:
        print(emit_asm())
    else:
        print(f"{len(RECORDS)} records, menu sizes " + ", ".join(
            f"D{d}={len(menu(d))}" for d in range(1, 9)))
