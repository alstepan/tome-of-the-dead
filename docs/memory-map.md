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
| `$5B00-$5BFF`| Printer buffer → **`LOG_TXT`** (B3B-11)     | log message ring, 4 × 64 B (runtime only, after boot) |
| `$5C00-$5CBF`| System variables                            |                               |
| `$5CCB-$7FFF`| Free RAM (after BASIC reclaim)              | program + working storage; **D3-6b: `$5E00-$5EFF` = `PF_RAM`** (proj_fire scratch, runtime only — "3D contracts") |
| `$8000-$BFFF`| Program origin region                       | `ORG $8000` for now           |
| `$C000-$FFFF`| Paged bank window                           | bank selected by $7FFD bits0-2|

## 128K banks ($C000 window)

| Bank | Planned use                       | Status   |
|------|-----------------------------------|----------|
| 0    | **D3-TX: the text block** (`TEXT_ADDR` `$C000..POOL_START`, own tape block), then the pre-shift sprite pool | PROTO    |
| 1    | PROTO: sprite sources (virtual $8000-$BFFF), ZX0-packed since A5: 6,947 of 16,384 B (A6); + `vdata` (D3-TX: the text block moved to bank 0); **C3-0: `ui1_code` (3C UI code, via `far1`)** after it | PROTO |
| 2    | (also $8000 fixed)                | system   |
| 3    | PROTO: sprite sources tail (virtual $C000-; empty since A5) + **cold code** (select, transition scrolls, new game, follower selection); **`$F000-$FFFF` AY player slot** (A8; **D3-0: 4 KB**, user 2026-10-06, was 7 KB from `$E400`: silent stub today, called by the IM 2 ISR) | PROTO |
| 4    | PROTO: pre-shift sprite pool      | PROTO    |
| 5    | normal screen (also $4000 fixed); low RAM `$6000-$7FFF` buffers + **cold code** (boot, generator) + frame descriptors (A6) | system   |
| 6    | PROTO: pre-shift sprite pool      | PROTO    |
| 7    | **displayed screen during play** (screen 2, `$C000-$DAFF`, A7 double buffer) + **8 level tilesets** `$DB00-$DFFF` / `$FAA0-$FF9F` (B3B-8: 8 × 320 B, loaded from tape) + **D3-S2: bank-7 cold code** `$E000-$F7FF` (`far7`; was the bitmap shadow) + the attr shadow `$F800-$FA3F` | system / PROTO |

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
`restore_page` takes only bits 0-2 of a saved shadow value (farb (far3 /
far1) / blit_keep never roll the screen bit back). **A8:** the IM 2 ISR pages
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
> `-o DIR` / extra `-D` args for tests; **D3-7: `DEBUG_KIT` (defs.asm, default 1 = the designer's debug start kit, game.md §1.4) — the suites and goldens run on `-DDEBUG_KIT=0`; `KIT_DEBUG` in the `.sym` mirrors it and `tests/game_lib.py` refuses a kit build**) → `build/wazhack.tap` / `build/wazhack.sna`. Includes `constants.asm` (read-only). Spec: `docs/design/prototype.md` rev B.
> Tests read every address below from `build/wazhack.sym`, never hard-coded.

### Banks & tape

| Bank | Contents | Size | Written by |
|------|----------|------|------------|
| 1 | sprite **sources** at *virtual* `$8000..` (MMU slot 2 = page 1): `build/zx0/sprites_zx0.asm` (see "Sprite sources (ZX0)" below; B3B-12 retired the raw `index.asm` A/B build) | ZX0: `SRC_TOTAL` **6,947 B** (`$C000..$DB22` in bank 1), then (B3B-11b, bank-3 relief) the **`vdata` block** 2,704 B (B3B-13 measured) (`vdata..vdata_end`: `font6x8` 768, `panel_icons` 774, the `HOT_COPY` load image `panel_hot_img` 515, `tiles_common` 288 + `orn_glyphs` 64 (D3-0: the 16 B of PROTO zap glyphs `tiles_fx.asm` are no longer assembled; `VDATA_LEN` 3,563 B) — boot / new-game cold data, read only through `copy_virt` / `copy_virt3`; B3B-13: + the **text block** `text_img` 277 B, DISPed to its runtime `$C000..` address — **D3-TX: moved to bank 0**, see the bank-0 row and "Text (B3B-13)" below); **C3-0: then `ui1_img..ui1_img_end` = `ui1_code..ui1_end`** (bank-1 UI code, `src/ui1.asm`, DISPed by `TEXT_DISP` to its runtime `$C000..` address, ASSERTed in bank 1 and `ui1_end <= UI1_LIMIT` `$10000`; empty in C3-0 at `$E4AC`; the build DISPLAYs `bank 1 free`); bank-1 block `SRC_LEN_LO` 9,388 B (C3-0 measured), **6,996 B free** (B3B-13: −265 raw items / tiles, +277 text; **C3-7 measured: bank 1 free 861 B** after the UI code — the 6 hero frames took 904 B of packed sources, was 1,765; **D3-TX: 2,168 B free**, was 992 at D3-0: the text block (1,166 B at D3-0) out to bank 0; `VDATA_LEN` 2,397 B; **D3-4: 783 B free** — +1,322 B packed sources (27 frames) + the 63-B `status_icons` in `vdata` (`VDATA_LEN` 2,460 B)) (A6: the 272 B of banked descriptors moved to bank 5) | tape block 3 / .sna |
| 3 | sprite sources tail, virtual `$C000..` (MMU slot 3 = page 3) — **empty** with ZX0, then the **bank-3 cold code** (`bank3_code..bank3_end`, below) | 0 B sources + code + cold data = `BANK3_LEN` (**D3-7 T7: 11,770 B, 518 B free** (both `DEBUG_KIT` builds) — +44: `pf_miss` + `pf_dodge` in `pf_strike` (`proj3.asm`), +4 (review): `set_reaction_at` lets a BLOCK replace a pending `RC_DODGE`; **D3-7 T6: 11,722 B, 566 B free** (both `DEBUG_KIT` builds) — −~190 `dg_drips` + its scratch (the drips are gone), +~10 `build_room_map` stamps the ammo stacks, `dg_bad` regenerated (ids 17/18 no longer decor); **D3-7 T5: 11,978 B, 310 B free** (both `DEBUG_KIT` builds; T4 left 216 B / 171 B with the kit) — +92 `melee_hit` (`rank3.asm`), −~150 `potion_pickup` (→ bank-7 `pickup7.asm`), −~34 `try_quaff` (→ bank-7 `intent7.asm` `ic_quaff`), −~36 `debug_kit` in kit builds (→ `intent7.asm`); **D3-7 T1: 11,982 B, 306 B free** — +8: `set_reaction_at` / `pf_tick` add `TURN_TICK`; note the `dg_bad` ALIGN 64 has only ~2 B of slack: 3 more bytes in bank-3 code before `decor_gen.asm` cost 64; **D3-7 T0: 11,974 B, 314 B free** — −284: `intent3.asm` → bank 7 (`intent7.asm`), `slot_act_tab` / `slot_act` / `abil_rank` + the `icons3.asm` page pad → bank 2, `rank3.asm` `abil_load` +~80; **D3-6b: 12,258 B, 30 B free** — +1,046: `proj3.asm` ~1,060 B, `deal_hit` −14 (shares `rsp_hl`); D3-6a: 11,212 B, 1,076 free; the figures that follow are older) **9,893 B, 2,395 B free** (merged with D3-1 / D3-TX; LP alone: 9,637 B, 2,651 B free) to `AY_RESERVE $F000` (**LP +1,216**: `src/lpop3.asm` 1,302 B (`lp_dtab` 48, `lp_wt` 9, `lp_budget`, `lp_append`, `lp_bank`, `lp_transition`, `lp_enter`, `lp_fit`, `lp_place`, `lp_cmap` / `lp_mark`, `lp_legal`, `lp_spawn`), `follow_admit` / `dest_counts` LP paths ~+70, the stand-in `pop_one` / `pop_kinds` / `pop_cols` −~150, an `icons3.asm` page pad for `slot_act_tab`; before LP: 8,421 B, 3,867 B free (**D3-0**: AY reserve 7 → 4 KB = +3,072 B; the PROTO zap out −87 B: `init_tiles`' zap-glyph copy, `do_attack`'s zap tail + `wz_zap`; `kx_tab` +192 B (R2, zeros until D3-1); the `ST_*` clear in `level_reset` + `level_reset_new` +64 B; before: 8,252 B, 964 B free to `$E400` (C3-7)). Earlier: 8,369 B, 847 B free to `$E400` (B12, measured: 8,305 → 8,369 = +64 incl. the `dg_bad` ALIGN 64 shift: `glow_ids` 8 + the `.gate` stamp in `build_room_map` ~42; the D1 decor rework before it was not itemised here). Before: 7,744 B, 1,472 B free (B11/B14 +44 (measured: 7,700 → 7,744, incl. `level_reset` clearing `CLIMB_BLK_N`; the row's older figures below were not re-measured): the B14 yield — on the shaft col the facing side instead of the roomier one, the flyer's vertical fallback that must end off the path; B3B-13 −196: `show_impact_msg` + `kind_name` / `str_cat` + the 7 combat words → low RAM / the text block, `str_descend`, the room-D chest decor entries out; + `sel_nm_knight` / `sel_nm_wizard` 14 (select-screen names, ROM charset) in; before: B3B-12 +469 incl. the review fixes: `level_card` + strings, `level_new` (seed + level_gen retry), `level_populate` / `pop_one` + `pop_kinds` / `pop_cols` (the stand-in population), `level_reset` / `spawn_one` factored out of `new_game`; before: 7,157 B, 2,059 free; B3B-R2 +1,558: `src/turn3.asm`, the monster phase / attacks / potions moved out of bank 2, see "Cold code placement"; before R2: 5,599 B, 3,617 free; B3B-10 −1: `build_room_map` picks + empties the decor list of its map page (`dg_dst`), the deriver's ROOM_MAP-only test gone; the B3B-9 deriver `decor_room` (`src/decor_gen.asm`, ~1.0 KB incl. its 56 object records) came with the B3B-9 merge; B3B-11b −2,534: font, icons, hot image, `tiles_common` / ornament / zap data out to bank-1 `vdata`, `panel_boot` builds the planar font, `pblit` / `init_tiles` read through `copy_virt3`; before: 8,134 B, 1,082 free after the B3B-9 merge; B3B-11 +2,687: `src/panel.asm` cold code 437 (`panel_boot`, `panel_init` / `panel_flush`, `pblit` / `glyph8` / `cell_bm`, bar tables), the 6×8 font 768 (`font6x8`, boot-copied to `FONT6`), the panel icons 774 (`panel_icons.asm`), the `HOT_COPY` image 708 (`panel_hot_img`, boot-copied); B3B-8 +1,149: `build_room_map` v2 524, `init_tiles` 39 + its cold data 370 (`tiles_common` 288, `orn_glyphs` 64, the zap glyphs 18), `proto_level` + its tables ~150, the scroll ornament hooks ~45, `decor_room` stub 1 (B3B-9: the real deriver); B3B-7 merge: `level_gen` / `level_start_x` ~1.7 KB; B3B-5 +22: `edge_init` + the `EDGE_TAB` / `JUMP_TURN` init in `new_game`; raw: 515 + 1,760 = 2,275, 6,941 free before B3B-5; A7 review: + `new_game`/`init_ent_common`/`spawn_tab` and the follower selection / arrival conflicts, 794 B, out of bank 2). ASSERT `bank3_end <= AY_RESERVE` | tape block 4 / .sna |
| 3 | **AY player slot** `AY_RESERVE..$FFFF` (A8; **D3-0: 4 KB** = 4,096 B at `$F000`, user 2026-10-06, game.md §11.2; was 7 KB `$E400`, before that 8 KB `$E000`): `ay_code..ay_code_end` (`src/ay.asm`), entry `AY_PLAY` = `AY_RESERVE`. Today the silent stub `ay_play` (37 B: `AY_CALLS` += 1, R7 = `$3F`, R8-R10 = 0) | `AY_LEN` 37 B, 4,059 B free; ASSERT `ay_code_end <= $10000` | tape block 5 (headerless, `start` `.ay`) / .sna |
| 0 | **text block** (D3-TX; B3B-13 format, "Text" below) `text_img..text_img_end` = `TEXT_ADDR` `$C000` .. `POOL_START` (`TEXT_LEN` = `TEXT_PACKED`; ASSERTed below the `tap_loader` scratch `$E000`). The pool's bank-0 part starts at `POOL_START` (`alloc_reset`), so the pool never overwrites it | D3-2 strings: 198 strings, 82 tokens, **2,684 B** (`$C000..$CA7B`, pool from `$CA7C`) | tape block 8 (headerless, `start` `.txt`) / .sna |
| 0, 4, 6 | **pre-shift pool**: every frame variant (facing × shift), boot-generated by a bump allocator (no variant straddles a bank); bank 0 from `POOL_START` (D3-TX), banks 4 / 6 from `$C000` | need **44,096** of `POOL_CAP` 46,468 B (D3-4; was 40,096) (D3-TX: 49,152 − the text block; ASSERT `POOL_NEED <= POOL_CAP`) (monsters 22,688 + largest hero **with its class FX kind** 18,528 = the Knight 18,176 (D3-4: +3,648 for THROW / BOW / WHIRL / POWER_STRIKE) + `K_FXW` 352 (the Wizard: 13,184 + `K_FXM` 1,152 = 14,336); before D3-4 the largest hero 14,528 = the Knight (C3-7: +1,920 for JUMP1/2; the Wizard 9,728 → 13,184 with JUMP1/2 + STAFF_RAISE/SWING) + 2 select idles + straddle slack; ASSERTed) | `gen_kind` / `gen_frame` at boot and at hero select |
| 7 | **level tilesets** (B3B-8): slots 0–3 `TSET_LO` `$DB00..$DFFF`, slots 4–7 `TSET_HI` `$FAA0..$FF9F`, 320 B each (`tools/tiles_convert.py` → `assets/gfx/tiles/tilesets.asm`, slot format under "Bank-7 tileset slots") | 2 × 1,280 B (`TSET_HALF_LEN`) | tape blocks 6 / 7 (headerless, `start` `.t7lo` / `.t7hi`) / .sna |
| 7 | **screen 2** `$C000..$DAFF` (A7): the screen the ULA shows during play, a copy of the bank-5 screen kept by `present` / `present_full`; **attr shadow** `SHADOW_ATTR` `$F800..$FA3F` (the room's tile attrs in screen-attr layout, rows 0–17; high byte = screen attr + `$A0`; `$FA40..$FA9F` = 3 spare PROTO rows). **D3-S2 (2026-10-12): the bitmap shadow (`$E000..$F7FF`, R-1 erase lever since A7) is gone** — `erase_rect` redraws `TILE_GLYPHS[ROOM_MAP]` (+ the row-17 ornament) and takes attrs from the attr shadow (decor attr cycles) | 6,912 + 576 B; `$DB00..$DFFF` + `$FAA0..$FF9F` = the tilesets (row above) | screen 2: `present*`; attr shadow: `shadow_rect` / `shadow_room` on room entry, door planks, potion pickup; `decor_tick` steps |
| 7 | **bank-7 cold code** (D3-S2) `b7_code..b7_end` = `B7_CODE` `$E000` .. ≤ `B7_LIMIT` `$F800` (`src/bank7.asm`, entered only through `far7`; rules under "Cold code placement") | **3,134 B** (`B7_LEN`, `-DDEBUG_KIT=0`; 3,184 B with the kit; T7 review +50: the swallowed-tap latch `LOG_PDIR`, the Mage-aware pre-filter, `act_pend`'s wait-only drain; **D3-7 T7: +193** (3,084 B) = the named miss line / `ent_kind` / `miss_pre` (`abil_ammo7.asm`), the log drain (`end_turn` / `turn_input` / `act_pend`), `power_fire`'s `slot_live` + Power break, the `floor_pickup` pre-filter + `PD_AMMO`; T6: 2,891 B (2,941 kit), +318 = `abil_ammo7.asm` (`abil_ammo` / `ammo_fire` + the `msg_*` line composer) and the list-driven `floor_pickup` (replaces `potion_pickup` + the `ammo_pickup` stub); T5: 2,573 B (2,623 kit, measured at T7; was written 2,620), +546 = the power attacks (`abil_melee7.asm`), `potion_pickup` / `ic_quaff` / `debug_kit` from bank 3, `act_seq` / `act_begin_ok`; T4: 2,027; T1: 1,773, +157 = `act7.asm` + the fire stubs; T0: 1,616, +336 = `intent7.asm` + the D3-7 stubs; D3-S2: 1,280), **3,010 B free** (2,960 with the kit; T7 first pass: 3,060 / 3,010; T6: 3,253 / 3,203; T5: 3,571 / 3,521; T1: 4,371) to the attr shadow; ASSERT `b7_end <= B7_LIMIT` | tape block 6 together with tilesets 0–3 (`B7_TAPE_LEN` = `TSET_LO..b7_end`, `start` `.t7lo`) / .sna; `tests/gfx_integrity.py` asserts `B7_CODE..B7_LIMIT` == the .sna (no SMC, no data: the canary for the freed shadow) |

Sources are read only at generation time via `copy_virt` (virtual < `$C000` →
bank 1 at +`$4000`, else bank 3; a frame straddling `$C000` is split) — with
ZX0 only the raw items/tiles (`init_tiles`) go through `copy_virt` (A6: the
frame descriptors live in bank 5, `fdesc_tab`); the packed blocks are read by `dzx0_standard` straight from the
`$C000` window (a block never straddles virtual `$C000`: the tool pads it into
bank 3, ASSERTed). The pool
and attr-shadow banks are uncontended (0/4/6) resp. contended (7: erase attrs,
decor steps, the D3-S2 cold code).
`PORT_7FFD_SHADOW` always has bit 4 = 1 (48K ROM: charset, LD-BYTES).

Tape: BASIC `10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "<start>"`
(the 5 USR digits are emitted from the `start` label, today `29927` = `$74E7`).
ONE CODE block `lowram_code..code_end` (`TAPE_CODE_LEN` 12,521 B: bank-5
low-RAM cold block `$74E7..$7FFF` — code, then the frame descriptors
`fdesc_tab` as its tail — straight into the bank-2 image `$8000..code_end`;
the low-RAM block is ORGed to end exactly at `$8000` so there is no gap, and
`start` is its first byte: `ASSERT start == lowram_code`). **A6 layout
decision:** the descriptors are placed INSIDE the cold block (after the code)
rather than below `lowram_code`, so the tape stays BASIC + one CODE block +
two headerless blocks, the USR target stays the block's first byte, and the
block simply grows downward as frames are added (the fit ASSERT reserves the
growth to `FRT_MAX`). Then six
**headerless** blocks (flag `$FF`) that `start` loads with ROM `LD-BYTES`
(each with its own rewind-and-retry loop) before falling into `boot`: bank 1
(`SRC_LEN_LO`), bank 3 from `$C000` (`BANK3_LEN` = source tail + bank-3 cold
code) and (A8) bank 3 from `AY_RESERVE` (`AY_LEN`: the AY slot, a separate
block so the gap below it is not on tape), (B3B-8) bank 7 from `TSET_LO` and from
`TSET_HI` (`TSET_HALF_LEN` 1,280 B each: the level tilesets; two blocks so the
screen-2 / attr-shadow gap between them is not on tape; **D3-S2: the `TSET_LO`
block runs on through the bank-7 cold code**, `B7_TAPE_LEN` = 1,280 + `B7_LEN`;
`#50` checks it after a real tape load), (D3-TX) bank 0 from
`TEXT_ADDR` (`TEXT_LEN`: the text block; `check_paging`'s bank-0 probe byte,
written before it, is overwritten). Nothing in bank 7 is live
while `start` runs: screen 2 is not displayed (`$7FFD` bit 3 = 0 from BASIC),
the attr shadow / screen 2 are written only after `boot`, and the 128 editor's
bank-7 workspace is abandoned with BASIC (PROTO never returns to it). The
`.sna` enters at `boot` (all banks preloaded). `tests/game.py` #50 checks bank
1, bank 3 (whole `BANK3_LEN`), the AY slot (`AY_LEN`), both bank-7 tileset
blocks, the bank-0 text block (D3-TX) and the low-RAM cold block byte-equal to the `.sna` after a real tape
load, and IM 2 installed.

### Sprite sources (ZX0, A5; descriptors moved out in A6)

Generated before every build by `tools/zx0_sources.py` →
`build/zx0/sprites_zx0.asm` (gitignored, deterministic; needs `tools/bin/zx0`
from `tools/setup_zx0.sh`, else it stops with that hint). Layout, in order, at
virtual `$8000` (`sprite_src`):

| Part | Contents | Size (measured) |
|------|----------|-----------------|
| ~~raw items + tiles~~ | B3B-13: no longer emitted (nothing at runtime read the `item_*` / `tiles_*` data since B3B-8; the tools read the `.asm` files from disk) | 0 B (was 265) |
| packed blocks `zblk_0..zblk_31` | per kind (D3-4: the FRM kind argument, not the name prefix — the FX kinds mix prefixes), in `src/frames.asm` FRM (= fid = `gen_kind`) order, 1–4 consecutive frames of ONE kind, raw ≤ `GEN_SCRATCH_LEN` 1,536 B; each one ZX0 v2 standard forward stream. Partition per kind = fewest packed bytes (DP over 1..4-frame splits) | 101 frames, raw 20,480 → **8,908 B (2.30×)** (D3-4: +4 Knight + 23 FX frames, +1,322 B; C3-7: 74 / 7,586; was 68 / 6,682) |
| per-frame EQUs (A6: no bytes) | `nm EQU zblk_N` (its block = `FD_BLK`), `nm_zoff EQU` raw offset in the block (`FD_FRM` = `GEN_SCRATCH + nm_zoff`); plus `nm_w/h/cols/ax/ay` and `nm_len` = raw pixel bytes (cols·H·2, no ATTR byte). Folded into the bank-5 `fdesc_tab` by the FRM list (A5 had 4-B banked descriptors here) | 0 B |

Build-time metadata per block (EQUs, in the `.sym`): `zblk_N_raw`,
`zblk_N_packed`, `zblk_N_first`, `zblk_N_n`; totals `ZX0_BLOCKS`, `ZX0_FRAMES`,
`ZX0_PACKED_RAW`, `ZX0_PACKED_TOTAL`, `ZX0_RAW_SRC_TOTAL` (18,867 = what the
raw build assembles; the per-kind `index.asm` tables `<kind>_frames/_meta/
_flags`, unread by the engine, are not emitted). Total 8,908 vs 21,658 B (D3-4); C3-7: 7,586 vs 18,867 B
(C3-7; B3B-13 6,682, was 6,947 with the raw items / tiles): **freed 11,281 B**. The packer parses the frame
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
`GEN_SRC` stays as the `vdata` staging buffer (`panel_boot`, `pblit`). Decompressor =
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
| `present` (gfx.asm) | `tick_work`, before render (probe `probe_presented` after it) | flushes `HUD4_PW` (B3B-11: text rows 20..23) into the mask, copies every marked cell from `PRES_RMIN` down, clears the mask; ~50 T when idle; A7b: a full mask byte (8 cells, HUD text) goes by LDI lines (`.full8`, ~1.5k vs ~2.1k T) except cols 24-31 of a third's last char row (low byte `$F8`: LDI would carry into H) |
| panel items (B3B-11, `panel.asm` / `panel2.asm`; D3-0: `draw_zap` gone) | during the tick | log rows 22/23 → `HUD4_EXT` (ink extent, cols 0..EXT−1) / `HUD4_PW` (cols to copy) by `item_log` / `log_scroll`; HP, potion slot, depth → `pmark_rect` of their cells. (A7's `HUD_EXT`/`HUD_PW`, `hud_track`, `clear_row`, `hud_clear_mark` are gone) |
| `present_full` (lowram.asm) | `start_game`; end of `do_exit` | whole screen bank 5 → screen 2 (LDIR 6,912 B), mask + `HUD4_PW` cleared, show bank 7 |
| `show_bank5` / `set_screen` (lowram.asm) | `enter_select`; `do_exit` before the scroll | display bank 5 (they draw there) |
| `vis_reset` / `vis_room_sync` (lowram.asm) | `new_game` (tail) / `do_exit` after arrival | **the render-state resync contract** (B7, B7b): render runs first in a tick from the previous `anim_tick`'s `N_VIS`/`N_FID`/`RLIST`, so EVERY path that rewrites the entity table (`new_game`; Stage 3B level change / stairs) must end with `vis_reset` (every slot hidden), and every path that changes `CUR_ROOM` with slots kept (`do_exit`) with `vis_room_sync` (slots not live in `CUR_ROOM` hidden; the hero keeps its last frame). Both rebuild `RLIST` (`RLIST_N`) from the slots still visible or drawn. B7b (A7 review): a new game after death drew the dead game's slots and the hero with the old hero's frame id; `tests/game.py` #54 |

Invariants (asserted): at `probe_presented` screen 2 == the bank-5 screen
(`tests/flicker.py` and `tests/game.py` #53 — staff melee (D3-0; was the zap), potion pickup, quaff —
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
| player slot `AY_PLAY` | bank 3 `$F000..$FFFF` (4 KB, D3-0; was 7 KB at `$E400`) | the user-approved AY reserve (game.md §11.2, user 2026-10-06); bank 3 is contended, but the ISR runs at the frame start (top border), so its fetches are not delayed in practice |
| `SYS_FRAMES` | `$5C78` (3 B) | unchanged: the tick pacing (`wait_tick`, `resync_tick`, `menu_frame`, `start_game`) reads its low byte |

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

Hot (per-tick) code stays in bank 2 (uncontended). Cold code lives in
contended places, chosen by whether it pages `$C000` (D3-S2: + bank 7, the
per-turn / per-event logic that needs bank 2's helpers but no other `$C000`
bank):

| Where | Why | What |
|-------|-----|------|
| bank 5 low RAM `lowram_code..$7FFF` (`src/lowram.asm`) | always mapped: may page any bank through `$C000` | `start`, `boot`, `check_paging`, (A8) `isr_install` + `isr_image` (the ISR's load image, copied to `ISR_ADDR`), `start_game`, `init_kbd_mirror`, `sel_tab`, the generator (`pool_banks`, `alloc*`, `build_bitrev`, `copy_virt`, `gen_kind/frame/facing/variant`, `mirror_src`, `mul8`, `frt_ptr`, `sel_frt_copy`), (A7) `set_screen` / `show_bank5` / `present_full` / `hud_clear_mark` / `vis_reset` / `vis_room_sync`, (B3B-8) the room-entry ends of the bank-3 builder: `build_room` (far entry, A = room / H = map page), `room_show` (build + `draw_room` + ornament on screen and shadow), `room_shadow` (do_exit), `orn_row` / `orn_cells` (row-17 ornament; pages nothing, so the bank-3 scrolls call it), `level_load_tiles` + `theme_ids` + `chest_glyphs` (pages bank 7), the B3B-5 doors / falls / jump, and (A6) the frame descriptors `fdesc_tab` as the block's tail. B3B-8 moved `build_room_map` (v1, 254 B) and `init_tiles` + its stand-in glyphs / `tile_attr_src` / `tile_src_tab` / `bg_tiles` out (to bank 3, rewritten) |
| bank 3 after the source tail, `bank3_code..bank3_end` (`src/bank3.asm`) | needs no other `$C000` bank while running | (C3-6: the hero select `sel_run` became the bank-1 menu, the transition scrolls and the DEPTH card moved to bank 1 — `menu1.asm` / `scroll1.asm`); (A7 review) `new_game` + `init_ent_common` + `spawn_tab` (far3 from `start_game`), `follow_select` + `dest_counts` + `place_follower` and `arrival_conflicts` (far3 from `do_exit`) — bank-2 queries + `vis_reset` only; (B3B-7) `level_gen` / `level_start_x`; (B3B-8) `build_room_map` v2 (far3 via lowram `build_room`; bank-2 helpers `room_desc` / `seg_storey` / `map_cell` / `storey_row` only), `decor_room` (B3B-9 decor deriver, `src/decor_gen.asm`; contract under "As built in B3B-9 / B3B-10"), `proto_level` + `proto_hdr` / `proto_floor` / `proto_rooms` / `proto_decor` (rooms A–D as a level state, from `new_game`), `init_tiles` (boot, far3; B3B-11b: its cold data `tiles_common` (ids 0..31), `orn_glyphs` and the PROTO zap glyphs (`MODULE b3fx`) now sit in bank-1 `vdata` and are read through `copy_virt3`), (B3B-11) `panel_boot` / `panel_init` / `panel_flush` / `pblit` (sources from `vdata` via `copy_virt3` → `GEN_SRC`); the scrolls call `orn_cells` for the entering row-17 cells; (B3B-R2, `src/turn3.asm`, once-per-turn / per-event logic, ZX0 build only — the raw A/B build assembles it into bank 2) `resolve_monsters` (far3 from `read_turn_input`: ONE bank switch per turn) (+ bank-2 `cache_player`), `ai_monster`, `nearest_ladder`, `dx_to_player`, `attack_if_reach`, `ai_flyer`, `clamp_band`, `materialise`; `do_attack` + `set_reaction_at` (far3 from `try_horizontal`, direct from `attack_if_reach`; D3-6a: `do_attack` runs on `hit_roll` / `deal_hit`, `src/combat3.asm`, see "3D contracts"); (D3-6b) `proj_fire` (`src/proj3.asm`; called from bank-3 cast code, D3-7); (`show_impact_msg` + `kind_name` / `str_cat`: B3B-13 → low RAM, called directly from `anim_tick`); (`potion_pickup` and `try_quaff`: D3-7 T5 → bank 7, for bank-3 room); (D3-7) `abil_load` (`src/rank3.asm`, far3 from `intent7` `ic_disp`: A = `ABL_*` → `ABIL_DESC` = the `ab_def` row + the rank / ammo row, L = `ABF_*` flags, B = `ABL_*`); (D3-7 T4) `proj_rel` (`rank3.asm`, far3 from bank-7 `spell_fire`: A = `ABL_*`, DE = rank row → `proj_fire` HL = DE, E = 0); (D3-7 T5) `melee_hit` (`rank3.asm`, far3 from bank-7 `melee_strike`: one Power Strike / Whirlwind blow, A = target slot, `ABIL_DESC` loaded → L = HP lost, H = 1 hit; `hit_roll` + `deal_hit`); (B3B-13: every message string is a TX_* token stream in the bank-1 text block; `potion_pickup` / `panel_init` call lowram `msg_push`, which re-pages the caller's bank). The bank-2 helpers they call (`try_step` / `try_step_face` / `cork_check` / `flyer_lcost` / `box_free` / `box_vs_ix` / `find_target` / `cache_player` stay: `try_step` and `cache_player` are also called by a `tests/world.py` unit stub with any bank paged) page nothing, except `try_step` → `mon_door` → `door_open` → `door_paint` → `shadow_rect`: `door_paint` (lowram) now saves `PORT_7FFD_SHADOW` and `restore_page`s after it (+8 B) |
| **bank 7** `b7_code..b7_end` (`$E000..`, `src/bank7.asm`; D3-S2) | per-turn / per-event, needs no other `$C000` bank while running; may call helpers that leave bank 7 paged (`erase_rect`, `shadow_rect`, `room_shadow`, `present_full`, `level_enter`) | entered only via **`far7`** (`ld c, BANK_COLD7` → `farb`): `turn_input` (from bank-2 `read_turn_input`, the budget probe stays there) → `try_player_turn` / `tpt_intent` / `try_climb` / `try_horizontal` / `exit_h` / `ladder_exists` / `find_target` (D3-7 T0: `find_target_far` gone — its only caller `ic_melee` is bank 7 now); `end_turn` (play_loop: `turn_done` CF → far7) + `do_exit` + `hide_sprites`; `pause_run7` (bank-2 `pause_hook` stub); `intent_icon7` (intent_tick's ICON MODE branch; D, E pass in). **D3-7 T0:** the C3-2 icon logic `src/intent7.asm` (was bank-3 `intent3.asm`): `use_icon` (plain call from `tpt_intent`; the SA_* dispatch is a cp chain — no data in bank 7), `cursor_step` (plain call from `intent_icon7`), `sel_key` (far7 from bank-2 `intent_tick`), `hero_st_init` (far7 from bank-3 `new_game`); bank-3 targets by far3: `do_attack`, `abil_load` (`try_quaff`: D3-7 T5 → `ic_quaff`, this bank); the ability entries `abil_spell` / `abil_melee` / `abil_ammo` (`abil_spell7.asm` / `abil_melee7.asm` / `abil_ammo7.asm`, chosen by `ABIL_DESC`'s `ABF_MELEE` / `ABF_AMMO` / else; In IX = hero, B = `ABL_*`; Out L = 1 turn / 0), `melee_bonk` (the staff-bonk slot after `ic_melee`'s blow), `ammo_pickup` (`pickup7.asm`, from `end_turn` after `potion_pickup`; **T6: both replaced by `floor_pickup`**) — T0 stubs (L = 0 / `ret`), T1 implements them. **D3-7 T1:** `src/act7.asm` — `act_begin` (plain call from the ability accept), `act_pend` (far7 from bank-2 `pend_far`, the `anim_gate` hook: the release + the deferred monster phase, far3 `resolve_monsters`), `act_fire` → `spell_fire` / `power_fire` / `ammo_fire` (stubs, L = 1, in the `abil_*7.asm` files); contract under "Projectiles". **D3-7 T4:** `abil_spell` / `spell_fire` (+ `spell_row`) and `melee_bonk` implemented (bank-3 shim `proj_rel`, `rank3.asm`); contract under "Projectiles". **D3-7 T5:** `abil_melee` / `melee_scan` / `mask_hostile` / `power_fire` / `melee_strike` / `imp_fx` / `front_cell` (`abil_melee7.asm`; bank-3 shim `melee_hit`), `act_begin_ok` / `act_seq` (`act7.asm`); moved in from bank 3: `potion_pickup` (`pickup7.asm`, plain call from `end_turn`; its tail `jp shadow_rect` leaves bank 7 paged: allowed; T6: now `floor_pickup` → `ap_stamp`'s tail, the same rule), `try_quaff` (= `intent7.asm` `ic_quaff`, `ic_potion`'s tail), `debug_kit` (`intent7.asm`, `hero_st_init`'s tail; far3 `rank_sync`). Moved 2026-10-12 from bank 2 (`main.asm`, `logic.asm`, `anim.asm`, `io.asm`); `clear_screen` / `print_char` / `print_str` went to bank-5 low RAM |

Bank-3 code is entered only via `far3`, bank-1 UI code (C3-0) only via
`far1`, bank-7 code (D3-S2) only via `far7` — all `ld c, bank` in front of **`farb`** (bank 2, `gfx.asm`; far3
+7 T, far1 +19 T over the old far3): HL = target, A = argument, C = bank;
saves `PORT_7FFD_SHADOW`, pages bank C (`page_bank`: bit 4 = 1, shadow
before `OUT`), calls, then `restore_page` writes the saved value back
(shadow first, then `OUT`); BC/DE/HL/IX of the target pass through; far
calls nest. (C3-0: +5 B in bank 2; far3 keeps its name so no caller moved.) Bank-3
code must never page `$C000` itself; the select screen blits through
`blit_keep` (bank 2), which re-pages the caller's bank after the pool blit.
`enter_select` (bank 2) = `show_bank5`, `far1 menu_run` (C3-6) → `jp start_game`
(bank 5). A7: the scrolls and the select screen keep drawing on the `$4000`
screen, which is the one displayed while they run (`show_bank5` in
`enter_select` / `do_exit`); `start_game` and the end of `do_exit` copy it
to screen 2 and show bank 7 (`present_full`).

B3B-R2 cost (turn3 in bank 3, `tests/budget.py` heavy, the same worst
input tick, hero + 4 monsters): `resolve_monsters` 25,181 → 27,938 T,
`materialise` 2,115 → 3,142, `try_player_turn` 10,672 → 11,109; the tick
116,235 → 120,456 T (+4.2k: one far3 ~220 T, the rest is ULA contention on
the bank-3 code fetches). Mix worst 111,466 → 113,283 T; flicker a/b/c
121,144 / 60,307 / 98,595 T, 0 flicker / tear events, 0 overruns (cap 126k).
If the input tick ever needs it back: `materialise` (~50 B) in bank 2
saves ~1k T.

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
| `$8000..$A5CF` | `image_start`…`code_end` | HOT code + static tables (**D3-S2: `$8000..$A0CF`, 8,400 B; headroom 1,328 B to `FRT` + 249 B pad = 1,577 B** (was 48 + 196): −1,280 B to bank 7 (`bank7.asm`: the player turn, `end_turn` / `do_exit` / `hide_sprites`, `pause_hook`'s body, intent_tick's ICON MODE branch), −96 B to low RAM (`clear_screen`, `print_char`, `print_str`), +~25 B stubs / `far7`, Part 1 (no bitmap shadow) +11 B; `kind_tab` `$A400` → `$9F00`) (8,912 B incl. the pad, C3-3; 8,656 B, C3-2; 8,144 B, C3-1; 7,888 B, B3B-13; B3B-R2 8,144 B; B3B-10 9,680 B; incl. the ALIGN pad + the 16-B `dt_attr_tab` and the 64-B `tile_flags` before `kind_tab`; `ASSERT code_end <= FRT`). **Headroom (D3-5, build DISPLAY): 48 B to `FRT` + 174 B pad** (D3-5 +899 B: `fx.asm`, `kind_tab` `$A000` → `$A400`; "3D contracts"). Before: **(D3-0): 1,072 B to `FRT` + 108 B pad** (D3-0 −256 B code: the zap (`draw_zap` / `zap_covered` / `draw_glyph` / `dt_zap` / the anim + hide paths, ~250 B) out, `kind_tab` `$A100` → `$A000`). Before: **(C3-2b; + main's B12 merge, see the build DISPLAY): 816 B to `FRT` + 166 B pad = 982 B** (C3-2b: the ICON MODE `intent_tick` / `tpt_intent` +~250 B, paid by moving the icon state / drawing — `slot_act_tab` … `icon_state`, `slot_want`, `item_icons`, `sel_paint`, `lvl_draw`, `pot_slot` — to bank 3 (`icons3.asm`, entered by `item_icons_far` → far3); C3-3 +362 B: `icons.asm` — `slot_act_tab` / `slot_act` / `abil_rank` moved from bank 3, `icon_state`, `icon_poll` + `icon_sig`, `item_icons`, `sel_paint`, `lvl_draw`, `panel_more`, `print6x`; old `item_icons` / `pot_col` out; `kind_tab` → `$A100`. C3-2 + B11/B14 merge: 1,297 B (B11 +11 B; C3-2 alone: 1,308 B) (C3-2 +391 B: `intent_tick` + `fire_used` / `bag_msg` / `pause_hook` ~190, `tpt_intent` ~110, the `legacy_input` gates in `input_tick` / `sample_input` / `read_turn_input` / `try_player_turn` ~40, `SC_ENTER` ~6; `kind_tab` moved `$9E00` → `$A000`. C3-1: 1,699 B (C3-1 +154 B: `input_tick`, `read_stick` / `stick_tab` + the Sinclair presets (20 B), `sample_input` on `STICK` + `PLAYER_SC`; `kind_tab` moved `$9D00` → `$9E00`. C3-0: 1,853 B (C3-0 +5 B: `farb` / `far1` / `far3`, `kind_tab` stays at `$9D00`; B3B-13: 1,840 + 24 = 1,864 B; B3B-13 −151 B net: the strings `str_found/quaff/died/win/welcome` + `kind_names` / names ~160, the PROTO chest win in `end_turn` ~35 out; `tk_get` 44 + `print6t` 21 in, `item_log` → `print6t`; `kind_tab` moved down to `$9D00`, read from the `.sym`. Before: B3B-12: 1,584 B to `FRT` + 129 B pad = 1,713 B; B3B-12 +32 B: `try_climb` `EX_LEVEL` (only at `RD_EXITCOL` with `LF_GRATE_OPEN`), the `do_exit` → `level_descend` dispatch, the PROTO win gated on `LVL_DEPTH` 0; B3B-R2: 1,745 B) for code/static tables (B3B-R2 −1,538 B net: `src/turn3.asm` (monster phase, attacks, potions, impact messages; 1,558 B) out to bank 3, + the far3 call sites (5 sites, +20 B); `kind_tab` moved to `$9E00`. (The raw A/B build that kept turn3 in bank 2 was retired in B3B-12, manager decision.) Before: B3B-10: 48 B to `FRT` + 159 B pad = 207 B (B3B-10 +355 B: `decor.asm` 352 (`decor_tick` with the step inlined, `dt_zap`) + the `play_loop` call, `dt_attr_tab` 16 in the pad; `kind_tab` moved one page up to `$A400`. Before: B3B-11b: 560 B to `FRT` + 18 B pad = 578 B (B3B-11b +74 B: `item_icons` + `pot_col` moved here from `HOT_COPY` ~65, `print6g` / `p6_inline` (the print6 getter interface) ~55, `item_log` one item, no chunk state −~45; B3B-11: 652 B; B3B-11 +82 B net: `panel2.asm` 435 (`item_log` 121, `log_scroll` 183, `bars_draw` 96, `num2` 35), `str_cat` / `show_impact_msg` composer, the `panel_tick` call; out: the A7 HUD (`hud_status` / `hud_room` / `msg_begin`, `clear_row` 155, `hud_track`, `print_char_hud`, `print_dec`, 3 strings) ~350; the rest of the panel's hot code sits in `HOT_COPY`. Before: B3B-8: 560 B to `FRT` + 174 B pad = 734 B; B3B-8 −69 B net: the PROTO `room_tab` + 4 room descriptors (~105 B, now bank-3 `proto_rooms`) and the old `room_desc` / `exit_h` / list loops out; `seg_storey` 13, `room_side` 36, `try_climb` `.vexit` 20, `potion_pickup` on `FLOOR_LIST`, the `hud_room` letter 7 in. Before: B3B-5 + review + B10: 560 + 105 = 665 B; B3B-5 used 402 B of the 1,067 (B10 hardening: flyer box row clamp 6): `tile_flags` 64, `cell_addr` / `cell_blocked` / `lead_cell` / `desc_byte` 57, `box_solid` (flyer steps, jump swept box) 34, `LOCK_SHOWN` clear 3, terrain + pit + door hooks in `try_horizontal` / `try_step` ~85, jump chord + key C in `try_player_turn` / `sample_input` ~30, `M_FALL` / `M_JUMP` anim 83 + `jump_dy` 12, room descriptors +16; the rest of B3B-5 is bank-5 low RAM. Before: A7b rebased on the B8 rev 816 B to `FRT` + 251 B pad = 1,067 B; A7 review: 993 B; A7b: code −78 B net — the one-pass record render (−138 B) and the blit rewrite (−46 B) pay for the erase row stepping (+26), `stamp_rect` / the 16-bit blit entry patch (+19) and the present `.full8` path (+61); A6: 677 B; A7: 111 B after present / pmark / HUD tracking / in-place rect dedupe / paging +566 B; the review moved 1,062 B of cold code out — `build_room_map` 254 B to bank-5 low RAM, `new_game` + `init_ent_common` + `spawn_tab` and follower selection + arrival conflicts 794 B to bank 3, net of the `far3` call sites — and added the B8 flyer ladder-end rule +159 B and the bank-2 `map_cell` +21 B; the 2026-10-02 cross-or-leave flyer rule + blocked-climb wait: +4 B net), plus the 1,536 B free runtime RAM `$B200..$B7FF` below. Code bytes `$8000..kind_tab_pad` 7,439 (B3B-R2; B3B-10 8,977; B3B-11b 8,622; B3B-11 8,548; B3B-8 8,466; A7 review 8,271; A7 9,153; A6 8,587). `kind_tab` page-aligned at `$A400` (D3-5; D3-0 `$A000`; `$A100` C3-3; C3-2 `$A000`; C3-1 `$9E00`; B3B-13 `$9D00`; B3B-R2 `$9E00`; B3B-10 `$A400`, before `$A200`; moves with the code: tests read it from the `.sym`), **2 pages** (`KT_SIZE` `$200`): 13 parallel **32-B** kind arrays (`K_MAX` 32; ids 0..8 used, 2 = Rogue hole; **D3-4: ids 30 / 31 = the class FX kinds `K_FXW` / `K_FXM`, only their `KT_FID0` / `KT_FCNT` columns are set** — 3F's monster rows have ids 9..29) + `KT_MOD9`/`KT_DIV9` tables (n mod/div `STOREY_ROWS`, n = 0..23; B3B-3, were MOD7/DIV7 at the same offsets), `KT_END` `$1D0` → `$9DD0..$9DFF` 48 B spare in its page (resistances, 3F). No array crosses a page: `KFIELD` folds the page into `H`. `frame_tab` **4 B/fid** (`FT_COLS`, `FT_H`, `FT_OFFR`, `FT_OFFL`: only what the renderer reads; D3-4: 101 fids = 404 B). `far1` / `far3` / `farb` / `restore_page` / `blit_keep` / `enter_select`: the far-call trampolines (53 B, C3-0). |
| `$A600..$AFFF` | `FRT` | frame runtime table (A6: moved from `$B200`): 16 B/fid (4 variants × bank,lo,hi), **`FRT_MAX` 160** (101 used, D3-4; 74 at C3-7); `FRT = P_ENTITIES − FRT_MAX × 16` |
| `$B000..$B1FF` | `P_ENTITIES` | 16 slots × **32 B** (layout below); slot 0 = hero |
| `$B200..$B7FF` | `BANK2_FREE` | the vacated A5 `FRT` (1,536 B, runtime RAM, not in the image/tape; `BANK2_FREE_END` = `SLOTREC`). **B3B-1 (D8): fully reserved; B3B-11 / B3B-11b use it** — **`FONT6` `$B200..$B5FF` = the PLANAR 6×8 font** (B3B-11b, for the quad printer): line *l* of char *c* (32..127) at `FONT6 + (l>>1)*256 + c + (l&1)*FONT6_WB` (`FONT6_WB` 96): 4 pages, even lines in window A (offsets 32..127), odd lines in window B (128..223); built at boot by `panel_boot` from the char-major `font6x8` (bank-1 `vdata`, via `GEN_SRC`), glyph bits 1..0 masked off. Free holes inside the planes: offsets 0..31 / 224..255 of each page (`$B200..$B21F`, `$B2E0..$B31F`, `$B3E0..$B41F`, `$B4E0..$B51F`, 32 + 3 × 64 B); (B3B-13..C3-7: `ZAP_GLYPHS` `$B200..$B20F`, gone with the zap in D3-0.) **D3-0: the holes hold the 3D runtime state** — see "3D contracts (D3-0)": `FXREC` `$B2E0..$B30F`, `ST_FLAGS` `$B310..$B31F`, `ST_T1` / `ST_T2` / `ST_X` `$B3E0..$B40F`, `FXQ` `$B410..$B41F`, `RANK_ROWS` `$B4E0..$B4FD`; free: `$B200..$B21F` (32 B), `$B4FE..$B51F` (34 B). **`HOT_COPY` `$B5E0..$B7FF`** (544 B, boot-copied hot code, risk R2): **`$B5E0..$B7D6` = the panel hot image (503 B, C3-3; was 515**: `print6` (quad printer, 4 SMC fetch sites + 8 SMC plane offsets) ~270, `log_push` / `log_push_end` / `log_drop`, `panel_tick` / `panel_step`, `item_hp`, `item_depth`), **41 B spare** (C3-3: `panel_step` polls through `icon_poll` and ends in `panel_more`, bank 2; ASSERT `HOT_COPY + PANEL_HOT_LEN <= HOT_COPY_END`; the build DISPLAY reports it). Labels in the `.sym` are the runtime addresses (`DISP`) |
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
| `$BC10` / `$BC11..$BC40` | `ANIM_N2` / `ANIM_LIST2` | B3B-10 (B3B-9 review): the decor list of a NEXT_MAP build (do_exit), same format as `ANIM_N` / `ANIM_LIST`; `room_shadow` copies the 49 B over them after the scroll. (Was the B3B-1 `OCC_MASK`, 72 B: dropped — `decor_tick` tests a due cell against the drawn footprints directly, see "As built in B3B-10") |
| `$BC41..$BC49` / `$BC4A..$BC50` / `$BC51..$BC5E` | `HERO3D` / `TURN_PEND` / — | **D3-0: `HERO3D`** (9 B: `MP_RG`, `HERO_RES` 3 B, `HERO_IMM`, `MP_SH`, `STAT_SH`, D3-6a `HERO_DEF`, `XP_UP`; "3D contracts (D3-0)"), **D3-7: the `TURN_PEND` block** (7 B: `TURN_PEND`, `ACT_ABL`, `ACT_AT`, `MON_AT`, `FX_DROP`, T7 `LOG_TURN` / `LOG_PDIR`), then spare (14 B; T6: 16 B; D3-0: 21 B; was 30 B spare, B3B-10: the `ANIM_RR` round-robin index dropped, unused — the per-entry `AL_PHASE` counters + per-tick caps need none) |
| `$BC5F` / `$BC60..$BC8F` | `ANIM_N` / `ANIM_LIST` | B3B-1 (D6; B3B-10: `ANIM_N` moved `$BC58` → `$BC5F` so count + list are one 49-B block): animated decor cells of the room in `ROOM_MAP`, 12 × 4 B (`AL_COL`, `AL_ROW`, `AL_TYPE`, `AL_PHASE`); filled by the decor deriver (B3B-9) or copied from `ANIM_LIST2`; stepped by `decor_tick` (B3B-10) |
| `$BC90..$BCBB` | `HERO_ST` | C3-0: the 3C hero / input state block (44 B, runtime RAM, `src/hero_defs.asm`; layout in "3C contracts"); full since C3-2 (`CUR_REP` .. `PAUSE_REQ`) |
| `$BCBC..$BCF3` | `ISR_ADDR` | A8 ISR, 56 B (`ISR_LEN`; 68 with `ISR_SAVE_ALT`, 42 with `ISR_ROM_CHAIN`; ASSERT end ≤ `ISR_ADDR_END` `$BD00`), copied from `isr_image` at boot; `$BCF4..$BCFF` spare |
| `$BD00..$BEFF` | — | stack, **768 B** (SP = `$BF00`, grows down to `STACK_BOTTOM $BD00`; A8: was 1 KB from `$BB00`; C3-1: `tests/world.py` W20 re-measures it: 40 B over boot, a generated D1 start and 53 random turns). **Measured max depth 40 B** (lowest byte touched `$BED8`; pattern-fill over boot, both hero starts, a room transition, the §8.2 walkthrough and both `budget.py` fights, ROM IM1 ISR included; tape path's `LD-BYTES` not covered, ~10 B). The A8 ISR adds 16 B (return address + 6 pairs) + the player's own depth to whatever is in use |
| `$BF00..$BFFF` | state block | below |

**Entity record** (32-B stride, `defs.asm`): `+0 KIND, +1 ROOM, +2 FLAGS
(1 ACTIVE, 2 PLAYER, 4 HOSTILE, 8 FACING_LEFT, 16 DYING, 32 WALKIN, 64 PENDING),
+3 X (body-left col), +4 Y (body-top row), +5 HP, +6 MAXHP, +7 AIDIR (±1 climb
dir), +8 POT (hero potions), +9 PX, +10 PY, +11 MODE, +12/13 SEQ ptr, +14 TMR,
+15 REACT, +16 REACTAT, +17 WPH, +18 FLT, +19 FLA, +20 MSG, +21 TGT, +22 HIT,
+23 spare (D3-0: was ZAP), +24 DVIS (bit0 drawn, bit3 facing), +25 DFID, +26 DFPX, +27 DFPY,
+28..31 drawn footprint col,row,cols,rows`. Hero HP/potions = `$B005`/`$B008`.

### Bank 5 low RAM (`$6000-$7FFF`, free after `CLEAR 24575`)

| Address | Symbol | Size | Contents |
|---------|--------|------|----------|
| `$6000` | `ROOM_MAP` | 672 | current room tile ids, 32 × `PLAY_ROWS` (B3B-3: rows 0–17 = 576 B used, `PLAY_CELLS`; 672-B buffer = `MAP_BUF_LEN`, page-aligned) |
| `$6300` | `NEXT_MAP` | 672 | destination room during a transition |
| `$6600` | `TILE_GLYPHS` | 512 | 8×8 tile glyphs, **64 ids** (A6), glyph = base + id·8; **512-aligned** so `tile_rect` forms it as `E = id·8`, `D = (base>>9) RL CF` (+8 T per cell vs 32 ids) |
| `$6800` | `BITREV_TAB` | 256 | bit-reverse table (mirroring, boot; page-aligned) |
| `$6900` | `TILE_ATTRS` | 64 | attr by tile id (one page: `ld h, TILE_ATTRS>>8`) |
| `$6940` | `GEN_SRC` | 512 | B3B-11b: `panel_boot` (font halves, 384 B) and `pblit` (one icon, <= 54 B) stage `vdata` here — boot / new game only, never during generation. C3-6: the pause overlay saves rows 7-9 here (`PAUSE_SAVE`, 864 B: it runs on into `GEN_MIR`) while paused |
| `$6B40` | `GEN_MIR` | 512 | generator: mirrored frame (`LOWRAM_END` = `LOWRAM_FREE_END` `$6D40`). D3-TX: its top 43 B `$6D15..$6D3F` = `TX_DEC` (`tx_dec`'s transient decode buffer, menu text) |
| `$6D40..$6E7F` | `LVL_STATE` | 320 | B3B-1: **3B level state** (header 16, `EDGE_TAB` 6 (+10 spare), `ROOM_DESC` 9 × 16, 16 spare, `FLOOR_LIST` 32 × 4) — byte layout under "3B contracts". Runtime only (not on tape). Written by `level_gen` (B3B-7) or, for the PROTO rooms A–D, by `proto_level` (B3B-8, from `new_game`) |
| `$6E80..$6EBF` | `ORN_GLYPHS` | 64 | B3B-1: row-17 ornament glyphs (8 × 8 B, game.md §3.3: not tile ids, same on every level). Here, not in bank 3, because `orn_cells` (also called from the scrolls) reads it with any bank paged. Filled at boot by `init_tiles` (bank 3, from `panel_orn.asm`). `LOWRAM_END_3B` = `LOWRAM_FREE_END` = `$6EC0` |
| `$6EC0..$6F31` | `LP_STATE` | 114 | **LP (game.md §9.4, plan task LP)**: the lazy-population level budget + `ROOM_VISITS` + 9 room records (102 B persistent + 12 B `lp_enter` scratch) — byte layout under "LP contracts". Runtime only. Written by `lp_budget` (level entry) / `lp_bank` / `lp_enter` (room changes). `LOWRAM_END_3B` = `LP_END` (`$6F32`): the test stubs moved up with it |
| `$6F32..$7160` | free | 559 | of which 295 B (D3-4, 101 frames) are kept for descriptor growth (below); **264 spare** (`LOWRAM_SPARE` DISPLAY; **D3-S2 −89 (from the measured 353): `clear_screen` / `print_char` / `print_str` moved here from bank 2**; **L2 engine −28: `pit_range` + `pit_w` reading `L2_PITW`, `jump_pit` on `pit_range`**; before: 400, measured after merging D3-4 + J1: **D3-4 −8 (`start_game` generates the class FX kind) + 101 frame descriptors; J1 −145: `try_jump` / `jump_pit`**; earlier history as before: LP −114 `LP_STATE`; D3-TX −55; B12 −21; C3-2 −1; B14 −175) |
| `$7161..$7FFF` | `lowram_code` (`start` first) | 3,743 | **cold block**, ends exactly at `$8000` (`src/lowram.asm`): code 3,238 B + 101 frame descriptors 505 B (D3-S2 +89 incl. the bitmap-shadow paths' removal: + `clear_screen` / `print_char` / `print_str`, − `room_show` / `room_shadow`'s shadow ornament; L2 engine +28: `pit_range` / `pit_w`; D3-4 +8: `start_game` → `gen_kind(HERO_KIND + K_FX_BASE)`; J1 +145: `try_jump` D 6 / 7 + `jump_pit` + `pit_w`; earlier: D3-TX `tx_dec` + `.txt`, B12 +21, B14 +175, C3-2 +1, C3-1 +33, C3-0 +3, B3B-13 +37) |
| inside the cold block | A5 `zx0_code..zx0_code_end` | 107 | `zx0_frame` 39 + `dzx0_standard` 68 (ASSERT ≤ `ZX0_BUDGET` 128) |
| `$6000..$65FF` (alias) | A5 `GEN_SCRATCH` | 1,536 | ZX0 unpack target **aliasing `ROOM_MAP`+`NEXT_MAP`** (ends exactly at `TILE_GLYPHS`, ASSERTed): the generator runs only at boot, hero start and (3F) level start, before the room map is built — never mid-room. Guard: `GEN_TRAP` (state block) counts `gen_frame` calls while `GAME_STATE` is PLAYING/TRANSITION; tests assert 0 |

Tile ids (A6): 0..31 = common/engine tiles (`TILE_COMMON`; B3B-8: `init_tiles`
(bank 3, boot) copies the B3B-2 `tiles_common` set — glyphs byte-identical to
the old stand-ins for every id the PROTO uses (`tools/tiles_convert.py`
`LIVE_UNCHANGED`, validated); B3B-13: ids 17/18 kept the set's `T_DRIP1/2`; D3-7 T6: they are `T_DAGGERS` / `T_ARROWS`, see the tile table; the
wizard zap glyphs went to `ZAP_GLYPHS` `$B200` until D3-0 removed the zap), **32..63 = per-level slots**
(game.md §1.2). **B3B-8 (built):** `level_load_tiles` (A = depth; 0 = PROTO)
pages bank 7 and copies the depth's slot: 32 glyphs → `TILE_LEVEL_GLYPHS`
(`TILE_GLYPHS + 256`, the second page), 32 attrs → `TILE_LEVEL_ATTRS`
(`TILE_ATTRS + 32`), 32 flags → `tile_flags + 32` (bank 2), then sets the
attrs of the common floor ids (`T_PLAT`, `T_WALLF`, `T_END_L/R`) to
`LVL_ATTR_FLOOR` and of the wall ids (`T_BRICK`, `T_WALL_DITHER/PATCH/FADE`,
`T_RUBBLE`) to `LVL_ATTR_WALL` (`theme_ids`); restores the caller's `$C000`
bank; 11.7k T worst (measured). Depth 0 (rooms A–D) = D1's slot (B3B-13: the
room-D chest stand-in over ids 32..35 and the PROTO chest win are gone).

Fit (ASSERTed: `lowram_code − (FRT_MAX − FDESC_COUNT) ×
FDESC_STRIDE ≥ LOWRAM_FREE_END`, and `fdesc_end == lowram_code_end`): 3,392
fixed buffers (incl. the 64-id tiles) + 384 B3B level state / ornament
(B3B-1: `LOWRAM_FREE_END` = `LOWRAM_END_3B`) + 2,949 cold block + 460 descriptor
growth to 160 frames = 7,185 of 8,192 B → **1,007 spare** (B3B-12; B3B-10: 1,115; B3B-11: 1,134; B3B-8: 1,066; B10: 391; B3B-5: 455; B3B-1: 1,426; before it 1,810; A8: 1,913; A7 review: 1,921; A7: 2,216; A6: 2,409; A5: 1,308 with
its 1,920 B ≤ 12-B descriptor reserve), room for the ~0.6 KB level state with
~1.3 KB margin. A separate 1.5 KB ZX0 scratch would now fit, but would eat
most of that margin — the alias stays. `$5B00-$5BFF` and `$5CC0-$5FFF` (~832 B after D3-6b PF_RAM $5E00..$5EFF, E: free once `boot` has
moved SP off the BASIC stack) are a further runtime-only (not tape-loadable)
reserve (B3B-11: `$5B00` = `LOG_TXT`; **D3-6b: `$5E00-$5EFF` = `PF_RAM`**, the
proj_fire scratch — never touched before `boot`). A8: after `boot` nothing uses the system variables but
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
| `$BF13` | `CUR_ROOM` | room id = 3×3 grid cell 0..8 (B3B-8; PROTO rooms A 0, B 1, D 3, C 4 — was 0..3 = A..D) |
| `$BF14` | `HERO_KIND` | 0 Knight, 1 Wizard (2 = retired Rogue: hole in the `K_*` ids) |
| `$BF15` | `POTIONS_TAKEN` | bitmask of taken potions by `FLOOR_LIST` entry index 0..7 (B3B-8; the PROTO potion ids 0..3 = entries 0..3) |
| `$BF16` | `INPUT_REPEAT` | 1 (default) held keys repeat; poke 0 = edge-triggered |
| `$BF17` | `ANIM_FREEZE` | poke 1: resting sprites hold IDLE frame 0 (goldens) |
| `$BF18` | `PORT_7FFD_SHADOW` | last `$7FFD` value. The ROM's own shadow `BANKM` (`$5B5C`) is deliberately left stale: PROTO never returns to 128 BASIC and never calls 128-ROM paging routines |
| `$BF19` | `OVERRUN_COUNT` | word: ticks whose work exceeded 2 frames |
| `$BF1B` / `$BF20` | `ANIM_TRACE_IDX` / `ANIM_TRACE` | 32-B ring of (slot, frame_id) per drawn-frame change |
| `$BF1C..$BF1F` | `LAST_TICK_FRAME`, `TURN_TICK`, `NEED_RELEASE`, `EXIT_KIND` | loop internals |
| `$BF40` | `BLIT_MISS` | count: stationary frame requested at an ungenerated shift (debug trap, expect 0) |
| `$BF41` | `GEN_OVERFLOW` | 1 if the pre-shift pool ran out (expect 0). An allocation ending exactly at `$10000` opens the next bank for the next one |
| `$BF42..$BF4F` | allocator, damage counts, exit dest/storey/col (`$BF48..$BF4B` spare since D3-0: were the zap overlay's `ZAP_T/ROW/COL/LEN`) | internals |
| `$BF55` | `DMG_OVERFLOW` | count: `DMG_LIST` (48) full → last rect = whole playfield, or `PEND_DMG` (4) full → last rect grows to the bounding box (expect 0; was the unused `MSG_DIRTY`) |
| `$BF80` | `CLIP_TRAP` | count: a blit would cross col 31 (not drawn) or a stamp was clamped at col 31 (debug trap, expect 0; was the unused `SEL_KEY`) |
| `$BF51..$BF92` | blit params, generator scratch, `CAND_LIST $BF60`, `CAND_GAP $BF70`, `TMP0..7 $BF83`, `ACT_SLOT $BF8B`, `PLAYER_DIR/DISC`, `ATK_PTR $BF8E`, `MON_SLOT`, `ANIM_SLOT`, `YIELD_FLAG` | internals |
| `$BF93` | `GEN_ZBLK` | word: virtual address of the ZX0 block now unpacked in `GEN_SCRATCH` (0 = none; cleared by `alloc_reset` / `alloc_restore`, A6) |
| `$BF95` | `PRES_ANY` | A7: 1 = `present` has work (a mask bit or a HUD width is pending) |
| `$BF96` | `DMG_PRES_N` | A7: `DMG_LIST` rects `pmark_dmg` marks (those before the overlap-repair pass) |
| `$BF97` | `PRES_RMIN` | A7: first marked row (`$FF` none): `present` starts its scan there |
| `$BF98` | `JUMP_ARC` | J1: the hero's jump arc, written by `try_jump`, read by `anim_entity.jump` only while `M_JUMP`: bits 0-4 `JA_N` airborne ticks n = 2·\|x_f − x\| (12 / 14; less when a wide pit cuts the arc), bit 6 `JA_D7_BIT` (arc shape N = 14), bit 7 `JA_FALL_BIT` (the jump ends in a pit fall: `E_Y` already on storey 1, the arc is drawn 72 px up, then `M_FALL`). Was `FLY_INBOX` (B8 flyer ladder-end rule, removed by J1) |
| `$BF9A` | `MENU_SPIN` | C3-6: word, busy-wait passes counted by the menu's frame wait (`menu_wait`); `new_game` adds it to `SYS_FRAMES` (+ R) for `MASTER_SEED` unless `seed_fixed` |
| `$BF9C` | `PAUSED` | C3-6: 1 while the pause overlay is up (test-observable) |
| `$BF9D` | `END_SHOWN` | C3-6: 1 = the death / win card is drawn, 2 = armed (all keys released once, C3-6b) (`end_screen`; cleared by `hero_st_init`) |
| `$BF9E` | `MENU_IN_SIG` | C3-6 review: the last input fold `menu_frame` saw (key-edge seed mixing) |
| `$BF9F` | — | spare |
| `$BF99` | `GEN_TRAP` | count (saturating): `gen_frame` ran while `GAME_STATE` = PLAYING/TRANSITION, i.e. while `GEN_SCRATCH` holds live room maps (debug trap, expect 0; `tests/game.py` #1/#40/#51) |
| `$BFA0` | `MSG_BUF` | 32 B: `show_impact_msg` / `impact_line` (B14: also the squeeze line) composes the impact line here (B3B-13: a token stream, pre + name + post, ≤ 31 B + 0 ASSERTed), then `log_push` copies it (B3B-11; tests use it as a stub result byte) |
| `$BFC0` | `TIMING_MARK` | spare |
| `$BFC2` | `AY_CALLS` | A8 word: `AY_PLAY` calls (the silent stub counts them; = frames since boot's `EI`). Test-observable |
| `$BFC4` | `JUMP_TURN` | B3B-5 word: the `TURN_COUNTER` value on which a jump is refused (= the turn after a jump; game.md §2.4 "not two turns in a row"); `$FFFF` = none (`new_game`) |
| `$BFC6` | `LOCK_SHOWN` | B3B-5: 1 = the locked-door message was printed for the key still held (once per press); `read_turn_input` clears it when no key is held |
| `$BFC7` | `CLIMB_BLK_ID` | B14: slot of the body that blocked the hero's last climb (`climb_blocked`) |
| `$BFC8` | `CLIMB_BLK_N` | B14: consecutive blocked climbs by `CLIMB_BLK_ID`; the 2nd = squeeze past (prototype §6.4 "B14 fix rules"). Cleared by `read_turn_input` after any other consumed turn (`CLIMB_BLK` = 0), by the squeeze and by `level_reset`. Test-observable |
| `$BFC9` | `PLAYER_SC` | C3-1 (`$BFC7` until the B14 merge): shortcut keys this sample (`sample_input`): bits 0-3 slot 1..10 (key 1..9, 0 = 10; lowest held wins; 0 = none; the selected Sinclair half of the number row is ignored), bit 6 `SC_INV` (I), bit 7 `SC_BREAK` (CAPS + SPACE). Test-observable |
| `$BFCA` | `LVL_SH` | C3-3: hero level digit last drawn ((31, 19); `$FF` = never) |
| `$BFCB` | `ICON_SIG` | C3-3: `icon_sig` (SEL_SLOT, daggers 0, bow ready) as last drawn — `icon_poll` compares it, not the 10 slot states (~0.15k T a step) |
| `$BFCC` | `ICON_MODE` | C3-2b: 1 = ICON MODE (↓+FIRE): play frozen in INPUT ticks (`anim_gate` / `decor_gate`), ←/→ move the cursor, FIRE uses, ↑ / ↓ / BREAK leave |
| `$BFCD` | `DN_T` | C3-2b: ticks ↓ alone has been held (`DN_DEFER` 3: the ICON MODE window; the wait / climb-down acts at 3) |
| `$BFCE` | `DN_COMMIT` | C3-2b: 1 = a ↓ released inside the window: `tpt_intent` acts on it once |
| `$BFCF` | `PRE_N` | C3-2b: `pre_get` state (the info line's `>` prefix in ICON MODE) |
| `$BFD0..$BFFF` | **3B sub-range** (`STATE_3B`, B3B-1) | `PANEL_DIRTY $BFD0` (D5 `PD_*` bits), **`EXIT_LOCK $BFD1`** (C3-2b: directions ignored until released after leaving ICON MODE; was spare), `HUD4_EXT $BFD2` (4 B) / `HUD4_PW $BFD6` (4 B): rows 20..23 (B3B-11: the successors of `HUD_EXT`/`HUD_PW`), `LOG_QN $BFDA` (pending messages), `PANEL_POT_SH $BFDB` (potions last drawn), `P_NUMBUF $BFDC` (3 B: number / depth text), **`FIRE_LOCK $BFDF`** (C3-2b review: FIRE masked after BREAK until FIRE is released; B3B-11b: was `P_LIM`), `LOG_Q $BFE0` (8 B: `LQ_RD` +0 oldest ring slot, `LQ_DROP` +1 dropped / replaced pushes (saturating, expect 0), +2..+7 spare — B3B-11b: no chunked-print state), `PANEL_HP_SH $BFE8` (2 B: hero HP, MAXHP last drawn, `$FF` = never; B3B-11b, was `$BFD1`), **`JOY_MIRROR $BFEA`** (C3-0, see "3C contracts"), `$BFEB..$BFFF` spare. Test-observable |
| `$BFC1` | `CLIMB_BLK` | 1 = this input's climb was blocked by an entity → `try_player_turn` makes it a WAIT (prototype §6.4, rule 2026-10-02); cleared at every `try_player_turn`. B14: also read by `cork_check` (the monster phase of that turn yields to the blocked climb, even from a standing hero; `climb_blocked` set the hero's `E_AIDIR` to the attempted dy) |

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
`fx_trk_erase.probe_ret` / `fx_blit.probe_ret` (D3-5) are `tests/flicker.py`'s
FX erase / draw probes (no code; `ANIM_SLOT` = 16 + track there).
`present.probe_row` (A = row being copied) / `present.probe_row_end` and
`probe_presented` (main.asm, after the tick-start present) (A7) are
`tests/flicker.py`'s present probes (no code).
`isr.done` (A8, `ISR_ADDR` space: after the ISR's restoring `OUT`, port ==
shadow) and `AY_PLAY` (bank 3, only ever reached from the ISR) are
`tests/game.py` #61's ISR probes.
D3-7 T1: `pend_far` (budget phase: `act_pend` + the deferred monster phase)
and `probe_act_fire` (a bank-2 `ret` that `act_pend` calls on the fire tick:
opens `tests/budget.py`'s "cast" class).
D3-S2: `read_turn_input` (budget phase) and `pause_hook` stay bank-2 stubs
(`ld hl` / `jp far7`) so no probe sits in bank-7 code; a PC breakpoint at
`$E000+` also fires in bank-3 / bank-1 code — `tests/game.py` #61 qualifies
its region checks with `RAM=7` (ZEsarUX condition). `GAME_PROFILE`'s
`try_player_turn` phase is now a bank-7 address (aliases possible: profiling
only).

Per-game vs since-boot observables: `new_game` resets `TICK_COUNTER`,
`ANIM_TRACE`/`_IDX`, `BLIT_MISS`, `DMG_OVERFLOW`, `CLIP_TRAP` (plus RNG/turns);
`OVERRUN_COUNT`, `GEN_OVERFLOW` and `GEN_TRAP` count since boot. Moving them is
free; removing them breaks `tests/game.py` / `tests/budget.py`.

## 3B contracts (B3B-1) — code against these symbols

> Source of truth: `src/level_defs.asm` (EQUs + ASSERTs only, INCLUDEd at the
> end of `defs.asm`; emits no bytes — the B3B-1 image is byte-identical to A8).
> Design refs: game.md §1.1–1.4, §2.1, §2.5, §3.3–3.5, §8.5, §9.1;
> concept-screen §3.1, §3.3, §5; plan.md "3B breakdown" D1–D10.

### Geometry (D3/D4) — permanent names; **B3B-3: the engine runs on them, the PROTO names are deleted**

| New | Value | Replaces |
|---|---|---|
| `STOREY_COUNT` / `STOREY_ROWS` / `STOREY_AIR` | 2 / 9 / 8 | `STOREYS` 3 / `STOREY_H` 7 (deleted) |
| `FLOOR_ROW0` / `FLOOR_ROW1` | 8 / 17 | — (storey `s`: air rows `9s..9s+7`, floor `9s+8`; `s` = 0 is the TOP storey) |
| `PLAY_ROWS` / `PLAY_CELLS` | 18 / 576 | `ROOM_ROWS` 21 / `ROOM_CELLS` 672 (deleted; the 672-B `ROOM_MAP`/`NEXT_MAP` buffers stay, `MAP_BUF_LEN`; ASSERT fits) |
| `PANEL_ROW` / `PANEL_ROWS` | 18 / 6 | `HUD_ROW` 21 (3 rows) |
| `ICON_ROW` 18, `INFO_ROW` 20, `STAT_ROW` 21, `LOG_ROW` 22 | | concept-screen §5 |
| `TEXT_ROW` / `TEXT_ROWS` | 20 / 4 | `HUD_ROW` / `HUD_ROWS` for present tracking (`HUD4_EXT` / `HUD4_PW`) |

MOD9/DIV9 (B3B-3, done): `KT_MOD9` / `KT_DIV9` at the old `KT_MOD7` / `KT_DIV7`
offsets `$1A0` / `$1B8` (n = 0..23); `kind_tab` `$1D0..$1FF` stays the 3F
resistance spare.

**As switched in B3B-3** (code against these; `tests/world.py` W0–W4):
- Storey `s`: air rows `9s..9s+7`, floor row `9s+8`; stands iff `(y+h) mod 9 == 8`
  (`is_standing`: `cp STOREY_AIR`); `storey_ref = min(1, (y+h) div 9)`; standing top
  `9s+8−h`; flyer band `9s..9s+8−h`, cruising row `9s+1`; potion / floor-item row
  `9s+7` (`storey_row`). `MUL_STOREY r` (defs.asm) = A × 9, 20 T.
- Ladder segment `{c,s}` (B3B-8: the 6 col bytes `RD_UPCOL..RD_LAD2` of `ROOM_DESC`, `seg_storey`): rows `9s−1..9s+7`
  clipped to 0–17: `{c,0}` up-exit (rows 0–7), `{c,1}` internal (hole row 8),
  `{c,2}` down-exit hole (row 17). A climb between storeys = 9 turns. The
  climbers' "shaft clear" box for `{c,B}`: rows `9(B−1)..9B+7` (17 rows).
- Exits: horizontal on one storey (air rows `9s..9s+7` opened in col 0 / 31);
  vertical arrival: going up → bottom storey (`FLOOR_ROW1 − h`), going down →
  storey 0 (`FLOOR_ROW0 − h`). Transition scrolls move rows 0–17 only (h: 16
  steps, v: 18 char-row steps); panel rows 18–23 are never scrolled, stamped,
  or in the shadow. Row 17 is a normal map row (logical PLATFORM, the B3B-8
  ornament glyphs are a render detail) and scrolls with the room.
- (B3B-3 kept the PROTO HUD text on rows 21–23 until B3B-11, which replaced it
  with the panel engine: "Panel (D5)" below.)
- Rooms A–D (B3B-8: a PROTO level state, `proto_level` in bank 3; room ids =
  grid cells A 0, B 1, D 3, C 4) = prototype §8.2 on 2 storeys: PROTO storey 2 → 1,
  1 → 0, 0 → 0. A `{5,1}` `{23,1}`, potion 0 (28, s0); B `{4,1}` `{11,1}` `{24,2}`→C,
  potion 1 (1, s0); C `{24,0}`→B `{24,1}` `{6,1}`, potion 2 (29, s0); D `{22,1}` `{8,1}`,
  potion 3 (17, s0), chest cols 2–3 rows 6–7. Horizontal exits A↔B, C↔D on storey 1.
  B3B-5 adds: A|B door (starts open), D|C door (starts closed: the walkthrough
  bumps it), B pit p = 20 (storey 0), D dead-end block (right edge, storey 0,
  cols 29–31, rubble (28, 7)).
  Spawns (bank 3 `spawn_tab`): hero A (2, s1); rat A 16 s1, slime A 14 s0, goblin B 16
  s1, bat B 18 s0, skeleton C 12 s1 (PROTO col 16: moved so it climbs `{6,1}`, not the arrival shaft), ghost C 12 s0, skeleton D 12 s0, bat D 12 s1.

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
| 8 | `RD_PITCOL` | pit: left hole col `p` (holes `p..p+W−1` in row 8, caps `T_PIT_L` at `p−1`, `T_PIT_R` at `p+W`; W = 3, or `L2_PITW`); storey-0 floor only (game.md §2.5) → no storey byte |
| 9 | `RD_BLOCK` | dead-end block: bits 0–1 width (0 none / 2 / 3), `RDB_S1` bit 6 storey, `RDB_RIGHT` bit 7 side; cols `0..w−1` or `32−w..31`, WALL + WALLF in the floor row, `T_RUBBLE` at its foot |
| 10–11 | `RD_SEED` | room seed (word, ≠ 0): decor is re-derived from it, never stored |
| 12 | `L2_PITW` (`RD_SPARE`+0) | L2 wide pit (game.md §1.1): width W 4..6 of the `RD_PITCOL` pit; 0 = the narrow 3-col pit (`PIT_W_NARROW`) |
| 13 | `L2_MIDB` | L2 mid-room block, storey 0: left col b (0 = none); cols `b..b+w−1` rows 0–7 WALL, row 8 WALLF, `T_RUBBLE` at row 7 cols `b−1` and `b+w` |
| 14 | `L2_MIDW` | its width w 2..3 |
| 15 | — | zero (spare) |

### `EDGE_TAB` (`$6D50`, 6 B) — horizontal edges only

Index `e = gy*2 + gx` = edge between `r` and `r+1` (gx ∈ {0,1}): right edge of
`r` = `r − gy`, left edge = `r − gy − 1`. Bits: `EG_LINK 1` (connected),
`EG_DOOR 2`, `EG_OPEN 4` (runtime door state, both rooms), `EG_LOCK 8`,
`EG_SEAL 16` (never set in 3B). none = 0 · open passage = LINK · closed door =
LINK|DOOR · open door = LINK|DOOR|OPEN · locked / sealed = LINK|DOOR|LOCK / SEAL.
**Vertical connections have no table** (no doors on them): `RDX_U`/`RDX_D` +
the shaft cols of both rooms. Door cells (concept §3.1): cols 0–1 / 30–31 of
the exit storey, lintel row `9s` WALL, arch `9s+1`, planks `9s+2..9s+7`
(`DOOR_ARCH_DY`, `DOOR_PLANK_DY`, `DOOR_PLANK_H`); open = the plank rows drawn as the jambs `T_DOOR_JAMB_L` / `_R` (B10, non-solid), arch + lintel stay.

### Level header (`LVL_STATE` `$6D40`, 16 B) and `FLOOR_LIST`

| Addr | Symbol | |
|---|---|---|
| `$6D40` | `LVL_DEPTH` | 1..8 (0 = none) |
| `$6D41` | `LVL_SEED` | word, f(`MASTER_SEED`, depth) |
| `$6D43` | `GEN_RNG` | word, generator RNG (D9; never `RNG_STATE`) |
| `$6D45` / `$6D46` | `LVL_ATTR_FLOOR` / `LVL_ATTR_WALL` | game.md §1.2 |
| `$6D47`..`$6D4A` | `LVL_START`, `LVL_LAIR`, `LVL_KEYROOM`, `LVL_SANCTUM` | room ids (`ROOM_NONE` `$FF`) |
| `$6D4B` | `LVL_NROOMS` | 7..9 |
| `$6D4C` | `LVL_FLAGS` | `LF_GRATE_OPEN 1`, `LF_KEY_TAKEN 2`, `LF_SEAL_OPEN 4`, `LF_GATE_HINT 8` (B12: the lair's gate hint was logged this level; `lair_hint`, reset by `level_gen` rewriting the byte) |
| `$6D4D` | `FLOOR_N` | floor-list entries used |
| `$6D4E` | `MASTER_SEED` | word, per game |

`FLOOR_LIST` `$6E00..$6E7F`, `FLOOR_MAX` 32 × `FL_STRIDE` 4: `FL_ROOM` (bits
0–3 room, bit 7 `FL_S1` storey 1; `FL_EMPTY` `$FF` = picked up / free),
`FL_COL` (item cell col; row = the storey's standing row `9s+7`), `FL_ITEM`
(3E owns the enum; 3B: `IT_POTION` 1; D3-7: `IT_DAGGER` 2 / `IT_ARROW` 3, `FL_QTY` = the stack's count — one entry per type and cell, an ammo stack may share a cell with another item, game.md §6.3), `FL_QTY`.

### Tile ids (64; common 0..31 FULL)

| Id | Symbol | Note |
|---|---|---|
| 0, 1 | `T_AIR`, `T_PLAT` | |
| 2 | `T_BRICK` = `T_WALL_DARK` | plain air-band wall face; re-glyphed DARK (B3B-2) |
| 3 | `T_WALLF` | wall in a floor row (blocks, lintels in row 8/17) |
| 4–6 / 7–9 | `T_LAD_L/M/R` / `T_HOLE_L/M/R` | ladder / ladder cells in a floor row |
| 10 | `T_POTION` | PROTO; kept while potions are a floor tile (3B stand-in) — then the one free common id |
| 11, 14 | `T_DOOR_JAMB_L`, `T_DOOR_JAMB_R` | B10 (user option B): open-door jambs, `$A0` / `$05` × 8, ink `$06`, non-solid (the PROTO chest stand-in is gone, B3B-13) |
| 12, 13 | `T_CHAIN`, `T_SKULLS` | small decor; cobweb / moss move to the per-level sets |
| 15, 16 | `T_TORCH_T/B` | small torch (attr cycle) |
| 17, 18 | `T_DAGGERS` / `T_ARROWS` | **D3-7 (designer 2026-10-12, game.md §6.3): permanently the dropped-ammo floor glyphs** (ink `$47` / `$07`), TILE_FLAGS 0 (floor items, like `T_POTION`), not decor for the deriver's ring (`dg_bad` 0). **D3-7 T6:** the B3B-13b drips are no longer placed (`dg_drips` / `decorgen.drips` removed: the per-level sets have no free id; game.md §6.3 "if they are ever placed"); the `T_DRIP1/2` aliases are gone. Glyphs (`tools/tiles_convert.py`): concept `assets/gfx/concept/grid/ammo.tiles` (17 = pile of 3 daggers, 18 = 2 arrows; draft 2026-10-13, canvas review pending) |
| 19, 20 | `T_END_L` = `T_PIT_R`, `T_END_R` = `T_PIT_L` | floor edge right / left of a hole: the pit caps share them |
| 21–25 | `T_DOOR_ARCH_L/R`, `T_DOOR_L/R`, `T_DOOR_LOCK` | concept §3.1 (5 door ids) |
| 26, 27 | `T_GRATE`, `T_RUBBLE` | B12: `T_GRATE` = the **raised** gate (variant B, ink `$46` = `ATTR_GRATE`), `TF_LADDER \| TF_HOLE`, stamped over the lair's open level exit; `T_GRATE_SHUT` = `T_GRATE` until 3F gives the closed gate its own id (TODO 3F, level_defs.asm) |
| 28–30 | `T_WALL_DITHER/PATCH/FADE` | wall set |
| 31 | `T_CANDLES` | |
| 32..59 | `T_LVL_BASE`.. | per-level decor (bank-7 tileset) |
| 60..63 | `T_LVL_OBJ` | per-level **attackable** object slots (D8 lectern + Book 2×2); D1–D7 leave them unused |

Row-17 ornament: not tile ids (`ORN_GLYPHS`, 8 × 8 B, attr `LVL_ATTR_FLOOR`).
B3B-8: a render detail of the map's row-17 `T_PLAT` / `T_WALLF` cells
(`orn_cells`, lowram): cap_l at logical col 0, cap_r at 31, wing_l skull_l
skull_r wing_r at `ORN_MID_COL` 14..17, link (odd) / bar (even) elsewhere
(`tools/concept_r4.py`); hole / grate cells keep their tiles (no `T_END` caps
in row 17: the ornament runs to the hole). Bitmap only (the cell attr is
already `LVL_ATTR_FLOOR`). Drawn by `room_show` (screen), the scrolls
(the entering row-17 cells, by the next room's logical col) and (D3-S2)
`erase_rect` when a rect reaches row 17 (`orn_cells` over its cols; there is
no bitmap shadow to carry it). Tests: `tests/room_model.py` `expected_cell`.

**`TILE_FLAGS` bits** (D2; table = B3B-5 data `tile_flags`, 64 B by id, one
256-B page, static): `TF_SOLID 1` (bodies + projectiles: walls, block, arch,
closed planks, lectern), `TF_DOOR 2` (closed plank: bump opens), `TF_LOCK 4`
(locked/sealed plank), `TF_LADDER 8` (LAD_*, HOLE_*), `TF_HOLE 16` (floor-row
cell passable vertically), `TF_ATTACK 32` (lectern/Book), `TF_ANIM 64`
(deriver adds the cell to `ANIM_LIST`), `TF_FLOOR 128` (floor support; pit
holes are `T_AIR`, the pit itself is `RD_PITCOL`). `_BIT` twins for `bit`.

**As built in B3B-5** (`tests/world.py` W5–W9):
- `tile_flags` = the 64 B right below `kind_tab` (low byte `$C0`, page of
  `kind_tab − 1`; it sits in the ALIGN pad). Values: AIR 0, PLAT / END caps /
  GRATE `TF_LADDER|TF_HOLE` (B12: the raised gate = the open exit hole; was `TF_FLOOR`), BRICK `TF_SOLID`, WALLF `SOLID|FLOOR`, LAD `TF_LADDER`, HOLE
  `LADDER|HOLE`, arch `SOLID`, planks `SOLID|DOOR`, LOCK `SOLID|DOOR|LOCK`,
  torch / drip / candles `TF_ANIM`, the wall set (DARK = BRICK, DITHER,
  PATCH, FADE) `TF_SOLID`, RUBBLE 0, 32..59 0, 60..63 `SOLID|ATTACK`
  (game.md §1.2 "Solidity of decor": solidity = the cell class; wall-set ids
  only replace wall cells, non-solid decor only non-solid cells). **B3B-8:**
  ids 32..63 are overwritten per level by `level_load_tiles` from the slot's
  flags (`tools/tiles_convert.py` `level_flags`: wall-ink objects = pillar /
  plaster patches `TF_SOLID`, glyph-swap cells `TF_ANIM`, D8 lectern
  `SOLID|ATTACK`, everything else 0; PROTO depth 0: chest ids 32..35 = 0).
- `cell_addr` (B = row, C = col → HL = `ROOM_MAP` cell; 67 T), `cell_blocked`
  (→ A = flags, CF = `TF_SOLID`; keeps BC/DE, clobbers A/HL; ~135 T),
  `lead_cell` (box + dx → the leading col at row `y+h−1`; ~210 T),
  `box_solid` (every cell of a box; ~60 T a cell): bank 2. Walkers test the
  leading cell on horizontal steps only (safe: body h ≤ 6 never reaches the
  arch / lintel rows, ASSERTed); flyers test their whole new box on every
  step (game.md §9.1: an open door only through its opening rows). A closed
  plank → `hero_door` / `mon_door` (bank-5 low RAM; never on a yield step).
- Close (key C, game.md §2.3): door cells free of every body of the room
  incl. PENDING (`room_bodies`), no living hostile with a gap ≤ 2 cols to the
  hero or the door. Locked bump: message once per press (`LOCK_SHOWN`).
- Doors: state = `EDGE_TAB`; `door_find` (dx → the edge byte, door col, top
  plank row), `door_paint` (6 × 2 planks / jambs in `ROOM_MAP` + `shadow_rect` +
  `queue_damage`), `door_open` / `try_close` (key C); `build_room_map` draws
  lintel / arch / planks from the edge state. Measured (W5): close turn worst
  tick 31.8k T (input phase 18.6k), bump-open 31.8k (input 17.7k).
- Pit: `RD_PITCOL` of the current room's descriptor (0 = none:
  B11, `try_horizontal` skips the test then — a left-exit step lands on x 0,
  which used to match and drop the hero a storey at the doorway); `hero_fall`
  (`M_FALL`: 2 walk ticks + 9 × 8 px; 1d4; landing box → PENDING); walkers
  refuse `x == p` in `try_step` (**L2:** the whole fall range, below). Jump (`try_jump`, `M_JUMP`, 14-tick arc,
  `jump_dy`): W8 worst tick 60.3k T; fall turn 39.5k T.
  **J1 (2026-10-06):** `try_jump` picks D = 6 / 7 (low-body extension,
  `jump_bodies` low = h ≤ 2, w ≤ 4), `jump_pit` (lowram) lets a landing on the
  fall range `p .. p+W−3` fall (and cuts the arc short at a wide pit, W ≥ 4)
  via `hero_fall` with the mode kept `M_JUMP`; `pit_w` (lowram) = the
  descriptor's `L2_PITW`, 0 → `PIT_W_NARROW` (W8 pokes room B's `L2_PITW` to 5
  to test the cut-short path). The arc py
  is computed (`8y − 4·min(t, N−t, JUMP_APEX)`), `jump_dy` is gone. W8:
  D 6 jump 48.7k T, jump into the pit 56.4k T, D 7 68.7k T.
  **L2 engine (2026-10-12; `tests/world.py` W26):** `pit_range` (lowram, C = x
  → CF = 1 iff `p ≤ x ≤ p+W−3`, H = p, L = W−2; keeps BC/DE, ~150 T) is the one
  fall-range test: `try_horizontal` (hero falls), `try_step` (walkers refuse;
  flyers skip it), `jump_pit`. `desc_byte` is gone (no callers left). The
  mid-room block needs no logic: its cells are `T_BRICK` / `T_WALLF`
  (`TF_SOLID`), so `lead_cell` and the jump's `box_solid` stop at it like an
  edge block. `build_room_map` draws W holes + caps (`.pit`) and the mid-block
  through the edge block's `.wall` + `T_RUBBLE` at both feet (`.mid`), before
  the segments and decor (the deriver only places on exact `T_AIR` / `T_BRICK`
  cells with ring tests, so rubble / caps / holes never carry decor; the block's
  `T_BRICK` cells may take wall-class decor exactly like an edge block).

**As built in B3B-8** (`tests/world.py` W0/W3 + W11/W12/W12M, `tests/room_model.py`):
- One descriptor format: the PROTO rooms are a level state (`proto_level`,
  called by `new_game`: header with `LVL_DEPTH` 0 = PROTO and D1 colours,
  `EDGE_TAB` A|B open / D|C closed, 4 descriptors with `RD_SEED` 0,
  `FLOOR_LIST` = the 4 potions). The PROTO `room_tab` / `RD_LADDERS` lists
  are gone; every query reads `ROOM_DESC` + r·16 (bank 2: `room_desc` 46 T,
  `cur_room_desc`, `seg_storey`, `ladder_exists`, `nearest_ladder` (bank 3
  since B3B-R2), `room_side` (exit storey, neighbour r±1, edge index
  `m − m div 3`) → `exit_h`, `door_find`; `try_climb` takes the up / down exit
  only at `x == RD_UPCOL` / `RD_DNCOL` with `RDX_U` / `RDX_D`, dest r∓3; the
  arrival shaft `{ARRCOL,0}` and the level exit `{EXITCOL,2}` are segments
  without an exit (B3B-12 wires the level exit). Potions (D3-7 T6: `floor_pickup`, list-driven):
  every `FLOOR_LIST` entry (room | `FL_S1`, col under the body), marks a taken one `FL_EMPTY`,
  sets `POTIONS_TAKEN` bit = entry index (potions) and re-stamps the cell (`ap_stamp`).
- `build_room_map` v2 (bank 3, far3 through lowram `build_room`, A = room,
  page in D): base → exits + doors → pit → block → segments (row 8 holes +
  `T_END` caps, row 17 holes, ARR + `T_RUBBLE` ×3 in row 0, EXIT under
  `T_GRATE_SHUT` ×3 unless `LF_GRATE_OPEN`, always set in 3B: game.md §1.4 →
  the open hole) → `FLOOR_LIST` potions → decor: `RD_SEED` ≠ 0 →
  `decor_room` (B3B-9 deriver, below), seed 0 → `proto_decor` (A torch, D
  chest) → **B12 `.gate`** (open grate only): `T_GRATE` (raised) over the 3
  exit cells + `glow_ids[depth − 1]` (`TS<d>_GLOW_F1_R0C0`, bank 3) at row 16,
  col `EXITCOL + 1` if that cell is `T_AIR`. After the deriver on purpose: its
  ring rule still sees `HOLE_*`, so the decor is unchanged and nothing sits
  beside / above the exit. `do_exit` → `lair_hint` (lowram) logs
  `TX_GATE_GLEAMS` on the first lair entry per level (`LF_GATE_HINT`). B3B-10: the build first picks the decor list of its map page
  (`ROOM_MAP` → `ANIM_N`, `NEXT_MAP` → `ANIM_N2`, bank-3 `dg_dst`) and empties
  it, so PROTO / seed-0 rooms always leave an empty list. Measured (DI, ZEsarUX, contended): 45.4k T
  worst per room (cold: room entry only). `floor_pickup` / `ap_stamp` / the builder all
  read `FL_ROOM` through `FL_ROOM_MASK | FL_S1` (bits 4–6 reserved, ignored).
- `room_show` (A = room) = build + `draw_room` (screen + attr shadow) + ornament (screen):
  the room-entry path of `level_show` (new game, descend: "Level entry"
  below). `tests/world.py` W11–W13 still drive generated rooms through stubs
  (`far3 level_gen` → `level_load_tiles` → `room_show r` → `present_full`).

### As built in B3B-9 / B3B-10 (animated decor; `tests/world.py` W13 / W14)

- **Deriver** `decor_room` (bank 3, `src/decor_gen.asm`; reference
  `tools/decorgen.py`, byte-equal, W13): re-derived from `RD_SEED` (own
  xorshift, never `GEN_RNG` / `RNG_STATE`); 12 attempts × 4 rnd calls; budgets
  ≤ 2 large animated objects, ≤ 4 glyph-swap + ≤ 8 attr-cycle cells (≤ 12
  entries), ≤ 6 wall-class cells; objects in rows `9s..9s+5` only, never on a
  structural cell or next to a ladder. Measured 47–72k T per room (W13: build
  with decor − build with `RD_SEED` 0; cold, room entry only).
- **`ANIM_LIST` contract** (per entry `AL_COL`, `AL_ROW`, `AL_TYPE`,
  `AL_PHASE`; entries per object, row-major; an object's glyph and attr cells
  are separate entries): `AL_TYPE` 1..15 = attr-cycle kind (1 flame, 2 candle:
  `dt_attr_tab`, 8 steps each), ≥ `AL_GLYPH_MIN` 16 = glyph swap holding the
  OTHER tile id (the deriver writes the alternate frame; `decor_tick`
  exchanges it with the `ROOM_MAP` cell, so the map always holds the shown
  id); drip entries hold 16 ticks (glyph entries step only at `AL_PHASE & 15 == 0`, `DT_GLYPH_HOLD`). `AL_PHASE` = the object's stagger `(col + row) & 7` at build, then a
  tick counter (+1 per serviced tick; due when `& 3 == 0`; cycle index = bits
  4..2).
- **NEXT_MAP rule** (B3B-9 review 🔴): a build into `ROOM_MAP` fills `ANIM_N` /
  `ANIM_LIST`, a build into `NEXT_MAP` (do_exit) fills `ANIM_N2` /
  `ANIM_LIST2`; `room_shadow` (do_exit, after the scroll) copies the 49 B over
  `ANIM_N` / `ANIM_LIST` (~1k T). Every build empties its list first.
- **For B3B-12 (level change)**: the new level's first room must be built
  into `ROOM_MAP` (`room_show`) — or into `NEXT_MAP` followed by
  `room_shadow` — before the first play tick, so `ANIM_N` / `ANIM_LIST`
  describe the room on screen; otherwise `decor_tick` steps the previous
  level's entries on the new map (wrong cells / ids).
- **`decor_tick`** (bank 2, `src/decor.asm`; `play_loop` after this tick's
  `render` + `pmark_dmg` — with `RENDER_FIRST` (default) also after
  `read_turn_input` / `anim_tick`, which leave `R_COL..R_ROWS` alone — just
  before `panel_tick`): skipped when `ANIM_N` = 0 or when the tick is already
  in its 2nd frame (`SYS_FRAMES` ≠ `LAST_TICK_FRAME`, like `panel_tick`: the
  decor holds, so a heavy input tick is never lengthened). Per tick ≤ `DT_MAX_GLYPH` 1 glyph
  swap + ≤ `DT_MAX_ATTR` 2 attr steps (D6 allowed 2 + 3; measured ~1.2k /
  ~0.75k T per step) and ≤ `DT_MAX_TRIES` 3 occupancy tests; a due entry past
  a cap waits a tick (`AL_PHASE` − 1); a tested entry whose cell lies in a
  drawn sprite footprint (`RLIST` slots' `R_COL..R_ROWS`, a direct test (like the
  old `zap_covered`): ~90 T per slot, only for the ≤ 3 tested cells — cheaper than
  clearing + rebuilding a 72-B `OCC_MASK` every tick, ~0.9k + ~0.5k per
  sprite) skips that step (the cell holds; next test at its
  next due tick). A step writes the
  bank-5 cell and the bank-7 attr shadow (D3-S2: no bitmap shadow; glyph swap: map id ↔
  `AL_TYPE`, glyph + `TILE_ATTRS` attr; attr kind: the cycle colour) and marks
  the cell in `PRES_MASK` (inline 1-cell `pmark_rect`). Leaves bank 7 paged.
  Never touches panel rows (deriver rows ≤ 14). Measured per tick, by
  scenario: `tests/world.py` W14 (a real D1 room, its 8 derived entries,
  hero only): max 3,534 T, mean 2,458 T; `tests/budget.py` (the synthetic
  full list, 12 entries, 4 glyph + 8 attr, 5 sprites, incl. the call and the
  panel test): max 5,364 T, mean 2,487 T (mix) / 1,117 T (heavy) — the
  budget figure is the worst case to plan with. Worst ticks (B3B-10) mix
  111,466 / heavy 116,235 T (without decor 116,883 / 114,139), 0 overruns.
  Attr kinds write the whole attr byte (`DT_HOT` = `ATTR_TORCH` $46 /
  `DT_RED` $42 / `DT_DIM` $06, `src/decor.asm`), overriding the cell's
  paper: black on every attr-cycled cell (candles, small torch, the large
  torches' / braziers' row-1 cells in all 8 tileset slots; checked
  2026-10-04), so nothing changes but the ink / BRIGHT.
- **Tests**: W13 (deriver == Python for `ROOM_MAP` and `NEXT_MAP` builds, an
  independent rules checker incl. a wall-heavy sweep and synthetic maps, Z80
  on synthetic maps), W14 (`decor_tick` == a Python model every tick for 32
  ticks: lists, map, bank-5 cells, shadow; a cell under the hero holds;
  shadow == map; displayed == composed at every present; the scroll A → B
  brings B's list). `tests/budget.py` / `tests/flicker.py` inject a synthetic
  full list (4 glyph + 8 attr, one stagger) into room A (`BUDGET_DECOR=0`:
  off).

### Level entry (B3B-12; `tests/world.py` W16)

- **One path** for a new game and a descend: `level_enter` (bank-5 low RAM,
  A = depth 1..8, DE = first log line): `GAME_STATE` = TRANSITION; clear the
  bank-5 screen, `far3 level_card` ("DEPTH n", ROM charset, row 11 col 12),
  `present_full` — the card stays on screen 2 while the rest is composed in
  bank 5; `far3 level_new` (bank 3): `LVL_SEED = MASTER_SEED + depth ×
  LVL_SEED_MUL` (`$9E37`, 16-bit; additive with an odd constant because
  `level_gen` seeds `GEN_RNG = LVL_SEED ^ depth·$0101`, which an XOR mix would
  cancel; per depth the map master → seed is a bijection over the whole
  16-bit space), `level_gen` retried while it returns B = 1 (each failed call
  has already advanced `LVL_SEED` by 16; D8 seeds 55352–55354 exhaust once;
  ≤ 2 calls: `tools/levelgen_runs.py` scans all 65,536 seeds — D1–D7 never
  fail, D8's longest run of failing seeds is 18 < 32, so no hard cap),
  then `level_populate`; then `level_show` (also the PROTO entry, A = 0):
  `level_load_tiles` → clear → `room_show CUR_ROOM` (first room built into
  `ROOM_MAP`, so `ANIM_N` / `ANIM_LIST` are the new room's) → `far3
  panel_init` (depth `Dn`) → `vis_reset` (entity table rewritten) →
  `present_full`. Callers set `GAME_STATE` (PLAYING) and resync the tick. No
  generator call: the 3B stand-in kinds are all in the boot pool (`GEN_TRAP`
  stays 0; 3F's per-level pool goes between `level_gen` and the build, after
  `alloc_restore`). Measured: `level_enter` (D2, DI) **1.56M T ≈ 0.44 s**;
  real descends 31 frames (D1→D2, incl. the turn's ticks) to 50 frames (D8
  from an exhausting seed: two `level_gen` calls) ≈ 0.6–1.0 s.
- **Population** (`level_populate`; **LP since plan task LP**, the B3B-12
  stand-in table is gone): hero slot 0 keeps kind / HP / MAXHP / potions and
  the `E_FLAGS` bits of `HERO_CARRY` (today `EF_LEFT`; ACTIVE | PLAYER
  rebuilt, the rest dropped); **D3-0: the hero's status (`ST_*` slot 0) and
  `HERO3D` carry by not being touched — `level_reset` clears `ST_*` slots
  1..15 only, `new_game` (`level_reset_new`) clears slot 0 + `HERO3D` too
  (`tests/world.py` W16)**; room = `LVL_START`, x = `level_start_x`, standing
  on storey 0; `CUR_ROOM` = `LVL_START`; per-level state reset
  (`level_reset`: `POTIONS_TAKEN`, `EXIT_KIND`, `MSG_Q`, `PEND_DMG`,
  `YIELD_FLAG`, `JUMP_TURN`, entity table). Then `lp_budget`
  (the per-room quotas) and the start room's `lp_enter` (quota 0: no
  monster; record VISITED, `ROOM_VISITS[start]` = 1). Monsters appear when
  the hero enters their room: "LP contracts".
- **Descend**: the lair's level exit `{EXITCOL,2}` is a ladder segment
  without an exit bit; `try_climb` DOWN at `x == RD_EXITCOL` on storey 1,
  only while `LVL_FLAGS` has `LF_GRATE_OPEN` (always in 3B; 3F: the boss),
  sets `EXIT_KIND` = `EX_LEVEL` (5) and animates the first step; `end_turn` →
  `do_exit` → `level_descend` (lowram): D8 → `GS_WIN` + `str_win` (stand-in),
  else `level_enter(depth + 1)` with "YOU DESCEND DEEPER", then
  `NEED_RELEASE` = 1 like `start_game`. Followers do not come along (the
  entity table is rebuilt; designer ruling pending). The PROTO win
  (room D) only counts at `LVL_DEPTH` 0.
- **Run flags** (cold-block bytes, on tape; `-D` defaults; tests poke them):
  `proto_start` (`PROTO_START`, default 0: generated D1; 1: PROTO rooms A–D,
  the `tests/game.py` walkthrough / budget / flicker / W0–W15 path —
  `game_lib.Proto.load()` pokes 1 after every load), `seed_fixed` /
  `seed_value` (`SEED_FIXED` / `SEED_VALUE`, game.md §1 F3: `MASTER_SEED` =
  `seed_value`; default `SYS_FRAMES` low word when the hero is chosen, its
  high byte XORed with `R` — little extra entropy since the select loop is
  HALT-synchronised; the 20 ms frame of the keypress is the real source).
  (C3-8a: the `legacy_input` cold-block byte and the PROTO input mode are removed; the cold block is 1 B shorter.)

### Bank-7 tileset slots

`BANK_TSET` 7; slot = depth − 1 (PROTO depth 0 → slot 0); `TSET_STRIDE` **320**
(B3B-8, was 288) = glyphs of ids 32..63 (256 B, `TSET_GLYPHS` +0) + attrs (32
B, `TSET_ATTRS` +256) + `TILE_FLAGS` of ids 32..63 (32 B, `TSET_FLAGS` +288)
→ LDIRs of 256 / 32 / 32 to `TILE_LEVEL_GLYPHS` / `TILE_LEVEL_ATTRS` /
`tile_flags + 32` (`level_load_tiles`). Slots 0–3 at `TSET_LO`
`$DB00..$DFFF` (exactly up to `B7_CODE` `$E000`, D3-S2: one tape block with the bank-7 code), 4–7 at `TSET_HI`
`$FAA0..$FF9F` (`(slot<4 ? LO : HI) + (slot&3)*320`; 96 B left to `$FFFF`).
Data: `assets/gfx/tiles/tilesets.asm` (generated; it invokes `TSET_SPLIT`,
a `main.asm` macro, between D4 and D5 to `ORG TSET_HI`), assembled with
`MMU 3, 7` into the `.sna` and saved as two headerless tape blocks
(`TSET_HALF_LEN` 1,280 B each, loaded by `start` `.t7lo` / `.t7hi`).
Nothing at runtime writes `$DB00..$DFFF` or `$FAA0..$FFFF`.

### Panel (D5) and bank-2 runtime

`PANEL_DIRTY` `$BFD0` bits: `PD_HP 1`, `PD_MP 2`, `PD_FOOD 4` (bar + hunger
word), `PD_AMMO 8`, `PD_LOG 16` (scroll + newest line from `LOG_Q`), `PD_ICONS
32`, `PD_INFO 64`, `PD_DEPTH 128` (depth + key). One item per tick, never in
the input tick. `HUD4_EXT`/`HUD4_PW` (rows 20..23, one page, ASSERTed),
`LOG_Q`/`LOG_QN`, `FONT6` `$B200` (planar, 4 pages), `HOT_COPY` `$B5E0`, `ANIM_LIST` / `ANIM_LIST2`
— addresses in the bank-2 and state-block tables above.

**As built in B3B-11 / B3B-11b** (`src/panel.asm` bank 3, `src/panel_hot.asm`
`HOT_COPY` image (load image in bank-1 `vdata`), `src/panel2.asm` bank 2;
`tests/world.py` W15):
- Layout (concept-screen §5): rows 18–19 the 10 icon slots of the class
  (game.md §3.5; static art: ability / bag icons, quick food / scroll and the
  spare as empty outlines, slot 0 selected = PAPER blue); the quick-potion slot
  shows the `T_POTION` glyph at (col, 19) + the potion count at (col+2, 19)
  (greyed `$07` at 0; stand-in for the PROTO "POT n"); depth `Dn` at (30, 18)
  (`LVL_DEPTH`, PROTO 0 → `D1`); row 20 blank (info line: 3C); row 21 heart /
  HP bar (cols 1–4) + 2-digit number (5–6) `$42`, drop / MP bar empty (3C)
  `$45`, drumstick / FOOD bar full + `FED` `$44` (3E), no ammo; rows 22–23 log
  (cols 0–23, `$07` / `$47`) + 4 empty gear outlines (cols 24–31, `$01`).
- `print6` (B3B-11b "quad" printer, `src/panel_hot.asm`; HL string, B row,
  E pixel x **multiple of 8**): 4 chars = 3 bytes per pixel line composed in
  registers from the planar `FONT6` and stored (no screen reads, no phase
  code); exactly the ceil(6n/8) bytes of the run are written (partial last
  quad: ' ' padding + the stores past the text patched to `nop`), E out =
  x + 6n. Measured **~461 T/char** (32 chars 14.8k T, contended; B3B-11:
  ~650-678). Short strings pay one whole quad (~2.1k T for 1..4 chars). Char
  source = 4 SMC fetch sites (default inline `ld a,(bc) / inc bc`);
  `print6g` (bank 2) switches them to `call getter`, `print6` switches back
  by itself. B3B-13: `print6t` (HL = token stream) = print6g + `tk_get`
  with `BANK_TEXT` paged around it ("Text (B3B-13)").
- Queue (B3B-13: the ring holds token streams, `item_log` draws them with
  `print6t`; game code pushes string ids with `msg_push` / `msg_push_end`):
  `log_push` copies ≤ 32 bytes into the `LOG_TXT` ring (4 × 64 B at
  `$5B00`, bank-5 printer buffer: runtime RAM, free after boot), `LOG_QN` += 1,
  `PD_LOG`; ring full → dropped, `LQ_DROP` += 1. `log_push_end` (GS_DEAD /
  GS_WIN lines) is never dropped: ring full → it replaces the newest pending
  message (counted in `LQ_DROP`). HP + MAXHP (one 16-bit compare) / potions
  are polled by `panel_step` against `PANEL_HP_SH` / `PANEL_POT_SH` (logic
  never sets those bits); `panel_init` sets HP / ICONS / DEPTH. Priority
  HP → LOG → ICONS → DEPTH.
- `panel_tick` (play_loop after `anim_tick`, skipped in a turn's input tick =
  ANIM with `TURN_TICK` 0; also every `end_screen` tick): while the tick is
  still in its **first frame** (`SYS_FRAMES == LAST_TICK_FRAME`) it draws items
  (any, a log message = `log_scroll` + the whole line, ~20.4k T for 32 chars)
  and re-checks the frame after each, so it stops below ~92k T; a tick already
  in its **second frame** draws one small item (HP ~4.5k / ICONS / DEPTH
  ~2.5k T), never a log message (heavy ticks reach ~117k T before the panel).
  In fights the log therefore lands in the turn's last light ticks: budget.py
  reports max 6 ticks push → drawn (mix and heavy), 0 ticks over 126k T.
  Test probe `panel_done` after the call. (B3B-11's chunked `P_LIM` /
  `LOG_CHUNK` path is gone.)
- Present: log rows by `HUD4_PW` (present's text-row loop), the rest by
  `pmark_rect`. `panel_init` (far3 from `start_game`, DE = first message) +
  `panel_flush` draw everything at once before `present_full`.

### Text (B3B-13)

- **Source:** `src/strings.txt` (every game message; `name "TEXT"`, upper
  case, ≤ 32 chars = `LOG_MAX`). `tools/textpack.py` (`tools/build.sh` step,
  before sjasmplus) writes `build/text/strings_ids.inc` (`TX_<NAME>` ids,
  `TXL_<NAME>` decoded lengths + `ASSERT TXL_* <= LOG_MAX`, INCLUDEd at the
  end of `defs.asm`) and `build/text/strings.asm` (the block), then re-parses
  the emitted asm, decodes every string with the getter's algorithm and fails
  the build on a mismatch / a char outside 32..127 / > LOG_MAX.
- **Stream format:** 0 end; 32..127 literal; t ≥ 128 token → dictionary
  entry t − 128 = 2+ literal chars, the last with bit 7 set (no nesting).
  Dictionary built greedily from the real strings (saving n·(L−1) − (L+2)).
  Streams concatenate (composition in `MSG_BUF`); numbers are literal digits.
- **Block** (`text_img`; **D3-TX: bank 0 = `BANK_TEXT`** at `TEXT_ADDR`
  `$C000`, under the pool (`POOL_START` = its end), own tape block; was bank 1
  after `vdata`, DISPed — the D3-2 strings, 2,684 B, did not fit bank 1's
  992 B; bank 0 is uncontended, so text reads got cheaper): `tx_tab` (DW per string id) · `tx_dict` (DW per token) · entries ·
  streams. B3B-13: 24 strings, 4 tokens, 278 B raw text (0-terminated; +48 B
  of the pointers the code used) → **277 B** incl. tables (the corpus is tiny;
  the format pays off with the 3E/3F names).
- **Z80:** `msg_push` / `msg_push_end` (A = TX_*; lowram: page `BANK_TEXT`,
  `tx_ptr`, `log_push(_end)`, hand `$C000` back), `tx_ptr` (A → HL; **D3-0: 16-bit index**, `ld l,a / ld h,0 / add hl,hl`, 86 T: string ids 0..255, `TX_COUNT ≤ 256` (textpack `MAX_STRINGS` + the emitted ASSERT; was 128 via `add a,a`); `tx_ptr_hl` = the same entry for an HL id, the planned path past 256 — ids are bytes in every caller / DB table today),
  `show_impact_msg` (lowram, pre + kind name `TX_NM_KNIGHT + kind` + post via
  `imp_pre` / `imp_post`); `print6t` (bank 2: HL = stream, pages `BANK_TEXT`
  around `print6g`); `tk_get` (bank 2, the getter; mode = SMC opcode at
  `tk_get.sw`, parked stream in `tk_get.back+1`): +35 T per literal char vs the
  inline fetch, measured (W17) **+39.5 T/char** averaged over all strings vs a
  called plain fetch. Log item: whole line incl. a 32-char scroll ≤ 22.3k T
  (W15), worst real message push + item 19.6k T, worst composed impact line
  22.1k T (W17).
- **D3-TX: no in-place reads.** Bank-1 UI code (menus) cannot page bank 0
  under itself: `tx_dec` (lowram: A = id → the decoded string, 0-terminated,
  in `TX_DEC`, HL = `TX_DEC`; pages `BANK_TEXT`, restores the caller's bank;
  ~0.4k T + ~60 T/char) feeds `mf_tx` / `tx_copy` (menu1). `TX_DEC` = 43 B
  (`WIDE_MAX` + 0) at `$6D15..$6D3F`, the top of `GEN_MIR`: transient, above
  `PAUSE_SAVE..+PAUSE_LEN` (ASSERTed); the generator never runs inside a menu
  text call. `print6x` / `print6t` / `msg_push` / `impact_line` page it as
  before.
- **textpack speed (D3-TX):** the dictionary build keeps per-stream substring
  counts incrementally (only streams an entry was substituted into are
  re-counted): 198 strings in 0.2 s (was ~3 min), output byte-identical.
- **3C long text** (menus, help, books): the same streams, ZX0-packed per
  text, unpacked into a buffer that `print6t` streams (the getter state is a
  plain pointer). Not built yet.
- Test: `tests/world.py` W17.


## LP contracts (plan task LP, game.md §9.4.1–9.4.7) — lazy monster population

A level stores no monster list: a **budget** + one **record per room**; the
16 entity slots hold only the current room's monsters (+ pending followers).
Generated levels only: on the PROTO rooms (`LVL_DEPTH` 0, `proto_start`)
none of this runs and every monster keeps its slot as before.

**`LP_STATE`** (`$6EC0`, `LP_LEN` 114 B, bank 5 low RAM, `level_defs.asm`):

| Off | Symbol | |
|---|---|---|
| +0 | `LP_KINDS` | 4 B: the depth's kinds (game.md §9.4 table order) |
| +4 / +5 | `LP_BOSS` / `LP_TOTAL` | boss kind row / the table count incl. boss |
| +6 | `LP_LVL` | hero `LVL` at level entry (§9.6 tier input, 3F) |
| +7 | `LP_RESPAWNS` | trickle spawns this level (§9.5 `RESPAWN_MAX` 6; 3F) |
| +8 | `LP_DISCARD` | units lost: split / sum cap / a full record (expect 0 from the split) |
| +9 | `LP_RMAX` | `ROOM_MAX` 2 (D1–D2) / 3 (D3–D8) |
| +10 | `LP_RNG` | word: the last entry's spawn-stream seed |
| +12..+23 | `LP_HX` `LP_HS` `LP_HW` `LP_SIG` `LP_RECP` (w) `LP_W` `LP_GAPV` `LP_BEST` `LP_BS` `LP_BX` `LP_RES` | `lp_enter` / `lp_budget` scratch (tests mask it) |
| +24 | `ROOM_VISITS` | 9 B: entries per room this level (spawn-stream input) |
| +33 | `LP_REC` | 9 records × `LR_STRIDE` 9: `LR_HDR` (bit 7 `LR_VISITED`, bits 0–2 count) + 4 × {`LE_KIND` = kind row bits 0–4 \| `LEK_BRED` bit 6 \| `LEK_RESPAWN` bit 7 (= `EF_RESPAWN`), `LE_HP` exact hp}. FRESH: count = quota, no entries; VISITED: count = entries (unused entries 0) |

**`LP_CMAP`** = `NEXT_MAP + PLAY_CELLS` (`$6540..$6581`, 2 × 33 B, NEXT_MAP's
unused tail): `lp_enter`'s per-col placement marks (`LPC_BAD` 1: footprints
widened by the 1-col margin, arrival boxes, placed bodies; the arrival gap is
tested per try). Valid only inside `lp_enter` (before do_exit builds NEXT_MAP; at level
start GEN_SCRATCH's `LG_*` sit at `$6000..$6051`).

**`EF_RESPAWN`** = `E_FLAGS` bit 7 (was spare): §9.5 `F_RESPAWN`, carried
through the records; nothing sets it before 3F.

**Kinds:** `lp_dtab` (bank 3) per depth; the kinds / bosses without a
`kind_tab` row yet are **stand-in aliases** (`defs.asm`: `K_SPIDER` = rat,
`K_VAMPIRE` / `K_ARCHER` / `K_MUMMY` = skeleton, `K_ORC` / `K_NECRO` =
goblin, `K_BOSS_D1..8`): 3F replaces the EQUs. Weights `lp_wt` (bank 3, by
kind row, `WT_K_*`, game.md §9.1 W).

**Flow** (bank 3, `src/lpop3.asm`; Python reference `tools/levelgen.py`
`lp_budget` / `lp_enter`, byte-exact, `tests/lp.py` + `tests/levelgen_z80.py`):
- `level_new` → `level_gen` → `level_populate` → `lp_budget` (after the
  generator, on a copy of `GEN_RNG`: the header keeps the generator's final
  state; 3E traps go before it) → `lp_enter(start)`.
- `do_exit` → `follow_select` (candidates only on LP levels) → `hide_sprites`
  → `far3 lp_transition`: `lp_bank(old, E=1)` (alive, non-candidate slots
  appended, all freed; dead never written) → arrival box from `EXIT_*` →
  `lp_enter(dest)` → `follow_admit` (≤ `ROOM_CAP` alive and Σ weight ≤ 12,
  record leftovers counted) → `lp_bank(old, E=0)` (rejected candidates) →
  `ROOM_VISITS[dest]` += 1 → `R_VIS` of slots 1..15 cleared (`vis_room_sync`
  rebuilds RLIST) → the NEXT_MAP build and the scroll as before.
- `lp_append` (A room, B kind byte, C hp): the §9.5 trickle's record side (3F).
- Invariant after every transition: every active non-hero slot has
  `E_ROOM = CUR_ROOM` (`tests/lp.py` B1–B3).

**Cost (measured, DI, contended bank-3 code / bank-5 data, `tests/lp.py`
A2, after the 2026-10-06 tuning):** `lp_enter` mean ~19.8k T, worst ~37.7k T
(incl. far3 ~0.4k); game.md §9.4.3 accepted ceiling mean ≤ 20k / worst ≤ 40k
(lp.py guards both). Tuning (designer decision 2026-10-06): reservation fit
(`LP_RES`, SIGMA_INIT = max(8, ROOM_MAX × minW): `LP_DISCARD` 0), arrival
gap `LP_GAP` 8 on tries 1–4 / `LP_GAP2` 5 on 5–8 (`LP_GAPV`), a gap-only
failure re-tests the same x on the other storey, footprint margin 1 for
walkers and flyers (§9.4.3 "±1 col"). Levelcheck sweep: 9.4 % of first-entry
units wait (was 16 %).

## 3C contracts (C3-0) — code against these symbols

Plan "3C breakdown" D4 / D7. EQUs in `src/hero_defs.asm` (no image bytes);
far calls in `src/gfx.asm`; the bank-1 region in `src/main.asm`.

**Far calls.** `farb` (bank 2): HL = target, A = arg, C = bank → the
target runs with bank C at `$C000`; the caller's bank (bits 0-2 of the saved
shadow; screen bit kept) is restored. DE / IX pass in, BC does not (page_bank);
BC / DE / HL / IX pass out; clobbers A, F; nestable. `far3` = `ld c,
BANK_COLD3` + farb (unchanged for its callers, +7 T); `far1` = `ld c,
BANK_UI1` + `jr farb`. Every helper paged-bank code calls hands `$C000` back
(conventions.md "Banking"; `copy_virt_keep` = `copy_virt3` since C3-0).

**Bank-1 UI code** `ui1_code..ui1_end` (`src/ui1.asm`, `BANK_UI1` = 1):
assembled after `vdata` (D3-TX: the text block is in bank 0) at its runtime address (DISP
`TEXT_DISP`), part of the bank-1 tape block; ASSERT `ui1_img_end <= $C000`
(virtual) and `ui1_end <= UI1_LIMIT` (`$10000`). C3 review (bank-3
relief) + C3-6: `$E81E..$F8E8`, 4,298 B — the C3-6 menu / redefine / pause
/ end and DEPTH cards (`menu1.asm` ~2.0 KB + the C3-5 menu art 1,104 B:
`menu_font`, `menu_title`, `menu_torch`), the transition scrolls (`scroll1.asm`:
`hscroll_room` / `vscroll_room` + their shift / row helpers, far1 from
`do_exit`; they touch only bank 5 and bank-2 / low-RAM helpers) and the info
line (`info1.asm`: `item_info`, `dec16`, `xp_next`, `info_tab`, far1 from
`panel_more`; `INFO_TX` picks the potion / Bag numbers, so no `slot_act`);
**1,744 B free** (DISPLAY "bank-1 UI code"; review relief: 4,935 B; C3-0:
empty at `$E4AC`, 6,996 B — the C3-4 text grew the block below it). Every
bank-1 UI variable sits in one block `ui1_vars..ui1_vars_end` (tests/game.py
#50 masks only that). The menu's frame + probe `select_tick` (= `menu_tick`)
is `menu_frame` in bank 2 (always mapped; C3-6 review). **PC probes alias
across banks 1 / 3** (a ZEsarUX `PC=` breakpoint fires in whichever bank is
paged): since D3-0 the AY slot `$F000..` lies inside the bank-1 UI code's
range, so tests stop at the ISR's call site `isr.page` (bank 2), never at
`AY_PLAY` (#61). Bank-3 cold code (`..bank3_end`, `$DFE4` at D3-0) is still
below `ui1_code` (`$EB8D`); once they overlap, a probe on a bank-3 or bank-1
label must add a `RAM=n` condition. Bank-1 data (`vdata`, text) is
readable in place at virtual + `TEXT_DISP` while the UI runs. Runtime bank-1
RAM above `ui1_end` is otherwise unused (W18 borrows it for its target).

**`HERO_ST`** `$BC90..$BCBB` (bank-2 runtime RAM, 44 B, after `ANIM_LIST`,
up to `ISR_ADDR`; not on tape — the owner task initialises it; one page):

| Addr | Symbol | Size | Meaning |
|------|--------|------|---------|
| `$BC90` | `SEL_SLOT` | 1 | selected icon slot 0..9 |
| `$BC91` | `FIRE_ST` | 1 | fire-button state: `FS_UP` 0, `FS_TAP` 1 (held, a release now is a tap), `FS_USED` 2 (held and used, or ≥ `FIRE_TAP_MAX` 10 ticks) |
| `$BC92` | `FIRE_T` | 1 | fire hold timer (ticks) |
| `$BC93` | `STICK` | 1 | the 5 inputs this tick, `JOY_*` bits (C3-1: `input_tick`, once per tick, every tick: `read_stick`, FIRE cleared under BREAK) |
| `$BC94` | `STICK_OLD` | 1 | `STICK` of the previous tick (edges; ANIM ticks included) |
| `$BC95` | `JOY_MODE` | 1 | input source (C3-1): `JM_KEYS` 0 (boot), `JM_KEMPSTON` 1, `JM_SINC1` 2, `JM_SINC2` 3; KEYTAB is read in every mode |
| `$BC96` | `KEYTAB` | 10 | 5 × {row byte, bit mask}, entry i = `JOY` bit i; row byte = `KEYTAB_ROW` + `KBROW_*` (= low byte of the half-row's `KBD_MATRIX` address; C3-1 review, was the port high byte); defaults P / O / A / Q / SPACE (macro `KEYTAB_DEFAULTS`). C3-6 redefine must store only rows `KEYTAB_ROW..+7` and a non-zero one-bit mask (mask 0 reads as always pressed) |
| `$BCA0` | `ICON_SH` | 10 | C3-3: per slot `IS_HIDDEN` 0 / `IS_GREY` 1 / `IS_NORMAL` 2 \| `IS_SEL` `$80` as last drawn; `IS_NONE` `$FF` = redraw (panel_init, potion count change) |
| `$BCAA` | `DAGGERS` | 1 | |
| `$BCAB` | `ARROWS` | 1 | |
| `$BCAC` | `HAS_BOW` | 1 | 0 / 1 |
| `$BCAD` | `QPIN` | 3 | quick pins |
| `$BCB0` | `LVL` | 1 | reserved 3D |
| `$BCB1` | `XP` | 2 | reserved 3D |
| `$BCB3` | `ARANK` | 2 | reserved 3D |
| `$BCB5` | `MP` / `$BCB6` `MAXMP` | 1 + 1 | reserved 3D |
| `$BCB7` | `CUR_REP` | 1 | C3-2: cursor auto-repeat countdown while FIRE is held |
| `$BCB8` | `TURN_HOLD` | 1 | C3-2: ticks a held ←/→ still waits after a turn-around (`TURN_DELAY` 10) |
| `$BCB9` | `INTENT` | 1 | C3-2: pending icon use (`IN_FIRE` 1) for the next INPUT tick |
| `$BCBA` | `SC_OLD` | 1 | C3-2: `PLAYER_SC` of the previous tick (shortcut edges) |
| `$BCBB` | `PAUSE_REQ` | 1 | C3-2: pause requests (FIRE+↑ / BREAK), counted by `pause_hook`; C3-6 replaces the hook |

**Inputs.** `JOY_*` bits = the Kempston layout, active-high: 0 R, 1 L, 2 D,
3 U, 4 F (`JOY_MASK` `$1F`; `KEMPSTON_PORT` `$1F`). **`JOY_MIRROR` `$BFEA`**
(state block, test-observable): while `INPUT_SRC` ≠ 0 the Kempston read takes
this byte instead of `IN ($1F)` (as `KBD_MATRIX` stands in for the keyboard).

**Input (C3-1, `src/io.asm`).** Per tick: `input_tick` (play_loop every
tick before the state dispatch; the hero-select loop each pass) =
`scan_matrix` (unchanged: `KBD_MATRIX`, kept as poked while `INPUT_SRC` ≠ 0)
+ `STICK_OLD` ← `STICK`, `STICK` ← `read_stick`; BREAK (CAPS + SPACE) clears FIRE (`SC_BREAK` has priority — C3-2
checks it first). `read_stick` → A = `JOY_*` bits, clobbers A, BC, DE, HL,
writes nothing: `KEYTAB` always, ORed with `sinc1_tab` / `sinc2_tab` (bank 2,
`KEYTAB` format on `KBROW_09876` / `KBROW_12345`: S1 = 7 / 6 / 8 / 9 / 0, S2 =
2 / 1 / 3 / 4 / 5 for R / L / D / U / F) in `JM_SINC1` / `JM_SINC2`, or with `IN
($1F)` (`JOY_MIRROR` while `INPUT_SRC` ≠ 0) in `JM_KEMPSTON` only. A Kempston
byte with any of bits 5-7 set is dropped (absent interface reads `$FF`);
accepted caveat (user-selected only): on a 128K / +2 without an interface the
floating bus can pass a byte with bits 5-7 = 0. `stick_tab`: `ld d,
KBD_MATRIX >> 8` / `ld e,(row byte)` / `ld a,(de)` — 57 T per entry. Measured
(W19, ZEsarUX, DI): `read_stick` keys 413 T, Kempston 479 T, Sinclair 824 T;
`input_tick` (injected, keys) 663 T; `sample_input` 523 T. `sample_input`
(reads only, after `input_tick`; `read_turn_input`, `end_screen`):
`PLAYER_DIR` = `STICK & JOY_DIRS` (`DIR_*` bits = `JOY_*` order: `DIR_S` 2 /
`DIR_N` 3), `PLAYER_DISC` (`DK_WAIT` = FIRE or `.`, ENTER, 1 / 2 / 3, G, C),
`PLAYER_SC` `$BFC9` (slot shortcut 1..10, I, BREAK); a selected Sinclair half
of the number row is masked out of `DK_1..3` / `PLAYER_SC` (S1: 6-0, S2:
1-5). Hero select reads the raw 1 / 2 keys (not masked; C3-6 replaces it).
Boot: `JOY_MODE` = `JM_KEYS`, `KEYTAB` = `keytab_defaults` (low RAM, macro
`KEYTAB_DEFAULTS`).

**Turn intents (C3-2; game.md §2.3 / §3.1 / §3.5; the FIRE-held cursor / FIRE+↓ bag parts are superseded by C3-2b "ICON MODE" below).** `intent_tick`
(`io.asm`, bank 2) runs every `GS_PLAYING` tick after `input_tick` (ANIM ticks
too) and calls `sample_input`; `read_turn_input` reuses its outputs. UI
events, never a turn: shortcut edges (`PLAYER_SC` vs `SC_OLD`; `SC_ENTER` bit 5
added) — BREAK → `pause_hook` + cancels a FIRE tap (priority over FIRE), I →
`NO BAG YET`, ENTER → `INTENT`, 1–0 → `sel_key`; FIRE held (`FIRE_ST`) — ←/→
(a diagonal's side) → `cursor_step` at once, again after `CUR_DELAY1` 10 ticks,
then every `CUR_DELAY2` 4; ↓ edge → `NO BAG YET`; ↑ edge → `pause_hook`; FIRE
released in `FS_TAP` (held < `FIRE_TAP_MAX` 10 ticks, nothing done) → `INTENT`
= `IN_FIRE`. While FIRE is held the stick never moves the hero. Turns
(`tpt_intent`, `logic.asm`, from `try_player_turn`): `INTENT` → `use_icon`
(far3) first; ↖/↗ jump; ←/→ (↙/↘ the same) against the facing = turn-around,
0 turns, and the held key then waits `TURN_DELAY` 10 ticks (`TURN_HOLD`)
before it walks; along the facing = `try_horizontal`; ↑ climb; ↓ climb else
wait; `.` wait; opposite keys cancel. Bank 7 since D3-7 T0 (`src/intent7.asm`, was bank-3 `intent3.asm`;
`slot_act_tab` / `slot_act` / `abil_rank` in bank-2 `icons.asm`): `slot_act_tab` (SA_* per class and slot), `slot_ok` (cursor stops: not
`SA_EMPTY`, abilities only with `ARANK` rank > 0; greyed icons stop),
`cursor_step` (wraps), `sel_key`, `use_icon` → `icon_jt`: melee = the faced
hostile in reach (`find_target` + `do_attack`), else `try_close` (replaces key
C), else `NO TARGET`; potion = `ic_quaff` (was bank-3 `try_quaff`, D3-7 T5) / `NO POTION`; daggers `NO
DAGGERS` at 0; bow `NO BOW` / `NO ARROWS`; food `NO FOOD`; scroll `NO SCROLL`;
bag `NO BAG YET`; unlearned ability `NOT LEARNED` (throw / shot / cast with
ammo or rank: D3-7 `abil_*`, see "Projectiles"); handlers return L = 1 turn used.
`hero_st_init` (new_game): `SEL_SLOT` / `FIRE_ST` / `FIRE_T`, `CUR_REP` ..
`PAUSE_REQ` = 0, `DAGGERS` 3 (Warrior) / 0, `ARROWS` / `HAS_BOW` / `ARANK` 0.
Measured (W22 / W23, ZEsarUX): `intent_tick` idle 826 T (the INPUT tick no
longer re-samples: net ≈ +0.3k T there, +0.8k in ANIM ticks), with a cursor
step 2.6k T; a FIRE melee turn's worst tick 83k T.

**Icon bar / info line / level digit (C3-3; game.md §3.3–3.5, §4.1;
concept-screen §5).** `icon_state(slot)` (`icons.asm`, bank 2) → `IS_HIDDEN`
(empty slot, unlearned ability: the empty outline), `IS_GREY` (daggers 0, bow
not found or 0 arrows, potions 0, quick food / scroll until 3E: all 6 attrs
`$07`), `IS_NORMAL` (melee, Bag, learned abilities, ammo / item > 0: the icon's
own attrs); the selected slot adds `IS_SEL` = PAPER blue on its 3 × 2 cells
(greyed + selected `$0F`). `panel_step` (HOT) → `icon_poll`: potions vs
`PANEL_POT_SH`, `LVL` vs `LVL_SH`, `icon_sig` vs `ICON_SIG` → `PD_ICONS`.
`item_icons`: a selection-only change → `sel_paint` (attrs, ~0.3k T, all
slots in one item); any other → ONE `slot_redraw` (bank 3 far3: pblit icon /
outline or the potion glyph + count digit, then grey / select attrs, ~3k T)
per item, `PD_ICONS` kept for the rest; any change → `PD_INFO`. 3D must set
`PD_ICONS` (or extend `icon_sig`) when learning / ranks / MP change a state.
`panel_more` (end of `panel_step`): `PD_INFO` → `item_info` (bank 1 since the review, 1st frame
only, ~25k T): row 20 bitmap cleared whole (`HUD4_EXT/PW` row 20 = 32), the
slot's `info_*` token string straight from the text block (`print6x`, pages bank 0 since D3-TX: no log
ring / MSG_BUF for the 42-char streams), then the potion count `X n` (char 16)
or the Bag's `LV n` (char 16) / `XP x/next` (char 28; `MSG_BUF` as plain-text
scratch); field attrs `$47` cols 0–11 / `$46` 12–20 / `$45` 21–31 (panel_init).
Level digit: `lvl_draw` at (31, 19), attr `$46`. `hero_st_init` sets `LVL` 1,
`XP` 0 (reserved state; 3D moves them). Strings (C3-3 edit of C3-4's):
`info_potion` "POTION … FIRE: DRINK", food / scroll "FIRE: EAT" / "FIRE: READ",
`info_bag` "BAG" (the numbers are live).

**ICON MODE (C3-2b; game.md §3.1 "ICON MODE", user 2026-10-05; replaces C3-2's
"FIRE held + ←/→" cursor and FIRE+↓ bag).** `intent_tick`: ↓ + FIRE, either
first and the other within `DN_DEFER` 3 ticks (`DN_T` / `FIRE_T`) →
`mode_enter`. In the mode: FIRE press → `INTENT` (`tpt_intent`: a use that
costs a turn leaves the mode, an illegal one prints its reason and stays); ↑ /
↓ press → `mode_exit` (+ `EXIT_LOCK`); BREAK → exit, no pause; ←/→ →
`cursor_step` (at once, +10, every 4); 1–0 select (both modes). Outside: FIRE
tap uses the selected icon; FIRE + any direction cancels the tap; FIRE + ↑ =
`pause_hook`; ↓ alone waits `DN_DEFER` ticks before the wait / climb-down
(`DN_COMMIT` if released earlier). `read_turn_input` does nothing in the mode
but a pending `INTENT`; `play_loop` skips `anim_tick` / `decor_tick` while the
mode is on in the INPUT phase (a turn already animating finishes first). Look:
the selected slot `IS_SEL | IS_MODE` = inverse attrs (ink → paper, blank
cells white paper; `sel_paint`), `icon_sig` bit 6; `item_info` prints `>` +
the line with its char 15 (a name pad space) dropped (`pre_get`, `PRE_N`), so
the fields stay on chars 16 / 28. Bank 3: 278 B free after C3-2b, **1,456 B** after the review's relief (scrolls + info line → bank 1).

**Menu, pause, cards (C3-6; bank 1 `menu1.asm`; game.md §3.1 / §3.2).**
`enter_select` → `show_bank5` + far1 `menu_run` (returns C = hero kind;
replaces bank 3's `sel_run`): torches (3-frame flame every
`MENU_TORCH_STEP` frames), the title, subtitle (6×8), the panel ornament on
row 6, items 1 START / 2 HERO: class / 3 CONTROLS (+ row 16 KEYS / KEMPSTON /
SINCLAIR 1 / 2, the chosen `JOY_MODE` on PAPER blue) / 4 REDEFINE KEYS (+ row
20 the KEYTAB names) in the 8×16 menu font, both hero idles (the chosen one
BRIGHT), the footer. Keys: 1–4 (`PLAYER_SC` digits, so a Sinclair half is
its joystick, not menu digits), ENTER / FIRE act on the `>` item, ↑ / ↓ move
it. The tests start through this menu (2 toggles HERO, 1 starts).
Redefine asks UP, DOWN, LEFT, RIGHT, FIRE: all keys released, then one key
(row byte + one-bit mask by construction); a key given this round → `KEY IN
USE`; KEYTAB is written only when all 5 are in. Every menu loop waits a frame
in `menu_wait` = `menu_frame` (bank 2: busy wait, the probe `select_tick`,
`input_tick`, and on any input change `MENU_SPIN` = `MENU_SPIN` × 2 + R +
`SYS_FRAMES`: the seed depends on every keypress's timing) + the torch step;
the pause loop calls `menu_frame` only (the torches sit in playfield row 0).
Redefine refuses the reserved keys (number row, ENTER, I, CAPS, SYM → `KEY
RESERVED`) and BREAK at a prompt cancels it (KEYTAB kept). Pause (`pause_hook`, bank 2): `show_bank5`, far1 `pause_run`
(rows 7-9 of bank 5 saved to `GEN_SRC` 864 B, the RESUME / QUIT box; ←/→,
FIRE / ENTER; BREAK resumes; QUIT → `QUIT? Y/N`, FIRE or Y = yes, any other
key = no) → L = 0: rows restored, `FIRE_ST` = USED + `SC_OLD` synced (the
resuming press is no tap), `present_full`, `resync_tick`; L = 1: SP reset,
`enter_select`. `end_screen`: once, far1 `end_card` (YOU DIED / YOU WIN!
rows 7-11 + PRESS 1-4 OR ENTER), after every key was released once (`END_SHOWN` 2, `keys_down`) any 1-0 / ENTER → the menu (C3-6b: not FIRE). The menu (`menu_run`) reads only the raw matrix (`menu_read`: 1-4 / ENTER edges, no cursor, `menu_sel` gone); `input_tick` yields STICK = 0 and never polls Kempston unless `GAME_STATE == GS_PLAYING` (the pause overlay runs in-game controls). `level_card`
(far1 from `level_show`): "DEPTH n" in the menu font at (12, 11). far1
clobbers A, so bank-1 results come back in L / C.


## 3D contracts (D3-0) — code against these symbols

`src/combat_defs.asm` (EQU / ASSERT only, INCLUDEd once by `defs.asm` after
`hero_defs.asm`) is the source; this table is authoritative. Plan "3D
breakdown" relief R1–R4; game.md §4.1, §5, §6.0, §6.4, §11.2, §11.4.

**Relief done in D3-0.** R1: the PROTO wizard zap is gone (`draw_zap`,
`zap_covered`, `draw_glyph`, `dt_zap`, `ZAP_T/ROW/COL/LEN` `$BF48..$BF4B`,
`E_ZAP` +23, `KF_ZAP` bit 5, `ZAP_GLYPHS` `$B200`, `wz_zap`; the wizard's
`KT_REACH` 3 → 1: a Mage with no spell has only the staff melee, game.md
§5 / §11.4; `WZ_WIND` stays, it is the melee's `KS_IMPACT`). AY reserve 7 →
4 KB (`AY_RESERVE` `$F000`). R4 (ZX0-packing the boot-only `vdata`) is NOT
done: measured `font6x8` 768 → 410 B, `tiles_common` 288 → 198 B (+ the
503-B hot image), ~0.5 KB of bank 1 for a lowram unpack-to-`GEN_SCRATCH`
helper (must clear `GEN_ZBLK`); due when D3-4's art (+1,322 B packed) meets
bank 1's 992 B free.

**State homes (R3), bank-2 runtime RAM** (not in the image / on tape; all
in FONT6 plane holes = offsets 0..31 / 224..255 of the font pages, ASSERTed
per record by `FONT6_HOLE`: one page per record, outside the font windows
and below `HOT_COPY`):

| Range | Symbol | Contents |
|---|---|---|
| `$B200..$B21F` | `FXT1` | **D3-5:** FX track 1 (32 B; was `ZAP_GLYPHS`) — layout below "FX engine (D3-5)" |
| `$B2E0..$B2FF` | `FXT0` (= `FXREC`) | **D3-5:** FX track 0 (32 B) |
| `$B300..$B30F` | `FXQ1` | **D3-5:** FX queue entry 1 (a 16-B descriptor) |
| `$B310..$B31F` | `ST_FLAGS` | STATUS per slot (game.md §6.4): bits 0-1 HOLD kind (`HOLD_FROZEN` 1 / `ASLEEP` 2 / `STUNNED` 3), 2-3 MIND kind (`MIND_FEAR` 1<<2, `MIND_CONFUSED` 2<<2), 4 POISON, 5 WEAK, 6 STUN_GUARD, 7 reserved; 0 = fast path |
| `$B3E0..$B3EF` | `ST_T1` | STMR1: hi nibble HOLD turns, lo MIND turns |
| `$B3F0..$B3FF` | `ST_T2` | STMR2: hi nibble POISON turns, lo WEAK turns |
| `$B400..$B40F` | `ST_X` | spare byte per slot (§6.4 "byte 3") |
| `$B410..$B41F` | `FXQ0` (= `FXQ`) | **D3-5:** FX queue entry 0 (FIFO head; a 16-B descriptor). D3-0's 2 × 8 B could not hold a 16-B descriptor |
| `$B4E0..$B4FD` | `RANK_ROWS` | the hero's current-rank rows, `RANK_N` 5 × `RR_STRIDE` 6 B (`RR_MP`, `RR_RANGE`, `RR_DIE`, `RR_BONUS`, `RR_BOUNCE`, `RR_EFFECT`), row k = ability k (ARANK bits 2k..2k+1); copied from the bank-3 rank table on learn / rank-up (D3-9b) |
| `$B4FE` / `$B4FF` | `FX_BUSY` / `FXQ_N` | **D3-5:** bit i = FX track i live or still drawn (0 = FX idle: `turn_done` waits for it) / queued descriptors 0..2 |
| `$B500..$B51F` | `FXT2` | **D3-5:** FX track 2 (32 B). No FONT6 hole is free any more |
| `$BC4A..$BC50` | `TURN_PEND` block (D3-7) | `TURN_PEND` +0 (bit 0 `TP_ACT` ability logic pending, bit 1 `TP_MON` monster phase pending, bit 2 `TP_FIRE` this is the fire tick), `ACT_ABL` +1 (`ABL_*` pending), `ACT_AT` +2 (`TURN_TICK` of the release, fire tick f = `ACT_FIRE_TICK` 2), `MON_AT` +3 (≠ 0: monster phase deferred, its earliest `TURN_TICK` f + 1; it runs once the hero's FX is idle, designer 2026-10-12), `FX_DROP` +4 (T1: descriptors `fx_start` dropped, mod 256; tests assert 0), **T7:** `LOG_TURN` +5 (log drain: bit 0 `LT_SERVED` = `item_log` drew a line since the turn started, bit 1 `LT_HOLD` = `end_turn` holds the next turn), `LOG_PDIR` +6 (T7 review: the input a hold swallowed — `PLAYER_DIR` bits 0-3, bit 7 = `DK_WAIT` — replayed when the key was released during the hold; "Log drain (T7)" under "Projectiles"). Zeroed by `level_reset_new` (`HERO3D..TURN_PEND_END`). Contract under "Projectiles" |
| `$BC41..$BC49` | `HERO3D` | `MP_RG` +0 (MP regen counter), `HERO_RES` +1 (3 B, RES format), `HERO_IMM` +4 (`IMMF_*`; ASSERT = `HERO_RES + KX_IMM`: deal_hit reads hero and kx row alike), `MP_SH` +5 (panel MP as drawn), `STAT_SH` +6 (status icons as drawn), **D3-6a:** `HERO_DEF` +7 (hero DEF: Warrior 1 Leather / Mage 0, set by `hero_st_init`; gear in 3E), `XP_UP` +8 (1 = `deal_hit` added XP; D3-9's level-up check clears it); `$BC4A..$BC50` = `TURN_PEND` (row above), `$BC51..$BC5E` free |

`ST_*` arrays: byte = array + slot (`P_MAX_ENT` 16); `ST_FLAGS` / `ST_T1` /
`ST_T2` share page `$B3` (ASSERT). **HERO_CARRY:** slot 0 carries over a
descend; `level_reset` clears slots 1..15 of all four arrays (~1.4k T, once
per level); `level_reset_new` (new_game) also clears slot 0 and `HERO3D`.
`RANK_ROWS` is not initialised yet (its owner does it). The FX state is
reset by `vis_reset` (`fx_reset`) and `hide_sprites` (`fx_hide`).

**FX engine (D3-5)** (`src/fx.asm`, bank 2; game.md §6, plan "3D breakdown"
decision P). Render-only tracks: no entity slot, no kind row. A track record
(`FXT0..2`, 32 B, one FONT6 hole each, IX + field) = the caller's 16-B
descriptor (+0..15, copied by `fx_start`, mutated by the flight) + the render
state (+16..31):

| Off | Field | Meaning |
|---|---|---|
| +0 / +1 | `FXD_FIDA` / `FXD_FIDB` | flight frame on even / odd visible ticks (`FX_NONE` $FF: no sprite — impact-only FX) |
| +2 / +3 | `FXD_IMPA` / `FXD_IMPB` | impact frames, alternating (`FXD_IMPA` = `FX_NONE`: no impact) |
| +4 | `FXD_ATTR` | 0 = each frame's own attr (`fx_meta`, the sheet's `ATTR_SPRITE`), else this attr for all |
| +5 / +6 | `FXD_COL` / `FXD_ROW` | anchor cell (the frames' 8-px body cell; 16-wide frames reach one cell ahead: right c..c+1, left c−1..c) / flight row (frame top = row − ay/8; the 16×16 bursts have ay 8) |
| +7 | `FXD_FLAGS` | bit 0 `FXDF_LEFT` (flips at every reversal), bit 1 `FXDF_FAST` (16 px = 2 cells per tick) |
| +8 / +9 | `FXD_DELAY` / `FXD_IMPT` | hidden ticks before the first frame / impact ticks |
| +10 / +11..15 | `FXD_NSEG` / `FXD_SEGS` | 1..5 segments of n cells (0 allowed), a reversal between each (bounce / reflect: precomputed by `proj_fire`) |
| +16 / +17 | `FX_ST` / `FX_PH` | `FXS_IDLE` 0 / `WAIT` 1 / `FLY` 2 / `IMP` 3; frame alternation phase |
| +18..24 | `FX_FID`, `FX_ATTR`, `FX_LEFT`, `FX_COL`, `FX_ROW`, `FX_COLS`, `FX_ROWS` | desired (written by `fx_tick`; FX frames are cell-aligned, ASSERTed: position = footprint) |
| +25..31 | `FX_DFID` … `FX_DROWS` | drawn, same order (`FX_DFID` = `FX_NONE`: not on the bank-5 screen) |

Timeline (`fx_tick` #k from the first after `fx_start`): #0..d−1 hidden, #d
first flight frame at the anchor, then one step per tick (2 cells fast; a
finished segment reverses first, mid-tick if need be), the impact on the last
cell at #d+⌈n/s⌉+1 for `FXD_IMPT` ticks, then idle; `fx_start` returns that
impact tick in A (= the target's `E_REACTAT` when called in a turn's input
tick). Render: `fx_erase` at the end of phase 2 (changed FX erased from the
clean background, rect in the damage list before `DMG_PRES_N`: presented,
bodies under it repaired), `fx_draw` after the player (FX drawn last;
unchanged FX re-blitted only when a damage rect touches it; new footprints
`pmark_rect`ed). `decor_tick` skips cells under a drawn FX (`fx_occ`). Queue:
3 tracks + 2 queued; more → `fx_start` CF = 0 (dropped). Measured per tick,
one track, no body under it (tests: scratch script, fx_tick + fx_erase +
fx_draw): 8×8 5.4k T, 16×8 6.0–6.1k, 16×16 burst 7.5k (held frame 5.7k
first draw, ~0.25k after); FX idle: ~130 T per tick (3 `FX_BUSY` tests +
`decor_tick`'s `fx_occ`); a busy hidden track ~0.9k. Tests: `tests/combat.py` C1,
`tests/flicker.py` d, `tests/budget.py` "lightning".

**Damage types / resistance record** (`KX_RES`, `HERO_RES`, 3 B): `DTY_PHYS`
0, `FIRE` 1, `COLD` 2, `SHOCK` 3, `DRAIN` 4, `DARK` 5; 2-bit response
`RSP_N` 0 / `RSP_R` 1 / `RSP_I` 2 / `RSP_X` 3: byte 0 = PHYS 1-0, FIRE 3-2,
COLD 5-4, SHOCK 7-6; byte 1 = DRAIN 1-0, DARK 3-2; byte 2 = weak mask (bit t
= ×2 to type t). The hero's gear combine (3E) is a per-field max, not OR.
Immunity mask `IMMF_SLEEP` 1, `STUN` 2, `CONFUSE` 4, `FEAR` 8, `POISON` 16.

**KX (R2), bank 3:** `kx_tab` (first thing in `bank3.asm`, `$C000` at D3-0;
ASSERT one page), `K_MAX` 32 rows × `KX_STRIDE` 6 B = `KX_LEN` 192 B: `KX_RES`
+0 (3 B), `KX_IMM` +3, `KX_XP` +4 (KXP, game.md §4.1), `KX_DEF` +5 (0 in 3D,
§11.4). Row = `kx_tab + kind * 6` (`ld h, kx_tab >> 8`, L = kind × 6). Read
by bank-3 combat code only. Reserved as zeros (`DS`); data rows in D3-1.

**Combat core (D3-6a, `src/combat3.asm`, bank 3, after `turn3.asm`).**
`hit_roll` (IX attacker, A target slot, B signed to-hit modifier → A 1/0 +
Z; one d20; held target = eva 0) and `deal_hit` (IX attacker, A target slot,
B dmg rolled, C = `DTY_*` | `DH_NODEF` (bit 3) | `EFX_*` << 4 | `DH_HEAL`
(bit 7), E = effect param in the `RK_EFFECT` status format (hi nibble 1-in-N
chance, 0 = always; lo nibble turns) → L = HP lost; clobbers all but IX).
EQUs in `combat_defs.asm`. Data: `kx_melee` (per kind {C, E}, stride 2,
`K_COUNT` rows: the melee hit's type + on-hit effect; Ghost DRAIN + CONFUSED
4 at 1 in 4), `efx_tab` (per effect id 1..7, 6 B: immunity bit, STATUS mask
/ value, timer field, hero line, monster suffix). Scratch `dh_*` (13 B) is
bank-3 RAM next to the code (not re-entrant). Monster lines go through
`impact_line` codes `MSG_M_UNAFF` 7 .. `MSG_M_THAW` 14 (lowram `imp_pre` /
`imp_post` +16 B). `do_attack` is now hit_roll → 1dN + bonus → deal_hit.
Not yet: the BOSS halving / immunity (no BOSS flag before 3F), WEAK's
atk/eva/dmg penalties (D3-8). Bank 3: 1,589 B free after D3-6a (was 2,324;
+735: `combat3.asm` ~765 incl. 81 B tables + 13 B scratch, `do_attack` −30);
low RAM spare 384 (was 400). Test: `tests/combat3.py` C0–C10.

**Projectiles (D3-6b, `src/proj3.asm`, bank 3, after `combat3.asm`).**
`proj_fire` (IX = caster, A = `ABL_*` with a projectile, HL = its 6-B rank
row (`RANK_ROWS` / `ab_rank` / `ab_ammo`, `RK_*`), E = `FXD_DELAY`; LIVE_LIST
current → L = `pf_stop`; clobbers all but IX) resolves the whole flight at
cast time (game.md §6 "Logic", §6.0) and starts ONE FX track
(`pf_desc` → `fx_start`; segments = the precomputed path, a reversal between
each). Contract EQUs in `combat_defs.asm`: `PFS_RANGE` 0 / `WALL` 1 / `BODY`
2 / `ABSORB` 3 / `EXIT` 4 / `LOOP` 5, `PF_MAXREV` 4 (= `FXD_SEGMAX` − 1),
`PF_ROW_DY` 2 (flight row = caster top + 2), `PF_IMPT` 2. Rules as built:
start = the caster's leading col (not counted), range = cells entered;
solid next cell → bounce (range kept) or stop on the free cell in front;
col 0 / 31 not solid = open exit (entered, no impact); bodies = the
LIVE_LIST bodies whose rows overlap the caster's (slot order), each once
per pass; mid-ladder absorbs; `RSP_X` reverses at its front cell (no bounce
used); spells always hit (deal_hit: I = 0 dmg), missiles roll `hit_roll`
(`ABD_HIT`) and fly on when they miss; Lightning pierces; the caster is a
target after the first reversal; Firebolt's burst hits every body within 1
col of the impact except the stopper (the caster unless `RKE_SPARE`); each
struck body's `E_REACTAT` = `TURN_TICK` + `FXD_DELAY` + ⌈moves / speed⌉ + 1
(fx_start's impact formula from the cast's tick; D3-7 T1 added `TURN_TICK`,
0 on the input tick, so a cast at the release tick lines up too). `deal_hit`'s
C per ability = `pf_dhc_tab` (bank 3, 9 B). Results (D3-7, tests): `pf_stop`,
`pf_col` (impact col; a miss lands there), `pf_tgt` / `pf_lost` (first body
hit, $FF none), **T7: `pf_miss`** (first body a missile missed, $FF none; every
missed body gets `RC_DODGE` at the tick the FX passes its first col unless a
reaction is pending — `anim_entity` turns it into an `ATTR_MISS` $46 flash for
`MISS_FLASH` 3 ticks, no sequence; a later hit's HURT / DEATH, or a melee miss's BLOCK on the Knight, overwrites it), `pf_stopper`, `pf_itick`, `pf_desc`.
**`PF_RAM` `$5E00..$5EFF`** (bank 5, runtime only, not on tape: the dead
BASIC area after boot; `PF_RAM_LEN` $100): the `pf_*` scratch / results +
descriptor + candidate list `$5E00..$5E5D` (T7: + `pf_miss`, was `..$5E5C`), `PF_ROWF` `$5EE0..$5EFF` (the
flight row's flags: TF_SOLID, edge, candidate cols — the fast-forward over
plain cells); **D3-7: `ABIL_DESC` `$5E60..$5E6F`** (16 B: the `ab_def` row (`ABD_*`, 10 B) then `ABIL_RK` the rank row (`RK_*`, 6 B: `ab_rank` at the hero's rank, or `ab_ammo`), filled by `abil_load` (bank 3) for the bank-7 ability code, which cannot read bank 3; D3-7 T4: also the scratch FX descriptor of `melee_bonk` (a melee turn has no ability pending); ASSERTed clear of the `pf_*` block and `PF_ROWF`; `$5E5D..$5E5F` / `$5E72..$5EDF` stay free); **D3-7 T5: `ABIL_TGT` `$5E70..$5E71`** (word: the power attack's target slot mask, bit s = slot s, written by `abil_melee` at the accept, read by `power_fire` on the fire tick — no second scan; ASSERTed below `PF_ROWF`). Contended, as is the bank-3 code: measured 10–30k T a typical
cast, worst seen ~66k T (Lightning r3 through 4 bodies, 3 passes, deal_hit
messages); D3-7 must budget the cast tick. Not done (bank 3 was full, 30 B
free): impact-only flashes on pierced bodies.
**Split ability turn (D3-7 T1, built; designer 2026-10-12, game.md §2.2 / §6.1;
`src/act7.asm`, bank 7):**
- **Input tick (`TURN_TICK` 0):** the ability's accept (`abil_spell` /
  `abil_melee` / `abil_ammo`, T4/T6) validates, calls **`act_begin`** (IX =
  hero, B = `ABL_*` → L = 1: `TURN_PEND` = `TP_ACT | TP_MON`, `ACT_ABL`,
  `ACT_AT` = `ACT_FIRE_TICK` 2, `MON_AT` = 3; L = 0 refused, nothing changed:
  the hero's lead col is 0 / 31, no turn), then pays the cost and starts the
  sequence. `turn_input` skips `resolve_monsters` while `MON_AT` ≠ 0.
- **Hook:** `anim_gate` (bank 2) starts with `ld a,(TURN_PEND) / or a / call nz,
  pend_far` (idle 27 T) → far7 **`act_pend`**, before `anim_tick` / `fx_tick`.
- **Fire tick f** (`TURN_TICK` == `ACT_AT`): `TP_ACT` → `TP_FIRE` (bit 2: the
  play loop skips the panel item and `decor_gate` skips `decor_tick` this tick,
  as on the input tick), `probe_act_fire` (bank-2 `ret`, budget probe), then
  **`act_fire`** (A = `ACT_ABL`): lead col 1..30 else fizzle (L = 0, the turn
  stands); `ABL_DAGGER` / `ABL_BOW` → `ammo_fire`, else `spell_fire`;
  **T5: `ABL_POWER` / `ABL_WHIRL` → `power_fire` first, without the lead-col
  guard** (no projectile; their accept uses `act_begin_ok`, the same block
  write without the guard) (IX = hero, B = `ABL_*`, `ABIL_DESC` from the
  accept; T1 stubs: L = 1). A cast here calls `proj_fire` with E = 0 (the
  projectile appears now).
- **Monster phase:** the first later tick with `TURN_TICK` ≥ `MON_AT` and
  `FX_BUSY` = 0 (the hero's FX shown and erased): `TURN_PEND` = `MON_AT` = 0,
  then far3 `resolve_monsters` unless the hero is DYING. Monsters stand still
  for the whole flight.
- **Time base:** `TURN_TICK` is 0 throughout INPUT (`turn_input` before
  `try_player_turn`, `end_turn`); `set_reaction_at` (impact tick +
  `TURN_TICK`) and `pf_tick` add it, so input-tick logic is byte-identical and
  later-tick logic (release, deferred monsters) lines its reactions up.
- `turn_done` returns CF = 0 while `TURN_PEND` ≠ 0. `FX_DROP` counts every
  descriptor `fx_start` drops (tests assert 0).
- **Spells (D3-7 T4, `src/abil_spell7.asm`, bank 7).** `abil_spell` (the
  accept, IX = hero, B = `ABL_SPARK..ABL_LIGHTNING` = k): refusals L = 0 +
  message, no turn — unlearned `TX_NOT_LEARNED`, `MP` < the `RANK_ROWS` row's
  `RR_MP` `TX_NO_MANA`, mid-ladder `TX_NO_TARGET`; `act_begin`'s lead col
  0 / 31: L = 0, no message. Accept: `act_begin`, `MP` −= `RR_MP`,
  `PANEL_DIRTY` |= `PD_MP` (`PD_MP_BIT` 1; no MP item drawn yet, the panel
  clears it), `start_seq` of the `abl_seq` row (`wz_cast`), the hero flashes
  `ABIL_DESC + ABD_AT1` (the spell ink) for `SPELL_FLASH` 5 ticks (the whole
  cast). **`spell_fire`** (the release): far3 **`proj_rel`** (bank 3,
  `rank3.asm`: A = `ABL_*`, DE = the 6-B rank row → `proj_fire` with HL = DE,
  E = 0; far3 takes HL as its target) with the `RANK_ROWS` row k; Drain Life
  with `pf_tgt` ∉ {0, $FF} and `pf_lost` > 0: the hero flashes `ATTR_HEAL`
  from the release to `FLASH_TICKS` after `pf_itick`. L = 1.
  **Rulings applied in `proj3.asm` (T4, game.md §6 "Logic"):** no Firebolt
  burst after `PFS_ABSORB` (was: only `PFS_EXIT` skipped it); Drain Life
  striking its own caster deals a normal DRAIN hit with `DH_HEAL` masked (no
  self-heal; `pf_strike` compares `pf_cur` with `pf_cslot`). `tests/proj3.py`
  model + P6 cases follow.
- **Staff bonk (D3-7 T4, `melee_bonk`, `abil_melee7.asm`).** After
  `ic_melee`'s blow: a Mage (`E_KIND` = `K_WIZARD`) swing re-starts as
  `wz_bonk` (CAST1 2 → STAFF_SWING 3; same `KS_IMPACT` = `WZ_WIND` 2 as
  `wz_attack`, so `E_REACTAT` stands); on a hit (`E_HIT` = 1) an impact-only
  FX is built in **`ABIL_DESC`** (scratch: no ability is pending in a melee
  turn) and `fx_start`ed: FIDA/B = `FX_NONE`, IMPA/B = `FID_staff_bonk`,
  attr 0, col = the target's front col (facing the hero), row = the staff
  row (hero top + `PF_ROW_DY`) clamped to [target top, target bottom − 1],
  `FXDF_LEFT` = the hero's facing, **`FXD_DELAY` = `WZ_WIND` − 1** (an
  impact-only FX shows its impact at fx_tick #delay + 1, i.e. on
  `KS_IMPACT`, the target's `E_REACTAT`), `FXD_IMPT` = `PF_IMPT`, 1 segment
  of 0 cells.
- **Power attacks (D3-7 T5, `src/abil_melee7.asm`, bank 7; game.md §6.2).**
  `abil_melee` (the accept, IX = hero, B = `ABL_POWER` / `ABL_WHIRL`):
  refusals L = 0 + message, no turn, no MP — unlearned `TX_NOT_LEARNED`
  (`abil_rank` k = B − `ABL_POWER`), `MP` < `ABIL_RK + RK_MP` `TX_NO_MANA`,
  mid-ladder or no target `TX_NO_TARGET`. Targets = **`melee_scan`**:
  `find_target`'s rules (reach, the body-row overlap, a nearer mid-ladder body
  blocks); Power Strike the nearest in the facing, Whirlwind every one on
  both sides (a found body leaves the scan by a cleared `EF_HOSTILE`, all
  restored by `mask_hostile` before the return; several can share a side —
  a Bat over a Rat) → DE = slot mask → `ABIL_TGT`. Accept: `act_begin_ok`,
  `MP` −= `RK_MP`, `PD_MP`, `act_seq` (`kn_power` / `kn_whirl`: WIND-UP 2 →
  POWER_STRIKE / WHIRL 3, `SF_IMPACT` on tick 2). **`power_fire`** (fire tick
  2, before `anim_tick` runs the `SF_IMPACT`): the hero's `E_MSG` / `E_HIT` =
  0 (`do_impact` then adds nothing), one **`melee_strike`** per `ABIL_TGT`
  slot in slot order (**T7:** a slot DYING / HP 0 by then is skipped — no
  roll, no line; Power Strike stops after its one target: its `imp_fx`
  overwrites `ABIL_DESC`, ASSERTed `ABD_FLAGS` / `ABIL_RK` < `FXD_LEN`;
  `P_MAX_ENT` ≤ 16 ASSERTed for the mask): far3 **`melee_hit`** (bank 3: `hit_roll` with B =
  `ABD_HIT` (+2 Power) + Whirlwind's `RK_EFFECT` (rank-3 to-hit +2); dmg =
  1d`KT_DIE` + `KT_BONUS` (the hero kind's weapon) + `RK_BONUS`, ×2
  saturating with `ABF_DMGX2`; `deal_hit` C = `ABD_DTY`, Power Strike `|
  EFX_STUNNED`, E = `RK_EFFECT` (chance 0, turns 1 / 1 / 2: survivors only,
  R halves, IMMF_STUN / STUN_GUARD refuse; the §6.4 BOSS halving comes with
  3F's BOSS flag); RNG per target d20, 1dN, then deal_hit's) → HP lost: the
  target flashes `ATTR_HIT`, `E_REACTAT` = `TURN_TICK` (its HURT / DEATH under
  the strike frame; `set_reaction_at` had added the Knight's `KS_IMPACT`);
  `impact_line` "YOU HIT / MISS / KILL THE <kind>" per target (after
  deal_hit's status lines); Power Strike + HP lost: **power_burst** on the
  target (`front_cell`: its front col, the staff row clamped into its body —
  the staff-bonk placement). Whirlwind: **spark_fizz** at `x − 1` (facing
  left) and `x + w` on the staff row, hit or not (the sweep). Both FX via
  **`imp_fx`** (descriptor in `ABIL_DESC`, IF1 / IF2 read first): FIDA = IF1,
  IMPA = IF2, `FXD_DELAY` 0, `FXD_IMPT` 1 → IF1 set on the strike tick, IF2
  the next, idle after (the monster phase then). Cost: accept ~4–20k T
  (`melee_scan`: ~4k per `find_target`, contended), fire tick ~1k + ~6–9k
  per target + ~1.5k per FX. **Scenario "wcast"** (`tests/budget.py`):
  Whirlwind r3 on 3 bodies (Skeleton left, Rat + Bat right) ×3 turns: cast
  ticks max **104.9k T** (fire ticks 57–105k; the third turn's render
  carries 3 HURTs), ordinary max 112.1k (an accept tick). Note (T6): in that
  scenario the log never drained (`LOG_QN` 4, `LQ_DROP` 14 over 3 turns): the
  log item runs only in a tick's first frame, and every tick there is heavy.
  **T7: fixed by the log drain rules below (0 dropped).**
  Tests: `tests/abil_melee.py` R1–R4 (refusals), P1–P6 (Power Strike per
  rank, Slime R, kill, miss), W1–W3 (Whirlwind both sides, two bodies on
  one side, out-of-reach body untouched, ranks) vs a Python model.
- **Dagger throw / bow shot (D3-7 T6, `src/abil_ammo7.asm`, bank 7; game.md
  §6.3).** `abil_ammo` (the accept, IX = hero, B = `ABL_DAGGER` /
  `ABL_BOW`; `ic_daggers` / `ic_bow` already refused `NO DAGGERS` / `NO BOW` /
  `NO ARROWS` at no turn): mid-ladder `TX_NO_TARGET` (L = 0); `act_begin`'s
  lead col 0 / 31: L = 0, no message. Accept: `act_begin`, `DAGGERS` /
  `ARROWS` −= 1 (spent at the accept, as MP), `PANEL_DIRTY` |= `PD_AMMO`
  (no ammo item drawn yet: the panel clears it; the icons grey through
  `ICON_SIG`), `act_seq` (`kn_throw` WIND-UP 2 → THROW 3 / `kn_bow` BOW 4;
  the release on tick 2). Legal with no target. **`ammo_fire`** (fire tick):
  far3 `proj_rel` with DE = `ABIL_RK` (the `ab_ammo` row `abil_load` copied
  at the accept: dagger r6 1d4+2, bow r14 1d6+1; to-hit `ABD_HIT` +1 / 0;
  PHYS; no bounces: a wall stops it on the free cell in front; a failed roll
  flies on), then the lines (**T7**: `pf_miss` a monster other than the body hit →
  `YOUR DAGGER / ARROW MISSES THE <kind>` first); `pf_tgt` a monster → `YOUR DAGGER / ARROW HITS
  THE <kind>` (composed in `MSG_BUF` from `tx_dec` pieces: bank-7 code cannot
  page the text block; plain ASCII is a valid log stream) or `YOU KILL THE
  <kind>` (`impact_line` `MSG_P_KILL`); `$FF` → `YOUR DAGGER / ARROW MISSES` unless the named miss line went out;
  the hero (a reflection) → deal_hit's line only. **3D: the spent ammo is
  consumed** (game.md §11.4); §6.3's floor drop / 1-in-4 loss / 50 % arrow
  recovery come with the 3E floor-item records (no RNG drawn for it now).
  Cost: accept ~1k T; fire tick ~2–3k + proj_fire. **Scenario "acast"**
  (`tests/budget.py`): bow shots into Rat, Goblin, Slime, Skeleton in line.
- **Floor pickup (D3-7 T6, `src/pickup7.asm`).** `floor_pickup` (end_turn;
  replaces `potion_pickup`, which keyed on the map tile, and the
  `ammo_pickup` stub): the hero standing, not DYING; every `FLOOR_LIST`
  entry of `CUR_ROOM` on his storey whose col the body covers, in list
  order, by its own rule (game.md §6.3 shared cells): `IT_POTION` with
  `E_POT` < 9 → `pp_take` (as before: `FL_EMPTY`, `POTIONS_TAKEN` bit =
  index < 8, `YOU PICK UP A POTION`); `IT_DAGGER` / `IT_ARROW`, Warrior
  only → `ap_take`: min(`FL_QTY`, cap − counter) (`DAGGERS_MAX` 9 /
  `ARROWS_MAX` 24; arrows without the bow too), `YOU PICK UP n DAGGER(S) /
  ARROW(S)` if n > 0, emptied → `FL_EMPTY`, a remainder (also n = 0) →
  `QUIVER FULL` (every turn the hero ends on it). Every taken / matched
  entry → **`ap_stamp`** (C = col, E = room byte): the cell = the last live
  entry there in list order (`T_POTION` / `T_DAGGERS` / `T_ARROWS`) else
  `T_AIR`, `queue_damage` + `shadow_rect` (tail: leaves bank 7 paged).
  `build_room_map` stamps `IT_DAGGER` / `IT_ARROW` like potions (list
  order: the last entry of a shared cell shows). **T7:** a pre-filter reads
  the body's cells on row 9s+7 first and returns unless one is `T_POTION` /
  `T_DAGGERS` / `T_ARROWS` (invariant: every live entry shows on its cell —
  `build_room_map` stamps them, `ap_stamp` re-stamps after a pickup, decor
  lands on `T_AIR` only; written down at `level_defs.asm` FLOOR_LIST and checked by `tests/gfx_integrity.py` `floor_check` / `floor_build_check`, D1..D8); an ammo glyph counts for the Warrior only; `ap_take` sets `PD_AMMO` when it took any. Cost:
  ~0.4k T a turn with no item glyph under the body (T6: ~3k T), + ~3–6k T per entry taken. No floor generation of ammo
  yet (game.md §8.5: a later task); tests poke the entries.
  Tests: `tests/abil_ammo.py` R1–R4, F1–F7, D1, P1–P5, B1; T7: G (the miss sweep), P6–P10.
- **Edge clamp (T7, `render`, `anim.asm` `.offr` / `.edge`).** A frame wider
  than the body (the Knight's 40-px WHIRL / POWER_STRIKE / SLASH) at col 0 or 29
  wrapped below x 0 / ran past x 255: `blit_clip` counted `CLIP_TRAP` and the
  hero was not drawn. The frame x is now clamped into the screen keeping its
  shift (`fpx & 4`: a STATIONARY ax-4 frame has only shift 4): x 0 / 4 at the
  left, 256 − W − shift at the right. +30 T per drawn slot (the test:
  `fpx + W` carry), ~70 T when it clamps. Tests: `tests/abil_melee.py` E
  (Power / Whirlwind / SLASH at cols 0 and 29: `CLIP_TRAP` 0, was 6–12).
- **Log drain (T7; reworked after review).** With every tick of a turn in its
  2nd frame (a heavy fight) `panel_tick` never draws a log line and the
  4-slot ring dropped the newest (`wcast` 3 turns: `LQ_DROP` 14). Two rules:
  (1) `act_pend` defers the monster phase while `LOG_QN` > `LOG_MON_MAX` **0**,
  at most `LOG_WAIT_MAX` 8 ticks past `MON_AT`; it draws NOTHING itself —
  `panel_tick`'s 1st-frame rule drains the cast's lines on the light rest
  ticks (the first pass drew a line in `act_pend`: on a heavy repaint tick
  that passed the cast cap in "wcast4", 145.6k T). `ROOM_CAP` + `LOG_MON_MAX`
  ≤ `LOG_SLOTS` is ASSERTed: the replies' melee lines (one per impact tick)
  fit; the residual is deal_hit's on-hit status lines at resolve time (3D:
  the Ghost's 1-in-4 CONFUSED), dropped and counted, never a corrupt ring.
  (2) `end_turn` sets `LT_HOLD` when ≥ `LOG_HOLD_MIN` 2 lines are pending, or
  any is pending and none was drawn since the turn started (`LT_SERVED`, set
  by `item_log`, cleared when a turn starts) — `turn_input` then draws one
  line a tick (an idle tick: no turn logic) and starts no turn until the
  queue is empty. `INTENT` and a held key are kept; a key released during the
  hold is latched in `LOG_PDIR` and replayed (review: a 1-tick tap was lost).
  Lines `end_turn` itself pushes (pickup, death) do not count.
  Measured (`tests/budget.py`): "wcast" `LQ_DROP` 14 → **0**, cast max 105.1k
  → 96.5k T, ordinary max 115.6k; **"wcast4"** (Whirlwind r3 on 2 Skeletons +
  Goblin + Rat, `ROOM_CAP`, all in reach, 2 per side overlapping; gated):
  cast max **118.3k T** (cap 128k), ordinary max 120.0k (cap 126k), 0
  dropped; "acast" / "lcast" unchanged. Tests: `tests/abil_melee.py` L (3
  Whirlwind turns, FIRE tapped: 0 dropped, 17 before), `tests/abil_ammo.py`
  H (a 1-tick Right / WAIT tap during a hold runs after the drain).
- **Budget class "cast"** (`tests/budget.py`): ticks from the fire tick
  (`probe_act_fire`) to the one that clears `TURN_PEND` are gated at
  `CAST_CAP` 128,000 T (hard limit 141,816); every other tick keeps 126k.
  Scenario "cast" = "lightning" with the `TURN_PEND` block poked as
  `act_begin` leaves it (T4: its Lightning row poked to range 0, so it stays
  the engine-only measurement). **Scenario "lcast" (T4)**: the real cast
  through the controls — Lightning r3 from x 14 facing left through 4
  monsters to the left wall and back through all 4 + the caster (9 hits):
  fire tick **~125.9k T** (proj_fire part ~89k), 2.1k under `CAST_CAP`;
  `FX_DROP` 0, `LQ_DROP` 0. If it ever passes the cap: defer the hero-hit
  `deal_hit` messages or move the `pf_*` walk helpers out of contended bank 3.
Test: `tests/proj3.py` P0–P8
(the game.md §6.1 / §6.3 table at every rank + a 120-case fuzz vs a Python
model of the rules); P9 the split turn (`TURN_TICK` shift of `pf_itick` /
`E_REACTAT` / `set_reaction_at`, the `act_begin` / `act_fire` lead-col guard,
`FX_DROP`).

**Text ids:** `tx_ptr` indexes 16-bit since D3-0 — ids 0..255 (`TX_COUNT`
≤ 256), `tx_ptr_hl` takes an HL id for the later > 256 path (see "Text").

**Class FX kinds (D3-4)** (`src/frames.asm`, `defs.asm`): the projectile /
impact sprites (game.md §6.1–6.3) are two render-only kinds at the top of the
kind ids, `K_FXW` 30 (= `K_FX_BASE` + `K_KNIGHT`) and `K_FXM` 31 (=
`K_FX_BASE` + `K_WIZARD`); no entity ever has them, only `KT_FID0` /
`KT_FCNT` are set (`KROWFX`). `start_game` generates the hero's kind and then
`gen_kind(HERO_KIND + K_FX_BASE)` above the select mark, so the pool holds
only the current class's FX (Warrior 352 B, Mage 1,152 B; `POOL_NEED` uses
max(Knight + `K_FXW`, Wizard + `K_FXM`)). Their fid ranges **overlap** on
`spark_fizz1/2` (Spark impact = Whirlwind impact): fids `KFID_FXM` 78 ..
`KFID_FXM + KFCNT_FXM` = 78..94 (15 Mage-only + the shared pair 93/94),
`K_FXW` = 93..100 (shared pair + `power_burst`, `dagger_spin1/2`,
`arrow_fly1/2`, `arrow_hit`). Every FX frame: ax 0, body width 8 (one cell),
STATIONARY (one shift per facing, pool = 2 × source); `drain_hit` /
`power_burst` are SYM (mirror-symmetric art: left = right). `ab_def`'s
`FXF_*` (bank 3, `combat_data3.asm`) name them; ASSERTed inside the owning
class's range. The Warrior's THROW / BOW / WHIRL (ax 8) / POWER_STRIKE (ax 4)
are ordinary `K_KNIGHT` frames (fids 16..19). Values above from the `.sym`
at D3-4; code reads the symbols. Checked by `tests/frames_d3.py` (static),
`tests/zx0_pool.py` (pool bit-exact incl. the FX kind), `tests/gfx_integrity.py`
(FX resident at the hero start), `tests/combat_tables.py` (`ab_def` fids).

**Status icons (D3-4, data only; D3-8 draws them):** `status_icons` in the
bank-1 `vdata` block (after `orn_glyphs`; read through `copy_virt3`), 7 × 8 B
glyphs in the order FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR, POISON, WEAK
(= `status_icons + 8i`), then `status_icons_attr` 7 B ($45, $41, $07, $43,
$42, $44, $42); 63 B ASSERTed (`assets/gfx/sprites/status_icons.asm`,
generated by `tools/svg_sprites.py` from the D3-3 sheet).

**Headroom after D3-7 T7** (build DISPLAY, incl. the review follow-up): bank 3
**518 B** free in both `DEBUG_KIT` builds (−48: `pf_miss` / `pf_dodge`, the
BLOCK-over-DODGE test); bank 7 code 3,134 B, 3,010 B free (kit: 3,184 /
2,960); bank 2 image unchanged to `FRT` (1,328 B), the
`kind_tab` ALIGN pad 84 → 36 B (−48: the `RC_DODGE` branch 18, the edge clamp
~26, `item_log`'s `LT_SERVED` 5); bank 1 / low RAM unchanged; new RAM:
`LOG_TURN` `$BC4F`, `LOG_PDIR` `$BC50`, `pf_miss` `$5E5D` (PF_RAM). Budget:
"wcast" cast max 96.5k T, ordinary 115.6k; "wcast4" cast 118.3k, ordinary
120.0k; "acast" 93.4k; "lcast" 126.1k.

**Headroom after D3-7 T6** (build DISPLAY): bank 3 **566 B** free in both
`DEBUG_KIT` builds (+256: the drips removed); bank 7 code 2,891 B, 3,253 B
free (kit: 2,941 / 3,203); bank 1, low RAM, bank 2 image unchanged; no new
fixed RAM (`DAGGERS` / `ARROWS` / `HAS_BOW` `$BCAA..$BCAC`, `MSG_BUF`
reused). Budget: "acast" fire ticks max 84.1k T (cast cap 128k), "lcast"
126.1k unchanged.

**Headroom after D3-7 T5** (build DISPLAY): bank 3 **310 B** free in both
`DEBUG_KIT` builds (T4: 216 B / 171 B with the kit; −94 net: `melee_hit` +92,
`potion_pickup` / `try_quaff` (+ `debug_kit` in kit builds) moved to bank 7);
bank 7 code 2,573 B, 3,571 B free (kit: 2,623 / 3,521 — measured at T7; first written 2,620 / 3,524); bank 2 image
unchanged (1,328 B to `FRT`, `kind_tab` pad 84 B); new RAM: `ABIL_TGT`
`$5E70..$5E71` (PF_RAM).

**Headroom after D3-7 T4** (build DISPLAY, `-DDEBUG_KIT=0`): bank 3 **216 B**
free (`proj_rel` 6 B, `pf_burst` +2, `pf_strike` +9; T3's `rank_sync` / kit
before); bank 7 code 2,027 B, 4,117 B free; bank 2 image unchanged (1,328 B
to `FRT`, `kind_tab` pad 84 B).

**Headroom after D3-7 T1** (build DISPLAY, `-DDEBUG_KIT=0`): bank 3 **306 B**
free; bank 7 code 1,773 B, 4,371 B free; bank 2 image 1,328 B to `FRT`, the
`kind_tab` pad 191 → 153 B (+38: the `anim_gate` hook + `pend_far` +
`probe_act_fire`, `turn_done` / panel / `decor_gate` `TURN_PEND` tests,
`fx_start`'s `FX_DROP`).

**Headroom after D3-7 T0** (build DISPLAY): bank 3 **314 B** free (was 30);
bank 7 code 1,616 B, 4,528 B free; bank 2 image unchanged 1,328 B to `FRT`,
the `kind_tab` pad 249 → 191 B (the 20-B `slot_act_tab` + `slot_act` /
`abil_rank` from bank 3 landed before it).

**Headroom after D3-5** (build DISPLAY): bank 2 image **48 B to `FRT` + 174 B
pad** (−899: `fx.asm` 869 B incl. `fx_meta` 23, hooks in `render` /
`turn_done` / `hide_sprites` / `anim_gate` / `decor_tick` ~30; `kind_tab`
`$A000` → `$A400`); bank 3 unchanged 2,324 B; low RAM 397 B spare (−3:
`vis_reset` → `fx_reset`); FONT6 holes all used. Bank 2 is now the tightest
store: the D3-S switch (drop the bank-7 clean background) frees 6 KB of bank
7 but no bank-2 bytes.

**Headroom after D3-4** (build DISPLAY): bank 1 free **783 B** (−1,385: +1,322
packed sources, +63 status icons); bank 2 image 816 B to `FRT` + 250 B pad
(−108 = 27 × `FT_STRIDE`); bank 3 2,267 B (unchanged by D3-4); low RAM 545 B
spare (−8) + 295 B descriptor reserve (59 more fids); FRT 101 of 160; pool
need 44,096 of 46,468 (2,372 slack). Bank 1 is the next store to run out:
R4 (ZX0-pack `font6x8` / `tiles_common`, ~0.5 KB) is the lever.

**Headroom after D3-TX** (text block → bank 0, D3-2 strings in): bank 1
free 2,168 B; bank 2 unchanged (1,072 + 108 pad); bank 3 unchanged 3,867 B;
AY slot 4,059 B; low RAM 667 B spare (−55: `tx_dec` 35, the `.txt` tape
load 20); pool `POOL_CAP` 46,468 for a need of 40,096 (6,372 slack).

**Headroom at D3-0** (build DISPLAY): bank 1 free 992 B (was 974); bank 2
image 1,072 B to `FRT` + 108 B pad (was 816 + 110; `kind_tab` `$A100` →
`$A000`); bank 3 3,867 B to `AY_RESERVE` (was 964 to `$E400`); AY slot
4,059 B free; low RAM 722 B spare (was 723).

