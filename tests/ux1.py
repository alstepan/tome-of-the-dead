#!/usr/bin/env python3
"""UX-POLISH (UX1, docs/design/ux_polish.md §9 "New") + the ITEM-INFO bag rows (item_info.md §6).
Release build (DEBUG_KIT=0); PROTO room A, real play unless noted. `code` = a stub run through
tests/proj3.T.code (interrupts off, a private stack): used where a real pickup would need a level
walk; its results are poked back into a fresh game for the page part.

  M1  menu row 10 pointer while the tutorial is offered (es_go = ts_choice); blank once it is gone
  U1  FOOD 9 (WEAK): word cells (the ink ones of 19-23) $C2, bar 15-18 $42; FOOD 10 (HUNGRY): no bit 7
  U2  MAXHP 40: HP 10 flashes (HP number cells), 11 not; MAXHP 12: HP 5 flashes, 6 not
  U3  Mage, Spark, MP 0, cast: MP number flashes, MPF_T 16, SFX_NO requested, no turn, MP 0;
      off after 16 ticks; in ICON MODE a refusal then a cursor press ends it at once
  U4  pick up A then B (code: pu_add x2): LAST_PICK 1, NEW bits 0+1; the page opens on B (its bit
      cleared), A shows '*' (cell 11,4) until the cursor visits it
  U5  NEW on slots 1, 3, LAST_PICK 3; discard slot 1 (code bag_discard): bits -> 2, LAST_PICK 2;
      discarding LAST_PICK -> $FF, the page opens on slot 0
  U6  verb strip highlight: EAT / READ cols 2-4, DRINK 2-5, DISCARD 18-23; row 20 attrs restored
  U7  first book (code pu_add IT_BOOK): READ IT IN THE BAG queued after the pick line, once;
      second book: none; with pl_et = ts_turn (D0): silent but flagged; new_game from GS_PLAYING
      (the D0 grate) keeps the flag, from GS_SELECT (menu START) clears it
  U8  WEAK: bag open / close -> F1 back; a pointer clear (bit 7 off over row 21) + ux_ptr -> still on
  I1  ITEM-INFO: every bag type in slot 0: PAGE_BUF (row 18) starts with its name, IE_BUF (row 19)
      == the spec model (tests/itemtab.py IE_SPEC), both <= 40; row-19 pixels iff text; attrs
      row 18 $47 / row 19 $05 (cols 2-31); EMPTY slot / [CLOSE] / a worn copy
  I2  row 18 says DODGE (Silk Cloak, King Helm), never EVA
Run: ZRCP_PORT=<port> python3 tests/ux1.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game_lib  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, GS_PLAYING  # noqa: E402
from proj3 import T, w16  # noqa: E402
import textpack  # noqa: E402
import itemtab  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
attr_at, cell_bytes = game_lib.attr_at, game_lib.cell_bytes
ROW = 21
HP_NUM, MP_NUM, FOOD_BAR, WORD = S["HP_NUM_COL"], S["MP_NUM_COL"], S["FOOD_BAR_COL"], S["HUNGER_COL"]
STR = dict(textpack.read_strings())
IDS = {n.lower(): i for i, (n, _) in enumerate(textpack.read_strings())}
IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}


def far(addr, a=None, bank_far="far6", de=None):
    """Stub bytes: [ld a, n] [ld de, nn] ld hl, addr : call far6 (or FARB0 via farb, C = 0)."""
    b = ([0x3E, a] if a is not None else []) + ([0x11] + w16(de) if de is not None else [])
    if bank_far == "b0":
        return b + [0x21] + w16(addr) + [0x0E, S["BANK_TEXT"], 0xCD] + w16(S["farb"])
    return b + [0x21] + w16(addr) + [0xCD] + w16(S[bank_far])


def main():
    fails = []
    n = [0]
    if KIT:
        print("[skip] ux1 needs a DEBUG_KIT=0 build")
        return 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        def ink(fr, c, r=ROW):
            return any(cell_bytes(fr, c, r))

        def flash(cols):
            """(bit-7 cells, ink cells) of row 21 among cols (bank-5 = the panel's own screen)."""
            fr = p.composed_frame()
            return ([c for c in cols if attr_at(fr, c, ROW) & 0x80], [c for c in cols if ink(fr, c)])

        def panel_idle(t=6):
            p.tick(2)
            p.until(lambda: p.rb("PANEL_DIRTY") == 0, 40)
            p.tick(t)

        def is_open():
            return p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]

        def open_page():
            p.tap("I")
            return p.until(is_open, 12)

        def close_page():
            p.tap("I")
            ok = p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
            p.settle(3)
            return ok

        def rc():
            return p.rb("pg_rc"), p.rb(S["pg_rc"] + 1)

        def zstr(name, ln=41):
            b = bytes(p.z.read_memory(S[name], ln))
            return b.split(b"\0")[0].decode("latin1")

        def put_bag(types):
            flat = [b for t in types for b in (t, 1, 0)]
            p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))

        def newmask():
            b = p.z.read_memory(S["NEW_MASK"], 3)
            return b[0] | b[1] << 8 | b[2] << 16

        # ---- M1 the menu pointer (item_info.md §5) ------------------------------------
        p.tut_default_off = False
        p.load()
        p.wait_state(S["GS_SELECT"])
        fr = p.frame()
        m_ink = [c for c in range(32) if any(cell_bytes(fr, c, 10))]
        m_at = {attr_at(fr, c, 10) for c in range(21)}
        es = p.rb(S["es_go"] + 1) | p.rb(S["es_go"] + 2) << 8
        check("M1 tutorial offered: row 10 NEW HERE? START > 1 TUTORIAL in cols 0-20, attr $45",
              es == S["ts_choice"] and len([c for c in m_ink if c <= 20]) >= 18 and m_at == {0x45},
              (es, m_ink, m_at))                   # (cols 21+: the hero preview's body)
        p.tut_default_off = True
        p.tut_off()                                # = the offer gone (blob_choice / the grate)
        for ln in range(8):                        # row 10 (third 1, row 2) cleared, then menu_static again
            p.wmem(0x4800 + 2 * 32 + ln * 256, [0] * 32)
        p.wmem(S["SCREEN_ATTR"] + 10 * 32, [0] * 32)
        okc = p.code(far(S["menu_static"], bank_far="far1"))
        fr = p.composed_frame()
        blank = okc and not any(any(cell_bytes(fr, c, 10)) for c in range(21)) and \
            all(attr_at(fr, c, 10) == 0 for c in range(21))
        check("M1 the offer gone (es_go = start_game): menu_static leaves row 10 blank", blank)

        # ---- U1 FOOD -----------------------------------------------------------------
        p.boot(K_KNIGHT)
        p.wb("FOOD", 9)
        p.wb("HSTAGE", S["HS_WEAK"])
        p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_FOOD"])
        panel_idle()
        fl, ik = flash(range(FOOD_BAR, FOOD_BAR + 9))
        fr = p.composed_frame()
        bars = [attr_at(fr, c, ROW) for c in range(FOOD_BAR, WORD)]
        words = [attr_at(fr, c, ROW) for c in range(WORD, WORD + 5)]
        check("U1 FOOD 9: the word's ink cells $C2, blank word cells / bar 15-18 $42",
              fl and fl == [c for c in ik if c >= WORD] and bars == [0x42] * 4
              and all(a == (0xC2 if ink(fr, WORD + i) else 0x42) for i, a in enumerate(words)), (fl, ik, bars, words))
        p.wb("FOOD", 10)
        p.wb("HSTAGE", S["HS_HUNGRY"])
        p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_FOOD"])
        panel_idle()
        fl, _ = flash(range(FOOD_BAR, FOOD_BAR + 9))
        check("U1 FOOD 10: no bit 7 over 15-23", fl == [], fl)

        # ---- U2 HP -------------------------------------------------------------------
        hp_a = S["P_ENTITIES"] + S["E_HP"]
        res = {}
        for mx, hp in ((40, 10), (40, 11), (12, 5), (12, 6)):
            p.wmem(hp_a, [hp, mx])
            panel_idle()
            fl, ik = flash((HP_NUM, HP_NUM + 1))
            res[(mx, hp)] = (fl, ik)
        ok = (res[(40, 10)][0] and res[(40, 10)][0] == res[(40, 10)][1] and res[(40, 11)][0] == []
              and res[(12, 5)][0] and res[(12, 5)][0] == res[(12, 5)][1] and res[(12, 6)][0] == [])
        check("U2 MAXHP 40: HP 10 flashes, 11 not; MAXHP 12: HP 5 flashes, 6 not (ink cells of 5-6)", ok, res)
        p.wmem(hp_a, [40, 40])

        # ---- U3 MP -------------------------------------------------------------------
        def mage_mp0():
            p.boot(K_WIZARD)
            p.wmem(S["ARANK"], w16(1))                 # Spark rank 1
            p.wb("MP", 0)
            p.tick(3)
            panel_idle()

        sfx_seen = []

        def watch_sfx(on):
            if on:
                sfx_seen.clear()
                p.present_samples = []
                p.present_probe = S["sfx_req"]
                p.banks_differ = lambda: sfx_seen.append(
                    int(re.search(r"AF=([0-9a-fA-F]{4})", p.z.get_registers()).group(1), 16) >> 8)
                p.z.cmd("set-breakpoint 4 PC=%d" % S["sfx_req"])
            else:
                p.present_probe = None
                p.z.cmd("set-breakpoint 4")

        mage_mp0()
        p.select_slot(1)
        t0 = p.rw("TURN_COUNTER")
        watch_sfx(True)
        nt = p.no_turn("FIRE")
        watch_sfx(False)
        fl, ik = flash((MP_NUM, MP_NUM + 1))
        st = (nt, p.rw("TURN_COUNTER") == t0, p.rb("MP"), p.rb("MPF_T"), fl, ik, S["SFX_NO"] in sfx_seen)
        check("U3 MP 0 + Spark: MP number ink cells flash, MPF_T counting, SFX_NO requested, no turn, MP 0",
              nt and st[1] and st[2] == 0 and 0 < st[3] <= 16 and fl and fl == ik and st[6], (st, sfx_seen))
        p.tick(18)
        fl, _ = flash((MP_NUM, MP_NUM + 1))
        check("U3 32 frames later: MPF_T 0, no bit 7", p.rb("MPF_T") == 0 and fl == [], (p.rb("MPF_T"), fl))
        # ICON MODE: enter, cursor on Spark, FIRE (refused, the mode stays), then a cursor press
        p.hold("A", "SPACE")
        p.tick(2)
        p.release()
        p.tick(2)
        im = p.rb("ICON_MODE")
        p.wb("SEL_SLOT", 1)
        p.tap("SPACE")
        p.tick(2)
        on = (p.rb("MPF_T"), flash((MP_NUM, MP_NUM + 1))[0], p.rb("ICON_MODE"))
        p.tap("P")
        p.tick(1)
        off = (p.rb("MPF_T"), flash((MP_NUM, MP_NUM + 1))[0])
        check("U3 ICON MODE: refusal flashes (mode kept), the next press ends it",
              im == 1 and on[0] > 0 and on[1] and on[2] == 1 and off == (0, []), (im, on, off))

        # ---- U4 / U5 / U7: pickups through pu_add, compaction through bag_discard ----------
        p.boot(K_KNIGHT)
        p.wmem(S["BAG"], [0] * 60)
        p.wmem(S["NEW_MASK"], [0, 0, 0])
        p.wb("LAST_PICK", 0xFF)
        qn0 = p.rb("LOG_QN")
        ok = p.code(far(S["pu_add"], IT["W_LONG"], de=0x0100) + far(S["pu_add"], IT["H_HELM"], de=0x0100))
        got = (ok, newmask(), p.rb("LAST_PICK"), list(p.z.read_memory(S["BAG"], 6)))
        check("U4 pick up A then B: NEW bits 0 + 1, LAST_PICK 1",
              got == (True, 3, 1, [IT["W_LONG"], 1, 0, IT["H_HELM"], 1, 0]), got)
        # top-up counts: a Heal x1 then another Heal -> LAST_PICK = that stack's slot
        p.boot(K_KNIGHT)
        put_bag([IT["W_LONG"], IT["P_HEAL"], IT["H_HELM"]])
        p.wmem(S["NEW_MASK"], [0, 0, 0])
        ok = p.code(far(S["pu_add"], IT["P_HEAL"], de=0x0100))
        check("U4b a stack top-up counts: LAST_PICK 1, bit 1", (ok, p.rb("LAST_PICK"), newmask()) == (True, 1, 2),
              (ok, p.rb("LAST_PICK"), newmask()))
        # the page: A (slot 0) NEW, B (slot 1) NEW + LAST_PICK
        p.boot(K_KNIGHT)
        put_bag([IT["W_LONG"], IT["H_HELM"], IT["F_APPLE"]])
        p.wmem(S["NEW_MASK"], [3, 0, 0])
        p.wb("LAST_PICK", 1)
        okp = open_page()
        fr = p.frame()
        star0 = any(cell_bytes(fr, 11, 4))
        st = (okp, rc(), newmask(), star0, any(cell_bytes(fr, 14, 4)))
        check("U4 page opens on B (row 1 col 1), B's bit cleared + no mark; A shows '*'",
              st == (True, (1, 1), 1, True, False), st)
        p.tap("O")                                 # the cursor arrives on A
        fr = p.frame()
        st = (rc(), newmask(), any(cell_bytes(fr, 11, 4)))
        check("U4 visiting A clears its mark", st == ((1, 0), 0, False), st)
        close_page()
        # U5: NEW slots 1 + 3, LAST_PICK 3, discard slot 1
        p.boot(K_KNIGHT)
        put_bag([IT["W_LONG"], IT["H_HELM"], IT["F_APPLE"], IT["S_FEAR"], IT["C_MIGHT"]])
        p.wmem(S["NEW_MASK"], [0x0A, 0, 0])
        p.wb("LAST_PICK", 3)
        ok = p.code(far(S["bag_discard"], 1))
        st = (ok, newmask(), p.rb("LAST_PICK"), p.z.read_memory(S["BAG"], 1)[0])
        check("U5 discard below a NEW slot: its bit moves down (3 -> 2), LAST_PICK 3 -> 2", st[:3] == (True, 4, 2), st)
        p.boot(K_KNIGHT)
        put_bag([IT["W_LONG"], IT["H_HELM"], IT["F_APPLE"], IT["S_FEAR"]])
        p.wmem(S["NEW_MASK"], [0x0C, 0, 0])
        p.wb("LAST_PICK", 2)
        ok = p.code(far(S["bag_discard"], 2))
        lp, nm = p.rb("LAST_PICK"), newmask()
        p.boot(K_KNIGHT)
        put_bag([IT["W_LONG"], IT["H_HELM"], IT["S_FEAR"]])
        p.wmem(S["NEW_MASK"], [nm & 255, 0, 0])
        p.wb("LAST_PICK", lp)
        okp = open_page()
        st = (ok, lp, nm, okp, rc())
        check("U5 discarding LAST_PICK: $FF, NEW 2,3 -> 2; the page opens on slot 0",
              st == (True, 0xFF, 0x04, True, (1, 0)), st)
        close_page()

        # ---- U6 the verb strip --------------------------------------------------------
        p.boot(K_KNIGHT)
        put_bag([IT["F_APPLE"], IT["BOOK"], IT["P_HEAL"], IT["W_LONG"]])
        p.wb("LAST_PICK", 0xFF)
        open_page()
        r20 = [attr_at(p.frame(), c, 20) for c in range(32)]

        def hi_cols():
            fr = p.frame()
            return [c for c in range(32) if attr_at(fr, c, 20) & 0x38 == 0x08]
        res = {}
        for slot, name in ((0, "EAT"), (1, "READ"), (2, "DRINK")):
            while rc() != (1, slot):
                p.tap("P")
            base = [attr_at(p.frame(), c, 20) for c in range(32)]
            p.tap("FIRE")                          # the strip on USE
            res[name] = hi_cols()
            if name == "DRINK":
                p.tap("P")                         # -> DISCARD (EQUIP / REMOVE disabled)
                res["DISCARD"] = hi_cols()
            p.tap("Q")                             # back to the grid
            res[name + " back"] = [attr_at(p.frame(), c, 20) for c in range(32)] == base
        check("U6 highlight: EAT / READ cols 2-4, DRINK 2-5, DISCARD 18-23; row 20 restored after the strip",
              res.get("EAT") == [2, 3, 4] and res.get("READ") == [2, 3, 4] and res.get("DRINK") == [2, 3, 4, 5]
              and res.get("DISCARD") == list(range(18, 24)) and all(res[k] for k in res if k.endswith("back")),
              (res, r20[:8]))
        close_page()

        # ---- U7 the first-book hint ---------------------------------------------------
        def log_ids_after(qn0):
            return p.rb("LOG_QN") - qn0
        p.boot(K_KNIGHT)
        p.wmem(S["BAG"], [0] * 60)
        p.wb("UX_FL", 0)
        p.wb("LOG_QN", 0)
        ok = p.code(far(S["pu_add"], IT["BOOK"], de=0x0100))
        q1 = p.rb("LOG_QN")
        slot = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + q1 - 1) % S["LOG_SLOTS"]
        last = bytes(p.z.read_memory(S["LOG_TXT"] + 64 * slot, 40))
        ok2 = p.code(far(S["pu_add"], IT["BOOK"], de=0x0100))
        q2 = p.rb("LOG_QN")
        st = (ok, ok2, q1, q2, p.rb("UX_FL") & 1)
        hint_ok = textpack_decode(last) == STR["hint_book"]
        check("U7 first book: pick line + READ IT IN THE BAG; second book: the pick line only",
              st == (True, True, 2, 3, 1) and hint_ok, (st, last[:24]))
        # D0 (pl_et = ts_turn): silent, flag set
        p.boot(K_KNIGHT)
        p.wmem(S["BAG"], [0] * 60)
        p.wb("UX_FL", 0)
        p.wb("LOG_QN", 0)
        p.wmem(S["pl_et"] + 1, w16(S["ts_turn"]))
        ok = p.code(far(S["pu_add"], IT["BOOK"], de=0x0100))
        st = (ok, p.rb("LOG_QN"), p.rb("UX_FL") & 1)
        check("U7 D0 book: flag set, no hint line (the pick line only)", st == (True, 1, 1), st)
        # new_game: the flag survives the D0 grate (GS_PLAYING), a menu START clears it
        res = {}
        for gs, name in ((GS_PLAYING, "grate"), (S["GS_SELECT"], "menu")):
            p.boot(K_KNIGHT)
            p.wb("UX_FL", 1)
            p.wb("GAME_STATE", gs)
            p.wmem(S["NEW_MASK"], [7, 0, 0])
            p.wb("MPF_T", 9)
            ok = p.code(far(S["new_game"], bank_far="b0"))
            res[name] = (ok, p.rb("UX_FL"), newmask(), p.rb("MPF_T"), p.rb("LAST_PICK"))
        check("U7 new_game: D0 grate keeps the hint flag, a menu START clears it; NEW 0, MPF_T 0, LAST_PICK $FF",
              res == {"grate": (True, 1, 0, 0, 0xFF), "menu": (True, 0, 0, 0, 0xFF)}, res)

        # ---- U8 rebuild after the page / a pointer -----------------------------------------
        p.boot(K_KNIGHT)
        p.wb("FOOD", 9)
        p.wb("HSTAGE", S["HS_WEAK"])
        p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_FOOD"])
        panel_idle()
        before = flash(range(WORD, WORD + 5))[0]
        open_page()
        close_page()
        after = flash(range(WORD, WORD + 5))[0]
        disp = [c for c in range(WORD, WORD + 5) if attr_at(p.frame(), c, ROW) & 0x80]
        check("U8 WEAK: bag open / close -> F1 back (bank 5 + displayed)", before and after == before and disp == before,
              (before, after, disp))
        # a pointer clear over row 21 (tt_ptr: bit 7 off), then its ux_ptr call
        base = S["SCREEN_ATTR"] + ROW * 32
        row = list(p.z.read_memory(base, 32))
        p.wmem(base, [a & 0x7F for a in row])
        ok = p.code(far(S["ux_ptr"], bank_far="b0"))
        again = [c for c in range(WORD, WORD + 5) if p.z.read_memory(base + c, 1)[0] & 0x80]
        check("U8 a pointer clearing cols 19-23 at WEAK + ux_ptr: still flashing", ok and again == before, (ok, again))
        blob = open(os.path.join(game_lib.BUILD_DIR, "ovl", "blob.bin"), "rb").read()
        far_ptr = bytes([0x21]) + bytes(w16(S["ux_ptr"])) + bytes([0x0E, S["BANK_TEXT"], 0xCD]) + bytes(w16(S["farb"]))
        check("U8 the D0 blob's tt_ptr calls ux_ptr (FARB0 in blob.bin)", far_ptr in blob)

        # ---- I1 / I2 the item rows ------------------------------------------------------
        model = itemtab.ie_model(STR, {k: v for k, v in S.items() if isinstance(v, int)})
        p.boot(K_KNIGHT)
        p.wb("LAST_PICK", 0xFF)
        p.wmem(S["NEW_MASK"], [0, 0, 0])
        put_bag([IT["F_APPLE"]])
        open_page()
        bad, dodge = [], {}
        for t in range(S["IT_F_CARROT"], S["IT_COUNT"]):
            p.wmem(S["BAG"], [t, 1, 0])
            p.tap("P")                             # re-run pg_info on slot 0 (empty slot 1, back)
            p.tap("O")
            r18, r19 = zstr("PAGE_BUF", 40), zstr("IE_BUF")
            fr = p.frame()
            ink19 = any(any(cell_bytes(fr, c, 19)) for c in range(2, 32))
            at18 = {attr_at(fr, c, 18) for c in range(2, 32)}
            at19 = {attr_at(fr, c, 19) for c in range(2, 32)}
            if r19 != model[t] or len(r18) > 40 or len(r19) > 40 or ink19 != bool(r19) or not r18 \
                    or at18 != {0x47} or at19 != {0x05}:
                bad.append((t, r18, r19, model[t], ink19, at18, at19))
            if t in (IT["A_SILK"], IT["H_KING"]):
                dodge[t] = r18
        check("I1 every bag type: row 18 text, row 19 == phrase[, gate] (spec), <= 40, attrs $47 / $05",
              bad == [], bad[:3])
        check("I2 DODGE on row 18 (Silk Cloak, King Helm), never EVA",
              all("DODGE+" in v and "EVA" not in v for v in dodge.values()) and len(dodge) == 2, dodge)
        # an empty bag slot / [CLOSE] / a worn copy
        p.wmem(S["BAG"], [IT["A_PLATE"], 1, 0] + [0] * 57)
        p.tap("P")                                 # slot 1: empty
        fr = p.frame()
        e18 = [c for c in range(2, 32) if any(cell_bytes(fr, c, 18))]   # EMPTY = 30 px from x 16: cols 2-5
        e19 = not any(any(cell_bytes(fr, c, 19)) for c in range(32))
        while rc()[0] != 0:
            p.tap("Q")
        fr = p.frame()
        c1819 = not any(any(cell_bytes(fr, c, r)) for c in range(32) for r in (18, 19))
        p.wmem(S["WORN"] + S["WS_ARMOUR"] * S["IR_STRIDE"], [IT["A_PLATE"], 1, 0])
        p.tap("Q")                                 # [CLOSE] -> worn row (col kept 0 -> min = weapon)
        p.tap("P")                                 # worn armour
        w18, w19 = zstr("PAGE_BUF", 40), zstr("IE_BUF")
        st = (e18, e19, c1819, w18, w19)
        check("I1 EMPTY slot: row 18 EMPTY, row 19 blank; [CLOSE]: both blank; worn Plate == the bag text",
              e18 == [2, 3, 4, 5] and e19 and c1819 and w18.startswith("PLATE") and w19 == model[IT["A_PLATE"]], st)
        close_page()
        print(f"ux1: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def textpack_decode(stream):
    """A LOG_TXT slot (a token stream, 0-terminated) -> text, via the build's dictionary."""
    img = textpack.parse_emitted(os.path.join(game_lib.BUILD_DIR, "text", "strings.asm"))
    raw = bytes(img)
    dict_off = img.dict_off
    out = []
    for b in stream:
        if b == 0:
            break
        if b < 128:
            out.append(chr(b))
            continue
        e = raw[dict_off + b - 128]
        while True:
            c = raw[e]
            out.append(chr(c & 0x7F))
            e += 1
            if c & 0x80:
                break
    return "".join(out)


if __name__ == "__main__":
    sys.exit(main())
