#!/usr/bin/env python3
"""abc_audit.py - per-note decode table of an ABC file as tools/abc2wzm.py reads it.

  python3 tools/abc_audit.py FILE.abc [--accidentals strict|naturals] [--transpose N]
                             [--instr harpsichord|organ] [--fpe N] [--only-flagged]

One row per (tie-merged) note: voice, bar.beat (beat in eighths from 1), source token,
decoded pitch (MIDI + name), heard pitch after --transpose (default -12 = the tape's
batch), AY period from the player table, actual frequency on a 128K (1.7734475 MHz) and
the cents error vs equal temperament, the arp0 transient pitch of the instrument's first
frame, frames, articulation (. staccato, ~ slurred into next) and decode flags:
  key           bare note took the key signature (alt = the other e/d reading)
  in-bar acc    bare note took an accidental from earlier in the same bar (ABC 2.1)
  tie carries   tied note kept its accidental across a bar line
  digit-oct d   short-melodies octave digit (C3 = MIDI 60 numbering); alt sci-oct =
                the same digit read as scientific octave (an octave lower)
  CASE/DIGIT CONFLICT  the letter case says another octave than the digit (alt case-oct)
Rows with a flag are marked '*'. A summary lists every flagged token and the period
table error extremes."""
import argparse
import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import abc2wzm as a2w  # noqa: E402
import wzm_ref  # noqa: E402

CLK_128 = 1773447.5
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def name(m):
    return "-" if m is None else "%s%d" % (NAMES[m % 12], m // 12 - 1)


def ay(m, clk=CLK_128):
    """-> (TP, Hz, cents error) for MIDI m played through the player table."""
    idx = min(max(m - a2w.PITCH_BASE, 0), 0x5F)
    tp = wzm_ref.TP[idx]
    f = clk / (16.0 * tp)
    want = 440.0 * 2 ** ((m - 69) / 12.0)
    return tp, f, 1200.0 * __import__("math").log2(f / want)


def audit(path, accidentals="strict", transpose=-12, instr="harpsichord", fpe=None,
          only_flagged=False, out=sys.stdout):
    info = a2w.convert(path, accidentals=accidentals, transpose=transpose, instr=instr,
                       fpe=Fraction(fpe) if fpe else None)
    t = info["tune"]
    arp0 = a2w.INSTRUMENTS[instr][0]
    print("# %s  (mtime %s)" % (path, __import__("time").ctime(os.path.getmtime(path))), file=out)
    print("# T:%s  K:%s  keysig %s  Q=%s  fpe=%d  transpose %+d  instr %s  accidentals %s"
          % (t["title"], t["key"], t["keysig"], t["q"], info["fpe"], transpose, instr,
             accidentals), file=out)
    flagged, worst = [], (0.0, "")
    for vi, vn in enumerate(info["voice_names"]):
        v = t["voices"][vn]
        if v["mangled"]:
            print("# %s: no bar lines -> bars every M:%s, octave-digit decode" % (vn, t["m"]),
                  file=out)
        if v["dropped"]:
            print("# %s: dropped chord symbols/decorations: %s" % (vn, v["dropped"]), file=out)
        print("%-3s %-6s %-10s %-11s %-11s %5s %8s %6s %-11s %4s %-2s %s" % (
            "V", "bar.bt", "token", "decoded", "heard", "TP", "Hz", "cents", "arp0 frame",
            "fr", "ar", "flags / alt readings"), file=out)
        for n, ev in zip(v["notes"], info["events"][vi]):
            m = n["midi"]
            beat = 1 + n["at"] / Fraction(1, 8)
            bb = "%d.%s" % (n["bar"], str(beat) if beat.denominator > 1 else int(beat))
            art = ("." if ev[2] else "") + ("~" if ev[3] else "")
            if m is None:
                row = (vn, bb, n["tok"], "rest", "", "", "", "", "", ev[1], art, "")
            else:
                h = m + transpose
                tp, f, c = ay(h)
                if abs(c) > abs(worst[0]):
                    worst = (c, "%s %s %s" % (vn, bb, name(h)))
                arp = ""
                if arp0:
                    hp = h + arp0
                    clamp = " CLAMP" if hp - a2w.PITCH_BASE > 0x5F else ""
                    arp = name(min(hp, 0x5F + a2w.PITCH_BASE)) + clamp
                alts = ", ".join("%s=%s" % (k, name(x + 0)) for k, x in n["alt"])
                fl = "; ".join(n["why"]) + (" | " + alts if alts else "")
                row = (vn, bb, n["tok"], "%d %s" % (m, name(m)), "%d %s" % (h, name(h)),
                       tp, "%.1f" % f, "%+.1f" % c, arp, ev[1], art, fl)
                if n["why"]:
                    flagged.append((vn, bb, n["tok"], name(m), fl))
            if only_flagged and not row[-1]:
                continue
            print("%s%-3s %-6s %-10s %-11s %-11s %5s %8s %6s %-11s %4s %-2s %s"
                  % ((("*" if row[-1] else " "),) + row), file=out)
    kinds = {}
    for f in flagged:
        k = f[4].split(" | ")[0]
        kinds[k] = kinds.get(k, 0) + 1
    print("# flagged %d notes: %s" % (len(flagged), kinds), file=out)
    print("# worst period error in this tune: %+.1f cents (%s)" % worst, file=out)
    return flagged


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("abc", nargs="+")
    ap.add_argument("--accidentals", choices=("strict", "naturals"), default="strict")
    ap.add_argument("--transpose", type=int, default=-12)
    ap.add_argument("--instr", choices=sorted(a2w.INSTRUMENTS), default="harpsichord")
    ap.add_argument("--fpe", type=int)
    ap.add_argument("--only-flagged", action="store_true")
    ap.add_argument("--table", action="store_true", help="print the period table errors")
    a = ap.parse_args(argv)
    if a.table:
        print("idx midi name    TP      Hz   cents(128K)")
        for i in range(0x60):
            m = i + a2w.PITCH_BASE
            tp, f, c = ay(m)
            print("$%02X %4d %-5s %5d %9.2f %+6.1f" % (i, m, name(m), tp, f, c))
    for p in a.abc:
        audit(p, a.accidentals, a.transpose, a.instr, a.fpe, a.only_flagged)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
