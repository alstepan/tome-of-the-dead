#!/usr/bin/env python3
"""E0 flicker metric: does the raster beam cross a sprite while it is erased?

Single-steps ZEsarUX with breakpoints (same machinery as budget.py) and records,
per tick, the T-state offset since the frame interrupt of: tick start, render
start/end, every sprite erase (render phase 2) and draw (phase 4) incl. its
screen rect.  Offsets are frame-relative from the interrupt that released the
HALT in wait_tick (tick start = frame 0; the 2nd frame of the tick = +70908).

Beam model (128K): 70,908 T/frame, 228 T/line, first display line starts at
FIRST_LINE_T = 14361 T after the interrupt (63 border lines * 228 - 3).
Pixel row y is scanned at FIRST_LINE_T + y*228 (+ f*70908 in frame f).

Absent window of a sprite = [erase start, draw end] (conservative: the first
erased byte to the last redrawn byte).  Flicker event = a sprite whose window
contains the scan time of any pixel row of its erased rect or drawn rect, in
any frame of the tick.  "strict" = window [erase end, draw start] (sprite
completely gone), a lower bound.

Usage: FL=abc python3 tests/flicker.py      (scenarios a b c)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WHICH = os.environ.get("FL", "abc")
sys.argv = [sys.argv[0]] + ["999"]
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT  # noqa: E402
import budget  # noqa: E402

FRAME = 70908
LINE = 228
FIRST_LINE_T = 14361

BP = {
    "tick_work": S["tick_work"],
    "render": S["render"],
    "render_end": S["probe_render_done"],
    "erase": S["erase_rect"],
    "erase_end": S["render.probe_e2_ret"],
    "blit": S["blit_sprite"],
    "blit_end": S["draw_slot.probe_blit_ret"],
    "wait_tick": S["wait_tick"],
}
INV = {}
for k, v in BP.items():
    INV.setdefault(v, []).append(k)


def regs(z):
    r = z.cmd("get-registers")
    d = {}
    for tok in r.replace(",", " ").split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            try:
                d[k] = int(v.strip("$"), 16)
            except ValueError:
                pass
    return d


class Rec:
    def __init__(self, p):
        self.p, self.z = p, p.z
        z = self.z
        z.cmd("enter-cpu-step")
        z.cmd("enable-breakpoints")
        for i, a in enumerate(sorted(INV)):
            z.cmd("set-breakpoint %d PC=%d" % (i + 1, a))
        self.nbp = len(INV)
        self.ticks = []
        while self._stop()[0] != "wait_tick":
            pass

    def _stop(self):
        z = self.z
        z.cmd("run")
        r = regs(z)
        t = int(z.cmd("get-tstates"))             # frame-relative T
        part = int(z.cmd("get-tstates-partial"))
        return INV.get(r["PC"], [None])[0], r, t, part

    def tick(self):
        z = self.z
        while True:
            n, r, t, part = self._stop()
            if n == "tick_work":
                break
        base = t                                   # frame offset at tick start
        z.cmd("reset-tstates-partial")
        ev = dict(start=base, erases=[], draws=[], render=None, rend=None)
        pend = {}
        cur = {}
        while True:
            n, r, t, part = self._stop()
            now = base + part
            if n == "render":
                ev["render"] = now
            elif n == "render_end":
                ev["rend"] = now
            elif n == "erase":
                m = z.read_memory(r["SP"], 2)
                ret = m[0] | (m[1] << 8)
                if ret == S["render.probe_e2_ret"]:
                    row, rows = r["BC"] >> 8, r["DE"] & 0xFF
                    pend = dict(slot=self.p.rb("ANIM_SLOT"), t0=now,
                                y0=row * 8, y1=(row + rows) * 8 - 1)
            elif n == "erase_end":
                if pend:
                    pend["t1"] = now
                    ev["erases"].append(pend)
                    pend = {}
            elif n == "blit":
                fid = self.p.rb("BL_FID")
                fpy = self.p.rb("BL_FPY")
                h = self.p.rb(S["frame_tab"] + fid * S["FT_STRIDE"] + S["FT_H"])
                cur = dict(slot=self.p.rb("ANIM_SLOT"), t0=now, y0=fpy, y1=fpy + h - 1)
            elif n == "blit_end":
                cur["t1"] = now
                ev["draws"].append(cur)
            elif n == "wait_tick":
                ev["end"] = now
                break
        self.ticks.append(ev)
        return ev

    def close(self):
        for i in range(self.nbp):
            self.z.cmd("set-breakpoint %d" % (i + 1))
        self.p.load_breakpoints()


def beam_in(y0, y1, a, b, frames=3):
    for f in range(frames):
        for y in range(max(y0, 0), min(y1, 191) + 1):
            t = FIRST_LINE_T + y * LINE + f * FRAME
            if a <= t <= b:
                return True
    return False


def analyse(ev):
    flick = strict = 0
    for e in ev["erases"]:
        for d in ev["draws"]:
            if d["slot"] != e["slot"]:
                continue
            rows = [(e["y0"], e["y1"]), (d["y0"], d["y1"])]
            if any(beam_in(y0, y1, e["t0"], d["t1"]) for y0, y1 in rows):
                flick += 1
            if any(beam_in(y0, y1, e["t1"], d["t0"]) for y0, y1 in rows):
                strict += 1
            break
    return flick, strict


def run(h, name):
    p = game.T(h)
    p.boot(K_KNIGHT, freeze=0)
    p.isolate()
    p.place(0, 12, 14)
    if name == "a":
        scen = budget.SCENARIOS["heavy"]
        keys = scen[2]
        for slot, x, y, fl in scen[1]:
            p.place(slot, x, y, room=0, flags=fl)
        label = "a: budget heavy fight"
    elif name == "b":
        keys = [("L", 10), ("H", 10)]
        label = "b: hero alone walking"
    else:
        keys = [("L", 10), ("H", 10)]
        for slot, x, y, fl in ((1, 22, 18, budget.HOSTILE), (3, 25, 16, budget.HOSTILE)):
            p.place(slot, x, y, room=0, flags=fl)
        label = "c: hero + rat + goblin walking"
    r = Rec(p)

    def turn(key):
        t0 = p.rw("TURN_COUNTER")
        p.hold(key)
        for i in range(80):
            r.tick()
            if i == 1:
                p.release()
            if p.rw("TURN_COUNTER") != t0 and p.rb("TURN_PHASE") == 0:
                break
        p.release()
        r.tick()

    for key, n in keys:
        for _ in range(n):
            turn(key)
    r.close()
    T = r.ticks
    an = [analyse(e) for e in T]
    fl = sum(a[0] for a in an)
    st = sum(a[1] for a in an)
    dr = sum(len(e["draws"]) for e in T)
    ftk = sum(1 for a in an if a[0])
    rs = [e["render"] for e in T if e["render"] is not None and e["draws"]]
    re_ = [e["rend"] for e in T if e["rend"] is not None and e["draws"]]
    worst = max(e["end"] for e in T)

    def mm(v):
        return "%d/%d/%d" % (min(v), sum(v) // len(v), max(v)) if v else "-"
    print(f"== {label}")
    print(f"ticks={len(T)} (with draws={len(rs)}) sprites_drawn={dr} flicker_events={fl}"
          f" (ticks affected={ftk}) strict={st}")
    print(f"tick start   min/mean/max: {mm([e['start'] for e in T])}")
    print(f"render start min/mean/max (ticks that draw): {mm(rs)}")
    print(f"render end   min/mean/max (ticks that draw): {mm(re_)}")
    print(f"worst tick T={worst}  OVERRUN={p.rw('OVERRUN_COUNT')}", flush=True)


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        for w in WHICH:
            run(h, w)


if __name__ == "__main__":
    main()
