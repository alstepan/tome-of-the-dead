# Memory map (128K) — authoritative

> Ground truth for every fixed address and bank assignment. Update in the same
> change that allocates or moves anything. Code references named constants only;
> this table is where the numbers are decided.

## Address space (paged view)

| Range        | Contents                                   | Notes                         |
|--------------|--------------------------------------------|-------------------------------|
| `$0000-$3FFF`| ROM (48 or 128 editor/BASIC)               | paged via $7FFD bit 4         |
| `$4000-$57FF`| Screen bitmap (bank 5)                      | 6144 bytes                    |
| `$5800-$5AFF`| Screen attributes (bank 5)                  | 768 bytes, the clash grid     |
| `$5B00-$5BFF`| Printer buffer / reusable                   |                               |
| `$5C00-$5CBF`| System variables                            |                               |
| `$5CCB-$7FFF`| Free RAM (after BASIC reclaim)              | program + working storage     |
| `$8000-$BFFF`| Program origin region                       | `ORG $8000` for now           |
| `$C000-$FFFF`| Paged bank window                           | bank selected by $7FFD bits0-2|

## 128K banks ($C000 window)

| Bank | Planned use                       | Status   |
|------|-----------------------------------|----------|
| 0    | PROTO: pre-shift sprite pool      | PROTO    |
| 1    | PROTO: sprite sources (virtual $8000-$BFFF) | PROTO |
| 2    | (also $8000 fixed)                | system   |
| 3    | PROTO: sprite sources (virtual $C000-$FFFF) | PROTO |
| 4    | PROTO: pre-shift sprite pool      | PROTO    |
| 5    | normal screen (also $4000 fixed)  | system   |
| 6    | PROTO: pre-shift sprite pool      | PROTO    |
| 7    | shadow screen / PROTO clean-background copy | system / PROTO |

(main.asm and the spike use no banks beyond 5/2/7; the PROTO column is the
separate `src/proto.asm` build — see the PROTO section below.)

## Paging shadow

| Symbol            | Address | Purpose                                  |
|-------------------|---------|------------------------------------------|
| `PORT_7FFD_SHADOW`| TBD     | last value written to $7FFD (port is WO) |

## Program origin & layout

| Symbol         | Address  | Size       | Notes                                          |
|----------------|----------|------------|------------------------------------------------|
| `start` (ORG)  | `$8000`  | 1228 B     | program origin; `SAVESNA` PC + tape exec entry |
| `map_data`     | `$822E`* | 630 B      | static 30x21 map (DEFB), row-major; ends `$84A4` |
| `tile_glyphs`  | `$84A4`* | 32 B       | 4 terrain glyphs, 8 B each (wall/floor/corr/stairs) |
| `glyph_player` | `$84C4`* | 8 B        | `@` placeholder glyph                            |
| `code_end`     | `$84CC`* | —          | first free byte past emitted code (`CODE_LEN`) |
| Tokenise area  | `$E000`  | scratch    | `tap_loader` BASIC autoloader; NOT saved as CODE |

\* `code_end` is informational — read it from `build/wazhack.lst` after a build;
the program grows from `start` as the engine is built.

## Screen regions (bank 5, fixed window — see constants.asm)

| Symbol            | Address | Size  | Notes                                  |
|-------------------|---------|-------|----------------------------------------|
| `SCREEN_BITMAP`   | `$4000` | 6144  | 256x192 1-bit pixels                   |
| `SCREEN_ATTR`     | `$5800` | 768   | 32x24 attribute cells (the clash grid) |
| `SCREEN_FRAME_LEN`| —       | 6912  | bitmap+attrs; golden-screen hash unit  |

## Engine working storage

> **Constraint:** the state block sits **at/above the initial SP** (`$BF00`) and
> the stack grows **down** from `$BF00`. New working storage is allocated
> upward from `$BF01` (alongside the state block) or by lowering the bottom of
> the stack region — keep both recorded here so they never collide.

| Symbol          | Address       | Size  | Owner  | Notes                                    |
|-----------------|---------------|-------|--------|------------------------------------------|
| `ENTITIES`      | `$B000`       | 256 B | engine | 16-slot entity array (`ENT_STRIDE`=16); slot 0 = player. `$B000..$B0FF` |
| `PLAYER_X`      | `$B001`       | 1 B   | engine | slot-0 `ENT_X`; test-observable          |
| `PLAYER_Y`      | `$B002`       | 1 B   | engine | slot-0 `ENT_Y`; test-observable          |
| `WORKSTORE_TOP` | `$BF00`       | —     | engine | initial SP; stack grows down from here   |
| `GAME_STATE`    | `$BF00`       | 1 B   | engine | game-state enum (`GS_*`); test-observable |
| `RNG_STATE`     | `$BF01`       | 2 B   | engine | xorshift16 state (design §5.6); test-obs. |
| `TURN_COUNTER`  | `$BF03`       | 2 B   | engine | turns elapsed (design §4.1); test-observable |
| `INPUT_SRC`     | `$BF05`       | 1 B   | engine | 0 = scan keyboard; !=0 = freeze mirror (test injection) |
| `KBD_MATRIX`    | `$BF06`       | 8 B   | engine | keyboard half-row mirror `$BF06..$BF0D`; scan order (idx 0=$FEFE … 6=$BFFE 7=$7FFE), active-low |

These are runtime storage declared via `EQU` (no image bytes emitted); `start:`
(via `init_game`) initialises them at boot, so the tape/snapshot stays one clean
CODE block.

> **Stack vs. entities:** the stack grows down from `$BF00`; `ENTITIES` lives far
> below at `$B000..$B0FF`. With code+data ending `$84CC`, the gap `$84CC..$AFFF`
> is free and the stack has the whole `$B100..$BF00` run before it could reach the
> entity array — no collision at the slice's shallow call depth (P3 ≤3 deep + the
> chord-window `halt` ISR pushes). P4's monster loop is a flat 16-slot scan (no
> recursion), so headroom stays ample; revisit only if call depth grows.

## Stable test-observable addresses

_Addresses the `test` skill reads via ZRCP (`tests/smoke.py`). Keep these stable._

| Symbol         | Address | Meaning                                            |
|----------------|---------|----------------------------------------------------|
| `GAME_STATE`   | `$BF00` | byte: game-state enum; `0x02` = `GS_PLAYING` (turn loop) |
| `RNG_STATE`    | `$BF01` | word (LE): RNG state; boot seed `0xA55A`            |
| `TURN_COUNTER` | `$BF03` | word (LE): turns elapsed; `0` at boot               |
| `PLAYER_X`     | `$B001` | byte: player tile column; `1` at boot               |
| `PLAYER_Y`     | `$B002` | byte: player tile row; `5` at boot                  |
| `INPUT_SRC`    | `$BF05` | byte: input source; poke `1` to inject via `KBD_MATRIX` |
| `KBD_MATRIX`   | `$BF06` | 8 B: keyboard half-row mirror (active-low); poke to inject keys |

## Side-view feasibility SPIKE (throwaway — `src/spike_sideview.asm`)

> **Isolated build.** The spike is a SEPARATE program/image assembled on its own
> (`sjasmplus src/spike_sideview.asm --fullpath --lst=build/spike.lst
> --sld=build/spike.sld -i src`) → `build/spike.tap` / `build/spike.sna`
> (`--fullpath` required with `--sld`, else a warning). It does **not** share or
> modify `src/main.asm`, so the P2/P3 `build`/`smoke`/`p3` path is untouched. It
> reuses the shared `constants.asm` EQUs and re-uses (by copy) the P3 input
> primitives + the `INPUT_SRC`/`KBD_MATRIX` injection contract. No `$7FFD` paging.
> Origin `$8000`; full image (with assets) `$8000..$88DE` (2271 B) for the default
> 16×24 build and `$8000..$8D7D` (3454 B) for `-DUSE_HERO_32X48=1` (SPIKE-6: three
> 385-B walk frames instead of one).
> Throwaway: not slice content.
>
> **SPIKE-2 (byte-shift scroll, 2026-06-29):** the scroll path is a byte-shift
> (`scroll_view_east`/`scroll_view_west`): shift the visible playfield one
> byte-column in place (bitmap + attrs) then redraw only the newly-exposed column.
> Compile-time flag `USE_NAIVE_SCROLL` (default 0) flips back to the naive
> 768-cell `do_scroll_redraw` baseline for A/B measurement.
>
> **SPIKE-3 (content-rows-only shift, 2026-07-01):** the default shift height is
> now the 12 non-sky content rows. `shift_bitmap_left/right` shift only char rows
> 12–23 (pixel 96–191, 96 scanlines) and `shift_attr_left/right` shift only the 6
> ground-band rows 18–23; rows 0–11 bitmap (blank sky) and rows 0–17 attrs (uniform
> `ATTR_AIR`) are shift-invariant for this scene, so the result is byte-exact vs the
> full-height path (`tests/scroll.py` 12/12 + `tests/sideview.py` 14/14 stay green;
> west path window-verified over ZRCP). Compile-time flag `SHIFT_CONTENT_ROWS_ONLY`
> (default 1) reverts to the full-height SPIKE-2 path (flag 0) for A/B. **Per 8px
> EAST scroll step ≈ 81.5k T ≈ 1.15 frames** (vs SPIKE-2 146.4k / 2.07 fr; 1.80×);
> west ≈ 84k. The 1-in-4 scroll *frame* additionally erases+reblits the sprite
> (~13.5k T) → worst-case scroll frame ≈ 95k T (~1.34 fr); the 3 glide frames are
> ~13.5k (~0.19 fr). NO new fixed RAM addresses were allocated — the scroll routines
> reuse screen memory in place and the existing `$BF1x` scratch/observable block;
> `WORLD_BUF`/`VIEW_ORIGIN_COL` unchanged. The shift routines clobber `IX`
> (documented in their headers; the ROM ISR preserves it, `IY` stays `$5C3A`).

> **SPIKE-5 (hero sprite size is a build flag, 2026-08-10):** the sprite path
> (pre-shift gen, footprint attr-follow, erase, masked blit) is parameterised by
> `SPRITE_TOP_ROW`/`SPRITE_H_ROWS`/`SPRITE_W_COLS`/`SPRITE_SRC_COLS` and selected
> by `USE_HERO_32X48`:
> * **0 (default)** — legacy 16×24 `assets/gfx/player.asm` (3 cols × 24 rows,
>   144 B/frame), rows 15–17. This is the scene the committed goldens
>   (`tests/golden/sideview_start.hash`) were captured from; artefacts
>   `build/spike.tap`/`.sna`.
> * **1** — design §1.1/§1.4 hero: 32×48 `assets/gfx/wizard_ai_test.asm`
>   (4 data cols × 48 rows = 384 B + 1 descriptor); the engine **boot-generates
>   the 5th spill column** (§1.3), so the in-RAM frame is 5 cols × 48 rows =
>   480 B. Rows 12–17, footprint 5×6 = 30 cells (60 attr writes/frame, the §2.3
>   budget). Built with `-DUSE_HERO_32X48=1` → **separate** artefacts
>   `build/spike_hero.tap`/`.sna`, so it can never shadow the tested build.
>
> The sprite's colour is no longer a hard-coded EQU: `spike_start` copies the
> asset's trailing **colour-descriptor byte** (design §1.7) into `SPRITE_ATTR`
> and the attribute-follow stamps that. `player` → `$46` (bright yellow),
> `wizard_ai_test` → `$45` (bright cyan). The hero build's clash-legality set is
> therefore `{$05, $4F, $45}`.

> **SPIKE-6 (hero walk-cycle animation, 2026-08-10):** the `USE_HERO_32X48=1`
> build now assembles **three** 32×48 walk frames (`wizard_ai_test_f0/f1/f2`,
> 385 B each, all descriptor `$45`) and cycles them while the player is moving
> (`ANIM_PERIOD` = 6 moving frames ≈ 8.3 steps/s at 50 Hz; a full 3-frame cycle
> ≈ 0.36 s). On the moving→idle edge the pose snaps back to frame 0 and the sprite
> is repainted **once** so the screen matches the observable; steady-state idle
> still renders nothing, so at-rest assertions stay deterministic.
>
> **Pre-shift memory tradeoff (the interesting bit).** 3 frames × 8 pre-shifts ×
> 480 B = **11,520 B**, which does *not* fit in one run: only ~6.1 KB is free
> between the (now larger) image and `WORLD_BUF`. Chosen: **(a) find the room** —
> three separate 3840-B tables placed in the two free runs that exist, `$6000`
> and `$7000` inside the documented `$5CCB..$7FFF` free-RAM region, plus `$9400`
> above the image. That region is safe because the spike's BASIC loader does
> `CLEAR 32767` (RAMTOP `$7FFF`) and `spike_start` immediately does `di` +
> `ld sp,WORKSTORE_TOP` and never returns to BASIC, so BASIC's program/stack area
> below `$7FFF` is dead from boot onward. Cost: **0 T on the hot path** — a frame
> change is one SMC pointer patch (`set_anim_frame` → `blit_ptr_base+1`), and the
> per-blit lookup is unchanged. Boot cost: 3 × `gen_preshifts` ≈ 360k T (~5 frames,
> boot only). Rejected alternatives: **(b)** regenerate the active frame's 8
> pre-shifts on every frame change (~120k T = **~1.7 frames of hitch** every 6th
> moving frame — turns a walk into a stutter); **(c)** keep only the 4 *even*
> pre-shifts, exploiting that `SPRITE_PX` is provably even (init 120, `MOVE_STEP`
> 2, clamps 0/472) → 5760 B and one contiguous run, rejected as a correctness
> landmine that breaks silently if `MOVE_STEP` ever becomes odd.
>
> Because the three tables are **not contiguous**, the blit cannot index them by
> arithmetic; each has its own 8-word `preshift_ptrs_fN` table in the image and
> `anim_frame_tabs[i]` maps anim frame → table.
>
> M2 note: this is a spike-scale answer. A real multi-entity, multi-frame roster
> will not fit in low RAM at all and should move pre-shifts into a `$C000` bank
> (design §1.3 already anticipates this), or drop pre-shifting for a runtime
> shift on the cold entities.

| Symbol             | Address      | Size   | Notes                                              |
|--------------------|--------------|--------|----------------------------------------------------|
| `PRESHIFT_TABLE` (16×24) | `$A000` | 1152 B | 8 × 144-B pre-shift frames, **boot-generated** from the single S=0 `player` frame (`$A000..$A47F`). Entry `s` = `PRESHIFT_TABLE + s*144`; layout = 24 rows × `[m0,d0,m1,d1,m2,d2]`. `ANIM_COUNT`=1 → no animation, byte-identical render to pre-SPIKE-6. |
| `PRESHIFT_TABLE` (32×48, anim f0) | `$6000` | 3840 B | `USE_HERO_32X48=1`: 8 × 480-B pre-shifts of walk frame 0 (`$6000..$6EFF`). In the `$5CCB..$7FFF` free-RAM run — safe post-`CLEAR 32767`, see the SPIKE-6 note. Layout = 48 rows × `[m0,d0 … m4,d4]`; col 4 is the boot-generated transparent spill column. |
| `PRESHIFT_TABLE1` (anim f1) | `$7000` | 3840 B | walk frame 1's 8 pre-shifts (`$7000..$7EFF`). |
| `PRESHIFT_TABLE2` (anim f2) | `$9400` | 3840 B | walk frame 2's 8 pre-shifts (`$9400..$A2FF`). Placed at `$9400` (not `$9000`) to leave ~1.6 KB of image-growth headroom above `spike_data_end` (`$8D7D`). |
| `preshift_ptrs_f0/1/2` | in image | 16 B ea. | Per-anim-frame 8-entry word tables of pre-shift addresses (assemble-time constants); `blit_current_sprite` indexes the **currently selected** one by `SPRITE_PX AND 7`. |
| `blit_ptr_base + 1` | in image    | 2 B    | **SMC**: which `preshift_ptrs_fN` the blit uses. Patched by `set_anim_frame` (~60 T) on a frame change only — never per blit. |
| `anim_frame_tabs`  | in image     | 6 B    | anim frame index → `preshift_ptrs_fN` address (2 B stride). Hero build only. |

Layout guards in `src/spike_sideview.asm` fail the build on any collision:
`PRESHIFT_TABLE + PRESHIFT_SIZE <= PRESHIFT_TABLE1`,
`PRESHIFT_TABLE1 + PRESHIFT_SIZE <= $8000`,
`spike_data_end <= PRESHIFT_TABLE2`,
`PRESHIFT_TABLE2 + PRESHIFT_SIZE <= WORLD_BUF`, plus
`spike_data_end - sprite_frame == ANIM_COUNT * ANIM_FRAME_BYTES` and two
assemble-time byte compares that every walk frame's colour descriptor equals
frame 0's (no colour flicker across the cycle).
| `WORLD_BUF`        | `$A500`      | 1536 B | 64×24 tile-id buffer (one byte/cell, row-major; `$A500..$AAFF`) — the wider-than-screen scene scrolled horizontally. |
| `CUR_SC`           | `$BF10`      | 1 B    | scratch: current sprite screen char col            |
| `CUR_DX`           | `$BF11`      | 1 B    | scratch: this frame's dx (`-1`/`0`/`+1`)           |
| `SPRITE_PX`        | `$BF12`      | 2 B    | **test-observable** word (LE): player WORLD pixel X; `120` at boot. Max = `(ORIGIN_MAX + VIEW_COLS − SPRITE_W_COLS)*8` → `488` (16×24) / `472` (32×48), which keeps the rightmost blit column ≤ 31. |
| `SPRITE_PY`        | `$BF14`      | 1 B    | sprite top pixel Y; constant `120` (char-row 15, 16×24) / `96` (char-row 12, 32×48) |
| `VIEW_ORIGIN_COL`  | `$BF15`      | 1 B    | **test-observable**: world col shown at screen col 0; `0` at boot |
| `FRAME_COUNTER`    | `$BF16`      | 2 B    | **test-observable** word (LE): per-frame liveness counter |
| `PORT_7FFD_SHADOW` | `$BF18`      | 1 B    | SPIKE-4: last value written to `$7FFD` (write-only port); bit 3 = displayed buffer |
| `PREP_PHASE`       | `$BF19`      | 1 B    | SPIKE-4: back-buffer prep phase 0..3 within a scroll cycle |
| `PREP_DIR`         | `$BF1A`      | 1 B    | SPIKE-4: cycle scroll direction (`+1` east / `−1` west) |
| `PREP_SRC`         | `$BF1B`      | 2 B    | SPIKE-4: front bitmap scanline address for the next shift-copy chunk |
| `SPRITE_ATTR`      | `$BF1D`      | 1 B    | SPIKE-5, **test-observable**: the sprite colour **descriptor** read at boot from `sprite_frame + SPRITE_SRC_FRAME` (design §1.7). `$46` (player) / `$45` (wizard_ai_test). The attribute-follow stamps this, so the colour follows the asset. |
| `ANIM_FRAME`       | `$BF1E`      | 1 B    | SPIKE-6, **test-observable**: current walk-cycle frame index `0..ANIM_COUNT-1`; `0` = neutral/idle pose. Always `0` in the 16×24 build. |
| `ANIM_TICK`        | `$BF1F`      | 1 B    | SPIKE-6: moving frames since the last advance (`0..ANIM_PERIOD-1`); reset to 0 whenever the player stops, so each walk starts a fresh cadence. |

Spike-only attribute constants (defined in `src/spike_sideview.asm`, not
`constants.asm`): `ATTR_AIR=$05` (cyan/black, rows 0–17), `ATTR_GROUND=$4F`
(white/blue bright, rows 18–23), sprite colour = the asset descriptor in
`SPRITE_ATTR`. The clash legality set asserted by `tests/sideview.py` on the
default build is exactly `{$05,$4F,$46}`; for the `USE_HERO_32X48=1` build it is
`{$05,$4F,$45}` (verified over ZRCP by `tests/hero_anim.py`: 0 illegal cells at
boot, under motion and across the whole walk cycle — all three walk frames carry
descriptor `$45`, ASSERTed at assembly time, so the cycle cannot flicker colour).

> The spike's `$BF1x` vars sit **above** the initial SP (`$BF00`, stack grows
> down) alongside the existing `INPUT_SRC`/`KBD_MATRIX` mirror, so the shallow
> spike call stack never reaches them. `WORLD_BUF` lives far below at
> `$A500..$AAFF`, and the pre-shift tables at `$A000..$A47F` (16×24) or
> `$6000/$7000/$9400` (32×48, SPIKE-6) — all clear of the image (`≤$88DE` /
> `≤$8D7D`) and of the `$B100..$BF00` stack run. The `ASSERT`s at the end of
> `src/spike_sideview.asm` fail the build if any of them ever collides.


## PROTO — first playable prototype (`src/proto.asm`, separate build)

> **Isolated build** (like the spike): `sjasmplus src/proto.asm --fullpath
> --lst=build/proto.lst --sld=build/proto.sld --sym=build/proto.sym -i src` →
> `build/proto.tap` / `build/proto.sna`. Shares only `constants.asm` (read-only);
> main/spike artefacts are byte-unchanged. Spec: `docs/design/prototype.md` rev B.
> Tests read every address below from `build/proto.sym`, never hard-coded.

### Banks & tape

| Bank | Contents | Size | Written by |
|------|----------|------|------------|
| 1 | sprite **sources** part 1 = `assets/gfx/sprites/index.asm` assembled at *virtual* `$8000..$BFFF` (MMU slot 2 = page 1) | 16384 B | tape block 3 / .sna |
| 3 | sprite sources part 2, virtual `$C000..$D082` (MMU slot 3 = page 3) | 4227 B (grows with art; ASSERT total ≤ 32 KB) | tape block 4 / .sna |
| 0, 4, 6 | **pre-shift pool**: every frame variant (facing × shift), boot-generated by a bump allocator (no variant straddles a bank) | need 38,752 of 49,152 B (monsters 22,688 + largest hero 12,608 + select idles + straddle slack; ASSERTed) | `gen_kind` / `gen_frame` at boot and at hero select |
| 7 | **clean-background shadow** (R-1 erase lever): the room's tiles in screen layout, bitmap within `$C000..$D79F` (char rows 0–20 only), attrs `$D800..$DA9F` | 6048 B used | `shadow_rect` / `shadow_room` on room entry + potion pickup |

Sources are read only at generation time via `copy_virt` (virtual < `$C000` →
bank 1 at +`$4000`, else bank 3; a frame straddling `$C000` is split). The pool
and shadow banks are uncontended (0/4/6) resp. contended (7, erase-only).
`PORT_7FFD_SHADOW` always has bit 4 = 1 (48K ROM: IM1 ISR, charset, LD-BYTES).

Tape: BASIC `10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "32768"`,
CODE block `$8000..code_end`, then two **headerless** blocks (flag `$FF`) that
`start` loads into banks 1 and 3 with ROM `LD-BYTES` before falling into `boot`.
The `.sna` enters at `boot` (all banks preloaded).

### Bank 2 (`$8000-$BFFF`)

| Range | Symbol | Contents |
|-------|--------|----------|
| `$8000..$ADFF` | `start`…`code_end` | code + static tables (11,776 B; `ASSERT code_end <= P_ENTITIES`, 512 B headroom). `kind_tab` page-aligned at `$AD00` (13 parallel 16-B kind arrays + MOD7/DIV7 tables). `frame_tab` (8 B/fid, 80 fids). |
| `$B000..$B1FF` | `P_ENTITIES` | 16 slots × **32 B** (layout below); slot 0 = hero |
| `$B200..$B7FF` | `FRT` | frame runtime table: 16 B/fid (4 variants × bank,lo,hi), ≤ 96 fids |
| `$B800..$B8CF` | `SLOTVARS` | per-slot render scratch, 16 B arrays: `N_VIS $B800`, `N_FID $B810`, `N_FPX $B820`, `N_FPY $B830`, `N_ATTR $B840`, `N_DIRTY $B850`, `N_COL..N_ROWS $B860-$B890`, `D_ATTR $B8A0`, `N_LEFT $B8B0`, `N_LOG $B8C0` |
| `$B900..$B9BF` | `DMG_LIST` | per-render damage rects, 4 B each (c0,c1,r0,r1), 48 max |
| `$B9C0..$B9CF` | `PEND_DMG` | queued damage for the next render (4 rects) |
| `$BA00..$BA4F` | `LIVE_LIST` | per-turn collider list, 5 B/entry (slot, ptr, w, h); `LIVE_N $BA50` |
| `$BA60..$BA6F` | `RLIST` | per-tick render list (slots visible or still drawn); `RLIST_N $BA70`, `RL_IDX $BA71` |
| `$BA72..$BA79` | `PL_X/Y/W/H`, `PL_STOREY`, `PL_LADDER`, `MSG_Q`, `BLIT_CROWS` | per-turn hero cache, queued impact message, aligned-blit counter |
| `$BA80..$BAAF` | `SEL_FRT_SAVE` | 3 × 16 B: the select idles' boot FRT rows (`sel_frt_copy` saves at boot, restores on every `enter_select`; a game's `gen_kind` re-points its hero's rows above the alloc mark, which the next hero overwrites) |
| `$BB00..$BEFF` | — | stack (SP = `$BF00`, grows down to `STACK_BOTTOM $BB00`) |
| `$BF00..$BFFF` | state block | below |

**Entity record** (32-B stride, `proto_defs.asm`): `+0 KIND, +1 ROOM, +2 FLAGS
(1 ACTIVE, 2 PLAYER, 4 HOSTILE, 8 FACING_LEFT, 16 DYING, 32 WALKIN, 64 PENDING),
+3 X (body-left col), +4 Y (body-top row), +5 HP, +6 MAXHP, +7 AIDIR (±1 climb
dir), +8 POT (hero potions), +9 PX, +10 PY, +11 MODE, +12/13 SEQ ptr, +14 TMR,
+15 REACT, +16 REACTAT, +17 WPH, +18 FLT, +19 FLA, +20 MSG, +21 TGT, +22 HIT,
+23 ZAP, +24 DVIS (bit0 drawn, bit3 facing), +25 DFID, +26 DFPX, +27 DFPY,
+28..31 drawn footprint col,row,cols,rows`. Hero HP/potions = `$B005`/`$B008`.

### Bank 5 low RAM (`$6000-$7FFF`, free after `CLEAR 24575`)

| Address | Symbol | Size | Contents |
|---------|--------|------|----------|
| `$6000` | `ROOM_MAP` | 672 | current room tile ids, 32×21 (page-aligned) |
| `$6300` | `NEXT_MAP` | 672 | destination room during a transition |
| `$6600` | `BITREV_TAB` | 256 | bit-reverse table (mirroring, boot) |
| `$6700` | `GEN_SRC` | 512 | generator: source frame copied out of bank 1/3 |
| `$6900` | `GEN_MIR` | 512 | generator: mirrored frame |
| `$6B00` | `TILE_GLYPHS` | 256 | 8×8 tile glyphs by id (page-aligned) |
| `$6C00` | `TILE_ATTRS` | 32 | attr by tile id |

### State block (`$BF00..`) — stable test-observable addresses

| Address | Symbol | Meaning |
|---------|--------|---------|
| `$BF00` | `GAME_STATE` | `GS_BOOT 1`, `GS_PLAYING 2`, `GS_WIN 3`, `GS_DEAD 4`, **`GS_SELECT 5`**, **`GS_TRANSITION 6`** |
| `$BF01` | `RNG_STATE` | xorshift16 (7,9,8); reseeded `$A55A` every new game |
| `$BF03` | `TURN_COUNTER` | word; +1 at the end of every turn's animation |
| `$BF05` / `$BF06` | `INPUT_SRC` / `KBD_MATRIX` | P3 injection contract, unchanged |
| `$BF10` | `TURN_PHASE` | 0 INPUT / 1 ANIM |
| `$BF11` | `TICK_COUNTER` | word, 25 Hz ticks |
| `$BF13` | `CUR_ROOM` | 0..3 = A..D |
| `$BF14` | `HERO_KIND` | 0 Knight, 1 Wizard, 2 Rogue |
| `$BF15` | `POTIONS_TAKEN` | bitmask of level potion ids 0..3 |
| `$BF16` | `INPUT_REPEAT` | 1 (default) held keys repeat; poke 0 = edge-triggered |
| `$BF17` | `ANIM_FREEZE` | poke 1: resting sprites hold IDLE frame 0 (goldens) |
| `$BF18` | `PORT_7FFD_SHADOW` | last `$7FFD` value. The ROM's own shadow `BANKM` (`$5B5C`) is deliberately left stale: PROTO never returns to 128 BASIC and never calls 128-ROM paging routines |
| `$BF19` | `OVERRUN_COUNT` | word: ticks whose work exceeded 2 frames |
| `$BF1B` / `$BF20` | `ANIM_TRACE_IDX` / `ANIM_TRACE` | 32-B ring of (slot, frame_id) per drawn-frame change |
| `$BF1C..$BF1F` | `LAST_TICK_FRAME`, `TURN_TICK`, `NEED_RELEASE`, `EXIT_KIND` | loop internals |
| `$BF40` | `BLIT_MISS` | count: stationary frame requested at an ungenerated shift (debug trap, expect 0) |
| `$BF41` | `GEN_OVERFLOW` | 1 if the pre-shift pool ran out (expect 0). An allocation ending exactly at `$10000` opens the next bank for the next one |
| `$BF42..$BF4F` | allocator, zap overlay, damage counts, exit dest/storey/col | internals |
| `$BF55` | `DMG_OVERFLOW` | count: `DMG_LIST` (48) full → last rect = whole playfield, or `PEND_DMG` (4) full → last rect grows to the bounding box (expect 0; was the unused `MSG_DIRTY`) |
| `$BF80` | `CLIP_TRAP` | count: a blit would cross col 31 (not drawn) or a stamp was clamped at col 31 (debug trap, expect 0; was the unused `SEL_KEY`) |
| `$BF51..$BF92` | blit params, generator scratch, `CAND_LIST $BF60`, `CAND_GAP $BF70`, `TMP0..7 $BF83`, `ACT_SLOT $BF8B`, `PLAYER_DIR/DISC`, `ATK_PTR $BF8E`, `MON_SLOT`, `ANIM_SLOT`, `YIELD_FLAG` | internals |
| `$BFA0` | `MSG_BUF` | 32 B spare |

System variable used: `SYS_FRAMES $5C78` (ROM ISR frame counter) paces the 25 Hz
tick; `IY` stays `$5C3A` throughout.

### Test probe labels

`tick_work` (tick work starts), `wait_tick` (tick work done, render complete) and
`select_tick` (after the select-screen HALT) exist so the tests can stop the
emulator at tick boundaries (ZEsarUX cpu-step + breakpoints). `start.lo`
(tape entry past the paging check) and `check_paging.locked` (paging-lock stop)
are probes for `tests/proto.py` #43.

Per-game vs since-boot observables: `new_game` resets `TICK_COUNTER`,
`ANIM_TRACE`/`_IDX`, `BLIT_MISS`, `DMG_OVERFLOW`, `CLIP_TRAP` (plus RNG/turns);
`OVERRUN_COUNT` and `GEN_OVERFLOW` count since boot. Moving them is
free; removing them breaks `tests/proto.py` / `tests/proto_budget.py`.
