# WazHack/ZX — PROTO: first playable prototype (design spec)

> Game-designer deliverable, 2026-09-24. Phase **PROTO**: the first playable build
> on the committed side-view renderer, using the user's sprite-sheet cast. Heroes
> and enemies **visibly move in all four directions and fight**.
>
> **Revision B (same day): the user answered §12.** Accepted as proposed: 3 storeys
> + 3-row HUD, a 25 Hz tick with 4 px steps, turn-based play with key repeat,
> 24 px ladders, storey-bound flyers, the Wizard's reach-3 zap, Knight BLOCK as a
> visual only, mirroring at load, the chest win, death going to hero select with
> the same seed, and the full art scope. **Changed by the user:**
> (1) **coloured floor bands are kept.** Ladder crossing is solved with black-paper
> ladder holes plus a no-combat-on-ladders rule (§4); (2) **monsters persist and
> follow you between rooms** (§3.7), replacing the room-entry reset; (3) **potions
> are added** as carried pickups (§6.6), replacing HP regen.
>
> **Revision C (2026-09-25): as-built reconciliation after review.** This revision
> records what was built and fixed. It covers: ladder yield / anti-cork (§6.4);
> mid-ladder bodies blocking the line of attack and zap cells skipping sprites
> (§6.1, §6.5); the engineer's accepted spec deviations (§3.6, §3.7, §6.5, #18, #24,
> #34); robustness guards (§11.4); the measured budget and the renderer-optimisation
> decision (§5.5); a balance note (§6.3). No design numbers changed.
>
> **Binding inputs (user, 2026-09-24):** (1) the cast is the sprite sheet
> `assets/gfx/source/wazhack_sprites.dc.html` (Knight / Wizard / Rogue; Skeleton,
> Goblin, Ghost, Giant Rat, Bat, Slime). This replaces Wizard/Witch + cat. (2) "All
> directions" means rooms with floors joined by ladders, plus up/down room exits
> that use the Cauldron vertical transition (`foundations.md` F5/F6).
> (3) There is no climb art in the sheet, so this doc decides how climbing is shown
> (§3.4, §10). (4) Every state an entity can be in must have art (§10).
>
> **Companion doc:** `docs/design/foundations.md` holds the stable rules this spec
> reuses unchanged: rolls and RNG (F1-F3), turn invariants (F4), the room-transition
> scroll and room model (F5/F6), input rules (F7), the sprite data contract (F8) and
> colour zoning (F9). The earlier top-down and spike designs are archived under
> `docs/archive/design/`.
>
> Numbers are binding. The engineer assigns bytes/addresses in
> `docs/memory-map.md`.

---

## 0. PROTO in one paragraph

You pick a Knight, Wizard or Rogue. You start in the top-left room of a
hand-authored **2×2 block of rooms**. Each room is one static screen with **3
storeys**: black air bands over coloured brick floors, joined by **ladders** that
pass through black holes in the floors. You walk left/right, climb up/down, and
cross room edges. Horizontal edges scroll sideways and ladder shafts scroll
vertically, Cauldron-style. **8 monsters** roam the four rooms. They stay where
you left them, and the ones chasing you **follow you through exits**. Walkers pace
and chase, Skeletons and Goblins climb ladders, and Bats and Ghosts fly in 2D inside
their storey. Combat is roguelike bump-to-attack with **animated turns**: wind-up,
strike, hurt, death. **Potions** lie around and heal you when you drink them (`G`).
You win by reaching the treasure chest. If you die, you get a game-over screen and
go back to hero select.

---

## 1. Scope

### 1.1 IN

- Hero select (3 heroes with different stats and attack style, §6.3).
- 4 hand-authored rooms in a 2×2 grid, with horizontal and vertical transitions
  (§3.6, §8).
- Walk L/R, climb U/D on ladders, flyers move in 2D. Facing is left/right
  (mirrored art).
- Bump melee, the Wizard's reach-3 zap (no projectile entity), hit flash, hurt/block
  reactions, death sequences, player death leading to game over.
- 6 monster kinds, 2 AI archetypes (walker / flyer) + a climber flag.
- **Persistent monsters that follow the player between rooms** (§3.7).
- **Potions:** pickup, carry, quaff (§6.6). Persistent once taken.
- Turn-based logic with animated, concurrent turns at 25 Hz (§3).
- Win condition: touch the chest in room D.
- ZRCP-observable state + checklist (§11).

### 1.2 OUT (explicitly)

- All other items (scroll, sword, key), inventory UI, equipment. Sheet items used:
  **POTION** (pickup tile), **CHEST** (goal tile), **TORCH** (optional wall decor).
- HP regen (replaced by potions).
- Procedural generation, multiple levels, descend. P4's generator emits the same
  room descriptor (§8.1).
- Gravity, jumping, falling, pits, partial platforms (every floor spans the full
  width).
- **Combat on ladders** (§4.3), projectiles as entities, spells, status effects, XP.
- Witch and the cat companion (dropped; the cat art stays in `assets/gfx/cat_*`).
- Sound, save/load, double-buffering (risk R-3, §12).

---

## 2. Cast (from the sprite sheet)

Art faces **right**. The engine produces left-facing art (§5.2). The colour is the
one sprite attribute byte, and **its paper is always black** (§4).

| Kind | Role | Body box (W×H px / cells) | Colour attr | Sheet frames |
|---|---|---|---|---|
| Knight | hero | 24×48 / 3×6 | `$47` bright white | IDLE1, IDLE2, WALK1-4, WIND-UP/SLASH/FOLLOW 40×48, BLOCK 32×48, HURT 32×48 |
| Wizard | hero | 24×48 / 3×6 | `$45` bright cyan | IDLE, WALK1-4, CAST1-2 32×48 |
| Rogue | hero | 24×48 / 3×6 | `$44` bright green | IDLE, WALK1-4, STAB1-2 32×48 |
| Skeleton | walker, climber | 24×48 / 3×6 | `$47` bright white | WALK1-4, RAISE, CUT 32×48, COLLAPSED |
| Goblin | walker, climber | 24×32 / 3×4 | `$44` bright green | WALK1-4, CLUB UP, SMASH 32×32 |
| Ghost | flyer | 24×32 / 3×4 | `$45` bright cyan | FLOAT1-2 |
| Giant Rat | walker | 32×16 / 4×2 | `$06` yellow (not bright) | RUN1-2 |
| Bat | flyer | 24×16 / 3×2 | `$43` bright magenta | FLAP UP, GLIDE, FLAP DOWN |
| Slime | walker (slow) | 24×16 / 3×2 | `$44` bright green | WOBBLE, SQUASH, STRETCH |

The **body box** is the entity's logical footprint for collision and reach. Frames
wider than the body extend beyond it by their anchor (§5.3). **No frame is taller
than its kind's body height** (all are bottom-anchored).

---

## 3. Movement model

### 3.1 DECISION (accepted): **turn-based logic, animated turns, 25 Hz tick**

- **Logic is the P3 turn loop:** one action per turn, player first, then monsters
  in slot order, all resolved **instantly** at the start of the turn with the §5.6
  RNG. Positions are **cell-granular** (8 px).
- **Presentation replays the turn:** every entity that changed animates
  **concurrently** over the turn's animation phase. **1 tick = 2 frames (25 Hz)**.
  Tweens move **4 px per tick**, so one cell step = **2 ticks = 80 ms**.
- **Hold-to-repeat:** if a key is still held when the animation phase ends, the
  next turn starts immediately. Walking is continuous at 100 px/s, and holding into
  a monster repeats the attack. The test flag `INPUT_REPEAT = 0` restores the P3
  edge-triggered rule (§11.2).

**Why:** turn-based keeps the determinism contract (§5.6) that every checklist item
relies on, and ZRCP-injected tests stay time-independent. 25 Hz fits a 5-sprite
worst case in the 2-frame tick (§5.5). 4 px steps mean each frame needs at most 2
pre-shifts (§5.1).

### 3.2 Turn phases (engine contract)

```
TURN_PHASE = INPUT:
    tick idle animations (unless ANIM_FREEZE); sample input
    no action / illegal action -> stay in INPUT, no turn consumed
    legal action -> resolve turn:
        1. resolve player (move / climb / attack / quaff / wait)
           exit edge -> follower selection (§3.7), transition (§3.6); skip 2-3
        2. monsters in the current room, slot order: AI -> action -> resolve
        3. pending entries (§3.7): materialise any whose box is now free
        4. deaths: hp==0 -> mark DYING (removed from collision immediately)
        5. build each entity's animation queue for this turn (§7)
    TURN_PHASE = ANIM
TURN_PHASE = ANIM:
    each tick: advance every queue, tween px/py by 4 toward target, redraw dirty
    when all queues finished (and at least 2 ticks elapsed):
        TURN_COUNTER++, potion pickup check (§6.6), HUD refresh
        player DEAD -> GS_DEAD; chest touched -> GS_WIN
        TURN_PHASE = INPUT (repeat immediately if a key is held and INPUT_REPEAT=1)
```

A **WAIT** turn lasts 2 ticks.

### 3.3 Room geometry (cells)

> **Superseded by `game.md` §2.1** (2 storeys × 9 rows + 6-row panel).

The room area is **32 cols × 21 rows (rows 0–20)**. The HUD is rows 21–23 (§9).
There are **3 storeys** of 7 rows. For storey `s ∈ {0,1,2}` (0 = top):

| Storey | Air band (black paper) | Floor row (coloured band) | Standing top row for body height `h` |
|---|---|---|---|
| 0 | 0–5 | 6 | `6 − h` |
| 1 | 7–12 | 13 | `13 − h` |
| 2 | 14–19 | 20 | `20 − h` |

In general: air rows `7s … 7s+5`, floor row `7s+6`, standing `y = 7s+6−h`. A 48-px
hero exactly fills the headroom.

**Tiles (8×8, cell-aligned background):** `AIR`, `PLATFORM` (floor rows), `WALL`
(cols 0/31 except open exits; air-row and floor-row variants differ only by attr,
§4.1), `LADDER_L`/`LADDER_M`/`LADDER_R` (both in air rows and as the **hole** cells
in floor rows), optional `PLATFORM_END_L`/`PLATFORM_END_R` (floor edge caps beside a
hole), `POTION` (1 cell), `CHEST` (2×2 cells), `TORCH` (1×2, optional).

**Other structural rules:**

- **No gravity.** Every floor row is solid across the whole width (PLATFORM, wall,
  or ladder hole, and holes are walkable). An entity stands iff
  `(y + h) mod 7 == 6`, and its storey is `(y + h) div 7`.
- **Walls:** cols 0 and 31, except the air rows of an open horizontal exit.
  Monsters treat cols 0/31 as walls even when open.
- **Body limits:** `1 ≤ x`, `x + w − 1 ≤ 30`. The player reaches col 0/31 only via
  an open exit.

### 3.4 Ladders

- **Width = 3 cells (24 px),** equal to every climber's body width. An entity is
  "at" a ladder iff `x ==` the ladder's left col.
- **Ladder segment** = `{col, s}`. It links storey `s` (lower) to storey `s−1`
  (upper). Its tiles fill rows `7s−1 … 7s+5` (clipped to 0–20) × cols
  `col … col+2`. The top row sits in the upper floor row: that is the **hole**
  (black paper, ladder glyphs), which you can walk across and climb down through.
  - `{col, 0}` = **up-exit** shaft (rows 0–5, open through the top of the room).
  - `{col, 3}` = **down-exit** hole (row 20 only).
  - A shaft through two floors = two segments at the same col.
- **Climb rules** (for an entity at `x == col`, standing and stationary):
  - **UP** legal iff standing on storey `s` and `{col, s}` exists, or already
    mid-ladder. `s == 0` → up-exit (player only).
  - **DOWN** legal iff standing on storey `t` and `{col, t+1}` exists, or
    mid-ladder. `t+1 == 3` → down-exit (player only).
  - 1 row (8 px) per turn. A storey-to-storey climb = **7 turns**.
  - **Mid-ladder:** only UP/DOWN. LEFT/RIGHT is illegal (no turn). **There is no
    combat on ladders** (§4.3).
  - **Snap invariant:** climbing only starts from a standing, cell-aligned position
    and mid-ladder horizontal moves don't exist. So a climber's `px == col × 8`
    exactly, with **zero sub-cell x offset**, for the whole climb. The renderer can
    rely on it (§4.2).
- **Climb presentation:** CLIMB1/CLIMB2 back-view frames, alternating every tick while
  climbing, with CLIMB1 held while resting mid-ladder (art §10). **Fallback until the
  art lands:** the WALK cycle.

### 3.5 Flyers (Bat, Ghost): free 2D inside their own storey (accepted)

- A flyer moves up to **1 cell in x and 1 cell in y per turn** (diagonals allowed,
  tweened 4 px/tick on both axes).
- y is clamped to the storey's **air band**: `7s ≤ y ≤ 7s+6−h`. Bat: 5 rows of
  freedom, Ghost: 3. Flyers never enter a floor row and never pass through walls
  or entities. Ghosts do not phase.
- **Ladder ends (B8; rule by user 2026-10-02, as built — supersedes the
  91cf829 "shafts are walls" rule):** flyers **may cross** a ladder shaft but
  must **never block the hero**. A *ladder-end box* = the standing box at
  either end of a segment, cols `col … col+2` in that storey (the box the
  climbers' "no head-on" rule keeps clear, §6.4).
  - Entering a box is legal only as part of crossing (an x move; the y-only
    move can't change box membership anyway).
  - A flyer inside a box at the **start of its turn must move**: it may keep
    crossing (dx = its facing) or step out (any x step that ends with no box
    overlap). It never waits, stops (dx = 0) or reverses while staying inside.
    Order: the chase dx first (aligned: facing), then the other x direction;
    y kept; no RNG drawn.
  - It does **not attack from inside a box** while a legal move exists. Fully
    boxed (both x steps illegal: an entity ahead, a reversal that stays
    inside) it may attack if in reach, else it stays. Typical case: the hero
    standing right beside a shaft while the Ghost arrives from the far side:
    the Ghost ends on the shaft and fights there (the hero can fight or leave;
    he is not climbing, so nothing is corked).
  - Yield steps (§6.4, hero mid-ladder) are exempt: they move off the hero's
    path in x, reversing inside a box if need be.
  - The Ghost's 3-col body spends 5 turns in a 3-col box when crossing:
    accepted. Speeds unchanged; the Bat's wander reverses only at walls.
  - Engine: `ai_flyer` computes the box overlap once per turn (`FLY_INBOX`,
    `flyer_lcost`); `try_step` enforces "keep crossing or leave".
    `tests/game.py` #55–#57.

### 3.6 Room exits and transitions (foundations F5/F6 applied)

- **Horizontal exit:** an open wall col on storey `s`. The player's body entering
  col 0 (moving left) or col 31 (moving right) triggers it. The step animates first,
  then the transition runs. **Arrival:** same storey, `x = 31 − w` facing left
  (entered from the right) or `x = 1` facing right.
- **Vertical exit:** climbing UP out of `{col,0}` or DOWN into `{col,3}` triggers
  on the first step. *(Rev C, as built: going UP an exit ladder transitions
  immediately, with no tween of the first step. It would move the hero into rows
  above row 0, which is off the room area. Going down still animates the first step
  into the row-20 hole.)* Arrival going up: the room above, **standing on storey 2 at
  `x = col`**. Going down: the room below, **standing on storey 0 at `x = col`**. The
  col must match across the pair (authoring).
- **Transition:** gameplay frozen (`GS_TRANSITION`). **All sprites are hidden**,
  including the hero. Rows 0–20 are shifted (the HUD is not scrolled): horizontal
  8 px/frame (32 frames ≈ 0.64 s), vertical by whole char rows (≤1 s, engineer
  measures). Then the destination room is built and its **non-pending** sprites are
  drawn. **Followers are never visible during the scroll.** They appear through the
  pending mechanism (§3.7) from the next turn on.
- **Arrival conflict:** any monster whose body box intersects the hero's arrival box
  is set **PENDING in place** (hidden, non-colliding, keeps its x/y). It reappears
  by the §3.7 materialise rule once its box is free, i.e. after the hero steps
  away. This replaces the old spawn-reset rule and is the only displacement rule
  needed.
- On the exit turn, monsters of the room being left do not act, except that
  followers are selected (§3.7).

### 3.7 Persistent monsters & following between rooms (user change 2)

**Persistence (where state lives, what it costs):** every monster, in every room,
lives permanently in the **existing 16-slot entity array**. Its `room` field says
which room it is in, and x/y/hp/facing/ai_dir persist exactly as last left. There
is **no per-room save area**: leaving a room simply stops simulating slots whose
`room ≠ CUR_ROOM`. Cost: **+1 flag bit (`PENDING`) per slot, and −3 B/slot**
because the `spawn_x/spawn_y/spawn_facing` fields of rev A are deleted. The only
per-room persistent byte elsewhere is `POTIONS_TAKEN` (§6.6). Monsters are **not
reset** on re-entry.

**Follow rule (evaluated once, on the player's exit turn, before the transition):**

1. **Candidates** = alive, standing (not mid-ladder), non-pending monsters in the
   room being left that are on the **same storey the player exited from**, with
   **gap ≤ 4 cells** to the player's body (either direction; for a vertical exit,
   measured to the shaft col's body box). A **vertical exit** also requires the
   `CLIMBER` flag (Skeleton, Goblin). Flyers and non-climbers follow only through
   horizontal exits.
2. **Order:** by gap ascending, ties by lower slot.
3. **Admit** each candidate in order while all hold:
   - at most **2 followers per exit**;
   - destination room `alive monsters (incl. pending) + admitted followers ≤ 4`
     (the on-screen cap, §5.5);
   - for a Skeleton, destination `tall monsters + admitted tall ≤ 2`.
   A rejected candidate stays in its room, untouched (deterministic).
4. **Admitted followers:** `room ← destination`, `PENDING ← 1`, x/y ← their **entry
   position**:
   - **horizontal:** the destination edge the player arrived at (`x = 1` for the
     left edge, `31 − w` for the right). Walkers stand on the same storey; a flyer
     keeps its band offset `y − 7s`.
   - **vertical:** the player's arrival spot (standing, `x = col`, storey 2 when
     going up / storey 0 when going down).
   They face into the room.

*(Rev C, as built: a follower's entry box overlaps the hero's arrival box, so it
materialises as soon as that box is free. That takes **up to 4 hero steps** (the
widest follower, the 4-cell rat, needs the hero fully clear of the edge), not
necessarily the first step. See #24.)*

**Materialise rule (each turn, step 3 of §3.2, only for `room == CUR_ROOM`):** in
slot order, a `PENDING` monster whose body box is free of all non-pending entities
clears `PENDING` and appears. Horizontal followers **walk in** with a 2-tick tween
from the edge column (col 0 or 31, which is open on the exit storey). Vertical
followers and in-place-pending monsters **pop in** at their position. Until then
they are invisible, don't collide, and don't act. So a follower enters on the first
turn after the player steps off the arrival spot, which is usually the turn after
arriving.

- If the player leaves a room while monsters are still pending there, they stay
  pending and are resolved when the player returns.
- A follower may be chosen again on a later exit. It can chase you through any
  number of rooms.
- **Why this shape:** it needs no new storage, no off-screen simulation and no
  pathfinding. It is fully deterministic (fixed ordering, no RNG). It never
  violates the sprite cap. And a follower can never appear inside the hero or
  another monster.

---

## 4. Colour & clash (user change 1: coloured floor bands kept)

### 4.1 Zoning

The two-band idea (`foundations.md` F9) is kept, repeated per
storey. **Air bands are PAPER black; floor rows are a coloured band.** Every sprite
attr has black paper, so a sprite may only ever stamp **black-paper cells**. §4.2
proves that it does.

| Attr | Value | Cells |
|---|---|---|
| `ATTR_AIR` | `$00` | air-band empty cells |
| `ATTR_WALL` | `$01` | wall cells (cols 0/31) **in air bands**, dim blue bricks on black |
| `ATTR_FLOOR` | `$0F` | **floor-row** PLATFORM / end-caps / wall cells: PAPER blue, INK white (the coloured band) |
| `ATTR_LADDER` | `$02` | ladder cells in air bands **and hole cells in floor rows** (black paper, dim red rungs) |
| `ATTR_POTION` | `$42` | potion tile (sheet: INK 2 bright) |
| `ATTR_CHEST` | `$06` | chest |
| `ATTR_TORCH` | `$46` | torch (optional) |
| `ATTR_HIT` | `$42` | hit flash, stamped instead of the kind attr for 2 ticks (same value as the potion, which is harmless) |
| `ATTR_HEAL` | `$44` | quaff flash on the hero for 2 ticks |

### 4.2 Why a sprite never stamps a coloured floor cell (every case)

Sprites are drawn with an **exact footprint**: `cols = ((frame_px AND 7) + W + 7)
div 8`, `rows = ((frame_py AND 7) + H + 7) div 8`. **The spike's branch-free "always
stamp one extra column" trick is forbidden**, because it would stamp the cell beside
a hole.

| Case | Why it's safe |
|---|---|
| Standing / walking | Body rows = `7s … 7s+5` (air). Tweens are horizontal only, so py stays cell-aligned. Feet stand *on* the floor row and never cover it. |
| Any frame of a standing entity (attack overhang, HURT, BLOCK, DEAD, lunge) | Bottom-anchored with `H ≤ body_h` ⇒ inside the same air rows. Overhang is horizontal only. |
| Walking across a ladder top (hole in the floor under you) | Still standing: the body is above the floor row. |
| Climbing through a floor row | Snap invariant (§3.4): `px = col×8` ⇒ footprint cols = **exactly `col…col+2`** = the hole cells (black). The CLIMB frames are 24 px = body width. |
| Stepping onto / off the ladder at top or bottom | Every intermediate climb position has the same cols. The end positions are standing (air rows). |
| Monster on a ladder | Same snap invariant. Climbers are the only monsters that enter floor rows. |
| Wide frames while in the floor gap | Impossible: **no combat on ladders** (§4.3), so ATTACK/HURT/BLOCK/DEATH never play mid-ladder. Only CLIMB (or the WALK fallback, also 24 px) is drawn there. The quaff flash is attr-only on the exact 3-col footprint = hole cells. |
| Flyers | y is clamped to the air band. x-tweens only widen the footprint within air rows. |
| Wizard zap tiles | Drawn on the staff row of a standing Wizard = an air row, only in the gap cells (empty air). |
| Two sprites overlapping | Only in air rows (attack overhangs, adjacent 4-px tweens) or in hole cells (two climbers on one shaft, vertically adjacent). All black paper. A shared cell shows the ink of the sprite drawn last. Draw order = monsters in slot order, **player last**. Erasing a sprite forces a re-blit of every sprite that intersects its erased region. |
| Exit tweens / follower walk-in | Horizontal exits are open only in air rows. The down-exit first step covers the row-20 hole cells only (snap). |
| HUD rows 21–23 | Never reached (the down-exit triggers on the first step). |

**Why no combat on ladders:** every hero body mid-ladder straddles a floor row (a
6-row body in a 7-row period). Any frame wider than 24 px there would stamp coloured
floor cells. Banning ladder combat is the cheapest complete guarantee. Its
gameplay side effect, a "safe" ladder, has no exploit value now that regen is gone
(nothing heals while you wait). The yield rules in §6.4 stop ladders from becoming
softlocks.

### 4.3 Restore model

**DECISION: restore attrs from the room tile map, not from a 672-B attr copy.**
Air bands are not a single constant: they hold walls, ladders, potions, chest and
torch. So a pure band-constant restore is wrong, but the tile map (672 B, required
anyway to draw the room) gives it for free:

- **Erase = redraw the background tiles under the old footprint from the tile map
  (the spike's `draw_cell`).** `draw_cell` writes the glyph **and** the tile's attr
  (`TILE_ATTR[tile_id]`; for WALL the attr depends on whether the row is a floor
  row). So the attr restore costs **0 extra**, with no second buffer.
- If profiling moves erase to a clean-background **bitmap** copy (the planned speed
  lever, R-1), restore attrs as `TILE_ATTR[tile_map[cell]]`: one table lookup,
  ≈20 T/cell, about the same as copying from a shadow. The 672-B attr copy of rev A
  is **dropped** either way.

**Legality set** for rows 0–20 = {`$00`, `$01`, `$0F`, `$02`, `$42`, `$06`, `$46`}
∪ {colour attrs of the hero + kinds in the room} ∪ {`ATTR_HIT`, `ATTR_HEAL`,
`ATTR_ZAP` = `$45`}. There
is also a structural assertion: **every floor-row cell outside hole cells is always
`ATTR_FLOOR`**.

---

## 5. Sprite data, facing, anchors, budget

### 5.1 Frame classes: the pre-shift rule

All screen x values are multiples of 4, so only shifts 0 and 4 exist.

- **MOTION frames** (walk cycles, flyer loops, slime loop, rat run) store **both**
  shifts.
- **STATIONARY frames** (idle, climb, attack, hurt, block, dead) are drawn only while
  the body is cell-aligned. Attacks and reactions never overlap a horizontal tween
  (§7), and climbs are snapped. So each stores **one shift per facing**: `ax mod 8`
  (right) / `ax_L mod 8` (left).
- Build-time ASSERT: anchors are multiples of 4. Debug-build trap: a STATIONARY frame
  drawn with body `px AND 7 ≠ 0`.

### 5.2 Facing (accepted): **mirror at load time into RAM**

Runtime mirroring would add about 15–20 T per byte pair (a bit-reverse table + a
reversed column walk), ≈ +25–40 % per left-facing blit on the hot path.
Pre-mirroring costs bytes only. The artist emits right-facing, unshifted frames.
The engine generates the mirror + shifts (monsters at boot, the chosen hero after
selection, ≈100 T/byte ≈ 1.1 s total). `SYMMETRIC` frames (CLIMB back-views) skip
the mirror.

| Set (masked, both facings, §5.1 rule, new art included) | Bytes (≈) |
|---|---|
| Knight (largest hero; only the chosen hero is generated) | 13.4 K |
| Wizard / Rogue | 10.9 K each |
| Skeleton | 9.2 K |
| Goblin | 6.1 K |
| Ghost | 3.2 K |
| Rat / Bat / Slime | 2.2 K / 2.2 K / 2.0 K |
| **Total resident (worst hero + all monsters)** | **≈ 38.3 K** |

Recommendation: uncontended **banks 0, 4, 6** (48 K). Unshifted sources (≈16–20 K)
go in a contended bank, read only at generation time. One `$7FFD` switch per blit.
No frame may straddle a bank. Final placement belongs to `memory-map.md`.

### 5.3 Anchor convention

- Bottom-anchored: `frame_py = body_py + body_h − H`, with **`H ≤ body_h`**.
- **`ax`** = in the right-facing art, the px offset from the frame's left edge to the
  body box's left edge. Right: `frame_px = body_px − ax`. Left:
  `ax_L = W − ax − body_w`, `frame_px = body_px − ax_L`.
- Constraints (the converter rejects violations): `W mod 8 == 0`; `ax mod 4 == 0`;
  `0 ≤ ax ≤ 8` (backward ≤ 1 cell); `0 ≤ ax_L ≤ 16` (forward ≤ 2 cells). The body is
  always within cols 1–30. Forward overhang is drawn only during an attack, whose
  target is on screen in front (no whiff attacks). So no clipping is ever needed.
- **Measuring `ax`:** overlay the frame on IDLE (or WALK1) with the torso/hips column
  and feet line coinciding. If the offset isn't a multiple of 4, re-pad the frame.
- **Measured from the sheet:** Knight WIND-UP/SLASH/FOLLOW `ax = 4` (`ax_L = 12`) ✓.
  Knight BLOCK ≈ 2 and HURT ≈ 3 need **re-padding** (§10.3).

### 5.4 Masks

The converter derives them. Mask = the filled silhouette (8-connected flood from
outside) grown by a 1-px halo, clipped to the frame. **Ghost exception:** the
dithered tail rows are data-only masked.

### 5.5 Per-tick budget & on-screen cap

Extrapolated from the spike (erase ≈ 250 T/cell, masked blit ≈ 45 T/byte, attr
≈ 30 T/cell). The reviewer re-measures.

| Sprite in motion | ≈ T per redraw |
|---|---|
| 24×48 walk/climb | 15.5k |
| 40×48 knight slash | 22k |
| 32×48 cut/cast/stab | 18k |
| 24×32 goblin/ghost | 10–12k |
| 32×16 rat / 24×16 bat, slime | 6k / 5k |

Worst realistic tick ≈ 88k T of sprites + ≈10k logic/HUD ≈ **100k (≈120k contended)**,
under the **2-frame tick (141.8k)**.

**Measured (rev C):** the heavy-mix scene (2 Skeletons + full cap, attacks in flight)
measured **154,852 T per tick = 109 % of the 2-frame budget** *before*
optimisation. So the estimate above was optimistic. **User decision (2026-09-25):
optimise the renderer, do not cut the design.** The caps stay at **2 Skeletons** and
**2 ticks per step**. **Target: the heavy-mix tick ≤ 95 % of 141.8k T (≤ ≈134.7k
T)**, leaving ~5 % headroom for contention variance. The levers are the §4.3
clean-background erase and the reviewer's list. The measurement and the result are
recorded by the manager in `plan.md`. Until the target is met, overruns are
presentation-only (`OVERRUN_COUNT`), never logic.

> **Caps superseded by `game.md` §9.3** (weight cap incl. projectiles).

**Caps (binding):** **hero + 4 monsters on screen**; **≤ 2 Skeletons** among them.
The caps are enforced at authoring (≤ 3 monsters per room initially) and at
**follow time** (§3.7 step 3), the only way a room's population grows.
`OVERRUN_COUNT` counts ticks over budget. Overruns affect presentation only.

---

## 6. Combat, AI, potions

### 6.1 Reach, facing, same-floor rule

- **Gap** = empty cells between body boxes in the facing direction. **Vertical
  overlap** = body boxes share a row.
- **In reach** ⟺ both entities **standing or flying** (neither mid-ladder) ∧
  vertical overlap ∧ `0 ≤ gap ≤ reach`. Vertical overlap is the same-floor rule:
  walkers on different storeys never overlap, and a flyer anywhere in the hero's
  storey overlaps the 6-row hero.
- **Bump-to-attack (player):** LEFT/RIGHT picks the nearest hostile in that
  direction that is in reach. If there is one → ATTACK (face, no move). Otherwise →
  move/illegal. **No whiff attacks.**
- **Line of attack (rev C):** the candidate target is the **nearest body** in the
  facing direction whose box vertically overlaps the attacker, of any kind or
  state. If that nearest body is **mid-ladder**, there is **no target**: the ladder
  body blocks the line and nothing behind it can be hit. This matters for the
  Wizard's reach 3, whose zap cannot pass a climber. It applies to monsters too.
- **Blocking:** body boxes never overlap (cell AABB, pending monsters excluded).
- Reach: Knight 1, Rogue 1, **Wizard 3**, all monsters 1 (gap 0 or 1). Attack frames
  overhang 8–16 px forward over the gap.

### 6.2 Rolls (reuse `foundations.md` F1/F2/F3 verbatim)

To-hit `d20 + atk ≥ 10 + eva`. Damage `1dN + bonus`, saturating. xorshift16, fixed
seed, mask-and-reject. **RNG consumption order:** player to-hit, then damage. Then
each monster in slot order: AI randomness (bat jitter), then to-hit, then damage.
Follow selection and potions use **no RNG**. **HP regen is removed** (rev B).

### 6.3 Starting stats (PROTO; retune in P4)

| Kind | hp | atk | eva | dmg | reach | move | act every | notes |
|---|---|---|---|---|---|---|---|---|
| Knight | 22 | 2 | 2 | 1d6 | 1 | walk+climb | 1 | BLOCK frame on an incoming miss |
| Wizard | 14 | 3 | 1 | 1d6+1 | **3** | walk+climb | 1 | zap |
| Rogue | 18 | 5 | 3 | 1d4+1 | 1 | walk+climb | 1 | |
| Rat | 3 | 0 | 1 | 1d2 | 1 | walker | 1 | |
| Slime | 5 | 0 | 0 | 1d3 | 1 | walker | **2** | acts on even `TURN_COUNTER` |
| Bat | 3 | 1 | 4 | 1d2 | 1 | flyer | 1 | erratic |
| Goblin | 6 | 1 | 1 | 1d3 | 1 | walker+climb | 1 | |
| Ghost | 7 | 2 | 3 | 1d4 | 1 | flyer | 1 | |
| Skeleton | 10 | 2 | 2 | 1d4 | 1 | walker+climb | 1 | |

All heroes start with **1 potion**. Sanity check (Knight): ≈20 expected damage over
8 monsters vs 22 hp + 5 potions × 8. Winnable with care, lethal when reckless.
Followers make fleeing costly, which is intended.

**Balance note (rev C, engineer observation):** on the fixed-seed reference
walkthrough, the **Knight dies before the chest if the route skips room C's potion**
(id 2, col 29 s1). **Recommendation: accept for PROTO, do not retune yet.**
- Needing the potions is the intended "careful vs reckless" line, and potion 2 is a
  2-cell detour off the §8.2 route (C s1, walking left from col 24).
- Fix the **walkthrough**, not the numbers: the reference script must collect every
  potion on or next to its path (ids 2 and 3; 0 and 1 are optional).
- A single seed is one sample, not a balance measurement. Before P4, run the
  walkthrough with **all three heroes** and a few seeds. The Wizard (14 hp) is the
  likelier outlier.
- If tuning is then needed, turn **one knob first: potion heal 8 → 10**. It applies to
  every hero equally and rewards exploring. Raising Knight hp would only mask the
  problem for one hero.

This is a recommendation; the numbers above are unchanged.

### 6.4 Monster AI (only non-pending monsters in the current room act)

`storey_ref(e) = min(2, (e.y + e.h) div 7)`.

**Yield & anti-cork (rev C, as built; checked first, all kinds).** While the player
is **mid-ladder**, define the hero's **remaining climb path** = every box the hero
would occupy from its next step up to and including the **standing box at the
ladder end** in its current climb direction.

1. **Mid-ladder monster on the path** (a climber on the same shaft): yields
   **along the ladder, in the hero's climb direction** (moving ahead of the hero,
   away from it). **Never sideways:** a non-flyer can never step sideways while
   mid-ladder, in any rule. If the along-ladder step is blocked → wait.
2. **Standing (or flying) monster whose box intersects the path:** steps 1 cell
   sideways off the path, toward the **preferred side** (away from the shaft
   centre). If that side is blocked it **falls back to the other side**, else waits.
   Flyers may use any in-band move that leaves the path.
3. **Anti-cork:** while the player is mid-ladder, **no monster move may end on any
   box of the remaining climb path.** This covers yield steps, approach steps, climb
   starts and flyer moves. A monster never steps back onto the path it just left, so
   yielding cannot oscillate.

**B14 fix rules (engineering rule 2026-10-04 (B14), designer-confirmed).**
- **Facing tie-break:** a yielding monster standing exactly on the shaft column steps
  toward its **facing side** (replaces the "roomier side" tie-break, which oscillated
  5->6->5 beside a wall).
- **Forced yield:** when the hero's climb is blocked by an entity (the turn becomes a
  wait), the monsters in that turn yield and may not step onto the climb path, even if
  the hero has not yet left the floor.
- **Vertical fallback:** a flyer whose two sideways steps are blocked tries up, then
  down, within its band, ending off the climb path; else it waits.
- **Known residual (superseded by the squeeze below):** a flyer with a wall on one side
  and an immovable body on the other would wait.
- **Squeeze past (designer decision 2026-10-04, hard anti-softlock guarantee).** The
  hero keeps `climb_block_id` (blocker entity id) and `climb_block_n`. Each climb
  start/continue blocked by an entity E: if `E == climb_block_id` then `n++` else
  `climb_block_id = E, n = 1`. Any other hero action, or a climb that succeeds, clears
  both. On the **2nd consecutive** block by the same E, instead of a wait: the hero
  and E **swap cells** (E takes the hero's foot cell; hero takes the cell E occupied,
  the first rung cell, and is mid-ladder), costing the hero's turn; clear counters.
  The swap is legal for every entity kind including bosses, sleepers and flyers (the
  swap is the guarantee; no exclusions), only if the hero's destination is the cell E
  occupies. If E sits further along the climb path, the hero swaps with the first
  blocker on it. Monsters get **no free attack** from the swap; they act normally
  afterwards (a reach monster hits as usual). E keeps its facing and is not stunned.
  Message `YOU SQUEEZE PAST THE <NAME>` (names <= 8 chars, total <= 32). A blocker
  that yields on the first wait never triggers the swap (the normal case).
  **B16 (engineering rule 2026-10-05):** a *flyer* of the other storey (its band is
  not the storey the climb leaves) is not moved — the foot cell lies outside its air
  band, and moving it dropped a ghost over the top box onto the floor below. It goes
  PENDING in place (hidden, non-colliding) and materialises once its box is free.
  Flyers never leave their band. `tests/game.py` #64 / #65.

Monsters get their fights when the hero steps off: the player acts first each turn,
and in-reach monsters then attack.

**Walker** (Rat, Slime, Goblin, Skeleton):

1. If the player is in reach → face and **attack**.
2. Else if standing and `storey_ref(me) == storey_ref(player)` → step 1 toward the
   player. If blocked → wait.
3. Else:
   - **Climber:** if mid-ladder → continue in `ai_dir` (blocked → wait). Else pick
     the nearest segment on my storey leading toward the player's storey (up
     `{col, my_s}` / down `{col, my_s+1}`; exit segments excluded). Step toward col.
     At col, **start climbing only if no other entity is mid-ladder on that segment
     or in its far-end box** (no head-on ladder jams). Otherwise wait.
   - **Non-climber:** patrol. Step in the facing direction, reversing when blocked.

**Flyer** (Bat, Ghost):

1. In reach → attack.
2. Same storey as the player: `dx = sign(player.x − x)` (stop at gap 0),
   `dy = sign(7s+1 − y)`, clamped to the band. If the diagonal is blocked → x only →
   y only → wait. **Bat jitter:** if `rng_mod(4) == 0`, use step 3 instead.
3. Else: Bat wanders (`dx` = facing, reversing at walls; `dy = rng_mod(3) − 1`,
   clamped). Ghost drifts (`dx = sign(player.x − x)`).

**No softlock:** illegal inputs (no ladder, wall, terrain) cost no turn. **A
climb (start or continue) blocked by an entity counts as a WAIT** (rule by user
2026-10-02, as built): the turn is consumed, monsters act, so the blocker
yields (§6.4 yield rule) instead of the hero being frozen by a free no-op. A
chord falls back to its horizontal move first; the blocked climb has wait
priority (after G). The player can always reverse on a ladder (a reversal
blocked by a climber behind is also a wait). Monsters yield ladder ends and
never start a head-on climb; flyers never idle in a ladder-end box (§3.5).
Pending monsters never block anything. `tests/game.py` #58 / #59.

### 6.5 Hit feedback & reactions

- **Impact tick:** the target flashes `ATTR_HIT` for 2 ticks on a hit. The Wizard's
  `ZAP1/ZAP2` tiles fill the gap cells on the staff row for 3 ticks. The HUD message
  updates.
  - *(Rev C)* The zap **skips any cell covered by a drawn sprite's footprint**. So
    `ATTR_ZAP` (`$45`, in the §4.3 legal set) never lands inside a sprite
    footprint and never fights the attribute-follow. With the line-of-attack rule
    (§6.1), the gap is normally empty. The skip covers attack overhangs and flyers
    hovering in the gap row.
  - *(Rev C, as built)* When several impacts land on the same tick, **only the last
    impact's message is printed** (one HUD message line, no queue).
- **Reaction** (after the target's own action this turn): **HURT** 3 ticks on a hit.
  **BLOCK** 3 ticks when an attack misses the **Knight**. Other misses show nothing.
- **Death:** HURT 3 → DEAD pose 12 ticks (the Skeleton uses COLLAPSED). A monster is
  then erased and its slot freed. The hero stays on DEAD → `GS_DEAD` →
  `YOU DIED - PRESS ENTER` → `GS_SELECT` (new game, fixed seed reseeded, all rooms,
  monsters and potions re-initialised).

### 6.6 Potions (user change 3)

- **DECISION: carried, not auto-quaffed.** Walking over a potion adds it to
  `potions` (max **9**). **`G` = quaff**: `hp += 8` capped at `max_hp`,
  `potions −= 1`, costs **1 turn** (2 ticks). The hero flashes `ATTR_HEAL` and
  monsters act as normal. `G` with `potions == 0` **or `hp == max_hp`** does
  nothing (no turn, no waste). You can quaff on a ladder (attr-only flash, §4.2).
  The `potions` field is in §11.1.
  - **Why carried:** it turns healing into a decision (drink now, or save it for
    the skeleton), shows the stock in the HUD, and matches the existing design.
    Auto-quaff would waste potions picked up at full hp.
- **Heal amount 8:** roughly one monster fight's worth of damage for the Knight
  (22 hp), and more than half the Wizard's (14).
- **Regen: dropped.** Potions are the only healing. That also removes the incentive
  to camp safely on ladders (§4.2).
- **Pickup:** at the end of a turn, if the player is **standing** and its body cols
  cover a potion's col on its storey → pick it up. Monsters never pick up. Message:
  `YOU FOUND A POTION`. The tile becomes AIR (erased via `draw_cell`).
- **Persistence:** each potion has a level-wide id 0–7. `POTIONS_TAKEN` is a 1-byte
  bitmask; room build skips taken ids. It is reset only on a new game.
- **Placement:** a potion sits in the bottom air row of its storey (row `7s+5`), 1
  cell, never inside ladder cols. §8.2 lists 4 potions (+1 in the starting kit =
  5 heals ≈ 40 hp).

---

## 7. Animation state machine (per entity)

**States:** `IDLE`, `WALK`, `CLIMB` (moving or resting mid-ladder), `FLY`,
`ATTACK`, `HURT`, `BLOCK`, `DYING`, `DEAD`. `PENDING` entities are not drawn.

**Per-turn queue:** `[action] → [reaction, if any] →` the resting sequence. The
phase lasts until all queues are done, at least 2 ticks.

- Actions: `WALK`/`CLIMB`/`FLY`/walk-in (2 ticks, tween) or `ATTACK` or `QUAFF`
  (2 ticks, resting frame + `ATTR_HEAL` flash).
- Reactions start after the action. So wide frames never overlap a horizontal tween,
  and they can never happen mid-ladder (no ladder combat).
- The target's flash starts on the attacker's IMPACT tick. It is attr-only.

Sequences (frame × ticks; `!` = IMPACT; `⟲` loop; *italic* = new art from §10,
with the listed fallback in use until it lands):

| Kind | IDLE | WALK / FLY (per 2-tick step) | CLIMB | ATTACK | HURT | DEATH |
|---|---|---|---|---|---|---|
| Knight | IDLE1 16 ↔ IDLE2 16 ⟲ | WALK1-4, 1 tick each, continuous phase | *CLIMB1/2* alt per tick; rest CLIMB1 | WIND-UP 2 → SLASH 2! → FOLLOW 2 | HURT 3 (BLOCK 3 on a miss) | HURT 3 → *DEAD* 12 |
| Wizard | IDLE 16 ↔ *IDLE2* 16 ⟲ | WALK1-4 | *CLIMB1/2* | CAST1 2 → CAST2 3! (+ZAP) | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Rogue | IDLE 16 ↔ *IDLE2* 16 ⟲ | WALK1-4 | *CLIMB1/2* | STAB1 2 → STAB2 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Skeleton | WALK1 | WALK1-4 | *CLIMB1/2* | RAISE 3 → CUT 2! | *HURT* 3 | *HURT* 3 → COLLAPSED 12 |
| Goblin | WALK1 | WALK1-4 | *CLIMB1/2* | CLUB UP 3 → SMASH 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Ghost | FLOAT1 6 ↔ FLOAT2 6 ⟲ | same loop | — | FLOAT2 2 → *LUNGE* 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Rat | RUN1 | RUN1/RUN2 alt per tick | — | RUN1 1 → *BITE* 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Bat | FLAP UP 3 → GLIDE 3 → FLAP DOWN 3 → GLIDE 3 ⟲ | same loop | — | FLAP UP 2 → *DIVE* 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |
| Slime | WOBBLE 8 → SQUASH 4 → WOBBLE 8 → STRETCH 4 ⟲ | SQUASH 1 → STRETCH 1 | — | SQUASH 2 → *LUNGE* 2! | *HURT* 3 | *HURT* 3 → *DEAD* 12 |

**Fallbacks** (frame-table entries only, no separate code paths): CLIMB → the WALK
cycle; IDLE2 → none (static IDLE); HURT → the resting frame + flash; DEAD → the
resting frame blinking every 2 ticks for 12 ticks; LUNGE/BITE/DIVE → the wind-up
frame held.

**Idle phase** = `TICK_COUNTER + slot*5` (staggered). `ANIM_FREEZE = 1` → resting
sprites hold their first IDLE frame (capture-time-independent goldens).

---

## 8. World: the 4 PROTO rooms

### 8.1 Room descriptor (P4's generator emits the same)

`room_id`; `exits[]` = `{L/R, storey, dest}` and `{U/D, ladder col, dest}`;
`ladders[]` = `{col, s}`; `potions[]` = `{id, col, storey}`; `decor[]` =
`{tile, col, row}`; `spawns[]` = `{kind, col, storey, facing}`. Spawns are used
**once**, at new-game init, to fill entity slots with `room` set; after that the
slots are the truth (§3.7). The tile map (672 B) is built from the descriptor +
`POTIONS_TAKEN` at room entry. Only the current room's map exists.

### 8.2 Layout

```
  A (0,0) ⇄ B (1,0)          ⇄ = horizontal exit on storey 2
              ⇅               ⇅ = ladder shaft through floor/ceiling, col 24
  D (0,1) ⇄ C (1,1)
```

| Room | Exits | Ladders `{col,s}` | Initial spawns (kind, col, storey, facing) | Potions `{id: col, storey}` | Decor |
|---|---|---|---|---|---|
| **A** (start) | R s2 → B | {5,2}, {23,1} | **Hero** 2, s2, right · Rat 16, s2, left · Slime 14, s1, left | 0: col 28, s0 | torch col 0 rows 16–17 (optional) |
| **B** | L s2 → A · D {24,3} → C | {10,2}, {4,1}, {24,3} | Goblin 16, s2, left · Bat 18, s1 | 1: col 1, s0 | — |
| **C** | U {24,0} → B · L s2 → D | {24,0}, {24,1}, {6,2} | Skeleton 16, s2, left · Ghost 12, s1 | 2: col 29, s1 | — |
| **D** (goal) | R s2 → C | {22,2}, {8,1} | Skeleton 12, s0, left · Bat 12, s2 | 3: col 17, s1 | **CHEST** cols 2–3, rows 4–5 |

- **Win:** the player standing on storey 0 of D with `x ≤ 3` (body over the chest
  cols) → `GS_WIN` → `TREASURE! PRESS ENTER` → `GS_SELECT`.
- **Reference walkthrough** (no-softlock test): A right → B right to col 24 → down →
  C (s0, col 24) → down {24,1} → left to 6 → down {6,2} → left exit → D (s2) → left
  to 22 → up {22,2} → left to 8 (picks up potion 3) → up {8,1} → left to 3. About
  150 moves plus fights. Followers from B/C may join; the script is recorded
  against the fixed seed.
- Initial population ≤ 3 per room, ≤ 1 Skeleton, 8 monsters total. Slots: 1 + 8 = 9
  of 16.

---

## 9. Controls & HUD

> **Superseded by `game.md` §3** (controls, menu) **and `concept-screen.md` §5** (panel).

| Key | PROTO action |
|---|---|
| `H` / `O` | left: walk / bump-attack |
| `L` / `P` | right: walk / bump-attack |
| `K` / `Q` | up: climb |
| `J` / `A` | down: climb |
| `G` | quaff a potion (§6.6) |
| `Space` / `.` | wait (2-tick turn) |
| `1` / `2` / `3` | hero select: Knight / Wizard / Rogue |
| `Enter` | confirm on the win/death screens |

- **Chords:** vertical wins if a climb is legal, else the horizontal component, else
  nothing (no diagonals in side-view).
- Illegal inputs consume no turn. `D` (descend) is unbound in PROTO.

**HUD (rows 21–23):** row 21 = `KNIGHT  HP 22/22  POT 1`; row 22 = the last message;
row 23 = room letter (+ turn count if cheap). Fixed HUD attrs; sprites never enter.

**Hero select:** the three heroes' IDLE frames with names and `1 2 3`. A choice sets
`HERO_KIND`, generates the hero frames, initialises the world → `GS_PLAYING`.

---

## 10. Art requests (for `graphics-artist`)

Frames: 1-bit, right-facing, `W` a multiple of 8, bottom-anchored with
`H ≤ body height`, black paper, one ink per kind. For each frame deliver
**`name, W, H, ax, class (MOTION/STATIONARY), SYMMETRIC?`**. Masks are derived
(§5.4). Silhouette readability at 1× on black comes first.

### 10.1 State coverage matrix

✓ = exists · **NEW** = must be drawn · (reuse) = covered by an existing frame.

| Kind | Idle | Walk / fly | Climb | Attack wind-up | Attack strike | Hurt | Death | Block |
|---|---|---|---|---|---|---|---|---|
| Knight | ✓ IDLE1, IDLE2 | ✓ WALK1-4 | **NEW** CLIMB1-2 | ✓ WIND-UP | ✓ SLASH, FOLLOW | ✓ HURT (re-pad) | **NEW** DEAD | ✓ BLOCK (re-pad) |
| Wizard | ✓ IDLE, **NEW** IDLE2 | ✓ WALK1-4 | **NEW** CLIMB1-2 | ✓ CAST1 | ✓ CAST2 + **NEW** ZAP1-2 tiles | **NEW** HURT | **NEW** DEAD | n/a |
| Rogue | ✓ IDLE, **NEW** IDLE2 | ✓ WALK1-4 | **NEW** CLIMB1-2 | ✓ STAB1 | ✓ STAB2 | **NEW** HURT | **NEW** DEAD | n/a |
| Skeleton | (reuse WALK1) | ✓ WALK1-4 | **NEW** CLIMB1-2 | ✓ RAISE | ✓ CUT | **NEW** HURT | ✓ COLLAPSED | n/a |
| Goblin | (reuse WALK1) | ✓ WALK1-4 | **NEW** CLIMB1-2 | ✓ CLUB UP | ✓ SMASH | **NEW** HURT | **NEW** DEAD | n/a |
| Ghost | ✓ FLOAT1-2 | ✓ FLOAT1-2 | n/a | (reuse FLOAT2) | **NEW** LUNGE | **NEW** HURT | **NEW** DEAD | n/a |
| Rat | (reuse RUN1) | ✓ RUN1-2 | n/a | (reuse RUN1) | **NEW** BITE | **NEW** HURT | **NEW** DEAD | n/a |
| Bat | ✓ FLAP UP/GLIDE/FLAP DOWN | ✓ same | n/a | (reuse FLAP UP) | **NEW** DIVE | **NEW** HURT | **NEW** DEAD | n/a |
| Slime | ✓ WOBBLE/SQUASH/STRETCH | ✓ SQUASH/STRETCH | n/a | (reuse SQUASH) | **NEW** LUNGE | **NEW** HURT | **NEW** DEAD | n/a |

Quaff has no dedicated frame: resting frame + `ATTR_HEAL` flash (attr-only by
design, safe on ladders).

### 10.2 Missing frames & tiles: exact list

Sprite frames (32), unchanged from rev A:

| # | Kind | Frame | W×H | Count | Class | Pose (one line) | `ax` |
|---|---|---|---|---|---|---|---|
| 1–2 | Knight | CLIMB1, CLIMB2 | 24×48 | 2 | STATIONARY, SYMMETRIC | back view on a ladder: helmet from behind, shield on back, arms alternating on rungs, one knee raised | 0 |
| 3 | Knight | DEAD | 40×16 | 1 | STATIONARY | lying on his back, sword dropped beside | 8 |
| 4 | Wizard | IDLE2 | 24×48 | 1 | STATIONARY | robe hem swayed, hat tip dipped 1 px, orb raised 1 px | 0 |
| 5–6 | Wizard | CLIMB1, CLIMB2 | 24×48 | 2 | STATIONARY, SYMMETRIC | back view, hat cone from behind, staff slung across the back, arms alternating | 0 |
| 7 | Wizard | HURT | 32×48 | 1 | STATIONARY | recoiling backward, hat askew, staff flung up | 8 |
| 8 | Wizard | DEAD | 40×16 | 1 | STATIONARY | face-down, hat fallen ahead, staff beside | 8 |
| 9 | Rogue | IDLE2 | 24×48 | 1 | STATIONARY | cloak edge flutters, dagger hand shifts 1 px | 0 |
| 10–11 | Rogue | CLIMB1, CLIMB2 | 24×48 | 2 | STATIONARY, SYMMETRIC | back view, hood up, cloak hanging, arms alternating | 0 |
| 12 | Rogue | HURT | 32×48 | 1 | STATIONARY | doubled over, stumbling back, cloak flaring | 8 |
| 13 | Rogue | DEAD | 40×16 | 1 | STATIONARY | sprawled, cloak spread, dagger dropped | 8 |
| 14–15 | Skeleton | CLIMB1, CLIMB2 | 24×48 | 2 | STATIONARY, SYMMETRIC | back view: skull, spine, ribcage, bony arms alternating | 0 |
| 16 | Skeleton | HURT | 24×48 | 1 | STATIONARY | skull knocked sideways, ribs rattled, sword arm flung back | 0 |
| 17–18 | Goblin | CLIMB1, CLIMB2 | 24×32 | 2 | STATIONARY, SYMMETRIC | back view: big head and ears, club in belt, arms alternating | 0 |
| 19 | Goblin | HURT | 24×32 | 1 | STATIONARY | head snapped back, club low, knees buckled | 0 |
| 20 | Goblin | DEAD | 32×16 | 1 | STATIONARY | flat on its back, legs up, club beside | 4 |
| 21 | Ghost | LUNGE | 32×32 | 1 | STATIONARY | leaning forward, claws thrust ahead, dithered tail streaming | 0 |
| 22 | Ghost | HURT | 24×32 | 1 | STATIONARY | torn/distorted, face stretched, more dither holes | 0 |
| 23 | Ghost | DEAD | 24×32 | 1 | STATIONARY | dissolving to sparse dither, wisps rising | 0 |
| 24 | Rat | BITE | 40×16 | 1 | STATIONARY | stretched lunge, jaws wide, tail straight back | 0 |
| 25 | Rat | HURT | 32×16 | 1 | STATIONARY | hunched, tail kinked | 0 |
| 26 | Rat | DEAD | 32×16 | 1 | STATIONARY | on its back, feet up | 0 |
| 27 | Bat | DIVE | 32×16 | 1 | STATIONARY | wings swept back, claws and fangs forward | 0 |
| 28 | Bat | HURT | 24×16 | 1 | STATIONARY | wings crumpled, tumbling | 0 |
| 29 | Bat | DEAD | 24×16 | 1 | STATIONARY | wings folded, upside down on the floor line | 0 |
| 30 | Slime | LUNGE | 32×16 | 1 | STATIONARY | stretched into an engulfing wave | 0 |
| 31 | Slime | HURT | 24×16 | 1 | STATIONARY | splattered, droplets flying | 0 |
| 32 | Slime | DEAD | 24×8 | 1 | STATIONARY | flat puddle | 0 |

Tiles (8×8, 1-bit glyph; colour comes from the §4.1 attr):

| # | Tile | Attr context | Notes |
|---|---|---|---|
| 33–34 | ZAP1, ZAP2 | `$45` on black | horizontal bolt segment that tiles seamlessly, two alternating variants, centred on CAST2's staff-tip row (artist reports that row) |
| 35 | PLATFORM | `ATTR_FLOOR` (white ink on **blue paper**) | brick course. It must read on coloured paper: ink = mortar/highlights, and paper is the brick colour |
| 36 | WALL | `ATTR_WALL` in air bands (dim blue ink on **black**) **and** `ATTR_FLOOR` in floor rows | one glyph serving both paper contexts. Check it reads in both |
| 37–39 | LADDER_L, LADDER_M, LADDER_R | `ATTR_LADDER` (dim red on black) | left rail + rungs / rungs / right rail + rungs, a rung every 4 px. **Also used as the hole cells in floor rows**, so the floor visibly opens onto the shaft |
| 40–41 | PLATFORM_END_L, PLATFORM_END_R *(optional)* | `ATTR_FLOOR` | brick end-caps drawn on the floor cells either side of a ladder hole, so the blue band ends cleanly at the black opening. PROTO works without them (PLATFORM is used instead) |
| — | POTION | `$42` | exists in the sheet (8×8). Now a PROTO room pickup, no change |
| — | CHEST / TORCH | `$06` / `$46` | exist, used as-is |

### 10.3 Fixes to existing frames

- Anchor audit (`ax`) for every existing frame wider than its body.
- Re-pad Knight BLOCK (≈2) and HURT (≈3) to a multiple of 4.
- Ghost: mark the tail rows for the mask exception.
- Confirm all existing frames have `H ≤ body height` (they do on the sheet).

**Priority:** (1) PLATFORM/WALL/LADDER tiles + anchor audit/re-pads, which block the
first build. (2) HURT/DEAD for everything. (3) Attack strikes + ZAP. (4) CLIMB for 5
kinds. (5) IDLE2s, PLATFORM_END caps.

---

## 11. Engine hand-off: entity shape, observables, checklist

### 11.1 Entity record: fields (the 16-byte stride will not fit; the engineer lays out)

**Logic:** `kind`, `room` (0–3), `flags` {`ACTIVE`, `IS_PLAYER`, `HOSTILE`,
`FACING_LEFT`, `DYING`, `DIRTY`, **`PENDING`**}, `x` (body-left col), `y`
(body-top row), `hp`, `max_hp`, `ai_dir`. (Rev A's `spawn_x/spawn_y/spawn_facing`
are **removed**.)

**Render:** `px`, `py` (u8), `seq_id`, `seq_step`, `seq_timer`, `react_pending`,
`frame_id`, `drawn_col`, `drawn_row`, `drawn_cols`, `drawn_rows`, `flash_timer`,
`flash_attr` (HIT or HEAL).

**Player extras:** `potions` (0–9).
**Globals:** `CUR_ROOM`, `POTIONS_TAKEN` (1 B bitmask), `HERO_KIND`.

**Kind table:** `body_w`, `body_h`, `hp`, `atk`, `eva`, `dmg_die`, `dmg_bonus`,
`reach`, `act_period`, `archetype`, `CLIMBER`, `TALL` (for the cap), `colour_attr`,
`name`, sequence pointers.
**Frame table:** `frame_id → W, H, ax, class, symmetric, {facing × shift → bank,
addr, cols}`.

### 11.2 Test-observable state (addresses in `memory-map.md`)

`GAME_STATE` (+ `GS_SELECT`, `GS_TRANSITION`), `RNG_STATE`, `TURN_COUNTER`,
`TURN_PHASE`, `TICK_COUNTER`, `CUR_ROOM`, `HERO_KIND`, `POTIONS_TAKEN`, the entity
array (player = slot 0, incl. `potions`), `INPUT_SRC`/`KBD_MATRIX`, `INPUT_REPEAT`
(poke 0 = edge-triggered), `ANIM_FREEZE`, `ANIM_TRACE` (32-B ring of
`(slot, frame_id)` on every drawn-frame change + index), `OVERRUN_COUNT`.

### 11.3 PROTO playability checklist (ZRCP assertions)

Setup: fixed seed, `INPUT_REPEAT = 0`, `ANIM_FREEZE = 1` for goldens. "Wait for turn"
= poll `TURN_PHASE == INPUT`.

**Boot & select**
1. Boot → `GS_SELECT`. Inject `1` → Knight, `GS_PLAYING`, `CUR_ROOM = A`, player
   `x=2, y=14`, `hp = 22`, `potions = 1`.

**Movement — four directions**
2. **Walk right:** `L` → `x` 2→3, `TURN_COUNTER += 1`, facing right, ≥2 WALK frames
   in `ANIM_TRACE`, final `px = 24`.
3. **Walk left + mirror:** `H` → `FACING_LEFT = 1`. The sprite region equals the
   bit-mirrored render (golden).
4. **Wall blocks:** `x = 1` in A, `H` → no change, no turn.
5. **Climb up:** at col 5 on s2, `K` ×7 → `y` 14→7, `TURN_COUNTER += 7`. After the
   first step, `H`/`L` do nothing (no turn).
6. **Climb down:** `J` ×7 → `y = 14`.
7. **No ladder, no climb:** `K` at col 2 → no change.

**Coloured floors (rev B)**
8. **Floor band intact at rest:** every cell of rows 6/13/20 outside hole cols and
   outside open-exit cells has attr `ATTR_FLOOR` (`$0F`). Hole cells = `ATTR_LADDER`
   or a sprite attr.
9. **Floor band intact under climbing:** during the 7-step climb of #5, after every
   turn *and* on ≥4 sampled mid-turn frames: row 13 cols ∉ 5–7 are all `$0F`. The
   hero's `px AND 7 == 0` throughout.
10. **No floor stamp by wide frames:** a Knight slash on s2 next to the {5,2} hole →
    rows 13 and 20 unchanged outside holes, on every sampled frame of the attack.
11. **No combat on ladders:** a hostile in horizontal reach of a mid-ladder hero does
    not attack (monster hp/player hp unchanged over 5 turns). `L` toward it on the
    ladder → no turn.
12. **Yield:** a monster standing on the ladder-end box while the hero is mid-ladder
    moves off within 1 turn. The hero completes the climb.

**Monsters move**
13. **Walker approaches:** in A, waiting → the rat's `x` decreases until gap ≤ 1,
    then its attack sequence appears in the trace.
14. **Climber climbs:** arrive in C at s0 → within ≤30 turns the skeleton's `y`
    decreases by ≥7.
15. **Flyer 2D:** in B, over 10 waits the bat's `x` changes and its `y` takes ≥2
    values, always in 7–11.

**Combat**
16. **Player attack anim:** rat in reach, `L` → trace slot 0 = WIND-UP, SLASH,
    FOLLOW. `x` unchanged. Rat hp reduced or a miss message.
17. **Monster attack anim:** skeleton in reach, wait → trace RAISE, CUT. Player hp
    drops by the seeded amount on a hit.
18. **Anchor holds (rev C, as built):** during #16, the **drawn feet line sits at the
    computed anchor position**, `frame_px + ax` (or `+ ax_L` when facing left), on
    the body's bottom row. It is not required to be byte-equal to IDLE: wide *lunge*
    strike frames move the feet forward by design. Build-time `ax` ASSERTs pass.
19. **Wizard reach:** a rat at gap 3 → `L` attacks, `x` unchanged, ZAP tiles appear
    in the gap during impact.
20. **Monster dies:** hp → 0 → trace HURT, DEAD (or fallback). The slot is freed and
    its footprint equals the background (no pixel or colour trail).
21. **Hero dies:** poke `hp = 1` next to the skeleton, wait → `GS_DEAD`. `Enter` →
    `GS_SELECT`. A new game restores potions, monsters and `POTIONS_TAKEN = 0`.
22. **HP never underflows.**

**Persistence & following (rev B)**
23. **Persistence:** damage the slime in A (hp 5 → k), leave A, return → the slime
    has hp k at the same x/y (no reset).
24. **Follow (horizontal):** lure the rat to gap ≤ 4, exit A right → after the
    transition the rat's `room = B` and `PENDING = 1`. Nothing is drawn for it. The
    hero steps right; **within ≤ 4 hero steps** (as soon as its entry box is free) the
    rat is non-pending at `x = 1`, s2, facing right, and the walk-in trace appears.
    It is never visible before its box is free.
25. **Non-follower stays:** the slime (s1) in A keeps `room = A` in #24.
26. **Follow (vertical, climbers only):** the goblin within 4 cells when the hero
    goes down {24,3} in B → the goblin's `room = C` and it materialises at s0,
    `x = 24` after the hero moves. A bat within 4 cells does **not** follow.
27. **Cap:** set up (poke) a destination holding 3 monsters and 2 candidates → exactly
    1 (the nearest) follows. A Skeleton candidate is refused if the destination holds
    2 tall monsters.
28. **Arrival conflict:** poke a monster onto the arrival box, then enter → it is
    `PENDING` in place and reappears once the hero moves off.
29. **Transition hides sprites:** during `GS_TRANSITION`, no sprite attr appears in
    rows 0–20.

**Potions (rev B)**
30. **Pickup:** walk over potion 0 in A → `potions += 1`, bit 0 of `POTIONS_TAKEN`
    set, the tile cell = AIR/`ATTR_AIR`, message shown.
31. **Persistent once taken:** leave A and return → potion 0 absent.
32. **Quaff:** with `hp < max_hp`, `G` → `hp = min(max, hp+8)`, `potions −= 1`,
    `TURN_COUNTER += 1`. With `hp == max` or `potions == 0` → no change, no turn.
33. **Max 9:** poke `potions = 9`, walk over a potion → stays 9 and the potion
    stays on the floor. (Decision: a full pack does not pick up.)

**World & end**
34. **Horizontal transition:** A → B, `CUR_ROOM = B`, player `x = 1` s2. HUD rows 21–22
    byte-identical before and after. *(Rev C, as built: the row-23 **room letter
    updates** on transition, so row 23 differs only in that cell.)*
35. **Vertical transition:** B col 24 `J` → C, s0, `x = 24`. `K` → back in B, s2,
    `x = 24`.
36. **Win:** reach the chest → `GS_WIN`. `Enter` → `GS_SELECT`.
37. **No softlock:** the recorded §8.2 walkthrough reaches `GS_WIN` within a bounded
    turn count.
38. **Determinism:** the same script twice → identical `RNG_STATE`, `TURN_COUNTER`,
    all entity hp/positions/rooms, `POTIONS_TAKEN`.

**Rendering**
39. **Clash legality:** all attrs in rows 0–20 ∈ the §4.3 legal set on every sampled
    frame. Footprint cells = the sprite attr (or flash). Vacated cells = the tile attr.
40. **Budget:** `OVERRUN_COUNT` reported after the walkthrough, target 0. The
    heavy-mix tick is measured against the §5.5 target of ≤ 95 % of 141.8k T.

**As-built additions (rev C). Numbers match the test ids in `tests/game.py`.**
The zap-skips-sprites check is part of **#19** ("no ZAP attr inside the target's
drawn footprint").
- **12b. Mid-ladder yield is along the ladder** (§6.4 rule 1): a climbing monster in
  the hero's path moves in the hero's climb direction and is never off the shaft
  while mid-ladder. The hero completes the climb.
41. **Hold-to-repeat** (§3.1): holding `L` for 20 ticks gives ≥ 9 steps (2 ticks per
    step), exactly one turn per step.
42. **Flash under overlap** (§4.2 overlap rule): a flashing hero keeps its pixels
    when an overlapping sprite (skeleton) is redrawn on the same tick.
43. **Paging-lock check** (§11.4): unlocked → start continues; locked → stops in the
    check with `LOAD FROM 128 BASIC` printed.
44. **Sprite allocator never crosses `$10000`** (§5.2, no frame straddles a bank):
    an allocation that would pass the end of a bank opens the next bank at `$C000`.
45. **Damage-list overflow** (§11.4): a full pending/damage list grows its last rect
    to the bounding box / whole playfield. `DMG_OVERFLOW` is counted.
46. **Ladder body blocks the zap** (§6.1 line of attack): a climbing goblin in the gap
    → no CAST, and the rat behind it is untouched. Control: a clear gap-3 rat is
    zapped.
47. **Yield fallback / anti-cork** (§6.4 rules 2–3): a hero corked at the ladder
    end still completes the climb.
48. **Potion tile without a list entry** (§6.6): a stray POTION tile not in the
    room's `potions[]` is not picked up and stays in the map. `POTIONS_TAKEN`
    unchanged.
49. **`CLIP_TRAP`** (§11.4): a stamp with `col + width > 32` is clipped at col 31
    (no wrap into the next row) and counted in `CLIP_TRAP`.

### 11.4 Robustness guards (rev C, as built)

- **Paging lock check at start:** if `$7FFD` paging is locked (a 48K-mode boot), the
  game shows **`LOAD FROM 128 BASIC`** and halts instead of running with broken
  banking.
- **+2A/+3 unsupported** for PROTO. Their contention pattern and paging differ from
  the §5.2 bank assumptions (uncontended 0/4/6). Out of scope; documented, not
  detected.
- **Damage-list overflow:** if a tick's dirty/erase list overflows, the renderer
  falls back to redrawing one larger enclosing rectangle. That is correct but
  slower (it may count an overrun), and never drops a region.
- **`CLIP_TRAP`:** if a write would have `col + width > 32`, it is **clipped at col 31**
  (never wrapping into the next row) and counted in `CLIP_TRAP`. §5.3's anchor
  limits make this impossible by design, so a non-zero count (asserted 0 over the
  walkthrough, #40) means a data or anchor bug. The clip is only a safety net. (#49)

---

## 12. Decisions log & remaining confirmations

**User-confirmed (2026-09-24):** 3 storeys + 3-row HUD; 25 Hz / 4 px; turn-based +
key repeat + bump repeat; 24 px ladders; storey-bound flyers (no phasing); reach-3
zap tiles; visual-only BLOCK; mirror at load; chest-touch win; death → select with
the same seed; full art scope.
**User-changed and resolved in rev B:** coloured floors (§4), persistent/following
monsters (§3.7), potions replacing regen (§6.6).
**Rev C (2026-09-25):** as-built reconciliation (see the header note). User decision:
optimise the renderer to ≤ 95 % of budget rather than cut caps. Balance: accept
for PROTO, fix the walkthrough route, re-evaluate across heroes/seeds before P4
(§6.3).

**New designer decisions in rev B (flag if you disagree; none block the engineer):**
1. **No combat on ladders** (neither side can attack or be attacked mid-ladder).
   This is the clash guarantee for coloured floors, and it replaces rev A's
   "fight from a ladder".
2. **Monster yield rule** at ladder ends + no head-on climbs (anti-softlock).
3. **Follow parameters:** gap ≤ 4, same storey, ≤ 2 followers per exit, climbers
   only through vertical exits. Followers walk/pop in after the hero leaves the
   arrival spot.
4. **Potions:** carried (`G`), heal 8, max 9 carried, start with 1, 4 placed; a full
   pack leaves the potion on the floor; quaff at full hp is refused.
5. **Floor band attr `$0F`** (white on blue, not bright). Air-band walls are dim blue
   on black.

**Open risks:**
- **R-1 (rev C: measured):** heavy mix = 154,852 T/tick (109 %) before
  optimisation. The user chose renderer optimisation to ≤ 95 %, keeping 2 Skeletons
  and 2 ticks/step (§5.5).
- **R-2:** the ≈38 K sprite memory depends on the §5.1 single-shift rule for
  STATIONARY frames.
- **R-3:** single-buffer flicker at 25 Hz. The fix is SPIKE-4's bank-7 flip.
