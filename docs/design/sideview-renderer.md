# WazHack/ZX — Side-view renderer (FEASIBILITY SPIKE design)

> **REVISED 2026-06-28: colour proven.** Scope change by manager+user — the spike
> must now PROVE COLOUR: a coloured sprite moving over a coloured background with
> attribute clash **actively managed every frame**, not a monochrome playfield.
> Sections changed: **§0** (what the spike proves), **§1.4/§1.7** (sprite data
> contract gains a colour descriptor), **§2** (rewritten: colour-clash strategy for
> a moving sprite), **§3.3** (attributes scroll with the background), **§5**
> (assertions are now *legality*, not *identity*; attribute-write cost added to the
> budget), **§6-§8** (hand-off, banking byte, assumptions). All other decisions
> (16×24 sprite, masked blit, engine-side pre-shift, fine-sprite/coarse-background
> scroll, pixel-coordinate entity model) are **unchanged** — colour does not touch
> the bitmap/blit/scroll path; see §2.1.

> Game-designer deliverable for the **SPIKE — Side-view feasibility spike** phase
> (`docs/plan.md`, IN-PROGRESS). This is the decision-quality spec the
> `graphics-artist` and `z80-staff-engineer` build the throwaway prototype to. It
> is the blocking dependency for the rest of the spike.
>
> **Scope discipline:** this spec covers *only what the spike must PROVE —
> feasibility of the side-view sprite renderer* — not a full game renderer. It is
> deliberately throwaway-tolerant (plan SPIKE bullet). Where M2 would need more,
> it is flagged "M2:" and left out of the spike. Every section states a
> **DECISION** and justifies it in cycles/bytes/clash terms, per the charter. The
> engineer assigns byte addresses in `docs/memory-map.md`; this doc gives formats,
> sizes, and the data contract only.

---

## 0. What the spike proves (one paragraph)

That a **recognizable, masked, side-on adventurer sprite at an arbitrary pixel X**
can be composited **in colour** over a **wider-than-screen, coloured background**
that **scrolls horizontally to follow it**, redrawn every frame with **no trails /
no stale pixels** and with **attribute clash actively managed** — every cell stays
clash-legal (the hardware's 1 paper + 1 ink per cell never mis-colours its bitmap)
as the moving sprite changes which cells it covers and re-tints them **every
frame** — all **within a measurable per-frame budget** on the 128K, handing the
manager a **measured T-state number** (bitmap blit **plus** the per-frame
attribute writes) that says whether the slice's ~8-12 on-screen entities are
renderable per frame.

This is the harder, more WazHack-like case the user asked the spike to prove
(plan "Spike scope decisions", 2026-06-28): a **coloured, moving sprite with
attribute clash managed at runtime**, not the earlier monochrome-uniform
sidestep. The colour cost turns out to be small (§2.3) precisely because
attributes are 1/8 the resolution of pixels and linearly addressed — so proving
colour does **not** materially change the feasibility verdict, only confirms it.

The risk being retired is risk-register row #1 ("Side-view rendering
cost/feasibility — clash, masked pre-shifted sprites, scroll, banking") plus the
2026-06-28 row "Colour under motion (attribute clash with a moving sprite)".

---

## 1. Sprite format & blitting strategy

### 1.1 DECISION — sprite size: **16 × 24 px** (2 cells wide × 3 cells tall)

A 16×24 sprite is the smallest box that reads as a *standing humanoid* (head /
torso / legs) side-on at Spectrum resolution — the spike's whole point is a
**recognizable** adventurer, and 16×16 reads as a squat blob. 24 px = exactly 3
character rows, which (see §1.5) lets us keep the sprite **char-row-aligned
vertically** and pay the pre-shift cost on the X axis only.

- Fallback if blit cost is marginal: drop to **16×16** (2×2 cells). Same data
  contract, 33% fewer rows to blit. The reviewer's measurement decides whether the
  extra row band is affordable; default to 16×24 and let the number argue.

### 1.2 DECISION — masked blit: AND-mask then OR-data, per byte

Compositing rule, applied per screen byte the sprite touches:

```
screen_byte = (screen_byte AND mask_byte) OR data_byte
```

- **mask**: `1` bit = keep background (transparent), `0` bit = sprite pixel hole.
- **data**: sprite pixels (set bits), `0` everywhere the mask is `1`.

This is the standard correct masked composite; it lets the sprite show background
through its outline so there is no rectangular black box around the figure.

### 1.3 DECISION — sub-byte X: **pre-shift all 8 positions** (not shift-at-runtime)

A 16-px sprite placed at an arbitrary X spans **3 byte-columns** once shifted by
1-7 (16 bits shifted into a third byte). The two options:

| Option | Bytes | Cycles per blit |
|---|---|---|
| **Pre-shift 8 (CHOSEN)** | 8 × one frame | ~0 shift cost: pick the pre-shifted copy by `X AND 7`, then a straight masked copy |
| Shift-at-runtime | 1 × one frame | Per blit: rotate a 3-byte span right by `X AND 7`, ×24 rows. Z80 has no multi-bit shift, so worst case ≈ 24 rows × 7 shifts × 3 bytes ≈ **~500 rotate ops just to shift**, dwarfing the copy and paid *every frame the sprite moves* |

On a slow Z80 the runtime shift is the dominant cost and it recurs every motion
frame; the pre-shift trades **bytes (cheap, 128K) for cycles (scarce)**. One
16×24 frame is 144 bytes (§1.4), so 8 pre-shifts = **1152 bytes** — trivial in
main RAM. DECISION: pre-shift 8.

**Who generates the 8 copies — DECISION: engine generates them at boot from one
artist-supplied unshifted frame.** The artist emits exactly **one** frame
(S=0); `init` shifts it into the 8-entry pre-shift table in RAM once at startup.
Rationale: minimises the artist data contract to a single frame, emits no
pre-shifted image bytes into the tape, and the boot-time shift is a one-off cost
off the hot path. (M2: an offline `tools/` step emits all 8 pre-shifts straight
into a `$C000` bank instead, when many sprites/frames make boot-gen too slow.)

### 1.4 DECISION — byte layout the artist emits (DATA CONTRACT)

The sprite occupies a **uniform 3-byte-column span** at every pre-shift (the
unshifted S=0 frame pads its third column to transparent: mask `$FF`, data `$00`),
so one blit routine serves all 8 shifts.

Per frame, **row-major, top row first; within a row, left column first; within a
column, mask byte then data byte** (interleaved so the blit reads them
sequentially as it walks the screen):

```
frame = 24 rows × [ col0_mask, col0_data, col1_mask, col1_data, col2_mask, col2_data ]
      = 24 × 6  = 144 bytes
```

- Bit order: **MSB = leftmost pixel** (matches the existing tileset, `main.asm`
  `tile_glyphs`).
- Mask polarity: **AND-mask, `1` = transparent** (§1.2).
- The artist/converter delivers **one** 144-byte frame (the S=0, char-aligned
  figure) **+ one colour descriptor byte** (§1.7), plus its human-readable 16×24
  pixel + mask source. **= 145 bytes.** No pre-shifts, no animation frames. The
  sprite shape stays 1-bit + mask; **colour is carried in the single descriptor
  byte, not per pixel** (a 1-bit screen cannot hold per-pixel colour) — the
  renderer stamps that descriptor into the attribute cells the sprite covers (§2).

> Artist hand-off in one line: *"One side-on adventurer, 16×24, 1-bit + 1-bit
> mask, emitted as 24 rows of `[mask,data]×3` (MSB-left, mask 1=transparent),
> third column padded transparent, 144 bytes; then 1 colour-descriptor byte
> (§1.7). 145 bytes total."*

### 1.7 DECISION — sprite colour descriptor: **ONE attribute byte** (REVISED 2026-06-28)

The sprite carries its colour as a **single Spectrum attribute byte**
`ATTR_SPRITE = FLASH|BRIGHT|PAPER|INK` (same bit layout as `constants.asm`), which
the renderer stamps into every attribute cell the sprite currently covers (§2.3).

Why one uniform byte and **not** a per-cell attribute block (a 3×3 = 9-byte map):

- The spike's clash problem is the **moving footprint**, not per-cell colour
  richness — and the footprint write set / cost is *identical* whether the
  renderer stamps 1 repeated byte or 9 distinct bytes (§2.3). One byte proves
  colour-under-motion with the minimal, most clash-checkable contract.
- **Hard constraint on the byte's PAPER bits:** `ATTR_SPRITE` paper **must equal
  the paper of the colour band the sprite stands in** (§2.2). Because paper then
  matches the background, stamping the descriptor changes only the **ink** of the
  cells it covers, so empty (all-paper) footprint cells are visually unchanged and
  the colour artefact is confined to cells that actually contain pixels. The
  converter takes the band paper as a parameter and **must reject** a descriptor
  whose paper bits disagree (`gfx_assess.py` flags it).
- Spike value: `ATTR_SPRITE = $46` (PAPER black, INK yellow, BRIGHT) — this is the
  existing `ATTR_PLAYER` constant; reuse it.

> **M2 (flagged, not built):** a per-cell 3×3 attribute block lets the sprite be
> multi-coloured (e.g. yellow torso / white legs). It is a drop-in: same 9 stamp
> writes, the converter emits 9 bytes instead of 1, each still one paper+ink so
> still clash-legal by construction. Out of spike scope.

### 1.5 DECISION — vertical alignment: **sprite Y is char-row-aligned (floor line)**

The sprite stands on the floor at a fixed Y that is a multiple of 8, so it spans
**exactly 3 char rows** with no vertical sub-cell and **no vertical pre-shift**.
Justification: the horizontal axis is the scroll/sub-pixel axis under test;
vertical sub-pixel adds cost and band-colour complications (§2) while adding
nothing to the feasibility question. The blit therefore touches a fixed
**3 byte-columns × 24 rows** region. (M2: sub-pixel Y for jumps/elevation reuses
the same pre-shift technique on the Y axis or accepts 8px Y steps.)

### 1.6 DECISION — erase / no-trails: **redraw background tiles under the sprite**

Before blitting the sprite at its new position, redraw the background tiles under
the sprite's **previous** bounding box (up to 3 char-cols × 3 char-rows) from the
world tile buffer (§3) via the existing `draw_cell`. This is the simplest robust
no-trails method and reuses proven code. (M2: save-under/restore-under is faster
once profiled; note it, don't build it.)

---

## 2. Colour clash under a MOVING sprite — THE Spectrum side-view problem (REVISED 2026-06-28)

### 2.1 What changed from the monochrome version, and what did not

The earlier spec sidestepped clash: uniform attributes set at init, **never**
rewritten, so a moving sprite touched zero attribute bytes and clash was
impossible by construction — but the playfield was monochrome (one ink for sprite
+ background). The manager+user rejected that scope: the spike must prove the
**harder, defining** case — a coloured sprite moving over coloured background with
**clash managed at runtime**. So §2 is rewritten.

What does **not** change: the bitmap path. Pixels are 1-bit regardless of colour;
the 16×24 size, masked `(scr AND mask) OR data` blit, engine-side pre-shift, the
erase-under, and the scroll model are all colour-agnostic. Colour is **purely an
attribute-plane concern**, handled by a small extra per-frame routine (§2.3) that
runs alongside — never inside — the blit. That separation is why proving colour
costs little and changes no earlier decision.

### 2.2 DECISION — colour-band zoning + per-cell attribute-follow (combination)

Two mechanisms, together:

**(A) Colour-band zoning (the coloured backdrop, set once).** The playfield is
split into fixed horizontal bands, one paper colour per band, set at init and on
each scroll-step redraw (never mid-pixel). Concrete spike layout:

| Band | Char rows | PAPER | INK (background features) | Attr value |
|---|---|---|---|---|
| Air / sky | 0–17 | black | cyan (pillars, doorway) | `ATTR_AIR = $05` |
| Ground | 18–23 | blue | white (floor texture) | `ATTR_GROUND = $4F` |

This alone is genuine colour (cyan pillars on black sky over a blue floor) and
**cannot clash**: each background cell is cell-aligned and carries exactly one
attribute.

**(B) Per-cell attribute-follow (the moving sprite re-tints its footprint).** The
sprite occupies **char rows 15–17** (its 24 px = 3 cells, feet resting on the
ground band top at row 18), so its whole vertical footprint sits **inside the air
band** → single paper (black) across the footprint. Each frame the renderer:

1. **restores** the cells of its *current* footprint to the band attribute
   (`ATTR_AIR`), then
2. moves the sprite (and maybe scrolls), then
3. **stamps** `ATTR_SPRITE = $46` (black paper, **yellow** ink, bright) into the
   cells of its *new* footprint, then
4. masked-blits the sprite bitmap.

Restore-**before**-move means the engine never has to remember the previous
position. Because `ATTR_SPRITE` paper (black) == `ATTR_AIR` paper (black), the
stamp changes only the **ink** of covered cells: the yellow sprite reads on the
black sky, and any cyan background pixel inside a covered cell (e.g. a pillar the
sprite is passing) momentarily renders **yellow**, reverting to cyan the moment the
sprite leaves. Empty (all-paper) footprint cells are visually unchanged — the
colour artefact is confined to cells that actually hold background pixels.

This is the classic, deliberate ZX "**colour follows the sprite**" look — the
faithful WazHack-on-Spectrum compromise, and exactly the clash-under-motion case
the user wanted proven.

### 2.3 The footprint write/restore set and its EXACT per-frame cost

- **Footprint = a fixed 3 cols × 3 rows = 9 cells**, stamped every frame
  regardless of `X AND 7`. When the sprite is byte-aligned it really covers only
  2 cols; the spike still stamps the third (right-margin) column because, with
  paper == band paper, stamping an empty cell is **invisible** — so the routine is
  **branch-free** (no aligned/unaligned special-case).
- **Restore set = the same 9 cells**, all written back to the single constant
  `ATTR_AIR` (legal because all three footprint rows are air). The sprite stays in
  one band, so restore needs no per-row table.
- **Writes/frame = 9 restore + 9 stamp = 18 attribute-byte writes.**

**Cost.** Attribute addresses are linear: `$5800 + row*32 + col`; `INC HL` steps a
column, `+32` steps a row. Estimate: setup ~60 T + 18 × (`LD (HL),A` 7 T + step
~8 T) ≈ **~330 T-states/frame, bounded < 400 T**. That is **< 0.6 % of the 70,908
T-state frame** and roughly an order of magnitude cheaper than the 24-row masked
blit. For N sprites it scales ~330 T × N (≈ 3,300 T at N = 10) — still trivial.

**KEY RESULT for the verdict:** managing colour clash under motion is nearly free
on top of the bitmap renderer, because the attribute plane is 1/8 the resolution
of the pixel plane and linearly addressed. Proving colour therefore does not move
the feasibility needle — it only confirms it. The reviewer must still *measure*
this and add it to the per-sprite frame cost (§5.4).

### 2.4 The clash guarantee — why every cell is always legal

The Spectrum hardware renders **exactly one paper + one ink per 8×8 cell** — so
"≤ 2 colours per cell" is *always* physically true; it can never be violated. The
"attribute clash" artefact is a **mis-colouring**: a cell whose single attribute
cannot correctly colour a bitmap that contains two things wanting different inks.
Our construction removes that: every cell the sprite touches is forced **whole** to
`ATTR_SPRITE`, so the sprite and any background pixels sharing the cell all render
in one ink — nothing in the cell wants a colour it doesn't have. Background-only
cells carry their cell-aligned band/feature attribute. Therefore **no clash, by
construction, every frame — even though attributes change every frame.**

### 2.5 What the reviewer screen-checks (LEGALITY, not identity)

The old check "`$5800-$5AFF` byte-identical to the init snapshot" is now **wrong** —
attributes legitimately change every frame. Replace it with:

1. **Sanctioned-value check (clash-legality proxy):** every byte in `$5800-$5AFF`
   is in the known finite set `{ATTR_AIR, ATTR_GROUND, ATTR_SPRITE, ATTR_FEATURE?}`.
   No garbage/stale value appears. (Each such value is itself one paper+one ink, so
   this guarantees no mis-coloured cell — see §2.4.)
2. **Footprint is coloured:** the ≤9 cells under the sprite's *current*
   `SPRITE_PX/SPRITE_PY` equal `ATTR_SPRITE`. Proves colour is stamped under
   motion.
3. **No colour trail:** cells the sprite covered N frames ago but no longer covers
   equal their band attribute (`ATTR_AIR`), **not** `ATTR_SPRITE`. This is the
   colour counterpart of the no-pixel-trails check and the single most important
   colour assertion.

### 2.6 Why this over the pure alternatives

- **Pure colour-band zoning, zero attribute writes** (sprite ink fixed to read on
  one band, never re-tint cells): cheapest, but the sprite ink would have to be a
  *background* ink to avoid ever changing a cell — i.e. it is monochrome-in-disguise
  and does **not** prove clash management. Rejected as evidence; folded in only as
  mechanism (A), the backdrop.
- **Background-only-on-cell-boundaries** (2 colours/cell hold without sprite
  writes): works for static background but says nothing about a *moving* sprite,
  which is the risk. Adopted as a backdrop property (features are cell-aligned),
  not as the answer.
- **Per-cell attribute-follow (B)** is the only one that actually exercises
  runtime clash management — and it is cheap (§2.3) — so it is the spike's core,
  with (A) as its cheap, legal backdrop.

---

## 3. Scroll model

### 3.1 DECISION — horizontal only; **vertical OUT for the spike**

One scroll axis fully exercises the cost/feasibility question (no-hardware-scroll
redraw, sub-pixel sprite over a moving background). A second axis multiplies cost
and reintroduces band-colour problems for no extra feasibility information.
Recommend OUT. (M2: vertical is a separate decision; the techniques extend.)

### 3.2 DECISION — **fine sprite, coarse background**: pixel-granular sprite motion + cell-granular (8px) viewport scroll, follow-with-dead-zone

The Spectrum has **no hardware scroll**; full smooth pixel-scroll of a 6144-byte
screen is multi-frame on a Z80. So the spike splits the two motions to get an
honest, useful measurement of each:

- **Sprite motion = pixel-granular** (e.g. **2 px/frame** while a direction key is
  held). This is what exercises the #1 risk: all 8 pre-shifts (`X AND 7` cycles
  through 0,2,4,6,...), the masked blit, and the no-trails erase. The sprite moves
  **within a central dead zone** (e.g. viewport char-columns 12-19).
- **Background scroll = cell-granular (8 px / 1 char column)**, triggered only
  when the sprite would leave the dead zone: the sprite is clamped at the margin
  and the **world origin advances by 1 cell**, then the visible window is redrawn
  from the world tile buffer.

This is legitimate scrolling (many Spectrum games scroll 8px/step) and it yields
**two separate cost numbers** for the reviewer — frequent cheap sprite redraws and
occasional background redraws — instead of one muddy figure. Smooth *pixel*-scroll
of the background is explicitly deferred to M2 with the spike's numbers informing
that decision.

### 3.3 DECISION — world vs viewport sizes

- **World (background) = 64 char-cols × 24 char-rows tile buffer** = 1536 bytes,
  one tile id per cell (same model as the top-down `map_data`). 64 cols (512 px) =
  2× the 32-col viewport → enough travel to scroll meaningfully and to assert a
  feature has moved.
- **Viewport = full 32 × 24** char grid (the spike has no status/message UI; it is
  not slice content).
- **Background redraw on scroll = redraw the 32 visible columns from the world
  buffer** via `draw_cell` (simplest, most measurable). The reviewer measures this
  cost; if it is too slow the M2 follow-up is byte-shift + draw-exposed-column, but
  the spike does the simple thing and *reports the number*.
- **Attributes scroll with the background (colour knock-on).** On the same
  scroll-step redraw, the renderer rewrites the **32×24 attribute cells** for the
  visible window. No separate "world attribute buffer" is needed: a background
  cell's attribute is a pure function of **(row → band)** overridden by
  **(tile-id → feature attr)** — so `draw_cell` writes `band[row]` for that cell,
  or the feature attr if the tile is a feature. This adds **768 attribute writes
  per scroll step** (occasional, amortised) — a separate cost line the reviewer
  records (§5.4). Between scroll steps (the common case: pixel-granular sprite
  motion inside the dead zone) attributes are touched **only** by the 18-write
  footprint follow (§2.3).

### 3.4 DECISION — frame pacing: per-frame loop synced to `HALT`

The spike runs a **per-frame render loop** (sync to the 50 Hz interrupt via
`HALT`), each frame: sample held keys → move sprite/scroll → erase → blit. This
diverges from P3's blocking one-keypress-one-turn `get_action` **deliberately** —
the turn loop is renderer-agnostic and is *not* what the spike tests; smooth
scrolling needs continuous motion. It **reuses the existing input primitives**
(`scan_matrix`, `sample_keys`, `dirs_to_step`) so "existing input" still drives it
(plan exit gate 2). Per-step (one keypress = 8px, reusing `get_action`) is an
acceptable fallback if the per-frame loop proves troublesome, but per-frame gives
the stronger "redraw fits in a frame" evidence.

---

## 4. Pixel-coordinate entity model

The current record (`constants.asm`) carries **tile** coords `ENT_X`/`ENT_Y`
(bytes). Side-view needs a **pixel** X. Minimal spike extension, reusing the
existing 16-byte slot-0 layout (the spike touches only the player):

| Field | Width | Meaning | Reuse |
|---|---|---|---|
| `ENT_PX` | **u16** | player **world** pixel X, 0..511 (world is 512 px) | repurpose the spare player-only bytes `ENT_GOLD` (offset 12-13) for the throwaway spike |
| `ENT_PY` | u8 | sprite top pixel Y; **fixed to the floor band**, char-aligned (§1.5) | repurpose `ENT_XP` (offset 14); may be a constant |

Derived each frame (no stored fields needed):
- pre-shift index = `ENT_PX AND 7`
- world char column = `ENT_PX >> 3`
- screen char column = `(ENT_PX >> 3) − VIEW_ORIGIN_COL`

`VIEW_ORIGIN_COL` (world column at screen col 0) is engine state, not a per-entity
field — a single test-observable byte (§5.3).

**Do not grow `ENT_STRIDE` for the spike** — repurposing slot-0 spare bytes keeps
the array layout and all P3 code untouched, and the spike is throwaway.

> **M2 needs (out of spike):** *every* entity (not just player) needs a 16-bit
> pixel X, a **facing** bit (sprite mirror left/right), and an **animation frame
> index**; 16-bit X for 16 entities + facing + frame likely overflows the 16-byte
> stride → M2 either grows the stride or moves render-coords to a parallel array.
> Flag for M2 design; not the spike's concern.

---

## 5. What the spike must demonstrate + how it's checked

### 5.1 Scene spec (engineer implements)

1. **Background (coloured)**: a side-view world, 64×24 tile buffer — a continuous
   **floor line** along the ground band (rows 18–23), a back feature set the eye
   can track while scrolling (a few **cyan pillars / a doorway** at known world
   columns), the rest blank sky. Two colour bands per §2.2: **air** (`ATTR_AIR`,
   black paper / cyan ink, rows 0–17) over **ground** (`ATTR_GROUND`, blue paper /
   white ink, rows 18–23). Attributes set at init and rewritten on each scroll step
   (§3.3).
2. **Player sprite (coloured)**: the 16×24 masked adventurer (§1) at char rows
   15–17, **bright yellow** (`ATTR_SPRITE = $46`) on the black sky, standing on the
   ground band, initially in the viewport's central dead zone.
3. **Motion**: hold West/East (existing `H`/`L` or `O`/`P`) → sprite moves
   ±2px/frame within the dead zone; at the margin the world origin advances 1 cell
   and the background redraws (§3). Redraw leaves **no pixel trails** (mask + erase
   correct) and **no colour trails** — every frame the footprint cells become
   `ATTR_SPRITE` and vacated cells revert to `ATTR_AIR`, all cells staying
   clash-legal (§2.5). As the sprite passes a cyan pillar, the pillar's covered
   cells visibly flash yellow then revert — the intended "colour follows sprite".

### 5.2 ZRCP / screen-memory assertions (test harness reads `$4000`, 6912 bytes)

| # | Check | How asserted |
|---|---|---|
| 1 | **Sprite is on screen** | Bitmap bytes at the sprite's known initial 3-col × 24-row region match the known composited signature (sprite-over-floor); non-blank where the figure is. |
| 2 | **No trails after motion** | Move East several frames, then read the bitmap at the **vacated** cells: they equal the pure **background** pattern from the world buffer (sprite fully erased — proves the mask + erase). The single most important check. |
| 3 | **Sub-byte X path runs** | After a 2px move, `ENT_PX AND 7` is non-zero (2,4,6,…); read `ENT_PX`. Confirms pre-shifted blits (not just the S=0 copy) are exercised. |
| 4 | **Viewport scrolled** | After crossing the dead zone, `VIEW_ORIGIN_COL` has changed **and** a known background feature's bitmap has moved by 8px (sample two columns). |
| 5a | **Clash-legal (sanctioned values)** | Every byte in `$5800-$5AFF` ∈ `{ATTR_AIR=$05, ATTR_GROUND=$4F, ATTR_SPRITE=$46, (ATTR_FEATURE?)}` on every motion/scroll frame. Each value is one paper+ink, so no cell is mis-coloured (§2.4). Replaces the old "byte-identical" check — **legality, not identity**. |
| 5b | **Footprint coloured under motion** | The ≤9 attribute cells under the sprite's current `SPRITE_PX/SPRITE_PY` equal `ATTR_SPRITE=$46`. Proves colour is stamped as the sprite moves. |
| 5c | **No colour trail** | After moving East several frames, the cells vacated by the sprite equal `ATTR_AIR=$05`, **not** `ATTR_SPRITE`. The colour counterpart of check 2 (no pixel trails). |
| 6 | **No softlock / loop alive** | A test-observable frame counter advances while input is injected; the loop never wedges. |

All assertions use **fixed seed / scripted injected input** (reuse the P3
`INPUT_SRC`/`KBD_MATRIX` injection path) so results are deterministic and
golden-able. A golden of the init frame (bitmap + attr) and of a
known-after-N-frames frame are committed for the spike scene.

### 5.3 Test-observable named addresses the engineer must expose

(Engineer assigns real addresses in `docs/memory-map.md`; names are the contract.)

- `SPRITE_PX` — player world pixel X (u16) = slot-0 `ENT_PX`.
- `VIEW_ORIGIN_COL` — world char column shown at screen col 0 (byte or u16).
- `FRAME_COUNTER` — increments per render frame (liveness / pacing).
- (`SPRITE_PY` if not a constant.)

### 5.4 Measurements the reviewer must record (the actual spike deliverable)

| Measurement | Why |
|---|---|
| **Per-frame sprite redraw cost** = erase-under + masked blit, in **T-states** | The hot cost; recurs every motion frame |
| **Per-frame attribute-follow cost** = 18-write restore+stamp (§2.3), in **T-states** | The colour cost; recurs every motion frame. Add it to the sprite redraw cost — the per-sprite frame budget is now blit **+** attr-follow. Designer estimate ~330 T (< 400 T); confirm the real number. |
| **Per-scroll-step background redraw cost** in T-states | Occasional. **Report bitmap redraw and the 768-cell attribute rewrite (§3.3) separately** — colour adds the attribute pass to the scroll step. |
| **Single-sprite cost (blit + attr-follow) extrapolated to N sprites** | Verdict input; ~8-12 sprites |
| **Flicker/tearing severity** (single screen, no double-buffer) | Informs the M2 shadow-screen decision |

**Frame budget reference:** 128K = **70,908 T-states/frame** (50.01 Hz; 48K =
69,888). Feasibility rule of thumb the reviewer applies: leave roughly **half the
frame** (~35k T) for game logic + scroll + input, so the sprite-blit budget is
~35k T. **Target entity count for the verdict: ~8-12 on-screen sprites** (the
slice spawns 6-10 monsters + player, design §4.4). So the verdict question is:
*does (one-sprite redraw × ~10) + a scroll step amortised fit a frame?* If not,
the fallbacks are: 16×16 sprites (§1.1), fewer simultaneous sprites, per-step
(8px) motion instead of per-frame, or a coarser redraw region.

---

## 6. Banking note

### 6.1 Spike: **no `$C000` paged banks needed**

Everything fits in main RAM below `$C000`:

- pre-shift table: 8 × 144 = **1152 B** (or 144 B source + boot-gen, §1.3)
- sprite colour descriptor: **1 B** (`ATTR_SPRITE`, §1.7)
- world tile buffer: 64 × 24 = **1536 B**
- background tileset: a handful of 8×8 glyphs ≈ **64-128 B**
- background attributes: **0 B stored** — derived from (row→band) + (tile-id→
  feature attr) at redraw (§3.3); band attr constants only (`ATTR_AIR`,
  `ATTR_GROUND`, …), a few bytes.

Total < ~3 KB. The spike runs on the single normal screen (bank 5) with no paging.
State explicitly: **the spike does not touch `$7FFD`.**

### 6.2 M2 (flagged, not built in the spike)

- **Sprite assets**: 3 monster kinds + player × a few animation frames × 8
  pre-shifts × ~144 B reaches tens of KB → M2 puts sprite/mask data in `$C000`
  banks, with a documented bank-switch (and its T-state cost) around the blit, via
  the `PORT_7FFD_SHADOW` discipline (`docs/conventions.md` Banking).
- **Double buffering**: per-frame full redraw on the single live screen will
  flicker/tear; M2 will likely render to the **shadow screen (bank 7)** and flip.
  The spike skips this (records flicker severity instead, §5.4) so the M2
  shadow-screen decision is made on evidence.

---

## 7. Hand-off summary

- **Artist + converter** build: `tools/gfx_convert.py` (image/text → clash-checked
  masked Z80 DEFB + round-trip) and `tools/gfx_assess.py` (silhouette IoU, SSIM,
  clash, render-back), producing **one 16×24** side-on adventurer through the
  autonomous Ollama pipeline. Emit **24 rows of `[mask,data] × 3 columns`**
  (MSB=left pixel, mask `1`=transparent, third column padded transparent) = **144
  B**, **followed by 1 colour-descriptor byte** `ATTR_SPRITE` (§1.7) = **145 B
  total**. Constraint the converter validates: `ATTR_SPRITE` **paper bits must
  equal the band paper** the sprite stands in (air = black) — assess flags a
  mismatch. Also a small background tileset (floor / cyan pillar / doorway / blank,
  8×8 each). No pre-shifts, no animation. (Per-cell 3×3 attr block is M2.)
- **Engineer** builds: boot-time pre-shift gen (8 copies); a 64×24 world tile
  buffer; a per-frame loop (HALT-synced) reusing `scan_matrix`/`sample_keys`/
  `dirs_to_step`; pixel-granular sprite motion with dead-zone follow + cell-granular
  background redraw; masked blit `(scr AND mask) OR data`; erase-under via
  `draw_cell`. **Colour:** init the two colour bands (`ATTR_AIR`/`ATTR_GROUND`);
  each frame **restore (9 cells → `ATTR_AIR`) → move → stamp (9 cells →
  `ATTR_SPRITE`) → blit** (§2.2-2.3); on scroll, rewrite the 32×24 visible
  attributes from (row→band)+(tile-id→feature) (§3.3). Expose `SPRITE_PX`,
  `SPRITE_PY`, `VIEW_ORIGIN_COL`, `FRAME_COUNTER`. Throwaway source path OK. No
  `$7FFD`.
- **Reviewer** records: per-frame **sprite redraw + attribute-follow** T-states
  (the colour cost is now part of the per-sprite budget, ~330 T est.),
  per-scroll-step T-states (bitmap redraw **and** the 768-cell attribute pass,
  separately), extrapolation to ~8-12 sprites against ~70,908 T/frame, flicker
  severity; and **screen-checks clash *legality* not identity** (§2.5: sanctioned
  attr value set, footprint coloured, no colour trail) → **feasibility verdict**
  for the manager + user re-decision.

---

## 8. Assumptions to confirm before artist/engineer start

1. **Colour scheme (REVISED — colour now in scope).** The spike proves colour via
   §2: two fixed bands (air = black paper/cyan ink rows 0-17; ground = blue
   paper/white ink rows 18-23), a **bright-yellow** sprite (`ATTR_SPRITE=$46`) kept
   **within the air band** (rows 15-17) so its paper matches the band, and a
   per-frame 9-cell restore/stamp attribute-follow. Confirm: (a) "colour follows
   the sprite" — background pixels in covered cells briefly take the sprite ink — is
   the accepted look (it is the standard ZX compromise; the alternative, true
   per-pixel colour, is impossible on this hardware); (b) the **single uniform
   sprite attribute byte** (not a per-cell block) is sufficient colour proof for
   the spike (per-cell is a cheap M2 drop-in, §1.7); (c) keeping the sprite inside
   one band (no air/ground straddle) is acceptable for the spike — straddling needs
   a per-row restore table, deferred to M2.
2. **Fine sprite + coarse (8px) background scroll**, not smooth pixel-scroll of the
   background. This gives honest separate cost numbers and keeps the spike small;
   smooth background pixel-scroll stays an M2 question informed by the spike's
   measurement. Confirm 8px-step background scrolling is acceptable to *prove
   feasibility* (it need not be the final look).
3. **Per-frame (real-time) loop reusing the input primitives**, diverging from the
   turn loop for the spike only. Confirm this is acceptable (the alternative,
   per-keypress 8px steps, is weaker evidence but stays inside the turn model).
4. **16×24 sprite** (vs 16×16). I default to 16×24 for recognizability and let the
   reviewer's number decide a fall-back to 16×16. Confirm or pin a size.
5. **Vertical scroll OUT, sprite Y char-aligned.** Confirm vertical is out of the
   spike.

None of these block the artist's single-frame deliverable (it is the same
regardless); they shape the engineer's loop. Confirm 1-3 before the engineer
starts.
