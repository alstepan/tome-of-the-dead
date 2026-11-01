#!/usr/bin/env python3
"""LOG-FIX: what the player reads in the log for every combat event (the LOG-AUDIT
findings), played through the real controls in PROTO room A on a release build
(DEBUG_KIT=0). The ring (LOG_TXT, 4 x 64 B) is read by its WRITE index (LQ_RD +
LOG_QN, unchanged by the panel's drain), so a line stays readable after it was
drawn; LQ_DROP (the ring's drop counter) is asserted where a drop would be a bug.

  L1  every spell rank 1 on a Rat: "YOU CAST <SPELL>" then the hit line
      (SPARK HITS THE / FIREBOLT BURNS THE / FROST HITS THE / YOU DRAIN THE /
      LIGHTNING HITS THE RAT); LQ_DROP 0
  L2  a Firebolt kill: "YOU CAST FIREBOLT", "YOU KILL RAT"
  L3  a cast into a wall (no target): "YOU CAST SPARK" only
  L4  Drain: CAST, YOU FEEL HEALTHIER (deal_hit), YOU DRAIN THE
  L5  Frost: CAST, its status line (FROZEN) from the strike, then the hit line
  L6  Lightning through 3 bodies with statuses: CAST first; LQ_DROP is reported
  L7  a bolt / a burst onto the caster (bounce, burst on the caster): THE BOLT HITS
      YOU / THE BURST SCORCHES YOU
  L8  dagger / bow regression: no cast line, the hit / miss line as before
  L9  two monsters hitting on the same tick: both lines
  L10 an Archer's arrow (hit / miss line)
  L12 a hunger crossing on a fight turn
  L14 a level-up on a kill
  C   the cast line is dropped (not the hit line) when >= 3 lines are pending
LOG-DMG (2026-11-01): the hero-strike lines lost "THE " and every hit line got a
" -D" / " -D HP H" / " +G" tail; this suite compares the lines with the tail
stripped (tail(): the numbers themselves are tests/logdmg.py's).
Run: ZRCP_PORT=<port> python3 tests/log_audit.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_SLIME, K_GOBLIN,  # noqa: E402
                      K_SKELETON, stand_y)
from tier6 import T, stream_text  # noqa: E402
from proj3 import w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING = range(5)
CAST = ["YOU CAST SPARK", "YOU CAST FIREBOLT", "YOU CAST FROST SHARD", "YOU CAST DRAIN LIFE",
        "YOU CAST LIGHTNING"]
HIT = ["SPARK HITS ", "FIRE BURNS ", "FROST HITS ", "YOU DRAIN ", "BOLT HITS "]   # LOG-DMG: no "THE "
TAIL = re.compile(r" [-+]\d{1,2}( HP \d{1,2})?$")


def tail(line):
    """LOG-DMG: the line without its " -D" / " -D HP H" / " +G" tail."""
    return TAIL.sub("", line)
SLOT_KIND = {1: K_RAT, 2: K_SLIME, 3: K_GOBLIN, 5: K_SKELETON}
NAME = {K_RAT: "RAT", K_SLIME: "SLIME", K_GOBLIN: "GOBLIN", K_SKELETON: "SKELETON"}


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
            print("[skip] log_audit needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"log_audit: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    kt = {}

    def drops():
        return p.rb(S["LOG_Q"] + S["LQ_DROP"])

    def stand(kind, cls):
        return HY + kt[cls]["bh"] - kt[kind]["bh"]

    def place(slot, x, y, flags, hp=None, room=0):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room, FLAGS=flags, REACT=0, FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(cls, mons, hero_hp=200, mp=40, learn=None, daggers=0, arrows=0, bow=0):
        p.boot(cls)
        if not kt:
            kt.update(p.kinds())
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, hero_hp)
        p.set_ent(0, MAXHP=max(hero_hp, 60))
        for sl, x, hp in mons:
            place(sl, x, stand(SLOT_KIND[sl], cls), EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp, room)
        p.wb("MP", mp)
        p.wb("MAXMP", max(mp, 1))
        av = 0
        for k, r in (learn or {}).items():
            av |= r << (2 * k)
        p.wmem(S["ARANK"], w16(av))
        p.wb("DAGGERS", daggers)
        p.wb("ARROWS", arrows)
        p.wb("HAS_BOW", bow)
        p.wb("FX_DROP", 0)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.tick(3)

    def slots_raw():
        return bytes(p.z.read_memory(S["LOG_TXT"], S["LOG_SLOTS"] * S["LOG_SLOT_LEN"]))

    def since(w0, raw0):
        """The lines pushed since the ring snapshot w0 = (LQ_RD, LOG_QN): by the write index;
        a full lap (4 pushes) leaves the index where it was -> told by the slot bytes."""
        wr0 = (w0[0] + w0[1]) % S["LOG_SLOTS"]
        wr1 = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"]
        n = (wr1 - wr0) % S["LOG_SLOTS"]
        if n == 0 and slots_raw() != raw0:
            n = S["LOG_SLOTS"]
        L = S["LOG_SLOT_LEN"]
        raw = slots_raw()
        return [tail(stream_text(raw[((wr0 + k) % S["LOG_SLOTS"]) * L:][:L])) for k in range(n)]

    def run_turn(act, pre=None, ticks=160):
        """`act()` presses the key; run the turn out. -> (lines pushed, drops). Sampled every tick
        (a lap of 4 pushes inside one tick is the only ambiguity: none of the scenes has it)."""
        if pre:
            pre()
        w0, raw0 = p.ring(), slots_raw()
        d0 = drops()
        t0 = p.rw("TURN_COUNTER")
        out = []
        act()
        for _ in range(ticks):
            out += since(w0, raw0)
            w0, raw0 = p.ring(), slots_raw()
            if p.rw("TURN_COUNTER") != t0 and p.idle() and p.rb("LOG_QN") == 0:
                break
            p.tick()
        p.tick(2)
        out += since(w0, raw0)
        return out, drops() - d0

    def play_turn(slot, pre=None):
        """Select icon `slot`, FIRE, run the turn out."""
        p.select_slot(slot)
        return run_turn(lambda: p.tap("FIRE"), pre)

    sx = HX + 3

    def flight_row():
        """The solid cols of the hero's flight row (ROOM_MAP row hero.y + PF_ROW_DY)."""
        row0 = p.ent(0)["Y"] + S["PF_ROW_DY"]
        row = list(p.z.read_memory(S["ROOM_MAP"] + row0 * 32, 32))
        tf = p.z.read_memory(S["tile_flags"], 64)
        return [c for c in range(32) if tf[row[c]] & S["TF_SOLID"]]

    # ---- L1: every spell, rank 1, on a Rat 3 cells off ----------------------------
    for k in range(5):
        scene(K_WIZARD, [(1, sx + 3, 200)], learn={k: 1})
        lines, dd = play_turn(k + 1)
        want = [CAST[k], HIT[k] + "RAT"]
        extra = {FROST: ["THE RAT IS FROZEN"], DRAINL: ["YOU FEEL HEALTHIER"]}.get(k, [])
        want = [want[0]] + extra + want[1:]            # deal_hit's own status / heal line comes between
        check(f"L1 {CAST[k][9:]}: {want}, LQ_DROP 0", lines == want and dd == 0, (lines, dd))

    # ---- L2: a kill ---------------------------------------------------------------
    scene(K_WIZARD, [(1, sx + 3, 1)], learn={FIREBOLT: 1})
    lines, dd = play_turn(FIREBOLT + 1)
    check("L2 Firebolt kills a Rat: CAST, YOU KILL THE RAT", lines == [CAST[FIREBOLT], "YOU KILL RAT"] and dd == 0,
          (lines, dd))

    # ---- L3: no target ------------------------------------------------------------
    scene(K_WIZARD, [], learn={SPARK: 1})
    lines, dd = play_turn(SPARK + 1)
    check("L3 a Spark into the wall: YOU CAST SPARK only", lines == [CAST[SPARK]] and dd == 0, (lines, dd))

    # ---- L4: Drain ----------------------------------------------------------------
    scene(K_WIZARD, [(1, sx + 2, 200)], hero_hp=5, learn={DRAINL: 1})
    lines, dd = play_turn(DRAINL + 1)
    check("L4 Drain: CAST, YOU FEEL HEALTHIER, YOU DRAIN THE RAT",
          lines == [CAST[DRAINL], "YOU FEEL HEALTHIER", "YOU DRAIN RAT"] and dd == 0, (lines, dd))

    # ---- L5: Frost ----------------------------------------------------------------
    scene(K_WIZARD, [(2, sx + 5, 200)], learn={FROST: 2})
    lines, dd = play_turn(FROST + 1)
    check("L5 Frost: CAST first, the hit line last, no drop",
          len(lines) >= 2 and lines[0] == CAST[FROST] and lines[-1] == HIT[FROST] + "SLIME" and dd == 0, (lines, dd))
    print(f"[info] L5 Frost lines: {lines}", flush=True)

    # ---- L6: Lightning through 3 bodies ---------------------------------------------
    scene(K_WIZARD, [(1, sx + 2, 200), (2, sx + 6, 200), (5, sx + 10, 200)], hero_hp=120, learn={LIGHTNING: 3})
    lines, dd = play_turn(LIGHTNING + 1)
    check("L6 Lightning x3 bodies: CAST first, the first body's hit line, LQ_DROP 0 (pierced bodies: no lines yet, P3)",
          lines[:2] == [CAST[LIGHTNING], HIT[LIGHTNING] + "RAT"] and dd == 0, (lines, dd))
    print(f"[info] L6 Lightning lines: {lines}  LQ_DROP {dd}", flush=True)

    # ---- S: Lightning through 3 / 4 ASLEEP monsters (4 WAKES UP lines + the cast line fill the ring):
    # the hit line must still be shown (Fix A: it replaces the newest pending line; LQ_DROP counts that)
    for nb in (3, 4):
        mons = [(1, sx + 2, 200), (2, sx + 6, 200), (5, sx + 10, 200), (3, sx + 14, 200)][:nb]
        scene(K_WIZARD, mons, hero_hp=120, learn={LIGHTNING: 3})
        for sl, _, _ in mons:
            p.wb(S["ST_FLAGS"] + sl, 2)
            p.wb(S["ST_T1"] + sl, 0x50)
        lines, dd = play_turn(LIGHTNING + 1)
        print(f"[info] S Lightning through {nb} ASLEEP: {lines} LQ_DROP {dd}", flush=True)
        check(f"S Lightning through {nb} sleepers: the hit line is not lost",
              any(l.startswith("BOLT HITS ") for l in lines), (lines, dd))

    # ---- L7: onto the caster -------------------------------------------------------
    scene(K_WIZARD, [], learn={SPARK: 1})
    print(f"[info] solid cols on the flight row: {flight_row()}", flush=True)
    for tag, k, rank, hx, want_self in (("Frost r2", FROST, 2, 6, True), ("Lightning r3", LIGHTNING, 3, 8, True),
                                        ("Spark (no bounce)", SPARK, 1, 6, False)):
        scene(K_WIZARD, [], learn={k: rank})
        place(0, hx, HY, EF_ACTIVE | EF_PLAYER | EF_LEFT, 200)
        p.tick(2)
        lines, dd = play_turn(k + 1)
        check(f"L7 {tag} bounces off the wall onto the caster: CAST first, THE BOLT HITS YOU last",
              lines[:1] == [CAST[k]] and (lines[-1:] == ["THE BOLT HITS YOU"]) == want_self and dd == 0, (lines, dd))
    scene(K_WIZARD, [(1, sx, 200)], learn={FIREBOLT: 1})
    lines, dd = play_turn(FIREBOLT + 1)
    check("L7 Firebolt r1 burst on the adjacent Rat scorches the caster: CAST, THE BURST SCORCHES YOU, hit line",
          lines[:3] == [CAST[FIREBOLT], "THE BURST SCORCHES YOU", "FIRE BURNS RAT"] and dd == 0, (lines, dd))

    # ---- L9: two monsters hitting on the same tick ----------------------------------
    def goblin(slot, x, left):
        place(slot, x, stand(K_GOBLIN, K_KNIGHT), EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), 500, p.rb("CUR_ROOM"))
        p.set_ent(slot, KIND=K_GOBLIN)

    scene(K_KNIGHT, [])
    goblin(3, HX + 3, True)
    goblin(6, HX - 3, False)
    p.set_ent(0, HP=200, MAXHP=200)
    p.select_slot(0)
    lines, dd = run_turn(lambda: p.tap("WAIT"))
    check("L9 two Goblins hitting on the same tick: both lines (MSG_Q used to keep only the last)",
          len(lines) == 2 and all(l in ("THE GOBLIN MISSES", "THE GOBLIN HITS YOU") for l in lines), lines)

    # ---- L8: dagger / bow regression -----------------------------------------------
    scene(K_KNIGHT, [(1, sx + 3, 200)], daggers=3, arrows=10, bow=1)
    lines, dd = play_turn(3)
    check("L8 dagger: one hit / miss line, no cast line",
          len(lines) == 1 and (lines[0] == "DAGGER HITS RAT" or lines[0].startswith("YOUR DAGGER MISSES")),
          (lines, dd))
    scene(K_KNIGHT, [(1, sx + 3, 200)], daggers=3, arrows=10, bow=1)
    lines, dd = play_turn(4)
    check("L8 bow: one hit / miss line, no cast line",
          len(lines) == 1 and (lines[0] == "ARROW HITS RAT" or lines[0].startswith("YOUR ARROW MISSES")),
          (lines, dd))

    # ---- L10: an Archer's arrow ------------------------------------------------------
    got = []
    for rep in range(4):
        scene(K_KNIGHT, [])
        arch = S["K_ARCHER"]
        place(3, HX + 8, stand(arch, K_KNIGHT), EF_ACTIVE | EF_HOSTILE | EF_LEFT, 500, p.rb("CUR_ROOM"))
        p.set_ent(3, KIND=arch)
        p.set_ent(0, HP=200, MAXHP=200)
        p.select_slot(0)
        g = []
        for _ in range(3):
            l_, _d = run_turn(lambda: p.tap("WAIT"))
            g += l_
        got.append(g)
    print(f"[info] L10 archer turns: {got}", flush=True)
    check("L10 an Archer's shots: every line is THE ARCHER HITS YOU / MISSES, at least one shot",
          all(set(g) <= {"THE ARCHER HITS YOU", "THE ARCHER MISSES"} for g in got) and any(got), got)

    # ---- L12: a hunger crossing on a fight turn ---------------------------------------
    scene(K_WIZARD, [(1, sx, 200)], learn={FIREBOLT: 1})
    p.wb("FOOD", 25)
    p.wb("FOOD_TMR", S["FOOD_PERIOD"] - 1)
    lines, dd = play_turn(FIREBOLT + 1)
    print(f"[info] L12 Firebolt + adjacent Rat + hunger crossing: {lines} drop {dd} HSTAGE {p.rb('HSTAGE')}", flush=True)
    check("L12 a hunger crossing on a Firebolt turn (CAST, SCORCH, hit, Rat, HUNGRY = 5 pushes): all shown, LQ_DROP 0",
          p.rb("HSTAGE") == S["HS_HUNGRY"] and lines[-1:] == ["YOU ARE HUNGRY"] and lines[:1] == [CAST[FIREBOLT]]
          and dd == 0, (lines, dd))
    # ---- L14: a level-up on a kill -----------------------------------------------------
    scene(K_KNIGHT, [])
    goblin(3, HX + 3, True)
    p.set_ent(3, HP=1, MAXHP=1)
    p.wmem(S["XP"], w16(39))
    p.select_slot(0)
    lines, dd = [], 0
    for _ in range(12):
        l_, d_ = play_turn(0)
        if p.rw("XP") >= 40:
            lines, dd = l_, d_
            break
    print(f"[info] L14 kill + level-up: {lines} drop {dd}", flush=True)
    check("L14 a kill that levels up: YOU KILL GOBLIN and YOU REACH LEVEL 2 both logged",
          "YOU KILL GOBLIN" in lines and any(l.startswith("YOU REACH LEVEL 2") for l in lines), (lines, dd))

    # ---- C: the cast line is dropped, not the hit line, with >= 3 lines pending ---------
    def prefill(n):
        def f():
            for k in range(n):
                txt = [ord(c) for c in f"TEST LINE {k}"] + [0]
                sl = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + p.rb("LOG_QN") + k) % S["LOG_SLOTS"]
                p.wmem(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], txt)
            p.wb("LOG_QN", p.rb("LOG_QN") + n)
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_LOG"])
        return f
    for n in (2, 3):
        scene(K_WIZARD, [(1, sx + 3, 200)], learn={SPARK: 1})
        p.select_slot(SPARK + 1)
        p.z.cmd("set-breakpoint 3 PC=%d" % S["act_begin"])
        p.extra_probes = {S["act_begin"]}
        t0 = p.rw("TURN_COUNTER")
        p.tap("FIRE")                              # stops at act_begin, mid input tick
        at = p.pc() == S["act_begin"]
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        prefill(n)()                               # n lines pending as the accept sees them
        w0, raw0 = p.ring(), slots_raw()
        lines = []
        for _ in range(160):
            p.tick()
            lines += since(w0, raw0)
            w0, raw0 = p.ring(), slots_raw()
            if p.rw("TURN_COUNTER") != t0 and p.idle() and p.rb("LOG_QN") == 0:
                break
        print(f"[info] C {n} pending at the accept: {lines} drop {drops()}", flush=True)
        has_cast = CAST[SPARK] in lines
        check(f"C {n} lines pending at the accept: cast line {'kept' if n < 3 else 'dropped'}, the hit line kept",
              at and has_cast == (n < 3) and "SPARK HITS RAT" in lines, (at, lines))


if __name__ == "__main__":
    sys.exit(main())
