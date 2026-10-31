#!/usr/bin/env python3
"""concept_fonts.py — font round for tools/concept_screen.py (imported by its main()).

6x8 proportional-grid text (42 chars per 256 px), the 8x16 menu font and the 16x16 title,
composed through the same attribute model as every other mock and validated by
concept_screen.validate(). Colour rule for 6-px text: an attribute change may only happen
on an 8-px cell boundary, i.e. every 4 characters (24 px) from a cell-aligned start —
text6() asserts it, and validate() proves 0 clash cells on the result.

Screens: the panel's info line + 2-row log (all four 9+9+6 mocks), the redesigned
inventory page (inventory6.scr/.png) and the main menu (screen_menu.scr/.png).
"""

from __future__ import annotations

import os

import numpy as np

import concept_screen as C
import concept_r4 as R4
import font_tool as FT

GRID, OUT = C.GRID, C.OUT


def load(art) -> None:
    art.f6 = FT.parse(os.path.join(GRID, "font6x8.grid"), 6, 8)
    art.f16 = FT.parse(os.path.join(GRID, "font8x16.grid"), 8, 16)
    art.ft = FT.parse(os.path.join(GRID, "title16.grid"), 16, 16)


def text6(s, col: int, row: int, segments, art, ncells: int | None = None, paper_fill=0x00):
    """Write 6x8 text into one character row starting at cell `col`.
    segments: [(text, attr), ...] laid end to end. Every attr change must fall on a
    multiple of 4 characters from the start (24 px = 3 cells) -> asserted.
    The covered cells are blanked first; ncells (default: what the text needs) are claimed
    with the first segment's attr."""
    total = sum(len(t) for t, _ in segments)
    need = (total * 6 + 7) // 8
    ncells = ncells or need
    assert need <= ncells, (segments, need, ncells)
    blank = np.zeros((8, 8), bool)
    first = segments[0][1]
    for c in range(ncells):
        s.glyph(col + c, row, blank, first if c < need else paper_fill)
    x = col * 8
    k = 0
    for text, attr in segments:
        assert k % 4 == 0 or attr == segments[0][1], f"colour change at char {k}: {segments}"
        c0 = (x + k * 6) // 8
        c1 = (x + (k + len(text)) * 6 - 1) // 8
        for c in range(c0, c1 + 1):
            s.attr[row, c] = attr
            s.bg_attr[row, c] = attr
        for ch in text:
            g = art.f6[ord(ch)]
            px = x + k * 6
            s.bm[row * 8:row * 8 + 8, px:px + 6] = g
            w = s.want[row * 8:row * 8 + 8, px:px + 6]
            w[:] = np.where(g, attr & 0x47, -1)
            k += 1


def text16(s, col: int, row: int, text: str, attr, art):
    """8x16 menu text: 1 cell wide, 2 rows tall per char; attr may be per char (list)."""
    for i, ch in enumerate(text):
        a = attr[i] if isinstance(attr, list) else attr
        g = art.f16.get(ord(ch), art.f16[32])
        s.glyph(col + i, row, g[:8], a)
        s.glyph(col + i, row + 1, g[8:], a)


def title16(s, col: int, row: int, text: str, top_attr: int, bot_attr: int, art):
    """16x16 script title: 2x2 cells per letter, a space is 1 cell; two-tone by cell row."""
    c = col
    for ch in text:
        if ch == " ":
            c += 1
            continue
        g = art.ft[ord(ch)]
        for k in (0, 1):
            s.glyph(c + k, row, g[:8, 8 * k:8 * k + 8], top_attr)
            s.glyph(c + k, row + 1, g[8:, 8 * k:8 * k + 8], bot_attr)
        c += 2


def title_width(text: str) -> int:
    return sum(1 if ch == " " else 2 for ch in text)


# ---------------------------------------------------------------------------
# Panel text in 6x8 (info line: row 20, 42 chars; log: rows 22-23, cols 0-23 = 32 chars)
# ---------------------------------------------------------------------------

def panel_text(s, art, name: str, cost: str, rest: str, log2: str, log1: str):
    """Info line: NAME (12 chars, white) | COST (4 chars, cyan) | rest (26 chars, yellow)."""
    segs = [(f"{name:<12.12s}", 0x47), (f"{cost:<4.4s}", 0x45), (f"{rest:<26.26s}", 0x46)]
    text6(s, 0, 20, segs, art, 32)
    assert len(log2) <= 32 and len(log1) <= 32, (log2, log1)
    text6(s, 0, 22, [(f"{log2:<32s}", 0x07)], art, 24)
    text6(s, 0, 23, [(f"{log1:<32s}", 0x47)], art, 24)


PANEL6 = {
    "D1": ("FIREBOLT", "3MP", "RANGE 12  BURST: ADJ +YOU",
           "THE GOBLIN ATTACKS AND MISSES.", "YOU CAST FIREBOLT. IT FLIES!"),
    "D4": ("POWER STRIKE", "3MP", "REACH  HIT+2  DAMAGE X2",
           "THE OGRE WARLORD ROARS!", "YOU STRIKE THE OGRE. (12)"),
    "D7": ("DAGGERS X6", "", "RANGE 6  1D4+2  RECOVERED",
           "THE DEATH KNIGHT PARRIES! (0)", "YOU THROW A DAGGER AT THE KNIGHT"),
    "D8": ("LIGHTNING", "5MP", "RANGE 28  BOUNCE 2  PIERCES",
           "THE TOME WHISPERS. -1 HP.", "LIGHTNING HITS THE ARCHMAGE!"),
}


def apply_panel6(s, art, depth: str):
    panel_text(s, art, *PANEL6[depth])


# ---------------------------------------------------------------------------
# Inventory page, redesigned for 6x8 text
# ---------------------------------------------------------------------------

def inventory6(art):
    s = C.Screen()
    I16 = {**art.ic16, **art.ic16b}
    O = art.orn
    # row 0: title bar; row 1: ornament band
    text6(s, 0, 0, [("INVENTORY   ", 0x46), ("MAGE    D1  TURN 341  BAG 9/20", 0x07)], art, 32)
    for c in range(32):
        n = "orn_cap_l" if c == 0 else "orn_cap_r" if c == 31 else \
            ("orn_wing_l", "orn_skull_l", "orn_skull_r", "orn_wing_r")[c - 14] if 14 <= c <= 17 \
            else ("orn_link" if c % 2 else "orn_bar")
        s.glyph(c, 1, O[n]["bm"], 0x0F)
    # worn column: cols 0-12. Label row 2, slots at rows 3, 6, 9, 12
    text6(s, 0, 2, [("WORN", 0x46)], art, 3)
    worn = [("staff", 0x46, "EMBER STAFF", "1D6  SPELLS +1"),
            ("robe", 0x43, "ROBE OF WARDS", "DEF 1  FIRE R"),
            ("hood", 0x43, "HOOD", "DEF 1"),
            ("ring", 0x46, "RING OF MANA", "MP REGEN X2")]
    for k, (ic, a, nm, st) in enumerate(worn):
        r = 3 + 3 * k
        s.glyph(0, r, I16[ic]["bm"], a)
        text6(s, 2, r, [(nm, 0x47)], art, 11)
        text6(s, 2, r + 1, [(st, 0x07)], art, 11)
    # bag: cols 14-31, 5x4 slots of 16x16 at pitch 3, rows 3..13
    text6(s, 14, 2, [("BAG", 0x46)], art, 3)
    bag = [[("meat", 0x43, 2), ("apple", 0x42, 3), ("carrot", 0x46, 1), ("pear", 0x44, 1),
            ("cheese", 0x46, 2)],
           [("potion", 0x42, 2), ("potion", 0x45, 1), ("scroll", 0x47, 1), ("book", 0x43, 1),
            ("sword", 0x47, 1)]] + [[("empty", 0x01, 0)] * 5] * 2
    for j, rowl in enumerate(bag):
        for i, (ic, a, q) in enumerate(rowl):
            c, r = 14 + 3 * i, 3 + 3 * j
            cursor = (i, j) == (1, 0)
            s.glyph(c, r, I16[ic]["bm"], C.sel(a) if cursor else a)
            if q > 1:
                text6(s, c + 2, r + 1, [(str(q), 0x47)], art, 1)
    # stats block rows 15-17 (one colour per row)
    text6(s, 0, 15, [("HP 18/22  MP 5/12  ATK 3  DEF 2  HIT +1", 0x47)], art, 32)
    text6(s, 0, 16, [("RESIST:  FIRE R  COLD -  DARK -  DRAIN -", 0x07)], art, 32)
    text6(s, 0, 17, [("FOOD:   ", 0x07), ("HUNGRY  ", 0x46), ("-1 PER 6 TURNS  KEY: NO", 0x07)],
          art, 32)
    # selected item: 24x24 icon + 8x16 name + 6x8 description (rows 19-21)
    s.glyph(0, 19, art.ic24["apple24"]["bm"], 0x42)
    text16(s, 4, 19, "APPLE X3", 0x42, art)
    text6(s, 13, 19, [("FOOD  +4  ", 0x46)], art, 19)
    text6(s, 13, 20, [("STACKS TO 9", 0x07)], art, 19)
    text6(s, 4, 21, [("A CRISP RED APPLE. QUICK SLOT: 7", 0x07)], art, 28)
    # action strip row 22: 8-char verb fields (cell-aligned); selected verb on blue paper
    verbs = [("  EAT   ", C.A_GREY_SEL | 0x40), ("  QUICK ", 0x07), ("  DROP  ", 0x07)]
    text6(s, 4, 22, verbs, art, 18)
    text6(s, 0, 23, [("FIRE:ACT  FIRE+DOWN:BACK  QAOP:MOVE  I:OUT", 0x05)], art, 32)
    return s


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def menu(art):
    s = C.Screen()
    # title: TOME OF / THE DEAD, script 16x16, two-tone (white over yellow), centred
    for r, line in ((1, "TOME OF"), (3, "THE DEAD")):
        title16(s, (32 - title_width(line)) // 2, r, line, 0x47, 0x46, art)
    C.place_big(s, 2, 0, art.big["torch_tall_f1"])
    C.place_big(s, 28, 0, art.big["torch_tall_f1"])
    text6(s, 4, 5, [("A ROGUELIKE FOR THE ZX SPECTRUM 128K", 0x05)], art, 27)
    for c in range(32):
        n = "orn_cap_l" if c == 0 else "orn_cap_r" if c == 31 else \
            ("orn_wing_l", "orn_skull_l", "orn_skull_r", "orn_wing_r")[c - 14] if 14 <= c <= 17 \
            else ("orn_link" if c % 2 else "orn_bar")
        s.glyph(c, 6, art.orn[n]["bm"], 0x0D)
    sel, norm, key = 0x46, 0x07, 0x45
    text16(s, 2, 8, ">", sel, art)
    text16(s, 4, 8, "1 START", [key, 0] + [sel] * 5, art)
    text16(s, 4, 11, "2 HERO: MAGE", [key, 0] + [norm] * 6 + [0x47] * 4, art)
    text16(s, 4, 14, "3 CONTROLS", [key, 0] + [norm] * 8, art)
    text6(s, 0, 16, [("    ", 0x07), (" KEYS   ", 0x0F | 0x40), ("KEMPSTON SINCLAIR 1 SINCLAIR 2", 0x07)],
          art, 32)
    text16(s, 4, 18, "4 REDEFINE KEYS", [key, 0] + [norm] * 13, art)
    text6(s, 4, 20, [("UP Q  DOWN A  LEFT O  RIGHT P  FIRE M", 0x05)], art, 28)
    kf, ks = C.load_sprite("knight_idle1")
    s.sprite("warrior", 21 * 8, 9 * 8, kf, ks, 0x07)
    wf, ws = C.load_sprite("wizard_idle")
    s.sprite("mage", 25 * 8, 9 * 8, wf, ws, 0x45)
    text6(s, 0, 22, [("PRESS 1-4 OR FIRE  -  JOYSTICK OK", 0x47)], art, 32)
    text6(s, 0, 23, [("V0.2 CONCEPT  (C) 2026 TOME OF THE DEAD", 0x07)], art, 32)
    return s


def write_all(art) -> tuple[list[str], list[str]]:
    errs, rep = [], []
    for fn, mk in (("inventory6", lambda: inventory6(art)), ("screen_menu", lambda: menu(art))):
        s = mk()
        scr = s.to_scr()
        open(os.path.join(OUT, fn + ".scr"), "wb").write(scr)
        C.save_png(s.rgb_image(), os.path.join(OUT, fn + ".png"))
        e, r = C.validate(fn, s, scr, [], range(0))
        errs += [f"{fn}: {x}" for x in e]
        rep += r
    return errs, rep
