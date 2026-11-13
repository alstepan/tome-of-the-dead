#!/usr/bin/env python3
"""B19c (user, Fuse, after the B19 fix): the hero throws daggers at a monster
until it dies; it plays its death animation, then stands alive and attacks.
Release build (DEBUG_KIT=0).

Root cause found by F: two monsters of one kind follow the hero through a
door; place_follower puts BOTH PENDING on the same entry box, one
materialises, the other stays hidden under it (B19b). Killing the visible
one made its box "free" (box_free skips DYING bodies) and materialise popped
the hidden one on the corpse during the death animation: same kind, same
place, alive. Fix: materialise also waits for a DYING body in the box
(turn3.asm corpse_hit; prototype §3.7 "free of all non-pending entities").

Every scenario runs a per-tick Watch over the whole entity table:
  - a slot seen DYING keeps HP 0 + DYING until it is freed (flags 0), and is
    freed within DEATH_MAX ticks (no stuck corpse);
  - no body leaves PENDING over a corpse that is still DYING ("pop");
  - at the kill no live body stands under the corpse; no two live walkers
    overlap.
  F  (default) 2 Goblins / 2 Skeletons follow the hero A -> B, he walks n
     steps and kills both at the door: daggers, then melee (not dagger
     specific: daggers just make the door kill the common case).
  A  (default) the plain loop: a full-HP monster approaching / attacking, one
     dagger a turn until it dies (Goblin / Skeleton; ALL=1: every kind, more).
  R  (default) the same with FIRE mashed every 2nd tick (queued throws).
  P  (opt-in) PROTO fuzz: every monster re-kinded Goblin / Skeleton, random
     walks / climbs / throws (B19C_SEEDS, B19C_TURNS).
  G  (opt-in) generated D1 fuzz (LP: lazy population, followers, records),
     fresh rooms roll Goblins / Skeletons; exit / ladder hops.
Run: ZRCP_PORT=<port> python3 tests/b19c.py [F] [A] [R] [P] [G]
"""
import sys
from pathlib import Path

ARGV = sys.argv[1:]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_RAT, K_SLIME, K_GOBLIN,  # noqa: E402
                      K_SKELETON, K_GHOST, K_BAT, stand_y, E as EO, STRIDE)

EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, 8, 16, 64
NAME = {K_RAT: "RAT", K_SLIME: "SLIME", K_GOBLIN: "GOBLIN", K_SKELETON: "SKELETON",
        K_GHOST: "GHOST", K_BAT: "BAT"}
SLOT_OF = {K_RAT: 1, K_SLIME: 2, K_GOBLIN: 3, K_BAT: 4, K_SKELETON: 5, K_GHOST: 6}
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
DAGGER_SLOT = 3
DEATH_MAX = 80
VERB = bool(__import__("os").environ.get("B19C_VERBOSE"))
ONLY = {a for a in ARGV if a in ("A", "G", "P", "R", "F")} or {"A", "R", "F"}
ALL = bool(__import__("os").environ.get("ALL"))


def ents(p):
    b = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
    return [{k: b[s * STRIDE + o] for k, o in EO.items()} for s in range(16)]


def ov(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def plain(p, kt, check, kinds, dists, seeds):
    """A: one dagger a turn at a full-HP monster until it dies."""
    fails = []
    for kind in kinds:
        for d in dists:
            for seed in seeds:
                sl = scene(p, kt, kind, d, seed)
                w = Watch(p, kt)
                throws = 0
                for t in range(40):
                    e = p.ent(sl)
                    if not e["FLAGS"]:
                        break
                    if e["FLAGS"] & EF_DYING:
                        p.turn("WAIT", per_tick=w)
                        continue
                    h = p.ent(0)
                    want_left = e["X"] < h["X"]
                    if bool(h["FLAGS"] & EF_LEFT) != want_left:
                        p.tap("H" if want_left else "L")
                        p.tick()
                    if p.turn("FIRE", per_tick=w):
                        throws += 1
                    else:
                        p.turn("WAIT", per_tick=w)
                for _ in range(4):
                    p.turn("WAIT", per_tick=w)
                tag = f"A {NAME[kind]} d{d} seed{seed}"
                if w.bad or not w.kills or p.ent(sl)["FLAGS"]:
                    fails.append((tag, throws, w.kills, w.bad[:3]))
                    print(f"[detail] {tag}: throws {throws} kills {w.kills} bad {w.bad[:3]} "
                          f"slot {p.ent(sl)} daggers {p.rb('DAGGERS')}", flush=True)
    check(f"A plain throw loop ({len(kinds)} kinds x {len(dists)} dists x {len(seeds)} seeds): "
          "killed, freed, never revived", not fails, fails[:3])


class Watch:
    """Generated-level watch: per tick, every slot (kills / revivals) + live
    same-room bodies overlapping each other or a corpse box."""
    def __init__(self, p, kt):
        self.p, self.kt = p, kt
        self.t = 0
        self.dying = {}            # slot -> (t0, box, kind, room)
        self.freed = {}            # slot -> (t, box, kind, room)
        self.bad = []
        self.kills = 0
        self.prev = None

    def box(self, e):
        bw, bh, _ = self.kt[e["KIND"]]
        return (e["X"], e["Y"], bw, bh)

    def __call__(self, *_):
        self.t += 1
        p = self.p
        es = ents(p)
        room = p.rb("CUR_ROOM")
        gs = p.rb("GAME_STATE")
        live = [s for s in range(1, 16) if es[s]["FLAGS"] & (EF_ACTIVE | EF_PENDING | EF_DYING) == EF_ACTIVE
                and es[s]["ROOM"] == room]
        for s in range(1, 16):
            e = es[s]
            f = e["FLAGS"]
            if s in self.dying:
                t0, bx, k, r = self.dying[s]
                if f == 0:
                    del self.dying[s]
                    self.freed[s] = (self.t, bx, k, r)
                elif not f & EF_DYING or e["HP"]:
                    self.bad.append(("revived-in-slot", s, self.t, f, e["HP"], k, e["KIND"]))
                    del self.dying[s]
                elif self.t - t0 > DEATH_MAX and gs == 2:
                    self.bad.append(("stuck-corpse", s, self.t, f, e["MODE"], e["REACT"], e["ROOM"], room))
                    del self.dying[s]
            elif f & EF_ACTIVE and f & EF_DYING and e["HP"] == 0:
                self.dying[s] = (self.t, self.box(e), e["KIND"], e["ROOM"])
                self.kills += 1
                for o in live:          # a live body under the fresh corpse
                    if o != s and ov(self.box(es[o]), self.box(e)):
                        self.bad.append(("live-under-corpse", s, o, self.t, e["KIND"], es[o]["KIND"],
                                         self.box(e), self.box(es[o]), es[o]["FLAGS"]))
        # a body leaving PENDING over a corpse still DYING (drawn): "the kill
        # comes back". (After the slot is freed a follower may walk in there:
        # prototype §3.7, a legal arrival — not checked.)
        for s, (t0, bx, k, r) in list(self.dying.items()):
            if r != room:
                continue
            for o in live:
                if es[o]["KIND"] == k and ov(self.box(es[o]), bx) and o not in [b[2] for b in self.bad
                                                                               if b[0] == "pop"]:
                    prevf = self.prev[o]["FLAGS"] if self.prev else 0
                    prevr = self.prev[o]["ROOM"] if self.prev else 0
                    if not (prevf & EF_ACTIVE and not prevf & EF_PENDING and prevr == room):
                        self.bad.append(("pop", s, o, self.t, k, bx, self.box(es[o]), prevf, f"slot{o}"))
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                if ov(self.box(es[a]), self.box(es[b])) and not (self.kt[es[a]["KIND"]][2]
                                                                 or self.kt[es[b]["KIND"]][2]):
                    key = ("overlap", a, b)
                    if not any(x[:3] == key for x in self.bad):
                        self.bad.append(key + (self.t, es[a]["KIND"], es[b]["KIND"], self.box(es[a]),
                                               self.box(es[b])))
        self.prev = es


def storey(kt, e):
    return (e["Y"] + kt[e["KIND"]][1] - 1) // S["STOREY_ROWS"]


def hop(p, kt, rnd, w):
    """Leave the room by a legal exit: stand at an edge col of a storey and
    walk out (tries the 4 horizontal exits in random order)."""
    room = p.rb("CUR_ROOM")
    bw = kt[K_KNIGHT][0]
    rd = p.z.read_memory(S["ROOM_DESC"] + 16 * room, 16)
    ex = rd[1]
    opts = []
    if ex & 1:
        opts.append(("H", 1 if ex & 0x10 else 0, 1))
    if ex & 2:
        opts.append(("L", 1 if ex & 0x20 else 0, 31 - bw))
    if ex & 4 and rd[2]:
        opts.append(("K", 0, rd[2]))
    if ex & 8 and rd[3]:
        opts.append(("J", 1, rd[3]))
    rnd.shuffle(opts)
    for key, s_, x in opts:
        y = stand_y(s_, kt[K_KNIGHT][1])
        f = p.ent(0)["FLAGS"]
        f = (f | EF_LEFT) if key == "H" else (f & ~EF_LEFT)
        p.set_ent(0, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, FLAGS=f)
        p.tick(2)
        for _ in range(12):
            if not p.turn(key, per_tick=w):
                break
            if p.rb("CUR_ROOM") != room:
                return True
    return False


def gen_fuzz(p, kt, check, seeds, turns, proto=0, tag="G"):
    import random
    allbad = []
    for seed in seeds:
        rnd = random.Random(seed)
        p.proto_start = proto
        p.load()
        p.wait_state(2 + 3)                         # GS_SELECT
        p.wb("INPUT_SRC", 1)
        p.wb("ANIM_FREEZE", 0)
        p.wb("INPUT_REPEAT", 1)
        p.wb("seed_fixed", 1)
        p.wmem("seed_value", [seed & 255, (seed >> 8) & 255])
        p.menu_start(K_KNIGHT)
        p.wmem(S["RNG_STATE"], [seed & 255, (seed >> 8) | 1])
        if proto:                                  # every PROTO monster -> Goblin / Skeleton (the
            for s_ in range(1, 16):                # reported kinds), full HP
                e = p.ent(s_)
                if e["FLAGS"] & EF_ACTIVE and not kt[e["KIND"]][2]:
                    k = rnd.choice((K_GOBLIN, K_SKELETON))
                    y = e["Y"] + kt[e["KIND"]][1] - kt[k][1]
                    p.set_ent(s_, KIND=k, Y=y, PY=y * 8, HP=kt["hp"][k], MAXHP=kt["hp"][k])
            p.tick(2)
        else:                                      # fresh rooms roll Goblins / Skeletons
            p.wmem(S["LP_KINDS"], [K_GOBLIN, K_SKELETON, K_GOBLIN, K_SKELETON] * 2)    # 8 slots (NEW-MON3 T3)
        w = Watch(p, kt)
        throws = 0
        sel = None
        last_room, dirk, stuck = None, "L", 0
        rooms = set()
        quiet = other = 0
        for t in range(turns):
            if p.rb("GAME_STATE") != 2:
                break
            p.set_ent(0, HP=250, MAXHP=250)
            p.wb("DAGGERS", 20)
            h = p.ent(0)
            room = p.rb("CUR_ROOM")
            rooms.add(room)
            hs = storey(kt, h)
            mons = [(s, e) for s, e in enumerate(ents(p)) if s and e["FLAGS"] & (EF_ACTIVE | EF_PENDING | EF_DYING)
                    == EF_ACTIVE and e["ROOM"] == room and storey(kt, e) == hs]
            ok = False
            allm = [1 for s_, e in enumerate(ents(p)) if s_ and e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room]
            quiet = 0 if allm else quiet + 1
            other = 0 if mons or not allm else other + 1
            if other > 6 and not proto:              # monsters only on the other storey: ladder
                other = 0
                lad = p.z.read_memory(S["ROOM_DESC"] + 16 * room + 6, 1)[0]
                y = stand_y(hs, kt[K_KNIGHT][1])
                p.set_ent(0, X=lad, Y=y, PX=lad * 8, PY=y * 8, MODE=0)
                p.tick(2)
                for _ in range(12):
                    if not p.turn("J" if hs == 0 else "K", per_tick=w) or \
                            storey(kt, p.ent(0)) != hs and p.ent(0)["Y"] == stand_y(1 - hs, kt[K_KNIGHT][1]):
                        break
                continue
            if quiet > 12 and not proto:
                quiet = 0
                r0 = p.rb("CUR_ROOM")
                okh = hop(p, kt, rnd, w)
                if VERB:
                    print(f"  hop {r0} -> {p.rb('CUR_ROOM')} {okh} exits "
                          f"{list(p.z.read_memory(S['ROOM_DESC'] + 16 * r0, 4))} "
                          f"rec {list(p.z.read_memory(S['LP_REC'] + 9 * p.rb('CUR_ROOM'), 9))}", flush=True)
                continue
            if mons and rnd.random() < 0.85:
                s, e = min(mons, key=lambda se: abs(se[1]["X"] - h["X"]))
                left = e["X"] < h["X"]
                if bool(h["FLAGS"] & EF_LEFT) != left:
                    p.tap("H" if left else "L")
                    p.tick()
                if sel != DAGGER_SLOT:
                    p.select_slot(DAGGER_SLOT)
                    sel = DAGGER_SLOT
                ok = p.turn("FIRE", per_tick=w)
                throws += ok
            if not ok:
                if room != last_room or rnd.random() < 0.04:
                    last_room = room
                    dirk = rnd.choice(("L", "H"))
                k = dirk if rnd.random() < 0.8 else rnd.choice(("J", "K", "J", "K", "WAIT"))
                x0 = h["X"]
                ok = p.turn(k, per_tick=w)
                if not ok:
                    p.turn("WAIT", per_tick=w)
                if k == dirk and p.ent(0)["X"] == x0 and p.rb("CUR_ROOM") == room:
                    stuck += 1
                    if stuck > 2:
                        dirk = "H" if dirk == "L" else "L"
                        stuck = 0
        print(f"[gen] seed {seed:#06x}: turns {t + 1} throws {throws} kills {w.kills} bad {len(w.bad)} "
              f"depth {p.rb('LVL_DEPTH')} rooms {sorted(rooms)}", flush=True)
        for b in w.bad[:6]:
            print(f"   {b}", flush=True)
        allbad += [(seed,) + b for b in w.bad]
    check(f"{tag} throw fuzz proto={proto} ({len(seeds)} seeds x {turns} turns): no revival / pop / stacking",
          not allbad, allbad[:4])


def scene(p, kt, kind, d, seed, daggers=30, repeat=0, freeze=1):
    p.boot(K_KNIGHT, repeat=repeat, freeze=freeze)
    room = p.rb("CUR_ROOM")
    for sl in range(1, 16):
        e = p.ent(sl)
        if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
            p.set_ent(sl, ROOM=NOWHERE)
    p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8, MODE=0, ROOM=room,
              FLAGS=EF_ACTIVE | EF_PLAYER, HP=250, MAXHP=250, REACT=0)
    bw, bh, fly = kt[kind]
    y = S["STOREY_ROWS"] + 1 if fly else HY + kt[K_KNIGHT][1] - bh
    x = HX + kt[K_KNIGHT][0] + d
    sl = SLOT_OF[kind]
    hp = kt["hp"][kind]
    p.set_ent(sl, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room,
              FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, HP=hp, MAXHP=hp, REACT=0, FLT=0, HIT=0)
    p.wmem(S["ST_FLAGS"], [0] * 16)
    p.wmem(S["ST_T1"], [0] * 16)
    p.wb("DAGGERS", daggers)
    p.wmem(S["RNG_STATE"], [seed & 255, (seed >> 8) | 1])
    p.tick(3)
    p.select_slot(DAGGER_SLOT)
    return sl


def rapid(p, kt, check, kinds, dists, seeds, period=2, repeat=1, maxt=500):
    """The user's loop as played: FIRE mashed (pressed every `period` ticks)
    through every animation, so a throw starts on the first INPUT tick it
    can; the monster approaches and attacks. Per-tick Watch."""
    fails = []
    for kind in kinds:
        for d in dists:
            for seed in seeds:
                sl = scene(p, kt, kind, d, seed, repeat=repeat, freeze=0)
                w = Watch(p, kt)
                t, gone = 0, None
                while t < maxt:
                    if t % period == 0:
                        p.hold("FIRE")
                    else:
                        p.release()
                    p.tick()
                    w()
                    t += 1
                    if gone is None and not p.ent(sl)["FLAGS"]:
                        gone = t
                    if gone is not None and t - gone > 120:
                        break
                p.release()
                tag = f"R {NAME[kind]} d{d} seed{seed} period{period}"
                if w.bad or not w.kills:
                    fails.append((tag, w.kills, w.bad[:3]))
                    print(f"[detail] {tag}: kills {w.kills} bad {w.bad[:4]} daggers {p.rb('DAGGERS')} "
                          f"slot {p.ent(sl)}", flush=True)
                else:
                    print(f"[ok] {tag}: freed at tick {gone}, daggers left {p.rb('DAGGERS')}", flush=True)
    check(f"R mashed-FIRE throw loop period {period} ({len(kinds)} kinds x {len(dists)} dists x "
          f"{len(seeds)} seeds): killed, freed, never revived", not fails, fails[:3])


def followers(p, kt, check, kinds=(K_GOBLIN, K_SKELETON), steps=(1, 2, 3, 4, 6), seeds=(1, 2, 3), how="dagger"):
    """F: two monsters of one kind follow the hero out of room A (right exit,
    storey 1) into room B; both are placed PENDING on the same entry box (x 1)
    — one materialises, the other waits hidden under it. The hero walks
    `steps` right, turns and throws daggers at the door until both are dead
    (how="melee": bump-attacks them as they come)."""
    fails = []
    for kind in kinds:
        bw, bh, _ = kt[kind]
        for n in steps:
            for seed in seeds:
                p.boot(K_KNIGHT)
                p.isolate()
                room = p.rb("CUR_ROOM")
                for s_ in range(1, 16):                 # room B empty too (the caps)
                    if p.ent(s_)["ROOM"] == room + 1:
                        p.set_ent(s_, ROOM=NOWHERE)
                hx = 31 - kt[K_KNIGHT][0]               # one step from the exit: both in FOLLOW_GAP
                p.set_ent(0, X=hx, Y=HY, PX=hx * 8, PY=HY * 8, MODE=0, HP=250, MAXHP=250,
                          FLAGS=EF_ACTIVE | EF_PLAYER)
                y = HY + kt[K_KNIGHT][1] - bh
                for sl, x in ((3, hx - bw), (5, hx - 2 * bw)):
                    p.set_ent(sl, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=room,
                              FLAGS=EF_ACTIVE | EF_HOSTILE, HP=kt["hp"][kind], MAXHP=kt["hp"][kind],
                              REACT=0, FLT=0, HIT=0)
                p.wmem(S["ST_FLAGS"], [0] * 16)
                p.wb("DAGGERS", 30)
                p.wmem(S["RNG_STATE"], [seed & 255, (seed >> 8) | 1])
                p.settle()
                w = Watch(p, kt)
                for _ in range(4):
                    if p.rb("CUR_ROOM") != room:
                        break
                    p.turn("L", per_tick=w)
                fol = [s for s in (3, 5) if p.ent(s)["ROOM"] == p.rb("CUR_ROOM")]
                for _ in range(n):
                    p.turn("L", per_tick=w)
                if how == "dagger":
                    p.select_slot(DAGGER_SLOT)
                kills_seen = 0
                for _ in range(30):
                    alive = [s for s in (3, 5) if p.ent(s)["FLAGS"] & EF_ACTIVE and
                             not p.ent(s)["FLAGS"] & EF_DYING and p.ent(s)["ROOM"] == p.rb("CUR_ROOM")]
                    if not alive:
                        break
                    h = p.ent(0)
                    e = p.ent(alive[0])
                    if e["FLAGS"] & EF_PENDING:
                        p.turn("WAIT", per_tick=w)
                        continue
                    left = e["X"] < h["X"]
                    if bool(h["FLAGS"] & EF_LEFT) != left:
                        p.tap("H" if left else "L")
                        p.tick()
                    if how == "melee":
                        gap = (h["X"] - e["X"] - bw) if left else (e["X"] - h["X"] - kt[K_KNIGHT][0])
                        ok = gap == 0 and p.turn("C", per_tick=w)
                    else:
                        ok = p.turn("FIRE", per_tick=w)
                    if not ok:
                        p.turn("WAIT", per_tick=w)
                for _ in range(3):
                    p.turn("WAIT", per_tick=w)
                tag = f"F {how} {NAME[kind]} steps{n} seed{seed}"
                if w.bad or VERB:
                    print(f"[{'ok' if not w.bad else 'BAD'}] {tag}: followers {fol} kills {w.kills} "
                          f"bad {w.bad[:3]}", flush=True)
                if len(fol) != 2:                       # else the run tested nothing
                    fails.append((tag, f"followers did not both arrive: {fol}"))
                if w.bad:
                    fails.append((tag, w.bad[:3]))
    total = len(kinds) * len(steps) * len(seeds)
    check(f"F {how}: two same-kind followers through a door, killed at the door ({total} runs): "
          "nothing materialises on a corpse, no revival", not fails, fails[:3])


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)

        if S.get("KIT_DEBUG", 0):
            print("[skip] b19c needs a DEBUG_KIT=0 build", flush=True)
        else:
            p.boot(K_KNIGHT)
            g = lambda f, k: p.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
            kt = {k: (g("KT_BW", k), g("KT_BH", k), bool(g("KT_FLAGS", k) & S["KF_FLYER"])) for k in range(9)}
            kt["hp"] = {k: g("KT_HP", k) for k in range(9)}
            every = (K_GOBLIN, K_SKELETON, K_RAT, K_SLIME, K_GHOST, K_BAT)
            if "F" in ONLY:
                followers(p, kt, check)
                followers(p, kt, check, steps=(3, 4), seeds=(1, 2), how="melee")
            if "A" in ONLY:
                plain(p, kt, check, every if ALL else (K_GOBLIN, K_SKELETON),
                      (3, 8, 14) if ALL else (3, 8), (1, 2, 3) if ALL else (1,))
            if "R" in ONLY:
                for per in ((2, 3) if ALL else (2,)):
                    rapid(p, kt, check, every if ALL else (K_GOBLIN, K_SKELETON),
                          (2, 8), (1, 2) if ALL else (1,), period=per)
            if "P" in ONLY:
                import os
                n = int(os.environ.get("B19C_SEEDS", "4"))
                gen_fuzz(p, kt, check, [0x2345 + 0x3B1 * i for i in range(n)],
                         int(os.environ.get("B19C_TURNS", "150")), proto=1, tag="P")
            if "G" in ONLY:
                import os
                n = int(os.environ.get("B19C_SEEDS", "4"))
                gen_fuzz(p, kt, check, [0x1234 + 0x3B1 * i for i in range(n)],
                         int(os.environ.get("B19C_TURNS", "150")))
        print(f"b19c: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
