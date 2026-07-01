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
| 0    | —                                 | TBD      |
| 1    | —                                 | TBD      |
| 2    | (also $8000 fixed)                | system   |
| 3    | —                                 | TBD      |
| 4    | —                                 | TBD      |
| 5    | normal screen (also $4000 fixed)  | system   |
| 6    | —                                 | TBD      |
| 7    | shadow screen                     | system   |

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
> Origin `$8000`; code `$8000..$8556`, full image (with assets) `$8000..$8614`
> (1557 B) after SPIKE-2. Throwaway: not slice content.
>
> **SPIKE-2 (byte-shift scroll, 2026-06-29):** the scroll path is now a byte-shift
> (`scroll_view_east`/`scroll_view_west`): shift the visible playfield one
> byte-column in place (bitmap + attrs) then redraw only the newly-exposed column.
> Compile-time flag `USE_NAIVE_SCROLL` (default 0) flips back to the naive
> 768-cell `do_scroll_redraw` baseline for A/B measurement. NO new fixed RAM
> addresses were allocated — the scroll routines reuse screen memory in place and
> the existing `$BF1x` scratch/observable block; `WORLD_BUF`/`VIEW_ORIGIN_COL`
> unchanged. The shift routines clobber `IX` (documented in their headers; the ROM
> ISR preserves it, `IY` stays `$5C3A`).

| Symbol             | Address      | Size   | Notes                                              |
|--------------------|--------------|--------|----------------------------------------------------|
| `PRESHIFT_TABLE`   | `$A000`      | 1152 B | 8 × 144-B pre-shift frames, **boot-generated** from the single S=0 `player` frame (`$A000..$A47F`). Entry `s` = `PRESHIFT_TABLE + s*144`; layout = 24 rows × `[m0,d0,m1,d1,m2,d2]`. |
| `WORLD_BUF`        | `$A500`      | 1536 B | 64×24 tile-id buffer (one byte/cell, row-major; `$A500..$AAFF`) — the wider-than-screen scene scrolled horizontally. |
| `CUR_SC`           | `$BF10`      | 1 B    | scratch: current sprite screen char col            |
| `CUR_DX`           | `$BF11`      | 1 B    | scratch: this frame's dx (`-1`/`0`/`+1`)           |
| `SPRITE_PX`        | `$BF12`      | 2 B    | **test-observable** word (LE): player WORLD pixel X (0..488); `120` at boot |
| `SPRITE_PY`        | `$BF14`      | 1 B    | sprite top pixel Y; constant `120` (char-row 15)   |
| `VIEW_ORIGIN_COL`  | `$BF15`      | 1 B    | **test-observable**: world col shown at screen col 0; `0` at boot |
| `FRAME_COUNTER`    | `$BF16`      | 2 B    | **test-observable** word (LE): per-frame liveness counter |

Spike-only attribute constants (defined in `src/spike_sideview.asm`, not
`constants.asm`): `ATTR_AIR=$05` (cyan/black, rows 0–17), `ATTR_GROUND=$4F`
(white/blue bright, rows 18–23), `ATTR_SPRITE=$46` (= `ATTR_PLAYER`). The clash
legality set asserted by `tests/sideview.py` is exactly `{$05,$4F,$46}`.

> The spike's `$BF1x` vars sit **above** the initial SP (`$BF00`, stack grows
> down) alongside the existing `INPUT_SRC`/`KBD_MATRIX` mirror, so the shallow
> spike call stack never reaches them. `PRESHIFT_TABLE`/`WORLD_BUF` live far below
> at `$A000..$AAFF` (clear of code `≤$8437` and of the `$B100..$BF00` stack run).
