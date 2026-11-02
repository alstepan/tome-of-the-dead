#!/usr/bin/env python3
"""D3-7 T5: the Warrior's power attacks (src/abil_melee7.asm abil_melee /
melee_scan / power_fire, bank-3 melee_hit in src/rank3.asm) as a split
ability turn, played through the real controls (number key + FIRE) in PROTO
room A on a release build (DEBUG_KIT=0). Rules: game.md §6.2 (+2 to-hit,
x2, STUN 1 on a non-lethal hit; Whirlwind every hostile in reach on both
sides, +1 dmg), §5 ranks (tests/combat_tables.py transcription), §2.3 (no
power attack mid-ladder), §6.4 (stun: R halves, survivors only).

  R1  NOT LEARNED: the Power Strike slot forced (SEL_SLOT) with ARANK 0
  R2  NO MANA: MP = rank-1 cost - 1 (Power 1 of 2 MP, BAL-1 FINAL B costs 2/3/4; Whirlwind r3 with 3 of 4 MP: the threshold stays at rank 1)
  R3  mid-ladder (room A's {5,1} shaft) -> NO TARGET
  R4  no target: Power Strike with a Goblin only BEHIND the hero; Whirlwind
      with the nearest body 2 cols away (reach 1)
      every refusal: no turn, MP / TURN_PEND untouched, the line on row 23
  P1..P6  Power Strike r1 / r2 / r3 on a Goblin (dmg (1d6 + 0) x 2, STUN
      1 / 1 / 2), r1 on a Slime (PHYS R: dmg / 2, the stun halved to none),
      r3 killing a Rat (KILL, no stun), r1 missing (no burst, MISS line)
  W1..W3  Whirlwind r1 on a Rat + a Bat over it (both gap 0, right) and a
      Goblin behind (left), a Skeleton 4 cols away untouched; r2 (+2 dmg) on
      one Goblin; r3 (3 MP, to-hit +2) on both sides
  every strike: the accept pays RK_MP (MP, TURN_PEND = TP_ACT | TP_MON, ABL,
  2, 3, the kn_power / kn_whirl sequence); on the fire tick (probe_act_fire,
  TURN_TICK 2; the RNG poked with a seed the model picks) every body's HP /
  DYING / ST_FLAGS / ST_T1 and the RNG == the model (per target in slot
  order: d20, 1dN); struck bodies: E_REACTAT = 2 (the strike tick, the
  HURT / DEATH already running), ATTR_HIT flash; the lines pushed that tick
  == "[status] YOU HIT / SMASH / MISS / KILL <kind> [-D [HP H]]" per target (LOG-DMG); FX tracks:
  power_burst at the target's front col (a hit) / spark_fizz1 at x - 1 and
  x + w (Whirlwind), IF2 on the next tick; the monster phase only after the
  FX is idle; FX_DROP 0; the turn ends
  T7: K  power_fire skips a slot DYING by the strike (no roll, no line)
      E  edge clamp: Power / Whirlwind / SLASH at cols 0 and 29 -> CLIP_TRAP 0
      L  3 Whirlwind turns, FIRE tapped throughout: LQ_DROP 0, the log drains
Run: ZRCP_PORT=<port> python3 tests/abil_melee.py
"""
import copy
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_DIR = os.environ.get("WZ_BUILD_DIR", str(HERE.parent / "build"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_RAT, K_SLIME, K_GOBLIN, K_SKELETON, K_BAT,  # noqa: E402
                      stand_y)
from proj3 import T, w16, World, Body  # noqa: E402
import proj3  # noqa: E402
import combat_tables as CT  # noqa: E402
import textpack  # noqa: E402
import world  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, 8, 16, 64
E_REACT, E_REACTAT = 15, 16
POWER, WHIRL = S["ABL_POWER"], S["ABL_WHIRL"]
NAME = {POWER: "Power", WHIRL: "Whirl"}
SLOT = {POWER: 1, WHIRL: 2}                       # bar_knight: sword, power, whirl, ...
HY = stand_y(1, 6)                                # the hero on room A's bottom storey
HX = 12
NOWHERE = 7
R = 1
STUN_IMM, GUARD = 2, 0x40
NONE = 0xFF
FX_ST, FX_FID, FXD_COL, FXD_ROW = 16, 18, 5, 6
STRINGS = textpack.read_strings()
TXT = dict(STRINGS)
NM = {K_RAT: "RAT", K_SLIME: "SLIME", K_GOBLIN: "GOBLIN", K_SKELETON: "SKELETON", K_BAT: "BAT"}
IMG = textpack.parse_emitted(os.path.join(BUILD_DIR, "text", "strings.asm"))


def stream_text(raw):
    """A log ring entry (token stream) -> text (tk_get's expansion)."""
    return textpack.expand(IMG, raw)   # w2d: the layout lives in textpack


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
            print("[skip] abil_melee needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"abil_melee: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    sym, b3 = CT.load()
    ab = sym["ab_rank"] - CT.BASE
    kt = {}
    probe = S["probe_act_fire"]
    kdie = kbon = 0
    slots = {}                                    # kind -> a slot holding it after boot

    def stand(kind):
        return HY + 6 - kt[kind]["bh"]

    def place(slot, x, y, flags, hp=None, kind=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(mons, learn=None, mp=20, hero=(HX, HY)):
        """Fresh Warrior game in PROTO room A: every monster parked, the hero
        at `hero` facing right (HP 200), mons = [(kind, x, y | None, hp,
        left)] (y None: standing on the hero's floor), learn = {abl: rank}
        -> ARANK (abil_load picks the row)."""
        nonlocal kdie, kbon
        p.boot(K_KNIGHT)
        if not kt:
            kt.update(p.kinds())
            kdie = p.rb(S["kind_tab"] + S["KT_DIE"] + K_KNIGHT)
            kbon = p.rb(S["kind_tab"] + S["KT_BONUS"] + K_KNIGHT)
            for sl in range(1, 16):
                k = p.ent(sl)["KIND"]
                slots.setdefault(k, sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, hero[0], hero[1], EF_ACTIVE | EF_PLAYER, 200)
        out = {}
        for kind, x, y, hp, left in mons:
            sl = slots[kind]
            place(sl, x, stand(kind) if y is None else y,
                  EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), hp)
            out[sl] = kind
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.wb("MP", mp)
        p.wb("MAXMP", max(mp, 1))
        av = 0
        for abl, r in (learn or {}).items():
            k = abl - POWER
            av |= r << (2 * k)
        p.wmem(S["ARANK"], w16(av))
        p.wb("FX_DROP", 0)
        p.tick(3)
        return out

    def last_line():
        p.until(lambda: p.rb("LOG_QN") == 0, 30)
        p.tick(2)
        return world.log_row(p.composed_frame(), 23)

    def shows(text):
        return last_line() == world.text6(text)

    def refuse(tag, abl, want_txt, force=False):
        mp0 = p.rb("MP")
        if force:
            p.wb("SEL_SLOT", SLOT[abl])
            p.tick()
        else:
            p.select_slot(SLOT[abl])
        t0 = p.rw("TURN_COUNTER")
        nt = p.no_turn("FIRE")
        got = dict(no_turn=nt, tc=p.rw("TURN_COUNTER") - t0, mp=p.rb("MP"), pend=p.rb("TURN_PEND"),
                   line=shows(want_txt))
        check(f"{tag}: refused, no turn, MP / TURN_PEND untouched, {want_txt!r}",
              got == dict(no_turn=True, tc=0, mp=mp0, pend=0, line=True), got)

    # ---- the model ------------------------------------------------------------
    def model_world():
        cur = p.rb("CUR_ROOM")
        w = World(kt, list(p.z.read_memory(S["HERO_RES"], 3)), p.rb("HERO_DEF"))
        w.hero_imm = p.rb("HERO_IMM")
        stf = p.z.read_memory(S["ST_FLAGS"], 16)
        st1 = p.z.read_memory(S["ST_T1"], 16)
        for sl in range(16):
            e = p.ent(sl)
            if e["FLAGS"] & (EF_ACTIVE | EF_PENDING) != EF_ACTIVE or e["ROOM"] != cur:
                continue
            b = Body(sl, e["KIND"], e["X"], e["Y"], e["HP"], e["MAXHP"], e["FLAGS"])
            b.stf, b.st1 = stf[sl], st1[sl]
            w.bodies[sl] = b
        return w

    def blows(w, rng, abl, rank, tgts):
        """melee_hit per target in slot order: [(slot, hit, lost)]."""
        mp, _, die, bonus, bounces, eff = CT.RANKS[NAME[abl]][rank - 1]
        dty, _, _, _, fl, hit = CT.DEFS[abl]
        x2 = fl & CT.DMGX2
        out = []
        for sl in sorted(tgts):
            # RANK1: Power Strike's to-hit = ab_def + RK_BOUNCES (+0 / 1 / 2), Whirlwind's + RK_EFFECT
            if not w.hit_roll(rng, 0, sl, hit + (bounces if x2 else eff)):
                out.append((sl, False, 0))
                continue
            d = rng.mod(kdie) + 1 + kbon + bonus
            if x2:                                  # RANK1: 2d + RK_DIE x d div 2 (x2 / x2.5 / x3)
                d = min(255, 2 * d + (die * d) // 2)
            lost = w.deal(rng, 0, sl, d, dty, 0)
            b = w.bodies[sl]
            if x2 and lost and b.hp:                # deal_hit's STUNNED (chance 0: always)
                turns = eff & 15
                if w.resp(b, dty)[0] == R:
                    turns //= 2
                if turns and not (w.imm(b) & STUN_IMM) and not (b.stf & GUARD):
                    same = (b.stf & 3) == 3
                    cur = b.st1 >> 4
                    b.stf = (b.stf & ~3) | 3
                    b.st1 = (b.st1 & 0x0F) | ((max(cur, turns) if same else turns) << 4)
            out.append((sl, True, lost))
        return out

    def find_seed(w0, abl, rank, tgts, want):
        """The first seed whose blows satisfy want(results)."""
        for seed in range(1, 20000):
            w = copy.deepcopy(w0)
            rng = proj3.Rng(seed)
            res = blows(w, rng, abl, rank, tgts)
            if want(res, w):
                return seed, w, res, rng.st
        raise AssertionError("no seed")

    def ring():
        q = S["LOG_Q"]
        return (p.rb(q + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"], p.rb("LOG_QN")

    def ring_lines(w0, n):
        out = []
        for i in range(n):
            sl = (w0 + i) % S["LOG_SLOTS"]
            out.append(stream_text(p.z.read_memory(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], S["LOG_SLOT_LEN"])))
        return out

    def strike(tag, abl, rank, mons, tgts, want, mp=20):
        """One power attack through the controls; tgts = the slots it must
        strike (independent of melee_scan), want(res, w) picks the seed."""
        kinds = scene(mons, learn={abl: rank}, mp=mp)
        while rank > 1 and CT.RANKS[NAME[abl]][rank - 1][0] > mp:       # RANK1 auto-downcast
            rank -= 1
        cost = CT.RANKS[NAME[abl]][rank - 1][0]
        p.select_slot(SLOT[abl])
        t0 = p.rw("TURN_COUNTER")
        p.tap("FIRE")
        e0 = p.z.read_memory(S["P_ENTITIES"], STRIDE)
        seq = S["kn_power" if abl == POWER else "kn_whirl"]
        acc = dict(mp=p.rb("MP"), pend=list(p.z.read_memory(S["TURN_PEND"], 4)), ph=p.rb("TURN_PHASE"),
                   seq=seq <= (e0[13] << 8 | e0[12]) < seq + 7)
        want_acc = dict(mp=mp - cost, pend=[S["TP_ACT"] | S["TP_MON"], abl, 2, 3], ph=1, seq=True)
        check(f"{tag}: accept pays {cost} MP, TURN_PEND set", acc == want_acc, (acc, want_acc))
        p.z.cmd("set-breakpoint 3 PC=%d" % probe)
        p.extra_probes = {probe}
        for _ in range(6):
            p.tick()
            if p.pc() == probe:
                break
        at = p.pc() == probe and p.rb("TURN_TICK") == 2
        check(f"{tag}: the strike on TURN_TICK 2", at, (p.pc(), p.rb("TURN_TICK")))
        if not at:
            p.z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            return
        w0 = model_world()
        seed, w, res, rng_end = find_seed(w0, abl, rank, tgts, want)
        p.wmem(S["RNG_STATE"], w16(seed))
        wr0, qn0 = ring()
        drop0 = p.rb(S["LOG_Q"] + S["LQ_DROP"])
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        p.tick()                                  # the rest of the fire tick
        mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        stf = p.z.read_memory(S["ST_FLAGS"], 16)
        st1 = p.z.read_memory(S["ST_T1"], 16)
        got = {sl: (mem[sl * STRIDE + 5], bool(mem[sl * STRIDE + 2] & EF_DYING), stf[sl], st1[sl])
               for sl in w.bodies}
        exp = {sl: (b.hp, bool(b.flags & EF_DYING), b.stf, b.st1) for sl, b in w.bodies.items()}
        check(f"{tag}: HP / DYING / status / RNG == the model {res}",
              got == exp and p.rw("RNG_STATE") == rng_end, (got, exp, p.rw("RNG_STATE"), rng_end))
        hurt = [sl for sl, hit, lost in res if lost]
        rx = {sl: (mem[sl * STRIDE + E_REACTAT], bool(mem[sl * STRIDE + E_REACT] & 0x80),
                   mem[sl * STRIDE + 19]) for sl in hurt}
        check(f"{tag}: struck bodies react on the strike tick (E_REACTAT 2, running), flash ATTR_HIT",
              all(v == (2, True, S["ATTR_HIT"]) for v in rx.values()), rx)
        wr1, qn1 = ring()
        lines = ring_lines(wr0, qn1 - qn0)
        exp_lines = []
        for sl, hit, lost in res:
            b, k = w.bodies[sl], kinds[sl]
            if hit and lost and b.hp and (b.stf & 3) == 3 and not (w0.bodies[sl].stf & 3):
                exp_lines.append("THE " + NM[k] + TXT["st_m_stunned"])
            word = "you_miss" if not hit else ("you_kill" if b.hp == 0 else "you_hit")
            if word == "you_hit" and abl == POWER:
                word = "cmb_power"                # LOG-DMG: "YOU SMASH <kind>"
            tail = ""                             # LOG-DMG: " -D" (+ " HP H" alive); D = 0: none
            if hit and lost:
                tail = f" -{min(lost, 99)}" + (f" HP {min(b.hp, 99)}" if b.hp else "")
            exp_lines.append(TXT[word] + NM[k] + tail)
        check(f"{tag}: the lines {exp_lines}",
              [l.rstrip(".") for l in lines] == [l.rstrip(".") for l in exp_lines]
              and p.rb(S["LOG_Q"] + S["LQ_DROP"]) == drop0, (lines, exp_lines))
        tracks = [list(p.z.read_memory(S[f"FXT{i}"], 32)) for i in range(3)]
        live = sorted((t[FXD_COL], t[FXD_ROW], t[FX_FID]) for t in tracks if t[FX_ST])
        if abl == POWER:
            want_fx = []
            if hurt:
                tb = w.bodies[hurt[0]]
                row = max(tb.y, min(HY + 2, tb.y + kt[tb.kind]["bh"] - 2))
                want_fx = [(tb.x, row, S["FID_power_burst"])]
        else:
            want_fx = sorted([(HX - 1, HY + 2, S["FID_spark_fizz1"]), (HX + 3, HY + 2, S["FID_spark_fizz1"])])
        check(f"{tag}: FX set on the strike tick {want_fx}", live == want_fx, (live, want_fx))
        p.tick()
        tracks = [list(p.z.read_memory(S[f"FXT{i}"], 32)) for i in range(3)]
        live2 = sorted(t[FX_FID] for t in tracks if t[FX_ST])
        want2 = sorted(S["FID_power_burst"] if abl == POWER else S["FID_spark_fizz2"] for _ in want_fx)
        check(f"{tag}: the impact frame the next tick", live2 == want2, (live2, want2))
        seen = []
        for _ in range(120):
            seen.append((p.rb("TURN_PEND"), p.rb("FX_BUSY")))
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
            p.tick()
        kmon = next((i for i, s in enumerate(seen) if s[0] == 0), None)
        tc1, mp1 = p.rw("TURN_COUNTER"), p.rb("MP")
        drained = p.until(lambda: p.rb("LOG_QN") == 0, 60)
        check(f"{tag}: monsters only after the FX is idle, the turn ends, MP stays, FX_DROP 0, the log drains",
              kmon is not None and seen[kmon][1] == 0 and tc1 == t0 + 1
              and mp1 == mp - cost and p.rb("FX_DROP") == 0 and drained,
              (kmon, seen[:10], tc1 - t0, mp1, p.rb("FX_DROP"), p.rb("LOG_QN")))

    gx = HX + 3                                   # gap 0 in front (the Knight's bw 3)
    all_hit = lambda res, w: all(hit for _, hit, _ in res) and all(w.bodies[s].hp for s, _, _ in res)  # noqa: E731

    # ---- refusals ---------------------------------------------------------------
    scene([(K_GOBLIN, gx, None, 30, True)])
    refuse("R1 Power Strike not learned", POWER, TXT["not_learned"], force=True)
    scene([(K_GOBLIN, gx, None, 30, True)], learn={POWER: 1}, mp=1)
    refuse("R2 Power Strike r1 with 1 MP", POWER, TXT["no_mana"])
    scene([(K_GOBLIN, gx, None, 30, True)], learn={WHIRL: 3}, mp=3)
    refuse("R2 Whirlwind r3 with 3 MP (rank 1 costs 4)", WHIRL, TXT["no_mana"])
    scene([], learn={POWER: 1, WHIRL: 1}, mp=20, hero=(5, HY))
    p.turn("K")                                   # one row up the {5,1} shaft: mid-ladder
    rat = slots[K_RAT]
    place(rat, 8, stand(K_RAT), EF_ACTIVE | EF_HOSTILE | EF_LEFT, 30)
    check("R3 hero mid-ladder", p.ent(0)["Y"] == HY - 1, p.ent(0)["Y"])
    refuse("R3 Power Strike mid-ladder", POWER, TXT["no_target"])
    refuse("R3 Whirlwind mid-ladder", WHIRL, TXT["no_target"])
    scene([(K_GOBLIN, HX - 3, None, 30, False)], learn={POWER: 1})
    refuse("R4 Power Strike, a Goblin behind only", POWER, TXT["no_target"])
    scene([(K_GOBLIN, gx + 1 + 1, None, 30, True), (K_RAT, HX - 4 - 2, None, 30, False)], learn={WHIRL: 1})
    refuse("R4 Whirlwind, nearest bodies 2 cols away", WHIRL, TXT["no_target"])

    # ---- Power Strike per rank ---------------------------------------------------
    gob, slime, ratsl = slots[K_GOBLIN], slots[K_SLIME], slots[K_RAT]
    for r in (1, 2, 3):
        strike(f"P{r} Power Strike r{r} on a Goblin", POWER, r, [(K_GOBLIN, gx, None, 60, True)], [gob], all_hit)
    strike("P4 Power Strike r1 on a Slime (PHYS R: no stun)", POWER, 1, [(K_SLIME, gx, None, 60, True)],
           [slime], all_hit)
    strike("P5 Power Strike r3 kills a Rat", POWER, 3, [(K_RAT, gx, None, 1, True)], [ratsl],
           lambda res, w: res[0][1] and w.bodies[ratsl].hp == 0)
    strike("P6 Power Strike r1 misses", POWER, 1, [(K_GOBLIN, gx, None, 60, True)], [gob],
           lambda res, w: not res[0][1])

    # ---- Whirlwind -----------------------------------------------------------------
    bat, skel = slots[K_BAT], slots[K_SKELETON]
    strike("W1 Whirlwind r1: Rat + Bat right, Goblin left (Skeleton out of reach)", WHIRL, 1,
           [(K_RAT, gx, None, 60, True), (K_BAT, gx, HY, 60, True), (K_GOBLIN, HX - 3, None, 60, False),
            (K_SKELETON, HX + 8, None, 60, True)], [ratsl, bat, gob], all_hit)
    strike("W2 Whirlwind r2 (+2 dmg) on a Goblin", WHIRL, 2, [(K_GOBLIN, gx, None, 60, True)], [gob], all_hit)
    strike("W3 Whirlwind r3 (10 MP, dmg +4, to-hit +2) both sides", WHIRL, 3,
           [(K_GOBLIN, gx, None, 60, True), (K_RAT, HX - 4, None, 60, False)], [gob, ratsl], all_hit)
    # RANK1 auto-downcast: learned rank 3, the pool covers only rank 2 / rank 1 (NO MANA stays at rank 1's cost)
    strike("D1 Power Strike r3 with MP 3 casts rank 2 (3 MP, x2.5)", POWER, 3,
           [(K_GOBLIN, gx, None, 60, True)], [gob], all_hit, mp=3)
    strike("D2 Power Strike r3 with MP 2 casts rank 1 (2 MP)", POWER, 3,
           [(K_GOBLIN, gx, None, 60, True)], [gob], all_hit, mp=2)
    strike("D3 Whirlwind r3 with MP 8 casts rank 2 (7 MP, dmg +3)", WHIRL, 3,
           [(K_GOBLIN, gx, None, 60, True)], [gob], all_hit, mp=8)

    # ---- K: T7 power_fire skips a target that is DYING / HP 0 by the strike -------------
    # (none can be today: poked between the accept and the fire tick) — no d20 for it,
    # no line; the other target is struck as the model says (RNG for one target only).
    kinds = scene([(K_GOBLIN, gx, None, 60, True), (K_RAT, HX - 4, None, 60, False)], learn={WHIRL: 1})
    p.select_slot(SLOT[WHIRL])
    p.tap("FIRE")
    p.z.cmd("set-breakpoint 3 PC=%d" % probe)
    p.extra_probes = {probe}
    for _ in range(6):
        p.tick()
        if p.pc() == probe:
            break
    p.set_ent(ratsl, HP=0, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_DYING)
    w0 = model_world()
    w0.bodies.pop(ratsl, None)
    seed, w, res, rng_end = find_seed(w0, WHIRL, 1, [gob], all_hit)
    p.wmem(S["RNG_STATE"], w16(seed))
    wr0, qn0 = ring()
    p.z.cmd("set-breakpoint 3")
    p.extra_probes = set()
    p.tick()
    wr1, qn1 = ring()
    lines = [l.rstrip(".") for l in ring_lines(wr0, qn1 - qn0)]
    got = dict(lines=lines, rng=p.rw("RNG_STATE") == rng_end, gob=p.ent(gob)["HP"], rat=p.ent(ratsl)["HP"])
    check("K Whirlwind: a DYING target is skipped (no roll, no line), the other struck",
          got == dict(lines=[TXT["you_hit"] + "GOBLIN" + f" -{res[0][2]} HP {w.bodies[gob].hp}"], rng=True,
                      gob=w.bodies[gob].hp, rat=0), (got, res))
    p.until(lambda: p.idle(), 120)

    # ---- E: T7 edge clamp — the 40-px frames at cols 0 / 29 -----------------------------
    # Before T7 a WHIRL / POWER_STRIKE / SLASH frame wider than the body wrapped below x 0
    # (col 0) or ran past x 255 (col 29): blit_clip counted CLIP_TRAP and the hero vanished
    # for those ticks. Now render clamps the frame anchor: CLIP_TRAP / BLIT_MISS 0 and the
    # hero drawn on every tick of the turn.
    def edge(tag, what, hx, left):
        gxe = hx - 3 if left else hx + 3
        scene([(K_GOBLIN, gxe, None, 60, not left)], learn={POWER: 3, WHIRL: 3}, mp=20, hero=(hx, HY))
        if left:
            p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER | EF_LEFT)
            p.tick(2)
        p.wb("CLIP_TRAP", 0)
        p.wb("BLIT_MISS", 0)
        t0 = p.rw("TURN_COUNTER")
        if what == "SLASH":
            p.select_slot(0)
        else:
            p.select_slot(SLOT[what])
        p.tap("FIRE")
        hidden, fids = 0, set()
        for _ in range(60):
            p.tick()
            e = p.ent(0)
            if not e["DVIS"] & 1:
                hidden += 1
            fids.add(e["DFID"])
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
        want_fid = {"SLASH": "FID_knight_slash", POWER: "FID_knight_powerstrike", WHIRL: "FID_knight_whirl"}[what]
        got = dict(turn=p.rw("TURN_COUNTER") - t0, clip=p.rb("CLIP_TRAP"), miss=p.rb("BLIT_MISS"), hidden=hidden,
                   drew=S.get(want_fid) in fids, x=p.ent(0)["X"])
        check(f"E {tag}: CLIP_TRAP 0, the hero drawn every tick (the wide frame clamped)",
              got == dict(turn=1, clip=0, miss=0, hidden=0, drew=True, x=hx), (got, sorted(fids)))

    for what, nm in ((POWER, "Power Strike"), (WHIRL, "Whirlwind"), ("SLASH", "SLASH")):
        edge(f"{nm} at col 0 facing right", what, 0, False)
        edge(f"{nm} at col 29 facing left", what, 29, True)

    # ---- L: T7 log drain — three Whirlwind turns back to back (FIRE tapped) ----------------
    # budget.py "wcast" geometry: 3 bodies, each turn 3 hit lines + their replies.
    # Before T7 every tick of such a turn was in its 2nd frame, the log never drew and
    # LOG_SLOTS 4 dropped 14 lines in 3 turns. Now act_pend draws while > LOG_MON_MAX
    # are pending before the monsters act, and end_turn holds the next turn
    # (turn_input draws one line a tick) until the queue is empty.
    scene([(K_SKELETON, HX - 3, None, 60, False), (K_RAT, gx, None, 60, True), (K_BAT, gx, HY, 60, True)],
          learn={WHIRL: 3}, mp=40)
    p.select_slot(SLOT[WHIRL])
    drop0 = p.rb(S["LOG_Q"] + S["LQ_DROP"])
    t0 = p.rw("TURN_COUNTER")
    for _ in range(120):                          # FIRE tapped every other tick: the
        p.tap("FIRE")                             # latched INTENT starts each next turn
        if p.rw("TURN_COUNTER") >= t0 + 3:        # on its first INPUT tick
            break
    p.until(lambda: p.idle() and p.rb("LOG_QN") == 0, 120)
    got = dict(turns=p.rw("TURN_COUNTER") - t0, drop=p.rb(S["LOG_Q"] + S["LQ_DROP"]) - drop0,
               qn=p.rb("LOG_QN"), hold=p.rb("LOG_TURN") & S["LT_HOLD"] if p.rb("LOG_QN") else 0)
    check("L 3 Whirlwind turns, FIRE tapped throughout: no log line dropped, the log drains",
          got["turns"] >= 3 and got["drop"] == 0 and got["qn"] == 0, got)


if __name__ == "__main__":
    sys.exit(main())
