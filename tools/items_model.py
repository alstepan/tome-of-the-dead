#!/usr/bin/env python3
"""items_model.py - reference model for 3E item / trap generation (3E-T5, simplified 3E-T5b).

This is the SPEC the Z80 generator (3E-T6) must match byte for byte. It runs
AFTER levelgen.generate() (the GEN_RNG pass is untouched) and produces, per
level: the new FLOOR_LIST (potion types rolled, new entries appended) and the
trap list (TRAP_LIST 6 x 2 B + TRAP_N). It never touches GEN_RNG / decor streams
(game.md 8.11 Q8): everything is on ITEM_RNG. Rev 6 (game.md 8.11 "3E
simplification"): no identification, no BUC / cursed, no FL_IST - a floor item
is always m 0 (ISTATE bits only exist in the bag), names are fixed and known.

Stream (game.md 8.11 Q8)
------------------------
Same algorithm as GEN_RNG (levelgen.Rng: 16-bit xorshift 7,9,8;
rnd(n) = step then (x & $FF) mod n; rnd16 = step then x), own state:
    LVL_SEED(m, d')  = (m + d' * LVL_SEED_MUL) & $FFFF       (bank3 level_new)
    ITEM_RNG(m, d)   = Rng(LVL_SEED(m, d | $80), d | $80)     seed ^ (d'*$0101), 0 -> 1
It derives from the MASTER seed, not from the (possibly reseeded) level seed.

ITEM_RNG call order, per level (potion types -> food -> scrolls -> gear ->
class books -> ammo / bow -> traps). Per item: type (or qty) roll, THEN
placement. `place(pool, ...)` = room = pool[rnd(len)], storey = rnd(2), then up
to PLACE_TRIES x (col = 2 + rnd(28), first legal wins); no legal col -> the item
is dropped (counted, not an error).
 1. potions: the levelgen entries in list order; entry 0 = Heal (no roll), the
    others type = POT_BY_ROLL[rnd(3)]. Then (FLOOR1) each entry in list order is
    re-checked against the item rules below (its own cell freed first); an
    illegal one is re-placed (non-start pool, scan fallback, same slot).
 2. food:    n = 3 + rnd(2); each: type = IT_F_CARROT + rnd(5), place(non-start).
 3. scrolls: n = 1 + rnd(2); each: type = IT_S_TELEPORT + rnd(4), place(non-start).
 4. gear:    n = 1 + rnd(2); each: type = pool[rnd(len)] (depth + class gated),
    then place(non-start).  Fixed stats, no state roll.
 5. books (IT_BOOK, D1-D7): n = 1 (+1 if depth >= 4 and rnd(2) == 0; the roll is
    skipped on D1-D3 and D8); the D1 book is in the start room at a
    place()d col (scan fallback, never dropped); the others place(non-start).
    D8: none, no roll.
 6. Warrior only, D1-D7: dagger stack qty 2 + rnd(2), arrow stack qty 5 + rnd(4),
    each place(non-start non-lair). Then D2 only: the bow (place(non-start
    non-lair) with a deterministic scan fallback: "regardless of RNG") plus
    an IT_ARROW qty-6 entry in the bow's cell. D8: no ammo.
 7. traps (1.5): count / pool by depth; per trap type = pool[rnd(len)], then up
    to TRAP_TRIES x (room = elig[rnd(len)], storey = rnd(2), t = 6 + rnd(20)),
    first legal wins; none -> dropped.
The key has no floor entry (8.11 Q1); LVL_KEYROOM stays whatever level_gen set.

GEAR2 (docs/design/gear_rules.md 1.3 / 2.3): the gear pool is class-gated per row
(Robe / Hood Mage, Leather / Chain / Plate / Helm Warrior; 2 new rows), and a q pass runs
AFTER gen_traps: for every gear entry in FLOOR_LIST order (generated gear only) one
ITEM_RNG rnd(8); numeric gear (weapon / armour / helmet) gets q in -1..+2 stored as
FL_QTY = 1 + (q & 7), charms keep qty 1 (the draw is still consumed). `gen_level_items(...,
gear2=False)` skips the q pass (G2-1 on/off comparison); the pre-GEAR2 pool is
GEAR_TABLE_OLD / gear_pool(..., old=True).

Encodings
---------
FLOOR_LIST entry (room | S1<<7, col, type, qty). Trap list entry: B0 = room |
S1<<4 (KNOWN / SPENT 0), B1 = col | type << 5.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import levelgen as G  # noqa: E402

D = G.D
MUL = D["LVL_SEED_MUL"] if "LVL_SEED_MUL" in D else 0x9E37     # level_defs.asm (parsed if EQU-literal)

# --- type ids (item_defs.asm, parsed: never copied) -------------------------------
T = {k: v for k, v in D.items() if k.startswith(("IT_", "TT_", "TR_", "TRF_"))}
IT_BOOK, IT_BOW = T["IT_BOOK"], T["IT_BOW"]
FLOOR_MAX = D["FLOOR_MAX"]
OFF_TRAP = D["TRAP_LIST"] - G.BASE          # $B0 in the 320-B block
OFF_TRAPN = D["TRAP_N"] - G.BASE            # $BC
TRAP_MAX = D["TRAP_MAX"]
HERO_WARRIOR, HERO_MAGE = "warrior", "mage"

# --- tunables / rulings (every one a named constant) -------------------------------
PLACE_TRIES = 2 * D["FEAT_TRIES"]           # FLOOR1: 16 col tries per new item (was 8; potions use 32/8 in GEN_RNG)
TRAP_TRIES = 8                              # 1.5 "each trap <= 8 seeded tries"
FLOOR_CAP = 31                              # 8.11 Q11: >= 1 entry stays free for a boss unique
COL_LO, COL_SPAN = 2, 28                    # item col = 2 + rnd(28)  (same as the 3B potions)
# FLOOR1 (game.md 8.11 Q1 rev 2026-10-26): an item covers cols c..c+1 (rows 9s+6..9s+7):
# c <= COL_LAST, both cols legal, no other item within c-1..c+1, <= ROOM_CAP per room
COL_LAST = D["ITEM_COL_LAST"]
ROOM_CAP = D["ITEM_ROOM_CAP"]
TRAP_COL_LO, TRAP_COL_SPAN = 6, 20          # 1.5 t in 6..25
ARROW_BUNDLE = 6                            # 8.5 bow: 6-arrow bundle in the bow's cell
ARROWS_MAX = 24                             # 8.5 "capped 24" (checker only)

POT_BY_ROLL = (T["IT_P_HEAL"], T["IT_P_MANA"], T["IT_P_CURE"])    # Q_POTION_TYPE
POTION_COUNT_MIN = 2                        # 8.5 / levelgen (2..3 entries, from GEN_RNG)
FOOD_N_MIN, FOOD_N_SPAN = 3, 2              # 8.5 food 3-4
SCROLL_N_MIN, SCROLL_N_SPAN = 1, 2          # 8.5 scrolls 1-2
GEAR_N_MIN, GEAR_N_SPAN = 1, 2              # 8.5 gear 1-2
BOOK2_DEPTHS = range(4, 8)                  # 8.5 / 5: 2nd book 1 in 2 on D4-D7
BOOK_DEPTHS = range(1, 8)                   # 8.5: class book D1-D7
AMMO_DEPTHS = range(1, 8)                   # 8.5: ammo D1-D7 (none on D8)
BOW_DEPTH = 2

# 8 table (gear_rules.md 1.3), id order: (type, first depth, class lock); start-kit weapons /
# armour are not found, uniques neither.  GEAR2 adds ROBE (M) and LEATHER (W) and class-locks
# CHAIN / PLATE / HELM (W) and HOOD (M).
GEAR_TABLE = (
    (T["IT_W_LONG"], 2, "W"), (T["IT_W_AXE"], 4, "W"),
    (T["IT_W_IRON"], 2, "M"), (T["IT_W_RUNE"], 4, "M"),
    (T["IT_A_ROBE"], 1, "M"), (T["IT_A_LEATHER"], 1, "W"),
    (T["IT_A_CHAIN"], 3, "W"), (T["IT_A_PLATE"], 6, "W"),
    (T["IT_H_HOOD"], 1, "M"), (T["IT_H_HELM"], 1, "W"),
    (T["IT_C_MIGHT"], 2, None), (T["IT_C_WARD"], 2, None), (T["IT_C_FIRE"], 2, None),
    (T["IT_C_MANA"], 3, None), (T["IT_C_PLENTY"], 3, None),
)
# the pre-GEAR2 table (baseline for the differential check)
GEAR_TABLE_OLD = (
    (T["IT_W_LONG"], 2, "W"), (T["IT_W_AXE"], 4, "W"),
    (T["IT_W_IRON"], 2, "M"), (T["IT_W_RUNE"], 4, "M"),
    (T["IT_A_CHAIN"], 3, None), (T["IT_A_PLATE"], 6, None),
    (T["IT_H_HOOD"], 1, None), (T["IT_H_HELM"], 1, None),
    (T["IT_C_MIGHT"], 2, None), (T["IT_C_WARD"], 2, None), (T["IT_C_FIRE"], 2, None),
    (T["IT_C_MANA"], 3, None), (T["IT_C_PLENTY"], 3, None),
)
# GEAR2 2.3 q thresholds (balance knobs): q = -1 + (s >= T0) + (s >= T1) + (s >= T2),
# s = rnd(8) + ((depth + 1) >> 2)
Q_T0, Q_T1, Q_T2 = 2, 6, 8
Q_MIN, Q_MAX = -1, 2
QTY_MAX_GEAR = 8                            # numeric gear FL_QTY = 1 + (q & 7): 1, 2, 3 or 8 (q -1)
# 1.5 traps: count per depth; pool = kinds allowed at that depth (uniform)
TRAP_COUNT = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3, 7: 4, 8: 4}
# STUN1 (game.md 1.5.1): pool order DART GAS TELEPORT STUN ALARM (the overlay's ig_tord prefix)
TRAP_FIRST = ((T["TT_DART"], 1), (T["TT_GAS"], 2), (T["TT_TELEPORT"], 3), (T["TT_STUN"], 4), (T["TT_ALARM"], 5))

# --- QUESTIONs (doc ambiguous; each choice above/below is a named constant) --------
QUESTIONS = [
    "Q_POTION_TYPE: potion types for entries 2..n are uniform Heal/Mana/Cure (POT_BY_ROLL, rnd(3)); doc fixes only 'first = Heal'.",
    "Q_FOOD_TYPE: food type uniform over the 5 foods (rnd(5)); doc gives only the count 3-4.",
    "Q_SCROLL_COUNT_ROOMS: food/scroll/gear/2nd+ books use the potions' pool (present, non-start rooms, lair allowed); doc names rooms only for ammo/bow (non-start non-lair) and the D1 book (start).",
    "Q_GEAR_POOL: gear type uniform over the depth+class gated 8 table (start kit and uniques excluded); no weighting stated.",
    "Q_POTION_RECHECK (FLOOR1): the GEN_RNG potions do not know the 2-col footprint / spacing / room cap: an illegal one is RE-PLACED on ITEM_RNG in the non-start pool (was Q_D8_LAIR_POTION, D8 lair only; the D8 lair exclusion is gone).",
    "Q_AMMO_CELL: new entries never share a cell with an existing entry, except the bow's arrow bundle (doc: bundle in the bow's cell; other ammo sharing unspecified).",
    "Q_AMMO_QTY: 'stack of 2-3 (1d2+1)' = 2 + rnd(2); '5-8 (1d4+4)' = 5 + rnd(4).",
    "Q_DROPPED_ITEMS: when PLACE_TRIES fail, a new item is dropped silently (only the bow has a scan fallback); stats report it.",
    "Q_TRAP_ROOM_ROLL: trap type is rolled once per trap before the tries; each try rolls room (uniform over eligible rooms without a trap), storey, t; D1 'not within start body +-1' is vacuous (start room is excluded).",
    "Q_KEY_ROOM: LVL_KEYROOM selection is not in this model (no floor item; the key rule is runtime).",
    "Q_ITEM_SEED_XOR: ITEM_RNG applies the same ^(d'*$0101) as GEN_RNG with d' = depth|$80 (doc: 'the generator algorithm seeded with f(master, depth|$80)').",
    "Q_D1_BOOK_COL (RULED): D1 book in the start room, place() then scan fallback; never dropped.",
]


# =============================================================================
# 1. ITEM_RNG
# =============================================================================
def level_seed(master, d):
    """bank3 level_new: MASTER_SEED + d * LVL_SEED_MUL (16-bit wrap); game.md 1 'Seed'."""
    return (master + d * MUL) & 0xFFFF


def item_rng(master, depth):
    """ITEM_RNG for one level (game.md 8.11 Q8): GEN_RNG algorithm, own state,
    seeded from f(master, depth | $80). Separate from every GEN_RNG / decor stream."""
    dd = depth | 0x80
    return G.Rng(level_seed(master, dd), dd)


# =============================================================================
# 2. legality and helpers
# =============================================================================
def glyph(typ):
    """game.md 8.11 Q1 floor glyph id of an item type (17 AMMO, 18 PAGES, 60 FLASK,
    61 FOOD, 62 WEAPON, 63 WORN)."""
    if typ in (T["IT_DAGGER"], T["IT_ARROW"]):
        return 17
    if D["IT_SCR_LO"] <= typ <= D["IT_SCR_HI"] or typ == IT_BOOK:
        return 18
    if typ == T["IT_POTION"] or D["IT_POT_LO"] <= typ <= D["IT_POT_HI"]:
        return 60
    if D["IT_FOOD_LO"] <= typ <= D["IT_FOOD_HI"]:
        return 61
    if D["IT_WPN_LO"] <= typ <= D["IT_WPN_HI"] or typ == IT_BOW:
        return 62
    if D["IT_ARM_LO"] <= typ <= D["IT_CHARM_HI"]:
        return 63
    raise ValueError(typ)


# SINGLE SOURCE of floor ink per item type (approved legend: assets/gfx/concept/grid/
# items3e.tiles headers, game.md 8.11 Q1 + "3E simplification" item 2). Keyed by type id.
_INK_BY_NAME = {
    "IT_DAGGER": 0x47, "IT_ARROW": 0x46,                                   # AMMO
    "IT_F_CARROT": 0x06, "IT_F_APPLE": 0x44, "IT_F_PEAR": 0x04,           # FOOD
    "IT_F_CHEESE": 0x46, "IT_F_MEAT": 0x42,
    "IT_P_HEAL": 0x42, "IT_P_MANA": 0x45, "IT_P_CURE": 0x44,              # FLASK
    "IT_S_TELEPORT": 0x45, "IT_S_FEAR": 0x46, "IT_S_SLEEP": 0x44,         # PAGES
    "IT_S_ENCHANT": 0x47, "IT_BOOK": 0x43,
    "IT_BOW": 0x06,                                                        # WEAPON: staves/bow $06
    "IT_W_SHORT": 0x07, "IT_W_LONG": 0x07, "IT_W_AXE": 0x07, "IT_W_CLEAVER": 0x07,
    "IT_W_OAK": 0x06, "IT_W_IRON": 0x06, "IT_W_RUNE": 0x06, "IT_W_BONE": 0x06,
    "IT_A_ROBE": 0x07, "IT_A_LEATHER": 0x07, "IT_A_CHAIN": 0x07, "IT_A_PLATE": 0x07,   # WORN
    "IT_A_SILK": 0x07, "IT_A_GRAVE": 0x07,
    "IT_H_HOOD": 0x07, "IT_H_HELM": 0x07, "IT_H_KING": 0x07, "IT_H_MIRROR": 0x07,
    "IT_C_MIGHT": 0x06, "IT_C_WARD": 0x06, "IT_C_FIRE": 0x06, "IT_C_MANA": 0x06,
    "IT_C_PLENTY": 0x06, "IT_C_SCARAB": 0x06, "IT_C_GRAVE": 0x06,
}
ITEM_INK = {T[k]: v for k, v in _INK_BY_NAME.items()}


def item_attr(typ):
    """Floor attribute byte (ink on black) of an item type; no state tints."""
    return ITEM_INK[typ]


def is_gear(typ):
    return D["IT_GEAR_LO"] <= typ <= D["IT_GEAR_HI"]


class Lvl:
    """Result: floor = [[room|S1<<7, col, type, qty]], traps = [(B0, B1)], plus
    stats (dropped items / traps)."""

    def __init__(self, depth, hero):
        self.depth, self.hero = depth, hero
        self.floor, self.traps = [], []
        self.dropped_items = 0
        self.dropped_traps = 0
        self.dropped_by_type = {}

def cell_legal(b, r, s, col):
    """FLOOR1: legal item footprint c..c+1 on storey s of room r: c in 2..COL_LAST,
    neither col on a footprint f..f+2, the storey-0 pit p-1..p+3, the edge block
    or an L2 span (wide pit, mid-block, each +1 col): levelgen.lp_hits over
    cols c..c+1 (game.md 8.11 Q8 'avoid every footprint, L2 span (+1)')."""
    if not COL_LO <= col <= COL_LAST:
        return False
    return not G.lp_hits(b, r, s, col, col + 1)


def read_floor(b):
    n = b[G.H["FLOOR_N"]]
    out = []
    for i in range(n):
        o = G.OFF_FLOOR + i * D["FL_STRIDE"]
        out.append(list(b[o:o + 4]))
    return out


def rooms_of(b):
    # P3: the D8 Sanctum (f3 blocks) is in no pool (overlay ig_main: PRESENT and not SANCTUM)
    pres = [r for r in range(9)
            if (G._rd(b, r, "RD_FLAGS") & (D["RDF_PRESENT"] | D["RDF_SANCTUM"])) == D["RDF_PRESENT"]]
    return pres, b[G.H["LVL_START"]], b[G.H["LVL_LAIR"]]


def occupied(lvl):
    return {(e[0] & D["FL_ROOM_MASK"], 1 if e[0] & D["FL_S1"] else 0, e[1])
            for e in lvl.floor if e[0] != D["FL_EMPTY"]}


def item_free(lvl, r, s, col):
    """FLOOR1 (overlay ig_occ + ig_cap): no live entry of (r, s) at a col in
    col-1..col+1, and the room (both storeys) holds < ROOM_CAP entries."""
    n = 0
    for e in lvl.floor:
        if e[0] == D["FL_EMPTY"] or e[0] & D["FL_ROOM_MASK"] != r:
            continue
        n += 1
        if (1 if e[0] & D["FL_S1"] else 0) == s and abs(e[1] - col) <= 1:
            return False
    return n < ROOM_CAP


def item_ok(b, lvl, r, s, col):
    """overlay ig_ok: the footprint legal and free."""
    return col <= COL_LAST and item_free(lvl, r, s, col) and cell_legal(b, r, s, col)


def place(rng, b, lvl, pool, cell_ok_extra=None):
    """One placement (see module doc): room, storey, then col tries. Returns
    (r, s, col) or None (FLOOR1: item_ok - spacing, room cap, footprint)."""
    r = pool[rng.rnd(len(pool))]
    s = rng.rnd(2)
    for _ in range(PLACE_TRIES):
        col = COL_LO + rng.rnd(COL_SPAN)
        if item_ok(b, lvl, r, s, col):
            return r, s, col
    return None


def scan_place(b, lvl, pool):
    """Deterministic fallback (bow, D1 book, a re-placed potion): first legal free
    footprint, pool order, storey 0..1, col 2..29 (29 never legal)."""
    for r in pool:
        for s in (0, 1):
            for col in range(COL_LO, COL_LO + COL_SPAN):
                if item_ok(b, lvl, r, s, col):
                    return r, s, col
    raise RuntimeError("no legal cell at all")


def add(lvl, rsc, typ, qty):
    r, s, col = rsc
    lvl.floor.append([r | (D["FL_S1"] if s else 0), col, typ, qty])


def try_add(rng, b, lvl, pool, typ, qty, scan=False):
    """Roll placement for an already-rolled item. scan=True (D1 book, designer
    ruling 2026-10-20): deterministic scan fallback inside `pool`, never dropped.
    The FLOOR_CAP check is an assert only (max 17 entries, 8.11 rulings)."""
    assert len(lvl.floor) < FLOOR_CAP
    rsc = place(rng, b, lvl, pool)
    if rsc is None and scan:
        rsc = scan_place(b, lvl, pool)
    if rsc is None:
        lvl.dropped_items += 1
        lvl.dropped_by_type[typ] = lvl.dropped_by_type.get(typ, 0) + 1
        return None
    add(lvl, rsc, typ, qty)
    return rsc


# =============================================================================
# 3. item rules
# =============================================================================
def gear_pool(depth, hero, old=False):
    """gear_rules.md 1.3: gear types available at `depth` for `hero` (class-gated, id
    order). old=True: the pre-GEAR2 table.  G2-9: Warrior D1 = [LEATHER, HELM]."""
    lock = "W" if hero == HERO_WARRIOR else "M"
    return [t for t, d0, c in (GEAR_TABLE_OLD if old else GEAR_TABLE) if depth >= d0 and c in (None, lock)]


# =============================================================================
# GEAR2 / GEAR1 / GEAR3 model hooks (pure functions; balance_sim.py imports these)
# =============================================================================
def is_numeric_gear(typ):
    """Weapons, armour, helmets (IT_WPN_LO..IT_HELM_HI); charms are never numeric."""
    return D["IT_WPN_LO"] <= typ <= D["IT_HELM_HI"]


def q_roll(w, depth):
    """gear_rules.md 2.3: q (-1..+2) from the ITEM_RNG draw w = rnd(8) at `depth`."""
    s = w + ((depth + 1) >> 2)
    return -1 + (s >= Q_T0) + (s >= Q_T1) + (s >= Q_T2)


def q_support(depth, q):
    """True if q can occur at `depth` (some w in 0..7 gives it)."""
    return any(q_roll(w, depth) == q for w in range(8))


def q_to_qty(q):
    """Floor encoding FL_QTY = 1 + (q & 7)  (q -1 -> 8, 0 -> 1, +1 -> 2, +2 -> 3)."""
    return 1 + (q & 7)


def qty_to_q(qty):
    """Inverse of q_to_qty: signed 3-bit q = (((qty - 1) & 7) ^ 4) - 4."""
    return (((qty - 1) & 7) ^ 4) - 4


def istate_q(istate):
    """q of a bag / worn ISTATE (bits 0-2, two's complement): ((I & 7) ^ 4) - 4."""
    return ((istate & 7) ^ 4) - 4


def istate_m(istate):
    """m of a bag / worn ISTATE (bits 5-7, signed -4..+3)."""
    return (((istate >> 5) & 7) ^ 4) - 4


def istate_v(istate):
    """v = m + q, the item's total offset on its main stat (gear_dec uses v)."""
    return istate_m(istate) + istate_q(istate)


def pickup_istate(qty):
    """Pickup of a non-ammo floor entry: ISTATE = (FL_QTY - 1) & 7 (no type test)."""
    return (qty - 1) & 7


def gear_instance_q(entry):
    """q of a generated floor entry [room, col, type, qty]: qty_to_q for numeric gear,
    0 for everything else (charms, potions, ...)."""
    return qty_to_q(entry[3]) if is_numeric_gear(entry[2]) else 0


def gear_banned(hero, armour, helm):
    """GEAR1 gate predicate (gear_rules.md 1.2): True if the hero's class abilities are
    blocked.  Mage: worn armour CHAIN/PLATE or helmet HELM; Warrior: armour ROBE or helmet
    HOOD.  Uniques / LEATHER / charms never ban.  armour / helm = worn type id (0 = none)."""
    if hero == HERO_MAGE:
        return armour in (T["IT_A_CHAIN"], T["IT_A_PLATE"]) or helm == T["IT_H_HELM"]
    return armour == T["IT_A_ROBE"] or helm == T["IT_H_HOOD"]


def type_banned_for(hero, typ):
    """equip_consider helper: would wearing `typ` ban `hero`?  (gear_rules.md 1.1)."""
    if hero == HERO_MAGE:
        return typ in (T["IT_A_CHAIN"], T["IT_A_PLATE"], T["IT_H_HELM"])
    return typ in (T["IT_A_ROBE"], T["IT_H_HOOD"])


def rng_mod_mask(n):
    """io.asm rng_mod mask: (n - 1) smeared to 2^k - 1."""
    m = n - 1
    m |= m >> 1
    m |= m >> 2
    m |= m >> 4
    return m


def rng_mod(step, n):
    """gear_rules.md 3.1 rng_mod: repeat x = step() (a gameplay rng_next returning L),
    a = x & 0xFF & mask until a < n.  n = 1 still costs one step."""
    mask = rng_mod_mask(n)
    while True:
        a = step() & 0xFF & mask
        if a < n:
            return a


def enchant_candidate(typ, istate):
    """Enchant candidate test: numeric gear (not IT_NONE) and m != +3."""
    return is_numeric_gear(typ) and (istate & 0xE0) != 0x60


def enchant_target(worn, bag, step):
    """GEAR3 target selection (gear_rules.md 3.1), AFTER the scroll left the bag.
    worn = [(type, istate)] in slot order WEAPON, ARMOUR, HELMET (type 0 = empty slot);
    bag = [(type, istate)] in bag slot order (post-take indices); step = gameplay rng_next.
    Returns ('worn', i, new_istate) / ('bag', i, new_istate) / None (NOTHING HAPPENS, 0 draws).
    Worn m changes need hero_recalc; bag m changes do not.  new_istate = istate + $20."""
    for where, lst in (("worn", worn), ("bag", bag)):
        cand = [i for i, (t, ist) in enumerate(lst) if enchant_candidate(t, ist)]
        if cand:
            i = cand[rng_mod(step, len(cand))]
            return where, i, (lst[i][1] + 0x20) & 0xFF
    return None


def gen_potions(rng, b, lvl, pres, start, lair):
    """game.md 8.5 / 8.11 Q8 step 1: potion TYPES for the levelgen entries (first
    = Heal, no roll). FLOOR1: then every entry, in list order, is re-checked
    against item_ok (its own cell freed first) and an illegal one re-placed in
    the non-start pool, scan fallback (Q_POTION_RECHECK)."""
    pool = [r for r in pres if r != start]
    for i, e in enumerate(lvl.floor):
        e[2] = POT_BY_ROLL[0] if i == 0 else POT_BY_ROLL[rng.rnd(len(POT_BY_ROLL))]
    for i, e in enumerate(lvl.floor):
        rb, col = e[0], e[1]
        e[0] = D["FL_EMPTY"]                         # not its own neighbour
        r, s = rb & D["FL_ROOM_MASK"], 1 if rb & D["FL_S1"] else 0
        if not item_ok(b, lvl, r, s, col):
            rsc = place(rng, b, lvl, pool)
            if rsc is None:
                rsc = scan_place(b, lvl, pool)       # keep the count (>= 2 potions, 8.5)
            r, s, col = rsc
            rb = r | (D["FL_S1"] if s else 0)
        e[0], e[1] = rb, col


def gen_level_items(b, master, hero, gear2=True, old_pool=False):
    """Whole 3E item + trap step for one levelgen block `b` (bytes, 320 B).
    master = MASTER_SEED word; hero in {HERO_WARRIOR, HERO_MAGE}. Pure: returns Lvl.
    gear2=False skips the q pass (the extra ITEM_RNG steps); old_pool=True uses the pre-GEAR2
    gear table (both = the pre-GEAR2 model, byte-identical to 864f0c3)."""
    depth = b[G.H["LVL_DEPTH"]]
    rng = item_rng(master, depth)
    pres, start, lair = rooms_of(b)
    lvl = Lvl(depth, hero)
    lvl.floor = read_floor(b)
    non_start = [r for r in pres if r != start]
    non_lair = [r for r in non_start if r != lair]
    glyph_pool = non_start                   # FLOOR1: the D8 lair exclusion is gone

    gen_potions(rng, b, lvl, pres, start, lair)
    # 8.5 food 3-4
    for _ in range(FOOD_N_MIN + rng.rnd(FOOD_N_SPAN)):
        typ = D["IT_FOOD_LO"] + rng.rnd(D["IT_FOOD_HI"] - D["IT_FOOD_LO"] + 1)
        try_add(rng, b, lvl, glyph_pool, typ, 1)
    # 8.5 scrolls 1-2 (PAGES glyph 18: lair allowed on D8), type uniform of 4 (8)
    for _ in range(SCROLL_N_MIN + rng.rnd(SCROLL_N_SPAN)):
        typ = D["IT_SCR_LO"] + rng.rnd(D["IT_SCR_HI"] - D["IT_SCR_LO"] + 1)
        try_add(rng, b, lvl, non_start, typ, 1)
    # 8.5 gear 1-2 depth-gated, fixed stats
    gp = gear_pool(depth, hero, old=old_pool)
    for _ in range(GEAR_N_MIN + rng.rnd(GEAR_N_SPAN)):
        typ = gp[rng.rnd(len(gp))]
        try_add(rng, b, lvl, glyph_pool, typ, 1)
    # 8.5 / 5: class books
    if depth in BOOK_DEPTHS:
        n = 1 + (1 if depth in BOOK2_DEPTHS and rng.rnd(2) == 0 else 0)
        for k in range(n):
            pool = [start] if (depth == 1 and k == 0) else non_start
            try_add(rng, b, lvl, pool, IT_BOOK, 1, scan=(depth == 1 and k == 0))
    # 8.5 ammunition / bow (Warrior runs only)
    if hero == HERO_WARRIOR and depth in AMMO_DEPTHS:
        for typ, lo, span in ((T["IT_DAGGER"], 2, 2), (T["IT_ARROW"], 5, 4)):
            try_add(rng, b, lvl, non_lair, typ, lo + rng.rnd(span))
        if depth == BOW_DEPTH:
            rsc = place(rng, b, lvl, non_lair)
            if rsc is None:
                rsc = scan_place(b, lvl, non_lair)
            add(lvl, rsc, T["IT_ARROW"], ARROW_BUNDLE)   # same cell (8.5); bundle first, the bow LAST:
            add(lvl, rsc, IT_BOW, 1)                     # the cell shows its last entry (BOW-ICON)
    gen_traps(rng, b, lvl, pres, start, lair)
    if gear2:
        gen_gear_q(rng, lvl)
    return lvl


def gen_gear_q(rng, lvl):
    """GEAR2 2.3: after the traps, one rnd(8) per gear entry in FLOOR_LIST order (generated
    gear only exists here).  Numeric gear: FL_QTY = 1 + (q & 7); charms: qty stays 1."""
    for e in lvl.floor:
        if is_gear(e[2]):
            w = rng.rnd(8)
            if e[2] < D["IT_CHARM_LO"]:
                e[3] = q_to_qty(q_roll(w, lvl.depth))


# =============================================================================
# 4. traps (game.md 1.5)
# =============================================================================
def trap_pool(depth):
    """1.5 type pool by depth (uniform): DART D1+, GAS D2+, TELEPORT D3+, ALARM D5+."""
    return [t for t, d0 in TRAP_FIRST if depth >= d0]


def trap_col_ok(b, r, s, t, floor):
    """1.5 placement col rules for a trap at col t on storey s of room r (the room
    rules are the caller's): t in 6..25; for every footprint c..c+2 on that
    storey (ladders, shafts, holes, arrival, pit) t not in [c-1, c+3]; wide pit /
    mid-block / edge block (+1 col, adjacent included); storey 1: pit landing
    zone [p-1, p+3] (wide: p+W); not inside a floor item's footprint c..c+1."""
    if not TRAP_COL_LO <= t < TRAP_COL_LO + TRAP_COL_SPAN:
        return False
    names = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2", "RD_PITCOL") if s == 0 else \
            ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
    for k in names:
        c = G._rd(b, r, k)
        if c and c - 1 <= t <= c + 3:
            return False
    p = G._rd(b, r, "RD_PITCOL")
    pw = G._rb(b, r, G.L2_PITW) or 3
    if p and p - 1 <= t <= p + pw:              # wide pit caps (s=0) / landing zone (s=1)
        return False
    mb, mw = G._rb(b, r, G.L2_MIDB), G._rb(b, r, G.L2_MIDW)
    if s == 0 and mb and mb - 1 <= t <= mb + mw:
        return False
    bl = G._rd(b, r, "RD_BLOCK")
    if bl and (bl >> 6) & 1 == s:               # not under/adjacent to the block or its rubble col
        w = bl & D["RDB_WMASK"]
        if (t >= 30 - w) if bl & D["RDB_RIGHT"] else (t <= w + 1):
            return False
    for e in floor:
        if e[0] != D["FL_EMPTY"] and e[0] & D["FL_ROOM_MASK"] == r and \
                bool(e[0] & D["FL_S1"]) == bool(s) and e[1] in (t - 1, t):
            return False                        # FLOOR1: t != c, c + 1 of any item
    return True


def gen_traps(rng, b, lvl, pres, start, lair):
    """1.5 counts / placement. Eligible rooms: present, not start, not lair (the
    Sanctum is never present), <= 1 trap per room."""
    pool = trap_pool(lvl.depth)
    used = set()
    for _ in range(TRAP_COUNT[lvl.depth]):
        typ = pool[rng.rnd(len(pool))]
        placed = False
        for _ in range(TRAP_TRIES):
            elig = [r for r in pres if r not in (start, lair) and r not in used]
            if not elig:
                break
            r = elig[rng.rnd(len(elig))]
            s = rng.rnd(2)
            t = TRAP_COL_LO + rng.rnd(TRAP_COL_SPAN)
            if trap_col_ok(b, r, s, t, lvl.floor):
                used.add(r)
                lvl.traps.append((r | (T["TRF_S1"] if s else 0), t | (typ << T["TR_TYPE_SHIFT"])))
                placed = True
                break
        if not placed:
            lvl.dropped_traps += 1
    assert len(lvl.traps) <= TRAP_MAX


def apply_block(b, lvl):
    """Write `lvl` into a copy of the 320-B block: FLOOR_LIST + FLOOR_N, TRAP_LIST + TRAP_N.
    Every other byte is unchanged. Returns the block."""
    nb = bytearray(b)
    nb[G.H["FLOOR_N"]] = len(lvl.floor)
    for i in range(FLOOR_MAX):
        o = G.OFF_FLOOR + i * D["FL_STRIDE"]
        nb[o:o + 4] = bytes(lvl.floor[i]) if i < len(lvl.floor) else bytes((D["FL_EMPTY"],) * 4)
    for i in range(TRAP_MAX):
        o = OFF_TRAP + i * D["TRAP_STRIDE"]
        nb[o:o + 2] = bytes(lvl.traps[i]) if i < len(lvl.traps) else b"\0\0"
    nb[OFF_TRAPN] = len(lvl.traps)
    return bytes(nb)


# =============================================================================
# 5. invariants
# =============================================================================
def check_items(b, lvl, hero=None):
    """Invariants of one generated level (b = the levelgen block it was made from).
    Returns a list of violation strings (empty = ok)."""
    v = []
    hero = hero or lvl.hero
    depth = lvl.depth
    pres, start, lair = rooms_of(b)
    nb = apply_block(b, lvl)
    n = len(lvl.floor)
    base = read_floor(b)
    if n > FLOOR_CAP:
        v.append(f"floor entries {n} > {FLOOR_CAP}")
    if len(lvl.traps) > TRAP_MAX:
        v.append("trap list overflow")
    # the non-item bytes of the block are untouched
    for i in range(len(b)):
        if G.OFF_FLOOR <= i < G.OFF_FLOOR + FLOOR_MAX * 4 or i == G.H["FLOOR_N"] or \
                OFF_TRAP <= i <= OFF_TRAPN:
            continue
        if nb[i] != b[i]:
            v.append(f"block byte {i} changed")
            break
    if any(b[OFF_TRAP:OFF_TRAPN + 1]):
        v.append("base block trap bytes not 0")
    cnt = {}
    cells = {}
    for i, (rb, col, typ, qty) in enumerate(lvl.floor):
        r, s = rb & D["FL_ROOM_MASK"], 1 if rb & D["FL_S1"] else 0
        cnt[typ] = cnt.get(typ, 0) + 1
        if r not in pres:
            v.append(f"entry {i}: room {r} absent")
            continue
        if not cell_legal(b, r, s, col) or not G.item_col_ok(G_room(b, r), s, col) \
                or not G.item_col_ok(G_room(b, r), s, col + 1):
            v.append(f"entry {i}: illegal cell r{r} s{s} c{col}")
        cells.setdefault((r, s, col), []).append((i, typ))
        try:
            g = glyph(typ)
        except ValueError:
            v.append(f"entry {i}: bad type {typ}")
            continue
        if typ == T["IT_POTION"] or typ in (T["IT_KEY"],):
            v.append(f"entry {i}: type {typ} not allowed")
        if i < len(base) and typ == T["IT_POTION"]:
            v.append("legacy potion left")
        if qty < 1:
            v.append(f"entry {i}: qty 0")
        if not is_numeric_gear(typ) and typ not in (T["IT_DAGGER"], T["IT_ARROW"]) and qty != 1:
            v.append(f"entry {i}: non-ammo type {typ} qty {qty} (invariant: 1 unless numeric gear)")
        if is_gear(typ):
            if is_numeric_gear(typ):
                if not 1 <= qty <= QTY_MAX_GEAR or not Q_MIN <= qty_to_q(qty) <= Q_MAX:
                    v.append(f"entry {i}: gear qty {qty}")
                elif not q_support(depth, qty_to_q(qty)):
                    v.append(f"entry {i}: q {qty_to_q(qty)} outside D{depth} support")
            elif qty != 1:
                v.append(f"entry {i}: charm qty {qty}")
            if typ not in gear_pool(depth, hero):
                v.append(f"entry {i}: gear {typ} not in D{depth} {hero} pool")
    # FLOOR1: one item per footprint, except the bow + its bundle (exact col), no two
    # items within c-1..c+1 of each other (the potions too: re-checked), the room cap
    for k, es in cells.items():
        if len(es) > 1 and sorted(t for _, t in es) != sorted([IT_BOW, T["IT_ARROW"]]):
            v.append(f"cell {k} holds {[t for _, t in es]}")
    for (r, s, c) in cells:
        if (r, s, c + 1) in cells:
            v.append(f"items r{r} s{s} at cols {c} and {c + 1}")
    per_room = {}
    for rb, col, typ, qty in lvl.floor:
        per_room[rb & D["FL_ROOM_MASK"]] = per_room.get(rb & D["FL_ROOM_MASK"], 0) + 1
    for r, n in per_room.items():
        if n > ROOM_CAP + 1:                   # (+ the bow's bundle)
            v.append(f"room {r}: {n} entries > cap {ROOM_CAP}")
    # counts
    pots = [e for e in lvl.floor if D["IT_POT_LO"] <= e[2] <= D["IT_POT_HI"]]
    if not POTION_COUNT_MIN <= len(pots) <= POTION_COUNT_MIN + 1 or len(pots) != len(base):
        v.append(f"potions {len(pots)}")
    if not any(e[2] == T["IT_P_HEAL"] for e in pots):
        v.append("no Heal")
    if lvl.floor[:len(base)] and any(e[2] not in range(D["IT_POT_LO"], D["IT_POT_HI"] + 1)
                                     for e in lvl.floor[:len(base)]):
        v.append("base entries not potions")
    nf = sum(cnt.get(t, 0) for t in range(D["IT_FOOD_LO"], D["IT_FOOD_HI"] + 1))
    ns = sum(cnt.get(t, 0) for t in range(D["IT_SCR_LO"], D["IT_SCR_HI"] + 1))
    ng = sum(c for t, c in cnt.items() if is_gear(t))
    nbk = cnt.get(IT_BOOK, 0)
    if not FOOD_N_MIN - lvl.dropped_items <= nf <= FOOD_N_MIN + FOOD_N_SPAN - 1:
        v.append(f"food {nf}")
    if not SCROLL_N_MIN - lvl.dropped_items <= ns <= SCROLL_N_MIN + SCROLL_N_SPAN - 1:
        v.append(f"scrolls {ns}")
    if not GEAR_N_MIN - lvl.dropped_items <= ng <= GEAR_N_MIN + GEAR_N_SPAN - 1:
        v.append(f"gear {ng}")
    want_lo = (1 if depth in BOOK_DEPTHS else 0)
    want_hi = want_lo + (1 if depth in BOOK2_DEPTHS else 0)
    if not want_lo - (0 if depth == 1 else lvl.dropped_items) <= nbk <= want_hi:
        v.append(f"books {nbk} (want {want_lo}..{want_hi})")
    if depth == 1 and nbk and not any(e[2] == IT_BOOK and e[0] & 15 == start for e in lvl.floor):
        v.append("D1 book not in the start room")
    for e in lvl.floor:
        if e[2] == IT_BOOK and e[0] & 15 == start and depth != 1:
            v.append("book in the start room off D1")
    if hero == HERO_MAGE:
        if cnt.get(T["IT_DAGGER"]) or cnt.get(T["IT_ARROW"]) or cnt.get(IT_BOW):
            v.append("Mage run has ammo / bow")
    else:
        d_ok = depth in AMMO_DEPTHS
        exp_arrow = (1 if d_ok else 0) + (1 if depth == BOW_DEPTH else 0)
        if not (exp_arrow - lvl.dropped_items <= cnt.get(T["IT_ARROW"], 0) <= exp_arrow):
            v.append(f"arrow entries {cnt.get(T['IT_ARROW'], 0)} want {exp_arrow}")
        if cnt.get(T["IT_DAGGER"], 0) > (1 if d_ok else 0):
            v.append("dagger stacks")
        if cnt.get(IT_BOW, 0) != (1 if depth == BOW_DEPTH else 0):
            v.append(f"bow count {cnt.get(IT_BOW, 0)}")
        for rb, col, typ, qty in lvl.floor:
            if typ == T["IT_DAGGER"] and not 2 <= qty <= 3:
                v.append(f"dagger qty {qty}")
            if typ == T["IT_ARROW"] and not (5 <= qty <= 8 or qty == ARROW_BUNDLE):
                v.append(f"arrow qty {qty}")
            if typ in (T["IT_DAGGER"], T["IT_ARROW"], IT_BOW) and (rb & 15 in (start, lair)):
                v.append("ammo/bow in start/lair room")
        if cnt.get(IT_BOW) and depth == BOW_DEPTH:
            bw = [e for e in lvl.floor if e[2] == IT_BOW][0]
            if not any(e[2] == T["IT_ARROW"] and e[3] == ARROW_BUNDLE and e[:2] == bw[:2] for e in lvl.floor):
                v.append("bow without bundle in its cell")
    # traps
    pool = trap_pool(depth)
    if len(lvl.traps) + lvl.dropped_traps != TRAP_COUNT[depth]:
        v.append(f"trap count {len(lvl.traps)}+{lvl.dropped_traps} != {TRAP_COUNT[depth]}")
    seen = set()
    for b0, b1 in lvl.traps:
        r, s = b0 & T["TRF_ROOM_MASK"], 1 if b0 & T["TRF_S1"] else 0
        t, ty = b1 & T["TR_COL_MASK"], (b1 & T["TR_TYPE_MASK"]) >> T["TR_TYPE_SHIFT"]
        if b0 & ~(T["TRF_ROOM_MASK"] | T["TRF_S1"]):
            v.append("trap flag/spare bits set")
        if r not in pres or r in (start, lair):
            v.append(f"trap in room {r} (absent/start/lair)")
        if r in seen:
            v.append(f"two traps in room {r}")
        seen.add(r)
        if ty not in pool:
            v.append(f"trap type {ty} not in D{depth} pool")
        if not trap_col_ok_indep(b, r, s, t, lvl.floor):
            v.append(f"trap r{r} s{s} t{t} illegal")
    return v


def G_room(b, r):
    """A levelgen.Room view of block room r (for levelgen.item_col_ok)."""
    rm = G.Room()
    rm.up, rm.dn = G._rd(b, r, "RD_UPCOL"), G._rd(b, r, "RD_DNCOL")
    rm.arr, rm.exitcol = G._rd(b, r, "RD_ARRCOL"), G._rd(b, r, "RD_EXITCOL")
    rm.lad1, rm.lad2 = G._rd(b, r, "RD_LAD1"), G._rd(b, r, "RD_LAD2")
    rm.pit, rm.block = G._rd(b, r, "RD_PITCOL"), G._rd(b, r, "RD_BLOCK")
    return rm


def trap_col_ok_indep(b, r, s, t, floor):
    """Checker re-statement of 1.5 using explicit footprint spans (does not share
    trap_col_ok's code path)."""
    if not 6 <= t <= 25:
        return False
    spans = []
    fp = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2") if s == 0 else \
         ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
    for k in fp:
        c = G._rd(b, r, k)
        if c:
            spans.append((c - 1, c + 3))
    p = G._rd(b, r, "RD_PITCOL")
    if p:
        spans.append((p - 1, p + (G._rb(b, r, G.L2_PITW) or 3)))
    if s == 0 and G._rb(b, r, G.L2_MIDB):
        spans.append((G._rb(b, r, G.L2_MIDB) - 1, G._rb(b, r, G.L2_MIDB) + G._rb(b, r, G.L2_MIDW)))
    bl = G._rd(b, r, "RD_BLOCK")
    if bl and (bl >> 6) & 1 == s:
        w = bl & 3
        spans.append((30 - w, 31) if bl & 128 else (0, w + 1))
    if any(lo <= t <= hi for lo, hi in spans):
        return False
    return not any(e[0] != D["FL_EMPTY"] and e[0] & 15 == r and (e[0] >> 7) == s and t in (e[1], e[1] + 1)
                   for e in floor)


# =============================================================================
# 6. CLI / sweep
# =============================================================================
def master_for(i):
    """i-th master seed of a sweep (all of 0..65535 for N=65536)."""
    return i & 0xFFFF


def sweep(args):
    """(masters, depths) -> (violations, stats) over masters x depths x both heroes."""
    masters, depths = args
    bad, st = [], {"levels": 0, "dropped_items": 0, "dropped_traps": 0, "by_type": {},
                   "traps": 0, "entries_max": 0}
    for mst in masters:
        for d in depths:
            try:
                b = G.generate(d, level_seed(mst, d), mst)
            except RuntimeError:
                continue
            for hero in (HERO_WARRIOR, HERO_MAGE):
                lvl = gen_level_items(b, mst, hero)
                viol = check_items(b, lvl, hero)
                if viol:
                    bad.append((mst, d, hero, viol[:3]))
                st["levels"] += 1
                st["dropped_items"] += lvl.dropped_items
                st["dropped_traps"] += lvl.dropped_traps
                for k_, n_ in lvl.dropped_by_type.items():
                    st["by_type"][k_] = st["by_type"].get(k_, 0) + n_
                st["traps"] += len(lvl.traps)
                st["entries_max"] = max(st["entries_max"], len(lvl.floor))
    return bad, st


def merge(a, b):
    a["levels"] += b["levels"]
    for k in ("dropped_items", "dropped_traps", "traps"):
        a[k] += b[k]
    a["entries_max"] = max(a["entries_max"], b["entries_max"])
    for k_, n_ in b["by_type"].items():
        a["by_type"][k_] = a["by_type"].get(k_, 0) + n_


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=1000, help="number of master seeds (0..N-1)")
    ap.add_argument("--depths", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--questions", action="store_true", help="print the open QUESTIONs and exit")
    ap.add_argument("--show", nargs=3, metavar=("MASTER", "DEPTH", "HERO"), help="dump one level")
    a = ap.parse_args(argv)
    if a.questions:
        print("\n".join("QUESTION: " + q for q in QUESTIONS))
        return 0
    if a.show:
        mst, d, hero = int(a.show[0], 0), int(a.show[1]), a.show[2]
        b = G.generate(d, level_seed(mst, d), mst)
        lvl = gen_level_items(b, mst, hero)
        for e in lvl.floor:
            print(f"  r{e[0] & 15} s{e[0] >> 7} c{e[1]:2d} type {e[2]:2d} qty {e[3]} attr {item_attr(e[2]):02X}")
        print("  traps", [(f"{x:02X}", f"{y:02X}") for x, y in lvl.traps])
        print("  violations:", check_items(b, lvl, hero))
        return 0
    import multiprocessing as mp
    import time
    t0 = time.time()
    depths = list(range(1, a.depths + 1))
    jobs = a.jobs or (mp.cpu_count() or 1)
    chunks = [(range(i, a.seeds, jobs * 8), depths) for i in range(jobs * 8)]
    st = {"levels": 0, "dropped_items": 0, "dropped_traps": 0, "traps": 0, "entries_max": 0, "by_type": {}}
    bad = []
    if jobs > 1:
        with mp.Pool(jobs) as pool:
            for b_, s_ in pool.imap_unordered(sweep, chunks):
                bad += b_
                merge(st, s_)
    else:
        for c in chunks:
            b_, s_ = sweep(c)
            bad += b_
            merge(st, s_)
    print(f"items_model: {a.seeds} master seeds x D1..D{a.depths} x 2 heroes = {st['levels']} levels "
          f"in {time.time() - t0:.0f}s")
    print(f"  violations {len(bad)}  max floor entries {st['entries_max']}")
    print(f"  dropped items {st['dropped_items']}  dropped traps {st['dropped_traps']}  traps {st['traps']}")
    print("  dropped by type", dict(sorted(st["by_type"].items())))
    for x in bad[:10]:
        print("  FAIL", x)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
