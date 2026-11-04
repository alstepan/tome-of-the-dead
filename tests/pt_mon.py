#!/usr/bin/env python3
"""T14: end-to-end playthrough bot (release build, -DDEBUG_KIT=0), ZRCP-driven.

A deterministic bot plays a real run from the menu: new game (SEED_FIXED via poke seed_fixed /
seed_value, proto_start = 0), D1 -> D8 -> GS_WIN (or GS_DEAD for the death variant), for either
hero.  Everything that is gameplay runs on the game's own code paths: combat, abilities, XP /
level-ups, floor pickups, hunger / food, the bag page, room changes and room-mem re-entry, bosses,
the Archmage, the sealed Sanctum door, the Tome (flash / ash / border), the D8 gate, the end card.

What the bot is allowed to poke (every use is counted and reported at the end of a run):
  nav     hero position inside the CURRENT room (stuck recovery only; the room change itself is
          then still the game's own walk through the exit)
  god     hero HP top-up when the bot would otherwise die (only with --god; default is no god mode)

Monitor, sampled at EVERY tick (see Mon):
  T       tick work (tick_work -> wait_tick, T-states) <= 141,816 (2 frames); transitions / end
          card ticks are reported separately (budget.py treats them the same way)
  FRAMES  SYS_FRAMES delta == AY_CALLS delta at every sample (no interrupt lost)
  STATE   GAME_STATE sane, GEN_OVERFLOW 0
  BANK7   bank-7 code ($DB00..$F800) hash == the .sna's (checked every BANK7_EVERY ticks)
  MAP     ROOM_MAP ids < TILE_IDS, and the cells of every room that are static in the generator's
          model (bricks) match it
  ENT     <= 16 slots, every active slot has a valid kind / room / position, no body left DYING for
          > 80 ticks, parked (other-room) bodies <= 15
  TOME    TOME_HP only decreases, 0 outside D8; TOME_FL <= TOME_FL_N
  BORDER  border (port $FE & 7) is 0 except while TOME_FL runs (white / yellow) or an ALARM trap
          (red); a non-zero border for > 6 ticks in a row is a violation
  LOG     every line pushed to the log ring decodes to the charset of the game's font / strings
  [ANOMALY] harness lines are counted (Proto.anomalies)

Run:  ZRCP_PORT=<port> python3 tests/playthrough.py [--hero W|M] [--seed N] [--mode win|dead] [--god]
Never port 10000.
"""
import argparse
import collections
import hashlib
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, Proto, GS_PLAYING, GS_WIN, GS_DEAD, GS_SELECT,  # noqa: E402
                      GS_TRANSITION, K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT,
                      EF_DYING, RUN_LIMIT, MAX_RUN_RETRIES, stand_y, sna_bank7)
import game_lib  # noqa: E402
import room_model  # noqa: E402
import textpack  # noqa: E402
from lp import T as LPT, w16  # noqa: E402

BUDGET = 2 * 70908
BANK7_EVERY = 25
BANK7_LO, BANK7_HI = S["B7_CODE"], S["B7_LIMIT"]
STRIDE = S["P_ENT_STRIDE"]
NOWHERE = 15
LOG_SLOTS, LOG_SLOT_LEN = S["LOG_SLOTS"], S["LOG_SLOT_LEN"]
LOG_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?'+-/:>%()<=*&@#$\"")
IMG = textpack.parse_emitted(os.path.join(game_lib.BUILD_DIR, "text", "strings.asm"))


class Mon:
    """Per-tick monitor state and the violation / statistics ledger."""

    def __init__(self, p):
        self.p = p
        self.viol = collections.OrderedDict()           # kind -> [(tick, text)]
        self.ticks = 0
        self.max_t = 0
        self.max_t_info = None
        self.max_work_t = 0                              # ticks that are NOT transitions / end cards
        self.over = []                                   # work ticks over BUDGET
        self.top = []                                    # (T, tick, depth, room, TURN_PHASE, TURN_PEND, last log lines)
        self.trans = []                                  # (T, why)
        self.tome_hp_prev = None
        self.dying = {}
        self.b_nonzero = self.b_stale = 0
        self.bring = []
        self.max_border_run = 0
        self.last_sf = self.last_ay = None
        self.slow = []                                   # (tick, dsf, T, why, room) play ticks 4+ frames after the previous sample (a 3 is only the sampling phase moving)
        self.dsf = collections.Counter()
        self.ring_prev = None
        self.lines = collections.Counter()
        self.hp_trace = collections.deque(maxlen=40)     # (tick, HP) of the hero, one per play tick
        self.recent = collections.deque(maxlen=30)       # (tick, text) of the last log lines
        self.garbage = []
        self.b7_hash = hashlib.sha256(bytes(sna_bank7(BANK7_LO, BANK7_HI - BANK7_LO))).hexdigest()
        self.b7_checks = 0
        self.max_ents = 0
        self.max_parked = 0
        self.tome_seen = collections.Counter()
        self.border_seen = collections.Counter()
        self.depth = None
        self.room = None
        self.gs = None
        self.end_shown = 0

    def v(self, kind, text):
        L = self.viol.setdefault(kind, [])
        L.append((self.p.rw("TICK_COUNTER"), text))
        if len(L) <= 3:
            print(f"[VIOLATION] {kind} @tick {self.ticks}: {text}", flush=True)

    # --- helpers -------------------------------------------------------------
    def border(self):
        m = re.search(r"Spectrum FE port:\s*([0-9A-Fa-f]+)", self.p.z.cmd("get-io-ports"))
        return int(m.group(1), 16) & 7 if m else -1

    def mb(self, name_or_addr):
        """a byte from this tick's block reads (page $BF00, LVL_DEPTH..TOME_FL); anything else single-reads."""
        a = S[name_or_addr] if isinstance(name_or_addr, str) else name_or_addr
        if 0xBF00 <= a < 0xC000:
            return self.pg[a - 0xBF00]
        if S["LVL_DEPTH"] <= a <= S["TOME_FL"]:
            return self.lv[a - S["LVL_DEPTH"]]
        return self.p.rb(a)

    def sample(self, t, in_work, stop_pc=None):
        """After a tick (at wait_tick / select_tick). t = tick work T-states or None."""
        p = self.p
        self.ticks += 1
        # two block reads replace ~10 single-byte ZRCP round trips per tick (the host is the bottleneck)
        self.pg = bytes(p.z.read_memory(0xBF00, 256))
        self.lv = bytes(p.z.read_memory(S["LVL_DEPTH"], S["TOME_FL"] - S["LVL_DEPTH"] + 1))
        rb = self.mb
        gs, room, depth = rb("GAME_STATE"), rb("CUR_ROOM"), rb("LVL_DEPTH")
        shown = rb("END_SHOWN") & S["ES_CARD"]
        why = None
        if self.room is not None and room != self.room:
            why = "room change"
        if self.depth is not None and depth != self.depth:
            why = "level change"
        if self.gs is not None and gs != self.gs:
            why = f"state {self.gs}->{gs}"
        if shown and not self.end_shown:
            why = "end card"
        if stop_pc == S["select_tick"] and t is not None:
            why = "modal (page / menu)"
        self.end_shown = shown
        if t is not None:
            if why:
                self.trans.append((t, why))
                self.max_t = max(self.max_t, t)
            else:
                self.max_work_t = max(self.max_work_t, t)
                self.max_t = max(self.max_t, t)
                if len(self.top) < 8 or t > self.top[-1][0]:      # the heaviest work ticks, with their context
                    self.top.append((t, self.ticks, depth, room, self.mb("TURN_PHASE"), p.rb("TURN_PEND"),
                                     [x for _, x in list(self.recent)[-2:]]))
                    self.top = sorted(self.top, key=lambda e: -e[0])[:8]
                if t > BUDGET:
                    self.over.append((self.ticks, t))
                    self.v("T", f"work tick {t} T > {BUDGET} (room {room}, D{depth})")
        self.room, self.depth, self.gs = room, depth, gs
        # frames vs AY calls
        sf = int.from_bytes(p.z.read_memory(S["SYS_FRAMES"], 3), "little")
        ay = self.mb("AY_CALLS") | self.mb(S["AY_CALLS"] + 1) << 8
        if self.last_sf is not None:
            dsf = (sf - self.last_sf) & 0xFFFFFF
            day = (ay - self.last_ay) & 0xFFFF
            if dsf != day:
                self.v("FRAMES", f"dSYS_FRAMES {dsf} != dAY_CALLS {day}")
            self.dsf[min(dsf, 99)] += 1
            if gs == GS_PLAYING and dsf >= 4 and stop_pc != S["select_tick"] and len(self.slow) < 400:
                self.slow.append((self.ticks, dsf, t, why, room))
        self.last_sf, self.last_ay = sf, ay
        if gs not in (GS_PLAYING, GS_WIN, GS_DEAD, GS_SELECT, GS_TRANSITION, 7, 8, 9, 10, 11):
            self.v("STATE", f"GAME_STATE {gs}")
        if rb("GEN_OVERFLOW"):
            self.v("GEN_OVERFLOW", f"GEN_OVERFLOW {rb('GEN_OVERFLOW')}")
        if gs in (GS_PLAYING,):
            self.ent_check(room, depth)
            self.tome_check(depth)
            self.log_check()
        self.border_check()
        if self.ticks % BANK7_EVERY == 0:
            self.b7_check()

    def b7_check(self):
        p = self.p
        p.z.cmd("set-memory-zone 0")
        try:
            raw = bytes(p.z.read_memory(7 * 16384 + BANK7_LO - 0xC000, BANK7_HI - BANK7_LO))
        finally:
            p.z.cmd("set-memory-zone -1")
        self.b7_checks += 1
        if hashlib.sha256(raw).hexdigest() != self.b7_hash:
            bad = [i for i, (a, b) in enumerate(zip(raw, sna_bank7(BANK7_LO, BANK7_HI - BANK7_LO))) if a != b]
            self.v("BANK7", f"bank-7 code differs from the .sna at {len(bad)} bytes, first {BANK7_LO + bad[0]:#x}")
            self.b7_hash = hashlib.sha256(raw).hexdigest()   # report once per change

    def ent_check(self, room, depth):
        p = self.p
        raw = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        act = parked = 0
        for s in range(16):
            b = raw[s * STRIDE:(s + 1) * STRIDE]
            fl = b[S["E_FLAGS"]]
            if not fl & EF_ACTIVE:
                self.dying.pop(s, None)
                continue
            act += 1
            if s == 0:
                self.hp_trace.append((self.ticks, b[S["E_HP"]]))
            k, r, x, y = b[S["E_KIND"]], b[S["E_ROOM"]], b[S["E_X"]], b[S["E_Y"]]
            if s and r != room:
                parked += 1
            if k >= S["K_COUNT"] or r > 8 or x > 31 or y > 17:
                self.v("ENT", f"slot {s}: kind {k} room {r} x {x} y {y} flags {fl:#x}")
            if s and r == NOWHERE:
                self.v("ENT", f"slot {s}: parked in NOWHERE (leak) kind {k}")
            if s and not fl & EF_HOSTILE and not fl & EF_DYING:
                self.v("ENT", f"slot {s}: active, non-hostile non-dying monster slot kind {k}")
            if fl & EF_DYING:
                self.dying[s] = self.dying.get(s, 0) + 1
                if self.dying[s] == 80:
                    self.v("ENT", f"slot {s}: DYING for 80 ticks (leaked corpse) kind {k} room {r}")
            else:
                self.dying.pop(s, None)
        self.max_ents = max(self.max_ents, act)
        self.max_parked = max(self.max_parked, parked)
        if act > 16:
            self.v("ENT", f"{act} active slots")
        if parked > 15:
            self.v("ENT", f"{parked} parked bodies")

    def tome_check(self, depth):
        p = self.p
        hp, fl = self.mb("TOME_HP"), self.mb("TOME_FL")
        self.tome_seen[(hp, fl)] += 1
        if depth != 8 and hp:
            self.v("TOME", f"TOME_HP {hp} on D{depth}")
        if hp > S["TOME_MAX"] or fl > S["TOME_FL_N"]:
            self.v("TOME", f"TOME_HP {hp} TOME_FL {fl}")
        if self.tome_hp_prev is not None and depth == 8 and hp > self.tome_hp_prev and self.tome_hp_prev:
            self.v("TOME", f"TOME_HP rose {self.tome_hp_prev} -> {hp}")
        if depth == 8 and hp:
            self.tome_hp_prev = hp
        elif depth != 8:
            self.tome_hp_prev = None

    def border_check(self):
        """Border (port $FE & 7) is 0 except: white / yellow while the Tome hook runs (TOME_FL > 0; a hit every 3rd
        tick keeps it lit across hits: by design the 2-tick flash is re-armed), red for an ALARM trap (<= 6 ticks).
        A lit border with TOME_FL 0 for more than 2 samples, any other colour, or red for > 6 ticks = violation."""
        tfl = self.mb("TOME_FL") if self.gs == GS_PLAYING else 0
        if not (tfl or self.b_nonzero or self.ticks % 3 == 0 or self.gs != GS_PLAYING):
            return                     # a get-io-ports round trip is dear: sampled on every Tome / lit tick, else every 3rd
        b = self.border()
        self.border_seen[b] += 1
        self.bring.append((self.ticks, b, tfl, self.mb("TOME_HP"), self.mb("TURN_PHASE")))
        self.bring = self.bring[-30:]
        tome_cols = (S["BORDER_TOME"] & 7, S["BORDER_TOME_END"] & 7)
        if b == 0:
            self.b_nonzero = self.b_stale = 0
            return
        self.b_nonzero += 1
        self.max_border_run = max(self.max_border_run, self.b_nonzero)
        if self.gs != GS_PLAYING or self.ticks < 40:
            return                                   # menu / loading border is the loader's business
        if b in tome_cols:
            self.b_stale = self.b_stale + 1 if not tfl else 0
            if self.b_stale > 2:
                self.v("BORDER", f"Tome border {b} lit with TOME_FL 0 for {self.b_stale} samples: {self.bring[-8:]}")
                self.b_stale = 0
        elif b == S["BORDER_ALARM"]:
            if self.b_nonzero > 6:
                self.v("BORDER", f"ALARM red border for {self.b_nonzero} ticks")
                self.b_nonzero = 0
        else:
            self.v("BORDER", f"unexpected border colour {b}")
        if self.gs in (GS_DEAD, GS_WIN) and self.b_nonzero > 3:
            self.v("BORDER", f"border {b} lit on the end card ({self.b_nonzero} ticks)")
            self.b_nonzero = 0

    def log_check(self):
        p = self.p
        rd = (self.mb(S["LOG_Q"] + S["LQ_RD"]), self.mb("LOG_QN"))
        wr = (rd[0] + rd[1]) % LOG_SLOTS
        if self.ring_prev is None:
            self.ring_prev = wr
            return
        n = (wr - self.ring_prev) % LOG_SLOTS
        if n:
            raw = bytes(p.z.read_memory(S["LOG_TXT"], LOG_SLOTS * LOG_SLOT_LEN))
            for k in range(n):
                sl = (self.ring_prev + k) % LOG_SLOTS
                txt = textpack.expand(IMG, raw[sl * LOG_SLOT_LEN:][:LOG_SLOT_LEN])
                self.note_line(txt)
        self.ring_prev = wr

    def note_line(self, txt):
        norm = re.sub(r"\d+", "#", txt)
        self.recent.append((self.ticks, txt))
        self.lines[norm] += 1
        ok = txt and set(txt) <= LOG_CHARS and len(txt) <= S["LOG_MAX"] and txt == txt.strip() or txt == ""
        if not ok or not txt:
            self.garbage.append(txt)
            self.v("LOG", f"garbage / empty log line {txt!r}")


class PT(LPT):
    """lp.T (code stubs, kb, ...) + per-tick monitoring: tick_work / wait_tick bracketing."""
    mon = None

    def pc(self):
        """get-registers can answer empty under host load: retry (a glitch is not a game fault)."""
        for i in range(8):
            r = self.z.cmd("get-registers")
            m = re.match(r"PC=([0-9a-fA-F]{4})", r)
            if m:
                return int(m.group(1), 16)
            time.sleep(0.2)
            print(f"[WARN] get-registers returned {r[:40]!r} (retry {i})", flush=True)
        raise RuntimeError("get-registers keeps failing")

    def load_breakpoints(self):
        super().load_breakpoints()
        self.z.cmd("set-breakpoint 6 PC=%d" % S["tick_work"])

    # PERF-GHOST: PT_PROF="a-b" = per-phase split (tests/budget.py GAME_PROFILE phases + the ISR) of every
    # play tick a..b (monitor tick numbers); ticks >= PT_PROF_MIN T (default 120000) are printed as
    # "[prof] tick T split". Extra probe labels: PT_PROF_EXTRA=label,label. Emulated behaviour is unchanged
    # (breakpoints only), so the run stays deterministic.
    PROF_PHASES = ["intent_tick", "read_turn_input", "pend_far", "probe_act_fire", "try_player_turn",
                   "resolve_monsters", "materialise", "anim_tick", "render", "render.nopend", "render.sdone",
                   "render.f3done", "render.drdone", "render.nopl", "pmark_dmg", "present", "decor_tick",
                   "panel_tick", "panel_done", "dn_gate", "isr", "isr.done"]
    PROF_BP0 = 60
    prof_on = False

    def _prof_window(self):
        w = os.environ.get("PT_PROF")
        if not w or not self.mon:
            return False
        a, b = (int(x) for x in w.split("-"))
        return a <= self.mon.ticks + 1 <= b

    def _prof_set(self, on):
        if on == self.prof_on:
            return
        self.prof_on = on
        names = self.PROF_PHASES + [x for x in os.environ.get("PT_PROF_EXTRA", "").split(",") if x in S]
        self.prof_inv = {S[nm]: nm for nm in names if nm in S}
        for i, nm in enumerate(names):
            if nm in S:
                self.z.cmd("set-breakpoint %d PC=%d" % (self.PROF_BP0 + i, S[nm]) if on
                           else "set-breakpoint %d" % (self.PROF_BP0 + i))

    def tick(self, n=1):
        z = self.z
        for _ in range(n):
            self._prof_set(self._prof_window())
            z.cmd("cpu-step")
            in_work = False
            t = None
            stop = None
            split, last, prev, saved = {}, "tick_work", 0, None
            attempt = 0
            while attempt <= MAX_RUN_RETRIES:
                r = z.cmd("run %d" % RUN_LIMIT)
                m = re.search(r"^PC=([0-9a-fA-F]{4})", r, re.M)
                pc = int(m.group(1), 16) if m else self.pc()
                if self.prof_on and pc in self.prof_inv:
                    if in_work:
                        v = int(z.cmd("get-tstates-partial"))
                        split[last] = split.get(last, 0) + v - prev
                        prev = v
                        nm = self.prof_inv[pc]
                        if nm == "isr":
                            saved, last = last, "isr"
                        elif nm == "isr.done":
                            last = saved or "tick_work"
                        else:
                            last = nm
                    z.cmd("cpu-step")
                    continue
                attempt += 1
                if pc == S["tick_work"]:
                    z.cmd("reset-tstates-partial")
                    in_work = True
                    split, last, prev, saved = {}, "tick_work", 0, None
                    trs = os.environ.get("PT_ITRACE")         # PERF-GHOST: instruction profile of these ticks
                    if trs and self.mon and self.mon.ticks + 1 in [int(x) for x in trs.split(",")]:
                        import tick_prof
                        if not hasattr(self, "_sld"):
                            self._sld = tick_prof.load_sld(os.path.join(game_lib.BUILD_DIR, "wazhack.sld"))
                        ex, inc, cl = tick_prof.trace_tick(z, S["wait_tick"], self._sld, S["PORT_7FFD_SHADOW"])
                        t = int(z.cmd("get-tstates-partial"))
                        print(f"[trace] tick {self.mon.ticks + 1}: {t} T\n" + tick_prof.report(ex, inc, cl, 70),
                              flush=True)
                        stop = S["wait_tick"]
                        break
                    z.cmd("cpu-step")
                    continue
                if pc in self.probes:
                    stop = pc
                    if in_work:
                        t = int(z.cmd("get-tstates-partial"))
                    break
                Proto.anomalies += 1
                print(f"[ANOMALY] run returned at PC={pc:#06x} (not a probe): {r[:90]!r}", flush=True)
            else:
                raise RuntimeError("run keeps returning outside the probes")
            if self.prof_on and t is not None and t >= int(os.environ.get("PT_PROF_MIN", "120000")):
                split[last] = split.get(last, 0) + t - prev
                print(f"[prof] tick {self.mon.ticks + 1} {t} T: room {self.rb('CUR_ROOM')} D{self.rb('LVL_DEPTH')} "
                      f"ph {self.rb('TURN_PHASE')}/{self.rb('TURN_PEND')}: "
                      + ", ".join(f"{k}={v}" for k, v in split.items()), flush=True)
            if self.mon:
                self.mon.sample(t, in_work, stop)
