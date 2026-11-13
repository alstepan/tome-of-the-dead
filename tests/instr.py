#!/usr/bin/env python3
"""INSTR-BUILD boot overlay after ITEM-INFO (docs/design/item_info.md §5: HOW TO PLAY dropped).
instr_ovl.asm keeps in_ft (frame_tab -> FRT), the loading picture's key wait (GS_ANYKEY; tests/anykey.py
covers the wait itself) and in_tut (the D0 blob, the low-RAM stubs, the es_go patch).
  I6  static: the BOOT4 block in pool bank 4 = frame_tab stream (at BOOT4_ORG) + the overlay code + the blob
      stream + trailer, ending <= BLOB_ORG; no HOW TO PLAY page stream / state / INSTR_DATA symbol is left
  I7  boot -> GS_ANYKEY -> one key -> GS_SELECT, never a page state (9..11)
  I8  in_tut ran: es_go+1 == ts_choice, the stubs at check_paging == build/ovl/stub.bin, the raw blob at
      BLOB_ORG == build/ovl/blob.bin and its tail to $FFFF zeroed
   ZRCP_PORT=<port> python3 tests/instr.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game_lib import Harness, Proto, S, EMU_ARGS, GS_SELECT, GS_ANYKEY, BUILD_DIR  # noqa: E402


def main():
    with Harness() as h:
        gone = [n for n in ("instr_p1_zx0", "instr_p2_zx0", "INSTR_DATA", "GS_HELP1", "GS_HELP2", "GS_HELP3",
                            "in_page", "instr_main.in_page") if n in S]
        h.expect("I6 BOOT4 (pool bank 4) = frame_tab, the boot overlay code, the blob stream; ends <= BLOB_ORG",
                 S["BANK_INSTR"] == S["BANK_POOL1"] and S["ftz_zx0"] == S["BOOT4_ORG"]
                 and S["ftz_zx0_end"] == S["instr_zx0"] and S["instr_zx0_end"] == S["blob_zx0"]
                 and S["boot4_end"] <= S["BLOB_ORG"], True)
        h.expect("I6b no HOW TO PLAY symbol left (%s)" % gone, len(gone), 0)
        h.launch(EMU_ARGS)
        p = Proto(h)
        p.load()
        p.wb("INPUT_SRC", 1)
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_ANYKEY, 600)
        h.expect("I7 boot -> the picture's key wait", ok, True)
        p.wb("INPUT_SRC", 1)
        p.release()
        p.tick(2)
        seen = set()
        p.hold("ENTER")
        ok = p.until(lambda: (seen.add(p.rb("GAME_STATE")), p.rb("GAME_STATE") == GS_SELECT)[1], 60)
        p.release()
        h.expect("I7b one key -> menu, no page state (%s)" % sorted(seen), ok and not seen & {9, 10, 11}, True)
        es = p.rb(S["es_go"] + 1) | p.rb(S["es_go"] + 2) << 8
        h.expect("I8 es_go+1 == ts_choice", es, S["ts_choice"])
        stub = open(os.path.join(BUILD_DIR, "ovl", "stub.bin"), "rb").read()
        h.expect("I8b stubs at check_paging == stub.bin", bytes(p.z.read_memory(S["check_paging"], len(stub))) == stub, True)
        blob = open(os.path.join(BUILD_DIR, "ovl", "blob.bin"), "rb").read()
        p.z.cmd("set-memory-zone 0")              # the 128K RAM, bank n at n * 16K
        try:
            got = bytes(p.z.read_memory(4 * 16384 + S["BLOB_ORG"] - 0xC000, 0x10000 - S["BLOB_ORG"]))
        finally:
            p.z.cmd("set-memory-zone -1")
        h.expect("I8c raw blob at BLOB_ORG == blob.bin, tail zeroed",
                 got[:len(blob)] == blob and not any(got[len(blob):]), True)
    print("instr:", "OK" if h.ok else "FAIL %s" % h.failures)
    return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
