#!/usr/bin/env python3
"""Pack the 3E item names, appearance words, per-type numbers and message stems (3E-T4).

Input : src/items.txt (format documented in that file's header) and the
        constants of src/item_defs.asm (IT_* type ids, IT_COUNT) and the
        bank-0 strings of src/strings.txt (E: references).
Output (default build/text/, overridable with --out DIR; stdout = budgets):
  items_tab.asm       bank-1 resident block: it_words, it_wcx, it_name,
                      it_stems(_end), it_attr, app_attr, it_stat (+ ASSERTs)
  items_ovl_stems.asm overlay-only stems (it_ovl_stems, ASSERT <= 310 B)
  items_ids.inc       W_* word ids, W_APP_POT / W_APP_SCR bases, S3_* / S3O_*
                      stem offsets, ITW_* / ITN_* / ITS_* / ITO_* sizes

Word table: raw ASCII, the last char with bit 7 set, no terminator. Word id
is 1-based (0 = none in a name ref), id k = index k-1 in the table. it_wcx
holds one DW (offset from it_words) per 8 words: a lookup starts at
it_wcx[(k-1) >> 3] and skips (k-1) & 7 words (<= 7 scans).

Type rows: it_name = 3 word ids per row (0-padded, no terminator when full),
44 rows, one per type id. IT_BOOK's first word is HERO_MARK ($FF): item_name
substitutes W_WAR (Warrior/knight) or W_SPELL (Mage); the TOME word is shared.
it_stat = 2 B per row: byte0 = DIE | (ATK & $0F) << 4; byte1 = AMT (food,
potions) or (DEF & $0F) | (MP << 4) (gear).

Stems: 0-terminated ASCII, offset = S3_<NAME> / S3O_<NAME>.

CHECKS (any failure = message on stderr and exit 1; nothing is written):
  - every word A-Z and <= 8 chars; 65 distinct words (game.md §8.11 (1));
    appearance runs contiguous (6 colours, 8 labels);
  - every name 1..3 words; BUC-able gear names <= 12 chars, others <= 18;
    no duplicate display name; unique gear never gets a BUC prefix;
  - every composed line <= 32 chars (LOG_MAX): pick / equip / remove /
    discard with the BUC prefixes BLESSED / CURSED on BUC-able gear (the
    BUC prefix only exists on gear, §8.11 (1): checking it on potions would
    test lines the Z80 never composes), eat / drink / read / it_was_a /
    trap_found and the bank-0 'YOU READ THE BOOK';
  - E: stems equal their src/strings.txt value; stem texts printable,
    upper case, no '"' and no byte 0;
  - byte budgets: words+refs <= 460, resident stems <= 480, resident total
    (words + wcx + names + stems) <= 700, overlay stems <= 310.

Usage:  python3 tools/itempack.py [--src FILE] [--out DIR]
        tools/build.sh --items      (stand-alone target; not part of the build)
"""
import argparse
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DEFAULT = os.path.join(ROOT, "src", "items.txt")
DEFS_DEFAULT = os.path.join(ROOT, "src", "item_defs.asm")
STRINGS_DEFAULT = os.path.join(ROOT, "src", "strings.txt")
OUT_DEFAULT = os.path.join(ROOT, "build", "text")

LOG_MAX = 32
WORD_MAX = 8
NAME_MAX_WORDS = 3
NAME_CAP_BUC_GEAR = 12
NAME_CAP_OTHER = 18
WORD_COUNT_SPEC = 65
COLOUR_COUNT = 6
LABEL_COUNT = 8
WCX_STEP = 8
ROWS = 44                 # one row per type id 0..43 (IT_COUNT)
HERO_TOKEN = "<HERO>"     # [types] name token: the class book's first word
HERO_MARK = 0xFF          # it_name id; item_name substitutes W_WAR / W_SPELL
HERO_WORD = {"warrior": "WAR", "knight": "WAR", "mage": "SPELL"}
BUDGET_REFS = 460         # words + name refs
BUDGET_STEMS = 480        # resident stems
BUDGET_RESIDENT = 700     # words + wcx + names + resident stems
BUDGET_OVL = 310          # overlay stems
BUC_PREFIX = {"": "", "BLESSED": "BLESSED ", "CURSED": "CURSED "}


class ItemsError(Exception):
    """Parse-time failure (malformed input). Check failures are collected instead."""


# ----------------------------------------------------------------------------
# input parsing
# ----------------------------------------------------------------------------

def parse_defs(path):
    """IT_* EQUs of item_defs.asm -> {name: int} (numeric EQUs only)."""
    syms = {}
    pat = re.compile(r"^(IT_\w+)\s+EQU\s+(\d+)\b")
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = pat.match(line)
            if m:
                syms[m.group(1)] = int(m.group(2))
    for need in ("IT_COUNT", "IT_F_CARROT", "IT_F_MEAT", "IT_P_HEAL", "IT_P_CURE",
                 "IT_S_TELEPORT", "IT_S_ENCHANT", "IT_BOOK", "IT_BOW",
                 "IT_W_SHORT", "IT_C_GRAVE", "IT_DAGGER", "IT_ARROW", "IT_KEY"):
        if need not in syms:
            raise ItemsError(f"{path}: {need} not found")
    if syms["IT_COUNT"] != 44:
        raise ItemsError(f"{path}: IT_COUNT is {syms['IT_COUNT']}, the packer expects 44")
    return syms


def parse_strings(path):
    """src/strings.txt -> {name: text} (the 'name "TEXT"' lines)."""
    out = {}
    pat = re.compile(r'^(\w+)\s+"(.*)"\s*$')
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = pat.match(line.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    return out


class Row:
    def __init__(self, sym, tid, name, ink, stat, unique, line_no):
        self.sym = sym
        self.tid = tid
        self.name = name          # str (words joined by spaces) or None
        self.ink = ink           # int, or the string "APP"
        self.die, self.atk, self.dfn, self.mp, self.amt = stat
        self.unique = unique
        self.line_no = line_no


class Stem:
    def __init__(self, name, group, ref, text, line_no):
        self.name = name
        self.group = group        # "res" | "ovl"
        self.ref = ref            # None for N, else the strings.txt name
        self.text = text
        self.line_no = line_no


class Items:
    def __init__(self):
        self.buc = []             # [words]
        self.book = []            # [words]: W_WAR / W_SPELL seeds
        self.colours = []         # [(word, ink int)]
        self.labels = []          # [word]
        self.rows = {}            # tid -> Row
        self.stems = []           # [Stem]


def _ink(tok, where):
    if tok == "-":
        return 0
    if tok == "APP":
        return "APP"
    if re.fullmatch(r"\$[0-9A-Fa-f]{2}", tok):
        return int(tok[1:], 16)
    raise ItemsError(f"{where}: bad INK '{tok}'")


def parse_items(path, syms):
    items = Items()
    section = None
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        where = f"{os.path.basename(path)}:{no}"
        m = re.fullmatch(r"\[(\w+)\]", line)
        if m:
            section = m.group(1)
            if section not in ("buc", "book", "appear", "types", "stems"):
                raise ItemsError(f"{where}: unknown section [{section}]")
            continue
        if section == "buc":
            items.buc.append(line)
        elif section == "appear":
            head, _, rest = line.partition(" ")
            if head == "potion":
                for tok in rest.split():
                    mm = re.fullmatch(r"([A-Z]+)=(\$[0-9A-Fa-f]{2})", tok)
                    if not mm:
                        raise ItemsError(f"{where}: potion token '{tok}' is not WORD=$xx")
                    items.colours.append((mm.group(1), int(mm.group(2)[1:], 16)))
            elif head == "scroll":
                items.labels.extend(rest.split())
            else:
                raise ItemsError(f"{where}: [appear] line must start potion/scroll")
        elif section == "book":
            items.book.append(line)
        elif section == "types":
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 6:
                raise ItemsError(f"{where}: [types] row needs 6 '|' fields, got {len(parts)}")
            sym, name, ink_t, nums, flag, _note = parts
            if sym in syms and syms[sym] < syms["IT_COUNT"]:
                tid = syms[sym]
            else:
                raise ItemsError(f"{where}: unknown type symbol '{sym}'")
            if tid in items.rows:
                raise ItemsError(f"{where}: type {sym} ({tid}) listed twice")
            nm = None if name == "-" else name
            if nm is not None and any(t != HERO_TOKEN and re.fullmatch(r"[A-Z]+", t) is None
                                      for t in nm.split()):
                raise ItemsError(f"{where}: NAME '{nm}' must be UPPER words separated by single spaces")
            vals = nums.split()
            if len(vals) != 5:
                raise ItemsError(f"{where}: DIE ATK DEF MP AMT needs 5 numbers")
            die, atk, dfn, mp, amt = (int(v) for v in vals)
            if not (0 <= die <= 15 and -8 <= atk <= 7 and 0 <= dfn <= 15 and 0 <= mp <= 15 and 0 <= amt <= 255):
                raise ItemsError(f"{where}: number out of packed range")
            if flag not in ("U", "-"):
                raise ItemsError(f"{where}: FLAG must be U or -")
            items.rows[tid] = Row(sym, tid, nm, _ink(ink_t, where), (die, atk, dfn, mp, amt),
                                  flag == "U", no)
        elif section == "stems":
            parts = [p.strip() for p in line.split("|", 3)]
            if len(parts) != 4:
                raise ItemsError(f"{where}: stem row needs NAME | GROUP | SRC | \"TEXT\"")
            name, group, src, text_q = parts
            if re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
                raise ItemsError(f"{where}: stem NAME must be lower_case")
            if group not in ("res", "ovl"):
                raise ItemsError(f"{where}: GROUP must be res or ovl")
            mq = re.fullmatch(r'"([^"]*)"', text_q)
            if not mq:
                raise ItemsError(f"{where}: TEXT must be double-quoted")
            ref = None
            if src.startswith("E:"):
                ref = src[2:]
            elif src != "N":
                raise ItemsError(f"{where}: SRC must be N or E:<strings name>")
            items.stems.append(Stem(name, group, ref, mq.group(1), no))
        else:
            raise ItemsError(f"{where}: text outside any section")
    return items


# ----------------------------------------------------------------------------
# model
# ----------------------------------------------------------------------------

class Model:
    """Word table, name refs and derived names. Built once; all checks run here."""

    def __init__(self, items, syms, strings):
        self.items = items
        self.syms = syms
        self.errors = []
        self.words = []           # index k-1 -> word (id k)
        self.wid = {}             # word -> id (1-based)
        self._build_words()
        self._check_appearance()
        self.name_ids = {}        # tid -> (id, id, id)
        self._build_names()
        self._check_stems(strings)
        self.klass = self._classes()

    # -- words ---------------------------------------------------------------
    def _add(self, w, where):
        if re.fullmatch(r"[A-Z]+", w) is None:
            self.errors.append(f"{where}: word '{w}' must be A-Z only")
            return
        if len(w) > WORD_MAX:
            self.errors.append(f"{where}: word '{w}' is {len(w)} chars (max {WORD_MAX})")
        if w not in self.wid:
            self.words.append(w)
            self.wid[w] = len(self.words)

    def _build_words(self):
        it = self.items
        for w in it.book:
            self._add(w, "[book]")
        for w in it.buc:
            self._add(w, "[buc]")
        for w, _ in it.colours:
            self._add(w, "[appear]")
        for w in it.labels:
            self._add(w, "[appear]")
        for tid in sorted(it.rows):
            row = it.rows[tid]
            if row.name:
                for w in row.name.split():
                    if w != HERO_TOKEN:
                        self._add(w, f"[types] {row.sym}")
        if len(self.words) != WORD_COUNT_SPEC:
            self.errors.append(f"word count {len(self.words)} != {WORD_COUNT_SPEC} (game.md §8.11 (1))")

    def _check_appearance(self):
        it = self.items
        if len(it.colours) != COLOUR_COUNT or len(it.labels) != LABEL_COUNT:
            self.errors.append(f"[appear] needs {COLOUR_COUNT} potion colours and {LABEL_COUNT} scroll labels")
            self.app_pot = self.app_scr = 1
            return
        ids = [self.wid[w] for w, _ in it.colours]
        if ids != list(range(ids[0], ids[0] + COLOUR_COUNT)):
            self.errors.append("potion colour words are not contiguous in the word table")
        ids = [self.wid[w] for w in it.labels]
        if ids != list(range(ids[0], ids[0] + LABEL_COUNT)):
            self.errors.append("scroll label words are not contiguous in the word table")
        self.app_pot = self.wid[it.colours[0][0]]
        self.app_scr = self.wid[it.labels[0]]
        self.app_ink = [ink for _, ink in it.colours]

    # -- names ----------------------------------------------------------------
    def _build_names(self):
        it = self.items
        for tid in range(ROWS):
            if tid not in it.rows:
                self.errors.append(f"type id {tid} has no [types] row")
        for tid in sorted(it.rows):
            row = it.rows[tid]
            if row.name is None:
                self.name_ids[tid] = (0, 0, 0)
                continue
            toks = row.name.split()
            if not (1 <= len(toks) <= NAME_MAX_WORDS):
                self.errors.append(f"[types] {row.sym}: name '{row.name}' has {len(toks)} words (max 3)")
                toks = toks[:NAME_MAX_WORDS]
            ids = [HERO_MARK if w == HERO_TOKEN else self.wid.get(w, 0) for w in toks]
            ids += [0] * (NAME_MAX_WORDS - len(toks))
            self.name_ids[tid] = tuple(ids)

    def _classes(self):
        s = self.syms
        def rng(lo, hi):
            return set(range(s[lo], s[hi] + 1))
        k = {}
        for t in rng("IT_F_CARROT", "IT_F_MEAT"):
            k[t] = "food"
        for t in rng("IT_P_HEAL", "IT_P_CURE"):
            k[t] = "pot"
        for t in rng("IT_S_TELEPORT", "IT_S_ENCHANT"):
            k[t] = "scr"
        k[s["IT_BOOK"]] = "book"
        k[s["IT_BOW"]] = "bow"
        for t in rng("IT_W_SHORT", "IT_C_GRAVE"):
            k[t] = "gear"
        return k

    def buc_able(self, tid):
        return self.klass.get(tid) == "gear" and not self.items.rows[tid].unique

    def known_names(self, tid):
        """Known display names: two for the class book (one per hero kind), else <= 1."""
        row = self.items.rows[tid]
        if row.name is None:
            return []
        if HERO_TOKEN not in row.name:
            return [row.name]
        return [row.name.replace(HERO_TOKEN, w) for w in ("WAR", "SPELL")]

    def known_name(self, tid):
        """The single known name (not for the class book: use known_names)."""
        names = self.known_names(tid)
        return names[0] if names else None

    def unknown_names(self, tid):
        """Appearance names of an unknown potion / scroll (§8.8)."""
        if self.klass.get(tid) == "pot":
            return [f"{w} POTION" for w, _ in self.items.colours]
        if self.klass.get(tid) == "scr":
            return [f"SCROLL {w}" for w in self.items.labels]
        return []

    def display_forms(self, tid):
        """Every name text the game may show for a bag type (known first)."""
        out = []
        return self.known_names(tid) + self.unknown_names(tid)

    # -- stems ----------------------------------------------------------------
    def _check_stems(self, strings):
        seen = set()
        for st in self.items.stems:
            if st.name in seen:
                self.errors.append(f"[stems] duplicate name {st.name}")
            seen.add(st.name)
            t = st.text
            if any(not (32 <= ord(c) <= 126) or c == '"' for c in t):
                self.errors.append(f"[stems] {st.name}: non-printable or '\"' in text")
            if t.upper() != t:
                self.errors.append(f"[stems] {st.name}: text must be UPPER CASE")
            if st.ref is not None:
                if st.ref not in strings:
                    self.errors.append(f"[stems] {st.name}: E:{st.ref} not in src/strings.txt")
                elif strings[st.ref] != t:
                    self.errors.append(f"[stems] {st.name}: E:{st.ref} is '{strings[st.ref]}', "
                                       f"items.txt says '{t}'")
        self.stem = {st.name: st for st in self.items.stems}
        for need in ("pick", "bk_read", "trap_found", "tf_dart", "tf_gas", "tf_alarm",
                     "drink", "read", "eat", "it_was_a", "equip", "remove", "discard"):
            if need not in self.stem:
                self.errors.append(f"[stems] missing '{need}'")

    def stem_text(self, name):
        return self.stem[name].text

    def res_stems(self):
        return [st for st in self.items.stems if st.group == "res" and st.ref is None]

    def ovl_stems(self):
        return [st for st in self.items.stems if st.group == "ovl" and st.ref is None]


# ----------------------------------------------------------------------------
# packing
# ----------------------------------------------------------------------------

def pack_words(words):
    out = bytearray()
    for w in words:
        out += bytes(ord(c) for c in w[:-1])
        out.append(ord(w[-1]) | 0x80)
    return bytes(out)


def pack_wcx(words):
    """DW offsets (from it_words) of word index 0, 8, 16, ...; one per 8 words."""
    offs = []
    pos = 0
    starts = []
    for w in words:
        starts.append(pos)
        pos += len(w)
    for i in range(0, len(words), WCX_STEP):
        offs.append(starts[i])
    # the lookup for the last word index needs (last >> 3) entries too
    need = (len(words) - 1) // WCX_STEP + 1
    assert len(offs) == need
    return offs


def pack_stat(model, tid):
    row = model.items.rows[tid]
    food_or_pot = model.klass.get(tid) in ("food", "pot")
    if food_or_pot:
        b1 = row.amt
    else:
        b1 = (row.dfn & 0x0F) | ((row.mp & 0x0F) << 4)
    b0 = (row.die & 0x0F) | ((row.atk & 0x0F) << 4)
    return b0, b1


def stem_blob(stems):
    """-> (bytes, {NAME: offset}) with each text 0-terminated."""
    blob = bytearray()
    offs = {}
    for st in stems:
        offs[st.name] = len(blob)
        blob += bytes(ord(c) for c in st.text) + b"\x00"
    return bytes(blob), offs


# ----------------------------------------------------------------------------
# composed-line checks (the Z80 composer's grammar; see module docstring)
# ----------------------------------------------------------------------------

def check_composed(model):
    """-> (max length, worst line, [errors]); every line is checked to <= LOG_MAX."""
    errs = []
    worst = ("", 0)

    def line(label, text):
        nonlocal worst
        if len(text) > worst[1]:
            worst = (f"{label}: {text}", len(text))
        if len(text) > LOG_MAX:
            errs.append(f"composed line {len(text)} > {LOG_MAX}: '{text}' ({label})")

    s = model.stem_text
    for tid in sorted(model.items.rows):
        cls = model.klass.get(tid)
        if cls is None:
            continue
        names = model.display_forms(tid)
        prefixes = list(BUC_PREFIX) if model.buc_able(tid) else [""]
        for pre in prefixes:
            pfx = BUC_PREFIX[pre]
            for n in names:
                line(f"pick t{tid}", s("pick") + pfx + n)
                line(f"discard t{tid}", s("discard") + pfx + n)
            if cls == "gear":
                for verb in ("equip", "remove"):
                    line(f"{verb} t{tid}", s(verb) + pfx + model.known_name(tid))
        if cls == "food":
            line(f"eat t{tid}", s("eat") + model.known_name(tid))
        if cls == "pot":
            for n in names:
                line(f"drink t{tid}", s("drink") + n)
            line(f"it_was_a t{tid}", s("it_was_a") + model.known_name(tid))
        if cls == "scr":
            for n in names:
                line(f"read t{tid}", s("read") + n)
            line(f"it_was_a t{tid}", s("it_was_a") + model.known_name(tid))
        if cls == "book":
            for kn in model.known_names(tid):
                line(f"read t{tid}", s("read") + kn)
    for frag in ("tf_dart", "tf_gas", "tf_alarm"):
        line(frag, s("trap_found") + s(frag))
    line("trap_found TELEPORT", s("trap_found") + "TELEPORT")
    line("bk_read", s("bk_read"))
    return worst[1], worst[0], errs


def check_names(model):
    """Name caps, uniqueness, unique flags, potion/scroll names (§8.11 (1))."""
    errs = []
    seen = {}
    for tid in sorted(model.items.rows):
        row = model.items.rows[tid]
        cls = model.klass.get(tid)
        if row.unique and cls != "gear":
            errs.append(f"[types] {row.sym}: only gear can be unique")
        if cls in ("pot", "scr") and row.name is None:
            errs.append(f"[types] {row.sym}: potion/scroll needs its known name")
        if row.name is None:
            continue
        if HERO_TOKEN in row.name and row.sym != "IT_BOOK":
            errs.append(f"[types] {row.sym}: {HERO_TOKEN} only on IT_BOOK")
        cap = NAME_CAP_BUC_GEAR if model.buc_able(tid) else NAME_CAP_OTHER
        for nm in model.known_names(tid):
            if len(nm) > cap:
                errs.append(f"[types] {row.sym}: name '{nm}' {len(nm)} > {cap}")
            if nm in seen:
                errs.append(f"duplicate display name '{nm}' ({seen[nm]}, {row.sym})")
            seen[nm] = row.sym
    unknown = [f"{w} POTION" for w, _ in model.items.colours] + \
              [f"SCROLL {w}" for w in model.items.labels]
    for n in unknown:
        if len(n) > NAME_CAP_OTHER:
            errs.append(f"unknown appearance name '{n}' {len(n)} > {NAME_CAP_OTHER}")
    return errs


def check_stat_rows(model):
    """AMT only on food / potion rows; food and potions need it (it_stat packing)."""
    errs = []
    for tid in sorted(model.items.rows):
        row = model.items.rows[tid]
        cls = model.klass.get(tid)
        if cls in ("food", "pot"):
            if row.dfn or row.mp or row.die or row.atk:
                errs.append(f"[types] {row.sym}: food/potion rows carry AMT only")
            if row.amt == 0:
                errs.append(f"[types] {row.sym}: food/potion needs AMT")
        elif row.amt:
            errs.append(f"[types] {row.sym}: AMT only on food/potion rows")
    return errs


# ----------------------------------------------------------------------------
# emission
# ----------------------------------------------------------------------------

def _db_lines(data, comment_for=None, per_line=16):
    out = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        out.append("    DB " + ",".join(f"${b:02X}" for b in chunk))
    return out


def emit(model, out_dir):
    it = model.items
    words = model.words
    wcx_offs = pack_wcx(words)
    wbytes = pack_words(words)
    res_blob, res_off = stem_blob(model.res_stems())
    ovl_blob, ovl_off = stem_blob(model.ovl_stems())
    names_bytes = bytearray()
    names_comment = []
    for tid in range(ROWS):
        ids = model.name_ids.get(tid, (0, 0, 0))
        label = it.rows[tid].sym if tid in it.rows else "-"
        names_bytes += bytes(ids)
        names_comment.append(f"    DB ${ids[0]:02X},${ids[1]:02X},${ids[2]:02X} ; {tid}: {label}")
    attr = bytearray()
    attr_comment = []
    stat = bytearray()
    stat_comment = []
    for tid in range(ROWS):
        if tid in it.rows:
            row = it.rows[tid]
            ink = row.ink
            ink_b = 0 if ink == "APP" else ink
            label = row.sym
        else:
            ink_b, label = 0, "-"
        attr.append(ink_b)
        attr_comment.append(f"    DB ${ink_b:02X} ; {tid}: {label}")
        if tid in it.rows:
            b0, b1 = pack_stat(model, tid)
        else:
            b0, b1 = 0, 0
        stat += bytes([b0, b1])
        stat_comment.append(f"    DB ${b0:02X},${b1:02X} ; {tid}: {label}")
    app = bytes(model.app_ink)

    def words_lines():
        out = []
        pos = 0
        for k, w in enumerate(words, 1):
            out.append(f"    DB " + ",".join(f"${b:02X}" for b in pack_words([w])) + f" ; {k}: {w}")
        return out

    wcx_lines = []
    for i, off in enumerate(wcx_offs):
        wcx_lines.append(f"    DW ${off:04X} ; word {i * WCX_STEP + 1} (offset from it_words)")

    hdr = ("; GENERATED by tools/itempack.py from src/items.txt -- do not edit.\n"
           "; 3E-T4 item text, bank-1 resident block (T4b places it; not in the default build).\n")
    tab = [hdr,
           "    INCLUDE \"items_ids.inc\"",
           "",
           "; it_words: word table, id k = (k-1)th word; last char | $80, no terminator.",
           "it_words:"] + words_lines() + [
           "",
           "; it_wcx: DW offset (from it_words) of word 1, 9, 17, ... (every 8th word).",
           "it_wcx:"] + wcx_lines + [
           "",
           "; it_name: 44 rows x 3 B word ids (1-based, 0 = none). $FF (ITN_HERO) = the hero tome word:",
           "; item_name substitutes W_WAR (Warrior/knight) or W_SPELL (Mage) for it; TOME is shared.",
           "it_name:"] + names_comment + [
           "",
           "; it_stems: resident log stems, 0-terminated ASCII (S3_* in items_ids.inc).",
           "it_stems:"] + _db_lines(res_blob) + [
           "it_stems_end:",
           "",
           "; --- outside the 700-B resident budget (placement open, see the report) ---",
           "; it_attr: floor / inventory ink per type row. 0 = APP (potion: app_attr[appearance]).",
           "it_attr:"] + attr_comment + [
           "; app_attr: potion appearance inks, index = appearance (RUBY AZURE EMERALD AMBER VIOLET MILKY).",
           "app_attr:"] + _db_lines(app) + [
           "; it_stat: 2 B per row: byte0 = DIE | (ATK&$0F)<<4; byte1 = AMT (food/potion) or DEF | MP<<4.",
           "it_stat:"] + stat_comment + [
           "it_tab_end:",
           "",
           "    ; --- budgets (game.md §8.11 (5)); a failure here is a packer bug or a data overrun ---",
           "    ASSERT (it_wcx - it_words) == ITW_BYTES",
           "    ASSERT (it_stems - it_name) == ITN_BYTES",
           "    ASSERT (it_wcx - it_words) + (it_stems - it_name) <= ITB_REFS",
           "    ASSERT it_stems_end - it_stems <= ITB_STEMS",
           "    ASSERT it_stems_end - it_words <= ITB_RESIDENT",
           "    ASSERT it_stems_end - it_stems == ITS_LEN",
           ""]
    ovl = [hdr,
           "    INCLUDE \"items_ids.inc\"",
           "",
           "; it_ovl_stems: overlay-only stems (page verbs and their effects), 0-terminated ASCII.",
           "it_ovl_stems:"] + _db_lines(ovl_blob) + [
           "it_ovl_stems_end:",
           "    ASSERT it_ovl_stems_end - it_ovl_stems == ITO_LEN",
           f"    ASSERT it_ovl_stems_end - it_ovl_stems <= ITB_OVL",
           ""]

    # ids include file
    ids = [hdr.rstrip("\n"),
           "; word ids (1-based, table order), appearance bases, stem offsets, sizes",
           "; include guard: items_tab.asm and items_ovl_stems.asm both INCLUDE this file",
           "    IFNDEF ITEMS_IDS_INC",
           "    DEFINE ITEMS_IDS_INC",
           f"ITW_COUNT        EQU {len(words)}",
           f"ITW_BYTES        EQU {len(wbytes)}",
           f"ITW_WCX_N        EQU {len(wcx_offs)}",
           f"ITW_WCX_STEP     EQU {WCX_STEP}",
           f"ITN_ROWS         EQU {ROWS}",
           f"ITN_BYTES        EQU {ROWS * 3}",
           f"ITN_HERO         EQU ${HERO_MARK:02X}   ; it_name id: hero tome word (W_WAR / W_SPELL)",
           f"ITB_REFS         EQU {BUDGET_REFS}",
           f"ITB_STEMS        EQU {BUDGET_STEMS}",
           f"ITB_RESIDENT     EQU {BUDGET_RESIDENT}",
           f"ITB_OVL          EQU {BUDGET_OVL}",
           f"ITS_LEN          EQU {len(res_blob)}",
           f"ITO_LEN          EQU {len(ovl_blob)}",
           f"W_APP_POT        EQU {model.app_pot}   ; + k = potion colour k (k 0..{COLOUR_COUNT - 1})",
           f"W_APP_SCR        EQU {model.app_scr}   ; + k = scroll label k (k 0..{LABEL_COUNT - 1})",
           ]
    for k, w in enumerate(words, 1):
        ids.append(f"W_{w:<12}EQU {k}")
    for st in model.res_stems():
        ids.append(f"S3_{st.name.upper():<12}EQU {res_off[st.name]}   ; offset in it_stems")
    for st in model.ovl_stems():
        ids.append(f"S3O_{st.name.upper():<11}EQU {ovl_off[st.name]}   ; offset in it_ovl_stems")
    ids.append("    ENDIF")
    ids.append("")

    os.makedirs(out_dir, exist_ok=True)
    files = {
        "items_tab.asm": "\n".join(tab) + "\n",
        "items_ovl_stems.asm": "\n".join(ovl) + "\n",
        "items_ids.inc": "\n".join(ids) + "\n",
    }
    for name, text in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
    return {"words": len(wbytes), "wcx": 2 * len(wcx_offs), "names": ROWS * 3,
            "res_stems": len(res_blob), "ovl_stems": len(ovl_blob),
            "attr": len(attr), "app": len(app), "stat": len(stat)}


# ----------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------

def run(src, defs, strings_path, out_dir, quiet=False):
    """-> (budgets dict, [errors]). Writes outputs only when there are no errors."""
    syms = parse_defs(defs)
    strings = parse_strings(strings_path)
    items = parse_items(src, syms)
    model = Model(items, syms, strings)
    errors = list(model.errors)
    errors += check_names(model)
    errors += check_stat_rows(model)
    worst_len, worst_line, comp_errs = check_composed(model)
    errors += comp_errs
    if errors:
        return None, errors, model
    b = emit(model, out_dir)
    refs = b["words"] + b["names"]
    resident = b["words"] + b["wcx"] + b["names"] + b["res_stems"]
    if refs > BUDGET_REFS:
        errors.append(f"words+refs {refs} > {BUDGET_REFS}")
    if b["res_stems"] > BUDGET_STEMS:
        errors.append(f"resident stems {b['res_stems']} > {BUDGET_STEMS}")
    if resident > BUDGET_RESIDENT:
        errors.append(f"resident total {resident} > {BUDGET_RESIDENT}")
    if b["ovl_stems"] > BUDGET_OVL:
        errors.append(f"overlay stems {b['ovl_stems']} > {BUDGET_OVL}")
    b.update(refs=refs, resident=resident, worst_len=worst_len, worst_line=worst_line)
    return b, errors, model


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--defs", default=DEFS_DEFAULT)
    ap.add_argument("--strings", default=STRINGS_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    a = ap.parse_args(argv)
    try:
        b, errors, _model = run(a.src, a.defs, a.strings, a.out)
    except ItemsError as e:
        print(f"itempack: ERROR: {e}", file=sys.stderr)
        return 1
    if errors:
        for e in errors:
            print(f"itempack: ERROR: {e}", file=sys.stderr)
        return 1
    print(f"itempack: words+refs {b['refs']} / {BUDGET_REFS} (words {b['words']} B, 65 ids; "
          f"refs {b['names']} B, {ROWS} rows)")
    print(f"itempack: resident stems {b['res_stems']} / {BUDGET_STEMS}")
    print(f"itempack: resident total WITHOUT it_wcx {b['resident'] - b['wcx']} / {BUDGET_RESIDENT}; "
          f"WITH it_wcx ({b['wcx']} B) {b['resident']} / {BUDGET_RESIDENT}")
    print(f"itempack: overlay stems {b['ovl_stems']} / {BUDGET_OVL}")
    print(f"itempack: outside resident budget: attr {b['attr']} + app {b['app']} + stat {b['stat']} = "
          f"{b['attr'] + b['app'] + b['stat']} B")
    print(f"itempack: longest composed line {b['worst_len']} / {LOG_MAX}: {b['worst_line']}")
    print(f"itempack: wrote {a.out}/items_tab.asm, items_ovl_stems.asm, items_ids.inc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
