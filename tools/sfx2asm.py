#!/usr/bin/env python3
"""sfx2asm.py - SND-5: sound-effect descriptions (JSON) -> the AY-slot SFX bank.

    python3 tools/sfx2asm.py [assets/sfx/effects.json] OUTDIR   ->  OUTDIR/sfx_ids.inc
                                                                     OUTDIR/sfx_data.asm
tools/build.sh runs it into OUTDIR/build/sfx/ (on the -i search path). sfx_ids.inc
(EQUs only) is INCLUDEd by src/main.asm after defs.asm; sfx_data.asm by src/ay.asm
(bank 3, the AY slot, read by the ISR's sfx_step).

Input (JSON):
  {"effects": [{"name": "HIT", "prio": 4, "frames": ["v15 tC3 n12", "v13 tA2 n14 x2", ...]}, ...]}
  name  -> SFX_<NAME>; ids are 0.. in file order (max 32); prio 0..7 (an id is never 0:
  the first effect needs prio >= 1). Top-level "aliases": {"NO": "FIZZ"} = SFX_NO EQU SFX_FIZZ.
  {"name": "X", "prio": p, "like": "BASE", "transpose": k}: BASE's frames, every pitch + k
  semitones (an own copy of the bytes: the format has no jumps).
  A frame (one 50 Hz frame of channel A) is a space-separated token list:
    vN      volume 0..15 (default: the previous frame's; the first frame needs one)
    tP      tone on at pitch P: a note name (C4 = MIDI 60, sharps "#": F#5) or an
            integer pitch index 0..95 (= MIDI - 12, the music player's pl_tp row)
    t       tone on, the previous pitch
    nN      noise on, noise period N 0..31 (R6)
    n       noise on, the previous noise period
    xK      the frame repeated K times (K >= 1)
  No t -> tone off that frame; no n -> noise off.

Id byte (what `ld a, SFX_<NAME> : call sfx_req` passes): prio << 5 | index, so
sfx_req compares priorities without a table (SFX_PRIO_MASK $E0).

Frame byte format (sound.md "SFX as built"; AYFX-like, 1-3 B a frame):
  B0 = bits 0-3 volume, bit 4 tone off, bit 5 a pitch byte follows,
       bit 6 a noise byte follows, bit 7 noise off
  [pitch index]  if bit 5 (only emitted when the tone is on and the pitch changed)
  [noise period] if bit 6 (only when the noise is on and the period changed)
  $FF = end of effect (bit 4 + bit 5 together is never emitted, so it is unambiguous)
Pitch / noise state carries over between frames; at an effect's start it is unknown
(the previous effect's), so the first tone / noise frame always carries its byte.

decode() is the reference the tests use (tests/sfx.py).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(ROOT, "assets", "sfx", "effects.json")
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
PITCH_MAX = 0x5F
END = 0xFF
F_TOFF, F_PIT, F_NSE, F_NOFF = 0x10, 0x20, 0x40, 0x80
MAX_EFFECTS = 32
STATUS_NAME = "STATUS"
STATUS_XP = (-7, 7)                           # the SFX_XP offsets sfx_msg writes (sfx_xp_tab)


def pitch(tok):
    if re.fullmatch(r"\d+", tok):
        p = int(tok)
    else:
        m = re.fullmatch(r"([A-G])(#?)(-?\d)", tok)
        if not m:
            raise ValueError("bad pitch %r" % tok)
        p = 12 * (int(m.group(3)) + 1) + NOTES[m.group(1)] + (1 if m.group(2) else 0) - 12
    if not 0 <= p <= PITCH_MAX:
        raise ValueError("pitch %r out of range 0..%d" % (tok, PITCH_MAX))
    return p


def parse_frames(frames):
    """-> list of (vol, pitch or None (tone off), noise or None (noise off))."""
    out, vol, pit, nse = [], None, None, None
    for f in frames:
        tone, noise, rep = False, False, 1
        for tok in f.split():
            k, arg = tok[0], tok[1:]
            if k == "v":
                vol = int(arg)
                if not 0 <= vol <= 15:
                    raise ValueError("volume %r" % tok)
            elif k == "t":
                tone = True
                if arg:
                    pit = pitch(arg)
            elif k == "n":
                noise = True
                if arg:
                    nse = int(arg)
                    if not 0 <= nse <= 31:
                        raise ValueError("noise %r" % tok)
            elif k == "x":
                rep = int(arg)
                if rep < 1:
                    raise ValueError("repeat %r" % tok)
            else:
                raise ValueError("bad token %r in %r" % (tok, f))
        if vol is None:
            raise ValueError("first frame needs a volume: %r" % f)
        if tone and pit is None:
            raise ValueError("'t' without a pitch yet: %r" % f)
        if noise and nse is None:
            raise ValueError("'n' without a period yet: %r" % f)
        out += [(vol, pit if tone else None, nse if noise else None)] * rep
    if not out:
        raise ValueError("no frames")
    return out


def encode(frames):
    b, cp, cn = [], None, None
    for vol, p, n in frames:
        b0 = vol | (F_TOFF if p is None else 0) | (F_NOFF if n is None else 0)
        extra = []
        if p is not None and p != cp:
            b0 |= F_PIT
            extra.append(p)
            cp = p
        if n is not None and n != cn:
            b0 |= F_NSE
            extra.append(n)
            cn = n
        assert b0 != END
        b += [b0] + extra
    return b + [END]


def decode(data, off=0, state=(0, 0)):
    """Reference decoder: -> list of (pitch index, vol, mixer A bits, noise) per frame, with
    the engine's carried state (pitch, noise) as `state`. Mixer A bits = R7 bits 0 / 3."""
    out, p, n = [], state[0], state[1]
    while True:
        b0 = data[off]
        off += 1
        if b0 == END:
            return out
        if b0 & F_PIT:
            p = data[off]
            off += 1
        if b0 & F_NSE:
            n = data[off]
            off += 1
        out.append((p, b0 & 15, (b0 >> 4) & 0x09, n))


def load(src):
    with open(src) as f:
        effects = json.load(f)["effects"]
    if not 1 <= len(effects) <= MAX_EFFECTS:
        raise ValueError("1..%d effects" % MAX_EFFECTS)
    res, names = [], set()
    for i, e in enumerate(effects):
        name = e["name"].upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in names:
            raise ValueError("bad / duplicate name %r" % name)
        names.add(name)
        prio = int(e["prio"])
        if not 0 <= prio <= 7:
            raise ValueError("%s: prio 0..7" % name)
        if "like" in e:                        # a variant: another effect's frames, transposed
            base = next((b for b in effects if b["name"].upper() == e["like"].upper()
                         and "like" not in b), None)
            if base is None:
                raise ValueError("%s: \"like\": %r names no effect with its own frames"
                                 % (name, e["like"]))
            k = int(e.get("transpose", 0))
            fr = [(v, None if p is None else p + k, n) for v, p, n in parse_frames(base["frames"])]
            if any(p is not None and not 0 <= p <= PITCH_MAX for _, p, _ in fr):
                raise ValueError("%s: transposed pitch out of range" % name)
        else:
            fr = parse_frames(e["frames"])
        if prio << 5 | i == 0:
            raise ValueError("%s: id 0 is 'none' (index 0 needs prio >= 1)" % name)
        if name == STATUS_NAME:               # sfx_msg's SFX_XP offsets (src/sfx2.asm sfx_xp_tab) stay in pl_tp
            lo = min(p for _, p, _ in fr if p is not None) + STATUS_XP[0]
            hi = max(p for _, p, _ in fr if p is not None) + STATUS_XP[1]
            if not (0 <= lo and hi <= PITCH_MAX):
                raise ValueError("STATUS pitch %d..%d with SFX_XP %+d..%+d leaves 0..%d" % (lo, hi, *STATUS_XP, PITCH_MAX))
        res.append(dict(name=name, idx=i, prio=prio, id=prio << 5 | i, frames=fr, data=encode(fr)))
    return res


def load_aliases(src, effects):
    """-> [(alias, target effect dict)] from the top-level "aliases" (SFX_<alias> EQU SFX_<target>)."""
    with open(src) as f:
        al = json.load(f).get("aliases", {})
    by = {e["name"]: e for e in effects}
    out = []
    for a, t in al.items():
        a, t = a.upper(), t.upper()
        if a in by or t not in by:
            raise ValueError("bad alias %r -> %r" % (a, t))
        out.append((a, by[t]))
    return out


def load_reserved(src, effects):
    """-> the top-level "reserved" names (indices SFX_COUNT.. kept free; SFX_IDX_<name> EQU index)."""
    with open(src) as f:
        r = [x.upper() for x in json.load(f).get("reserved", [])]
    if len(effects) + len(r) > MAX_EFFECTS or len(set(r)) != len(r):
        raise ValueError("effects + reserved > %d / duplicate reserved" % MAX_EFFECTS)
    return r


def write(effects, outdir, src):
    os.makedirs(outdir, exist_ok=True)
    rel = os.path.relpath(src, ROOT)
    total = sum(len(e["data"]) for e in effects) + 2 * len(effects)
    ids = ["; generated by tools/sfx2asm.py from %s - do not edit." % rel,
           "; id = prio << 5 | index (sfx_req compares the top 3 bits)"]
    for e in effects:
        ids.append("SFX_%-12s EQU $%02X     ; prio %d, %d frames, %d B"
                   % (e["name"], e["id"], e["prio"], len(e["frames"]), len(e["data"])))
    for a, t in load_aliases(src, effects):
        ids.append("SFX_%-12s EQU SFX_%s     ; alias" % (a, t["name"]))
    for k, r in enumerate(load_reserved(src, effects)):
        ids.append("SFX_IDX_%-8s EQU %d     ; reserved index (3F): prio << 5 | %d once authored" % (r, len(effects) + k, len(effects) + k))
    ids.append("SFX_COUNT        EQU %d" % len(effects))
    ids.append("SFX_DATA_LEN     EQU %d     ; sfx_tab + effects" % total)
    with open(os.path.join(outdir, "sfx_ids.inc"), "w") as f:
        f.write("\n".join(ids) + "\n")
    asm = ["; generated by tools/sfx2asm.py from %s - do not edit." % rel,
           "; sfx_tab: DW effect, stride 2, index order 0..SFX_COUNT-1. Frame format: sfx2asm.py.",
           "sfx_tab:"]
    for e in effects:
        asm.append("                DW   sfx_d_%s" % e["name"].lower())
    for e in effects:
        asm.append("sfx_d_%s:" % e["name"].lower())
        d = e["data"]
        for k in range(0, len(d), 16):
            asm.append("                DB   " + ", ".join("$%02X" % x for x in d[k:k + 16]))
    asm.append("sfx_data_end:")
    asm.append("                ASSERT sfx_data_end - sfx_tab == SFX_DATA_LEN")
    with open(os.path.join(outdir, "sfx_data.asm"), "w") as f:
        f.write("\n".join(asm) + "\n")
    return total


def main(argv):
    if len(argv) == 1:
        src, out = DEFAULT_SRC, argv[0]
    elif len(argv) == 2:
        src, out = argv
    else:
        print(__doc__.split("\n")[2], file=sys.stderr)
        return 2
    effects = load(src)
    total = write(effects, out, src)
    for e in effects:
        assert decode(e["data"]) and len(decode(e["data"])) == len(e["frames"])
    print("sfx2asm: %d effects, %d B (table %d + data %d)"
          % (len(effects), total, 2 * len(effects), total - 2 * len(effects)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
