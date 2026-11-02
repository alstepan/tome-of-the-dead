#!/usr/bin/env python3
"""MONSTER-FALL storey fuzz (user playtest 2026-11-02: monsters, not only Rats, drop to the other
storey when blocked near a ladder; earlier fixes B16 59f3830, B18 / D-AI1a 17c0875).

Seeded generated games (the real level_descend, so the level's kinds are pooled), the room the
hero starts in; every monster of it cleared, then 1-4 bodies of the level's kinds (base and tier
rows, walkers, climbers, flyers) put near a ladder shaft {c, 1} (standing on either storey, a
climber sometimes mid-ladder, a flyer anywhere in its band), sometimes anywhere in the room
(doors, pits, wide pits, blocks); some get FEAR / CONFUSED. The hero stands at a shaft end or
mid-ladder and plays a random mix weighted to climbing (UP / DOWN; a blocked climb is a wait,
the 2nd block a squeeze), WAIT and walks. After every turn, for every monster of the room:

  F1  a FLYER never changes storey (storey_ref, its band) — B16;
  F2  a NON-FLYER changes its y only on a ladder: a KF_CLIMBER whose x is an internal shaft col
      (RD_LAD1 / RD_LAD2) before and after (a climb step, a yield along the ladder, or the
      squeeze moving it to the hero's foot cell on the same shaft) — no pit fall exists for a
      monster (game.md §2.5: walkers never step onto a fall-range x);
  F3  a non-flyer that is not standing is on a shaft col (never mid-air);
  F4  no live (not PENDING, not DYING) monster overlaps another live body (the hero included);
  F5  no live monster's box holds a TF_SOLID cell (a wall, a block, a closed plank).
The run only ends at a level change, a room change or the hero's death (HP kept high).

Evidence (--seeds 64): main fa58d38 9 violations, all F2 from the B14 squeeze (lowram.asm climb_blocked)
moving a wall-wedged body of the OTHER storey to the hero's foot cell (Orc, Berserker, Archer x2, Sniper,
Necro, Skeleton, Spider, Death Knight); MONSTER-FALL: 0 in 11,092 turns. The defaults (32 seeds) hold 6 of them.
Build with -DDEBUG_KIT=0.  Usage: ZRCP_PORT=n [WZ_BUILD_DIR=d] python3 tests/storey_fuzz.py
  [--seeds N] [--turns T] [--sub K] [--seed0 S] [--quiet]
Exit 1 on any violation; prints one line per violation (seed / depth / room / turn / slot)."""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, storey_of, is_standing  # noqa: E402
from lp import T as Proto, w16  # noqa: E402


def arg(name, d):
    return int(sys.argv[sys.argv.index(name) + 1], 0) if name in sys.argv else d


NSEEDS, NTURNS, NSUB, SEED0 = arg("--seeds", 32), arg("--turns", 30), arg("--sub", 6), arg("--seed0", 0x5F00)
QUIET = "--quiet" in sys.argv
TF_SOLID, TF_LADDER, TF_FLOOR, TF_HOLE = S["TF_SOLID"], S["TF_LADDER"], S["TF_FLOOR"], S["TF_HOLE"]
EF_ACTIVE, EF_HOSTILE, EF_DYING, EF_PENDING, EF_LEFT = 1, 4, S["EF_DYING"], S["EF_PENDING"], S["EF_LEFT"]
KF_FLYER, KF_CLIMBER = S["KF_FLYER"], S["KF_CLIMBER"]
KT = S["kind_tab"]
ROWS = S["PLAY_ROWS"]
# game.md §9.4 per-depth kinds (+ the tier rows of those kinds, which share their frames, + the boss)
POOL = {1: "RAT BAT SLIME GOBLIN GIANT_RAT SCREECH SLINGER",
        2: "GOBLIN SPIDER BAT RAT BLACK_WIDOW SLINGER RABBIT_RAT",
        3: "SKELETON VAMPIRE GHOST BAT SKEL_GUARD POLTERGEIST",
        4: "ORC RAT SPIDER ARCHER OGRE ORC_BERSERK SNIPER",
        5: "MUMMY SKELETON ARCHER SPIDER SKEL_KNIGHT SNIPER BLACK_WIDOW",
        6: "VAMPIRE GHOST NECRO ORC BONE_CALLER ORC_BOUNCER",
        7: "ORC NECRO GHOST DKNIGHT ORC_BERSERK BONE_CALLER",
        8: "NECRO SKELETON GHOST VAMPIRE SKEL_KNIGHT"}
POOL = {d: [k for k in v.split() if "K_" + k in S] for d, v in POOL.items()}
viol = []
counts = {}


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * ROWS)
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < ROWS else TF_SOLID


def kt(p, field, k):
    return p.rb(KT + S[field] + k)


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def standable(f, s, x, w, h):
    y = stand_y(s, h)
    if x < 1 or x + w > 31:
        return False
    if not any(f(c, y + h) & (TF_FLOOR | TF_LADDER) and not f(c, y + h) & TF_HOLE for c in range(x, x + w)):
        return False
    return all(not f(c, r) & TF_SOLID for c in range(x, x + w) for r in range(y, y + h))


def free_of(boxes, b):
    return not any(overlap(b, o) for o in boxes)


def note(kind, msg):
    counts[kind] = counts.get(kind, 0) + 1
    viol.append(msg)
    print("[VIOL] " + msg, flush=True)


with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    GL.Proto.snd_mode = 2
    rng = random.Random(SEED0)
    nruns = nturns = 0
    for si in range(NSEEDS):
        depth = 1 + si % 8
        hero = (si // 8) % 2
        seed = (SEED0 + 0x137 * si) & 0xFFFF
        lad = None
        for attempt in range(6):
            p.proto_start = 0
            p.boot(hero=hero, freeze=0)
            p.wmem(S["MASTER_SEED"], w16((seed + 0x100 * attempt) & 0xFFFF))
            pc0 = p.pc()
            ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            if not ok or p.rb("LVL_DEPTH") != depth:
                continue
            p.release(); p.settle(4)
            room = p.rb("CUR_ROOM")
            rd = p.z.read_memory(S["ROOM_DESC"] + room * 16, 16)
            lad = [c for c in (rd[S["RD_LAD1"]], rd[S["RD_LAD2"]]) if c]
            if lad:
                seed = (seed + 0x100 * attempt) & 0xFFFF
                break
        if not lad:
            print(f"[SKIP] seed {seed:#06x} D{depth}: no room with an internal ladder", flush=True)
            continue
        f = room_cells(p)
        exits = [c for c in (rd[S["RD_UPCOL"]], rd[S["RD_DNCOL"]], rd[S["RD_ARRCOL"]], rd[S["RD_EXITCOL"]]) if c]
        kinds = [S["K_" + k] for k in POOL[depth]]
        info = {k: (kt(p, "KT_BW", k), kt(p, "KT_BH", k), kt(p, "KT_FLAGS", k)) for k in kinds + [S["K_VBAT"]]}
        snap = None
        for sub in range(NSUB):
            # --- the setup: hero + bodies -------------------------------------------------------
            c = rng.choice(lad)
            hs = rng.randrange(2)
            mode = rng.random()
            if mode < 0.35:                                  # mid-ladder (rows 9s.. of {c,1}: y 3..10)
                hy, hx = rng.randrange(3, 11), c
                hdir = rng.choice((1, 0xFF))
            elif mode < 0.8:
                hy, hx = stand_y(hs, 6), c
                hdir = 1 if hs == 0 else 0xFF
            else:
                hx = next((x for x in rng.sample(range(2, 28), 26) if standable(f, hs, x, 3, 6)), c)
                hy, hdir = stand_y(hs, 6), 1
            for sl in range(1, S["P_MAX_ENT"]):
                p.set_ent(sl, FLAGS=0)
            boxes = [(hx, hy, 3, 6)]
            n = rng.choice((1, 2, 2, 3, 3, 4))
            placed = []
            for i in range(n):
                k = rng.choice(kinds)
                w, hh, fl = info[k]
                for _ in range(60):
                    near = rng.random() < 0.75
                    x = c + rng.randrange(-w - 3, 6) if near else rng.randrange(1, 31 - w)
                    if fl & KF_FLYER:
                        s = rng.randrange(2)
                        y = 9 * s + rng.randrange(0, 9 - hh)
                        ok = 1 <= x and x + w <= 31 and all(not f(cc, r) & TF_SOLID for cc in range(x, x + w)
                                                             for r in range(y, y + hh))
                    elif fl & KF_CLIMBER and near and rng.random() < 0.25:
                        x, y = c, rng.randrange(3, 17 - hh)          # mid-ladder on the shaft
                        ok = True
                    else:
                        s = rng.randrange(2)
                        y = stand_y(s, hh)
                        ok = standable(f, s, x, w, hh)
                    if ok and free_of(boxes, (x, y, w, hh)):
                        break
                else:
                    continue
                boxes.append((x, y, w, hh))
                sl = 1 + len(placed)
                p.set_ent(sl, KIND=k, ROOM=room, FLAGS=EF_ACTIVE | EF_HOSTILE | (EF_LEFT if rng.random() < .5 else 0),
                          HP=200, MAXHP=200, X=x, Y=y, PX=8 * x, PY=8 * y, MODE=0, REACT=0, FLT=0,
                          AIDIR=rng.choice((1, 0xFF)))
                p.wb(S["P_ENTITIES"] + sl * S["P_ENT_STRIDE"] + S["E_RCD"], 0)
                st = 0
                if rng.random() < 0.12:
                    st = rng.choice((S["MIND_FEAR"], S["MIND_CONFUSED"]))
                p.wb(S["ST_FLAGS"] + sl, st)
                p.wb(S["ST_T1"] + sl, 6 if st else 0)
                placed.append(k)
            if not placed:
                continue
            p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0, AIDIR=hdir)
            p.wb("CLIMB_BLK_N", 0)
            p.settle(2)
            nruns += 1
            tag0 = f"seed {seed:#06x} D{depth} hero {hero} room {room} sub {sub} lad {lad}"
            if not QUIET:
                print(f"  {tag0}: hero ({hx},{hy}) bodies " +
                      ", ".join(f"{S_k}" for S_k in placed), flush=True)

            def state():
                out = {}
                for sl in range(1, S["P_MAX_ENT"]):
                    e = p.ent(sl)
                    if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                        out[sl] = e
                return out
            prev = state()
            names = {v: k[2:] for k, v in S.items() if k.startswith("K_") and isinstance(v, int)}
            for t in range(NTURNS):
                he = p.ent(0)
                on_lad = not is_standing(he["Y"], 6)
                r = rng.random()
                if on_lad:
                    keys = rng.choice(["K", "J"]) if r < 0.15 else ("J" if he["AIDIR"] == 1 else "K")
                    if r > 0.9:
                        keys = "WAIT"
                elif he["X"] in lad and r < 0.6:
                    keys = "J" if storey_of(he["Y"], 6) == 0 else "K"
                elif r < 0.75:
                    keys = "WAIT"
                else:
                    keys = rng.choice(["L", "H"])
                if not p.turn(keys, max_ticks=300):
                    p.turn("WAIT", max_ticks=300)
                nturns += 1
                if p.rb("GAME_STATE") != 2 or p.rb("CUR_ROOM") != room or p.rb("LVL_DEPTH") != depth:
                    break
                cur = state()
                he = p.ent(0)
                live = [(0, (he["X"], he["Y"], 3, 6))]
                tag = f"{tag0} turn {t + 1} (hero {keys} -> ({he['X']},{he['Y']}))"
                for sl, e in cur.items():
                    k = e["KIND"]
                    w, hh, fl = info.get(k) or (kt(p, "KT_BW", k), kt(p, "KT_BH", k), kt(p, "KT_FLAGS", k))
                    nm = names.get(k, k)
                    o = prev.get(sl)
                    if o and o["KIND"] in info:
                        ow, oh, ofl = info[o["KIND"]]
                        s0, s1 = storey_of(o["Y"], oh), storey_of(e["Y"], hh)
                        what = f"slot {sl} {nm} ({o['X']},{o['Y']})->({e['X']},{e['Y']})" + \
                               (" PENDING" if e["FLAGS"] & EF_PENDING else "")
                        if fl & KF_FLYER and ofl & KF_FLYER:
                            if s0 != s1:
                                note("F1 flyer storey", f"F1 {tag}: {what}: flyer changed storey {s0}->{s1}")
                        elif not fl & KF_FLYER and not ofl & KF_FLYER and e["Y"] != o["Y"]:
                            okc = fl & KF_CLIMBER and e["X"] == o["X"] and e["X"] in lad
                            if not okc:
                                kd = "F2 storey" if s0 != s1 else "F2 y"
                                note(kd + (" climber" if fl & KF_CLIMBER else " walker"),
                                     f"F2 {tag}: {what}: non-flyer y change off a shaft (storey {s0}->{s1})")
                    if not fl & KF_FLYER and not is_standing(e["Y"], hh) and e["X"] not in lad + exits:
                        note("F3 mid-air", f"F3 {tag}: slot {sl} {nm} ({e['X']},{e['Y']}) not standing, off a shaft")
                    if e["FLAGS"] & (EF_PENDING | EF_DYING):
                        continue
                    b = (e["X"], e["Y"], w, hh)
                    for osl, ob in live:
                        if overlap(b, ob):
                            note("F4 overlap", f"F4 {tag}: slot {sl} {nm} {b} overlaps slot {osl} {ob}")
                    live.append((sl, b))
                    if any(f(cc, rr) & TF_SOLID for cc in range(b[0], b[0] + w) for rr in range(b[1], b[1] + hh)):
                        f = room_cells(p)                    # a door may have opened: re-read
                        if any(f(cc, rr) & TF_SOLID for cc in range(b[0], b[0] + w) for rr in range(b[1], b[1] + hh)):
                            note("F5 wall", f"F5 {tag}: slot {sl} {nm} {b} inside a solid cell")
                prev = cur
    print(f"storey_fuzz: {nruns} runs, {nturns} turns, {len(viol)} violations " +
          (str(sorted(counts.items())) if counts else ""), flush=True)
sys.exit(1 if viol else 0)
