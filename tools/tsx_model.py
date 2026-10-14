#!/usr/bin/env python3
"""tsx_model.py - the user's browser player (assets/sfx/concepts/player-js/main.tsx, the
ground truth) sampled at 50 Hz, and a comparison of a WZM register stream against it.

tsx gain model (main.tsx l.1178-1214; HARPSICHORD mode l.1049-1057 only changes the
oscillator to sawtooth on all 3 voices, not the gain): a sounding note is held at
AY_VOL_TABLE[13] (V1, V2) / [14] (V3) for its whole length - no decay, no tremolo, no
re-attack (the frequency glides, the gain stays); a staccato note drops to level 0 once
its progress (beat - start) / duration exceeds 0.45; a rest is level 0.

Sampling: frame k shows the tsx state at time (k + 1/2) frames, a note owning
(start, end] - so a note boundary lands on round-half-up(exact frame), the same as
tools/abc2wzm.py's cumulative boundary rounding.

CLI: python3 -I tools/tsx_model.py   (every JSON tune with its batch instrument; prints
gate / level / pitch agreement and the loudness figures - no emulator needed)
"""
import json
import math
import os
import sys
from fractions import Fraction

AY_VOL_TABLE = [0.0, 0.007, 0.011, 0.016, 0.024, 0.035, 0.051, 0.075,
                0.110, 0.160, 0.235, 0.345, 0.505, 0.740, 0.880, 1.0]   # main.tsx l.809
BASE_LEVEL = (13, 13, 14)
STAC_CUT = Fraction(45, 100)
VOICES = ("A", "B", "C")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def notes(j):
    """-> per voice [(start, end, midi|None, stac)] in beats (Fractions)."""
    out = []
    for k in VOICES:
        t, lst = Fraction(0), []
        for n in j["voices"][k]:
            d = Fraction(n["beats"]).limit_denominator(64)
            lst.append((t, t + d, n["midi"], bool(n["stac"])))
            t += d
        out.append(lst)
    return out


def frames_per_beat(j, bpm=None):
    return Fraction(3000) / Fraction(bpm if bpm is not None else j["bpm"])


def model(j, bpm=None):
    """-> (frames, owner): frames[k][v] = (midi|None, level); owner[k][v] = note index.
    One pass of the tune (round-half-up(total beats x frames per beat) frames)."""
    fpb = frames_per_beat(j, bpm)
    ns = notes(j)
    total = ns[0][-1][1]
    nfr = math.floor(total * fpb + Fraction(1, 2))
    frames, owner = [], []
    idx = [0, 0, 0]
    for k in range(nfr):
        s = (k + Fraction(1, 2)) / fpb
        row, own = [], []
        for v in range(3):
            while ns[v][idx[v]][1] < s:
                idx[v] += 1
            st, en, midi, stac = ns[v][idx[v]]
            if midi is None:
                lvl = 0
            elif stac and (s - st) / (en - st) > STAC_CUT:
                lvl = 0
            else:
                lvl = BASE_LEVEL[v]
            row.append((midi, lvl))
            own.append(idx[v])
        frames.append(row)
        owner.append(own)
    return frames, owner


def tsx_loudness(j):
    """Continuous tsx figures: mean amplitude of a legato note and of a staccato note
    (per-note means over all voices; a staccato note sounds 45 % of its length)."""
    leg, sta = [], []
    for v, lst in enumerate(notes(j)):
        a = AY_VOL_TABLE[BASE_LEVEL[v]]
        for _, _, midi, stac in lst:
            if midi is not None:
                (sta if stac else leg).append(a * float(STAC_CUT) if stac else a)
    return _mean(leg), _mean(sta)


def _mean(x):
    return sum(x) / len(x) if x else None


def amp(vol):
    """AY volume register -> tsx amplitude (envelope mode counts as full level 15)."""
    return 1.0 if vol & 0x10 else AY_VOL_TABLE[vol & 15]


def compare(j, regs, bpm=None, tp=None):
    """WZM register frames vs the model over one pass.  Returns a dict:
    frames, pitch_bad (sounding frames whose period != TP[midi-12], tp given),
    level_bad (frames whose volume != model level; envelope mode = on), gate_diffs
    {wzm - model sounding frames: count} per staccato note, leg/stac per-note mean
    amplitude of the WZM stream (and of the 50 Hz model)."""
    fr, owner = model(j, bpm)
    ns = notes(j)
    res = {"frames": len(fr), "pitch_bad": 0, "level_bad": 0, "gate_diffs": {}}
    per = {}          # (v, note) -> [model_on, wzm_on, n, model_amp_sum, wzm_amp_sum]
    for k, row in enumerate(fr):
        r = regs[k]
        for v, (midi, lvl) in enumerate(row):
            vol = r[8 + v]
            on = vol != 0
            want = lvl if not (vol & 0x10) else (BASE_LEVEL[v] if lvl else 0)
            if (vol if not (vol & 0x10) else (BASE_LEVEL[v] if on else 0)) != want:
                res["level_bad"] += 1
            if tp is not None and lvl and on:
                p = r[2 * v] | r[2 * v + 1] << 8
                if p != tp[midi - 12]:
                    res["pitch_bad"] += 1
            e = per.setdefault((v, owner[k][v]), [0, 0, 0, 0.0, 0.0])
            e[0] += lvl > 0
            e[1] += on
            e[2] += 1
            e[3] += AY_VOL_TABLE[lvl]
            e[4] += amp(vol)
    leg, sta, mleg, msta = [], [], [], []
    for (v, i), (m_on, w_on, n, ma, wa) in per.items():
        _, _, midi, stac = ns[v][i]
        if midi is None:
            continue
        if stac:
            d = w_on - m_on
            res["gate_diffs"][d] = res["gate_diffs"].get(d, 0) + 1
            sta.append(wa / n)
            msta.append(ma / n)
        else:
            leg.append(wa / n)
            mleg.append(ma / n)
    res["leg"], res["stac"] = _mean(leg), _mean(sta)
    res["model_leg"], res["model_stac"] = _mean(mleg), _mean(msta)
    return res


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import abc2wzm
    import wzm_ref
    for name, tune, kw in abc2wzm.BATCH:
        p = os.path.join(abc2wzm.SRC_DIR, tune + ".json")
        j = load(p)
        info = abc2wzm.convert(p, name=name, source="json", **kw)
        bpm = kw.get("bpm")
        n = model(j, bpm)[0]
        regs = wzm_ref.play(info["bytes"], max_frames=len(n))
        c = compare(j, regs, bpm, wzm_ref.TP)
        tl, ts = tsx_loudness(j)
        print("%-20s %5d fr  pitch_bad %d  level_bad %d  gate wzm-model %s  "
              "leg %.3f stac %s (tsx %.3f / %s)"
              % (name, c["frames"], c["pitch_bad"], c["level_bad"],
                 dict(sorted(c["gate_diffs"].items())), c["leg"],
                 "%.3f" % c["stac"] if c["stac"] else "-", tl,
                 "%.3f" % ts if ts else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
