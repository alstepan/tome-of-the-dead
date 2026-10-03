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
| 1    | PROTO: sprite sources (virtual $8000-$BFFF), ZX0-packed since A5: 6,947 of 16,384 B (A6) | PROTO |
| 2    | (also $8000 fixed)                | system   |
| 3    | PROTO: sprite sources tail (virtual $C000-; empty since A5) + **cold code** (select, transition scrolls, new game, follower selection); **`$E400-$FFFF` AY player slot** (A8, 7 KB: silent stub today, called by the IM 2 ISR) | PROTO |
| 4    | PROTO: pre-shift sprite pool      | PROTO    |
| 5    | normal screen (also $4000 fixed); low RAM `$6000-$7FFF` buffers + **cold code** (boot, generator) + frame descriptors (A6) | system   |
| 6    | PROTO: pre-shift sprite pool      | PROTO    |
| 7    | **displayed screen during play** (screen 2, `$C000-$DAFF`, A7 double buffer) + PROTO clean-background copy (`$E000-$FA9F`) + (B3B-1, reserved) **8 level tilesets** `$DB00-$DF7F` / `$FAA0-$FF1F` | system / PROTO |

(Bank assignments are those of `src/main.asm` — see the PROTO section below.)

## Paging shadow

| Symbol            | Address | Purpose                                  |
|-------------------|---------|------------------------------------------|
| `PORT_7FFD_SHADOW`| `$BF18` | last value written to $7FFD (port is WO) |

**`$7FFD` rules (A7).** Every write goes through the shadow, shadow first,
then the `OUT`. Bit 4 = 1 always (48K ROM: charset, `LD-BYTES`, the optional
`ISR_ROM_CHAIN` handler); bit 5 (lock) never. **Bit 3 = displayed screen**: 0 = bank 5 (`$4000`) at boot, on
the select screen and during the transition scrolls; 1 = bank 7 (screen 2)
during play. Only `set_screen` / `show_bank5` / `present_full` (bank-5 low
RAM) change it; they patch it into `page_bank`'s `OR` operand (SMC
`page_bank.scr+1`), so `page_bank` keeps the screen bit at no extra cost, and
`restore_page` takes only bits 0-2 of a saved shadow value (far3 /
blit_keep never roll the screen bit back). **A8:** the IM 2 ISR pages
`BANK_AY` by `OUT` only (`(shadow & ~7) | 3`) and afterwards re-OUTs the
shadow as it finds it; it never writes the shadow, so the shadow-first order
makes every interleaving safe without `DI` (see "Interrupts (A8)").

## Screen regions (bank 5, fixed window — see constants.asm)

| Symbol            | Address | Size  | Notes                                  |
|-------------------|---------|-------|----------------------------------------|
| `SCREEN_BITMAP`   | `$4000` | 6144  | 256x192 1-bit pixels                   |
| `SCREEN_ATTR`     | `$5800` | 768   | 32x24 attribute cells (the clash grid) |
| `SCREEN_FRAME_LEN`| —       | 6912  | bitmap+attrs; golden-screen hash unit  |

## PROTO — first playable prototype (`src/main.asm`)

> Build: `tools/build.sh` (A6, the single entry point: `tools/zx0_sources.py`,
> then `sjasmplus src/main.asm --fullpath --lst=build/wazhack.lst
> --sld=build/wazhack.sld --sym=build/wazhack.sym -i src`; fails on warnings;
> `-o DIR` / extra `-D` args for tests) → `build/wazhack.tap` / `build/wazhack.sna`. Includes `constants.asm` (read-only). Spec: `docs/design/prototype.md` rev B.
> Tests read every address below from `build/wazhack.sym`, never hard-coded.

### Banks & tape

| Bank | Contents | Size | Written by |
|------|----------|------|------------|
| 1 | sprite **sources** at *virtual* `$8000..` (MMU slot 2 = page 1): `ZX0_SOURCES=1` (default) = `build/zx0/sprites_zx0.asm` (see "Sprite sources (ZX0)" below); `=0` = the raw `assets/gfx/sprites/index.asm` (A/B only) | ZX0: `SRC_TOTAL` **6,947 B** (`$C000..$DB22` in bank 1), **9,437 B free** (A6: the 272 B of banked descriptors moved to bank 5); raw: 16,384 B (full) | tape block 3 / .sna |
| 3 | sprite sources tail, virtual `$C000..` (MMU slot 3 = page 3) — **empty** with ZX0 (raw: 515 B), then the **bank-3 cold code** (`bank3_code..bank3_end`, below) | ZX0: 0 B sources + 1,760 B code = `BANK3_LEN` 1,760 B, **7,456 B free** to `AY_RESERVE $E400` (raw: 515 + 1,760 = 2,275, 6,941 free; A7 review: + `new_game`/`init_ent_common`/`spawn_tab` and the follower selection / arrival conflicts, 794 B, out of bank 2). ASSERT `bank3_end <= AY_RESERVE` | tape block 4 / .sna |
| 3 | **AY player slot** `AY_RESERVE..$FFFF` (A8, **7 KB** = 7,168 B, game.md §11.2; was 8 KB `$E000`): `ay_code..ay_code_end` (`src/ay.asm`), entry `AY_PLAY` = `AY_RESERVE`. Today the silent stub `ay_play` (37 B: `AY_CALLS` += 1, R7 = `$3F`, R8-R10 = 0) | `AY_LEN` 37 B, 7,131 B free; ASSERT `ay_code_end <= $10000` | tape block 5 (headerless, `start` `.ay`) / .sna |
| 0, 4, 6 | **pre-shift pool**: every frame variant (facing × shift), boot-generated by a bump allocator (no variant straddles a bank) | need 38,176 of 49,152 B (monsters 22,688 + largest hero 12,608 + 2 select idles + straddle slack; ASSERTed) | `gen_kind` / `gen_frame` at boot and at hero select |
| 7 | **screen 2** `$C000..$DAFF` (A7): the screen the ULA shows during play, a copy of the bank-5 screen kept by `present` / `present_full`; **clean-background shadow** (R-1 erase lever), rebased in A7 to `$E000`: the room's tiles in screen layout, bitmap within `$E000..$F79F` (char rows 0–20 only), attrs `$F800..$FA9F` (high byte = screen + `$A0`) | 6,912 + 6,048 B; spare `$DB00..$DFFF` (1,280 B) + `$FAA0..$FFFF` (1,376 B) — B3B-1: 4 tileset slots in each (`TSET_LO`/`TSET_HI`, 1,152 B each; 128 B + 224 B left) + the unused rows 21–23 holes of the shadow bitmap (8 × 96 B, `$F0A0..$F0FF` … `$F7A0..$F7FF`) | screen 2: `present*`; shadow: `shadow_rect` / `shadow_room` on room entry + potion pickup |

Sources are read only at generation time via `copy_virt` (virtual < `$C000` →
bank 1 at +`$4000`, else bank 3; a frame straddling `$C000` is split) — with
ZX0 only the raw items/tiles (`init_tiles`) go through `copy_virt` (A6: the
frame descriptors live in bank 5, `fdesc_tab`); the packed blocks are read by `dzx0_standard` straight from the
`$C000` window (a block never straddles virtual `$C000`: the tool pads it into
bank 3, ASSERTed). The pool
and shadow banks are uncontended (0/4/6) resp. contended (7, erase-only).
`PORT_7FFD_SHADOW` always has bit 4 = 1 (48K ROM: charset, LD-BYTES).

Tape: BASIC `10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "<start>"`
(the 5 USR digits are emitted from the `start` label, today `30341` = `$7685`).
ONE CODE block `lowram_code..code_end` (`TAPE_CODE_LEN` 11,339 B: bank-5
low-RAM cold block `$7685..$7FFF` — code, then the frame descriptors
`fdesc_tab` as its tail — straight into the bank-2 image `$8000..code_end`;
the low-RAM block is ORGed to end exactly at `$8000` so there is no gap, and
`start` is its first byte: `ASSERT start == lowram_code`). **A6 layout
decision:** the descriptors are placed INSIDE the cold block (after the code)
rather than below `lowram_code`, so the tape stays BASIC + one CODE block +
two headerless blocks, the USR target stays the block's first byte, and the
block simply grows downward as frames are added (the fit ASSERT reserves the
growth to `FRT_MAX`). Then three
**headerless** blocks (flag `$FF`) that `start` loads with ROM `LD-BYTES`
before falling into `boot`: bank 1 (`SRC_LEN_LO`), bank 3 from `$C000`
(`BANK3_LEN` = source tail + bank-3 cold code) and (A8) bank 3 from
`AY_RESERVE` (`AY_LEN`: the AY slot, a separate block so the 7 KB gap is
not on tape). The `.sna` enters at `boot`
(all banks preloaded). `tests/game.py` #50 checks bank 1, bank 3 (whole
`BANK3_LEN`), the AY slot (`AY_LEN`) and the low-RAM cold block byte-equal to
the `.sna` after a real tape load, and IM 2 installed.

### Sprite sources (ZX0, A5; descriptors moved out in A6)

Generated before every build by `tools/zx0_sources.py` →
`build/zx0/sprites_zx0.asm` (gitignored, deterministic; needs `tools/bin/zx0`
from `tools/setup_zx0.sh`, else it stops with that hint). Layout, in order, at
virtual `$8000` (`sprite_src`):

| Part | Contents | Size (measured) |
|------|----------|-----------------|
| raw items + tiles | `item_*`, `tiles_*` `.asm` INCLUDEd verbatim (init_tiles reads them with `copy_virt`; never the generator) | 265 B |
| packed blocks `zblk_0..zblk_22` | per kind, in `src/frames.asm` FRM (= fid = `gen_kind`) order, 1–4 consecutive frames of ONE kind, raw ≤ `GEN_SCRATCH_LEN` 1,536 B; each one ZX0 v2 standard forward stream. Partition per kind = fewest packed bytes (DP over 1..4-frame splits) | 68 frames, raw 16,048 → **6,682 B (2.40×)** |
| per-frame EQUs (A6: no bytes) | `nm EQU zblk_N` (its block = `FD_BLK`), `nm_zoff EQU` raw offset in the block (`FD_FRM` = `GEN_SCRATCH + nm_zoff`); plus `nm_w/h/cols/ax/ay` and `nm_len` = raw pixel bytes (cols·H·2, no ATTR byte). Folded into the bank-5 `fdesc_tab` by the FRM list (A5 had 4-B banked descriptors here) | 0 B |

Build-time metadata per block (EQUs, in the `.sym`): `zblk_N_raw`,
`zblk_N_packed`, `zblk_N_first`, `zblk_N_n`; totals `ZX0_BLOCKS`, `ZX0_FRAMES`,
`ZX0_PACKED_RAW`, `ZX0_PACKED_TOTAL`, `ZX0_RAW_SRC_TOTAL` (16,899 = what the
raw build assembles; the per-kind `index.asm` tables `<kind>_frames/_meta/
_flags`, unread by the engine, are not emitted). Total 6,947 vs 16,899 B:
**freed 9,952 B** (bank 1: 9,437; bank 3: 515). The packer parses the frame
`.asm` files strictly (only `DEFB $xx` rows / sub-labels / comments between
`nm:` and `nm_attr:`; anything else fails the build, A6).

Generator path (`lowram.asm`): `gen_frame` reads `frame_tab` (bank 2: cols,
H, offsets) and its `fdesc_tab` entry (bank 5: `FD_BLK`, `FD_FRM`,
`FD_FLAGS`) → `zx0_frame` (DE = block, BC = frame address): if the block ≠
`GEN_ZBLK` it pages the block's bank and `dzx0_standard` unpacks it to
`GEN_SCRATCH` (`$6000`); the frame is then read in place (`GEN_BASE` = scratch
address; no copy to `GEN_SRC`; `mirror_src` reads `(GEN_BASE)`). No banked
descriptor read, no `copy_virt` (A6). `GEN_ZBLK` = one-block cache, valid for
one generator **session** = `alloc_reset`/`alloc_restore` .. the next
`build_room_map`: both entry points clear it (A6; A5 cleared it in `gen_kind`),
so a cached block never outlives its session (`tests/zx0_pool.py` "stale":
poked stale `GEN_ZBLK` + garbage scratch at the select screen → pool still
identical; verified to FAIL with the `alloc_restore` clear removed).
`GEN_SRC` stays for `init_tiles` (raw items) and the raw build. Decompressor =
`src/dzx0_standard.asm` (vendored, pinned commit, unmodified, 68 B);
`zx0_frame` + `dzx0` = 107 B (A5: 121; `zx0_code..zx0_code_end`, ASSERT ≤
`ZX0_BUDGET` 128).

### Double buffer (A7, budget.md §3 option A)

During play the ULA shows **bank 7's screen 2** (`$7FFD` bit 3 = 1, rules
under "Paging shadow"). Everything is still composed in the bank-5 screen
exactly as before; the changed cells are marked during the tick and
**present** copies them (8 bitmap bytes + attr each) from bank 5 to screen 2
**first thing in the next tick, right after the HALT** (top border: it starts
~13k T before the beam reaches line 0 and copies a char row faster than the
beam scans one → measured 0 tears, mostly uncontended). Cost: +1 tick (40 ms)
display latency (user decision, A7).

| Routine (file) | Where / when | What |
|----------------|--------------|------|
| `pmark_rect` (gfx.asm, bank 2) | — | ORs cell rect C,B,D,E into `PRES_MASK` (1- and 2-mask-byte rects in one row pass), sets `PRES_ANY`, lowers `PRES_RMIN` |
| `pmark_dmg` (gfx.asm) | `play_loop`, right after `render` | marks `DMG_LIST[0..DMG_PRES_N)` (PEND_DMG restores, erased old footprints, new / attr-only footprints; A7b: a moved sprite's old + new footprint is ONE rect when their union is a rectangle — same row band or same col band, overlapping or touching — which covers the in-place redraw too; the overlap-repair rects after them only rewrite identical bytes) |
| `present` (gfx.asm) | `tick_work`, before render (probe `probe_presented` after it) | flushes `HUD_PW` into the mask, copies every marked cell from `PRES_RMIN` down, clears the mask; ~50 T when idle; A7b: a full mask byte (8 cells, HUD text) goes by LDI lines (`.full8`, ~1.5k vs ~2.1k T) except cols 24-31 of a third's last char row (low byte `$F8`: LDI would carry into H) |
| `draw_zap` / `hud_track` / `clear_row` | during the tick | zap run → `pmark_rect`; HUD rows → `HUD_EXT` / `HUD_PW` per string (only the cols that held or now hold text; `clear_row` blanks only `HUD_EXT` cols) |
| `present_full` (lowram.asm) | `start_game`; end of `do_exit` | whole screen bank 5 → screen 2 (LDIR 6,912 B), mask + `HUD_PW` cleared, show bank 7 |
| `show_bank5` / `set_screen` (lowram.asm) | `enter_select`; `do_exit` before the scroll | display bank 5 (they draw there) |
| `vis_reset` / `vis_room_sync` (lowram.asm) | `new_game` (tail) / `do_exit` after arrival | **the render-state resync contract** (B7, B7b): render runs first in a tick from the previous `anim_tick`'s `N_VIS`/`N_FID`/`RLIST`, so EVERY path that rewrites the entity table (`new_game`; Stage 3B level change / stairs) must end with `vis_reset` (every slot hidden), and every path that changes `CUR_ROOM` with slots kept (`do_exit`) with `vis_room_sync` (slots not live in `CUR_ROOM` hidden; the hero keeps its last frame). Both rebuild `RLIST` (`RLIST_N`) from the slots still visible or drawn. B7b (A7 review): a new game after death drew the dead game's slots and the hero with the old hero's frame id; `tests/game.py` #54 |

Invariants (asserted): at `probe_presented` screen 2 == the bank-5 screen
(`tests/flicker.py` and `tests/game.py` #53 — zap, potion pickup, quaff —
every tick); at every golden displayed == composed (`tests/game.py`);
`tests/flicker.py` gates **split late rows** = 0 (a row whose copy starts
after the beam scanned it, in a present that also copied a row ahead of the
beam: old and new rows in one displayed frame; measured 0 late rows at all).

Rules / caveats:
- On an **overrun tick** (`wait_tick` finds ≥ 2 frames gone) there is no
  HALT before `present`, so it starts wherever the beam is: a one-frame tear
  of a copied cell is possible on overrun ticks only.
- **A8 ISR** (done): pages `BANK_AY` with `(PORT_7FFD_SHADOW & ~7) | 3`
  (keeps bit 3 = the shown screen, bit 4) and restores with
  `OUT (PORT_7FFD_SHADOW)`; never writes the shadow ("Interrupts (A8)").
- `present` / `present_full` must not run under `DI` (they are long; the
  music would stall) — they never do. Tests read the DISPLAYED screen (`frame()`; one tick behind
bank 5), `composed_frame()` for bank 5.
Cost (ZEsarUX, contended): present ~200 T per cell at the tick start;
budget mix worst tick 120,293 → **140,151 T (98.8%)**, heavy (over the M1
cap, reported) 124,729 → 143,471 T (101.2%, 1 tick). A7 review: mix
140,170 T; heavy 144,913 T (102.2%, 2 ticks) — its ghost now starts at x 23
(x 4 is inside `{5,2}`'s end box, B8), so the fight geometry differs. **A7b (renderer optimisation, hard prerequisite of A8)**, same tests:
budget mix worst 140,170 → **121,395 T (85.6%)**, heavy 144,913 (2 overruns)
→ **121,049 T (85.4%, 0 overruns)**; `tests/flicker.py` worst tick a
145,966 (2 overruns) → 122,100, b 64,377 → 58,747, c 109,010 → 96,129, all 0
events / tears / split; means mix 71,716 → 61,139, heavy 52,256 → 44,472.
Levers, in measured order: `erase_rect` steps rows incrementally (218 → 74 T
per row; −1.2k / −2.4k); per-slot render state as one 16-B record per slot
(`SLOTREC`, fields by `inc l` instead of a 31-T array lookup each),
classify + erase + damage in ONE `RLIST` pass (was three), merged move rects
(−8.3k / −11.2k); the blit with DE = screen / HL = pool data (`and (hl)` /
`or (hl)`: 44 T/byte, was 52; line end `ld e,c`: 31 T/line aligned, was 42;
FRT pointer by nibble swap; −8.1k / −9.2k); `stamp_rect` row step 55 T (was
79), `print_char` `inc e`, present `.full8` (−1.2k / −0.8k together). Not
taken (measured or costed, no gain worth the bytes): attr-only present for
`DIRTY_ATTR` (flash ticks are not the worst ticks), run-length present for
partial mask bytes (break-even ~4 cells per run; sprite runs are 3-7),
moving code to `$B200` (bank-2 code is already uncontended; only the
screen / shadow data is, and that cannot move), reordering render into the
border (the tick fills both frames). The worst ticks are now present of a
turn's HUD lines + sprite rects (~26k, half in contended display time) +
render ~85k (blits ~55k) + the turn's HUD print (~11k). End screens keep
showing bank 7; the 3E inventory page will draw in bank 5 behind
`show_bank5` and leave through `present_full`.

### Interrupts (A8): IM 2 + ISR + AY player slot

| Item | Where | Why there |
|------|-------|-----------|
| vector table `ISR_VEC_TABLE` | `$BB00..$BC00` (257 B of `$BC`), `I` = `$BB` | bank 2: always mapped and uncontended. `I` in `$40-$7F` (bank 5, contended) triggers the 128K "snow"/crash bug; `$C0-$FF` is the paged window (the table would vanish when another bank is paged). A full 257-B table: the IM 2 low byte comes off the floating bus, `$FF` on a stock 128K but not guaranteed (peripherals, +2 variants) — any byte reads `$BCBC` |
| ISR `isr` | `ISR_ADDR` `$BCBC..$BCF3` (56 B) | bank 2 like the table (the ISR must be mapped whatever bank sits at `$C000`); assembled in the low-RAM cold block (`isr_image`, `DISP ISR_ADDR`) and copied at boot, so it costs no bank-2 **image** bytes (the image headroom is for Stage-3 hot code) |
| player slot `AY_PLAY` | bank 3 `$E400..$FFFF` (7 KB) | the user-approved AY reserve (game.md §11.2); bank 3 is contended, but the ISR runs at the frame start (top border), so its fetches are not delayed in practice |
| `SYS_FRAMES` | `$5C78` (3 B) | unchanged: the tick pacing (`wait_tick`, `resync_tick`, `sel_run`, `start_game`) reads its low byte |

Sequence per frame (interrupts off): IM 2 acknowledge (19 T) → push AF, HL →
`SYS_FRAMES` += 1 (ROM `MASK-INT` semantics: 16-bit increment, carry into the
third byte) → push BC, DE, IX, IY → `OUT ($7FFD), (shadow & ~7) | BANK_AY` →
`call AY_PLAY` → `OUT ($7FFD), shadow` → `isr.done` → pops → `EI` / `RET`.
Build options (`src/defs.asm`): `ISR_SAVE_ALT=1` also saves AF'..HL' (+8 B,
+~60 T; assemble-only, untested at runtime); `ISR_ROM_CHAIN=1` skips the counter and ends with `jp $0038` (ROM
FRAMES + keyboard scan; needs `IY = $5C3A`; −14 B, ISR ~1.54k T/frame
measured; assemble-only, untested at runtime). Default: neither. Input never depended on the ROM ISR
(`scan_matrix` reads the ports), so the chain is not needed.

**Paging race protocol** (no `DI`): see `docs/conventions.md` "Interrupts".
Main code writes the shadow, then the port; the ISR only reads the shadow
(at both of its OUTs) and never writes it, so an interrupt between the two
writes just OUTs the new value early. The screen bit (A7 double buffer) and
ROM bit ride along in both ISR OUTs.

**DI / EI sites** (all of them): `start` `DI` (tape entry; LD-BYTES' own
`DI` / closing `EI`, ROM IM1 active until boot); `boot` `DI` … `EI` (SP
reset, `isr_install`, the first shadow write — the ISR must not run before
the shadow is valid; boot only, before any music); `check_paging.locked`
`DI` + `HALT` (deliberate stop); the ISR's closing `EI`. None in bank 2 /
bank 3 runtime code.

**Cost (measured, ZEsarUX, breakpoints at `isr` / `AY_PLAY` / `isr.done`):**
acknowledge + HALT exit 19 T, entry → `AY_PLAY` 198 T, stub 286 T, restoring
`OUT` 35 T, pops + `EI`/`RET` 82 T: **620 T per frame**, of which the ISR's own
overhead is **334 T** (315 T own instructions + 19 T acknowledge; the other 286 T is the stub). The ROM IM1 handler it
replaces cost ~990 T (tick start after the HALT: 1,051 → 688 T in
`tests/flicker.py`). It runs in the top border (frame T 0–620), so bank-3
fetches see no contention. Worst ticks, A7b → A8 (same tests): budget mix
121,395 → **120,849 T**, heavy 121,047 → **120,726 T**, `tests/flicker.py` a
122,100 → **121,416**, b 58,747 → 58,304, c 96,129 → 95,386; 0 overruns /
flicker events / tears / split rows. **Headroom for a real player** at ~6.5k T
per call: per 2-frame tick two ISRs of 334 + 6,500 = 6,834 T → 2 × 6,834 ≈
13.7k T count against the 141,816 T. The measured worst tick 120,849 T (budget
mix) already holds 2 × 620 = 1,240 T of stub ISRs (the stub itself is
2 × 286 = 572 T of that), so work without ISRs ≈ 119.6k; with the player
119.6k + 13.7k ≈ 133.3k → **~8.5k T (6.0 %) left**. Caveat for the player task: a 6.5k player in the
HALT-side ISR starts `present` ~6.2k T later in the frame (still inside the
14.3k T top border, but re-run `tests/flicker.py` for late rows / tears).

### Cold code placement (A3) and far calls

Hot (per-tick) code stays in bank 2 (uncontended). Cold code lives in two
contended places, chosen by whether it pages `$C000`:

| Where | Why | What |
|-------|-----|------|
| bank 5 low RAM `lowram_code..$7FFF` (`src/lowram.asm`) | always mapped: may page any bank through `$C000` | `start`, `boot`, `check_paging`, (A8) `isr_install` + `isr_image` (the ISR's load image, copied to `ISR_ADDR`), `start_game`, `init_kbd_mirror`, `sel_tab`, the generator (`pool_banks`, `alloc*`, `build_bitrev`, `copy_virt`, `gen_kind/frame/facing/variant`, `mirror_src`, `mul8`, `frt_ptr`, `sel_frt_copy`), `init_tiles` + its stand-in glyphs / `tile_attr_src` / `tile_src_tab` / `bg_tiles`, (A7) `set_screen` / `show_bank5` / `present_full` / `hud_clear_mark` / `vis_reset` / `vis_room_sync`, (A7 review) `build_room_map` (its `map_cell` lookup stays in bank 2: `potion_pickup` uses it every turn end), and (A6) the frame descriptors `fdesc_tab` as the block's tail |
| bank 3 after the source tail, `bank3_code..bank3_end` (`src/bank3.asm`) | needs no other `$C000` bank while running | hero select (`sel_run`, `select_loop`, `select_tick`, `row_attr_fill`, select strings); transition scrolls (`hscroll_room`, `vscroll_room` and their row/column movers) — they touch only the `$4000` screen, `ROOM_MAP`/`NEXT_MAP`/`TILE_*` (bank 5) and `TMP4/5` (bank 2); (A7 review) `new_game` + `init_ent_common` + `spawn_tab` (far3 from `start_game`), `follow_select` + `dest_counts` + `place_follower` and `arrival_conflicts` (far3 from `do_exit`) — bank-2 queries + `vis_reset` only |

Bank-3 code is entered only via `far3` (bank 2, `gfx.asm`): HL = target, A =
argument; saves `PORT_7FFD_SHADOW`, pages bank 3 (`page_bank`: bit 4 = 1,
shadow before `OUT`), calls, then `restore_page` writes the saved value back
(shadow first, then `OUT`); BC/DE/HL/IX of the target pass through. Bank-3
code must never page `$C000` itself; the select screen blits through
`blit_keep` (bank 2), which re-pages the caller's bank after the pool blit.
`enter_select` (bank 2) = `show_bank5`, `far3 sel_run` → `jp start_game`
(bank 5). A7: the scrolls and the select screen keep drawing on the `$4000`
screen, which is the one displayed while they run (`show_bank5` in
`enter_select` / `do_exit`); `start_game` and the end of `do_exit` copy it
to screen 2 and show bank 7 (`present_full`).

Cost (measured, ZEsarUX, contention emulated; before → after A3):

| Path | Before | After | Δ |
|------|--------|-------|---|
| `boot` → first `select_tick` (pool generation) | 3,601,619 T (50.8 fr) | 4,120,438 T (58.1 fr) | +14.4 % (+146 ms) |
| select '1' (Knight) → first `tick_work` | 2,639,335 T | 2,971,412 T | +12.6 % (+94 ms) |
| select '2' (Wizard) → first `tick_work` | 2,001,164 T | 2,262,333 T | +13.1 % (+74 ms) |
| room A→B (`do_exit` → `resync_tick`) | 3,058,044 T | 3,270,924 T | +7.0 % (+60 ms) |
| per-tick worst (`tests/budget.py` mix / heavy) | 120,382 / 125,067 T | 120,382 / 125,067 T | 0 |

A5 (ZX0 sources; `tests/zx0_pool.py`, same method; A3 build → A5 build):

| Path | A3 (raw sources) | A5 (ZX0) | Δ |
|------|------------------|----------|---|
| `boot` → first `select_tick` | 4,120,438 T | 4,760,719 T | +15.5 % (+183 ms) |
| select '1' (Knight) → first `tick_work` | 2,971,412 T | 3,252,935 T | +9.5 % (+80 ms) |
| select '2' (Wizard) → first `tick_work` | 2,262,333 T | 2,472,947 T | +9.3 % (+60 ms) |
| Knight game → select → '2' (regen after rooms) | 2,198,213 T | 2,410,936 T | +9.7 % (+61 ms) |

(~67 T per unpacked byte net: dzx0 runs contended in bank 5, reads contended
bank 1, writes contended bank 5; the saved `GEN_SRC` copy is ~21 T/B. Lever if
it matters: `dzx0_turbo` (126 B) with `ZX0_BUDGET` raised, or the generator in
bank 2.) Per-tick cost unchanged (generator is cold).

A6 (limits + bank-5 descriptors; `tests/zx0_pool.py --baseline` = main @
`1242a15`, same method, both ZX0 builds):

| Path | A5 | A6 | Δ |
|------|----|----|---|
| `boot` → first `select_tick` | 4,760,719 T | 4,747,696 T | −0.3 % |
| select '1' (Knight) → first `tick_work` | 3,252,935 T | 3,195,050 T | −1.8 % (−16 ms) |
| select '2' (Wizard) → first `tick_work` | 2,472,947 T | 2,415,062 T | −2.3 % (−16 ms) |
| Knight game → select → '2' (regen after rooms) | 2,410,936 T | 2,410,936 T | 0 (frame-quantised: ends on a `wait_tick` HALT) |
| per-tick worst (`tests/budget.py` mix / heavy) | 120,382 / 125,067 T | 120,293 / 124,729 T | −0.1 / −0.3 % |

(Generator: no banked descriptor `copy_virt` per frame. Per tick: `frame_tab`
stride 8 → 4 saves one `add hl,hl` per lookup (3 lookups per drawn sprite),
outweighing the +8 T per redrawn background cell of the 64-id glyph address.)

### Bank 2 (`$8000-$BFFF`)

| Range | Symbol | Contents |
|-------|--------|----------|
| `$8000..$A2CF` | `image_start`…`code_end` | HOT code + static tables (8,912 B incl. 251 B `ALIGN` pad before `kind_tab`; `ASSERT code_end <= FRT`). **Headroom measured (A7b rebased on the B8 rev): 816 B to `FRT` + 251 B pad = 1,067 B** for code/static tables (A7 review: 993 B; A7b: code −78 B net — the one-pass record render (−138 B) and the blit rewrite (−46 B) pay for the erase row stepping (+26), `stamp_rect` / the 16-bit blit entry patch (+19) and the present `.full8` path (+61); A6: 677 B; A7: 111 B after present / pmark / HUD tracking / in-place rect dedupe / paging +566 B; the review moved 1,062 B of cold code out — `build_room_map` 254 B to bank-5 low RAM, `new_game` + `init_ent_common` + `spawn_tab` and follower selection + arrival conflicts 794 B to bank 3, net of the `far3` call sites — and added the B8 flyer ladder-end rule +159 B and the bank-2 `map_cell` +21 B; the 2026-10-02 cross-or-leave flyer rule + blocked-climb wait: +4 B net), plus the 1,536 B free runtime RAM `$B200..$B7FF` below. Code bytes `$8000..kind_tab_pad` 8,193 (A7 review 8,271; A7 9,153; A6 8,587). `kind_tab` page-aligned at `$A100` (moves with the code: tests read it from the `.sym`), **2 pages** (`KT_SIZE` `$200`): 13 parallel **32-B** kind arrays (`K_MAX` 32; ids 0..8 used, 2 = Rogue hole) + MOD7/DIV7 tables, `KT_END` `$1D0` → `$A2D0..$A2FF` 48 B spare in its page (resistances, 3F). No array crosses a page: `KFIELD` folds the page into `H`. `frame_tab` **4 B/fid** (`FT_COLS`, `FT_H`, `FT_OFFR`, `FT_OFFL`: only what the renderer reads; 68 fids = 272 B). `far3` / `restore_page` / `blit_keep` / `enter_select`: the bank-3 trampolines (48 B). |
| `$A600..$AFFF` | `FRT` | frame runtime table (A6: moved from `$B200`): 16 B/fid (4 variants × bank,lo,hi), **`FRT_MAX` 160** (68 used); `FRT = P_ENTITIES − FRT_MAX × 16` |
| `$B000..$B1FF` | `P_ENTITIES` | 16 slots × **32 B** (layout below); slot 0 = hero |
| `$B200..$B7FF` | `BANK2_FREE` | the vacated A5 `FRT` (1,536 B, runtime RAM, not in the image/tape; `BANK2_FREE_END` = `SLOTREC`). **B3B-1 (D8): fully reserved** — `FONT6` `$B200..$B4FF` (6×8 text font, 96 × 8 = 768 B, boot copy target, B3B-11) + `HOT_COPY` `$B500..$B7FF` (768 B, boot-copied hot code, risk R2). Unused until those tasks |
| `$B800..$B8FF` | `SLOTREC` | A7b: per-slot render record, 16 slots × **16 B** (one page; record = `SLOTREC + slot*16`, fields reached by `inc l`): `R_VIS +0`, `R_FID +1` (written by `anim_tick`), `R_FPX +2`, `R_FPY +3`, `R_COL +4`, `R_ROW +5`, `R_COLS +6`, `R_ROWS +7` (`R_FID..R_ROWS` = the entity's drawn block `E_DFID..E_DROWS` in the same order: `draw_slot` copies it with one LDIR; ASSERTed), `R_LEFT +8`, `R_ATTR +9`, `R_DATTR +10`, `R_DIRTY +11`, `R_LOG +12`, +13..15 spare (was the 13 × 16-B `SLOTVARS` arrays `N_VIS`… `$B800..$B8CF`) |
| `$B900..$B9BF` | `DMG_LIST` | per-render damage rects, 4 B each (c0,c1,r0,r1), 48 max |
| `$B9C0..$B9CF` | `PEND_DMG` | queued damage for the next render (4 rects) |
| `$BA00..$BA4F` | `LIVE_LIST` | per-turn collider list, 5 B/entry (slot, ptr, w, h); `LIVE_N $BA50` |
| `$BA60..$BA6F` | `RLIST` | per-tick render list (slots visible or still drawn); `RLIST_N $BA70`, `RL_IDX $BA71` |
| `$BA72..$BA79` | `PL_X/Y/W/H`, `PL_STOREY`, `PL_LADDER`, `MSG_Q`, `BLIT_CROWS` | per-turn hero cache, queued impact message, aligned-blit counter |
| `$BA80..$BA9F` | `SEL_FRT_SAVE` | 2 × 16 B: the select idles' boot FRT rows (`sel_frt_copy` saves at boot, restores on every `enter_select`; a game's `gen_kind` re-points its hero's rows above the alloc mark, which the next hero overwrites) |
| `$BAA0..$BAFF` | `PRES_MASK` | A7 present dirty-cell mask: 24 rows × 4 B (`PRES_LEN` 96), byte `row*4 + col/8`, bit `7 − col%8`; ends at the page end (`present` stops when `L` wraps) |
| `$BB00..$BC00` | `ISR_VEC_TABLE` | A8 IM 2 vector table, 257 B, every byte `ISR_VEC_BYTE` `$BC` (`I` = `$BB`); filled by `isr_install` at boot (runtime only, not on tape) |
| `$BC01..$BC0F` | — | spare (15 B) |
| `$BC10..$BC57` | `OCC_MASK` | B3B-1 (D6, used from B3B-10): occupancy mask, rows 0–17 × 4 B = 72 B, `PRES_MASK` layout (byte `row*4 + col/8`, bit `7 − col%8`); 1 = a sprite covers the cell (`decor_tick` skips it) |
| `$BC58` / `$BC59` | `ANIM_N` / `ANIM_RR` | B3B-1: `ANIM_LIST` entries used (0..12) / `decor_tick` round-robin index |
| `$BC60..$BC8F` | `ANIM_LIST` | B3B-1 (D6): animated decor cells, 12 × 4 B (`AL_COL`, `AL_ROW`, `AL_TYPE`, `AL_PHASE`); filled by the decor deriver (B3B-9) |
| `$BC90..$BCBB` | — | spare (44 B, runtime RAM) |
| `$BCBC..$BCF3` | `ISR_ADDR` | A8 ISR, 56 B (`ISR_LEN`; 68 with `ISR_SAVE_ALT`, 42 with `ISR_ROM_CHAIN`; ASSERT end ≤ `ISR_ADDR_END` `$BD00`), copied from `isr_image` at boot; `$BCF4..$BCFF` spare |
| `$BD00..$BEFF` | — | stack, **768 B** (SP = `$BF00`, grows down to `STACK_BOTTOM $BD00`; A8: was 1 KB from `$BB00`). **Measured max depth 40 B** (lowest byte touched `$BED8`; pattern-fill over boot, both hero starts, a room transition, the §8.2 walkthrough and both `budget.py` fights, ROM IM1 ISR included; tape path's `LD-BYTES` not covered, ~10 B). The A8 ISR adds 16 B (return address + 6 pairs) + the player's own depth to whatever is in use |
| `$BF00..$BFFF` | state block | below |

**Entity record** (32-B stride, `defs.asm`): `+0 KIND, +1 ROOM, +2 FLAGS
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
| `$6600` | `TILE_GLYPHS` | 512 | 8×8 tile glyphs, **64 ids** (A6), glyph = base + id·8; **512-aligned** so `tile_rect` forms it as `E = id·8`, `D = (base>>9) RL CF` (+8 T per cell vs 32 ids) |
| `$6800` | `BITREV_TAB` | 256 | bit-reverse table (mirroring, boot; page-aligned) |
| `$6900` | `TILE_ATTRS` | 64 | attr by tile id (one page: `ld h, TILE_ATTRS>>8`) |
| `$6940` | `GEN_SRC` | 512 | generator: source frame copied out of bank 1/3 (raw build; `init_tiles` items) |
| `$6B40` | `GEN_MIR` | 512 | generator: mirrored frame (`LOWRAM_END` = `LOWRAM_FREE_END` `$6D40`) |
| `$6D40..$6E7F` | `LVL_STATE` | 320 | B3B-1: **3B level state** (header 16, `EDGE_TAB` 6 (+10 spare), `ROOM_DESC` 9 × 16, 16 spare, `FLOOR_LIST` 32 × 4) — byte layout under "3B contracts". Runtime only (not on tape); unused until B3B-7 |
| `$6E80..$6EBF` | `ORN_GLYPHS` | 64 | B3B-1: row-17 ornament glyphs (8 × 8 B, game.md §3.3: not tile ids, same on every level). Here, not in bank 3, because the transition scrolls redraw row 17 without bank 3. `LOWRAM_END_3B` = `LOWRAM_FREE_END` = `$6EC0` |
| `$6EC0..$761D` | free | 1,886 | of which 460 B are kept for descriptor growth (below); **1,426 spare** (`LOWRAM_SPARE` DISPLAY) |
| `$761E..$7FFF` | `lowram_code` (`start` first) | 2,530 | **cold block**, ends exactly at `$8000` (`src/lowram.asm`): code 2,190 B (A8 +103: `isr_install` 31 + 1 for its call replacing `im 1`, the ISR image 56, the AY tape block load 15; A7b +8: `vis_reset` / `vis_room_sync` walk the 16-B `SLOTREC` records; A7 review +295: `build_room_map` 254 out of bank 2, `vis_reset` + RLIST rebuild 41; A7 +193: `hud_clear_mark`, `vis_room_sync`, `set_screen`/`show_bank5`/`present_full`, boot HUD init, 0-frame `gen_kind` guard; A6 1,591; A5 1,572: + session cache clears in `alloc_reset`/`alloc_restore` 11, − `gen_kind` clear 6, + 64-attr clear in `init_tiles` 13, `zx0_frame` 53 → 39, `gen_frame` descriptor read +15), then **`fdesc_tab..fdesc_end`** (A6): frame descriptors, `FDESC_STRIDE` **5 B** × 68 = 340 B (`FD_BLK` word = virtual packed block / raw: virtual frame, `FD_FRM` word = `GEN_SCRATCH` + in-block offset, `FD_FLAGS`), generated from the same `src/frames.asm` list as `frame_tab` (ASSERT counts equal). Raw build: 2,329 B at `$76E7` |
| inside the cold block | A5 `zx0_code..zx0_code_end` | 107 | `zx0_frame` 39 + `dzx0_standard` 68 (ASSERT ≤ `ZX0_BUDGET` 128; `ZX0_RESERVE` = 0 in ZX0 builds, 128 in `-DZX0_SOURCES=0` builds) |
| `$6000..$65FF` (alias) | A5 `GEN_SCRATCH` | 1,536 | ZX0 unpack target **aliasing `ROOM_MAP`+`NEXT_MAP`** (ends exactly at `TILE_GLYPHS`, ASSERTed): the generator runs only at boot, hero start and (3F) level start, before the room map is built — never mid-room. Guard: `GEN_TRAP` (state block) counts `gen_frame` calls while `GAME_STATE` is PLAYING/TRANSITION; tests assert 0 |

Tile ids (A6): 0..31 = common/engine tiles (`TILE_COMMON`; `init_tiles`,
`T_COUNT` 21 used, ASSERT ≤ 32), **32..63 = per-level decor slots**
(game.md §1.2), zeroed at boot. **Hook (3B, not built):** at level start copy
the level's 32 glyphs to `TILE_LEVEL_GLYPHS` (= `TILE_GLYPHS + 256`, i.e. the
whole second page) and its 32 attrs to `TILE_LEVEL_ATTRS` (= `TILE_ATTRS +
32`) from the 8 tilesets (8 × 288 = 2,304 B) in bank 7 spare — two LDIRs from
bank-5 cold code (pages bank 7 at `$C000`).

Fit (ASSERTed: `lowram_code − ZX0_RESERVE − (FRT_MAX − FDESC_COUNT) ×
FDESC_STRIDE ≥ LOWRAM_FREE_END`, and `fdesc_end == lowram_code_end`): 3,392
fixed buffers (incl. the 64-id tiles) + 384 B3B level state / ornament
(B3B-1: `LOWRAM_FREE_END` = `LOWRAM_END_3B`) + 2,530 cold block + 460 descriptor
growth to 160 frames = 6,766 of 8,192 B → **1,426 spare** (B3B-1; before it 1,810; A8: 1,913; A7 review: 1,921; A7: 2,216; A6: 2,409; A5: 1,308 with
its 1,920 B ≤ 12-B descriptor reserve), room for the ~0.6 KB level state with
~1.3 KB margin. A separate 1.5 KB ZX0 scratch would now fit, but would eat
most of that margin — the alias stays. `$5B00-$5BFF` and `$5CC0-$5FFF` (~1,088 B, E: free once `boot` has
moved SP off the BASIC stack) are a further runtime-only (not tape-loadable)
reserve. A8: after `boot` nothing uses the system variables but
`SYS_FRAMES` (`$5C78-$5C7A`; the IM 2 ISR does not run the ROM keyboard scan),
so most of `$5C00-$5CBF` is free too unless `ISR_ROM_CHAIN=1`.

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
| `$BF14` | `HERO_KIND` | 0 Knight, 1 Wizard (2 = retired Rogue: hole in the `K_*` ids) |
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
| `$BF93` | `GEN_ZBLK` | word: virtual address of the ZX0 block now unpacked in `GEN_SCRATCH` (0 = none; cleared by `alloc_reset` / `alloc_restore`, A6) |
| `$BF95` | `PRES_ANY` | A7: 1 = `present` has work (a mask bit or a HUD width is pending) |
| `$BF96` | `DMG_PRES_N` | A7: `DMG_LIST` rects `pmark_dmg` marks (those before the overlap-repair pass) |
| `$BF97` | `PRES_RMIN` | A7: first marked row (`$FF` none): `present` starts its scan there |
| `$BF98` | `FLY_INBOX` | `ai_flyer`: the flyer's ladder-end box overlap at turn start (`flyer_lcost`, once per turn); `try_step` reads it for the cross-or-leave rule (prototype §3.5). 0 outside `ai_flyer` (cleared on return and by `new_game`) |
| `$BF9A` / `$BF9D` | `HUD_EXT` / `HUD_PW` | A7, 3 B each (rows 21..23): ink extent of the row in bank 5 (cols 0..EXT−1) / cols changed since the last present (`print_char`, `clear_row` → `hud_clear_mark`) |
| `$BF99` | `GEN_TRAP` | count (saturating): `gen_frame` ran while `GAME_STATE` = PLAYING/TRANSITION, i.e. while `GEN_SCRATCH` holds live room maps (debug trap, expect 0; `tests/game.py` #1/#40/#51) |
| `$BFA0` | `MSG_BUF` | 32 B spare |
| `$BFC0` | `TIMING_MARK` | spare |
| `$BFC2` | `AY_CALLS` | A8 word: `AY_PLAY` calls (the silent stub counts them; = frames since boot's `EI`). Test-observable |
| `$BFC4..$BFCF` | — | spare (general) |
| `$BFD0..$BFFF` | **3B sub-range** (`STATE_3B`, B3B-1) | `PANEL_DIRTY $BFD0` (D5 `PD_*` bits), `$BFD1` spare, `HUD4_EXT $BFD2` (4 B) / `HUD4_PW $BFD6` (4 B): rows 20..23, the B3B-11 successors of `HUD_EXT`/`HUD_PW` (old ones stay in use until then), `LOG_QN $BFDA`, `$BFDB..$BFDF` spare, `LOG_Q $BFE0` (8 B, layout B3B-11), `$BFE8..$BFFF` spare. Test-observable |
| `$BFC1` | `CLIMB_BLK` | 1 = this input's climb was blocked by an entity → `try_player_turn` makes it a WAIT (prototype §6.4, rule 2026-10-02); cleared at every `try_player_turn` |

System variable used: `SYS_FRAMES $5C78` (3-byte frame counter, bumped by the
A8 IM 2 ISR exactly as the ROM's did) paces the 25 Hz tick; `IY` stays
`$5C3A` throughout (tape path IM1 / `ISR_ROM_CHAIN`).

### Test probe labels

`tick_work` (tick work starts), `wait_tick` (tick work done, render complete) and
`select_tick` (after the select-screen HALT; bank 3 `$C2xx` — only bank-3 code
ever executes at `$C000+`, so a PC breakpoint there is unambiguous) exist so the
tests can stop the emulator at tick boundaries (ZEsarUX cpu-step + breakpoints).
`start.lo` (tape entry past the paging check) and `check_paging.locked`
(paging-lock stop) are probes for `tests/game.py` #43 (bank 5 low RAM).
`hscroll_room.step` (bank 3) is #29's mid-transition probe.
`present.probe_row` (A = row being copied) / `present.probe_row_end` and
`probe_presented` (main.asm, after the tick-start present) (A7) are
`tests/flicker.py`'s present probes (no code).
`isr.done` (A8, `ISR_ADDR` space: after the ISR's restoring `OUT`, port ==
shadow) and `AY_PLAY` (bank 3, only ever reached from the ISR) are
`tests/game.py` #61's ISR probes.

Per-game vs since-boot observables: `new_game` resets `TICK_COUNTER`,
`ANIM_TRACE`/`_IDX`, `BLIT_MISS`, `DMG_OVERFLOW`, `CLIP_TRAP` (plus RNG/turns);
`OVERRUN_COUNT`, `GEN_OVERFLOW` and `GEN_TRAP` count since boot. Moving them is
free; removing them breaks `tests/game.py` / `tests/budget.py`.

## 3B contracts (B3B-1) — code against these symbols

> Source of truth: `src/level_defs.asm` (EQUs + ASSERTs only, INCLUDEd at the
> end of `defs.asm`; emits no bytes — the B3B-1 image is byte-identical to A8).
> Design refs: game.md §1.1–1.4, §2.1, §2.5, §3.3–3.5, §8.5, §9.1;
> concept-screen §3.1, §3.3, §5; plan.md "3B breakdown" D1–D10.

### Geometry (D3/D4) — new permanent names; B3B-3 switches the engine and deletes the old

| New | Value | Replaces |
|---|---|---|
| `STOREY_COUNT` / `STOREY_ROWS` / `STOREY_AIR` | 2 / 9 / 8 | `STOREYS` 3 / `STOREY_H` 7 |
| `FLOOR_ROW0` / `FLOOR_ROW1` | 8 / 17 | — (storey `s`: air rows `9s..9s+7`, floor `9s+8`; `s` = 0 is the TOP storey) |
| `PLAY_ROWS` / `PLAY_CELLS` | 18 / 576 | `ROOM_ROWS` 21 / `ROOM_CELLS` 672 (the 672-B `ROOM_MAP`/`NEXT_MAP` buffers stay; ASSERT fits) |
| `PANEL_ROW` / `PANEL_ROWS` | 18 / 6 | `HUD_ROW` 21 (3 rows) |
| `ICON_ROW` 18, `INFO_ROW` 20, `STAT_ROW` 21, `LOG_ROW` 22 | | concept-screen §5 |
| `TEXT_ROW` / `TEXT_ROWS` | 20 / 4 | `HUD_ROW` / `HUD_ROWS` for present tracking (`HUD4_EXT` / `HUD4_PW`) |

MOD9/DIV9: B3B-3 rewrites `KT_MOD7`/`KT_DIV7` **in place** (same offsets
`$1A0`/`$1B8`, n = 0..23); `kind_tab` `$1D0..$1FF` stays the 3F resistance spare.

### Room grid and descriptor (D1)

Room id `r = gy*3 + gx` (0..8); neighbours left `r−1` (gx>0), right `r+1`
(gx<2), up `r−3` (gy>0, via the up-exit `{c,0}`), down `r+3` (gy<2, via the
down-exit hole `{c,2}` in row 17). `ROOM_DESC` = `$6D60`, `r*16`, all in page
`$6D` (`ld h,$6D` constant). Every 3-col feature (ladder, shaft, pit) is named
by its **left col c**; a col byte 0 = none (all legal cols ≥ 1). Same-storey
footprints: `|c1 − c2| ≥ FEAT_GAP` (7).

| Off | Symbol | Contents |
|---|---|---|
| 0 | `RD_FLAGS` | `RDF_PRESENT 1`, `RDF_START 2`, `RDF_LAIR 4`, `RDF_DEADEND 8` (leaf), `RDF_KEY 16`, `RDF_SANCTUM 32` (both unused in 3B), `RDF_SEEN 64` (runtime), bit 7 spare |
| 1 | `RD_EXITS` | `RDX_L 1`, `RDX_R 2`, `RDX_U 4`, `RDX_D 8` (grid edges only), `RDX_LS1 16` / `RDX_RS1 32` = that horizontal exit is on storey 1 (must equal the neighbour's opposite bit) |
| 2 | `RD_UPCOL` | up-exit shaft `{c,0}` (rows 0–7) left col; = `RD_DNCOL` of `r−3` |
| 3 | `RD_DNCOL` | down-exit hole `{c,2}` (row 17) left col; = `RD_UPCOL` of `r+3` |
| 4 | `RD_ARRCOL` | D2+ start room: arrival shaft `{c,0}`, rubble-capped (no exit bit) |
| 5 | `RD_EXITCOL` | lair: level-exit shaft `{c,2}` under `T_GRATE` (no exit bit; grate state = `LF_GRATE_OPEN`) |
| 6 / 7 | `RD_LAD1` / `RD_LAD2` | internal ladders `{c,1}` (hole in row 8, rows 8–16), `c ∈ 3..26`; LAD1 ≥ 1 always, LAD2 0 = none. Never a shaft col |
| 8 | `RD_PITCOL` | pit: left hole col `p` (holes `p..p+2` in row 8, caps `T_PIT_L` at `p−1`, `T_PIT_R` at `p+3`); storey-0 floor only (game.md §2.5) → no storey byte |
| 9 | `RD_BLOCK` | dead-end block: bits 0–1 width (0 none / 2 / 3), `RDB_S1` bit 6 storey, `RDB_RIGHT` bit 7 side; cols `0..w−1` or `32−w..31`, WALL + WALLF in the floor row, `T_RUBBLE` at its foot |
| 10–11 | `RD_SEED` | room seed (word, ≠ 0): decor is re-derived from it, never stored |
| 12–15 | `RD_SPARE` | zero |

### `EDGE_TAB` (`$6D50`, 6 B) — horizontal edges only

Index `e = gy*2 + gx` = edge between `r` and `r+1` (gx ∈ {0,1}): right edge of
`r` = `r − gy`, left edge = `r − gy − 1`. Bits: `EG_LINK 1` (connected),
`EG_DOOR 2`, `EG_OPEN 4` (runtime door state, both rooms), `EG_LOCK 8`,
`EG_SEAL 16` (never set in 3B). none = 0 · open passage = LINK · closed door =
LINK|DOOR · open door = LINK|DOOR|OPEN · locked / sealed = LINK|DOOR|LOCK / SEAL.
**Vertical connections have no table** (no doors on them): `RDX_U`/`RDX_D` +
the shaft cols of both rooms. Door cells (concept §3.1): cols 0–1 / 30–31 of
the exit storey, lintel row `9s` WALL, arch `9s+1`, planks `9s+2..9s+7`
(`DOOR_ARCH_DY`, `DOOR_PLANK_DY`, `DOOR_PLANK_H`); open = planks drawn AIR.

### Level header (`LVL_STATE` `$6D40`, 16 B) and `FLOOR_LIST`

| Addr | Symbol | |
|---|---|---|
| `$6D40` | `LVL_DEPTH` | 1..8 (0 = none) |
| `$6D41` | `LVL_SEED` | word, f(`MASTER_SEED`, depth) |
| `$6D43` | `GEN_RNG` | word, generator RNG (D9; never `RNG_STATE`) |
| `$6D45` / `$6D46` | `LVL_ATTR_FLOOR` / `LVL_ATTR_WALL` | game.md §1.2 |
| `$6D47`..`$6D4A` | `LVL_START`, `LVL_LAIR`, `LVL_KEYROOM`, `LVL_SANCTUM` | room ids (`ROOM_NONE` `$FF`) |
| `$6D4B` | `LVL_NROOMS` | 7..9 |
| `$6D4C` | `LVL_FLAGS` | `LF_GRATE_OPEN 1`, `LF_KEY_TAKEN 2`, `LF_SEAL_OPEN 4` |
| `$6D4D` | `FLOOR_N` | floor-list entries used |
| `$6D4E` | `MASTER_SEED` | word, per game |

`FLOOR_LIST` `$6E00..$6E7F`, `FLOOR_MAX` 32 × `FL_STRIDE` 4: `FL_ROOM` (bits
0–3 room, bit 7 `FL_S1` storey 1; `FL_EMPTY` `$FF` = picked up / free),
`FL_COL` (item cell col; row = the storey's standing row `9s+7`), `FL_ITEM`
(3E owns the enum; 3B: `IT_POTION` 1), `FL_QTY`.

### Tile ids (64; common 0..31 FULL)

| Id | Symbol | Note |
|---|---|---|
| 0, 1 | `T_AIR`, `T_PLAT` | |
| 2 | `T_BRICK` = `T_WALL_DARK` | plain air-band wall face; re-glyphed DARK (B3B-2) |
| 3 | `T_WALLF` | wall in a floor row (blocks, lintels in row 8/17) |
| 4–6 / 7–9 | `T_LAD_L/M/R` / `T_HOLE_L/M/R` | ladder / ladder cells in a floor row |
| 10 | `T_POTION` | PROTO; kept while potions are a floor tile (3B stand-in) — then the one free common id |
| 11–14 | `T_COBWEB`, `T_CHAIN`, `T_SKULLS`, `T_MOSS` | reuse `T_CHEST_*`: **valid only after B3B-13** |
| 15, 16 | `T_TORCH_T/B` | small torch (attr cycle) |
| 17, 18 | `T_DRIP1/2` | reuse `T_ZAP1/2`: **valid only after B3B-13** |
| 19, 20 | `T_END_L` = `T_PIT_R`, `T_END_R` = `T_PIT_L` | floor edge right / left of a hole: the pit caps share them |
| 21–25 | `T_DOOR_ARCH_L/R`, `T_DOOR_L/R`, `T_DOOR_LOCK` | concept §3.1 (5 door ids) |
| 26, 27 | `T_GRATE`, `T_RUBBLE` | |
| 28–30 | `T_WALL_DITHER/PATCH/FADE` | wall set |
| 31 | `T_CANDLES` | |
| 32..59 | `T_LVL_BASE`.. | per-level decor (bank-7 tileset) |
| 60..63 | `T_LVL_OBJ` | per-level **attackable** object slots (D8 lectern + Book 2×2); D1–D7 leave them unused |

Row-17 ornament: not tile ids (`ORN_GLYPHS`, 8 × 8 B, attr `LVL_ATTR_FLOOR`).

**`TILE_FLAGS` bits** (D2; table = B3B-5 data `tile_flags`, 64 B by id, one
256-B page, static): `TF_SOLID 1` (bodies + projectiles: walls, block, arch,
closed planks, lectern), `TF_DOOR 2` (closed plank: bump opens), `TF_LOCK 4`
(locked/sealed plank), `TF_LADDER 8` (LAD_*, HOLE_*), `TF_HOLE 16` (floor-row
cell passable vertically), `TF_ATTACK 32` (lectern/Book), `TF_ANIM 64`
(deriver adds the cell to `ANIM_LIST`), `TF_FLOOR 128` (floor support; pit
holes are `T_AIR`, the pit itself is `RD_PITCOL`). `_BIT` twins for `bit`.

### Bank-7 tileset slots

`BANK_TSET` 7; slot = depth − 1; `TSET_STRIDE` 288 = glyphs of ids 32..63 (256
B, `TSET_GLYPHS` +0) + attrs (32 B, `TSET_ATTRS` +256) → one 256-B LDIR to
`TILE_LEVEL_GLYPHS`, one 32-B LDIR to `TILE_LEVEL_ATTRS`. Slots 0–3 at
`TSET_LO` `$DB00..$DF7F`, 4–7 at `TSET_HI` `$FAA0..$FF1F` (`(slot<4 ? LO : HI)
+ (slot&3)*288`). Bank 7 is not loaded from tape today: B3B-2/-8 add a
headerless block (or `.sna` bank 7 data) for them; nothing at runtime writes
`$DB00..$DFFF` or `$FAA0..$FFFF`.

### Panel (D5) and bank-2 runtime

`PANEL_DIRTY` `$BFD0` bits: `PD_HP 1`, `PD_MP 2`, `PD_FOOD 4` (bar + hunger
word), `PD_AMMO 8`, `PD_LOG 16` (scroll + newest line from `LOG_Q`), `PD_ICONS
32`, `PD_INFO 64`, `PD_DEPTH 128` (depth + key). One item per tick, never in
the input tick. `HUD4_EXT`/`HUD4_PW` (rows 20..23, one page, ASSERTed),
`LOG_Q`/`LOG_QN`, `FONT6` `$B200`, `HOT_COPY` `$B500`, `OCC_MASK`, `ANIM_LIST`
— addresses in the bank-2 and state-block tables above.
