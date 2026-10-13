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

Usage: python3 tests/budget.py      (exit 1 if any tick > budget)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0]] + ["999"]           # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_HOSTILE, EF_LEFT, stand_y  # noqa: E402

BUDGET = 2 * 70908
CAP = 126000                                      # D5: worst tick incl. the panel item
# D3-7 T1: the split ability turn. Ticks from the fire tick (probe_act_fire)
# until the deferred monster phase has run (TURN_PEND back to 0) are class
# "cast": they carry act_fire (proj_fire, 10-30k T, worst ~66k) or the moved
# resolve_monsters on top of the render. Gate: <= CAST_CAP (hard limit BUDGET);
# every other tick keeps its scenario's gate (CAP / BUDGET).
CAST_CAP = 128000
# B3B-11: panel_tick .. play_loop.nopanel = the tick's panel item (D5: one per
# tick, never in a turn's input tick); its present lands in the next tick_work.
PHASES = ["tick_work", "intent_tick", "read_turn_input", "pend_far", "probe_act_fire", "anim_tick", "render",
          "decor_tick", "panel_tick", "panel_done", "wait_tick"]
if os.environ.get("GAME_PROFILE"):                # finer split for optimisation work
    PHASES = ["tick_work", "intent_tick", "read_turn_input", "pend_far", "probe_act_fire",
              "try_player_turn", "resolve_monsters",
              "materialise", "anim_tick", "render", "render.nopend", "render.sdone",
              "render.f3done", "render.drdone", "render.nopl", "pmark_dmg", "present",
              "decor_tick", "panel_tick", "panel_done", "wait_tick"]
    PHASES += [n for n in os.environ["GAME_PROFILE"].split(",") if n in S]


RETURNS = {}


class Stepper:
    def __init__(self, p):
        self.p, self.z = p, p.z
        self.ticks = []                       # (total, {phase: T})
        self.cast_ix, self.casting = set(), False  # D3-7: indices of "cast" class ticks
        self.fire_t = []                      # D3-7 T4: the fire ticks' totals
        # B3B-11b log latency: FIFO ring -> drawn = LQ_RD advances, pushed = drawn + LOG_QN
        self.rd, self.drawn, self.pushed = p.rb(S["LOG_Q"] + S["LQ_RD"]), 0, p.rb("LOG_QN")
        self.push_tick, self.lat = [0] * self.pushed, []
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
        k = len(self.ticks)
        if "probe_act_fire" in split:         # D3-7: the fire tick opens the cast class
            self.casting = True
            self.fire_t.append(prev)
        if self.casting:
            self.cast_ix.add(k - 1)
            if self.p.rb("TURN_PEND") == 0:   # monsters resolved (or the hero died): closed
                self.casting = False
        rd, qn = self.p.rb(S["LOG_Q"] + S["LQ_RD"]), self.p.rb("LOG_QN")
        self.drawn += (rd - self.rd) % S["LOG_SLOTS"]
        self.rd = rd
        for _ in range(self.drawn + qn - self.pushed):
            self.push_tick.append(k)
        self.pushed = self.drawn + qn
        if os.environ.get("LOG_TRACE"):
            pre = sum(v for n_, v in split.items() if n_ not in ("panel_tick", "panel_done", "wait_tick"))
            print(f"[trace] t{k} {prev} pre-panel {pre} panel {split.get('panel_tick', 0)} qn {qn}"
                  f" render {split.get('render', 0)} pend {split.get('pend_far', 0)} present {split.get('tick_work', 0)}"
                  f" ph {self.p.rb('TURN_PHASE')}/{self.p.rb('TURN_TICK')}")
        while len(self.lat) < self.drawn:
            self.lat.append(k - self.push_tick[len(self.lat)])
        return prev

    def turn(self, *keys, max_ticks=80):
        """One scripted action on the C3 controls, every tick measured: the
        0-turn turn-around tap / slot select (_prep) and FIRE taps included."""
        keys, fire = self.p._prep(keys, step=self.tick)
        t0 = self.p.rw("TURN_COUNTER")
        self.p.hold(*keys)
        if fire:                                  # FIRE acts on release
            self.tick()
            self.p.release()
        for i in range(max_ticks):
            self.tick()
            if i == 1:
                self.p.release()
            if self.p.rw("TURN_COUNTER") != t0 and self.p.rb("TURN_PHASE") == 0:
                break
            if i >= 6 and self.p.rw("TURN_COUNTER") == t0 and self.p.rb("TURN_PHASE") == 0:
                break                             # nothing legal: no turn
        self.p.release()
        self.tick()

    def close(self):
        for i in range(len(PHASES)):
            self.z.cmd("set-breakpoint %d" % (i + 1))    # cleared, not just disabled
        self.p.load_breakpoints()


HOSTILE = EF_ACTIVE | EF_HOSTILE | EF_LEFT
RIGHT = EF_ACTIVE | EF_HOSTILE
# C3-8a: FIRE taps (melee icon via use_icon / far3) + a bump, a turn-around tap
# then the walk away, '.' waits: the whole intent_tick path is measured.
KEYS = [("FIRE", 3), ("L", 3), ("H", 4), ("WAIT", 4)]
# Gate: "mix" must keep every tick within the 2-frame budget. It is the M1
# encounter cap exactly (game.md §9.3: skeleton tall 5 + goblin medium 3 + rat
# small 2 + bat small 2 = 12, 4 monsters) with the hero's slash on top.
# "heavy" (hero + 2 skeletons + goblin + ghost = 5+5+3+3 = 16 > 12) is OVER
# the cap: a REPORTED stress scenario only (rare 3-frame ticks accepted, no
# flicker with the A7 double buffer; renderer optimisation = A7b).
GATED = ("mix", "mage")
CAP_GATED = ("lightning", "cast", "lcast", "wcast", "wcast4", "acast")        # D3-5: worst ordinary tick <= CAP
# B3B-3 (2 x 9): everything on the bottom storey (s 1) of room A, the PROTO
# storey-2 layout moved up 3 rows (the floor row 20 -> 17).
HERO_Y = stand_y(1, 6)                            # 11
SCENARIOS = {
    # hero + 4 monsters in A (cap), all visible, all close enough to act
    "mix": ("knight + skeleton, rat, goblin, bat", [
        (5, 15, stand_y(1, 6), HOSTILE),          # skeleton adjacent (gap 0)
        (1, 22, stand_y(1, 2), HOSTILE),          # rat walking in
        (3, 25, stand_y(1, 4), HOSTILE),          # goblin walking in
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS),  # bat, storey-1 band
    # C3-7: the same cap mix with the Mage: STAFF_RAISE -> the 40-px STAFF_SWING
    # (gap 0 melee) on the skeleton while everything else moves / attacks
    "mage": ("mage + skeleton, rat, goblin, bat", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_WIZARD),
    # D3-5: the mage mix with a Lightning (+ 2 flashes, 3 tracks) every turn
    "lightning": ("mage + 4 monsters + Lightning every turn", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_WIZARD, "fx"),
    # review A1 worst mix: 2 skeletons (both 40-px attacks), goblin, ghost
    # D3-7 T1: "lightning" with the monster phase deferred past the hero's FX
    "cast": ("mage + 4 monsters + Lightning, split turn (monsters after the FX)", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_WIZARD, "cast"),
    # D3-7 T4: the real cast through the controls — Lightning r3 (4 MP, range
    # 28, 3 bounces, pierce) from x 14 facing left through 4 monsters in line
    # (60 HP each) to the room's left wall (13 cells), bounced back through
    # all 4 AND the caster (HP 200): 9 hits — the worst proj_fire (~66-70k T
    # in tests/proj3.py) + deal_hit messages on the fire tick; the deferred
    # monster phase after the FX
    "lcast": ("mage Lightning r3 through 4 monsters + the caster in line", [
        (5, 1, stand_y(1, 6), RIGHT),
        (3, 5, stand_y(1, 4), RIGHT),
        (2, 8, stand_y(1, 2), RIGHT),
        (1, 11, stand_y(1, 2), RIGHT)], [("FIRE", 3)], K_WIZARD, None, "lcast"),
    # D3-7 T5: the real Whirlwind r3 (3 MP) through the controls, 3 bodies in
    # reach (Skeleton left gap 0; Rat + Bat over it right gap 0), all 60 HP: 3
    # blows + 3 lines + 2 spark_fizz FX on the fire tick; a Goblin walking in
    "wcast": ("knight Whirlwind r3 on Skeleton + Rat + Bat", [
        (5, 9, stand_y(1, 6), RIGHT),
        (1, 15, stand_y(1, 2), HOSTILE),
        (4, 15, stand_y(1, 6), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE)], [("FIRE", 3)], K_KNIGHT, None, "wcast"),
    # T7 review: the Whirlwind worst case at the room cap (ROOM_CAP 4, all in reach:
    # 2 per side, overlapping — Skeleton + Goblin left, Skeleton + Rat right, gap 0):
    # 4 blows + 4 lines + 2 FX on the fire tick, 4 replies after the log drain
    "wcast4": ("knight Whirlwind r3 on 2 Skeletons + Goblin + Rat (ROOM_CAP, all in reach)", [
        (5, 9, stand_y(1, 6), RIGHT),
        (3, 9, stand_y(1, 4), RIGHT),
        (7, 15, stand_y(1, 6), HOSTILE),
        (1, 15, stand_y(1, 2), HOSTILE)], [("FIRE", 3)], K_KNIGHT, None, "wcast"),
    # D3-7 T6: the real bow shot through the controls (range 14), 4 monsters in
    # line to the right (60 HP; missed rolls fly on: up to 4 hit rolls + deal_hit
    # on the fire tick), a Skeleton behind walking in, 3 shots
    "acast": ("knight bow shots through Rat, Goblin, Slime, Skeleton in line", [
        (1, 17, stand_y(1, 2), HOSTILE),
        (3, 20, stand_y(1, 4), HOSTILE),
        (2, 23, stand_y(1, 2), HOSTILE),
        (5, 26, stand_y(1, 6), HOSTILE)], [("FIRE", 3)], K_KNIGHT, None, "acast"),
    "heavy": ("knight + 2 skeletons, goblin, ghost", [
        (5, 15, stand_y(1, 6), HOSTILE),          # skeleton C right, gap 0
        (7, 8, stand_y(1, 6), RIGHT),             # skeleton D left, gap 1
        (3, 20, stand_y(1, 4), HOSTILE),          # goblin
        (6, 4, stand_y(1, 4) - 1, RIGHT)], KEYS),  # ghost, storey-1 band, starts in
                                                  # {5,1}'s end box (legal again: flyers
                                                  # cross shafts, rule 2026-10-02)
}


# B3B-10: the PROTO rooms carry no animated decor (RD_SEED 0), so the
# scenarios get a synthetic FULL ANIM_LIST in room A (4 glyph swaps + 8 attr
# cycles = the deriver's budget maximum, ALL with the same stagger so the
# per-tick caps bind and the deferred steps pile into the following ticks),
# placed in the fight band (storey 1, rows 11-14) and storey 0. BUDGET_DECOR=0
# measures without it.
DECOR = os.environ.get("BUDGET_DECOR", "1") != "0"
DECOR_GLYPH = [(10, 12), (18, 13), (12, 3), (20, 4)]
DECOR_ATTR = [(9, 12), (14, 13), (16, 11), (20, 14), (11, 2), (15, 4), (27, 3), (27, 12)]


def inject_decor(p):
    """Synthetic ANIM_LIST for room A (in ROOM_MAP): glyph cells get the D1
    tall-torch body id 36 in the map and its tip id 40 as the swap partner
    (both non-solid, ids >= 16); attr cells kinds 1 / 2. Phase 3 = all due on
    the next tick. Cells must be AIR (asserted)."""
    al = []
    for c, r in DECOR_GLYPH:
        a = S["ROOM_MAP"] + r * 32 + c
        assert p.rb(a) == S["T_AIR"], (c, r)
        p.wb(a, 36)
        al += [c, r, 40, 3]
    for k, (c, r) in enumerate(DECOR_ATTR):
        assert p.rb(S["ROOM_MAP"] + r * 32 + c) == S["T_AIR"], (c, r)
        al += [c, r, 1 + (k & 1), 3]
    p.z.cmd("write-memory %d %s" % (S["ANIM_LIST"], " ".join(str(b) for b in al)))
    p.wb("ANIM_N", len(al) // 4)


def fx_cast(p):
    """Queue the hero's Lightning (+ flashes on slots 3 and 1) through ZRCP
    from the wait_tick probe; returns the fx_start accept flags."""
    import combat
    e = p.ent(0)
    row = e["Y"] + 2
    if e["FLAGS"] & EF_LEFT:
        col, segs = e["X"] - 1, (e["X"] - 2, 28 - (e["X"] - 2))
    else:
        col, segs = e["X"] + 3, (30 - (e["X"] + 3), 28 - (30 - (e["X"] + 3)))
    out = [combat.C.fx_call(p, combat.desc("lightning_fly1", "lightning_fly2", "lightning_flash",
                                           "lightning_flash", col, row, left=bool(e["FLAGS"] & EF_LEFT),
                                           fast=True, impt=2, segs=segs))[0]]
    for slot, delay in ((3, 3), (1, 5)):
        m = p.ent(slot)
        if m["FLAGS"] & EF_ACTIVE and m["ROOM"] == 0:
            out.append(combat.C.fx_call(p, combat.desc(None, None, "lightning_flash", "lightning_flash",
                                                        m["X"], min(row, 16), delay=delay, impt=4))[0])
    return out


class FxStepper(Stepper):
    """D3-5 "lightning": every turn of the Mage starts a Lightning (16 px/tick,
    2 bounces, range 28, 16x16 flash) from the hero's staff row plus two
    impact-only flashes on the struck bodies (3 tracks = the cap), queued by
    fx_start through ZRCP on the turn's first tick (tests/combat.py fx_call;
    abilities come in D3-7). Also counts the cells erase_rect restores per
    tick (D3-S2 dropped the bank-7 bitmap shadow: ~+37 T per cell, measured in)."""

    def __init__(self, p):
        self.erase_cells, self.cur_cells, self.turn_seen = [], 0, None
        self.casts, self.fx_ticks = [], 0
        super().__init__(p)
        self.z.cmd("set-breakpoint %d PC=%d" % (len(PHASES) + 1, S["erase_rect"]))

    def _run(self):
        while True:
            self.z.cmd("run")
            r = self.z.cmd("get-registers")
            pc = int(r[3:7], 16)
            if pc == S["erase_rect"]:
                de = int(r.split("DE=")[1][:4], 16)
                self.cur_cells += (de >> 8) * (de & 0xFF)
                self.z.cmd("cpu-step")
                continue
            return self.inv.get(pc), int(self.z.cmd("get-tstates-partial"))

    def tick(self):
        self.cur_cells = 0
        v = super().tick()
        self.erase_cells.append(self.cur_cells)
        p = self.p
        self.fx_ticks += p.rb("FX_BUSY") != 0
        tc = p.rw("TURN_COUNTER")
        if p.rb("TURN_PHASE") == 1 and self.turn_seen != tc:
            self.turn_seen = tc
            self.cast()
        return v

    def cast(self):
        self.casts += fx_cast(self.p)


class CastStepper(FxStepper):
    """D3-7 T1 "cast": the lightning scenario as a split ability turn. Before
    every action the TURN_PEND block is poked as act_begin leaves it (Lightning,
    ACT_AT 2, MON_AT 3), so turn_input skips resolve_monsters, act_pend fires at
    tick 2 (spell_fire: a T1 stub) and runs the monster phase once the Lightning
    FX (queued on the turn's first tick, as in "lightning") is idle."""

    def turn(self, *keys, **kw):
        p = self.p
        p.z.cmd("write-memory %d %d %d %d %d" % (S["TURN_PEND"], S["TP_ACT"] | S["TP_MON"], S["ABL_LIGHTNING"],
                                                  S["ACT_FIRE_TICK"], S["ACT_FIRE_TICK"] + 1))
        # D3-7 T4: spell_fire is real now; a range-0 Lightning row keeps this
        # scenario the engine-only measurement ("lcast" is the real cast)
        p.z.cmd("write-memory %d %s" % (S["RANK_ROWS"] + 6 * S["ABL_LIGHTNING"], " ".join(["0"] * 6)))
        super().turn(*keys, **kw)

    def close(self):
        self.z.cmd("set-breakpoint %d" % (len(PHASES) + 1))
        super().close()


def lcast_setup(p, placements):
    """"lcast": the hero at x 14 facing left (HP 200), the monsters 60 HP,
    Lightning learned at rank 3 (ARANK + its RANK_ROWS row, as rank_sync),
    MP 40, the Lightning slot selected (no turn)."""
    import combat_tables as CT
    sym, b3 = CT.load()
    k, r = S["ABL_LIGHTNING"], 3
    row = sym["ab_rank"] - CT.BASE + (k * 3 + r - 1) * 6
    p.set_ent(0, X=14, PX=14 * 8, FLAGS=EF_ACTIVE | 2 | EF_LEFT, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
    p.z.cmd("write-memory %d %s" % (S["RANK_ROWS"] + 6 * k, " ".join(str(b) for b in b3[row:row + 6])))
    p.z.cmd("write-memory %d %d %d" % (S["ARANK"], (r << (2 * k)) & 255, (r << (2 * k)) >> 8))
    p.wb("MP", 40)
    p.wb("MAXMP", 40)
    p.select_slot(k + 1)


def wcast_setup(p, placements):
    """"wcast": the hero at x 12 facing right (HP 200), the monsters 60 HP,
    Whirlwind learned at rank 3 (ARANK + its RANK_ROWS row, as rank_sync),
    MP 40, the Whirlwind slot selected (no turn)."""
    import combat_tables as CT
    sym, b3 = CT.load()
    a, r = S["ABL_WHIRL"], 3
    k = a - S["ABL_POWER"]
    row = sym["ab_rank"] - CT.BASE + (a * 3 + r - 1) * 6
    p.set_ent(0, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
    p.z.cmd("write-memory %d %s" % (S["RANK_ROWS"] + 6 * k, " ".join(str(b) for b in b3[row:row + 6])))
    p.z.cmd("write-memory %d %d %d" % (S["ARANK"], (r << (2 * k)) & 255, (r << (2 * k)) >> 8))
    p.wb("MP", 40)
    p.wb("MAXMP", 40)
    p.select_slot(k + 1)


def acast_setup(p, placements):
    """"acast": the hero at x 12 facing right (HP 200), the monsters 60 HP,
    the bow in the bag, ARROWS 24, the bow slot selected (no turn)."""
    p.set_ent(0, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
    p.wb("HAS_BOW", 1)
    p.wb("ARROWS", 24)
    p.select_slot(4)


def run_scenario(h, scen):
    name, placements, keys = scen[:3]
    p = game.T(h)
    p.boot(scen[3] if len(scen) > 3 else K_KNIGHT, freeze=0)
    p.isolate()
    p.place(0, 12, HERO_Y)
    for slot, x, y, flags in placements:
        p.place(slot, x, y, room=0, flags=flags)
    if DECOR:
        inject_decor(p)
    if len(scen) > 5 and scen[5] == "lcast":
        lcast_setup(p, placements)
    if len(scen) > 5 and scen[5] == "wcast":
        wcast_setup(p, placements)
    if len(scen) > 5 and scen[5] == "acast":
        acast_setup(p, placements)
    mode = scen[4] if len(scen) > 4 else None
    st = {"fx": FxStepper, "cast": CastStepper}.get(mode, Stepper)(p)
    swing = 0
    for key, n in keys:
        for _ in range(n):
            p.clear_trace()
            st.turn(key)
            swing += S["FID_wizard_staffswing"] in p.trace_fids(0)
    st.close()
    totals = [t for t, _ in st.ticks]
    worst = max(st.ticks, key=lambda x: x[0])
    over = [t for t in totals if t > BUDGET]
    casts = [totals[i] for i in sorted(st.cast_ix)]
    ordinary = [t for i, t in enumerate(totals) if i not in st.cast_ix]
    ovc = p.rw("OVERRUN_COUNT")
    print(f"== {name}")
    print(f"ticks measured : {len(totals)}")
    print(f"max tick       : {worst[0]} T  ({worst[0] / BUDGET * 100:.1f}% of {BUDGET})")
    print(f"mean tick      : {sum(totals) // len(totals)} T")
    print(f"worst split    : " + ", ".join(f"{k}={v}" for k, v in worst[1].items()))
    print(f"ticks > budget : {len(over)}")
    print(f"OVERRUN_COUNT  : {ovc}  BLIT_MISS: {p.rb('BLIT_MISS')}", flush=True)
    if isinstance(st, FxStepper):
        wi = totals.index(worst[0])
        ec = st.erase_cells
        print(f"fx lightning   : worst tick {worst[0]} T, headroom to {CAP}: {CAP - worst[0]} T;"
              f" erased cells worst tick {ec[wi]}, max/tick {max(ec)} (D3-S2: erase redraws from"
              f" ROOM_MAP, +37 T/cell, already in these ticks);"
              f" {sum(st.casts)}/{len(st.casts)} fx_start accepted, {st.fx_ticks} ticks with FX live", flush=True)
    if len(scen) > 3:                             # C3-7: did the staff swing run?
        print(f"staff swings   : {swing} turns drew STAFF_SWING", flush=True)
    dts = [sp.get("decor_tick", 0) for _, sp in st.ticks]
    print(f"decor_tick     : {'on' if DECOR else 'off'}, max {max(dts)} T, mean {sum(dts) // len(dts)} T"
          f" (incl. the call / panel test to panel_tick)", flush=True)
    cap = [t for t in ordinary if t > CAP]
    lat = st.lat
    print(f"ticks > {CAP} : {len(cap)}  (D5 cap, ordinary ticks)")
    print(f"cast ticks     : {len(casts)} (fire tick .. monsters resolved), max {max(casts) if casts else 0} T"
          f" (cap {CAST_CAP}), {sum(1 for t in casts if t > CAST_CAP)} over; ordinary max"
          f" {max(ordinary) if ordinary else 0} T", flush=True)
    st.casts_t, st.ordinary_t = casts, ordinary
    print(f"FX_DROP        : {p.rb('FX_DROP')}; fire ticks {st.fire_t} T", flush=True)
    if len(scen) > 5:
        print("HP after       : " + ", ".join(f"slot {sl} {p.ent(sl)['HP']}" for sl in [0] + [q[0] for q in placements]),
              flush=True)
    print(f"log latency    : {len(lat)} messages drawn, max {max(lat) if lat else 0} ticks after the push"
          f" (histogram {dict(sorted({v: lat.count(v) for v in lat}.items()))}), still queued {p.rb('LOG_QN')},"
          f" dropped {p.rb(S['LOG_Q'] + S['LQ_DROP'])}", flush=True)
    return st, over


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        for key in os.environ.get("BUDGET_ONLY", "mix,mage,heavy,lightning,cast,lcast,wcast,wcast4,acast").split(","):
            st, bad = run_scenario(h, SCENARIOS[key])
            if any(t > CAST_CAP for t in st.casts_t):
                fails.append(key + " (cast)")
            elif key in ("cast", "lcast", "wcast", "wcast4", "acast") and not st.casts_t:
                fails.append(key + " (no cast tick seen)")
            elif key in CAP_GATED and max(st.ordinary_t) > CAP:
                fails.append(key)
            elif bad and key in GATED:
                fails.append(key)
            elif bad:
                print(f"[info] {key}: {len(bad)} ticks over budget (reported, not gated)")
    print(f"[{'FAIL' if fails else 'PASS'}] budget gate (every tick <= budget in"
          f" {', '.join(GATED)}; <= {CAP} in {', '.join(CAP_GATED)}; cast ticks <= {CAST_CAP}): {fails or 'ok'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
