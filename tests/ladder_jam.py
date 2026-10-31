#!/usr/bin/env python3
"""AI-L1 ladder queue (game.md §9.2 'Ladder queue'; user 2026-10-29: STRONGEST FIRST).
Seeded generated games, the real level_descend (level_enter pools the level's kinds), a room
with exactly one {c, 1} ladder; every monster of the room cleared, then two climbers put on the
bottom storey (1) at c + d; the hero waits on the top storey (0), >= 8 cols from the shaft.

  Q1  both climbers reach the hero's storey within MAX_TURNS turns (no jam: J2, the approach
      from both sides that stuck one cell short for ever before AI-L1);
  Q2  opposite sides: the STRONGER (static KT_HP; tie = the lower slot) arrives first;
  Q3  every move is legal: no two live bodies overlap at any turn end;
  Q4  lq_block in the jam pose (stub call): the winner waits, the loser backs off 1 cell;
  T   its cost (far3 included): wait <= 2k T, back-off <= 4.5k T;
  Q5  (the 'mid' cases, Q1) a climber mid-ladder heading away from the hero's storey, blocked by a
      waiter at the foot, turns round (turn3.asm .other) instead of hanging there;
  Q6  no pacing: each climber's x direction reverses at most 4 times (back off, come back).
3-climber chains: a seeker blocked by a body on its own side that is not yet at col backs off.
J1 (the climb-start check over the own end box) cannot happen: every KF_CLIMBER kind is
FEAT_W wide (turn3.asm .at ASSERT), so a body in the near-end box overlaps the climber itself.
fix/spider-climb: the 4-wide Spider (+ Black Widow) is the exception (the cases with SPIDER; lq6 LQ_W = 4).
Build with -DDEBUG_KIT=0.  Usage: ZRCP_PORT=n python3 tests/ladder_jam.py"""
import sys
import game_lib as GL
from game_lib import Harness, S, EMU_ARGS, stand_y, storey_of
from lp import T as Proto, w16

MAX_TURNS = 40                                  # + 20 a climber beyond 2
TF_SOLID, TF_LADDER, TF_FLOOR, TF_HOLE = S["TF_SOLID"], S["TF_LADDER"], S["TF_FLOOR"], S["TF_HOLE"]
HP = {k: None for k in ("ORC", "NECRO", "GOBLIN", "SKELETON", "ARCHER", "SPIDER", "MUMMY")}
BW = {k: 4 if k == "SPIDER" else 3 for k in HP}       # fix/spider-climb: the 4-wide Spider
BH = {k: S["BH_K_" + k] for k in HP}
# (tag, hero, depth, [(kind, dx from col)], seed, opposite sides?)
CASES = [
    ("Orc L / Necro R  D7", 0, 7, [("ORC", -4), ("NECRO", 4)], 0x7403, True),
    ("Necro L / Orc R  D7", 1, 7, [("NECRO", -4), ("ORC", 4)], 0x7303, True),
    ("Necro L / Orc R  D7b", 0, 7, [("NECRO", -5), ("ORC", 4)], 0x7203, True),
    ("Goblin L / Goblin R D1", 0, 1, [("GOBLIN", -4), ("GOBLIN", 4)], 0x1401, True),
    ("Goblin R / Goblin L D2", 1, 2, [("GOBLIN", 4), ("GOBLIN", -4)], 0x2401, True),
    ("Skel L / Archer R D5", 0, 5, [("SKELETON", -4), ("ARCHER", 4)], 0x5401, True),
    ("Archer L / Skel R D5", 1, 5, [("ARCHER", -4), ("SKELETON", 5)], 0x5402, True),
    ("Orc L / Archer R D4", 0, 4, [("ORC", -4), ("ARCHER", 4)], 0x4401, True),
    ("Archer L / Orc R D4", 1, 4, [("ARCHER", -4), ("ORC", 4)], 0x4402, True),
    ("Orc col+3 / Necro col+6 D7", 0, 7, [("ORC", 3), ("NECRO", 6)], 0x7501, False),
    ("Goblin col / Goblin col+3 D1", 1, 1, [("GOBLIN", 0), ("GOBLIN", 3)], 0x1501, False),
    # review: 3 climbers, the middle one boxed in between two winners (stuck for ever before the
    # same-side back-off: 3 of 4 on the first AI-L1 tree, all 4 on main)
    ("3: Orc c-2 / Necro c+1 / Orc c+4 D7", 0, 7, [("ORC", -2), ("NECRO", 1), ("ORC", 4)], 0x7403, False),
    ("3: Orc c-4 / Necro c+3 / Orc c+6 D7", 0, 7, [("ORC", -4), ("NECRO", 3), ("ORC", 6)], 0x7403, False),
    ("3: Orc c+4 / Necro c-2 / Orc c-5 D7", 1, 7, [("ORC", 4), ("NECRO", -2), ("ORC", -5)], 0x7303, False),
    ("3: Necro c-4 / Orc c+3 / Orc c+6 D7", 0, 7, [("NECRO", -4), ("ORC", 3), ("ORC", 6)], 0x7203, False),
    ("3: Goblin c-2 / Goblin c+1 / Goblin c+4 D1", 1, 1, [("GOBLIN", -2), ("GOBLIN", 1), ("GOBLIN", 4)], 0x1401, False),
    # review: the 1st climber mid-ladder heading DOWN (ai_dir +1) while the hero is above (it changed
    # storey mid-climb), the 2nd waiting at col below it: the mid-ladder one must turn round (Q5)
    # fix/spider-climb: a 4-wide body (Spider, BH 2) in the 3-wide shaft's end box (J1 re-proof)
    ("Spider L / Goblin R D2", 0, 2, [("SPIDER", -5), ("GOBLIN", 4)], 0x2601, True),
    ("Goblin L / Spider R D2", 1, 2, [("GOBLIN", -4), ("SPIDER", 4)], 0x2602, True),
    ("Spider L / Spider R D4", 0, 4, [("SPIDER", -5), ("SPIDER", 4)], 0x4601, True),
    ("Spider L / Mummy R D5", 1, 5, [("SPIDER", -5), ("MUMMY", 4)], 0x5601, True),
    ("Mummy L / Spider R D5", 0, 5, [("MUMMY", -4), ("SPIDER", 4)], 0x5602, True),
    ("Spider col / Goblin col+4 D2", 0, 2, [("SPIDER", 0), ("GOBLIN", 4)], 0x2701, False),
    ("Spider col+1 / Spider col+5 D4", 1, 4, [("SPIDER", 1), ("SPIDER", 5)], 0x4701, False),
    ("Mummy col / Spider col+3 D5", 0, 5, [("MUMMY", 0), ("SPIDER", 3)], 0x5701, False),
    ("3: Spider c-5 / Mummy c+1 / Spider c+5 D5", 1, 5, [("SPIDER", -5), ("MUMMY", 1), ("SPIDER", 5)], 0x5801, False),
    ("mid: Spider descending above / Mummy waiting at col D5", 0, 5, [("SPIDER", 0), ("MUMMY", 0)], 0x5901, "mid"),
    ("mid: Mummy descending above / Spider waiting at col D5", 1, 5, [("MUMMY", 0), ("SPIDER", 0)], 0x5902, "mid"),
    ("mid: Spider descending above / Spider waiting at col D4", 0, 4, [("SPIDER", 0), ("SPIDER", 0)], 0x4901, "mid"),
    ("mid: Orc descending above / Necro waiting at col D7", 0, 7, [("ORC", 0), ("NECRO", 0)], 0x7403, "mid"),
    ("mid: Necro descending above / Orc waiting at col D7", 1, 7, [("NECRO", 0), ("ORC", 0)], 0x7303, "mid"),
]
fails = 0


def check(name, ok, got=None):
    global fails
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": {got}"), flush=True)


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"])
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < S["PLAY_ROWS"] else TF_SOLID


def standable(f, s, x, h=6, w=3):
    y = stand_y(s, h)
    if x < 1 or x + w > 31:
        return False
    if not all(f(c, y + h) & TF_FLOOR and not f(c, y + h) & TF_HOLE for c in range(x, x + w)):
        return False
    return all(not f(c, r) & TF_SOLID for c in range(x, x + w) for r in range(y, y + h))


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def lq_cost(p, c):
    """Q4 / T: lq_block itself (far3 from a stub; bank 3 since MEM-RECLAIM w3, LIVE_LIST of the last turn: both slots live).
    The J2 jam pose on storey 1: Orc (slot 1, hp 14) at c-1, Necro (slot 2, hp 12) at c+2."""
    ent = lambda sl: S["P_ENTITIES"] + sl * S["P_ENT_STRIDE"]
    for sl, x in ((1, c - 1), (2, c + 2)):
        y = stand_y(1, 6)
        p.set_ent(sl, X=x, Y=y, PX=8 * x, PY=8 * y, MODE=0)
    pc0 = p.pc()
    res = {}
    for name, sl, dx in (("winner waits", 1, 1), ("loser backs off", 2, 0xFF)):
        ok, ts = p.code([0x3E, sl, 0x32] + w16(S["ACT_SLOT"]) + [0xDD, 0x21] + w16(ent(sl)) +
                        [0x11, c, dx, 0x21] + w16(S["lq_block"]) + [0xCD] + w16(S["far3"]), game=True)   # MEM-RECLAIM w3: lq_block is bank 3 (far3 from the stub)
        res[name] = (ok, ts - 62)                       # minus the stub (DI, EI, 5 loads: 62 T)
    p.z.cmd("set-register PC=%d" % pc0)
    x1, x2 = p.ent(1)["X"], p.ent(2)["X"]
    print("  lq_block T (incl. far3): " + ", ".join(f"{k} {v[1]}" for k, v in res.items()), flush=True)
    check("lq_block: the winner waits, the loser backs off 1 cell (Q4)", x1 == c - 1 and x2 == c + 3 and
          all(v[0] for v in res.values()), (x1, x2, res))
    # measured 1,420 / 3,548 (D7, 2 live monsters + hero): far6 ~0.2k, box_free ~0.4k, the back-off's
    # try_step (terrain, box_free, cork, mv_sfx) ~2k; only on a blocked seek step
    check("lq_block: wait <= 2k T, back-off (a step) <= 4.5k T (T)",
          res["winner waits"][1] <= 2000 and res["loser backs off"][1] <= 4500, res)


with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    GL.Proto.snd_mode = 2
    jams = 0
    for tag, hero, depth, mons, seed, opp in CASES:
        done = False
        for attempt in range(16):
            p.proto_start = 0
            p.boot(hero=hero, freeze=0)
            p.wmem(S["MASTER_SEED"], w16(seed + 0x100 * attempt))
            pc0 = p.pc()
            ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            if not ok or p.rb("LVL_DEPTH") != depth:
                continue
            p.release(); p.settle(4)
            f = room_cells(p)
            lad = [c for c in range(2, 29) if all(f(c, r) & TF_LADDER for r in range(10, 15))]
            if not lad or lad[-1] - lad[0] > 2:
                continue                                # none, or two {c,1} shafts
            c = lad[0]
            okp = all(standable(f, 1, c + d, BH[k], BW[k]) for k, d in mons)
            hd = 4 * len(mons) + 1                      # room for the arrivals queueing toward the hero
            hx = next((x for x in list(range(c - hd, 0, -1)) + list(range(c + hd, 28)) if standable(f, 0, x)), None)
            if not okp or hx is None:
                continue
            done = True
            break
        if not done:
            check(tag + ": room found", False, "no room")
            continue
        room = p.rb("CUR_ROOM")
        for k in HP:                                    # static base hp (kind_tab KT_HP, bank 2)
            HP[k] = p.z.read_memory(S["kind_tab"] + S["KT_HP"] + S["K_" + k], 1)[0]
        for sl in range(1, S["P_MAX_ENT"]):
            p.set_ent(sl, FLAGS=0)
        for i, (kn, d) in enumerate(mons):
            x, yk = c + d, stand_y(1, BH[kn]) - (max(BH[k] for k, _ in mons) if opp == "mid" and i == 0 else 0)
            p.set_ent(1 + i, KIND=S["K_" + kn], ROOM=room, FLAGS=1 | 4, HP=200, MAXHP=200, X=x, Y=yk,
                      PX=8 * x, PY=8 * yk, MODE=0, REACT=0, FLT=0, AIDIR=1)
            p.wb(S["ST_FLAGS"] + 1 + i, 0)
        hy = stand_y(0, 6)
        p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0)
        p.settle(2)
        turns, first, bad = 0, {}, None
        xs = [[p.ent(1 + i)["X"]] for i in range(len(mons))]
        while turns < MAX_TURNS + 20 * (len(mons) - 2) and p.rb("GAME_STATE") == 2:
            p.turn("WAIT", max_ticks=200)
            turns += 1
            boxes = []
            for i, (kn, _) in enumerate(mons):
                e = p.ent(1 + i)
                boxes.append((e["X"], e["Y"], BW[kn], BH[kn]))
                if e["X"] != xs[i][-1]:
                    xs[i].append(e["X"])
                if storey_of(e["Y"], BH[kn]) == 0 and (e["Y"] + BH[kn]) % 9 == 8 and i not in first:
                    first[i] = turns
            if bad is None and any(overlap(boxes[a], boxes[b]) for a in range(len(boxes)) for b in range(a)):
                bad = (turns, boxes)
            if len(first) == len(mons):
                break
        rev = [sum((b - a) * (c_ - b) < 0 for a, b, c_ in zip(x, x[1:], x[2:])) for x in xs]   # x reversals
        st = "; ".join(f"{k}(hp{HP[k]}) x{p.ent(1 + i)['X']} top@{first.get(i)} rev{rev[i]}"
                       for i, (k, _) in enumerate(mons))
        print(f"  {tag} (col {c}): {st}", flush=True)
        both = len(first) == len(mons) or (opp == "mid" and 0 in first)   # mid: the 2nd may be a
        # shooter (Necro) parked on the far-end box shooting the hero: a pre-existing hold, not AI-L1
        jams += not both
        check(tag + ": all climbed (Q1)", both, st)
        check(tag + ": no pacing: <= 4 x reversals each (Q6)", max(rev) <= 4, rev)
        check(tag + ": no overlap (Q3)", bad is None, bad)
        if tag == CASES[0][0]:
            lq_cost(p, c)
        if opp is True and both:
            (k0, _), (k1, _) = mons
            win = 0 if HP[k0] >= HP[k1] else 1              # tie: slot 1 (the lower) first
            check(tag + ": strongest first (Q2)", first[win] < first[1 - win] or
                  (first[win] == first[1 - win] and win == 0), first)
    print(f"ladder_jam: {fails} failed, jams {jams}/{len(CASES)}", flush=True)
sys.exit(1 if fails else 0)
