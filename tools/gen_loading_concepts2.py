#!/usr/bin/env python3
"""gen_loading_concepts2.py -- ART18: four more LOADING SCREEN concepts (L1..L4).

CONCEPT ONLY: nothing here is wired into the build (the approved screen stays
assets/gfx/loading/loading_s2d.scr, tools/gen_loading_screen.py).

  L1 THE ABYSS    one-point perspective tunnel of stone ribs; light at the far end,
                  the Warrior 2x silhouetted (black body, rim light) against it.
  L2 THE SHAFT    cutaway of the 8 dungeon levels stacked in a shaft; the Warrior
                  at the top, small fauna per level, the Archmage in a red glow at D8.
  L3 THE TOME     monochrome green: the Tome of Absolute Death Magic on its lectern
                  radiating, Warrior and Mage (2x) facing it in side view.
  L5 THE MOUTH    L1 x L3 (user 2026-10-31): cave mouth, ladder down the middle,
                  the Tome glowing at the vanishing point, both heroes silhouetted.
  L6-L9 (user 2026-10-31, no Archmage anywhere): L6 THE DOOR, L7 THE DROP,
                  L8 THE PHARAOH'S CRYPT, L9 THE LAST CAMP (see their docstrings / notes).
  L10-L13 (user 2026-10-31, no Archmage): L10 THE SKULL GATE, L11 THE TOWER UNDER THE
                  MOON, L12 THE CREST, L13 THE CIRCLE.
  L3a-L3c (user 2026-10-31): L3 with more colour -- a torches + shaded walls,
                  b multicolour rays + dais + torch stands, c crypt colonnade;
                  concepts2_l3_variants.png = L3 + a + b + c side by side.
  L3d (user 2026-11-01): L3c redrawn at native resolution -- hand-built 48x64 Warrior /
                  Mage, native torches / columns / Tome / lectern / rune circle;
                  concepts2_l3d.png = L3c vs L3d (3x, 1:1, 4x crops of the hero aisles).
  L4 THE GALLERY  crypt arcade: 7 monsters in gothic niches (Archmage centre),
                  Ogre / Ghost / Spider / Bat facing the heroes below, title plaque.

Deterministic: shapes + ordered dither + the game's own fonts / torch and the
approved sprite grids (sprites40 / sprites .grid, read in place). No raster
input. The composer paints per-pixel colour indices; gen_loading_screen.Scr
.resolve() enforces <= 2 colours / one BRIGHT per 8x8 cell (aborts on a clash,
never quantises), and validate() below re-checks independently: the .scr
decodes pixel-exact to the intended composition and rows 22-23 are blank (the
ROM clears them while the next header loads).

Outputs (assets/gfx/loading/concepts2/):
  l{1..4}_<name>.scr        6,912 B SCREEN$ ($4000 layout + attrs)
  l{1..4}_<name>.png        3x preview decoded from the .scr
  l{1..4}_<name>_grid.png   3x preview + attribute-cell grid
  concepts2_sheet.png       all thirteen, 4x4 grid (2x)

Usage: python3 tools/gen_loading_concepts2.py
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_loading_screen as G  # noqa: E402  (Scr, fonts, torch, .scr I/O)
from gen_loading_screen import (B, BLUE, CYAN, GREEN, MAG, NONE, RED,  # noqa: E402
                                WHITE, YEL, H, W, Scr, box, centre, dith, hsh)

ROOT = G.ROOT
OUT = os.path.join(ROOT, "assets", "gfx", "loading", "concepts2")
SP40 = os.path.join(ROOT, "assets", "gfx", "sprites40", "grid")
SP48 = os.path.join(ROOT, "assets", "gfx", "sprites", "grid")
ICONS = os.path.join(ROOT, "assets", "gfx", "icons")
TITLE = "TOME OF THE DEAD"
SUB = G.SUB
CREDIT = G.CREDIT


BONE = np.array([[ch == "#" for ch in r] for r in ("##....##", ".######.", "##....##")])


# ---------------------------------------------------------------- sprite grids
def grid(path: str) -> list[str]:
    """3-state .grid rows ('#' ink, '+' opaque paper, '.' transparent), cropped
    to the opaque bbox. Header lines are '# ...' / '#'; rows never contain ' '."""
    rows = []
    for ln in open(path):
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("# ") or ln == "#" or ln.startswith("==="):
            continue
        rows.append(ln)
    ys = [i for i, r in enumerate(rows) if r.strip(".")]
    xs = [j for r in rows for j, ch in enumerate(r) if ch != "."]
    x0, x1 = min(xs), max(xs) + 1
    return [r[x0:x1].ljust(x1 - x0, ".") for r in rows[ys[0]:ys[-1] + 1]]


def g40(name):
    return grid(os.path.join(SP40, name + ".grid"))


def g48(name):
    return grid(os.path.join(SP48, name + ".grid"))


def masks(rows, mirror=False, scale=1):
    ink = np.array([[ch == "#" for ch in r] for r in rows])
    opq = np.array([[ch != "." for ch in r] for r in rows])
    if mirror:
        ink, opq = ink[:, ::-1], opq[:, ::-1]
    if scale > 1:
        ink = ink.repeat(scale, 0).repeat(scale, 1)
        opq = opq.repeat(scale, 0).repeat(scale, 1)
    return ink, opq


def dilate(m, n=1):
    for _ in range(n):
        p = np.pad(m, 1)
        d = np.zeros_like(p)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                d |= np.roll(np.roll(p, dy, 0), dx, 1)
        m = d[1:-1, 1:-1] | m
    return m


def stamp(s: Scr, rows, x0, y0, c, mirror=False, scale=1, halo=1, floor=None):
    """Sprite: halo px cleared round the silhouette, '+' cleared, '#' in c.
    floor: if given, y0 is ignored and the feet sit on row `floor - 1`."""
    ink, opq = masks(rows, mirror, scale)
    h, w = ink.shape
    if floor is not None:
        y0 = floor - h
    if halo:
        big = dilate(np.pad(opq, halo), halo)
        for y, x in zip(*np.nonzero(big)):
            s.clr(x0 + x - halo, y0 + y - halo)
    for y, x in zip(*np.nonzero(opq)):
        X, Y = x0 + x, y0 + y
        if ink[y, x]:
            s.put(X, Y, c(X, Y) if callable(c) else c)
        else:
            s.clr(X, Y)
    return x0, y0, w, h


def cells_of(x0, y0, w, h, pad=0):
    return {(c, r) for c in range(max(0, (x0 - pad) // 8), min(32, (x0 + w + pad - 1) // 8 + 1))
            for r in range(max(0, (y0 - pad) // 8), min(24, (y0 + h + pad - 1) // 8 + 1))}


def line(s: Scr, x0, y0, x1, y1, c, keep=None):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(n + 1):
        t = i / max(n, 1)
        x, y = int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t))
        if keep is None or keep(x, y):
            s.put(x, y, c(x, y) if callable(c) else c)


def text_c(s: Scr, txt, y, c):
    s.text6(txt, centre(len(txt) * 6), y, c)


def title_line(bw, bh, gap, chamfer=True):
    return G.logo5(TITLE, bw, bh, gap, chamfer)


# ================================================================ L1 THE ABYSS
def l1() -> Scr:
    s = Scr()
    # -- title, one line of 3x3 block letters (237 px), fire chrome rows 0-2
    lg = G.chrome(title_line(3, 3, 2), [6, 13])
    s.bits(lg, centre(lg.shape[1]), 1, G.by_row([YEL + B, RED + B, RED], 0))

    # -- tunnel: rows 3-19 (y 24..159), vanishing point (128, 92)
    Y0, Y1, CX, CY, HW, HH = 24, 160, 128, 92, 128.0, 68.0
    K = 0.74                       # plane spacing (scale ratio per stone rib)
    S_OPEN = 0.30                  # far opening (the light)
    RAMP = [BLUE, MAG, RED, RED + B, YEL, YEL + B, WHITE + B]

    def sval(x, y):
        return max(abs(x + 0.5 - CX) / HW, abs(y + 0.5 - CY) / HH)

    def cone(x, y):  # the path of light on the floor (world |X| < 40)
        dy = y + 0.5 - CY
        if dy <= 0 or abs(x + 0.5 - CX) / HW > dy / HH:
            return False
        sv = dy / HH
        return abs((x + 0.5 - CX) / sv) < 40

    def cell_ink(c, r):
        x, y = c * 8 + 4, r * 8 + 4
        sv = sval(x, y)
        if sv < S_OPEN:
            return WHITE + B
        i = int((1 - (sv - S_OPEN) / (1 - S_OPEN)) * 6.2)
        if cone(x, y):
            i += 2
        return RAMP[max(0, min(6, i))]

    ink = lambda x, y: cell_ink(x // 8, y // 8)
    u_of = lambda sv: math.log(sv) / math.log(K)
    for y in range(Y0, Y1):
        for x in range(W):
            sv = sval(x, y)
            dx, dy = x + 0.5 - CX, y + 0.5 - CY
            if sv < S_OPEN:  # far opening: radial white glow
                if dith(x, y, 1.0 - 0.8 * (sv / S_OPEN) ** 5):
                    s.put(x, y, WHITE + B)
                continue
            u = u_of(sv)
            rib = abs(u - round(u)) * (sv * HW) * (1 - K) < 0.55 or \
                abs(u - round(u)) * (sv * HW) * (1 - K) < 1.2 and round(u) <= 1
            on = rib
            wall = abs(dx) / HW >= abs(dy) / HH
            if wall:
                Yw = dy / sv
                Yp = (dy - 1) / sv
                course = math.floor(Yw / 11)
                if course != math.floor(Yp / 11):
                    on = True
                ux = u_of(max(abs(dx + (1 if dx < 0 else -1)) / HW, 1e-3))
                ph = 0.5 * (course & 1)
                if math.floor(2 * u + ph) != math.floor(2 * ux + ph):
                    on = True
            elif dy > 0:  # floor flagstones
                Xw, Xp = dx / sv, (dx - 1) / sv
                if math.floor(Xw / 26) != math.floor(Xp / 26):
                    on = True
                up = u_of((dy - 1) / HH) if dy > 1 else u
                if math.floor(2 * u) != math.floor(2 * up):
                    on = True
            else:  # ceiling: barrel seams only, sparse
                Xw, Xp = dx / sv, (dx - 1) / sv
                if math.floor(Xw / 52) != math.floor(Xp / 52):
                    on = True
            # light spill: dither falling off from the opening; the floor cone glows
            glow = max(0.0, 0.42 - 1.1 * (sv - S_OPEN))
            if cone(x, y):
                glow = max(glow, 1.0 - 0.5 * sv)
            if on or dith(x, y, glow):
                s.put(x, y, ink(x, y))
    # corner edges of the tunnel
    for (ex, ey) in ((0, Y0), (W - 1, Y0), (0, Y1 - 1), (W - 1, Y1 - 1)):
        tx = CX + (ex - CX) * S_OPEN
        ty = CY + (ey + 0.5 - CY) * S_OPEN
        line(s, ex, ey, tx, ty, ink)

    # -- the Warrior 2x (wind-up, sword raised), a black silhouette with rim light, standing in the cone
    kn = g40("knight_windup")
    inkm, opq = masks(kn, scale=2)
    opq = opq & ~(dilate(~np.pad(opq, 1), 1)[1:-1, 1:-1])   # drop the mask's 1-px paper outline
    h, w = opq.shape
    x0, y0 = CX - w // 2, Y1 - 3 - h
    # body black, 1-px outer rim in the cell's ink: against the light the body
    # reads as a cut-out, in the dim cells the rim alone draws the figure
    rim = dilate(np.pad(opq, 1), 1) & ~np.pad(opq, 1)
    for y, x in zip(*np.nonzero(opq)):
        s.clr(x0 + x, y0 + y)
    for y, x in zip(*np.nonzero(rim)):
        s.put(x0 + x - 1, y0 + y - 1, ink(x0 + x - 1, y0 + y - 1))

    text_c(s, SUB, 160, YEL)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Paper black; one ink per cell. Title: 3x3 block letters in one 252-px line, fire chrome Y+ R+ R.",
        "Tunnel rows 3-19: one-point perspective (stone ribs every 0.74 scale, coursed walls, flagstone",
        "floor, barrel-seam ceiling). Cell ink = depth ramp B M R R+ Y Y+ W+ toward the far opening;",
        "the floor cone of light lifts its cells 2 steps. Light spill = ordered dither by depth.",
        "Warrior wind-up 2x as a black silhouette with a 1-px rim in the cell's ink (cone + light behind).",
    ]
    return s


# ================================================================ L2 THE SHAFT
def l2() -> Scr:
    s = Scr()
    SX0, SX1 = 17 * 8, 31 * 8           # shaft interior cols 17-30
    # level bands (row0, nrows): D1 big (hero), D2-D7 two rows, D8 Sanctum
    bands = [(0, 5)] + [(5 + 2 * i, 2) for i in range(6)] + [(17, 5)]
    inks = [WHITE + B, WHITE, CYAN + B, CYAN, BLUE + B, MAG, RED, RED + B]
    ladder_x = [SX0 + 88, SX0 + 16, SX0 + 80, SX0 + 24, SX0 + 72, SX0 + 8, SX0 + 56]
    for k, (r0, n) in enumerate(bands):
        c = inks[k]
        ytop, ybot = r0 * 8, (r0 + n) * 8 - 1
        # back wall bricks, mortar dithered away with depth
        dens = 0.9 - 0.08 * k
        for y in range(ytop, ybot - 1):
            for x in range(SX0, SX1):
                yy = y - ytop
                mort = (yy % 5 == 4) or ((x + (5 if (yy // 5) & 1 else 0)) % 10 == 0)
                if k < 7 and mort and dith(x, y, dens * 0.4):
                    s.put(x, y, c)
        # floor slab (2 px) with the ladder hole
        for x in range(SX0, SX1):
            if k < 7 and ladder_x[k] - 1 <= x < ladder_x[k] + 9:
                continue
            s.put(x, ybot, c)
            if x % 2 == 0 or k == 7:
                s.put(x, ybot - 1, c)
        # ladder down from the level above (lands on this floor)
        if k > 0:
            lx = ladder_x[k - 1]
            s.clear_rect(lx - 1, ytop, 10, ybot - ytop)
            for y in range(ytop, ybot - 1):
                s.put(lx, y, c)
                s.put(lx + 7, y, c)
                if (y - ytop) % 4 == 1:
                    for x in range(lx, lx + 8):
                        s.put(x, y, c)
        # depth number in col 16 (rock column) at the floor row
        s.text6(str(k + 1), 16 * 8 + 1, (r0 + n - 1) * 8, c)

    # rock col 31 and the strata on the left of the shaft: blue dither + fossils
    for y in range(0, 176):
        for x in range(31 * 8, W):
            if dith(x, y, 0.3 + 0.2 * ((hsh(x // 4, y // 4, 3) % 3) == 0)):
                s.put(x, y, BLUE)

    # D1: torch, hero at the lip of the ladder
    s.clear_rect(29 * 8, 0, 16, 32)
    G.place_torch(s, 29, 0)
    stamp(s, G.KNIGHT, SX0 + 20, 0, WHITE + B, floor=38)
    # D2-D7 fauna (cropped to the 14-px headroom above the slab)
    fauna = [(1, g48("bat_glide"), SX0 + 56, False), (2, g48("rat_run1"), SX0 + 36, True),
             (3, g48("slime_wobble"), SX0 + 48, False), (4, g48("spider_walk1"), SX0 + 28, True),
             (5, g48("item_chest"), SX0 + 84, False), (6, G.SKULL, SX0 + 26, False)]
    for k, rows, x, mir in fauna:
        r0, n = bands[k]
        ybot = (r0 + n) * 8 - 2
        rows = rows[-14:]
        stamp(s, rows, x, 0, inks[k], mirror=mir, floor=ybot)

    # D8 Sanctum: red glow + Archmage + the Tome on a pedestal
    r0, n = bands[7]
    gcx, gcy = SX0 + 40, r0 * 8 + 18
    tome_cells = box(27, 19, 2, 2)
    for y in range(r0 * 8, (r0 + n) * 8 - 2):
        for x in range(SX0, SX1):
            if (x // 8, y // 8) in tome_cells:
                continue
            d = math.hypot((x - gcx) / 1.6, y - gcy)
            if dith(x, y, max(0.0, 0.7 - d / 34)) or (int(d) % 9 == 0 and dith(x, y, 0.5)):
                s.put(x, y, RED + B)
    stamp(s, g40("nun_cast"), gcx - 12, 0, RED + B, floor=(r0 + n) * 8, halo=2)  # she glides: hem on the slab
    book = [r for r in open(os.path.join(ICONS, "book.grid")) if not r.startswith("#")]
    book = [r.rstrip("\n") for r in book if r.strip()]
    bk = np.array([[ch == "#" for ch in r] for r in book])
    s.clear_rect(27 * 8, 19 * 8, 16, 16)
    s.bits(bk, 27 * 8, 19 * 8 - 1, YEL + B)
    s.bits(np.ones((1, 12), bool), 27 * 8 + 2, 20 * 8 + 7, YEL + B)

    # left panel: stacked title, legend text, an earth cutaway between
    lines = ["TOME", "OF THE", "DEAD"]
    grad = G.by_row([YEL + B, YEL + B, YEL, RED + B, RED + B, RED, MAG + B, MAG + B, MAG, MAG, MAG], 1)
    used = set()
    for i, t in enumerate(lines):
        lg = G.chrome(G.logo5(t, 3, 4, 3), [9, 18])
        x0 = (17 * 8 - 8 - lg.shape[1]) // 2
        y0 = 8 + 32 * i
        s.bits(lg, x0, y0, grad)
        used |= cells_of(x0, y0, lg.shape[1], lg.shape[0])
    legend = ["EIGHT LEVELS DOWN", "THE ARCHMAGE WAITS", "WITH THE TOME", "",
              "A DUNGEON ROGUELIKE", "ZX SPECTRUM 128K", CREDIT]
    lc = [CYAN, CYAN, CYAN, None, WHITE + B, WHITE + B, WHITE]
    for i, (t, c) in enumerate(zip(legend, lc)):
        if c is None:
            continue
        y = 15 * 8 + i * 8 - 8
        x0 = (17 * 8 - 8 - len(t) * 6) // 2
        s.text6(t, x0, y, c)
        used |= cells_of(x0, y, len(t) * 6, 8)
    used |= {(c + d, r) for (c, r) in used for d in (-1, 1)}
    # strata in the free left cells: wavy blue lines + bone fossils (white)
    for r in range(22):
        for c in range(16):
            if (c, r) in used:
                continue
            fossil = hsh(c, r, 11) % 11 == 0
            for y in range(r * 8, r * 8 + 8):
                for x in range(c * 8, c * 8 + 8):
                    wave = int(3 * math.sin(x / 11 + y // 12))
                    if not fossil and (y + wave) % 12 == 0 and dith(x, y, 0.55):
                        s.put(x, y, BLUE)
            if fossil:  # a small bone, knobbed at both ends
                s.bits(BONE, c * 8, r * 8 + 2 + hsh(c, r) % 3, WHITE)
    s.notes = [
        "Paper black; one ink per cell. Shaft = cols 17-30, rock col 31 (B dither), depth numbers col 16.",
        "Bands: D1 rows 0-4 (W+, Warrior + game torch), D2-D7 two rows each (W C+ C B+ M R), D8 Sanctum",
        "rows 17-21 (R+ glow, Archmage 40 px with a 2-px halo); the Tome icon in its own Y+ cells.",
        "Every band owns whole cell rows, so ladders / bricks / fauna take the band ink with no clash.",
        "Left: stacked title (fire->magenta per row), legend text, strata (B) with bone fossils (W).",
    ]
    return s


# ================================================================ L3 THE TOME
def l3() -> Scr:
    s = Scr()
    G_ = GREEN + B
    # -- title: menu font glyphs 2x, cropped to their ink + 2-px tracking (fits
    #    256 px), chrome stripes, W+ (rows 0-3)
    parts = []
    for ch in TITLE:
        g = G.FONT16[ch]
        cs = np.nonzero(g.any(0))[0]
        parts.append(g[:, cs[0]:cs[-1] + 1] if len(cs) else np.zeros((16, 3), bool))
        parts.append(np.zeros((16, 1), bool))
    bm = np.hstack(parts[:-1]).repeat(2, 0).repeat(2, 1)
    bm = G.chrome(bm, [5, 11, 17, 23])
    assert bm.shape[1] <= W, bm.shape
    s.bits(bm, centre(bm.shape[1]), 0, WHITE + B)

    FLOOR = 152
    BX, BY = 128, 100                        # tome centre
    # -- radiance: rays + concentric dither, rows 4-18
    nrays = 14
    for y in range(32, FLOOR):
        for x in range(W):
            dx, dy = x + 0.5 - BX, (y + 0.5 - BY) * 1.25
            r = math.hypot(dx, dy)
            a = math.atan2(dy, dx)
            ph = (a / (2 * math.pi) * nrays + 0.25) % 1.0
            ray = abs(ph - 0.5) < 0.09 * (1 - min(r, 170) / 260)
            core = max(0.0, 1.0 - r / 64) ** 1.3
            ring = abs(r % 14 - 7) < 0.6 and r < 90
            if (ray and dith(x, y, 0.85 - r / 300)) or dith(x, y, core * 0.9) or (ring and dith(x, y, 0.5)):
                s.put(x, y, G_)
    # -- floor + reflection
    for x in range(W):
        s.put(x, FLOOR, G_)
        for y in range(FLOOR + 2, 160):
            if dith(x, y, max(0.0, 0.5 - abs(x - BX) / 160) * (1 - (y - FLOOR) / 8)):
                s.put(x, y, G_)

    # -- lectern: slanted top, carved column, stepped base (black halo round it)
    lec = np.zeros((H, W), bool)
    for y in range(116, FLOOR):
        hw = 6 if y < 140 else (10 if y < 146 else 16)
        if y < 124:
            hw = 18 - (y - 116)
        for x in range(BX - hw, BX + hw):
            lec[y, x] = True
    lec_cut = np.zeros_like(lec)
    for y in range(124, 140, 4):
        lec_cut[y, BX - 3:BX + 3] = True
    # -- the Tome: open book, curved pages, skull page left, sigil page right
    book = np.zeros((H, W), bool)
    detail = np.zeros((H, W), bool)
    for x in range(BX - 40, BX + 40):
        t = abs(x + 0.5 - BX) / 40
        top = int(BY - 12 + 7 * t - 9 * math.sin(math.pi * min(1, t * 1.1)) * 0.6)
        bot = top + 26 - int(3 * t)
        book[top:bot + 3, x] = True                   # pages + cover rim
        detail[bot, x] = True                         # page / cover seam
        if abs(x - BX) < 1:
            detail[top:bot, x] = True                 # spine gutter
    # skull on the left page: the game skull, black-outlined, its holes black
    sk = G.SKULL_BM
    ring = dilate(np.pad(sk, 1), 1)
    sx0, sy0 = BX - 31, BY - 13
    for y, x in zip(*np.nonzero(ring)):
        if not np.pad(sk, 1)[y, x]:
            detail[sy0 + y, sx0 + x] = True
    # sigil (pentacle-ish star) on the right page
    for i in range(5):
        a1, a2 = -math.pi / 2 + i * 4 * math.pi / 5, -math.pi / 2 + (i + 1) * 4 * math.pi / 5
        x1, y1 = BX + 21 + 9 * math.cos(a1), BY - 3 + 9 * math.sin(a1)
        x2, y2 = BX + 21 + 9 * math.cos(a2), BY - 3 + 9 * math.sin(a2)
        n = 24
        for k in range(n + 1):
            detail[int(round(y1 + (y2 - y1) * k / n)), int(round(x1 + (x2 - x1) * k / n))] = True
    for k in range(64):
        a = k * 2 * math.pi / 64
        detail[int(round(BY - 3 + 11 * math.sin(a))), int(round(BX + 21 + 11 * math.cos(a)))] = True
    # carve: black halo round book+lectern, then fill
    solid = book | lec
    halo = dilate(solid, 2) & ~solid
    for y, x in zip(*np.nonzero(halo)):
        s.clr(x, y)
    for y, x in zip(*np.nonzero(solid)):
        s.put(x, y, G_)
    for y, x in zip(*np.nonzero((detail & book) | (lec_cut & lec))):
        s.clr(x, y)
    # rising wisps above the book
    for k in range(3):
        x0 = BX - 16 + 16 * k
        for y in range(52, BY - 18):
            xx = int(x0 + 4 * math.sin((y + 7 * k) / 6))
            if dith(xx, y, 0.9):
                s.put(xx, y, G_)
                s.clr(xx + 1, y)
                s.clr(xx - 1, y)

    # -- heroes 2x in side view, facing the tome; same green, 2-px black halo
    stamp(s, G.KNIGHT, 12, 0, G_, scale=2, halo=2, floor=FLOOR)
    stamp(s, G.MAGE_CAST, W - 12 - 64, 0, G_, scale=2, halo=2, floor=FLOOR, mirror=True)

    text_c(s, "THE TOME OF ABSOLUTE DEATH MAGIC", 160, G_)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Monochrome: every scene cell is G+ on black (one colour, bright), title W+, credit W.",
        "Radiance = 14 rays + core falloff + ripple rings (ordered dither) from the tome at (128,100).",
        "Tome: open book with curved pages, skull page (game skull) + sigil page, on a lectern;",
        "2-px black halo carves it out of the glow. Warrior idle / Mage cast 2x, mirrored to face it.",
    ]
    return s


# ================================================================ L4 THE GALLERY
def l4() -> Scr:
    s = Scr()
    STONE = BLUE + B
    # niche plan: outer pillars 2 cols, inner 1 col, centre niche 4 cols
    niches = []
    c = 2
    for i in range(7):
        wdt = 4 if i == 3 else 3
        niches.append((c, wdt))
        c += wdt + 1
    assert c - 1 == 30, c
    cast = [("skeleton_walk1", 40, WHITE, False), ("orc_walk1", 40, GREEN, False),
            ("vamp_walk1", 40, CYAN, False), ("nun_cast", 40, GREEN + B, False),
            ("mummy_walk1", 40, YEL, True), ("necro_walk1", 40, MAG + B, True),
            ("dk_walk1", 48, RED + B, True)]
    ARCH_R0, MON_R0, MON_R1 = 0, 3, 9           # arch rows 0-2, figures rows 3-8, plinth row 9
    niche_cells = set()
    for (c0, wdt), (name, sz, ink, mir) in zip(niches, cast):
        x0, x1 = c0 * 8, (c0 + wdt) * 8
        niche_cells |= box(c0, MON_R0, wdt, MON_R1 - MON_R0)
        rows = g40(name) if sz == 40 else g48(name)
        # candle glow behind the figure: faint dither of its ink, rising from the plinth
        for y in range(MON_R0 * 8, MON_R1 * 8):
            for x in range(x0, x1):
                f = (y - MON_R0 * 8) / ((MON_R1 - MON_R0) * 8)
                if dith(x, y, 0.28 * f * f):
                    s.put(x, y, ink)
        ww = len(rows[0])
        stamp(s, rows, x0 + (x1 - x0 - ww) // 2, 0, ink, mirror=mir, floor=MON_R1 * 8, halo=1)
        # pointed (gothic) arch in rows 0-2 over the niche, stone
        cx = (x0 + x1) / 2
        half = (x1 - x0) / 2
        for y in range(ARCH_R0 * 8 + 2, MON_R0 * 8):
            t = (MON_R0 * 8 - y) / (MON_R0 * 8 - 2)
            off = half * math.cos(math.asin(min(1.0, t))) if t < 1 else 0
            for xx in (int(cx - off), int(cx + off) - 1):
                if x0 <= xx < x1:
                    s.put(xx, y, STONE)
            if t > 0.7:
                for xx in range(int(cx - off), int(cx + off)):
                    if x0 <= xx < x1 and dith(xx, y, 0.5):
                        s.put(xx, y, STONE)
        for xx in range(x0, x1):  # plinth slab
            s.put(xx, MON_R1 * 8, STONE)
            s.put(xx, MON_R1 * 8 + 2, STONE)
            if xx % 2:
                s.put(xx, MON_R1 * 8 + 4, STONE)
    # pillars (stone) with brick courses; spandrels above the arches
    torch_c = box(0, 2, 2, 4) | box(30, 2, 2, 4)
    G.bricks(s, sorted({(c, r) for c in range(32) for r in range(0, 10)} - niche_cells - torch_c
                       - {(c, r) for (c0, wdt) in niches for c in range(c0, c0 + wdt) for r in range(0, 3)}
                       - {(c, 9) for (c0, wdt) in niches for c in range(c0, c0 + wdt)}),
             lambda c, r: STONE, bw=8, bh=4, seed=4)
    G.place_torch(s, 0, 2)
    G.place_torch(s, 30, 2)

    # lower crypt rows 10-15: heroes left, the rest of the bestiary facing them
    FLOOR = 16 * 8 - 1                          # feet on y 127; floor line y 128
    stamp(s, G.KNIGHT, 10, 0, WHITE + B, floor=FLOOR + 1)
    stamp(s, G.MAGE, 40, 0, CYAN + B, floor=FLOOR + 1)
    stamp(s, g48("bat_glide"), 92, 86, MAG + B, mirror=True)
    # spider dangling on its thread from the plinth row
    sp = g48("spider_climb1")
    for y in range(10 * 8, 12 * 8 + 2):
        s.put(140, y, CYAN)
    stamp(s, sp, 140 - len(sp[0]) // 2, 12 * 8 + 3, CYAN)
    stamp(s, g48("ghost_float1"), 168, 0, WHITE + B, floor=FLOOR - 6, mirror=True)
    stamp(s, g48("ogre_walk1"), 208, 0, GREEN + B, floor=FLOOR + 1, mirror=True)
    for x in range(W):  # crypt floor = top edge of the title plaque (row 16, W)
        s.put(x, FLOOR + 1, WHITE)
        if x % 2 == 0:
            s.put(x, FLOOR + 3, WHITE)
    # title plaque rows 16-20: hollow block letters, frame in stone
    lg = title_line(3, 3, 2, chamfer=False)
    lg = G.outline_dither(lg, 0.25)
    lx = centre(lg.shape[1])
    s.bits(lg, lx, 17 * 8 + 2, G.by_row([YEL + B, YEL + B, RED + B], 17))
    for x in range(0, W):
        if x % 2 == 0:
            s.put(x, 19 * 8 + 7, RED + B)
    text_c(s, SUB, 20 * 8, CYAN)
    text_c(s, CREDIT, 21 * 8, WHITE)
    s.notes = [
        "Paper black; one ink per cell. Arcade rows 0-9: 7 gothic niches (3 cols, centre 4) between",
        "B+ brick pillars (outer 2 cols carry the game torches). Each niche owns its rows 3-8 cells:",
        "Skeleton W, Orc G, Vampire C, Archmage G+ (centre), Pharaoh Y, Necromancer M+, Death Knight R+,",
        "each over a faint dither glow of its own ink. Lower crypt rows 10-15: Warrior W+ / Mage C+ face",
        "Bat M+, Spider C (on a thread), Ghost W+, Ogre G+. Title rows 16-19 (hollow Y+/R+ between a W floor line and an R+ dotted rule), sub C, credit W.",
    ]
    return s


# ================================================================ L5 THE MOUTH (L1 + L3)
def l5() -> Scr:
    """User 2026-10-31: L1 x L3. Cave mouth, ladder down the middle, the Tome
    glowing far away at the vanishing point, both heroes silhouetted in front."""
    s = Scr()
    lg = G.chrome(title_line(3, 3, 2), [6, 13])
    s.bits(lg, centre(lg.shape[1]), 1, G.by_row([YEL + B, RED + B, RED], 0))

    Y0, Y1, CX, CY, HW, HH = 24, 160, 128, 84, 136.0, 80.0
    K = 0.72
    RAMP = [BLUE, BLUE + B, MAG, RED, RED + B, YEL, YEL + B, WHITE + B]
    S_GLOW = 0.16                    # the Tome's glow (white core)
    core_cells = cells_of(CX - 10, CY - 22, 20, 36)   # tome + lectern + motes: all W+
    HEROES = ((g40("knight_windup"), 40, False), (G.MAGE_CAST, 168, True))
    pool_cells = set()                                 # hero back-light pools: one warm ink
    for rows, xh, mir in HEROES:
        hh, ww = 2 * len(rows), 2 * len(rows[0])
        pool_cells |= cells_of(xh - 4, Y1 - 1 - hh - 4, ww + 8, hh + 4)

    def noise(a, k):  # jagged rock: smooth per-ring wobble of the radius
        return (0.07 * math.sin(5 * a + 1.7 * k) + 0.04 * math.sin(11 * a + 0.9 * k * k)
                + 0.025 * math.sin(23 * a + k))

    def sval(x, y):
        dx, dy = (x + 0.5 - CX) / HW, (y + 0.5 - CY) / HH
        return math.hypot(dx, dy), math.atan2(dy, dx)

    def cell_ink(c, r):
        sv, _ = sval(c * 8 + 4, r * 8 + 4)
        if sv < S_GLOW or (c, r) in core_cells:
            return WHITE + B
        if (c, r) in pool_cells:
            return YEL
        i = int((1 - min(1.0, (sv - S_GLOW) / (1.0 - S_GLOW))) * 7.4)
        return RAMP[max(0, min(7, i))]

    ink = lambda x, y: cell_ink(x // 8, y // 8)
    for y in range(Y0, Y1):
        for x in range(W):
            sv, a = sval(x, y)
            if sv >= 1.0 + noise(a, 0):          # outside the mouth: rock face
                if dith(x, y, 0.22 + 0.12 * (hsh(x // 6, y // 5, 9) % 3 == 0)):
                    s.put(x, y, ink(x, y))
                continue
            on = False
            u = math.log(max(sv, 1e-3)) / math.log(K)
            for k in (math.floor(u), math.ceil(u)):   # jagged rock ribs
                rk = K ** k * (1 + noise(a, k))
                if abs(sv - rk) * HW < 0.6 + 0.5 * (k == 0) and K ** k > S_GLOW:
                    on = True
            # radial cracks between the ribs
            if abs(((a / (2 * math.pi)) * 22 + 0.3 * math.sin(7 * sv)) % 1 - 0.5) < 0.03 / max(sv, 0.2) * 0.25 \
                    and dith(x, y, 0.6) and sv > S_GLOW:
                on = True
            # Tome radiance: core falloff + rays (the L3 language, small and distant)
            core = max(0.0, 1.0 - sv / 0.62) ** 1.3
            ph = (a / (2 * math.pi) * 12 + 0.25) % 1.0
            ray = abs(ph - 0.5) < 0.08 and sv < 0.75
            if on or dith(x, y, core) or (ray and dith(x, y, 0.55 - sv * 0.6)):
                s.put(x, y, ink(x, y))

    # -- the ladder: two rails converging on the vanishing point, perspective rungs
    vy = CY + 18                          # ladder foot of the far end (just below the tome)
    near_l, near_r, far_l, far_r = 100, 156, 122, 134
    lad = np.zeros((H, W), bool)
    rails = []
    for y in range(vy, Y1):
        t = (y - vy) / (Y1 - 1 - vy)
        xl = far_l + (near_l - far_l) * t
        xr = far_r + (near_r - far_r) * t
        rails.append((y, xl, xr))
        lad[y, int(round(xl))] = lad[y, int(round(xr))] = True
        if t > 0.45:  # rails gain thickness toward the viewer
            lad[y, int(round(xl)) + 1] = lad[y, int(round(xr)) - 1] = True
    depth = 0.0
    while True:  # rungs: equal world spacing -> geometric screen spacing
        t = 0.08 * (1.42 ** depth)
        if t > 1:
            break
        y = int(round(vy + t * (Y1 - 1 - vy)))
        _, xl, xr = rails[y - vy]
        lad[y, int(xl):int(xr) + 1] = True
        if t > 0.35:
            lad[y - 1, int(xl):int(xr) + 1] = True
        depth += 1
    for y, x in zip(*np.nonzero(dilate(lad, 1) & ~lad)):
        s.clr(x, y)
    for y, x in zip(*np.nonzero(lad)):
        s.put(x, y, ink(x, y))

    # -- the Tome on its lectern at the vanishing point, tiny, black-haloed in the white core
    tome = ["..##........##..",
            ".#####....#####.",
            "##.#####.#####.#",
            "#.#.####.####.##",
            "#######..#######",
            ".######..######.",
            "......####......",
            ".......##.......",
            ".......##.......",
            ".......##.......",
            "......####......",
            ".....######....."]
    tb = np.array([[ch == "#" for ch in r] for r in tome])
    tx, ty = CX - 8, CY - 2
    for y, x in zip(*np.nonzero(dilate(np.pad(tb, 2), 2))):
        s.clr(tx + x - 2, ty + y - 2)
    s.bits(tb, tx, ty, WHITE + B)
    # light motes rising from the book
    for k in range(-2, 3):
        for y in range(ty - 18, ty - 3):
            xx = int(CX + 5 * k + 2 * math.sin((y + 5 * k) / 3))
            if dith(xx, y, 0.6):
                s.put(xx, y, WHITE + B)

    # -- heroes 2x at the mouth, facing in: black silhouettes against back-light
    for rows, xh, mir in HEROES:
        _, opq = masks(rows, mirror=mir, scale=2)
        opq = opq & ~(dilate(~np.pad(opq, 1), 1)[1:-1, 1:-1])
        h, w = opq.shape
        y0 = Y1 - 1 - h
        # back-light: a soft elliptical pool of dense dither behind the figure
        # (the Tome's light on the cave wall), then the body cut out in black
        hx, hy = xh + w / 2, y0 + h / 2
        for Y in range(max(Y0, y0 - 4), Y1 - 1):
            for X in range(max(0, xh - 4), min(W, xh + w + 4)):
                d = ((X - hx) / (w / 2 + 6)) ** 2 + ((Y - hy) / (h / 2 + 6)) ** 2
                if d < 1 and dith(X, Y, 0.85 * (1 - d) ** 0.5):
                    s.put(X, Y, ink(X, Y))
        for y, x in zip(*np.nonzero(opq)):
            s.clr(xh + x, y0 + y)
    for x in range(W):  # threshold of the mouth
        if not (95 <= x < 162):
            s.put(x, Y1 - 1, ink(x, Y1 - 1))

    text_c(s, SUB, 160, YEL)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "L1 x L3. Paper black; one ink per cell. Title as L1 (3x3 block letters, fire chrome).",
        "Cave rows 3-19: jagged elliptical rock ribs receding to the vanishing point (128,84);",
        "cell ink by depth B B+ M R R+ Y Y+ W+ (cool mouth -> white Tome glow). Rays/core = L3 dither.",
        "Ladder down the middle: converging rails, geometric rung spacing, 1-px black halo.",
        "Tome 16x12 on its lectern, W+ with a 2-px black halo in the white core; motes rising.",
        "Warrior wind-up / Mage cast 2x as black cut-outs on a soft dither pool of light; pool cells all Y (one warm ink).",
    ]
    return s


# ================================================================ L6-L9 (no Archmage)
def sil_mask(rows, mirror=False, scale=1):
    """Filled silhouette of a sprite (opaque mask minus its 1-px paper outline)."""
    _, opq = masks(rows, mirror, scale)
    return opq & ~(dilate(~np.pad(opq, 1), 1)[1:-1, 1:-1])


def backlit(s: Scr, rows, xh, floor, ink, mirror=False, scale=1, pad=6, dens=0.85, top=0, xlim=(0, W)):
    """L5 technique: a soft elliptical pool of dither light, the body cut out black."""
    opq = sil_mask(rows, mirror, scale)
    h, w = opq.shape
    y0 = floor - h
    hx, hy = xh + w / 2, y0 + h / 2
    if dens > 0:
        for Y in range(max(top, y0 - pad), floor):
            for X in range(max(xlim[0], xh - pad), min(xlim[1], xh + w + pad)):
                d = ((X - hx) / (w / 2 + pad)) ** 2 + ((Y - hy) / (h / 2 + pad)) ** 2
                if d < 1 and dith(X, Y, dens * (1 - d) ** 0.5):
                    s.put(X, Y, ink(X, Y) if callable(ink) else ink)
    for y, x in zip(*np.nonzero(opq)):
        s.clr(xh + x, y0 + y)
    return xh, y0, w, h


def fire_title(s: Scr, grad=(YEL + B, RED + B, RED)):
    lg = G.chrome(title_line(3, 3, 2), [6, 13])
    s.bits(lg, centre(lg.shape[1]), 1, G.by_row(list(grad), 0))


def book_bm():
    rows = [r.rstrip("\n") for r in open(os.path.join(ICONS, "book.grid"))
            if r.strip() and not r.startswith("#")]
    return np.array([[ch == "#" for ch in r] for r in rows])


def eyes(s: Scr, ex, ey, c, big=False):
    pts = ((0, 0), (1, 0), (5, 0), (6, 0)) + (((0, 1), (1, 1), (5, 1), (6, 1)) if big else ())
    for (dx, dy) in pts:
        s.put(ex + dx, ey + dy, c)


# ---------------------------------------------------------------- L6 THE DOOR
def l6() -> Scr:
    s = Scr()
    # -- title carved in a stone lintel (rows 0-3): W stone dither, letters cut black
    #    with a solid W edge
    lg = title_line(3, 3, 2, chamfer=False)
    lx, ly = centre(lg.shape[1]), 5
    edge = dilate(np.pad(lg, 1), 1) & ~np.pad(lg, 1)
    for y in range(1, 31):
        for x in range(4, W - 4):
            if y in (1, 30) or x in (4, W - 5) or dith(x, y, 0.3 if (x // 24 + y // 10) % 2 else 0.2):
                s.put(x, y, WHITE)
    for y, x in zip(*np.nonzero(dilate(np.pad(lg, 1), 1))):
        s.clr(lx + x - 1, ly + y - 1)
    for y, x in zip(*np.nonzero(edge)):
        s.put(lx + x - 1, ly + y - 1, WHITE)

    FLOOR = 152
    DX0, DX1, ACY, AR = 72, 184, 96, 56          # door opening + arch (centre y, radius)
    RO = AR + 10
    tl, tr = (4, 9), (26, 9)
    steps = [(2.0, YEL + B), (3.2, RED + B), (4.6, RED)]
    lf = G.light(tl[0] + 1, tl[1] + 0.5, steps)
    rf = G.light(tr[0] + 1, tr[1] + 0.5, steps)
    ring_px = np.zeros((H, W), bool)
    door_px = np.zeros((H, W), bool)
    for y in range(32, FLOOR):
        for x in range(DX0 - 10, DX1 + 10):
            dx, dy = x + 0.5 - 128, y + 0.5 - ACY
            rr = math.hypot(dx, dy)
            inside = (y >= ACY and DX0 <= x < DX1) or (y < ACY and rr < AR)
            ring = (not inside) and ((y >= ACY and (DX0 - 10 <= x < DX0 or DX1 <= x < DX1 + 10))
                                     or (y < ACY and rr < RO))
            door_px[y, x] = inside
            ring_px[y, x] = ring
    door_cells = {(x // 8, y // 8) for y, x in zip(*np.nonzero(ring_px | door_px))}
    torch_cells = box(tl[0], tl[1], 2, 4) | box(tr[0], tr[1], 2, 4)

    def wall(c, r):
        a, b = lf(c, r), rf(c, r)
        return a if a is not None else b
    G.bricks(s, sorted({(c, r) for c in range(32) for r in range(4, 19)} - door_cells - torch_cells),
             wall, seed=6)
    G.place_torch(s, *tl)
    G.place_torch(s, *tr)
    DOOR = YEL + B
    for y, x in zip(*np.nonzero(ring_px)):       # arch ring: voussoirs + jambs, torch-lit
        dx, dy = x + 0.5 - 128, y + 0.5 - ACY
        rr = math.hypot(dx, dy)
        if y < ACY:
            ang = math.degrees(math.atan2(-dy, dx))
            on = rr < AR + 1 or rr >= RO - 1 or any(abs(ang - a) < 50 / rr for a in range(0, 181, 15))
        else:
            xx = x - (DX0 - 10) if x < DX0 else (DX1 + 9 - x)
            on = xx in (0, 9) or (y - ACY) % 10 == 9
        if on or dith(x, y, 0.12):
            s.put(x, y, DOOR)
    for y, x in zip(*np.nonzero(door_px)):       # leaves: planks, iron bands + studs, grain
        band = 76 <= y < 82 or 124 <= y < 130
        plank = (x - DX0) % 14 == 0 or x in (127, 128)
        stud = band and (x - DX0) % 14 == 7 and y in (78, 79, 126, 127)
        if not stud and (band or plank or dith(x, y, 0.45)):
            s.put(x, y, DOOR)
    # keyhole plate: own W+ cells (15-16, 12-13), keyhole + a 4-ray key glint
    s.clear_rect(120, 96, 16, 16)
    for y in range(97, 111):
        for x in range(121, 135):
            if y in (97, 110) or x in (121, 134):
                s.put(x, y, WHITE + B)
    for (x, y) in ((127, 101), (128, 101), (126, 102), (129, 102), (126, 103), (129, 103),
                   (127, 104), (128, 104), (127, 105), (128, 105), (127, 106), (128, 106),
                   (126, 107), (127, 107), (128, 107), (129, 107)):
        s.put(x, y, WHITE + B)
    for k in range(1, 4):
        for (dx, dy) in ((k, 0), (-k, 0), (0, k), (0, -k)):
            s.put(131 + dx, 101 + dy, WHITE + B)
    for x in range(W):                           # flagstone floor
        s.put(x, FLOOR, WHITE)
        if x % 2 == 0:
            s.put(x, FLOOR + 2, WHITE)
        if x % 24 == 12:
            for y in range(FLOOR + 3, FLOOR + 8):
                s.put(x, y, WHITE)
    # heroes 2x: black silhouettes cut out of the lit door (their cells are door cells)
    backlit(s, G.KNIGHT, 70, FLOOR, DOOR, dens=0.0)
    backlit(s, G.MAGE, 138, FLOOR, DOOR, mirror=True, dens=0.0)
    text_c(s, SUB, 160, YEL)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Paper black. Title carved in a W stone lintel (letters cut black, solid W edges), rows 0-3.",
        "Door + arch ring one ink (Y+, torch-lit): planks, iron bands with black studs, grain dither;",
        "wall bricks Y+ / R+ / R by distance from the two game torches (cols 4 / 26).",
        "Keyhole plate = own W+ cells (15-16, 12-13) with a key glint.",
        "Warrior / Mage 2x as black silhouettes against the lit door, facing it.",
    ]
    return s


# ---------------------------------------------------------------- L7 THE DROP
def l7() -> Scr:
    s = Scr()
    fire_title(s, (WHITE + B, CYAN + B, CYAN))
    ROCK, EYE = BLUE, RED + B
    SH0, SH1 = 13, 18                           # shaft cols 13-17
    TOP_FLOOR, BOT_FLOOR = 72, 160              # top corridor rows 4-8, bottom rows 14-19
    pockets = [(1, 11, 3, 5, "skeleton_walk1"), (6, 12, 3, 3, None), (9, 10, 3, 2, None),
               (5, 17, 4, 2, None), (10, 15, 2, 3, None), (1, 17, 2, 2, None),
               (19, 4, 3, 3, None), (23, 4, 3, 5, "orc_walk1"), (28, 3, 3, 3, None),
               (19, 9, 2, 3, None), (28, 8, 3, 3, None)]
    pocket_cells = set()
    for (c, r, w, h, _) in pockets:
        pocket_cells |= box(c, r, w, h)
    open_cells = box(0, 4, SH0, 5) | box(SH0, 3, SH1 - SH0, 17) | box(SH1, 14, 32 - SH1, 6)
    rock_cells = {(c, r) for c in range(32) for r in range(3, 20)} - open_cells - pocket_cells
    G.bricks(s, sorted(rock_cells), lambda c, r: ROCK, bw=12, bh=5, seed=7)
    for (c, r) in rock_cells:                   # solid rock face along every opening
        for y in range(r * 8, r * 8 + 8):
            for x in range(c * 8, c * 8 + 8):
                if ((x % 8 == 7 and (c + 1, r) in open_cells) or (x % 8 == 0 and (c - 1, r) in open_cells)
                        or (y % 8 == 7 and (c, r + 1) in open_cells) or (y % 8 == 0 and (c, r - 1) in open_cells)):
                    s.put(x, y, ROCK)
    # pockets: black holes with a dithered arch lip; R+ eyes; a dotted rim where a monster lurks
    for (c, r, w, h, who) in pockets:
        x0, y0, x1, y1 = c * 8, r * 8, (c + w) * 8, (r + h) * 8
        for x in range(x0, x1):
            t = (x + 0.5 - (x0 + x1) / 2) / ((x1 - x0) / 2)
            for y in range(y0, y0 + int(5 * t * t) + 1):
                if dith(x, y, 0.5):
                    s.put(x, y, EYE)
        if who:
            opq = sil_mask(g40(who), mirror=c > 16)
            hh, ww = opq.shape
            fx, fy = x0 + (x1 - x0 - ww) // 2, y1 - hh
            rim = dilate(np.pad(opq, 1), 1) & ~np.pad(opq, 1)
            for y, x in zip(*np.nonzero(rim)):
                if (x + y) % 2 == 0 and fy + y - 1 >= y0 + 6:
                    s.put(fx + x - 1, fy + y - 1, EYE)
            eyes(s, fx + ww // 2 - 4 + (2 if c > 16 else -2), fy + 7, EYE, big=True)
        else:
            eyes(s, (x0 + x1) // 2 - 3 + hsh(c, r) % 5 - 2, y0 + (y1 - y0) // 2 + 1, EYE, big=w > 2)
    # bottom corridor: eyes in the dark; the Tome's faint green glow at the far end
    for (ex, ey) in ((166, 130), (194, 142), (204, 122)):
        eyes(s, ex, ey, EYE)
    for y in range(112, BOT_FLOOR):
        for x in range(224, W):
            d = math.hypot((x - 244) / 1.3, y - 146)
            if dith(x, y, max(0.0, 0.55 - d / 30)):
                s.put(x, y, GREEN)
    bk = book_bm()
    for y, x in zip(*np.nonzero(dilate(np.pad(bk, 1), 1))):
        s.clr(236 + x - 1, 140 + y - 1)
    s.bits(bk, 236, 140, GREEN)
    for x in range(SH1 * 8, W):
        s.put(x, BOT_FLOOR - 1, GREEN if x >= 224 else ROCK)
    # the ladder: one long drop down the shaft; the climbing Warrior on its lamp pool
    LAD = YEL
    lx0, lx1 = 116, 139
    for y in range(24, BOT_FLOOR):
        if y % 6 == 0:
            for x in range(lx0, lx1 + 1):
                s.put(x, y, LAD)
    for y in range(24, BOT_FLOOR):
        s.put(lx0, y, LAD)
        s.put(lx1, y, LAD)
    # lamp light round the climber (dither in the shaft), the Warrior inked over it
    for y in range(72, 136):
        for x in range(SH0 * 8, SH1 * 8):
            d = math.hypot((x - 128) / 18, (y - 104) / 30)
            if d < 1 and dith(x, y, 0.35 * (1 - d)):
                s.put(x, y, LAD)
    stamp(s, g40("knight_climb1"), 116, 0, LAD, floor=124, halo=2)
    # top corridor: the Mage at the lip, the game torch on the back wall
    stamp(s, G.MAGE, 70, 0, CYAN + B, floor=TOP_FLOOR)
    G.place_torch(s, 2, 4)
    text_c(s, SUB, 160, CYAN)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Paper black. Title W+ C+ C chrome. Side cutaway: top corridor rows 4-8, shaft cols 13-17,",
        "bottom corridor rows 14-19; rock = B bricks. Dark pockets (own cells) hold R+ eyes; two",
        "hold a dotted R+ rim of a lurking Skeleton / Orc. Ladder Y; the climbing Warrior is inked Y",
        "(2-px halo) on a faint lamp-light dither. Mage C+ at the lip by a game torch; the Tome's faint G glow at",
        "the far end of the bottom corridor.",
    ]
    return s


# ---------------------------------------------------------------- L8 THE PHARAOH'S CRYPT
def l8() -> Scr:
    s = Scr()
    fire_title(s, (YEL + B, YEL + B, CYAN + B))
    GOLD, GOLDB, CY_, CYB = YEL, YEL + B, CYAN, CYAN + B
    FLOOR = 159
    sarc = box(13, 4, 6, 12)                      # sarcophagus cols 13-18 rows 4-15
    dais = box(9, 16, 14, 4)
    guards = [(10, 11, False), (19, 11, True), (24, 15, True), (28, 15, True)]
    door = box(0, 9, 7, 11)
    cm = {}
    for c in sarc | dais:
        cm[c] = GOLDB
    for (c, r, _) in guards:
        for cc in box(c, r, 3, 5):
            cm[cc] = CYB
    for c in door:
        cm[c] = GOLD
    ink = lambda x, y: cm.get((x // 8, y // 8), CY_)
    # back wall: hieroglyph registers (cyan), glyph per 6x16 slot from a hash
    for r in range(3, 20):
        for c in range(32):
            if (c, r) in sarc or (c, r) in door or (c, r) in dais:
                continue
            for y in range(r * 8, r * 8 + 8):
                for x in range(c * 8, c * 8 + 8):
                    yy = (y - 24) % 16
                    if yy == 0 and x % 2 == 0:
                        s.put(x, y, ink(x, y))
                        continue
                    lx_, ly_ = x % 6, yy - 4
                    k = hsh(x // 6, (y - 24) // 16, 8) % 6
                    if 0 <= ly_ < 9 and 1 <= lx_ <= 4:
                        on = (k == 0 and (lx_ in (1, 4) or ly_ in (0, 8))) or \
                             (k == 1 and (lx_ == 2 or (ly_ == 2 and lx_ < 4))) or \
                             (k == 2 and (ly_ == 4 or (lx_ in (2, 3) and ly_ < 3))) or \
                             (k == 3 and (lx_ + ly_) % 4 == 0) or \
                             (k == 4 and ly_ in (2, 6))
                        if on:
                            s.put(x, y, ink(x, y))
    # dais: three steps
    for k, (a, b, ty) in enumerate([(11 * 8, 21 * 8, 128), (10 * 8, 22 * 8, 138), (9 * 8, 23 * 8, 148)]):
        for x in range(a, b):
            s.put(x, ty, GOLDB)
            if x % 2 == 0:
                s.put(x, ty + 1, GOLDB)
        for y in range(ty, min(ty + 10, FLOOR + 1)):
            s.put(a, y, GOLDB)
            s.put(b - 1, y, GOLDB)
            for x in range(a + 1, b - 1):
                if dith(x, y, 0.12 + 0.08 * k):
                    s.put(x, y, GOLDB)
    # sarcophagus (anthropoid coffin, upright): nemes headdress, face, crook + flail, bands
    SX, SY, SW, SH = 13 * 8, 4 * 8, 48, 94
    sm = np.zeros((SH, SW), bool)
    for y in range(SH):
        if y < 34:
            hw = 12 + (y * 11) // 34
        elif y < 44:
            hw = 23
        else:
            hw = int(23 - (y - 44) * 8 / 50)
        sm[y, SW // 2 - hw:SW // 2 + hw] = True
    for y in range(3):                            # round the crown
        sm[y, :SW // 2 - 12 + 3 - y] = False
        sm[y, SW // 2 + 12 - 3 + y:] = False
    det = np.zeros_like(sm)
    for y in range(4, 36, 3):
        det[y, :] = True
    face = np.zeros_like(sm)
    face[5:28, 16:32] = True
    det &= ~face
    det |= face & dilate(~face, 1)
    for (ex, ey) in ((19, 12), (20, 12), (21, 12), (26, 12), (27, 12), (28, 12)):
        det[ey, ex] = det[ey + 1, ex] = True
    det[17:21, 23:25] = True
    det[23, 20:28] = True
    det[28:36, 21] = det[28:36, 26] = True       # false beard
    for y in range(46, 62):                       # crossed crook and flail
        t = y - 46
        for d in (0, 1):
            det[y, 10 + t + d] = det[y, 37 - t - d] = True
    det[40, :] = True                             # collar line
    for y in range(66, SH, 6):
        det[y, :] = True
    det[66:SH, 23:25] = True
    for y in range(68, SH - 2, 4):
        det[y, 23:25] = False
    for y, x in zip(*np.nonzero(dilate(np.pad(sm, 2), 2))):
        s.clr(SX + x - 2, SY + y - 2)
    for y, x in zip(*np.nonzero(sm & ~det)):
        s.put(SX + x, SY + y, GOLDB)
    # skeleton honour guard (C+), facing the sarcophagus
    for (c, r, mir) in guards:
        stamp(s, g40("skeleton_walk1"), c * 8, 0, CYB, mirror=mir, floor=min(FLOOR, (r + 5) * 8 - 2))
    # entrance on the left: gold light pouring in, the heroes walking in as silhouettes
    for y in range(9 * 8, FLOOR):
        for x in range(0, 7 * 8):
            d = (x / 56) * 0.55 + abs(y - 124) / 120
            if x in (2, 3) or y in (74, 75) or dith(x, y, max(0.0, 0.9 - d)):
                s.put(x, y, GOLD)
    backlit(s, g40("knight_walk1"), 26, FLOOR, GOLD, dens=0.0)
    backlit(s, g40("wizard_walk1"), 6, FLOOR, GOLD, dens=0.0)
    for x in range(W):
        if (x // 8, 19) not in dais:
            s.put(x, FLOOR, ink(x, FLOOR))
    text_c(s, SUB, 160, YEL)
    text_c(s, CREDIT, 168, CYAN)
    s.notes = [
        "Paper black; gold / cyan. Title Y+ Y+ C+ chrome. Back wall = C hieroglyph registers.",
        "Sarcophagus (anthropoid: nemes stripes, face, beard, crook + flail, wrapped bands) Y+ on a",
        "3-step Y+ dais with a 2-px black halo. Skeleton honour guard C+ (2 on the dais, 2 on the floor).",
        "Left entrance cells Y: gold light pouring in; Warrior + Mage walk in as black silhouettes.",
    ]
    return s


# ---------------------------------------------------------------- L9 THE LAST CAMP
def l9() -> Scr:
    s = Scr()
    fire_title(s)
    LEDGE = 96                                    # ledge top (row 12)
    FX = 60
    glow = G.light(FX / 8, 10.8, [(1.7, YEL + B), (3.8, RED + B), (5.8, RED)])
    rock = {(c, r) for c in range(0, 17) for r in range(3, 6 - (c > 12) - (c > 15))}
    rock |= {(0, r) for r in range(6, 12)}
    rock |= {(c, r) for c in range(0, 13) for r in range(12, 20)}

    def rink(c, r):
        g = glow(c, r)
        return g if g is not None else BLUE
    for (c, r) in rock:
        col = rink(c, r)
        for y in range(r * 8, r * 8 + 8):
            for x in range(c * 8, c * 8 + 8):
                strata = (y + int(3 * math.sin(x / 9 + y // 7))) % 7 == 0
                if (strata and dith(x, y, 0.75)) or dith(x, y, 0.07):
                    s.put(x, y, col)
    for c in range(1, 16):                        # stalactites
        if hsh(c, 3) % 3 == 0:
            continue
        L = 3 + hsh(c, 5) % 7
        x = c * 8 + 3
        for i in range(L):
            for dx in range(-((L - i) // 3), (L - i) // 3 + 1):
                s.put(x + dx, 48 + i, rink(c, 6))
    for x in range(0, 13 * 8):                    # ledge lip
        s.put(x, LEDGE, rink(x // 8, 12))
        if x % 2 == 0:
            s.put(x, LEDGE + 1, rink(x // 8, 12))
    # heroes standing at the fire, black silhouettes on the fire-glow pools
    gl = lambda x, y: rink(x // 8, y // 8)
    backlit(s, G.KNIGHT, 18, LEDGE, gl, pad=8, dens=0.8, top=48)
    backlit(s, G.MAGE, 80, LEDGE, gl, mirror=True, pad=8, dens=0.8, top=48)
    # the fire: flames + crossed logs + sparks, all in the Y+ cells round (FX, 88)
    s.clear_rect(FX - 10, 74, 20, 22)
    flame = ["....#.....", "...##..#..", "..###.##..", ".#####.##.", ".########.",
             "##########", "####.#####", "###...####", ".##....##.", "..#....#.."]
    fb = np.array([[ch == "#" for ch in r] for r in flame]).repeat(2, 0)
    s.bits(fb, FX - 5, 74, YEL + B)
    for k in range(-8, 9):
        s.put(FX + k, 94 - abs(k) // 5, YEL + B)
        s.put(FX + k, 95, YEL + B)
    for (sx, sy) in ((FX - 3, 70), (FX + 4, 66), (FX + 1, 62)):
        s.put(sx, sy, YEL + B)
    # the dungeon beyond: huge dark steps going down to the right
    for k in range(5):
        x0, ty = 13 * 8 + k * 30, LEDGE + 8 + k * 12
        ink = BLUE + B if k < 2 else BLUE
        for x in range(x0, min(W, x0 + 34)):
            s.put(x, ty, ink)
            if x % 2 == 0 and k < 3:
                s.put(x, ty + 1, ink)
        for y in range(ty, min(160, ty + 12)):
            s.put(x0, y, ink)
        for y in range(ty + 2, 160):
            for x in range(x0 + 1, min(W, x0 + 30)):
                if dith(x, y, max(0.0, 0.22 - 0.04 * k - (y - ty) / 220)):
                    s.put(x, y, ink)
    # step cells: the bright top ones must not share cells with the dim ones
    for y in range(LEDGE, 160):
        for x in range(13 * 8, W):
            v = s.px[y, x]
            if v != NONE:
                s.px[y, x] = BLUE + B if (y // 8) < 14 else BLUE
    # distant red eyes in the dark; the Tome's faint green glow at the bottom of the steps
    for (ex, ey) in ((150, 64), (186, 54), (206, 80), (234, 62), (172, 88), (226, 94)):
        eyes(s, ex, ey, RED + B)
    gcells = box(26, 17, 6, 3)
    for y in range(17 * 8, 20 * 8):
        for x in range(26 * 8, W):
            if s.px[y, x] != NONE:
                s.px[y, x] = GREEN
            d = math.hypot((x - 236) / 2.2, y - 156)
            if dith(x, y, max(0.0, 0.5 - d / 20)):
                s.put(x, y, GREEN)
    assert all((x // 8, y // 8) in gcells for x in range(208, W) for y in range(136, 160))
    text_c(s, SUB, 160, YEL)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Paper black. Title fire chrome. Cave camp: rock strata + stalactites, ink by distance from",
        "the fire (Y+ R+ R, else B); fire Y+; Warrior / Mage as black silhouettes on fire-glow pools.",
        "Beyond: 5 huge dark steps (B+ upper rows, B below) dropping to the right, R+ eye pairs in",
        "the dark, the Tome's faint G glow in the bottom-right cells.",
    ]
    return s


# ================================================================ L10-L13 (no Archmage)
def ell(x, y, cx, cy, rx, ry):
    return ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2


# ---------------------------------------------------------------- L10 THE SKULL GATE
def l10() -> Scr:
    """A giant carved skull is the dungeon gate; its open mouth holds the stairs."""
    s = Scr()
    fire_title(s, (RED + B, RED + B, RED))
    BONE_, EYE = WHITE, RED + B
    MOUTH = (84, 172, 120, 160)                     # x0, x1, y0, y1
    skull = np.zeros((H, W), bool)
    for y in range(26, 160):
        for x in range(W):
            cran = ell(x, y, 128, 80, 98, 58) < 1 and y < 124
            jaw = abs(x + 0.5 - 128) < 70 - max(0, y - 120) * 0.5 and 100 <= y < 160
            cheek = ell(x, y, 128, 108, 86, 26) < 1
            skull[y, x] = cran or jaw or cheek
    holes = np.zeros_like(skull)
    for y in range(H):
        for x in range(W):
            sock = ell(x, y, 88, 82, 23, 19) < 1 or ell(x, y, 168, 82, 23, 19) < 1
            nose = 98 <= y < 114 and abs(x + 0.5 - 128) < (y - 96) * 0.55
            mouth = MOUTH[0] <= x < MOUTH[1] and MOUTH[2] <= y < MOUTH[3]
            holes[y, x] = sock or nose or mouth
    # teeth hang into the mouth from the upper jaw (y 120-131), gaps every 11 px
    for x in range(MOUTH[0], MOUTH[1]):
        if (x - MOUTH[0]) % 11 not in (0, 10):
            for y in range(120, 131 - abs(((x - MOUTH[0]) % 11) - 5) // 3):
                holes[y, x] = False
    body = skull & ~holes
    edge = body & dilate(~body, 1)
    # carved stone: solid outline, shading dither lit from the top-left, cracks
    for y, x in zip(*np.nonzero(body)):
        lit = 0.55 - 0.004 * (x - 30) - 0.003 * (y - 26)
        crack = abs((x - 1.6 * y) % 97) < 0.8 and y < 70 or abs((x + 1.3 * y) % 131) < 0.7 and y > 96
        if edge[y, x] or crack or dith(x, y, max(0.06, lit)):
            s.put(x, y, BONE_)
    # sockets: a red ember deep in each (own R+ cells cols 10-11 / 20-21, rows 9-10)
    for (cx, cy) in ((88, 82), (168, 82)):
        for y in range(cy - 7, cy + 8):
            for x in range(cx - 7, cx + 8):
                d = math.hypot(x + 0.5 - cx, (y + 0.5 - cy) * 1.2)
                if d < 2.2 or dith(x, y, max(0.0, 0.7 - d / 8)):
                    s.put(x, y, EYE)
    # the stairs = the tongue: perspective steps in the mouth cells cols 11-20 rows 17-19
    ink = lambda x, y: {17: RED, 18: RED + B, 19: YEL + B}.get(y // 8)
    yn, yf, hn, hf = 159, 137, 38, 12
    hw = lambda y: hf + (hn - hf) * (y - yf) / (yn - yf)
    edges = [159, 151, 145, 141, 138]
    for k, ey in enumerate(edges):
        w = int(hw(ey))
        for x in range(128 - w, 128 + w):
            s.put(x, ey, ink(x, ey))
        if k + 1 < len(edges):
            for y in range(edges[k + 1] + 1, ey - 1):
                ww = int(hw(y))
                for x in range(128 - ww + 1, 128 + ww - 1):
                    if dith(x, y, 0.4 * (1 - k / 5)):
                        s.put(x, y, ink(x, y))
    for y in range(yf, yn + 1):
        w = int(hw(y))
        s.put(128 - w, y, ink(128 - w, y))
        s.put(128 + w - 1, y, ink(128 + w - 1, y))
    # tiny heroes below, facing the gate, lit by the ember glow (inked)
    stamp(s, G.KNIGHT, 22, 0, WHITE + B, floor=160)
    stamp(s, G.MAGE, 210, 0, CYAN + B, floor=160, mirror=True)
    for x in list(range(0, 64)) + list(range(192, W)):
        if x % 3:
            s.put(x, 159, WHITE + B if x < 64 else CYAN + B)
    text_c(s, SUB, 160, RED + B)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Bone and blood: one giant carved skull (W stone dither lit top-left, cracks, solid edge).",
        "Eye sockets hold R+ embers in their own cells; the open mouth (teeth hanging) is the gate,",
        "its perspective stairs the tongue (rows R / R+ / Y+). Tiny inked heroes either side below.",
    ]
    return s


# ---------------------------------------------------------------- L11 THE TOWER UNDER THE MOON
def l11() -> Scr:
    """Outside view: an 8-tier cracked ziggurat in silhouette against a huge moon."""
    s = Scr()
    text_c(s, SUB, 0, CYAN)
    MX, MY, MR = 188, 80, 58
    moon_cells = {(c, r) for c in range(32) for r in range(24)
                  if any(math.hypot(x + 0.5 - MX, y + 0.5 - MY) < MR + 1
                         for x in (c * 8, c * 8 + 7) for y in (r * 8, r * 8 + 7))}
    GLOW = box(4, 1, 10, 5)
    GND = 150
    ink = lambda x, y: (WHITE + B if (x // 8, y // 8) in moon_cells else
                        GREEN + B if (x // 8, y // 8) in GLOW else WHITE)
    # moon: solid disc with dithered maria, rim solid
    for y in range(8, GND):
        for x in range(MX - MR, min(W, MX + MR + 1)):
            d = math.hypot(x + 0.5 - MX, y + 0.5 - MY)
            if d < MR:
                mare = (ell(x, y, MX - 18, MY - 14, 16, 12) < 1 or ell(x, y, MX + 14, MY + 10, 20, 14) < 1
                        or ell(x, y, MX - 10, MY + 26, 10, 7) < 1)
                if d > MR - 1.5 or not mare and dith(x, y, 0.92) or mare and dith(x, y, 0.45):
                    s.put(x, y, WHITE + B)
    # stars in the sky cells (W), none in moon / glow cells
    for k in range(70):
        x, y = hsh(k, 1) % W, 9 + hsh(k, 2) % 120
        if (x // 8, y // 8) not in moon_cells and (x // 8, y // 8) not in GLOW:
            s.put(x, y, WHITE)
            if k % 9 == 0:
                for d in (-1, 1):
                    s.put(x + d, y, WHITE)
                    s.put(x, y + d, WHITE)
    # the ziggurat: 8 tiers, black mass, edges + cracks + dark doorways in the cell ink
    ZX, TH, BW = 76, 13, 152
    zig = np.zeros((H, W), bool)
    tiers = []
    for k in range(8):
        hw = BW / 2 - k * 9.5
        y1 = GND - k * TH
        y0 = y1 - TH
        tiers.append((int(ZX - hw), int(ZX + hw), y0, y1))
        zig[y0:y1, max(0, int(ZX - hw)):int(ZX + hw)] = True
    for y, x in zip(*np.nonzero(dilate(zig, 1))):
        s.clr(x, y)
    for k, (x0, x1, y0, y1) in enumerate(tiers):
        for x in range(max(0, x0), x1):
            s.put(x, y0, ink(x, y0))
            if (x + k) % 3 == 0:
                s.put(x, y0 + 2, ink(x, y0 + 2))
        for y in range(y0, y1):
            if x0 >= 0:
                s.put(x0, y, ink(x0, y))
            s.put(x1 - 1, y, ink(x1 - 1, y))
        for j in range(x0 + 10, x1 - 10, 22):        # dark doorways: lintel + jambs
            if j < 0:
                continue
            for y in range(y0 + 5, y1):
                s.put(j, y, ink(j, y))
                s.put(j + 6, y, ink(j + 6, y))
            for x in range(j, j + 7):
                s.put(x, y0 + 5, ink(x, y0 + 5))
    # a great crack running down the tower face
    x = ZX + 6
    for y in range(GND - 8 * TH + 2, GND):
        x += (hsh(y, 4) % 3) - 1
        if zig[y, x]:
            s.put(x, y, ink(x, y))
            s.put(x + 1, y, ink(x + 1, y))
    # the Tome's green glow on the summit: rays + core (own G+ cells)
    tx, ty = ZX, GND - 8 * TH
    for y in range(8, ty):
        for x in range(32, 112):
            if (x // 8, y // 8) not in GLOW:
                continue
            dx, dy = x + 0.5 - tx, (y + 0.5 - ty) * 1.4
            r = math.hypot(dx, dy)
            a = math.atan2(dy, dx)
            ray = abs(((a / (2 * math.pi)) * 10 + 0.25) % 1 - 0.5) < 0.07
            if dith(x, y, max(0.0, 0.9 - r / 22)) or (ray and dith(x, y, 0.6 - r / 90)):
                s.put(x, y, GREEN + B)
    bk = book_bm()[1:15, 1:15]
    for yy, xx in zip(*np.nonzero(dilate(np.pad(bk, 1), 1))):
        s.clr(tx - 7 + xx - 1, ty - 14 + yy - 1)
    s.bits(bk, tx - 7, ty - 14, GREEN + B)
    # foreground ridge (black) and the heroes in silhouette against the moon
    for x in range(W):
        top = GND - 1 - int(6 * max(0.0, math.sin((x - 120) / 60))) - (x > 150) * 3
        for y in range(top, GND + 2):
            s.clr(x, y)
        s.put(x, top, ink(x, top))
    backlit(s, G.KNIGHT, 160, GND - 8, WHITE + B, dens=0.0)
    backlit(s, G.MAGE, 192, GND - 9, WHITE + B, dens=0.0, mirror=True)
    lg = G.chrome(title_line(3, 3, 2), [6, 13])
    s.bits(lg, centre(lg.shape[1]), 153, G.by_row([WHITE + B, CYAN + B, BLUE + B], 19))
    s.notes = [
        "Night: a huge W+ moon (own cells), W stars. The 8-tier ziggurat is a black mass whose edges,",
        "doorways and crack take the cell ink (W+ over the moon, W in the sky) - a silhouette.",
        "The Tome glows G+ (rays + core, own cells) on the summit. Heroes cut out of the moon on",
        "the ridge. Title at the bottom (rows 19-21) W+ C+ B+; sub-title row 0 C.",
    ]
    return s


# ---------------------------------------------------------------- L12 THE CREST
def l12() -> Scr:
    """Mirror-symmetric heraldic cover: crossed sword + staff behind a shield bearing
    the Tome, bats and skulls as supporters, the title on a banner scroll."""
    s = Scr()
    GOLD = YEL + B
    text_c(s, SUB, 0, CYAN + B)
    CX, SY0, SY1, SHW = 128, 30, 132, 44           # shield centre x, top, tip, half width
    def in_shield(x, y):
        if y < SY0 or y >= SY1:
            return False
        if y < SY0 + 50:
            return abs(x + 0.5 - CX) < SHW
        t = (y - SY0 - 50) / (SY1 - SY0 - 50)
        return abs(x + 0.5 - CX) < SHW * math.sqrt(max(0.0, 1 - t * t))
    shield = np.array([[in_shield(x, y) for x in range(W)] for y in range(H)])
    # crossed sword (\) and staff (/) behind the shield, gold
    def bar(x0, y0, x1, y1, wdt):
        n = int(math.hypot(x1 - x0, y1 - y0))
        for i in range(n):
            t = i / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for d in range(-wdt, wdt + 1):
                s.put(int(x + d * 0.7), int(y - d * 0.7) if x1 > x0 else int(y + d * 0.7), GOLD)
    bar(40, 26, 216, 138, 1)                         # sword blade
    for d in range(-9, 10):                           # crossguard
        s.put(46 + d, 34 - d, GOLD)
        s.put(47 + d, 34 - d, GOLD)
    for y in range(16, 26):                           # grip + pommel
        s.put(33 + int((y - 16) * 0.75), y, GOLD)
    for (px, py) in ((30, 14), (31, 14), (30, 15), (31, 15), (29, 14), (30, 13)):
        s.put(px, py, GOLD)
    bar(216, 26, 40, 138, 1)                          # staff shaft
    for k in range(48):                               # staff head: a ring round an orb
        a = k * 2 * math.pi / 48
        s.put(int(222 + 7 * math.cos(a)), int(20 + 7 * math.sin(a)), GOLD)
    for y in range(17, 24):
        for x in range(219, 226):
            if math.hypot(x - 222, y - 20) < 3:
                s.put(x, y, GOLD)
    # shield: black halo, gold rim, red field in heraldic hatching (gules = verticals)
    for y, x in zip(*np.nonzero(dilate(shield, 2))):
        s.clr(x, y)
    rim = shield & dilate(~shield, 2)
    TOME_BOX = box(13, 7, 6, 6)
    for y, x in zip(*np.nonzero(shield)):
        if (x // 8, y // 8) in TOME_BOX:
            continue
        if rim[y, x]:
            s.put(x, y, GOLD)
    field = field_cells(shield, rim)
    for y, x in zip(*np.nonzero(shield & ~rim)):
        c = (x // 8, y // 8)
        if c not in TOME_BOX and x % 3 == 0:
            s.put(x, y, RED + B if c in field else GOLD)
    # the Tome 3x, green, in the shield's heart (own G+ cells)
    bk = book_bm()[1:15, 1:15].repeat(3, 0).repeat(3, 1)
    for y in range(7 * 8, 13 * 8):
        for x in range(13 * 8, 19 * 8):
            s.clr(x, y)
            if dith(x, y, max(0.0, 0.35 - math.hypot(x - 128, y - 80) / 90)):
                s.put(x, y, GREEN + B)
    for y, x in zip(*np.nonzero(dilate(np.pad(bk, 1), 1))):
        s.clr(107 + x - 1, 59 + y - 1)
    s.bits(bk, 107, 59, GREEN + B)
    # supporters: bats over skulls, mirrored
    bat = g48("bat_glide")
    stamp(s, bat, 6, 52, MAG + B)
    stamp(s, bat, W - 6 - len(bat[0]), 52, MAG + B, mirror=True)
    s.bits(G.SKULL_BM, 18, 96, WHITE + B, halo=True)
    s.bits(G.SKULL_BM, W - 34, 96, WHITE + B, halo=True)
    for (x0, mir) in ((10, False), (W - 42, True)):   # crossed bones under each skull
        for t in range(32):
            s.put(x0 + t, 116 + t // 4, WHITE + B)
            s.put(x0 + 31 - t, 116 + t // 4, WHITE + B)
    # banner scroll with the title: ribbon rows 17-20 in gold, curled tails
    lg = title_line(3, 3, 2)
    lx, ly = centre(lg.shape[1]), 142
    for x in range(4, W - 4):
        for y in range(136, 168):
            s.clr(x, y)
    for x in range(lx - 6, lx + lg.shape[1] + 6):
        wob = int(2 * math.sin((x - 128) / 40))
        s.put(x, 138 + wob, GOLD)
        s.put(x, 166 + wob - 1, GOLD) if 166 + wob - 1 < 168 else None
    for (ex, dirn) in ((lx - 6, -1), (lx + lg.shape[1] + 5, 1)):   # tails
        for k in range(14):
            for y in (146 + k // 3, 160 - k // 3):
                s.put(ex + dirn * k, y, GOLD)
        for y in range(138, 167):
            s.put(ex, y, GOLD)
    s.bits(lg, lx, ly, GOLD)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Heraldic, mirror-symmetric. Gold (Y+): sword + staff crossed behind the shield, shield rim,",
        "banner + title. Field = R+ vertical hatching (heraldic gules); the Tome 3x G+ in its own",
        "6x6-cell heart. Supporters: Bats M+ above Skulls + crossed bones W+. Sub C+, credit W.",
    ]
    return s


def field_cells(shield, rim):
    """Shield cells that hold no rim pixel: the red field (rim cells stay gold)."""
    out = set()
    for r in range(24):
        for c in range(32):
            blk = shield[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            if blk.any() and not rim[r * 8:r * 8 + 8, c * 8:c * 8 + 8].any():
                out.add((c, r))
    return out


# ---------------------------------------------------------------- L13 THE CIRCLE
def l13() -> Scr:
    """Monster-eye view: the heroes small in a pool of white light, the bestiary
    looming in from the dark edges as black shapes with dotted red rims and eyes."""
    s = Scr()
    fire_title(s, (RED + B, RED + B, RED))
    MON = RED + B
    PX, PY, PRX, PRY = 128, 122, 46, 26
    pool_cells = {(x // 8, y // 8) for y in range(PY - PRY, PY + PRY) for x in range(PX - PRX, PX + PRX)
                  if ell(x, y, PX, PY, PRX, PRY) < 1}
    # the dark room: a red speckle thickening toward the light, so the black shapes read
    for y in range(24, 160):
        for x in range(W):
            if (x // 8, y // 8) in pool_cells:
                continue
            d = math.sqrt(ell(x, y, PX, PY, PRX * 2.6, PRY * 3.6))
            if dith(x, y, max(0.04, 0.42 * (1 - d))) and hsh(x, y, 13) % 3:
                s.put(x, y, MON)
    # pool of light + a few lit flagstones
    for y in range(PY - PRY, PY + PRY):
        for x in range(PX - PRX, PX + PRX):
            d = ell(x, y, PX, PY, PRX, PRY)
            if d < 1:
                tile = ((y - PY) % 9 == 0 or (x - PX + (y - PY) // 9 * 7) % 22 == 0) and d < 0.8
                if tile or dith(x, y, 0.55 * (1 - d) ** 0.8):
                    s.put(x, y, WHITE + B)
    stamp(s, G.KNIGHT, 102, 0, WHITE + B, floor=136, halo=2)
    stamp(s, G.MAGE_CAST, 126, 0, WHITE + B, floor=136, halo=2, mirror=True)
    # the bestiary, 2x silhouettes closing in from the edges
    cast = [("ogre_walk1", 48, -10, 160, False), ("skeleton_walk1", 40, 176, 160, True),
            ("vamp_walk1", 40, 214, 160, True), ("ghost_float1", 48, 30, 92, False),
            ("bat_glide", 48, 104, 60, False), ("spider_climb1", 48, 176, 72, False)]
    for name, sz, x0, floor, mir in cast:
        rows = g40(name) if sz == 40 else g48(name)
        opq = sil_mask(rows, mir, 2)
        hh, ww = opq.shape
        y0 = floor - hh
        for y, x in zip(*np.nonzero(opq)):
            s.clr(x0 + x, y0 + y)
        rim = dilate(np.pad(opq, 1), 1) & ~np.pad(opq, 1)
        for y, x in zip(*np.nonzero(rim)):
            s.put(x0 + x - 1, y0 + y - 1, MON)
        # eyes: two 2x2 embers in the upper body, toward the light
        ey = y0 + max(6, hh // 6)
        ex = x0 + ww // 2 - 4 + (4 if x0 < PX else -4)
        eyes(s, ex, ey, MON, big=True)
        if name == "spider_climb1":
            for y in range(24, y0):
                s.put(x0 + ww // 2, y, MON)
            eyes(s, ex + 10, ey + 2, MON)
    # more eyes in the dark
    for (ex, ey) in ((70, 40), (236, 40), (60, 112), (232, 108), (176, 32)):
        eyes(s, ex, ey, MON)
    text_c(s, SUB, 160, RED)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Monster-eye view, red on black + one white light. Heroes W+ (2-px halo) in a W+ dithered",
        "pool with lit flagstones. Ogre, Skeleton, Vampire, Ghost, Bat, Spider 2x as black shapes",
        "with solid R+ rims and R+ ember eyes on a red speckle that thickens toward the light, closing in; extra eye pairs in the dark.",
    ]
    return s


# ================================================================ L3a-L3c: L3 with more colour
# (user 2026-10-31). Each variant plans its colours per CELL first (a dict cell -> ink),
# then draws every structure with that map, so colour follows the picture's structure.
def menu_title(s: Scr, c):
    parts = []
    for ch in TITLE:
        g = G.FONT16[ch]
        cs = np.nonzero(g.any(0))[0]
        parts.append(g[:, cs[0]:cs[-1] + 1] if len(cs) else np.zeros((16, 3), bool))
        parts.append(np.zeros((16, 1), bool))
    bm = G.chrome(np.hstack(parts[:-1]).repeat(2, 0).repeat(2, 1), [5, 11, 17, 23])
    s.bits(bm, centre(bm.shape[1]), 0, c)


def tome_masks(BX, BY, FLOOR):
    """The L3 Tome + lectern as masks: (solid, carve) -- carve = black detail."""
    lec = np.zeros((H, W), bool)
    for y in range(116, FLOOR):
        hw = 6 if y < FLOOR - 12 else (10 if y < FLOOR - 6 else 16)
        if y < 124:
            hw = 18 - (y - 116)
        lec[y, BX - hw:BX + hw] = True
    lec_cut = np.zeros_like(lec)
    for y in range(124, FLOOR - 12, 4):
        lec_cut[y, BX - 3:BX + 3] = True
    book = np.zeros((H, W), bool)
    det = np.zeros((H, W), bool)
    for x in range(BX - 40, BX + 40):
        t = abs(x + 0.5 - BX) / 40
        top = int(BY - 12 + 7 * t - 9 * math.sin(math.pi * min(1, t * 1.1)) * 0.6)
        bot = top + 26 - int(3 * t)
        book[top:bot + 3, x] = True
        det[bot, x] = True
        if abs(x - BX) < 1:
            det[top:bot, x] = True
    sk = np.pad(G.SKULL_BM, 1)
    for y, x in zip(*np.nonzero(dilate(sk, 1) & ~sk)):
        det[BY - 13 + y, BX - 31 + x] = True
    for i in range(5):
        a1, a2 = -math.pi / 2 + i * 4 * math.pi / 5, -math.pi / 2 + (i + 1) * 4 * math.pi / 5
        x1, y1 = BX + 21 + 9 * math.cos(a1), BY - 3 + 9 * math.sin(a1)
        x2, y2 = BX + 21 + 9 * math.cos(a2), BY - 3 + 9 * math.sin(a2)
        for k in range(25):
            det[int(round(y1 + (y2 - y1) * k / 24)), int(round(x1 + (x2 - x1) * k / 24))] = True
    for k in range(64):
        a = k * 2 * math.pi / 64
        det[int(round(BY - 3 + 11 * math.sin(a))), int(round(BX + 21 + 11 * math.cos(a)))] = True
    return book | lec, (det & book) | (lec_cut & lec)


def draw_tome(s: Scr, ink, BX=128, BY=100, FLOOR=152):
    solid, carve = tome_masks(BX, BY, FLOOR)
    for y, x in zip(*np.nonzero(dilate(solid, 2) & ~solid)):
        s.clr(x, y)
    for y, x in zip(*np.nonzero(solid)):
        s.put(x, y, ink(x, y))
    for y, x in zip(*np.nonzero(carve)):
        s.clr(x, y)
    for k in range(3):                              # rising wisps
        x0 = BX - 16 + 16 * k
        for y in range(52, BY - 18):
            xx = int(x0 + 4 * math.sin((y + 7 * k) / 6))
            if dith(xx, y, 0.9):
                s.put(xx, y, ink(xx, y))
                s.clr(xx + 1, y)
                s.clr(xx - 1, y)


def radiance(s: Scr, ink, keep, BX=128, BY=100, y0=32, y1=152, nrays=14, reach=1.0):
    for y in range(y0, y1):
        for x in range(W):
            if not keep(x // 8, y // 8):
                continue
            dx, dy = x + 0.5 - BX, (y + 0.5 - BY) * 1.25
            r = math.hypot(dx, dy)
            a = math.atan2(dy, dx)
            ph = (a / (2 * math.pi) * nrays + 0.25) % 1.0
            ray = abs(ph - 0.5) < 0.09 * (1 - min(r, 170) / 260)
            core = max(0.0, 1.0 - r / 64) ** 1.3
            ring = abs(r % 14 - 7) < 0.6 and r < 90
            if (ray and dith(x, y, (0.85 - r / 300) * reach)) or dith(x, y, core * 0.9) or (ring and dith(x, y, 0.5)):
                s.put(x, y, ink(x, y))


def cell_ink(cm, default=None):
    return lambda x, y: cm.get((x // 8, y // 8), default)


def bricks_px(s: Scr, cells, ink, bw=16, bh=6, seed=0, dens=1.0):
    for (c, r) in cells:
        for y in range(r * 8, r * 8 + 8):
            off = bw // 2 if (y // bh) & 1 else 0
            for x in range(c * 8, c * 8 + 8):
                if ((y % bh == bh - 1) or ((x + off) % bw == 0)) and dith(x, y, dens):
                    s.put(x, y, ink(x, y))


HERO_L = box(1, 9, 7, 10)                          # 2x Warrior x 12..59, y 72..151
HERO_R = box(22, 9, 9, 10)                         # 2x Mage cast x 180..243


# ---------------------------------------------------------------- L3a torches + shaded walls
def l3a() -> Scr:
    s = Scr()
    menu_title(s, G.by_row([WHITE + B, WHITE + B, YEL + B, YEL + B], 0))
    G_ = GREEN + B
    torches = [(1, 4), (6, 4), (24, 4), (29, 4)]
    tcells = set().union(*(box(c, r, 2, 4) for c, r in torches))
    lights = [G.light(c + 1, r + 2, [(2.2, YEL + B), (3.0, RED + B), (3.8, RED)]) for c, r in torches]
    cm = {}
    for r in range(4, 20):
        for c in range(32):
            if (c, r) in tcells:
                continue
            glow = ((c + 0.5 - 16) / 15.5) ** 2 + ((r + 0.5 - 12.5) / 7.2) ** 2 < 1 or (c, r) in HERO_L | HERO_R
            if glow and r >= 6:
                cm[(c, r)] = G_
                continue
            warm = [f(c, r) for f in lights if f(c, r) is not None]
            if warm:
                cm[(c, r)] = warm[0]
            else:
                d = math.hypot((c + 0.5 - 16) / 16, (r + 0.5 - 12.5) / 8)
                cm[(c, r)] = MAG if d < 1.15 else BLUE
    ink = cell_ink(cm, G_)
    walls = [c for c, v in cm.items() if v != G_]
    bricks_px(s, walls, ink, seed=3)
    radiance(s, ink, lambda c, r: cm.get((c, r)) == G_)
    for x in range(W):                               # floor + reflection in the glow cells
        s.put(x, 152, ink(x, 152))
        for y in range(154, 160):
            if dith(x, y, max(0.0, 0.5 - abs(x - 128) / 160) * (1 - (y - 152) / 8)):
                s.put(x, y, ink(x, y))
    for c, r in torches:
        s.clear_rect(c * 8, r * 8, 16, 32)
        G.place_torch(s, c, r)
    draw_tome(s, ink)
    stamp(s, G.KNIGHT, 12, 0, G_, scale=2, halo=2, floor=152)
    stamp(s, G.MAGE_CAST, W - 12 - 64, 0, G_, scale=2, halo=2, floor=152, mirror=True)
    text_c(s, "THE TOME OF ABSOLUTE DEATH MAGIC", 160, G_)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "L3 + four game torches (cols 1/6/24/29, rows 4-7). Cell plan: the Tome's G+ glow is an",
        "ellipse of cells (rays, core, rings, heroes inside it); torch cells cast Y+ / R+ / R warm",
        "patches on the brick wall; the rest of the wall shades M near the glow, B further out.",
        "Title W+ W+ Y+ Y+ by row.",
    ]
    return s


# ---------------------------------------------------------------- L3b multicolour rays
def l3b() -> Scr:
    s = Scr()
    menu_title(s, G.by_row([WHITE + B, CYAN + B, CYAN + B, GREEN + B], 0))
    BX, BY = 128, 100
    stands = [(9, 9), (21, 9)]                        # torch on a tall stand, cols 9-10 / 21-22
    tcells = set().union(*(box(c, r, 2, 4) for c, r in stands))
    pole = set().union(*(box(c, 13, 2, 6) for c, _ in stands))
    dais = {17: YEL + B, 18: RED + B}
    flyers = [("bat", 3, 4), ("bat", 26, 4), ("skull", 11, 4), ("skull", 19, 4)]
    fcells = set()
    for kind, c, r in flyers:
        fcells |= box(c, r, 3 if kind == "bat" else 2, 2)
    cm = {}
    for r in range(4, 20):
        for c in range(32):
            if (c, r) in tcells:
                continue
            if (c, r) in pole:
                cm[(c, r)] = YEL
            elif (c, r) in HERO_L:
                cm[(c, r)] = WHITE + B
            elif (c, r) in HERO_R:
                cm[(c, r)] = CYAN + B
            elif (c, r) in fcells:
                kind = next(k for k, fc, fr in flyers if (c, r) in box(fc, fr, 3 if k == "bat" else 2, 2))
                cm[(c, r)] = MAG + B if kind == "bat" else WHITE + B
            elif r in dais and 11 <= c <= 20:
                cm[(c, r)] = dais[r]
            else:
                d = math.hypot((c + 0.5 - 16), (r + 0.5 - 12.5) * 1.6)
                cm[(c, r)] = GREEN + B if d < 6.5 else CYAN + B if d < 11 else WHITE + B if d < 15 else WHITE
    tsol = tome_masks(BX, BY, 136)[0]                 # Tome + lectern + wisps stay G+
    for (c, r) in {(x // 8, y // 8) for y, x in zip(*np.nonzero(tsol))} | box(13, 6, 6, 4):
        cm[(c, r)] = GREEN + B
    ink = cell_ink(cm, GREEN + B)
    radiance(s, ink, lambda c, r: (c, r) not in pole and (c, r) not in fcells and not (r in dais and 11 <= c <= 20))
    # dais: two steps (Y+ upper, R+ lower) under the lectern
    for (a, b, ty) in ((96, 160, 136), (88, 168, 144)):
        for x in range(a, b):
            s.put(x, ty, ink(x, ty))
            if x % 2 == 0:
                s.put(x, ty + 2, ink(x, ty + 2))
            for y in range(ty + 3, ty + 8):
                if dith(x, y, 0.25):
                    s.put(x, y, ink(x, y))
    for x in range(W):                               # floor line
        if not (88 <= x < 168):
            s.put(x, 152, ink(x, 152))
    draw_tome(s, lambda x, y: GREEN + B, BX, BY, 136)
    # torch stands: game torch on a ringed pole (after the Tome: its halo stays off them)
    for c, r in stands:
        s.clear_rect(c * 8, r * 8, 16, 80)
        G.place_torch(s, c, r)
        for y in range(104, 152):
            for x in (c * 8 + 6, c * 8 + 9):
                s.put(x, y, YEL)
            if y % 12 == 0:
                for x in range(c * 8 + 4, c * 8 + 12):
                    s.put(x, y, YEL)
        for x in range(c * 8 + 2, c * 8 + 14):
            s.put(x, 151, YEL)
            s.put(x, 150, YEL)
    # floating bats (M+) and skulls (W+)
    for kind, c, r in flyers:
        s.clear_rect(c * 8, r * 8, 24 if kind == "bat" else 16, 16)
        if kind == "bat":
            stamp(s, g48("bat_glide"), c * 8, r * 8, MAG + B, halo=0, mirror=c > 16)
        else:
            s.bits(G.SKULL_BM, c * 8, r * 8, WHITE + B)
    stamp(s, G.KNIGHT, 12, 0, WHITE + B, scale=2, halo=2, floor=152)
    stamp(s, G.MAGE_CAST, 188, 0, CYAN + B, scale=2, halo=2, floor=152, mirror=True)
    text_c(s, "THE TOME OF ABSOLUTE DEATH MAGIC", 160, GREEN + B)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Rays change ink by cell distance from the Tome: G+ core, C+, W+, W at the rim.",
        "Lectern on a 2-step dais (Y+ / R+ cell rows); game torches on tall Y ringed poles",
        "flank it; floating Bats M+ and Skulls W+ in their own cells. Warrior W+ / Mage C+",
        "inked in the matching ray ink (2-px black halo). Title W+ C+ C+ G+ by row.",
    ]
    return s


# ---------------------------------------------------------------- L3c crypt chamber
def l3c() -> Scr:
    s = Scr()
    menu_title(s, G.by_row([WHITE + B, WHITE + B, CYAN + B, CYAN + B], 0))
    G_, STONE, ARCH = GREEN + B, WHITE, BLUE + B
    FLOOR = 136                                     # floor tiles rows 17-19
    cols_ = [0, 8, 22, 30]                          # 2-cell columns
    torches = [(c, 6) for c in cols_]
    tcells = set().union(*(box(c, r, 2, 4) for c, r in torches))
    colc = set().union(*(box(c, 4, 2, 13) for c in cols_)) - tcells
    archc = box(2, 4, 6, 3) | box(24, 4, 6, 3)
    glowc = box(10, 4, 12, 13)
    rune_px = np.zeros((H, W), bool)
    for k in range(400):
        a = k * 2 * math.pi / 400
        x, y = int(round(128 + 72 * math.cos(a))), int(round(150 + 9 * math.sin(a)))
        if y < 160:
            rune_px[y, x] = True
    for k in range(16):                               # rune ticks on the ring
        a = k * 2 * math.pi / 16
        x, y = int(round(128 + 72 * math.cos(a))), int(round(150 + 9 * math.sin(a)))
        for d in (-2, -1, 1, 2):
            if 0 <= y + d < 160:
                rune_px[y + d, x] = True
    lecmask = tome_masks(128, 100, 152)[0]
    lec_cells = {(x // 8, y // 8) for y, x in zip(*np.nonzero(dilate(lecmask, 2))) if y >= 136}
    rune_cells = {(x // 8, y // 8) for y, x in zip(*np.nonzero(rune_px))} - lec_cells
    cm = {}
    for r in range(4, 20):
        for c in range(32):
            if (c, r) in tcells:
                continue
            if (c, r) in lec_cells:
                cm[(c, r)] = G_
            elif r >= 17:
                cm[(c, r)] = YEL + B if (c, r) in rune_cells else (MAG if (c + r) % 2 else BLUE)
            elif (c, r) in colc:
                cm[(c, r)] = STONE
            elif (c, r) in archc:
                cm[(c, r)] = ARCH
            elif (c, r) in glowc:
                cm[(c, r)] = G_
            else:
                cm[(c, r)] = BLUE                    # dark aisles behind the arches
    hero_c = {(c, r) for (c, r) in HERO_L | HERO_R if (c, r) not in tcells}
    for cr in hero_c:                                 # heroes stand in front, lit W+
        cm[cr] = WHITE + B
    ink = cell_ink(cm, BLUE)
    # columns: fluted shafts + capitals + bases
    for c in cols_:
        x0 = c * 8
        for y in range(32, FLOOR):
            if (x0 // 8, y // 8) in tcells:
                continue
            for x in (x0, x0 + 15, x0 + 5, x0 + 10):
                if x in (x0, x0 + 15) or y % 3:
                    s.put(x, y, ink(x, y))
        for y in (33, 35, FLOOR - 3, FLOOR - 1):
            for x in range(x0, x0 + 16):
                s.put(x, y, ink(x, y))
    # pointed arches between the column pairs, the aisle behind in faint blue
    for (a, b) in ((16, 64), (192, 240)):
        cx, half = (a + b) / 2, (b - a) / 2
        for y in range(32, 56):
            t = (56 - y) / 24
            off = half * math.sqrt(max(0.0, 1 - t * t))
            for xx in (int(cx - off), int(cx + off) - 1, int(cx - off) + 1, int(cx + off) - 2):
                s.put(xx, y, ink(xx, y))
            for x in range(a, b):
                if abs(x + 0.5 - cx) > off and dith(x, y, 0.4):
                    s.put(x, y, ink(x, y))
        for y in range(56, FLOOR):
            for x in range(a, b):
                if (x // 8, y // 8) not in hero_c and dith(x, y, 0.07 if (y // 6) % 2 else 0.12):
                    s.put(x, y, ink(x, y))
    # the Tome's green glow, held inside the central nave
    radiance(s, ink, lambda c, r: (c, r) in glowc, y1=FLOOR, reach=0.9)
    # floor: checker tiles (cell outlines), the yellow rune circle round the lectern
    for y in range(FLOOR, 160):
        for x in range(W):
            if (x // 8, y // 8) in rune_cells:
                if rune_px[y, x]:
                    s.put(x, y, ink(x, y))
                continue
            if (x // 8, y // 8) in lec_cells:
                continue
            if x % 8 == 0 or y % 8 == 0 or ((x // 8 + y // 8) % 2 and dith(x, y, 0.25)):
                s.put(x, y, ink(x, y))
    for c, r in torches:
        s.clear_rect(c * 8, r * 8, 16, 32)
        G.place_torch(s, c, r)
    draw_tome(s, lambda x, y: G_)
    # heroes 2x in front of the colonnades, lit W+ (2-px black halo cuts them out)
    stamp(s, G.KNIGHT, 12, 0, WHITE + B, scale=2, halo=2, floor=152)
    stamp(s, G.MAGE_CAST, W - 12 - 64, 0, WHITE + B, scale=2, halo=2, floor=152, mirror=True)
    text_c(s, "THE TOME OF ABSOLUTE DEATH MAGIC", 160, G_)
    text_c(s, CREDIT, 168, WHITE)
    s.notes = [
        "Crypt chamber. Cell plan: 4 fluted W columns (2 cells each) carrying the 4 game torches,",
        "B+ pointed arches between them over dark B aisles; the G+ nave holds the Tome's rays;",
        "floor rows 17-19 = M / B checker by cell, with a Y+ rune circle (own cells) round the",
        "lectern. Heroes 2x inked W+ (lit by the torches) with a 2-px halo. Title W+ W+ C+ C+.",
    ]
    return s


# ================================================================ L3d: L3c redrawn at native resolution
# (user 2026-11-01: "the heroes and objects feel like upscaled sprites"). Nothing here is a
# scaled game sprite: the figures, torches, columns, Tome, lectern and rune circle are built
# from shapes at 1:1 with material labels, then rendered with ordered dither in ONE ink per
# cell (the 1-bit lit side / shadow side of each part).
MK, MS, MD, ML, MC, MH = 1, 2, 3, 4, 5, 6     # black detail, solid, 50 %, 25 %, chainmail, 75 %


def _poly(h, w, pts):
    m = np.zeros((h, w), bool)
    n = len(pts)
    ys = [p[1] for p in pts]
    for y in range(max(0, int(min(ys))), min(h, int(max(ys)) + 1)):
        yc = y + 0.5
        xs = []
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            for x in range(max(0, int(math.ceil(a - 0.5))), min(w, int(math.floor(b - 0.5)) + 1)):
                m[y, x] = True
    return m


def _ell(h, w, cx, cy, rx, ry):
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1.0


def _line(h, w, pts, r=0.0):
    """Polyline (or a 3-point quadratic Bezier if bez) as a mask, radius r."""
    m = np.zeros((h, w), bool)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for i in range(n + 1):
            x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
            for dy in range(-int(r) - 1, int(r) + 2):
                for dx in range(-int(r) - 1, int(r) + 2):
                    X, Y = int(math.floor(x + dx + 0.5)), int(math.floor(y + dy + 0.5))
                    if 0 <= X < w and 0 <= Y < h and (X - x) ** 2 + (Y - y) ** 2 <= (r + 0.5) ** 2:
                        m[Y, X] = True
    return m


def _bez(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


class Fig:
    """A figure as a label image; parts are painted back to front."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.lab = np.zeros((h, w), np.uint8)

    def sep(self, m):
        """1-px black seam where part m lies over earlier parts."""
        ring = dilate(m, 1) & ~m & (self.lab != 0)
        self.lab[ring] = MK

    def paint(self, m, mat, sep=True):
        if sep:
            self.sep(m)
        self.lab[m] = mat

    def shade(self, m, levels, lit_right=True, rim=True, sep=True):
        """Per row, u = 0 (shadow side) .. 1 (lit side): first level with u >= t wins."""
        if sep:
            self.sep(m)
        for y in range(self.h):
            xs = np.nonzero(m[y])[0]
            if not len(xs):
                continue
            a, b = xs[0], xs[-1]
            for x in xs:
                u = (x - a) / max(1, b - a)
                if not lit_right:
                    u = 1 - u
                self.lab[y, x] = next(mat for t, mat in levels if u >= t)
            if rim:                       # torch rim light on the shadow edge
                self.lab[y, a if lit_right else b] = MS

    def mask(self, kind, *a, **k):
        f = {"poly": _poly, "ell": _ell, "line": _line}[kind]
        return f(self.h, self.w, *a, **k)


def render_fig(s: Scr, lab, x0, y0, ink, halo=1):
    sil = lab != 0
    for y, x in zip(*np.nonzero(dilate(np.pad(sil, halo), halo))):
        s.clr(x0 + x - halo, y0 + y - halo)
    for y, x in zip(*np.nonzero(sil)):
        X, Y = x0 + x, y0 + y
        m = lab[y, x]
        on = (m == MS or (m == MH and dith(X, Y, 0.75)) or (m == MD and dith(X, Y, 0.5))
              or (m == ML and dith(X, Y, 0.25))
              or (m == MC and ((Y % 2 == 0 and X % 2 == 0) or (Y % 2 == 1 and X % 4 == 1))))
        if on:
            s.put(X, Y, ink(X, Y) if callable(ink) else ink)


LIT2 = [(0.24, MS), (0.0, MD)]                 # lit body, one 50 % shadow band on the back edge


def warrior_fig() -> Fig:
    """Hand-built Warrior, 48x64, facing right (toward the Tome): flat lit shapes, black
    seams, one dither shadow band; sword held upright before him."""
    f = Fig(48, 64)
    # kite shield on the back arm: 2-px rim, shaded field, cross
    sh = f.mask("poly", [(2, 22), (14, 20), (15, 34), (9, 53), (3, 38)])
    f.paint(sh, MD, sep=False)
    inner = sh & ~dilate(~sh, 2)
    f.lab[sh & ~inner] = MS
    f.lab[(f.mask("line", [(8, 24), (8.5, 46)]) | f.mask("line", [(4, 31), (13, 30)])) & inner] = MS
    # plume sweeping back from the crest, two strand seams
    pl = f.mask("poly", [(17, 2), (23, 3), (17, 7), (11, 13), (5, 21), (2, 19), (6, 11), (11, 5)])
    f.paint(pl, MS, sep=False)
    for pts in (_bez((18, 4), (10, 7), (4, 18)), _bez((20, 3), (12, 9), (7, 16))):
        f.lab[f.mask("line", pts) & pl & ~dilate(~pl, 1)] = MK
    # legs and boots (back leg in shadow), knee cop
    f.paint(f.mask("poly", [(14, 44), (20, 44), (20, 57), (15, 57)]), MD)
    f.paint(f.mask("poly", [(13, 57), (21, 57), (22, 63), (12, 63)]), MS)
    f.paint(f.mask("poly", [(21, 44), (28, 44), (28, 57), (22, 57)]), MS)
    f.lab[f.mask("line", [(23, 52), (23, 56)])] = MD
    f.paint(f.mask("ell", 25.5, 49.5, 3.2, 2.6), MS)
    f.paint(f.mask("poly", [(21, 57), (29, 57), (33, 60), (34, 63), (21, 63)]), MS)
    # mail skirt with a scalloped hem
    sk = f.mask("poly", [(12, 36), (29, 36), (31, 45), (10, 45)])
    f.paint(sk, MC)
    for x in range(48):
        if sk[44, x] and x % 3 == 0:
            f.lab[44, x] = MK
    # surcoat with a cross, shadow band on the back edge
    tor = f.mask("poly", [(13, 19), (28, 19), (29, 36), (12, 36)])
    f.shade(tor, [(0.18, MS), (0.0, MD)], rim=False)
    f.lab[23:34, 20:22] = MK
    f.lab[26:28, 16:26] = MK
    # belt + buckle
    belt = f.mask("poly", [(12, 34.5), (29.3, 34.5), (29.5, 37.5), (11.8, 37.5)])
    f.lab[belt] = MS
    f.lab[34][belt[35]] = MK
    f.lab[37][belt[36]] = MK
    f.lab[34:38, 23] = f.lab[34:38, 26] = MK
    # back pauldron, mail coif
    f.paint(f.mask("ell", 14.5, 20.5, 4.6, 3.8), MD)
    f.paint(f.mask("poly", [(16, 15), (26, 15), (27, 20), (15, 20)]), MC)
    # great helm: dome, flat face plate, front ridge, visor slit, breaths
    helm = f.mask("poly", [(14, 7), (27, 6), (29, 9), (29, 16), (14, 16)]) | f.mask("ell", 21, 7.5, 7.6, 4.6)
    f.shade(helm, [(0.2, MS), (0.0, MD)], rim=False)
    f.lab[10, 21:30][helm[10, 21:30]] = MK
    f.lab[6:10, 23] = MK
    for (x, y) in ((25, 13), (27, 13), (26, 14), (28, 14)):
        f.lab[y, x] = MK
    f.lab[16, 15:29] = MK
    # front pauldron with lames, mail sleeve, vambrace
    pd = f.mask("ell", 27, 21.5, 5.6, 4.4)
    f.paint(pd, MS)
    for y in (23, 25):
        f.lab[y][pd[y] & (np.arange(48) > 23)] = MK
    f.paint(f.mask("poly", [(25, 25), (30, 25), (31, 30), (27, 31)]), MC)
    f.paint(f.mask("poly", [(28, 29), (33, 28), (35, 31), (31, 33)]), MS)
    # sword held upright: grip, hand, crossguard, blade (highlight / fuller / shade), pommel
    f.paint(f.mask("poly", [(35, 29), (38, 29), (38, 34), (35, 34)]), MD)
    f.paint(f.mask("ell", 36.5, 31.5, 2.8, 2.5), MS)
    f.lab[31, 35:39] = MK
    f.paint(f.mask("poly", [(30, 26), (43, 26), (43, 28), (30, 28)]), MS)
    f.lab[25, 30] = f.lab[25, 42] = MS
    for y in range(2, 26):
        f.lab[y, 35] = MS
        f.lab[y, 36] = MK if 6 <= y <= 22 else MS
        f.lab[y, 37] = MD if y > 3 else 0
    f.lab[1, 36] = MS
    f.lab[2, 35] = 0
    f.lab[2, 37] = 0
    f.paint(f.mask("ell", 36.5, 35.5, 1.8, 1.4), MS)
    return f


def mage_fig() -> Fig:
    """Hand-built Mage, 48x64, built facing right (mirrored on screen)."""
    f = Fig(48, 64)
    # staff + claw + orb with sparkle rays
    f.lab[9:64, 41] = MS
    f.lab[9:64, 40] = MD
    for y in range(14, 64, 10):
        f.lab[y, 40:42] = MK
    f.paint(f.mask("line", [(39, 10), (37.5, 6)]) | f.mask("line", [(42, 10), (43.5, 6)]), MS, sep=False)
    orb = f.mask("ell", 40.5, 5, 3.4, 3.4)
    f.paint(orb, MS)
    f.lab[orb & (np.arange(48)[None, :] < 39) & (np.arange(64)[:, None] > 4)] = MD
    f.lab[3, 41] = MK
    for (x, y) in ((40, 0), (35, 5), (45, 5), (37, 1), (44, 1)):
        if f.lab[y, x] == 0:
            f.lab[y, x] = MS
    # back sleeve, robe (shadow band), three folds, hem
    f.paint(f.mask("poly", [(11, 22), (17, 22), (17, 40), (11, 42), (8, 34)]), MD, sep=False)
    robe = f.mask("poly", [(12, 21), (28, 21), (30, 34), (33, 55), (36, 63), (4, 63), (6, 50), (10, 34)])
    f.shade(robe, [(0.2, MS), (0.0, MD)], rim=False)
    for frac, ph in ((0.42, 0.0), (0.62, 1.3), (0.82, 2.1)):
        for y in range(41, 62):
            xs = np.nonzero(robe[y])[0]
            x = int(round(xs[0] + (xs[-1] - xs[0]) * frac + 1.0 * math.sin(y / 5 + ph)))
            f.lab[y, x] = MK
    for x in range(48):
        if robe[61, x] and (x // 3) % 2:
            f.lab[61, x] = MK
    # rope belt, knot + cords, pouch
    for y in (36, 39):
        f.lab[y][robe[y]] = MK
    for y in (37, 38):
        f.lab[y][robe[y]] = MS
    f.paint(f.mask("ell", 23, 39.5, 2.2, 1.8), MS)
    for x0 in (22, 24):
        f.paint(f.mask("line", [(x0, 41), (x0 + (x0 - 23), 48)]), MS)
    f.paint(f.mask("ell", 12.5, 43, 3.6, 4.0), MS)
    f.lab[41, 9:16] = MK
    f.lab[43, 12] = MK
    # beard with strands
    beard = f.mask("poly", [(21, 17), (29, 17), (30, 25), (27, 35), (24, 43), (22, 34), (20, 24)])
    f.paint(beard, MS)
    for k, x0 in enumerate((22, 25, 28)):
        f.lab[f.mask("line", _bez((x0, 20), (x0 - 1, 28), (24 + k * 0.5, 38))) & beard & ~dilate(~beard, 1)] = MK
    # face: nose, eye, moustache; brim shadow
    face = f.mask("poly", [(21, 12), (29, 12), (31, 15), (33, 16.5), (30, 18), (22, 18)])
    f.paint(face, MS)
    f.lab[13, 21:31][face[13, 21:31]] = MD
    f.lab[14, 28] = MK
    f.lab[18, 26:30] = MK
    # hat: wide brim, bent cone, band + buckle, star
    brim = f.mask("ell", 21, 10.6, 14.5, 2.2)
    f.paint(brim, MS)
    cone = f.mask("poly", [(12, 10), (30, 10), (26, 5), (21, 1), (14, 0), (6, 3), (14, 4.5)])
    f.shade(cone, [(0.22, MS), (0.0, MD)], rim=False)
    f.lab[8][cone[8] & (np.arange(48) > 12)] = MK
    f.lab[7:10, 22] = f.lab[7:10, 25] = MK
    f.lab[7, 22:26] = MK
    for (x, y) in ((18, 3), (17, 4), (18, 4), (19, 4), (18, 5)):
        f.lab[y, x] = MK
    # front sleeve to the staff, cuff, hand over the staff
    f.paint(f.mask("poly", [(25, 22), (31, 22), (38, 27), (40, 33), (34, 38), (29, 34), (26, 28)]), MS)
    f.lab[f.mask("line", [(35, 36), (40, 31)])] = MK
    f.lab[f.mask("line", [(27, 27), (33, 33)])] = MD
    f.paint(f.mask("ell", 40.5, 29, 2.6, 2.6), MS)
    f.lab[29, 40] = MK
    return f


def torch_native(s: Scr, x0, y0, smoke=True):
    """Native 16x32 torch in the game's cell inks: flame Y+ (2 rows), bowl Y, bracket W."""
    s.clear_rect(x0, y0, 16, 32)
    F, BOWL, BR = YEL + B, YEL, WHITE
    fl = np.zeros((16, 16), bool)
    core = np.zeros((16, 16), bool)
    for y in range(16):
        t = y / 15
        c = 7.5 + 1.1 * math.sin(y / 2.6)
        hw = 5.6 * t ** 0.7
        for x in range(16):
            if abs(x + 0.5 - c) <= hw:
                fl[y, x] = True
            if y >= 6 and abs(x + 0.5 - c) <= hw - 2.1:
                core[y, x] = True
    for (tx, ty, bx, by) in ((2.5, 4.0, 5.0, 13.0), (13.5, 6.0, 10.5, 13.0)):   # side tongues
        for y in range(int(ty), 16):
            t = (y - ty) / (by - ty)
            cx = tx + (bx - tx) * min(1.0, t)
            for x in range(16):
                if abs(x + 0.5 - cx) <= 1.7 * min(1.0, t) ** 0.8:
                    fl[y, x] = True
    inner = np.zeros((16, 16), bool)
    for y in range(9, 16):
        for x in range(16):
            if abs(x + 0.5 - 7.8) <= 1.6 * ((y - 9) / 6) ** 0.6:
                inner[y, x] = True
    img = (fl & ~core) | inner
    for (x, y) in ((4, 0), (11, 1), (8, 0)):
        img[y, x] = True                             # sparks
    s.bits(img, x0, y0, F)
    # bowl (Y): rim, curved cup, stem
    for y in range(16, 24):
        for x in range(16):
            X, Y = x0 + x, y0 + y
            if y in (16, 17) and 1 <= x <= 14:
                if y == 16 or dith(X, Y, 0.5):
                    s.put(X, Y, BOWL)
            elif 18 <= y <= 21:
                hw = 6 - (y - 18) * 1.0
                if abs(x + 0.5 - 8) <= hw and (abs(x + 0.5 - 8) > hw - 1.2 or dith(X, Y, 0.25 + 0.5 * (x < 8))):
                    s.put(X, Y, BOWL)
            elif y >= 22 and 6 <= x <= 9:
                s.put(X, Y, BOWL)
    # bracket (W): stem, collar, riveted wall plate
    for y in range(24, 32):
        for x in range(16):
            X, Y = x0 + x, y0 + y
            if 7 <= x <= 8 and y <= 26:
                s.put(X, Y, BR)
            elif y == 25 and 5 <= x <= 10:
                s.put(X, Y, BR)
            elif 27 <= y <= 31 and 3 <= x <= 12:
                edge = y in (27, 31) or x in (3, 12)
                rivet = (x, y) in ((5, 29), (10, 29))
                if not rivet and (edge or dith(X, Y, 0.35)):
                    s.put(X, Y, BR)
    if smoke:  # wisps rising into the column cells above (W)
        for k, ph in enumerate((0.0, 2.2)):
            for y in range(y0 - 14, y0 - 1):
                x = int(x0 + 8 + (k * 2 - 1) * 2 + 2.2 * math.sin((y - y0) / 3.0 + ph))
                if (y + k) % 3:
                    s.clr(x - 1, y)
                    s.clr(x + 1, y)
                    s.put(x, y, WHITE)


def column_native(s: Scr, x0, tcells, top=32, base=136):
    """Fluted column 16 px wide: abacus + echinus + astragal, shaded shaft, torus + plinth."""
    C = WHITE
    for y in range(top, base):
        if (x0 // 8, y // 8) in tcells:
            continue
        for x in range(x0, x0 + 16):
            u = x - x0
            on = False
            if y < top + 2:                                  # abacus
                on = True
            elif y < top + 7:                                # echinus: swelling curve
                inset = int(round(2.4 * ((y - top - 2) / 4) ** 1.6))
                on = inset <= u <= 15 - inset and (u in (inset, 15 - inset) or y == top + 2
                                                   or dith(x, y, 0.55 - 0.08 * (y - top - 2)))
            elif y == top + 7:
                on = False
            elif y == top + 8:                               # astragal ring
                on = 2 <= u <= 13
            elif y >= base - 8:                              # torus, scotia, plinth
                yy = y - (base - 8)
                if yy <= 2:
                    on = 1 <= u <= 14 and (yy != 1 or u in (1, 14) or dith(x, y, 0.75))
                elif yy == 3:
                    on = 3 <= u <= 12 and u % 2 == 0
                else:
                    on = yy in (4, 7) or u in (0, 15) or dith(x, y, 0.3)
            else:                                            # shaft, 12 px, 3 flutes
                if 2 <= u <= 13:
                    if u in (2, 13):
                        on = True
                    elif u in (5, 8, 11):
                        on = False
                    else:
                        lvl = 0.92 - 2.2 * ((u - 6.5) / 11) ** 2 - 0.1 * (u > 8)
                        on = dith(x, y, lvl)
            if on:
                s.put(x, y, C)


def tome_native(s: Scr, BX=128, BY=100, FLOOR=152):
    """The Tome + lectern at 1:1: curved pages with text lines and gutter shade, skull +
    pentacle, leather cover with clasp strap, ribbon; shaded lectern with mouldings."""
    G_ = GREEN + B
    lab = np.zeros((H, W), np.uint8)
    for x in range(BX - 42, BX + 42):
        t = min(1.0, abs(x + 0.5 - BX) / 40)
        top = int(BY - 12 + 7 * t - 9 * math.sin(math.pi * min(1, t * 1.1)) * 0.6)
        bot = top + 26 - int(3 * t)
        if abs(x + 0.5 - BX) < 40:
            lab[top:bot, x] = MS
            lab[bot, x] = MK
            if abs(x + 0.5 - BX) >= 36 and x % 2 == 0:
                lab[top + 1:bot, x] = MK                 # page stack at the fore-edge
            if abs(x + 0.5 - BX) < 3.5:
                lab[top:bot, x] = MD                     # gutter shadow
            if abs(x - BX) < 1:
                lab[top:bot, x] = MK
        lab[bot + 1:bot + 4, x] = MD                     # leather cover
        lab[bot + 1, x] = MS if abs(x + 0.5 - BX) < 41 else MD
        lab[bot + 3, x] = MS
    # text lines on both pages (dotted words), kept clear of the skull / pentacle
    for y in range(BY - 14, BY + 20):
        for x in range(BX - 36, BX + 36):
            if lab[y, x] != MS or abs(x - BX) < 5:
                continue
            left = x < BX
            busy = (left and y <= BY + 6) or (not left and y <= BY + 10)
            if not busy and (y - BY) % 3 == 0 and x % 2 == 0 and hsh(x // 5, y, 9) % 6 and lab[y + 1, x] == MS:
                lab[y, x] = MK
    sk = np.pad(G.SKULL_BM, 1)
    for y, x in zip(*np.nonzero(dilate(sk, 1) & ~sk)):
        lab[BY - 13 + y, BX - 31 + x] = MK
    for i in range(5):
        a1, a2 = -math.pi / 2 + i * 4 * math.pi / 5, -math.pi / 2 + (i + 1) * 4 * math.pi / 5
        x1, y1 = BX + 21 + 9 * math.cos(a1), BY - 3 + 9 * math.sin(a1)
        x2, y2 = BX + 21 + 9 * math.cos(a2), BY - 3 + 9 * math.sin(a2)
        for k in range(49):
            lab[int(round(y1 + (y2 - y1) * k / 48)), int(round(x1 + (x2 - x1) * k / 48))] = MK
    for k in range(96):
        a = k * 2 * math.pi / 96
        lab[int(round(BY - 3 + 11 * math.sin(a))), int(round(BX + 21 + 11 * math.cos(a)))] = MK
    # clasp strap hanging from the right board, ribbon from the gutter
    cb = int(BY - 12 + 7 - 9 * math.sin(math.pi) * 0.6) + 23 + 4
    for y in range(cb - 3, cb + 7):
        for x in range(BX + 38, BX + 42):
            lab[y, x] = MK if x == BX + 38 or (y == cb + 6) else MS
    lab[cb + 2:cb + 5, BX + 39:BX + 41] = MK
    lab[cb + 3, BX + 40] = MS
    rb = int(BY - 12) + 26
    for y in range(rb, rb + 13):
        x = BX + 2 + int(round(1.3 * math.sin((y - rb) / 2.5)))
        lab[y, x] = MS
        lab[y, x + 1] = MK
    # lectern: slanted desk, moulded column (cylinder shade), stepped base
    for y in range(116, FLOOR):
        if y < 124:
            hw = 18 - (y - 116)
        elif y < FLOOR - 12:
            hw = 6
        elif y < FLOOR - 6:
            hw = 10
        else:
            hw = 16
        for x in range(BX - hw, BX + hw):
            if lab[y, x]:
                continue
            u = abs(x + 0.5 - BX) / hw
            lab[y, x] = MS if (u < 0.35 or x == BX - hw or x == BX + hw - 1) else MH if u < 0.6 else MD
        if y in (123, 124, FLOOR - 13, FLOOR - 7):
            lab[y, BX - hw:BX + hw] = MK if y in (124, FLOOR - 7) else MS
    for y in range(127, FLOOR - 13, 5):
        lab[y, BX - 6:BX + 6] = MK                       # ring mouldings
    sil = lab != 0
    for y, x in zip(*np.nonzero(dilate(sil, 2))):      # halo + interior start black
        s.clr(x, y)
    for y, x in zip(*np.nonzero(sil)):
        m = lab[y, x]
        if m == MS or (m == MH and dith(x, y, 0.75)) or (m == MD and dith(x, y, 0.5)):
            s.put(x, y, G_)
    for k in range(3):                                   # rising wisps, as L3
        x0 = BX - 16 + 16 * k
        for y in range(52, BY - 20):
            xx = int(x0 + 4 * math.sin((y + 7 * k) / 6))
            if dith(xx, y, 0.9):
                s.put(xx, y, G_)
                s.clr(xx + 1, y)
                s.clr(xx - 1, y)
    return sil


RUNES = [["#.#", ".#.", "#.#"], ["###", "#..", "###"], ["#..", "###", "..#"], [".#.", "###", ".#."],
         ["#.#", "###", "#.#"], ["##.", ".#.", ".##"], ["###", ".#.", "#.#"], ["#.#", "#.#", "###"]]


def l3d() -> Scr:
    s = Scr()
    menu_title(s, G.by_row([WHITE + B, WHITE + B, CYAN + B, CYAN + B], 0))
    G_, STONE, ARCH = GREEN + B, WHITE, BLUE + B
    FLOOR = 136
    cols_ = [0, 8, 22, 30]
    torches = [(c, 6) for c in cols_]
    tcells = set().union(*(box(c, r, 2, 4) for c, r in torches))
    colc = set().union(*(box(c, 4, 2, 13) for c in cols_)) - tcells
    archc = box(2, 4, 6, 3) | box(24, 4, 6, 3)
    glowc = box(10, 4, 12, 13)
    # figures first (as label images) so their cells are known
    war, mag = warrior_fig().lab, mage_fig().lab[:, ::-1]
    WX, MX, FY = 16, 192, 152 - 64
    hero_c = set()
    for lab, x0 in ((war, WX), (mag, MX)):
        for y, x in zip(*np.nonzero(lab)):              # (the black halo may cross cells)
            hero_c.add(((x0 + x) // 8, (FY + y) // 8))
    # rune circle: clean ellipse + 8 glyphs
    RX, RY, RCX, RCY = 72, 9, 128, 150
    rune_px = np.zeros((H, W), bool)
    prev = None
    for x in range(RCX - RX, RCX + RX + 1):
        dy = RY * math.sqrt(max(0.0, 1 - ((x + 0.5 - RCX) / RX) ** 2))
        for sgn in (-1, 1):
            y = int(round(RCY + sgn * dy))
            if y < 160:
                rune_px[y, x] = True
        if prev is not None:                           # close vertical gaps at the ends
            for sgn in (-1, 1):
                y0_, y1_ = sorted((int(round(RCY + sgn * prev)), int(round(RCY + sgn * dy))))
                for y in range(y0_, y1_ + 1):
                    if y < 160:
                        rune_px[y, x] = True
        prev = dy
    glyph_px = np.zeros((H, W), bool)
    for k in range(12):
        a = math.pi + k * 2 * math.pi / 12 + 0.26
        gx, gy = int(round(RCX + RX * math.cos(a))), int(round(RCY + RY * math.sin(a)))
        if gy + 2 >= 160 or gy - 2 < 136:
            continue
        g = RUNES[k % len(RUNES)]
        rune_px[gy - 2:gy + 3, gx - 2:gx + 3] = False
        for j, row in enumerate(g):
            for i, ch in enumerate(row):
                if ch == "#":
                    glyph_px[gy - 1 + j, gx - 1 + i] = True
    rune_px |= glyph_px
    lecmask = tome_masks(128, 100, 152)[0]
    lec_cells = {(x // 8, y // 8) for y, x in zip(*np.nonzero(dilate(lecmask, 2))) if y >= 136}
    rune_cells = {(x // 8, y // 8) for y, x in zip(*np.nonzero(rune_px))} - lec_cells - hero_c
    cm = {}
    compromised = 0
    for r in range(4, 20):
        for c in range(32):
            if (c, r) in tcells:
                continue
            if (c, r) in lec_cells:
                v = G_
            elif r >= 17:
                v = YEL + B if (c, r) in rune_cells else (MAG if (c + r) % 2 else BLUE)
            elif (c, r) in colc:
                v = STONE
            elif (c, r) in archc:
                v = ARCH
            elif (c, r) in glowc:
                v = G_
            else:
                v = BLUE
            if (c, r) in hero_c:
                compromised += r >= 17                  # floor cells taken by the feet
                v = WHITE + B
            cm[(c, r)] = v
    assert not (hero_c & (colc | tcells | glowc | archc)), "figures must stay in the aisles"
    ink = cell_ink(cm, BLUE)
    for c in cols_:
        column_native(s, c * 8, tcells)
    for (a, b) in ((16, 64), (192, 240)):              # pointed arches + voussoir joints
        cx, half = (a + b) / 2, (b - a) / 2
        for y in range(32, 56):
            t = (56 - y) / 24
            off = half * math.sqrt(max(0.0, 1 - t * t))
            for xx in (int(cx - off), int(cx + off) - 1, int(cx - off) + 1, int(cx + off) - 2):
                s.put(xx, y, ink(xx, y))
            for x in range(a, b):
                if abs(x + 0.5 - cx) > off + 1:
                    joint = (x - a) % 8 == 4 and (y - 32) % 6 < 5
                    if (y - 32) % 6 == 5 or joint or dith(x, y, 0.3):
                        s.put(x, y, ink(x, y))
        for y in range(56, FLOOR):
            for x in range(a, b):
                if (x // 8, y // 8) not in hero_c and dith(x, y, 0.07 if (y // 6) % 2 else 0.12):
                    s.put(x, y, ink(x, y))
    radiance(s, ink, lambda c, r: (c, r) in glowc, y1=FLOOR, reach=0.9)
    for y in range(FLOOR, 160):                        # floor: checker, rune circle
        for x in range(W):
            cell = (x // 8, y // 8)
            if cell in lec_cells:
                continue
            if cell in rune_cells:
                if rune_px[y, x]:
                    s.put(x, y, ink(x, y))
                continue
            if x % 8 == 0 or y % 8 == 0 or ((x // 8 + y // 8) % 2 and dith(x, y, 0.25)):
                s.put(x, y, ink(x, y))
    for c, r in torches:
        torch_native(s, c * 8, r * 8)
    tome_native(s)
    render_fig(s, war, WX, FY, WHITE + B)
    render_fig(s, mag, MX, FY, WHITE + B)
    text_c(s, "THE TOME OF ABSOLUTE DEATH MAGIC", 160, G_)
    text_c(s, CREDIT, 168, WHITE)
    s.compromised = compromised
    s.notes = [
        "L3c redrawn at 1:1, no scaled sprites. Warrior / Mage are 48x64 hand-built figures",
        "(shapes + material labels: solid lit side, 75/50/25 % dither shadow, chainmail texture,",
        "black seams, rim light on the shadow edge), W+ in the aisles cols 2-7 / 24-29 rows 11-18.",
        "Torches, fluted columns, Tome + lectern and the rune circle redrawn natively; the cell plan",
        f"is L3c's. Floor cells given to the figures' feet (W+ instead of checker): {compromised}.",
    ]
    return s


# ---------------------------------------------------------------- validation
def validate(tag, s: Scr, bm, attr):
    """Independent clash check on the intended composition + exact .scr round trip."""
    want = np.zeros((H, W, 3), np.uint8)
    bad = []
    for r in range(24):
        for c in range(32):
            blk = s.px[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            pap = int(s.paper[r, c])
            vals = {pap if v == NONE else int(v) for v in blk.flat}
            ids = {G.ident(v) for v in vals}
            brs = {v >> 3 for v in vals if G.ident(v)}
            if len(ids) > 2 or len(brs) > 1:
                bad.append((c, r))
            for y in range(8):
                for x in range(8):
                    v = int(blk[y, x])
                    v = pap if v == NONE else v
                    want[r * 8 + y, c * 8 + x] = G.rgb(v & 7, v >> 3) if G.ident(v) else (0, 0, 0)
    scr = G.to_scr(bm, attr)
    bm2, at2 = G.decode_scr(scr)
    img = G.render(bm2, at2)
    # black ink renders black regardless of BRIGHT; compare against the intended colours
    diff = int((img != want).any(2).sum())
    blank = not (s.px[176:] != NONE).any() and not bm2[176:].any()
    ncol = max(len({tuple(p) for p in img[r * 8:r * 8 + 8, c * 8:c * 8 + 8].reshape(-1, 3)})
               for r in range(24) for c in range(32))
    ok = not bad and diff == 0 and blank and ncol <= 2 and len(scr) == 6912
    print(f"{tag}: cells>2col {len(bad)}, px mismatch {diff}, max colours/cell {ncol}, "
          f"rows 22-23 blank {blank}, attrs {len(set(at2.flat))} -> {'PASS' if ok else 'FAIL'}")
    return ok, scr, img


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    comps = [("l1_abyss", l1), ("l2_shaft", l2), ("l3_tome", l3), ("l4_gallery", l4),
             ("l5_mouth", l5),
             ("l6_door", l6), ("l7_drop", l7), ("l8_crypt", l8), ("l9_camp", l9),
             ("l10_skullgate", l10), ("l11_moon", l11), ("l12_crest", l12), ("l13_circle", l13)]
    imgs, allok = [], True
    for tag, fn in comps:
        s = fn()
        bm, attr = s.resolve(tag)
        ok, scr, img = validate(tag, s, bm, attr)
        allok &= ok
        base = os.path.join(OUT, tag)
        open(base + ".scr", "wb").write(scr)
        G.png(img, base + ".png", scale=3)
        G.png(img, base + "_grid.png", scale=3, grid=True)
        imgs.append(img)
    sheet = np.full((H * 4 + 24, W * 4 + 24, 3), 40, np.uint8)
    for i, im in enumerate(imgs):
        r, c = divmod(i, 4)
        sheet[r * (H + 8):r * (H + 8) + H, c * (W + 8):c * (W + 8) + W] = im
    Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(
        os.path.join(OUT, "concepts2_sheet.png"))
    vimgs = [imgs[2]]
    for tag, fn in (("l3a_torches", l3a), ("l3b_colour_rays", l3b), ("l3c_crypt", l3c)):
        s = fn()
        bm, attr = s.resolve(tag)
        ok, scr, img = validate(tag, s, bm, attr)
        allok &= ok
        base = os.path.join(OUT, tag)
        open(base + ".scr", "wb").write(scr)
        G.png(img, base + ".png", scale=3)
        G.png(img, base + "_grid.png", scale=3, grid=True)
        vimgs.append(img)
    vs = np.full((H, W * 4 + 24, 3), 40, np.uint8)
    for i, im in enumerate(vimgs):
        vs[:, i * (W + 8):i * (W + 8) + W] = im
    Image.fromarray(vs).resize((vs.shape[1] * 2, H * 2), Image.NEAREST).save(
        os.path.join(OUT, "concepts2_l3_variants.png"))
    # L3d: L3c at native resolution + the comparison sheet (3x pair, 1:1 pair, 4x crops)
    s = l3d()
    bm, attr = s.resolve("l3d_native")
    ok, scr, img_d = validate("l3d_native", s, bm, attr)
    print(f"l3d_native: compromised cells {s.compromised}")
    allok &= ok
    base = os.path.join(OUT, "l3d_native")
    open(base + ".scr", "wb").write(scr)
    G.png(img_d, base + ".png", scale=3)
    G.png(img_d, base + "_grid.png", scale=3, grid=True)
    img_c = vimgs[3]
    up = lambda a, k: Image.fromarray(a).resize((a.shape[1] * k, a.shape[0] * k), Image.NEAREST)
    crops = [(0, 72, 80, 88), (176, 72, 80, 88)]     # x, y, w, h: both hero aisles
    sheet = Image.new("RGB", (2 * W + 24 + 4 * (80 * 4 + 8), H * 3 + 24 + 88 * 4), (40, 40, 40))
    sheet.paste(up(img_c, 3), (0, 0))
    sheet.paste(up(img_d, 3), (W * 3 + 24, 0))
    y2 = H * 3 + 24
    sheet.paste(Image.fromarray(img_c), (0, y2))
    sheet.paste(Image.fromarray(img_d), (W + 8, y2))
    x = 2 * W + 24
    for (cx, cy, cw, ch) in crops:
        for im in (img_c, img_d):
            sheet.paste(up(im[cy:cy + ch, cx:cx + cw], 4), (x, y2))
            x += cw * 4 + 8
    sheet.save(os.path.join(OUT, "concepts2_l3d.png"))
    print("ALL PASS" if allok else "FAILURES")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
