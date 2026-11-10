#!/usr/bin/env python3
"""TUT0-T9: the D0 tutorial suite (docs/design/tutorial_d0.md §10 items 1-15 -> C1..C15;
docs/design/tut0_split.md "T9"; memory-map "TUT0-T6" / "TUT0-T7").

Release build (DEBUG_KIT=0), SEED_FIXED via the cold-block `seed_fixed` / `seed_value`, a
real menu START with the tutorial path LIVE (Proto.tut_default_off = False: the choice screen
is offered). Every address comes from the .sym; the test-observable D0 state is TUT_RAM
(`TV_BEAT` / `TV_STAGE` / `TV_SPOT` / `TV_HOLD`). The book read, the eating, the cure and the
Sleep scroll go through the REAL bag page / ICON MODE (A+FIRE, cursor, FIRE), never a poke;
the Mage run opens the page with the I key, the others through the BAG icon.

  C1  `1` at the menu -> the choice screen (golden tut0_choice, es_go still the choice, the
      keys of the blob); `2` -> D1 == a plain legacy START (frames + hero state equal)
  C2  `1` -> D0: hero mid-ladder at room A's shaft top, mentor at A1 (his tile ids stamped in
      ROOM_MAP), the card + panel digit show 0, FOOD 40, LVL_DEPTH 1, pl_et = the turn stub
      (golden tut0_d0_arrival)
  C3  the scripted run B0 -> B15 in order, each beat's first line seen in the log (both
      classes; the stamped lines are the SRC text with the keys expanded)
  C4  skip run: shortest route, no read / eat / drink: grate shut until the Goblin dies, then D1
  C5  sandbox equality: the D1 after D0 == the D1 of a plain `2 START` (same fixed seed);
      only PU_POS / PU_ARR and the animated decor / flying-number phase are tolerated
  C6  once per load: after D1 entry the offer is gone (es_go = start_game); a game over -> menu
      -> `1` goes straight to D1
  C7  hold: 20 Waits at the door of C -> the Goblin's x unchanged and ASLEEP; one hit wakes it
  C8  mercy: HP poked to 3, one Wait -> HP = MAXHP and L50 in the log; no D0 turn leaves HP < 1
  C9  death fallback -> end card -> menu -> `1` -> the choice again, D0 rebuilt identically
  C10 blob bytes == the tape image (build/ovl/blob.bin) at every check, incl. after the bag
      page and the fight, and with garbage poked into bank 4 BLOB_ORG..$FFFF before boot
  C11 Kempston only (JOY_MIRROR): the whole D0 (bag READ, quick FOOD / SCROLL / POTION,
      the fight) without a key; a joystick FIRE dismisses a hold; lines show stick words
  C12 redefined keys W S K L M (through the real REDEFINE menu): L02 / L12 name them
  C13 no softlock: the key facts the walk relies on (grate reachable by walk + climb)
  C14 the mentor never appears in the D1 pool / screen after the reset
  C15 the goal is told: L54 / L55 in B1; L56-L58 after the Goblin dies, before the grate step
  TUT0-R2 (spec s13, s10 16-28): C16 the name (blob strings, choice golden); C17 pointers yield to the
  cursor (none in ICON MODE, retired, back with the nudge re-show); C18 the icon tour (I00 held once,
  one line per slot per class, no line for slots passed under auto-repeat, I02 after the read);
  C19 icon targets (B3 BAG held first, B5 FOOD); C20 bag READ stick-only; C21 the scroll from the icon
  (Warrior) and from the bag page (Mage); C22 the pit: leap (G0/G2 held, G1 not) and fall (L69+L10);
  C23 the B5 WEAK tail + the rule (WEAK refuses the leap silently, HUNGRY does not); C24 the nudge
  12 / 36 at B4, none in the fight; C25 L76 once; C26 Kempston tour (stick words, stick-dismissed
  in-mode hold swallowed); C27 pi_ic / pl_et restored after choice 2, D1 entry, death, Quit;
  C28 blob >= 600 B free, TUT_RAM_END <= PF_ROWF

Usage: ZRCP_PORT=10778 WZ_BUILD_DIR=<dir>/build python3 tests/tut0.py [--update-golden] [--only C3,C5]
Output: one line per check, then `tut0: N failed of M: ids`.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
_ARGV = list(sys.argv)
UPDATE = "--update-golden" in _ARGV
ONLY = set(_ARGV[_ARGV.index("--only") + 1].split(",")) if "--only" in _ARGV else None
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert (as page.py)
import game                                   # noqa: E402  (the golden() mechanism)
game.UPDATE = UPDATE
game.PNG_DIR = os.environ.get("TUT0_PNG") or None
import game_lib as G                          # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS, GS_PLAYING, GS_SELECT, GS_DEAD   # noqa: E402
import textpack as tp                         # noqa: E402

Proto.tut_default_off = False                 # the tutorial path is live (choice screen offered)
Proto.snd_mode = 2                            # SFX only: no Level Complete stinger hold on a descent

# --- text model: the source lines + the resident dictionary (to decode log_push streams) ---
IMG = tp.parse_emitted(os.path.join(G.BUILD_DIR, "text", "strings.asm"))
SRC = {}
for _l in open(os.path.join(REPO, "src/tut/tut_strings.txt")):
    _s = _l.rstrip("\n")
    if _s.strip() and not _s.lstrip().startswith("#") and " = " in _s:
        _k, _t = _s.split(" = ", 1)
        SRC[_k.strip()] = _t


def dec(bs):
    """A dictionary-token stream (log_push's HL) -> text."""
    out = []
    for a in bs:
        if a == 0:
            break
        if a < 0x80:
            out.append(chr(a))
        else:
            q = IMG[IMG.dict_off + a - 0x80]
            while True:
                c = IMG[q]
                q += 1
                out.append(chr(c & 0x7F))
                if c & 0x80:
                    break
    return "".join(out)


# --- inputs ---------------------------------------------------------------------------------
# logical controls (the PROTO scenario names Proto.hold maps onto the DEFAULT keys): P right, O left,
# Q up, A down, FIRE, "." wait. A scheme maps those to the physical keys / stick bits of the run.
BIT = dict(P=1, O=2, A=4, Q=8, FIRE=16)                         # JOY_R_BIT.. (Kempston bit order R L D U F)
REDEF = dict(Q=(2, 1), A=(1, 1), O=(6, 2), P=(6, 1), FIRE=(7, 2))   # W S K L M (the five prompts UP DOWN LEFT RIGHT FIRE)
REDEF_KEYS = ["W", "S", "K", "L", "M"]
RAW = {"W": (2, 1), "S": (1, 1), "K": (6, 2), "L": (6, 1), "M": (7, 2)}   # physical keys the redefine test taps


class TP(Proto):
    """Proto + the control scheme + a log recorder (every log_push of the engine and the blob)."""
    proto_start = 0                                              # the generated D1 start
    scheme = "keys"
    LOG = None
    mturn = None                                                 # tests/budget.py: a measured turn(*keys) / wait(cond) replace
    mwait = None                                                 # the plain ones (the T-state of every play tick is recorded)
    dismissed = 0                                                # holds dismissed by the driver
    run = None                                                   # the Run tracing beats (note() at every hold)
    page_via = "icon"                                            # how the bag page opens: BAG icon / the I key
    scroll_via = "icon"                                          # R2 C21: the Sleep scroll from the SCROLL icon / the bag page
    hold_marks = None                                            # R2: len(LOG) at every hold dismissed (held(): which group held)

    def hold(self, *keys):
        rows, joy = [0xFF] * 8, 0
        for k in keys:
            if k.startswith("raw:"):                             # a physical key by name (the scenario aliases L / K stay logical)
                r, b = RAW[k[4:]]
                rows[r] &= ~(1 << b) & 0xFF
                continue
            k = self.NEW_KEYS.get(k, k)
            if k == "SPACE":
                k = "FIRE"
            if k == "." and self.scheme in ("kemp", "redef"):     # WAIT = DOWN alone on a floor (no SYMBOL SHIFT key)
                k = "A"
            if k in BIT and self.scheme == "kemp":
                joy |= BIT[k]
                continue
            if k in BIT and self.scheme == "redef":
                r, b = REDEF[k]
                rows[r] &= ~(1 << b) & 0xFF
                continue
            if k == ".":                                         # WAIT = SYMBOL SHIFT + M
                rows[7] &= ~0x06 & 0xFF
                continue
            if k in RAW:
                r, b = RAW[k]
            else:
                r, b = G.KEYS["FIRE" if k == "SPACE" else k]
            rows[r] &= ~(1 << b) & 0xFF
        self.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(str(x) for x in rows)))
        if self.scheme == "kemp":
            self.wb("JOY_MIRROR", joy)

    def release(self):
        Proto.release(self)
        if self.scheme == "kemp":
            self.wb("JOY_MIRROR", 0)

    def tick(self, n=1):
        for _ in range(n):
            while True:
                Proto.tick(self, 1)
                if self.LOG is not None and self.pc() == S["log_push"]:
                    r = self.z.cmd("get-registers")
                    hl = int(re.search(r"HL=([0-9a-fA-F]{4})", r).group(1), 16)
                    self.LOG.append(dec(self.z.read_memory(hl, 40)))
                    continue
                break

    def arm_log(self):
        self.LOG = []
        self.extra_probes = {S["log_push"]}
        self.z.cmd("set-breakpoint 20 PC=%d" % S["log_push"])

    def seen(self, text):
        return any(text == l.rstrip() for l in self.LOG)


CHECKS = []                                                      # (id, ok, detail)


def check(cid, name, ok, detail=""):
    if ONLY is not None and cid not in ONLY:
        return ok
    CHECKS.append((cid, bool(ok), name))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {name}" + ("" if ok else f"  <- {detail}"), flush=True)
    return ok


# --- drive helpers ----------------------------------------------------------------------------
def tv(p, name):
    return p.rb(S[name])


def w2(p, a):
    return p.rb(a) | p.rb(a + 1) << 8


def st(p):
    e = p.ent(0)
    return (f"beat {tv(p, 'TV_BEAT')} stage {tv(p, 'TV_STAGE')} spot {tv(p, 'TV_SPOT')} room {p.rb('CUR_ROOM')} "
            f"x {e['X']} y {e['Y']} hp {e['HP']}/{e['MAXHP']} food {p.rb('FOOD')} gs {p.rb('GAME_STATE')}")


def anykey(p):
    """The key a hold waits for: ENTER on the keyboard, the FIRE stick / key otherwise."""
    return "ENTER" if p.scheme == "keys" else "FIRE"


def dismiss(p, max_frames=400):
    """While a group holds (TV_HOLD = 1): keys up, the queue drawn (tt_hold waits for LOG_QN = 0), a
    key down, up again. True if a hold was dismissed."""
    if not tv(p, "TV_HOLD"):
        return False
    p.release()
    for _ in range(max_frames):
        p.tick()
        if p.rb("LOG_QN") == 0:
            break
    p.tick(2)
    if p.run is not None:                                        # TUT0-R2: after the drain (a held group's pointer
        p.run.note()                                             # is drawn by tt_hold once the queue is drawn)
    if p.LOG is not None:
        p.hold_marks.append(len(p.LOG))                          # R2: the held group = the lines logged just before
    p.hold(anykey(p))
    p.tick(2)
    p.dismissed += 1
    p.release()
    for _ in range(20):
        p.tick()
        if not tv(p, "TV_HOLD"):
            break
    p.tick(2)
    return True


def T(p, *keys):
    """One turn from the keys (Proto.turn), then every hold it raised is dismissed."""
    ok = p.mturn(*keys) if p.mturn else p.turn(*keys)
    while dismiss(p):
        pass
    if p.run is not None:
        p.run.note()
    return ok


def settle_holds(p):
    while dismiss(p):
        pass
    if p.run is not None:
        p.run.note()


def walk_to(p, x, maxn=40):
    for _ in range(maxn):
        e = p.ent(0)
        if e["X"] == x:
            return True
        if not T(p, "L" if e["X"] < x else "H"):
            return False
    return p.ent(0)["X"] == x


def down(p, n=12, room=None):
    for _ in range(n):
        T(p, "J")
        if room is not None and p.rb("CUR_ROOM") == room:
            return True
    return room is None


def icon_mode(p, on=True):
    """ICON MODE: DOWN + FIRE (the taught gesture, L12); UP leaves it."""
    if bool(p.rb("ICON_MODE")) == on:
        return True
    if on:
        p.hold("J", "FIRE")
        p.tick(2)
        p.release()
        p.tick(2)
        settle_holds(p)                                          # TUT0-R2: the first entry holds I00a / I00b
    else:
        p.tap("K")
        p.tick(1)
    return bool(p.rb("ICON_MODE")) == on


def cursor_to(p, slot):
    """The icon cursor to `slot` (0-based) by LEFT / RIGHT taps (ICON MODE)."""
    for _ in range(14):
        cur = p.rb("SEL_SLOT")
        if cur == slot:
            return True
        p.tap("L" if cur < slot else "H")
        p.tick(1)
    return p.rb("SEL_SLOT") == slot


def fire_turn(p, max_ticks=300):
    """FIRE tap (a use in ICON MODE), run to the end of the turn it starts; holds dismissed.
    True if the turn counter moved."""
    t0 = p.rw("TURN_COUNTER")
    if p.mturn:
        p.mturn("FIRE")
        settle_holds(p)
        return p.rw("TURN_COUNTER") != t0
    p.hold("FIRE")
    p.tick(2)
    p.release()
    for _ in range(max_ticks):
        p.tick()
        if tv(p, "TV_HOLD"):
            break
        if p.rw("TURN_COUNTER") != t0 and p.idle():
            break
    p.tick(1)
    settle_holds(p)
    p.tick(2)
    return p.rw("TURN_COUNTER") != t0


def quick(p, icon):
    """Quick use of the ICON_* slot (ICON MODE, cursor, FIRE) -> True if a turn passed."""
    icon_mode(p, True)
    cursor_to(p, icon)
    ok = fire_turn(p)
    icon_mode(p, False)
    return ok


def bag_slot(p, typ):
    b = p.z.read_memory(S["BAG"], 3 * S["BAG_SLOTS"])
    for i in range(S["BAG_SLOTS"]):
        if b[3 * i] == typ:
            return i
    return None


def rc(p):
    return p.rb("pg_rc"), p.rb(S["pg_rc"] + 1)


def page_is_open(p):
    return p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]


def open_page(p, via="icon"):
    """The bag page: via the BAG icon (ICON MODE) or the I key."""
    if via == "I":
        p.tap("I")
    else:
        icon_mode(p, True)
        cursor_to(p, S["ICON_BAG"])
        p.hold("FIRE")
        p.tick(2)
        p.release()
        p.tick(1)
    return p.until(lambda: page_is_open(p), 12)


def page_nav(p, slot):
    """Cursor onto bag slot `slot` (row 1 + slot // 5, col slot % 5; row 0 = [CLOSE])."""
    row, col = 1 + slot // 5, slot % 5
    for _ in range(8):
        if rc(p)[0] == row:
            break
        p.tap("J" if (row - rc(p)[0]) % 6 <= 3 else "K")
    for _ in range(6):
        if rc(p)[1] == col:
            break
        p.tap("L")
    return rc(p) == (row, col)


def page_use(p, typ, via="icon"):
    """Open the page, cursor on the item `typ`, FIRE (the verb strip: the first verb = USE /
    DRINK / READ), FIRE (apply) -> the page closes and the use turn runs. True if a turn passed."""
    s = bag_slot(p, typ)
    if s is None or not open_page(p, via):
        return False
    t0 = p.rw("TURN_COUNTER")
    if not page_nav(p, s):
        return False
    p.tap("FIRE")
    p.tap("FIRE")
    p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
    done = lambda: tv(p, "TV_HOLD") or (p.rw("TURN_COUNTER") != t0 and p.idle())      # noqa: E731
    if p.mwait:
        p.mwait(done)
    else:
        for _ in range(300):
            p.tick()
            if done():
                break
    p.tick(1)
    settle_holds(p)
    p.tick(2)
    if p.rb("ICON_MODE"):
        icon_mode(p, False)
    if p.run is not None:
        p.run.blob_check("after the bag page")
    return p.rw("TURN_COUNTER") != t0


def blob_bytes(p):
    """BLOB_ORG.. of bank 4 (the machine RAM zone), len(blob.bin) bytes."""
    n = len(BLOB_IMAGE)
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(4 * 16384 + S["BLOB_ORG"] - 0xC000, n))
    finally:
        p.z.cmd("set-memory-zone -1")


BLOB_IMAGE = open(os.path.join(G.BUILD_DIR, "ovl", "blob.bin"), "rb").read()
# the mentor's tile ids (TUT0-F1): TUT0_MENTOR_N ids from TUT0_MENTOR_ID0, cell (5, 2) takes none (0); right / left tables in the blob
MID0, MN = S["TUT0_MENTOR_ID0"], S["TUT0_MENTOR_N"]
MENTOR_IDS = range(MID0, MID0 + MN)
MENTOR_R = list(BLOB_IMAGE[S["tut0_mentor_ids"] - S["BLOB_ORG"]:][:18])
MENTOR_L = list(BLOB_IMAGE[S["tut0_mentor_ids_l"] - S["BLOB_ORG"]:][:18])


def press_start(p, key, target):
    """Hold `key` until the game start `target` begins (the human's tap ends long before the ~1 s level build), then
    release: a key still down when D0 / D1 starts would be read as a play key (slot select '2': NOT LEARNED)."""
    p.hold(key)
    p.z.cmd("set-breakpoint 21 PC=%d" % S[target])
    try:
        for _ in range(60):
            p.z.cmd("cpu-step")
            r = p.z.cmd("run %d" % G.RUN_LIMIT)
            if p.pc() == S[target]:
                break
        else:
            raise RuntimeError("%s never started" % target)
    finally:
        p.z.cmd("set-breakpoint 21")
        p.release()
    p.z.cmd("cpu-step")
    ok = p.wait_state(GS_PLAYING)
    return ok


def garbage_bank4(p):
    """Junk over bank 4 BLOB_ORG..$FFFF (before the boot code runs): the boot must (re)build the blob itself."""
    n = 0x10000 - S["BLOB_ORG"]
    p.z.cmd("set-memory-zone 0")
    try:
        base = 4 * 16384 + S["BLOB_ORG"] - 0xC000
        for i in range(0, n, 64):
            p.z.cmd("write-memory %d %s" % (base + i, " ".join(str((i * 7 + j * 13 + 0xA5) & 255) for j in range(64))))
    finally:
        p.z.cmd("set-memory-zone -1")


def start(h, hero=0, seed=1, scheme="keys", via_menu=None, boot_garbage=False, path="d0"):
    """Fresh load -> menu (SEED_FIXED, ANIM_FREEZE) -> hero -> then by `path`:
    "menu"    stop at the menu;
    "choice"  `1` START: stop at the choice screen;
    "d0"      ... `1` = TUTORIAL: D0 running (the TP, scheme = the run's control scheme);
    "choice2" ... `2` = START: the D1 through the choice screen;
    "plain"   the legacy path (tut_off: es_go -> start_game): a plain `2 START`'s D1 (what the suites do).
    via_menu(p) runs at the menu (REDEFINE / the Kempston pick)."""
    p = TP(h)
    p.hold_marks = []
    p.scheme = "keys"                                            # the menu is the keyboard's
    p.load()
    if boot_garbage:
        garbage_bank4(p)
    p.arm_log()
    p.wb("seed_fixed", 1)
    p.wb("seed_value", seed & 255)
    p.wb(S["seed_value"] + 1, seed >> 8)
    assert p.wait_state(GS_SELECT), "no menu"
    if path == "plain":
        p.tut_off()
    p.wb("INPUT_SRC", 1)
    p.wb("ANIM_FREEZE", 1)
    p.release()
    p.tick(2)
    for _ in range(2):
        if p.rb("menu_hero") == hero:
            break
        p.tap("2")
    if via_menu:
        via_menu(p)
    if path == "menu":
        return p
    if path == "plain":
        assert press_start(p, "1", "start_game"), "plain START did not start"
        p.tick(3)
        return p
    p.hold("1")                                                  # START
    p.tick(3)
    p.release()
    p.tick(3)
    if path == "choice":
        return p
    p.scheme = scheme
    assert press_start(p, "1" if path == "d0" else "2", "tut_d0" if path == "d0" else "start_game"), "the game did not start"
    p.tick(3)
    return p


# --- the scripted D0 run ----------------------------------------------------------------------
VERBOSE = bool(os.environ.get("TUT0_VERBOSE"))
QS_FOOD_ICON = S["QS_SLOT0"] + S["QS_FOOD"]                     # the quick slots (icon index)
QS_POTION_ICON = S["QS_SLOT0"] + S["QS_POTION"]
QS_SCROLL_ICON = S["QS_SLOT0"] + S["QS_SCROLL"]
STAND_Y = (S["STAND_Y0"], S["STAND_Y1"])


PTR_RECTS = [(18, 27, 3, 2), (18, 18, 3, 2), (18, 21, 3, 2), (18, 24, 3, 2), (21, 30, 2, 1), (21, 0, 30, 1), (20, 0, 26, 1)]  # tut_rects (row, col, w, h)


class Run:
    """The beat / room trace of one D0 run (sampled after every turn)."""
    def __init__(self, p):
        self.p, self.beats, self.rooms, self.blob_bad = p, [], [], []
        self.grate, self.grate_post, self.exit_mark, self.used_heal, self.blocked = [], [], 0, False, []
        self.ptr_bad, self.ptr_seen, self.ptr_cells = [], set(), 0
        self.wake_mark = None
        p.run = self
        self.note()

    def ptr_check(self):
        """V3 sampler: with a pointer up, no blank rect cell (8 bitmap bytes 0) has FLASH, every non-blank one has."""
        pid = tv(self.p, "TV_PTR")
        if pid == 0xFF or pid >= len(PTR_RECTS):
            return
        fr = self.p.frame()
        r0, c0, w, h = PTR_RECTS[pid]
        self.ptr_seen.add(pid)
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                self.ptr_cells += 1
                flash = bool(G.attr_at(fr, c, r) & 0x80)
                if flash == (not any(G.cell_bytes(fr, c, r))):
                    self.ptr_bad.append((tv(self.p, 'TV_BEAT'), self.p.rb('PANEL_DIRTY'), pid, (c, r), flash, G.cell_bytes(fr, c, r).hex(), hex(self.p.rb(0x5800 + 32 * r + c)),
                                         bytes(self.p.z.read_memory(0x4000 + ((r & 24) << 8) + ((r & 7) << 5) + c, 1)).hex()))

    def note(self):
        self.ptr_check()
        b = tv(self.p, "TV_BEAT")
        if not self.beats or self.beats[-1] != b:
            self.beats.append(b)
            if VERBOSE:
                print(f"   beat -> {b}: {st(self.p)}", flush=True)
        r = self.p.rb("CUR_ROOM")
        if not self.rooms or self.rooms[-1] != r:                # C10: the blob after every room change
            self.rooms.append(r)
            self.blob_check("room %d" % r)

    def blob_check(self, tag):
        if self.p.rb("GAME_STATE") == GS_PLAYING and w2(self.p, S["pl_et"] + 1) == S["ts_turn"]:
            if blob_bytes(self.p) != BLOB_IMAGE:
                self.blob_bad.append(tag)
            self.blob_n = getattr(self, "blob_n", 0) + 1


def storey(p):
    return 0 if p.ent(0)["Y"] <= STAND_Y[0] else 1


def goblin(p):
    """(slot, entity) of the live Goblin in CUR_ROOM, else None."""
    for s in range(1, 9):
        e = p.ent(s)
        if e["FLAGS"] & G.EF_ACTIVE and e["KIND"] == G.K_GOBLIN and e["ROOM"] == p.rb("CUR_ROOM"):
            return s, e
    return None


def to_floor(p, s, room=None, n=14):
    """DOWN until standing on storey s (or the room changes to `room`)."""
    for _ in range(n):
        if room is not None and p.rb("CUR_ROOM") == room:
            return True
        if room is None and p.ent(0)["Y"] >= STAND_Y[s]:
            return True
        T(p, "J")
    return room is None and p.ent(0)["Y"] >= STAND_Y[s]


def leg(p, run, x):
    ok = walk_to(p, x)
    if not ok:
        run.blocked.append((x, st(p)))
    return ok


def go_to_C(p, run, full, pit=False):
    """From the D0 start to the door of room C. full: read the book, eat, drink the cure through the
    page / icons (the taught route); else the shortest walk (no read / eat / drink)."""
    to_floor(p, 0)                                               # B0: 2 DOWN turns to storey 0
    run.note()
    if full:
        leg(p, run, 16)
        run.note()
        T(p, "K", "L")                                           # B2: U + R leaps the pit
        T(p, "L")                                                # the BOOK (col 24)
        run.note()
        page_use(p, S["IT_BOOK"], p.page_via)                    # B3: READ from the bag page
        run.note()
        T(p, "WAIT")
        leg(p, run, 26)
        to_floor(p, 1)                                           # B4: L2 down
        run.note()
        T(p, "WAIT")
        leg(p, run, 17)                                           # the PEAR (col 17)
        run.note()
        quick(p, QS_FOOD_ICON)                                   # B5: the FOOD icon
        run.note()
        T(p, "WAIT")
    elif pit:                                                    # C13: no ladder, walk off into the pit (cols 19..21): a fall
        for _ in range(40):
            if p.ent(0)["Y"] >= STAND_Y[1] or p.ent(0)["Y"] > STAND_Y[0] + 2:
                break
            T(p, "L")
        to_floor(p, 1)
        run.note()
    else:
        leg(p, run, 12)
        to_floor(p, 1)
        run.note()
    leg(p, run, 5)
    to_floor(p, 1, room=4)                                       # B6: the shaft down -> room B
    run.note()
    to_floor(p, 0)
    T(p, "WAIT")
    leg(p, run, 19 if full else 24)                               # B8: the dart (col 13) on the way, B9 the CURE (col 19)
    run.note()
    if full:
        T(p, "WAIT")
        page_use(p, S["IT_P_CURE"], p.page_via)                  # B9: DRINK from the bag
        run.note()
        T(p, "WAIT")
        leg(p, run, 24)
    to_floor(p, 1)
    run.note()
    for _ in range(12):                                          # B10: the door (the bump opens it with the key)
        if p.rb("CUR_ROOM") == 5:
            break
        T(p, "L")
    run.note()
    return p.rb("CUR_ROOM") == 5


def fight(p, run, use_scroll, n=70):
    """Walk right into the Goblin until it dies; with use_scroll, read the Sleep scroll through the ICON MODE
    once it is awake and near (B13), and keep striking. Returns (dead, used)."""
    used, waits = False, 0
    for _ in range(n):
        if run.wake_mark is None and tv(p, "TV_BEAT") >= 12:    # R2 C24: the Goblin woke (B12)
            run.wake_mark = len(p.LOG) if p.LOG is not None else 0
        run.grate.append(p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"])
        if p.rb("ST1_KILLS"):
            return True, used
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
        g = goblin(p)
        if (use_scroll and not used and g and bag_slot(p, S["IT_S_SLEEP"]) is not None
                and tv(p, "TV_BEAT") >= 12 and p.rb(S["ST_FLAGS"] + g[0]) & S["STS_HOLD"] != S["HOLD_ASLEEP"]):
            prompt = tv(p, "TV_BEAT") >= 13 if p.mturn else p.seen(line("TL_L39", p.scheme))   # (no log capture while measuring)
            if not prompt and waits < 3:
                waits += 1
                T(p, "WAIT")                                     # B13's prompt (L39 / L40) shows after the wake
                continue
            if (page_use(p, S["IT_S_SLEEP"], p.page_via) if p.scroll_via == "bag" else quick(p, QS_SCROLL_ICON)):
                used = True
                continue
        T(p, "L")
    run.blob_check("after the fight")
    return bool(p.rb("ST1_KILLS")), used


def after_fight_to_exit(p, run, heal=False, waits=0):
    """The Goblin is dead: (optionally) heal and wait out `waits` turns, then walk STRAIGHT to the grate and step into it
    (the grate opens after the 3rd victory group). run.exit_mark = len(p.LOG) before the turn that leaves D0.
    True once the D1 start was seen (es_go = start_game, playing)."""
    if heal and p.ent(0)["HP"] < p.ent(0)["MAXHP"] and bag_slot(p, S["IT_P_HEAL"]) is not None:
        quick(p, QS_POTION_ICON)                                 # L48: HURT? DRINK THE HEAL POTION
        run.used_heal = True
    for _ in range(waits):
        T(p, "WAIT")
    gx = 22                                                      # the grate {22,2}: cols 22-24, the storey-1 floor
    for _ in range(40):
        e = p.ent(0)
        run.grate_post.append(p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"])
        if e["X"] == gx:
            break
        run.exit_mark = len(p.LOG)
        T(p, "L" if e["X"] < gx else "H")
    run.blob_check("at the grate")
    for _ in range(10):                                          # DOWN into the grate (shut until the 3rd group is shown)
        run.grate_post.append(p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"])
        run.exit_mark = len(p.LOG)
        T(p, "J")
        if w2(p, S["es_go"] + 1) == S["start_game"]:
            return True
    return False


def run_d0(p, run, full=True, scroll=True):
    ok = go_to_C(p, run, full)
    dead, used = fight(p, run, scroll and full)
    return ok, dead, used


# --- state snapshots (C5 / C9 / C14) -------------------------------------------------------------
# name -> (address, length). PU_POS (word) / PU_ARR (byte) are the pickup tracker: the D0 hero's last
# pickup x / room survive the reset (tolerated, C5: no game rule reads them before the first pickup,
# which rewrites both). The decor / drip animation phase and flying numbers live in screen-only state.
PU_MASK = range(S["PU_POS"], S["PU_ARR"] + 1)
SNAP = [("ITEM_RAM", S["ITEM_RAM"], S["ITEM_RAM_END"] - S["ITEM_RAM"]),
        ("ents", S["P_ENTITIES"], S["P_MAX_ENT"] * S["P_ENT_STRIDE"]),
        ("ST_FLAGS..", S["ST_FLAGS"], 0x100),
        ("HERO3D", S["HERO3D"], S["ST_HERO_END"] - S["HERO3D"]),
        ("HERO_ST", S["HERO_ST"], S["HERO_ST_END"] - S["HERO_ST"]),
        ("LVL_STATE", S["LVL_STATE"], S["LVL_STATE_END"] - S["LVL_STATE"]),
        ("LP_STATE", S["LP_STATE"], S["LP_END"] - S["LP_STATE"]),
        ("ROOM_MAP", S["ROOM_MAP"], 32 * G.PLAY_ROWS),
        ("TILE_GLYPHS", S["TILE_GLYPHS"], 0x340),
        ("tile_flags", S["tile_flags"], 0x40),
        ("scalars", S["TURN_COUNTER"], 2),
        ("RNG_STATE", S["RNG_STATE"], 2),
        ("CUR_ROOM", S["CUR_ROOM"], 1),
        ("HERO_KIND", S["HERO_KIND"], 1)]


def snapshot(p):
    d = {n: bytes(p.z.read_memory(a, ln)) for n, a, ln in SNAP}
    d["frame"] = bytes(p.frame())
    return d


def snap_diff(a, b, skip_frame=False):
    """[(region, [(offset, a, b)...])] of the regions that differ (PU_POS / PU_ARR masked)."""
    out = []
    for n, addr, ln in SNAP:
        bad = [(i, a[n][i], b[n][i]) for i in range(ln)
               if a[n][i] != b[n][i] and not (n == "HERO_ST" and addr + i in PU_MASK)]
        if bad:
            out.append((n, bad))
    if not skip_frame and a["frame"] != b["frame"]:
        bad = [(i, a["frame"][i], b["frame"][i]) for i in range(G.SCREEN_FRAME_LEN) if a["frame"][i] != b["frame"][i]]
        out.append(("frame", bad))
    return out


# --- expected text ---------------------------------------------------------------------------
KN = {"keys": dict(U="Q", D="A", L="O", R="P", F="SP"),         # the 2-char REDEFINE names of the default keys
      "redef": dict(U="W", D="S", L="K", R="L", F="M"),
      "kemp": dict(U="UP", D="DOWN", L="LEFT", R="RIGHT", F="FIRE")}   # Kempston: the stick words
CLS = {0: "W", 1: "M"}


def line(key, scheme="keys"):
    t = SRC[key]
    for tok, nm in KN[scheme].items():
        t = t.replace("{" + tok + "}", nm)
    return t.rstrip()


def first_lines(hero):
    """Each beat's first line (spec s3), in play order; class pairs by hero."""
    c = CLS[hero]
    return ["L01", "L03", "L05", "L54", "L65", "L08", "L67", "L11", "L60", "L13", "L14" + c, "L63", "L16", "L17", "L19", "L21",
            "L70", "L23", "L24",
            "L26", "L28", "L30b", "L31", "L33", "L34", "L35" + c, "L37", "L38" + c, "L39", "L41", "L42", "L56", "L57",
            "L58", "L59", "L43", "L44", "L46", "L47"]


def log_order(p, keys, scheme="keys"):
    """(missing ids, out-of-order ids): `keys` must appear in p.LOG in that order."""
    pos, missing, late = -1, [], []
    lines = [l.rstrip() for l in p.LOG]
    for k in keys:
        want = line("TL_" + k, scheme)
        try:
            i = lines.index(want, pos + 1)
            pos = i
        except ValueError:
            (late if want in lines else missing).append(k)
    return missing, late


# --- D1 comparison (C5): the tolerated phases --------------------------------------------------
def anim_cells(snap_p):
    """(col, row) of the animated-decor entries (ANIM_LIST) + the drip overlay cells of a live game."""
    n = snap_p.rb("ANIM_N")
    b = snap_p.z.read_memory(S["ANIM_LIST"], 4 * 12)
    cells = {(b[4 * i], b[4 * i + 1]) for i in range(min(n, 12))}
    d = snap_p.z.read_memory(S["DRIP_COL"], 4)               # COL, ROW, DRAWN, N
    if d[3] and d[1] < G.PLAY_ROWS:
        cells |= {(d[0], d[1]), (d[0], d[1] - 1)}
    return cells


def frame_cell_diff(fa, fb):
    cells = set()
    for r in range(24):
        for c in range(32):
            if G.attr_at(fa, c, r) != G.attr_at(fb, c, r) or G.cell_bytes(fa, c, r) != G.cell_bytes(fb, c, r):
                cells.add((c, r))
    return cells


def d1_equal(a, b, tol):
    """Problems between two D1 snapshots (empty = equal). Tolerated, and only these: PU_POS / PU_ARR
    (pickup tracker), the decor frame phase (ROOM_MAP ids + the screen cells of the ANIM_LIST entries) and the drip
    overlay cells (`tol` = the cells, read from the live games)."""
    bad = []
    for n, diffs in snap_diff(a, b, skip_frame=True):
        if n == "ROOM_MAP":
            diffs = [(i, x, y) for i, x, y in diffs if (i % 32, i // 32) not in tol]
        if diffs:
            bad.append((n, diffs[:4]))
    cells = frame_cell_diff(a["frame"], b["frame"]) - tol
    if cells:
        bad.append(("frame cells", sorted(cells)[:8]))
    return bad


# --- scenarios -----------------------------------------------------------------------------------
SHARED = {}                                                     # state handed between scenarios (the D1 snapshots)


def d1_after(p, ticks=60):
    """Settled D1 snapshot (the log's lines drawn, the decor phase is whatever it is)."""
    p.tick(ticks)
    return snapshot(p), anim_cells(p)


def check_blob(cid, p, name):
    ok = blob_bytes(p) == BLOB_IMAGE
    check(cid, name, ok, "bank 4 BLOB_ORG.. != build/ovl/blob.bin")
    return ok


def scen_plain(h):
    """The legacy `2 START` D1 (the reference) and the choice screen's `2` -> D1 (C1)."""
    p = start(h, 0, path="plain")
    SHARED["plain"] = d1_after(p)
    check("C1", "legacy START (tutorial path off) = the reference D1: depth 1, D1 room, pl_et = end_turn",
          p.rb("LVL_DEPTH") == 1 and w2(p, S["pl_et"] + 1) == S["end_turn"], (p.rb("LVL_DEPTH"), hex(w2(p, S["pl_et"] + 1))))
    p = start(h, 0, path="choice")
    ch = p.frame()
    ok = (p.rb("GAME_STATE") == GS_SELECT and w2(p, S["es_go"] + 1) == S["ts_choice"] and w2(p, S["pl_et"] + 1) == S["end_turn"])
    check("C1", "`1` START -> the choice screen (menu state, es_go = the blob's choice, no D0 hook yet)", ok,
          (p.rb("GAME_STATE"), hex(w2(p, S["es_go"] + 1))))
    game.golden(h, "tut0_choice", ch)
    press_start(p, "2", "start_game")
    p.tick(3)
    d2, a2 = d1_after(p)
    ref, aref = SHARED["plain"]
    bad = d1_equal(ref, d2, a2 | aref)
    check("C1", "`2` at the choice -> D1 exactly as a plain START (state + screen; decor / drip phase tolerated)", not bad, bad)
    check("C6", "after `2`: no more offer (es_go = start_game), D1 hooks (pl_et = end_turn)",
          w2(p, S["es_go"] + 1) == S["start_game"] and w2(p, S["pl_et"] + 1) == S["end_turn"], hex(w2(p, S["es_go"] + 1)))
    check("C27", "after choice `2` (D1): pi_ic = intent_icon7, pl_et = end_turn", hooks_off(p), hex(w2(p, S["pi_ic"] + 1)))
    SHARED["choice2"] = (d2, a2)
    p = start(h, 0, path="choice")                               # ENTER = TUTORIAL (the newcomer nudge)
    ok = press_start(p, "ENTER", "tut_d0")
    p.tick(3)
    check("C1", "ENTER at the choice = TUTORIAL (D0 hooks live)", ok and w2(p, S["pl_et"] + 1) == S["ts_turn"],
          hex(w2(p, S["pl_et"] + 1)))


def mentor_cells(p):
    """The 18 ROOM_MAP cells of the mentor box at A1 (room A, box left 9, top row 1) and their ids."""
    return [p.rb(S["ROOM_MAP"] + 32 * (1 + i // 3) + 9 + i % 3) for i in range(18)]


def arrival_checks(p, hero, tag):
    e = p.ent(0)
    check("C2", f"{tag}: D0 starts in room A, hero mid-ladder at the shaft top (x 5, y 0), HP full",
          (p.rb("CUR_ROOM"), e["X"], e["Y"]) == (1, 5, 0) and e["HP"] == e["MAXHP"] and p.rb("HERO_KIND") == hero,
          (p.rb("CUR_ROOM"), e["X"], e["Y"], e["HP"], e["MAXHP"]))
    ids = mentor_cells(p)
    check("C2", f"{tag}: the mentor stands at A1 (his {MN} tile ids {MID0}.. stamped in ROOM_MAP, a facing table)", ids in (MENTOR_R, MENTOR_L), ids)
    check("C2", f"{tag}: FOOD = 40, DEPTH stays 1, the turn hook is the blob's (pl_et = ts_turn), choice offer still armed",
          p.rb("FOOD") == 40 and p.rb("LVL_DEPTH") == 1 and w2(p, S["pl_et"] + 1) == S["ts_turn"]
          and w2(p, S["es_go"] + 1) == S["ts_choice"], (p.rb("FOOD"), p.rb("LVL_DEPTH"), hex(w2(p, S["pl_et"] + 1))))
    check("C2", f"{tag}: B0 on arrival (TV_BEAT 0, the mentor at spot A1)", (tv(p, "TV_BEAT"), tv(p, "TV_SPOT")) == (0, 0),
          (tv(p, "TV_BEAT"), tv(p, "TV_SPOT")))
    fr = p.frame()
    dig = G.cell_bytes(fr, 31, 18)
    check("C2", f"{tag}: the panel depth digit cell (31, 18) is drawn (not blank)", any(dig), dig.hex())
    SHARED["d0_digit"] = dig
    return fr


def scen_full(h, hero, via, name, final, scheme="keys", via_menu=None):
    """A whole D0 run of the taught route (read the book, eat the pear, drink the cure through the page / icons),
    the fight with the Sleep scroll, then straight to the grate."""
    t0 = time.monotonic()
    p = start(h, hero, scheme=scheme, via_menu=via_menu)
    p.page_via = via
    p.scroll_via = "bag" if (hero == 1 and scheme == "keys") else "icon"    # R2 C21: run B = the bag page
    run = Run(p)
    tag = f"{name} run"
    check("C10", f"{tag}: blob bytes == the image at the D0 start", blob_bytes(p) == BLOB_IMAGE)
    p.tick(3)
    fr = arrival_checks(p, hero, tag)
    if final:
        game.golden(h, "tut0_d0_arrival", fr)
        SHARED["mentor_glyphs"] = {bytes(p.z.read_memory(S["TILE_GLYPHS"] + 8 * i, 8)) for i in MENTOR_IDS} - {bytes(8)}
    ok = go_to_C(p, run, True)
    check("C3", f"{tag}: B0-B10 walked (the book read from the page, the pear eaten, the cure drunk) to room C", ok, st(p))
    check("V3", f"{tag}: no blank cell in a pointer rect has FLASH set; non-blank cells do ({run.ptr_cells} cells, rects seen {sorted(run.ptr_seen)})",
          not run.ptr_bad and run.ptr_cells > 0, run.ptr_bad[:4])
    arank_mid = p.rb("ARANK")
    check("C3", f"{tag}: bag READ turned the page: ARANK != 0, the book is gone",
          p.rb("ARANK") != 0 and bag_slot(p, S["IT_BOOK"]) is None, p.rb("ARANK"))
    nf = len(p.LOG)
    dead, used = fight(p, run, True)
    check("C3", f"{tag}: the Goblin was struck, the Sleep scroll read after the prompt, the Goblin killed", dead and used, (dead, used))
    fl = [l.rstrip() for l in p.LOG[nf:]]
    awake = [l.rstrip() for l in p.LOG[run.wake_mark:]] if run.wake_mark is not None else fl
    check("C21", f"{tag}: the Sleep scroll read {'from the bag page (pick, READ)' if p.scroll_via == 'bag' else 'from the SCROLL icon'} "
          "-> L41 (the Goblin ASLEEP fired B13)", used and line("TL_L41", scheme) in fl, fl[-8:])
    check("C24", f"{tag}: no L75 nudge while the Goblin is awake (from its wake, B12, to its death)",
          run.wake_mark is not None and line("TL_L75", scheme) not in awake, (run.wake_mark, awake[:6]))
    left = after_fight_to_exit(p, run, heal=True)
    for _ in range(400):                                         # the reset's D1 start
        p.tick()
        if p.rb("GAME_STATE") == GS_PLAYING and w2(p, S["pl_et"] + 1) == S["end_turn"]:
            break
    p.tick(3)
    check("C3", f"{tag}: the grate step left D0 for D1 (hooks back: pl_et = end_turn, es_go = start_game)",
          left and w2(p, S["pl_et"] + 1) == S["end_turn"] and w2(p, S["es_go"] + 1) == S["start_game"], (left, st(p)))
    check("C3", f"{tag}: beats B0..B15 in order, none skipped", run.beats == list(range(16)), run.beats)
    miss, late = log_order(p, first_lines(hero), scheme)
    check("C3", f"{tag}: every beat's lines in the log, in beat order", not miss and not late, (miss, late))
    check("C10", f"{tag}: blob bytes == the image at {run.blob_n} checks (D0 start, 3 rooms, page, fight, grate)",
          not run.blob_bad and run.blob_n >= 6, (run.blob_bad, run.blob_n))
    check("C4", f"{tag}: the grate is shut while the Goblin lives and open (after the victory groups) before the step",
          set(run.grate) == {0} and run.grate_post and run.grate_post[-1] == S["LF_GRATE_OPEN"], (set(run.grate), run.grate_post[-3:]))
    lines = [l.rstrip() for l in p.LOG]
    mark = run.exit_mark
    pre = [l for l in lines[:mark]]
    k54, k55 = line("TL_L54", scheme), line("TL_L55", scheme)
    i54 = lines.index(k54) if k54 in lines else -1
    check("C15", f"{tag}: L54 / L55 (the Tome is the goal) in B1, right after L05 / L06 and before the pit beat (L08)",
          k54 in lines and k55 in lines and lines.index(line("TL_L05", scheme)) < i54 < lines.index(k55) < lines.index(line("TL_L08", scheme)),
          (i54,))
    check("C15", f"{tag}: after the kill L56 / L57 / L58 are logged before the hero steps into the grate (walking straight)",
          all(line("TL_" + k, scheme) in pre for k in ("L56", "L57", "L58")),
          [k for k in ("L56", "L57", "L58") if line("TL_" + k, scheme) not in pre])
    if final:
        d1, a1 = d1_after(p)
        bad = d1_equal(SHARED["plain"][0], d1, a1 | SHARED["plain"][1])
        check("C5", "the D1 after D0 == the D1 of a plain `2 START` (hero record, ENT_STAT, bag, counters, FOOD, ARANK, TURN_COUNTER, "
              "level state, map, screen; only PU_POS / PU_ARR and the decor / drip phase tolerated)", not bad, bad)
        e1 = p.ent(0)
        check("C5", "reset hero: FOOD 80, ARANK 0, TURN_COUNTER 0, KILLS 0, KEY 0, kit bag, full HP",
              (p.rb("FOOD"), p.rb("ARANK"), p.rw("TURN_COUNTER"), p.rb("ST1_KILLS")) == (S["FOOD_START"], 0, 0, 0)
              and e1["HP"] == e1["MAXHP"], (p.rb("FOOD"), p.rb("ARANK"), p.rw("TURN_COUNTER"), p.rb("ST1_KILLS")))
        check("C6", "after D1 entry: the offer is spent (es_go = start_game)", w2(p, S["es_go"] + 1) == S["start_game"])
        check("C27", "after D1 entry (the grate reset): pi_ic = intent_icon7, pl_et = end_turn", hooks_off(p), hex(w2(p, S["pi_ic"] + 1)))
        # C14: no mentor in D1 (map ids carrying his glyphs, screen cells carrying them)
        mg = SHARED["mentor_glyphs"]
        fr1 = p.frame()
        mp = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * G.PLAY_ROWS))
        ids_bad = [i for i, t in enumerate(mp) if t in MENTOR_IDS
                   and bytes(p.z.read_memory(S["TILE_GLYPHS"] + 8 * t, 8)) in mg]
        scr_bad = [(c, r) for r in range(G.PLAY_ROWS) for c in range(32) if G.cell_bytes(fr1, c, r) in mg]
        slots = [(s, e["KIND"]) for s in range(S["P_MAX_ENT"]) for e in (p.ent(s),) if e["FLAGS"] & G.EF_ACTIVE and e["KIND"] > 12]
        check("C14", "D1 after the reset: none of the mentor's 18 glyph cells in the map or on the screen, no extra body",
              not ids_bad and not scr_bad and not slots, (ids_bad[:3], scr_bad[:3], slots))
        # C6: a game over, then the menu's START goes straight to D1
        p.wb("GAME_STATE", GS_DEAD)
        p.tick(2)
        ok = p.end_to_menu()
        p.tick(3)
        p.hold("1")
        p.tick(3)
        shows_choice = p.rb("GAME_STATE") == GS_SELECT
        ok2 = p.wait_state(GS_PLAYING) if shows_choice else p.rb("GAME_STATE") == GS_PLAYING
        p.release()
        p.tick(3)
        check("C6", "completed D0 -> D1 -> game over -> menu START: straight to D1, the tutorial is not offered again",
              ok and ok2 and not shows_choice and w2(p, S["pl_et"] + 1) == S["end_turn"] and p.rb("LVL_DEPTH") == 1,
              (ok, ok2, shows_choice, hex(w2(p, S["pl_et"] + 1))))
    if scheme == "kemp":
        check("C11", f"{tag}: Kempston only (JOY_MODE 1, no key down at any time): bag READ, quick FOOD / SCROLL / POTION, the "
              "fight and the grate all completed; every hold dismissed by the stick's FIRE", p.rb("JOY_MODE") == 1 and p.dismissed >= 8
              and all(b == 0xFF for b in p.z.read_memory(S["KBD_MATRIX"], 8)) and ok and dead and used and left,
              (p.rb("JOY_MODE"), p.dismissed, ok, dead, used, left))
        check("C11", f"{tag}: the lines show the stick's words (L02 'DOWN CLIMBS DOWN THE LADDER', R2 L60 'DOWN+FIRE OPENS THE ICON BAR')",
              line("TL_L02", "kemp") in lines and line("TL_L60", "kemp") in lines,
              (line("TL_L02", "kemp"), line("TL_L60", "kemp"), [l for l in lines[:4]]))
        check("C20", f"{tag}: bag READ with the stick only (FIRE on BAG -> page, the book's slot from the bag, FIRE, FIRE READ): "
              "ARANK != 0 and B3's G1 (L13) logged", arank_mid != 0 and line("TL_L13", "kemp") in lines, arank_mid)
    print(f"[time] {name} run {time.monotonic() - t0:.0f}s, {len(p.LOG)} log lines, {p.dismissed} holds dismissed", flush=True)
    return p


def menu_kempston(p):
    """The menu's CONTROLS item (key 3) cycles KEYS -> KEMPSTON."""
    for _ in range(4):
        if p.rb("JOY_MODE") == 1:
            break
        p.tap("3")
        p.tick(2)


RAW["X"] = (0, 2)


def set_redef(keys):
    """The run's redefined set, keys = [UP, DOWN, LEFT, RIGHT, FIRE] physical names (a RAW key each)."""
    for tok, k in zip("QAOP", keys[:4]):
        REDEF[tok] = RAW[k]
    REDEF["FIRE"] = RAW[keys[4]]
    KN["redef"] = dict(U=keys[0], D=keys[1], L=keys[2], R=keys[3], F=keys[4])


def keytab_for(keys):
    """KEYTAB bytes for [U D L R F]: entry i = JOY bit i = R L D U F."""
    u, d, l, r, f = keys
    out = []
    for k in (r, l, d, u, f):
        row, bit = RAW[k]
        out += [S["KEYTAB_ROW"] + row, 1 << bit]
    return out


def menu_redefine(keys):
    """The menu's REDEFINE (key 4): five prompts UP DOWN LEFT RIGHT FIRE answered with `keys`."""
    def go(p):
        p.tap("4", n=3)
        p.tick(3)
        for k in keys:
            p.tick(3)
            p.hold("raw:" + k)
            p.tick(3)
            p.release()
            p.tick(3)
    return go


def menu_poke_keytab(keys):
    """W S K L M cannot be entered at the REDEFINE prompt (S is the reserved sound hotkey, menu1.asm key_reserved): the
    KEYTAB is written as a completed redefine leaves it."""
    def go(p):
        p.wmem("KEYTAB", keytab_for(keys))
    return go


def scen_skip(h):
    """C4 / C13: the shortest walk (no read / eat / drink): ladder variant, then the pit-fall variant."""
    for pit in (False, True):
        tag = "pit-fall route" if pit else "skip run"
        cid = "C13" if pit else "C4"
        p = start(h, 0)
        run = Run(p)
        ok = go_to_C(p, run, False, pit=pit)
        arank0, food_ok = p.rb("ARANK"), p.rb("FOOD") <= 40
        check(cid, f"{tag}: A -> B -> C by walk + climb" + (" (off the pit)" if pit else "") +
              ", the mentor's boxes (A1 / B1 / C1) never block a step", ok and not run.blocked, (st(p), run.blocked))
        if pit:
            ls = [l.rstrip() for l in p.LOG]
            i69 = ls.index(line("TL_L69")) if line("TL_L69") in ls else -1
            check("C22", "run A: walking into the pit (x 19) -> storey 1, L69 + L10 in one group (no hold), the beat stays B2 "
                  "until room B", i69 >= 0 and ls[i69 + 1:i69 + 2] == [line("TL_L10")] and not held(p, "TL_L10")
                  and 2 in run.beats and 3 not in run.beats, (i69, run.beats))
        if not pit:
            check("C4", "skip run: nothing read, eaten, drunk (ARANK 0, FOOD only fell), beats jumped ahead in order",
                  arank0 == 0 and food_ok and run.beats == sorted(run.beats) and run.beats[-1] >= 10, (arank0, p.rb("FOOD"), run.beats))
            g = goblin(p)
            pre = p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"]
            check("C4", "skip run: the Goblin is on the shut grate (asleep) and the grate is shut", g is not None and pre == 0, (g and g[1]["X"], pre))
        dead, used = fight(p, run, False, n=90)
        left = after_fight_to_exit(p, run)
        for _ in range(400):
            p.tick()
            if p.rb("GAME_STATE") == GS_PLAYING and w2(p, S["pl_et"] + 1) == S["end_turn"]:
                break
        p.tick(3)
        check(cid, f"{tag}: the Goblin killed, grate shut before / open after, the grate step -> D1",
              dead and left and set(run.grate) == {0} and run.grate_post and run.grate_post[-1] == S["LF_GRATE_OPEN"]
              and w2(p, S["pl_et"] + 1) == S["end_turn"], (dead, left, set(run.grate), run.grate_post[-2:]))
        check("C10", f"{tag}: blob bytes == the image at {run.blob_n} checks", not run.blob_bad, run.blob_bad)


def scen_hold_mercy(h):
    p = start(h, 0)
    run = Run(p)
    to_floor(p, 0)
    flags = [p.rb(S["tile_flags"] + i) for i in MENTOR_IDS]
    check("C13", f"the mentor's tile ids {MID0}.. are tile_flags 0 (not solid, no floor support): a ghost blocks nothing",
          flags == [0] * MN, flags)
    p.set_ent(0, HP=3)                                           # C8: mercy
    T(p, "WAIT")
    e = p.ent(0)
    check("C8", "HP poked to 3, one Wait -> HP = MAXHP, L50 + L51 in the log (first mercy)",
          e["HP"] == e["MAXHP"] and p.seen(line("TL_L50")) and p.seen(line("TL_L51")) and p.rb("GAME_STATE") == GS_PLAYING,
          (e["HP"], e["MAXHP"], p.LOG[-4:]))
    n50, n51 = sum(1 for l in p.LOG if l.rstrip() == line("TL_L50")), sum(1 for l in p.LOG if l.rstrip() == line("TL_L51"))
    p.set_ent(0, HP=1)
    T(p, "WAIT")
    e = p.ent(0)
    check("C8", "HP 1 -> mended again: L50 again, L51 only the first time",
          e["HP"] == e["MAXHP"] and sum(1 for l in p.LOG if l.rstrip() == line("TL_L50")) == n50 + 1
          and sum(1 for l in p.LOG if l.rstrip() == line("TL_L51")) == n51, (e["HP"], n50, n51))
    ok = go_to_C(p, run, False)                                  # C7: the hold
    g = goblin(p)
    x0 = g[1]["X"] if g else None
    st_ok, xs = True, []
    for _ in range(20):
        T(p, "WAIT")
        g = goblin(p)
        xs.append(g[1]["X"] if g else None)
        st_ok &= bool(g) and p.rb(S["ST_FLAGS"] + g[0]) & S["STS_HOLD"] == S["HOLD_ASLEEP"] and g[1]["HP"] == g[1]["MAXHP"]
    check("C7", "20 Waits at the door of C: the Goblin's x unchanged, ASLEEP, HP full", ok and st_ok and set(xs) == {x0}, (ok, xs[:5], st_ok))
    hit = False
    for _ in range(40):
        g = goblin(p)
        if g and g[1]["HP"] < g[1]["MAXHP"]:
            hit = True
            break
        T(p, "L")
    g = goblin(p)
    awake = bool(g) and p.rb(S["ST_FLAGS"] + g[0]) & S["STS_HOLD"] != S["HOLD_ASLEEP"]
    xh = g[1]["X"] if g else None
    for _ in range(4):
        T(p, "H")
    g2 = goblin(p)
    check("C7", "one hit wakes the Goblin (HP < max, no longer ASLEEP) and it chases the retreating hero",
          hit and awake and g2 is not None and g2[1]["X"] < xh and p.rb(S["ST_FLAGS"] + g2[0]) & S["STS_HOLD"] != S["HOLD_ASLEEP"],
          (hit, awake, xh, g2 and g2[1]["X"]))
    hp_min, gs_ok = 99, True                                     # C8: never dead in D0
    for _ in range(40):
        T(p, "WAIT")
        hp_min = min(hp_min, p.ent(0)["HP"])
        gs_ok &= p.rb("GAME_STATE") == GS_PLAYING
    mended = sum(1 for l in p.LOG if l.rstrip() == line("TL_L50"))
    check("C8", "a Wait-only hero beside the awake Goblin for 40 turns never dies (HP >= 1, playing) and is mended when low",
          hp_min >= 1 and gs_ok and mended >= 3, (hp_min, gs_ok, mended))
    check("C10", f"hold / mercy run: blob bytes == the image ({run.blob_n} checks)", not run.blob_bad, run.blob_bad)


def scen_death(h):
    """C9: a death (HP 0 + DYING: the normal flow, mercy does not touch it) -> end card -> menu -> `1` -> the choice again, D0 rebuilt."""
    p = start(h, 0)
    run = Run(p)
    p.tick(3)
    d0 = snapshot(p)
    SHARED["d0_tol"] = anim_cells(p)
    d0["TUT_RAM"] = bytes(p.z.read_memory(S["TUT_RAM"], S["TUT_RAM_END"] - S["TUT_RAM"]))
    to_floor(p, 0)
    leg(p, run, 16)
    for _ in range(12):                                          # HP 1 before every step: the pit's fall (1d4) kills (mercy only
        if p.rb("GAME_STATE") != GS_PLAYING:                     # mends a hero that is not dying at the end of a turn)
            break
        p.set_ent(0, HP=1)
        T(p, "L")
    ok = p.until(lambda: p.rb("GAME_STATE") == GS_DEAD, 60)
    check("C9", "a fatal fall (HP 1, pit) in D0 -> the normal death flow (GS_DEAD; mercy leaves a dying hero alone)", ok, p.rb("GAME_STATE"))
    ok = p.end_to_menu()
    p.tick(3)
    p.hold("1")
    p.tick(3)
    p.release()
    p.tick(3)
    check("C9", "end card -> menu -> `1`: the tutorial is offered again (choice screen, offer armed, D0 hook undone)",
          ok and p.rb("GAME_STATE") == GS_SELECT and w2(p, S["es_go"] + 1) == S["ts_choice"] and w2(p, S["pl_et"] + 1) == S["end_turn"],
          (ok, p.rb("GAME_STATE"), hex(w2(p, S["es_go"] + 1)), hex(w2(p, S["pl_et"] + 1))))
    check("C27", "after a D0 death -> menu -> `1`: pi_ic = intent_icon7, pl_et = end_turn", hooks_off(p), hex(w2(p, S["pi_ic"] + 1)))
    game.golden(h, "tut0_choice", p.frame())                     # the same choice screen as the first offer
    assert press_start(p, "1", "tut_d0")
    p.tick(3)
    d1 = snapshot(p)
    d1["TUT_RAM"] = bytes(p.z.read_memory(S["TUT_RAM"], S["TUT_RAM_END"] - S["TUT_RAM"]))
    tol = anim_cells(p)
    diff = d1_equal(d0, d1, tol | SHARED.get("d0_tol", set()))
    tv_diff = d0["TUT_RAM"] != d1["TUT_RAM"]
    check("C9", "D0 rebuilt identically (level state, map, hero, pool; PU_POS / PU_ARR + decor / drip phase tolerated), TV_* state fresh",
          not diff and not tv_diff, (diff, tv_diff))
    check("C9", "blob bytes unchanged (== the image) after the death and the rebuild", blob_bytes(p) == BLOB_IMAGE)
    check("C9", "second D0 is live: B0, hooks, FOOD 40", (tv(p, "TV_BEAT"), w2(p, S["pl_et"] + 1), p.rb("FOOD")) == (0, S["ts_turn"], 40))


def scen_garbage(h):
    """C10: junk in bank 4 BLOB_ORG..$FFFF before the boot code runs (the harness has no tape boot: the snapshot's boot runs the same
    instr_ovl unpack-in-place the tape's does)."""
    p = start(h, 0, boot_garbage=True)
    run = Run(p)
    check("C10", "junk poked into bank 4 BLOB_ORG..$FFFF before boot: the blob == the image at the D0 start",
          blob_bytes(p) == BLOB_IMAGE and p.rb("CUR_ROOM") == 1)
    to_floor(p, 0)
    leg(p, run, 16)
    T(p, "K", "L")
    T(p, "L")
    page_use(p, S["IT_BOOK"], "I")
    check("C10", "... and still == the image after the book page and the first beats (ARANK set)",
          blob_bytes(p) == BLOB_IMAGE and p.rb("ARANK") != 0 and not run.blob_bad, (run.blob_bad, p.rb("ARANK")))


def scen_redef(h, keys, via_menu, label):
    set_redef(keys)
    p = start(h, 0, scheme="redef", via_menu=via_menu)
    kt = list(p.z.read_memory(S["KEYTAB"], 10))
    run = Run(p)
    check("C12", f"{label}: KEYTAB = the redefined set {''.join(keys)} (R L D U F entries)", kt == keytab_for(keys), (kt, keytab_for(keys)))
    to_floor(p, 0)
    leg(p, run, 16)
    T(p, "K", "L")                                               # UP + RIGHT over the pit
    T(p, "L")
    ok = page_use(p, S["IT_BOOK"], "icon")                       # DOWN + FIRE, RIGHT to the BAG icon, FIRE
    lines = [l.rstrip() for l in p.LOG]
    l02, l60, l67 = line("TL_L02", "redef"), line("TL_L60", "redef"), line("TL_L67", "redef")
    check("C12", f"{label}: L02 reads '{l02}', R2 L60 '{l60}', L67 '{l67}' (the redefined keys)",
          l02.startswith(keys[1] + " CLIMBS DOWN") and l02 in lines and l60 == f"{keys[1]}+{keys[4]} OPENS THE ICON BAR"
          and l60 in lines and l67 == f"LEAPS GO LEFT TOO: {keys[0]}+{keys[2]}" and l67 in lines, lines[:16])
    check("C12", f"{label}: the whole route works on the redefined keys: walk, leap the pit, pick up the book, READ it from the page",
          ok and p.rb("ARANK") != 0 and not run.blocked, (ok, p.rb("ARANK"), run.blocked))


def mentor_box(p):
    """(col, row) of the stamped mentor box in ROOM_MAP (every cell = the right or the left table's id), or None."""
    mp = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * G.PLAY_ROWS))
    for tbl in (MENTOR_R, MENTOR_L):
        for i in range(len(mp) - 32 * 5 - 3):
            if i % 32 <= 29 and all(mp[i + 32 * (k // 3) + k % 3] == tbl[k] for k in range(18) if tbl[k]):
                return i % 32, i // 32
    return None


def scen_visual(h, hero):
    """V1: the mentor's 3x6 box on the DISPLAYED screen == the current pose's glyphs + attrs (never blank / partial), sampled every
    5 ticks for 100 ticks right after a turn beside him and again after ~3 s without input. V2: the animated-decor cells of
    room A never show a mentor glyph cell (no fragments in the torches)."""
    tag = CLS[hero] + " "
    p = start(h, hero)
    run = Run(p)
    to_floor(p, 0)
    leg(p, run, 8)                                               # beside A1 (box cols 9..11)
    T(p, "WAIT")
    seen = set(SHARED.get("mentor_glyphs", set()))
    bad1, bad2, n = [], [], 0

    def dump(label):
        nonlocal n
        n += 1
        fr = p.frame()
        box = mentor_box(p)
        if box is None:
            bad1.append((label, "box not stamped"))
            return
        c0, r0 = box
        ids = [p.rb(S["ROOM_MAP"] + 32 * (r0 + k // 3) + c0 + k % 3) for k in range(18)]
        gl = [bytes(p.z.read_memory(S["TILE_GLYPHS"] + 8 * i, 8)) for i in ids]
        ids_gl = [i for i in ids]
        seen.update(g for g in gl if any(g))
        want_nonblank = sum(1 for g in gl if any(g))
        got_nonblank = 0
        for k in range(18):
            c, r = c0 + k % 3, r0 + k // 3
            if ids[k] not in MENTOR_IDS:                         # the id-less cell (5, 2): background, not his
                continue
            b = G.cell_bytes(fr, c, r)
            got_nonblank += bool(any(b))
            if b != gl[k] or G.attr_at(fr, c, r) != p.rb(S["TILE_ATTRS"] + ids[k]):
                bad1.append((label, (c, r), b.hex(), gl[k].hex()))
                break
        if want_nonblank < 6 or got_nonblank != want_nonblank:
            bad1.append((label, "blank / partial", want_nonblank, got_nonblank))
        for (c, r) in anim_cells(p):
            if r < G.PLAY_ROWS and not (c0 <= c < c0 + 3 and r0 <= r < r0 + 6) and any(G.cell_bytes(fr, c, r)) \
                    and G.cell_bytes(fr, c, r) in seen:
                bad2.append((label, (c, r)))

    for phase, steps in (("after turn", 20), ("idle 3 s", 20)):
        if phase == "idle 3 s":
            p.tick(75)
        for i in range(steps):
            dump(f"{phase} +{5 * i}")
            p.tick(5)
    check("V1", f"{tag}mentor box == the current pose's glyphs + attrs, never blank / partial ({n} dumps over 200 ticks, near him and idle)",
          not bad1, bad1[:3])
    check("V2", f"{tag}animated decor cells of room A never equal a mentor glyph cell over {n} dumps", not bad2, bad2[:3])


# --- TUT0-R2 (tutorial_d0.md s13, s10 C16..C28) ---------------------------------------------------
def held(p, key, scheme="keys"):
    """True if the group whose last line is (or second-last line is) `key` was HELD (a hold dismissed right after it)."""
    want = line(key, scheme)
    lines = [l.rstrip() for l in p.LOG]
    return any(m >= 1 and want in lines[max(0, m - 2):m] for m in p.hold_marks)


def flash_cells(p, rows=range(18, 24), displayed=False):
    """(col, row) of the panel cells with FLASH set: bank 5 attrs, or the DISPLAYED frame."""
    if displayed:
        fr = p.frame()
        return [(c, r) for r in rows for c in range(32) if G.attr_at(fr, c, r) & 0x80]
    a = p.z.read_memory(0x5800, 768)
    return [(c, r) for r in rows for c in range(32) if a[32 * r + c] & 0x80]


def rect_flash_ok(p, rid):
    """Every non-blank cell of tut_rects[rid] has FLASH (bank 5) and at least one cell is non-blank."""
    r0, c0, w, hh = PTR_RECTS[rid]
    a = p.z.read_memory(0x5800, 768)
    cells = [(c, r) for r in range(r0, r0 + hh) for c in range(c0, c0 + w)]
    nb = [(c, r) for c, r in cells if any(bytes(p.z.read_memory(0x4000 + ((r & 24) << 8) + ((r & 7) << 5) + c + 256 * k, 1))[0]
                                          for k in range(8))]
    return bool(nb) and all(a[32 * r + c] & 0x80 for c, r in nb)


def rest(p, n=14):
    """The ICON MODE cursor rests n ticks (n > REST_T hook calls); returns the lines logged meanwhile."""
    n0 = len(p.LOG)
    p.tick(n)
    return [l.rstrip() for l in p.LOG[n0:]]


def blob_strings():
    """Every tutorial string decoded from the blob IMAGE (tut_tab), control bytes as {U}.."""
    base = S["BLOB_ORG"]
    out = {}
    for i in range(S["TUT_TEXT_COUNT"]):
        o = S["tut_tab"] - base + 2 * i
        a = BLOB_IMAGE[o] | BLOB_IMAGE[o + 1] << 8
        out[i] = dec(BLOB_IMAGE[a - base:a - base + 64])
    return out


def scen_static():
    """C16 (strings), C28 (budget, static: from the .sym)."""
    ss = blob_strings()
    l05 = ss[S["TL_L05"]]
    bad = [t for t in ss.values() if "ALDOUS" in t or "SEXTON" in t]
    check("C16", f"L05 decodes to '{l05}' from the blob image; no tutorial string names ALDOUS / SEXTON; the choice line is "
          f"'{ss[S['TS_CHOICE3']]}'", l05 == "I AM BROTHER MORROW, LONG DEAD" and not bad
          and ss[S["TS_CHOICE3"]] == "BROTHER MORROW WILL TEACH YOU", (l05, bad))
    free = S["BLOB_RES"] - S["BLOB_LEN"] - S["BLOB_DELTA"]
    check("C28", f"blob BLOB_LEN + BLOB_DELTA <= BLOB_RES with >= 600 B free ({free}); TUT_RAM_END ${S['TUT_RAM_END']:04X} <= PF_ROWF "
          f"${S['PF_ROWF']:04X}", free >= 600 and S["TUT_RAM_END"] <= S["PF_ROWF"], free)


def hooks_off(p):
    return w2(p, S["pi_ic"] + 1) == S["intent_icon7"] and w2(p, S["pl_et"] + 1) == S["end_turn"]


def scen_tour(h, hero, scheme="keys"):
    """C18 (+ C26 Kempston): the icon tour from the D0 start; C22 run B (the leap); C17 / C19 / C20 at B3; slot 2 after the
    read; C24 the nudge at B4; C19 FOOD target + C23 at B5."""
    tag = ("Kempston " if scheme == "kemp" else "") + ("Warrior" if hero == 0 else "Mage")
    p = start(h, hero, scheme=scheme, via_menu=menu_kempston if scheme == "kemp" else None)
    run = Run(p)
    p.tick(3)
    cw = CLS[hero]
    L = lambda k: line(k, scheme)                                 # noqa: E731
    # --- C18 / C26: the first ICON MODE entry holds I00a / I00b; the dismissing input is swallowed ---
    n0, t0, s0 = len(p.LOG), p.rw("TURN_COUNTER"), p.rb("SEL_SLOT")
    p.hold("J", "FIRE")
    p.tick(2)
    p.release()
    hold_up = p.until(lambda: tv(p, "TV_HOLD") == 1, 12)
    hq = tv(p, "TV_HQ")
    dismiss(p)
    p.tick(2)
    ent = [l.rstrip() for l in p.LOG[n0:]]
    check("C18", f"{tag}: the first ICON MODE entry -> I00a / I00b ('{L('TL_I00b')}') with a hold (TV_HQ 1)",
          hold_up and hq == 1 and L("TL_I00a") in ent and L("TL_I00b") in ent, (hold_up, hq, ent))
    check("C26" if scheme == "kemp" else "C18", f"{tag}: the hold's dismissing {'stick' if scheme == 'kemp' else 'key'} neither moves the cursor, "
          "leaves ICON MODE nor uses (no turn, INTENT 0)",
          (p.rb("ICON_MODE"), p.rb("SEL_SLOT"), p.rw("TURN_COUNTER"), p.rb("INTENT")) == (1, s0, t0, 0),
          (p.rb("ICON_MODE"), p.rb("SEL_SLOT"), p.rw("TURN_COUNTER"), p.rb("INTENT")))
    # RIGHT held through the slots (first repeat after 10 ticks, then every 4 < REST_T): no line; then UP leaves
    n1 = len(p.LOG)
    p.hold("L")
    p.tick(22)
    p.release()
    p.tap("K")
    p.tick(2)
    passed = [l.rstrip() for l in p.LOG[n1:]]
    check("C18", f"{tag}: RIGHT held through the slots (auto-repeat) adds no tour line; UP leaves ICON MODE",
          not passed and p.rb("ICON_MODE") == 0, (passed, p.rb("ICON_MODE")))
    # rest on every reachable slot
    icon_mode(p, True)
    no_second_hold = tv(p, "TV_HOLD") == 0 and not (L("TL_I00a") in [l.rstrip() for l in p.LOG[n1:]])
    cursor_to(p, 0)
    seen, order = {}, []
    for _ in range(12):
        s = p.rb("SEL_SLOT")
        if s in seen:
            break
        seen[s] = rest(p)
        order.append(s)
        hq_any = tv(p, "TV_HOLD")
        p.tap("L")
        p.tick(1)
    again = rest(p)                                               # a second rest on slot 1 (wrapped round)
    want = {0: "TL_I01" + cw, 6: "TL_I07", 7: "TL_I08", 8: "TL_I09", 9: "TL_I10"}
    if hero == 0:
        want.update({3: "TL_I04W", 4: "TL_I05W"})
    got = {s: ls for s, ls in seen.items()}
    ok = set(got) == set(want) and all(got[s] == [L(k)] for s, k in want.items())
    check("C18", f"{tag}: a rest of REST_T on each reachable slot before the book says its line once "
          f"(slots {sorted(s + 1 for s in want)}); stick words in the lines", ok and no_second_hold,
          ({s + 1: v for s, v in got.items()}, no_second_hold))
    check("C18", f"{tag}: a second rest on a said slot adds no line", again == [] and p.rb("SEL_SLOT") == 0, (again, p.rb("SEL_SLOT")))
    icon_mode(p, False)
    # --- C22 run B: B2 G0 L65 / L66 held, G2 L08 / L09 held, the leap -> G1 L67 / L68 scroll, B3 on the book ---
    to_floor(p, 0)
    leg(p, run, 16)
    T(p, "K", "L")
    land = (p.ent(0)["X"], storey(p))
    g1 = held(p, "TL_L66", scheme), held(p, "TL_L09", scheme), L("TL_L67") in [l.rstrip() for l in p.LOG], held(p, "TL_L68", scheme)
    check("C22", f"{tag}: B2 G0 L65 / L66 (held), then L08 / L09 (held); UP+RIGHT from x 16 lands x 22 storey 0; G1 L67 / L68 "
          "without a hold", g1 == (True, True, True, False) and land == (22, 0), (g1, land))
    # --- B3: the book; C17 pointer; C19 BAG target ---
    T(p, "L")
    b3 = tv(p, "TV_BEAT")
    ptr_on = tv(p, "TV_PTR") == 0 and rect_flash_ok(p, 0)
    p.hold("J", "FIRE")
    p.tick(2)
    p.release()
    p.tick(3)
    in_mode = p.rb("ICON_MODE") == 1
    f5, fd = flash_cells(p), flash_cells(p, displayed=True)
    cursor_to(p, 9)
    f5b = flash_cells(p) + flash_cells(p, displayed=True)
    n2 = len(p.LOG)
    p.tick(14)
    t_hold = tv(p, "TV_HOLD") == 1
    dismiss(p)
    tgt1 = [l.rstrip() for l in p.LOG[n2:]]
    p.tap("K")
    p.tick(3)
    f_after = flash_cells(p) + flash_cells(p, displayed=True)
    check("C17", f"{tag}: B3 G0 -> the BAG rect FLASHes; in ICON MODE no FLASH in rows 18-23 (bank 5 + shown screen), after "
          "UP still none (retired)", b3 == 3 and ptr_on and in_mode and not f5 and not fd and not f5b and not f_after and tv(p, "TV_PTR") == 0xFF,
          (b3, ptr_on, in_mode, f5[:3], fd[:3], f5b[:3], f_after[:3], tv(p, "TV_PTR")))
    icon_mode(p, True)
    n3 = len(p.LOG)
    p.tick(14)
    t2_hold = tv(p, "TV_HOLD")
    tgt2 = [l.rstrip() for l in p.LOG[n3:]]
    icon_mode(p, False)
    pair = [L("TL_L12"), L("TL_L61")]
    check("C19", f"{tag}: B3 rest on BAG -> '{pair[0]}' / '{pair[1]}' held the first time; a 2nd session's rest says it again, no hold",
          t_hold and tgt1 == pair and tgt2 == pair and not t2_hold, (t_hold, tgt1, tgt2, t2_hold))
    # C17: the nudge re-show re-arms the BAG pointer (13 off-task moves, away from Morrow's repeat range not needed: moves)
    n4 = len(p.LOG)
    for i in range(13):
        T(p, "H" if i % 2 == 0 else "L")
    nud = [l.rstrip() for l in p.LOG[n4:]]
    check("C17", f"{tag}: B3 nudge (12 off-task turns: L75, then the G0 re-show) -> the BAG FLASH is back",
          nud[:3] == [L("TL_L75"), L("TL_L11"), L("TL_L60")] and tv(p, "TV_PTR") == 0 and rect_flash_ok(p, 0), (nud, tv(p, "TV_PTR")))
    # --- the read (bag page); B3 G1 + the tail L63 / L64 (no hold); slot 2 -> I02 ---
    page_use(p, S["IT_BOOK"], "icon")
    T(p, "WAIT")
    T(p, "WAIT")                                                  # the tail ends: B4's G0 (L16) this turn
    g0_b4 = p.LOG[-1].rstrip() == L("TL_L16")
    tc_g0 = p.rw("TURN_COUNTER")
    tail = L("TL_L63") in [l.rstrip() for l in p.LOG] and not held(p, "TL_L64", scheme)
    icon_mode(p, True)
    cursor_to(p, 1)
    i02 = rest(p)
    icon_mode(p, False)
    check("C18", f"{tag}: after the read: B3 tail L63 / L64 (no hold); slot 2 -> '{L('TL_I02' + cw)}'",
          tail and i02 == [L("TL_I02" + cw)], (tail, i02))
    # --- C24 the nudge at B4: Waits > 4 cols from Morrow (A3, col 19) ---
    leg(p, run, 27)
    beat4 = tv(p, "TV_BEAT")
    k = p.rw("TURN_COUNTER") - tc_g0                              # off-task turns already spent walking (since B4's G0)
    marks = []
    for i in range(100):
        T(p, "WAIT")
        marks.append(len(p.LOG))
    tut = {line(k, scheme) for k in SRC if k.startswith("TL_")}       # (engine lines, e.g. the hunger word's, ignored)
    lines = [l.rstrip() for l in p.LOG]
    due = [t - k for t in (12, 13, 36, 37)]                       # Wait numbers of off-task turns 12, 13, 36, 37
    w = [[l for l in lines[marks[t - 2]:marks[t - 1]] if l in tut] for t in due]
    rest_lines = [l for t in range(2, 101) if t not in due for l in lines[marks[t - 2]:marks[t - 1]] if l in tut]
    check("C24", f"{tag}: B4 (G0 L16), {k} walking turns + 100 Waits at x 27 (> 4 cols from Morrow): L75 on off-task turn 12, "
          "L16 on 13; again on 36 / 37; nothing else up to 100",
          g0_b4 and beat4 == 4 and k < 10 and w == [[L("TL_L75")], [L("TL_L16")], [L("TL_L75")], [L("TL_L16")]]
          and not rest_lines, (g0_b4, beat4, k, w, rest_lines[:4]))
    # --- B5: G0 / G2, the FOOD target (no hold), the eat, the WEAK tail L70 / L71 (no hold) ---
    to_floor(p, 1)
    T(p, "WAIT")
    leg(p, run, 17)
    icon_mode(p, True)
    cursor_to(p, 6)
    food = rest(p)
    fh = tv(p, "TV_HOLD")
    fire_turn(p)
    icon_mode(p, False)
    T(p, "WAIT")
    T(p, "WAIT")
    lines = [l.rstrip() for l in p.LOG]
    check("C19", f"{tag}: B5 rest on FOOD -> L73 '{L('TL_L73')}' (no hold)", food == [L("TL_L73")] and not fh, (food, fh))
    check("C23", f"{tag}: after the eat (L21 / L22) the B5 tail L70 / L71 shows, without a hold",
          L("TL_L21") in lines and L("TL_L70") in lines and lines.index(L("TL_L70")) > lines.index(L("TL_L21"))
          and not held(p, "TL_L71", scheme), lines[-6:])
    # --- C23 rule check (the line must be true): WEAK refuses the leap silently, HUNGRY does not ---
    if hero == 0 and scheme == "keys":
        p.wb("FOOD", 5)
        T(p, "WAIT")
        x0, t0, n5 = p.ent(0)["X"], p.rw("TURN_COUNTER"), len(p.LOG)
        T(p, "K", "L")
        weak = (p.ent(0)["X"], p.rw("TURN_COUNTER"), [l.rstrip() for l in p.LOG[n5:]])
        p.wb("FOOD", 15)
        T(p, "WAIT")
        x1 = p.ent(0)["X"]
        T(p, "K", "L")
        x2 = p.ent(0)["X"]
        check("C23", "rule: FOOD 5 (WEAK) -> UP+RIGHT on the floor: x, TURN_COUNTER unchanged, no log line; FOOD 15 (HUNGRY) -> the "
              "same leap moves 6 cols", weak == (x0, t0, []) and x2 - x1 == 6, (x0, t0, weak, x1, x2))
    check("C10", f"{tag} tour run: blob bytes == the image ({run.blob_n} checks)", not run.blob_bad, run.blob_bad)
    return p


def scen_left(h):
    """C25: skip the book and the pear, take the shaft -> L76 once in B, before L24; up to A and down again: no second L76.
    C22 run A is the pit-fall route (scen_skip). C27 after Quit."""
    p = start(h, 0)
    run = Run(p)
    to_floor(p, 0)
    leg(p, run, 12)
    to_floor(p, 1)
    leg(p, run, 5)
    to_floor(p, 1, room=4)
    for _ in range(3):
        T(p, "WAIT")
    in_b = p.rb("CUR_ROOM") == 4
    for _ in range(14):                                           # back up the shaft to A
        if p.rb("CUR_ROOM") == 1:
            break
        T(p, "K")
    up = p.rb("CUR_ROOM") == 1
    to_floor(p, 1, room=4)
    for _ in range(2):
        T(p, "WAIT")
    lines = [l.rstrip() for l in p.LOG]
    n76 = lines.count(line("TL_L76"))
    check("C25", "book + pear skipped, the shaft -> L76 once in B, before L24; up to A and down again: no second L76",
          in_b and up and p.rb("CUR_ROOM") == 4 and n76 == 1 and line("TL_L24") in lines
          and lines.index(line("TL_L76")) < lines.index(line("TL_L24")), (in_b, up, p.rb("CUR_ROOM"), n76, lines[-8:]))
    # C27: Quit from the pause (FIRE + UP -> QUIT) -> menu -> 1 START: the choice; both D0 operands back
    p.hold("FIRE", "K")
    p.tick(3)
    p.release()
    p.tick(3)
    paused = p.rb("PAUSE_REQ")
    for key in ("H", "FIRE", "FIRE"):                             # RESUME -> (wrap) QUIT, FIRE, QUIT? FIRE = yes
        p.tap(key, n=2)
        p.tick(4)
    p.until(lambda: p.rb("GAME_STATE") == GS_SELECT, 60)
    at_menu = p.rb("GAME_STATE") == GS_SELECT
    p.tick(3)
    p.hold("1")
    p.tick(3)
    p.release()
    p.tick(3)
    check("C27", "after Quit (pause) -> menu -> `1`: the choice screen; pi_ic = intent_icon7 and pl_et = end_turn",
          at_menu and w2(p, S["es_go"] + 1) == S["ts_choice"] and hooks_off(p), (paused, at_menu, hex(w2(p, S["pi_ic"] + 1))))


def main():
    t0 = time.monotonic()
    with Harness() as h:
        h.launch(EMU_ARGS)
        scen_static()
        scen_plain(h)
        scen_full(h, 0, "icon", "Warrior", True)
        scen_full(h, 1, "I", "Mage", False)
        scen_skip(h)
        scen_hold_mercy(h)
        scen_death(h)
        scen_garbage(h)
        scen_full(h, 0, "icon", "Kempston Warrior", False, scheme="kemp", via_menu=menu_kempston)
        scen_redef(h, ["W", "X", "K", "L", "M"], menu_redefine(["W", "X", "K", "L", "M"]), "REDEFINE menu W X K L M")
        scen_redef(h, ["W", "S", "K", "L", "M"], menu_poke_keytab(["W", "S", "K", "L", "M"]), "KEYTAB W S K L M")
        scen_visual(h, 0)
        scen_visual(h, 1)
        scen_tour(h, 0)
        scen_tour(h, 1)
        scen_tour(h, 0, scheme="kemp")
        scen_left(h)
    fails = sorted({c for c, ok, _ in CHECKS if not ok})
    nbad = sum(1 for c in CHECKS if not c[1])
    print(f"tut0: {nbad} failed of {len(CHECKS)}" + (f": {fails}" if fails else "") + f"  ({time.monotonic() - t0:.0f}s)", flush=True)
    return 1 if nbad or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
