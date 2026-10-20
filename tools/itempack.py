#!/usr/bin/env python3
"""Pack the 3E item names, per-type numbers and message stems (3E-T4).

Input : src/items.txt (format documented in that file's header) and the
        constants of src/item_defs.asm (IT_* type ids, IT_COUNT) and the
        bank-0 strings of src/strings.txt (E: references).
Output (default build/text/, overridable with --out DIR; stdout = budgets):
  items_tab.asm       bank-1 resident block: it_words, it_wcx, it_name,
                      it_stems(_end) (+ ASSERTs). The per-type ink (it_attr)
                      is NOT emitted: src/lowram.asm it_tab carries it.
  items_fx_stems.asm  overlay stems of the effect / quick-use lines (it_fx_stems,
                      S_FX_*) followed by it_stat (2 B per type row); the pair
                      ASSERTs <= 700 B raw.
  items_ovl_stems.asm overlay page stems (it_ovl_stems, S3O_*, ASSERT <= 310 B).
  items_ids.inc       W_* word ids, S3_* / S_FX_* / S3O_* stem offsets, ITW_* /
                      ITN_* / ITS_* / ITF_* / ITO_* sizes

Word table: raw ASCII, the last char with bit 7 set, no terminator. Word id
is 1-based (0 = none in a name ref), id k = index k-1 in the table. it_wcx
holds one DW (offset from it_words) per 8 words: a lookup starts at
it_wcx[(k-1) >> 3] and skips (k-1) & 7 words (<= 7 scans).

Type rows: it_name = 3 word ids per row (0-padded, no terminator when full),
44 rows, one per type id. IT_BOOK's first word is HERO_MARK ($FF): item_name
substitutes W_WAR (Warrior/knight) or W_SPELL (Mage); the TOME word is shared.
it_stat = 2 B per row: byte0 = DIE | (ATK & $0F) << 4; byte1 = AMT (food,
potions) or (DEF & $0F) | (MP << 4) (gear).

Stems: 0-terminated ASCII, offset = S3_<NAME> (resident) / S_FX_<NAME> (fx)
/ S3O_<NAME> (page).

CHECKS (any failure = message on stderr and exit 1; nothing is written):
  - every word A-Z and <= 8 chars; 48 distinct words (game.md §8.11 item 2);
  - every name 1..3 words, <= 18 chars; no duplicate display name; only gear
    is unique;
  - every composed line <= 32 chars (LOG_MAX): pick / equip / remove /
    discard (no prefix), eat / drink / read and trap_found, plus the
    bank-0 'YOU READ THE BOOK';
  - E: stems equal their src/strings.txt value; stem texts printable,
    upper case, no '"' and no byte 0;
  - byte budgets: words+refs <= 460, resident stems <= 480, resident total
    (words + wcx + names + stems) <= 700, fx stems + it_stat <= 700 (raw),
    page overlay stems <= 310.

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
NAME_CAP = 18
WORD_COUNT_SPEC = 48      # §8.11 item 2: 2 book words + names (no BUC / appearance / OF)
WCX_STEP = 8
ROWS = 44                 # one row per type id 0..43 (IT_COUNT)
HERO_TOKEN = "<HERO>"     # [types] name token: the class book's first word
HERO_MARK = 0xFF          # it_name id; item_name substitutes W_WAR / W_SPELL
HERO_WORD = {"warrior": "WAR", "knight": "WAR", "mage": "SPELL"}
BUDGET_REFS = 460         # words + name refs
BUDGET_STEMS = 480        # resident stems
BUDGET_RESIDENT = 700     # words + wcx + names + resident stems
BUDGET_FX = 700           # fx overlay stems + it_stat (raw)
BUDGET_OVL = 310          # page overlay stems


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
        self.ink = ink           # int (floor / inventory ink; 0 = none)
        self.die, self.atk, self.dfn, self.mp, self.amt = stat
        self.unique = unique
        self.line_no = line_no


class Stem:
    def __init__(self, name, group, ref, text, line_no):
        self.name = name
        self.group = group        # "res" | "fx" | "page"
        self.ref = ref            # None for N, else the strings.txt name
        self.text = text
        self.line_no = line_no


class Items:
    def __init__(self):
        self.book = []            # [words]: W_WAR / W_SPELL seeds
        self.rows = {}            # tid -> Row
        self.stems = []           # [Stem]


def _ink(tok, where):
    if tok == "-":
        return 0
    if re.fullmatch(r"\$[0-9A-Fa-f]{2}", tok):
        return int(tok[1:], 16)
    raise ItemsError(f"{where}: bad INK '{tok}' (want $xx or -)")


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
            if section not in ("book", "types", "stems_resident", "stems_fx", "stems_page"):
                raise ItemsError(f"{where}: unknown section [{section}]")
            continue
        if section == "book":
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
        elif section in ("stems_resident", "stems_fx", "stems_page"):
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) != 3:
                raise ItemsError(f"{where}: stem row needs NAME | SRC | \"TEXT\"")
            name, src, text_q = parts
            if re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
                raise ItemsError(f"{where}: stem NAME must be lower_case")
            group = {"stems_resident": "res", "stems_fx": "fx", "stems_page": "page"}[section]
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
        for tid in sorted(it.rows):
            row = it.rows[tid]
            if row.name:
                for w in row.name.split():
                    if w != HERO_TOKEN:
                        self._add(w, f"[types] {row.sym}")
        if len(self.words) != WORD_COUNT_SPEC:
            self.errors.append(f"word count {len(self.words)} != {WORD_COUNT_SPEC} (game.md §8.11 (1))")

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

    def known_names(self, tid):
        """Display names: two for the class book (one per hero kind), else <= 1."""
        row = self.items.rows[tid]
        if row.name is None:
            return []
        if HERO_TOKEN not in row.name:
            return [row.name]
        return [row.name.replace(HERO_TOKEN, w) for w in ("WAR", "SPELL")]

    def known_name(self, tid):
        """The single name (not for the class book: use known_names)."""
        names = self.known_names(tid)
        return names[0] if names else None

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
                     "drink", "read", "eat", "equip", "remove", "discard"):
            if need not in self.stem:
                self.errors.append(f"[stems] missing '{need}'")

    def stem_text(self, name):
        return self.stem[name].text

    def _group(self, g):
        return [st for st in self.items.stems if st.group == g and st.ref is None]

    def res_stems(self):
        return self._group("res")

    def fx_stems(self):
        return self._group("fx")

    def page_stems(self):
        return self._group("page")


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
        names = model.known_names(tid)
        for n in names:
            line(f"pick t{tid}", s("pick") + n)
            line(f"discard t{tid}", s("discard") + n)
        if cls == "gear":
            for verb in ("equip", "remove"):
                line(f"{verb} t{tid}", s(verb) + model.known_name(tid))
        if cls == "food":
            line(f"eat t{tid}", s("eat") + model.known_name(tid))
        if cls == "pot":
            for n in names:
                line(f"drink t{tid}", s("drink") + n)
        if cls == "scr":
            for n in names:
                line(f"read t{tid}", s("read") + n)
        if cls == "book":
            for kn in model.known_names(tid):
                line(f"read t{tid}", s("read") + kn)
    for frag in ("tf_dart", "tf_gas", "tf_alarm"):
        line(frag, s("trap_found") + s(frag))
    line("trap_found TELEPORT", s("trap_found") + "TELEPORT")
    line("bk_read", s("bk_read"))
    return worst[1], worst[0], errs


def check_names(model):
    """Name caps, uniqueness, unique flags, potion/scroll names (§8.11 item 2)."""
    errs = []
    seen = {}
    for tid in sorted(model.items.rows):
        row = model.items.rows[tid]
        cls = model.klass.get(tid)
        if row.unique and cls != "gear":
            errs.append(f"[types] {row.sym}: only gear can be unique")
        if cls in ("pot", "scr") and row.name is None:
            errs.append(f"[types] {row.sym}: potion/scroll needs its fixed name")
        if row.name is None:
            continue
        if HERO_TOKEN in row.name and row.sym != "IT_BOOK":
            errs.append(f"[types] {row.sym}: {HERO_TOKEN} only on IT_BOOK")
        for nm in model.known_names(tid):
            if len(nm) > NAME_CAP:
                errs.append(f"[types] {row.sym}: name '{nm}' {len(nm)} > {NAME_CAP}")
            if nm in seen:
                errs.append(f"duplicate display name '{nm}' ({seen[nm]}, {row.sym})")
            seen[nm] = row.sym
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

def _db_lines(data, per_line=16):
    out = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        out.append("    DB " + ",".join(f"${b:02X}" for b in chunk))
    return out


def sizes(model):
    """Byte sizes of every emitted block (no file output)."""
    words = model.words
    res_blob, _ = stem_blob(model.res_stems())
    fx_blob, _ = stem_blob(model.fx_stems())
    page_blob, _ = stem_blob(model.page_stems())
    return {"nwords": len(words), "words": len(pack_words(words)),
            "wcx": 2 * len(pack_wcx(words)), "names": ROWS * 3,
            "res_stems": len(res_blob), "fx_stems": len(fx_blob),
            "stat": ROWS * 2, "page_stems": len(page_blob)}


def emit(model, out_dir):
    it = model.items
    words = model.words
    wcx_offs = pack_wcx(words)
    wbytes = pack_words(words)
    res_blob, res_off = stem_blob(model.res_stems())
    fx_blob, fx_off = stem_blob(model.fx_stems())
    page_blob, page_off = stem_blob(model.page_stems())
    names_comment = []
    for tid in range(ROWS):
        ids = model.name_ids.get(tid, (0, 0, 0))
        label = it.rows[tid].sym if tid in it.rows else "-"
        names_comment.append(f"    DB ${ids[0]:02X},${ids[1]:02X},${ids[2]:02X} ; {tid}: {label}")
    stat_comment = []
    for tid in range(ROWS):
        if tid in it.rows:
            b0, b1 = pack_stat(model, tid)
            label = it.rows[tid].sym
        else:
            b0, b1, label = 0, 0, "-"
        stat_comment.append(f"    DB ${b0:02X},${b1:02X} ; {tid}: {label}")

    def words_lines():
        out = []
        for k, w in enumerate(words, 1):
            out.append(f"    DB " + ",".join(f"${b:02X}" for b in pack_words([w])) + f" ; {k}: {w}")
        return out

    wcx_lines = []
    for i, off in enumerate(wcx_offs):
        wcx_lines.append(f"    DW ${off:04X} ; word {i * WCX_STEP + 1} (offset from it_words)")

    hdr = ("; GENERATED by tools/itempack.py from src/items.txt -- do not edit.\n"
           "; 3E-T4 item text (T4b places it; not in the default build).\n")
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
           "; it_stems: resident log stems (turn-path lines only), 0-terminated ASCII (S3_* in items_ids.inc).",
           "it_stems:"] + _db_lines(res_blob) + [
           "it_stems_end:",
           "",
           "    ; --- budgets (game.md §8.11 (5)); a failure here is a packer bug or a data overrun ---",
           "    ASSERT (it_wcx - it_words) == ITW_BYTES",
           "    ASSERT (it_stems - it_name) == ITN_BYTES",
           "    ASSERT (it_wcx - it_words) + (it_stems - it_name) <= ITB_REFS",
           "    ASSERT it_stems_end - it_stems <= ITB_STEMS",
           "    ASSERT it_stems_end - it_words <= ITB_RESIDENT",
           "    ASSERT it_stems_end - it_stems == ITS_LEN",
           ""]
    fx = [hdr,
          "    INCLUDE \"items_ids.inc\"",
          "",
          "; it_fx_stems: effect / quick-use log stems (overlay data, S_FX_* in items_ids.inc).",
          "it_fx_stems:"] + _db_lines(fx_blob) + [
          "it_fx_stems_end:",
          "; it_stat: 2 B per row: byte0 = DIE | (ATK&$0F)<<4; byte1 = AMT (food/potion) or DEF | MP<<4.",
          "it_stat:"] + stat_comment + [
          "it_stat_end:",
          "    ASSERT it_fx_stems_end - it_fx_stems == ITF_LEN",
          "    ASSERT it_stat_end - it_stat == ITF_STAT",
          "    ASSERT (it_fx_stems_end - it_fx_stems) + (it_stat_end - it_stat) <= ITB_FX",
          ""]
    ovl = [hdr,
           "    INCLUDE \"items_ids.inc\"",
           "",
           "; it_ovl_stems: overlay page stems (S3O_* in items_ids.inc), 0-terminated ASCII.",
           "it_ovl_stems:"] + _db_lines(page_blob) + [
           "it_ovl_stems_end:",
           "    ASSERT it_ovl_stems_end - it_ovl_stems == ITO_LEN",
           "    ASSERT it_ovl_stems_end - it_ovl_stems <= ITB_OVL",
           ""]

    # ids include file
    ids = [hdr.rstrip("\n"),
           "; word ids (1-based, table order), stem offsets, sizes",
           "; include guard: items_tab.asm, items_fx_stems.asm and items_ovl_stems.asm INCLUDE this file",
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
           f"ITB_FX           EQU {BUDGET_FX}",
           f"ITB_OVL          EQU {BUDGET_OVL}",
           f"ITS_LEN          EQU {len(res_blob)}",
           f"ITF_LEN          EQU {len(fx_blob)}",
           f"ITF_STAT         EQU {ROWS * 2}",
           f"ITO_LEN          EQU {len(page_blob)}",
           ]
    for k, w in enumerate(words, 1):
        ids.append(f"W_{w:<12}EQU {k}")
    for st in model.res_stems():
        ids.append(f"S3_{st.name.upper():<12}EQU {res_off[st.name]}   ; offset in it_stems")
    for st in model.fx_stems():
        ids.append(f"S_FX_{st.name.upper():<16}EQU {fx_off[st.name]}   ; offset in it_fx_stems")
    for st in model.page_stems():
        ids.append(f"S3O_{st.name.upper():<11}EQU {page_off[st.name]}   ; offset in it_ovl_stems")
    ids.append("    ENDIF")
    ids.append("")

    os.makedirs(out_dir, exist_ok=True)
    files = {
        "items_tab.asm": "\n".join(tab) + "\n",
        "items_fx_stems.asm": "\n".join(fx) + "\n",
        "items_ovl_stems.asm": "\n".join(ovl) + "\n",
        "items_ids.inc": "\n".join(ids) + "\n",
    }
    for name, text in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)


# ----------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------

def budget_errors(b):
    """Byte-budget failures for a sizes() dict (words+refs, resident, fx, page)."""
    errs = []
    refs = b["words"] + b["names"]
    resident = b["words"] + b["wcx"] + b["names"] + b["res_stems"]
    fx = b["fx_stems"] + b["stat"]
    if refs > BUDGET_REFS:
        errs.append(f"words+refs {refs} > {BUDGET_REFS}")
    if b["res_stems"] > BUDGET_STEMS:
        errs.append(f"resident stems {b['res_stems']} > {BUDGET_STEMS}")
    if resident > BUDGET_RESIDENT:
        errs.append(f"resident total {resident} > {BUDGET_RESIDENT}")
    if fx > BUDGET_FX:
        errs.append(f"fx stems + it_stat {fx} > {BUDGET_FX}")
    if b["page_stems"] > BUDGET_OVL:
        errs.append(f"page overlay stems {b['page_stems']} > {BUDGET_OVL}")
    return errs


def run(src, defs, strings_path, out_dir, quiet=False):
    """-> (budgets dict, [errors], model). Writes outputs only when there are no errors."""
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
    b = sizes(model)
    errors += budget_errors(b)
    b.update(refs=b["words"] + b["names"],
             resident=b["words"] + b["wcx"] + b["names"] + b["res_stems"],
             fx=b["fx_stems"] + b["stat"],
             worst_len=worst_len, worst_line=worst_line)
    if errors:
        return b, errors, model
    emit(model, out_dir)
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
    print(f"itempack: words+refs {b['refs']} / {BUDGET_REFS} (words {b['words']} B, {b['nwords']} ids; "
          f"refs {b['names']} B, {ROWS} rows)")
    print(f"itempack: resident stems {b['res_stems']} / {BUDGET_STEMS} (turn-path lines)")
    print(f"itempack: resident total WITHOUT it_wcx {b['resident'] - b['wcx']} / {BUDGET_RESIDENT}; "
          f"WITH it_wcx ({b['wcx']} B) {b['resident']} / {BUDGET_RESIDENT}")
    print(f"itempack: fx stems {b['fx_stems']} + it_stat {b['stat']} = {b['fx']} / {BUDGET_FX} (raw, overlay)")
    print(f"itempack: page overlay stems {b['page_stems']} / {BUDGET_OVL}")
    print(f"itempack: longest composed line {b['worst_len']} / {LOG_MAX}: {b['worst_line']}")
    print(f"itempack: wrote {a.out}/items_tab.asm, items_fx_stems.asm, items_ovl_stems.asm, items_ids.inc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
