# Tome of the Dead — Foundations (stable rules and contracts)

> Current design set = `docs/design/prototype.md` (rev C, the authoritative game
> spec) + this file. Created 2026-10-01 by consolidating the still-binding parts of
> the archived `docs/archive/design/spectrum-design.md` (top-down Slice-1 design) and
> `docs/archive/design/sideview-renderer.md` (spike design). Text is copied
> near-verbatim; spike-only measurements and history are dropped. Where this file and
> `prototype.md` disagree, **`prototype.md` wins**.
>
> Section ids (F1..F9) are stable; cross-refer as "foundations F1". The "was ..."
> tag names the origin in the archived docs.

| Id | Topic | Was |
|---|---|---|
| F1 | To-hit roll | spectrum-design §5.1 |
| F2 | Damage | spectrum-design §5.2 |
| F3 | RNG and determinism contract | spectrum-design §5.6 |
| F4 | Turn-loop invariants | spectrum-design §4.1 (properties only) |
| F5 | Room-transition scroll | spectrum-design §R1 |
| F6 | Room-based dungeon | spectrum-design §R2 |
| F7 | Keyboard rationale and input contract | spectrum-design §3 |
| F8 | Sprite data contract | sideview-renderer §1.2, §1.4, §1.7 |
| F9 | Colour zoning and attribute-follow | sideview-renderer §2.2, §2.4 |

---

## F1. To-hit roll (was spectrum-design §5.1)

Single-byte threshold roll, no multiply.

- Roll `r = rng_d20()` = **1..20** (`rng_byte()` masked to 5 bits, reject >= 20 and
  reroll; seed-deterministic, see F3).
- **Hit if** `r + attacker.atk >= 10 + defender.eva`.
  - `atk` and `eva` are per-kind constants (prototype §6.3). The constant `10` is the
    base difficulty.
- A natural 20 auto-hit / natural 1 auto-miss is optional; include only if it costs
  nothing, and document it if added. (Not part of the PROTO contract.)

## F2. Damage (was spectrum-design §5.2)

- Each kind has a damage descriptor `(die_size, bonus)`; **`num_dice` is always 1**:
  effective damage = `rng_mod(die_size) + 1 + bonus`.
- Damage is subtracted from `hp` with a **saturating** subtract (never underflows
  past 0). `hp == 0` means dead.
- Worked example for a test assertion: a `1d3+0` attacker vs `hp=3`; with a pinned
  seed the kill turn is fixed, and `test` asserts "dies on turn N".

## F3. RNG and determinism contract (was spectrum-design §5.6)

Requirements: deterministic, cheap on Z80, one word of state, shifts and xors only.

**Algorithm: 16-bit xorshift (`xorshift16`)**, state in a 2-byte word `RNG_STATE`
at a **stable named address** (recorded in `docs/memory-map.md` under test-observable
addresses, readable via ZRCP):

```
; state is a non-zero 16-bit word
x ^= x << 7
x ^= x >> 9
x ^= x << 8
return x            ; full 16-bit result; low byte is rng_byte()
```

(The engineer uses a verified triplet. Design requirement: full period 2^16-1,
never yields 0 from a non-zero seed. An 8/16-bit LFSR with the same properties is an
acceptable alternative.)

Derived rolls:
- `rng_byte()` = low 8 bits of one xorshift step.
- `rng_mod(n)` = `0..n-1`. For small `n` (2, 3, 4, 6, 20) use **mask-and-reject**
  (e.g. d20: mask to 5 bits, reject >= 20 and reroll). No modulo, no divide. For
  powers of two a single mask suffices.

**Seed:** a **fixed compile-time seed constant** by default, so a build is fully
reproducible and `test` can assert exact outcomes and golden screens. The seed is a
named constant and `RNG_STATE` is readable via ZRCP. If a random-seed mode is ever
added, expose a flag the harness can force to the fixed-seed path.

**Determinism contract:** given the fixed seed + a recorded input sequence, the
entire run (monster placement, every roll) reproduces bit-for-bit. This is what makes
golden-screen and state assertions meaningful. RNG consumption order is defined in
prototype §6.2.

## F4. Turn-loop invariants (was spectrum-design §4.1, properties only)

The PROTO loop shape and animation phase are in prototype §3.1/§3.2. The invariants
below still hold:

- **Player acts first, then monsters in slot-index order**, every turn. Given the
  same RNG state and inputs, the run is reproducible.
- **No real-time logic:** nothing happens without a player action. Interrupts may
  pace presentation (the 25 Hz tick), but logic is action-paced.
- **One legal action = one turn.** An illegal action (into a wall, climb with no
  ladder, quaff with nothing to quaff) **costs no turn**.
- No speed/energy system: all actors take one action per turn (a monster's `act
  every` period in prototype §6.3 is the only exception).

## F5. Room-transition scroll (was spectrum-design §R1; Cauldron model)

Continuous scrolling during play is **dropped**. The model is *Cauldron* (Hewson,
1985):

- **Normal gameplay: the screen is STATIC.** Entities move within the current room.
  Nothing scrolls while the player walks; the renderer redraws only dirty
  sprites/cells. No bitmap shift on the hot path.
- **Room transition: gameplay pauses and the screen scrolls once.** When the player
  steps across a room boundary (an exit), the turn loop **freezes**, the playfield
  bitmap is shifted left/right (or vertically, F6) toward the adjacent room in a
  single animated sequence, then play resumes in the new room.
- **Budget:** shift 4-8 px/frame via a pixel-shift chain (`RLCA`/`RRCA` per byte
  row). A full 256 px room width = 32-64 frames = 0.64-1.3 s. Because gameplay is
  frozen, the transition may spend the **whole frame budget**; the cost is paid
  infrequently and off the interactive path. Start at 8 px/frame (~0.64 s); drop to
  4 if it tears or reads too fast. (PROTO uses 8 px/frame horizontal and whole-char-row
  vertical, prototype §3.6; only rows 0-20 are shifted, the HUD is not.)

## F6. Room-based dungeon (was spectrum-design §R2)

- **A room = one screenful.** No intra-room scrolling.
- **Rooms connect at edges.** A room has up to 4 exits (left/right/up/down). Stepping
  onto an exit triggers the F5 transition to the neighbouring room. Horizontal exits
  scroll left/right; vertical exits scroll up/down (whole-screen `LDIR` by 8-px
  bands, cheaper than horizontal, still frozen-budget).
- **Corridors are narrow rooms.** No special case: the map model is "a set of rooms
  + an adjacency table", not one giant tile array.
- **Engineer data shape (fields, not bytes):** per room `room_id`, a tile buffer for
  its screenful of terrain, and an exits table `{dir -> neighbour room_id or NONE,
  exit cell(s)}`. Only the current room's buffer exists; on transition the neighbour
  is built and scrolled in. (The PROTO room descriptor is prototype §8.1.)
- Game logic (combat, AI, turns) operates on "the current room's" entities and tiles.

## F7. Keyboard rationale and input contract (was spectrum-design §3)

The Spectrum has no usable cursor block, so keys are chosen deliberately. **PROTO key
map: prototype §9** (`H/O` left, `L/P` right, `K/Q` up, `J/A` down, `G` quaff,
`Space`/`.` wait, `1 2 3` select, `Enter` confirm). Rationale and contract kept here:

- **`hjkl`** is the canonical roguelike map; the redundant **`QAOP`** cross is the
  classic Spectrum feel for non-genre players (extra key-table entries only).
- **`G` = quaff ("glug")** keeps the only item verb off the movement letters.
- The Rogue `>` glyph needs Symbol-Shift, so descend would be `D` (unbound in PROTO).
- **Input layer:** reads keyboard half-rows directly (`scan_matrix`, `sample_keys`),
  sums held movement keys into `(dx,dy)` with opposite keys cancelling; `(0,0)` = no
  action, no turn. In side-view, chords resolve **vertical-first if a climb is legal,
  else horizontal, never diagonal** (prototype §9).
- **Debounce:** one physical press = one action (edge-detect, wait for release), unless
  hold-to-repeat is enabled (prototype §3.1; test flag `INPUT_REPEAT = 0` restores
  edge-triggered).
- Test injection (`INPUT_SRC` / `KBD_MATRIX`) replaces the matrix read, so ZRCP tests
  are time-independent.

## F8. Sprite data contract (was sideview-renderer §1.2, §1.4, §1.7)

**Masked composite (per screen byte the sprite touches):**

```
screen_byte = (screen_byte AND mask_byte) OR data_byte
```

mask `1` = keep background (transparent), `0` = sprite pixel hole; data = sprite
pixels (set bits), `0` wherever mask is `1`. The sprite shows background through its
outline, so no rectangular box around the figure.

**Byte layout the artist/converter emits (one frame):** row-major, top row first;
within a row, left column first; within a column, **mask byte then data byte**
(interleaved so the blit reads sequentially):

```
frame = H rows x [ col0_mask, col0_data, ... col(W/8-1)_mask, col(W/8-1)_data ]
      = H * (W/8) * 2 bytes
```

- Bit order **MSB = leftmost pixel**. Mask polarity **AND-mask, `1` = transparent**.
- **No pad column, no pre-shifts:** the artist emits the native, right-facing,
  byte-aligned frame; the engine generates shifted copies and left-facing mirrors at
  load (prototype §5.1/§5.2). The engine's shifted copies spill one extra byte column.
- Frame sizes are per-kind and per-frame (prototype §2, §10), `W mod 8 == 0`,
  bottom-anchored with `H <= body height`, plus the per-frame `ax` anchor
  (prototype §5.3). The original spike frame (32x48 = 384 B) is now just one case of
  the formula above.
- **Mask derivation:** filled silhouette (enclosed paper opaque) dilated by a 1-px
  8-neighbour outline (prototype §5.4).

**Colour descriptor: ONE attribute byte per sprite kind**, `ATTR_SPRITE =
FLASH|BRIGHT|PAPER|INK` (Spectrum attribute layout), stamped into every attribute
cell the sprite covers. A 1-bit screen cannot hold per-pixel colour, so colour lives
in this byte, not in the frame data.

- **Hard constraint:** the byte's **PAPER must equal the paper of the colour band the
  sprite stands in**. In PROTO every sprite stands in an air band, so **paper is always
  black** (prototype §2, §4). Stamping then changes only the ink of covered cells.
  The converter takes the band paper as a parameter and **rejects** a descriptor whose
  paper bits disagree.
- Per-cell multi-colour sprites (a block of attribute bytes per frame) remain a
  possible drop-in (same stamp writes, each cell still one paper + one ink) but are
  **not** part of PROTO.

## F9. Colour zoning and attribute-follow (was sideview-renderer §2.2, §2.4)

Two mechanisms, together:

**(A) Colour-band zoning (the coloured backdrop).** The playfield is split into fixed
horizontal bands, one paper colour per band, set at room build and on each transition
redraw (never mid-pixel). Cell-aligned background features carry exactly one
attribute each, so background alone cannot clash. PROTO repeats the two-band idea per
storey (black air bands, coloured floor rows): **prototype §4.1 is the binding
attribute table.**

**(B) Per-cell attribute-follow (the sprite re-tints its footprint).** Each redraw:
1. **restore** the cells of the sprite's previous footprint to the background attr,
2. move the sprite,
3. **stamp** the sprite's attribute byte into the cells of its new footprint,
4. masked-blit the bitmap.

Restore-before-move means the engine never remembers the previous position. In PROTO
the restore value comes from the room tile map (prototype §4.3), and footprints are
exact, not "always one extra column" (prototype §4.2).

**Why it is legal.** The hardware renders exactly one paper + one ink per 8x8 cell,
so "<= 2 colours per cell" always holds. Attribute clash is a *mis-colouring*: a cell
whose single attribute cannot colour a bitmap containing two things that want
different inks. Because every cell the sprite touches is set **whole** to the
sprite's attribute, the sprite and any background pixels sharing the cell render in
one ink. Background-only cells keep their own tile attribute. Hence **no clash by
construction, every frame**, even though attributes change every frame. The
deliberate visible artefact is the classic "colour follows the sprite": background
pixels in covered cells briefly take the sprite's ink, then revert when it leaves.

**Legality checks (what `test` asserts; PROTO set in prototype §4.3/§11.3):**
1. every attribute byte in the playfield is in the finite sanctioned set;
2. cells under the sprite's current footprint equal the sprite attribute (or flash);
3. **no colour trail:** vacated cells equal their tile attribute, not the sprite's.

**Frame budget reference:** the 128K frame is **70,908 T-states** (50.01 Hz; 48K =
69,888). PROTO's tick is 2 frames = 141.8k T (prototype §3.1, §5.5).
Attribute writes are linear (`$5800 + row*32 + col`, `LD (HL),A` 7 T + step ~8 T), so
attribute-follow is cheap next to the masked blit.
