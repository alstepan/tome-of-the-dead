#!/usr/bin/env python3
"""3E-T3 item contracts (src/item_defs.asm; docs/memory-map.md "3E contracts (3E-T3)").
Release build (DEBUG_KIT=0) for the emulator part; the layout part runs on any build.

  L1  type enum: legacy ids 1..3 kept, class ranges contiguous in the documented
      order (counters, food, potions, scrolls, book, bow, gear W/A/H/C), IT_COUNT
  L2  record / ISTATE bits (reserved, enchant, m) partition the byte; IST_M_* values
  L3  ITEM_RAM fields consecutive in the documented order and sizes, one page, outside
      LOG_TXT / PF_RAM / MK_RAM / the page band / GEN_SCRATCH / the tape image;
      TRAP_LIST / TRAP_N inside the ROOM_DESC spare below FLOOR_LIST; QPIN out of HERO_ST
  R1  canary $A5 over ITEM_RAM + the rest of $5CC0..$5DFF + $5F8C..$5FFF at the menu;
      START: new_game zeroes exactly ITEM_RAM, every other canary byte survives
  R2  20 turns of play + a descent (level_descend, music off): ITEM_RAM (a written
      pattern) is kept byte-exact (3E rev 6: no per-level field in it); the 3E-T6
      generator's trap list holds TRAP_N <= TRAP_MAX entries, unused bytes 0; the canaries survive
Run: ZRCP_PORT=<port> python3 tests/items3e.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, RUN_LIMIT, GS_SELECT  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
CANARY = 0xA5
LOW_RES = [(0x5CC0, 0x5E00), (S["MK_RAM_END"], 0x6000)]   # runtime-only reserve (memory-map)


def layout(check):
    s = S
    # ---- L1 ------------------------------------------------------------------
    check("L1 legacy ids", (s["IT_NONE"], s["IT_POTION"], s["IT_DAGGER"], s["IT_ARROW"]) == (0, 1, 2, 3))
    order = [("IT_CNT", 2, 4), ("IT_FOOD", 5, 9), ("IT_POT", 10, 12), ("IT_SCR", 13, 16)]
    check("L1 class ranges", all((s[n + "_LO"], s[n + "_HI"]) == (lo, hi) for n, lo, hi in order),
          [(n, s[n + "_LO"], s[n + "_HI"]) for n, _, _ in order])
    check("L1 book / bow", (s["IT_BOOK"], s["IT_BOW"]) == (17, 18))
    gear = ["IT_WPN", "IT_ARM", "IT_HELM", "IT_CHARM"]
    nxt, ok = s["IT_BOW"] + 1, True
    for g in gear:
        ok &= s[g + "_LO"] == nxt and s[g + "_HI"] >= s[g + "_LO"]
        nxt = s[g + "_HI"] + 1
    ok &= s["IT_GEAR_LO"] == s["IT_WPN_LO"] and s["IT_GEAR_HI"] == s["IT_CHARM_HI"] == nxt - 1
    ok &= s["IT_WPN_M_LO"] == s["IT_WPN_W_HI"] + 1 and s["IT_WPN_W_LO"] == s["IT_WPN_LO"]
    check("L1 gear ranges in W/A/H/C order, IT_COUNT", ok and s["IT_COUNT"] == nxt == 44)
    check("L1 slot ids", [s[k] for k in ("WS_WEAPON", "WS_ARMOUR", "WS_HELM", "WS_CHARM")] == [0, 1, 2, 3])
    # ---- L2 ------------------------------------------------------------------
    check("L2 record", (s["IR_TYPE"], s["IR_QTY"], s["IR_IST"], s["IR_STRIDE"], s["STACK_MAX"]) == (0, 1, 2, 3, 9))
    m = [s["IST_RSVD_MASK"], s["IST_ENCH_MASK"], s["IST_M_MASK"]]
    check("L2 ISTATE fields", m == [0x07, 0x18, 0xE0] and sum(m) == 0xFF)
    check("L2 m encodings", [s["IST_M_" + k] for k in ("P2", "P1", "M1", "M2", "M3")]
          == [((v & 7) << 5) for v in (2, 1, -1, -2, -3)])
    # ---- L3 ------------------------------------------------------------------
    fields = [("BAG", 60), ("WORN", 12), ("FOOD", 1),          # 3E rev 6: no FL_IST / ID_MAP / KNOWN
              ("FOOD_TMR", 1), ("HSTAGE", 1), ("QPIN", 3), ("QS_CACHE", 3)]
    a, ok = s["ITEM_RAM"], True
    for name, n in fields:
        ok &= s[name] == a
        a += n
    check("L3 ITEM_RAM fields", ok and a == s["ITEM_RAM_END"] and s["ITEM_RAM_LEN"] == 81,
          [(n, hex(s[n])) for n, _ in fields])
    lo, hi = s["ITEM_RAM"], s["ITEM_RAM_END"]
    check("L3 one page", lo & 0xFF == 0 and (hi - 1) >> 8 == lo >> 8)

    def clear(a0, a1):
        return hi <= a0 or lo >= a1
    busy = [("LOG_TXT", s["LOG_TXT"], s["LOG_TXT"] + 256), ("sysvars+CHANS", 0x5C00, 0x5CCB),
            ("PF_RAM", s["PF_RAM"], s["PF_RAM"] + s["PF_RAM_LEN"]), ("MK_RAM", s["MK_RAM"], s["MK_RAM_END"]),
            ("page band", s["PAGE_ORG"], s["PAGE_LIMIT"]),
            ("GEN_SCRATCH", s["GEN_SCRATCH"], s["GEN_SCRATCH"] + s["GEN_SCRATCH_LEN"]),
            ("lowram..", 0x6000, 0x10000)]
    check("L3 no overlap", all(clear(b, e) for _, b, e in busy),
          [n for n, b, e in busy if not clear(b, e)])
    check("L3 inside the runtime reserve", lo >= 0x5CC0 and hi <= s["PF_RAM"])
    tl, tn = s["TRAP_LIST"], s["TRAP_N"]
    check("L3 trap list", tl == s["ROOM_DESC"] + 9 * 16 and tn == tl + 12 and tn < s["FLOOR_LIST"]
          and s["TRAP_MAX"] == 6 and s["TRAP_STRIDE"] == 2)
    check("L3 QPIN left HERO_ST", not (s["HERO_ST"] <= s["QPIN"] < s["HERO_ST_END"]))


def emu(p, check):
    def mem(a, n):
        return bytes(p.z.read_memory(a, n))

    lo, n = S["ITEM_RAM"], S["ITEM_RAM_LEN"]
    p.proto_start = 0
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_REPEAT", 1)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    for a0, a1 in LOW_RES:
        p.wmem(a0, [CANARY] * (a1 - a0))

    def canaries():
        bad = []
        for a0, a1 in LOW_RES:
            b = mem(a0, a1 - a0)
            bad += [hex(a0 + i) for i, v in enumerate(b) if v != CANARY and not lo <= a0 + i < lo + n]
        return bad

    # ---- R1 ------------------------------------------------------------------
    p.menu_start(K_KNIGHT)
    # 3E-T11: new_game zeroes ITEM_RAM, then kit_add writes the Warrior start kit
    # (game.md §8.11 Q10: WORN Short Sword + Leather, BAG Heal x1 + Apple x1)
    want = bytearray(n)
    bag, worn = 0, S["WORN"] - lo
    want[bag:bag + 6] = bytes([S["IT_P_HEAL"], 1, 0, S["IT_F_APPLE"], 1, 0])
    want[worn:worn + 6] = bytes([S["IT_W_SHORT"], 1, 0, S["IT_A_LEATHER"], 1, 0])
    check("R1 new_game zeroes ITEM_RAM + the start kit (T11)", mem(lo, n) == bytes(want), mem(lo, n).hex())
    bad = canaries()
    check("R1 the rest of the reserve untouched", not bad, bad[:16])
    # ---- R2 ------------------------------------------------------------------
    pat = bytes((i * 7 + 1) & 0xFF for i in range(n))
    p.wmem(lo, list(pat))
    p.wb("SND_MODE", 0)
    t0 = p.rw("TURN_COUNTER")
    for _ in range(10):
        p.turn("WAIT")
    check("R2 turns played", (p.rw("TURN_COUNTER") - t0) & 0xFFFF >= 10)
    d0 = p.rb("LVL_DEPTH")
    wt = S["wait_tick"]
    while p.pc() != wt:
        p.tick()
    stub = S["LOWRAM_END_3B"]
    p.wmem(stub, [0xCD] + w16(S["level_descend"]) + [0xC3] + w16(wt))
    p.z.cmd("set-register PC=%d" % stub)
    for _ in range(50):
        p.z.cmd("cpu-step")
        p.z.cmd("run %d" % RUN_LIMIT)
        if p.pc() == wt:
            break
    check("R2 descended", p.rb("LVL_DEPTH") == d0 + 1, (d0, p.rb("LVL_DEPTH")))
    got = mem(lo, n)
    check("R2 ITEM_RAM kept across the level change", got == pat)
    tl = S["TRAP_LIST"]
    tr = mem(tl, 13)
    tn = tr[12]
    check("R2 trap list: TRAP_N <= TRAP_MAX, unused entries 0",
          1 <= tn <= S["TRAP_MAX"] and tr[2 * tn:12] == bytes(12 - 2 * tn), tr.hex())
    p.tick(10)
    for _ in range(10):
        p.turn("WAIT")
    check("R2 ITEM_RAM still kept after play", mem(lo, n) == got)
    bad = canaries()
    check("R2 the rest of the reserve untouched", not bad, bad[:16])


def main():
    fails = []
    n = [0]
    with Harness() as h:
        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        layout(check)
        if KIT:
            print("[skip] items3e emulator part needs a DEBUG_KIT=0 build", flush=True)
        else:
            h.launch(EMU_ARGS)
            emu(T(h), check)
        print(f"items3e: {len(fails)} failed of {n[0]}" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
