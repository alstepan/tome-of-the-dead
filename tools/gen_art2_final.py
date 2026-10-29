#!/usr/bin/env python3
"""gen_art2_final.py — 3F ART2 FINAL frames (user picks on art2_options.png, 2026-10-29).

Deterministic pixel art (no AI raster). The REDRAWN frames that replace wired
ones in place live in tools/gen_3f_art.py (it owns them): Orc WALK 1/2 + ATTACK
(O3 overhead; the strip between the legs removed), Ogre SLAM (O1 overhead). This
tool owns the NEW frames only and does NOT wire them (no index.asm /
index_3f.asm / src/frames.asm / SRC6 / defs edits: T13b does that):

  VAMPIRE       BITE   32x48  ax 0  (V1: hood thrust forward, fangs, cape flared
                                     like a bat wing, claw ahead; Necro robe/feet)
  OGRE          RAISE  32x48  ax 0  (O2: club hoisted behind the head, wind-up)
  ORC           RAISE  32x48  ax 8  (new: cleaver raised high behind the head,
                                     torso + head leaning back 1/2 px)
  SMALL ANIMAL  CORPSE 32x16  ax 0  (C2: neutral heap + splash droplets, mirror-
                                     symmetric -> SYM-capable; replaces rat_dead
                                     for Rat / Spider / Giant Rat / Brood Rat)

Inks: Vampire $05, Ogre $44, Orc $04; the corpse asm carries $06 (rat_dead's) —
the engine draws a dead body in the dead kind's ink.

Outputs:
  assets/gfx/sprites/grid/<name>.grid, assets/gfx/sprites/<name>.asm  (native)
  assets/gfx/source/3f_art2_frames.svg.html  canvas fragment: ALL final ART2
      frames (incl. the fixed Orc walk/attack + Ogre slam, identical to the
      3f_frames copies, so svg_sprites.merge_drafts skips them as duplicates)
  assets/gfx/sprites/draft3f_art2_sheet.png  review sheet
Validation (exit 1 on failure): fragment re-parses to the same bitmaps; canvas +
3f_frames + the new frames through the REAL importer (anchors, gfx_convert
clash, data/mask round-trip); committed asm decoded again; symmetric corpse.
Sizes: ZX0 per kind block (zx0_sources.partition + dzx0 round-trip).
Run AFTER tools/gen_3f_art.py. Usage: python3 tools/gen_art2_final.py [--check]
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G  # noqa: E402
import gen_art2_options as A  # noqa: E402  (approved concept builders V1 / O2)
import svg_sprites as S  # noqa: E402
import zx0_sources as ZS  # noqa: E402

REPO = S.REPO
SPR, GRID_DIR = G.SPR, G.GRID_DIR
FRAGMENT = os.path.join(REPO, "assets/gfx/source/3f_art2_frames.svg.html")
SHEET_PNG = os.path.join(SPR, "draft3f_art2_sheet.png")
GEN_DATE = "2026-10-29"
art, put, poly, ellipse, blank = G.art, G.put, G.poly, G.ellipse, G.blank

INK_VAMP = "#00D7D7"      # $05 (T13 Vampire kind row)
INK_CORPSE = "#D7D700"    # $06 = rat_dead's attr; drawn in the dead kind's ink


# ===========================================================================
# ORC RAISE (32x48, ax 8): body of WALK 1 moved to x 8..31; the front arm goes
# up past the jaw (paper ring) and bends back over the skull; the fist sits
# above the crown, the cleaver hangs behind the head in x 0..10. Weight back:
# head rows 0-14 -2 px, torso rows 15-28 -1 px, hips and legs unchanged.
# ===========================================================================

ORC_RAISE_CLEAVER = """
00|.##########.
01|.########.#.
02|.###########
03|.#........##
04|.##########.
"""               # the O3 ATTACK slab mirrored (edge line row 3), haft stub at x 11


def orc_raise() -> np.ndarray:
    sh = (48, 32)
    w = G.orc_walk(G.ORC_LEGS1)
    w[15:29, 18:] = False                    # front arm (re-drawn raised)
    w[29:38, 19:] = False                    # cleaver at the hip
    b = np.zeros(sh, bool)
    b[29:, 8:] = w[29:]                      # hips + legs: body box x 8..31
    b[15:29, 7:31] = w[15:29]                # torso leans back 1 px
    b[0:15, 6:30] = w[0:15]                  # head leans back 2 px
    arm = np.zeros(sh, bool)
    arm |= poly(sh, [(25, 16), (28, 9), (28, 5)], w=3)     # upper arm up past the jaw
    arm |= poly(sh, [(28, 3), (16, 1)], w=3)               # forearm back over the skull
    arm |= ellipse(sh, 14.5, 2.0, 2.4, 2.0)                # fist above/behind the crown
    put(b, arm, sep=True)
    clv = np.zeros(sh, bool)
    clv[0:5, 0:12] = art(ORC_RAISE_CLEAVER, 12)            # blade cocked behind the head
    put(b, clv, sep=True)
    b[2, 11:13] = True                                     # haft into the fist
    for x, y in ((2, 7), (5, 8), (8, 7)):
        b[y, x] = True                                     # wind-up ticks under the blade
    return b


# ===========================================================================
# SMALL ANIMAL CORPSE (C2, 32x16): left half authored, right half = its mirror.
# ===========================================================================

CORPSE_LEFT = """
00|................
01|................
02|................
03|................
04|................
05|................
06|................
07|................
08|...........#....
09|.....#.........#
10|.........#...###
11|...#.......#####
12|.......#.####.##
13|..#...#######.##
14|.#.##########.##
15|################
"""


def small_corpse() -> np.ndarray:
    left = art(CORPSE_LEFT, 16)
    return np.hstack([left, left[:, ::-1]])


# heading, caption, builder, ink, note
NEW = [
    ("VAMPIRE", "BITE", A.vampire_bite32, INK_VAMP,
     "V1 own frame 32x48 ax 0: hood thrust forward, open maw on two fangs, cape flared "
     "like a bat wing, claw ahead; robe/feet = Necro WALK 1."),
    ("OGRE", "RAISE", A.ogre_raise32, G.INK_OGRE,
     "O2 wind-up 32x48 ax 0: club hoisted behind the head (RAISE -> SLAM)."),
    ("ORC", "RAISE", orc_raise, G.INK_ORC,
     "New wind-up 32x48 ax 8: cleaver raised high behind the head, weight back (RAISE -> ATTACK)."),
    ("SMALL ANIMAL", "CORPSE", small_corpse, INK_CORPSE,
     "C2 neutral heap 32x16 ax 0, mirror-symmetric (SYM: one pool facing); replaces rat_dead "
     "for Rat / Spider / Giant Rat / Brood Rat; drawn in the dead kind's ink."),
]
# frames redrawn in gen_3f_art.py, shown on the review fragment/sheet (same pixels)
REDRAWN = [("ORC", "WALK 1"), ("ORC", "WALK 2"), ("ORC", "ATTACK"), ("OGRE", "SLAM")]
NOTE_TEXT = {
    "ORC": "ART2: the 1-px strip hanging between the legs removed (all frames); ATTACK = O3 "
           "cleaver overhead; NEW RAISE wind-up. Ink $04.",
    "OGRE": "ART2: SLAM = O1 club down at head height + swing arc (same 40x48); NEW RAISE "
            "32x48. Ink $44.",
    "VAMPIRE": "ART2: own BITE (the Vampire otherwise draws the Necro walk frames). Ink $05.",
    "SMALL ANIMAL": "ART2: shared small-animal corpse (C2). The Spider keeps no own DEAD.",
}


def pool_bytes(name: str, w: int, h: int) -> int:
    """pool_spike.md: cell-aligned (STA) = h x 2 (mask+data) x cols x 2 facings; SYM one facing."""
    return h * 2 * (w // 8) * (1 if name in S.SYMMETRIC_FRAMES else 2)


def asm_notes(b) -> list[str]:
    h, w = b["bm"].shape
    return ["DRAFT (not yet on the canvas): assets/gfx/source/3f_art2_frames.svg.html",
            "generated by tools/gen_art2_final.py (3F ART2 final)",
            f"artboard: {b['hd']} / {b['cap']} ({w}x{h}), ink {b['ink']}",
            f"grid: {b['rel_grid']}",
            f"anchor: {b['anchor_note']}; ax_L={b['axl']}",
            "class: STATIONARY" + (", SYMMETRIC (mirror-identical: one pool facing)"
                                   if b["name"] in S.SYMMETRIC_FRAMES else ""),
            "NOT in sprites/index.asm / index_3f.asm yet (T13b wires it: FRM row, SRC6 block)"]


def gfx_native(b, out_asm) -> None:
    colour, bright = S.INK_MAP[b["ink"]]
    argv = ["--mode", "sprite", "--layout", "native", "--in", b["rel_grid"],
            "--name", b["name"], "--out", out_asm,
            "--ink", G.GC.COL_NAME[colour], "--paper", "black", "--band-paper", "black",
            "--anchor-x", str(b["ax"]), "--anchor-y", str(b["ay"]), "--src-path",
            "--date", GEN_DATE]
    for n in asm_notes(b):
        argv += ["--note", n]
    if bright:
        argv.append("--bright")
    S._quiet(S.run_gfx, argv)


def grid_text(b) -> str:
    t = G.grid_text(b).split("\n", 1)[1]
    return ("# WazHack/ZX gfx text grid — DRAFT generated by tools/gen_art2_final.py "
            "(edit that); 3F ART2 final, not on the canvas yet.\n" + t)


def zx0_group(fl, zdir, tag) -> int:
    parts = ZS.partition(fl, zdir)
    tot = 0
    for i, (s0, k) in enumerate(parts):
        raw = b"".join(d for _, d in fl[s0:s0 + k])
        z = ZS.pack(raw, zdir)
        ZS.roundtrip(z, raw, zdir, f"{tag}{i}")
        tot += len(z)
    return tot


def label(im, text, sub=""):
    c = Image.new("RGB", (max(im.width, 150), im.height + 30), (24, 24, 36))
    c.paste(im, (0, 0))
    d = ImageDraw.Draw(c)
    d.text((2, im.height + 4), text, fill=(232, 230, 240))
    if sub:
        d.text((2, im.height + 16), sub, fill=(150, 150, 170))
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate + sizes; write nothing")
    args = ap.parse_args()
    new = []
    for hd, cap, fn, ink, note in NEW:
        bm = fn().astype(bool)
        name = f"{S.CHAR_PREFIX[hd]}_{S.slug(cap)}"
        h, w = bm.shape
        assert w % 8 == 0 and h % 8 == 0 and h <= 48, (name, w, h)
        new.append(dict(hd=hd, cap=cap, name=name, bm=bm, ink=ink, note=note,
                        solid=S.make_mask(bm, S.OUTLINE, name)))
    by_new = {b["name"]: b for b in new}
    assert np.array_equal(by_new["small_corpse"]["bm"], by_new["small_corpse"]["bm"][:, ::-1])
    # the redrawn frames, straight from their owner (gen_3f_art.py)
    g3 = {}
    for hd, cap, fn, ink in G.FRAMES:
        bm = fn()
        g3[(hd, cap)] = dict(hd=hd, cap=cap, name=f"{S.CHAR_PREFIX[hd]}_{S.slug(cap)}", bm=bm,
                             ink=ink, solid=S.make_mask(bm, S.OUTLINE))
    # ---- fragment: every final ART2 frame, grouped per character
    order = ["ORC", "OGRE", "VAMPIRE", "SMALL ANIMAL"]
    shown = {hd: [g3[k] for k in REDRAWN if k[0] == hd] + [b for b in new if b["hd"] == hd]
             for hd in order}
    out = ["<!-- WazHack/ZX 3F ART2 FINAL artboards (user picks 2026-10-29 on art2_options.png). "
           "Generated by tools/gen_art2_final.py (+ the redrawn frames of tools/gen_3f_art.py, "
           "identical to their 3f_frames.svg.html copies). All face right (the engine mirrors). -->",
           "<h2>3F ART2</h2>"]
    for hd in order:
        out.append(G.heading(hd))
        out.append(G.NOTE.format(html.escape(NOTE_TEXT[hd])))
        out.append(G.ROW)
        out += [G.artboard(b["bm"], b["ink"], b["cap"]) for b in shown[hd]]
        out.append("</div>")
    frag = "\n".join(out) + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "frag.html")
        with open(fpath, "w") as f:
            f.write(frag)
        fr, _ = S.parse_sheet(fpath)
        flat = [b for hd in order for b in shown[hd]]
        assert len(fr) == len(flat)
        for f, b in zip(fr, flat):
            assert (f.character, f.caption) == (b["hd"], b["cap"]) and \
                np.array_equal(f.bitmap, b["bm"]), b["name"]
        # ---- the real importer: canvas + 3f_frames (sprites) + the NEW frames
        newfrag = "\n".join([G.heading(b["hd"]) + "\n" + G.ROW + "\n"
                             + G.artboard(b["bm"], b["ink"], b["cap"]) + "\n</div>"
                             for b in new])
        sheet = os.path.join(tmp, "sheet.html")
        with open(sheet, "w") as f:
            f.write(open(S.SHEET).read() + "\n"
                    + open(G.FRAGMENT).read().split("<h2>3F TILES</h2>")[0] + "\n" + newfrag)
        frames = S.import_sheet(sheet, os.path.join(tmp, "out"), GEN_DATE)
        by = {f.name: f for f in frames}
        for k in REDRAWN:                       # gen_3f_art.py was run after its edit
            assert np.array_equal(by[g3[k]["name"]].bitmap, g3[k]["bm"]), \
                f"{g3[k]['name']}: 3f_frames.svg.html is stale — run tools/gen_3f_art.py first"
        for b in new:
            f = by[b["name"]]
            assert np.array_equal(f.solid, b["solid"]), b["name"]
            b["ax"], b["ay"] = f.anchor
            b["axl"] = f.extra["ax_l"]
            b["anchor_note"] = ("declared (svg_sprites ANCHOR_X)" if f.extra.get("declared")
                                else f"reference {f.extra['ref']} head-band IoU "
                                     f"{f.extra['iou']:.2f}")
            b["raw"], rows, _ = G.raw_bytes(os.path.join(tmp, "out", b["name"] + ".asm"))
            G.check_rows(b, rows)
        print(f"importer: canvas + 3f_frames + {len(new)} ART2 frames, clash + round-trip OK")
        # ---- sizes: ZX0 per kind block, pool per frame (both facings; SYM one)
        raw = {f.name: G.raw_bytes(os.path.join(tmp, "out", f.name + ".asm"))[0]
               for f in frames if f.kind == "sprite"}
        zdir = os.path.join(tmp, "z")
        os.makedirs(zdir)
        for b in new:
            h, w = b["bm"].shape
            print(f"{b['name']:14s} {w}x{h:<3d} raw {len(b['raw']):4d} ax {b['ax']} ay {b['ay']} "
                  f"axL {b['axl']}  pool {pool_bytes(b['name'], w, h)}"
                  + (" (SYM; STA 256)" if b["name"] in S.SYMMETRIC_FRAMES else ""))
        blocks = [("ORC", ["orc_walk1", "orc_walk2", "orc_attack"], "orc_raise", 338),
                  ("OGRE", ["ogre_walk1", "ogre_walk2", "ogre_slam"], "ogre_raise", 464),
                  ("NECRO", ["necro_walk1", "necro_walk2", "necro_cast"], "vamp_bite", 470)]
        for g, names, add, standin in blocks:
            base = zx0_group([(n, raw[n]) for n in names], zdir, g)
            plus = zx0_group([(n, raw[n]) for n in names + [add]], zdir, g + "p")
            print(f"group {g:5s} {len(names)} frames zx0 {base} (stand-in {standin}, cap "
                  f"{standin * 11 // 10}) ; + {add}: {plus} (delta +{plus - base})")
        rd = zx0_group([("rat_dead", raw["rat_dead"])], zdir, "rd")
        sc = zx0_group([("small_corpse", raw["small_corpse"])], zdir, "sc")
        print(f"corpse: rat_dead zx0 {rd} -> small_corpse {sc} (delta {sc - rd:+d})")
    if args.check:
        return 0
    with open(FRAGMENT, "w") as f:
        f.write(frag)
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        for b in new:
            gpath = os.path.join(GRID_DIR, b["name"] + ".grid")
            b["rel_grid"] = os.path.relpath(gpath, REPO)
            with open(gpath, "w") as f:
                f.write(grid_text(b))
            asm = os.path.join("assets/gfx/sprites", b["name"] + ".asm")
            gfx_native(b, asm)
            rb, rows, attr = G.raw_bytes(asm)
            G.check_rows(b, rows)
            assert rb == b["raw"], b["name"]
            colour, bright = S.INK_MAP[b["ink"]]
            assert attr == colour | (0x40 if bright else 0), (b["name"], attr)
    finally:
        os.chdir(cwd)
    # ---- review sheet (x4, ink on black, mask-opaque paper black on slate)
    rows_im = []
    for hd in order:
        ims = [label(G.render(b["bm"], b["solid"], b["ink"]),
                     f"{b['name']}  {b['bm'].shape[1]}x{b['bm'].shape[0]}",
                     "NEW" if b in new else "redrawn (wired fid)") for b in shown[hd]]
        if hd == "SMALL ANIMAL":               # also in Spider ink: it is shared
            b = by_new["small_corpse"]
            ims.append(label(G.render(b["bm"], b["solid"], G.INK_SPIDER),
                             "small_corpse", "as Spider ($05)"))
        title = Image.new("RGB", (400, 16), (24, 24, 36))
        ImageDraw.Draw(title).text((2, 2), hd, fill=(255, 216, 74))
        rows_im.append(G.vstack_im([title, G.hstrip(ims)], gap=2))
    G.vstack_im(rows_im).save(SHEET_PNG)
    print(f"wrote {len(new)} grids + asm, {os.path.relpath(FRAGMENT, REPO)}, "
          f"{os.path.relpath(SHEET_PNG, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
