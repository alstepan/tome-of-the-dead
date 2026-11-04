#!/usr/bin/env python3
"""FLY-CLIMB (user 2026-11-04: "all ghost climbing using their fly animation, and bats"): every
FLYER (Ghost, Poltergeist, Bat, Screech Bat, the Vampire's bat form K_VBAT) that moves VERTICALLY
-- up or down, over a ladder shaft -- draws its own KS_MOVE (fly / float / flap) frames, never a
climb / walk / rest pose. By construction (anim.asm .move: only a NON-flyer's vertical M_MOVE
takes KS_CLIMB; a flyer's M_MOVE is KS_MOVE drawn at the idle phase), so this is the regression
net, not a fix. Seeded generated games, the real level_descend (level_enter pools the level's units):

  F1  FORCED vertical moves (no AI: the body is poked 3 rows up / 3 rows down over the ladder
      shaft in M_MOVE and the engine ticks the 4-px tween, 6 ticks, no turn): every tick of the
      move draws a frame of the kind's fly set (Ghost / Poltergeist: float2 held; Bat / Screech:
      flapup / glide / flapdown; K_VBAT: flapup / glide), both directions; bats show >= 2 frames;
  F2  AI-driven (real WAIT turns, the hero on the flyer's storey): a Ghost / Poltergeist climbing
      from the floor row to its cruising row, a bat jittering up AND down: every tick that moves
      the body in y (diagonals included) draws a fly-set frame; >= 1 up move (>= 1 down for bats);
  F3  PHASE_TRAP / BLIT_MISS / GEN_TRAP / SEQ_TRAP stay 0 (the fly frames are in the level's pool);
  F4  control: a Skeleton (KF_CLIMBER) poked the same way mid-ladder draws its climb pair, so the
      checks above would catch a flyer drawing a climb pose.
Build with -DDEBUG_KIT=0 (or the kit build).  Usage: python3 tests/flyclimb.py [--png DIR]"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, frame_png  # noqa: E402
from lp import T as Proto, w16  # noqa: E402

FID = {k[4:]: v for k, v in S.items() if k.startswith("FID_") and isinstance(v, int)}
NAME = {v: k for k, v in FID.items()}
PNG = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
TF_SOLID, TF_LADDER, TF_FLOOR, TF_HOLE = (S["TF_SOLID"], S["TF_LADDER"], S["TF_FLOOR"], S["TF_HOLE"])
M_MOVE, M_REST = S["M_MOVE"], S["M_REST"]
GHOSTY = {FID["ghost_float2"]}
BATTY = {FID["bat_flapup"], FID["bat_glide"], FID["bat_flapdown"]}
VBATTY = {FID["bat_flapup"], FID["bat_glide"]}
# (kind, depth, fly set, body h, bat?)  tier kinds are pooled on the levels their base lives on
RUNS = [("GHOST", 3, GHOSTY, 4, False), ("GHOST", 7, GHOSTY, 4, False), ("POLTERGEIST", 7, GHOSTY, 4, False),
        ("BAT", 3, BATTY, 2, True), ("SCREECH", 3, BATTY, 2, True), ("VBAT", 6, VBATTY, 2, True),
        ("VBAT", 8, VBATTY, 2, True)]
SEEDS = {3: 0x3F11, 6: 0x3F12, 7: 0x3F13, 8: 0x3F14}
fails = 0


def check(name, ok, got=None):
    global fails
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"])
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < S["PLAY_ROWS"] else TF_SOLID


def standable(f, s, x, w=3, h=6):
    y = stand_y(s, h)
    if not all(f(c, y + h) & TF_FLOOR and not f(c, y + h) & TF_HOLE for c in range(x, x + w)):
        return False
    return all(not f(c, r) & (TF_SOLID | TF_LADDER) for c in range(x, x + w) for r in range(y, y + h))


def fid1(p):
    return p.rb(S["SLOTREC"] + S["SLOTREC_STRIDE"] + S["R_FID"])   # slot 1's desired frame


def nm(fids):
    return sorted(NAME.get(f, f) for f in fids)


def setup(p, depth, seed):
    """A generated D<depth> room with a ladder shaft {c, rows 10..14} and a hero standing cell on storey 1."""
    for attempt in range(8):
        p.proto_start = 0
        p.boot(hero=0, freeze=0)
        p.wmem(S["MASTER_SEED"], w16(seed + 0x100 * attempt))
        pc0 = p.pc()
        ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        if not ok or p.rb("LVL_DEPTH") != depth:
            continue
        p.release()
        p.settle(4)
        f = room_cells(p)
        lad = [c for c in range(2, 28) if all(f(c, r) & TF_LADDER for r in range(10, 15))
               and not any(f(c + dx, r) & TF_SOLID for dx in range(3) for r in range(10, 15))]
        for c in lad:
            hx = next((x for x in list(range(c + 8, 28)) + list(range(c - 8, 0, -1)) if standable(f, 1, x)), None)
            if hx is not None:
                return c, hx
    return None, None


def put(p, sl, kind, x, y, mode=0):
    p.set_ent(sl, KIND=S["K_" + kind], ROOM=p.rb("CUR_ROOM"), FLAGS=1 | 4, HP=200, MAXHP=200, X=x, Y=y,
              PX=8 * x, PY=8 * y, MODE=mode, REACT=0, FLT=0)
    p.wb(S["ST_FLAGS"] + sl, 0)


def forced(p, kind, c, y0, dy, fly):
    """Poke the body dy rows (M_MOVE, PY unchanged) and run the tween with no AI; -> (fids, moved ticks)."""
    seen = []
    p.set_ent(1, Y=y0 + dy, MODE=M_MOVE)
    for _ in range(2 * abs(dy) + 2):
        p.tick()
        e = p.ent(1)
        seen.append((e["MODE"], e["PY"], fid1(p)))
        if e["MODE"] == M_REST:
            break
    return seen


with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    GL.Proto.snd_mode = 2
    for kn, depth, fly, H, bat in RUNS:
        tag = f"{kn} D{depth}"
        c, hx = setup(p, depth, SEEDS[depth])
        if c is None:
            check(f"{tag}: setup (a generated room with a ladder shaft and a hero cell)", False, "none")
            continue
        for sl in range(1, S["P_MAX_ENT"]):
            p.set_ent(sl, FLAGS=0)
        hy = stand_y(1, 6)
        p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0, FLAGS=1 | 2)
        for t in ("PHASE_TRAP", "BLIT_MISS"):
            p.wb(t, 0)
        # ---- F1: forced vertical moves over the shaft, both directions -----------------------
        ymid = 9 + 4                                   # a row the 3-row moves keep inside the band 9..17-H
        for dname, dy in (("up", -3), ("down", 3)):
            y0 = 9 + 8 - H if dy < 0 else 9 + 1        # the moves start at the band's bottom / top
            put(p, 1, kn, c, y0)
            p.settle(1)
            seen = forced(p, kn, c, y0, dy, fly)
            ticks = [(m, py, f) for m, py, f in seen if m == M_MOVE or py != 8 * y0]
            bad = {f for m, py, f in ticks if f not in fly}
            check(f"F1 {tag} {dname}: all {len(ticks)} ticks of the vertical move draw fly frames {nm(fly)}",
                  len(ticks) >= 5 and not bad, (nm(bad), len(ticks)))
            if bat:
                check(f"F1 {tag} {dname}: the flap animation plays (>= 2 distinct frames)",
                      len({f for m, py, f in ticks}) >= 2, nm({f for m, py, f in ticks}))
            if PNG and dy < 0:
                os.makedirs(PNG, exist_ok=True)
                frame_png(p.frame(), os.path.join(PNG, f"flyclimb_{kn.lower()}_d{depth}.png"), 3)
        # ---- F2: AI-driven, the hero on the flyer's storey ----------------------------------
        y0 = 9 + 8 - H
        put(p, 1, kn, c, y0)
        p.wb(S["ST_FLAGS"] + 1, 0)
        p.settle(2)
        bads = set()

        def per_tick(_frame, _hero):
            e = p.ent(1)
            if e["MODE"] == M_MOVE and e["PY"] != 8 * e["Y"]:    # a tick of a move that still has y to go
                f = fid1(p)
                if f not in fly:
                    bads.add(f)
                per_tick.n[e["PY"] > 8 * e["Y"]] += 1            # [1] = up (PY below the target row), [0] = down
        per_tick.n = [0, 0]
        for turn in range(30):
            p.turn("WAIT", per_tick=per_tick, max_ticks=200)
            if p.rb("GAME_STATE") != 2:
                break
        downs, ups = per_tick.n
        check(f"F2 {tag}: AI vertical ticks draw fly frames only ({ups} up / {downs} down ticks)",
              not bads and ups > 0 and (downs > 0 or not bat), (nm(bads), ups, downs))
        traps = (p.rb("PHASE_TRAP"), p.rb("BLIT_MISS"), p.rb("GEN_TRAP"), p.rb("SEQ_TRAP"))
        check(f"F3 {tag}: PHASE_TRAP / BLIT_MISS / GEN_TRAP / SEQ_TRAP 0", traps == (0, 0, 0, 0), traps)
    # ---- F4: control, a climber mid-ladder shows the climb pair --------------------------
    c, hx = setup(p, 3, SEEDS[3])
    if c is None:
        check("F4 control: setup", False, "none")
    else:
        for sl in range(1, S["P_MAX_ENT"]):
            p.set_ent(sl, FLAGS=0)
        y0 = stand_y(1, 6)
        put(p, 1, "SKELETON", c, y0)
        p.settle(1)
        seen = forced(p, "SKELETON", c, y0, -3, None)
        got = {f for m, py, f in seen if m == M_MOVE}
        climb = {FID["skeleton_climb1"], FID["skeleton_climb2"]}
        check("F4 control: a Skeleton's 3-row climb draws only its climb pair", got and got <= climb, nm(got))
print("flyclimb:", "OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
