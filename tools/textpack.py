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
Text block layout (all addresses absolute, runtime bank-1 $C000-based):
  tx_tab    DW x TX_COUNT     string id -> its stream
  tx_dict   DW x TX_TOKENS    token t -> entry (index (t - 128) * 2)
  entries, then the 0-terminated streams.
The dictionary is built greedily from the real strings: repeatedly take the
literal substring with the best saving n*(L-1) - (L+2) (n non-overlapping
uses, L chars, +2 for its tx_dict word) until none saves a byte or 128 tokens
are used. Deterministic (ties: longer, then lexicographically smaller).

Dynamic parts (kind names, numbers) are composed into MSG_BUF from whole
streams (concatenating streams keeps a valid stream: tokens are 1 byte and
self-contained) or as literal digits; the getter decodes at print time.
3C long static text (menus, help, books): the same token streams, ZX0-packed
per text and unpacked into a buffer that print6t streams (tk_get state = a
plain pointer, so a buffer is just another stream source).

Usage: tools/textpack.py [--report]
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src/strings.txt")
OUT_DIR = os.path.join(REPO, "build/text")
OUT_IDS = os.path.join(OUT_DIR, "strings_ids.inc")
OUT_ASM = os.path.join(OUT_DIR, "strings.asm")
LOG_MAX = 32            # src/level_defs.asm (ASSERTed in the output too)
MAX_TOKENS = 128
MAX_ENTRY = 16          # longest dictionary entry considered


def fail(msg):
    sys.exit(f"textpack: {msg}")


def read_strings(path=SRC):
    """-> [(name, text)] in file order."""
    out, seen = [], set()
    for n, line in enumerate(open(path), 1):
        s = line.rstrip("\n")
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        m = re.match(r'^(\w+)\s+"([^"]*)"\s*$', s)
        if not m:
            fail(f"{path}:{n}: expected `name \"TEXT\"`: {s!r}")
        name, text = m.group(1), m.group(2)
        if name.lower() in seen:
            fail(f"{path}:{n}: duplicate name {name}")
        seen.add(name.lower())
        bad = [c for c in text if not 32 <= ord(c) <= 126]
        if bad:
            fail(f"{path}:{n}: {name}: chars outside 32..126: {bad!r}")
        if any("a" <= c <= "z" for c in text):
            fail(f"{path}:{n}: {name}: upper case only (game.md §3.4)")
        if len(text) > LOG_MAX:
            fail(f"{path}:{n}: {name}: {len(text)} chars > LOG_MAX {LOG_MAX}")
        out.append((name, text))
    if len(out) > 128:
        fail("more than 128 strings: tx_ptr indexes with `add a, a`")
    return out


def count_uses(streams, cand):
    """Non-overlapping left-to-right uses of literal `cand` in literal runs."""
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


def build_dict(texts):
    streams = [list(t) for t in texts]
    entries = []
    while len(entries) < MAX_TOKENS:
        cands = set()
        for st in streams:
            run = []
            for it in st + [None]:
                if isinstance(it, str):
                    run.append(it)
                    continue
                r = "".join(run)
                for i in range(len(r)):
                    for L in range(2, min(MAX_ENTRY, len(r) - i) + 1):
                        cands.add(r[i:i + L])
                run = []
        best = None
        for c in cands:
            g = count_uses(streams, c) * (len(c) - 1) - (len(c) + 2)
            key = (g, len(c), [-ord(ch) for ch in c])
            if g > 0 and (best is None or key > best[0]):
                best = (key, c)
        if best is None:
            break
        c = best[1]
        tok = len(entries)
        entries.append(c)
        L = len(c)
        for st in streams:
            i = 0
            while i <= len(st) - L:
                if all(isinstance(st[i + k], str) for k in range(L)) and \
                        "".join(st[i:i + L]) == c:
                    st[i:i + L] = [tok]
                i += 1
    return entries, streams


def encode(texts):
    entries, streams = build_dict(texts)
    ents = []
    for e in entries:
        b = [ord(ch) for ch in e]
        b[-1] |= 0x80
        ents.append(bytes(b))
    strs = [bytes((0x80 + it) if isinstance(it, int) else ord(it) for it in st) + b"\0"
            for st in streams]
    return ents, strs


def layout(ents, strs, base=0):
    """-> (image bytes, tx_tab offsets, entry offsets) for a block at `base`."""
    n_s, n_t = len(strs), len(ents)
    off = 2 * n_s + 2 * n_t
    e_off = []
    for e in ents:
        e_off.append(off)
        off += len(e)
    s_off = []
    for s in strs:
        s_off.append(off)
        off += len(s)
    img = bytearray()
    for o in s_off:
        img += (base + o).to_bytes(2, "little")
    for o in e_off:
        img += (base + o).to_bytes(2, "little")
    for e in ents:
        img += e
    for s in strs:
        img += s
    return bytes(img), s_off, e_off


def decode(img, n_strings, sid, base=0):
    """The Z80 getter's algorithm (tk_get) on the block image -> chars."""
    p = int.from_bytes(img[2 * sid:2 * sid + 2], "little") - base
    t0 = 2 * n_strings
    out = []
    for _ in range(4 * LOG_MAX):
        a = img[p]
        p += 1
        if a == 0:
            return out
        if a < 0x80:
            out.append(a)
            continue
        q = int.from_bytes(img[t0 + 2 * (a - 0x80):t0 + 2 * (a - 0x80) + 2], "little") - base
        while True:
            c = img[q]
            q += 1
            out.append(c & 0x7F)
            if c & 0x80:
                break
    fail(f"string {sid}: no terminator")


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
        ids.append(f"                ASSERT TXL_{nm.upper()} <= LOG_MAX")
    ids += [f"TX_COUNT         EQU {n_s}", f"TX_TOKENS        EQU {n_t}",
            f"TEXT_RAW         EQU {raw}          ; 0-terminated plain strings",
            f"TEXT_PACKED      EQU {len(img)}     ; the whole text block (tables included)",
            "                ASSERT TX_COUNT <= 128 && TX_TOKENS <= 128", ""]
    asm = [
        "; " + "=" * 76,
        "; strings.asm — GENERATED by tools/textpack.py from src/strings.txt (B3B-13).",
        "; DO NOT EDIT. Dictionary-token streams (format: the tool's docstring).",
        "; Words are text_base + offset; src/main.asm places the block (bank 1).",
        f"; {n_s} strings, {n_t} tokens: raw {raw} B -> {len(img)} B packed (tables included)",
        "; " + "=" * 76,
        "text_base:",
        "tx_tab:",
    ]
    for i, o in enumerate(s_off):
        asm.append(f"        DW text_base + {o}    ; {i} {names[i]}")
    asm.append("tx_dict:")
    for i, o in enumerate(e_off):
        asm.append(f"        DW text_base + {o}    ; ${0x80 + i:02X} {entries_txt(ents[i])!r}")
    asm.append("tx_entries:")
    for i, e in enumerate(ents):
        asm.append("        DB " + ",".join(f"${b:02X}" for b in e)
                   + f"    ; ${0x80 + i:02X} {entries_txt(e)!r}")
    asm.append("tx_strings:")
    for i, s in enumerate(strs):
        asm.append("        DB " + ",".join(f"${b:02X}" for b in s) + f"    ; {names[i]}: {texts[i]!r}")
    asm += ["text_end:", f"        ASSERT text_end - text_base == {len(img)}", ""]
    return "\n".join(ids), "\n".join(asm), img, raw


def entries_txt(e):
    return "".join(chr(b & 0x7F) for b in e)


def parse_emitted(path):
    """Rebuild the block image (base 0) from the emitted DB / DW lines."""
    img = bytearray()
    for line in open(path):
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
    return bytes(img)


def write_if_changed(path, text):
    old = open(path).read() if os.path.exists(path) else None
    if old != text:
        with open(path, "w") as f:
            f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    pairs = read_strings()
    names = [n for n, _ in pairs]
    texts = [t for _, t in pairs]
    ents, strs = encode(texts)
    ids, asm, img, raw = emit(names, texts, ents, strs)
    os.makedirs(OUT_DIR, exist_ok=True)
    write_if_changed(OUT_IDS, ids)
    write_if_changed(OUT_ASM, asm)
    # round trip on the EMITTED file
    back = parse_emitted(OUT_ASM)
    if back != img:
        fail("emitted strings.asm does not re-parse to the packed image")
    for i, t in enumerate(texts):
        got = decode(back, len(texts), i)
        if any(not 32 <= c <= 127 for c in got):
            fail(f"{names[i]}: decodes to a char outside 32..127: {got}")
        if bytes(got) != t.encode():
            fail(f"{names[i]}: round trip mismatch: {bytes(got)!r} != {t!r}")
        if len(got) > LOG_MAX:
            fail(f"{names[i]}: {len(got)} chars > LOG_MAX")
    print(f"textpack: {len(texts)} strings, {len(ents)} tokens, raw {raw} -> packed "
          f"{len(img)} B (streams {sum(map(len, strs))} + dict {sum(map(len, ents))} + "
          f"tables {2 * (len(strs) + len(ents))}); round-trip ok; -> build/text/")
    if a.report:
        for i, e in enumerate(ents):
            print(f"  ${0x80 + i:02X} {entries_txt(e)!r}")


if __name__ == "__main__":
    main()
