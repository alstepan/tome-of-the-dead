#!/usr/bin/env python3
"""3E-T8 gear: hero_recalc (src/gear6.asm, R6), the effects overlay
(3E-T12: R6 src/fx6.asm fx_main, far6; was the fx overlay), the page-verb
consumer (page_post, src/menu1.asm), ench_any, the page stat line
(it_fmt). Release build (DEBUG_KIT=0), PROTO room A, every monster parked.
game.md §8 gear table, §8.6 uniques, §8.11 "3E simplification".

  N   kit start == the B20 numbers: Warrior atk 3 / eva 2 / 1d6+0 / DEF 1 / MP 6/6,
      period 8; Mage atk 1 / eva 1 / 1d4+0 / DEF 0 / MP 12/12 (10 + Robe 2), period 6
  E   fx_main EQUIP / REMOVE (direct): the swap (old weapon takes the bag slot), an
      empty slot (bag compacted), REMOVE -> the bag end, full bag refused (nothing,
      no turn), lines "YOU EQUIP <name>" / "YOU REMOVE <name>", FXR_TURN; stats
      follow (Long Sword atk +1 1d8, Chain DEF 2, Helm DEF +1, fists 1d2)
  F   fx_main leaves ROOM_MAP / LVL_STATE / LP_STATE / P_ENTITIES /
      RNG / FLOOR_LIST / MK_RAM / ANIM lists unchanged; cost
  U   uniques + charms: King Helm eva +1, Silk Cloak eva +2 + IMMF_POISON, Grave
      Cloak DRAIN R + DARK R, + Mirror Helm DARK X (per-field max, not OR), +
      Grave Ring (I < X: stays X) MP +2, Fire Ring FIRE R, Might atk +1, Ward DEF
      +1, Cleaver 1d10 +1 atk +1
  P   page_post consumes injected PAGE_VERB / PAGE_SLOT once: EQUIP -> L 1 (turn),
      applied, PAGE_VERB 0, the map restored from the page's save; DRINK Heal at
      full HP -> L 0, NO NEED, nothing consumed (T12); DISCARD -> "YOU DISCARD
      <name>", 0 turns
  X   ench_any: m +1 .. +3 (KT_BONUS 1..3), the 4th and fists -> unchanged
  L   level steps exactly once with gear: XP 922 -> L8: atk base +2 (+1 Might),
      eva +1; an equip afterwards keeps them (no double count)
  M   MP: remove the Robe -> MAXMP 10, MP clamped 10; re-equip -> 12, MP stays 10;
      period: Mana amulet 3, + Plate 6, Plate alone 12; regen +1 on the 3rd turn
  C   combat reads them: deal_hit PHYS 3 on the hero = 2 (DEF 1) / 1 (Chain DEF 2);
      DARK on the Mirror Helm = 0 (X)
  S   the page stat line text (it_fmt) for a few types
Run: ZRCP_PORT=<port> python3 tests/equip.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, stand_y, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER = 1, 2
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
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
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        if KIT:
            print("[skip] equip needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"equip: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    KTAB = S["kind_tab"]
    z = p.z

    def run_to_probe():
        for _ in range(400):
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
        """far<n> label with A; L -> RES."""
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S[far]) + [0x7D, 0x32] + w16(RES))
        return p.rb(RES)

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        stub([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
        return p.rb("FX_OP")

    def stats(kind=None):
        k = p.rb("HERO_KIND") if kind is None else kind
        g = lambda f: p.rb(KTAB + S[f] + k)  # noqa: E731
        return dict(atk=g("KT_ATK"), eva=g("KT_EVA"), die=g("KT_DIE"), bon=g("KT_BONUS"), df=p.rb("HERO_DEF"),
                    mp=p.rb("MP"), maxmp=p.rb("MAXMP"), per=p.rb("MP_PER"), gmp=p.rb("GEAR_MP"),
                    res=tuple(z.read_memory(S["HERO_RES"], 3)), imm=p.rb("HERO_IMM"))

    def bag():
        b = list(z.read_memory(S["BAG"], 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20) if b[3 * i]]

    def worn():
        b = list(z.read_memory(S["WORN"], 12))
        return [b[3 * i] for i in range(4)]

    def put(bag_items=(), worn_items=None):
        flat = [x for n in bag_items for x in (I(n), 1, 0)]
        p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))
        if worn_items is not None:
            p.wmem(S["WORN"], [x for n in worn_items for x in ((I(n), 1, 0) if n else (0, 0, 0))])

    def recalc():
        farcall("far6", "hero_recalc")

    def scene(hero=K_KNIGHT):
        p.boot(hero)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        p.tick(3)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def state():
        return {k: bytes(z.read_memory(S[a], n)) for k, a, n in (
            ("ROOM_MAP", "ROOM_MAP", S["PLAY_CELLS"]), ("LVL_STATE", "LVL_STATE", 320),
            ("LP_STATE", "LP_STATE", S["LP_END"] - S["LP_STATE"]), ("P_ENTITIES", "P_ENTITIES", 512),
            ("RNG_STATE", "RNG_STATE", 2), ("FLOOR_LIST", "FLOOR_LIST", 128),
            ("MK_RAM", "MK_RAM", S["MK_RAM_END"] - S["MK_RAM"]), ("ANIM_N", "ANIM_N", 49), ("ANIM_N2", "ANIM_N2", 49))}

    # ======================= N: kit start ========================================
    scene(K_KNIGHT)
    st = stats()
    want = dict(atk=3, eva=2, die=6, bon=0, df=1, mp=6, maxmp=6, per=8, gmp=0, res=(0, 0, 0), imm=0)
    check("N1 Warrior start: atk 3 eva 2 1d6+0 DEF 1 MP 6/6 period 8", st == want, (st, want))
    scene(K_WIZARD)
    st = stats()
    want = dict(atk=1, eva=1, die=4, bon=0, df=0, mp=12, maxmp=12, per=6, gmp=2, res=(0, 0, 0), imm=0)
    check("N2 Mage start: atk 1 eva 1 1d4+0 DEF 0 MP 12/12 (10 + Robe) period 6", st == want, (st, want))

    # ======================= M: MP clamp, periods, regen =========================
    put(["P_HEAL", "F_APPLE"])
    r = fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_ARMOUR"])
    a = (r, p.rb("MP"), p.rb("MAXMP"), p.rb("GEAR_MP"))
    r = fx(S["FX_EQUIP"], 2)
    b = (r, p.rb("MP"), p.rb("MAXMP"), p.rb("GEAR_MP"))
    check("M1 Robe off: MAXMP 10, MP clamped 10; on again: MAXMP 12, MP stays 10",
          (a, b) == ((1, 10, 10, 0), (1, 10, 12, 2)), (a, b))
    pers = []
    put(["C_MANA", "A_PLATE"])
    fx(S["FX_EQUIP"], 0)
    pers.append(p.rb("MP_PER"))
    fx(S["FX_EQUIP"], 0)                           # Plate (the Robe goes to the bag)
    pers.append(p.rb("MP_PER"))
    fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_CHARM"])
    pers.append(p.rb("MP_PER"))
    check("M2 MP_PER: Mana amulet 3, + Plate 6, Plate alone 12", pers == [3, 6, 12], pers)
    put(["C_SCARAB"], [None, "A_ROBE", None, None])
    fx(S["FX_EQUIP"], 0)
    p.wb("MP", 0)
    p.wb("MP_RG", 0)
    got = []
    for _ in range(6):
        p.turn("WAIT")
        got.append(p.rb("MP"))
    check("M3 Scarab: Mage regen +1 every 3 turns", got == [0, 0, 1, 1, 1, 2], got)

    # ======================= E: equip / remove, F: round trip ====================
    scene(K_KNIGHT)
    put(["P_HEAL", "F_APPLE", "W_LONG", "A_CHAIN", "H_HELM"])
    s0, t0 = state(), p.rw("TURN_COUNTER")
    lines.clear()
    r1 = fx(S["FX_EQUIP"], 2)
    s1 = stats()
    e1 = (r1, worn(), [x[0] for x in bag()], s1["atk"], s1["die"])
    r2 = fx(S["FX_EQUIP"], 3)
    e2 = (r2, worn(), [x[0] for x in bag()], p.rb("HERO_DEF"))
    r3 = fx(S["FX_EQUIP"], 4)
    e3 = (r3, worn(), [x[0] for x in bag()], p.rb("HERO_DEF"), p.ent(0)["POT"])
    check("E1 EQUIP Long Sword (swap: Short Sword takes slot 2): atk 4, 1d8; FXR_TURN",
          e1 == (1, [I("W_LONG"), I("A_LEATHER"), 0, 0], [I("P_HEAL"), I("F_APPLE"), I("W_SHORT"), I("A_CHAIN"),
                                                         I("H_HELM")], 4, 8), e1)
    check("E2 EQUIP Chain Mail (Leather to the bag): DEF 2",
          e2 == (1, [I("W_LONG"), I("A_CHAIN"), 0, 0], [I("P_HEAL"), I("F_APPLE"), I("W_SHORT"), I("A_LEATHER"),
                                                         I("H_HELM")], 2), e2)
    check("E3 EQUIP Helm into the empty slot: the bag compacted (4 left), DEF 3, E_POT kept",
          e3 == (1, [I("W_LONG"), I("A_CHAIN"), I("H_HELM"), 0], [I("P_HEAL"), I("F_APPLE"), I("W_SHORT"),
                                                                   I("A_LEATHER")], 3, 1), e3)
    r4 = fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_HELM"])
    e4 = (r4, worn()[2], [x[0] for x in bag()][-1], p.rb("HERO_DEF"))
    r5 = fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_WEAPON"])
    e5 = (r5, worn()[0], stats()["die"], stats()["bon"], stats()["atk"])
    check("E4 REMOVE Helm -> the bag end, DEF 2; REMOVE the weapon -> fists 1d2, atk 3",
          (e4, e5) == ((1, 0, I("H_HELM"), 2), (1, 0, 2, 0, 3)), (e4, e5))
    check("E5 lines: YOU EQUIP LONG SWORD / CHAIN MAIL / HELM, YOU REMOVE HELM / LONG SWORD",
          lines == ["YOU EQUIP LONG SWORD", "YOU EQUIP CHAIN MAIL", "YOU EQUIP HELM", "YOU REMOVE HELM",
                    "YOU REMOVE LONG SWORD"], lines)
    put(["F_APPLE"] * 20)
    b0, w0 = bag(), worn()
    r6 = fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_ARMOUR"])
    check("E6 REMOVE with a full bag: refused (FX_OP 0), nothing changes",
          (r6, bag() == b0, worn() == w0) == (0, True, True), (r6,))
    s2 = state()
    check("F1 fx_main calls leave ROOM_MAP / LVL_STATE / LP_STATE / P_ENTITIES / RNG / FLOOR_LIST / MK_RAM / "
          "ANIM lists unchanged (no turn by itself)",
          s2 == s0 and p.rw("TURN_COUNTER") == t0, [k for k in s0 if s0[k] != s2[k]])
    # cost: the full fx path (map save + unpack + equip + line + recalc + map back), interrupts off
    put(["W_LONG"])
    z.cmd("set-breakpoint 5")
    p.wb("FX_OP", S["FX_EQUIP"])
    p.wb("FX_ARG", 0)
    ok = p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_fx = p.tstates
    put(["P_HEAL"])
    p.wb("FX_OP", S["FX_DRINK"])
    p.wb("FX_ARG", 5)                              # an empty slot: nothing
    ok2 = p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_nop = p.tstates
    ok3 = p.code([0x21] + w16(S["hero_recalc"]) + [0xCD] + w16(S["far6"]))
    t_rc = p.tstates
    print(f"[info] fx_main EQUIP {t_fx} T, an empty-slot op {t_nop} T, "
          f"hero_recalc {t_rc} T (incl. far6)", flush=True)
    check("F2 fx_main EQUIP <= 20k T (resident: no overlay), hero_recalc <= 6k T", ok and ok2 and ok3
          and t_fx <= 20000 and t_rc <= 6000, (t_fx, t_nop, t_rc))
    scene(K_KNIGHT)

    # ======================= U: uniques, charms ==================================
    def wear(w, b=()):
        put(b, w)
        recalc()
        return stats()
    s = wear(["W_SHORT", "A_LEATHER", "H_KING", None])
    u1 = (s["eva"], s["df"])
    s = wear(["W_SHORT", "A_SILK", None, None])
    u2 = (s["eva"], s["df"], s["imm"])
    s = wear([None, "A_GRAVE", None, None])
    u3 = s["res"]
    s = wear([None, "A_GRAVE", "H_MIRROR", None])
    u4 = s["res"]
    s = wear([None, "A_GRAVE", "H_MIRROR", "C_GRAVE"])
    u5 = (s["res"], s["maxmp"], s["gmp"])
    s = wear([None, None, None, "C_FIRE"])
    u6 = (s["res"], s["maxmp"], s["gmp"])
    s = wear(["W_CLEAVER", None, None, "C_MIGHT"])
    u7 = (s["die"], s["bon"], s["atk"])
    s = wear([None, "A_LEATHER", "H_HELM", "C_WARD"])
    u8 = s["df"]
    s = wear([None, None, None, "C_FROST"])
    u9 = (s["res"], s["maxmp"], s["gmp"])
    R, X, IM = S["RSP_R"], S["RSP_X"], S["RSP_I"]
    check("U1 King Helm eva 3 DEF 2; Silk Cloak eva 4 DEF 1 IMMF_POISON",
          (u1, u2) == ((3, 2), (4, 1, S["IMMF_POISON"])), (u1, u2))
    check("U2 Grave Cloak DRAIN R + DARK R; + Mirror Helm DARK X (max); + Grave Ring (I) stays X, MP +2; "
          "Fire Ring FIRE R (MP back)",
          (u3, u4, u5, u6) == ((0, R | R << 2, 0), (0, R | X << 2, 0), ((0, R | X << 2, 0), 8, 2), ((R << 2, 0, 0), 6, 0)),
          (u3, u4, u5, u6))
    check("U3 Cleaver + Might: 1d10 +1, atk 3 + 1 + 1 = 5; Leather + Helm + Ward DEF 3",
          (u7, u8) == ((10, 1, 5), 3), (u7, u8))
    check("U4 Frost Charm (NEW-MON3): COLD R only (RES_B0 bits 5-4), MP unchanged",
          u9 == ((R << 4, 0, 0), 6, 0), u9)

    # ======================= C: combat reads DEF / RES ===========================
    g = None
    for sl in range(1, 16):
        if p.ent(sl)["KIND"] == K_GOBLIN:
            g = sl
            break

    def deal(dmg, dty):
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + g * S["P_ENT_STRIDE"]) + [0x3E, 0, 0x06, dmg, 0x0E, dty,
                 0x1E, 0, 0xCD] + w16(S["deal_hit"]) + [0x7D, 0x32] + w16(RES))
        stub(p.bank3(inner))
        return p.rb(RES)
    p.set_ent(0, HP=40, MAXHP=40)
    wear(["W_SHORT", "A_LEATHER", None, None])
    c1 = deal(3, S["DTY_PHYS"])
    wear(["W_SHORT", "A_CHAIN", None, None])
    c2 = deal(3, S["DTY_PHYS"])
    wear(["W_SHORT", "A_CHAIN", "H_MIRROR", None])
    c3 = deal(3, S["DTY_DARK"])
    check("C1 deal_hit on the hero: PHYS 3 -> 2 (DEF 1) / 1 (Chain DEF 2); DARK with the Mirror Helm -> 0",
          (c1, c2, c3) == (2, 1, 0), (c1, c2, c3))

    # ======================= X: enchant ==========================================
    wear(["W_SHORT", None, None, None])               # GEAR3: the sword is the only candidate
    xs = []
    for _ in range(4):
        farcall("far6", "ench_any")                   # (its result is in A, lost by far6: read the state)
        xs.append((p.rb(KTAB + S["KT_BONUS"]), z.read_memory(S["WORN"] + 2, 1)[0]))
    wear([None, None, None, None])
    farcall("far6", "ench_any")
    xf = (p.rb(KTAB + S["KT_BONUS"]), list(z.read_memory(S["WORN"], 3)))
    check("X1 ench_any: m +1 .. +3 (bonus 1..3, ISTATE $20..$60), then no change; fists: nothing to enchant",
          (xs, xf) == ([(1, 0x20), (2, 0x40), (3, 0x60), (3, 0x60)], (0, [0, 0, 0])), (xs, xf))

    # ======================= L: level steps once =================================
    scene(K_KNIGHT)
    put([], ["W_SHORT", "A_LEATHER", None, "C_MIGHT"])
    recalc()
    a0 = stats()
    p.wb("XP", 922 & 255)
    p.wb(S["XP"] + 1, 922 >> 8)
    p.wb("XP_UP", 1)
    for _ in range(3):
        p.turn("WAIT")
        if p.rb("LVL") == 8:
            break
    a1 = stats()
    put(["H_HELM"])
    fx(S["FX_EQUIP"], 0)
    a2 = stats()
    check("L1 Might worn: atk 4 eva 2 at L1; XP 922 -> L8: atk 6 eva 3; an equip later keeps 6 / 3",
          (a0["atk"], a0["eva"], p.rb("LVL"), a1["atk"], a1["eva"], a2["atk"], a2["eva"]) == (4, 2, 8, 6, 3, 6, 3),
          (a0, p.rb("LVL"), a1, a2))
    fx(S["FX_REMOVE"], S["PG_SLOT_WORN"] + S["WS_CHARM"])
    check("L2 Might off at L8: atk 5 eva 3", (stats()["atk"], stats()["eva"]) == (5, 3), stats())

    # ======================= P: page_post injection ==============================
    scene(K_KNIGHT)
    put(["P_HEAL", "W_LONG"])
    m0 = bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"]))

    def post(verb, slot):
        p.wmem(S["PAGE_MAP_SAVE"], list(m0))            # page_ovl's save
        p.wmem(S["ROOM_MAP"], [0xEE] * S["PLAY_CELLS"])  # the page clobbered the window
        p.wb("PAGE_VERB", verb)
        p.wb("PAGE_SLOT", slot)
        lines.clear()
        r = farcall("far1", "page_post")
        return (r, p.rb("PAGE_VERB"), p.rb("PAGE_VLAST"),
                bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"])) == m0, list(lines))
    q1 = post(S["VB_EQUIP"], 1) + (worn()[0], bag()[1][0])
    q2 = post(S["VB_DRINK"], 0) + (bag()[0],)
    q3 = post(S["VB_DISCARD"], 1) + (len(bag()),)
    check("P1 page_post EQUIP: L 1, PAGE_VERB 0, PAGE_VLAST EQUIP, map back, the line, applied",
          q1 == (1, 0, S["VB_EQUIP"], True, ["YOU EQUIP LONG SWORD"], I("W_LONG"), I("W_SHORT")), q1)
    check("P2 page_post DRINK Heal at full HP: L 0, consumed verb, NO NEED, potion kept; DISCARD: L 0, "
          "YOU DISCARD SHORT SWORD, bag 1",
          (q2, q3) == ((0, 0, S["VB_DRINK"], True, ["NO NEED"], (I("P_HEAL"), 1, 0)),
                       (0, 0, S["VB_DISCARD"], True, ["YOU DISCARD SHORT SWORD"], 1)), (q2, q3))

    # ======================= S: stat line text ====================================
    def fmt(slot):
        stub([0x3E, slot, 0x11] + w16(RES) + [0x21] + w16(S["it_fmt"]) + [0xCD] + w16(S["far6"])
             + [0xAF, 0x12])                       # xor a / ld (de), a
        raw = bytes(z.read_memory(RES, 40))
        return raw[:raw.index(0)].decode()
    put(["W_CLEAVER", "A_SILK", "F_CHEESE", "P_MANA", "S_FEAR", "W_AXE", "A_ROBE"])
    p.wb(S["BAG"] + 2, 0x40)                         # Cleaver m +2
    p.wb(S["BAG"] + 20, 0xE0)                        # Robe m -1
    got = [fmt(s) for s in range(7)]
    want = [" +2 1D10+3 ATK+1", " DEF+1 DODGE+2", " FOOD+30", " MP+8", "", " 1D10 ATK-1", " -1 MP+1"]   # WEAR-UI: " +m" before the numbers; ITEM-INFO: EVA -> DODGE
    check("S1 it_fmt: Cleaver +2, Silk, Cheese, Mana, Fear (none), Axe, Robe -1", got == want, (got, want))


if __name__ == "__main__":
    sys.exit(main())
