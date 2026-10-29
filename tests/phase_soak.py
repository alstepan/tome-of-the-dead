"""Walk phase-lock soak (docs/conventions.md "Walk cycles"): seeded random play,
both heroes, PROTO + generated starts; PHASE_TRAP and BLIT_MISS must stay 0.
Most telling on -DPHASE_SHIFT=2 (unlocked: a parity break also misses a blit);
the default build (1) checks the trap. Build with -DDEBUG_KIT=0.
Usage: python3 tests/phase_soak.py [turns per run, default 250]"""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL  # noqa: E402
from game_lib import Harness, S, EMU_ARGS  # noqa: E402
from lp import T as Proto, w16  # noqa: E402  (Proto + code(): a level_descend stub)

GS_PLAYING = 2
KEYS = ["L", "L", "L", "H", "H", "H", "K", "J", "WAIT", "SPACE"]
fails = 0
GL.Proto.snd_mode = 2                            # no stinger hold in descents
with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    # (hero, proto, seed, depth): depth > 1 = a generated start, then MASTER_SEED := seed and a
    # level_descend stub to that depth (3F kinds: D4 Spider/Orc/Mummy.., D7 Ogre/DK/Necro..)
    for run, (hero, proto, seed, depth) in enumerate(
            [(0, 1, 1, 1), (1, 1, 2, 1), (0, 0, 3, 1), (1, 0, 4, 1), (0, 0, 5, 1), (1, 0, 6, 1),
             (0, 0, 7, 4), (1, 0, 8, 4), (0, 0, 9, 7), (1, 0, 10, 7)]):
        rnd = random.Random(seed)
        p.proto_start = proto
        p.boot(hero=hero, freeze=0)
        if depth > 1:
            p.wmem(S["MASTER_SEED"], w16(0x1000 + seed))
            pc0 = p.pc()
            ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"])
                           + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            if not ok or p.rb("LVL_DEPTH") != depth:
                fails += 1
                print(f"[FAIL] run {run}: level_descend stub to D{depth} (LVL_DEPTH {p.rb('LVL_DEPTH')})", flush=True)
                continue
            p.release()
            p.settle(4)
        turns = walks = 0
        for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 250):
            if p.rb("GAME_STATE") != GS_PLAYING:
                break
            k = rnd.choice(KEYS)
            if p.turn(k, max_ticks=200):
                turns += 1
                walks += k in "LH"
        tr, bm = p.rb("PHASE_TRAP"), p.rb("BLIT_MISS")
        ok = tr == 0 and bm == 0
        fails += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] run {run} hero {hero} proto {proto} depth {depth}: turns {turns} "
              f"(walk keys {walks}) PHASE_TRAP {tr} BLIT_MISS {bm} state {p.rb('GAME_STATE')} "
              f"CUR_ROOM {p.rb('CUR_ROOM')} TURN_COUNTER {p.rw('TURN_COUNTER')}", flush=True)
print("phase_soak:", "OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
