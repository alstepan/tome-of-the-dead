# Tome of the Dead — Screen concept

> Status: **rev 3 (M1, 2026-10-02) — concept approved in round 5.** Rev 2 was the layout
> revision after the user's first concept review: the V1 family, with the bottom panel grown
> to 6 rows, larger decor, brick patches and per-level floor colours. **Rev 3 replaces the
> panel** with the approved round-5 design: **10 icons 24×16**, a full info line, bars with
> the hunger word and ammo, a 2-row log beside a 4-slot 16×16 gear block, an ornament on
> row 17; and adds the **custom fonts** (§5.1). Approved reference image:
> `assets/gfx/concept/screen_d7_fortress.png` (a concept render: its glyph widths are
> 8 px, the real text is 6×8).
> Mechanics and numbers are owned by `game.md`. Where the two differ, game.md wins. This doc
> stays consistent with `budget.md` §6–§8, `prototype.md` §4 and `foundations.md` F9.
> Coordinates are **(col, row)** on the 32×24 char grid, 0-based.
> The rev-1 V1/V2 comparison is superseded. V2 was rejected and V1 was revised.

## 1. Fixed rules every mock obeys

- **F9 zoning:** air bands are black paper. Floor rows are a coloured band, with
  `ATTR_FLOOR[depth]` per level (§3.4). Sprites, projectiles and FX only ever cover
  black-paper cells. **Decor lives only in air bands**, never in floor rows. That keeps the
  "every floor-row cell outside holes = `ATTR_FLOOR`" assertion true. Holes are now ladder
  holes, pit cells and the exit grate.
- Walls: `WALL` takes `ATTR_WALL[depth]` in air rows and `ATTR_FLOOR[depth]` in floor rows.
  Ladder: 3 cols wide, `$02`. Its top cell row is the **hole** in the floor above.
- Hero 24×48 (6 rows), CAST2 32×48. Goblin 24×32. Skeleton/Vampire/Mummy/Orc/Necro 24×48.
- **Animated decor under a sprite footprint pauses.** Re-blitting the sprite over it would
  cost 12–28k T (budget §6).
- Row 0 has an implied ceiling. Lower-storey ceiling decor hangs from the underside of the
  upper floor row.

## 2. Layout: **2 × 9 + 6** (decided)

| | rev 1 V1 | **rev 2** |
|---|---|---|
| Storey height | 10 rows | **9 rows** |
| Storey 0: air / floor | 0–8 / 9 | **0–7 / 8** |
| Storey 1: air / floor | 10–18 / 19 | **9–16 / 17** |
| Hero standing rows (storey 0 / 1) | 3–8 / 13–18 | **2–7 / 11–16** |
| Headroom over a 48-px hero (jump band) | 3 rows | **2 rows = 16 px** |
| Bottom panel | rows 20–23 (4) | **rows 18–23 (6)** |
| Action icons | 16×16 | **10 × 24×16** (3×2 cells; rev 3, was 24×24 in rev 2) |
| Info line | — | **row 20, 42 chars, 6×8 font** (rev 3) |
| Message log | 1 row | **2 rows**, 32 chars each, 6×8 font |
| Worn gear | 5 × 8×8 strip | **4 × 16×16 block** |
| Room map / climb turns per storey | 640 B / 10 | **576 B / 9** |

**Jump consequence.** The jump peak is **16 px**. A jump clears **bodies ≤ 16 px tall**
(Slime, a grounded Bat) and pits, but nothing taller (game.md §2.4). Jump frames rise at
most 2 rows. Their footprint stays inside the storey's own air rows, so the hero's top
reaches row `9s` exactly. A 3rd headroom row would have allowed clearing 24-px bodies, but
nothing in the roster is that height. **Door** height: lintel row `9s`, arch row `9s+1`,
planks `9s+2 … 9s+7`. **Flyer range:** Bat 7 rows of positions, Ghost 5.

## 3. Mock scene: room + characters + decor

Legend: `#` wall · `=` floor · `<`/`>` pit caps · `o` pit (black, floor row) · `H` ladder
(row 8 = hole) · `^` door arch · `D` door planks · `M` Mage (CAST2) · `S` Skeleton ·
`G` Goblin · `*` projectile (sprite) · `T` tall torch · `t` small torch · `b`/`B` brazier
flame/bowl · `c` candles · `w` cobweb · `~` moss · `|` chain · `F` banner · `k` skulls ·
`d` drip · `x` barred window · `p` brick patch (missing plaster) · `r` rubble · `.` air.
Panel glyphs: §5. (In the grid below the panel rows show *cells*, not text widths: log and
info text use 6-px glyphs, 4 chars per 3 cells.)

```
     0         1         2         3
     01234567890123456789012345678901
 0   ###w............................
 1   ###.........................TT..
 2   ###...xx..SSSpp.............TT..
 3   ###...xx..SSS...............TT..
 4   ###.......SSS...............TT..
 5   ###.......SSS...................
 6   ###.......SSS........b..........
 7   ###r......SSS........B..........
 8   ###=============<ooo>===HHH=====
 9   #w......~~.....F........HHH.|.##
10   #.t............F........HHH.|.^^
11   #.t.MMMM..............p.HHH.|.DD
12   #...MMMM................HHH...DD
13   #...MMMM...**......GGG..HHH...DD
14   #...MMMM...........GGG..HHH...DD
15   #...MMMM...........GGG..HHH...DD
16   #.c.MMMM.........k.GGG..HHH...DD
17   #==============================#
18   111222333444555666777888999000D7
19   111222333444555666777888999000K.
20   FIREBOLT 3MP RANGE 12 FIRE BURST
21   h####14m####12f####FED........SS
22   LLLLLLLLLLLLLLLLLLLLLLLLWWAAHHCC
23   LLLLLLLLLLLLLLLLLLLLLLLLWWAAHHCC
```
Every grid line is exactly 32 cells. Panel rows: icons `1–9, 0` (24×16 each; the Mage's
selected icon is slot 3, Firebolt) · `D7` depth · `K.` key icon · row 20 info line · row 21
`h` heart, `####` 32-px bars, numbers, `m` drop, `f` drumstick, `FED` hunger word, `SS` hero
status icons (cols 30–31, rev 4), cols 24–29 blank here: the Warrior shows `D3 A06` (daggers 3, arrows 6); the Mage mock has none · `L` log (24 cells = 32 chars) ·
`WWAAHHCC` worn gear (weapon, armour, helmet, charm). Row 17 is the storey-1 floor and
carries the panel **ornament** (a decorative border in `ATTR_FLOOR`, same cells, no new
attrs; approved round 4).

### 3.1 Structure (exact extents)

| Element | Cols | Rows | Tile / attr |
|---|---|---|---|
| **Dead end** (storey 0, left): solid block, no exit | 0–2 | 0–7 (+ floor 8) | WALL `ATTR_WALL` (`ATTR_FLOOR` in row 8) |
| Rubble at its foot | 3 | 7 | RUBBLE |
| Open horizontal exit (storey 0, right) | 31 | 0–7 | AIR |
| Storey 0 floor | 3–15, 21–23, 27–31 | 8 | PLATFORM `ATTR_FLOOR` |
| **Pit** (3 cols) + caps | pit 17–19, caps 16 / 20 | 8 | AIR `$00` (hole) / PIT_L, PIT_R `ATTR_FLOOR` |
| Ladder (storey 1 ↔ 0) | 24–26 | 8 (hole) – 16 | LADDER_L/M/R `$02` |
| Left room edge (storey 1) | 0 | 9–16 | WALL |
| Lintel / **door arch** / **planks** (closed), 2 wide | 30–31 | 9 / 10 / 11–16 | WALL / DOOR_ARCH_L/R / DOOR_L/R `$06` |
| Storey 1 floor | 0–31 | 17 | PLATFORM / WALL `ATTR_FLOOR` |

**Door = 5 tile ids:** arch L/R, plank L/R, and a plank-R variant with a lock plate for
locked or sealed doors. Sealed doors use the plank attr `$02`. **Open:** the planks are
redrawn as AIR and the arch stays. The door belongs to the **connection**: it is drawn in
both rooms (cols 30–31 here, cols 0–1 in the neighbour) and has one state bit.

### 3.2 Characters

| Who | Cols | Rows | Frame / attr | Notes |
|---|---|---|---|---|
| **Mage**, storey 1, facing right | 4–7 (body 4–6, staff 7) | 11–16 | CAST2 32×48 | casting |
| Firebolt mid-flight | 11–12 | 13 | sprite 16×8 `$46` | flight row = body top + 2 |
| Goblin, storey 1, facing left | 19–21 | 13–16 | WALK1 24×32 | target |
| Skeleton (tall), storey 0 | 10–12 | 2–7 | WALK2 24×48 | |
| *Alt: Warrior* | 4–8 | 11–16 | POWER_STRIKE 40×48 | 2×2 power-burst glyphs at the target's front cells |

On-screen: weight T5 + M3 = 8 ≤ 12 (game.md §9.3). The bolt belongs to the hero's phase 1.

### 3.3 Decor catalogue (tile ids: 64 = 32 common + 32 per level)

Glyph swap ~0.55k T/cell/step, attr cycle ~0.12k T/cell/step (budget §6).

| # | Object | Size (cols×rows) | Ink / paper | Anim | New ids |
|---|---|---|---|---|---|
| 1 | ~~Wall torch (small)~~ **REMOVED 2026-10-19 (DEC1)**; ids 15/16 now BONES | — | — | — | — |
| 2 | **Tall torch** (Barbarian / PoP), see below | **2×4** | flame `$46`/`$42`, bowl + bracket `$06` | flame tips: **glyph swap 2 frames** + attr cycle; flame body: attr cycle | **10** |
| 3 | Brazier | 1×2 | flame `$46`, bowl `$07` | glyph swap 2 + attr cycle | 3 |
| 4 | ~~Candles~~ **REMOVED 2026-10-19 (DEC1)**; id 31 now BONES | — | — | — | — |
| 5 | Dripping water | 1×1 | `$45` | glyph swap 2, hold 12 | 2 |
| 6 | Cobweb | 1×1 | `$07` | — | 1 |
| 7 | Hanging chain | 1×N | `$07` | — | 1 |
| 8 | Banner | 1×2 | `$43` | — | 2 |
| 9 | ~~Skulls & bones~~ **REMOVED 2026-10-19 (DEC1)**, replaced by **Dead skeleton (BONES) 4×1**, see "Dead skeleton (DEC1)" below; id 13 is its tile 0 | 4×1 (standing row) | `$47` | — | 0 new (common 13, 15, 16, 31) |
| 10 | Barred window | 2×2 (1 glyph tiled) | `$05` | — | 1 |
| 11 | Moss (under a floor) | 1×1 tiled | `$04` | — | 1 |
| 12 | Rubble | 1×1 | `ATTR_WALL` | — | 1 |
| 13 | Bookshelf | 2×2 (1 glyph tiled) | `$06` | — | 1 |
| 14–15 | **Wall set (artist round 3): DARK · DITHER · PATCH · FADE** on a black background, see below | 1×1 each | `ATTR_WALL[depth]` on black (`$07` reads light, `$01` reads dark) | — | **4** (they replace the rev-2 patches ×3 + WALL2) |
| 16 | ~~Cauldron (bubbling)~~ **SUPERSEDED by DEC2 (removed 2026-10-26)** | 2×1 | `$44` | glyph swap 2 | 3 |
| 17 | **Lectern + Tome** (D8 Sanctum, attackable, game.md §1.3) | 2×2 | lectern `$06`, book `$43` | flash on hit | 4 |
| — | Door (§3.1) / grate over the exit hole / pit caps | 2×8 / 3×1 / 1+1 | `$06` / `$07` / floor | — | 5 / 1 / 2 |

**Designer decision 2026-10-03:** per-level sets are capped at **28 ids (32..59)** for D1–D7
(D1's 28-id example fits exactly); ids 60..63 are reserved for attackable objects (D8 lectern).
Pit caps alias the platform-end glyphs (end shape facing the hole, game.md §2.5), DARK
aliases the brick glyph, and common id 10 is the reserved spare once potions leave the map.
**Rev 4 (designer decision 2026-10-03):** common id 10 = **`T_TRAP`**, a revealed trap: one
8×8 pressure-plate glyph in the standing row (row 7 / 16, like skulls), low in the cell; attr by
trap type from a 4-entry table (DART `$42`, GAS `$44`, TELEPORT `$43`, ALARM `$46`), game.md
§1.5. Sprites stamp over it like any standing-row decor. **Status tints** (game.md §6.4) recolour
a body's stamp attr: FROZEN `$45`, ASLEEP `$41`, STUNNED `$07`, CONFUSED `$43`. **Gear state**
(§8.7): BLESSED icons/glyphs `$45`, CURSED `$42`, cell-uniform. **Tier inks** (§9.6): palette
`$02 $03 $04 $05 $06 $44 $47`, same frames.
Any set over 28: drop the arched window and pillar first.

**Open-door jambs and lair grate (designer decision 2026-10-03; user 2026-10-03: option B):**
`door_jamb_l` = `#.#.....` x8 rows, `door_jamb_r` = `.....#.#` x8 rows, ink `$06` on black,
non-solid; the same glyph down all 6 opening rows (rows 11-16) of a 2-col door, replacing the
AIR the opened planks leave. They are **common ids 11 (`T_DOOR_JAMB_L`) and 14
(`T_DOOR_JAMB_R`)**, since every level has doors. `T_COBWEB` (was 11) and `T_MOSS` (was 14)
leave the common range and become ordinary **per-level** decor ids (32..59), spent only by
levels that use them. A set over 28 drops the arched window and pillar first. `T_SKULLS` (13),
`T_CHAIN` (12) stays common. Ids 17/18 (were `T_DRIP1/2`) become the ammo item glyphs
`T_DAGGERS` / `T_ARROWS` (game.md §6.3, 2026-10-12); drips become per-level decor if they are ever placed. Id 10 remains the reserved spare (potions
unchanged). Lair grate = common id 26 `T_GRATE`, ink `$07`, over the 3-col down-exit hole on
floor row 17 (no change). Source: `assets/gfx/concept/grid/b10_door_grate.tiles` (branch feat/3b-tiles).

**Solidity (designer decision 2026-10-03):** wall-set glyphs (#14-15: DARK, DITHER, PATCH,
FADE, worn/broken variants) are SOLID and replace only already-solid wall cells; rubble,
skulls, moss, cobweb, chain, banner, candles, drips are non-solid and go only on non-solid
cells. Decor never changes a cell's solidity (game.md §1.2). **Amended 2026-10-05:** the
back-wall patches (DITHER, PATCH, FADE, PATCH_A/B) are non-solid and go on `T_AIR`.

**B3B-8 answers (designer decision 2026-10-03):**
1. Rule is solidity by the class of the cell a tile is placed on, never per art type. Pillar and
   plaster-patch placed on wall cells: SOLID (ok). Window and bookshelf: NON-solid, placed
   only on air (room-interior) cells, as in game.md §1.2. If the builder ever puts them on
   wall cells they must become SOLID; never mix.
2. Row 17: no end caps beside down-exit holes; ornament runs to the hole edge. Approved.
   Caps stay on pits only.
3. Arrival shaft: rubble in row 0 above the ladder. Approved.
4. 3B stand-in: lair grate always open, drawn as an open hole; `T_GRATE` unseen until 3F. Confirmed.
   **SUPERSEDED, designer decision 2026-10-04 (B12):** the level exit must read as distinct.
   Common id 26 `T_GRATE` becomes the **raised-portcullis frame**, drawn from 3B on over the 3
   cells of the exit hole on row 17: glyph = a 3-px bar across rows 0-2 of each cell with 2-px
   teeth hanging at cols 0,3,6 down to row 4, rows 5-7 clear (the hole stays see-through and
   walkable), ink **`$46`** (bright yellow) on black, non-solid. No ordinary hole uses `$46` or
   this glyph. Plus a lit marker: the standing row (row 16) cell above the hole centre gets
   the existing `T_CANDLES`-style glow only if free; otherwise none. 3F closed state = a
   second glyph (full bars, ink `$07`), a new common id taken by dropping the per-level window
   or pillar; open/closed swap is a tile-id swap on the same 3 cells. Artist: 1 glyph now
   (id 26 redraw), 1 in 3F. Log hint: first entry to the lair room each level, one line
   `A GATE GLEAMS. THE WAY DOWN.` (28 chars); in 3F while closed: `THE GATE IS BARRED.`
5. Dropping raw item/tile data from the sprite sources in B3B-13: acknowledged (engineering call).

**Tile ids: 64 = 32 common + 32 per-level** (game.md §1.2). The artist's round 1+2 decor
comes to 93 ids, so the large objects live in **per-level sets**. A set's glyphs and attrs
are copied in from bank 7 spare at level start (8 sets, 2,304 B).

| Bank | Ids | Count |
|---|---|---|
| **Common** | AIR, PLATFORM, WALL, LADDER ×3, PLATFORM_END ×2, door 5, grate 1, pit caps 2, rubble, cobweb, chain, skulls, moss, candles, small torch, drip ×2, wall set ×4 (dark/dither/patch/fade) | **29** + 3 spare |
| **Per-level set** (≤ 32 each, picked in G2) | the large objects: tall torch, big brazier, tall banner, arched window, pillar, slim torch, bookshelf, cauldron, banner, barred window; lectern (D8 only) | e.g. D1: tall torch 10 + arched window 12 + pillar 6 = 28 |

**Flames are cut from 3 to 2 frames** (−2 ids per object). POTION, CHEST, ZAP1 and ZAP2 are
retired: floor items come from the 8×8 item-icon table, and the zap is now a projectile sprite.
The table above lists the rev-1 small decor plus the new objects; the artist's measured
sizes override the "New ids" column.

**Tall torch (2×4)**, top to bottom:

| Row | Content | Anim |
|---|---|---|
| 0 | flame tips, L/R × 2 frames | glyph swap |
| 1 | flame body, L/R | attr cycle `$46→$42` |
| 2 | bowl, L/R | — |
| 3 | wall bracket, L/R | — |

- Mounted on a wall face with the bottom row ≥ 1 row above the standing row, so it never
  sits in a floor row. A storey has rows 0–7, so the torch fits rows 1–4.
- Its silhouette reads at 2× the size of the small torch, which is what the
  Barbarian / Prince of Persia look needs.

**Walls (user, rev 2b): black background with occasional dithered light-brick patches.**
The air-band wall is plain black, with no solid plaster. Here and there a patch of brick
shows through as a **dithered** pattern: a 50 % checker/ordered dither of brick courses,
lighter at the patch centre and fading out at its ragged edge. Artist round 3 uses 4
tiles:

| Tile | Use |
|---|---|
| DARK | plain face |
| DITHER | sparse brick |
| PATCH | patch core |
| FADE | patch edge |

Patches combine them into irregular shapes up to 2×3. Ink is the level's wall ink: `$07`
reads as light brick, `$01` as dark.
A sprite passing over a patch recolours its bricks (attribute-follow, F9), the same
accepted artefact as any decor.
Patch rules (**amended 2026-10-05:** patches go on the black back wall = `T_AIR`, non-solid,
≥ 1 per room guaranteed; see "Decor placement (D1)" below):
- ≤ 6 patch cells per room;
- never in the 2 rows directly above a floor row (keeps the sprites' feet clean);
- never adjacent to a ladder.

**Per-level colour schemes** (artist round 2; attr-only, no ids; game.md §1.2):

| Depth | Scheme | `ATTR_FLOOR` | `ATTR_WALL` |
|---|---|---|---|
| D1 | Blue Keep | `$0F` | `$01` |
| D2 | Green Caves | `$27` | `$04` |
| D3 | Red Crypt | `$17` | `$02` |
| D4 | Orc Warrens (cyan) | `$28` | `$05` |
| D5 | Sandstone Tombs | `$30` | `$06` |
| D6 | Bone Catacombs (white) | `$38` | `$07` |
| D7 | Iron Fortress (bright blue) | `$4F` | `$41` |
| D8 | Sanctum (magenta) | `$1F` | `$03` |

Patches and WALL2 follow the wall ink.

**Animated-decor rule (per room, staggered):** **≤ 2 large animated objects**, and in total
≤ 4 glyph-swap cells + ≤ 8 attr-cycle cells. That includes a unique item's floor shimmer.
The worst case is 4 × 0.55 + 8 × 0.12 ≈ **3.2k T ≤ 4.0k**.

**Drip placement (designer decision 2026-10-04; for tools/decorgen.py + src/decor_gen.asm).**
`T_DRIP1`/`T_DRIP2` (common 17/18, `$45`, non-solid) are one animated pair:
- **Levels:** D1..D7 all; themes D2 Green Caves, D3 Red Crypt, D5 Sandstone Tombs, D6 Catacombs
  get up to 2 per room, the rest (D1, D4, D7) up to 1; D8 Sanctum none.
- **Cell:** an AIR (non-solid) cell whose cell directly above is SOLID (storey ceiling, or the
  floor-row platform above); the cell below is AIR and the drip is in the **upper half of its
  storey**: storey row 0..2 only (never rows 3..7), so it reads as hanging from the ceiling.
- **Never:** in a floor row; in the 2 rows above a floor row (sprite feet/heads); on or adjacent
  (col +-1) to a ladder column, door cell, jamb, grate, pit cap, exit hole; on a cell holding any
  other decor, item, trap or spawn; adjacent to another drip (min 6 cols apart).
- **Animation:** one ANIM_LIST entry per drip, type **glyph swap 2 frames** DRIP1<->DRIP2, hold
  12 ticks, phase staggered by cell index. Counts against the room budget (<= 4 glyph-swap cells,
  <= 2 large animated objects not affected): the deriver places drips **last**, only if the
  room's glyph-swap total stays <= 4; otherwise skip. Paused under a sprite footprint (rule §1).
- Deterministic: candidate cells scanned left-to-right, top-to-bottom, chosen by the level-seed
  LCG; same seed gives the same drips.

**Decor placement (D1; user 2026-10-05 points marked *user*, the rest designer decision
2026-10-05; for tools/decorgen.py + src/decor_gen.asm, Python == Z80).** Supersedes the
random `r0` row for every class except back-wall patches and brick decor.

*User 2026-10-05:* heights must look deliberate: windows and torches share one height per
storey; candles one height; the cobweb is a corner sprite and goes only in a corner; the
plaster patches must actually appear; anything standing on the floor sits on the floor, never
floating.

Storey rows `0..7` (map row = `9s + r`); row 7 = **standing row**, row 8 = floor.

| Class | Objects | Row rule (no rng) | Cell rule |
|---|---|---|---|
| **Mount** | small/slim/tall torch, barred + arched window, banner, tall banner, bookshelf | **top row = storey row 1** for every object (torch 1×2 → rows 1–2, tall torch / arched window → 1–4, tall banner → 1–5) | footprint all `T_AIR`, cols 1..30 |
| **Ceiling** | chain, moss | **storey row 0**; cell above solid floor (`T_PLAT`/`T_WALLF`) or, for chain only, map row 0 (screen top = ceiling) | `T_AIR`; moss only map row 9 |
| **Floor** | ~~skulls, candles~~ (removed DEC1; BONES is placed by its own pass), cauldron, brazier, big brazier | **bottom row = standing row 7** (brazier 1×2 → 6–7, big brazier → 4–7) | footprint `T_AIR`; **every cell directly below the bottom row is `T_PLAT` or `T_WALLF`** (never hole, pit, cap, ladder hole, grate, door); not on a trap/item cell |
| **Corner** | cobweb | storey row 0 only | see corner rule |
| **Back-wall patch** | `T_WALL_DITHER/PATCH/FADE`, `PATCH_A/B` (non-solid, game.md §1.2) | `r0` random, footprint inside storey rows **1..5** | footprint all `T_AIR`, cols 2..29 |
| **Brick** | pillar | unchanged (`T_BRICK` only) | unchanged |

**No decor on walls (user 2026-10-12):** decor never goes on a wall cell (room walls, edge or mid-room dead-end blocks); every footprint is `T_AIR`. The Brick class is dropped: PILLAR (D6) is removed from the decor menu.

- **The "2 rows above a floor" exclusion applies to Mount, Ceiling, Corner and Patch only**
  (they cannot reach rows 6–7 by construction). Floor-class objects are exempt by definition:
  they must end on row 7 (sprites stamp over them, attribute-follow, as with skulls/T_TRAP).
- Kept for all classes: footprint never on door/arch/lintel/jamb/ladder/pit/cap/rubble/grate/
  item cells (exact base-tile match), no ladder cell in the 1-cell ring, budgets (≤ 2 large
  animated, ≤ 4 glyph, ≤ 8 attr, ≤ 6 patch cells), and new: **no other decor in the 1-cell
  ring** (objects never touch).
- **Corner rule:** cell `(9s, c)`, `T_AIR`, ceiling above as in Ceiling. **Left corner:**
  col `c−1` is `T_BRICK` in storey rows 0, 1 and 2 (room edge or dead-end block face;
  excludes door lintels). **Right corner:** same with col `c+1`. Glyphs: existing `COBWEB` =
  the **left** corner (web anchored top-left; artist confirms orientation), new per-level
  **`COBWEB_R`** = its horizontal mirror, produced by the import tool (no new art). Sets
  at the 28-id cap (D1, D3, D8) drop **PILLAR** (2 ids) to fit it, per the existing cut order.
- **Pass order and rng:** (1) **patch pass**, (2) **cobweb pass**, (3) the 12-try menu loop
  (cobweb removed from the menu), (4) drips (unchanged). Every menu try still makes exactly
  4 rnd calls (`o, col, s, r0`); `r0` is used only by Patch/Brick classes.
- **(1) Patch pass, guaranteed:** every room gets **≥ 1 patch**. Up to 8 tries, each
  exactly 4 calls: `o = rnd(k)` over the level's `PATCH_A/PATCH_B` (k = 1–2), `col = 2 +
  rnd(29 − w)`, `s = rnd(2)`, `r0 = 1 + rnd(6 − h)`; first legal placement wins. Levels
  without `PATCH_A/B` (D1, D8): a 3-cell patch, `T_WALL_PATCH` at (row, col), `T_WALL_FADE`
  at (row, col+1), `T_WALL_DITHER` at (row+1, col), placed as one object (all 3 cells legal,
  w = 2, h = 2 for the ring check). Then a **2nd patch with 50 %** (`rnd(2) == 0`, same 8-try
  loop) if the ≤ 6 patch-cell budget allows. The menu may add more 1×1 patch cells.
- **(2) Cobweb pass** (levels with `COBWEB`): scan corner candidates left-to-right,
  top-to-bottom; each takes one `rnd(2)`, placed on 0; **≤ 2 cobwebs per room**.

> **SUPERSEDED by DEC2 (removed 2026-10-26): BONES and the cauldron are gone; ids 13/15/16/31 are free. Kept as history.**

**Dead skeleton, BONES (DEC1; designer decision 2026-10-19; for tools/decorgen.py + src/decor_gen.asm, Python == Z80).**
Replaces CANDLES (31), TORCH_SMALL (15/16) and SKULLS (13). TORCH_SLIM (D2/6/8) stays.
- **Art:** the Skeleton's DEAD frame (collapsed pile) condensed to a **4 cols x 1 row (32x8 px)** lying
  pose, skull at the left end, ribs and a long bone toward the right. Tiles in screen order
  (left to right) = common ids **13, 15, 16, 31**; they are NOT contiguous, so BONES is a
  common-record with an explicit 4-id list (a `BONES_IDS` table), not `base + c`; no renumber.
  Static (no anim, no flags, no attr cycle, adds 0 to every animation budget). Every other
  common id stays put. Glyph pixels must keep cell-edge columns touching across tiles 0-3 so
  it reads as one pile.
- **Attr:** all four cells `$47` (bright-white ink on black paper). Row 7 is an air-band cell, so the
  paper is black on every tileset; the per-level floor colour (`ATTR_FLOOR`) paints only the platform row
  below it, so there is no per-tileset variant and no clash (one ink, black paper, bright bit set like
  skulls were). Artist deliverable: 4 tiles in one `.grid` strip on the Design canvas, shown
  on a black cell row sitting on a floor row in each of the 8 `ATTR_FLOOR` values for review.
- **Behaviour (explicit):** pure decor, class **Floor**. The cells stay `T_AIR`-solidity: BONES
  never blocks, is not solid, owns no entity slot, no state and no log line; hero and monsters walk
  through it visually exactly as over rubble, `T_TRAP` and the former skulls: their sprites
  stamp over it with attribute-follow (F9), restoring tile+attr on leave. An item, ammo or monster
  drop that later lands on a BONES cell simply draws over it (placement only avoids them at
  generation).
- **Where:** levels whose pool contains a Skeleton-family kind (game.md §9.4): **D3 (Skeleton), D4
  (Archer), D5 (Skeleton, Archer), D7 (Archer), D8 (Skeleton)**. None on D1, D2, D6 (the Bone Caller's
  summon fallback does not count). Per-room chance: **1 in 2 on D3, D5, D8; 1 in 3 on D4, D7**.
  **At most 1 per room.** BONES is NOT in the 12-try menu (the menu keeps the common records
  CHAIN, WALL_DITHER, WALL_PATCH, WALL_FADE plus the level's set, so records for all depths lose
  CANDLES, SKULLS and TORCH_SMALL, i.e. D1..D8 each lose all three; D2/D6/D8 keep TORCH_SLIM).
- **Cells:** floor row (bottom row = standing row 7 of storey `s`), 4 consecutive cols `c..c+3`,
  `c` in 1..27 so the footprint stays in cols 1..30; all 4 cells base-tile `T_AIR` (never a wall
  cell: "no decor on walls"); every cell directly below is `T_PLAT` or `T_WALLF` (so not over a
  pit, cap, ladder hole, grate/exit hole or door); not an item, ammo, trap or spawn cell; no
  ladder cell and no other decor in the 1-cell ring (this excludes cells next to a ladder end
  and keeps it clear of doors, jambs, caps); budgets unaffected.
- **Facing: fixed, not mirrored.** A mirrored copy would cost 4 more ids (or a runtime bit-reverse
  table); no free ids exist. The skull-left pose is deliberately readable either way. So
  facing needs no RNG call and no stored state, and nothing is derived from RD_SEED beyond
  the placement draws below (which already come from the RD_SEED-seeded decor LCG).
- **Pass order and rng (fixed):** (1) patch pass, (2) cobweb pass, (3) 12-try menu loop (unchanged
  except the menu is shorter, so `o = rnd(k)` has a new k), (4) **bones pass, last**; the old drip
  pass is gone. Bones pass, only on D3/D4/D5/D7/D8, for every room: exactly **1 gate call**
  `rnd(2)` (D3/D5/D8) or `rnd(3)` (D4/D7), placed on result 0; if placed, up to **6 tries**, each
  exactly **2 calls** `s = rnd(2)` then `c = 1 + rnd(27)`; the first legal try wins and the
  rest are not drawn. On depths D1/D2/D6 the pass draws nothing, so their streams change
  only through the shorter menu. A storey that does not exist in the room (single-storey) is an
  illegal try, not a re-draw. Because the pass runs last, bones see the final placed
  decor for the ring check, and nothing downstream of the room's stream is consumed afterwards.
- **Tool/test notes:** `is_decor(t)` must now read `t >= 28 or t in (12, 13, 15, 16, 31)`
  (31 was not listed; it is now BONES). tests/world.py W13 and the decor goldens rebaseline.

**In the mock scene:**

| Decor | Cols | Rows |
|---|---|---|
| Cobweb | 3 / 1 | 0 / 9 |
| Barred window | 6–7 | 2–3 |
| Brick patch | 13–14 / 22 | 2 / 11 |
| Tall torch (anim) | 28–29 | 1–4 |
| Brazier (anim) | 21 | 6–7 |
| Small torch (anim) | 2 | 10–11 |
| Moss | 8–9 | 9 |
| Banner | 15 | 9–10 |
| Chain | 28 | 9–11 |
| Candles (anim) | 2 | 16 |
| Skulls | 17 | 16 |
| Rubble | 3 | 7 |

Animated cells in the scene: 2 glyph + 2 attr (tall torch), 2 glyph + 1 attr (brazier),
1 attr (small torch), 1 attr (candles). That is **4 glyph + 5 attr**, within the rule. The
drip (rev 1) was dropped from this mock to stay within the glyph limit.

## 4. Spells and attacks (visual notes; numbers in game.md §6)

**Rev 2b (user): projectiles and impacts are real masked sprites** (game.md §6). They spawn
cell-aligned and move whole cells: 8 px per tick, Lightning 16. That makes each frame
single-shift. Black paper only. They take no entity slot. Concept art:
`assets/gfx/concept/concept_sheet.png` (SPELLS row) and `grid/sprites/*.grid`.

| Action | Projectile sprite | Ink | Impact sprite |
|---|---|---|---|
| Spark | 8×8 × 2 | `$43` | 8×8 fizzle × 2 |
| Firebolt | 16×8 × 2 | `$46` | 16×16 burst × 2 |
| Frost Shard | 8×8 | `$45` | 16×16 crack |
| Drain Life (new) | 16×8 × 2 wisps | `$43` | 16×16 drain hit; the caster flashes `$44` |
| Lightning | 16×8 × 2 | `$47` | 16×16 flash |
| Power Strike / Whirlwind / staff | — | — | 16×16 power burst / 8×8 fizz / 16×16 bonk |
| Dagger (spinning) / arrow | 8×8 × 2 / 16×8 × 2 | `$47` / `$07` | — / 8×8 arrow hit |
| Dark Bolt / Death Bolt | necro bolt × 3 (same frames) | `$44` / `$43` | its own hit frame |

A **reflected** spell (game.md §6.0) reverses at the reflector's front cell and plays the
same sprite mirrored.

**Mage staff melee: dedicated STAFF_SWING 32×48 frame** (user decision; wind-up = CAST1).

## 5. Bottom panel (rows 18–23)

The panel is the always-visible *use* surface. Gear management happens only on the page
(§7). The hero sprite does not change with equipment.

**Approved round-5 layout (replaces every earlier panel description).**

| Cells | Content | Attr |
|---|---|---|
| (0–29, 18–19) | **10 icon slots 24×16**; slot *i* (0-based) at cols `3i … 3i+2`, rows 18–19 | per state below |
| (30–31, 18) | **depth** `D1`–`D8` (6×8 font; 2 chars = 12 px) | `$47` |
| (30, 19) | **key icon** 8×8 (only while carrying the level key) | `$46` |
| (0–31, 20) | **info line** for the selected icon: name, MP cost, range, bounces/notes, ammo (≤ 42 chars, §5.1) | name `$47` (chars 0–15) · numbers `$46` (from char 16) · notes `$45` (from char 28) |
| (0, 21) heart · (1–4, 21) **HP bar 32 px** · (5–6, 21) HP number (≤ 2 digits) | | `$42` |
| (7, 21) drop · (8–11, 21) **MP bar 32 px** · (12–13, 21) MP number (≤ 2 digits) | | `$45` |
| (14, 21) drumstick · (15–18, 21) **FOOD bar 32 px** · (19–23, 21) **hunger stage word** (`FED`, `OK`, `HUNGRY`, `WEAK`; 6 chars max = 36 px) | stage attr `$44`/`$46`/`$42`/`$42` | |
| (24–29, 21) **Warrior ammo** `D6 A12` (daggers, arrows, 36 px; blank for the Mage; a count at 0 shows in `$02`) | | `$47` |
| (30–31, 21) **hero status icons** (rev 4, game.md §6.4): up to 2 × 8×8, priority HOLD > MIND > POISON > WEAK; panel glyphs (7 × 8 B), not tile ids; blank when none | | per icon: FROZEN `$45`, ASLEEP `$41`, STUNNED `$07`, CONFUSED `$43`, FEAR `$42`, POISON `$44`, WEAK `$42` |
| (0–23, 22–23) **message log**, 2 rows × 32 chars (6×8 font). Newest on row 23; a new message scrolls row 23 → 22 (192 px × 8 lines ≈ 192 B bitmap + attr copy, ~4k T; a queued panel item, drained in a non-input tick, game.md §3.3) | | `$07` (row 22) / `$47` (row 23) |
| (24–31, 22–23) **worn gear, 4 × 16×16**: weapon 24–25, armour 26–27, helmet 28–29, charm 30–31. An empty slot is a dotted outline | item ink / `$01` |
| row 17 (storey-1 floor) | panel **ornament**: 8 fixed glyphs, not tile ids; the down-exit hole/grate cells override it (game.md §3.3) | `ATTR_FLOOR` |

**Icon order** (full table: game.md §3.5). Warrior (9 + 1 spare): 1 sword · 2 Power Strike ·
3 Whirlwind · 4 daggers · 5 bow · 6 quick food · 7 quick potion · 8 quick scroll · 9 bag ·
10 empty outline. Mage (10): 1 staff · 2 Spark · 3 Firebolt · 4 Frost · 5 Drain Life ·
6 Lightning · 7 quick food · 8 quick potion · 9 quick scroll · 10 bag. **Both classes have
the BAG icon** (FIRE on it opens the page; FIRE+↓ / `I` also do).
- Unlearned ability slots draw the empty outline, and the cursor skips them.
- Quick slots (food, potion, scroll) show the item's 16×16 icon in the slot's left 2×2
  cells, with the count digit (6×8) at cell (col+2, row+1).
- The info line for the selected icon, examples (≤ 42 chars):
  `FIREBOLT  3MP RANGE 12  FIRE BURST` · `DAGGERS X6  RANGE 6  RECOVERABLE` ·
  `BOW X12  RANGE 14  ARROW BREAKS ON HIT` · `NO ARROWS  USE THE SWORD` · `APPLE X3  +15 FOOD`.
- **Ammo at 0:** the icon greys out (below) and the ammo count turns `$02`.

| Icon state | Attr |
|---|---|
| Normal | ink, PAPER black, BRIGHT 1 |
| **Selected** | ink, **PAPER blue**, BRIGHT 1 (attr-only, ~0.1k T to move) |
| **Greyed** (MP < cost, ammo 0, empty quick slot) | `$07` |
| Selected + greyed | `$0F` |

Melee (sword/staff) never greys. The 32-px bars give 8 px per 25 %, and the exact value is
always in the digits. The selected icon's PAPER blue spans its 3×2 cells (rows 18–19).

### 5.1 Text and fonts (user, round 5; rules and numbers also in game.md §3.4)

| Font | Glyph | Where | Capacity |
|---|---|---|---|
| **Text font** | **6×8**, ASCII 32–127, 768 B | log (cols 0–23), info line (row 20), numbers/word on row 21, inventory page | **32 chars** per log line (192 px); **42 chars** on a full row (252 of 256 px) |
| **Menu font** | **8×16** (title may be **16×16** glyphs), ~64 glyphs, size TBD by the artist | main menu, hero/controls select, redefine, pause, `DEPTH n` card, death and win screens | 32 chars per line |

- **Colour rule.** Attributes are per 8 px, glyphs are 6 px, so a char straddles cells. A
  text row has **one colour**, or its coloured words begin on **24-px boundaries** (chars
  0, 4, 8, 12 …; 3 cells = 4 chars). Info line fields: name at char 0, numbers at char 16,
  notes at char 28 (all multiples of 4). The log: one colour per row.
- Text is written with a glyph blit that shifts by `(x mod 8)`; each char costs 8 byte-writes
  + a masked merge on the straddled cell. Black paper only on text rows (log, info line,
  page), so no ink/paper clash.
- Text is drawn only into the bank-5 screen and presented (A7). The text font (768 B) sits
  in bank 2 (`$B200`); the menu font (≤ 1.5 KB raw) stays in bank 3 cold data (game.md §3.4,
  revised 2026-10-03).
- **Messages:** one log line, ≤ 32 chars, upper case, no wrapping. Examples:
  `GOBLIN ATTACKS YOU AND MISSES.` (30) · `THE FIREBOLT FLIES.` · `THE VAMPIRE TURNS INTO A BAT!`
  (28) · `NO ARROWS.` · `YOU PICK UP 3 ARROWS.`. Messages longer than 32 chars are not allowed.

## 6. Icon set

| Icon | Bar | Page / gear | 8×8 (floor) | Ink |
|---|---|---|---|---|
| Sword, Staff, Power Strike, Whirlwind, Daggers, Bow | **24×16** | — | dagger/arrow ammo only | `$47`,`$46`,`$42`,`$47`,`$47`,`$06` |
| Spark / Firebolt / Frost / Drain Life / Lightning | **24×16** | — | — | `$43` / `$42` / `$45` / `$43` / `$47` |
| Bag | **24×16** | — | — | `$06` |
| Heart / drop / drumstick / key | 8×8 labels | | | `$42` / `$45` / `$44` / `$46` |
| Food ×5, potions ×3, scrolls ×3, books, key | 16×16 in a quick slot | 16×16 | yes | per item (rev 1 inks) |
| Weapons ×6 + 2 unique, armour ×3 + 1, helmets ×2 + 1, charms ×4 + 1 | — | 16×16 (page + gear block) | yes | per item |
| Empty slot (dotted) | 24×16 / 16×16 | 16 | — | `$01` |

Bytes (E): 12 bar icons × (48 bitmap + 6 attr = 54) ≈ 0.65 KB, ~44 items × (33 + 9) ≈ 1.8 KB,
labels 32 B, so ≈ 2.5 KB raw, ZX0-packed ~1.5 KB, of cold data in bank 3 (game.md §11.2). They
are drawn into bank 5 (the compose buffer), so they don't need fixed RAM. **Fonts are
separate: bank 2, §5.1.**

## 7. Inventory page (full screen, play paused)

Layout as rev 2 (**4 worn slots**: weapon rows 3–4, armour 6–7, helmet 9–10, **charm**
12–13; bag 5×4 = 20 slots at cols `13+3i … 14+3i`, rows `3+3j … 4+3j`), **but all text is the
6×8 text font** (user, round 5): labels, names, stats, counters, the verb strip and the
description, so a row holds **42 chars** and the page can say more. Rows 15–16 of the worn
column show the counters `KEY`, `DAGGERS n`, `ARROWS n` (`NO ARROWS` in `$02` at 0). Stats at
rows 15–17. The verb strip is row 19: food `EAT QUICK DROP`, potion `DRINK QUICK DROP`,
scroll `READ QUICK DROP`, book `READ DROP`, bag gear `EQUIP DROP`, worn gear `REMOVE`.
**Larger icons (round 5; engineer/artist to size):** the selected item is shown magnified
2× (32×32, cols 0–3, rows 20–23) beside its description (rows 20–22, cols 5–31 ≈ 36 chars × 3
lines, hint on row 23). Colour rule §5.1 applies: one colour per row, or words on 24-px
boundaries. Controls as rev 1 (directions move, ←/→ pick the verb, FIRE confirms, FIRE+↓ backs
out). A verb that changes the game state costs 1 turn, applied on return to play.

## 8. Decisions taken in this revision

- 2×9 + 6. The jump is 16 px; the decision is accepted in game.md §2.4.
- **Rev 3 (round 5 approved):** panel = 10 icons 24×16, depth + key at cols 30–31, info line
  on row 20, bars + hunger word + ammo on row 21, 2-row log (cols 0–23) + 4 gear icons 16×16
  (cols 24–31), ornament on row 17. Custom 6×8 text font and 8×16 menu font, in bank 2.
  Colour rule: one colour per row or words on 24-px boundaries. Mage keeps the BAG icon.
- 2-row log, and gear as 16×16 with 4 slots (charm: user agreed).
- 64 tile ids, split into 32 common and 32 per-level, with 8 sets in bank 7.
- Door 2 cols, belonging to the connection.
- 8 per-level colour schemes.
- The tall torch is in the catalogue.
- **Rev 2b:** black walls with dithered brick patches; projectiles and impacts as sprites;
  the Mage bar has 5 spells (rev 3: and keeps the bag icon).
- Staff swing has its own frame.
