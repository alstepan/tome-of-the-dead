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

### 2.1 Level key (user 2026-11-15: "avoid quick pass through without visiting most of rooms")

Keys and locked doors go live on D1–D8 (rev 2026-11-15, user: a lock may sit mid-route, and there may be several).
This **supersedes game.md §1.4 "Key / locked door"**, game.md §1.1 "Key room" (the farthest leaf, with the lock always
on the lair door) and L1 step (7)'s note "key gating only matters from 3F". The grate and the boss stay the final gate.
**Rev 2 (user 2026-11-15, "clarity and non-linear routes from the start"):** keys and locks are **coloured** (2 colours) and
2-lock levels may be **non-linear**. Rows marked *rev 2* replace the rev-1 text kept above them as history.

| Topic | Rule (KEY, designer decision 2026-11-15) |
|---|---|
| Graph `G` | Rooms + tree edges (horizontal and vertical) + the 0–1 loop edge. Pits only drop storey 0 → 1 inside a room, the arrival shaft enters the start room, and the exit shaft leaves the level, so `G` holds **every** room-to-room link. `P` = the BFS-shortest path start → lair in `G` |
| Lock candidates | An edge `e` may be locked iff it is (a) on `P`, (b) a **tree** edge, (c) **horizontal** (`T_DOOR_LOCK` plank art; shafts can't hold planks) and (d) a **bridge** of `G` (not on the loop's cycle). Removing `e` splits `G` into a start side and a lair side, so nothing (loop, shaft, fall) bypasses it. The lair door is a valid candidate when it qualifies |
| Lock candidates *rev 2* | (b)–(d) stand; (a) "on `P`" is **relaxed to "needed"**: a lock off `P` is allowed only if it guards the region holding the other lock's key. Every lock must be needed: with lock `j` treated as a permanent wall, the key fixpoint (proof row) must fail to reach the lair. **Locked treasure vaults (an unneeded lock off the route) are OUT of scope**, a later add-on |
| Lock count `m` | **D1–D3: 1. D4–D8: 2 if `n ≥ 11` and a valid pair exists, else 1.** Never more than 2, because 3+ fetches in a scrolling side-view are tedious. Locks are ordered along `P`: `L1` is nearer the start. The regions are `R0` (start side of `L1`), `R1` (between), `R2` (lair side of the last lock) |
| Key rooms | Key `j` lies in `R(j−1)` (the region that is open before `Lj`). It is the room there **farthest (BFS within the region) from `Lj`'s near-side room**, i.e. the deepest leaf and the longest detour. Excluded: start, lair, Sanctum; ties lowest id. A lock set is valid only if every region it needs has a candidate. Stored as `LVL_KEYROOM[0..1]` (`ROOM_NONE` if unused) |
| Lock choice | Enumerate the valid sets (1 edge, or 2 ordered edges). `F` = the distinct rooms on the BFS paths start → K1 (→ K2) → lair in `G` with all locks open. Both ends count, and a loop shortcut lowers `F`. **Pick the max `F`**; ties go to the lowest `P` index (lock 1, then lock 2). With ≤ 12 rooms and ≤ ~8 candidates this is a trivial loop |
| Placement *rev 2* (supersedes Key rooms + Lock choice) | Removing the locks splits `G` into components; `C0` holds start. **Key candidates** = rooms of `G`-degree 1 (dead ends), never start/lair/Sanctum. Enumerate every lock set (1 edge, or an unordered pair) × key-room assignment. **Valid** iff the fixpoint from start with 0 keys reaches the lair and every lock is needed. Coloured keys are never wasted, so a fixpoint success holds under **every** collection order. **Shapes (2 locks):** *linear* = both locks on `P` and key 2 lies only beyond lock 1 (rev-1 chain); *non-linear* = (b1) **branch**: one lock off `P` guards a dead-end region holding the `P`-lock's key, its own key in `C0`; or (b2) **open series**: both locks on `P`, both keys in `C0` (any order) |
| Route `F` *rev 2* | For each valid collection order, chain BFS segments start → first key → second key → lair in `G`, treating locks whose key is not yet held as walls (far-side bolt allowed); `F` = distinct rooms on the union, both ends counted. Set `F` = **min over valid orders** (the player's shortest honest route) |
| Selection *rev 2* | Score = `F` + **1 if a 2-lock set is non-linear**. Pick the max score; ties: higher raw `F`, then non-linear, then lowest `P` index of the nearer lock (off-`P` lock: its branch room's `P` index), then lowest edge index, then lowest key room ids (colour 0 first). `F ≥ F_min` is still a hard floor (raw `F`, no bonus). 2 locks on D4–D8 when `n ≥ 11` and any valid pair meets `F_min`, else 1. No valid set from dead-end keys = "no valid lock" → restart path. **Target: ≥ 50 % of 2-lock levels non-linear**; if the sweep misses, report and the designer raises the bonus to 2 (not tuned silently) |
| Colours *rev 2* | **Colour 0 = cyan, colour 1 = magenta.** Colour 0 goes to the lock the fixpoint opens first (its key is in `C0`); if both open in the same round (b2), colour 0 = the lock with the lower `P` index. 1-lock levels are cyan. Yellow was rejected: closed planks are already `$06` yellow (concept-screen §3.1), so a yellow plate reads as an ordinary door; red = seal, green = poison, blue is too dark on black |
| Generic keys *(superseded by Coloured keys, rev 2)* | `IT_KEY` is a **count 0–2**, not coloured, and needs no new art. This is safe because of the ordering: `Lj+1` can only be reached through `Lj`, and key `j+1` lies beyond `Lj`. The bag `KEY` slot shows the count (`KEY 2`); the panel icon is lit while the count is ≥ 1 |
| Coloured keys *rev 2* | `IT_KEY` becomes a **2-bit held mask** (bit 0 cyan, bit 1 magenta). **Lock plate:** only the `T_DOOR_LOCK` cell takes the colour, attr **`$45`** (cyan) / **`$43`** (magenta), drawn in **both** rooms (1 cell per side, 2 per door); the other plank cells stay `$06`. Once unlocked, that cell draws as a plain plank-R `$06` when the door is closed. **Panel** cell (30, 19), one key glyph: ink `$45` or `$43` for the held colour; both held = **`$EB`** (FLASH + BRIGHT, paper cyan, ink magenta: the hardware swaps the colours every 16 frames, 0 CPU); none = unlit as before. **Bag `KEY` slot:** one line per held key, `CYAN KEY` / `MAGENTA KEY` in its ink (0 new glyphs) |
| Far-side bolt *rev 2* | A lock bars only its **start side** (the side of `C0`). From the far side the Open-door action opens it with no key (1 turn, ordinary open, no line, never relocks). Without this a teleport into a b1 dead end would softlock. Supersedes "locked from both sides" below |
| Coverage minimum | **`F_min = n − 4`** (10 → 6, 11 → 7, 12 → 8: 60–67 %) over the full forced route with every detour. If `F < F_min` **or no valid lock exists**, the tree **restarts** in-stream (no reseed): pass 2 reruns steps 3–8 with the DFS **Warnsdorff bias** (pick the unvisited neighbour with the fewest unvisited onward neighbours; ties `rnd`), continuing GEN_RNG. Pass 2 is accepted as is, and if it still has no candidate the level is keyless (sweep target 0). Pass 1 has no fork bias, so side branches and their items still pull players in |
| Sweep (300 seeds × D1–D8) | Assert `F ≥ F_min` after pass 2 and reseeds 0. Report the `F/n` histogram (mean **target ≥ 75 %**), the restart rate (**≤ 10 %**), the keyless count (**0**), and the share of D4–D8 levels with 2 locks and with a lair-door lock, and (*rev 2*) the share of 2-lock levels that are non-linear, split b1 / b2 (target ≥ 50 %). If a target misses, report back to the designer rather than tuning silently |
| No-softlock proof (levelcheck) | Simulate per level: the hero starts with 0 keys in **each** region `R0..Rm` (start, plus teleport arrival). Repeat: flood-fill the open rooms, take the keys there (first entry), and open any adjacent lock while the count is > 0. Assert the lair is always reached. By induction each `Rj` (j < m) holds key `j+1`, and the lair is in `Rm` |
| Proof *rev 2* (supersedes the row above) | **Key-set fixpoint:** `R` = flood of `G` from start, held = ∅. Repeat until no change: held ∪= keys of key rooms in `R`; open every lock `j` with an end in `R` whose colour ∈ held, or whose far side is in `R` (bolt); re-flood. Assert lair ∈ `R`. Repeat from each component as the start (teleport, 0 keys) and assert the same. Also assert each lock is needed (fixpoint with lock `j` walled fails) |
| Monsters | A locked edge is a **wall** to every monster, `KF_OPENER` included: they can't open it, path through it or attack through it. The boss stays posted on the grate (§9.2) |
| Bump, no key | **0 turns**, no monster acts. Log `THE DOOR IS LOCKED` (existing), through the same `LOCK_SHOWN` path and latch as the D8 Sanctum door. The door is locked from both sides. *Rev 2:* start side only (bolt); holding only the other colour counts as no key (same line, 0 turns) |
| Bump, with key | The Open-door action (1 turn, game.md §2.3): **one key consumed** (count −1; *rev 2:* the matching colour's bit cleared). `EG_LOCK` is cleared and the door is **open**. It stays unlocked for the rest of the level across re-entry (edge state lives in the level state), then behaves as an ordinary door (`C` closes it, `KF_OPENER` opens it). It never relocks |
| Pickup | Granted on first entry into a key room (game.md §8.11 Q1), with no floor item. The flags `LF_KEY_TAKEN` become 2 bits, one per key room |
| Byte hint (engineer sizes) | Level state +1 B (2nd key room) + 1 bit (2nd taken flag); `IT_KEY` is already a counter; `EG_LOCK` already exists per edge (0 B); +19 B unlock string; the generator gains bridge + region BFS + enumeration (bank 3, est. 250–400 B) |
| Byte hint *rev 2* (supersedes the row above) | Level state +1 B (2nd key room) + 2 bits (taken) + 1 bit per lock edge for its colour (or 2 B lock-edge-by-colour, engineer picks); `IT_KEY` mask 0 B; strings **+92 B** whole (or **+46 B** as fragments `YOU FIND A ` 11 · ` KEY` 4 · `YOU UNLOCK THE ` 15 · ` DOOR` 5 · `CYAN` 4 · `MAGENTA` 7 if the log already composes); generator fixpoint + shape test + scored enumeration (≤ 28 pairs × ≤ 36 dead-end assignments) est. **350–550 B** bank 3; panel/bag colour code est. 40–60 B |

**Messages** (≤ 32 chars, uppercase, game style):

| Event | Line | Bytes |
|---|---|---|
| Key room, first entry | `YOU FIND A KEY` (replaces `YOU FIND THE LAIR KEY`, since a key may open a mid door) | 14 (−7) |
| Bump locked, no key | `THE DOOR IS LOCKED` (existing, reused) | 0 new |
| Bump locked, with key | `YOU UNLOCK THE DOOR` (**new**) | 19 |
| *rev 2* key room, first entry | `YOU FIND A CYAN KEY` / `YOU FIND A MAGENTA KEY` (supersede `YOU FIND A KEY`) | 19 / 22 |
| *rev 2* unlock | `YOU UNLOCK THE CYAN DOOR` / `YOU UNLOCK THE MAGENTA DOOR` (supersede `YOU UNLOCK THE DOOR`) | 24 / 27 |

**Edge cases.**

| Case | Rule |
|---|---|
| D8 | The Sanctum door is **sealed, not locked**: it is never a lock candidate (it is off `P`), it opens only on the Archmage's death, and **a key never opens it** (existing sealed line, no key consumed). Locks may include the 10–E lair door. Key rooms exclude `S` |
| D0 tutorial | Keyless: both `LVL_KEYROOM` = `ROOM_NONE`, and `EG_LOCK` is never set. The D0 blob is untouched |
| Teleport | **Allowed, no exclusion.** Landing beyond a lock skips that key, but scrolls are rare, so this is a rare reward or gamble. The proof row covers every 0-key arrival region. In the lair the exit is the boss grate. *Rev 2:* safe in b1 dead ends via the far-side bolt |
| Falls / shafts | No bypass by construction: locks sit on bridges of `G`, and `G` holds every vertical, shaft and loop link. Levelcheck asserts that each lock edge is a bridge |
| Death / reload | Single-life run, so nothing to save. A new game regenerates from the seed |

**Tests (named only).** levelcheck: `K1` every lock is a horizontal tree bridge on `P` · `K2` `m` per depth/n,
≤ 2 · `K3` key `j` ∈ `R(j−1)`, deepest by BFS (lowest id), never start/lair/Sanctum · `K4` lock set = argmax `F` · `K5` `F ≥ n − 4`,
reseeds 0, histogram/restart/keyless stats · `K6` no-softlock simulation from every region · `K7` D0 none, D8 seal
never `EG_LOCK`. Emulator: `key_pickup_first_entry` · `lock_bump_nokey` (0 turns, line) · `lock_unlock_key` (1 turn,
count −1) · `lock_persists_reentry` · `lock_opener_blocked` · `two_keys_count` (D4+) · `d8_lock_and_seal` ·
`teleport_past_lock_no_softlock`. *Rev 2:* `K1` → horizontal tree bridge, each needed · `K3` → keys in dead ends, fixpoint-valid ·
`K4` → argmax score + tie chain · `K6` → key-set fixpoint from every component · `K8` colour rule (cyan first) · `K9`
non-linear share ≥ 50 %, b1/b2 split. Emulator: `two_keys_count` → `two_keys_colours` (panel `$EB`, bag lines) ·
`lock_wrong_colour` (0 turns) · `lock_plate_attr` (`$45`/`$43` both sides) · `lock_far_side_bolt` · `teleport_b1_deadend`.

**Decisions (user 2026-11-15): Q1 (c), Q2 n − 4, Q3 0 turns, Q4 allowed APPROVED; Q5 default (no hint) taken.**
1. Lock model: (a) lair door only, 1 lock; (b) 1 mid-route lock (the lair door allowed); **(c) 1 lock on D1–D3, up to 2
   on D4–D8 when `n ≥ 11`, the lair door allowed as either.**
2. Coverage floor: **`F_min = n − 4`**, with a mean target of ≥ 75 %. The alternative `n − 3` forces more backtracking.
3. Bump without a key: **0 turns** (not 1).
4. Teleport past a lock: **allowed** (vs excluding the regions beyond any lock that is still shut).
5. A hint in the locked line (`LOCKED - FIND A KEY`, 19 B)? **No: reuse `THE DOOR IS LOCKED`.** The panel key cell is the hint.
6. *(rev 2, DECIDED by the user 2026-11-15: cyan + magenta; far-side bolt yes; red rejected because it clashes with the sealed Sanctum)* Colours: **cyan + magenta** (yellow clashes with the `$06` planks), or yellow + cyan as first suggested?
   Far-side bolt: **a lock opens keyless from its far side**, or exclude teleport from b1 dead ends instead?

#### 2.1 rev 3 (designer 2026-11-15): supersedes rev 2 Placement keys, Selection, Coverage pass 2 and L1 steps (3)/(5); rest kept

Rev 2 sweep (`select_keys`, D1–D8 × 300): **56 % keyless**, 15.5 % pass 2, 2-lock 65 / 1,500 on D4–D8, ~50 % lair-door locks.
Causes: start sides of snake trees have no dead ends, Warnsdorff pass 2 makes snakes, and ring loops erase bridges.

| Topic | Rule (rev 3) |
|---|---|
| (3) DFS branch | In **every** pass, at the top of each DFS iteration with `len(stack) ≥ 4`, draw `b = rnd(BRANCH_ODDS)` (**4**, pass 1; **2**, pass 2). If `b == 0` and `stack[2]` has a free neighbour, `cur = stack[2]`, else `cur = stack[-1]`. Then as before: `cur` has none free → pop (it is the top; no draw), else `rnd(k)`, link, **push**. No draw when `len(stack) < 4`. Warnsdorff is **dropped** |
| (5) Loop split | 5a: mandatory loop exactly as now (`mand` → pick draw). 5b: lair (step 8 tiers, on adjacency) and **lock select on `G5a`** (no draws). 5c: if not `mand`: odds draw; on a loop the candidate list (same scan order) keeps only pairs whose two rooms are on the **same side of every chosen lock**, then `rnd(count)` if count ≥ 1 (no pick draw if 0). So an optional loop can never bypass a lock or erase a bridge |
| Lock candidates | Horizontal tree bridges of `G5a`. A 1-lock set must be on `P` (otherwise not needed). Pairs: any 2 (the "needed" test filters) |
| Key rooms | `best(X)` = the room in `X` (never start, lair or `S`) maximising (**dead end**, BFS distance in `G5a − e_j` from `e_j`'s near room, −id). 1 lock: `best(near(j))`. Pair `(i, j)`: lock `j`'s candidates are `best(near(j) ∩ far(i))` and `best(near(j) − far(i))` (each if non-empty). Test the ≤ 4 combos with distinct rooms by the fixpoint. No dead-end-only rule |
| Score | `score = F + 1 (b1/b2) − 2 (a lock on the lair door)`. Choice: max score, then max `F`, then rev 2's tie order. Floor `F ≥ n − 4` (user decision) is kept, raw. 2 locks if D4–D8, `n ≥ 11` and a pair meets the floor, else 1 |
| Fail ladder (in-level) | Pass 1 has no set meeting the floor → pass 2 (draws 3–8 rerun, `BRANCH_ODDS` 2). Pass 2 has no **valid** set (floor ignored) → **Restart** from draw 1 (existing mechanism, stream continues). So keyless = 0 by construction |
| RNG (T4 port) | New draws: the `b` draw only (inside step 4, before the free-neighbour scan, so it is also made on iterations that end in a pop). `stack` is a list ≤ 12 B, and `stack[2]` is a fixed index. Step 5c's filter runs **before** `rnd(count)`. Lock and key select draw nothing. `levelgen_test` pins the draw count per seed |
| Sweep targets | keyless **0**; pass-2 rate **≤ 10 %**; full Restarts (all causes) **≤ 3 %**; mean `F/n` **≥ 75 %**; D4–D8 2-lock share **≥ 40 %** of all levels (≈ 60 % of `n ≥ 11`), and **≥ 60 %** of those b1/b2; lair-door locks **≤ 35 %** of all locks; reseeds 0. Report the per-depth table |
| Tuning ladder (junior, in order; stop when green; report each step) | 1. 2-lock share low → `BRANCH_ODDS` pass 1: 4 → 3 → 2. 2. Pass-2 rate high (floor misses) → key `best` drops the dead-end term (distance only). 3. Lair-door share high → penalty 2 → 3; if 2-lock non-linear low → b1/b2 bonus 1 → 2. 4. Still red → **stop and report**; lowering the floor to `n − 5` needs the user |

Tests: `K3` → key = `best` of its candidate list · `K4` → argmax rev-3 score · `K10` no optional loop crosses a lock ·
`K11` the GEN_RNG draw count per seed matches the reference (the `b` draws included).

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
