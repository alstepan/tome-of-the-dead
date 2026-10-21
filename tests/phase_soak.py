"""Walk phase-lock soak (docs/conventions.md "Walk cycles"): seeded random play,
both heroes, PROTO + generated starts; PHASE_TRAP and BLIT_MISS must stay 0.
Most telling on -DPHASE_SHIFT=2 (unlocked: a parity break also misses a blit);
the default build (1) checks the trap. Build with -DDEBUG_KIT=0.
Usage: python3 tests/phase_soak.py [turns per run, default 250]"""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_lib import Harness, Proto, S, EMU_ARGS  # noqa: E402

GS_PLAYING = 2
KEYS = ["L", "L", "L", "H", "H", "H", "K", "J", "WAIT", "SPACE"]
fails = 0
with Harness() as h:
    h.launch(EMU_ARGS)
    p = Proto(h)
    for run, (hero, proto, seed) in enumerate([(0, 1, 1), (1, 1, 2), (0, 0, 3), (1, 0, 4), (0, 0, 5), (1, 0, 6)]):
        rnd = random.Random(seed)
        p.proto_start = proto
        p.boot(hero=hero, freeze=0)
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
        print(f"[{'PASS' if ok else 'FAIL'}] run {run} hero {hero} proto {proto}: turns {turns} "
              f"(walk keys {walks}) PHASE_TRAP {tr} BLIT_MISS {bm} state {p.rb('GAME_STATE')} "
              f"CUR_ROOM {p.rb('CUR_ROOM')} TURN_COUNTER {p.rw('TURN_COUNTER')}", flush=True)
print("phase_soak:", "OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
