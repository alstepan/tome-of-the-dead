#!/usr/bin/env python3
"""TUT0 text check (no emulator). Runs tools/tutpack.py, then re-reads the EMITTED
build/tut/tut_text.asm and decodes every id with the engine's getter algorithm:
  tut_tab[id] -> 0-terminated stream; 0 end, 1..5 control token (key name, shown
  as width placeholders), 32..127 literal, >=128 resident dictionary token
  (tx_entries / tx_dict read from build/text/strings.asm).
Checks: every id decodes to its source text; TL_/TS_ EQUs match the table; tokens
reference real resident entries; every line <= 32 chars under BOTH width rules
(KEYS: token 5, SPACE spelled out (TUT0-F4 R4-2); STICK: token 5); K2 lint: no log line
begins with a key token.
Run: python3 tests/tut_text.py   (exit 0 = pass)"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import textpack as tp  # noqa: E402

SRC = os.path.join(REPO, "src/tut/tut_strings.txt")
OUT = os.path.join(REPO, "build/tut/tut_text.asm")
RES_ASM = os.path.join(REPO, "build/text/strings.asm")
RES_IDS = os.path.join(REPO, "build/text/strings_ids.inc")
TOK = re.compile(r"\{([UDLRF])\}")
CTRL = {"U": 1, "D": 2, "L": 3, "R": 4, "F": 5}
RULES = {"KEYS": 5, "STICK": 5}
LINE_MAX = 32

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def source_lines():
    out = []
    for line in open(SRC, encoding="utf-8"):
        s = line.rstrip("\n")
        if s.strip() and not s.lstrip().startswith("#"):
            key, text = s.split(" = ", 1)
            out.append((key.strip(), text))
    return out


def emitted_block_and_ids():
    """-> (block bytes with base 0, {name: id}) from the emitted file."""
    ids, block, started = {}, bytearray(), False
    for line in open(OUT, encoding="utf-8"):
        code = line.split(";")[0].strip()
        m = re.fullmatch(r"(TL_\S+|TS_\S+)\s+EQU\s+(\d+)", code)
        if m:
            ids[m.group(1)] = int(m.group(2))
            continue
        if code == "tut_tab:":
            started = True
        elif not started or not code or code.endswith(":") or code.startswith("ASSERT"):
            continue
        elif code.startswith("DW "):
            m = re.fullmatch(r"DW tut_text \+ (\d+)", code)
            block += int(m.group(1)).to_bytes(2, "little")
        elif code.startswith("DB "):
            block += bytes(int(t.strip()[1:], 16) for t in code[3:].split(","))
    return bytes(block), ids


def getter(block, off, res, key_w):
    """tk_get + control-token test, as the blob will run it."""
    ents_img, dict_off = res
    out, p = [], off
    while True:
        a = block[p]
        p += 1
        if a == 0:
            return "".join(out)
        if 1 <= a <= 5:
            out.append("#" * key_w)
        elif a < 0x80:
            out.append(chr(a))
        else:
            q = ents_img[dict_off + a - 0x80]
            while True:
                c = ents_img[q]
                q += 1
                out.append(chr(c & 0x7F))
                if c & 0x80:
                    break


def main():
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools/tutpack.py")],
                       capture_output=True, text=True)
    check(r.returncode == 0, "tutpack.py failed: " + (r.stdout + r.stderr).strip()[-300:])
    if r.returncode != 0:
        print("\n".join(failures))
        print("tut_text: FAIL")
        return 1
    src = source_lines()
    block, ids = emitted_block_and_ids()
    check(len(ids) == len(src), f"{len(ids)} EQUs vs {len(src)} source ids")

    img = tp.parse_emitted(RES_ASM)
    n_tok = int(re.search(r"TX_TOKENS\s+EQU (\d+)", open(RES_IDS).read()).group(1))
    res = (img, img.dict_off)

    worst = {k: (0, "") for k in RULES}
    for i, (key, text) in enumerate(src):
        check(ids.get(key) == i, f"{key}: EQU {ids.get(key)} != file order {i}")
        off = int.from_bytes(block[2 * i:2 * i + 2], "little")
        check(2 * len(src) <= off < len(block), f"{key}: offset {off} out of range")
        for rule, w in RULES.items():
            got = getter(block, off, res, w)
            want = TOK.sub("#" * w, text)
            check(got == want, f"{key} [{rule}]: decoded {got!r} != {want!r}")
            width = len(got)
            if width > worst[rule][0]:
                worst[rule] = (width, key)
            if width > LINE_MAX:
                check(False, f"{key} [{rule}]: {width} > {LINE_MAX}")
        # every resident token used must exist
        p = off
        while block[p]:
            a = block[p]
            check(a < 0x80 or a - 0x80 < n_tok, f"{key}: token {a:#x} >= {n_tok}")
            p += 1

    # TUT0-R2 (tutorial_d0.md s13.1, s10 C16): the mentor is Brother Morrow; the old name is gone
    texts = dict(src)
    check(texts.get("TL_L05") == "I AM BROTHER MORROW, LONG DEAD", f"TL_L05 = {texts.get('TL_L05')!r}")
    check(texts.get("TS_CHOICE3") == "BROTHER MORROW WILL TEACH YOU", f"TS_CHOICE3 = {texts.get('TS_CHOICE3')!r}")
    for key, text in src:
        check("ALDOUS" not in text and "SEXTON" not in text, f"{key}: the old mentor name in {text!r}")
    check("TL_L30" not in texts, "TL_L30 still present (R2: removed)")
    # TUT0-F4 K2 (tut0_split.md "Playtest round 2"): no log line starts with a key token; the R4-5 wordings
    for key, text in src:
        check(not (key.startswith("TL_") and TOK.match(text)), f"{key}: begins with a key token: {text!r}")
    check(texts.get("TL_L09") == "LEAP: PRESS {U}+{R} AT ONCE", f"TL_L09 = {texts.get('TL_L09')!r}")
    check(texts.get("TL_L23") == "AT THE SHAFT (LEFT) PRESS {D}", f"TL_L23 = {texts.get('TL_L23')!r}")

    print(f"tut_text: {len(src)} ids; worst KEYS {worst['KEYS'][0]} ({worst['KEYS'][1]}), "
          f"worst STICK {worst['STICK'][0]} ({worst['STICK'][1]}); limit {LINE_MAX}")
    for f in failures[:20]:
        print("  " + f)
    print("tut_text: " + ("PASS" if not failures else f"FAIL ({len(failures)})"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
