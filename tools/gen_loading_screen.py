#!/usr/bin/env python3
"""gen_loading_screen.py -- ART14: three LOADING SCREEN compositions (S1..S3).

Deterministic: every pixel comes from structured shapes, ordered dither, the
game's own fonts / torch (assets/gfx/{fonts,menu}) and the approved 40 px hero
grids (vendored in assets/gfx/loading/src/, from feat/3f-art11-40px and the
ART13 nun concept). No raster input, no randomness beyond a fixed hash.

Colour model: the composer paints a per-pixel colour index (ink 0..7 + 8*BRIGHT,
NONE = cell paper). resolve() then enforces the Spectrum rule per 8x8 cell:
<= 2 colour identities (paper + one ink), one BRIGHT bit (black is
BRIGHT-agnostic). Any illegal cell aborts with its coordinates -- the art is
redrawn, never auto-quantised.

Outputs (assets/gfx/loading/):
  loading_s{1,2,3}.scr        6,912 B SCREEN$ image ($4000 layout + attrs)
  loading_s{1,2,3}.png        2x preview, decoded back FROM the .scr
  loading_s{1,2,3}_grid.png   2x preview + attribute-cell grid overlay
  loading_s{1,2,3}_attr.txt   32x24 attribute plan (hex) + legend
  loading_options.png         the three side by side (review sheet)
  loading_options.svg.html    canvas board fragment (F3o)

Usage: python3 tools/gen_loading_screen.py
"""
from __future__ import annotations

import base64
import io
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "gfx", "loading")
SRC = os.path.join(OUT, "src")
FONTS = os.path.join(ROOT, "assets", "gfx", "fonts")
MENU = os.path.join(ROOT, "assets", "gfx", "menu")

W, H = 256, 192
NONE = 255
BLACK, BLUE, RED, MAG, GREEN, CYAN, YEL, WHITE = range(8)
B = 8  # BRIGHT flag in a colour index


def ident(c: int) -> int:
    """Colour identity: black is the same with or without BRIGHT."""
    return 0 if c in (0, 8) else c


# ---------------------------------------------------------------- assets
def load_grid(name: str) -> list[str]:
    rows = []
    for ln in open(os.path.join(SRC, name + ".grid")):
        ln = ln.rstrip("\n")
        if ln.startswith("#") or not ln:
            continue
        rows.append(ln)
    return rows


def font6() -> dict[str, np.ndarray]:
    raw = open(os.path.join(FONTS, "font6x8.bin"), "rb").read()
    return {chr(32 + i): np.array([[(raw[i * 8 + r] >> (7 - b)) & 1 for b in range(6)]
                                   for r in range(8)], bool) for i in range(96)}


MENU_SET = " !-0123456789:>ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def font16() -> dict[str, np.ndarray]:
    raw = open(os.path.join(MENU, "menu_font.bin"), "rb").read()
    return {ch: np.array([[(raw[i * 16 + r] >> (7 - b)) & 1 for b in range(8)]
                          for r in range(16)], bool) for i, ch in enumerate(MENU_SET)}


def title16() -> dict[str, np.ndarray]:
    raw = open(os.path.join(FONTS, "title16.bin"), "rb").read()
    out = {}
    for i, ch in enumerate(" ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        g = raw[i * 32:(i + 1) * 32]
        out[ch] = np.array([[((g[r * 2] << 8 | g[r * 2 + 1]) >> (15 - b)) & 1 for b in range(16)]
                            for r in range(16)], bool)
    return out


def torch_cells() -> tuple[np.ndarray, list[list[int]]]:
    """The game's menu torch (frame 1) as a 32x16 bitmap + its 2x4 attr inks."""
    raw = open(os.path.join(MENU, "menu_torch.bin"), "rb").read()
    swap, static = raw[0:16], raw[48:96]
    cells = [swap[0:8], swap[8:16]] + [static[i * 8:(i + 1) * 8] for i in range(6)]
    bm = np.zeros((32, 16), bool)
    for k, c in enumerate(cells):
        r, col = divmod(k, 2)
        for y in range(8):
            for b in range(8):
                bm[r * 8 + y, col * 8 + b] = (c[y] >> (7 - b)) & 1
    inks = [[YEL + B] * 2, [YEL + B] * 2, [YEL] * 2, [WHITE] * 2]  # menu_torch_attr
    return bm, inks


# 5x7 logotype letters (custom; chunky block font for the big title)
LOGO5 = {
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    " ": ["..", "..", "..", "..", "..", "..", ".."],
}

# 16x16 skull, left half mirrored (symmetric by construction)
SKULL_L = ["....####", "..######", ".#######", "########", "########",
           "###...##", "##.....#", "##.....#", "###...##", ".#######",
           ".######.", "..######", "...#.#.#", "...#####", "...#.#.#", "....####"]
SKULL = [r + r[::-1] for r in SKULL_L]

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])


def dith(x: int, y: int, level: float) -> bool:
    """Ordered dither: True with density `level` (0..1)."""
    return BAYER4[y & 3, x & 3] < level * 16


def hsh(*v: int) -> int:
    h = 2166136261
    for a in v:
        h = ((h ^ (a & 0xFFFF)) * 16777619) & 0xFFFFFFFF
    return h


# ---------------------------------------------------------------- canvas
class Scr:
    def __init__(self):
        self.px = np.full((H, W), NONE, np.uint8)
        self.paper = np.zeros((24, 32), np.uint8)
        self.notes: list[str] = []

    def put(self, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            self.px[y, x] = c

    def clr(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            self.px[y, x] = NONE

    def bits(self, bm, x0, y0, c, scale=1, mirror=False, halo=False):
        """Stamp a bool bitmap in colour c (callable c(x,y) allowed)."""
        bm = np.asarray(bm, bool)
        if mirror:
            bm = bm[:, ::-1]
        if scale > 1:
            bm = bm.repeat(scale, 0).repeat(scale, 1)
        hh, ww = bm.shape
        if halo:  # clear a 1-px black outline (8-neighbour) round the shape
            pad = np.pad(bm, 1)
            dil = np.zeros_like(pad)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    dil |= np.roll(np.roll(pad, dy, 0), dx, 1)
            for y, x in zip(*np.nonzero(dil & ~pad)):
                self.clr(x0 + x - 1, y0 + y - 1)
        for y, x in zip(*np.nonzero(bm)):
            X, Y = x0 + x, y0 + y
            self.put(X, Y, c(X, Y) if callable(c) else c)

    def grid(self, rows, x0, y0, c, scale=1, mirror=False):
        """3-state sprite grid: '#' ink, '+' opaque paper (clears), '.' skip."""
        if mirror:
            rows = [r[::-1] for r in rows]
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                for sy in range(scale):
                    for sx in range(scale):
                        X, Y = x0 + x * scale + sx, y0 + y * scale + sy
                        if ch == "#":
                            self.put(X, Y, c(X, Y) if callable(c) else c)
                        elif ch == "+":
                            self.clr(X, Y)

    def clear_rect(self, x0, y0, w, h):
        self.px[max(0, y0):y0 + h, max(0, x0):x0 + w] = NONE

    def text6(self, s, x0, y0, c, f=None):
        f = f or FONT6
        for i, ch in enumerate(s):
            self.bits(f[ch], x0 + i * 6, y0, c)

    def text16(self, s, x0, y0, c):
        for i, ch in enumerate(s):
            self.bits(FONT16[ch], x0 + i * 8, y0, c)

    # ---- resolve to Spectrum data
    def resolve(self, name):
        bm = np.zeros((H, W), bool)
        attr = np.zeros((24, 32), np.uint8)
        errs = []
        for r in range(24):
            for c in range(32):
                blk = self.px[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
                pap = int(self.paper[r, c])
                vals = {pap if v == NONE else int(v) for v in blk.flat}
                ids = {ident(v) for v in vals}
                brights = {v >> 3 for v in vals if ident(v) != 0}
                if len(ids) > 2 or len(brights) > 1 or (len(ids) == 2 and ident(pap) not in ids):
                    errs.append(f"cell ({c},{r}) colours {sorted(vals)}")
                    continue
                inks = [v for v in vals if ident(v) != ident(pap)]
                ink = inks[0] if inks else WHITE
                br = (brights.pop() if brights else 0)
                attr[r, c] = (br << 6) | ((pap & 7) << 3) | (ink & 7)
                sub = np.vectorize(lambda v: ident(pap if v == NONE else int(v)) != ident(pap))(blk)
                bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = sub
        if errs:
            raise SystemExit(f"{name}: attribute clash in {len(errs)} cells:\n  " + "\n  ".join(errs[:40]))
        return bm, attr


# ---------------------------------------------------------------- .scr I/O
def scr_addr(y: int) -> int:
    return ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)


def to_scr(bm, attr) -> bytes:
    out = bytearray(6912)
    for y in range(H):
        for c in range(32):
            v = 0
            for b in range(8):
                v = (v << 1) | int(bm[y, c * 8 + b])
            out[scr_addr(y) + c] = v
    out[6144:] = bytes(attr.flatten())
    return bytes(out)


def decode_scr(data: bytes):
    assert len(data) == 6912
    bm = np.zeros((H, W), bool)
    for y in range(H):
        for c in range(32):
            v = data[scr_addr(y) + c]
            for b in range(8):
                bm[y, c * 8 + b] = (v >> (7 - b)) & 1
    return bm, np.frombuffer(data[6144:], np.uint8).reshape(24, 32)


def rgb(idx: int, bright: int):
    lv = 0xFF if bright else 0xD7
    return ((idx >> 1 & 1) * lv, (idx >> 2 & 1) * lv, (idx & 1) * lv)


def render(bm, attr) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    for r in range(24):
        for c in range(32):
            a = int(attr[r, c])
            br = a >> 6 & 1
            ink, pap = rgb(a & 7, br), rgb(a >> 3 & 7, br)
            blk = bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = np.where(blk[..., None], ink, pap)
    return img


def png(img, path, scale=2, grid=False):
    im = Image.fromarray(img).resize((W * scale, H * scale), Image.NEAREST)
    if grid:
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for c in range(1, 32):
            d.line([(c * 8 * scale, 0), (c * 8 * scale, H * scale)], fill=(255, 0, 255, 110))
        for r in range(1, 24):
            d.line([(0, r * 8 * scale), (W * scale, r * 8 * scale)], fill=(255, 0, 255, 110))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    im.save(path)
    return im


# ---------------------------------------------------------------- shared art
FONT6 = font6()
FONT16 = font16()
T16 = title16()
TORCH, TORCH_INK = torch_cells()
KNIGHT = load_grid("knight_idle1")
MAGE = load_grid("wizard_idle")
MAGE_CAST = load_grid("wizard_cast1")
NUN = load_grid("nun_a_cast")
SKULL_BM = np.array([[ch == "#" for ch in r] for r in SKULL])


def logo5(text, bw, bh, gap, chamfer=True):
    """Big block-letter logotype -> bool bitmap (7*bh tall)."""
    widths = [len(LOGO5[ch][0]) * bw for ch in text]
    tw = sum(widths) + gap * (len(text) - 1)
    bm = np.zeros((7 * bh, tw), bool)
    x = 0
    for ch, wd in zip(text, widths):
        g = LOGO5[ch]
        on = lambda i, j: 0 <= i < 7 and 0 <= j < len(g[i]) and g[i][j] == "#"
        for i in range(7):
            for j in range(len(g[i])):
                if not on(i, j):
                    continue
                y0, x0 = i * bh, x + j * bw
                bm[y0:y0 + bh, x0:x0 + bw] = True
                if chamfer:  # round convex corners: cut a diagonal
                    k = min(bw, bh) - 1
                    for (di, dj, cy, cx) in ((-1, -1, 0, 0), (-1, 1, 0, 1), (1, -1, 1, 0), (1, 1, 1, 1)):
                        if not on(i + di, j) and not on(i, j + dj) and not on(i + di, j + dj):
                            for t in range(k):
                                for u in range(k - t):
                                    yy = y0 + (t if cy == 0 else bh - 1 - t)
                                    xx = x0 + (u if cx == 0 else bw - 1 - u)
                                    bm[yy, xx] = False
        x += wd + gap
    return bm


def chrome(bm, rows):
    """Cut 1-px horizontal paper lines (chrome-stripe shading) at the given rows."""
    bm = bm.copy()
    for y in rows:
        if 0 <= y < bm.shape[0]:
            bm[y, :] = False
    return bm


def outline_dither(bm, level):
    """Letter outline (2 px) + ordered-dither interior."""
    er = bm.copy()
    for _ in range(2):
        e = er.copy()
        e[1:, :] &= er[:-1, :]
        e[:-1, :] &= er[1:, :]
        e[:, 1:] &= er[:, :-1]
        e[:, :-1] &= er[:, 1:]
        er = e
    out = bm & ~er
    ys, xs = np.nonzero(er)
    for y, x in zip(ys, xs):
        if dith(x, y, level):
            out[y, x] = True
    return out


def script_logo(text):
    """A title line in the game's title16 script glyphs, 2x (32 px tall)."""
    adv = 13
    bm = np.zeros((16, adv * len(text) + 4), bool)
    for i, ch in enumerate(text):
        g = T16[ch]
        x = i * adv - 2
        for y, xx in zip(*np.nonzero(g)):
            if 0 <= x + xx < bm.shape[1]:
                bm[y, x + xx] = True
    cols = np.nonzero(bm.any(0))[0]
    bm = bm[:, cols[0]:cols[-1] + 1]
    return bm.repeat(2, 0).repeat(2, 1)


def by_row(inks, row0):
    """Colour callable: ink chosen by the cell row (attribute gradient)."""
    return lambda x, y: inks[min(len(inks) - 1, max(0, y // 8 - row0))]


def bricks(s: Scr, cells, colour_of, bw=16, bh=6, seed=0):
    """Mortar-line brick texture in the given cells; colour_of(c,r) -> ink|None."""
    for (c, r) in cells:
        col = colour_of(c, r)
        if col is None:
            continue
        for y in range(r * 8, r * 8 + 8):
            row = y // bh
            off = (bw // 2) if row & 1 else 0
            for x in range(c * 8, c * 8 + 8):
                mortar = (y % bh == bh - 1) or ((x + off) % bw == 0)
                speck = (not mortar and hsh(x // 2, y // 2, seed) % 23 == 0)
                if mortar or speck:
                    s.put(x, y, col)


def light(cx, cy, steps):
    """Torch falloff: distance (cells) thresholds -> ink; None beyond."""
    def f(c, r):
        d = ((c + 0.5 - cx) ** 2 + ((r + 0.5 - cy) * 1.15) ** 2) ** 0.5
        for lim, ink in steps:
            if d < lim:
                return ink
        return None
    return f


def place_torch(s: Scr, col, row):
    s.bits(TORCH, col * 8, row * 8,
           lambda x, y: TORCH_INK[y // 8 - row][(x // 8) - col], halo=True)


def box(c0, r0, w, h):
    return {(c, r) for c in range(c0, c0 + w) for r in range(r0, r0 + h)}


def centre(width):
    return (W - width) // 2


SUB = "A DUNGEON ROGUELIKE - ZX SPECTRUM 128K"
CREDIT = "by alstepan, 2026"


# ================================================================ S1 THE GATE
def s1() -> Scr:
    """Title over a torch-lit arched doorway; stairs descend into the dark."""
    s = Scr()
    # -- logo rows 1-4: chrome block letters, fire gradient per cell row
    fire = by_row([YEL + B, YEL + B, YEL, RED + B, RED + B, RED], 0)
    for i, line in enumerate(("TOME OF", "THE DEAD")):
        lg = chrome(logo5(line, 4, 3, 4), [14, 18])
        s.bits(lg, centre(lg.shape[1]), 1 + 24 * i, fire)
    s.text6(SUB, centre(len(SUB) * 6), 48, CYAN)

    # -- torch light map (two torches flank the arch)
    tl, tr = (9, 12), (22, 12)
    steps = [(1.9, YEL), (3.0, RED + B), (4.3, RED)]
    lf = light(tl[0] + 1, tl[1] + 0.5, steps)
    rf = light(tr[0] + 1, tr[1] + 0.5, steps)
    torch_cells_set = box(tl[0], tl[1], 2, 4) | box(tr[0], tr[1], 2, 4)

    def lit(c, r):
        if (c, r) in torch_cells_set:  # glow: wall in torch cells takes the torch ink
            ci = c - (tl[0] if c < 16 else tr[0])
            return TORCH_INK[r - tl[1]][ci]
        a, b = lf(c, r), rf(c, r)
        return a if a is not None else b

    # -- the arch: opening x 96..159, jambs cols 11/20, ring r 32..40 round (128,104)
    cx, cy, ri, ro = 128, 104, 32, 41
    arch_cells = set()
    stone = np.zeros((H, W), bool)
    for y in range(56, 168):
        for x in range(80, 176):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            rr = (dx * dx + dy * dy) ** 0.5
            if y < cy:
                ring = ri <= rr < ro
                if ring:
                    ang = np.degrees(np.arctan2(-dy, dx))
                    joint = any(abs(ang - a) < 1.2 * 40 / max(rr, 1) for a in range(0, 181, 20))
                    edge = rr < ri + 1 or rr >= ro - 1
                    stone[y, x] = joint or edge or (hsh(x, y) % 17 == 0)
            elif 87 <= x < 96 or 160 <= x < 169:
                xx = x - 87 if x < 96 else 168 - x
                stone[y, x] = xx in (0, 8) or (y - cy) % 8 == 7 or (hsh(x, y) % 17 == 0)
    for y, x in zip(*np.nonzero(stone)):
        arch_cells.add((x // 8, y // 8))
    interior = {(c, r) for c in range(12, 20) for r in range(9, 21)}
    hero_l, hero_r = box(2, 16, 3, 5), box(27, 16, 3, 5)

    wall = {(c, r) for c in range(32) for r in range(7, 21)} - interior - hero_l - hero_r
    bricks(s, sorted(wall - arch_cells), lit, seed=1)
    for y, x in zip(*np.nonzero(stone)):
        col = lit(x // 8, y // 8)
        s.put(x, y, col if col is not None else BLUE)
    # bricks inside ring cells that lie outside the ring get the ring ink
    for (c, r) in arch_cells:
        col = lit(c, r) or BLUE
        for y in range(r * 8, r * 8 + 8):
            for x in range(c * 8, c * 8 + 8):
                dx, dy = x + 0.5 - cx, y + 0.5 - cy
                outside = (y < cy and (dx * dx + dy * dy) ** 0.5 >= ro) or (y >= cy and (x < 87 or x >= 169))
                if outside and lit(c, r) is not None:
                    bw, bh = 16, 6
                    off = 8 if (y // bh) & 1 else 0
                    if y % bh == bh - 1 or (x + off) % bw == 0:
                        s.put(x, y, col)

    # -- stairs descending inside the doorway (perspective, darker with depth)
    # Tunnel: near mouth x 98..158 at y 167, far end x 113..143 at y 122; beyond = black.
    stair_ink = {20: WHITE + B, 19: WHITE, 18: CYAN, 17: CYAN, 16: BLUE + B, 15: BLUE}
    sc = lambda x, y: stair_ink.get(y // 8)
    yn, yf, hn, hf = 167, 122, 30, 15
    hw = lambda y: hf + (hn - hf) * (y - yf) / (yn - yf)
    edges = [167, 158, 150, 143, 137, 132, 128, 125, 122]
    for k, ey in enumerate(edges):
        w = int(hw(ey) + 0.5)
        for x in range(128 - w, 128 + w):
            if sc(x, ey) is not None:
                s.put(x, ey, sc(x, ey))
        if k + 1 < len(edges):  # riser = dithered face under the next (farther) edge
            ny = edges[k + 1]
            depth = 1 - k / len(edges)
            for y in range(ny + 1, ey - max(1, (ey - ny) // 3)):
                ww = int(hw(y) + 0.5)
                for x in range(128 - ww + 1, 128 + ww - 1):
                    if sc(x, y) is not None and dith(x, y, 0.45 * depth):
                        s.put(x, y, sc(x, y))
    for y in range(yf, yn + 1):  # tunnel side walls
        w = int(hw(y) + 0.5)
        for x in (128 - w, 128 + w - 1):
            if sc(x, y) is not None:
                s.put(x, y, sc(x, y))

    # -- keystone skull, torches, heroes
    s.clear_rect(120, 56, 16, 16)
    s.bits(SKULL_BM, 120, 56, WHITE + B)
    place_torch(s, *tl)
    place_torch(s, *tr)
    s.grid(KNIGHT, 2 * 8, 16 * 8, WHITE + B)
    s.grid(MAGE, 27 * 8, 16 * 8, CYAN + B, mirror=True)

    # -- floor row 21 (flagstones), text rows 22-23
    for x in range(W):
        if 96 <= x < 160:
            continue
        s.put(x, 168, WHITE)
        if x % 2 == 0:
            s.put(x, 170, WHITE)
        if x % 24 == 12:
            for y in range(171, 176):
                s.put(x, y, WHITE)
    for x in range(96, 160):
        s.put(x, 168, WHITE + B if x % 2 == 0 else NONE)
    s.text6(CREDIT, centre(len(CREDIT) * 6), 184, WHITE)
    s.text6("PRESS PLAY ON TAPE", centre(18 * 6), 176, YEL)
    s.notes = [
        "Paper black everywhere; every cell has exactly one ink.",
        "Title rows 0-5 (TOME OF / THE DEAD, 3 rows each): ink per cell row Y+ Y+ Y R+ R+ R; chrome stripes = paper.",
        "Torch light is an attribute map: wall cells take yellow / bright red / red by distance from",
        "the flame; out of the light no bricks are drawn (darkness), so the arch ring alone falls back",
        "to blue. Torch cells reuse the game torch inks ($46/$46/$06/$07); bricks inside them glow.",
        "Stairs: ink per row W+ W C C B+ B (depth = darkness). Heroes stand in the dark cols 2-4 /",
        "27-29 where no wall is drawn, so the sprite owns its 3x5 cells (W+ Warrior, C+ Mage).",
    ]
    return s


# ---------------------------------------------------------------- S2 Archmage, native HD
NUN_X0, NUN_Y0 = 23 * 8, 10 * 8          # 64 x 88 px block: cols 23-30, rows 10-20
WIMPLE_CELLS = box(26, 11, 3, 3)          # coif / wimple / face: W+ cells, crisp at cell edges


RED_FACE_CELLS = box(26, 12, 3, 1) | {(27, 13)}   # S2b: PAPER W+, INK R+

# S2c crone face: the 3x3 W+ head block (24x24 px, local x 24..47, y 8..31) as a
# designed LEFT half (12 cols, col 11 touches the axis), mirrored. Codes:
#   '#' coif (solid white)   '.' black gap / outside   'k' aged skin (75% dither)
#   'h' lit skin (forehead, cheekbone, nose ridge, chin)   'e' sunken socket
#   'g' eye glint   's' shadow (hollows, wrinkles)   'm' mouth seam
#   'l' lip (white in a, red in b)   't' stitch (black in a, white in b)
CRONE_HALF = [
    "....########",   # 0  coif crown
    "..##########",   # 1
    ".###########",   # 2
    "############",   # 3
    "############",   # 4
    "#######.....",   # 5  top of the face opening
    "######.kkhhh",   # 6  forehead
    "#####.kkshhh",   # 7  wrinkle
    "#####.kksssh",   # 8  brow ridge in shadow
    "#####.keeeeh",   # 9  sunken socket
    "#####.segeeh",   # 10 glint, crow's foot
    "#####.kkeekh",   # 11
    "####.khhhksh",   # 12 high cheekbone
    "####.kkhkksh",   # 13
    "#####.sskksh",   # 14 hollow cheek, thin nose
    "#####.sskkeh",   # 15 nostril, nose tip
    "#####.skkkkk",   # 16
    "######.kkllt",   # 17 upper lip + stitch
    "######.ksmmm",   # 18 mouth seam
    ".#####.kkllt",   # 19 lower lip + stitch; bib tapers
    "..####.skkkh",   # 20 long jaw
    "...####.skkh",   # 21
    "....####.kkh",   # 22 bony chin
    "......###...",   # 23 under the chin
]
CRONE = [r + r[::-1] for r in CRONE_HALF]
assert len(CRONE) == 24 and all(len(r) == 24 for r in CRONE)


def narrow_coif(grid: list[str], d: int = 3) -> list[str]:
    """S2d: keep coif ('#') only within d px (Chebyshev) of the face; the rest of the
    head block becomes black -- the gap between the tight coif and the veil."""
    face = {(j, i) for j, r in enumerate(grid) for i, ch in enumerate(r) if ch in "khegsmlt"}
    out = []
    for j, r in enumerate(grid):
        row = []
        for i, ch in enumerate(r):
            near = any((j + dj, i + di) in face for dj in range(-d, d + 1) for di in range(-d, d + 1))
            row.append(ch if ch != "#" or near else ".")
        out.append("".join(row))
    return out


CRONE_NARROW = narrow_coif(CRONE)


def crone_face(s: Scr, X0: int, Y0: int, red: bool, narrow: bool = False):
    """Stamp the S2c head block. a: W+ on black. b: RED_FACE_CELLS become PAPER W+
    / INK R+ so sockets, face edge, shadows, mouth and lips turn red there."""
    if red:
        for (c, r) in RED_FACE_CELLS:
            s.paper[r, c] = WHITE + B
    for j, row in enumerate(CRONE_NARROW if narrow else CRONE):
        for i, ch in enumerate(row):
            X, Y = X0 + 24 + i, Y0 + 8 + j
            in_red = red and (X // 8, Y // 8) in RED_FACE_CELLS
            if in_red:          # b: PAPER W+ / INK R+ -- pale smooth skin, red features
                on = ch in "eml" or (ch in ".s" and (X + Y) % 2 == 0)
                s.put(X, Y, RED + B) if on else s.clr(X, Y)
            else:
                white = ch in "#hgl" or (ch == "k" and not (X % 2 == 0 and Y % 2 == 1))
                s.put(X, Y, WHITE + B) if white else s.clr(X, Y)



def red_face(s: Scr, X0: int, Y0: int, cx: float, human: bool):
    """S2b: eyes + lips in red. In RED_FACE_CELLS paper = bright white (skin / coif)
    and ink = bright red, so those cells hold only W+ and R+ -- no black: sockets
    become red, the face edge a red dotted line. All other cells are untouched."""
    for (c, r) in RED_FACE_CELLS:
        s.paper[r, c] = WHITE + B
        s.clear_rect(c * 8, r * 8, 8, 8)
    def red(x, y):
        X, Y = X0 + x, Y0 + y
        if (X // 8, Y // 8) in RED_FACE_CELLS:
            s.put(X, Y, RED + B)
    for ex in (int(cx - 3.5), int(cx + 3.5)):               # eye centres x 32 / 39
        if human:   # almond eye 6 px: red lids, red 2-px iris, white of the eye = paper
            for x in range(ex - 1, ex + 3):
                red(x, 17)
                red(x, 19)
            for x in (ex - 2, ex, ex + 1, ex + 3):
                red(x, 18)
        else:       # skull: solid red hollow (the socket glows), white pupil-less
            for y in range(15, 23):
                for x in range(26, 46):
                    if ((x + 0.5 - (ex + 0.5)) / 2.8) ** 2 + ((y + 0.5 - 18.5) / 2.4) ** 2 <= 1:
                        red(x, y)
    if human:
        red(37, 21)                                         # nose shadow
        red(37, 22)
        red(35, 23)
        lips = {25: (34, 35, 37, 38), 26: range(33, 40), 27: range(34, 39), 28: range(35, 38)}
    else:
        for y in (21, 22):                                  # nose slit
            red(35, y)
            red(36, y)
        lips = {25: range(34, 38), 26: (33, 35, 36, 38), 27: range(34, 38)}
    for y, xs in lips.items():
        for x in xs:
            red(x, y)
    if human:
        s.clr(X0 + 36, Y0 + 27)                             # highlight on the lower lip


def nun_hd(s: Scr, X0: int, Y0: int, face: str = "skull"):
    """The Archmage nun drawn at screen resolution (not the 40 px sprite at 2x).

    Inks: the 3x3 wimple block (cols 26-28, rows 11-13) is W+; veil + habit are
    green, BRIGHT on rows 10-15 (hood and shoulders catch the light), dim on rows
    16-20; mist = green dither on row 20; floor reflection = blue on row 21.
    Tone = ordered dither from a fold-phase lighting model (no 2nd ink per cell).
    The figure is centred on the wimple block (x 220), so it spills into col 31.
    """
    global WIMPLE_CELLS, RED_FACE_CELLS
    r0 = Y0 // 8
    WIMPLE_CELLS = box(26, r0 + 1, 3, 3)
    RED_FACE_CELLS = box(26, r0 + 2, 3, 1) | {(27, r0 + 3)}

    def col(x, y):
        if (x // 8, y // 8) in WIMPLE_CELLS:
            return WHITE + B
        return GREEN + B if y // 8 <= r0 + 5 else GREEN

    WD = 72
    cx = 36.0
    m = np.zeros((88, WD), bool)       # silhouette of veil + habit
    hem = 82 + 2 * np.sin(np.arange(WD) * 0.55)
    for y in range(88):
        if y < 16:
            hw = (max(0.0, 15.5 ** 2 - (16 - y) ** 2)) ** 0.5 if y >= 1 else 0
        elif y < 40:
            hw = 15.5 + (y - 16) * 0.55
        else:
            hw = min(31.5, 28.7 + (y - 40) * 0.07)
        for x in range(WD):
            if abs(x + 0.5 - cx) < hw and y < hem[x]:
                m[y, x] = True
    inner = m.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        inner &= np.roll(np.roll(m, dy, 0), dx, 1)
    edge = m & ~inner

    def put(x, y, on=True):
        X, Y = X0 + x, Y0 + y
        if on:
            s.put(X, Y, col(X, Y))
        else:
            s.clr(X, Y)

    in_wim = lambda x, y: 24 <= x < 48 and 8 <= y < 32   # local box of the W+ cells

    # -- veil + habit: outline, fold-shaded dither, highlight lines beside the creases
    folds = [12, 19, 26, 46, 53, 60]
    for y in range(88):
        spread = 1 + max(0, y - 34) / 40
        fx = [cx + (f - cx) * spread + 1.5 * np.sin(y / 9 + f) for f in folds]
        for x in range(WD):
            if not m[y, x] or in_wim(x, y):
                continue
            if edge[y, x]:
                put(x, y)
                continue
            d = min(abs(x + 0.5 - f) for f in fx)
            ridge = max(0.0, 1 - d / 3.5)
            side = 0.5 + 0.5 * (1 - x / WD)                 # torch is far to the left
            depth = 1 - 0.5 * max(0, y - 50) / 38
            lvl = (0.03 + 0.7 * ridge) * side * depth
            if d < 0.8 and y > 20:
                lvl = 0                                     # crease = shadow
            if dith(x, y, lvl):
                put(x, y)
        if y > 22:
            for f in fx:                                    # lit edge of each fold
                hx = int(f + 1.6)
                if 0 <= hx < WD and m[y, hx] and not in_wim(hx, y) and (y // 5) % 4 != 3:
                    put(hx, y)

    # -- scapular: straight front panel from the bib to the hem, darker
    for y in range(32, 84):
        for x in (27, 44):
            put(x, y)
        for x in range(28, 44):
            put(x, y, False)
            if dith(x, y, 0.06 + 0.1 * (x < 36)):
                put(x, y)

    # -- sleeves: wide cuffs meeting in front, hands clasped (y 54..64)
    for y in range(40, 66):
        t = (y - 40) / 25
        for sd in (-1, 1):
            put(int(cx + sd * (26 - 15 * t)), y)
            put(int(cx + sd * (25 - 15 * t)), y)
    for x in range(14, 58):
        if abs(x + 0.5 - cx) > 6:
            put(x, 65)
            put(x, 66, x % 2 == 0)
    for y in range(50, 66):                                 # praying hands, tips up
        hw = min(4.5, 1 + (y - 50) * 0.6)
        for x in range(int(cx - hw), int(cx + hw) + 1):
            put(x, y)
        put(int(cx - hw) - 1, y, False)
        put(int(cx + hw) + 1, y, False)
        if y > 52:
            put(int(cx), y, False)                          # the gap between the palms
    for y in (58, 61):                                      # finger joints
        for x in (int(cx) - 3, int(cx) + 2):
            put(x, y, False)

    # -- rosary: bead loop from the hands, then the cross with a black halo
    for i in range(15):
        a = np.pi * i / 14
        bx, by = cx - 10 * np.cos(a), 66 + 8 * np.sin(a)
        for dy in (0, 1):
            for dx in (0, 1):
                put(int(bx) + dx, int(by) + dy)
    for y in range(74, 88):
        for x in range(30, 43):
            put(x, y, False)
    for y in range(75, 87):
        put(35, y)
        put(36, y)
    for x in range(32, 40):
        put(x, 78)
        put(x, 79)

    if face.startswith("crone"):
        crone_face(s, X0, Y0, red=(face == "crone_red"), narrow=(face == "crone_narrow"))
        if face == "crone_narrow":   # veil's inner edge just outside the W+ block
            for y in range(8, 34):
                put(23, y)
                put(48, y)
            for x in range(24, 48):                        # chamfered corners
                put(x, 7)
    else:
        # -- coif + wimple (W+): rounded hood opening, bib below, folds; crisp black gap
        for y in range(8, 32):
            for x in range(24, 48):
                red = face != "skull"   # S2b: row-12 cells + mouth cell must be all coif
                hood = ((x + 0.5 - cx) / (12.6 if red else 11.5)) ** 2 + ((y + 0.5 - 20) / 12.5) ** 2 <= 1
                bib = y >= 20 and abs(x + 0.5 - cx) < 11.5 - max(0, y - 25) * (1.2 if red else 1.4)
                if hood or bib:
                    put(x, y)
        for x in range(24, 48):
            put(x, 12, False) if ((x + 0.5 - cx) / 11.5) ** 2 + ((12.5 - 20) / 12.5) ** 2 <= 1 else None
        fcx, fcy, frx, fry = cx, 20.0, 7.0, 8.0
        for y in range(10, 31):
            for x in range(26, 47):
                e = ((x + 0.5 - fcx) / frx) ** 2 + ((y + 0.5 - fcy) / fry) ** 2
                if 1.0 < e <= 1.3 and y > 11 and face == "skull":
                    put(x, y, False)                            # crisp face opening in the wimple
                if e <= 1.0:
                    put(x, y, False)
                    gaunt = 0.5 if y < 21 else 0.18            # hollow cheeks / jaw in shadow
                    if face == "red_human":
                        gaunt = 1.0                             # pale, smooth skin
                    if 0.8 < e <= 1.0 and dith(x, y, 0.75) or dith(x, y, gaunt):
                        put(x, y)
        for (ex, ey) in ((cx - 3.5, 18.5), (cx + 3.5, 18.5)) if face == "skull" else ():
            for y in range(14, 24):
                for x in range(28, 46):
                    q = ((x + 0.5 - ex) / 2.8) ** 2 + ((y + 0.5 - ey) / 2.3) ** 2
                    if q <= 1:
                        put(x, y, False)
                    elif q <= 1.9:
                        put(x, y)
            put(int(ex), int(ey))
        if face == "red_human":                                 # black brows (row 11, W+ cells)
            for x in list(range(30, 35)) + list(range(38, 43)):
                put(x, 14 if x in (30, 42) else 13, False)
                put(x, 15 if x in (30, 42) else 14, False)
        if face == "skull":
            for y in (22, 23):
                put(35, y, False)
                put(36, y, False)
            for x in range(33, 39):
                put(x, 26, False)
        for t in range(16):                                     # wimple folds under the chin
            a = np.pi * (0.2 + 0.6 * t / 15)
            for r in (10.5, 13.5):
                put(int(cx + r * np.cos(a)), int(20 + r * np.sin(a)), False)
    if face in ("red_skull", "red_human"):
        red_face(s, X0, Y0, cx, human=(face == "red_human"))

    # -- mist (last nun row, green wisps) and floor reflection (landing row, blue)
    for y in range(Y0 + 80, Y0 + 88):
        for x in range(160, 256):
            lx = x - X0
            inside = 0 <= lx < WD and m[y - Y0, lx]
            lvl = 0.10 + 0.14 * (np.sin(x / 7 + y * 0.9) + np.sin(x / 13 - y))
            if not inside and dith(x, y, lvl):
                s.put(x, y, GREEN)
    for y in range(Y0 + 90, Y0 + 96):
        for x in range(X0, min(W, X0 + WD)):
            src = 87 - (y - Y0 - 90) * 2 - 6
            if m[src, x - X0] and dith(x, y, 0.22 - 0.03 * (y - Y0 - 90)):
                s.put(x, y, BLUE)


# ================================================================ S2 THE DESCENT
def s2(hd: bool = True, face: str = "skull") -> Scr:
    """Cross-section staircase: heroes descend toward the Archmage in the dark."""
    s = Scr()
    ice = by_row([WHITE + B, CYAN + B, CYAN, BLUE + B, WHITE + B, CYAN + B, CYAN, BLUE + B], 0)
    l1, l2 = script_logo("TOME OF"), script_logo("THE DEAD")
    s.bits(l1, 8, 0, ice)
    s.bits(l2, W - 8 - l2.shape[1], 32, ice)
    assert W - 8 - l2.shape[1] >= 40, "line 2 must clear the torch cols 2-3"

    # torch on the back wall
    tc, trow = 2, 7
    place_torch(s, tc, trow)
    lf = light(tc + 1, trow + 0.5, [(1.8, YEL), (2.6, RED + B), (3.1, RED)])
    mage_cells, war_cells = box(6, 8, 3, 5), box(14, 12, 3, 5)
    nun_cells = box(20, 8, 12, 11)
    reserved = (mage_cells | war_cells | nun_cells | box(0, 0, 32, 4) | box(5, 4, 27, 4)
                | box(tc, trow, 2, 4))
    back = {(c, r) for c in range(0, 22) for r in range(4, 20) if r < 10 + c // 2} - reserved
    bricks(s, sorted(back), lambda c, r: lf(c, r), seed=2)

    # staircase: step k = cols 2k..2k+1, tread at row 10+k; mass below to row 19
    # (rows 20-21 = captions, rows 22-23 blank: the ROM clears them for the next header)
    nsteps, GND = 10, 160
    def step_ink(k):
        return [WHITE + B, WHITE, YEL, YEL, RED + B, RED, MAG, MAG, BLUE + B, BLUE, BLUE][k]
    for k in range(nsteps):
        ink = step_ink(k)
        x0, ty = 16 * k, 80 + 8 * k
        for x in range(x0, x0 + 16):
            s.put(x, ty, ink)                       # tread edge
            if k < 6 or x % 2 == 0:
                s.put(x, ty + 1, ink)
        for y in range(ty, GND):                    # riser line at the step's left
            if k > 0 and y < ty + 8:
                s.put(x0, y, ink)
        # mass texture: bricks fading with depth (dither density by k)
        dens = max(0.0, 0.55 - 0.05 * k)
        for y in range(ty + 2, GND):
            for x in range(x0, x0 + 16):
                yy = y - ty
                mortar = (yy % 6 == 5) or ((x + (8 if (yy // 6) & 1 else 0)) % 16 == 0)
                fade = (y - ty) / (GND - ty)
                if mortar and dith(x, y, max(0.0, 1.0 - fade * 1.6) * (1 - k / nsteps) + dens * 0.0):
                    s.put(x, y, ink)
    # landing at the bottom (cols 20-31, tread row 19)
    for x in range(160, W):
        s.put(x, 152, BLUE)
        if x % 2 == 0:
            s.put(x, 153, BLUE)
    for y in range(154, GND):
        for x in range(160, W):
            yy = y - 152
            if ((yy % 6 == 5) or ((x + (8 if (yy // 6) & 1 else 0)) % 16 == 0)) and dith(x, y, 0.35):
                s.put(x, y, BLUE)

    # heroes on steps 3 (Mage) and 7 (Warrior), the Archmage nun 2x on the landing
    s.grid(MAGE, 6 * 8, 8 * 8, CYAN + B)
    s.grid(KNIGHT, 14 * 8, 12 * 8, WHITE + B)
    if hd:
        nun_hd(s, 23 * 8, 8 * 8, face)
    else:
        s.grid(NUN, 23 * 8, 9 * 8, GREEN, scale=2, mirror=False)
    # small skull on step 9
    s.bits(SKULL_BM, 18 * 8, 17 * 8, WHITE)
    # text
    s.text6(SUB, centre(len(SUB) * 6), 160, CYAN + B)
    s.text6(CREDIT, centre(len(CREDIT) * 6), 168, WHITE)
    assert not (s.px[176:] != NONE).any(), "rows 22-23 must stay blank"
    s.notes = [
        "Paper black; one ink per cell.",
        "Title: game title16 script 2x, TOME OF (rows 0-3, left) / THE DEAD (rows 4-7, right); ink per row W+ C+ C B+.",
        "Each 2-cell step owns its own ink, so step boundaries are cell boundaries: depth gradient",
        "W+ W Y Y R+ R M M B+ B B down the stair (light fades into the dark); brick mortar is dithered",
        "away with depth inside each step's ink. Heroes stand on treads in cells left empty above the",
        "steps (Mage C+ step 3, Warrior W+ step 7). Torch reuses the game torch.",
        "Archmage (native 64x88, cols 23-31 rows 8-18, nothing else in those cells): wimple/coif/face",
        "= 3x3 W+ cells (cols 26-28 rows 9-11) cut on cell edges; veil + habit G+ rows 8-13, G rows",
        "14-18; tone/folds by ordered dither; mist = G dither row 18; reflection = B dither on the",
        "landing row 19. Captions rows 20-21; rows 22-23 BLANK (ROM clears them for the next header).",
    ]
    return s


# ================================================================ S3 THE CRYPT
def s3() -> Scr:
    """Framed crypt portrait: skull crest, gothic title, 2x heroes, credits."""
    s = Scr()
    # border: 1-cell frame, rune/chain tile in red
    tile = ["#..##..#", ".#....#.", "..#..#..", "#..##..#", "#..##..#", "..#..#..", ".#....#.", "#..##..#"]
    corner = ["########", "#......#", "#.####.#", "#.#..#.#", "#.#..#.#", "#.####.#", "#......#", "########"]
    tb = np.array([[ch == "#" for ch in r] for r in tile])
    cb = np.array([[ch == "#" for ch in r] for r in corner])
    for c in range(32):
        for r in (0, 23):
            s.bits(cb if c in (0, 31) else tb, c * 8, r * 8, RED)
    for r in range(1, 23):
        for c in (0, 31):
            s.bits(tb.T, c * 8, r * 8, RED)

    # skull crest 3x (48x48) cols 13-18 rows 1-6, crossed bones behind it
    sk = SKULL_BM.repeat(3, 0).repeat(3, 1)
    bones = np.zeros((48, 112), bool)
    for t in range(0, 100):
        for w in range(-2, 3):
            y1 = int(4 + t * 40 / 100) + w
            bones[min(47, max(0, y1)), 6 + t] = True
            y2 = int(44 - t * 40 / 100) + w
            bones[min(47, max(0, y2)), 6 + t] = True
    for (bx, by) in ((6, 4), (106, 4), (6, 44), (106, 44)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if dx * dx + dy * dy <= 12 and 0 <= by + dy < 48 and 0 <= bx + dx < 112:
                    bones[by + dy, bx + dx] = True
    s.bits(bones, 72, 8, WHITE)
    s.clear_rect(104, 8, 48, 48)
    s.bits(sk, 104, 8, WHITE + B, halo=True)

    # torches in the top corners
    place_torch(s, 3, 1)
    place_torch(s, 27, 1)

    # gothic title rows 7-12, two lines (hollow letters + stripes), ice gradient per line
    ice = by_row([WHITE + B, CYAN + B, BLUE + B, WHITE + B, CYAN + B, BLUE + B], 7)
    for i, line in enumerate(("TOME OF", "THE DEAD")):
        lg = logo5(line, 4, 3, 4, chamfer=False)
        lg = outline_dither(lg, 0.0) | chrome(lg, [2, 5, 8, 11, 14, 17, 20])
        s.bits(lg, centre(lg.shape[1]), 7 * 8 + 1 + 24 * i, ice)

    # heroes 2x on both sides, rows 12-21 (80 px), facing the centre
    s.grid(KNIGHT, 2 * 8, 13 * 8, WHITE + B, scale=2)
    s.grid(MAGE_CAST, 23 * 8, 13 * 8, CYAN + B, scale=2, mirror=True)

    # centre text block
    l1, l2 = "ROGUELIKE", "ZX SPECTRUM"
    s.text16(l1, centre(len(l1) * 8), 14 * 8, YEL + B)
    s.text16(l2, centre(len(l2) * 8), 16 * 8, WHITE + B)
    s.text16("128K", centre(32), 18 * 8, RED + B)
    s.text6(CREDIT, centre(len(CREDIT) * 6), 20 * 8, CYAN)
    s.text6("LOADING", centre(42), 21 * 8 + 1, MAG + B)
    s.notes = [
        "Paper black; one ink per cell. Border = 1-cell red rune frame (owns rows 0/23, cols 0/31).",
        "Skull crest W+ (3x of the 16x16 skull, black halo) over dim-white crossed bones: the bones",
        "only enter cells beside the skull block, so W and W+ never share a cell.",
        "Title rows 7-12: TOME OF / THE DEAD, hollow block letters + stripes, ink per row W+ C+ B+ per line.",
        "Heroes at 2x (Warrior idle W+, Mage cast C+) own cols 2-7 / 23-30, rows 13-22; the centre",
        "text block (8x16 menu font, Y+ / W+ / R+, 6x8 credit C) sits in cols 11-21 between them.",
    ]
    return s


# ---------------------------------------------------------------- board
def svg_paths(img) -> str:
    """Screen as crisp SVG: one path of 1-px runs per non-black colour."""
    out = []
    cols = {}
    hh, ww = img.shape[:2]
    for y in range(hh):
        x = 0
        while x < ww:
            c = tuple(int(v) for v in img[y, x])
            x1 = x
            while x1 < ww and tuple(int(v) for v in img[y, x1]) == c:
                x1 += 1
            if c != (0, 0, 0):
                cols.setdefault(c, []).append(f"M{x} {y}h{x1 - x}v1h-{x1 - x}z")
            x = x1
    for c, runs in cols.items():
        out.append(f'<path d="{"".join(runs)}" fill="#{c[0]:02X}{c[1]:02X}{c[2]:02X}"></path>')
    return "".join(out)


GRID_PATH = ('<path d="' + "".join(f"M{c * 8} 0V192" for c in range(1, 32)) +
             "".join(f"M0 {r * 8}H256" for r in range(1, 24)) +
             '" stroke="#FF00FF" stroke-opacity="0.45" stroke-width="0.25" fill="none"></path>')


def board(items, heading, intro, grid_for=None) -> str:
    hd = "font-family: 'Press Start 2P', monospace; font-size: 13px; color: #e8e6f0; margin: 24px 0 12px;"
    tx = "font-size: 12px; color: #e8e6f0; margin: 6px 0;"
    parts = [f'<div style="{hd}">{heading}</div>', f'<div style="{tx}">{intro}</div>']
    for name, title, img, notes, scale in items:
        pw, ph = 256 * scale, 192 * scale
        parts.append(f'<div style="{hd}">{name} — {title}</div>')
        parts.append('<div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start;">')
        for grid in ((False, True) if grid_for is None or name in grid_for else (False,)):
            parts.append('<div style="display: flex; flex-direction: column; gap: 6px;">'
                         '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
                         f'<svg width="{pw}" height="{ph}" viewBox="0 0 256 192" shape-rendering="crispEdges" '
                         'style="display: block;"><rect width="256" height="192" fill="#000000"></rect>'
                         + svg_paths(img) + (GRID_PATH if grid else "") + "</svg></div>"
                         f'<div style="{tx}">{name} · 256×192{" · ATTR GRID" if grid else ""}</div></div>')
        parts.append("</div>")
        parts.append(f'<div style="{tx}">' + "<br>".join(notes) + "</div>")
    return "\n".join(parts) + "\n"


def attr_txt(name, attr, notes) -> str:
    names = "KBRMGCYW"
    lines = [f"# {name}: attribute plan, 32x24 cells (hex attr; key: ink letter, '+' = BRIGHT, paper black)",
             *[f"# {n}" for n in notes], "#"]
    for r in range(24):
        lines.append(" ".join(f"{attr[r, c]:02X}" for c in range(32)) + "   " +
                     "".join((names[attr[r, c] & 7] + ("+" if attr[r, c] & 64 else " ")) for c in range(32)))
    return "\n".join(lines) + "\n"


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    comps = [("S1", "THE GATE", s1), ("S2", "THE DESCENT", s2), ("S3", "THE CRYPT", s3)]
    items, imgs = [], []
    for tag, title, fn in comps:
        s = fn()
        bm, attr = s.resolve(tag)
        scr = to_scr(bm, attr)
        assert len(scr) == 6912
        bm2, attr2 = decode_scr(scr)
        assert (bm2 == bm).all() and (attr2 == attr).all(), f"{tag}: .scr round-trip mismatch"
        base = os.path.join(OUT, f"loading_{tag.lower()}")
        open(base + ".scr", "wb").write(scr)
        img = render(bm2, attr2)  # previews are decoded from the .scr bytes
        png(img, base + ".png")
        png(img, base + "_grid.png", grid=True)
        open(base + "_attr.txt", "w").write(attr_txt(tag, attr2, s.notes))
        items.append((tag, title, img, s.notes, 2))
        imgs.append(img)
        inks = sorted({int(a) for a in attr2.flat})
        print(f"{tag} {title}: ok, {len(inks)} distinct attrs, {int(bm2.sum())} ink px -> {base}.scr")
    sheet = np.full((H, W * 3 + 16, 3), 40, np.uint8)
    for i, im in enumerate(imgs):
        sheet[:, i * (W + 8):i * (W + 8) + W] = im
    Image.fromarray(sheet).resize((sheet.shape[1] * 2, H * 2), Image.NEAREST).save(
        os.path.join(OUT, "loading_options.png"))
    s2_final = next(it for it in items if it[0] == "S2")
    pb, pa = s2(hd=False).resolve("S2-prev")              # superseded 2x-sprite nun (reference)
    png(render(pb, pa), os.path.join(OUT, "loading_s2_prev.png"))
    # S2b (user 2026-10-30): red eyes + red lips via PAPER W+ / INK R+ face cells
    b_items = []
    for tag, face, title in (("S2b_skull", "red_skull", "red eyes + lips, skull face"),
                             ("S2b_human", "red_human", "red eyes + lips, pale human face")):
        sb = s2(face=face)
        sb.notes = s2_final[3] + [
            "S2b: cells (26,10) (27,10) (28,10) (27,11) = PAPER W+ / INK R+ (attr $7A): skin and coif",
            "are paper, eyes / lips / face edge are red ink; no black in those 4 cells (sockets turn red).",
            "Every neighbour keeps W+ on black, so the face edge changes from red dots to black at the",
            "cell edge. 4 cells only; the 2-colour check is unchanged."]
        bm, attr = sb.resolve(tag)
        scr = to_scr(bm, attr)
        bm2, attr2 = decode_scr(scr)
        assert (bm2 == bm).all() and (attr2 == attr).all()
        base = os.path.join(OUT, f"loading_{tag.lower()}")
        open(base + ".scr", "wb").write(scr)
        img = render(bm2, attr2)
        png(img, base + ".png")
        png(img, base + "_grid.png", grid=True)
        open(base + "_attr.txt", "w").write(attr_txt(tag, attr2, sb.notes))
        b_items.append((tag.replace("_", " ").upper(), title, img, sb.notes[-4:], 3))
        print(f"{tag}: ok -> {base}.scr")
    # S2c (user 2026-10-30): elongated gaunt crone face; a = W+ on black, b = red trick
    c_items = []
    for tag, face, title, extra in (
            ("S2c_a", "crone", "crone face, black sockets (W+ on black)",
             ["S2c a: same attributes as S2 final; the 3x3 W+ head block is a designed 24x24",
              "crone face (CRONE_HALF, mirrored): long oval, sunken sockets + glint, thin nose,",
              "hollow cheeks, stitched mouth, long bony chin; the bib tapers under the chin."]),
            ("S2c_b", "crone_red", "crone face, red sockets + lips",
             ["S2c b: crone face + cells (26,10) (27,10) (28,10) (27,11) = PAPER W+ / INK R+ ($7A):",
              "sockets, face edge, hollows, mouth seam and lips are red there; the eye glint is",
              "paper white; rows 9/11 side cells stay W+ on black (edge turns black there)."])):
        sc = s2(face=face)
        sc.notes = s2_final[3] + extra
        bm, attr = sc.resolve(tag)
        scr = to_scr(bm, attr)
        bm2, attr2 = decode_scr(scr)
        assert (bm2 == bm).all() and (attr2 == attr).all()
        base = os.path.join(OUT, f"loading_{tag.lower()}")
        open(base + ".scr", "wb").write(scr)
        img = render(bm2, attr2)
        png(img, base + ".png")
        png(img, base + "_grid.png", grid=True)
        open(base + "_attr.txt", "w").write(attr_txt(tag, attr2, sc.notes))
        c_items.append((tag.replace("_", " ").upper(), title, img, extra, 3))
        print(f"{tag}: ok -> {base}.scr")
    sd = s2(face="crone_narrow")
    sd.notes = s2_final[3] + [
        "S2d: crone face with a TIGHT coif (3 px round the face, narrow_coif()); the rest of the",
        "3x3 W+ block is black, so a black gap separates coif and veil; the veil's inner edge is a",
        "green line just outside the block (cols 25 / 29, row 8). No red variant: the gap would fall",
        "inside the PAPER-white face cells, which cannot show black."]
    bm, attr = sd.resolve("S2d")
    scr = to_scr(bm, attr)
    bm2, attr2 = decode_scr(scr)
    assert (bm2 == bm).all() and (attr2 == attr).all()
    base = os.path.join(OUT, "loading_s2d")
    open(base + ".scr", "wb").write(scr)
    img = render(bm2, attr2)
    png(img, base + ".png")
    png(img, base + "_grid.png", grid=True)
    open(base + "_attr.txt", "w").write(attr_txt("S2d", attr2, sd.notes))
    print(f"S2d: ok -> {base}.scr")
    trio = ([("S2 FINAL", "round skull face", s2_final[2], s2_final[3][-4:], 3)] + c_items +
            [("S2D", "crone face, tight coif (black sockets)", img, sd.notes[-4:], 3)])
    html = board(
        trio,
        "F3o ART14 — LOADING SCREEN: S2 FINAL / S2c a / S2c b / S2d TIGHT COIF (SCREEN$ 6,912 B)",
        "S2c redraws the Archmage head as a long gaunt crone (designed pixel grid, not a circle). "
        "a keeps S2 final's attributes (white on black, black sockets); b adds red sockets + lips "
        "with the 4-cell PAPER white / INK red trick. Every cell is 2 colours (generator-checked). "
        "S2d = S2c a with a tight coif and a black gap to the veil. Rows 22-23 are blank in all four "
        "(the ROM clears them while the next header loads). "
        "Files: assets/gfx/loading/loading_s2.scr, loading_s2c_a.scr, loading_s2c_b.scr, loading_s2d.scr.",
        grid_for={"S2 FINAL", "S2C A", "S2C B", "S2D"})
    hd = "font-family: 'Press Start 2P', monospace; font-size: 13px; color: #e8e6f0; margin: 24px 0 12px;"
    tx = "font-size: 12px; color: #e8e6f0; margin: 6px 0;"
    crops = [f'<div style="{hd}">HEAD CLOSE-UP 6× (cols 25-29, rows 8-12, attr grid)</div>',
             '<div style="display: flex; gap: 16px; flex-wrap: wrap;">']
    for name, _, img, _, _ in trio:
        cr = img[64:104, 200:240]
        gp = ('<path d="' + "".join(f"M{k} 0V40" for k in (8, 16, 24, 32)) +
              "".join(f"M0 {k}H40" for k in (8, 16, 24, 32)) +
              '" stroke="#FF00FF" stroke-opacity="0.45" stroke-width="0.12" fill="none"></path>')
        crops.append('<div style="display: flex; flex-direction: column; gap: 6px;">'
                     '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
                     '<svg width="240" height="240" viewBox="0 0 40 40" shape-rendering="crispEdges" '
                     'style="display: block;"><rect width="40" height="40" fill="#000000"></rect>'
                     + svg_paths(cr) + gp + f'</svg></div><div style="{tx}">{name} · HEAD 40×40</div></div>')
    crops.append("</div>")
    html += "\n".join(crops) + "\n"
    open(os.path.join(OUT, "loading_options.svg.html"), "w").write(html)
    print(f"board: {len(html)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
