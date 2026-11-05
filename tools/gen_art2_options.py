#!/usr/bin/env python3
"""gen_art2_options.py — CONCEPT options after the first 3F Fuse playtest (2026-10-29).

Review artefact only: NOT engine data, NOT on the canvas, NOT in index.asm /
frames.asm / SRC6. The manager publishes the sheet to the Design canvas; the user
picks options; the chosen frames are then authored for real (gen_3f_art.py) and
go back through the canvas.

Problems (user feedback after T13):
  V  Vampire attack unreadable (it plays the Necro cast pose): bite options.
  O  Ogre SLAM / Orc ATTACK read as coming from the bottom: overhead options.
  C  Spider dies into the Rat's corpse: neutral remains + a Spider-own DEAD.
  A  Cheap animation (shift-lunge, knock-back, SYM) — sequence strips + GIFs.
  S  48 -> 40 px: what the 3F 48-px kinds lose (row-drop mocks, like
     tools/short_sprites_preview.py).

Writes assets/gfx/concept/art2_options/:
  grid/<name>.grid          3-state grids (ink '#', opaque '+', transparent '.')
  art2_options.png          review sheet (x3, ink on black + mask panel)
  art2_options.svg.html     canvas-format artboards (svg_sprites convention)
  anim_*.gif                sequence previews
  costs.txt                 per-frame pool / raw / packed numbers
Validation (exit 1 on failure): every grid packed by gfx_convert.py --layout
native (clash: one ink per 8x8 cell), DEFB decoded back == grid (data + mask).
Packed sizes: ZX0 (tools/bin/zx0; falls back to the main checkout's binary),
measured as the DELTA of the kind's SRC6 block with/without the frame.
Usage: python3 tools/gen_art2_options.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G  # noqa: E402
import gfx_convert  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402

REPO = S.REPO
OUT = os.path.join(REPO, "assets/gfx/concept/art2_options")
GRID_OUT = os.path.join(OUT, "grid")
SPR_GRID = os.path.join(REPO, "assets/gfx/sprites/grid")
art, put, poly, ellipse, blank = G.art, G.put, G.poly, G.ellipse, G.blank

if not os.path.exists(zp.ZX0):            # worktree without tools/bin: use the main checkout's
    alt = os.path.join(REPO.split("/.claude/worktrees/")[0], "tools/bin/zx0")
    if os.path.exists(alt):
        zp.ZX0 = alt


def load(name: str) -> np.ndarray:
    bm, _ = S.read_grid(os.path.join(SPR_GRID, name + ".grid"))
    return bm.astype(bool)


# ===========================================================================
# V  VAMPIRE (draws the Necro frames, ink $05)
# ===========================================================================

def necro_robe_lower() -> np.ndarray:
    """Necro WALK 1 rows 26..47 with the staff and sleeve stripes removed."""
    b = G.necro_walk(G.NECRO_HEM1)[26:].copy()
    b[0:8, 16:] = False                     # staff + sleeve edge rows 26..33
    return b


VAMP_TOP_32 = """
00|................................
01|.#..............................
02|.##.............................
03|.###............######..........
04|.####.........##########........
05|.##.##.......############.......
06|.###.##.....##############......
07|..###.##....######....#####.....
08|.#.###.##...#####.........##....
09|.##.###.##..####..##..##...#....
10|.###.###.##.####............#...
11|..###.###.#.####..#.....#...#...
12|...#.#.###.#####..#.....#..#....
13|.......#.#.######..#...#..#.....
14|.........#.#######.#####.#......
15|..........#.#######.....#.......
16|.........##.#########.##........
17|.........###.#########.###...#..
18|.........####.#########.######..
19|.........#####.#######...###.##.
20|.........######.######...#.#..#.
21|.........#######.#####...#..#...
22|.........#.#.#.#.####...........
23|.........############...........
24|.........############...........
25|.........############...........
"""


def vampire_bite32() -> np.ndarray:
    """V1 own BITE 32x48: hood thrust forward over the victim, the maw open on
    two long fangs, cape flared up behind like a bat wing (scalloped edge),
    clawed hand gripping ahead. Robe = the Necro walk's (same feet)."""
    b = np.zeros((48, 32), bool)
    b[:26] = art(VAMP_TOP_32, 32)
    b[26:, :24] = necro_robe_lower()
    return b


def vampire_bite24() -> np.ndarray:
    """V2 own BITE in the 24x48 body box (no wider frame): V1's head + cape
    pulled back 5 px (the wing tip and most of the claw are lost)."""
    v1 = vampire_bite32()
    b = np.zeros((48, 24), bool)
    b[:16] = v1[:16, 5:29]                  # head + cape, 5 px back
    b[16:22] = v1[16:22, :24]               # arm (claw clipped at the box edge)
    b[22:] = v1[22:, :24]
    return b


def vampire_cast_drain() -> np.ndarray:
    """V3 mock: the existing Necro CAST + a 'drain' trail flowing back INTO the
    hand (drawn in the cells right of the body). In game this is an FX sprite /
    attr cue, not part of the frame; shown in one ink here."""
    b = np.hstack([load("necro_cast"), blank(8, 48)])
    for x, y in ((33, 16), (35, 15), (37, 17), (39, 16), (34, 18), (38, 14), (36, 19)):
        b[y, x] = True                         # droplets stream toward the claw
    b[15:18, 32] = True
    return b


def vampire_batswoop() -> np.ndarray:
    """V4 mock: the attack frame is the Bat kind's DIVE (resident on every
    Vampire level for the bat form) drawn at head height of the 24x48 box —
    the vampire 'flickers' into a bat for the bite."""
    b = np.zeros((48, 32), bool)
    b[0:16] = load("bat_dive")
    return b


# ===========================================================================
# O  OGRE / ORC overhead attacks
# ===========================================================================

def ogre_slam_overhead() -> np.ndarray:
    """O1 SLAM redrawn (same 40x48 box): the club comes DOWN on the victim's
    head — arm thrown up-forward, club head at head height, an arc of swing
    streaks above it from behind the skull. No floor impact."""
    sh = (48, 40)
    b = G.ogre_body(sh, G.OGRE_LEGS1, front_arm=False)
    for x, y in ((14, 0), (17, 0), (20, 0), (23, 1), (26, 1), (29, 2), (31, 3),
                 (33, 4), (12, 1), (24, 0), (28, 0), (32, 1)):
        b[y, x] = True                                            # swing arc above the head
    put(b, poly(sh, [(21, 14), (28, 10)], w=4), sep=True)         # arm thrown up-forward
    put(b, ellipse(sh, 30.5, 11.0, 2.6, 2.6), sep=True)           # fist
    put(b, poly(sh, [(32, 9), (34, 6)], w=2), sep=True)           # haft
    put(b, ellipse(sh, 36.0, 5.5, 3.6, 4.6), sep=True)            # club head (coming down)
    b[4, 36] = False                                              # knots
    b[7, 35] = False
    for x, y in ((39, 13), (38, 15), (36, 14)):
        b[y, x] = True                                            # chips off the impact
    return b


def ogre_raise32() -> np.ndarray:
    """O2 RAISE wind-up in 32x48 (not 40x48): club hoisted high behind the head,
    both shoulders up, front arm bent back over the skull."""
    sh = (48, 32)
    b = G.ogre_body(sh, G.OGRE_LEGS1, front_arm=False)
    put(b, poly(sh, [(4, 2), (12, 0)], w=1))                      # wind streak
    put(b, ellipse(sh, 5.0, 4.5, 3.6, 4.0))                       # club head (behind)
    b[3, 4] = False
    b[6, 6] = False
    put(b, poly(sh, [(8, 5), (12, 3)], w=2))                      # haft
    put(b, poly(sh, [(21, 14), (17, 3)], w=4), sep=True)          # front arm up beside the head
    put(b, ellipse(sh, 15.0, 2.6, 2.6, 2.4), sep=True)            # fist above/behind the skull
    return b


ORC_ATTACK_HIGH = """
00|................#..#.##########.
01|.............#.......#.########.
02|...........#.........##########.
03|.....................#........#.
04|.....................##########.
05|......................###.......
06|......................###.......
07|......................####......
08|.....................#####......
09|....................#####.......
10|...................#####........
11|..................#####.........
12|..................####..........
13|..................###...........
14|..................###...........
15|..................###...........
16|..................###...........
17|..................###...........
18|..................##............
"""


def orc_attack_overhead() -> np.ndarray:
    """Orc ATTACK redrawn (same 32x48): the cleaver (carried low at the hip in
    the walk) is raised over the head and chopping down — blade above the fist,
    a swing arc behind the skull."""
    b = np.hstack([G.orc_walk(G.ORC_LEGS1), blank(8, 48)])
    b[15:29, 18:] = False                                         # old front arm
    b[29:38, 19:] = False                                         # cleaver at the hip
    arm = np.zeros_like(b)
    arm[0:19] = art(ORC_ATTACK_HIGH, 32)
    put(b, arm, sep=True)
    return b


# ===========================================================================
# C  corpses (32x16)
# ===========================================================================

REMAINS_BONES = """
00|................................
01|................................
02|................................
03|................................
04|................................
05|................................
06|................................
07|..............####..............
08|.............######.............
09|.............#.##.#.............
10|.............######.............
11|.....##.......#.#.......##......
12|....#..###.#.#.#.#.#.###..#.....
13|.....##...##.#.#.#.#.##...##....
14|..#.......####.#.####........#..
15|.##########################.###.
"""


def remains_bones() -> np.ndarray:
    """C1 neutral 'bone pile': a small skull over a rib spread and two bones —
    fits rat / spider / giant rat alike. Nearly symmetric (SYM candidate)."""
    return art(REMAINS_BONES, 32)


REMAINS_SPLAT = """
00|................................
01|................................
02|................................
03|................................
04|................................
05|................................
06|................................
07|................................
08|...........#........#...........
09|.....#.........##.........#.....
10|.........#...######...#.........
11|...#.......##########......#....
12|.......#.####.####.####.#.......
13|..#...###############.#####...#.
14|.#.##########.##############.##.
15|################################
"""


def remains_splat() -> np.ndarray:
    """C2 neutral 'remains': a flattened heap with splash droplets — no head,
    no tail, no legs, so it is no animal in particular."""
    return art(REMAINS_SPLAT, 32)


def spider_dead() -> np.ndarray:
    """C3 Spider-own DEAD: on its back, abdomen down, the 8 legs curled up in
    the air (two sets of knees pointing up)."""
    sh = (16, 32)
    b = np.zeros(sh, bool)
    legs = [[(18, 11), (21, 3), (25, 1), (27, 3)], [(17, 11), (18, 2), (21, 0)],
            [(13, 11), (12, 3), (9, 1)], [(12, 11), (9, 4), (5, 2), (3, 4)]]
    for pts in legs:
        put(b, poly(sh, pts))
    put(b, ellipse(sh, 11.0, 12.5, 7.0, 3.6), sep=True)            # abdomen (belly up)
    put(b, ellipse(sh, 21.5, 13.0, 3.6, 2.4), sep=True)            # cephalothorax
    put(b, ellipse(sh, 26.0, 13.8, 2.0, 1.8))                      # head
    b[12, 7:15] = False                                            # belly seam
    b[14, 26] = False                                              # dead eye
    b[15, :] = False
    b[15, 3:30] = True                                             # floor contact
    b[15, 16] = b[15, 24] = False
    for x, y in ((27, 9), (28, 11), (5, 8)):
        b[y, x] = True                                             # twitch ticks
    return b


# ===========================================================================
# S  48 -> 40 px mocks (rows dropped at joints, like short_sprites_preview.py)
# ===========================================================================

SHORT = {
    # name: (builder, rows dropped)   -- 8 rows each, none in the eyes/mouth band
    "orc_walk1": (lambda: G.orc_walk(G.ORC_LEGS1), {0, 1, 2, 3, 22, 25, 38, 43}),
    "necro_walk1": (lambda: G.necro_walk(G.NECRO_HEM1), {0, 6, 20, 26, 30, 33, 36, 40}),
    "ogre_walk1": (lambda: G.ogre_walk(G.OGRE_LEGS1), {0, 1, 2, 17, 22, 35, 37, 41}),
    "dk_walk1": (lambda: G.dk_walk(G.DK_LEGS1), {6, 16, 20, 27, 33, 39, 41, 43}),
    "mummy_walk1": (lambda: G.mummy_walk(G.MUMMY_LEGS1), {0, 1, 2, 3, 25, 34, 38, 42}),
}


def shorten(name: str) -> np.ndarray:
    f, drop = SHORT[name]
    b = f()
    return np.array([r for y, r in enumerate(b) if y not in drop], bool)


# ===========================================================================
# frame table: (group, name, caption, builder, ink, pool flag, note)
# pool flag: STA / SYM (cell-aligned, 1 facing) / MOCK (no frame of its own)
# ===========================================================================

INK_VAMP, INK_ORC, INK_OGRE = "#00D7D7", "#00D700", "#00FF00"
INK_RAT, INK_SPIDER = "#D7D700", "#00D7D7"

FRAMES = [
    ("V", "vamp_bite32", "V1 BITE 32x48", vampire_bite32, INK_VAMP, "STA", "own frame, lunge"),
    ("V", "vamp_bite24", "V2 BITE 24x48", vampire_bite24, INK_VAMP, "STA", "own frame, body box"),
    ("V", "vamp_castdrain", "V3 CAST+DRAIN", vampire_cast_drain, INK_VAMP, "MOCK",
     "Necro cast + FX/attr cue"),
    ("V", "vamp_batswoop", "V4 BAT SWOOP", vampire_batswoop, INK_VAMP, "MOCK", "Bat DIVE at head height"),
    ("O", "ogre_slam_now", "OGRE SLAM (now)", lambda: load("ogre_slam"), INK_OGRE, "MOCK", "current: floor"),
    ("O", "ogre_slam_high", "O1 SLAM HIGH", ogre_slam_overhead, INK_OGRE, "STA", "redraw, same box"),
    ("O", "ogre_raise32", "O2 RAISE 32x48", ogre_raise32, INK_OGRE, "STA", "new wind-up"),
    ("O", "orc_attack_now", "ORC ATTACK (now)", lambda: load("orc_attack"), INK_ORC, "MOCK", "current"),
    ("O", "orc_attack_high", "O3 ORC ATTACK HIGH", orc_attack_overhead, INK_ORC, "STA", "redraw, same box"),
    ("C", "rat_dead_now", "RAT DEAD (now)", lambda: load("rat_dead"), INK_SPIDER, "MOCK",
     "shown in Spider ink"),
    ("C", "remains_bones", "C1 BONES", remains_bones, INK_SPIDER, "STA", "replaces rat_dead"),
    ("C", "remains_splat", "C2 REMAINS", remains_splat, INK_RAT, "SYM", "replaces rat_dead"),
    ("C", "spider_dead", "C3 SPIDER DEAD", spider_dead, INK_SPIDER, "STA", "Spider-own"),
]
for _n in SHORT:
    _k = _n.split("_")[0]
    _ink = {"orc": INK_ORC, "necro": "#D700D7", "ogre": INK_OGRE, "dk": "#FFFFFF",
            "mummy": "#D7D700"}[_k]
    FRAMES.append(("S", _n + "_48", f"{_k.upper()} 48", (lambda n=_n: SHORT[n][0]()), _ink,
                   "MOCK", "now"))
    FRAMES.append(("S", _n + "_40", f"{_k.upper()} 40", (lambda n=_n: shorten(n)), _ink,
                   "S40", "short mock"))

# SRC6 block the frame would join (delta packing), from src/frames.asm FRM kinds
BLOCK = {
    "vamp_bite32": ["necro_walk1", "necro_walk2", "necro_cast"],
    "vamp_bite24": ["necro_walk1", "necro_walk2", "necro_cast"],
    "ogre_slam_high": ["ogre_walk1", "ogre_walk2"],              # replaces ogre_slam
    "ogre_raise32": ["ogre_walk1", "ogre_walk2", "ogre_slam"],
    "orc_attack_high": ["orc_walk1", "orc_walk2"],               # replaces orc_attack
    "remains_bones": [],
    "remains_splat": [],
    "spider_dead": ["spider_walk1", "spider_walk2", "spider_bite"],
}
REPLACES = {"ogre_slam_high": "ogre_slam", "orc_attack_high": "orc_attack",
            "remains_bones": "rat_dead", "remains_splat": "rat_dead"}


# Options table (pool = both facings, cell-aligned; SRC6 = ZX0 delta, see costs.txt).
# Worst pool level stays D7 (pool_spike.md); D3/D4/D6/D8 slack >= 6.4 KB, so pool
# growth on those levels is free. SRC6 free = 167 B, FRT spare fids = 4.
TABLE = """\
OPTION                      POOL B (levels)           SRC6/ZX0 B   FID  NOTE
V1 own BITE 32x48           +768 (D3 D6 D8, not max)  +133         +1   lunge, fangs, cape-wing, claw
V2 own BITE 24x48           +576 (D3 D6 D8)           +108         +1   box too narrow: weak read
V3 Necro CAST + drain cue    0                         0            0   attr flash heal ~20-30 B code;
                                                                        FX must stay outside body cells
V4 Bat DIVE at head height   0 (Bat set resident)      0            0   code: per-kind attack fid + y
O1 Ogre SLAM overhead        0 (same 40x48)            -13          0   club at head height, arc above
O2 + RAISE 32x48 (not 40)    +768 (D4, not max)        +143         +1   wind-up; 40x48 = +960
O3 Orc ATTACK overhead       0 (same 32x48)            +24          0   cleaver raised, was at hip
C1 BONES (replaces rat_dead) 0                         -8 (bank1/3) 0   skull + ribs, neutral
C2 REMAINS, SYM              -128 every Rat/Spider lvl -14 (bank1/3) 0  no head/tail; 1 facing
C3 Spider-own DEAD           +256 (D2 D4; 0 on D5)     +100         +1   on its back, legs up
A1 lunge: WALK2(WK4) at +4px 0                         0            0   step-in tick before ATTACK
A2 knock-back: WALK2 at -4px 0                         0            0   + the $42 flash (R4)
A3 SYM on symmetric frames   -half per frame           0            0   corpses, bolt hit
A4 1-px idle bob             0                         0            0   engine: pixel-y draw? (ask)
S  48->40 px                 -96/frame STA, -128 WK4   -48 raw/fr   0   Orc/Mummy art is 44 rows
                                                                        (lose 4); DK/heroes lose detail
"""


def pool_bytes(w: int, h: int, flag: str) -> int:
    """Cell-aligned (STA) both facings = h*2*cols*2; SYM = one facing."""
    c = w // 8
    return h * 2 * c * (1 if flag == "SYM" else 2)


def grid_text(name, bm, solid, caption, ink, note) -> str:
    h, w = bm.shape
    lines = ["# Tome of the Dead gfx text grid — CONCEPT (tools/gen_art2_options.py); not engine data.",
             f"# name: {name}", f"# size: {w}x{h}", f"# character: {name.split('_')[0].upper()}",
             f"# caption: {caption}", f"# ink: {ink}", "# anchor: 0 0", f"# note: {note}",
             "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent", "#"]
    for y in range(h):
        lines.append("".join("#" if bm[y, x] else "+" if solid[y, x] else "." for x in range(w)))
    return "\n".join(lines) + "\n"


def pack_check(name, gpath, bm, solid, ink, td):
    colour, bright = S.INK_MAP[ink]
    out = os.path.join(td, name + ".asm")
    argv = ["--mode", "sprite", "--layout", "native", "--in", gpath, "--name", name,
            "--out", out, "--ink", gfx_convert.COL_NAME[colour], "--paper", "black",
            "--band-paper", "black", "--date", "concept"] + (["--bright"] if bright else [])
    S._quiet(S.run_gfx, argv)
    rows, _attr = S.decode_asm(out)
    fg, sol = gfx_convert.unpack_sprite_mask(rows, bm.shape[1], "native")
    if not (np.array_equal(fg, bm) and np.array_equal(sol, solid)):
        raise SystemExit(f"{name}: round-trip mismatch")
    return bytes(b for r in rows for b in r)


def packed(raw: bytes, td: str) -> int:
    return len(zp.zx0(raw, os.path.join(td, f"z{abs(hash(raw)) % 10**12}")))


def panel(bm, solid, ink_hex, scale, box_h=None):
    colour, bright = S.INK_MAP[ink_hex]
    ink = S.spec_rgb(colour, bright)
    h, w = bm.shape
    a = np.full((h, w, 3), (34, 34, 60), np.uint8)
    a[solid] = (0, 0, 0)
    a[bm] = ink
    if box_h and box_h > h:
        a = np.vstack([np.full((box_h - h, w, 3), (20, 20, 30), np.uint8), a])
    return Image.fromarray(a).resize((a.shape[1] * scale, a.shape[0] * scale), Image.NEAREST)


def main() -> int:
    os.makedirs(GRID_OUT, exist_ok=True)
    game = dict(zp.game_frames())
    built, cost_lines = [], []
    with tempfile.TemporaryDirectory() as td:
        for grp, name, cap, fn, ink, flag, note in FRAMES:
            bm = fn().astype(bool)
            assert bm.shape[1] % 8 == 0 and bm.shape[0] % 8 == 0, name
            solid = S.make_mask(bm, outline=True)
            gpath = os.path.join(GRID_OUT, name + ".grid")
            with open(gpath, "w") as f:
                f.write(grid_text(name, bm, solid, cap, ink, note))
            raw = pack_check(name, gpath, bm, solid, ink, td)    # clash + round-trip
            h, w = bm.shape
            line = f"{name:18s} {w}x{h:<3d} {flag:4s}"
            if flag == "S40":
                line += (f" per frame (STA, both facings) pool -{pool_bytes(w, 8, 'STA')}"
                         f" (shift-4 copy -{h and 8 * 2 * (w // 8 + 1) * 2}), raw -{8 * 2 * w // 8}")
            elif flag != "MOCK":
                pool = pool_bytes(w, h, flag)
                blk = b"".join(game[n] for n in BLOCK.get(name, []))
                dpk = packed(blk + raw, td) - (packed(blk, td) if blk else 0)
                rep = REPLACES.get(name)
                if rep:
                    old = game[rep]
                    oldpk = packed(blk + old, td) - (packed(blk, td) if blk else 0)
                    line += (f" pool {pool:5d} (was {pool_bytes(w, h, 'STA') if rep != 'rat_dead' else 256})"
                             f"  raw {len(raw)}  packed {dpk} (was {oldpk}, delta {dpk - oldpk:+d})")
                else:
                    line += f" pool {pool:5d}  raw {len(raw)}  packed +{dpk} (block delta)"
            cost_lines.append(line + f"  ; {note}")
            built.append((grp, name, cap, bm, solid, ink, note))
    with open(os.path.join(OUT, "costs.txt"), "w") as f:
        f.write("# gen_art2_options.py — pool = cell-aligned, both facings (SYM: one);"
                " packed = ZX0 delta in the kind's block\n" + "\n".join(cost_lines) + "\n")
    print("\n".join(cost_lines))

    # ---- review sheet ------------------------------------------------------
    scale = 3
    titles = {"V": "V  VAMPIRE ATTACK", "O": "O  OGRE / ORC OVERHEAD",
              "C": "C  CORPSES (32x16)", "S": "S  48 px vs 40 px (8 rows dropped at joints)"}
    rows_img = []
    for grp in "VOCS":
        items = [b for b in built if b[0] == grp]
        box_h = max(b[3].shape[0] for b in items)
        cells = []
        for _g, name, cap, bm, solid, ink, note in items:
            p = panel(bm, solid, ink, scale, box_h)
            c = Image.new("RGB", (max(p.width, 120) + 8, p.height + 28), (16, 16, 24))
            c.paste(p, (4, 4))
            d = ImageDraw.Draw(c)
            d.text((4, p.height + 6), cap, fill=(220, 220, 230))
            d.text((4, p.height + 16), note, fill=(140, 140, 160))
            cells.append(c)
        wsum = sum(c.width for c in cells)
        r = Image.new("RGB", (wsum, cells[0].height + 18), (16, 16, 24))
        ImageDraw.Draw(r).text((4, 4), titles[grp], fill=(255, 255, 120))
        x = 0
        for c in cells:
            r.paste(c, (x, 18))
            x += c.width
        rows_img.append(r)
    W = max(r.width for r in rows_img)
    sheet = Image.new("RGB", (W, sum(r.height for r in rows_img)), (16, 16, 24))
    y = 0
    for r in rows_img:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(os.path.join(OUT, "art2_options.png"))

    # ---- canvas fragment (svg_sprites artboards) ----------------------------
    html = ["<!-- CONCEPT art2 options (tools/gen_art2_options.py) — review only, not importable -->",
            '<pre style="font-size:10px;color:#a9a7b8;line-height:1.5;">' + TABLE + "</pre>"]
    for grp in "VOCS":
        html.append(f"<h2>{titles[grp]}</h2>")
        for g, name, cap, bm, solid, ink, note in built:
            if g == grp:
                html.append(S.svg_artboard_html(bm, ink, cap.replace(" ", "_")))
    with open(os.path.join(OUT, "art2_options.svg.html"), "w") as f:
        f.write("\n".join(html) + "\n")

    anims()
    return 0


# ===========================================================================
# A  cheap-animation previews (GIFs on a 64x48 strip; target = a grey post)
# ===========================================================================

def anims() -> None:
    def frame_img(parts, w=72, h=48, scale=3):
        a = np.zeros((h, w, 3), np.uint8)
        a[:, 56:58] = (90, 90, 90)                          # victim / wall marker
        for bm, x, ink_hex in parts:
            colour, bright = S.INK_MAP[ink_hex]
            ink = S.spec_rgb(colour, bright)
            solid = S.make_mask(bm, outline=True)
            hh, ww = bm.shape
            sub = a[h - hh:h, x:x + ww]
            sub[solid[:, :sub.shape[1]]] = (0, 0, 0)
            sub[bm[:, :sub.shape[1]]] = ink
        for cx in range(0, w, 8):                           # 8-px cell ticks
            a[h - 1, cx] = (60, 60, 120)
        return Image.fromarray(a).resize((w * scale, h * scale), Image.NEAREST)

    def gif(name, seq, ms=260):
        imgs = [frame_img(p) for p in seq]
        imgs[0].save(os.path.join(OUT, name), save_all=True, append_images=imgs[1:],
                     duration=ms, loop=0)

    ow1, ow2 = G.orc_walk(G.ORC_LEGS1), G.orc_walk(G.ORC_LEGS2)
    gif("anim_orc_lunge.gif", [[(ow1, 16, INK_ORC)], [(ow2, 20, INK_ORC)],
                                [(orc_attack_overhead(), 16, INK_ORC)], [(ow1, 16, INK_ORC)]])
    gw1 = G.ogre_walk(G.OGRE_LEGS1)
    gif("anim_ogre_raise_slam.gif", [[(gw1, 8, INK_OGRE)], [(ogre_raise32(), 8, INK_OGRE)],
                                     [(ogre_slam_overhead(), 8, INK_OGRE)], [(gw1, 8, INK_OGRE)]])
    gif("anim_ogre_slam_high.gif", [[(gw1, 8, INK_OGRE)], [(ogre_slam_overhead(), 8, INK_OGRE)],
                                    [(gw1, 8, INK_OGRE)]])
    nw1 = G.necro_walk(G.NECRO_HEM1)
    gif("anim_vamp_bite.gif", [[(nw1, 16, INK_VAMP)], [(vampire_bite32(), 16, INK_VAMP)],
                               [(nw1, 16, INK_VAMP)]])
    gif("anim_hurt_knockback.gif", [[(ow1, 24, INK_ORC)], [(ow2, 20, "#FF3030")],
                                    [(ow1, 24, INK_ORC)]])


if __name__ == "__main__":
    sys.exit(main())
