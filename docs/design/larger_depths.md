# LARGER-D — bigger depths for more playtime (designer 2026-11-12)

Status: **APPROVED with the §9 defaults (user 2026-11-12).** User goal (2026-11-12): MORE PLAYTIME, still D1–D8, one-screen rooms (no bigger or
scrolling rooms). Does not edit game.md; §8 lists impacts. Inputs: game.md §1/§1.1 (L1, L2, I1–I6), §4.1,
§7, §8.5, §8.11, §9.4–9.5, §10; budget.md §6; memory-map.md (`LVL_STATE`, `ROOM_DESC`, `EDGE_TAB`,
`LP_STATE`); new_monsters.md §2.3/§5; BSIM1 sim note (manager 2026-11-12).

## 1. Options and recommendation

| | Grid | Rooms / level (D8 excl. Sanctum) | Total rooms | Run (E) | Per depth |
|---|---|---|---|---|---|
| Today | 3×3 | 7–9 (D8 7–8) | ~65 | 60–65 min | ~7.5–8 min |
| **A** | 3×3 | 9 always (D8 8) | 72 | 66–72 min (+11 %) | ~8.5–9 min |
| **B-tall (recommended)** | **3 wide × 4 tall** | **10–12 (D8 10–11)** | **~89** | **82–89 min (+37 %)** | **~10.5–11 min** |
| B 4×3 | 4 wide × 3 tall | 10–12 (D8 10–11) | ~89 | 82–89 min | ~10.5–11 min |
| B 4×4 | 4×4 | 12–16 (D8 12–15) | ~113 | 104–113 min (+74 %) | ~13–14 min |

Model: minutes ∝ rooms (~0.95 min/room: ~450 turns per 8-room level, §10). Bigger trees also lengthen
key-room and backtrack walks, so B is if anything an underestimate.

**Decision: B-tall, 3 columns × 4 rows, `n = 10 + rnd(3)`.** Why:
- **A misses the goal:** ≤ +7 rooms, and every level fills the whole 3×3 (layout variety gone). Free in bytes.
- **4×4 is too much at once:** ×1.75 content per level overflows `FLOOR_LIST` (32), room ids fill all 16
  values of the 4-bit fields (`FL_ROOM`, `TR_B0`), and ~14-room levels make the far-leaf key room a slog.
- **Tall beats wide.** (1) Id `r = 3·row + col` is unchanged (neighbours `r∓1`, `r∓3`, `col = r mod 3`,
  `EDGE_TAB e = 2·row + col`): only the row bound and bottom-row ids change, a constant edit in Z80 and
  Python. 4×3 rewrites every `mod 3` site (cheaper `and 3`, but more churn and D0 ids remap). (2) L1 "the
  hero always heads down": 4 rows force ≥ 3 descents start → lair (today ≥ 2), so the new rooms get played.
  (3) The D0 hand-made ids (room C = cell 5, exit into cell 8) stay valid.
- Fill ratio 10–12 of 12 (83–100 %) matches today's 7–9 of 9 (78–100 %).

## 2. Generator rules (replace the L1 rules row; style as game.md §1.1)

| Step | Rule (LARGER-D) |
|---|---|
| Grid | `GRID_W` 3, `GRID_H` 4, `r = 3·row + col`, row 0 top, ids 0–11; left `r−1` (col > 0), right `r+1` (col < 2), up `r−3` (row > 0), down `r+3` (row < 3). Bottom row = **9–11** |
| (1) Start | `start = rnd(3)` (top row), unchanged; no up-exit; D2+ arrival shaft unchanged |
| (2) Count | **`n = 10 + rnd(3)`; D8 `n = min(10 + rnd(3), 11)`** (Sanctum cell reserved) |
| (3) DFS | random DFS from `start` `while stack and not done`; `done` = `|visited| ≥ n` **and** a bottom pair (9–10 or 10–11) visited. A full DFS reaches all 12, so `done` is reachable |
| (4) Bottom edge | if no tree edge joins two bottom rooms, the loop edge is **mandatory**, `rnd(len)` over unlinked present pairs (9–10, 10–11); else the `LOOP_EDGE_ODDS` roll. 0–1 extra edges |
| (5) D8 Sanctum | before the DFS reserve **`S = 9 + 2·rnd(2)`**; the DFS never enters `S`; `done` also needs 10 and the other bottom end. **Lair = 10**; Sanctum off its free side, sealed door. D8 `LVL_NROOMS` 11–12 |
| (6) Lair tiers | as today, "bottom row" = row 3: (a) farthest BFS bottom non-start leaf with a horizontal edge; (b) farthest bottom room with one; ties lowest id; D8 `sanctum_ok`. Reseeds must be 0 (≤ 16 safety net kept) |
| (7)(8) | lair door, key room (farthest other leaf), vertical links, doors 1 in 3, shaft cols: unchanged |
| L2 caps | odds unchanged; **≤ 3 mid-blocks and ≤ 3 wide pits per level** (was 2); ≤ 1 per room; none on D1 or in start/lair/Sanctum |

Levelcheck (D1–D8, 300 seeds): start row 0, lair row 3, `n` 10–12 (D8 10–11 + Sanctum), lair horizontal
edge, D8 lair = 10 with `S` free, reseeds 0, **BFS start → lair ≥ 3**, I1 "7–9" → "10–12", I2 caps 2 → 3,
I3–I6 unchanged. Junior reports Restart counts (feature/potion) before vs after.

## 3. Pacing: monsters and consumables ×~1.35, power items fixed

ROOM_MAX 3 unchanged, so per-room fight and supply density stay; books/gear/bow/uniques stay as BAL-1 FINAL.

| Knob | Today | LARGER-D |
|---|---|---|
| Monsters incl. boss D1..D8 (§9.4) | 13/14/14/15/16/15/15/12 | **18/19/19/20/22/20/20/16** (D8 15 + Archmage); min `|R|` 8 × 3 = 24 ≥ max N 20 |
| `RESPAWN_MAX` (§9.5) | 6 | **8** |
| Food entries (§8.5) | 3–4 | **4–5** (≈ 104 + drops ~27 ≈ 131 vs ~100 burned per ~610-turn level; today 100 / 75) |
| Potions / scrolls | 2–3 (min 2) / 1–2 | **3–4 (min 3, ≥ 1 Heal) / 2** |
| Arrow / dagger stack | 1d4+4 / 1d2+1 | **1d4+6** / unchanged |
| Traps (§1.5) | per depth, list ≤ 6 | count × 4/3 rounded, **list ≤ 8**, ≤ 1 per room |
| `XP_NEXT` L2..L9 (§4.1) | 40/100/200/340/500/700/920/1,150 | **55/135/270/460/675/945/1,240/1,550**: `LVL_EXP(d) = d` kept |
| FED HP regen (§7) | +1 per 12 turns | **+(1 + `MAXHP` div 24) per 12 turns** (§3.1) |

Why scale, not sparse: same totals over 37 % more rooms = empty corridors that add minutes, not play, while
the food clock still burns ~100 per level. Why scale XP: BAL-1/B20 assume hero level = depth.

### 3.1 Regen vs max HP (BSIM1 interaction; folded in by user decision)
BSIM1 found that the flat FED regen (+1 HP per 12 turns) punishes max HP: a full heal of `MAXHP` costs
`12·MAXHP` turns = `2·MAXHP` FOOD, so a bigger hero rests longer, burns more food and enters fights at a
lower HP fraction. Mage sim (n = 2,000): +0 HP 0.376, **+30 HP 0.237** (D3 Vampire Lord), +30 with
`FED_REGEN` 4 0.66. LARGER-D adds ~160 turns per depth, which stretches the same clock further.
**Ruling: regen scales with max HP, food scales with rooms, not both with rooms.** FED regen per 12 turns =
`1 + MAXHP div 24` (Mage 16 → 1, 40 → 2; Warrior 70 → 3): a full heal is ~250–290 turns (~45 FOOD) at
any size, the same shape as the MP rule (`+1 + MAXMP div 16` per period, §7). Food stays ×1.35 (§3).
FED-only and the HUNGRY/WEAK halts stay. `FED_REGEN` 4 (+3 per 12) overshoots (0.66 vs the ~0.40 target).
Sim the divisor 16/24/32; first food knob if starvation shows: 4–5 → 5–6.

**Balance gate (before any Z80):** `tools/balance_sim.py` with 12-room levels, §3 table and §3.1 regen, 10k ×
2 seeds, average policy. Pass = W and M ≥ 35 % and within ±3 of BAL-1 FINAL (W 41.1/41.5, M 40.1/38.8),
gap ≤ 3; also the BSIM1 +30 HP Mage case must not fall below +0. Knobs in order: regen divisor, `XP_NEXT`
×1.35 → ×1.25, potions min 3 → 4, Heal +12 → +13, counts −1 on D4/D7.

## 4. Level-state memory (engineer gives exact figures)

budget.md §6: 24–32 B/room + 4 B/floor item. Measured layout: `ROOM_DESC` 16 + `LP_REC` 9 + `ROOM_VISITS`
1 + `TRK_W` 1 = **27 B/room**. 3×4: +81 B rooms, `EDGE_TAB` 6 → 8, `TRAP_LIST` +4, `FLOOR_LIST` 32 (keep
unless the item sweep loses > 1 %; else 40 = +32) → **≈ 90–125 B**. 4×3: same +1 edge byte. 4×4: ≈ 250–300 B.
Constraints: (1) `ROOM_DESC` is read via constant `ld h, $6D`: 192 B must stay in one page (e.g.
`$6D40..$6DFF`, header after it). (2) Level state is read with any bank paged at `$C000` (room build, bank-3/6/7
code, scrolls), so **it must stay in bank-5 low RAM, not move to B0_FREE**. Low RAM has tens of bytes spare,
so the room is made by moving an equal amount of cold low-RAM code (`lowram_code`, 3,619 B) to B0_FREE via
FARB0 (+~20 % for stubs). (3) Code: bounds `9`→`12`, bottom `6`→`9`, Sanctum `6+2·rnd`→`9+2·rnd`; E +20–40 B
cold, ~0 B bank 2. Pools do not grow (kinds per level unchanged). Engineer confirms every `cp 9`/`ld b,9`
site, `TURN_COUNTER` width (~4,900 turns), and that no other table is sized 9.

## 5. Joint budget with NEW-MON3 (per amendment (1): joins, cap 5 kinds on D4–D7)

Key point: **fund the FRT page and new code from the existing B0_FREE carve, not by moving `POOL_START`**.
The carve already sits below `POOL_START` `$FC3E`, so using it costs the pool 0 B; the `POOL_CAP −256 on
every level` route in new_monsters.md §2.3 predates the carve and is no longer needed.

| Consumer | Bank | A | B 3×4 / 4×3 | B 4×4 | Remains after (B 3×4 column) |
|---|---|---|---|---|---|
| NEW-MON3 frames, D4/D5/D6/D7 (Imp 1,088, Garg 1,472, Wraith 1,280, dust 96, spark 64) | pool 0/4/6 | +1,184 / +2,848 / +2,720 / +1,376 | same | same | post-C slack ≥ 2,976 every level → worst **D6 ≥ 256** (joins; plan X there ≈ 2.4–2.9 KB); D8 untouched 2,976 |
| FRT page (fids 145–160) | bank 2 | +256, paid by moving 256 B bank-2 cold code | same | same | bank 2 ≈ 9 − 2 (`rk_tab`) = ~7 B |
| ↳ moved bank-2 cold code | B0_FREE | 256 | 256 | 256 | |
| G-1/F-1/A-1/P-1 code | R6 or B0_FREE | ≈ 250 | 250 | 250 | |
| names/KXP/seq/units + Frost Charm text/icon | cold (b0/b3/b7) | ≈ 110 | 110 | 110 | |
| 9 frame descriptors (+45) + extra level state | bank-5 low RAM | 45 + 0 | 45 + 90–125 | 45 + 250–300 | 0 net (break-even by reclaim) |
| ↳ low-RAM cold code moved out (×1.2) | B0_FREE | ≈ 55 | ≈ 165–205 | ≈ 355–415 | |
| generator code delta | cold | 0 | ≈ 40 | ≈ 60 | |
| **B0_FREE used / left (of 11,958)** | | **≈ 670 / 11,290** | **≈ 820–860 / ≈ 11,100** | **≈ 1,030–1,100 / ≈ 10,860** | |

**Verdict: all three options fit together with NEW-MON3.** Binding limits are not B0_FREE but (1) the D6 pool
with 5 kinds (lower bound 256 B; engineer measures post-C D6, falls back to plan X on D6 only if < 256) and
(2) bank 2 (~7 B left after the FRT page). Rooms never touch the pool. Engineer confirms: post-C per-depth
pool slack, that `POOL_CAP` 31,712 excludes the carve, R6 free space, and the low-RAM code moved.

## 6. UI and interactions

- **No level map/minimap exists**; level card and depth readout have no grid assumption. End card (stats2.md):
  no room stat; TURNS grow (~4,900) and must fit the field; XP (~1,650 expected) under the 9,999 cap.
- **AI-SEEK2:** in-room only (`ROOM_CUT`): no change. **NEW-MON3:** cap bounds the pool, not the count;
  new kinds appear more often, so the D6/D7 freeze and Imp risks get more exposure (balance gate).
  **DECOR2:** per-room seed, id cap 28, per-room CPU unchanged; R4's `(rnd + room id) mod 3` repeats down a
  column as today (one more room per column). **ROOM-MEM, TUT0, trickle:** logic unchanged.

## 7. Tests and tools (named only, not cold-read)
Tools: `tools/levelgen.py`, `tools/levelcheck.py`, `tools/items_model.py`, `tools/balance_sim.py`,
`tools/decor_sweep.py`, `tools/decor_density.py`. Tests with 3×3/≤ 9 assumptions (grep hits):
`tests/levelgen_test.py`, `levelgen_z80.py`, `lp.py`, `roommem.py`, `trickle.py` (`TRK_W`), `world.py`,
`game.py`, `game_lib.py`, `boss.py`, `pt_bot.py`, `tier_respawn_model_test.py`, `budget.py`, `floor1.py`,
`drip.py`, `hunger.py` (+ regen), `b19.py`, `b19c.py`, `endcard_k.py`. `tests/tut0_level.py` should pass
unchanged. **Every seeded generated golden re-baselines.**

## 8. Impacts (other docs; not edited here)
game.md §1 Levels/Level; §1.1 Tree, Lair, Level shape (6–8 → 9–11), L1 rules row, L2 rows, I1, Stored per
level; §1.5 traps; §4.1 `XP_NEXT`/expected XP; §7 FED regen; §8.5; §8.11 food line; §9.4/9.4.1/9.4.2;
§9.5; §10. budget.md §6. memory-map.md (`LVL_STATE`, room grid, `EDGE_TAB`, `LVL_NROOMS`, LP contracts,
`TRAP_LIST`, low-RAM code moved to B0_FREE). new_monsters.md §2.3 (fund from the carve). plan.md (new task).

## 9. Open questions for the user (defaults in bold)
1. Grid: **3 wide × 4 tall, 10–12 rooms (~82–89 min)**, or 4×3, or 4×4 (12–16, ~104–113 min)?
2. Content: **scale monsters and consumables ×~1.35, keep books/gear/bow/uniques**, or keep totals (sparser)?
3. XP: **scale `XP_NEXT` ×1.35**, or keep thresholds (hero ~+1 level, easier)?
4. Regen: **FED regen `1 + MAXHP div 24` per 12 turns, food ×1.35 with rooms**, or flat regen + more food
   (5–6 per level), or `FED_REGEN` 4 (sim 0.66: too easy)?
5. Loops: **keep 0–1 extra edge per level**, or 0–2 (less backtracking, a bit less playtime)?
6. Order: **NEW-MON3 first, then LARGER-D** (shares the balance gate; D6 pool measured first)?
7. Gate: **W and M ≥ 35 %, within ±3 of BAL-1 FINAL, BSIM1 +30 HP case ≥ +0 case** before any Z80?
