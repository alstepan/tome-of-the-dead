#!/usr/bin/env python3
"""LOG-DMG (docs/design/log_damage.md, user 2026-11-01): the damage number in the
log line of every hit, + the remaining HP of a struck enemy. Release build
(DEBUG_KIT=0), PROTO room A.

U  unit vectors (§6), each line composed by the REAL routine from a stub (impact_line,
   hit_line, msg_push_d / _h / _t with the carriers poked: E_HIT / E_TGT / LN_VAL /
   pf_tgt / pf_lost / LN_G / TOME_HP) and read back from the log ring:
   V1-V7, V11, V12, V14, V15, V24, V27, V28 + the LOG-DMG self / heal lines (V16-V22 shape)
W  sweep: every kind x every hit pre (impact P_HIT, Power Strike SMASH, the 7 hit_line
   pres, the kill, the monster hit / Vampire drain) at D = H = 99: the exact text, <= 31 chars
I  the real game (controls / turns), numbers checked against the HP the bodies lost:
   I1 Warrior bump (V1-V3), I2 Goblin hits the hero (V5), I3 Firebolt (V9) + its burst on
   the caster (V20), I4 Lightning pierces A then B: A's numbers (V26, V10), I5 Lightning
   bounce onto the caster (V21), I6 Drain (V16 / V17), I7 Whirlwind one line per target
   in slot order (V13), I8 Power Strike SMASH (V12), I9 an Archer's arrow (V23: E_HIT bit 7,
   the line's -D), I10 a poison tick (V25: no line), I11 heal potion (V18) / cure (V19)
Not covered (cut, see the report): V22 the dart / stone trap number (the trap line is
pushed by bank-1 it_line before the damage is rolled).
Run: ZRCP_PORT=<port> python3 tests/logdmg.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_SLIME, K_GOBLIN,  # noqa: E402
                      K_SKELETON, stand_y)
from tier6 import T, stream_text, TXT  # noqa: E402
from proj3 import w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
PE = S["P_ENTITIES"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING = range(5)
POWER, WHIRL = 0, 1                       # the Warrior's k (ARANK bits 2k)
SLOT_KIND = {1: K_RAT, 2: K_SLIME, 3: K_GOBLIN, 5: K_SKELETON}
TAIL = re.compile(r"^(.*?)(?: ([-+])(\d{1,2})(?: HP (\d{1,2}))?)?$")


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
            print("[skip] logdmg needs a DEBUG_KIT=0 build", flush=True)
        else:
            unit(h, p, check)
            game(h, p, check)
        print(f"logdmg: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


# ------------------------------------------------------------------------- unit -----
def kind_names():
    """kind -> its name, in kind id order (src/strings.txt nm_*: TX_NM_KNIGHT + kind)."""
    names = [t for n, t in TXT.items() if n.startswith("nm_")]
    return {k: names[k] for k in range(S["K_COUNT"])}


def unit(h, p, check):
    NM = kind_names()
    p.boot(K_KNIGHT)
    for sl in range(1, 16):
        p.set_ent(sl, FLAGS=0)

    def ring_line(fn):
        """Run stub fn with an empty ring -> the ONE line it pushed (None: none / more)."""
        p.wb("LOG_QN", 0)
        p.wb(S["LOG_Q"] + S["LQ_DROP"], 0)
        rd = p.rb(S["LOG_Q"] + S["LQ_RD"])
        fn()
        n = p.rb("LOG_QN")
        if n != 1:
            return None if n == 0 else ("<%d lines>" % n)
        raw = p.z.read_memory(S["LOG_TXT"] + (rd % S["LOG_SLOTS"]) * S["LOG_SLOT_LEN"], S["LOG_SLOT_LEN"])
        return stream_text(raw)

    def imp(code, kind, ix_slot):
        body = [0xDD, 0x21] + w16(PE + ix_slot * STRIDE) + [0x06, code, 0x0E, kind, 0xCD] + w16(S["impact_line"])
        return ring_line(lambda: p.code(body))

    def hitl(pre, kind):
        body = [0x06, pre, 0x0E, kind, 0xCD] + w16(S["hit_line"])
        return ring_line(lambda: p.code(body))

    def push(label, tx):
        body = [0x3E, tx, 0xCD] + w16(S[label])
        return ring_line(lambda: p.code(body))

    def hero(hit=0, tgt=1):
        p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER, HIT=hit, HP=50, MAXHP=50)
        p.wb(PE + S["E_TGT"], tgt)

    def mon(slot, kind, hp, hit=0):
        p.set_ent(slot, FLAGS=EF_ACTIVE | EF_HOSTILE, KIND=kind, HP=hp, MAXHP=max(hp, 1), HIT=hit)
        p.wb(PE + slot * STRIDE + S["E_TGT"], 0)

    def flags(dmgx2):
        a = S["ABIL_DESC"] + S["ABD_FLAGS"]
        v = p.rb(a)
        p.wb(a, (v | S["ABF_DMGX2"]) if dmgx2 else (v & ~S["ABF_DMGX2"] & 255))

    MP = {n: S["MSG_" + n] for n in ("P_HIT", "P_MISS", "P_KILL", "M_HIT", "M_MISS", "P_PARRY", "SQUEEZE")}
    K = {n: S["K_" + n] for n in ("GOBLIN", "RAT", "ORC", "VAMPIRE", "SKEL_GUARD", "OGRE", "DKNIGHT",
                                   "POLTERGEIST", "DKNIGHT")}
    TX = lambda n: S["TX_" + n]   # noqa: E731
    V = {}
    # V1 / V2 / V3 / V4: the hero's blow at IMPACT (show_impact_msg: IX = the hero, D = E_HIT)
    hero(4); mon(1, K["GOBLIN"], 2)
    V["V1 YOU HIT GOBLIN -4 HP 2"] = (imp(MP["P_HIT"], K["GOBLIN"], 0), "YOU HIT GOBLIN -4 HP 2")
    hero(2); mon(1, K["GOBLIN"], 0)
    V["V2 overkill: YOU KILL GOBLIN -2"] = (imp(MP["P_KILL"], K["GOBLIN"], 0), "YOU KILL GOBLIN -2")
    hero(3); mon(1, K["RAT"], 0)
    V["V3 YOU KILL RAT -3"] = (imp(MP["P_KILL"], K["RAT"], 0), "YOU KILL RAT -3")
    hero(0); mon(1, K["ORC"], 14)
    V["V4 YOU MISS ORC"] = (imp(MP["P_MISS"], K["ORC"], 0), "YOU MISS ORC")
    # V5-V7: the monster's blow (IX = the attacker, D = its E_HIT; no HP part)
    hero(); mon(1, K["GOBLIN"], 6, hit=3)
    V["V5 THE GOBLIN HITS YOU -3"] = (imp(MP["M_HIT"], K["GOBLIN"], 1), "THE GOBLIN HITS YOU -3")
    mon(1, K["VAMPIRE"], 20, hit=4)
    V["V6 THE VAMPIRE DRAINS YOU -4"] = (imp(MP["M_HIT"], K["VAMPIRE"], 1), "THE VAMPIRE DRAINS YOU -4")
    mon(1, K["GOBLIN"], 6, hit=0)
    V["V7 THE GOBLIN MISSES"] = (imp(MP["M_MISS"], K["GOBLIN"], 1), "THE GOBLIN MISSES")
    mon(1, K["GOBLIN"], 6, hit=0x83)
    V["V23u a ranged shot's E_HIT $80|3: THE GOBLIN HITS YOU -3"] = (imp(MP["M_HIT"], K["GOBLIN"], 1),
                                                                     "THE GOBLIN HITS YOU -3")
    # V11 / V27 / V8: hit_line (pf_tgt's HP, pf_lost)
    mon(1, K["SKEL_GUARD"], 99)
    p.wb("pf_tgt", 1); p.wb("pf_lost", 99)
    V["V11 DAGGER HITS BONEGUARD -99 HP 99 (31)"] = (hitl(TX("CMB_DAG_HIT"), K["SKEL_GUARD"]),
                                                     "DAGGER HITS BONEGUARD -99 HP 99")
    p.wb("pf_lost", 120)
    V["V27 D 120 -> -99"] = (hitl(TX("CMB_DAG_HIT"), K["SKEL_GUARD"]), "DAGGER HITS BONEGUARD -99 HP 99")
    mon(1, K["ORC"], 9); p.wb("pf_lost", 5)
    V["V8 SPARK HITS ORC -5 HP 9"] = (hitl(TX("SPL_SPARK"), K["ORC"]), "SPARK HITS ORC -5 HP 9")
    mon(1, K["ORC"], 0); p.wb("pf_lost", 5)
    V["V8k ammo kill YOU KILL ORC -5"] = (hitl(TX("YOU_KILL"), K["ORC"]), "YOU KILL ORC -5")
    mon(1, K["ORC"], 9); p.wb("pf_lost", 0)
    V["V15h D 0 (immune): bare SPARK HITS ORC"] = (hitl(TX("SPL_SPARK"), K["ORC"]), "SPARK HITS ORC")
    # V12: melee_strike (IX = the target, D = LN_VAL); ABF_DMGX2 -> SMASH
    mon(1, K["OGRE"], 25); p.wb("LN_VAL", 15); flags(True)
    V["V12 YOU SMASH OGRE LORD -15 HP 25"] = (imp(MP["P_HIT"], K["OGRE"], 1), "YOU SMASH OGRE LORD -15 HP 25")
    flags(False)
    V["V13u Whirlwind blow: YOU HIT OGRE LORD -15 HP 25"] = (imp(MP["P_HIT"], K["OGRE"], 1),
                                                             "YOU HIT OGRE LORD -15 HP 25")
    mon(1, K["RAT"], 0); p.wb("LN_VAL", 2)
    V["V13k Whirlwind kill: YOU KILL RAT -2"] = (imp(MP["P_KILL"], K["RAT"], 1), "YOU KILL RAT -2")
    # V14 / V15 / V28: no tail
    hero(5); mon(1, K["DKNIGHT"], 30)
    V["V14 THE DEATHLORD PARRIES!"] = (imp(MP["P_PARRY"], K["DKNIGHT"], 0), "THE DEATHLORD PARRIES!")
    hero(0); mon(1, K["POLTERGEIST"], 10)
    V["V15 immune: YOU HIT WRAITH (no tail)"] = (imp(MP["P_HIT"], K["POLTERGEIST"], 0), "YOU HIT WRAITH")
    V["V28 YOU SQUEEZE PAST THE RAT"] = (imp(MP["SQUEEZE"], K["RAT"], 0), "YOU SQUEEZE PAST THE RAT")
    mon(1, K["GOBLIN"], 6)
    V["V-st status line: no tail"] = (imp(S["MSG_M_FROZEN"], K["GOBLIN"], 1), "THE GOBLIN" + TXT["st_m_frozen"])
    # V16-V22 shapes / V24: msg_push_d / _h / _t
    p.wb("LN_G", 3)
    V["V16 YOU FEEL HEALTHIER +3"] = (push("msg_push_h", TX("SPL_DRAIN_HEAL")), "YOU FEEL HEALTHIER +3")
    p.wb("LN_G", 0)
    V["V17 G 0: YOU FEEL HEALTHIER"] = (push("msg_push_h", TX("SPL_DRAIN_HEAL")), "YOU FEEL HEALTHIER")
    p.wb("LN_VAL", 4)
    V["V20 THE BURST SCORCHES YOU -4"] = (push("msg_push_d", TX("SPL_BURN_SELF")), "THE BURST SCORCHES YOU -4")
    p.wb("LN_VAL", 6)
    V["V21 THE BOLT HITS YOU -6"] = (push("msg_push_d", TX("SPL_HIT_SELF")), "THE BOLT HITS YOU -6")
    p.wb("LN_VAL", 3)
    V["Vf YOU FALL INTO A PIT -3"] = (push("msg_push_d", TX("FALL")), "YOU FALL INTO A PIT -3")
    p.wb("TOME_HP", 4)
    V["V24 THE TOME SHUDDERS -1 HP 4"] = (push("msg_push_t", TX("TOME_HIT")), "THE TOME SHUDDERS -1 HP 4")
    for tag, (got, want) in V.items():
        check("U " + tag, got == want and p.rb(S["LOG_Q"] + S["LQ_DROP"]) == 0, (got, want))

    # ---- W: the sweep: every kind x every pre at 99 / 99 ----------------------------------
    pres = [(TX("SPL_SPARK") + a, TXT[n]) for a, n in ((0, "spl_spark"), (1, "spl_fire"), (2, "spl_frost"),
                                                        (3, "spl_drain"), (4, "spl_light"))]
    pres += [(TX("CMB_DAG_HIT"), TXT["cmb_dag_hit"]), (TX("CMB_ARR_HIT"), TXT["cmb_arr_hit"])]
    bad, longest = [], (0, "")
    for k in range(S["K_COUNT"]):
        nm = NM[k]
        got = []
        hero(99); mon(1, k, 99)
        got.append((imp(MP["P_HIT"], k, 0), f"YOU HIT {nm} -99 HP 99"))
        p.wb("LN_VAL", 120); flags(True)
        got.append((imp(MP["P_HIT"], k, 1), f"YOU SMASH {nm} -99 HP 99"))
        flags(False)
        p.wb("pf_tgt", 1); p.wb("pf_lost", 99)
        for tx, pre in pres:
            got.append((hitl(tx, k), f"{pre}{nm} -99 HP 99"))
        mon(1, k, 0)
        got.append((hitl(TX("YOU_KILL"), k), f"YOU KILL {nm} -99"))
        hero(99); got.append((imp(MP["P_KILL"], k, 0), f"YOU KILL {nm} -99"))
        mon(1, k, 9, hit=99)
        post = TXT["cmb_drains"] if k == K["VAMPIRE"] else TXT["hits_you"]
        got.append((imp(MP["M_HIT"], k, 1), f"THE {nm}{post} -99"))
        for g, w in got:
            if g != w or len(g or "") > 31:
                bad.append((k, g, w))
            if g and len(g) > longest[0]:
                longest = (len(g), g)
    print(f"[info] W sweep: the longest line {longest[0]} chars: {longest[1]!r}", flush=True)
    check(f"W every kind x every pre at 99/99: exact text, <= 31 chars ({S['K_COUNT']} kinds)",
          not bad and longest[0] <= 31, bad[:6])


# ------------------------------------------------------------------------- game -----
def game(h, p, check):
    kt = {}

    def stand(kind, cls):
        return HY + kt[cls]["bh"] - kt[kind]["bh"]

    def place(slot, x, y, flags, hp=None, room=0):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room, FLAGS=flags, REACT=0, FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    seed = [0x1357]

    def scene(cls, mons, hero_hp=200, maxhp=None, mp=40, learn=None, kinds=None):
        p.boot(cls)
        seed[0] = (seed[0] * 75 + 74) % 65537 or 1   # each scene its own rolls (the snapshot's RNG is fixed)
        p.wmem(S["RNG_STATE"], w16(seed[0] & 0xFFFF or 1))
        if not kt:
            kt.update(p.kinds())
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, hero_hp)
        p.set_ent(0, MAXHP=maxhp or max(hero_hp, 60))
        for m in mons:
            sl, x, hp = m[:3]
            left = m[3] if len(m) > 3 else True
            kind = (kinds or {}).get(sl, SLOT_KIND.get(sl))
            place(sl, x, stand(kind, cls), EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), hp, room)
            p.set_ent(sl, KIND=kind)
        p.wb("MP", mp)
        p.wb("MAXMP", max(mp, 1))
        av = 0
        for k, r in (learn or {}).items():
            av |= r << (2 * k)
        p.wmem(S["ARANK"], w16(av))
        p.wb("DAGGERS", 0)
        p.wb("FX_DROP", 0)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.tick(3)

    def slots_raw():
        return bytes(p.z.read_memory(S["LOG_TXT"], S["LOG_SLOTS"] * S["LOG_SLOT_LEN"]))

    def since(w0, raw0):
        wr0 = (w0[0] + w0[1]) % S["LOG_SLOTS"]
        wr1 = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"]
        n = (wr1 - wr0) % S["LOG_SLOTS"]
        if n == 0 and slots_raw() != raw0:
            n = S["LOG_SLOTS"]
        L = S["LOG_SLOT_LEN"]
        raw = slots_raw()
        return [stream_text(raw[((wr0 + k) % S["LOG_SLOTS"]) * L:][:L]) for k in range(n)]

    def run_turn(act, ticks=160):
        w0, raw0 = p.ring(), slots_raw()
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
        return out

    def play(slot):
        p.select_slot(slot)
        return run_turn(lambda: p.tap("FIRE"))

    def hps(*slots):
        return [p.ent(s)["HP"] for s in slots]

    sx = HX + 3

    def hit_ok(line, pre, nm, d, hpl):
        """line == the hit / kill / miss line for a blow that took d HP leaving hpl."""
        if d == 0:
            return line in (f"YOU MISS {nm}", f"{pre}{nm}")
        return line == (f"{pre}{nm} -{min(d, 99)} HP {hpl}" if hpl else f"YOU KILL {nm} -{min(d, 99)}")

    # ---- I1: the Warrior's bump on a Goblin (V1-V3): until a hit and a kill are seen --------
    seen = {"hit": False, "kill": False}
    bad = []
    for rep in range(12):
        hp0 = 6 if not seen["hit"] else 2
        scene(K_KNIGHT, [(3, HX + 3, hp0)], kinds={3: K_GOBLIN})
        p.select_slot(0)
        before = hps(3)[0]
        lines = run_turn(lambda: p.tap("FIRE"))
        after = hps(3)[0]
        mine = [l for l in lines if l.startswith("YOU ")]
        if len(mine) != 1 or not hit_ok(mine[0], "YOU HIT ", "GOBLIN", before - after, after):
            bad.append((before, after, lines))
        if before != after:
            seen["kill" if after == 0 else "hit"] = True
        if all(seen.values()):
            break
    check("I1 the Warrior's bump: YOU HIT GOBLIN -D HP H / YOU KILL GOBLIN -D / YOU MISS GOBLIN == the HP lost",
          not bad and all(seen.values()), (bad[:3], seen))

    # ---- I2: Goblins hit the hero (V5): THE GOBLIN HITS YOU -D == the hero's HP lost ---------
    bad, hits = [], 0
    for rep in range(6):
        scene(K_KNIGHT, [(3, HX + 3, 500)], kinds={3: K_GOBLIN})
        p.select_slot(0)
        h0 = hps(0)[0]
        lines = run_turn(lambda: p.tap("WAIT"))
        d = h0 - hps(0)[0]
        want = f"THE GOBLIN HITS YOU -{d}" if d else "THE GOBLIN MISSES"
        if lines != [want]:
            bad.append((d, lines))
        hits += d > 0
        if hits >= 2:
            break
    check("I2 THE GOBLIN HITS YOU -D == the hero's loss (no HP part) / THE GOBLIN MISSES", not bad and hits, (bad, hits))

    # ---- I3: Firebolt on a Rat next to the hero (V9 + V20 burst on the caster) ---------------
    scene(K_WIZARD, [(1, sx, 60)], learn={FIREBOLT: 1})
    h0, r0 = hps(0, 1)
    lines = play(FIREBOLT + 1)
    h1, r1 = hps(0, 1)
    want = ["YOU CAST FIREBOLT", f"THE BURST SCORCHES YOU -{h0 - h1}", f"FIRE BURNS RAT -{r0 - r1} HP {r1}"]
    check("I3 Firebolt + burst: CAST, THE BURST SCORCHES YOU -D (hero), FIRE BURNS RAT -D HP H (pf_tgt)",
          lines[:3] == want, (lines, want))

    # ---- I4: Lightning pierces A then B: the line is A's (V26 / V10) -------------------------
    scene(K_WIZARD, [(1, sx + 2, 60), (2, sx + 6, 60)], hero_hp=120, learn={LIGHTNING: 1})
    a0, b0 = hps(1, 2)
    lines = play(LIGHTNING + 1)
    a1, b1 = hps(1, 2)
    hl = [l for l in lines if l.startswith("BOLT HITS")]
    check("I4 Lightning through A then B: one line, A's numbers (pf_lost / pf_tgt), B struck silently",
          hl == [f"BOLT HITS RAT -{a0 - a1} HP {a1}"] and b1 < b0, (lines, (a0, a1), (b0, b1)))

    # ---- I5: a bolt bouncing off the wall onto its caster (V21) -------------------------------
    scene(K_WIZARD, [], learn={LIGHTNING: 3})
    place(0, 8, HY, EF_ACTIVE | EF_PLAYER | EF_LEFT, 200)
    p.tick(2)
    h0 = hps(0)[0]
    lines = play(LIGHTNING + 1)
    d = h0 - hps(0)[0]
    check("I5 Lightning bounce onto the caster: THE BOLT HITS YOU -D == his loss",
          d > 0 and lines[-1:] == [f"THE BOLT HITS YOU -{d}"], (lines, d))

    # ---- I6: Drain (V16 / V17) ---------------------------------------------------------------
    for tag, hhp, mx in (("3 below max", 57, 60), ("at full HP", 60, 60)):
        scene(K_WIZARD, [(1, sx + 2, 60)], hero_hp=hhp, maxhp=mx, learn={DRAINL: 1})
        h0, r0 = hps(0, 1)
        lines = play(DRAINL + 1)
        h1, r1 = hps(0, 1)
        g = h1 - h0
        heal = f"YOU FEEL HEALTHIER +{g}" if g else "YOU FEEL HEALTHIER"
        want = ["YOU CAST DRAIN LIFE", heal, f"YOU DRAIN RAT -{r0 - r1} HP {r1}"]
        check(f"I6 Drain {tag}: CAST, {heal.replace(str(g), 'G') if g else heal}, YOU DRAIN RAT -D HP H",
              lines == want and g == min(r0 - r1, mx - hhp), (lines, want))

    # ---- I7: Whirlwind, one line per target in slot order (V13) -------------------------------
    bad, struck = [], False
    for rep in range(6):
        scene(K_KNIGHT, [(1, HX + 3, 30), (3, HX - 3, 30, False)], mp=40, learn={WHIRL: 1},
              kinds={1: K_RAT, 3: K_GOBLIN})
        b0 = hps(1, 3)
        lines = play(2)
        b1 = hps(1, 3)
        mine = [l for l in lines if l.startswith("YOU ")]
        ok = len(mine) == 2 and all(hit_ok(l, "YOU HIT ", nm, x0 - x1, x1)
                                    for l, nm, x0, x1 in zip(mine, ("RAT", "GOBLIN"), b0, b1))
        if not ok:
            bad.append((b0, b1, lines))
        struck |= b1 != b0
        if struck:
            break
    check("I7 Whirlwind: 2 targets -> 2 lines in slot order (RAT then GOBLIN), each with its own -D HP H",
          not bad and struck, bad[:3])

    # ---- I8: Power Strike = YOU SMASH (V12) ---------------------------------------------------
    bad, struck = [], False
    for rep in range(6):
        scene(K_KNIGHT, [(5, HX + 3, 40)], mp=40, learn={POWER: 1}, kinds={5: K_SKELETON})
        s0 = hps(5)[0]
        lines = play(1)
        s1 = hps(5)[0]
        mine = [l for l in lines if l.startswith("YOU ")]
        if len(mine) != 1 or not hit_ok(mine[0], "YOU SMASH ", "SKELETON", s0 - s1, s1):
            bad.append((s0, s1, lines))
        struck |= s1 != s0
        if struck:
            break
    check("I8 Power Strike: YOU SMASH SKELETON -D HP H (YOU MISS SKELETON on a miss)", not bad and struck, bad[:3])

    # ---- I9: an Archer's arrow (V23): THE ARCHER HITS YOU -D, E_HIT = $80 | D ---------------------
    arch = S["K_ARCHER"]
    bad, got = [], None
    for rep in range(10):
        scene(K_KNIGHT, [])
        place(3, HX + 8, stand(arch, K_KNIGHT), EF_ACTIVE | EF_HOSTILE | EF_LEFT, 500, p.rb("CUR_ROOM"))
        p.set_ent(3, KIND=arch)
        p.select_slot(0)
        for _ in range(3):
            h0 = hps(0)[0]
            lines = run_turn(lambda: p.tap("WAIT"))
            d = h0 - hps(0)[0]
            e = p.ent(3)
            for l in lines:
                if l.startswith("THE ARCHER HITS YOU"):
                    got = (l, d, e["HIT"])
                    if l != f"THE ARCHER HITS YOU -{d}" or e["HIT"] != 0x80 | d:
                        bad.append(got)
            if got:
                break
        if got:
            break
    print(f"[info] I9 archer: {got}", flush=True)
    check("I9 an Archer's hit: THE ARCHER HITS YOU -D == the loss, its E_HIT = $80 | D (bit 7: no IMPACT flash)",
          got and not bad, (got, bad))

    # ---- I10: a poison tick prints nothing (V25) ----------------------------------------------
    scene(K_KNIGHT, [])
    p.wb(S["ST_FLAGS"], S["STS_POISON"])
    p.wb("ST_X", 12)                              # 1 HP every 4 turns (status1.py P1)
    p.select_slot(0)
    h0 = hps(0)[0]
    lines = []
    for _ in range(4):
        lines += run_turn(lambda: p.tap("WAIT"))
    check("I10 4 poisoned turns: HP -1, no log line", lines == [] and hps(0)[0] == h0 - 1, (lines, h0, hps(0)))

    # ---- I11: heal potion (V18) and cure (V19, cut-order 2: bare) -----------------------------
    def drink(item, hp, mx, status=0):
        scene(K_KNIGHT, [], hero_hp=hp, maxhp=mx)
        p.wmem(S["BAG"], [S["IT_" + item], 1, 0] + [0] * 57)
        if status:
            p.wb(S["ST_FLAGS"], status)
            p.wb("ST_X", 6)
        p.wb("FX_OP", S["FX_DRINK"])
        p.wb("FX_ARG", 0)
        w0 = p.ring()
        body = [0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"])
        assert p.code(body), "fx_main stub"
        return p.log_since(w0), hps(0)[0] - hp
    lines, g = drink("P_HEAL", 55, 60)
    check("I11 Heal potion 5 below max: YOU FEEL HEALTHIER +5 (the cap)", lines[-1:] == ["YOU FEEL HEALTHIER +5"] and g == 5,
          (lines, g))
    lines, g = drink("P_HEAL", 20, 60)
    check(f"I11 Heal potion 20/60: YOU FEEL HEALTHIER +{S['QUAFF_HEAL']}",
          lines[-1:] == [f"YOU FEEL HEALTHIER +{S['QUAFF_HEAL']}"] and g == S["QUAFF_HEAL"], (lines, g))
    lines, g = drink("P_CURE", 60, 60, S["STS_POISON"])
    check("I11 Cure at full HP: YOU ARE CURED (bare)", lines[-1:] == ["YOU ARE CURED"] and g == 0, (lines, g))


if __name__ == "__main__":
    sys.exit(main())
