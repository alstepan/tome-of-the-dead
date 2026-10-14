#!/usr/bin/env python3
"""Tests for tools/abc2wzm.py + tools/wzm_ref.py (no emulator). The 7 concept ABCs live
untracked in the main checkout; they are located via $WZ_CONCEPTS, ./assets/sfx/concepts
or the main checkout and their tests skip when absent. The golden hash uses an inline ABC.
Run: python3 tests/abc_tools_test.py"""
import json
import os
import sys
import tempfile
import unittest
from fractions import Fraction

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import abc2wzm as a2w  # noqa: E402
import tsx_model  # noqa: E402
import wzm_ref  # noqa: E402


def concepts_dir():
    for d in (os.environ.get("WZ_CONCEPTS"), os.path.join(REPO, "assets/sfx/concepts"),
              "/Users/alexs/sources/zxspectrum/wazhack/assets/sfx/concepts"):
        if d and os.path.isdir(os.path.join(d, "short-melodies")):
            return d
    return None


CD = concepts_dir()

TUNE = """X:1
T:t
M:4/4
L:1/8
Q:1/4=75
K:Fm
V:V1
.f2 ._a .c' .f'2 .c' ._a | f2 e2 d2 z2 |]
V:V2
c'2 f' _a _a2 f _a | c2 c2 c2 c-c |]
V:V3
F,2 _A,2 C2 F2 | F,8 |]
"""
# v0.1: a rest no longer plays the arp0 period on its frame 0 (volume 0 there, so the
# audio is unchanged; the v0 hash was bd7e0811...). Gate byte is now gate_sh.
GOLDEN = "59944fff791f0b4d416c2680c5854b5ba0fa60c7b2bcd44cdc0e345098775e75"

SLUR = """X:1
T:s
M:4/4
L:1/8
Q:1/4=75
K:Fm
V:V1
(f2 g2 a2) c2 | (.c .d .e) .f (g2 g2) |]
V:V2
c8 | c4 c4 |]
V:V3
F,8 | F,8 |]
"""
SLUR_GOLDEN = "80be79d18b852e31d403850d5f8e0097983d713a35338f0b1b0d8e95f8f25823"  # organ, fpe 4 (wzm_ref v0.1)


def convert_text(text, **kw):
    with tempfile.NamedTemporaryFile("w", suffix=".abc", delete=False) as f:
        f.write(text)
    try:
        return a2w.convert(f.name, **kw)
    finally:
        os.unlink(f.name)


class Inline(unittest.TestCase):
    def test_bar_sums_ok(self):
        self.assertEqual(convert_text(TUNE)["errors"], [])

    def test_bad_bar_detected(self):
        bad = TUNE.replace("c2 c2 c2 c-c", "c2 c2 c2 c")
        self.assertTrue(any("wrong sum" in e or "last bar" in e
                            for e in convert_text(bad)["errors"]))

    def test_chord_rejected(self):
        with self.assertRaises(a2w.AbcError):
            convert_text(TUNE.replace("F,2 _A,2", "[F,A,]2 _A,2"))

    def test_bare_e_d_readings(self):
        s = convert_text(TUNE, accidentals="strict")["tune"]["voices"]["V1"]["notes"]
        n = convert_text(TUNE, accidentals="naturals")["tune"]["voices"]["V1"]["notes"]
        # f2 e2 d2 : bare e/d are Eb/Db when strict, E/D natural otherwise
        self.assertEqual([x["midi"] for x in s[-3:-1]], [75, 73])
        self.assertEqual([x["midi"] for x in n[-3:-1]], [76, 74])

    def test_tie_merge_and_blob_roundtrip(self):
        i = convert_text(TUNE, fpe=Fraction(4), loop=True)
        v2 = i["tune"]["voices"]["V2"]["notes"]
        self.assertEqual(v2[-1]["len"], Fraction(2, 8))
        regs = wzm_ref.play(i["bytes"], max_frames=200)
        self.assertEqual(len(regs), 200)  # looping song never finishes

    def test_oneshot_finishes(self):
        regs = wzm_ref.play(convert_text(TUNE, fpe=Fraction(4))["bytes"])
        self.assertEqual(len(regs), 64 + 1)  # 2 bars x 8 eighths x 4 frames + silent tail

    def test_slur_events(self):
        i = convert_text(SLUR, fpe=Fraction(4))
        ev = i["events"][0]
        # (f g a) c | (.c .d .e) .f (g4 g4): legato into the next note, last of a slur not;
        # slurred notes lose their staccato gate; never legato into the same pitch
        self.assertEqual([e[3] for e in ev], [True, True, False, False,
                                              True, True, False, False, False, False])
        self.assertEqual([e[2] for e in ev], [False] * 4 + [False, False, True, True]
                         + [False, False])
        self.assertEqual(i["bytes"].count(bytes([a2w.CMD_LEGATO])), 4)
        none = convert_text(SLUR, fpe=Fraction(4), legato="none")
        self.assertEqual([e[3] for e in none["events"][0]], [False] * 10)
        self.assertEqual([e[2] for e in none["events"][0]][4:8], [True] * 4)

    def test_slur_oracle(self):
        """Legato note: no arp0 frame, the volume table runs on (no re-attack)."""
        i = convert_text(SLUR, fpe=Fraction(4))
        regs = wzm_ref.play(i["bytes"])
        per = [r[0] | r[1] << 8 for r in regs]
        vol = [r[8] for r in regs]
        tp = wzm_ref.TP
        self.assertEqual(per[0], tp[77 + 12 - 12])          # f: attack, arp0 +12
        self.assertEqual(per[8], tp[79 - 12])               # g slurred: no arp0 frame
        self.assertEqual(vol[:12], [15, 13, 12, 11, 10, 9, 9, 8, 8, 7, 7, 6])
        self.assertEqual(per[24], tp[72 + 12 - 12])         # c after the slur: attack
        self.assertEqual(vol[24], 15)
        plain = wzm_ref.play(convert_text(SLUR, fpe=Fraction(4), legato="none")["bytes"])
        self.assertEqual(plain[8][8], 15)                   # no-legato: g re-attacks

    def test_slur_golden(self):
        i = convert_text(SLUR, fpe=Fraction(4), instr="organ")
        self.assertEqual(wzm_ref.stream_hash(wzm_ref.play(i["bytes"])), SLUR_GOLDEN)

    def test_legato_before_rest_invalid(self):
        b = bytearray(convert_text(SLUR, fpe=Fraction(4))["bytes"])
        o = b[0] | b[1] << 8
        b[o:o + 3] = bytes([a2w.CMD_LEGATO, a2w.REST, 4])   # $85 then a rest
        with self.assertRaises(ValueError):
            wzm_ref.play(bytes(b))

    def test_tuplet_rejected(self):
        with self.assertRaises(a2w.AbcError):
            convert_text(TUNE.replace("F,2 _A,2", "(3F,_A,C F,"))

    def test_key_signatures(self):
        self.assertEqual(a2w.key_signature("Fm"), {"B": -1, "E": -1, "A": -1, "D": -1})
        self.assertEqual(a2w.key_signature("F"), {"B": -1})
        self.assertEqual(a2w.key_signature("Dm"), {"B": -1})
        self.assertEqual(a2w.key_signature("C"), {})
        self.assertEqual(a2w.key_signature("G"), {"F": 1})

    def test_accidental_rules(self):
        t = TUNE.replace("F,2 _A,2 C2 F2 | F,8", "=A,2 A,2 C2 F2 | A,8")
        v3 = convert_text(t)["tune"]["voices"]["V3"]["notes"]
        self.assertEqual([n["midi"] for n in v3], [57, 57, 60, 65, 56])  # = lasts the bar only
        t = TUNE.replace("F,2 _A,2 C2 F2 | F,8", "F,2 C2 F2 =A,2- | A,8")
        v3 = convert_text(t)["tune"]["voices"]["V3"]["notes"]
        self.assertEqual([(n["midi"], n["len"]) for n in v3][-1], (57, Fraction(10, 8)))

    def test_boundary_rounding_keeps_voices_aligned(self):
        t = TUNE.replace("F,2 _A,2 C2 F2", "F,/2F,/2F,/2F,/2 F,/2F,/2F,/2F,/2 F,4")
        i = convert_text(t, fpe=Fraction(21))               # 1/16 = 10.5 frames
        sums = [sum(e[1] for e in ev) for ev in i["events"]]
        self.assertEqual(len(set(sums)), 1)
        self.assertEqual([e[1] for e in i["events"][2]][:4], [11, 10, 11, 10])

    def test_golden_register_stream(self):
        i = convert_text(TUNE, fpe=Fraction(4), instr="harpsichord")
        self.assertEqual(wzm_ref.stream_hash(wzm_ref.play(i["bytes"])), GOLDEN)


@unittest.skipUnless(CD, "concept ABCs not available")
class RealFiles(unittest.TestCase):
    def test_short_melodies(self):
        for n in a2w.SHORT:
            i = a2w.convert(os.path.join(CD, "short-melodies", "tome_%s.abc" % n))
            self.assertEqual(i["errors"], [], n)

    def test_lament(self):
        for acc in ("strict", "naturals"):
            i = a2w.convert(os.path.join(CD, a2w.LAMENT), accidentals=acc)
            self.assertEqual(i["errors"], [])
            self.assertEqual([len([e for e in ev if e[0] is not None])
                              for ev in i["events"]], [180, 184, 192])
            # Q:1/4=96, exact tempo 125/8 frames an eighth (was 16 by whole-frame fitting)
            self.assertEqual(sum(e[1] for e in i["events"][0]), 4000)

    def test_lament_default_naturals(self):
        """The Lament's default reading is 'naturals' (= the tsx); other ABCs strict."""
        self.assertEqual(a2w.convert(os.path.join(CD, a2w.LAMENT))["accidentals"], "naturals")
        self.assertEqual(a2w.convert(os.path.join(CD, "short-melodies", "tome_dangerous.abc"))
                         ["accidentals"], "strict")

    def test_lament_strict_flats(self):
        """User report 'missing flats': strict = every bare e/d of the Lament is Eb/Db."""
        i = a2w.convert(os.path.join(CD, a2w.LAMENT), accidentals="strict")
        bare = [n for v in i["tune"]["voices"].values() for n in v["notes"]
                if n["midi"] is not None and n["tok"].lstrip(".")[0] in "edED"]
        self.assertEqual(len(bare), 30)
        self.assertTrue(all(n["midi"] % 12 in (1, 3) for n in bare))

    def test_dangerous_bar2_g_natural(self):
        """No bar lines: the bar-1 _g42 must not carry into bar 2 (g2 = G5)."""
        v1 = a2w.convert(os.path.join(CD, "short-melodies", "tome_dangerous.abc"))["tune"]
        notes = v1["voices"]["V1"]["notes"]
        self.assertEqual([(n["bar"], n["midi"]) for n in notes],
                         [(1, 77), (1, 78), (1, 77), (1, 76), (2, 77), (2, 80), (2, 79), (2, 76)])


SRC = os.path.join(REPO, "assets/sfx/music/src")
TUNES = list(a2w.SHORT) + ["f_minor_staccato_theme", "f_minor_lament"]
# (notes per voice A/B/C, beats per voice) from the tsx; IIb also (93, 45, 47) staccato
EXPECT = {"dungeon_crawl": ([20, 18, 16], 16), "dangerous": ([8, 8, 12], 8),
          "boss_fight": ([30, 30, 30], 16), "level_complete": ([11, 11, 7], 8),
          "game_win": ([10, 10, 8], 8), "game_over": ([8, 8, 8], 8),
          "f_minor_staccato_theme": ([180, 184, 192], 128),
          "f_minor_lament": ([180, 184, 192], 128)}


def load_json(t):
    with open(os.path.join(SRC, t + ".json")) as f:
        return json.load(f)


class JsonSource(unittest.TestCase):
    """--source json (tools/tsx_extract.py output, the tsx ground truth)."""

    def test_counts_and_beats(self):
        for t in TUNES:
            j = load_json(t)
            vs = [j["voices"][k] for k in "ABC"]
            self.assertEqual([len(v) for v in vs], EXPECT[t][0], t)
            self.assertEqual([sum(n["beats"] for n in v) for v in vs], [EXPECT[t][1]] * 3, t)

    def test_lament_ii_legato(self):
        """tsx 'II. Catacomb Lament (Legato)' = IIb without its staccato: 128 beats a voice,
        no staccato flag, and the same pitch and length at every index as IIb."""
        ii, iib = load_json("f_minor_lament"), load_json("f_minor_staccato_theme")
        self.assertEqual(ii["title"], "II. Catacomb Lament (Legato)")
        self.assertEqual((ii["bpm"], ii["loop"]), (iib["bpm"], iib["loop"]))
        for k in "ABC":
            self.assertEqual(sum(n["beats"] for n in ii["voices"][k]), 128, k)
            self.assertFalse(any(n["stac"] for n in ii["voices"][k]), k)
            self.assertEqual([(n["midi"], n["pitch"], n["beats"]) for n in ii["voices"][k]],
                             [(n["midi"], n["pitch"], n["beats"]) for n in iib["voices"][k]], k)

    def test_iib_staccato_counts(self):
        j = load_json("f_minor_staccato_theme")
        self.assertEqual([sum(n["stac"] for n in j["voices"][k]) for k in "ABC"], [93, 45, 47])

    def test_convert_ok(self):
        for t in TUNES:
            i = a2w.convert(os.path.join(SRC, t + ".json"), source="json", loop=True)
            self.assertEqual(i["errors"], [], t)

    def test_ref_abc_roundtrip(self):
        """The clean reference ABC parses (strict, K:Fm) back to the JSON pitches, lengths,
        staccato and bar sums: naturals/octaves/bars all written explicitly."""
        for t in TUNES:
            p = os.path.join(SRC, t + ".json")
            j = load_json(t)
            tune = a2w.parse_abc(a2w.ref_abc(p))[0]
            self.assertEqual(a2w.validate(tune, None), [], t)
            for vk, vn in zip("ABC", ("V1", "V2", "V3")):
                got = [(n["midi"], n["len"] * 4, n["stac"]) for n in tune["voices"][vn]["notes"]]
                want = [(n["midi"], Fraction(n["beats"]), n["stac"]) for n in j["voices"][vk]]
                self.assertEqual(got, want, (t, vk))

    def test_ref_abc_files_current(self):
        for t in TUNES:
            path = os.path.join(REPO, "assets/sfx/music/ref", t + ".abc")
            with open(path) as f:
                self.assertEqual(f.read(), a2w.ref_abc(os.path.join(SRC, t + ".json")), t)

    @unittest.skipUnless(CD, "concept ABCs not available")
    def test_iib_vs_old_abc(self):
        """Old (+12 shifted, hence transpose -12) IIb ABC vs the JSON: with bare e/d natural
        ('naturals', 'explicit') the event lists are identical; under 'strict' exactly the 30
        bare E/D naturals differ (the ABC reads them as Eb/Db, one semitone low); lengths,
        gates and staccato never differ.  Staccato counts of the ABC are 93/45/47 too."""
        abc = os.path.join(CD, a2w.LAMENT)
        j = a2w.convert(os.path.join(SRC, "f_minor_staccato_theme.json"), source="json",
                        fpe=Fraction(20))
        with open(abc, encoding="utf-8") as f:
            old = a2w.parse_abc(f.read())[0]
        self.assertEqual([sum(n["stac"] for n in old["voices"][v]["notes"])
                          for v in ("V1", "V2", "V3")], [93, 45, 47])
        for acc, ndiff in (("strict", 30), ("naturals", 0), ("explicit", 0)):
            b = a2w.convert(abc, accidentals=acc, transpose=-12, fpe=Fraction(20))
            diffs = []
            for ej, eb in zip(j["events"], b["events"]):
                self.assertEqual(len(ej), len(eb))
                for x, y in zip(ej, eb):
                    if x != y:
                        self.assertEqual(x[1:], y[1:])       # only the pitch may differ
                        diffs.append(x[0] - y[0])
            self.assertEqual(len(diffs), ndiff, acc)
            self.assertTrue(all(d == 1 for d in diffs), acc)  # natural vs flat


# wzm_ref register stream of one pass (tsx JSON source).  S1d hashes: unchanged by
# WZM v0.3 (the tail/rest/gate changes are invisible with drop 15, rel_per 1) - except
# lament_buzz, whose R7 is now $38 on the frames where the buzzer is silent (v0.2:
# the header's $3C on every frame; sound identical: volume 0 there).
S1D = [("tune_" + n, n, {}) for n in a2w.SHORT]     # S1d cues at their own tempo
TSX_GOLDEN = {
    "tune_dungeon_crawl": "eda4d3fc0417432cac41ae1ac5cc5ce5567185d41f359d9fd6ae810bb32b3e7f",
    "tune_dangerous": "d30edda84b62038b3a76f91422336cf5b0c049ab721981d6fb48a7cc3d77be04",
    "tune_boss_fight": "4ca13a5275b61992bba38677242573346901059f4e42d283134a1fcb264c7ce4",
    "tune_level_complete": "78dee28c32ecfbdfa21797fa30694b0c2a3d6dbb937717e5fd458bd7944f9839",
    "tune_game_win": "4c9112bb1fa77f9deed954b0bdee9178d2b38fa55f5ea73a0e323cd354c1aff6",
    "tune_game_over": "82de55a5a70150634b29ff5b9732acffe3f96f8529707970213805b19f0b60f7",
    "lament_tsx": "5da96061e926664c45d49b6533f5ad538e712f01ca13166f19d40c8d39dcc9f1",
    "lament_tsx_96": "609e5f0fd1467aa3634f96ad2b4492c69a6f51533d0171b33462cb3de4dd1c76",
    "lament_pluck": "2c80ecb72bbc4868eb020a81cc2d7da6179abf8708241fe8783d3f4327764afe",
    "lament_buzz": "2c6b6ab7a2b4fda3b3a07794e30fdb4d5bc1216ee54beaa9bbcc05a84284ac0b",
    "lament_oct": "bfb853d88b6674cf8c2ba06feb3a91b59406b4c79199426049868cf61938e2e9",
    "lament2_tsx": "a4a03d2e21b4885c9994f2c79ff6fc0280b650f8413bf2b96300898082e724b7",
    "lament2_tsx_96": "89e0eb586ccfa2bbf22a5dc1e9b3ab3314f6629570f26cc90844db771df65909",
}
# S1e tape entries (organ / harpsichord + reverb tails, tsx-max tempo, 56 % gate)
S1E_GOLDEN = {
    "org_lament2": "42f259449e27e0aa6f11c98bc2ebbc66dcde2b51786655f8d38a767e9083a5dd",
    "hps_lament2": "392e785056eeb17c818f58d8a2e08d07a90cd7d5da196e5cfdcf1c2aa24734c7",
    "org_dungeon_crawl": "38eb2bd4e41d43d49ae6ad97b3d8067ef2e19e1c975f333c9c78c4933ee8d352",
    "org_dangerous": "c23557291e637925de7d8bbfbdf2633ca266afde91a4cff67b9149ea6ee3ae27",
    "org_boss_fight": "1ff33494de638b7a9c883ba816b6709552c6326eaca58e61754d68a6df2dc89a",
    "org_level_complete": "faad4315585b6124cef3419a573556303ea6af576400035634f898c837818fca",
    "org_game_win": "a118b66cb3797c57f7360ca6b82d4d8172b8386fc2876a9c83a1ba053a59cbb4",
    "org_game_over": "0ef213771f2b6e2f3ce258116548c138fbd22fda1d872a80d189425e9f92cdd8",
    "org_lament": "f7955fa93111d19e07b6fb409bd020c146af7f31c74913bfc6255c320a96fe53",
    "hps_dungeon_crawl": "c7a6becc399c6a95c08bc3b997851467d8c52274a2167638c6575fe63ff7f96d",
    "hps_dangerous": "e5b4ca4a9670e7be630db18383f2882779fb4d0b0baf226f799d2e8044ff2f85",
    "hps_boss_fight": "c212c2fa130b16d8db212bacf6432767a37c48a956583734daf2e5998c3d97a4",
    "hps_level_complete": "df5e274ff82915b419d5ca3d3d165797476319c131cbff928692143d448d05a5",
    "hps_game_win": "ec88885c88fbd4e44506a7a73b21c7edb9117f5e1634e40b4b6d9ee28024c6ef",
    "hps_game_over": "5dbd0beb869510655766f54e99419709b8cb7a4e8fafe3ce093f757e83b35e7b",
    "hps_lament": "60406161635bc5fa3a5fe7ac003e18ccc48434369ac88a783ec6e7bcc35b09ba",
}
# staccato notes whose gate is 1 frame short of the 50 Hz tsx model (frame phase: no
# dur-only formula can hit these; round(0.45 dur) misses the same 32; at 9/16 and
# 96 bpm round(9/16 dur) misses the same 37)
TSX_LEVEL_BAD = {"lament_tsx": 32, "lament_buzz": 32, "lament_oct": 32}
S1E_SHORT_GATES = {"org_lament": 37, "hps_lament": 37}
S1E_CUT = tsx_model.GATE_CUT[a2w.GATE_DEFAULT]


def spec(name):
    return next(b for b in a2w.BATCH + a2w.EXTRA + S1D if b[0] == name)


def batch_run(name, gate=None, reverb=None):
    _, tune, kw = spec(name)
    p = os.path.join(SRC, tune + ".json")
    j = tsx_model.load(p)
    if gate is not None:
        kw = dict(kw, gate=gate)
    if reverb is not None:
        kw = dict(kw, reverb=reverb)
    info = a2w.convert(p, name=name, source="json", **kw)
    nfr = len(tsx_model.model(j, kw.get("bpm"))[0])
    regs = wzm_ref.play(info["bytes"], max_frames=nfr)
    return j, info, regs, kw.get("bpm")


class TsxFaithful(unittest.TestCase):
    """S1d: the tsx-faithful instrument set against tools/tsx_model.py (main.tsx sampled
    at 50 Hz: constant level 13/13/14, staccato 45 % then 0, exact bpm)."""

    def test_instrument_bytes(self):
        info = a2w.convert(os.path.join(SRC, "dangerous.json"), source="json", name="d")
        b, lab = info["blob"].bytes_()
        self.assertEqual(b[6:10], bytes([0, 0, 1, 0]))                    # no buzzer shape
        self.assertEqual(b[lab["d_inst_tsx13"]:lab["d_inst_tsx13"] + 10],
                         bytes([0, 0xFF, 0, 0, 15, 2, 3, a2w.CUT, 13, 0xFF]))  # s1 = 1, s2 = 4
        self.assertEqual(b[lab["d_inst_tsx14"] + 8], 14)

    def test_gate_45(self):
        """(dur >> 1) - (dur >> 4) == round(0.45 dur) for every staccato length the IIb
        produces at 66, 74 and 96 bpm, and is >= 1 from 2 frames."""
        for d in (15, 16, 20, 21, 22, 23, 31, 32, 40, 41, 45, 46):
            self.assertEqual(a2w.inst_gate("tsx13", d, True), int(Fraction(45, 100) * d
                                                                   + Fraction(1, 2)), d)
        self.assertEqual(a2w.inst_gate("harpsichord", 21, True), 11)      # old 50 %, up
        self.assertEqual(a2w.inst_gate("organ", 21, True), 16)            # old 75 %
        self.assertTrue(all(a2w.inst_gate("tsx13", d, True) >= 1 for d in range(2, 256)))

    def test_gate_zero_rejected(self):
        t = TUNE.replace(".f2 ._a", ".f/2 .f/2 ._a")
        with self.assertRaises(a2w.AbcError):          # a 1-frame staccato: gate 0
            convert_text(t, fpe=Fraction(2), instr="tsx")

    def test_exact_tempo(self):
        _, info, _, _ = batch_run("lament_tsx")
        self.assertEqual(info["fpe"], Fraction(750, 37))                  # 74 bpm exactly
        self.assertEqual([sum(e[1] for e in ev) for ev in info["events"]], [5189] * 3)
        _, info, _, _ = batch_run("lament_tsx_96")
        self.assertEqual([sum(e[1] for e in ev) for ev in info["events"]], [4000] * 3)
        i = a2w.convert(os.path.join(SRC, a2w.IIB + ".json"), source="json", bpm=80)
        self.assertEqual(sum(e[1] for e in i["events"][0]), 4800)

    def test_golden_streams(self):
        for name in TSX_GOLDEN:
            self.assertEqual(wzm_ref.stream_hash(batch_run(name)[2]), TSX_GOLDEN[name], name)

    def test_vs_tsx_model(self):
        """Pitches exact on every sounding frame (except the experiments' arp0 frame),
        levels exact except the pinned 1-frame-short staccato gates, every staccato gate
        within 1 frame of the model."""
        for name in TSX_GOLDEN:
            if name == "lament_pluck":
                continue
            j, _, regs, bpm = batch_run(name)
            c = tsx_model.compare(j, regs, bpm, wzm_ref.TP)
            if name != "lament_oct":
                self.assertEqual(c["pitch_bad"], 0, name)
            self.assertEqual(c["level_bad"], TSX_LEVEL_BAD.get(name, 0), name)
            self.assertTrue(set(c["gate_diffs"]) <= {-1, 0}, (name, c["gate_diffs"]))

    def test_loudness(self):
        """Legato louder than staccato; both per-note means and their ratio within 10 %
        of the tsx's (0.795 / 0.349 for the Lament)."""
        j, _, regs, _ = batch_run("lament_tsx")
        tl, ts = tsx_model.tsx_loudness(j)
        self.assertAlmostEqual(tl, 0.795, places=3)
        self.assertAlmostEqual(ts, 0.349, places=3)
        for name in ("lament_tsx", "lament_tsx_96"):
            j2, _, regs2, bpm = batch_run(name)
            c = tsx_model.compare(j2, regs2, bpm)
            self.assertGreater(c["leg"], c["stac"], name)
            self.assertLess(abs(c["leg"] / tl - 1), 0.10, name)
            self.assertLess(abs(c["stac"] / ts - 1), 0.10, name)
            self.assertLess(abs((c["leg"] / c["stac"]) / (tl / ts) - 1), 0.10, name)
        for t in a2w.SHORT:
            j, _, regs, _ = batch_run("tune_" + t)
            c = tsx_model.compare(j, regs)
            self.assertLess(abs(c["leg"] / tsx_model.tsx_loudness(j)[0] - 1), 0.10, t)

    def test_pluck_is_wrong(self):
        """The S1 decaying harpsichord: legato:staccato ratio far below the tsx's (the
        user's 'legato shy, staccato loud')."""
        j, _, regs, _ = batch_run("lament_pluck")
        c = tsx_model.compare(j, regs)
        tl, ts = tsx_model.tsx_loudness(j)
        self.assertLess(c["leg"] / c["stac"], 0.6 * tl / ts)

    def test_buzzer_oracle(self):
        """Saw (hps, S1d buzz) and triangle (organ) buzzer: R7 = $3C exactly on buzzer
        frames, R11/R12 = (TP + 8) >> 4 (saw) or that halved rounding up (triangle)."""
        for name, tri in (("lament_buzz", False), ("hps_lament", False),
                          ("org_lament", True), ("org_game_over", True)):
            _, info, regs, _ = batch_run(name)
            self.assertEqual(info["bytes"][9], a2w.ENV_TRI if tri else a2w.ENV_SAW, name)
            for r in regs[:600]:
                self.assertEqual(r[7], a2w.MIXER_BUZZ_C if r[10] & a2w.VOL_ENV
                                 else a2w.MIXER_TONE, name)
                if r[10] & a2w.VOL_ENV:
                    e = ((r[4] | r[5] << 8) + 8) >> 4
                    self.assertEqual(r[11] | r[12] << 8, (e + 1) >> 1 if tri else e, name)
            self.assertTrue(any(r[10] & a2w.VOL_ENV for r in regs[:400]), name)
        with self.assertRaises(a2w.AbcError):          # envelope instrument off voice C
            a2w.build_song("x", [[(60, 4, False, False)]] * 3, "tsxbuzz", False)


class S1eReverb(unittest.TestCase):
    """S1e: organ / harpsichord + reverb tails at the tsx-max tempo, 9/16 gate."""

    def test_tempo_tsx_max(self):
        for t in a2w.SHORT + [a2w.IIB]:
            self.assertEqual(a2w.TSX_MAX_BPM[t], max(96, load_json(t)["bpm"]), t)
        self.assertEqual(a2w.TSX_MAX_BPM["boss_fight"], 106)
        names = [b[0] for b in a2w.BATCH]
        self.assertEqual(len(names), 20)
        self.assertEqual(names[14:], ["lament_tsx", "lament_tsx_96", "org_lament2",
                                      "hps_lament2", "lament2_tsx", "lament2_tsx_96"])
        self.assertEqual(names[:7], ["org_" + n for n in a2w.SHORT] + ["org_lament"])
        self.assertEqual(names[7:14], ["hps_" + n for n in a2w.SHORT] + ["hps_lament"])

    def test_golden_streams(self):
        for name in S1E_GOLDEN:
            self.assertEqual(wzm_ref.stream_hash(batch_run(name)[2]), S1E_GOLDEN[name], name)

    def test_gates_56_62(self):
        """9/16 = round(dur >> 1) + (dur >> 4) and 5/8 = round(dur >> 1) + (dur >> 3):
        within 1 frame of round(f dur) for every length 8..255, >= 1 from 2 frames, and
        the oracle's formula = the converter's."""
        for g, f in ((30, Fraction(5, 16)), (56, Fraction(9, 16)), (62, Fraction(5, 8))):
            for d in range(8, 256):
                self.assertLessEqual(abs(a2w.gate_of(a2w.GATES[g], d) - int(f * d + Fraction(1, 2))),
                                     1, (g, d))
            self.assertTrue(all(a2w.gate_of(a2w.GATES[g], d) >= 1 for d in range(2, 256)))
        self.assertEqual([a2w.gate_of(a2w.GATES[56], d) for d in (15, 16, 31, 32)], [8, 9, 17, 18])
        self.assertEqual([a2w.gate_of(a2w.GATES[100], d) for d in range(1, 256)],
                         list(range(1, 256)))                     # 100 %: the whole note
        for g in (30, 45, 56, 62, 100):
            info = a2w.convert(os.path.join(SRC, "dangerous.json"), source="json", name="d",
                               instr="organ-rev", gate=g)
            b, lab = info["blob"].bytes_()
            ins = wzm_ref.Inst(b, lab["d_inst_org13"])
            for d in range(2, 256):
                self.assertEqual(ins.gate(d, True), a2w.gate_of(a2w.GATES[g], d), (g, d))

    def test_instrument_bytes(self):
        _, info, _, _ = batch_run("org_dangerous")
        b, lab = info["blob"].bytes_()
        self.assertEqual(b[6:10], bytes([0, 0, 1, a2w.ENV_TRI]))
        self.assertEqual(b[lab["org_dangerous_inst_org13"]:][:10],
                         bytes([0, 0xFF, 0, 0, 3, 2, 0x84, 6, 13, 0xFF]))
        self.assertEqual(b[lab["org_dangerous_inst_orgtri"]:][:10],
                         bytes([0, 0xFF, 0, 0, 5, 2, 0x84, 6, a2w.VOL_ENV, 0xFF]))
        _, info, _, _ = batch_run("hps_dangerous")
        b, lab = info["blob"].bytes_()
        self.assertEqual(b[9], a2w.ENV_SAW)
        self.assertEqual(b[lab["hps_dangerous_inst_hps13"]:][:10],
                         bytes([0, 0xFF, 0, 0, 4, 2, 0x84, 4, 13, 0xFF]))

    def test_vs_tsx_model(self):
        """Flat parts exact against the model at the 9/16 cut (pitches on every sounding
        frame - the organ pedal one octave down - levels except the pinned 1-frame-short
        gates); every tail stays below the note level and never rises."""
        for name in S1E_GOLDEN:
            j, info, regs, bpm = batch_run(name)
            c = tsx_model.compare(j, regs, bpm, wzm_ref.TP, S1E_CUT, True,
                                  (0, 0, info["transpose_v3"]))
            self.assertEqual(c["pitch_bad"], 0, name)
            self.assertEqual(c["level_bad"], S1E_SHORT_GATES.get(name, 0), name)
            self.assertEqual(c["tail_bad"], 0, name)
            self.assertTrue(set(c["gate_diffs"]) <= {-1, 0}, (name, c["gate_diffs"]))
            self.assertEqual(c["gate_diffs"].get(-1, 0), S1E_SHORT_GATES.get(name, 0), name)
            if name.endswith("lament"):
                self.assertGreater(c["tail_frames"], 1000, name)   # the tails do sound
        self.assertEqual(batch_run("org_lament")[1]["transpose_v3"], -12)
        self.assertEqual(batch_run("hps_lament")[1]["transpose_v3"], 0)

    def test_gate_frames_all_ratios(self):
        """At 45 / 56 / 62 % every staccato gate of the 96 bpm Lament is within 1 frame of
        the 50 Hz model cut at that ratio (the tape's G key)."""
        for g in (30, 45, 56, 62, 100):
            j, _, regs, bpm = batch_run("hps_lament", gate=g)
            c = tsx_model.compare(j, regs, bpm, wzm_ref.TP, tsx_model.GATE_CUT[g], True)
            self.assertTrue(set(c["gate_diffs"]) <= {-1, 0, 1}, (g, c["gate_diffs"]))
            self.assertEqual(c["tail_bad"], 0, g)

    def test_loudness_flat_parts(self):
        """Tails excluded: legato and staccato per-note means and their ratio within 10 %
        of the model at the same 9/16 cut; legato louder than staccato."""
        for name in S1E_GOLDEN:
            j, info, regs, bpm = batch_run(name)
            c = tsx_model.compare(j, regs, bpm, None, S1E_CUT, True)
            tl, ts = tsx_model.tsx_loudness(j, S1E_CUT)
            self.assertLess(abs(c["leg"] / tl - 1), 0.10, name)
            if ts:
                self.assertLess(abs(c["stac"] / ts - 1), 0.10, name)
                self.assertGreater(c["leg"], c["stac"], name)
                self.assertLess(abs((c["leg"] / c["stac"]) / (tl / ts) - 1), 0.10, name)

    def test_tail_shape(self):
        """A staccato note: full level for the gate, then base - drop, then -1 every
        rel_per frames (organ 13 -> 10 / 6 frames, harpsichord 13 -> 9 / 4 frames); the
        next note cuts it.  A one-shot's last note rings out over the appended rest."""
        for name, top, per in (("org_lament", 10, 6), ("hps_lament", 9, 4)):
            _, info, regs, _ = batch_run(name)
            ev = info["events"][0]
            f0 = 0
            for mid, fr, st, _ in ev:
                if st and fr >= 15:
                    break
                f0 += fr
            g = a2w.gate_of(a2w.GATES[56], fr)
            vols = [r[8] for r in regs[f0:f0 + fr]]
            want = [13] * g + [max(0, top - k // per) for k in range(fr - g)]
            self.assertEqual(vols, want, name)
        # the final rest fits the longest level (100 %: voice C 16 -> 13, 1 step / 9 frames)
        for name, n in (("org_game_over", 1 + 9 * 13), ("hps_game_over", 1 + 9 * 13)):
            _, info, _, _ = batch_run(name)
            full = wzm_ref.play(info["bytes"])
            tot = sum(e[1] for e in info["events"][0])
            self.assertEqual(len(full), tot + n + 1, name)    # + the END frame
            c = [r[10] for r in full[tot:tot + n]]
            self.assertEqual(c[-1], 0, name)
            self.assertEqual(c, sorted(c, reverse=True), name)
            self.assertGreater(c[0], 0, name)
            self.assertEqual(full[tot - 1][10], a2w.VOL_ENV, name)  # the buzzer up to the end

    def test_reverb_levels(self):
        """Key H / --reverb: every level keeps the flat parts (levels exact except the 37
        pinned gates, loudness within 10 % of the model, tails never above the note,
        never rising) and has the documented tail: drop / rel_per per REVERB_LEVELS
        (0 % = cut at the gate).  s1e = the default bytes.  Dry entries are unaffected."""
        tails = {}
        for name in ("org_lament", "hps_lament"):
            base = batch_run(name)[1]["bytes"]
            self.assertEqual(batch_run(name, reverb="s1e")[1]["bytes"], base, name)
            for lv in a2w.REVERB_STEPS:
                j, info, regs, bpm = batch_run(name, reverb=lv)
                c = tsx_model.compare(j, regs, bpm, wzm_ref.TP, S1E_CUT, True,
                                      (0, 0, info["transpose_v3"]))
                self.assertEqual((c["level_bad"], c["tail_bad"], c["pitch_bad"]),
                                 (37, 0, 0), (name, lv))
                tl, ts = tsx_model.tsx_loudness(j, S1E_CUT)
                self.assertLess(abs(c["leg"] / tl - 1), 0.10, (name, lv))
                self.assertLess(abs(c["stac"] / ts - 1), 0.10, (name, lv))
                tails[name, lv] = c["tail_frames"]
                b, lab = info["blob"].bytes_()
                for ins in a2w.instr_map(info["instr"]):
                    o = lab["%s_inst_%s" % (name, ins)]
                    self.assertEqual((b[o + 4], b[o + 7]), a2w.inst_tail(ins, lv), (name, lv))
                # first staccato note of voice A: full for the gate, then the tail
                f0 = 0
                for mid, fr, st, _ in info["events"][0]:
                    if st and fr >= 15:
                        break
                    f0 += fr
                g = a2w.gate_of(a2w.GATES[56], fr)
                drop, rper = a2w.inst_tail("org13" if name[0] == "o" else "hps13", lv)
                want = [13] * g + [max(0, 13 - drop - k // rper) for k in range(fr - g)]
                self.assertEqual([r[8] for r in regs[f0:f0 + fr]], want, (name, lv))
            self.assertEqual(tails[name, 0], 0, name)
            self.assertTrue(0 < tails[name, 50] <= tails[name, 100], name)   # gaps are short: both fill them
        self.assertEqual(a2w.inst_tail("org13", 100), (1, 9))
        self.assertEqual(a2w.inst_tail("orgtri", 0), (16, a2w.CUT))
        self.assertEqual(a2w.inst_tail("hpsaw", 50), (4, 9))
        self.assertEqual(a2w.inst_tail("tsx13", 100), (15, a2w.CUT))      # dry: untouched
        b0 = batch_run("lament_tsx")[1]["bytes"]
        self.assertEqual(batch_run("lament_tsx", reverb=100)[1]["bytes"], b0)
        # 100 %: ~2 s from the note level (1 + 9 x 12 frames), the final rest fits it
        self.assertEqual(1 + 9 * (13 - 1), 109)
        self.assertEqual(a2w.tail_frames("orgtri"), 1 + 9 * (16 - 3))

    def test_gate_100(self):
        """100 %: every staccato note sounds its whole length at full level; the Lament IIb
        then equals the pure-legato Lament II frame for frame (no rests: no tail at all),
        and the release logic still holds (tail_bad 0, levels exact)."""
        j, info, regs, bpm = batch_run("org_lament", gate=100)
        c = tsx_model.compare(j, regs, bpm, wzm_ref.TP, tsx_model.GATE_CUT[100], True,
                              (0, 0, -12))
        self.assertEqual((c["level_bad"], c["tail_bad"], c["tail_frames"]), (0, 0, 0))
        self.assertEqual(set(c["gate_diffs"]), {0})
        _, _, regs2, _ = batch_run("org_lament2")
        self.assertEqual(regs, regs2)
        b, lab = info["blob"].bytes_()
        self.assertEqual(b[lab["org_lament_inst_org13"] + 5:][:2], bytes([1, 8]))

    def test_rest_continues_release(self):
        """v0.3: a rest runs the release on (organ-rev), but stays silent with an
        instant-cut instrument (drop 15 = v0.2)."""
        ev = [[(60, 10, False, False), (None, 20, False, False)]] * 3
        for instr, first in (("organ-rev", 10), ("tsx", 0)):
            b, _ = a2w.build_song("x", ev, instr, False).bytes_()
            regs = wzm_ref.play(b)
            self.assertEqual([r[8] for r in regs[9:12]], [13, first, first], instr)


class EchoExperiment(unittest.TestCase):
    """WZM_ECHO (tape-only): after a note change the voice plays the previous note's
    period at its last level - drop on odd frames (every frame while the dry voice is
    silent), -1 every 9 frames."""

    REST3 = [(None, 60, False, False)]

    def song(self, ev, instr="tsx"):
        b, _ = a2w.build_song("x", [ev, self.REST3, self.REST3], instr, False).bytes_()
        return b

    def test_off_is_identity(self):
        for name in ("org_lament", "hps_dangerous", "lament2_tsx_96"):
            _, info, regs, _ = batch_run(name)
            self.assertEqual(wzm_ref.play(info["bytes"], max_frames=len(regs), echo_drop=0),
                             regs, name)

    def test_alternation_and_decay(self):
        b = self.song([(60, 20, False, False), (64, 20, False, False), (None, 20, False, False)])
        tp = wzm_ref.TP
        regs = wzm_ref.play(b, echo_drop=2)
        a = [(r[0] | r[1] << 8, r[8]) for r in regs]
        self.assertEqual(a[:20], [(tp[48], 13)] * 20)                 # no previous note
        want = []
        lvl, cnt = 11, 9                                              # 13 - 2
        for k in range(20, 60):
            out = lvl
            cnt -= 1
            if cnt == 0:
                cnt, lvl = 9, lvl - 1
            dry = (tp[52], 13) if k < 40 else (tp[52], 0)
            want.append((tp[48], out) if (dry[1] == 0 or k & 1) else dry)
        self.assertEqual(a[20:60], want)
        # the dry note's level: 50 % of its frames -> -3 dB of its power
        dry_frames = sum(1 for k in range(20, 40) if a[k] == (tp[52], 13))
        self.assertEqual(dry_frames, 10)

    def test_same_pitch_no_echo(self):
        b = self.song([(60, 20, False, False), (60, 20, False, False)])
        self.assertEqual(wzm_ref.play(b, echo_drop=2), wzm_ref.play(b))

    def test_levels(self):
        """J key levels: drop 6 / 4 / 2 = -18 / -12 / -6 dB below the old note."""
        b = self.song([(60, 20, False, False), (64, 20, False, False)])
        for drop, start in ((6, 7), (4, 9), (2, 11)):
            regs = wzm_ref.play(b, echo_drop=drop)
            self.assertEqual(regs[21][8], start, drop)


if __name__ == "__main__":
    unittest.main()
