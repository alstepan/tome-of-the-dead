#!/usr/bin/env python3
"""respawn_model.py - reference model of the 3F respawn trickle (game.md §9.5).

Records only (§9.5 "Lazy population"): the trickle APPENDS an entry to a room
record and never touches monster slots. The model is what the Z80 must match
once it exists; the kind / tier ids come from levelgen.KROWS (3F-T3 edits that
table only). The idle wave is NOT modelled (dropped from 3F, §9.7 R5).

State  : Level  = per-room records + LP_RESPAWNS + boss_dead + cur/prev room.
Entry  : (kind byte = row | LEK_RESPAWN, hp)  (hp = §9.1 depth-scaled, full).
Step   : trickle_check(level, turn, rng) -> the appended (room, kind, hp) or None.
RNG    : the GAMEPLAY stream (levelgen.Rng; Rng.byte() = low byte of one step), in
         this fixed order (spec gap, see tests/respawn_model_test.py header):
           1. chance byte  (spawn iff < RESPAWN_CHANCE)           -- always, on a period turn
           2. room pick    rnd(sum of weights)                    -- only if a room is eligible
           3. kind         rnd(8) over the 8 LP_KINDS slots, then the §9.6 tier roll (byte, if the kind has tiers)
           4. cap retry    ONE retry with the next kind in the list (+ its tier roll)
         Hard limits that need no RNG are tested BEFORE step 1 so a skipped check
         costs one chance byte at most.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import levelgen as G                                    # noqa: E402

RESPAWN_PERIOD = 48
RESPAWN_CHANCE = 96                 # of 256
RESPAWN_XP_DIV = 2
RESPAWN_ITEM_W = 2
RESPAWN_ITEM_CAP = 7                # room weight = min(7, 1 + 2 * items)
RESPAWN_MAX = 6                     # LP_RESPAWNS ceiling per level
ROOM_CAP_N = 4                      # §9.3 / LR_MAX: entries per record
ROOM_CAP_SIGMA = 12                 # §9.3 sum-weight cap (LP_SIGMA_CAP)


class Level:
    """Everything the trickle reads or writes.

    recs[r]   : None (no room) or {"visited": bool, "ents": [(kind byte, hp), ...]}
                (a FRESH room has no entries yet: its quota is not an entry)
    items[r]  : un-picked floor items in room r (weight input)
    kinds     : the level's LP_KINDS as KROWS keys (8 slots)
    """

    def __init__(self, depth, lvl, kinds, lair, recs, items=None):
        self.depth, self.lvl, self.kinds, self.lair = depth, lvl, list(kinds), lair
        self.recs = recs
        self.items = items or [0] * 9
        self.resp = 0               # LP_RESPAWNS
        self.boss_dead = False
        self.sanctum = None         # LVL_SANCTUM (D8; 3F-D2: never eligible)
        self.cur = None             # the hero's room
        self.prev = None            # the room the hero just left (updated on EVERY room change)

    def enter(self, r):
        if r != self.cur:
            self.prev, self.cur = self.cur, r
        # entering marks the record VISITED (the real lp_enter does it; tests set it directly)

    def sigma(self, r):
        return sum(G.k3_weight(k) for k, _ in self.recs[r]["ents"])


def room_weight(items):
    return min(RESPAWN_ITEM_CAP, 1 + RESPAWN_ITEM_W * items)


def eligible(lv, extra_w=0):
    """Rooms passing §9.5 hard limits 1, 3, 4 (lair and D8 Sanctum) (and the entry count of 2). `extra_w` > 0
    additionally requires Σ + extra_w <= 12 (limit 2 for a known new body)."""
    out = []
    for r, rec in enumerate(lv.recs):
        if rec is None or not rec["visited"] or len(rec["ents"]) >= ROOM_CAP_N:
            continue
        if r == lv.cur or r == lv.prev or r == lv.lair or r == lv.sanctum:
            continue
        if lv.sigma(r) + extra_w > ROOM_CAP_SIGMA:
            continue
        out.append(r)
    return out


def trickle_check(lv, turn, rng):
    """One §9.5 check. Returns (room, kind byte, hp) when an entry was appended, else None.
    `turn` = the hero turn counter AFTER the turn just completed."""
    if turn % RESPAWN_PERIOD:
        return None
    if lv.boss_dead or lv.resp >= RESPAWN_MAX:        # limit 1 + "stops the turn the boss dies"
        return None
    minw = min(G.KROWS[k][4] for k in lv.kinds)
    # a room qualifies only if SOME kind could still fit (the lightest base weight)
    elig = eligible(lv, minw)
    if not elig or rng.byte() >= RESPAWN_CHANCE:
        return None
    ws = [room_weight(lv.items[r]) for r in elig]
    v = rng.rnd(sum(ws))
    room = elig[-1]
    for r, w in zip(elig, ws):
        if v < w:
            room = r
            break
        v -= w
    i = rng.rnd(8)                                    # NEW-MON3 T3: the 8 slots
    for j in (i, (i + 1) & 7):                        # picked kind, then the next in list order ONCE
        key = G.tier_roll(rng, lv.kinds[j], lv.depth, lv.lvl)
        kb = G.KROWS[key][0] | G.LEK_RESPAWN
        if lv.sigma(room) + G.k3_weight(kb) <= ROOM_CAP_SIGMA:
            hp = G.k3_hp(kb, lv.depth)                # full hp, never golden
            lv.recs[room]["ents"].append((kb, hp))
            lv.resp += 1
            return room, kb, hp
    return None


def respawn_xp(kxp):
    """§9.5: KXP / RESPAWN_XP_DIV rounded down, min 1."""
    return max(1, kxp // RESPAWN_XP_DIV)


def drops_nothing(kb):
    """F_RESPAWN cancels the death-drop roll."""
    return bool(kb & G.LEK_RESPAWN)
