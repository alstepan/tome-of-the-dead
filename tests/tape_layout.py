#!/usr/bin/env python3
"""Tape layout gate (LOAD-WIRE): build/tome-of-the-dead.tap parses as
  BASIC header + program (autostart 10, loader lines 10/15/20/30),
  SCREEN$ header (CODE @ $4000, 6912 B) + data == assets/gfx/loading/loading_l3d.scr,
  CODE header (lowram_code) + data, then only headerless (flag $FF) blocks.
Every block's XOR parity is checked. No emulator needed.
Usage: tests/tape_layout.py [TAP]   (default build/tome-of-the-dead.tap)"""
import os
import re
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.environ.get("WZ_BUILD_DIR", os.path.join(REPO, "build"))   # a variant build (game_lib's WZ_BUILD_DIR)
tap_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BUILD, "tome-of-the-dead.tap")
sym = {}
for line in open(os.path.join(BUILD, "tome-of-the-dead.sym")):
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
# INSTR-BUILD / C-T8 / C+TUT0 / B0CODE: 6th headerless = the bank-0 text block + the b0 cold code + its
# reserve pad up to B0_FREE_START, then the used part of the carve, B0_CODE2 (b0c2_code = B0_FREE_START
# .. b0c2_end <= POOL_START); the rest of the carve and anything above POOL_START are NOT on tape.
# 7th = the bank-4 BOOT4 block: frame_tab (RECLAIM-D, first, at BOOT4_ORG), the boot overlay
# code (ITEM-INFO: no HOW TO PLAY page streams), then blob_zx0 + its 2-byte length trailer (in_tut reads it from
# the block's end via tape_tab TT_BOOT4_REC), ending <= BLOB_ORG (forward unpack, no overlap)
txt = rest[5] if len(rest) > 5 else b""
b4 = rest[6] if len(rest) > 6 else b""
expect("headerless 6 = text + b0 code + pad + B0_CODE2 (%d B = %d + %d + %d), ends at b0c2_end (<= POOL_START)" % (
       len(txt) - 2, sym["TEXT_LEN"], sym["B0_FREE_START"] - sym["TEXT_ADDR"] - sym["TEXT_LEN"], sym["B0C2_LEN"]),
       len(txt) - 2 == sym["TEXT_TAPE_LEN"]
       and sym["b0c2_code"] == sym["B0_CODE2"] == sym["B0_FREE_START"]
       and sym["TEXT_ADDR"] + sym["TEXT_TAPE_LEN"] == sym["b0c2_end"] == sym["text_tape_end"]
       and sym["b0c2_end"] - sym["b0c2_code"] == sym["B0C2_LEN"]
       and sym["b0c2_end"] + sym["B0C2_FREE"] == sym["POOL_START"]
       and sym["B0_FREE_START"] + sym["B0_FREE_RES"] == sym["POOL_START"])
# B0CODE: the B0_CODE2 bytes on tape are the assembled ones (.sna bank 0), i.e. the loader puts the
# region's code where FARB0 enters it
sna = os.path.join(BUILD, "tome-of-the-dead.sna")
expect("B0CODE: %s exists (needed for the B0_CODE2 tape == .sna check)" % os.path.basename(sna), os.path.exists(sna))
if os.path.exists(sna):
    s = open(sna, "rb").read()
    # 128K .sna: 27-B header + 48K (banks 5, 2, paged) + 4 B + the other banks in order 0,1,3,4,6,7
    # minus the paged one; bank 0 is first unless it was paged at save time (then it sits in the 48K part)
    paged = s[27 + 49152 + 2] & 7
    off = 27 + 32768 if paged == 0 else 27 + 49152 + 4
    o = sym["b0c2_code"] - sym["TEXT_ADDR"]
    expect("B0_CODE2 tape bytes == .sna bank 0 (%d B)" % sym["B0C2_LEN"],
           txt[1 + o:1 + o + sym["B0C2_LEN"]] == s[off + (sym["b0c2_code"] - 0xC000):off + (sym["b0c2_code"] - 0xC000) + sym["B0C2_LEN"]])
expect("headerless 7 = BOOT4: frame_tab + INSTR code + blob_zx0 + trailer at BOOT4_ORG (%d B)" % (len(b4) - 2),
       len(b4) - 2 == sym["BOOT4_TAPE_LEN"] and sym["ftz_zx0"] == sym["BOOT4_ORG"] == sym["INSTR_FT_ZX0"]
       and sym["ftz_zx0"] < sym["ftz_zx0_end"] == sym["instr_zx0"]
       and sym["instr_zx0"] < sym["instr_zx0_end"] == sym["blob_zx0"]
       and "instr_p1_zx0" not in sym and "instr_p2_zx0" not in sym
       and sym["BOOT4_ORG"] + sym["BOOT4_TAPE_LEN"] == sym["boot4_end"] <= sym["BLOB_ORG"]
       and sym["BANK_BOOT4"] == sym["BANK_BLOB"] == sym["BANK_INSTR"])
tl = len(b4) - 2
expect("BOOT4 block trailer (last 2 B) == BLOB_ZX0_LEN",
       tl >= 2 and b4[1 + tl - 2] | b4[1 + tl - 1] << 8 == sym["BLOB_ZX0_LEN"])
print("tape_layout: %s (%d blocks, %d B)" % ("OK" if not fails else "%d FAILED" % fails, len(blocks), len(d)))
sys.exit(1 if fails else 0)
