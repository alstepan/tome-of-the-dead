#!/usr/bin/env python3
"""XP-BAR (user 2026-11-18): the 8-px XP progress bar in panel cell (30, 19) (src/sv_r2.asm xp_bar: R2, boot-installed; drawn by
item_depth's tail depth_tail; PD_DEPTH set by xp_level on every XP gain / level-up and by panel_init).
Release build (-DDEBUG_KIT=0), PROTO room A, monsters parked.

  X1  new game: XP 0 -> fill 0 (frame lines 1 / 6 = $FF, fill lines 2..5 = 0, lines 0 / 7 blank), attr $46
  X2  XP 22 of L1's 44 -> 4 px; XP 43 -> 7 px  (floor(8 * XP / 44))
  X3  XP 77 (level-up to 2 by xp_turn) -> LVL 2, fill floor(8 * (77 - 44) / 66) = 4 px  (after the level-up)
  X4  XP 1265 (several levels at once) -> LVL 9, full bar (8 px)
  X5  panel_init (a new level) keeps the bar; (30, 19) attr stays $46, the level digit cell (31, 19) is not touched
  C   cost of item_depth (incl. depth_tail -> far6 key_pan) and of xp_bar alone
Run: ZRCP_PORT=<port> python3 tests/xpbar.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game_lib  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, stand_y, attr_at, cell_bytes  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
COL, ROW = S["XPB_COL"], S["XPB_ROW"]
XPN = [44, 110, 220, 374, 550, 770, 1012, 1265]
EF_ACTIVE, EF_PLAYER = 1, 2
STUB = S["LOWRAM_END_3B"]
NOWHERE = 7


def fill_for(xp, lvl):
    if lvl >= 9:
        return 8
    prev = XPN[lvl - 2] if lvl > 1 else 0
    return min(8, 8 * (xp - prev) // (XPN[lvl - 1] - prev))


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

    def bar():
        f = p.frame()
        b = cell_bytes(f, COL, ROW)
        fill = bin(b[2]).count("1")
        ok = (b[1] == 0xFF and b[6] == 0xFF and b[0] == 0 and b[7] == 0 and len(set(b[2:6])) == 1
              and b[2] == (0xFF00 >> fill) & 0xFF)
        return fill, ok, attr_at(f, COL, ROW), cell_bytes(f, COL + 1, ROW)

    def lvl():
        return p.rb("LVL")

    def gain(xp):
        p.wmem(S["XP"], [xp & 255, xp >> 8])
        p.wb("XP_UP", 1)
        p.turn("WAIT")
        p.tick(6)

    f0 = bar()
    check("X1 new game: XP 0 -> empty bar (frame only), attr $46", f0[:3] == (0, True, 0x46), f0)
    gain(22)
    b = bar()
    check("X2a XP 22 of 44 -> 4 px", (lvl(), b[0], b[1], b[2]) == (1, 4, True, 0x46), (lvl(), b))
    gain(43)
    b = bar()
    check("X2b XP 43 of 44 -> 7 px", (lvl(), b[0], b[1]) == (1, 7, True), (lvl(), b))
    gain(77)
    b = bar()
    check("X3 XP 77: level 2, fill floor(8 * 33 / 66) = 4 px", (lvl(), b[0], b[1]) == (2, fill_for(77, 2), True), (lvl(), b))
    gain(110)
    b = bar()
    check("X3b XP 110 = the L3 threshold exactly: level 3, empty bar", (lvl(), b[0], b[1]) == (3, 0, True), (lvl(), b))
    gain(1265)
    b = bar()
    check("X4 XP 1265: level 9 (several at once), full 8 px", (lvl(), b[0], b[1]) == (9, 8, True), (lvl(), b))
    lv = cell_bytes(p.frame(), S["LVL_COL"], ROW)
    check("X5 the level digit cell (31, 19) is a '9' glyph, attr $46, not the bar",
          any(lv) and attr_at(p.frame(), S["LVL_COL"], ROW) == 0x46 and lv != cell_bytes(p.frame(), COL, ROW), lv.hex())
    # costs
    p.z.cmd("set-breakpoint 5")
    ok = p.code([0x21] + w16(S["PANEL_DIRTY"]) + [0xCD] + w16(S["item_depth"]))
    t_all = p.tstates
    ok2 = p.code([0xCD] + w16(S["xp_bar"]))
    t_xp = p.tstates
    print(f"[info] item_depth (incl. depth_tail -> far6 key_pan + xp_bar + 2 pmark_rect) {t_all} T; xp_bar {t_xp} T", flush=True)
    check("C1 item_depth <= 9k T, xp_bar <= 1.5k T", ok and ok2 and t_all <= 9000 and t_xp <= 1500, (t_all, t_xp))


if __name__ == "__main__":
    sys.exit(main())
