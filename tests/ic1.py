#!/usr/bin/env python3
"""IC1 true 16x16 item icons (game.md §8.11 Q5; src/icons6.asm R6: icon_slot /
worn_draw / qs_draw; page_ovl.asm pg_cell / pg_info; panel.asm slot_redraw /
panel_init; icons3.asm icon_state / pot_need / item_icons; icons.asm icon_poll (QS_RECHK);
panel_hot.asm item_hp; pickup6.asm pot_sync).
Release build (DEBUG_KIT=0), PROTO room A, monsters parked. Icon bytes are compared
with their SOURCE (assets/gfx/icons/icons16.asm), inks with it_tab.

  G1  page grid: every bag type (39, in two fills of 20 + 19) draws its icon into
      its 2x2 cells in its it_tab ink; the 4 worn slots filled: the worn row
  G2  page description (cols 0-1, rows 18-19): the cursor item's icon; an empty bag
      slot / [CLOSE] -> blank; an empty worn slot -> its placeholder (ink $05)
  W1  panel worn cells (rows 22-23, cols 24/26/28/30): the start kit (Short Sword,
      Leather, helmet + charm placeholders), then EQUIP Helm / REMOVE the weapon
      (fx_main: fx_done's worn_cell) -> redrawn (composed + displayed after present)
  Q1  quick POTION = the item quick-use would use, in its own icon / ink, the count
      OF THAT TYPE: Mana only -> Mana x3; Heal x2 + Mana x3 hurt -> Heal "2" (not
      5); full HP -> Mana "3" (no BAG write: item_hp / the MP poll -> QS_RECHK); MP full too -> the
      first present (Heal: quick-use says NO NEED); Cure + POISON with HP / MP full
      -> Cure; Heal split 9 + 2 -> "9" (capped); none -> the Heal icon greyed, "0"
  Q2  quick FOOD (lowest type: Carrot x2 over Meat) / SCROLL (largest stack: Fear x2
      over Teleport) icon + own count; none -> Apple / Teleport greyed
  Q3  the Mage's quick slots (one col right): Mana pick
  I1  ISR over bank 6 (R6 follow-up (b)): icon blits in a loop with interrupts on;
      every ISR stop records the $C000 bank; bank 6 is interrupted, the ISR pages
      bank 3 for AY_PLAY and hands back exactly the shadow (port + MMU) each time;
      the icons drawn meanwhile are intact. Also reports the banks seen during a
      real page open
  T   cost (DI, incl. far6): icon_slot, worn_draw, qs_draw (each class)
Run: ZRCP_PORT=<port> python3 tests/ic1.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
import game_lib
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, RUN_LIMIT  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE = 1
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
LO = S["IT_BAG_LO"]
PH = S["ICONS16_PH"]
INK_PH = S["ICONS16_INK_PH"]
GREY, HUD = S["ATTR_P_GREY"], S["ATTR_HUD"]
FONT6 = open(os.path.join(HERE.parent, "assets", "gfx", "fonts", "font6x8.bin"), "rb").read()
QCOL = {K_KNIGHT: {"F": 15, "P": 18, "S": 21}, K_WIZARD: {"F": 18, "P": 21, "S": 24}}
I = lambda n: S["IT_" + n]                     # noqa: E731,E741


def w16(v):
    return [v & 255, v >> 8]


def digit(ch):
    return bytes(b & 0xFC for b in FONT6[(ord(ch) - 32) * 8:(ord(ch) - 31) * 8])


def run(p, check):
    z = p.z
    WT = S["wait_tick"]
    attr_at, cell_bytes = game_lib.attr_at, game_lib.cell_bytes
    def ink(t):                                # FLOOR1: it_tab lives in R6: the model's ink
        return room_model.item_ink(t)

    def stub(body, measure=False):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        z.cmd("set-register PC=%d" % STUB)
        if measure:
            z.cmd("reset-tstates-partial")
        z.cmd("run %d" % RUN_LIMIT)
        t = int(z.cmd("get-tstates-partial")) if measure else 0
        assert p.pc() == WT, "stub did not return: %#06x" % p.pc()
        return t

    def far6(target, pre=()):
        return list(pre) + [0x21] + w16(S[target]) + [0xCD] + w16(S["far6"])

    def put(items, worn=None, sync=True):
        flat = []
        for it in items:
            n, q = it if isinstance(it, tuple) else (it, 1)
            flat += [I(n), q, 0]
        p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))
        if worn is not None:
            p.wmem(S["WORN"], [x for n in worn for x in ((I(n), 1, 0) if n else (0, 0, 0))])
        if sync:
            stub(far6("pot_sync"))

    def park():
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)

    def icon_ok(fr, idx, c, r, a):
        """[] if icon idx sits at (c, r) 2x2 with attr a, else the bad cells."""
        bad = []
        for (dc, dr), want in game_lib.icon16_cells(idx).items():
            if cell_bytes(fr, c + dc, r + dr) != want:
                bad.append(("px", c + dc, r + dr))
            if a is not None and attr_at(fr, c + dc, r + dr) & ~0x38 & 255 != a:   # (the cursor: paper)
                bad.append(("attr", c + dc, r + dr, hex(attr_at(fr, c + dc, r + dr))))
        return bad

    def scene(hero):
        p.boot(hero)
        park()
        for a in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
            p.wmem(S[a], [0] * 16)
        p.settle(3)

    def is_open():
        return p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]

    def open_page():
        p.tap("I")
        return p.until(is_open, 12)

    def close_page():
        p.tap("I")
        ok = p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
        p.settle(2)
        return ok

    def slot_rect(s):
        if s >= 20:
            return 11 + 3 * (s - 20), 16
        return 9 + 3 * (s % 5), 4 + 3 * (s // 5)

    # ======================= G: the page ==========================================
    scene(K_KNIGHT)
    types = list(range(LO, S["IT_COUNT"]))
    assert len(types) == PH
    worn = ["W_LONG", "A_PLATE", "H_KING", "C_SCARAB"]
    bad, nfill = [], 0
    for fill in (types[:20], types[20:]):
        p.wmem(S["BAG"], [b for t in fill for b in (t, 1, 0)] + [0] * (60 - 3 * len(fill)))
        p.wmem(S["WORN"], [b for n in worn for b in (I(n), 1, 0)])
        stub(far6("pot_sync"))
        ok = open_page()
        fr = p.frame()
        for s, t in enumerate(fill):
            c, r = slot_rect(s)
            bad += [(t,) + b for b in icon_ok(fr, t - LO, c, r, ink(t))]
        for k, n in enumerate(worn):
            c, r = slot_rect(20 + k)
            bad += [(n,) + b for b in icon_ok(fr, I(n) - LO, c, r, ink(I(n)))]
        nfill += ok and close_page()
    check("G1 page: all 39 bag types draw their icon (source bytes) in their 2x2 cells, it_tab ink; "
          "the worn row's 4 items", nfill == 2 and bad == [], (nfill, bad[:6]))

    put(["P_MANA", ("F_MEAT", 3)], [None, "A_ROBE", None, None])
    ok = open_page()
    seen = {}
    for name, keys, idx, a in (("mana (slot 0)", (), I("P_MANA") - LO, ink(I("P_MANA"))),
                               ("meat (slot 1)", ("P",), I("F_MEAT") - LO, ink(I("F_MEAT"))),
                               ("empty bag slot 2", ("P",), None, None),
                               ("[CLOSE]", ("Q",), None, None),
                               ("empty worn weapon", ("Q", "O", "O"), PH + 0, INK_PH),
                               ("robe", ("P",), I("A_ROBE") - LO, ink(I("A_ROBE"))),
                               ("empty worn helmet", ("P",), PH + 2, INK_PH)):
        for k in keys:
            p.tap(k)
        fr = p.frame()
        if idx is None:
            seen[name] = all(not any(cell_bytes(fr, c, r)) for c in (0, 1) for r in (18, 19))
        else:
            seen[name] = icon_ok(fr, idx, 0, 18, a) == []
    ok = ok and close_page()
    check("G2 description icon (cols 0-1, rows 18-19): item / blank (empty bag slot, [CLOSE]) / "
          "placeholder (empty worn)", ok and all(seen.values()), seen)

    # ======================= W: panel worn cells ===================================
    scene(K_KNIGHT)                               # kit: Short Sword + Leather worn

    def worn_cells(fr, want):
        bad = []
        for k, w in enumerate(want):
            idx, a = (PH + k, INK_PH) if w is None else (I(w) - LO, ink(I(w)))
            bad += [(k,) + b for b in icon_ok(fr, idx, 24 + 2 * k, 22, a)]
        return bad
    w1 = (worn_cells(p.composed_frame(), ["W_SHORT", "A_LEATHER", None, None]),
          worn_cells(p.frame(), ["W_SHORT", "A_LEATHER", None, None]))
    put(["H_HELM"])

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        stub(far6("fx_main"))
        return p.rb("FX_OP")
    r1 = fx(S["FX_EQUIP"], 0)
    p.settle(2)
    w2 = worn_cells(p.frame(), ["W_SHORT", "A_LEATHER", "H_HELM", None])
    r2 = fx(S["FX_REMOVE"], S["PG_SLOT_WORN"])
    p.settle(2)
    w3 = (worn_cells(p.composed_frame(), [None, "A_LEATHER", "H_HELM", None]),
          worn_cells(p.frame(), [None, "A_LEATHER", "H_HELM", None]))
    check("W1 panel worn cells: start kit + 2 placeholders; EQUIP Helm, REMOVE the weapon -> redrawn "
          "(composed and displayed)", (w1, r1 & 1, w2, r2 & 1, w3) == (([], []), 1, [], 1, ([], [])),
          (w1, r1, w2, r2, w3))

    # ======================= Q: quick slots ========================================
    def qslot(fr, col, t, n, grey=False):
        """[] if the quick slot at col shows type t's icon + digit n (grey: all 6 attrs GREY)."""
        bad = icon_ok(fr, t - LO, col, 18, GREY if grey else ink(t))
        if cell_bytes(fr, col + 2, 19) != digit(str(min(n, 9))):
            bad.append(("digit", cell_bytes(fr, col + 2, 19).hex()))
        if any(cell_bytes(fr, col + 2, 18)):
            bad.append("row18")
        a = (attr_at(fr, col + 2, 18), attr_at(fr, col + 2, 19))
        if a != ((GREY, GREY) if grey else (0, HUD)):
            bad.append(("count attrs", a))
        return bad

    def hp(v=None, maxhp=None):
        e = p.ent(0)
        p.set_ent(0, HP=e["MAXHP"] if v is None else v)

    def show(n=8):
        p.settle(n)
        return p.frame()

    scene(K_KNIGHT)
    p.wb("SEL_SLOT", 0)
    qc = QCOL[K_KNIGHT]
    q = {}
    hp()
    p.wb("MP", 0)
    put([("P_MANA", 3), "F_APPLE"])
    q["mana only -> Mana 3"] = qslot(show(), qc["P"], I("P_MANA"), 3)
    p.set_ent(0, HP=p.ent(0)["MAXHP"] - 5)
    put([("P_HEAL", 2), ("P_MANA", 3)])
    q["heal+mana hurt -> Heal 2 (not 5)"] = qslot(show(), qc["P"], I("P_HEAL"), 2)
    hp()                                          # no BAG write: item_hp sets QS_RECHK
    q["full HP -> Mana 3 (Heal skipped)"] = qslot(show(), qc["P"], I("P_MANA"), 3)
    p.wb("MP", p.rb("MAXMP"))
    q["HP + MP full -> Heal 2 (first present)"] = qslot(show(), qc["P"], I("P_HEAL"), 2)
    put([("P_HEAL", 1), "P_CURE"])
    p.wb(S["ST_FLAGS"], S["STS_POISON"])
    q["POISON, HP / MP full -> Cure 1"] = qslot(show(), qc["P"], I("P_CURE"), 1)
    p.wb(S["ST_FLAGS"], 0)
    p.set_ent(0, HP=p.ent(0)["MAXHP"] - 1)
    put([("P_HEAL", 9), "F_APPLE", ("P_HEAL", 2)])
    q["Heal 9 + 2 -> 9 (capped, all stacks)"] = qslot(show(), qc["P"], I("P_HEAL"), 9)
    put([("F_MEAT", 1), ("F_CARROT", 2), "S_TELEPORT", ("S_FEAR", 2), ("S_FEAR", 1)])
    fr = show(10)
    q["potions none -> Heal greyed 0"] = qslot(fr, qc["P"], I("P_HEAL"), 0, grey=True)
    q["food: Carrot 2 (lowest)"] = qslot(fr, qc["F"], I("F_CARROT"), 2)
    q["scroll: Fear 3 (largest stack; count = all Fear)"] = qslot(fr, qc["S"], I("S_FEAR"), 3)
    put(["P_HEAL"])
    fr = show(10)
    q["food none -> Apple greyed 0"] = qslot(fr, qc["F"], I("F_APPLE"), 0, grey=True)
    q["scroll none -> Teleport greyed 0"] = qslot(fr, qc["S"], I("S_TELEPORT"), 0, grey=True)
    bad = {k: v[:3] for k, v in q.items() if v}
    check("Q1/Q2 quick slots: the quick-use pick's icon + ink + own count; potion Heal->Mana->Cure "
          "skipping no-ops (HP / MP / status changes redraw); empty -> representative greyed",
          not bad, bad)

    scene(K_WIZARD)
    p.wb("SEL_SLOT", 0)
    hp()
    p.wb("MP", 0)
    put([("P_HEAL", 1), ("P_MANA", 2)])
    q3 = qslot(show(), QCOL[K_WIZARD]["P"], I("P_MANA"), 2)
    check("Q3 Mage potion slot (col 21): Heal at full HP skipped -> Mana 2", q3 == [], q3)

    # ======================= T: cost ===============================================
    put([("P_HEAL", 2), "F_APPLE", "S_FEAR"], ["W_OAK", "A_ROBE", None, None])
    di, ei = [0xF3], [0xFB]
    t_icon = stub(di + far6("icon_slot", [0x3E, 0, 0x11] + w16((4 << 8) | 9)) + ei, True)
    t_clr = stub(di + far6("icon_slot", [0x3E, 5, 0x11] + w16((4 << 8) | 9)) + ei, True)
    t_worn = stub(di + far6("worn_draw") + ei, True)
    t_q = [stub(di + far6("qs_draw", [0x3E, qs, 0x11] + w16((18 << 8) | S["IS_NORMAL"])) + ei, True)
           for qs in (0, 1, 2)]
    print(f"[info] T icon_slot {t_icon} T, cleared {t_clr} T, worn_draw {t_worn} T, qs_draw food / potion / "
          f"scroll {t_q} T (all incl. far6 + DI stub)", flush=True)
    check("T costs: icon_slot <= 2.5k, worn_draw <= 9.5k, qs_draw <= 12k T",
          t_icon <= 2500 and t_worn <= 9500 and max(t_q) <= 12000, (t_icon, t_worn, t_q))
    p.settle(4)

    # ======================= I1: the ISR over bank 6 ===============================
    ay, done = S["isr.page"], S["isr.done"]
    n_loop = 120
    # ei; ld b, n; .l: push bc; ld a, 0; ld de, (4 << 8) | 9; ld hl, icon_slot; call far6; pop bc; djnz .l
    body = [0xFB, 0x06, n_loop, 0xC5, 0x3E, 0, 0x11] + w16((4 << 8) | 9) + [0x21] + w16(S["icon_slot"]) \
        + [0xCD] + w16(S["far6"]) + [0xC1, 0x10]
    body.append((3 - (len(body) + 1)) & 255)       # djnz back to the push (index 3)
    p.wmem(STUB, body + [0xC3] + w16(WT))
    z.cmd("set-breakpoint 5 PC=%d" % ay)
    z.cmd("set-breakpoint 6 PC=%d" % done)
    z.cmd("set-register PC=%d" % STUB)
    banks, bad6, n6, stops = [], [], 0, 0
    pending6 = False
    for _ in range(400):
        z.cmd("run %d" % RUN_LIMIT)
        pc = p.pc()
        if pc not in (ay, done):
            break
        stops += 1
        regs = z.cmd("get-registers")
        sh, port, c000 = p.rb("PORT_7FFD_SHADOW"), game.port_7ffd(p), game.mmu_c000(regs)
        if pc == ay:
            banks.append(sh & 7)
            pending6 = sh & 7 == 6
            n6 += pending6
            if (port, c000) != ((sh & 0xF8) | S["BANK_AY"], S["BANK_AY"]):
                bad6.append(("ay", hex(sh), hex(port), c000))
        else:
            if (port, c000) != (sh, sh & 7) or (pending6 and c000 != 6):
                bad6.append(("done", hex(sh), hex(port), c000))
        z.cmd("cpu-step")
    z.cmd("set-breakpoint 5")
    z.cmd("set-breakpoint 6")
    fr = p.composed_frame()
    intact = icon_ok(fr, I("P_HEAL") - LO, 9, 4, ink(I("P_HEAL")))
    print(f"[info] I1 {n_loop} icon_slot calls with EI: {stops} ISR stops, banks interrupted {sorted(set(banks))},"
          f" bank 6 {n6}x", flush=True)
    check("I1 the ISR interrupts R6 code (bank 6 paged): AY_PLAY on bank 3, port == shadow and bank 6 back "
          "at isr.done; icon intact", (p.pc() == WT, n6 > 0, bad6[:4], intact) == (True, True, [], []),
          (hex(p.pc()), n6, banks[:12], bad6[:4], intact))
    # the real page open, for the record
    z.cmd("set-breakpoint 5 PC=%d" % ay)
    p.hold("I")
    pb = set()
    for _ in range(4000):
        z.cmd("cpu-step")
        z.cmd("run %d" % RUN_LIMIT)
        pc = p.pc()
        if pc == ay:
            pb.add(p.rb("PORT_7FFD_SHADOW") & 7)
            continue
        if pc == WT:
            p.release()
        if is_open():
            break
    z.cmd("set-breakpoint 5")
    print(f"[info] I1 page open: ISR interrupted $C000 banks {sorted(pb)}", flush=True)
    close_page()


def main():
    fails = []
    n = [0]
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)

        if KIT:
            print("[skip] ic1 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(p, check)
        print(f"ic1: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
