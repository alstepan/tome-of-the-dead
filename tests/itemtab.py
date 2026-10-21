#!/usr/bin/env python3
"""Unit tests for tools/itempack.py (3E-T4, simplified per game.md §8.11 item 2;
3E-T4c retag): the item word table, name refs, the hero-tome marker, the three
stem sets (resident / fx / page), it_stat, the 32-char composed-line rule and
the byte budgets. The per-type ink is not emitted (src/lowram.asm carries it);
the ink test checks items.txt against tools/items_model.py ITEM_INK.

Run:  python3 tests/itemtab.py            (stdlib unittest; no build needed)

The round-trip tests pack src/items.txt into a temporary directory, then parse
the EMITTED items_tab.asm / items_fx_stems.asm / items_ovl_stems.asm / items_ids.inc back into bytes
and decode them with the algorithm the Z80 will use (word lookup through
it_wcx, 0-terminated stems, 3 word ids per name, $FF = hero tome word ->
W_WAR / W_SPELL by hero kind). Expected strings come from items.txt (through
the packer's parser) and from src/strings.txt, never from the emitted bytes.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import itempack as ip  # noqa: E402

SRC = os.path.join(ROOT, "src", "items.txt")
DEFS = os.path.join(ROOT, "src", "item_defs.asm")
STRINGS = os.path.join(ROOT, "src", "strings.txt")
TOOL = os.path.join(ROOT, "tools", "itempack.py")
LOG_MAX = 32
HERO_KINDS = ("warrior", "mage")
HERO_WORD = {"warrior": "WAR", "mage": "SPELL"}   # knight maps to WAR too (tool table)
ROWS = 44
sys.path.insert(0, os.path.join(ROOT, "tools"))
import items_model as M  # noqa: E402  (ITEM_INK: the lowram ink source)


def _num(tok):
    if tok.startswith("$"):
        return int(tok[1:], 16)
    return int(tok, 10)


def parse_asm_sections(path):
    """Emitted .asm -> {label: [bytes]} (DW little-endian, as sjasmplus emits it)."""
    sections = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            code = raw.split(";", 1)[0].rstrip()
            if re.fullmatch(r"\w+:", code):
                cur = code[:-1]
                sections[cur] = []
                continue
            m = re.match(r"^\s+(DB|DW)\s+(.*)$", code)
            if m and cur is not None:
                for tok in m.group(2).split(","):
                    v = _num(tok.strip())
                    if m.group(1) == "DB":
                        sections[cur].append(v & 0xFF)
                    else:
                        sections[cur] += [v & 0xFF, (v >> 8) & 0xFF]
    return sections


def parse_ids(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(\w+)\s+EQU\s+(\d+|\$[0-9A-Fa-f]+)\b", line)
            if m:
                out[m.group(1)] = _num(m.group(2))
    return out


class Decoder:
    """Reads the packed tables the way the Z80 will (item_name, T10)."""

    def __init__(self, tab, ids, fx_tab, ovl):
        self.ids = ids
        self.raw_words = bytes(tab["it_words"])
        self.wcx = [tab["it_wcx"][i] | (tab["it_wcx"][i + 1] << 8)
                    for i in range(0, len(tab["it_wcx"]), 2)]
        self.names = tab["it_name"]
        self.stems = bytes(tab["it_stems"])
        self.fx = bytes(fx_tab["it_fx_stems"])
        st = fx_tab["it_stat"]
        self.stat = [(st[2 * i], st[2 * i + 1]) for i in range(len(st) // 2)]
        self.ovl = bytes(ovl)

    def _skip_word(self, pos):
        while self.raw_words[pos] < 0x80:
            pos += 1
        return pos + 1

    def word(self, wid):
        """Word id (1-based): start at wcx[(k-1)>>3], skip (k-1)&7 words (<= 7 scans)."""
        i = wid - 1
        pos = self.wcx[i >> 3]
        for _ in range(i & 7):
            pos = self._skip_word(pos)
        out = []
        while True:
            b = self.raw_words[pos]
            out.append(b & 0x7F)
            if b & 0x80:
                break
            pos += 1
        return "".join(chr(c) for c in out)

    def name(self, row, hero_kind="warrior"):
        """item_name's word walk: $FF -> W_WAR (Warrior/knight) or W_SPELL (Mage)."""
        out = []
        for w in self.names[3 * row:3 * row + 3]:
            if w == ip.HERO_MARK:
                wid = self.ids["W_" + HERO_WORD[hero_kind]]
            elif w:
                wid = w
            else:
                continue
            out.append(self.word(wid))
        return " ".join(out)

    @staticmethod
    def zstr(blob, off):
        end = blob.index(0, off)
        return blob[off:end].decode("ascii")


class ItemTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="itemtab_")
        cls.syms = ip.parse_defs(DEFS)
        cls.strings = ip.parse_strings(STRINGS)
        cls.items = ip.parse_items(SRC, cls.syms)
        cls.budgets, cls.errors, cls.model = ip.run(SRC, DEFS, STRINGS, cls.tmp)
        assert cls.errors == [], cls.errors
        cls.tab = parse_asm_sections(os.path.join(cls.tmp, "items_tab.asm"))
        cls.fx_tab = parse_asm_sections(os.path.join(cls.tmp, "items_fx_stems.asm"))
        cls.ovl_tab = parse_asm_sections(os.path.join(cls.tmp, "items_ovl_stems.asm"))
        cls.ids = parse_ids(os.path.join(cls.tmp, "items_ids.inc"))
        cls.dec = Decoder(cls.tab, cls.ids, cls.fx_tab, cls.ovl_tab["it_ovl_stems"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------------
    def _res(self, name):
        return self.dec.zstr(self.dec.stems, self.ids["S3_" + name.upper()])

    def _fx(self, name):
        return self.dec.zstr(self.dec.fx, self.ids["S_FX_" + name.upper()])

    def _ovl(self, name):
        return self.dec.zstr(self.dec.ovl, self.ids["S3O_" + name.upper()])

    def _expect(self, tid, kind):
        """Display name from items.txt for a hero kind (the marker -> WAR / SPELL)."""
        row = self.items.rows[tid]
        if row.name is None:
            return ""
        return row.name.replace(ip.HERO_TOKEN, HERO_WORD[kind])

    def _bag_types(self):
        return [t for t in sorted(self.items.rows) if self.model.klass.get(t)]

    # -- word table ---------------------------------------------------------------
    def test_word_table_round_trip(self):
        self.assertEqual(len(self.model.words), ip.WORD_COUNT_SPEC)
        for k, w in enumerate(self.model.words, 1):
            self.assertEqual(self.dec.word(k), w, f"word id {k}")

    def test_words_are_short_and_upper(self):
        for w in self.model.words:
            self.assertRegex(w, r"^[A-Z]{1,8}$", w)

    def test_word_bytes_top_bit_terminator(self):
        self.assertEqual(self.budgets["words"], 229)
        self.assertEqual(sum(1 for b in self.tab["it_words"] if b & 0x80), ip.WORD_COUNT_SPEC)

    def test_retired_words_absent(self):
        # §8.11 item 2: no appearance words, no BUC prefixes, no 'OF', no 'UNKNOWN'
        retired = {"BLESSED", "CURSED", "OF", "UNKNOWN", "RUBY", "AZURE", "EMERALD", "AMBER",
                   "VIOLET", "MILKY", "ZORAK", "VELMIS", "OSTRUN", "KAPPU", "MIRADEL", "THUNE",
                   "YOLQ", "ABRAXA"}
        self.assertEqual(retired & set(self.model.words), set())

    def test_wcx_is_every_eighth_word(self):
        self.assertEqual(len(self.dec.wcx), 6)
        starts = []
        pos = 0
        for w in self.model.words:
            starts.append(pos)
            pos += len(w)
        self.assertEqual(self.dec.wcx, [starts[i] for i in range(0, ip.WORD_COUNT_SPEC, 8)])

    # -- names and the hero-tome marker -------------------------------------------
    def test_every_type_name_round_trip_both_hero_kinds(self):
        for kind in HERO_KINDS:
            for tid in range(ROWS):
                self.assertEqual(self.dec.name(tid, kind), self._expect(tid, kind),
                                 f"type {self.items.rows[tid].sym} kind {kind}")

    def test_book_row_is_one_marker_row(self):
        self.assertEqual(self.items.rows[self.syms["IT_BOOK"]].name, "<HERO> TOME")
        ids = self.dec.names[3 * self.syms["IT_BOOK"]:3 * self.syms["IT_BOOK"] + 3]
        self.assertEqual(ids, [ip.HERO_MARK, self.ids["W_TOME"], 0])

    def test_book_name_by_hero_kind(self):
        t = self.syms["IT_BOOK"]
        self.assertEqual(self.dec.name(t, "warrior"), "WAR TOME")
        self.assertEqual(self.dec.name(t, "mage"), "SPELL TOME")

    def test_hero_words_present(self):
        self.assertEqual(self.dec.word(self.ids["W_WAR"]), "WAR")
        self.assertEqual(self.dec.word(self.ids["W_SPELL"]), "SPELL")

    def test_no_marker_outside_the_book(self):
        for tid in range(ROWS):
            if tid == self.syms["IT_BOOK"]:
                continue
            self.assertNotIn(ip.HERO_MARK, self.dec.names[3 * tid:3 * tid + 3], tid)

    def test_fixed_potion_and_scroll_names(self):
        # §8.11 item 2: type-first, 2 words, always known
        expect = {"IT_P_HEAL": "HEAL POTION", "IT_P_MANA": "MANA POTION", "IT_P_CURE": "CURE POTION",
                  "IT_S_TELEPORT": "TELEPORT SCROLL", "IT_S_FEAR": "FEAR SCROLL",
                  "IT_S_SLEEP": "SLEEP SCROLL", "IT_S_ENCHANT": "ENCHANT SCROLL"}
        for sym, name in expect.items():
            self.assertEqual(self.dec.name(self.syms[sym]), name, sym)

    def test_no_duplicate_display_names(self):
        names = []
        for t in self.items.rows:
            names += self.model.known_names(t)
        names = [n for n in names if n]
        self.assertEqual(len(names), len(set(names)))

    def test_name_length_caps(self):
        for t in self.items.rows:
            cap = ip.NAME_CAP
            for kind in HERO_KINDS:
                name = self._expect(t, kind)
                if name:
                    self.assertLessEqual(len(name.split()), 3)
                    self.assertLessEqual(len(name), cap, name)

    def test_longest_name_per_rule(self):
        self.assertEqual(self.items.rows[self.syms["IT_W_SHORT"]].name, "SHORT SWORD")
        self.assertEqual(len(self.items.rows[self.syms["IT_C_MANA"]].name), 11)

    # -- composed lines (the 32-char rule) ------------------------------------------
    def test_pickup_lines_round_trip_and_fit(self):
        stem = self.strings["cmb_pick"]
        self.assertEqual(stem, "YOU PICK UP ")
        for kind in HERO_KINDS:
            for t in self._bag_types():
                name = self._expect(t, kind)
                line = stem + name
                self.assertEqual(line, "YOU PICK UP " + name)
                self.assertLessEqual(len(line), LOG_MAX, line)

    def test_verb_lines_round_trip(self):
        for kind in HERO_KINDS:
            for t in self._bag_types():
                cls = self.model.klass[t]
                name = self._expect(t, kind)
                if cls == "food":
                    self.assertEqual(self._fx("eat") + name, "YOU EAT THE " + name)
                if cls == "pot":
                    self.assertEqual(self._fx("drink") + name, "YOU DRINK THE " + name)
                if cls == "scr":
                    self.assertEqual(self._fx("read") + name, "YOU READ THE " + name)
                if cls == "book":
                    self.assertEqual(self._fx("read") + name, "YOU READ THE " + name)
                if cls == "gear":
                    for verb, expect in (("equip", "YOU EQUIP "), ("remove", "YOU REMOVE ")):
                        line = self._fx(verb) + name
                        self.assertEqual(line, expect + name)
                        self.assertLessEqual(len(line), LOG_MAX, line)
                if name:
                    line = self._fx("discard") + name
                    self.assertEqual(line, "YOU DISCARD " + name)
                    self.assertLessEqual(len(line), LOG_MAX, line)

    def test_trap_lines_round_trip(self):
        for frag, expect in (("tf_dart", "DART"), ("tf_gas", "GAS"), ("tf_alarm", "ALARM")):
            self.assertEqual(self._res("trap_found") + self._res(frag), "TRAP FOUND: " + expect)
        self.assertEqual(self._res("trap_found") + "TELEPORT", "TRAP FOUND: TELEPORT")

    def test_longest_composed_line_is_28(self):
        longest, _, errs = ip.check_composed(self.model)
        self.assertEqual(errs, [])
        self.assertEqual(longest, 28)

    def test_known_example_lines(self):
        t_teleport = self.syms["IT_S_TELEPORT"]
        self.assertEqual(self._fx("read") + self._expect(t_teleport, "warrior"),
                         "YOU READ THE TELEPORT SCROLL")
        self.assertEqual(self._fx("drink") + self._expect(self.syms["IT_P_HEAL"], "mage"),
                         "YOU DRINK THE HEAL POTION")
        self.assertEqual(self._fx("read") + self._expect(self.syms["IT_BOOK"], "mage"),
                         "YOU READ THE SPELL TOME")

    # -- stat / attr ------------------------------------------------------------------
    def test_stat_round_trip(self):
        for t in range(ROWS):
            row = self.items.rows[t]
            b0, b1 = self.dec.stat[t]
            die = b0 & 0x0F
            atk = (b0 >> 4) - 16 if (b0 >> 4) >= 8 else (b0 >> 4)
            if self.model.klass.get(t) in ("food", "pot"):
                self.assertEqual(b1, row.amt, row.sym)
            else:
                self.assertEqual(b1 & 0x0F, row.dfn, row.sym)
                self.assertEqual(b1 >> 4, row.mp, row.sym)
            self.assertEqual(die, row.die, row.sym)
            self.assertEqual(atk, row.atk, row.sym)

    def test_ink_column_matches_lowram_source(self):
        # No it_attr any more: the floor ink lives in src/lowram.asm it_tab, built from
        # tools/items_model.py ITEM_INK. items.txt's INK column must agree with it.
        for t in range(ROWS):
            row = self.items.rows[t]
            if row.ink:
                self.assertEqual(M.ITEM_INK.get(M.T[row.sym]), row.ink, row.sym)

    def test_fixed_floor_inks(self):
        # §8.11 item 2: floor / inventory ink per type (potions and scrolls)
        expect = {"IT_P_HEAL": 0x42, "IT_P_MANA": 0x45, "IT_P_CURE": 0x44,
                  "IT_S_TELEPORT": 0x45, "IT_S_FEAR": 0x46, "IT_S_SLEEP": 0x44,
                  "IT_S_ENCHANT": 0x47, "IT_BOOK": 0x43}
        for sym, ink in expect.items():
            self.assertEqual(self.items.rows[self.syms[sym]].ink, ink, sym)

    def test_no_it_attr_emitted(self):
        self.assertNotIn("it_attr", self.tab)

    def test_food_amounts(self):
        amounts = [self.items.rows[self.syms[s]].amt for s in
                   ("IT_F_CARROT", "IT_F_APPLE", "IT_F_PEAR", "IT_F_CHEESE", "IT_F_MEAT")]
        self.assertEqual(amounts, [10, 15, 20, 30, 40])

    # -- budgets ----------------------------------------------------------------------
    def test_budgets(self):
        b = self.budgets
        self.assertEqual(b["words"], 229)
        self.assertEqual(b["names"], ROWS * 3)
        self.assertEqual(b["refs"], 361)
        self.assertLessEqual(b["refs"], 460)
        # resident: turn-path stems only (3E-T4c retag; ~80 B target, 89 B as built;
        # 3E-T11: + "BOSS DROPS " 11 + its terminator = 101; review: + "NO NEED" moved
        # from the fx set, 7 + 1 = 109)
        self.assertEqual(b["res_stems"], 109)
        self.assertLessEqual(b["res_stems"], 480)
        self.assertEqual(b["resident"], 482)          # 3E-T11: + BOSS DROPS (12) + NO NEED (8)
        self.assertLessEqual(b["resident"], 700)
        self.assertLessEqual(b["resident"] - b["wcx"], 700)
        # fx overlay: effect / quick-use stems + it_stat (raw)
        self.assertEqual(b["fx_stems"], 307)        # T11 review: NO NEED (8) moved to resident
        self.assertEqual(b["stat"], ROWS * 2)
        self.assertEqual(b["fx"], b["fx_stems"] + b["stat"])
        self.assertLessEqual(b["fx"], 700)
        # page overlay: empty after the retag (all page verbs / effects are fx)
        self.assertEqual(b["page_stems"], 0)
        self.assertLessEqual(b["page_stems"], 310)
        self.assertEqual(len(self.tab["it_stems"]), b["res_stems"])
        self.assertEqual(len(self.fx_tab["it_fx_stems"]), b["fx_stems"])
        self.assertEqual(len(self.fx_tab["it_stat"]), b["stat"])
        self.assertEqual(len(self.ovl_tab["it_ovl_stems"]), b["page_stems"])

    def test_every_resident_and_fx_stem_round_trip(self):
        for st in self.model.res_stems():
            self.assertEqual(self._res(st.name), st.text, st.name)
        for st in self.model.fx_stems():
            self.assertEqual(self._fx(st.name), st.text, st.name)
        # bank-0 (E:) stems are not emitted: their text must equal src/strings.txt
        for st in self.items.stems:
            if st.ref is not None:
                self.assertEqual(self.strings[st.ref], st.text, st.name)

    def test_stems_sit_in_their_section(self):
        groups = {st.name: st.group for st in self.items.stems}
        self.assertEqual(groups["pick"], "res")
        self.assertEqual(groups["trap_found"], "res")
        self.assertEqual(groups["bag_full"], "res")
        self.assertEqual(groups["drink"], "fx")
        self.assertEqual(groups["hg_hungry"], "fx")
        self.assertEqual(groups["bk_read"], "fx")
        self.assertEqual(self.model.page_stems(), [])

    def test_verb_stem_name_combos_fit_32(self):
        # every verb stem x every display name it can take, decoded from the tables
        longest = 0
        for kind in HERO_KINDS:
            for t in self._bag_types():
                cls = self.model.klass[t]
                name = self.dec.name(t, kind)
                lines = []
                if cls == "gear":
                    lines += [self._fx("equip") + name, self._fx("remove") + name]
                if cls == "food":
                    lines += [self._fx("eat") + name]
                if cls == "pot":
                    lines += [self._fx("drink") + name]
                if cls in ("scr", "book"):
                    lines += [self._fx("read") + name]
                if name:
                    # pick is a bank-0 E: stem (not emitted): its value from src/strings.txt
                    lines += [self.strings["cmb_pick"] + name, self._fx("discard") + name]
                for line in lines:
                    longest = max(longest, len(line))
                    self.assertLessEqual(len(line), LOG_MAX, line)
        self.assertEqual(longest, 28)
        for frag in ("tf_dart", "tf_gas", "tf_alarm"):
            self.assertLessEqual(len(self._res("trap_found") + self._res(frag)), LOG_MAX)

    def test_deterministic_output(self):
        tmp2 = tempfile.mkdtemp(prefix="itemtab2_")
        try:
            ip.run(SRC, DEFS, STRINGS, tmp2)
            for name in ("items_tab.asm", "items_fx_stems.asm", "items_ovl_stems.asm", "items_ids.inc"):
                with open(os.path.join(self.tmp, name), "rb") as a, open(os.path.join(tmp2, name), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_sjasmplus_assembles_the_output(self):
        if shutil.which("sjasmplus") is None:
            self.skipTest("sjasmplus not on PATH")
        wrap = os.path.join(self.tmp, "wrap.asm")
        with open(wrap, "w", encoding="utf-8") as f:
            f.write('    ORG $6000\n    INCLUDE "items_tab.asm"\n    INCLUDE "items_fx_stems.asm"\n'
                    '    INCLUDE "items_ovl_stems.asm"\n')
        r = subprocess.run(["sjasmplus", "--nologo", "--raw=" + os.path.join(self.tmp, "o.bin"),
                            "-i", self.tmp, wrap], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Errors: 0, warnings: 0", r.stdout + r.stderr)


class ItemPackCliTests(unittest.TestCase):
    """The packer must refuse bad data (exit 1, nothing written)."""

    def _run_with(self, edit):
        tmp = tempfile.mkdtemp(prefix="itemtab_bad_")
        try:
            with open(SRC, encoding="utf-8") as f:
                text = f.read()
            bad = edit(text)
            src = os.path.join(tmp, "items.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(bad)
            out = os.path.join(tmp, "out")
            r = subprocess.run([sys.executable, TOOL, "--src", src, "--out", out],
                               capture_output=True, text=True)
            return r, os.path.exists(os.path.join(out, "items_tab.asm"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ok_input_exits_zero(self):
        tmp = tempfile.mkdtemp(prefix="itemtab_ok_")
        try:
            r = subprocess.run([sys.executable, TOOL, "--out", tmp], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_word_longer_than_8_fails(self):
        r, wrote = self._run_with(lambda t: t.replace("| FEAR SCROLL", "| FEARXYZWQ SCROLL", 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is 9 chars (max 8)", r.stderr)
        self.assertFalse(wrote)

    def test_four_word_name_fails(self):
        r, wrote = self._run_with(lambda t: t.replace("FEAR SCROLL ", "FEAR SCROLL HARD NOW ", 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("words", r.stderr)
        self.assertFalse(wrote)

    def test_composed_line_over_32_fails(self):
        r, wrote = self._run_with(lambda t: t.replace('"YOU DISCARD "', '"YOU DISCARD THE ITEM NOW "', 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("composed line", r.stderr)
        self.assertFalse(wrote)

    def test_bank0_mismatch_fails(self):
        r, wrote = self._run_with(lambda t: t.replace('"YOU PICK UP "', '"YOU PICK UP  "', 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("E:cmb_pick", r.stderr)
        self.assertFalse(wrote)

    def test_wrong_word_count_fails(self):
        r, wrote = self._run_with(lambda t: t.replace("[book]\nWAR\nSPELL", "[book]\nWAR\nSPELL\nNEWWORD", 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("word count", r.stderr)
        self.assertFalse(wrote)

    def test_marker_on_non_book_fails(self):
        r, wrote = self._run_with(lambda t: t.replace("| CARROT            |", "| <HERO> CARROT     |", 1))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only on IT_BOOK", r.stderr)
        self.assertFalse(wrote)


if __name__ == "__main__":
    unittest.main(verbosity=2)
