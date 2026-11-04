#!/usr/bin/env python3
"""END-WAIT (user 2026-11-04): GS_DEAD / GS_WIN do not draw the end card at once. The final scene
(+ the lethal turn's log line) stays up; the card is drawn by the first key after a quiet countdown.

END_SHOWN (main.asm end_screen, menu1 end_card): END_DELAY..1 = countdown (a tick with no key down
counts it down, a key reloads it), 0 = wait for a key; bit 7 ES_CARD = the card is up (same countdown, then a key leaves).

  D1  death with a digit held (a panicked press): no card, the countdown stays at END_DELAY while held
  D2  released: it counts down; a key tapped mid-count reloads it (no card)
  D3  quiet END_DELAY ticks -> 0, still no card (the frame is the scene, no card title)
  D4  a key -> the card (title in the menu font); that key still down / tapped inside the card's quiet: no menu; quiet -> armed
  D5  a digit after the release -> the menu (GS_SELECT)
  The same for GS_WIN ("YOU WIN!").
Run: WZ_BUILD_DIR=<dir>/build ZRCP_PORT=<port> python3 tests/endwait.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS               # noqa: E402
from boss import Lair                                   # noqa: E402
from lp import T                                        # noqa: E402
from world import menu_text_ok                          # noqa: E402

GS_DEAD, GS_WIN, GS_SELECT = S["GS_DEAD"], S["GS_WIN"], S["GS_SELECT"]
DELAY, CARD = S["END_DELAY"], S["ES_CARD"]
TROW = S["EC_TROW"]
fails = []


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {str(got)[:300]}"), flush=True)


def run(p, state, title, tag):
    p.wb("GAME_STATE", state)                             # (the lethal turn's own .dead / game_win set it)
    p.wb("END_SHOWN", DELAY)                              # what start_game leaves
    p.hold("2")
    p.tick(DELAY + 10)
    sh = p.rb("END_SHOWN")
    check(f"{tag} D1 a digit held at the end: no card, the quiet stays at END_DELAY",
          sh == DELAY and p.rb("GAME_STATE") == state, (sh, p.rb("GAME_STATE")))
    p.release()
    p.tick(6)
    sh = p.rb("END_SHOWN")
    check(f"{tag} D2a released: counting down, no card", 0 < sh < DELAY, sh)
    p.tap("3")
    sh2 = p.rb("END_SHOWN")               # (tap = a key tick reloads, then a release tick counts 1)
    check(f"{tag} D2b a key mid-count reloads the quiet, still no card", sh2 >= DELAY - 1 and sh2 > sh, (sh, sh2))
    p.tick(DELAY + 4)
    fr = p.frame()
    check(f"{tag} D3 a quiet END_DELAY: waiting for a key (0), no card on screen",
          p.rb("END_SHOWN") == 0 and not menu_text_ok(p, fr, TROW, 12, title) and p.rb("LOG_QN") == 0,
          (p.rb("END_SHOWN"), p.rb("LOG_QN")))
    p.hold("1")
    p.tick(4)
    fr = p.frame()
    check(f"{tag} D4a the key draws the card ({title})",
          p.rb("END_SHOWN") & CARD and menu_text_ok(p, fr, TROW, 12, title), (p.rb("END_SHOWN"),))
    p.tick(4)
    fr0 = bytes(p.frame())
    p.tick(30)                                            # end_screen calls panel_tick over the card too:
    check(f"{tag} D4e the card is stable (panel_tick draws nothing over it)", bytes(p.frame()) == fr0, "frame changed")
    check(f"{tag} D4b the key that drew it still down: no menu", p.rb("GAME_STATE") == state, p.rb("GAME_STATE"))
    p.release()
    p.tick(4)
    p.tap("2")                                            # a tap inside the card's quiet: no menu
    p.tick(2)
    check(f"{tag} D4c a key inside the card's quiet: no menu", p.rb("GAME_STATE") == state, p.rb("GAME_STATE"))
    p.tick(DELAY + 4)
    check(f"{tag} D4d quiet again: armed (ES_CARD, count 0)", p.rb("END_SHOWN") == CARD, p.rb("END_SHOWN"))
    p.hold("2")
    p.tick(6)
    check(f"{tag} D5 a digit after the release -> the menu", p.rb("GAME_STATE") == GS_SELECT, p.rb("GAME_STATE"))
    p.release()


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        if S.get("KIT_DEBUG", 0):
            print("[skip] endwait needs a DEBUG_KIT=0 build", flush=True)
            return 0
        for st, title, tag in ((GS_DEAD, "YOU DIED", "death"), (GS_WIN, "YOU WIN!", "win")):
            L = Lair(p, 6, 0x6E06, hero=0)
            p.wb("ST1_KILLER", 0)
            check(f"{tag} setup", L.ok)
            run(p, st, title, tag)
    print(f"endwait: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
