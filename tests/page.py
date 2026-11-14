#!/usr/bin/env python3
"""3E-T2 bag page window + 3E-T13 / T14 the real page (src/lowram.asm page_run, src/menu1.asm page_ovl /
page_post, src/page_ovl.asm; docs/memory-map.md "Overlays", the page window).
Release build (DEBUG_KIT=0), real play.

  P1  I opens the page: PAGE_OPEN, NO SND_HOLD (the page is not a pause: SND_MODE,
      MUS_STATE / MUS_CUR unchanged, the player state ay_vars keeps changing, AY_CALLS
      advance), bank 5 shown, GEN_SCRATCH == build/ovl/page.bin (round trip of the
      bank-1 stream), PAGE_MAP_SAVE == the room map, screen 2 == the screen before
      (the backup), golden `page_start` (the Warrior start bag); open / close cost
  P2  keys inside the page do not leak: slot key, S, ENTER held, Q / A / O / P,
      DOWN held -> no turn, SEL_SLOT / SND_MODE / ICON_MODE / hero unchanged, page up
  P3  closing with a direction held: the hero does not move (EXIT_LOCK) while it is
      held, nor on its release; a fresh tap afterwards works
  P4  20 open / close cycles (I / BAG icon via 9 + ENTER / FIRE tap / ICON MODE FIRE;
      closed by [CLOSE] + FIRE / BREAK / [CLOSE] + ENTER / I; sound modes 3 / 2 / 0): each time the
      displayed AND composed screens == before, no turn, no SND_HOLD, PAGE_OPEN clear,
      mode kept, ICON MODE kept, displayed == composed; after the 20 cycles ROOM_MAP,
      LVL_STATE, LP_STATE, ANIM lists, P_ENTITIES, RNG_STATE, tile_flags, FLOOR_LIST,
      MK_RAM, the drip state and ITEM_RAM are unchanged
  P5  review fixes: BAG selected + I and ENTER in the same tick -> one open only;
      closing with BREAK / I / ENTER+I never re-opens nor uses the icon; no turn; a held hero
      (STS_HOLD): I opens nothing (INTENT dropped on the turn-intent path)
  P6  a mixed bag + worn set: IC1 16x16 icons, floor inks, QTY digits, empty frames, the
      empty worn slot's placeholder, the description icon, ITEMS n,
      cursor on slot 0, golden `page_bag`
  P7  cursor wrap rules; P8 the verb-enable matrix (+ the USE word)
  P9  verbs: EQUIP / REMOVE return PAGE_VERB / PAGE_SLOT, consumed by page_post
      (PAGE_VERB 0 after the close, PAGE_VLAST = the verb) and applied (3E-T8: the
      swap / the bag add, 1 turn each; tests/equip.py has the details); [CLOSE],
      strip navigation, BREAK, CLOSE verb -> VB_NONE; DISCARD (stack, bow: HAS_BOW 0,
      E_POT, ITEMS n - 1, 0 turns); REMOVE with a full bag -> BAG FULL, page stays
Run: ZRCP_PORT=<port> python3 tests/page.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_DIR = os.environ.get("WZ_BUILD_DIR", str(HERE.parent / "build"))
sys.path.insert(0, str(HERE))
_UPD = "--update-golden" in sys.argv
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
game.UPDATE = _UPD
game.PNG_DIR = os.environ.get("PAGE_PNG") or None   # PAGE_PNG=dir: dump the goldens' screens
import game_lib  # noqa: E402
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, SCREEN_FRAME_LEN  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
HOLD = 0x80
# 3E-T13: FIRE / ENTER select; they close only on [CLOSE] (UP from bag row 0 first)
CLOSERS = (("Q", "FIRE"), ("CAPS", "SPACE"), ("Q", "ENTER"), ("I",))


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
    ncell = S["PLAY_CELLS"]
    keep = {"map": bytes(z.read_memory(S["ROOM_MAP"], ncell))}

    def state():
        """Game state that must survive any number of page opens / closes."""
        return {k: bytes(z.read_memory(S[a] if isinstance(a, str) else a, n)) for k, a, n in (
            ("ROOM_MAP", "ROOM_MAP", ncell), ("LVL_STATE (GEN_RNG, seeds, FLOOR_LIST)", "LVL_STATE", 320),
            ("LP_STATE (LP_RNG)", "LP_STATE", S["LP_END"] - S["LP_STATE"]), ("ANIM_N", "ANIM_N", 49),
            ("ANIM_N2", "ANIM_N2", 49), ("P_ENTITIES", "P_ENTITIES", 512), ("RNG_STATE", "RNG_STATE", 2),
            ("tile_flags", "tile_flags", 64), ("FLOOR_LIST", "FLOOR_LIST", 128),
            ("MK_RAM", "MK_RAM", S["MK_RAM_END"] - S["MK_RAM"]), ("DRIP", "DRIP_ST", 11),
            ("ITEM_RAM", "ITEM_RAM", S["ITEM_RAM_LEN"]))}
    mus0 = (p.rb("SND_MODE"), p.rb("MUS_STATE"), p.rb("MUS_CUR"))

    def ayv():
        z.cmd("set-memory-zone 0")
        try:
            return bytes(z.read_memory(3 * 16384 + S["ay_vars"] - 0xC000, S["ay_vars_end"] - S["ay_vars"]))
        finally:
            z.cmd("set-memory-zone -1")
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
    raw = open(Path(BUILD_DIR) / "ovl" / "page.bin", "rb").read()
    win = bytearray(z.read_memory(S["PAGE_ORG"], len(raw)))
    v0, v1 = S["pg_rc"] - S["PAGE_ORG"], S["pg_wid"] - S["PAGE_ORG"]   # the page's variables (written)
    win[v0:v1] = raw[v0:v1]
    win = bytes(win)
    check("P1 GEN_SCRATCH == build/ovl/page.bin but its variables (%d B, limit %d)" % (len(raw), S["GEN_SCRATCH_LEN"]),
          win == raw, sum(a != b for a, b in zip(win, raw)))
    check("P1 PAGE_MAP_SAVE holds the room map",
          bytes(z.read_memory(S["PAGE_MAP_SAVE"], ncell)) == keep["map"])
    a0, c0 = ayv(), p.rw("AY_CALLS")
    p.tick(10)
    a1, c1 = ayv(), p.rw("AY_CALLS")
    mus1 = (p.rb("SND_MODE"), p.rb("MUS_STATE"), p.rb("MUS_CUR"))
    check("P1 open: PAGE_OPEN 1, bank 5 shown, no SND_HOLD: SND_MODE / MUS_STATE / MUS_CUR "
          "unchanged, the player keeps sequencing (ay_vars change, AY_CALLS +10 frames)",
          (p.rb("PAGE_OPEN"), shown5(), mus1, a1 != a0, (c1 - c0) & 0xFFFF >= 10)
          == (1, True, mus0, True, True),
          (p.rb("PAGE_OPEN"), shown5(), mus0, mus1, a1 != a0, c1 - c0))
    game.golden(p.h, "page_start", p.frame())
    z.cmd("set-memory-zone 0")
    try:
        b7 = bytes(z.read_memory(7 * 16384, SCREEN_FRAME_LEN))
    finally:
        z.cmd("set-memory-zone -1")
    check("P1 screen 2 holds the screen before the page (the backup)", b7 == bytes(before),
          sum(a != b for a, b in zip(b7, before)))
    p.tick(3)
    p.hold("I")
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
    check("P1 I closes", ok and p.rb("PAGE_OPEN") == 0 and not shown5())
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
           p.rb("ICON_MODE")) == (True, 1, t0, sel0, m0, e0["X"], e0["FLAGS"], 0),
          (opened, p.rb("PAGE_OPEN"), tc() - t0, p.rb("SEL_SLOT"), hex(p.rb("SND_MODE")), e1["X"], e0["X"]))

    # ---- P3: close with a direction held ---------------------------------------
    p.hold("P", "I")                             # facing right: P would walk
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
    st0 = state()
    bad = []
    for i in range(20):
        smode = (3, 2, 0)[i % 3]
        p.wb("SND_MODE", smode)
        p.settle(2)
        how = i % 4
        icon = how == 3
        if icon:                                  # ICON MODE: A + SPACE, cursor to BAG (key 0, UB5: slot 10 on both bars)
            p.hold("A", "SPACE")
            p.tick(2)
            p.release()
            p.tick(2)
            p.tap("0")
            p.tick(2)
        elif how in (1, 2):
            p.tap("0")
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
        cl = CLOSERS[i % 4]
        if cl[0] == "Q":                          # [CLOSE]: UP from bag row 0, then FIRE / ENTER
            p.tap("Q")
            cl = cl[1:]
        p.hold(*cl)
        p.tick(2)
        p.release()
        p.tick(4)
        aft, comp1 = p.frame(), p.composed_frame()
        st = (up, snd_open, p.rb("PAGE_OPEN"), p.rb("SND_MODE"), tc(), p.rb("ICON_MODE"),
              p.rb("SEL_SLOT"), aft == before, comp1 == before, aft == comp1)
        want = (True, smode, 0, smode, t0, im0, sel0, True, True, True)
        if st != want:
            bad.append((i, how, st))
        if icon:                                  # leave ICON MODE (UP)
            p.tap("Q")
            p.tick(2)
    check("P4 20 open / close cycles (I / ENTER / FIRE / ICON MODE; FIRE / BREAK / ENTER / I; "
          "modes 3 / 2 / 0): screens identical, no turn, no SND_HOLD, mode / ICON MODE / slot kept",
          bad == [], bad[:3])
    st1 = state()
    check("P4 after the 20 cycles: ROOM_MAP, LVL_STATE, LP_STATE, ANIM lists, P_ENTITIES, RNG_STATE, "
          "tile_flags, FLOOR_LIST, MK_RAM, drip state, ITEM_RAM unchanged",
          st1 == st0, [k for k in st0 if st1[k] != st0[k]])

    # ---- P5: same-tick ENTER + I, close keys never re-open; held hero ---------
    p.settle(3)
    if p.rb("SEL_SLOT") != 9:
        p.tap("0")
        p.tick(2)
    res = []
    for opener, closer in ((("I", "ENTER"), ("CAPS", "SPACE")), (("I",), ("I",)), (("ENTER",), ("ENTER", "I"))):
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
    check("P5 I+ENTER / I / ENTER open once; BREAK / I / ENTER+I close without a re-open or a use",
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
    p.settle(3)
    wear_ui(p, check)
    bag_page(p, check)


# ---- 3E-T13 / T14: the real page (P6..P9) -------------------------------------
VB = {k: S["VB_" + k] for k in ("NONE", "DRINK", "EAT", "READ", "EQUIP", "REMOVE", "DISCARD")}
V_COLS = (2, 7, 12, 18, 25)                   # verb strip cols (page_ovl.asm pg_vtab)
A_VON, A_VOFF = 0x45, 0x01
CLOSE_SLOT = 24
WIDTHS = (1, 5, 5, 5, 5, 4)                   # cursor row widths ([CLOSE], 4 bag rows, worn)


def slot_rect(s):
    """(col, row) of slot s's icon (page_ovl.asm pg_rect); [CLOSE] = (26, 0)."""
    if s == CLOSE_SLOT:
        return 26, 0
    if s >= 20:
        return 11 + 3 * (s - 20), 16
    return 9 + 3 * (s % 5), 4 + 3 * (s // 5)


def rect_cells(s):
    c, r = slot_rect(s)
    if s == CLOSE_SLOT:
        return [(c + i, 0) for i in range(6)]
    return [(c + i, r + j) for i in range(2) for j in range(2)]   # UX1 C1: the 2x2 icon cells (count column: black)


def wear_ui(p, check):
    """WEAR-UI: the description line shows a gear item's modifier m (" -2" / " +1", m != 0) and, at m = -3,
    " WORN OUT" in place of " -3" (the next wear event destroys it); m = 0 shows nothing extra (the fresh-item goldens are
    unchanged); the longest line (any gear type, m -3 / +3) fits PAGE_BUF (PAGE_BUF_LEN - 1 chars)."""
    z = p.z
    tc = lambda: p.rw("TURN_COUNTER")          # noqa: E731
    I = lambda n: S["IT_" + n]                 # noqa: E731,E741
    bag0 = bytes(z.read_memory(S["BAG"], 60))
    worn0 = bytes(z.read_memory(S["WORN"], 12))

    def txt():
        b = bytes(z.read_memory(S["PAGE_BUF"], S["PAGE_BUF_LEN"]))
        return b.split(b"\0")[0].decode("latin1")

    def is_open():
        return p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]

    def shown(slot_bytes, where="bag"):
        """Page text for a record in bag slot 0 (cursor there) after a cursor bounce (re-runs pg_info)."""
        p.wmem("BAG", slot_bytes + [0] * (60 - len(slot_bytes)))
        p.tap("P")
        p.tap("O")
        return txt()
    ist = lambda m: (m & 7) << 5               # noqa: E731
    p.wmem("BAG", [0] * 60)
    p.wmem("WORN", [0] * 12)
    p.tap("I")
    ok = p.until(is_open, 12)
    got = {m: [shown([I(t), 1, ist(m)]) for t in ("W_LONG", "A_CHAIN", "H_HELM")] for m in (0, -1, -2, -3, 1)}
    want = {0: ["LONG SWORD 1D8 ATK+1", "CHAIN MAIL DEF+2", "HELM DEF+1"],
            -1: ["LONG SWORD -1 1D8-1 ATK+1", "CHAIN MAIL -1 DEF+1", "HELM -1"],
            -2: ["LONG SWORD -2 1D8-2 ATK+1", "CHAIN MAIL -2", "HELM -2 DEF-1"],
            -3: ["LONG SWORD WORN OUT 1D8-3 ATK+1", "CHAIN MAIL WORN OUT DEF-1", "HELM WORN OUT DEF-2"],
            1: ["LONG SWORD +1 1D8+1 ATK+1", "CHAIN MAIL +1 DEF+3", "HELM +1 DEF+2"]}
    check("WU1 page text m = 0 / -1 / -2 / -3 / +1: name + signed m (WORN OUT instead of -3) + the numbers",
          ok and got == want, (ok, {m: (got[m], want[m]) for m in got if got[m] != want[m]}))
    # the worn slots (cursor Q Q = worn weapon) show the same text; the bag item likewise
    mx, who = 0, None
    for t in range(S["IT_GEAR_LO"], S["IT_GEAR_HI"] + 1):
        for m in (-3, 3):
            tx = shown([t, 1, ist(m)])
            if len(tx) > mx:
                mx, who = len(tx), (t, m, tx)
    check("WU2 every gear type at m = -3 / +3: the line fits PAGE_BUF (<= PAGE_BUF_LEN - 1 chars)",
          mx <= S["PAGE_BUF_LEN"] - 1, (mx, who))
    # a fresh bag potion / food stack: unchanged (no m text, whatever bits 5-7 hold)
    pot = shown([I("P_HEAL"), 2, 0xE0])
    check("WU3 a potion stack with ISTATE $E0 (bits 5-7 set) has no m text", pot.startswith("HEAL POTION X2") and "-" not in pot, pot)
    # destruction at -3: the slot empties and the page reflects it (the row 18 text = an always-empty slot's; ITEM-INFO)
    p.tap("I")
    p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
    # the wear event itself (wear_slot: m -3 + notch empties the slot, WEAR_PEND bit pair 2) is tier6.py W1;
    # here its aftermath: the empty slot, the pending redraw applied by a real turn
    p.wmem("WORN", [0] * 12)
    p.wb("WEAR_PEND", 2)
    t0 = tc()
    for k in ("P", "O", "Q", "A"):             # a real turn: end_turn -> hunger_turn -> wear_apply
        p.tap(k)
        p.tick(8)
        if tc() != t0:
            break
    slot = list(z.read_memory(S["WORN"], 3))
    p.tap("I")
    p.until(is_open, 12)
    p.tap("Q")
    p.tap("Q")
    p.tick(2)
    at20 = (p.rb("pg_rc"), p.rb(S["pg_rc"] + 1))
    from game_lib import cell_bytes
    row19 = lambda: [cell_bytes(p.frame(), c, 18) for c in range(2, 8)]   # noqa: E731  (ITEM-INFO: row 18)
    r20 = row19()
    p.tap("P")
    p.tap("P")
    p.tap("P")
    r23 = row19()
    check("WU4 aftermath of a destruction (slot empty, redraw applied by a turn): the page shows EMPTY there like any empty slot; the wear event itself is tier6 W1",
          slot == [0, 0, 0] and at20 == (5, 0) and r20 == r23 and p.rb("WEAR_PEND") == 0, (slot, at20, r20 == r23, p.rb("WEAR_PEND")))
    p.tap("I")
    p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
    p.wmem("BAG", list(bag0))
    p.wmem("WORN", list(worn0))
    p.settle(2)


def bag_page(p, check):
    z = p.z
    tc = lambda: p.rw("TURN_COUNTER")          # noqa: E731
    I = lambda n: S["IT_" + n]                 # noqa: E731,E741
    attr_at, cell_bytes = game_lib.attr_at, game_lib.cell_bytes

    def ink(t):                                # FLOOR1: it_tab lives in R6: the model's ink
        return room_model.item_ink(t)

    def icon(idx):
        """IC1: the 16x16 icon idx (type - IT_BAG_LO; ICONS16_PH + worn slot = placeholder) cells."""
        return game_lib.icon16_cells(idx)

    def is_open():
        return p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]

    def open_page():
        p.tap("I")
        return p.until(is_open, 12)

    def wait_closed():
        return p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)

    def highlighted(fr):
        """(slots whose whole cursor rect has paper blue, cells with any paper outside the ornaments)."""
        hi = {s for s in range(25) if all(attr_at(fr, c, r) & 0x38 == 0x08 for c, r in rect_cells(s))}
        n = sum(1 for i in range(768) if fr[6144 + i] & 0x38 and i // 32 not in (2, 23))
        return hi, n

    def verbs(fr):
        return tuple({A_VON: 1, A_VOFF: 0}.get(attr_at(fr, c, 20) & 0xC7, "?") for c in V_COLS)

    def rc():
        return p.rb("pg_rc"), p.rb(S["pg_rc"] + 1)

    def row22(fr):
        return b"".join(cell_bytes(fr, c, 22) for c in range(32))

    def nav(slot):
        """Cursor to `slot` by key taps (vertical first, then horizontal)."""
        row, col = (0, 0) if slot == CLOSE_SLOT else (5, slot - 20) if slot >= 20 else (1 + slot // 5, slot % 5)
        for _ in range(8):
            r = rc()[0]
            if r == row:
                break
            p.tap("A" if (row - r) % 6 <= 3 else "Q")
        for _ in range(6):
            if min(rc()[1], WIDTHS[row] - 1) == col:
                break
            p.tap("P")
        return rc()[0] == row and min(rc()[1], WIDTHS[row] - 1) == col

    bag = [("P_HEAL", 2), ("P_MANA", 1), ("F_APPLE", 3), ("S_FEAR", 1), ("BOOK", 1), ("W_LONG", 1),
           ("A_CHAIN", 1), ("BOW", 1), ("C_MIGHT", 1), ("H_HELM", 1), ("F_MEAT", 9)]
    worn = [("W_SHORT", 1), ("A_LEATHER", 1), None, ("C_FIRE", 1)]

    def put_bag(items):
        flat = [b for n, q in items for b in (I(n), q, 0)]
        p.wmem("BAG", flat + [0] * (60 - len(flat)))
    put_bag(bag)
    p.wmem("WORN", [b for w in worn for b in ((I(w[0]), 1, 0) if w else (0, 0, 0))])
    p.wb("DAGGERS", 3)
    p.wb("ARROWS", 14)
    p.wb("HAS_BOW", 1)
    p.settle(2)

    # ---- P6: cells, inks, counts, golden ---------------------------------------
    ok = open_page()
    fr = p.frame()
    bad = []
    for s in range(24):
        rec = (bag + [None] * 9)[s] if s < 20 else worn[s - 20]
        c, r = slot_rect(s)
        if rec is None and s < 20:
            if cell_bytes(fr, c, r)[0] != 0xFF or attr_at(fr, c, r) & 0xC7 != 0x47:
                bad.append((s, "frame"))
            continue
        if rec is None:                           # IC1: an empty worn slot = its placeholder
            idx, a, q = S["ICONS16_PH"] + s - 20, S["ICONS16_INK_PH"], 0
        else:
            idx, a, q = I(rec[0]) - S["IT_BAG_LO"], ink(I(rec[0])), rec[1]
        for (dc, dr), want in icon(idx).items():
            if cell_bytes(fr, c + dc, r + dr) != want:
                bad.append((s, "icon", dc, dr))
            if attr_at(fr, c + dc, r + dr) & 0xC7 != a:
                bad.append((s, "ink", hex(attr_at(fr, c + dc, r + dr))))
        if any(cell_bytes(fr, c + 2, r + 1)) != (q >= 2):
            bad.append((s, "qty", q))
    # IC1: the description icon (cols 0-1, rows 18-19) = the cursor slot 0's (Heal)
    for (dc, dr), want in icon(I("P_HEAL") - S["IT_BAG_LO"]).items():
        if cell_bytes(fr, dc, 18 + dr) != want or attr_at(fr, dc, 18 + dr) != ink(I("P_HEAL")):
            bad.append(("desc", dc, dr))
    check("P6 page: 11 bag icons (IC1 16x16 icon, floor ink, QTY digit >= 2), 9 empty frames, worn W/A/C"
          " + the H placeholder ($05), description icon", ok and bad == [], (ok, bad[:6]))
    got = (p.rb("pg_n"), highlighted(fr), verbs(fr), p.rb("pg_use"))
    check("P6 ITEMS 11/20 (pg_n), cursor on slot 0 only, potion verbs DRINK / DISCARD / CLOSE",
          got == (11, ({0}, 4), (1, 0, 0, 1, 1), VB["DRINK"]), got)
    game.golden(p.h, "page_bag", fr)

    # ---- P7: cursor moves + wrap rules -----------------------------------------
    path = (("P", 1), ("O", 0), ("O", 4), ("A", 9), ("A", 14), ("A", 19), ("A", 23), ("P", 20), ("O", 23),
            ("A", CLOSE_SLOT), ("P", CLOSE_SLOT), ("A", 0), ("Q", CLOSE_SLOT), ("Q", 20), ("Q", 15), ("O", 19))
    bad = []
    for k, want in path:
        p.tap(k)
        hi = highlighted(p.frame())
        if hi != ({want}, len(rect_cells(want))):
            bad.append((k, want, hi))
    check("P7 cursor: L / R wrap in a row (5 bag, 4 worn, 1 [CLOSE]), U / D wrap over [CLOSE] / 4 bag rows / worn, "
          "remembered col (worn min(col, 3))", bad == [], bad[:4])

    # ---- P8: the verb-enable matrix ---------------------------------------------
    want = {0: (1, 0, 0, 1, 1), 2: (1, 0, 0, 1, 1), 3: (1, 0, 0, 1, 1), 4: (1, 0, 0, 1, 1), 5: (0, 1, 0, 1, 1),
            6: (0, 1, 0, 1, 1), 7: (0, 0, 0, 1, 1), 8: (0, 1, 0, 1, 1), 9: (0, 1, 0, 1, 1), 11: (0, 0, 0, 0, 1),
            20: (0, 0, 1, 0, 1), 22: (0, 0, 0, 0, 1), 23: (0, 0, 1, 0, 1), CLOSE_SLOT: (0, 0, 0, 0, 1)}
    use = {0: VB["DRINK"], 2: VB["EAT"], 3: VB["READ"], 4: VB["READ"], 5: 0, 7: 0, 20: 0}
    bad = []
    for s, w in want.items():
        okn = nav(s)
        got = verbs(p.frame())
        if not okn or got != w or (s in use and p.rb("pg_use") != use[s]):
            bad.append((s, okn, got, p.rb("pg_use")))
    check("P8 verbs: potion / food / scroll / book USE (DRINK / EAT / READ) + DISCARD; gear EQUIP + DISCARD; "
          "bow DISCARD; worn REMOVE; empty / [CLOSE]: CLOSE only", bad == [], bad[:4])

    # ---- P9: verb selection and the return protocol ----------------------------
    st0 = (bytes(z.read_memory(S["BAG"], 72)), p.rb("HAS_BOW"), tc())
    res = {}
    nav(5)                                         # Long Sword: EQUIP first
    p.tap("FIRE")
    sel = attr_at(p.frame(), 7, 20) & 0x38 == 0x08 and p.rb("pg_mode") == 1
    p.tap("FIRE")
    res["equip"] = (sel, wait_closed(), p.rb("PAGE_VERB"), p.rb("PAGE_VLAST"), p.rb("PAGE_SLOT"),
                    z.read_memory(S["BAG"] + 15, 1)[0] == I("W_SHORT"), z.read_memory(S["WORN"], 1)[0] == I("W_LONG"),
                    p.rb("HAS_BOW") == st0[1])
    p.settle(4)
    res["equip"] += (tc() == st0[2] + 1,)
    bag[5] = ("W_SHORT", 1)                        # 3E-T8: the swap (the old weapon took the slot)
    st0 = (st0[0], st0[1], tc())
    open_page()
    nav(CLOSE_SLOT)
    p.tap("FIRE")
    res["[close]"] = (wait_closed(), p.rb("PAGE_VERB"))
    p.settle(2)
    open_page()                                    # Heal x2: DRINK; L wraps to CLOSE, R back, R -> DISCARD
    p.tap("FIRE")
    seq = [p.rb("pg_vsel")]
    for k in ("O", "P", "P"):
        p.tap(k)
        seq.append(p.rb("pg_vsel"))
    p.tap("Q")                                     # back to the grid
    back = (p.rb("pg_mode"), highlighted(p.frame()))
    p.tap("FIRE")
    p.tap("CAPS", "SPACE")                         # BREAK in the strip
    res["strip"] = (seq, back, wait_closed(), p.rb("PAGE_VERB"))
    p.settle(2)
    open_page()                                    # food: USE, L -> CLOSE in the strip, FIRE
    nav(2)
    p.tap("FIRE")
    p.tap("O")
    p.tap("FIRE")
    res["close verb"] = (wait_closed(), p.rb("PAGE_VERB"), tc() == st0[2])
    check("P9 EQUIP: strip on EQUIP, FIRE closes, PAGE_VLAST / PAGE_SLOT = EQUIP / 5, PAGE_VERB consumed, applied "
          "(swap), 1 turn; "
          "[CLOSE] FIRE -> VB_NONE; strip L / R skip disabled verbs and wrap, U back, BREAK closes; CLOSE verb",
          res == {"equip": (True, True, 0, VB["EQUIP"], 5, True, True, True, True), "[close]": (True, 0),
                  "strip": ([0, 4, 0, 3], (0, ({0}, 4)), True, 0), "close verb": (True, 0, True)}, res)

    # DISCARD: the Heal stack (E_POT follows), then the bow (HAS_BOW 0); 0 turns
    p.settle(2)
    open_page()
    p.tap("FIRE")
    p.tap("P")
    p.tap("FIRE")
    d1 = (wait_closed(), p.rb("PAGE_VLAST"), p.rb("PAGE_SLOT"))
    p.settle(2)
    want_bag = [b for n, q in bag[1:] for b in (I(n), q, 0)]
    d1 += (list(z.read_memory(S["BAG"], 60)) == want_bag + [0] * (60 - len(want_bag)), p.ent(0)["POT"])
    open_page()
    n1 = p.rb("pg_n")
    nav(6)                                         # the bow moved up one slot
    p.tap("FIRE")
    p.tap("FIRE")
    d2 = (wait_closed(), p.rb("PAGE_VLAST"), p.rb("PAGE_SLOT"), p.rb("HAS_BOW"),
          I("BOW") not in list(z.read_memory(S["BAG"], 60))[0::3])
    p.settle(2)
    open_page()
    n2 = p.rb("pg_n")
    p.tap("I")
    wait_closed()
    check("P9 DISCARD: the whole Heal x2 stack (bag compacted, E_POT 1), then the bow (its only verb, HAS_BOW 0); "
          "ITEMS 11 -> 10 -> 9; 0 turns",
          (d1, d2, n1, n2, tc()) == ((True, VB["DISCARD"], 0, True, 1), (True, VB["DISCARD"], 6, 0, True), 10, 9,
                                     st0[2]), (d1, d2, n1, n2, tc() - st0[2]))

    # REMOVE: refused with a full bag (BAG FULL on row 22, page stays), the next key restores the help
    p.settle(2)
    put_bag([("F_APPLE", 1)] * 20)
    open_page()
    help0 = row22(p.frame())
    nav(20)
    p.tap("FIRE")
    p.tap("FIRE")
    r1 = (p.rb("PAGE_OPEN"), p.rb("pg_msgf"), row22(p.frame()) != help0, p.rb("PAGE_VERB"))
    p.tap("Q")                                     # any press: the help again (and back to the grid)
    r2 = (p.rb("pg_msgf"), row22(p.frame()) == help0)
    p.tap("CAPS", "SPACE")
    wait_closed()
    p.settle(2)
    put_bag(bag[1:7])
    open_page()
    nav(20)
    p.tap("FIRE")
    p.tap("FIRE")
    r3 = (wait_closed(), p.rb("PAGE_VLAST"), p.rb("PAGE_SLOT"), z.read_memory(S["WORN"], 1)[0] == 0,
          z.read_memory(S["BAG"] + 18, 1)[0] == I("W_LONG"))
    p.settle(4)
    r3 += (tc() == st0[2] + 1,)
    check("P9 REMOVE: full bag -> BAG FULL on row 22, page up, no verb; next key -> help; with room -> "
          "PAGE_VLAST REMOVE, slot 20, applied (W_LONG -> bag slot 6, weapon slot empty), 1 turn",
          (r1, r2, r3) == ((1, 1, True, 0), (0, True), (True, VB["REMOVE"], 20, True, True, True)), (r1, r2, r3))


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
