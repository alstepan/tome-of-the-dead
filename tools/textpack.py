#!/usr/bin/env python3
"""Pack the game's message strings into dictionary-token streams (B3B-13).

Pre-build step (tools/build.sh runs it before sjasmplus, like zx0_sources.py).
Reads src/strings.txt (the single string source) and writes
  build/text/strings_ids.inc  TX_<NAME> EQU id, TXL_<NAME> EQU decoded length,
                              TX_COUNT / TX_TOKENS / TEXT_RAW / TEXT_PACKED,
                              ASSERT TXL_<NAME> <= LOG_MAX per string
                              (INCLUDEd at the end of src/defs.asm)
  build/text/strings.asm      the text block (INCLUDEd by src/main.asm in the
                              bank-1 vdata area, DISPed to its runtime $C000
                              address; docs/memory-map.md "Text (B3B-13)")
then re-parses the EMITTED strings.asm, decodes every string with the same
algorithm as the Z80 getter (tk_get, src/panel2.asm) and fails (exit 1) unless
each one is bit-exact with src/strings.txt, emits only chars 32..127 and fits
LOG_MAX.

Stream format (user decision 2026-10-03, plan B3B-13):
  0          end of string
  32..127    the literal char
  128..255   dictionary token t: entry t - 128
Dictionary entry = 2+ literal chars (32..127), the LAST one with bit 7 set
(no length byte, no terminator; no nesting: an entry never holds a token).
Text block layout (MEM-RECLAIM w2d; runtime bank-0 $C000-based, 256-aligned):
  tx_entries  the entries, <= DICT_MAX (256) B: one page, so an entry's
              address is (tx_entries >> 8, offset) - tk_get loads B as a constant;
              0-padded to the next page (the greedy fills it: ~1 B)
  tx_tab      (page-aligned: tx_ptr loads H as a constant) DW x
              ceil(TX_COUNT / TX_STRIDE) (absolute) the stream of string id
              k * TX_STRIDE; string id i is reached by skipping i % TX_STRIDE
              0-terminated streams from it (tx_ptr). TX_STRIDE 2: an odd id
              skips its predecessor's stream - HOT_SKIP_MAX caps that for the
              log-width (hot: impact / combat / cast lines) ids; 256 ids =
              128 words = exactly the $C100 page
  tx_dict     DB x TX_TOKENS   token t -> its entry's offset from tx_entries
  then the 0-terminated streams, in id order (the skip relies on it).
The dictionary is built greedily from the real strings: repeatedly take the
literal substring with the best saving n*(L-1) - (L+1) (n non-overlapping
uses, L chars, +1 for its tx_dict byte) that still fits DICT_MAX, until none
saves a byte or 128 tokens are used. Deterministic (ties: longer, then
lexicographically smaller).

Dynamic parts (kind names, numbers) are composed into MSG_BUF from whole
streams (concatenating streams keeps a valid stream: tokens are 1 byte and
self-contained) or as literal digits; the getter decodes at print time.

Long static text (3C, C3-4: help pages, later book/scroll descriptions): a
second output class, `@long NAME ... @end` blocks in src/strings.txt. Each block
is plain ASCII lines (32..126, upper case, <= 42 chars, the 6x8 page width);
it is NOT dictionary-tokenised (ZX0 already finds the repeated words, and the
block then needs no shared dictionary). Raw image of a block:
  byte 0      number of lines N (a blank line is just its 0 terminator)
  then N lines, each 0-terminated (a plain tk_get stream: all chars < 128)
The image is ZX0-packed (tools/bin/zx0: v2, optimal, forward, no header,
decompress with the standard dzx0) and every block is round-tripped through
tools/bin/dzx0 at build time. Emitted:
  build/text/longtext.asm   lt_base: lt_tab (stride 4: DW packed ptr, DW raw
                            length) then the packed blocks; DISP it like
                            strings.asm (words = lt_base + offset)
  strings_ids.inc           LT_<NAME> id, LTR_/LTP_<NAME> raw/packed bytes,
                            LT_COUNT, LT_BUF_MAX (largest raw image = the
                            unpack buffer size), LONG_RAW, LONG_PACKED
Runtime: unpack block i to a buffer, then stream lines from buffer+1 (tk_get
state is a plain pointer, so a buffer is just another stream source).

Style checks (fail the build): every string upper case, 32..126, no '"', no
trailing full stop, no double spaces (info_* excepted: field padding), length
<= LIMIT (32; 42 for info_* / ft_*, the 6x8-font lines); info_* fields land on
the 16 / 28 boundaries (see src/strings.txt).

Usage: tools/textpack.py [--report] [--src FILE]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src/strings.txt")
OUT_DIR = os.path.join(REPO, "build/text")
OUT_IDS = os.path.join(OUT_DIR, "strings_ids.inc")
OUT_ASM = os.path.join(OUT_DIR, "strings.asm")
OUT_LONG = os.path.join(OUT_DIR, "longtext.asm")
ZX0 = os.path.join(REPO, "tools/bin/zx0")
DZX0 = os.path.join(REPO, "tools/bin/dzx0")
WIDE_MAX = 42           # 6x8-font lines (info line, footers, long text rows)
WIDE_PREFIXES = ("info_", "ft_")
INFO_FIELDS = (16, 28)  # info line: numbers from char 16, notes from char 28
LOG_MAX = 32            # src/level_defs.asm (ASSERTed in the output too)
MAX_TOKENS = 128
MAX_STRINGS = 256      # ids are bytes (A / DB tables); tx_tab fills one page at 256
MAX_ENTRY = 16          # longest dictionary entry considered
DICT_MAX = 256          # entry bytes: one page (tk_get: B = tx_entries >> 8)
TX_STRIDE = 2           # tx_tab: one word per 2 ids (tx_ptr: res 0,l / rra = the skip flag)
HOT_SKIP_MAX = 24       # w2d review: an odd log-width id skips <= 24 B (~0.6k T) in tx_ptr


def fail(msg):
    sys.exit(f"textpack: {msg}")


def limit_for(name):
    return WIDE_MAX if name.lower().startswith(WIDE_PREFIXES) else LOG_MAX


def style_check(where, name, text, limit, full_stop=True):
    """Style rules shared by every string (game.md §3.4); fails the build."""
    bad = [c for c in text if not 32 <= ord(c) <= 126 or c == '"']
    if bad:
        fail(f"{where}: {name}: chars outside 32..126 (or a quote): {bad!r}")
    if any("a" <= c <= "z" for c in text):
        fail(f"{where}: {name}: upper case only (game.md §3.4)")
    if full_stop and text.endswith("."):
        fail(f"{where}: {name}: no trailing full stop (game.md §3.4)")
    if len(text) > limit:
        fail(f"{where}: {name}: {len(text)} chars > {limit}")


def info_check(where, name, text):
    """info_* = name | numbers | notes, pre-padded to the info-line fields."""
    if text != text.rstrip():
        fail(f"{where}: {name}: trailing space (pad only between fields)")
    if not text.strip() or text[0] == " ":
        fail(f"{where}: {name}: info line must start with the name")
    n0, n1 = INFO_FIELDS
    if len(text) > n0 and text[n0 - 1] != " ":
        fail(f"{where}: {name}: name field longer than {n0 - 1} chars")
    if len(text) > n0 and text[n0:n1].strip() and text[n0] == " ":
        fail(f"{where}: {name}: numbers must start at char {n0}")
    if len(text) > n1:
        if text[n1 - 1] != " ":
            fail(f"{where}: {name}: numbers field longer than {n1 - n0 - 1} chars")
        if text[n1] == " ":
            fail(f"{where}: {name}: notes must start at char {n1}")


def read_source(path=SRC):
    """-> ([(name, text)] short strings in file order, [(name, [lines])] long)."""
    out, longs, seen = [], [], set()
    cur = None
    for n, line in enumerate(open(path), 1):
        s = line.rstrip("\n")
        where = f"{path}:{n}"
        if cur is not None:
            if s.strip() == "@end":
                if not cur[1]:
                    fail(f"{where}: empty @long block {cur[0]}")
                longs.append(cur)
                cur = None
            elif s.lstrip().startswith("#"):
                fail(f"{where}: '#' comments are not allowed inside @long")
            else:
                style_check(where, cur[0], s, WIDE_MAX, full_stop=False)
                cur[1].append(s)
            continue
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        m = re.match(r"^@long\s+(\w+)\s*$", s)
        if m:
            name = m.group(1)
            if name.lower() in seen:
                fail(f"{where}: duplicate name {name}")
            seen.add(name.lower())
            cur = (name, [])
            continue
        m = re.match(r'^(\w+)\s+"([^"]*)"\s*$', s)
        if not m:
            fail(f"{where}: expected `name \"TEXT\"` or @long: {s!r}")
        name, text = m.group(1), m.group(2)
        if name.lower() in seen:
            fail(f"{where}: duplicate name {name}")
        seen.add(name.lower())
        style_check(where, name, text, limit_for(name))
        if name.lower().startswith("info_"):
            info_check(where, name, text)
        elif "  " in text:
            fail(f"{where}: {name}: double space (only info_* pads)")
        out.append((name, text))
    if cur is not None:
        fail(f"{path}: @long {cur[0]} has no @end")
    if len(out) > MAX_STRINGS:
        fail(f"more than {MAX_STRINGS} strings: ids are bytes (A / DB tables); "
             "beyond that tx_tab outgrows its page: tx_ptr needs a 16-bit index")
    if len(longs) > 64:
        fail("more than 64 long blocks")
    return out, longs


def read_strings(path=SRC):
    return read_source(path)[0]


def count_uses(streams, cand):
    """Non-overlapping left-to-right uses of literal `cand` in literal runs
    (the reference definition; build_dict keeps the same counts incrementally)."""
    n, L = 0, len(cand)
    for st in streams:
        i = 0
        while i <= len(st) - L:
            if all(isinstance(st[i + k], str) for k in range(L)) and \
                    "".join(st[i:i + L]) == cand:
                n += 1
                i += L
            else:
                i += 1
    return n


def stream_counts(st):
    """{substring: non-overlapping greedy uses} for every literal substring of
    2..MAX_ENTRY chars of one stream = count_uses per candidate, in one pass:
    positions ascend, so an occurrence counts iff it starts at or after the
    end of the last counted one (per run; runs never share an occurrence)."""
    cnt = {}
    run = []
    for it in st + [None]:
        if isinstance(it, str):
            run.append(it)
            continue
        r = "".join(run)
        last = {}
        n = len(r)
        for i in range(n - 1):
            for L in range(2, min(MAX_ENTRY, n - i) + 1):
                c = r[i:i + L]
                if last.get(c, 0) <= i:
                    last[c] = i + L
                    cnt[c] = cnt.get(c, 0) + 1
        run = []
    return cnt


def build_dict(texts):
    """Greedy dictionary (see the module docstring). Same choices as the
    original full rescan (every candidate's count_uses each round, ~3 min on
    200 strings), but the counts are kept incrementally: per-stream count maps
    summed into `total`; a round re-counts only the streams the chosen entry
    was substituted into, and the best is searched among the candidates used
    at least twice (one use never saves: (L-1) - (L+2) < 0)."""
    streams = [list(t) for t in texts]
    per = [stream_counts(st) for st in streams]
    total, multi = {}, set()

    def add(cnt, sign):
        for c, n in cnt.items():
            v = total.get(c, 0) + sign * n
            if v:
                total[c] = v
            else:
                del total[c]
            if v >= 2:
                multi.add(c)
            else:
                multi.discard(c)

    for cnt in per:
        add(cnt, 1)
    entries, used = [], 0
    while len(entries) < MAX_TOKENS:
        best = None
        for c in multi:
            L = len(c)
            g = total[c] * (L - 1) - (L + 1)
            if g <= 0 or used + L > DICT_MAX or (best is not None and (g, L) < best[0][:2]):
                continue
            key = (g, L, [-ord(ch) for ch in c])
            if best is None or key > best[0]:
                best = (key, c)
        if best is None:
            break
        c = best[1]
        tok = len(entries)
        entries.append(c)
        L = len(c)
        used += L
        for k, st in enumerate(streams):
            if c not in per[k]:
                continue
            i = 0
            while i <= len(st) - L:
                if all(isinstance(st[i + j], str) for j in range(L)) and \
                        "".join(st[i:i + L]) == c:
                    st[i:i + L] = [tok]
                i += 1
            add(per[k], -1)
            per[k] = stream_counts(st)
            add(per[k], 1)
    return entries, streams


def dp_parse(text, entries):
    """Min-length token/literal parse of `text` over the fixed dictionary."""
    n = len(text)
    best = [0] * (n + 1)
    pick = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        best[i], pick[i] = best[i + 1] + 1, None
        for t, e in enumerate(entries):
            if text.startswith(e, i) and best[i + len(e)] + 1 < best[i]:
                best[i], pick[i] = best[i + len(e)] + 1, t
    out, i = [], 0
    while i < n:
        if pick[i] is None:
            out.append(text[i])
            i += 1
        else:
            out.append(pick[i])
            i += len(entries[pick[i]])
    return out


def encode(texts):
    entries, streams = build_dict(texts)
    # Optimal re-parse with the SAME dictionary (no decoder change): the greedy
    # substitution order can pick a token that blocks two better ones; a DP over
    # each text (1 B per literal or token, ties -> fewer tokens) is never longer.
    streams = [dp_parse(t, entries) for t in texts]
    ents = []
    for e in entries:
        b = [ord(ch) for ch in e]
        b[-1] |= 0x80
        ents.append(bytes(b))
    strs = [bytes((0x80 + it) if isinstance(it, int) else ord(it) for it in st) + b"\0"
            for st in streams]
    return ents, strs


class TextImg(bytes):
    """The block image (bytes) + where its tables sit (offsets from text_base)."""
    dict_off = tab_off = 0


def layout(ents, strs, base=0):
    """-> (image, tx_tab offsets of every string, entry offsets) for a block at
    `base` (offsets from the block start; the image keeps every TX_STRIDE-th)."""
    n_s, n_t = len(strs), len(ents)
    e_off, off = [], 0
    for e in ents:
        e_off.append(off)
        off += len(e)
    if off > DICT_MAX:
        fail(f"dictionary {off} B > {DICT_MAX}")
    pad = DICT_MAX - off
    tab_off = DICT_MAX
    dict_off = tab_off + 2 * ((n_s + TX_STRIDE - 1) // TX_STRIDE)
    off = dict_off + n_t
    s_off = []
    for s in strs:
        s_off.append(off)
        off += len(s)
    img = bytearray()
    for e in ents:
        img += e
    img += bytes(pad)
    for o in s_off[::TX_STRIDE]:
        img += (base + o).to_bytes(2, "little")
    img += bytes(e_off)
    for s in strs:
        img += s
    img = TextImg(img)
    img.dict_off, img.tab_off = dict_off, tab_off
    return img, s_off, e_off


def expand(img, raw):
    """A token stream (bytes; stops at 0) -> text, as tk_get expands it."""
    out = []
    for a in raw:
        if a == 0:
            break
        if a < 0x80:
            out.append(chr(a))
            continue
        q = img[img.dict_off + a - 0x80]
        while True:
            c = img[q]
            q += 1
            out.append(chr(c & 0x7F))
            if c & 0x80:
                break
    return "".join(out)


def decode(img, n_strings, sid, base=0):
    """The Z80 getter's algorithm (tx_ptr + tk_get) on the block image -> chars."""
    t = img.tab_off + 2 * (sid // TX_STRIDE)
    p = int.from_bytes(img[t:t + 2], "little") - base
    for _ in range(sid % TX_STRIDE):
        p = img.index(0, p) + 1
    end = img.index(0, p)
    if end - p > 4 * WIDE_MAX:
        fail(f"string {sid}: no terminator")
    return [ord(c) for c in expand(img, img[p:end + 1])]


def emit(names, texts, ents, strs):
    img, s_off, e_off = layout(ents, strs)
    n_s, n_t = len(strs), len(ents)
    raw = sum(len(t) + 1 for t in texts)
    ids = [
        "; " + "=" * 76,
        "; strings_ids.inc — GENERATED by tools/textpack.py from src/strings.txt",
        "; (B3B-13). DO NOT EDIT. String ids, decoded lengths, sizes.",
        "; " + "=" * 76,
    ]
    for i, (nm, t) in enumerate(zip(names, texts)):
        ids.append(f"TX_{nm.upper():<16} EQU {i}")
    for nm, t in zip(names, texts):
        ids.append(f"TXL_{nm.upper():<15} EQU {len(t)}")
        lim = "LOG_MAX" if limit_for(nm) == LOG_MAX else str(limit_for(nm))
        ids.append(f"                ASSERT TXL_{nm.upper()} <= {lim}")
    ids += [f"TX_COUNT         EQU {n_s}", f"TX_TOKENS        EQU {n_t}",
            f"TX_STRIDE        EQU {TX_STRIDE}          ; tx_tab: a word per {TX_STRIDE} ids",
            f"TEXT_RAW         EQU {raw}          ; 0-terminated plain strings",
            f"TEXT_PACKED      EQU {len(img)}     ; the whole text block (tables included)",
            f"                ASSERT TX_COUNT <= {MAX_STRINGS} && TX_TOKENS <= {MAX_TOKENS}", ""]
    asm = [
        "; " + "=" * 76,
        "; strings.asm — GENERATED by tools/textpack.py from src/strings.txt (B3B-13).",
        "; DO NOT EDIT. Dictionary-token streams (format: the tool's docstring).",
        "; Words are text_base + offset; src/main.asm places the block (bank 1).",
        f"; {n_s} strings, {n_t} tokens: raw {raw} B -> {len(img)} B packed (tables included)",
        "; " + "=" * 76,
        "text_base:",
        "tx_entries:",
    ]
    for i, e in enumerate(ents):
        asm.append("        DB " + ",".join(f"${b:02X}" for b in e)
                   + f"    ; ${0x80 + i:02X} {entries_txt(e)!r}")
    pad = img.tab_off - sum(map(len, ents))
    if pad:
        asm.append("        DB " + ",".join(["$00"] * pad) + "    ; pad: tx_tab page-aligned")
    asm.append("tx_tab:")
    for i, o in enumerate(s_off[::TX_STRIDE]):
        asm.append(f"        DW text_base + {o}    ; {i * TX_STRIDE} {names[i * TX_STRIDE]}")
    asm.append("tx_dict:")
    for i, o in enumerate(e_off):
        asm.append(f"        DB ${o:02X}    ; ${0x80 + i:02X} {entries_txt(ents[i])!r}")
    asm.append("tx_strings:")
    for i, s in enumerate(strs):
        asm.append("        DB " + ",".join(f"${b:02X}" for b in s) + f"    ; {names[i]}: {texts[i]!r}")
    asm += ["text_end:", f"        ASSERT text_end - text_base == {len(img)}",
            f"        ASSERT tx_tab - tx_entries == {DICT_MAX} && tx_dict - text_base == {img.dict_off}", ""]
    return "\n".join(ids), "\n".join(asm), img, raw


def entries_txt(e):
    return "".join(chr(b & 0x7F) for b in e)


def parse_emitted(path):
    """Rebuild the block image (base 0) from the emitted DB / DW lines."""
    img, offs = bytearray(), {}
    for line in open(path):
        lab = line.split(";")[0].strip()
        if lab in ("tx_dict:", "tx_tab:"):
            offs[lab[:-1]] = len(img)
        code = line.split(";")[0].strip()
        if code.startswith("DW "):
            m = re.fullmatch(r"DW text_base \+ (\d+)", code)
            if not m:
                fail(f"emitted DW not understood: {code!r}")
            img += int(m.group(1)).to_bytes(2, "little")
        elif code.startswith("DB "):
            for t in code[3:].split(","):
                t = t.strip()
                if not re.fullmatch(r"\$[0-9A-F]{2}", t):
                    fail(f"emitted DB token not understood: {t!r}")
                img.append(int(t[1:], 16))
    img = TextImg(img)
    img.dict_off, img.tab_off = offs.get("tx_dict", 0), offs.get("tx_tab", 0)
    return img


def long_image(lines):
    """Raw image of one @long block: line count, then 0-terminated lines."""
    return bytes([len(lines)]) + b"".join(l.encode() + b"\0" for l in lines)


def long_unpack(img):
    """Reference reader of the raw image -> [lines]."""
    n, p, out = img[0], 1, []
    for _ in range(n):
        q = img.index(0, p)
        out.append(img[p:q].decode())
        p = q + 1
    if p != len(img):
        fail("long image has trailing bytes")
    return out


def zx0_pack(data):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "in.bin"), os.path.join(d, "out.zx0")
        open(i, "wb").write(data)
        subprocess.run([ZX0, "-f", i, o], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return open(o, "rb").read()


def zx0_unpack(packed):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "in.zx0"), os.path.join(d, "out.bin")
        open(i, "wb").write(packed)
        subprocess.run([DZX0, "-f", i, o], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return open(o, "rb").read()


def pack_longs(longs):
    """-> [(name, lines, raw image, packed)]; round-trips every block."""
    if longs and not (os.path.exists(ZX0) and os.path.exists(DZX0)):
        fail("tools/bin/zx0 / dzx0 missing: run tools/setup_zx0.sh")
    out = []
    for name, lines in longs:
        raw = long_image(lines)
        packed = zx0_pack(raw)
        if zx0_unpack(packed) != raw:
            fail(f"long block {name}: ZX0 round trip mismatch")
        if long_unpack(zx0_unpack(packed)) != lines:
            fail(f"long block {name}: line round trip mismatch")
        out.append((name, lines, raw, packed))
    return out


def emit_long(blocks):
    """-> (ids lines, longtext.asm text)."""
    n = len(blocks)
    ids = [f"LT_{nm.upper():<17} EQU {i}" for i, (nm, *_r) in enumerate(blocks)]
    for nm, lines, raw, packed in blocks:
        ids.append(f"LTR_{nm.upper():<16} EQU {len(raw)}")
        ids.append(f"LTP_{nm.upper():<16} EQU {len(packed)}")
    raw_t = sum(len(b[2]) for b in blocks)
    pk_t = sum(len(b[3]) for b in blocks)
    ids += [f"LT_COUNT         EQU {n}",
            f"LT_BUF_MAX       EQU {max((len(b[2]) for b in blocks), default=0)}"
            "          ; largest raw image = unpack buffer size",
            f"LONG_RAW         EQU {raw_t}",
            f"LONG_PACKED      EQU {pk_t + 4 * n}     ; packed blocks + lt_tab"]
    off = 4 * n
    offs = []
    for b in blocks:
        offs.append(off)
        off += len(b[3])
    asm = ["; " + "=" * 76,
           "; longtext.asm — GENERATED by tools/textpack.py from src/strings.txt (C3-4).",
           "; DO NOT EDIT. ZX0 (v2, forward, no header) blocks; format: the tool's docstring.",
           "; Words are lt_base + offset; place like strings.asm (DISP to the runtime address).",
           f"; {n} blocks: raw {raw_t} B -> {pk_t} B packed (+ {4 * n} B table)",
           "; " + "=" * 76,
           "lt_base:", "lt_tab:                 ; stride 4: DW packed ptr, DW raw length"]
    for i, (b, o) in enumerate(zip(blocks, offs)):
        asm.append(f"        DW lt_base + {o}, {len(b[2])}    ; {i} {b[0]}")
    for b in blocks:
        asm.append(f"lt_{b[0].lower()}:    ; {len(b[2])} -> {len(b[3])} B")
        for i in range(0, len(b[3]), 16):
            asm.append("        DB " + ",".join(f"${c:02X}" for c in b[3][i:i + 16]))
    asm += ["lt_end:", f"        ASSERT lt_end - lt_base == {off}", ""]
    return ids, "\n".join(asm), off


def parse_long_asm(text):
    """Rebuild the long block image (base 0) from the emitted DW / DB lines."""
    img = bytearray()
    for line in text.splitlines():
        code = line.split(";")[0].strip()
        if code.startswith("DW "):
            m = re.fullmatch(r"DW lt_base \+ (\d+), (\d+)", code)
            if not m:
                fail(f"emitted long DW not understood: {code!r}")
            img += int(m.group(1)).to_bytes(2, "little") + int(m.group(2)).to_bytes(2, "little")
        elif code.startswith("DB "):
            img += bytes(int(t.strip()[1:], 16) for t in code[3:].split(","))
    return bytes(img)


def write_if_changed(path, text):
    old = open(path).read() if os.path.exists(path) else None
    if old != text:
        with open(path, "w") as f:
            f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()
    pairs, longs = read_source(a.src)
    names = [n for n, _ in pairs]
    texts = [t for _, t in pairs]
    ents, strs = encode(texts)
    ids, asm, img, raw = emit(names, texts, ents, strs)
    blocks = pack_longs(longs)
    lt_ids, lt_asm, lt_len = emit_long(blocks)
    ids += "\n" + "\n".join(lt_ids) + "\n"
    os.makedirs(OUT_DIR, exist_ok=True)
    write_if_changed(OUT_IDS, ids)
    write_if_changed(OUT_ASM, asm)
    write_if_changed(OUT_LONG, lt_asm)
    # round trip on the EMITTED files
    back = parse_emitted(OUT_ASM)
    if back != img or (back.dict_off, back.tab_off) != (img.dict_off, img.tab_off):
        fail("emitted strings.asm does not re-parse to the packed image")
    for i, t in enumerate(texts):
        got = decode(back, len(texts), i)
        if any(not 32 <= c <= 127 for c in got):
            fail(f"{names[i]}: decodes to a char outside 32..127: {got}")
        if bytes(got) != t.encode():
            fail(f"{names[i]}: round trip mismatch: {bytes(got)!r} != {t!r}")
        if len(got) > limit_for(names[i]):
            fail(f"{names[i]}: {len(got)} chars > {limit_for(names[i])}")
    # w2d review: the tx_ptr skip on hot (log-width) ids is bounded, so a new or
    # reordered string cannot silently push a composed log line over the tick budget
    hot_worst = 0
    for i, nm in enumerate(names):
        if limit_for(nm) == LOG_MAX and i % TX_STRIDE:
            sk = sum(len(strs[j]) for j in range(i - i % TX_STRIDE, i))
            hot_worst = max(hot_worst, sk)
            if sk > HOT_SKIP_MAX:
                fail(f"{nm}: tx_ptr skips {sk} B (> HOT_SKIP_MAX {HOT_SKIP_MAX}): move it, or "
                     f"the long string before it, by one line in src/strings.txt")
    lb = parse_long_asm(open(OUT_LONG).read())
    if len(lb) != lt_len:
        fail("emitted longtext.asm size mismatch")
    for i, (nm, lines, rawimg, packed) in enumerate(blocks):
        p, rl = (int.from_bytes(lb[4 * i + k:4 * i + k + 2], "little") for k in (0, 2))
        if rl != len(rawimg) or long_unpack(zx0_unpack(lb[p:p + len(packed)])) != lines:
            fail(f"long block {nm}: emitted longtext.asm does not round-trip")
    print(f"textpack: {len(texts)} strings, {len(ents)} tokens, raw {raw} -> packed "
          f"{len(img)} B (streams {sum(map(len, strs))} + dict {sum(map(len, ents))} + "
          f"tables {len(img) - sum(map(len, strs)) - sum(map(len, ents))} incl. pad); round-trip ok; hot skip <= {hot_worst} B; -> build/text/")
    if blocks:
        print(f"textpack: {len(blocks)} long blocks, raw {sum(len(b[2]) for b in blocks)} -> "
              f"ZX0 {sum(len(b[3]) for b in blocks)} B (+ {4 * len(blocks)} B table); "
              f"round-trip ok")
    if a.report:
        for i, e in enumerate(ents):
            print(f"  ${0x80 + i:02X} {entries_txt(e)!r}")
        for nm, lines, rawimg, packed in blocks:
            print(f"  long {nm}: {len(rawimg)} -> {len(packed)} B")


if __name__ == "__main__":
    main()
