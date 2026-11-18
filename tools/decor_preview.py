#!/usr/bin/env python3
"""decor_preview.py - DECOR2 step 1: old-vs-new room previews with the real tile graphics.

Renders rooms (storey 0 + storey 1, 32 x 18 cells = 256 x 144 px) at Spectrum colours: glyphs and attrs
are the engine's own (assets/gfx/tiles/tiles_common.asm ids 0..31, the per-depth tileset record out of
bank 7 of the built .sna for ids 32..63, the depth's floor / wall attrs as level_tiles7 patches them,
assets/gfx/panel/panel_orn.asm for the row-17 ornament).  Sprites, floor items and door key plates are
omitted.  The same room (same level seed, same room, same RD_SEED) is derived by the deployed decorgen.py
(OLD) and by the DECOR2 model decorgen2.py (NEW).

    python3 tools/decor_preview.py OUTDIR [--ascii]

Writes OUTDIR/dNN_rX_old.png, dNN_rX_new.png and decor2_sheet.png (pairs side by side, labelled).
Needs a build (tests/game_lib reads build/tome-of-the-dead.sym / .sna; DEBUG_KIT=0).
"""
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "tools"))
import decorgen as DG               # noqa: E402
import decorgen2 as D2              # noqa: E402
import levelgen as G                # noqa: E402
import room_model as RM             # noqa: E402
from game_lib import S, tset_slot, sna_bank7   # noqa: E402

COLS, ROWS = 32, 18
SCALE = 3


def defbs(path, first_label, n):
    """the first n bytes of the DEFB lines after `first_label:` in an asm file."""
    out, on = [], False
    for line in open(path):
        if line.startswith(first_label + ":"):
            on = True
            continue
        if on:
            m = re.match(r"\s*DEFB\s+([^;]+)", line)
            if m:
                out += [int(x.strip().lstrip("$"), 16) for x in m.group(1).split(",")]
                if len(out) >= n:
                    return bytes(out[:n])
    raise ValueError(first_label)


COMMON_G = defbs(os.path.join(REPO, "assets/gfx/tiles/tiles_common.asm"), "tiles_common_glyphs", 32 * 8)
COMMON_A = defbs(os.path.join(REPO, "assets/gfx/tiles/tiles_common.asm"), "tiles_common_attrs", 32)
ORN = defbs(os.path.join(REPO, "assets/gfx/panel/panel_orn.asm"), "orn_glyphs", 64)
T = RM.T


def tables(depth):
    """-> (glyphs 64 x 8 B, attrs 64) of depth `depth` as the engine holds them in TILE_GLYPHS / TILE_ATTRS."""
    slot = tset_slot(sna_bank7, depth - 1)
    glyphs = COMMON_G + slot[:256]
    attrs = bytearray(COMMON_A + slot[256:288])
    fl, wl = RM.THEME[depth]
    for n in ("T_PLAT", "T_WALLF", "T_END_L", "T_END_R"):
        attrs[T[n]] = fl
    for n in ("T_BRICK", "T_WALL_DITHER", "T_WALL_PATCH", "T_WALL_FADE", "T_RUBBLE"):
        attrs[T[n]] = wl
    return glyphs, bytes(attrs)


def colour(idx, bright):
    lv = 0xFF if bright else 0xD7
    return ((idx >> 1 & 1) * lv, (idx >> 2 & 1) * lv, (idx & 1) * lv)


def render(flat, depth, scale=SCALE):
    """576 tile ids -> PIL image (256 x 144 x scale)."""
    glyphs, attrs = tables(depth)
    img = np.zeros((ROWS * 8, COLS * 8, 3), np.uint8)
    item = {T["T_ITEM0"] + k for k in range(8)} if "T_ITEM0" in T else set()
    for r in range(ROWS):
        for c in range(COLS):
            t = flat[r * COLS + c]
            if t in item or 60 <= t < 64:                       # floor-item markers: the icons are runtime overlays
                t = 0
            g = glyphs[t * 8:t * 8 + 8]
            if r == RM.F1 and t in (T["T_PLAT"], T["T_WALLF"]):
                k = RM.orn_index(c)
                g = ORN[k * 8:k * 8 + 8]
            a = attrs[t]
            ink, paper = colour(a & 7, a & 0x40), colour(a >> 3 & 7, a & 0x40)
            for y in range(8):
                for x in range(8):
                    img[r * 8 + y, c * 8 + x] = ink if g[y] >> (7 - x) & 1 else paper
    im = Image.fromarray(img)
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def room_of(depth, seed):
    return bytes(G.generate(depth, seed * 7919 & 0xFFFF or 1))


def derive(blk, r, depth, new):
    """final 576 tile ids of room r (decor + the lair gate over its holes), + the mood (new only)."""
    base = RM.base_room(blk, r)
    o = G.LOFF_DESC + r * S["RD_STRIDE"]
    sd = blk[o + S["RD_SEED"]] | blk[o + S["RD_SEED"] + 1] << 8
    mood = None
    if new:
        flat, _al, objs = D2.decorate(base, depth, sd, True, RM.room_role(blk, r))
        mood = objs.mood
    else:
        flat, _al = DG.decorate(base, depth, sd)
    xc = blk[o + S["RD_EXITCOL"]]
    if xc:
        for k in range(3):
            flat[RM.F1 * COLS + xc + k] = T["T_GRATE_SHUT"]
    return flat, mood


def role_name(blk, r):
    _rid, fl, key = RM.room_role(blk, r)
    return ("start" if fl & D2.RDF_START else "lair" if fl & D2.RDF_LAIR else "key room" if key
            else "dead end" if fl & D2.RDF_DEADEND else "plain")


# the 8 review rooms: (depth, wanted role, wanted DECOR2 mood or None, tag)
PICKS = [(1, "start", None, "start"), (2, "plain", "LIT", "lit"), (3, "key room", None, "key"),
         (4, "lair", None, "lair"), (5, "dead end", "DARK", "dark"), (6, "dead end", "DARK", "dark+moss"),
         (7, "plain", "DIM", "dim"), (8, "plain", "LIT", "lit")]


def pick_rooms():
    out, used = [], set()
    for depth, role, mood, _tag in PICKS:
        for seed in range(1, 400):
            blk = room_of(depth, seed)
            for r in range(G.NCELL):
                o = G.LOFF_DESC + r * S["RD_STRIDE"]
                fl = blk[o + S["RD_FLAGS"]]
                if not fl & S["RDF_PRESENT"] or fl & S["RDF_SANCTUM"] or role_name(blk, r) != role:
                    continue
                if (depth, r) in used:
                    continue
                new, m = derive(blk, r, depth, True)
                if mood and m != mood:
                    continue
                st, pit = D2.analyze(RM.base_room(blk, r))
                if role in ("plain", "lair", "key room") and not (st[0]["focal"] and st[1]["focal"] or role == "lair"):
                    continue                                   # prefer rooms with a ladder / shaft in view
                used.add((depth, r))
                out.append((depth, r, seed, role, m, blk))
                break
            else:
                continue
            break
        else:
            raise SystemExit(f"no D{depth} {role} room found")
    return out


def main(argv):
    outdir = argv[1]
    os.makedirs(outdir, exist_ok=True)
    font = ImageFont.load_default(size=16)
    pairs = []
    for depth, r, seed, role, mood, blk in pick_rooms():
        old, _ = derive(blk, r, depth, False)
        new, _ = derive(blk, r, depth, True)
        io, inw = render(old, depth), render(new, depth)
        io.save(os.path.join(outdir, f"d{depth:02d}_r{r}_old.png"))
        inw.save(os.path.join(outdir, f"d{depth:02d}_r{r}_new.png"))
        pairs.append((depth, r, seed, role, mood, io, inw))
        if "--ascii" in argv:
            print(depth, r, seed, role, mood)
    w, h = pairs[0][5].size
    pad, lab = 16, 26
    percol = 2
    nrow = (len(pairs) + percol - 1) // percol
    cw = 2 * w + pad
    sheet = Image.new("RGB", (percol * (cw + pad) + pad, nrow * (h + lab + pad) + pad + 28), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 6), "DECOR2 model: OLD (left, deployed decorgen.py) vs NEW (right, decorgen2.py), same room, real tiles, no sprites",
           fill=(220, 220, 220), font=font)
    for i, (depth, r, seed, role, mood, io, inw) in enumerate(pairs):
        x = pad + (i % percol) * (cw + pad)
        y = 28 + pad + (i // percol) * (h + lab + pad)
        d.text((x, y), f"D{depth} room {r} ({role}), level seed {seed}   OLD  |  NEW" + (f" mood {mood}" if mood else ""),
               fill=(255, 255, 255), font=font)
        sheet.paste(io, (x, y + lab))
        sheet.paste(inw, (x + w + pad, y + lab))
    sheet.save(os.path.join(outdir, "decor2_sheet.png"))
    print(f"{len(pairs)} pairs -> {outdir}")
    for depth, r, seed, role, mood, *_ in pairs:
        print(f"  d{depth:02d}_r{r}  {role:9s} seed {seed:3d} mood {mood}")


if __name__ == "__main__":
    main(sys.argv)
