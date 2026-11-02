#!/usr/bin/env python3
"""Tape layout gate (LOAD-WIRE): build/wazhack.tap parses as
  BASIC header + program (autostart 10, loader lines 10/15/20/30),
  SCREEN$ header (CODE @ $4000, 6912 B) + data == assets/gfx/loading/loading_l3d.scr,
  CODE header (lowram_code) + data, then only headerless (flag $FF) blocks.
Every block's XOR parity is checked. No emulator needed.
Usage: tests/tape_layout.py [TAP]   (default build/wazhack.tap)"""
import os
import re
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.environ.get("WZ_BUILD_DIR", os.path.join(REPO, "build"))   # a variant build (game_lib's WZ_BUILD_DIR)
tap_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BUILD, "wazhack.tap")
sym = {}
for line in open(os.path.join(BUILD, "wazhack.sym")):
    m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
    if m:
        sym[m.group(1)] = int(m.group(2), 16)

d = open(tap_path, "rb").read()
blocks, i = [], 0
while i < len(d):
    n = struct.unpack_from("<H", d, i)[0]
    b = d[i + 2:i + 2 + n]
    assert len(b) == n, "truncated block"
    x = 0
    for c in b:
        x ^= c
    assert x == 0, "bad parity in block %d" % len(blocks)
    blocks.append(b)
    i += 2 + n

fails = 0


def expect(name, ok):
    global fails
    print(("PASS " if ok else "FAIL ") + name)
    fails += 0 if ok else 1


def hdr(b):
    return b[0] == 0 and len(b) == 19, (b[1], b[2:12].decode("latin1").strip(),
                                          *struct.unpack_from("<HHH", b, 12))


ok, (typ, nm, ln, p1, p2) = hdr(blocks[0])
expect("block 0 = BASIC program header, autostart 10", ok and typ == 0 and p1 == 10)
prog = blocks[1]
expect("block 1 = BASIC data (flag $FF, length matches)", prog[0] == 0xFF and len(prog) - 2 == ln)
lines = {}
j = 1
while j < len(prog) - 1:
    num = prog[j] * 256 + prog[j + 1]
    ll = struct.unpack_from("<H", prog, j + 2)[0]
    lines[num] = prog[j + 4:j + 4 + ll]
    j += 4 + ll
expect("loader lines 10,15,20,30", sorted(lines) == [10, 15, 20, 30])
expect("line 15 = LOAD \"\" SCREEN$", lines.get(15) == bytes([0xEF, 0x22, 0x22, 0xAA, 0x0D]))
expect("line 20 = LOAD \"\" CODE", lines.get(20) == bytes([0xEF, 0x22, 0x22, 0xAF, 0x0D]))
expect("line 10 starts CLEAR VAL \"24575\" (before the picture)", lines[10].startswith(b'\xfd\xb0"24575"'))

ok, (typ, nm, ln, p1, p2) = hdr(blocks[2])
expect("block 2 = CODE header $4000, 6912 B", ok and typ == 3 and p1 == 0x4000 and ln == 6912)
scr = open(os.path.join(REPO, "assets/gfx/loading/loading_l3d.scr"), "rb").read()
expect("block 3 data == loading_l3d.scr (6912 B)", blocks[3][0] == 0xFF and blocks[3][1:-1] == scr and len(scr) == 6912)
ok, (typ, nm, ln, p1, p2) = hdr(blocks[4])
expect("block 4 = game CODE header @ lowram_code", ok and typ == 3 and p1 == sym["lowram_code"] and ln == sym["TAPE_CODE_LEN"])
expect("block 5 = game CODE data", blocks[5][0] == 0xFF and len(blocks[5]) - 2 == ln)
rest = blocks[6:]
expect("%d headerless blocks follow (TAPE_HEADLESS_N)" % len(rest),
       len(rest) == sym["TAPE_HEADLESS_N"] and all(b[0] == 0xFF for b in rest))
# INSTR-BUILD: the bank-0 block (6th headerless, TAPE_BLOCKS order) = the text block + the
# HOW TO PLAY streams (page 1 at POOL_START, pages 2 and 3, the overlay code), boot only
txt = rest[5] if len(rest) > 5 else b""
expect("headerless 6 = text + INSTR streams (%d B = %d + %d)" % (
       len(txt) - 2, sym["TEXT_LEN"], sym["TEXT_TAPE_LEN"] - sym["TEXT_LEN"]),
       len(txt) - 2 == sym["TEXT_TAPE_LEN"] and sym["instr_p1_zx0"] == sym["POOL_START"]
       and sym["TEXT_ADDR"] + sym["TEXT_TAPE_LEN"] == sym["instr_zx0_end"]
       and sym["instr_p1_zx0"] < sym["instr_p2_zx0"] < sym["instr_p3_zx0"] < sym["instr_zx0"] < sym["instr_zx0_end"])
print("tape_layout: %s (%d blocks, %d B)" % ("OK" if not fails else "%d FAILED" % fails, len(blocks), len(d)))
sys.exit(1 if fails else 0)
