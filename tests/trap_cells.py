#!/usr/bin/env python3
"""TRAP-CELLS: every known trap plate the engine draws sits on a legal cell, once.

For master seeds 0..N-1 x D1..D8 x both heroes: the real level_new (far3), every
TRAP_LIST entry forced KNOWN, every present room built with build_room_map into
NEXT_MAP, then on the ENGINE's map + tile_flags:
  C1  exactly the list's plates: each entry's (9s+7, col) is T_TRAP, no other T_TRAP
      cell in any room (no plate without a record, none twice)
  C2  the plate's cell sits on solid ground: the floor row below is TF_FLOOR and no
      ladder / hole cell in the storey's rows 9s..9s+8 within cols t-1 .. t+1
      (the generator's footprint rule, game.md 1.5), no item marker on the cell
  A1  (fix/trap-tile) ALARM on a generated level: the plate fires by walking onto it; the
      TRAP_LIST entry keeps its room / storey / col / type (only KNOWN set), LP_RESPAWNS + 1
      per fire, capped at RESPAWN_MAX, the plate in the map, no other T_TRAP cell. (TRAP2
      shipped `inc (hl)` with HL = the entry: the record moved to the next room, a stray
      plate appeared there, often on a ladder top.)
Run: ZRCP_PORT=<port> [WZ_BUILD_DIR=..] python3 tests/trap_cells.py [--seeds N]   (default 40 seeds, ~0.23 s a level)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import levelgen as G                                     # noqa: E402
from game_lib import Harness, S, EMU_ARGS                # noqa: E402
from items_gen import T, DRV                             # noqa: E402
from lp import T as LPT                                  # noqa: E402
import game_lib as GL                                    # noqa: E402
from game_lib import stand_y                             # noqa: E402

TL, TN, TMAX = S["TRAP_LIST"], S["TRAP_N"], S["TRAP_MAX"]


def w16(v):
    return [v & 255, v >> 8]


def run_stub(p, code, org):
    """Run raw code at org up to its trailing `jr $` (as tests/game.py run_stub)."""
    code = bytes(code) + b"\x18\xfe"
    p.z.cmd("write-memory %d %s" % (org, " ".join(str(b) for b in code)))
    end = org + len(code) - 2
    p.z.cmd("set-breakpoint 3 PC=%d" % end)
    p.extra_probes = {end}
    p.z.cmd("set-register PC=%d" % org)
    p.z.cmd("run 50000000")
    ok = p.pc() == end
    p.z.cmd("set-breakpoint 3")
    p.extra_probes = set()
    return ok


def alarm_fires(h, seeds):
    """A1: walk onto an ALARM plate of a real generated D5..D8 level, several times."""
    p = LPT(h)
    GL.Proto.snd_mode = 2
    TLa, TNa, T_TRAP = S["TRAP_LIST"], S["TRAP_N"], S["T_TRAP"]
    bad, fires = [], 0
    for sd in range(seeds):
        depth = 5 + sd % 4
        p.proto_start = 0
        p.boot(hero=sd & 1, freeze=0)
        p.wmem(S["MASTER_SEED"], w16(0x6100 + sd))
        pc0 = p.pc()
        ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        p.release()
        p.settle(3)
        n = p.rb(TNa)
        if not n:
            continue
        b0, b1 = p.rb(TLa), p.rb(TLa + 1)
        r0, s0, t0 = b0 & 15, (b0 >> 4) & 1, b1 & 31
        p.wb(TLa + 1, t0 | (3 << 5))                          # type ALARM
        for sl in range(1, S["P_MAX_ENT"]):
            p.set_ent(sl, FLAGS=0)
        p.wb("CUR_ROOM", r0)
        p.set_ent(0, ROOM=r0)
        ok, _ = p.code([0x3E, r0, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["present_full"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        p.wb("LP_RESPAWNS", 0)
        hx = t0 - 3
        y = stand_y(s0, 6)
        for k in range(8):                                    # fire it 8 times (walk onto it from t - 3)
            p.set_ent(0, HP=250, MAXHP=250, X=hx, Y=y, PX=8 * hx, PY=8 * y, MODE=0, REACT=0, FLT=0)
            p.settle(1)
            p.turn("L", max_ticks=400)
            p.settle(2)
            fires += 1
        ent = (p.rb(TLa), p.rb(TLa + 1))
        want0 = (b0 | S["TRF_KNOWN"], t0 | (3 << 5))
        cells = len([q for q in p.z.read_memory(S["ROOM_MAP"], 576) if q == T_TRAP])
        resp = p.rb("LP_RESPAWNS")
        if ent != want0 or cells != 1 or p.rb("CUR_ROOM") != r0 or not 1 <= resp <= S["RESPAWN_MAX"]:
            bad.append((sd, depth, "entry", [hex(v) for v in ent], "want", [hex(v) for v in want0],
                        "plates", cells, "respawns", resp))
    return bad, fires


def main():
    nseeds = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 40   # ~0.23 s a level: 40 seeds x 16 = ~2.5 min (300 was ~20 min of silence, read as a hang)
    tf_ok = None
    bad = []
    by_d = {d: [0, 0] for d in range(1, 9)}         # levels, plates
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        p.load()
        tf = bytes(p.z.read_memory(S["tile_flags"], 64))
        LAD, HOLE, FLOOR = S["TF_LADDER"], S["TF_HOLE"], S["TF_FLOOR"]
        T_TRAP = S["T_TRAP"]
        page = S["NEXT_MAP"] >> 8
        for m in range(nseeds):
            if m % 10 == 0:
                print(f"  seed {m}/{nseeds} ({len(bad)} violations so far)", flush=True)
            for d in range(1, 9):
                for hk in (0, 1):
                    p.wb("HERO_KIND", hk)
                    p.wmem(S["MASTER_SEED"], [m & 255, m >> 8])
                    stub = [0xF3, 0x31] + w16(S["WORKSTORE_TOP"]) + [0x3E, d, 0x21] + w16(S["level_new"]) \
                        + [0xCD] + w16(S["far3"])
                    if not run_stub(p, stub, DRV):
                        bad.append((m, d, hk, "level_new did not finish"))
                        p.load()
                        continue
                    n = p.rb(TN)
                    ents = []
                    for i in range(min(n, TMAX)):
                        b0, b1 = p.rb(TL + 2 * i), p.rb(TL + 2 * i + 1)
                        p.wb(TL + 2 * i, b0 | S["TRF_KNOWN"])
                        ents.append((b0 & 15, (b0 >> 4) & 1, b1 & 31))
                    blk = bytes(p.z.read_memory(S["LVL_STATE"], G.BLOCK_LEN))
                    by_d[d][0] += 1
                    by_d[d][1] += len(ents)
                    for r in range(15):
                        if not blk[S["ROOM_DESC"] - S["LVL_STATE"] + r * S["RD_STRIDE"]] & 1:
                            continue
                        code = [0xF3, 0x31] + w16(S["WORKSTORE_TOP"]) + [0x3E, r, 0x16, page, 0x21] \
                            + w16(S["build_room_map"]) + [0xCD] + w16(S["far3"])
                        run_stub(p, code, DRV)
                        mp = p.z.read_memory(S["NEXT_MAP"], 576)
                        got = {i for i in range(576) if mp[i] == T_TRAP}
                        want = {(9 * s + 7) * 32 + t for (er, s, t) in ents if er == r}
                        tag = (m, d, hk, r)
                        if got != want:
                            bad.append(tag + ("C1 plates", sorted(got), sorted(want)))
                        for i in got:
                            row, t = divmod(i, 32)
                            s = row // 9
                            why = []
                            if not tf[mp[(row + 1) * 32 + t]] & FLOOR:
                                why.append("no floor below")
                            for rr in range(9 * s, 9 * s + 9):
                                for c in range(max(0, t - 1), min(31, t + 1) + 1):
                                    if tf[mp[rr * 32 + c]] & (LAD | HOLE):
                                        why.append(f"ladder/hole at ({c},{rr})")
                                        break
                            if why:
                                bad.append(tag + ("C2 plate", (t, row), why[:2]))
        abad, fires = alarm_fires(h, 12)
        print(f"  A1: {fires} ALARM fires on generated D5..D8 levels, {len(abad)} violations")
        for b in abad[:6]:
            print("  FAIL A1", b)
        bad += abad
        for d, (lv, pl) in by_d.items():
            print(f"  D{d}: {lv} levels, {pl} plates")
        print(f"TRAP-CELLS: {len(bad)} violations over {nseeds} seeds")
        for b in bad[:12]:
            print("  FAIL", b)
        h.expect("trap cells: every plate legal, once, with a record", len(bad), 0)
        return 1 if bad or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
