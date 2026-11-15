#!/usr/bin/env python3
"""levelgen.py - reference level generator for Stage 3B (B3B-6; Z80 port = B3B-7).

Produces the level-state block the Z80 holds at LVL_STATE. LARGER-D: 3 x 4 grid (12 descriptors; T4: the defs say
so, the T3 compat shim is gone). Offsets/bit values are parsed from src/level_defs.asm (never copied).

GEN_RNG (port bit-exactly)
--------------------------
16-bit xorshift (Marsaglia 7,9,8; John Metcalf's Z80 form, period 65535):
    step:  x ^= x << 7;  x ^= x >> 9;  x ^= x << 8        (16-bit, wraps)
    rnd(n) = step, then (x & $FF) mod n        (n = 1..255; L mod n by repeated
             subtraction; cold code, bias ignored)
    rnd16  = step, then x                      (room seeds)
x never becomes 0 from a non-zero start.
Seeding: GEN_RNG = LVL_SEED ^ (depth * $0101); if that is 0 it becomes 1.
LVL_SEED itself (= f(MASTER_SEED, depth)) is the caller's business (CLI SEED).
RESEED: if no lair candidate exists (see step 6) the whole generation restarts
with seed+1 (fresh GEN_RNG from the formula above), at most RESEED_MAX=16
tries; the header LVL_SEED holds the seed actually used. Under the L1 level
shape this path is unreachable (tier (b) always has a candidate: the bottom row
is always present and reached by a horizontal edge, steps 2 + 3;
LAIR_RESEEDS stays 0, tools/levelgen_runs.py checks it); it is kept as a cheap
guard, mirrored by the Z80 port.
The header stores the FINAL GEN_RNG state (after room seeds).
Call order: see the comment block at the top of attempt() (LARGER-D 3 x 4, the T4 contract). In short:
 n = 10 + rnd(3) (D8 min 11), start = rnd(3), D8 S = 9 + 2*rnd(2); DFS (done = n visited and
 10 and 9|11 visited); loop edge (mandatory when no tree edge joins 9-10 / 10-11); h-edges (storey,
 door); vertical links; arrival / exit shafts; per-room features; potions (3 + rnd(2)); room seeds.
 Lair (BFS only, no rnd): tier (a) farthest bottom-row (9..11) non-start leaf with a horizontal edge, else
 (b) farthest bottom-row room with one; ties lowest id; D8: needs a free horizontal neighbour (-> 10).
 A restart does NOT reseed.
pick_feature: up to FEAT_TRIES=8 tries of lo + rnd(hi-lo+1) accepted if
|c - f| >= FEAT_GAP for every footprint f already on the storeys it touches;
mandatory features then scan lo..hi for the first legal col; if none, the
whole level RESTARTS from step 1 (RNG continues). Optional -> dropped.
Hero start x is NOT stored (derived: start_x(block), pure function of the
descriptors, see its docstring). Block tries: side=rnd(2), storey=rnd(2), w=2+rnd(2) (8 tries).
Port notes: hardest bits are the DFS neighbour collection, BFS lair choice
and the legality test (footprint lists per storey) - all small loops, depth <= 9.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- 3F kind / tier table (game.md §9.1 roster, §9.6 tiers, §9.7 R1) ------------
# The 3F kind rows (3F-T3: the ids are the Z80's, src/defs.asm K_*, asserted below; golden
# bosses are a flag, not rows). Everything 3F in this module and in respawn_model.py
# (tier roll, escort, golden flag, respawn) reads it.
#   key           : name used by LP_TAB / the tests
#   (id, base hp (§9.1 / §9.6 stats column, before depth scaling), body cols,
#    flyer, §9.3 weight, base key or None, tier 1/2/3)
KROWS = {
    "K_RAT":        (6,   3, 4, False, 2, None,        1),    # §9.1
    "K_BAT":        (7,   3, 3, True,  2, None,        1),
    "K_SLIME":      (8,   6, 3, False, 2, None,        1),
    "K_GOBLIN":     (4,   6, 3, False, 3, None,        1),
    "K_SPIDER":     (9,   7, 4, False, 2, None,        1),
    "K_SKELETON":   (3,  10, 3, False, 5, None,        1),
    "K_VAMPIRE":    (10, 14, 3, False, 5, None,        1),
    "K_GHOST":      (5,   8, 3, True,  3, None,        1),
    "K_ORC":        (11, 14, 3, False, 5, None,        1),
    "K_ARCHER":     (12,  8, 3, False, 6, None,        1),
    "K_MUMMY":      (13, 18, 3, False, 5, None,        1),
    "K_NECRO":      (14, 12, 3, False, 6, None,        1),
    "K_OGRE":       (15, 36, 4, False, 6, None,        1),    # unique boss D4
    "K_DKNIGHT":    (16, 50, 3, False, 5, None,        1),    # unique boss D7
    "K_ARCHMAGE":   (17, 60, 3, False, 6, None,        1),    # unique boss D8
    # §9.6 tier rows, table order (hp from the stats column; a tier keeps its
    # base's body, flyer flag and weight, except the Slinger's +1)
    "K_GIANT_RAT":  (18,  5, 4, False, 2, "K_RAT",     2),
    "K_RABBIT_RAT": (19,  8, 4, False, 2, "K_RAT",     3),
    "K_SCREECH":    (20,  5, 3, True,  2, "K_BAT",     2),
    "K_SLINGER":    (21,  8, 3, False, 4, "K_GOBLIN",  2),    # weight 3 + 1
    "K_BLACK_WIDOW": (22, 10, 4, False, 2, "K_SPIDER", 2),
    "K_SKEL_GUARD": (23, 14, 3, False, 5, "K_SKELETON", 2),
    "K_SKEL_KNIGHT": (24, 18, 3, False, 5, "K_SKELETON", 3),
    "K_POLTERGEIST": (25, 11, 3, True,  3, "K_GHOST",  2),
    "K_ORC_BERSERK": (26, 18, 3, False, 5, "K_ORC",    2),
    "K_ORC_BOUNCER": (27, 24, 3, False, 5, "K_ORC",    3),
    "K_SNIPER":     (28, 10, 3, False, 6, "K_ARCHER",  2),
    "K_BONE_CALLER": (29, 14, 3, False, 6, "K_NECRO",  2),
    # NEW-MON3 (new_monsters.md §4): 30 Gargoyle; 31 = the A-1 alias row: the Fire Imp as assembled (hp 5),
    # the Frost Wraith (hp 13) on the NM3_B_DEPTHS depths (k3_hp resolves it by depth; body / flyer / weight shared)
    "K_GARGOYLE":   (30,  9, 3, True,  3, None,        1),
    "K_ALIAS":      (31,  5, 3, True,  3, None,        1),
}
# boss per depth (§8.6): (row key, golden). Golden = base row + LEK_GOLD (§9.7 R1)
BOSS3 = {1: ("K_GOBLIN", True), 2: ("K_SPIDER", True), 3: ("K_VAMPIRE", True),
         4: ("K_OGRE", False), 5: ("K_MUMMY", True), 6: ("K_NECRO", True),
         7: ("K_DKNIGHT", False), 8: ("K_ARCHMAGE", False)}
LEK_GOLD = 0x20                   # LE_KIND bit 5 (§9.7 R1; bits 0-4 row, 6 bred, 7 respawn)
LEK_BRED = 0x40
LEK_RESPAWN = 0x80
LEK_ROW_MASK = 0x1F
# §9.6 tier roll constants
T2_BASE = (None, 24, 48, 64, 72, 80, 88, 144, 144)           # index = depth (NEW-MON3 T9: D7 / D8 tuned preset)
T3_BASE = (None, 0, 0, 0, 16, 24, 32, 72, 80)
TIER3_MIN_DEPTH, TIER_SHIFT2, TIER_SHIFT3, TIER_DELTA_MAX, T2_CAP, T3_CAP = 4, 16, 8, 2, 160, 80
# 3F-T3: the Z80 ids are authoritative (src/defs.asm K_*); this table must agree with them
# (checked below once defs.asm is parsed).
# derived (do not edit): id -> key, base key -> (tier2 key, tier3 key)
K3_BY_ID = {v[0]: k for k, v in KROWS.items()}
TIERS = {}
for _k, _v in KROWS.items():
    if _v[5]:
        TIERS.setdefault(_v[5], [None, None])[_v[6] - 2] = _k

# ---- tunables (designer decision 2026-10-03) ---------------------------------
SHAFT_MIN = 5            # exit shafts (up/down/arrival/level-exit) left col 5..24
SHAFT_MAX = 24
SHAFT_N = SHAFT_MAX - SHAFT_MIN + 1
POTIONS_MIN = 3          # LARGER-D: 3 + rnd(2) potions (was 2 + rnd(2))
LOOP_EDGE_ODDS = 2       # 1 in 2
DOOR_ODDS = 3            # 1 in 3
MAX_RESTARTS = 64
PIT_MIN = 5              # pit col 5..24 (game.md 1.1 Pit geometry (1))
PIT_MAX = 24


def load_defs(paths=None):
    syms = {}
    for p in (paths or [ROOT / "src" / "defs.asm", ROOT / "src" / "level_defs.asm",
                        ROOT / "src" / "item_defs.asm"]):   # 3E-T3: IT_* moved there
        _load_one(Path(p), syms)
    return syms


def _load_one(path, syms):
    pat = re.compile(r"^([A-Z][A-Z0-9_]*)\s+EQU\s+([^;]+)")
    for line in path.read_text().splitlines():
        m = pat.match(line)
        if not m:
            continue
        expr = m.group(2).strip().replace("$", "0x")
        expr = re.sub(r"%([01]+)", lambda x: str(int(x.group(1), 2)), expr)
        try:
            syms[m.group(1)] = int(eval(expr, {}, dict(syms)))
        except Exception:
            pass                       # needs symbols we do not define


D = load_defs()                       # the defs as assembled (LARGER-D T4: 3 wide x 4 tall, larger_depths.md section 2)
# LARGER-D T4: the T3 layout shim (a forced 3 x 4 grid over 3 x 3 defs) is gone; L / LH / LOFF_* / LBASE /
# LBLOCK_LEN stay as aliases of D / H / OFF_* / BASE / BLOCK_LEN for the tools that import them.
L = D
W, GH = D["GRID_W"], D["GRID_H"]      # 3, 4: r = 3*row + col, ids 0..11
NCELL = W * GH                        # 12 room ids
BOT = W * (GH - 1)                    # first bottom-row id = 9
NEDGE_H = (W - 1) * GH                # 8 horizontal edges
assert (W, GH, NCELL, NEDGE_H) == (3, 4, D["GRID_CELLS"], D["EDGES_H"]), "levelgen: level_defs.asm grid != 3 x 4"
for _k, _v in KROWS.items():          # 3F-T3: KROWS ids == defs.asm K_* ids (the Z80 is the truth)
    if D.get(_k) != _v[0]:
        raise SystemExit(f"levelgen: KROWS {_k} id {_v[0]} != src/defs.asm {D.get(_k)}")


def sym(name):
    if name not in D:
        raise SystemExit(f"levelgen: symbol {name} missing/unparsed in level_defs.asm / item_defs.asm")
    return D[name]


NEEDED = """RD_FLAGS RD_EXITS RD_UPCOL RD_DNCOL RD_ARRCOL RD_EXITCOL RD_LAD1 RD_LAD2
RD_PITCOL RD_BLOCK RD_SEED RD_SPARE RD_STRIDE RDF_PRESENT RDF_START RDF_LAIR
RDF_DEADEND RDX_L RDX_R RDX_U RDX_D RDX_LS1 RDX_RS1 RDB_WMASK RDB_S1 RDB_RIGHT
EG_LINK EG_DOOR FLOOR_MAX FL_STRIDE FL_ROOM FL_COL FL_ITEM FL_QTY FL_S1 FL_EMPTY
IT_POTION LVL_STATE LVL_DEPTH LVL_SEED GEN_RNG LVL_ATTR_FLOOR LVL_ATTR_WALL LVL_START
LVL_LAIR LVL_KEYROOM LVL_SANCTUM LVL_NROOMS LVL_FLAGS FLOOR_N MASTER_SEED EDGE_TAB
ROOM_DESC FLOOR_LIST LVL_STATE_END ROOM_NONE LF_GRATE_OPEN FEAT_W FEAT_GAP LAD_COL_MIN
LAD_COL_MAX FEAT_TRIES EDGES_H GRID_CELLS EG_SEAL RDF_SANCTUM TOME_HP TOME_MAX""".split()
for _n in NEEDED:
    sym(_n)

BASE = D["LVL_STATE"]
BLOCK_LEN = D["LVL_STATE_END"] - BASE
OFF_EDGE = D["EDGE_TAB"] - BASE
OFF_DESC = D["ROOM_DESC"] - BASE
OFF_FLOOR = D["FLOOR_LIST"] - BASE
H = {k: D[k] - BASE for k in ("LVL_DEPTH LVL_SEED GEN_RNG LVL_ATTR_FLOOR LVL_ATTR_WALL "
     "LVL_START LVL_LAIR LVL_KEYROOM LVL_SANCTUM LVL_NROOMS LVL_FLAGS FLOOR_N MASTER_SEED").split()}

LBASE, LBLOCK_LEN, LOFF_EDGE, LOFF_DESC, LOFF_FLOOR, LH = BASE, BLOCK_LEN, OFF_EDGE, OFF_DESC, OFF_FLOOR, H
LOFF_KEYROOM2 = D["LVL_KEYROOM2"] - BASE   # LARGER-D T4: $6EAE (the T2 spare after TRAP_N): colour-1 key room, ROOM_NONE if unused
EG_LOCKC = D["EG_LOCKC"]                  # LARGER-D T4: $20, lock colour 1 (EG_LOCK set; clear = colour 0)


ATTRS = {1: (0x0F, 0x01), 2: (0x27, 0x04), 3: (0x17, 0x02), 4: (0x28, 0x05),
         5: (0x30, 0x06), 6: (0x38, 0x07), 7: (0x4F, 0x41), 8: (0x1F, 0x03)}


class Rng:
    def __init__(self, seed, depth):
        s = (seed ^ (depth * 0x0101)) & 0xFFFF
        self.x = s or 1
        self.calls = 0           # rnd()/rnd16 calls (Z80 time budget stat)

    def step(self):
        x = self.x
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        self.x = x
        return x

    def rnd(self, n):
        self.calls += 1
        return (self.step() & 0xFF) % n

    def rnd16(self):
        self.calls += 1
        return self.step()

    def byte(self):
        """one step, low byte: the 0..255 tier / chance roll (no modulo)"""
        self.calls += 1
        return self.step() & 0xFF


LAIR_RESEEDS = 0            # L1: times no lair candidate existed (must stay 0)
LAST = (0, 0, 0)            # (restarts, rnd calls, reseeds) of the last generate()


# ---- L2 (game.md 1.1 "Mid-room block" / "Wide pit"): a LAST pass ------------------
# Descriptor fields in the RD_SPARE bytes (level_defs.asm): L2_PITW = wide-pit width W
# (4..6; 0 = RD_PITCOL is the ordinary 3-col pit), L2_MIDB = mid-block left col b
# (0 = none), L2_MIDW = its width w (2..3). RD_SPARE+3 stays 0.
L2_PITW = sym("L2_PITW")
L2_MIDB = sym("L2_MIDB")
L2_MIDW = sym("L2_MIDW")
# tuned on a 300-seed sweep (per level: mid-block / wide pit): D2-3 0.22 / 0.09, D4-8 ~0.65 / ~0.30
# (wide = 1 in 1: every eligible room tries; the geometry, not the odds, caps it near 0.3)
L2_ODDS_W = {2: 4, 3: 4, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1}        # wide pit: 1 in N per room; none on D1
L2_ODDS_M = {2: 8, 3: 8, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2}        # mid-block
L2_MAX = 3                                                     # per feature per level (LARGER-D: was 2)


class Room:
    def __init__(self):
        self.present = False
        self.start = self.lair = self.dead = self.sanct = False
        self.exits = 0
        self.up = self.dn = self.arr = self.exitcol = 0
        self.lad1 = self.lad2 = self.pit = self.block = 0
        self.seed = 0
        self.pitw = self.midb = self.midw = 0

    def fps(self, s):
        if s == 0:
            return [f for f in (self.up, self.arr, self.lad1, self.lad2, self.pit) if f]
        return [f for f in (self.dn, self.exitcol, self.lad1, self.lad2) if f]


def legal(room, c, storeys):
    return all(abs(c - f) >= L["FEAT_GAP"] for s in storeys for f in room.fps(s))


class Restart(Exception):
    pass


class Reseed(Exception):
    pass


RESEED_MAX = 16
SANCTUM_CELL_RULE = True    # D8: lair needs a free horizontal neighbour cell


def pick_feature(rng, room, lo, hi, storeys, mandatory):
    for _ in range(L["FEAT_TRIES"]):
        c = lo + rng.rnd(hi - lo + 1)
        if legal(room, c, storeys):
            return c
    if mandatory:
        for c in range(lo, hi + 1):
            if legal(room, c, storeys):
                return c
        raise Restart
    return 0


def nbrs(r):
    gx, gy = r % W, r // W
    out = []
    if gx > 0: out.append(r - 1)
    if gx < W - 1: out.append(r + 1)
    if gy > 0: out.append(r - W)
    if gy < GH - 1: out.append(r + W)
    return out


def hedge(r):                      # EDGE_TAB index of the edge between r and r+1
    return r - r // 3


def block_hits(room, s, side_right, w):
    """block (cols 0..w-1 / 32-w..31, rubble w / 31-w) vs features on storey s"""
    lo, hi = (32 - w - 1, 31) if side_right else (0, w)
    spans = [(f, f + 2) for f in room.fps(s)]
    if s == 0 and room.pit:
        spans.append((room.pit - 1, room.pit + 3))
    return any(not (b < lo or a > hi) for a, b in spans)


def item_col_ok(room, s, col):
    for f in room.fps(s):
        if f <= col <= f + 2:
            return False
    if s == 0 and room.pit and room.pit - 1 <= col <= room.pit + 3:
        return False
    if room.block and ((room.block >> 6) & 1) == s:
        w = room.block & L["RDB_WMASK"]
        if room.block & L["RDB_RIGHT"]:
            if col >= 31 - w:
                return False
        elif col <= w:
            return False
    return 2 <= col <= 29


def l2_clear(room, mask_cols, x, lft, wd, rgt):
    """every footprint f of `mask_cols` keeps f+lft <= x or f >= x+wd+rgt"""
    return all(f + lft <= x or f >= x + wd + rgt for f in mask_cols if f)


def l2_items(floor, r, lo, hi):
    return any(e[0] == r and lo <= e[1] <= hi for e in floor)          # storey-0 items


def l2_pass(rng, rooms, floor, depth, start, lair):
    """L2 (designer 2026-10-07): per non-start/lair room in id order, wide pit
    first, else mid-block. A narrow pit is removed while trying (restored on
    failure); a 1-ladder room gets a 2nd ladder at a seeded col per try (3..26,
    FEAT_GAP both storeys, no item under it, not on an edge block), kept only
    if the feature fits. 8 tries; W / w, the ladder col, then p / b are rolled
    in that order every try."""
    odds = (L2_ODDS_W.get(depth, 0), L2_ODDS_M.get(depth, 0))
    if not (odds[0] or odds[1]):
        return
    cnt = [0, 0]
    for r in range(NCELL):
        rm = rooms[r]
        if not rm.present or r == start or r == lair:
            continue
        for kind in (0, 1):                                    # 0 wide pit, 1 mid-block
            if rm.pitw or rm.midb:
                break
            if cnt[kind] >= L2_MAX or not odds[kind] or rng.rnd(odds[kind]):
                continue
            n_w, base, lft, rgt = ((3, 4, 7, 4), (2, 2, 6, 3))[kind]
            pit0 = rm.pit
            rm.pit = 0                                         # a narrow pit makes way
            for _ in range(L["FEAT_TRIES"]):
                W = base + rng.rnd(n_w)
                new = 0
                if not rm.lad2:                                # add the missing 2nd ladder
                    n = L["LAD_COL_MIN"] + rng.rnd(L["LAD_COL_MAX"] - L["LAD_COL_MIN"] + 1)
                    if not legal(rm, n, (0, 1)) or any((e[0] & 15) == r and n <= e[1] <= n + 2 for e in floor):
                        continue
                    if rm.block:
                        bw = rm.block & L["RDB_WMASK"]
                        blo, bhi = (31 - bw, 31) if rm.block & L["RDB_RIGHT"] else (0, bw)
                        if not (n + 2 < blo or n > bhi):
                            continue
                    new = n
                c1, c2 = min(rm.lad1, rm.lad2 or new), max(rm.lad1, rm.lad2 or new)
                lo, hi = c1 + lft, c2 - W - rgt
                if hi < lo:
                    continue
                p = lo + rng.rnd(hi - lo + 1)
                cols = (rm.up, rm.dn, rm.arr, rm.exitcol) if kind == 0 else (rm.up, rm.arr)
                if l2_clear(rm, cols, p, lft, W, rgt) and not l2_items(floor, r, p - 1, p + W):
                    if new:
                        rm.lad2 = new
                    if kind == 0:
                        rm.pit, rm.pitw = p, W
                    else:
                        rm.midb, rm.midw = p, W
                    cnt[kind] += 1
                    break
            else:
                rm.pit = pit0


KEY_STATS = {"krestart": 0, "restart": 0, "last": None, "p2": False}   # KEY sweep stats: pass-1 failures (this process), last (locks, keys, F)


BRANCH_ODDS = 4            # rev 3 step (3): pass 1 branch draw b = rnd(4); pass 2 uses BRANCH_ODDS2
BRANCH_ODDS2 = 2


def tree_pass(rng, depth, n, start, odds):
    """Draws 3-5b of the attempt() contract: S, DFS (with the rev 3 branch draw), the mandatory loop (5a), then the lair
    on G5a (5b, no draw). The optional loop (5c) and everything after it run in attempt()."""
    sanct = BOT + 2 * rng.rnd(2) if depth == 8 else None    # L1 (5): never visited
    adj = {r: set() for r in range(NCELL)}
    visited = {start}
    stack = [start]

    def done():                         # L1 (3): n rooms AND two adjacent bottom cells
        return len(visited) >= n and BOT + 1 in visited and (BOT in visited or BOT + 2 in visited)

    def free_of(c):
        return [x for x in nbrs(c) if x not in visited and x != sanct]
    while stack and not done():
        cur = stack[-1]
        if len(stack) >= 4 and rng.rnd(odds) == 0 and free_of(stack[2]):
            cur = stack[2]              # branch: grow from the third cell of the path
        free = free_of(cur)
        if not free:
            stack.pop()                 # cur is the top here (the branch needs a free neighbour): no draw
            continue
        nx = free[rng.rnd(len(free))]
        adj[cur].add(nx); adj[nx].add(cur)
        visited.add(nx)
        stack.append(nx)
    # 5a: the mandatory loop (L1 (4)): no tree edge joins two bottom-row rooms -> pick over the bottom pairs
    mand = not (BOT + 1 in adj[BOT] or BOT + 2 in adj[BOT + 1])
    if mand:
        cand = loop_cands(adj, visited, True)
        if cand:
            a_, b_ = cand[rng.rnd(len(cand))]
            adj[a_].add(b_); adj[b_].add(a_)
    # 5b: lair on G5a (BFS only)
    dist = {start: 0}
    q = [start]
    for r in q:
        for x in sorted(adj[r]):
            if x not in dist:
                dist[x] = dist[r] + 1
                q.append(x)

    def has_h(r):
        return (r % W > 0 and r - 1 in adj[r]) or (r % W < W - 1 and r + 1 in adj[r])
    leaves = [r for r in visited if len(adj[r]) == 1]

    def sanctum_ok(r):
        if depth != 8 or not SANCTUM_CELL_RULE:
            return True
        gx = r % W
        return (gx > 0 and r - 1 not in visited) or (gx < W - 1 and r + 1 not in visited)
    lair = None
    for pool in ([r for r in leaves if r >= BOT and has_h(r) and sanctum_ok(r)],     # L1 (6): bottom row
                 [r for r in visited if r >= BOT and has_h(r) and sanctum_ok(r)]):
        if pool:
            lair = max(pool, key=lambda r: (dist[r], -r))
            break
    if lair is None:
        global LAIR_RESEEDS
        LAIR_RESEEDS += 1
        raise Reseed
    return adj, visited, sanct, lair, mand


def loop_cands(adj, visited, mand):
    cand = []
    for r in (range(BOT, NCELL) if mand else range(NCELL)):
        if r not in visited:
            continue
        if r % W < W - 1 and r + 1 in visited and r + 1 not in adj[r]:
            cand.append((r, r + 1))
        if r // W < GH - 1 and r + W in visited and r + W not in adj[r]:
            cand.append((r, r + W))
    return cand


def _bfs_par(adj, src, banned=None):
    """BFS over G in sorted-neighbour order; parent = first discoverer (the deterministic shortest path)."""
    par = {src: None}
    q = [src]
    for r in q:
        for x in sorted(adj[r]):
            if x not in par and (banned is None or (r, x) not in banned):
                par[x] = r
                q.append(x)
    return par


def _path(par, dst):
    out = []
    while dst is not None:
        out.append(dst)
        dst = par[dst]
    return out[::-1]


FAR_BOLT = True        # larger_depths.md 2.1 rev 2: a lock bars only its start side; from the far side it opens keyless


def _lock_arcs(locks, open_):
    """Directed arcs the unopened locks forbid: near -> far always, far -> near too unless FAR_BOLT."""
    out = set()
    for i, (near, far) in enumerate(locks):
        if i not in open_:
            out.add((near, far))
            if not FAR_BOLT:
                out.add((far, near))
    return out


def _key_fix(adj, start, locks, keyrooms, walled=None):
    """Key-set fixpoint (rev 2 proof). Returns (reach, rounds {lock: round it opened}). Coloured keys are never wasted,
    so the outcome does not depend on collection order. `walled` lock never opens."""
    open_ = set()
    rounds = {}
    rnd = 0
    while True:
        rnd += 1
        reach = _bfs_par(adj, start, _lock_arcs(locks, open_))
        new = {i for i, (near, far) in enumerate(locks)
               if i not in open_ and i != walled and near in reach and keyrooms[i] in reach}
        if not new:
            return reach, rounds
        for i in new:
            rounds[i] = rnd
        open_ |= new


def _route_f(adj, start, lair, locks, keyrooms):
    """F: min over the valid collection orders of the distinct rooms on the legs start -> key -> (key ->) lair; a lock
    whose key is not yet held is a wall (arcs as _lock_arcs). None if no order is valid."""
    from itertools import permutations
    best = None
    for perm in permutations(range(len(locks))):
        held = set()
        cur = start
        used = {start}
        ok = True
        for j in list(perm) + [None]:
            tgt = lair if j is None else keyrooms[j]
            par = _bfs_par(adj, cur, _lock_arcs(locks, held))
            if tgt not in par:
                ok = False
                break
            used.update(_path(par, tgt))
            cur = tgt
            if j is not None:
                held.add(j)
        if ok and (best is None or len(used) < best):
            best = len(used)
    return best


DEAD_PREF = True       # rev 3 key best(): prefer dead ends (ladder step 2 drops it)
LAIR_PEN = 2           # score - LAIR_PEN when a lock stands on the lair door (ladder step 3: 3)
NL_BONUS = 1           # score + NL_BONUS for a non-linear (b1 / b2) pair (ladder step 3: 2)


def select_keys(adj, start, lair, n, depth, final=False):
    """KEY placement rule (larger_depths.md 2.1 rev 3). PLUGGABLE: LOCK_SELECT. Draws NO rnd (pure function of G5a =
    the tree plus the mandatory loop). Returns (locks, keys, F, shape) or None. locks = [(near, far, colour)]
    (near = start-side room), keys = [(room, colour)], shape in one / lin / b1 / b2.
    Locks: horizontal bridges of G5a; a single lock must be on P. Keys: best(X) = the room of X (never start / lair)
    maximising (dead end, BFS distance from the lock's near room in G5a minus that lock, -id). One lock: X = near(j).
    A pair (i, j): lock j's candidates are best(near(j) & far(i)) and best(near(j) - far(i)) (each if non-empty),
    likewise lock i, <= 4 combos with distinct rooms. Valid iff the fixpoint reaches the lair and every lock is needed.
    F = _route_f; score = F + NL_BONUS (b1: exactly one lock on P; b2: both on P and both keys in C0)
    - LAIR_PEN (a lock on the lair door). Best = max (score, F), then max non-linear, then min (nearer lock's P index,
    edge indices, key ids by colour). Floor F >= n - 4 (raw): 2 locks only if depth >= 4 and n >= 11 and a pair meets
    it, else 1. Pass 1 with no floor-meeting set -> None; final (pass 2): no floor, the best valid set (pair if
    allowed and any exists), else None (the caller Restarts)."""
    par = _bfs_par(adj, start)
    P = _path(par, lair)
    pidx = {r: i for i, r in enumerate(P)}
    pe = {frozenset(e) for e in zip(P, P[1:])}
    cands = []                                    # (edge idx, near, far, onP, pi, near set, far set)
    for r in sorted(adj):
        x = r + 1
        if r % W < W - 1 and x in adj[r]:
            p2 = _bfs_par(adj, start, {(r, x), (x, r)})
            if len(p2) < len(par):                # bridge of G5a
                near, far = (r, x) if r in p2 else (x, r)
                onp = frozenset((r, x)) in pe
                if onp:
                    pi = min(pidx[r], pidx[x])
                else:                             # the P room nearest the branch (lowest P index on ties)
                    dist = {near: 0}
                    q = [near]
                    for u in q:
                        for v in sorted(adj[u]):
                            if v not in dist:
                                dist[v] = dist[u] + 1
                                q.append(v)
                    pi = min((dist[p], pidx[p]) for p in P)[1]
                ns = set(p2)
                cands.append((hedge(r), near, far, onp, pi, ns, set(adj) - ns))
    cands = [c for c in cands if True]
    pair_ok = depth >= 4 and n >= 11
    best = {1: [], 2: []}                         # lists of (sortkey, result)

    def bestkey(c, X):
        if not X:
            return None
        dist = {c[1]: 0}                          # BFS in G5a - e_j from the near room
        q = [c[1]]
        for u in q:
            for v in sorted(adj[u]):
                if v not in dist and {u, v} != {c[1], c[2]}:
                    dist[v] = dist[u] + 1
                    q.append(v)
        pool = [r for r in X if r != start and r != lair and r in dist]
        if not pool:
            return None
        return max(pool, key=lambda r: (len(adj[r]) == 1 if DEAD_PREF else 0, dist[r], -r))

    def consider(sel, ks):
        locks = [(c[1], c[2]) for c in sel]
        reach, rounds = _key_fix(adj, start, locks, ks)
        if lair not in reach:
            return
        for j in range(len(locks)):
            if lair in _key_fix(adj, start, locks, ks, walled=j)[0]:
                return                            # lock j is not needed
        F = _route_f(adj, start, lair, locks, ks)
        if F is None:
            return
        nl = 0
        shape = "one"
        if len(sel) == 2:
            onp = [c[3] for c in sel]
            if onp[0] != onp[1]:
                nl, shape = 1, "b1"
            else:
                c0 = _bfs_par(adj, start, _lock_arcs(locks, set()) | {(f, nr) for nr, f in locks})
                nl, shape = (1, "b2") if all(k in c0 for k in ks) else (0, "lin")
        # colours: the lock opened in the earlier round gets 0; a tie goes to the lower P index
        order = sorted(range(len(sel)), key=lambda j: (rounds[j], sel[j][4], sel[j][0]))
        col = {j: c for c, j in enumerate(order)}
        score = F + NL_BONUS * nl - (LAIR_PEN if any(lair in (c[1], c[2]) for c in sel) else 0)
        pi_min = min(c[4] for c in sel)
        kbycol = tuple(ks[j] for j in order)
        key = (-score, -F, -nl, pi_min, tuple(sorted(c[0] for c in sel)), kbycol)
        res = ([(sel[j][1], sel[j][2], col[j]) for j in range(len(sel))],
               sorted(((ks[j], col[j]) for j in range(len(sel))), key=lambda t: t[1]), F, shape)
        best[len(sel)].append((key, res))
    for c in cands:
        if c[3]:                                  # a single lock must be on P (else not needed)
            k = bestkey(c, c[5])
            if k is not None:
                consider([c], [k])
    if pair_ok:
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                ci, cj = cands[i], cands[j]
                ki = {bestkey(ci, ci[5] & cj[6]), bestkey(ci, ci[5] - cj[6])} - {None}
                kj = {bestkey(cj, cj[5] & ci[6]), bestkey(cj, cj[5] - ci[6])} - {None}
                for a_ in sorted(ki):
                    for b_ in sorted(kj):
                        if a_ != b_:
                            consider([ci, cj], [a_, b_])
    floor = n - KEY_FMIN_SLACK
    for m in (2, 1):
        pool = [t for t in best[m] if t[1][2] >= floor]
        if pool:
            return min(pool, key=lambda t: t[0])[1]
    if final:
        for m in (2, 1):
            if best[m]:
                return min(best[m], key=lambda t: t[0])[1]
    return None


KEY_FMIN_SLACK = 4                          # F_min = n - 4
LOCK_SELECT = select_keys                 # swap to change the placement rule; the proof/output do not care


def attempt(rng, depth, l2=True):
    """One generation attempt (LARGER-D 3 wide x 4 tall; docs/design/larger_depths.md section 2).
    THE T4 CONTRACT: the Z80 generator (src/levelgen.asm) must make exactly these GEN_RNG draws in
    exactly this order. rnd(n) = step, (x & $FF) mod n; rnd16 = step, x. A Restart (Restart exception)
    re-enters from draw 1 WITHOUT reseeding (the stream continues). Ids: r = 3*row + col, 0..11,
    bottom row 9..11. Draws:
      1. n      = 10 + rnd(3)               ; D8: n = min(n, 11)
      2. start  = rnd(3)                    ; top row
      3. D8 only: S = 9 + 2*rnd(2)          ; Sanctum cell (9 or 11), never entered by the DFS
      4. DFS from start, `while stack and not done` (REV 3): at the top of each iteration with len(stack) >= 4 draw
         b = rnd(BRANCH_ODDS) (4 in pass 1, 2 in pass 2) BEFORE the neighbour scan (also on iterations that end in a pop);
         cur = stack[2] if b == 0 and stack[2] has a free neighbour else stack[-1]. Free = L, R, U, D neighbours
         unvisited and != S, k of them: k == 0 pops with NO further draw; else pick = rnd(k), link, push (on top).
         done = |visited| >= n and 10 in visited and (9 or 11 in visited)   (D8: S is never visited,
         so it needs 10 and the other end)
      5a. mandatory loop: mand = no tree edge 9-10 and none 10-11. If mand: candidates = unlinked present bottom pairs,
         scanning r = 9..11 (right pair (r, r+1) if col < 2, then down pair is impossible); if any: pick = rnd(count)
         (also when count == 1), link. No odds draw.
      5b. lair (BFS tiers, on G5a = tree + the mandatory loop): NO draw; then LOCK_SELECT (select_keys): NO draw.
         None in pass 1 -> pass 2 = draws 3, 4, 5a rerun (n and start kept; S redrawn; BRANCH_ODDS2) continuing GEN_RNG.
         None in pass 2 -> Restart (from draw 1, pass 1; no reseed). So every level has locks and keys.
      5c. optional loop (only when not mand): odds = rnd(2), loop iff 0. When looping: candidates = unlinked present
         pairs, scanning r = 0..11 (right pair if col < 2, then down pair if row < 3), KEEPING only pairs whose two rooms
         are on the same side of every chosen lock; if count >= 1: pick = rnd(count); count == 0 -> no pick draw.
      6. horizontal edges, e in r order r = 0..11 (col < 2, r present, edge linked): storey = rnd(2),
         then door = rnd(3) (door iff 0)                                    [2 draws per edge]
      7. vertical links, r = 0..8 with r+3 linked to r: col = 5 + rnd(20)   [1 draw per link]
      8. lair (BFS) and the D8 free-side rule: NO draw. Arrival col of start: pick_feature(5..24, storey 0,
         mandatory); then the level-exit col of the lair: pick_feature(5..24, storey 1, mandatory)
         (pick_feature: up to FEAT_TRIES=8 draws of lo + rnd(hi-lo+1), stops at the first legal one;
         mandatory + none legal -> NO more draws: linear scan lo..hi, else Restart)
      9. per present room r = 0..11 (id order): LAD1 = pick_feature(LAD_COL_MIN..MAX, both storeys, mandatory);
         then `rnd(2) == 0` -> PIT = pick_feature(5..24, both, optional); `rnd(2) == 0` -> LAD2 =
         pick_feature(LAD, both, optional); `rnd(2) == 0` -> BLOCK: (none, no draw, in the start / lair
         room) else up to 8 tries of right = rnd(2), storey = rnd(2), w = 2 + rnd(2) (3 draws, always)
     10. potions: total = 3 + rnd(2) draws (rnd(2) FIRST, k = 0..total-1): per potion room =
         cands[rnd(len)] (cands = present non-start rooms in id order), storey = rnd(2), then up to 32
         (k < 3) / 8 (k == 3, dropped on failure) tries of col = 2 + rnd(28); k < 3 failing -> Restart
         (the Sanctum does not exist yet here: it is added after generation)
     11. room seeds, present rooms in id order: rnd16.     <- the header keeps GEN_RNG here
     12. L2 (after the header snapshot, GEN_RNG restored afterwards): see l2_pass.
    KEY (larger_depths.md 2.1 rev 2) adds NO draw of its own. Draws 3-8 form a PASS: after the lair is known (end of the
    pass, before the arrival-shaft picks) LOCK_SELECT = select_keys(adj, start, lair, n_visited, depth, final) picks locks
    and keys with no rnd. If it returns None (no valid set, or none with raw F >= n - 4) and this was pass 1, GEN_RNG simply
    CONTINUES and pass 2 reruns draws 3-5b (n and start are KEPT, not redrawn; S IS redrawn) with BRANCH_ODDS2 (rev 3: Warnsdorff
    dropped). Pass 2 passes final=True: no F floor, the best valid set is taken, else a full Restart (rev 3). A Restart
    (pick_feature / potions) still re-enters from draw 1 with pass 1. Outputs: edges[hedge(min)] |= EG_LOCK | EG_DOOR
    (| EG_LOCKC for colour 1); LVL_KEYROOM = colour-0 key room, LVL_KEYROOM2 ($6EAE) = colour-1, ROOM_NONE.
    Z80: src/levelgen.asm attempt + src/lgkey.asm ksel (LARGER-D T4, bit-exact: tests/levelgen_z80.py).
    The D8 Sanctum leaf runs afterwards on its own stream (sanctum_pass, SANCT_SALT): no GEN_RNG draw."""
    n = 10 + rng.rnd(3)
    if depth == 8:
        n = min(n, 11)                  # L1 (2): the Sanctum cell is reserved
    start = rng.rnd(3)                  # L1 (1): top grid row, nothing above it
    for warns in (False, True):         # KEY: pass 1 (BRANCH_ODDS); pass 2 (BRANCH_ODDS2) = draws 3-5b rerun in-stream
        adj, visited, sanct, lair, mand = tree_pass(rng, depth, n, start, BRANCH_ODDS2 if warns else BRANCH_ODDS)
        keyset = LOCK_SELECT(adj, start, lair, len(visited), depth, warns)
        if keyset:
            break
        if warns:
            KEY_STATS["krestart"] += 1  # pass 2 has no valid set: full Restart from draw 1 (keyless = 0 by construction)
            raise Restart
        KEY_STATS["restart"] += 1
    KEY_STATS["p2"] = warns
    KEY_STATS["shape"] = keyset[3]
    KEY_STATS["last"] = keyset
    locks, keys = keyset[0], keyset[1]
    # 5c: optional loop; candidate pairs must be on the same side of every lock (never bypasses or erases a bridge)
    if not mand and rng.rnd(LOOP_EDGE_ODDS) == 0:
        nears = [set(_bfs_par(adj, start, {(a_, b_), (b_, a_)})) for a_, b_, _ in locks]
        cand = [(x, y) for x, y in loop_cands(adj, visited, False) if all((x in nr) == (y in nr) for nr in nears)]
        if cand:
            x, y = cand[rng.rnd(len(cand))]
            adj[x].add(y); adj[y].add(x)
    rooms = [Room() for _ in range(NCELL)]
    edges = [0] * NEDGE_H
    for r in visited:
        rooms[r].present = True
    # horizontal edges
    for r in range(NCELL):
        if r % W < W - 1 and r in visited and r + 1 in adj[r]:
            s_ = rng.rnd(2)
            door = rng.rnd(DOOR_ODDS) == 0
            edges[hedge(r)] = L["EG_LINK"] | (L["EG_DOOR"] if door else 0)
            rooms[r].exits |= L["RDX_R"] | (L["RDX_RS1"] if s_ else 0)
            rooms[r + 1].exits |= L["RDX_L"] | (L["RDX_LS1"] if s_ else 0)
    # vertical links
    for r in range(BOT):                # r + 3 <= 11: the `cp 9` vertical-link bound of the Z80
        if r in visited and r + 3 in adj[r]:
            c = SHAFT_MIN + rng.rnd(SHAFT_N)
            rooms[r].dn = c; rooms[r].exits |= L["RDX_D"]
            rooms[r + 3].up = c; rooms[r + 3].exits |= L["RDX_U"]
    leaves = [r for r in visited if len(adj[r]) == 1]
    for a_, b_, col in locks:           # LOCKed edges are doors (clearing EG_LOCK on unlock leaves the open door)
        edges[hedge(min(a_, b_))] |= L["EG_LOCK"] | L["EG_DOOR"] | (EG_LOCKC if col else 0)
    rooms[start].start = True
    rooms[lair].lair = True
    for r in leaves:
        rooms[r].dead = True
    # exits: arrival shaft (H1-D1, user 2026-11-05: every depth, D1 too), level exit
    rm = rooms[start]
    rm.arr = pick_feature(rng, rm, SHAFT_MIN, SHAFT_MAX, (0,), True)
    rm = rooms[lair]
    rm.exitcol = pick_feature(rng, rm, SHAFT_MIN, SHAFT_MAX, (1,), True)
    # in-room features
    for r in sorted(visited):
        rm = rooms[r]
        rm.lad1 = pick_feature(rng, rm, L["LAD_COL_MIN"], L["LAD_COL_MAX"], (0, 1), True)
        if rng.rnd(2) == 0:
            rm.pit = pick_feature(rng, rm, PIT_MIN, PIT_MAX, (0, 1), False)   # pit geometry (1),(4)
        if rng.rnd(2) == 0:
            rm.lad2 = pick_feature(rng, rm, L["LAD_COL_MIN"], L["LAD_COL_MAX"], (0, 1), False)
        if rng.rnd(2) == 0:
            for _ in range(0 if (r == start or r == lair) else L["FEAT_TRIES"]):
                right = rng.rnd(2); s = rng.rnd(2); w = 2 + rng.rnd(2)
                bit = (L["RDX_R"], L["RDX_RS1"]) if right else (L["RDX_L"], L["RDX_LS1"])
                if rm.exits & bit[0]:        # the side must have no exit at all
                    continue
                if rm.pit and ((rm.pit > 25 - w) if right else (rm.pit < w + 4)):
                    continue                 # pit geometry (3)/(4): keep the jump / landing zone
                if block_hits(rm, s, right, w):
                    continue
                rm.block = w | (L["RDB_S1"] if s else 0) | (L["RDB_RIGHT"] if right else 0)
                break
    # potions
    floor = []
    cands = sorted(r for r in visited if r != start)
    for k in range(POTIONS_MIN + rng.rnd(2)):
        r = cands[rng.rnd(len(cands))]
        s = rng.rnd(2)
        for _ in range(32 if k < POTIONS_MIN else L["FEAT_TRIES"]):
            col = 2 + rng.rnd(28)
            if item_col_ok(rooms[r], s, col):
                floor.append((r | (L["FL_S1"] if s else 0), col, L["IT_POTION"], 1))
                break
        else:
            if k < POTIONS_MIN:
                raise Restart
    for r in sorted(visited):
        rooms[r].seed = rng.rnd16()
    if l2:
        x0 = rng.x                       # the header keeps the pre-L2 GEN_RNG: LP budgets
        l2_pass(rng, rooms, floor, depth, start, lair)     # (and all earlier output) unchanged
        rng.x = x0
    return rooms, edges, floor, start, lair, len(visited), keys


SANCT_SALT = 0x5A17     # 3F: the Sanctum leaf's own stream (GEN_RNG and every earlier output untouched)


def sanctum_pass(rooms, edges, seed, lair):
    """3F D8 (game.md §1.1 L1 (5), 'D8 Sanctum'): the reserved bottom-row end
    cell S (the one of 6/8 the DFS never entered) becomes a leaf room hanging
    off the lair's free side behind a SEALED edge (EG_LINK|EG_DOOR|EG_SEAL; it
    opens on the Archmage's death, LF_SEAL_OPEN). Own Rng stream: edge storey,
    one ladder column, room seed. Returns S. Items/traps/L2 never see it."""
    sc = [c for c in (BOT, BOT + 2) if not rooms[c].present]
    assert len(sc) == 1 and lair == BOT + 1, "D8 Sanctum rule (L1 (5)) broken"
    S = sc[0]
    rng = Rng(seed ^ SANCT_SALT, 8)
    s = rng.rnd(2)
    rm = rooms[S]
    rm.present = rm.dead = rm.sanct = True
    lo = min(BOT + 1, S)                # the left room of the Sanctum pair
    rooms[lo].exits |= L["RDX_R"] | (L["RDX_RS1"] if s else 0)
    rooms[lo + 1].exits |= L["RDX_L"] | (L["RDX_LS1"] if s else 0)
    edges[hedge(lo)] = L["EG_LINK"] | L["EG_DOOR"] | L["EG_SEAL"]
    rm.lad1 = pick_feature(rng, rm, L["LAD_COL_MIN"], L["LAD_COL_MAX"], (0, 1), True)
    rm.seed = rng.rnd16()
    return S


def generate(depth, seed, master=0, l2=True, f3=False):
    global LAST
    restarts = reseeds = calls = 0
    for k in range(RESEED_MAX):
        rng = Rng(seed + k, depth)
        try:
            for _ in range(MAX_RESTARTS):
                try:
                    rooms, edges, floor, start, lair, n, keys = attempt(rng, depth, l2)
                    break
                except Restart:
                    restarts += 1
            else:
                raise Reseed            # restart cap hit: same as no lair -> seed+1
            break
        except Reseed:
            reseeds += 1
            calls += rng.calls
    else:
        raise RuntimeError("levelgen: no lair after 16 reseeds")
    seed = (seed + k) & 0xFFFF
    sanct = None
    if f3 and depth == 8:
        sanct = sanctum_pass(rooms, edges, seed, lair)
        n += 1
    rng.calls += calls
    LAST = (restarts, rng.calls, reseeds)
    b = bytearray(LBLOCK_LEN)
    b[LH["LVL_DEPTH"]] = depth
    b[LH["LVL_SEED"]:LH["LVL_SEED"] + 2] = (seed & 0xFFFF).to_bytes(2, "little")
    b[LH["GEN_RNG"]:LH["GEN_RNG"] + 2] = rng.x.to_bytes(2, "little")
    b[LH["LVL_ATTR_FLOOR"]], b[LH["LVL_ATTR_WALL"]] = ATTRS[depth]
    b[LH["LVL_START"]] = start
    b[LH["LVL_LAIR"]] = lair
    b[LH["LVL_KEYROOM"]] = L["ROOM_NONE"]
    b[LOFF_KEYROOM2] = L["ROOM_NONE"]
    for room, col in keys:              # slot = colour
        b[LH["LVL_KEYROOM"] if col == 0 else LOFF_KEYROOM2] = room
    b[LH["LVL_SANCTUM"]] = L["ROOM_NONE"] if sanct is None else sanct
    b[LH["LVL_NROOMS"]] = n
    b[LH["LVL_FLAGS"]] = 0               # 3F-T8 (BOSS-GUARD): shut until the boss dies (grate_open); 3B: LF_GRATE_OPEN
    b[LH["FLOOR_N"]] = len(floor)
    b[LH["MASTER_SEED"]:LH["MASTER_SEED"] + 2] = (master & 0xFFFF).to_bytes(2, "little")
    for i, e in enumerate(edges):
        b[LOFF_EDGE + i] = e
    if sanct is not None:               # P3 (game.md §1.3): sanctum_leaf sets the Tome's hp once per level
        b[L["TOME_HP"] - LBASE] = L["TOME_MAX"]
    for r, rm in enumerate(rooms):
        o = LOFF_DESC + r * L["RD_STRIDE"]
        if not rm.present:
            continue
        fl = L["RDF_PRESENT"] | (L["RDF_START"] if rm.start else 0) | \
            (L["RDF_LAIR"] if rm.lair else 0) | (L["RDF_DEADEND"] if rm.dead else 0) | \
            (L["RDF_SANCTUM"] if rm.sanct else 0)
        b[o + L["RD_FLAGS"]] = fl
        b[o + L["RD_EXITS"]] = rm.exits
        b[o + L["RD_UPCOL"]] = rm.up
        b[o + L["RD_DNCOL"]] = rm.dn
        b[o + L["RD_ARRCOL"]] = rm.arr
        b[o + L["RD_EXITCOL"]] = rm.exitcol
        b[o + L["RD_LAD1"]] = rm.lad1
        b[o + L["RD_LAD2"]] = rm.lad2
        b[o + L["RD_PITCOL"]] = rm.pit
        b[o + L["RD_BLOCK"]] = rm.block
        b[o + L2_PITW] = rm.pitw
        b[o + L2_MIDB] = rm.midb
        b[o + L2_MIDW] = rm.midw
        b[o + L["RD_SEED"]:o + L["RD_SEED"] + 2] = rm.seed.to_bytes(2, "little")
    for i in range(L["FLOOR_MAX"]):
        o = LOFF_FLOOR + i * L["FL_STRIDE"]
        ent = floor[i] if i < len(floor) else (L["FL_EMPTY"],) * 4
        b[o:o + 4] = bytes(ent)
    return bytes(b)


def room_cut(desc):
    """AI-SEEK2 (docs/design/ai_seek2.md §2.1): the room's walker cut col K, the Python twin of the Z80
    ROOM_CUT that build_room_map writes: the pit col p (narrow or wide), else the mid-block's b - 1,
    else $FF (no cut). One cut per room (L2 is one feature). seg0(x) = x > K: 0 left / 1 right half.
    desc: the 16 descriptor bytes (or any object indexed by the RD_* / L2 offsets)."""
    p = desc[L["RD_PITCOL"]]
    if p:
        return p
    b = desc[L["RD_SPARE"] + 1]                  # L2_MIDB
    return (b - 1) & 0xFF if b else 0xFF


def seg0(k, x):
    return 1 if x > k else 0


def start_x(b):
    """Hero start col (DFS-root room) = its arrival shaft col on every depth (H1-ARRIVAL, user
    2026-11-05: the hero enters mid-ladder at the shaft's top; level_start_x)."""
    return b[LOFF_DESC + b[LH["LVL_START"]] * L["RD_STRIDE"] + L["RD_ARRCOL"]]



# ---- LP: lazy monster population (game.md §9.4.1-9.4.7) ----------------------
# Reference for the Z80 lp_budget / lp_enter (src/lpop3.asm), byte-exact.
#
# lp_budget(block, lvl): the LP_STATE block (LP_LEN B at LP_STATE) right after
#   generation: LP_KINDS / LP_BOSS / LP_TOTAL from LP_TAB[depth], LP_LVL = lvl,
#   LP_RMAX, every other header / scratch byte 0, ROOM_VISITS 0, every record
#   FRESH with its quota. Split (§9.4.1): N = total - 2; R = present rooms but
#   start / lair / Sanctum (id order); N >= |R| -> every room in R gets 1, the
#   rest one by one by a weighted pick (weight = BFS distance from the start)
#   over the rooms of R with quota < ROOM_MAX, v = rnd(sum) on a COPY of the
#   final GEN_RNG (the header keeps the post-generation state, so every earlier
#   output stays byte-identical); no eligible room -> LP_DISCARD. N < |R| -> the
#   N farthest (ties: lowest id) get 1. Lair quota = 2 (boss + escort).
# lp_enter(block, lp, r, hs, hx, hw): one room entry (§9.4.3) -> (lp', placed)
#   placed = [(kind_byte, hp, storey, col, facing_left)] in slot-fill order.
#   Stream: x = (LVL_SEED ^ ((r*16 + $0F) << 8) ^ ROOM_VISITS[r]) or 1, the
#   GEN_RNG algorithm. FRESH lair: [boss, escort = fit(rnd(8), cap 12)];
#   FRESH room: count x fit(rnd(8), SIGMA_INIT = max(8, ROOM_MAX * minW),
#   reserving left * minW for the units still to roll: the rolled kind, else the
#   other LP_KINDS in list order; the lightest always fits, so nothing is lost);
#   VISITED: its entries. Then per unit, in order: a unit of the LAIR first
#   takes its post (lp_post, 3F-T8 BOSS-GUARD: the boss on the grate, the
#   escort beside it; no stream step), else
#   LP_TRIES candidates, one GEN_RNG step v each: s = bit 8
#   of v, x = LP_XMIN + (v & $FF) mod (29 - w)
#   arrival gap >= LP_GAP (8) on tries 1-4, >= LP_GAP2 (5) on 5-8; a candidate
#   failing ONLY the gap is re-tested at the same x on the other storey
#   (the first legal one; 3F-T8: the old 'boss farthest from the hero' rule is
#   gone). Unplaced units stay in the record (in order). Record -> VISITED; the
#   entries past the new count keep their old bytes (ROOM-MEM reclaim: no zero fill).
#   ROOM_VISITS is NOT incremented here (the caller does it after admission).
#   ROOM-MEM (user 2026-11-03): parked = the room's parked bodies in slot order,
#   [(kind row, storey, x, facing_left)] (Z80: slots with E_ROOM = r | LPK_PARK, lp_bank).
#   Per unit, BEFORE the post / tries: the first parked body of the same kind row
#   (lp_find) -- a lair unit with a post still takes the post; else try 0 = its own
#   (s, x) with lp_legal gap LP_GAP2 (5), no stream step, no other-storey retry; if
#   that fails, the 8 tries as above. A placed unit consumes its parked body and keeps
#   its facing; an unplaced one leaves it parked (a later unit of that kind may match it).
def _x2(*k4):
    """NEW-MON3 T3: today's 4 kinds listed twice = the 8-slot LP_KINDS (pick rnd & 7 draws as rnd & 3 did).
    T4 replaces the rows by the new_monsters.md section 5 lists (slots 0..n-1 distinct, then duplicates)."""
    return tuple(k4) + tuple(k4)


# NEW-MON3 T9: the new_monsters.md §5 lists (slots 0..n-1 distinct, fallback order; n..7 duplicates = weight),
# weights = the tuned preset tools/balance_nm3.json (user 2026-11-13). K_ALIAS = Imp on D4 / D6, Wraith D5 / D7 / D8.
LP_TAB = {1: (_x2("K_RAT", "K_BAT", "K_SLIME", "K_GOBLIN"), "K_BOSS_D1", 13),
          2: (_x2("K_GOBLIN", "K_SPIDER", "K_BAT", "K_RAT"), "K_BOSS_D2", 14),
          3: (("K_SKELETON", "K_VAMPIRE", "K_GHOST", "K_BAT", "K_GOBLIN", "K_GHOST", "K_VAMPIRE", "K_GHOST"), "K_BOSS_D3", 14),
          4: (("K_ORC", "K_RAT", "K_SPIDER", "K_ARCHER", "K_ALIAS", "K_ORC", "K_ARCHER", "K_RAT"), "K_BOSS_D4", 15),
          5: (("K_MUMMY", "K_SPIDER", "K_SKELETON", "K_ARCHER", "K_GARGOYLE", "K_ALIAS", "K_MUMMY", "K_ARCHER"), "K_BOSS_D5", 16),
          6: (("K_VAMPIRE", "K_GARGOYLE", "K_ALIAS", "K_GHOST", "K_NECRO", "K_ORC", "K_VAMPIRE", "K_ORC"), "K_BOSS_D6", 15),
          7: (("K_ORC", "K_GHOST", "K_NECRO", "K_ALIAS", "K_MUMMY", "K_SPIDER", "K_NECRO", "K_NECRO"), "K_BOSS_D7", 15),
          8: (("K_NECRO", "K_SKELETON", "K_GHOST", "K_VAMPIRE", "K_ORC", "K_ALIAS", "K_NECRO", "K_NECRO"), "K_BOSS_D8", 12)}
NM3_B_DEPTHS = L["NM3_B_DEPTHS"]          # bit d-1: row 31 is the Frost Wraith on depth d (defs.asm)
NM3_WR_HP = L["NM3_WR_HP"]


def nm3_variant(depth):
    """A-1: 1 = row 31 is the Frost Wraith (variant B) on this depth, 0 = the Fire Imp (A)."""
    return (NM3_B_DEPTHS >> (depth - 1)) & 1 if depth >= 1 else 0
# kind_tab mirror (main.asm KROW KT_BW / KT_HP / KF_FLYER; tests/lp.py checks
# it against the build): kind -> (body width, hp, flyer)
KINFO = {"K_SKELETON": (3, 10, False), "K_GOBLIN": (3, 6, False), "K_GHOST": (3, 8, True),
         "K_RAT": (4, 3, False), "K_BAT": (3, 3, True), "K_SLIME": (3, 6, False),
         # 3F-T3: the new rows (main.asm KT_BW / KT_HP / KF_FLYER; 3F-T13: BW = the real 3F-A1
         # body, hp the game.md §9.1 / §9.6 value before depth scaling)
         "K_SPIDER": (4, 7, False), "K_VAMPIRE": (3, 14, False), "K_ORC": (3, 14, False),
         "K_ARCHER": (3, 8, False), "K_MUMMY": (3, 18, False), "K_NECRO": (3, 12, False),
         "K_OGRE": (4, 36, False), "K_DKNIGHT": (3, 50, False), "K_ARCHMAGE": (3, 60, False),
         "K_GIANT_RAT": (4, 5, False), "K_RABBIT_RAT": (4, 8, False), "K_SCREECH": (3, 5, True),
         "K_SLINGER": (3, 8, False), "K_BLACK_WIDOW": (4, 10, False), "K_SKEL_GUARD": (3, 14, False),
         "K_SKEL_KNIGHT": (3, 18, False), "K_POLTERGEIST": (3, 11, True), "K_ORC_BERSERK": (3, 18, False),
         "K_ORC_BOUNCER": (3, 24, False), "K_SNIPER": (3, 10, False), "K_BONE_CALLER": (3, 14, False),
         "K_GARGOYLE": (3, 9, True), "K_ALIAS": (3, 5, True)}       # NEW-MON3: row 31 as assembled (the Imp)

# 3F-T13bc: the climbing kinds (main.asm KT_FLAGS KF_CLIMBER; tests/lp.py A0 checks it against
# the build). The LP model does not move monsters, so nothing here reads it yet (the AI / ladder
# rules are the Z80's): Goblin / Skeleton (+ tiers) since 3B, + Orc / Archer / Necro (+ tiers) + Mummy,
# + the Vampire (VAMP-BOSS, user 2026-11-02: the shared climb pair; the Lord too).
CLIMBERS = {"K_SKELETON", "K_GOBLIN", "K_SLINGER", "K_SKEL_GUARD", "K_SKEL_KNIGHT",
            "K_ORC", "K_ORC_BERSERK", "K_ORC_BOUNCER", "K_ARCHER", "K_SNIPER",
            "K_NECRO", "K_BONE_CALLER", "K_MUMMY", "K_SPIDER", "K_BLACK_WIDOW", "K_VAMPIRE"}


def lp_kinfo(k):
    for n, v in KINFO.items():
        if L[n] == k:
            return v
    raise KeyError(k)


def lp_wt(k):
    for n in KINFO:
        if L[n] == k:
            return L["WT_" + n]
    raise KeyError(k)


# 3F-T3: KROWS (game.md) vs the Z80 rows (KINFO = kind_tab BW / HP / flyer, defs.asm WT_*).
# Intentional differences, NOT game changes (designer ruling pending): the prototype rows keep
# (D3-1: Slime / Ghost hp now match §9.1; 3F-T13: the Ogre's body is the real 32x48 = 4 cols,
# so no difference is left). key -> field names that may differ.
KNOWN_STANDIN_DIFFS = {}
for _k, _v in KROWS.items():
    _bw, _hp, _fl = KINFO[_k]
    _got = {"hp": _hp == _v[1], "body": _bw == _v[2], "flyer": _fl == _v[3], "weight": L["WT_" + _k] == _v[4]}
    _bad = {f for f, ok in _got.items() if not ok}
    if _bad != KNOWN_STANDIN_DIFFS.get(_k, set()):
        raise SystemExit(f"levelgen: KROWS {_k} differs from the Z80 row in {sorted(_bad)} "
                         f"(allowed: {sorted(KNOWN_STANDIN_DIFFS.get(_k, ()))})")


# ---- 3F: tier roll, golden flag, kind lookups (table at the top of the module) ----

def tier_odds(depth, lvl):
    """§9.6 spawn roll odds out of 256 -> (T2, T3). LVL_EXP(d) = d, Δ = clamp(LVL - d, -2, 2)."""
    dl = max(-TIER_DELTA_MAX, min(TIER_DELTA_MAX, lvl - depth))
    t2 = max(0, min(T2_CAP, T2_BASE[depth] + TIER_SHIFT2 * dl))
    t3 = max(0, min(T3_CAP, T3_BASE[depth] + TIER_SHIFT3 * dl)) if depth >= TIER3_MIN_DEPTH else 0
    return t2, t3


def tier_pick(base, r, depth, lvl):
    """Pure part of the roll: r in 0..255 -> row key. r < T3 -> tier 3 (tier 2 if the
    kind has none); r < T3 + T2 -> tier 2; else base. Untiered kinds stay base."""
    t = TIERS.get(base)
    if not t:
        return base
    t2, t3 = tier_odds(depth, lvl)
    if r < t3:
        return t[1] or t[0]
    if r < t3 + t2:
        return t[0]
    return base


def tier_roll(rng, base, depth, lvl):
    """One rng step (low byte) iff the kind has tiers; none otherwise (bosses, escorts,
    summons and breeding never call this)."""
    if base not in TIERS:
        return base
    return tier_pick(base, rng.byte(), depth, lvl)


def k3_row(key):
    return KROWS[key][0]


def k3_weight(kb):
    """§9.3 weight of a record kind byte (row | LEK_*): golden +1."""
    w = KROWS[K3_BY_ID[kb & LEK_ROW_MASK]][4]
    return w + (1 if kb & LEK_GOLD else 0)


def k3_info(kb):
    """(body cols, hp, flyer) of a record kind byte; hp = §9.1 depth-scaled by the
    caller via k3_hp."""
    v = KROWS[K3_BY_ID[kb & LEK_ROW_MASK]]
    return v[2], v[1], v[3]


def k3_hp(kb, depth):
    """Spawn hp: row hp + (depth - 1) (§9.1); golden = 2 x scaled + 6 (§9.7 R1)."""
    row = kb & LEK_ROW_MASK
    hp = (NM3_WR_HP if row == KROWS["K_ALIAS"][0] and nm3_variant(depth) else KROWS[K3_BY_ID[row]][1]) + depth - 1
    return 2 * hp + 6 if kb & LEK_GOLD else hp


def k3_boss(depth):
    """LP_BOSS record kind byte: row | LEK_GOLD on the golden depths."""
    key, gold = BOSS3[depth]
    return KROWS[key][0] | (LEK_GOLD if gold else 0)


def lp_off(name):
    return L[name] - L["LP_STATE"]


def _rd(b, r, k):
    return b[LOFF_DESC + r * L["RD_STRIDE"] + L[k]]


def _rb(b, r, off):
    return b[LOFF_DESC + r * L["RD_STRIDE"] + off]


def lp_bfs(b):
    start = b[LH["LVL_START"]]
    dist = {start: 0}
    q = [start]
    steps = ((L["RDX_L"], -1), (L["RDX_R"], 1), (L["RDX_U"], -3), (L["RDX_D"], 3))
    for r in q:
        ex = _rd(b, r, "RD_EXITS")
        for bit, dd in steps:
            if ex & bit and r + dd not in dist:
                dist[r + dd] = dist[r] + 1
                q.append(r + dd)
    return dist


def lp_budget(b, lvl=0, f3=False):
    depth = b[LH["LVL_DEPTH"]]
    start, lair, sanct = b[LH["LVL_START"]], b[LH["LVL_LAIR"]], b[LH["LVL_SANCTUM"]]
    kinds, boss, total = LP_TAB[depth]
    rmax = L["ROOM_MAX"]
    dist = lp_bfs(b)
    R = [r for r in range(NCELL) if _rd(b, r, "RD_FLAGS") & L["RDF_PRESENT"] and r not in (start, lair, sanct)]
    n = total - 2
    quota = [0] * NCELL
    if n >= len(R):
        for r in R:
            quota[r] = 1
        rem = n - len(R)
    else:
        for r in sorted(R, key=lambda r: (-dist[r], r))[:n]:
            quota[r] = 1
        rem = 0
    rng = Rng(0, 0)
    rng.x = int.from_bytes(b[LH["GEN_RNG"]:LH["GEN_RNG"] + 2], "little")
    discard = 0
    while rem:
        elig = [r for r in R if quota[r] < rmax]
        if not elig:
            discard += rem
            break
        v = rng.rnd(sum(dist[r] for r in elig))
        for r in elig:
            if v < dist[r]:
                quota[r] += 1
                break
            v -= dist[r]
        rem -= 1
    quota[lair] = 2
    lp = bytearray(L["LP_LEN"])
    for i, k in enumerate(kinds):
        lp[lp_off("LP_KINDS") + i] = KROWS[k][0] if f3 else L[k]
    lp[lp_off("LP_BOSS")] = k3_boss(depth) if f3 else L[boss]
    lp[lp_off("LP_TOTAL")] = total
    lp[lp_off("LP_LVL")] = lvl
    lp[lp_off("LP_DISCARD")] = discard
    lp[lp_off("LP_RMAX")] = rmax
    for r in range(NCELL):
        lp[lp_off("LP_REC") + r * L["LR_STRIDE"]] = quota[r]
    return bytes(lp)


def lp_hits(b, r, s, lo, hi, flo=None, fhi=None):
    """bank-3 `hits` (levelgen.asm): storey-s footprints f..f+2, the storey-0
    pit p-1..p+3, the storey-s block, against cols lo..hi (ROOM-MEM2: the footprints
    against flo..fhi when given: a returning monster without the 1-col margin)."""
    fp = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2") if s == 0 else \
         ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
    flo, fhi = (lo, hi) if flo is None else (flo, fhi)
    for k in fp:
        f = _rd(b, r, k)
        if f and f <= fhi and f + 2 >= flo:
            return True
    p = _rd(b, r, "RD_PITCOL")
    pw = _rb(b, r, L2_PITW) or 3
    if s == 0 and p and p - 1 <= hi and p + pw >= lo:       # holes + caps (wide: W holes)
        return True
    mb, mw = _rb(b, r, L2_MIDB), _rb(b, r, L2_MIDW)
    if s == 0 and mb and mb - 1 <= hi and mb + mw >= lo:    # mid-block + both rubble cols
        return True
    bl = _rd(b, r, "RD_BLOCK")
    if bl and (bl >> 6) & 1 == s:
        w = bl & L["RDB_WMASK"]
        if bl & L["RDB_RIGHT"]:
            if hi + w >= 31:
                return True
        elif w >= lo:
            return True
    return False


def lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap=8, ret=False):
    """§9.4.3 placement legality -> "ok" / "gap" (fails ONLY the arrival-gap
    test: the caller re-tests the same x on the other storey) / "bad"."""
    for ps, plo, phi in placed:                         # occupied (same storey, cols)
        if ps == s and plo <= x + w - 1 and x <= phi:
            return "bad"
    ex = _rd(b, r, "RD_EXITS")
    if ex & L["RDX_L"] and bool(ex & L["RDX_LS1"]) == (s == 1) and x <= 4:
        return "bad"                                    # left arrival box cols 1..4
    if ex & L["RDX_R"] and bool(ex & L["RDX_RS1"]) == (s == 1) and x + w - 1 >= 27:
        return "bad"                                    # right arrival box cols 27..30
    m = 1                                               # §9.4.3: footprints +-1 col (walkers and flyers)
    lo, hi = max(0, x - m), x + w - 1 + m
    # ROOM-MEM2 (user 2026-11-14): a returning monster (ret: try 0, the door slide) has no ladder /
    # shaft margin: the footprints are tested against its body cols only (the pit / blocks keep it)
    if lp_hits(b, r, s, lo, hi, *((x, x + w - 1) if ret else (None, None))):
        return "bad"
    p = _rd(b, r, "RD_PITCOL")
    if s == 1 and p and p <= hi and p + (_rb(b, r, L2_PITW) or 3) - 1 >= lo:   # a fall from storey 0 lands here
        return "bad"
    if s == hs and not (x >= hx + hw + gap or x + w + gap <= hx):
        return "gap"                                    # body gap to the arrival box
    return "ok"


GUARD_GAP = 5               # boss6.asm: G1a / G1b body gap to the hero's arrival box


def lp_cmap1(b, r, k, placed=()):
    """Z80 lp_cmap's storey-1 LPC_BAD mark of col k: the footprints f-1..f+3 (lp_hits), the
    arrival box of a storey-1 edge, the pit's landing p-1..p+W (+ `placed`: lp_spawn's LPC_BODY)."""
    ex = _rd(b, r, "RD_EXITS")
    if ex & L["RDX_L"] and ex & L["RDX_LS1"] and 1 <= k <= 4:
        return True
    if ex & L["RDX_R"] and ex & L["RDX_RS1"] and 27 <= k <= 30:
        return True
    if lp_hits(b, r, 1, k - 1, k + 1):
        return True
    p = _rd(b, r, "RD_PITCOL")
    if p and p - 1 <= k <= p + (_rb(b, r, L2_PITW) or 3):
        return True
    return any(ps == 1 and lo <= k <= hi for ps, lo, hi in placed)


def lp_post(b, lp, r, kb, w, fly, hs, hx, hw, placed, info, ROWM):
    """3F-T8 (game.md §9.2 'Boss guard' G1 / G1a / G1b; Z80 R6 boss6.asm lp_post): a unit of the
    lair -> (1, x) or None (the ordinary 8-try placement). No spawn-stream step. The post: c (the
    lair's RD_EXITCOL: on the grate); a hero arriving on storey 1 with a body gap < 5 to it shifts
    it 1 col at a time away (right if hx < c) to the first x with gap >= 5 whose body cols carry
    no cell-map mark outside the exit's own c-1..c+3; out of LP_XMIN..LP_XMAX+1-wb -> None. The
    boss (kind | LEK_GOLD == LP_BOSS) stands there; any other unit tries shoulder to shoulder on
    the door side (left if the lair has a left edge), then the other side: range, gap 5, no
    mark, else None (also when the boss has no post)."""
    boss = lp[lp_off("LP_BOSS")]
    wb = info(boss & ROWM)[0]
    c = _rd(b, r, "RD_EXITCOL")

    def rng(x, ww):
        return L["LP_XMIN"] <= x <= L["LP_XMAX"] + 1 - ww

    def gap(x, ww):
        return hs != 1 or x >= hx + hw + GUARD_GAP or x + ww + GUARD_GAP <= hx

    def marks(x, ww, lo, hi):       # LPC_BAD outside lo..hi, or a body placed (LPC_BODY: never exempt)
        return any((lp_cmap1(b, r, k) and not lo <= k <= hi)
                   or any(ps == 1 and plo <= k <= phi for ps, plo, phi in placed) for k in range(x, x + ww))
    bx = c
    if not gap(c, wb) or marks(c, wb, c - 1, c + 3):
        d = 1 if hx < c else -1
        while True:
            bx += d
            if not rng(bx, wb):
                return None
            if gap(bx, wb) and not marks(bx, wb, c - 1, c + 3):
                break
    if kb & (ROWM | LEK_GOLD) == boss:
        return (1, bx)
    sides = [bx - 1 - w, bx + wb + 1]
    if not _rd(b, r, "RD_EXITS") & L["RDX_L"]:
        sides.reverse()
    for x in sides:
        if rng(x, w) and gap(x, w) and not marks(x, w, 1, 0):
            return (1, x)
    return None


def lp_seed(b, lp, r):
    seed = int.from_bytes(b[LH["LVL_SEED"]:LH["LVL_SEED"] + 2], "little")
    v = lp[lp_off("ROOM_VISITS") + r]
    x = seed ^ (((r * 16 + 0x0F) & 0xFF) << 8) ^ v
    return x or 1


LP_CALLS = 0                # rnd calls of the last lp_enter (tests: cost)
LP_OUT_SLOT = []            # ROOM-MEM: the parked slot each placed unit of the last lp_enter used (None: a free one)


def lp_pos_byte(x, s, left, fyo=None):
    """ROOM-MEM2 LP_POS byte (level_defs.asm): x bits 0-4, storey bit 5, facing left bit 6; a flyer
    (fyo = its band row y - 9s) bits 6-7 = min(fyo, 3) instead of the facing; 0 = none."""
    if fyo is not None:
        return (x & 31) | (s & 1) << 5 | min(fyo, 3) << 6
    return (x & 31) | (s & 1) << 5 | (0x40 if left else 0)


def lp_slide(b, r, s, x0, w, fly, hs, hx, hw, placed, gap, bud=None):
    """ROOM-MEM2 door case (R6 lp_t06): try 0 rejected -> the same storey, the nearest x' (a tie: right)
    in [LP_XMIN, LP_XMAX + 1 - w] whose cells are legal ignoring the gap rule (the margin-less returning
    rules); on the hero's arrival storey only on the monster's side, >= gap clear of his box. The Z80's
    two run-length scans (right from x0+1, then left only while nearer). bud = [1 once a slide failed
    this entry]: review 3 (the lp_transition bound) allows one failed slide an entry. None: tries 1-8."""
    if bud is None:
        bud = [0]
    if bud[0]:
        return None
    sc = [False]
    res = _slide(b, r, s, x0, w, fly, hs, hx, hw, placed, gap, sc)
    if res is None and sc[0]:                           # review 4: only a failure after a real scan spends it
        bud[0] = 1
    return res


def _slide(b, r, s, x0, w, fly, hs, hx, hw, placed, gap, sc=None):
    sc = sc if sc is not None else [False]
    lo, hi = L["LP_XMIN"], L["LP_XMAX"] + 1 - w
    if s == hs:
        if x0 > hx:
            lo = max(lo, hx + hw + gap)
        else:
            t = hx - w - gap
            if t < 0:
                return None
            hi = min(hi, t)
    if hi < lo:
        return None
    blk = [lp_legal(b, r, s, c, 1, fly, -1, hx, hw, placed, 0, ret=True) != "ok" for c in range(40)]

    def scan(cols, step, first):
        sc[0] = True
        run = 0
        for k in range(cols):
            c = first + step * k
            run = 0 if blk[c] else run + 1
            if run == w:
                return c
        return None
    xr = None
    start = max(x0 + 1, lo)
    if start <= hi:
        c = scan(hi + w - start, 1, start)
        xr = None if c is None else c - w + 1
    lower = lo if xr is None else max(lo, 2 * x0 + 1 - xr)
    sl = min(x0 - 1, hi)
    if x0 - 1 >= 0 and sl >= lower:
        c = scan(sl + w - lower, -1, sl + w - 1)
        if c is not None:
            return c
    return xr


def lp_enter(b, lp, r, hs, hx, hw, f3=False, parked=None):
    lp = bytearray(lp)
    # ROOM-MEM2: try 0 is every unit's LP_POS byte (the last cell lp_bank wrote; parked or not); a parked
    # body (kind, s, x, left[, slot]) only decides the slot (restored in place) and keeps its own facing
    parked = [[True] + list(q) for q in (parked or [])]     # [still parked, kind, s, x, left(, slot)]
    global LP_OUT_SLOT
    LP_OUT_SLOT = []                                        # per out entry: its parked slot (q[5]) / None
    rng = Rng(0, 0)
    rng.x = lp_seed(b, lp, r)
    lp[lp_off("LP_RNG"):lp_off("LP_RNG") + 2] = rng.x.to_bytes(2, "little")
    ro = lp_off("LP_REC") + r * L["LR_STRIDE"]
    hdr = lp[ro]
    kinds = [lp[lp_off("LP_KINDS") + i] for i in range(8)]     # NEW-MON3 T3: 8 slots
    sig = [0]
    depth, lvl = b[LH["LVL_DEPTH"]], lp[lp_off("LP_LVL")]
    wt = k3_weight if f3 else lp_wt
    info = k3_info if f3 else lp_kinfo
    ROWM = LEK_ROW_MASK if f3 else L["LEK_KIND_MASK"]

    def hp0(k):
        return k3_hp(k, depth) if f3 else lp_kinfo(k)[1]

    minw = min(wt(k) for k in kinds)
    sigi = max(L["LP_SIGMA_INIT"], lp[lp_off("LP_RMAX")] * minw)

    def fit(cap, left=0, tier=False):
        """reservation fit (§9.4.3, designer 2026-10-06): accept a kind only if
        sum + w + left * minW <= cap; rolled first, then the others in list order.
        3F (tier=True, FRESH rooms only): the rolled kind gets the §9.6 tier roll
        (spawn stream, LP_LVL); a rejected tier falls back to its own base, then
        the other LP_KINDS at base tier (the escort is never rolled)."""
        i = rng.rnd(8)
        order = [kinds[i]] + [kinds[j] for j in range(8) if j != i]
        if f3 and tier:
            key = tier_roll(rng, K3_BY_ID[kinds[i]], depth, lvl)
            if KROWS[key][0] != kinds[i]:
                order.insert(0, KROWS[key][0])
        for k in order:
            if sig[0] + wt(k) + left * minw <= cap:
                sig[0] += wt(k)
                return k
        lp[lp_off("LP_DISCARD")] += 1
        return None
    if not hdr & L["LR_VISITED"]:
        units = []
        if r == b[LH["LVL_LAIR"]]:
            k = lp[lp_off("LP_BOSS")]
            units.append((k, hp0(k)))
            sig[0] = wt(k)
            k = fit(L["LP_SIGMA_CAP"])                  # escort: base tier, never rolled
            if k is not None:
                units.append((k, hp0(k)))
        else:
            n = hdr & L["LR_CNT_MASK"]
            for u in range(n):
                k = fit(sigi, n - 1 - u, True)
                if k is not None:
                    units.append((k, hp0(k)))
        for i, (kb, hp) in enumerate(units):            # R6 lp_gen writes them into the record
            lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i] = kb, hp
    else:
        units = [(lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i]) for i in range(hdr & L["LR_CNT_MASK"])]
    placed, out, left = [], [], []
    po = lp_off("LP_POS") + r * L["LR_MAX"]             # ROOM-MEM2: the entries' last cells (0 = none)
    bud = [0]                                           # the slide budget of this entry (LPS_USED)
    for i, (kb, hp) in enumerate(units):
        w, _, fly = info(kb & ROWM)
        pos = lp[po + i]
        pk = next((q for q in parked if q[0] and q[1] == kb & L["LEK_KIND_MASK"]), None)
        best = lp_post(b, lp, r, kb, w, fly, hs, hx, hw, placed, info, ROWM) \
            if r == b[LH["LVL_LAIR"]] else None
        try0 = False
        if best is None and hdr & L["LR_VISITED"] or best is not None:
            lp[po + len(left)] = pos                    # R6 lp_t06 (try 0) / bank-0 lp_post (posted, review 4)
                                                        # copy the byte to the compaction slot first
        if best is None and pos:                        # try 0 (parked or not): the LP_POS cell
            s0, x0 = (pos >> L["LPP_S_BIT"]) & 1, pos & L["LPP_X"]
            if lp_legal(b, r, s0, x0, w, fly, hs, hx, hw, placed, L["LP_GAP2"], ret=True) == "ok":
                best, try0 = (s0, x0), True
            else:                                       # the door case: keep the storey, slide x
                rsv = [(s0, lp[po + j] & 31, (lp[po + j] & 31) + info(units[j][0] & ROWM)[0] - 1)
                       for j in range(i + 1, len(units))                # the later units' saved cells
                       if lp[po + j] and (lp[po + j] >> 5) & 1 == s0]   # on this storey: reserved
                xs = lp_slide(b, r, s0, x0, w, fly, hs, hx, hw, placed + rsv, L["LP_GAP2"], bud)
                if xs is not None:
                    best, try0 = (s0, xs), True
        for t in range(0 if best else L["LP_TRIES"]):
            v = rng.rnd16()                             # one step per candidate
            s = (v >> 8) & 1
            x = L["LP_XMIN"] + (v & 0xFF) % (L["LP_XMAX"] - w)
            gap = L["LP_GAP"] if t < L["LP_TRIES"] // 2 else L["LP_GAP2"]
            res = lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap)
            if res == "gap":                            # other-storey retry, same x
                s ^= 1
                res = lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap)
            if res != "ok":
                continue
            best = (s, x)
            break
        if best is None:
            left.append((kb, hp, pos))
            continue
        s, x = best[0], best[1]
        placed.append((s, x, x + w - 1))
        if pk is not None:
            pk[0] = False                               # restored in place: its own facing
            out.append((kb, hp, s, x, bool(pk[4])) + ((pos >> 6,) if try0 and fly else ()))
            LP_OUT_SLOT.append(pk[5] if len(pk) > 5 else None)
        else:                                           # a fresh slot: its saved facing on try 0
            if try0 and fly:                            # a flyer: faces the hero (from its saved x), its row
                out.append((kb, hp, s, x, x > hx, pos >> 6))
            else:
                out.append((kb, hp, s, x, bool(pos >> L["LPP_LEFT_BIT"] & 1) if try0 else x > hx))
            LP_OUT_SLOT.append(None)
    lp[ro] = L["LR_VISITED"] | len(left)
    global LP_CALLS
    LP_CALLS = rng.calls
    for i, (kb, hp, pos) in enumerate(left):            # the rest keep their bytes (no zero fill)
        lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i] = kb, hp
        lp[po + i] = pos                                # ROOM-MEM2: compacted with its entry
    return bytes(lp), out

def render(b):
    g = lambda r, k: b[LOFF_DESC + r * L["RD_STRIDE"] + L["%s" % k]]
    hdr = lambda k: b[LH[k]]
    out = [f"depth {hdr('LVL_DEPTH')} seed {int.from_bytes(b[LH['LVL_SEED']:LH['LVL_SEED']+2],'little'):04X}"
           f" rooms {hdr('LVL_NROOMS')} start {hdr('LVL_START')} lair {hdr('LVL_LAIR')} startx {start_x(b)}"]
    for gy in range(GH):
        row = vert = ""
        for gx in range(W):
            r = gy * W + gx
            fl = g(r, "RD_FLAGS")
            ex = g(r, "RD_EXITS")
            if not fl & L["RDF_PRESENT"]:
                row += " " * 10; vert += " " * 10; continue
            tag = ("S" if fl & L["RDF_START"] else "") + ("L" if fl & L["RDF_LAIR"] else "") + \
                  ("d" if fl & L["RDF_DEADEND"] else "")
            row += f"[{r}{tag:<3}]"
            if ex & L["RDX_R"]:
                e = b[LOFF_EDGE + hedge(r)]
                row += ("D" if e & L["EG_DOOR"] else "-") + str(1 if ex & L["RDX_RS1"] else 0)
            else:
                row += "  "
            row += "  "[:0]
            vert += " " + ("v" if ex & L["RDX_D"] else " ") + "       "
        out.append(row.rstrip()); out.append(vert.rstrip())
    out.append("(edge: -s open passage / Ds door on storey s; v = vertical link to the room below)")
    for r in range(NCELL):
        if not g(r, "RD_FLAGS") & L["RDF_PRESENT"]:
            continue
        names = [("up", "RD_UPCOL"), ("dn", "RD_DNCOL"), ("arr", "RD_ARRCOL"), ("exit", "RD_EXITCOL"),
                 ("lad1", "RD_LAD1"), ("lad2", "RD_LAD2"), ("pit", "RD_PITCOL")]
        f = " ".join(f"{n}={g(r, k)}" for n, k in names if g(r, k))
        bl = g(r, "RD_BLOCK")
        if bl:
            f += f" block(w{bl & 3},s{(bl >> 6) & 1},{'R' if bl & 128 else 'L'})"
        items = [(b[LOFF_FLOOR + i * 4 + 1], b[LOFF_FLOOR + i * 4] >> 7)
                 for i in range(hdr("FLOOR_N")) if b[LOFF_FLOOR + i * 4] & 15 == r]
        if items:
            f += " potions@" + ",".join(f"{c}/s{s}" for c, s in items)
        out.append(f"  room {r}: {f}")
    return "\n".join(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__.split("\n")[0]); print("usage: levelgen.py DEPTH SEED [--hex|--ascii] [--lp]"); return 2
    depth, seed = int(argv[1], 0), int(argv[2], 0)
    b = generate(depth, seed)
    if "--hex" in argv:
        for i in range(0, len(b), 16):
            print(f"{LBASE + i:04X}: " + " ".join(f"{x:02X}" for x in b[i:i + 16]))
    if "--ascii" in argv or "--hex" not in argv:
        print(render(b))
    if "--lp" in argv:                  # LP budget + every room's first entry from its left edge / x 1
        lp = lp_budget(b, 1)
        o = L["LP_REC"] - L["LP_STATE"]
        print("LP quotas", [lp[o + L["LR_STRIDE"] * r] for r in range(NCELL)], "discard", lp[L["LP_DISCARD"] - L["LP_STATE"]])
        for r in range(NCELL):
            if r != b[LH["LVL_START"]] and _rd(b, r, "RD_FLAGS") & L["RDF_PRESENT"]:
                lp2, out = lp_enter(b, lp, r, 0, 1, 3)
                print(f"  room {r}: placed (kind, hp, s, x, left) {out}  left {lp2[o + L["LR_STRIDE"] * r] & 7}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
