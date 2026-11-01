#!/usr/bin/env python3
"""GEAR2: the per-instance offset q (docs/design/gear_rules.md 2, vectors G2-3 .. G2-9). Release build
(DEBUG_KIT=0), PROTO room A, the hero walks onto floor entries like tests/pickup3e.py / exit3e.py.
The generator side (class gate, the q pass, FL_QTY = 1 + (q & 7)) is tests/items_gen.py (Z80 == model,
16,000 levels) and tools/items_model_test.py (G2-1 / G2-2 / G2-9 distributions).

  G2-3  floor HELM FL_QTY 8 -> bag I $07, the page ' -1' (DEF 1 - 1 = 0 prints nothing); every pickup
        decodes (FL_QTY - 1) & 7: LONG 1 / 2 / 3 -> I 0 / 1 / 2 (page ' +1 1D8+1 ATK+1' for q+1)
  G2-4  floor CHAIN FL_QTY 3 picked up, page ' +2 DEF+4', equipped (Leather swapped out): HERO_DEF 4
  G2-5  worn LONG I $01: hero_recalc KT_BONUS +1, KT_DIE 8; I $00: bonus 0
  G2-6  worn ROBE I $07 (q -1): GEAR_MP 1 (Mage), I $02: GEAR_MP 4
  G2-7  potion / food / scroll / book / bow / charm / unique (FL_QTY 1) and the legacy IT_POTION: I $00
  G2-8  worn HELM I $A7 (m -3, q -1): the page ' WORN OUT DEF-3', the summed DEF clamps at 0
  G2-9  the Warrior D1 / Mage D3 gear pools (tools/items_model) == the spec lists
  G2-10 the ist_v decode, all 256 ISTATE values, v = m + q via the page line of a worn Long Sword (it_fmt)
Run: ZRCP_PORT=<port> python3 tests/gear2.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, stand_y, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402
import items_model as M  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER = 1, 2
HX = 9
HY = stand_y(1, 6)
NOWHERE = 7
IROW = 9 + 7
FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
FLS1 = S["FL_S1"]
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
BAG, WORN = S["BAG"], S["WORN"]
I = lambda n: S["IT_" + n]                     # noqa: E731,E741


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)

        if KIT:
            print("[skip] gear2 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"gear2: {len(fails)} failed" + (f": {fails[:12]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    KTAB = S["kind_tab"]
    z = p.z

    def run_to_probe():
        for _ in range(4000):
            z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == LOGP:
                regs = z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                lines.append(stream_text(z.read_memory(hl, 48)).rstrip("."))
                z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")

    def tick(n=1):
        for _ in range(n):
            z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def farcall(far, label, a=0):
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S[far]) + [0x7D, 0x32] + w16(RES))
        return p.rb(RES)

    def recalc():
        stub([0x21] + w16(S["hero_recalc"]) + [0xCD] + w16(S["far6"]))

    def bag():
        b = list(z.read_memory(BAG, 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20) if b[3 * i]]

    def worn():
        b = list(z.read_memory(WORN, 12))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(4)]

    def kt(f):
        return p.rb(KTAB + S[f] + p.rb("HERO_KIND"))

    def stats():
        return dict(bon=kt("KT_BONUS"), die=kt("KT_DIE"), df=p.rb("HERO_DEF"), gmp=p.rb("GEAR_MP"))

    def fmt(slot):
        stub([0x3E, slot, 0x11] + w16(RES) + [0x21] + w16(S["it_fmt"]) + [0xCD] + w16(S["far6"])
             + [0xAF, 0x12])
        raw = bytes(z.read_memory(RES, 40))
        return raw[:raw.index(0)].decode()

    def setworn(slot, name, ist):
        p.wmem(WORN + slot * 3, [I(name) if name else 0, 1 if name else 0, ist])

    def act(*keys):
        lines.clear()
        t0 = p.rw("TURN_COUNTER")
        p.turn(*keys)
        return p.rw("TURN_COUNTER") - t0, list(lines)

    def scene(cls):
        p.proto_start = 1
        p.boot(cls)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        p.set_ent(0, HP=200, MAXHP=200)
        p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8, MODE=0, REACT=0, FLT=0, FLAGS=EF_ACTIVE | EF_PLAYER)
        tick(3)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()
        p.wmem(BAG, [0] * 60)
        stub([0x21] + w16(S["pot_sync"]) + [0xCD] + w16(S["far6"]))
        return room

    col = HX + 3

    def pick(room, name, qty):
        """Floor entry {name, qty} one step in front; walk onto it; returns (turns, lines, entry byte, bag)."""
        free = [i for i in range(S["FLOOR_MAX"]) if p.rb(FL + i * FLS) == S["FL_EMPTY"]]
        e = free[0]
        p.wmem(FL + e * FLS, [room | FLS1, col, I(name) if isinstance(name, str) else name, qty])
        p.wmem(S["ROOM_MAP"] + (IROW - 1) * 32 + col, [S["T_ITEM0"] + 2] * 2)
        p.wmem(S["ROOM_MAP"] + IROW * 32 + col, [S["T_ITEM0"] + 3] * 2)
        d, ln = act("L")
        res = (d, ln, p.rb(FL + e * FLS), bag())
        p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8)       # back for the next one
        tick(2)
        return res

    # ---- G2-3: HELM FL_QTY 8 -----------------------------------------------------------
    room = scene(K_KNIGHT)
    d, ln, ent, b = pick(room, "H_HELM", 8)
    check("G2-3 floor HELM FL_QTY 8: 1 turn, the pickup line, entry gone, bag I $07; the page ' -1' only",
          (d, ln, ent, b, fmt(0)) == (1, ["YOU PICK UP HELM"], S["FL_EMPTY"], [(I("H_HELM"), 1, 0x07)], " -1"),
          (d, ln, ent, b))
    for name, qty, ist, line in (("W_LONG", 1, 0x00, " 1D8+0 ATK+1"), ("W_LONG", 2, 0x01, " +1 1D8+1 ATK+1"),
                                 ("W_LONG", 3, 0x02, " +2 1D8+2 ATK+1"), ("A_CHAIN", 1, 0x00, " DEF+2"),
                                 ("A_CHAIN", 8, 0x07, " -1 DEF+1"), ("H_HOOD", 3, 0x02, " +2 MP+3")):
        scene(K_KNIGHT)
        d, ln, ent, b = pick(room, name, qty)
        f = fmt(0)
        want_f = line.replace("1D8+0", "1D8") if ist == 0 and name == "W_LONG" else line
        check(f"G2-3 pickup {name} FL_QTY {qty}: I ${ist:02X}, page '{want_f.strip()}'",
              (b, f) == ([(I(name), 1, ist)], want_f), (b, f))

    # ---- G2-4: CHAIN FL_QTY 3, equip -----------------------------------------------------
    room = scene(K_KNIGHT)
    d, ln, ent, b = pick(room, "A_CHAIN", 3)
    f = fmt(0)
    m0 = bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"]))
    p.wmem(S["PAGE_MAP_SAVE"], list(m0))
    p.wmem(S["ROOM_MAP"], [0xEE] * S["PLAY_CELLS"])
    p.wb("PAGE_VERB", S["VB_EQUIP"])
    p.wb("PAGE_SLOT", 0)
    lines.clear()
    r = farcall("far1", "page_post")
    st = stats()
    check("G2-4 floor CHAIN FL_QTY 3: page ' +2 DEF+4'; equipped (Leather -> bag, I travels): HERO_DEF 4",
          (f, r, worn()[1], st["df"], (I("A_LEATHER"), 1, 0) in bag()) ==
          (" +2 DEF+4", 1, (I("A_CHAIN"), 1, 0x02), 4, True), (f, r, worn(), st, bag()))

    # ---- G2-5 / G2-6 / G2-8: hero_recalc and the page on poked worn ISTATEs ---------------
    scene(K_KNIGHT)
    setworn(0, "W_LONG", 0x01)
    recalc()
    s1 = stats()
    setworn(0, "W_LONG", 0x00)
    recalc()
    s0 = stats()
    setworn(0, "W_LONG", 0x21)                                  # m +1, q +1: v 2
    recalc()
    s2 = stats()
    check("G2-5 worn LONG I $01: KT_BONUS +1 / KT_DIE 8; I $00: 0; I $21 (m+1 q+1): +2",
          (s1["bon"], s1["die"], s0["bon"], s2["bon"]) == (1, 8, 0, 2), (s1, s0, s2))
    scene(K_WIZARD)
    setworn(1, "A_ROBE", 0x07)
    recalc()
    g1 = stats()["gmp"]
    setworn(1, "A_ROBE", 0x02)
    recalc()
    g2 = stats()["gmp"]
    setworn(1, "A_ROBE", 0x00)
    recalc()
    g0 = stats()["gmp"]
    check("G2-6 worn ROBE I $07: GEAR_MP 1; I $02: 4; I $00: 2", (g1, g2, g0) == (1, 4, 2), (g1, g2, g0))
    scene(K_KNIGHT)
    setworn(2, "H_HELM", 0xA7)
    recalc()
    sa = stats()
    f_worn = fmt(20 + S["WS_HELM"])                              # slots 20..23 = WORN (BAG + 60)
    setworn(1, "A_LEATHER", 0x00)
    setworn(2, "H_HELM", 0xA7)
    recalc()
    check("G2-8 worn HELM I $A7 (m -3, q -1): page ' WORN OUT DEF-3'; the summed DEF clamps at 0 (Leather 1 + -3)",
          (f_worn, sa["df"], stats()["df"]) == (" WORN OUT DEF-3", 0, 0), (f_worn, sa, stats()))

    # ---- G2-7: every other non-ammo pickup keeps I 0 ----------------------------------------
    got = []
    for name in ("P_MANA", "F_CHEESE", "S_FEAR", "S_ENCHANT", "BOOK", "BOW", "C_MIGHT", "C_SCARAB", "H_KING",
                 "W_CLEAVER", "A_SILK", "H_MIRROR"):
        room = scene(K_KNIGHT)
        d, ln, ent, b = pick(room, name, 1)
        got.append((name, b))
    check("G2-7 potion / food / scroll / book / bow / charm / uniques (FL_QTY 1): bag I $00",
          all(b == [(I(n), 1, 0)] for n, b in got), got)
    room = scene(K_KNIGHT)
    d, ln, ent, b = pick(room, S["IT_POTION"], 1)                # the legacy PROTO / 3B stand-in = a Heal potion
    check("G2-7 the legacy IT_POTION entry: a Heal potion, I $00", b == [(I("P_HEAL"), 1, 0)], b)

    # ---- G2-9: the pools --------------------------------------------------------------------
    gp = M.gear_pool
    check("G2-9 Warrior D1 pool [LEATHER, HELM]; Mage D3 [IRON, ROBE, HOOD, MIGHT, WARD, FIRE, MANA, PLENTY]",
          gp(1, M.HERO_WARRIOR) == [I("A_LEATHER"), I("H_HELM")] and
          gp(3, M.HERO_MAGE) == [I(n) for n in ("W_IRON", "A_ROBE", "H_HOOD", "C_MIGHT", "C_WARD", "C_FIRE",
                                                "C_MANA")] + [I("C_PLENTY")], (gp(1, M.HERO_WARRIOR), gp(3, M.HERO_MAGE)))
    check("G2-9 pool sizes Warrior D1 2 D2 6 D3 9 D4 10 D6 11; Mage D1 2 D2 6 D3 8 D4 9",
          [len(gp(d, M.HERO_WARRIOR)) for d in (1, 2, 3, 4, 6)] == [2, 6, 9, 10, 11] and
          [len(gp(d, M.HERO_MAGE)) for d in (1, 2, 3, 4)] == [2, 6, 8, 9])

    # ---- G2-10: the decode on every ISTATE value (a worn Long Sword; the page shows v) -----------
    scene(K_KNIGHT)
    bad = []
    for ist in range(256):
        setworn(0, "W_LONG", ist)
        v = M.istate_v(ist)
        recalc()
        f = fmt(20 + S["WS_WEAPON"])
        bon = kt("KT_BONUS")
        bon_exp = v
        sg = lambda n: ("+%d" % n) if n >= 0 else ("-%d" % -n)       # noqa: E731
        if (ist >> 5) & 7 == 5:                                      # m -3: ' WORN OUT'
            pre = " WORN OUT"
        else:
            pre = "" if v == 0 else " " + sg(v)
        want = pre + " 1D8" + ("" if v == 0 else sg(v)) + " ATK+1"
        bon_exp = v if v >= -128 else 0
        if f != want or (bon - (256 if bon > 127 else 0)) != bon_exp:
            bad.append((hex(ist), v, f, want, bon))
    check("G2-10 all 256 ISTATE values: the page ' v 1D8+v ATK+1' (' WORN OUT' at m -3) and KT_BONUS == m + q",
          not bad, bad[:3])


if __name__ == "__main__":
    sys.exit(main())
