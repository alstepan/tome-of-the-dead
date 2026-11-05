#!/usr/bin/env python3
"""tsx_extract.py - pull the 7 chosen tunes out of the user's browser player (main.tsx).

main.tsx is the GROUND TRUTH for the notes; the .abc exports are corrupt (octave digits
read as lengths, +12 shift, missing naturals, no bar lines).  Scope: the six game cues
(dungeon_crawl .. game_over: their literal Note[] arrays), the Catacomb Lament IIb
(f_minor_staccato_theme = transposeNotes(BASE_*_LEGATO, 3, preferFlats) followed by
applyStaccatoToSubject, both reimplemented here from the tsx source) and, for comparison
(S1e), the pure-legato Lament II (f_minor_lament = the same transposeNotes, no
staccato at all: transposeNotes forces staccato false).

The pasted copy carries a line-number prefix on every line ("12  const x"); it is
stripped (only the exact running line number, so real leading digits are safe).

Output assets/sfx/music/src/<tune>.json:
  {title, bpm, loop, voices:{A,B,C:[{midi, pitch, beats, stac}]}}
tsx pitch C4 = MIDI 60 (= ABC 'C'; no octave shift).  Rests: pitch "R", midi null.
beats: quarter note = 1.0 (as in the tsx).  IIb's bpm is the player's default state (74):
the cues carry their own defaultBpm, the theme variants do not.

Run: python3 -I tools/tsx_extract.py [main.tsx] [-o assets/sfx/music/src]
"""
import argparse
import json
import math
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TSX = os.path.join(REPO, "assets/sfx/concepts/player-js/main.tsx")
MAIN_CHECKOUT_TSX = ("/Users/alexs/sources/zxspectrum/tome-of-the-dead/assets/sfx/concepts/"
                     "player-js/main.tsx")   # untracked in worktrees
OUTDIR = os.path.join(REPO, "assets/sfx/music/src")

CUES = ["dungeon_crawl", "dangerous", "boss_fight", "level_complete", "game_win", "game_over"]
IIB_ID = "f_minor_staccato_theme"
IIB_TITLE = "IIb. Catacomb Lament (Staccato Theme)"
II_ID = "f_minor_lament"
II_TITLE = "II. Catacomb Lament (Legato)"
IIB_BPM_RE = r"const \[bpm, setBpm\] = useState\((\d+)\)"
VOICE_KEYS = ("A", "B", "C")

MIDI_TO_NOTE_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
MIDI_TO_NOTE_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class TsxError(Exception):
    pass


def strip_line_numbers(text):
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        p = str(i)
        out.append(line[len(p):] if line.startswith(p) else line)
    return "\n".join(out)


def parse_note_table(src):
    m = re.search(r"const NOTE_TO_MIDI[^=]*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        raise TsxError("NOTE_TO_MIDI not found")
    table = {k: int(v) for k, v in re.findall(r'"([A-G][#b]?\d)":\s*(\d+)', m.group(1))}
    if table.get("C4") != 60 or len(table) < 80:
        raise TsxError("NOTE_TO_MIDI looks wrong (%d entries)" % len(table))
    return table


def _notes_in(text):
    text = re.sub(r"//[^\n]*", "", text)
    return [(p, float(d)) for p, d in
            re.findall(r'\{\s*pitch:\s*"([^"]+)",\s*duration:\s*([0-9.]+)', text)]


def parse_cues(src):
    start = src.index("const GAME_CUES")
    body = src[start:src.index("\n];", start)]
    parts = re.split(r'\n  \{\n    id: "', body)[1:]
    cues = {}
    for p in parts:
        cid = p.split('"', 1)[0]
        bpm = int(re.search(r"defaultBpm:\s*(\d+)", p).group(1))
        name = re.search(r'\n    name: "([^"]+)"', p).group(1)
        total = int(re.search(r"totalBeats:\s*(\d+)", p).group(1))
        loop = re.search(r"loop:\s*(true|false)", p).group(1) == "true"
        voices = {}
        for v in "123":
            m = re.search(r"\n    v%s: \[(.*?)\n    \]," % v, p, re.S)
            if not m:
                raise TsxError("%s v%s array not found" % (cid, v))
            voices["v" + v] = _notes_in(m.group(1))
        cues[cid] = {"name": name, "bpm": bpm, "total": total, "loop": loop, "voices": voices}
    return cues


def parse_base(src, n):
    m = re.search(r"const BASE_V%d_LEGATO: Note\[\] = \[(.*?)\n\];" % n, src, re.S)
    if not m:
        raise TsxError("BASE_V%d_LEGATO not found" % n)
    return _notes_in(m.group(1))


def transpose_pitch(pitch, semitones, prefer_flats, table):
    """transposePitch(): rests pass; unknown names return unchanged (the tsx then plays
    silence for them - here that is an error); name from MIDI_TO_NOTE_{FLAT,SHARP}, and
    octave = floor(midi/12) - 1 (C4 = 60)."""
    if pitch == "R":
        return "R"
    if pitch not in table:
        raise TsxError("pitch %r not in NOTE_TO_MIDI" % pitch)
    new = table[pitch] + semitones
    names = MIDI_TO_NOTE_FLAT if prefer_flats else MIDI_TO_NOTE_SHARP
    return "%s%d" % (names[new % 12], math.floor(new / 12) - 1)


def transpose_notes(notes, semitones, prefer_flats, table):
    # transposeNotes() forces staccato false
    return [(transpose_pitch(p, semitones, prefer_flats, table), d, False) for p, d in notes]


def apply_staccato(notes, starts):
    """applyStaccatoToSubject(): a note is staccato iff its start beat lies in
    [start, start+16) for some subject entry."""
    cur = 0.0
    out = []
    for p, d, _ in notes:
        s = cur
        cur += d
        out.append((p, d, any(st <= s < st + 16 for st in starts)))
    return out


def to_json_voice(notes, table):
    return [{"midi": None if p == "R" else table[p], "pitch": p, "beats": d, "stac": bool(st)}
            for p, d, st in notes]


def build_all(src):
    table = parse_note_table(src)
    cues = parse_cues(src)
    tunes = {}
    for cid in CUES:
        c = cues.get(cid)
        if not c:
            raise TsxError("cue %s missing" % cid)
        voices = {k: to_json_voice([(p, d, False) for p, d in c["voices"]["v" + str(i + 1)]], table)
                  for i, k in enumerate(VOICE_KEYS)}
        tunes[cid] = {"title": c["name"], "bpm": c["bpm"], "loop": c["loop"], "voices": voices,
                      "_total": c["total"]}
    base = [parse_base(src, n) for n in (1, 2, 3)]
    tr = [transpose_notes(b, 3, True, table) for b in base]
    starts = ([0, 16, 64, 96], [16, 96], [32, 96])   # FM_STACCATO_THEME_VOICES
    # guard: the constants above are copied from the tsx; fail if it changed
    for pat in ("applyStaccatoToSubject(baseFmV1, [0, 16, 64, 96])",
                "applyStaccatoToSubject(baseFmV2, [16, 96])",
                "applyStaccatoToSubject(baseFmV3, [32, 96])",
                "transposeNotes(BASE_V1_LEGATO, 3, true)"):
        if pat not in src:
            raise TsxError("tsx logic changed: %s" % pat)
    voices = {k: to_json_voice(apply_staccato(tr[i], starts[i]), table)
              for i, k in enumerate(VOICE_KEYS)}
    bpm = int(re.search(IIB_BPM_RE, src).group(1))
    v = src.index('id: "%s"' % II_ID)
    block = src[v:src.index("\n  },", v)]
    for n in (1, 2, 3):
        if "v%d: transposeNotes(BASE_V%d_LEGATO, 3, true)," % (n, n) not in block:
            raise TsxError("tsx logic changed: %s v%d" % (II_ID, n))
    if 'name: "%s"' % II_TITLE not in block:
        raise TsxError("tsx title changed: %s" % II_ID)
    tunes[II_ID] = {"title": II_TITLE, "bpm": bpm, "loop": True, "_total": 128,
                    "voices": {k: to_json_voice(tr[i], table) for i, k in enumerate(VOICE_KEYS)}}
    tunes[IIB_ID] = {"title": IIB_TITLE, "bpm": bpm, "loop": True, "voices": voices,
                     "_total": 128}
    return tunes


def summarize(tunes):
    lines = []
    for tid, t in tunes.items():
        row = []
        for k in VOICE_KEYS:
            v = t["voices"][k]
            row.append("%s: %d notes %g beats%s" % (
                k, len(v), sum(n["beats"] for n in v),
                " stac=%d" % sum(n["stac"] for n in v) if any(n["stac"] for n in v) else ""))
        lines.append("%-24s bpm=%-3d %s" % (tid, t["bpm"], " | ".join(row)))
    return "\n".join(lines)


def check(tunes):
    errs = []
    for tid, t in tunes.items():
        for k in VOICE_KEYS:
            tot = sum(n["beats"] for n in t["voices"][k])
            if tot != t["_total"]:
                errs.append("%s %s: %g beats, expected %d" % (tid, k, tot, t["_total"]))
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tsx", nargs="?")
    ap.add_argument("-o", "--outdir", default=OUTDIR)
    a = ap.parse_args(argv)
    path = a.tsx or next((p for p in (DEFAULT_TSX, MAIN_CHECKOUT_TSX) if os.path.exists(p)), None)
    if not path:
        print("main.tsx not found", file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as f:
        src = strip_line_numbers(f.read())
    try:
        tunes = build_all(src)
    except (TsxError, AttributeError, ValueError) as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    errs = check(tunes)
    os.makedirs(a.outdir, exist_ok=True)
    for tid, t in tunes.items():
        out = {k: v for k, v in t.items() if not k.startswith("_")}
        with open(os.path.join(a.outdir, tid + ".json"), "w") as f:
            json.dump(out, f, indent=1)
            f.write("\n")
    print(summarize(tunes))
    for e in errs:
        print("ERROR", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
