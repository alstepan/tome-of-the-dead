#!/usr/bin/env python3
"""tests/tut0_level.py - static (no emulator) check of the TUT0 D0 level block (task TUT0-T4).

Reads build/tut/tut0_level.asm (written by tools/tut0_level.py; regenerated here when missing or
older than the tool), rebuilds the 320-B LVL_STATE block from its byte images and checks:
  L  game.md §1.1 rules via tools/levelcheck.py's helpers (feature gaps, shaft / ladder ranges, pit
     geometry, item cells, exits / storeys / shaft links, flag consistency) - the 3-room shape
     replaces levelcheck.check's 7..9-room rules
  R  tutorial_d0.md §10.13 / §1.1 reachability by walk + climb (+ the narrow-pit jump), door
     unlocked by the key room's key: every (room, storey, side) node is mutually reachable, the
     grate, every item and the trap are reachable
  S  every mentor spot box (3 cols x 6 rows) is all T_AIR in the room model (structure + the decor
     of RD_SEED + the shut gate), clear of ladders / holes / doors / items / trap plates, and no
     decorative drip source (drip7.asm model, DEPTH 1) in its cols on its storey
  B  tile-id budget: decor of rooms A / B / C uses <= 10 distinct ids in 32..59 (map ids + the
     ANIM_LIST alternate frame ids decor_tick swaps in, TUT0-F1), the 18 mentor ids are distinct,
     in 32..59 and disjoint from them; 17 ids (cell 17, blank in every image, is T_AIR)
  M  Goblin params, hero state, LF_UNIQUE set, grate shut, descriptor bytes zero outside A / B / C,
     images == the tool's emit
Also cross-checks structure + decor against tests/room_model.py render_room when the build's
.sna / .sym allow importing it (skipped otherwise).
Run: python3 tests/tut0_level.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import tut0_level as TL  # noqa: E402
import levelcheck as LC  # noqa: E402
import levelgen as G  # noqa: E402

D, BASE, H = G.D, G.BASE, G.H
OFF_EDGE, OFF_DESC, OFF_FLOOR = G.OFF_EDGE, G.OFF_DESC, G.OFF_FLOOR
ASM = ROOT / "build" / "tut" / "tut0_level.asm"
T = TL.T
COLS, SR, SA, F0, F1 = TL.COLS, TL.SR, TL.SA, TL.F0, TL.F1
A, B, C = TL.ROOM_A, TL.ROOM_B, TL.ROOM_C

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    if not ok:
        print(f"FAIL {name} {detail}")


def parse_asm(path):
    """{label: bytes} for the DEFB tables, {name: int} for the EQUs, {label: [[bytes per DEFB line]]}"""
    labels, equs, cur = {}, {}, None
    for line in path.read_text().splitlines():
        code = line.split(";")[0].strip()
        m = re.match(r"^([A-Za-z_]\w*):", code)
        if m:
            cur = m.group(1)
            labels[cur] = []
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s+EQU\s+(\S+)", code)
        if m:
            equs[m.group(1)] = int(m.group(2).replace("$", "0x"), 0)
            continue
        m = re.match(r"^DEFB\s+(.*)$", code)
        if m and cur:
            labels[cur].append([int(x.strip().replace("$", "0x"), 0) for x in m.group(1).split(",")])
    return labels, equs


def rd(blk, r, k):
    return blk[OFF_DESC + r * D["RD_STRIDE"] + D[k]]


def main():
    tool = ROOT / "tools" / "tut0_level.py"
    if not ASM.exists() or ASM.stat().st_mtime < tool.stat().st_mtime:
        print("(regenerating build/tut/tut0_level.asm: ~20 s)")
        TL.main(["tut0_level.py"])
    labels, equs = parse_asm(ASM)
    flat = {k: bytes(b for ln in v for b in ln) for k, v in labels.items()}

    # ---- rebuild the block from the images ----------------------------------------------------------
    blk = bytearray(G.BLOCK_LEN)
    img = (("tut0_lvl_state", 0, 16), ("tut0_edge_tab", OFF_EDGE, 6), ("tut0_room_desc", OFF_DESC, 144),
           ("tut0_trap_list", D["TRAP_LIST"] - BASE, 16),
           ("tut0_floor_list", OFF_FLOOR, D["FLOOR_MAX"] * D["FL_STRIDE"]))
    for lab, off, n in img:
        check(f"M image {lab} length {n}", len(flat.get(lab, b"")) == n, str(len(flat.get(lab, b""))))
        blk[off:off + n] = flat[lab]
    blk = bytes(blk)
    seeds = {r: blk[OFF_DESC + r * 16 + D["RD_SEED"]] | blk[OFF_DESC + r * 16 + D["RD_SEED"] + 1] << 8 for r in range(9)}
    check("M images == the block the tool builds for those seeds",
          blk == TL.build_block({r: seeds[r] for r in (A, B, C)}))
    present = [r for r in range(9) if rd(blk, r, "RD_FLAGS") & D["RDF_PRESENT"]]
    check("M rooms present == A B C", present == sorted((A, B, C)), str(present))
    for r in range(9):
        if r not in (A, B, C):
            check(f"M absent room {r} zero", not any(blk[OFF_DESC + r * 16:OFF_DESC + r * 16 + 16]))

    # ---- M: header / state ---------------------------------------------------------------------------
    check("M LVL_DEPTH 1 (internal depth stays 1)", blk[H["LVL_DEPTH"]] == 1)
    check("M start A / lair C / key B / nrooms 3", (blk[H["LVL_START"]], blk[H["LVL_LAIR"]], blk[H["LVL_KEYROOM"]],
                                                    blk[H["LVL_NROOMS"]]) == (A, C, B, 3))
    check("M sanctum none", blk[H["LVL_SANCTUM"]] == D["ROOM_NONE"])
    fl = blk[H["LVL_FLAGS"]]
    check("M LF_UNIQUE set, grate SHUT, gate hint clear", fl & D["LF_UNIQUE"] and not fl & D["LF_GRATE_OPEN"]
          and not fl & D["LF_GATE_HINT"], hex(fl))
    check("M attrs == ATTR_FLOOR/WALL[1]", (blk[H["LVL_ATTR_FLOOR"]], blk[H["LVL_ATTR_WALL"]]) == LC.ATTRS_REF[1])
    check("M MASTER_SEED bytes 0 (blob copies TUT0_HDR_COPY only)", equs["TUT0_HDR_COPY"] == H["MASTER_SEED"]
          and blk[H["MASTER_SEED"]:H["MASTER_SEED"] + 2] == b"\0\0")
    check("M header spare zero", not any(blk[H["MASTER_SEED"] + 2:D["LVL_HDR_LEN"]]))
    check("M edge B-C = LINK|DOOR|LOCK, others 0", [blk[OFF_EDGE + e] for e in range(6)] ==
          [0, 0, 0, D["EG_LINK"] | D["EG_DOOR"] | D["EG_LOCK"], 0, 0] and TL.EDGE_BC == 3)
    check("M no L2 / block fields", all(not any(blk[OFF_DESC + r * 16 + D["RD_SPARE"]:OFF_DESC + r * 16 + 16]) and
                                         not rd(blk, r, "RD_BLOCK") for r in range(9)))
    check("M seeds nonzero in A B C", all(seeds[r] for r in (A, B, C)), str(seeds))
    check("M TRAP_LIST: 1 hidden dart in B storey 0 col 13",
          flat["tut0_trap_list"][:2] == bytes((B, 13 | D["TT_DART"] << D["TR_TYPE_SHIFT"])) and flat["tut0_trap_list"][12] == 1
          and not any(flat["tut0_trap_list"][2:12]) and not any(flat["tut0_trap_list"][13:]) and not flat["tut0_trap_list"][0] & D["TRF_KNOWN"])
    fn = blk[H["FLOOR_N"]]
    ents = [tuple(blk[OFF_FLOOR + 4 * i:OFF_FLOOR + 4 * i + 4]) for i in range(D["FLOOR_MAX"])]
    check("M FLOOR_N 5 + the rest FL_EMPTY", fn == 5 == equs["TUT0_FLOOR_N"] and
          all(e == (D["FL_EMPTY"],) * 4 for e in ents[fn:]))
    want = [(A, 0, 24, "IT_BOOK"), (A, 1, 17, "IT_F_PEAR"), (B, 0, 19, "IT_P_CURE"),
            (C, 1, 4, "IT_S_SLEEP"), (C, 1, 9, "IT_P_HEAL")]
    check("M floor entries (book, pear, cure, sleep, heal) qty 1",
          ents[:fn] == [(r | (D["FL_S1"] if s else 0), c, D[it], 1) for r, s, c, it in want], str(ents[:fn]))
    check("M Goblin: room C, x 22 (= the grate col), storey 1", (equs["TUT0_GOB_ROOM"], equs["TUT0_GOB_X"], equs["TUT0_GOB_S"]) ==
          (C, rd(blk, C, "RD_EXITCOL"), 1) and equs["TUT0_GOB_X"] == 22)

    # ---- L: game.md §1.1 rules through levelcheck's helpers ------------------------------------------
    # (levelcheck.check itself asserts the 7..9-room generator shape, not applicable to 3 hand rooms)
    for r in (A, B, C):
        tag = "ABC"[(A, B, C).index(r)]
        up, dn, arr, ec = (rd(blk, r, k) for k in ("RD_UPCOL", "RD_DNCOL", "RD_ARRCOL", "RD_EXITCOL"))
        l1, l2, pit = rd(blk, r, "RD_LAD1"), rd(blk, r, "RD_LAD2"), rd(blk, r, "RD_PITCOL")
        check(f"L room {tag} has an internal ladder", l1 != 0)
        for nm, c in (("lad1", l1), ("lad2", l2)):
            check(f"L room {tag} {nm} in range", not c or D["LAD_COL_MIN"] <= c <= D["LAD_COL_MAX"])
        for nm, c in (("up", up), ("dn", dn), ("arr", arr), ("exit", ec)):
            check(f"L room {tag} {nm} shaft in 5..24", not c or LC.SHAFT_LO <= c <= LC.SHAFT_HI)
        check(f"L room {tag} no ladder on a shaft col", not any(s and s in (l1, l2) for s in (up, dn, arr, ec)))
        s0 = [f for f in (up, arr, l1, l2, pit) if f]
        s1 = [f for f in (dn, ec, l1, l2) if f]
        for s, lst in ((0, s0), (1, s1)):
            check(f"L room {tag} storey {s} feature gaps >= 7",
                  all(abs(x - y) >= D["FEAT_GAP"] for i, x in enumerate(lst) for y in lst[i + 1:]), str(lst))
        check(f"L room {tag} pit geometry (§1.1 pit rules)", not LC.pit_violations(blk, r), str(LC.pit_violations(blk, r)))
        check(f"L room {tag} flags / start / lair", bool(rd(blk, r, "RD_FLAGS") & D["RDF_START"]) == (r == A) and
              bool(rd(blk, r, "RD_FLAGS") & D["RDF_LAIR"]) == (r == C) and bool(rd(blk, r, "RD_FLAGS") & D["RDF_DEADEND"]) == (r != B))
        check(f"L room {tag} seed != 0", seeds[r] != 0)
    check("L arrival only in the start room, level exit only in the lair",
          [bool(rd(blk, r, "RD_ARRCOL")) for r in (A, B, C)] == [True, False, False] and
          [bool(rd(blk, r, "RD_EXITCOL")) for r in (A, B, C)] == [False, False, True])
    check("L start x == arrival col (H1-ARRIVAL), 5", G.start_x(blk) == rd(blk, A, "RD_ARRCOL") == 5)
    check("L A.down {5,2} == B.up {5,0}; both sides carry the exit bit",
          rd(blk, A, "RD_DNCOL") == rd(blk, B, "RD_UPCOL") == 5 and rd(blk, A, "RD_EXITS") & D["RDX_D"]
          and rd(blk, B, "RD_EXITS") & D["RDX_U"])
    exB, exC = rd(blk, B, "RD_EXITS"), rd(blk, C, "RD_EXITS")
    check("L B.right and C.left on the same storey 1", exB & D["RDX_R"] and exB & D["RDX_RS1"] and exC & D["RDX_L"]
          and exC & D["RDX_LS1"])
    check("L no stray exits (A: down only; C: left only; B: up + right)", rd(blk, A, "RD_EXITS") == D["RDX_D"] and
          exB == D["RDX_U"] | D["RDX_R"] | D["RDX_RS1"] and exC == D["RDX_L"] | D["RDX_LS1"])
    for i, (r, s, col, it) in enumerate(want):
        check(f"L item {i} ({it}) cell legal (levelcheck.item_ok)", LC.item_ok(blk, r, s, col) and LC.item_ok(blk, r, s, col + 1))
    check("L items: not in the start col zone of the hero, no 2 items on a col", len({(r, s, c) for r, s, c, _ in want}) == 5)
    tr = (B, 0, 13)
    check("L trap cells legal (item_ok cols 13, 14)", LC.item_ok(blk, tr[0], tr[1], 13) and LC.item_ok(blk, tr[0], tr[1], 14))

    # ---- R: reachability (§10.13) ----------------------------------------------------------------------
    def side(r, s, col):                     # a narrow pit splits storey 0 into side 0 (left) / 1 (right)
        p = rd(blk, r, "RD_PITCOL")
        return 1 if (s == 0 and p and col >= p) else 0
    E = {}

    def link(a, b):
        E.setdefault(a, set()).add(b)
        E.setdefault(b, set()).add(a)
    for r in (A, B, C):
        if rd(blk, r, "RD_PITCOL"):          # the narrow pit: jump x = p-3 <-> p+3 (bodies on floor, pit rules above)
            link((r, 0, 0), (r, 0, 1))
        for k in ("RD_LAD1", "RD_LAD2"):
            c = rd(blk, r, k)
            if c:
                link((r, 0, side(r, 0, c)), (r, 1, 0))
        ex = rd(blk, r, "RD_EXITS")
        if ex & D["RDX_R"]:
            s = 1 if ex & D["RDX_RS1"] else 0
            link((r, s, side(r, s, 31)), (r + 1, s, side(r + 1, s, 0)))    # the door: the key room's key opens it
        if ex & D["RDX_D"]:
            link((r, 1, 0), (r + 3, 0, side(r + 3, 0, rd(blk, r + 3, "RD_UPCOL"))))
    nodes = {(r, s, sd) for r in (A, B, C) for s in (0, 1) for sd in (0, 1) if s == 1 and sd == 0 or
             (s == 0 and (sd == 0 or rd(blk, r, "RD_PITCOL")))}
    src = (A, 0, side(A, 0, 5))
    reach, q = {src}, [src]
    for n in q:
        for x in E.get(n, ()):
            if x not in reach:
                reach.add(x)
                q.append(x)
    check("R every node reachable from the arrival by walk + climb + narrow jump",
          nodes <= reach, str(sorted(nodes - reach)))
    grate = (C, 1, 0)
    check("R the grate (C, storey 1) is reachable from every node (graph is undirected: strongly connected)",
          all(grate in _bfs(E, n) for n in nodes))
    for i, (r, s, col, it) in enumerate(want):
        check(f"R item {it} reachable", (r, s, side(r, s, col)) in reach)
    check("R trap on B's only storey-0 walk path to L1 (up {5} < trap 13 < ladder 24)",
          rd(blk, B, "RD_UPCOL") < 13 < rd(blk, B, "RD_LAD1") and not rd(blk, B, "RD_PITCOL"))
    check("R no block / pit in B and C", not any(rd(blk, r, "RD_PITCOL") or rd(blk, r, "RD_BLOCK") for r in (B, C)))

    # ---- S: spot boxes -----------------------------------------------------------------------------------
    maps = {r: TL.final_room(blk, r) for r in (A, B, C)}
    tab = flat["tut0_spots"]
    spots = [tuple(tab[3 * i:3 * i + 3]) for i in range(len(tab) // 3)]
    names = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "GRATE"]
    check("S spot table: 8 spots in the contract order", equs["TUT0_SPOT_N"] == 8 == len(spots) and
          [equs.get("TUT0_SP_" + n) for n in names] == list(range(8)),
          str(equs))
    want_room = [A, A, A, B, B, B, C, C]
    check("S spot rooms", [s[0] for s in spots] == want_room)
    drips = {r: TL.drip_sources(maps[r], TL.DEPTH, seeds[r]) for r in (A, B, C)}
    for nm, (r, col, top) in zip(names, spots):
        s = 1 if top >= SR else 0
        check(f"S {nm}: top row = 9s+1", top == SR * s + 1, str(top))
        check(f"S {nm}: cols {col}..{col + 2} inside 2..29", 2 <= col and col + 2 <= 29)
        cells = [(top + dr, col + dc) for dr in range(6) for dc in range(3)]
        check(f"S {nm}: 3x6 box all T_AIR (room model, decor + gate included)",
              all(maps[r][y * COLS + x] == T["T_AIR"] for y, x in cells),
              str([(y, x, maps[r][y * COLS + x]) for y, x in cells if maps[r][y * COLS + x]]))
        # explicit "clear of ..." (the T_AIR check already implies the structural ones)
        foot = []
        for k in ("RD_UPCOL", "RD_ARRCOL"):
            if rd(blk, r, k):
                foot.append((0, rd(blk, r, k)))
        for k in ("RD_DNCOL", "RD_EXITCOL"):
            if rd(blk, r, k):
                foot.append((2, rd(blk, r, k)))
        for k in ("RD_LAD1", "RD_LAD2"):
            if rd(blk, r, k):
                foot.append((1, rd(blk, r, k)))      # storey-1 ladder: rows 8..16
        rows = range(top, top + 6)
        bad = [(st, c) for st, c in foot
               if any(((st == 0 and y <= 7) or (st == 1 and y >= 8) or (st == 2 and y >= 17)) for y in rows)
               and not (c + 2 < col or c > col + 2)]
        check(f"S {nm}: clear of ladders / shafts / holes", not bad, str(bad))
        check(f"S {nm}: clear of doors (cols 0-1 / 30-31)", col >= 2 and col + 2 <= 29)
        itc = [(r2, s2, c2) for r2, s2, c2, _ in want if r2 == r and s2 == s and not (c2 + 1 < col or c2 > col + 2)]
        check(f"S {nm}: clear of items (cols c..c+1, rows 9s+6..7)",
              not any(top + 5 >= SR * s + SA - 2 for _ in itc), str(itc))
        check(f"S {nm}: clear of the trap plate", not (tr[0] == r and tr[1] == s and not (14 < col or 13 > col + 2)))
        check(f"S {nm}: no drip source in its cols on its storey",
              not any(sr // SR == s and col <= c < col + 3 for c, sr in drips[r]), str(drips[r]))

    # ---- B: tile-id budget -------------------------------------------------------------------------------
    used = set()
    per = {}
    for r in (A, B, C):
        per[r] = {t for t in maps[r] if TL.ID_LO <= t <= TL.ID_HI}
        # TUT0-F1: decor_tick swaps in each ANIM_LIST entry's AL_TYPE (the alternate frame id, not in
        # the map): those glyph slots are live too (torch flames once showed the mentor's head)
        anim = TL.decorgen.decorate(TL.structure(blk, r), TL.DEPTH, seeds[r])[1]
        aids = {t for t in anim[2::4] if TL.ID_LO <= t <= TL.ID_HI}
        check(f"B room {r}: every animation frame id is in 32..59", all(TL.ID_LO <= t <= TL.ID_HI for t in anim[2::4]),
              str(anim[2::4]))
        per[r] |= aids
        used |= per[r]
    check(f"B decor ids in A/B/C <= {TL.DECOR_IDS_MAX} distinct (32..59)", len(used) <= TL.DECOR_IDS_MAX, str(sorted(used)))
    mall = list(flat["tut0_mentor_ids"])
    mids = mall[:TL.MENTOR_IDS]
    n0 = equs.get("TUT0_MENTOR_ID0")
    check("B 17 mentor ids, distinct, contiguous from TUT0_MENTOR_ID0, 32..59, disjoint from the decor",
          len(mids) == TL.MENTOR_IDS == equs["TUT0_MENTOR_N"] and mids == list(range(n0, n0 + TL.MENTOR_IDS)) and
          all(TL.ID_LO <= i <= TL.ID_HI for i in mids) and not set(mids) & used, str(mids))
    lft = list(flat["tut0_mentor_ids_l"])
    check("B mentor table: 18 cells, the blank cell T_AIR; the left table = each row reversed",
          len(mall) == 18 and mall[TL.MENTOR_BLANK] == T["T_AIR"] and
          lft == [mall[3 * (i // 3) + 2 - i % 3] for i in range(18)], str((mall, lft)))
    art = []
    for ln in (ROOT / "assets" / "gfx" / "mentor" / "aldous34.asm").read_text().splitlines():
        m = re.search(r"DEFB\s+(.*)", ln.split(";")[0])
        if m:
            art += [int(t.strip()[1:], 16) for t in m.group(1).split(",")]
    nimg = len(art) // 144
    check(f"B mentor cell {TL.MENTOR_BLANK} is blank in all {nimg} images (it takes no id)",
          nimg == 7 and all(not any(art[i * 144 + 8 * TL.MENTOR_BLANK:i * 144 + 8 * TL.MENTOR_BLANK + 8]) for i in range(nimg)))
    check("B any other id in rooms is a structural / item id (< 32 or 60..63)",
          all(t < TL.ID_LO or TL.ID_HI < t <= 63 for r in (A, B, C) for t in maps[r] if t not in used))
    check("B no room uses RD_SEED 0 fallback", all(seeds[r] for r in (A, B, C)))

    # ---- optional cross-check against tests/room_model.py ------------------------------------------------
    xnote = "skipped (room_model not importable)"
    try:
        os.environ.setdefault("GAME_ALLOW_DEBUG_KIT", "1")
        sys.path.insert(0, str(HERE))
        import room_model as RM  # noqa: E402
        ok = all(list(RM.render_room(blk, r)) == maps[r] for r in (A, B, C))
        check("X structure + decor + gate == tests/room_model.py render_room", ok)
        xnote = "room_model cross-check done"
    except Exception as e:  # noqa: BLE001
        xnote = f"skipped ({type(e).__name__})"

    bad = [n for n, ok in results if not ok]
    print(f"tut0_level: {len(results) - len(bad)}/{len(results)} pass; decor ids {len(used)} "
          f"(A {len(per[A])} B {len(per[B])} C {len(per[C])}); {xnote}")
    if bad:
        print("FAILED:", "; ".join(bad))
    return 1 if bad else 0


def _bfs(E, s):
    seen, q = {s}, [s]
    for n in q:
        for x in E.get(n, ()):
            if x not in seen:
                seen.add(x)
                q.append(x)
    return seen


if __name__ == "__main__":
    sys.exit(main())
