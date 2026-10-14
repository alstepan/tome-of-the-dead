#!/usr/bin/env python3
"""abc2wzm.py - ABC -> "WZM" compact song data for the AY player (S0 tool).

Parses the ABC subset used by assets/sfx/concepts/ (own minimal parser), validates
(bar sums, 3 monophonic voices, AY range), and emits sjasmplus DEFB data plus a JSON
event list.  No Z80 here: this file is also the spec of the byte format below.

WZM v0.3 byte format (docs/design/sound.md sec.2 only sketches it; this is the concrete
definition the Z80 player is written against, wzm_ref.py is the oracle).  All words
little-endian, all durations in 50 Hz frames (tempo is baked in, no tempo byte).

Song block (label <name>):
  +0  DEFW stream_A, stream_B, stream_C   ; one monophonic stream per AY channel
  +6  DEFB inst_A, inst_B, inst_C         ; index into the instrument pointer list
  +9  DEFB env_shape                      ; R13 for the voice-C buzzer: $0C saw, $0E
                                          ; triangle, 0 = no buzzer (v0.3; was the R7
                                          ; mixer in v0.2 - R7 is now per frame: $3C on
                                          ; a buzzer frame, else $38)
  +10 DEFW inst_0 .. inst_{n-1}           ; instrument pointers
  ...streams and instruments follow (any order, referenced by label)

Stream = sequence of events, each starts with a byte B:
  $00-$5F  note: pitch index = MIDI-12 (C1..; C4=$30), followed by DEFB dur_frames (1-255)
  $60      rest, followed by DEFB dur_frames
  $80      loop:  DEFW address, continue there immediately (same frame, no gap)
  $81      end (one-shot): voice goes silent
  $82      staccato gate ON  (applies to following notes; initial state OFF)
  $83      staccato gate OFF
  $84 nn   set instrument index nn (reserved: the v0.1 player ends the voice on it)
  $85      legato: the NEXT event must be a note; it does not re-attack.  Only the
           period changes: no arp0 frame, the volume table / tremolo phase run on from
           the previous note, the gate is the new note's own.  (v0.1; invalid before
           a rest or as the first note of a stream - the converter never emits that.)
  A note occupies exactly dur frames; gate/release is inside that span (no overrun).
  A rest keeps the last period (no arp0 frame, v0.1) and continues the previous note's
  release (v0.3: the reverb tail runs on into a rest; an instrument with drop >= 15
  is silent there, as a v0.2 rest was).

Instrument (per frame t = 0.. since note start):
  +0 arp0       semitones added to the pitch on frame 0 only (pluck transient)
  +1 loop_idx   volume-table index to wrap to after the last entry; $FF = hold last
  +2 trem_per   tremolo period in frames (0 = off); frames with (t mod per) >= per/2
  +3 trem_dep   ... lose trem_dep volume
  +4 drop       release: the first release frame drops the volume by `drop` (floor 0)
  +5 gate_s1p   s1 + 1 (1..7)      staccato gate, non-staccato = dur:
  +6 gate_s2    bit 7 = 0: s2 - s1 (1..8), gate = (dur >> s1) - (dur >> s2) (v0.2;
                (0, 8) = dur: the 100 % gate, S1e).
                (0, 1): 50 % rounded up, (0, 2): 75 %, (1, 4): 7/16, the tsx's 45 % cut
                (frame-exact vs round(0.45 dur) for every staccato length at 66/74/96 bpm).
                bit 7 = 1 (v0.3, s1 >= 1): s2 (absolute), gate = round-half-up(dur >> s1)
                + (dur >> s2): (1, 4) = 9/16 ~ 56 %, (1, 3) = 5/8 = 62.5 %.
                The converter rejects a staccato gate of 0.
  +7 rel_per    (v0.3) after the drop, the volume falls by 1 every rel_per frames (floor
                0): the reverb tail.  Each AY volume step is ~3 dB, so this is an
                exponential decay.  drop >= the level = the v0.2 instant cut (rel_per CUT = 255).
  +8 ..         volume table (0..15 per frame, or $10 = AY envelope mode: voice C only,
                the buzzer), terminated by $FF
  Envelope time e counts sustain frames since the last attack (a legato note does not
  reset it): vol = table(e) - tremolo(e) while t < gate.  Release (t >= gate, and every
  rest frame): frame 1 of the release = last volume - drop; then -1 every rel_per frames.
  Every note (attacked or legato) restarts the release (first frame drops again); a
  rest does not.  An envelope-mode volume ($10) minus the drop is a plain level: the
  buzzer voice's tail is its square tone at that level.
Tone only, no noise.  R13 is written once by player_start (header +9, only with the
buzzer assembled in); the stream holds $FF.
Buzzer (optional, player assembled with WZM_BUZZER): a voice-C volume with bit 4 set
makes the player also write R11/R12 that frame: e = (TP + 8) >> 4 (sawtooth $0C at the
note's pitch), halved again for a triangle shape (bit 1 of the shape): (e + 1) >> 1;
R11/R12 hold otherwise and are 0 after a start.  R7 = $3C (tone C off) on a buzzer
frame, $38 otherwise (v0.3: the tail needs tone C).
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from fractions import Fraction

AY_CLK = 1773400
MIDI_MIN, MIDI_WARN_MAX, MIDI_MAX = 21, 96, 108  # TP<=4095 / "C7 top of usable" / hard
PITCH_BASE = 12  # stream pitch index = midi - 12
REST = 0x60
CMD_LOOP, CMD_END, CMD_STAC_ON, CMD_STAC_OFF, CMD_INST = 0x80, 0x81, 0x82, 0x83, 0x84
CMD_LEGATO = 0x85
MIXER_TONE, MIXER_BUZZ_C = 0x38, 0x3C     # R7: tone A/B/C; tone A/B (C = envelope only)
VOL_ENV = 0x10                            # volume-table value: AY envelope mode (buzzer)
ENV_SAW, ENV_TRI = 0x0C, 0x0E             # R13 shapes: //// and /\/\ (bit 1: triangle)

# Staccato gates (s1, s2[, "+"]): "-" = (dur >> s1) - (dur >> s2); "+" = round(dur >> s1)
# + (dur >> s2).  30 = 5/16 = 31.25 % (round(dur >> 2) + (dur >> 4); the closest two-shift
# form to 30 %: 1/4 and 3/8 are the neighbours), 45 = the tsx's cut (S1d), 56 = 9/16 (S1e default, user: "a little
# longer"), 62 = 5/8 (the "65 %" option: no two-shift form gives 65 %), 100 = dur -
# (dur >> 8) = the whole note (S1e: staccato marks ignored, the tail only on rests).
GATES = {30: (2, 4, "+"), 45: (1, 4), 56: (1, 4, "+"), 62: (1, 3, "+"), 100: (0, 8)}
GATE_DEFAULT = 56

# S1e reverb approximation ("cathedral crypt", main.tsx l.946-962: IR = 2.8 s noise x
# exp(-2t), wet 1.0 / dry 0.5): after the gate the dry level drops by `drop` AY steps
# (the dry cut; what remains is the wet tail) and then falls 1 step (~3 dB) every
# `rel_per` frames - an exponential decay.  Tail length = rel_per x tail start level:
# organ 6 x 10 = 60 frames (1.2 s), harpsichord 4 x 9 = 36 frames (0.72 s).  The tsx IR
# itself falls ~17 dB/s (~1 step / 9.5 frames, ~2 s to silence from level 10): both
# are deliberately shorter (user brief 0.5-1.2 s, organ longer).
REVERB = {"organ": {"drop": 3, "rel_per": 6}, "harp": {"drop": 4, "rel_per": 4}}

# rel_per of an instant-cut instrument (drop >= its level: silent after the first
# release frame).  Any value gives the same registers; 255 keeps the player off its
# step path (~0.15k T) on almost every release frame (rel_per 1 would step every frame).
CUT = 255

# Reverb levels (S1e follow-up; tape key H, --reverb, WZM_REVERB).  The tsx reverb is a
# wet/dry MIX: dry = max(0.3, 1 - wet/2), wet = the slider (100 % = 1.0, 50 % = 0.5), the
# convolver normalised (equal power).  At a staccato cut the dry part stops and the wet
# part rings on: its level relative to the note's mix is
#   wet x w / sqrt(dry^2 + (wet x w)^2),  w = the IR's build-up during the note
# (w = 1 for a long note; a 96 bpm staccato eighth sounds ~0.16 s: w = sqrt(1 -
# exp(-4 x 0.16)) ~ 0.69).  100 %: -1 .. -2 dB -> drop 1 AY step (~3 dB);  50 %: -5 ..
# -8 dB -> drop 2 steps.  The IR decays exp(-2t) = 17.4 dB/s = 1 step (~3 dB) every ~9
# frames at both levels -> rel_per 9: from the note level 13 a 100 % tail lasts 1 + 9 x 12
# = 109 frames (2.2 s), 50 % ~2 s.  0 % = instant cut (drop past the level).  "s1e" = the
# S1e tails above (REVERB; shorter than the tsx on purpose).  The buzzer voice (C) drops 2
# more (its full envelope level 16 stands for the tsx's 14).  It stays a release-tail
# approximation: the tail is the voice's own note, only where that voice is silent.
REVERB_LEVELS = {0: {"drop": 14, "rel_per": CUT}, 50: {"drop": 2, "rel_per": 9},
                 100: {"drop": 1, "rel_per": 9}}
REVERB_STEPS = ("s1e", 0, 50, 100)        # the tape's H cycle (s1e = default)

INSTRUMENTS = {
    # arp0, loop_idx, trem_per, trem_dep, drop, gate, volume table, rel_per
    # S1 "harpsichord" (pluck): decays 15 -> 3, so an un-slurred legato note averages far
    # below a staccato one - audibly wrong against the tsx (docs/design/sound.md S1d).
    "harpsichord": (12, 0xFF, 0, 0, 15, (0, 1),
                    [15, 13, 12, 11, 10, 9, 9, 8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3], CUT),
    # S1 organ; v0.3 release = 13 -> 9, then -1 a frame (v0.2: -4 a frame)
    "organ": (0, 2, 8, 1, 4, (0, 2), [9, 11, 13, 13], 1),
    # tsx-faithful (main.tsx HARPSICHORD/any mode gain model): constant AY level 13 (V1/V2)
    # or 14 (V3) for the whole note, no arp/tremolo/decay; staccato = 45 % then 0.
    "tsx13": (0, 0xFF, 0, 0, 15, GATES[45], [13], CUT),
    "tsx14": (0, 0xFF, 0, 0, 15, GATES[45], [14], CUT),
    # S1d (6) brightening experiments, never the default
    "tsx13oct": (12, 0xFF, 0, 0, 15, GATES[45], [13], CUT),     # +1 octave on frame 0 only
    "tsx14oct": (12, 0xFF, 0, 0, 15, GATES[45], [14], CUT),
    "tsxbuzz": (0, 0xFF, 0, 0, 16, GATES[45], [VOL_ENV], CUT),  # voice C: envelope sawtooth
    # S1e GOTHIC ORGAN (tsx CRYPT_ORGAN: A saw, B square, C triangle): A/B flat squares at
    # 13; C = triangle buzzer (voice C transposed -12 by the set, see SET_V3_TRANSPOSE),
    # nominal 14; tails from 10 (A/B) and 11 (C, a square at the buzzer's pitch).
    "org13": (0, 0xFF, 0, 0, REVERB["organ"]["drop"], GATES[GATE_DEFAULT], [13],
              REVERB["organ"]["rel_per"]),
    "orgtri": (0, 0xFF, 0, 0, 16 - (14 - REVERB["organ"]["drop"]), GATES[GATE_DEFAULT],
               [VOL_ENV], REVERB["organ"]["rel_per"]),
    # S1e HARPSICHORD (tsx: 3 saws): A/B flat squares at 13, C = sawtooth buzzer (the S1d
    # key-0 experiment); tails from 9 (A/B) and 10 (C).
    "hps13": (0, 0xFF, 0, 0, REVERB["harp"]["drop"], GATES[GATE_DEFAULT], [13],
              REVERB["harp"]["rel_per"]),
    "hpsaw": (0, 0xFF, 0, 0, 16 - (14 - REVERB["harp"]["drop"]), GATES[GATE_DEFAULT],
              [VOL_ENV], REVERB["harp"]["rel_per"]),
}
# per-voice instrument map (A, B, C); a plain instrument name means all three voices
INSTR_SETS = {
    "tsx": ("tsx13", "tsx13", "tsx14"),
    "tsx-oct": ("tsx13oct", "tsx13oct", "tsx14oct"),
    "tsx-buzz": ("tsx13", "tsx13", "tsxbuzz"),
    "organ-rev": ("org13", "org13", "orgtri"),
    "harp-rev": ("hps13", "hps13", "hpsaw"),
}
# envelope shape of the buzzer instruments (song header +9)
BUZZ_SHAPE = {"tsxbuzz": ENV_SAW, "orgtri": ENV_TRI, "hpsaw": ENV_SAW}
# reverb-tail instruments -> REVERB kind (the instruments --reverb / key H retunes)
REVERB_INST = {"org13": "organ", "orgtri": "organ", "hps13": "harp", "hpsaw": "harp"}


def inst_tail(inst, reverb=None):
    """(drop, rel_per) of an instrument at a reverb level (REVERB_STEPS; None = its own)."""
    _, _, _, _, drop, _, vols, rper = INSTRUMENTS[inst]
    if reverb is None or inst not in REVERB_INST:
        return drop, rper
    lv = REVERB[REVERB_INST[inst]] if reverb == "s1e" else REVERB_LEVELS[reverb]
    env = any(v & VOL_ENV for v in vols)
    return min(16, lv["drop"] + (2 if env else 0)), lv["rel_per"]
# The triangle's period is ~TP / 32: at the bass's own pitch that integer is too
# coarse (C3 = 26.5 -> +-33 cents); one octave down it is exact to <= 16 cents on every
# cue and on the Lament's common notes.  So the organ pedal sounds an octave below the
# tsx (a 16' pedal).  Applied by convert() unless transpose_v3 is given.
SET_V3_TRANSPOSE = {"organ-rev": -12}
DEFAULT_INSTR = {"json": "tsx", "abc": "harpsichord"}


def instr_map(instr):
    """instrument set or single instrument name -> (inst_A, inst_B, inst_C)."""
    if instr in INSTR_SETS:
        return INSTR_SETS[instr]
    if instr in INSTRUMENTS:
        return (instr,) * 3
    raise AbcError("unknown instrument %r" % instr)


def gate_of(g, dur):
    """Gate formula of a GATES tuple (the player's)."""
    if len(g) == 3:
        s1, s2, _ = g
        return ((dur + (1 << (s1 - 1))) >> s1) + (dur >> s2)
    s1, s2 = g
    return (dur >> s1) - (dur >> s2)


def gate_bytes(g):
    """instrument header +5/+6 of a GATES tuple."""
    if len(g) == 3:
        s1, s2, op = g
        assert op == "+" and 1 <= s1 < s2 <= 7
        return s1 + 1, 0x80 | s2
    s1, s2 = g
    assert 0 <= s1 < s2 <= 8 and s2 - s1 <= 8   # s2 = 8 only for the 100 % gate
    return s1 + 1, s2 - s1


def inst_gate(inst, dur, stac, gate=None):
    """Frames of sustain of a note (the player's formula); gate = GATES key override."""
    g = GATES[gate] if gate is not None else INSTRUMENTS[inst][5]
    return gate_of(g, dur) if stac else dur

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# K: tonic -> position on the circle of fifths (major); minor = relative major
_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
           "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}
_SHARP_ORDER, _FLAT_ORDER = "FCGDAEB", "BEADGCF"


def key_signature(k):
    """K: value -> {letter: semitones} (major/minor/ maj/min/m; no modes, no explicit acc)."""
    m = re.match(r"^\s*([A-G][#b]?)\s*(m|min|minor|maj|major)?\s*$", k)
    if not m:
        raise AbcError("unsupported K:%s" % k)
    tonic, mode = m.group(1), (m.group(2) or "")
    n = _FIFTHS.get(tonic)
    if mode.startswith("m") and not mode.startswith("maj"):
        n = None if n is None else n - 3          # relative major is 3 fifths flatter
    if n is None or not -7 <= n <= 7:
        raise AbcError("unsupported K:%s" % k)
    if n >= 0:
        return {c: 1 for c in _SHARP_ORDER[:n]}
    return {c: -1 for c in _FLAT_ORDER[:-n]}


class AbcError(Exception):
    pass


# ---------------------------------------------------------------- parsing

NOTE_RE = re.compile(r"(?P<stac>\.?)(?P<acc>[_^=]*)(?P<l>[A-Ga-gz])(?P<oct>[,']*)"
                     r"(?P<num>\d*)(?P<den>(?:/\d*)?)(?P<tie>-?)")
ACC = {"_": -1, "__": -2, "^": 1, "^^": 2, "=": 0}


def _length(num, den, digits_fix=None):
    n = int(num) if num else 1
    if den:
        d = int(den[1:]) if len(den) > 1 else 2
    else:
        d = 1
    return Fraction(n, d)


def parse_abc(text, accidentals="strict", mangled=None):
    """-> list of tunes {x,title,m,l,q,key,voices:{name:{notes,bars}}, notes}.
    accidentals: 'strict' (bare notes follow the key signature, ABC 2.1), 'naturals'
    (a bare e/d with no accidental symbol is natural: the rev-2 Lament hypothesis) or
    'explicit' (the key signature is ignored: a bare note is natural, a flat must be
    written - what the tsx-derived exports mean)."""
    tunes = []
    cur = None
    voice = None
    for raw in text.splitlines():
        line = raw.split("%")[0].rstrip() if not raw.startswith("%%") else ""
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z]):(.*)$", line)
        if m and not (len(line) > 2 and line[1] != ":"):
            k, v = m.group(1), m.group(2).strip()
            if k == "X":
                cur = {"x": int(v), "title": "", "m": Fraction(4, 4), "l": Fraction(1, 8),
                       "q": 120, "key": "", "keysig": {}, "voices": {}, "raw": {}}
                tunes.append(cur)
                voice = None
            elif cur is None:
                continue
            elif k == "T":
                cur["title"] = v
            elif k == "M":
                a, b = v.split("/")
                cur["m"] = Fraction(int(a), int(b))
            elif k == "L":
                a, b = v.split("/")
                cur["l"] = Fraction(int(a), int(b))
            elif k == "Q":
                qm = re.match(r"(\d+)/(\d+)=(\d+)", v)
                if qm:
                    cur["q"] = Fraction(int(qm.group(3)) * int(qm.group(1)) * 4,
                                        int(qm.group(2)))  # quarter-notes per minute
                else:
                    cur["q"] = Fraction(int(v))
            elif k == "K":
                cur["key"] = v
                cur["keysig"] = key_signature(v)
            elif k == "V":
                voice = v.split()[0]
                cur["raw"].setdefault(voice, [])
            continue
        if cur is None or voice is None:
            continue
        cur["raw"][voice].append(line)
    for t in tunes:
        for vn, lines in t["raw"].items():
            t["voices"][vn] = _parse_voice(" ".join(lines), t, accidentals, mangled)
    return tunes


def _parse_voice(body, tune, accidentals, mangled):
    """Notes carry, besides midi/len/stac/tie: slur (slurred INTO the next note), tok
    (source text), bar (1-based), at (offset in the bar, whole notes), why (decode
    notes) and alt (other plausible readings: [(label, midi)]) for tools/abc_audit.py."""
    bars_present = "|" in body.replace("|]", "")
    if mangled is None:
        mangled = not bars_present  # re-exported short-melodies: bar lines lost + octave digits
    notes = []
    bars = []  # per-bar length in whole notes
    bar_acc = {}
    bar_len = Fraction(0)
    pos = 0
    dropped = re.findall(r'"[^"]*"|![^!]*!', body)
    body = re.sub(r'"[^"]*"|![^!]*!', "", body)
    L, M = tune["l"], tune["m"]
    keysig = tune["keysig"]
    slur_depth = 0
    open_slur = None   # last note inside an open slur (gets slur=True when a note follows)
    tied = None        # previous note if it ended with '-'
    while pos < len(body):
        c = body[pos]
        if c in " \t":
            pos += 1
            continue
        if c == "(":
            if pos + 1 < len(body) and body[pos + 1].isdigit():
                raise AbcError("tuplets not supported (pos %d)" % pos)
            slur_depth += 1
            pos += 1
            continue
        if c == ")":
            slur_depth = max(0, slur_depth - 1)
            if not slur_depth:
                open_slur = None
            pos += 1
            continue
        if c in "[{":
            raise AbcError("chords/grace notes not supported (pos %d)" % pos)
        if c in "|:]":
            m = re.match(r"(\|\]|\|\||\|:|:\||\||\]|:)+", body[pos:])
            pos += m.end() if m else 1
            if bar_len or "|" in body[pos - 1:pos]:
                if bar_len:
                    bars.append(bar_len)
                bar_len = Fraction(0)
                bar_acc = {}
            continue
        m = NOTE_RE.match(body, pos)
        if not m:
            raise AbcError("cannot parse %r at %d" % (body[pos:pos + 8], pos))
        pos = m.end()
        if mangled and bar_len >= M:
            # no bar lines in the file: the bar (and its accidentals) ends every M
            bars.append(bar_len)
            bar_len = Fraction(0)
            bar_acc = {}
        acc, letter, octs = m.group("acc"), m.group("l"), m.group("oct")
        num, den = m.group("num"), m.group("den")
        why, alt = [], []
        digit_oct = None
        if mangled and letter != "z" and num and not octs:
            # exporter writes an octave digit after the letter on accidental notes
            # (and a few plain ones): midi = 12*(d+2)+pc+acc (C3 = MIDI 60 numbering).
            # No bars to arbitrate: a leading number >= 3 is always an octave (these files
            # only use lengths 1/2); a leading 1/2 is an octave only after _ or ^.
            if ((acc and acc != "=") and letter.islower()) or \
                    (letter.isupper() and int(num[0]) >= 3):
                digit_oct, num = int(num[0]), num[1:]
            elif letter.isupper() and acc:
                why.append("upper+acc digit read as length")
        ln = _length(num, den) * L
        note = {"tok": m.group(0), "bar": len(bars) + 1, "at": bar_len, "len": ln,
                "stac": bool(m.group("stac")), "tie": False, "slur": False,
                "why": why, "alt": alt}
        if letter == "z":
            note["midi"] = None
            open_slur = None   # a rest breaks the legato line
            tied = None
        else:
            pc = PC[letter.upper()]
            case_base = (72 if letter.islower() else 60) \
                + 12 * octs.count("'") - 12 * octs.count(",")
            if digit_oct is not None:
                base = 12 * (digit_oct + 2)
                why.append("digit-oct %d" % digit_oct)
                dig_alt = [("sci-oct", base - 12 + pc)]
                if base != case_base:
                    why.append("CASE/DIGIT CONFLICT")
                    dig_alt.append(("case-oct", case_base + pc))
            else:
                base = case_base
                dig_alt = []
            key = (letter.upper(), base)
            keydef = 0 if accidentals == "explicit" else keysig.get(letter.upper(), 0)
            if acc:
                a = ACC[acc]
                bar_acc[key] = a
            elif tied is not None and tied["key"] == key:
                a = tied["a"]   # ABC 2.1: a tied note keeps its accidental across the bar
                if bar_acc.get(key, keydef) != a:
                    why.append("tie carries acc")
            elif key in bar_acc:
                a = bar_acc[key]
                if a != keydef:
                    why.append("in-bar acc")
                    alt.append(("no-persist", base + pc + keydef))
            else:
                a = keydef
                if accidentals == "naturals" and letter.upper() in "ED":
                    a = 0
                if keydef:
                    why.append("key")
                    alt.append(("no-keysig" if a == keydef else "strict", base + pc
                                + (0 if a == keydef else keydef)))
            note["midi"] = base + pc + a
            alt.extend((k, x + a) for k, x in dig_alt)
            note["tie"] = bool(m.group("tie"))
            if open_slur is not None:
                open_slur["slur"] = True
            open_slur = note if slur_depth else None
            tied = {"key": key, "a": a} if note["tie"] else None
        notes.append(note)
        bar_len += ln
    if bar_len:
        bars.append(bar_len)
    # merge ties
    out = []
    for n in notes:
        if out and out[-1]["tie"] and out[-1]["midi"] == n["midi"]:
            out[-1]["len"] += n["len"]
            out[-1]["tie"] = n["tie"]
            out[-1]["slur"] = n["slur"]
            out[-1]["tok"] += " " + n["tok"]
        else:
            if out and out[-1]["tie"]:
                out[-1]["why"].append("TIE TO OTHER PITCH -> legato")
                out[-1]["slur"] = n["midi"] is not None
            out.append(n)
    return {"notes": out, "bars": bars, "bars_present": bars_present, "mangled": mangled,
            "dropped": dropped}


def tune_from_json(path):
    """tsx_extract.py output (assets/sfx/music/src/*.json) -> the same tune dict
    parse_abc() yields, so validate/events_for/encode need no special case.  beats are
    quarter notes -> len in whole notes; pitches are exact (C4 = MIDI 60, no shift,
    no key-signature or bar-accidental rules to apply)."""
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    voices = {}
    for vn, lst in j["voices"].items():
        notes, bars, t = [], [], Fraction(0)
        for n in lst:
            ln = Fraction(n["beats"]).limit_denominator(64) / 4
            notes.append({"tok": n["pitch"], "bar": int(t) + 1,
                          "at": t % 1, "len": ln, "stac": bool(n["stac"]),
                          "tie": False, "slur": False, "why": [], "alt": [],
                          "midi": n["midi"]})
            t += ln
        voices[vn] = {"notes": notes, "bars": bars, "bars_present": False, "mangled": False,
                      "dropped": []}
    return {"x": 1, "title": j["title"], "m": Fraction(4, 4), "l": Fraction(1, 8),
            "q": Fraction(j["bpm"]), "key": "Fm", "keysig": key_signature("Fm"),
            "voices": voices, "raw": {}, "loop": bool(j.get("loop", False))}


def ref_abc(path):
    """JSON -> clean reference ABC: K:Fm header, every accidental written (naturals of
    key-signature letters as '=' too), bar line every 4 beats (a note crossing one is
    split with a tie), correct octaves (C4 = 'C', C5 = 'c', no +12 shift)."""
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    ks = key_signature("Fm")
    out = ["%abc-2.1", "X:1", "T:Tome of the Dead - " + j["title"],
           "C:generated by tools/abc2wzm.py from assets/sfx/music/src (tsx ground truth)",
           "M:4/4", "L:1/8", "Q:1/4=%d" % j["bpm"], "K:Fm"]

    def spell(m):
        pc = m % 12
        for letter, base in PC.items():
            if base == pc:
                return letter, 0
        for letter, base in PC.items():   # black key -> flat of the next letter up
            if (base - 1) % 12 == pc:
                return letter, -1
        raise AbcError("unspellable %d" % m)
    for vi, (vn, lst) in enumerate(j["voices"].items(), 1):
        out.append("V:V%d" % vi)
        bar_state = {}
        toks, beat = [], Fraction(0)
        line = []
        for n in lst:
            left = Fraction(n["beats"]).limit_denominator(64)
            first = True
            while left > 0:
                room = 4 - beat % 4
                part = min(left, room)
                left -= part
                units = part * 2
                if units.denominator != 1:
                    raise AbcError("duration %s not on the 1/8 grid" % part)
                ln = "" if units == 1 else str(units)
                if n["midi"] is None:
                    tok = "z" + ln
                else:
                    letter, a = spell(n["midi"])
                    # octave letter from the pitch class it is spelt at (Cb never occurs)
                    m0 = n["midi"] - a
                    octv = m0 // 12 - 1
                    key = (letter, octv)
                    cur = bar_state.get(key, ks.get(letter, 0))
                    if first:
                        acc = {-1: "_", 0: "=", 1: "^"}[a] if (a != cur or letter in ks or a) else ""
                        bar_state[key] = a
                    else:
                        acc = ""
                    if octv >= 5:
                        nm = letter.lower() + "'" * (octv - 5)
                    else:
                        nm = letter + "," * (4 - octv)
                    tok = ("." if n["stac"] and first else "") + acc + nm + ln
                    if left > 0:
                        tok += "-"
                toks.append(tok)
                beat += part
                if beat % 4 == 0:
                    toks.append("|")
                    bar_state = {}
                first = False
        txt = " ".join(toks)
        if txt.endswith("|"):
            txt = txt[:-1] + "|]"
        out.append(txt)
    return "\n".join(out) + "\n"


def validate(tune, report):
    """Bar-sum + voice-count checks. Returns list of error strings."""
    errs = []
    m = tune["m"]
    if len(tune["voices"]) != 3:
        errs.append("expected 3 voices, found %d" % len(tune["voices"]))
    totals = {}
    for vn, v in tune["voices"].items():
        total = sum((n["len"] for n in v["notes"]), Fraction(0))
        totals[vn] = total
        if v["bars_present"]:
            bad = [(i + 1, str(b)) for i, b in enumerate(v["bars"][:-1]) if b != m]
            if bad:
                errs.append("%s: bars with wrong sum (bar, whole-notes): %s" % (vn, bad[:6]))
            if v["bars"] and v["bars"][-1] != m:
                errs.append("%s: last bar sums to %s" % (vn, v["bars"][-1]))
        elif total % m:
            errs.append("%s: no bar lines, total %s not a multiple of %s" % (vn, total, m))
    if len(set(totals.values())) > 1:
        errs.append("voice lengths differ: %s" % {k: str(x) for k, x in totals.items()})
    return errs


# ---------------------------------------------------------------- timing

def exact_frames_per_eighth(tune, bpm=None):
    """Exact frames (50 Hz) per eighth note: 1500 / quarter-notes-per-minute, as a
    Fraction (74 bpm -> 750/37 = 20.27; the boundary rounding in events_for keeps every
    onset within half a frame of the exact time, so there is no drift)."""
    return Fraction(1500) / Fraction(bpm if bpm is not None else tune["q"])


def frames_per_unit(tune, fpe):
    """frames per whole-note: 8 eighths."""
    return fpe * 8


def events_for(tune, vn, fpe, transpose, stac_enabled=True, legato="slurs"):
    """-> list of (midi|None, frames, stac, slur).  slur = this note runs legato into
    the next one (the next note gets CMD_LEGATO).  legato: 'slurs' (ABC slurs and
    ties-to-another-pitch), 'none' (--no-legato: every note attacks), 'unmarked'
    (--legato-unmarked: also every run of unmarked, i.e. non-staccato, notes).
    Never legato into the same pitch (a slur over repeated notes would merge them into
    one long note: they re-attack).  A slurred note's gate is the full length: its
    staccato mark is dropped (only the last note of a slur keeps its gate).
    Frames: each note boundary is rounded on the exact cumulative time, so rounding
    never accumulates and all voices stay aligned at every common onset."""
    ev = []
    fpw = frames_per_unit(tune, fpe)
    notes = tune["voices"][vn]["notes"]
    t0 = Fraction(0)
    f0 = 0
    for i, n in enumerate(notes):
        t1 = t0 + n["len"]
        f1 = int(t1 * fpw + Fraction(1, 2))
        fi = f1 - f0
        if not 1 <= fi <= 255:
            raise AbcError("duration %s frames out of 1..255" % fi)
        t0, f0 = t1, f1
        mid = None if n["midi"] is None else n["midi"] + transpose
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        slur = False
        if mid is not None and nxt is not None and nxt["midi"] is not None \
                and nxt["midi"] != n["midi"] and legato != "none":
            slur = n["slur"] or (legato == "unmarked" and not n["stac"] and not nxt["stac"])
        ev.append((mid, fi, bool(n["stac"]) and stac_enabled and not slur, slur))
    return ev


# ---------------------------------------------------------------- encoding

class Blob:
    """Items with symbolic word fixups, assembled for both the .asm text and a byte blob."""

    def __init__(self):
        self.items = []  # ('L',name) ('B',bytes) ('W',label)

    def label(self, n):
        self.items.append(("L", n))

    def b(self, *bs):
        self.items.append(("B", bytes(bs)))

    def w(self, label):
        self.items.append(("W", label))

    def bytes_(self):
        labels, off = {}, 0
        for k, v in self.items:
            if k == "L":
                labels[v] = off
            elif k == "B":
                off += len(v)
            else:
                off += 2
        out = bytearray()
        for k, v in self.items:
            if k == "B":
                out += v
            elif k == "W":
                out += labels[v].to_bytes(2, "little")
        return bytes(out), labels

    def asm(self, name):
        lines = []
        row = []

        def flush():
            if row:
                lines.append("\tDEFB " + ",".join("$%02X" % x for x in row))
                row.clear()
        for k, v in self.items:
            if k == "L":
                flush()
                lines.append(v + ":")
            elif k == "B":
                for x in v:
                    row.append(x)
                    if len(row) == 12:
                        flush()
            else:
                flush()
                lines.append("\tDEFW " + v)
        flush()
        return "\n".join(lines) + "\n"


def tail_frames(inst):
    """Frames the release (reverb tail) of a full-level note needs to reach 0; 1 for
    the pre-S1e instruments (instant cut, or the S1 organ's rel_per 1: their one-shots
    end as in v0.2).  A reverb-tail instrument: the longest over every REVERB_STEPS
    level (the tape retunes the tails at run time; the final rest must fit them all)."""
    vols = INSTRUMENTS[inst][6]
    top = max(16 if v & VOL_ENV else v for v in vols)
    out = 1
    for lv in (REVERB_STEPS if inst in REVERB_INST else (None,)):
        drop, rper = inst_tail(inst, lv)
        if not (rper == 1 or top <= drop):
            out = max(out, 1 + rper * (top - drop))
    return out


def encode_stream(blob, label, events, loop, tail=0):
    """tail: one-shot only - a final rest of that many frames so the release (reverb
    tail) of the last note plays out before END."""
    blob.label(label)
    stac = False
    slur = False
    for mid, fr, st, sl in events:
        if mid is not None and st != stac:
            blob.b(CMD_STAC_ON if st else CMD_STAC_OFF)
            stac = st
        if slur:
            assert mid is not None
            blob.b(CMD_LEGATO)
        slur = sl
        if mid is None:
            blob.b(REST, fr)
        else:
            p = mid - PITCH_BASE
            if not 0 <= p < REST:
                raise AbcError("pitch %d out of stream range" % mid)
            blob.b(p, fr)
    if tail > 1 and not loop:
        while tail > 0:
            blob.b(REST, min(tail, 255))
            tail -= 255
    if loop:
        blob.b(CMD_LOOP)
        blob.w(label)
    else:
        blob.b(CMD_END)


def build_song(name, voices_events, instr, loop, gate=None, reverb=None):
    """voices_events: 3 event lists. instr: instrument set / name (instr_map).
    gate: GATES key overriding every instrument's staccato gate.  reverb: REVERB_STEPS
    level for the reverb-tail instruments (None = their own = "s1e")."""
    imap = instr_map(instr)
    uniq = list(dict.fromkeys(imap))
    for v, ins in enumerate(imap):
        if VOL_ENV in INSTRUMENTS[ins][6] and v != 2:
            raise AbcError("envelope (buzzer) instrument %s only on voice C" % ins)
    buzz = any(x & VOL_ENV for x in INSTRUMENTS[imap[2]][6])
    blob = Blob()
    blob.label(name)
    for s in "abc":
        blob.w("%s_%s" % (name, s))
    blob.b(*(uniq.index(x) for x in imap), BUZZ_SHAPE[imap[2]] if buzz else 0)
    for ins in uniq:
        blob.w("%s_inst_%s" % (name, ins))
    tail = max(tail_frames(i) for i in imap)
    for i, s in enumerate("abc"):
        encode_stream(blob, "%s_%s" % (name, s), voices_events[i], loop, tail)
    for ins in uniq:
        arp0, lp, tp, td, _, g, vols, _ = INSTRUMENTS[ins]
        drop, rper = inst_tail(ins, reverb)
        s1p, s2b = gate_bytes(GATES[gate] if gate is not None else g)
        assert 1 <= rper <= 255 and 1 <= drop <= 16
        blob.label("%s_inst_%s" % (name, ins))
        blob.b(arp0, lp, tp, td, drop, s1p, s2b, rper, *vols, 0xFF)
    blob.label(name + "_end")
    return blob


# ---------------------------------------------------------------- pipeline

def default_accidentals(path):
    """The Lament's bare e/d are E/D natural (= the tsx ground truth, tests/abc_tools_test
    test_iib_vs_old_abc); every other ABC follows its key signature."""
    return "naturals" if os.path.basename(path) == LAMENT else "strict"


def convert(path, tune_idx=0, accidentals=None, transpose=0, fpe=None, fit=True,
            instr=None, loop=None, name=None, transpose_v3=None, stac=True,
            legato="slurs", source="abc", bpm=None, gate=None, reverb=None):
    """fpe: frames per eighth (Fraction/int) overrides the tempo; default = the exact
    Fraction from bpm (or the tune's own Q:/bpm).  loop None: the JSON's loop flag (ABC:
    one-shot).  instr None: 'tsx' for JSON, 'harpsichord' for ABC.  transpose_v3 None:
    the set's SET_V3_TRANSPOSE (organ-rev: -12).  gate: GATES key (45/56/62) overriding
    every instrument's staccato gate."""
    if source == "json":
        t = tune_from_json(path)
        accidentals = "json"      # pitches are exact; accidental rules do not apply
    else:
        accidentals = accidentals or default_accidentals(path)
        with open(path, encoding="utf-8") as f:
            tunes = parse_abc(f.read(), accidentals)
        t = tunes[tune_idx]
    instr = instr or DEFAULT_INSTR[source]
    if loop is None:
        loop = bool(t.get("loop", False))
    errs = validate(t, None)
    exact = exact_frames_per_eighth(t, bpm)
    fpe = Fraction(fpe) if fpe is not None else exact
    names = list(t["voices"])
    if len(names) != 3:
        raise AbcError("need 3 voices")
    evs = []
    imap = instr_map(instr)
    if transpose_v3 is None:
        transpose_v3 = SET_V3_TRANSPOSE.get(instr)
    for i, vn in enumerate(names):
        tr = transpose + (transpose_v3 if (i == 2 and transpose_v3 is not None) else 0)
        ev = events_for(t, vn, fpe, tr, stac, legato)
        for mid, fr, st, _ in ev:
            if mid is not None and inst_gate(imap[i], fr, st, gate) < 1:
                raise AbcError("%s: staccato gate 0 for a %d-frame note" % (vn, fr))
        evs.append(ev)
    name = name or re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0])
    blob = build_song(name, evs, instr, loop, gate, reverb)
    data, _ = blob.bytes_()
    info = {"tune": t, "errors": errs, "exact_fpe": exact, "fpe": fpe, "events": evs,
            "voice_names": names, "name": name, "blob": blob, "bytes": data,
            "instr": instr, "loop": loop, "accidentals": accidentals,
            "transpose": transpose, "transpose_v3": transpose_v3 or 0, "legato": legato,
            "gate": gate, "reverb": reverb,
            "bpm": Fraction(1500) / fpe}
    return info


def report(path, info):
    t = info["tune"]
    lines = []
    total_frames = sum(e[1] for e in info["events"][0])
    ranges = []
    for ev in info["events"]:
        ms = [e[0] for e in ev if e[0] is not None]
        ranges.append((min(ms), max(ms)) if ms else None)
    nbars = (sum((n["len"] for n in t["voices"][info["voice_names"][0]]["notes"]), Fraction(0))
             / t["m"])
    lines.append("%s [X:%d %r] Q=%s" % (os.path.basename(path), t["x"], t["title"], t["q"]))
    lines.append("  bars=%s  frames=%d  seconds=%.1f  fpe=%s (%.3f, tune's exact %.3f) -> %.2f BPM"
                 % (nbars, total_frames, total_frames / 50.0, info["fpe"], float(info["fpe"]),
                    float(info["exact_fpe"]), float(info["bpm"])))
    lines.append("  notes/voice=%s  slurred=%s  midi range=%s  size=%d B"
                 % ([sum(1 for e in ev if e[0] is not None) for ev in info["events"]],
                    [sum(1 for e in ev if e[3]) for ev in info["events"]],
                    ranges, len(info["bytes"])))
    fpw = frames_per_unit(t, info["fpe"])
    nr = sum(1 for v in t["voices"].values() for n in v["notes"]
             if (n["len"] * fpw).denominator != 1)
    if nr:
        lines.append("  exact tempo: %d notes not a whole number of frames, boundary-rounded"
                     " (every onset within 1/2 frame, no drift)" % nr)
    for r, vn in zip(ranges, info["voice_names"]):
        if r and r[0] < MIDI_MIN:
            info["errors"].append("%s below AY range (%d)" % (vn, r[0]))
        if r and r[1] > MIDI_MAX:
            info["errors"].append("%s above AY range (%d)" % (vn, r[1]))
        elif r and r[1] > MIDI_WARN_MAX:
            lines.append("  WARN %s peak midi %d above C7" % (vn, r[1]))
    for e in info["errors"]:
        lines.append("  ERROR " + e)
    if not info["errors"]:
        lines.append("  OK")
    return "\n".join(lines)


def to_json(info):
    return {"name": info["name"], "fpe": str(info["fpe"]), "instrument": info["instr"],
            "loop": info["loop"], "accidentals": info["accidentals"],
            "legato": info["legato"],
            "voices": {vn: [{"midi": m, "frames": fr, "staccato": s, "slur": sl}
                            for m, fr, s, sl in ev]
                       for vn, ev in zip(info["voice_names"], info["events"])},
            "sha256": hashlib.sha256(info["bytes"]).hexdigest()}


def write_asm(info, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("; generated by tools/abc2wzm.py - do not edit.  Format: see that file's docstring.\n")
        f.write("; %s  instr=%s accidentals=%s fpe=%s (%.2f bpm) loop=%s transpose=%d "
                "transpose_v3=%d legato=%s gate=%s\n"
                % (info["tune"]["title"], info["instr"], info["accidentals"], info["fpe"],
                   float(info["bpm"]), info["loop"], info["transpose"], info["transpose_v3"],
                   info["legato"], info["gate"] or "inst"))
        f.write(info["blob"].asm(info["name"]))
        f.write("%s_size EQU %s_end - %s\n" % (info["name"], info["name"], info["name"]))


SHORT = ["dungeon_crawl", "dangerous", "boss_fight", "level_complete", "game_win", "game_over"]
LAMENT = "tome_of_the_dead_f_minor_staccato_theme.abc"
DOOR = "the-last-locked-door.abc"   # K:F, real ABC slurs: the legato A/B piece


SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets/sfx/music/src")
IIB = "f_minor_staccato_theme"
IIB_ALT_BPM = 96        # second tape entry: the user picks 74 or 96 by ear
II = "f_minor_lament"    # tsx "II. Catacomb Lament (Legato)": IIb without staccato

# tsx tempo slider maximum (main.tsx l.2267 max={96}); a cue whose defaultBpm is above it
# (boss_fight 106) keeps its own.  S1e plays every tune at this "tsx-max" tempo.
TSX_SLIDER_MAX = 96
TSX_MAX_BPM = dict({n: TSX_SLIDER_MAX for n in SHORT + [IIB, II]}, boss_fight=106)
VARIANTS = (("org", "organ-rev"), ("hps", "harp-rev"))   # tape keys 1-7 / Q-U


def _label(prefix, tune):
    return "%s_%s" % (prefix, "lament" if tune == IIB else tune)


# Standard Fuse-audition set = src/music/testtape.asm song_tab, in request order:
# (label, json tune, convert() keywords).  S1e: 7 tunes x {organ, harpsichord} with the
# reverb tails at the tsx-max tempo, then the two S1d tsx-faithful Lament entries, then
# (comparison) the pure-legato Lament II: organ / harpsichord 96, tsx-faithful 74 / 96.
BATCH = [(_label(p, t), t, {"instr": s, "bpm": TSX_MAX_BPM[t]})
         for p, s in VARIANTS for t in SHORT + [IIB]] + [
    ("lament_tsx", IIB, {}),                               # S1d: 74 bpm (the tsx default)
    ("lament_tsx_96", IIB, {"bpm": IIB_ALT_BPM}),          # S1d: 96 bpm
    ("org_lament2", II, {"instr": "organ-rev", "bpm": TSX_MAX_BPM[II]}),
    ("hps_lament2", II, {"instr": "harp-rev", "bpm": TSX_MAX_BPM[II]}),
    ("lament2_tsx", II, {}),                               # 74 bpm, dry
    ("lament2_tsx_96", II, {"bpm": IIB_ALT_BPM}),          # 96 bpm, dry
]
# S1d entries no longer on the tape (kept for the tests / A-B by CLI)
EXTRA = [
    ("lament_pluck", IIB, {"instr": "harpsichord"}),       # S1 pluck harpsichord
    ("lament_buzz", IIB, {"instr": "tsx-buzz"}),           # S1d (6) envelope-saw bass
    ("lament_oct", IIB, {"instr": "tsx-oct"}),             # S1d (6) +12 on frame 0 only
]


def batch(srcdir, outdir, iib_bpm=None, gate=None, reverb=None):
    """Emit the audition set from the tsx JSON sources (tools/tsx_extract.py output);
    returns [(asmpath, info)].  iib_bpm overrides the tempo of the IIb entries that have
    none of their own (lament_tsx, default its JSON 74).  gate (GATES key) overrides the
    staccato gate of the S1e reverb entries (default GATE_DEFAULT; the S1d entries keep
    the tsx's 45 %)."""
    res = []
    for name, tune, kw in BATCH:
        kw = dict(kw)
        if tune == IIB and iib_bpm is not None and "bpm" not in kw:
            kw["bpm"] = iib_bpm
        if gate is not None and kw.get("instr") in dict(VARIANTS).values():
            kw["gate"] = gate
        if reverb is not None and kw.get("instr") in dict(VARIANTS).values():
            kw["reverb"] = reverb
        info = convert(os.path.join(srcdir, tune + ".json"), name=name, source="json", **kw)
        p = os.path.join(outdir, name + ".asm")
        write_asm(info, p)
        res.append((p, info))
    return res


GAME_GATE = 30      # the 5/16 gate ratio chosen for the game (S1e batch --gate 30)
GAME_TUNES = ["dungeon_crawl", "dangerous", "boss_fight", "level_complete", "game_win",
              "game_over", "lament"]    # music id 1..7 (lament = the IIb staccato theme)


def game(srcdir, outdir):
    """Emit the in-game songs: the hps_* (harp-rev) BATCH entries at GAME_GATE, one .asm each,
    plus game_songs.asm (INCLUDEs + mus_tab, id order); returns [(asmpath, info)].  Same
    code path as batch(--gate GAME_GATE): the files are byte-identical to those entries."""
    ents = {n: (t, kw) for n, t, kw in BATCH}
    res = []
    for t in GAME_TUNES:
        name = "hps_" + t
        tune, kw = ents[name]
        info = convert(os.path.join(srcdir, tune + ".json"), name=name, source="json",
                       **dict(kw, gate=GAME_GATE))
        p = os.path.join(outdir, name + ".asm")
        write_asm(info, p)
        res.append((p, info))
    with open(os.path.join(outdir, "game_songs.asm"), "w") as f:
        f.write("; generated by tools/abc2wzm.py --game - do not edit.\n")
        for p, info in res:
            f.write('    INCLUDE "%s"\n' % os.path.basename(p))
        f.write("mus_tab:\n")
        for p, info in res:
            f.write("    DW %s\n" % info["name"])
        f.write("mus_tab_end:\n")
    return res


def _reverb_arg(x):
    return x if x == "s1e" else int(x)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("abc", nargs="?")
    ap.add_argument("--tune", type=int, default=0, help="index of the X: tune in the file")
    ap.add_argument("--accidentals", choices=("strict", "naturals", "explicit"),
                    default=None,
                    help="strict: bare notes follow K:Fm (e/d flat); naturals: bare e/d "
                         "natural; explicit: key signature ignored, bare = natural. "
                         "Default: naturals for the Lament (= the tsx), strict otherwise")
    ap.add_argument("--source", choices=("abc", "json"), default="abc",
                    help="json: assets/sfx/music/src/*.json from tools/tsx_extract.py "
                         "(tsx ground truth; --accidentals/--tune ignored)")
    ap.add_argument("--ref-abc", metavar="FILE",
                    help="with --source json: also write the clean reference ABC")
    ap.add_argument("--strict-accidentals", dest="accidentals", action="store_const", const="strict")
    ap.add_argument("--naturals-for-bare-e-d", dest="accidentals", action="store_const",
                    const="naturals")
    ap.add_argument("--transpose", type=int, default=0)
    ap.add_argument("--transpose-v3", type=int, default=None, help="extra semitones for V3")
    ap.add_argument("--frames-per-eighth", type=Fraction,
                    help="fixed tempo, e.g. 16 or 750/37 (default: exact from the bpm)")
    ap.add_argument("--bpm", type=Fraction,
                    help="override the tune's tempo (quarter notes a minute); with --batch: "
                         "the Lament's (IIb) tempo, default its JSON bpm (74)")
    ap.add_argument("--instr", choices=sorted(INSTRUMENTS) + sorted(INSTR_SETS), default=None,
                    help="instrument or per-voice set (default: tsx for --source json, "
                         "harpsichord for ABC)")
    ap.add_argument("--loop", action="store_true", default=None,
                    help="loop (default: the JSON's loop flag; ABC: one-shot)")
    ap.add_argument("--no-legato", dest="legato", action="store_const", const="none",
                    default="slurs", help="ignore slurs: every note re-attacks")
    ap.add_argument("--legato-unmarked", dest="legato", action="store_const",
                    const="unmarked", help="also slur every run of unmarked (non-staccato) notes")
    ap.add_argument("--reverb", type=_reverb_arg, choices=REVERB_STEPS,
                    help="reverb level of the S1e organ / harpsichord tails: s1e (default), "
                         "0, 50 or 100 (percent of the tsx's slider; see REVERB_LEVELS)")
    ap.add_argument("--gate", type=int, choices=sorted(GATES),
                    help="staccato gate percent for every instrument (with --batch: the S1e "
                         "reverb entries only); default the instrument's own (S1e: %d)"
                         % GATE_DEFAULT)
    ap.add_argument("--name")
    ap.add_argument("-o", "--asm")
    ap.add_argument("--json")
    ap.add_argument("--batch", metavar="OUTDIR",
                    help="emit the standard audition set (BATCH) from the JSON sources")
    ap.add_argument("--game", metavar="OUTDIR",
                    help="emit the 7 in-game songs (hps_*, gate %d) + game_songs.asm" % GAME_GATE)
    ap.add_argument("--src", default=SRC_DIR, help="JSON source dir for --batch")
    a = ap.parse_args(argv)
    try:
        if a.game:
            for p, info in game(a.src, a.game):
                print(report(p, info), "->", p)
            return 0
        if a.batch:
            for p, info in batch(a.src, a.batch, a.bpm, a.gate, a.reverb):
                print(report(p, info), "->", p)
            return 0
        if not a.abc:
            ap.error("abc file required")
        info = convert(a.abc, a.tune, a.accidentals, a.transpose, a.frames_per_eighth,
                       True, a.instr, a.loop, a.name, a.transpose_v3, legato=a.legato,
                       source=a.source, bpm=a.bpm, gate=a.gate, reverb=a.reverb)
        print(report(a.abc, info))
        if a.ref_abc:
            if a.source != "json":
                ap.error("--ref-abc needs --source json")
            os.makedirs(os.path.dirname(a.ref_abc) or ".", exist_ok=True)
            with open(a.ref_abc, "w") as f:
                f.write(ref_abc(a.abc))
        if a.asm:
            write_asm(info, a.asm)
        if a.json:
            with open(a.json, "w") as f:
                json.dump(to_json(info), f, indent=1)
        return 1 if info["errors"] else 0
    except AbcError as e:
        print("ERROR:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
