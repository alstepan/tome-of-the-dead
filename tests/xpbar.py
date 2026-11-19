#!/usr/bin/env python3
"""XP-BAR2 (user 2026-11-19; XP-BAR 2026-11-18 was 8 px at (30, 19)): the 23-px XP progress bar on row 21, cols 25..27
(src/sv_r2.asm xp_bar + R5 sv_r5.asm xpb_draw, boot-installed; drawn by item_depth's tail depth_tail; PD_DEPTH set by
xp_level on every XP gain / level-up and by panel_init), the level digit at (24, 21), "Dn" at (28-29, 21), the two panel
keys at (30-31, 18 / 19), and the >= 1-px gaps between the row-21 bars and their neighbours (FOOD bar 31 px: R5 fbar_gap).
Release build (-DDEBUG_KIT=0), PROTO room A, monsters parked.

  X1  new game: XP 0 -> fill 0 (frame lines 1 / 6 = FF FF FE, lines 2..5 = the end caps 80 00 02, lines 0 / 7 blank), $46
  X2  XP 11 / 22 / 43 of L1's 44 -> 5 / 11 / 22 px  (floor(23 * XP / 44)); crops build/xpbar_row21_{xp0,xp25,full}.png
  X3  XP 77 (level-up to 2 by xp_turn) -> LVL 2, fill floor(23 * 33 / 66) = 11 px; XP 110 -> L3, empty
  X4  XP 1265 (several levels at once) -> LVL 9, full bar (23 px, bit 0 of col 27 clear)
  X5  the level digit (24, 21) is a glyph, attr $46; "Dn" (28-29, 21) attr $47; the retired (30, 19) cell is blank
  K1  both keys held: cyan glyph at (30-31, 18) attr $45, magenta at (30-31, 19) attr $43; none held: blank, attr $47
  G1  gaps on row 21 (FOOD full, word HUNGRY = the longest): FOOD bar col 18 bit 0 clear (cap at bit 1), word end ->
      level digit, digit -> bar (col 25 bit 7), bar -> "D" (col 27 bit 0); writes build/xpbar_row21.png (the crop)
  G2  FLASH set on (24..29, 21) (a tutorial BARS pointer) survives the digit / bar / Dn redraws (none writes an attr)
  C   cost of item_depth (incl. depth_tail -> far6 key_pan + xp_bar + xpb_draw) at a 22-px fill and at L9
Run: ZRCP_PORT=<port> python3 tests/xpbar.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game_lib  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, stand_y, attr_at, cell_bytes, BUILD_DIR  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
COL, ROW = S["XPB_COL"], S["STAT_ROW"]
NC = S["XPB_CELLS"]
PX = S["XPB_PX"]
XPN = [44, 110, 220, 374, 550, 770, 1012, 1265]
EF_ACTIVE, EF_PLAYER = 1, 2
NOWHERE = 7
LF_KEYC, LF_KEYM = 0x40, 0x80
PD_DEPTH, PD_FOOD = 0x80, 0x04
HS_HUNGRY = 2


def fill_for(xp, lvl):
    if lvl >= 9:
        return PX
    prev = XPN[lvl - 2] if lvl > 1 else 0
    return min(PX, PX * (xp - prev) // (XPN[lvl - 1] - prev))


def mask(fill):
    m = ((1 << fill) - 1) << (NC * 8 - fill)
    return [(m >> (8 * (NC - 1 - i))) & 0xFF for i in range(NC)]


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] xpbar needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"xpbar: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    p.boot(K_KNIGHT)
    room = p.rb("CUR_ROOM")
    for sl in range(1, 16):
        e = p.ent(sl)
        if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
            p.set_ent(sl, ROOM=NOWHERE)
    p.set_ent(0, X=12, Y=stand_y(1, 6), PX=96, PY=stand_y(1, 6) * 8, MODE=0, ROOM=room,
              FLAGS=EF_ACTIVE | EF_PLAYER, REACT=0, FLT=0, HIT=0, HP=60, MAXHP=60)
    p.tick(3)

    def bar(want):
        """(shape ok for a `want`-px fill: frame FF FF FE on lines 1 / 6, mask | the end caps (bit 7 of col 25, bit 1 of
        col 27) on lines 2..5, lines 0 / 7 blank; the 3 attrs). Fills 0 / 1 and 22 / 23 draw the same (the caps)."""
        f = p.frame()
        cells = [cell_bytes(f, COL + i, ROW) for i in range(NC)]
        line = [[c[ln] for c in cells] for ln in range(8)]
        frame = [0xFF] * (NC - 1) + [0xFE]
        fill = [b | c for b, c in zip(mask(want), [0x80] + [0] * (NC - 2) + [0x02])]
        ok = (line[0] == [0] * NC and line[7] == [0] * NC and line[1] == frame and line[6] == frame
              and line[2] == line[3] == line[4] == line[5] == fill)
        return ok, tuple(attr_at(f, COL + i, ROW) for i in range(NC)), [hex(x) for x in line[2]]

    def crop(tag):
        try:
            from PIL import Image
            full = Path(BUILD_DIR) / "xpbar_screen.png"
            game_lib.frame_png(p.frame(), str(full), scale=4)
            Image.open(full).crop((0, ROW * 32, 1024, ROW * 32 + 32)).save(Path(BUILD_DIR) / f"xpbar_row21_{tag}.png")
        except ImportError:
            pass

    def lvl():
        return p.rb("LVL")

    def gain(xp):
        p.wmem(S["XP"], [xp & 255, xp >> 8])
        p.wb("XP_UP", 1)
        p.turn("WAIT")
        p.tick(6)

    gold = (0x46,) * NC
    b = bar(0)
    check("X1 new game: XP 0 -> empty 23-px box (FF FF FE frame, the end caps), attrs $46", b[:2] == (True, gold), b)
    crop("xp0")
    gain(11)
    b = bar(5)
    check("X2 XP 11 of 44 -> 5 px (~25%)", (lvl(), b[0]) == (1, True), (lvl(), b))
    crop("xp25")
    gain(22)
    b = bar(11)
    check("X2a XP 22 of 44 -> 11 px", (lvl(), b[0], b[1]) == (1, True, gold), (lvl(), b))
    gain(43)
    b = bar(22)
    check("X2b XP 43 of 44 -> 22 px", (lvl(), b[0]) == (1, True), (lvl(), b))
    gain(77)
    b = bar(fill_for(77, 2))
    check("X3 XP 77: level 2, fill floor(23 * 33 / 66) = 11 px", (lvl(), b[0]) == (2, True), (lvl(), b))
    gain(110)
    b = bar(0)
    check("X3b XP 110 = the L3 threshold exactly: level 3, empty bar", (lvl(), b[0]) == (3, True), (lvl(), b))
    gain(1265)
    b = bar(PX)
    check("X4 XP 1265: level 9 (several at once), full 23 px", (lvl(), b[0]) == (9, True), (lvl(), b))
    crop("full")
    fr = p.frame()
    lv = cell_bytes(fr, S["LVL_COL"], ROW)
    dn = [cell_bytes(fr, S["DEPTH_COL"] + i, ROW) for i in range(2)]
    check("X5 level digit (24, 21) a glyph attr $46; Dn (28-29, 21) attr $47; (30, 19) blank",
          any(lv) and attr_at(fr, S["LVL_COL"], ROW) == 0x46 and all(any(c) for c in dn)
          and attr_at(fr, S["DEPTH_COL"], ROW) == attr_at(fr, S["DEPTH_COL"] + 1, ROW) == 0x47
          and not any(cell_bytes(fr, 30, 19)), (lv.hex(), [c.hex() for c in dn], attr_at(fr, S["DEPTH_COL"], ROW)))

    # K1: the panel keys beside the BAG slot
    def keys():
        fr = p.frame()
        return [(attr_at(fr, S["KEY_PAN_COL"] + c, S["KEY_PAN_ROW"] + r), any(cell_bytes(fr, S["KEY_PAN_COL"] + c, S["KEY_PAN_ROW"] + r)))
                for r in range(2) for c in range(2)]
    fl = p.rb("LVL_FLAGS")
    p.wb("LVL_FLAGS", fl | LF_KEYC | LF_KEYM)
    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | PD_DEPTH)
    p.tick(3)
    k = keys()
    check("K1a both keys held: cyan (30-31, 18) $45, magenta (30-31, 19) $43",
          k == [(0x45, True), (0x45, True), (0x43, True), (0x43, True)], k)
    p.wb("LVL_FLAGS", fl & ~(LF_KEYC | LF_KEYM) & 0xFF)
    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | PD_DEPTH)
    p.tick(3)
    k = keys()
    check("K1b no key: 4 blank cells, attr $47", k == [(0x47, False)] * 4, k)

    # G1: gaps, FOOD full + the longest word (HUNGRY), HP / MP full, XP full (L9)
    p.wb("FOOD", 100)
    p.wb("HSTAGE", HS_HUNGRY)
    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | PD_FOOD | PD_DEPTH)
    p.tick(4)
    fr = p.frame()

    def colbits(col, bit):
        return any(b & (1 << bit) for b in cell_bytes(fr, col, ROW))
    fb = cell_bytes(fr, S["FOOD_BAR_COL"] + 3, ROW)
    word_last = max((c * 8 + 7 - bit for c in range(S["HUNGER_COL"], S["LVL_COL"]) for bit in range(8) if colbits(c, bit)), default=-1)
    dig = [8 * S["LVL_COL"] + 7 - bit for bit in range(8) if colbits(S["LVL_COL"], bit)]
    g = {"food_b0": colbits(S["FOOD_BAR_COL"] + 3, 0), "food_cap_b1": all(x & 2 for x in fb[1:7]),
         "word_b7": colbits(S["HUNGER_COL"], 7), "word_end_x": word_last, "digit_x": (min(dig), max(dig)) if dig else None,
         "bar_b7": colbits(COL, 7), "bar_end_b0": colbits(COL + NC - 1, 0), "d_b7": colbits(S["DEPTH_COL"], 7)}
    ok = (not g["food_b0"] and g["food_cap_b1"] and g["word_b7"] and dig and word_last < min(dig) - 1
          and max(dig) < 8 * COL - 1 and g["bar_b7"] and not g["bar_end_b0"])
    check("G1 row 21 gaps: FOOD bar 31 px (bit 0 clear, cap bit 1) / word -> digit / digit -> XP bar / XP bar -> D", ok, g)
    try:
        from PIL import Image
        full = Path(BUILD_DIR) / "xpbar_screen.png"
        game_lib.frame_png(fr, str(full), scale=4)
        img = Image.open(full)
        crop = img.crop((0, ROW * 8 * 4, 256 * 4, (ROW + 1) * 8 * 4))
        crop.save(Path(BUILD_DIR) / "xpbar_row21.png")
        print(f"[info] row-21 crop: {Path(BUILD_DIR) / 'xpbar_row21.png'}", flush=True)
    except ImportError:
        print("[info] no Pillow: no PNG", flush=True)

    # G2: a tutorial BARS pointer's FLASH (bit 7, tt_ptr) on cols 24..29 survives the level digit / bar / Dn redraws
    base = S["SCREEN_ATTR"] + ROW * 32
    for c in range(S["LVL_COL"], S["DEPTH_COL"] + 2):
        p.wb(base + c, p.rb(base + c) | 0x80)
    p.wb("LVL_SH", 0xFF)                       # the level digit redraws (icon_poll: LVL != LVL_SH)
    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | PD_DEPTH)
    p.tick(4)
    fl = [p.rb(base + c) for c in range(S["LVL_COL"], S["DEPTH_COL"] + 2)]
    check("G2 FLASH on (24..29, 21) survives the digit / XP bar / Dn redraws", all(a & 0x80 for a in fl) and p.rb("LVL_SH") == lvl()
          and not p.rb("PANEL_DIRTY") & PD_DEPTH, [hex(a) for a in fl])
    for c in range(S["LVL_COL"], S["DEPTH_COL"] + 2):
        p.wb(base + c, p.rb(base + c) & 0x7F)
    t_l9 = cost(p)
    p.wb("LVL", 1)                             # the worst divide: 22 px (no turn: the costs run code directly)
    p.wmem(S["XP"], [43, 0])
    t_mid = cost(p)
    print(f"[info] item_depth (depth_tail -> far6 key_pan + xp_bar + xpb_draw + 2 pmark_rect): 22-px fill {t_mid} T, L9 {t_l9} T",
          flush=True)
    check("C1 item_depth <= 7k T (worst fill)", 0 < t_mid <= 7000 and 0 < t_l9 <= 7000, (t_mid, t_l9))


def cost(p):
    p.z.cmd("set-breakpoint 5")
    ok = p.code([0x21] + w16(S["PANEL_DIRTY"]) + [0xCD] + w16(S["item_depth"]))
    return p.tstates if ok else -1


if __name__ == "__main__":
    sys.exit(main())
