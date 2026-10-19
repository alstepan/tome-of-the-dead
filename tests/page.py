#!/usr/bin/env python3
"""3E-T2 bag page spike (src/lowram.asm page_run, src/menu1.asm page_ovl /
page_post, src/page_ovl.asm; docs/memory-map.md "Overlays", the page window).
Release build (DEBUG_KIT=0), real play.

  P1  I opens the page: PAGE_OPEN, SND_HOLD set (mode bits kept), bank 5 shown,
      the band (rows PAGE_BAND_ROW..23) all attr 0, the band bitmap ==
      build/ovl/page.bin (round trip of the bank-1 stream), screen 2 == the
      screen before (the backup); open / close cost in T and frames
  P2  keys inside the page do not leak: slot key, S, ENTER held, Q / A / O / P,
      DOWN held -> no turn, SEL_SLOT / SND_MODE / ICON_MODE / hero unchanged, page up
  P3  closing with a direction held: the hero does not move (EXIT_LOCK) while it is
      held, nor on its release; a fresh tap afterwards works
  P4  20 open / close cycles (I / BAG icon via 9 + ENTER / FIRE tap / ICON MODE FIRE;
      closed by FIRE / BREAK / ENTER / I; sound modes 3 / 2 / 0): each time the
      displayed AND composed screens == before, no turn, SND_HOLD / PAGE_OPEN clear,
      mode kept, ICON MODE kept, displayed == composed
  P5  review fixes: BAG selected + I and ENTER in the same tick -> one open only;
      closing with ENTER / I never re-opens nor uses the icon; no turn; a held hero
      (STS_HOLD): I opens nothing (INTENT dropped on the turn-intent path)
Run: ZRCP_PORT=<port> python3 tests/page.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, SCREEN_FRAME_LEN  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
HOLD = 0x80
BAND = S["PAGE_BAND_ROW"]
CLOSERS = (("FIRE",), ("CAPS", "SPACE"), ("ENTER",), ("I",))


def run(p, check):
    REPO = HERE.parent
    p.boot(K_KNIGHT)
    p.wb("INPUT_REPEAT", 1)
    p.settle(4)
    tc = lambda: p.rw("TURN_COUNTER")          # noqa: E731
    hero = lambda: p.ent(0)                     # noqa: E731
    shown5 = lambda: not (p.rb("PORT_7FFD_SHADOW") & 0x08)   # noqa: E731

    # ---- P1: open with I, measured ------------------------------------------
    before, comp0 = p.frame(), p.composed_frame()
    check("P1 settled: displayed == composed before", before == comp0)
    z = p.z
    z.cmd("set-breakpoint 5 PC=%d" % S["page_run"])
    z.cmd("set-breakpoint 6 PC=%d" % S["PAGE_ORG"])
    z.cmd("set-breakpoint 7 PC=%d" % S["page_run.closed"])
    z.cmd("set-breakpoint 8 PC=%d" % S["page_run.post"])
    p.extra_probes = {S["page_run"], S["PAGE_ORG"], S["page_run.closed"], S["page_run.post"]}
    pcs = []

    def step_to(pc_set, limit=40):
        for _ in range(limit):
            p.tick()
            if p.pc() in pc_set:
                return True
        return False

    p.hold("I")
    ok = step_to({S["page_run"]})
    p.release()
    z.cmd("reset-tstates-partial")
    f0 = p.rb("SYS_FRAMES")
    ok = ok and step_to({S["PAGE_ORG"]})
    t_unpack = int(z.cmd("get-tstates-partial"))
    ok = ok and step_to({S["select_tick"]})
    t_open = int(z.cmd("get-tstates-partial"))
    f_open = (p.rb("SYS_FRAMES") - f0) & 255
    check("P1 I -> page_run -> overlay -> page loop", ok)
    raw = open(REPO / "build" / "ovl" / "page.bin", "rb").read()
    band = bytes(z.read_memory(S["PAGE_ORG"], len(raw)))
    check("P1 band bitmap == build/ovl/page.bin (%d B)" % len(raw), band == raw,
          sum(a != b for a, b in zip(band, raw)))
    mode = p.rb("SND_MODE")
    attrs = bytes(z.read_memory(S["SCREEN_ATTR"] + 32 * BAND, 32 * (24 - BAND)))
    check("P1 open: PAGE_OPEN 1, SND_HOLD set (mode 3 kept), bank 5 shown, band attrs 0",
          (p.rb("PAGE_OPEN"), mode, shown5(), set(attrs)) == (1, 3 | HOLD, True, {0}),
          (p.rb("PAGE_OPEN"), hex(mode), shown5(), sorted(set(attrs))[:4]))
    z.cmd("set-memory-zone 0")
    try:
        b7 = bytes(z.read_memory(7 * 16384, SCREEN_FRAME_LEN))
    finally:
        z.cmd("set-memory-zone -1")
    check("P1 screen 2 holds the screen before the page (the backup)", b7 == bytes(before),
          sum(a != b for a, b in zip(b7, before)))
    p.tick(3)
    p.hold("FIRE")
    z.cmd("reset-tstates-partial")
    ok = step_to({S["page_run.closed"]})
    p.release()
    z.cmd("reset-tstates-partial")
    f1 = p.rb("SYS_FRAMES")
    ok = ok and step_to({S["page_run.post"]})
    t_copy = int(z.cmd("get-tstates-partial"))
    ok = ok and step_to({S["wait_tick"]})
    t_close = int(z.cmd("get-tstates-partial"))
    f_close = (p.rb("SYS_FRAMES") - f1) & 255
    check("P1 FIRE closes", ok and p.rb("PAGE_OPEN") == 0 and not shown5())
    print(f"[info] P1 open: {t_unpack} T to the overlay entry (present_full + unpack), "
          f"{t_open} T to the first page frame ({f_open} frames); close: copy-back {t_copy} T, "
          f"{t_close} T to the next tick probe ({f_close} frames)", flush=True)
    for n in range(5, 9):
        z.cmd("set-breakpoint %d" % n)
    p.extra_probes = set()
    p.settle(3)
    check("P1 after close: displayed == composed == before",
          p.frame() == before and p.composed_frame() == before)

    # ---- P2: keys inside the page --------------------------------------------
    t0, sel0, e0, m0 = tc(), p.rb("SEL_SLOT"), hero(), p.rb("SND_MODE")
    p.tap("I")
    opened = p.rb("PAGE_OPEN") == 1
    for keys in (("3",), ("S",), ("P",), ("O",), ("Q",), ("A",), ("A", "P")):
        p.hold(*keys)
        p.tick(12)
        p.release()
        p.tick(2)
    e1 = hero()
    check("P2 keys on the page: page still up, no turn, slot / sound / hero / ICON MODE kept",
          (opened, p.rb("PAGE_OPEN"), tc(), p.rb("SEL_SLOT"), p.rb("SND_MODE"), e1["X"], e1["FLAGS"],
           p.rb("ICON_MODE")) == (True, 1, t0, sel0, m0 | HOLD, e0["X"], e0["FLAGS"], 0),
          (opened, p.rb("PAGE_OPEN"), tc() - t0, p.rb("SEL_SLOT"), hex(p.rb("SND_MODE")), e1["X"], e0["X"]))

    # ---- P3: close with a direction held ---------------------------------------
    p.hold("P", "FIRE")                          # facing right: P would walk
    p.tick(2)
    p.hold("P")
    closed = p.rb("PAGE_OPEN") == 0
    p.tick(30)
    x_held = hero()["X"]
    p.release()
    p.tick(6)
    check("P3 closed with P held: no move while held nor on release, no turn",
          (closed, x_held, hero()["X"], tc()) == (True, e0["X"], e0["X"], t0),
          (closed, x_held, hero()["X"], tc() - t0))
    moved = p.turn("L")
    check("P3 a fresh P afterwards walks", moved and hero()["X"] != e0["X"], (moved, hero()["X"]))
    p.settle(4)

    # ---- P4: 20 cycles ----------------------------------------------------------
    bad = []
    for i in range(20):
        smode = (3, 2, 0)[i % 3]
        p.wb("SND_MODE", smode)
        p.settle(2)
        how = i % 4
        icon = how == 3
        if icon:                                  # ICON MODE: A + SPACE, cursor to BAG (9)
            p.hold("A", "SPACE")
            p.tick(2)
            p.release()
            p.tick(2)
            p.tap("9")
            p.tick(2)
        elif how in (1, 2):
            p.tap("9")
            p.tick(2)
        before, comp0 = p.frame(), p.composed_frame()
        t0, sel0, im0 = tc(), p.rb("SEL_SLOT"), p.rb("ICON_MODE")
        if how == 0:
            p.hold("I")
        elif how == 1:
            p.hold("ENTER")
        else:
            p.hold("SPACE")                       # a tap (play) / a press (ICON MODE)
        p.tick(2)
        p.release()
        up = p.until(lambda: p.rb("PAGE_OPEN") == 1, 6)
        snd_open = p.rb("SND_MODE")
        p.tick(3)
        p.hold(*CLOSERS[i % 4])
        p.tick(2)
        p.release()
        p.tick(4)
        aft, comp1 = p.frame(), p.composed_frame()
        st = (up, snd_open, p.rb("PAGE_OPEN"), p.rb("SND_MODE"), tc(), p.rb("ICON_MODE"),
              p.rb("SEL_SLOT"), aft == before, comp1 == before, aft == comp1)
        want = (True, smode | HOLD, 0, smode, t0, im0, sel0, True, True, True)
        if st != want:
            bad.append((i, how, st))
        if icon:                                  # leave ICON MODE (UP)
            p.tap("Q")
            p.tick(2)
    check("P4 20 open / close cycles (I / ENTER / FIRE / ICON MODE; FIRE / BREAK / ENTER / I; "
          "modes 3 / 2 / 0): screens identical, no turn, HOLD cleared, mode / ICON MODE / slot kept",
          bad == [], bad[:3])

    # ---- P5: same-tick ENTER + I, close keys never re-open; held hero ---------
    p.settle(3)
    if p.rb("SEL_SLOT") != 8:
        p.tap("9")
        p.tick(2)
    res = []
    for opener, closer in ((("I", "ENTER"), ("ENTER",)), (("I",), ("I",)), (("ENTER",), ("ENTER", "I"))):
        n0, t0 = p.rb("PAGE_N"), tc()
        p.hold(*opener)
        p.tick(2)
        p.release()
        p.tick(3)
        up = p.rb("PAGE_OPEN")
        p.hold(*closer)
        p.tick(2)
        p.release()
        p.tick(8)
        res.append((up, (p.rb("PAGE_N") - n0) & 255, p.rb("PAGE_OPEN"), tc() - t0))
    check("P5 I+ENTER / I / ENTER open once; ENTER / I / ENTER+I close without a re-open or a use",
          res == [(1, 1, 0, 0)] * 3, res)
    st = S["ST_FLAGS"]
    f0 = p.rb(st)
    p.wb(st, f0 | S["STS_HOLD"])
    n0 = p.rb("PAGE_N")
    p.tap("I")
    p.tick(6)
    held = (p.rb("PAGE_N") - n0) & 255, p.rb("PAGE_OPEN"), p.rb("INTENT")
    p.wb(st, f0)
    check("P5 held hero: I opens nothing, INTENT dropped", held == (0, 0, 0), held)


def main():
    fails = []
    n = [0]
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] page needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(p, check)
        print(f"page: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
