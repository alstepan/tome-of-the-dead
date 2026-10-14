#!/usr/bin/env python3
"""SND-0 S1a..S1e: the WZM v0.3 Z80 player (src/music/player.asm) against the oracle
tools/wzm_ref.py, on the standalone music test tape (src/music/testtape.asm).

Build first: tools/build_music_test.sh (-> build/music_test.sna + .sym).

The tape's IM 2 ISR runs player_frame at 50 Hz and appends the 14-B register
mirror pl_regs of every frame to a 1,024-frame ring at TT_LOG; the oracle is run
on the song bytes read back from the emulator's RAM (pointers are absolute).
  A  free run, every song via the mailbox tt_req: the ring == wzm_ref frame for
     frame (1,024 frames; the 96 bpm Laments to 4,200 frames = through their $80
     loop). One-shots: ENDED at exactly len(oracle) frames (incl. the reverb-tail
     rest), then the counter holds, pl_regs and the AY chip volumes stay 0.
  B  SPACE-equivalent stop (mailbox $FF): STOPPED, chip volumes 0.
  C  keyboard path (set-ui-io-ports): '6' starts song 6 (organ), SPACE stops, 'Q'
     song 8 (harpsichord), 'L' restarts it, '9' song 16, '0' / 'I' / 'O' / 'P' songs
     17..20 (the legato Lament II).
  E  'G' key on the organ Lament: the gate cycles 56 -> 62 -> 100 -> 30 -> 45 -> 56 % (instrument
     bytes patched in RAM, song restarted); after each press the ring == wzm_ref run
     on the re-read (patched) song bytes.
  F  'H' key: reverb S1e -> 0 -> 50 -> 100 -> S1e (bytes == abc2wzm.inst_tail, ring == oracle).
  G  'J' key: the WZM_ECHO experiment off -> 25 -> 50 -> 100 % (pl_edrop 6/4/2), ring ==
     wzm_ref(echo_drop) on the organ Lament IIb and the legato Lament II.
  D  cpu-step, breakpoints around the ISR's CALL player_frame: T-states per frame
     (incl. CALL/RET) and the AY chip registers R0..R12 (ZRCP get-io-ports) ==
     the oracle frame, for N frames of every song (default 256; frame 0 = all
     three voices fetch with a staccato command, the recurring worst case).
Usage: python3 tests/music_player.py [--timing-frames N] [--skip-timing]
       (ZRCP_PORT=... to run beside another suite; MUSIC_BUILD=DIR for another build,
       e.g. the game configuration without WZM_ECHO: stage G is then skipped)
Stage D also prints the max T over two ADJACENT frames (the 2-frame tick bound).
Prints one PASS/FAIL line per check and a summary line; exit 1 on any failure.
"""
import os
import re
import shutil
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
from test_harness import Harness  # noqa: E402
import wzm_ref  # noqa: E402
import abc2wzm  # noqa: E402

# MUSIC_BUILD = the build dir holding music_test.sna/.sym (default build/); the game
# configuration (no echo) is WZM_ECHO=0 tools/build_music_test.sh -o DIR -> DIR/build
BUILD = os.environ.get("MUSIC_BUILD", os.path.join(REPO, "build"))
SNA = os.path.join(BUILD, "music_test.sna")
SYM = os.path.join(BUILD, "music_test.sym")
EMU_ARGS = tuple(os.environ.get("GAME_EMU_ARGS", "--emulatorspeed 1000 --vo null --ao null").split())
LOG_FRAMES = 1024
REQ_STOP = 0xFF
ST_IDLE, ST_PLAYING, ST_ENDED, ST_STOPPED = 0, 1, 2, 3
LONG_RUN = {n: 4200 for n in ("lament_tsx_96", "org_lament", "hps_lament",   # $80 loop
                               "org_lament2", "hps_lament2", "lament2_tsx_96")}  # at 4,000
GATE_BYTES = {30: (3, 0x84), 45: (2, 3), 56: (2, 0x84), 62: (2, 0x83), 100: (1, 8)}  # GATES +5/+6


def load_syms():
    s = {}
    for line in open(SYM):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            s[m.group(1)] = int(m.group(2), 16)
    return s


S = load_syms()
ECHO = "pl_edrop" in S          # WZM_ECHO assembled (the default tape; not the game)


class CountingHarness(Harness):
    n_checks = 0

    def expect(self, name, got, want):
        """Harness.expect for any value (tuples/bytes), counting checks."""
        self.n_checks += 1
        ok = got == want
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got!r} want {want!r}"), flush=True)
        if not ok:
            self.failures.append(name)
        return ok


class Tape:
    def __init__(self, h):
        self.h, self.z = h, h.z
        self.stepping = False

    def rb(self, a):
        return self.h.read_byte(S[a] if isinstance(a, str) else a)

    def rw(self, a):
        return self.h.read_word_le(S[a] if isinstance(a, str) else a)

    def req(self, n, wait=True):
        """Mailbox request; wait (free run only) until the ISR has taken it."""
        self.h.write_byte(S["tt_req"], n)
        t0 = time.time()
        while wait and self.rb("tt_req"):
            if time.time() - t0 > 5:
                raise TimeoutError("ISR never took tt_req")
            time.sleep(0.01)

    def pc(self):
        return int(self.z.cmd("get-registers")[3:7], 16)

    def chip(self):
        """AY-3-8912 registers R0..R15 as the emulator holds them."""
        out = self.z.cmd("get-io-ports")
        regs = re.findall(r"^([0-9A-F]{2}):\s+([0-9A-F]{2})", out.split("AY-3-8912 chip 0:")[1], re.M)
        return bytes(int(v, 16) for _, v in regs)

    # --- cpu-step control -------------------------------------------------
    def pause(self):
        """Stop the CPU right after an ISR (main_loop's HALT wake-up): the log,
        counter and mirror are consistent there."""
        if not self.stepping:
            self.z.cmd("enter-cpu-step")
            self.z.cmd("enable-breakpoints")
            self.stepping = True
        self.z.cmd("set-breakpoint 1 PC=%d" % S["ml_wake"])
        self.run_to({S["ml_wake"]})

    def resume(self):
        for n in (1, 2, 3):
            self.z.cmd("set-breakpoint %d" % n)
        self.z.cmd("disable-breakpoints")
        self.z.cmd("exit-cpu-step")
        self.stepping = False

    def run_to(self, pcs, step_first=True):
        if step_first:
            self.z.cmd("cpu-step")            # `run` re-fires on a breakpoint PC
        for _ in range(1000):
            self.z.cmd("run 2000000")
            pc = self.pc()
            if pc in pcs:
                return pc
        raise RuntimeError("never reached %s" % pcs)

    def wait_frames(self, n, timeout=60.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.rw("tt_frames") >= n or self.rb("tt_state") != ST_PLAYING:
                return
            time.sleep(0.05)
        raise TimeoutError("frames stuck at %d" % self.rw("tt_frames"))


def songs(mem):
    """[(name, addr, request n)] in song_tab (request) order."""
    names = {v: k for k, v in S.items() if not k.startswith(("TT_", "tt_")) and "." not in k}
    out = []
    for i in range(S["TT_SONGS"]):
        e = S["song_tab"] + S["TT_ENTRY"] * i
        a = mem[e] | mem[e + 1] << 8
        out.append((names.get(a, "%04x" % a), a, i + 1))
    return out


def ram(tape):
    """$8000..code_end (code + songs) as a 64K image for wzm_ref (absolute ptrs)."""
    lo, hi = 0x8000, S["code_end"]
    mem = bytearray(65536)
    mem[lo:hi] = tape.z.read_memory(lo, hi - lo)
    return bytes(mem)


def first_diff(got, want):
    for k, (g, w) in enumerate(zip(got, want)):
        if g != w:
            return k, g.hex(), w.hex()
    return None


def ring_check(h, t, mem, name, addr, n, target, label="A", echo=0):
    """Request n, run to `target` frames, ring == oracle. Leaves the CPU paused."""
    oracle = wzm_ref.play(mem, addr, max_frames=target + 200, echo_drop=echo)
    one_shot = len(oracle) < target + 200
    t.req(n)
    t.wait_frames(target)
    t.pause()
    f, st = t.rw("tt_frames"), t.rb("tt_state")
    ring = t.z.read_memory(S["TT_LOG"], LOG_FRAMES * 14)
    k0 = max(0, f - LOG_FRAMES)
    got = [ring[(k % LOG_FRAMES) * 14:(k % LOG_FRAMES) * 14 + 14] for k in range(k0, f)]
    d = first_diff(got, oracle[k0:f])
    h.expect(f"{label}{n} {name}: frames {k0}..{f - 1} == wzm_ref", d is None and len(got) == f - k0, True) \
        or print(f"    first diff frame {k0 + d[0]}: got {d[1]} want {d[2]}" if d else "", flush=True)
    return oracle, one_shot, f, st


def stage_a(h, t, mem, song_list):
    for name, addr, n in song_list:
        target = LONG_RUN.get(name, LOG_FRAMES)
        oracle, one_shot, f, st = ring_check(h, t, mem, name, addr, n, target)
        if one_shot:
            h.expect(f"A{n} {name}: one-shot ENDED at len(oracle)", (st, f), (ST_ENDED, len(oracle)))
            t.resume()
            time.sleep(0.3)
            t.pause()
            regs = t.z.read_memory(S["pl_regs"], 14)
            c = t.chip()
            h.expect(f"A{n} {name}: after end counter holds, mirror == last oracle frame",
                     (t.rw("tt_frames"), regs) == (len(oracle), oracle[-1]), True)
            h.expect(f"A{n} {name}: after end AY volumes 0", (c[8], c[9], c[10]), (0, 0, 0))
        else:
            h.expect(f"A{n} {name}: looping song still PLAYING at {f}", st == ST_PLAYING and f >= target, True)
        t.resume()


def stage_b(h, t):
    t.req(1)
    t.wait_frames(100)
    t.req(REQ_STOP)
    time.sleep(0.2)
    t.pause()
    regs, c = t.z.read_memory(S["pl_regs"], 14), t.chip()
    h.expect("B stop: STOPPED", t.rb("tt_state"), ST_STOPPED)
    h.expect("B stop: mirror + AY volumes 0", (regs[8:11], c[8:11]), (b"\0\0\0", b"\0\0\0"))
    h.expect("B stop: AY R0..R12 == mirror", c[:13], regs[:13])
    t.resume()


def press(t, row, mask):
    rows = ["ff"] * 8
    order = [0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F]
    rows[order.index(row)] = "%02x" % (0xFF ^ mask)
    t.z.cmd("set-ui-io-ports " + "".join(rows) + "00")
    time.sleep(0.15)
    t.z.cmd("set-ui-io-ports ffffffffffffffff00")
    time.sleep(0.15)


def stage_c(h, t):
    press(t, 0xEF, 0x10)                          # '6': organ Game Over
    h.expect("C key 6: song 6 playing", (t.rb("tt_song"), t.rb("tt_state") in (ST_PLAYING, ST_ENDED)), (6, True))
    press(t, 0x7F, 0x01)                          # SPACE
    h.expect("C SPACE: STOPPED", t.rb("tt_state"), ST_STOPPED)
    press(t, 0xFB, 0x01)                          # 'Q': harpsichord Dungeon Crawl
    h.expect("C key Q: song 8 playing", (t.rb("tt_song"), t.rb("tt_state")), (8, ST_PLAYING))
    time.sleep(0.5)
    f0 = t.rw("tt_frames")
    press(t, 0xBF, 0x02)                          # 'L': restart
    ptr = t.rw("pl_voice_a")                      # VO_PTR: inside hps_dungeon_crawl
    h.expect("C key L: song 8 restarted",
             (t.rb("tt_song"), t.rb("tt_state"), t.rw("tt_frames") < f0,
              S["hps_dungeon_crawl"] <= ptr < S["hps_dungeon_crawl_end"]),
             (8, ST_PLAYING, True, True))
    press(t, 0xEF, 0x02)                          # '9': S1d tsx Lament 96
    h.expect("C key 9: song 16 playing", (t.rb("tt_song"), t.rb("tt_state")), (16, ST_PLAYING))
    for key, (row, mask), n in (("0", (0xEF, 0x01), 17), ("I", (0xDF, 0x04), 18),
                                ("O", (0xDF, 0x02), 19), ("P", (0xDF, 0x01), 20)):
        press(t, row, mask)
        h.expect(f"C key {key}: song {n} playing", (t.rb("tt_song"), t.rb("tt_state")), (n, ST_PLAYING))


def gates(t, name):
    """{(+5, +6)} gate bytes of the 3 voices' instruments of a song."""
    hdr = t.z.read_memory(S[name], 16)
    out = set()
    for v in range(3):
        i = hdr[6 + v]
        ip = hdr[10 + 2 * i] | hdr[11 + 2 * i] << 8
        out.add(tuple(t.z.read_memory(ip + 5, 2)))
    return out


def stage_e(h, t):
    """G key on the organ Lament (request 7): 56 -> 62 -> 100 -> 30 -> 45 -> 56."""
    name, n = "org_lament", 7
    t.req(n)
    time.sleep(0.2)
    h.expect("E default gate 56 %", gates(t, name), {GATE_BYTES[56]})
    for g in (62, 100, 30, 45, 56):
        press(t, 0xFD, 0x10)                      # 'G'
        h.expect(f"E key G: gate {g} %, song {n} restarted",
                 (gates(t, name), t.rb("tt_song"), t.rb("tt_state")),
                 ({GATE_BYTES[g]}, n, ST_PLAYING))
        t.pause()
        mem = ram(t)
        t.resume()
        ring_check(h, t, mem, name, S[name], n, 600, label=f"E{g}-")
        t.resume()


def tails(t, name):
    """[(drop, rel_per)] of voice A/B/C's instruments of a song."""
    hdr = t.z.read_memory(S[name], 16)
    out = []
    for v in range(3):
        i = hdr[6 + v]
        ip = hdr[10 + 2 * i] | hdr[11 + 2 * i] << 8
        b = t.z.read_memory(ip + 4, 4)
        out.append((b[0], b[3]))
    return out


def stage_f(h, t):
    """H key: reverb S1e -> 0 -> 50 -> 100 -> S1e on the organ and harpsichord Lament
    (bytes == abc2wzm.inst_tail, ring == oracle on the patched bytes); a dry entry
    (8: tsx Lament) is left untouched."""
    for name, n in (("org_lament", 7), ("hps_lament", 14)):
        imap = abc2wzm.instr_map("organ-rev" if name[0] == "o" else "harp-rev")
        t.req(n)
        time.sleep(0.2)
        h.expect(f"F {name}: default reverb S1e",
                 tails(t, name), [abc2wzm.inst_tail(i, "s1e") for i in imap])
        for lv in (0, 50, 100, "s1e"):
            press(t, 0xBF, 0x10)                  # 'H'
            h.expect(f"F key H: {name} reverb {lv}, restarted",
                     (tails(t, name), t.rb("tt_song"), t.rb("tt_state")),
                     ([abc2wzm.inst_tail(i, lv) for i in imap], n, ST_PLAYING))
            if lv != "s1e":
                t.pause()
                mem = ram(t)
                t.resume()
                ring_check(h, t, mem, name, S[name], n, 400, label=f"F{lv}-")
                t.resume()
    t.req(15)
    time.sleep(0.2)
    before = tails(t, "lament_tsx")
    press(t, 0xBF, 0x10)
    h.expect("F key H on a dry entry: tails unchanged", tails(t, "lament_tsx"), before)


def stage_g(h, t):
    """J key (WZM_ECHO experiment): pl_edrop off -> 6 -> 4 -> 2 -> off (global, the song
    restarts); for each level the ring == wzm_ref(echo_drop) on the organ Lament IIb
    (buzzer voice, staccato) and the legato Lament II (tsx, 96)."""
    h.expect("G echo off by default", t.rb("pl_edrop"), 0)
    for name, n in (("org_lament", 7), ("lament2_tsx_96", 20)):
        t.req(n)
        time.sleep(0.2)
        mem = ram(t)
        for drop in (6, 4, 2, 0):
            press(t, 0xBF, 0x08)                  # 'J'
            h.expect(f"G key J: echo drop {drop}, song {n} restarted",
                     (t.rb("pl_edrop"), t.rb("tt_song"), t.rb("tt_state")),
                     (drop, n, ST_PLAYING))
            if drop:
                ring_check(h, t, mem, name, S[name], n, 500, label=f"G{drop}-", echo=drop)
                t.resume()


def stage_d(h, t, mem, song_list, nframes):
    allt = []
    worst = (0, "")
    pair = (0, "")                                # max T over two adjacent frames
    t.pause()
    t.z.cmd("set-breakpoint 1")
    t.z.cmd("set-breakpoint 2 PC=%d" % S["tt_isr_pf"])
    t.z.cmd("set-breakpoint 3 PC=%d" % S["tt_isr_pf_ret"])
    for name, addr, n, *ex in song_list:
        echo = ex[0] if ex else 0
        if ECHO:
            t.h.write_byte(S["pl_edrop"], echo)
        oracle = wzm_ref.play(mem, addr, max_frames=nframes, echo_drop=echo)
        t.req(n, wait=False)
        ts, bad = [], None
        for k in range(len(oracle)):
            t.run_to({S["tt_isr_pf"]})
            t.z.cmd("reset-tstates-partial")
            t.run_to({S["tt_isr_pf_ret"]})
            ts.append(int(t.z.cmd("get-tstates-partial")))
            c = t.chip()
            if bad is None and c[:13] != oracle[k][:13]:
                bad = (k, c[:13].hex(), oracle[k][:13].hex())
        h.expect(f"D{n} {name}: AY chip R0..R12 == wzm_ref, {len(oracle)} frames", bad is None, True) \
            or print(f"    first diff frame {bad[0]}: chip {bad[1]} want {bad[2]}" if bad else "", flush=True)
        # frame 0 of a song is preceded by player_start in the same ISR (not timed here)
        p2 = max((ts[k] + ts[k + 1], k) for k in range(len(ts) - 1))
        print(f"    T/frame {name}: median {statistics.median(ts):.0f} mean {statistics.mean(ts):.0f}"
              f" max {max(ts)} (frame {ts.index(max(ts))}) min {min(ts)};"
              f" pair max {p2[0]} (frames {p2[1]}+{p2[1] + 1})", flush=True)
        allt += ts
        if max(ts) > worst[0]:
            worst = (max(ts), f"{name} frame {ts.index(max(ts))}")
        if p2[0] > pair[0]:
            pair = (p2[0], f"{name} frames {p2[1]}+{p2[1] + 1}")
    t.resume()
    print(f"T/frame all songs ({len(allt)} frames): median {statistics.median(allt):.0f}"
          f" mean {statistics.mean(allt):.0f} worst {worst[0]} ({worst[1]});"
          f" adjacent-pair max {pair[0]} ({pair[1]})", flush=True)
    return worst[0]


def main():
    nframes = 256                                 # ~0.075 s a frame; 1024 = full (~17 min)
    if "--timing-frames" in sys.argv:
        nframes = int(sys.argv[sys.argv.index("--timing-frames") + 1])
    tmp = tempfile.mkdtemp(prefix="music_test_")
    sna = os.path.join(tmp, "music_test.sna")     # private copy: a rebuild can't tear it
    shutil.copy(SNA, sna)
    try:
        with CountingHarness() as h:
            h.launch(EMU_ARGS)
            h.load(sna, settle=0.5)
            t = Tape(h)
            h.expect("boot: IDLE, no song", (t.rb("tt_state"), t.rb("tt_song")), (ST_IDLE, 0))
            mem = ram(t)
            song_list = songs(mem)
            stage_a(h, t, mem, song_list)
            stage_b(h, t)
            stage_c(h, t)
            stage_e(h, t)
            stage_f(h, t)
            if ECHO:
                stage_g(h, t)
            else:
                print("(game configuration: no WZM_ECHO, stage G skipped)", flush=True)
            if "--skip-timing" not in sys.argv:
                extra = [("org_lament+echo100", S["org_lament"], 7, 2),
                         ("lament2_tsx_96+echo100", S["lament2_tsx_96"], 20, 2)]
                stage_d(h, t, ram(t), song_list + (extra if ECHO else []), nframes)
            print(f"music_player: {'PASS' if h.ok else 'FAIL'} ({h.n_checks - len(h.failures)}/"
                  f"{h.n_checks} checks passed)"
                  + ("" if h.ok else ": " + ", ".join(h.failures)), flush=True)
            return 0 if h.ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
