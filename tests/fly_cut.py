#!/usr/bin/env python3
"""FLY-CUT: a flyer whose storey-0 path to the hero is cut by an L2 mid-room block flies round it
(down its own half's ladder shaft, across storey 1 under the block, up the shaft in the hero's half)
instead of hovering at the block face for ever (AI-SEEK2 Q3 finding; game.md §9.2 "FLY-CUT").

The ai_seek2.py pattern: a seeded generated game on a depth whose level list holds the kind (its frames
are loaded), the room's descriptor overwritten with the case's geometry and rebuilt by the real
build_room (ROOM_MAP, ROOM_CUT, FLY_CUT), every other body cleared, the flyer and the hero poked; the
hero waits. Per turn: no body overlap, no body in a solid tile.

  C<kind>  mid-block lad1 4 / b 16 w 2 / lad2 21; the flyer cruising on storey 0 left half (x 6), the hero
           standing on storey 0 right half (x 26): first contact (vertical overlap, gap <= 1, or the
           hero's HP drops) within the bound; it visits storey 1 on the way. Kinds: Bat, Ghost, Gargoyle
           (awake), Fire Imp, Frost Wraith.
  H1       same room, the hero on storey 1: no detour (the flyer keeps its storey-0 rules, never leaves storey 0)
  P1       wide-pit room (no block): FLY_CUT = $FF; the Ghost flies straight over the pit (contact, never
           leaves storey 0)
  D2       two flyers detouring at once: no overlap, both reach the hero
  D3       the hero crosses halves mid-detour: the flyer re-targets, no stall > 6 turns
  K        FLY_CUT = b - 1 in a mid-block room, $FF in pit / plain rooms
Prints turns-to-contact per kind (the before / after figure of the task). Build with -DDEBUG_KIT=0.
Usage: ZRCP_PORT=n python3 tests/fly_cut.py"""
import os
import sys
import game_lib as GL
from game_lib import Harness, S, EMU_ARGS, stand_y, storey_of, is_standing
from lp import T as Proto, w16

TF_SOLID = S["TF_SOLID"]
ROOMS = S["ROOM_DESC"]
RDS = 16
HERO_H = 6
FLY_CUT = S.get("FLY_CUT")
fails = 0

# kind name -> (S key, depth whose level list holds it)
KINDS = {"BAT": ("K_BAT", 1), "GHOST": ("K_GHOST", 3), "GARGOYLE": ("K_GARGOYLE", 5),
         "IMP": ("K_ALIAS", 4), "WRAITH": ("K_ALIAS", 5)}
BOUND = {"BAT": 50, "GHOST": 50, "GARGOYLE": 50, "IMP": 50, "WRAITH": 100}   # the Wraith acts every 2 turns


def check(name, ok, got=None):
    global fails
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": {got}"), flush=True)


def kwh(p, k):
    return (p.z.read_memory(S["kind_tab"] + S["KT_BW"] + k, 1)[0], p.z.read_memory(S["kind_tab"] + S["KT_BH"] + k, 1)[0])


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"])
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < S["PLAY_ROWS"] else TF_SOLID


def new_game(p, depth, seed):
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


def set_geometry(p, lad1, lad2=0, pit=0, pitw=0, midb=0, midw=0):
    room = p.rb("CUR_ROOM")
    base = ROOMS + room * RDS
    for off in range(RDS):
        if off != S["RD_FLAGS"]:
            p.wb(base + off, 0)
    for k, v in (("RD_LAD1", lad1), ("RD_LAD2", lad2), ("RD_PITCOL", pit), ("L2_PITW", pitw),
                 ("L2_MIDB", midb), ("L2_MIDW", midw)):
        p.wb(base + S[k], v)
    pc0 = p.pc()
    ok, _ = p.code([0x3E, room, 0x26, S["ROOM_MAP"] >> 8, 0xCD] + w16(S["build_room"]), game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    assert ok, "build_room"
    return room


def place(p, room, hero, flyer, kind, awake):
    """hero = (storey, x) standing; flyer = (storey, x) at its cruise row 9s+1."""
    for sl in range(1, S["P_MAX_ENT"]):
        p.set_ent(sl, FLAGS=0)
    fs, fx = flyer
    fy = 9 * fs + 1
    p.set_ent(1, KIND=kind, ROOM=room, FLAGS=1 | 4, HP=200, MAXHP=200, X=fx, Y=fy, PX=8 * fx, PY=8 * fy,
              MODE=0, REACT=0, FLT=0, AIDIR=1, POT=S["RCD_AWAKE"] if awake else 0)
    p.wb(S["ST_FLAGS"] + 1, 0)
    hs, hx = hero
    hy = stand_y(hs, HERO_H)
    p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0, AIDIR=0)
    p.settle(2)


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def run(p, kind, nturns, f):
    """-> (contact turn or None, trace [(fx, fy)], bad)"""
    w, h = kwh(p, kind)
    tr, bad, contact = [], None, None
    hp0 = p.ent(0)["HP"]
    for t in range(nturns + 1):
        if t:
            if p.rb("GAME_STATE") != 2:
                break
            p.turn("WAIT", max_ticks=200)
        m, hero = p.ent(1), p.ent(0)
        tr.append((m["X"], m["Y"]))
        fb, hb = (m["X"], m["Y"], w, h), (hero["X"], hero["Y"], 3, HERO_H)
        if bad is None and overlap(fb, hb):
            bad = (t, "overlap hero", fb, hb)
        if bad is None and any(f(c, r) & TF_SOLID for c in range(fb[0], fb[0] + w) for r in range(max(0, fb[1]), min(fb[1] + h, S["PLAY_ROWS"]))):
            bad = (t, "solid", fb)
        vov = fb[1] < hb[1] + HERO_H and hb[1] < fb[1] + h
        gap = max(hb[0] - (fb[0] + w), fb[0] - (hb[0] + 3))
        if contact is None and t and ((vov and gap <= 1) or hero["HP"] < hp0):
            contact = t
            break
    return contact, tr, bad


def case_c(p, name, results):
    kkey, depth = KINDS[name]
    assert new_game(p, depth, 0x3C00 + depth), "no game"
    k = S[kkey]
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 26), (0, 6), k, name == "GARGOYLE")
    w, h = kwh(p, k)
    c, tr, bad = run(p, k, BOUND[name] + 30, f)
    results[name] = c
    s1 = any(storey_of(y, h) == 1 for _, y in tr)
    print(f"  {name}: contact at turn {c}; path {tr[:: max(1, len(tr) // 12)]}", flush=True)
    check(f"C {name}: no overlap / no body in a solid tile", bad is None, bad)
    check(f"C {name}: reaches the hero round the mid-block within {BOUND[name]} turns", c is not None and c <= BOUND[name], c)
    check(f"C {name}: the detour goes through storey 1", s1, None)


def case_h1(p):
    assert new_game(p, 3, 0x3C21), "no game"
    k = S["K_GHOST"]
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (1, 26), (0, 6), k, False)
    w, h = kwh(p, k)
    _, tr, bad = run(p, k, 20, f)
    check("H1: hero on storey 1: the storey-0 Ghost never leaves storey 0 (no detour)", all(storey_of(y, h) == 0 for _, y in tr), tr)
    check("H1: no overlap / solid", bad is None, bad)


def case_p1(p):
    assert new_game(p, 3, 0x3C31), "no game"
    k = S["K_GHOST"]
    room = set_geometry(p, lad1=4, lad2=24, pit=14, pitw=5)
    f = room_cells(p)
    check("K: FLY_CUT = $FF in a wide-pit room", p.rb("FLY_CUT") == 0xFF, p.rb("FLY_CUT"))
    place(p, room, (0, 28), (0, 6), k, False)
    w, h = kwh(p, k)
    c, tr, bad = run(p, k, 40, f)
    check("P1: the Ghost flies straight over the wide pit (contact <= 25)", c is not None and c <= 25, c)
    check("P1: it never leaves storey 0", all(storey_of(y, h) == 0 for _, y in tr), tr)
    check("P1: no overlap / solid", bad is None, bad)


def case_k(p):
    assert new_game(p, 3, 0x3C41), "no game"
    set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    check("K: FLY_CUT = b - 1 = 15 in a mid-block room", p.rb("FLY_CUT") == 15, p.rb("FLY_CUT"))
    set_geometry(p, lad1=6, lad2=22)
    check("K: FLY_CUT = $FF in a plain room", p.rb("FLY_CUT") == 0xFF, p.rb("FLY_CUT"))


def contact_of(m, w, h, hero):
    vov = m["Y"] < hero["Y"] + HERO_H and hero["Y"] < m["Y"] + h
    gap = max(hero["X"] - (m["X"] + w), m["X"] - (hero["X"] + 3))
    return vov and gap <= 1


def case_d2(p):
    """Two flyers detour at once (same half, both cut off): never overlap each other / the hero / a solid,
    and both reach the hero."""
    assert new_game(p, 3, 0x3C51), "no game"
    k = S["K_GHOST"]
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 28), (0, 6), k, False)
    w, h = kwh(p, k)
    fy = 9 * 0 + 1
    p.set_ent(2, KIND=k, ROOM=room, FLAGS=1 | 4, HP=200, MAXHP=200, X=11, Y=fy, PX=88, PY=8 * fy,
              MODE=0, REACT=0, FLT=0, AIDIR=1, POT=0)
    p.wb(S["ST_FLAGS"] + 2, 0)
    p.settle(2)
    got, bad, trace2 = {1: None, 2: None}, None, []
    for t in range(1, 101):
        if p.rb("GAME_STATE") != 2:
            break
        p.turn("WAIT", max_ticks=200)
        hero, ms = p.ent(0), {1: p.ent(1), 2: p.ent(2)}
        fb = {i: (m["X"], m["Y"], w, h) for i, m in ms.items()}
        if bad is None and overlap(fb[1], fb[2]):
            bad = (t, "flyers overlap", fb)
        for i, b in fb.items():
            if bad is None and any(f(c, r) & TF_SOLID for c in range(b[0], b[0] + w) for r in range(max(0, b[1]), min(b[1] + h, S["PLAY_ROWS"]))):
                bad = (t, "solid", i, b)
            # reached = in contact, or back on storey 0 in the hero's half (past the block: the first one at the hero blocks the way)
            if got[i] is None and (contact_of(ms[i], w, h, hero) or (storey_of(ms[i]["Y"], h) == 0 and ms[i]["X"] >= 18)):
                got[i] = t
        trace2.append((t, ms[1]["X"], ms[1]["Y"], ms[2]["X"], ms[2]["Y"]))
        if all(got.values()):
            break
    print(f"  D2 trace {trace2[::4]}", flush=True)
    print(f"  D2: contact turns {got}", flush=True)
    check("D2: two detouring flyers never overlap each other / a solid", bad is None, bad)
    check("D2: both reach the hero's half within 100 turns", all(got.values()), got)


def case_d3(p):
    """The hero crosses halves mid-detour: the flyer re-targets and does not stall."""
    assert new_game(p, 3, 0x3C61), "no game"
    k = S["K_GHOST"]
    room = set_geometry(p, lad1=4, lad2=21, midb=16, midw=2)
    f = room_cells(p)
    place(p, room, (0, 26), (0, 6), k, False)
    w, h = kwh(p, k)
    moved, tr, bad, c, stall, worst, last = None, [], None, None, 0, 0, None
    for t in range(1, 121):
        if p.rb("GAME_STATE") != 2:
            break
        p.turn("WAIT", max_ticks=200)
        m, hero = p.ent(1), p.ent(0)
        pos = (m["X"], m["Y"])
        tr.append(pos)
        if moved is None and storey_of(m["Y"], h) == 1:
            moved = t               # the detour is under way: the hero walks to the flyer's origin half
            hy = stand_y(0, HERO_H)
            p.set_ent(0, X=3, Y=hy, PX=24, PY=hy)
            last, stall, worst = None, 0, 0
        elif moved is not None:
            stall = stall + 1 if pos == last else 0
            worst = max(worst, stall)
            if c is None and contact_of(m, w, h, p.ent(0)):
                c = t
        last = pos
        fb = (m["X"], m["Y"], w, h)
        if bad is None and any(f(cc, r) & TF_SOLID for cc in range(fb[0], fb[0] + w) for r in range(max(0, fb[1]), min(fb[1] + h, S["PLAY_ROWS"]))):
            bad = (t, "solid", fb)
        if c is not None:
            break
    print(f"  D3: detour at turn {moved}, contact at {c}, worst stall {worst}", flush=True)
    check("D3: the flyer started a detour", moved is not None, tr)
    check("D3: hero crossed halves: contact within 60 turns of the swap", c is not None and moved is not None and c - moved <= 60, (moved, c))
    check("D3: no stall > 6 turns after the swap", worst <= 6, worst)
    check("D3: no solid", bad is None, bad)


with Harness() as hh:
    hh.launch(EMU_ARGS)
    p = Proto(hh)
    GL.Proto.snd_mode = 2
    results = {}
    only = os.environ.get("FLY_CUT_ONLY")
    for name in KINDS:
        if only and name not in only.split(","):
            continue
        try:
            case_c(p, name, results)
        except AssertionError as e:
            check(f"C {name}: setup", False, repr(e))
    fns = [f for f in (case_k, case_h1, case_p1, case_d2, case_d3) if f.__name__[5:] in os.environ.get("FLY_CUT_FN", f.__name__[5:]).split(",")]
    if FLY_CUT is not None and (not only or os.environ.get("FLY_CUT_FN")):
        for fn in fns:
            try:
                fn(p)
            except AssertionError as e:
                check(fn.__name__ + ": setup", False, repr(e))
    print("  turns-to-contact: " + ", ".join(f"{k} {v}" for k, v in results.items()), flush=True)
    print(f"fly_cut: {fails} failed", flush=True)
sys.exit(1 if fails else 0)
