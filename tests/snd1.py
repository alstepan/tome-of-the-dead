#!/usr/bin/env python3
"""SND-1: the sound settings UI (game.md §3.6 checks 1-7; src/menu1.asm snd_cycle,
sfx2.asm snd_scan / snd_hot). Release build (DEBUG_KIT=0), real menu / pause / play.

  1  boot SND_MODE = 3; menu item 5 drawn "5 SOUND: ALL ON" (rows 22-23)
  2  in play S x3 -> 2, 0, 3; TURN_COUNTER / NEED_RELEASE / FIRE_ST / INTENT / TURN_HOLD / DN_T
     unchanged; the log shows each string
  3  S held 50 ticks -> one change only
  4  O held + S tapped -> the hero keeps walking; mode changed once
  5  menu '5' x3 -> 2, 0, 3 (item redrawn, no leftover cells); the setting survives
     death -> menu -> START
  6  pause: RIGHT -> SOUND, FIRE cycles and stays paused (SND_HOLD kept), the box redraws;
     RIGHT x2 wraps, LEFT wraps; S cycles too; BREAK resumes (HOLD cleared, mode kept)
  7  redefine to S -> KEY RESERVED (rd_i unchanged)
  8  snd_cycle's confirmation SFX_MENU: queued when the new mode has SFX on, not when OFF,
     not while SND_HOLD
Run: ZRCP_PORT=<port> python3 tests/snd1.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game  # noqa: E402
import world  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, GS_PLAYING, GS_SELECT  # noqa: E402
from proj3 import w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
TXT = dict(world.STRINGS)
SND_MODE, HOLD = S["SND_MODE"], 0x80
NAMES = {3: "snd_all", 2: "snd_sfx", 0: "snd_off"}
NEXT = {3: 2, 2: 0, 0: 3}


def main():
    fails = []
    n = [0]
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = world.W(h)

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:400]}", flush=True)

        if KIT:
            print("[skip] snd1 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(p, check)
        print(f"snd1: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(p, check):
    mode = lambda: p.rb("SND_MODE") & 3          # noqa: E731
    held = lambda: p.rb("SND_MODE") & HOLD       # noqa: E731

    def menu_item(fr, m):
        t = "5 " + TXT[NAMES[m]]
        ok = world.menu_text_ok(p, fr, 22, 4, t)
        # nothing drawn right of the text up to col 20 (the longest state) on rows 22-23
        blank = all(not any(world.cell_bytes(fr, c, r)) for r in (22, 23) for c in range(4 + len(t), 21))
        return ok and blank

    def log_line():
        p.until(lambda: p.rb("LOG_QN") == 0, 20)
        p.tick(2)
        return world.log_row(p.composed_frame(), 23)

    # ---- 1 + 5: boot, menu item 5
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_SRC", 1)
    p.wb("ANIM_FREEZE", 1)
    p.release()
    p.tick(4)
    check("1 boot: SND_MODE = 3 (ALL ON)", p.rb("SND_MODE") == 3, p.rb("SND_MODE"))
    check("1 menu: '5 SOUND: ALL ON' on rows 22-23", menu_item(p.frame(), 3), "")
    seq, drawn = [], []
    for _ in range(3):
        p.tap("5", n=2)
        p.tick(2)
        seq.append(mode())
        drawn.append(menu_item(p.frame(), mode()))
    check("5 menu '5' x3 cycles 2, 0, 3, item redrawn (no leftover cells)",
          seq == [2, 0, 3] and all(drawn) and p.rb("GAME_STATE") == GS_SELECT, (seq, drawn))
    p.tap("5", n=2)                                       # -> 2 (SFX ONLY) for the persistence run
    p.tap("1", n=2)                                       # key '1' held: START
    ok = p.wait_state(GS_PLAYING, 400)
    p.release()
    p.isolate()
    p.settle(4)
    check("5 START keeps SFX ONLY", ok and mode() == 2, (ok, mode()))

    # ---- 8: the confirmation SFX (run snd_cycle with interrupts off, so the ISR cannot take the request)
    def cycle_req(start, hold=False):
        p.wb("SND_MODE", start | (HOLD if hold else 0))
        p.wb("SFX_REQ", 0)
        p.wb("SFX_NEXT", 0)
        pc0 = p.pc()
        world.run_code(p, [0xF3, 0x21] + w16(S["snd_cycle"]) + [0xCD] + w16(S["far1"]) + [0xFB])
        p.z.cmd("set-register PC=%d" % pc0)
        return p.rb("SND_MODE"), p.rb("SFX_REQ")
    r = [cycle_req(3), cycle_req(2), cycle_req(0), cycle_req(2, hold=True)]
    check("8 snd_cycle: 3->2 and 0->3 queue SFX_MENU; 2->0 and the held cycle do not; HOLD kept",
          r == [(2, S["SFX_MENU"]), (0, 0), (3, S["SFX_MENU"]), (0 | HOLD, 0)], r)
    p.wb("SND_MODE", 3)
    p.wb("SFX_REQ", 0)
    p.settle(3)

    # ---- 2: in play S x3
    p.settle(2)
    keep = ("TURN_COUNTER", "NEED_RELEASE", "FIRE_ST", "INTENT", "TURN_HOLD", "DN_T")
    snap = lambda: [p.rw(k) if k == "TURN_COUNTER" else p.rb(k) for k in keep]   # noqa: E731
    s0 = snap()
    ms, logs = [], []
    for _ in range(3):
        p.tap("S", n=2)
        p.tick(2)
        ms.append(mode())
        logs.append(log_line() == world.text6(TXT[NAMES[mode()]]))
        p.tick(2)
    check("2 in play S x3 -> 2, 0, 3; counters / FIRE_ST / INTENT / hold state unchanged; each log line shown",
          ms == [2, 0, 3] and snap() == s0 and all(logs), (ms, s0, snap(), logs))

    # ---- 9: rapid S: at most one pending SOUND line, a queued combat line survives
    p.wb("SND_MODE", 3)
    p.wb("LOG_QN", 0)
    drop0 = p.rb(S["LOG_Q"] + S["LQ_DROP"])
    pc0 = p.pc()
    code = [0xF3, 0x3E, S["TX_NO_ARROWS"], 0xCD] + w16(S["msg_push"])        # a "combat" line first, no ISR / no drain
    code += ([0x21] + w16(S["snd_cycle"]) + [0xCD] + w16(S["far1"])) * 6
    world.run_code(p, code + [0xFB])
    p.z.cmd("set-register PC=%d" % pc0)
    qn = p.rb("LOG_QN")
    rd = p.rb(S["LOG_Q"] + S["LQ_RD"])
    slots = [bytes(p.z.read_memory(S["LOG_TXT"] + ((rd + i) & 3) * 64, 2)) for i in range(qn)]
    n_snd = sum(1 for x in slots if x == b"SO")
    check("9 six rapid S: at most one pending SOUND line, the queued NO ARROWS line kept, nothing dropped",
          n_snd <= 1 and qn <= 2 and (qn < 2 or slots[0] != b"SO") and p.rb(S["LOG_Q"] + S["LQ_DROP"]) == drop0,
          (qn, slots, p.rb(S["LOG_Q"] + S["LQ_DROP"])))
    p.until(lambda: p.rb("LOG_QN") == 0, 30)
    p.wb("SND_MODE", 3)

    # ---- 3: S held 50 ticks
    p.hold("S")
    p.tick(50)
    p.release()
    p.tick(3)
    check("3 S held for 50 ticks cycles once (3 -> 2)", mode() == 2 and snap() == s0, (mode(), snap()))
    p.wb("SND_MODE", 3)

    # ---- 4: O held, S tapped
    e0 = p.ent(0)
    p.hold("P")
    p.tick(4)
    x1 = p.ent(0)["X"]
    p.hold("P", "S")
    p.tick(3)
    p.hold("P")
    p.tick(10)
    x2 = p.ent(0)["X"]
    p.release()
    p.tick(10)
    check("4 P (right) held + S tapped: the hero keeps walking, mode changed once",
          x1 > e0["X"] and x2 > x1 and mode() == 2, (e0["X"], x1, x2, mode()))
    p.wb("SND_MODE", 3)
    p.isolate()
    p.settle(4)

    # ---- 6: pause box
    t0 = p.rw("TURN_COUNTER")
    p.hold("SPACE", "Q")
    p.tick(2)
    p.release()
    p.tick(3)
    fr = p.frame()
    check("6 pause box: RESUME / SOUND: ALL ON / QUIT at cols 1 / 9 / 27, HOLD set",
          p.rb("PAUSED") == 1 and held() and world.menu_text_ok(p, fr, 8, 1, "RESUME")
          and world.menu_text_ok(p, fr, 8, 9, "SOUND: ALL ON") and world.menu_text_ok(p, fr, 8, 27, "QUIT"), "")
    p.tap("P")                                            # -> SOUND
    sel1 = p.rb("pause_sel")
    p.tap("SPACE", n=2)                                   # FIRE: cycle in place
    p.tick(2)
    fr = p.frame()
    check("6 pause: RIGHT -> SOUND, FIRE cycles (3 -> 2), box redrawn, still paused with HOLD",
          sel1 == 1 and mode() == 2 and p.rb("PAUSED") == 1 and held()
          and world.menu_text_ok(p, fr, 8, 9, "SOUND: SFX ONLY"), (sel1, mode(), p.rb("PAUSED")))
    p.tap("S")
    p.tick(2)
    check("6 pause: S cycles too (2 -> 0), the box shows OFF",
          mode() == 0 and p.rb("PAUSED") == 1 and world.menu_text_ok(p, p.frame(), 8, 9, "SOUND: OFF"), mode())
    sel = []
    p.tap("P"); sel.append(p.rb("pause_sel"))             # QUIT          # noqa: E702
    p.tap("P"); sel.append(p.rb("pause_sel"))             # wraps: RESUME # noqa: E702
    p.tap("O"); sel.append(p.rb("pause_sel"))             # wraps: QUIT   # noqa: E702
    p.tap("O"); sel.append(p.rb("pause_sel"))             # SOUND         # noqa: E702
    check("6 pause: LEFT / RIGHT wrap over RESUME / SOUND / QUIT", sel == [2, 0, 2, 1], sel)
    p.hold("CAPS", "SPACE")                               # BREAK resumes
    p.tick(3)
    p.release()
    p.tick(6)
    check("6 BREAK resumes: PAUSED 0, HOLD cleared, the mode set in the pause kept (OFF), no turn",
          p.rb("PAUSED") == 0 and not held() and mode() == 0 and p.rw("TURN_COUNTER") == t0,
          (p.rb("PAUSED"), p.rb("SND_MODE"), p.rw("TURN_COUNTER"), t0))

    # ---- 5 (cont.): survives death -> menu -> START
    p.wb("SND_MODE", 2)
    check("5 hero dies", p.die(), True)
    check("5 ENTER -> menu, the setting kept", p.enter_to_select() and mode() == 2, mode())
    p.wb("ANIM_FREEZE", 1)
    p.tick(4)
    check("5 menu after the game shows SFX ONLY", menu_item(p.frame(), 2), "")
    p.tap("5", n=2)
    p.tick(2)
    p.tap("1", n=2)
    p.wait_state(GS_PLAYING, 400)
    p.release()
    check("5 survives death -> menu -> START (a cycle in the menu: 0)", mode() == 0, mode())

    # ---- 7: redefine to S -> KEY RESERVED
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_SRC", 1)
    p.wb("ANIM_FREEZE", 1)
    p.release()
    p.tick(4)
    p.tap("4", n=2)
    p.tap("S", n=2)
    p.tick(2)
    shown = p.rb("rd_i")
    msg = world.log_row(p.frame(), 20, 0, 32) == world.text6(TXT["key_reserved"], 0, 32)
    check("7 redefine: S shows KEY RESERVED (rd_i stays 0)", shown == 0 and msg, (shown, msg))
    p.tick(30)
    p.tap("G", n=2)
    p.tick(30)
    check("7 redefine: G accepted afterwards (rd_i 1)", p.rb("rd_i") == 1, p.rb("rd_i"))


if __name__ == "__main__":
    sys.exit(main())
