#!/usr/bin/env python3
"""PROTO per-tick budget measurement (prototype §5.5, risk R-1).

Runs ZEsarUX in cpu-step mode with breakpoints on tick_work (tick start) and
wait_tick (work done) and reads the T-state counter at each, so every 25 Hz
tick's real cost (ULA contention included, as emulated) is measured exactly.
Budget = 2 frames = 141,816 T (128K: 70,908 T/frame).

Scenario (worst case asked for by the task): room A, Knight + 4 monsters on
screen (skeleton adjacent, rat, goblin, bat) — the Knight's 40-px WIND-UP/SLASH/
FOLLOW against the skeleton while everything else moves/attacks, then a run of
walking turns. Reports max / mean tick and the per-phase split of the worst tick.

Usage: python3 tests/proto_budget.py      (exit 1 if any tick > budget)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0]] + ["999"]           # keep proto.py's item filter inert
import proto  # noqa: E402
from proto_lib import Harness, S, EMU_ARGS, K_KNIGHT, EF_ACTIVE, EF_HOSTILE, EF_LEFT  # noqa: E402

BUDGET = 2 * 70908
PHASES = ["tick_work", "read_turn_input", "anim_tick", "render", "wait_tick"]
if os.environ.get("PROTO_PROFILE"):                # finer split for optimisation work
    PHASES = ["tick_work", "read_turn_input", "try_player_turn", "resolve_monsters",
              "materialise", "anim_tick", "render", "render.nopend", "render.e2done",
              "render.e3done", "render.drdone", "draw_zap", "wait_tick"]
    PHASES += [n for n in os.environ["PROTO_PROFILE"].split(",") if n in S]


RETURNS = {}


class Stepper:
    def __init__(self, p):
        self.p, self.z = p, p.z
        self.ticks = []                       # (total, {phase: T})
        z = self.z
        z.cmd("enter-cpu-step")
        z.cmd("enable-breakpoints")
        for i, n in enumerate(PHASES):
            z.cmd("set-breakpoint %d PC=%d" % (i + 1, S[n]))
        self.inv = {S[n]: n for n in PHASES}
        self._to("wait_tick")

    def _run(self):
        self.z.cmd("run")
        pc = int(self.z.cmd("get-registers")[3:7], 16)
        return self.inv.get(pc), int(self.z.cmd("get-tstates-partial"))

    def _to(self, name):
        while True:
            n, _ = self._run()
            if n == name:
                return

    def tick(self):
        """Advance one tick; record its work (tick_work -> wait_tick)."""
        self._to("tick_work")
        self.z.cmd("reset-tstates-partial")
        split, last, prev = {}, "tick_work", 0
        while True:
            n, v = self._run()
            split[last] = split.get(last, 0) + v - prev
            prev = v
            if n in RETURNS:                  # returning into a phase: credit it
                last = RETURNS[n]
            else:
                last = n
            if n == "wait_tick":
                break
        self.ticks.append((prev, split))
        return prev

    def turn(self, *keys, max_ticks=80):
        t0 = self.p.rw("TURN_COUNTER")
        self.p.hold(*keys)
        for i in range(max_ticks):
            self.tick()
            if i == 1:
                self.p.release()
            if self.p.rw("TURN_COUNTER") != t0 and self.p.rb("TURN_PHASE") == 0:
                break
        self.p.release()
        self.tick()

    def close(self):
        for i in range(len(PHASES)):
            self.z.cmd("set-breakpoint %d" % (i + 1))    # cleared, not just disabled
        self.p.load_breakpoints()


HOSTILE = EF_ACTIVE | EF_HOSTILE | EF_LEFT
RIGHT = EF_ACTIVE | EF_HOSTILE
KEYS = [("L", 6), ("H", 4), ("SPACE", 4)]        # slash the skeleton, walk away, wait
# Gate: "mix" must keep every tick within the 2-frame budget. "heavy" (review
# A1: hero + 2 skeletons + goblin + ghost) is REPORTED only (~109% today; the
# renderer optimisation is deferred by the user, 2026-09-25).
GATED = ("mix",)
SCENARIOS = {
    # hero + 4 monsters in A (cap), all visible, all close enough to act
    "mix": ("knight + skeleton, rat, goblin, bat", [
        (5, 15, 14, HOSTILE),                     # skeleton adjacent (gap 0)
        (1, 22, 18, HOSTILE),                     # rat walking in
        (3, 25, 16, HOSTILE),                     # goblin walking in
        (4, 8, 15, HOSTILE)], KEYS),              # bat, storey-2 band
    # review A1 worst mix: 2 skeletons (both 40-px attacks), goblin, ghost
    "heavy": ("knight + 2 skeletons, goblin, ghost", [
        (5, 15, 14, HOSTILE),                     # skeleton C right, gap 0
        (7, 8, 14, RIGHT),                        # skeleton D left, gap 1
        (3, 20, 16, HOSTILE),                     # goblin
        (6, 4, 15, RIGHT)], KEYS),                # ghost, storey-2 band
}


def run_scenario(h, scen):
    name, placements, keys = scen
    p = proto.T(h)
    p.boot(K_KNIGHT, freeze=0)
    p.isolate()
    p.place(0, 12, 14)
    for slot, x, y, flags in placements:
        p.place(slot, x, y, room=0, flags=flags)
    st = Stepper(p)
    for key, n in keys:
        for _ in range(n):
            st.turn(key)
    st.close()
    totals = [t for t, _ in st.ticks]
    worst = max(st.ticks, key=lambda x: x[0])
    over = [t for t in totals if t > BUDGET]
    ovc = p.rw("OVERRUN_COUNT")
    print(f"== {name}")
    print(f"ticks measured : {len(totals)}")
    print(f"max tick       : {worst[0]} T  ({worst[0] / BUDGET * 100:.1f}% of {BUDGET})")
    print(f"mean tick      : {sum(totals) // len(totals)} T")
    print(f"worst split    : " + ", ".join(f"{k}={v}" for k, v in worst[1].items()))
    print(f"ticks > budget : {len(over)}")
    print(f"OVERRUN_COUNT  : {ovc}  BLIT_MISS: {p.rb('BLIT_MISS')}", flush=True)
    return st, over


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        for key in ("mix", "heavy"):
            _, bad = run_scenario(h, SCENARIOS[key])
            if bad and key in GATED:
                fails.append(key)
            elif bad:
                print(f"[info] {key}: {len(bad)} ticks over budget (reported, not gated)")
    print(f"[{'FAIL' if fails else 'PASS'}] budget gate (every tick <= budget in"
          f" {', '.join(GATED)}): {fails or 'ok'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
