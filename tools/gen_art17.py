#!/usr/bin/env python3
"""gen_art17.py — ART17 (2026-10-31) CONCEPT: the GHOST (K_GHOST, also drawn for
K_POLTERGEIST) redrawn as a SIDE-VIEW, much scarier spectre, three options. Review artefact
only: NOT engine data, nothing in index*.asm / frames.asm / SRC6.

DROP-IN geometry (no engine change, zero extra pool bytes): every frame keeps the slot,
size, flags and ax of the frame it replaces (src/frames.asm KFID_GHOST):
  ghost_float1 24x32 WK0 (= STA under PHASE_SHIFT: the rest pose, idle, never drawn in flight)
  ghost_float2 24x32 MOT (gh_fly holds it; idle = float1 6 ticks, float2 6 ticks: even cycle)
  ghost_lunge  32x32 STA (gh_attack = float2 2 ticks -> LUNGE 2, SF_IMPACT; ax 0, reach right)
  ghost_hurt   24x32 STA (gh_hurt 3 ticks; gh_death = HURT -> DEAD)
  ghost_dead   24x32 STA (own DEAD: no corpse-ashes for the Ghost)
Profiles face right (the left facing is the engine mirror). Bob rule (checked): FLOAT2 is
FLOAT1 one pixel lower with the same upper body (rows above the hem), only the tatters
change -> the 2-frame idle bob and a cheap zx0 match.
Checks (exit 1): sizes, gfx_convert --layout native clash + data / mask round-trip in both
inks the frames are drawn in (K_GHOST $45 bright cyan, K_POLTERGEIST $03 magenta; one ink
+ black paper per frame, so every 8x8 cell is 2-colour by construction), the bob rule.
Costs: frames.asm FRM pool formula + zx0 packed with the zx0_sources.partition rule
(blocks of <= 4 frames of one kind), against the frames in the build today
(zx0_pack.game_frames).
Writes assets/gfx/concept/art17/: grid/*.grid, anim/*.gif, art17_ghost.svg.html (board
F3r), art17.png, costs.txt.   Usage: python3 tools/gen_art17.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_art13_nun as N  # noqa: E402  (also points zx0_pack at the main checkout's zx0)
import gen_art2_options as A  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402
import zx0_sources as zs  # noqa: E402

REPO = S.REPO
OUT = os.path.join(REPO, "assets/gfx/concept/art17")
GRID_OUT = os.path.join(OUT, "grid")
ANIM = os.path.join(OUT, "anim")

INKS = (("$45 GHOST", "#00FFFF"), ("$03 POLTERGEIST", "#D700D7"))
SRC6_FREE = 15                                      # B free in the 16 SRC6 pages (task brief)
POOL_SLACK_D8 = 2297                                # after the reclaim; the nun needs 2,080
H, BW = 32, 24
FRAMES = (("ghost_float1", "FLOAT1", "WK0", 24), ("ghost_float2", "FLOAT2", "MOT", 24),
          ("ghost_lunge", "LUNGE", "STA", 32), ("ghost_hurt", "HURT", "STA", 24),
          ("ghost_dead", "DEAD", "STA", 24))
NAMES = [n for n, *_ in FRAMES]


def bm(txt, w):
    rows = [r for r in txt.strip("\n").splitlines()]
    out = np.zeros((H, w), bool)
    if len(rows) > H or any(len(r) > w for r in rows):
        raise SystemExit(f"art too big: {[(i, len(r)) for i, r in enumerate(rows) if len(r) > w]} rows {len(rows)}")
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c == "#":
                out[y, x] = True
    return out


def patch(base, y0, x0, txt):
    """Edit a copy of `base`: '#' ink, 'o' paper, anything else untouched (top-left y0, x0)."""
    b = base.copy()
    for j, r in enumerate(txt.strip("\n").splitlines()):
        for i, c in enumerate(r):
            if c in "#o":
                b[y0 + j, x0 + i] = c == "#"
    return b


def shifted(base, dy=0, w=None):
    """`base` moved dy px down, on a canvas `w` wide (ax 0: extra width on the right)."""
    b = np.zeros((H, w or base.shape[1]), bool)
    src = base[:H - dy] if dy >= 0 else base[-dy:]
    b[max(dy, 0):max(dy, 0) + src.shape[0], :base.shape[1]] = src
    return b


def derived(base, dy, w, patches):
    """HURT / LUNGE drawn as edits of FLOAT1 / FLOAT2: the rows they keep are a near-free
    zx0 match in the same block (float1+float2+lunge+hurt), the reason the options fit SRC6."""
    b = shifted(base, dy, w)
    for y0, x0, txt in patches:
        b = patch(b, y0, x0, txt)
    return b


def bob(f1, hem, tail2):
    """FLOAT2 = FLOAT1 one px lower above `hem`; rows hem+1.. = the second tatter phase."""
    f2 = np.zeros_like(f1)
    f2[1:hem + 1] = f1[0:hem]
    t = bm(tail2, f1.shape[1])
    f2[hem + 1:] = t[:H - hem - 1]
    return f2


# ===========================================================================
# A: HOODED WRAITH — a tall cowl in profile, the face a black void with two glowing slit
# eyes, a bell sleeve with a bony three-claw hand, the robe torn into trailing strips.
# ===========================================================================
A_F1 = """
...##...................
...####.................
....######..............
....#########...........
....############........
....##############......
...#################....
...##########.....###...
..##########.......##...
..#########...##.##.#...
..#########.........#...
.##########........##...
.###########......##....
.############....##.....
..##############........
.#######.#######........
.######.#########.......
..#####.##########......
.######.###########.....
.#####.#.#######.##.....
..####.##......######...
.#####.###.....#.#.#.#..
..####.####....#.#.#..#.
..####.#####...#..#.#...
..####.######.....#.....
...###..#####...........
...##...####.##.........
..##....###...#.........
..#.....##....#.........
.#......#...............
"""
A_HEM = 24
A_T2 = """
.####...#####.##........
.##.....####...#........
##.....####.....#.......
#......##...............
.......#................
"""
# HURT = FLOAT1 knocked 2 px down, the eyes crossed out, the claw clenched into the sleeve.
A_HURT = (2, [(10, 13, """
#o#o#o#
o#ooo#o
#o#o#o#
"""), (21, 17, "ooooooo"), (22, 14, """
oooooooooo
oooooooooo
oooooooooo
oooooooooo
oooooooooo
"""), (21, 17, """
####
#####
.###
..#
""")])
# LUNGE = FLOAT2 (the frame before it in gh_attack) with the sleeve thrust out and the claws
# raking forward to x 31; the eyes narrow to a slant.
A_LUNGE = (0, [(21, 13, """
ooooooooooo
ooooooooooo
ooooooooooo
ooooooooooo
"""), (16, 16, """
#####...........
########........
#########..####.
#########.######
#########.######
oooooo....#.#.##
..........#.#..#
.........#..#..#
""")])
A_DEAD = """
........................
........................
........................
........................
........................
........................
........................
........................
............#...........
...........#............
...........#............
............#...........
.............#..........
.............#..........
............#...........
...........#............
...........#............
............#...........
........................
........................
.........####...........
.......########.........
......####...###........
.....###.......##.......
.....####.......###.....
....######.......####...
...#########.#########..
..########.####.#######.
.#######.######.#######.
.######..#####..######..
..##..####..###...#.#.#.
"""

# ===========================================================================
# B: SKELETAL SPECTRE — a bare skull in profile (socket, nasal hole, upper and lower teeth,
# the jaw hanging open) under a torn shroud, a bone arm reaching with splayed claws, the
# body thinning to a single curling wisp.
# ===========================================================================
B_F1 = """
........................
......####..............
....#######.#####.......
...######.#########.....
..######.###########....
..#####.#####...####....
.#####.#####.....###....
.#####.######...####....
.#####.##############...
.#####..#######.####....
.######..#.#.#.#.#......
.#######................
.#######...#.#.#.#......
.########..#######......
..########..............
..#####.###.............
..####.####.............
..####.###.##...........
..####.##.#.##......#.#.
..####.####.#.#####.###.
..#####.###.#..####.####
...####.####.......#.#.#
...####.###.............
...#####.#..............
....#####...............
....######..............
...######...............
..#####.................
.####...................
.##.....................
"""
B_HEM = 23
B_T2 = """
....######..............
.....######.............
....######..............
...#####................
..####..................
.###....................
.#......................
"""
# HURT = FLOAT1 knocked 2 px down: the jaw drops wide, a crack runs up from the socket, the
# bone arm falls limp.
B_HURT = (2, [(14, 10, """
oooooooo
o#o#o#o#
.#######
"""), (4, 14, """
.o
o.
.o
"""), (19, 11, """
##ooooooooooo
o##oooooooooo
oo#oooooooooo
oo##ooooooooo
ooo#ooooooooo
...##
..#.#.#
..#.#..#
.#..#
""")])
# LUNGE = FLOAT2 with the jaw gaping and the bone arm locked straight out, claws splayed.
B_LUNGE = (0, [(13, 10, """
oooooooo
o#o#o#o#
.#######
"""), (16, 11, """
...................#.
##..............#.#.#
o############..######
oo#.#.#.#.#.###.#####
ooo##########...#.#.#
oooooooooooo....#..#.
.oooooooooooo........
""")])
B_DEAD = """
........................
........................
........................
........................
........................
........................
..........#.............
...........#............
..........#.............
.........#..............
..........#...#.........
...........#.#..........
..........#..#..........
.........#..#...........
..........#.............
........................
.........#..............
........................
........................
..........######........
........##########......
.......############.....
.......#####...####.....
.......####.....###.....
.......#####...####.....
........#############...
.........#.#.#.#.###....
.......................#
....###...#.#.#.....###.
..##.#.##.#######.##.#..
.#.....#.........#......
"""

# ===========================================================================
# C: SCREAMING BANSHEE — a gaunt profile with the jaw dropped in a black scream and a hollow
# eye, hair streaming back in torn strands, a claw out front, the gown ripped into tatters.
# ===========================================================================
C_F1 = """
........................
............######......
.........###########....
.......##############...
.....######.##########..
...########.####..####..
##########.#####..#####.
#########.##############
...#####.#############..
#######.##########......
#######.##.#######......
...###.##.######........
######.##.######........
######.##.#######.......
...###.##.#########.....
..####.##.#########.....
.####...##.#######......
..##.....##.####........
..........######........
..........######........
...........######.......
..........########......
.........###########....
........#####.###..#.#..
.......######....#.#..#.
......#######....#..#.#.
.....###.####...........
....###..###............
...###...##.............
..##.....#..............
"""
C_HEM = 25
C_T2 = """
.....####.####..........
....###..####...........
...###...###............
..##.....#..............
"""
# HURT = FLOAT1 knocked 2 px down, the eye crossed out, the claw snatched back.
C_HURT = (2, [(6, 15, """
o#o
#o#
o#o
"""), (25, 14, """
###ooooooo
o##ooooooo
oo#ooooooo
""")])
# LUNGE = FLOAT2 with the jaw dropped further and the arm flung out, talons raking at x 31.
C_LUNGE = (0, [(15, 15, "oooo"), (17, 11, "#########"), (22, 17, """
...........###.
##########.####
oo#########.#.#
ooooooo...#.#.#
ooooooo...#..#.
""")])
C_DEAD = """
........................
........................
........................
........................
........................
........................
........................
........................
.............#..........
............#...........
............#...........
.............#..........
..............#.........
..............#.........
.............#..........
............#...........
............#...........
.............#..........
........................
........................
..........#####.........
........#########.......
.......####...####......
.......###.....###......
......####.###.####.....
....#######...#######...
..###########.#########.
.####.#####.#.#####.###.
###..######...######.##.
#...###..###..###..####.
..###....##....#.....##.
"""


def option(f1, hem, t2, hurt, lunge, dead):
    a = bm(f1, 24)
    b = bob(a, hem, t2)
    hu = derived(a, hurt[0], 24, hurt[1]) if isinstance(hurt, tuple) else bm(hurt, 24)
    lu = derived(b, lunge[0], 32, lunge[1]) if isinstance(lunge, tuple) else bm(lunge, 32)
    return {"FLOAT1": a, "FLOAT2": b, "LUNGE": lu, "HURT": hu, "DEAD": bm(dead, 24)}, hem


OPTIONS = {
    "A": ("HOODED WRAITH", lambda: option(A_F1, A_HEM, A_T2, A_HURT, A_LUNGE, A_DEAD)),
    "B": ("SKELETAL SPECTRE", lambda: option(B_F1, B_HEM, B_T2, B_HURT, B_LUNGE, B_DEAD)),
    "C": ("SCREAMING BANSHEE", lambda: option(C_F1, C_HEM, C_T2, C_HURT, C_LUNGE, C_DEAD)),
}


# ===========================================================================
# costs
# ===========================================================================
def packed_kind(raws, td):
    tot, blocks = 0, []
    for st, k in zs.partition(raws, td):
        n = len(zs.pack(b"".join(d for _, d in raws[st:st + k]), td))
        tot += n
        blocks.append(f"{'+'.join(x[0].split('_')[1] for x in raws[st:st + k])} {n}")
    return tot, blocks


def cur_bitmaps():
    return {n: N.load_grid(os.path.join(REPO, "assets/gfx/sprites/grid", n + ".grid")) for n in NAMES}


# ===========================================================================
# animation strips: (bitmap, x, y, body_x) per tick, both facings
# ===========================================================================
SEQS = {
    "IDLE": ["FLOAT1"] * 6 + ["FLOAT2"] * 6,               # gh_idle 12 ticks (6 + 6)
    "FLY": ["FLOAT2"] * 12,                                 # gh_fly: FLOAT2 held, gliding
    "ATTACK": ["FLOAT1"] * 3 + ["FLOAT2"] * 2 + ["LUNGE"] * 2 + ["FLOAT1"] * 3,
    "HURT/DEATH": ["FLOAT1"] * 2 + ["HURT"] * 3 + ["FLOAT1"] * 2 + ["HURT"] * 3 + ["DEAD"] * 6,
}


def strip(fr, seq, facing, glide):
    W = BW + 2 * len(seq) + 40 if glide else BW + 40
    out = []
    for i, p in enumerate(seq):
        b = fr[p]
        xb = (8 + 2 * i if facing > 0 else W - BW - 8 - 2 * i) if glide else 16
        if facing > 0:
            out.append((b, xb, 1, xb))
        else:
            out.append((np.fliplr(b), xb - (b.shape[1] - BW), 1, xb))
    return out, W, H + 2


def gif(path, rows, W, Hh, ink, scale=3, ms=120):
    imgs = []
    for i in range(len(rows[0])):
        a = np.full((Hh * len(rows), W, 3), N.BG, np.uint8)
        for r, tk in enumerate(rows):
            sub = a[r * Hh:(r + 1) * Hh]
            b, x, y, _xb = tk[i]
            N.blit(sub, b, x, y, ink)
        imgs.append(Image.fromarray(a).resize((W * scale, a.shape[0] * scale), Image.NEAREST))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0)


def sheet(path, rows, scale=3):
    ims = []
    for lab, cells in rows:
        hh = H + 4
        ps = []
        for b, ink in cells:
            a = np.full((hh, b.shape[1] + 4, 3), N.BG, np.uint8)
            N.blit(a, b, 2, 2, ink)
            ps.append(Image.fromarray(a).resize((a.shape[1] * scale, hh * scale), Image.NEAREST))
        r = Image.new("RGB", (190 + sum(p.width + 6 for p in ps), hh * scale + 6), N.BG)
        ImageDraw.Draw(r).text((4, 4), lab, fill=(255, 255, 120))
        x = 190
        for p in ps:
            r.paste(p, (x, 3))
            x += p.width + 6
        ims.append(r)
    sh = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims)), N.BG)
    y = 0
    for i in ims:
        sh.paste(i, (0, y))
        y += i.height
    sh.save(path)


# ===========================================================================
def main() -> int:
    for d in (GRID_OUT, ANIM):
        os.makedirs(d, exist_ok=True)
    bad = []
    res, pk, blk = {}, {}, {}
    pool = sum(N.pool(H, w, 0, BW, f) for _n, _p, f, w in FRAMES)
    with tempfile.TemporaryDirectory() as td:
        for o, (title, fn) in OPTIONS.items():
            fr, hem = fn()
            res[o] = fr
            raws = []
            for name, pose, flag, w in FRAMES:
                b = fr[pose]
                if b.shape != (H, w):
                    bad.append(f"{o} {name}: shape {b.shape}")
                solid = S.make_mask(b, outline=True)
                nm = f"{name}_{o.lower()}"
                g = os.path.join(GRID_OUT, nm + ".grid")
                with open(g, "w") as fh:
                    fh.write(A.grid_text(nm, b, solid, f"GHOST {o} {title} {pose}", INKS[0][1],
                                         f"ART17 ghost option {o} ({title}), {flag}, ax 0, body {BW}; "
                                         "tools/gen_art17.py; not imported")
                             .replace("tools/gen_art2_options.py", "tools/gen_art17.py"))
                for _lab, ink in INKS:
                    raw = A.pack_check(f"{nm}_{ink[1:]}", g, b, solid, ink, td)
                raws.append((nm, raw))
            pk[o], blk[o] = packed_kind(raws, td)
            f1, f2 = fr["FLOAT1"], fr["FLOAT2"]
            if not np.array_equal(f2[1:hem + 1], f1[:hem]) or f1[H - 1].any():
                bad.append(f"{o}: bob rule (FLOAT2 = FLOAT1 + 1 px above the hem)")
        gf = dict(zp.game_frames())
        cur, cur_blk = packed_kind([(n, gf[n]) for n in NAMES], td)
    ref = cur_bitmaps()

    def fit(d):
        if d <= 0:
            return "saves" if d < 0 else "same"
        if d <= SRC6_FREE:
            return f"fits the {SRC6_FREE} B free"
        pages = -(-(d - SRC6_FREE) // 256)
        return (f"OVER by {d - SRC6_FREE} B -> +{pages} SRC6 page: POOL_CAP -{256 * pages} on EVERY level "
                f"(D8 slack {POOL_SLACK_D8:,} -> {POOL_SLACK_D8 - 256 * pages:,}, nun needs 2,080)")

    L = ["# ART17 Ghost side-view options — costs (tools/gen_art17.py).",
         "# pool = src/defs.asm FRM formula (both facings, one shift per flag); packed = zx0 with",
         "# the zx0_sources.partition rule (<= 4 frames a block), today's frames from zx0_pack.game_frames.",
         f"# SRC6: {SRC6_FREE} B free of 16 pages; each further page costs 256 B of POOL_CAP on EVERY level.",
         "",
         "GHOST frames (src/frames.asm KFID_GHOST, also K_POLTERGEIST): float1 24x32 WK0, float2 24x32 MOT,",
         "  lunge 32x32 STA, hurt 24x32 STA, dead 24x32 STA (own DEAD); ax 0, body 24.",
         f"  pool {pool} B per Ghost level (384 + 896 + 512 + 384 + 384) -- UNCHANGED by every option (drop-in)",
         "  frame ids 0, engine 0, pool 0: only the packed SRC6 bytes move.",
         f"  today  packed {cur} B  ({', '.join(cur_blk)})"]
    for o, (title, _fn) in OPTIONS.items():
        d = pk[o] - cur
        L.append(f"  {o} {title:18s} packed {pk[o]} B  delta {d:+d} B SRC6  ({fit(d)})  [{', '.join(blk[o])}]")
    with open(os.path.join(OUT, "costs.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")

    # ---- board ---------------------------------------------------------------
    bd = [N.heading("F3r ART17 — GHOST, SIDE VIEW + SCARIER (3 OPTIONS)"),
          N.sub("Concept, not imported. Drop-in for the 5 Ghost frames: same slots, sizes, flags (FLOAT1 "
                "WK0, FLOAT2 MOT, LUNGE / HURT / DEAD STA), ax 0, cycles; pool and frame ids unchanged. "
                "Profiles face right (left = engine mirror). FLOAT2 = FLOAT1 1 px lower, only the tatters "
                "move (the idle bob). Ink $45 bright cyan (K_GHOST); the Poltergeist draws the same frames "
                "in $03. One ink + black paper: every cell 2-colour, no FLASH."),
          N.heading("F3r GHOST TODAY"),
          N.sub(f"packed {cur} B"),
          N.row([S.svg_artboard_html(b, INKS[0][1], n.upper().replace("_", " ")) for n, b in ref.items()])]
    for o, (title, _fn) in OPTIONS.items():
        bd.append(N.heading(f"F3r GHOST {o} — {title}"))
        bd.append(N.sub(f"packed {pk[o]} B (today {cur} B, {pk[o] - cur:+d} B SRC6; pool +0)"))
        bd.append(N.row([S.svg_artboard_html(res[o][p], INKS[0][1], f"GHOST {o} {p}")
                         for _n, p, _f, _w in FRAMES]))
        cells = []
        for lab, seq in SEQS.items():
            glide = lab == "FLY"
            rows = [strip(res[o], seq, fc, glide)[0] for fc in (1, -1)]
            _t, W, Hh = strip(res[o], seq, 1, glide)
            cells.append(N.anim_svg(rows, INKS[0][1], W, Hh, f"GHOST {o} {lab}", dur_ms=120))
            gif(os.path.join(ANIM, f"ghost_{o.lower()}_{lab.split('/')[0].lower()}.gif"), rows, W, Hh,
                INKS[0][1])
        rows = [strip(res[o], SEQS["IDLE"], 1, False)[0]]
        _t, W, Hh = strip(res[o], SEQS["IDLE"], 1, False)
        cells.append(N.anim_svg(rows, INKS[1][1], W, Hh, f"POLTERGEIST {o} IDLE ($03)", dur_ms=120))
        bd.append(N.row(cells))
    with open(os.path.join(OUT, "art17_ghost.svg.html"), "w") as fh:
        fh.write("\n".join(bd) + "\n")
    rows = [("GHOST today", [(b, INKS[0][1]) for b in ref.values()])]
    rows += [(f"GHOST {o} {t}", [(res[o][p], INKS[0][1]) for _n, p, _f, _w in FRAMES])
             for o, (t, _) in OPTIONS.items()]
    sheet(os.path.join(OUT, "art17.png"), rows)
    print("\n".join(L[5:]))
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
