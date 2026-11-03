#!/usr/bin/env python3
"""decorgen.py - reference decor deriver for Stage 3B (B3B-9; Z80 = src/decor_gen.asm).

decorate(m, depth, seed, live=True) -> (m', anim)
  m     576 tile ids (rows 0..17 x 32) of a room as build_room_map leaves it
        (structure + potions, before decor)
  anim  ANIM_LIST bytes: n x 4 (AL_COL, AL_ROW, AL_TYPE, AL_PHASE); [] if not live
        (the Z80 only writes ANIM_LIST when building into ROOM_MAP).

D1 REWORK (user + designer 2026-10-05; concept-screen 3.3 "Decor placement (D1)"):
classes decide the row, not rng; order: (1) patch pass, (2) cobweb pass, (3) 12-try
menu loop (D3-7 T6: the drips removed; DEC2: the bones pass and the cauldron removed).  Class rules (storey row r = map row - 9s; row 7 = standing row):
  Mount    torches / windows / banners / bookshelf: top row = storey row 1, T_AIR, cols 1..30
  Ceiling  chain, moss: storey row 0, T_AIR, cols 1..30; the cell above is T_PLAT/T_WALLF
           (chain also at map row 0; moss only map row 9)
  Floor    brazier(s): bottom row = row 7, T_AIR, cols 1..30,
           every cell below the bottom row is T_PLAT / T_WALLF
  Patch    T_WALL_DITHER/PATCH/FADE, PATCH_A/B: NON-solid back wall, T_AIR, cols 2..29,
           rows 1..5 (r0 random)
  Brick    pillar: T_BRICK (unchanged), r0 random
  Cobweb   own pass: corner cells only, see cobwebs()
NO DECOR ON WALLS (user 2026-10-12): every footprint is T_AIR; the brick class (PILLAR) is
dropped from the menu (the Z80's DC_BRICK paths are unreachable: no record uses them).
Every placement: footprint exactly the base tile, no ladder cell and NO other decor in the
1-cell ring (objects never touch), budgets.  Per attempt of the menu loop / patch pass the
4 rnd calls are o, col, s, r0 (r0 = rnd(6 - h), used only by Patch / Brick).

Algorithm (OLD text below is superseded where it says otherwise; Z80 == this file)
---------------------------------------------------------
RNG: private 16-bit xorshift 7,9,8 (same step as levelgen's GEN_RNG, own state
x = RD_SEED; never GEN_RNG / RNG_STATE), rnd(n) = step, then (x & $FF) mod n.
Menu = 4 common objects + the depth's per-level objects (tileset_ids.inc order).
TRIES = 12 attempts; EVERY attempt makes exactly 4 rnd calls, in this order,
whether or not it places anything:
    o   = rnd(N)                       menu index
    col = cmin + rnd(33 - w - 2*cmin)  cmin = 0 wall-class, 1 air-class
    s   = rnd(2)
    r0  = rmin + rnd(7 - h - rmin)     rmin = 1 wall-class, 0 air-class
    row = 9*s + r0                     (so the object sits in rows 9s..9s+5:
                                        never the 2 rows above a floor)
Then (no more rng): reject if the budgets would be exceeded (large animated
objects <= 2, glyph-swap cells <= 4, wall-class cells
<= 6); reject unless every footprint cell is exactly the base tile (T_AIR for
air-class, T_BRICK for wall-class: so never door / arch / lintel / jamb /
ladder / pit / cap / rubble / potion cells, and wall decor never touches a
passage) and no in-bounds cell of the 1-cell ring around the footprint is a
ladder cell (T_LAD_L..T_HOLE_R).  Placed objects are row-major ids
base + dy*w + dx (tiled: all base).  Solidity follows the cell class: wall-class
ids go on T_BRICK only, air-class on T_AIR only (designer, game.md 1.2).

ANIM_LIST contract for B3B-10 (AL_TYPE): LOOK-1 (2026-11-02): the flame attr cycle (kind 1,
$46 -> $42 -> $06) is gone, the flame cells keep the fixed $42 of their tile; every entry is a
glyph swap (AL_TYPE >= 16), the value is the ALTERNATE
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
# D3-7 T6: the B3B-13b drips are gone (ids 17 / 18 = the ammo floor glyphs, game.md §6.3)
MAX_LARGE, MAX_GLYPH, MAX_WALL = 2, 4, 6   # LOOK-1: no attr-cycle budget any more (half-row flames: still counts columns)
# D2-DECOR (user 2026-11-02, "D2 looks empty"): D2's set is all small objects (1x1..1x3, 3.6 visible
# objects but only ~16 decor cells a room vs 24-25 on D1/3/4/5/7/8) and ~48 % of the menu attempts of
# every level die on the spent 6-cell wall budget.  Per-depth wall budget (wall-class cells) and menu
# tries: D2 wall 13 / tries 19 (tries = wall + 6; 12 / 6 elsewhere) -> D2 ~24.6 cells a room.
# The Z80 holds one byte per depth: wall budget + 1 (dg_wmax_tab); tries = that + DG_TRIES_ADD (5).
WALL_MAX = {d: MAX_WALL for d in range(1, 9)}
WALL_MAX[2] = 13
TRIES_ADD = 5


def tries_of(depth):
    return WALL_MAX[depth] + 1 + TRIES_ADD


assert tries_of(1) == 12 and tries_of(3) == 12   # TRIES: the default depths keep their 12 attempts

# object classes (record wh byte bits 5..7)
C_MOUNT, C_CEIL, C_FLOOR, C_PATCH, C_BRICK, C_COMP = 0, 1, 2, 3, 4, 5
CMIN = {C_MOUNT: 1, C_CEIL: 1, C_FLOOR: 1, C_PATCH: 2, C_BRICK: 0, C_COMP: 2}
CLASS_OF = {"TORCH_TALL": C_MOUNT, "TORCH_SLIM": C_MOUNT, "WINDOW_ARCH": C_MOUNT,
            "WINDOW_BAR": C_MOUNT, "BANNER": C_MOUNT, "BANNER_TALL": C_MOUNT, "BOOKSHELF": C_MOUNT,
            "CHAIN": C_CEIL, "MOSS": C_CEIL, "BRAZIER": C_FLOOR, "BRAZIER_BIG": C_FLOOR,
            "WALL_DITHER": C_PATCH, "WALL_PATCH": C_PATCH, "WALL_FADE": C_PATCH,
            "PATCH_A": C_PATCH, "PATCH_B": C_PATCH, "PILLAR": C_BRICK}
PATCH_TRIES = 8
MAX_COB = 2
# flags byte of an object record (bit 0 = moss: a ceiling object that needs a floor above)
# (bit 3 glyph last col = the cauldron: DEC2, gone; bit 4 attr row 1 = the flame cycle: LOOK-1, gone;
#  bits 5 / 6 were attr-all / attr type 2: candles + small torch, gone with DEC1; never set now)
F_MOSS, F_TILED, F_GROW0, F_GROW1, F_LO0, F_LARGE = 1, 2, 4, 8, 16, 128   # F_GROW1: row 1 swaps too (w = 2); F_LO0: only (row 1, col 0)

# common objects (all depths): name, base, w, h, flags
COMMON = [
    ("CHAIN", D["T_CHAIN"], 1, 2, F_TILED),       # DEC1: CANDLES / SKULLS / TORCH_SMALL removed
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
ANIM_FLAGS = {"TORCH_TALL": F_GROW0 | F_LARGE, "BRAZIER_BIG": F_GROW0 | F_LARGE,
              "TORCH_SLIM": F_GROW0 | F_LARGE, "BRAZIER": F_GROW0 | F_LARGE}


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
        if name in ("LECTERN", "GLOW", "PILLAR"):   # GLOW: B12 exit marker; PILLAR dropped (user 2026-10-12)
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
            assert all(r < 2 for r, c in diff), (d, name)
            low = [c for r, c in diff if r == 1]
            if low:                                   # half-row flames: the 2nd cell row swaps (2-wide objects)
                assert w == 2 and fl & F_GROW0, (d, name)
                fl |= F_GROW1 if len(low) == 2 else F_LO0     # both cells, or only the left one (one id short)
                assert low in ([0, 1], [0]), (d, name, diff)
            assert [fr[2][k] for k in diff] == [base + w * h + k for k in range(len(diff))], (d, name)
            want = w + (w if fl & F_GROW1 else 1 if fl & F_LO0 else 0) if fl & F_GROW0 else 1
            assert len(diff) == want, (d, name, diff)
        else:
            assert not fl & F_GROW0, (d, name)
        out[d].append((name, base, w, h, fl, CLASS_OF[name]))
    for d in out:
        out[d].sort(key=lambda o: o[0] not in ("PATCH_A", "PATCH_B"))   # stable: patches first
        assert len(out[d]) >= 3          # D5 / D7: 3 since PILLAR made room for GLOW (B12)
    for d, c in cob.items():
        assert not c or c[1] is not None, f"D{d}: COBWEB without COBWEB_R"   # both ids exist
    return out, cob


LEVEL, COBWEB = level_objects()
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
    """glyph cells an object adds to the room budget (LOOK-1: no attr-cycle cells any more)."""
    return w if fl & F_GROW0 else 0   # columns, not cells: the lower flame row (F_GROW1) is free of budget


def is_decor(t):
    """a tile id the 1-cell ring must not hold (placed decor): chain and
    everything per-level / wall-set (28..59). Not 17 / 18 (ammo / pages floor glyphs) and not
    60..63 (3E floor-item class glyphs FLASK FOOD WEAPON WORN on every depth: items, like the
    old potion 10; the D8 lectern is stamped outside decorgen).  DEC2: 12 chain only (13 / 15 / 16 / 31
    were the DEC1 bones, now free; 31 sits inside the 28..59 range, so it is carved out)."""
    return (28 <= t < 60 and t != 31) or t == 12


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
    def __init__(self, m, live, maxwall=MAX_WALL):
        self.m, self.live, self.maxwall = list(m), live, maxwall
        self.anim = []
        self.nl = self.ng = self.nw = 0

    def budget_ok(self, w, h, fl, cls, area):
        dg = counts(w, h, fl)
        large = 1 if fl & F_LARGE else 0
        if self.nl + large > MAX_LARGE or self.ng + dg > MAX_GLYPH:
            return False
        if cls in (C_PATCH, C_BRICK, C_COMP) and self.nw + area > self.maxwall:
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
                if fl & F_GROW0 and (dy == 0 or (dy == 1 and (fl & F_GROW1 or (fl & F_LO0 and dx == 0)))):
                    typ, alt = alt, alt + 1
                if typ and self.live:
                    self.anim += [col + dx, row + dy, typ, ph]
        self.nl += 1 if fl & F_LARGE else 0
        self.ng += counts(w, h, fl)
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
    room = Room(m, live, WALL_MAX[depth])
    patch_pass(room, rng, depth)
    cobwebs(room, rng, depth)
    mn = menu(depth)
    for _ in range(tries_of(depth)):
        o = mn[rng.rnd(len(mn))]
        room.try_place(rng, o, None)
    return room.m, room.anim


def emit_asm():
    out = ["; GENERATED by tools/decorgen.py --asm (edit the tool, re-run, paste)",
           "; record (3 B): base id | w + h*4 + class*32 | flags (bit0 moss, 1 tiled, 2 glyph row 0, 3 glyph row 1 too (half-row flames), 4 only its col 0,",
           ";                 5 / 6 unused, 7 large animated)",
           "; class 0 mount, 1 ceiling, 2 floor, 3 patch, 4 brick, 5 composite patch",
           "dg_start:       ; first per-level record of depth 1..8, then the end"]
    out.append("                DEFB " + ", ".join(str(LEVEL_FIRST[d]) for d in range(1, 10)))
    out.append("dg_pk:          ; PATCH_A/B records at the head of each level's records (0 = composite)")
    out.append("                DEFB " + ", ".join(str(PATCHK[d]) for d in range(1, 9)))
    out.append("dg_wmax_tab:    ; per depth: wall-class cell budget + 1 (D2-DECOR); menu tries = that + DG_TRIES_ADD")
    out.append("                DEFB " + ", ".join(str(WALL_MAX[d] + 1) for d in range(1, 9)))
    out.append(f"DG_TRIES_ADD    EQU {TRIES_ADD}")
    out.append("dg_cob:         ; COBWEB left / right corner id per depth (0 = none)")
    for d in range(1, 9):
        l, r = COBWEB[d] or (0, 0)
        out.append(f"                DEFB {l:3d}, {r:3d}")
    # dg_bad: emitted separately (--asm-bad -> src/dg_bad3.asm, L-RELIEF)
    out.append("dg_crec:        ; the composite patch record (D1 / D8)")
    out.append(f"                DEFB 0, {COMP[2] + COMP[3] * 4 + COMP[5] * 32}, 0")
    out.append("dg_recs:")
    for i, (name, base, w, h, fl, cls) in enumerate(RECORDS):
        tag = f"{i:2d} " + ("common " if i < len(COMMON) else f"D{[d for d in range(1, 9) if LEVEL_FIRST[d] <= i < LEVEL_FIRST[d+1]][0]} ") + name
        out.append(f"                DEFB {base:3d}, {w + h * 4 + cls * 32:3d}, ${fl:02X}      ; {tag}")
    out.append(f"DG_NCOM         EQU {len(COMMON)}")
    out.append(f"DG_NREC         EQU {len(RECORDS)}")
    return "\n".join(out)


def emit_bad_asm():
    """dg_bad (64 B, dg_ring's lookup: 1 = ladder / hole / decor id). L-RELIEF:
    its own file, src/dg_bad3.asm, INCLUDEd by combat_data3.asm right after
    kx_tab ($C000 + 256 = $C100, 64-aligned by construction: no ALIGN pad)."""
    bad = [1 if (T_LAD_L <= t <= T_HOLE_R or is_decor(t)) else 0 for t in range(64)]
    out = ["; GENERATED by tools/decorgen.py --asm-bad (edit the tool, re-run, paste)",
           "; dg_ring's lookup: 1 = ladder / hole / decor id; 64-aligned (the OR is the add)",
           "dg_bad:"]
    for k in range(0, 64, 16):
        out.append("                DEFB " + ", ".join(str(v) for v in bad[k:k + 16]))
    return "\n".join(out)


if __name__ == "__main__":
    if "--asm-bad" in sys.argv:
        print(emit_bad_asm())
    elif "--asm" in sys.argv:
        print(emit_asm())
    else:
        print(f"{len(RECORDS)} records, menu sizes " + ", ".join(
            f"D{d}={len(menu(d))}" for d in range(1, 9)))
