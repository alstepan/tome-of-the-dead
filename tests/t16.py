#!/usr/bin/env python3
"""3E-T16 traps runtime (src/trap6.asm R6 trap_turn (the input-tick decision) /
trap_step (the sequence: effects, lines, flashes) / tele_arm / trap_at; bank-7
turn_input + trap_chk + tpt_intent .srch + end_turn .ex + act_pend's ABL_TRAP
dispatch + ap_stamp's plate fallback; bank-3 trap_hit + the build_room_map
stamp (TILE_ATTRS[T_TRAP] = the type ink); bank-1 tf_line; R6 drop_put's trap
cols). Release build (DEBUG_KIT=0). game.md §1.5 (+ "As built"), §2.3, §2.2,
§6 V3, §8.11 (3).

PROTO room A, monsters parked, the hero on storey 1 (one trap entry at a time:
trap_chk takes the room's first unspent entry, the generator puts <= 1 there):
  A  trigger rules (Warrior): a hidden DART one col ahead fires on the step that
     first brings it under the body (line, 1d4+1 - DEF, POISON 6, known + drawn
     T_TRAP with ink $42 once the hero is off it); WAIT / steps still over it do
     not re-fire; walking off and back on does (re-arms); a jump whose swept cols
     hold it clears it, a jump landing on it fires; a trap on the other storey
     never fires; GAS (ASLEEP 4, the $44 flash, both lines, spent, never drawn),
     ALARM (the 3E bell line, spent), TELEPORT (spent, YOU ARE TELEPORTED!,
     GS_PLAYING after)
  B  search (Warrior): WAIT finds a hidden trap 6 cols off the body (both sides)
     within 16 waits ("TRAP FOUND: DART", drawn, ink); 7 cols off never; walking
     past a hidden one never finds it
  C  Mage sense: found at <= 2 cols after any turn (no RNG), not at 3; the
     TELEPORT / GAS / ALARM names and inks; after a held (asleep) Wait too
  V  flashes: trigger (plate $47 then its ink / erased, hero the type ink), find
     (the plate blinks $47 / off twice, then its ink), teleport scroll + trap
     (hero $43 >= 2 ticks before the room change and >= 2 after), nothing left
     tinted after
  O  item / trap overlap: drop_put skips a hidden trap col; ap_stamp keeps a
     known plate; build_room_map never hides an item under T_TRAP; the Silk
     Cloak's poison immunity against the DART
Generated levels (seed_fixed):
  D  persistence: a trap the Mage senses in a neighbour room stays known (map
     T_TRAP + its ink) after leaving and re-entering it twice (scroll path); the
     room-entry sense (a trap 2 cols off the arrival body found on entry)
  P  placement: live TRAP_LIST of generated D1 levels (+ a Python model sweep
     D1..D8 x both heroes) — every trap in a present room != start / lair /
     Sanctum, <= 1 per room, hidden + unspent at generation, col 6..25, clear of
     every ladder / shaft / exit / arrival / pit / block footprint (+-1) and of the
     floor items (items_model.trap_col_ok_indep), never in the hero's spawn room
  F  fuzz: random walks / jumps / waits with hidden traps poked next to the hero:
     every fire / find matches the rule from the pre / post body, the map and
     the displayed attr of every known trap of CUR_ROOM, hidden ones never drawn
  T  costs (direct, interrupts off): trap_chk with no trap in the room, the
     decision of each event, every trap_step of each sequence
Run: ZRCP_PORT=<port> python3 tests/t16.py
"""
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, stand_y, attr_at, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER, EF_LEFT, EF_DYING = 1, 2, 8, 16
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
STF, ST1, ST2 = S["ST_FLAGS"], S["ST_T1"], S["ST_T2"]
TL, TN = S["TRAP_LIST"], S["TRAP_N"]
KNOWN, SPENT, S1 = S["TRF_KNOWN"], S["TRF_SPENT"], S["TRF_S1"]
DART, GAS, TELE, ALARM = range(4)
INK = (0x42, 0x44, 0x43, 0x46)
NAME = ("DART", "GAS", "TELEPORT", "ALARM")
T_TRAP = S["T_TRAP"]
FIRE_LINE = {DART: "A DART HITS YOU!", GAS: "SLEEPING GAS!", ALARM: "A BELL RINGS. NOTHING COMES",
             TELE: "YOU ARE TELEPORTED!"}


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
            print("[skip] t16 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"t16: {len(fails)} failed" + (f": {fails[:12]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
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

    def park():
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)

    def heal():
        p.set_ent(0, HP=250, MAXHP=250)
        p.wmem(STF, [0])
        p.wmem(ST1, [0])
        p.wmem(ST2, [0])

    def put_hero(x, s=1, left=False):
        y = stand_y(s, 6)
        p.set_ent(0, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, REACT=0, FLT=0,
                  FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0))
        tick(2)

    def scene(hero=K_KNIGHT):
        p.proto_start = 1
        p.boot(hero)
        park()
        heal()
        p.wmem(TL, [0] * 13)
        put_hero(HX)
        tick(2)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def trap(col, typ, s=1, known=False, room=None):
        room = p.rb("CUR_ROOM") if room is None else room
        p.wmem(TL, [room | (S1 if s else 0) | (KNOWN if known else 0), col | (typ << 5)] + [0] * 10 + [1])

    def ent():
        return tuple(z.read_memory(TL, 2))

    def cell(col, s=1, room_map=True):
        return p.rb(S["ROOM_MAP"] + (9 * s + 7) * 32 + col)

    def shown_attr(col, s=1):
        tick(2)
        return attr_at(p.frame(), col, 9 * s + 7)

    def stub(body):
        assert p.pc() == S["wait_tick"], hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(S["wait_tick"]))
        z.cmd("set-register PC=%d" % STUB)
        run_to_probe()

    def hero_attr(fr, hero):
        return attr_at(fr, hero["X"] + 1, hero["Y"] + 2)

    def act(*keys, per_tick=None):
        lines.clear()
        t0 = p.rw("TURN_COUNTER")
        ok = p.turn(*keys, per_tick=per_tick)
        return ok, p.rw("TURN_COUNTER") - t0, list(lines)

    # ======================= A: trigger rules =====================================
    scene(K_KNIGHT)
    room = p.rb("CUR_ROOM")
    print("[info] PROTO room %d storey-1 rows 16/17: %s / %s" % (
        room, list(z.read_memory(S["ROOM_MAP"] + 16 * 32, 32)), list(z.read_memory(S["ROOM_MAP"] + 17 * 32, 32))),
        flush=True)
    t = HX + 3
    trap(t, DART)
    hp0, dfn = p.ent(0)["HP"], p.rb("HERO_DEF")
    rec = []
    ok, d, ln = act("L", per_tick=lambda fr, hero: rec.append(
        (p.rb(S["TILE_ATTRS"] + T_TRAP), hero["FLT"], hero["FLA"], hero_attr(fr, hero))))
    e = p.ent(0)
    lost = hp0 - e["HP"]
    want_lost = {max(1, r - dfn) for r in range(2, 6)}
    a1 = (ok, d, e["X"], ln[:2], lost in want_lost, p.rb(STF) & S["STS_POISON"], p.rb(ST2) >> 4, ent()[0] & (KNOWN | SPENT),
          cell(t), p.rb("FX_DROP"))
    check("A1 hidden DART one col ahead: the step fires it — 'A DART HITS YOU!' + 'YOU ARE POISONED!', "
          "1d4+1-DEF HP, POISON 6, known (not spent), T_TRAP in the map, 1 turn",
          a1 == (True, 1, HX + 1, ["A DART HITS YOU!", "YOU ARE POISONED!"], True, S["STS_POISON"], 6, KNOWN, T_TRAP, 0),
          (a1, lost, want_lost, ln))
    v1 = (any(a == 0x47 for a, *_ in rec), any(f and fa == 0x42 for _, f, fa, _ in rec),
          any(ha == 0x42 for *_, ha in rec), p.rb(S["TILE_ATTRS"] + T_TRAP), p.ent(0)["FLT"])
    check("V1 DART trigger: the plate attr $47 on a tick of the turn, then its ink $42; the hero "
          "flashes $42 (E_FLA + the displayed body cell); no flash left after", v1 == (True, True, True, 0x42, 0),
          (v1, rec))
    heal()
    _, _, ln_w = act("WAIT")
    _, _, ln_1 = act("L")
    _, _, ln_2 = act("L")
    x2 = p.ent(0)["X"]
    check("A2 WAIT on it and steps that keep it under the body: no re-fire",
          ("A DART HITS YOU!" not in ln_w + ln_1 + ln_2, x2) == (True, HX + 3), (ln_w, ln_1, ln_2, x2))
    _, _, ln_3 = act("L")                      # body t+1.. : off it
    sa = shown_attr(t)
    check("A3 off the plate: the displayed cell has the DART ink $42, the map T_TRAP",
          (sa, cell(t), "A DART HITS YOU!" in ln_3) == (0x42, T_TRAP, False), (sa, cell(t), ln_3))
    heal()
    hp1 = p.ent(0)["HP"]
    _, d4, ln_4 = act("H")                     # turn-around + the step back on
    check("A4 walking back on (DART re-arms): fires again, 1 turn",
          (d4, ln_4[:1], p.ent(0)["HP"] < hp1, ent()[0] & SPENT) == (1, ["A DART HITS YOU!"], True, 0), (d4, ln_4))
    # jumps: over (t in the swept cols x+3..x+5) / onto
    heal()
    put_hero(t - 4)
    hp2 = p.ent(0)["HP"]
    ok5, d5, ln_5 = act("K", "L")
    check("A5 a jump over it (t in x+3..x+5): no fire",
          (ok5, d5, p.ent(0)["X"], "A DART HITS YOU!" in ln_5, p.ent(0)["HP"]) == (True, 1, t + 2, False, hp2),
          (ok5, d5, p.ent(0)["X"], ln_5))
    heal()
    put_hero(t - 7)
    p.wb("JUMP_TURN", 0xFF)
    p.wb(S["JUMP_TURN"] + 1, 0xFF)
    ok6, d6, ln_6 = act("K", "L")
    check("A6 a jump landing on it (body t-1..t+1): fires",
          (ok6, d6, p.ent(0)["X"], ln_6[:1]) == (True, 1, t - 1, ["A DART HITS YOU!"]), (ok6, d6, p.ent(0)["X"], ln_6))
    # other storey
    heal()
    put_hero(HX)
    trap(HX + 3, DART, s=0)
    _, _, ln_7 = act("L")
    check("A7 the same col on the other storey: never fires", (ln_7, ent()[0] & (KNOWN | SPENT)) == ([], 0), ln_7)
    # GAS (a fresh room map: A1..A6 left T_TRAP at HX + 3)
    scene(K_KNIGHT)
    heal()
    trap(HX + 3, GAS)
    fl = []
    pa = []
    _, d8, ln_8 = act("L", per_tick=lambda fr, hero: (fl.append((hero["FLT"], hero["FLA"])),
                                                      pa.append((p.rb(S["TILE_ATTRS"] + T_TRAP), cell(HX + 3)))))
    a8 = (d8, ln_8[:2], p.rb(STF) & 3, p.rb(ST1) >> 4 in (3, 4), ent()[0] & SPENT, cell(HX + 3) != T_TRAP,
          any(f > 0 and a == 0x44 for f, a in fl))
    check("A8 GAS: 'SLEEPING GAS!' + 'YOU FALL ASLEEP', ASLEEP ~4, the $44 flash, spent, never drawn",
          a8 == (1, ["SLEEPING GAS!", "YOU FALL ASLEEP"], S["HOLD_ASLEEP"], True, SPENT, True, True), (a8, ln_8, fl))
    check("V2 GAS trigger: the plate shown $47 (T_TRAP) on a tick, erased at the end; hero $44, no flash left",
          (any(a == 0x47 and c == T_TRAP for a, c in pa), cell(HX + 3) != T_TRAP, p.ent(0)["FLT"]) == (True, True, 0),
          (pa, fl))
    heal()
    tick(4)
    _, _, ln_8b = act("H")
    _, _, ln_8c = act("L")
    check("A9 a spent GAS never fires again", "SLEEPING GAS!" not in ln_8b + ln_8c, (ln_8b, ln_8c))
    # ALARM
    put_hero(HX)
    heal()
    trap(HX + 3, ALARM)
    _, d10, ln_10 = act("L")
    check("A10 ALARM (3E stub): 'A BELL RINGS. NOTHING COMES', spent",
          (d10, ln_10, ent()[0] & SPENT) == (1, ["A BELL RINGS. NOTHING COMES"], SPENT), (d10, ln_10))
    # TELEPORT
    put_hero(HX)
    heal()
    trap(HX + 3, TELE)
    tl = []
    _, d11, ln_11 = act("L", per_tick=lambda fr, hero: tl.append((p.rb("CUR_ROOM"), hero["FLT"], hero["FLA"],
                                                                  hero_attr(fr, hero))))
    for _ in range(10):
        tick()
        tl.append((p.rb("CUR_ROOM"), p.ent(0)["FLT"], p.ent(0)["FLA"], hero_attr(p.frame(), p.ent(0))))
    check("V3 TELEPORT trap: the hero shows $43 on >= 2 ticks before the room change and >= 2 after "
          "arrival; nothing tinted at the end", tele_ok(tl, room) and tl[-1][3] != 0x43 and p.ent(0)["FLT"] == 0, tl)
    check("A11 TELEPORT: spent, 'YOU ARE TELEPORTED!', 1 turn, GS_PLAYING, EXIT_KIND 0 after",
          (d11, "YOU ARE TELEPORTED!" in ln_11, ent()[0] & SPENT, p.rb("GAME_STATE"), p.rb("EXIT_KIND")) ==
          (1, True, SPENT, 2, 0), (d11, ln_11))

    # teleport scroll (quick slot 7, PROTO: the room set A..D)
    scene(K_KNIGHT)
    p.wmem(S["BAG"], [S["IT_S_TELEPORT"], 1, 0] + [0] * 57)
    stub([0x21] + w16(S["pot_sync"]) + [0xCD] + w16(S["far6"]))
    p.select_slot(7)
    r0 = p.rb("CUR_ROOM")
    tl = []
    _, d12, ln_12 = act("FIRE", per_tick=lambda fr, hero: tl.append((p.rb("CUR_ROOM"), hero["FLT"], hero["FLA"],
                                                                     hero_attr(fr, hero))))
    for _ in range(10):
        tick()
        tl.append((p.rb("CUR_ROOM"), p.ent(0)["FLT"], p.ent(0)["FLA"], hero_attr(p.frame(), p.ent(0))))
    check("V4 TELEPORT scroll: 1 turn, the hero shows $43 on >= 2 ticks before the room change and >= 2 "
          "after arrival; nothing tinted at the end",
          d12 == 1 and "YOU ARE TELEPORTED!" in ln_12 and tele_ok(tl, r0) and tl[-1][3] != 0x43, (d12, ln_12, tl))

    # ======================= B: search ============================================
    blink = []

    def search(col, n=16):
        trap(col, DART)
        for i in range(n):
            heal()
            blink.clear()
            _, _, ln = act("WAIT", per_tick=lambda fr, hero: blink.append(attr_at(fr, col, 16)))
            if ent()[0] & KNOWN:
                for _ in range(4):
                    tick()
                    blink.append(attr_at(p.frame(), col, 16))
                return i + 1, ln
        return None, []
    scene(K_KNIGHT)
    nb, lnb = search(HX + 2 + 6)
    seq = [a for k, a in enumerate(blink) if k == 0 or blink[k - 1] != a]
    sa = shown_attr(HX + 8)
    check("V5 find: the plate blinks on the displayed screen bright $47 / off twice, then its ink $42",
          "71,0,71,0,66" in ",".join(str(a) for a in seq) and sa == 0x42, (blink, seq))
    check("B1 WAIT searches: a hidden DART 6 cols right of the body found (1 in 2 a wait), "
          "'TRAP FOUND: DART', drawn with ink $42",
          (nb is not None, lnb, cell(HX + 8), sa) == (True, ["TRAP FOUND: DART"], T_TRAP, 0x42), (nb, lnb, sa))
    nb2, _ = search(HX + 2 + 7)
    nb3, _ = search(HX - 6)
    nb4, _ = search(HX - 7)
    check("B2 7 cols right never (16 waits); 6 cols left found; 7 cols left never",
          (nb2, nb3 is not None, nb4) == (None, True, None), (nb2, nb3, nb4))
    trap(HX - 2, GAS)
    _, _, ln_b5 = act("L")
    check("B3 the Warrior walking past a hidden trap 2 cols off: not found (no wait, no sense)",
          (ent()[0] & KNOWN, ln_b5) == (0, []), ln_b5)

    # ======================= C: Mage sense ========================================
    scene(K_WIZARD)
    res = []
    for k, typ in enumerate((TELE, GAS, ALARM, DART)):
        x0 = 8 + 3 * k
        col = x0 + 5
        put_hero(x0)
        trap(col, typ)
        _, _, l1 = act("H")                    # x0-1: 6 cols from x, 4 off the body: not sensed
        k1 = bool(ent()[0] & KNOWN)
        put_hero(x0)
        _, _, l2 = act("L")                    # x0+1: t - x = 4 (2 off the body): sensed
        k2 = bool(ent()[0] & KNOWN)
        put_hero(2)
        sa = shown_attr(col)
        res.append((NAME[typ], k1, l1, k2, l2, cell(col), sa))
    want = [(NAME[ty], False, [], True, ["TRAP FOUND: " + NAME[ty]], T_TRAP, INK[ty]) for ty in (TELE, GAS, ALARM, DART)]
    check("C1 Mage sense (no RNG, any turn): a trap 2 cols off the body found, 4 off not; "
          "'TRAP FOUND: TELEPORT / GAS / ALARM / DART', drawn with the type inks $43 / $44 / $46 / $42", res == want,
          res)
    put_hero(HX)
    trap(HX - 2, GAS)
    _, _, lc = act("L")                        # x+1: t - x = -3 (3 off the body, left)
    kc = bool(ent()[0] & KNOWN)
    put_hero(HX)
    _, _, lc2 = act("H")                       # x-1: t - x = -1
    check("C2 left side: 3 off the body not sensed, then 1 off sensed",
          (kc, lc, lc2) == (False, [], ["TRAP FOUND: GAS"]), (kc, lc, lc2))
    put_hero(HX)
    trap(HX + 4, ALARM)
    p.wb(STF, S["HOLD_ASLEEP"])
    p.wb(ST1, 0x30)
    lines.clear()
    t0 = p.rw("TURN_COUNTER")
    p.until(lambda: p.rw("TURN_COUNTER") != t0 and p.idle(), 80)
    tick(2)
    check("C3 an asleep Mage's held Wait still senses (no search roll): found, 'TRAP FOUND: ALARM'",
          (bool(ent()[0] & KNOWN), "TRAP FOUND: ALARM" in lines, p.rw("TURN_COUNTER") - t0 >= 1) == (True, True, True),
          (ent(), lines))
    heal()

    # ======================= O: item / trap overlap, Silk =========================
    overlap(p, check, scene, trap, put_hero, heal, ent, cell, act, stub, tick, lines)

    # ======================= P: placement =========================================
    import items_model as M
    import levelgen as G
    bad, st = M.sweep((range(300), range(1, 9)))
    print(f"[info] model sweep 300 masters x D1..D8 x 2 heroes: {st['levels']} levels, {st['traps']} traps, "
          f"{st['dropped_traps']} dropped", flush=True)
    check("P1 model sweep (300 masters, D1..D8, both heroes): 0 trap / item invariant violations", not bad, bad[:3])
    p.proto_start = 0
    live = []
    for si, seed in enumerate((0x1234, 0x9E37, 0x4242, 0x0101, 0xBEEF, 0x7A31)):
        start_level(p, seed, K_KNIGHT if si % 2 == 0 else K_WIZARD)
        b = bytes(z.read_memory(S["LVL_STATE"], 320))
        pres, start, lair = M.rooms_of(b)
        floor = M.read_floor(b)
        san = p.rb("LVL_SANCTUM")
        rooms = []
        for i in range(p.rb(TN)):
            b0, b1 = z.read_memory(TL + 2 * i, 2)
            r, s, c = b0 & 15, (b0 >> 4) & 1, b1 & 31
            rooms.append(r)
            why = []
            if r not in pres or r in (start, lair, san):
                why.append("room")
            if b0 & (KNOWN | SPENT | 0x80) or b1 & 0x80:
                why.append("state")
            if not M.trap_col_ok_indep(b, r, s, c, floor):
                why.append("col")
            if r == p.ent(0)["ROOM"] or r == p.rb("CUR_ROOM"):
                why.append("spawn room")
            if why:
                live.append((seed, r, s, c, why))
        if len(set(rooms)) != len(rooms):
            live.append((seed, "two in a room", rooms))
    check("P2 live D1 levels (6 seeds): every trap legal (room, hidden, cols vs footprints / items, "
          "not the spawn room), <= 1 per room", not live, live)

    # ======================= D: persistence (generated) ===========================
    d_res = persistence(p, check, lines, act, tick, heal, ent, cell, shown_attr)

    # ======================= F: fuzz ==============================================
    fuzz(p, check, lines, act, tick, heal, ent, cell)

    # ======================= T: costs =============================================
    costs(p, check, scene, trap, put_hero, heal)
    return d_res


def tele_ok(tl, room):
    """>= 2 ticks with the $43 hero shown in the old room, >= 2 in the new one."""
    before = [r for r in tl if r[0] == room and r[3] == 0x43]
    after = [r for r in tl if r[0] != room and r[3] == 0x43]
    return len(before) >= 2 and len(after) >= 2


def overlap(p, check, scene, trap, put_hero, heal, ent, cell, act, stub, tick, lines):
    z = p.z
    scene(K_KNIGHT)
    room = p.rb("CUR_ROOM")
    rb = room | 0x80                           # the FL_ROOM byte, storey 1
    # O1 drop_put next to a hidden trap: slot 1 (a Rat, w 2) with its centre col c
    c = HX + 6
    trap(c, DART)
    sl = 1
    kind = p.ent(sl)["KIND"]
    w = p.rb(S["kind_tab"] + S["KT_BW"] + kind)
    hgt = p.rb(S["kind_tab"] + S["KT_BH"] + kind)
    x = c - w // 2
    y = stand_y(1, hgt)
    p.set_ent(sl, ROOM=room, X=x, Y=y, PX=x * 8, PY=y * 8)
    ent0 = [i for i in range(32) if p.rb(S["FLOOR_LIST"] + 4 * i) == 0xFF][0]
    stub([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_R6"], 0xCD] + w16(S["page_bank"])
         + [0xDD, 0x21] + w16(S["P_ENTITIES"] + 32 * sl)
         + [0x3E, S["IT_F_APPLE"], 0x01, S["DROP_NEAR"], 1, 0xCD] + w16(S["drop_put"])
         + [0xF1, 0xCD] + w16(S["restore_page"]))
    fe = list(z.read_memory(S["FLOOR_LIST"] + 4 * ent0, 4))
    check("O1 drop_put: the body's centre col holds a hidden trap -> the drop lands on the nearest other col",
          (fe[0], fe[2], fe[1] != c, abs(fe[1] - c) == 1) == (rb, S["IT_F_APPLE"], True, True), (fe, c, kind, w))
    p.set_ent(sl, ROOM=NOWHERE)
    # O2 ap_stamp keeps a known plate (no item left there)
    put_hero(HX)
    trap(HX + 4, GAS)                          # Warrior: not sensed; make it known by a find poke + draw
    p.wb(S["TRAP_LIST"], room | S1 | KNOWN)
    stub([0x3E, 0x47, 0x32] + w16(S["TILE_ATTRS"] + T_TRAP)
         + [0x3E, HX + 4, 0x11] + w16((T_TRAP << 8) | rb) + [0x21] + w16(S["ap_put_a"]) + [0xCD] + w16(S["far7"]))
    k1 = cell(HX + 4)
    stub([0x3E, HX + 4, 0x11] + w16(rb) + [0x21] + w16(S["ap_stamp_a"]) + [0xCD] + w16(S["far7"]))
    k2 = cell(HX + 4)
    p.wb(S["TRAP_LIST"], room | S1)            # hidden now: the stamp clears it
    stub([0x3E, HX + 4, 0x11] + w16(rb) + [0x21] + w16(S["ap_stamp_a"]) + [0xCD] + w16(S["far7"]))
    k3 = cell(HX + 4)
    check("O2 ap_stamp on a known trap cell with no item: the plate stays; a hidden trap's cell: T_AIR",
          (k1, k2, k3) == (T_TRAP, T_TRAP, 0), (k1, k2, k3))
    # O3 build_room_map: an item on a known trap cell shows (never generated: poked)
    p.wb(S["TRAP_LIST"], room | S1 | KNOWN)
    fe = [i for i in range(32) if p.rb(S["FLOOR_LIST"] + 4 * i) == 0xFF][0]
    p.wmem(S["FLOOR_LIST"] + 4 * fe, [rb, HX + 4, S["IT_F_APPLE"], 1])
    stub([0x3E, room, 0x26, S["ROOM_MAP"] >> 8, 0xCD] + w16(S["build_room"]))
    g = p.rb(S["it_cls"] + (p.rb(S["it_tab"] + S["IT_F_APPLE"]) >> 4))
    k4 = cell(HX + 4)
    p.wmem(S["FLOOR_LIST"] + 4 * fe, [0xFF] * 4)
    stub([0x3E, room, 0x26, S["ROOM_MAP"] >> 8, 0xCD] + w16(S["build_room"]))
    k5 = cell(HX + 4)
    check("O3 build_room_map: an item on a known trap cell keeps its glyph; without it the plate is stamped",
          (k4, k5) == (g, T_TRAP), (k4, k5, g))
    # S Silk Cloak: poison-immune against the DART
    scene(K_KNIGHT)
    p.wmem(S["WORN"], [S["IT_W_SHORT"], 1, 0, S["IT_A_SILK"], 1, 0, 0, 0, 0, 0, 0, 0])
    stub([0x21] + w16(S["hero_recalc"]) + [0xCD] + w16(S["far6"]))
    heal()
    hp0 = p.ent(0)["HP"]
    trap(HX + 3, DART)
    _, d, ln = act("L")
    check("O4 Silk Cloak: the DART hurts but 'YOU ARE UNAFFECTED' replaces the poison (no POISON bit)",
          (d, ln[:2], p.rb(S["ST_FLAGS"]) & S["STS_POISON"], p.ent(0)["HP"] < hp0) ==
          (1, ["A DART HITS YOU!", "YOU ARE UNAFFECTED"], 0, True), (d, ln, p.rb(S["HERO_IMM"])))


def start_level(p, seed, hero):
    z = p.z
    p.load()
    p.wait_state(5)
    p.wb("seed_fixed", 1)
    z.cmd("write-memory %d %d %d" % (S["seed_value"], seed & 255, seed >> 8))
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.menu_start(hero)


def persistence(p, check, lines, act, tick, heal, ent, cell, shown_attr):
    """D: the Mage senses a trap in a neighbour room; leave, re-enter (twice)."""
    z = p.z
    found = None
    for seed in (0x2468, 0x1357, 0x4242, 0x9999, 0x0BAD, 0x7777):
        start_level(p, seed, K_WIZARD)
        z.cmd("set-breakpoint 5 PC=%d" % S["log_push"])
        r0 = p.rb("CUR_ROOM")
        ex = p.rb(S["ROOM_DESC"] + r0 * 16 + 1)
        for side, bit, sbit in (("L", 2, 0x20), ("H", 1, 0x10)):
            if ex & bit:
                found = (seed, side, 1 if ex & sbit else 0)
                break
        if found:
            break
    if not found:
        check("D0 a start room with a horizontal exit", False)
        return None
    seed, side, s = found
    back = "H" if side == "L" else "L"

    def go_out(key, x_edge):
        p.set_ent(0, HP=250, MAXHP=250)
        y = stand_y(s, 6)
        p.set_ent(0, X=x_edge, Y=y, PX=x_edge * 8, PY=y * 8, MODE=0,
                  FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if key == "H" else 0))
        tick(2)
        r = p.rb("CUR_ROOM")
        go_out.lines = []
        for _ in range(4):
            go_out.lines = act(key)[2]
            if p.rb("CUR_ROOM") != r:
                break
        tick(3)
        return p.rb("CUR_ROOM")
    for sl in range(1, 16):
        p.set_ent(sl, ROOM=NOWHERE)
    edge = 28 if side == "L" else 1
    n = go_out(side, edge)
    hx = p.ent(0)["X"]
    col = hx + 2 + 2 + 1 if side == "L" else hx - 3       # 3 off the arrival body, 2 off after one step in
    p.wmem(S["TRAP_LIST"], [n | (S1 if s else 0), col | (GAS << 5)] + [0] * 10 + [1])
    heal()
    for sl in range(1, 16):
        if p.ent(sl)["ROOM"] == n:
            p.set_ent(sl, ROOM=NOWHERE)
    _, _, l1 = act(side)                       # one step in: sensed
    k1 = bool(ent()[0] & KNOWN)
    res = [(k1, l1)]
    for rnd in range(2):
        r_back = go_out(back, 1 if back == "H" else 28)
        for sl in range(1, 16):
            p.set_ent(sl, ROOM=NOWHERE)
        r_in = go_out(side, edge)
        tick(3)
        # the hero arrives at the edge: col is >= 3 cols away, off his body
        sa = attr_at(p.frame(), col, 9 * s + 7)
        res.append((r_back, r_in, cell(col, s), sa))
    # D2 the room-entry sense: back to S, a hidden ALARM in N 2 cols off the arrival body, enter
    go_out(back, 1 if back == "H" else 28)
    ecol = 5 if side == "L" else 26            # arrival x 1 (body 1..3) / 28 (28..30)
    p.wmem(S["TRAP_LIST"], [n | (S1 if s else 0), ecol | (ALARM << 5)] + [0] * 10 + [1])
    r_e = go_out(side, edge)
    tick(2)
    check("D2 the room-entry Mage sense: a trap 2 cols off the arrival body found on the entry turn, drawn "
          "in its ink at once", (r_e, bool(ent()[0] & KNOWN), "TRAP FOUND: ALARM" in go_out.lines, cell(ecol, s),
                                 attr_at(p.frame(), ecol, 9 * s + 7)) == (n, True, True, T_TRAP, 0x46),
          (r_e, n, ent(), go_out.lines, cell(ecol, s)))
    ok = (res[0] == (True, ["TRAP FOUND: GAS"]) and all(x[1] == n and x[0] != n and x[2] == T_TRAP and x[3] == 0x44
                                                       for x in res[1:]))
    check("D1 a sensed trap stays known across leaving / re-entering its room twice: T_TRAP in the "
          "rebuilt map + its ink $44 on the displayed screen", ok, (seed, side, s, n, col, res))
    return res


def fuzz(p, check, lines, act, tick, heal, ent, cell):
    """F: random actions next to a poked hidden trap; every event checked against the rule."""
    z = p.z
    rnd = random.Random(16)
    events = {"fire": 0, "find": 0, "turns": 0}
    bad = []
    draw_bad = []
    for si, seed in enumerate((0x3141, 0x2718, 0x1618, 0x5772)):
        hero = K_KNIGHT if si % 2 == 0 else K_WIZARD
        start_level(p, seed, hero)
        z.cmd("set-breakpoint 5 PC=%d" % S["log_push"])
        for sl in range(1, 16):
            p.set_ent(sl, ROOM=NOWHERE)
        for step in range(60):
            heal()
            p.wb("JUMP_TURN", 0xFF)
            p.wb(S["JUMP_TURN"] + 1, 0xFF)
            room = p.rb("CUR_ROOM")
            e = p.ent(0)
            s = 1 if e["Y"] >= 9 else 0
            if e["Y"] not in (stand_y(0, 6), stand_y(1, 6)):
                p.turn("WAIT")
                continue
            # one hidden trap in this room, near the hero, off his body, off items
            fl = [tuple(z.read_memory(S["FLOOR_LIST"] + 4 * i, 4)) for i in range(32)]
            ok_cols = [c for c in range(max(2, e["X"] - 3), min(29, e["X"] + 6))
                       if not e["X"] <= c <= e["X"] + 2 and cell(c, s) != T_TRAP and
                       not any(f[0] != 0xFF and f[0] & 15 == room and (f[0] >> 7) == s and f[1] == c for f in fl)]
            cur = [tuple(z.read_memory(S["TRAP_LIST"] + 2 * i, 2)) for i in range(6)]
            mine = [i for i, (b0, b1) in enumerate(cur[:p.rb("TRAP_N")]) if b0 & 15 == room and not b0 & SPENT]
            if not mine or not -3 <= (cur[mine[0]][1] & 31) - e["X"] <= 5:
                c = rnd.choice(ok_cols)
                typ = rnd.choice((DART, DART, GAS, ALARM, TELE))
                p.wmem(S["TRAP_LIST"], [room | (S1 if s else 0), c | (typ << 5)] + [0] * 10 + [1])
                cur = [tuple(z.read_memory(S["TRAP_LIST"] + 2 * i, 2)) for i in range(6)]
                mine = [0]
            i0 = mine[0]
            b0, b1 = cur[i0]
            t, typ, ts = b1 & 31, (b1 >> 5) & 3, (b0 >> 4) & 1
            act_k = rnd.choice((("L",), ("H",), ("L",), ("H",), ("WAIT",), ("K", "L"), ("K", "H")))
            px, py = e["X"], e["Y"]
            ok, d, ln = act(*act_k)
            if not ok or not d:
                continue
            events["turns"] += 1
            nb0, nb1 = z.read_memory(S["TRAP_LIST"] + 2 * i0, 2)
            e2 = p.ent(0)
            moved_room = p.rb("CUR_ROOM") != room
            fired = (FIRE_LINE[typ] in ln) and not (typ == TELE and not nb0 & SPENT)
            found = any(x.startswith("TRAP FOUND: ") for x in ln)
            # the logic-time body: after the action (a teleport moved him on: the intended one)
            if moved_room and fired and typ == TELE:
                dx = {"L": 1, "H": -1}.get(act_k[-1], 0) * (6 if "K" in act_k else 1) if act_k != ("WAIT",) else 0
                x, y = px + dx, py
            else:
                x, y = e2["X"], e2["Y"]
            s_now = 1 if y >= 9 else 0
            under = s_now == ts and x <= t <= x + 2
            under0 = (1 if py >= 9 else 0) == ts and px <= t <= px + 2
            exit_turn = moved_room and not (fired and typ == TELE)
            want_fire = under and not under0 and not exit_turn
            if fired != want_fire:
                bad.append(("fire", seed, step, act_k, (px, py), (x, y), t, ts, typ, ln))
            if found:
                dist = t - x
                okf = (not (b0 & KNOWN) and s_now == ts and
                       ((hero == K_WIZARD and -2 <= dist <= 4) or (act_k == ("WAIT",) and -6 <= dist <= 8)))
                if not okf or not nb0 & KNOWN:
                    bad.append(("find", seed, step, act_k, (px, py), (x, y), t, ts, typ, ln))
            elif (hero == K_WIZARD and not (b0 & KNOWN) and not fired and not exit_turn and s_now == ts
                  and -2 <= t - x <= 4):
                bad.append(("sense missed", seed, step, act_k, (x, y), t, ts, ln))
            events["fire"] += fired
            events["find"] += found
            tick(2)
            if p.rb("CUR_ROOM") == room and not moved_room:
                fr = p.frame()
                ex2 = p.ent(0)
                for b0x, b1x in [tuple(z.read_memory(S["TRAP_LIST"] + 2 * k, 2)) for k in range(p.rb("TRAP_N"))]:
                    if b0x & 15 != room:
                        continue
                    c, sx = b1x & 31, (b0x >> 4) & 1
                    known = b0x & KNOWN and not b0x & SPENT
                    on_body = sx == (1 if ex2["Y"] >= 9 else 0) and ex2["X"] <= c <= ex2["X"] + 2
                    if known and (cell(c, sx) != T_TRAP or (not on_body and
                                                             attr_at(fr, c, 9 * sx + 7) != INK[(b1x >> 5) & 3])):
                        draw_bad.append((seed, step, c, sx, cell(c, sx), attr_at(fr, c, 9 * sx + 7)))
                    if not known and cell(c, sx) == T_TRAP:
                        draw_bad.append(("hidden drawn", seed, step, c, sx))
            if p.rb("GAME_STATE") != 2:
                break
    print(f"[info] fuzz: {events}", flush=True)
    check(f"F1 fuzz ({events['turns']} turns, 4 seeds, both heroes): every fire / find matches the rule",
          not bad and events["fire"] > 5 and events["find"] > 3, (bad[:4], events))
    check("F2 fuzz: every known trap of CUR_ROOM drawn (map T_TRAP + its ink), hidden / spent never",
          not draw_bad, draw_bad[:5])


def costs(p, check, scene, trap, put_hero, heal):
    """T: direct T-states (interrupts off) of trap_chk (far7) per case."""
    z = p.z
    out = {}

    def call(tag, wait=0, kind=None):
        heal()
        p.wb("TRP_WAIT", wait)
        e = p.ent(0)
        p.wmem(S["TRP_PRE"], [e["X"] - 1, e["Y"]])
        z.cmd("set-breakpoint 5")
        p.wmem(S["TURN_PEND"], [0, 0, 0, 0])
        p.code([0x21] + w16(S["trap_chk"]) + [0xCD] + w16(S["far7"]))
        out[tag] = p.tstates
        k = 0
        while p.rb("TURN_PEND") & S["TP_ACT"] and k < 8:     # the armed sequence, step by step
            p.wb("TURN_PEND", p.rb("TURN_PEND") & ~S["TP_ACT"] & 0xFF)
            p.wb("TURN_TICK", p.rb("ACT_AT"))
            p.code([0x21] + w16(S["trap_step"]) + [0xCD] + w16(S["far6"]))
            out[f"{tag} step {k}"] = p.tstates
            k += 1
        p.wmem(S["TURN_PEND"], [0, 0, 0, 0])
        p.wb("TURN_TICK", 0)
        p.wb("EXIT_KIND", 0)
    scene(K_KNIGHT)
    p.wmem(S["TRAP_LIST"], [0] * 13)
    call("no trap (TRAP_N 0)")
    other = (p.rb("CUR_ROOM") + 1) & 7
    p.wmem(S["TRAP_LIST"], [other, HX] * 6 + [6])
    call("6 entries, none in the room")
    trap(HX + 20, DART)
    call("one 18 cols off (pre-filtered)")
    trap(HX + 5, DART)
    call("trap_turn, no event")
    trap(HX + 2, DART)
    call("DART (Warrior)")
    trap(HX + 2, GAS)
    call("GAS")
    trap(HX + 2, ALARM)
    call("ALARM")
    trap(HX + 2, TELE)
    call("TELEPORT (EX_TELE only)")
    scene(K_WIZARD)
    trap(HX + 4, DART)
    call("find (Mage sense)")
    trap(HX + 6, DART)
    call("trap_turn, Mage no event")
    print("[info] trap T-states: " + ", ".join(f"{k} {v}" for k, v in out.items()), flush=True)
    check("T1 (incl. this probe's far7 ~0.25k T) no trap in the room / one >= 7 cols off: trap_chk <= 1k T; trap_turn "
          "without an event <= 1.6k T", out["6 entries, none in the room"] <= 1000 and out["one 18 cols off (pre-filtered)"] <= 1000
          and out["trap_turn, no event"] <= 1600
          and out["trap_turn, Mage no event"] <= 1600, out)
    dec = [v for k, v in out.items() if "step" not in k]
    steps = [v for k, v in out.items() if "step" in k]
    check("T2 (incl. the probe's far7 / far6 ~0.25k T) the input-tick decision of every event <= 2.5k T; "
          "every sequence step <= 20k T (the tick budget: tests/budget.py t*)", max(dec) <= 2500 and
          max(steps) <= 20000 and len(steps) >= 10, out)


if __name__ == "__main__":
    sys.exit(main())
