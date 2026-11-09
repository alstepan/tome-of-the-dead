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
      TRAP_LIST entry keeps its room / storey / col / type (only KNOWN + RUNG set), LP_RESPAWNS + 1
      per fire, capped at RESPAWN_MAX, the plate in the map, no other T_TRAP cell. (TRAP2
      shipped `inc (hl)` with HL = the entry: the record moved to the next room, a stray
      plate appeared there, often on a ladder top.)
  C3  (TRAP-OR) the first 10 seeds: a room built with its traps known == built with them hidden,
      except the plate cells (the decor never depends on a known trap); after each build with a
      plate, TILE_GLYPHS[T_TRAP] == glyph(the hidden build's cell) | the plate (lines 6 / 7) and
      TILE_ATTRS[T_TRAP] == the type ink, over decor too (user ruling 2026-11-05)
  L1..L3 (TRAP-OR, user playtest 2026-11-05: a revealed plate erased the decor of its cell) a
      real generated room, a hidden DART poked under a floor object's bottom row (row 9s+7):
      the Mage's sense finds it on a Wait (the blink sequence) -> the cell on the composed
      (bank 5) AND the displayed (screen 2) screen == decor glyph | plate, the DART ink $42;
      L2 the same after walking out through the storey's side exit and back in (NEXT_MAP
      build + the scroll strips); L3 the same after a room_show rebuild (teleport / level entry)
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
        if b0 & S["TRF_RUNG"]:                                  # ALARM-1 guard: never set on an unfired plate
            bad.append((sd, depth, "TRF_RUNG set before any step", hex(b0)))
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
        want0 = (b0 | S["TRF_KNOWN"] | S["TRF_RUNG"], t0 | (3 << 5))
        cells = len([q for q in p.z.read_memory(S["ROOM_MAP"], 576) if q == T_TRAP])
        resp = p.rb("LP_RESPAWNS")
        if ent != want0 or cells != 1 or p.rb("CUR_ROOM") != r0 or not 1 <= resp <= S["RESPAWN_MAX"]:
            bad.append((sd, depth, "entry", [hex(v) for v in ent], "want", [hex(v) for v in want0],
                        "plates", cells, "respawns", resp))
    return bad, fires


def plate_glyph():
    """The plate's 8 lines from the generated tiles_common.asm (independent of the engine)."""
    for ln in (HERE.parent / "assets/gfx/tiles/tiles_common.asm").read_text().splitlines():
        if ln.rstrip().endswith("T_TRAP") and "DEFB" in ln:
            return [int(v.strip().lstrip("$"), 16) for v in ln.split("DEFB")[1].split(";")[0].split(",")]
    raise SystemExit("no T_TRAP glyph line in tiles_common.asm")


PLATE = plate_glyph()


def composed(gly_u, plate=PLATE):
    return [a | b for a, b in zip(gly_u, plate)]


def cell_bytes(fr, col, row):
    """8 bitmap lines + attr of a cell in a 6912-B Spectrum frame."""
    base = ((row & 0x18) << 8) | ((row & 7) << 5) | col
    return [fr[base + (k << 8)] for k in range(8)], fr[6144 + row * 32 + col]


def live_or(h, seeds):
    """L1..L3: a real reveal / scroll / rebuild over a decor cell on a generated level."""
    p = LPT(h)
    GL.Proto.snd_mode = 2
    T_TRAP, TG, TA = S["T_TRAP"], S["TILE_GLYPHS"], S["TILE_ATTRS"]
    NM = S["NEXT_MAP"]
    bad, done = [], None
    for sd in range(seeds):
        depth = 1 + sd % 8
        p.proto_start = 0
        p.boot(hero=1, freeze=0)                               # the Mage: the sense finds it
        p.wmem(S["MASTER_SEED"], w16(0x7300 + sd))
        pc0 = p.pc()
        if depth > 1:
            p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
        p.release()
        p.settle(3)
        p.wmem(TL, [0] * (2 * TMAX))                           # no generated trap: ours only
        p.wb(TN, 0)
        cur = p.rb("CUR_ROOM")
        cand = None
        for r in range(15):
            if r == cur or not p.rb(S["ROOM_DESC"] + r * S["RD_STRIDE"]) & 1:
                continue
            ex = p.rb(S["ROOM_DESC"] + r * S["RD_STRIDE"] + 1)
            p.code([0x3E, r, 0x16, NM >> 8, 0x21] + w16(S["build_room_map"]) + [0xCD] + w16(S["far3"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            mp = p.z.read_memory(NM, 576)
            for s_ in (0, 1):
                row = 9 * s_ + 7
                for side, bit, x_edge in (("L", 2 << 4 * s_, 28), ("H", 1 << 4 * s_, 1)):
                    if not ex & bit:
                        continue
                    for t in range(6, 26):
                        u = mp[row * 32 + t]
                        x = t + 2 if side == "L" else t - 4    # the sense range, on the exit side
                        if S["T_LVL_BASE"] <= u < S["T_ITEM0"] and 1 <= x <= 28 and \
                                all(mp[row * 32 + c] == 0 for c in range(x, x + 3)):
                            cand = (r, s_, t, side, x, x_edge, u)
                            break
                    if cand:
                        break
                if cand:
                    break
            if cand:
                break
        if not cand:
            continue
        r, s_, t, side, x, x_edge, u = cand
        row = 9 * s_ + 7
        back = "H" if side == "L" else "L"
        p.wmem(TL, [r | (s_ << 4), t])                         # a hidden DART (type 0) at t
        p.wb(TN, 1)
        for sl in range(1, S["P_MAX_ENT"]):
            p.set_ent(sl, FLAGS=0)
        p.wb("CUR_ROOM", r)
        p.set_ent(0, ROOM=r)
        p.code([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["present_full"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        hgt = p.rb(S["kind_tab"] + S["KT_BH"] + p.ent(0)["KIND"])
        y = stand_y(s_, hgt)
        gly_u = list(p.z.read_memory(TG + 8 * u, 8))
        want = (composed(gly_u), S["TRAP_INK_DART"])             # its own type colour over the decor (user 2026-11-05)

        def place(xx, left):
            fl = p.ent(0)["FLAGS"]
            fl = (fl | S["EF_LEFT"]) if left else (fl & ~S["EF_LEFT"] & 255)
            p.set_ent(0, HP=250, MAXHP=250, X=xx, Y=y, PX=8 * xx, PY=8 * y, MODE=0, REACT=0, FLT=0, FLAGS=fl)
            p.settle(2)

        def look(tag):
            p.settle(4)
            got5 = cell_bytes(p.composed_frame(), t, row)
            gotd = cell_bytes(p.frame(), t, row)
            mapc = p.rb(S["ROOM_MAP"] + row * 32 + t)
            ok = got5 == want and gotd == want and mapc == T_TRAP and p.rb("CUR_ROOM") == r
            if not ok:
                bad.append((tag, sd, depth, cand, "bank5", got5, "shown", gotd, "want", want, "map", mapc,
                            "room", p.rb("CUR_ROOM")))
            return ok
        place(x, side == "H")
        p.turn("WAIT")
        p.settle(12)                                           # the find's blink steps
        if not p.rb(TL) & S["TRF_KNOWN"]:
            bad.append(("L1 not found", sd, depth, cand))
            continue
        look("L1 reveal")
        if p.rb("TRAP_UNDER") != u:
            bad.append(("L1 TRAP_UNDER", p.rb("TRAP_UNDER"), u))

        def go(key, xx):
            place(xx, key == "H")
            r0 = p.rb("CUR_ROOM")
            for _ in range(5):
                p.turn(key)
                if p.rb("CUR_ROOM") != r0:
                    break
            p.settle(3)
            for sl in range(1, S["P_MAX_ENT"]):
                if p.ent(sl)["FLAGS"]:
                    p.set_ent(sl, FLAGS=0)
            return p.rb("CUR_ROOM")
        if go(side, x_edge) == r:
            print("  [info] L2 skip (the exit did not take: a door / block), seed", sd, cand, flush=True)
            continue
        back_edge = 1 if side == "L" else 28                   # the arrival side in the neighbour
        if go(back, back_edge) != r:
            print("  [info] L2 skip (did not come back), seed", sd, cand, flush=True)
            continue
        look("L2 scroll back in")
        p.code([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["present_full"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        look("L3 room_show")
        done = (sd, depth, cand)
        break
    if done is None:
        bad.append(("L no candidate (decor on a standing row beside an exit) in", seeds, "seeds"))
    return bad, done


def main():
    nseeds = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 40   # ~0.23 s a level: 40 seeds x 16 = ~2.5 min (300 was ~20 min of silence, read as a hang)
    tf_ok = None
    bad = []
    by_d = {d: [0, 0] for d in range(1, 9)}         # levels, plates
    c3 = [0, 0]                                     # C3: plates over T_AIR / over decor
    INK = [S["TRAP_INK_DART"], S["TRAP_INK_GAS"], S["TRAP_INK_TELE"], S["TRAP_INK_ALARM"], S["TRAP_INK_STUN"]]
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
                        if b0 & S["TRF_RUNG"]:                  # ALARM-1 guard (generation)
                            bad.append(("C1 RUNG", sd, d, i, hex(b0)))
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
                        mine = [(i, er, s, t) for i, (er, s, t) in enumerate(ents) if er == r]
                        hid = None
                        if m < 10 and mine:                   # C3: the hidden build first
                            for i, *_ in mine:
                                p.wb(TL + 2 * i, p.rb(TL + 2 * i) & ~S["TRF_KNOWN"] & 255)
                            run_stub(p, code, DRV)
                            hid = p.z.read_memory(S["NEXT_MAP"], 576)
                            for i, *_ in mine:
                                p.wb(TL + 2 * i, p.rb(TL + 2 * i) | S["TRF_KNOWN"])
                        run_stub(p, code, DRV)
                        mp = p.z.read_memory(S["NEXT_MAP"], 576)
                        if hid is not None:
                            plates = {(9 * s + 7) * 32 + t for (_, er, s, t) in mine}
                            diff = [i for i in range(576) if mp[i] != hid[i] and i not in plates]
                            if diff:
                                bad.append((m, d, hk, r, "C3 decor changed by a known trap", diff[:6]))
                            i_, _, s, t = mine[-1]
                            u = hid[(9 * s + 7) * 32 + t]
                            if u < S["T_ITEM0"]:
                                ty = p.rb(TL + 2 * i_ + 1) >> 5
                                gl = list(p.z.read_memory(S["TILE_GLYPHS"] + 8 * T_TRAP, 8))
                                at = p.rb(S["TILE_ATTRS"] + T_TRAP)
                                wg = composed(list(p.z.read_memory(S["TILE_GLYPHS"] + 8 * u, 8)))
                                wa = INK[ty]                  # user 2026-11-05: its own type colour, over decor too
                                c3[1 if u else 0] += 1
                                if gl != wg or at != wa or p.rb("TRAP_UNDER") != u:
                                    bad.append((m, d, hk, r, "C3 composite", u, gl, wg, hex(at), hex(wa)))
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
        print(f"  C3: {c3[0]} plates over T_AIR, {c3[1]} over decor, composed + checked")
        lbad, ldone = live_or(h, 40)
        print(f"  L1..L3 (seed, depth, (room, s, col, side, x, edge, decor id)): {ldone}, {len(lbad)} violations")
        for b in lbad[:6]:
            print("  FAIL L", b)
        bad += lbad
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
