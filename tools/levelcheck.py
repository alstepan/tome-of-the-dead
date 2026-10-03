#!/usr/bin/env python3
"""levelcheck.py - invariant checker for level-state blocks (B3B-6).

check(block) -> list of violation strings (empty = pass). Hero model (game.md
2.4/2.5): per (room, storey, side) nodes; a storey-0 pit splits the floor into
a left/right side; the hero crosses it by jump (pit >= 3 clear cols each side);
falling goes storey 0 -> 1 only; ladders/vertical links are two-way; horizontal
exits join (room,s) to (neighbour,s). Walkers cannot cross a pit (stat only).

CLI: levelcheck.py [N_SEEDS=1000] [DEPTH_MAX=8]  (run all, print stats)
"""
import sys
from collections import Counter

import levelgen as G
from levelgen import D, H, OFF_DESC, OFF_EDGE, OFF_FLOOR, BLOCK_LEN, hedge


def rd(b, r, k):
    return b[OFF_DESC + r * D["RD_STRIDE"] + D[k]]


def item_free(rm, c):
    """col c on storey 0 touches no footprint/pit cap/storey-0 block"""
    for f in (rm.up, rm.arr, rm.lad1, rm.lad2):
        if f and f <= c <= f + 2: return False
    if rm.pit and rm.pit - 1 <= c <= rm.pit + 3: return False
    if rm.block and not (rm.block >> 6) & 1:
        w = rm.block & D["RDB_WMASK"]
        if (c >= 31 - w) if rm.block & D["RDB_RIGHT"] else (c <= w): return False
    return True


def check(b, stats=None):
    v = []
    if len(b) != BLOCK_LEN:
        return [f"length {len(b)} != {BLOCK_LEN}"]
    depth = b[H["LVL_DEPTH"]]
    if not 1 <= depth <= 8:
        return ["depth range"]
    present = [r for r in range(9) if rd(b, r, "RD_FLAGS") & D["RDF_PRESENT"]]
    pset = set(present)
    n = len(present)
    if not 7 <= n <= 9: v.append(f"rooms {n} not 7..9")
    if b[H["LVL_NROOMS"]] != n: v.append("NROOMS mismatch")
    if b[H["LVL_KEYROOM"]] != D["ROOM_NONE"] or b[H["LVL_SANCTUM"]] != D["ROOM_NONE"]:
        v.append("key/sanctum must be ROOM_NONE in 3B")
    if b[H["LVL_FLAGS"]] != D["LF_GRATE_OPEN"]: v.append("LVL_FLAGS")
    if (b[H["LVL_ATTR_FLOOR"]], b[H["LVL_ATTR_WALL"]]) != G.ATTRS.get(depth): v.append("attrs")
    for i in range(H["MASTER_SEED"] + 2, D["LVL_HDR_LEN"]):
        if b[i]: v.append("header spare")
    for i in range(OFF_EDGE + 6, OFF_DESC):
        if b[i]: v.append("EDGE_TAB spare nonzero")
    for i in range(OFF_DESC + 9 * 16, OFF_FLOOR):
        if b[i]: v.append("desc-area spare nonzero")
    start = b[H["LVL_START"]]; lair = b[H["LVL_LAIR"]]
    if start not in pset or lair not in pset or start == lair:
        return v + ["start/lair ids"]
    adj = {r: set() for r in present}
    for r in range(9):
        o = OFF_DESC + r * 16
        if r not in pset:
            if any(b[o:o + 16]): v.append(f"absent room {r} not zero")
            continue
        for i in range(D["RD_SPARE"], 16):
            if b[o + i]: v.append(f"room {r} spare byte {i}")
        fl = rd(b, r, "RD_FLAGS")
        if fl & ~(D["RDF_PRESENT"] | D["RDF_START"] | D["RDF_LAIR"] | D["RDF_DEADEND"]): v.append(f"room {r} flags")
        if bool(fl & D["RDF_START"]) != (r == start) or bool(fl & D["RDF_LAIR"]) != (r == lair):
            v.append(f"room {r} start/lair flag")
        if b[o + D["RD_SEED"]] | b[o + D["RD_SEED"] + 1] == 0: v.append(f"room {r} seed 0")
        ex = rd(b, r, "RD_EXITS")
        if ex & 0xC0: v.append(f"room {r} exits bits 6-7")
        gx = r % 3
        for bit, sbit, nb, ok in ((D["RDX_L"], D["RDX_LS1"], r - 1, gx > 0),
                                  (D["RDX_R"], D["RDX_RS1"], r + 1, gx < 2)):
            if ex & bit:
                if not ok or nb not in pset: v.append(f"room {r} exit to nowhere"); continue
                e = b[OFF_EDGE + hedge(min(r, nb))]
                if not e & D["EG_LINK"]: v.append(f"room {r} exit w/o LINK")
                opp = rd(b, nb, "RD_EXITS")
                osb = D["RDX_RS1"] if bit == D["RDX_L"] else D["RDX_LS1"]
                obit = D["RDX_R"] if bit == D["RDX_L"] else D["RDX_L"]
                if not opp & obit or bool(opp & osb) != bool(ex & sbit): v.append(f"edge {r}-{nb} storey mismatch")
                adj[r].add(nb)
            elif ex & sbit:
                v.append(f"room {r} storey bit w/o exit")
        up, dn = rd(b, r, "RD_UPCOL"), rd(b, r, "RD_DNCOL")
        for bit, col, nb, ok, ncolk in ((D["RDX_U"], up, r - 3, r >= 3, "RD_DNCOL"),
                                         (D["RDX_D"], dn, r + 3, r < 6, "RD_UPCOL")):
            if ex & bit:
                if not ok or nb not in pset: v.append(f"room {r} vertical to nowhere"); continue
                if not G.SHAFT_MIN <= col <= G.SHAFT_MAX: v.append(f"room {r} shaft col {col} out of range")
                if rd(b, nb, ncolk) != col: v.append(f"link {r}-{nb} shaft cols differ")
                if not rd(b, nb, "RD_EXITS") & (D["RDX_D"] if bit == D["RDX_U"] else D["RDX_U"]):
                    v.append(f"link {r}-{nb} one-sided")
                adj[r].add(nb)
            elif col:
                v.append(f"room {r} shaft col without exit")
        arr, ec = rd(b, r, "RD_ARRCOL"), rd(b, r, "RD_EXITCOL")
        if bool(arr) != (r == start and depth >= 2): v.append(f"room {r} arrival col presence")
        if bool(ec) != (r == lair): v.append(f"room {r} exit col presence")
        for nm, c in (("arr", arr), ("exitcol", ec)):
            if c and not G.SHAFT_MIN <= c <= G.SHAFT_MAX: v.append(f"room {r} {nm} range")
        l1, l2, pit = rd(b, r, "RD_LAD1"), rd(b, r, "RD_LAD2"), rd(b, r, "RD_PITCOL")
        if not l1: v.append(f"room {r} no ladder")
        for nm, c in (("lad1", l1), ("lad2", l2)):
            if c and not D["LAD_COL_MIN"] <= c <= D["LAD_COL_MAX"]: v.append(f"room {r} {nm} range")
        if pit and not 3 <= pit <= 26: v.append(f"room {r} pit range / clear cols")
        s0 = [f for f in (up, arr, l1, l2, pit) if f]
        s1 = [f for f in (dn, ec, l1, l2) if f]
        for lst, s in ((s0, 0), (s1, 1)):
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    if abs(lst[i] - lst[j]) < D["FEAT_GAP"]: v.append(f"room {r} storey {s} features {lst[i]},{lst[j]} too close")
        for sh in (up, dn, arr, ec):
            if sh and sh in (l1, l2): v.append(f"room {r} ladder on shaft col")
        bl = rd(b, r, "RD_BLOCK")
        if bl:
            w = bl & D["RDB_WMASK"]; s = (bl >> 6) & 1; right = bool(bl & D["RDB_RIGHT"])
            if bl & 0x3C or w not in (2, 3): v.append(f"room {r} block byte")
            bit, sbit = (D["RDX_R"], D["RDX_RS1"]) if right else (D["RDX_L"], D["RDX_LS1"])
            if r in (start, lair): v.append(f"room {r} block in start/lair")
            if ex & bit: v.append(f"room {r} block on an exit edge")
            lo, hi = (32 - w - 1, 31) if right else (0, w)
            for f in (s0 if s == 0 else s1):
                if not (f + 2 < lo or f > hi): v.append(f"room {r} block hits feature {f}")
            if s == 0 and pit and not (pit + 3 < lo or pit - 1 > hi): v.append(f"room {r} block hits pit")
    for e in range(6):
        gy, gx = divmod(e, 2)
        r = gy * 3 + gx
        eb = b[OFF_EDGE + e]
        linked = r in pset and (r + 1) in adj.get(r, ())
        if eb & ~(D["EG_LINK"] | D["EG_DOOR"]): v.append(f"edge {e} unexpected bits")
        if bool(eb & D["EG_LINK"]) != linked: v.append(f"edge {e} LINK vs exits")
        if eb & D["EG_DOOR"] and not eb & D["EG_LINK"]: v.append(f"edge {e} door w/o link")
    nedges = sum(len(a) for a in adj.values()) // 2
    if nedges not in (n - 1, n): v.append(f"edges {nedges} for {n} rooms")
    seen = {start}; q = [start]; dist = {start: 0}
    for r in q:
        for x in sorted(adj.get(r, ())):
            if x not in seen: seen.add(x); dist[x] = dist[r] + 1; q.append(x)
    if seen != pset: v.append("grid not connected")
    deg = {r: len(adj[r]) for r in present}
    for r in present:
        if bool(rd(b, r, "RD_FLAGS") & D["RDF_DEADEND"]) != (deg[r] == 1): v.append(f"room {r} DEADEND flag != leaf")
    def has_h(r): return bool(rd(b, r, "RD_EXITS") & (D["RDX_L"] | D["RDX_R"]))
    def san(r):
        if depth != 8 or not G.SANCTUM_CELL_RULE: return True
        return (r % 3 > 0 and r - 1 not in pset) or (r % 3 < 2 and r + 1 not in pset)
    pools = ([r for r in present if deg[r] == 1 and r != start and has_h(r) and san(r)],
             [r for r in present if r != start and has_h(r) and san(r)])
    pool = next((p for p in pools if p), [])
    fallback = pool is not pools[0]
    if lair not in pool: v.append("lair not in candidate pool")
    elif dist.get(lair, -1) != max(dist.get(r, 0) for r in pool): v.append("lair not farthest candidate")
    def side(r, s, col):
        p = rd(b, r, "RD_PITCOL")
        return 1 if (s == 0 and p and col >= p) else 0
    def graph(walker):
        E = {}
        def link(a, c, both=True):
            E.setdefault(a, set()).add(c)
            if both: E.setdefault(c, set()).add(a)
        for r in present:
            if rd(b, r, "RD_PITCOL") and not walker:
                link((r, 0, 0), (r, 0, 1))                                   # jump
                link((r, 0, 0), (r, 1, 0), False); link((r, 0, 1), (r, 1, 0), False)  # fall
            for k in ("RD_LAD1", "RD_LAD2"):
                c = rd(b, r, k)
                if c: link((r, 0, side(r, 0, c)), (r, 1, 0))
            ex = rd(b, r, "RD_EXITS")
            if ex & D["RDX_R"]:
                s = 1 if ex & D["RDX_RS1"] else 0
                link((r, s, side(r, s, 31)), (r + 1, s, side(r + 1, s, 0)))
            if ex & D["RDX_D"]:
                link((r, 1, 0), (r + 3, 0, side(r + 3, 0, rd(b, r + 3, "RD_UPCOL"))))
        return E
    targets = set()
    for r in present:
        ex = rd(b, r, "RD_EXITS")
        for bit, sb, col in ((D["RDX_L"], D["RDX_LS1"], 0), (D["RDX_R"], D["RDX_RS1"], 31)):
            if ex & bit:
                s = 1 if ex & sb else 0
                targets.add((r, s, side(r, s, col)))
        if ex & D["RDX_U"]: targets.add((r, 0, side(r, 0, rd(b, r, "RD_UPCOL"))))
        if ex & D["RDX_D"]: targets.add((r, 1, 0))
    targets.add((lair, 1, 0))
    a = rd(b, start, "RD_ARRCOL")
    src = (start, 0, side(start, 0, a if a else 1))
    cut = {}
    for walker in (False, True):
        E = graph(walker); reach = {src}; q = [src]
        for nd in q:
            for x in E.get(nd, ()):
                if x not in reach: reach.add(x); q.append(x)
        cut[walker] = [t for t in targets if t not in reach]
    if cut[False]: v.append(f"hero cannot reach {sorted(cut[False])}")
    fn = b[H["FLOOR_N"]]
    if fn > D["FLOOR_MAX"]: v.append("FLOOR_N > 32"); fn = 0
    for i in range(D["FLOOR_MAX"]):
        o = OFF_FLOOR + i * 4
        ent = b[o:o + 4]
        if i >= fn:
            if any(x != D["FL_EMPTY"] for x in ent): v.append(f"floor slot {i} not FL_EMPTY")
            continue
        r = ent[0] & 15; s = ent[0] >> 7
        if ent[0] & 0x70 or r not in pset or r == start: v.append(f"floor {i} room")
        elif ent[2] != D["IT_POTION"] or ent[3] < 1: v.append(f"floor {i} item/qty")
        else:
            rm = G.Room(); rm.up = rd(b, r, "RD_UPCOL"); rm.dn = rd(b, r, "RD_DNCOL")
            rm.arr = rd(b, r, "RD_ARRCOL"); rm.exitcol = rd(b, r, "RD_EXITCOL")
            rm.lad1 = rd(b, r, "RD_LAD1"); rm.lad2 = rd(b, r, "RD_LAD2")
            rm.pit = rd(b, r, "RD_PITCOL"); rm.block = rd(b, r, "RD_BLOCK")
            if not G.item_col_ok(rm, s, ent[1]): v.append(f"floor {i} illegal cell col {ent[1]} s{s}")
    if not 2 <= fn <= 3: v.append(f"potion count {fn}")
    try:
        sx = G.start_x(b)
        rm0 = G.Room(); rm0.up = rd(b, start, "RD_UPCOL"); rm0.arr = 0     # arrival shaft exempt (hero stands at arr+1)
        rm0.lad1 = rd(b, start, "RD_LAD1"); rm0.lad2 = rd(b, start, "RD_LAD2")
        rm0.pit = rd(b, start, "RD_PITCOL"); rm0.block = rd(b, start, "RD_BLOCK")
        if not 2 <= sx <= 29 or any(not item_free(rm0, c) for c in (sx - 1, sx, sx + 1)):
            v.append(f"start x {sx} illegal")
        if depth == 1 and abs(sx - 14) > 12: v.append("start x far from 14")
    except RuntimeError as ex_:
        v.append(str(ex_))
    if stats is not None:
        hedges = [b[OFF_EDGE + e] for e in range(6) if b[OFF_EDGE + e] & D["EG_LINK"]]
        stats["rooms"][n] += 1
        stats["h_edges"] += len(hedges)
        stats["doors"] += sum(1 for e in hedges if e & D["EG_DOOR"])
        stats["pits"] += sum(1 for r in present if rd(b, r, "RD_PITCOL"))
        stats["dead"] += sum(1 for r in present if deg[r] == 1)
        stats["loops"] += nedges == n
        stats["lair_fallback"] += fallback
        stats["walker_cut"] += bool(cut[True])
        stats["blocks"] += sum(1 for r in present if rd(b, r, "RD_BLOCK"))
        stats["lad2"] += sum(1 for r in present if rd(b, r, "RD_LAD2"))
        stats["potions"] += fn
    return v


def run(nseeds=1000, dmax=8):
    st = {"rooms": Counter(), "h_edges": 0, "doors": 0, "pits": 0, "dead": 0, "loops": 0,
          "lair_fallback": 0, "walker_cut": 0, "blocks": 0, "lad2": 0, "potions": 0}
    fails = []
    tot = 0
    for depth in range(1, dmax + 1):
        for i in range(nseeds):
            seed = (i * 0x9E37 + depth * 0x3D) & 0xFFFF or 1
            b = G.generate(depth, seed)
            assert b == G.generate(depth, seed), "non-deterministic"
            viol = check(b, st)
            tot += 1
            if viol:
                fails.append((depth, seed, viol[:3]))
    print(f"{tot - len(fails)}/{tot} pass")
    for f in fails[:10]: print("FAIL", f)
    print("rooms", dict(sorted(st["rooms"].items())),
          f"doors {st['doors']}/{st['h_edges']} ({st['doors'] / max(1, st['h_edges']):.2f})")
    print({k: round(st[k] / tot, 2) for k in ("pits", "dead", "loops", "lair_fallback", "walker_cut", "blocks", "lad2", "potions")}, "(per level)")
    return 1 if fails else 0


if __name__ == "__main__":
    a = sys.argv
    sys.exit(run(int(a[1]) if len(a) > 1 else 1000, int(a[2]) if len(a) > 2 else 8))
