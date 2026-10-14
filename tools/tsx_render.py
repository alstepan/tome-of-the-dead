#!/usr/bin/env python3
"""Offline re-implementation of the browser player's audio path.

Ground truth: assets/sfx/concepts/player-js/main.tsx (untracked, main checkout).
Signal path replicated (line numbers refer to that file):

  osc(A/B/C) -> gain -> StereoPanner -> BiquadLowpass(Q 0.7 dB) -+-> dry gain -+
                                                                  +-> Convolver -> wet gain -+-> master -> out

  * oscillator types per mode         l.1033-1069 (organ: saw/square/tri, harpsichord: saw x3)
  * AY volume table, levels 13/13/14  l.809, l.1212-1214, x0.28 gain scale (l.1206)
  * staccato gate: level 0 at progress > 0.45 (l.1199-1204)
  * setTargetAtTime smoothing: gain/freq tau 6 ms, rest gain tau 5 ms (l.1187-1207)
  * control loop = requestAnimationFrame, modelled at exactly 60 Hz (735 samples @44.1k)
  * lowpass 8000/9500 Hz, Q 0.7 *dB* (WebAudio lowpass Q is in dB) (l.1043, 1052)
  * convolver: 2.8 s stereo white noise * exp(-2t) (l.946-962), normalize=true
    (Chromium calibration 0.00125/rms), per-channel (2ch IR, 2ch input)
  * dry = max(0.3, 1 - wet/2), wet = reverb (l.1080-1083); master 0.85 (l.830)
  * panning ACB: A -0.75, C 0, B +0.75 (l.1015-1019), equal-power StereoPanner law

Not replicated: browser float32 internals, AudioContext 128-frame block
quantisation of currentTime, rAF jitter, Chromium's exact PeriodicWave
band-limiting (PolyBLEP used instead), the ~20-50 ms startup transients of
the initial dry/wet/filter setTargetAtTime ramps.
"""
import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
CTRL_HZ = 60
SPF = SR // CTRL_HZ  # 735 samples per control frame
AY_VOL_TABLE = [0.0, 0.007, 0.011, 0.016, 0.024, 0.035, 0.051, 0.075,
                0.110, 0.160, 0.235, 0.345, 0.505, 0.740, 0.880, 1.0]
BASE_LEVEL = {"A": 13, "B": 13, "C": 14}
GAIN_SCALE = 0.28
TAU_NOTE = 0.006
TAU_REST = 0.005
STAC_CUT = 0.45
MASTER = 0.85
IR_SECONDS = 2.8
MODES = {  # osc types A,B,C ; lowpass Hz
    "organ": (("saw", "square", "tri"), 8000.0),
    "harpsichord": (("saw", "saw", "saw"), 9500.0),
    "ay": (("square", "square", "square"), 6500.0),
}
PAN = {"ACB": {"A": -0.75, "B": 0.75, "C": 0.0},
       "ABC": {"A": -0.75, "B": 0.0, "C": 0.75},
       "MONO": {"A": 0.0, "B": 0.0, "C": 0.0}}
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets/sfx/music/src"
OUT = ROOT / "assets/sfx/music/renders"


def default_bpm(json_bpm):
    """Slider max is 96; tunes above it (boss_fight, 106) keep their own."""
    return max(96, json_bpm)


# ---------------------------------------------------------------- control
def build_timeline(notes):
    t, starts, ends = 0.0, [], []
    for n in notes:
        starts.append(t)
        t += n["beats"]
        ends.append(t)
    return np.array(starts), np.array(ends), t


def frame_targets(notes, ch, bpm, nframes):
    """Per-frame (freq_target or nan, gain_target, tau) as the tsx loop sets them."""
    starts, ends, _ = build_timeline(notes)
    freq = np.full(nframes, np.nan)
    gain = np.zeros(nframes)
    tau = np.full(nframes, TAU_REST)
    for k in range(nframes):
        beat = k / CTRL_HZ * bpm / 60.0
        i = int(np.searchsorted(starts, beat, side="right")) - 1
        if i < 0 or i >= len(notes) or beat >= ends[i]:
            continue  # no note: gain 0, tau 0.005
        n = notes[i]
        if n["pitch"] == "R":
            continue
        freq[k] = 440.0 * 2.0 ** ((n["midi"] - 69) / 12.0)
        level = BASE_LEVEL[ch]
        if n.get("stac") and (beat - starts[i]) / n["beats"] > STAC_CUT:
            level = 0
        gain[k] = AY_VOL_TABLE[level] * GAIN_SCALE
        tau[k] = TAU_NOTE
    return freq, gain, tau


def settarget_track(targets, taus, init):
    """setTargetAtTime re-issued once per control frame; NaN target = no call.
    v(t) = tgt + (v0 - tgt) * exp(-(t - T)/tau), v0 = value at the call."""
    out = np.empty(len(targets) * SPF)
    v = init
    n = np.arange(SPF)
    tgt, tau = v, TAU_NOTE
    for k in range(len(targets)):
        if not math.isnan(targets[k]):
            tgt, tau = targets[k], taus[k]
        seg = tgt + (v - tgt) * np.exp(-n / (tau * SR))
        out[k * SPF:(k + 1) * SPF] = seg
        v = tgt + (v - tgt) * math.exp(-SPF / (tau * SR))
    return out


# ------------------------------------------------------------- oscillator
def _blep(t, dt):
    """PolyBLEP residual for a step of height 2 at t=0 (t in [0,1))."""
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    x = (t[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def oscillator(kind, freq):
    """WebAudio-phased waveforms (sine-aligned), amplitude +-1, from per-sample Hz."""
    dt = freq / SR
    p = np.mod(np.cumsum(dt), 1.0)
    if kind == "tri":
        return 1.0 - 4.0 * np.abs(np.mod(p + 0.25, 1.0) - 0.5)
    if kind == "square":
        s = np.where(p < 0.5, 1.0, -1.0)
        return s + _blep(p, dt) - _blep(np.mod(p + 0.5, 1.0), dt)
    # saw: 0 at phase 0 rising to +1 at 0.5, jump to -1 (phase 0.5)
    q = np.mod(p + 0.5, 1.0)
    return 2.0 * q - 1.0 - _blep(q, dt)


def panner_gains(pan):
    x = (pan + 1.0) / 2.0
    return math.cos(x * math.pi / 2), math.sin(x * math.pi / 2)


# ------------------------------------------------------------ filter / fx
def lowpass_ir(fc, q_db, n=8192):
    w0 = 2 * math.pi * fc / SR
    alpha = math.sin(w0) / (2 * 10 ** (q_db / 20))
    c = math.cos(w0)
    b = np.array([(1 - c) / 2, 1 - c, (1 - c) / 2])
    a = np.array([1 + alpha, -2 * c, 1 - alpha])
    b, a = b / a[0], a / a[0]
    h = np.zeros(n)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        x0 = 1.0 if i == 0 else 0.0
        y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        h[i] = y0
        x2, x1, y2, y1 = x1, x0, y1, y0
    return h


def fftconv(x, h):
    n = len(x) + len(h) - 1
    nf = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(h, nf), nf)[:n]


def make_ir(seed):
    """tsx l.946-962 + Chromium ConvolverNode normalisation (normalize=true)."""
    rng = np.random.default_rng(seed)
    length = int(SR * IR_SECONDS)
    env = np.exp(-(np.arange(length) / SR) * 2.0)
    ir = (rng.random((2, length)) * 2 - 1) * env
    power = math.sqrt(float(np.sum(ir ** 2)) / (2 * length))
    if not math.isfinite(power) or power < 0.000125:
        power = 1.0
    ir *= (1.0 / power) * 0.00125 * (44100.0 / SR)
    return ir


# ---------------------------------------------------------------- render
def render(tune, mode="organ", bpm=None, reverb=1.0, pan="ACB", seed=1, master=MASTER):
    data = json.loads((SRC / f"{tune}.json").read_text())
    bpm = bpm or default_bpm(data["bpm"])
    kinds, fc = MODES[mode]
    total = max(build_timeline(data["voices"][c])[2] for c in "ABC")
    music_frames = int(math.ceil(total * 60.0 / bpm * CTRL_HZ))
    tail_frames = int(math.ceil(IR_SECONDS * CTRL_HZ))
    nframes = music_frames + tail_frames
    left = np.zeros(nframes * SPF)
    right = np.zeros(nframes * SPF)
    for ch, kind in zip("ABC", kinds):
        f, g, tau = frame_targets(data["voices"][ch], ch, bpm, music_frames)
        f = np.concatenate([f, np.full(tail_frames, np.nan)])
        g = np.concatenate([g, np.zeros(tail_frames)])
        tau = np.concatenate([tau, np.full(tail_frames, TAU_REST)])
        fs = settarget_track(f, tau, 440.0)
        gs = settarget_track(g, tau, 0.0)
        sig = oscillator(kind, fs) * gs
        gl, gr = panner_gains(PAN[pan][ch])
        left += sig * gl
        right += sig * gr
    h = lowpass_ir(fc, 0.7)
    left, right = fftconv(left, h)[:len(left)], fftconv(right, h)[:len(right)]
    if mode == "ay":
        wet, dry = 0.0, 1.0
    else:
        wet = reverb
        dry = max(0.3, 1.0 - wet * 0.5)
    out = dry * np.stack([left, right])
    if wet > 0:
        ir = make_ir(seed)
        out += wet * np.stack([fftconv(left, ir[0])[:len(left)],
                               fftconv(right, ir[1])[:len(right)]])
    return out * master, bpm, total


def write_wav(path, stereo):
    pcm = np.clip(np.round(stereo.T * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tunes", nargs="*", help="tune names (default: all)")
    ap.add_argument("--mode", choices=list(MODES) + ["both"], default="both")
    ap.add_argument("--bpm", type=float, help="override (default 96; boss_fight 106)")
    ap.add_argument("--reverb", type=float, default=1.0, help="0..1 (tsx reverbMix)")
    ap.add_argument("--pan", choices=list(PAN), default="ACB")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    tunes = a.tunes or sorted(p.stem for p in SRC.glob("*.json"))
    modes = ["organ", "harpsichord"] if a.mode == "both" else [a.mode]
    a.out.mkdir(parents=True, exist_ok=True)
    for t in tunes:
        for m in modes:
            st, bpm, _ = render(t, m, a.bpm, a.reverb, a.pan, a.seed)
            peak = float(np.max(np.abs(st)))
            norm = ""
            if peak > 1.0:  # the browser would hard-clip; normalise instead
                st = st / peak * 0.999
                norm = f" NORMALISED(x{1 / peak:.3f})"
            rms = float(np.sqrt(np.mean(st ** 2)))
            p = a.out / f"{t}_{m}.wav"
            write_wav(p, st)
            print(f"{p.name}: bpm={bpm:g} dur={st.shape[1] / SR:.2f}s "
                  f"peak={peak:.3f} rms={rms:.4f}{norm}")


if __name__ == "__main__":
    sys.exit(main())
