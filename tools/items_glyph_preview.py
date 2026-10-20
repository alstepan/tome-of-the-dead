#!/usr/bin/env python3
"""items_glyph_preview.py — review page + validation for the 3E floor-item class glyphs.

Source: assets/gfx/concept/grid/items3e.tiles (food, pages, weapon, worn, ammo, trap; 8x8,
1 ink on black) + the FLASK glyph = the old T_POTION bytes (sprites item_potion rows 0..7).
Rulings: docs/design/game.md §8.11 Q1 (class = shape, type = ink), §1.5 (T_TRAP type inks).
Writes:
  assets/gfx/tiles/items3e.svg.html   x8 artboard per glyph + legend table; (a) the 7 glyphs on
                                      a black standing row over a T_PLAT row in each of the 8
                                      ATTR_FLOOR values (tiles_convert.SCHEME), x4 and x1;
                                      (b) x2 bag-page icons (16x16, 2x2 cells) in every ink
                                      variant, normal and cursor (paper blue), shown x3
  <png_dir>/items3e.png               scene (a) for all 8 floors stacked (x4), if --png
Validation (exit 1 on failure): blocks parse (8x8); every default/variant attr has paper black,
ink != black/blue, cursor attr = ink|$08 legal; ink on row 7 (stands on the floor line); the 7
glyphs pairwise distinct; the 6 blocks packed through tools/gfx_convert.py --mode tile (clash:
one ink+paper per tile) and decoded back from the emitted DEFB == the grid (round-trip).
Usage: python3 tools/items_glyph_preview.py [--png DIR]
Review artefact only: no engine data is written (staff wires ids 10/17/18/60..63 after approval).
"""
from __future__ import annotations

import argparse
import html
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b10_preview as bp  # noqa: E402  (scene_svg / scene_png / artboard / figure / PLAT)
import tiles_convert as tc  # noqa: E402

SRC = "items3e.tiles"
OUT = os.path.join(tc.REPO, "assets/gfx/tiles/items3e.svg.html")
AIR = (bytes(8), 0x00)
PLAT_G = bp.PLAT[0]
CURSOR_PAPER = 0x08                    # §8.11 Q3: cursor = paper blue (ink | $08)

# (block or None=FLASK, label, tile id, [(type, attr), ...] first = default)
CLASSES = [
    (None,     "FLASK",  60, [("potion (appearance ink, §8.8)", 0x42), ("e.g.", 0x45),
                              ("e.g.", 0x43), ("e.g.", 0x44), ("e.g.", 0x46), ("e.g.", 0x47)]),
    ("food",   "FOOD",   61, [("meat", 0x42), ("cheese", 0x46), ("pear", 0x04),
                              ("apple", 0x44), ("carrot", 0x06)]),
    ("pages",  "PAGES",  18, [("scroll", 0x07), ("book", 0x43)]),
    ("weapon", "WEAPON", 62, [("blade", 0x07), ("staff/bow", 0x06), ("BUC blessed", 0x45),
                              ("BUC cursed", 0x42)]),
    ("worn",   "WORN",   63, [("armour/helm", 0x07), ("charm", 0x06), ("BUC blessed", 0x45),
                              ("BUC cursed", 0x42)]),
    ("ammo",   "AMMO",   17, [("daggers", 0x47), ("arrows", 0x46)]),
    ("trap",   "T_TRAP", 10, [("DART", 0x42), ("GAS", 0x44), ("TELEPORT", 0x43),
                              ("ALARM", 0x46)]),
]
NOTES = {
    "food": "tilted drumstick: meat (paper shine) top-left, bone + knob down-right.",
    "pages": "upright scroll (= icons8 scroll8 motif): scrolls and class books.",
    "weapon": "leaning sword, blade up-right (item_sword motif), pommel on the floor.",
    "worn": "heater shield with a paper cross, tip on the floor.",
    "ammo": "two crossed shafts tied at the crossing: daggers or arrows. Replaces dagger pile.",
    "trap": "revealed flush pressure plate, 2 rows: slab + 2 dart holes.",
}
INK_NAME = {0: "black", 1: "blue", 2: "red", 3: "magenta", 4: "green", 5: "cyan",
            6: "yellow", 7: "white"}


def glyph(block):
    if block is None:
        return tc.item_tile("item_potion", 0)
    return tc.tile8(SRC, block)[0]


def default_attr(block):
    return tc.tile8(SRC, block)[1]


def attr_name(a: int) -> str:
    return f"{'bright ' if a & 0x40 else ''}{INK_NAME[a & 7]} on {INK_NAME[(a >> 3) & 7]}"


def scene(floor_attr: int):
    row = [AIR] + [(glyph(b), v[0][1]) for b, _, _, v in CLASSES] + [AIR]
    w = len(row)
    return [[AIR] * w, row, [(PLAT_G, floor_attr)] * w]


def double(g: bytes, attr: int):
    """8x8 glyph -> 2x2 cells of the x2 page icon (16x16), all cells the item attr."""
    rows = []
    for y in range(8):
        v = 0
        for x in range(8):
            bit = (g[y] >> (7 - x)) & 1
            v = (v << 2) | (bit * 3)
        rows += [v, v]
    top = [bytes(r >> 8 for r in rows[:8]), bytes(r & 0xFF for r in rows[:8])]
    bot = [bytes(r >> 8 for r in rows[8:]), bytes(r & 0xFF for r in rows[8:])]
    return [[(top[0], attr), (top[1], attr)], [(bot[0], attr), (bot[1], attr)]]


def validate() -> list[str]:
    errs = list(tc.errors)
    names = [b for b, *_ in CLASSES if b]
    have = tc.blocks(SRC)
    errs += [f"missing block {n}" for n in names if n not in have]
    if errs:
        return errs
    errs += list(tc.errors)
    for b, label, _, variants in CLASSES:
        g = glyph(b)
        if not g[7]:
            errs.append(f"{label}: no ink on row 7 (must stand on the floor line)")
        if b and default_attr(b) != variants[0][1]:
            errs.append(f"{label}: header attr ${default_attr(b):02X} != default "
                        f"${variants[0][1]:02X}")
        for t, a in variants:
            ink, paper = a & 7, (a >> 3) & 7
            if paper != 0 or a & 0x80:
                errs.append(f"{label}/{t}: attr ${a:02X} paper not black / FLASH set")
            if ink in (0, 1):
                errs.append(f"{label}/{t}: ink {INK_NAME[ink]} unreadable on black/cursor blue")
    gl = [glyph(b) for b, *_ in CLASSES]
    for i in range(len(gl)):
        for j in range(i + 1, len(gl)):
            if gl[i] == gl[j]:
                errs.append(f"{CLASSES[i][1]} == {CLASSES[j][1]} glyph")
    with tempfile.TemporaryDirectory() as td:
        grid = os.path.join(td, "items3e.grid")
        with open(grid, "w") as f:
            for n in names:
                a = default_attr(n)
                f.write(f"=== {n} ink:{INK_NAME[a & 7]} paper:black"
                        f"{' bright' if a & 0x40 else ''}\n")
                f.write("\n".join(have[n]["rows"]) + "\n\n")
        asm = os.path.join(td, "items3e.asm")
        r = subprocess.run([sys.executable, os.path.join(tc.REPO, "tools/gfx_convert.py"),
                            "--mode", "tile", "--in", grid, "--name", "items3e", "--out", asm,
                            "--date", "review"], capture_output=True, text=True)
        if r.returncode:
            errs.append("gfx_convert: " + (r.stderr or r.stdout).strip())
        else:
            print(r.stdout.strip())
            for n in names:
                got = tc.asm_bytes(asm, f"items3e_{n}")
                if got[:8] != glyph(n):
                    errs.append(f"round-trip mismatch {n}")
    return errs


def legend() -> str:
    th = 'style="text-align:left;padding:4px 10px;border-bottom:1px solid #33334a;"'
    td = 'style="padding:4px 10px;vertical-align:middle;"'
    rows = [f"<tr><th {th}>id</th><th {th}>class (shape)</th><th {th}>type -> attr (ink on "
            f"black)</th></tr>"]
    for b, label, tid, variants in CLASSES:
        chips = " ".join(
            f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;">'
            f'<span style="width:10px;height:10px;display:inline-block;background:'
            f'{bp.zx_hex(a & 7, bool(a & 0x40))};"></span>{html.escape(t)} ${a:02X}</span>'
            for t, a in variants)
        rows.append(f"<tr><td {td}>{tid}</td><td {td}>{label}</td><td {td}>{chips}</td></tr>")
    return ('<table style="border-collapse:collapse;font-size:10px;color:#d8d6e6;">'
            + "".join(rows) + "</table>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png")
    a = ap.parse_args()
    errs = validate()
    if errs:
        print("\n".join("ERROR: " + e for e in errs), file=sys.stderr)
        sys.exit(1)
    print("round-trip: OK (6 tiles), attrs: paper black, ink legal in all variants + cursor; "
          "all glyphs rest on row 7, pairwise distinct")
    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = ['<!doctype html><meta charset="utf-8"><title>3E item glyphs</title>',
         '<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" '
         'rel="stylesheet"><body style="margin:0;background:#12121c;">',
         f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">3E FLOOR-ITEM GLYPHS (DRAFT FOR REVIEW)</h2>',
         '<div style="font-size:10px;color:#a9a7b8;max-width:900px;line-height:1.6;">'
         'Class = glyph shape, type = per-cell ink (game.md §8.11 Q1). All on black paper in '
         'the standing row, so the floor colour below never clashes. FLASK = existing T_POTION '
         'glyph (no new art).</div>',
         '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;">']
    for b, label, tid, variants in CLASSES:
        if b is None:
            h.append(bp.figure(bp.scene_svg([[(glyph(None), variants[0][1])]], scale=8),
                               f"FLASK id 60 · ${variants[0][1]:02X} (existing)"))
        else:
            at = variants[0][1]
            h.append(bp.artboard(SRC, b, bp.zx_hex(at & 7, bool(at & 0x40)),
                                 f"{label} id {tid} · default ${at:02X}. {NOTES[b]}"))
    h += ['</div>', legend()]
    for scale in (4, 1):
        h += [f'<h2 style="margin:0;font-size:12px;">(a) x{scale} · FLASK FOOD PAGES WEAPON '
              f'WORN AMMO TRAP on the standing row over each ATTR_FLOOR</h2>',
              '<div style="display:flex;gap:20px;flex-wrap:wrap;">']
        h += [bp.figure(bp.scene_svg(scene(fa), scale=scale), f"D{d} ${fa:02X}")
              for d, (fa, _) in enumerate(tc.SCHEME, 1)]
        h += ['</div>']
    h += ['<h2 style="margin:0;font-size:12px;">(b) bag page icons: glyph x2 = 16x16 (2x2 '
          'cells), shown x3 · every ink variant, then the cursor state (paper blue)</h2>']
    for b, label, tid, variants in CLASSES:
        if b == "trap":
            continue                   # traps never enter the bag
        g = glyph(b)
        figs = [bp.figure(bp.scene_svg(double(g, at), scale=3), f"{t} ${at:02X}")
                for t, at in variants]
        cur = variants[0][1] | CURSOR_PAPER
        figs.append(bp.figure(bp.scene_svg(double(g, cur), scale=3), f"cursor ${cur:02X}"))
        h += [f'<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end;">'
              f'<div style="width:90px;font-size:10px;">{label}</div>{"".join(figs)}</div>']
    h += ['</div></body>', '']
    with open(OUT, "w") as f:
        f.write("\n".join(h))
    print("wrote", OUT)
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        allrows = []
        for fa, _ in tc.SCHEME:
            allrows += scene(fa)
        bp.scene_png(allrows, os.path.join(a.png, "items3e.png"), scale=4)
        print("png ->", os.path.join(a.png, "items3e.png"))


if __name__ == "__main__":
    main()
