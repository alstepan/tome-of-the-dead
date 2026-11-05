#!/usr/bin/env python3
"""levelcheck.py - invariant checker for level-state blocks (B3B-6).

check(block) -> list of violation strings (empty = pass). Hero model (game.md
2.4/2.5): per (room, storey, side) nodes; a storey-0 pit splits the floor into
a left/right side; the hero crosses it by jump (pit >= 3 clear cols each side);
falling goes storey 0 -> 1 only; ladders/vertical links are two-way; horizontal
exits join (room,s) to (neighbour,s). Walkers cannot cross a pit (stat only).

CLI: levelcheck.py [N_SEEDS=1000] [DEPTH_MAX=8]  (run all, print stats)
     levelcheck.py --full   (all 65,536 seeds x depths 1..8, multiprocessing)
"""
import sys
from collections import Counter

import levelgen as G
from levelgen import D, H, OFF_DESC, OFF_EDGE, OFF_FLOOR, BLOCK_LEN, hedge


def rd(b, r, k):
    return b[OFF_DESC + r * D["RD_STRIDE"] + D[k]]


# Checker constants, written from docs/design/game.md (NOT imported from the
# generator): sections 1.1 (rules), 1.2 (attrs), 2.4 (jump). Layout offsets/bit
# values (level_defs.asm) come from levelgen.D, which only parses the contract.
SHAFT_LO, SHAFT_HI = 5, 24                       # 1.1 "Shaft cols"
ATTRS_REF = {1: (0x0F, 0x01), 2: (0x27, 0x04), 3: (0x17, 0x02), 4: (0x28, 0x05),
             5: (0x30, 0x06), 6: (0x38, 0x07), 7: (0x4F, 0x41), 8: (0x1F, 0x03)}  # 1.2
# L2 descriptor fields (RD_SPARE bytes; written from game.md 1.1, not imported)
L2_PITW, L2_MIDB, L2_MIDW = D["RD_SPARE"], D["RD_SPARE"] + 1, D["RD_SPARE"] + 2
L2_ODDS_MAX = 2
BODY_MIN, BODY_MAX = 1, 28                       # 1.1: hero stands at x = 1 .. x = 28
DOOR_P, DOOR_TOL = 1 / 3, 0.02                   # 1.1 "1 in 3 carry a door"


def feats(b, r, s):
    """left cols of the footprints on storey s of room r (0 = none dropped)"""
    ks = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2") if s == 0 else \
         ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
    return [rd(b, r, k) for k in ks if rd(b, r, k)]


def block_span(b, r, s):
    """(lo, hi) wall cols incl. the rubble col of the storey-s block, else None"""
    bl = rd(b, r, "RD_BLOCK")
    if not bl or ((bl >> 6) & 1) != s:
        return None
    w = bl & 3
    return (31 - w, 31) if bl & 0x80 else (0, w)


def blocked(b, r, s, lo, hi, exempt_arr=False):
    """cols lo..hi touch a storey-s footprint (3 cols), the pit incl. its caps
    (storey 0: p-1 .. p+3) or the storey-s block"""
    fs = feats(b, r, s)
    if exempt_arr and s == 0 and rd(b, r, "RD_ARRCOL") in fs:
        fs.remove(rd(b, r, "RD_ARRCOL"))
    if any(not (f + 2 < lo or f > hi) for f in fs):
        return True
    p = rd(b, r, "RD_PITCOL")
    pw = b[OFF_DESC + r * 16 + L2_PITW] or 3
    if s == 0 and p and not (p + pw < lo or p - 1 > hi):          # holes + caps
        return True
    mb, mw = b[OFF_DESC + r * 16 + L2_MIDB], b[OFF_DESC + r * 16 + L2_MIDW]
    if s == 0 and mb and not (mb + mw < lo or mb - 1 > hi):       # mid-block + rubble faces
        return True
    bs = block_span(b, r, s)
    return bool(bs) and not (bs[1] < lo or bs[0] > hi)


def item_ok(b, r, s, col):
    """a floor item may stand on col: 2..29, not on a footprint / pit + caps / block"""
    return 2 <= col <= 29 and not blocked(b, r, s, col, col)


def start_legal(b, st, x):
    return 2 <= x <= 29 and not blocked(b, st, 0, x - 1, x + 1, exempt_arr=True)


def pit_violations(b, r):
    """game.md 1.1 'Pit geometry' (1)-(4), modelled exactly: the crossing is
    x = p-3 <-> p+3 (bodies p-3..p-1 and p+3..p+5, both x in 2..27); storey-0 zones
    p-4..p-1 / p+3..p+6 hold no footprint; a block keeps the zone (left: p >= w+4,
    right: p <= 25-w, either storey); every storey-1 footprint has |c-p| >= 7."""
    p = rd(b, r, "RD_PITCOL")
    out = []
    if not p:
        return out
    if not 5 <= p <= 24: out.append(f"pit col {p} outside 5..24")
    if not (2 <= p - 3 and p + 3 <= 27): out.append("crossing x outside 2..27")
    for lo, hi in ((p - 4, p - 1), (p - 3, p - 1), (p + 3, p + 6), (p + 3, p + 5)):
        if any(not (f + 2 < lo or f > hi) for f in feats(b, r, 0)):
            out.append(f"storey-0 footprint in jump zone {lo}..{hi}")
    for f in feats(b, r, 1):
        if abs(f - p) < 7: out.append(f"storey-1 footprint {f} within 7 of pit {p} (landing)")
    bl = rd(b, r, "RD_BLOCK")
    if bl:
        w = bl & 3
        if (p > 25 - w) if bl & 0x80 else (p < w + 4): out.append(f"block w{w} too close to pit {p}")
    return out


def check(b, stats=None):
    v = []
    depth_l2 = {}
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
    if b[H["LVL_FLAGS"]] != 0: v.append("LVL_FLAGS (3F-T8: the grate is shut at generation)")
    if (b[H["LVL_ATTR_FLOOR"]], b[H["LVL_ATTR_WALL"]]) != ATTRS_REF.get(depth): v.append("attrs")
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
        if b[o + D["RD_SPARE"] + 3]: v.append(f"room {r} spare byte 15")
        pitw, midb, midw = b[o + L2_PITW], b[o + L2_MIDB], b[o + L2_MIDW]
        l2 = []
        if pitw: l2.append("wide pit")
        if midb: l2.append("mid-block")
        if len(l2) > 1: v.append(f"room {r}: two L2 features")
        if midw and not midb: v.append(f"room {r}: mid width without block")
        if l2:                                          # I2 / I4
            n_l2 = depth_l2.setdefault(tuple(l2), 0)
            depth_l2[tuple(l2)] = n_l2 + 1
            ld1, ld2 = rd(b, r, "RD_LAD1"), rd(b, r, "RD_LAD2")
            c1, c2 = min(ld1, ld2), max(ld1, ld2)
            if depth < 2: v.append(f"room {r}: L2 feature on D1")
            if r in (start, lair) or not (ld1 and ld2): v.append(f"room {r}: L2 feature in an ineligible room")
            fl0 = [f for f in (rd(b, r, "RD_UPCOL"), rd(b, r, "RD_ARRCOL"), ld1, ld2) if f]
            allf = fl0 + [f for f in (rd(b, r, "RD_DNCOL"), rd(b, r, "RD_EXITCOL")) if f]
            items = [(e[1]) for e in (b[OFF_FLOOR + 4 * i:OFF_FLOOR + 4 * i + 4] for i in range(b[H["FLOOR_N"]]))
                     if e[0] == r]                      # storey-0 items of the room
            if pitw:
                p = rd(b, r, "RD_PITCOL")
                if not 4 <= pitw <= 6 or not p: v.append(f"room {r}: wide pit W {pitw} / col {p}")
                else:
                    if not (p >= c1 + 7 and p + pitw + 4 <= c2): v.append(f"room {r}: wide pit {p}/{pitw} outside the ladders")
                    for f in allf:
                        if not (f <= p - 7 or f >= p + pitw + 4): v.append(f"room {r}: footprint {f} too close to wide pit {p}/{pitw}")
                    if any(p - 1 <= c <= p + pitw for c in items): v.append(f"room {r}: item on the wide pit span")
            else:
                if not 2 <= midw <= 3: v.append(f"room {r}: mid-block width {midw}")
                if rd(b, r, "RD_PITCOL"): v.append(f"room {r}: mid-block with a pit")
                if not (midb >= c1 + 6 and midb + midw + 3 <= c2): v.append(f"room {r}: mid-block {midb}/{midw} outside the ladders")
                for f in fl0:
                    if not (f + 6 <= midb or f >= midb + midw + 3): v.append(f"room {r}: footprint {f} too close to the mid-block")
                if any(midb - 1 <= c <= midb + midw for c in items): v.append(f"room {r}: item on the mid-block span")
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
                if not SHAFT_LO <= col <= SHAFT_HI: v.append(f"room {r} shaft col {col} out of range")
                if rd(b, nb, ncolk) != col: v.append(f"link {r}-{nb} shaft cols differ")
                if not rd(b, nb, "RD_EXITS") & (D["RDX_D"] if bit == D["RDX_U"] else D["RDX_U"]):
                    v.append(f"link {r}-{nb} one-sided")
                adj[r].add(nb)
            elif col:
                v.append(f"room {r} shaft col without exit")
        arr, ec = rd(b, r, "RD_ARRCOL"), rd(b, r, "RD_EXITCOL")
        if bool(arr) != (r == start): v.append(f"room {r} arrival col presence")   # H1-D1: D1 too
        if bool(ec) != (r == lair): v.append(f"room {r} exit col presence")
        for nm, c in (("arr", arr), ("exitcol", ec)):
            if c and not SHAFT_LO <= c <= SHAFT_HI: v.append(f"room {r} {nm} range")
        l1, l2, pit = rd(b, r, "RD_LAD1"), rd(b, r, "RD_LAD2"), rd(b, r, "RD_PITCOL")
        if not l1: v.append(f"room {r} no ladder")
        for nm, c in (("lad1", l1), ("lad2", l2)):
            if c and not D["LAD_COL_MIN"] <= c <= D["LAD_COL_MAX"]: v.append(f"room {r} {nm} range")
        if not b[OFF_DESC + r * 16 + L2_PITW]:
            for pv in pit_violations(b, r): v.append(f"room {r}: {pv}")
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
        if depth != 8: return True
        return (r % 3 > 0 and r - 1 not in pset) or (r % 3 < 2 and r + 1 not in pset)
    pools = ([r for r in present if r >= 6 and deg[r] == 1 and has_h(r) and san(r)],
             [r for r in present if r >= 6 and has_h(r) and san(r)])
    pool = next((p for p in pools if p), [])
    fallback = pool is not pools[0]
    # L1 (game.md 1.1 "L1 rules"): entry on the top row, lair on the bottom row, a
    # bottom-row horizontal edge, D8 Sanctum cell reserved (lair 7, one bottom end absent)
    if start > 2: v.append(f"L1: start {start} not on the top row")
    if rd(b, start, "RD_EXITS") & D["RDX_U"] or rd(b, start, "RD_UPCOL"): v.append("L1: start has an up exit")
    if lair < 6: v.append(f"L1: lair {lair} not on the bottom row")
    if not (7 in adj.get(6, ()) or 8 in adj.get(7, ())): v.append("L1: no horizontal edge between bottom-row rooms")
    if not pools[0] and not pools[1]: v.append("L1: no lair candidate")
    if depth == 8:
        ends = [c in pset for c in (6, 8)]
        if lair != 7 or 7 not in pset or sum(ends) != 1: v.append(f"L1: D8 lair {lair} / Sanctum cell not reserved")
        if n > 8: v.append("L1: D8 rooms > 8")
    if lair not in pool: v.append("lair not in candidate pool")
    elif dist.get(lair, -1) != max(dist.get(r, 0) for r in pool): v.append("lair not farthest candidate")
    def side(r, s, col):                    # storey-0 floor divider: a pit (col p) or the mid-block (col b)
        p = rd(b, r, "RD_PITCOL") or b[OFF_DESC + r * 16 + L2_MIDB]
        return 1 if (s == 0 and p and col >= p) else 0
    def graph(walker):
        E = {}
        def link(a, c, both=True):
            E.setdefault(a, set()).add(c)
            if both: E.setdefault(c, set()).add(a)
        for r in present:
            if rd(b, r, "RD_PITCOL") and not walker and not b[OFF_DESC + r * 16 + L2_PITW]:
                link((r, 0, 0), (r, 0, 1))      # jump: ONLY across a narrow pit (I5); falls are
                                                # one-way shortcuts and never needed, so not modelled
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
    try:
        sx = G.start_x(b)
    except RuntimeError as ex_:
        v.append(str(ex_)); sx = 14
    src = (start, 0, side(start, 0, sx))
    cut = {}
    for walker in (False, True):
        E = graph(walker); reach = {src}; q = [src]
        for nd in q:
            for x in E.get(nd, ()):
                if x not in reach: reach.add(x); q.append(x)
        cut[walker] = [t for t in targets if t not in reach]
    if cut[False]: v.append(f"hero cannot reach {sorted(cut[False])}")
    # I5: walk + climb (+ narrow jumps) join EVERY (room, storey, side) node; the edges are
    # two-way, so reachability from the start is strong connectivity
    nodes = {(r, 0, 0) for r in present} | {(r, 1, 0) for r in present}
    nodes |= {(r, 0, 1) for r in present if rd(b, r, "RD_PITCOL") or b[OFF_DESC + r * 16 + L2_MIDB]}
    Eh = graph(False); reach = {src}; q = [src]
    for nd in q:
        for x in Eh.get(nd, ()):
            if x not in reach: reach.add(x); q.append(x)
    if nodes - reach: v.append(f"I5: not strongly connected by walk+climb: {sorted(nodes - reach)[:4]}")
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
        elif not item_ok(b, r, s, ent[1]): v.append(f"floor {i} illegal cell col {ent[1]} s{s}")
    if not 2 <= fn <= 3: v.append(f"potion count {fn}")
    arr0 = rd(b, start, "RD_ARRCOL")
    if depth >= 2:
        if sx != arr0 + 1: v.append(f"start x {sx} != arrival col {arr0} + 1")
    elif sx != arr0:                        # H1-D1: D1 enters mid-ladder on the arrival shaft
        v.append(f"D1 start x {sx} != arrival col {arr0}")
    if stats is not None:
        stats["pits_n"] += sum(1 for r in present if rd(b, r, "RD_PITCOL"))
    for k, nm in ((("wide pit",), "wide pits"), (("mid-block",), "mid-blocks")):
        if depth_l2.get(k, 0) > L2_ODDS_MAX: v.append(f"I2: {depth_l2[k]} {nm} on one level")
    # I3: L2 is a last pass: everything else is byte-identical to the pre-L2 block
    seed_used = int.from_bytes(b[H["LVL_SEED"]:H["LVL_SEED"] + 2], "little")
    master = int.from_bytes(b[H["MASTER_SEED"]:H["MASTER_SEED"] + 2], "little")
    pre = G.generate(depth, seed_used, master, l2=False)
    m = bytearray(b)
    for r in range(9):
        o = OFF_DESC + r * 16
        if m[o + L2_PITW] or m[o + L2_MIDB]:      # designer 2026-10-07: only L2 rooms may differ,
            m[o + D["RD_PITCOL"]] = 0             # in the narrow pit / 2nd ladder fields
            m[o + D["RD_LAD2"]] = 0
            pre_o = bytearray(pre)
            pre_o[o + D["RD_PITCOL"]] = 0
            pre_o[o + D["RD_LAD2"]] = 0
            pre = bytes(pre_o)
        m[o + L2_PITW] = m[o + L2_MIDB] = m[o + L2_MIDW] = 0
    if bytes(m) != pre: v.append("I3: pre-L2 output changed outside the L2 rooms' pit / lad2")
    if stats is not None:
        stats["l2_wide"] += sum(1 for r in present if b[OFF_DESC + r * 16 + L2_PITW])
        stats["l2_mid"] += sum(1 for r in present if b[OFF_DESC + r * 16 + L2_MIDB])
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
    v += lp_check(b, stats)
    return v


def lp_check(b, stats=None, f3=False, lvl=1):
    """LP (game.md §9.4.7 levelcheck): the budget split's quotas, then every
    room's first entry from each of its horizontal exits (the spawn rules hold:
    sum weight <= 8 / lair <= 12, count <= quota, body gap >= 8 to the arrival)."""
    v = []
    depth = b[G.H["LVL_DEPTH"]]
    st, lair = b[G.H["LVL_START"]], b[G.H["LVL_LAIR"]]
    lp = G.lp_budget(b, lvl, f3)
    wt = G.k3_weight if f3 else G.lp_wt
    kid = (lambda k: G.KROWS[k][0]) if f3 else (lambda k: D[k])      # noqa: E731
    o = lambda n: D[n] - D["LP_STATE"]                       # noqa: E731
    q = [lp[o("LP_REC") + r * D["LR_STRIDE"]] for r in range(9)]
    rmax = D["ROOM_MAX"]
    n = G.LP_TAB[depth][2] - 2
    if q[st] != 0:
        v.append(f"LP: start quota {q[st]}")
    if q[lair] != 2:
        v.append(f"LP: lair quota {q[lair]}")
    if any(q[r] > rmax for r in range(9) if r != lair):
        v.append(f"LP: quota > ROOM_MAX {q}")
    if sum(q[r] for r in range(9) if r != lair) != n:
        v.append(f"LP: sum quotas {sum(q) - 2} != N {n}")
    if lp[o("LP_DISCARD")]:
        v.append(f"LP: split discard {lp[o('LP_DISCARD')]}")
    for r in range(9):
        if not rd(b, r, "RD_FLAGS") & D["RDF_PRESENT"] or r == st:
            continue
        ex = rd(b, r, "RD_EXITS")
        arr = [(1 if ex & D["RDX_LS1"] else 0, 1)] if ex & D["RDX_L"] else []
        arr += [(1 if ex & D["RDX_RS1"] else 0, 28)] if ex & D["RDX_R"] else []
        arr += [(0, rd(b, r, "RD_UPCOL"))] if ex & D["RDX_U"] else []
        arr += [(1, rd(b, r, "RD_DNCOL"))] if ex & D["RDX_D"] else []
        for hs, hx in arr:
            lp2, out = G.lp_enter(b, lp, r, hs, hx, 3, f3)
            ws = sum(wt(kb if f3 else kb & 31) for kb, *_ in out)
            nk = lp2[o("LP_REC") + 9 * r] & D["LR_CNT_MASK"]     # ROOM-MEM: entries past the count are stale
            ws += sum(wt(e if f3 else e & 31) for e in lp2[o("LP_REC") + 9 * r + 1:o("LP_REC") + 9 * r + 1 + 2 * nk:2])
            minw = min(wt(kid(k)) for k in G.LP_TAB[depth][0])
            cap = D["LP_SIGMA_CAP"] if r == lair else max(D["LP_SIGMA_INIT"], rmax * minw)
            if lp2[o("LP_DISCARD")]:
                v.append(f"LP: room {r} lost {lp2[o('LP_DISCARD')]} unit(s) to the sum cap")
            if ws > cap or len(out) > max(q[r], 1 if r == lair else 0) + (1 if r == lair else 0):
                v.append(f"LP: room {r} spawn sum {ws} / {len(out)} units")
            for kb, hp, s, x, _ in out:
                w = (G.k3_info if f3 else G.lp_kinfo)(kb & 31)[0]
                if s == hs and not (x >= hx + 3 + 5 or x + w + 5 <= hx):
                    v.append(f"LP: room {r} spawn x{x} s{s} within 5 of the arrival x{hx}")
                # I6 (L2): nobody spawns inside / against a mid-block, on a wide pit's fall
                # columns (storey 0: holes + caps) or on its storey-1 landing columns
                pw, mb, mw = b[OFF_DESC + r * 16 + L2_PITW], b[OFF_DESC + r * 16 + L2_MIDB], b[OFF_DESC + r * 16 + L2_MIDW]
                pp = rd(b, r, "RD_PITCOL")
                if s == 0 and mb and x <= mb + mw and x + w - 1 >= mb - 1:
                    v.append(f"I6: room {r} spawn x{x} touches the mid-block {mb}/{mw}")
                if pw and ((s == 0 and x <= pp + pw and x + w - 1 >= pp - 1) or
                           (s == 1 and x <= pp + pw - 1 and x + w - 1 >= pp)):
                    v.append(f"I6: room {r} spawn s{s} x{x} on the wide pit {pp}/{pw} span")
            if stats is not None:
                stats["lp_units"] += len(out)
                stats["lp_left"] += lp2[o("LP_REC") + 9 * r] & 7
                stats["lp_lost"] += lp2[o("LP_DISCARD")]
                stats["lp_entries"] += 1
    return v


def check3(b, lvl=1, stats=None):
    """3F block (generate(..., f3=True)): the ordinary invariants, the closed grate,
    the D8 Sanctum leaf behind its sealed edge, then the 3F-mode LP checks
    (tier roll with LP_LVL = lvl, golden boss, escort at base tier)."""
    depth = b[G.H["LVL_DEPTH"]]
    lair = b[G.H["LVL_LAIR"]]
    if b[G.H["LVL_FLAGS"]] & D["LF_GRATE_OPEN"]:
        return ["3F: grate open at level start"]
    plain = bytearray(b)                    # strip the Sanctum -> must equal the plain generator
    if depth == 8:
        sc0 = b[G.H["LVL_SANCTUM"]]
        if sc0 in (6, 8):
            o = OFF_DESC + sc0 * D["RD_STRIDE"]
            plain[o:o + D["RD_STRIDE"]] = bytes(D["RD_STRIDE"])
            plain[OFF_DESC + 7 * D["RD_STRIDE"] + D["RD_EXITS"]] &= ~(D["RDX_R"] | D["RDX_RS1"]) if sc0 == 8 \
                else ~(D["RDX_L"] | D["RDX_LS1"])
            plain[OFF_EDGE + hedge(min(7, sc0))] = 0
            plain[G.H["LVL_SANCTUM"]] = D["ROOM_NONE"]
            plain[G.H["LVL_NROOMS"]] -= 1
            if b[D["TOME_HP"] - G.BASE] != D["TOME_MAX"]:
                return ["P3: D8 TOME_HP != TOME_MAX at generation"]
            plain[D["TOME_HP"] - G.BASE] = 0
    seed_used = int.from_bytes(b[G.H["LVL_SEED"]:G.H["LVL_SEED"] + 2], "little")
    master = int.from_bytes(b[G.H["MASTER_SEED"]:G.H["MASTER_SEED"] + 2], "little")
    if bytes(plain) != G.generate(depth, seed_used, master):
        return ["3F: block minus the Sanctum != the plain generator's block"]
    v = check(bytes(plain), stats)
    sc = b[G.H["LVL_SANCTUM"]]
    if depth != 8:
        if sc != D["ROOM_NONE"]:
            v.append("3F: Sanctum on a depth that has none")
    else:
        if sc not in (6, 8) or lair != 7:
            return v + [f"3F: Sanctum {sc} lair {lair}"]
        fl = rd(b, sc, "RD_FLAGS")
        if not fl & D["RDF_PRESENT"] or not fl & D["RDF_SANCTUM"] or not fl & D["RDF_DEADEND"]:
            v.append(f"3F: Sanctum room flags {fl:#04x}")
        if bin(rd(b, sc, "RD_EXITS") & (D["RDX_L"] | D["RDX_R"] | D["RDX_U"] | D["RDX_D"])).count("1") != 1:
            v.append("3F: Sanctum is not a one-exit leaf")
        e = b[OFF_EDGE + hedge(min(7, sc))]
        if e != D["EG_LINK"] | D["EG_DOOR"] | D["EG_SEAL"]:
            v.append(f"3F: Sanctum edge {e:#04x} is not a sealed link")
        if any(r != sc and rd(b, r, "RD_FLAGS") & D["RDF_SANCTUM"] for r in range(9)):
            v.append("3F: two Sanctum rooms")
        if G.lp_budget(b, lvl, True)[D["LP_REC"] - D["LP_STATE"] + sc * D["LR_STRIDE"]]:
            v.append("3F: Sanctum has a population quota")
    v += lp_check(b, stats, True, lvl)
    return v


def new_stats():
    return {"rooms": Counter(), "h_edges": 0, "doors": 0, "pits": 0, "dead": 0, "loops": 0,
            "lair_fallback": 0, "walker_cut": 0, "blocks": 0, "lad2": 0, "potions": 0,
            "pits_n": 0, "l2_wide": 0, "l2_mid": 0, "lp_units": 0, "lp_left": 0, "lp_lost": 0, "lp_entries": 0}


def merge(a, b):
    for k, v in b.items():
        if k == "rooms": a[k].update(v)
        else: a[k] += v


LP_WAIT_MAX = 0.15


def report(st, tot, fails):
    print(f"{tot - len(fails)}/{tot} pass")
    for f in fails[:10]: print("FAIL", f)
    ratio = st["doors"] / max(1, st["h_edges"])
    print("rooms", dict(sorted(st["rooms"].items())),
          f"doors {st['doors']}/{st['h_edges']} ({ratio:.3f})")
    print({k: round(st[k] / tot, 2) for k in ("pits", "dead", "loops", "lair_fallback", "walker_cut", "blocks", "lad2", "potions", "l2_wide", "l2_mid")}, "(per level)")
    u = st["lp_units"] + st["lp_left"]
    print("LP first entries:", st["lp_entries"], "units", u, "placed", st["lp_units"], "wait (no legal cell)",
          st["lp_left"], f"({100 * st['lp_left'] / max(1, u):.1f}%)", "lost to the sum cap", st["lp_lost"])
    # door odds bound: 1 in 3 per horizontal edge (game.md 1.1). Over N edges the
    # sd of the fraction is sqrt(2/9/N): 524k-level scan (~2M edges) 0.0003, the
    # 8,000-level run (~30k edges) 0.0027, so +-0.02 is > 7 sd in both.
    bad = st["h_edges"] >= 5000 and abs(ratio - DOOR_P) > DOOR_TOL
    if bad: print(f"FAIL door fraction {ratio:.3f} outside 1/3 +- {DOOR_TOL}")
    # 3F-D3-3 (game.md §9.4.3): waits (units with no legal cell) target <= 15 %
    wbad = u >= 1000 and st["lp_left"] / u > LP_WAIT_MAX
    if wbad: print(f"FAIL LP waits {100 * st['lp_left'] / u:.1f}% above {100 * LP_WAIT_MAX:.0f}%")
    return bool(fails) or bad or wbad


def _scan(args):
    """(seeds slice, depths) -> (stats, fails, maxima, exhausted)"""
    seeds, dmax = args
    st = new_stats(); fails = []; mx = {"restarts": (0,), "reseeds": (0,), "calls": (0,)}; ex = []; tot = 0
    for seed in seeds:
        for depth in range(1, dmax + 1):
            lr0 = G.LAIR_RESEEDS
            try:
                b = G.generate(depth, seed)
            except RuntimeError:
                ex.append((depth, seed)); continue
            rs, calls, rsd = G.LAST
            if G.LAIR_RESEEDS != lr0: fails.append((depth, seed, ["L1: lair reseed (no bottom-row candidate)"]))
            for k, v in (("restarts", rs), ("reseeds", rsd), ("calls", calls)):
                if v > mx[k][0]: mx[k] = (v, depth, seed)
            tot += 1
            viol = check(b, st)
            if viol: fails.append((depth, seed, viol[:3]))
    return st, fails, mx, ex, tot


def full(dmax=8):
    import time
    from multiprocessing import Pool
    t0 = time.time()
    chunks = [(range(i, min(i + 512, 65536)), dmax) for i in range(0, 65536, 512)]
    st = new_stats(); fails = []; mx = {"restarts": (0,), "reseeds": (0,), "calls": (0,)}; ex = []; tot = 0
    with Pool() as pool:
        for s2, f2, m2, e2, t2 in pool.imap_unordered(_scan, chunks):
            merge(st, s2); fails += f2; ex += e2; tot += t2
            for k in mx:
                if m2[k][0] > mx[k][0]: mx[k] = m2[k]
    print(f"full scan 65536 seeds x depths 1..{dmax}: {time.time() - t0:.0f}s")
    print("max (value, depth, seed):", mx)
    print(f"seeds exhausting the 16 reseeds: {sorted(ex)}")
    return 1 if report(st, tot, fails) else 0


def run(nseeds=1000, dmax=8):
    st = new_stats()
    fails = []
    tot = 0
    for depth in range(1, dmax + 1):
        for i in range(nseeds):
            seed = (i * 0x9E37 + depth * 0x3D) & 0xFFFF or 1
            lr0 = G.LAIR_RESEEDS
            b = G.generate(depth, seed)
            assert b == G.generate(depth, seed), "non-deterministic"
            assert G.LAIR_RESEEDS == lr0, f"L1: lair reseed d{depth} seed {seed:#06x}"
            viol = check(b, st)
            tot += 1
            if viol:
                fails.append((depth, seed, viol[:3]))
    rc = 1 if report(st, tot, fails) else 0
    return rc | run3(nseeds, dmax)


def run3(nseeds=1000, dmax=8):
    """3F pass: same seeds with f3=True. Blocks must equal the plain ones except in the D8
    Sanctum (room, lair exit bit, edge), the closed grate and the header counts."""
    fails = []
    tot = 0
    st = new_stats()
    for depth in range(1, dmax + 1):
        for i in range(nseeds):
            seed = (i * 0x9E37 + depth * 0x3D) & 0xFFFF or 1
            lr0 = G.LAIR_RESEEDS
            b = G.generate(depth, seed, f3=True)
            assert b == G.generate(depth, seed, f3=True), "non-deterministic"
            assert G.LAIR_RESEEDS == lr0, f"L1: lair reseed d{depth} seed {seed:#06x}"
            viol = check3(b, 1 + (i % 8), st)
            tot += 1
            if viol:
                fails.append((depth, seed, viol[:3]))
    print(f"3F pass (f3=True, LP_LVL cycling 1..8): {tot - len(fails)}/{tot} pass, "
          f"LP discards/lost {st['lp_lost']}")
    for f in fails[:10]:
        print("FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    a = sys.argv
    if len(a) > 1 and a[1] == "--full":
        sys.exit(full())
    sys.exit(run(int(a[1]) if len(a) > 1 else 1000, int(a[2]) if len(a) > 2 else 8))
