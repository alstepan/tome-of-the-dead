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
| Win | D8: kill the **Necromancer Archmage** → the Sanctum seal opens → **destroy the Book of Absolute Death Magic** (§1.3) → `GS_WIN` | user |

### 1.1 Generation rules (F6, per level, deterministic from the level seed)

| Step | Rule |
|---|---|
| Tree | random DFS spanning tree over the 3×3 cells from a random start, 7–9 rooms, + 0–1 extra edge (a loop). Leaves = **dead-end rooms** |
| Edges | horizontal: open edge on storey `s ∈ {0,1}`; **1 in 3 carry a door** (§2.3). Vertical: up-exit `{c,0}` below + down-exit hole `{c,2}` above, same `c` |
| Start | the DFS root, **on the top grid row (L1, 2026-10-05)**, 0 monsters. D2–D8: arrival shaft from above, rubble-capped |
| Lair | **on the bottom grid row (L1, 2026-10-05; tiers in the L1 rules row)**, the farthest leaf (BFS) with a horizontal tree edge: boss + **level exit** = down-shaft `{c,2}` under a **GRATE** that opens when the boss dies |
| Key room | the farthest other leaf (else the farthest non-start room): holds the **level key**. The lair edge is a **locked door** |
| D8 Sanctum | an extra leaf off the lair behind a **sealed door** (opens on the Archmage's death); holds the Book. D8 has no exit |
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
| Traps (3E) | placed **last**, after the floor items, so every earlier generator output stays byte-identical to B3B-7 (Python == Z80). Rules §1.5 |
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

### 1.3 The Book of Absolute Death Magic

- The Book lies on a **2×2 lectern tile object** in the Sanctum. It **cannot be picked up**.
- **BOOK_HP = 5.** Every hit whose line reaches the Book removes 1: melee, power attack,
  spell, arrow or dagger.
  - It **ignores resistances** and is never missed.
  - Each hit flashes the lectern `$43` and prints a message.
- **Aura:** while the hero is within 6 cols on its storey, it deals 1 HP per turn (end of
  turn, ignores DEF).
- At 0 it turns to ash (rubble glyph) → `THE BOOK IS DESTROYED` → `GS_WIN`.
- It is a tile with an `ATTACKABLE` flag, not an entity.

### 1.4 Stage 3B stand-ins (user, 2026-10-03; temporary, replaced in 3C+)

| Area | 3B stand-in | Final rule |
|---|---|---|
| Floor items | **potions only** | §8.5 |
| Population | a **fixed per-room table** using today's (prototype) kinds | §9.4 **lazy population** (user 2026-10-06; plan task LP): budget + per-room records, spawned on room entry (§9.4.1–9.4.3) |
| Lair | the **grate is always open** (boss death not required), but drawn as the distinct raised-portcullis frame (id 26, ink `$46`, concept-screen §3.3 B3B-8 #4) with a first-entry hint `A GATE GLEAMS. THE WAY DOWN.` (designer decision 2026-10-04, B12); ordinary down-exit holes stay plain | §1.1, §8.6 |
| Key / locked door | no key exists (potions only), so the lair door is an **ordinary unlocked door** (designer decision 2026-10-03) | §1.1 |
| D8 | D8 gets a lair exit like D1–D7; **descending from D8 = `GS_WIN`** | §1.3 |
| Close door | keyboard key **`C`** (1 turn, §2.3 legality; not redefinable, not on joystick) until the 3C icon bar adds FIRE on the melee icon (designer decision 2026-10-03: the key) | §3.1 |
| Start kit (3D, D3-7 debug; designer decision 2026-10-12) | Behind a debug build flag only, never in a release tape. **Mage:** all 5 spells rank 1, MP 40/40. **Warrior:** Power Strike + Whirlwind rank 1, bow in the bag, **ARROWS 20, DAGGERS 8**, MP 20/20. The near-cap ammo lets the D1 floor stacks trigger `QUIVER FULL.` | §4 start kit (3E) |

### 1.5 Traps (3E; user 2026-10-03 scope, designer decision 2026-10-03 details)

**Model.** A trap is a **1-col pressure plate in a storey's standing row** (row `9s+7`, the
air row directly above the floor), the same row skulls and rubble use. It is not an entity and
not a map tile while hidden: it lives in the per-level **trap list**; the room map keeps the
cell's normal id. **Only the hero triggers traps** (monsters know their dungeon: no AI or
pathing change, no off-screen events).

| Type | Depths | Effect on the hero | After triggering | Message (≤ 32) |
|---|---|---|---|---|
| **DART** | D1+ | 1d4+1 PHYS (DEF applies) + **POISON 6** (§6.4); impact = `arrow_hit` sprite at the hero | **re-arms** (stays, now known) | `A DART HITS YOU!` |
| **GAS** | D2+ | **ASLEEP 4** (§6.4); hero flashes `$44` one step (no new art) | **one-shot** (removed) | `SLEEPING GAS! YOU FALL ASLEEP.` (30) |
| **TELEPORT** | D3+ | as the Teleport scroll (§8): random free spot, random room, never the lair while its boss lives; attr flash as the Archmage's | one-shot | `YOU ARE TELEPORTED!` |
| **ALARM** | D5+ | while the boss lives: one **wave** = the §9.5 idle-wave spawn (1 + (rnd & 1) of the level's kinds at the room's doors/exits, awake, `F_RESPAWN`, slot + §9.3 cap rules), runs even with `IDLE_WAVE` off; border flashes red 2 ticks. Boss dead: nothing comes | one-shot | `AN ALARM BELL RINGS!` / `A BELL RINGS. NOTHING COMES.` (28) |

ALARM's wave code lands in 3F; in 3E the trap is generated and prints the "nothing comes"
line (the generator must not change between 3E and 3F).

**Trigger.** A trap fires when a hero move **first brings its col under the body** (walk,
bump-free step, jump landing, fall landing, ladder step-off onto the storey). Standing on it,
turning, or waiting does not re-fire; walking off and back on does (DART). A **jump clears
it** when the trap col is within the cleared cols `x+3 … x+5` (§2.4): jumping is the way
past a known DART. Teleport/fear arrivals never land with a trap col under the body.

**Finding (hidden → known).** All traps are generated hidden. A known trap draws `T_TRAP`
(common id 10) in its cell; the room builder sets its attr from a 4-entry type table (DART
`$42`, GAS `$44`, TELEPORT `$43`, ALARM `$46`; ink on black, joins the legality set). A trap
becomes known when:
1. it **triggers** (DART stays known; one-shot traps are removed and the cell redraws as its
   normal id);
2. **Search = Wait** (↓ with no ladder below, §2.3; no new key, joystick-complete): each
   hidden trap in the current room on the hero's storey within **6 cols** of the body is
   found with **1 in 2** (gameplay RNG);
3. **Mage trap sense** (class ability, passive): at the end of every Mage turn, hidden traps
   within **2 cols** of his body on his storey are found (100 %). The Warrior must search.

Message on find: `YOU FIND A DART TRAP.` · `… A GAS TRAP.` · `… AN ALARM TRAP.` ·
`YOU FIND A TELEPORT TRAP.` (25). A known trap overrides any derived decor in its cell
(decor is cosmetic and re-derived on room entry, never stored).

**Counts and types per level (seeded from the level seed, `GEN_RNG`).**

| Depth | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| Traps | 1 | 2 | 2 | 3 | 3 | 3 | 4 | 4 |
| Type pool (uniform) | DART | DART, GAS | DART, GAS, TELEPORT | same | + ALARM | all 4 | all 4 | all 4 |

**Placement (generator, after floor items; each trap ≤ 8 seeded tries, else dropped).**
- Room: not start, not lair, not Sanctum; **≤ 1 trap per room**.
- Storey `s ∈ {0,1}` (random), col **`t ∈ 6..25`** (keeps the arrival bodies at x = 1 / 28
  and every door/arch col clear by ≥ 2 cols).
- For every footprint on that storey (ladder, shaft, hole, pit, arrival shaft, all
  `c … c+2`): `t ∉ [c−1, c+3]` (excludes caps and ladder-end cells). Not under or adjacent
  to a dead-end block or its rubble col. On storey 1, `t ∉ [p−1, p+3]` (pit landing zone).
  D1: not within the hero start body ±1.
- Not on a floor-item cell.
- Storage: **trap list ≤ 6 entries × 2 B**: room (4 bits), storey (1), col (5), type (2),
  known (1), spent (1), 2 bits spare. Spent entries are skipped (never compacted mid-level).

**Levelcheck invariants (B3B-6 checker extension).** Per seed and depth: trap count = table
(minus dropped tries, reported); ≤ 1 per room; none in start/lair/Sanctum; every `t` passes
the col rules above against the final room descriptors; types within the depth pool; all
generated hidden; no trap under a pit landing zone; Python == Z80 trap list byte-exact;
generator outputs before the trap step unchanged vs B3B-7.

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
its action. Exception to F4: a CONFUSED hero's reversed action that turns out illegal costs
the turn (`YOU STUMBLE.`, §6.4).

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
| Pause (Resume / Quit) | FIRE held + ↑ | — | BREAK |
| Page: move / verb / confirm / back | directions / ← → / FIRE / ↓ + FIRE | same | — |
| Close door, hit the Book | FIRE on the melee icon / bump | — | — |
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
- Shortcut keys confirmed: ENTER, `1`–`0`, `I`, BREAK, `.`. Default map Q/A/O/P/SPACE.
  Redefine rejects these (see §3.2, manager ruling 2026-10-05, designer-confirmed).
- Sinclair 1 or 2 selected: in game, the `1`–`0` slot shortcuts on that joystick's half of
  the number row are disabled (S1 = 6–0, S2 = 1–5); the other half and the icon bar keep
  working. This applies only in game; the menu (§3.2, user 2026-10-06) never reads joysticks.
- The joystick/redefined keys documented here are active from START only (menu: §3.2).

- ↙/↘ act as ←/→. Opposite keys cancel (F7). The cursor **skips unlearned slots** (empty
  outlines) but **does not skip greyed ones** (you may select a greyed icon to read its info
  line; FIRE on it is illegal, costs no turn, and prints the reason, e.g. `NO ARROWS`).
- **Both bars have a BAG icon** (Warrior slot 9, Mage slot 10). Layouts: §3.5.
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
WAZHACK   1 START   2 HERO: WARRIOR|MAGE   3 CONTROLS: KEYS|KEMPSTON|SINCLAIR 1|SINCLAIR 2   4 REDEFINE KEYS
```

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
  choose Resume/Quit; `QUIT? Y/N` stays FIRE or `Y` = yes, anything else = no (§3.1).
- **Kempston** (port `$1F`: bit 0 R, 1 L, 2 D, 3 U, 4 F) is read **only after it is
  selected**, because the port floats on a bare machine.
- **Sinclair 1** = keys 6 L, 7 R, 8 D, 9 U, 0 F. **Sinclair 2** = keys 1 L, 2 R, 3 D, 4 U, 5 F.
- Redefine asks for UP, DOWN, LEFT, RIGHT, FIRE (no duplicates).
  (Manager ruling 2026-10-05, designer-confirmed.) Reserved keys are rejected with the message
  `KEY RESERVED`: ENTER, `1`–`0`, `I`, CAPS SHIFT, SYMBOL SHIFT, and any key BREAK uses. The
  prompt stays on the same action. BREAK at any redefine prompt cancels the whole redefinition
  and keeps the previous key set.
- START seeds the RNG → generates D1 → play.
- **Title (user 2026-10-04):** the menu/title screen reads **"TOME OF THE DEAD"** (the concept
  screen's title), not WAZHACK. Torches animated and hero previews on the select screen follow
  `concept_menu` / `screen_menu.png` (designer decision 2026-10-04). Death `KILLED BY …`
  killer tracking is 3D (designer decision).

### 3.3 Panel at a glance (layout: concept-screen §5; approved round 5)

Rows 18–19: **10 icons 24×16** (cols `3i … 3i+2`), cols 30–31 = depth + key icon. Row 20: the
**info line** (selected icon's name, MP cost, range, bounces/notes). Row 21: HP / MP / FOOD
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
`THE BOOK IS DESTROYED` (21) · `NO ARROWS.` · `QUIVER FULL.` · `THE VAMPIRE TURNS INTO A BAT!` (28) · `YOU PICK UP 3 ARROWS.` ·
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
| 6 | Quick food | Lightning |
| 7 | Quick potion | Quick food |
| 8 | Quick scroll | Quick potion |
| 9 | **Bag** | Quick scroll |
| 10 | (empty outline; spare) | **Bag** |

- The Warrior has 9 icons (a spare 10th). The Mage has all 10.
- **Quick scroll** (new slot, needed to hold the scroll icon the approved panel shows): FIRE
  reads the quick scroll (1 turn; same effect as `READ` on the page). Auto-fill: the stack
  with the most scrolls, ties → Teleport, Fear, Sleep, Enchant (known types only, §8.8). `QUICK` on the page pins a type.
  It greys out with no scroll.
- Unlearned ability slots draw an empty outline and are skipped by the cursor.
- The cursor moves only in ICON MODE (↓ + FIRE, §3.1) or via `1`–`0`; the BAG icon opens the bag when used there.
- 3C (designer decision 2026-10-04): the Bow slot and quick food are greyed-but-selectable
  until found (see §3.1), not skipped.

---

## 4. Classes

| Stat | **Warrior** (Knight art, `$47`) | **Mage** (Wizard art, `$45`) |
|---|---|---|
| HP / MP at start | 24 / 6 | 16 / 12 (10 + Robe 2) |
| atk / eva / DEF | 3 / 2 / 1 (Leather) | 1 / 1 / 0 |
| Melee | Short Sword 1d6, reach 1 | Oak Staff 1d4, reach 1, own **STAFF_SWING** frame. Never greys out (the 0-MP fallback) |
| MP regen | +1 per 8 turns | +1 per 5 turns |
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

**Messages:** `YOU REACH LEVEL 5!` (18), then on L4/L8 `YOU STRIKE TRUER.` (17), on L6
`YOU FEEL NIMBLE.` (16). Death/win screens show `LEVEL n`.

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
| Placement (rev 5, designer decision 2026-10-03) | **1 class book per level D1–D7, plus a 2nd class book with 1 in 2 on D4–D7** (`GEN_RNG`; E ≈ 9 per run). **The D1 book lies in the start room.** D8 has none. The generator places a generic **class book** (`SPELLBOOK` / `WAR MANUAL`); *what it teaches is decided when it is read* (below), so generation never depends on hero state |
| Reading | Page verb `READ`, 1 turn on return; the book is consumed. Content, first match (gameplay RNG): **1.** an unlearned ability whose unlock depth (§4) ≤ the current depth → learn the earliest-depth one (rank 1; fills its bar slot); **2.** else **rank up** a known ability below rank 3, chosen uniformly; **3.** else a tome (Warrior Vigor, Mage Power, §4). So the D1 book always teaches the starter (Spark / Power Strike), each later ability arrives at its unlock depth (or on the next book read, if carried), and every other book is a rank-up. "Chance of new vs rank-up" (user) = rule 1 is deterministic (the §10 threat answers depend on the schedule); the rank-up target is the random part |
| Other class's book | 50 % per level. `READ` → "YOU GRASP LITTLE OF IT": Warrior +1 max MP, Mage +2 max HP; the book crumbles. Unchanged |
| Expected yield (E) | Warrior: 2 unlocks, 4 rank-ups (both to rank 3 by ~D6), ~3 Vigor. Mage: 5 unlocks, ~4 rank-ups (of 10 possible), ~0 Power. Mage ranks are the scarcer choice by design: 5 spells × 3 ranks cannot all max |

**Ability ranks (user 2026-10-03: repeat books level an ability; numbers designer decision
2026-10-03). Max rank 3; rank 1 = the §6.1/§6.2 row. Ranks are cumulative.**

| Ability | Rank 2 | Rank 3 |
|---|---|---|
| Spark (1 MP, r6, 1d4+1) | 1d4+2, range 8 | 1d4+3, CONFUSED chance 1 in 2 |
| Firebolt (3 MP, r12, 1d8+2, burst 1d4) | 1d8+3, burst 1d6 | 1d8+4, the burst **spares the caster** |
| Frost Shard (3 MP, r12, 1d6, 1 bounce, freeze 2) | freeze 3, 2 bounces | 1d6+2, freeze 4 (bosses halved, §6.4) |
| Drain Life (3 MP, r5, 1d6+1) | 1d6+2, range 8 | **2 MP**, 1d6+3 |
| Lightning (5 MP, r28, 1d8+3, 2 bounces) | 1d8+4 | **4 MP**, 3 bounces (loop guard 4 still binds) |
| Power Strike (3 MP, +2 hit, ×2, stun 1) | **2 MP** | stun 2 (bosses 1) |
| Whirlwind (4 MP, dmg +1) | dmg +2 | **3 MP**, to-hit +2 |

Daggers and the bow have no ranks (ammo is their limit).

**Display.** Icons are unchanged (no pip: the 24×16 art fills its 3×2 cells, a digit would
clash). The **info line name field** carries the rank as a roman suffix: `FIREBOLT II  3MP
RANGE 12  FIRE BURST`, `POWER STRIKE III` (16 = the name field max). Messages: `YOU LEARN
FIREBOLT!` · `FIREBOLT RISES TO RANK 2.` (25; longest `POWER STRIKE RISES TO RANK 3.` 29).

**Data / cost.** Hero state `ARANK` 2 B (2 bits × up to 5 abilities; 0 = unlearned, replaces
the learned-bit test). Rank table: 7 abilities × 3 ranks × 6 fields (MP, range, die, bonus,
bounces, effect duration/chance) = **126 B**; the engineer may keep it in bank 3 and copy the
hero's ≤ 5 current rows (30 B) into bank 2 on learn/rank-up, so casting reads one row as now
(0 extra T per cast). Read-time book code ~90 B bank 3; strings ~60 B raw (two message
stems + roman suffixes; ability names exist).

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
- Falls and the Book's aura ignore resistances.

### 6.1 Mage spells (dmg ignores DEF)

| Spell | Book | MP | Range | Dmg / type | Bounces | Effect | Projectile → impact sprites |
|---|---|---|---|---|---|---|---|
| **Spark** | D1 | 1 | 6 | 1d4+1 SHOCK | 0 | **1 in 4: CONFUSED 3** (§6.4; 3D) | spark_fly1/2 8×8 `$43` → spark_fizz1/2 8×8 |
| **Firebolt** | D2 | 3 | 12 | 1d8+2 FIRE | 0 | **burst**: bodies within 1 col of impact take 1d4 FIRE, **caster included** at point-blank (impact within 1 col of the caster's front col; ranks 1–2, intended; rank 3 spares him) | firebolt_fly1/2 16×8 alternating yellow `$46` / red `$42` per frame (**user 2026-10-06**) → firebolt_burst1/2 16×16 |
| **Frost Shard** | D3 | 3 | 12 | 1d6 COLD | **1** | **freeze 2 turns** (bosses 1); can freeze the caster after a bounce | frost_fly 8×8 `$45` → frost_crack **8×8** (**user 2026-10-06**: stays 8×8, not 16×16; revisit after playtesting) |
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
  1 FEAR, 2 CONFUSED, 3 reserved) · bit 4 POISON · bit 5 WEAK · bit 6 **STUN_GUARD** · bit 7
  reserved. Invariant: a group bit/kind is set ⇔ its timer nibble ≠ 0. `STATUS = 0` is the
  fast path (skip the whole step).
- `STMR1`: high nibble HOLD turns, low nibble MIND turns. `STMR2`: high nibble POISON turns,
  low nibble WEAK turns. **Max 15 turns** per effect.
- Per kind: an **immunity mask** (1 B: bits SLEEP, STUN, CONFUSE, FEAR, POISON), §9.1. The
  hero's mask = OR of worn gear (Silk Cloak: POISON).
- **Where (budget):** the 32-B entity record has **no free byte** (+0..+31 all assigned; +8
  POT frees only when the 3E bag replaces it). Recommended: a parallel **`ENT_STAT` table,
  16 slots × 4 B = 64 B in `BANK2_FREE`** (`slot*4`), byte 3 spare (e.g. the Vampire's
  fled-once bit). Engineer's choice; the record format stays.

**Status step** (start of the entity's own action phase, §2.2), in order:
1. POISON: decrement; if the new value is a multiple of 3, lose **1 HP** (ignores DEF and
   resistances; **never below 1 HP**: no source poisons monsters, so poison never kills).
2. WEAK, MIND: decrement; at 0 clear (end message, hero only).
3. HOLD: if set → decrement, **skip the action** (cooldowns do not tick); at 0 clear. If
   STUNNED just cleared, set STUN_GUARD.
4. Otherwise act; after the action, clear STUN_GUARD.

Because the step runs before the action, "duration *n*" = the entity loses exactly its next
*n* action phases, whether applied in phase 1 (a hero spell on a monster) or phase 2 (a
monster hit on the hero), with no "applied this turn" flag. Monsters in other rooms are
frozen in time: their timers pause.

| Effect | Does | Ends | Durations / sources |
|---|---|---|---|
| **FROZEN** | skip action; eva counts as **0** against it | timer; **any FIRE damage ≥ 1 thaws it** | Frost Shard 2 (COLD hit, also self after a bounce) |
| **ASLEEP** | skip action; eva 0 | timer, or **any HP loss** (incl. poison, aura) wakes it | Sleep scroll 8 (room), GAS trap 4 (hero) |
| **STUNNED** | skip action; eva 0; cannot parry | timer. **STUN_GUARD:** cannot be stunned again until it has taken one action | Power Strike 1 (hit, no kill), Ogre SLAM hit 1 (hero) |
| **CONFUSED** | hero: each turn-costing walk/bump/jump/facing-icon action is **reversed with 1 in 3** (turns, then acts the other way); if the reversed action is illegal the turn is spent (`YOU STUMBLE.`). Climbs, page verbs, quick food/potion/scroll and 0-turn turnarounds never roll. Monster: 1 in 2 its action is replaced by a step in a random direction (illegal → wait; walkers still never step to `x == pit col`); a confused monster never shoots | timer; Cure (hero) | Spark 1 in 4 → 3; Ghost touch 1 in 4 → 4 (hero) |
| **FEAR** | hero: **no melee-reach action** (melee, bump attack, Power Strike, Whirlwind) → illegal, no turn, `YOU ARE TOO AFRAID TO FIGHT!`; ranged, spells, items allowed. Monster: steps away from the hero; cornered (no legal step away) it melees if the hero is in reach, else waits; never shoots | timer; Cure (hero) | Fear scroll 6 (room); Necromancer **Dark Bolt** hit 1 in 3 → 3 (hero) |
| **POISON** | −1 HP every 3rd turn (step 1) | timer; Cure | Spider bite 9 (= 3 HP; Spider Queen 12), DART trap 6 |
| **WEAK** | the hunger-WEAK penalties (§7: atk −2, eva −1, dmg −1 min 1, no MP regen, no jump); **not cumulative** with hunger WEAK (the same penalties apply once) | timer; Cure | **Mummy curse** (below) 12 |

**Mummy curse (defines §10's "curse").** A Mummy (and the Golden Pharaoh) hit drains 5 FOOD
as before and, **1 in 3**, curses: WEAK 12. `THE MUMMY CURSES YOU!` WEAK is a hero-only
effect (no source targets monsters).

**Stacking / refresh.** Same effect again → timer = **max(current, new)**, never added. A
different effect in the same group **overwrites** kind and timer (a Frost Shard on a sleeper:
the COLD damage wakes it, then FROZEN applies). Groups are independent.

**Bosses** (`BOSS` flag: golden bosses, Ogre, Death Knight, Archmage): **immune to ASLEEP and
FEAR**; HOLD and MIND durations are **halved, round down; 0 = no effect** (Frost 2 → 1, as
before; Power Strike stun 1 → none; Spark confusion 3 → 1). POISON full.

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
- No overhead "Zz" FX: a persistent FX track would cost ~5k T/tick and a track slot.

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

---

## 7. Stats, hunger, food

**Combat and mana:**
- To-hit: `d20 + atk ≥ 10 + eva` (F1).
- Physical damage: `max(1, roll × resist − DEF)`. Spells: `roll × resist`, no DEF.
- Nat-20/1 stays off.
- MP regen as §4, halted when Weak. Mana potion +8. Amulet of Mana / Scarab halve the regen
  interval.

**Hunger** (`FOOD` 0–100, start 80): burns −1 per **6 turns**, a jump −2 extra. **Never fatal.**

The stage word is shown on the panel (row 21, 6 cells max, in the stage's attr). **Four
distinct stages, each name ≤ 6 chars:**

| Stage (panel word) | FOOD | Effects | Bar + word attr |
|---|---|---|---|
| **FED** | 50–100 | **HP +1 per 12 turns** (user: agreed) | `$44` |
| **OK** (was Peckish) | 25–49 | no HP regen | `$46` |
| **HUNGRY** | 10–24 | atk −1, MP regen halved | `$42` |
| **WEAK** | 0–9 | atk −2, eva −1, dmg −1 (min 1), no MP regen, no jump | `$42` + message every 50 turns (`YOU ARE WEAK WITH HUNGER.`) |

The Mummy curse applies the same penalties as the WEAK **status** (§6.4), not cumulative with
this stage. The panel hunger word stays FOOD-derived; the curse shows as a status icon.
Worn cursed gear does **not** affect regen (rev 5, §8.7).

| Food | FOOD | Source |
|---|---|---|
| Meat | +40 | floor (D2+), Orc drop 1/3 |
| Cheese | +30 | floor, Rat drop 1/4 |
| Pear | +20 | floor |
| Apple | +15 | floor, Goblin drop 1/4 |
| Carrot | +10 | floor |

Per level (E): ~450 turns ≈ 75 FOOD burned. Supply: 3–4 floor items + drops ≈ 100.

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
  Floor scrolls pick the type uniformly from the four.
- The **key** opens the lair door and is consumed.

**Quick slots auto-fill** (user):
- FOOD: the smallest FOOD value first.
- POTION: Heal, else Mana, else Cure.
- `QUICK` on the page pins a type until its stack runs out.
- SCROLL: the largest stack, ties Teleport → Fear → Sleep → Enchant (§3.5). Quick scroll = read.
- **Unknown types (§8.8) never auto-fill**: auto-fill considers only known types; if the bag
  holds only unknown potions/scrolls the quick slot greys out. `QUICK` on the page may pin
  an unknown type (deliberate use); the info line then shows its appearance name.

### 8.5 Per-level placement (floor list ≤ 32 entries)

Food 3–4 · potions 2–3 (≥ 1 Heal) · **scrolls 1–2** (rev 2: 1; E: 1–2 keeps the quick
slot alive) · gear 1–2 (depth-gated) · class book 1 (D1–D7) + 1 more with 1 in 2 on D4–D7
(rev 5, §5) · other-class book 0–1 ·
key 1 · **ammunition (rev 3; Warrior runs only: a Mage run generates no ammo entries):**

| Item | Per level | Notes |
|---|---|---|
| **Dagger stack** | **1 stack of 2–3** (`1d2+1`) on D1–D7; none on D8 | placed in a random non-start, non-lair room |
| **Arrow stack** | **1 stack of 5–8** (`1d4+4`) on D1–D7; D8 none | same |
| **Bow (user 2026-10-04; Warrior runs only)** | **Exactly 1 on D2**: a floor-list entry in a random non-start, non-lair room, **plus a 6-arrow bundle placed in the same cell** (extra to D2's normal 5–8 stack; the two merge on pickup per the one-stack-per-cell rule, capped 24). Generated regardless of RNG; never on other depths. If the bow is dropped it stays findable; if lost (pit fall) it is gone, and the run continues melee/daggers only | Pre-bow arrows (D1 stack) are picked up and kept; the bow icon stays greyed until the bow is in the bag |
| Skeleton Archer drop | Arrows ×3, 1/2 | D4, D5, D7 (§9.1) |
| Thrown-and-recovered | per §6.3 | not a placement; uses floor-list slots |

Supply estimate (E, whole run): daggers ≈ 3 + 7 × 2.5 ≈ 20 found + recoveries (×4 throws
each ≈ 80 throws if all are used); arrows ≈ 6 (D2 bundle) + 7 × 6.5 ≈ 52 found (start 0; D1 is dagger-only play, which the D1 balance row already assumes) + ~9 from Archers.
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

**Golden bosses** are a level kind with the `BOSS` flag.
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
not regenerate and is never rerolled. Archmage summons are discarded on leave.

Uniques on the floor shimmer with the same cycle (it counts toward the room's attr-cycle
cells). Panel and page use hardware FLASH.

### 8.7 Blessed and cursed gear (3E; user 2026-10-03: known states, no identification; rev 5 user 2026-10-03: hidden ± value, bless/shatter)

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

**Cursed value roll (designer decision 2026-10-03; out of 8, `GEN_RNG` at item placement):**

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
- A known re-arming DART trap is therefore a deliberate (costly: ~3.5 HP + POISON 6 per hit,
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
`TYPE` (item type id) · `QTY` (stack 1–9; ammo counts live outside the bag) · `ISTATE`:
bits 0–1 BUC (0 normal, 1 blessed, 2 cursed, 3 reserved) · bit 2 **HIDDEN** (rev 5: the
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
| Spider | 32×16 | 7 | 3 | 3 | 0 | 1d4 | 2 | walker | hit **poisons**: POISON 9 (= −1 HP / 3 turns ×3, §6.4) | — | D2, D4, D5 |
| Skeleton | 24×48 | 10 | 2 | 2 | 1 | 1d6 | 5 | walker, climber, opener | chase | — | D3, D5, D8 |
| **Vampire** | 24×48 | 14 | 2 | 1 | 0 | 1d6 DRAIN | 5 | walker, opener, acts every 2 (bat form: every turn) | **drain bite heals it** by the damage dealt (to max hp); **bat form** §9.2 | — | D3, D6, D8 |
| Ghost | 24×32 | 8 | 2 | 3 | 0 | 1d4 DRAIN | 3 | flyer | drift; touch 1 in 4 → CONFUSED 4 (§6.4) | — | D3, D6–D8 |
| Orc | 24×48 | 14 | 3 | 1 | 1 | 1d8 | 5 | walker, climber, opener | chase | Meat 1/3 | D4, D6, D7 |
| Skeleton Archer | 24×48 | 8 | 2 | 2 | 0 | 1d4; arrow 1d6 PHYS r10 | **6** | walker, climber, opener | ranged | Arrows ×3 1/2 (W) | D4, D5, D7 |
| Mummy | 24×48 | 18 | 3 | 0 | 2 | 1d8 | 5 | walker, acts every 2 | hit drains 5 FOOD; **curse** 1 in 3 → WEAK 12 (§6.4) | — | D5 |
| Necromancer | 24×48 | 12 | 2 | 2 | 0 | 1d4; Dark Bolt 1d6+1 DARK r8 | **6** | walker, opener | ranged, cooldown 2; Dark Bolt hit 1 in 3 → FEAR 3 (§6.4) | Mana 1/3 | D6–D8 |
| **Ogre Warlord** (unique) | **32×48** | 40 | 5 | 1 | 2 | 1d10+2 | **6** | walker, lair only | chase; every 3rd turn **SLAM**: reach 2, ×1.5 dmg, a hit STUNS 1 (§6.4) | unique | D4 |
| **Death Knight** (unique) | 24×48 | 50 | 6 | 3 | 3 | 1d10+3 | 5 | walker, climber, lair only | chase; **parries** 1 in 3 PHYS hits (BLOCK frame, 0 dmg); a parried melee hit **notches** the weapon 1 in 2 (§8.10) | unique | D7 |

**Death Knight silhouette (round 4/5):** an evil twin of the Warrior with a clearly distinct
outline: a **two-handed greatsword** (blade carried upright above the shoulder when walking,
chopped down in CLEAVE) and a **horned, crowned helm**. Do not reuse Knight frames. **5 frame
ids:** WALK1, WALK2, CLEAVE, BLOCK, DEAD (the rev-2 WIND-UP is dropped; HURT = flash).
| **Necromancer Archmage** | 24×48 | 40 | 4 | 3 | 1 | 1d6; Death Bolt 1d8+3 DARK r28, 1 bounce | **6** | teleports, never walks | boss caster | — | D8 |

Opener = it can open closed doors (1 turn). Locked/sealed doors stop all monsters. The
Ogre and Death Knight scale by depth like the rest.

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

**Ranged** (Archer, Necromancer), first match:
1. In melee reach → melee.
2. Hero in line (vertical overlap, not mid-ladder), `gap ≤ range`, the first body in line
   is the hero, cooldown 0 → **shoot** (cooldown: Archer 1, Necro 2).
3. `gap < 3` → step away.
4. Otherwise, walker rules.

**AI and resistances:** a monster never fires at a body that reflects its type.

**Archmage** (never leaves the lair), first match:
1. Summon cooldown 0, < 2 summoned Skeletons, a slot free, and the cap allows → **summon a
   Skeleton** (cooldown 6).
2. Hero in line → **Death Bolt** (cooldown 2).
3. Hero adjacent → **teleport** to the other storey (cooldown 4; attr flash).
4. Melee, else wait.

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
3. Otherwise humanoid chase and bite.
Flying over a pit is fine (flyer rules); on a ladder it cannot attack, as for any body.
Bosses never follow, so the Lord's bat form stays in its lair.
**Ogre:** a SLAM turn plays RAISE → SLAM.
**Death Knight:** a parry plays BLOCK and prints `PARRIED`.

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
| D7 | Orc, Skeleton Archer, Ghost, Necromancer | 14 | **Death Knight** |
| D8 | Necromancer, Skeleton, Ghost, Vampire | 10 + Archmage (+ ≤ 2 summons) | Archmage |

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
- Statuses are lost both ways (a poisoned monster recovers; a frozen one thaws).

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
  order at base tier; the lightest kind always passes. A unit is therefore **never lost**
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
hero. A teleport into a room (trap or scroll) is an entry with no followers; its arrival
point is the teleport cell.

**Cost (revised 2026-10-06 after LP measurement: mean 20k, worst 38.6k T).** **Accepted: mean
≤ 20k, worst ≤ 40k T once per transition.** 40k T is 0.57 of a 50 Hz frame, on a frozen screen
already paying ~45k room build + 100–130k decor, so it is under 25% of the transition. No
tick budget is used and the pool is not touched. Do not add tries to chase fewer waits. A
wait is cheap (the unit is retried on the next entry) and a few missing monsters on first
visit is acceptable. Target: waits ≤ 8% of first-entry units.

#### 9.4.4 Lair and bosses

- **Created on the first lair entry:** the boss (`LP_BOSS`) plus 1 escort (`LP_KINDS[rnd & 3]`,
  base tier, never tier-rolled), within Σ ≤ 12. The boss takes the legal cell farthest from
  the hero.
- **Banked like any room:** the boss's **exact hp persists** and it does not regenerate. The
  escort is banked too.
- Archmage summons are discarded on leave (their cooldown resets).
- The boss never follows. Its death sets the boss-dead flag: the grate opens and the trickle
  stops (§9.5).

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

### 9.5 Respawn trickle

Implemented in 3F. Tags: **U** = user 2026-10-03, **D** = designer decision 2026-10-03.

**Rule (U).** While the level boss is alive, the level slowly refills. The trickle stops
permanently the turn the boss dies (the flag is not re-armed on revisit or reload).

**Constants (D, named, tuning knobs).**

| Name | Value | Meaning |
|---|---|---|
| `RESPAWN_PERIOD` | 48 | check every 48 game turns (hero turn counter, `turn mod 48 = 0`) |
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
4. The room is not the boss lair (a lair holds boss + ≤ 1 escort, Σ ≤ 12, never topped up).

**Room choice (U + D).** Eligible rooms = all rooms passing 2–4. Pick one by weighted
random using the weight above (rooms with un-picked items preferred; every eligible room
has weight ≥ 1, so the fallback is automatic). No eligible room = skip.

**Kind (U + D).** Uniform over the level's own ≤ 4 kinds (§9.4), never the boss, an escort
unique, a summon or any `unique` kind. If the picked kind would break the cap, try the
next kind in the level's list once (cheapest-first not needed), else skip.

**Flags (U).** Respawned monsters get `F_RESPAWN`: **no drops** (the death-drop roll is
skipped) and XP / `RESPAWN_XP_DIV`. They are otherwise normal and may follow (prototype §3.7,
subject to the §9.3 cap) like any monster.

**Depth scaling (D).** None: period and chance are the same on every depth. Per-depth hp ×
count already rises ~25 % (§10) and per-kind weights grow with depth, so the cap and slot
limits throttle later depths automatically; a faster trickle would stack on that growth
and break the §10 threat curve.

**Placement (D).** Cell-legal, deterministic from the gameplay RNG (`RNG_STATE`, the
same stream as combat, so a seeded test replays; `GEN_RNG` is generation-only and
untouched). Draw up to 8 candidate cells in the chosen room; first legal one wins, else skip:
- Walkers: a floor-standing cell on a storey, not a ladder cell or pit cell, not a door
  cell, not in a ladder-end box (the 1-cell footprint at each ladder end), not occupied,
  and at least 6 columns from the hero if the room is visible.
- Flyers (Bat, Ghost, Vampire bat form not applicable at spawn): a cell inside the kind's
  flight band for the storey (same band as generation), same exclusions, over a pit allowed.
- The monster is created at full hp, in the **idle** state the generator uses for
  initial monsters (wakes when the hero enters its room or on a noise/hit); it takes no
  action on the spawn turn. The room map is not touched; spawning occurs outside the
  hero's room, so there is no render cost and no redraw beyond the normal room entry.

**Idle wave (U, gated by `IDLE_WAVE`, default off; D for details).** Enable only if
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
Short names ≤ 12 chars (messages, §6.4).

| Base (ink) | Tier 2 | Tier 3 | Stats hp/atk/eva/DEF/dmg | Ink | Ability (mechanic reused) |
|---|---|---|---|---|---|
| Rat (`$06`) | **Giant Rat** | | 5/1/1/0/1d3 | `$02` | bite 1 in 4 → POISON 6 (Spider poison) |
| | | **Rabbit Rat** | 8/2/3/0/1d4 | `$47` | **breeds**: hit and survives → 1 in 4 spawns one base **Rat** in the nearest legal cell (summon code, slot + §9.3 cap; `F_RESPAWN`); once per Rabbit Rat (`ENT_STAT` spare bit) |
| Bat (`$43`) | **Screech Bat** | | 5/2/4/0/1d3 | `$05` | bite 1 in 4 → CONFUSED 2 |
| Goblin (`$44`) | **Goblin Slinger** | | 8/2/1/0/1d4; rock 1d3 PHYS r6 | `$06` | ranged AI as the Archer (cooldown 2); rock = `dagger_spin` frames at `$06`, not recoverable; weight 3 + 1 |
| Spider | **Black Widow** | | 10/4/3/0/1d4 | `$02` | POISON 12; bite 1 in 4 → **ACID** (armour `m −1`, §8.10; rev 5 replaces ASLEEP 2) |
| Skeleton (`$47`) | **Skeleton Guard** | | 14/3/2/2/1d6 | `$05` | **parries 1 in 4** PHYS hits (Death Knight parry; 0 dmg, `PARRIED`, no BLOCK frame: the hit flash is skipped); a parried melee hit **notches** the weapon 1 in 2 (§8.10) |
| | | **Skeleton Knight** | 18/4/2/3/1d8 | `$44` | parries 1 in 3 (notch 1 in 2, §8.10); hit 1 in 4 → STUNNED 1 |
| Ghost (`$45`) | **Poltergeist** | | 11/3/3/0/1d4 DRAIN | `$03` | touch 1 in 3 → FEAR 3 (replaces the Ghost's confusion) |
| Orc | **Orc Berserker** | | 18/4/0/1/1d8+2 | `$02` | FEAR-immune; **rage**: hp ≤ ½ max → atk +2 |
| | | **Orc Bouncer** | 24/5/1/2/1d10 | `$03` | hit 1 in 3 → STUNNED 1 (a "bouncer" throws you out cold) |
| Skeleton Archer | **Skeleton Sniper** | | 10/3/2/0/1d4; arrow 1d8 r14 | `$04` | stands its ground (skips the "gap < 3 → step away" rule); Arrows ×3 drop 1/2 |
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
  80)` if `d ≥ TIER3_MIN_DEPTH` else 0. Roll `r` (gameplay RNG for respawns; the **room spawn
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

---

## 10. Balance sketch

Monster hp × count rises ~25 % per depth (depth scaling + kinds). XP levels (§4.1), ability
ranks and gear keep pace.

| Depth | Expected `LVL` | Hero at entry W HP/MP · M HP/MP (rev 5) | Threat | Key answer |
|---|---|---|---|---|
| D1 | 1 | 24/6 · 16/12 | soft | the D1 book in the start room |
| D2 | 2 | 28/7 · 19/14 | poison | Cure; Firebolt (Spider W) |
| D3 | 3 | 32/8 · 22/16 | first undead: Frost/Drain are useless | Firebolt (Vampire W); Whirlwind |
| D4 | 4 | 36/9 · 25/18 | archers, Ogre 43 hp; Black Widow acid | Drain Life on living Orcs/Ogre; close doors; bow |
| D5 | 5 | 40/10 · 28/20 | Mummy PHYS R, curse (WEAK 12, §6.4); first ALARM traps | Lightning; fire on Mummies; Cure; Scarab next |
| D6 | 6 | 47/12 · 31/22 | casters, ghost reflecting Lightning | Ring of the Grave; Firebolt on ghosts |
| D7 | 7 | 54/14 · 34/24 | Death Knight (parry + notch, fire reflect) | Lightning (W); Power Strike through parries; blessed weapon |
| D8 | 8 | 61/16 · 37/26 | Archmage + summons + bouncing bolt; reflects Frost/Lightning | Mirror Helm; Firebolt; potions saved |

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
**Mage:** opening with 2 Sparks at range costs ~0 HP. Mana economy is ~90 MP per level.

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
| Monsters drawn **M**: **Vampire**, Mummy, Orc, Necromancer, Spider 5 each; Archer 4 (HURT/DEAD = Skeleton) | WALK×2, ATTACK, HURT, DEAD | 29 | ~8,000 **M** | 4.2–4.6 KB per kind, Spider 2.75 **M** |
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
- **DEF (designer decision 2026-10-06):** 3D implements hero DEF (armour, e.g. Leather 1) in the damage formula. Monster DEF is 0 in 3D; the KX table adds it in 3E (no `kind_tab` change in 3D).
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
| D7 | Orc 4.6 + Archer 4.4 + Skel HURT/DEAD 0.9 + Ghost 2.9 + Necro 4.48 + **Death Knight 5.18** | 22.5 |
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
