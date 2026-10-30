#!/usr/bin/env python3
"""gen_art15_spider_climb.py — ART15 (2026-10-30): a DEDICATED Spider climb cycle.

Today the Spider / Black Widow climb on their side-view rest pose (seq_img.asm
ksm_sp: KS_CLIMB = sp_idle, KS_CLIMBREST = spider_walk1). User Option A: a
2-frame climb cycle spider_climb1 / spider_climb2, the Spider seen from behind
/ above (dorsal view, head UP) on the ladder, legs gripping rails and rungs.

Geometry (prototype §3.4, tiles_common.asm T_LAD_L/M/R): the ladder is 3 cells
(24 px) wide, rails at x 1-2 and 21-22, rungs every 4 px; a climber's px is
col*8 for the whole climb (snap invariant) and the climb tween is 4 px per
tick, so the rungs sit at sprite rows 1, 5, 9, 13 on EVERY climb tick. The
Spider body is 4 cells (KT_BW 4, FRM bwpx 32 -> the frame must be 32 wide),
standing at col .. col+3 with the ladder under cols 0..2: the art is drawn in
x 0..23 (centred on the ladder, x 11.5) and cols 24..31 stay transparent.
Both frames are SYM (one facing: a dorsal view has no facing), STA (drawn
cell-aligned), so each costs 16 x 2 x 4 = 128 B of pool on a level that
generates the Spider unit, and CLIMB2 = mirror(CLIMB1) about the ladder centre
(tetrapod gait: L1 R2 L3 R4 reach while L2 R1 L4 R3 grip, then swap).
CLIMBREST = CLIMB1 (data.asm CLIMBREST macro).

Writes assets/gfx/sprites/grid/spider_climb{1,2}.grid + assets/gfx/sprites/
spider_climb{1,2}.asm (packed by gfx_convert.py --layout native, NOT in
index.asm / frames.asm: not wired), assets/gfx/concept/art15_spider_climb/:
board.svg.html (F3q style: old vs new, both facings), anim_climb.gif,
art15.png, costs.txt. Validation: clash + round-trip (exit 1 on failure).
Usage: python3 tools/gen_art15_spider_climb.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G  # noqa: E402
import gen_art2_options as A  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402
import zx0_sources as ZS  # noqa: E402
import gfx_convert  # noqa: E402

REPO = S.REPO
SPR = os.path.join(REPO, "assets/gfx/sprites")
GRID_DIR = os.path.join(SPR, "grid")
OUT = os.path.join(REPO, "assets/gfx/concept/art15_spider_climb")
INK_SP, INK_BW = "#00D7D7", "#D70000"      # Spider $05; Black Widow tier ink $02 (kind_tab)
W, H, LW = 32, 16, 24                      # frame box; ladder width (art centred on it)

poly, ellipse, put = G.poly, G.ellipse, G.put


# ---------------------------------------------------------------------------
# the art: left legs in pose P, right legs in pose Q (mirrored), body centred
# ---------------------------------------------------------------------------
# Leg polylines on the LEFT half (hip on the cephalothorax edge -> knee -> tip on
# a rail / rung). REACH = the leg swung up to the next rung (knee high and wide),
# GRIP = the leg holding its rung, pulled in under the body (tip 4 px lower).
LEG_REACH = [
    [(9, 3), (6, 0), (3, 0), (2, 1)],      # L1 front: arched up over the top rung
    [(9, 4), (5, 2), (3, 3), (2, 5)],      # L2: knee high
    [(9, 5), (5, 6), (3, 7), (2, 9)],      # L3: knee level
    [(9, 6), (6, 9), (3, 11), (2, 13)],    # L4 rear
]
LEG_GRIP = [
    [(9, 3), (5, 3), (2, 1)],              # L1 front: knee out, pulling down
    [(9, 4), (5, 6), (2, 5)],              # L2: knee below the tip (V)
    [(9, 5), (5, 10), (2, 9)],             # L3: knee low
    [(9, 6), (6, 14), (2, 13)],            # L4 rear: knee at the bottom
]


def half_legs(pose_reach):
    """pose_reach[i] True -> leg i reaches, else grips; returns a 16x24 mask."""
    m = np.zeros((H, LW), bool)
    for i, reach in enumerate(pose_reach):
        m |= poly(m.shape, (LEG_REACH if reach else LEG_GRIP)[i])
    return m


def body() -> np.ndarray:
    sh = (H, LW)
    b = np.zeros(sh, bool)
    put(b, ellipse(sh, 11.5, 4.4, 2.7, 2.5))          # cephalothorax (head up)
    put(b, ellipse(sh, 11.5, 11.4, 4.3, 4.2))         # abdomen
    b[1:3, 10] = True                                  # palps / fangs
    b[1:3, 13] = True
    b[7, 9:15] = False                                 # waist gap
    b[7, 11:13] = True                                 # pedicel
    b[10, 9:15] = False                                # abdomen bands (as the walk
    b[13, 10:14] = False                               # frames' band)
    return b


def climb1() -> np.ndarray:
    p = (True, False, True, False)                     # L1 L3 reach, L2 L4 grip
    q = tuple(not x for x in p)                        # right side opposite
    left = half_legs(p)
    right = half_legs(q)[:, ::-1]                      # mirror about x 11.5
    m = left | right
    b = body()
    pass
    m |= b
    out = np.zeros((H, W), bool)
    out[:, :LW] = m
    return out


def climb2() -> np.ndarray:
    c = climb1()
    out = np.zeros_like(c)
    out[:, :LW] = c[:, :LW][:, ::-1]                   # mirror about the ladder centre
    return out


def ladder_bg(h, w, x0, phase=0):
    """RGB backdrop with the real T_LAD_L/M/R ladder (ink $02) at x0..x0+23."""
    a = np.full((h, w, 3), (0, 0, 0), np.uint8)
    red = S.spec_rgb(2, False)
    a[:, x0 + 1:x0 + 3] = red
    a[:, x0 + 21:x0 + 23] = red
    for ry in range((1 + phase) % 4, h, 4):
        a[ry, x0 + 1:x0 + 23] = red
    return a


def blit(a, bm, x, y, ink_hex):
    colour, bright = S.INK_MAP[ink_hex]
    solid = S.make_mask(bm, outline=True)
    hh, ww = bm.shape
    sub = a[y:y + hh, x:x + ww]
    sub[solid] = (0, 0, 0)
    sub[bm] = S.spec_rgb(colour, bright)
    # attribute clash as the engine shows it: every 8x8 screen cell the sprite
    # touches takes the sprite's INK (ladder pixels there turn the sprite colour)
    ink = np.array(S.spec_rgb(colour, bright), np.uint8)
    for cy in range(y // 8, (y + hh - 1) // 8 + 1):
        for cx in range(x // 8, (x + ww - 1) // 8 + 1):
            ys, xs = slice(cy * 8, cy * 8 + 8), slice(cx * 8, cx * 8 + 8)
            loc = np.zeros(a.shape[:2], bool)
            loc[y:y + hh, x:x + ww] = solid
            if loc[ys, xs].any():
                cell = a[ys, xs]
                cell[cell.any(axis=2)] = ink



# ---------------------------------------------------------------------------
# strips: the Spider on the real ladder, 4 px up per tick, frame per tick
# ---------------------------------------------------------------------------
VIEW_W, VIEW_H, TICKS = 48, 40, 8            # ladder at x 8..31 (cell-aligned), body 8..39


def strip_ticks(frames, facing, ink):
    """[RGB arrays] one per tick: climbing up 4 px per tick from y 24."""
    out = []
    for t in range(TICKS):
        y = 24 - (4 * t) % 24
        a = ladder_bg(VIEW_H, VIEW_W, 8, 0)
        bm = frames[t % len(frames)]
        if facing < 0:
            bm = bm[:, ::-1]                    # the engine mirrors non-SYM frames in the box
        blit(a, bm, 8, y, ink)
        out.append(a)
    return out


def rgb_svg(a, scale=3):
    """Multi-colour pixel svg (review strips only, not an importable artboard)."""
    h, w, _ = a.shape
    parts = [f'<svg width="{w * scale}" height="{h * scale}" viewBox="0 0 {w} {h}" '
             'shape-rendering="crispEdges" style="display: block;">',
             f'<rect width="{w}" height="{h}" fill="#000000"></rect>']
    cols = {}
    for y in range(h):
        x = 0
        while x < w:
            c = tuple(int(v) for v in a[y, x])
            x1 = x
            while x1 < w and tuple(int(v) for v in a[y, x1]) == c:
                x1 += 1
            if c != (0, 0, 0):
                cols.setdefault(c, []).append(f"M{x} {y}h{x1 - x}v1h-{x1 - x}z")
            x = x1
    for c, d in cols.items():
        parts.append(f'<path d="{"".join(d)}" fill="#{c[0]:02X}{c[1]:02X}{c[2]:02X}"></path>')
    return "".join(parts) + "</svg>"


def gif(path, rows, labels, scale=4, ms=200):
    imgs = []
    for t in range(TICKS):
        a = np.hstack([np.pad(r[t], ((0, 0), (2, 2), (0, 0)), constant_values=24) for r in rows])
        im = Image.fromarray(a).resize((a.shape[1] * scale, a.shape[0] * scale), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for i, lab in enumerate(labels):
            d.text((i * (VIEW_W + 4) * scale + 6, 2), lab, fill=(255, 255, 120))
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0)


HEAD = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; color: #e8e6f0; '
        'margin: 24px 0 12px;">{}</div>')
SUB = '<div style="font-size: 12px; color: #e8e6f0; margin: 12px 0 6px;">{}</div>'
ROW = '<div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end;">\n{}\n</div>'
CELL = ('<div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start;">\n'
        '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">{}</div>\n'
        '<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{}</div>\n</div>')


def strip_cell(ticks, cap):
    return CELL.format('<div style="display: flex; gap: 4px;">' + "".join(rgb_svg(t) for t in ticks)
                       + "</div>", cap)


def write_asm(name, bm, solid, ink, cap):
    colour, bright = S.INK_MAP[ink]
    rel = os.path.relpath(os.path.join(GRID_DIR, name + ".grid"), REPO)
    with open(os.path.join(REPO, rel), "w") as f:
        f.write(A.grid_text(name, bm, solid, cap, ink,
                            "ART15 dorsal climb, art in x 0..23 (ladder), cols 24..31 empty; SYM STA")
                .replace("CONCEPT (tools/gen_art2_options.py); not engine data.",
                         "ART15 (tools/gen_art15_spider_climb.py); regenerate, never hand-edit.")
                .replace("# character: SPIDER", "# character: SPIDER"))
    out = os.path.join("assets/gfx/sprites", name + ".asm")
    argv = ["--mode", "sprite", "--layout", "native", "--in", rel, "--name", name, "--out", out,
            "--ink", gfx_convert.COL_NAME[colour], "--paper", "black", "--band-paper", "black",
            "--anchor-x", "0", "--anchor-y", "0", "--src-path", "--date", "2026-10-30",
            "--note", "ART15 Spider / Black Widow climb (dorsal view, head up); generated by "
                      "tools/gen_art15_spider_climb.py",
            "--note", f"artboard: SPIDER / {cap} (32x16), ink {ink}; Black Widow = same frame, ink $02",
            "--note", "class: STATIONARY|SYM (drawn cell-aligned on the ladder, one facing)",
            "--note", "NOT in sprites/index.asm / frames.asm yet (not wired)"]
    S._quiet(S.run_gfx, argv)
    rows, _attr = S.decode_asm(os.path.join(REPO, out))
    fg, sol = gfx_convert.unpack_sprite_mask(rows, W, "native")
    if not (np.array_equal(fg, bm) and np.array_equal(sol, solid)):
        raise SystemExit(f"{name}: round-trip mismatch")
    return bytes(b for r in rows for b in r)


def pool_sta_sym(h=H, cols=W // 8):
    return h * 2 * cols                       # defs.asm FRM: STA, ax 0, aligned, SYM = one facing


def main() -> int:
    os.chdir(REPO)
    os.makedirs(OUT, exist_ok=True)
    c1, c2 = climb1(), climb2()
    assert c1[:, LW:].sum() == 0 and c2[:, LW:].sum() == 0
    new = {}
    for name, bm, cap in (("spider_climb1", c1, "CLIMB 1"), ("spider_climb2", c2, "CLIMB 2")):
        new[name] = (bm, write_asm(name, bm, S.make_mask(bm, outline=True), INK_SP, cap))
    # pool + SRC6 (ZX0, the zx0_sources.py min-packed partition of the Spider's frames)
    game = dict(zp.game_frames())
    old = [(n, game[n]) for n in ("spider_walk1", "spider_walk2", "spider_bite")]
    with tempfile.TemporaryDirectory() as td:
        def best(frames):
            parts = ZS.partition(frames, td)
            return sum(len(ZS.pack(b"".join(d for _, d in frames[i:i + k]), td)) for i, k in parts), parts
        p0, _ = best(old)
        pa, parts_a = best(old + [(n, new[n][1]) for n in ("spider_climb1", "spider_climb2")])
        pb, parts_b = best(old + [("spider_climb1", new["spider_climb1"][1])])
    pool = pool_sta_sym()
    L = ["# ART15 Spider climb costs (tools/gen_art15_spider_climb.py)",
         "# pool = src/defs.asm FRM POOLACC: STA, ax 0, w 32 = bwpx 32 -> 4 cols, no spill col; SYM = one facing",
         "# Same bytes for Warrior and Mage (monster unit); levels generating the Spider unit (K_SPIDER /",
         "# K_BLACK_WIDOW tier, pool6.asm GU KFID_SPIDER): D2, D4, D5.",
         "",
         f"spider_climb1  STA|SYM  32x16  pool {pool} B  raw {len(new['spider_climb1'][1])} B",
         f"spider_climb2  STA|SYM  32x16  pool {pool} B  raw {len(new['spider_climb2'][1])} B",
         "",
         f"OPTION A (chosen): 2 fids, pool +{2 * pool} B on D2/D4/D5 (both heroes), 0 elsewhere;",
         f"   SRC6 Spider kind packed {p0} -> {pa} B (+{pa - p0}); blocks {parts_a} (start, count)",
         f"   seq: sp_climb CLIMBCYC climb1, climb2 (DB 2, c1,1, c2,1, $FF); KS_CLIMBREST = climb1",
         f"OPTION B: 1 fid (climb1 static, also the rest), pool +{pool} B, SRC6 +{pb - p0} B; blocks {parts_b}",
         "",
         "Spare fids today 6 of 144; Archmage nun takes 4 -> A leaves 0, B leaves 1.",
         "Attribute: one ink (Spider $05 / Black Widow $02) on black paper per cell, the climb box",
         "is the Spider's 4x2 cells as today; art within the ladder's 3 cells (x 0..23)."]
    with open(os.path.join(OUT, "costs.txt"), "w") as f:
        f.write("\n".join(L) + "\n")
    # strips
    idle = [game_bm("spider_walk1")]
    sets = []
    for lab, ink in (("SPIDER $05", INK_SP), ("BLACK WIDOW $02", INK_BW)):
        for fc, fl in ((1, "R"), (-1, "L")):
            sets.append((f"OLD {fl} {lab}", strip_ticks(idle, fc, ink)))
            sets.append((f"NEW {fl} {lab}", strip_ticks([c1, c2], 1, ink)))  # SYM: same both facings
    gif(os.path.join(OUT, "anim_climb_spider.gif"), [r for _, r in sets[:4]],
        ["OLD R", "NEW R", "OLD L", "NEW L"])
    gif(os.path.join(OUT, "anim_climb_widow.gif"), [r for _, r in sets[4:]],
        ["OLD R", "NEW R", "OLD L", "NEW L"])
    bd = [HEAD.format("F3q ART15 — SPIDER CLIMB (OPTION A: 2-FRAME CYCLE)"),
          SUB.format("Dorsal view, head up, on the 3-cell ladder (rails x 1-2 / 21-22, rungs every 4 px "
                     "= sprite rows 1, 5, 9, 13 on every tick). Tetrapod gait: CLIMB1 L1 L3 R2 R4 "
                     "reach / L2 L4 R1 R3 grip, CLIMB2 = mirror. SYM (no facing), STA cell-aligned, "
                     f"{pool} B pool each, 2 fids, SRC6 +{pa - p0} B. Rest on rung = CLIMB1. Not wired."),
          ROW.format("\n".join([S.svg_artboard_html(c1, INK_SP, "CLIMB 1"),
                                S.svg_artboard_html(c2, INK_SP, "CLIMB 2"),
                                S.svg_artboard_html(c1, INK_BW, "CLIMB 1 WIDOW"),
                                S.svg_artboard_html(c2, INK_BW, "CLIMB 2 WIDOW"),
                                S.svg_artboard_html(idle[0], INK_SP, "TODAY WALK 1 AS CLIMB")]))]
    for lab in ("SPIDER $05", "BLACK WIDOW $02"):
        bd.append(HEAD.format(f"F3q STRIPS {lab} (8 ticks, 4 px / tick)"))
        bd.append(ROW.format("\n".join(strip_cell(r, cap) for cap, r in sets if lab in cap)))
    with open(os.path.join(OUT, "art15_spider_climb.svg.html"), "w") as f:
        f.write("\n".join(bd) + "\n")
    # png sheet (one row per set, ticks left to right)
    rows = [np.hstack([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=24) for t in r])
            for _, r in sets]
    sh = np.vstack(rows)
    Image.fromarray(sh).resize((sh.shape[1] * 3, sh.shape[0] * 3), Image.NEAREST).save(
        os.path.join(OUT, "art15_spider_climb.png"))
    print("\n".join(L[5:12]))
    return 0


def game_bm(name):
    bm, _meta = S.read_grid(os.path.join(GRID_DIR, name + ".grid"))
    return bm.astype(bool)


if __name__ == "__main__":
    sys.exit(main())
