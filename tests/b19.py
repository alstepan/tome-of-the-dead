#!/usr/bin/env python3
"""B19 (user, Fuse 2026-10-14): "a dagger kill comes back" — the Goblin /
Skeleton plays its death animation, then stands alive and attacks. Plus the
D-AI1a / B18 ladder hunt (the hero descending "lands on" a monster; a blocked
walker changes storey). PROTO room A, release build (DEBUG_KIT=0), played
through the real controls.

Kill path (thrown vs shot vs melee vs spell), per kind:
  K1  a lethal hit (HP 1, the RNG reseeded until the roll hits): from the kill
      on, every tick: HP stays 0, the slot is never ACTIVE without DYING, the
      DEATH reaction never runs with HP > 0; the slot is freed by the end of
      the death sequence and stays free for 3 more turns; the turn logs
      "YOU KILL THE <kind>" (no HITS line); after every settled tick (FX idle)
      the playfield == ROOM_MAP + the live bodies (game.T.bg_mismatch).
      Goblin / Skeleton x dagger / bow first, then every other walker / flyer
      with the dagger, then melee (Knight sword) and a spell (Mage Spark).
  K2  a non-lethal dagger / arrow hit (HP 40): no DEATH reaction at all, the
      line is "... HITS THE <kind>", the slot stays alive.
Root cause (B19): a PENDING body (§3.6: hidden, collides with nothing) under
a live monster. Monsters stepped onto a pending body's box (box_free ignores
PENDING), so the pending one stayed hidden under it; the kill made the box
"free" (DYING bodies don't collide) and materialise popped the hidden body
on the corpse — the same kind, often (a follower / an arrival). Fix: a
monster move never ends on a PENDING body of the room (logic.asm pend_hit).
  P2  (review) a walker already stacked on a PENDING body walks off it (no
      freeze) and the hidden body materialises.
  P1  the reported sequence: a Goblin PENDING beside the hero (an arrival),
      a 2nd Goblin walks in over it, the hero steps off and kills the walker
      with a dagger: no body ever appears on the corpse's box; invariant at
      every turn end: no PENDING body overlaps a live monster.
Ladder (D-AI1a / B18; prototype §6.4 rules 2-3 + the B14 squeeze):
  L0  the fuzz-found case, deterministic: hero mid-ladder turning down onto a
      Goblin on the shaft col (a Skeleton beside it): it yields over 3 turns,
      no squeeze, it stays on storey 1, the hero reaches the foot.
  L3  (review) several blockers on one path taking turns: bounded pass.
  L1  hero descending / climbing past ONE walker beside a shaft (room to
      yield): every tick the hero's box overlaps no live body, and no walker
      changes storey (the squeeze — a swap onto the other storey — only fires
      on a blocker that could not yield; B18 / D-AI1a root cause: it fired on
      the 2nd block although the blocker had just stepped aside, because one
      1-col sidestep can't clear a 3-col climb path; the Slime's every-2nd-
      turn gate also skipped its yield).
  L2  fuzz: 1..4 walkers around both shafts of room A, random climbs / walks:
      the hero never overlaps a live body; a walker changes storey only by
      the squeeze (logged "YOU SQUEEZE PAST"), never otherwise.
Run: ZRCP_PORT=<port> python3 tests/b19.py [K] [P] [L]   (default: all)
"""
import os
import random
import sys
from pathlib import Path

ARGV = sys.argv[1:]                             # (tests/world.py, imported below, rewrites sys.argv)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_SLIME, K_GOBLIN,  # noqa: E402
                      K_SKELETON, K_GHOST, K_BAT, stand_y)
from abil_ammo import stream_text, TXT  # noqa: E402
import combat_tables as CT  # noqa: E402

EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, 8, 16, 64
RC_DEATH_RUN = 0x80 | S["RC_DEATH"]
NAME = {K_RAT: "RAT", K_SLIME: "SLIME", K_GOBLIN: "GOBLIN", K_SKELETON: "SKELETON",
        K_GHOST: "GHOST", K_BAT: "BAT"}
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
ONLY = {a for a in ARGV if a in ("K", "P", "L")} or {"K", "P", "L"}
KIT = bool(S.get("KIT_DEBUG", 0))
DAGGER_SLOT, BOW_SLOT = 3, 4                    # bar_knight: sword, power, whirl, daggers, bow
SLOT_OF = {K_RAT: 1, K_SLIME: 2, K_GOBLIN: 3, K_BAT: 4, K_SKELETON: 5, K_GHOST: 6}


class B(game.T):
    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(str(b) for b in data)))

    def kinds(self):
        g = lambda f, k: self.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
        return {k: (g("KT_BW", k), g("KT_BH", k), bool(g("KT_FLAGS", k) & S["KF_FLYER"])) for k in range(9)}

    def wr(self):
        q = S["LOG_Q"]
        return (self.rb(q + S["LQ_RD"]) + self.rb("LOG_QN")) % S["LOG_SLOTS"]

    def lines(self, w0, w1):
        out = []
        n = (w1 - w0) % S["LOG_SLOTS"]
        for i in range(n):
            sl = (w0 + i) % S["LOG_SLOTS"]
            out.append(stream_text(self.z.read_memory(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"],
                                                      S["LOG_SLOT_LEN"])).rstrip("."))
        return out


def ov(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = B(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] b19 needs a DEBUG_KIT=0 build", flush=True)
        else:
            p.boot(K_KNIGHT)
            kt = p.kinds()
            if "K" in ONLY:
                kills(p, kt, check)
            if "P" in ONLY:
                pending_stack(p, kt, check)
            if "L" in ONLY:
                ladder(p, kt, check)
        print(f"b19: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


# ---------------------------------------------------------------- K: kill path
def kills(p, kt, check):
    def body_y(kind, cls):
        bw, bh, fly = kt[kind]
        if fly:
            return S["STOREY_ROWS"] + 1                 # cruise row 9s+1: in the hero's line
        return HY + kt[cls][1] - bh

    def scene(cls, kind, x, hp, seed):
        p.boot(cls)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8, MODE=0, ROOM=room, FLAGS=EF_ACTIVE | EF_PLAYER,
                  HP=200, MAXHP=200, REACT=0)
        sl = SLOT_OF[kind]
        y = body_y(kind, cls)
        p.set_ent(sl, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room,
                  FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, HP=hp, MAXHP=max(hp, 40), REACT=0, FLT=0, HIT=0)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.wb("DAGGERS", 9)
        p.wb("ARROWS", 20)
        p.wb("HAS_BOW", 1)
        if cls == K_WIZARD:                             # Spark rank 1 (abil_load picks the ab_rank row)
            p.wb("MP", 40)
            p.wb("MAXMP", 40)
            p.wmem(S["ARANK"], [1, 0])
            sym, b3 = CT.load()
            ab = sym["ab_rank"] - CT.BASE
        p.wmem(S["RNG_STATE"], [seed & 255, seed >> 8])
        p.wb("FX_DROP", 0)
        p.tick(3)
        return sl

    def act(how, per):
        if how == "melee":
            return p.turn("C", per_tick=per)
        p.select_slot({"dagger": DAGGER_SLOT, "bow": BOW_SLOT, "spark": 1}[how])
        return p.turn("FIRE", per_tick=per)

    def one(tag, cls, kind, how, lethal):
        bw_h = kt[cls][0]
        x = HX + bw_h + (0 if how == "melee" else 2)    # adjacent for melee, gap 2 for missiles
        for seed in range(101, 140):
            sl = scene(cls, kind, x, 1 if lethal else 40, seed * 197)
            w0 = p.wr()
            seen = dict(dead=False, bad=[], death_hp=False, death=False)
            run_ = {}                                   # cell -> consecutive FX-idle mismatching ticks

            def per(fr, e0):
                e = p.ent(sl)
                if e["REACT"] == RC_DEATH_RUN:
                    seen["death"] = True
                    if e["HP"] > 0:
                        seen["death_hp"] = True
                if e["FLAGS"] & EF_DYING:
                    seen["dead"] = True
                if seen["dead"] and (e["HP"] != 0 or (e["FLAGS"] & EF_ACTIVE and not e["FLAGS"] & EF_DYING)):
                    seen["bad"].append(("revived", e["HP"], e["FLAGS"]))
                if seen["dead"] and p.rb("FX_BUSY") == 0:
                    # the composed screen (bank 5; bank 7 trails it a tick): a
                    # cell off every drawn footprint that differs from ROOM_MAP
                    # for 3 FX-idle ticks in a row = a stale body / erase miss
                    mm = set(p.bg_mismatch_in(p.composed_frame()))
                    for c in list(run_):
                        if c not in mm:
                            del run_[c]
                    for c in mm:
                        run_[c] = run_.get(c, 0) + 1
                        if run_[c] == 3:
                            seen["bad"].append(("screen", c))

            if not act(how, per):
                check(f"{tag}: the action ran", False)
                return
            lines = p.lines(w0, p.wr())
            e = p.ent(sl)
            if lethal and not seen["dead"]:
                continue                                # missed / not killed: next seed
            if not lethal and e["HP"] == 40:
                continue                                # missed: next seed
            for _ in range(3):
                p.turn("WAIT", per_tick=per)
            e = p.ent(sl)
            if lethal:
                p.tick(2)
                settled = p.bg_mismatch()
                kl = [l for l in lines if l.startswith(TXT["you_kill"])]
                # a spell kill logs no line of its own (abil_spell7 has no impact
                # line; abil_ammo7 / melee: YOU KILL, from the target's HP then)
                want_kl = [] if how == "spark" else [TXT["you_kill"] + NAME[kind]]
                check(f"{tag}: kill — HP 0 for good, never alive again, no DEATH with HP > 0, slot freed, "
                      f"no stale cell, settled screen == map + live bodies; kill line {want_kl}",
                      not seen["bad"] and not seen["death_hp"] and seen["death"] and e["FLAGS"] == 0
                      and not settled and kl == want_kl and not any("HITS" in l for l in lines),
                      (seen, e["FLAGS"], settled[:4], lines))
            else:
                check(f"{tag}: non-lethal hit — no DEATH, alive, a HITS line",
                      not seen["death"] and not seen["dead"] and e["FLAGS"] & EF_ACTIVE and 0 < e["HP"] < 40
                      and any(l.endswith("HITS THE " + NAME[kind]) for l in lines), (seen, e, lines))
            return
        check(f"{tag}: no seed gave the hit", False)

    for kind in (K_GOBLIN, K_SKELETON):
        for how in ("dagger", "bow"):
            one(f"K1 {NAME[kind]} {how}", K_KNIGHT, kind, how, True)
            one(f"K2 {NAME[kind]} {how}", K_KNIGHT, kind, how, False)
    for kind in (K_RAT, K_SLIME, K_GHOST, K_BAT):
        one(f"K1 {NAME[kind]} dagger", K_KNIGHT, kind, "dagger", True)
    for kind in (K_GOBLIN, K_SKELETON):
        one(f"K1 {NAME[kind]} melee", K_KNIGHT, kind, "melee", True)
        one(f"K1 {NAME[kind]} spark", K_WIZARD, kind, "spark", True)


# ---------------------------------------------------- P: pending body stacking
def pending_stack(p, kt, check):
    """The B19 sequence: G2 PENDING (an arrival) overlapping the hero's box,
    G1 walks up to the hero, the hero steps off, then kills G1 with a dagger."""
    g1, g2 = 3, 1                                     # slot 1 (the Rat's) re-kinded as a 2nd Goblin
    gy = HY + kt[K_KNIGHT][1] - kt[K_GOBLIN][1]
    gw, gh = kt[K_GOBLIN][0], kt[K_GOBLIN][1]
    p.boot(K_KNIGHT)
    p.isolate()
    room = p.rb("CUR_ROOM")
    p.set_ent(0, X=6, Y=HY, PX=48, PY=HY * 8, MODE=0, HP=200, MAXHP=200)
    p.set_ent(g2, KIND=K_GOBLIN, X=8, Y=gy, PX=64, PY=gy * 8, MODE=0, ROOM=room,
              FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT | EF_PENDING, HP=20, MAXHP=20, REACT=0)
    p.set_ent(g1, KIND=K_GOBLIN, X=14, Y=gy, PX=112, PY=gy * 8, MODE=0, ROOM=room,
              FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, HP=1, MAXHP=20, REACT=0)
    p.wb("DAGGERS", 9)
    p.settle()
    stack = []

    def inv(tag):
        bs = {}
        for s in range(1, 16):
            e = p.ent(s)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room and not e["FLAGS"] & EF_DYING:
                bw, bh, _ = kt[e["KIND"]]
                bs[s] = ((e["X"], e["Y"], bw, bh), bool(e["FLAGS"] & EF_PENDING))
        for a, (ba, pa) in bs.items():
            for b, (bb, pb) in bs.items():
                if pa and not pb and ov(ba, bb):
                    stack.append((tag, a, ba, b, bb))

    for i in range(5):                                # G1 walks up to the hero
        p.turn("WAIT")
        inv(f"wait{i}")
    p.turn("H")                                       # (turn-around tap, then the step)
    inv("step")
    for i in range(2):
        p.turn("WAIT")
        inv(f"wait'{i}")
    # kill whatever stands nearest on the right with daggers (G1, HP 1)
    p.tap("L")                                        # face right: 0 turns
    p.tick()
    p.select_slot(DAGGER_SLOT)
    corpse, popped = None, []
    for i in range(8):
        e1 = p.ent(g1)
        if not e1["FLAGS"] & EF_ACTIVE:
            break
        box = (e1["X"], e1["Y"], gw, gh)

        def per(fr, e0, box=box):
            e = p.ent(g1)
            if e["FLAGS"] & EF_DYING:
                e2 = p.ent(g2)
                if e2["FLAGS"] & EF_ACTIVE and not e2["FLAGS"] & EF_PENDING and \
                        ov((e2["X"], e2["Y"], gw, gh), box) and box not in popped:
                    popped.append(box)

        p.turn("FIRE", per_tick=per)
        inv(f"throw{i}")
        if p.ent(g1)["FLAGS"] & EF_DYING or not p.ent(g1)["FLAGS"] & EF_ACTIVE:
            corpse = box
            for _ in range(3):
                p.turn("WAIT", per_tick=per)
                inv("after")
            break
    check("P1 the walker was killed by a dagger", corpse is not None, p.ent(g1))
    overlap_freeze(p, kt, check)
    check("P1 no PENDING body is ever stacked under a live monster", not stack, stack[:3])
    check("P1 nothing materialises on the corpse (no 'kill comes back')", not popped, popped)


def overlap_freeze(p, kt, check):
    """P2 (review): a Goblin already stacked on a PENDING Goblin (made before
    the rule, or by a squeeze / arrival) must walk off it — pend_hit ignores a
    pending body the mover already overlaps — and the hidden one then
    materialises; no freeze, and it never ends up on a new pending body."""
    g1, g2 = 3, 1
    gy = HY + kt[K_KNIGHT][1] - kt[K_GOBLIN][1]
    p.boot(K_KNIGHT)
    p.isolate()
    room = p.rb("CUR_ROOM")
    p.set_ent(0, X=4, Y=HY, PX=32, PY=HY * 8, MODE=0, HP=200, MAXHP=200)
    for sl, fl in ((g2, EF_PENDING), (g1, 0)):
        p.set_ent(sl, KIND=K_GOBLIN, X=14, Y=gy, PX=112, PY=gy * 8, MODE=0, ROOM=room,
                  FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT | fl, HP=20, MAXHP=20, REACT=0)
    p.settle()
    xs, popped = [], None
    for t in range(6):
        p.turn("WAIT")
        xs.append(p.ent(g1)["X"])
        if popped is None and not p.ent(g2)["FLAGS"] & EF_PENDING:
            popped = t
    check("P2 a walker stacked on a PENDING body walks off it (no freeze) and the hidden one materialises",
          xs[0] < 14 and popped is not None and popped <= 3, (xs, popped, p.ent(g2)))


# ---------------------------------------------------------------- L: ladders
WALKERS = ((1, K_RAT), (2, K_SLIME), (3, K_GOBLIN), (5, K_SKELETON))


def ladder(p, kt, check):
    def boxes():
        out = {}
        for s in range(16):
            e = p.ent(s)
            if e["FLAGS"] & (EF_ACTIVE | EF_PENDING | EF_DYING) != EF_ACTIVE or e["ROOM"] != 0:
                continue
            bw, bh, _ = kt[e["KIND"]]
            out[s] = (e["X"], e["Y"], bw, bh)
        return out

    def storey(e):
        bh = kt[e["KIND"]][1]
        return (e["Y"] + bh - 1) // S["STOREY_ROWS"]

    def run(tag, col, hero_s, mons, keys, rnd=None, allow_squeeze=False):
        p.boot(K_KNIGHT)
        p.isolate()
        p.place(0, col, stand_y(hero_s, 6))
        for slot, kind, x, s, left in mons:
            y = stand_y(s, kt[kind][1])
            p.set_ent(slot, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=0,
                      FLAGS=EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), HP=200, MAXHP=200, REACT=0)
        p.settle()
        over, moved = [], []

        def per(fr, e0):
            bs = boxes()
            if 0 in bs:
                over.extend((s, b, bs[0]) for s, b in bs.items() if s and ov(b, bs[0]))

        for t in range(len(keys)):
            k = keys[t]
            before = {m[0]: p.ent(m[0]) for m in mons}
            w0 = p.wr()
            if not p.turn(k, per_tick=per):
                p.turn("WAIT", per_tick=per)
            sq = any("SQUEEZE" in l for l in p.lines(w0, p.wr()))
            for m in mons:
                a, b = before[m[0]], p.ent(m[0])
                if storey(a) != storey(b) and a["Y"] == stand_y(storey(a), kt[a["KIND"]][1]) \
                        and b["Y"] == stand_y(storey(b), kt[b["KIND"]][1]) and not (allow_squeeze and sq):
                    moved.append((t, k, m[0], (a["X"], a["Y"]), (b["X"], b["Y"]), sq))
        return over, moved

    # L0: the fuzz-found B18 sequence (deterministic): the hero mid-ladder on
    # {5,1} at y 7 turns to climb DOWN; a Goblin stands on the shaft col at
    # the foot facing right, a Skeleton left of it (cols 2..4). The 1st J is
    # blocked (a wait: the Goblin yields 5 -> 6, still on the 3-col path);
    # the 2nd J used to squeeze it onto storey 0. Now it keeps yielding.
    p.boot(K_KNIGHT)
    p.isolate()
    p.place(0, 5, 7)
    p.set_ent(0, AIDIR=0xFF)
    for slot, kind, x in ((3, K_GOBLIN, 5), (5, K_SKELETON, 2)):
        y = stand_y(1, kt[kind][1])
        p.set_ent(slot, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=0, FLAGS=EF_ACTIVE | EF_HOSTILE,
                  HP=200, MAXHP=200, REACT=0)
    p.settle()
    path = []
    for _ in range(9):
        if p.ent(0)["Y"] == stand_y(1, 6):
            break
        if not p.turn("J"):
            p.turn("WAIT")
        g = p.ent(3)
        path.append((p.ent(0)["Y"], g["X"], g["Y"]))
    check("L0 hero descends past a yielding Goblin (no squeeze): it never leaves storey 1, hero at the foot",
          all(gy == stand_y(1, kt[K_GOBLIN][1]) for _, _, gy in path) and p.ent(0)["Y"] == stand_y(1, 6), path)

    # L3 (review): several blockers on one climb path, each yielding in turn
    # (A / B alternating as CLIMB_BLK_ID): the count runs on across blockers,
    # so the hero passes within the yield turns + CLIMB_SQZ_N blocks + 1.
    p.boot(K_KNIGHT)
    p.isolate()
    p.place(0, 5, 7)
    p.set_ent(0, AIDIR=0x01)
    for slot, kind, x, y in ((4, K_BAT, 5, 10), (1, K_RAT, 5, stand_y(1, kt[K_RAT][1])),
                             (3, K_GOBLIN, 9, stand_y(1, kt[K_GOBLIN][1]))):
        p.set_ent(slot, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=0, FLAGS=EF_ACTIVE | EF_HOSTILE,
                  HP=200, MAXHP=200, REACT=0)
    p.settle()
    ids, n = [], 0
    bound = 4 + S["CLIMB_SQZ_N"] * 2 + 2
    while p.ent(0)["Y"] != stand_y(1, 6) and n < bound + 4:
        if not p.turn("J"):
            p.turn("WAIT")
        n += 1
        ids.append((p.rb("CLIMB_BLK_ID"), p.rb("CLIMB_BLK_N"), p.ent(0)["Y"]))
    check(f"L3 bat + rat on the path (a goblin boxing the rat): hero at the foot within {bound} turns",
          p.ent(0)["Y"] == stand_y(1, 6) and n <= bound, ids)

    # L1: one walker, room to yield, hero descends / climbs straight through
    bad1 = []
    for col in (5, 23):
        for kind_slot, kind in WALKERS:
            for dx in (-1, 0, 1):
                for hero_s, key in ((0, "J"), (1, "K")):
                    ms = 1 - hero_s                       # the walker on the other storey
                    x = col + dx
                    left = dx >= 0                        # facing the shaft col's far side
                    over, moved = run("L1", col, hero_s, [(kind_slot, kind, x, ms, left)], [key] * 12)
                    if over or moved:
                        bad1.append((col, NAME[kind], x, key, left, over[:1], moved[:1]))
    check("L1 one walker beside a shaft: the climbing hero never overlaps it, it never changes storey",
          not bad1, bad1[:4])

    # L2: fuzz (deterministic), several walkers, random climbs / walks
    rnd = random.Random(19)
    over_all, moved_all = [], []
    for it in range(int(os.environ.get("FUZZ_B19", "24"))):
        col = rnd.choice((5, 23))
        hs = rnd.randint(0, 1)
        used = [(col, stand_y(hs, 6), 3, 6)]
        mons = []
        for slot, kind in rnd.sample(WALKERS, rnd.randint(1, 4)):
            bw, bh, _ = kt[kind]
            for _ in range(20):
                s = rnd.randint(0, 1)
                x = max(1, min(30 - bw, col + rnd.randint(-5, 5)))
                b = (x, stand_y(s, bh), bw, bh)
                if not any(ov(b, u) for u in used):
                    used.append(b)
                    mons.append((slot, kind, x, s, rnd.random() < 0.5))
                    break
        keys = [rnd.choice(("J", "K") * 4 + ("H", "L", "WAIT")) for _ in range(14)]
        over, moved = run("L2", col, hs, mons, keys, allow_squeeze=True)
        over_all += [(it,) + o for o in over]
        moved_all += [(it,) + m for m in moved]
    check("L2 fuzz: the hero never overlaps a live body", not over_all, over_all[:3])
    check("L2 fuzz: no walker changes storey except by a logged squeeze", not moved_all, moved_all[:3])


if __name__ == "__main__":
    sys.exit(main())
