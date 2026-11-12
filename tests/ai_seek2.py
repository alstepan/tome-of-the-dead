#!/usr/bin/env python3
"""AI-SEEK2 (docs/design/ai_seek2.md): walkers follow the hero across storeys and halves.

Emulator cases, the ladder_jam.py pattern (seeded generated game, the real level_descend, the room's
descriptor then OVERWRITTEN with the case's geometry and the room rebuilt by the real build_room
-> ROOM_MAP + ROOM_CUT; every other monster cleared; bodies poked; the hero waits / climbs). Each
case: the outcome within a turn bound, no body overlap and no body in a solid tile at any turn
end, <= 2 x reversals per monster (no pacing).

  K    ROOM_CUT (build_room_map) == the Python twin tools/levelgen.py room_cut for every room of
       generated levels (pits, wide pits, mid-blocks, none)
  S1   mid-block, Goblin on storey 1 near the right ladder, hero storey 0 left half: climbs LAD1 (F1)
  S2   wide pit, Skeleton under the left half, hero right half: climbs the right ladder (F1)
  S3   mid-block, Goblin storey 0 left half next to the block, hero storey 1: descends the LEFT
       ladder, never presses at the block face (F2)
  S4   mid-block, climber storey 0 left, hero storey 0 right: down, across, up, adjacent (F3)
  S5   as S4 with a non-climber (Rat): walks to the block face, then stands still facing the hero
  S6   narrow pit, one ladder (left), hero in the ladderless right half, climber storey 1: climbs
       the ladder, waits at the far lip facing the hero, never climbs back down (R5 + R6)
  S7   narrow pit, one ladder, climber in the ladderless half, hero storey 1: waits at the lip (R6)
  S8   no cut, hero climbing the left ladder up from storey 1: the storey-0 Skeleton does NOT go down
       the other ladder; it walks to the left ladder's lip, off the climb path (F4)
  S9   no cut, hero climbing the left ladder down: the storey-1 climber waits at the foot, never climbs
  S10  narrow pit, two ladders, the hero hops the pit 6 times, 2 climbers: no overlap, every body
       legal, both end adjacent to the hero
  U1   seek_col (far7 stub) over a table of (K, ladders, M, H, x) rows: col / STRANDED; T
  U2   cache_player + pl_seg3 (stub): PL_SEG / PL_LADDER for the hero mid-climb up / down on an
       internal ladder, on the exit shafts, standing
Build with -DDEBUG_KIT=0.  Usage: ZRCP_PORT=n python3 tests/ai_seek2.py"""
import sys
import game_lib as GL
from game_lib import Harness, S, EMU_ARGS, stand_y, storey_of, is_standing, E
from lp import T as Proto, w16

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "tools"))
import levelgen as LG                                                   # noqa: E402

TF_SOLID, TF_LADDER, TF_FLOOR, TF_HOLE = S["TF_SOLID"], S["TF_LADDER"], S["TF_FLOOR"], S["TF_HOLE"]
ROOMS = S["ROOM_DESC"]
RDS = 16
EF_LEFT = 8
fails = 0
HERO_H = 6
KIND_DEPTH = {"GOBLIN": 2, "SKELETON": 5, "RAT": 1}


def check(name, ok, got=None):
    global fails
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": {got}"), flush=True)


def kbox(kind):
    return (S["K_" + kind], None)


def kwh(p, kind):
    """(w, h) of a kind from kind_tab (bank 2: always mapped)."""
    k = S["K_" + kind]
    return (p.z.read_memory(S["kind_tab"] + S["KT_BW"] + k, 1)[0], p.z.read_memory(S["kind_tab"] + S["KT_BH"] + k, 1)[0])


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"])
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < S["PLAY_ROWS"] else TF_SOLID


def standable(f, s, x, h, w):
    y = stand_y(s, h)
    if x < 1 or x + w > 31:
        return False
    if not all(f(c, y + h) & TF_FLOOR and not f(c, y + h) & TF_HOLE for c in range(x, x + w)):
        return False
    return all(not f(c, r) & TF_SOLID for c in range(x, x + w) for r in range(y, y + h))


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def desc_base(room):
    return ROOMS + room * RDS


def new_game(p, depth, seed):
    """Boot a generated game and enter depth (as ladder_jam)."""
    for attempt in range(16):
        p.proto_start = 0
        p.boot(hero=0, freeze=0)
        p.wmem(S["MASTER_SEED"], w16(seed + 0x100 * attempt))
        pc0 = p.pc()
        ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        if ok and p.rb("LVL_DEPTH") == depth:
            p.release(); p.settle(4)
            return True
    return False


def build_room_now(p, room):
    """The real build_room for the current room into ROOM_MAP (A = room, H = ROOM_MAP >> 8)."""
    pc0 = p.pc()
    ok, _ = p.code([0x3E, room, 0x26, S["ROOM_MAP"] >> 8, 0xCD] + w16(S["build_room"]), game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    return ok


def set_geometry(p, lad1, lad2=0, pit=0, pitw=0, midb=0, midw=0):
    """Overwrite the current room's descriptor with a bare room (no exits, no shafts, no block, no
    decor) holding just these features, rebuild its map."""
    room = p.rb("CUR_ROOM")
    base = desc_base(room)
    for off in range(RDS):
        if off in (S["RD_FLAGS"],):
            continue
        p.wb(base + off, 0)
    p.wb(base + S["RD_LAD1"], lad1)
    p.wb(base + S["RD_LAD2"], lad2)
    p.wb(base + S["RD_PITCOL"], pit)
    p.wb(base + S["L2_PITW"], pitw)
    p.wb(base + S["L2_MIDB"], midb)
    p.wb(base + S["L2_MIDW"], midw)
    p.wb(base + S["RD_SEED"], 0)
    p.wb(base + S["RD_SEED"] + 1, 0)
    assert build_room_now(p, room)
    return room


def place(p, room, hero, mons, kinds_hp=200):
    """hero = (storey, x); mons = [(kind, storey, x)]; every other slot cleared."""
    for sl in range(1, S["P_MAX_ENT"]):
        p.set_ent(sl, FLAGS=0)
    for i, (kn, s, x) in enumerate(mons):
        w, h = kwh(p, kn)
        y = stand_y(s, h)
        p.set_ent(1 + i, KIND=S["K_" + kn], ROOM=room, FLAGS=1 | 4, HP=kinds_hp, MAXHP=kinds_hp, X=x, Y=y,
                  PX=8 * x, PY=8 * y, MODE=0, REACT=0, FLT=0, AIDIR=1)
        p.wb(S["ST_FLAGS"] + 1 + i, 0)
    hs, hx = hero
    hy = stand_y(hs, HERO_H)
    p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0, AIDIR=0)
    p.settle(2)


class Run:
    """One scenario: per turn the hero's and each monster's (x, y, flags) + legality."""

    def __init__(self, p, tag, kinds, f):
        self.p, self.tag, self.kinds, self.f = p, tag, kinds, f
        self.dims = [kwh(p, k) for k in kinds]
        self.tr = []                                    # per turn: (hero, [monster...])
        self.rng = []                                   # RNG_STATE per turn end (an attack draws: the only RNG user here)
        self.bad = None

    def snap(self):
        p = self.p
        h = p.ent(0)
        ms = [p.ent(1 + i) for i in range(len(self.kinds))]
        self.tr.append((h, ms))
        self.rng.append(p.rw("RNG_STATE"))
        boxes = [(m["X"], m["Y"], self.dims[i][0], self.dims[i][1]) for i, m in enumerate(ms)]
        hb = (h["X"], h["Y"], 3, HERO_H)
        n = len(self.tr)
        for i, b in enumerate(boxes):
            if overlap(b, hb) and self.bad is None:
                self.bad = (n, "overlap hero", i, b, hb)
            for j in range(i):
                if overlap(b, boxes[j]) and self.bad is None:
                    self.bad = (n, "overlap", i, j, b, boxes[j])
            if any(self.f(c, r) & TF_SOLID for c in range(b[0], b[0] + b[2]) for r in range(max(0, b[1]), min(b[1] + b[3], S["PLAY_ROWS"]))) and self.bad is None:
                self.bad = (n, "solid", i, b)

    def mstorey(self, i, t):
        m = self.tr[t][1][i]
        return storey_of(m["Y"], self.dims[i][1])

    def mstand(self, i, t):
        m = self.tr[t][1][i]
        return is_standing(m["Y"], self.dims[i][1])

    def adj(self, i, t):
        """standing on the hero's storey, horizontal gap <= 1."""
        h, ms = self.tr[t]
        m = ms[i]
        if not self.mstand(i, t) or not is_standing(h["Y"], HERO_H):
            return False
        if self.mstorey(i, t) != storey_of(h["Y"], HERO_H):
            return False
        w = self.dims[i][0]
        gap = max(h["X"] - (m["X"] + w), m["X"] - (h["X"] + 3))
        return gap <= 1

    def xs(self, i):
        out = []
        for _, ms in self.tr:
            if not out or ms[i]["X"] != out[-1]:
                out.append(ms[i]["X"])
        return out

    def rev(self, i):
        x = self.xs(i)
        return sum((b - a) * (c - b) < 0 for a, b, c in zip(x, x[1:], x[2:]))


def run_turns(r, n, key="WAIT", stop=None, hero_script=None):
    p = r.p
    r.snap()
    for t in range(n):
        if p.rb("GAME_STATE") != 2:
            break
        if hero_script:
            hero_script(t)
        keys = key(t) if callable(key) else key
        p.turn(*(keys if isinstance(keys, tuple) else (keys,)), max_ticks=200)
        r.snap()
        if stop and stop(r):
            break


def common(r, tag, rev_max=2):
    check(f"{tag}: no overlap, no body in a solid tile", r.bad is None, r.bad)
    revs = [r.rev(i) for i in range(len(r.kinds))]
    check(f"{tag}: no pacing (<= {rev_max} x reversals each)", max(revs) <= rev_max, revs)


def case_env(p, kind_for_depth, seed):
    d = KIND_DEPTH[kind_for_depth]
    assert new_game(p, d, seed), "no game"


def first_turn(r, pred, i=0):
    for t in range(len(r.tr)):
        if pred(r, i, t):
            return t
    return None


# ---------------------------------------------------------------------------------------- cases
def case_s1(p):
    p_ = dict(lad1=4, lad2=20, midb=15, midw=2)
    case_env(p, "GOBLIN", 0x2A01)
    room = set_geometry(p, **p_)
    f = room_cells(p)
    place(p, room, (0, 9), [("GOBLIN", 1, 19)])
    assert standable(f, 0, 9, HERO_H, 3)
    r = Run(p, "S1", ["GOBLIN"], f)
    K = p.rb("ROOM_CUT")
    run_turns(r, 40, stop=lambda r: r.adj(0, len(r.tr) - 1))
    t = first_turn(r, lambda r, i, t: r.adj(i, t))
    check("S1: ROOM_CUT = b - 1 = 14", K == 14, K)
    check("S1: the Goblin climbs LAD1 and is adjacent within 30 turns (F1)", t is not None and t <= 30, t)
    wrong = [tt for tt in range(len(r.tr)) if r.mstand(0, tt) and r.mstorey(0, tt) == 0 and r.tr[tt][1][0]["X"] > K]
    check("S1: never stands on storey 0 in the right half (F1)", not wrong, wrong[:3])
    common(r, "S1")


def case_s2(p):
    case_env(p, "SKELETON", 0x2A02)
    room = set_geometry(p, lad1=4, lad2=24, pit=14, pitw=5)
    f = room_cells(p)
    place(p, room, (0, 28), [("SKELETON", 1, 8)])
    assert standable(f, 0, 28, HERO_H, 3), "hero cell"
    r = Run(p, "S2", ["SKELETON"], f)
    K = p.rb("ROOM_CUT")
    run_turns(r, 60, stop=lambda r: r.adj(0, len(r.tr) - 1))
    t = first_turn(r, lambda r, i, t: r.adj(i, t))
    check("S2: ROOM_CUT = the wide pit col 14", K == 14, K)
    check("S2: the Skeleton climbs the right ladder and is adjacent within 55 turns (F1, pit)", t is not None and t <= 55, t)
    left0 = [tt for tt in range(len(r.tr)) if r.mstand(0, tt) and r.mstorey(0, tt) == 0 and r.tr[tt][1][0]["X"] <= K]
    check("S2: never stands on storey 0 in the left half", not left0, left0[:3])
    common(r, "S2")


def case_s3(p):
    case_env(p, "GOBLIN", 0x2A03)
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (1, 10), [("GOBLIN", 0, 13)])
    assert standable(f, 0, 13, kwh(p, "GOBLIN")[1], 3), "goblin cell"
    r = Run(p, "S3", ["GOBLIN"], f)
    run_turns(r, 30, stop=lambda r: r.mstorey(0, len(r.tr) - 1) == 1 and r.mstand(0, len(r.tr) - 1))
    t = first_turn(r, lambda r, i, t: r.mstorey(i, t) == 1 and r.mstand(i, t))
    check("S3: the Goblin descends the left ladder within 25 turns (F2)", t is not None and t <= 25, t)
    over = [tt for tt in range(len(r.tr)) if r.mstorey(0, tt) == 0 and r.tr[tt][1][0]["X"] > 13]
    check("S3: never steps right of x 13 (never presses at the block face)", not over, over[:3])
    common(r, "S3")


def case_s4(p):
    case_env(p, "GOBLIN", 0x2A04)
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 26), [("GOBLIN", 0, 10)])
    assert standable(f, 0, 26, HERO_H, 3) and standable(f, 0, 10, kwh(p, "GOBLIN")[1], 3)
    r = Run(p, "S4", ["GOBLIN"], f)
    run_turns(r, 75, stop=lambda r: r.adj(0, len(r.tr) - 1))
    t = first_turn(r, lambda r, i, t: r.adj(i, t))
    check("S4: the Goblin goes down LAD1, across, up LAD2 and is adjacent (F3) within 70 turns", t is not None and t <= 70, t)
    check("S4: it visited storey 1", any(r.mstorey(0, tt) == 1 and r.mstand(0, tt) for tt in range(len(r.tr))), None)
    common(r, "S4")


def case_s5(p):
    case_env(p, "RAT", 0x2A05)
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 26), [("RAT", 0, 8)])
    r = Run(p, "S5", ["RAT"], f)
    run_turns(r, 60)
    x_end = r.tr[-1][1][0]["X"]
    still = r.xs(0)[-1] == x_end and all(r.tr[tt][1][0]["X"] == x_end for tt in range(len(r.tr) - 20, len(r.tr)))
    fl = r.tr[-1][1][0]["FLAGS"]
    check("S5: the Rat reaches the block face then stands still for 20 turns (R2)", still, r.xs(0)[-4:])
    check("S5: it stays on storey 0, left half, facing the hero", all(r.mstorey(0, tt) == 0 for tt in range(len(r.tr))) and
          x_end < 16 and not fl & EF_LEFT, (x_end, fl))
    check("S5: it got to the face (x >= 11)", x_end >= 11, x_end)
    common(r, "S5", 1)


def case_s6(p):
    case_env(p, "GOBLIN", 0x2A06)
    room = set_geometry(p, lad1=5, pit=14)
    f = room_cells(p)
    place(p, room, (0, 24), [("GOBLIN", 1, 20)])
    assert standable(f, 0, 24, HERO_H, 3)
    r = Run(p, "S6", ["GOBLIN"], f)
    run_turns(r, 60)
    on0 = [tt for tt in range(len(r.tr)) if r.mstorey(0, tt) == 0 and r.mstand(0, tt)]
    check("S6: the Goblin climbs the only ladder to storey 0 (R5)", bool(on0), None)
    if on0:
        t0 = on0[0]
        tail = r.tr[t0 + 5:]
        xe = r.tr[-1][1][0]["X"]
        check("S6: then it never goes back down", all(r.mstorey(0, tt) == 0 for tt in range(t0, len(r.tr))), None)
        check("S6: it waits at the far lip (x constant for the last 12 turns, left half near the pit, facing the hero)",
              all(r.tr[tt][1][0]["X"] == xe for tt in range(len(r.tr) - 12, len(r.tr))) and 14 - 6 <= xe <= 14 and
              not r.tr[-1][1][0]["FLAGS"] & EF_LEFT, (xe, r.tr[-1][1][0]["FLAGS"]))
    common(r, "S6")


def case_s7(p):
    case_env(p, "GOBLIN", 0x2A07)
    room = set_geometry(p, lad1=5, pit=14)
    f = room_cells(p)
    place(p, room, (1, 8), [("GOBLIN", 0, 24)])
    r = Run(p, "S7", ["GOBLIN"], f)
    run_turns(r, 50)
    xe = r.tr[-1][1][0]["X"]
    check("S7: the climber in the ladderless half walks to the pit lip and waits (R6)",
          all(r.tr[tt][1][0]["X"] == xe for tt in range(len(r.tr) - 12, len(r.tr))) and 14 < xe < 24 and
          r.tr[-1][1][0]["FLAGS"] & EF_LEFT, (xe, r.xs(0)[-4:]))
    check("S7: it never leaves storey 0", all(r.mstorey(0, tt) == 0 for tt in range(len(r.tr))), None)
    common(r, "S7", 1)


def case_s8(p):
    case_env(p, "SKELETON", 0x2A08)
    room = set_geometry(p, lad1=6, lad2=22)
    f = room_cells(p)
    place(p, room, (1, 6), [("SKELETON", 0, 19)])
    r = Run(p, "S8", ["SKELETON"], f)
    run_turns(r, 9, key="K")
    run_turns(r, 6)
    hero_up = [tt for tt in range(len(r.tr)) if is_standing(r.tr[tt][0]["Y"], HERO_H) and storey_of(r.tr[tt][0]["Y"], HERO_H) == 0]
    check("S8: the hero climbed up to storey 0 in <= 9 turns", bool(hero_up), [t[0]["Y"] for t in r.tr])
    left = all(r.mstorey(0, tt) == 0 and r.mstand(0, tt) for tt in range(len(r.tr)))
    check("S8: the Skeleton never leaves storey 0 (does NOT go down LAD2, F4)", left,
          [(r.tr[tt][1][0]["X"], r.tr[tt][1][0]["Y"]) for tt in range(len(r.tr))])
    xs = r.xs(0)
    check("S8: it walks left toward the climber's ladder (x decreases, never into LAD2's col 22)", xs[-1] < 19 and max(xs) <= 19, xs)
    # off the climb path EVERY turn: the hero's column band (3 wide) from the standing top row down to his feet
    on_path = []
    for tt, (h_, ms) in enumerate(r.tr):
        if is_standing(h_["Y"], HERO_H) and storey_of(h_["Y"], HERO_H) == 0:
            continue                                    # he has arrived: the path is behind him
        band = (h_["X"], stand_y(0, HERO_H), 3, h_["Y"] + HERO_H - stand_y(0, HERO_H))
        m = ms[0]
        if overlap((m["X"], m["Y"], r.dims[0][0], r.dims[0][1]), band):
            on_path.append((tt, m["X"], m["Y"]))
    check("S8: the Skeleton is off the hero's climb path at every turn end (F4, the cork rule)", not on_path, on_path[:3])
    t = hero_up[0] if hero_up else None
    att = [tt for tt in range(1, len(r.tr)) if r.rng[tt] != r.rng[tt - 1]]      # an attack draws the RNG; nothing else does here
    check("S8: it is adjacent when he stands and attacks within 2 turns of it (no RNG draw before)",
          t is not None and r.adj(0, t) and bool(att) and t <= att[0] <= t + 2,
          (t, att[:3], r.adj(0, t) if t is not None else None))
    common(r, "S8")


def case_s9(p):
    """The hero climbs UP from storey 1: PL_STOREY says storey 1 the whole climb, PL_SEG says storey 0 (F4 mirror). The
    storey-1 Goblin (x 16, LAD2 nearer than LAD1) heads for the ladder into the hero's destination at once (old: it
    treated him as 'same storey' and walked to his shaft's foot)."""
    case_env(p, "GOBLIN", 0x2A09)
    room = set_geometry(p, lad1=6, lad2=22)
    f = room_cells(p)
    place(p, room, (1, 6), [("GOBLIN", 1, 16)])
    r = Run(p, "S9", ["GOBLIN"], f)
    run_turns(r, 9, key="K")
    run_turns(r, 20)
    xs = r.xs(0)
    check("S9: while the hero climbs up the climber walks AWAY from his shaft toward LAD2 (x grows, F4 mirror)", len(xs) > 2 and xs[1] > 16, xs)
    top = [tt for tt in range(len(r.tr)) if r.mstorey(0, tt) == 0 and r.mstand(0, tt)]
    check("S9: it climbs LAD2 to storey 0 within 30 turns", bool(top) and top[0] <= 30, top[:2])
    common(r, "S9")


def case_s9r(p):
    """Regression: the hero climbs DOWN (PL_STOREY == PL_SEG): the storey-1 climber waits at the foot, never climbs."""
    case_env(p, "GOBLIN", 0x2A09)
    room = set_geometry(p, lad1=6, lad2=22)
    f = room_cells(p)
    place(p, room, (0, 6), [("GOBLIN", 1, 16)])
    r = Run(p, "S9r", ["GOBLIN"], f)
    run_turns(r, 9, key="J")
    run_turns(r, 4)
    hero_dn = [tt for tt in range(len(r.tr)) if is_standing(r.tr[tt][0]["Y"], HERO_H) and storey_of(r.tr[tt][0]["Y"], HERO_H) == 1]
    check("S9r: the hero climbed down to storey 1 in <= 9 turns", bool(hero_dn), [t[0]["Y"] for t in r.tr])
    check("S9r: the climber stays on storey 1 (waits at the foot, never climbs, R1)",
          all(r.mstorey(0, tt) == 1 and r.mstand(0, tt) for tt in range(len(r.tr))), [r.tr[tt][1][0]["Y"] for tt in range(len(r.tr))])
    xs = r.xs(0)
    check("S9r: it walked to the foot (x decreased toward col 6) and stopped", xs[-1] < 16 and r.rev(0) == 0, xs)
    common(r, "S9r")


def case_s10(p):
    case_env(p, "GOBLIN", 0x2A0A)
    room = set_geometry(p, lad1=5, lad2=26, pit=14)
    f = room_cells(p)
    L, R = 11, 17                                      # the jump crossing: p - 3 <-> p + 3
    place(p, room, (0, L), [("GOBLIN", 1, 12), ("GOBLIN", 0, 24)])
    assert standable(f, 0, L, HERO_H, 3) and standable(f, 0, R, HERO_H, 3), "hop cells"
    r = Run(p, "S10", ["GOBLIN", "GOBLIN"], f)
    hops = []
    for n in range(7):                                 # 7 REAL jumps (UP + side), each one turn
        x0 = p.ent(0)["X"]
        want_left = x0 != L
        if bool(p.ent(0)["FLAGS"] & EF_LEFT) != want_left:       # turn-around tap first (0 turns)
            p.tap("O" if want_left else "P")
            p.tick(2)
        run_turns(r, 1, key=("K", "H") if want_left else ("K", "L"))
        x1 = p.ent(0)["X"]
        if x1 != x0:
            hops.append((x0, x1))
        run_turns(r, 1)                                  # no jump two turns in a row (try_jump JUMP_TURN): a wait between
    check("S10: the hero made 7 real jumps across the pit (11 <-> 17)", len(hops) == 7 and all(abs(a - b) == 6 for a, b in hops), hops)
    half = lambda x: 1 if x > 14 else 0
    hh = half(p.ent(0)["X"])
    arrived = lambda r, i: (r.mstand(i, len(r.tr) - 1) and r.mstorey(i, len(r.tr) - 1) == 0 and half(r.tr[-1][1][i]["X"]) == hh)
    run_turns(r, 70, stop=lambda r: arrived(r, 0) and arrived(r, 1))
    check("S10: no softlock: both climbers end on storey 0 in the hero's half, one adjacent",
          arrived(r, 0) and arrived(r, 1) and any(r.adj(i, len(r.tr) - 1) for i in (0, 1)),
          [(m["X"], m["Y"]) for m in r.tr[-1][1]])
    check("S10: no overlap, every body outside solids at every turn end", r.bad is None, r.bad)


def case_s4b(p):
    """1-hop + R3: a body parked at LAD1's foot (re-poked there every turn) blocks the descending climber; it must not
    reverse mid-ladder (ping-pong), it waits above the foot."""
    case_env(p, "GOBLIN", 0x2A04)
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 26), [("GOBLIN", 0, 8), ("RAT", 1, 16)])
    r = Run(p, "S4b", ["GOBLIN", "RAT"], f)
    ry = stand_y(1, kwh(p, "RAT")[1])

    def park(t):                                       # the body arrives once the climber is on the ladder
        if p.ent(1)["Y"] >= 7 or r.tr[-1][1][1]["X"] == 4:
            p.set_ent(2, X=4, Y=ry, PX=32, PY=8 * ry, MODE=0)
    run_turns(r, 40, hero_script=park)
    ys = [r.tr[t][1][0]["Y"] for t in range(len(r.tr))]
    mid = [y for t, y in enumerate(ys) if not r.mstand(0, t)]
    d = [b - a for a, b in zip(mid, mid[1:]) if b != a]
    rev = sum(1 for a, b in zip(d, d[1:]) if (a > 0) != (b > 0))
    print(f"  S4b climber y per turn {ys}", flush=True)
    check("S4b: blocked at the LAD1 foot the climber never reverses mid-ladder (no ping-pong)", rev == 0 and max(ys) < 13, (rev, ys))


# ----------------------------------------------------------------------------- K: ROOM_CUT twin
def case_k(p):
    bad, n, kinds = [], 0, set()
    for depth, seed in ((2, 0x2B01), (3, 0x2B02), (4, 0x2B03), (5, 0x2B04), (6, 0x2B05), (7, 0x2B06), (8, 0x2B07), (3, 0x2B08)):
        if not new_game(p, depth, seed):
            bad.append(("no game", depth)); continue
        for rm in range(9):
            base = desc_base(rm)
            d = list(p.z.read_memory(base, RDS))
            if not d[S["RD_FLAGS"]] & S["RDF_PRESENT"]:
                continue
            if not build_room_now(p, rm):
                bad.append(("build", depth, rm)); continue
            got, want = p.rb("ROOM_CUT"), LG.room_cut(d)
            n += 1
            kinds.add("pit" if d[S["RD_PITCOL"]] else "mid" if d[S["L2_MIDB"]] else "none")
            if got != want:
                bad.append((depth, rm, got, want, d))
    check(f"K: ROOM_CUT == levelgen.room_cut over {n} rooms ({', '.join(sorted(kinds))})", not bad and n >= 40 and len(kinds) == 3, (bad[:2], n, kinds))


# --------------------------------------------------------------------------------- U1 seek_col
def u1(p):
    """seek_col via far7 from a stub. Rows: (K, lad1, lad2, M, H, x, expect, note). M / H as the segment ids
    ($80 = storey 1); expect = col or None (STRANDED $FF)."""
    ST = 0x80
    rows = [
        (0xFF, 6, 22, ST, 0, 10, 6, "no cut: nearest of both, up"),
        (0xFF, 6, 22, ST, 0, 17, 22, "no cut: x nearer LAD2"),
        (0xFF, 6, 22, 0, ST, 10, 6, "no cut: down, nearest"),
        (14, 4, 20, ST, 0, 19, 4, "R4: up into H's left half although LAD2 is nearer"),
        (14, 4, 20, ST, 1, 5, 20, "R4: up into H's right half although LAD1 is nearer"),
        (15, 4, 21, 0, ST, 13, 4, "R4: F2, down my own half (LAD2 is nearer)"),
        (15, 4, 21, 1, ST, 18, 21, "R4: down my own (right) half"),
        (15, 4, 21, 0, 1, 10, 4, "1-hop: down LAD1 (both halves own a ladder)"),
        (14, 5, 0, 0, 1, 10, None, "1-hop: the right half has no ladder -> STRANDED (R6)"),
        (14, 5, 0, 1, ST, 20, None, "M ladderless half, H storey 1 -> STRANDED (R6)"),
        (14, 5, 0, ST, 1, 20, 5, "R5: no ladder into H's half: the nearest of any"),
        (14, 5, 22, ST, 0, 20, 5, "R4: the two-ladder pit room, up into the left half"),
    ]
    ok_all, worst = True, 0
    room = p.rb("CUR_ROOM")
    base = desc_base(room)
    ent = S["P_ENTITIES"] + 1 * S["P_ENT_STRIDE"]
    res_at = S["TMP5"]
    for K, l1, l2, M, H, x, expect, note in rows:
        p.wb(base + S["RD_LAD1"], l1); p.wb(base + S["RD_LAD2"], l2)
        p.wb("ROOM_CUT", K); p.wb("PL_SEG", H)
        p.set_ent(1, X=x)
        pc0 = p.pc()
        ok, ts = p.code([0xDD, 0x21] + w16(ent) + [0x16, M, 0x21] + w16(S["seek_col"]) + [0xCD] + w16(S["far7"]) +
                        [0x7D, 0x32] + w16(res_at), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        got = p.rb(res_at)
        want = 0xFF if expect is None else expect
        good = ok and got == want
        ok_all &= good
        worst = max(worst, ts - 92)                     # minus the stub's own instructions (~92 T)
        if not good:
            print(f"  U1 row FAIL ({note}): K {K} lad {l1},{l2} M {M:#x} H {H:#x} x {x}: got {got:#x} want {want:#x}")
    check(f"U1: seek_col over {len(rows)} (K, ladders, M, H, x) rows: col / STRANDED as §2.3", ok_all)
    print(f"  U1 seek_col worst T (far7 incl.) ~{worst}", flush=True)
    # measured ~1.37k worst (R4 1-hop: two passes over the two ladders, bank 7 is contended, far7 ~0.5k of it); the spec's
    # 0.7k was for R6 uncontended; nearest_ladder was ~0.65k. Only a climber that is in another segment pays it, per turn.
    check("U1: T <= 1.5k (bank 7 contended, far7 incl.)", worst <= 1500, worst)


# ------------------------------------------------------------------------------ U2 cache_player
def u2(p):
    """cache_player + pl_seg3 for the hero's poses. (name, x, y, aidir, K, expect PL_SEG, expect PL_LADDER, expect PL_STOREY)"""
    ST = 0x80
    rows = [
        ("mid up, internal, left", 10, 6, 0xFF, 14, 0, 2, 1),
        ("mid up, internal, right", 20, 6, 0xFF, 14, 1, 2, 1),
        ("mid down, internal", 10, 6, 1, 14, ST, 2, 1),
        ("mid down, internal (no cut)", 10, 6, 1, 0xFF, ST, 2, 1),
        ("up-exit shaft mid-climb (storey 0)", 20, 0xFE, 0xFF, 14, 1, 1, 0),
        ("down-exit shaft mid-climb (storey 1)", 10, 14, 1, 14, ST, 1, 1),
        ("standing storey 0, left", 10, 2, 0, 14, 0, 0, 0),
        ("standing storey 0, right", 15, 2, 0, 14, 1, 0, 0),
        ("standing storey 0, no cut", 28, 2, 0, 0xFF, 0, 0, 0),
        ("standing storey 1", 20, 11, 0, 14, ST, 0, 1),
    ]
    ok_all = True
    for name, x, y, ad, K, e_seg, e_lad, e_sto in rows:
        p.set_ent(0, X=x, Y=y, AIDIR=ad)
        p.wb("ROOM_CUT", K)
        for a in ("PL_SEG", "PL_LADDER", "PL_STOREY"):
            p.wb(a, 0x55)
        pc0 = p.pc()
        ok, _ = p.code([0xCD] + w16(S["cache_player"]) + [0x21] + w16(S["pl_seg3"]) + [0xCD] + w16(S["far3"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        got = (p.rb("PL_SEG"), p.rb("PL_LADDER"), p.rb("PL_STOREY"))
        if not ok or got != (e_seg, e_lad, e_sto):
            ok_all = False
            print(f"  U2 row FAIL ({name}): got seg {got[0]:#x} lad {got[1]} sto {got[2]}; want {e_seg:#x} {e_lad} {e_sto}")
    check(f"U2: cache_player / pl_seg3 PL_SEG / PL_LADDER / PL_STOREY over {len(rows)} hero poses", ok_all)


with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    GL.Proto.snd_mode = 2
    case_k(p)
    assert new_game(p, 2, 0x2A00)
    u1(p)
    u2(p)
    for fn in (case_s1, case_s2, case_s3, case_s4, case_s4b, case_s5, case_s6, case_s7, case_s8, case_s9, case_s9r, case_s10):
        try:
            fn(p)
        except AssertionError as e:
            check(fn.__name__ + ": setup", False, repr(e))
    print(f"ai_seek2: {fails} failed", flush=True)
sys.exit(1 if fails else 0)
