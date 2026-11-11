#!/usr/bin/env python3
"""TUT0-T9c: the D0 tutorial against NON-STANDARD player behaviour (docs/design/tutorial_d0.md s3 / s13;
memory-map "TUT0-T7" / "TUT0-F2" / "TUT0-R2"; extends tests/tut0.py C1-C28 + V1-V3, whose helpers it imports).

  A. scripted misbehaviour scenarios (A1..): each runs with the invariants below armed on every 25th tick, and ends by
     COMPLETING the tutorial (a generic finisher walks / kills / steps into the grate from wherever the hero is) and
     checking the three SMC operands are back to the D1 set.
  B. random-input soak: seeds x classes x N random inputs from the full input set, holds dismissed periodically.

Invariants (checked every 25 ticks, in every scenario and the soak; "heavy" ones every 100):
  I1 no run anomaly / no exception (hang, crash) in the driver;   I2 GAME_STATE in {PLAYING, TRANSITION, SELECT, LEVEL,
  (DEAD only outside D0)};   I3 (es_go, pl_et, pi_ic) is one of the three legal sets: D0 (ts_choice, ts_turn, ts_icon),
  D1 / offer spent (start_game, end_turn, intent_icon7), menu with the offer armed (ts_choice, end_turn, intent_icon7);
  PLAYING never with the menu set (SELECT with the stale D0 set after a pause-QUIT is legal, in_tut undoes it at START);   I4 bank 4 BLOB_ORG.. == build/ovl/blob.bin while the
  offer is unspent (es_go = ts_choice);   I5 (heavy) mentor box == the current pose (V1) when stamped and in view, no
  mentor glyph outside it (V2);   I6 no FLASH on blank pointer cells (V3, tut0.Run.ptr_check, every turn);   I7 the hero
  never dies in D0 (mercy), HP >= 1;   I8 TUT_RAM in range (TV_BEAT 0..15, TV_SPOT 0..7, TV_STAGE 0..5, TV_HOLD 0/1,
  TV_PTR $FF or a rect id);   I10 / I11 (TUT0-F4, tut0.Run.goal_check at every turn) the goal line == its model
  (row 20 cols 0-23: text, attrs, visibility), no FLASH in cols 24-31 during a hold;   I9 OVERRUN_COUNT (ticks > 2 frames) reported, not gated (room builds / holds count).

Usage: ZRCP_PORT=10801 python3 tests/tut0_adv.py [--only A3,A5] [--no-scen] [--no-soak] [--seeds N] [--inputs N]
       [--hero 0|1] [--seed0 K]
Output: one line per scenario / seed; violations with a repro; `tut0_adv: ...` summary.
"""
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tut0 as U                                         # noqa: E402  (imports game_lib, sets the tutorial path live)
import game_lib as G                                     # noqa: E402
from game_lib import Harness, S, EMU_ARGS, GS_PLAYING, GS_SELECT, GS_DEAD, GS_TRANSITION   # noqa: E402

ARGV = U._ARGV


def opt(name, default, cast=int):
    return cast(ARGV[ARGV.index(name) + 1]) if name in ARGV else default


ONLY = set(ARGV[ARGV.index("--only") + 1].split(",")) if "--only" in ARGV else None
GS_LEVEL = 7
PAUSED = S["PAUSED"]
D0H = (S["ts_choice"], S["ts_turn"], S["ts_icon"])
D1H = (S["start_game"], S["end_turn"], S["intent_icon7"])
MENUH = (S["ts_choice"], S["end_turn"], S["intent_icon7"])
HOOK_NAMES = {D0H: "D0", D1H: "D1", MENUH: "MENU"}
OVR = S["OVERRUN_COUNT"]
BREAK_KEYS = ("CAPS", "SPACE")

VIOL = {}                                                # (scenario, kind) -> [count, first detail]
STATS = dict(ticks=0, inputs=0, d0_ticks=0, overruns=0, heavy=0, i5_unsettled=0)


def viol(ctx, kind, detail="", counts=True):
    k = (ctx.name, kind)
    if k not in VIOL:
        VIOL[k] = [0, f"tick {ctx.nt} step '{ctx.step}': {detail}"]
        print(f"  [VIOLATION] {ctx.name} {kind}: {VIOL[k][1]}", flush=True)
    VIOL[k][0] += 1
    if counts:
        ctx.nviol += 1


class Ctx:
    """One scenario / soak run: the driver, the run tracer, the tick counter and the invariant state."""
    def __init__(self, name):
        self.name, self.p, self.run, self.nt, self.step, self.nviol = name, None, None, 0, "start", 0
        self.fails, self.in_hook, self.expect_death, self.ovr0, self.sample = [], False, False, 0, 0
        self.mglyphs, self.last_hooks = set(), None
        self.max_ovr = 0

    def fail(self, msg):
        self.fails.append(msg)
        print(f"  [FAIL] {self.name}: {msg}", flush=True)


# --- the tick hook: invariants every 25th tick ----------------------------------------------------------------
def _orig_tick(self, n=1):
    """tut0.TP.tick with a diagnosable failure (the register read of the log_push probe)."""
    for _ in range(n):
        while True:
            G.Proto.tick(self, 1)
            if self.LOG is not None and self.pc() == S["log_push"]:
                r = self.z.cmd("get-registers")
                m = re.search(r"HL=([0-9a-fA-F]{4})", r)
                if not m:
                    raise RuntimeError(f"get-registers at log_push had no HL: {r[:160]!r}")
                self.LOG.append(U.dec(self.z.read_memory(int(m.group(1), 16), 40)))
                continue
            break


def _tick(self, n=1):
    for _ in range(n):
        _orig_tick(self, 1)
        c = getattr(self, "ctx", None)
        if c is None:
            continue
        c.nt += 1
        STATS["ticks"] += 1
        if c.nt % 25 == 0 and not c.in_hook:
            c.in_hook = True
            try:
                invariants(c, heavy=(c.nt % 100 == 0))
            except Exception as e:                       # a broken read is a driver problem, not a game verdict
                print(f"  [warn] invariant read failed at tick {c.nt}: {e!r}", flush=True)
            finally:
                c.in_hook = False


U.TP.tick = _tick


def hooks(p):
    return (U.w2(p, S["es_go"] + 1), U.w2(p, S["pl_et"] + 1), U.w2(p, S["pi_ic"] + 1))


def invariants(c, heavy=False):
    p = c.p
    gs = p.rb("GAME_STATE")
    hk = hooks(p)
    d0 = hk == D0H
    if d0:
        STATS["d0_ticks"] += 25
    # I2
    if gs not in (GS_PLAYING, GS_TRANSITION, GS_SELECT, GS_LEVEL, GS_DEAD):
        viol(c, "I2 game state", f"GAME_STATE {gs}")
    # I7 (the hero never dies in D0)
    if gs == GS_PLAYING or d0:
        e = p.ent(0)
        if d0 and (gs == GS_DEAD or (gs == GS_PLAYING and e["HP"] < 1 and e["FLAGS"] & G.EF_ACTIVE)) and not c.expect_death:
            viol(c, "I7 hero died in D0", f"gs {gs} HP {e['HP']}/{e['MAXHP']} {U.st(p)}")
    # I3 hook triple
    if hk not in HOOK_NAMES:
        if gs in (GS_PLAYING, GS_SELECT):
            viol(c, "I3 SMC mixed", f"es_go/pl_et/pi_ic = {tuple(hex(x) for x in hk)} gs {gs}")
    elif gs == GS_PLAYING and hk == MENUH:
        viol(c, "I3 playing with menu hooks", U.st(p))
    # (SELECT with the D0 operands is legal: a pause-QUIT / death leaves them until the menu's START runs in_tut)
    # I8 TUT_RAM
    if d0 and gs == GS_PLAYING:
        beat, spot, stg, hold, ptr = (U.tv(p, n) for n in ("TV_BEAT", "TV_SPOT", "TV_STAGE", "TV_HOLD", "TV_PTR"))
        if beat > 15 or spot > 7 or stg > 5 or hold > 1 or not (ptr == 0xFF or ptr < len(U.PTR_RECTS)):
            viol(c, "I8 TUT_RAM out of range", f"beat {beat} spot {spot} stage {stg} hold {hold} ptr {ptr:#x}")
    # I9
    ov = p.rw("OVERRUN_COUNT")
    if ov != c.ovr0:
        d = (ov - c.ovr0) & 0xFFFF
        STATS["overruns"] += d
        c.max_ovr += d
        c.ovr0 = ov
    # I4 blob (while the offer is unspent the blob is resident; D1's pool overwrites it afterwards)
    if heavy and hk[0] == S["ts_choice"]:
        STATS["heavy"] += 1
        if U.blob_bytes(p) != U.BLOB_IMAGE:
            viol(c, "I4 blob != blob.bin", U.st(p))
    # I5 mentor (heavy; D0 playing, idle, box stamped, nothing overlaying the play area)
    if heavy and d0 and gs == GS_PLAYING and i5_gate(p, True):
        mentor_check(c)


def i5_gate(p, idle):
    """I5 applies: D0 playing, box stamped, no pause / page over the play area (and, at the first look, no turn running)."""
    return hooks(p) == D0H and p.rb("GAME_STATE") == GS_PLAYING and U.tv(p, "TV_STAMP") == 1 and p.rb(PAUSED) == 0 \
        and p.rb("PAGE_OPEN") == 0 and (not idle or p.rb("TURN_PHASE") == 0)


# TUT0-F3 (P2 root cause = this sampler): a pose / spot change made by end_turn (tt_mentor: glyphs + a queued
# restore) is rendered in the next tick and presented in the tick after (A7 double buffer, RENDER_FIRST), so the
# DISPLAYED box shows the previous pose for up to 2 probes. A held key can end a turn every tick (Wait '.', a
# turn-around, a diagonal pair), and every turn toggles IDLE1 / IDLE2, so the old fixed 3-tick retry re-sampled
# fresh latency (V1 in BW1 BW9 BW16 BM2 BM5): the recheck now waits until the pose has been unchanged for
# POSE_LAT probes; never settling in POSE_WAIT ticks is inconclusive (counted, not a violation). BW15's V2 was a
# flying damage number's line over the hero's head (== a mentor glyph): live number cells are excluded.
POSE_LAT = 3
POSE_WAIT = 24


def pose_key(p):
    return tuple(U.tv(p, n) for n in ("TV_IMG", "TV_SPOT", "TV_STAMP")) + (p.rb("CUR_ROOM"),)


def pose_settle(p):
    k0, stable = pose_key(p), 0
    for _ in range(POSE_WAIT):
        p.tick(1)
        k = pose_key(p)
        stable = stable + 1 if k == k0 else 0
        k0 = k
        if stable >= POSE_LAT:
            return True
    return False


def mentor_check(c, again=True):
    p = c.p
    if not again and not i5_gate(p, False):
        return
    fr = p.frame()
    box = U.mentor_box(p)
    if box is None:
        viol(c, "I5 mentor box not stamped", U.st(p))
        return
    c0, r0 = box
    hx = p.ent(0)["X"]
    ids = [p.rb(S["ROOM_MAP"] + 32 * (r0 + k // 3) + c0 + k % 3) for k in range(18)]
    gl = [bytes(p.z.read_memory(S["TILE_GLYPHS"] + 8 * i, 8)) for i in ids]
    c.mglyphs.update(g for g, i in zip(gl, ids) if i in U.MENTOR_IDS and any(g))
    dn = p.dn_cells()                                    # a live flying number is OR'd on the displayed screen only (BW15:
    bad = []                                             # its top line f0.. == a mentor glyph at (20, 11), the hero's head)
    for k in range(18):
        col, row = c0 + k % 3, r0 + k // 3
        if ids[k] not in U.MENTOR_IDS or hx - 2 <= col <= hx + 5 or (col, row) in dn:   # the id-less cell / under the hero
            continue
        if G.cell_bytes(fr, col, row) != gl[k] or G.attr_at(fr, col, row) != p.rb(S["TILE_ATTRS"] + ids[k]):
            bad.append((col, row))
    if bad:
        if again:                                        # a persistent mismatch only (see POSE_LAT)
            if pose_settle(p):
                return mentor_check(c, False)
            STATS["i5_unsettled"] += 1
            return
        viol(c, "I5 mentor box != pose (V1)", f"cells {bad[:3]} (in ANIM_LIST/drip cells: {[b for b in bad if b in U.anim_cells(p)]}) box {box} {U.st(p)}")
    # V2: a mentor-only glyph anywhere outside the box (glyphs also used by ordinary tiles excluded)
    tiles = bytes(p.z.read_memory(S["TILE_GLYPHS"], 0x340))
    plain = {tiles[8 * t:8 * t + 8] for t in range(len(tiles) // 8) if t not in U.MENTOR_IDS}
    only = c.mglyphs - plain
    if only:
        stray = [(col, row) for row in range(G.PLAY_ROWS) for col in range(32)
                 if not (c0 <= col < c0 + 3 and r0 <= row < r0 + 6) and (col, row) not in dn
                 and G.cell_bytes(fr, col, row) in only]
        if stray and again:                              # the old box's cells after a spot change: the same latency
            if pose_settle(p):
                return mentor_check(c, False)
            STATS["i5_unsettled"] += 1
        elif stray:
            viol(c, "I5 mentor glyph outside the box (V2)", f"cells {stray[:3]} {U.st(p)}")


# --- scenario plumbing ------------------------------------------------------------------------------------------
def begin(h, name, hero=0, seed=1, scheme="keys"):
    c = Ctx(name)
    p = U.start(h, hero, seed=seed, scheme=scheme)
    p.ctx = c
    c.p = p
    c.ovr0 = p.rw("OVERRUN_COUNT")
    c.run = U.Run(p)
    return c


def finish_checks(c):
    """The Run tracer's own findings (V3 / blob at room changes) become violations."""
    r = c.run
    if r.ptr_bad:
        viol(c, "I6 FLASH on blank pointer cell (V3)", str(r.ptr_bad[0]) + f" ({len(r.ptr_bad)} samples)")   # TUT0-F3: failing (ROW20 = cols 0-25, the prompt owns 26-31)
    if r.blob_bad:
        viol(c, "I4 blob != blob.bin (room change)", str(r.blob_bad[:3]))
    if r.goal_bad:                                                   # TUT0-F4 K3: the goal line (row 20 cols 0-23 only)
        viol(c, "I10 goal line != its model (row 20 text / attrs / visibility)", str(r.goal_bad[0]) + f" ({len(r.goal_bad)} samples)")
    if r.k5_bad:
        viol(c, "I11 FLASH in row 20 cols 24-31 during a hold (K5)", str(r.k5_bad[0]))
    c.step = "end"
    invariants(c, heavy=hooks(c.p)[0] == S["ts_choice"])


def ensure_play(p):
    """Back to plain play: resume the pause, close the page, leave ICON MODE, dismiss holds."""
    for _ in range(8):
        did = False
        if p.rb(PAUSED):
            p.hold(*BREAK_KEYS)
            p.tick(2)
            p.release()
            p.tick(3)
            did = True
        elif p.rb("PAGE_OPEN"):
            p.tap("I")
            p.tick(2)
            did = True
        elif p.rb("ICON_MODE"):
            p.tap("K")
            p.tick(2)
            did = True
        elif U.tv(p, "TV_HOLD"):
            U.dismiss(p)
            did = True
        if not did:
            break
    if p.run is not None:
        p.run.note()


def T(c, *keys):
    c.step = "T" + "+".join(keys)
    ok = U.T(c.p, *keys)
    return ok


def kill_goblin(c, n=90):
    p = c.p
    for _ in range(n):
        if p.rb("ST1_KILLS"):
            return True
        if p.rb("GAME_STATE") != GS_PLAYING:
            return False
        g = U.goblin(p)
        if not g:
            return False
        e = p.ent(0)
        gs_ = 0 if g[1]["Y"] <= U.STAND_Y[0] + 2 else 1          # the Goblin's storey (its stand Y is 2 below the hero's)
        if e["Y"] not in U.STAND_Y:                              # mid-ladder: finish the climb first
            T(c, "J" if e["Y"] < U.STAND_Y[0] or gs_ == 1 else "K")
        elif U.storey(p) != gs_:                                 # other storey: walk to the room's ladder and change
            lad = 24 if p.rb("CUR_ROOM") == 4 else 12
            if e["X"] != lad:
                T(c, "L" if e["X"] < lad else "H")
            else:
                T(c, "J" if gs_ == 1 else "K")
        else:
            T(c, "L" if e["X"] < g[1]["X"] else "H")
    return bool(p.rb("ST1_KILLS"))


def wait_d1(p, n=400):
    for _ in range(n):
        p.tick()
        if p.rb("GAME_STATE") == GS_PLAYING and hooks(p) == D1H:
            break
    p.tick(3)
    return hooks(p) == D1H


def complete(c, rounds=10):
    """The generic finisher: from wherever the hero is (A / B / C) reach the grate and step in. True once the D1 start is up."""
    p = c.p
    for _ in range(rounds):
        ensure_play(p)
        if p.rb("GAME_STATE") != GS_PLAYING or hooks(p) == D1H:
            break
        c.step = "complete"
        room = p.rb("CUR_ROOM")
        if p.rb("ST1_KILLS") == 0 and U.goblin(p) and room != 5:
            kill_goblin(c)
            continue
        if room == 1:
            if U.storey(p) == 0:
                U.walk_to(p, 12)
                U.to_floor(p, 1)
            U.walk_to(p, 5)
            U.to_floor(p, 1, room=4)
        elif room == 4:
            if U.storey(p) == 0:
                U.walk_to(p, 24)
                U.to_floor(p, 1)
            for _ in range(30):
                if p.rb("CUR_ROOM") != 4:
                    break
                T(c, "L")
        elif room == 5:
            if not p.rb("ST1_KILLS"):
                kill_goblin(c)
            if p.rb("ST1_KILLS"):
                U.after_fight_to_exit(p, c.run)
                wait_d1(p)
    ok = hooks(p) == D1H
    if ok:
        p.tick(3)
    return ok


MASH = []
UX = {}                                                  # scenario -> evidence for the designer


def ux_collect(c, tag="pre"):
    """UX evidence: which TL ids were shown, which beats' first lines never, nudges, holds, turns (before the finisher)."""
    p = c.p
    lines = [l.rstrip() for l in p.LOG]
    inv = {}
    for k, v in U.SRC.items():
        inv.setdefault(U.line(k, "keys"), k)
    ids = [inv.get(l) for l in lines]
    firsts = ["TL_" + k for k in U.first_lines(c.hero)]
    missing = [k[3:] for k in firsts if k not in ids]
    UX[c.name] = dict(turns=p.rw("TURN_COUNTER"), beats=list(c.run.beats) if c.run else [], missing=missing,
                      l75=ids.count("TL_L75"), l76=ids.count("TL_L76"), holds=p.dismissed, lines=len(lines),
                      food=p.rb("FOOD"), hp=p.ent(0)["HP"])


def done(c, extra_ok=True):
    ux_collect(c)
    ok = complete(c)
    if not ok:
        g = [(sl, e["ROOM"], e["X"], e["Y"], e["HP"], hex(e["FLAGS"])) for sl in range(1, 9) for e in (c.p.ent(sl),)
             if e["FLAGS"] & G.EF_ACTIVE]
        c.fail(f"tutorial could not be completed afterwards: {U.st(c.p)} hooks {HOOK_NAMES.get(hooks(c.p))} "
               f"kills {c.p.rb('ST1_KILLS')} ents(slot,room,x,y,hp,flags) {g}")
    finish_checks(c)
    return ok and extra_ok and not c.fails and c.nviol == 0


def to_B(c, full=False):
    """A start -> room B (the shortest walk), at the shaft landing."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 12)
    U.to_floor(p, 1)
    U.walk_to(p, 5)
    U.to_floor(p, 1, room=4)
    U.to_floor(p, 0)


def to_C(c):
    p = c.p
    U.go_to_C(p, c.run, False)
    return p.rb("CUR_ROOM") == 5


def bag_types(p):
    b = p.z.read_memory(S["BAG"], 3 * S["BAG_SLOTS"])
    return [b[3 * i] for i in range(S["BAG_SLOTS"])]


FOOD_TYPES = set(range(S["IT_FOOD_LO"], S["IT_FOOD_HI"] + 1)) | {S["IT_F_PEAR"]}


def page_discard(p, typ_set, via="icon"):
    """Bag page -> the slot of a type in typ_set -> FIRE (verb strip, USE first) -> RIGHT (next enabled verb = DISCARD for a
    consumable) -> FIRE. True if a slot was emptied."""
    for s, t in enumerate(bag_types(p)):
        if t in typ_set and t != 0xFF and t != 0:
            break
    else:
        return False
    n0 = sum(1 for t in bag_types(p) if t in typ_set)
    if not U.open_page(p, via) or not U.page_nav(p, s):
        U.ensure = None
        ensure_play(p)
        return False
    p.tap("FIRE")
    p.tap("L")
    p.tap("FIRE")
    p.until(lambda: p.rb("PAGE_OPEN") == 0, 12)
    p.tick(2)
    ensure_play(p)
    return sum(1 for t in bag_types(p) if t in typ_set) < n0


def beats_str(c):
    return ",".join(map(str, c.run.beats))


# =============================== A. scenarios ==================================================================
SCEN = []


def scen(sid, heroes=(0,)):
    def deco(fn):
        SCEN.append((sid, fn, heroes))
        return fn
    return deco


@scen("A1", (0, 1))
def a1_discard_book(c):
    """Pick the book up, DISCARD it from the bag page before reading; carry on (B3 is never satisfied by a read)."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 16)
    T(c, "K", "L")
    T(c, "L")
    gone = page_discard(p, {S["IT_BOOK"]}, "icon" if c.hero == 0 else "I")
    c.fail("book not discarded") if not gone else None
    for _ in range(4):
        T(c, "WAIT")
    if p.rb("ARANK") != 0:
        c.fail("ARANK != 0 without a read")
    return done(c)


@scen("A2", (0, 1))
def a2_discard_kit(c):
    """DISCARD the Sleep scroll, every food and the Heal potion at B0, before any lesson; finish by the plain skip route."""
    p = c.p
    types = bag_types(p)
    sc = page_discard(p, {S["IT_S_SLEEP"]}, "icon" if c.hero == 0 else "I")
    fd = page_discard(p, FOOD_TYPES, "icon" if c.hero == 0 else "I")
    hp = page_discard(p, {S["IT_P_HEAL"]}, "icon" if c.hero == 0 else "I")
    if not (sc or fd or hp):
        c.fail(f"nothing discarded (bag {types})")
    # quick slots now empty: use them anyway (a use with nothing must not crash / spend a turn)
    for ic in (U.QS_FOOD_ICON, U.QS_POTION_ICON, U.QS_SCROLL_ICON):
        U.quick(p, ic)
    for _ in range(3):
        T(c, "WAIT")
    return done(c)


@scen("A3", (0, 1))
def a3_eat_all(c):
    """The B5 lesson overdone: eat every food through the FOOD quick slot until none is left (a full stomach, then more)."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 26)
    U.to_floor(p, 1)
    U.walk_to(p, 17)
    foods = []
    for _ in range(14):
        if not any(t in FOOD_TYPES for t in bag_types(p)):
            break
        f0 = p.rb("FOOD")
        if not U.quick(p, U.QS_FOOD_ICON):
            break
        foods.append((f0, p.rb("FOOD")))
    if any(b < a - 1 for a, b in foods):
        c.fail(f"eating lowered FOOD: {foods}")
    if p.rb("FOOD") < 30:
        c.fail(f"FOOD {p.rb('FOOD')} after eating everything ({foods})")
    print(f"  food trail {foods}", flush=True)
    return done(c)


@scen("A4", (0, 1))
def a4_cure_early(c):
    """B: jump the dart (never poisoned), pick the Cure and drink it from the bag unpoisoned (B9 alt line); then eat a drink twice."""
    p = c.p
    to_B(c)
    U.walk_to(p, 10)
    T(c, "K", "L")                                       # over the dart at col 13
    if p.ent(0)["X"] < 14:
        c.fail(f"leap did not clear the dart (x {p.ent(0)['X']})")
    U.walk_to(p, 19)
    T(c, "WAIT")
    ok = U.page_use(p, S["IT_P_CURE"], "icon" if c.hero == 0 else "I")
    refused = any(l.rstrip() == "NO NEED" for l in p.LOG)
    print(f"  cure drunk unpoisoned: turn passed {ok}, 'NO NEED' refusal {refused}, cure still in bag {S['IT_P_CURE'] in bag_types(p)}", flush=True)
    if ok or not refused or S["IT_P_CURE"] not in bag_types(p):
        c.fail("expected a free refusal ('NO NEED') that keeps the Cure")
    T(c, "WAIT")
    return done(c)


@scen("A5a", (0, 1))
def a5a_scroll_early(c):
    """Read the Sleep scroll in room A at B0 (no Goblin anywhere); the later fight has no scroll (the known B13 skip)."""
    p = c.p
    used = U.quick(p, U.QS_SCROLL_ICON)
    for _ in range(3):
        T(c, "WAIT")
    ok = to_C(c)
    ok = done(c) and ok
    if 13 in c.run.beats:
        print("  note: B13 was reached although the scroll was spent early", flush=True)
    print(f"  scroll early: used {used} beats {beats_str(c)}", flush=True)
    return ok


@scen("A5b", (0, 1))
def a5b_scroll_late(c):
    """Kill the Goblin first, then read the Sleep scroll with the Goblin dead (before the exit)."""
    p = c.p
    to_C(c)
    dead = kill_goblin(c)
    if not dead:
        c.fail("goblin not killed")
    used = U.quick(p, U.QS_SCROLL_ICON)
    T(c, "WAIT")
    print(f"  scroll with the Goblin dead: used {used} beats {beats_str(c)}", flush=True)
    return done(c)


@scen("A6", (0, 1))
def a6_hit_mentor(c):
    """Attack / cast / throw at the mentor from beside him (every icon slot, FIRE at his box), spam melee into the box."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 8)                                      # beside A1 (box cols 9..11)
    for rep in range(2):
        for slot in range(0, 6):
            c.step = f"slot {slot}"
            T(c, f"@{slot}")
            ensure_play(p)
    for _ in range(8):
        T(c, "L")                                        # walk / bump into his box
    U.select_slot = None
    p.tap("1")                                           # back to slot 0
    p.tick(2)
    ensure_play(p)
    if p.rb("GAME_STATE") != GS_PLAYING:
        c.fail(f"state {p.rb('GAME_STATE')} after attacking the mentor")
    return done(c)


@scen("A7")
def a7_in_mentor_box(c):
    """Stand inside the mentor's box (A1, cols 9..11) and wait ~80 turns (nag / repeat pressure, the box under the hero)."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 10)
    n0 = len(p.LOG)
    for i in range(80):
        T(c, "WAIT")
    spam = {}
    for l in p.LOG[n0:]:
        spam[l.rstrip()] = spam.get(l.rstrip(), 0) + 1
    worst = max(spam.values(), default=0)
    print(f"  80 waits in the box: beat {U.tv(p, 'TV_BEAT')} lines {len(p.LOG) - n0} worst repeat {worst}", flush=True)
    if worst > 12:
        c.fail(f"one line logged {worst}x in 80 waits")
    return done(c)


def up_to_storey0(c, ladder=12, n=14):
    """Walk to the ladder column on storey 1 and climb to storey 0."""
    p = c.p
    if U.storey(p) == 0:
        return True
    U.walk_to(p, ladder)
    for _ in range(n):
        if U.storey(p) == 0:
            break
        T(c, "K")
    return U.storey(p) == 0


def climb_up_to(c, room, n=40):
    p = c.p
    for _ in range(n):
        if p.rb("CUR_ROOM") == room:
            break
        T(c, "K")
    if p.rb("CUR_ROOM") == room:
        for _ in range(4):                               # the shaft drops the hero one rung below the floor
            if p.ent(0)["Y"] <= U.STAND_Y[1]:
                break
            T(c, "K")
        return True
    return False


@scen("A8", (0, 1))
def a8_back_to_A(c):
    """After the key (room B) go to C, then walk all the way back: C -> B -> up L1 -> the shaft -> A, wait there, go down again."""
    p = c.p
    if not to_C(c):
        c.fail("did not reach C")
    for _ in range(3):
        T(c, "H")
    for _ in range(25):
        if p.rb("CUR_ROOM") == 4:
            break
        T(c, "H")
    if p.rb("CUR_ROOM") != 4:
        c.fail("did not get back to B")
    U.walk_to(p, 24)
    for _ in range(14):
        if U.storey(p) == 0:
            break
        T(c, "K")
    U.walk_to(p, 5)
    if not climb_up_to(c, 1, 16):
        c.fail(f"did not climb back to A: {U.st(p)}")
    for _ in range(6):
        T(c, "WAIT")
    return done(c)


@scen("A9", (0, 1))
def a9_shaft_pit_loops(c):
    """Shaft down / up three times and the pit three times before any lesson (fall damage under mercy, L69 / L76 repeats)."""
    p = c.p
    U.to_floor(p, 0)
    for k in range(3):
        c.step = f"shaft loop {k}"
        U.walk_to(p, 12)
        U.to_floor(p, 1)
        U.walk_to(p, 5)
        U.to_floor(p, 1, room=4)
        for _ in range(2):
            T(c, "WAIT")
        if not climb_up_to(c, 1, 16):
            c.fail(f"loop {k}: no way back up: {U.st(p)}")
            break
    ensure_play(p)
    if not up_to_storey0(c):
        c.fail(f"could not climb to storey 0 in A: {U.st(p)}")
    for k in range(3):
        c.step = f"pit loop {k}"
        U.walk_to(p, 17)
        for _ in range(8):
            if U.storey(p) == 1:
                break
            T(c, "L")
        if U.storey(p) != 1:
            c.fail(f"pit loop {k}: no fall: {U.st(p)}")
            break
        U.walk_to(p, 26)
        for _ in range(14):
            if U.storey(p) == 0:
                break
            T(c, "K")
        if U.storey(p) != 0:
            c.fail(f"pit loop {k}: no ladder back: {U.st(p)}")
            break
    return done(c)


@scen("A10", (0,))
def a10_door_toggle(c):
    """B-C door: open (the key bump), pass, back, CLOSE it (FIRE on the melee icon), reopen - repeatedly."""
    p = c.p
    to_C(c)
    for k in range(4):
        c.step = f"door loop {k}"
        for _ in range(25):
            if p.rb("CUR_ROOM") == 4:
                break
            T(c, "H")
        T(c, "C")                                        # close it from B's side (FIRE, melee icon)
        T(c, "C")
        for _ in range(25):
            if p.rb("CUR_ROOM") == 5:
                break
            T(c, "L")
    return done(c)


def ranged_slots(p):
    return range(1, 6)


@scen("A11", (0, 1))
def a11_early_ranged_kill(c):
    """Kill the sleeping Goblin from range straight after entering C (Mage Spark / Warrior daggers, every ability slot)."""
    p = c.p
    to_C(c)
    beat0 = U.tv(p, "TV_BEAT")
    for _ in range(8):
        if U.goblin(p) is None or p.ent(0)["X"] >= 12:
            break
        T(c, "L")
    shots = 0
    for slot in ranged_slots(p):
        if p.rb("ST1_KILLS"):
            break
        U.icon_mode(p, True)
        U.cursor_to(p, slot)
        for _ in range(7):
            if p.rb("ST1_KILLS"):
                break
            g = U.goblin(p)
            if g is None:
                break
            if not U.fire_turn(p):
                break
            shots += 1
        U.icon_mode(p, False)
    print(f"  early ranged: {shots} shots from beat {beat0} killed={p.rb('ST1_KILLS')} beat now {U.tv(p, 'TV_BEAT')} beats {beats_str(c)}", flush=True)
    return done(c)


@scen("A12", (0, 1))
def a12_chase(c):
    """Wake the Goblin (one hit), then run: C -> B -> up the ladder -> A -> down again; it follows; finish wherever."""
    p = c.p
    to_C(c)
    for _ in range(40):
        g = U.goblin(p)
        if g and g[1]["HP"] < g[1]["MAXHP"]:
            break
        T(c, "L")
    for _ in range(50):                                  # run left and out of C, up L1 of B, left to the shaft, up to A
        r = p.rb("CUR_ROOM")
        if r == 1:
            break
        if r == 5:
            T(c, "H")
        elif r == 4:
            if U.storey(p) == 1 and p.ent(0)["X"] < 24:
                T(c, "L")
            elif U.storey(p) == 1 and p.ent(0)["X"] > 24:
                T(c, "H")
            elif U.storey(p) == 1:
                T(c, "K")
            elif p.ent(0)["X"] > 5:
                T(c, "H")
            else:
                T(c, "K")
    print(f"  chase: room {p.rb('CUR_ROOM')} goblin in room {U.goblin(p) and U.goblin(p)[1]['ROOM']} {U.st(p)}", flush=True)
    for _ in range(10):
        T(c, "WAIT")
    return done(c)


@scen("A13", (0, 1))
def a13_pause(c):
    """BREAK pause mid-turn, during a hold, and FIRE+UP; resume each time (the hold / turn must survive)."""
    p = c.p
    U.to_floor(p, 0)
    U.walk_to(p, 6)
    # mid-turn: start a step, press BREAK 2 ticks in
    for k in range(3):
        c.step = f"mid-turn pause {k}"
        p.hold("P")
        p.tick(2)
        p.hold("P", *BREAK_KEYS)
        p.tick(2)
        p.release()
        p.tick(4)
        if p.rb(PAUSED) == 0 and p.rb("PAUSE_REQ") == 0:
            pass
        ensure_play(p)
        p.tick(10)
    # FIRE+UP pause
    c.step = "FIRE+UP pause"
    p.hold("FIRE", "K")
    p.tick(3)
    p.release()
    p.tick(4)
    was = p.rb(PAUSED)
    ensure_play(p)
    if not was:
        print("  note: FIRE+UP did not pause here", flush=True)
    # during a hold: raise a hold with a turn that fires a group, then BREAK on it
    for k in range(6):
        c.step = f"hold pause {k}"
        p.turn("L" if k % 2 == 0 else "H")
        if U.tv(p, "TV_HOLD"):
            p.release()
            p.tick(3)
            p.hold(*BREAK_KEYS)
            p.tick(3)
            p.release()
            p.tick(5)
            ensure_play(p)
            break
        U.settle_holds(p)
    ensure_play(p)
    T(c, "WAIT")
    return done(c)


@scen("A14", (0,))
def a14_sound(c):
    """Toggle sound with S ten times in play and in the pause box, across a hold and a room change."""
    p = c.p
    modes = []
    for k in range(10):
        c.step = f"S {k}"
        p.tap("S")
        p.tick(2)
        modes.append(p.rb("SND_MODE") & 3)
        if k % 3 == 0:
            T(c, "WAIT")
    # pause box: SOUND item (RIGHT) cycled by FIRE, then resume
    p.hold(*BREAK_KEYS)
    p.tick(3)
    p.release()
    p.tick(3)
    if p.rb(PAUSED):
        p.tap("L")
        p.tick(3)
        for _ in range(3):
            p.tap("FIRE")
            p.tick(3)
            modes.append(p.rb("SND_MODE") & 3)
    ensure_play(p)
    print(f"  SND_MODE low bits trail {modes}", flush=True)
    if any(m not in (0, 2, 3) for m in modes):
        c.fail(f"illegal SND_MODE {modes}")
    ok = to_C(c)
    return done(c, ok)


@scen("A15", (0,))
def a15_idle(c):
    """Idle 330 turns at A: nudges, hunger. Reports FOOD / HP / lines; mercy must keep the hero alive."""
    p = c.p
    n0 = len(p.LOG)
    foods = []
    for i in range(330):
        T(c, "WAIT")
        if i % 30 == 0:
            foods.append((i, p.rb("FOOD"), p.ent(0)["HP"]))
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
    spam = {}
    for l in p.LOG[n0:]:
        spam[l.rstrip()] = spam.get(l.rstrip(), 0) + 1
    top = sorted(spam.items(), key=lambda kv: -kv[1])[:3]
    print(f"  idle: (turn, FOOD, HP) {foods}\n  most repeated lines {top} beat {U.tv(p, 'TV_BEAT')}", flush=True)
    return done(c)


@scen("A16", (0, 1))
def a16_icon_break(c):
    """Enter ICON MODE and leave with BREAK 20 times (BREAK must not pause), incl. during the first-entry holds."""
    p = c.p
    pr0 = p.rb("PAUSE_REQ")
    for k in range(20):
        c.step = f"icon/BREAK {k}"
        p.hold("J", "FIRE")
        p.tick(2)
        p.release()
        p.tick(2)
        U.settle_holds(p)
        p.hold(*BREAK_KEYS)
        p.tick(2)
        p.release()
        p.tick(3)
        if p.rb(PAUSED):
            c.fail(f"BREAK in ICON MODE paused (loop {k})")
            ensure_play(p)
    if p.rb("ICON_MODE"):
        c.fail("still in ICON MODE after BREAK x20")
    if p.rb("PAUSE_REQ") != pr0:
        c.fail(f"PAUSE_REQ moved {pr0} -> {p.rb('PAUSE_REQ')}")
    return done(c)


@scen("A17", (0, 1))
def a17_mash_holds(c):
    """Raise a hold, then mash keys: it must end after the first key and that key must not also move the hero (nor a FIRE tap /
    DOWN window poked in before the dismissal: TUT0-F3)."""
    p = c.p
    rng = random.Random(77)
    keys = ["P", "O", "Q", "A", "FIRE", "ENTER", "I", "1", "2", "S", "."]
    checks = 0
    U.to_floor(p, 0)
    for k in range(30):
        c.step = f"mash {k}"
        p.turn("L" if k % 2 == 0 else "H")
        if not U.tv(p, "TV_HOLD"):
            continue
        p.release()
        p.tick(3)
        if k % 2 == 0:                                   # TUT0-F3 3: input left from the turn's last tick must not act
            if k % 4 == 0:                               # after the dismissal: a queued use (IN_BAG: the page would open)
                p.wb("INTENT", S["IN_BAG"])
            else:                                        # a FIRE tap in progress + a DOWN window (a use / a wait turn)
                p.wb("FIRE_ST", S["FS_TAP"])
                p.wb("DN_T", 1)
        x0, t0 = p.ent(0)["X"], p.rw("TURN_COUNTER")
        n_log = len(p.LOG) if p.LOG is not None else 0
        presses = 0
        for presses in range(1, 81):                     # mash until it ends (a hold ignores keys until its text is drawn)
            p.hold(*rng.sample(keys, rng.randint(1, 3)))
            p.tick(1)
            p.release()
            p.tick(1)
            if not U.tv(p, "TV_HOLD"):
                break
        p.release()
        p.tick(4)
        checks += 1
        MASH.append(presses)
        if U.tv(p, "TV_HOLD"):
            U.dismiss(p)
            c.fail(f"mash {k}: the hold survived {presses} key presses")
        elif p.ent(0)["X"] != x0 or p.rw("TURN_COUNTER") != t0 or p.rb("PAGE_OPEN") \
                or (p.LOG is not None and len(p.LOG) != n_log):
            c.fail(f"mash {k}: the dismissing key (or the input before the hold) also acted (x {x0}->{p.ent(0)['X']}, "
                   f"turns {t0}->{p.rw('TURN_COUNTER')}, page {p.rb('PAGE_OPEN')}, log +{len(p.LOG or []) - n_log})")
        ensure_play(p)
    print(f"  mashed {checks} holds, presses needed {MASH[-checks:]}", flush=True)
    return done(c)


@scen("A18", (0,))
def a18_death_twice(c):
    """HP 1 at the pit (the fall kills: mercy only mends at a turn END): the D0 death flow -> card -> menu -> tutorial offered
    again -> a SECOND D0 run completed. (Flags the death itself as an I7 finding: see the report.)"""
    p = c.p
    c.expect_death = True
    U.to_floor(p, 0)
    U.walk_to(p, 16)
    for _ in range(12):
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
        p.set_ent(0, HP=1)
        T(c, "L")
    died = p.until(lambda: p.rb("GAME_STATE") == GS_DEAD, 60)
    print(f"  fatal fall at HP 1: died={died}", flush=True)
    if not died:
        c.expect_death = False
        return done(c)
    if not p.end_to_menu():
        c.fail("end card -> menu failed")
    p.tick(3)
    p.hold("1")
    p.tick(3)
    p.release()
    p.tick(3)
    if hooks(p) != MENUH or p.rb("GAME_STATE") != GS_SELECT:
        c.fail("the choice screen was not offered again")
    c.expect_death = False
    if not U.press_start(p, "1", "tut_d0"):
        c.fail("second D0 did not start")
        return False
    p.tick(3)
    c.run = U.Run(p)                                     # a fresh tracer for the second run
    c.step = "second run"
    if hooks(p) != D0H or U.tv(p, "TV_BEAT") != 0:
        c.fail(f"second D0 not fresh: {U.st(p)}")
    return done(c)


# =============================== B. random soak ================================================================
MOVES = [("P",), ("O",), ("Q",), ("A",), ("Q", "P"), ("Q", "O"), ("A", "P"), ("A", "O"), (".",)]
OTHER = [("FIRE",), ("A", "FIRE"), ("I",), ("1",), ("2",), ("3",), ("4",), ("5",), ("6",), ("7",), ("8",), ("9",), ("0",),
         BREAK_KEYS, ("S",), ("ENTER",), ("FIRE", "Q"), ("FIRE", "P"), ("FIRE", "O")]


def pick_input(rng):
    r = rng.random()
    if r < 0.5:
        return rng.choice(MOVES), rng.choice((1, 1, 2, 3, 5))
    if r < 0.58:
        return rng.sample(MOVES + OTHER, rng.randint(2, 3)) and tuple(
            k for grp in rng.sample(MOVES + OTHER, 2) for k in grp), 2
    return rng.choice(OTHER), rng.choice((1, 1, 2, 3, 12))


def soak(h, hero, seed, n_inputs):
    name = f"B{'W' if hero == 0 else 'M'}{seed}"
    c = begin(h, name, hero, seed=seed)
    c.hero = hero
    p, rng = c.p, random.Random(seed * 1009 + hero)
    t0, i0 = time.monotonic(), 0
    hist = []
    gs_seen = {}
    try:
        for i in range(n_inputs):
            i0 = i
            keys, hold_n = pick_input(rng)
            c.step = f"input {i} {keys} x{hold_n}"
            hist.append(c.step)
            del hist[:-6]
            p.hold(*keys)
            p.tick(hold_n)
            p.release()
            p.tick(1 + rng.randint(0, 2))
            STATS["inputs"] += 1
            gs = p.rb("GAME_STATE")
            gs_seen[gs] = gs_seen.get(gs, 0) + 1
            if i % 7 == 0 and U.tv(p, "TV_HOLD") and hooks(p) == D0H:
                U.dismiss(p)
            if i % 400 == 399 and p.rb(PAUSED):
                ensure_play(p)
            if gs == GS_DEAD:
                invariants(c)                            # flags a D0 death
                if not p.end_to_menu():
                    c.fail(f"input {i}: end card -> menu failed")
                    break
                p.tick(3)
            if p.rb("GAME_STATE") == GS_SELECT:
                if hooks(p) in (MENUH, D0H):
                    p.hold("1")
                    p.tick(3)
                    p.release()
                    p.tick(3)
                if p.rb("GAME_STATE") == GS_SELECT and hooks(p) == MENUH:    # on the choice screen
                    if not U.press_start(p, "1", "tut_d0"):
                        c.fail(f"input {i}: tutorial start failed")
                        break
                    p.tick(3)                            # TUT0-F4: as tut0.start: tt_init's goal line is presented first
                    c.run = U.Run(p)
                elif p.rb("GAME_STATE") == GS_SELECT and hooks(p) == D1H:
                    if not U.press_start(p, "1", "start_game"):
                        c.fail(f"input {i}: D1 start failed")
                        break
                p.tick(3)
    except Exception as e:
        viol(c, "I1 exception / hang", f"{e!r} at input {i0}; last inputs {hist}")
    crashed = any(k[0] == name and k[1].startswith("I1") for k in VIOL)
    if not crashed:
        ux_collect(c)
        finish_checks(c)
    ok = c.nviol == 0 and not c.fails
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {i0 + 1} inputs, {c.nt} ticks in {time.monotonic() - t0:.0f}s, "
          f"states {gs_seen}, overruns {c.max_ovr}" + ("" if crashed else f", hooks now {HOOK_NAMES.get(hooks(p))}, beat {U.tv(p, 'TV_BEAT')}"), flush=True)
    if not ok:
        print(f"  repro: seed {seed} class {hero}; last inputs {hist}", flush=True)
    return ok


# =============================== main ==========================================================================
def run_scen(h, sid, fn, hero):
    name = f"{sid}{'W' if hero == 0 else 'M'}"
    t0 = time.monotonic()
    c = None
    try:
        c = begin(h, name, hero)
        c.hero = hero
        ok = fn(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        if c is None:
            c = Ctx(name)
        viol(c, "I1 exception / hang", repr(e))
        ok = False
    ok = bool(ok) and c.nviol == 0 and not c.fails
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {fn.__doc__.splitlines()[0][:100]} "
          f"({c.nt} ticks, {time.monotonic() - t0:.0f}s, overruns {c.max_ovr}, beats {beats_str(c) if c.run else '-'})", flush=True)
    u = UX.get(name)
    if u:
        print(f"  UX {name}: turns {u['turns']} beats {u['beats']} never-shown first lines {u['missing']} "
              f"L75 x{u['l75']} L76 x{u['l76']} holds {u['holds']} log lines {u['lines']}", flush=True)
    return name, ok


def main():
    t0 = time.monotonic()
    results = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        if "--no-scen" not in ARGV:
            for sid, fn, heroes in SCEN:
                if ONLY is not None and sid not in ONLY:
                    continue
                for hero in (heroes if "--hero" not in ARGV else (opt("--hero", 0),)):
                    if hero in heroes or "--hero" not in ARGV:
                        results.append(run_scen(h, sid, fn, hero))
        n_seeds, n_in = opt("--seeds", 20), opt("--inputs", 3000)
        if "--no-soak" not in ARGV:
            s0 = opt("--seed0", 1)
            for hero in ((0, 1) if "--hero" not in ARGV else (opt("--hero", 0),)):
                for seed in range(s0, s0 + n_seeds):
                    ok = soak(h, hero, seed, n_in)
                    results.append((f"B{hero}{seed}", ok))
                    if any(k[0] == f"B{'W' if hero == 0 else 'M'}{seed}" and k[1].startswith("I1") for k in VIOL):
                        h.launch(EMU_ARGS)                  # the emulator died: a fresh one for the next seed
    bad = [n for n, ok in results if not ok]
    print(f"tut0_adv: {len(bad)} failed of {len(results)}: {bad}  ticks {STATS['ticks']} inputs {STATS['inputs']} "
          f"d0-ticks ~{STATS['d0_ticks']} heavy checks {STATS['heavy']} (I5 unsettled {STATS['i5_unsettled']}) overruns {STATS['overruns']}  ({time.monotonic() - t0:.0f}s)", flush=True)
    for (sc, kind), (n, d) in sorted(VIOL.items()):
        print(f"  VIOL {sc} {kind} x{n}: {d}")
    return 1 if bad or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
