#!/usr/bin/env python3
"""HOW TO PLAY (INSTR1) page data -> asm for the build (stdlib only).

THE spec of the two pages: the text rows come from docs/design/instructions_screen.txt
(the approved wording, read verbatim), the attribute fills and the icon placements are
the PAGES table below (the render spec's ATTRS / ICONS sections as data). The mockups
(tools/gen_instr_mock.py) render from the same table, and tests/instr.py compares the
emulator's screen with that render byte for byte.

Output (per page n = 1, 2; TUT0-T2 dropped the old items/tips page): OUTDIR/instr_p<n>.inc, the page image src/instr_ovl.asm
assembles at INSTR_DATA (docs/memory-map.md "INSTR1"):
  text   24 rows; a byte 32..127 = that char, 1..31 = that many spaces, 0 = end of row
         (trailing spaces dropped; the row is printed from x = 0 by print6)
  icons  records IK_* kind, char row, col, DW arg (0 = end): IK_I16 arg = the logical
         icons16 index (R6 ic_scr), IK_BAR / IK_GLY arg = the vdata label (bank-3 pblit /
         glyph8), IK_TILE arg = a common tile id (TILE_GLYPHS)
  attrs  run-length pairs (count 1..255, attr) covering the 768 cells, 0 = end; the
         icon cells carry the icon's own attr (bar / label / tile data, or the i16 attr)
Usage: tools/instr_pack.py [OUTDIR]   (default build/text)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(ROOT, "assets", "gfx")
SPEC_TXT = os.path.join(ROOT, "docs", "design", "instructions_screen.txt")
ROWS, COLS, CHARS = 24, 32, 42


def _rows_fill(rows, c0, c1, a):
    return [(r, c0, c1, a) for r in rows]


P1_FIELDS = (8, 9, 10, 11, 12, 13, 15)          # the STICK / ACTION / KEY rows
PAGES = {
    1: {
        "fills": (_rows_fill([0], 0, 31, 0x46) + _rows_fill([2, 3, 4, 5], 0, 31, 0x47)
                  + _rows_fill([7], 0, 31, 0x06)
                  + [f for r in P1_FIELDS for f in ((r, 0, 8, 0x45), (r, 9, 23, 0x47), (r, 24, 31, 0x46))]
                  + _rows_fill([14], 9, 31, 0x47)
                  + _rows_fill([16], 3, 23, 0x47) + _rows_fill([16], 24, 31, 0x46)
                  + _rows_fill([17], 3, 31, 0x07)
                  + _rows_fill([18], 3, 31, 0x47) + _rows_fill([19], 3, 31, 0x07)
                  + _rows_fill([20], 0, 31, 0x45) + _rows_fill([21, 22], 0, 31, 0x05) + _rows_fill([23], 0, 31, 0x46)),
        # (kind, name / tile id, row, col[, attr for i16])
        "icons": [("bar", "icon_bag", 16, 0), ("bar", "icon_sword", 18, 0),
                  ("tile", 15, 4, 30), ("tile", 16, 4, 31), ("tile", 17, 5, 30), ("tile", 18, 5, 31)],
    },
    2: {
        "fills": (_rows_fill([0, 23], 0, 31, 0x46) + _rows_fill([2, 12], 0, 31, 0x06)
                  + _rows_fill([3, 4, 7, 8, 13, 14, 17, 18], 0, 31, 0x47)
                  + _rows_fill([5, 6, 9, 10, 15, 16], 0, 31, 0x45)
                  + _rows_fill([20, 21, 22], 0, 31, 0x05)),
        "icons": [("i16", "h_king", 3, 0, 0x07), ("i16", "a_silk", 3, 16, 0x07),
                  ("i16", "a_grave", 5, 0, 0x07), ("i16", "w_cleaver", 5, 16, 0x07),
                  ("i16", "w_bone", 7, 0, 0x06), ("i16", "c_scarab", 7, 16, 0x06),
                  ("i16", "c_grave", 9, 0, 0x06), ("i16", "h_mirror", 9, 16, 0x07),
                  ("i16", "c_might", 13, 0, 0x06), ("i16", "c_ward", 13, 16, 0x06),
                  ("i16", "c_fire", 15, 0, 0x06), ("i16", "c_mana", 15, 16, 0x06),
                  ("i16", "c_plenty", 17, 0, 0x06)],
    },
}


def rd(p):
    return open(os.path.join(G, p)).read()


def hexes(txt):
    return [int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]{2})", re.sub(r";[^\n]*", "", txt))]


def bytes_after(txt, label, n):
    """First n DEFB bytes after `label:`."""
    return hexes(txt.split(label + ":", 1)[1])[:n]


def rows(page):
    """The 24 text rows of a page, verbatim from the render spec."""
    out, on = [], False
    for ln in open(SPEC_TXT).read().split("\n"):
        if ln.startswith("==="):
            on = ln.startswith("=== PAGE %d ROWS" % page)
            continue
        if on:
            out.append(ln)
    assert len(out) == ROWS, (page, len(out))
    return out


def i16_logical(name):
    """Logical icons16 index (= the number in icons16.asm's table comment; ic_find maps it)."""
    m = re.search(r"^;\s*(\d+) %s\s" % re.escape(name), rd("icons/icons16.asm"), re.M)
    assert m, name
    return int(m.group(1))


def icon_attrs(ic):
    """[(row, col, attr)] the icon leaves on its cells (what the game's draw writes)."""
    kind, arg, r, c = ic[:4]
    if kind == "bar":
        a = bytes_after(rd("panel/panel_icons.asm"), arg, 54)[48:54]
        return [(r + i // 3, c + i % 3, a[i]) for i in range(6)]
    if kind == "label":
        return [(r, c, bytes_after(rd("panel/panel_icons.asm"), arg, 9)[8])]
    if kind == "tile":
        return [(r, c, bytes_after(rd("tiles/tiles_common.asm"), "tiles_common_attrs", 32)[arg])]
    return [(r + i // 2, c + i % 2, ic[4]) for i in range(4)]


def check_icons(page):
    """Static asserts: (a) no text char overlaps an i16 icon's pixels; (b) i16 attr == items.txt INK."""
    items = open(os.path.join(ROOT, "src", "items.txt")).read()
    rr = rows(page)
    for ic in PAGES[page]["icons"]:
        if ic[0] != "i16":
            continue
        _, name, r, c, a = ic
        x0, x1 = 8 * c, 8 * c + 15
        for k in range(CHARS):
            if 6 * k + 5 >= x0 and 6 * k <= x1:
                for rw in (r, r + 1):
                    ch = rr[rw][k] if k < len(rr[rw]) else " "
                    assert ch == " ", (page, name, rw, k, ch)
        m = re.search(r"^IT_%s\s*\|[^|]*\|\s*\$([0-9A-Fa-f]{2})\s*\|" % name.upper(), items, re.M)
        if m:
            assert int(m.group(1), 16) == a, (name, m.group(1), a)
        elif page == 2:
            raise AssertionError("no IT_ row for " + name)


def attr_grid(page):
    at = [[0] * COLS for _ in range(ROWS)]
    for r, c0, c1, a in PAGES[page]["fills"]:
        for c in range(c0, c1 + 1):
            at[r][c] = a
    for ic in PAGES[page]["icons"]:
        for r, c, a in icon_attrs(ic):
            at[r][c] = a
    return at


def enc_row(s):
    s = s.rstrip(" ")
    assert len(s) <= CHARS, s
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == " ":
            j += 1
        n = j - i
        if n >= 2:
            while n:
                k = min(n, 31)
                out.append(k)
                n -= k
            i = j
            continue
        assert 32 <= ord(s[i]) < 128, s
        out.append(ord(s[i]))
        i += 1
    return out + [0]


def rle(flat):
    out, i = [], 0
    while i < len(flat):
        j = i
        while j < len(flat) and flat[j] == flat[i] and j - i < 255:
            j += 1
        out += [j - i, flat[i]]
        i = j
    return out


IK = {"i16": "IK_I16", "bar": "IK_BAR", "label": "IK_GLY", "tile": "IK_TILE"}


def emit(page):
    L = ["; GENERATED by tools/instr_pack.py from docs/design/instructions_screen.txt",
         "; + its PAGES table: do not edit. Page %d image (src/instr_ovl.asm in_page)." % page,
         "; text: 32..127 = char, 1..31 = spaces, 0 = end of row (24 rows)"]
    n = 0
    for r, s in enumerate(rows(page)):
        b = enc_row(s)
        n += len(b)
        L.append("                DB   %s   ; %02d %s" % (", ".join(str(x) for x in b), r, s.rstrip()))
    L.append("; icons: kind, row, col, DW arg; 0 = end")
    for ic in PAGES[page]["icons"]:
        kind, arg, r, c = ic[:4]
        if kind == "i16":
            val, cm = str(i16_logical(arg)), arg + " attr $%02X (from the attrs below)" % ic[4]
        elif kind == "tile":
            val, cm = str(arg), "common tile %d" % arg
        else:
            val, cm = arg, "vdata (bank 1, virtual)"
        L.append("                DB   %s, %d, %d" % (IK[kind], r, c))
        L.append("                DW   %s   ; %s" % (val, cm))
    L.append("                DB   0")
    flat = [a for row in attr_grid(page) for a in row]
    pairs = rle(flat)
    L.append("; attrs: (count, attr) runs over 768 cells, 0 = end (%d B)" % (len(pairs) + 1))
    for i in range(0, len(pairs), 16):
        L.append("                DB   " + ", ".join("$%02X" % x for x in pairs[i:i + 16]))
    L.append("                DB   0")
    assert sum(pairs[0::2]) == ROWS * COLS
    return "\n".join(L) + "\n", n, len(pairs) + 1


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "text")
    os.makedirs(out, exist_ok=True)
    rep = []
    for p in (1, 2):
        check_icons(p)
        txt, nt, na = emit(p)
        path = os.path.join(out, "instr_p%d.inc" % p)
        if not os.path.exists(path) or open(path).read() != txt:
            open(path, "w").write(txt)
        rep.append("p%d text %d B attrs %d B" % (p, nt, na))
    print("instr_pack: " + ", ".join(rep) + " -> " + out)


if __name__ == "__main__":
    main()
