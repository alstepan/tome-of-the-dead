#!/usr/bin/env python3
"""wzm_ref.py - reference WZM player: song bytes -> per-frame 14-byte AY register image.
Test oracle for the Z80 player (WZM v0.2 format: see tools/abc2wzm.py docstring).
Register image: R0..R5 tone A/B/C fine/coarse, R6 noise=0, R7 mixer = song header +9,
R8..R10 volume, R11/R12 envelope period (0 unless the voice-C buzzer ran: then
(TP_C + 8) >> 4 of the last buzzer frame), R13=$FF (not tracked per frame)."""
import hashlib
import math
import sys

AY_CLK = 1773400
PITCH_BASE = 12
ENV_BIT = 0x10      # volume bit 4: AY envelope mode (voice-C buzzer, v0.2)


def period(idx):
    f = 440.0 * 2 ** ((idx + PITCH_BASE - 69) / 12.0)
    return max(1, min(4095, int(AY_CLK / (16.0 * f) + 0.5)))


TP = [period(i) for i in range(0x60)]


def _w(b, o):
    return b[o] | (b[o + 1] << 8)


class Inst:
    def __init__(self, b, o):
        self.arp0, self.loop, self.per, self.dep, self.rel, s1p, s2d = b[o:o + 7]
        if not (1 <= s1p and 1 <= s2d and s1p - 1 + s2d <= 7):
            raise ValueError("bad gate shifts %d/%d" % (s1p, s2d))
        self.s1, self.s2 = s1p - 1, s1p - 1 + s2d
        v = []
        o += 7
        while b[o] != 0xFF:
            v.append(b[o])
            o += 1
        self.vols = v

    def table(self, e):
        n = len(self.vols)
        if e < n:
            return self.vols[e]
        if self.loop == 0xFF:
            return self.vols[-1]
        return self.vols[self.loop + (e - n) % (n - self.loop)]

    def sustain(self, e):
        v = self.table(e)
        if self.per and (e % self.per) >= self.per // 2:
            v -= self.dep
        return max(0, v)

    def gate(self, dur, stac):
        return (dur >> self.s1) - (dur >> self.s2) if stac else dur


class Voice:
    """State machine of one voice, same state as the Z80 player (pl_voice/pl_fetch)."""

    def __init__(self, blob, ptr, inst):
        self.b, self.ptr, self.inst = blob, ptr, inst
        self.rem = 0
        self.t = 0
        self.pitch = 0
        self.rest = True
        self.stac = False
        self.done = False
        self.attack = False   # this event's frame 0 uses pitch + arp0
        self.env = None       # envelope time e (sustain frames since the last attack)
        self.gate = 0         # sustain frames left
        self.last = 0         # last output volume (release starts from it)

    def fetch(self):
        b = self.b
        leg = False
        for _ in range(1000):
            c = b[self.ptr]
            if c < 0x60:
                self.pitch, dur, self.rest = c, b[self.ptr + 1], False
                self.ptr += 2
                if leg:
                    if self.env is None:
                        raise ValueError("$85 legato before the first note")
                    self.attack = False
                else:
                    self.attack, self.env = True, 0
                self.gate = self.inst.gate(dur, self.stac)
                break
            if c == 0x60:
                if leg:
                    raise ValueError("$85 legato before a rest")
                dur, self.rest, self.attack = b[self.ptr + 1], True, False
                self.ptr += 2
                break
            if c == 0x80:
                self.ptr = _w(b, self.ptr + 1)
            elif c == 0x81:
                self.done = True
                return
            elif c in (0x82, 0x83):
                self.stac = c == 0x82
                self.ptr += 1
            elif c == 0x85:
                leg = True
                self.ptr += 1
            else:
                raise ValueError("bad stream byte %02x" % c)
        else:
            raise ValueError("stream without notes")
        self.rem, self.t = dur, 0

    def frame(self):
        """-> (period, volume)"""
        if self.done:
            return TP[self.pitch], 0
        if self.rem == 0:
            self.fetch()
            if self.done:
                return TP[self.pitch], 0
        idx = self.pitch + (self.inst.arp0 if self.t == 0 and self.attack else 0)
        if self.rest:
            vol = 0
        elif self.gate:
            self.gate -= 1
            vol = self.last = self.inst.sustain(self.env)
            self.env += 1
        else:
            vol = self.last = max(0, self.last - self.inst.rel)
        self.t += 1
        self.rem -= 1
        return TP[min(idx, 0x5F)], vol


def play(blob, base=0, max_frames=3000):
    """Return list of 14-byte register images, stops when every voice has ended."""
    sp = [_w(blob, base + 2 * i) for i in range(3)]
    ii = [blob[base + 6 + i] for i in range(3)]
    mixer = blob[base + 9]
    voices = [Voice(blob, sp[i], Inst(blob, _w(blob, base + 10 + 2 * ii[i]))) for i in range(3)]
    out = []
    env = 0
    while len(out) < max_frames and not all(v.done for v in voices):
        r = [v.frame() for v in voices]
        regs = [0] * 14
        for i, (p, vol) in enumerate(r):
            regs[2 * i], regs[2 * i + 1] = p & 255, p >> 8
            regs[8 + i] = vol
        if r[2][1] & ENV_BIT:
            env = (r[2][0] + 8) >> 4          # buzzer: envelope period of voice C
        regs[11], regs[12] = env & 255, env >> 8
        regs[7] = mixer
        regs[13] = 0xFF
        out.append(bytes(regs))
    return out


def stream_hash(regs):
    return hashlib.sha256(b"".join(regs)).hexdigest()


def write_psg(regs, path):
    """Minimal .psg export (Vortex/AY-Emul): header + per-frame register writes."""
    with open(path, "wb") as f:
        f.write(b"PSG\x1a" + bytes([0, 0]) + bytes(10))
        prev = [None] * 14
        for fr in regs:
            f.write(b"\xff")
            for r in range(13):
                if fr[r] != prev[r]:
                    f.write(bytes([r, fr[r]]))
                    prev[r] = fr[r]


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import abc2wzm
    info = abc2wzm.convert(sys.argv[1])
    regs = play(info["bytes"])
    print(len(regs), "frames", stream_hash(regs))
