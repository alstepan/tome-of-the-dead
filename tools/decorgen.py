#!/usr/bin/env python3
"""decorgen.py - reference decor deriver for Stage 3B (B3B-9; Z80 = src/decor_gen.asm).

decorate(m, depth, seed, live=True) -> (m', anim)
  m     576 tile ids (rows 0..17 x 32) of a room as build_room_map leaves it
        (structure + potions, before decor)
  anim  ANIM_LIST bytes: n x 4 (AL_COL, AL_ROW, AL_TYPE, AL_PHASE); [] if not live
        (the Z80 only writes ANIM_LIST when building into ROOM_MAP).

D1 REWORK (user + designer 2026-10-05; concept-screen 3.3 "Decor placement (D1)"):
classes decide the row, not rng; order: (1) patch pass, (2) cobweb pass, (3) 12-try
menu loop, (4) drips.  Class rules (storey row r = map row - 9s; row 7 = standing row):
  Mount    torches / windows / banners / bookshelf: top row = storey row 1, T_AIR, cols 1..30
  Ceiling  chain, moss: storey row 0, T_AIR, cols 1..30; the cell above is T_PLAT/T_WALLF
           (chain also at map row 0; moss only map row 9)
  Floor    skulls, candles, cauldron, brazier(s): bottom row = row 7, T_AIR, cols 1..30,
           every cell below the bottom row is T_PLAT / T_WALLF
  Patch    T_WALL_DITHER/PATCH/FADE, PATCH_A/B: NON-solid back wall, T_AIR, cols 2..29,
           rows 1..5 (r0 random)
  Brick    pillar: T_BRICK (unchanged), r0 random
  Cobweb   own pass: corner cells only, see cobwebs()
Every placement: footprint exactly the base tile, no ladder cell and NO other decor in the
1-cell ring (objects never touch), budgets.  Per attempt of the menu loop / patch pass the
4 rnd calls are o, col, s, r0 (r0 = rnd(6 - h), used only by Patch / Brick).

Algorithm (OLD text below is superseded where it says otherwise; Z80 == this file)
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
Entries are emitted per object, row-major; the drips' entries (AL_TYPE = T_DRIP2) come last.
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
T_DRIP1, T_DRIP2 = D["T_DRIP1"], D["T_DRIP2"]
DRIP_TRIES, DRIP_DIST, STOREY = 8, 6, D["STOREY_ROWS"]
DRIP_N = {1: 1, 2: 2, 3: 2, 4: 1, 5: 2, 6: 2, 7: 1, 8: 0}     # per room, by depth
# structural base ids a drip keeps 1 col clear of (whole storey): ladder / hole 4..9, door
# jambs 11 / 14, pit caps .. rubble 19..27 (door arches / planks / lock, grate, rubble)
DRIP_AVOID = frozenset(list(range(T_LAD_L, T_HOLE_R + 1)) + [D["T_DOOR_JAMB_L"], D["T_DOOR_JAMB_R"]]
                       + list(range(D["T_END_L"], D["T_RUBBLE"] + 1)))
MAX_LARGE, MAX_GLYPH, MAX_ATTR, MAX_WALL = 2, 4, 8, 6

# object classes (record wh byte bits 5..7)
C_MOUNT, C_CEIL, C_FLOOR, C_PATCH, C_BRICK, C_COMP = 0, 1, 2, 3, 4, 5
CMIN = {C_MOUNT: 1, C_CEIL: 1, C_FLOOR: 1, C_PATCH: 2, C_BRICK: 0, C_COMP: 2}
CLASS_OF = {"TORCH_TALL": C_MOUNT, "TORCH_SLIM": C_MOUNT, "WINDOW_ARCH": C_MOUNT,
            "WINDOW_BAR": C_MOUNT, "BANNER": C_MOUNT, "BANNER_TALL": C_MOUNT, "BOOKSHELF": C_MOUNT,
            "TORCH_SMALL": C_MOUNT, "CHAIN": C_CEIL, "MOSS": C_CEIL, "SKULLS": C_FLOOR,
            "CANDLES": C_FLOOR, "CAULDRON": C_FLOOR, "BRAZIER": C_FLOOR, "BRAZIER_BIG": C_FLOOR,
            "WALL_DITHER": C_PATCH, "WALL_PATCH": C_PATCH, "WALL_FADE": C_PATCH,
            "PATCH_A": C_PATCH, "PATCH_B": C_PATCH, "PILLAR": C_BRICK}
PATCH_TRIES = 8
MAX_COB = 2
# flags byte of an object record (bit 0 = moss: a ceiling object that needs a floor above)
F_MOSS, F_TILED, F_GROW0, F_GLAST, F_AROW1, F_AALL, F_AT2, F_LARGE = 1, 2, 4, 8, 16, 32, 64, 128

# common objects (all depths): name, base, w, h, flags
COMMON = [
    ("CANDLES", D["T_CANDLES"], 1, 1, F_AALL | F_AT2),
    ("SKULLS", D["T_SKULLS"], 1, 1, 0),
    ("CHAIN", D["T_CHAIN"], 1, 2, F_TILED),
    ("TORCH_SMALL", D["T_TORCH_T"], 1, 2, F_AALL),
    ("WALL_DITHER", D["T_WALL_DITHER"], 1, 1, 0),
    ("WALL_PATCH", D["T_WALL_PATCH"], 1, 1, 0),
    ("WALL_FADE", D["T_WALL_FADE"], 1, 1, 0),
]
COMMON = [o + (CLASS_OF[o[0]],) for o in COMMON]
# D1/D8 have no PATCH_A/B: the patch pass places this 3-cell composite instead
# (PATCH at (row, col), FADE at (row, col+1), DITHER at (row+1, col); the 4th cell of its
# 2 x 2 box must be T_AIR too and is ring-checked, never written).
COMP = ("PATCH3", 0, 2, 2, 0, C_COMP)
COMP_AREA = 3
TILED_OBJ = ("BOOKSHELF", "WINDOW_BAR")
ANIM_FLAGS = {"TORCH_TALL": F_GROW0 | F_AROW1 | F_LARGE, "BRAZIER_BIG": F_GROW0 | F_AROW1 | F_LARGE,
              "TORCH_SLIM": F_GROW0 | F_AROW1 | F_LARGE, "BRAZIER": F_GROW0 | F_LARGE,
              "CAULDRON": F_GLAST | F_LARGE}
COBWEB_R_PLACEHOLDER = False  # COBWEB_R in tileset_ids.inc since 2026-10-05 (tiles_convert mirror)


def level_objects():
    """-> (objects, cobwebs): objects depth -> [(name, base, w, h, flags, cls)] parsed from
    tileset_ids.inc (the single source of the per-level ids), PATCH_A/B first (the patch pass
    indexes them), COBWEB removed; cobwebs depth -> (left id, right id) or None.
    Asserts the id layout the Z80 relies on."""
    objs = {}
    pat = re.compile(r"TS(\d)_([A-Z_]+?)_(?:F(\d)_)?R(\d)C(\d)\s+EQU (\d+)")
    for line in (ROOT / "assets/gfx/tiles/tileset_ids.inc").read_text().splitlines():
        m = pat.match(line)
        if not m:
            continue
        d, name, f, r, c, v = m.groups()
        if name in ("LECTERN", "GLOW"):     # GLOW: B12 exit marker, stamped by the room builder
            continue
        objs.setdefault((int(d), name), {}).setdefault(int(f or 1), {})[(int(r), int(c))] = int(v)
    out = {d: [] for d in range(1, 9)}
    cob = {d: None for d in range(1, 9)}
    for (d, name), fr in objs.items():
        g = fr[1]
        h = max(r for r, c in g) + 1
        w = max(c for r, c in g) + 1
        base = g[(0, 0)]
        if name in ("COBWEB", "COBWEB_R"):
            assert (w, h) == (1, 1)
            cob.setdefault(d, None)
            left, right = cob[d] or (None, None)
            cob[d] = (base, right) if name == "COBWEB" else (left, base)
            continue
        fl = ANIM_FLAGS.get(name, 0)
        if name == "MOSS":
            fl |= F_MOSS
        if name in TILED_OBJ:
            fl |= F_TILED
            assert all(v == base for v in g.values()), (d, name)
        else:
            assert all(g[(r, c)] == base + r * w + c for r in range(h) for c in range(w)), (d, name)
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
        out[d].append((name, base, w, h, fl, CLASS_OF[name]))
    for d in out:
        out[d].sort(key=lambda o: o[0] not in ("PATCH_A", "PATCH_B"))   # stable: patches first
        assert len(out[d]) >= 3          # D5 / D7: 3 since PILLAR made room for GLOW (B12)
    for d, c in list(cob.items()):
        if c and c[1] is None:
            cob[d] = (c[0], c[0])         # COBWEB_R_PLACEHOLDER
    return out, cob


LEVEL, COBWEB = level_objects()
for _o in COMMON:
    assert _o[2] == 1 or not _o[4] & (F_AALL), _o      # attr-all objects are w = 1 (area == h)
RECORDS = COMMON + [o for d in range(1, 9) for o in LEVEL[d]]
PATCHK = {d: sum(1 for o in LEVEL[d] if o[0] in ("PATCH_A", "PATCH_B")) for d in range(1, 9)}
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


def is_decor(t):
    """a tile id the 1-cell ring must not hold (placed decor): chain, skulls, torch, drips,
    candles and everything per-level / wall-set (>= 28)."""
    return t >= 28 or 12 <= t <= 13 or 15 <= t <= 18


def floorish(t):
    return t in (D["T_PLAT"], D["T_WALLF"])


def fits(m, row, col, w, h, cls, fl):
    """footprint exactly the base tile, class support, ring free of ladders and decor."""
    req = T_BRICK if cls == C_BRICK else T_AIR
    if any(m[(row + dy) * COLS + col + dx] != req for dy in range(h) for dx in range(w)):
        return False
    if cls == C_CEIL:
        if row == 0:
            if fl & F_MOSS:
                return False
        elif not floorish(m[(row - 1) * COLS + col]):
            return False
    elif cls == C_FLOOR:
        if not all(floorish(m[(row + h) * COLS + col + dx]) for dx in range(w)):
            return False
    for rr in range(max(row - 1, 0), min(row + h, ROWS - 1) + 1):
        for cc in range(max(col - 1, 0), min(col + w, COLS - 1) + 1):
            t = m[rr * COLS + cc]
            if T_LAD_L <= t <= T_HOLE_R or is_decor(t):
                return False
    return True


class Room:
    """decorate() state: budgets + ANIM list."""
    def __init__(self, m, live):
        self.m, self.live = list(m), live
        self.anim = []
        self.nl = self.ng = self.na = self.nw = 0

    def budget_ok(self, w, h, fl, cls, area):
        dg, da = counts(w, h, fl)
        large = 1 if fl & F_LARGE else 0
        if self.nl + large > MAX_LARGE or self.ng + dg > MAX_GLYPH or self.na + da > MAX_ATTR:
            return False
        if cls in (C_PATCH, C_BRICK, C_COMP) and self.nw + area > MAX_WALL:
            return False
        return True

    def try_place(self, rng, obj, row_of):
        """one attempt: 3 rnd calls (col, s, r0) for the chosen record, then budget, fit, place.
        row_of(s, r0, h) -> map row.  -> True if placed."""
        m = self.m
        name, base, w, h, fl, cls = obj
        cmin = CMIN[cls]
        col = cmin + rng.rnd(33 - w - 2 * cmin)
        s = rng.rnd(2)
        r0 = rng.rnd(6 - h)
        if cls in (C_PATCH, C_BRICK, C_COMP):
            row = 9 * s + 1 + r0
        elif cls == C_MOUNT:
            row = 9 * s + 1
        elif cls == C_CEIL:
            row = 9 * s
        else:
            row = 9 * s + 8 - h
        area = COMP_AREA if cls == C_COMP else w * h
        if not self.budget_ok(w, h, fl, cls, area) or not fits(m, row, col, w, h, cls, fl):
            return False
        ph = (col + row) & 7
        if cls == C_COMP:
            m[row * COLS + col] = D["T_WALL_PATCH"]
            m[row * COLS + col + 1] = D["T_WALL_FADE"]
            m[(row + 1) * COLS + col] = D["T_WALL_DITHER"]
            self.nw += COMP_AREA
            return True
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
                if typ and self.live:
                    self.anim += [col + dx, row + dy, typ, ph]
        dg, da = counts(w, h, fl)
        self.nl += 1 if fl & F_LARGE else 0
        self.ng += dg
        self.na += da
        self.nw += area if cls in (C_PATCH, C_BRICK) else 0
        return True


def patch_pass(room, rng, depth):
    """(1) >= 1 back-wall patch (up to PATCH_TRIES attempts of 4 rnd calls, first legal wins),
    then a 2nd with 50 % (rnd(2) == 0, same loop; the <= 6 patch-cell budget decides)."""
    k = PATCHK[depth]
    pats = LEVEL[depth][:k] if k else [COMP]
    for n in range(2):
        if n and rng.rnd(2):
            break
        for _ in range(PATCH_TRIES):
            obj = pats[rng.rnd(len(pats))]
            if room.try_place(rng, obj, None):
                break


def cobwebs(room, rng, depth):
    """(2) levels with a COBWEB: corner candidates scanned storey 0 then 1, cols 1..30; each
    takes one rnd(2) and is placed on 0; <= MAX_COB per room.  A candidate: (9s, c) T_AIR,
    ceiling above (map row 0, or T_PLAT / T_WALLF), col c-1 (left corner, glyph = left id)
    or else col c+1 (right corner) T_BRICK in storey rows 0..2, ring free of ladders / decor."""
    ids = COBWEB[depth]
    if not ids:
        return
    m = room.m
    n = 0
    for s in range(2):
        row = 9 * s
        for c in range(1, COLS - 1):
            if m[row * COLS + c] != T_AIR:
                continue
            if row and not floorish(m[(row - 1) * COLS + c]):
                continue
            if all(m[(row + k) * COLS + c - 1] == T_BRICK for k in range(3)):
                gid = ids[0]
            elif all(m[(row + k) * COLS + c + 1] == T_BRICK for k in range(3)):
                gid = ids[1]
            else:
                continue
            if not fits(m, row, c, 1, 1, C_COMP + 1, 0) or rng.rnd(2):
                continue
            m[row * COLS + c] = gid
            n += 1
            if n == MAX_COB:
                return


def decorate(m, depth, seed, live=True):
    rng = Rng(seed)
    room = Room(m, live)
    patch_pass(room, rng, depth)
    cobwebs(room, rng, depth)
    mn = menu(depth)
    for _ in range(TRIES):
        o = mn[rng.rnd(len(mn))]
        room.try_place(rng, o, None)
    drips(room.m, depth, rng, room.anim, room.ng, live)
    return room.m, room.anim


def drips(m, depth, rng, anim, ng, live):
    """B3B-13b (concept-screen 3.3 "Drip placement"), mirror of dg_drips. After the decor:
    DRIP_N[depth] drips, each skipped if the room holds 4 glyph-swap cells already. A drip =
    <= 8 attempts of exactly 3 rnd calls (col = rnd 32, storey = rnd 2, storey row = rnd 3),
    stopping at the first that fits: map row >= 1, cell T_AIR, above T_PLAT/T_BRICK/T_WALLF
    (ids 1..3), below T_AIR, no DRIP_AVOID id in cols col-1..col+1 of the whole storey, >= 6
    cols from an earlier drip. Map keeps T_DRIP1; AL_TYPE = T_DRIP2, AL_PHASE (col+row)&7.
    (Spawns stand on floors, never in storey rows 0..2: no test.)"""
    cols = []
    for _ in range(DRIP_N[depth]):
        if ng >= MAX_GLYPH:
            continue
        for _ in range(DRIP_TRIES):
            col = rng.rnd(32)
            s = rng.rnd(2)
            row = STOREY * s + rng.rnd(3)
            if row == 0:
                continue
            j = row * COLS + col
            if m[j] != T_AIR or not T_AIR < m[j - COLS] <= 3 or m[j + COLS] != T_AIR:
                continue
            if any(abs(col - c) < DRIP_DIST for c in cols):
                continue
            if any(m[rr * COLS + cc] in DRIP_AVOID for rr in range(STOREY * s, STOREY * s + STOREY)
                   for cc in range(max(col - 1, 0), min(col + 1, COLS - 1) + 1)):
                continue
            m[j] = T_DRIP1
            ng += 1
            cols.append(col)
            if live:
                anim += [col, row, T_DRIP2, (col + row) & 7]
            break


def emit_asm():
    out = ["; GENERATED by tools/decorgen.py --asm (edit the tool, re-run, paste)",
           "; record (3 B): base id | w + h*4 + class*32 | flags (bit0 moss, 1 tiled, 2 glyph row 0, 3 glyph last",
           ";                 col, 4 attr row 1, 5 attr all, 6 attr type 2, 7 large animated)",
           "; class 0 mount, 1 ceiling, 2 floor, 3 patch, 4 brick, 5 composite patch",
           "dg_start:       ; first per-level record of depth 1..8, then the end"]
    out.append("                DEFB " + ", ".join(str(LEVEL_FIRST[d]) for d in range(1, 10)))
    out.append("dg_pk:          ; PATCH_A/B records at the head of each level's records (0 = composite)")
    out.append("                DEFB " + ", ".join(str(PATCHK[d]) for d in range(1, 9)))
    out.append("dg_cob:         ; COBWEB left / right corner id per depth (0 = none)"
               + ("; COBWEB_R_PLACEHOLDER: right id = left id until the artist adds COBWEB_R" if COBWEB_R_PLACEHOLDER else ""))
    for d in range(1, 9):
        l, r = COBWEB[d] or (0, 0)
        out.append(f"                DEFB {l:3d}, {r:3d}")
    bad = [1 if (T_LAD_L <= t <= T_HOLE_R or is_decor(t)) else 0 for t in range(64)]
    out.append("                ALIGN 64                   ; dg_ring's lookup: 1 = ladder / hole / decor id (never crosses a page)")
    out.append("dg_bad:")
    for k in range(0, 64, 16):
        out.append("                DEFB " + ", ".join(str(v) for v in bad[k:k + 16]))
    out.append("dg_crec:        ; the composite patch record (D1 / D8)")
    out.append(f"                DEFB 0, {COMP[2] + COMP[3] * 4 + COMP[5] * 32}, 0")
    out.append("dg_recs:")
    for i, (name, base, w, h, fl, cls) in enumerate(RECORDS):
        tag = f"{i:2d} " + ("common " if i < len(COMMON) else f"D{[d for d in range(1, 9) if LEVEL_FIRST[d] <= i < LEVEL_FIRST[d+1]][0]} ") + name
        out.append(f"                DEFB {base:3d}, {w + h * 4 + cls * 32:3d}, ${fl:02X}      ; {tag}")
    out.append(f"DG_NCOM         EQU {len(COMMON)}")
    out.append(f"DG_NREC         EQU {len(RECORDS)}")
    return "\n".join(out)


if __name__ == "__main__":
    if "--asm" in sys.argv:
        print(emit_asm())
    else:
        print(f"{len(RECORDS)} records, menu sizes " + ", ".join(
            f"D{d}={len(menu(d))}" for d in range(1, 9)))
