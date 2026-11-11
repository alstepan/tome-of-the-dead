#!/usr/bin/env python3
"""ISR-RATE: the 50 Hz AY interrupt never drifts, under the game's heaviest ticks and the transitions.

Release build (-DDEBUG_KIT=0), music on (SND_MODE 3, the Lament; the game itself requests the Dangerous
tune when hostiles are awake) in every scenario:
  blair, dnum, dkill, wcast4   tests/budget.py scenarios (its setup + Stepper, so the same heavy ticks),
                               then idle ticks (hero HP topped up) up to MIN_FRAMES
  exit                         room A <-> B transitions (real walk, hscroll + lp_transition)
  descend                      level_descend D1 .. D7 (level generation, the Level Complete stinger wait)
                               with idle play between; the stub runs with EI, as in play
  bag                          bag page open / cursor moves / close, repeated
  iy                           IX / IY across the ISR (isr -> isr.done) with SFX requests: the handler
                               does not save IY (ISR-RATE), so the player must never touch it

A meter wraps the ZRCP command channel: it adds every `reset-tstates-partial` (the budget Stepper resets
per tick) to a running total, so T is absolute over a window. A sample (after every tick, at the
wait_tick / select_tick breakpoint, never inside an ISR) reads T, SYS_FRAMES (3 B), AY_CALLS and the
mailbox (SND_MODE, MUS_REQ, MUS_SHOT, MUS_STATE, MUS_CUR). A harness stub (`set-register PC=`: p.code, a
DI'd test routine, which loses frames by construction) ends the window: the next sample starts a new one.
Asserted per scenario, >= MIN_FRAMES frames in total:
  - dSYS_FRAMES == dAY_CALLS at every sample (one AY_PLAY call per counted frame);
  - |dSYS_FRAMES - round(dT / 70908)| <= 1 against the window start at every sample, and for every
    consecutive pair of samples (no accumulating drift);
  - SND_MODE bit 7 (SND_HOLD) never set; MUS_CUR changes only to MUS_REQ (a start the game asked for, listed
    in the log), follows MUS_REQ within 2 samples, no MUS_SHOT / MS_SHOT unless the scenario plays the
    stinger (descend).
Not done: the frame-by-frame chip-register oracle (tests/sound.py does it for the same player).
Usage: ZRCP_PORT=<port> python3 tests/isr_rate.py [scenario ...]    (default port 10741, never 10000)
"""
import os
import sys

os.environ.setdefault("ZRCP_PORT", "10741")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ARGS = sys.argv[1:]
import budget  # noqa: E402  (sets sys.argv; imports game / game_lib)
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, stand_y  # noqa: E402
import game  # noqa: E402
import lp  # noqa: E402

FRAME_T = 70908
MIN_FRAMES = 2000
MS_LOOP, MS_SHOT, MS_MASK = 1, 2, 3
LAMENT = S["MUS_LAMENT"]
MBOX = S["SND_MODE"]
assert [S[n] - MBOX for n in ("SND_MODE", "MUS_REQ", "MUS_SHOT", "MUS_STATE", "MUS_CUR")] == [0, 1, 2, 3, 4]


class Meter:
    def __init__(self, name, z, steady=True):
        self.name, self.z, self.steady = name, z, steady
        self.acc, self.base, self.prev, self.n = 0, None, None, 0
        self.bad, self.seen, self.worst = [], {}, 0.0
        self.go, self.dirty, self.rebases = True, False, 0   # go: armed only once true (budget: 1st Stepper tick)
        self.last_cur, self.lag, self.trans = None, 0, []
        self.frames = self.total_t = 0
        self.orig = z.cmd
        z.cmd = self._cmd

    def _cmd(self, line):
        if line == "reset-tstates-partial":
            self.acc += int(self.orig("get-tstates-partial"))
        elif line.startswith("set-register PC="):
            self.dirty = True                     # a harness stub ran: not the game's interrupt state
        return self.orig(line)

    def close(self):
        self.z.cmd = self.orig

    def now(self):
        z = self.z
        t = self.acc + int(self.orig("get-tstates-partial"))
        sf = int.from_bytes(z.read_memory(S["SYS_FRAMES"], 3), "little")
        ay = int.from_bytes(z.read_memory(S["AY_CALLS"], 2), "little")
        return t, sf, ay, bytes(z.read_memory(MBOX, 5))

    def fail(self, msg):
        if len(self.bad) < 8:
            self.bad.append(msg)

    def sample(self, tag="tick"):
        t, sf, ay, mb = self.now()
        mode, req, shot, state, cur = mb
        if self.base is None or self.dirty:
            if not self.go:
                return
            if self.base is not None:
                self.rebases += 1                 # a harness stub ran in this interval: a fresh window
            self.dirty = False
            self.base = self.prev = (t, sf, ay)
            self.last_cur = cur
            return
        self.n += 1
        t0, sf0, ay0 = self.base
        df, da = (sf - sf0) & 0xFFFFFF, (ay - ay0) & 0xFFFF
        if df & 0xFFFF != da:
            self.fail(f"{tag} dSYS_FRAMES {df} != dAY_CALLS {da}")
        dt = t - t0
        self.worst = max(self.worst, abs(df - dt / FRAME_T))
        if abs(df - round(dt / FRAME_T)) > 1:
            self.fail(f"{tag} window frames {df} vs T {dt} ({dt / FRAME_T:.2f})")
        pt, psf, pay = self.prev
        pdf, pdt = (sf - psf) & 0xFFFFFF, t - pt
        if abs(pdf - round(pdt / FRAME_T)) > 1 or pdf != (ay - pay) & 0xFFFF:
            self.fail(f"{tag} pair: frames {pdf} AY {(ay - pay) & 0xFFFF} T {pdt} ({pdt / FRAME_T:.2f})")
        self.prev = (t, sf, ay)
        self.frames += pdf
        self.total_t += pdt
        key = (cur, state & 0x83, mode >> 7)
        self.seen[key] = self.seen.get(key, 0) + 1
        if mode & 0x80:
            self.fail(f"{tag} SND_HOLD set at frame {self.frames}")
        st3 = state & MS_MASK
        if cur != self.last_cur:                  # a music start: only one the game / scenario requested
            self.trans.append((self.frames, self.last_cur, cur))
            if not (cur == req and st3 == MS_LOOP) and not (st3 == MS_SHOT and not self.steady):
                self.fail(f"{tag} unrequested music start at frame {self.frames}: MUS_CUR {self.last_cur} -> {cur},"
                          f" MUS_REQ {req} MUS_STATE {state:#04x} SHOT {shot}")
            self.last_cur = cur
        if st3 == MS_LOOP and cur != req:         # the ISR takes MUS_REQ on its next frame: 2 samples at most
            self.lag += 1
            if self.lag > 2:
                self.fail(f"{tag} MUS_CUR {cur} does not follow MUS_REQ {req} (frame {self.frames})")
        else:
            self.lag = 0
        if self.steady and (shot or st3 == MS_SHOT):
            self.fail(f"{tag} one-shot music at frame {self.frames}: MUS_SHOT {shot} MUS_STATE {state:#04x}")

    def report(self, checks):
        ok = not self.bad and self.frames >= MIN_FRAMES
        seen = ", ".join(f"cur {c} state {s:#04x} hold {h}: {n}" for (c, s, h), n in sorted(self.seen.items()))
        tr = ", ".join(f"f{f}: {a}->{b}" for f, a, b in self.trans) or "none"
        print(f"[{'PASS' if ok else 'FAIL'}] {self.name}: {self.frames} frames, {self.total_t} T"
              f" ({self.total_t / FRAME_T:.2f} frames), max |dF - dT/{FRAME_T}| in a window {self.worst:.2f},"
              f" {self.n} samples, {self.rebases} stub rebases; mailbox states [{seen}];"
              f" music starts (game-requested): {tr}", flush=True)
        for b in self.bad:
            print("   ", b, flush=True)
        if self.frames < MIN_FRAMES:
            print(f"    only {self.frames} frames (< {MIN_FRAMES})", flush=True)
        checks.append(ok)


M = {"m": None}                                   # the active meter (the tick wrappers read it)
LAST = {"p": None}


def hook_ticks():
    """Every Proto / Stepper tick ends with a sample (at wait_tick or select_tick, never inside an ISR)."""
    otick = game.Proto.tick

    def ptick(self, n=1):
        for _ in range(n):
            otick(self, 1)
            if M["m"]:
                M["m"].sample()
    game.Proto.tick = ptick
    ost = budget.Stepper.tick

    def stick(self):
        r = ost(self)
        if M["m"]:
            M["m"].go = True                      # budget: the setup / pre-roll stubs are behind us
            M["m"].sample()
        return r
    budget.Stepper.tick = stick
    ot = budget.game.T

    class Rec(ot):
        def __init__(self, h):
            super().__init__(h)
            LAST["p"] = self
    budget.game.T = Rec


def top_up(p):
    p.set_ent(0, HP=250, MAXHP=250)


def pad(p, m):
    """Idle ticks until the windows hold MIN_FRAMES frames (the hero kept alive)."""
    i = 0
    while m.frames < MIN_FRAMES and i < 2000:
        if i % 40 == 0:
            top_up(p)
        p.tick()
        i += 1


def run_budget(h, key, checks):
    m = M["m"] = Meter(key, h.z)
    m.go = False                                  # armed by the first Stepper tick (after setup, pre-roll)
    try:
        budget.run_scenario(h, budget.SCENARIOS[key])
        pad(LAST["p"], m)
    finally:
        M["m"] = None
        m.close()
    m.report(checks)


def new_game(h, proto=True):
    p = game.T(h)
    p.proto_start = 1 if proto else 0
    p.boot(K_KNIGHT, freeze=0)
    return p


def run_exit(h, checks):
    p = new_game(h)
    p.isolate()
    p.wb("MUS_REQ", LAMENT)
    p.settle(6)
    m = M["m"] = Meter("exit", h.z)
    try:
        y = stand_y(1, 6)
        rooms = set()
        for _ in range(400):
            if m.frames >= MIN_FRAMES:
                break
            top_up(p)
            p.isolate()
            p.place(0, 28, y)
            p.settle(2)
            p.turn("L")                           # room A -> B (hscroll + lp_transition)
            rooms.add(p.rb("CUR_ROOM"))
            p.settle(3)
            p.place(0, 1, y)
            p.settle(1)
            p.turn("H")                           # back to A
            rooms.add(p.rb("CUR_ROOM"))
            p.settle(2)
        print(f"[info] exit: rooms seen {sorted(rooms)}", flush=True)
        assert rooms >= {0, 1}, "exit: no room change happened"
    finally:
        M["m"] = None
        m.close()
    m.report(checks)


def run_descend(h, checks):
    """level_descend called as do_exit does, in play (EI): every stop (the stinger wait's select_tick,
    wait_tick) is a sample."""
    p = lp.T(h)
    p.proto_start = 0
    p.boot(K_KNIGHT, freeze=1)
    m = M["m"] = Meter("descend", h.z, steady=False)
    z = h.z
    stub = S["LOWRAM_END_3B"]
    try:
        depth, descents = 1, 0
        p.settle(10)
        for _ in range(60):
            if m.frames >= MIN_FRAMES and descents >= 6:
                break
            pc0 = p.pc()
            code = [0xFB, 0x3E, depth, 0x32] + lp.w16(S["LVL_DEPTH"]) + [0xCD] + lp.w16(S["level_descend"]) + [0x00, 0x18, 0xFE]
            end = stub + len(code) - 3
            p.wmem(stub, code)
            z.cmd("set-breakpoint 3 PC=%d" % end)
            p.extra_probes = {end}
            m.orig("set-register PC=%d" % stub)   # not a "dirty" event: the stub runs with EI, like play
            ok = False
            for _ in range(2000):                 # run on through the probes, sampling at each
                z.cmd("cpu-step")
                z.cmd("run 20000000")
                if p.pc() == end:
                    ok = True
                    break
                m.sample("descend")
            z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            m.orig("set-register PC=%d" % pc0)
            assert ok, f"descend: level_descend {depth} -> {depth + 1} did not return"
            m.sample("descend-end")
            descents += 1
            depth = depth + 1 if depth < 7 else 1
            p.release()
            for k in range(160):
                if k % 40 == 0:
                    top_up(p)
                p.tick()
        print(f"[info] descend: {descents} descents, final depth {p.rb('LVL_DEPTH')}", flush=True)
    finally:
        M["m"] = None
        m.close()
    m.report(checks)


def run_bag(h, checks):
    p = new_game(h)
    p.isolate()
    p.wb("MUS_REQ", LAMENT)
    p.wb("INPUT_REPEAT", 1)
    p.settle(6)
    m = M["m"] = Meter("bag", h.z)
    opened = 0
    try:
        for _ in range(500):
            if m.frames >= MIN_FRAMES:
                break
            p.tap("I")
            opened += p.rb("PAGE_OPEN") != 0
            for k in ("P", "A", "P", "O", "Q", "O"):   # cursor moves inside the page
                p.tap(k)
            p.tap("I")                            # closed by I (page.py P4)
            assert p.rb("PAGE_OPEN") == 0, "bag: page did not close"
            p.settle(2)
        print(f"[info] bag: page open at {opened} of the cycles", flush=True)
        assert opened >= 10, "bag: the page never opened"
    finally:
        M["m"] = None
        m.close()
    m.report(checks)


def reg(z, name):
    r = z.cmd("get-registers")
    return int(r.split(name + "=")[1][:4], 16)


def run_iy(h, checks):
    """IX / IY across isr -> isr.done (+ the 8 instructions to the exit jp, C-T3): sentinels set at the ISR entry
    must be intact (IY: never saved, so untouched; IX: pushed / popped)."""
    p = new_game(h)
    p.isolate()
    p.wb("MUS_REQ", LAMENT)
    p.settle(6)
    z = h.z
    sfx = [S[n] for n in ("SFX_STEP", "SFX_DOOR", "SFX_LIGHTNING", "SFX_WHIRL", "SFX_QUAFF", "SFX_TRAP", "SFX_FALL")]
    z.cmd("set-breakpoint 20 PC=%d" % S["isr"])
    z.cmd("set-breakpoint 21 PC=%d" % S["isr.done"])
    bad, n = [], 0
    try:
        for i in range(4000):
            if n >= 500:
                break
            z.cmd("cpu-step")                     # off the breakpoint PC (run re-fires on it)
            z.cmd("run")
            pc = int(z.cmd("get-registers")[3:7], 16)
            if pc == S["isr"]:
                if i % 5 == 0:
                    z.cmd("write-memory %d %d" % (S["SFX_REQ"], sfx[(i // 5) % len(sfx)]))
                ix0, iy0 = reg(z, "IX"), reg(z, "IY")
                z.cmd("set-register IY=%d" % 0x5A3C)
                z.cmd("set-register IX=%d" % 0x1357)
            elif pc == S["isr.done"]:
                n += 1
                iy1 = reg(z, "IY")                # IY is never popped: it must be intact right here
                for _ in range(8):                # pop ix / de / bc / hl / af, ld sp, ei, jp (C-T3)
                    z.cmd("cpu-step")
                if iy1 != 0x5A3C or reg(z, "IY") != 0x5A3C or reg(z, "IX") != 0x1357:
                    bad.append((i, hex(iy1), hex(reg(z, "IY")), hex(reg(z, "IX"))))
                z.cmd("set-register IY=%d" % iy0)
                z.cmd("set-register IX=%d" % ix0)
    finally:
        z.cmd("set-breakpoint 20")
        z.cmd("set-breakpoint 21")
        p.load_breakpoints()
    ok = not bad and n >= 500
    print(f"[{'PASS' if ok else 'FAIL'}] iy: {n} ISRs with SFX requests, IX / IY kept "
          f"{'across all' if ok else bad[:4]}", flush=True)
    checks.append(ok)


ALL = ["blair", "dnum", "dkill", "wcast4", "exit", "descend", "bag", "iy"]


def main():
    want = ARGS or ALL
    checks = []
    hook_ticks()
    with Harness() as h:
        h.launch(EMU_ARGS)
        for name in want:
            if name in budget.SCENARIOS:
                run_budget(h, name, checks)
            else:
                {"exit": run_exit, "descend": run_descend, "bag": run_bag, "iy": run_iy}[name](h, checks)
    ok = all(checks) and len(checks) == len(want)
    print(f"[{'PASS' if ok else 'FAIL'}] isr_rate: {sum(checks)}/{len(want)} scenarios")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
