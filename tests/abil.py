#!/usr/bin/env python3
"""D3-7 T3: abil_load's rank row + the DEBUG start kit (src/rank3.asm, hero_st_init).

  K1  start state per class after START: the base MP (Warrior 6 / Mage 12,
      game.md §4) and no abilities on a release build; on a DEBUG_KIT=1 build
      (needs GAME_ALLOW_DEBUG_KIT=1) the designer's kit: Mage 5 spells rank 1,
      MP 40/40; Warrior bow, ARROWS 20, DAGGERS 8, Power Strike + Whirlwind
      rank 1, MP 20/20
  K2  RANK1 abil_load (run in bank 3 over a booted game): for each class, rank
      pattern and MP, ABIL_RK == ab_rank[(cls_base + k) * 3 + q - 1] with q the
      highest rank <= the hero's with cost <= MP (rank 1 is the floor;
      auto-downcast), and a spell's row is also CAST_ROW
D3-7 T4: the Mage spells as a split ability turn (abil_spell / spell_fire,
src/abil_spell7.asm) and the staff bonk (melee_bonk), played through the real
controls (number key + FIRE) in PROTO room A, release build (DEBUG_KIT=0):
  S1..S5  Spark r1 / Firebolt r1 (burst) / Frost r2 (freeze) / Drain r1 (heal)
      / Lightning r3 (pierce + bounce): the accept pays RR_MP (MP, TURN_PEND
      = TP_ACT | TP_MON, the hero flashes the spell ink ABD_AT1); D3-8e: the
      cast's strikes start in the accept (act_begin -> proj_pre), so the
      proj3 Python model is run on the state at probe_act_prep (bodies,
      flight row, RNG) as a one-shot cast at the release (TURN_TICK 2,
      delay 0), the release is reached (probe_act_fire, TURN_TICK 2) and
      after the fire tick pf_stop / pf_col / pf_tgt / pf_lost / pf_itick / pf_desc, the RNG,
      every body's HP / DYING / E_REACTAT / ST_FLAGS / ST_T1 == the model; the
      struck monsters' reactions start on their E_REACTAT (the FX tick; the
      first target's = pf_itick unless it pierced); the monster phase
      (TURN_PEND -> 0) runs only once FX_BUSY = 0 and no monster moved
      before it (a Goblin behind the hero walks after); FX_DROP = 0; Drain:
      the hero flashes ATTR_HEAL after the release
  S6  Spark with MP 0: refused, no turn, MP / TURN_PEND untouched, "NO MANA"
      logged
  S7  staff bonk: Mage melee until a hit: every swing plays wz_bonk (CAST1,
      no STAFF_RAISE); on the hit the staff_bonk FX (impact-only) is set on
      the target's E_REACTAT tick = KS_IMPACT, drawn the tick after (attr
      $46) at the target's front col
  G1  golden "abil_spark_cast": the composed frame with the hero in CAST2 and
      the Spark in flight (--update-golden rewrites it)
Run: ZRCP_PORT=<port> python3 tests/abil.py [--update-golden] [--png DIR]
     (K1 kit checks: GAME_ALLOW_DEBUG_KIT=1 on a DEBUG_KIT=1 build; S/G need
     DEBUG_KIT=0 and are skipped on a kit build)
"""
import hashlib
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_SLIME, K_GOBLIN,  # noqa: E402
                      K_SKELETON, stand_y, split_frame, attr_at, frame_png)
from proj3 import T, w16, World, Body, Rng  # noqa: E402
import combat_tables as CT  # noqa: E402

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
UPDATE = "--update-golden" in sys.argv
PNG_DIR = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None

RK = 6
SENT = 0xEE
KIT = bool(S.get("KIT_DEBUG", 0))


def main():
    fails = []
    sym, b3 = CT.load()
    ab = sym["ab_rank"] - CT.BASE
    ab_rank = lambda row: list(b3[ab + row * RK: ab + (row + 1) * RK])  # noqa: E731
    base = {K_KNIGHT: S["ABL_POWER"], K_WIZARD: 0}
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        for kind, name in ((K_KNIGHT, "Warrior"), (K_WIZARD, "Mage")):
            p.boot(kind)
            mp, mx = p.rb("MP"), p.rb("MAXMP")
            arank = p.rw("ARANK")
            if KIT:
                if kind == K_KNIGHT:
                    want = dict(mp=20, mx=20, arank=0b0101, bow=1, arrows=20, daggers=8)
                    nk = 2
                else:
                    want = dict(mp=40, mx=40, arank=0b0101010101, bow=0, arrows=0, daggers=0)
                    nk = 5
                got = dict(mp=mp, mx=mx, arank=arank, bow=p.rb("HAS_BOW"),
                           arrows=p.rb("ARROWS"), daggers=p.rb("DAGGERS"))
                check(f"K1 {name} debug kit == {want}", got == want, got)
            else:
                want = dict(mp=6 if kind == K_KNIGHT else 12, arank=0)
                want["mx"] = want["mp"]
                got = dict(mp=mp, mx=mx, arank=arank)
                check(f"K1 {name} release start: base MP {want['mp']}, no abilities", got == want, got)

            # K2 (RANK1): abil_load over poked ARANK patterns and MP: ABIL_RK == the ab_rank row of the
            # highest rank <= the hero's whose cost is <= MP (rank 1 is the floor; an unlearned ability
            # reads rank 1), and a spell's row is also CAST_ROW
            nk = 2 if kind == K_KNIGHT else 5
            rng = random.Random(7 + kind)
            pats = [[0] * nk, [1] * nk, [2] * nk, [3] * nk, [3, 2, 1, 0, 3][:nk], [0, 3, 0, 2, 1][:nk]]
            pats += [[rng.randrange(4) for _ in range(nk)] for _ in range(10)]
            bad, n = [], 0
            for pat in pats:
                av = sum(r << (2 * k) for k, r in enumerate(pat))
                p.wmem(S["ARANK"], w16(av))
                for mp in (0, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 40):
                    p.wb("MP", mp)
                    for k in range(nk):
                        abl = base[kind] + k
                        r = max(pat[k], 1)
                        while r > 1 and ab_rank(abl * 3 + r - 1)[0] > mp:
                            r -= 1
                        want = ab_rank(abl * 3 + r - 1)
                        p.z.cmd("write-memory %d %s" % (S["CAST_ROW"], " ".join([str(SENT)] * RK)))
                        assert p.code(p.bank3([0x3E, abl, 0xCD] + w16(S["abil_load"])))
                        got = list(p.z.read_memory(S["ABIL_RK"], RK))
                        crow = list(p.z.read_memory(S["CAST_ROW"], RK))
                        n += 1
                        if got != want or crow != (want if abl < S["ABL_POWER"] else [SENT] * RK):
                            bad.append((pat, mp, k, got, crow, want))
            check(f"K2 {name} abil_load == the highest affordable ab_rank row, CAST_ROW for spells ({n} cases)",
                  not bad, bad[:1])

        if not KIT:
            spells(h, p, check)

        print(f"abil: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


# ---- D3-7 T4: spells + staff bonk through the controls ----------------------------
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, 8, 16, 64
E_REACT, E_REACTAT = 15, 16
HY = stand_y(1, 6)                         # the hero on room A's bottom storey
HX = 9
NOWHERE = 7
SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING = range(5)
NAMES = ["Spark", "Firebolt", "Frost", "Drain", "Lightning"]
SLOT_KIND = {1: K_RAT, 2: K_SLIME, 3: K_GOBLIN, 5: K_SKELETON}   # PROTO room A slots (game.py SLOT_*)
M_MOVE = 1


def golden(h, name, data):
    """game.py's golden format (play / panel hashes); --update-golden writes."""
    play, panel = split_frame(bytes(data))
    got = {"play": hashlib.sha256(play).hexdigest(), "panel": hashlib.sha256(panel).hexdigest()}
    path = os.path.join(GOLDEN_DIR, name + ".hash")
    if PNG_DIR:
        os.makedirs(PNG_DIR, exist_ok=True)
        frame_png(bytes(data), os.path.join(PNG_DIR, name + ".png"))
    if UPDATE:
        open(path, "w").write("".join(f"{k} {v}\n" for k, v in got.items()))
        print(f"[golden] wrote {path}")
        return True
    try:
        ref = dict(l.split() for l in open(path).read().split("\n") if len(l.split()) == 2)
    except FileNotFoundError:
        print(f"[FAIL] golden missing: {path} (run --update-golden)")
        return False
    return all(h.expect(f"golden {name} {k}", got[k], ref.get(k)) for k in ("play", "panel"))


def spells(h, p, check):
    sym, b3 = CT.load()
    ab = sym["ab_rank"] - CT.BASE
    kt = None
    probe = S["probe_act_fire"]

    def stand(kind):
        return HY + kt[K_WIZARD]["bh"] - kt[kind]["bh"]

    def place(slot, x, y, flags, hp=None, room=0):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room, FLAGS=flags, REACT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(mons, hero_hp=60, behind=True, mp=40, learn=None):
        """Fresh Mage game in PROTO room A: every monster parked, the hero at
        HX facing right, `mons` = [(slot, x, hp)] on his floor (facing him),
        a Goblin (slot 3) behind him if `behind`; MP / MAXMP = mp; learn =
        {k: rank} -> ARANK (abil_load picks the ab_rank row)."""
        nonlocal kt
        p.boot(K_WIZARD)
        if kt is None:
            kt = p.kinds()
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, hero_hp)
        p.set_ent(0, MAXHP=max(hero_hp, 60))      # (Drain: room to heal)
        for sl, x, hp in mons:
            place(sl, x, stand(SLOT_KIND[sl]), EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp)
        if behind:
            place(3, 2, stand(K_GOBLIN), EF_ACTIVE | EF_HOSTILE, 60)
        p.wb("MP", mp)
        p.wb("MAXMP", max(mp, 1))
        av = 0
        for k, r in (learn or {}).items():
            av |= r << (2 * k)
        p.wmem(S["ARANK"], w16(av))
        p.wb("FX_DROP", 0)
        p.tick(3)

    def model_world():
        cur = p.rb("CUR_ROOM")
        w = World(kt, list(p.z.read_memory(S["HERO_RES"], 3)), p.rb("HERO_DEF"))
        w.hero_imm = p.rb("HERO_IMM")
        w.turn_tick = p.rb("TURN_TICK")
        stf = p.z.read_memory(S["ST_FLAGS"], 16)
        st1 = p.z.read_memory(S["ST_T1"], 16)
        for sl in range(16):
            e = p.ent(sl)
            if e["FLAGS"] & (EF_ACTIVE | EF_PENDING) != EF_ACTIVE or e["ROOM"] != cur:
                continue
            b = Body(sl, e["KIND"], e["X"], e["Y"], e["HP"], e["MAXHP"], e["FLAGS"])
            b.stf, b.st1 = stf[sl], st1[sl]
            w.bodies[sl] = b
        row0 = w.bodies[0].y + S["PF_ROW_DY"]
        w.row = list(p.z.read_memory(S["ROOM_MAP"] + row0 * 32, 32))
        tf = p.z.read_memory(S["tile_flags"], 64)
        solid = {i for i in range(64) if tf[i] & S["TF_SOLID"]}
        return w, solid

    def snap():
        e = {sl: p.ent(sl) for sl in range(16)}
        mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        return dict(tt=p.rb("TURN_TICK") - 1, pend=p.rb("TURN_PEND"), busy=p.rb("FX_BUSY"),
                    ent=e, rat=[mem[sl * STRIDE + E_REACTAT] for sl in range(16)],
                    tracks=[list(p.z.read_memory(S[f"FXT{i}"], 32)) for i in range(3)])

    def cast(tag, k, rank, mons, hero_hp=60, gold=None, mp=40):
        """rank = the learned rank; with a low `mp` the cast downcasts (RANK1): the
        rank cast = the highest one whose cost <= mp (rank 1 floor)."""
        scene(mons, hero_hp, learn={k: rank}, mp=mp)
        while rank > 1 and b3[ab + (k * 3 + rank - 1) * 6] > mp:
            rank -= 1
        cost = b3[ab + (k * 3 + rank - 1) * 6]
        mp0 = p.rb("MP")
        p.select_slot(k + 1)
        t0 = p.rw("TURN_COUNTER")
        prep = S["probe_act_prep"]                # D3-8e: the strikes start in the accept
        p.z.cmd("set-breakpoint 3 PC=%d" % prep)
        p.extra_probes = {prep}
        p.tap("FIRE")                             # (stops at the probe, mid input tick)
        at_prep = p.pc() == prep
        w, solid = model_world()                  # the world before the first strike
        w.turn_tick = S["ACT_FIRE_TICK"]          # a one-shot cast at the release
        seed = p.rw("RNG_STATE")
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        if at_prep:
            p.tick()                              # the rest of the input tick
        check(f"S{k + 1} {tag}: the accept reaches proj_pre (probe_act_prep)", at_prep, p.pc())
        hero = p.ent(0)
        acc = dict(mp=p.rb("MP"), pend=list(p.z.read_memory(S["TURN_PEND"], 4)), fla=hero["FLA"],
                   flt=hero["FLT"], ph=p.rb("TURN_PHASE"))
        want = dict(mp=mp0 - cost, pend=[S["TP_ACT"] | S["TP_MON"], k, 2, 3], fla=CT.DEFS[k][1],
                    flt=acc["flt"] if acc["flt"] > 0 else -1, ph=1)
        check(f"S{k + 1} {tag}: accept pays {cost} MP, TURN_PEND set, spell-ink flash", acc == want, (acc, want))
        # to the release
        p.z.cmd("set-breakpoint 3 PC=%d" % probe)
        p.extra_probes = {probe}
        for _ in range(6):
            p.tick()
            if p.pc() == probe:
                break
        at_probe = p.pc() == probe
        check(f"S{k + 1} {tag}: the release on TURN_TICK 2", at_probe and p.rb("TURN_TICK") == 2,
              (at_probe, p.rb("TURN_TICK")))
        if not at_probe:
            p.z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            return None
        rng = Rng(seed)
        res = w.fire(rng, 0, k, rank, 0, solid)
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        p.tick()                                 # the rest of the fire tick
        got = {n: p.rb(n) for n in ("pf_stop", "pf_col", "pf_tgt", "pf_lost", "pf_itick")}
        got["desc"] = list(p.z.read_memory(S["pf_desc"], 16))
        got["rng"] = p.rw("RNG_STATE")
        mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        stf = p.z.read_memory(S["ST_FLAGS"], 16)
        st1 = p.z.read_memory(S["ST_T1"], 16)
        got["bodies"] = {sl: (mem[sl * STRIDE + 5], bool(mem[sl * STRIDE + 2] & EF_DYING),
                              mem[sl * STRIDE + E_REACTAT] if mem[sl * STRIDE + E_REACT] else None,
                              stf[sl], st1[sl]) for sl in w.bodies}
        exp = {"pf_stop": res["stop"], "pf_col": res["col"], "pf_tgt": res["tgt"], "pf_lost": res["lost"],
               "pf_itick": res["itick"], "desc": res["desc"], "rng": rng.st,
               "bodies": {sl: (b.hp, bool(b.flags & EF_DYING), b.reactat if b.react else None, b.stf, b.st1)
                          for sl, b in w.bodies.items()}}
        bad = [(n, got[n], exp[n]) for n in exp if got[n] != exp[n]]
        check(f"S{k + 1} {tag}: the cast == the proj3 model (stop {res['stop']}, tgt {res['tgt']},"
              f" lost {res['lost']}, itick {res['itick']})", not bad, bad)
        hero = p.ent(0)
        heal = (k == DRAINL and res["tgt"] not in (0, 0xFF) and res["lost"] > 0)
        if k == DRAINL:
            check(f"S{k + 1} {tag}: the hero flashes ATTR_HEAL after the release",
                  heal and hero["FLA"] == S["ATTR_HEAL"] and hero["FLT"] > 0, (heal, hero["FLA"], hero["FLT"]))
        # the rest of the turn, tick by tick
        ticks, shot = [snap()], None
        for _ in range(120):
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
            p.tick()
            ticks.append(snap())
            if gold and shot is None:
                fids = [t[S["FX_DFID"]] for t in ticks[-1]["tracks"]]
                if any(f in (S["FID_spark_fly1"], S["FID_spark_fly2"]) for f in fids):
                    shot = p.composed_frame()
                    shot_hero = ticks[-1]["ent"][0]["DFID"]
        # every struck monster's reaction (HURT / DEATH) starts on its E_REACTAT
        # = the tick the FX reaches it (the first target's for non-piercing
        # spells = pf_itick)
        starts = {sl: (next((t["tt"] for t in ticks if t["ent"][sl]["REACT"] & 0x80), None), b.reactat)
                  for sl, b in w.bodies.items() if sl and b.react}
        tgt = res["tgt"]
        first = tgt not in (0, 0xFF) and (k == LIGHTNING or w.bodies[tgt].reactat == res["itick"])
        check(f"S{k + 1} {tag}: reactions start at the FX tick (pf_itick {res['itick']})",
              starts and first and all(a == b for a, b in starts.values()), (first, starts))
        kmon = next((i for i, t in enumerate(ticks) if t["pend"] == 0), None)
        early = [t["tt"] for t in ticks[:kmon or 0]
                 if any(t["ent"][sl]["X"] != w.bodies[sl].x or t["ent"][sl]["MODE"] == M_MOVE
                        for sl in w.bodies if sl != 0)]
        walked = any(t["ent"][3]["X"] != w.bodies[3].x for t in ticks[kmon or 0:]) if 3 in w.bodies else True
        check(f"S{k + 1} {tag}: monsters act only after the hero's FX is idle",
              kmon is not None and ticks[kmon]["busy"] == 0 and ticks[kmon - 1]["pend"] != 0 and not early
              and walked, (kmon, [(t["tt"], t["pend"], t["busy"]) for t in ticks[:12]], early, walked))
        check(f"S{k + 1} {tag}: FX_DROP 0", p.rb("FX_DROP") == 0, p.rb("FX_DROP"))
        if gold:
            ok = shot is not None and shot_hero == S["FID_wizard_cast2"]
            check(f"G1 a CAST2 frame with the spark in flight captured", ok,
                  (shot is not None, shot_hero if shot else None))
            if ok:
                check("G1 golden abil_spark_cast", golden(h, gold, shot))
        return res

    sx = HX + 3                                  # the first cell in front of the Mage (bw 3)
    cast("Spark r1 on a Rat", SPARK, 1, [(1, sx + 3, 40)], gold="abil_spark_cast")
    cast("Firebolt r1: Rat + burst on the Slime", FIREBOLT, 1, [(1, sx + 3, 40), (2, sx + 4, 40)])
    cast("Frost r2 freezes a Slime", FROST, 2, [(2, sx + 5, 40)])
    cast("Drain r1 on a Rat heals the hero", DRAINL, 1, [(1, sx + 2, 40)], hero_hp=5)
    cast("Lightning r3 through Rat, Slime, Skeleton", LIGHTNING, 3,
         [(1, sx + 2, 60), (2, sx + 6, 60), (5, sx + 10, 60)], hero_hp=120)

    # RANK1 auto-downcast: learned rank 3, MP only covers rank 2 / rank 1
    cast("Lightning III with MP 9 casts rank II (8 MP)", LIGHTNING, 3,
         [(1, sx + 2, 60), (2, sx + 6, 60), (5, sx + 10, 60)], hero_hp=120, mp=9)
    cast("Firebolt III with MP 4 casts rank I (3 MP)", FIREBOLT, 3, [(1, sx + 3, 40), (2, sx + 4, 40)], mp=4)

    # --- S6: no MP ---
    scene([(1, sx + 3, 40)], learn={SPARK: 1}, mp=0)
    p.select_slot(1)
    slot = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"]
    t0 = p.rw("TURN_COUNTER")
    nt = p.no_turn("FIRE")
    raw = p.z.read_memory(S["LOG_TXT"] + slot * S["LOG_SLOT_LEN"], S["LOG_MAX"])
    txt = bytes(raw).split(b"\0")[0].decode("latin-1")
    # (the ring holds the token stream: "NO " is a dictionary token)
    got = dict(no_turn=nt, tc=p.rw("TURN_COUNTER") - t0, mp=p.rb("MP"), pend=p.rb("TURN_PEND"),
               log=txt.endswith("MANA"))
    check("S6 Spark with 0 MP: refused, no turn, NO MANA", got == dict(no_turn=True, tc=0, mp=0, pend=0,
                                                                        log=True), (got, txt))

    # --- S7: the staff bonk ---
    scene([(3, HX + 3, 200)], hero_hp=200, behind=False)
    imp = p.rb((S["seq_rows"] & 0xFF00 | p.rb(S["kind_tab"] + S["KT_SEQ"] + K_WIZARD)) + S["KS_IMPACT"])  # 3F-T2 seq cache row
    bonk, raises, hit_turn = S["FID_staff_bonk"], 0, None
    for _ in range(8):
        t0 = p.rw("TURN_COUNTER")
        p.select_slot(0)
        p.tap("FIRE")
        ticks = [snap()]
        for _ in range(60):
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
            p.tick()
            ticks.append(snap())
            sh = ticks[-1]
            sh["attr"] = None
            for tr in sh["tracks"]:
                if tr[S["FX_DFID"]] == bonk:
                    sh["attr"] = attr_at(p.composed_frame(), tr[S["FX_DCOL"]], tr[S["FX_DROW"]])
        raises += sum(t["ent"][0]["DFID"] == S["FID_wizard_staffraise"] for t in ticks)
        if any(t["ent"][0]["HIT"] for t in ticks[:1]):
            hit_turn = ticks
            break
    check("S7 Mage swings play wz_bonk (no STAFF_RAISE frame)", raises == 0, raises)
    ok = hit_turn is not None
    if ok:
        ticks = hit_turn
        set_t = next((t["tt"] for t in ticks if any(tr[S["FX_FID"]] == bonk for tr in t["tracks"])), None)
        hurt_t = ticks[0]["rat"][3]               # E_REACTAT (the Goblin's own swing may delay the HURT)
        drawn = [t for t in ticks if t.get("attr") is not None]
        tr0 = next((tr for t in drawn for tr in t["tracks"] if tr[S["FX_DFID"]] == bonk), None)
        gob = ticks[0]["ent"][3]
        got = dict(set=set_t, hurt=hurt_t, drawn=drawn[0]["tt"] if drawn else None,
                   attr=drawn[0]["attr"] if drawn else None, col=tr0[S["FX_DCOL"]] if tr0 else None,
                   cast1=any(t["ent"][0]["DFID"] == S["FID_wizard_cast1"] for t in ticks))
        want = dict(set=imp, hurt=imp, drawn=imp + 1, attr=0x46, col=gob["X"], cast1=True)
        check(f"S7 staff bonk on the hit: set on the target's E_REACTAT = KS_IMPACT {imp}, drawn the next ($46) at the"
              f" target's front col", got == want, (got, want))
    check("S7 a hit within 8 swings", ok)


if __name__ == "__main__":
    sys.exit(main())
