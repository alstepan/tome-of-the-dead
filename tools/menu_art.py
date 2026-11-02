#!/usr/bin/env python3
"""menu_art.py -- Stage 3C C3-5: menu font, title lettering and torches -> include data.

Reads the approved concept grids (assets/gfx/concept/grid/{font8x16,title16,bigdecor}.grid),
emits assets/gfx/menu/menu_{font,title,torch}.asm (+ .bin of the raw pixel data) with
ASSERT-able sizes and assets/gfx/menu/menu_art.inc (all sizes as EQUs), then composes the
menu screen FROM THE PACKED BYTES (not from the grids) into a PNG, runs the per-cell
attribute-legality check and diffs the 8x16 / title / torch regions against the concept
screen_menu.scr.   usage: python3 tools/menu_art.py [--preview DIR]

Charset (8x16) is derived from the menu/end-screen strings in MENU_STRINGS (game.md 3.2,
3.4, src/strings.txt); letters are the full A-Z because KILLED BY <monster> and DEPTH cards
are open-ended. Hero previews and the row-6 ornament reuse existing data (printed at the end).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import concept_screen as C          # noqa: E402  (Screen, validate, sprites, png)
import font_tool as FT              # noqa: E402

ROOT = os.path.dirname(HERE)
GRID = os.path.join(ROOT, "assets", "gfx", "concept", "grid")
OUT = os.path.join(ROOT, "assets", "gfx", "menu")

# Every string drawn in the 8x16 menu font (+ end screens). Digits 0-9 and A-Z are kept whole.
MENU_STRINGS = [
    "> 1 START", "2 HERO: MAGE", "2 HERO: WARRIOR", "3 CONTROLS", "4 REDEFINE KEYS",
    "PAUSED", "DEPTH 8", "KILLED BY SKELETON GUARD", "YOU WIN! PRESS ENTER",
    "YOU DIED - PRESS ENTER", "PRESS KEY FOR UP", "KEY ALREADY USED", "0123456789",
]
LETTERS = [chr(c) for c in range(65, 91)]
DIGITS = [str(d) for d in range(10)]
CHARSET = sorted(set(" ".join(MENU_STRINGS)) | set(LETTERS) | set(DIGITS), key=ord)


def font_glyph(c: int) -> int:
    """Glyph index of ASCII c = the Z80 range arithmetic of menu1.asm `mf_char_e`
    (RECLAIM-B T3; replaced a 64-B map).  Anything absent -> 0 (space).  Needs the
    charset ' !-0123456789:>A..Z' (asserted in build())."""
    if c == 32 or c == 33:
        return c - 32                       # ' ' 0, '!' 1
    if c == 45:
        return 2                            # '-'
    if 48 <= c <= 58:
        return c - 45                       # '0'..'9' 3..12, ':' 13
    if c == 62:
        return 14                           # '>'
    if 65 <= c <= 90:
        return c - 50                       # 'A'..'Z' 15..40
    return 0
TITLE_LINES = ((1, "TOME OF"), (3, "THE DEAD"))
TITLE_SET = sorted(set("TOME OF THE DEAD") - {" "}, key=ord)
TORCH_COLS = (2, 28)               # concept screen_menu: tall torch, rows 0-3
TORCH_STEP_OLD, TORCH_CYCLE = 3, (0x46, 0x46, 0x42)   # the pre-LOOK-1 torch: menu_torch.bin only (loading screen tool)
# LOOK-1 (user 2026-11-02): the menu torch = the decor tall torch's RAG flame, fixed red, no attr cycle;
# 2 glyph-swap frames every TORCH_STEP menu frames (8 x 20 ms = 160 ms, the decor flames' 4-tick rate)
TORCH_STEP, TORCH_LOOK = 8, ("torch_tall_look1_f1", "torch_tall_look1_f2")
A_TOP, A_BOT, A_ORN = 0x47, 0x46, 0x0D
HEROES = (("warrior", "knight_idle1  (sprite idx KNIGHT_IDLE1_IDX, 24x48)", 21, 9, 0x07),
          ("mage", "wizard_idle   (sprite idx WIZARD_IDLE_IDX, 24x48)", 25, 9, 0x45))


def db(rows: list[bytes], comment=lambda i: "") -> str:
    return "".join("        DEFB " + ",".join(f"${b:02X}" for b in r) + f"    ; {comment(i)}\n"
                   for i, r in enumerate(rows))


TSETS = os.path.join(ROOT, "assets", "gfx", "tiles", "tilesets.asm")


def tset_pool_glyphs() -> list[bytes]:
    """The bank-7 tset_pool glyphs (tools/tiles_convert.py output), in index order."""
    out, on = [], False
    for ln in open(TSETS):
        t = ln.split(";")[0].strip()
        if t.startswith("tset_pool:"):
            on = True
        elif on and t.startswith("DEFB"):
            out.append(bytes(int(v.strip().lstrip("$"), 16) for v in t[4:].split(",")))
        elif on and t.endswith(":"):
            break
    return out


def torch_pool_ix(run: bytes) -> int:
    """RECLAIM-C (d): index of the run of tset_pool glyphs == these torch cells (the D1 tall
    torch); the menu reads them from bank 7 instead of a bank-1 copy."""
    pool, n = tset_pool_glyphs(), len(run) // 8
    for i in range(len(pool) - n + 1):
        if b"".join(pool[i:i + n]) == run:
            return i
    sys.exit("menu_art: torch cells are no longer a tset_pool run "
             "(tilesets.asm changed?): restore a bank-1 copy (RECLAIM-C (d))")


def pack_rows(g: np.ndarray) -> bytes:
    """bool (h, w) -> h * w/8 bytes, MSB-left."""
    return bytes(int("".join("1" if v else "0" for v in row[x:x + 8]), 2)
                 for row in g for x in range(0, g.shape[1], 8))


def build() -> dict:
    f16 = FT.parse(os.path.join(GRID, "font8x16.grid"), 8, 16)
    ft = FT.parse(os.path.join(GRID, "title16.grid"), 16, 16)
    big = C.parse_blocks(os.path.join(GRID, "bigdecor.grid"))
    assert all(font_glyph(ord(c)) == i for i, c in enumerate(CHARSET)), \
        "menu1.asm mf_char_e range arithmetic no longer matches CHARSET"
    d = {"font": [pack_rows(f16[ord(c)]) for c in CHARSET],
         "title": [pack_rows(ft[ord(c)]) for c in TITLE_SET]}
    # --- torch: split cells into static / glyph-swap rows
    cells = lambda b: [b["bm"][r * 8:r * 8 + 8, c * 8:c * 8 + 8] for r in range(4) for c in range(2)]

    def split(names):
        fr = [big[n] for n in names]
        cf = [cells(b) for b in fr]
        diff = [i for i in range(8) if any(not np.array_equal(cf[0][i], cf[k][i]) for k in range(1, len(cf)))]
        swap_rows = max(diff) // 2 + 1 if diff else 0
        assert diff == [i for i in range(swap_rows * 2) if i in diff], "swap cells must sit at the top"
        return ([b"".join(pack_rows(g) for g in cf[k][:swap_rows * 2]) for k in range(len(cf))],
                b"".join(pack_rows(g) for g in cf[0][swap_rows * 2:]),
                bytes(int(a) for a in fr[0]["cells"].flatten()), swap_rows)
    # the pre-LOOK-1 3-frame torch: menu_torch.bin only (tools/gen_loading_screen.py reads it)
    sw, st, at, _ = split([f"torch_tall_f{k}" for k in (1, 2, 3)])
    d["legacy_bin"] = b"".join(sw) + st + at + bytes(TORCH_CYCLE)
    d["torch_swap"], d["torch_static"], d["torch_attr"], d["swap_rows"] = split(TORCH_LOOK)
    return d


def emit(d: dict) -> dict:
    os.makedirs(OUT, exist_ok=True)
    n = len(CHARSET)
    sz = {}
    hdr = ("; GENERATED by tools/menu_art.py (Stage 3C C3-5) -- do not hand-edit.\n"
           "; Source: assets/gfx/concept/grid/{} (approved concept round 6).\n")
    # font
    raw = b"".join(d["font"])
    sz["MENU_FONT_BYTES"] = len(raw)
    open(os.path.join(OUT, "menu_font.bin"), "wb").write(raw)
    s = hdr.format("font8x16.grid") + (
        f"; 8x16 menu font, {n} glyphs x 16 B = {len(raw)} B (ASCII -> glyph by range arithmetic, menu1.asm mf_char_e).\n"
        f"; Charset: {''.join(CHARSET)!r}\n"
        "; Glyph = 16 rows x 1 B, MSB-left, col 7 = letter gap; drawn 2 cell-rows tall\n"
        f"; (rows 0-7 top cell, 8-15 bottom cell).  Ink per cell = attr of the cell pair.\n"
        f"MENU_FONT_COUNT  EQU {n}\nMENU_FONT_STRIDE EQU 16\n"
        "\n"
        "menu_font:\n" + db(d["font"], lambda i: f"{ord(CHARSET[i])} {CHARSET[i]!r}") +
        "menu_font_end:\n"
        f"        ASSERT menu_font_end - menu_font == {len(raw)}\n")
    open(os.path.join(OUT, "menu_font.asm"), "w").write(s)
    # title
    raw = b"".join(d["title"])
    idx = {c: i for i, c in enumerate(TITLE_SET)}
    lines = []
    for row, text in TITLE_LINES:
        w = sum(1 if ch == " " else 2 for ch in text)
        col = (32 - w) // 2
        lines.append((row, col, bytes([0xFF if ch == " " else idx[ch] for ch in text]) + b"\xFE"))
    sz["MENU_TITLE_BYTES"] = len(raw) + sum(2 + len(t) for _, _, t in lines)
    open(os.path.join(OUT, "menu_title.bin"), "wb").write(raw)
    s = hdr.format("title16.grid") + (
        f"; Title lettering 'TOME OF / THE DEAD': {len(TITLE_SET)} script glyphs 16x16 x 32 B\n"
        f"; ({len(raw)} B; set {''.join(TITLE_SET)!r}) + 2 line descriptors.\n"
        "; Glyph = 16 rows x 2 B (left byte, right byte), MSB-left; drawn as 2x2 cells: top\n"
        f"; cell row attr ${A_TOP:02X} (white), bottom cell row ${A_BOT:02X} (yellow).\n"
        "; Line descriptor: DEFB row, col ; then glyph indices, $FF = 1-cell gap, $FE = end.\n"
        "; A glyph advances 2 cells.  Lines are centred (col = (32 - width) / 2).\n"
        f"MENU_TITLE_COUNT EQU {len(TITLE_SET)}\nMENU_TITLE_STRIDE EQU 32\n"
        f"MENU_TITLE_ATTR_TOP EQU ${A_TOP:02X}\nMENU_TITLE_ATTR_BOT EQU ${A_BOT:02X}\n\n"
        "menu_title:\n" + db(d["title"], lambda i: f"{TITLE_SET[i]}") + "menu_title_end:\n"
        f"        ASSERT menu_title_end - menu_title == {len(raw)}\n\nmenu_title_lines:\n" +
        "".join(f"        DEFB {r},{c}\n        DEFB " + ",".join(f"${b:02X}" for b in t) + "\n"
                for r, c, t in lines) + "        DEFB $FF               ; end of lines\n"
        "menu_title_lines_end:\n")
    open(os.path.join(OUT, "menu_title.asm"), "w").write(s)
    # torch (RECLAIM-C (d) + LOOK-1): every glyph is in the bank-7 tset_pool; bank 1 keeps the attrs
    sr = d["swap_rows"]
    swap_b = len(d["torch_swap"][0])
    nfr = len(d["torch_swap"])
    st = d["torch_static"]
    six = torch_pool_ix(st)
    fix = [torch_pool_ix(f) for f in d["torch_swap"]]
    fstep = fix[1] - fix[0]
    assert nfr == 2 and all(fix[k] == fix[0] + k * fstep for k in range(nfr)), "menu1 menu_torch: 2 frames, fixed stride"
    tot = len(d["torch_attr"])
    sz["MENU_TORCH_BYTES"] = tot
    open(os.path.join(OUT, "menu_torch.bin"), "wb").write(d["legacy_bin"])
    chk = [(8 * six, st)] + [(8 * fix[k], d["torch_swap"][k]) for k in range(nfr)]

    def check_lines(off, b, tag):
        return "".join("        ASSERT " + " && ".join(f"{{b addr + {off + i + k}}} == ${b[i + k]:02X}" for k in range(8))
                       + f"   ; {tag} cell {i // 8}\n" for i in range(0, len(b), 8))
    s = hdr.format("bigdecor.grid (" + " / ".join(TORCH_LOOK) + "; LOOK-1)") + (
        f"; Animated title torch, 2x4 cells (16x32), drawn at cols {TORCH_COLS[0]} and {TORCH_COLS[1]},\n"
        "; rows 0-3.  Cells row-major (c0,r0),(c1,r0),(c0,r1)...; 8 B per cell.\n"
        f"; LOOK-1: the decor tall torch's RAG flame, fixed attrs (no flame-tip cycle). {nfr} glyph-swap\n"
        f"; frames of the top {sr} cell row(s) ({swap_b} B each), next frame every {TORCH_STEP} menu frames (the\n"
        f"; decor flames' 160 ms); the right torch runs a frame ahead. The lower {4 - sr} rows are static.\n"
        "; RECLAIM-C (d): NO glyph bytes in bank 1 - they are the bank-7 tileset glyphs (the D1 tall\n"
        f"; torch): static = tset_pool[{six}..{six + len(st) // 8 - 1}], frame k = tset_pool[{fix[0]} + {fstep} k ..+{swap_b // 8 - 1}];\n"
        "; menu1 fetches them with ldir7. main.asm runs MENU_TORCH_CHECK tset_pool after the tilesets\n"
        "; (a tileset change that moves / alters them fails the build: rerun this tool).\n"
        f"MENU_TORCH_STEP EQU {TORCH_STEP}\nMENU_TORCH_FRAMES EQU {nfr}\n"
        f"MENU_TORCH_SWAP_ROWS EQU {sr}\nMENU_TORCH_SWAP_BYTES EQU {swap_b}\n"
        f"MENU_TORCH_COL_L EQU {TORCH_COLS[0]}\nMENU_TORCH_COL_R EQU {TORCH_COLS[1]}\n"
        f"MENU_TORCH_STATIC_LEN EQU {len(st)}\nMENU_TORCH_POOL_IX EQU {six}\n"
        f"MENU_TORCH_F0_IX EQU {fix[0]}\nMENU_TORCH_FSTEP_IX EQU {fstep}\n"
        "    MACRO MENU_TORCH_CHECK addr\n" +
        check_lines(8 * six, st, "static") +
        "".join(check_lines(8 * fix[k], d["torch_swap"][k], f"frame {k}") for k in range(nfr)) +
        "    ENDM\n\n"
        "menu_torch_attr:                       ; 2 x 4 cells, row-major (fixed: LOOK-1)\n" +
        db([d['torch_attr'][i:i + 2] for i in range(0, 8, 2)]) +
        "menu_torch_end:\n"
        f"        ASSERT menu_torch_end - menu_torch_attr == {tot}\n")
    open(os.path.join(OUT, "menu_torch.asm"), "w").write(s)
    # sizes
    total = sum(sz.values())
    sz["MENU_ART_BYTES"] = total
    inc = ("; GENERATED by tools/menu_art.py. Byte counts of the menu art includes (bank 1 cold data).\n"
           "; The row-6 ornament reuses ORN_GLYPHS (panel_orn.asm, 0 B extra); hero previews reuse\n"
           "; sprites knight_idle1 / wizard_idle (0 B extra).\n" +
           "".join(f"{k} EQU {v}\n" for k, v in sz.items()))
    open(os.path.join(OUT, "menu_art.inc"), "w").write(inc)
    return sz


# ---- preview + checks, driven from the packed bytes ---------------------------------------
def compose(d: dict, frame: int = 0) -> C.Screen:
    s = C.Screen()
    fmap = {c: i for i, c in enumerate(CHARSET)}
    gl = lambda b: np.array([[(byte >> (7 - i)) & 1 for i in range(8)] for byte in b], bool)

    def text16(col, row, text, attr):
        for i, ch in enumerate(text):
            g = gl(d["font"][fmap[ch]])
            a = attr[i] if isinstance(attr, list) else attr
            s.glyph(col + i, row, g[:8], a)
            s.glyph(col + i, row + 1, g[8:], a)

    for row, text in TITLE_LINES:
        c = (32 - sum(1 if ch == " " else 2 for ch in text)) // 2
        for ch in text:
            if ch == " ":
                c += 1
                continue
            g = np.array([[(b >> (7 - i)) & 1 for b in pair for i in range(8)]
                          for pair in zip(d["title"][TITLE_SET.index(ch)][0::2],
                                          d["title"][TITLE_SET.index(ch)][1::2])], bool)
            for k in (0, 1):
                s.glyph(c + k, row, g[:8, 8 * k:8 * k + 8], A_TOP)
                s.glyph(c + k, row + 1, g[8:, 8 * k:8 * k + 8], A_BOT)
            c += 2
    sr = d["swap_rows"]
    for col in TORCH_COLS:
        for i in range(8):
            r, c = divmod(i, 2)
            b = (d["torch_swap"][frame][i * 8:i * 8 + 8] if r < sr
                 else d["torch_static"][(i - sr * 2) * 8:(i - sr * 2) * 8 + 8])
            a = d["torch_attr"][i]
            s.glyph(col + c, r, gl(b), a)
    orn = open(os.path.join(ROOT, "assets/gfx/panel/panel_orn.asm")).read()
    og = [bytes(int(x.strip().strip("$"), 16) for x in ln.split(";")[0].split("DEFB")[1].split(","))
          for ln in orn.splitlines() if ln.strip().startswith("DEFB") and "orn_" in ln]
    for c in range(32):
        n = 0 if c == 0 else 7 if c == 31 else (3, 4, 5, 6)[c - 14] if 14 <= c <= 17 else (1 if c % 2 else 2)
        s.glyph(c, 6, gl(og[n]), A_ORN)
    sel, norm, key = 0x46, 0x07, 0x45
    text16(2, 8, ">", sel)
    text16(4, 8, "1 START", [key, 0] + [sel] * 5)
    text16(4, 11, "2 HERO: MAGE", [key, 0] + [norm] * 6 + [0x47] * 4)
    text16(4, 14, "3 CONTROLS", [key, 0] + [norm] * 8)
    text16(4, 18, "4 REDEFINE KEYS", [key, 0] + [norm] * 13)
    for name, _lbl, col, row, attr in HEROES:
        fg, solid = C.load_sprite("knight_idle1" if name == "warrior" else "wizard_idle")
        s.sprite(name, col * 8, row * 8, fg, solid, attr)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None)
    a = ap.parse_args()
    d = build()
    sz = emit(d)
    s = compose(d)
    scr = s.to_scr()
    errs, rep = C.validate("menu_c3_5", s, scr, [], range(0))
    # per-cell colour count straight from the screen
    bm, attr = C.decode_scr(scr)
    img = C.render_rgb(bm, attr)
    bad = sum(len({tuple(p) for p in img[r * 8:r * 8 + 8, c * 8:c * 8 + 8].reshape(-1, 3)}) > 2
              for r in range(24) for c in range(32))
    # diff vs concept (only regions this tool draws: rows 0-4 title/torch, 6 orn, 8-19 menu text)
    cbm, cattr = C.decode_scr(open(os.path.join(GRID, "..", "screen_menu.scr"), "rb").read())
    dpx = int((bm[0:40] != cbm[0:40]).sum() + (bm[48:56] != cbm[48:56]).sum()
              + (bm[64:128] != cbm[64:128]).sum() + (bm[136:160] != cbm[136:160]).sum())
    dat = int((attr[[0, 1, 2, 3, 4, 6]] != cattr[[0, 1, 2, 3, 4, 6]]).sum())
    print("sizes:", ", ".join(f"{k}={v}" for k, v in sz.items()))
    print(f"charset ({len(CHARSET)}): {''.join(CHARSET)!r}  title set: {''.join(TITLE_SET)!r}")
    print(f"legality: cells>2 colours = {bad}; validate errors = {errs or 'none'}")
    print(f"diff vs concept screen_menu.scr: bitmap px {dpx} (rows 0-4,6,8-15,17-19; row 16 = 6x8 text, not ours), attrs {dat}")
    print("hero previews (reuse):", "; ".join(f"{n} -> {l} at col {c} row {r} attr ${at:02X}"
                                              for n, l, c, r, at in HEROES))
    print("ornament row 6: reuse orn_glyphs (panel_orn.asm), attr $%02X" % A_ORN)
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        C.save_png(img, os.path.join(a.preview, "menu_c3_5.png"))
        print("preview:", os.path.join(a.preview, "menu_c3_5.png"))
    if errs or bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
