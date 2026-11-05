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
BLAIR-FIX: on a build without ANIM_TRACE (the release) the Mage melee scenarios' STAFF_SWING count
comes from a private -DANIM_TRACE_ON=1 copy run after the timed pass (swing_pass; BUDGET_NO_SWING=1
skips it); the gated T-states are always those of the build under test.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0]] + ["999"]           # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import Harness, S, HAS_TRACE, EMU_ARGS, K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_HOSTILE, EF_LEFT, stand_y  # noqa: E402

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
          "decor_tick", "panel_tick", "panel_done", "dn_gate", "wait_tick"]   # D3-11: dn_gate = the numbers pass
if os.environ.get("GAME_PROFILE"):                # finer split for optimisation work
    PHASES = ["tick_work", "intent_tick", "read_turn_input", "pend_far", "probe_act_fire",
              "try_player_turn", "resolve_monsters",
              "materialise", "anim_tick", "render", "render.nopend", "render.sdone",
              "render.f3done", "render.drdone", "render.nopl", "pmark_dmg", "present",
              "decor_tick", "panel_tick", "panel_done", "dn_gate", "wait_tick"]
    PHASES += [n for n in os.environ["GAME_PROFILE"].split(",") if n in S]


TRACE_SLD = None
if os.environ.get("BUDGET_TRACE"):
    import tick_prof
    TRACE_SLD = tick_prof.load_sld(os.path.join(__import__("game_lib").BUILD_DIR, "tome-of-the-dead.sld"))

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
        self.end_shown = self.p.rb("END_SHOWN") & S["ES_CARD"]
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
        tr = os.environ.get("BUDGET_TRACE")           # PERF-GHOST: instruction profile of tick N
        if tr and len(self.ticks) in [int(x) for x in tr.split(",")]:
            import tick_prof
            ex, inc, cl = tick_prof.trace_tick(self.z, S["wait_tick"], TRACE_SLD, S["PORT_7FFD_SHADOW"])
            prev = int(self.z.cmd("get-tstates-partial"))
            print(f"[trace] tick {len(self.ticks)}: {prev} T\n" + tick_prof.report(ex, inc, cl), flush=True)
            self.ticks.append((prev, {"trace": prev}))
            self.isr_in.append(0)
            return prev
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
        shown = self.p.rb("END_SHOWN") & S["ES_CARD"]
        if shown and not self.end_shown:      # STATS1: the end card's one-time tick (a static screen: the
            self.end_shown = shown            # card + the KILLS / TURNS / BEST KILL rows, ~150k T): reported,
            print(f"[info] end-card tick {prev} T (GS_DEAD / GS_WIN card), not gated", flush=True)
            return                            # not gated, like a transition
        self.end_shown = shown
        if os.environ.get("BUDGET_SPLITS") and prev >= int(os.environ["BUDGET_SPLITS"]):
            print(f"[split] t{len(self.ticks)} {prev} T: " + ", ".join(f"{k}={v}" for k, v in split.items()),
                  flush=True)                   # PERF-GHOST diagnostic: every tick >= the given T
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
# BOSS-RANGED "blair" (D1 lair walk-in, Σ 11): BLAIR-FIX gates it like "mix" (every tick within the
# 2-frame budget, real <= BUDGET). Its worst tick is an input tick (the turn's logic) right after a
# walk step of all 5 bodies (the render redraws every one): 145,564 T total / 152,514 real before,
# 133,624 / 139,995 after (find_target / build_live / box_free / feet_mod / cycle_frame / the blit
# line DJNZ / anim_tick and render bookkeeping / resolve_monsters in bank 2). It stays over the
# 126k cap (work ~130.4k), so it is NOT in CAP_GATED.
GATED = ("mix", "mage", "blair")
CAP_GATED = ("lightning", "cast", "lcast", "lcastf", "lcasts", "advcast", "fzcast", "fzcast2", "fcast", "wcast", "wcast4", "dnum", "dkill", "acast", "mkmix",
             "pmix", "umix", "qmix", "tdart", "tgas", "ttele", "talarm", "tstun", "tfaint", "tsearch", "tsense", "imix", "dmix", "tmix", "rroom", "nroom", "rcast", "sroom", "lglow", "omix", "bsum", "walarm", "walarm2", "vbat", "trickle", "otrickle", "aroom", "asum", "rfar", "sanct", "adeath", "ghost3", "glad")
CAST_KEYS = ("rcast", "cast", "lcast", "lcastf", "lcasts", "advcast", "fzcast", "fzcast2", "fcast", "wcast", "wcast4", "dnum", "dkill", "acast")        # D3-5: worst ordinary tick <= CAP
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
    # D3-11 "dnum": the flying numbers at their busiest: wcast4's Whirlwind r3 on 4 bodies
    # (4 numbers rippling out, <= 3 live, the 4th ends the oldest), the hero POISONED (a -1
    # magenta number every turn start), HP 150 / 200, then a Heal potion (+n green) and a
    # third Whirlwind; dnum_setup / dnum_report (the passes really drew)
    "dnum": ("knight Whirlwind r3 x 2 on 4 bodies, poisoned, a Heal potion, Whirlwind (flying numbers)", [
        (5, 9, stand_y(1, 6), RIGHT),
        (3, 9, stand_y(1, 4), RIGHT),
        (7, 15, stand_y(1, 6), HOSTILE),
        (1, 15, stand_y(1, 2), HOSTILE)], [("FIRE", 2), ("G", 1), ("@2", 1)], K_KNIGHT, None, "dnum"),
    # D3-11 review "dkill": the same 4 bodies at 4 HP, ASLEEP: Whirlwinds r3 kill them all (DEATHs
    # at once, their slots freed ~15 ticks later): every killed body must have shown its -n
    "dkill": ("knight Whirlwind r3 kills 4 bodies at 4 HP (flying numbers: a -n per kill)", [
        (5, 9, stand_y(1, 6), RIGHT),
        (3, 9, stand_y(1, 4), RIGHT),
        (7, 15, stand_y(1, 6), HOSTILE),
        (1, 15, stand_y(1, 2), HOSTILE)], [("FIRE", 4), ("WAIT", 2)], K_KNIGHT, None, "dkill"),
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
    # FLOOR1: "mix" with 4 floor items (16x16 icons) under the fight, storey 1 cols 9 / 13 /
    # 17 / 21 (not picked up: no walk onto them is required; restores under every body)
    "imix": ("knight + 4 monsters, 4 floor items under the fight", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "imix"),
    # FLOOR1 (manager decision 2026-10-28): the kill-drop at 8 item types: "mix" with room A at 8
    # distinct types (the first food / ammo / potion type has 2 entries, one piled on another
    # item) and the 1-HP skeleton as the lair boss: its first-slash kill runs uq_fit (fi_gc, the
    # displacement of every entry of the victim type, each col re-stamped) + drop_put + ap_stamp
    "dmix": ("knight + 4 monsters, a boss kill-drop in a room at 8 item types", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "dmix"),
    # 3E-T12: "mix" with the quick uses as the hero's actions (R6 fx_quick): two potions
    # (HP 5), three eats (the 3rd NO NEED at 100), three reads (Fear, Sleep, Fear over the
    # 4 monsters: room_status), then melee / waits
    "umix": ("knight + 4 monsters, quick potion / food / scroll uses", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)],
        [("G", 2), ("@6", 3), ("@8", 3), ("FIRE", 2), ("WAIT", 2)], K_KNIGHT, None, "umix"),
    # 3F-T6: "pmix" with the 3F tier abilities live (tmix_setup): the 1-slot skeleton is a Skeleton Guard
    # (60 hp: parry 1 in 4 + NOTCH 1 in 2 on a worn weapon), the rat a Black Widow (ACID 1 in 4 on the
    # worn armour), the goblin an Orc Berserker at hp <= half (rage: hit_roll +2); the end_turn tick of a
    # wear event pays the deferred line + hero_recalc + worn cell. The Widow / Berserker bodies have no
    # PROTO frames (their pool kinds are not resident): their draw is skipped, the hooks are measured
    "tmix": ("knight + Guard, Widow, Berserker, bat: parry + NOTCH, ACID, rage over pmix", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "tmix"),
    # IC1: "pmix" with Heal + Mana in the bag, MP 0 and full HP: the quick POTION slot shows
    # Mana until a monster hit makes Heal useful (the pick flips: the slot redraws, a
    # 1st-frame item) + the pickups' quick-slot count redraws (food / potion / scroll)
    "qmix": ("knight + 4 monsters, pmix items, the quick-slot pick / count redraws", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "qmix"),
    # 3E-T16 (review 2026-10-26): "pmix" with a hidden trap of each type at col 16 of
    # room A's storey 1 (the 2nd walk step fires it: the trap sequence's ticks),
    # a Wait search (col 20, 8 waits: found w.p. 255/256) and the Mage's sense on a
    # walk tick (col 17, the first step); gated <= CAP like pmix
    **{k: ("knight + 4 monsters + pmix items, a hidden %s trap on the walk" % n, [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, k)
       for k, n in (("tdart", "DART"), ("tgas", "GAS"), ("ttele", "TELEPORT"), ("talarm", "ALARM"),
                    ("tstun", "STUN"), ("tfaint", "hunger-faint (WEAK, HW_TMR 49: the first turn faints)"))},
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
    # 3F-T7 (game.md §9.2 RANGED-SPEC): "pmix" with the 4 monsters replaced by 2 Skeleton Archers (Σ 12),
    # one on each side of the hero in line (gap 5), counter 0 (both shoot on the first turn, then every 2nd);
    # the bolts start on the release ticks 2 / 3 (slot parity) of every turn they shoot. "nroom": the same
    # with a Necromancer + Bone Caller (DARK bolts, FEAR). "rcast": the Mage's Lightning r3 (lcast) through
    # the 2 Archers, the deferred monster phase shoots back (Lightning track, then 2 bolt tracks). Kinds /
    # KT_SEQ / counters by ranged_setup; bolt frames the PROTO pool lacks are remapped (RANGED_FIDS).
    "rroom": ("knight + 2 Archers in line (Σ12), pmix items, a shot every 2nd turn each", [
        (5, 20, stand_y(1, 6), HOSTILE),
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "rroom"),
    "nroom": ("knight + Necromancer + Bone Caller in line, pmix items, DARK bolts", [
        (5, 20, stand_y(1, 6), HOSTILE),
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "nroom"),
    # 3F-T9: "bsum" = "nroom" with the Bone Caller alone (S = 0, room for a summon): its first in-line turn
    # summons (the cast pose), end_turn's sp_run makes the Ghost (spawn6.asm) on that turn's last tick
    "bsum": ("knight + Bone Caller in line, pmix items, a Ghost summoned at end_turn", [
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "bsum"),
    # 3F-T9 review: "walarm" = an ALARM wave on a generated level, room already holding 2 monsters (Rat + Bat,
    # sigma 4): the queue is poked as tr_eff leaves it (SPQ_WAVE at the doors, 2 bodies) and the LP_KINDS the
    # PROTO rooms lack are 4 Goblins (4 + 3 + 3 = 10 <= 12: both always fit, so the 2-body worst case is
    # deterministic). The first turn's end_turn runs sp_run (2 bodies, door spot, build_live); the later turns
    # materialise them (the trap's own cost is the "talarm" scenario).
    "walarm": ("knight + Rat, Bat; ALARM wave of 2 Goblins queued, sp_run at end_turn, then materialise", [
        (1, 22, stand_y(1, 2), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "walarm"),
    # TRAP2: "walarm2" = a SECOND firing of the same (re-armed, known) ALARM plate: the same wave work with
    # LP_RESPAWNS = 1 (the first wave counted) -> tr_eff gates on / counts LP_RESPAWNS (< RESPAWN_MAX);
    # the wave work (sp_run, 2 bodies) is identical, the cap is the contract (<= CAP).
    "walarm2": ("knight + Rat, Bat; a second ALARM wave (LP_RESPAWNS 1), as walarm", [
        (1, 22, stand_y(1, 2), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "walarm2"),
    # 3F-T12: "trickle" = "pmix" with a respawn-trickle check after EVERY turn (TRK_PHASE re-armed to 47):
    # end_turn only sets TRK_DUE, the check (R6 trk_run) runs on the next INPUT tick (turn_input, alone).
    # Worst case: LVL_DEPTH 5, 8 other VISITED rooms of 3 entries (sigma 8: the full eligibility scan),
    # LP_KINDS Skeleton / Rat alternating and RNG_STATE poked to TRK_SEED once DUE (chance passes, a Skeleton
    # pick fails the cap, the Rat retry spawns: 2 tier rolls) -> a spawn on every check (asserted).
    # "otrickle": the same over "omix" (the Ogre SLAM: the heaviest turn-ending tick, 115.8k).
    "trickle": ("knight + 4 monsters, pmix items, a trickle check at every end_turn", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "trickle"),
    "otrickle": ("knight + Ogre SLAM + goblin + rat + bat, pmix items, a trickle check after every turn", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "otrickle"),
    # 3F-T11b (game.md §9.9): the Archmage in line at gap 5 (slot 7, x 4; hero x 12) with a Mirror Helm hero
    # (DARK X): S = 15 / C = 1 at the start (no summon: a Skeleton beside it would block the line), then a
    # bolt every 2nd turn (Death Bolts: the ½ return hit + the 2nd FX track), hexes / staff between; pmix items
    "aroom": ("knight (Mirror Helm) + the Archmage in line, pmix items: summon, bolts + returns, hexes", [
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "aroom"),
    # 3F-T11b review: "asum" = the Archmage at S 0 / C 1 (no Mirror Helm): turn 1 summons (the decision on the
    # input tick, end_turn's sp_run makes the Skeleton), then the Archmage + the live Skeleton (it walks in and
    # fights; the Archmage bolts / hexes when the line is clear, the staff otherwise)
    # P3: "sanct" = room A as the D8 Sanctum (LVL_SANCTUM 0: the lectern's right-wall geometry, gap = 26 - x),
    # the hero at x 26 facing it: every FIRE a melee Tome hit (far6 tome_geo6 + the line) and every end_turn
    # the aura (far6 + 1 hp); TOME_HP 99 (no win). "adeath" = room A as the D8 lair: a Skeleton = LP_BOSS at
    # 1 hp adjacent, FIRE kills it -> mon_drop -> grate_open -> R6 seal_open on the death tick (asserted)
    "sanct": ("knight in the Sanctum, melee Tome hits + the aura every turn", [], [("FIRE", 6)], K_KNIGHT,
              None, "sanct"),
    "adeath": ("knight kills the D8 boss (seal_open on its death tick) + rat, goblin, bat", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], [("FIRE", 4), ("WAIT", 2)], K_KNIGHT, None, "adeath"),
    "asum": ("knight + the Archmage summoning, then Archmage + its Skeleton, pmix items", [
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "asum"),
    # 3F-T11b review: "rfar" = 2 shooters held OUT of range for the whole run (Archer gap 11 >= r 10 at x 26,
    # Necromancer gap 8 >= r 8 at x 1; the hero only waits): the cheap range reject in rg_line (before the
    # line scans), compared against main
    "rfar": ("knight waiting + Archer and Necromancer out of range, pmix items", [
        (5, 26, stand_y(1, 6), HOSTILE),
        (7, 1, stand_y(1, 6), RIGHT)], [("WAIT", 12)], K_KNIGHT, None, "rfar"),
    "vbat": ("knight + a low-hp Vampire, pmix items, the bat transform at end_turn", [
        (7, 4, stand_y(1, 6), RIGHT)], KEYS, K_KNIGHT, None, "vbat"),
    "rcast": ("mage Lightning r3 through 2 Archers in line, the deferred phase shoots back", [
        (5, 6, stand_y(1, 6), RIGHT),
        (7, 22, stand_y(1, 6), HOSTILE)], [("FIRE", 3)], K_WIZARD, None, "rcast"),
    # 3F-T7 review: 3 Goblin Slingers shooting on one input tick (+ pmix items): one left of the hero, two
    # STACKED on the right (same cols: a forced layout, only so all three have a clear line — a body in the
    # gap blocks, so a real room fires at most 2 per hero storey); slots 1 / 2 / 5: releases on ticks 3 / 2 / 3
    "sroom": ("knight + 3 Slingers (2 stacked) shooting together, pmix items", [
        (1, 5, stand_y(1, 4), RIGHT),
        (2, 19, stand_y(1, 4), HOSTILE),
        (5, 19, stand_y(1, 4), HOSTILE)], KEYS, K_KNIGHT, None, "sroom"),
    # AI-L1 review: 3 climbers jammed at the {23,1} ladder top (storey 0; the hero walks storey 1 below
    # through the pmix items): Skeleton c-2 / Goblin c+1 / Skeleton c+4 = the 3-climber chain (strong,
    # weak, strong), so lq_block (far6, box_free, a back-off try_step) runs for each of them on the
    # same monster phase. Kinds by lqmix_setup (slot 1 the Rat -> a 2nd Skeleton).
    # 3F-T8: room A made the lair (LVL_LAIR 0, LP_BOSS, its RD_EXITCOL = the post), pmix items under the
    # hero's walk. "lglow": the goblin (slot 3, x 25) is the GOLDEN Goblin King standing on its post
    # (RD_EXITCOL 25; the hero stays >= 9 cols away: G2 holds it there), so its glow steps through the
    # attr-only repaint (boss2.asm stamp2) every 2 eligible ticks, some of them right before an input
    # tick; + the skeleton / rat / bat as escort. "omix": the 1-slot skeleton re-kinded to the OGRE
    # (Skeleton sequences: PROTO pools no Ogre frames — the 32-px RAISE / SLAM blit is 1 col
    # narrower here), PROVOKED (always engaged), SLAM counter 2 at the start (a reach-2 SLAM + STUN on
    # the first turn, then every 3rd), goblin + rat + bat, the Knight's slash (KEYS).
    "lglow": ("knight + golden Goblin King stationary on its post + 3, pmix items", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "lglow"),
    # BOSS-RANGED: "blair" = the "lglow" lair with the golden Goblin King IN LINE (x 24, the hero 12..14,
    # nothing between): it walks in, throws a dagger every 3rd turn from gap < 6 (FX track, SFX_THROW), walks in
    # between (RWF_WALK -> ai_guard), then melees; a D1 lair at the encounter cap (King 3 + 1, Goblin 3, Rat 2,
    # Bat 2 = 11 <= 12): rat behind it, bat, slot 5 re-kinded to a plain Goblin left of the hero.
    "blair": ("knight + golden Goblin King daggers in line (gap 9 -> 5) + goblin, rat, bat, pmix items", [
        (3, 24, stand_y(1, 4), HOSTILE),
        (1, 28, stand_y(1, 2), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE),
        (5, 4, stand_y(1, 4), RIGHT)], KEYS, K_KNIGHT, None, "blair"),
    "omix": ("knight + Ogre SLAM (RAISE->SLAM, STUN) + goblin + rat + bat, pmix items", [
        (5, 15, stand_y(1, 6), HOSTILE),
        (1, 22, stand_y(1, 2), HOSTILE),
        (3, 25, stand_y(1, 4), HOSTILE),
        (4, 8, stand_y(1, 2) - 3, HOSTILE)], KEYS, K_KNIGHT, None, "omix"),
    "lqmix": ("knight + pmix items below, 3 climbers jammed at a ladder top (lq_block x3)", [
        (5, 21, stand_y(0, 6), RIGHT),
        (3, 24, stand_y(0, 4), HOSTILE),
        (1, 27, stand_y(0, 6), HOSTILE)], KEYS, K_KNIGHT, None, "lqmix"),
    # PERF-GHOST (T14 finding, docs/t14-playthrough.md: M 0x1234 D3 room 3, 145,471 T): the Mage meleeing
    # 3 awake Ghosts (24x32 flyers, DRAIN touch / CONFUSED) in a line on its storey (box_free keeps flyers
    # apart: bodies placed overlapping jam), then walking away over pmix's bag items while they chase: a
    # pickup turn end (floor_pickup + the line + ap_stamp) with 3 Ghosts flying; kinds / rows / HP by
    # ghost_setup. "ghost3" GATES (<= CAP work, real <= BUDGET); "ghost5" (5 Ghosts, one behind the hero:
    # over the encounter cap) is reported only. The real scene (4 bodies + the hero in a decorated room) is
    # heavier: the gate for it is the playthrough run (docs/memory-map.md "PERF-GHOST ledger").
    "ghost3": ("mage melee vs 3 Ghosts in a line, then a walk away over pmix items (pickups), the Ghosts chasing", [
        (5, 15, stand_y(1, 4), HOSTILE),
        (3, 18, stand_y(1, 4) - 1, HOSTILE),
        (1, 21, stand_y(1, 4), HOSTILE)], KEYS, K_WIZARD, None, "ghost3"),
    "ghost5": ("mage melee vs 5 Ghosts (both sides), then a walk over pmix items (informational)", [
        (5, 15, stand_y(1, 4), HOSTILE),
        (3, 18, stand_y(1, 4) - 1, HOSTILE),
        (1, 21, stand_y(1, 4), HOSTILE),
        (4, 24, stand_y(1, 4) - 1, HOSTILE),
        (2, 3, stand_y(1, 4), RIGHT)], KEYS, K_WIZARD, None, "ghost5"),
    # PERF-GHOST2 (T14 rerun on main b0e299f: M 0x1234 D3 room 3, 149,206 T): the Mage CLIMBING (mid-ladder
    # every turn: each monster's yield test + every try_step ran cork_check over the whole climb path) with a
    # Ghost beside the shaft foot, 2 Ghosts on the storey above and a Bat over the shaft (its columns: the
    # probe path); kinds / rows / HP by glad_setup (GLAD). Gated like ghost3.
    "glad": ("mage climbing (mid-ladder) + Ghost beside it, 2 Ghosts above, a Bat over the shaft", [
        (5, 26, 10, HOSTILE),
        (3, 12, 1, RIGHT),
        (1, 9, 1, RIGHT),
        (4, 22, 0, HOSTILE)], [("K", 6), ("WAIT", 2)], K_WIZARD, None, "glad"),
    "heavy": ("knight + 2 skeletons, goblin, ghost", [
        (5, 15, stand_y(1, 6), HOSTILE),          # skeleton C right, gap 0
        (7, 8, stand_y(1, 6), RIGHT),             # skeleton D left, gap 1
        (3, 20, stand_y(1, 4), HOSTILE),          # goblin
        (6, 4, stand_y(1, 4) - 1, RIGHT)], KEYS),  # ghost, storey-1 band, starts in
                                                  # {5,1}'s end box (legal again: flyers
                                                  # cross shafts, rule 2026-10-02)
}


# B3B-10: the PROTO rooms carry no animated decor (RD_SEED 0), so the
# scenarios get a synthetic FULL ANIM_LIST in room A (4 glyph swaps = the
# deriver's budget maximum since LOOK-1 removed the flame attr cycle, ALL with
# the same stagger so the per-tick caps bind and the deferred steps pile into the following ticks),
# placed in the fight band (storey 1, rows 11-14) and storey 0. BUDGET_DECOR=0
# measures without it.
DECOR = os.environ.get("BUDGET_DECOR", "1") != "0"
DECOR_GLYPH = [(10, 12), (18, 13), (12, 3), (20, 4)]
DECOR_ATTR = []                       # LOOK-1: no attr-cycle entries any more


# D3-8b: callables f(p) run after the scenario's setup (tests/drip.py injects a
# drip source into PROTO room A to time drip_tick in the loaded scenarios)
EXTRA_SETUP = []


def inject_decor(p):
    """Synthetic ANIM_LIST for room A (in ROOM_MAP): glyph cells get the D1
    tall-torch body id 36 in the map and its tip id 40 as the swap partner
    (both non-solid, ids >= 16). Phase 3 = all due on
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
        p.z.cmd("write-memory %d %s" % (S["CAST_ROW"], " ".join(["0"] * 6)))
        super().turn(*keys, **kw)

    def close(self):
        self.z.cmd("set-breakpoint %d" % (len(PHASES) + 1))
        super().close()


def lcast_setup(p, placements, k=None, r=3, x=14):
    """"lcast": the hero at x facing left (HP 200), the monsters 60 HP,
    spell k (default Lightning) learned at rank r (ARANK; abil_load picks the row), MP 40, its slot selected (no turn)."""
    import combat_tables as CT
    sym, b3 = CT.load()
    k = S["ABL_LIGHTNING"] if k is None else k
    p.set_ent(0, X=x, PX=x * 8, FLAGS=EF_ACTIVE | 2 | EF_LEFT, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
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
    Whirlwind learned at rank 3 (ARANK; abil_load picks the row),
    MP 40, the Whirlwind slot selected (no turn)."""
    import combat_tables as CT
    sym, b3 = CT.load()
    a, r = S["ABL_WHIRL"], 3
    k = a - S["ABL_POWER"]
    p.set_ent(0, HP=200, MAXHP=200)
    for slot, *_ in placements:
        p.set_ent(slot, HP=60, MAXHP=60)
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


DNUM = {"pass0": 0, "spawns": 0, "dn": [], "react": {}, "lag": [], "k": 0, "sig": {}, "seen": [],
        "passes": 0, "pass_k": 0}


def dnum_hook(st):
    """D3-11 "dnum" / "dkill" (TICK_HOOKS): the spawns, the passes and the spawn lags.
    A pass = a tick whose DN_PASS moved (the 1st-frame scan; a 2nd-frame tick spawns from
    the queue without one). A spawn = a live record at DL_AGE 1 whose (slot, value, col,
    row, age) differs from the last tick's (a record stays at age 1 over the 2nd-frame
    ticks until the next pass ages it, so age 1 alone over-counts). The lag = ticks from
    the body's reaction start ($80 | rc seen) to its spawn."""
    p = st.p
    DNUM["k"] += 1
    DNUM["dn"].append(st.ticks[-1][1].get("dn_gate", 0))
    DNUM.setdefault("dn2", []).append((st.ticks[-1][1].get("dn_gate", 0), st.ticks[-1][0]))
    ps = p.rb("DN_PASS")
    if ps != DNUM["pass_k"]:
        DNUM["passes"] += 1
        DNUM["pass_k"] = ps
    ents = p.z.read_memory(S["P_ENTITIES"], 16 * S["P_ENT_STRIDE"])
    for sl in range(16):                          # the spawn lag: a reaction started -> its number
        rc = ents[sl * S["P_ENT_STRIDE"] + S["E_REACT"]]
        if rc & 0x80 and sl not in DNUM["react"]:
            DNUM["react"][sl] = DNUM["k"]
    for e in range(S["DN_LIVE_N"]):
        r = p.z.read_memory(S["DN_LIVE"] + e * S["DN_LIVE_STRIDE"], 8)
        sig = (r[S["DL_SLOT"]], r[S["DL_VAL"]], r[S["DL_COL"]], r[S["DL_ROW"]], r[S["DL_AGE"]])
        if sig[0] != 0xFF and sig[4] == 1 and DNUM["sig"].get(e) != sig:
            DNUM["spawns"] += 1
            DNUM["seen"].append((sig[0], "MISS" if sig[1] == S["DNV_MISS"] else sig[1] - 256 if sig[1] > 128 else sig[1]))
            if sig[0] in DNUM["react"]:
                DNUM["lag"].append(DNUM["k"] - DNUM["react"].pop(sig[0]))
        DNUM["sig"][e] = sig
    if os.environ.get("BUDGET_DN2"):              # diagnostic: one line a tick
        g, tot = st.ticks[-1][1].get("dn_gate", 0), st.ticks[-1][0]
        keys = {i: v for i, v in enumerate(p.z.read_memory(S["DN_KEY"], 16)) if v != 0xFF}
        rcs = {sl: ents[sl * S["P_ENT_STRIDE"] + S["E_REACT"]] for sl in (0, 1, 3, 5, 7)}
        print(f"[dn2] k{DNUM['k']} {'F2' if tot - g > 70908 else 'F1'} gate {g} tot {tot} fx {p.rb('FX_BUSY')}"
              f" keys {keys} react {rcs} spawns {DNUM['spawns']}", flush=True)


def mkmix_setup(p):
    for slot, (f, t1) in MKMIX.items():
        p.wb(S["ST_FLAGS"] + slot, f)
        p.wb(S["ST_T1"] + slot, t1)
    p.settle()


PMIX_STEP = int(os.environ.get("BUDGET_PMIX_STEP", "2"))   # >= 2 (FLOOR1: 2-col footprints)


def pmix_setup(p):
    """"pmix": FLOOR_LIST entries (room A, storey 1) on every PMIX_STEP-th col of 6..11 and 15..21,
    one bag type each, FLOOR1: T_ITEM on their 2x2 cells (PMIX_STEP >= 2: footprints c..c+1
    touch, never overlap) + the glyph cache / icons (fi_refresh); the skeleton at 1 HP."""
    types = [S[n] for n in ("IT_F_APPLE", "IT_P_HEAL", "IT_S_FEAR", "IT_W_LONG", "IT_A_CHAIN", "IT_C_MIGHT",
                            "IT_F_MEAT")]
    cols = list(range(15, 22, PMIX_STEP)) + list(range(6, 12, PMIX_STEP))
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + i * S["FL_STRIDE"]) == S["FL_EMPTY"]]
    for k, (i, c) in enumerate(zip(free, cols)):
        t = types[k % len(types)]
        p.put_item(i, S["FL_S1"], c, t)           # FLOOR1: T_ITEM 2x2 (rows 15..16, cols c..c+1)
    p.fi_refresh()                                # the glyph cache + the icons on screen
    p.set_ent(5, HP=1)


def ghost_setup(p, placements):
    """PERF-GHOST "ghost3" / "ghost5": the placements re-kinded to Ghosts (HP 60, standing on the hero's
    floor), the hero HP 250 (the DRAIN touches), pmix's bag items under the walk (without its 1-HP kill)."""
    floor = HERO_Y + p.rb(S["kind_tab"] + S["KT_BH"] + K_WIZARD)
    y = floor - p.rb(S["kind_tab"] + S["KT_BH"] + S["K_GHOST"])
    for slot, x, y0, _ in placements:
        yy = y - (stand_y(1, 4) - y0)             # a placement 1 row up flies 1 row up
        p.set_ent(slot, KIND=S["K_GHOST"], Y=yy, PY=yy * 8, HP=60, MAXHP=60)
    p.set_ent(0, HP=250, MAXHP=250, FLAGS=EF_ACTIVE | 2)   # facing the Ghosts (right)
    hp5 = p.ent(5)["HP"]
    pmix_setup(p)
    p.set_ent(5, HP=hp5)
    p.settle()


GLAD = {5: "K_GHOST", 3: "K_GHOST", 1: "K_GHOST", 4: "K_BAT"}


def glad_setup(p, placements):
    """PERF-GHOST2 "glad": the hero at the col-23 shaft foot (storey 1, x 23: K climbs to storey 0, mid-ladder
    every turn), the placements re-kinded (GLAD) at their raw rows, HP 60; the hero HP 250."""
    p.set_ent(0, X=23, PX=23 * 8, HP=250, MAXHP=250)
    for slot, x, y, _ in placements:
        p.set_ent(slot, KIND=S[GLAD[slot]], Y=y, PY=y * 8, HP=60, MAXHP=60)
    p.settle()


TRK = {"on": False, "checks": 0, "spawns": 0, "rec": []}
TRK_SEED = 6                                      # RNG_STATE: draw 1 < 96, draw 3 even (a Skeleton first)


def trickle_arm(p):
    p.wb("TRK_PHASE", S["RESPAWN_PERIOD"] - 1)
    p.wb("LP_RESPAWNS", 0)
    p.wmem(S["LP_REC"], TRK["rec"])


def trickle_setup(p, key="trickle"):
    """"trickle" / "otrickle" (3F-T12): pmix / omix + the trickle state (see the scenario comment)."""
    if key == "otrickle":
        boss_setup(p, "omix")                     # room A = the lair (excluded anyway: CUR_ROOM)
    else:
        pmix_setup(p)
    sk, rat, gob = S["K_SKELETON"], S["K_RAT"], S["K_GOBLIN"]
    p.wb("LVL_DEPTH", 5)
    p.wmem(S["LP_KINDS"], [sk, rat, sk, rat])
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_GRATE_OPEN"] & 255)
    if key == "trickle":
        p.wb("LVL_LAIR", S["ROOM_NONE"])
    p.wb("LVL_SANCTUM", S["ROOM_NONE"])
    cur = p.rb("CUR_ROOM")
    p.wb("TRK_PREV", cur)
    rec = []
    for r in range(9):
        rec += [0x80] + [0] * 8 if r == cur else [0x83, gob, 9, gob, 9, rat, 7, 0, 0]
    TRK["rec"] = rec
    trickle_arm(p)
    TRK.update(on=True, checks=0, spawns=0, tick=0)


def trickle_hook(st):
    if TRK["on"] and st.p.rb("TRK_PHASE") == S["TRK_DUE"]:   # end_turn counted the 48th turn
        assert st.p.rb("LP_RESPAWNS") == 0, "trickle ran on the turn-ending tick"
        st.p.wmem(S["RNG_STATE"], [TRK_SEED, 0])
    elif TRK["on"] and st.p.rb("TRK_PHASE") == 0:    # the next INPUT tick ran the check
        TRK["checks"] += 1
        TRK["tick"] = max(TRK.get("tick", 0), st.ticks[-1][0])
        TRK["spawns"] += st.p.rb("LP_RESPAWNS")
        trickle_arm(st.p)


TICK_HOOKS.append(trickle_hook)


TMIX_SEED = int(os.environ.get("BUDGET_TMIX_SEED", "0"), 0)


def tmix_setup(p):
    """"tmix" (3F-T6): pmix + the tier abilities (see the scenario comment)."""
    pmix_setup(p)
    p.set_ent(5, KIND=S["K_SKEL_GUARD"], HP=60, MAXHP=60)
    p.set_ent(1, KIND=S["K_BLACK_WIDOW"], HP=60, MAXHP=60)
    p.set_ent(3, KIND=S["K_ORC_BERSERK"], HP=9, MAXHP=20)
    # 3F-T13bc (manager-accepted 2026-10-29): PROTO has no Orc frames, so the fixture clears the
    # Berserker's KF_CLIMBER. The Berserker climbs now (KF_CLIMBER), but rooms A-D pool no Orc frames: its block is
    # not cached, so it animates with the HERO's sequence row (Knight climb / walk frames, 40 px) — a
    # stand-in this scenario never meant to measure (it measures the tier hooks). Keep it walking as in
    # 3F-T6 (main's figures); real climbers on their own frames: tests/climb3f.py + the D7 "cmix" note
    # in docs/memory-map.md "ART2 / ART3 / ART4 wiring".
    kf = S["kind_tab"] + S["KT_FLAGS"] + S["K_ORC_BERSERK"]
    p.wb(kf, p.rb(kf) & ~S["KF_CLIMBER"])
    p.set_ent(0, HP=250, MAXHP=250)               # the run must outlast the Widow / Berserker bites
    # the deferred half of a wear event is forced onto the first end_turn (the random 1-in-N rolls would
    # rarely land in a 14-turn run): WEAR_PEND = the armour ACID line -> hunger_turn's wear_apply (line +
    # hero_recalc + worn cell) runs once, in the worst case alongside the pickups / kill of pmix
    p.wb("WEAR_PEND", S["TX_CMB_ACID_ARM"])
    if TMIX_SEED:
        p.wmem(S["RNG_STATE"], [TMIX_SEED & 255, TMIX_SEED >> 8])


RANGED_FIDS = {}                                  # filled per run: non-resident bolt fid -> resident stand-in


def ranged_fids(st):
    """TICK_HOOK (3F-T7 scenarios): queued RS_Q bolt descriptors (not yet started) get frames the PROTO
    pool holds, so their FX draw is measured instead of skipped (BLIT_MISS)."""
    p = st.p
    if not RANGED_FIDS or not p.rb("TURN_PEND") & S["TP_SHOT"]:
        return
    end = (S["RS_Q"] & ~255) | p.rb("RS_P")
    for a in range(S["RS_Q"], end, S["RS_STRIDE"]):
        if p.rb(a) == 255:
            continue
        d = list(p.z.read_memory(a + 2, 4))
        nd = [RANGED_FIDS.get(f, f) for f in d]
        if nd != d:
            p.wmem(a + 2, nd)


def ranged_setup(p, placements, key):
    """"rroom" / "nroom" / "rcast" (3F-T7): the 2 slots re-kinded to shooters, drawn with the Skeleton's
    sequences (KT_SEQ poke: Archer / Necro frames are not in the PROTO pool), counter 0 (E_RCD = 1), 60 HP."""
    kinds = {"rroom": ("K_ARCHER", "K_ARCHER"), "nroom": ("K_NECRO", "K_BONE_CALLER"),
             "rcast": ("K_ARCHER", "K_ARCHER"), "sroom": ("K_SLINGER",) * 3, "bsum": ("K_BONE_CALLER",),
             "vbat": ("K_VAMPIRE",), "aroom": ("K_ARCHMAGE",), "asum": ("K_ARCHMAGE",),
             "rfar": ("K_ARCHER", "K_NECRO")}[key]
    if key == "rcast":
        lcast_setup(p, placements)
    else:
        pmix_setup(p)
    sk = p.rb(S["kind_tab"] + S["KT_SEQ"] + S["K_GOBLIN" if key == "sroom" else "K_SKELETON"])
    for (slot, *_), kn in zip(placements, kinds):
        p.wb(S["kind_tab"] + S["KT_SEQ"] + S[kn], sk)
        p.set_ent(slot, KIND=S[kn], HP=60, MAXHP=60, POT=1)
    p.set_ent(0, HP=250, MAXHP=250)               # the run must outlast every shot (nroom: 1d6+1 a hit)
    RANGED_FIDS.clear()
    if key == "rcast":                            # the Mage's PROTO pool: no arrows
        RANGED_FIDS.update({S["FID_arrow_fly1"]: S["FID_firebolt_fly1"], S["FID_arrow_fly2"]: S["FID_firebolt_fly2"],
                            S["FID_arrow_hit"]: S["FID_firebolt_burst1"]})
    if key == "vbat":                             # the bat form draws the PROTO Bat's sequences
        p.wb(S["kind_tab"] + S["KT_SEQ"] + S["K_VBAT"], p.rb(S["kind_tab"] + S["KT_SEQ"] + S["K_BAT"]))
        p.set_ent(placements[0][0], HP=4, MAXHP=14, POT=0)
        p.wb(S["LP_KINDS"], S["K_VAMPIRE"])
    if key == "aroom":                            # 3F-T11b: the Mirror Helm (DARK X), POT 0: S 0 / C 1
        p.set_ent(placements[0][0], HP=67, MAXHP=67, POT=0x3C)   # S 15: no summon (it would stand in the line;
                                                                  # the summon decision + sp_run: "bsum")
        p.wmem(S["HERO_RES"], [0, 3 << 2, 0])
        p.wb(S["ST_X"] + placements[0][0], 0)
    if key == "rfar":                             # bricks on the standing row 16 at cols 25 / 4: neither can
        for c_ in (25, 4):                        # step in (the flight row 13 stays clear)
            p.wb(S["ROOM_MAP"] + 16 * 32 + c_, S["T_BRICK"])
    if key == "asum":                             # S 0 / C 1: the first turn summons
        p.set_ent(placements[0][0], HP=67, MAXHP=67, POT=0)
        p.wb(S["ST_X"] + placements[0][0], 0)
        p.wb("SPQ_K", 0)
    if key in ("nroom", "bsum", "aroom", "asum", "rfar"):   # no Necro bolt in the PROTO pool
        RANGED_FIDS.update({S["FID_nbolt_fly1"]: S["FID_arrow_fly1"], S["FID_nbolt_fly2"]: S["FID_arrow_fly2"],
                            S["FID_nbolt_hit"]: S["FID_arrow_hit"]})
    if ranged_fids not in TICK_HOOKS:
        TICK_HOOKS.append(ranged_fids)
    p.settle()


def lqmix_setup(p):
    """"lqmix" (AI-L1): pmix items + slot 1 re-kinded to a Skeleton (60 HP each, so nothing dies)."""
    pmix_setup(p)
    p.set_ent(1, KIND=S["K_SKELETON"])
    for sl in (1, 3, 5):
        p.set_ent(sl, HP=60, MAXHP=60)
    p.set_ent(0, HP=250, MAXHP=250)
    if os.environ.get("BUDGET_LQ_X"):             # control run: other storey-0 cols (e.g. no jam)
        for sl, x in zip((5, 3, 1), map(int, os.environ["BUDGET_LQ_X"].split(","))):
            p.set_ent(sl, X=x, PX=8 * x)
    p.settle()


def imix_setup(p):
    """"imix" (FLOOR1): 4 floor items (Apple, Heal, Long Sword, Chain) in room A storey 1
    at cols 9 / 13 / 17 / 21, cache + icons drawn (fi_refresh)."""
    types = [S[n] for n in ("IT_F_APPLE", "IT_P_HEAL", "IT_W_LONG", "IT_A_CHAIN")]
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + i * S["FL_STRIDE"]) == S["FL_EMPTY"]]
    for i, c, t in zip(free, (9, 13, 17, 21), types):
        p.put_item(i, S["FL_S1"], c, t)
    p.fi_refresh()


def dmix_setup(p):
    """"dmix" (FLOOR1): room A at exactly 8 distinct item types (the PROTO items + these), the victim
    type = the first food / ammo / potion in list order (the PROTO potion), the 1-HP
    skeleton the lair boss (LF_UNIQUE clear, depth 1: King's Helm), cache + icons drawn."""
    room = p.rb("CUR_ROOM")
    fl = lambda: list(p.z.read_memory(S["FLOOR_LIST"], 128))                   # noqa: E731
    have = {fl()[4 * i + 2] for i in range(S["FLOOR_MAX"])
            if fl()[4 * i] != S["FL_EMPTY"] and fl()[4 * i] & S["FL_ROOM_MASK"] == room}
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + i * S["FL_STRIDE"]) == S["FL_EMPTY"]]
    names = ["IT_A_CHAIN", "IT_W_LONG", "IT_C_MIGHT", "IT_S_FEAR", "IT_BOOK", "IT_H_HOOD", "IT_S_SLEEP"]
    spots = [(S["FL_S1"], 6, "IT_A_CHAIN"), (S["FL_S1"], 6, "IT_F_APPLE"), (S["FL_S1"], 9, "IT_F_APPLE")]   # (clear of the hero's walk)
    spots += [(room, c, n) for c, n in zip((6, 12, 18, 24), names[1:])]
    spots = spots[:int(os.environ.get("BUDGET_DMIX_SPOTS", "99"))]       # (info: fewer = no displacement)
    types = {S[n] for _, _, n in spots}
    k = 0
    while len(have | types) < int(os.environ.get("BUDGET_DMIX_TYPES", "8")):                  # (the PROTO room already holds some)
        spots.append((room, 28 - 3 * k, names[k + 4 if k + 4 < len(names) else 0]))
        types.add(S[spots[-1][2]])
        k += 1
    for i, (rb, c, n) in zip(free, spots):
        p.put_item(i, rb | (room if rb == S["FL_S1"] else 0), c, S[n])
    p.fi_refresh()
    p.wb("LVL_LAIR", room)
    p.wb("LP_BOSS", p.ent(5)["KIND"])
    p.wb("LVL_DEPTH", 1)
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_UNIQUE"] & 0xFF)
    p.set_ent(5, HP=1)
    p.wmem(S["RNG_STATE"], [DMIX_SEED & 255, DMIX_SEED >> 8])   # a seed whose first slash hits (the kill is the point)


DMIX_SEED = int(os.environ.get("BUDGET_DMIX_SEED", "8"))


# 3E-T16: scenario -> (type, col) of the hidden trap (room A storey 1) poked over pmix
TRAPS = {"tdart": (0, 16), "tgas": (1, 16), "ttele": (2, 16), "talarm": (3, 16), "tstun": (4, 16),
         "tfaint": (None, 0), "tsearch": (0, 20), "tsense": (1, 17)}


def trap_setup(p, key):
    typ, col = TRAPS[key]
    pmix_setup(p)
    if typ is None:                               # STATUS1 "tfaint": a WEAK hero whose first turn is the 50th
        p.wb("FOOD", 5)
        p.wb("HSTAGE", S["HS_WEAK"])
        p.wb("HW_TMR", S["HW_REPEAT"] - 1)
        p.wb("ST_FLAGS", S["STS_HWEAK"])
        return
    room = p.rb("CUR_ROOM")
    p.z.cmd("write-memory %d %s" % (S["TRAP_LIST"], " ".join(
        str(v) for v in [room | S["TRF_S1"], col | (typ << 5)] + [0] * 10 + [1])))


def trap_report(p, key):
    if key == "tfaint":                           # HW_TMR left 49: the faint was deferred / never ran
        ev = "fired" if p.rb("HW_TMR") != S["HW_REPEAT"] - 1 else "nothing"
        print(f"[info] tfaint: {ev} (HW_TMR {p.rb('HW_TMR')}, FOOD {p.rb('FOOD')}, HSTAGE {p.rb('HSTAGE')}, "
              f"ST_FLAGS {p.rb('ST_FLAGS'):#04x}, EXIT_KIND {p.rb('EXIT_KIND')}, hero Y {p.ent(0)['Y']}, "
              f"turns {p.rw('TURN_COUNTER')}), HP {p.ent(0)['HP']}", flush=True)
        return ev
    b0, b1 = p.z.read_memory(S["TRAP_LIST"], 2)
    # TRAP2: every trap is known after a fire too (no SPENT bit): the scenario says which event was meant
    ev = (("found" if key in ("tsearch", "tsense") else "fired") if b0 & S["TRF_KNOWN"] else "nothing")
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


def qmix_setup(p):
    """"qmix" (IC1): pmix + bag Heal x1, Mana x2, Fear x1, Carrot x1 (QS_CACHE / E_POT as pot_sync
    leaves them), MP 0, full HP; the 3 quick slots marked undrawn."""
    pmix_setup(p)
    recs = [("IT_P_HEAL", 1), ("IT_P_MANA", 2), ("IT_S_FEAR", 1), ("IT_F_CARROT", 1)]
    flat = [v for n, q in recs for v in (S[n], q, 0)]
    p.z.cmd("write-memory %d %s" % (S["BAG"], " ".join(str(b) for b in flat + [0] * (60 - len(flat)))))
    p.wmem(S["QS_CACHE"], [1, 3, 1])                  # food QTY, potions present (Heal | Mana), scroll QTY
    p.wb(S["P_ENTITIES"] + S["E_POT"], 3)
    p.wb("MP", 0)
    e = p.ent(0)
    p.set_ent(0, HP=e["MAXHP"])
    p.wmem(S["ICON_SH"] + S["QS_SLOT0"], [0xFF] * 3)


def boss_setup(p, key):
    """"lglow" / "omix" (3F-T8): room A (PROTO 0) becomes the lair (see the scenario comment)."""
    pmix_setup(p)
    p.wb("LVL_LAIR", 0)
    p.wb(S["ROOM_DESC"] + S["RD_EXITCOL"], 25)       # the post (only ai_guard reads it here)
    if key == "blair" and os.environ.get("BUDGET_BLAIR_NOSHOT"):  # control run: the King never shoots
        p.wb(S["rk_tab"] + S["K_GOBLIN"], 0)
    if key in ("lglow", "blair"):
        p.wb("LP_BOSS", S["K_GOBLIN"] | S["LEK_GOLD"])
        p.wb(S["P_ENTITIES"] + 3 * S["P_ENT_STRIDE"] + S["E_GOLD"], S["LEK_GOLD"])
        p.set_ent(3, HP=60, MAXHP=60)
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_PROVOKED"] & 255)
        if key == "blair":
            p.set_ent(5, KIND=S["K_GOBLIN"], HP=20, MAXHP=20)
    else:
        sk = p.rb(S["kind_tab"] + S["KT_SEQ"] + S["K_SKELETON"])
        p.wb(S["kind_tab"] + S["KT_SEQ"] + S["K_OGRE"], sk)
        p.wb("LP_BOSS", S["K_OGRE"])
        p.set_ent(5, KIND=S["K_OGRE"], HP=60, MAXHP=60, POT=2)     # POT = E_RCD: SLAM counter 2
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | S["LF_PROVOKED"])
    p.set_ent(0, HP=250, MAXHP=250)


WALARM_PRE = []                                   # "walarm": the slots live before the wave


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
    if len(scen) > 5 and scen[5] in ("wcast", "dnum", "dkill"):
        wcast_setup(p, placements)
    if len(scen) > 5 and scen[5] in ("dnum", "dkill"):
        if scen[5] == "dnum":
            p.set_ent(0, HP=150)
            p.wb(S["ST_X"], 30)                   # POISONED 30 turns (POIS1: ST_X slot 0)
        else:
            for slot, *_ in placements:
                p.set_ent(slot, HP=4)             # one Whirlwind r3 blow kills: ASLEEP (STS_HOLD:
                p.wb(S["ST_FLAGS"] + slot, 2)     # eva 0, every blow lands), 15 turns
                p.wb(S["ST_T1"] + slot, 0xF0)
        DNUM.update(pass0=p.rb("DN_PASS"), pass_k=p.rb("DN_PASS"), spawns=0, passes=0, k=0, dn=[], dn2=[],
                    react={}, lag=[], sig={}, seen=[])
        TICK_HOOKS.append(dnum_hook)
    if len(scen) > 5 and scen[5] == "acast":
        acast_setup(p, placements)
    if len(scen) > 5 and scen[5] == "mkmix":
        mkmix_setup(p)
    if len(scen) > 5 and scen[5] == "pmix":
        pmix_setup(p)
    if len(scen) > 5 and scen[5] == "tmix":
        tmix_setup(p)
    if len(scen) > 5 and scen[5] in ("ghost3", "ghost5"):
        ghost_setup(p, placements)
    if len(scen) > 5 and scen[5] == "glad":
        glad_setup(p, placements)
    if len(scen) > 5 and scen[5] in ("trickle", "otrickle"):
        trickle_setup(p, scen[5])
    if len(scen) > 5 and scen[5] in ("rroom", "nroom", "rcast", "sroom", "bsum", "vbat", "aroom", "asum", "rfar"):
        ranged_setup(p, placements, scen[5])
    else:
        RANGED_FIDS.clear()
    if len(scen) > 5 and scen[5] == "imix":
        imix_setup(p)
    if len(scen) > 5 and scen[5] == "lqmix":
        lqmix_setup(p)
    if len(scen) > 5 and scen[5] in ("lglow", "blair", "omix"):
        boss_setup(p, scen[5])
    if len(scen) > 5 and scen[5] == "dmix":
        dmix_setup(p)
    if len(scen) > 5 and scen[5] == "umix":
        umix_setup(p)
    if len(scen) > 5 and scen[5] == "qmix":
        qmix_setup(p)
    if len(scen) > 5 and scen[5] in TRAPS:
        trap_setup(p, scen[5])
    if len(scen) > 5 and scen[5] in ("walarm", "walarm2"):
        WALARM_PRE[:] = [sl for sl in range(1, 16) if p.ent(sl)["FLAGS"] & 1]
        p.wmem(S["LP_KINDS"], [S["K_GOBLIN"]] * 4)
        p.wmem(S["SPQ_K"], [S["SPQ_WAVE"], S["SPQ_NONE"], 2])
        if scen[5] == "walarm2":
            p.wb("LP_RESPAWNS", 1)
    if len(scen) > 5 and scen[5] == "sanct":
        p.wb("LVL_SANCTUM", 0)
        p.wb("TOME_HP", 99)
        p.place(0, 26, HERO_Y)
        p.set_ent(0, HP=250, MAXHP=250)
    if len(scen) > 5 and scen[5] == "adeath":
        p.wb("LVL_DEPTH", 8)
        p.wb("LVL_LAIR", 0)
        p.wb("LP_BOSS", S["K_SKELETON"])
        p.wb("LVL_FLAGS", 0)
        p.set_ent(5, HP=1)
        p.set_ent(0, HP=250, MAXHP=250)
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
    blog = []                                     # "blair": per turn (gap at the start, King MSG, POT)
    for key, n in keys:
        for _ in range(n):
            if HAS_TRACE:                         # RECLAIM-C2: release builds have no trace
                p.clear_trace()
            if len(scen) > 5 and scen[5] == "blair":
                g0 = p.ent(3)["X"] - (p.ent(0)["X"] + 3)
                p.wb(S["P_ENTITIES"] + 3 * S["P_ENT_STRIDE"] + S["E_MSG"], 0)
            st.turn(key)
            if len(scen) > 5 and scen[5] == "blair":
                blog.append((g0, p.rb(S["P_ENTITIES"] + 3 * S["P_ENT_STRIDE"] + S["E_MSG"]), p.ent(3)["POT"] & 3))   # POT & 3 = counter ^ 1
            if HAS_TRACE:
                swing += S["FID_wizard_staffswing"] in p.trace_fids(0)
    st.close()
    if dnum_hook in TICK_HOOKS:
        TICK_HOOKS.remove(dnum_hook)
        print(f"[info] {scen[5]} after: {DNUM['passes']} passes in {DNUM['k']} ticks, {DNUM['spawns']} spawns "
              f"{DNUM['seen']}, worst dn_gate {sorted(DNUM['dn'])[-8:]} T, spawn lags after the reaction start "
              f"{DNUM['lag']} ticks, hero HP {p.ent(0)['HP']}, bodies HP "
              f"{[p.ent(sl)['HP'] for sl, *_ in placements]}", flush=True)
        assert DNUM["spawns"] >= 4 and DNUM["passes"] >= 1, "dnum: too few numbers spawned / no pass"
        if os.environ.get("BUDGET_DN2"):          # diagnostic: the 2nd-frame ticks' dn_gate share
            print("[info] dn_gate in ticks > 1 frame (gate, total):",
                  sorted(x for x in DNUM["dn2"] if x[1] - x[0] > 70908)[-10:], flush=True)
        if scen[5] == "dkill":                    # every kill showed its -n
            dead = [sl for sl, *_ in placements if p.ent(sl)["HP"] == 0]
            hit = {sl for sl, v in DNUM["seen"] if v != "MISS" and v < 0}
            assert len(dead) == len(placements), f"dkill: not every body died: {dead}"
            assert set(dead) <= hit, f"dkill: kills with no -n: {sorted(set(dead) - hit)}"
        st.dnum_lag = list(DNUM["lag"])
    st.trap_ev = trap_report(p, scen[5]) if len(scen) > 5 and scen[5] in TRAPS else None
    if len(scen) > 5 and scen[5] == "umix":         # the uses really happened (bag / FOOD / statuses)
        bag = list(p.z.read_memory(S["BAG"], 15))
        print(f"[info] umix after: bag {bag}, FOOD {p.rb('FOOD')}, HP {p.ent(0)['HP']}, "
              f"ST_FLAGS {list(p.z.read_memory(S['ST_FLAGS'], 6))}", flush=True)
    if len(scen) > 5 and scen[5] == "tmix":         # the tier abilities really ran
        print(f"[info] tmix after: WORN {list(p.z.read_memory(S['WORN'], 9))}, WEAR_PEND {p.rb('WEAR_PEND')},"
              f" HP {p.ent(0)['HP']}/{p.ent(0)['MAXHP']}, Guard HP {p.ent(5)['HP']}", flush=True)
    if len(scen) > 5 and scen[5] in ("rroom", "nroom", "rcast", "sroom", "bsum", "vbat", "aroom", "asum", "rfar"):
        print(f"[info] {scen[5]} after: hero HP {p.ent(0)['HP']}, shooters HP "
              f"{[p.ent(sl)['HP'] for sl, *_ in placements]}, BLIT_MISS {p.rb('BLIT_MISS')}", flush=True)
    if len(scen) > 5 and scen[5] == "aroom":        # 3F-T11b: the bolts + the Mirror Helm returns really happened
        print(f"[info] aroom after: Archmage HP {p.ent(7)['HP']} / 67, state {p.rb(S['ST_X'] + 7):#04x}", flush=True)
        assert p.ent(7)["HP"] < 67, "aroom: no Mirror Helm return"
    if len(scen) > 5 and scen[5] == "asum":         # 3F-T11b: the Archmage's summon really happened
        sm = [sl for sl in range(1, 16) if p.ent(sl)["FLAGS"] & 1 and p.ent(sl)["POT"] & 0x40]
        print(f"[info] asum after: summon-made slots {sm}, Archmage HP {p.ent(7)['HP']}", flush=True)
        assert sm or any(p.ent(sl)["KIND"] == S["K_SKELETON"] and p.ent(sl)["FLAGS"] & 0x10 for sl in range(1, 16)), \
            "asum: no summon was made"
    if len(scen) > 5 and scen[5] == "bsum":         # 3F-T9: the summon really happened
        sm = [sl for sl in range(1, 16) if p.ent(sl)["FLAGS"] & 1 and p.ent(sl)["POT"] & 0x40]
        print(f"[info] bsum after: summon-made slots {sm}", flush=True)
        assert sm, "bsum: no summon was made"
    if len(scen) > 5 and scen[5] in ("trickle", "otrickle"):   # 3F-T12: the checks really ran
        TRK["on"] = False
        print(f"[info] {scen[5]} after: {TRK['checks']} checks, {TRK['spawns']} record appends, worst check tick {TRK['tick']} T", flush=True)
        assert TRK["checks"] >= 6 and TRK["spawns"] == TRK["checks"], "trickle: a check did not spawn"
    if len(scen) > 5 and scen[5] in ("walarm", "walarm2"):       # the wave really was made (2 new bodies, SPQ empty)
        wv = [sl for sl in range(1, 16) if p.ent(sl)["FLAGS"] & 1 and sl not in WALARM_PRE]
        print(f"[info] walarm after: wave slots {wv}, SPQ_K {p.rb('SPQ_K')}", flush=True)
        assert len(wv) == 2 and p.rb("SPQ_K") == 0, "walarm: the 2-body wave was not made"
    if len(scen) > 5 and scen[5] == "blair":        # BOSS-RANGED: the daggers really flew (a hit / miss line at gap >= 2)
        darts = sum(1 for g0, m_, c_ in blog if c_ == 3 and m_ in (S["MSG_M_HIT"], S["MSG_M_MISS"]))
        print(f"[info] blair after: {darts} dagger turns; per turn (gap, MSG, counter) {blog}", flush=True)
        assert darts or os.environ.get("BUDGET_BLAIR_NOSHOT"), "blair: the King never threw"
    if len(scen) > 5 and scen[5] == "sanct":        # P3: the Tome really took the hits, the aura the hp
        print(f"[info] sanct after: TOME_HP {p.rb('TOME_HP')}, hero HP {p.ent(0)['HP']}", flush=True)
        assert p.rb("TOME_HP") < 99 and p.ent(0)["HP"] < 250, "sanct: no Tome hit / no aura"
    if len(scen) > 5 and scen[5] == "adeath":       # P3: the seal really broke on the boss's death
        print(f"[info] adeath after: LVL_FLAGS {p.rb('LVL_FLAGS'):#04x}, EDGE 4/5 {p.rb(S['EDGE_TAB'] + 4):#04x}",
              flush=True)
        assert p.rb("LVL_FLAGS") & S["LF_SEAL_OPEN"], "adeath: the seal did not break"
    if len(scen) > 5 and scen[5] == "vbat":         # 3F-T9: the transform really happened (RCD_ONCE)
        e = p.ent(placements[0][0])
        print(f"[info] vbat after: kind {e['KIND']}, E_RCD {e['POT']:#04x}, HP {e['HP']}", flush=True)
        assert e["POT"] & 0x80, "vbat: the Vampire never turned into a bat"
    if len(scen) > 5 and scen[5] == "dmix":         # the boss kill-drop really ran uq_fit's displacement
        fl = list(p.z.read_memory(S["FLOOR_LIST"], 128))
        room = [(fl[4 * i + 1], fl[4 * i + 2]) for i in range(S["FLOOR_MAX"])
                if fl[4 * i] != S["FL_EMPTY"] and fl[4 * i] & S["FL_ROOM_MASK"] == p.rb("CUR_ROOM")]
        assert p.rb("LVL_FLAGS") & S["LF_UNIQUE"] and S["IT_POTION"] not in [t for _, t in room], \
            f"dmix: the boss kill-drop did not displace (BUDGET_DMIX_SEED?): {room}"
        print(f"[info] dmix after: {len(room)} entries, {len({t for _, t in room})} types, the potion type "
              f"displaced (the walk may have picked the KING HELM up)", flush=True)
    if len(scen) > 5 and scen[5] in ("lglow", "blair", "omix"):
        print(f"[info] {scen[5]} after: boss x {p.ent(5 if scen[5] == 'omix' else 3)['X']}, hero HP "
              f"{p.ent(0)['HP']}, GLOW_CNT {p.rb('GLOW_CNT')}, Ogre counter {p.ent(5)['POT'] & 3}", flush=True)
    if len(scen) > 5 and scen[5] == "lqmix":        # AI-L1: where the climbers ended
        print(f"[info] lqmix after: climbers (x, y) {[(p.ent(sl)['X'], p.ent(sl)['Y']) for sl in (5, 3, 1)]},"
              f" hero ({p.ent(0)['X']}, {p.ent(0)['Y']})", flush=True)
    if len(scen) > 5 and scen[5] == "qmix":         # IC1: the potion pick as drawn (state bits 2-3)
        sh = list(p.z.read_memory(S["ICON_SH"] + S["QS_SLOT0"], 3))
        print(f"[info] qmix after: quick ICON_SH {[hex(v) for v in sh]} (potion pick {(sh[1] >> 2) & 3}),"
              f" HP {p.ent(0)['HP']}/{p.ent(0)['MAXHP']}, MP {p.rb('MP')}, bag {list(p.z.read_memory(S['BAG'], 15))}",
              flush=True)
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
    if os.environ.get("BUDGET_WORST_IX"):         # diagnostic: where the worst tick sits (+ its neighbours)
        wi = totals.index(worst[0])
        print(f"worst index    : {wi} of {len(totals)}; totals around it {totals[max(0, wi - 3):wi + 4]}")
    print(f"mean tick: {sum(totals) // len(totals)} T")
    print(f"worst split    : " + ", ".join(f"{k}={v}" for k, v in worst[1].items()))
    if os.environ.get("GAME_PROFILE"):            # 3F-B5: per-phase max / sum over ALL ticks (A/B work)
        ph = {}
        for _, sp in st.ticks:
            for k, v in sp.items():
                m, s = ph.get(k, (0, 0))
                ph[k] = (max(m, v), s + v)
        print("phase max/sum  : " + ", ".join(f"{k}={m}/{s}" for k, (m, s) in ph.items()
                                              if k in ("try_player_turn", "resolve_monsters", "materialise")))
        if os.environ.get("GAME_PROFILE_TICKS"):  # per-tick resolve_monsters (A/B diffs)
            print("resolve/tick   : " + " ".join(str(sp.get("resolve_monsters", 0)) for _, sp in st.ticks))
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
        st.swing = swing if HAS_TRACE else None
        print(f"staff swings   : {swing if HAS_TRACE else 'counted on the ANIM_TRACE copy (end of run)'}"
              f" turns drew STAFF_SWING", flush=True)
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


ALL_KEYS = ("mix,mage,heavy,lightning,cast,lcast,lcastf,lcasts,advcast,fzcast,fzcast2,fcast,wcast,wcast4,acast,mkmix,pmix,umix,qmix,"
            "tdart,tgas,ttele,talarm,tstun,tfaint,tsearch,tsense,imix,dmix,tmix,rroom,nroom,rfar,bsum,aroom,asum,walarm,walarm2,vbat,trickle,otrickle,rcast,sroom,lglow,blair,omix,lqmix,sanct,adeath,dnum,dkill,ghost3,ghost5,glad")


def swing_pass(keys):
    """BLAIR-FIX (tests/game.py's RECLAIM-C2 approach): the release build has no ANIM_TRACE, so the
    STAFF_SWING count of the Mage scenarios is taken on a private -DDEBUG_KIT=0 -DANIM_TRACE_ON=1 copy
    (~5 s, temp dir), in a child run AFTER the timed one: the trace adds render work (R_LOG, trace_log),
    so the gated T-states stay those of the build under test. Returns {key: swings} (None: build failed)."""
    import shutil
    import subprocess
    import tempfile
    root = os.path.dirname(HERE)
    out = tempfile.mkdtemp(prefix="budget_trace_")
    print(f"[budget] staff-swing count: building -DDEBUG_KIT=0 -DANIM_TRACE_ON=1 -> {out}", flush=True)
    try:
        r = subprocess.run([os.path.join(root, "tools", "build.sh"), "-o", out, "-DDEBUG_KIT=0",
                            "-DANIM_TRACE_ON=1"], capture_output=True, text=True)
        if r.returncode:
            print("[budget] trace build failed:\n" + r.stdout[-1500:] + r.stderr[-500:], flush=True)
            return None
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True,
                           env=dict(os.environ, WZ_BUILD_DIR=os.path.join(out, "build"),
                                    BUDGET_SWING_ONLY="1", BUDGET_ONLY=",".join(keys)))
        res = {}
        for ln in r.stdout.splitlines():
            if ln.startswith("[swing] "):
                k, v = ln.split()[1:3]
                res[k] = int(v)
        if not res:
            print("[budget] swing pass printed nothing:\n" + r.stdout[-1500:] + r.stderr[-500:], flush=True)
        return res
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    fails = []
    keys = os.environ.get("BUDGET_ONLY", ALL_KEYS).split(",")
    swing_only = bool(os.environ.get("BUDGET_SWING_ONLY"))      # child of swing_pass (trace copy)
    # the Mage scenarios on the melee KEYS (FIRE taps at gap 0: the C3-7 STAFF_SWING); the cast ones
    # FIRE a spell, so their count says nothing (and the child pass would double the run)
    wiz = [k for k in keys if len(SCENARIOS[k]) > 3 and SCENARIOS[k][3] == K_WIZARD and SCENARIOS[k][2] is KEYS]
    with Harness() as h:
        h.launch(EMU_ARGS)
        for key in keys:
            st, bad = run_scenario(h, SCENARIOS[key])
            if swing_only:
                if getattr(st, "swing", None) is not None:
                    print(f"[swing] {key} {st.swing}", flush=True)
                continue
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
    if swing_only:
        return 0
    if wiz and not HAS_TRACE and not os.environ.get("BUDGET_NO_SWING"):
        sw = swing_pass(wiz)                      # (the timed harness is closed: same ZRCP port)
        if sw is not None:
            print("staff swings   : " + ", ".join(f"{k} {sw.get(k, '?')}" for k in wiz)
                  + " turns drew STAFF_SWING (ANIM_TRACE copy)", flush=True)
        # D3-11 review: a melee Mage scenario that drew no STAFF_SWING proves nothing (the
        # copy failed to swing, or the count was lost): a gate failure, not a 0 to read past
        fails += [k + " (no STAFF_SWING)" for k in wiz if not (sw or {}).get(k)]
    print(f"[{'FAIL' if fails else 'PASS'}] budget gate (every tick <= budget in"
          f" {', '.join(GATED)}; <= {CAP} in {', '.join(CAP_GATED)}; cast ticks <= {CAST_CAP}): {fails or 'ok'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
