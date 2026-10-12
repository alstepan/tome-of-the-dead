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

A7 double buffer (option A): render composes in bank 5 while the ULA shows
bank 7, so an erase->draw window is only an event if it happens on the
DISPLAYED bank ($7FFD bit 3 = 0 at the erase; PORT_7FFD_SHADOW is read there).
"flicker_events" = sprite-absent events on the displayed bank (target 0).
Tear events (reported separately): present copies changed cells bank 5 -> 7
row by row; a row tears if the beam scans any of its 8 pixel lines while the
row is being copied ([present.probe_row, present.probe_row_end]); split into
playfield rows (0-20, sprites) and HUD rows (21-23, text). Conservative: the
whole char row counts even if the beam is in another column.
Late rows (A7 review): a row whose copy STARTS after the beam already scanned
all its 8 lines in that frame shows the OLD content for the whole frame; if
the same present also copied a row before the beam reached it (an "early"
row: NEW content in that frame), the frame mixes old and new rows (a sprite
spanning both is split across char rows for one frame). Reported as
late_rows (all) / split (late rows of presents that also have an early row
in the same frame). Gated: any split late row fails the run (exit 1).

Usage: FL=abcd python3 tests/flicker.py     (scenarios a b c d; d = D3-5 FX)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WHICH = os.environ.get("FL", "abcd")
sys.argv = [sys.argv[0]] + ["999"]
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD  # noqa: E402
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
    "fx_blit_end": S["fx_blit.probe_ret"],       # D3-5: FX tracks (ANIM_SLOT 16 + track)
    "wait_tick": S["wait_tick"],
}
if "probe_presented" in S:                         # A7: bank 7 == bank 5 here
    BP["presented"] = S["probe_presented"]
if "present.probe_row" in S:                       # A7 builds
    BP["prow"] = S["present.probe_row"]
    BP["prow_end"] = S["present.probe_row_end"]
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
        ev = dict(start=base, erases=[], draws=[], render=None, rend=None, rows=[])
        prow = None
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
                if ret in (S["render.probe_e2_ret"], S["fx_trk_erase.probe_ret"]):
                    row, rows = r["BC"] >> 8, r["DE"] & 0xFF
                    pend = dict(slot=self.p.rb("ANIM_SLOT"), t0=now,
                                y0=row * 8, y1=(row + rows) * 8 - 1,
                                shown=not self.p.rb("PORT_7FFD_SHADOW") & 0x08)
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
            elif n in ("blit_end", "fx_blit_end"):
                cur["t1"] = now
                ev["draws"].append(cur)
            elif n == "prow":
                prow = dict(row=r["AF"] >> 8, t0=now)
            elif n == "prow_end":
                if prow:
                    prow["t1"] = now
                    ev["rows"].append(prow)
                    prow = None
            elif n == "presented":
                ev["mismatch"] = self.banks_differ()
            elif n == "wait_tick":
                ev["end"] = now
                break
        self.ticks.append(ev)
        return ev

    def banks_differ(self):
        """A7 invariant right after the tick-start present (probe_presented):
        displayed bank 7 == composed bank 5.
        Returns the number of differing screen bytes (0 if bank 5 is shown)."""
        if not self.p.rb("PORT_7FFD_SHADOW") & 0x08:
            return 0
        z = self.z
        z.cmd("set-memory-zone 0")
        try:
            b5 = z.read_memory(5 * 16384, 6912)
            b7 = z.read_memory(7 * 16384, 6912)
        finally:
            z.cmd("set-memory-zone -1")
        return sum(1 for a, b in zip(b5, b7) if a != b)

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
        if not e.get("shown", True):
            continue                               # composed off-screen (bank 7 shown)
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


def tears(ev):
    """(playfield rows, HUD rows) copied by present while the beam scanned them."""
    pf = hud = 0
    for w in ev["rows"]:
        y0 = w["row"] * 8
        if beam_in(y0, y0 + 7, w["t0"], w["t1"]):
            if w["row"] < 21:
                pf += 1
            else:
                hud += 1
    return pf, hud


def late_rows(ev):
    """(late rows, late rows of a split present): see the module doc."""
    late, early = [], []
    for w in ev["rows"]:
        y0 = w["row"] * 8
        f = w["t0"] // FRAME
        if FIRST_LINE_T + (y0 + 7) * LINE + f * FRAME < w["t0"]:
            late.append(f)
        elif w["t1"] < FIRST_LINE_T + y0 * LINE + f * FRAME:
            early.append(f)
    return len(late), sum(1 for f in late if f in early)


def run(h, name):
    p = game.T(h)
    p.boot(K_WIZARD if name == "d" else K_KNIGHT, freeze=0)
    p.isolate()
    p.place(0, 12, budget.HERO_Y)
    if name == "a":
        scen = budget.SCENARIOS["heavy"]
        keys = scen[2]
        for slot, x, y, fl in scen[1]:
            p.place(slot, x, y, room=0, flags=fl)
        label = "a: budget heavy fight"
    elif name == "b":
        keys = [("L", 10), ("H", 10)]
        label = "b: hero alone walking"
    elif name == "d":                             # D3-5: FX tracks over bodies
        keys = [("WAIT", 3), ("L", 2), ("H", 3)]
        for slot, x, y, fl in ((1, 22, budget.stand_y(1, 2), budget.HOSTILE),
                               (3, 25, budget.stand_y(1, 4), budget.HOSTILE)):
            p.place(slot, x, y, room=0, flags=fl)
        label = "d: mage + rat + goblin, Lightning + 2 flashes every turn"
    else:
        keys = [("L", 10), ("H", 10)]
        for slot, x, y, fl in ((1, 22, budget.stand_y(1, 2), budget.HOSTILE),
                               (3, 25, budget.stand_y(1, 4), budget.HOSTILE)):
            p.place(slot, x, y, room=0, flags=fl)
        label = "c: hero + rat + goblin walking"
    if budget.DECOR:                              # B3B-10: synthetic full decor list
        budget.inject_decor(p)                    # in room A (BUDGET_DECOR=0: off)
        label += " + decor"
    r = Rec(p)
    fxn = [0, 0]

    def rtick():
        ev = r.tick()
        if name == "d" and p.rb("TURN_PHASE") == 1 and fxn[1] != p.rw("TURN_COUNTER") + 1:
            fxn[1] = p.rw("TURN_COUNTER") + 1
            fxn[0] += sum(budget.fx_cast(p))
        return ev

    def turn(key):
        keys, fire = p._prep((key,), step=rtick)    # C3-8a: turn-around tap (0 turns)
        t0 = p.rw("TURN_COUNTER")
        p.hold(*keys)
        if fire:
            rtick()
            p.release()
        for i in range(80):
            rtick()
            if i == 1:
                p.release()
            if p.rw("TURN_COUNTER") != t0 and p.rb("TURN_PHASE") == 0:
                break
            if i >= 6 and p.rw("TURN_COUNTER") == t0 and p.rb("TURN_PHASE") == 0:
                break
        p.release()
        rtick()

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
    tr = [tears(e) for e in T]
    nrows = sum(len(e["rows"]) for e in T)
    shown = sum(1 for e in T for x in e["erases"] if x.get("shown", True))
    lr = [late_rows(e) for e in T]
    nlate, nsplit = sum(a for a, _ in lr), sum(b for _, b in lr)

    def mm(v):
        return "%d/%d/%d" % (min(v), sum(v) // len(v), max(v)) if v else "-"
    print(f"== {label}")
    print(f"ticks={len(T)} (with draws={len(rs)}) sprites_drawn={dr} flicker_events={fl}"
          f" (ticks affected={ftk}) strict={st}")
    print(f"erases on the displayed bank={shown}; present rows copied={nrows}"
          f" tear_events playfield={sum(a for a, _ in tr)} hud={sum(b for _, b in tr)}"
          f" (ticks affected={sum(1 for a, b in tr if a or b)})")
    print(f"late_rows={nlate} split={nsplit}"
          f" (ticks affected={sum(1 for a, _ in lr if a)})")
    ps = [w["t0"] for e in T for w in e["rows"]]
    pe = [w["t1"] for e in T for w in e["rows"]]
    print(f"present row start min/mean/max: {mm(ps)}  end: {mm(pe)}")
    mis = [e.get("mismatch", 0) for e in T]
    print(f"bank7 != bank5 after the tick-start present: {sum(1 for m in mis if m)} ticks"
          f" ({sum(mis)} bytes)")
    print(f"tick start   min/mean/max: {mm([e['start'] for e in T])}")
    print(f"render start min/mean/max (ticks that draw): {mm(rs)}")
    print(f"render end   min/mean/max (ticks that draw): {mm(re_)}")
    print(f"worst tick T={worst}  OVERRUN={p.rw('OVERRUN_COUNT')}"
          + (f"  fx_start accepted={fxn[0]}" if name == "d" else ""), flush=True)
    return nsplit


def main():
    split = 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        for w in WHICH:
            split += run(h, w)
    if split:
        print(f"[FAIL] flicker: {split} split late rows (present fell behind the beam)")
        sys.exit(1)


if __name__ == "__main__":
    main()
