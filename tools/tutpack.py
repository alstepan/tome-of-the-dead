#!/usr/bin/env python3
"""Pack the TUT0 tutorial text (src/tut/tut_strings.txt) for the D0 blob (TUT0-T3).

Writes build/tut/tut_text.asm:
  TL_<id> / TS_<id> EQU n     numeric id = file order
  TUT_TEXT_COUNT / TUT_TEXT_RAW / TUT_TEXT_PACKED
  tut_text:                   block base; the blob INCLUDEs this file, so the DW
  tut_tab:                    words are the blob's own addresses. One DW per id:
                              tut_text + offset of that id's stream (no skip chain)
  tut_streams:                0-terminated streams, in id order

Streams use the RESIDENT dictionary: the one tools/textpack.py emits for the main
text (build/text/strings.asm, tx_entries / tx_dict). It is read back with
textpack.parse_emitted, not rebuilt, so token numbers cannot drift from the game's.
Stream bytes (textpack's format, docstring there, plus the control tokens):
  0          end of string
  1..5       control token U D L R F ({U} {D} {L} {R} {F} in the source). NOT a
             dictionary token: the blob expands it to a key name when the line is
             queued (KEYS: 2-char REDEFINE names; KEMPSTON/SINCLAIR: UP DOWN LEFT
             RIGHT FIRE). The blob's getter must test for 1..5 before tk_get
             (tk_get would print them as literals).
  32..127    literal char
  128..255   resident dictionary token t: entry t - 128

Width rules (a line must be <= 32 under BOTH):
  KEYS       token = 2 chars (REDEFINE names, menu1.asm key_names); chord {D}+{F} = 5
  STICK      token = 5 chars (UP DOWN LEFT RIGHT FIRE, RIGHT widest); chord = 11

Usage: tools/tutpack.py [--report]
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import textpack as tp  # noqa: E402  (reused: parse_emitted, dp_parse)

SRC = os.path.join(REPO, "src/tut/tut_strings.txt")
RES_ASM = os.path.join(REPO, "build/text/strings.asm")
RES_IDS = os.path.join(REPO, "build/text/strings_ids.inc")
OUT_DIR = os.path.join(REPO, "build/tut")
OUT = os.path.join(OUT_DIR, "tut_text.asm")

CTRL = {"U": 1, "D": 2, "L": 3, "R": 4, "F": 5}
TOK_RE = re.compile(r"\{([UDLRF])\}")
ID_RE = re.compile(r"^(TL_L\d\d[WMb]?|TL_I\d\d[abWM]?|TS_[A-Z0-9_]+)$")
W_KEYS = 2      # KEYS rule: token width (REDEFINE names)
W_STICK = 5     # STICK rule: token width (widest stick word)
LINE_MAX = 32


def fail(msg):
    sys.exit(f"tutpack: {msg}")


def read_source(path=SRC):
    """-> [(id, text)] in file order. Text keeps its {U}.. tokens."""
    out, seen = [], set()
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        s = line.rstrip("\n")
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        where = f"{path}:{n}"
        if " = " not in s:
            fail(f"{where}: expected `TL_<id> = TEXT`: {s!r}")
        key, text = (x for x in s.split(" = ", 1))
        key = key.strip()
        if not ID_RE.match(key):
            fail(f"{where}: bad id {key!r} (TL_L<nn>[W|M|b], TL_I<nn>[a|b|W|M] or TS_<NAME>)")
        if key in seen:
            fail(f"{where}: duplicate id {key}")
        seen.add(key)
        plain = TOK_RE.sub("", text)
        bad = [c for c in plain if not 32 <= ord(c) <= 126 or c in "\"{}"]
        if bad:
            fail(f"{where}: {key}: chars outside 32..126 / stray brace: {bad!r}")
        if any("a" <= c <= "z" for c in text):
            fail(f"{where}: {key}: upper case only")
        if text.endswith("."):
            fail(f"{where}: {key}: no trailing full stop")
        if "  " in text and key.startswith("TL_"):
            fail(f"{where}: {key}: double space in a log line")
        out.append((key, text))
    if not out:
        fail(f"{path}: no ids")
    return out


def widths(text):
    """-> (KEYS width, STICK width) of the displayed line."""
    n_tok = len(TOK_RE.findall(text))
    plain = len(TOK_RE.sub("", text))
    return plain + n_tok * W_KEYS, plain + n_tok * W_STICK


def resident():
    """-> (dictionary entries as str, resident image) read from the emitted main
    text. Fails if textpack has not run."""
    if not (os.path.exists(RES_ASM) and os.path.exists(RES_IDS)):
        fail("build/text/strings.asm missing: run tools/textpack.py first")
    img = tp.parse_emitted(RES_ASM)
    n = int(re.search(r"TX_TOKENS\s+EQU (\d+)", open(RES_IDS).read()).group(1))
    ents = []
    for t in range(n):
        o = img[img.dict_off + t]
        b = []
        while True:
            c = img[o]
            o += 1
            b.append(c & 0x7F)
            if c & 0x80:
                break
        ents.append("".join(chr(x) for x in b))
    return ents, img


def pack_one(text, ents):
    """-> 0-terminated stream. Min-length parse over the resident dictionary."""
    raw = TOK_RE.sub(lambda m: chr(CTRL[m.group(1)]), text)
    out = [(0x80 + it) if isinstance(it, int) else ord(it) for it in tp.dp_parse(raw, ents)]
    return bytes(out + [0])


def getter(block, off, res_img, key_w):
    """The blob's getter on the block (tk_get + control-token test), with each
    control token shown as key_w placeholder chars -> displayed text."""
    res, p = [], off
    while True:
        a = block[p]
        p += 1
        if a == 0:
            break
        if 1 <= a <= 5:
            res.append(chr(ord("a") + a) * key_w)
        elif a < 0x80:
            res.append(chr(a))
        else:
            q = res_img[res_img.dict_off + a - 0x80]
            while True:
                c = res_img[q]
                q += 1
                res.append(chr(c & 0x7F))
                if c & 0x80:
                    break
    return "".join(res)


def emit(pairs, streams, raw):
    n = len(pairs)
    offs, off = [], 2 * n
    for s in streams:
        offs.append(off)
        off += len(s)
    lines = [
        "; " + "=" * 76,
        "; tut_text.asm - GENERATED by tools/tutpack.py from src/tut/tut_strings.txt (TUT0-T3).",
        "; DO NOT EDIT. Streams use the RESIDENT dictionary (build/text/strings.asm).",
        "; Control tokens $01..$05 = U D L R F: the blob expands them (never literal).",
        "; " + "=" * 76,
        "",
    ]
    for i, (k, _) in enumerate(pairs):
        lines.append(f"{k:<16} EQU {i}")
    lines += [
        "",
        f"TUT_TEXT_COUNT   EQU {n}",
        f"TUT_TEXT_RAW     EQU {raw}          ; 0-terminated plain text",
        f"TUT_TEXT_PACKED  EQU {off}     ; tut_tab + streams",
        f"                ASSERT TUT_TEXT_COUNT <= 256",
        "",
        "tut_text:",
        "tut_tab:                       ; DW per id (TL_/TS_ EQU = index)",
    ]
    for i, ((k, t), o) in enumerate(zip(pairs, offs)):
        lines.append(f"        DW tut_text + {o}    ; {i} {k} {t!r}")
    lines.append("tut_streams:")
    for (k, _), s in zip(pairs, streams):
        hexs = ",".join(f"${b:02X}" for b in s)
        lines.append(f"        DB {hexs}    ; {k}")
    lines += ["tut_end:", f"        ASSERT tut_end - tut_text == {off}", ""]
    return "\n".join(lines), off


def read_block(path):
    """Rebuild the block (base 0) from the EMITTED tut_tab / tut_streams lines."""
    block, started = bytearray(), False
    for line in open(path, encoding="utf-8"):
        code = line.split(";")[0].strip()
        if code == "tut_tab:":
            started = True
        elif code in ("tut_end:", "") or code.endswith(":") or not started:
            continue
        elif code.startswith("ASSERT "):
            continue
        elif code.startswith("DW "):
            m = re.fullmatch(r"DW tut_text \+ (\d+)", code)
            if not m:
                fail(f"emitted DW not understood: {code!r}")
            block += int(m.group(1)).to_bytes(2, "little")
        elif code.startswith("DB "):
            block += bytes(int(t.strip()[1:], 16) for t in code[3:].split(","))
        else:
            fail(f"emitted line not understood: {code!r}")
    return bytes(block)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", default=OUT, help="output asm (default build/tut/tut_text.asm; "
                    "tools/build.sh -o DIR passes DIR/build/tut/tut_text.asm)")
    a = ap.parse_args()
    out = a.out

    pairs = read_source()
    ents, res_img = resident()
    streams = [pack_one(t, ents) for _, t in pairs]
    raw = sum(len(t) + 1 for _, t in pairs)
    text, total = emit(pairs, streams, raw)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    # self-check on the EMITTED file: every line decodes (getter, both width rules)
    block = read_block(out)
    if len(block) != total:
        fail(f"emitted block {len(block)} B != {total}")
    for i, (k, t) in enumerate(pairs):
        off = int.from_bytes(block[2 * i:2 * i + 2], "little")
        if block[off:off + len(streams[i])] != streams[i]:
            fail(f"{k}: emitted stream does not match the packed stream")
        for key_w in (W_KEYS, W_STICK):
            got = getter(block, off, res_img, key_w)
            want = TOK_RE.sub(lambda m: chr(ord("a") + CTRL[m.group(1)]) * key_w, t)
            if got != want:
                fail(f"{k}: round trip mismatch: {got!r} != {want!r}")

    wk = max(pairs, key=lambda p: widths(p[1])[0])
    ws = max(pairs, key=lambda p: widths(p[1])[1])
    over = [(k, widths(t)) for k, t in pairs if max(widths(t)) > LINE_MAX]
    print(f"tutpack: {len(pairs)} lines, raw {raw} B -> packed {total} B "
          f"(id table {2 * len(pairs)} B + streams {total - 2 * len(pairs)} B; resident dict "
          f"{len(ents)} tokens); round-trip ok; worst KEYS {widths(wk[1])[0]} ({wk[0]}), "
          f"worst STICK {widths(ws[1])[1]} ({ws[0]}); -> {out}")
    if a.report:
        for k, t in pairs:
            w = widths(t)
            print(f"  {k:<14} keys={w[0]:>2} stick={w[1]:>2}  {t}")
    for k, w in over:
        print(f"tutpack: OVER {LINE_MAX}: {k} keys={w[0]} stick={w[1]}")
    if over:
        fail(f"{len(over)} line(s) exceed {LINE_MAX} chars under a width rule")


if __name__ == "__main__":
    main()
