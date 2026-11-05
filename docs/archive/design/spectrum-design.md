ARCHIVED 2026-10-01 — superseded; current spec = docs/design/prototype.md + foundations.md

# Tome of the Dead — Spectrum design (vertical slice)

> Game-designer deliverable. Authoritative for *what the game is*: rendering
> approach, slice scope, controls, turn/entity model, combat + RNG, playability.
> The engineer assigns byte addresses in `docs/memory-map.md`; this doc gives
> field-level data shapes and concrete numbers, never fixed addresses.
>
> Every section states a **DECISION** and justifies it in cycles/bytes/clash
> terms, per the charter. This document is the P1 exit gate and unblocks the
> engine. It is deliberately decisive — where I assume, I say so in
> §8 "Assumptions & confirmations".

---

## Milestone context (staged delivery)

> **Decided 2026-06-26.** The *target* look for Tome of the Dead is **side-view bitmap
> sprites** (the WazHack-inspired feel). To de-risk, delivery is **staged**: this document
> specifies **Slice 1 = top-down char-cell**, which proves the turn loop, combat,
> RNG, level generation, items, and the whole test harness — all of which are
> **reused unchanged** in **Milestone 2 = the side-view renderer**. Only §1
> (rendering) and parts of §4 (entity coordinates / level structure) are replaced
> in M2; everything else here is permanent. Build Slice 1 to this spec.

---

## Rendering & world model — 2026-07-03 revisions (side-view committed)

> **Decided 2026-07-03, user.** The side-view spike track (SPIKE…SPIKE-4) proved
> the WazHack-inspired renderer feasible, and it is now **committed as the Slice 1
> renderer** (the top-down §1 below is retained as the reference for the
> renderer-agnostic game logic — turn loop, combat, RNG, entities, level gen —
> which is reused unchanged; only the *presentation* switches to side-view). This
> block records three binding decisions that supersede parts of the spike design
> (`sideview-renderer.md` §3) and add new content. All numbers here are binding.

### R1. Scroll model — DECISION: **Cauldron-style room-transition scroll** (replaces continuous scroll)

The continuous per-column double-buffer scroll (SPIKE-4) works but reads as a
slow lurch (12.5 column-scrolls/s = one 8px jump every 4 frames). We **drop
continuous scrolling during play** in favour of the model used by *Cauldron*
(Hewson, 1985):

- **Normal gameplay: the screen is STATIC.** The player (and cat, and monsters)
  move freely **within the current room**. Nothing scrolls while the player
  walks. The renderer only redraws dirty sprites/cells — no bitmap shift per
  frame. This removes the per-frame scroll cost from the hot path entirely.
- **Room transition: gameplay PAUSES and the whole screen scrolls once.** When
  the player steps across a room boundary (an exit edge), the turn loop **freezes**
  and the full 6144-byte screen bitmap is shifted left/right (or the
  vertical equivalent, see R2) toward the adjacent room in a **single animated
  sequence**, then play resumes in the new room.
- **Transition animation budget:** shift the entire screen **4–8 px/frame** via a
  pixel-shift chain (`RLCA`/`RRCA` per byte-row). A full 256px room width =
  **32–64 frames ≈ 0.64–1.3 s**. Because gameplay is frozen, the transition may
  spend the **whole frame budget** on the shift — the very cost that made
  continuous scroll unacceptable is fine here because it happens **infrequently
  and off the interactive path**. Start at 8 px/frame (~0.64 s); drop to 4 if it
  tears or reads too fast.
- **Why this wins:** normal movement becomes as cheap as the static top-down
  renderer (dirty-sprite redraw only, no shift), while transitions get the
  faithful "camera pans to the next room" WazHack-inspired feel. It also kills the SPIKE-4
  residual (spreading scroll work across frames, atomic flip) — no longer needed,
  because we never scroll *during* interactive frames.

> **Supersedes** `sideview-renderer.md` §3.2/§3.4 (fine-sprite/coarse-background
> follow-with-dead-zone continuous scroll, per-frame HALT-synced motion loop) for
> the shipped renderer. The spike's byte-shift primitive is still the basis of the
> transition shift; the double-buffer is optional polish, not required.

### R2. Dungeon structure — DECISION: **room-based, discrete rooms joined at edges**

The world is **not** an open continuous floor; it is a graph of **discrete rooms**
connected at their edges, which is exactly what R1's transition model wants and
fits the original game's dungeon structure naturally.

- **A room = one screenful.** Each room fits the viewport (side-view playfield;
  see §2.4 for the row split). No intra-room scrolling.
- **Rooms connect at edges.** A room has up to 4 exits (left/right/up/down edge).
  Stepping onto an exit cell triggers the R1 transition to the neighbouring room
  in that direction. Horizontal exits scroll left/right; vertical exits scroll
  up/down (vertical shift = whole-screen `LDIR` by 8-px bands — cheaper than
  horizontal, still frozen-budget).
- **Corridors are just narrow rooms / short transitions.** A corridor is modelled
  as a room whose walkable area is a 1–2 tile-tall passage; it need not be special
  cased. This keeps the map model = "a set of rooms + an adjacency table", not a
  giant tile array.
- **Level = a small graph of rooms.** Slice target: **4–6 rooms per level**
  (unchanged from §4.4), now each its own screen with an adjacency/exit table,
  rather than a single 30×21 array. The down-stairs live in one room far (in graph
  hops) from the entry room; connectivity is a generation invariant (§6.2).
- **Engineer data shape (fields, not bytes):** per room — `room_id`, a tile buffer
  for its screenful of terrain, and an **exits[4]** table = `{dir → neighbour
  room_id or NONE, exit_cell(s)}`. The active room's tile buffer is what the
  renderer draws; on transition the neighbour's buffer is scrolled in.

> This replaces the single-screen no-scroll assumption of the top-down §2.4/§4.2
> for the shipped side-view. Game logic (combat, AI, turns) is unchanged — it just
> operates on "the current room's" entities/tiles.

### R3. Hero selection — DECISION: **choose Wizard or Witch at start; both have a cat companion**

> **SUPERSEDED 2026-09-24 (user)** by `docs/design/prototype.md` §2: the cast is
> now the sprite sheet's — heroes **Knight / Wizard / Rogue** (mechanically
> distinct, prototype §6.3); **Witch and cat dropped for now** (cat art kept in
> `assets/gfx/cat_*`, unused). R3 below is kept for the record only.

At game start the player picks one of **two hero classes**; both are side-view
humanoids with a following **cat** pet (as in the original game). Full visual/animation
spec for the artist is in `docs/design/heroes.md`; the game-model summary:

- **Wizard** and **Witch** are the two selectable player kinds. For **Slice 1
  they are mechanically identical** (same HP/atk/dmg/start kit) — the choice is
  cosmetic (sprite + optional flavour). Class differentiation (e.g. a spell) is a
  post-slice hook, noted but OUT of the slice.
- **Cat companion:** a small side-view quadruped that **follows the player**. It
  is a separate entity in the array (an ally), occupies a cell, and is drawn as a
  sprite. Slice behaviour: pathless follow (greedy step toward the player, one
  step behind, non-blocking to the player, does not fight yet). It participates in
  R1 transitions (snaps into the new room with the player).
- **Selection screen** (pre-game state): a minimal two-option chooser (`W` =
  Wizard, `I` = Witch — or Left/Right + Enter; engineer's choice) that sets
  `player.kind` and the player sprite set, then generates level 1. This adds one
  game state (`SELECT`) ahead of `PLAYING`.

Entity-model impact: the player slot's `kind` now encodes wizard vs witch; the
cat is one more entity slot with an `IS_ALLY` flag (new `flags` bit) and follow
AI. `MAX_ENTITIES` (16) is unchanged — cat + player + up to 14 monsters.

### R4. PROTO revisions — 2026-09-24 (pointer)

> **Decided 2026-09-24 (user + game-designer).** The first playable prototype is
> specified in **`docs/design/prototype.md`**, which is authoritative for the
> side-view game where it conflicts with this document. Summary of what it
> supersedes here (sections below are kept, not rewritten):
>
> - **R3** hero selection → sprite-sheet cast (Knight/Wizard/Rogue), no cat/Witch.
> - **§2.4** screen budget → side-view rooms are rows 0–20 (3 storeys × 7 rows),
>   HUD rows 21–23 (prototype §3.3, §9).
> - **§3** controls → side-view semantics: L/R walk or bump-attack, U/D climb
>   ladders; chords no longer mean diagonals (vertical wins if legal); held keys
>   repeat turns (prototype §3.1, §9).
> - **§4.1** turn loop → same player-then-monsters logic, now with a presentation
>   *animation phase* at a 25 Hz tick (prototype §3.1–§3.2).
> - **§4.3/§4.4** entity fields & counts → prototype §11.1 (pixel u8 coords,
>   facing, animation, room, spawn); on-screen cap hero + 4 monsters (§5.5).
> - **§5.3** AI → walker/flyer archetypes + ladder-climbing (prototype §6.4).
> - **§5.4** monster table → the six sprite-sheet kinds (prototype §6.3).
> - **§2.1/§2.2 items** → PROTO keeps only **potions** (carried, `G` quaff from §3,
>   heal 8, max 9, persistent once taken; prototype §6.6). No regen. Weapon/gold
>   pickups OUT for PROTO.
> - **R2 room model, extended (rev B, user):** monsters **persist per room** in
>   the entity array (no reset on re-entry) and **follow the player through
>   exits** under a deterministic, cap-respecting rule (prototype §3.7).
> - **Colour (rev B, user):** coloured floor bands are kept; ladders cross them via
>   black-paper hole cells + snapped climbers + no combat on ladders (prototype §4).
> - **Unchanged and reused:** §5.1 to-hit, §5.2 damage dice, §5.6 RNG, R1/R2.

---

## 0. One-paragraph pitch

A turn-based, top-down dungeon crawl in the Rogue/NetHack lineage, "faithful in
spirit" to the original game's *descend-or-die* loop but **not** its side-scrolling
real-time presentation. You are an adventurer descending through two generated
dungeon levels. You walk, you bump monsters to fight them, you pick up a couple
of items, you find the down-stairs and descend to a freshly generated **level 2**;
descending level 2's stairs wins the slice (death ends it early). Everything is
rendered on the **character grid** to make attribute clash a non-problem.

---

## 1. Rendering approach — THE lever

### DECISION: **UDG / char-cell tiles, top-down, on the 32×24 attribute grid.**

The engine is built to a **fixed 8×8 character grid**. One dungeon tile = one
8×8 cell = one screen character position. Each cell is drawn from a small bank of
8×8 bitmaps (UDG-style glyphs) and coloured by writing **one attribute byte** for
that cell. No sprite crosses a cell boundary; nothing is drawn at pixel offsets.

### Why (hardware, not taste)

The Spectrum screen is a 256×192 1-bit bitmap with a *separate* 32×24 attribute
grid; each 8×8 cell carries exactly two colours (ink + paper). The two competing
designs trade off like this:

| Concern | UDG char-cell top-down (CHOSEN) | Bitmap sprites side-view (WazHack-inspired) |
|---|---|---|
| **Attribute clash** | **Structurally impossible.** A tile *is* a cell, so its 2 colours never collide with a neighbour. We never fight clash. | Endemic. A sprite at a non-8-pixel boundary forces ≥2 cells to share colours → visible colour bleed; needs masking/colour-snapping work every frame. |
| **Per-cell draw cost** | Copy 8 bytes of bitmap (one per pixel row) + write 1 attribute byte. The 8 bitmap bytes are at fixed +256-stride screen addresses; a tile blit is ~tens of T-states, and we only redraw *dirty* cells. | A masked sprite blit is read-AND-mask-OR-write per byte across up to 2 cells horizontally and 2 vertically, plus pre-shifted sprite copies for sub-cell X — multiples of the cost, every moving frame. |
| **Bytes (graphics data)** | One glyph = 8 bytes. A full tileset of ~32 glyphs = 256 bytes. Trivially fits low RAM, no banking needed for tiles. | Each sprite needs pre-shifted variants (up to 4 X-shifts) + masks → 8–16× the bytes per visual, pushing assets into paged banks. |
| **Map model** | Map is a 2D byte array of tile IDs; render = map[y][x] → glyph + attr. Clean, indexable, cheap to diff. | Needs a free-floating entity list with pixel coordinates and a scrolling viewport — far more engine. |
| **Look** | Classic Rogue/NetHack. Reads instantly, ages well, unmistakably "this is the slice." | Closer to the original game's vibe but unbuildable cheaply on this hardware at this scope. |

The char-cell approach makes clash a **design invariant rather than a runtime
battle**, makes rendering a *dirty-cell* problem (redraw only changed cells, not
the screen), and keeps the map a flat indexable array. On a slow Z80 that is the
difference between a smooth turn loop and a slideshow. the original game's side-view does
not port literally (charter §"Hard reality"); this is the faithful-in-spirit
reinterpretation that is actually buildable.

### What the engine is built to (binding for the engineer)

- **Playfield:** a fixed top-down grid of cells. Reserve the bottom rows for a
  status/message line (see §2). Map viewport = **30 columns × 21 rows** (the
  remaining 3 rows of 24 are UI: see §2.4). The *logical* dungeon map is the same
  size as the viewport for the slice — **no scrolling** (decision in §4).
- **Tile = cell:** a tile never spans cells; an entity occupies exactly one cell
  and is drawn by overwriting that cell's glyph + attribute.
- **Render is dirty-cell:** the engine keeps a per-cell "dirty" mark and only
  blits changed cells each turn. A turn typically dirties ≤ (1 + #moved entities)
  cells, so a turn redraw is a handful of cell blits, not a frame.
- **Colour is per-cell via attributes:** monster/item/terrain colour = the
  attribute byte written with the glyph. No ink/paper mixing inside a cell beyond
  the native 2.
- **One glyph per entity kind**, chosen so silhouettes differ at 8×8 (letters
  are fine and classic: `@` player, `r`/`k`/`o` monsters, etc. — final glyph
  bytes are the artist's job; this doc only fixes the *grid contract*).

---

## 2. Vertical-slice scope

The smallest thing that is genuinely *playable*: walk a real generated level,
fight by bumping, grab an item or two, descend or die.

### 2.1 IN scope

- **One dungeon level**, procedurally generated from a seed (rooms + corridors),
  with a guaranteed-reachable **down-stairs**.
- **8-direction (or 4-direction, see §3) grid movement**, one tile per turn,
  blocked by walls.
- **Melee combat by bumping**: moving into a monster's cell attacks instead of
  moving. Monsters attack the player when adjacent.
- **A handful of monster kinds (3)** with different stats (see §5.4), spawned at
  generation, each a single-cell glyph.
- **A handful of items (2–3 kinds)**: at minimum a **healing potion** and a
  **weapon pickup** that raises damage; optionally **gold** (cosmetic score).
  Pick up by stepping onto the cell; potion is quaffed via a key.
- **Player stats**: HP, max HP, attack/damage, simple level/XP counter
  (XP optional — see §5.5).
- **Descend**: standing on down-stairs + a key **generates the next level** and
  places the player on it. The slice is **2 levels deep**; descending the stairs
  on **level 2** is the win condition. (The generator is simply re-run for the
  next level — §5.7.)
- **Death**: HP ≤ 0 → death state, run ends, message shown.
- **Status/message UI line** showing HP and the last event message.
- **Deterministic RNG** from a fixed/known seed so `test` can assert outcomes
  (see §5.6).

### 2.2 OUT of scope (explicitly deferred)

- Dungeon depth beyond **2 levels** / persistent revisitable levels (you descend
  level 1 → level 2; that is the slice).
- Scrolling / maps larger than one screen viewport.
- Field of view / lighting / fog-of-war / line-of-sight (whole level is drawn;
  see §4 note — this can be a P5+ enhancement, not the slice).
- Ranged combat, spells, status effects (poison, confusion…), hunger.
- Inventory management UI beyond "carry a weapon + a few potions" and a quaff
  key. No drop/equip menus.
- Item identification, shops, classes/races, character creation.
- Sound (deferred project-wide until engine works — CLAUDE.md / plan P7).
- Animation, real-time anything, mouse, side-view, multi-cell sprites.
- Save/load.
- Pathfinding smarter than greedy step-toward-player (see §5.3).

### 2.3 Slice "done" = §6 playability checklist passes.

### 2.4 Screen budget (24 rows)

> **Side-view: SUPERSEDED 2026-09-24** by `prototype.md` §3.3/§9 (room rows 0–20,
> HUD rows 21–23).

| Rows | Use |
|---|---|
| 0 | Top status line: `HP nn/nn  Lv n  G nnnn` (compact) |
| 1–21 | Map viewport, 30 cols × 21 rows (cols 1–30; cols 0 and 31 are border/margin) |
| 22 | (spare / separator) |
| 23 | Message line: last event text ("You hit the rat.", "The rat dies.") |

> The engineer may shift the exact split, but: **reserve ≥1 row for HP/status and
> ≥1 row for a message**, and keep the map a contiguous rectangle. Map dims used
> elsewhere in this doc assume **30×21**; if the engineer changes the split,
> update §4 max-counts proportionally and note it here.

---

## 3. Controls

> **Side-view: partly SUPERSEDED 2026-09-24** by `prototype.md` §9 — same keys,
> but U/D = climb, chords resolve vertical-first (no diagonals), held keys repeat
> turns (test flag `INPUT_REPEAT=0` restores the edge-triggered rule below).

The Spectrum keyboard has **no dedicated cursor block** (cursor keys are
shifted 5/6/7/8 on a 48K layout and awkward). So we pick deliberately.

### DECISION (REVISED 2026-06-26, manager+user): **4 movement keys, with
diagonals via two-key chords.** No dedicated diagonal keys (`yubn` dropped).
Primary = classic Rogue `hjkl`; secondary (redundant) = `QAOP` cross. A single
direction key moves orthogonally; **pressing two orthogonal keys at the same time
moves diagonally** (e.g. `K`+`L` = up-right, `J`+`H` = down-left). So the player
can reach all 8 directions, but the *key layout* is only 4 keys — diagonals are
emergent from chording, not separate bindings.

| Key(s) | Action |
|---|---|
| `H`  (or `O`) | move left (west) |
| `L`  (or `P`) | move right (east) |
| `K`  (or `Q`) | move up (north) |
| `J`  (or `A`) | move down (south) |
| `K`+`L`, `K`+`H`, `J`+`L`, `J`+`H` (any orthogonal pair) | move diagonally (NE/NW/SE/SW) |

**Input model:** the input layer samples the *set* of movement keys currently
held and sums their contributions into a step `(dx,dy)`, each component ∈
`{-1,0,+1}`: `dx = (+1 if east key) + (-1 if west key)`, `dy = (+1 if south key)
+ (-1 if north key)`. Opposite keys cancel (`dx`/`dy` = 0). If `(dx,dy) == (0,0)`
→ no action, no turn. This yields up to **8 movement directions from 4 keys**.
Because two physical presses are rarely perfectly simultaneous, the sampler
should allow a tiny capture window (engineer's choice — e.g. on first edge,
re-read the matrix ~1 frame later and OR the held keys) so a near-simultaneous
second key still registers as a diagonal. Still **one chord = one turn** (debounce
to a single action per press; require release before the next).
| `.` (period) or `Space` | wait / pass turn |
| `G` | quaff healing potion (G = "glug"; avoids clashing with movement letters) |
| `>` (Symbol-Shift + `T`) → **use `D` for "descend"** | descend stairs when standing on them |
| `Enter` | dismiss message / confirm (e.g. on the death/descend screen) |

### Rationale

- **`hjkl`/`yubn`** is the canonical roguelike map, costs the player nothing to
  learn if they know the genre, and the 8 keys are physically spread across the
  Spectrum keyboard (no awkward cluster). It maps cleanly to a single
  "direction → (dx,dy)" lookup the engine already needs.
- The real Rogue `>` glyph requires Symbol-Shift on a Spectrum (uncomfortable
  and ambiguous to read), so **descend is bound to `D`** instead — a single
  unshifted key, only meaningful while on the stairs.
- **`G` for quaff** keeps the only item-use verb off the movement keys.
- The redundant `QAOP` cross is the classic Spectrum "Sinclair cursor" feel for
  non-genre players; it is cheap (extra entries in the key table) and 4-direction
  only — diagonals stay vi-keys.

### Engine contract

- Input layer samples held movement keys → a **step action** carrying `(dx,dy)`,
  each ∈ `{-1,0,+1}` (summed per the revised §3 input model), plus the discrete
  actions `WAIT`, `QUAFF`, `DESCEND`, `CONFIRM`. `(dx,dy)` reaches all 8
  directions from the 4 movement keys via chording; `(0,0)` = no action (no turn).
  A `dxdy` lookup table is unnecessary — `(dx,dy)` is computed directly from the
  key set. (Chordable 4-key scheme per the revised §3; original design was 8 keys.)
- Reading the keyboard half-rows directly is fine; debounce so one physical press
  = one action (turn-based, so a simple "wait for no-key then key" or edge-detect
  is enough — engineer's choice, but **one keypress must equal one turn**).

---

## 4. Turn & entity model

### 4.1 Turn loop shape (energy-free, player-driven)

The slice uses the **simplest correct** turn model: a strict
**player-acts-then-world-acts** loop (no speed/energy system — all actors take
one turn per turn).

```
loop forever:
    1. read input  -> action            ; blocks; non-action keys ignored
    2. resolve player action            ; move / attack / quaff / wait / descend
       - if DESCEND on stairs -> set WIN state, break
       - if action illegal (wall) -> no turn consumed, goto 1
    3. for each living monster (in slot order):
          decide action (AI, §5.3)
          resolve monster action        ; move toward player or attack player
    4. apply deaths (player or monsters), update messages
       - if player HP <= 0 -> set DEAD state, break
    5. render dirty cells + status + message line
    6. advance turn counter
end loop
on WIN/DEAD: show end screen, wait CONFIRM
```

Properties the engineer can rely on:

- **Deterministic order:** monsters act in **slot index order** every turn. Given
  the same RNG state and inputs, the whole run is reproducible (required for
  `test`, §5.6).
- **No real-time:** nothing happens without a player keypress. No timers, no
  interrupt-driven game logic. (Interrupts may still drive flicker-free rendering
  if the engineer wants, but **logic is keypress-paced**.)
- **One keypress = at most one turn.** Illegal moves (into a wall) do **not**
  consume a turn (classic Rogue behaviour, avoids accidental death).
- **No scrolling** → the renderer never has to shift the playfield; only dirty
  cells change.

### 4.2 Map data shape

- **Map:** a 2D array of **tile bytes**, `MAP_W × MAP_H = 30 × 21 = 630 bytes`.
  Row-major. One byte per cell.
- **Tile byte encoding (suggested):** low bits = terrain type, plus flags.
  - Terrain types (the engineer may renumber): `0 = wall`, `1 = floor`,
    `2 = corridor` (functionally floor; may render differently), `3 = down-stairs`.
  - **Flags** the engine needs per cell (can be packed into the tile byte's high
    bits or a parallel array — engineer's call):
    - `WALKABLE` (derived from terrain: floor/corridor/stairs yes, wall no).
    - `OCCUPANT` index, OR keep occupancy in the entity list and a separate
      "who is on cell (x,y)" lookup. **Recommendation:** store a small
      `occupant` byte per cell ( `0xFF` = none, else entity slot index) so
      bump-attack and movement-blocking are O(1) without scanning the entity list.
- **Items on the floor:** for the slice, a short **item-on-floor list** (≤ 8
  entries) of `(x, y, item_kind)` is simpler than a per-cell item field. The
  engineer may instead store an item id in the tile byte if bits allow.

> The 630-byte map fits easily in low RAM; **no banking needed** for the slice's
> map or tileset. Banking is reserved for later (more levels, audio, art).

### 4.3 Entity record — FIELDS (engineer assigns bytes/layout)

One **fixed-size record per entity**, stored in a flat array of `MAX_ENTITIES`
slots. **Slot 0 is always the player.** A slot is "alive" iff `hp > 0` and a
`flags.ACTIVE` bit is set.

| Field | Type / width | Range | Meaning |
|---|---|---|---|
| `kind` | u8 | 0–255 | entity kind id (0 = player; 1.. = monster kinds; indexes the kind table §5.4) |
| `x` | u8 | 0–29 | tile column (≤ MAP_W-1) |
| `y` | u8 | 0–20 | tile row (≤ MAP_H-1) |
| `hp` | u8 | 0–255 | current hit points (0 = dead) |
| `max_hp` | u8 | 1–255 | max hit points |
| `atk` | u8 | 0–255 | to-hit value (§5.1) |
| `dmg` | u8 | small | damage value/dice id (§5.2) |
| `flags` | u8 (bitfield) | — | bit0 `ACTIVE`, bit1 `IS_PLAYER`, bit2 `HOSTILE`, bit3 `DIRTY` (needs redraw), others reserved |
| `glyph` | u8 | — | tile/UDG glyph id to draw (could be derived from `kind`; storing it allows e.g. a "fleeing" variant later) |
| `attr` | u8 | — | attribute byte (colour) to draw with the glyph |

Player-only extra fields (can live in the player slot or a separate struct —
engineer's choice; keeping them in slot 0 with spare bytes is fine):

| Field | Type | Range | Meaning |
|---|---|---|---|
| `weapon_dmg_bonus` | u8 | 0–small | added to player `dmg` when a weapon is picked up |
| `potions` | u8 | 0–9 | healing potions carried |
| `gold` | u16 | 0–9999 | score (cosmetic) |
| `xp` / `level` | u8 each | small | optional progression (§5.5) |
| `depth` | u8 | 1 | current dungeon depth (always 1 in slice; descend increments it conceptually for the win message) |

### 4.4 Concrete max counts (binding)

| Quantity | Value | Rationale |
|---|---|---|
| `MAP_W` | **30** | viewport width minus borders (§2.4) |
| `MAP_H` | **21** | viewport height (§2.4) |
| Map bytes | 630 | `MAP_W*MAP_H`, one byte/cell |
| `MAX_ENTITIES` | **16** | slot 0 player + up to 15 monsters; fixed array, no allocation. 16 keeps a slot index in low nibble-ish range and the per-turn AI loop cheap. |
| Monsters per level (spawn) | **6–10** | randomised within `MAX_ENTITIES-1`; tuned for a beatable-but-dangerous slice |
| Monster kinds | **3** | rat / kobold / orc-equivalent (§5.4) |
| Item kinds | **2–3** | healing potion, weapon, (gold) |
| Items on floor (max) | **8** | small fixed list (§4.2) |
| Rooms per level | **4–6** | enough to need corridors and create combat spacing |
| Max potions carried | **9** | single status digit |

These numbers are the contract; if the engineer needs to move one for a real
constraint, record the new value here (this doc) **and** in `docs/memory-map.md`.

---

## 5. Combat & RNG

Everything here is **8-bit-friendly** (single-byte adds/compares, table lookups,
no multiply/divide unless trivial) and **deterministic from a seed**.

### 5.1 To-hit — DECISION: single-byte threshold roll

```
hit if  rng_below(attacker.atk + DEFENDER_DODGE_CONST - defender_evasion)
```

Concretely, the simplest correct model:

- Roll `r = rng_d20()` → a value **1..20** (see §5.6 for how an 8-bit RNG yields
  a d20: `rng_byte() mod 20 + 1`, or a 5-bit mask + reroll; engineer picks one,
  but it MUST be seed-deterministic).
- **Hit if** `r + attacker.atk >= 10 + defender_evasion`.
  - `attacker.atk` is the entity field (player starts ~1; weapon raises effective
    damage not to-hit, keeping to-hit stable and readable).
  - `defender_evasion` is a per-kind constant (slice: small, 0–4).
  - The constant `10` is the base difficulty.
- This is one add and one compare on bytes. No multiply.

A natural `r == 20` may auto-hit and `r == 1` may auto-miss (classic, optional;
include it only if it costs nothing — engineer's discretion, document if added).

### 5.2 Damage — DECISION: small "dice" table, byte-only

- Each entity kind has a **damage descriptor** = `(num_dice, die_size, bonus)`,
  e.g. player unarmed = `1d3`, with a sword = `1d3 + weapon_dmg_bonus`; rat =
  `1d2`; orc = `1d6`.
- Roll = sum of `num_dice` rolls of `rng_below(die_size)+1`, plus `bonus`. For
  the slice, **`num_dice` is always 1** to keep it a single roll + add. So
  effective damage = `rng_mod(die_size) + 1 + bonus`.
- Damage is subtracted from `hp` with a **saturating** subtract (don't underflow
  past 0). `hp == 0` → dead.

Worked example (deterministic, for a `test` assertion): player `1d3+0` vs rat
`hp=3`. With a fixed seed producing rolls `2,3` → two hits of 3 then 1 → rat
dead in ≤2 turns. The `test` skill can pin the seed and assert "rat dies on turn
N".

### 5.3 Monster AI — DECISION: greedy step-toward-player (no pathfinding)

> **Side-view: SUPERSEDED 2026-09-24** by `prototype.md` §6.4 (walker/flyer
> archetypes, ladder climbers, storey-bound flyers). Kept for the top-down record.

Per monster, each turn:

1. If **orthogonally adjacent to player** (Manhattan distance 1 — 4-connected per
   the revised §3) → **attack** the player (to-hit + damage as above).
2. Else compute `dx = sign(player.x - x)`, `dy = sign(player.y - y)`; attempt to
   move one step by that (dx,dy).
   - If the target cell is a wall or occupied → try the axis-only fallbacks
     (move just in x, or just in y). If all blocked → **wait**.
3. (Optional, only if cheap) a monster may have a **wake radius**: it does
   nothing until the player is within N tiles. Keeps far monsters from swarming
   instantly and is one compare. Recommended N = 6.

No A*, no flow field. This is intentionally dumb but produces correct,
deterministic, testable behaviour and reads as "monsters come at you." It can be
upgraded post-slice.

### 5.4 Monster kind table (3 kinds) — starting balance

> **Side-view: SUPERSEDED 2026-09-24** by `prototype.md` §6.3 (hero + six
> sprite-sheet monster kinds). The rat/kobold/orc table below is historical.

| id | name (glyph) | hp | atk | evasion | damage | wake N | notes |
|---|---|---|---|---|---|---|---|
| 1 | rat (`r`) | 3 | 0 | 0 | 1d2 | 4 | trivial; teaches the bump-attack |
| 2 | kobold (`k`) | 6 | 1 | 1 | 1d3 | 6 | the staple threat |
| 3 | orc (`o`) | 10 | 2 | 2 | 1d6 | 6 | can kill a fresh player in ~3–4 hits |

Player start: `hp = max_hp = 12`, `atk = 1`, unarmed `dmg = 1d3`,
`weapon_dmg_bonus = 0`, `potions = 1`. A picked-up weapon sets
`weapon_dmg_bonus = 2` (→ `1d3+2`). These are **starting** values; the
game-designer will retune in P4 against the real engine — they are chosen so the
slice is *winnable but lethal* (you can die to two orcs; you can clear the level
with care + the potion).

### 5.5 Progression (optional, keep minimal)

XP/level is **OUT of the must-have slice** but cheap if wanted: killing a monster
grants `xp += kind.hp`; crossing a threshold raises `max_hp` by a few and `atk`
by 1. Include only if it doesn't delay P4; otherwise ship flat stats. Default:
**flat stats for the slice**, `gold` as the only score.

### 5.6 RNG — DECISION: 16-bit xorshift, seed in a named RAM word

The `test` skill must be able to **fix the seed and assert outcomes** (CLAUDE.md
testing hook; conventions §"Testing hook" wants RNG state at a stable named
address). Requirements: deterministic, cheap on Z80, full-ish period, byte/word
ops only.

**Algorithm: 16-bit xorshift** (`xorshift16`), state in a 2-byte word `RNG_STATE`
at a **stable named address** (engineer records it in `memory-map.md` under
"stable test-observable addresses"):

```
; state is a non-zero 16-bit word
x ^= x << 7
x ^= x >> 9
x ^= x << 8
return x            ; full 16-bit result; take low byte for rng_byte()
```

(The exact shift triplet must be a known-good xorshift16 — the engineer should
use a verified triplet; the point for design is: **one word of state, shifts +
xors only, no multiply/divide, full period 2^16-1, never produces 0 from a
non-zero seed**.) An 8/16-bit LFSR is an acceptable alternative with the same
properties; xorshift16 is preferred for a longer, less-patterned sequence at
similar cost.

Derived rolls:
- `rng_byte()` = low 8 bits of one xorshift step.
- `rng_mod(n)` = `rng_byte()` reduced to `0..n-1`. For the small `n` we use
  (2,3,6,20) prefer **mask-and-reject** (e.g. d20: mask to 5 bits `0..31`, reject
  ≥20 and reroll) to avoid modulo bias and avoid a divide. For powers-of-two
  (d2) a single mask suffices.

**Seed source:**
- **Default / test mode:** a **fixed compile-time seed constant** (e.g. a known
  non-zero word) so a build is fully reproducible and `test` can assert exact
  outcomes and golden screens. There must be a way for `test` to know/he set this
  seed — keep it a named constant and keep `RNG_STATE` readable via ZRCP.
- **Play mode (optional):** seed from a frame counter / `R` register / first
  keypress timing **only if** a "random each run" mode is wanted. For the slice,
  **default to the fixed seed** so everything is reproducible; a "press a key to
  re-seed" path can come later. If both exist, expose a flag the test harness can
  force to the fixed-seed path.

> Determinism contract: given the fixed seed + a recorded input sequence, the
> entire run (level layout, monster placement, every roll) reproduces
> bit-for-bit. This is what makes the golden-screen and state assertions in §6
> meaningful.

### 5.7 Level generation (deterministic)

- Draw `4–6` rectangular **rooms** (random within bounds, non-overlapping or
  lightly overlapping), carve **corridors** connecting them so the whole floor is
  **fully connected** (every floor cell reachable from the player start).
- Place **player** in the first room. Place **down-stairs** in a room **far from**
  the player (e.g. the last room, or the room maximising tile distance) and
  **assert reachability** at generation time (the generator must guarantee a path
  exists — connectivity is a generation invariant, see §6).
- Scatter `6–10` monsters in rooms other than the start room (or beyond wake
  radius), and `2–3` items.
- All draws come from the seeded RNG, so the level is reproducible from the seed.

---

## 6. Playability checklist (observable by `test` / `run`)

Each item is a concrete, machine-checkable condition. The engineer/manager wires
these into `test` scenarios (ZRCP state reads + golden screens). The slice is
**done** when all pass.

**Determinism / generation**
1. **Fixed seed reproduces the level.** Two builds (or two runs) with the same
   seed produce an identical map (assert map bytes equal, and/or identical golden
   screen of the starting level).
2. **Down-stairs exist and are reachable.** The generated level always contains
   exactly one down-stairs tile, and a path of walkable cells connects player
   start → stairs (generator invariant; testable by a flood-fill assertion or by
   actually walking it in a scripted run).
3. **No unreachable required content.** Player start, stairs, and at least one
   item are all on the connected floor region.

**Movement & turn loop**
4. **Player moves.** Pressing `L` once moves the player one cell east on the
   map (assert player.x increments; dirty cells redraw).
5. **Walls block.** Moving into a wall does **not** change position and does
   **not** advance the turn counter (assert player.x/y unchanged, turn counter
   unchanged).
6. **One keypress = one turn.** A single legal move advances the turn counter by
   exactly 1 and lets each monster act at most once.
7. **No softlock.** From the start position, the scripted input sequence
   "walk to the stairs" (along the known reachable path) terminates in the WIN
   state within a bounded number of turns. There is no input that wedges the loop
   (illegal moves are simply ignored, never block input).

**Combat**
8. **Player can kill a monster.** Bumping a rat repeatedly reduces its `hp` to 0;
   the rat's slot goes inactive and its cell stops rendering the rat glyph; a
   "dies" message shows. Deterministic seed → dies on a known turn.
9. **A monster can kill the player.** Standing adjacent to an orc and waiting
   (`.`) while it attacks reduces player `hp` to 0 → DEAD state and death screen.
   (Demonstrates the lose condition works.)
10. **Bump = attack, not move.** Moving into a monster's cell attacks it and the
    player does **not** enter the cell (assert player position unchanged, monster
    hp reduced).
11. **HP never underflows.** Damage exceeding current hp clamps hp to 0 (no
    wrap to 255).

**Items**
12. **Pick up works.** Stepping onto a potion cell increments `potions`; the
    floor item is removed (cell stops rendering the potion).
13. **Quaff heals.** With `potions > 0` and `hp < max_hp`, pressing `G` increases
    `hp` (capped at `max_hp`) and decrements `potions`. With `potions == 0`, `G`
    is a no-op (no turn consumed, no underflow).
14. **Weapon increases damage.** After picking up the weapon,
    `weapon_dmg_bonus > 0` and subsequent damage rolls are higher (assert a
    known-seed kill happens in fewer hits than unarmed).

**End states**
15. **Descend generates level 2; descending level 2 wins.** Pressing `D` on
    level 1's down-stairs generates a fresh, fully-connected level 2 and places
    the player there (assert depth increments, the new map differs, its stairs
    are reachable). Pressing `D` on level 2's down-stairs sets the WIN state and
    shows the descend screen.
16. **End screen waits for input.** WIN and DEAD screens hold until `Enter`
    (CONFIRM), then do something defined (restart or halt — engineer's choice,
    but it must not crash or fall through).

**Rendering invariants**
17. **No attribute clash by construction.** Every drawn cell uses exactly one
    attribute byte; the golden-screen pipeline's clash check (≤2 colours/cell)
    passes trivially because tiles are cell-aligned.
18. **Dirty-cell redraw is correct.** After a move, only the player's old and new
    cells (and any cell whose occupant changed) differ between consecutive golden
    screens (sanity that we aren't full-redrawing or leaving stale glyphs).

---

## 7. Hand-off summary for the engineer

- Build to a **32×24 char grid, top-down, tile=cell, dirty-cell redraw.** Map =
  `30×21` byte array. No scrolling, no FOV, no sprites.
- **16 entity slots**, slot 0 = player; fields per §4.3. Per-cell occupant index
  for O(1) bump/block.
- **Turn loop:** player acts → monsters act in slot order → resolve deaths →
  render dirty → bump turn counter. Keypress-paced; illegal moves cost no turn.
- **Combat:** d20 to-hit (`r + atk >= 10 + evasion`), `1dN + bonus` damage,
  saturating hp subtract. Greedy monster AI.
- **RNG:** `xorshift16`, 1 word of state at a **named, ZRCP-readable** address,
  **fixed compile-time seed by default** for reproducibility. Mask-and-reject for
  small dice.
- Expose at **stable named addresses** (for `test`, per conventions §Testing
  hook): `RNG_STATE`, the dungeon seed, player `hp`/`max_hp`/`x`/`y`, turn
  counter, and a game-state byte (PLAYING / WIN / DEAD). These let every §6 check
  be a ZRCP assertion.
- Glyph bytes and final colours are the **artist's** job (P5); this doc fixes the
  grid contract and which kinds need a glyph, not the pixels.

---

## 8. Assumptions & confirmations (flagged for manager/user)

These are decisions I made to stay decisive; confirm before the engineer builds
to them if you disagree:

1. **Top-down for Slice 1, side-view as Milestone 2 (CONFIRMED 2026-06-26).**
   Side-view is the target look; staged so Slice 1 is top-down (this doc) and the
   side-view renderer is M2, built on the proven game logic. See "Milestone
   context" above. Resolved — no longer open.
2. **Single-screen level, no scrolling, whole level visible (no FOV).** Smallest
   buildable slice. If a fog-of-war/explore feel is considered essential to the
   experience, it's a P-later add but should be acknowledged now. Assumed OUT.
3. **Two levels (CONFIRMED 2026-06-26).** Descend generates a real level 2; the
   slice win is descending level 2's stairs (§2.1, §6.15). Resolved per manager
   decision — no longer an open assumption.
4. **Fixed compile-time RNG seed by default** (random re-seeding deferred). This
   is required for the testability the plan/skills depend on; a "random each run"
   mode is a later toggle. Assumed: fixed seed is the default ship mode for the
   slice.
5. **`D` rebinds Rogue's `>` for descend** (Symbol-Shift `>` is awkward on
   Spectrum). Cosmetic but player-facing; assumed fine.
6. **XP/levelling OUT for the slice** (flat stats + gold score). Cheap to add if
   wanted; assumed deferred.
7. **Movement scheme (RESOLVED 2026-06-26 → 4 keys, chordable to diagonals).**
   The original assumption was 8-direction vi-keys; manager+user chose a **4-key**
   layout (`hjkl` + `QAOP`, no `yubn`) where **pressing two orthogonal keys at
   once moves diagonally** — so all 8 directions are reachable from 4 keys via
   chords. Input sums held-key contributions into `(dx,dy)`. §3 and the engine
   contract are updated. Monster AI (§5.3) remains 4-connected (monsters move/
   attack orthogonally); the player may step diagonally. No longer open.

Nothing here blocks P2 (engine skeleton is design-light). The items above only
need confirmation before **P3/P4** build to them.
