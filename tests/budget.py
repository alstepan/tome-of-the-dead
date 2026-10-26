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
# SND-2 T5: the measured window tick_work -> wait_tick INCLUDES the frame-N+1 ISR
# (fires inside it on ticks over ~70.2k T) but EXCLUDES the HALT-side frame-N ISR
# (runs before tick_work). Real deadline: M + 402 + P(N) <= BUDGET, M = the measured
# total, P(N) = the worst ISR (player) time. So per tick: isr_in = time inside
# [isr, isr.done); work = total - isr_in (gated by CAP / CAST_CAP as before);
# real = total + PRE_MAX (gated by BUDGET), PRE_MAX = 402 + max isr_in of the
# scenario's run, floored at PRE_FLOOR.
PRE_FLOOR = 5300
PRE_BASE = 402
MUS_POKE = os.environ.get("BUDGET_MUS", "7")      # MUS_REQ poked before START ("" = no poke)
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
# D3-8d: callables f(stepper) run after every measured tick (tests/marks.py
# reads MK_OPS there: the mark ops of that tick)
TICK_HOOKS = []


class Stepper:
    def __init__(self, p):
        self.p, self.z = p, p.z
        self.ticks = []                       # (total, {phase: T})
        self.isr_in = []                      # per tick: T spent in [isr, isr.done)
        self.cast_ix, self.casting = set(), False  # D3-7: indices of "cast" class ticks
        self.fire_t = []                      # D3-7 T4: the fire ticks' totals
        self.trans_t = []                     # 3E-T16: room-change (transition) ticks, not gated
        # B3B-11b log latency: FIFO ring -> drawn = LQ_RD advances, pushed = drawn + LOG_QN
        self.rd, self.drawn, self.pushed = p.rb(S["LOG_Q"] + S["LQ_RD"]), 0, p.rb("LOG_QN")
        self.push_tick, self.lat = [0] * self.pushed, []
        z = self.z
        z.cmd("enter-cpu-step")
        z.cmd("enable-breakpoints")
        for i, n in enumerate(PHASES):
            z.cmd("set-breakpoint %d PC=%d" % (i + 1, S[n]))
        # ISR breakpoints sit on ids past every other user's (erase_rect = len(PHASES)+1)
        z.cmd("set-breakpoint %d PC=%d" % (len(PHASES) + 10, S["isr"]))
        z.cmd("set-breakpoint %d PC=%d" % (len(PHASES) + 11, S["isr.done"]))
        self.inv = {S[n]: n for n in PHASES}
        self.inv[S["isr"]], self.inv[S["isr.done"]] = "isr", "isr.done"
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
        room0 = self.p.rb("CUR_ROOM")
        self.z.cmd("reset-tstates-partial")
        split, last, prev, saved, isr_t = {}, "tick_work", 0, None, 0
        while True:
            n, v = self._run()
            split[last] = split.get(last, 0) + v - prev
            if last == "isr":
                isr_t += v - prev
            prev = v
            if n == "isr":                    # credit [isr, isr.done) to "isr", then resume
                saved, last = last, "isr"
            elif n == "isr.done":
                last = saved
            elif n in RETURNS:                  # returning into a phase: credit it
                last = RETURNS[n]
            else:
                last = n
            if n == "wait_tick":
                break
        if self.p.rb("CUR_ROOM") != room0:    # 3E-T16 "ttele": the teleport's frozen room build /
            self.trans_t.append(prev)         # draw / present (a transition, as a room exit):
            print(f"[info] transition tick {prev} T (room {room0} -> {self.p.rb('CUR_ROOM')}),"
                  f" not gated", flush=True)
            return                            # reported, not a play tick
        self.ticks.append((prev, split))
        self.isr_in.append(isr_t)
        for f in TICK_HOOKS:
            f(self)
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
        for bp in list(range(1, len(PHASES) + 1)) + [len(PHASES) + 10, len(PHASES) + 11]:
            self.z.cmd("set-breakpoint %d" % bp)    # cleared, not just disabled
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
CAP_GATED = ("lightning", "cast", "lcast", "lcastf", "lcasts", "advcast", "fzcast", "fzcast2", "fcast", "wcast", "wcast4", "acast", "mkmix",
             "pmix", "umix", "tdart", "tgas", "ttele", "talarm", "tsearch", "tsense")
CAST_KEYS = ("cast", "lcast", "lcastf", "lcasts", "advcast", "fzcast", "fzcast2", "fcast", "wcast", "wcast4", "acast")        # D3-5: worst ordinary tick <= CAP
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
    # D3-8 review: "lcast" with all 4 monsters FROZEN 1 — tinted ($45 / the
    # BRIGHT twin) through the fire tick, the HOLD expiring in the deferred
    # monster phase (st_step: the tint drops, 4 bodies re-stamped)
    "lcastf": ("mage Lightning r3 through 4 FROZEN-1 monsters + the caster in line", [
        (5, 1, stand_y(1, 6), RIGHT),
        (3, 5, stand_y(1, 4), RIGHT),
        (2, 8, stand_y(1, 2), RIGHT),
        (1, 11, stand_y(1, 2), RIGHT)], [("FIRE", 3)], K_WIZARD, None, "lcastf"),
    # D3-8 review 2: "lcastf" with all 4 monsters ASLEEP (ST_FLAGS 2): the
    # Lightning wakes each one -> 4 wake lines on the fire tick (was measured
    # with BUDGET_STF=2 only)
    "lcasts": ("mage Lightning r3 through 4 ASLEEP monsters (4 wake lines) + the caster", [
        (5, 1, stand_y(1, 6), RIGHT),
        (3, 5, stand_y(1, 4), RIGHT),
        (2, 8, stand_y(1, 2), RIGHT),
        (1, 11, stand_y(1, 2), RIGHT)], [("FIRE", 3)], K_WIZARD, None, "lcasts"),
    # D3-8 review 2: the adversarial PF_ROWF fuzz worst case (#208, mirrored in
    # tests/proj3.py P10) through the real cast: ROOM_CAP 4 — Lightning r2 from
    # x 26 facing right, a Bat over the caster (x 28, HP 1), a reflecting Ghost
    # (x 19, HP 6), Slimes at x 24 (HP 6) / x 21 (HP 23); flight-row walls at
    # cols 0, 3 and 31 (poked): bounces + the Ghost's reflections walk the line
    # back and forth over the caster, 3 kills. Kinds are set by advcast_setup.
    "advcast": ("mage Lightning r2: reflecting Ghost + 2 Slimes + Bat around the caster, 3 kills", [
        (1, 28, stand_y(1, 2), RIGHT),
        (2, 19, stand_y(1, 4), RIGHT),
        (3, 24, stand_y(1, 2), RIGHT),
        (4, 21, stand_y(1, 2), RIGHT)], [("FIRE", 3)], K_WIZARD, None, "advcast"),
    # D3-8e: the worst ROOM_CAP-legal casts of a model search over 2M layouts
    # (tests/proj3.py P11 mirrors them; box_free-disjoint bodies, no ladder
    # bodies): a SHOCK-reflecting Ghost and 2 Bats + a Rat / Slime stacked
    # between it and a wall, so the Lightning ping-pongs through the stack and
    # the caster until the range runs out (16 strikes; the HP keep every one).
    # "fzcast": Lightning r1 from x 23 facing left, bricks at cols 4 / 27 — the
    # stack overlaps the caster's box, so the fire tick's render is ~70k T on
    # its own (148.1k T before D3-8e: proj_fire ~97k on the fire tick).
    # "fzcast2": r3 from x 18 facing right, bricks at cols 12 / 31.
    # Kinds / HP / bricks are set by fzcast_setup (FZ).
    "fzcast": ("mage Lightning r1: Ghost <-> wall ping-pong through Rat + 2 Bats + the caster, 16 strikes", [
        (1, 26, 15, RIGHT),
        (2, 20, 15, RIGHT),
        (3, 17, 16, RIGHT),
        (4, 20, 10, RIGHT)], [("FIRE", 3)], K_WIZARD, None, "fzcast"),
    "fzcast2": ("mage Lightning r3: wall <-> Ghost ping-pong through Slime + 2 Bats + the caster, 16 strikes", [
        (1, 15, 15, RIGHT),
        (2, 12, 14, RIGHT),
        (3, 21, 15, RIGHT),
        (4, 14, 12, RIGHT)], [("FIRE", 3)], K_WIZARD, None, "fzcast2"),
    # D3-8 review: Frost Shard r2 (2 bounces, freeze 3) from x 7 facing left to
    # the left wall: the bounce comes back and freezes the caster (self-freeze
    # 1, §6.4.1: hero tint + panel icon + a held turn); Rat, Goblin, Skeleton,
    # Bat walking in from the right. The caster is the first body on the way
    # back (pierce-less), so 1 of the 2 bounces is the most a real cast uses.
    "fcast": ("mage Frost Shard r2 bounce -> self-freeze, 4 monsters", [
        (1, 24, stand_y(1, 2), HOSTILE),
        (3, 16, stand_y(1, 4), HOSTILE),
        (5, 20, stand_y(1, 6), HOSTILE),
        (4, 12, stand_y(1, 2) - 3, HOSTILE)], [("FIRE", 3)], K_WIZARD, None, "fcast"),
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
    # D3-8d: "mix" with every body under a HOLD / MIND status (15 turns): 5
    # overhead marks — a FROZEN Skeleton (the Knight's target), an ASLEEP Bat,
    # a CONFUSED Rat and a FEAR Goblin walking (their marks follow: erase +
    # draw = 2 ops), the hero CONFUSED — toggling every 8 ticks; <= 2 mark
    # ops a tick, gated <= CAP (tests/marks.py B reads MK_OPS per tick)
    "mkmix": ("knight + 4 monsters, all with status marks", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "mkmix"),
    # 3E-T11: "mix" with a bag item on every col of the hero's walk (a pickup at
    # each arrival: bag_add + the name line + ap_stamp) and a 1-HP skeleton (the
    # first slash kills it: mon_drop's roll / placement)
    "pmix": ("knight + 4 monsters, bag items under every step, a kill", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "pmix"),
    # 3E-T12: "mix" with the quick uses as the hero's actions (R6 fx_quick): two potions
    # (HP 5), three eats (the 3rd NO NEED at 100), three reads (Fear, Sleep, Fear over the
    # 4 monsters: room_status), then melee / waits
    "umix": ("knight + 4 monsters, quick potion / food / scroll uses", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)],
        [("G", 2), ("@5", 3), ("@7", 3), ("FIRE", 2), ("WAIT", 2)], K_KNIGHT, None, "umix"),
    # 3E-T16 (review 2026-10-26): "pmix" with a hidden trap of each type at col 16 of
    # room A's storey 1 (the 2nd walk step fires it: the trap sequence's ticks),
    # a Wait search (col 20, 8 waits: found w.p. 255/256) and the Mage's sense on a
    # walk tick (col 17, the first step); gated <= CAP like pmix
    **{k: ("knight + 4 monsters + pmix items, a hidden %s trap on the walk" % n, [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, k)
       for k, n in (("tdart", "DART"), ("tgas", "GAS"), ("ttele", "TELEPORT"), ("talarm", "ALARM"))},
    "tsearch": ("knight + 4 monsters + pmix items, a Wait search finds a trap", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], [("FIRE", 3), ("WAIT", 8)], K_KNIGHT, None, "tsearch"),
    "tsense": ("mage + 4 monsters + pmix items, the Mage senses a trap on a walk tick", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_WIZARD, None, "tsense"),
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


# D3-8b: callables f(p) run after the scenario's setup (tests/drip.py injects a
# drip source into PROTO room A to time drip_tick in the loaded scenarios)
EXTRA_SETUP = []


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
        # fx_call (tests/combat.py) runs routines by breakpoint and asserts PC: an ISR
        # breakpoint would steal the stop, so the ISR pair is lifted around the call
        isr_bp = (len(PHASES) + 10, len(PHASES) + 11)
        for b in isr_bp:
            self.z.cmd("set-breakpoint %d" % b)
        try:
            self.casts += fx_cast(self.p)
        finally:
            self.z.cmd("set-breakpoint %d PC=%d" % (isr_bp[0], S["isr"]))
            self.z.cmd("set-breakpoint %d PC=%d" % (isr_bp[1], S["isr.done"]))


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


def lcast_setup(p, placements, k=None, r=3, x=14):
    """"lcast": the hero at x facing left (HP 200), the monsters 60 HP,
    spell k (default Lightning) learned at rank r (ARANK + its RANK_ROWS row,
    as rank_sync), MP 40, its slot selected (no turn)."""
    import combat_tables as CT
    sym, b3 = CT.load()
    k = S["ABL_LIGHTNING"] if k is None else k
    row = sym["ab_rank"] - CT.BASE + (k * 3 + r - 1) * 6
    p.set_ent(0, X=x, PX=x * 8, FLAGS=EF_ACTIVE | 2 | EF_LEFT, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
    p.z.cmd("write-memory %d %s" % (S["RANK_ROWS"] + 6 * k, " ".join(str(b) for b in b3[row:row + 6])))
    p.z.cmd("write-memory %d %d %d" % (S["ARANK"], (r << (2 * k)) & 255, (r << (2 * k)) >> 8))
    p.wb("MP", 40)
    p.wb("MAXMP", 40)
    p.select_slot(k + 1)


ADV_BODIES = ((1, 7, 1), (2, 5, 6), (3, 8, 6), (4, 8, 23))   # (slot, K_*, HP): Bat, Ghost, Slime, Slime


def advcast_setup(p, placements):
    """"advcast": Lightning r2 learned, the hero at x 26 facing right (HP 40,
    as fuzz #208), the 4 slots re-kinded (Bat, Ghost, Slime, Slime) standing on
    the hero's floor with the fuzz HP; flight row cols 0 / 3 / 31 = brick."""
    lcast_setup(p, placements, r=2, x=26)
    p.set_ent(0, FLAGS=EF_ACTIVE | 2, HP=40)
    floor = HERO_Y + p.rb(S["kind_tab"] + S["KT_BH"] + K_WIZARD)
    for slot, kind, hp in ADV_BODIES:
        y = floor - p.rb(S["kind_tab"] + S["KT_BH"] + kind)
        p.set_ent(slot, KIND=kind, Y=y, PY=y * 8, HP=hp, MAXHP=60)
    row = S["ROOM_MAP"] + (HERO_Y + S["PF_ROW_DY"]) * 32
    for c in (0, 3, 31):
        p.wb(row + c, S["T_BRICK"])
    p.settle()


# D3-8e "fzcast" / "fzcast2" (tests/proj3.py P11 mirrors them): the
# caster's x / facing, the Lightning rank, (slot, K_*, HP) re-kinding the
# placements (99 HP: the real cast's own rolls keep all 16 strikes), the
# flight-row brick cols (every other col of the row = air)
FZ = {"fzcast": dict(x=23, left=True, rank=1, brick=(4, 27),
                     bodies=((1, 6, 99), (2, 7, 99), (3, 5, 99), (4, 7, 99))),      # Rat, Bat, Ghost, Bat
      "fzcast2": dict(x=18, left=False, rank=3, brick=(12, 31),
                      bodies=((1, 8, 99), (2, 7, 99), (3, 5, 99), (4, 7, 99)))}     # Slime, Bat, Ghost, Bat


def fzcast_setup(p, placements, key):
    """"fzcast" / "fzcast2": Lightning learned at the FZ rank, the hero at FZ x /
    facing (HP 200), the 4 slots re-kinded at the placements' rows with FZ's
    HP, the flight row = air but FZ's brick cols."""
    fz = FZ[key]
    lcast_setup(p, placements, r=fz["rank"], x=fz["x"])
    if not fz["left"]:
        p.set_ent(0, FLAGS=EF_ACTIVE | 2)
    for slot, kind, hp in fz["bodies"]:
        p.set_ent(slot, KIND=kind, HP=hp, MAXHP=hp)
    row = S["ROOM_MAP"] + (HERO_Y + S["PF_ROW_DY"]) * 32
    for c in range(32):
        p.wb(row + c, S["T_BRICK"] if c in fz["brick"] else S["T_AIR"])
    p.settle()


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


# D3-8d "mkmix": slot -> (ST_FLAGS, ST_T1): FROZEN / CONFUSED / FEAR / ASLEEP
# 15 turns (HOLD = ST_T1 high nibble, MIND = low), the hero CONFUSED 15
MKMIX = {5: (1, 0xF0), 1: (2 << 2, 0x0F), 3: (1 << 2, 0x0F), 4: (2, 0xF0), 0: (2 << 2, 0x0F)}


def mkmix_setup(p):
    for slot, (f, t1) in MKMIX.items():
        p.wb(S["ST_FLAGS"] + slot, f)
        p.wb(S["ST_T1"] + slot, t1)
    p.settle()


PMIX_STEP = int(os.environ.get("BUDGET_PMIX_STEP", "2"))   # 1: 13 adjacent items, 126.65k (T11 report)


def pmix_setup(p):
    """"pmix": FLOOR_LIST entries (room A, storey 1) on every PMIX_STEP-th col of 6..11 and 15..21,
    one bag type each, their glyphs in ROOM_MAP row 16; the skeleton at 1 HP."""
    types = [S[n] for n in ("IT_F_APPLE", "IT_P_HEAL", "IT_S_FEAR", "IT_W_LONG", "IT_A_CHAIN", "IT_C_MIGHT",
                            "IT_F_MEAT")]
    cols = list(range(15, 22, PMIX_STEP)) + list(range(6, 12, PMIX_STEP))
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + i * S["FL_STRIDE"]) == S["FL_EMPTY"]]
    for k, (i, c) in enumerate(zip(free, cols)):
        t = types[k % len(types)]
        p.z.cmd("write-memory %d %d %d %d %d" % (S["FLOOR_LIST"] + i * S["FL_STRIDE"], S["FL_S1"], c, t, 1))
        g = p.rb(S["it_cls"] + (p.rb(S["it_tab"] + t) >> 4))
        p.wb(S["ROOM_MAP"] + 16 * 32 + c, g)
    p.set_ent(5, HP=1)


# 3E-T16: scenario -> (type, col) of the hidden trap (room A storey 1) poked over pmix
TRAPS = {"tdart": (0, 16), "tgas": (1, 16), "ttele": (2, 16), "talarm": (3, 16), "tsearch": (0, 20),
         "tsense": (1, 17)}


def trap_setup(p, key):
    typ, col = TRAPS[key]
    pmix_setup(p)
    room = p.rb("CUR_ROOM")
    p.z.cmd("write-memory %d %s" % (S["TRAP_LIST"], " ".join(
        str(v) for v in [room | S["TRF_S1"], col | (typ << 5)] + [0] * 10 + [1])))


def trap_report(p, key):
    b0, b1 = p.z.read_memory(S["TRAP_LIST"], 2)
    ev = ("fired" if b0 & S["TRF_SPENT"] or (key == "tdart" and b0 & S["TRF_KNOWN"]) else
          "found" if b0 & S["TRF_KNOWN"] else "nothing")
    print(f"[info] {key}: trap {ev} (TR_B0 {b0:#04x}), HP {p.ent(0)['HP']}, room {p.rb('CUR_ROOM')}", flush=True)
    return ev


def umix_setup(p):
    """"umix": HP 5 / 200, FOOD 40, bag Heal x2, Meat x2, Fear x2, Sleep x1, Apple."""
    p.set_ent(0, HP=5, MAXHP=200)
    p.wb("FOOD", 40)
    recs = [("IT_P_HEAL", 2), ("IT_F_MEAT", 2), ("IT_S_FEAR", 2), ("IT_S_SLEEP", 1), ("IT_F_APPLE", 1)]
    flat = [v for n, q in recs for v in (S[n], q, 0)]
    p.z.cmd("write-memory %d %s" % (S["BAG"], " ".join(str(b) for b in flat + [0] * (60 - len(flat)))))
    p.wb(S["P_ENTITIES"] + S["E_POT"], 2)


def run_scenario(h, scen):
    name, placements, keys = scen[:3]
    p = game.T(h)
    p.boot(scen[3] if len(scen) > 3 else K_KNIGHT, freeze=0)
    p.isolate()
    if MUS_POKE:                                  # SND-2 T5: T3's level hook isn't merged yet
        p.wb("MUS_REQ", int(MUS_POKE, 0))
    p.place(0, 12, HERO_Y)
    for slot, x, y, flags in placements:
        p.place(slot, x, y, room=0, flags=flags)
    if DECOR:
        inject_decor(p)
    if len(scen) > 5 and scen[5] in ("lcast", "lcastf", "lcasts"):
        lcast_setup(p, placements)
    if len(scen) > 5 and scen[5] in ("lcastf", "lcasts"):  # FROZEN 1 / ASLEEP (ST_FLAGS kind 1 / 2,
        # ST_T1 high nibble); BUDGET_STF / BUDGET_ST1 override for variants
        stf = os.environ.get("BUDGET_STF", "1" if scen[5] == "lcastf" else "2")
        for slot, *_ in placements:
            p.wb(S["ST_FLAGS"] + slot, int(stf, 0))
            p.wb(S["ST_T1"] + slot, int(os.environ.get("BUDGET_ST1", "0x10"), 0))
    if len(scen) > 5 and scen[5] == "advcast":
        advcast_setup(p, placements)
    if len(scen) > 5 and scen[5] in FZ:
        fzcast_setup(p, placements, scen[5])
    if len(scen) > 5 and scen[5] == "fcast":
        lcast_setup(p, placements, k=S["ABL_FROST"], r=2, x=7)
    if len(scen) > 5 and scen[5] == "wcast":
        wcast_setup(p, placements)
    if len(scen) > 5 and scen[5] == "acast":
        acast_setup(p, placements)
    if len(scen) > 5 and scen[5] == "mkmix":
        mkmix_setup(p)
    if len(scen) > 5 and scen[5] == "pmix":
        pmix_setup(p)
    if len(scen) > 5 and scen[5] == "umix":
        umix_setup(p)
    if len(scen) > 5 and scen[5] in TRAPS:
        trap_setup(p, scen[5])
    for f in EXTRA_SETUP:
        f(p)
    mode = scen[4] if len(scen) > 4 else None
    st = {"fx": FxStepper, "cast": CastStepper}.get(mode, Stepper)(p)
    for _ in range(6):                            # a few unmeasured ticks: the ISR picks MUS_REQ up
        if p.rb("MUS_CUR") == S["MUS_LAMENT"]:
            break
        st._to("tick_work")
        st._to("wait_tick")
    snd, cur = p.rb("SND_MODE"), p.rb("MUS_CUR")
    assert snd == 3 and cur == S["MUS_LAMENT"], (
        f"budget run needs the WZM player active: SND_MODE={snd} (want 3), MUS_CUR={cur} (want"
        f" {S['MUS_LAMENT']}); MUS_REQ={p.rb('MUS_REQ')} (BUDGET_MUS={MUS_POKE!r}: set it to the"
        f" tune id to poke, until the level hook sets MUS_REQ)")
    swing = 0
    for key, n in keys:
        for _ in range(n):
            p.clear_trace()
            st.turn(key)
            swing += S["FID_wizard_staffswing"] in p.trace_fids(0)
    st.close()
    st.trap_ev = trap_report(p, scen[5]) if len(scen) > 5 and scen[5] in TRAPS else None
    if len(scen) > 5 and scen[5] == "umix":         # the uses really happened (bag / FOOD / statuses)
        bag = list(p.z.read_memory(S["BAG"], 15))
        print(f"[info] umix after: bag {bag}, FOOD {p.rb('FOOD')}, HP {p.ent(0)['HP']}, "
              f"ST_FLAGS {list(p.z.read_memory(S['ST_FLAGS'], 6))}", flush=True)
    totals = [t for t, _ in st.ticks]
    worst = max(st.ticks, key=lambda x: x[0])
    work = [t - i for t, i in zip(totals, st.isr_in)]
    pre_max = max(PRE_FLOOR, PRE_BASE + max(st.isr_in))
    real = [t + pre_max for t in totals]
    st.real_over = [r for r in real if r > BUDGET]
    over = [t for t in totals if t > BUDGET]
    casts = [work[i] for i in sorted(st.cast_ix)]          # gated on work (ISR time removed)
    ordinary = [w for i, w in enumerate(work) if i not in st.cast_ix]
    orig_o = [t for i, t in enumerate(totals) if i not in st.cast_ix]
    orig_c = [totals[i] for i in sorted(st.cast_ix)]
    real_o = [t + pre_max for t in orig_o]
    real_c = [t + pre_max for t in orig_c]
    ovc = p.rw("OVERRUN_COUNT")
    print(f"== {name}")
    print(f"ticks measured : {len(totals)}")
    print(f"max tick       : {worst[0]} T  ({worst[0] / BUDGET * 100:.1f}% of {BUDGET})")
    print(f"mean tick      : {sum(totals) // len(totals)} T")
    print(f"worst split    : " + ", ".join(f"{k}={v}" for k, v in worst[1].items()))
    print(f"ticks > budget : {len(over)}")
    print(f"ISR in window  : max {max(st.isr_in)} T, ticks with ISR {sum(1 for i in st.isr_in if i)};"
          f" PRE_MAX {pre_max} (402 + max ISR, floor {PRE_FLOOR})")
    print(f"old total / work / real, max: ordinary {max(orig_o, default=0)} / {max(ordinary, default=0)} /"
          f" {max(real_o, default=0)}; cast {max(orig_c, default=0)} / {max(casts, default=0)} /"
          f" {max(real_c, default=0)}  (real gate <= {BUDGET}: {len(st.real_over)} over)")
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
    st.work_t, st.real_t = work, real
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
        for key in os.environ.get("BUDGET_ONLY", "mix,mage,heavy,lightning,cast,lcast,lcastf,lcasts,advcast,fzcast,fzcast2,fcast,wcast,wcast4,acast,mkmix,pmix,umix,"
                                  "tdart,tgas,ttele,talarm,tsearch,tsense").split(","):
            st, bad = run_scenario(h, SCENARIOS[key])
            if st.real_over and (key in GATED or key in CAP_GATED):
                fails.append(key + " (real)")
                continue
            want_ev = {"tsearch": "found", "tsense": "found"}.get(key, "fired")
            if key in TRAPS and st.trap_ev != want_ev:
                fails.append(key + " (no trap event: %s)" % st.trap_ev)
            if any(t > CAST_CAP for t in st.casts_t):
                fails.append(key + " (cast)")
            elif key in CAST_KEYS and not st.casts_t:
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
