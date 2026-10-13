#!/usr/bin/env python3
"""D3-8: status effects (game.md §6.4, §2.2 "Status step" / "Held hero",
§2.3, §9.1 boss / immunity) on a release build (DEBUG_KIT=0), PROTO room A,
every other monster parked. The effects are applied by deal_hit (combat3.asm);
the step / behaviour is src/status7.asm, the tint render's st_tint, the panel
icons st_sig + stat1.asm. Every log line pushed is captured at log_push (a
breakpoint, decoded from the token stream).

  F   Frost Shard r1 (freeze 2) on a Goblin through the controls: "THE GOBLIN
      IS FROZEN", exactly 2 skipped actions (the cast turn's monster phase and
      the next), then it walks; tint $45 (SLOTREC R_DATTR) while frozen, its
      kind attr after
  H   held hero (FROZEN 2 poked, a walk key held all along): 2 automatic Wait
      turns, HELD_GAP + 1 = 4 ticks apart, the hero never moves, then "YOU CAN
      MOVE AGAIN" and the 3rd turn walks; hero tint $45 and the panel icon
      (row 21 col 30: the FROZEN glyph, attr $45; STAT_SH) while held, blank
      after
  W   a sleeper wakes on damage: Spark on an ASLEEP Goblin -> HOLD clear, "THE
      GOBLIN WAKES UP"; poison wakes too (ASLEEP + POISON 4: the step's HP
      loss at 3)
  G   HOLD_GUARD (D3-8c: FROZEN too; HG1-HG8 below: no HOLD on a held body, guard after
      a thaw, self-freeze 1, POISON adds cap 15):
      STUN_GUARD: deal_hit STUNNED 1 (stub) -> the next monster phase skips
      and sets the guard; a 2nd stun is refused; after the Goblin acted (the
      guard cleared) a 3rd stun lands
  P   poison: POISON 9 on the hero at HP 10 -> HP 7 after 9 turns (losses at
      6, 3, 0), "THE POISON WEARS OFF"; POISON 15 at HP 2 -> never below 1
  C   CONFUSED hero, RNG poked from the model (rng_mod 3 == 0: reversed):
      a walk right -> turns and walks left; not reversed -> walks right; a
      reversed jump that is illegal -> "YOU STUMBLE", the turn is spent;
      a confused Goblin (rng_mod 2 == 0) steps in a random direction
  B   boss (KX_IMM bit 7 poked for the Goblin): FROZEN 2 -> 1, STUNNED 1 ->
      none, CONFUSED 3 -> 1, POISON 9 full, ASLEEP -> "UNAFFECTED"; Slime
      (PHYS R) + boss: STUNNED 2 -> 0
  X   FEAR hero: a bump attack is refused (no turn, "YOU ARE TOO AFRAID TO
      FIGHT!"); a fearful Goblin next to the hero steps away; WEAK hero: no
      jump (no turn), deal_hit dmg - 1 (min 1)
  R   review fixes: woken by the step on the held path with a walk key held
      (INPUT_REPEAT 0) -> no walk until released; CONFUSED mid-ladder never
      rolls; a reversed icon action refused with a line (NO MANA) -> no
      turn, facing restored, no stumble; refused by the direction (melee /
      Power Strike NO TARGET behind, the lead col 0) -> YOU STUMBLE, the turn
      spent (review 2); a plain NO TARGET keeps its line; a FEAR / CONFUSED
      Goblin on the hero's ladder end
      yields (ai_monster's cork rule)
Run: ZRCP_PORT=<port> python3 tests/status.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, K_SLIME,  # noqa: E402
                      stand_y, RUN_LIMIT, attr_at, cell_bytes)
from proj3 import T, w16, Rng  # noqa: E402
import combat_tables as CT  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
STF, ST1, ST2 = S["ST_FLAGS"], S["ST_T1"], S["ST_T2"]
FROZEN, ASLEEP, STUNNED = 1, 2, 3
FEAR, CONF = 1 << 2, 2 << 2
POISON, WEAK, GUARD = 0x10, 0x20, 0x40
EFX = dict(FROZEN=1, ASLEEP=2, STUNNED=3, FEAR=4, CONFUSED=5, POISON=6, WEAK=7)
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
R_DATTR = 10
TXT = None


def main():
    global TXT
    import textpack
    TXT = dict(textpack.read_strings())
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
            print("[skip] status needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"status: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    sym, b3 = CT.load()
    ab = sym["ab_rank"] - CT.BASE
    kt = {}
    slots = {}
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]

    # ---- stepping with the log captured ------------------------------------------
    def run_to_probe():
        """run until a probe PC; every log_push line (breakpoint 5) -> `lines`."""
        for _ in range(200):
            p.z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == LOGP:
                regs = p.z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                lines.append(stream_text(p.z.read_memory(hl, 48)).rstrip("."))
                p.z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")

    def tick(n=1):
        """Proto.tick with the log captured."""
        for _ in range(n):
            p.z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick                                  # Proto.turn / tap / until use it

    def capture(on):
        p.z.cmd(("set-breakpoint 5 PC=%d" % LOGP) if on else "set-breakpoint 5")

    def stub(body):
        """Run body (bytes) inside the current tick's start (PC at wait_tick):
        code at STUB, then jp wait_tick (the game stack is untouched)."""
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        p.z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def far7(label, slot_ix, a=0):
        """far7 label with IX = slot's entity, A = a -> L stored at RES."""
        stub([0xDD, 0x21] + w16(S["P_ENTITIES"] + slot_ix * STRIDE) + [0x3E, a, 0x21] + w16(S[label])
             + [0xCD] + w16(S["far7"]) + [0x7D, 0x32] + w16(RES))
        return p.rb(RES)

    def deal(att, tgt, dmg, c, e):
        """deal_hit (bank 3): IX = att's entity -> L (HP lost) at RES."""
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, tgt, 0x06, dmg, 0x0E, c, 0x1E, e,
                 0xCD] + w16(S["deal_hit"]) + [0x7D, 0x32] + w16(RES))
        stub(p.bank3(inner))
        return p.rb(RES)

    def st(slot):
        return p.rb(STF + slot), p.rb(ST1 + slot), p.rb(ST2 + slot)

    def setst(slot, f, t1=0, t2=0):
        p.wb(STF + slot, f)
        p.wb(ST1 + slot, t1)
        p.wb(ST2 + slot, t2)

    def place(slot, x, y, flags, hp=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(hero, mons, learn=None, mp=30, hx=HX, hp=200):
        """Fresh game (hero kind) in PROTO room A: every monster parked, the hero
        at hx facing right, mons = [(kind, x, hp, left)] standing on his floor;
        learn = {abl: rank} (Mage abl = ability index k)."""
        p.boot(hero)
        if not kt:
            kt.update(p.kinds())
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, hx, HY, EF_ACTIVE | EF_PLAYER, hp)
        out = []
        for kind, x, mhp, left in mons:
            sl = slots[kind]
            place(sl, x, HY + 6 - kt[kind]["bh"], EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), mhp)
            out.append(sl)
        for a in (STF, ST1, ST2):
            p.wmem(a, [0] * 16)
        p.wb("MP", mp)
        p.wb("MAXMP", mp)
        av = 0
        for abl, r in (learn or {}).items():
            k = abl if hero == K_WIZARD else abl - S["ABL_POWER"]
            av |= r << (2 * k)
            p.wmem(S["RANK_ROWS"] + 6 * k, list(b3[ab + (abl * 3 + r - 1) * 6: ab + (abl * 3 + r) * 6]))
        p.wmem(S["ARANK"], w16(av))
        p.tick(3)
        capture(True)
        lines.clear()
        return out

    def tint(slot):
        return p.rb(S["SLOTREC"] + slot * 16 + R_DATTR)

    def kattr(kind):
        return p.rb(S["kind_tab"] + S["KT_ATTR"] + kind)

    def cast(slot_icon):
        p.select_slot(slot_icon)
        return p.turn("FIRE")

    def wait_turn():
        return p.turn("WAIT")

    # ======================= F: Frost freeze = 2 skipped actions ===================
    FROST = S["ABL_FROST"]
    g, = scene(K_WIZARD, [(K_GOBLIN, HX + 5, 60, True)], learn={FROST: 1})
    x0 = p.ent(g)["X"]
    ok = cast(3)
    s1, x1, t1 = st(g), p.ent(g)["X"], tint(g)
    check("F1: the Frost turn ran; Goblin FROZEN, 1 turn left after its own step (2 -> 1), did not move,"
          " tint $45", ok and s1[0] & 3 == FROZEN and s1[1] >> 4 == 1 and x1 == x0 and t1 == 0x45,
          (ok, s1, x0, x1, hex(t1)))
    check("F1: 'THE GOBLIN IS FROZEN' pushed", "THE GOBLIN" + TXT["st_m_frozen"] in lines, lines)
    wait_turn()
    s2, x2 = st(g), p.ent(g)["X"]
    p.tick(2)
    check("F2: the 2nd skipped action: HOLD cleared at 0, still not moved, tint back to the kind attr",
          s2[0] == GUARD and s2[1] == 0 and x2 == x0 and tint(g) == kattr(K_GOBLIN), (s2, x2, hex(tint(g))))
    wait_turn()
    x3 = p.ent(g)["X"]
    check("F3: the 3rd turn: the Goblin walks again (exactly 2 actions lost)", x3 == x0 - 1, (x0, x3))

    # ======================= H: held hero =========================================
    scene(K_KNIGHT, [])
    tc0 = p.rw("TURN_COUNTER")
    p.hold("L")                                   # walk right, held throughout the hold
    setst(0, FROZEN, 0x20)
    ends, xs, icon = [], [], None
    for i in range(16):
        tick()
        tc = p.rw("TURN_COUNTER") - tc0
        while len(ends) < tc:
            ends.append(i)
        xs.append(p.ent(0)["X"])
        if i == 2:
            fr = p.composed_frame()
            icon = (p.rb("STAT_SH"), attr_at(fr, 30, 21), any(cell_bytes(fr, 30, 21)), hex(tint(0)))
    p.release()
    tick(3)
    check("H1: exactly 2 automatic turns while held, a walk key held: the hero never moves",
          len(ends) == 2 and set(xs) == {HX} and st(0) == (GUARD, 0, 0), (ends, xs, st(0)))
    check("H1: held turns 4 ticks apart (HELD_WAIT 3 idle + the Wait turn)", len(ends) == 2 and ends[1] - ends[0] == 4, ends)
    check("H1: 'YOU CAN MOVE AGAIN' once", lines.count(TXT["st_move"]) == 1, lines)
    check("H2: while held: STAT_SH = FROZEN (1), panel (30, 21) attr $45 with a glyph, hero tint $45",
          icon == (1, 0x45, True, "0x45"), icon)
    fr = p.composed_frame()
    check("H2: after: STAT_SH 0, (30, 21) blank, hero tint = its kind attr",
          p.rb("STAT_SH") == 0 and not any(cell_bytes(fr, 30, 21)) and tint(0) == kattr(K_KNIGHT),
          (p.rb("STAT_SH"), cell_bytes(fr, 30, 21), hex(tint(0))))
    ok = p.turn("L")
    check("H3: free again: the next walk moves him", ok and p.ent(0)["X"] == HX + 1, p.ent(0)["X"])

    # ======================= W: a sleeper wakes on damage ==========================
    SPARK = S["ABL_SPARK"]
    g, = scene(K_WIZARD, [(K_GOBLIN, HX + 6, 60, True)], learn={SPARK: 1})
    setst(g, ASLEEP, 0x80)
    p.tick()
    check("W0: an ASLEEP Goblin shows the $41 tint", tint(g) == 0x41, hex(tint(g)))
    cast(1)
    s = st(g)
    check("W1: Spark on a sleeper: HOLD cleared, 'THE GOBLIN WAKES UP'",
          s[0] & 3 == 0 and s[1] >> 4 == 0 and "THE GOBLIN" + TXT["st_m_wake"] in lines, (s, lines))
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 8, 30, True)])
    setst(g, ASLEEP | POISON, 0x80, 0x40)
    hp0 = p.ent(g)["HP"]
    wait_turn()
    s = st(g)
    check("W2: poison (4 -> 3) costs 1 HP and wakes the sleeper; it acts (walks) the same turn",
          p.ent(g)["HP"] == hp0 - 1 and s[0] == POISON and s[2] == 0x30 and p.ent(g)["X"] == HX + 7
          and "THE GOBLIN" + TXT["st_m_wake"] in lines, (p.ent(g)["HP"], s, p.ent(g)["X"], lines))

    # ======================= G: STUN_GUARD =========================================
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    STUNC = 0 | (EFX["STUNNED"] << S["DH_EFX_SHIFT"])
    deal(0, g, 1, STUNC, 1)
    a = st(g)
    x0 = p.ent(g)["X"]
    wait_turn()
    b = st(g)
    deal(0, g, 1, STUNC, 1)
    c = st(g)
    x1 = p.ent(g)["X"]
    wait_turn()
    d = st(g)
    x2 = p.ent(g)["X"]
    deal(0, g, 1, STUNC, 1)
    e = st(g)
    check("G1: STUNNED 1, then its phase: skipped, cleared, STUN_GUARD set",
          a[0] == STUNNED and a[1] == 0x10 and b[0] == GUARD and b[1] == 0 and x1 == x0, (a, b, x0, x1))
    check("G2: a stun under the guard is refused", c == b, c)
    check("G3: the Goblin acts (walks), the guard clears; a new stun lands",
          x2 == x0 - 1 and d[0] == 0 and e[0] == STUNNED and e[1] == 0x10, (x2, d, e))


    # ======================= H8c: HOLD_GUARD, self-freeze, poison stacking (D3-8c) ====
    FRZC = EFX["FROZEN"] << S["DH_EFX_SHIFT"]
    SLPC = EFX["ASLEEP"] << S["DH_EFX_SHIFT"]
    POIC = EFX["POISON"] << S["DH_EFX_SHIFT"]
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    deal(0, g, 1, FRZC, 2)
    a = st(g)
    deal(0, g, 1, FRZC, 3)                         # a recast on the frozen body (the chain lock)
    b = st(g)
    deal(0, g, 1, STUNC, 1)                        # a stun on it
    c = st(g)
    check("HG1: FROZEN 2, then FROZEN 3 / STUNNED 1 on the held body: no effect (damage applies)",
          a == (FROZEN, 0x20, 0) and b == a and c == a and p.ent(g)["HP"] == 57, (a, b, c, p.ent(g)["HP"]))
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    deal(0, g, 1, STUNC, 2)
    deal(0, g, 1, FRZC, 3)
    check("HG2: STUNNED, then FROZEN: no overwrite", st(g) == (STUNNED, 0x20, 0), st(g))
    setst(g, ASLEEP, 0x80)
    deal(0, g, 1, FRZC, 2)
    check("HG3: a sleeper is woken by the hit and then frozen", st(g) == (FROZEN, 0x20, 0), st(g))
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    deal(0, g, 1, FRZC, 1)
    wait_turn()
    a = st(g)
    deal(0, g, 1, FRZC, 3)
    b = st(g)
    deal(0, g, 1, STUNC, 1)
    c = st(g)
    deal(0, g, 1, SLPC, 4)                         # ASLEEP is not guarded
    d = st(g)
    check("HG4: FROZEN ends -> HOLD_GUARD set; a re-freeze / stun under it is refused, a sleep lands",
          a == (GUARD, 0, 0) and b == a and c == a and d[0] == GUARD | ASLEEP, (a, b, c, d))
    setst(g, GUARD)
    wait_turn()
    deal(0, g, 1, FRZC, 3)
    check("HG5: the body acted -> the guard cleared; a freeze lands", st(g) == (FROZEN, 0x30, 0), st(g))
    deal(0, g, 1, S["DTY_FIRE"] | (0 << S["DH_EFX_SHIFT"]), 0)
    check("HG6: a FIRE hit thaws it and sets the guard", st(g)[0] == GUARD and st(g)[1] == 0, st(g))
    deal(0, g, 1, FRZC, 2)
    check("HG6: ...so an immediate re-freeze is refused", st(g)[0] == GUARD, st(g))
    # self-freeze: the caster struck by his own shard is held 1 turn at any rank
    scene(K_KNIGHT, [])
    deal(0, 0, 1, FRZC, 4)
    check("HG7: Frost on its own caster (rank 3, 4 turns): FROZEN 1", st(0) == (FROZEN, 0x10, 0), st(0))
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    deal(g, g, 1, FRZC, 4)
    deal(g, 0, 1, FRZC, 4)
    check("HG7: a Goblin reflecting onto itself: 1; onto the hero (other attacker): full 4",
          st(g) == (FROZEN, 0x10, 0) and st(0) == (FROZEN, 0x40, 0), (st(g), st(0)))
    # POISON stacks per hit, cap 15
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 6, 60, True)])
    seq = []
    for _ in range(4):
        deal(g, 0, 1, POIC, 6)
        seq.append(st(0)[2] >> 4)
    check("HG8: POISON 6 per bite adds: 6, 12, 15 (cap), 15", seq == [6, 12, 15, 15], seq)
    check("HG8: ...with the flag set and no other effect", st(0)[0] == POISON, st(0))

    # ======================= P: poison =============================================
    scene(K_KNIGHT, [], hp=10)
    setst(0, POISON, 0, 0x90)
    hps = []
    for _ in range(9):
        wait_turn()
        hps.append(p.ent(0)["HP"])
    check("P1: POISON 9 at HP 10: -1 HP at timer 6 / 3 / 0, cleared", hps == [10, 10, 9, 9, 9, 8, 8, 8, 7]
          and st(0) == (0, 0, 0), (hps, st(0)))
    check("P1: 'THE POISON WEARS OFF' once", lines.count(TXT["st_poison_off"]) == 1, lines)
    scene(K_KNIGHT, [], hp=2)
    setst(0, POISON, 0, 0xF0)
    hps = []
    for _ in range(15):
        wait_turn()
        hps.append(p.ent(0)["HP"])
    check("P2: POISON 15 at HP 2: down to 1, never below", min(hps) == 1 and hps[-1] == 1 and hps[0] == 2,
          hps)

    # ======================= C: CONFUSED ===========================================
    def seed_for(pred):
        for s in range(1, 5000):
            if pred(Rng(s)):
                return s
        raise AssertionError("no seed")

    rev = seed_for(lambda r: r.mod(3) == 0)
    fwd = seed_for(lambda r: r.mod(3) != 0)
    scene(K_KNIGHT, [])
    setst(0, CONF, 0x0F)
    p.wmem(S["RNG_STATE"], w16(rev))
    ok = p.turn("L")
    e = p.ent(0)
    check("C1: reversed (rng_mod 3 == 0): a walk right turns and walks left",
          ok and e["X"] == HX - 1 and e["FLAGS"] & EF_LEFT, (ok, e["X"], e["FLAGS"]))
    p.tap("L")                                    # the 0-turn turnaround (never rolls)
    tick()
    x0 = p.ent(0)["X"]
    p.wmem(S["RNG_STATE"], w16(fwd))
    ok = p.turn("L")
    check("C2: not reversed: walks right", ok and p.ent(0)["X"] == x0 + 1, (ok, x0, p.ent(0)["X"]))
    scene(K_KNIGHT, [], hx=3)
    setst(0, CONF, 0x0F)
    p.wmem(S["RNG_STATE"], w16(rev))
    tc0 = p.rw("TURN_COUNTER")
    ok = p.turn("K", "L")                         # jump right, reversed -> left from x 3: illegal
    e = p.ent(0)
    check("C3: a reversed illegal jump: 'YOU STUMBLE', the turn is spent, facing left, no move",
          p.rw("TURN_COUNTER") == tc0 + 1 and e["X"] == 3 and e["FLAGS"] & EF_LEFT
          and TXT["st_stumble"] in lines, (p.rw("TURN_COUNTER") - tc0, e["X"], e["FLAGS"], lines))
    # a confused Goblin: rng_mod 2 == 0 (replaced), then rng_mod 2 -> dx = 2v - 1
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 8, 30, True)])
    setst(g, CONF, 0x0F)

    def conf_away(r):
        return r.mod(2) == 0 and r.mod(2) == 1
    p.wmem(S["RNG_STATE"], w16(seed_for(conf_away)))
    wait_turn()
    check("C4: a confused Goblin's replaced action: a random step (here +1, away from the hero)",
          p.ent(g)["X"] == HX + 9, p.ent(g)["X"])

    # ======================= B: boss ===============================================
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 8, 90, True)])
    kx = S["kx_tab"] + K_GOBLIN * S["KX_STRIDE"] + S["KX_IMM"]
    zone = 3 * 16384 + kx - 0xC000

    def kx_poke(v):
        p.z.cmd("set-memory-zone 0")
        try:
            p.z.cmd("write-memory %d %d" % (zone, v))
        finally:
            p.z.cmd("set-memory-zone -1")
    kx_poke(0x80)
    res = {}
    for name, turns, want in (("FROZEN", 2, (FROZEN, 0x10, 0)), ("STUNNED", 1, (0, 0, 0)),
                              ("CONFUSED", 3, (CONF, 0x01, 0)), ("POISON", 9, (POISON, 0, 0x90)),
                              ("ASLEEP", 8, (0, 0, 0))):
        setst(g, 0)
        lines.clear()
        deal(0, g, 1, EFX[name] << S["DH_EFX_SHIFT"], turns)
        res[name] = (st(g), want)
    check("B1: boss: FROZEN 2 -> 1, STUNNED 1 -> none, CONFUSED 3 -> 1, POISON 9 full, ASLEEP immune",
          all(a == b for a, b in res.values()), res)
    check("B1: ASLEEP on a boss: 'THE GOBLIN IS UNAFFECTED'", lines == ["THE GOBLIN" + TXT["cmb_unaffected"]],
          lines)
    kx_poke(0)
    sl, = scene(K_KNIGHT, [(K_SLIME, HX + 8, 90, True)])
    zone = 3 * 16384 + S["kx_tab"] + K_SLIME * S["KX_STRIDE"] + S["KX_IMM"] - 0xC000
    p.z.cmd("set-memory-zone 0")
    try:
        imm0 = p.z.read_memory(zone, 1)[0]
        p.z.cmd("write-memory %d %d" % (zone, imm0 | 0x80))
    finally:
        p.z.cmd("set-memory-zone -1")
    deal(0, sl, 4, EFX["STUNNED"] << S["DH_EFX_SHIFT"], 2)
    check("B2: Slime (PHYS R) + boss: STUNNED 2 -> R 1 -> boss 0 (none)", st(sl)[0] == 0, st(sl))

    # ======================= X: FEAR / WEAK ========================================
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 3, 60, True)])
    setst(0, FEAR, 0x0F)
    hp0 = p.ent(g)["HP"]
    nt = p.no_turn("L")
    check("X1: FEAR: the bump attack is refused (no turn, no damage), 'YOU ARE TOO AFRAID TO FIGHT!'",
          nt and p.ent(g)["HP"] == hp0 and TXT["st_afraid"].rstrip(".") in lines, (nt, lines))
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 3, 60, True)])
    setst(g, FEAR, 0x0F)
    wait_turn()
    check("X2: a fearful Goblin next to the hero steps away", p.ent(g)["X"] == HX + 4, p.ent(g)["X"])
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 8, 60, True)])
    setst(0, WEAK, 0, 0x0C)
    nt = p.no_turn("K", "L")
    check("X3: WEAK: no jump (no turn)", nt and p.ent(0)["X"] == HX, (nt, p.ent(0)["X"]))
    hp0 = p.ent(g)["HP"]
    l3 = deal(0, g, 3, 0, 0)
    l1 = deal(0, g, 1, 0, 0)
    check("X4: WEAK hero: deal_hit dmg 3 -> 2, 1 -> 1 (min 1)", (l3, l1) == (2, 1), (l3, l1, hp0))

    # ======================= R: review fixes (fix pass) ============================
    # R1: woken by the status step (ASLEEP 5 + POISON 4: 4 -> 3 costs 1 HP) on the
    # held path, a walk key held all along, INPUT_REPEAT 0: no action that tick,
    # and the held key needs a release before the next walk.
    scene(K_KNIGHT, [], hp=20)
    p.wb("INPUT_REPEAT", 0)
    tc0 = p.rw("TURN_COUNTER")
    p.hold("L")
    setst(0, ASLEEP | POISON, 0x50, 0x40)
    xs = []
    for _ in range(12):
        tick()
        xs.append(p.ent(0)["X"])
    p.release()
    tick(2)
    check("R1: woken by poison while a walk key is held (INPUT_REPEAT 0): no walk, no turn, 'YOU WAKE UP'",
          set(xs) == {HX} and p.rw("TURN_COUNTER") == tc0 and st(0)[0] == POISON and p.ent(0)["HP"] == 19
          and TXT["st_wake"] in lines, (xs, p.rw("TURN_COUNTER") - tc0, st(0), lines))
    ok = p.turn("L")
    check("R1: released, the next walk moves him", ok and p.ent(0)["X"] == HX + 1, p.ent(0)["X"])

    rng_w = S["RNG_STATE"]
    # R2: CONFUSED mid-ladder: the melee icon never rolls (RNG untouched), refused
    # NO TARGET (no turn), no stumble, facing kept
    scene(K_KNIGHT, [], hx=5)
    p.turn("K")                                   # one row up room A's {5,1} shaft
    setst(0, CONF, 0x0F)
    p.wmem(rng_w, w16(rev))
    lines.clear()
    f0 = p.ent(0)["FLAGS"]
    nt = p.no_turn("C")
    check("R2: confused mid-ladder melee: no roll, NO TARGET, no turn, no stumble, facing kept",
          nt and p.rw("RNG_STATE") == rev and TXT["no_target"] in lines and TXT["st_stumble"] not in lines
          and p.ent(0)["FLAGS"] == f0, (nt, hex(p.rw("RNG_STATE")), lines, p.ent(0)["FLAGS"], f0))
    # R3: reversed, refused for a non-directional reason (Spark, MP 0): NO MANA,
    # no turn, facing restored, no stumble
    scene(K_WIZARD, [], learn={SPARK: 1}, mp=0)
    setst(0, CONF, 0x0F)
    p.wmem(rng_w, w16(rev))
    p.select_slot(1)
    lines.clear()
    nt = p.no_turn("FIRE")
    check("R3: reversed Spark with MP 0: NO MANA, no turn, facing right again, no stumble",
          nt and TXT["no_mana"] in lines and TXT["st_stumble"] not in lines
          and not p.ent(0)["FLAGS"] & EF_LEFT, (nt, lines, p.ent(0)["FLAGS"]))
    # R4: reversed melee with the only target in front: NO TARGET behind is the
    # direction's fault (game.md §2.3 / §6.4) -> the silent stumble: YOU
    # STUMBLE (no NO TARGET line), the turn is spent, facing stays reversed
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 3, 60, True)])
    setst(0, CONF, 0x0F)
    p.wmem(rng_w, w16(rev))
    lines.clear()
    hp0 = p.ent(g)["HP"]
    tc0 = p.rw("TURN_COUNTER")
    p.turn("C")
    check("R4: reversed melee, no target behind: YOU STUMBLE, the turn is spent, no NO TARGET, facing left",
          p.rw("TURN_COUNTER") == tc0 + 1 and p.ent(g)["HP"] == hp0 and TXT["st_stumble"] in lines
          and TXT["no_target"] not in lines and p.ent(0)["FLAGS"] & EF_LEFT,
          (p.rw("TURN_COUNTER") - tc0, lines, p.ent(0)["FLAGS"]))
    # R4b: the same with Power Strike (abil_melee's NO TARGET): a stumble, no MP spent
    g, = scene(K_KNIGHT, [(K_GOBLIN, HX + 3, 60, True)], learn={S["ABL_POWER"]: 1})
    setst(0, CONF, 0x0F)
    p.wmem(rng_w, w16(rev))
    p.select_slot(1)
    lines.clear()
    hp0, mp0 = p.ent(g)["HP"], p.rb("MP")
    tc0 = p.rw("TURN_COUNTER")
    p.turn("FIRE")
    check("R4b: reversed Power Strike, no target behind: YOU STUMBLE, the turn is spent, no MP, no NO TARGET",
          p.rw("TURN_COUNTER") == tc0 + 1 and p.ent(g)["HP"] == hp0 and p.rb("MP") == mp0
          and TXT["st_stumble"] in lines and TXT["no_target"] not in lines and p.ent(0)["FLAGS"] & EF_LEFT,
          (p.rw("TURN_COUNTER") - tc0, lines, p.rb("MP"), mp0, p.ent(0)["FLAGS"]))
    # R4c: not CONFUSED, melee with nothing in front: the NO TARGET line, no
    # turn (use_icon pushes the line for IC_NOTGT)
    scene(K_KNIGHT, [])
    lines.clear()
    nt = p.no_turn("C")
    check("R4c: plain melee with no target: NO TARGET, no turn, no stumble",
          nt and TXT["no_target"] in lines and TXT["st_stumble"] not in lines, (nt, lines))
    # R5: reversed and refused BY the direction (Spark at x 0 — poked: the edge
    # col a room exit passes through — facing right -> left: act_begin's lead
    # col 0, a silent refusal): YOU STUMBLE, the turn is spent
    scene(K_WIZARD, [], learn={SPARK: 1}, hx=0)
    setst(0, CONF, 0x0F)
    p.wmem(rng_w, w16(rev))
    p.select_slot(1)
    lines.clear()
    tc0 = p.rw("TURN_COUNTER")
    mp0 = p.rb("MP")
    p.turn("FIRE")
    check("R5: reversed Spark into the wall col: YOU STUMBLE, the turn is spent, no MP, facing left",
          p.rw("TURN_COUNTER") == tc0 + 1 and TXT["st_stumble"] in lines and p.rb("MP") == mp0
          and p.ent(0)["FLAGS"] & EF_LEFT, (p.rw("TURN_COUNTER") - tc0, lines, p.rb("MP"), p.ent(0)["FLAGS"]))
    # R6: a FEARful / CONFUSED Goblin parked on the top ladder end at the shaft
    # col (facing left), the hero mid-ladder below: ai_monster's yield runs (off
    # the shaft col that way: x 4), not the flee / random step
    for mind in (FEAR, CONF):
        scene(K_KNIGHT, [], hx=5)
        p.turn("K")
        sl = slots[K_GOBLIN]
        place(sl, 5, stand_y(0, kt[K_GOBLIN]["bh"]), EF_ACTIVE | EF_HOSTILE | EF_LEFT, 60)
        setst(sl, mind, 0x0F)
        p.wmem(rng_w, w16(seed_for(lambda r: r.mod(2) == 0 and r.mod(2) == 1)))   # confused: replaced, +1
        tick()
        wait_turn()
        check(f"R6 {'FEAR' if mind == FEAR else 'CONFUSED'}: a Goblin on the hero's ladder end yields (x 5 -> 4)",
              p.ent(sl)["X"] == 4 and p.ent(sl)["Y"] == stand_y(0, kt[K_GOBLIN]["bh"]),
              (p.ent(sl)["X"], p.ent(sl)["Y"]))


if __name__ == "__main__":
    sys.exit(main())
