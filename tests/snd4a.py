#!/usr/bin/env python3
"""SND-4a: Level Complete stinger (cue R) on descent; the next level's start is held while it plays.
Release build (DEBUG_KIT=0). Generated start (proto_start 0), level_descend called from the wait_tick
probe by a stub; the driver stops at every ISR (isr.done) and every menu_frame (menu_tick), so each
wait-loop iteration and each music frame is observed.

  A  mode 3 (ALL ON): MS_SHOT with MUS_CUR 4 begins exactly once (one rising edge over the run);
     level_enter waits (>= 1 stinger_wait frame) until the shot ends; then MUS_REQ 7 resumes
     (MUS_CUR 7, MS_LOOP, DONE set); LVL_DEPTH + 1, GS_PLAYING; MUS_SHOT consumed; reports the wait
  S  skip: a key still down from the move does NOT skip; after release a fresh press stops the
     stinger within 3 frames, the room tune restarts (MUS_CUR 7), SND_MODE back to 3
  M  modes 2 (SFX only) and 0 (off): no wait-loop iteration, no shot ever sounds, MUS_SHOT dropped,
     MUS_REQ 7, depth + 1
  W  depth 8 (win): no stinger requested (MUS_SHOT 0, MUS_CUR != 4), GS_WIN
Run: ZRCP_PORT=<port> python3 tests/snd4a.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STUB = S["LOWRAM_END_3B"]
WT, MT, DONE = S["wait_tick"], S["menu_tick"], S["isr.done"]
MUS_ROOM, MUS_LEVEL = 7, 4
MS_SHOT, MS_LOOP, MS_DONE = 2, 1, 0x80
MAXRUN = 3000


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        n = [0]

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] snd4a needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"snd4a: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    def rb(a):
        return p.rb(a)

    def scene(mode, depth=None):
        p.proto_start = 0
        p.boot(K_KNIGHT)
        p.settle(2)
        p.wb("SND_MODE", mode)
        if depth is not None:
            p.wb("LVL_DEPTH", depth)
        p.release()

    def descend(on_wait=None):
        """level_descend from the wait_tick probe. Stops at isr.done / menu_tick / wait_tick.
        on_wait(k) is called at the k-th wait-loop iteration (menu_tick); -> trace of samples."""
        assert p.pc() == WT
        p.wmem(STUB, [0xCD] + w16(S["level_descend"]) + [0xC3] + w16(WT))
        p.z.cmd("set-breakpoint 5 PC=%d" % DONE)
        p.z.cmd("set-register PC=%d" % STUB)
        tr, k = [], 0
        try:
            for _ in range(MAXRUN):
                p.z.cmd("cpu-step")
                p.z.cmd("run %d" % RUN_LIMIT)
                pc = p.pc()
                if pc == WT:
                    return tr
                if pc == MT:
                    k += 1
                    if on_wait:
                        on_wait(k)
                if pc in (MT, DONE):
                    tr.append((pc, k, rb("MUS_STATE"), rb("MUS_CUR"), rb("MUS_SHOT"), rb("SND_MODE")))
            raise RuntimeError("descent did not finish")
        finally:
            p.z.cmd("set-breakpoint 5")

    def edges(tr):
        """Rising MS_SHOT (CUR 4) edges over the ISR samples."""
        e, prev = 0, False
        for pc, k, st, cur, shot, mode in tr:
            if pc != DONE:
                continue
            on = (st & 3) == MS_SHOT and cur == MUS_LEVEL
            e += on and not prev
            prev = on
        return e

    # ---- A: mode 3, no key -------------------------------------------------
    scene(3)
    d0 = rb("LVL_DEPTH")
    tr = descend()
    waits = [t for t in tr if t[0] == MT]
    isrs = [t for t in tr if t[0] == DONE]
    check("A1 stinger started exactly once (one MS_SHOT/MUS_CUR 4 rising edge)", edges(tr) == 1, edges(tr))
    check("A2 the start is held: stinger_wait ran (>= 1 menu_frame) and every wait but the last (the ISR may end it first) saw MS_SHOT / CUR 4",
          len(waits) >= 1 and all((t[2] & 3) == MS_SHOT and t[3] == MUS_LEVEL for t in waits[:-1]), len(waits))
    check("A3 descended + playing, MUS_SHOT consumed, stinger over",
          rb("LVL_DEPTH") == d0 + 1 and rb("GAME_STATE") == S["GS_PLAYING"] and rb("MUS_SHOT") == 0
          and (rb("MUS_STATE") & 3) != MS_SHOT, (rb("LVL_DEPTH"), d0))
    check("A4 room tune requested (MUS_REQ 7)", rb("MUS_REQ") == MUS_ROOM)
    p.z.cmd("set-breakpoint 5 PC=%d" % DONE)
    for _ in range(3):
        p.z.cmd("cpu-step")
        p.z.cmd("run %d" % RUN_LIMIT)
    p.z.cmd("set-breakpoint 5")
    check("A5 after the stinger the room loop plays (MS_LOOP, CUR 7, DONE set)",
          rb("MUS_CUR") == MUS_ROOM and (rb("MUS_STATE") & 3) == MS_LOOP and rb("MUS_STATE") & MS_DONE,
          (rb("MUS_STATE"), rb("MUS_CUR")))
    print(f"[info] A: ISR frames in the descent {len(isrs)}, stinger_wait iterations {len(waits)} "
          f"(= {len(waits) / 50:.2f} s of hold after the generation)", flush=True)

    # ---- S: skip by key ------------------------------------------------------
    scene(3)
    d0 = rb("LVL_DEPTH")
    DOWN = [255, 255, 255, 255, 255, 255, 255, 254]    # SPACE / row 7 bit 0 down (= FIRE)
    UP = [255] * 8
    state = {}

    def keys(k):
        rows = DOWN if (k <= 3 or k >= 8) else UP     # held at entry, released k=4..7, fresh press at 8
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))
        if k in (3, 7):
            state[k] = rb("MUS_STATE") & 3

    p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, DOWN))))   # still held
    tr = descend(keys)
    waits = [t for t in tr if t[0] == MT]
    check("S1 held move key does not skip; released alone does not skip (still MS_SHOT at waits 3 and 7)",
          state.get(3) == MS_SHOT and state.get(7) == MS_SHOT, state)
    check("S2 a fresh press (wait 8) ends the hold within 3 waits", 8 <= len(waits) <= 11, len(waits))
    check("S3 skipped: depth + 1, playing, SND_MODE back to 3, MUS_SHOT 0",
          rb("LVL_DEPTH") == d0 + 1 and rb("SND_MODE") == 3 and rb("MUS_SHOT") == 0
          and rb("GAME_STATE") == S["GS_PLAYING"], (rb("SND_MODE"), rb("LVL_DEPTH")))
    p.z.cmd("set-breakpoint 5 PC=%d" % DONE)
    for _ in range(4):
        p.z.cmd("cpu-step")
        p.z.cmd("run %d" % RUN_LIMIT)
    p.z.cmd("set-breakpoint 5")
    check("S4 room loop restarted after the skip (MS_LOOP, CUR 7)",
          rb("MUS_CUR") == MUS_ROOM and (rb("MUS_STATE") & 3) == MS_LOOP, (rb("MUS_STATE"), rb("MUS_CUR")))
    p.release()

    # ---- K: Kempston FIRE skips (GS_TRANSITION forces STICK 0; stinger_wait reads the port) ----
    scene(3)
    p.wb("JOY_MODE", 1)                                 # JM_KEMPSTON; the mirror stands in for IN $1F
    p.wb("JOY_MIRROR", 0)
    d0 = rb("LVL_DEPTH")
    ks = {}

    def kemp(k):
        p.wb("JOY_MIRROR", (1 << S["JOY_F_BIT"]) if k >= 6 else 0)
        if k == 5:
            ks[5] = rb("MUS_STATE") & 3

    tr = descend(kemp)
    waits = [t for t in tr if t[0] == MT]
    check("K1 Kempston FIRE (after a release) ends the hold within 3 waits; no skip before it",
          ks.get(5) == MS_SHOT and 6 <= len(waits) <= 9, (ks, len(waits)))
    check("K2 skipped: depth + 1, SND_MODE 3, playing", rb("LVL_DEPTH") == d0 + 1 and rb("SND_MODE") == 3
          and rb("GAME_STATE") == S["GS_PLAYING"], (rb("LVL_DEPTH"), rb("SND_MODE")))
    p.wb("JOY_MIRROR", 0)

    # ---- M: SFX only / off ----------------------------------------------------
    for mode in (2, 0):
        scene(mode)
        d0 = rb("LVL_DEPTH")
        tr = descend()
        waits = [t for t in tr if t[0] == MT]
        check(f"M{mode}a mode {mode}: no wait-loop iteration, no shot ever sounds",
              not waits and edges(tr) == 0 and all((t[2] & 3) != MS_SHOT for t in tr), len(waits))
        check(f"M{mode}b mode {mode}: depth + 1, MUS_SHOT dropped, MUS_REQ 7, playing",
              rb("LVL_DEPTH") == d0 + 1 and rb("MUS_SHOT") == 0 and rb("MUS_REQ") == MUS_ROOM
              and rb("GAME_STATE") == S["GS_PLAYING"], (rb("LVL_DEPTH"), rb("MUS_SHOT")))

    # ---- W: win path -----------------------------------------------------------
    scene(3, depth=8)
    tr = descend()
    check("W1 D8 descent = win: GS_WIN, no stinger requested, no wait",
          rb("GAME_STATE") == S["GS_WIN"] and rb("MUS_SHOT") == 0 and edges(tr) == 0
          and not [t for t in tr if t[0] == MT] and rb("MUS_CUR") != MUS_LEVEL,
          (rb("GAME_STATE"), rb("MUS_SHOT")))


if __name__ == "__main__":
    sys.exit(main())
