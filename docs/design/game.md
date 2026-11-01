# WazHack/ZX — Game mechanics (M1, Stage 2)

> Game-designer deliverable. **Authoritative mechanics for Stage 3.**
> **Rev 2 (2026-10-01):** user answers applied. 8 levels; 2 unique bosses + golden bosses;
> monster resistances and Drain Life; projectiles and impacts are real sprites; black walls
> with dithered brick patches (concept-screen §3.3).
> **Rev 3 (2026-10-02):** round-4/5 review applied. Approved 9+9+6 panel (24×16 icons, info
> line, 16×16 gear); custom 6×8 text font + 8×16 menu font (§3.4); Mage keeps BAG (10 icons);
> Zombie → **Vampire**; gold glow = SYNC; ZX0 in blocks of 3–4 frames (§11); **finite
> ammunition** (§6.3, §8.5); Death Knight redesigned (5 frames); hunger stage names.
> **Rev 4 (2026-10-03):** user 2026-10-03 adds **status effects** (§6.4, 3D), **traps** (§1.5,
> 3E), **blessed/cursed gear as known states** (§8.7, 3E) and **light identification** of
> potions/scrolls (§8.8, 3E); details are designer decisions 2026-10-03.
> **Rev 5 (2026-10-03):** user 2026-10-03 replaces the cursed-gear rule (§8.7: hidden ±
> modifier revealed on equip, sticky until **blessed** by Enchant or **shattered** by a
> projectile hit; no regen penalty) and adds **XP and hero levels** (§4.1, max level 9),
> which replace boss-kill growth and the tier power level `PL` (§9.6), **gear wear only from
> special attacks** (§8.10) and **book-gated abilities with ranks from repeat books** (§4,
> §5, §6.3). Numbers are designer decisions 2026-10-03.
> It supersedes `prototype.md` wherever they differ. Anything not restated here keeps the
> PROTO rule: turn phases §3.2, ladders §3.4, the follow and materialise rules §3.7, F9
> zoning §4, frame rules §5.1–§5.4, line of attack §6.1, AI §6.4, the animation state
> machine §7. `foundations.md` F1–F9 still bind.
> Inputs: `plan.md` Stage 2, `budget.md`, E0 (logic runs in the input tick; heavy fight
> 125k T = 88 %), the user decisions (ZX0 sources, cold code out of bank 2, per-level pool)
> and the artist's round-2 measurements. Layout: `concept-screen.md`. The engineer assigns
> bytes and addresses in `memory-map.md`. **E** = estimate, **M** = measured.

---

## 1. Run structure

| Item | Decision | Why |
|---|---|---|
| Levels | **8** (D1–D8), each freshly generated, one way down | user wants it longer: ~65 rooms, **~60–65 min**; one level resident at a time |
| Level | **3×3 grid of room cells, 7–9 rooms** | ~1 KB of level state (budget §6) |
| Room | one screen, **2 storeys of 9 rows** (8 air + 1 floor) + 6-row panel (§2.1) | user decision; 2 jump rows |
| Going back up | **no**; the arrival shaft top is rubble | the previous level is discarded with its pool |
| Save | **none; permadeath**. Death → death screen (`KILLED BY … ON D5, TURN n`) → main menu | user |
| Seed | master seed = `FRAMES` when START is pressed; level seed = f(master, depth). Test flag `SEED_FIXED` forces the compile-time seed (F3) | a fixed seed would replay the same dungeon every game |
| Win | D8: kill the **Necromancer Archmage** → the Sanctum seal opens → **destroy the Tome of Absolute Death Magic** (§1.3) → the exit gate opens → leave through it → `GS_WIN` (WIN2, user 2026-11-01) | user |

### 1.1 Generation rules (F6, per level, deterministic from the level seed)

| Step | Rule |
|---|---|
| Tree | random DFS spanning tree over the 3×3 cells from a random start, 7–9 rooms, + 0–1 extra edge (a loop). Leaves = **dead-end rooms** |
| Edges | horizontal: open edge on storey `s ∈ {0,1}`; **1 in 3 carry a door** (§2.3). Vertical: up-exit `{c,0}` below + down-exit hole `{c,2}` above, same `c` |
| Start | the DFS root, **on the top grid row (L1, 2026-10-05)**, 0 monsters. D2–D8: arrival shaft from above, rubble-capped |
| Lair | **on the bottom grid row (L1, 2026-10-05; tiers in the L1 rules row)**, the farthest leaf (BFS) with a horizontal tree edge: boss + **level exit** = down-shaft `{c,2}` under a **GRATE** that opens when the boss dies. **The grate is SHUT (`T_GRATE_SHUT`, solid) while the boss lives; this is the rule (BOSS-GUARD 2026-10-29; the §1.4 "always open" row was the 3B stand-in only).** The boss is posted on the grate and guards it (§9.2 "Boss guard") |
| Key room | the farthest other leaf (else the farthest non-start room): holds the **level key** (rev 2026-10-20: found on first entry, no floor item, §8.11 Q1). The lair edge is a **locked door** |
| D8 Sanctum | an extra leaf off the lair behind a **sealed door** (opens on the Archmage's death); holds the Tome. **D8 keeps its exit** (WIN2, user 2026-11-01): the lair's grate over the down-shaft stays shut through the Archmage's death and opens only when the Tome is destroyed; leaving through it = `GS_WIN` |
| **Level shape (L1, user 2026-10-05)** | The level exit (lair) is **always on the bottom grid row** (ids 6–8), and **no room is above the entry room**: the hero always heads down into the dungeon |
| L1 rules (designer decision 2026-10-05) | Grid id `r = 3·row + col`, row 0 = top. **(1) Start = top row:** `start = rnd(3)` (replaces `rnd(9)`), so nothing can be above it; the start room has no up-exit; its row-0 horizontal neighbours are allowed (they are beside it, not above). Arrival shaft D2+ unchanged (storey 0 of the start room, rubble-capped). **(2) Room count:** `n = 7 + rnd(3)`; **D8: `n = min(7 + rnd(3), 8)`** (the Sanctum cell is reserved, see (5)). **(3) DFS growth:** the random DFS from `start` runs `while stack and not done`, where `done` = `|visited| ≥ n` **and** two horizontally adjacent bottom-row cells (6–7 or 7–8) are visited. A full DFS reaches all 9 cells, so `done` is always reachable; the room count stays 7–9. **(4) Bottom-row horizontal edge:** after the tree, if no tree edge joins two bottom-row rooms, the loop edge becomes **mandatory** and is drawn with `rnd(len)` from the unlinked present bottom-row pairs (the `LOOP_EDGE_ODDS` roll is skipped); otherwise the loop step is unchanged. Still 0–1 extra edges. **(5) D8 Sanctum:** before the DFS, reserve `S = 6 + 2·rnd(2)` (bottom-row end cell); the DFS never enters `S`; `done` additionally needs cell 7 and the other bottom end visited. The lair is then always cell 7 (the only bottom room next to the free `S`); the Sanctum hangs off its free side behind the sealed door. **(6) Lair tiers (replace F6 gap (1) tiers):** (a) farthest (BFS) **bottom-row** non-start leaf with a horizontal edge; (b) farthest bottom-row room with a horizontal edge (a through-room lair is fine; the boss never follows); ties = lowest id; D8 also needs `sanctum_ok`. (3)+(4) guarantee tier (b) exists, so **lair reseeds must be 0**; the reseed path (seed+1, ≤ 16) stays as a safety net only. Levelcheck asserts over the seed sweep: start on row 0 (so no room above it), lair on row 2, room count 7–9, lair has a horizontal edge, D8 lair = 7 with `S` free, lair-reseed count = 0; the junior reports Restart counts (feature/potion) before vs after. **(7) Lair door:** the lair's horizontal edge toward its BFS parent if horizontal, else its lowest-id horizontal edge, is the lair door (key gating only matters from 3F; the grate gates the exit). **(8)** Key room, vertical links, edges, door odds, shaft cols: unchanged |
| In-room | 1–2 internal ladders `{c,1}`, `c ∈ 3..26`, ≥ 4 cols from ladders/pits · optional **pit** (3 cols, storey-0 floor, ≥ 3 clear cols on each side) · optional **dead-end block** (2–3 wall cols at an exitless edge, rubble at its foot) · decor **re-derived from the room seed** (never stored; rules in concept-screen §3.3) |
| Ladder/pit placement (designer decision 2026-10-03) | **Internal ladders are in addition to the exit shafts** (up-exit `{c,0}`, down-exit `{c,2}`, the D2+ arrival shaft). **A shaft col is never an internal-ladder col** (no continuous 2-segment ladders: keeps one ladder segment per col and no "stand over a hole with ladders both ways" state). Every ladder, shaft and pit is a **3-col footprint `c … c+2`, `c` = its left col** (pit: the 3 hole cols; caps at `c−1`/`c+3` are floor). Two footprints that touch the same storey (storey 0: up-exit, internal-ladder hole in row 8, pit; storey 1: internal ladder, down-exit hole in row 17) keep **≥ 4 clear cols between them: `|c1 − c2| ≥ 7`**. Placement order: exits → 1st internal ladder → pit → 2nd internal ladder → dead-end block; an optional feature that finds no legal `c` in 8 seeded tries is dropped (deterministic) |
| Pit geometry (designer decision 2026-10-03) | **(1) Pit col `p ∈ 5..24`** (same range as shaft cols). Why: jump take-off/landing bodies are fully on floor, so a crossing is `x = p−3 → p+3` (or back); both `x` must lie in 2..27 (col 1/28 door-arch cells excluded from the swept box), giving `p−3 ≥ 2` and `p+3 ≤ 27`. Pits at `p<5` or `p>24` are illegal. **(2) Storey-0 clear zones:** cols `p−4 … p−1` and `p+3 … p+6` hold no ladder/shaft/hole footprint and no block (this is exactly what `\|c1−c2\| ≥ 7` already guarantees against footprints; the generator additionally checks blocks). **(3) Dead-end block + pit in one room:** allowed only if the block's inner face keeps the jump zone clear: left block of width `w` (2–3) needs `p ≥ w+4`; right block needs `p ≤ 25−w`; else the block is dropped (it is placed last). **(4) Storey-1 landing:** a fall lands body `p … p+2` on storey 1, which must be plain solid floor with ≥ 1 clear col each side: every storey-1 footprint (internal ladder, down-exit hole, arrival shaft if on storey 1) has `\|c−p\| ≥ 7`, and any storey-1 block keeps ≥ 1 clear col from `p … p+2` (same formulas as (3)). **(5) Reachability:** with (1)–(4) the pit is always jumpable both ways AND the fall lands on walkable storey-1 floor, which spans the room to a ladder, so the hero is never cut off. Levelcheck must model the jump as exactly `p−3 ↔ p+3` and fail otherwise |
| Reachability | storeys span the full width except pits and blocks; ≥ 1 internal ladder; a **narrow** (3-col) pit is always jumpable, and falling only leads to storey 1. The hero can reach every exit; monsters may be cut off by a pit or block (intended). L2 (below) adds mid-room blocks and wide pits, with the same guarantee by walk + climb alone |
| **Mid-room block (L2, user 2026-10-06; rules designer decision 2026-10-06)** | A wall block in the middle of **storey 0** (floor to ceiling of storey 0, rubble at the foot on **both** faces, decor only), splitting storey 0 in two. Storey 1 is never blocked, so it joins the halves. **(1) Width `w = 2 + rnd(2)` (2–3 cols), left col `b`.** **(2) Eligible room:** not start, lair, Sanctum; has no wide pit (**designer decision 2026-10-07: an edge block no longer excludes; a narrow pit is removed (pit = 0) when the block is placed, restored if placement fails**); has **1 or 2 internal ladders**: with 2, `c1 < c2` are used as is; with **1, L2 adds the missing 2nd ladder** at a seeded col `n ∈ LAD_COL_MIN..LAD_COL_MAX` legal under the normal `FEAT_GAP` rule on both storeys (`c1, c2 = sorted(lad1, n)`), kept only if the block then fits (else lad2 stays 0). An exit shaft never counts as a crossing: a half without an internal ladder would be stranded. Earlier output is no longer byte-identical in such rooms (lad2 / pit fields only; LP budgets are computed after and may shift). **(3) Hero never cut off:** the block lies strictly between the ladders with ≥ 3 clear cols to each footprint: `b ≥ c1 + 6` and `b + w + 3 ≤ c2` (needs `c2 − c1 ≥ w + 9`). Each half therefore owns a ladder down to storey 1, so every storey-0 point (incl. both horizontal edges and the up-exit) is reachable by walk + climb with no jump and no fall. Walkers may be cut off (intended). **(4) Other storey-0 footprints** (up-exit, narrow pit) keep ≥ 3 clear cols from the block faces; a narrow pit is not allowed in the room anyway (2). **(5) Items/traps:** reject any `b` with a floor item or trap on storey 0 in cols `b−1 … b+w`. Spawns (§9.4.3) treat the block as wall. **(6) Odds, per eligible room in id order, new pass after traps and LP (GEN_RNG; 8 seeded tries for `b`, then dropped):** D1 none; D2–3 1 in 4; D4–8 1 in 2 (designer decision 2026-10-07, raised; target ~0.5–1 per level on D4+, ~0.2 on D2–3, junior tunes N on a 300-seed sweep); **≤ 2 per level**. Only one L2 feature per room (wide pit is rolled first) |
| **Wide pit (L2, user 2026-10-06; rules designer decision 2026-10-06)** | **Unjumpable** pit, **in addition to** the narrow 3-col jumpable pit (kept, unchanged). Storey-0 floor only, holes `p … p+W−1`, `W = 4 + rnd(3)` (**4, 5 or 6**), caps `PIT_L` at `p−1`, `PIT_R` at `p+W`. Descriptor gains a width field (3 = narrow). **(1) Eligible room:** not start, lair, Sanctum (**designer decision 2026-10-07: narrow pit is replaced, edge block allowed, 1 ladder + L2-added 2nd ladder allowed, exactly as the mid-block rule above; the 8 tries also re-roll the added ladder col**); has 1 or 2 internal ladders, `c1 < c2` after adding. **(2) Placement:** `p ≥ c1 + 7` and `p + W + 4 ≤ c2` (≥ 4 clear cols from each ladder footprint: the narrow rule extended to width; far-side ladder gives the way back up). So `p ≥ 10`, `p ≤ 22 − W`, needs `c2 − c1 ≥ W + 11`. **(3) Storey-1 landing:** every other footprint touching storey 1 (internal ladders, a row-17 down-exit hole) is ≥ 4 clear cols from `p … p+W−1`: `c ≤ p−7` or `c ≥ p+W+4`; the same for any storey-0 up-exit/arrival footprint. If one violates it, the pit is dropped. **(4) Fall/stand:** the hero (3 cols) falls when its body is fully over holes: `p ≤ x ≤ p+W−3`; walkers of any width refuse every such `x`; other overlaps stand (≥ 1 floor col). Fall = §2.5 (1d4, ignores DEF), same `x`, onto plain storey-1 floor. **(5) No crossing by jump:** a jump whose span contains a wide-pit hole col ends in a fall (§2.4, user 2026-10-06); a narrow pit never cuts the arc. **(6) Items/traps:** reject `p` if a floor item or trap is on storey 0 in cols `p−1 … p+W`. **(7) Odds, per eligible room in id order, same pass as the mid-block, rolled first (designer decision 2026-10-07, raised):** D1 none; D2–3 1 in 8; D4–8 1 in 2 (`W` and `p` seeded, 8 tries); **≤ 2 per level**. Target ~0.3–0.6 per level on D4+, ~0.1 on D2–3; the junior tunes N until the 300-seed sweep lands in range. **(8) Reachability:** crossing needs no fall: left half → left ladder down → storey 1 → right ladder up (and back); a fall is only an optional one-way shortcut (1d4). So the hero is never cut off and never forced to take damage |
| **L2 invariants (levelcheck, seed sweep D1–D8)** | **I1** Grid shape unchanged: start on row 0, lair on row 2, room count 7–9, lair reseeds 0, exit/lair marking (B12: lair grate = id 26 + hint; ordinary down-exit holes plain) untouched. **I2** L2 features only in non-start/lair/Sanctum rooms with 2 internal ladders after L2 (2026-10-07: L2 may add lad2 and clear a narrow pit in its room, nothing else); ≤ 1 L2 feature per room; ≤ 2 mid-blocks and ≤ 2 wide pits per level; none on D1; `w ∈ 2..3`, `W ∈ 4..6`. **I3** Earlier generator output (tree, ladders, edge blocks, items, traps) identical to pre-L2 except, in L2-feature rooms only, an added lad2 and a removed narrow pit; LP records are derived afterwards. **I4** Geometry: mid-block `b ≥ c1+6`, `b+w+3 ≤ c2`; wide pit `p ≥ c1+7`, `p+W+4 ≤ c2`; every storey-1 and storey-0 footprint obeys the extended `\|c−p\|` clearance; no item/trap in the L2 span +1. **I5** Reachability model: nodes (room, storey, x); edges = walk (blocks are walls, fall-range `x` illegal), climb, door/edge transit; **jump `x ↔ x±6` crosses only a narrow pit**; a jump toward a wide pit is a fall edge (`x_f`), never a crossing; jump landing on a narrow-pit `p` is a fall edge; fall edge (one-way, 1d4) allowed but **not required**. Assert: from every room entry point the hero reaches every exit, the key room and the lair by **walk + climb only**, and the walk + climb graph is **strongly connected** per room (hero can always go back). **I6** No walker spawns on a fall-range `x` or inside a block |
| Shaft cols (designer decision 2026-10-03) | Exit shafts (up-exit, down-exit, arrival, level exit) use left col **`c ∈ 5..24`** (footprint cols 5..26), a subset of the internal-ladder range 3..26. Why: door cells occupy cols 0–1 / 30–31, and a hero arriving through a horizontal exit stands at x = 1 (cols 1..3) or x = 28 (cols 28..30); `c ≥ 5` / `c+2 ≤ 26` leaves ≥ 1 solid-floor col (4 / 27) so arrival never overlaps a hole. The ≥ 4-clear-cols (`\|c1−c2\| ≥ 7`) rule applies unchanged between shafts and internal ladders/pits on the same storey |
| Generator gaps (designer decision 2026-10-03) | **(1) Lair tiers** (superseded by the L1 rules row, 2026-10-05: both tiers are restricted to the bottom row; the D8 Sanctum cell is reserved up front)**:** (a) farthest non-start leaf with a horizontal edge; else (b) farthest non-start room with a horizontal edge (it keeps its other exits; the boss never follows, so a through-room lair is fine; on D8 the Sanctum leaf needs a free horizontal neighbour cell, else tier fails); there is **no tier (c)**: if neither exists, the generator **reseeds** (seed+1, ≤ 16 tries). The lair edge must be horizontal so the lair has its door. Key room (§1.4: unused in 3B) follows the same fallback. **(2) Potions: minimum 2** per level (≥ 1 Heal); up to 32 seeded placement tries each for the first two, the 3rd is optional and dropped after 8 tries. **(3) Dead-end block:** only in rooms that are **not start, lair or Sanctum**, and only at an edge with no exit. **(4) Start:** hero begins in the DFS-root room on **storey 0** (top); D1 x = col 14, D2+ x = arrival-shaft `c+1`; if x falls on a pit/ladder/shaft footprint, move to the nearest solid-floor col with ≥ 1 clear col. **Designer clarification 2026-10-03:** the arrival shaft is a storey-0 feature (it descends from above into the start room's storey 0, rubble-capped overhead), so the hero arrives on **storey 0, standing on solid floor at x = `c+1`, not mid-climb** (option a). The footprint-move rule **does not apply to the arrival shaft itself**; it applies only to the *other* footprints (pit, internal ladder, up/down-exit), and since placement already keeps those ≥ 4 clear cols (`\|c1−c2\| ≥ 7`) from the arrival shaft, in practice the move rule can only trigger on D1 (x = 14). **(5) 3B level block** needs nothing beyond the descriptors, floor-item list and hero start; population is the fixed per-room stand-in table keyed by room id and depth, not stored |
| Traps (3E) | placed **last**, after the floor items, so every earlier generator output stays byte-identical to B3B-7 (Python == Z80). Rules §1.5. **Rev 2026-10-20:** 3E items and traps run on the separate `ITEM_RNG` after the whole `GEN_RNG` pass (§8.11 Q8) |
| Stored per level | room descriptors (exits, ladders, pits, blocks, door/grate bits), the floor-item list, the **trap list (≤ 6 × 2 B, §1.5)**, the **population budget + 9 room records (~100 B, §9.4.1–9.4.2, user 2026-10-06)**; the 16 entity slots hold only the current room. Population §9.4, items §8.5 |

### 1.2 Level themes: colours and decor tilesets (attr-only; floor rows never under sprites)

| Depth | Scheme | `ATTR_FLOOR` | `ATTR_WALL` (air band) | Tileset |
|---|---|---|---|---|
| D1 | Blue Keep | `$0F` | `$01` | 1 |
| D2 | Green Caves | `$27` | `$04` | 2 |
| D3 | Red Crypt | `$17` | `$02` | 3 |
| D4 | Orc Warrens (cyan) | `$28` | `$05` | 4 |
| D5 | Sandstone Tombs | `$30` | `$06` | 5 |
| D6 | Bone Catacombs (white) | `$38` | `$07` | 6 |
| D7 | Iron Fortress (bright blue) | `$4F` | `$41` | 7 |
| D8 | Sanctum (magenta) | `$1F` | `$03` | 8 (incl. lectern) |

- The legality set (prototype §4.3) becomes per-level: `ATTR_FLOOR[depth]`, `ATTR_WALL[depth]`.
- **Tile ids:** 64 = **32 common + 32 per-level decor slots**. At level start, a level's
  glyphs and attrs (32 × 9 B) are copied in from cold storage. 8 sets = 2,304 B, stored in
  bank 7 spare (§11.2).
- **Id budget (designer decision 2026-10-03):** common ids 0..31 are full (aliases allowed:
  pit caps = platform-end glyphs, DARK = `T_BRICK`; chain/skulls/drips reuse the
  retired chest/zap ids; **designer decision 2026-10-03 + user 2026-10-03 option B:** ids 11/14
  = open-door jambs L/R, cobweb and moss move to per-level ids, see concept-screen §3.3). Per-level decor ids **32..59 = 28 per level for D1–D7**; **60..63 are
  reserved for attackable objects** (D8 lectern = 4). The cap is 28 decor ids per set; if
  a set exceeds it, cut the arched window and the pillar variants first. Common id 10
  (freed when potions stop being a map tile in 3E) becomes **`T_TRAP`** (revealed trap,
  designer decision 2026-10-03, §1.5). After 3E the common ids are completely full.
  **Rev 2026-10-20 (§8.11 Q1):** floor items use common 17 (AMMO) / 18 (PAGES) and
  per-level 60..63 (FLASK, FOOD, WEAPON, WORN) on D1–D7; D8 swaps 60..63 with the lectern
  in the Sanctum only. **Superseded by FLOOR1 + 3F-D1 (§9.7 R2):** 60..63 are item markers on
  every depth incl. D8; the lectern is common ids **15/16 (top L/R), 17/18 (bottom L/R)**,
  `T_GRATE_SHUT` is common **13**; no D8 swap.
- Walls are **black-background** with occasional dithered brick patches (concept-screen §3.3).
- **Solidity of decor (designer decision 2026-10-03).** Solidity belongs to the map cell
  class, never to the glyph: a decor glyph must have the same solidity as the cell it
  replaces. (a) **Wall-set glyphs** (DARK = BRICK id, DITHER, PATCH, FADE, wall_worn,
  wall_brk_top/bot and any other wall variant) are **SOLID** and may replace only cells that
  are already solid wall (brick). (b) **Rubble, skulls, moss, cobweb, chain, banner, torch,
  candles, drips, window, bookshelf** are **non-solid** (walkable or overlay) and may be placed only
  on cells that are already non-solid (floor-row standing cells or air-band cells); window and
  bookshelf are placed only on air cells. Pillar and plaster-patch are **SOLID** and placed on
  wall cells (they follow (a)). Solidity follows the cell class.
  (c) The B3B-9 deriver never places on door/arch/lintel/ladder/pit/cap cells, nor changes a
  cell's TILE_FLAGS. TILE_FLAGS solid must therefore be set on every wall-set id (the 3B
  non-solid wall_worn/wall_brk ids are a bug); rubble stays non-solid.
  **Amended, designer decision 2026-10-05 (D1):** the plaster patches never appeared because
  2×2/3×2 brick footprints exist almost only in dead-end blocks. The black air band *is* the
  back wall, so **back-wall patches** (common `T_WALL_DITHER/PATCH/FADE` 28–30 and per-level
  `PATCH_A/PATCH_B`) are **NON-solid and placed only on `T_AIR` cells**; clear their
  TILE_FLAGS solid bit. DARK (= `T_BRICK`), wall_worn/wall_brk and pillar stay SOLID on brick.
  Placement rules: concept-screen §3.3 "Decor placement (D1)".

### 1.3 The Tome of Absolute Death Magic

- The Tome lies on a **2×2 lectern tile object** in the Sanctum. It **cannot be picked up**.
- **TOME_HP = 5.** Every hit whose line reaches the Tome removes 1: melee, power attack,
  spell, arrow or dagger.
  - It **ignores resistances** and is never missed.
  - Each hit flashes the lectern `$43` and prints a message.
- **Aura:** while the hero is within 6 cols on its storey, it deals 1 HP per turn (end of
  turn, ignores DEF).
- At 0 it turns to ash (rubble glyph) → `THE TOME IS DESTROYED` → **the D8 exit gate opens** (`A GATE GLEAMS, THE WAY DOWN`, as a D1–D7 boss death) → the hero walks to the lair and leaves through it → `GS_WIN` (WIN2, user 2026-11-01; the P3 build ended the run on the hit).
- It is a tile with an `ATTACKABLE` flag, not an entity.
- **P3 rulings as built (user 2026-10-31; engineer details marked E):** a hit counts when an attack is
  RELEASED by the hero standing on the lectern's storey, FACING it, with the gap (empty cols between body and
  lectern) below that attack's reach / range — melee bump or FIRE, Power Strike, Whirlwind (reach 1; both
  accepted with no body target), spells / daggers / arrows (their rank-row range) — geometry only, no
  projectile collision; no `$43` flash and (E) no ash (the end card covers the play area at once); each hit
  `THE TOME SHUDDERS`. (E) The lectern stands on **storey 1 against the Sanctum's dead-end wall** (cols 1-2 in
  cell 6, 29-30 in cell 8). (E) `TOME_HP` is set once per level at generation and **never restored**: leaving
  the Sanctum keeps the damage. The aura is untyped (no DEF, no resistance), once per turn end, gap < 6 on
  storey 1 (either facing); its last hp ends the run (`GS_DEAD`, no death sequence). The seal opens on the
  Archmage's death by any hand (its own Mirror Helm return included): `THE SEAL BREAKS`; the door keeps its
  lock glyph until bumped open. (E) The D8 lair keeps its shut grate (the generator still places the exit
  col); the Archmage's death does not open it. **WIN2 as built (user 2026-11-01; E details):** the Tome's last hit
  logs `THE TOME IS DESTROYED` then `A GATE GLEAMS, THE WAY DOWN` and sets `LF_GRATE_OPEN` (the lair is another
  room: it opens off-screen, the lair's next build draws the raised gate + glow, re-entries / teleports keep it:
  level state); the run goes on (summoned Skeletons stay). The destroyed Tome is inert: (E) the lectern stays
  drawn (no ash), a bump on it is a wall (no turn), no hit counts, the aura stops (so the very hit that destroys
  it can never kill by the aura; an earlier hit can, and then the gate stays shut). DOWN on the open D8 grate =
  `GS_WIN`, log `YOU WIN!` (the end card's string; no new text), at any HP. No item or trap generates in the Sanctum. Accepted as is (manager review 2026-11-01):
  a FEARed hero can still hit the Tome by bump / FIRE (the Tome is no body, `fear_chk` gates body attacks
  only); the Mage's staff on the Tome plays no `melee_bonk` swing (the hit and the line only).

### 1.4 Stage 3B stand-ins (user, 2026-10-03; temporary, replaced in 3C+)

| Area | 3B stand-in | Final rule |
|---|---|---|
| Floor items | **potions only** | §8.5 |
| Population | a **fixed per-room table** using today's (prototype) kinds | §9.4 **lazy population** (user 2026-10-06; plan task LP): budget + per-room records, spawned on room entry (§9.4.1–9.4.3) |
| Lair | **SUPERSEDED in 3F (BOSS-GUARD 2026-10-29): shut until the boss dies, §1.1 / §9.2 "Boss guard".** 3B stand-in was: the **grate is always open** (boss death not required), but drawn as the distinct raised-portcullis frame (id 26, ink `$46`, concept-screen §3.3 B3B-8 #4) with a first-entry hint `A GATE GLEAMS. THE WAY DOWN.` (designer decision 2026-10-04, B12); ordinary down-exit holes stay plain | §1.1, §8.6 |
| Key / locked door | no key exists (potions only), so the lair door is an **ordinary unlocked door** (designer decision 2026-10-03) | §1.1 |
| D8 | D8 gets a lair exit like D1–D7; **descending from D8 = `GS_WIN`** (F3_GEN 0: the Archmage's death opens it) | §1.3 (WIN2: the Tome's destruction opens it, descending = `GS_WIN`) |
| Close door | keyboard key **`C`** (1 turn, §2.3 legality; not redefinable, not on joystick) until the 3C icon bar adds FIRE on the melee icon (designer decision 2026-10-03: the key) | §3.1 |
| Start kit (3D, D3-7 debug; designer decision 2026-10-12) | Behind a debug build flag only, never in a release tape. **Mage:** all 5 spells rank 1, MP 40/40. **Warrior:** Power Strike + Whirlwind rank 1, bow in the bag, **ARROWS 20, DAGGERS 8**, MP 20/20. The near-cap ammo lets the D1 floor stacks trigger `QUIVER FULL.` 3E additions: §8.11 Q10. **Infinite lives (DBG-1, user 2026-10-31; debug flag only):** the hero cannot die from any source (hits, Drain, traps, falls, the Tome's aura; poison and hunger never kill anyway): every death reaches the end-of-turn death check, which revives him there at **HP 1** (EF_DYING off, standing pose); the lethal hit, its DEATH reaction, the damage and the log lines play as usual, no `YOU DIED`, never `GS_DEAD`; that turn's hunger step is skipped | §4 start kit (3E) |

### 1.5 Traps (3E; user 2026-10-03 scope, designer decision 2026-10-03 details)

**Model.** A trap is a **1-col pressure plate in a storey's standing row** (row `9s+7`, the
air row directly above the floor), the same row skulls and rubble use. It is not an entity and
not a map tile while hidden: it lives in the per-level **trap list**; the room map keeps the
cell's normal id. **Only the hero triggers traps** (monsters know their dungeon: no AI or
pathing change, no off-screen events).

| Type | Depths | Effect on the hero | After triggering | Message (≤ 32) |
|---|---|---|---|---|
| **DART** | D1+ | 1d4+1 PHYS (DEF applies) + **POISON 12** (§6.4; was 6, POIS1 §6.4.3); impact = `arrow_hit` sprite at the hero | **re-arms** (stays, now known) | `A DART HITS YOU!` |
| **GAS** | D2+ | **ASLEEP 4** (§6.4); hero flashes `$44` one step (no new art) | re-arms (stays) | `SLEEPING GAS! YOU FALL ASLEEP.` (30) |
| **TELEPORT** | D3+ | as the Teleport scroll (§8): random free spot, random room, never the lair while its boss lives; attr flash as the Archmage's | re-arms (stays; accepted by the user: a free escape tool) | `YOU ARE TELEPORTED!` |
| **ALARM** | D5+ | while the boss lives: one **wave** = the §9.5 idle-wave spawn (1 + (rnd & 1) of the level's kinds at the room's doors/exits, awake, `F_RESPAWN`, slot + §9.3 cap rules), runs even with `IDLE_WAVE` off; border flashes red 2 ticks. Boss dead, or `LP_RESPAWNS` at `RESPAWN_MAX` (6): nothing comes (TRAP2: a wave counts toward the §9.5 respawn cap, so a re-arming plate cannot be farmed for XP) | re-arms (stays) | `AN ALARM BELL RINGS!` / `A BELL RINGS. NOTHING COMES.` (28) |
| **STUN** (falling stone; STUN1, §1.5.1) | D4+ | 1d3 PHYS (DEF applies) + **STUNNED 2–3** (rolled, §6.4); hero flashes `$07` | re-arms (stays) | `A STONE FALLS ON YOU!` (21) then `YOU ARE STUNNED!` (existing) |

ALARM's wave code lands in 3F; in 3E the trap is generated and prints the "nothing comes"
line (the generator must not change between 3E and 3F).

**As built (3E-T16, accepted deviations + user 2026-10-26 flashes; no new graphics).**
- DART impact: the `arrow_hit` sprite plays for the **Warrior only** — it is not in the Mage's
  class FX pool, so a Mage hit by a DART shows his hurt reaction alone (accepted, review
  2026-10-26; no art added).
- Timing: the trigger / find is decided on the move's input tick; the effect, its lines and
  the flashes run on the following ticks, then the monster phase (the cast mechanism). On a
  trigger the plate flashes bright white `$47` for 2 ticks (then every type shows its ink: TRAP2, no
  trap is ever removed) and the hero flashes the type ink (DART `$42`, GAS `$44` one step,
  TELEPORT `$43`, ALARM `$46`). On a find (search / sense) the plate blinks bright / off
  twice, 2 ticks each, then shows its ink, with the `TRAP FOUND:` line.
- Teleport (scroll and trap): the hero flashes `$43` (bright magenta = the TELEPORT ink; not
  a hero kind attr, the hit `$42` or the gold `$46`/`$47`) for 3 ticks before the room
  change (the turn is held 3 ticks) and again for 3 ticks on arrival, with the `DRAIN` SFX.
- Mage sense also runs after a held Wait and on the room-entry turn; on entry (the
  transition tick) a sensed trap is drawn at once in its ink, without the blink.
- No floor item ever covers a trap col: **FLOOR1 (2026-10-26):** an item covers cols c..c+1,
  so a trap col t is never c or c+1 — the generator (trap after items: t ∉ {c, c+1} of every
  item of the storey) and drops (§8.11 rulings 2: no footprint over a trap col, hidden or
  known).

**Trigger.** A trap fires when a hero move **first brings its col under the body** (walk,
bump-free step, jump landing, fall landing, ladder step-off onto the storey). Standing on it,
turning, or waiting does not re-fire; walking off and back on does (DART). A **jump clears
it** when the trap col is within the cleared cols `x+3 … x+5` (§2.4): jumping is the way
past a known DART. Teleport/fear arrivals never land with a trap col under the body.

**Finding (hidden → known).** All traps are generated hidden. A known trap draws `T_TRAP`
(common id 10) in its cell; the room builder sets its attr from a 5-entry type table (DART
`$42`, GAS `$44`, TELEPORT `$43`, ALARM `$46`, STUN `$07`; ink on black, joins the legality set). A trap
becomes known when:
1. it **triggers** (TRAP2, user 2026-10-28: **every** trap stays known and visible and re-arms; it fires again
   only on a NEW crossing, and monsters ignore traps);
2. **Search = Wait** (↓ with no ladder below, §2.3; no new key, joystick-complete): each
   hidden trap in the current room on the hero's storey within **6 cols** of the body is
   found with **1 in 2** (gameplay RNG);
3. **Mage trap sense** (class ability, passive): at the end of every Mage turn, hidden traps
   within **2 cols** of his body on his storey are found (100 %). The Warrior must search.

Message on find: `YOU FIND A DART TRAP.` · `… A GAS TRAP.` · `… AN ALARM TRAP.` ·
`YOU FIND A TELEPORT TRAP.` (25). A known trap overrides any derived decor in its cell
(decor is cosmetic and re-derived on room entry, never stored).

**Counts and types per level (seeded from the level seed; rev 2026-10-20: on `ITEM_RNG`,
not `GEN_RNG`, §8.11 Q8).**

| Depth | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| Traps | 1 | 2 | 2 | 3 | 3 | 3 | 4 | 4 |
| Type pool (uniform) | DART | DART, GAS | DART, GAS, TELEPORT | + STUN | + ALARM | all 5 | all 5 | all 5 |

(STUN1 rev 2026-10-26: pool order DART, GAS, TELEPORT, STUN, ALARM; pool length 1, 2, 3, 4,
5, 5, 5, 5. D4 was "same as D3", D5+ "all 4".)

**Placement (generator, after floor items; each trap ≤ 8 seeded tries, else dropped).**
- Room: not start, not lair, not Sanctum; **≤ 1 trap per room**.
- Storey `s ∈ {0,1}` (random), col **`t ∈ 6..25`** (keeps the arrival bodies at x = 1 / 28
  and every door/arch col clear by ≥ 2 cols).
- For every footprint on that storey (ladder, shaft, hole, pit, arrival shaft, all
  `c … c+2`): `t ∉ [c−1, c+3]` (excludes caps and ladder-end cells). Not under or adjacent
  to a dead-end block or its rubble col. On storey 1, `t ∉ [p−1, p+3]` (pit landing zone).
  D1: not within the hero start body ±1.
- Not on a floor-item cell.
- Storage: **trap list ≤ 6 entries × 2 B**: room (4 bits), storey (1), col (5), type (**3**,
  STUN1: widened into the old `TR_B1` bit 7 spare), known (1), 2 bits spare
  (`TR_B0` bits 6-7; the old `spent` bit is retired by TRAP2).

**Levelcheck invariants (B3B-6 checker extension).** Per seed and depth: trap count = table
(minus dropped tries, reported); ≤ 1 per room; none in start/lair/Sanctum; every `t` passes
the col rules above against the final room descriptors; types within the depth pool; all
generated hidden; no trap under a pit landing zone; Python == Z80 trap list byte-exact;
generator outputs before the trap step unchanged vs B3B-7.

#### 1.5.1 STUN trap (STUN1; user 2026-10-26 scope, designer decision 2026-10-26 details)

A **falling stone**: the plate releases a stone from the ceiling. It strikes the hero's head
for minor damage and stuns him for 2–3 turns. (Rev 2026-10-26, user rulings: (a) the trap does
damage, (b) the duration is a 2–3 roll, (c) there is no helm reduction. This replaces the
first draft's no-damage thunder rune.)

| Rule | Value |
|---|---|
| Status | the **existing STUNNED** HOLD kind (`HOLD_STUNNED` = 3, §6.4). No new status bit, tint, icon, mark, pose or line: tint `$07`, panel icon, V1 pose and V2 mark, `YOU ARE STUNNED!` / `YOU CAN MOVE AGAIN.` already exist for the Ogre SLAM / Orc Bouncer / Skeleton Knight hero stuns |
| Damage | **1d3 PHYS, DEF applies** (`max(1, roll − DEF)`): 1–3 HP, and with DEF 2+ almost always 1. No resistance, no helm rule. Not lethal by design, but it can kill a hero at 1–3 HP. The death goes through `deal_hit`'s standard DYING sequence and death credit, exactly as a DART death |
| Duration | **`2 + rnd(2)` = 2 or 3** (50/50). It is rolled at fire time on the **gameplay RNG**: one draw after the damage die. `ITEM_RNG` and the trap generator are untouched. The hero loses exactly his next 2–3 action phases (§6.4 step order). His eva is 0 from the trigger: the trigger turn's monster phase plus the held turns = **3–4 monster phases at eva 0** |
| vs GAS | GAS ASLEEP 4 ends on **any HP loss**. STUNNED does **not** end on damage, only on its timer. Out of combat STUN is the milder trap (2–3 turns, not 4, plus 1–3 HP). Next to monsters it is the harsher one: every adjacent monster gets ~3–4 near-sure swings, where under GAS the first swing wakes him. That is why it is D4+ |
| While stunned | as any HOLD (§2.2): the loop runs his turns automatically (1 per 4 ticks, a Wait **without** search). Every turn input is ignored: move, melee, cast, quick slots, bag page. Only Pause works. There is no look command to keep |
| Application | through **`deal_hit`**, like DART's poison: `trap_hit` parametrised, effect `EFX_STUNNED`, amount = the roll. So the standard hold rules apply. **B2:** cannot happen, because the hero has just moved. **HOLD_GUARD:** if it is still set (he just came out of a stun or freeze and this move is his guarded action), the stun is **silently refused** and the damage still lands. That matches the Ogre SLAM rule. HOLD_GUARD is set again when the trap stun ends (§6.4 step 3), so an Ogre SLAM or Orc Bouncer hit cannot extend it: he always gets one action first. The immunity mask is checked by `deal_hit` (no gear grants `IMMF_STUN` today) |
| Feedback | step 0: `SFX_TRAP` (reused); the hero flashes the type ink `$07` (`TRAP_FLASH_T`, the generic `tr_eff` path), then the STUNNED tint `$07` holds; the plate flashes `$47`; log `A STONE FALLS ON YOU!` (21, new), then `deal_hit`'s own `YOU ARE STUNNED!` (`st_stunned`, existing). The hurt reaction plays on arrival (`E_REACTAT`, the DART timing). There is no impact sprite (the `arrow_hit` frame is DART-only). Step 1: the plate shows its ink and stays (TRAP2), as GAS |
| Plate ink | **`$07`** (white, not bright, on black: grey stone). It is the STUNNED colour everywhere (tint, icon), so the plate tells you what it does. It is distinct from DART `$42`, GAS `$44`, TELEPORT `$43`, ALARM `$46` and from the `$47` flash/blink (the BRIGHT step is visible: the find blink goes `$47` / off / `$47` / off / `$07`). It is already in the legality set (STUNNED tint). `$45` was rejected (FROZEN tint, and the Mage's own attr: an invisible hero flash). `$41` was rejected (ASLEEP tint, near-black on black) |
| Find | search and Mage sense are unchanged; line `TRAP FOUND: STUN` (`STUN` 4 B, new name) |
| Hunger faint (§7.1) | the faint already defers while the hero is held. **STUN1 adds: it also defers while `HOLD_GUARD` is set.** So a faint never lands on the turn a stun or freeze ends, and he gets one free action between two holds. This costs ~4 B in FAINT1's defer checks (FAINT1 is not built yet, so it is in its estimate). |
| ALARM (3F) | no interplay: ≤ 1 trap per room, so a room never holds both. A stunned hero at a wave's arrival is the ordinary held case. Danger music: HOLD already adds +2 to the horizon (§3.7) |
| Monsters | never stunned by traps (only the hero triggers traps, §1.5) |

**Generation (T6 overlay + `tools/items_model.py`).** `TT_STUN` = **4** (`TT_DART..TT_ALARM`
keep 0..3, so the existing tests and asserts stay valid). The type is still drawn once per
trap as `pool[rnd(len)]`. The overlay keeps its prefix-length model through a 5-B order table
`ig_tord` = DART, GAS, TELEPORT, STUN, ALARM (type = `ig_tord[rnd(len)]`). `ig_tplen` becomes
1, 2, 3, 4, 5, 5, 5, 5. In the Python mirror, insert `(TT_STUN, 4)` into `TRAP_FIRST` between
TELEPORT and ALARM. **RNG impact:** `rnd(n)` is one draw then `% n`, so the draw count does
not change. Placement (room/storey/col) and every later `ITEM_RNG` output stay byte-identical.
Only the **type field at D4+** changes (D4 `%3` → `%4`, D5+ `%4` → `%5`). D1–D3 are
unchanged. Rebaseline the `tests/items_gen.py` 1,000-seed gate and the levelcheck "types
within the depth pool" check for D4–D8 only.

**Implementation (staff; contracted).**
- `item_defs.asm`: `TT_STUN` 4, `TR_TYPE_MASK` `%11100000` (bits 5–7), `TRAP_STONE_DIE` 3,
  `TRAP_STUN_T` 2 (+ `rnd(2)`), `TRAP_INK_STUN` `$07`, `TRAP_INKS` gets a 5th byte. Fix the
  three `ASSERT TT_* ==` lines. `tr_type` / bank 3's type extraction must take 3 bits.
- Bank 3 `trap_hit`: add a second entry, `trap_stone`. It rolls 1d3, then `2 + rng_mod 2`, and
  shares the WEAK +1 compensation and the `deal_hit` call with C = `DTY_PHYS | EFX_STUNNED`
  and E = the roll. DART keeps its entry: 1d4+1, POISON `TRAP_DART_PSN`. Draw order: damage,
  then duration. Tests pin both.
- R6 `trap6.asm` `tr_eff`: a 5th dispatch arm. It prints the stem `A STONE FALLS ON YOU!`
  (`S3_TRAP_STONE`, bank 1 `it_line`), calls far3 `trap_stone`, then joins DART's `E_REACTAT`
  arrival code and returns before the `arrow_hit` FX. `TEV_FIRE + TT_STUN` = 5 collides with
  `TEV_FIND` 5, so **renumber `TEV_FIND` to 6**.
- Bytes: R6 ~16 B (of ~2.1 KB free), bank 3 ~18 B (`trap_stone` entry ~16 + `tr_ink3` +1),
  bank 1 ~28 B (stem 21 + name `STUN` 4 + terminators/refs), overlay ~12 B raw (`ig_tord` 5
  + lookup ~6; ZX0 ~+10). **≈ 75 B total.** Time: about DART's (~15k + ~5k T over two ticks,
  budget.py `tdart` class, with no FX start).
- Tests (`tests/t16.py`): add a type-4 case to every type loop.
  - **Fire:** HOLD = STUNNED; both lines; plate stays; hero `E_FLT` attr `$07`.
  - **Damage:** with `SEED_FIXED`, HP loss = `max(1, d − DEF)` for d ∈ 1..3, checked at DEF 0
    (1, 2 and 3 all seen) and at DEF 3 (always 1).
  - **Roll distribution:** ≥ 200 fires over varied gameplay seeds. Every timer ∈ {2, 3}, each
    value ≥ 35 % of fires. The `ITEM_RNG` state is unchanged by a fire.
  - **A monster hit while stunned does not clear HOLD** (the GAS contrast). After 2 or 3
    auto-turns he can act and HOLD_GUARD is set.
  - **Guard:** HOLD_GUARD poked set → the damage lands, no stun, no line.
  - **Death:** HP 1, DEF 0 → DYING and the standard death sequence/credit (as DART).
  - **Find:** line `TRAP FOUND: STUN`, plate ink `$07`.
  - **Generator:** D1–D3 trap lists identical to the pre-STUN1 baseline, D4+ types in the
    5-pool, placement bytes identical.

---

## 2. Geometry and turn model

### 2.1 Storeys (replaces prototype §3.3)

- For storey `s ∈ {0,1}`: air rows `9s … 9s+7`, floor row `9s+8` (rows 8 and 17).
- Standing top for body height `h`: `y = 9s+8−h`. An entity stands iff `(y+h) mod 9 == 8`.
- Hero rows: 2–7 and 11–16. **Headroom over a 48-px body = 2 rows (16 px).** The panel is
  rows 18–23.
- Room map: 32×18 = 576 B, 6-bit tile ids.
- Ladder segments: `{c,0}` up-exit (rows 0–7), `{c,1}` internal (hole in row 8, rows 8–16),
  `{c,2}` down-exit hole (row 17). **A climb between storeys takes 9 turns.**
- Flyers: `9s ≤ y ≤ 9s+8−h`.

### 2.2 Turn loop (prototype §3.2 + E0)

- **Turn logic resolves in the input tick**: the player first, then monsters in slot order.
- Presentation keeps 25 Hz, 4 px tweens, 2 ticks per cell and hold-to-repeat.
- **Phase 1:** the player's action plays, including its projectile, any reflections, and its
  impacts and target reactions. **Phase 2:** all monster actions play concurrently, monster
  projectiles included. **Why:** logic resolved the player first, so a target must not
  visibly walk away from a bolt that already hit it. It also keeps monsters static, at zero
  render cost, while the player's spell flies (§9.3).
- **Casts and missiles (designer decision 2026-10-12):** the hero's ability logic (`proj_fire`,
  power attacks) may resolve on its **release tick f** (§6.1–6.3) rather than the input tick, and
  monster logic then resolves at f+1. Logic order stays hero-first. **Phase 2 still starts
  only when the hero's FX is idle**, after the last impact and its reactions, not at f+1.
  Monsters stand still for the whole flight; Lightning, the worst case, takes about 0.8 s.
- **Status step (3D, §6.4):** each entity runs its status step at the **start of its own
  action phase** (hero: when its turn begins; monsters: in slot order, current room only),
  every game turn, including turns an "acts every 2" monster does not act. Poison damage
  happens here.
- End of turn, in order: pickups → aura → hunger → regen → Mage trap sense (§1.5) → panel.
  (Poison moved into the status step.)
- **Held hero (3D):** while the hero is FROZEN / ASLEEP / STUNNED (§6.4) the loop runs his
  turns automatically, **one turn per 4 ticks**, each a Wait without search; input is ignored
  except Pause.

### 2.3 Actions and costs

| Action | Turns | Ticks (E) | Legal when |
|---|---|---|---|
| Walk 1 cell | 1 | 2 | standing; the box is free and inside the body limits; monsters never onto `x == pit col` |
| **Turn around** | **0** | 1 | always. The first ←/→ against your facing only turns you; held, the key then walks or attacks |
| Climb 1 row | 1 | 2 | prototype §3.4. **No attacks, casts, throws or shots while mid-ladder** |
| **Jump** (↖/↗) | 1 | 14 | §2.4 |
| Bump attack | 1 | 6–7 | a hostile in reach, facing it (prototype §6.1) |
| Use icon (FIRE tap) | 1 | per action | §3, §6 |
| Open door (bump it) | 1 | 2 | a closed door is adjacent in the facing direction. Locked: needs the key (consumed) |
| Close door (FIRE on the melee icon) | 1 | 2 | an open door is adjacent and faced, its cells are free of bodies, and no hostile is in reach. Only the hero closes doors (§9.1). 3B stand-in key: §1.4. **"In reach" (designer decision 2026-10-03):** a living hostile in the hero's current room whose box is within **2 cols** (melee reach) of the hero *or of the door cells* counts, whichever side of the door it stands on within this room (the door is a room-edge connection, so only the current room is checked; the other room is frozen). Door cells must also be body-free |
| Wait (↓ where no ladder goes down) | 1 | 2 | always. **Also searches** for hidden traps (§1.5, 3E) |
| Eat / drink (quick slot) | 1 | 2 | refused, at no turn, at FOOD = 100 (food) or HP = max (Heal) |
| Page verb (eat, read, equip…) | 1, applied on return to play | — | play is paused on the page |
| Fall (stepping onto a pit) | part of the walk | 2 + 9 | §2.5 |
| Exit room | part of the walk/climb | — | prototype §3.6 |

Illegal actions cost no turn (F4). A **held** entity (FROZEN, ASLEEP or STUNNED, §6.4) skips
its action. Exception to F4, and only for a **direction** failure: a CONFUSED hero's reversed
action that fails because of the new direction (blocked walk or jump, no target for a
directional melee, bump or Power Strike) costs the turn (`YOU STUMBLE.`); he stays facing the
reversed way. A reversed action refused for a **non-direction** reason (NO MANA, NOT LEARNED,
AFRAID, no ammo/bow) costs no turn, and he faces back to his original direction (user,
confirmed). Whirlwind never rolls. See §6.4.2 R4.

### 2.4 Jump (user: agreed)

| Rule | Value |
|---|---|
| Input | ↖ / ↗ (keyboard: chord UP+LEFT / UP+RIGHT). A diagonal is **always** a jump |
| Distance | **`D = 6` cols**: body `x … x+2` → `x+D … x+D+2`. **`D = 7`** only for the low-body case below (user 2026-10-06). Left jumps mirror (`x−D`) |
| Clears | cols `x+3 … x+D−1`: air, **a pit**, floor items, or a **low body** = `body_h ≤ 16` and ≤ 4 cols wide (Slime 24×16, **Rat 32×16, Spider 32×16** (user 2026-10-06), or a Bat in the bottom 2 band rows) |
| Low-body extension (user 2026-10-06, exact) | If box `x+6 … x+8` holds **only low bodies** (no other body), try `D = 7`: legal iff box `x+7 … x+9` holds **no body**. So a Rat/Spider adjacent to the hero (`r = x+3`, cols `x+3 … x+6`) is jumped with `D = 7`; a 4-wide low body at `r ≥ x+4` still blocks (overlaps `x+7`). A 3-wide low body adjacent keeps `D = 6`. Any non-low body in box `x+6 … x+8` (or `x+7 … x+9` when `D = 7`) = illegal. Arc for `D = 7`: 14 ticks, dy −4,−8,−12,−16×7,−12,−8,−4,0, `x += 4 px/tick` (56 px) |
| Swept box | cols `x+1 … x+D+2`, rows `top−2 … bottom`. It must be free of walls, door/arch/lintel, blocks and non-low bodies |
| Landing | box `x+D … x+D+2` per above, inside the body limits (`x+D ≤ 27`, no exit by jumping). **A landing in a pit is allowed (user 2026-10-06): the hero falls** (below). The old "`x+6 ≠ pit col`" refusal is **removed** |
| Landing in a pit (user 2026-10-06; details designer decision) | The fall test is the standing rule of §2.5: the hero falls iff the landing body is **fully over holes** (narrow pit: `x+D == p`; wide: `p ≤ x+D ≤ p+W−3`); a partial overlap with floor stands. Damage and landing: §2.5 (1d4, ignores DEF, storey 1 same x), no extra jump damage; FOOD paid as usual. **Wide pit, uncrossable by jump:** if the span `x+3 … x+D−1` contains a hole col of a **wide** pit (W ≥ 4), the arc is **cut short** and the hero falls at `x_f = min(x+D, p+W−3)` (always in `p … p+W−3`; mirror for left jumps: `x_f = max(x−D, p)`). Arc plays `2·(x_f − x)` ticks (x += 4 px/tick, a multiple of 8 px), the y offset is then dropped (F9 snap) and the fall plays. A narrow pit never cuts the arc (3 holes ≤ span) |
| Cost | 1 turn + **2 FOOD** |
| Restrictions | standing only. **Not from a ladder** (landing on a hole is fine). Not when Weak. **Not two turns in a row**. Not while frozen |
| Arc | tick 0: JUMP1 (aligned). Ticks 1–12: JUMP2, x += 4 px/tick, y offsets −4,−8,−12,−16,−16,−16,−16,−16,−12,−8,−4,0. Tick 13: JUMP1 (aligned) |
| F9 | the body only rises inside its own storey's air rows (top ≥ `9s`) |

**Art backlog (designer decision 2026-10-03):** Warrior and Mage JUMP1 (aligned, 24x48) and
JUMP2 (airborne, 24x48) are missing. 3B placeholder: climb pose for JUMP2 and the walk cycle
for JUMP1. Needed from graphics-artist before the 3E polish pass (not blocking 3B/3D).
**Scope:** the jump's FOOD cost, Weak and frozen restrictions are **3E (FOOD/Weak) and 3D
(frozen)**; 3B implements only geometry, swept-box legality and the not-twice rule.

**Why 6:** the smallest jump that clears a 3-col pit and a 3-col low monster. "Not twice
in a row" caps flight speed at 7 cols per 2 turns.

### 2.5 Pits and falls (user: agreed)

- A pit is **3 cols** of black-paper cells in the **storey-0 floor only**, with
  `PIT_L`/`PIT_R` caps.
- The hero falls when its body is **exactly** over it (`x == pit col`).
- **Fall:** 9 rows at 8 px/tick to storey 1, same x, **1d4 damage** (ignores DEF). An
  occupied landing box puts that monster PENDING in place (prototype §3.6).
- Walkers never step onto `x == pit col`. Flyers ignore pits.
- **Geometry (designer decision 2026-10-03).** `pit col` = `p`, the pit's **left** hole col;
  holes `p … p+2` (AIR `$00`), caps `PIT_L` at `p−1` and `PIT_R` at `p+3` (solid floor). Only
  `x == p` is special, for every body width: the hero (3 cols) falls there; a walker of any
  width (24 or 32 px) refuses the step that would make `x == p`, and every other overlapping
  `x` stands normally (at least one body col is on floor). Because walking moves 1 col per
  turn, refusing `x == p` alone cuts a walker off at the pit. Generation, follower entry,
  PENDING placement and teleport/fear arrivals never put a walker or the hero at `x == p` on
  storey 0; **jump landings may put the hero there, and he falls (user 2026-10-06, §2.4)**.
- **Cap glyphs (designer decision 2026-10-03).** The pit caps may share the platform-end
  glyphs (`T_END_L`/`T_END_R`) provided the rounded end faces the hole: the cap at `p−1`
  shows the right-end shape, the cap at `p+3` the left-end shape. Semantically a pit is a gap
  in the platform, so no separate id is needed.
- **Legal pit placement (designer decision 2026-10-03):** `p ∈ 5..24`, clear zones, block and
  storey-1 landing rules are in §1.1 "Pit geometry". Guaranteed crossing: take-off `x = p−3`
  (right) or `x = p+3` (left), landing `p+3` / `p−3`, both on solid floor inside 2..27.
- **Wide pits (L2, designer decision 2026-10-06; user 2026-10-06 asked for unjumpable pits).**
  Holes `p … p+W−1`, `W ∈ 4..6`, caps at `p−1` / `p+W` (§1.1 "Wide pit"). The hero falls for
  `p ≤ x ≤ p+W−3` (body fully over holes), walkers refuse those `x`, flyers ignore it, a jump
  toward it ends in a fall (§2.4: cut-short arc). Narrow pits stay as above; a jump can also
  land in them and fall (user 2026-10-06).
- F9: `px = col×8` while falling (snap invariant).

---

## 3. Controls

### 3.1 Joystick-only completeness (4 directions + diagonals + FIRE)

| Action | Joystick | Keyboard default (redefinable U/D/L/R/F) | Shortcut (never required) |
|---|---|---|---|
| Walk / turn / bump attack / open door | ← → | O P | — |
| Climb | ↑ ↓ at a ladder | Q A | — |
| Jump | ↖ ↗ | Q+O, Q+P | — |
| Wait | ↓ with no ladder below: commits at 3 ticks held or on release, **unless FIRE joined** (see ICON MODE) | A | `.` |
| Use the selected icon toward your facing | FIRE **tap** (fires on release, no direction pressed while held) | SPACE | ENTER |
| **Enter ICON MODE** (user 2026-10-05) | ↓ + FIRE (either pressed first, both down within 3 ticks) | A + SPACE | — |
| In ICON MODE: move cursor / use / exit | ← → (repeat after 10 ticks, then every 4) / FIRE (use + return to play) / ↑ or ↓ or BREAK (exit, no use) | same | `1`–`9`, `0` (= slot 10) move the cursor |
| Inventory page | FIRE on the BAG icon (FIRE+↓ no longer opens it) | — | `I` |
| Pause (Resume / Sound / Quit, §3.6) | FIRE held + ↑ | — | BREAK |
| Cycle sound ALL ON > SFX ONLY > OFF (§3.6; no turn) | via Pause → SOUND | — | `S` |
| Page: move / verb / confirm / back | directions / ← → / FIRE / ↓ + FIRE | same | — |
| Close door, hit the Tome | FIRE on the melee icon / bump | — | — |
| Pickups | automatic at the end of a turn | — | — |

**Stage 3C decisions (user 2026-10-04 / designer decision 2026-10-04).**
- Redefined keys stay live while a joystick is selected (joystick and keys are ORed).
- Turn-around costs 0 turns (1 tick). A held direction then walks only after the key-repeat
  delay (10 ticks), so a tap only turns.
- FIRE on BAG before 3E's bag page exists: no turn, message `NO BAG YET`.
- Bow icon before the bow is found (D2), and quick food before 3E food: drawn greyed,
  selectable by the cursor, FIRE is illegal, costs no turn and prints `NO BOW` / `NO FOOD`.
- Legacy PROTO keys (H/J/K/L, G, C, 1/2/3 hero select) are dropped once the new input lands.
- Pause: an overlay box over the playfield with Resume / Quit; **Quit asks for confirmation**
  (`QUIT? Y/N`; FIRE = yes, any other = no).
- Shortcut keys confirmed: ENTER, `1`–`0`, `I`, BREAK, `.`, `S` (sound, §3.6). Default map Q/A/O/P/SPACE.
  Redefine rejects these (see §3.2, manager ruling 2026-10-05, designer-confirmed).
- Sinclair 1 or 2 selected: in game, the `1`–`0` slot shortcuts on that joystick's half of
  the number row are disabled (S1 = 6–0, S2 = 1–5); the other half and the icon bar keep
  working. This applies only in game; the menu (§3.2, user 2026-10-06) never reads joysticks.
- The joystick/redefined keys documented here are active from START only (menu: §3.2).

- ↙/↘ act as ←/→. Opposite keys cancel (F7). The cursor **skips unlearned slots** (empty
  outlines) but **does not skip greyed ones** (you may select a greyed icon to read its info
  line; FIRE on it is illegal, costs no turn, and prints the reason, e.g. `NO ARROWS`).
- **Both bars have a BAG icon** (slot 10 on both bars). Layouts: §3.5.
- **ICON MODE (user 2026-10-05, replaces "FIRE held + ← →"; details designer decision 2026-10-05).**
  Entered by ↓ + FIRE. Play is paused: no turn passes, monsters and timers do not act, no
  animation advance except the cursor highlight. The selected icon is drawn highlighted
  (inverse attr) and the info line shows its normal text (name, cost, range) with a `>`
  prefix. ← → move the cursor (repeat 10 ticks, then 4; unlearned skipped, greyed
  selectable; `1`–`0` also jump the cursor). FIRE uses the selected icon and returns to play
  (turn cost only if the action costs one; illegal use prints the reason and **stays in
  ICON MODE**). ↑, ↓ or BREAK exits without using (BREAK does not open Pause). The selection
  persists after exit. FIRE tap outside the mode uses the selected icon; ↑ + FIRE = Pause.
  Disambiguation: ↓ alone is deferred up to 3 ticks (wait/climb-down commits at 3 ticks held
  or on release); if FIRE arrives first, ICON MODE is entered instead. Number keys outside the
  mode only select (do not use), as before.

### 3.2 Main menu (bank 3, cold)

```
WAZHACK   1 START   2 HERO: WARRIOR|MAGE   3 CONTROLS: KEYS|KEMPSTON|SINCLAIR 1|SINCLAIR 2   4 REDEFINE KEYS   5 SOUND: ALL ON|SFX ONLY|OFF
```

(`5 SOUND`: §3.6, designer decision 2026-10-13. `S` is a reserved key, see the redefine bullet below.)

- **Digits-only menu (user 2026-10-06; supersedes the 2026-10-05 Sinclair-half ruling).** The
  menu and its sub-screens are driven by the number keys only; no cursor, no up/down, and no
  FIRE / Kempston / Sinclair / redefined-key (KEYTAB) input is read on any menu screen. Keys:
  `1` START (ENTER = START too, convenience); `2` toggles HERO (WARRIOR/MAGE); `3` cycles
  CONTROLS KEYS > KEMPSTON > SINCLAIR 1 > SINCLAIR 2 > KEYS (no sub-menu; current value shown
  on the line); `4` REDEFINE KEYS. All other keys are ignored. The selected source (joystick
  and/or redefined keys) takes effect only from START; Kempston port `$1F` is not polled in
  the menu at all.
- **REDEFINE prompts** read raw keys (not digits, since digits are reserved, see below); BREAK
  cancels and keeps the old set (kept). A redefine screen therefore ignores joystick input.
- **End screens (death/win)** return to the menu on any digit or ENTER (not FIRE, so a
  held-FIRE or joystick press cannot skip them accidentally; keys are only accepted after
  all keys have been released once).
- **Pause overlay (in game)** keeps in-game controls (it is part of play): directions/FIRE
  choose Resume/Sound/Quit (Sound cycles in place, §3.6); `QUIT? Y/N` stays FIRE or `Y` = yes, anything else = no (§3.1).
- **Kempston** (port `$1F`: bit 0 R, 1 L, 2 D, 3 U, 4 F) is read **only after it is
  selected**, because the port floats on a bare machine.
- **Sinclair 1** = keys 6 L, 7 R, 8 D, 9 U, 0 F. **Sinclair 2** = keys 1 L, 2 R, 3 D, 4 U, 5 F.
- Redefine asks for UP, DOWN, LEFT, RIGHT, FIRE (no duplicates).
  (Manager ruling 2026-10-05, designer-confirmed.) Reserved keys are rejected with the message
  `KEY RESERVED`: ENTER, `1`–`0`, `I`, `S` (§3.6), CAPS SHIFT, SYMBOL SHIFT, and any key BREAK uses. The
  prompt stays on the same action. BREAK at any redefine prompt cancels the whole redefinition
  and keeps the previous key set.
- START seeds the RNG → generates D1 → play.
- **Title (user 2026-10-04):** the menu/title screen reads **"TOME OF THE DEAD"** (the concept
  screen's title), not WAZHACK. Torches animated and hero previews on the select screen follow
  `concept_menu` / `screen_menu.png` (designer decision 2026-10-04). Death `KILLED BY …`
  killer tracking is 3D (designer decision).

#### 3.2.1 HOW TO PLAY screen (INSTR1; user 2026-10-30 request, designer decision 2026-10-30)

> **Superseded (user ruling 2026-10-30):** shown every game after START, two 42-col pages with
> icons (as built: THREE pages, page 3 = boss treasures and charms, `GS_HELP1..3`; once per power-on before the first menu; BREAK on page 1/2 skips the rest). Wording, flow and render spec: `docs/design/instructions_screen.md` / `.txt` (pending
> user approval). The text below (Option A, 32 cols) is now only the fallback.

**Problem.** The game never tells the player the goal or the non-obvious combos (↓ + FIRE,
FIRE + ↑, the BAG icon, Wait = search). One static screen fixes it.

**Flow (decision): once per boot, before the first menu, from the boot block.**

| Option | Resident bytes | Re-readable | Verdict |
|---|---|---|---|
| **A. Pre-menu, once per power-on, text in the bank-6 boot block** | **0** after boot (≈ 0.75 KB more tape, ≈ 4–5 s of loading) | no (reload the tape) | **chosen** |
| B. After START, before D1, every game | ≈ 0.5 KB packed (tokenised or ZX0) + ≈ 40 B code, permanently | yes | rejected now: no free slot fits (R6 379 B, bank 3 ≈ 380 B, bank 7 ≈ 110 B); the only home is the pre-shift pool slack (2,480 B), which is reserved for 3F monsters |
| C. After START, first game only | same as B | no | same cost as B for the same reach as A (a permadeath game is one boot = one session) |
| D. Menu item `6 HOW TO PLAY` | same as B | yes | rejected now: same cost as B, and the menu has no free row (item 5 is on rows 21–22, the credit on row 23) |

- Why A: the boot block (§ memory-map "Boot block") is already on tape, runs once and is **dead
  after boot by contract** (the hero pool may overwrite it). Text and its draw loop placed there
  cost no resident byte. This is the user's "load into video RAM before the menu" option without
  a separate tape block: same one-shot behaviour, no new `tape_tab` record. Showing it every game
  would annoy repeat players; showing it once per boot reaches every new player.
- **Order in `boot`:** after `boot6_tiles` (the `FONT6` planes exist), call `boot6_help`: clear
  the bank-5 screen (ULA shows bank 5 at boot), set the border black, draw the 24 rows below,
  then let the rest of `boot` (the boot pool generation) run **while the player reads**, if it
  does not touch the bank-5 screen (engineer verifies; else wait first, then generate). Then wait
  for the key and enter the menu.
- **Dismiss:** any key, accepted only after **all keys have been released once** (the `ENTER`
  of `LOAD ""` may still be held). No timeout. The key is **swallowed**: the menu waits for a
  full release before reading, so a `1` here never STARTs. Kempston is **not** read (the port
  floats on a bare machine, and the menu never reads joysticks, §3.2); Sinclair FIRE is a key
  (`0` / `5`), so it works. A joystick player needs the keyboard for `1 START` anyway, so this
  adds no new keyboard step.
- **Music:** silent (the title tune starts with the menu as today). Simplest; no AY change.
- **Unblock for B/D later:** after 3F, if R6 has ≥ 600 B free or the pool slack is still
  ≥ 1.5 KB, a tokenised copy can be added to the bank-0 text block and shown from the menu
  (needs a menu relayout to fit item 6).

**Rendering.** The custom **6×8 text font** (`FONT6`, resident), 32 chars per row = 192 px,
**left margin 32 px** (centred). With that margin, chars 0 / 12 / 24 start at px 32 / 104 / 176
= attr cols 4 / 13 / 22, so the 3 colour fields of the control rows fall exactly on attr cells
(§3.4 colour rule). Paper black (0) everywhere, border black. Every row is upper case, ≤ 32
chars, no scrolling, one screen.

**Exact text** (`|` marks col 0 and col 32; field starts at chars 0 / 12 / 24 are padded with spaces):

```
row |0         1         2         3 |
    |01234567890123456789012345678901|
 0  |TOME OF THE DEAD - HOW TO PLAY  |  $46
 1  |FIND THE KEY, KILL THE BOSS AND |  $47
 2  |GO DOWN. ON DEPTH 8 KILL THE    |  $47
 3  |ARCHMAGE, THEN DESTROY THE TOME.|  $47
 4  |STICK       ACTION      KEY     |  $06
 5  |LEFT RIGHT  WALK, HIT           |  F
 6  |UP+L/R      JUMP                |  F
 7  |UP DOWN     CLIMB               |  F
 8  |DOWN        WAIT/SEARCH .       |  F
 9  |FIRE        USE ICON    ENTER   |  F
10  |DOWN+FIRE   ICON BAR    1-0     |  F
11  |BAR: L/R PICK, FIRE USE, UP BACK|  $07
12  |SPELLS, ARROWS: AIM BY FACING.  |  $07
13  |FIRE ON BAG INVENTORY   I       |  F
14  |FIRE+UP     PAUSE/SOUND BREAK S |  F
15  |WALK INTO DOORS AND ONTO ITEMS. |  $07
16  |KEYS Q A O P SPACE ACT AS STICK |  $05
17  |MENU 3 PICKS STICK, 4 REDEFINES |  $05
18  |WATCH FOOD - THE STARVING FAINT.|  $44
19  |GRATES ARE ONE WAY: LOOT FIRST. |  $44
20  |BOSSES NEVER LEAVE THEIR LAIR.  |  $44
21  |READ FEAR OR SLEEP WHEN SWARMED.|  $44
22  |ENCHANT GIVES A WORN ITEM +1.   |  $44
23  |         PRESS ANY KEY          |  $46
```

`F` = the 3-field control row: chars 0–11 (STICK) `$45`, chars 12–23 (ACTION) `$47`,
chars 24–31 (KEY, shortcut) `$46`. Row 4 is the field header in `$06`.

**Why each line (source rules).** Goal: §1 Win, §1.1 key room / lair / grate, §1.3. Rows 5–14:
§3.1 (Wait = search: §1.5 `TRP_WAIT`; ↓ waits only with no ladder below; jump ↖ ↗; icon use
fires toward the facing; ICON MODE ← → / FIRE / ↑ back; BAG icon or `I`; Pause FIRE + ↑ or
BREAK, SOUND in the pause box or `S`). Row 15: doors open by walking (§3.1), pickups are
automatic (§8). Rows 16–17: §3.2. Tips: hunger is never fatal but WEAK faints (§7, §7.1); the
level exit is one way (§1 "Going back up: no"); bosses never follow (§8.6); Fear / Sleep scrolls
(§8); Enchant repairs a worn weapon (§8.11 rev 6). **Cursed gear is not mentioned: rev 6
(§8.11 "3E simplification") removed it.**

**Budget (E).** Text ≈ 650 chars + ≈ 40 B of row/field/attr records ≈ **0.7 KB**, plus a draw +
wait loop ≈ 60–80 B, all in the boot block (`BOOT6_LEN` grows; `BOOT6_ADDR` moves down into
bank-6 pool space that only the hero pool uses after boot; the boot pool still ends in bank 4,
`POOL_BOOT_NEED` ASSERT). Raw text is fine: ZX0 would save ≈ 0.25 KB of tape (≈ 1.5 s) but adds
an unpack step. Engineer's choice. Resident cost after boot: **0 B**.

**Checks (`test`).**
1. Real tape load → the help screen is shown before the menu; golden screen `help`.
2. A key held from load → the screen stays until release + a new press.
3. Pressing `1` on it → menu shown, not started (`GS` still menu, `TURN_COUNTER` untouched).
4. Death → menu → START, and win → menu: the help screen is **not** shown again.
5. `tests/game.py` #61 still passes (boot-block PCs only during boot); #50 bank-6 compare covers
   the new bytes.

### 3.3 Panel at a glance (layout: concept-screen §5; approved round 5)

Rows 18–19: **10 icons 24×16** (cols `3i … 3i+2`), cols 30–31 = depth + key icon. Row 20: the
**info line** (selected icon's name, MP cost, range, bounces/notes; after an attack it temporarily shows the **target readout**, §6.5). Row 21: HP / MP / FOOD
bars (32 px each) with numbers, the **hunger stage word**, the Warrior's ammo. Rows 22–23:
2-row message log (cols 0–23) + **4 worn-gear icons 16×16** (cols 24–31). Row 17 (the
storey-1 floor) carries the panel ornament.

**Update timing (user, 2026-10-03).** Panel changes (bars, numbers, hunger word, ammo, log
lines, icon states, key/depth) are **queued** and drained **one item per tick, never in the
input tick**. Accepted latency (user 2026-10-04): **≤ 3 ticks** outside heavy animation; in
heavy fights a log message may wait **up to ~6 ticks (≈ 0.25 s)**. Logic reads the real values,
never the panel.

**Row 17 (designer decision 2026-10-03).** Only row 17 differs from the normal floor. In the
room map its cells stay logical PLATFORM (solid; the down-exit `{c,2}` cells are the hole /
grate). The room builder draws row 17's PLATFORM cells from the fixed **8-glyph ornament
pattern** (`assets/gfx/concept/grid/panel_r4.tiles`: cap_l col 0, cap_r col 31, wing/skull/
skull/wing cols 14–17, link/bar alternating elsewhere), and the hole/grate cells override it.
Ornament glyphs are **not tile ids** (64 B, the same on every level), with attr
`ATTR_FLOOR[depth]`, so only the colour changes per level. The storey-0 floor (row 8) uses the
common PLATFORM glyph (+ PIT caps, ladder hole) on every level; the floor glyph never varies
per level.

### 3.4 Text and fonts (user, round 5)

| Font | Cell | Used for | Capacity |
|---|---|---|---|
| **Text font** (custom) | **6×8** px, ASCII 32–127 (96 glyphs, **768 B**) | message log, info line, inventory page (labels, descriptions, counters) | log **32 chars per line** (192 px, cols 0–23); info line **42 chars** (252 px); page rows 42 chars |
| **Menu font** (custom) | **8×16** px (title may be 16×16 glyphs) | main menu, hero/controls select, redefine, pause, `DEPTH n` card, death and win screens | 32 chars per line; ~11 lines. Size **TBD by the artist** (≈ 64 glyphs × 16 B = 1 KB; caps, digits, punctuation only) |

**Colour rule (attributes are 8 px, text is 6 px).** The lcm is 24 px. A text row therefore
has **one colour for the whole row**, or coloured words start on **24-px boundaries (every 4
chars: char index 0, 4, 8 … )**. Never recolour mid-cell. The log uses one colour per row
(newest row `$47`, older row `$07`). The info line uses 3 fixed fields (name `$47` at chars
0–15; numbers `$46` from char 16; notes `$45` from char 28).

**Message limits (rev 3).** Every message is **one log line, ≤ 32 chars, upper case**. A
message that would exceed it must be reworded in the table below; there is no wrapping.
Examples (all ≤ 32): `YOU HIT THE GOBLIN.` · `THE GOBLIN MISSES YOU.` ·
`DEATH KNIGHT PARRIES!` · `YOU THROW A DAGGER.` · `YOU GRASP LITTLE OF IT.` ·
`THE TOME IS DESTROYED` (21) · `NO ARROWS.` · `QUIVER FULL.` · `THE VAMPIRE TURNS INTO A BAT!` (28) · `YOU PICK UP 3 ARROWS.` ·
`FOOD: HUNGRY.` The death line moves to the menu font: `KILLED BY …` ≤ 32 chars, with the
monster name abbreviated by a table if longer than the budget.

**Message list (designer decision 2026-10-04; src/strings.txt, B3B-13).** Final wording:
`YOU ENTER THE DUNGEON` (welcome) · `YOU WIN! PRESS ENTER` (win) · `YOU DESCEND DEEPER` ·
`THE DOOR IS LOCKED` · `YOU FALL INTO A PIT` · `YOU DIED - PRESS ENTER`. Style: present tense,
second person, upper case, **no trailing full stop** (the "." in the examples above is dropped;
"!" only for wins, parries and transformations). Change: `found "YOU FOUND A POTION"` becomes
`YOU PICK UP A POTION` (20; matches `YOU PICK UP 3 ARROWS`; one verb for all pickups). Impact
pieces (`YOU HIT THE ` / ` HITS YOU` / ` MISSES`) are approved; the longest composition
(`YOU KILL THE SKELETON` = 21) is far under 32. Empty `nm_rogue` and `empty` are fine.

**Placement (memory; revised 2026-10-03, designer decision, after A7).** Since the A7
double buffer, all text (panel, page, menus, cards) is drawn **only into the bank-5 screen**
and reaches the ULA screen through `present`; bank 7 holds the playfield's clean background
only. So:
- The **text font** (768 B) is used every turn and stays boot-copied into bank 2 (`$B200`).
- The **menu font** is drawn only on static screens (menus, pause, `DEPTH n` card, death/win).
  It stays in **bank 3** cold data and is paged in while those screens draw. The ≤ 0.8 KB
  limit is **dropped**. New limit: **≤ 1.5 KB raw** (e.g. 64 glyphs × 16 B + a few 16×16
  title glyphs), counted in the banks 1+3 cold-data row of §11.2. The artist picks the
  glyph count.

Budget table: §11.2.

### 3.5 Icon bars (10 slots; `$` = ink, concept-screen §6)

| Slot | **Warrior** | **Mage** |
|---|---|---|
| 1 | Sword | Staff |
| 2 | Power Strike | Spark |
| 3 | Whirlwind | Firebolt |
| 4 | Daggers | Frost Shard |
| 5 | Bow | Drain Life |
| 6 | (blank gap; spare) | Lightning |
| 7 | Quick food | Quick food |
| 8 | Quick potion | Quick potion |
| 9 | Quick scroll | Quick scroll |
| 10 | **Bag** | **Bag** |

- The Warrior has 9 icons (slot 6 is a blank gap, UB5 2026-10-31). The Mage has all 10. Food / potion / scroll / bag sit at the SAME slots (7-10) on both bars.
- **Quick scroll** (new slot, needed to hold the scroll icon the approved panel shows): FIRE
  reads the quick scroll (1 turn; same effect as `READ` on the page). Auto-fill: the stack
  with the most scrolls, ties → Teleport, Fear, Sleep, Enchant (known types only, §8.8). `QUICK` on the page pins a type.
  It greys out with no scroll.
- Unlearned ability slots draw an empty outline and are skipped by the cursor.
- The cursor moves only in ICON MODE (↓ + FIRE, §3.1) or via `1`–`0`; the BAG icon opens the bag when used there.
- 3C (designer decision 2026-10-04): the Bow slot and quick food are greyed-but-selectable
  until found (see §3.1), not skipped.

### 3.6 Sound settings (designer decision 2026-10-13; audio itself: sound.md)

**One setting, 3 states, one cycle:** `ALL ON` > `SFX ONLY` > `OFF` > `ALL ON`. There are no
separate Music and SFX toggles. Why: one menu line, one hotkey, and at most 2 presses to reach
any state. The likely reason to mute in game is that the short loops start to grate
(sound.md §1.2), and turning music off while keeping effects covers it. "Music only" (effects
off) has no gameplay use. The state is stored as two flag bits, so a 4th state could be added
later without touching the player.

| Item | Decision |
|---|---|
| State byte | `SND_MODE`, 1 B: bit 0 `SND_MUSIC`, bit 1 `SND_SFX`, bit 7 `SND_HOLD` (pause, below). Values: ALL ON = 3, SFX ONLY = 2, OFF = 0. Home: **bank 2, next to the `MUS_REQ` / `SFX_REQ` mailbox** (sound.md §0), so the ISR can read it whatever bank is paged. Engineer assigns the address in memory-map.md |
| Default | `ALL ON`, set at boot |
| Persistence | **Per power-on.** Kept across death, quit, win and new games (like `JOY_MODE` / `KEYTAB`). `new_game` / `hero_st_init` never write it. No tape save |
| Menu | Item **`5`** cycles it (digits-only menu, §3.2). It is drawn in the menu font at rows 21–22, which follows the 3-row item pitch: item 4 is at 18–19 and the KEYTAB names are on row 20. The footer `TX_FT_PRESS` line on row 22 is dropped because the digit labels are enough. The credit stays on row 23. The value is shown on the line, and the item ignores joystick input like the rest of the menu |
| In-game hotkey | **`S`** (Sound), edge-triggered. Holding S cycles once, with no repeat. S is not a default key, is not on either Sinclair half and has no SYM/CAPS meaning that we use. Redefine rejects it (`KEY RESERVED`). Not `M`, because the `.` wait key is SYMBOL+M |
| Where `S` works | Wherever `intent_tick` runs: normal play, ICON MODE, and also during ANIM ticks of a turn. It does not work on the bag page, level card, end screens or menu, and in pause it is replaced by the SOUND item |
| Turn / input safety | A UI event like `I` / `1`–`0`: it costs **0 turns**, never sets `INTENT`, never touches `FIRE_ST`, `TURN_HOLD`, `DN_T` or `NEED_RELEASE`, and is not a turn input. So a held direction keeps walking while S is pressed, and S held does not block the next turn. Edge source: a `SC_SOUND` bit in `PLAYER_SC` vs `SC_OLD` |
| Joystick-only path | **Pause box** (FIRE + ↑): `RESUME   SOUND: …   QUIT`. ←/→ move over 3 items and wrap. FIRE/ENTER on SOUND cycles it, redraws the box and **stays paused**. `S` also cycles while paused |
| Feedback | In game, a log line through the normal panel queue (§3.3). In the menu and pause, the value text on the line. **No panel icon:** the panel has no free cell, the state can be heard, and the log confirms it. The info line is not used, because it belongs to the icon or the target readout |

**Audio behaviour (the ISR player sees `SND_MODE`; it tracks its own last copy to act on edges).**
- **Music off** (bit 0 cleared): on the next frame, write volume 0 to the music channels (which
  also drops envelope mode) and mask them in R7. From then on the sequencer **does not run**,
  which saves its ~1.5k T a frame. `MUS_REQ` is still accepted and remembered. One-shots that
  were requested while muted (stinger, win, game over) are dropped.
- **Music back on:** the **current requested looping tune** (explore, danger or boss) restarts
  from **bar 1** with the 8-frame fade-in. It does not resume the old position, because the
  tune may have changed meanwhile (danger has ended, boss is dead).
- **SFX off** (bit 1 cleared): the playing effect is cut at once and the steal channel (V1,
  the inner voice) goes back to music or to silence. `sfx_req` drops requests while the bit is
  clear (a ~10 T test). With SFX ONLY, effects still play on V1 and the other voices stay silent.
  When no effect is playing, R7 is `$3F`.
- **OFF:** the player writes silence once, then returns at about stub cost (~0.3k T).
- **Pause (`SND_HOLD`):** `pause_run` sets bit 7 on entry and clears it on resume or quit.
  While it is set, all volumes are 0, the sequencer is **frozen** (not reset) and SFX are
  dropped. On resume, music **continues from the frozen position**, because a pause is short
  and the tune cannot change. A setting changed in the pause box takes effect at resume
  (music turned on in pause → restarts at bar 1, as above).
- **Title/menu:** the title tune (sound.md §3 B, X:1 or the Lament) plays while
  `SND_MUSIC` is set. Pressing `5` applies immediately: turning music off silences it, and
  turning music back on restarts the title tune at bar 1. Menu blips (sound.md §4
  move/select/cancel) obey `SND_SFX`. START hands over to the level tune as usual.
- **End screens:** X:5 / X:6 obey `SND_MUSIC`, and the screens stay silent with music off.

**Strings (upper case, no full stop, §3.4).** Use one shared prefix token `SOUND: ` and 3 value
tokens: `ALL ON` · `SFX ONLY` · `OFF`.

| Where | Font | Text (max length) |
|---|---|---|
| Menu item 5 | 8×16 | `5 SOUND: ALL ON` / `5 SOUND: SFX ONLY` / `5 SOUND: OFF` (17) |
| Pause box, row 8–9 | 8×16 | `RESUME` col 1 · `SOUND: SFX ONLY` cols 9–23 · `QUIT` col 27 (30 wide in total) |
| Log, in game | 6×8 | `SOUND: ALL ON` / `SOUND: SFX ONLY` / `SOUND: OFF` (15) |

**Byte costs (E; placement is the engineer's).**

| Piece | Bank | Bytes E |
|---|---|---|
| `SND_MODE` + boot init | 2 (byte) / low RAM boot | 1 + ~4 |
| `S` read into `PLAYER_SC` (`sample_input`) + the edge in `intent_tick` → far call | 2 | ~12 (bank 2 has ~48 B free: keep only the stub here) |
| `snd_cycle` (3 → 2 → 0 → 3, queue the log line), shared by the hotkey, menu and pause | 1 | ~20 |
| Menu item 5: draw + `5` in `menu_read`; drop the footer line | 1 | ~35 |
| Pause: 3 items with wrap, SOUND cycles in place, set/clear `SND_HOLD` | 1 | ~45 |
| Redefine: `S` added to the reserved set | 1 | ~6 |
| Strings: prefix + 3 values (shared by menu, pause and log) | text block | ~30 |
| Player: edge handling, silence, restart at bar 1, hold/freeze, `sfx_req` test | 3 (AY slot) | ~50, inside sound.md's player estimate |
| **Total** | | **~200 B; about 12 of them in bank 2** |

**Checks (`test`):**
1. Boot → `SND_MODE` = 3.
2. In play, S ×3 → 2, 0, 3. `TURN_COUNTER`, `NEED_RELEASE` and `FIRE_ST` are unchanged, and
   the log shows each string.
3. Holding S for 50 ticks → one change only.
4. Holding O and tapping S → the hero keeps walking.
5. Menu `5` ×3 cycles; the state survives death → menu → START.
6. Pause, → to SOUND, FIRE → cycles and is still paused. BREAK resumes.
7. Redefining a key to S → `KEY RESERVED`.
8. OFF, or `SND_HOLD` set → the player's AY shadow has R8–R10 = 0 (sound.md T4).

**As built (SND-1, 2026-10-19; `tests/snd1.py` = checks 1–7 plus the confirmation SFX).**
- `snd_cycle` (bank 1, `menu1.asm`) is the only writer of the setting: bits 0–1 only (`SND_HOLD`
  stays), then `SFX_MENU` through `sfx_req` (so it plays only when the new state has SFX on and is
  not held), then, in play (`GS_PLAYING`, not `SND_HOLD`), the log line, plain ASCII; it overwrites the newest pending
  line when that is already a `SO...` line, so quick `S` taps use one of the 4 log slots. No log line in the menu or the pause box.
- Strings: three whole strings `SOUND: OFF` / `SOUND: SFX ONLY` / `SOUND: ALL ON` (ids in that
  order; `snd_id` maps `SND_MODE` 0 / 2 / 3 to +0 / +1 / +2). The same string is the pause item and
  the log line; the menu draws `5` in the digit colour and the string after it (cols 4 / 6). The
  dictionary packer already shares the `SOUND: ` prefix, so a separate prefix token was not needed.
- Pause box: `RESUME` col 1, the sound item col 9, `QUIT` col 27 (menu font, rows 8–9), chosen item
  yellow; ←/→ wrap over 3; FIRE / ENTER on SOUND cycles and stays paused; `S` cycles the setting
  whichever item is selected. No log line is queued while paused.
- Hotkey: `SC_SOUND` is bit 4 of `PLAYER_SC` (`snd_scan` in `sample_input`, `snd_hot` in
  `intent_tick`; both in `sfx2.asm` after `kind_tab`). `SC_OLD` carries the edge. Held `S` = one cycle.
- Redefine: `S` joins the reserved set (`key_reserved`).
- Cost: bank 1 124 B, bank 2 25 B (8 before `kind_tab`), low RAM 0, bank 7 0.

### 3.7 Danger music trigger (designer decision 2026-10-14; cue W, sound.md §S1f, plan SND-3)

**Meaning.** The Dangerous tune (W) plays when the monsters that are pressing the hero in the
current room could plausibly kill him within about **3 turns**, counting his healing
reserve. It also plays when he is at **≤ ¼ max HP with any threat present**. It is a
judgement about the next few turns, not about the room's contents.

**Signals ruled out (cheap but wrong).**
- **Raw monster count.** 4 Bats at full HP would fire, while 1 Orc Bouncer vs a 10-HP
  Warrior would not.
- **§9.3 render weight.** It measures render cost, not threat: a Skeleton (5) outranks a
  Spider (2), and the Archer's 6 includes its projectile sprite.
- **`KX_XP`.** It is an absolute reward, so it ignores hero growth and the D1 and D7
  numbers mean different things. It also bakes in the tier ×1.5/×2 reward bonus.
- **HP fraction alone.** It fires in an empty room after a trap, and it never fires for
  a full-HP D7 hero facing 2 Berserkers and a Bone Caller.
- **"Any awake hostile in the room"** (sound.md §3 B rev 1). It would be on in most
  rooms, so W would turn into the explore tune.

**Per-kind input: `KDNG`, a 32-B table in bank 3, indexed by kind.** It goes next to
`kx_tab`, among the D3-1 tables. Stride 1, so no change to `KX_STRIDE`. The engineer places
it in memory-map.md.
- Bits 0–4 `D`: expected HP the kind takes from the hero per turn while engaged, in
  **half-HP** (D = round(2 × avg dmg × ~0.6 hit × action rate), with on-hit statuses
  rounded up). Hero DEF is ignored, which errs on the cautious side.
- Bit 7 `KD_RANGED`: counts anywhere in the room.
- Bit 6 `KD_ANYST`: counts on either storey (flyers, and the Vampire because of its bat form).

| Kind | D | Flags | Kind | D | Flags | Kind | D | Flags |
|---|---|---|---|---|---|---|---|---|
| Warrior, Mage, hole | 0 | | Skeleton | 4 | | Skeleton Archer | 4 | R |
| Rat | 2 | | Skeleton Guard | 5 | | Skeleton Sniper | 6 | R |
| Giant Rat | 3 | | Skeleton Knight | 7 | | Mummy | 4 | |
| Rabbit Rat | 4 | | Vampire | 3 | S | Necromancer | 4 | R |
| Bat | 1 | S | Ghost | 3 | S | Bone Caller | 5 | R |
| Screech Bat | 2 | S | Poltergeist | 4 | S | Ogre Warlord | 12 | |
| Slime | 1 | | Orc | 6 | | Death Knight | 14 | |
| Goblin | 3 | | Orc Berserker | 9 | | Archmage | 12 | R S |
| Goblin Slinger | 3 | R | Orc Bouncer | 9 | | | | |
| Spider | 4 | | Black Widow | 5 | | | | |

(R = `KD_RANGED`, S = `KD_ANYST`.) Golden bosses use their base row. That is safe because a
boss lives only in its lair, never follows (§8.6), and the BOSS tune masks DANGER there (below).
`D` is a playtest knob, and it is 1 byte per kind.

**Counted slot.** A slot counts if it is ACTIVE, HOSTILE, not DYING, hp > 0, and in the
current room (lazy population, §9.4, makes every live slot current-room). PENDING slots
(walking in or landing) **count**. A slot is excluded if its HOLD kind is **ASLEEP** or its
MIND kind is **FEAR** (it is not pressing, and the relief after a Sleep or Fear scroll is
meant to be audible). FROZEN and STUNNED monsters still count, because those last 1–4 turns.
Reach band: `KD_RANGED` → always. Otherwise the column gap to the hero must be **≤ 10**, and
the slot must be on the same storey or have `KD_ANYST`. Projectiles are not slots and are
never counted.

**The score (all integers, no RNG).**
- `INC` = Σ `D` over counted slots, saturating at 63. With ≤ 4 monsters per room (§9.3) the
  real maximum is 56.
- `EHP` = HP − (POISON turns >> 2) + `HEAL_RES`, minimum 1. The poison term is roughly the
  poison HP still to come. `HEAL_RES` = **10** if the quick POTION slot holds a **known Heal**
  (count ≥ 1) and the hero is not HOLD; otherwise 0. Only one potion is counted, because
  drinking costs a turn and the horizon is 3 turns. Cure, Mana, Teleport/Fear/Sleep scrolls
  and MP are **not** counted. They are the player's answers, and their effect shows up in
  the next evaluation.
- `H` (horizon, turns) = **3**, plus **2** if the hero is HOLD (FROZEN, ASLEEP or STUNNED),
  plus **1** if MIND (FEAR or CONFUSED) **or** WEAK is set. Maximum 6.
- **Enter test:** `INC > 0` **and** (`2·EHP ≤ H·INC` **or** `4·HP ≤ maxHP`).
- **Safe test:** `INC = 0` **or** (`2·EHP > (H+2)·INC` **and** `3·HP > maxHP`). The +2 turns
  and the ¼ → ⅓ floor are the hysteresis band.
- Products fit in 16 bits (≤ 8 × 63 = 504; 2·EHP ≤ 510). H·INC is at most 8 adds.

**State machine (4 B of game state: `DNG_ON`, `DNG_DWELL`, `DNG_SAFE`, `DNG_CD`).**

| Constant | Value | Rule |
|---|---|---|
| `DNG_MIN_DWELL` | **8 turns** | Once DANGER is on, it stays on for at least this many turns |
| `DNG_EXIT_TURNS` | **3 turns** | The safe test must pass on this many consecutive turns, and dwell must be done, before DANGER goes off. This replaces sound.md rev 1's "room clear 2 turns" |
| `DNG_COOLDOWN` | **6 turns** | After DANGER goes off, the enter test is ignored for this many turns, **unless the HP floor (`4·HP ≤ maxHP`) holds**. Going critical is always heard |

- CALM → DANGER: the enter test passes and the cool-down is 0 (or the floor applies). Set
  `DNG_DWELL` = 0 and `DNG_SAFE` = 0. Entry is immediate, with no confirmation turn.
- In DANGER, each turn: `DNG_DWELL` += 1 (saturating). `DNG_SAFE` = safe ? `DNG_SAFE`+1 : 0.
  When `DNG_DWELL ≥ 8` and `DNG_SAFE ≥ 3`, go to CALM and set `DNG_CD` = 6.
- In CALM, `DNG_CD` −= 1 per turn, down to 0.
- **Real-time floor.** The ISR applies a tune change at the next bar line (sound.md §3 B), and
  a request reversed before that bar is a no-op. So the shortest audible W segment is 1 bar
  (2.5 s at 96 bpm). A combat turn is 6–7 ticks (~0.27 s), so 8 turns of dwell plus 3 safe
  turns is about 3 s, or 1–2 bars.

**When it runs.** Once per **game turn**, at the end-of-turn step (§2.2), after the monsters'
logic and after regen, and before the panel. HOLD auto-turns (1 per 4 ticks) also count.
It runs once more, **without** advancing any counter, right after a room build (§9.4.3,
after residents spawn and followers are admitted) and before the scroll, so a room entered
into an ambush switches on the first bar. It never runs on ANIM ticks.

**Tune selection (`mus_pick`, the only writer of the looping request).** It runs after the
evaluator. Looping tune = **BOSS** (E) if a BOSS-flagged slot is alive in the room, else
**DANGER** (W) if `DNG_ON`, else the level's **explore** tune. `MUS_REQ` is written only on
change. One-shots (R boss dead, T win, Y game over) are requested by their own events, and
the player's priority (WIN = GAMEOVER > BOSS > STINGER > DANGER > EXPLORE) applies. When the R
stinger ends, the player resumes the **current** looping request. If an escort is still
pressing a low-HP hero, that request is DANGER.

**Edge cases.**

| Situation | Behaviour |
|---|---|
| Room exit or scroll | No reset. The state machine carries on, and the room-build evaluation adds no counts. Fleeing into an empty room drops W after the dwell and 3 safe turns. Followers count in the new room. Same for Teleport, pit falls and fear/teleport arrivals |
| Boss room | The evaluator keeps running with its counters (so the state is correct after the boss dies), but `mus_pick` picks BOSS while the boss lives. Boss death → R → resume (above) |
| Hero death | The death event requests Y (overrides everything). There is no further evaluation. `new_game` zeroes the 4 bytes |
| Pause, bag page, level card, menus, end screens | No turns, so no evaluation and the counters freeze. Pause audio follows §3.6 `SND_HOLD` (frozen, resumes in place) |
| `SND_MODE` music off | The evaluator and `mus_pick` still run, and `MUS_REQ` is written and remembered (§3.6). Nothing is audible. Music back on → the **current** requested loop (possibly W) restarts at bar 1 |
| Level change (EX_LEVEL) while on W | Descent is an escape (§9.3, nobody follows). The 4 bytes are zeroed at the level card, and the new level starts on its explore tune as sound.md specifies. DANGER never carries across a level. Start room 0 is empty, so the first evaluation is CALM |
| Win | T overrides. No evaluation after the Archmage's death sequence |

**Sanity checks (D1–D4 numbers from §4, §9.1, §10; `D` from the table).**

| # | Scenario | INC | H | Result |
|---|---|---|---|---|
| 1 | Warrior 12/24, 2 Goblins adjacent, quick Heal | 6 | 3 | 2·22 = 44 > 18, HP > 6 → **calm**. Same without the potion (24 > 18). At **9 HP with no potion**: 18 ≤ 18 → **DANGER**. With the potion, from 6 HP (floor). Matches §10's duel: 2 Goblins cost ~5–7 HP over the fight |
| 2 | Mage 4/16, 1 Rat | 2 | 3 | Pressure 8 > 6, but the floor holds (16 ≤ 16) → **DANGER**. At 4/14 the floor fails (16 > 14) → calm. At 3/14 without a Heal: 6 ≤ 6 → DANGER |
| 3 | "5 Bats": the cap is ≤ 4 monsters per room (§9.3), so 4 Bats vs Mage 16/16 | 4 | 3 | 32 > 12 → **calm** (raw count would fire). At 6/16 with no potion: 12 ≤ 12 → DANGER. Compare 4 Ghosts (D3, Mage 22/22): INC 12, 44 > 36 calm; DANGER from 18 HP without a potion |
| 4 | Warrior 20/36 (D4) ASLEEP from a GAS trap, 2 Orcs | 12 | 5 | Potion unusable (HOLD) → 40 ≤ 60 → **DANGER**. The same hero awake: H 3 → 40 > 36 calm. Status matters |
| 5 | D4 lair: Ogre (12) + 1 Orc escort, Warrior 30/36 | 18 | 3 | 2·40 = 80 > 54 calm, but BOSS (E) plays either way. After the kill (R), only the Orc is left: INC 6 → calm → explore |
| 6 | Exit band: case 1 entered at 9 HP, then one Goblin dies | 3 | 3 | Safe test: 18 > (3+2)·3 = 15 and 27 > 24 → safe. W ends after dwell 8 and 3 safe turns |

**Cost (E).** Code in **bank 3**, next to the end-of-turn code in `turn3.asm` (far call from bank
2 only if end-of-turn lives there: ≤ 6 B): evaluator + state machine + `mus_pick` **~140 B**.
Data: `KDNG` 32 B in bank 3 and 4 B of state. Time per turn: slot loop ≤ 15 slots × ~90 T
(flag tests, band test, `KDNG` lookup, add) ≈ 1.4k, plus EHP/H/multiply/compare ~0.3k,
plus state ~0.1k, plus far call ~0.2k ≈ **2k T per turn** (well under 1 % of a turn's
~6-tick budget). **0 T on non-turn ticks.** No RNG is used, so outcomes are deterministic
under `SEED_FIXED`.

**Checks (`test`, by poking state under `SEED_FIXED`).**
1. Warrior HP 9/24, no potion, 2 Goblins adjacent → after 1 Wait, `DNG_ON` = 1 and `MUS_REQ` = DANGER.
2. Same with a known Heal in the quick slot → `DNG_ON` = 0.
3. 4 Bats around a Mage at 16/16 → 0. At 6/16 with no potion → 1.
4. Enter, then poke all monsters dead → `DNG_ON` stays 1 for turns 1–7, goes 0 at turn 8
   (dwell reaches 8, and the safe count is already ≥ 3). Re-enter test true at turn +2 → still 0 (cool-down). HP poked to ≤ ¼
   → 1 at once (floor bypass).
5. Monster ASLEEP or FEAR → not counted. The same monster FROZEN → counted.
6. Lair with a live boss and `DNG_ON` = 1 → `MUS_REQ` = BOSS.
7. Descend with `DNG_ON` = 1 → all 4 bytes are 0 after the card, and `MUS_REQ` = explore.
8. `SND_MODE` = 2 (music off) → `MUS_REQ` still changes per 1. Pause → counters unchanged.

**Open (user).** (a) Should the ¼-HP floor fire against a single weak monster (case 2, Mage
4/16 vs a Rat)? Default: **yes**. (b) Should critical HP with **no** threat (after a trap,
or starving) play W? Default: **no**, because poison never kills (§6.4) and no threat means no
danger. (c) Is it OK that Mage MP and escape scrolls are not counted? Default: yes,
because the next evaluation sees their effect.

---

## 4. Classes

| Stat | **Warrior** (Knight art, `$47`) | **Mage** (Wizard art, `$45`) |
|---|---|---|
| HP / MP at start | 24 / 6 | 16 / 12 (10 + Robe 2) |
| atk / eva / DEF | 3 / 2 / 1 (Leather) | 1 / 1 / 0 |
| Melee | Short Sword 1d6, reach 1 | Oak Staff 1d4, reach 1, own **STAFF_SWING** frame. Never greys out (the 0-MP fallback) |
| MP regen (B20, designer 2026-10-19) | every **8** turns: +1 + `MAXMP` div 16 | every **6** turns (was 5): +1 + `MAXMP` div 16 |
| Mana use | 2 power attacks (§6.2) | 5 spells (§6.1) |
| Finite supplies | daggers, arrows (§6.3) | spell books/scrolls are found, never bought (§5) |
| Ranged | **throwing daggers** (range 6) + **bow** (range 14), both **finite** (§6.3) | spells |
| Start kit | **3 daggers, 0 arrows, no bow** (user 2026-10-04: the bow is found on D2, §8.5), 1 Heal, 1 Apple | 1 Heal, 1 Mana, 1 Apple |
| Ability unlock depth (rev 5: earliest depth; §5 read-time rule) | Power Strike D1 · Whirlwind D3; other books rank them up, then Vigor | Spark D1 · Firebolt D2 · Frost Shard D3 · **Drain Life** D4 · Lightning D5; other books rank them up, then Power |
| Without a book (user 2026-10-03) | sword melee only; daggers need DAGGERS > 0; bow needs the **bow** (bag item, start kit) **and** ARROWS > 0 | **staff swing only**: no spell at all until a book is read |

- **Growth (rev 5):** XP levels (§4.1), books (abilities + tomes) and gear. Boss kills no
  longer grant stats directly; they grant large XP.
- **Tome of Vigor:** +3 HP, +1 MP. **Tome of Power:** +3 MP, +1 HP. Rev 5: a tome is only
  what a class book gives once every ability is learned and at rank 3 (§5).
- **Why these level-up amounts:** the hero reaches about L8 at D8 entry (7 level-ups). In rev
  4, 7 boss kills (+3/+1) plus the tomes made W 60/18 and M 39/25 at D8; rev 5's +4/+1 (W)
  and +3/+2 (M) plus ~3 late Vigor tomes (W) land at W ~61/16, M ~37/26 (§10).

### 4.0 Balance ruling B20 / BAL1 part 1 (designer decision 2026-10-19; playtest to tune)

**Base stats (confirmed, the table above is authoritative; the code's 22/14 HP, atk 2/3 and
Mage staff 1d6+1 were stale prototype values).** Warrior HP 24, MP 6, atk 3, eva 2, DEF 1
(Leather), Short Sword **1d6+0**. Mage HP 16, MP 12 (10 + Robe 2), atk 1, eva 1, DEF 0, Oak
Staff **1d4+0**. Level-up gains and steps unchanged (§4.1: W +4 HP/+1 MP, M +3/+2; L4 atk +1,
L6 eva +1, L8 atk +1). `XP_NEXT` unchanged.

**Why (F1 `d20 + atk ≥ 10 + eva`, so P(hit) = (11 + atk − eva) / 20; monster rows §9.1 incl.
depth scaling; HP regen FED +1 / 12 turns):**

| Fight (hero level = depth) | Hero hit % × avg dmg | Turns to kill | Hero HP lost | FED turns to regen |
|---|---|---|---|---|
| W L1 vs Goblin D1 (6 hp) | 65 % × 3.5 | ~2.6 | ~2.3 (50 % × 1.75) | ~28 |
| W L1 vs Rat D1 (3 hp) | 65 % × 3.5 | ~2 | ~0.9 | ~11 |
| W L3 vs Skeleton D3 (12 hp, DEF 1) | 60 % × 2.7 | ~7.5 melee · **~4.5 with 2 Power Strikes** (70 % × 6) | ~11 melee · ~6.6 with PS | 80–130 |
| M L1 staff vs Rat D1 | 55 % × 2.5 | ~2.7 | ~2 | ~24 |
| M L1 staff vs Goblin D1 | 55 % × 2.5 | ~5 | **~6.5 (40 % of 16)** | ~78 |
| M L1 **Spark** vs Goblin D1 | always hits, 3.5 | ~2.2 casts = **4.4 MP**, at range | ~0 if cast before contact | — |
| M L2 **Firebolt** vs Goblin D2 (7 hp) | always hits, 6.5 | ~1.5 casts = 4.5 MP | ~0 | — |
| M L3 Firebolt vs Skeleton D3 (Frost/Drain I) | 6.5 | ~2 casts = 6 MP | ~0–2 | — |
| M L3 staff vs Skeleton D3 | 50 % × 1.75 | ~14 | **~26 (death)** | — |

So the Warrior wins every D1–D3 melee and spends MP only to shorten long fights; the Mage
must open with spells and the staff is a rat-and-finisher tool. Mage melee damage per turn is
~60 % of the Warrior's (1.4 vs 2.3) and her HP is 2/3: she out-damages him only through MP.

**MP economy (first pass; playtest to tune).** The pool is the per-fight budget; regen is
the between-rooms refill, so in-fight regen is kept small (≤ 1 Spark per ~12-turn fight).
Regen gain per period = **1 + `MAXMP` div 16** (≤ 16 → +1, 16–31 → +2), so refill time stays
roughly flat as the pool grows. HUNGRY doubles the period, WEAK halts it (§7), Amulet of
Mana / Scarab halve it.

| Ability | MP (rank 1) | Change |
|---|---|---|
| **Spark** | **2** (rank 1; rev 6 ranks 4 / 6, §5) | was 1: at 1 MP it out-damaged Firebolt per MP (3.5 vs 2.2) and made MP endless |
| Firebolt · Frost Shard · Drain Life | 3 · 3 · 3 (rev 6 ranks 5 / 8 each, §5) | rank 1 unchanged |
| Lightning | 5 (rev 6 ranks 8 / 12) | rank 1 unchanged |
| Power Strike · Whirlwind | 3 (5 / 7) · 4 (7 / 10) | rank 1 unchanged; rev 6 auto-downcast, §5 |

| Hero / level | `MAXMP` | Fight budget | Turns to refill from 0 |
|---|---|---|---|
| Mage L1 | 12 | 6 Sparks ≈ 2.7 Goblins / ~5 Rats | 72 |
| Mage L3 | 16 | 5 Firebolts ≈ 2.5 Skeletons | 48 |
| Mage L5 | 20 | 4 Lightnings / 6 Firebolts | 60 |
| Mage L8 | 26 | 5 Lightnings / 8 Firebolts | 78 |
| Warrior L1 | 6 | 2 Power Strikes | 48 |
| Warrior L4 | 9 | 3 Power Strikes / 2 Whirlwinds | 72 |
| Warrior L8 (+~3 Vigor) | 13–16 | 4–5 Power Strikes | 104 → 64 |

A Mage runs dry in a room of 3+ monsters at D1–D3 (then staff, retreat or a Mana potion) and
is back to half-full after ~one room transit, full after ~1–2 (a level is ~450 turns).
Resting to refill costs food: 72 turns ≈ 12 FOOD. **Knobs, in order:** Mage period 6 → 5/7;
Spark 2 → 1 at rank 3; Mage base MP 12 → 10. **Playtest note:** `DEBUG_KIT` gives MP 40/20
and every ability, so its builds cannot judge the MP economy; judge with a non-kit build.

### 4.1 Experience and levels (user 2026-10-03: add XP; numbers designer decision 2026-10-03)

**Staging (user 2026-10-04).** XP gain, level-ups and ability ranks are built in **3D**. 3C
only shows the level digit and the `LV`/`XP` info line from reserved state.

**Award.** Every monster death awards the hero `KXP[kind]` (per-kind byte in `kind_tab`,
tiers have their own rows). `F_RESPAWN` monsters (respawns, ALARM/idle waves, summons,
Rabbit Rat offspring) award `KXP / 2`, min 1 (`RESPAWN_XP_DIV`, §9.5). The Archmage awards 0
(its death ends the run). No XP for books, items, traps or exploration.

| Kind | XP | Tier 2 | XP | Tier 3 | XP |
|---|---|---|---|---|---|
| Rat | 2 | Giant Rat | 3 | Rabbit Rat | 4 |
| Bat | 2 | Screech Bat | 3 | | |
| Slime | 3 | | | | |
| Goblin | 3 | Goblin Slinger | 4 | | |
| Spider | 4 | Black Widow | 6 | | |
| Skeleton | 6 | Skeleton Guard | 9 | Skeleton Knight | 12 |
| Ghost | 6 | Poltergeist | 9 | | |
| Skeleton Archer | 7 | Skeleton Sniper | 10 | | |
| Vampire | 9 | | | | |
| Orc | 9 | Orc Berserker | 13 | Orc Bouncer | 18 |
| Necromancer | 10 | Bone Caller | 15 | | |
| Mummy | 12 | | | | |

Bosses: Golden Goblin King 20 · Spider Queen 30 · Vampire Lord 45 · **Ogre Warlord 60** ·
Pharaoh 65 · High Necromancer 80 · **Death Knight 90** · Archmage 0. (Tier XP ≈ base ×1.5 /
×2, baked into the row: no runtime multiply.)

**Levels.** `LVL` 1–9 (**max 9**), `XP` 16-bit, saturating at 9,999. Thresholds (total XP):

| Level | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|
| `XP_NEXT` | 40 | 100 | 200 | 340 | 500 | 700 | 920 | 1,150 |

Expected XP at depth entry (E, full clear incl. tiers and ~3 respawns per level): D2 ~48, D3
~116, D4 ~243, D5 ~399, D6 ~589, D7 ~827, D8 ~1,072, run end ~1,190. So the **expected
level is `LVL_EXP(d) = d`** at every depth entry (thresholds sit ~15 % under the expected
totals, so a hero who skips a few monsters still keeps pace; skipping a third of a level
drops one level). L9 comes near the end of D8, only for thorough play.

**Level-up** (each level; several at once loop): **Warrior max HP +4, max MP +1 · Mage max
HP +3, max MP +2; current HP/MP rise by the same amounts** (not a full heal). The class split
replaces the Vigor/Power tomes, which are now rare (§5: books mostly teach or rank up
abilities). Extra steps: **L4 atk +1 · L6 eva +1 · L8 atk +1** (mirrors
the monsters' atk + (d − 1) div 3, §9.1). DEF stays gear-only.

**Books still matter.** XP never teaches an ability: spells and power attacks come only from
class books (§5), repeat books raise ability ranks (§5), and the rare tomes add on top of
the level curve. Levels are the stat floor; books are the toolkit.

**Messages:** `YOU REACH LEVEL 5!` (18), then on L4/L8 `YOU STRIKE TRUER` (16), on L6
`YOU FEEL NIMBLE` (15). Death/win screens show `LEVEL n`.

**Display.** Panel cell **(31, 19)** (free; the key icon is at (30, 19)): the level digit
`1`–`9` in the 6×8 text font, attr `$46`; queued (§3.3). The **BAG icon's info line** shows
the numbers: `BAG 12/20  LV 5  XP 412/500` (≤ 42; at L9 `XP 1234`). The inventory page
header shows the same. 0 new glyphs.

**Cost.** State: `XP` 2 B + `LVL` 1 B (replaces `PL`, net +2 B). Tables: `KXP` 32 B (a
`kind_tab` column, in the current page's 48 B spare), `XP_NEXT` 16 B. Code: award hot in bank
2 ~40 B (16-bit add + one compare; ~150 T per kill); level-up in bank 3 via `far3` ~120 B
(~2k T, ≤ 8 times a run); display ~60 B. Strings ~70 B raw.

---

## 5. Learning from books

| Rule | Decision |
|---|---|
| Source | Abilities come **only** from books **found in the dungeon** (nothing is bought or granted). Melee is always available. Scrolls and ammunition are likewise found only (§8.5) |
| Placement (rev 5, designer decision 2026-10-03) | **1 class book per level D1–D7, plus a 2nd class book with 1 in 2 on D4–D7** (`ITEM_RNG`, §8.11 Q8; E ≈ 9 per run). **The D1 book lies in the start room.** D8 has none. The generator places a generic **class book** (`SPELLBOOK` / `WAR MANUAL`); *what it teaches is decided when it is read* (below), so generation never depends on hero state |
| Reading (rev 6, user 2026-10-26: uniform pick; pity designer decision 2026-10-26, user-approved; keystone rule vetoed by the user 2026-10-26) | Page verb `READ`, 1 turn on return; the book is consumed. What it teaches is decided now, **first matching step wins**: **1. Starter** — no ability known yet → learn the class's slot-0 ability (Spark / Power Strike), deterministic, 0 RNG. This is the *first book read*, normally the D1 start-room book. **2. Pity** — `BOOK_DRY` = 2 (`PITY_N`) and an eligible unlearned ability exists → learn the **earliest-depth** eligible unlearned one, 0 RNG. **3. Uniform pick** — build the candidate list: every class ability that is either *unlearned with unlock depth (§4) ≤ current depth* (outcome: learn, rank 1, fills its bar slot) or *known below rank 3* (outcome: rank +1). Each ability contributes at most one candidate (≤ 5). Pick one uniformly with **one gameplay-RNG call** at read time. **4. Tome** — the list is empty → Warrior Vigor / Mage Power (§4), 0 RNG. **`BOOK_DRY`** (0–2): any learn (steps 1–3) sets it to 0; a rank-up while an eligible unlearned ability existed adds 1; any other read sets 0. Consequence: abilities can arrive late or never (Firebolt included, ~2 %, §10 BAL1 item); a run may end Spark III with no Lightning |
| Other class's book | **CUT (user 2026-10-20, memory):** never generated; only the hero's class book exists |
| Expected yield (E, rev 6; hand Markov estimate over 9 books, verify by sim in BAL1) | **Warrior:** step 3 at D2 has one candidate (PS → II); at D3 Whirlwind ½ / PS III ½; Whirlwind is the only candidate on the next read, so it is **always learned by the first D4 book**. End state is fixed: PS III + Whirlwind III after the 5th book (~D5), then Vigor × (books − 5) = 1–5, E 3. Pity never fires. **Mage:** Firebolt by D2 ½, by D3 ⅔, by D4 ~⅞, by D5 ~93 %, by run end ~98 %. End: **all 5 spells ~61 %, one missing ~36 % (Lightning in ~¾ of those, else Drain/Frost), two missing ~3 %**; ~3.6 unlocks + ~4.4 rank-ups, Spark III in ~½ of runs; **0 Power** (14 outcomes > 10 books max) |
| Why `PITY_N` = 2 | P(end missing ≥ 1 Mage spell), same estimate: no pity ~63 % (Firebolt alone ~10 %) · N 3 ~50 % · **N 2 ~39 %** · N 1 ~12 % (≈ the old fixed schedule, kills the variety the user asked for). N 2 keeps missing-a-spell a real ~⅓-of-runs build outcome while the worst case is 1 unlock per 3 eligible reads. Pity forces the earliest-depth spell, so Firebolt is the first forced one; it is missed only when random Frost/Drain/Lightning unlocks keep resetting `BOOK_DRY` (~2 %, §10 BAL1 item) |

**Ability ranks (user 2026-10-03: repeat books level an ability; numbers designer decision
2026-10-03). Max rank 3; rank 1 = the §6.1/§6.2 row. Ranks are cumulative.**

**Rev 6 (user 2026-10-26: each rank costs much more MP; numbers designer decision
2026-10-26).** Costs: rank 2 ≈ ×1.6–1.75, rank 3 ≈ ×2.3–3 of rank 1. Damage rises with the
cost so a higher rank is **more damage per cast (tempo/burst) at a lower damage per MP**
(rank 2 ~0.85–1.0×, rank 3 ~0.7–0.8× of rank-1 efficiency). The old MP-*reduction* rank
effects (Drain III 2 MP, Lightning III 4 MP, Power Strike II 2 MP, Whirlwind III 3 MP) are
removed.

| Ability | Rank 1 (§6.1/§6.2) | Rank 2 | Rank 3 |
|---|---|---|---|
| Spark | **2 MP**, r6, 1d4+1, confuse 1 in 4 | **4 MP**, r8, **1d8+2** | **6 MP**, r8, **1d8+4**, confuse 1 in 2 |
| Firebolt | **3 MP**, r12, 1d8+2, burst 1d4 | **5 MP**, **1d8+5**, burst 1d6 | **8 MP**, **1d10+7**, burst 1d6, burst **spares the caster** |
| Frost Shard | **3 MP**, r12, 1d6, 1 bounce, freeze 2 | **5 MP**, **1d6+1**, 2 bounces, freeze 3 | **8 MP**, **1d6+3**, 2 bounces, freeze 4 (bosses halved, §6.4) |
| Drain Life | **3 MP**, r5, 1d6+1 | **5 MP**, r8, **1d6+3** | **8 MP**, r8, **1d8+5** |
| Lightning | **5 MP**, r28, 1d8+3, 2 bounces | **8 MP**, **1d8+6** | **12 MP**, **1d8+8**, 3 bounces (loop guard 4 still binds) |
| Power Strike | **3 MP**, +2 hit, ×2, stun 1 | **5 MP**, +3 hit, **×2½** (2d + d div 2), stun 1 | **7 MP**, +4 hit, **×3**, stun 2 (bosses 1) |
| Whirlwind | **4 MP**, to-hit each, dmg +1 | **7 MP**, dmg **+3** | **10 MP**, dmg **+4**, to-hit +2 |

**Auto-downcast (rule).** A cast fires at the **highest known rank the hero can afford now**;
the MP spent and the effect are that rank's row. So a rank-up never locks an ability out and
never makes it worse than before: the floor is always rank 1. The **grey-out** (§3.5) and the
`NO MANA` refusal keep the **rank-1 cost** as their threshold (unchanged code path, the
threshold is read from row 1). The rank-3 decision is *when* to spend the burst: a full pool
opens with the big cast, a drained one keeps casting at rank 1–2. **Info line:** name +
learned rank + that rank's cost (`FIREBOLT III  8MP …`, static per rank row); a downcast is
silent apart from the smaller damage number (0 new strings).

**Pool check (MP at expected level, §4.1; casts of the top rank from full, then downcasts).**

| Ability, rank | Likely first reached | Pool there | Top-rank casts / fight |
|---|---|---|---|
| Spark III (6) | D3–D4 | M 16–18 | 2–3 (+ rank-1 tail) |
| Firebolt III (8) | D4–D5 | M 18–20 | 2 |
| Frost / Drain III (8) | D6–D7 | M 22–24 | 2–3 |
| Lightning II (8) / III (12) | D5–D6 / D7 (~¼ of runs) | M 20–22 / 24–26 | 2 / 2 |
| Power Strike II (5) / III (7) | D2 (always) / D3–D4 | W 7 / 8–9 | 1 / 1 (+ 0–1 rank-1) |
| Whirlwind II (7) / III (10) | D4–D5 / D5–D6 | W 9–10 / 11–13 (+Vigor) | 1 / 1 |

Never unaffordable: every top rank ≤ the pool at the depth it is first likely reached, and
downcast covers the rest. Warrior power attacks become **one big hit per fight** (was 2–4
cheap ones); the sword stays his main damage (§4.0).

Daggers and the bow have no ranks (ammo is their limit).

**Display.** Icons are unchanged (no pip: the 24×16 art fills its 3×2 cells, a digit would
clash). The **info line name field** carries the rank as a roman suffix: `FIREBOLT II  5MP
RANGE 12  FIRE BURST`, `POWER STRIKE III` (16 = the name field max). Messages: `YOU LEARN
FIREBOLT!` · `FIREBOLT RISES TO RANK 2` (24; longest `POWER STRIKE RISES TO RANK 3` 28; no full stop, strings style).

**Data / cost.** Hero state `ARANK` 2 B (2 bits × up to 5 abilities; 0 = unlearned, replaces
the learned-bit test). Rank table: 7 abilities × 3 ranks × 6 fields (MP, range, die, bonus,
bounces, effect duration/chance) = **126 B**; the engineer may keep it in bank 3 and copy the
hero's ≤ 5 current rows (30 B) into bank 2 on learn/rank-up, so casting reads one row as now
(0 extra T per cast). Read-time book code ~90 B bank 3; strings ~60 B raw (two message
stems + roman suffixes; ability names exist).

**`abil_learn` (rev 6, engineer contract).** State: `ARANK` + `BOOK_DRY` 2 bits, packed in
`ARANK`'s 6 spare bits (0 new bytes; engineer may choose otherwise). Inputs: class, current
depth, the class's unlock-depth row (slots ordered by unlock depth, so "earliest" = lowest
slot). One pass over slots 0–4 yields candidate count `n` ≤ 5 (a ≤ 5-byte slot list or a
bitmask) and "eligible unlearned exists". Steps 1, 2 and 4 make **0 RNG calls**; step 3 makes
**exactly 1**: index = `(RNG8 × n) >> 8` (bias ≤ 1/256 for n ≤ 5; no rejection loop, so the
call count is fixed and seeded tests replay). Warrior slots 2–4 are empty (never candidates).
Same messages as before (`YOU LEARN …` / `… RISES TO RANK n` / tome).

---

## 6. Abilities, projectiles, damage types

**Projectiles and impacts are real sprites** (user preference). They are masked and
pre-shifted like any frame, but drawn under three restrictions:
- **spawned cell-aligned and moving in whole cells** (8 px/tick; Lightning 16), so each
  frame needs **one shift only**, class STATIONARY, pool = 2 × source;
- symmetric bursts skip the mirror;
- they are **render-only**: no entity slot, 0 kind ids. An FX track list holds
  `{frame, px, py, attr, path}`.

Arrows, daggers and the staff bonk are sprites too (the budget allows it, §11). Black
paper only (F9). They are drawn **after** bodies, and are redrawn on overlap like any
sprite. **≤ 3 tracks at once**; more are queued.

**Logic (instant at cast time):**
- The projectile travels cell by cell along its row in the facing direction, up to
  `range` cells in total.
- **Flight row** = caster top + 2 (staff tip / bow). If the hit body doesn't cover that
  row, it flies at the nearest row of that body.
- **In line** = a living body whose rows overlap the **caster's body rows**, the same vertical
  rule as melee `find_target`, so a Rat on the caster's floor is in line. The first such body
  whose cols the projectile enters is struck. A mid-ladder body absorbs it harmlessly: **no
  Firebolt burst** and no drop rule beyond §6.3's miss landing.
- Each body is struck **at most once per pass**. A reversal starts a new pass, so a bounce
  right behind a body hits it again on the way back. This is intended: it is the payoff of
  bounces, with no per-cast cap.
- **Drain Life striking its own caster** (after a reflection or bounce): a normal DRAIN hit
  on the caster with the normal hero-hit line. **No self-heal.**
- At a **solid cell** (wall, closed door, block, lectern, room edge) it reverses if bounces
  remain (keeping the remaining range), else stops. An open exit edge ends it.
- **After any reversal, the caster is a valid target.**
- **Spells always hit unless the target is immune or reflects** (user); arrows and daggers
  roll F1.

### 6.0 Damage types and resistances (user)

| Type | Sources |
|---|---|
| **PHYS** | melee, power attacks, arrows, daggers, monster melee |
| **FIRE** | Firebolt (+ burst) |
| **COLD** | Frost Shard |
| **SHOCK** | Spark, Lightning |
| **DRAIN** | Drain Life, Ghost touch |
| **DARK** | Dark Bolt, Death Bolt |

| Response | Effect |
|---|---|
| N | ×1 |
| **R** resist | ×½, round down, min 1 |
| **I** immune | 0 and no side effect (no freeze, no heal); `UNAFFECTED` |
| **W** weak | ×2 |
| **X** reflect | 0 damage. A projectile **reverses at the reflector's front cell** and continues with its remaining range. This does **not** use a bounce, and it can strike the caster or others. A reflected type in **melee** counts as I |

- **Pierce + reflect:** Lightning stops piercing at a reflector and reverses there.
- **Loop guard:** max 4 reversals per projectile. Range is finite in any case.
- **Encoding (engineer):** per kind 6 × 2 bits {N, R, I, X} + a 6-bit W mask ≈ 3 B.
- **The hero uses the same format**, OR-combined from worn gear (best response wins).
- Falls and the Tome's aura ignore resistances.

### 6.1 Mage spells (dmg ignores DEF)

| Spell | Book | MP | Range | Dmg / type | Bounces | Effect | Projectile → impact sprites |
|---|---|---|---|---|---|---|---|
| **Spark** | D1 | **2** (B20, was 1) | 6 | 1d4+1 SHOCK | 0 | **1 in 4: CONFUSED 4** (§6.4; 3D; was 3, §6.4.1) | spark_fly1/2 8×8 `$43` → spark_fizz1/2 8×8 |
| **Firebolt** | D2 | 3 | 12 | 1d8+2 FIRE | 0 | **burst**: bodies within 1 col of impact take 1d4 FIRE, **caster included** at point-blank (impact within 1 col of the caster's front col; ranks 1–2, intended; rank 3 spares him) | firebolt_fly1/2 16×8 alternating yellow `$46` / red `$42` per frame (**user 2026-10-06**) → firebolt_burst1/2 16×16 |
| **Frost Shard** | D3 | 3 | 12 | 1d6 COLD | **1** | **freeze 2 turns** (bosses 1); can freeze the caster after a bounce or reflection: **1 turn at any rank** (§6.4.1) | frost_fly 8×8 `$45` → frost_crack **8×8** (**user 2026-10-06**: stays 8×8, not 16×16; revisit after playtesting) |
| **Drain Life** | D4 | 3 | 5 | 1d6+1 DRAIN | 0 | **caster heals the damage dealt** (to max HP); useless on undead (I) | **drain_fly1/2 16×8 `$43` → drain_hit 16×16 (new art)**; the caster flashes `$44` |
| **Lightning** | D5 | 5 | 28 | 1d8+3 SHOCK | **2** | **pierces** (each body once per pass) | lightning_fly1/2 16×8 `$47` (16 px/tick) → lightning_flash 16×16 |

- Cast: CAST1 2 → CAST2 3 ticks, with the hero flashing the spell ink. The projectile spawns
  on the CAST2 tick, so the release tick f = 2 (`FXD_DELAY` 2). No per-spell cast frames.
- **Release ticks, all abilities (designer decision 2026-10-12):** every strike or release
  falls on **tick 2**, as melee SLASH does:
  - Throw: WIND-UP 2 → THROW 3.
  - Bow: BOW 4, with the arrow on tick 2.
  - Power Strike: WIND-UP 2 → POWER_STRIKE 3, with power_burst 2 ticks on the target.
  - Whirlwind: WIND-UP 2 → WHIRL 3, with spark_fizz 2 ticks on each side.
  - Staff bonk: CAST1 2 → STAFF_SWING 3.
- **Mage bar = staff + 5 spells + food + potion + scroll + bag** (10 slots, §3.5). Drain
  Life is **added**, not swapped for anything.

### 6.2 Warrior power attacks (MP) and melee

| Ability | Book | MP | Target | Effect | Frames |
|---|---|---|---|---|---|
| Melee | — | 0 | in reach | F1/F2, weapon die, PHYS | Warrior WIND-UP → SLASH → FOLLOW; Mage CAST1 → **STAFF_SWING** + staff_bonk 16×16 |
| **Power Strike** | D1 | 3 | in reach | to-hit +2, **damage ×2**; a hit that does not kill **STUNS 1** (§6.4; the Warrior's stun bash, no new icon or art) | WIND-UP → **POWER_STRIKE** 40×48 + power_burst 16×16 |
| **Whirlwind** | D3 | 4 | **every** hostile in reach, both sides | to-hit each, dmg +1 | **WHIRL** 40×48 + spark_fizz each side |

A power attack with no target is illegal (no turn, no MP).

### 6.3 Warrior ranged

| | Throw dagger | Bow |
|---|---|---|
| Ammo (counter) | `DAGGERS` **0–9** | `ARROWS` **0–24** |
| Start (user 2026-10-04) | **3** | **0** (no bow either; the bow + 6 arrows are found on D2, §8.5) |
| Range / to-hit / dmg | 6 / atk+1 / 1d4+2 PHYS | 14 / atk / 1d6+1 PHYS |
| Frames | WIND-UP → **THROW** 32×48 | **BOW** 32×48 |
| Projectile sprites | dagger_spin1/2 8×8 `$47` | arrow1/2 16×8 `$07` → arrow_hit 8×8 |

Both are legal with no target. Axe throwing is dropped (daggers only).

**Finite ammunition (user, rev 3).** The Warrior's ranged play is a resource, not a free
attack. Rules:

| Rule | Dagger | Arrow |
|---|---|---|
| Spent | −1 on every throw/shot | −1 on every shot |
| **On a hit** | lost **1 in 4** (RNG), else drops as a floor item under the target's feet | **always broken** (consumed) |
| **On a miss** | lost **1 in 4**, else lands at the impact cell (wall cell: the free cell in front; range end: that cell) | **50 % recoverable**: lands like a dagger; else broken |
| Recovery | walk over it: normal auto-pickup, +1 each | same |
| Lost in a pit column | always lost (falls away) | always lost |
| Floor list full (§8.5, 32) | lost | lost |

- Expected throws per found dagger ≈ 4 (a 25 % loss per throw), so a small supply stays
  useful but really does run out. Arrows are ≈ 1 shot each, ~1.3 with misses.
- **Stack limits:** `DAGGERS` 9, `ARROWS` 24. Pickup takes what fits; the remainder stays on
  the floor and `QUIVER FULL.` prints.
- **At 0 ammo:** that icon **greys out** (`$07`; selected+greyed `$0F`), FIRE on it is
  illegal (no turn, no MP) and prints `NO DAGGERS.` / `NO ARROWS.`. **Melee is always
  available** (the sword icon never greys). Info line shows `NONE LEFT`.
- **No bow (rev 5, user 2026-10-03: no weapon → no ranged):** the **bow is a bag item** (1
  slot; **not in the start kit: guaranteed find on D2**, user 2026-10-04, §8.5; can be dropped, never worn, never worn down or shattered). Without it in the
  bag the bow icon greys exactly as at 0 arrows and FIRE prints `NO BOW.`; arrows are still
  picked up. Daggers are both weapon and ammo, so `DAGGERS = 0` is the only dagger gate.
- Dropped-ammo floor items merge into one stack per cell and are drawn as the 8×8
  dagger/arrow item glyph: **common tile ids 17 `T_DAGGERS` (ink `$47`) and 18 `T_ARROWS`
  (ink `$07`)**, taken from `T_DRIP1/2` permanently. Drips become per-level decor if they are
  ever placed (designer decision 2026-10-12).
- **"Under the target's feet"** = the impact col on the target's storey item row (`9s+7`).
  This also covers **flyers**: the dagger drops straight down to that storey's floor. The cell
  must be non-solid, with solid floor below. Otherwise try 1, then 2 cols back toward the
  caster; if neither works, the dagger is lost. A pit col is always a loss.
- **Shared cells:** a dropped stack may share a cell with any other floor item, such as a
  potion. Each item keeps its own floor-list entry; same-type ammo merges. Stepping on the
  cell picks up every entry by its own rule. The **last live entry in list order** is drawn,
  and it is re-stamped when a pickup leaves anything behind. The D2 bow + 6-arrow bundle
  already relies on this rule.
- `QUIVER FULL.` is one string for both counters. It prints on any pickup that leaves ammo on
  the floor, in the same way as `BAG FULL.`.
- Skeleton Archers' arrows are not recoverable (monster projectiles leave no item); the
  Archer's own drop is the supply (§8.5, §9.1).
- The **Mage has no ammunition**; his limit is MP and the found books/scrolls.

### 6.4 Status effects (3D; user 2026-10-03 scope, designer decision 2026-10-03 details)

Seven effects in **four groups**. Effects in one group are exclusive; groups combine freely.

| Group | Effects | Field |
|---|---|---|
| **HOLD** (cannot act) | FROZEN · ASLEEP · STUNNED | 2-bit kind + 4-bit turns |
| **MIND** | FEAR · CONFUSED | 2-bit kind + 4-bit turns |
| **POISON** | POISON | 1 bit + 4-bit turns |
| **WEAK** | WEAK (curse) | 1 bit + 4-bit turns |

**Data shape (per entity, 3 B + 1 spare; the engineer assigns layout in memory-map):**
- `STATUS`: bits 0–1 HOLD (0 none, 1 FROZEN, 2 ASLEEP, 3 STUNNED) · bits 2–3 MIND (0 none,
  1 FEAR, 2 CONFUSED, 3 reserved) · bit 4 POISON · bit 5 WEAK · bit 6 **HOLD_GUARD** (was STUN_GUARD; generalised
  to **HOLD_GUARD**, §6.4.1) · bit 7
  reserved. Invariant: a group bit/kind is set ⇔ its timer nibble ≠ 0. `STATUS = 0` is the
  fast path (skip the whole step).
- `STMR1`: high nibble HOLD turns, low nibble MIND turns. `STMR2`: high nibble POISON turns,
  low nibble WEAK turns. **Max 15 turns** per effect. **POIS1 (2026-10-26): POISON moves to
  the full byte 3 (`ST_X`, the spare per-slot array, so the cap is 30 turns, §6.4.3). The
  `STMR2` high nibble becomes spare. `STS_POISON` ⇔ `ST_X ≠ 0`.**
- Per kind: an **immunity mask** (1 B: bits SLEEP, STUN, CONFUSE, FEAR, POISON), §9.1. The
  hero's mask = OR of worn gear (Silk Cloak: POISON).
- **Where (budget):** the 32-B entity record has **no free byte** (+0..+31 all assigned; +8
  POT frees only when the 3E bag replaces it). Recommended: a parallel **`ENT_STAT` table,
  16 slots × 4 B = 64 B in `BANK2_FREE`** (`slot*4`), byte 3 spare (e.g. the Vampire's
  fled-once bit). Engineer's choice; the record format stays.

**Status step** (start of the entity's own action phase, §2.2), in order:
1. POISON: decrement; if the new value is a multiple of **4** (POIS1; was 3), lose **1 HP** (ignores DEF and
   resistances; **never below 1 HP**: no source poisons monsters, so poison never kills).
2. WEAK, MIND: decrement; at 0 clear (end message, hero only).
3. HOLD: if set → decrement, **skip the action** (cooldowns do not tick); at 0 clear. If
   STUNNED just cleared, set HOLD_GUARD (§6.4.1: FROZEN too).
4. Otherwise act; after the action, clear HOLD_GUARD.

Because the step runs before the action, "duration *n*" = the entity loses exactly its next
*n* action phases, whether applied in phase 1 (a hero spell on a monster) or phase 2 (a
monster hit on the hero), with no "applied this turn" flag. A banked monster (other room)
**loses its status**; an admitted follower keeps it (§6.4.2 R3).

| Effect | Does | Ends | Durations / sources |
|---|---|---|---|
| **FROZEN** | skip action; eva counts as **0** against it | timer; **any FIRE damage ≥ 1 thaws it** | Frost Shard 2 / 3 / 4 by rank (COLD hit); self after a bounce or reflection **1** (§6.4.1) |
| **ASLEEP** | skip action; eva 0 | timer, or **any HP loss** (incl. poison, aura) wakes it | Sleep scroll 8 (room), GAS trap 4 (hero), hunger faint 5 (hero, §7.1) |
| **STUNNED** | skip action; eva 0; cannot parry | timer (**not** HP loss). **HOLD_GUARD:** cannot be stunned again until it has taken one action | Power Strike 1 (hit, no kill), Ogre SLAM hit 1 (hero), STUN trap 2–3 rolled (hero, §1.5.1) |
| **CONFUSED** | hero: each turn-costing walk/bump/jump/facing-icon action is **reversed with 1 in 3** (turns, then acts the other way); if the reversed action fails because of the direction the turn is spent (`YOU STUMBLE.`); a non-direction refusal costs no turn and faces back (§2.3, §6.4.2 R4). Whirlwind, climbs, page verbs, quick food/potion/scroll and 0-turn turnarounds never roll. Monster: 1 in 2 its action is replaced by a step in a random direction (illegal → wait; walkers still never step to `x == pit col`); a confused monster never shoots | timer; Cure (hero) | Spark 1 in 4 (rank 3: 1 in 2) → **4** (was 3, §6.4.1); Ghost touch 1 in 4 → 4 (hero) |
| **FEAR** | hero: **no melee-reach action** (melee, bump attack, Power Strike, Whirlwind) → illegal, no turn, `YOU ARE TOO AFRAID TO FIGHT!`; ranged, spells, items allowed. Monster: steps away from the hero; cornered (no legal step away) it melees if the hero is in reach, else waits; never shoots | timer; Cure (hero) | Fear scroll 6 (room); Necromancer **Dark Bolt** hit 1 in 3 → 3 (hero) |
| **POISON** | −1 HP every **4th** turn (step 1); **cannot eat** (§7.2) | timer; Cure | **adds per application, cap 30** (POIS1, §6.4.3): Spider bite **12**, Giant Rat 12, Spider Queen **18**, Black Widow **24**, DART trap 12 |
| **WEAK** | the hunger-WEAK penalties (§7: atk −2, eva −1, dmg −1 min 1 on **physical hits only**, §6.4.2 R1, no MP regen, no jump); **not cumulative** with hunger WEAK (the same penalties apply once) | timer; Cure | **Mummy curse** (below) 12 |

**Mummy curse (defines §10's "curse").** A Mummy (and the Golden Pharaoh) hit drains 5 FOOD
as before and, **1 in 3**, curses: WEAK 12. `THE MUMMY CURSES YOU!` WEAK is a hero-only
effect (no source targets monsters).

**Stacking / refresh.** Same effect again → timer = **max(current, new)**, never added
(**exceptions, §6.4.1:** POISON adds, cap 30 (POIS1 §6.4.3; was 15); no HOLD lands on a body already held). A
different effect in the same group **overwrites** kind and timer (a Frost Shard on a sleeper:
the COLD damage wakes it, then FROZEN applies). Groups are independent.

**Bosses** (`BOSS` flag: golden bosses, Ogre, Death Knight, Archmage): **immune to ASLEEP and
FEAR**; HOLD and MIND durations are **halved, round down; 0 = no effect** (Frost 2 → 1, as
before; Power Strike stun 1 → none; Spark confusion 3 → 1). POISON full. Check order and
messages: §6.4.2 R2.

**Resistances (§6.0) for effects carried by a typed hit:** the effect applies only if the hit
dealt ≥ 1 damage (a parry, I or X gives nothing); response **I/X → no effect**, **R →
duration halved (round down, 0 = none)**, N/W → full. So: Frost freeze follows COLD, Spark
confusion SHOCK (a reflected Spark can confuse the Mage), Power Strike stun PHYS (Slime,
Ghost, Mummy, Ogre resist PHYS → no stun), Dark Bolt fear DARK (Ring of the Grave, Mirror
Helm block it), Ghost confusion DRAIN (Gravecloak halves 4 → 2). Typeless sources (scrolls,
traps) use only the immunity mask and the boss rule.

**Indication.**
- **Sprite tint (monsters and hero):** the entity's stamp attr ink is replaced while HOLD or
  CONFUSED is set: FROZEN `$45`, ASLEEP `$41`, STUNNED `$07`, CONFUSED `$43` (black paper,
  F9; `$46`/`$47` are avoided: they read as the gold boss glow, `$42` is the hit flash). If a
  tint equals the body's base attr it uses its BRIGHT-toggled twin (`attr XOR $40`; e.g. a confused
  Bat `$43` → `$03`). Priority: hit flash > HOLD tint > CONFUSED tint > gold glow > base attr.
  Cost: the footprint attrs are rewritten once when the tint changes (~0.12k T/cell, ≤ 2.9k T,
  like one glow step); redraws use the current attr at 0 extra. `$41`, `$07` join the
  legality set.
  FEAR, POISON, WEAK have no tint (behaviour and the panel show them).
- **Hero panel icons:** row 21, **cols 30–31** (free on both bars: the Warrior's ammo text
  ends at col 28), up to **2 × 8×8 status icons**, priority HOLD > MIND > POISON > WEAK, one
  attr per cell (no clash): FROZEN `$45`, ASLEEP `$41`, STUNNED `$07`, CONFUSED `$43`, FEAR
  `$42`, POISON `$44`, WEAK `$42`. **7 glyphs × 8 B = 56 B**, panel glyphs like the row-17
  ornament, **not tile ids** (concept-screen §5). Updated via the panel queue (§3.3).
- No overhead "Zz" **FX track**: a persistent FX track would cost ~5k T/tick and a track slot.
  **Superseded 2026-10-13 by §6.4.1:** a cell-aligned overhead **status mark** with its own
  list (not an FX track), drawn only on change.

**Messages (all ≤ 32, upper case; monster lines only for monsters in the current room, with
the ≤ 12-char short name from the KILLED-BY abbreviation table: `THE ` + 12 + suffix ≤ 30):**

| Event | Hero | Monster suffix |
|---|---|---|
| FROZEN | `YOU ARE FROZEN SOLID!` | ` IS FROZEN.` |
| ASLEEP / wakes | `YOU FALL ASLEEP.` / `YOU WAKE UP.` | ` FALLS ASLEEP.` / ` WAKES UP.` |
| STUNNED | `YOU ARE STUNNED!` | ` IS STUNNED.` |
| HOLD ends (frozen/stunned) | `YOU CAN MOVE AGAIN.` | — (tint drops) |
| CONFUSED / ends / misstep | `YOU FEEL CONFUSED.` / `YOUR HEAD CLEARS.` / `YOU STUMBLE.` | ` IS CONFUSED.` |
| FEAR / ends / blocked | `YOU ARE TERRIFIED!` / `YOU REGAIN YOUR NERVE.` / `YOU ARE TOO AFRAID TO FIGHT!` (28) | ` FLEES!` |
| POISON / ends | `YOU ARE POISONED!` / `THE POISON WEARS OFF.` | — |
| WEAK curse / ends | `THE MUMMY CURSES YOU!` / `YOU FEEL STRONGER.` | — |
| immune | — | ` IS UNAFFECTED.` |

**Cost.** Status step: `STATUS = 0` fast path ~20 T/entity; active ~150–250 T; ≤ 16 entities
≈ ≤ 4k T per turn in the input tick (E0 margin). Code ~0.45 KB (hold/skip/eva checks hot in
bank 2 ~150 B; apply/clear/messages/tint in bank 3 via `far3`, ~300 B). Strings ~0.45 KB raw.

### 6.4.1 Status review: durations and on-body cues (designer decision 2026-10-13)

**Balance changes** (everything not listed keeps its §6.4 value):

| # | Change | Why |
|---|---|---|
| B1 | **HOLD_GUARD** replaces STUN_GUARD: set when FROZEN or STUNNED ends (timer or FIRE thaw); while set, FROZEN and STUNNED do not apply (`IS UNAFFECTED.` is **not** printed: silent). Cleared after the body's next action, as before. ASLEEP is not guarded (damage already breaks it) | Frost recast on the last frozen turn chain-locked any COLD-N monster for 3 MP per 2–4 turns: zero monster actions while MP lasts. Guarded uptime is capped at n/(n+1): 67 / 75 / 80 % by rank |
| B2 | **No HOLD lands on a held body:** FROZEN/STUNNED/ASLEEP on a body whose HOLD is set → no effect (damage still applies). A sleeper is woken by the hit first, so Frost on a sleeper still freezes | Refresh (max) and overwrite (Stun → Frost) were the other ways to extend a lock |
| B3 | **Self-freeze = 1 turn** at every rank: a Frost Shard striking its own caster (bounce, Ghost/Archmage reflection) freezes for 1, whatever the rank | Rank-ups added bounces *and* length, so rank 3 punished its own caster with 4 eva-0 turns; the Archmage reflects Frost (§9.1), which at rank 3 was a near-certain death. The risk stays, the spike goes |
| B4 | **Spark CONFUSED 3 → 4** (all ranks; rank 3 chance 1 in 2 unchanged; bosses 4 → 2) | A confused monster loses only 1 in 2 actions, so 3 turns ≈ 1.5 lost actions on a 1-in-4 proc ≈ 0.4 per cast: invisible. 4 ≈ 2 lost actions; the boss value goes from 1 (≈ 0.5, unnoticeable) to 2 |
| B5 | **POISON adds** per application, cap 15 (still −1 HP every 3rd turn, never below 1 HP). Spider **6** per bite (was 9), Spider Queen **9** (was 12), DART 6. **Amounts, cap and tick rate superseded by POIS1, §6.4.3 (adding stays)** | With max() a long Spider fight cost the same 3 HP as one bite: more bites must hurt more. 1 bite = 2 HP (was 3), 2 bites = 4, 3+ = 5 (cap). Safe because poison cannot kill |

**Reviewed, unchanged.**
- Power Strike stun 1 / 1 / 2 (bosses — / — / 1; PHYS-R kinds — / — / 1; Ogre: none). It is a bonus on a ×2 hit.
- Ogre SLAM stun 1 (hero).
- Ghost CONFUSED 4 (hero; Gravecloak 2).
- Necromancer FEAR 3 (hero) and Fear scroll 6 (room).
- Sleep scroll 8 (room). The first hit wakes, so the value is one free strike per sleeper plus repositioning.
- GAS ASLEEP 4 (hero). It costs approach turns, and one near-sure hit wakes him.
- Mummy WEAK 12. It covers the Mummy fight and about half of the next one.
- **Whirlwind applies no status.** Slow monsters ("acts every 2") lose about half as many real
  actions to any timer. This is accepted, because timers count game turns.

**On-body cues.** Colour is not enough. **Every HOLD/MIND body (hero and monsters) also gets
(V1) a frozen pose and (V2) an overhead status mark.** POISON and WEAK are hero-only and slow,
so they stay on the panel icons plus the magenta `-1` poison number (§6.5).

| Rank | Cue | Effects | Art | Cost |
|---|---|---|---|---|
| **V1** | **Hold the pose:** a HOLD body's idle loop stops (`idle_phase` → 0 while HOLD), so bats stop flapping and the hero stops breathing | FROZEN, ASLEEP, STUNNED | none | ~15 B, ~40 T per drawn slot. It **saves** the idle-frame redraws (12–28k T each) |
| **V2** | **Status mark:** one 8×8 glyph above the head that alternates frame A / frame B every **8 ticks**. Frame A is the existing panel icon. **Frame B is derived (user / manager 2026-10-14): frame B = frame A shifted up 1 px; ASLEEP / STUNNED (full-height glyphs, the shift would clip the Z's top bar): a BRIGHT toggle (attr XOR $40)** | FROZEN ✻, ASLEEP Zz, STUNNED stars, CONFUSED ?, FEAR skull (one per body, HOLD > MIND) | **A: existing** (`status_icons` 0–4). **B: derived in code** (no new art) | ~0.5–0.6k T per change (restore 1 background cell + OR 8 B + 1 attr); ~250 B code, 80 B glyph copy, ~32 B RAM |
| V3 | **Apply moment:** reuse the hit's own impact (frost_crack, power_burst, spark_fizz, Ghost touch). Sleep scroll and GAS give a 1-step `$41` attr flash. Fear scroll: the mark appearing is the cue | all | existing | ~0 (flash mechanism exists) |

**Rejected.**
- Shake/jitter: a 1-px move is a full shifted body redraw, 12–28k T per body per tick.
- Alternating tint: the attr channel is already full (§6.5), a flicker reads as the hit flash, and it costs ≤ 2.9k T per body per toggle.
- Persistent FX-track overlays: they take 1 of the 3 tracks and ~5k T per tick.
- Ice-shell overlay sprite: a second masked body draw.
- Green poison bubbles: green means "HP gained" (§6.5), and poison is hero-only and already covered.

**Status mark rules (V2).**
- **Place:** the body's centre column (`x + (w−1) div 2` cells, rendered x rounded to a cell), on
  the row above the body's top cell. The glyph uses the effect's tint attr (`$45` / `$41` / `$07` /
  `$43` / `$42`) on black paper. As with numbers, a decor or ladder cell under it is accepted clash.
  **Hidden** when that row is above the storey band (a flyer at `y = 9s`; it keeps its tint and
  frozen pose) or when the cell lies inside another body's footprint.
- **Follows** a moving body (CONFUSED/FEAR walk): erase plus draw when the cell column changes, at
  most once per cell step.
- **Own list, not an FX track:** one record per slot `{drawn, frame, col, row}`, derived from
  `ST_FLAGS`. A record changes on apply, clear, move or the 8-tick toggle. Toggle phase = `(TICK + slot × 3) & 15`, so
  marks do not all toggle together.
- **≤ 2 mark operations per tick.** Extra operations wait a tick, round-robin. **None on a
  `TP_FIRE` tick** (like panel and decor), so the cast worst case (`lcast` 126.8k) is untouched.
  Worst ordinary tick: +~1.2k T for 2 operations, plus a ~0.3–0.6k T scan. Skip the scan when no
  live body has HOLD/MIND set.
- **Draw order:** bodies → FX tracks → **marks** → numbers. The D3-8b drip is not an FX track: it is
  a one-record overlay drawn only into a cell no body or FX covers (a body or FX moving onto it
  overlaps it for at most 1 tick, then it is dropped and the cell repaired). An FX or
  number erase that overlaps a mark cell re-stamps the mark in the same tick (~0.3k T).
- **Damage numbers (D3-11):** a live number over a body **hides that body's mark** for the
  number's 12 ticks. Both use the row above the body: the number is the event, the mark is the
  state. The mark is re-stamped when the number ends.
- **Room change** clears all marks. The marks are rebuilt from `ST_FLAGS` on entry.

**Frame B brief — superseded 2026-10-14 (frame B is derived: A shifted up 1 px, ASLEEP / STUNNED a BRIGHT toggle; no artist task). Kept for a later art pass:**
- Zz: the small z rises and the big Z sinks, giving a drifting motion.
- Stars: rotated 45°, so the two frames read as orbiting.
- Snowflake: a diagonal-arm sparkle variant.
- `?`: shifted 1 px and tilted, so it wobbles.
- Skull: 1 px lower with the jaw open, so it trembles.

**Decorative drip (D3-8b).** The drip stays ambient. Its attr is **`$01` or `$05`** (dim
water). It must never be `$44` or `$43` (the heal and poison colours), and never `$45` or `$41`
(the mark colours). **The poison-trap drip variant is rejected:** over a hidden trap it would
reveal it and break §1.5 trap finding, and over a known trap it repeats the `T_TRAP` glyph.

### 6.4.2 Status rulings (designer decision 2026-10-13)

| # | Question | Ruling | Why |
|---|---|---|---|
| R1 | Scope of WEAK `dmg −1` (curse **and** hunger stage, one rule) | Applies to **hero-dealt PHYS damage only** = exactly where DEF applies: melee, Mage staff bonk, Power Strike, Whirlwind, thrown daggers, arrows. Order: `max(1, roll × mult × resist − DEF − 1)` (Power Strike: after ×2). **Not** to spells (they ignore DEF): Spark, Firebolt + burst, Frost, Drain Life (heal = damage dealt, unreduced), Lightning, and a hero spell bounced/reflected onto himself. Not to traps, poison, monster hits. `atk −2` still applies to every hero to-hit roll | WEAK is lost strength; MP-regen halt is already the Mage's penalty. Gate = "DEF path", no extra source flag |
| R2 | Boss + short ASLEEP/FEAR (halving runs before the immunity check, so nothing prints) | Fixed check order in `dh_status`: **(1) immunity mask + boss ASLEEP/FEAR immunity → ` IS UNAFFECTED.`** (stop); (2) typed-hit resistance I/X → none, R → halve; (3) boss halve; (4) B2 held-body / HOLD_GUARD. A result of 0 in steps 2–3 and any step-4 block are **silent** | Immunity is a fact the player should learn; a halved-to-0 stun on a boss is a partial resist already shown by the damage number, and printing it after every Power Strike is log spam |
| R3 | Status of monsters leaving the room | **Accept the deviation:** banked monsters lose all status (§9.4.2 residue); no pause storage. **Admitted followers keep** their full 4-B status record (kind bits, timers, HOLD_GUARD), copied with the slot; timers do not tick during the transition. **HOLD or FEAR bodies are not follow candidates** (prototype §3.7 step 1); CONFUSED ones may follow | Pause would cost ≤ 4 × 9 rooms × 3 B ≈ 108 B of the 235 B bank-3 free for no visible gain (re-entry already re-places and keeps hp). A frozen monster walking through the door, or a fleeing one chasing, reads as a bug |
| R4 | Confused hero + Whirlwind with no target | Whirlwind **never rolls** confusion (it strikes both sides; reversal is meaningless). No target → the plain §6.2 refusal: no turn, no MP. General reversed-path rule (§2.3): **direction failure → `YOU STUMBLE.`, turn spent, stays reversed**; **non-direction refusal (NO MANA, NOT LEARNED, AFRAID, no ammo/bow) → no turn, faces back** (user, confirmed) | A stumble must be caused by the confusion; Whirlwind's miss never is |

### 6.4.3 Poison review: longer poison, no eating (POIS1; user 2026-10-26 scope, designer decision 2026-10-26 details)

The user asked for poison to last longer, and a poisoned hero **cannot eat** (§7.2). POISON
stays hero-only (no source poisons monsters). It still **adds** per application and still
**never takes HP below 1**.

| Rule | Was (B5) | Now |
|---|---|---|
| Durations (turns per application) | Spider 6 · Giant Rat 6 · Spider Queen 9 · Black Widow 12 · DART 6 | **×2: Spider 12 · Giant Rat 12 · Spider Queen 18 · Black Widow 24 · DART 12** |
| Cap | 15 (one nibble) | **30**. The timer moves to the full byte `ST_X` (§6.4 data shape) |
| Tick | −1 HP when the new value ≡ 0 mod 3 | **−1 HP when the new value ≡ 0 mod 4** (`and 3`, cheaper than the mod-3 loop) |
| HP per application (fresh, = ⌈n / rate⌉) | 2 · 2 · 3 · 4; cap 5 | **3 · 3 · 5 · 6; cap 8** |

**Why ×2 length but only ~×1.5 damage:** the length is what matters now. It is the window in
which the hero cannot eat, and the window in which a Cure is worth carrying. Doubling the HP
too would have been 4 · 4 · 6 · 8 / cap 10. Poison can't kill, so that cannot end a run on its
own, but it would leave the D2 Mage (19 HP) at about half HP after one Spider Queen fight.

**Lethality check (poison cannot kill; it softens the hero for the next fight).**
- D2 Spider (7 hp, ~2 bites a fight → 24 turns): **6 HP** over 24 turns (was 4 over 12).
  FED regen gives back +2 (1 per 12 turns), so net −4. That is 14 % of the Warrior's 28 HP
  and 21 % of the Mage's 19 HP.
- Spider Queen (3–4 bites → cap 30): **8 HP** over 30 turns, net −6 after regen (was 5 / −4).
  That is 21 % of the Warrior's HP and 32 % of the Mage's. It is the D2 boss, Cure is its §10
  answer, and Firebolt is the Mage's.
- D5 Black Widow (one bite 24 → 6 HP; two → cap 8): net −4 / −6 after regen. That is 15 % of the
  Warrior's 40 HP and 21 % of the Mage's 28 HP.
- Worst case at any depth: a capped hero loses **8 HP over 30 turns**, never below 1 HP.
- The danger estimate (§3.7) uses `EHP = HP − (POISON turns >> 2)`. That is now exactly the
  remaining poison HP (turns / 4), so the formula is unchanged. It reads `ST_X`.

**Cure supply (re-checked).** A level holds 2–3 potions: entry 0 is Heal, and entries 1..n are
uniform Heal/Mana/Cure. That gives **0.5 Cure per level**, and **~44 % of levels have at least
one**, plus monster drops (Q11). Cure is **not** the only way out. **Time always cures:** the
timer is capped at 30, so the no-eat window is at most 30 turns after the last bite. It can only
be extended by being bitten again (fighting poisoners) or by walking onto a known DART again
(self-inflicted). §7.2 shows that this cannot become an unavoidable starvation spiral.
Unchanged: the Cure frequency and the potion roll. Changing either would move every later
`ITEM_RNG` output.

**Implementation (staff).**
- **Status step** (`status7.asm` step 1): read/write `ST_X + slot` (page `$B4`, the same low
  byte as STATUS − `ST_FLAGS & $FF`) instead of the `STMR2` high nibble, and use the `and 3`
  test. About −2 B net (the mod-3 loop goes).
- **Apply** (`deal_hit` poison branch, combat3): add to the byte, cap `PSN_CAP` 30. It is
  already a special case, and it leaves the nibble write path. About +12 B in bank 3.
- **Cure** (`fx6.asm`): also zero `ST_X` slot 0 (+3 B). The **danger EHP** reads `ST_X`
  (±0). `level_reset` / `new_game` already zero `ST_X`.
- **Constants:** amounts ×2. Relax `TRAP_DART_PSN <= 15` and every amount `ASSERT` to `<=
  PSN_CAP`. Check any kind-table field that packs a poison amount into 4 bits: 18 and 24 do
  not fit. Store the amount / 2, or widen it (engineer's choice; the values are all even).
- **Bytes:** ≈ **+15 B** (bank 3 +12, R6 +3, bank 7 ±0).
- **Tests:** these rebaseline every test that pokes or reads poison in `STMR2`.
  - Fresh 12 → exactly 3 HP lost over 12 turns, then `THE POISON WEARS OFF`.
  - 12 + 12 + 12 → timer 30 (cap).
  - HP 1 never drops.
  - A sleeper wakes on a tick.
  - Cure zeroes it.
  - A level change keeps it (slot 0 carry).

**BAL1 knobs:** the four amounts, `PSN_CAP` 30 (24–30), and the tick rate (4; 3 brings back
the old HP per turn). If poison feels like a nuisance rather than a threat, drop the rate to 3
before raising the amounts. If the no-eat lock bites too hard, lower `PSN_CAP` first. If Cure
feels absent where poison is common, the cheapest fix is a guaranteed Cure as potion entry 1
on **D2** (the first Spider depth). That is an `ITEM_RNG` change (it rebaselines items_gen
from D2), so it is not taken now.

### 6.5 Hit feedback: damage numbers and target readout (D3-11; user 2026-10-13 numbers; designer decision 2026-10-13 rest)

Enemy health is shown in two ways: **flying numbers** over the body that was hit (what this hit
did), and a **target readout** on the info line (what is left). **No overhead HP bars:** each
moving monster would need its own overlay redrawn on every tween (~1k T per monster per tick),
it would fight the numbers for the 16-px headroom, and flyers at `y = 9s` have no headroom at
all. **No HP-threshold tints:** the attr channel already carries the hit flash, four status
tints and the gold glow (§6.4), and one more meaning in a 2-colour cell is unreadable.

**Numbers (render-only, own list, not FX tracks).**
- **Text (user 2026-10-13: signed):** the HP change, with a sign, for hero and monsters alike:
  `-n` for HP lost (damage after resistances), `+n` for HP gained (the HP actually gained,
  after the max-HP clamp). 1–2 digits, magnitude capped at 99, from the 6-px text font (`+`
  and `-` are already in ASCII 32–127; no new glyphs). `MISS` (24 px = exactly 3 cells) for a
  missed roll or a parry. `0` (no sign) for I/X (immune/reflect). A heal that gains 0 HP
  (caster already at max) shows **nothing**, never `0`: `0` means "immune".
- **Heal sources that emit `+n`:** **Heal potion** (drinker), **Drain Life** (caster, on the
  tick after the target's `-n`), **Vampire drain bite** (the Vampire), and any later
  monster potion (§9.2 idea). **Silent:** FED regen (+1 per 12 turns: a `+1` every 12 turns
  would hold a live slot and drown the real hits during waits and corridor walks; the panel
  HP bar already shows it), level-up and Vigor/Power tomes (max-HP raises, not heals; their
  log line carries them). Rule for any future source: a number only for a heal **caused by an
  action this turn**, never for a timed trickle.
- **Colours (black paper, BRIGHT):** damage to a monster `$47` white · damage to the hero `$42`
  red (any source: melee, spells, own burst/bounce, traps, falls, aura) · **heal (any body)
  `$44` green** · poison tick **`$43` magenta** (hero only, since nothing poisons monsters;
  moved off green so green means only "HP gained"; magenta is already the affliction colour:
  CONFUSED tint, Drain bolt) · `MISS` and `0` `$45` cyan ("nothing happened", both sides).
  Clash: numbers sit in air cells (black paper) like before, so a heal costs no new clash
  case; `$43` and `$44` are already in the legality set (traps, §1.5). The POISON panel icon
  stays `$44` (static, on the panel, not confusable with a flying `+n`).
- **Placement:** cell-aligned horizontally (no shifting), centred on the body's cols, clamped to
  cols 0..32−w. Width w (sign included, 6 px per char): **2 cells** for `-9`/`+9` (12 px,
  2-px side pad), **3 cells** for `-99`/`+99` (18 px, 3-px side pad), 1 cell for `0`, 3 cells
  for `MISS`. The widest case is still 3 cells, so the clamp (cols 0..29 worst case) and the
  24-B compose buffer are unchanged.
  Starts on the row above the body top and **rises 1 px per tick for 8 ticks, then holds 4**:
  **12 ticks (≈ 0.5 s)** in total. Vertical moves cost nothing extra; at most 2 attr rows are
  touched. If the row above is not air (a flyer at `y = 9s`, or row −1), the number starts on
  the body's top row and overdraws it; this is accepted clash, like the hit flash. Numbers draw
  **last**, over bodies and FX. They stay where they were spawned and do not follow the body.
- **One number per body:** a new HP change on a body whose number is still live, **with the same
  sign**, replaces it with the **sum** (a `MISS` or `0` is replaced by the new value) and
  restarts the 12 ticks; colour = the newest contributor's colour (so a poison tick merging into
  a red hit turns it magenta, which is fine). This merges a Lightning bounce or Firebolt burst
  into one figure. An HP change of the **opposite sign replaces** the live number outright (no
  netting): a `-5` then `+5` netted to `0` would read as "immune", and the player wants to see
  the heal happen. Sum magnitude caps at 99.
- **Spawning:** on the tick **after** the damage is resolved (never on the fire/release tick,
  which is the budget peak), with **at most 1 spawn per tick**. Pending spawns wait in a FIFO of
  4, and an entry older than 4 ticks is dropped (the log still carries it). **Whirlwind** on
  several targets therefore spawns as a 1-tick ripple, nearest first. **≤ 3 live numbers**; a
  spawn into a full list ends the oldest live number.
- **Non-blocking:** numbers never hold input and are **not** hero FX for the phase-2 gate
  (§2.2). A room change clears them all.
- **Data (engineer lays out):** 3 entries × {body slot, col, start row, px offset, ticks left,
  attr, width, value} + a pre-composed bitmap of ≤ 3 cells × 8 lines (24 B), composed once at
  spawn from the font. `value` is a signed byte (−99..+99; `MISS` and `0` as flag values).
  About 90 B RAM (unchanged).

**Target readout (info line, row 20, transient).** The info line normally describes the
selected icon (§3.3). After the hero attacks a monster (hit, miss, parry or immune), it switches
to that monster:

```
row 20  chars 0-15 ($47)    chars 16-27 ($42)        chars 28-41 ($45)
        SKELETON GUARD      [########----] 9/14      FROZEN
        ^short name <=12    ^32-px bar, cells 12-15  ^HOLD/MIND word, else blank
                             number from char 22
```

- **Which monster:** the one the hero's action struck. If it struck several (Whirlwind, pierce,
  burst), it is the **surviving struck monster with the lowest HP**, with ties going to the
  first in slot order. If no monster is set yet, a monster that hits the hero sets it.
- **Clears** (back to icon info) when the target dies or leaves the room, on a room change, or
  when the player moves the icon cursor (ICON MODE or `1`–`0`). It comes back on the next attack.
- **Updates** on any HP change of the target and on HOLD/MIND changes (notes word).
- **Panel queue (§3.3):** two items: `TGT_NAME` (name + notes, only when the target changes,
  ~5k T) and `TGT_HP` (bar + number, ~2.5k T). Both drain like any panel item: one per tick,
  never in the input tick. The bar reuses the row-21 32-px bar routine, and the name comes from
  the existing ≤ 12-char short-name table.
- The notes word (`FROZEN` / `ASLEEP` / `STUNNED` / `CONFUSED` / `AFRAID`) can be deferred to a
  later pass at no layout cost (blank field). The engineer decides.

**Cost (estimates; re-gate against `wcast4` 118.3k of ~126k).** Numbers: ~1.0–1.3k T per live
number per tick (erase + draw ≤ 3 cells × 2 rows + attrs), ≤ ~3.9k with 3 live, + ~0.7k for a
spawn's compose (one more glyph for the sign). The worst case is unchanged (3 cells was already
the `MISS` width); the sign makes the typical number 2–3 cells instead of 1–2, about +0.3k T
per live number on average. Heals add spawns, but they go through the same 1-per-tick FIFO, so
the per-tick peak does not grow (Drain Life: target `-n` at f+1, caster `+n` at f+2). Because
spawns come at f+1 or later, the Whirlwind fire tick gets nothing extra. Code ~290–400 B
(bank 7; +~40 B for the sign glyph, signed same-sign merge, heal colour and the heal hooks). Readout: ~150–200 B code, 0 B data. If a gated scenario still
exceeds the budget, **lower the live cap to 2 before anything else**.

### 6.5.1 Cast-time resolution timing (designer decision 2026-10-13)

The engine resolves a projectile's first ≤ 8 strikes on the **accept tick** and the rest on
the release tick (budget split). The rule is **logic early, visible output at impact**:

- **Logic at accept is fine.** HP, the DYING flag, XP/level, status application and the
  hero's self-hit HP may all change on the accept tick. The game already resolves at cast
  time (§6.1, §6.3), and flight time already puts impacts several ticks after the logic.
  The extra 2 ticks (≈ 80 ms) are not visible on their own. Nothing is held back in the
  logic, and the logic stays deterministic for the tests.
- **A struck body still looks alive until its impact tick.** A DYING monster keeps its
  current pose until its stored reaction tick. Only then does the death or reaction
  animation start. It takes no actions in between, because it is dead in the logic.
  **Hero death** (game-over flow) starts no earlier than the impact tick of the self-hit
  that killed him.
- **Damage numbers (Q2): spawn at the impact tick.** A pending number gets a due tick of
  `max(strike reaction tick, resolve tick + 1)`. The FIFO releases at most 1 entry per tick,
  and only once the entry is due. The order on screen is then bolt → flash → number. The
  4-tick age drop counts from the **due** tick, not the resolve tick; otherwise a long
  flight would drop every number. Drain Life's caster `+n` is due at the target's due tick
  + 1. Cost: 1 B per FIFO entry (4 B) and a compare in the drain.
- **Log, target readout and hero HP bar (Q1/Q3): one gate, not per-line timestamps.** On
  accept, the cast sets `COMBAT_NOT_BEFORE` to the cast's **first** impact tick. Until that
  tick, `panel_tick` draws **no log line, no `TGT_NAME`/`TGT_HP`, and no hero HP bar**.
  Lines are still **pushed** at resolve time in their current order, so the ring and
  `LT_HOLD` work unchanged. After the gate the lines drain at the normal 1 per tick and
  trail the bolt naturally. A Lightning kill on its 3rd target may print 1–2 ticks before
  the bolt reaches that target. This is accepted; per-line due ticks are not worth the ring
  rework. Cost: 1 B and 1 compare per tick. If gating the whole panel queue is simpler, the
  engineer may do that instead; non-combat items losing a few ticks is harmless.
- **Bound:** the gate expires after at most 8 ticks past the release tick, even if no impact
  has come yet (for example, a long Lightning flight). This keeps the log from backing up
  into `LOG_WAIT_MAX`. A miss with no body struck sets no gate.

---

## 7. Stats, hunger, food

**Combat and mana:**
- To-hit: `d20 + atk ≥ 10 + eva` (F1).
- Physical damage: `max(1, roll × resist − DEF)`. Spells: `roll × resist`, no DEF.
- Nat-20/1 stays off.
- MP regen as §4 / §4.0 (+1 + `MAXMP` div 16 per class period), period doubled when
  HUNGRY, halted when Weak. Mana potion +8. Amulet of Mana / Scarab halve the regen
  interval.

**Hunger** (`FOOD` 0–100, start 80): burns −1 per **6 turns**, a jump −2 extra. **Never fatal.**

The stage word is shown on the panel (row 21, 6 cells max, in the stage's attr). **Four
distinct stages, each name ≤ 6 chars:**

| Stage (panel word) | FOOD | Effects | Bar + word attr |
|---|---|---|---|
| **FED** | 50–100 | **HP +1 per 12 turns** (user: agreed) | `$44` |
| **OK** (was Peckish) | 25–49 | no HP regen | `$46` |
| **HUNGRY** | 10–24 | atk −1, MP regen halved (= regen **period ×2**, 3E, confirmed 2026-10-20 §8.11) | `$42` |
| **WEAK** | 0–9 | atk −2, eva −1, dmg −1 (min 1; physical hits only, §6.4.2 R1), no MP regen, no jump | `$42`; line on entry (`YOU ARE WEAK WITH HUNGER.`); **faints** after 50 WEAK turns, then every 30 (§7.1) |

The Mummy curse applies the same penalties as the WEAK **status** (§6.4), not cumulative with
this stage. The panel hunger word stays FOOD-derived; the curse shows as a status icon.
Worn cursed gear does **not** affect regen (rev 5, §8.7).

#### 7.1 Fainting from hunger (FAINT1; user 2026-10-26 scope, designer decision 2026-10-26 details)

Hunger never kills; the escalating penalty for staying WEAK is **fainting**: the hero falls
**ASLEEP** (§6.4) for a few turns. Only the hunger **stage** WEAK (FOOD 0–9, `STS_HWEAK`)
counts; the Mummy WEAK **status** never causes a faint.

| Rule | Value |
|---|---|
| Clock | the existing `HW_TMR` (turns in WEAK, mod `HW_REPEAT` 50). Entering WEAK sets it to −1 (unchanged), so **every entry into WEAK restarts the grace**; leaving WEAK (eating to FOOD ≥ 10) stops it |
| First faint | at the first `HW_TMR` rollover, **50 turns after WEAK begins** (FOOD ≈ 1 at the normal burn, ≈ 5 with Plenty/Scarab). The faint **replaces** the repeat line `YOU ARE WEAK WITH HUNGER` on that rollover |
| Faint | hero HOLD := ASLEEP, timer **`FAINT_T` = 5** (between GAS 4 and Sleep scroll 8). Fixed, no roll |
| Grace (cooldown) | after a faint `HW_TMR := HW_REPEAT − FAINT_GAP` = 50 − **30** = 20, so the next faint comes **30 turns after the previous one started** (25 awake turns). Faints cannot chain: at most 1 per 30 turns, ≈ 17 % of starving turns asleep |
| Wake | as any ASLEEP (§6.4, `st_step`): timer, or **any HP loss** wakes him (one hit, a poison tick, an aura). `YOU WAKE UP.` (existing). Eva 0 while asleep, so the first monster swing almost surely lands and wakes him |
| Deferred, not skipped | if at the rollover the hero is **mid-ladder** (`on_ladder`), **already held** (any HOLD kind: GAS this turn, frozen, stunned; also §6.4.1 B2), has **`HOLD_GUARD` set** (a stun/freeze just ended; STUN1 §1.5.1) or an **exit / teleport** this turn (`end_turn` runs `do_exit` first, so the clock stands still on the arrival turn), the faint waits: `HW_TMR` is held at 49 and the check repeats at the next end of turn. (A DART's reaction cannot be pending: the turn only ends once it has played.) A jump, fall or walk in progress is fine: the faint holds his **next** action (§6.4 step order), the current move finishes on screen |
| Bag page / page verbs | no special case: hunger ticks only in `end_turn`, which runs after a page verb is applied on return to play; the page cannot open while held (input ignored, §2.2). Eating on the page that turn lifts FOOD out of WEAK before the check (`hg_stage` runs first) → no faint |
| Feedback | log `YOU FAINT FROM HUNGER` (21, FONT6, new); the GAS one-step hero flash (`E_FLT` = `TRAP_FLASH_T`, attr `$44`, existing) then the ASLEEP tint `$41` and the ASLEEP panel icon (existing); SFX = the GAS trap's SFX (reuse). The food bar/word is unchanged (still WEAK `$42`) |
| Danger music | none extra: HOLD already adds +2 to the horizon (§3.7) |

**Numbers (normal burn, −1 FOOD / 6 turns):** WEAK warning line at FOOD 9 → first faint 50
turns later → faints at +80, +110, +140 … while unfed. Any food ends it (Carrot: FOOD 0 → 10 =
HUNGRY; it falls back into WEAK after 6 turns, which restarts the 50-turn grace: a Carrot buys
≈ 56 faint-free turns). **Expected cost:** a level holds 3–4 floor food items plus drops
(≈ one find per 110–150 exploring turns, §8.11 (2)), so a hero who turns WEAK with an empty bag
typically finds food within 60–75 WEAK turns: **0–1 faints**; a bad case (no food left on the
level, 150 WEAK turns to the next level's first item) is **4 faints**. Per faint: 5 lost turns
out of combat; in combat ≈ one sure hit per adjacent monster (the first wakes him) plus the
approach/shots of ranged monsters. A real penalty, never a lock: he always wakes on the first
damage, and 25 awake turns separate faints.

**BAL1 knobs (playtest):** `FAINT_T` 5 (4–6), `FAINT_GAP` 30 (25–40), first faint = `HW_REPEAT`
50. If starvation feels toothless, drop `FAINT_GAP` first; if it feels like a death spiral, raise
it before touching `FAINT_T`.

**Implementation (staff; R6 `hunger6.asm`, target ≤ 60 B code + 22 B string).** No new state:
`HW_TMR` is the counter. In `hunger_turn` step 4, the WEAK rollover branch becomes: defer checks
(HOLD bits of `ST_FLAGS`, `E_REACTAT`, `EXIT_KIND`; `on_ladder` on the hero — if `logic.asm` is
not callable from R6, `end_turn` (bank 7) evaluates it before `far6` and passes a flag) → on
defer `HW_TMR := HW_REPEAT − 1`, ret; else factor `trap6.asm`'s `.gas` HOLD write + flash into a
shared R6 `hero_sleep` (B = turns; GAS keeps its own two lines), call it with `FAINT_T`, the SFX,
`HW_TMR := HW_REPEAT − FAINT_GAP`, then `hg_line` with the new `S3_HG_FAINT`. Estimate: defer
checks ~22 B, sleep call + gap write ~10 B, SFX + line ~8 B, `hero_sleep` factoring +4 B net
≈ **44 B code + 22 B string**; ~0.1k T on the rollover turn only. Tests (`SEED_FIXED` not needed,
no roll): poke FOOD 5 / WEAK / `HW_TMR` 49 → after one Wait: ASLEEP 5, the line, `HW_TMR` 20;
same on a ladder → not asleep, `HW_TMR` 49; then step off → faints; a monster hit → wakes;
eat to FOOD ≥ 10 then back to 9 → `HW_TMR` restarts at 0.

| Food | FOOD | Source |
|---|---|---|
| Meat | +40 | floor (D2+), Orc drop 1/3 |
| Cheese | +30 | floor, Rat drop 1/4 |
| Pear | +20 | floor |
| Apple | +15 | floor, Goblin drop 1/4 |
| Carrot | +10 | floor |

Per level (E): ~450 turns ≈ 75 FOOD burned. Supply: 3–4 floor items + drops ≈ 100.

#### 7.2 Poisoned: cannot eat (POIS1; user 2026-10-26 ruling, designer decision 2026-10-26 details)

While POISON is set (`STS_POISON`), the hero **cannot eat** until it ends (timer or Cure).

| Rule | Value |
|---|---|
| Paths | **every EAT**: the bag-page EAT verb, the icon-bar FOOD quick slot (§3.5), and any `bag_pick` FOOD mode. Potions, scrolls, equip, discard and all other verbs are unaffected |
| Refusal | log `TOO SICK TO EAT` (15, new). It costs **0 turns**, consumes nothing and keeps the food in the bag. On the page the refusal is shown where `NO NEED` is (row 22) and the page stays open. Order: the POISON check runs **before** `NO NEED` (FOOD 100), so a poisoned hero at FOOD 100 sees `TOO SICK TO EAT`. The FOOD quick slot does not fall through to another class |
| Ends | `THE POISON WEARS OFF` (timer, ≤ 30 turns after the last application, §6.4.3), or a Cure potion (`YOU ARE CURED`). He can eat on the next action. The quick POTION pick already reaches Cure when Heal and Mana would be refused (§8.11 (3)) |
| Hunger keeps running | FOOD burns as usual (−1 / 6 turns), the stages apply as usual, and FED regen still runs. One capped poison window costs **≤ 5 FOOD** |
| FAINT1 (§7.1) | unchanged and independent. A faint can land inside a poison window. A poison tick that costs HP wakes him (any HP loss). At 1 HP a tick costs nothing, so he sleeps the full 5 |
| No spiral (proof) | (1) Poison is timed and capped at 30, so the lock lasts at most 30 turns after the last bite. (2) A 30-turn lock costs ≤ 5 FOOD and, with `FAINT_GAP` 30, **at most 1 faint**. (3) Neither poison nor hunger can kill: poison stops at 1 HP and hunger is never fatal. Only monsters kill, as always. (4) The lock only extends while he keeps being poisoned, i.e. while he fights poisoners or re-walks a known DART. Both are things he can stop doing |
| Feedback | the POISON panel icon (`$44`) is already on screen and explains the refusal. There is no extra icon |
| Bytes | the check `ld a,(ST_FLAGS) : bit STS_POISON_BIT,a : jr nz,.sick` sits before `NO NEED`'s FOOD-100 test, in the shared EAT legality path if there is one (~8 B). If the page and the quick slot test separately, ~16 B. The string is 15 + 1 B (with the other EAT refusals, `NO NEED`'s bank/overlay). **≈ 25–32 B** |
| Tests | Poisoned + FOOD 50: page EAT → line, turn counter unchanged, bag unchanged, FOOD unchanged. The FOOD quick slot gives the same. FOOD 100 + poisoned → `TOO SICK TO EAT` (not `NO NEED`). The quick POTION slot still drinks. Cure, then EAT → eats. Timer runs out → eats |

---

## 8. Items and inventory

- **Bag: 20 slots** (5×4 page grid), same-type stacks to 9.
- Ammo (`DAGGERS`, `ARROWS`) and the **level key** are counters outside the bag.
- Pickup is automatic. A full bag prints `BAG FULL.`
- Everything the hero uses is **found**: books, scrolls, ammunition, gear. Nothing is
  sold or regenerated.

**Worn slots: 4** (user: agreed): weapon · armour · helmet · **charm** (ring *or* amulet).

| Item | Slot | Effect | Found |
|---|---|---|---|
| Short Sword / Long Sword / War Axe | weapon (W) | 1d6 / 1d8 atk+1 / 1d10 atk−1 | start / D2+ / D4+ |
| Oak / Iron / Rune Staff | weapon (M) | 1d4 / 1d6 / 1d4 + spells +1 dmg | start / D2+ / D4+ |
| Robe / Leather / Chain Mail / Plate | armour | MP+2 / DEF 1 / DEF 2 / DEF 3, MP regen ×½ | M start / W start / D3+ / D6+ |
| Hood / Helm | helmet | MP+1 / DEF+1 | D1+ |
| Ring of Might / Warding / Fire Ward | charm | atk+1 / DEF+1 / FIRE R | D2+ |
| Amulet of Mana / Plenty | charm | MP regen ×2 / FOOD burn ×½ | D3+ |

Weapons are class-locked; everything else is not.

**Consumables:**
- Potions: **Heal** +10 HP · **Mana** +8 MP · **Cure** (clears POISON, WEAK, CONFUSED and
  FEAR, §6.4; +4 HP). No harmful or throwable potions (designer decision 2026-10-03: a throw
  verb needs an aim mode and item projectile art; a known-bad potion is junk).
- Scrolls (read on the page): **Teleport** (random free spot in a random room, never the lair
  while its boss lives) · **Fear** (the room's monsters flee 6 turns) · **Sleep** (new, 3D/3E:
  the room's monsters fall ASLEEP 8 turns, §6.4) · **Enchant** (if any worn item is cursed:
  **blesses every worn cursed item** instead (§8.7, `THE CURSE LIFTS. BLESSED!`); else
  weapon dmg +1, max +3).
  **[rev 6, 2026-10-20: Enchant = worn weapon `m` +1, max +3; no blessing; §8.11 "3E simplification". GEAR3, 2026-11-01: Enchant = a random worn weapon / armour / helmet (else a bag one) `m` +1, max +3: `docs/design/gear_rules.md` §3.]**
  Floor scrolls pick the type uniformly from the four.
- The **key** opens the lair door and is consumed.

**Quick slots auto-fill** (user):
- FOOD: the smallest FOOD value first.
- POTION: Heal, else Mana, else Cure.
- ~~`QUICK` on the page pins a type until its stack runs out.~~ **Cut 2026-10-20 (§8.11
  Q3):** no pin; auto-fill only.
- SCROLL: the largest stack, ties Teleport → Fear → Sleep → Enchant (§3.5). Quick scroll = read.
- ~~Unknown types never auto-fill~~ **[rev 6: no unknown types exist; every potion/scroll
  type is always known and eligible.]**

**Page engine rules (3E-T2 spike, manager review 2026-10-20; rev 2026-10-20 user: full
screen, sound keeps playing; layout §8.11 Q3).** The page opens only on the turn-intent path
(`I` or FIRE / ENTER on BAG; never while the hero is held; no turn). It covers **all 24
rows** (the panel and log are hidden while it is up), so it has its own message row for
refusals (row 22, §8.11). Verbs are chosen on the page but take effect after it closes, as
the turn's action (the screen is restored exactly as it was when the page opened). **The page
is not a pause: music and SFX keep playing** (no `SND_HOLD`). Engineering detail:
`docs/memory-map.md` "Overlays" → T13 page rules.

### 8.5 Per-level placement (floor list ≤ 32 entries)

Food 3–4 · potions 2–3 (≥ 1 Heal) · **scrolls 1–2** (rev 2: 1; E: 1–2 keeps the quick
slot alive) · gear 1–2 (depth-gated) · class book 1 (D1–D7) + 1 more with 1 in 2 on D4–D7
(rev 5, §5) · ~~other-class book 0–1~~ (cut, user 2026-10-20) ·
key 1 (no floor entry: found on entering the key room, §8.11 Q1) · all 3E entries on
`ITEM_RNG` (§8.11 Q8) · **ammunition (rev 3; Warrior runs only: a Mage run generates no ammo entries):**

| Item | Per level | Notes |
|---|---|---|
| **Dagger stack** | **1 stack of 2–3** (`1d2+1`) on D1–D7; none on D8 | placed in a random non-start, non-lair room |
| **Arrow stack** | **1 stack of 5–8** (`1d4+4`) on D1–D7; D8 none | same |
| **Bow (user 2026-10-04; Warrior runs only)** | **Exactly 1 on D2**: a floor-list entry in a random non-start, non-lair room, **plus a 6-arrow bundle placed in the same cell** (extra to D2's normal 5–8 stack; the two merge on pickup per the one-stack-per-cell rule, capped 24). Generated regardless of RNG; never on other depths. If the bow is discarded (§8.11: DISCARD destroys) or lost (pit fall) it is gone, and the run continues melee/daggers only | Pre-bow arrows (D1 stack) are picked up and kept; the bow icon stays greyed until the bow is in the bag |
| Skeleton Archer drop | Arrows ×3, 1/2 | D4, D5 (§9.1; D7 dropped by H1, §9.8) |
| Thrown-and-recovered | per §6.3 | not a placement; uses floor-list slots |

Supply estimate (E, whole run): daggers ≈ 3 + 7 × 2.5 ≈ 20 found + recoveries (×4 throws
each ≈ 80 throws if all are used); arrows ≈ 6 (D2 bundle) + 7 × 6.5 ≈ 52 found (start 0; D1 is dagger-only play, which the D1 balance row already assumes) + ~6 from Archers (D4/D5 only since H1; was ~9).
With ~14 monsters per level and ~65 % to-hit, a level's ~6 arrows kill about one monster, so
ranged play is a **tool for the dangerous kinds** (archers, casters, the Ogre's approach),
not a replacement for the sword. The stack caps (9 / 24) make hoarding a loss.

### 8.6 Bosses and unique gear (every level; never follow; death opens the grate)

| Depth | Boss | Kind | Unique drop |
|---|---|---|---|
| D1 | Golden Goblin King | golden Goblin | **Goblin King's Helm**: helmet DEF 1, eva +1 |
| D2 | Golden Spider Queen | golden Spider | **Silk Cloak**: armour DEF 1, eva +2, poison-immune |
| D3 | Golden Vampire Lord | golden Vampire | **Gravecloak**: armour DEF 2, DRAIN R, DARK R |
| D4 | **Ogre Warlord** | **unique** | **Warlord's Cleaver** (W: 1d10+1, atk+1) / **Bone Staff** (M: 1d6, spells +2) |
| D5 | Golden Pharaoh | golden Mummy | **Scarab Amulet**: charm, MP regen ×2, FOOD burn ×½ |
| D6 | Golden High Necromancer | golden Necromancer | **Ring of the Grave**: charm, DARK I, MP+2 |
| D7 | **Death Knight** | **unique** | **Mirror Helm**: helmet DEF 2, **DARK X** (reflects Dark/Death Bolts) |
| D8 | **Necromancer Archmage** | unique | none; its death unseals the Sanctum |

**Golden bosses** are their base kind's row plus a per-entity **golden flag** (implies `BOSS`);
no kind row of their own (3F-D1, §9.7 R1).
- **Stats:** hp = 2×hp + 6, atk +2, dmg +1, DEF +1, resistances of the kind.
- **0 new frames, 0 pool.**
- **Gold glow:** the stamp attr cycles **`$06 → $46 → $47 → $46`**, 2 ticks per step
  (period 8 ticks ≈ 0.32 s).
  - On ticks when the boss is redrawn anyway, the stamp simply uses the current gold attr,
    at **0 extra cost**.
  - When it is stationary, only its **footprint attrs** are rewritten at ~0.12k T/cell
    (**M**, incl. the attr-only present copy): **~2.2k T per step** for a 3×6 boss, ≤ 2.9k
    for a 4×6 one. That is ≤ 1.5k T/tick on average.
  - Pattern: **SYNC only** (all footprint cells step together; user decision, rev 3). No
    diagonal sweep.
  - The hit flash overrides it. `$06`/`$46`/`$47` join the legality set.
  - Weight +1 (§9.3).

**Lair population (user 2026-10-06 lazy population; designer decision 2026-10-06, §9.4.4).**
The boss and its 1 escort are created on the **first lair entry**, not at level start. When
the hero leaves the lair, the boss is banked in the lair record with its **exact hp**. It does
not regenerate and is never rerolled. A summon standing next to the hero follows him like any follower (user 2026-11-01); summons that do not follow are discarded when the room is left.

Uniques on the floor shimmer with the same cycle (it counts toward the room's attr-cycle
cells). Panel and page use hardware FLASH.

### 8.7 Blessed and cursed gear (3E; user 2026-10-03: known states, no identification; rev 5 user 2026-10-03: hidden ± value, bless/shatter)

> **CUT, rev 6 (user 2026-10-20, memory): blessed/cursed, the hidden value, bless and
> shatter do not exist. Superseded by §8.11 "3E simplification (2026-10-20)". The text below
> is history; do not implement.**

Every **found gear item** (weapon, armour, helmet, charm) has a visible state: **BLESSED,
normal or CURSED**. Start kit and boss uniques are always normal. Every state carries a
**modifier `m`** applied to the item's **main stat**: weapon dmg +m · armour/helmet DEF +m
(Robe/Hood: max MP +m) · charm max HP +2m. Hero totals clamp at 0 (DEF, max MP); damage keeps
`max(1, …)` (§7).

| State | `m` | Value shown | Unequip |
|---|---|---|---|
| **BLESSED** | +1 | always | free |
| normal | 0 | — | free |
| **CURSED** (user) | −2, −1, +1 or +2 (roll below) | **CURSED is visible; the value is hidden until the item is first equipped** (user + designer decision 2026-10-03: a state is known, a number is learned by wearing it — no identification verb) | **impossible** (`IT IS CURSED! YOU CANNOT.` 25) until the item is **blessed** or **shattered** |

**Cursed value roll (designer decision 2026-10-03; out of 8, `ITEM_RNG` at item placement, §8.11):**

| Depth | −2 | −1 | +1 | +2 | mean |
|---|---|---|---|---|---|
| D1–D3 | 0 | 5 | 3 | 0 | −0.25 |
| D4–D6 | 2 | 3 | 2 | 1 | −0.4 |
| D7–D8 | 3 | 2 | 2 | 1 | −0.5 |

Equip reveals it: `IT CLINGS TO YOU! CURSED -1.` (27) / `… CURSED +2.` The value stays shown
on that item from then on (page `CURSED -1 HELM`, info line note `STICKY`). Unworn: `CURSED ?`.

**Blessing (designer decision 2026-10-03: reuse Enchant, 0 new item types).** Reading
**Enchant** (known or unknown) while any worn item is cursed blesses **every worn cursed
item**: state → BLESSED, `m = max(m, +1)` (a cursed +2 keeps its +2), value shown;
`THE CURSE LIFTS. BLESSED!` (25). The weapon enchant is not applied that read. Unworn
cursed items in the bag are not affected (bless what you wear).

**Shattering (user: "destroyed, e.g. when an enemy shoots you"; details designer decision
2026-10-03; self-contained, no durability).**
- **Trigger:** a **projectile hit on the hero that deals ≥ 1 damage**: monster arrows/rocks
  (Archer, Sniper, Slinger), Dark/Death Bolts, the **DART trap** (§1.5), and the hero's own
  bounced or reflected spells. Not melee, bursts (Firebolt splash), falls, poison or aura.
- **Roll:** if ≥ 1 worn item is cursed, **1 in 4** (`SHATTER_CHANCE` 64/256, gameplay RNG)
  one of them shatters; the slot is chosen **uniformly among the worn cursed slots** (the
  projectile "finds the flaw"). Blessed and normal gear never shatter.
- **Result:** the item is destroyed (not dropped); the slot becomes **empty** (dotted outline
  in the panel gear cell, queued). Hero stats recompute as on unequip; HP/MP clamp to the new
  max. An empty **weapon** slot = **fists 1d2 PHYS** for either class (same frames; Power
  Strike doubles it). The hero may equip a replacement from the bag at once.
- **Message:** `YOUR CURSED ARMOUR SHATTERS!` (28), slot words WEAPON / ARMOUR / HELM /
  CHARM (4 fixed strings, no item-name table).
- A known re-arming DART trap is therefore a deliberate (costly: ~3.5 HP + POISON 12 per hit (POIS1: the poison ≈ 3 HP over 12 turns, and no eating while it runs),
  ~4 hits expected) way to break a curse on D1–D3, where no monster shoots except the Goblin
  Slinger tier. Intended.

**Why the regen penalty is removed (designer decision 2026-10-03):** the downside is now the
gamble itself (mean `m` < 0) plus the lock (a cursed item blocks a better find or a boss
unique in its slot). A regen penalty on top would make a cursed +1/+2 strictly bad and kill
the gamble the user asked for.

**Odds per found gear item (seeded, out of 16):**

| Depth | D1–D3 | D4–D6 | D7–D8 |
|---|---|---|---|
| BLESSED | 2 | 3 | 4 |
| CURSED | 2 | 3 | 4 |

≈ 12 gear items per run → ~3 blessed, ~3 cursed.

**Display.** The item's 16×16 icon (page, worn-gear panel cells) and its 8×8 floor glyph take
the state colour on all their cells: **BLESSED `$45`**, **CURSED `$42`**, normal = the item's own
attr (cell-uniform, no clash; uniques keep FLASH). Page description row prefixes `BLESSED +1 ` /
`CURSED ? ` (unrevealed) / `CURSED -1 ` (revealed); the info line note field shows `STICKY`
for a worn cursed item. Pickup line: `YOU PICK UP A CURSED HELM.`

**Cost (rev 5, E):** value roll ~40 B (bank 5, generator), shatter roll + slot pick + clear
~90 B and bless ~30 B (bank 3, `far3`), reveal-on-equip ~20 B; stat recompute is the existing
unequip path. Strings ~90 B raw (4 slot words, reveal, bless, shatter). The rev-4 regen check
is deleted (−~10 B hot). Per projectile hit on the hero: one test of the worn-cursed mask
(~30 T) on the fast path.

### 8.8 Light identification (3E; user 2026-10-03)

> **CUT, rev 6 (user 2026-10-20, memory): no appearances, shuffle, `KNOWN`, elimination or
> `IT WAS` lines. Superseded by §8.11 "3E simplification (2026-10-20)". History only.**

**Potions and scrolls have per-run shuffled appearances**; a **type** becomes known on its
**first use** (drink/read; free, automatic). Gear is never unidentified (§8.7). Food, books,
ammo, the key: always known.

| Class | Types | Appearance pool (name ≤ 7 chars, floor/icon ink) |
|---|---|---|
| Potion | Heal, Mana, Cure | RUBY `$02` · AZURE `$05` · EMERALD `$04` · AMBER `$06` · VIOLET `$03` · MILKY `$07` (6) |
| Scroll | Teleport, Fear, Sleep, Enchant | labels ZORAK · VELMIS · OSTRUN · KAPPU · MIRADEL · THUNE · YOLQ · ABRAXA (8); scroll ink always `$07` |

- **Per-run table:** at START, a shuffle seeded from `f(master seed, 255)` (a "depth 255"
  derivation, so no level seed and no generator output changes) maps each type to a distinct
  appearance. State: potion map 3 B + scroll map 4 B + **`KNOWN` 1 B** (bits 0–2 potions,
  3–6 scrolls) = **8 B** in the state block, kept across levels.
- **Known at start:** the hero's start-kit types (both: Heal; Mage: Mana). **Elimination:**
  when all but one type of a class are known, the last becomes known automatically.
- **Naming:** unknown → `RUBY POTION`, `SCROLL VELMIS`; known → `POTION OF HEAL`, `SCROLL OF
  FEAR` (page/info line); appearance ink is kept after identification. Log: `YOU PICK UP A
  RUBY POTION.` · `YOU DRINK THE RUBY POTION.` → `IT WAS A POTION OF HEAL.` · `YOU READ
  VELMIS.` → `IT WAS A SCROLL OF TELEPORT.` (28). All ≤ 32.
- **Using unknowns:** effects are identical to known use; the risk is timing only.
  Unknown potions are **never refused** (the HP = max / FOOD rules apply only to known types;
  a wasted Heal still identifies). An unknown **Teleport** teleports, **Fear**/**Sleep** hit
  the room's monsters (an empty room: no effect, still identified), **Enchant** blesses
  worn cursed gear or enchants as §8. Read unknown in the lair: Teleport still never lands in the lair.
- **Quick slots:** §8 "Quick slots auto-fill" (unknowns never auto-fill; pinnable).
- **Budget (bank 3):** appearance strings ~90 B, ID messages ~60 B, shuffle + naming code
  ~150 B; 8 B state; 0 tile ids (potions/scrolls are item glyphs recoloured).

### 8.9 Item record (designer decision 2026-10-03; layout by the engineer)

Floor-list entries, bag slots and worn slots all carry the same item fields:
`TYPE` (item type id) · `QTY` (stack 1–9; ammo counts live outside the bag) · `ISTATE`.
**[rev 6: `ISTATE` = bits 5–7 `m` only, §8.11 "3E simplification"; floor entries carry no
`ISTATE`. The rest of this paragraph is history.]** Former layout: bits 0–1 BUC (0 normal, 1 blessed, 2 cursed, 3 reserved) · bit 2 **HIDDEN** (rev 5: the
cursed value is not yet revealed; set at generation for cursed items, cleared on first
equip or on blessing; **display-only**, logic ignores it, as rev 4 reserved it) · bits 3–4
weapon enchant +0..3 · **bits 5–7 `m`, the signed BUC/wear modifier** (3-bit two's
complement −4..+3; used −3..+2; §8.7, §8.10). Stacks merge only on equal `TYPE` and
`ISTATE`. Potion/scroll knowledge is **per type** (the `KNOWN` byte, §8.8). Gear's effective
main stat = base + `m` (+ enchant for weapons), computed once on equip/unequip/change.

### 8.10 Gear wear from special attacks (3F; user 2026-10-03: wear only from special attacks; details designer decision 2026-10-03)

No durability counter: wear lowers the item's existing modifier `m` (§8.9). Ordinary hits,
time and use never wear gear.

| Source | Target slot | Trigger | Chance |
|---|---|---|---|
| **NOTCH** — Skeleton Guard, Skeleton Knight (§9.6), **Death Knight** (§9.1) | worn **weapon** | the monster **parries the hero's melee hit** (incl. Power Strike, Whirlwind; not thrown/shot ammo, not fists) | 1 in 2 per parry |
| **ACID** — **Black Widow** (§9.6; replaces its rev-4 sleep bite) | worn **armour**, else helmet, else nothing | its bite hits the hero (≥ 1 dmg) | 1 in 4 per hit |

**[rev 6, 2026-10-20: blessed/cursed are gone: "blessed immune", "cursed wears like normal" and
the shatter cross-references below are void; every wear event applies to the target; the
destroy-at-−3 path stays and is the only slot-clearing code.]**

**Effect.** `m −= 1` on the target item; stats recompute as on unequip. **Floor `m = −3`**: a
wear event on an item already at −3 **destroys** it; the slot empties exactly as a curse
shatter (§8.7: dotted outline, recompute, fists for an empty weapon slot).
- **Blessed items are immune** (no change, short message). Blessing is the only protection.
- **Normal items** go negative and stay normal (page `CHAIN MAIL -1`; still free to unequip).
- **Cursed items** wear like normal ones (a cursed +2 notches to +1, …) and **destruction at
  the floor frees the slot**, the second way out of a curse besides a projectile shatter.
  A hidden value cannot occur (a worn item is revealed).
- Boss uniques wear like normal items (the Mirror Helm is a helmet: hit only with no armour).

**Messages (≤ 32):** `YOUR WEAPON IS NOTCHED!` (23) · `ACID EATS YOUR ARMOUR!` (22; HELM
variant) · `YOUR BLESSED WEAPON HOLDS.` (26; ARMOUR/HELM variants) · `YOUR WEAPON BREAKS!`
(19) · `YOUR ARMOUR FALLS APART!` (24; HELM variant).

**Frequency (E).** ACID: a Black Widow lands ~2 bites per fight → ~0.5 wear per Widow, ~1
Widow per D2/D4/D5 level. NOTCH: ~1–2 parries per Guard/Knight fight → ~0.75 notch; Death
Knight ~3 parries → ~1.5 notches. Expect a Warrior to lose ~2–4 points of weapon/armour per
run unless blessed: noticeable, never run-ending. Mage: staff notches equally (he melees
less).

**Cost.** Code ~70 B bank 3 (shares the shatter clear path); the hooks are the existing parry
branch and the generic on-hit effect (new effect code `ACID`, no new column). Strings ~110 B
raw. Per event ~0.3k T; 0 on the fast path.

### 8.11 3E rulings (2026-10-20; designer, user-delegated "decide using memory constraints")

Context: user rulings 2026-10-19/20 (no gold; page icons = scaled 8×8 floor glyphs [reopened
2026-10-26: true 16×16, Q5]; ~0.4 s
page close OK; drops + boss uniques in 3E; other-class books cut; light-ID kept; page full
screen, sound not paused). 3E has ≈ 2.4 KB free vs ≈ 4.4 KB need, so every ruling picks the
smallest consistent rule.

**FLOOR1 — floor items are their 16×16 icons (user-approved 2026-10-26; supersedes Q1's class
glyphs and Q5's "floor reuse: NO").** Every floor item is drawn as its type's page icon (Q5) on
a **2×2-cell footprint**, in its type's ink (`it_tab`), so each type is recognisable on the floor.

- **Footprint:** cols **c..c+1** (`FL_COL` = c), rows **9s+6..9s+7** (the standing row and the
  row above it). **c ∈ 2..28** (c+1 ≤ 29: never a door col 0–1 / 30–31); both cols legal
  (no ladder / shaft / hole footprint f..f+2, no pit p−1..p+3, no edge block or its rubble, no
  L2 span +1).
- **Spacing:** no other item within **c−1..c+1** (footprints may touch, never overlap);
  **exact-col stacks** are allowed (the bow + its bundle, ammo, drops onto a pile). A stack
  shows its last live entry in list order.
- **Traps:** t ≠ c, c+1 (§1.5).
- **Generation (Q8):** ≤ **6 entries per room** (both storeys; the bow's bundle may make a
  7th; designer target was ≈ 4, but 4 loses an item on ~13 % of levels, 6 on 0.9 %), placement
  tries per item **16** (was 8; the 2-col footprint needs them). The GEN_RNG potions are
  re-checked against these rules on ITEM_RNG and an illegal one re-placed (non-start pool,
  scan fallback). **The D8 lair exclusion is gone** (no 60..63 class glyph exists any more).
- **Pickup:** the body takes an item when it covers **c or c+1**; BAG FULL on arrival as before
  (an arrival = the footprint was not under the previous body span).
- **Drops** (rulings 2): (1) an existing item whose col is within d−1..d+1 of the body's centre
  col d (an exact-col stack); (2) else the nearest free footprint c in d−3..d+3 (left first; a
  unique: the whole storey): its 4 cells empty air, floor (TF_FLOOR) under both cols, no unspent
  trap on c / c+1.
- **INVARIANT (manager 2026-10-28): a room never holds more than 8 distinct item types**
  (both storeys, tops and piles; the glyph cache has 8 slots, so every item always has its icon).
  An ordinary drop of a type that would be the room's 9th is **refused** (monster loot is simply
  not dropped; a thrown / hero-dropped item of a type the room already holds is never a 9th). A
  **boss unique** with the room at 8 types **destroys** the lowest-value ordinary item first: the
  first food / ammo / potion in list order, and every entry of its type (its pile shows the next
  item), so the unique always fits. (The generator places ≤ 7 entries, so an 8th type is always
  a monster drop = food / ammo / mana: a victim always exists.)
- **Potions share one shape** (user 2026-10-27): Heal, Mana and Cure all use the Heal flask
  icon, told apart by their inks (Heal `$42` red, Mana `$45` cyan, Cure `$44` green) — on the
  floor, the page and the quick slot. The Mana / Cure grids stay in the assets, unused.
- Thrown-and-recovered ammo (§6.3) is not built yet; when it is, it lands by the drop rules.

**Q1 Floor-item glyphs: 6 class glyphs, per-type ink, 0 new common ids.** *(Superseded by FLOOR1
above: the class glyph ids 17 / 18 / 60..63 are no longer placed; 60..63 are now the item
markers; kept for the history.)* All 64 ids are
taken except per-level slots **60..63 on D1–D7** (the D8 lectern holds them on D8). Common
ids 17/18 are re-purposed. Class is read from the **glyph**, the type from the **ink**
(per-cell attr set when the item is stamped, the same mechanism as known traps §1.5; ink
comes from the item-type table; gear BUC tint `$45`/`$42` and unique shimmer override it).

| Id | Glyph | Items | Ink (normal) |
|---|---|---|---|
| 17 | **AMMO** (merged: was `T_DAGGERS`) | daggers, arrows | daggers `$47`, arrows `$46` |
| 18 | **PAGES** (was `T_ARROWS`) | scrolls, class books | scroll `$07`, book `$43` |
| 60 | **FLASK** (the old `T_POTION` glyph moved, no new art) | potions | appearance ink (§8.8) |
| 61 | **FOOD** | meat, cheese, pear, apple, carrot | `$42` `$46` `$04` `$44` `$06` |
| 62 | **WEAPON** | swords, axe, staves, bow, unique weapons | blades `$07`, staves/bow `$06` |
| 63 | **WORN** (shield shape) | armour, helmets, charms, unique wearables | armour/helm `$07`, charms `$06` |

- **Storage:** the four 60..63 glyphs (+ attr, flags 0) are written into the **D1–D7 tileset
  slots' 60..63 bytes** (already reserved as zeros: 0 B new). **D8:** the room build loads
  60..63 from the D8 slot (lectern) when the room is the **Sanctum**, else from the D7
  slot (items). So that the lair↔Sanctum scroll never shows a mis-glyphed item, **on D8 no
  60..63 item lies in the lair or Sanctum**: the generator skips them and any drop there
  whose glyph is 60..63 is lost (AMMO/PAGES are common and allowed).
- **Key: no floor glyph and no floor entry.** The key is found automatically on the **first
  entry into the key room** (`LF_KEY_TAKEN`, panel key icon; `YOU FIND THE LAIR KEY.` 22).
- Id 10 = `T_TRAP` as §1.5. ~~Page icons = these 6 glyphs scaled ×2 (16×16) in the item
  ink.~~ **Superseded 2026-10-26 by Q5 below (true 16×16 icons); the floor keeps these 6 glyphs.**
- **Art the artist must deliver (8×8, standing-row items, low in the cell): FOOD, PAGES
  (open book / scroll, reads in white and magenta), WEAPON (sword), WORN (shield), AMMO
  (one bundle that reads as daggers or arrows; until delivered the id-17 dagger pile is
  used for both), plus the `T_TRAP` plate if not yet drawn.** FLASK reuses the potion glyph.

**Q5 Item icons: true 16×16 (REOPENED; user rulings 2026-10-26, details designer; plan IC1).**
Supersedes the 2026-10-19 "scaled 8×8 floor glyphs" ruling for the page and panel.

- **Format.** 16×16, **1-bit, no mask**, 32 B raw per icon: rows 0..15 top-down, each row
  left byte then right byte, bit 7 = leftmost pixel. Set bit = ink, clear = paper. Drawn as a
  **copy** (not OR) into its 2×2 cells, which are always byte-aligned (no shift).
- **Colour.** **One ink per icon** = the item type's ink from `it_tab` (the same ink as its
  floor glyph, incl. BRIGHT); paper = the screen's paper (black; page cursor = paper blue,
  §8.11 Q3). No item ink may be blue (1): it would vanish under the cursor (none is today).
  No unique shimmer off the floor. Per-cell colour inside an icon is a later fallback only,
  not in IC1.
- **Index = `type − IT_BAG_LO`** (no lookup table; address `ICON_BASE + idx × 32`):

| Idx | Types (`IT_*`, item_defs.asm) | n |
|---|---|---|
| 0–4 | F_CARROT, F_APPLE, F_PEAR, F_CHEESE, F_MEAT | 5 |
| 5–7 | P_HEAL, P_MANA, P_CURE | 3 |
| 8–11 | S_TELEPORT, S_FEAR, S_SLEEP, S_ENCHANT | 4 |
| 12–13 | BOOK (one icon for both tomes), BOW | 2 |
| 14–21 | W_SHORT, W_LONG, W_AXE, W_CLEAVER · W_OAK, W_IRON, W_RUNE, W_BONE | 8 |
| 22–27 | A_ROBE, A_LEATHER, A_CHAIN, A_PLATE, A_SILK, A_GRAVE | 6 |
| 28–31 | H_HOOD, H_HELM, H_KING, H_MIRROR | 4 |
| 32–38 | C_MIGHT, C_WARD, C_FIRE, C_MANA, C_PLENTY, C_SCARAB, C_GRAVE | 7 |
| 39–42 | **slot placeholders** (empty worn slot): WEAPON, ARMOUR, HELMET, CHARM — index `39 + worn slot` | 4 |

  **43 icons = 1,376 B raw.** No boots/hat (not in the model). **No bow placeholder:** the bow
  has no worn slot (§6.3: a bag item, never worn); the icon-bar Bow slot keeps its 24×16
  ability art. **Key and ammo get no 16×16 icon:** they are counters, not bag/worn items, and
  have no 16×16 draw site (page row 1 is one text row; the panel key and row-21 ammo have
  their own art). See question 1 below for adding them (+96 B).
- **Placeholder ink `$05`** (dim cyan; distinct from every item ink in practice, and visible on
  the blue cursor paper). Art: a **dotted outline** of the slot's class silhouette (sword,
  body armour, helm, ring) — the same "empty" language as §8.7/§8.10's cleared slot.
- **Storage.** Raw (the page overlay has no room to unpack ZX0), one copy, readable by both the
  page draw and the panel draw. Region is the architect's call: **R6** (2,739 B free after T8,
  before T12/T16/3F) or **bank 3** (619 B + DEC2's ~90–120 B ≈ 0.7 KB: does not fit 1,376 B
  unless the architect frees ~0.7 KB more there or splits the set). The T14 `pg_icon`
  bit-doubling code is deleted.
- **Draw sites** (all into the bank-5 screen, attr = paper | `it_tab` ink):

| Site | Where | Content |
|---|---|---|
| Bag grid | page rows 2–13, 2×2 at col `3 + 6c`, rows `2 + 3r` (Q3 table) | item icon; count digit unchanged |
| Worn row | page rows 15–16, cols 3, 9, 15, 21 | worn item icon, else placeholder |
| Description | page cols 0–1, rows 18–19 | selected item / worn item icon; blank on `[CLOSE]` or an empty bag slot; placeholder on an empty worn slot |
| Panel worn cells | rows 22–23, cols 24/26/28/30 (weapon, armour, helmet, charm) | as the worn row; redrawn on equip/remove/destroy (T8 path) |
| Quick slots | icon-bar FOOD/POTION/SCROLL slots, rows 18–19, cols `3i`, `3i+1` | the current auto-fill pick (§8.11 rulings 3) + stack count digit at col `3i+2` row 19 (the existing quick-potion layout); empty class → its representative icon (APPLE / HEAL / TELEPORT) greyed by the existing `IS_GREY` rule; redrawn through the existing `slot_redraw` when the pick or count changes |
| Ammo slots (AMMO-COUNT, user 2026-10-29) | Warrior dagger / bow slots (3 / 4), rows 18–19, cols `3i`, `3i+1` | drawn like a quick slot: the 16×16 dagger icon (`ICONS16_AMMO_DAGGER`, `$47`) / the **bow** icon (`IT_BOW`, `$06`) replace the 24×16 bar art; the count of `DAGGERS` (0–9) / `ARROWS` (0–24) in col `3i+2`: units digit row 19, a non-zero tens digit above it on row 18 (a 6×8 digit does not fit two to a cell: read top-down, 2 over 0 = 20); 0 ammo (or no bow) greys the 6 cells incl. the digit (`IS_GREY`, a grey `0`). Redrawn when `PD_AMMO` is raised (throw, shot, pickup). Mage: unchanged. The bag page's row 1 (`DAGGERS n  ARROWS n`) already shows both counts |

- **Floor reuse: NO** *(reversed 2026-10-26 by FLOOR1: the floor draws these icons)* (user question answered from the numbers). The floor set is 6 class
  glyphs × 8 B = **48 B** in tile ids 17/18/60–63 (ids already reserved: 0 B new). Deriving
  8×8 floor glyphs from the 16×16 set needs a 2:1 downscale routine (~40 B, and a 2×2→1 pixel
  reduction is unreadable at 8×8) **and** a tile id per drawn type (39 types vs 4 free ids:
  the 64-id tileset is full). It would save at most 48 B for ~40 B of code and ids that do
  not exist. The floor keeps the 6 class glyphs; class by shape, type by ink (Q1).
- **Cost (E).** Data 1,376 B raw. Code: one 2×2 copy blitter shared by page and panel
  (~30 B, ~1.0k T per icon; the full page = 20 + 4 + 1 icons ≈ 26k T, cheaper than the T14
  doubling); quick-slot pick-icon hook ~25 B bank 3; minus the doubling code.
- **Art brief (graphics-artist, Design canvas, user reviews; import via `tools/svg_sprites.py`
  to 32 B raw per icon, index order above).**
  - **Silhouette first:** each icon must read as a filled black-and-ink shape at 1× on a TV;
    1-px margin (live area 14×14) so neighbours and the cursor block stay apart; strokes ≥ 2
    px on the main shape; no large dither areas (chain mail's mesh is the only texture).
  - **One ink, no paper detail:** colour cannot carry meaning inside an icon; the type ink
    comes from `it_tab` (the artist does not pick it, but checks it reads on black and on
    blue paper).
  - **Class-consistent shapes, varied within the class:** swords share one 45° blade (bottom
    left → top right) differing by length/hilt (Short: short blade, plain cross; Long: longer,
    wider guard; Cleaver: broad chopping blade, heavy hilt); the Axe shares the 45° haft with
    an axe head. Staves share a 45° pole differing by head (Oak knot, Iron banded cap, Rune
    glyph-crystal, Bone skull). Armour = torso silhouette (Robe flared hem, Leather vest
    with laces, Chain mesh, Plate segmented with pauldrons, Silk Cloak hooded drape, Grave
    Cloak tattered hem). Helmets = head-on helmet (Hood soft peak, Helm nasal guard, King
    crown band, Mirror flat visor with a shine notch). Rings = one band shape with a
    differing stone (Might fist, Ward shield, Fire flame, Grave skull); amulets = chain +
    pendant (Mana drop, Plenty wheat sheaf, Scarab beetle). Potions = flasks of three
    distinct shapes (Heal round, Mana tall, Cure square) so the type also reads by shape;
    scrolls = one rolled scroll with a differing sigil (Teleport swirl, Fear eye, Sleep Z,
    Enchant star). Food: five distinct silhouettes (carrot, apple, pear, cheese wedge, meat
    on the bone). Book: closed tome with a clasp. Bow: drawn bow with string, 45°.
  - Placeholders: dotted outlines (2 px dot / 2 px gap) of the sword, torso, helm and ring.

**Q3 Page layout and verbs (full screen, 32×24 cells).**

| Rows | Content |
|---|---|
| 0 | `INVENTORY` · `BAG 12/20` · right: **`[CLOSE]`** (cols 26–31, selectable) |
| 1 | Warrior: `DAGGERS 3  ARROWS 14`; both: `KEY` when held |
| 2–13 | **bag grid 5 × 4**: slot (c, r) icon 2×2 at col `3 + 6c`, rows `2 + 3r`, `3 + 3r`; stack count digit (2–9; none for 1) at col `5 + 6c`, row `3 + 3r` |
| 14 | worn labels `WEAPON ARMOUR HELM CHARM` |
| 15–16 | **WORN row**: 4 icons 2×2 at cols 3, 9, 15, 21; empty slot = its slot placeholder (Q5) |
| 18 | description 1: name with BUC prefix (§8.7), ×n for stacks; **from 2026-10-26 (Q5):** the selected item's 16×16 icon at cols 0–1 rows 18–19, both text lines start at col 2 (≤ 40 chars) |
| 19 | description 2: stats generated from the type table (`1D8 ATK+1`, `DEF 2`, `HEAL 10 HP`, `UNKNOWN`) + note `WORN` / `STICKY` |
| 21 | **verb strip**: up to 3 words, the chosen one in inverse attr |
| 22 | **message row** (refusals, page stays open) |
| 23 | help `FIRE SELECT  I CLOSE` |

- **Cursor** = attr only: the slot's 3×2 cells get paper blue (`ink | $08`). ←→ within a
  row, ↑↓ between rows; ↓ from bag row 3 → WORN (col `min(c, 3)`); ↑ from bag row 0 →
  `[CLOSE]`. Opens on bag slot 0. FIRE on an item → verb strip (←→ choose, FIRE confirm,
  ↑/↓ back). FIRE on `[CLOSE]` or key `I` closes (joystick-complete).
- **Verbs and turn cost** (all close the page and apply after close, T13):

| Item | Verbs | Turns |
|---|---|---|
| potion / food / scroll / book | DRINK / EAT / READ / READ · DISCARD | 1 · 0 |
| gear in bag | EQUIP (swaps a non-cursed worn item into the bag) · DISCARD | 1 · 0 |
| worn gear | REMOVE (needs a free bag slot) | 1 |
| bow | DISCARD | 0 |

  Refused on the page (row 22, no close): EQUIP / REMOVE against a worn cursed item
  (`IT IS CURSED! YOU CANNOT.`), REMOVE with a full bag (`BAG FULL.`).
- **DROP is cut; DISCARD replaces it**: the item is destroyed (no floor-list entry, no glyph
  stamp, no "one entry per cell" merge). Worn items cannot be discarded. `YOU DISCARD THE
  HELM.` Rationale: same player value (clear junk, free a slot) at ~15 B instead of ~80 B.
- **QUICK pin is cut** (state + verb + rule ~70 B); quick slots auto-fill only (§8).
- **Bag 20, stacking:** stacks merge on equal `TYPE` + `ISTATE` up to 9 (potions, scrolls,
  food only); **books, the bow and gear NEVER stack** (user/engineering 2026-10-20; one slot each). Pickup tops up an existing stack, else takes
  the first free slot; bag order = pickup order, compacted when a slot empties. Floor
  non-ammo entries are always `QTY` 1. Full bag: the item stays, `BAG FULL.` once per
  arrival on the cell. Floor weapons are generated for the hero's class only (no junk).

**Q6 Teleport (scroll and trap share one routine).** Target = a random room ≠ current,
≠ Sanctum, ≠ lair while its boss lives (gameplay RNG). Arrival: storey `rnd(2)`, col `x`
`rnd(28)+1`, ≤ 16 tries until the 3-col body is on solid floor, clear of every footprint
±1, every trap col and every monster body; fallback storey 1, nearest legal col to 14
(storey 1 is never blocked). **No followers.** The current room is banked exactly as on a
normal exit (room record, §9.4.2); the target room is built as a normal entry
(`GS_TRANSITION`, survivors as persisted / §9.4.3 lazy spawn) with the arrival spot as the
entry point, so the entry spawn-distance rule applies to it. No scroll: an instant room
redraw after the attr flash. Arrival on an item picks it up as usual; arrival never fires a
trap (§1.5).

**Q8 Separate item stream: CONFIRMED.** `ITEM_RNG` = the generator algorithm seeded with
`f(master seed, depth | $80)` (as light-ID's depth-255 derivation). The whole `GEN_RNG`
pass is unchanged byte for byte, incl. the existing 3B potion step (its 2–3 entries stay;
their types are rolled on `ITEM_RNG`, the first is Heal). After it, `ITEM_RNG` runs: potion
types → food → scrolls → gear (+ BUC and cursed value) → class books → ammo / bow
(Warrior) → traps. New entries avoid every footprint, L2 span (+1) and existing entry (one
non-ammo item per cell). Effect: descriptors, LP, budgets, room records and population
goldens stay; decor changes only where a new item cell meets a decor footprint (decor still
skips item cells, its rnd count per try is unchanged). Reason: no world rebaseline and the
3E generator can be tuned without touching levelgen parity.

**Q9 Text: 0 B in banks 0/4/6; 3E text cap 1,100 B raw.** No per-item descriptions: the
second description line is formatted from type-table numbers. Names are **≤ 3 word tokens**
(1 B each, 0 = end) into one word table (`POTION OF HEAL`, `RUBY POTION`, `CHAIN MAIL`,
`WARLORD'S CLEAVER`); no plurals (page `×3`, floor singles). Budget: word table + per-type
refs ≤ 460 B (incl. §8.8 appearances) · log stems ≤ 480 B (pickup, eat, drink, read, ID,
equip/remove/discard, key, teleport, bag full; incl. §1.5 traps and §8.7 curse lines) ·
page-only text (labels, verbs, help) ≤ 160 B inside the page overlay stream. Resident text
goes to bank 1.

**Q10 Start bag (confirms §4).** Warrior: Short Sword + Leather worn; bag Heal ×1, Apple ×1;
DAGGERS 3, ARROWS 0. Mage: Oak Staff + Robe worn; bag Heal ×1, Mana ×1, Apple ×1. **[rev 6: no
BUC/known flags.]** **`DEBUG_KIT` adds** (on top of §1.4): Cure ×1, Mana ×1 (Warrior), one
scroll of each of the 4 types, Meat ×1, class book ×1, a **Helm** (plain; the cursed Helm and
the "four scrolls (unknown)" are gone) — exercises EQUIP, Enchant, READ.

**Q11 Drops (≤ 24 B data).** Drop table = **5 rows × 3 B** (kind, item type, chance code
1/2 · 1/3 · 1/4), the §9.1 column unchanged: Rat Cheese 1/4 · Goblin Apple 1/4 · Orc Meat
1/3 · Skeleton Archer Arrows ×3 1/2 (Warrior runs) · Necromancer Mana 1/3; no other kind
drops. Tiers drop as their base kind. Boss uniques = **8 B** (item type per depth D1–D7 +
the D4 Mage variant, §8.6), always dropped, `m` 0 (BUC is gone, rev 6). Placement (FLOOR1: the
2-col footprint rules above): onto an item within ±1 of the dead body's centre col, else the
nearest free footprint within ±3, else a non-unique is lost; a unique searches the whole storey. Gameplay RNG. The generator leaves ≥ 1
floor-list entry free (≤ 31 used) so a unique always fits; other drops are lost when the
list is full.

**3E pickup/drop rulings (2026-10-20).**

1. **Log lines** (UPPERCASE, no article, no trailing stop, all ≤ 32):

| Event | Line | Longest |
|---|---|---|
| Pick up potion / food / scroll / book / weapon / armour / charm / bow | `YOU PICK UP ` (bank-0 `cmb_pick`) + item name (§8.11 table; stack top-up prints the same) | `YOU PICK UP WARLORD CLEAVER` / `...TELEPORT SCROLL` 27 |
| Pick up ammo | `YOU PICK UP 3 ARROWS` (count + plural; the existing counter format, the only plural) | `YOU PICK UP 9 DAGGERS` 21 |
| Bag full | `BAG FULL` (8). The item **stays on the floor**; once per arrival on the cell | 8 |
| Ammo over cap | `QUIVER FULL` (existing); takes what fits, remainder stays | 11 |
| Ordinary monster drop | **no line**: the glyph simply appears on the body's cell (saves ~15 B; the ink says the type) | — |
| Boss unique drops | `BOSS DROPS ` (new resident stem, 11 B text) + item name | `BOSS DROPS WARLORD CLEAVER` 26 |
| Key found | `YOU FIND THE LAIR KEY` (existing, 21) | 21 |

   The legacy `cmb_bow` (`YOU PICK UP A BOW`) and the 3B stand-in `found` (`...A POTION`) are
   retired: bow and potions use `cmb_pick` + name, so no article remains anywhere.
2. **Drop table (5 rows × 3 B = 15 B; a row = base kind, item type, chance code):**

| Row | Kind (tiers as base) | Item type | Chance |
|---|---|---|---|
| 1 | Rat | `IT_F_CHEESE` | 1/4 |
| 2 | Goblin | `IT_F_APPLE` | 1/4 |
| 3 | Orc | `IT_F_MEAT` | 1/3 |
| 4 | Skeleton Archer (Warrior runs only) | arrows ×3 (`IT_ARROW`, qty 3) | 1/2 |
| 5 | Necromancer | `IT_P_MANA` | 1/3 |

   The §9.6 tier numerator bump and the "tier of a no-drop base drops random food 1 in 4" stay
   as written there. `F_RESPAWN` monsters and golden bosses use no row.
   **Boss uniques (8 B, item type by depth D1..D7 + D4 Mage variant; D8 none):** D1 `IT_H_KING`
   · D2 `IT_A_SILK` · D3 `IT_A_GRAVE` · D4 `IT_W_CLEAVER` (Warrior) / `IT_W_BONE` (Mage) · D5
   `IT_C_SCARAB` · D6 `IT_C_GRAVE` · D7 `IT_H_MIRROR`. A unique is simply **a fixed type whose
   table stats beat the generic tier, `m` 0** (no `+2`, no flag; the `U` mark in `items.txt` only
   drives the shimmer). **Placement (FLOOR1, see the FLOOR1 rules above):** an
   existing item within d−1..d+1 of the body's centre col d (an exact-col stack); else the nearest
   free 2-col footprint within ±3. A drop of a 9th distinct type of the room (the 8-type
   invariant), with no spot or a full list (31 used) is lost silently; a unique first displaces an
   ordinary item when the room is at 8 types, then searches the whole storey and always fits
   because the generator leaves entry 32 free (FLOOR_N ≤ 31 for generation).
3. **Quick use (icon bar, §3.5), per T10 `bag_pick` modes:** FOOD icon = the **lowest-value food
   type** (Carrot → Apple → Pear → Cheese → Meat); POTION icon = lowest potion type id (Heal →
   Mana → Cure); SCROLL icon = **largest stack**, ties lowest type (Teleport → Fear → Sleep →
   Enchant). Success prints the verb stem (`YOU EAT THE CARROT`, `YOU DRINK THE HEAL POTION`, `YOU
   READ THE TELEPORT SCROLL` 28) and costs **1 turn**. **POTION (manager ruling 2026-10-20, T11 review):** a type whose
   effect would be refused (Heal at full HP, Mana at full MP, Cure with no POISON / WEAK / FEAR /
   CONFUSED) is skipped for the next in order Heal → Mana → Cure; all refused → `NO NEED`. Empty class: `NO FOOD` / `NO POTION` / `NO
   SCROLL`, **0 turns**, nothing consumed. `NO NEED` (Heal at full HP, Mana at full MP, EAT at
   100) is also 0 turns and consumes nothing.
4. **Pickup turn cost = 0 extra.** Pickup is automatic at the end of the turn (§2.2 order:
   pickups → aura → hunger…); the turn was already paid. **An item under the hero is picked up
   at the end of the turn** — also when he stood still, and a drop landing under his body
   (manager ruling 2026-10-20, T11 review: the D3-7 ammo retry stands). `BAG FULL` prints once
   per arrival: only when the item's column was not under the hero's body on the previous turn
   (walking across one item prints it once; stepping fully off and back on prints it again).

**3E generation rulings (2026-10-20; designer, from the review of `tools/items_model.py`, commit
f387ff0).** The model is the byte-exact spec for the Z80 generator (T6); the defaults it
chose stand except where a line below says CHANGE. All 3E rolls are on `ITEM_RNG`
(§8.5/§5/§8.7/§1.5 mentions of `GEN_RNG` for books, cursed value and traps are superseded by Q8).
- **Streams.** `ITEM_RNG(m, d)` = the generator algorithm seeded `LVL_SEED(m, d|$80)` with the
  usual `^ (d'*$0101)` (0 → 1), `d' = d|$80`; derived from the MASTER seed, not the reseeded
  level seed. Light-ID stream = same with `d' = 255`. Run order per level: potion types (+ D8
  relocation) → food → scrolls → gear → books → ammo/bow → traps.
- **Roll order inside an item:** type (or qty) first, then BUC `rnd(16)`, then (cursed only)
  value `rnd(8)`, then placement (`room = pool[rnd(n)]`, `storey = rnd(2)`, up to 8 × `col =
  2 + rnd(28)`, first legal wins; none legal → the item is dropped silently, rolls stay
  consumed). The ≤ 31 cap is unreachable (max 17 new+base entries: 3+4+2+2+2+2+2 incl. bow
  bundle), so the Z80 omits the cap check.
- **Potions:** entry 0 = Heal (no roll); entries 1..n = uniform Heal/Mana/Cure `rnd(3)`.
- **Food** 3 + `rnd(2)`, type uniform of the 5 (`rnd(5)`). **Scrolls** 1 + `rnd(2)`, type uniform of 4.
- **Gear** 1 + `rnd(2)`; type uniform over the depth- and class-gated §8 table (start kit and
  uniques excluded, other-class weapons excluded). **BUC:** one `rnd(16)` `v`: `v < B` →
  BLESSED (m +1); `v < B + C` → CURSED + HIDDEN, then `w = rnd(8)` walked over the §8.7 row in
  column order m = −2, −1, +1, +2 (cumulative thresholds); else normal. Enchant bits 0.
- **Rooms:** food, scrolls, gear and every book except the D1 one use present, non-start rooms
  (lair allowed: it is the key's reward). D8 exception (Q1): food, gear and potions avoid the
  lair; scrolls/books (PAGES) and ammo are exempt as before. Ammo/bow: non-start, non-lair.
  **D1 book: start room** at a placed col. **CHANGE (model):** the D1 book gets the bow's
  deterministic scan fallback inside the start room, so it is never dropped (without it the
  Warrior/Mage has no ability at all).
- **2nd book:** `rnd(2) == 0` rolled only on D4–D7 (no roll D1–D3, D8).
- **D8 lair potion:** RELOCATE (the model's choice). A dropped Heal would break "≥ 1 Heal"
  and "2–3 potions"; the entry keeps its slot and type, moves to a non-start non-lair room
  via `place`, scan fallback if that fails. Types of all entries are rolled first; D8's
  base floor list therefore differs from `GEN_RNG`'s output only in that cell (decor goldens
  for D8 lair potions are re-baselined).
- **Shared cells (generation):** no. New entries never share a cell with any existing entry
  (stricter than Q8's "non-ammo"; ammo sharing is a runtime §6.3 rule only). Sole exception:
  the D2 arrow bundle in the bow's cell (bundle entry first, bow second: the cell shows its last entry, the bow's icon). The base potion
  entries may already share among themselves (3B), unchanged.
- **Ammo (Warrior only; Mage consumes no rolls):** dagger qty `2 + rnd(2)`, then arrow qty
  `5 + rnd(4)`, then (D2) the bow. The hero class is fixed before level generation.
- **Light-ID shuffle:** partial Fisher-Yates, potions first (3 of 6 appearances), then
  scrolls (4 of 8); step `i` swaps `pool[i]` with `pool[i + rnd(n − i)]`; the id stream is
  used for nothing else.
- **Traps:** per trap: type `pool[rnd(len)]` (once, before the tries, consumed even if the
  trap is then dropped), then ≤ 8 × (room = uniform among present non-start non-lair rooms
  without a trap, `storey = rnd(2)`, `t = 6 + rnd(20)`), first legal wins; no eligible room →
  dropped. The D1 "start body ±1" rule is vacuous (start room excluded). Pit zone and
  footprints are applied on both storeys (the model is slightly stricter than §1.5 on
  storey 0; keep it). A trap never shares a floor-item col in its room/storey.
- **Key room:** no interplay. The key has no entry; `LVL_KEYROOM` is whatever `level_gen`
  set, and items may lie in it. The key is granted on first entry (Q1).
- **Stale text fixed with this note:** §5 book placement and §8.7 cursed roll say `ITEM_RNG`.

**3E text rulings (2026-10-20; designer, closes the T4 name/message gaps; supersedes the
wording in §5, §7, §8.7, §8.8, §1.5 where it differs).** Style = `src/strings.txt`: UPPER
CASE, **no trailing full stop**, `!` and `:` allowed, an internal `.` only in the ALARM line;
every composed line ≤ 32 (`LOG_MAX`).

**(1) Names.** A name is ≤ 3 word tokens, each word ≤ 8 chars, 65 distinct words in one table.
**No article** in composed lines (`YOU PICK UP BLESSED HELM`, not `A BLESSED HELM`: the A/AN
code costs more than the 2 chars it would cost). Composer: `stem + [BLESSED␣|CURSED␣] + name`;
the BUC prefix is spelled out (8 / 7 chars) and only gear (weapon, armour, helmet, charm) ever
has one. **Name length caps: BUC-able gear ≤ 12 chars incl. spaces; every other type ≤ 18.**
The longest stem is 12 chars (`YOU PICK UP `, `YOU DISCARD `), 12 + 8 + 12 = 32: no
truncation rule is needed.

| Type (IT_*) | Display name (len) | Type | Display name (len) |
|---|---|---|---|
| F_CARROT / APPLE / PEAR / CHEESE / MEAT | CARROT 6 · APPLE 5 · PEAR 4 · CHEESE 6 · MEAT 4 | W_SHORT / LONG / AXE | SHORT SWORD 11 · LONG SWORD 10 · WAR AXE 7 |
| P_HEAL / MANA / CURE known | POTION OF HEAL 14 · POTION OF MANA 14 · POTION OF CURE 14 | W_CLEAVER (unique) | WARLORD CLEAVER 15 |
| P_* unknown (§8.8) | `<colour> POTION`, longest EMERALD POTION 14 | W_OAK / IRON / RUNE / BONE | OAK STAFF 9 · IRON STAFF 10 · RUNE STAFF 10 · BONE STAFF 10 (unique) |
| S_TELEPORT / FEAR / SLEEP / ENCHANT known | SCROLL OF TELEPORT 18 · … FEAR 14 · … SLEEP 15 · … ENCHANT 17 | A_ROBE / LEATHER / CHAIN / PLATE | ROBE 4 · LEATHER 7 · CHAIN MAIL 10 · PLATE MAIL 10 |
| S_* unknown | `SCROLL <label>`, longest SCROLL MIRADEL 14 | A_SILK / GRAVE (unique) | SILK CLOAK 10 · GRAVE CLOAK 11 |
| BOOK (by `HERO_KIND`) | **WAR TOME 8** (Warrior) · **SPELL TOME 10** (Mage); replaces SPELLBOOK / WAR MANUAL (SPELLBOOK is 9 chars) | H_HOOD / HELM | HOOD 4 · HELM 4 |
| BOW | BOW 3 | H_KING / MIRROR (unique) | KING HELM 9 · MIRROR HELM 11 |
| C_MIGHT / WARD / FIRE | MIGHT RING 10 · WARD RING 9 · FIRE RING 9 (was RING OF FIRE WARD) | C_MANA / PLENTY | MANA AMULET 11 · FOOD AMULET 11 (Plenty: burn ×½) |
| C_SCARAB (unique) | SCARAB AMULET 13 | C_GRAVE (unique) | GRAVE RING 10 (was RING OF THE GRAVE) |

Appearance words (§8.8, unchanged): colours RUBY AZURE EMERALD AMBER VIOLET MILKY; labels
ZORAK VELMIS OSTRUN KAPPU MIRADEL THUNE YOLQ ABRAXA. Bag types: food 5 + potions 3 + scrolls 4
+ book 1 + bow 1 + gear 25 = **39 names**. Uniques never carry a BUC prefix.
**Computed longest lines (all ≤ 32):** `YOU PICK UP BLESSED SHORT SWORD` = 12+8+11 = **31**
(equal: `… BLESSED MANA AMULET`, `… FOOD AMULET`; CURSED variants 30) · `YOU PICK UP SCROLL OF TELEPORT`
30 · `YOU PICK UP WARLORD CLEAVER` 27 · `YOU READ THE SCROLL OF TELEPORT` 13+18 = **31** ·
`YOU DRINK THE EMERALD POTION` 28 · `YOU DISCARD BLESSED SHORT SWORD` 31 · `YOU EQUIP BLESSED
MANA AMULET` 29 · `YOU REMOVE BLESSED SHORT SWORD` 30 · `IT WAS A SCROLL OF TELEPORT` 27.
Overall maximum **31**. The legacy `found` / `quaff` strings (`YOU PICK UP A POTION`, `YOU
DRINK A POTION`) are deleted by T4. Per-type name refs: 3 B/type (3 word ids, 0-padded, no
terminator when full) = 39 × 3 = 117 B; unknown potion/scroll names are composed by code from
the §8.8 map (colour/label word + POTION/SCROLL), 0 extra refs.

**(2) Food odds and hunger.** Food entry type is **uniform over the 5 at every depth** (the
`tools/items_model.py` rule `rnd(5)`, unchanged: 0 B of table, mean 23 FOOD per item, 3–4
items ≈ 80 FOOD + drops ≈ 100 against ≈ 75 burned per level, §7). No depth weighting. Hunger
numbers, complete: `FOOD_START` 80 · cap 100 (eating clamps) · −1 per 6 turns (jump −2 extra)
· stage by FOOD: FED ≥ 50, OK 25–49, HUNGRY 10–24, WEAK 0–9 · food values CARROT 10, APPLE 15,
PEAR 20, CHEESE 30, MEAT 40 · never fatal. **Stage-change lines** (only on a downward crossing
into HUNGRY / WEAK, and on an upward crossing into FED; crossing into OK and WEAK→HUNGRY print
nothing): `YOU ARE HUNGRY` · `YOU ARE WEAK WITH HUNGER` · `YOU FEEL WELL FED`. **FAINT1
(2026-10-26, §7.1) supersedes the 50-turn repeat line:** the WEAK rollover is now the faint
(`YOU FAINT FROM HUNGER`).

**(3) Messages.** `E` = exists in `src/strings.txt` (0 B), `N` = new.

| Event | Line (len) | |
|---|---|---|
| pickup | `YOU PICK UP ` + [BUC] + name (stem `cmb_pick`) | E |
| bag full | `BAG FULL` 8 | N |
| key found | `YOU FIND THE LAIR KEY` 21 | N |
| drink / read / eat | `YOU DRINK THE ` 14 · `YOU READ THE ` 13 · `YOU EAT THE ` 12 + name | N |
| book read | `YOU READ THE BOOK` then the §5 lines (`bk_learn`, `bk_rises`, `bk_grasp`, `bk_vigor`, `bk_power`, `bk_crumbles`) | E |
| identify on use | `IT WAS A ` 9 + known name (unknown types only, after the effect line) | N |
| Heal | `YOU FEEL HEALTHIER` (`spl_drain_heal`) | E |
| Mana | `MANA SURGES!` 12 | N |
| Cure | `YOU ARE CURED` 13 (also +4 HP) | N |
| Fear scroll | `THEY FLEE IN TERROR!` 20 | N |
| Sleep scroll | `THEY FALL ASLEEP!` 17 | N |
| Fear/Sleep, empty room; Enchant with no candidate (GEAR3) | `NOTHING HAPPENS` 15 | N |
| Teleport scroll / trap | `YOU ARE TELEPORTED!` 19 | N |
| Enchant, an item +1 (GEAR3) | `ENCHANTED: ` + name (max 26) | N |
| class gear gate refusal (GEAR1) | `YOUR GEAR FORBIDS IT` 20 | N |
| Enchant, worn cursed | `THE CURSE LIFTS: BLESSED!` (`cmb_lifts`) | E |
| equip / remove / discard | `YOU EQUIP ` 10 · `YOU REMOVE ` 11 · `YOU DISCARD ` 12 + [BUC] + name (no `THE`) | N |
| equip cursed reveal | `IT CLINGS TO YOU! CURSED ` + signed digit (`cmb_cling`) | E |
| cursed lock | `IT IS CURSED! YOU CANNOT` (`cmb_cursed_no`) | E |
| known-waste refusal (no turn, item kept) | `NO NEED` 7: known Heal at full HP, known Mana at full MP, EAT at FOOD 100. Cure and unknown types are never refused | N |
| poisoned EAT refusal (no turn, item kept; POIS1 §7.2; checked before `NO NEED`) | `TOO SICK TO EAT` 15 | N |
| shatter / wear lines | §8.7 / §8.10 (`cmb_shat_*`, `cmb_notch` …) | E |
| trap fires | `A DART HITS YOU!` 16 · `SLEEPING GAS!` 13 then `YOU FALL ASLEEP` (`st_asleep`, E) · `YOU ARE TELEPORTED!` · `AN ALARM BELL RINGS!` 20 · `A BELL RINGS. NOTHING COMES` 27 · `A STONE FALLS ON YOU!` 21 then `YOU ARE STUNNED!` (`st_stunned`, E; STUN1 §1.5.1) | N |
| trap found (walk-on of a hidden one needs no find line; search or Mage sense) | `TRAP FOUND: ` 12 + `DART` / `GAS` / `ALARM` / `TELEPORT` / `STUN` (4+3+5+4 chars new; TELEPORT is the item word) | N |
| search finds nothing | no line (0 B) | |

Search and Mage sense share the one `TRAP FOUND:` line. Scrolls carry **no BUC** (BUC is gear
only), so Enchant has no blessed/cursed scroll variants.

**(4) DISCARD destroys the whole stack** (one verb, no quantity prompt; frees the slot and
compacts the bag at once). Cheapest code; rationale as Q3. Worn items cannot be discarded.

**(5) Byte count (raw, before the dictionary packer).** Word table 65 words = **320 B**
(top-bit terminator) + type refs **117 B** = 437 B. **Bank 1 (resident) = 651 B**: 437 +
pickup/hunger/trap/key/teleport/bag-full strings 214 B (`BAG FULL` 8, key 21, TELEPORTED 19,
DART 16, GAS 13, ALARM 20, BELL 27, `TRAP FOUND: ` + 3 names 24, 3 hunger lines 55,
terminators 11). **Overlay (page-verb results, bank 3/page overlay) = 195 B**: stems 81
(DRINK / READ / EAT / IT WAS A / EQUIP / REMOVE / DISCARD) + effects 102 (NO NEED, NOTHING
HAPPENS, MANA SURGES!, CURED, FEAR, SLEEP, GLOWS) + 12 terminators. **New 3E words+stems =
846 B** (≤ 700 resident: OK 651; ≤ 310 overlay: OK 195). With the page-only text (~160 B,
Q9) the total is ≈ 1,006 B ≤ the 1,100 B cap; if the 160 B page text must also sit inside the
310 B overlay it is **45 B over** (355): trims in order are Cure → reuse `st_clear` (−14), or
move the 7 verb stems (81 B) to bank 1 (resident has 49 B of slack, so only ~4 of them fit).

**Hunger:** HUNGRY doubles the MP regen period (WEAK: none; HP regen FED only), 3E, §7.

#### 3E simplification (2026-10-20; rev 6, user decision: memory forces it)

**SUPERSEDES:** §8.7 (blessed/cursed, hidden value, bless, shatter), §8.8 (light-ID), the
BUC/cursed/HIDDEN/reveal parts of §8.9, §8.10 (blessed immunity, cursed wear, shatter
cross-refs), §8 (Enchant-blesses, "unknown never auto-fill"), §1.4/Q10 DEBUG_KIT (cursed Helm,
unknown scrolls), and in this section: Q1 BUC tints and the "appearance ink" for potions, Q3
`STICKY`/cursed refusals/BUC name prefix, Q9 "incl. §8.8 appearances", the generation rulings
(BUC `rnd(16)`, value `rnd(8)`, light-ID shuffle stream), text rulings (1) BUC composer and
unknown names, (3) `IT WAS A`, `cmb_cling`/`cmb_lifts`/`cmb_cursed_no`/shatter lines.

1. **Item record.** `TYPE` / `QTY` / `ISTATE`, 3 B as built. **`ISTATE` = bits 5–7 `m`
   (signed −3..+3, the existing `IST_M_*` macros) + bits 0–2 `q` (GEAR2, 2026-11-01: the
   per-instance offset rolled at generation for found weapons / armour / helmets, signed
   −1..+2, never changes; bits 3–4 stay 0).** [Superseded by `docs/design/gear_rules.md`
   §2 / §3: gear stats are the §8 table + v = m + q; Enchant picks a random worn item.]
   `m` starts 0 and changes only by (a) the **Enchant scroll** and (b) §8.10 wear.
   Main-stat effect of v = m + q: weapon dmg +v, armour/helm DEF +v (Robe/Hood max MP +v),
   clamped at 0 / `max(1,…)`.
   Only gear carries `ISTATE`; stacks still merge on equal `TYPE`+`ISTATE` (potions, scrolls,
   food only, always 0; books never stack). **Enchant (one rule, GEAR3):** a random worn weapon / armour /
   helmet (else a bag one) `m` +1, max +3 (`ENCHANTED: <name>`); no candidate →
   `NOTHING HAPPENS`, scroll consumed. Charms are never enchanted. Wear (§8.10): `m` −1 on the target, destroyed at −3 (slot empties, fists 1d2);
   Enchant is the repair. EQUIP/REMOVE/swap are always free (no lock, no refusal but `BAG FULL`).
   Tiers: the §8 table unchanged (Short Sword start / Long D2+ / Axe D4+; Chain D3+, Plate
   D6+; rings D2+, amulets D3+; Hood/Helm D1+; uniques §8.6).
2. **Names are fixed and always known:** `HEAL POTION` · `MANA POTION` · `CURE POTION` ·
   `TELEPORT SCROLL` · `FEAR SCROLL` · `SLEEP SCROLL` · `ENCHANT SCROLL` (type-first, 2 words,
   no `OF`). No `UNKNOWN`, appearance words, `BLESSED`/`CURSED` prefixes. Floor glyph ink stays
   per type: FLASK Heal `$42` · Mana `$45` · Cure `$44`; PAGES Teleport `$45` · Fear `$46` ·
   Sleep `$44` · Enchant `$47` (book `$43`). The player learns type by ink + the pickup line.
   Longest composed line `YOU READ THE TELEPORT SCROLL` 28. The known-waste `NO NEED` refusal now
   applies always (Heal at full HP, Mana at full MP, EAT at 100; Cure and scrolls never).
3. **Unchanged:** traps (§1.5, incl. the DART trap damage; it just no longer shatters
   anything); monster drops (Q11) and boss uniques (§8.6: fixed-stat items, never relied on
   BUC; `m` 0). **DEBUG_KIT** (on top of §1.4): Cure ×1, Mana ×1, one scroll of each of the 4
   types, Meat ×1, class book ×1, plain Helm ×1. **`ITEM_RNG` (Q8) kept.** Rolls that
   disappear: BUC `rnd(16)`, cursed value `rnd(8)`, and the whole depth-255 light-ID stream.
   **New exact per-item order:** type (or qty) → placement (`room = pool[rnd(n)]`, `storey =
   rnd(2)`, ≤ 8 × `col = 2 + rnd(28)`). Level order unchanged: potion types → food → scrolls →
   gear → books → ammo/bow → traps. Gear/trap/later outputs shift versus the T5 model (re-baseline
   `items_gen` goldens; `GEN_RNG`/world goldens untouched). **`FL_IST` is dropped:** a floor item
   is always `m` 0 (DISCARD destroys, nothing is dropped, boss/drop items are plain), so the floor
   entry is TYPE/QTY only and a pickup writes `ISTATE` 0 [GEAR2: `(FL_QTY − 1) & 7` = q, `FL_QTY` = 1 + (q & 7) for generated numeric gear, gear_rules.md §2.2] Floor ink is a pure function of TYPE
   (`it_attr`); `FL_ATTR` (T6) may become a per-draw lookup at the engineer's choice.
4. **DELETE / simplify (staff).** `items_model.py`: `light_id_map`/`id_rng`, `roll_gear_state`
   (BUC odds, `CURSE_M`, `BLESSED_M`), HIDDEN, `BUC_*` parsing, blessed/cursed checks in
   `check_items`; keep `ITEM_RNG`, placement, traps. T6 overlay: shuffle, BUC/value rolls,
   `known_init`, `FL_IST` writes. `item_defs.asm`: `IST_BUC_*`, `BUC_*`, `IST_HIDDEN*`,
   `IST_ENCH_*`/`ENCH_MAX` bits (use `m`), `IT_ID_*`, `ID_*`, `KNOWN_*`; `ITEM_RAM`: `ID_MAP` 7 +
   `KNOWN` 1 + `FL_IST` 32 = **−40 B** (`ITEM_RAM_LEN` 121 → 81, re-ASSERT). `items.txt` /
   `itempack.py`: appearance words (6+8), `BLESSED`/`CURSED`, `OF`, `APP` ink class, the `IT WAS A`
   stem; potion/scroll names to 2 words; re-run budgets. T8: shatter, bless, reveal-on-equip,
   curse lock; `hero_recalc` reads only `m`. T10 `item_name` mode bits BUC/appearance. T12:
   identify-on-use, elimination, unknown-refusal exceptions. T13: `STICKY` note, cursed refusals.
   Bank-0 `cmb_cling/lifts/cursed_no/shat_*` become dead (bank 0 is frozen, but deleting them
   frees bytes for the 3F pool; staff to confirm). Tests: drop reveal/bless/shatter/curse-lock/
   ID-elimination cases, `items_gen` BUC checks; add: Enchant +1..+3 cap and fists, wear to −3
   destroy, always-known names.
5. **Estimate of 3E bytes saved (qualitative):** state RAM −40 B; ID/BUC words + stems −~170 B
   tape (−14 appearance words ≈ −110 B table, stems/messages ≈ −60 B); T6 overlay ≈ −200 B
   (≈ 700 B raw left); T8/T10/T12 code (shatter ≈ 90, bless 30, reveal 20, ID + naming modes
   ≈ 270) ≈ −400 B bank 3/1; plus T13 refusals. **Total ≈ 0.9–1.0 KB**, enough to close the 3E gap
   without further feature cuts (QUICK pin stays cut).

---

## 9. Monsters

### 9.1 Roster (13 kinds + 2 unique bosses + Archmage → `kind_tab` 32, §11.2)

Every monster gains **depth scaling**: hp + (depth − 1), atk + (depth − 1) div 3.

| Kind | Body px | hp | atk | eva | DEF | dmg | W | Move / flags | Behaviour | Drop | Depths |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Rat | 32×16 | 3 | 0 | 1 | 0 | 1d2 | 2 | walker | chase | Cheese 1/4 | D1, D2, D4 |
| Bat | 24×16 | 3 | 1 | 4 | 0 | 1d2 | 2 | flyer | erratic | — | D1–D3 |
| Slime | 24×16 | 6 | 0 | 0 | 1 | 1d3 | 2 | walker, acts every 2 | chase | — | D1 |
| Goblin | 24×32 | 6 | 1 | 1 | 0 | 1d4 | 3 | walker, climber, opener | chase | Apple 1/4 | D1, D2 |
| Spider | 32×16 | 7 | 3 | 3 | 0 | 1d4 | 2 | walker, climber (own dorsal climb pair spider_climb1/2, STA|SYM; user 2026-10-30, was its rest pose) | hit **poisons**: POISON +12 per bite, cap 30 (= −1 HP / 4 turns; POIS1 §6.4.3) | — | D2, D4, D5 |
| Skeleton | 24×48 | 10 | 2 | 2 | 1 | 1d6 | 5 | walker, climber, opener | chase | — | D3, D5, D8 |
| **Vampire** | 24×48 | 14 | 2 | 1 | 0 | 1d6 DRAIN | 5 | walker, opener, acts every 2 (bat form: every turn) | **drain bite heals it** by the damage dealt (to max hp); **bat form** §9.2 | — | D3, D6, D8 |
| Ghost | 24×32 | 8 | 2 | 3 | 0 | 1d4 DRAIN | 3 | flyer | drift; touch 1 in 4 → CONFUSED 4 (§6.4) | — | D3, D6–D8 |
| Orc | 24×48 | 14 | 3 | 1 | 1 | 1d8 | 5 | walker, opener, climber (shared humanoid climb pair, 3F-T13bc) | chase | Meat 1/3 | D4, D6, D7 |
| Skeleton Archer | 24×48 | 8 | 2 | 2 | 0 | 1d4; arrow 1d6 PHYS r10 | **6** | walker, opener, climber (the Skeleton's climb pair, user 2026-10-29) | ranged | Arrows ×3 1/2 (W) | D4, D5 (ARCHER-DEPTHS H1, user 2026-10-29: not D7, §9.8) |
| Mummy | 24×48 | 18 | 3 | 0 | 2 | 1d8 | 5 | walker, climber (shared humanoid climb pair, user 2026-10-29), acts every 2 | hit drains 5 FOOD; **curse** 1 in 3 → WEAK 12 (§6.4) | — | D5 |
| Necromancer | 24×48 | 12 | 2 | 2 | 0 | 1d4; Dark Bolt 1d6+1 DARK r8 | **6** | walker, opener, climber (user 2026-10-29) | ranged, cooldown 2 (§9.2 RANGED-SPEC); Dark Bolt hit 1 in 3 → FEAR 3 (§6.4) | Mana 1/3 | D6–D8 |
| **Ogre Warlord** (unique) | **32×48** | 40 | 5 | 1 | 2 | 1d10+2 | **6** | walker, lair only | chase; every 3rd turn **SLAM**: reach 2, ×1.5 dmg, a hit STUNS 1 (§6.4) | unique | D4 |
| **Death Knight** (unique) | 24×48 | 50 | 6 | 3 | 3 | 1d10+3 | 5 | walker, lair only (3F-D1: not a climber) | chase; **parries** 1 in 3 PHYS hits (BLOCK frame, 0 dmg); a parried melee hit **notches** the weapon 1 in 2 (§8.10) | unique | D7 |

**Death Knight silhouette (round 4/5):** an evil twin of the Warrior with a clearly distinct
outline: a **two-handed greatsword** (blade carried upright above the shoulder when walking,
chopped down in CLEAVE) and a **horned, crowned helm**. Do not reuse Knight frames. **5 frame
ids:** WALK1, WALK2, CLEAVE, BLOCK, DEAD (the rev-2 WIND-UP is dropped; HURT = flash).
| **Necromancer Archmage** | 24×48 | **60** (ARCHMAGE-SPEC; was 40) | 4 | 3 | 1 | staff 1d6; **7 spells, §9.9** | **6** | blinks once, never walks | boss caster, §9.9 | — | D8 |

Opener = it can open closed doors (1 turn). Locked/sealed doors stop all monsters. The
Ogre and Death Knight scale by depth like the rest.

**3F-D3 (2026-10-28): this table is authoritative for the original kinds too.** The prototype
values still in `kind_tab` (Skeleton/Slime DEF 0, Goblin 1d3, Ghost hp 7, Slime hp 5) are
replaced by the values above (§9.8 D3-1); the §11.4 "monster DEF 0" rule was 3D-only.

**Door rules for monsters (designer decision 2026-10-03).**
- A closed door's plank cells block movement like a wall for every body.
- An **opener** whose chosen step would enter a closed, unlocked door's cells opens it
  instead: the whole turn is spent (2 ticks, it does not move), the connection's door bit
  is set (open in both rooms), and it moves on a later turn. Same cost as the hero (§2.3).
- **Non-openers and every flyer** (Bat, Ghost, the Vampire in bat form) are blocked; their
  step is simply illegal and their AI picks its next choice or waits. No movement, bump,
  follow, fall or knock-on ever opens a door without the opener flag.
- **Only the hero closes doors.** Closing also needs the door's cells free of bodies.
- **Locks (designer decision 2026-10-03):** the lock lives only in `EDGE_TAB` (per edge) and is
  the single source of truth; the door tile merely displays it and no tile flag is ever read
  for gameplay. Unlocking clears the EDGE_TAB lock, then the tile redraws.
- **Flyers and open doors (designer decision 2026-10-03):** an open door is passable to
  flyers only through its opening rows; the arch and lintel cells above it are solid for
  every body, so collision must test the whole body box (all cells), not one cell. A flyer
  too tall for the opening is blocked. Closed/locked doors block flyers (above).
- Following is unaffected: the follow rule runs on the hero's exit turn, when the door the
  hero walked through is open by construction.

**Resistances** (N blank; R resist, I immune, W weak, X reflect):

| Kind | PHYS | FIRE | COLD | SHOCK | DRAIN | DARK |
|---|---|---|---|---|---|---|
| Rat, Goblin | | | | | | |
| Bat | | | | W | | |
| Slime | R | W | | | | |
| Spider | | W | | | | |
| Skeleton, Skeleton Archer | | | **I** | | **I** | I |
| Vampire (undead set) | | **W** | **I** | | **I** | I |
| Ghost | R | | I | **X** | I | I |
| Orc | | R | | | | |
| Mummy | R | W | I | | I | I |
| Necromancer | | | R | | I | I |
| Ogre Warlord | R | | R | W | | |
| Death Knight | | **X** | I | W | I | I |
| Archmage | | | **X** | **X** | I | R |

Design intent:
- Undead shut off Frost and Drain, but burn.
- The Ghost bounces Lightning and Spark back at you.
- The Death Knight reflects Firebolt.
- The Archmage reflects Frost and Lightning, so the Mage must fight it with Firebolt and
  the staff, and the Warrior with steel.
- Reflected Death Bolts (Mirror Helm) deal ½ to the Archmage.

**Status immunity mask (3D, designer decision 2026-10-03; §6.4).** FROZEN follows COLD (no
mask bit); WEAK targets only the hero.

| Kind | Immune to |
|---|---|
| Rat, Bat, Goblin, Spider, Orc, Necromancer | — |
| Slime (mindless) | SLEEP, CONFUSE, FEAR |
| Undead: Skeleton, Skeleton Archer, Vampire (both forms), Ghost, Mummy | SLEEP, POISON |
| Bosses (`BOSS`) | SLEEP, FEAR (+ the kind's own), HOLD/MIND halved (§6.4) |
| Hero | — (OR of gear: Silk Cloak → POISON) |
| Tiers (§9.6) | as their base kind, plus the noted extras |

### 9.2 Behaviours (on top of prototype §6.4)

Flyers and ladders: engineering rule 2026-10-04 (B14), designer-confirmed. Full text in
prototype §6.4 "B14 fix rules": facing-side tie-break for yields on the shaft column;
forced yield when a blocked climb becomes a wait; flyer vertical fallback (up, then down,
in band, off the climb path, else wait). Accepted residual: a flyer between a wall and an
immovable body waits (the hero can fight or step back).
**User 2026-10-06 (free flight): the B8 ladder-end rule is DROPPED.** Flyers fly over ladder
shafts freely and may stop, wait, idle, reverse and attack inside a ladder-end box. The
only ladder constraints left are the hero-protecting ones above (anti-cork while he is
mid-ladder, forced yield, vertical fallback, squeeze past, B16). Exact rule: prototype §3.5.
Designer decision 2026-10-04: a climb blocked twice in a row by the same entity swaps
hero and blocker (no exclusions, no free attack, costs the hero's turn); see prototype
§6.4 "Squeeze past". This removes the residual: no ladder can stay blocked.

**Ladder queue: monsters following the hero to another storey (AI-L1, designer decision
2026-10-28; "strongest first" pending user confirmation).** Applies to climbers in the
prototype §6.4 walker rule 3 (`.seek`) only; the hero-protecting rules above run first and win.
Two monster-monster jams exist today:
- **J1 (own box counts as head-on):** the climb-start check (`turn3.asm .at`, `box_free` over
  the whole shaft rect) includes the climber's **own** end box, so a second climber that has
  stepped partly into that box (x = col ± 1/2) makes the one at `col` wait, while it is itself
  blocked by that body: both wait forever. **Fix:** the head-on check covers only the
  mid-ladder rows and the **far-end** box (direction from `ai_dir`). A body in the near box
  never stops a climb start.
- **J2 (approach from both sides):** two climbers reach for `col` from opposite sides and
  block each other one cell short. **Rule: strongest first.** Power = the kind's base hp
  (`kind_tab KT_HP`, static; not current hp, which would reorder the queue mid-fight; not W,
  which lives in bank 3). Equal power → the lower slot id wins (no extra code: slot order).
  When a seeker's step toward `col` is blocked by a monster that wins, and the seeker's box
  overlaps the near-end box (`|x − col| < 3`), it steps 1 cell **away** from `col` (no turn
  cost beyond its own; blocked → wait). Not overlapping → it **waits** facing the shaft (no
  pacing: pacing re-collides and costs bytes). Rule 1 (attack in reach) still comes first. A
  winner blocked by a loser just waits; the loser clears on its turn (one turn's delay).
- The shaft itself stays the existing queue: one climber per segment (mid-ladder + far box),
  the next starts when it is clear. No monster-monster swap on the ladder (D-AI1c's swap
  stays unbuilt; if built, it uses the same power compare instead of slot id alone).
- Why strongest first: the hero meets the biggest threat fresh and alone at the hole, can
  see it climbing and choose to fight or leave; weakest first wears him down with fodder so
  the strong one arrives when he is weakest (a hidden spike). It also reads as "the leader
  climbs, the pack waits". Today only Goblin (6) and Skeleton (10) climb, so it is mostly
  Skeleton before Goblin.
- **Cost:** J1 ≈ 6–10 B (direction-dependent rect origin/height), J2 ≈ 35–45 B with the
  power compare (blocker id, 2 × `KFIELD KT_HP`, overlap test, reverse step), ≈ 15–20 B
  without it. Runs only on a blocked seek step (< 0.5k T), nothing per tick. **If memory is
  short:** J1 + the symmetric back-off (the loser = whichever moves first, i.e. slot order)
  is the cheapest correct rule; the power compare is an add-on. J1 alone is the must-have.

**Ranged (RANGED-SPEC, designer decision 2026-10-29; T7; supersedes the 4-line rule).**
Shooters (one descriptor row each, R6; the Archmage's row is T11):

| Kind | Range r | Cool N | Hit rule | Damage | On hit | Step-away | Climbs | FX |
|---|---|---|---|---|---|---|---|---|
| Skeleton Archer | 10 | 1 | F1 roll | 1d6 PHYS, `max(1, roll×res − DEF)` | — | yes | no | arrow_fly `$07` |
| Skeleton Sniper | 14 | 1 | F1 roll | 1d8 PHYS, as above | — | **no** | no | arrow_fly `$07` |
| Goblin Slinger | 6 | 2 | F1 roll | 1d3 PHYS, as above | — | yes | yes | dagger_spin `$06` |
| Necromancer | 8 | 2 | auto-hit (spell) | 1d6+1 DARK, `roll×res`, no DEF | FEAR 3, 85/256 | yes | yes (user 2026-10-29) | NBOLT |
| Bone Caller | 8 | 2 | auto-hit | as Necromancer | as Necromancer | yes | yes | NBOLT |

Poltergeist is not a shooter (melee touch). atk / dmg include depth scaling and golden +2 / +1.
- **Geometry.** `gap` = empty cols between the boxes (melee reach = gap 0–1). **In range iff
  `gap < r`** (the bolt's cell 1 is the shooter's front neighbour; it strikes on entering the
  hero's near col = cell `gap+1`). **In line iff** shooter standing, hero standing (not
  mid-ladder) and the same storey (`storey_ref`); every standing body of a storey overlaps,
  so no row test is needed. **Flight row** `fr = shooter top + 2` (tall: `9s+4`, Slinger:
  `9s+6`), always inside the standing hero's rows `9s+2..9s+7`.
- **Clear line iff** (a) no `TF_SOLID` cell in `ROOM_MAP` row `fr` over the gap cols (air
  decor, torches and back-wall patches are non-solid by §1.2, so in practice only a mid-room
  block stops it) and (b) no body (any kind or state, mid-ladder included, pending excluded)
  in the rect gap cols × the shooter's rows: `box_free` with `ACT_SLOT` = the shooter. **No
  friendly fire:** a blocked line is never fired.
- **Cooldown.** Per-entity counter (2 bits). Set to **1 at spawn/arrival** (no shot on the
  first monster phase after room entry); set to **N on a shot**; decremented by 1 (floor 0) at
  the entry of the ranged hook (below), i.e. on every acting turn in which it did not melee.
  A shot needs the counter to be 0 AT HOOK ENTRY (the check uses the old value, then the counter
  decrements; T7 review 2026-10-29: "0 after the decrement" would fire every turn at N = 1).
  Net cadence for a stationary target: N = 1 → every 2nd turn, N = 2 → every 3rd; counter 1 at
  spawn/arrival/banked return. DYING bodies do NOT block the gap (`box_free` skips them).
- **Reflect gate:** a shooter never fires at a hero whose response to its type is X (Mirror
  Helm vs DARK); it behaves as if the line were blocked. **The Archmage is exempt** (T11; the
  §9.1 "reflected Death Bolt deals ½" intent needs it to fire).

**Per-turn order in `ai_monster`** (walker path; the yield rule, the act-every-2 gate and the
status step stay ahead, unchanged): 1 yield (`cork_check`) → 2 period gate → 3 melee
(`attack_if_reach.box`, `ret c`) → **4 ranged hook** (only `KF_RANGED` kinds; one flag test
for the rest) → 5 boss guard (§9.2 G2) → 6 walker rules (`.fstep` / `.other` / `.seek`).
The hook is entered after `ret c`, must not need the B5 box in BC/DE (it re-derives what it
needs), must preserve `TMP4` and the standing flag in H (or recompute), and returns CF = 1
when it consumed the turn. Hook, first match, cheapest reject first:
1. Decrement the counter. Shooter not standing, or hero not in line → CF = 0 (walker rules:
   climbers `.seek` the ladder toward the hero; Archer/Sniper patrol their storey).
2. Compute `gap`. `gap ≥ r` → CF = 0 (walker rules: it closes in).
3. Line not clear (wall scan, then `box_free`; or reflect gate) → CF = 0.
4. Counter 0 → **SHOOT**: face the hero (free), resolve now (below), counter = N, CF = 1.
5. `gap ≤ 2` and step-away kind → one walker step away from the hero (faces the step);
   blocked → wait facing the hero. CF = 1. (`gap ≤ 2` here means gap 2: gap 0–1 meleed.)
6. Otherwise **HOLD**: wait facing the hero, CF = 1 (in range, clear, reloading: it does not
   walk into melee; the hero must close the gap). Sniper holds at gap 2 too.
FEAR / CONFUSED / held monsters never reach the hook (status code), so they never shoot.

**Resolution (input tick, logic first, §6.5.1).** RNG order inside the shooter's slot turn:
PHYS: to-hit `d20 + atk ≥ 10 + hero eva`, then damage. DARK: damage, then the on-hit roll
(`r < 85`, via the T6 generic on-hit apply; skipped when the damage is 0 / I). Hero I → 0,
`UNAFFECTED`. Lines reuse the monster melee hit/miss strings (no new text). Death credit,
DYING, HP bar, log and damage number follow §6.5.1 (`COMBAT_NOT_BEFORE` = impact tick; game
over not before it). **Monster shots never bounce, never reflect, never drop an item** (hit
or miss). FX: the track starts at the shooter's release entry in `anim_tick` (far6), release
tick 2 + (slot & 1) (parity stagger), from the shooter's front col at `fr` to the hero's
near col; a hit plays the impact frame + `$42` flash there, a miss ends at the same col with
no impact and no flash. ≤ 3 tracks shared with hero bolts; a 4th waits (logic unaffected).
The SHOOT pose = the existing cut/cast frame (§9.7, user 2026-10-28).

**Data T9/T11 need from T7:** the hook leaves a **caster pre-rule slot** before step 4 (Bone
Caller summon, Archmage summon/teleport run there first); Bone Caller needs its own summon
counter (0..8, 4 bits) and a ≤ 1-live-summon test (summoned bodies carry `F_RESPAWN`; the
owner link is T9's choice: 4-bit owner slot or a room scan); the descriptor table gets an
Archmage row (r 28, N 2, auto-hit, 1d8+3 DARK, 1 bounce, no reflect gate). **ARCHMAGE-SPEC
(§9.9) changes that row to N 1, 0 bounces, and adds 6 more rows (7 in all).**

**AI and resistances:** a monster never fires at a body that reflects its type (Archmage
exempt, above).

**Archmage** (never leaves the lair): **superseded by §9.9 ARCHMAGE-SPEC (2026-10-29)**. The
old list (summon cd 6 → Death Bolt cd 2 → teleport when adjacent cd 4 → melee) is replaced:
7 spells on a telegraphed cycle, one phase blink at ½ hp, summons and the staff on off-turns.

**Vampire** (D3, D6, D8; and the golden Vampire Lord). Humanoid form is the Vampire kind;
**bat form reuses the Bat kind's frames and movement** (flyer, erratic, bat attack 1d2),
while keeping the Vampire's current hp, resistances and its encounter-cap weight (it never
frees cap room). Transforming costs its whole turn and prints `THE VAMPIRE TURNS INTO A
BAT!`. Bat form heals nothing; the drain bite exists only in humanoid form. First match:
1. **Flee:** humanoid, hp ≤ ⅓ max (E: 5 of 14), the hero in reach or in line, and it has
   not fled yet → bat, runs away erratically (away from the hero) for **8 turns**, then
   reverts to humanoid (once per life; the golden Lord may flee once too).
2. **Close distance:** humanoid, hero on the **other storey** or across a pit (no walk path
   shorter than 12 cols), gap ≤ 10 cols → bat and flies at the hero. It reverts to
   humanoid when within 2 cols of the hero on the same storey (costs its turn).
   **Cheap definition (RANGED-SPEC 2026-10-29; replaces the walk-path test):** `gap ≤ 10`
   (box gap in cols, as for shots) **and** either the hero is on the other storey (standing
   or mid-ladder), or the same storey with a **cut between** them: a scan of the gap cols
   finds a hole in the floor row `9s+8` (narrow or wide pit: a walker cannot jump) or a
   `TF_SOLID` cell in the standing row `9s+7` (mid-room block). Same scan routine as the
   ranged wall scan, other row. No path search. Revert: gap ≤ 2, same storey, and the
   humanoid box at its x is legal and standing (over a pit it stays a bat until it is not).
3. Otherwise humanoid chase and bite.
Flying over a pit is fine (flyer rules); on a ladder it cannot attack, as for any body.
Bosses never follow, so the Lord's bat form stays in its lair.
**Ogre:** a SLAM turn plays RAISE → SLAM.
**Death Knight:** a parry plays BLOCK and prints `PARRIED`.

**Boss guard (BOSS-GUARD; user 2026-10-29: the boss is always generated near the level exit and
tries to protect it; rules designer decision 2026-10-29).** Applies to every lair boss of D1–D7
(golden bosses, Ogre, Death Knight). D8's Archmage: spawn rule G1d only (it never walks).
- **Grate:** shut (`T_GRATE_SHUT` 13, solid floor) while the boss lives; its death sets
  `LF_GRATE_OPEN`, swaps the 3 cells to `T_GRATE` 26 and logs `A GATE GLEAMS. THE WAY DOWN.`
  (the existing B12 string moves from "first entry" to "the gate opens"). First lair entry
  while the boss lives logs `THE GATE IS BARRED.` (concept-screen §3.3 #4; +20 B text; cut
  first if text bytes are short). DOWN at `x == c` on the shut grate: illegal, no turn (F4).
  The boss is mandatory: no descent past a living boss (uniques and the BAL1 curve depend on it).
- **G1 Post.** `P = (storey 1, x = c)`, `c` = `RD_EXITCOL` of the lair: the boss stands **on the
  grate** (3-col body `c..c+2`, 4-col body `c..c+3`; `c ∈ 5..24` keeps both inside cols 5..27).
  The level-exit shaft is exempt from the §9.4.3 "shaft footprint ±1" exclusion (nobody arrives
  through it); every other legality test holds. Facing at spawn: toward the hero.
  - **G1a Arrival gap:** if the hero arrives on storey 1 and the body gap to his arrival box is
    < 5 cols, the boss spawns shifted away from the hero, 1 col at a time, until the gap is 5
    (worst case 5 cols, e.g. `c` = 24 with the hero at x 28). It then walks to `P` by G2.
  - **G1b Escort:** storey 1, shoulder to shoulder on the **lair-door side** of the boss (door
    side from the lair edge in `EDGE_TAB`): `x = bx − 1 − we` (door left) or `x = bx + wb + 1`
    (door right), `we`/`wb` = body widths in cols. Illegal by §9.4.3 (ladder box, arrival box,
    arrival gap, wall) → the other side → the normal 8-try placement (spawn stream, as today).
    Flyer escorts use the same `x` inside their storey-1 band.
  - **G1c Re-entry:** a banked boss (exact hp) and escort are re-placed by G1/G1a/G1b, never by
    the random rule. Pure function of (`c`, widths, door side, hero arrival): Python
    (`tools/levelgen.py` `lp_enter`) == Z80; no new RNG draws.
  - **G1d D8:** the Archmage spawns on the storey of the sealed lair↔Sanctum edge at `x = 5`
    (Sanctum left) or `x = 24` (right), with G1a. The Sanctum door is its "exit". No leash: it
    never walks; its teleport rule is unchanged. D8 has no level exit.
- **G2 Guard AI** (the boss slot only; inserted in `ai_monster` **after** the attack rules
  (melee in reach; ranged rule 2 shoot / Archmage rules) and **before** any movement rule):
  - **Engaged** iff the hero is **standing on storey 1** (not mid-ladder) **and** (`|hero_x − c|
    ≤ R`, **R = 8**, or the boss is **PROVOKED**). Engaged → its normal rules (chase, SLAM,
    parry, Necro step-away), anywhere on storey 1.
  - **Not engaged** → go home: `x ≠ c` → one step toward `c` (the walker step, blocked → wait);
    `x == c` → wait, facing the hero. Never climbs (the golden Goblin King loses climbing in
    its lair), never follows (§8.6). A ranged boss (golden High Necromancer) still shoots from
    the post by rule 2 (its r8 ≤ R, so in practice when the hero is inside the leash).
  - **PROVOKED** (1 bit per slot, engineer's choice, e.g. a spare `E_GOLD` bit): set when the
    hero's damage (melee, ammo, spell, burst) reaches the boss; cleared at spawn (so leaving
    the lair resets it; banking drops AI state anyway). Why: without it a bow (r14), Firebolt
    (r12) or Lightning (r28) kills a boss parked at its post from outside R for free.
  - **Statuses:** ASLEEP/FEAR immune (unchanged); FROZEN/STUNNED skip the action as for anyone;
    CONFUSED wanders as usual and the next clear turn resumes G2. Vampire Lord: flee (rule 1)
    as before; the close-distance rule (rule 2) is **off** for a guarding boss; a Lord left on
    storey 0 after its bat flight uses its ordinary chase there (rare; it cannot climb back).
  - **Hero on the grate:** he is inside R, so the boss attacks him. If the boss dies while the
    hero stands on the grate, the grate opens under him (walkable, no fall); DOWN descends.
  - The escort has **no leash**: it is an ordinary monster (may chase, may follow on exit).
- **Cost (estimate):** guard decision + home step in R6 behind far6 ≈ 45 B, hook in
  `ai_monster` (bank 3) ≈ 8 B, PROVOKED set in the monster damage path ≈ 10 B, lair placement
  (G1–G1d) in R6 ≈ 55 B → **≈ 120 B (R6 ≈ 100, bank 3 ≈ 18)** + 20 B text. Ticks: input tick
  only; non-boss slots pay one flag test (≈ 20 T); the boss ≈ 0.3k T (far6 + compare) + the
  existing step. No per-frame cost; golden glow's stationary path (§8.6) becomes the common
  lair case (already budgeted).
- **Tests:** placement sweep Python == Z80 (boss `x == c` or the G1a shift with gap exactly 5;
  escort side/fallback; never overlapping ladder/arrival boxes); hero on storey 0 for 20 turns →
  boss stays/returns to `c`; storey 1 at `|dx|` 9 → holds, 8 → engages; a ranged hit from 12
  → chases past R, hero climbs → returns home, comes down → chases (still provoked), leave and
  re-enter → unprovoked at `P` with exact hp; boss killed on the grate → tiles 13→26,
  `LF_GRATE_OPEN`, DOWN at `c` descends, before that DOWN is refused with no turn; D8 Archmage
  at the seal side; `tests/ai_equiv.py` A/B with no boss in the room = 0 mismatches.

**Idea (not scheduled; designer note 2026-10-13): monsters drink potions.** Shape if built:
only **Goblin, Orc, Necromancer** (hands, opener-humanoids); at spawn 1 in 4 carries **one
Heal potion** (1 bit in the spare `ENT_STAT` byte 3, beside the Vampire's fled bit). First-match
rule 0: hp ≤ ⅓ max and it has a potion → drink (whole turn, +10 hp to max, `+n` green number
§6.5, `$44` attr flash, `THE ORC DRINKS A POTION`); killed before drinking → the potion
drops (normal floor-list entry, identified as Heal). Bosses never carry one.
- **Pros:** WazHack-like "monsters use items"; a readable tell and a choice (burst it down
  before it drinks, or let it waste the turn); turns the potion drop into a visible reward;
  gives the new `+n` numbers a monster use beyond the Vampire.
- **Cons:** longer fights at D4–D7 where Orcs are already the attrition wall (§10); stacks with
  Vampire self-heal to make "heal" a common monster trait; one more source of loot variance
  (a drunk potion is a lost drop); a test hook (`SEED_FIXED` carry flag) is needed.
- **Cost:** ~120–160 B code (bank 2 rule check ~40 B hot, drink/drop/message via `far3`),
  1 bit per slot, 1 string (~24 B). No art (attr flash), no new frame, no layout change.
- **Recommendation: yes, but not before playtests of the finished 3D/3E balance.** Schedule it
  in 3F alongside monster tiers (§9.6) if playtests report mid-depth fights as samey or too
  short; drop it if they already run long. It needs the 3E potion item record and D3-11 `+n`
  numbers in place first.

### 9.3 Encounter cap (budget §4 + E0; projectiles included)

- Render budget for a non-input tick ≈ 114k T. Contended cost after the double buffer:
  tall 27.7k, medium 18.9k, small ~12k, projectile 8×8/16×8 ~4–5k, 16×16 impact ~7k.
- **Weights (≈ 6k T per unit):** small 2 · medium 3 · tall 5 · **ranged shooter 6** (5 + its
  in-flight projectile) · Ogre 6 · **golden +1**.

| Rule | Value |
|---|---|
| **Phase 2** (monsters + their projectiles) | room **Σ weight ≤ 12 and ≤ 4 monsters**, current room, alive, incl. pending → ≤ 72k + hero idle |
| **Phase 1** (hero action + its projectile/impacts + reacting targets) | hero ~30k + projectile ~5k + impact ~7k + 1 reacting tall ~28k ≈ 70k. Lightning piercing several targets staggers the reactions by impact tick. A rare overlap → one 3-frame tick (no flicker with the double buffer) |
| Initial population | Σ ≤ 8 per room; start room 0; lair = boss + ≤ 1 escort, Σ ≤ 12. Applied at the **first-entry spawn** (§9.4.3, lazy population user 2026-10-06), not at generation |
| Enforced at | room-entry spawn (§9.4.3), follow admission (prototype §3.7 step 3, after residents spawn), summons, fear/teleport arrivals, trickle into a record (§9.5) |
| Projectile tracks | ≤ 3 at once (queued beyond) |
| Overrun | presentation-only 3-frame tick; logic unaffected |

Followers: prototype §3.7 + this cap. **Bosses never follow.**

**Level descent: nobody follows (designer decision 2026-10-04).** The follower rule covers
room exits only. On EX_LEVEL every monster of the old level is discarded, adjacent or not;
no PENDING entries carry over. All room records and the level budget are rebuilt (§9.4.1). The new level is generated with its normal §9.4 population,
start room 0 monsters, and the usual §9.5 respawn and trap/arrival rules. The DEPTH card is
a clean break. Rationale: it keeps the §9.3 cap and the slot budget trivially valid at
arrival, and it makes descending a valid escape.

### 9.4 Per-level population (≤ 4 kinds + boss; hero + ≤ 15 slots)

| Depth | Kinds | Monsters (incl. boss) | Boss |
|---|---|---|---|
| D1 | Rat, Bat, Slime, Goblin | 11 | Golden Goblin King |
| D2 | Goblin, Spider, Bat, Rat | 12 | Golden Spider Queen |
| D3 | Skeleton, Vampire, Ghost, Bat | 12 | Golden Vampire Lord |
| D4 | Orc, Rat, Spider, Skeleton Archer | 13 | **Ogre Warlord** |
| D5 | Mummy, Skeleton, Skeleton Archer, Spider | 13 | Golden Pharaoh |
| D6 | Vampire, Ghost, Necromancer, Orc | 14 | Golden High Necromancer |
| D7 | Orc, Necromancer, Ghost, Necromancer (two Necro entries, ARCHER-DEPTHS H1) | 14 | **Death Knight** |
| D8 | Necromancer, Skeleton, Ghost, Vampire | 10 + Archmage (+ ≤ 2 summons) | Archmage |

**D7 pool (ARCHER-DEPTHS H1, user 2026-10-29).** `LP_KINDS` D7 = {Orc, Necromancer, Ghost,
Necromancer}; `LP_KINDS[rnd & 3]` stays a 2-bit pick, so the Necromancer is drawn 2 in 4
(Orc 1/4, Ghost 1/4). The Necromancer weighs **6 = the Archer's 6**, so Σ, `SIGMA_INIT[7]` and
`minW` (Ghost 3) are unchanged; the §9.4.3 fallback scan simply meets the Necro twice (index 1
then 3; harmless). The pool loads the Necro once (kinds are de-duplicated when the pool is
built; engineer confirms the builder skips a repeated kind).

**Lazy population (principle: user 2026-10-06; details: designer decision 2026-10-06; plan
task LP).** A level stores no monster list. It stores a **budget** (count, kinds, per-room
max) and a small **record per room**; monsters occupy entity slots **only while the hero is
in their room**. They are spawned in the room build when the hero enters. This replaces
prototype §3.7 "Persistence" (all monsters permanently in the slots) and the 3B fixed
per-room stand-in table (§1.4).

#### 9.4.1 Level budget (built at level generation, `GEN_RNG`, after traps)

Placed after traps, so every earlier generator output stays byte-identical (Python == Z80).

| Field | Value |
|---|---|
| `LP_KINDS[4]` | the depth's 4 kinds, in the table order above (tiers are rolled at spawn) |
| `LP_BOSS` | boss kind row |
| `LP_TOTAL` | the table count incl. boss (tests/levelcheck only) |
| `LP_LVL` | hero `LVL` at level entry (the §9.6 tier input for the whole level) |
| `LP_RESPAWNS` | trickle spawns this level (§9.5 `RESPAWN_MAX`) |
| `LP_DISCARD` | units lost to the split or to the Σ cap (tests only) |
| `ROOM_MAX[d]` | constant: **D1–D2 = 2, D3–D8 = 3** monsters per room (initial population) |

**Split (quota per room).** `N = count − 1 (boss) − 1 (escort)`, so D1 = 9 … D6/D7 = 12, D8 = 9.
`R` = present rooms except the start, the lair and the Sanctum (|R| ≥ 5).
1. If `N ≥ |R|`, every room in `R` gets 1. Otherwise the `N` rooms farthest from the start
   (BFS distance; ties go to the lowest id) get 1.
2. Each remaining unit: a weighted pick over the rooms in `R` with quota < `ROOM_MAX[d]`,
   weight = BFS distance from the start (≥ 1). If no room is eligible, the rest goes to
   `LP_DISCARD`. With these counts that never happens (worst case D2: 10 = 5 × 2).

The start room gets 0. The lair gets boss + 1 escort (§9.4.4). The quota is stored as the
room record's count (FRESH). No kinds are chosen at generation.

**D8 (3F-D2, designer 2026-10-28, confirms T4):** `LP_TOTAL` = 11 (10 + Archmage; summons
never count), `N` = 11 − 1 − 1 = **9**, the Sanctum's quota is **0** and it is never in `R`.
`LVL_NROOMS` counts every present room **including the Sanctum** (D8: 8–9); it is a room with a
record like any other, always empty of monsters.

#### 9.4.2 Room record (option b: exact survivors)

Per room: state `FRESH | VISITED`, a count 0–4, and up to **4 entries** = {kind row (tier
included), **exact hp**, `F_RESPAWN`, the Rabbit Rat "bred" bit}. A FRESH room's count is
its quota and it has no entries yet. Fields, not bytes: about 9 × 9 B + `ROOM_VISITS[9]` + the
header ≈ **100 B**. The engineer lays it out in `memory-map.md`.

**On leave**, every monster slot of the old room is handled as follows, except admitted
followers:
- If it is alive and not summon-made, it is **appended** to the record with its current hp.
  Position, facing, AI state, statuses and PENDING are dropped.
- The slot is freed. The record becomes VISITED.
- **Summon-made monsters** (Archmage and Bone Caller summons, Rabbit Rat offspring) are
  discarded, not banked.
- **Dead monsters are never written**, so they never return. The only way back is the §9.5
  trickle.

Why not (a) "bank survivors into the level budget, full hp": leaving and coming back would
heal monsters and reroll their kinds and tiers. That is two exploits: leaving to heal, and
leaving to turn a tier-3 monster into a base one. Option (b) costs ~80 B.

Accepted residue:
- Positions are re-placed on re-entry (at least 8 cols away, §9.4.3).
- Statuses are lost both ways (a poisoned monster recovers; a frozen one thaws). Admitted
  followers keep theirs (§6.4.2 R3).

#### 9.4.3 Spawn on entry (room build, `GS_TRANSITION`, before the scroll)

**Order:**
1. Bank the old room (§9.4.2). Keep the follower candidates aside.
2. Spawn the destination's residents.
3. Admit the candidates (prototype §3.7) against the **real** resident count and the §9.3
   cap. Rejected candidates are appended to the old room's record.
4. `ROOM_VISITS[r] += 1`. This happens after the spawn, so the first visit uses 0.

**Spawn stream.** A local generator (the same algorithm as `GEN_RNG`, its own state) seeded
from `f(level seed, room id, ROOM_VISITS[r])`. `RNG_STATE` (combat) and `GEN_RNG` are
untouched. A room's first-visit contents therefore do not depend on the order in which rooms
are visited.

**FRESH room**, repeated `quota` times:
- kind = `LP_KINDS[rnd & 3]`, then the §9.6 tier roll (with `LP_LVL`, from the spawn stream).
- **Reservation fit (designer decision 2026-10-06, replaces "try the others, else lose").** Let
  `SIGMA_INIT[d] = max(8, ROOM_MAX[d] × lightest LP_KINDS weight)` (D1–D4 = 8; D5–D8 = 9 if the
  lightest kind weighs 3), `minW` = the lightest weight in `LP_KINDS`, `left` = units still to
  roll after this one. A kind is accepted only if `Σ + w + left × minW ≤ SIGMA_INIT[d]`. The
  rolled kind (with its tier roll) is tried first; if rejected, the other `LP_KINDS` in list
  order at base tier; the lightest kind always passes. **Exact fallback order (3F-D2, designer
  2026-10-28, matches T4):** (1) the rolled kind at its rolled tier; (2) the **same kind at base
  tier** (only differs in weight for the Goblin Slinger, 4 → 3; for every other tier it fails
  again and costs one compare); (3) the other `LP_KINDS` indices **0, 1, 2, 3 ascending, skipping
  the rolled index**, base tier. First accepted wins. No RNG is drawn in (2)–(3). A unit is therefore **never lost**
  (`LP_DISCARD` stays 0, and levelcheck asserts it); the cost is a mild bias to light kinds in
  rooms that rolled heavy. Order-independent, no extra RNG steps. Lair: unchanged (cap 12,
  boss + escort).

**VISITED room:** the entries are recreated in order, with their stored kind, hp and flags.

**Placement**, per monster: up to **8 candidate cells** from the spawn stream; the first legal
cell wins. Legal means:
- the §9.5 placement rules hold: walker on a floor-standing cell; not a ladder, pit or door
  cell; not in a ladder-end box; not occupied; flyers inside their band;
- it is **not inside any arrival box** of the room: cols 1–4 and 27–30 on a storey with a
  horizontal exit, and every shaft or up-exit footprint ±1 col;
- on the hero's arrival storey, there is a **body gap** to the hero's arrival box: **≥ 8 cols on
  tries 1–4, ≥ 5 cols on tries 5–8** (designer decision 2026-10-06; 5 is still outside the
  3-wide arrival box plus one melee reach and the hero's first move).

**Other-storey retry (designer decision 2026-10-06).** If a candidate fails *only* the arrival
gap test, re-test the **same x on the other storey** before spending the next try (no new RNG
step; the storey bit of the stream is then used only for the first test). The test is cheap and
the other storey has no gap rule. Tries stay at 8, so the worst case cost is unchanged.

If no cell is legal, the monster stays in the record (a FRESH unit becomes an entry) and is
retried on the next entry. Nothing is lost, and arrival-conflict PENDING never applies to
residents.

Created monsters have full hp (FRESH) and the generator's initial state, and they face the
hero. **Full hp = depth-scaled (3F-D2, designer 2026-10-28; §9.1, §9.7 R1):** `hp = row hp +
(d − 1)` for base and tier rows alike; a golden boss `hp = 2 × (row hp + d − 1) + 6`. Every
path that writes or creates hp uses this value: FRESH spawn, lair boss + escort, trickle entry
(§9.5), summons, breed. A stored record hp is never re-scaled on re-entry (it is already
scaled). The 3B/LP stand-in path that stores unscaled row hp is a **bug**, fixed in T5. atk
scaling (`+ (d − 1) div 3`) is applied at creation from the row, never stored in the record. A teleport into a room (trap or scroll) is an entry with no followers; its arrival
point is the teleport cell.

**Cost (revised 2026-10-06 after LP measurement: mean 20k, worst 38.6k T; 3F-D3 2026-10-28:
real 3F weights measured worst 44.4k).** **Accepted: mean ≤ 20k (≤ 22k with 3F weights),
worst ≤ 46k T once per transition (3F-D3; was 40k).** 46k T is 0.66 of a 50 Hz frame, on a frozen screen
already paying ~45k room build + 100–130k decor, so it is under 25% of the transition. No
tick budget is used and the pool is not touched. Do not add tries to chase fewer waits. A
wait is cheap (the unit is retried on the next entry) and a few missing monsters on first
visit is acceptable. Target: waits ≤ 15% of first-entry units (3F-D3 2026-10-28; the old 8%
was never met: 11.8% pre-3F, 12.1% with 3F weights). Not a task; revisit only if the
levelcheck figure exceeds 15% or a playtest shows visibly empty first rooms.

#### 9.4.4 Lair and bosses

- **Created on the first lair entry:** the boss (`LP_BOSS`) plus 1 escort (`LP_KINDS[rnd & 3]`,
  base tier, never tier-rolled), within Σ ≤ 12. ~~The boss takes the legal cell farthest from
  the hero.~~ **Placement = the guard post (§9.2 "Boss guard", BOSS-GUARD 2026-10-29)**, on
  every lair entry (first and banked); it draws no spawn-stream step.
- **Banked like any room:** the boss's **exact hp persists** and it does not regenerate. The
  escort is banked too.
- A summon next to the hero follows him like any follower (user ruling 2026-11-01: let them follow, also into the Sanctum); summons that do not follow are discarded when the room is left (their cooldown resets).
- The boss never follows. It guards the exit (§9.2 "Boss guard"). Its death sets the
  boss-dead flag: the grate opens and the trickle stops (§9.5).
- **D8 sealed edge (3F-D2, confirms T4 and memory-map `EDGE_TAB`):** the lair↔Sanctum edge is
  `EG_LINK | EG_DOOR | EG_SEAL` (a sealed door is a door: door cells, planks, door collision;
  `EG_SEAL` only overrides opening, like `EG_LOCK`). Never `EG_LOCK`, never `EG_OPEN` at
  generation.

#### 9.4.5 Hard ceilings

- **Slots:** hero + 15 stays the ceiling. In practice only the current room's monsters,
  pending followers and summons hold slots, so ≤ 4 by the §9.3 cap.
- **Invariant:** after every transition, every active non-hero slot has `room = CUR_ROOM`.
- 3D projectile and FX tracks are render-only and use no slots.
- Shrinking the slot array is possible later, as an engineer + manager decision. It is not
  part of LP.

#### 9.4.6 Sprite pool

The pool holds only `LP_KINDS` (tiers share base frames), `LP_BOSS` and the §11.3 extras
(Vampire bat form, Archer HURT/DEAD). Every spawn path (entry, trickle, idle wave, breed,
summon, fear/teleport arrivals) creates only those kinds, so the engine can build the pool
per level from `LP_KINDS` + `LP_BOSS`.

**Fix:** the Bone Caller summons a base **Skeleton if Skeleton ∈ `LP_KINDS`, else a base
Ghost**. D6 and D7 have no Skeleton set (§11.3).

**Hero-dependent projectile extras (3F-D2, designer 2026-10-28; T1 open issue).** Monster
projectiles reuse the Warrior's class-FX frames, which a Mage run does not load (`K_FXW`).
So on a **Mage** run only, the level pool adds:
- **Archer levels (Skeleton Archer ∈ `LP_KINDS`: D4, D5; D7 dropped by ARCHER-DEPTHS H1):** `arrow_fly1/2` (16×8,
  stationary) = **≤ 128 B pool** (2 frames × 32 B source × 2 facings), 0 new source, 0 new fid.
- **Goblin levels (D1, D2; the Goblin Slinger's rock):** `dagger_spin1/2` (8×8) = **≤ 64 B**.
- **Not** `arrow_hit`: a Mage hit by an arrow shows his hurt reaction only (as the DART, §1.5).
The two sets never share a level, so the extra is **≤ 128 B**, on D4/D5 only; D5 is the
pool-limiting level (§9.7), so the engineer re-checks `POOL_NEED` for Mage D5. Warrior runs
add nothing (already resident).

#### 9.4.7 Test hooks (`SEED_FIXED`)

- **Levelcheck (Python, seed sweep):** the start quota is 0; each quota ≤ `ROOM_MAX`;
  Σ quotas = N; `LP_DISCARD` (split **and** Σ fit) = 0 on every seed.
- **Spawn reference (Python == Z80):** for the inputs (seed, room, visits), the list of
  kinds, tiers and x/y.
- **ZRCP checks:**
  1. A FRESH room's slots equal the reference.
  2. The slot invariant (§9.4.5) holds after every transition.
  3. Damage a monster, leave and re-enter: the same kind and hp, and the same count.
  4. Kill one, leave and re-enter: the count is −1.
  5. The same snapshot with the same inputs gives identical spawns.
  6. A different room-visit order gives the same first-visit contents.
  7. No resident spawns within 8 cols of the arrival on the arrival storey, or in a
     pit/ladder-end/door/arrival cell.
  8. The boss's hp is unchanged across leave and re-enter.
  9. Summons are gone after re-entry.
  10. The trickle changes only VISITED records, never slots, and stops after the boss's
      death (§9.5).

#### 9.4.8 D-AI1 playtest notes (designer 2026-10-13; NOTED, not scheduled)

The user reported four monster-movement issues in playtest. These are the designer's rulings for
when the work is picked up. Nothing here is built yet, and the current rules stay in force until it is.

**(a) Shared cells: no.** §6.1 "body boxes never overlap" stays. Reasons: (1) clash, because a shared cell
shows only the last-drawn ink (§4.2 prototype); (2) cost, because each overlap forces an overlap-repair
re-blit, the most expensive render path (A7b); (3) rules, because "nearest body in line", reach, the
target readout and anti-cork all assume one body per box. The turn model already resolves moves in slot
order, which acts as a reservation, so a separate reservation table adds nothing. Pushing is rejected
(chain pushes, wall cases). **Swap** is allowed in one case only, the ladder deadlock in (b). PENDING
bodies stay the only legal overlap.

**(b) Ladder deadlock: priority yield, with a swap after a timeout.** Typical case: walker A at the foot
wants to go up, and walker B in the far-end box wants to go down. The "no head-on climb" rule (prototype
§6.4 walker 3) makes both wait forever. Ranked options:
1. **Chosen: right of way to the lower slot id.** A climber that waits because of a lower-slot climber
   which occupies or targets the same segment steps 1 cell out of the ladder-end box. It uses the
   prototype §6.4 rule 2 side order (facing side first, then the other side). It must not re-enter that
   box while the other climber is mid-ladder on the segment. No RNG is used.
2. **Backstop: a timeout swap.** A monster blocked by the same body on 2 consecutive turns at a ladder
   end swaps cells with it. This is the hero's squeeze rule (prototype §6.4) applied monster-to-monster.
   It guarantees that no ladder stays jammed.
3. Rejected: ignoring collision on ladder cells. That reintroduces the overlap ruled out in (a), and it
   breaks the snap and line-of-attack rules.

Cost: a 2-bit wait counter per slot (the spare bits in `ENT_STAT` byte 3), about 80–120 B of bank-2 AI
code, and nothing per tick. The rule runs only on a turn when a climb start is refused. Risk: low. It
needs a seeded ZRCP case with two climbers placed head-on.

**(c) Hero descending onto monsters below.** By the rules this should not happen: prototype §6.4 rules
2–3 cover the whole remaining path, including the standing box at the foot. If the hero overlaps a
monster there, it is a §6.1 violation, not a design trade-off. Ranked options:
1. **Cheapest: find why rule 2 misses the monster.** The likely cause is a filter by storey or
   `storey_ref` that skips monsters of the lower storey. Fix the filter. Cost is near zero.
2. **Guarantee: a landing shove.** If a body still intersects the foot box when the hero takes his last
   rung step, move that body to the nearest free legal cell on its storey. Search ±1…±4 cols outward,
   facing side first. Flyers stay in their band, and B16 PENDING is the fallback. If no cell is free, the
   hero's step becomes a wait, and the existing squeeze swap resolves it on the next turn. Cost: about
   60 B, no RNG.
3. Rejected: an arrival offset, or the hero landing on the nearest free cell. Either one breaks the snap
   invariant (prototype §3.4) and the vertical-arrival contract (`x = col`).
4. Rejected: attack on arrival. It breaks the "no combat on ladders" rule and gives monsters free hits.
5. Keeping the overlap is the fallback only. It causes clash, ambiguous targeting and the repair cost
   from (a).

**(d) Re-entry continuity.** Monsters seem to jump because §9.4.2 drops positions and §9.4.3 re-places
them ≥ 8 cols from the arrival. They seem to vanish because a placement wait leaves the unit in the
record. Ranked options:
1. **Chosen: store each banked monster's position.** Add 1 byte per record entry: x (5 bits), storey
   (2 bits), facing (1 bit). That is 36 B for 9 × 4 entries, and the room record grows to about 136 B.
   On re-entry, the stored cell is **try 0**: it is used if it passes the §9.4.3 legality and arrival-gap
   tests. If it fails, tries 1–8 run unchanged. Try 0 draws no RNG, so FRESH spawns and the
   Python == Z80 reference stay identical. A flyer returns at its band default y. A VISITED entry whose
   9 tries all fail goes **PENDING in place at its stored cell**, instead of waiting in the record. So a
   banked monster can no longer vanish. Cost: about 40 B code plus 36 B data. Re-entry gets cheaper on
   average, because try 0 usually wins.
2. **Chosen too: a "waited by the door" touch.** When a monster that was chasing is banked (a rejected
   follower, or awake within 8 cols of the exit), store its x clamped to the exit side, just outside the
   arrival box. Try 0 then fails the gap test on the arrival storey only. On re-entry it reads as "it
   waited for you". Cost: about 20 B.
3. **Not chosen: every monster that noticed the hero follows.** The caps make it hollow: ≤ 4 monsters,
   Σ ≤ 12 and ≤ 2 tall per room (§9.3), and ≤ 2 per exit, so most "noticed" monsters would be rejected
   anyway. Where it did work, it would remove escape by exit, which is the main fleeing tool apart from
   descent (§9.3). It would also queue several PENDING bodies on one edge cell, so the follow-in would
   take 4+ hero steps. A milder version is acceptable if playtests still want more pursuit: widen
   candidate rule 1 from gap ≤ 4 to **gap ≤ 6 and awake/chasing**, and keep the 2-per-exit and §9.3 caps.
   Cost: a few bytes. It changes balance (§10 fleeing), so it needs the user's approval.

What persists across leave/re-enter after (d)1: kind, tier, exact hp, flags and now position/facing.
Statuses are still dropped (§9.4.2), and AI state resets to "awake and facing the hero". Respawning
on leave stays rejected (the heal and reroll exploits, §9.4.2).

**Engine work, cheapest first:** (c)1 bug hunt → (d)1+2 record byte and try 0 (record layout in
`memory-map.md`, the Python spawn reference, ZRCP #3 extended to check the same x/storey) → (b) priority
yield and swap → (c)2 shove. (a) needs no work.

### 9.5 Respawn trickle

Implemented in 3F. Tags: **U** = user 2026-10-03, **D** = designer decision 2026-10-03.

**Rule (U).** While the level boss is alive, the level slowly refills. The trickle stops
permanently the turn the boss dies (the flag is not re-armed on revisit or reload).

**Constants (D, named, tuning knobs).**

| Name | Value | Meaning |
|---|---|---|
| `RESPAWN_PERIOD` | 48 | check every 48 turns **of the level** (a per-level count reset on level entry; a turn whose end_turn makes a queued spawn does not count; manager ruling 2026-10-31, T12) |
| `RESPAWN_CHANCE` | 96 (of 256) | ≈ 38 % per check, so about 1 spawn per ~128 turns, ~3–4 per 450-turn level |
| `RESPAWN_XP_DIV` | 2 | XP awarded = `KXP` (§4.1) / 2, rounded down, min 1 |
| `RESPAWN_ITEM_W` | 2 | room weight = 1 + 2 × (un-picked floor items in the room), capped at 7 |
| `IDLE_WAVE` | 0 | build flag, default **off** (see below) |
| `IDLE_TURNS` | 60 | idle-wave trigger |
| `IDLE_WAVE_MAX` | 2 | monsters per wave: 1 + (rnd & 1) |

**Lazy population (designer decision 2026-10-06, §9.4.2).** The trickle **appends an entry
to a room record and never touches the slots**. The entry has a rolled kind, a §9.6 tier
(gameplay RNG), full hp and `F_RESPAWN`. The monster is placed by §9.4.3 on the hero's next
entry, so the "Placement" rules below now apply through §9.4.3. The trickle adds to the
records; it does not draw from the generation budget `N`. A hard cap
**`RESPAWN_MAX` = 6 per level** (`LP_RESPAWNS`) applies. Only **VISITED** rooms are eligible,
because a FRESH room already holds its quota. The idle wave spawns straight into slots (it
is the current room) and is banked on leave like anyone.

**Hard limits (U).** A spawn is skipped (no retry until the next check) unless all hold:
1. The target room is VISITED, its record has < 4 entries, and `LP_RESPAWNS < RESPAWN_MAX`
   (replaces "free slot", user 2026-10-06 lazy population).
2. The target room satisfies the §9.3 cap with the new body added (Σ weight ≤ 12, ≤ 4
   monsters, counted from the record). Initial-population Σ ≤ 8 is not applied.
3. The target room is not the hero's current room and not the room the hero just left (the
   previous room, for the turn after a transition and until the hero enters a third
   room; `prev_room` is updated on every room change).
4. The room is not the boss lair (a lair holds boss + ≤ 1 escort, Σ ≤ 12, never topped up),
   and not the D8 Sanctum (3F-D2).

**Room choice (U + D).** Eligible rooms = all rooms passing 2–4. Pick one by weighted
random using the weight above (rooms with un-picked items preferred; every eligible room
has weight ≥ 1, so the fallback is automatic). No eligible room = skip.

**Kind (U + D).** Uniform over the level's own ≤ 4 kinds (§9.4), never the boss, an escort
unique, a summon or any `unique` kind. If the picked kind would break the cap, try the
next kind in the level's list once (cheapest-first not needed), else skip.

**Exact check and RNG draw order (3F-D2, designer 2026-10-28; confirms T4; Python == Z80).**
All draws are on `RNG_STATE`. Steps 1–4 draw nothing, so a check with no eligible room leaves
the RNG untouched.
1. The level's turn count (reset on level entry; turns that run a queued spawn are not counted) reaches
   `RESPAWN_PERIOD`, else stop. The check itself runs on the next idle input tick (engine timing, T12).
2. Boss alive (boss-dead flag clear) and `LP_RESPAWNS < RESPAWN_MAX`, else stop.
3. Build the eligible set: rooms `r` in **ascending id**, `r` present, VISITED, record entries
   < 4, `r ≠ CUR_ROOM`, `r ≠ prev_room`, `r ≠ LVL_LAIR`, `r ≠ LVL_SANCTUM`, and
   **`Σ(record weights) + minW ≤ 12`** where `minW` = the lightest **base** weight in
   `LP_KINDS` (record weights include tier and golden +1). Weight `w_r = min(7, 1 + 2 × items_r)`.
4. Set empty → stop.
5. **Draw 1, chance byte:** `rnd8 ≥ RESPAWN_CHANCE` → stop.
6. **Draw 2, room:** `rnd(Σ w_r)` (the shared range helper used by the §9.4.1 weighted split),
   walk the set in id order subtracting `w_r`.
7. **Draw 3, kind:** `k = rnd & 3` (as §9.4.3). **Draw 4, tier:** the §9.6 roll for
   `LP_KINDS[k]` with the **current** `LVL` (one byte, drawn **only if the kind has tiers**,
   exactly as §9.6 and the FRESH spawn: Slime, Vampire, Mummy draw nothing; one shared tier
   routine for both paths).
8. Cap check of the tiered kind: `Σ + w ≤ 12` (count is already < 4). Pass → step 10.
9. **One retry:** `k = (k + 1) & 3`, **draw 5, tier** for it (same "only if tiered" rule),
   cap-check. Fail → stop (the
   draws are spent; `LP_RESPAWNS` unchanged).
10. Append {row, hp = depth-scaled full hp (§9.4.3), `F_RESPAWN`}; `LP_RESPAWNS += 1`.
No placement draws: placement is §9.4.3 on the next entry. Eligibility (step 3) uses the
lightest base weight only; the picked tiered kind is cap-checked in 8/9. A room passing 3 can
therefore still refuse both tries (e.g. Σ 9, both picks weigh 5): accepted, a skip.

**Flags (U).** Respawned monsters get `F_RESPAWN`: **no drops** (the death-drop roll is
skipped) and XP / `RESPAWN_XP_DIV`. They are otherwise normal and may follow (prototype §3.7,
subject to the §9.3 cap) like any monster.

**Depth scaling (D).** None: period and chance are the same on every depth. Per-depth hp ×
count already rises ~25 % (§10) and per-kind weights grow with depth, so the cap and slot
limits throttle later depths automatically; a faster trickle would stack on that growth
and break the §10 threat curve.

**Placement (D).** Cell-legal, deterministic from the gameplay RNG (`RNG_STATE`, the
same stream as combat, so a seeded test replays). `GEN_RNG` is overwritten by the trickle (it carries
the draws through the shared tier roll); nothing reads it between level generations: it is reseeded /
saved by level_gen, ig_seed, lp_enter, lp_budget, l2_pass (manager ruling 2026-10-31, T12). Draw up to 8 candidate cells in the chosen room; first legal one wins, else skip:
- Walkers: a floor-standing cell on a storey, not a ladder cell or pit cell, not a door
  cell, not in a ladder-end box (the 1-cell footprint at each ladder end), not occupied,
  and at least 6 columns from the hero if the room is visible.
- Flyers (Bat, Ghost, Vampire bat form not applicable at spawn): a cell inside the kind's
  flight band for the storey (same band as generation), same exclusions, over a pit allowed.
- The monster is created at full hp, in the **idle** state the generator uses for
  initial monsters (wakes when the hero enters its room or on a noise/hit); it takes no
  action on the spawn turn. The room map is not touched; spawning occurs outside the
  hero's room, so there is no render cost and no redraw beyond the normal room entry.

**Idle wave (U, gated by `IDLE_WAVE`, default off; D for details; 3F-D1: not built in 3F, §9.7 R5).** Enable only if
playtesting shows camping (waiting in a cleared room to regen, or farming) is a problem.
- Counter `idle_turns` counts hero turns spent in the same room with **no floor item
  picked up** (a pickup, room change, or learning a book resets it; plain waiting does
  not). At `idle_turns = IDLE_TURNS` the wave fires once and resets the counter.
- Fires only while the boss is alive. Spawns `1 + (rnd & 1)` monsters of the level's kinds
  (as above, `F_RESPAWN`, no drops, half XP) **at the room's doors / exits** (the door
  cells' adjacent floor, or the ladder-end cell if the room has none), awake and
  chasing, as if arriving from the neighbouring room.
- The same slot, §9.3 cap and kind rules apply; each monster that does not fit is skipped
  (a full room produces no wave). It ignores the "not in hero's room" rule, which is
  the whole point, but not the cap.

**Saves and revisits (D).** Levels are regenerated from the seed; respawned monsters exist
only in the room records (§9.4.2) and are not stored in the seed or the level image. Leaving a
level discards them, and a regenerated level restores the original population with
only the boss-alive state as saved. The turn-counter phase, `prev_room` and
`idle_turns` are runtime-only and reset on level entry. A boss-dead flag stops the
trickle for the rest of that visit (and for a regenerated level, because the grate is
then open).

**Tests (3F).** Seeded run: with the cap full or 0 free slots no spawn occurs; no spawn in
the hero's or previous room; no spawn after the boss dies; a spawned monster drops nothing
and awards half XP; same seed and inputs reproduce the same spawns.

### 9.6 Monster tiers (3F; user 2026-10-03 scope, designer decision 2026-10-03 details)

A tier is a **colour variant of a base kind**: the same frames (0 new frame ids, 0 pool), its
own ink, stats and one small ability, and **its own `kind_tab` row**. Rows: 32 − 18 used = 14
free (15 if the Rogue hole, id 2, is reclaimed); **12 tiers** below → 30 used, 2 spare.
Short names ≤ 9 chars (3F-D3: `YOUR DAGGER MISSES THE ` + 9 = 32; final list §9.8 D3-6).

| Base (ink) | Tier 2 | Tier 3 | Stats hp/atk/eva/DEF/dmg | Ink | Ability (mechanic reused) |
|---|---|---|---|---|---|
| Rat (`$06`) | **Giant Rat** | | 5/1/1/0/1d3 | `$02` | bite 1 in 4 → POISON 12 (Spider poison; POIS1 §6.4.3) |
| | | **Rabbit Rat** | 8/2/3/0/1d4 | `$47` | **breeds**: hit and survives → 1 in 4 spawns one base **Rat** in the nearest legal cell (summon code, slot + §9.3 cap; `F_RESPAWN`); once per Rabbit Rat (`ENT_STAT` spare bit) |
| Bat (`$43`) | **Screech Bat** | | 5/2/4/0/1d3 | `$05` | bite 1 in 4 → CONFUSED 2 |
| Goblin (`$44`) | **Goblin Slinger** | | 8/2/1/0/1d4; rock 1d3 PHYS r6 | `$06` | ranged AI as the Archer (cooldown 2); rock = `dagger_spin` frames at `$06`, not recoverable; weight 3 + 1 |
| Spider | **Black Widow** | | 10/4/3/0/1d4 | `$02` | POISON 24 (POIS1 §6.4.3); bite 1 in 4 → **ACID** (armour `m −1`, §8.10; rev 5 replaces ASLEEP 2) |
| Skeleton (`$47`) | **Skeleton Guard** | | 14/3/2/2/1d6 | `$05` | **parries 1 in 4** PHYS hits (Death Knight parry; 0 dmg, `PARRIED`, no BLOCK frame: the hit flash is skipped); a parried melee hit **notches** the weapon 1 in 2 (§8.10) |
| | | **Skeleton Knight** | 18/4/2/3/1d8 | `$44` | parries 1 in 3 (notch 1 in 2, §8.10); hit 1 in 4 → STUNNED 1 |
| Ghost (`$45`) | **Poltergeist** | | 11/3/3/0/1d4 DRAIN | `$03` | touch 1 in 3 → FEAR 3 (replaces the Ghost's confusion) |
| Orc | **Orc Berserker** | | 18/4/0/1/1d8+2 | `$02` | FEAR-immune; **rage**: hp ≤ ½ max → atk +2 |
| | | **Orc Bouncer** | 24/5/1/2/1d10 | `$03` | hit 1 in 3 → STUNNED 1 (a "bouncer" throws you out cold) |
| Skeleton Archer (`$03`, 3F-D3) | **Skeleton Sniper** | | 10/3/2/0/1d4; arrow 1d8 r14 | `$04` | stands its ground (skips the "gap < 3 → step away" rule); Arrows ×3 drop **2/2** (always; Rewards rule below, 3F-D3) |
| Necromancer | **Bone Caller** | | 14/3/2/0/1d4; Dark Bolt as base | `$06` | **summons** one base Skeleton if Skeleton ∈ `LP_KINDS`, else a base Ghost (designer decision 2026-10-06, §9.4.6: D6/D7 pools have no Skeleton) (Archmage summon code: cooldown 8, ≤ 1 live summon, slot + cap; `F_RESPAWN`) |

Untiered: Slime (D1 only), Vampire, Mummy (both already complex), uniques, the Archmage.
Depth scaling (§9.1) applies to tiers as to their base. A tier keeps its base kind's
resistances, movement flags, body, behaviour and weight (except the Slinger's +1).

**Ink rules.** On black paper, one ink per sprite cell (no new clash). Tier inks avoid `$42`
(hit flash), `$46` (gold boss glow), the status tints `$41`/`$45`/`$43`/`$07` (§6.4), and the
base kind's own ink; within one base the tiers differ. Allowed tier palette: `$02 $03 $04 $05
$06 $44 $47` (`$06`/`$47` are static here, so they never read as the cycling gold glow). The
artist's base inks for the new kinds (Spider, Orc, Archer, Necromancer…) must differ from
their tiers' inks; if one clashes, the tier ink moves within the palette.

**Spawn roll (initial population §9.4 and respawns §9.5; bosses, escorts, summons and
breeding are never rolled).** For each monster of a kind that has tiers:
- **Rev 5 (user 2026-10-03: XP replaces `PL`):** hero level `LVL` (§4.1) vs the **expected
  level `LVL_EXP(d) = d`** (§4.1 XP curve). `Δ = clamp(LVL − d, −2, +2)`. One Δ unit is now a
  whole depth of progress (rev 4's `PL` unit was half); the shifts stay 16/8 and are a
  playtest knob (§10).
- Odds out of 256, `T2 = clamp(T2_BASE[d] + 16·Δ, 0, 160)`, `T3 = clamp(T3_BASE[d] + 8·Δ, 0,
  80)` if `d ≥ TIER3_MIN_DEPTH` else 0. Roll `r` (one 8-bit step; untiered kinds draw no `r`,
  3F-D2) (gameplay RNG for respawns; the **room spawn
  stream** for the initial population, rolled at first entry with `LP_LVL`, §9.4.3, designer
  decision 2026-10-06): `r < T3` → tier 3 (if the kind has one, else tier 2); `r < T3 +
  T2` → tier 2; else base.

| Constant | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| `T2_BASE` | 24 | 48 | 64 | 72 | 80 | 88 | 96 | 96 |
| `T3_BASE` | 0 | 0 | 0 | 16 | 24 | 32 | 40 | 48 |

`TIER3_MIN_DEPTH = 4` (D1–D3 never elite), `TIER_SHIFT2 = 16`, `TIER_SHIFT3 = 8`,
`TIER_DELTA_MAX = 2`, `T2_CAP = 160`, `T3_CAP = 80`. A tier counts with its base for the
"≤ 4 kinds" rule (the pool loads base frames only). The initial-population roll uses the
`LVL` at level entry; the levelcheck/population reference takes `LVL` as an input.

**Rewards.** XP: each tier row has its own `KXP` (§4.1 table, ≈ ×1.5 tier 2, ×2 tier 3);
§9.5 halving applies. Drops: the
base drop numerator +1 per tier above 1 (Cheese 1/4 → 2/4 → 3/4; Arrows 1/2 → 2/2); a tier
whose base has no drop drops a random food (Carrot/Apple/Pear) 1 in 4. `F_RESPAWN` still
cancels drops.

**Budget.** `kind_tab` +12 rows (inside the 32). New per-kind arrays (resistances 3, status
immunity 1, on-hit effect 2 [effect+chance, duration], parry 1, tier-up id 1 ≈ 8 × 32 B)
need a **third `kind_tab` page: +256 B bank 2** (the current page has 48 B spare). Code (E):
generic on-hit status apply ~80 B (shared with Spider/Ghost/Mummy/Ogre/Necro, §6.4), parry
by row ~20 B, rage ~25 B, Sniper/Slinger flags ~30 B, breed + Bone Caller via the summon
routine ~100 B (bank 3), tier roll ~70 B (bank 3) → **~0.33 KB**. Names ~130 B raw strings.
Render: **0 per tick** (ink from `KT_ATTR`); turn logic +≤ 0.2k T per hit for the rolls.

### 9.7 3F-D1 memory rulings (designer decision 2026-10-28; architect: 3F ≈ 1.7 KB over, 0.6 KB in bank 2)

**R1 Golden bosses = flag, not rows.** Kind rows stay 18 + 12 tiers = **30**. A golden boss is
its base row + one per-entity golden bit (engineer picks the byte; it implies `BOSS`) and
**`LEK_GOLD` = `LE_KIND` bit 5** in the room record (bits 0–4 row, 6 bred, 7 respawn). Derived
at spawn, not stored per row: hp = 2 × (scaled hp) + 6; atk +2, dmg +1, DEF +1 (applied once at
spawn if the entity carries atk/DEF copies, else one flag test in the hit path, ≤ 25 B, ≤ 20 T);
glow + weight +1 from the bit. Per-depth tables replace the rows: name (5 × ≤ 12 chars, ≈ 60 B
raw, by depth), XP (§4.1 boss list, 8 B by depth), unique drop (§8.6, already by depth). The
golden Vampire Lord's bat form keeps the bit (it glows). Cost ≈ 70 B code + 68 B data, vs 5
rows that do not exist (35 > 32).

**R2 Lectern and closed grate onto freed common ids.** Lectern 2×2 = **15 TL, 16 TR, 17 BL,
18 BR** (contiguous: `id − 15 < 4` is the attackable test), `TF_SOLID|TF_ATTACK`, placed only in
the Sanctum. **`T_GRATE_SHUT` = 13** (`TF_SOLID`). **31 stays free** (spare). Cost 0 B (glyph
bytes overwrite the blank common slots; static flags/attrs); it **deletes** the planned D8 60..63
swap (≈ 40–60 B saved) and D8 keeps item markers like D1–D7. Tileset 8 loses the lectern (4
per-level ids freed). Art: the artist supplies the lectern (4 cells, from tileset 8) and a closed
grate glyph (8 B). Tome hit flash `$43` rewrites the 4 attrs (§1.3 unchanged).

**R3 Climbers.** Only kinds with climb frames climb: **Goblin, Skeleton** (+ their tiers) and the
heroes. **Orc, Skeleton Archer (+ Sniper), Death Knight are walkers, not climbers** (§9.1). 0 B,
avoids +1,152 B pool on D4/D7 (a shared Skeleton climb pair would have to be resident there, and
D7 is the worst level; since H1, §9.8, D7 has no Archer, so this now concerns D4 only). Gameplay: like Ogre/Mummy/Vampire/Necro, a hero on the other storey is
safe from them; the Archer still shoots along its storey, the DK lair fight is unchanged (bosses
never follow). **Orc = 3 frames** (WALK1 = MOT rest, WALK2, ATTACK), HURT = flash, DEAD = the
shared humanoid DEAD (as Mummy; pool spike assumption confirmed). **Superseded (3F-T13bc + user 2026-10-29):** the Orc, Necromancer and Mummy families climb on the shared humanoid climb pair, the Archer / Sniper on the Skeleton's own pair, the Spider / Black Widow on their rest pose (no art); Vampire, Ogre, Death Knight and every boss stay walkers.

**R4 HURT on frame-less kinds** (Spider, Orc, Necro, Mummy, Vampire, Archer, Ogre, DK, Archmage,
golden bosses): the body keeps its current frame and its footprint takes the existing **`$42` hit
flash** for the existing duration (priority §6.4: flash > tints > glow). No new code path.
**ANIM-IMPORT (user 2026-10-29 "ANIMATION ITEMS 1–4 GO" / "ART9 APPROVED"; the flash
alone is not acceptable for these kinds):** real HURT poses (the flash still plays on top):
Spider = its BITE pose (0 B), Skeleton Archer (+ Sniper) = `skeleton_hurt` (in the Archer's
unit). The HURT pose also opens the kind's DEATH sequence (as the original kinds). Walks:
Necromancer (+ Bone Caller / Archmage) B4 `W2, W4, W3, W1` (ART3 `necro_walk4`).
**ANIM-X12 (user 2026-10-30, X1 / X2):** the Orc and the Vampire walk four distinct poses, W2 W1 W3 W4
(`MOVECYC4`; W1 = the rest pose, W4 = the far-leg passing pose, WK0 in the odd slot), both planted feet
step exactly 4 px per tick with equal strides (the old cycle showed W1 twice: a limp / sliding far foot).
+1 frame id each (`orc_walk4`, `vamp_walk4`; 138 of 144), +480 B pool on the Orc / Vampire levels.

**ANIM-IMPORT2 (user 2026-10-30 "40 PX APPROVED" / "ART11 DECISIONS" / "ART12 PICKS"):** the
Warrior, Mage, Skeleton family (+ Archer / Sniper), Orc (V4 Ironhide), Mummy (V2 tomb guard),
Necromancer (V2 bone caster; Archmage / Bone Caller share it in their inks), Vampire (own set) and the
shared humanoid climb pair are drawn **40 px tall** on the unchanged 48-px (6-cell) body: bottom-anchored,
8 px blank at the body top; hit boxes, ladders, doors and the jump swept box are unchanged. Ogre and Death
Knight stay 48 px, the Goblin 32; hero DEAD frames unchanged. Jump = **J-a**: JUMP1 crouch at take-off and
landing, one JUMP2 leap pose on every airborne tick (§2.4 arc table unchanged). Mage HURT = the V3 stagger.

**R5 Cut order if memory still runs out** (cheapest player loss per byte first; E = estimate):
1. Idle wave + `idle_turns`: **stays unbuilt** (0 B, saves ≈ 60 B vs building it). `IDLE_WAVE`
   is dropped from 3F scope.
2. ALARM wave → the 3E behaviour on every depth ("bell rings", border flash, nothing comes):
   **−≈ 130 B** (door-cell spawn + awake set-up). §10 loses ~1 wave/level on D5+.
3. Vampire close-distance rule (§9.2 rule 2, incl. the walk-path ≥ 12 test): **−≈ 110 B**.
   Flee-as-bat stays.
4. Rabbit Rat breed → bite 1 in 3 → POISON 12 via the generic on-hit (0 code): **−≈ 50 B** +
   the bred bit.
5. Archmage teleport (rule 3): **−≈ 80 B**; it becomes a turret (summon, bolt, melee).
   **Superseded by the §9.9 cut order (ARCHMAGE-SPEC).**
6. Data packing (no player loss; bank 2): on-hit = 1 B (effect 3 bits, chance 2 bits ∈ {1, ½,
   ⅓, ¼}, duration index 3 bits → 8-entry table), parry folded into 2 bits of another per-kind
   byte, tier-up = a 12-entry base→tier list scanned at spawn: **3rd page 8 → 5 B/kind, −≈ 96 B
   bank 2**. Turn-only arrays (immunity, on-hit, parry, tier-up, KXP, drop) may live in R6 behind
   `far6` (≤ 0.3k T per hit, 0 render).
7. **Last resort, USER keeps it unless numbers force it:** Death Knight BLOCK → parry as the
   Skeleton Guard (no frame, `PARRIED` text, hit flash skipped). Saves ≤ ≈ 0.5 KB pool now that
   D5 is the max (D7 only drops to D5's level) + ≈ 190 B source.
Not on the list (rules, user-owned): the respawn trickle, tiers, wear, bosses' core attacks.
1–6 total ≈ 0.5 KB, mostly R6/bank 3 code; they close the bank-2 0.6 KB only together with the
R6 move in 6.

**DECIDED (user 2026-10-28): Archer SHOOT has no dedicated art.** The shot plays an existing
cut/cast frame (no new source): **D5** the resident Skeleton cut, **D4** has no resident, so it
loads the Skeleton cut frame alone (D4 has ~8 KB slack and is not the max, so 0 effective cost).
(D7 has no Archer since ARCHER-DEPTHS H1, §9.8.) Saves **768 B pool + ≈ 193 B source**;
**D5 becomes the pool-limiting level**. §11.1 Archer row: 3 ids (Skeleton walk shared), no SHOOT.

**R6 Plan reconciliation.** Plan 3F's "zombie" = **Vampire**, "giant spider" = **Spider** (§9.1;
Giant Rat is a Rat tier). Boss music (cue E entry + cue R on boss death, sound.md) is wired **in
3F** with the bosses (≈ 30 B, tune data already in the AY slot); if bank space blocks it, it is
the first item deferred to 3G.

### 9.8 3F-D3 rulings (designer decision 2026-10-28; T3 kind-row review)

**D3-1 Original rows take the §9.1 values now.** Skeleton DEF 1, Slime DEF 1 and hp 6, Goblin
dmg 1d4, Ghost hp 8. Data-only follow-up to T3 (before T5, so the first Fuse playtest runs on
spec numbers); seeded combat/levelcheck expectations are rebaselined in the same change.
Render goldens should not move (no hp is drawn at spawn); any golden that does move is reviewed,
not blindly accepted. Balance: D1 Goblin +0.5 avg dmg (the §10 sample duel already assumed
1d4); Slime DEF 1 + PHYS R makes the Mage's staff ≈ 1 per hit, but the Slime is D1-only, acts
every 2 and Spark ignores DEF, so the Mage walks away or Sparks it (2 MP). Skeleton DEF 1 from
D3 is answered by PS / Firebolt / Spark. Tuning stays a BAL1 job, starting from the spec.

**D3-2 `lp_enter` ceiling: worst ≤ 46k T, mean ≤ 22k** (§9.4.3). Room-entry work on a frozen
screen, not a tick; no new algorithm. Do not add placement tries.

**D3-3 Waits target ≤ 15%** (§9.4.3). Accept 12.1%; no task.

**D3-4 Skeleton Archer ink = `$03` (magenta, not BRIGHT).** Rejected: `$47` (= Skeleton),
`$05`/`$44` (Skeleton Guard/Knight, same frames on D5), `$04` (its Sniper), `$06` (= the D5
air-band ink; reads as decor), `$02` (the `$42` hit flash barely shows on it), and the status /
glow inks. Black paper, one ink per cell, so it is legal on every background. (The former D7
`$03` share with the Orc Bouncer and Poltergeist is moot: no Archer on D7, H1.) Constraint for
the artist: the Mummy (D5) and Spider base inks must not be `$03`.

**D3-5 Sniper drop = 2/2** (Rewards rule wins; §9.6 row text fixed).

**D3-6 Names (≤ 9 chars; the user may rename later).**

| Row | Name | | Row | Name |
|---|---|---|---|---|
| Giant Rat | `GIANT RAT` | | Spider | `SPIDER` |
| Rabbit Rat | `BROOD RAT` | | Vampire | `VAMPIRE` |
| Screech Bat | `SCREECHER` | | Mummy | `MUMMY` |
| Goblin Slinger | `SLINGER` | | Orc | `ORC` |
| Black Widow | `WIDOW` | | Skeleton Archer | `ARCHER` |
| Skeleton Guard | `BONEGUARD` | | Necromancer | `NECROMAGE` |
| Skeleton Knight | `REVENANT` | | Ogre Warlord | `OGRE LORD` |
| Poltergeist | `WRAITH` | | Death Knight | `DEATHLORD` |
| Orc Berserker | `BERSERKER` | | Archmage | `ARCHMAGE` |
| Orc Bouncer | `ORC BRUTE` | | | |
| Skeleton Sniper | `SNIPER` | | | |
| Bone Caller | `SUMMONER` | | | |

Design names in this doc stay as they are; only the in-game strings change. Golden boss names
(§9.7 R1, per-depth table) keep their own ≤ 12 limit because they are only used in boss lines;
if they reach the hit/miss line they must also fit 9.

**D3-7 Parry chance: no data, derive from the kind id in the PHYS hit path.** Only 3 rows
parry, so a compare chain on the row id (`SK_GUARD` → chance 64/256 = ¼; `SK_KNIGHT`, `DK` →
85/256 ≈ ⅓; anything else → no parry) costs ≈ 14 B code, ≤ 60 T, 0 data, and needs no KX byte
or table. Use spare KX bits only if a parry flag already exists there and the compare can be
dropped. A 4th parrier (BAL1) would move it to a 2-bit field (§9.7 R5 #6).

**ARCHER-DEPTHS H1 (user 2026-10-29): Archer removed from D7 to keep the D7 pool; D7 ranged
pressure = 2 Necro entries** (`LP_KINDS` D7 = Orc, Necro, Ghost, Necro; §9.4). The Skeleton
Archer and its Sniper tier spawn on **D4, D5** only; the Archer 2-frame walk is dropped.

### 9.9 Archmage spell set (ARCHMAGE-SPEC; user 2026-10-29 scope, designer decision 2026-10-29 details)

User (Fuse): *"it shares the Necromancer's sprite, feels too weak, casts too little; as the main
boss it should cast EVERY effect in the game."* Ruling: the Archmage **acts every turn**. It
casts a **damage spell every 2nd turn** and fills the turns between with a hex, a summon, its
one blink, or its staff. Its 7 spells cover **all 5 magic damage types and all 7 statuses**, and
the staff covers PHYS. Every spell is a **RANGED-SPEC monster shot** (§9.2): auto-hit, `roll ×
res`, no DEF, the on-hit roll after the damage. Each is **one descriptor row**: a new spell
costs data, not code.

**A1 Stats.** hp **60** (was 40; D8 scaling → **67**), atk 4, eva 3, DEF 1, `BOSS`, resistances
unchanged (§9.1: COLD X, SHOCK X, DRAIN I, DARK R). Why 60: the final boss now sits above the
Death Knight (56 at D7), and the Mage's Firebolt budget still covers it (below).

**A2 Spell rows** (`rd_tab` rows, RW_STRIDE 8, + an ink byte; rows 0–4 = bolts, 5–6 = hexes):

| Row | Spell | Type | r | Damage (avg) | Rider on the hero (chance) | FX ink | Special |
|---|---|---|---|---|---|---|---|
| 0 | **Death Bolt** | DARK | 28 | 1d8+3 (7.5) | FEAR 3 (85/256) | `$43` magenta | the fallback row; Mirror Helm return (A6) |
| 1 | **Frost** | COLD | 12 | 1d6+1 (4.5) | FROZEN 2 (128/256) | `$45` cyan | HOLD row (A4) |
| 2 | **Lightning** | SHOCK | 12 | 1d8+1 (5.5) | CONFUSED 4 (128/256) | `$47` white | — |
| 3 | **Drain** | DRAIN | 5 | 1d6+1 (4.5) | WEAK 8 (128/256) | `$44` green | heals the Archmage by the damage dealt (the Vampire's drain path; green `+n` on it) |
| 4 | **Firebolt** | FIRE | 12 | 1d8+2 (6.5) | STUNNED 1 (85/256) | `$42` red | HOLD row (A4); FIRE thaws a frozen hero (the cycle never puts it after Frost) |
| 5 | **Sleep** (hex) | typeless | 12 | 0 | ASLEEP 3 (always) | `$41` blue | HOLD row (A4) |
| 6 | **Venom** (hex) | typeless | 12 | 0 | POISON +12 (always) | `$06` yellow | — |

- **Riders** use the §6.4 rules unchanged: R2 check order, resist I/X → none, R → half, B2 (no
  HOLD on a held body), HOLD_GUARD, max-refresh, POISON adds (cap 30). Riders go through the
  generic on-hit apply (T6), fed from the row instead of the kind.
- **Hex rows** (`RWF_HEX`) deal no damage, print no hit line, and apply the rider through the
  immunity mask only (Silk Cloak → Venom `UNAFFECTED`). They are typeless, so no gear blocks
  Sleep: Sleep is the one effect only Cure/time answers, and any damage wakes the hero.
- **No bounces on any row** (the T7 row's 1 bounce goes). Monster shots still never bounce or
  drop items. The only reversal is A6.
- **Cap per turn:** the Archmage makes at most one attack per turn (one spell *or* one staff
  hit), so its maximum is **11 HP per turn** (Death Bolt 1d8+3) and **17 per two turns**
  (bolt + staff). Summons and the Tome aura are separate sources (the aura is in the Sanctum,
  not in the lair: it never stacks with this fight).

**A3 Turn rule** (the Archmage's own `ai_monster` branch: one kind test at entry → far6 R6
`arch_ai`; it skips the walker path, the melee-first rule and the ranged hook. It never walks:
G1d spawn only, no G2). State: cast counter **C** (the 2-bit `E_RCD`, 1 at spawn/arrival), cycle
pointer **P** (0..4, starts 0), hex cooldown **H** (0..4), summon cooldown **S** (T9's 4-bit
field), **blinked** bit. HOLD (FROZEN/STUNNED) skips the whole turn and nothing ticks (§6.4).
**In line / gap** = RANGED-SPEC geometry (same storey, both standing, wall scan + `box_free`);
the hero mid-ladder or on the other storey is out of line.
1. Decrement H and S (floor 0). Read C, then decrement it (the T7 rule: the old value decides).
2. **Bolt turn** (C was 0) and the hero in line: cast **ORDER[P]** if `gap < r` and (it is not
   a HOLD row, or the hero has no HOLD and no HOLD_GUARD); **otherwise cast Death Bolt** (r 28
   always reaches across the room). P = (P + 1) mod 5, C = 1, done. `ORDER = Death Bolt, Frost,
   Lightning, Drain, Firebolt` (Lightning follows Frost, so the cycle never thaws its own freeze).
   C was 0 but out of line: C stays 0 (it bolts the moment there is a line) and go to 3.
3. **Off-turn**, first match:
   a. **Blink** (once per life): hp ≤ ½ max and not blinked → move to post **P′** = the same
      x on the other storey. If that box is illegal (wall, pit, body, ladder box), try 1..8 cols
      toward the room centre; if none is legal, the bit is spent and nothing moves. Costs the
      turn, sets S = 0, `$47` attr flash on both footprints (the teleport flash),
      `THE ARCHMAGE VANISHES!`.
   b. **Summon** (T9's Bone Caller code): S = 0, no live summon (one at a time, user 2026-11-01), a free slot and the room's ROOM_CAP
      allow it (**exempt from `LP_SIGMA_CAP`**, user 2026-11-01) → one Skeleton beside it (Bone Caller placement rule), S = 6.
   c. **Hex:** H = 0, the hero in line, gap < 12 → **Sleep** if the hero has no HOLD and no
      HOLD_GUARD, else **Venom**. H = 4.
   d. **Staff:** the hero in reach → melee 1d6 PHYS (F1 roll, DEF applies; the cast/attack pose).
   e. Wait facing the hero.
- **Re-entry** (banked; AI state is not banked): P = 0, H = 0, C = 1, S as T9 resets it,
  blinked = (hp ≤ ½ max). It is re-placed at its G1d post, not at P′.
- Net cadence with the hero in line: a bolt on turns 2, 4, 6…, a hex about every 5th turn, the
  staff or a summon in between. **Something visible happens every turn.**

**A4 Hold lock (no chain-stun).** The HOLD rows (Frost, Firebolt's stun, Sleep) are never chosen
while the hero is held or has HOLD_GUARD (Frost/Firebolt fall back to Death Bolt, Sleep to
Venom). With B2 and HOLD_GUARD this caps the hero's lost turns at ≈ 1 in 4 during the worst
streak. Sleep is broken by the next bolt (any HP loss wakes), so it costs ≈ 1 turn.

**A5 Telegraph** (the player must see what comes next; turn-based, so the cue is *before* the
turn, not during it).
- **Body ink = the next bolt's ink.** After every bolt (and at spawn), the Archmage's stamp attr
  becomes ORDER[P]'s FX ink. The footprint attrs are rewritten once through the existing tint
  change path (≈ 2.2k T, on a render tick). Priority as §6.4: hit flash > HOLD tint > this ink.
  Its cyan body says "Frost next: get out of 12 cols, climb, or eat it". The fallback rule is
  honest: if the shown spell cannot fire, it is always the magenta Death Bolt.
- **Cast pose** on every spell and hex (the Necro cast frame), with the bolt in the row's ink.
  The impact is `nbolt_hit` in the same ink, then the usual `$42` hit flash and the status mark
  (§6.4.1 V2) or panel icon.
- **No border flash** per status: the mark, the tint and the panel icon already show it, and
  the border means ALARM (§1.5). No per-spell log line: the existing hit line plus the status
  line (`YOU ARE FROZEN SOLID!` …) name the effect. New text = **1 string** (A3a).

**A6 Mirror Helm return** (user 2026-10-29 (c): the Archmage ignores the reflect gate). A Death
Bolt on a DARK X hero deals him 0 and no FEAR. It reverses at his front cell (a second FX track
from the hero back to the Archmage, queued in `RS_Q`, starting at the impact tick) and strikes
the Archmage for the same roll × its DARK R = **½** (min 1); FEAR on it is boss-immune. No other row can be reflected (no hero gear has X except DARK). Ring of
the Grave (DARK I): 0, `UNAFFECTED`, no return. Gravecloak (DARK R, DRAIN R): ½ damage, half
durations on those riders. Fire Ward: Firebolt ½, stun duration 1 → 0.

**A7 Visuals: zero new frames.** Pose: the Necro frames already resident on D8 (the Necro is a D8
kind and its unit is generated for the Archmage too: cast + walk1 as the stand, `dead_humanoid`).
FX: **`nbolt_fly1/2` + `nbolt_hit` re-inked per row** via the FX descriptor's attr byte (the
Slinger-rock precedent, T7). These are resident on D8 for **both** heroes. The hero's own spell
frames (Firebolt, Frost…) are in the Mage pool only, so they are not used: same look on both runs,
0 pool, 0 fids (FRT 132/132 stays full). **Optional polish, not in T11:** on a Mage run, use the
resident hero fly/impact fids for rows 1–4 (a per-row Mage fid byte + 1 test, ≈ 12 B).
- **The Necro-sprite complaint:** with A5 the Archmage's body is never the Necro's ink; it is
  always a spell colour that changes every 2 turns. That is the free answer. A truly distinct
  silhouette needs art (A9 USER).

**A8 Balance at D8** (hero at entry W 61 HP / 16 MP, M 37 / 26; §10). Average bolt over a full
cycle 5.7 (4.2 with the Mirror Helm), so ≈ 2.9 HP per turn in line (2.1 with the helm), plus
the staff in reach.
- **Approach:** at gap ≥ 12 only Death Bolt reaches, and the Mirror Helm (the mandatory D7 boss's
  drop) turns it into ½ damage to the Archmage. The other storey and a mid-room block are out of
  line, so no casts come from there (summons still do). Without the helm, 6 turns of approach at
  gap ≥ 12 cost 3 Death Bolts ≈ 22 HP.
- **Warrior:** Power Strike ×5 (16 MP) ≈ 55 + 3 swings ≈ 70 ≥ 67 hp, so ≈ 8 melee turns.
  Damage taken: 4 bolts + staff ≈ 30, plus one blink phase (re-approach ≈ 4–6 turns, ≈ 12–17) and
  summons: **≈ 45 of 61** without the helm, **≈ 33** with it. Winnable without any ranged item.
  Cure answers FEAR/WEAK/CONFUSED; Heal potions are the buffer.
- **Mage:** Firebolt ≈ 9–10 per cast (Bone Staff +2, ranks) → ≈ 7–8 casts = 21–24 MP of 26
  (a Mana potion is the margin). Over those ≈ 8 turns he takes ≈ 4 bolts + 1 hex ≈ 23 of 37. His
  Frost/Lightning reflect (X), as before. The no-Firebolt Mage (~2 %) stays the §10 BAL1 item.
- **BAL1 knobs, in order:** hp 60 (50–70), C cadence (N 1; N 2 = every 3rd turn), the rider
  chances, hex cooldown 4, blink threshold ½.

**A9 Cost** (estimate; T11, mostly R6, input tick only).

| Item | R6 | bank 3 |
|---|---|---|
| 6 new rows × 8 B + 7 ink bytes (the T7 Archmage row is reused, edited) | ≈ 55 | — |
| `arch_ai`: counters, ORDER/P, range + hold-lock fallback, off-turn chain | ≈ 110 | entry test ≈ 6 |
| Row-fed rider + `RWF_HEX` path in `rg_shoot` | ≈ 35 | — |
| FX ink override from the row | ≈ 6 | — |
| Telegraph ink (stamp attr + tint request) | ≈ 20 | — |
| Blink (P′ search, flash, line) | ≈ 50 | — |
| Mirror Helm return (2nd track + ½ hit on the caster) | ≈ 45 | — |
| Drain heal (reuse the Vampire's) / summon (reuse T9) | ≈ 10 / ≈ 15 | — |
| String `THE ARCHMAGE VANISHES!` | 22 (text bank) | — |
| **Total** | **≈ 345 B** (≈ 200 B more than the old 4-rule Archmage) | **≈ 6 B** |

Bank 2 0 B (`rk_tab` already maps the Archmage to its first row). Pool 0 B. RAM: P (3 bits), H
(3 bits) and the blinked bit go in the Archmage slot's `ST_X` (monsters are never poisoned, §6.4.3)
or any spare per-slot bits (engineer's choice); C and S live in `E_RCD` as T7/T9 reserved. Ticks:
selection ≤ 0.6k T, a shot ≈ 8.7k T (T7 measured), the return track adds one FX track (the ≤ 3
shared tracks, queued if busy). One footprint attr rewrite (≈ 2.2k T) per bolt on a render tick.

**A9b As built (3F-T11b, manager rulings 2026-10-31; `src/arch6.asm`, memory-map "3F-T11b").** Accepted deviations:
- **Hex status at decision time** (not after impact): Sleep / Venom are applied when the hex is cast (the
  RANGED-SPEC "logic first" rule), so the ASLEEP tint / POISON mark and the line show while the bolt is still
  flying (≤ 1 s) and later monsters of the same phase already see the status. Moving it to the impact tick
  (shot_tick applying a stored row at I) costs ≈ 30 B R6, over the ≈ 20 B ruling. No sleep cue flash.
- **Blink flash on the new footprint only** (`$47`, `TELE_FLASH_T`); the old footprint is simply erased by render.
  If no box is legal the blink bit is spent and the off-turn goes on (b..e).
- **Summon limits (user 2026-11-01, D8 audit):** the Archmage's own summon is EXEMPT from `LP_SIGMA_CAP` (the always-spawned
  lair escort 3-6 + Archmage 6 + Skeleton 5 > 12 refused every summon); `ROOM_CAP`, a free slot, S = 0 and a legal box still
  apply, and the live-summon cap `AM_LIVE` is now 1 (was 2, which the Sigma cap used to enforce de facto). Other casters
  (Bone Caller, Pharaoh) keep the Sigma cap. `spawn6.asm sp_summon` zeroes `SP_SIG` for a `K_ARCHMAGE` caster.
- The Archmage skips `ai_monster` entirely, so it never yields to a climbing hero; a legal blink box
  (`sp_try`) never overlaps a shaft's exit box in the tested rooms, and a hero mid-ladder can always climb
  back down (no combat either way): not a lock (`tests/archmage.py` L).
- No green `+n` on the Drain heal (needs D3-11). The Sanctum seal opening on its death is not wired
  (`LF_SEAL_OPEN` has no writer yet; the death runs the boss flow: `LF_GRATE_OPEN`, `LF_UNIQUE`).

**A10 Cut order if memory runs out** (cheapest loss per byte first):
1. Mirror Helm return FX: keep the ½ hit on the Archmage, but drop the 2nd track (an impact flash
   on it instead): **−≈ 25 B**.
2. Telegraph body ink: the bolt ink still shows the type, but there is no warning before it: **−≈ 20 B**.
3. Blink: it becomes a turret with summons: **−≈ 50 B** (+ the string).
4. Hexes (rows 5–6 + `RWF_HEX`): ASLEEP and POISON leave its set: **−≈ 40 B**.
5. Archmage summons (T9's code stays for the Bone Caller): **−≈ 15 B**.
Never cut: rows 0–4 with the cycle, i.e. 5 types × 5 riders every 2nd turn. That is the request.
**Rejected:** casting a damage spell every turn (≈ 5.7 HP per turn would kill the Mage in about 6
turns, before his ≈ 8 Firebolts finish it); teleporting the hero (it would undo every Warrior
approach; the scroll/trap keep that effect); the hero's spell frames on a Warrior run (≈ 1.7 KB
pool vs ≈ 1.1 KB D8 slack after T8).

**T11 data slots T7 left:** the `rd_tab` Archmage row (edit: N 2 → 1, bounces 1 → 0), the caster
pre-rule slot `.pre` in `ai_ranged` (unused by the Archmage, which takes its own branch; it stays
for the Bone Caller), `E_RCD` bits 2–5 (summon counter), the `rk_tab` Archmage entry, and the
reflect-gate exemption flag on the Archmage row.

**USER decisions:** (U1) **cadence**: a damage spell every 2nd turn with an action every turn
(recommended), or a damage spell every turn (out of balance for the Mage, A8); (U2) **hp 60**
(recommended) vs keeping 40; (U3) **look**: telegraph inks only (0 B, recommended now) or **one new
24×48 Archmage stand frame** (+576 B D8 pool of the ≈ 1.1 KB left after T8, +16 B bank 2 for an
FRT_MAX bump, ≈ 150 B packed source; the cast pose stays the Necro's); the old §11.1 IDLE + CAST
pair (1,536 B pool) no longer fits; (U4) the Warrior wins without ranged items (A8: yes, by design;
confirm that the Mirror Helm as the expected answer is fine); (U5) teleporting the hero is
excluded (it would undo the Warrior's approach).

---

## 10. Balance sketch

Monster hp × count rises ~25 % per depth (depth scaling + kinds). XP levels (§4.1), ability
ranks and gear keep pace.

| Depth | Expected `LVL` | Hero at entry W HP/MP · M HP/MP (rev 5) | Threat | Key answer |
|---|---|---|---|---|
| D1 | 1 | 24/6 · 16/12 | soft | the D1 book in the start room (starter, deterministic) |
| D2 | 2 | 28/7 · 19/14 | poison | Cure; Firebolt (Spider W; Mage has it ½) |
| D3 | 3 | 32/8 · 22/16 | first undead: Frost/Drain are useless | Firebolt (Vampire W; ⅔); Whirlwind (½) or PS III |
| D4 | 4 | 36/9 · 25/18 | archers, Ogre 43 hp; Black Widow acid | Spark (Ogre SHOCK W, always known); Drain on living; close doors; bow |
| D5 | 5 | 40/10 · 28/20 | Mummy PHYS R, curse (WEAK 12, §6.4); first ALARM traps | Firebolt (Mage ~93 % by D5); Cure; Scarab next |
| D6 | 6 | 47/12 · 31/22 | casters, ghost reflecting Lightning | Ring of the Grave; Firebolt on ghosts |
| D7 | 7 | 54/14 · 34/24 | Death Knight (parry + notch, fire reflect); Necros 2 in 4 rolls (Dark Bolt + FEAR; no Archers, H1) | Spark / Lightning (W); Power Strike through parries; blessed weapon |
| D8 | 8 | 61/16 · 37/26 | Archmage + summons + bouncing bolt; reflects Frost/Lightning | Mirror Helm; Firebolt (Mage ~98 %); potions saved |

**Answers under random books (rev 6, §5).** Bosses never regenerate and never follow (§8.6),
so a missing answer costs time and food (retreat, rest, return), never the run.

| Threat (res., §9.1) | Mage answers | Mage without them | Warrior |
|---|---|---|---|
| Spider Queen D2 (FIRE W) | Firebolt | ½ of runs (and then Spark is II): Spark kite, ~14 MP for its 22 hp = the whole L2 pool; Mana potion or a second visit | PS II + sword; Cure |
| Vampire Lord D3 (FIRE W; COLD/DRAIN I) | Firebolt; Spark N | ⅓: Spark-kite at range (its bite heals it), 2 lair visits; Frost/Drain useless | Whirlwind ½ / PS III ½: both fine |
| Ogre Warlord D4 (PHYS R, SHOCK W) | **Spark**, Lightning | always has Spark; ranked Spark is the best answer | PS (×2–×3 beats PHYS R), bow, doors |
| Mummies / Pharaoh D5 (FIRE W, PHYS R, COLD/DRAIN I) | Firebolt; Spark/Lightning N | ~7 %: Spark/Lightning at N, slower; Pharaoh over 2 visits | PS, Scarab next |
| Ghosts D6–D8 (SHOCK X, PHYS R, COLD/DRAIN I) | **Firebolt only** | **~2 % (no Firebolt at run end): staff only, 1d4 PHYS R ≈ 1 per hit; avoid them (flyers, blocked by closed doors). BAL1 item** | sword (R), PS |
| Living Orcs D4–D7 (FIRE R) | Drain (sustain), Spark, Lightning | no Drain (~10 %): potions + rest | sword, Whirlwind on packs |
| Death Knight D7 (FIRE X, SHOCK W) | Spark, Lightning | no Lightning (~27 %): Spark III 1d8+4 ×2 = 17 per 6 MP is enough | PS through parries |
| Archmage D8 (COLD/SHOCK X, DRAIN I) + summons | Firebolt + staff; Lightning on summons | no Lightning: Firebolt burst on summons. **No Firebolt (~2 %): Bone Staff 1d6 (~38 swings for ~47 hp) + Mirror Helm reflecting Death Bolts (½ to it), hit-and-run over many visits (it never regenerates, §8.6); near-unwinnable. BAL1 item** | steel, Mirror Helm |

Warrior check: his end state is unchanged (PS III + Whirlwind III, ~3 Vigor); only the D3
order varies (Whirlwind or PS III). Low variance is accepted: his variety is gear, bow and
daggers. Rank-ups never hurt him (auto-downcast, §5).

**BAL1 items from rev 6 (user 2026-10-26; resolve with a tools/ simulation + playtest):**
- **No-Firebolt Mage (~2 % of runs; the keystone rule was vetoed).** Ghosts and the Archmage
  have no spell answer. Options, in order of preference: (a) give them a non-Firebolt
  answer, e.g. Ghost DRAIN I → R or SHOCK X → R, Archmage SHOCK X → R so Lightning works at
  ½; (b) a Firebolt-strong drop on the way (Bone Staff "spells +2" → also FIRE-type staff
  bonk, or a fire wand/scroll); (c) accept it as a rare hard run.
- **Re-verify the §5 book-outcome and rank-MP numbers** (hand estimates) by simulation.
- **Monsters must scale with depth, and stronger monsters should cast or throw.** Existing
  coverage: depth scaling hp + (d − 1), atk + (d − 1) div 3 (§9.1); tier odds rise with depth
  and hero level (§9.6). Ranged/casting today: Skeleton Archer / Sniper (arrows), Goblin
  Slinger (rock), Necromancer (Dark Bolt), Bone Caller (summons), Archmage (Death Bolt +
  summons). **Gap:** the melee tier-2/3 rows (Orc Berserker/Bouncer, Skeleton Guard/Knight,
  Black Widow, Poltergeist, Rabbit Rat) have no ranged or spell attack, and no monster
  throws daggers. BAL1 to decide e.g. Orc Bouncer / Skeleton Knight throw a dagger (Slinger
  ranged AI, `dagger_spin` frames, 1d4 r6), Poltergeist a short DARK bolt, and whether depth
  scaling should also add dmg (+ (d − 1) div 4).

**Rev 5 changes (E; flagged for the 5-seed playtest):**
- HP lands within ±2 of rev 4 at D8. **Mage MP runs ~+4 above rev 4 from D4 to D7** (the +2
  per level arrives earlier than the old Power tomes) and ranks cut MP costs (Drain 2,
  Lightning 4): the Mage is stronger mid-run. Knob: Mage level-up MP +2 → +1 on odd levels.
- Hero atk +1 at L4/L8 and eva +1 at L6 add ~5–10 % to-hit / evasion from D4 on. Knob: drop
  the L6 eva step.
- XP thresholds assume a near-full clear; a stair-diving hero is ~1 level behind by D5, which
  lowers his tier odds (Δ = −1) and is the intended rubber band. Check the D8 entry level
  over seeds (target 7–8).
- Cursed mean `m` −0.25…−0.5, wear ~2–4 points per run: confirm gear feels lossy but not
  punitive; blessing (Enchant) is the counter.

**Sample duel (D1, Warrior vs Goblin):** 65 % to hit, 3.5 avg → ~2.6 turns, ~2.3 HP lost.
**Mage:** opening with 2 Sparks at range costs ~0 HP and 4 MP (B20: Spark 2 MP; the pool is
the per-fight budget, refill 48–84 turns, §4.0).

**Run:** ~450 turns per level, ~3,600 turns ≈ 60–65 min.

**Rev 4 additions (E):** status effects mostly cost the hero tempo (≤ 4 lost turns per
event) and Cure now answers four effects; traps cost ~2–4 HP per level (DART) plus position
(TELEPORT) and ~1 extra wave (ALARM, D5+); tiers raise threat by ~10 % (D2) to ~25 % (D8) of
monsters being tougher, self-correcting through `Δ` for a hero who skips books or bosses.

**Tuning knobs, in order:** Heal amount, food per level, depth scaling, boss multiplier,
`XP_NEXT`, level-up HP/MP, `T2_BASE`/`T3_BASE`, trap counts, rank table, `SHATTER_CHANCE`.
Verify with ≥ 5 seeds × 2 heroes before Stage 3 exit.

---

## 11. Asset and budget reconciliation

- Source = `W/8 × H × 2`. Pool: stationary = 2 × source; moving = 2 × source + 2 × source ×
  (cols+1)/cols; projectiles = 2 × source (one shift).
- **ZX0 format (rev 3, A4 measured; supersedes rev 2's per-frame packing).** Sources are
  packed in **blocks of 3–4 frames per kind**. The generator unpacks one block into the
  **1.5 KB `GEN_SCRATCH`** (aliasing `ROOM_MAP`+`NEXT_MAP`, memory-map; legal because the
  generator never runs mid-room), then reads the frames out of it. Rev 2 unpacked each frame
  into the 512 B `GEN_SRC`. Measured ratios: **1.80× per frame, 2.71× per kind block**
  (concept data 1.69×). A block must unpack to ≤ 1,536 B; a kind whose 3–4 frames exceed it is
  split into two blocks (the packer asserts). Budget below keeps the **conservative 1.7×**
  and reports the block gain as slack.

### 11.1 Frame ids and bytes (new)

| Owner | Frames | Ids | Source raw | Pool |
|---|---|---|---|---|
| Monsters drawn **M** (superseded by the lean set 2026-10-20 + §9.7: Archer has no SHOOT frame, Orc 3 frames, no climb frames for Orc/Archer/DK): **Vampire**, Mummy, Orc, Necromancer, Spider 5 each; Archer 4 (HURT/DEAD = Skeleton) | WALK×2, ATTACK, HURT, DEAD | 29 | ~8,000 **M** | 4.2–4.6 KB per kind, Spider 2.75 **M** |
| Mage drawn **M** | STAFF_SWING **40×48** | 1 | 480 | 960 |
| Warrior **M** (round 3) | JUMP1, JUMP2 24×48, POWER_STRIKE 40×48 (ax 4), WHIRL 40×48 (ax 8), THROW 32×48, BOW 32×48 | 6 | 2,304 | **5,568** |
| Mage **M** | JUMP1, JUMP2 | 2 | 576 | 1,920 |
| Archmage **M** | IDLE 24×48, CAST 40×48 (HURT = flash, DEAD = Necro) | 2 | 768 | 1,536 |
| **Ogre Warlord**, to draw | WALK1/2 32×48 (M), RAISE 40×48, SLAM 40×48, HURT 32×48, DEAD 40×16 | 6 | 2,272 | 6,464 |
| **Death Knight**, to draw (redesign: greatsword, horned crowned helm) | WALK1/2 24×48 (M), CLEAVE 40×48, BLOCK 32×48, DEAD 40×16 (HURT = flash) | **5** | ~1,830 (E, artist confirms) | **5,184** |
| **Spell sprites, lean set M** (round 3) | Spark fly ×2 + fizz, Firebolt fly ×2 + burst, Frost fly + crack, Lightning fly ×2 + flash, Drain fly ×2 + hit (11 already drawn) | 14 | 464 | 1,696 |
| Other projectile/impact sprites **M** | power burst 1, necro bolt 3 (Death Bolt = same frames, `$43`), arrow 2 + hit 1, dagger spin 2 (4 → 2), staff bonk 1 | 10 | ~370 | ~740 |
| Golden bosses | recolour + glow | 0 | 0 | 0 |
| **Total new** | | **75** | **~17.0K raw → ~10.0K ZX0 at 1.7× (E); ~6.3K at the 2.71× block ratio** | projectiles ~2.4 KB resident on every level |

The Vampire's bat form reuses the Bat kind's frames: **0 new ids**. A level with a Vampire
therefore needs the **Bat set resident too** (D6 and D8; D3 already has it): +2.0 KB pool
(§11.3).

### 11.2 Limits vs need

| Store | Budget limit | Need | Verdict / change |
|---|---|---|---|
| Frame ids | 28 free (`FRT_MAX` 96, 68 used) | 68 + 75 = **143** | **`FRT_MAX` → 160**: +64 × 16 B = **+1,024 B bank 2**. 16 spare |
| Kind ids | 16 | 2 heroes + Rogue hole + 12 monster kinds + Archmage + Ogre + Death Knight = **18** | **`kind_tab` → 32**: **+256 B bank 2**. The resistance table adds ~60 B (3 B/kind) |
| Bank 2 | ~0.87K + ~2.1K freed by the cold-code move ≈ 3.0K | FRT +1,024, kinds +256, resist ~60 = **1.34K**; **text font 768 B** (6×8 × 96, rev 3) | 1.34 + 0.77 = 2.11K, **~0.9K left**. **Resolved 2026-10-03 (§3.4):** text is drawn only into bank 5 since A7; the text font stays in bank 2 (`$B200`); the **menu font moves to bank 3 cold data (≤ 1.5 KB raw)**, so it costs bank 2 nothing and the ≤ 0.8 KB cap is dropped. The text font is fixed. **The static frame descriptors (24 B/frame) must leave bank 2**: 146 × 24 = 3.5K. The engineer trims them to ≤ 12 B (W, H, ax, class/sym, source bank+offset) → 144 × 12 ≈ 1.75K, moved to **bank 5** next to the generator that alone reads them |
| Bank 5 low RAM | ~6.1K | generator + boot ~2.1K, ZX0 + `GEN_SRC` 0.6K (rev 3: the scratch is the 1.5 KB `GEN_SCRATCH`, **aliasing `ROOM_MAP`/`NEXT_MAP` → 0 extra bytes**; only the decompressor ~0.1K stays here), tile glyphs 0.6K, level state 0.6K, frame descriptors ~1.75K | ~5.65K, fits, **0.45K margin** |
| Sources + cold data (banks 1+3) | 32,768 − AY reserve | existing 16,899 → ~9.9K ZX0 + new ~10.1K ZX0 + menus code ~2.0K + icons ~2.7K → 1.6K ZX0 + strings ~2.9K → 1.7K ZX0 = **25.3K** | **AY reserve 4 KB, `AY_RESERVE` `$E400` → `$F000` (user 2026-10-06; supersedes 7 KB)**: compact tracker player 1–1.5 KB + effects ~0.3 KB + 1–3 KB in-game loop; sources get **+3 KB** (28.7K free vs 25.3K need → ~3.4K margin even at 1.7×). Earlier: AY 8 KB 0.7K over, 7 KB (user: approved) ~0.3K margin. With the rev-3 block packing (2.71× measured on kind data) the expected total is ~18–20K, i.e. ≥ 5K of real margin; the 1.7× row stays the build gate until A5 reports actual sizes |
| Bank 7 spare | 2,656 | **8 per-level tilesets 2,304** | Fits (cold, copied at level start; never drawn into bank 7) |
| Pool per level (0/4/6) | 49,152 − hero **18,176** (Knight 12,608 + Warrior 5,568 **M**) − straddle 1,728 − projectiles ~2.4K = **26.8K** | max **D8 23.9K** (§11.3; includes the Bat set for the Vampire's bat form) | **Fits, ≥ 2.9K slack** on every level. Build ASSERT per level |
| Tile ids | 64 | 29 common + ≤ 32 per level | fits (§1.2). Rev 4: common id 10 = `T_TRAP` → common ids full |
| **Rev 4 (designer decision 2026-10-03)** | — | kind rows 18 + 12 tiers = **30 of 32**; 3rd `kind_tab` page **+256 B bank 2** (resist, immunity, on-hit, parry, tier-up); `ENT_STAT` 64 B in `BANK2_FREE`; status hot code ~150 B bank 2 | bank 2: +256 + ~150 B against the ~0.9K left (+64 B in `BANK2_FREE`, which is outside the image). Cold, bank 3: status apply/messages ~300 B, traps (gen + trigger + search) ~350 B, BUC + ID ~250 B, tiers ~170 B, strings ~1.1 KB raw (status 0.45, traps 0.2, ID/BUC 0.25, tier names 0.13, scroll/potion names) → **~2.2 KB raw, ~1.4 KB at 1.7×** against bank 3's 7.4 KB free (R3 had 4.1 KB planned). Glyphs: 7 status icons 56 B (panel), trap glyph 8 B. Level state: trap list 12 B; state block: ID tables 8 B, `PL` 1 B. Render: tints = one-off attr rewrites; tiers 0 |
| **Rev 5 (designer decision 2026-10-03)** | — | **Bank 2:** `KXP` 32 B (kind_tab page spare 48 → 16 B), current-rank rows ≤ 30 B, XP award ~40 B, regen check −10 B → **~+0.1 KB**. **Bank 3 cold:** level-up + display ~180 B, curse shatter/bless/reveal ~140 B, wear ~70 B, book read-time ~90 B, rank table 126 B, `XP_NEXT` 16 B, strings ~330 B raw (XP 70, curse 90, wear 110, ranks 60) → **~0.95 KB raw** (worst case uncompressed) against bank 3's free space after rev 4 (~6 KB). **Bank 5:** cursed value roll ~40 B (margin 0.45 → ~0.41 KB). **State block:** `XP` 2 + `LVL` 1 + `ARANK` 2 − `PL` 1 = **+4 B**. Item record: 0 B (`ISTATE` spare bits). Turn cost: ~150 T per kill, ~30 T per projectile hit on the hero, ≤ 0.3k T per wear event; 0 render | fits |
| Render tick | ~114k T | §9.3 weights incl. projectiles; gold glow ≤ 1.5k/tick | by construction; E2 measures |

**Risk.** Sources are the tightest store, and the ZX0 ratio is an estimate. At 1.5× instead
of 1.7×, sources grow by ~2.3K. The levers, cheapest first:
1. Arrows/daggers/bonk back to 8×8 glyph cells: −6 ids, ~0.3K.
2. Monster HURT → flash: −5 ids, ~1.4K source, ~2.9K pool.
3. Shared DEAD frame: −5 ids, ~0.6K.
4. ~~AY reserve 7 → 6 KB~~ (taken: now 4 KB, user 2026-10-06).

### 11.4 Stage 3D decisions (designer decision 2026-10-06; user decisions marked)

- **user 2026-10-06:** (a) AY reserve 4 KB (see §11.2). (b) PROTO wizard "zap" melee removed; Mage melee = STAFF_RAISE → STAFF_SWING (staff bonk). (c) A measurement spike on dropping the bank-7 clean-background copy runs during 3D; decision before 3E.
- **Ammo glyphs (designer decision 2026-10-06):** no new tile ids (common ids full). 3D: thrown daggers and arrows are consumed (no floor drop). Recovery is deferred to 3E floor-item records (spent arrows / thrown daggers become floor items, drawn by the item glyph path).
- **DEF (designer decision 2026-10-06):** 3D implements hero DEF (armour, e.g. Leather 1) in the damage formula. Monster DEF is 0 in 3D; the KX table adds it in 3E (no `kind_tab` change in 3D). **Ended by 3F-D3 (§9.8 D3-1): every row carries its §9.1/§9.6 DEF.**
- **dagger_spin:** 2 frames (as §11.1); the other two drawn grids stay unused source.
- **Animation order:** monster animations start only after the hero's projectile lands (no overlap). Costs latency, protects the tick budget.
- **3D tests:** poison, WEAK, FEAR, SLEEP, book reading and bow pickup have no source until 3E/3F; 3D tests them by poking state.
- **Knight POWER_STRIKE 40x48:** confirmed needed; artist drafts it.
- **3D art (user 2026-10-06):** frost_crack impact stays 8×8 (revisit after playtesting); Firebolt fly frames alternate yellow `$46` and red `$42`; the full effect set is kept, including fizz2 and burst2; Knight POWER_STRIKE 40×48 and the 7 status icons are approved as drawn. Packed total 1,322 B (unchanged; §11.1 figures not altered).

### 11.3 Pool per level (KB; existing kinds E scaled from the measured 22,688; new **M**)

| Depth | Kind sets | Total |
|---|---|---|
| D1 | Rat 2.0 + Bat 2.0 + Slime 1.8 + Goblin 5.6 | 11.4 |
| D2 | Goblin 5.6 + Spider 2.75 + Bat 2.0 + Rat 2.0 | 12.4 |
| D3 | Skeleton 8.4 + Vampire 4.6 + Ghost 2.9 + Bat 2.0 | 17.9 |
| D4 | Orc 4.6 + Rat 2.0 + Spider 2.75 + Archer 4.4 + Skel HURT/DEAD 0.9 + **Ogre 6.5** | 21.2 |
| D5 | Mummy 4.6 + Skeleton 8.4 + Archer 4.4 + Spider 2.75 | 20.2 |
| D6 | Vampire 4.6 + **Bat 2.0** + Ghost 2.9 + Necro 4.48 + Orc 4.6 | 18.6 |
| D7 | Orc 4.6 + Ghost 2.9 + Necro 4.48 (loaded once; 2 `LP_KINDS` entries, H1) + **Death Knight 5.18** (no Archer / Skel HURT/DEAD since H1, −5.3) | 17.2 |
| D8 | Necro 4.48 + Skeleton 8.4 + Ghost 2.9 + Vampire 4.6 + **Bat 2.0** + Archmage 1.54 | **23.9** |

Level-start regeneration (≤ 24 KB, D8) takes ≈ 1.9 s (E; block unpacking is not slower than per-frame), behind a `DEPTH n` card.

---

## 12. Open questions for the user

Answered and removed in rev 3: Mage bar keeps BAG; AY reserve 7 KB; Ogre Warlord + Death
Knight; the 8 colour schemes.

1. **Ammo numbers (§6.3, §8.5):** start 3 daggers / 6 arrows; stack caps 9 / 24; dagger
   lost 1 in 4 per throw; arrow broken on a hit, 50 % recoverable on a miss; per level 1
   dagger stack of 2–3 + 1 arrow stack of 5–8 (D1–D7). Confirm, or tune after the 5-seed
   playtest.
2. **Quick scroll slot (§3.5):** added to the bar so the approved scroll icon works. Scrolls
   per level raised 1 → 1–2. OK?
3. **Vampire (§9.1–9.2):** hp 14, atk 2, 1d6 drain bite, slow in humanoid form, bat form to
   flee (hp ≤ 5, 8 turns, once) or to close distance. Confirm numbers.
4. **Hunger stage 2 is named `OK`** (§7). Alternative `SNACKY`/`PECKIS`. OK?
5. ~~Menu font size~~ — resolved 2026-10-03 (§3.4): the menu font lives in bank 3, ≤ 1.5 KB raw.
6. The Bat set is now resident on D6 and D8 (+2.0 KB pool; D8 = 23.9 KB, still fits).
7. ~~Cursed gear~~ — resolved 2026-10-03 (user, rev 5, §8.7): hidden ± value revealed on
   equip, sticky until blessed (Enchant) or shattered (projectile hit, 1 in 4); no regen
   penalty.
8. ~~Hero power level~~ — resolved 2026-10-03 (user, rev 5): XP and levels (§4.1) replace
   `PL`; tiers use `LVL − d` (§9.6).
9. ~~Bow as a bag item~~ — resolved 2026-10-04 (user): not in the start kit; guaranteed on D2
   with a 6-arrow bundle (§8.5, §6.3, §4).
10. ~~2nd class book 1 in 2 on D4–D7~~ — approved 2026-10-04 (user; §5).
11. ~~Stage 3C input/menu questions~~ — resolved 2026-10-04 (user + designer decision):
    title "TOME OF THE DEAD", Sinclair shortcut disabling, pause overlay with confirmed Quit,
    XP in 3D, redefined keys live with joysticks, greyed Bow/food, `NO BAG YET`, turn-around
    repeat delay, PROTO keys dropped (§3.1–3.2, §3.5, §4.1).
