#!/usr/bin/env python3
"""3F-T13bc: the new climbers (user 2026-10-29: Orc / Necro / Mummy climb on the
shared humanoid climb pair climb_h1 / climb_h2, ART3 A1; Archer / Sniper on the Skeleton's own). Seeded generated games, the real
level_descend (level_enter pools the level's units), the room's monsters cleared but one, which
is re-kinded and put on the bottom storey (1) away from a ladder {c, 1}; the hero waits on the
top storey (0). The AI (turn3.asm .seek, KF_CLIMBER only) must take it up the ladder.

  C1  the walker reaches the hero's storey within MAX_TURNS turns (it climbed);
  C2  every frame it shows mid-ladder is the kind's KS_CLIMB art (climb_h1 / climb_h2 for the
      3F climbers, skeleton_climb1/2 for the Skeleton control run), both frames seen;
  C3  every other frame it shows is one of the kind's own frames (walk / rest), or the climb
      pair while it stands at a ladder end (the climb starts / ends at a standing row);
  C4  PHASE_TRAP, BLIT_MISS, GEN_TRAP, SEQ_TRAP stay 0 (the climb pair is pooled on that level,
      the cycle is drawn cell-aligned: STA|SYM, docs/conventions.md "Walk cycles");
  C5  a NON-climber (Vampire on D8) put the same way never changes storey.
Scenarios (hero, depth, kind): Orc + Archer + Sniper on D4, Orc + Necro on D7, Archer + Sniper + Skeleton + Mummy on
D5 (Archer / Sniper / Skeleton: the SKELETON's climb pair skeleton_climb1/2, fix/archer-climb;
Orc / Necro / Mummy: the shared humanoid pair). --png DIR saves a mid-climb screen per run.
Build with -DDEBUG_KIT=0.  Usage: python3 tests/climb3f.py [--png DIR]"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, storey_of, frame_png  # noqa: E402
from lp import T as Proto, w16  # noqa: E402

MAX_TURNS = 40
STRIDE = S["P_ENT_STRIDE"]
FID = {k[4:]: v for k, v in S.items() if k.startswith("FID_") and isinstance(v, int)}
PNG = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
TF_SOLID, TF_LADDER, TF_FLOOR, TF_HOLE = (S["TF_SOLID"], S["TF_LADDER"], S["TF_FLOOR"], S["TF_HOLE"])
H6 = 6                                           # every scenario body is 24x48 (BW 3, BH 6)
CLIMB_H = {FID["climb_h1"], FID["climb_h2"]}
CLIMB_SK = {FID["skeleton_climb1"], FID["skeleton_climb2"]}
OWN = {
    "ORC": {FID[n] for n in ("orc_walk1", "orc_walk2")},
    "NECRO": {FID[n] for n in ("necro_walk1", "necro_walk2", "necro_walk3")},
    "ARCHER": {FID[n] for n in ("skeleton_walk1", "skeleton_walk2", "skeleton_walk3", "skeleton_walk4")},
    "SNIPER": {FID[n] for n in ("skeleton_walk1", "skeleton_walk2", "skeleton_walk3", "skeleton_walk4")},
    "SKELETON": {FID[n] for n in ("skeleton_walk1", "skeleton_walk2", "skeleton_walk3", "skeleton_walk4")},
    "VAMPIRE": {FID[n] for n in ("necro_walk1", "necro_walk2", "necro_walk3")},
    "MUMMY": {FID[n] for n in ("mummy_walk1", "mummy_walk2", "mummy_walk3", "mummy_walk4")},
}
# (hero, depth, kind name, climber?, master seed)
RUNS = [(0, 4, "ORC", True, 0x4101), (1, 4, "ARCHER", True, 0x4102), (0, 7, "NECRO", True, 0x7101),
        (1, 7, "ORC", True, 0x7102), (0, 5, "ARCHER", True, 0x5101), (1, 5, "SKELETON", True, 0x5102),
        (0, 8, "VAMPIRE", False, 0x8101), (0, 5, "MUMMY", True, 0x5103), (1, 5, "MUMMY", True, 0x5104),
        # fix/archer-climb: Archer / Sniper (the Skeleton body) climb on the SKELETON's own pair
        (0, 4, "ARCHER", True, 0x4103), (0, 4, "SNIPER", True, 0x4104), (1, 5, "SNIPER", True, 0x5105)]
fails = 0


def check(name, ok, got=None):
    global fails
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


def room_cells(p):
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"])
    return lambda c, r: tf[m[r * 32 + c] & 63] if 0 <= c < 32 and 0 <= r < S["PLAY_ROWS"] else TF_SOLID


def standable(f, s, x):
    """A 3-col body standing on storey s at col x: floor under it, nothing solid / ladder in it."""
    y = stand_y(s, H6)
    if not all(f(c, y + H6) & TF_FLOOR and not f(c, y + H6) & TF_HOLE for c in range(x, x + 3)):
        return False
    return all(not f(c, r) & (TF_SOLID | TF_LADDER) for c in range(x, x + 3) for r in range(y, y + H6))


with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    GL.Proto.snd_mode = 2
    for hero, depth, kn, climber, seed in RUNS:
        tag = f"{kn} D{depth} hero {hero}"
        kind = S["K_" + kn]
        done = False
        for attempt in range(6):                     # find a start room with a usable ladder {c, 1}
            p.proto_start = 0
            p.boot(hero=hero, freeze=0)
            p.wmem(S["MASTER_SEED"], w16(seed + 0x100 * attempt))   # the descend generates from it
            pc0 = p.pc()
            ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            if not ok or p.rb("LVL_DEPTH") != depth:
                continue
            p.release()
            p.settle(4)
            f = room_cells(p)
            lad = [c for c in range(1, 31) if all(f(c, r) & TF_LADDER for r in range(10, 15))]
            if not lad:
                continue
            c = lad[0]
            mx = next((x for x in list(range(c + 6, 28)) + list(range(c - 8, 0, -1)) if standable(f, 1, x)), None)
            hx = next((x for x in list(range(c - 8, 0, -1)) + list(range(c + 8, 28)) if standable(f, 0, x)), None)
            if mx is None or hx is None:
                continue
            done = True
            break
        if not done:
            check(f"{tag}: setup (a generated room with a ladder and two standing cells)", False, "none")
            continue
        room = p.rb("CUR_ROOM")
        for sl in range(1, S["P_MAX_ENT"]):          # one walker: the others out of the room
            p.set_ent(sl, FLAGS=0)
        my, hy = stand_y(1, H6), stand_y(0, H6)
        p.set_ent(1, KIND=kind, ROOM=room, FLAGS=1 | 4, HP=200, MAXHP=200, X=mx, Y=my, PX=8 * mx, PY=8 * my,
                  MODE=0, REACT=0, FLT=0)
        p.wb(S["ST_FLAGS"] + 1, 0)
        p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=hy, PX=8 * hx, PY=8 * hy, MODE=0)
        for t in ("PHASE_TRAP", "BLIT_MISS"):
            p.wb(t, 0)
        p.settle(2)
        seen = []                                    # (y, fid) of slot 1 per tick

        def per_tick(_frame, _hero):
            e = p.ent(1)
            fid = p.rb(S["SLOTREC"] + S["SLOTREC_STRIDE"] + S["R_FID"])   # slot 1's desired frame
            seen.append((e["Y"], e["PY"], fid))
            if PNG and climber and (e["Y"] + H6) % 9 in (3, 4) and not per_tick.shot:
                if fid in CLIMB_H | CLIMB_SK:
                    os.makedirs(PNG, exist_ok=True)
                    frame_png(p.frame(), os.path.join(PNG, f"climb_{kn.lower()}_d{depth}.png"), 3)
                    per_tick.shot = 1
        per_tick.shot = 0
        turns = 0
        while turns < MAX_TURNS and p.rb("GAME_STATE") == 2:
            p.turn("WAIT", per_tick=per_tick, max_ticks=200)
            turns += 1
            e = p.ent(1)
            if storey_of(e["Y"], H6) == 0 and (e["Y"] + H6) % 9 == 8:
                break
        e = p.ent(1)
        top = storey_of(e["Y"], H6) == 0
        mid = {fid for y, py, fid in seen if (y + H6) % 9 != 8 and fid != 0xFF}
        rest = {fid for y, py, fid in seen if (y + H6) % 9 == 8 and fid != 0xFF}
        want_climb = CLIMB_SK if kn in ("SKELETON", "ARCHER", "SNIPER") else CLIMB_H
        traps = (p.rb("PHASE_TRAP"), p.rb("BLIT_MISS"), p.rb("GEN_TRAP"), p.rb("SEQ_TRAP"))
        if climber:
            check(f"C1 {tag}: climbed to the hero's storey in {turns} turns (ladder col {c}, from x {mx})",
                  top, (e["X"], e["Y"], turns))
            check(f"C2 {tag}: mid-ladder frames == the climb pair, both seen",
                  mid == want_climb, sorted(mid))
            check(f"C3 {tag}: standing frames are its own walk / rest frames (or the climb pair at a ladder end)",
                  rest <= OWN[kn] | want_climb, sorted(rest - OWN[kn] - want_climb))
        else:
            check(f"C5 {tag}: a non-climber never leaves its storey ({turns} turns)",
                  not top and not mid, (e["X"], e["Y"], sorted(mid)))
        check(f"C4 {tag}: PHASE_TRAP / BLIT_MISS / GEN_TRAP / SEQ_TRAP 0", traps == (0, 0, 0, 0), traps)
print("climb3f:", "OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
