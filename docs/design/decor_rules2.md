# DECOR2: composed decor placement (designer proposal 2026-11-09)

Status: **APPROVED (user 2026-11-09), scheduled post-C** (docs/plan.md "POST-TUT0 ROADMAP" item 4). Manager corrections: the P2 planner goes to bank-0 cold code freed by C, NOT an R6 page (R6 is pinned at the boot-block ASSERT, defs.asm:68); Q1 = no R6 page; other open questions take their defaults; D0 seeds re-searched after P1.
concept-screen §3.3 (see "Doc impacts"). It covers the decor deriver `decor_room`
(`src/decor_gen.asm`, bank 3) and its Python reference `tools/decorgen.py`.

Fixed constraints, all kept: decor is **re-derived from `RD_SEED`, never stored**. Colour is set only
through attributes. Decor never sits in a floor row and never changes a cell's solidity. Every
footprint goes on `T_AIR`. The animation budget stays ≤ 2 large animated objects, ≤ 4 glyph-swap
columns and ≤ 6 patch cells (D2: 13). The per-level id cap stays 28 (32..59) on D1–D7. The tutorial
D0 may use ≤ 10 distinct ids (`tools/tut0_level.py`). Sprite clash rules are unchanged: mount, ceiling
and patch objects stay in storey rows 0..5, and floor objects end on row 7 where sprites stamp over
them with attribute-follow. **DECOR2 needs no new art and no new tile ids.**

---

## 1. Diagnosis: why rooms look unnatural today

Sources: `decorgen.py` / `decor_gen.asm` as of `68cb36b`, the in-game screenshots
`assets/gfx/concept/Screenshot 2026-11-02 at 16.12.21.png` (D6) and `… 2026-11-03 at 18.39.30.png`
(D8), and the user's reference crops `… 14.48.37 / 14.49.39 / 14.50.17.png`.

| # | Symptom on screen | Rule / code that causes it |
|---|---|---|
| C1 | **Every object is placed on its own, with no relation to the others.** The pieces are scattered evenly but read as noise. Nothing is framed or paired, and nothing points at a focal point. | The menu loop makes 12 (D2: 19) independent tries, each `col = cmin + rnd(33 − w − 2·cmin)` and `s = rnd(2)` (`dg_obj`, `try_place`). The only relation between objects is the 1-cell ring, which forbids touching. |
| C2 | **Speckle: lone 1×1 brick fragments float in the void.** In the D8 shot one sits at (row 3, col 4), another at storey-1 col 28, and a third hangs in mid-air. | `COMMON` holds three 1×1 patch records (`WALL_DITHER/PATCH/FADE`) in every depth's menu. On D4 / D5 / D7, 4 of the 7 menu entries are patch records (3 common + `PATCH_A/B`), so most menu picks are speckle. Patch rows are `1 + rnd(6 − h)`, anywhere in cols 2..29. |
| C3 | **Accidental repetition.** Two identical banners stand 2 columns apart (D8 shot, storey 1), which looks like a mistake rather than a design. | Small menus: D4 / D5 / D7 have only 3 per-level objects. The ring forbids touching but not near-duplicates, so the same record can land 2 columns away. |
| C4 | **Decor ignores the room's structure.** Ladders, the exit grate, pits, doors and wall faces are never used as anchors. The user's references do the opposite: torches flank the throne (14.49), brick shows only around the torch's light (14.48), and a brazier hangs above a pedestal (14.50). | The structure only acts as a veto (footprint `T_AIR`, no ladder in the ring). Nothing pulls an object towards a feature. |
| C5 | **Brick patches have no reason to be where they are.** On a black back wall, visible brick should be where light reaches it or where the wall is worn: near light sources, corners and wall bases. | `patch_pass` uses uniform `col = 2 + rnd(29 − w)`, `r0 = 1 + rnd(…)`. |
| C6 | **Every room has the same density and mood.** The start room, the lair, dead ends and through-rooms all look alike, so a room tells no "story". | `decor_room` ignores `RD_FLAGS` (`RDF_START / LAIR / DEADEND / KEY`) and the room id in A ("A = room (unused)"). The same tries count is used for every room of a depth. |
| C7 | **Both storeys are treated the same.** There is no gradient: cobwebs are not concentrated high, moss and damp are not concentrated low. | Cobweb pass: a flat `rnd(2)` per corner candidate on both storeys. Moss is a single 1×1 cell at a random col of map row 9. |
| C8 | **Moss and chains are single isolated cells, so texture never builds up.** Moss reads as a stray pixel rather than growth. | The ring forbids any decor next to decor, so a moss strip or a 2-chain cluster is illegal. `MOSS` is `w = 1`. |
| C9 | **Objects crowd exits and walls.** A banner or torch can stand in col 1 / col 30, hugging a door arch or an open edge, and a floor brazier can stand in a pit's jump zone. | `dg_cmin` = 1 for mount / ceiling / floor (cols 1..30). There is no door-side or pit-zone exclusion: the ring checks ladders and decor only. |
| C10 | **Lights are placed at random, so the scene has no light logic.** A torch can appear alone in the middle of the room while the next room has two side by side. | Lights are ordinary menu entries. Only `MAX_LARGE = 2` limits them, so their count and positions are random. |

The three main causes are **C1 (independent uniform scatter)**, **C2 + C5 (1×1 patch speckle, placed
without any anchor)** and **C4 + C6 (structure and room role ignored)**. C3 and C8 are side effects
of C1 and the ring rule.

---

## 2. Proposed rules

All rules are deterministic from `RD_SEED` through the existing private xorshift (`dg_rng`). The RNG
call order changes, so outputs change (see §5). Where a rule says "room id", it means A at
`decor_room` entry. Storey row `r` maps to map row `9s + r`.

### R1. Remove the speckle (fixes C2)
The three 1×1 common patch records `WALL_DITHER`, `WALL_PATCH` and `WALL_FADE` leave the menu, which
keeps `CHAIN` as the only common record. Back-wall brick now appears **only as clusters**: the
level's `PATCH_A/B` (2×2 / 3×2), or the 3-cell composite on D1 / D8. The ids stay (the composite
uses them).

### R2. Moss grows in strips (fixes C8, part of C7)
`MOSS` becomes a **tiled 2- or 3-cell strip**: two records, w = 2 and w = 3, with the same id and
`F_TILED`. It stays on map row 9 only. **Every** cell of the strip must have `T_PLAT` / `T_WALLF`
directly above it (today only the first column is checked).

### R3. Clearances (fixes C9)
- **Wall and door margin:** mount, ceiling and floor objects use cols **3..28**
  (`dg_cmin` = 3 for those classes). Door arches, open edges and the wall faces always keep 2 clear
  columns. Cobwebs (corner pass) and wall-anchored textures (R7) are exempt.
- **Pit jump zone:** floor-class objects (braziers) never overlap cols `p−4 … p+W+3` of a pit (narrow
  or wide) on storey 0. Mount objects above the zone are allowed.
- **Halo for fill objects:** a menu (fill) placement of class mount or floor needs its ring widened
  to **3 columns** on each side (rows as today). This leaves ≥ 3 clear columns between unrelated
  objects and kills near-duplicates (C3). Planned objects (R5) and textures keep the 1-cell ring.

### R4. Room mood from role, depth and room id (fixes C6, C10)
Each room gets one **mood**, drawn once, first, from a per-role / per-depth weight table (data):

| Room | Mood rule |
|---|---|
| **Lair** (`RDF_LAIR`) | always **LIT**. The focal point on storey 1 is the exit grate. |
| **Start** (`RDF_START`) | always **CALM**: one composition on storey 0 (focal = the arrival shaft on D2+, CENTRE on D1), textures only on storey 1 (0 mount / floor fill objects). |
| **Key room** (`RDF_KEY`) | **LIT**, composition = CENTRE (a "shrine": the centrepiece flanked by lights). |
| **Dead end** (`RDF_DEADEND`, not key / lair) | DARK 2/3, DIM 1/3. |
| Ordinary, D1–D3 | LIT 1/4, DIM 1/2, DARK 1/4 |
| Ordinary, D4–D7 | LIT 1/4, DIM 3/8, DARK 3/8 (it gets darker with depth) |
| Ordinary, D8 | LIT 1/2, DIM 1/2 |

**Variety across a level:** the composition choice inside LIT uses `(rnd + room id) mod 3` over
{FRAME, CENTRE, GALLERY+light-storey}. Neighbouring room ids therefore rotate templates instead of
repeating them.

**Light lock:** once the planned lights are placed, the light budget is closed (`dg_nl := MAX_LARGE`).
The fill loop can **never** add a stray light (C10).

### R5. Compositions: anchoring and symmetry (fixes C1, C4)
For each storey a **focal list** is read from the descriptor (or one map-row scan):
- internal ladder (storey 1 body, cols `c..c+2`);
- up-exit / arrival shaft (storey 0);
- the lair grate (storey 1, row 17);
- a pit (storey 0 floor);
- a mid-room block face.

The storey's **widest clear span** is the longest run of cols in storey row 3 with no ladder, block or
wall, shrunk by 1 for the ring.

| Template | Placement (all on mount row 1, so torches, windows and banners keep one height per storey: user 2026-10-05) |
|---|---|
| **FRAME** | Pick a focal `F = (fc, fw)` (lair: the grate; start: the arrival shaft; else `rnd` over the list). Place **the depth's light object twice, mirrored**: left at `fc − g − lw`, right at `fc + fw + g`, with gap `g = 1 + rnd(2)`. The pair is **atomic**: if either side fails the fit, both are dropped and the storey falls back to DIM (one light on the side that fits). On floor-light depths (D3 / D5 / D8: `BRAZIER_BIG`; D2 `BRAZIER`) the pair stands on the floor and must also pass R3's pit zone. |
| **CENTRE** | A non-animated mount object (window / bookshelf / banner / tall banner, `rnd` over the level's) goes at the middle of the widest clear span. In LIT / KEY rooms it is flanked by the mirrored light pair, gap `g` as in FRAME. |
| **GALLERY** | `k` copies of one non-animated mount object (k = 3 if w = 1, else 2) at a **fixed pitch** `w + 3 + rnd(2)`, centred in the widest clear span (skipped if the span is too short). Deliberate rhythm replaces accidental repetition, and this is how the 3-object sets of D4 / D5 / D7 look designed. In the lair, the gallery on storey 0 is **aligned to the torch columns** below it (same cols), so both storeys share one axis. |
| **SINGLE** (DIM) | One light, wall-anchored (`cmin … cmin + 3` from a wall face or block face, side `rnd(2)`) or `g = 1` beside a ladder. |
| **(none)** (DARK) | No lights. |

Per mood:
- **LIT:** one storey gets FRAME or CENTRE with lights. The other storey gets GALLERY or an unlit
  CENTRE (`rnd(2)`).
- **DIM:** one storey (`rnd(2)`) gets SINGLE. Menu fill runs on both storeys.
- **DARK:** no lights. The texture odds in R7 are raised.
- **CALM:** see R4.

### R6. Light pools: brick shows where light falls (fixes C5; reference 14.48)
For each placed light, with odds 1 in 2 (DIM: always), place **one patch cluster on the light's outer
side** (away from its focal point; SINGLE: `rnd(2)`):
- col = `lc − pw − 1` (left light) or `lc + lw + 1` (right light);
- top row = light top row + `rnd(2)` (inside storey rows 1..5).

Patches may touch their own light (a ring exception for texture next to a light). Pools are
**asymmetric on purpose**: a pair gets at most one pool. That breaks the mirror, so FRAME reads as
built, not stamped.

### R7. Textures anchored to walls, with a vertical gradient (fixes C5, C7)
- **Guaranteed patch (kept: user 2026-10-05 "the patches must actually appear"):** if no light pool
  was placed, place one **wall-anchored** patch cluster. Its col is within 3 cols of the storey's
  left or right wall / block face (side `rnd(2)`), rows 1..5. The old random 8-try loop is kept only
  as a fallback. The 2nd patch keeps its 50 % odds and is also wall-anchored.
- **Cobwebs (high and dark):** the corner-candidate odds depend on storey and mood. Storey 0: 1 in 2
  (DARK: always). Storey 1: 1 in 4 (DARK: 1 in 2). LIT rooms: storey 0 only. The cap goes from 2 to 3
  in DARK rooms.
- **Chains cluster:** in DARK and DIM rooms the first chain placed seeds a cluster of 2–3 chains at
  pitch 2 (one clear col between), within 6 cols of a wall / block face.
- **Moss (low and wet):** D1 / D2 / D6, map row 9 only. DARK rooms try a strip first, other moods via
  the menu. Odds rise with depth wetness through the menu weight (data).

### R8. Fill, with negative space (fixes C1, C3)
After R4–R7, the old menu loop runs as a **fill** with fewer tries, set per mood (data): LIT 6, DIM 8,
DARK 6, CALM 0 on storey 1.
- Fill obeys R3's 3-col halo and the light lock.
- **Negative space:** each storey keeps one clear run of ≥ 8 columns in rows 1..7, which the halo
  plus the reduced tries give in practice. It is measured (§5), not enforced in code.

### Things deliberately NOT proposed
- **New vignette art** (ossuary corner, collapsed shelf, puddle) is deferred. It needs ids, and
  D1 / D3 / D8 are at the 28 cap. Q5 in §6 records what would unblock it.
- **Drips** (`drip7.asm`, bank 7, 1 B free) stay separate. Anchoring drips to moss strips is a later
  item (Q8).

---

## 3. Cost realism

Budgets as of the latest ledger (`docs/memory-map.md`, trap-cells entry):

| Region | Free |
|---|---|
| bank 3 (to `AY_RESERVE`) | **7 B** (kit 3) |
| bank 7 low | 1 B |
| R6 | 3 / 8 B |
| bank 0 / low RAM | 0 |
| bank-6 pool slack | **384 B** (the one-page cliff) |

Room build time: `decor_room` measures **~120k T** on D1 (W13 profile, DI, contended), out of a
room build that runs during `GS_TRANSITION` (the `NEXT_MAP` build before the scroll).

Useful facts for placing code:
- `ROOM_MAP` / `NEXT_MAP` (`$6000` / `$6300`), `ROOM_DESC` (`$6D60`), `LVL_DEPTH`, `xs_core`
  (bank 2) and levelgen's `rnd_mod` / `hla` (low RAM) are all visible whatever is paged at `$C000`.
  So decor **planning** can run from any `$C000` bank.
- `dg_obj` / `dg_ring` / `dg_bad` (and the records) live in bank 3, so **placement** must stay
  there, or move as a whole.
- On the 128K / +2, bank 6 is **uncontended** and bank 3 is contended, so planner code runs faster
  in R6.

| Rule | Class | Estimate (engineer confirms from `.sym`) |
|---|---|---|
| R1 drop the three 1×1 common records | **(a) data** | **−9 B** (3 × 3 B records; `DG_NCOM` 4 → 1) |
| R2 moss strips: records w = 2 / 3, tiled | **(a) data** | +3 B (one extra record) |
| R2 support check across the full width for ceiling objects | (b) | +2..3 B (`ld e,1` → `ld e,(dg_w)`) |
| R3 wall / door margin (`dg_cmin` 1 → 3 for mount / ceiling / floor) | **(a) data** | 0 B |
| R3 pit jump-zone veto for floor objects | (b) | ~15 B |
| R3 3-col halo for fill mount / floor | (b) | ~10 B (ring box ±k with k from a per-class byte) |
| R4 mood draw (`RD_FLAGS` + depth → weight table + room id) | (b) code, (a) table | ~25 B code + 16 B table |
| R4 light lock | (b) | ~4 B |
| R5 focal list, widest span, FRAME / CENTRE / GALLERY / SINGLE | **(c)** | ~200–240 B planner + ~30 B executor |
| R6 light pools | (c) (part of the planner) | ~30 B |
| R7 wall-anchored patch, cobweb odds by storey and mood, chain cluster | (b) / (c) | ~40 B (replaces most of `dg_patches`' random path: −40..60 B) |
| R8 fill tries by mood | (a) table | +4 B |
| **In-file reclaims** in `decor_gen.asm`: the dead `DC_BRICK` paths (`dg_req` computation, brick `cmin`; `decorgen.py` says they are unreachable) ≈ 13–15 B; the no-op `jr .nr` straight before `.nr:` (2 B) | reclaim | **≈ −15..17 B** |

### Where the (c) code goes (decision)
Split the deriver into a **planner** and an **executor**.

- **Planner `dg_plan`** goes in **R6** (bank 6, uncontended, `far6` from `decor_room`, 3 B call
  site). It reads only low RAM (descriptor, map, depth) and writes a **plan**: ≤ 5 entries ×
  (record index, row, col, pair flag) + a count. The plan goes into the **ROOM_DESC spare
  `$6DF0..$6DFF`** (16 B, level_defs.asm "spare"; always visible). It also needs a per-depth
  light / centrepiece table (~24 B). R6 growth: **+1 page (`R6_GROW` 15 → 16), paid from the pool
  slack 384 → 128 B**.
- **Executor** stays in bank 3: a loop that feeds each plan entry to `dg_obj` with a fixed row / col
  (no rnd calls), with pair atomicity and the outward ±1 / ±2 nudge on failure, ~30 B. It is paid by
  the in-file reclaims (−15..17 B) plus the retired random half of `dg_patches` (−40..60 B).

Not chosen, and why:
- **Moving the whole deriver to R6** (≈ 0.85 KB with `dg_bad`) needs 4 pool pages; the slack has 1.
- **An overlay** would cost a ZX0 unpack and a map save on every room entry.
- **Bank 7 cold code** has 1 B free.
- **Running the planner in levelgen and storing per-room plans** breaks "never stored", and low RAM
  is full.

If the pool page is refused (Q1), the fallback is the P1 package alone (below), which fits today.
P2 then waits for a ≥ 300 B reclaim in bank 3; `z80-architect` would scope it.

### Room-build time
- The planner costs ~8–15k T: a descriptor read plus one 32-cell row scan per storey (~1k T each),
  run in uncontended bank 6.
- Planned placements are 2–6 `dg_obj` calls, all with a fixed row / col. They replace ~4–6 fill tries
  and fail less often, because anchors are pre-cleared.
- Net: **within ±15k T of today's ~120k T**. Ceiling for the gate: **W13 profile ≤ 135k T, D1–D8
  worst room**. That is still under 3 frames of a transition that already scrolls for longer.

---

## 4. Recommended package

**P1 "Clean scatter", fits today (no move, no pool page):** R1 (a), R2 (a + b), R3 margin (a) +
halo (b) + pit zone (b), R7 cobweb gradient by storey (b, mood-free form: storey 0 1/2, storey 1
1/4), R8 fill tries table (a). Net ≈ +30 B code / −6 B data, paid by the in-file reclaims (−15..17 B)
plus the 7 B free. **It removes C2, C3, C8 and C9 and most of C7.** If the bytes run short, the pit
zone (15 B) is the first to defer.

**P2 "Composed rooms", recommended, needs Q1:** P1 + R4 (moods, roles, light lock) + R5 (FRAME /
CENTRE / GALLERY / SINGLE) + R6 (light pools) + R7 (wall-anchored patches, chain clusters, mood
odds). Planner in R6 (+1 page), executor in bank 3. **This is the version that fixes C1, C4, C5,
C6 and C10: the "best look per byte".**

**Build order:**
1. Python model first, in `tools/decorgen.py` behind no flag (it becomes the reference), with the
   §5 metrics.
2. Render the room PNGs for user review.
3. Then the Z80: P1 by `z80-junior` (Sonnet), and P2's planner + executor by `z80-staff-engineer`.

### Mocks
Legend: `#` wall / block · `=` floor · `H` ladder (row 8 / 17 = hole) · `G` lair grate · `^` door
arch · `D` door planks · `T` tall torch (2×4) · `W` arched window (3×4) · `B` banner (1×2) or tall
banner (2×5) · `S` bookshelf (2×2) · `p` back-wall patch cell · `|` chain · `~` moss · `w` cobweb ·
`r` rubble · `.` air. Sprites are omitted.

**Example 1: D1 ordinary room** (storey-0 left edge open, storey-1 right door, internal ladder c = 20).
*Before* (a typical seed today): two banners 2 cols apart, a lone torch mid-room, speckle patches,
single moss cells.
```
     01234567890123456789012345678901
 0   .....|........................w#
 1   .....|..TT...B..........WWW....#
 2   ........TT...B....pp....WWW....#
 3   ........TT......p.p.....WWW....#
 4   ........TT..............WWW....#
 5   ....p..........................#
 6   ...............................#
 7   ...............................#
 8   ====================HHH=========
 9   #..~.......~........HHH.......##
10   #.....B..B..........HHH..TT...^^
11   #.....B..B......p...HHH..TT...DD
12   #...................HHH..TT...DD
13   #...................HHH..TT...DD
14   #...................HHH.......DD
15   #...................HHH.......DD
16   #...................HHH.......DD
17   ================================
```
*After* (mood LIT, storey 1 = FRAME on the ladder, g = 1, light pool on the left torch's outer side;
storey 0 = unlit CENTRE: window flanked by banners; a chain cluster near the right wall; a moss
strip; cols 14..25 of storey 0 left empty as negative space):
```
     01234567890123456789012345678901
 0   ..........................|.|.w#
 1   .....B..WWW..B............|.|..#
 2   .....B..WWW..B.................#
 3   ........WWW....................#
 4   ........WWW....................#
 5   ...............................#
 6   ...............................#
 7   ...............................#
 8   ====================HHH=========
 9   #.~~~...............HHH.......##
10   #................TT.HHH.TT....^^
11   #.............pp.TT.HHH.TT....DD
12   #.............p..TT.HHH.TT....DD
13   #................TT.HHH.TT....DD
14   #...................HHH.......DD
15   #...................HHH.......DD
16   #...................HHH.......DD
17   ================================
```

**Example 2: D4 lair** (grate at c = 12 on row 17, ladder c = 24, locked door storey-1 left).
*Before:*
```
     01234567890123456789012345678901
 0   #..............................#
 1   #..TT..........BB..............#
 2   #..TT..........BB...p..........#
 3   #..TT.....pp...BB..............#
 4   #..TT.....pp...BB..............#
 5   #..............BB..............#
 6   #..............................#
 7   #..............................#
 8   ========================HHH=====
 9   ##......................HHH....#
10   ^^.................BB...HHH.TT.#
11   DD.................BB...HHH.TT.#
12   DD.....p...........BB...HHH.TT.#
13   DD.................BB...HHH.TT.#
14   DD.................BB...HHH....#
15   DD......................HHH....#
16   DD......................HHH....#
17   ============GGG=================
```
*After* (LIT, FRAME on the grate: torches mirrored about col 13, g = 1. Light pool on the left torch.
Storey 0 = GALLERY of tall banners **on the torch columns**, one shared axis with the boss on the
grate. Wall-anchored patch top right):
```
     01234567890123456789012345678901
 0   #..............................#
 1   #........BB.....BB..........pp.#
 2   #........BB.....BB..........pp.#
 3   #........BB.....BB.............#
 4   #........BB.....BB.............#
 5   #........BB.....BB.............#
 6   #..............................#
 7   #..............................#
 8   ========================HHH=====
 9   ##......................HHH....#
10   ^^.......TT.....TT......HHH....#
11   DD...pp..TT.....TT......HHH....#
12   DD...pp..TT.....TT......HHH....#
13   DD.......TT.....TT......HHH....#
14   DD......................HHH....#
15   DD......................HHH....#
16   DD......................HHH....#
17   ============GGG=================
```

**Example 3: D6 dead end** (left dead-end block with rubble, ladder c = 14, storey-1 right edge open).
*Before:* like example 1: a slim torch, barred window, banner and 1×1 speckle at random cols, and at
most one cobweb by coin flip. *After* (DARK: no lights. Cobwebs in three corners, a chain cluster by
the block face, `PATCH_B` anchored to the block, a moss strip, the bookshelf low by the wall: an
abandoned store):
```
     01234567890123456789012345678901
 0   ###w.|.|......................w#
 1   ###..|.|.......................#
 2   ###............................#
 3   ###.ppp........................#
 4   ###.ppp........................#
 5   ###............................#
 6   ###............................#
 7   ###r...........................#
 8   ==============HHH===============
 9   #w............HHH...~~~.........
10   #..SS.........HHH...............
11   #..SS.........HHH...............
12   #.............HHH...............
13   #.............HHH...............
14   #.............HHH...............
15   #.............HHH...............
16   #.............HHH...............
17   ================================
```
(The bookshelf at cols 3–4 obeys the R3 margin. The moss at cols 20–22 is one 3-cell strip.)

---

## 5. Validation plan

### New metrics in `tools/decor_density.py`
Over 1,000 seeds × D1–D8, every non-Sanctum room. Targets are what "more natural" means here.

| Metric | Definition | Target (P2) |
|---|---|---|
| speckle | 1×1 back-wall patch cells not part of a cluster | **0** |
| anchored ratio | visible objects (mount + floor + ceiling) that are a planned focal / pair / gallery member, or a texture within 3 cols of a light or wall face, ÷ all visible objects | **≥ 70 %** (report today's as the baseline) |
| mirrored rooms | rooms with ≥ 1 mirrored pair (same record, same row, symmetric about a focal ±½ col) | LIT 100 %; all rooms 30–60 % |
| near-duplicate | same record on the same storey within 6 cols, outside a pair / gallery | **0** |
| fill spacing | min / median gap between unrelated mount / floor objects on a storey | min ≥ 3, median ≥ 5 |
| negative space | largest object-free col run in rows 1..7, per storey | ≥ 8 cols in ≥ 90 % of storeys |
| clearance | mount / floor in cols 0..2 / 29..31; floor objects in a pit zone | **0 / 0** |
| roles | lair FRAME on the grate; start-room storey-1 fill objects; dead-end DARK share | 100 % / 0 / ≈ 2/3 |
| gradient | cobwebs on storey 0 ÷ all; moss cells in strips ≥ 2 | ≥ 65 % / 100 % |
| density | decor cells per room vs today, per depth | within ±15 % (D2 ~24.6 kept); bare rooms 0 % |
| budgets | large ≤ 2, glyph cols ≤ 4, patch cells ≤ max | unchanged asserts |

### `tools/decor_sweep.py`
- "ZERO placements: none" must still hold: every per-level object, both moss records and both
  cobweb glyphs appear.
- Add a per-depth **distinct-ids-per-room** histogram, to see how much the D0 search can choose from.

### Python == Z80
- `tests/world.py` W13 byte compare: the model moves with the code, so this is not a rebaseline.
- W13 profile ceiling: **≤ 135k T**.

### Tests and goldens that will change
Decor is visual only, and solidity is unchanged, so gameplay outcomes are untouched.

**Screen hashes to rebaseline** (any that show a decorated room):
- `tests/golden/game_start.hash`
- `game_start_wizard.hash`
- `abil_spark_cast.hash`
- `w15_panel_mage.hash` (if the play area is in its hash)

Not affected: menu / select / page / endcard hashes (no room decor). The `test` run confirms.

**Suites with decor-derived seeds or maps to re-check / re-pick:**
- `tests/trap_cells.py` (C3, L1–L3: a D5 DART under a floor object, so re-pick the room)
- `tests/drip.py` (drip sources depend on the map)
- `tests/tut0_level.py` + `tools/tut0_level.py`: re-run the seed search. A FRAME of tall torches
  alone is 11 ids > 10, so D0 rooms must land on unlit moods. The search finds those, since D1
  weights keep DIM / DARK / unlit CENTRE likely.
- `tests/budget.py` (`inject_decor`, `decor_tick`)
- `tests/flicker.py`, `tests/sanctum.py`, `tests/d8_stress.py`, `tests/items_model_test.py`,
  `tests/room_model.py`, `tests/lp.py`, `tests/t12.py`, `tests/h1climb.py`, `tests/gfx_integrity.py`,
  `tests/pt_bot.py` / `pt_mon.py`: these reference decor. Expect seed / cell-level asserts only.

---

## 6. Open questions for the user (defaults in bold)

1. **Pool page for the planner:** R6 +1 page, pool slack 384 → 128 B? **Default: yes.** Without it,
   only P1 ships now.
2. **Strength of symmetry:** strict mirrored light pairs with asymmetric textures, or a ±1 col
   jitter on the pair? **Default: strict pairs, asymmetric pools / cobwebs.**
3. **Lair framing:** always torches on the grate, plus the storey-0 gallery on the same axis?
   **Default: yes.** Should the D8 Sanctum frame the lectern the same way? **Default: yes**, if the
   Sanctum is decorated at all (it is excluded from the density sweep today).
4. **Start room calm:** storey 1 of the start room gets textures only (cobweb / moss / patch), no
   objects? **Default: yes.**
5. **Vignette art** (ossuary corner, collapsed shelf, puddle): needs ids. D4 / D5 / D7 have 1–3 spare
   ids; D1 / D3 / D8 are full. **Default: deferred.** DECOR2 uses existing objects only.
6. **Galleries on the small sets** (D4 / D5 / D7): repeat the same banner 2–3× deliberately?
   **Default: yes.**
7. **Mood weights** (§2 R4 table): **default as given.** They are tunable data after the user sees
   the PNGs.
8. **Drips anchored to moss strips** (bank-7 `drip7.asm`): **default: later, separate task.**

---

## Doc impacts (not edited here)

| Doc | Change |
|---|---|
| `docs/design/concept-screen.md` §3.3 | New section "Decor placement (DECOR2)" superseding "Decor placement (D1)" pass order: moods / compositions / pools / anchored textures / fill. Amend the patch rules (≥ 1 per room kept, now light- or wall-anchored, no 1×1 speckle), the cobweb pass (odds by storey and mood, cap 3 in DARK), moss (2/3 strips), the ring (3-col halo for fill mount / floor), cols 3..28 for mount / ceiling / floor, and the pit jump-zone veto. |
| `docs/design/game.md` §1.1 "In-room" row | "rules in concept-screen §3.3" → add "(DECOR2: moods by room role)". §1.2: no id or colour change; note that DECOR2 adds no tile ids. |
| `docs/memory-map.md` | `R6_GROW` 15 → 16 (`dg_plan` + its table), pool slack 384 → 128, **plan buffer at ROOM_DESC spare `$6DF0..$6DFF`** (claimed), bank-3 ledger (executor vs reclaims), `dg_bad` unchanged. |
| `tools/decorgen.py` docstring, `src/decor_gen.asm` header | Algorithm text, pass order, RNG call order, measured T-states. |
| `docs/design/tutorial_d0.md`, `docs/design/tut0_split.md` | D0 rooms follow DECOR2 at DEPTH 1 (the start-room CALM rule applies to room A). The seed search is re-run. Lit moods are effectively unavailable under the 10-id cap. |
| `docs/plan.md` | Tasks: DECOR2-1 Python model + metrics + PNGs (junior), user review, DECOR2-2 P1 Z80 (junior / Sonnet), DECOR2-3 planner (R6) + executor (staff), rebaseline + tut0 re-search (junior). |
| `docs/design/prototype.md` / `foundations.md` | No change. "Decor is derived from `RD_SEED`, never stored" still holds. |


**User addition (2026-11-09; priority: MORE OBJECT TYPES over density):** some levels feel empty — DECOR2 must also raise density where it reads empty (per depth / room role, measured by tools/decor_density.py) and plan MORE object types: list per depth the free per-level tile ids, an id-reclaim plan where none are free (D1/D3/D8), and an art brief for new objects (vignettes deferred earlier — revisit).
