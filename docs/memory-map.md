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
| `$5CCB-$7FFF`| Free RAM (after BASIC reclaim)              | program + working storage; **D3-6b: `$5E00-$5EFF` = `PF_RAM`** (proj_fire scratch, runtime only — "3D contracts"); **D3-8d: `$5F00-$5F8B` = `MK_RAM`**; **3F-T7: `$5F8C-$5FF3` = `RG_RAM`** (ranged scratch + shot queue, runtime only — "3F-T7") (status-mark cell map + glyph / attr copy, runtime only — "Status marks (D3-8d)"); **3E-T3: `$5D00-$5D50` = `ITEM_RAM`** (bag, worn, hunger, quick slots; 81 B since the 3E simplification; runtime only — "3E contracts") |
| `$8000-$BFFF`| Program origin region                       | `ORG $8000` for now           |
| `$C000-$FFFF`| Paged bank window                           | bank selected by $7FFD bits0-2|

## 128K banks ($C000 window)

| Bank | Planned use                       | Status   |
|------|-----------------------------------|----------|
| 0    | **D3-TX: the text block** (`TEXT_ADDR` `$C000..POOL_START`, own tape block), then the pre-shift sprite pool | PROTO    |
| 1    | PROTO: sprite sources (virtual $8000-$BFFF), ZX0-packed since A5: 6,947 of 16,384 B (A6); + `vdata` (D3-TX: the text block moved to bank 0; **3E-T1: its boot-only part moved to the bank-6 boot block**); **C3-0: `ui1_code` (3C UI code, via `far1`)** after it; **3E-T1: then the packed overlay streams `ovl_blobs`** (**R6: moved to the R6 region**; bank 1 now ends at `bank1_end`, 1,300 B free) | PROTO |
| 2    | (also $8000 fixed)                | system   |
| 3    | PROTO: sprite sources tail (virtual $C000-; empty since A5) + **cold code** (select, transition scrolls, follower selection; new game → bank 7 since MEM-SND); **`$EFA0-$FFFF` AY player slot** (A8; **3E lever (c): 4,192 B** from `$EFA0` (+512 B to bank-3 cold code); MEM-SND: 4,704 B from `$EDA0`, was 4 KB at `$F000` since D3-0 (user 2026-10-06), 7 KB from `$E400` before; called by the IM 2 ISR) | PROTO |
| 4    | PROTO: pre-shift sprite pool      | PROTO    |
| 5    | normal screen (also $4000 fixed); low RAM `$6000-$7FFF` buffers + **cold code** (boot, generator) + frame descriptors (A6) | system   |
| 6    | PROTO: pre-shift sprite pool `$C000..POOL6_END` (**SRC6 spike: ends at `POOL6_END` = `SRC6_ADDR` `$E400`**; R6: was `R6_ADDR` `$E500`); **3E-T1: until the hero start, `BOOT6_ADDR..SRC6_ADDR` = the boot block** (boot-only code + data, own tape block, dead after boot — "Boot block"; R6 / SRC6: moved down from the top); **SRC6 spike (2026-10-27): `SRC6_ADDR..R6_ADDR` = the permanent bank-6 sprite-source region** (`SRC6_LEN` = `SRC6_PAGES` × 256, default 256 B; ZX0 blocks read by `zx0_frame`; on the boot block's tape block — "SRC6 region"); **R6 (2026-10-21): `R6_ADDR..$FFFF` = the permanent R6 region** (6,912 B: resident code via `far6` + packed overlay streams, own tape block — "R6 region") | PROTO    |
| 7    | **displayed screen during play** (screen 2, `$C000-$DAFF`, A7 double buffer) + **8 level tilesets** `$FAA0-$FF67` (MEM-RECLAIM w2a: deduplicated, 1,224 B; was 8 × 320 B at `$DB00-$DFFF` / `$FAA0-$FF9F`) + **D3-S2: bank-7 cold code** `$DB00-$F7FF` (`far7`; was the bitmap shadow + (w2a) tileset slots 0–3) + the attr shadow `$F800-$FA3F` | system / PROTO |

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
| 1 | sprite **sources** at *virtual* `$8000..` (MMU slot 2 = page 1): `build/zx0/sprites_zx0.asm` (see "Sprite sources (ZX0)" below; B3B-12 retired the raw `index.asm` A/B build) | ZX0: `SRC_TOTAL` **6,947 B** (`$C000..$DB22` in bank 1), then (B3B-11b, bank-3 relief) the **`vdata` block** 2,704 B (B3B-13 measured) (`vdata..vdata_end`: `font6x8` 768, `panel_icons` 774, the `HOT_COPY` load image `panel_hot_img` 515, `tiles_common` 288 + `orn_glyphs` 64 (D3-0: the 16 B of PROTO zap glyphs `tiles_fx.asm` are no longer assembled; `VDATA_LEN` 3,563 B) — boot / new-game cold data, read only through `copy_virt` / `copy_virt3`; B3B-13: + the **text block** `text_img` 277 B, DISPed to its runtime `$C000..` address — **D3-TX: moved to bank 0**, see the bank-0 row and "Text (B3B-13)" below); **C3-0: then `ui1_img..ui1_img_end` = `ui1_code..ui1_end`** (bank-1 UI code, `src/ui1.asm`, DISPed by `TEXT_DISP` to its runtime `$C000..` address, ASSERTed in bank 1 and `ui1_end <= UI1_LIMIT` `$10000`; empty in C3-0 at `$E4AC`; the build DISPLAYs `bank 1 free`); **3E-T1: `vdata` 837 B (`panel_icons` 774 + `status_icons` 63; −1,623 boot-only B → the boot block), UI code `$E611..$F80D`, then `ovl_blobs` 30 B, bank-1 block 14,379 B, 2,005 B free** (was 412); **3E-T2: UI code `$E611..$F851`, `ovl_blobs` 273 B (the page), 1,694 B free**; bank-1 block `SRC_LEN_LO` 9,388 B (C3-0 measured), **6,996 B free** (B3B-13: −265 raw items / tiles, +277 text; **C3-7 measured: bank 1 free 861 B** after the UI code (**SND-4a: 412 B free**, −62 `stinger_wait` (Kempston via read_stick, 512-frame cap) in `menu1.asm`; SND-1: 474 B free, −169 (−124 + 45 for the log line's replace-pending rule): `snd_cycle` / `snd_id` / `menu_snd`, the 3-item pause box, `S` reserved, key 5; bank 0 text −4 B net: 3 SOUND strings, `ft_press` dropped; bank 7 and low RAM unchanged) — the 6 hero frames took 904 B of packed sources, was 1,765; **D3-TX: 2,168 B free**, was 992 at D3-0: the text block (1,166 B at D3-0) out to bank 0; `VDATA_LEN` 2,397 B; **D3-4: 783 B free** — +1,322 B packed sources (27 frames) + the 63-B `status_icons` in `vdata` (`VDATA_LEN` 2,460 B); **D3-9b: 650 B free** — −16 `xp_next` (now bank-2 `xpn_tab`), +35 `item_info`'s rank-2/3 line pick (D3-9a); **D3-8: 689 B free** — +94 B `stat1.asm` (`st_icons_draw`) in the UI code) (A6: the 272 B of banked descriptors moved to bank 5) | tape block 3 / .sna |
| 3 | sprite sources tail, virtual `$C000..` (MMU slot 3 = page 3) — **empty** with ZX0, then the **bank-3 cold code** (`bank3_code..bank3_end`, below) | 0 B sources + code + cold data = `BANK3_LEN` (**3F-B5: 11,942 B, 250 B free to `AY_RESERVE`** (main `6edd76e` measured 265; +15 B: `ai_monster`'s one-lookup walker path + `.fstep`, `ACT_SLOT` stored by `resolve_monsters`; "3F-B5" below); (**3F-T5 on top of 3F-B4 (`materialise` +5 B PEND_N gate): 11,923 B, 269 B free to `AY_RESERVE`** (before T5: B4 left 5 B free) (-259: the FRESH unit loop `lp_fit` / `.unit` / `.fresh` and `mon_drop`'s `drop_tab` scan + table -> R6 `tier6.asm`; +27 `lp_spawn` max hp / `E_GOLD`, +6 the golden lair weight; "3F-T5" below); 3F-T3: 12,182 B, 10 B free to `AY_RESERVE` (68 before: `lp_wt` +21, `drop_tab` 15 -> 48 B, `mon_drop` +3: "Kind rows (3F-T3)"); **STATUS1: 11,811 B, 381 B free to `AY_RESERVE`** (both builds; +31: `trap_stone` + `th_go`, the POISON byte branch in `deal_hit`, the 5th `tr_ink3` ink; "STATUS1" below); **IC1: 11,780 B, 412 B free to `AY_RESERVE`** (both builds; "IC1 item icons"); **RANK1+MEM-1: ~436 B free to `AY_RESERVE`** (RANK1 −4 B on top of MEM-1's 432; re-verified by the build DISPLAY); **MEM-1: 11,760 B, 432 B free to `AY_RESERVE`** (both builds; was 492: `kx_tab` +64, the four kx_tab index sites −4); **3E-T16: 11,700 B, 492 B free to `AY_RESERVE`** (−99 vs the 591 measured on main ff69718: `trap_hit` + `tr_ink3` (combat3.asm), `build_room_map`'s known-trap stamp + its item guard); **B19c+3E-T12: 11,585 B, 607 B free to `AY_RESERVE`** (B19c +33 B: `turn3.asm` `corpse_hit`, materialise waits for a DYING body in the box; T12 alone was 11,552 B / 640 free) (+130: `room_status`, +8: `icon_state` reads `QS_CACHE`, combat3.asm, the Fear / Sleep scroll); **3E lever (c): `AY_RESERVE` `$EDA0` -> `$EFA0` (+512 B): 11,576 B code, 616 B free to `AY_RESERVE`**; DEC2: 11,414 B, 778 B free to `AY_RESERVE` `$EFA0` (from 11,573 / 619); DEC1: 11,577 B, 103 B free to `AY_RESERVE` `$EDA0` (was MEM-SND 11,475 / 205) (both `DEBUG_KIT` builds; −406 B → bank 7 `src/boot7.asm`: `init_tiles` (36) and `panel_boot` (73, boot), `new_game` minus its PROTO tail (now bank-3 `new_game_proto`: `proto_level` + `spawn_tab` + `vis_reset`, kept for the tests' `proto_start` = 1 path), `panel_init`'s bank-2-only half `panel_init7` (state reset, the 9 attr stamps, the potion-slot scan; `pot_slot` stays bank-3 data, written from L); then `AY_RESERVE` −608 B (`$F000` → `$EDA0`), ~200 B kept as bank-3 growth slack for 3E/3F; `level_start_x` and the PROTO cluster stay (A-returning / bank-3 data / test probe `level_new`, tests use `proto_start`); D3-9b: 11,881 B, 407 B free (−48: `xpn_tab` → bank 2, `lvlup_tab` / `lvl_step_tab` → `xp_turn` immediates, `panel_init`'s MP placeholder bar gone); D3-8d: 11,929 B, 359 B free (both `DEBUG_KIT` builds; +21: `dh_status`'s V3 sleep flash — an ASLEEP landing with no reaction pending sets `E_FLT` / `E_FLA`); D3-8f: 11,908 B, 380 B free (both `DEBUG_KIT` builds; −4: `deal_hit`'s WEAK −1 moved onto the DEF path (B → `dh_def`, the old dec / min-1 gone), `dh_status` reads the `efx_tab` row before the halving (R2 order; no push / pop)); L-RELIEF: 11,912 B, 376 B free (both `DEBUG_KIT` builds; −353: `follow_select` (the candidate scan, 186 B), `place_follower` (112) and `arrival_conflicts` (56) → bank 7, +1: `follow_admit` far7s `place_follower` (+3, its `jr .pick` → `jp`) ; `dg_bad` moved to `$C0C0` right after `kx_tab` (`src/dg_bad3.asm`), the 3-B `ALIGN 64` pad gone — **no alignment pad left in bank 3**: code size changes no longer cost 64 B steps); D3-8e2: 12,265 B, 23 B free (both `DEBUG_KIT` builds; +3 `level_reset` clears `pf_prep`, `pf_strike`'s `pf_ftick` record 0 B — absorbed by the `dg_bad` ALIGN 64 pad, which now has **3 B** of slack: 4 more bytes of bank-3 code before `decor_gen.asm` cost 64); D3-8e merged with D3-8c: 12,265 B, 23 B free (both `DEBUG_KIT` builds; D3-8c +54: `deal_hit` HOLD_GUARD / held-body refusal, self-freeze, POISON add (bank 7 −4 B); D3-8e alone: 12,211 B, 77 B free, +158: `proj3.asm` — the split cast (`proj_part` / `proj_go` / `proj_run` entries, the strike budget + park, `pf_prep` 1 B), the bulk run entry, the inline `pf_bdone`, `pf_strike` through `dh_tix`, the caster DONE in `pf_cands`, the die mask; `rank3.asm` `proj_rel`'s prep test + `proj_pre`; `deal_hit` `dh_tix` / `dh_rtick` 3 B; `set_reaction_at`'s `dh_rtick` test); D3-8 review 2: 12,053 B, 235 B free (both `DEBUG_KIT` builds; +123: `proj3.asm` — `pf_cands`' x1 clamp, `pf_bodies` rewritten (count early exit, `PFCF_DEAD`), the bulk fast-forward entry, `rsp_hl` without the loop; `deal_hit`'s page-local record reads + `dh_bit` 8 B; `set_reaction_at` × 17 by shifts); D3-8 review: 11,930 B, 358 B free (both `DEBUG_KIT` builds; −57: `proj3.asm`'s `PF_ROWF` body count — `pf_bdone`, the count in `pf_cands` / `pf_reverse` — and `panel_init`'s `STAT_SH` reset); **D3-8: 11,873 B, 415 B free** (both `DEBUG_KIT` builds; −103: the monster status test + far7 `mon_status`, `item_icons`' status sig, `deal_hit` boss + WEAK, `hit_roll` WEAK); **D3-7 T7: 11,770 B, 518 B free** (both `DEBUG_KIT` builds) — +44: `pf_miss` + `pf_dodge` in `pf_strike` (`proj3.asm`), +4 (review): `set_reaction_at` lets a BLOCK replace a pending `RC_DODGE`; **D3-7 T6: 11,722 B, 566 B free** (both `DEBUG_KIT` builds) — −~190 `dg_drips` + its scratch (the drips are gone), +~10 `build_room_map` stamps the ammo stacks, `dg_bad` regenerated (ids 17/18 no longer decor); **D3-7 T5: 11,978 B, 310 B free** (both `DEBUG_KIT` builds; T4 left 216 B / 171 B with the kit) — +92 `melee_hit` (`rank3.asm`), −~150 `potion_pickup` (→ bank-7 `pickup7.asm`), −~34 `try_quaff` (→ bank-7 `intent7.asm` `ic_quaff`), −~36 `debug_kit` in kit builds (→ `intent7.asm`); **D3-7 T1: 11,982 B, 306 B free** — +8: `set_reaction_at` / `pf_tick` add `TURN_TICK`; note the `dg_bad` ALIGN 64 has only ~2 B of slack: 3 more bytes in bank-3 code before `decor_gen.asm` cost 64; **D3-7 T0: 11,974 B, 314 B free** — −284: `intent3.asm` → bank 7 (`intent7.asm`), `slot_act_tab` / `slot_act` / `abil_rank` + the `icons3.asm` page pad → bank 2, `rank3.asm` `abil_load` +~80; **D3-6b: 12,258 B, 30 B free** — +1,046: `proj3.asm` ~1,060 B, `deal_hit` −14 (shares `rsp_hl`); D3-6a: 11,212 B, 1,076 free; the figures that follow are older) **9,893 B, 2,395 B free** (merged with D3-1 / D3-TX; LP alone: 9,637 B, 2,651 B free) to `AY_RESERVE $F000` (**LP +1,216**: `src/lpop3.asm` 1,302 B (`lp_dtab` 48, `lp_wt` 9, `lp_budget`, `lp_append`, `lp_bank`, `lp_transition`, `lp_enter`, `lp_fit`, `lp_place`, `lp_cmap` / `lp_mark`, `lp_legal`, `lp_spawn`), `follow_admit` / `dest_counts` LP paths ~+70, the stand-in `pop_one` / `pop_kinds` / `pop_cols` −~150, an `icons3.asm` page pad for `slot_act_tab`; before LP: 8,421 B, 3,867 B free (**D3-0**: AY reserve 7 → 4 KB = +3,072 B; the PROTO zap out −87 B: `init_tiles`' zap-glyph copy, `do_attack`'s zap tail + `wz_zap`; `kx_tab` +192 B (R2, zeros until D3-1); the `ST_*` clear in `level_reset` + `level_reset_new` +64 B; before: 8,252 B, 964 B free to `$E400` (C3-7)). Earlier: 8,369 B, 847 B free to `$E400` (B12, measured: 8,305 → 8,369 = +64 incl. the `dg_bad` ALIGN 64 shift: `glow_ids` 8 + the `.gate` stamp in `build_room_map` ~42; the D1 decor rework before it was not itemised here). Before: 7,744 B, 1,472 B free (B11/B14 +44 (measured: 7,700 → 7,744, incl. `level_reset` clearing `CLIMB_BLK_N`; the row's older figures below were not re-measured): the B14 yield — on the shaft col the facing side instead of the roomier one, the flyer's vertical fallback that must end off the path; B3B-13 −196: `show_impact_msg` + `kind_name` / `str_cat` + the 7 combat words → low RAM / the text block, `str_descend`, the room-D chest decor entries out; + `sel_nm_knight` / `sel_nm_wizard` 14 (select-screen names, ROM charset) in; before: B3B-12 +469 incl. the review fixes: `level_card` + strings, `level_new` (seed + level_gen retry), `level_populate` / `pop_one` + `pop_kinds` / `pop_cols` (the stand-in population), `level_reset` / `spawn_one` factored out of `new_game`; before: 7,157 B, 2,059 free; B3B-R2 +1,558: `src/turn3.asm`, the monster phase / attacks / potions moved out of bank 2, see "Cold code placement"; before R2: 5,599 B, 3,617 free; B3B-10 −1: `build_room_map` picks + empties the decor list of its map page (`dg_dst`), the deriver's ROOM_MAP-only test gone; the B3B-9 deriver `decor_room` (`src/decor_gen.asm`, ~1.0 KB incl. its 56 object records) came with the B3B-9 merge; B3B-11b −2,534: font, icons, hot image, `tiles_common` / ornament / zap data out to bank-1 `vdata`, `panel_boot` builds the planar font, `pblit` / `init_tiles` read through `copy_virt3`; before: 8,134 B, 1,082 free after the B3B-9 merge; B3B-11 +2,687: `src/panel.asm` cold code 437 (`panel_boot`, `panel_init` / `panel_flush`, `pblit` / `glyph8` / `cell_bm`, bar tables), the 6×8 font 768 (`font6x8`, boot-copied to `FONT6`), the panel icons 774 (`panel_icons.asm`), the `HOT_COPY` image 708 (`panel_hot_img`, boot-copied); B3B-8 +1,149: `build_room_map` v2 524, `init_tiles` 39 + its cold data 370 (`tiles_common` 288, `orn_glyphs` 64, the zap glyphs 18), `proto_level` + its tables ~150, the scroll ornament hooks ~45, `decor_room` stub 1 (B3B-9: the real deriver); B3B-7 merge: `level_gen` / `level_start_x` ~1.7 KB; B3B-5 +22: `edge_init` + the `EDGE_TAB` / `JUMP_TURN` init in `new_game`; raw: 515 + 1,760 = 2,275, 6,941 free before B3B-5; A7 review: + `new_game`/`init_ent_common`/`spawn_tab` and the follower selection / arrival conflicts, 794 B, out of bank 2). ASSERT `bank3_end <= AY_RESERVE` | tape block 4 / .sna |
| 3 | **AY player slot** `AY_RESERVE..$FFFF` (A8; **3E lever (c): 4,192 B at `$EFA0` (was 4,704 B at `$EDA0`), 4,023 B used, 169 B free; SND-STEP: STEP 5 -> 3 B** (3 reserved 3F ids + EAT/pickup tweaks need ~160); `ay_vars` now `$F5DD..$F645`; all else symbolic; **MEM-SND: 4,704 B at `$EDA0`, 3,987 B used, 717 B free; SND-5b: 4,055 B used, 649 B free (+5 effects +10 B table, 32 effects); 3E-T0: 4,025 B used, 679 B free (5 status variants -> one STATUS effect with a pitch offset, +TRAP, GOLD removed, 28 effects + 3 reserved ids; net +33 B vs 646 before)** (was 109 B free at `$F000`: the SFX room for SND-4a / SND-5b; tape block 5 = `AY_LEN` from `AY_RESERVE`, loader / tests / #50 all symbolic; ISR contract unchanged); **D3-0: 4 KB** = 4,096 B at `$F000`, user 2026-10-06, game.md §11.2; was 7 KB `$E400`, before that 8 KB `$E000`): `ay_code..ay_code_end` (`src/ay.asm`), entry `AY_PLAY` = `AY_RESERVE`. **SND-2 T2**, in this order: `ay_play` (208 B, the mailbox dispatcher + `ay_silence`; ASSERT `ay_play == AY_PLAY`), the WZM v0.3 player `MODULE wzm` (`src/music/player.asm`, `DEFINE WZM_BUZZER`, no echo; 1,082 B = code + period table 990 + state 92: `wzm.pl_regs` .. `wzm.player_end`), the dispatcher state `ay_mode` / `ay_loop` (2 B) right after it, then `MODULE mus` (`build/music_game/game_songs.asm`, generated by `tools/build.sh`, found through `-i OUTDIR/build/music_game`): the 7 harpsichord songs + `mus.mus_tab` (`DW` song, id order `MUS_CRAWL` 1 .. `MUS_LAMENT` 7; ASSERT `2 * MUS_COUNT` B), 1,947 B. **`ay_vars` .. `ay_vars_end`** (= `wzm.pl_regs` .. the dispatcher state, 94 B, ASSERTed contiguous) is the only runtime-written part of the slot (`tests/game.py` #50 masks it; no SMC). Was the silent stub (37 B). **SND-5 (sound effects; review round + the full set, 2026-10-19):** `ay_play` 247 B (+39: `.hold` clears `SFX_NEXT` when nothing plays, the SFX fast-path test, the `sfx_step` / `ay_music` / `sfx_out` calls; `MUS_FIRST` id checks), player 1,106 B (+24: the `WZM_SFX` hooks — V1 not stored while an effect plays, `sfx_ran`, `sfx_dk`, `sfx_mix` merged into R7; ASSERTs: the smallest period != 0, `WZM_SFX` needs `WZM_BUZZER`), the SFX engine `sfx_step` / `sfx_out` / `sfx_dk` 318 B (+47: the `SFX_NEXT` deferral, slot keeps the higher priority) right after `ay_silence` (before the player), the dispatcher state 12 B (`ay_mode`, `ay_loop` + `sfx_ptr` 2, `sfx_prio`, `sfx_duck`, `sfx_per` 2, `sfx_vol`, `sfx_mix`, `sfx_ran` 2; inside `ay_vars`, now 104 B), the songs **6, 1,794 B** (Dungeon Crawl removed by the user 2026-10-19: −151 B + its table entry; `mus.mus_tab_first` = ids 2..7, `mus.mus_tab` EQU first − 2), and after them `build/sfx/sfx_data.asm` (`tools/sfx2asm.py` from `assets/sfx/effects.json`, `-i OUTDIR/build/sfx`): `sfx_tab` (`DW`, stride 2, index order) + **27 effects = 510 B**. SFX total 891 B (engine 381 + data 510) | `AY_LEN` **SND-5: 3,987 B, 109 B free** (SND-2: 3,239 B, 857 B free); ASSERT `ay_code_end <= $10000` | tape block 5 (headerless, `start` `.ay`) / .sna |
| 0 | **text block** (D3-TX; B3B-13 format, "Text" below) `text_img..text_img_end` = `TEXT_ADDR` `$C000` .. `POOL_START` (`TEXT_LEN` = `TEXT_PACKED`; ASSERTed below the `tap_loader` scratch `$E000`). The pool's bank-0 part starts at `POOL_START` (`alloc_reset`), so the pool never overwrites it | SND-1 strings: 200 strings, 79 tokens, **2,680 B** (`$C000..$CA77`, pool from `$CA78`; was D3-2: 198 / 82 / 2,684 B) | tape block 8 (headerless, `start` `.txt`) / .sna |
| 0, 4, 6 | **pre-shift pool**: every frame variant (facing × shift), generated by a bump allocator (**3F-T1: per level** — boot: the 2 select idles; `start_game`: + the hero + its class FX, then the LEVEL mark; `level_enter`: + that depth's monster kinds, "Level pool (3F-T1)") (no variant straddles a bank); bank 0 from `POOL_START` (D3-TX), banks 4 / 6 from `$C000`; **R6: bank 6 ends at `R6_ADDR`** (`alloc`: an allocation past it = pool full; `tests/ovl.py` R1) | **R6: need 37,312 of `POOL_CAP` 39,792 B (= 46,704 − `R6_LEN` 6,912), slack 2,480**; before R6: need **37,312** of `POOL_CAP` 46,704 B (build DISPLAY), slack **9,392** — **phase-locked walk shifts (`PHASE_SHIFT` 1, 2026-10-21; docs/conventions.md "Walk cycles")**: each walk frame drawn at only one px parity stores one shift (monsters 22,688 → 18,592, hero max 18,528 → 15,840 = Knight 15,488 + `K_FXW` 352; per kind −2,688 Knight / Wizard, −2,112 Skeleton, −1,408 Goblin, −320 Rat, −256 Slime); `-DPHASE_SHIFT=0` = the figures below, need 44,096 (D3-4; was 40,096) (D3-TX: 49,152 − the text block; ASSERT `POOL_NEED <= POOL_CAP`) (monsters 22,688 + largest hero **with its class FX kind** 18,528 = the Knight 18,176 (D3-4: +3,648 for THROW / BOW / WHIRL / POWER_STRIKE) + `K_FXW` 352 (the Wizard: 13,184 + `K_FXM` 1,152 = 14,336); before D3-4 the largest hero 14,528 = the Knight (C3-7: +1,920 for JUMP1/2; the Wizard 9,728 → 13,184 with JUMP1/2 + STAFF_RAISE/SWING) + 2 select idles + straddle slack; ASSERTed) | `gen_kind` / `gen_frame` at boot and at hero select |
| 7 | **level tilesets** (B3B-8; **MEM-RECLAIM w2a: deduplicated**): `TSET_BASE` `$FAA0..$FF67` = `tset_slots` (8 × 65 B records) + `tset_fsets` (4 × 32 B) + `tset_pool` (72 × 8 B glyphs); 152 B free to `$FFFF` (`tools/tiles_convert.py` → `assets/gfx/tiles/tilesets.asm`, format under "Bank-7 tileset slots") | 1,224 B (`TSET_LEN`; was 2 × 1,280) | tape block 5 (headerless, `tape_tab`) / .sna |
| 7 | **screen 2** `$C000..$DAFF` (A7): the screen the ULA shows during play, a copy of the bank-5 screen kept by `present` / `present_full`; **attr shadow** `SHADOW_ATTR` `$F800..$FA3F` (the room's tile attrs in screen-attr layout, rows 0–17; high byte = screen attr + `$A0`; `$FA40..$FA9F` = 3 spare PROTO rows). **D3-S2 (2026-10-12): the bitmap shadow (`$E000..$F7FF`, R-1 erase lever since A7) is gone** — `erase_rect` redraws `TILE_GLYPHS[ROOM_MAP]` (+ the row-17 ornament) and takes attrs from the attr shadow (decor attr cycles) | 6,912 + 576 B; `$FAA0..$FF67` = the tilesets (row above) | screen 2: `present*`; attr shadow: `shadow_rect` / `shadow_room` on room entry, door planks, potion pickup; `decor_tick` steps |
| 7 | **bank-7 cold code** (D3-S2) `b7_code..b7_end` = `B7_CODE` **`$DB00`** (MEM-RECLAIM w2a; was `$E000`) .. ≤ `B7_LIMIT` `$F800` (`src/bank7.asm`, entered only through `far7`; rules under "Cold code placement") | **MEM-RECLAIM w2a (2026-10-30): `B7_CODE` `$E000` -> `$DB00` (+1,280 B: the old tileset slots 0–3), `level_tiles7` (`src/tiles7.asm`, the deduplicated tileset gather, +96 B; the low-RAM `level_load_tiles` is a 6-B far7 stub: low-RAM spare 13 -> 94 B); release `$DB00..$F2CA` 6,091 B, **1,333 B free** (kit 6,096 / 1,328; was 149 / 144). **MEM-RECLAIM w2b: + `hunger7` / `trap7` / `boss7` from R6 (+1,060 B): release `$DB00..$F6EE` 7,151 B, 273 B free (kit 7,156 / 268).** **KIT-FIX (debug_kit -> R6 `r6.asm`, far6 from `hero_st_init`; release build unchanged byte for byte): kit build `b7_end` `$F7E1` = 31 B free (release `$F7DC`, 36 free); kit R6 247 B free (release 317); the kit had overflowed `B7_LIMIT` by 9 B after T6 + T7.** STATUS1 (history below, older kit figures include the 44-B `debug_kit` now gone from bank 7): 6,032 B (kit 6,077), 112 B free (kit 67) (+3 net: `turn_input` calls `trap_chk` before the HOLD_GUARD clear, +6; `st_step`'s POISON byte, the mod-3 loop gone, −9); **IC1: 6,035 B (kit 6,080), 109 B free (kit 64)** (−15: `panel_init7`'s quick-potion slot scan); **RANK1: 6,050 B (kit 6,095), 94 B free (kit 49)** (−20 / −25: `abil_learn` no longer far3s `rank_sync`, the kit tail is a `ret`); **3E-T16: 6,070 B (kit 6,120), 74 B free (kit 24)** (+118: `turn_input` saves `TRP_PRE` on every try and `.spent` calls `trap_chk` (also the held Wait; the room's trap scan + a ±col pre-filter → far6 `trap_turn`), `tpt_intent .srch` (every Wait sets `TRP_WAIT`), `end_turn .ex` (the room-entry sense), `act_pend`'s `ABL_TRAP` dispatch → far6 `trap_step` + its exit-turn monster skip, `ap_stamp`'s known-plate fallback (far6 `trap_glyph`), `ap_put_a` / `ap_put` in `pickup7.asm`); **3E-T12: 5,952 B (kit 6,002), 192 B free (kit 142)** (−96 net: `ic_potion` / `ic_quaff` / `pot_eff` / `cap_add` → R6 `fx6.asm`, the 3 quick slots tail `jp far6 fx_quick` (+4), `do_exit`'s `EX_TELE` branch +34); after 3E-T8: 96 / 46; **3E-T2: 5,931 B (kit 5,981), 213 B free (kit 163)** (+13: `use_slot` calls `page_run`, `tpt_intent`'s `IN_BAG`); 3E-T1: 5,918 B (kit 5,968), 226 B free (kit 176) (−109: `init_tiles` / `panel_boot` → the bank-6 boot block); SND-5b: 6,027 B (kit 6,077), 117 B free (kit 67) (MEM-SND: 5,998 B, 146 B free; SND-5b hooks +29 B: hero step 5, pickup 2x5, quaff 5, `ic_no` +2, cursor MENU +7) (+423: `src/boot7.asm` — `init_tiles`, `panel_boot` (far7 from `boot`), `panel_init7` (far7 nested from bank-3 `panel_init`, ~0.3k T per level start), `new_game` (far7 from `start_game`; far3s `level_reset_new` / `init_ent_common` / `new_game_proto`, ~0.5-0.8k T once per game); no data, no SMC); **SND-5: 5,575 B (kit 5,625), 569 B free (kit 519)** (+36: `ic_no_mana` (the NO MANA refusal + `SFX_FIZZ`; the two `ld a, TX_NO_MANA : jp c, ic_refuse` sites → `jp c, ic_no_mana`), `act_fire` → `sfx_abl` (the release sound by `ABL_*`, after the lead-col guard; a fizzled release sounds FIZZ), `xp_level` `SFX_LEVELUP`, `try_climb` `SFX_LADDER`; SND-5 elsewhere: bank 2 +122 (image free to FRT 300 → 178, `kind_tab` pad 41 → 13, see `$8000` row), low RAM +25 (`impact_line` → `sfx_msg`, `hero_fall` FALL, the jump JUMP, `door_open` DOOR, boot and `level_enter` (new game / descent) clear `SFX_NEXT`; spare 156 → 131), bank 1 +7 (`menu_run` `SFX_MENU`; free 650 → 643), bank-3 cold code 0 (no bank-3 call site; 407 B free)); SND-3: 5,539 B (kit 5,589), 605 B free (kit 555) (+146: `src/mus7.asm` — `mus_pick`, the Dangerous (W) cue from the `LIVE_LIST`, called from `end_turn`; the death branch writes the Y cue; `level_enter` (low RAM, +6 B: spare 162 → 156) clears `DNG_DWELL` / `DNG_CALM`); D3-9b: 5,393 B (kit 5,443), 751 B free (kit 701) (+364: `src/xp7.asm` — `xp_turn` (end_turn's MP regen, then `xp_level`), `xp_level` (the level-up + its log lines + `LT_HOLD`, **only in a tick's 1st frame**: else `XP_UP` stays set and `turn_input`'s entry retries it each INPUT tick, +7 B), `abil_learn` (the read-time learn / rank-up entry for 3E); `hero_st_init` +14 (restores the heroes' `KT_ATK` / `KT_EVA` columns); `end_turn` tail `jp z, xp_turn`); D3-8d: 5,029 B (kit 5,079), 1,115 B free (kit 1,065) (+469 (review fixes incl.: `mk_erase` cover test, `MK_WAIT`, BRIGHT frame B): `src/mark7.asm` — `mk_op` (draw / erase / in-place redraw, the drip hand-over), `mk_new`, `mk_draw`, `mk_forget`, `mk_erase`, `mk_drop`, `mk_spend`, `mk_sweep`, `vis_tail`, `mk_room` (reset + glyph / attr copy), `mk_hide`; `hide_sprites` +3); D3-8b: 4,560 B (kit 4,610), 1,584 B free (kit 1,534) (+312: `src/drip7.asm` — `drip_room` (the room's drip sources, from `vis_room_sync`; `DRIP_ROW` $FF), `drip_idle` / `drip_rnd` / `drip_try`, `drip_step` (spawn / let go, with a T_AIR re-check), `drip_cover` / `drip_land`, `drip_hide`; `hide_sprites` +3); D3-8f: 4,248 B (kit 4,298), 1,896 B free (kit 1,846) (+53: `follow_select`'s HOLD / FEAR filter 20, `use_icon`'s Whirlwind no-roll 11, `turn_input`'s post-action hero HOLD_GUARD clear 11, `act_pend`'s 5, `st_step`'s hero skip 6); L-RELIEF: 4,195 B (kit 4,245), 1,949 B free (kit 1,899) (+354: `follow_select` / `place_follower` / `arrival_conflicts` from bank 3 (+4: `follow_select`'s PROTO tail `jp far3` `follow_admit`), `do_exit`'s two `ld hl` / `call far3` → plain calls (−6)); before: **3,781 B** (`B7_LEN`, `-DDEBUG_KIT=0`; 3,831 B with the kit; **D3-8 review +37**: the held-path wake return in `turn_input`, `use_icon`'s refusal split (`IC_REFUSED`), `conf_roll`'s mid-ladder test, `mon_status`' cork yield; **2,363 B free** (kit 2,313)); **D3-8e2: 3,841 B (kit 3,891), 2,303 B free (kit 2,253)** (+29 over the D3-8c merge's 3,812: `act_begin` sets `COMBAT_NOT_BEFORE`, `act_pend`'s log wait from max(`MON_AT`, it), `end_turn` clears it); D3-8e: 3,816 B (kit 3,866), 2,328 B free (kit 2,278) (+26: `act_begin`'s `probe_act_prep` + far3 `proj_pre` with the spell / ammo rank row); D3-8 review 2: 3,790 B (kit 3,840), 2,354 B free (kit 2,304) (+9: `use_icon`'s `IC_NOTGT` (NO TARGET) handling: the line on the plain path, a stumble on the reversed one); D3-8: 3,744 B (**+610**: `status7.asm` (`st_step`, `mon_status`, the confused / fearful hero), the `turn_input` held-hero / step hooks, `use_icon` / `ic_melee` / `ic_disp` / `try_horizontal` FEAR + CONFUSED hooks; 2,400 B free (kit 2,350)); D3-7 T7: 3,134 B; T7 review +50: the swallowed-tap latch `LOG_PDIR`, the Mage-aware pre-filter, `act_pend`'s wait-only drain; **D3-7 T7: +193** (3,084 B) = the named miss line / `ent_kind` / `miss_pre` (`abil_ammo7.asm`), the log drain (`end_turn` / `turn_input` / `act_pend`), `power_fire`'s `slot_live` + Power break, the `floor_pickup` pre-filter + `PD_AMMO`; T6: 2,891 B (2,941 kit), +318 = `abil_ammo7.asm` (`abil_ammo` / `ammo_fire` + the `msg_*` line composer) and the list-driven `floor_pickup` (replaces `potion_pickup` + the `ammo_pickup` stub); T5: 2,573 B (2,623 kit, measured at T7; was written 2,620), +546 = the power attacks (`abil_melee7.asm`), `potion_pickup` / `ic_quaff` / `debug_kit` from bank 3, `act_seq` / `act_begin_ok`; T4: 2,027; T1: 1,773, +157 = `act7.asm` + the fire stubs; T0: 1,616, +336 = `intent7.asm` + the D3-7 stubs; D3-S2: 1,280); free to the attr shadow: the current figure is the bold one above (history: T7 3,010 B (2,960 with the kit); T7 first pass: 3,060 / 3,010; T6: 3,253 / 3,203; T5: 3,571 / 3,521; T1: 4,371); ASSERT `b7_end <= B7_LIMIT` | tape block 6 together with tilesets 0–3 (`B7_TAPE_LEN` = `TSET_LO..b7_end`, `start` `.t7lo`) / .sna; `tests/gfx_integrity.py` asserts `B7_CODE..B7_LIMIT` == the .sna (no SMC, no data: the canary for the freed shadow) |

Sources are read only at generation time via `copy_virt` (virtual < `$C000` →
bank 1 at +`$4000`, else bank 3; a frame straddling `$C000` is split) — with
ZX0 only the raw items/tiles (`init_tiles`; 3E-T1: gone, boot6_tiles reads the boot block in place) go through `copy_virt` (A6: the
frame descriptors live in bank 5, `fdesc_tab`); the packed blocks are read by `dzx0_standard` straight from the
`$C000` window (a block never straddles virtual `$C000`: the tool pads it into
bank 3, ASSERTed). The pool
and attr-shadow banks are uncontended (0/4/6) resp. contended (7: erase attrs,
decor steps, the D3-S2 cold code).
`PORT_7FFD_SHADOW` always has bit 4 = 1 (48K ROM: charset, LD-BYTES).

Tape (LOAD-WIRE): BASIC `10 CLEAR VAL "24575": BORDER/PAPER/INK 0: CLS: POKE 23739,111`,
`15 LOAD "" SCREEN$`, `20 LOAD "" CODE`, `30 RANDOMIZE USR VAL "<start>"`; then the
**loading picture** (`assets/gfx/loading/loading_s2d.scr`, 6,912 B, "The Descent", variant S2d; generator
`tools/gen_loading_screen.py`) as a CODE block `$4000` + 6,912 B straight after the BASIC
and before the game CODE. It exists ONLY on the tape: `src/main.asm` parks the image's own
`$4000..$5AFF` bytes with SAVEBIN (`build/slot1_park.bin`), INCBINs the .scr there for that one
SAVETAP and INCBINs the parked bytes back, so the .sna / game image are byte-identical (0 game
bytes, banks and R6 free unchanged). The CLEAR must precede the picture (CLEAR CLSes). The ROM's
game-CODE header message clears rows 22-23 while that block loads, so S2d keeps them blank (bitmap 0, attr 7) (POKE 23739,111 only
drops the text; a DF_SZ poke scrolls the screen instead). `tests/tape_layout.py` parses the .tap
(block order, parity, .scr == block data). Game loader:
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
growth to `FRT_MAX`). Then six (3E-T1: seven)
**headerless** blocks (flag `$FF`) that `start` loads with ROM `LD-BYTES`
(each with its own rewind-and-retry loop; 3E-T1: one loop over `tape_tab`, 5 B
per block: bank, address, length, `$FF` end — retries the failed block) before falling into `boot`: bank 1
(`SRC_LEN_LO`), bank 3 from `$C000` (`BANK3_LEN` = source tail + bank-3 cold
code) and (A8) bank 3 from `AY_RESERVE` (`AY_LEN`: the AY slot, a separate
block so the gap below it is not on tape), (MEM-RECLAIM w2a) bank 7 from `B7_CODE`
(`B7_LEN`: the bank-7 cold code) and from `TSET_BASE` (`TSET_LEN` 1,224 B tilesets; the tape block is `B7D_LEN` = 1,253 B with `data7`: the
deduplicated level tilesets; two blocks so the attr shadow between them is not
on tape; was `TSET_LO` + code / `TSET_HI` before w2a; `#50` checks both after a
real tape load), (D3-TX) bank 0 from
`TEXT_ADDR` (`TEXT_LEN`: the text block; `check_paging`'s bank-0 probe byte,
written before it, is overwritten), (3E-T1) bank 6 from `BOOT6_ADDR`
(`BOOT6_LEN`: the boot block; **SRC6 spike: `BOOT6_TAPE_LEN` = the boot block + `SRC6_USED`, the block runs on through the SRC6 sources** — no 9th block, `tape_tab` unchanged), (R6, last = the 8th) bank 6 from `R6_ADDR`
(`R6_USED`: the R6 region's used bytes, not the whole `R6_LEN`). Nothing in bank 7 is live
while `start` runs: screen 2 is not displayed (`$7FFD` bit 3 = 0 from BASIC),
the attr shadow / screen 2 are written only after `boot`, and the 128 editor's
bank-7 workspace is abandoned with BASIC (PROTO never returns to it). The
`.sna` enters at `boot` (all banks preloaded). `tests/game.py` #50 checks bank
1, bank 3 (whole `BANK3_LEN`), the AY slot (`AY_LEN`), both bank-7 tileset
blocks (code + tilesets), the bank-0 text block (D3-TX), (R6) the R6 region (`R6_USED`; its only runtime writes, `drop_put`'s `dp_*`, happen after the menu), (3E-T1) the bank-6 boot block — at the menu, after
boot, still intact: the boot pool ends in bank 0 (3F-T1: the 2 idles only; `ALLOC_IDX` < 2 checked; `POOL_BOOT_NEED`
ASSERTed), so it is compared, not masked — and the low-RAM cold block byte-equal to the `.sna` after a real tape
load, and IM 2 installed.

### Boot block (3E-T1, memory levers (a) + (d))

`src/boot6.asm`, assembled by `main.asm` in pool bank 6 **just below the R6
region** (R6, 2026-10-21; was the top of bank 6, `$F86B..$FFFF`):
**3F-T2: `$D466..$DBFF` (R6 grew 8 pages: SRC6 `$DC00..$DCFF`, R6 `$DD00..`)**; SRC6 spike: `BOOT6_ADDR..SRC6_ADDR-1` = `$DC66..$E3FF` (default `SRC6_PAGES` 1; ASSERT `boot6_end == SRC6_ADDR`), `BOOT6_LEN` 1,946 B; before: `BOOT6_ADDR..R6_ADDR-1` = `$DD6B..$E4FF`, `BOOT6_LEN` **1,941 B** (phase lock: +3 B PHASE_TRAP clear; 1,938 before) (code 252 + data
1,689; ASSERT `boot6_end == R6_ADDR`; `BANK_BOOT6` = `BANK_POOL2`). Own
headerless tape block (SRC6 spike: it runs on through the SRC6 sources, `BOOT6_TAPE_LEN`), the 7th in `start`'s `tape_tab`; in the `.sna`
preloaded. `boot` runs it through `farb` (C = `BANK_BOOT6`) twice, both before
`alloc_reset`: `boot6_init` (under DI: the IM 2 install — vector table, ISR
image → `ISR_ADDR`, I, IM 2 — and the power-on state + `KEYTAB`, the screen
clear, the entity table clear) and `boot6_tiles` (after EI + `build_bitrev`:
`tiles_common` → `TILE_GLYPHS` / `TILE_ATTRS` 0..31, `orn_glyphs` →
`ORN_GLYPHS`, `panel_hot_img` → `HOT_COPY`, `font6x8` → the `FONT6` planes, all
read in place: no `copy_virt3`, no `GEN_SRC` staging, ~30k T). **Dead after
boot by contract:** the boot pool (3F-T1: the 2 select idles only, was every monster kind + the idles;
`POOL_BOOT_NEED` ASSERTed ≤ bank 0 + bank 4) never reaches bank 6, the hero
start's pool may overwrite the block — so it costs the pool nothing
(`POOL_NEED` 44,096 of `POOL_CAP` 46,472 unchanged, slack 2,376 B kept for 3F; 3E-T4b: slack now 2,588, see its ledger),
and **nothing may read it after `boot`** (`tests/game.py` #61: boot-block code may
run only below the select screen — bank-6 PCs in `BOOT6_ADDR..r6_code_end` during boot, only `R6_ADDR..r6_code_end` (far6 targets, by design) after it; no SMC / data writes in the block,
`tests/zx0_pool.py` seeds its reference from the snapshot's bank 6).
Boot-only proof per item (3E-T1 audit, `grep` of `src/`): `font6x8` — only
`panel_boot` read it (`FONT6` planes are built once; print6 / the menus read
`FONT6` or the bank-1 menu font); `panel_hot_img` — only `panel_boot`
(`HOT_COPY` is never rewritten); `tiles_common` — only `init_tiles`
(`level_load_tiles` writes ids 32..63 and *sets* the theme ids' attrs, it never
re-reads the depth-1 set; nothing rewrites `TILE_GLYPHS` 0..31 —
`tests/gfx_integrity.py` GI1 checks it after every depth); `orn_glyphs` — only
`init_tiles` (`orn_cells` reads `ORN_GLYPHS`); `keytab_defaults`, the ISR image,
the state init — only `boot` (new game / death / win / menu never re-run it).
Source files are unchanged (DEC1 etc. edit them as before): `tiles_common` =
`assets/gfx/tiles/tiles_common.asm` (`tiles_common_glyphs` / `tiles_common_attrs`,
`TILES_COMMON_LEN` ASSERTed 288), `orn_glyphs` = `assets/gfx/panel/panel_orn.asm`,
`font6x8` = `assets/gfx/fonts/font6x8.asm`, the hot image = `src/panel_hot.asm`;
only the INCLUDE moved (main.asm `vdata` → `src/boot6.asm`, in that order).
Not boot-only, left in bank-1 `vdata`: `panel_icons` (every `panel_init`,
per level), `status_icons` (`mk_room`, per room; `st_icons_draw`).

### R6 region (2026-10-21; user-approved carve of the pool slack)

A **permanent** code + data region at the top of bank 6: `R6_ADDR..$FFFF` =
**3F-T2: `$DD00..$FFFF`, `R6_LEN` 8,960 B (`(27 + R6_GROW) × 256`, `R6_GROW` 8 pages, defs.asm)** — **3F-T7: `R6_GROW` 10, `$DB00..$FFFF`, `R6_LEN` 9,472 B** (+2 pages from the D7 pool slack, manager 2026-10-29) (was `$E500..$FFFF`, `R6_LEN` **6,912 B** (`defs.asm`; `$1B00`, so ≥ 2.4 KB pool
slack is kept; `LOW R6_ADDR` = 0 ASSERTed: `alloc`'s test reads only the
high byte)). Carved out of `POOL_CAP` 1:1 (46,704 → **39,792**; need 37,312,
slack **2,480**; 3F-T2: `POOL_CAP` 37,481, level need 32,288, PROTO 37,312): `alloc` ends bank 6 at `R6_ADDR` (`tests/ovl.py` R1,
`tests/zx0_pool.py` model). Own headerless tape block, the **8th** (last;
`R6_USED` bytes, not `R6_LEN`); in the `.sna` preloaded; `tests/game.py`
#50 compares it after a real tape load. Code: `src/r6.asm` (rules in its
header), ORGed at its `$C000+` address, entered only through **`far6`**
(`gfx.asm`, bank 2: `ld c, BANK_R6` / `jr farb`, 4 B taken from the
`kind_tab` ALIGN pad 72 → 68; far3 + 12 T). Packed overlay streams come
LAST (`r6_blobs`), run by `ovl_run` with C = `BANK_R6`.

| Address (kit build) | Size (kit / release) | What |
|------|------|------|
| `$E500` `r6_code` | 602 / 584 | `pickup6.asm` (was bank-3 `pickup3.asm`): `pot_sync`, `pu_add`, ~~`pot_take1`~~ (3E-T12: deleted, −9 B), `kit_add` (+ kit lists; the `DEBUG_KIT` extras are the 18-B difference), `mon_drop`, `drop_put` + `dp_*` (5 B, written in play), `drop_tab`, `uniq_tab`; then `bag6.asm` (was `bag3.asm`, `BAG6_LEN` 187): `bag_add`, `bag_find`, `bag_take`, **3E-T13 `bag_discard` (+20)**, `bag_pick` |
| **MEM-RECLAIM w2c (2026-10-30)** | **R6 free +185 B (release 1,283 -> 1,468, kit 1,212 -> 1,397)** | icon packing: `icons16` 1,376 B raw -> `icpk_idx` + `icpk` 995 B (−381), unpacker code +196 (`icons6.asm` `ic_find` / `ic_scr` / `ic_unp` (unrolled oct, ~50 B: `fi_slot` runs on a drop's kill tick, budget lcastf) / `rev8`; `ic_blit`'s copy pass gone; `fi_slot`'s FI_INK fill x4 unrolled). Decoded byte-exact (tools/icons16.py proves the Python model; the screen tests compare against the raw table). Stack: none (decoded onto the screen / into `FI_GLY`). Costs (ic1, incl. far6): `icon_slot` 2.45k -> 3.1k T, a MIRROR icon 4.5k, `worn_draw` 9.4k -> 16.3k (3 MIRROR placeholders), `fi_slot` ~+0.7k T per new slot; budget lcastf 123,059 -> 123,743 T |
| **MEM-RECLAIM w2b (2026-10-30)** | **R6 free 229 -> 1,283 B release (kit 158 -> 1,212; 1,292 / 1,221 before the Spider climb commit took 9 B)** | cold code moved **R6 -> bank 7** (`B7_CODE` space freed by w2a): `hunger7.asm` (`hunger_turn` (end_turn calls it directly, was far6; `wear_apply` stays R6, far6 from it on a wear turn), `hg_faint`, `food_sub` / `food_dirty`, `hunger_add` (far7 from R6 `fx6`), `hg_stage` / `hg_line`); `trap7.asm` (`trap_turn` (jp from `trap_chk`), `trap_step` (jp from `act_pend`), `tr_*`, `tr_eff` (far6 R6 `tele_arm` / `fx_line`), `hero_hold`; `tr_draw` calls `ap_put_a` directly); `boss7.asm` (`grate_open` far7 from bank-3 `mon_drop`, `boss_chk` far7 from `lp_transition`, `ai_guard` far7 from bank-2 `ai_ghook`). Their read-only tables (`tr_ink7`, `tr_fx`, `glow7`; 29 B) are `data7.asm` in bank 7 right after the tilesets (`data7..data7_end`, one tape block with them, `B7D_LEN`; bank-7 code keeps no data). Stay in R6: `item_food` + `hg_attr` (panel render: never from contended bank 7), `tele_arm` / `tele_flash` / `trap_at` (R6 `fx6` / `pickup6` call them), `lp_post`; `mummy6` inlines its `food_sub` (13 B). Tests call the moved entries through far7 (`B7_LABELS` in hunger / status1 / tier6, t16). |
| (code, after `ranged6`) | **800** (3F-T9) | `spawn6.asm`: the spawn queue producers `breed6` / `sp_bcall` / `ph_summon` + `sp_summon` (the pose: ranged6 `rg_pose`, now shared with `rg_shoot`), `sp_scan` / `sp_wt` / `sp_fit` (§9.3 cap), `sp_run` (end_turn) + `sp_init` / `sp_y` / `sp_place` / `sp_try` / `sp_door` / `sp_fin`; no variables (bank-5 `SPQ_RAM`) — see "3F-T9" |
| (code, after `spawn6`) | **~225** (3F-T9 bat) | `vbat6.asm`: `vb_one` (far6 from bank-7 `vb_turn`, end_turn) + `vb_bat` / `vb_fin` / `vb_st` / `vb_gap` / `vb_cut`; no variables — see "3F-T9 Vampire bat form" |
| `$E75A` `ovl_page_zx0` | **1,182** (3E-T13; was 328) | the bag page stream (`BANK_OVL_PAGE`; was bank 1) |
| ~~`ovl_items_zx0`~~ | 0 (was 881) | **MEM-1: back in bank 1** (`BANK_OVL_ITEMS` = `BANK_UI1`, after the `it_text` block; R6 holds only `ovl_page_zx0` now, 1,192 B of streams incl. the page stream; the R6 addresses below shift down 881 B) |
| (code, after `bag6`) | 310 code+data (**STATUS1: +55** `hg_faint`) | **3E-T9** `hunger6.asm` — **MEM-RECLAIM w2b: `hunger_turn`, `food_sub` / `food_dirty`, `hunger_add`, `hg_stage` / `hg_line` moved to bank 7 (`hunger7.asm`); only `item_food`, `hg_attr` (4 B) stay here** — see "3E-T9" |
| (code, after `hunger6`; release `$E889..$EC72`) | **1,001** (680 code + data + 337 generated) | **3E-T8** `gear6.asm`: `hero_recalc`, `gear_dec`, `rmax`, `enchant_weapon`, `fx_line`, `it_fmt`, `gx_tab` (35), vars `gd_*` / `hr_*` (18, written in play), + `items_fx_stems.asm` (`it_fx_stems` 249 + `it_stat` 88, resident: `hero_recalc` needs `it_stat` outside any overlay) — see "3E-T8" |
| (code, after `gear6`; kit `$EC6E..$EFD9`) | **876** (code + 10 B vars) | **3E-T12** `fx6.asm`: `fx_main` (the page verbs), the exits `fx_take` / `fx_turn` / `fx_none` / `fx_noneed`, `fx_equip` / `fx_remove` / `fx_done` (T8, were the overlay), `fx_quick` (icon-bar POTION / FOOD / SCROLL), `fx_use`, `fx_eat`, `fx_read`, `fx_book`, `pot_eff` + `cap_add` (from bank 7), `it_amt`, `tele_pick` + `tp_ok`, vars `fx_slot` / `fx_type` / `fx_cand` (10 B, written in play) — see "3E-T12" |
| ~~`ovl_fx_zx0`~~ | 0 (was 174) | 3E-T8's effects overlay **retired by 3E-T12** (ZX0 packed it 3 %: resident code costs ~6 B more and no map save / unpack) |
| (code, after `fx6`) | **648** (`TRAP6_LEN`; no variables; **STATUS1: +38** = `hero_hold` + the STUN arm; was 610) | **3E-T16** `trap6.asm` — **MEM-RECLAIM w2b: `trap_turn`, `trap_step` and the `tr_*` helpers moved to bank 7 (`trap7.asm`); `tele_arm` / `tele_flash` / `trap_at` stay in R6** (historical list: `trap_turn` (the input-tick decision: trigger / Mage sense / search; `tr_arm`), `trap_step` (the sequence: `tr_eff` DART far3 `trap_hit` + the impact FX / GAS / TELEPORT / ALARM stub, the plate and hero flashes, `tr_final`), `tele_arm` / `tele_flash` (scroll + trap), `trap_at` / `trap_glyph`, `tr_*` helpers, `tr_ink6` (4), `tr_fx` (16, the DART impact descriptor template, copied to `MSG_BUF` per use: trap6 writes no R6 byte) — see "3E-T16" |
| (code, after `trap6`) | **~420** (MEM-RECLAIM w2c: +196) | **IC1** `icons6.asm`: `icon_slot` / `ic_slot` / `ic_draw` / `ic_clr` / `ic_blit` (attrs + the 2x2-cell clear), `worn_draw`, `worn_cell`, `qs_draw`; **w2c: the unpackers `ic_find` (logical → stream, was `ic_addr`), `ic_scr` (straight onto the screen), `ic_unp` (32-aligned linear: `fi_slot` → `FI_GLY`), `ic_sstep`, `rev8`** — see "IC1 item icons" |
| (data, after `icons6`) | **995** (MEM-RECLAIM w2c; was 1,376 raw) | **IC1 + FLOOR1** `icpk_idx` (43) + `icpk` (952) (`assets/gfx/icons/icons16.asm`, generated by `tools/icons16.py`; the raw `icons16` table stays in that file under `IF 0` as the tests' reference): **45 logical icons, 43 packed** (+ the 2 floor-ammo icons, − Mana / Cure: the potions share Heal's shape, user 2026-10-27; `ic_find` maps logical → physical); per icon 2 columns × 2 octs (mask byte, 1 = repeat the column's previous byte, + literals), 13 MIRROR icons store the left column only; read only by `icons6.asm` (the ISR never reads it) |
| (code, `pool6.asm`) | **334** (was 71) | **3F-T2** `pool6.asm` rewritten: `pool_hero` / `pool_proto` / `pool_list` (+ `pl_kinds`, `pl_begin`, `pool_map`, `pl_unit`, `frt_none`, `fxr_none`), `gu_tab` (64: the generation units, was `kind_tab` `KT_FID0` / `KT_FCNT`), `pool_gmap` / `pool_xmap` (1 + 1, empty) — "Level pool" / "Sequence cache (3F-T2)" |
| `sqm_zx0` (after `ovl_page_zx0`) | **280** (3F-T13: **420**, 711 B raw) | **3F-T2** the sequence masters stream (`src/seq_img.asm`, 437 B raw, unpacked to `SQ_IMG` per `pool_*` call) |
| `r6_end` .. `$FFFF` | **3F-T13: 1,300 free kit / 1,328 release** (−175 vs main `b2c300a`: the real 3F sequence blocks, units / gmap / xmap, the PROTO limit pokes; "Real 3F art (3F-T13)"); **3F-T10 (`-DF3_GEN=1`, default 0 = byte-identical to main): switch off 1,551 free release unchanged, bank 3 68 free unchanged; switch on 1,409 (−142: `src/sanct6.asm` `sanctum_leaf` = LVL_FLAGS 0 + the D8 Sanctum leaf, `jp far6` from `level_gen`'s tail; bank 3 −2 B → 70 free, a build with the switch on is what `tests/levelgen_z80.py --f3` runs; **`F3_GEN=1` is NOT yet the default**: the world (170) and lp (90) suites fail only as oracle mismatches (they call `generate()` without f3; `LVL_FLAGS` 0 shuts the grate: W16/W25 descents, W11/W26/A1 blocks), so the suites must become f3-aware and T8 must open the grate first)**; **3F-T2: 1,523 free kit / 1,551 release** (+8 pages = +2,048; −263 `pool6.asm` growth, −280 `sqm_zx0`; target ≥ 1,500 for 3F code); **3F-T1: 19 free** kit / 47 release (−71: `pool6.asm` `pool_list` 30 + `pool_map` 21 + `pl_add` 19 + `pool_gmap` 1; before it 90 on main `78b064a`); **STATUS1: 379 free** kit / 396 release (−101 / −102: `hg_faint` + `hero_hold` + the STUN arm of `tr_eff` + the TOO SICK check, `tr_ink6` +1, the 5th type; "STATUS1" below); **IC1: 480 free** kit / 498 release (−1,605: `icons16` 1,376 + `icons6` code ~225 + `pot_sync` +~17 + `fx_done` +5, the page stream −115 (1,192 → 1,077 packed)); **RANK1+MEM-1: ~2,085 free** kit / ~2,103 release (RANK1 −90 `fx_book`, re-verified by the build DISPLAY); **MEM-1: 2,175 free** kit / 2,193 release (+881: items stream to bank 1); before: 1,294 free kit / 1,312 release (3E-T16: −621); before: **1,915 free** kit / 1,933 release (3E-T12 review round; first T12 pass 2,043 / 2,061; after 3E-T8: 2,737 / 2,755) | `R6_FREE` (build DISPLAY) |

Callers: bank 7 `floor_pickup` → far6 `pu_add`, `use_slot` → far6
`fx_quick` (3E-T12; was `ic_quaff` → `bag_find` / `pot_take1`), `do_exit` → far6 `tele_pick`, bank 1 `page_post` → far6 `fx_main`, `new_game` → far6 `kit_add` (each +12 T vs far3,
same bytes); bank 3 `deal_hit` (kill path) → `ld hl, mon_drop` / `call
far6` (+3 B, ≈ +0.25k T per kill: R6 is paged over bank 3 while `mon_drop`
runs and bank 3 comes back after; `mon_drop` / `drop_put` use only bank-2 /
bank-5 helpers + far1 `it_line` / far7 `ap_stamp_a`; the bank-3 `hla` is
inlined), `level_populate` → far6 `pot_sync` (+3 B, ≈ +0.25k T per level
start). Measured (`tests/pickup3e.py`): pickup 21.6k T, kill + drop 12.7k,
boss + unique 19.1k; `budget.py` gate unchanged (pmix 127,791).

**Rule for later tasks** (3E T8 / T9 / T12 / T13–16, 3F): new cold code,
overlay streams and 3F sprite sources go to R6 — code into `r6.asm`
(before `r6_code_end`), streams after `r6_blobs` (INCBIN + their `BANK_OVL_*`
= `BANK_R6`); **sprite sources go to the SRC6 region just below R6** (SRC6 spike: `zx0_frame`'s third source bank, "SRC6 region").
`R6_LEN` is the cap: `ASSERT r6_end <= $10000` (an overflow DISPLAYs the
excess first); growing `R6_LEN` costs the pool 1:1 (`POOL_NEED <= POOL_CAP`
ASSERT) and must keep `LOW R6_ADDR` = 0.

| Ledger (kit build; release in brackets) | Before R6 (main `78dfcbd`) | After R6 | Δ |
|------|------|------|---|
| bank 1 free (`UI1_LIMIT − bank1_end`) | 91 | **1,300** (MEM-1: 241 = 1,122 − 881, the items stream back) | +1,209 (the two streams) |
| bank 3 free to `AY_RESERVE` | 29 (47) | **603 (603)** | +574 (+556) net: pickup + bag code out, +6 for the two far6 call sites |
| bank 7 free | 22 (72) | 22 (72) | 0 (far3 → far6, same size) |
| low RAM spare (`LOWRAM_SPARE`) | 103 (113) | **93 (103)** | −10: `alloc`'s bank-6 limit +5, the 8th `tape_tab` record +5 |
| bank 2 `kind_tab` pad / free to FRT | 72 / 18 | **68** / 18 | −4: `far6` |
| pool (`POOL_CAP` / slack) | 46,704 / 9,392 | **39,792 / 2,480** | −6,912 |
| bank-6 boot block | `$F86B..$FFFF` | `$DD6B..$E4FF` | moved below R6 (boot pool ends in bank 4: unchanged) |
| tape | 7 headerless blocks | 8 | net data +8 B (1,791 in R6 − 1,209 bank 1 − 574 bank 3); one more pilot + gap ≈ +2–3 s on real tape |
| cold paths (`zx0_pool.py`) | boot → select 4.54M T | 4,540,964 T | ≈ 0; hero start ('1') 5,388,886 T |

### SRC6 region (SRC6 spike 2026-10-27; 3F memory plan, `feat/src6-spike`)

**ANIM-X12 (2026-10-30, X1 Orc + X2 Vampire 4th walk pose):** `SRC6_PAGES` default **16**
(`$C800..$D7FF`, 4,096 B): `orc_walk4` / `vamp_walk4` (new WK0 frames; walk2 / walk3 redrawn) grow the
K_ORC / K_VAMPIRE blocks +75 B: 14 blocks, 9,888 raw -> **3,876 B packed, 220 free** (15 pages overflowed
by 36 B; reordering FRM rows saves only ~18 B in all, so a page it is). `POOL_CAP` 32,538 -> **32,269**;
R6 untouched (free 229 release). `FID_COUNT` 136 -> **138** of 144. Both walks `MOVECYC4 walk2, walk1,
walk3, walk4` (even slots WK4, odd WK0). Pool need +480 B on every level with the kind: Orc D4 D6 D7,
Vampire D3 D6 D8. Slack per level after (`POOL_CAP` 32,269), Warrior / Mage:
D1 8,077 / 11,213, D2 8,621 / 11,757, D3 4,077 / 7,277, **D4 2,285 / 5,357**, D5 7,789 / 10,861,
D6 2,765 / 5,965, D7 2,861 / 6,061, D8 2,445 / 5,645 (before, 15 pages: worst D4 3,034 / 6,106).
**Pending (T11): the nun Archmage** (~393 B packed, 2,080 B pool on D8, 4 ids) will need roughly one more
SRC6 page (-256 B pool every level): D8 Warrior slack then ~2,445 - 2,080 - 256 = **~109 B** (D8 becomes
the worst level; Mage ~3,309). `tests/walk_feet.py`: the Vampire XFAIL is gone; `vp_move` measures its
sloped boots over the bottom 3 rows (others: bottom row).

**ANIM-IMPORT2 (2026-10-30):** `SRC6_PAGES` default **15** (`$C900..$D7FF`, 3,840 B): + `K_VAMPIRE` (the
Vampire's own 40-px set, 2 blocks 675 B), 14 blocks, 9,408 raw → **3,801 B packed, 39 free**; boot block
`$C141..$C8FF`. 13 → 15 pages = −512 B `POOL_CAP` (33,050 → 32,538); R6 is not touched. The `zx0_pool`
**src6** variant keeps `K_VAMPIRE` in banks 1 / 3 too (16 pages max).

**3F-T13bc:** `SRC6_PAGES` default **13** (`$D000..$DCFF`): 12 blocks (+ `G_CLIMBH`, the ART2 /
ART3 / ART4 frames; `dk_block` out), 8,736 raw → **3,231 B packed, 97 free**; boot block
`$C863..$CFFF` ("ART2 / ART3 / ART4 wiring (3F-T13bc)").
**3F-T13 (as built, kit build):** `SRC6_PAGES` default **10** (`$D300..$DCFF`, 2,560 B), holding
the real 3F-A1 art: `SRC6_KINDS` = `K_SPIDER K_ORC K_NECRO K_MUMMY K_OGRE K_DKNIGHT G_DEADH
G_NBOLT` (`G_*` = frame groups with no kind: `defs.asm` `BH_G_*`), 8 blocks, 6,240 raw → **2,393 B
packed, 167 free**; `SRC6_STANDIN` default **0** (the spike stand-ins are retired: generated but not
assembled). Boot block now `$CB63..$D2FF`. **PROTO exception:** a PROTO-fixture game pools OVER
the SRC6 sources — R6 `pool_proto` writes `alloc.lim6 + 1` (SMC, `lowram.asm` `alloc`) =
`HIGH R6_ADDR`, `pool_hero` (every game start) puts `HIGH POOL6_END` back. Rooms A-D hold no 3F
kind and no stairs, so a PROTO session never reads SRC6; a test that descends from PROTO must
reload the snapshot first (SRC6 is overwritten: a PROTO session clobbers ~1-2.3 KB of the SRC6 sources for that power-on, reload needed). **Guard:** `pool_list` (every `level_enter`) checks the limit byte; if it is not `HIGH POOL6_END` it bumps `GEN_TRAP` and resets it (16 B in R6; test `tests/gfx_integrity.py` G-lim6). `POOL_CAP_PROTO` = `POOL_CAP` + `SRC6_LEN` =
37,540, the 6-kind fixture's bound 37,312 is ASSERTed again (slack 228). `tests/zx0_pool.py` S6
decodes every real SRC6 block; its **src6** variant = the default set + `K_WIZARD`,
`-DSRC6_PAGES=18 -DPOOL_PROTO_CHECK=0 -DPOOL_LVL_CHECK=0` (new define: skips the level-need
ASSERT; the variant never descends).

The **permanent bank-6 sprite-source region**: `SRC6_ADDR..R6_ADDR-1`, just
**below** R6 (R6 is unchanged: `$E500..$FFFF`, its free tail stays at the top,
480 kit / 498 release), the boot block just below it. `SRC6_LEN` =
`SRC6_PAGES` × 256 (`defs.asm`, `-DSRC6_PAGES=n`; default **1 = 256 B at
`$E400`**), carved out of `POOL_CAP` 1:1 (`POOL_CAP` = 3 × 16 KB − text −
`R6_LEN` − `SRC6_LEN`); the pool's bank-6 part ends at **`POOL6_END`** =
`SRC6_ADDR` (`alloc` tests `HIGH POOL6_END`, `LOW` = 0 ASSERTed). Main.asm
"SRC6 REGION", generated `build/zx0/src6_zx0.asm` (`tools/zx0_sources.py`):
* the blocks of the FRM kinds in `SRC6_KINDS` (tool constant, empty until 3F;
  env `SRC6_KINDS=K_A,K_B` overrides for a test build): same DP partition and
  per-frame EQUs as banks 1 / 3, but `nm EQU zblk_N - SRC6_VDELTA`;
* the 3F pool-spike **stand-ins** (`tools/pool_spike.py` `STAND_IN`, one block
  per group, `s6s_<i>`, bit i of `SRC6_STANDIN`; default 1 = Spider 185 B);
  nothing references them (no FRM line). Order / packed B: 0 SPIDER 185,
  1 ORC 338, 2 NECRO 470, 3 MUMMY 560, 4 OGRE 464, 5 DK 770, 6 ARCHER_SHOOT
  193, 7 DEAD_H 98, 8 NBOLT 101 = 3,179.

**`zx0_frame` virtual map** (`FD_BLK`, the `GEN_ZBLK` key): `$4000..$7FFF` =
SRC6 (bank 6 at + `SRC6_VDELTA` `$8000`), `$8000..$BFFF` = bank 1 at
+`$4000`, `$C000..` = bank 3. No `FD_FLAGS` bit is spent and the cache key
stays unique by construction (+8 B low RAM: `bit 6,a` / `jr nz` / `set 6,h`
/ `ld a, BANK_SRC6`; +20 T per bank-1 unpack, +30 T per SRC6 unpack; the
same stream decodes in the same T from bank 6 — the src6 E2E variant's
timings equal the default build's ±40 T). Read-only at runtime; on tape it is
the tail of the boot block's tape block (`BOOT6_TAPE_LEN`; `SRC6_FREE` above
the blocks is not on tape). Tests: `tests/zx0_pool.py` (bank-6 compare to
`POOL6_END`, SRC6 == snapshot at every point, **S6** decode of each stand-in
via `zx0_frame`, variant **src6** = the whole pool run with the Wizard's 4
blocks in SRC6), `tests/game.py` #50 (SRC6 == `.sna` after a real tape load),
`tests/ovl.py` R1 (`alloc` stops at `POOL6_END`).

| Build | `SRC6_LEN` | used | `POOL_CAP` | need (static) | slack |
|---|---|---|---|---|---|
| before (main `2401565`) | — | — | 39,785 | 37,312 | 2,473 |
| **default** (1 page, Spider) | 256 | 185 | 39,529 | 37,312 | **2,217** |
| 9 pages (max today; DK+NECRO+OGRE+ORC+SPIDER) | 2,304 | 2,227 | 37,481 | 37,312 | 169 |
| 13 pages (full lean 3,179) | 3,328 | 3,179 | 36,457 | 37,312 | **−855: ASSERT fails** |

**3F-T1: `POOL_NEED` is per level** (worst depth; "Level pool (3F-T1)"):
32,288 of 39,529 today, slack **7,241** (was 2,217); the table above was
computed with the old static need. Before 3F-T1: the full lean 3F source set did NOT fit until 3F's
per-level pool landed (need = the worst level, `docs/design/pool_spike.md`:
D7 Warrior 35,168 → with 13 pages slack **1,289** B). Decode cost (S6,
measured, DI): ~200 T per packed byte — Spider 185 → 416 B 40.8k T, the DK
stand-in 770 → 1,440 B **159.7k T** (worst block; once per block per generator
session).

### Level pool (3F-T1, `feat/3f-t1-pool`)

The pool holds the 2 select idles, the hero + its class FX and **one level's
monster kinds** (was: every monster kind, boot-generated).

* **boot** (`lowram.asm`): `gen_idles` = `alloc_reset` + the 2 idles; FRT rows
  saved (`sel_frt_copy`). No alloc mark at boot.
* **`start_game`**: `gen_idles` again (the select mark is gone: the idles
  regenerate to the same bytes at the same place, ~0.2M T), **3F-T2: far6
  `pool_hero` + `gen_list`** (the hero's unit, then unit `hero + K_FX_BASE`;
  was `gen_kind` ×2), **`alloc_mark` = the LEVEL mark**
  (`ALLOC_MARK_IDX` / `ALLOC_MARK_PTR`, `$BF45..$BF47`). PROTO rooms
  (`proto_start` 1, the test fixture): then every original monster kind
  `K_SKELETON .. K_PROTO_END − 1` (= `K_SLIME`; `POOL_NEED_PROTO`; 3F-T2: far6 `pool_proto` + `gen_list`).
* **`level_enter`**, after `far3 level_new` (LG_* + the items overlay are dead,
  no room map yet, `GAME_STATE` = `GS_LEVEL`), before `stinger_wait` (the
  generation overlaps the stinger): `alloc_restore` (level mark; drops
  `GEN_ZBLK`), `far6 pool_list` (3F-T2: its `pl_begin` does the **FRT rows
  `[KFID_MONSTERS, + KFCNT_MONSTERS)` := `FRT_NONE`** — was level_enter's LDIR —
  a kind not generated this level blits nothing and counts `BLIT_MISS`
  instead of drawing stale pool bytes; ASSERT monsters lie between the heroes
  and `KFID_FXM` — and the FX rows outside the class FX := NONE) → `PL_LIST`,
  then `gen_list`; `GS_TRANSITION`.
* **3F-T2 FX rows (`fxr_none`, every `pool_*` session):** the FX FRT rows
  `[KFID_FXM, KFID_FXW + KFCNT_FXW)` outside the hero's class FX unit :=
  NONE — the other class's exclusive rows (a previous game's hero) and any
  hero extra of the previous level never point at stale pool bytes (T1 note:
  a monster bolt / arrow drawing another class's FX row). Today nothing draws
  them (0 visible change).
* **`pool_list`** (R6 `src/pool6.asm`): `LP_KINDS[0..3]` + `LP_BOSS` (5) →
  **`pool_map`** → the generation **units** (3F-T2), + the hero extras
  (`pool_xmap`), deduplicated per unit (by fid0), first-seen order, as
  **pairs `fid0, fcnt`**, `$FF`-terminated in `PL_LIST` (= `GEN_SRC` `$6940`,
  `PL_CAP` 25 B; free between `level_new` and `panel_init`; not the LP
  scratch — `tests/lp.py` B0G reads `LP_HX..` after a new game); low-RAM
  `gen_list` generates each pair's frames. **3F-T2 generation units
  (`gu_tab`, R6, DB fid0, fcnt):** units 0..31 = the kinds' own ranges (the
  old `kind_tab` `KT_FID0` / `KT_FCNT`, only the generator read them),
  units ≥ 32 = extra ranges with no kind (a SHOOT frame, the Necro bolt, the
  Mage's arrows; none yet; ≤ 64 units). Monster / extra units must not
  overlap (dedup by unit).
* **Generation map** `pool_gmap` (R6; 3F-T2: `g1` / `g2` are **unit** ids):
  records `DB kind, u1, u2` (`u2` = `PG_NONE` $FF: none), `$FF`-terminated,
  first match wins (**3F-T13: every matching record applies**, "Real 3F art"); a mapped kind generates u1 (+ u2) **instead of** its own
  unit, an unmapped kind its own unit. Shared / tier rows → their base
  unit (Vampire / Archmage → Necro, a tier → its base kind); two units for
  e.g. Archer (Skeleton-walk unit + SHOOT unit) or Necro (+ bolt). Units must
  not overlap (dedup is per kind). **3F-T3: nine records** (`K_SPIDER` → the
  Rat unit; `K_VAMPIRE` / `K_ORC` / `K_ARCHER` / `K_MUMMY` / `K_NECRO` / `K_OGRE` / `K_DKNIGHT` /
  `K_ARCHMAGE` → the Skeleton unit) = the **stand-in frames** until T13 (real art
  replaces each record); the 12 tier rows have no record: their `gu_tab` row IS their base
  kind's range. **3F-T2 hero extras `pool_xmap`** (R6):
  records `DB kind, hero kind, unit`, `$FF`-terminated: on a level listing
  the kind, a game of that hero also generates the unit (game.md: the Mage's
  `arrow_fly1/2` on Archer levels D4 / D5 / D7, `dagger_spin` on D1 / D2).
  Empty today (no Archer id yet). An extra unit must lie outside that hero's
  class FX unit (`fxr_none` NONEs it at the next level entry). The build-time
  need counts an extra for either hero (conservative, ≤ 128 B a level).
* **Build-time need** (main.asm "LEVEL POOL NEED", after R6): per depth the
  assembled `lp_dtab` bytes → `pool_gmap` + `pool_xmap` → the unit set
  (dedup as at run time; two 32-bit masks) → `gu_tab` (3F-T2) → per fid
  `frame_tab` cols / H / offsets + `fdesc_tab` `FD_FLAGS` →
  the exact bytes `gen_frame` allocates. Read with sjasmplus `{b}`, so they
  are valid only in the last pass: `POOL_LVL_MAX`, `POOL_LVL_WORST`,
  `POOL_NEED` are **DEFL** (in the `.sym`), defined there and used nowhere
  above (the SRC6 DISPLAY no longer prints the slack). `POOL_NEED =
  POOL_FIXED (2 × 480 idles since ANIM-IMPORT2, was 2 × 576; + 3 × 576 straddle) + POOL_HERO_MAX +
  POOL_LVL_MAX`; ASSERTs `POOL_NEED ≤ POOL_CAP` and `POOL_NEED_PROTO ≤
  POOL_CAP` (`-DPOOL_LVL_VERBOSE=1` DISPLAYs every depth).
* Tests: `tests/zx0_pool.py` (the reference replays boot / hero / level
  sessions bit-exact; "levels": a Knight game D1..D8 through the real
  `level_descend`, pool / FRT / allocator == reference at every depth, pool
  top ≤ `POOL_NEED`, level_enter ≤ 2 s); `tests/gfx_integrity.py` GI1 (below
  the level mark == hero start, the level kinds generated, other monster
  rows NONE, after play == depth entry).

| Depth | kinds (LP + boss, dedup) | monsters B | need, Warrior | measured pool top (Knight, B from `POOL_START`) | `level_enter` (DI stub) |
|---|---|---|---|---|---|
| D1 | Rat, Bat, Slime, Goblin | 9,184 | 27,904 | 26,345 | (new game: select '1' → tick 7.66M T = 2.16 s, was 5.39M) |
| D2 | Goblin, Rat, Bat | 7,808 | 26,528 | 24,969 | 3.38M T (0.95 s) |
| D3 | Skeleton, Ghost, Bat | 11,392 | 30,112 | 28,553 | 4.08M T |
| D4 | Goblin, Rat, Skeleton | 12,160 | 30,880 | 29,321 | 4.27M T |
| D5 | Skeleton, Rat | 8,000 | 26,720 | 25,161 | 3.53M T |
| D6 | Skeleton, Ghost, Goblin | 13,568 | **32,288** | 30,825 | 4.48M T |
| D7 | Goblin, Skeleton, Ghost | 13,568 | 32,288 | 30,889 | 4.49M T |
| D8 | Goblin, Skeleton, Ghost | 13,568 | 32,288 | 30,889 | **4.52M T (1.27 s)** |

| Ledger (kit build) | Before (main `78b064a`) | After 3F-T1 | Δ |
|---|---|---|---|
| `POOL_NEED` / slack (`POOL_CAP` 39,529) | 37,312 static / 2,217 | **32,288 (worst D6) / 7,241** | −5,024 need |
| PROTO rooms need (`POOL_NEED_PROTO`) | (= the static need) | 37,312 / slack 2,217 | the binding term once SRC6 grows past ~2.2 KB: see "open" below |
| low RAM spare (`LOWRAM_SPARE`) | 77 | **29** | −48: level_enter pool block 43, `gen_idles` / start_game / proto loop +5 net |
| R6 free (kit / release) | 90 / 118 | **19 / 47** | −71: `pool6.asm` |
| bank 2 / bank 3 / bank 1 / bank 7 | 13 / 48 / 91 / 27 | unchanged | 0 (`GS_LEVEL` is a constant) |
| boot → select | 4.54M T | **1.21M T** | −3.33M (no monster kinds at boot) |
| per-tick cost | — | 0 | nothing on the tick path |

**Open (3F-T1):** the PROTO-rooms fixture still generates all six original
kinds (37,312 B): with SRC6 at 13 pages (`POOL_CAP` 36,457) its ASSERT fails
first — before 3F grows SRC6 past ~2.2 KB either the PROTO pool must shrink
(e.g. only its `spawn_tab` kinds per room is the same set; drop a kind from
the fixture, or a Wizard-only PROTO) or the tests move off PROTO. R6 has 19 B
left: the freed pool slack (+5,024) would pay for an R6_LEN +256 (manager
decision).

### Sequence cache (3F-T2, `feat/3f-t2-mem`)

The kind animation sequences (prototype §7: idle / move / climb cycles,
climb-rest, attack / hurt / block / death seqs + `KS_IMPACT`) are **masters
in R6** and a **per-level cache in bank 2** (was: every kind's 17-B
`kind_seqs` row + its sequences resident in bank 2, 446 B for 8 kinds; 3F's
9 new base kinds + 12 tier rows would have added ~0.65 KB).

* **Masters** `src/seq_img.asm`: `ksm_tab` (`K_MAX` words: each kind's block,
  0 = none; **a tier row names its base kind's block** → tiers cost 2 B of
  packed image, 0 B of bank 2, and share the base's cache slot), then one
  block per base kind: `KSM_LEN` n, `KSM_IMP` (= `KS_IMPACT`), `KSM_OFF` 8
  offsets (the `KS_*` order) from `KSM_SEQ`, then the n sequence bytes
  (no pointer inside: position-independent). Assembled in main.asm
  "OVERLAYS" DISPed at **`SQ_IMG` `$6980`** → `build/ovl/seq.bin` (437 B
  raw) → ZX0 → R6 **`sqm_zx0`** (280 B). The macros / role EQUs stay in
  data.asm.
* **Cache** (bank 2): **`seq_rows`** (`SQ_SLOTS` 7 × `KS_STRIDE` 17 = 119 B,
  one page, in the `kind_tab` ALIGN pad right below `dt_attr_tab`; zeros in
  the image) — slot 0 = the hero, 1..6 = the level's monster blocks (PROTO:
  all 6 original kinds); **`seq_bytes`** = `code_end` .. +`SEQB_LEN` 256
  (runtime only, below `FRT`), the rows point in. **`kind_tab` `KT_SEQ`**
  (runtime) = the low byte of each kind's row: `kind_seq_ptr` is 2 table
  reads (61 T for every kind, was 65 + 24 T per kind id: 257 T for the Slime,
  ~0.76k for a 3F id 29; keeps BC / DE, so `anim_entity`'s two push / pop
  pairs went too), `set_reaction_at` the same (+ `KS_IMPACT`).
* **Loader**: R6 `pool_hero` / `pool_proto` / `pool_list` → `pl_begin`
  unpacks the masters (`dzx0_standard` → `SQ_IMG`, ~60k T) and calls the
  low-RAM loader: `sq_reset` (no slot, `SQ_TOP` = `seq_bytes`, the hero's
  block → slot 0: the same bytes at the same place every time, so the
  hero's live `E_SEQ` stays valid across a level change), `sq_load` (A =
  kind: its block → the first free slot unless cached; rows = `SQ_TOP` +
  offset), `sq_fill` (`KT_SEQ` of all 32 kinds; a kind whose block is not
  cached gets slot 0's row — no entity of such a kind exists in play; test
  pokes of an uncached kind would animate with the hero's sequences). Scratch
  `SQ_PTR` / `SQ_TOP` / `PL_PROTO` in `GEN_SRC` (bank 5 table). No R6
  variable, no SMC.
* **Build check** (main.asm "SEQ CACHE NEED", after OVERLAYS, final pass,
  from the raw image bytes): per depth (`lp_dtab`) and for PROTO, the
  distinct blocks ≤ `SQ_SLOTS` − 1 and the largest hero block + their bytes
  ≤ `SEQB_LEN`. Today: **hero 49 + monsters 204 (PROTO) = 253 of 288** (3F-T13bc: `SEQB_LEN` 256 → 288; the build DISPLAYs every depth: D1..D8 177..207, D4 the worst level 207; was 253 of 256 after 3F-D7LEV), ≤ 6
  blocks. 3F (T3) raises `SEQB_LEN` as it adds blocks (each byte = 1 B bank
  2; expect ~+40 B for the worst 3F level's larger blocks).
* Tests: `tests/frames_phase.py` reads the masters from `build/ovl/seq.bin`;
  `tests/abil.py` S7 / `tests/proj3.py` read `KS_IMPACT` through `KT_SEQ`.

### 3F-T2 ledger (MEM-3F; kit build, release in brackets; measured, `tools/build.sh` DISPLAY)

| Region | Before (main `eee0f06`) | After 3F-T2 | Δ / lever |
|---|---|---|---|
| **bank 2 free** (to `FRT` + `kind_tab` pad) | 13 + 36 = **49** | 549 + 126 = **675** | +626: `FRT_MAX` 160 → 128 +512; seq cache +80 (−455 sequences / `kind_seqs` / `kind_rest`, +119 `seq_rows`, +256 `seq_bytes`); `kind_tab` −24; code −10 |
| bank 2 free, 3F-B1 ERASE-AIR | 675 | **651** | -24: `erase_rect` `.air` path (xor a / 8 stores) 20 B + `jp .third` out of line 3 B +1 (`.third` block moved after `.item` so the `jr c,.hi` / `jr z,.air` stay in range); build-time ASSERT in `boot6.asm` (TILE_GLYPHS[0..7] == 0), `tests/eraseair.py` |
| bank 2 free, 3F-B2 PRESENT-RUN | 651 | **636** | -15: `present` — all-zero `HUD4_PW` skipped in one OR pass (+9), screen highs re-patched per third (`.thd` SMC, +~14), cell low byte = mask low * 8 (the per-row `.rb` base and its patch gone, -~8), bit loop exits on the shift flags (`jr nc` / `jr c` / `jr nz`, the `inc c / dec c` test gone) |
| **R6 free** | 19 (47) | **1,523 (1,551)** | +2,048 (`R6_GROW` 8 pages), −263 `pool6.asm` (units, extras, FX rows, seq entries), −280 `sqm_zx0` |
| pool `POOL_CAP` / need / slack | 39,529 / 32,288 / 7,241 | 37,481 / 32,288 / **5,193** | −2,048 (R6) |
| PROTO rooms need / slack | 37,312 / 2,217 | 37,312 / **169** | the binding term (3F-T1 "Open"): no further R6 / SRC6 page fits until the PROTO fixture shrinks |
| low RAM spare (`LOWRAM_SPARE`) | 29 | **50** | +160 descriptor reserve (`FRT_MAX`), −139 net code (the seq loader in, `gen_kind` / its loops / level_enter's LDIR out) |
| bank 3 free to `AY_RESERVE` | 48 | **68** | +20: `kx_melee` → `kx_tab` `KX_MELEE` |
| bank 1 / bank 7 / AY slot | 91 / 27 / 169 | unchanged | 0 |
| per-tick cost | — | ≤ 0 | `kind_seq_ptr` 61 T flat (was 65 + 24 × kind), 2 push / pop pairs fewer in `anim_entity`; `set_reaction_at` −~60 T |
| new-game / level_enter | — | + ~0.1M T per `pool_*` session (unpack ~60k, FRT rows ~15k, seq ~10k) | cold |

**Levers not applied:** kind_tab "3rd page 8 → 5 B/kind" (the page does not exist yet: T3 adds the 3F columns after `KT_END` `$1B8` — 72 B to the page end — at 5 B/kind as game.md §9.7 R5.6, i.e. ≤ 160 B); font trim M1(c) (not needed: bank 2 ≥ 650).
**Projection for 3F (pool, `docs/design/pool_spike.md` S + Bat + the 3F rulings):** D7 Warrior 35,168 − 768 (Archer SHOOT = the resident Necro cast) + 640 (Orc 24×48) = **≈ 35,040 worst**; D5 33,120 (SHOOT = the resident Skeleton cut; a Mage there 29,856 incl. the arrows ≤ 160), D4 32,032, D8 33,376. Against `POOL_CAP` 37,481 − the 3F SRC6 growth (lean 3,179 B → +12 pages = 3,072) = 34,409 → **short ≈ 0.6 KB** with stand-in sizes, before the cut order (game.md §9.7 R5) or smaller real art; and the PROTO fixture (37,312) must shrink before any SRC6 growth (ASSERT).

### Kind rows (3F-T3, `feat/3f-t3-rows`)

**Ids** (`defs.asm`, the single source; `tools/levelgen.py` `KROWS` asserts the same ids when it
loads): 0 Warrior, 1 Mage, 2 hole (**3F-T9: `K_VBAT`, the Vampire's bat form**), 3 Skeleton, 4 Goblin, 5 Ghost, 6 Rat, 7 Bat, 8 Slime (unchanged),
**9 Spider, 10 Vampire, 11 Orc, 12 Archer, 13 Mummy, 14 Necro, 15 Ogre, 16 Death Knight, 17 Archmage**,
then the 12 tiers in the §9.6 table order **18 Giant Rat, 19 Rabbit Rat, 20 Screech Bat, 21 Slinger,
22 Black Widow, 23 Skel Guard, 24 Skel Knight, 25 Poltergeist, 26 Orc Berserker, 27 Orc Bouncer,
28 Sniper, 29 Bone Caller**; `K_COUNT` 30, 30 / 31 the class FX kinds (`K_MAX` 32). `K_BOSS_D1..8` =
Goblin, Spider, Vampire, Ogre, Mummy, Necro, Death Knight, Archmage (a golden boss is the base row +
a per-entity flag, §9.7 R1: T8). `lp_dtab` is unchanged text-wise (it already carried the §9.4 table).

**Where the data lives** (all 30 rows complete; 0 B of bank 2 growth):
`kind_tab` columns (`main.asm` `KROW`, 30 args: BW BH HP ATK EVA DIE BONUS REACH PERIOD FLAGS ATTR;
hp / atk / eva / die / bonus = the game.md §9.1 / §9.6 table values before depth scaling, `KT_PERIOD`
2 for Slime / Vampire / Mummy, climbers only Goblin / Skeleton + tiers, §9.7 R3); `kx_tab` rows
(`combat_data3.asm`: resistances, immunity (Ogre / Death Knight / Archmage `1 << IMMF_BOSS_BIT`,
Berserker FEAR), KXP (§4.1 table; Ogre 60, Death Knight 90, Archmage 0), **`KX_DEF` = the §9.1 / §9.6
DEF for the NEW rows** (Orc 1, Mummy 2, Ogre 2, Death Knight 3, Archmage 1, Guard 2, Knight 3,
Berserker 1, Bouncer 2; the nine 3D rows stay 0, game.md §11.4 — Skeleton / Slime DEF 1 in §9.1 is
still unapplied: manager / designer call), `KX_MELEE` = the **on-hit status**, which `deal_hit`
already applies: Spider POISON 12 / Black Widow 24 / Giant Rat 1-in-4 POISON 12 (turns nibble = half,
`PSN_*`), Mummy 1-in-3 WEAK 12, Screech Bat 1-in-4 CONFUSED 2, Skeleton Knight 1-in-4 STUNNED 1,
Orc Bouncer 1-in-3 STUNNED 1, Poltergeist DRAIN touch 1-in-3 FEAR 3, **Vampire `DTY_DRAIN | DH_HEAL`**);
`lp_wt` (30 B, `WT_K_*`, Slinger 3 + 1); `drop_tab` (above). **Not data (T6-T9 code keyed on the id)**:
parry (Skeleton Guard 1 in 4, Knight / Death Knight 1 in 3, notch 1 in 2), ACID, FOOD drain, rage,
breed, summons, SLAM, ranged (Archer / Sniper / Slinger / Necro / Archmage), bat form, golden, the
random-food drop of Screech / Widow / Guard / Knight / Poltergeist. There are **no spare KX bytes**
(`KX_STRIDE` 8 is full); T6 needs a home for the parry chance (a 3-row table or the third
`kind_tab` page at `KT_END`).

**Stand-ins until T13 (real art)** (**superseded by 3F-T13**, "Real 3F art (3F-T13)" below): each new base kind borrows the frames **and** sequences of the
nearest existing body so it plays today: `pool_gmap` (R6) maps Spider → the Rat unit and Vampire /
Orc / Archer / Mummy / Necro / Ogre / Death Knight / Archmage → the Skeleton unit; `ksm_tab`
(`seq_img.asm`) points them at the Rat / Skeleton block; the 12 tier rows name their base's block
(`ksm_tab`) and range (`gu_tab`). `KT_BW` / `KT_BH` are the stand-in body (`defs.asm` `BH_K_*`;
Ogre 4 cols and the real heights are T13's), `KT_ATTR` inks are provisional (tiers per §9.6,
bases differ from them). The seq cache holds one slot per **block**, so a D-level needs <= 3 slots
(Rat / Skeleton / Bat ...): `SEQB_LEN` stays 256 (PROTO still the 253 B worst after 3F-D7LEV; 3F-T13bc grew it to 288).

**PROTO fixture (T2 input "shrink it")**: the 21 names add 192 B of text (see below), which took the
PROTO 6-kind pool bound 23 B over `POOL_CAP`. `proto_start` is now a bit field: **bit 0 = PROTO rooms,
bit 1 (`PS_SLIME_BIT`) = also pool the Slime** (`pool_proto` drops the last kind of its list when
clear). The build asserts the 5-kind fixture (`POOL_NEED_PROTO5`, slack 1,353 B) and DISPLAYs the
6-kind one (slack -23 B: conservative bound, real top is lower); `tests/game_lib.py` / `tests/game.py`
#50 poke `proto_start = 3`, so every PROTO suite still sees the Slime. A default `-DPROTO_START=1`
build shows an invisible Slime (BLIT_MISS).

**Build checks**: the level pool need is computed **per hero** (`main.asm` "LEVEL POOL NEED":
`pool_xmap` records count only for their own hero; POOL_NEED = max over Warrior / Mage; verified
with a temporary `K_ARCHER, K_WIZARD, K_SLIME` record: the Mage's D4 / D5 / D7 masks gain the unit,
the Warrior's do not).

**Names** (`strings.txt`, ids `TX_NM_KNIGHT + kind`): <= 9 chars (`NM_LONG` = 9: "YOUR DAGGER MISSES
THE " + name fits the 32-char log) — SPIDER VAMPIRE ORC ARCHER MUMMY NECRO OGRE D. KNIGHT ARCHMAGE
GIANT RAT RABBIT SCREECHER SLINGER BLK WIDOW SK GUARD SK KNIGHT POLTERGST BERSERKER BOUNCER SNIPER
BONE CALL (the designer's longer names are abbreviated; edit the strings, ASSERTs re-check).

| Region | Before (main `bd311b7`) | After 3F-T3 | Δ |
|---|---|---|---|
| bank 2 free | 675 | **675** | 0 |
| bank 3 free to `AY_RESERVE` | 68 | **10** | -58: `lp_wt` +21, `drop_tab` +33 (12 x 4 B) and `mon_drop` +3 (the numerator) |
| R6 free (kit) | 1,523 | **1,475** | -48: `pool_gmap` 27, `gu_tab` tier rows (in the old 0-row hole: 0), `pool_proto` +8, per-hero need 0 |
| text (bank 0) | 2,455 | **2,647** | +192 (21 names; ~9 B each incl. the 3 B table cost) |
| pool slack (worst level) | 5,193 | **7,177** | the stand-ins share units: D3 11,392 B is the worst level now; real art in T13 re-derives it |
| PROTO 5 / 6 kinds slack | 169 | **1,353 / -23** | see the fixture note |
| low RAM spare | 43 | 43 | `proto_start` bit only |

### Monster tiers at spawn (3F-T5, `feat/3f-t5-tiers`)

**What**: the §9.6 tier roll, the lair escort / boss golden flag and the depth-scaled spawn hp in `lp_enter`
(game.md §9.4.3, §9.6, §9.7 R1, 3F-D2 rulings); Python reference `tools/levelgen.py` `lp_enter(f3=True)`,
`tests/lp.py` A7 (>= 1,000 levels, Python == Z80 record by record). No build switch: it is on in every build.
- **`src/tier6.asm` (R6, new)**: `lp_gen` (far6 from `lp_enter` for a FRESH record: the whole unit loop, ONE far6 per room
  entry) = the ordinary room's quota x `gen_fit` (the stream's `rnd(4)`, then `tier_row` = the roll, then the fit order
  rolled tier -> its base -> the other `LP_KINDS` ascending at base) or the lair (boss `LP_BOSS`, weight + 1 if golden,
  then one never-rolled escort); `gen_unit` writes `{kind byte, kind_hp}`; `gen_step` is `lg_step` re-coded (R6 cannot
  call bank 3); `tier_tab` (9 bases x {base, tier 2, tier 3}), `T2_BASE` / `T3_BASE` (9 B each, entry 0 unused),
  `lp_wt6` (= bank-3 `lp_wt`, both expanded from the macro `LP_WT_ROWS` in `lpop3.asm`), `kind_hp`,
  and (moved unchanged from bank 3 `drop3.asm`) `drop_row` + `drop_tab` (12 x 4 B, same results).
- **Tier roll**: `r` = the low byte of ONE stream step, only for a kind that has tiers (Slime, Vampire, Mummy and the uniques:
  no step); `T2 = max(0, T2_BASE[d] + 16 d)`, `T3 = d >= 4 ? max(0, T3_BASE[d] + 8 d) : 0`, `d = clamp(LP_LVL - depth, -2, 2)`
  (caps 160 / 80 are unreachable, ASSERTed; exact for `LP_LVL <= 120`).
- **Golden**: `lp_dtab` boss bytes of D1-D3, D5, D6 carry `LEK_GOLD` (`LP_BOSS`); `E_GOLD` (entity +23) = `LEK_GOLD` on the
  slot (`lp_spawn`), written back by `lp_bank`; **pool consumers mask `LP_BOSS`** (`pool6.asm` `pl_kinds`, `main.asm` `PLK4` / `SQK4`,
  `mon_drop`'s boss test). Nothing reads `E_GOLD` yet (glow, atk / DEF flag, `dest_counts` weight + 1: T8).
- **hp fix (the stand-in bug)**: spawn hp was the unscaled `KT_HP` in the record (`.unit`) and in `E_MAXHP` (`spawn_one` ->
  `init_ent_common`). Now record hp and `E_MAXHP` = row hp + (`LVL_DEPTH` - 1), golden 2 x that + 6 (R6 `kind_hp` for the record,
  the same arithmetic inline in `lp_spawn` for `E_MAXHP`). The T12 trickle must call `kind_hp`. The PROTO rooms (depth 0) keep the
  unscaled rows.
- **Python/test notes**: `tests/lp.py` takes the body widths from `kind_tab` (`sync_bodies`: the Ogre stand-in is 3 cols, KROWS 4).

| Region | Before (main `b2c300a`) | After 3F-T5 | Δ |
|---|---|---|---|
| bank 3 free to `AY_RESERVE` | 10 | **269** | +259 (incl. +23: golden +1 in dest_counts and follow_admit via kind_wt, the mon_drop golden-body test) |
| R6 free (kit / release) | 1,475 / 1,503 | **872 / 914** | -603 / -589: `tier6.asm` 587 + 2 align pad (lp_gen etc. ~480, `lp_wt6` 30, `tier_tab` + tables ~45, `drop_row` + `drop_tab` ~100) |
| bank 2 / low RAM / bank 1 / bank 7 | -- | unchanged | 0 |
| `lp_enter` (DI, incl. far3 + the one far6) | mean 20,247 / worst 44,397 (A2 sample) | A2 sample mean 20,367 / worst 40,098; A7 sweep (1,040 levels, 7,258 entries) mean 20,172 / median 19,623 / 90% 28,776 / worst 44,093 | budget mean <= 22k / worst <= 46k (§9.8 D3-2) |

### Tier abilities + gear wear (3F-T6, `feat/3f-t6-abil`)

game.md §8.10, §9.1, §9.6, §9.8 D3-7. Tests `tests/tier6.py` (P1-P3 parry, W1-W2 wear, R1 rage, M1 Mummy, X1 half XP,
D1 food drops) + budget `tmix`.
- **Parry** (bank 3 `deal_hit`, `.dmg`): kind-id compare (Death Knight, `K_SKEL_GUARD`, `K_SKEL_KNIGHT`; 59 T for any other target),
  PHYS only; a parrier calls R6 `parry6` (E = chance /256 `PARRY_GUARD` 64 / `PARRY_KNIGHT` 85, D = `dh_rtick`: != 0 = a shot,
  no notch). Result: **L = 0, H = 1** (new out: H = 1 iff parried, 0 on every other exit; `deal_hit` clobbers H already), the Death
  Knight gets `RC_BLOCK` (`set_reaction_at`; Guard / Knight have no BLOCK frame and no hit flash since L = 0).
  The line is the hero's E_MSG `MSG_P_PARRY` (15): `do_attack` sets it (no input-tick log push), `melee_hit` returns H = 2,
  `melee_strike` (bank 7) passes it to `impact_line`; `imp_pre` / `imp_post` +1 entry, text "THE BONEGUARD PARRIES!" (the existing
  `cmb_parries`; the design's "PARRIED" is this string).
- **Rage**: `hit_roll` (bank 3), Orc Berserker, `2 hp <= max hp` -> +`RAGE_ATK` 2 to the roll (33 T for every other attacker).
- **Mummy FOOD / Black Widow ACID**: `do_attack` (bank 3) on a hit that cost HP: attacker `K_MUMMY` -> R6 `mummy6` (`food_sub`
  `FOOD_MUMMY` 5), `K_BLACK_WIDOW` -> `acid6` (1 in 4: armour else helm). The curse (WEAK) stays the KX_MELEE pair.
- **Wear** (R6 `src/abil6.asm`): `wear_slot` = m - 1, or the slot emptied at m -3; ORs its bit into **`WEAR_PEND`** (new, `$BC5E`, the
  last byte of the HERO3D spare: **the spare is now FULL**; cleared by `level_reset_new`): bit 2 s = notch / acid, bit 2 s + 1 = broke
  (s = weapon / armour / helm), so two events of a turn both stay. `hunger_turn` (end_turn far6, +8 B) calls `wear_apply` =
  `hero_recalc` once + per affected slot its line (break line when it broke) + `worn_cell` (~6k + ~4k per slot, never on the input tick).
- **Review fixes (fix-then-ship)**: a held target (ST_FLAGS HOLD: STUNNED / FROZEN / ASLEEP) never parries (+10 B bank 3); a parried
  dagger / arrow prints the PARRIES line (`pf_strike` stores `pf_lost` = $FF on H = 1, `ammo_fire` reads it); the hero's weapon bonus
  is SIGNED (`hero_recalc` no longer clamps) and `do_attack` / `melee_hit` roll max(1, 1dN + bonus), so a notched weapon at m < 0 hits
  for less. Notes for later: no parry sound (T8); the Death Knight BLOCK on a parried Power Strike starts at the strike tick
  (`set_reaction_at` adds the attacker's IMPACT), not the blow's own tick.
- **Drops** (`tier6.asm`): `drop_tab` 12 -> 17 rows; type 0 = a random Carrot / Apple / Pear (`rng_mod 3`) for the Screech Bat,
  Black Widow, Skeleton Guard / Knight, Poltergeist (1 in 4). **F_RESPAWN half XP** was already in `deal_hit` (tested X1).

| Region | Before (main `6edd76e`) | After 3F-T6 | Δ |
|---|---|---|---|
| bank 3 free to `AY_RESERVE` | 265 | **121** | -144 (deal_hit hook 72, rage 19, do_attack 43, melee_hit 6, pf_strike 5, level_reset_new 3) |
| R6 free (release) | 723 | **517** | -206 (`abil6.asm` ~177, `drop_row` +14 / 5 rows +20, `hunger_turn` +8) |
| bank 7 free | 72 | **53** | -19 (`melee_strike` parry line, `ammo_fire` parry line) |
| low RAM spare | 43 | **37** | -6 (`show_impact_msg` +4, `imp_*` +2) |
| bank 2 | 508 | 508 | 0 |

Budget (worst ordinary work tick, cap 126,000): `pmix` 116,906 -> **116,906** (unchanged), `mix` 111,465, `mage` 107,619; new `tmix` (pmix + Skeleton Guard / Black Widow / Orc Berserker re-kinded, the deferred wear forced onto the first end_turn) **119,052** (seed-dependent 107.8k-119.1k; the Widow / Berserker bodies have no PROTO frames, so their draw is skipped and only the hooks are measured). Tier-ability costs: parrier PHYS hit +~0.3k (far6), other targets +59 T; rage +33 T per `hit_roll`; Mummy / Widow hit +~0.3k; wear event: input tick ~0.2k, end_turn ~8k once.

### Real 3F art (3F-T13, `feat/3f-t13-art`)

The 3F-A1 lean frames replace the T3 stand-ins (frames, sequences, bodies, inks).
* **Frames** (`src/frames.asm`, fids 101..123 after the Slime; still inside the monster
  range `[KFID_MONSTERS, + KFCNT_MONSTERS)` that `pl_begin` NONEs): Spider walk1/2 + bite,
  Orc / Necro / Mummy / Ogre walk1/2 + attack (cast / slam), Death Knight walk1/2 + cleave +
  block, `dead_humanoid` (`G_DEADH`), `nbolt_fly1/2` + `nbolt_hit` (`G_NBOLT`). `FID_COUNT`
  124 of `FRT_MAX` 128 (4 spare). The **Skeleton is reordered** (walk1..4, **cut**, raise,
  collapsed, climb1/2, hurt) so the Archer's frames are a prefix; `rat_dead` is its own unit.
* **2-frame walk (pool lever, docs/conventions.md "Walk cycles"):** `MOVECYC2 walk2, walk1` —
  WALK1 (the rest pose) in the ODD slot, drawn cell-aligned exactly like its rest / attack /
  death uses, so it is `WK0` (one shift) and WALK2 the `WK4` stride: one shift each instead of
  MOT + WK0 = **−576 B per 24×48 kind** (Ogre −768, Spider −256), ~−1.7 KB on D7. KS_CLIMB of
  these non-climbers = their idle cycle (never the move cycle: its even slot is WK4).
* **Units** (R6 `gu_tab`; ≥ `K_MAX`): 32 `U_SKARCH` (Skeleton walk1..4 + cut = the Archer /
  Sniper), 33 `U_SKREST` (raise .. hurt), 34 `U_DEADR` (`rat_dead`: Rat, Spider), 35 `U_DEADH`,
  36 `U_NBOLT`, 37 `U_ARROWM` (`arrow_fly1/2`), 38 `U_DAGM` (`dagger_spin1/2`); kind rows 9..17 =
  their own frames (Vampire / Archmage rows name the Necro's: informational), the Rat's row =
  its 4 body frames; tier rows = their base's (never generated: tiers are not in `LP_KINDS`).
* **`pool_gmap` — every matching record applies** (was: first match; `pl_kinds`, the
  build-time `PL_KIND`, `tests/zx0_pool.py` / `tests/gfx_integrity.py`): 13 records, 40 B —
  Skeleton → `U_SKARCH` + `U_SKREST`; Rat / Spider → own + `U_DEADR`; Orc / Mummy / Ogre / DK →
  own + `U_DEADH`; Archer → `U_SKARCH` + `U_DEADH` (SHOOT = the Skeleton cut everywhere,
  game.md §9.7 DECIDED: the designer's preference; fits); Vampire → Necro + `U_DEADH`; Necro /
  Archmage → Necro + `U_DEADH`, + `U_NBOLT`. `PL_CAP` 25 → 35 (≤ 5 kinds × 3 units + 2 extras;
  per-depth `ASSERT 2 × units + 1 ≤ PL_CAP`). **`pool_xmap`** (per hero): Archer → Mage
  `U_ARROWM` (128 B on D4 / D5 / D7), Goblin → Mage `U_DAGM` (64 B on D1 / D2).
* **Sequences** (`src/seq_img.asm`): own blocks `ksm_sp` (Black Widow), `ksm_or` (Berserker,
  Bouncer), `ksm_ne` (Necro, Vampire, Archmage, Bone Caller), `ksm_mu`, `ksm_og`, `ksm_dk` (+ the
  BLOCK seq), `ksm_ar` (Archer, Sniper: the Skeleton walk + cut, `dead_humanoid`); HURT = the
  rest frame held (the `$42` flash, §9.7 R4); their KS_CLIMBREST points at the HURT seq (anim
  `.crest` reads only the first byte = the rest fid; −2 B a block). Raw masters 437 → 711 B
  (`SQ_IMG`, 206 B left), `sqm_zx0` 293 → 420 B. Cache need unchanged: PROTO 251 of `SEQB_LEN` 256 is still the worst.
* **Bodies / inks** (`defs.asm` `BH_K_*`, `main.asm` KROW): Spider 32×16 (BW 4), Ogre 32×48 (BW
  4), the rest 24×48; inks Spider `$05`, Vampire **`$05`** (was `$03` = the Necro frames' ink),
  Orc `$04`, Archer `$03`, Mummy `$06`, Necro `$03`, Ogre `$44`, DK `$47`, Archmage `$04`.

| Depth (lp_dtab + boss) | monsters B, Warrior | need Warrior | monsters B, Mage (+ extras) | need Mage |
|---|---|---|---|---|
| D1 Rat Bat Slime Goblin | 9,184 | 27,904 | 9,248 (+64 dagger) | 23,776 |
| D2 Goblin Spider Bat Rat | 8,640 | 27,360 | 8,704 (+64) | 23,232 |
| D3 Skeleton Vampire Ghost Bat | 13,824 | 32,544 | 13,824 | 28,352 |
| D4 Orc Rat Spider Archer + Ogre | 11,648 | 30,368 | 11,776 (+128 arrows) | 26,304 |
| D5 Mummy Skeleton Archer Spider | 9,856 | 28,576 | 9,984 (+128) | 24,512 |
| D6 Vampire Ghost Necro Orc | 7,872 | 26,592 | 7,872 | 22,400 |
| **D7** Orc Archer Ghost Necro + DK | **15,360** | **34,080** | 15,488 (+128) | 30,016 |
| D8 Necro Skeleton Ghost Vampire + Archmage | 12,096 | 30,816 | 12,096 | 26,624 |

`POOL_CAP` **34,980** (37,284 − 9 SRC6 pages), `POOL_NEED` 34,080 (D7 Warrior), **slack 900**.

**3F-D7LEV (no art change):** the Skeleton / Goblin / Archer walk is `MOVECYC4 walk2, walk3,
walk4, walk1` (same cyclic order): WALK1 (the rest pose) sits in an odd, cell-aligned slot →
`WK0` (one shift; was MOT), WALK2 / WALK4 `WK4`, WALK3 `WK0`. The Ghost flies on its own
KS_MOVE `gh_fly` (FLOAT2 held, MOT) so FLOAT1 (idle at rest only) is `WK0`. Need per level
(Warrior / Mage), before → after:

| Depth | Warrior | Mage |
|---|---|---|
| D1 | 27,904 → 27,520 (−384) | 23,776 → 23,392 |
| D2 | 27,360 → 26,976 (−384) | 23,232 → 22,848 |
| D3 | 32,544 → 31,456 (−1,088) | 28,352 → 27,264 |
| D4 | 30,368 → 29,792 (−576) | 26,304 → 25,728 |
| D5 | 28,576 → 28,000 (−576) | 24,512 → 23,936 |
| D6 | 26,592 → 26,080 (−512) | 22,400 → 21,888 |
| **D7** | **34,080 → 32,992 (−1,088)** | 30,016 → 28,928 |
| D8 | 30,816 → 29,728 (−1,088) | 26,624 → 25,536 |

`POOL_NEED` **32,992** (D7 Warrior), **slack 1,988**; PROTO fixture 37,312 → 35,840 (slack
1,700). Asserted per level in `tests/zx0_pool.py` `LEVEL_NEED`. Sequence masters 711 → 713 B
raw (`gh_fly` +4, Ghost KS_CLIMBREST = `gh_idle + 1` −2), seq cache need 251 → **253** of 256.

| Region (kit build; release in brackets) | Before (main `b2c300a`) | After 3F-T13 | Δ |
|---|---|---|---|
| SRC6 | 1 page, 185 B stand-in | **10 pages, 2,393 B, 167 free** | +2,304 B carved from the pool |
| pool `POOL_CAP` / need / slack | 37,284 / 30,112 (D3) / 7,172 | **34,980 / 34,080 (D7) / 900** | real art |
| PROTO fixture (6 kinds) | 37,312 vs 37,284 (not asserted) | **37,312 of 37,540** (over SRC6, asserted) | `alloc.lim6` |
| bank 2 free (to FRT + pad) | 636 | **544** | −92: `frame_tab` +23 fids × `FT_STRIDE` 4 |
| R6 free | 1,475 (1,503) | **1,300 (1,328)** | −127 `sqm_zx0`, −48 `pool6.asm` (units +14, gmap +12, xmap +6, `pl_kinds` / limit pokes +16) |
| bank 1 free | 91 | **99** | +8: the Skeleton reorder packs 8 B smaller |
| low RAM spare | 43 | 43 | `fdesc_tab` +115 B came out of the `FRT_MAX` descriptor reserve (135 → 20); the cold block now starts at `$6F71`: the test-stub area `LOWRAM_END_3B` (`$6F32`) .. `lowram_code` is **63 B** (was 178; `tests/world.py` W17's decode buffer moved to `PAGE_MAP_SAVE` + 64) |
| bank 3 / bank 7 / AY slot | 10 / 27 (72) / 169 | unchanged | 0 |

### ART2 / ART3 / ART4 wiring (3F-T13bc, `feat/3f-t13bc`)

The user-approved ART2 (`feat/3f-art2-final`), ART3 (`feat/3f-art3-final`) and ART4
(`feat/3f-art4-dk`) frames, the new climbers and ARCHER-DEPTHS H1.
* **Frames** (`src/frames.asm`, 124 → **132 fids**, `FRT_MAX` 128 → **132**, 0 spare):
  `small_corpse` (STA|SYM, 32×16) replaces `rat_dead` in place (fid / unit `U_DEADR`
  unchanged: Rat, Spider + tiers); `orc_raise` (Orc: walk1, walk2, raise, attack);
  Necro split: `necro_walk1..3` (= the `K_NECRO` unit), `necro_cast` (`U_NCAST`), `vamp_bite`
  (`U_VBITE`); Mummy walk1..4, attack (the 4 + 1 block order); `ogre_raise` (walk1, walk2,
  raise, slam); `dk_walk3`, **`dk_block` removed**; `climb_h1` / `climb_h2` (group `G_CLIMBH`,
  `BH_G_CLIMBH` 6, unit **`U_CLIMBH`**) after `nbolt_*` (the monster range ends there,
  ASSERTed). Orc ATTACK / Ogre SLAM / Orc walk1/2 are redrawn in place by the art branch.
* **Units / map** (R6 `pool6.asm`): new `U_CLIMBH` (K_MAX + 7), `U_NCAST` (+ 8), `U_VBITE`
  (+ 9); `pool_gmap` 13 → 17 records (52 B): Vampire → Necro walk + `U_VBITE` + `U_DEADH`;
  Orc / Archer / Necro → + `U_CLIMBH` (one shared group, generated once per level: dedup per
  unit); Necro / Archmage → + `U_NCAST`. A duplicate `LP_KINDS` entry (D7: two Necros) is one
  unit set (pl_unit dedups by fid0, the build macro ORs a mask, sq_load dedups by block).
* **Sequences** (`seq_img.asm`, raw 713 → 781 B, 136 B left in the `SQ_IMG` window; packed
  422 → 458 B): own blocks per kind (the `KSM3F` macro is gone): Orc RAISE 3 → ATTACK 2 +
  IMPACT, Ogre RAISE 3 → SLAM 2 + IMPACT (same timing as before: `KS_IMPACT` 3), Vampire
  `ksm_vp` (Necro walk B3 + `vamp_bite`; was `ksm_ne`), Necro / Vampire / DK `MOVECYC4 walk2,
  walk1, walk3, walk1`, Mummy `MOVECYC4 walk2, walk4, walk3, walk1`; climbers (Orc, Necro,
  Archer blocks, so their tiers too) `KS_CLIMB` = `CLIMBCYC climb_h1, climb_h2`,
  `KS_CLIMBREST` = that cycle + 1 (one byte read = `climb_h1`, ASSERTed STA); DK `KS_BLOCK` =
  its HURT seq (never started: see parry).
* **Climbers** (`main.asm` KROW `KT_FLAGS`): `KF_CLIMBER` for Orc 11, Archer 12, Necro 14,
  Berserker 26, Bouncer 27, Sniper 28, Bone Caller 29 (not Vampire / Archmage / DK / Ogre /
  Mummy / Ghost). No AI change (turn3 `.seek` / bank-7 follow read only the flag);
  `tools/levelgen.py` `CLIMBERS` (checked by `tests/lp.py` A0), `tests/combat_tables.py`.
* **ARCHER-DEPTHS H1** (user): `lp_dtab` D7 = Orc, **Necro**, Ghost, Necro (+ DK): no Archer
  on D7 (no Archer units, no Mage arrows there); `tools/levelgen.py` LP_TAB the same byte.
  The Archer 2-frame walk / unit split (architect L1) is DROPPED: the Archer keeps the
  Skeleton walk on D4 / D5 and climbs on the shared pair (D5: +576 B pool, slack is ample).
* **Death Knight parry** (no BLOCK frame): `deal_hit` sets **`RC_PARRY`** (5) instead of
  `RC_BLOCK`; `anim_entity .rest` starts it like `RC_DODGE` — no sequence (the rest pose),
  `E_FLT` = `PARRY_FLASH` 1, `E_FLA` = `ATTR_PARRY` `$46` (+6 B bank 2); `set_reaction_at`
  treats it as BLOCK for the never-downgrade rule (+4 B bank 3). The PARRIES line is unchanged.
* **FRT / bank 2**: `FRT` must be page-aligned (`blit_sprite` nibble swap), so `FRT_MAX` 132
  puts it at `$A700..$AF3F` (−256 B from the image's room); the 192 B above it to
  `P_ENTITIES` are **`FRT_GAP`** (runtime) and now hold **`seq_rows`** (119 B, `$AF40..`,
  one page, were zeros in the `kind_tab` ALIGN pad), 73 B free. `SEQB_LEN` 256 → 288.

| Depth (lp_dtab + boss) | need Warrior before → after | need Mage before → after |
|---|---|---|
| D1 Rat Bat Slime Goblin | 27,520 → 27,392 | 23,392 → 23,264 |
| D2 Goblin Spider Bat Rat | 26,976 → 26,848 | 22,848 → 22,720 |
| **D3** Skeleton Vampire Ghost Bat | 31,456 → **32,224** (worst) | 27,264 → 28,032 |
| D4 Orc Rat Spider Archer + Ogre | 29,792 → 31,776 | 25,728 → 27,712 |
| D5 Mummy Skeleton Archer Spider | 28,000 → 29,792 | 23,936 → 25,728 |
| D6 Vampire Ghost Necro Orc | 26,080 → 28,960 | 21,888 → 24,768 |
| D7 Orc **Necro** Ghost Necro + DK | 32,992 → 31,456 | 28,928 → 27,264 |
| D8 Necro Skeleton Ghost Vampire + Archmage | 29,728 → 31,840 | 25,536 → 27,648 |

`POOL_CAP` 34,980 → **34,212** (SRC6 10 → 13 pages), `POOL_NEED` **32,224 (D3 Warrior),
slack 1,988** (D7 2,756). PROTO fixture
35,840 → 35,712 of 37,540. Asserted per level in `tests/zx0_pool.py` `LEVEL_NEED`.

| Region (`-DDEBUG_KIT=0` build) | Before (main `b92ee7b`) | After 3F-T13bc | Δ |
|---|---|---|---|
| bank 2 free (to `FRT` + pad) | 293 + 215 = **508** | 261 + 40 = **301** (+ 73 in `FRT_GAP`) | −207: `FRT` page step −256 (192 back as `FRT_GAP`, 119 of it `seq_rows` moved out of the pad), `frame_tab` +32, `SEQB_LEN` +32, anim +6 |
| SRC6 | 10 pages, 2,394 B used, 166 free | **13 pages, 3,231 used, 97 free** | 12 blocks (+ `G_CLIMBH`, the new frames; `dk_block` out) |
| R6 free | 515 | **461** | −54: `pool_gmap` +12, `gu_tab` +6, `sqm_zx0` +36 |
| bank 3 free to `AY_RESERVE` | 106 | **102** | −4 (`set_reaction_at` RC_PARRY) |
| bank 1 free | 99 | **111** | +12 (`rat_dead` → the smaller `small_corpse` block) |
| low RAM spare | 37 | **17** | −20: +8 descriptors (40 B) out of a reserve 20 → 0 |
| bank 7 / AY slot | 53 / 169 | unchanged | 0 |

Ticks (work, cap 126,000): the PROTO budget suite unchanged or lower except Lightning
FROZEN-1 118,015 → 119,766 (worst gated); `pmix` 116,906 → 109,064; `tmix` 119,052 (the
Berserker kept non-climbing there: in rooms A-D it animates on the HERO's uncached sequence
row, Knight frames, so a climbing stand-in measured 128,300 — not a real cost). On a generated
level (scratch scripts, same seed vs main): D4 Knight vs Ogre RAISE/SLAM + Orc RAISE/ATTACK +
Rat + Spider worst 110,637 (= main; mean +5.5k: the raise frames), D7 Orc + Necro climbing to
the hero + Ghost worst 109,688 (main 109,713). Tests: `tests/climb3f.py` (C1-C5: Orc / Archer
on D4, Orc / Necro on D7, Archer + Skeleton on D5 climb on their climb art, Vampire / Mummy
never leave their storey, traps 0), `tests/tier6.py` P2 / P2b (RC_PARRY + the flash),
`tests/phase_soak.py` + D5 / D8 runs, `tests/world.py` W17 stubs moved to `GEN_SRC` + `$240`
(17 B left below `lowram_code`), `tests/zx0_pool.py` src6 variant 21 pages.
**Resolved (manager):** `ATTR_PARRY` was `$47` = the Death Knight's own `KT_ATTR`
`$47` (invisible): now **`$46`** (bright yellow), 1 tick, on the DK's own cells (cells it shares
with an overlapping hero take the last-drawn body's attr).

### Overlays (3E-T1) — `ovl_run`, the GEN_SCRATCH window; screen-2 window contract

**Build** (`main.asm` "OVERLAYS", `tools/build.sh`): each overlay is source
INCLUDEd at its runtime load address (`DISP`) into the bank-0 scratch
`OVL_RAW_ORG` `$E100..` (above `tap_loader`; bank 0 is pool at runtime, never
loaded) and SAVEBINed to `build/ovl/<name>.bin`. `build.sh` runs sjasmplus
twice: pass 1 (`-DOVL_PASS=1`, no packed streams) writes the raw images, each
is packed with `tools/bin/zx0` → `<name>.zx0`; pass 2 (`OVL_PASS` 2, the real
build) INCBINs the streams (`-i build/ovl`) into the **R6 region after its
resident code** (R6, 2026-10-21; was bank 1 after the UI code)
(`r6_blobs..r6_blobs_end`, labels = runtime `$C000`-window addresses, bank
`BANK_R6` = `BANK_OVL_PAGE` (MEM-1: `BANK_OVL_ITEMS` = bank 1, its stream after the `it_text` block); last in R6, so their sizes move nothing an overlay can
reference) and writes the raw images again: **build.sh fails if any differs
from pass 1**. Today: **`page`** (3E-T2, `src/page_ovl.asm` at `PAGE_ORG`;
**3E-T13: the real page, 1,357 B raw → 1,182 B `ovl_page_zx0`** (179 B left
in the window); `tests/page.py` P1 round-trips it, its variables
`pg_rc..pg_wid` excepted) and
**`items`** (3E-T6, `src/items_ovl.asm` at `ITEMS_ORG`, 1,027 B raw → 881 B
`ovl_items_zx0`, bank `BANK_OVL_ITEMS` = bank 1 since MEM-1 (was R6); run by `level_new`, see "3E contracts"). The
3E-T1 `ovl_test` (30 B) is dropped: `tests/ovl.py` O1 assembles the same
self-test overlay in Python and pokes it into the free R6 tail (`r6_end`, C = `BANK_R6`; R6), O2 into the free bank-1 tail (`bank1_end`).

**`ovl_run`** (`src/lowram.asm`, 30 B, bank-5 cold block): In HL = packed
stream (bank C's `$C000` window or bank 2 / 5 RAM), C = its bank, DE = load +
entry address, IX passes in. Pages C, `dzx0_standard` (~67 T per raw byte,
measured incl. ISR), **clears `GEN_ZBLK`**, re-pages the caller's bank, calls
the entry, re-pages the caller's bank again (the overlay may page anything:
it runs in bank 5). Out: the overlay's BC / DE / HL / IX; clobbers A, F.
**GEN_SCRATCH window** (`$6000..$65FF`, 1,536 B raw, aliases `ROOM_MAP` +
`NEXT_MAP` + the ZX0 frame cache): only while no room map is live — boot,
the menu, a level start before `level_show` / `build_room_map` (i.e. inside
`level_new`'s far3 or before it); **never** in play, during a room transition
or a generator session's frames (a gen_frame after the overlay is fine:
`GEN_ZBLK` = 0 forces its unpack). The overlay ASSERTs `end ≤ GEN_SCRATCH +
GEN_SCRATCH_LEN`; it keeps no state the caller needs after it returns.
`tests/ovl.py`: O1 a self-test overlay (3E-T2: assembled by the test; round trip == its raw bytes, entry with
the caller's bank 3 + IX, BC/DE/HL/IX out, caller's bank back after the
overlay paged bank 4, screen bit kept, stale `GEN_ZBLK` → 0, the whole 128K
unchanged outside the window / stub / stack, DI), O2 a full 1,536-B blob
(574 packed) with interrupts on from bank 0 (round trip, bank 0 back, nothing
but ISR-owned bytes changed; ~103k T).

**Page window (3E-T2, built; page-fullscreen rev 2026-10-20)**: the page
overlay runs in **`GEN_SCRATCH`** (`PAGE_ORG` `$6000..PAGE_LIMIT` `$65FF`,
**1,536 B raw**, ASSERTed), so the page itself may draw all 24 rows. While a
room is live that window aliases `ROOM_MAP`: `page_ovl` copies the room map
(`PLAY_CELLS` 576 B) to `PAGE_MAP_SAVE` = `GEN_SRC` `$6940` first and
`page_post` copies it back after the close (~25k T both; ASSERT
`PAGE_MAP_SAVE + PLAY_CELLS <= TX_DEC`: `mf_tx` decodes into `TX_DEC` on the
page). Audit of what else lives in `$6000..$65FF` across the modal page
(grep, 2026-10-20): `NEXT_MAP` — written only by `do_exit`'s room build and
read by the scroll (the transition is over before any INPUT tick); its tail
`LP_CMAP` `$6540..` — `lp_enter` scratch, rebuilt each room entry; `LG_*` —
`level_gen` scratch (level start only); the ZX0 frame cache — the generator
only (`GEN_TRAP` guards play; `ovl_run` clears `GEN_ZBLK`); `GEN_SRC` — the
pause save (not nested), `pblit` (`panel_init`, level start), `copy_virt`
staging (cold). None keeps state across the page. `tests/page.py` P1 checks
`ROOM_MAP`, `LVL_STATE`, `LP_STATE`, `ANIM_N` / `ANIM_N2` unchanged after a
close and `PAGE_MAP_SAVE` == the map while open. Order (`page_run`, low RAM):
`present_full` — screen 2 := the composed bank-5 screen, shown, and **that
copy is the backup** —, then `page_ovl` (bank 1: state, the map save,
`ovl_run`), which calls the overlay **with bank 1 paged** (it calls the
bank-1 menu helpers directly; it may page / far-call anything). **IX is
kept** across the whole page (`page_run` pushes it: its callers run on the
turn-intent path with IX = the hero); AF / BC / DE / HL are clobbered. The
overlay draws the page over the whole bank-5 screen and shows it
(`show_bank5`). Close: `set_screen` shows screen 2 at once (the close is
instant), then a 6,912-B LDIR copies screen 2 back over the bank-5 screen —
**byte-exact restore, no recompose** (room, bodies, panel, log, status marks
/ icons, FX numbers, cursor, ICON MODE info line; `tests/page.py` P4 x20).
**The page is not a pause** (user 2026-10-20): no `SND_HOLD`, the ISR and the
player run on through the open (present_full / unpack / draw) and the close;
P1 checks `SND_MODE` / `MUS_STATE` / `MUS_CUR` unchanged and `ay_vars`
advancing while open. Rules: nothing may present / render / run mark, drip or
decor ops while the page is up (the page loop is modal: `menu_frame` +
`sample_input` only); nothing may read `ROOM_MAP` (the overlay is there);
the overlay ASSERTs `end <= PAGE_LIMIT`. Measured (`tests/page.py` P1,
release build, page 362 B raw / 346 packed): open 252k T to the overlay entry
(present_full + map save + unpack) + 373k T draw (the full 6,912-B clear +
attr bands + ornaments + text + 24 boxes) = **625k T, 9 frames** to the
first page frame (the game screen stays on view meanwhile); close: the
copy-back 198k T, **223k T / 3 frames** to the next tick (the screen flips
back in the first). **3E-T13 (the real page, release, Warrior start bag):
360k T to the overlay entry (unpack of 1,357 B) + 478k T draw (+ 15 2x
icons, `item_name`, counters) = 838k T, 12 frames to the first page frame;
close unchanged (223k T, 3 frames).** Free page-time RAM besides the window (verify before
use): `GEN_SRC` + `PLAY_CELLS`.. `TX_DEC` `$6B80..$6D14` (405 B); 3E-T13
uses `$6B80..$6BA7` (**IC1: `PAGE_G60` deleted** — the page draws the R6
16×16 icons, no glyph copy; `PAGE_BUF` 40 B (`PAGE_BUF_LEN`, WEAR-UI: was 34; the longest gear line
"WARLORD CLEAVER WORN OUT 1D10-2 ATK+1" is 37 chars): a composed text line; `defs.asm`,
ASSERT `PAGE_SCR_END <= TX_DEC`), so `$6BA8..$6D14` (365 B) stay free.
**[RETIRED 3E-T12: `ovl_fx` / `ovl_fx_saved` / `fx_ovl.asm` / `FX_ORG` / `FX_MAP_SAVE` / `BANK_OVL_FX` are deleted; the ops are R6-resident `fx6.asm` (far6), page_post restores the map then far6 `fx_main`. History below.]** **Silent in-play overlay (3E-T8, built: `ovl_fx`):** the same window serves
cold in-play events that neither render nor read `ROOM_MAP` / `NEXT_MAP` /
`LP_CMAP`; no `present_full` (nothing on screen changes while it runs; log
lines are only QUEUED — `fx_line` → `log_push` writes the `LOG_TXT` ring +
`PD_LOG`, never the screen, so it is safe inside the overlay). `ovl_fx`
(low RAM, ~43 B; saves / restores only `FX_OVL_LEN` = 180 B of the map, ASSERTed `FX_ORG == ROOM_MAP`; `ovl_fx_saved` restores all `PLAY_CELLS` since the page overlay is larger): A = op (`FX_*`, `item_defs.asm`), B = arg, IX kept → `FX_OP`
/ `FX_ARG`, `ROOM_MAP` → `FX_MAP_SAVE` (= `PAGE_MAP_SAVE` = `GEN_SRC`), `ovl_run`
(`ovl_fx_zx0`, C = `BANK_OVL_FX` = R6, DE = `FX_ORG` = `GEN_SCRATCH`), map back;
out `FX_OP` = `FXR_*` flags (bit 0 `FXR_TURN`, bit 2 `FXR_TELE` reserved: the
copy-back clobbers BC / DE / HL, so the result is in memory). `ovl_fx_saved`
= the same entry after the save (page_post: the page's save is reused, one
save / restore pair per page close). **Contract:** GS_PLAYING only, never in
a room transition / scroll or the pause (`GEN_SRC` is the pause save),
nothing renders / presents / reads `ROOM_MAP` until it returns. The overlay
(`src/fx_ovl.asm`, 180 B raw, ORG `GEN_SCRATCH`, no LG_* use) pages R6 at
its entry and calls the R6 resident code directly (`bag_add` / `bag_take` /
`hero_recalc` / `fx_line`); dispatch table `fx_tab` over ops 1..7 (`FX_DRINK`
/ `EAT` / `READ` / `TELEPORT` reserved no-ops for T12, `FX_DISCARD` unused).
**Measured** (`tests/equip.py` F2, DI): EQUIP **52.3k T** (≈ 0.75 frame:
2 x 576-B LDIR + the 180-B unpack + swap + line + recalc), a no-op op 38.0k
T. From the page it runs inside `page_post` BEFORE `resync_tick` (part of the
page close, not a tick overrun). **T12 note:** a quick-slot use from a turn
tick adds ~40-55k T to that tick: resync or defer it (the `budget.py` gate
would see it). (The old bank-5 band window is retired:
it limited the page to rows 0..15.)

**Bag page (3E-T2 SPIKE: empty)**: `page_run` (low RAM, 43 B; test
probes `page_run.closed` / `page_run.post`, no code), reached ONLY on the
turn-intent path, INPUT phase: `I` sets `INTENT` = `IN_BAG` (`intent_tick`;
an ENTER in the same tick overrides it with `IN_FIRE`: one action),
`tpt_intent` runs `page_run` for it (CF = 0, no turn), and FIRE / ENTER on the
BAG icon reach it through `use_icon` -> `use_slot` (L = 0, no turn, no line,
ICON MODE stays). A held hero (`STS_HOLD`) has `INTENT` dropped by
`turn_input`, so the page never opens while held (both entries alike);
`page_ovl` / `page_post` (bank 1, 80 B): `PAGE_N` += 1, `PAGE_OPEN` = 1, the
room map saved / restored, then the input latches: `INTENT` / `DN_T` /
`DN_COMMIT` 0, `STICK_OLD` = `STICK`, `SC_OLD` = `PLAYER_SC`, `FIRE_ST` =
`FS_USED`, `EXIT_LOCK` = the held directions (a held direction waits for its
release), `resync_tick`. The overlay closes on a NEW press of FIRE, BREAK,
ENTER or `I` (keys held at the open are ignored); S, slot keys and the stick
do nothing. Placeholder layout (Q3 open; golden `page_empty`, renamed `page_start` by 3E-T13):
rows 0-1 title `BAG` (menu font, col 2) + `ITEMS 0/20` (row 1, right), row 2
the menu ornament (`menu_orn_b`, `MENU_A_SUB`), rows 4..14 the 5×4 grid of
16×16 boxes (cols 9..22, centred), rows 16..17 `WORN` + 4 boxes (cols
11..21), row 19 the description, row 20 the verbs (placeholder `USE EQUIP REMOVE DISCARD`, game.md §8.11), **row 22 the page's
message row**, row 23 the ornament; 6×8 text from raw ASCII in the overlay
(no text-block strings; `NO BAG YET` dropped from `strings.txt`, −7 B bank 0).

**Bag page (3E-T13 / T14, built: the real page, read-only + navigation + verb
choice).** Supersedes the placeholder close keys above: **BREAK / I close
(any mode); FIRE / ENTER select** (an item → the verb strip; on `[CLOSE]` →
close); S, slot keys do nothing. Layout = the approved placeholder, rows
(goldens `page_start` = Warrior start bag, `page_bag` = the P6 mix):

| Rows | Content |
|------|---------|
| 0–1 | `BAG` (menu font, cols 2–4); row 0 `ITEMS n/20` (x 48) + **`[CLOSE]`** (cols 26–31, selectable, bright cyan); row 1 `DAGGERS d  ARROWS a` (Warrior only, x 48) + `KEY` (col 26, when `LF_KEY_TAKEN`) |
| 2 / 23 | ornament (`menu_orn_b`) |
| 4–14 | bag 5×4: slot s icon 2×2 at row `4 + 3(s / 5)`, col `9 + 3(s % 5)` = **IC1: its 16×16 icon** (R6 `icon_slot`, `icons16`) in the floor ink (`item_ink`); QTY digit (≥ 2) at row +1, col +2; empty = a 16×16 frame (`$47`) |
| 15 | `W A H C` over the worn icons |
| 16–17 | `WORN` (x 48) + 4 icons at col `11 + 3k` (k = `WS_*`), empty = **IC1: the slot placeholder** (ink `$05`) |
| 18–19, cols 0–1 | **IC1: the description icon** (`PG_DICON_ROW`): the cursor item's icon, an empty worn slot's placeholder, blank on `[CLOSE]` / an empty bag slot |
| 19 | description: `item_name` (+ ` Xn` for stacks) + **3E-T8 the stat line** (far6 `it_fmt`, A = slot: ` FOOD+n` / ` HP+n` / ` MP+n`, gear ` ±m` (m != 0; ` WORN OUT` replaces it at m = -3, WEAR-UI) then ` 1Dn[+b] ATK±n DEF±n MP±n EVA±n`), `EMPTY`, blank on `[CLOSE]`; page overlay **IC1: 1,243 B raw (293 left)**, was 1,365 / 171 |
| 20 | verbs `USE`-word (col 2: `DRINK` / `EAT` / `READ` / `USE`), `EQUIP` (7), `REMOVE` (12), `DISCARD` (18), `CLOSE` (25): enabled `$45`, disabled `$01` |
| 22 | message row: help `FIRE: SELECT   I: CLOSE`; refusal `BAG FULL` (bank-1 `it_stems` + `S3_BAG_FULL`, 0 B new text) until the next press |

Cursor = attr only (`xor $08`: paper blue; every page attr has paper 0) over
the slot's 3×2 cells (icon + count column), `[CLOSE]`'s 6 cells, the chosen
verb's cells. Cursor rows 0 `[CLOSE]`, 1–4 bag rows, 5 worn; U / D step the
row and wrap (worn ↔ `[CLOSE]`), L / R wrap inside the row (widths 1 / 5 / 5 /
5 / 5 / 4); the column is remembered across rows (worn shows min(col, 3));
opens on slot 0. Verb strip: FIRE on an item → the first enabled verb; L / R
skip disabled verbs and wrap; U / D back to the grid; FIRE confirms. Enables:
potion DRINK, food EAT, scroll / book READ (+ DISCARD); gear in the bag EQUIP
+ DISCARD; bow DISCARD; worn REMOVE (refused on the page with 20 used slots:
`BAG FULL`); empty / `[CLOSE]`: CLOSE only. **3E-T8: `page_post` CONSUMES the verb** (both entries: `tpt_intent`
`IN_BAG` and `use_slot` `SA_BAG`, which now tails `jp page_run`): it reads
`PAGE_VERB` / `PAGE_SLOT`, zeroes `PAGE_VERB` at once (a stale verb never
replays; `PAGE_VLAST` `$BC5C` keeps it for the tests), puts `ROOM_MAP` back from
`PAGE_MAP_SAVE` (3E-T12: for every verb, first), DISCARD → `fx_line` "YOU DISCARD
<name>" + `bag_discard` (0 turns), every other verb → `FX_OP` / `FX_ARG` + far6
`fx_main` (3E-T12; DRINK / EAT / READ / EQUIP / REMOVE, 1 turn unless refused); out L = 1
when the turn is spent (`page_run`'s far1 passes it; `tpt_intent` `.bag` →
CF, ICON MODE exits as for a used icon). **Return protocol:** the overlay
writes `PAGE_VERB` (`$BC56`, `VB_*` `item_defs.asm`: `VB_NONE` 0 at every
open, `VB_DRINK` 1, `VB_EAT` 2, `VB_READ` 3, `VB_EQUIP` 4, `VB_REMOVE` 5,
`VB_DISCARD` 6) and `PAGE_SLOT` (`$BC57`: 0..19 bag, `PG_SLOT_WORN` 20 +
`WS_*`; record = `BAG + 3 * slot`) and changes no other state.
**`page_post`** (bank 1, +16 B) applies `VB_DISCARD` after the copy-back:
far6 `bag_discard` (R6, 20 B: the whole stack via `bag_take` (B =
`STACK_MAX`) → compacted + `pot_sync`; the bow clears `HAS_BOW`; no log line
yet — the `YOU DISCARD ` stem is in the T8 fx stems; 0 turns). **Stub for
T8 / T12:** DRINK / EAT / READ / EQUIP / REMOVE are left in `PAGE_VERB` /
`PAGE_SLOT` and ignored today (no turn); T8 / T12 read them in
`tpt_intent`'s `.bag` (and `use_slot`'s `SA_BAG`) path after `page_run`,
run the effect overlay and return CF = 1. Bytes: bank 7 0, low RAM 0, bank 1
+16, R6 code +20, R6 stream +854. Tests: `tests/page.py` P6 (cells / glyphs /
inks / QTY / frames, `pg_n`, verbs, golden `page_bag`), P7 (wrap rules), P8
(the enable matrix + USE word), P9 (EQUIP / REMOVE return values, `[CLOSE]`,
strip navigation, BREAK, CLOSE verb, DISCARD stack + bow, BAG FULL refusal).

### 3E-T1 byte ledger (measured, `tools/build.sh` DISPLAY, both `DEBUG_KIT` builds)

| Area | Before (main `9c99ad1`) | After 3E-T1 | Δ | What moved |
|------|------|------|---|-----------|
| bank 1 free (`UI1_LIMIT − ovl_blobs_end`) | 412 | **2,005** | +1,593 | −1,623 boot data (`font6x8` 768, hot image 503, `tiles_common` 288, `orn_glyphs` 64) → boot block; +30 `ovl_test_zx0` |
| bank 7 free (`B7_LIMIT − b7_end`) | 117 (kit 67) | **226 (kit 176)** | +109 | `init_tiles` 36 + `panel_boot` 73 → `boot6_tiles` |
| low RAM spare (`LOWRAM_SPARE`) | 118 | **376** | +258 | out: boot's state init, `isr_install` + `isr_image` (81), `keytab_defaults` (10), the 6 loader stanzas (110 → 72 B table loop incl. the 7th block); in: `ovl_run` 30, the two `farb` calls |
| bank 3 free to `AY_RESERVE` | 205 | 103 (DEC1 from main) | 0 | — |
| bank 2 image (to `FRT` + `kind_tab` pad) | 29 + 85 | 29 + 85 | 0 | — |
| pool slack (`POOL_CAP − POOL_NEED`) | 2,376 | 2,376 | 0 | the boot block lives in bank 6's tail only until the hero start |
| bank-6 tail (boot block) | — | 1,938 B at boot | — | code 249 + data 1,689; tape +1 block, net tape bytes ≈ 0 |
| cold paths (`tests/zx0_pool.py --baseline`) | boot → select 5,179,148 T | 5,108,240 T | −70.9k T | boot6_tiles reads in place (no copy_virt3 / GEN_SRC); hero starts unchanged (5,530,691 / 4,466,715 T); per tick 0 (`budget.py` gate passes) |

**What 3E-T2 could count on (superseded by the 3E-T2 ledger below):** bank 1 **2,005 B** for packed overlay streams
(or far1 code), bank 7 **176 B** (kit build; 226 release), low RAM **376 B**
(less `ovl_run7`, ~45 B), bank 3 205 B, bank 2 ~114 B; the GEN_SCRATCH window
(1,536 B raw, level start / menu) via `ovl_run` and the screen-2 window
(6,912 B raw + packed, while bank 5 is shown) via `ovl_run7` (T2). Further
runtime-only RAM (not tape-loadable; boot-block code could copy code there):
`$5CC0..$5DFF` (320 B, unused by code and tests per a 3E-T1 grep) and
`$5F8C..$5FFF` (116 B). Total ≈ 2.8K resident + the windows vs the ≈ 4.4K
stored need: overlays (ZX0 ~1.6-2×) must carry the bulk of 3E's code.

**T13 page rules (review of 3E-T2, binding; page-fullscreen rev):** (a)
**entry** — only through `INTENT` (`IN_BAG` / the BAG icon) on the
turn-intent path, never directly from `intent_tick` or in an ANIM tick; while
the hero is held the page does not open (no read-only mode in 3E; if one is
ever added, USE / EQUIP / READ / EAT / DROP must refuse while held). (b)
**restore model: apply after close** — the copy-back restores the screen
exactly as it was at the open, so it is valid only for a page that changes
nothing on the play screen: the page is read-only while up; a verb only
RECORDS its choice (item + verb, e.g. a page-result byte), the page closes,
and the effect runs after the copy-back as the turn's action (`tpt_intent`
returns CF = 1 after applying it: HP / MP / panel / icons / log / hero
sprite / quick slots change through the normal paths and are presented as
usual). No verb applies its effect while the page is up; no dirty-region
recompose is planned. (c) **screen and messages** — the page owns all 24
rows (panel, log and info line are hidden while it is up); refusals and
prompts go to the page's own message row (**row 22** in the placeholder
layout, rows 20..22 reserved for description / verbs / message), never
`msg_push` for an immediate line (a pushed line would show only after the
close). (d) **code size** — each page overlay ≤ **1,536 B raw**
(`GEN_SCRATCH`, ASSERTed), chainable (one overlay may `ovl_run` the next at
`PAGE_ORG` only as its tail); it must not read `ROOM_MAP`; music / SFX play
on (no `SND_HOLD`).

### 3E-T2 ledger and the 3E memory plan (measured, `tools/build.sh` DISPLAY)

| Area | After 3E-T1 | After 3E-T2 | Δ | What |
|------|------|------|---|------|
| bank 1 free (`UI1_LIMIT − ovl_blobs_end`) | 2,005 | **1,617** (after merging main 2026-10-20) | −388 | +346 `ovl_page_zx0` (fullscreen rev: was 273), +80 `page_ovl` / `page_post` (+ the map save), +1 `menu_orn_b`, −30 `ovl_test_zx0`, ±text |
| bank 7 free (release / kit) | 226 / 176 | **194 / 144** (after merging main: incl. main's own bank-7 growth) | −13 by the page | `use_slot`'s SA_BAG branch calls `page_run`; review: `tpt_intent`'s `IN_BAG` path (+10) |
| low RAM spare (`LOWRAM_SPARE`) | 376 | **324** (after merging main) | −43 by the page | `page_run` (incl. push / pop IX) |
| bank 2 (to `FRT` + `kind_tab` pad) | 29 + 85 | 18 + 98 (after merging 3E-T0) | 0 | `bag_msg` gone, `I` sets `INTENT` = `IN_BAG` (same size) |
| bank 0 text / pool slack | 2,680 / 2,376 | 2,673 / 2,383 | +7 | `NO BAG YET` dropped |
| bank 3 free to `AY_RESERVE` | 205 | 103 (DEC1) | 0 by the page | — |

Menu art ZX0 (lever (b)), measured with `tools/bin/zx0`: the menu-only part
(`menu_title` + lines + `menu_torch*`, 385 B) packs to 284 B (net ≈ +90 B
after the unpack call; it could live in `GEN_SCRATCH` for the whole menu:
the previews blit the boot pool and never touch it); the menu font + map
(720 B → 423 B) is drawn in play too (pause box, DEPTH / end cards) and has
no 720-B play-time home — **not done in T2** (lever (b) is worth ≈ 90 B, not
the estimated 0.5K; worth doing only if 3E ends < 100 B short; needs
`tests/gfx_integrity.py`'s menu-art check pointed at the unpacked copy).

**What 3E can count on** (kit build, the binding one): **stored** — bank 1
**1,617 B** (packed overlay streams or far1 code), bank 7 **144 B** (194
release), low RAM **324 B**, bank 3 **103 B** (after DEC1), bank 2 **18 B**:
≈ **2.21K** stored (measured after merging main 2026-10-20). **Raw
windows** — `GEN_SCRATCH` **1,536 B** per overlay: the page (map saved), a
silent in-play event overlay (~1 frame a use), a level start / the menu
(`ovl_run`); + 405 B page-time scratch (`$6B80..$6D14`). **Runtime RAM** (state only, not tape-loaded):
`$5CC0..$5DFF` 320 B + `$5F8C..$5FFF` 116 B (fits T3's ≈ 130-B item block).
**Still to win:** (lever (c) DONE: `AY_RESERVE` `$EFA0`, bank 3 616 B free), (e) the
`level_gen` overlay +0.5K (bank 3), (g) font trim +0.2–0.3K, (b) +0.09K →
≈ +1.2K → ≈ 3.7K stored vs the ≈ 4.4K stored need (≈ 3.7K with (f) the
scaled floor-glyph icons, ruled 2026-10-19). **Must be overlays:** the page
(T13 input / T14 drawing / T15 READ + the verbs' effects, ≤ 1,536 B raw each,
chainable), the level-start item / trap / BUC / ID-shuffle generator (T6,
`GEN_SCRATCH`), and — via the silent in-play overlay — the cold effects shared by
quick slots and page verbs (quaff / read / eat / teleport / `hero_recalc` /
reveal / shatter / bless). Resident only: the hot / per-turn hooks (hunger
tick, `floor_pickup` → `bag_add`, quick-slot auto-fill, the trap step check)
within ≈ 0.7K (bank 7 + low RAM + bank 3 + bank 2), item strings preferably
inside the overlays (page-only text) or ZX0-packed in bank 1, not in bank 0.

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
H, offsets; MEM-FT: the FRT row tail) and its `fdesc_tab` entry (bank 5: `FD_BLK`, `FD_FRM`,
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
`GEN_SRC` stays as the `vdata` staging buffer (`pblit`; 3E-T1: `panel_boot` is gone). Decompressor =
`src/dzx0_standard.asm` (vendored, pinned commit, unmodified, 68 B);
`zx0_frame` + `dzx0` = 115 B (SRC6 spike +8: the SRC6 virtual range; A5: 121; `zx0_code..zx0_code_end`, ASSERT ≤
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
| `present` (gfx.asm) | `tick_work`, before render (probe `probe_presented` after it) | flushes `HUD4_PW` (B3B-11: text rows 20..23) into the mask, copies every marked cell from `PRES_RMIN` down, clears the mask; ~50 T when idle 3F-B2: ~242 T per copied cell (was ~262), 24 T per clear bit (was 31), screen highs patched once per screen third (SMC `.thd`), `HUD4_PW` all zero skipped in ~40 T; A7b: a full mask byte (8 cells, HUD text) goes by LDI lines (`.full8`, ~1.5k vs ~2.1k T) except cols 24-31 of a third's last char row (low byte `$F8`: LDI would carry into H) |
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
| ISR `isr` | `ISR_ADDR` `$BCBC..$BCF3` (56 B) | bank 2 like the table (the ISR must be mapped whatever bank sits at `$C000`); assembled in the low-RAM cold block (`isr_image`, `DISP ISR_ADDR`; **3E-T1: in the bank-6 boot block**, `boot6_init` installs it) and copied at boot, so it costs no bank-2 **image** bytes (the image headroom is for Stage-3 hot code) |
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

**Cost (SND-2 T2, measured, ZEsarUX: T from the ISR's `call AY_PLAY` to
its return, incl. CALL/RET; bank 3 runs in the top border, uncontended).**
The ISR's own overhead is unchanged: **334 T** (315 T own instructions + 19 T
acknowledge; A8). `ay_play` per case:

| Case | T | Note |
|------|---|------|
| idle (music on, `MUS_REQ` 0) | **243** | the menu / play today until T3 sets `MUS_REQ` (stub was 286) |
| music off, steady | **210** | falling edge once: 643 (`player_stop` + silence) |
| hold (`SND_HOLD`) | **291** | silence R8-R10 every held frame, sequencer frozen |
| start frame (loop or shot) | **3.3-3.5k** | `player_start` alone ~3.1k (header said ~1.9k: 3 voices × ~0.7k + `pl_out_all` 0.73k); no `player_frame` in that call |
| play frame (loop) | `player_frame` + ~0.25k: median **2,208**, max **5,147** (Lament, 600 frames) | |
| play frame (shot) | + `player_done` ~0.08k: max **5,194** | the shot's last frame restarts the loop (a start frame) |

**SND-5 (sound effects, `tests/sfx.py` SFX10 / `tests/sound.py` SND6 / SND9, whole ISR):**
the fast path (no `SFX_REQ`, no effect) adds ~40 T to every frame; the `WZM_SFX` hooks
in `player_frame` ~0.1k T a played frame. Music only: worst single **5,381 T** (song 2
frame 251; was 5,243), adjacent pair **8,749 T** (was 8,566), music off **465 T** (gate
≤ 500). With effects: every effect over the Lament, and the worst SFX path (a priority-7
effect taken every frame: take + pitch + noise byte + R6 OUT + ducking) over 300 frames
of the Lament / Dangerous: worst **6,243 T** (contract ≤ 6.5k; 27 effects, ducking on every effect frame). An effect frame costs
~0.4-0.9k T on top of the music (`sfx_step` ~0.35k, + noise ~75, `sfx_dk` ~0.13k (every effect),
`sfx_out` ~60 T after a played frame, ~0.25k when it OUTs itself).

So a frame costs ≤ ~0.6k T idle and ≤ **~5.5k T** with music (334 + 5,194),
inside the ~6.5k T contract; a 2-frame tick holds two ISRs. **SND-2 T4/T6
(`tests/sound.py` SND9, whole ISR `isr` → `isr.done`):** worst single
**5,243 T** (song 2 frame 251), worst adjacent pair **8,566 T** (start + first
play frame); start frame ≈ 3.4k T (`player_start` ~3.1k; accepted ≈ 3.5k by the
manager); music off 426 T whole ISR. **Tick caps unchanged as WORK caps**
(ordinary 126k, cast 128k: tick time minus the ISR time inside the window) plus
the SND-2 T5 **real** gate `total + PRE_MAX ≤ 141,816` (PRE_MAX = 402 + worst
ISR, floor 5,300). Since T3 the Lament plays in game, so every `tests/budget.py`
scenario runs with music: worst ordinary work **121,380 T** (mage + 4), cast
work **119,055 T** (wcast4), real **130,754 T** (wcast4), 0 over; per-scenario
table: budget.md §5.1. Stack: the ISR's 12 B + **8 B** for `AY_PLAY` (SND-5: CALL 2
+ `ay_play`'s `call ay_music` / `sfx_step` 2 + the player's deepest 4: `pl_voice` →
`pl_fetch`, `sfx_dk` → `.duck`, or `player_start`'s two pushes; SND-2: 6 B); the stub used 2.

History (A8, the silent stub): acknowledge + HALT exit 19 T, entry →
`AY_PLAY` 198 T, stub 286 T, restoring `OUT` 35 T, pops + `EI`/`RET` 82 T:
620 T per frame. The ROM IM1 handler it replaced cost ~990 T.

### Cold code placement (A3) and far calls

Hot (per-tick) code stays in bank 2 (uncontended). Cold code lives in
contended places, chosen by whether it pages `$C000` (D3-S2: + bank 7, the
per-turn / per-event logic that needs bank 2's helpers but no other `$C000`
bank):

| Where | Why | What |
|-------|-----|------|
| bank 5 low RAM `lowram_code..$7FFF` (`src/lowram.asm`) | always mapped: may page any bank through `$C000` | `start` (3E-T1: `tape_tab`-driven), `boot`, `check_paging`, (A8) `isr_install` + `isr_image` (3E-T1: both moved to the boot block, `boot6_init`), `start_game`, (3E-T1) `ovl_run`, `init_kbd_mirror`, `sel_tab`, the generator (`pool_banks`, `alloc*`, `build_bitrev`, `copy_virt`, `gen_kind/frame/facing/variant`, `mirror_src`, `mul8`, `frt_ptr`, `sel_frt_copy`), (A7) `set_screen` / `show_bank5` / `present_full` / `hud_clear_mark` / `vis_reset` / `vis_room_sync`, (B3B-8) the room-entry ends of the bank-3 builder: `build_room` (far entry, A = room / H = map page), `room_show` (build + `draw_room` + ornament on screen and shadow), `room_shadow` (do_exit), `orn_row` / `orn_cells` (row-17 ornament; pages nothing, so the bank-3 scrolls call it), `level_load_tiles` + `theme_ids` + `chest_glyphs` (pages bank 7), the B3B-5 doors / falls / jump, and (A6) the frame descriptors `fdesc_tab` as the block's tail. B3B-8 moved `build_room_map` (v1, 254 B) and `init_tiles` + its stand-in glyphs / `tile_attr_src` / `tile_src_tab` / `bg_tiles` out (to bank 3, rewritten) |
| bank 3 after the source tail, `bank3_code..bank3_end` (`src/bank3.asm`) | needs no other `$C000` bank while running | (C3-6: the hero select `sel_run` became the bank-1 menu, the transition scrolls and the DEPTH card moved to bank 1 — `menu1.asm` / `scroll1.asm`); (A7 review) `init_ent_common` + `spawn_tab` + (MEM-SND) `new_game_proto` (far3 from bank-7 `new_game`; `new_game` itself, `init_tiles`, `panel_boot` and `panel_init7` are bank 7 since MEM-SND, `src/boot7.asm`), `follow_admit` + `dest_counts` (far3 from bank-7 `follow_select` (PROTO), direct from `lp_transition`; L-RELIEF: `follow_select`, `place_follower`, `arrival_conflicts` → bank 7) — bank-2 queries + `vis_reset` only; (B3B-7) `level_gen` / `level_start_x`; (B3B-8) `build_room_map` v2 (far3 via lowram `build_room`; bank-2 helpers `room_desc` / `seg_storey` / `map_cell` / `storey_row` only), `decor_room` (B3B-9 decor deriver, `src/decor_gen.asm`; contract under "As built in B3B-9 / B3B-10"), `proto_level` + `proto_hdr` / `proto_floor` / `proto_rooms` / `proto_decor` (rooms A–D as a level state, from `new_game`), `init_tiles` (boot, far3; B3B-11b: its cold data `tiles_common` (ids 0..31), `orn_glyphs` and the PROTO zap glyphs (`MODULE b3fx`) now sit in bank-1 `vdata` and are read through `copy_virt3`), (B3B-11) `panel_boot` / `panel_init` / `panel_flush` / `pblit` (sources from `vdata` via `copy_virt3` → `GEN_SRC`); the scrolls call `orn_cells` for the entering row-17 cells; (B3B-R2, `src/turn3.asm`, once-per-turn / per-event logic, ZX0 build only — the raw A/B build assembles it into bank 2) `resolve_monsters` (far3 from `read_turn_input`: ONE bank switch per turn) (+ bank-2 `cache_player`), `ai_monster`, `nearest_ladder`, `dx_to_player`, `attack_if_reach`, `ai_flyer`, `clamp_band`, `materialise`; `do_attack` + `set_reaction_at` (far3 from `try_horizontal`, direct from `attack_if_reach`; D3-6a: `do_attack` runs on `hit_roll` / `deal_hit`, `src/combat3.asm`, see "3D contracts"); (D3-6b) `proj_fire` (`src/proj3.asm`; called from bank-3 cast code, D3-7); (`show_impact_msg` + `kind_name` / `str_cat`: B3B-13 → low RAM, called directly from `anim_tick`); (`potion_pickup` and `try_quaff`: D3-7 T5 → bank 7, for bank-3 room); (D3-7) `abil_load` (`src/rank3.asm`, far3 from `intent7` `ic_disp`: A = `ABL_*` → `ABIL_DESC` = the `ab_def` row + the rank / ammo row, L = `ABF_*` flags, B = `ABL_*`); (D3-7 T4) `proj_rel` (`rank3.asm`, far3 from bank-7 `spell_fire`: A = `ABL_*`, DE = rank row → `proj_fire` HL = DE, E = 0); (D3-7 T5) `melee_hit` (`rank3.asm`, far3 from bank-7 `melee_strike`: one Power Strike / Whirlwind blow, A = target slot, `ABIL_DESC` loaded → L = HP lost, H = 1 hit; `hit_roll` + `deal_hit`); (B3B-13: every message string is a TX_* token stream in the bank-1 text block; `potion_pickup` / `panel_init` call lowram `msg_push`, which re-pages the caller's bank). The bank-2 helpers they call (`try_step` / `try_step_face` / `cork_check` / `flyer_lcost` / `box_free` / `box_vs_ix` / `find_target` / `cache_player` stay: `try_step` and `cache_player` are also called by a `tests/world.py` unit stub with any bank paged) page nothing, except `try_step` → `mon_door` → `door_open` → `door_paint` → `shadow_rect`: `door_paint` (lowram) now saves `PORT_7FFD_SHADOW` and `restore_page`s after it (+8 B) |
| **bank 7** `b7_code..b7_end` (`$E000..`, `src/bank7.asm`; D3-S2) | per-turn / per-event, needs no other `$C000` bank while running; may call helpers that leave bank 7 paged (`erase_rect`, `shadow_rect`, `room_shadow`, `present_full`, `level_enter`) | entered only via **`far7`** (`ld c, BANK_COLD7` → `farb`): (MEM-SND, `src/boot7.asm`) `init_tiles` / `panel_boot` (far7 from `boot`; **3E-T1: moved to the boot block, `boot6_tiles`**), `new_game` (far7 from `start_game`), `panel_init7` (far7 from bank-3 `panel_init`, L = the potion slot); `turn_input` (from bank-2 `read_turn_input`, the budget probe stays there) → `try_player_turn` / `tpt_intent` / `try_climb` / `try_horizontal` / `exit_h` / `ladder_exists` / `find_target` (D3-7 T0: `find_target_far` gone — its only caller `ic_melee` is bank 7 now); `end_turn` (play_loop: `turn_done` CF → far7) + `do_exit` + `hide_sprites`; **L-RELIEF** (from bank 3, room exit = cold): `follow_select` (plain call from `do_exit`; PROTO tail `jp far3` → `follow_admit`), `place_follower` (far7 from bank-3 `follow_admit`, IX in), `arrival_conflicts` (plain call from `do_exit`, far7 from lowram `hero_fall`); `pause_run7` (bank-2 `pause_hook` stub); `intent_icon7` (intent_tick's ICON MODE branch; D, E pass in). **D3-7 T0:** the C3-2 icon logic `src/intent7.asm` (was bank-3 `intent3.asm`): `use_icon` (plain call from `tpt_intent`; the SA_* dispatch is a cp chain — no data in bank 7), `cursor_step` (plain call from `intent_icon7`), `sel_key` (far7 from bank-2 `intent_tick`), `hero_st_init` (far7 from bank-3 `new_game`); bank-3 targets by far3: `do_attack`, `abil_load` (`try_quaff`: D3-7 T5 → `ic_quaff`, this bank); the ability entries `abil_spell` / `abil_melee` / `abil_ammo` (`abil_spell7.asm` / `abil_melee7.asm` / `abil_ammo7.asm`, chosen by `ABIL_DESC`'s `ABF_MELEE` / `ABF_AMMO` / else; In IX = hero, B = `ABL_*`; Out L = 1 turn / 0), `melee_bonk` (the staff-bonk slot after `ic_melee`'s blow), `ammo_pickup` (`pickup7.asm`, from `end_turn` after `potion_pickup`; **T6: both replaced by `floor_pickup`**) — T0 stubs (L = 0 / `ret`), T1 implements them. **D3-7 T1:** `src/act7.asm` — `act_begin` (plain call from the ability accept), `act_pend` (far7 from bank-2 `pend_far`, the `anim_gate` hook: the release + the deferred monster phase, far3 `resolve_monsters`), `act_fire` → `spell_fire` / `power_fire` / `ammo_fire` (stubs, L = 1, in the `abil_*7.asm` files); contract under "Projectiles". **D3-7 T4:** `abil_spell` / `spell_fire` (+ `spell_row`) and `melee_bonk` implemented (bank-3 shim `proj_rel`, `rank3.asm`); contract under "Projectiles". **D3-7 T5:** `abil_melee` / `melee_scan` / `mask_hostile` / `power_fire` / `melee_strike` / `imp_fx` / `front_cell` (`abil_melee7.asm`; bank-3 shim `melee_hit`), `act_begin_ok` / `act_seq` (`act7.asm`); moved in from bank 3: `potion_pickup` (`pickup7.asm`, plain call from `end_turn`; its tail `jp shadow_rect` leaves bank 7 paged: allowed; T6: now `floor_pickup` → `ap_stamp`'s tail, the same rule), `try_quaff` (= `intent7.asm` `ic_quaff`, `ic_potion`'s tail), `debug_kit` (`intent7.asm`, `hero_st_init`'s tail; far3 `rank_sync`). Moved 2026-10-12 from bank 2 (`main.asm`, `logic.asm`, `anim.asm`, `io.asm`); `clear_screen` / `print_char` / `print_str` went to bank-5 low RAM |

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

3F-B4: `materialise` gated on `PEND_N` (`ret z`; exact because every PENDING setter in CUR_ROOM
rebuilds with `build_live` and the turn starts with one): probe 3.37k -> 0.45k T on the
pmix / mage / umix worst ticks, +5 B bank 3.

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
| `$8000..$A4DB` (+ `seq_bytes` to `$A5DB`) | `image_start`…`code_end` | **3F-T2 (MEM-3F): `$8000..$A4DB`, 9,435 B; then `seq_bytes` 256 B (runtime only, not on tape: the sequence cache's bytes, "Sequence cache (3F-T2)"); free to `FRT` (`$A800`) 549 B + 126 B `kind_tab` ALIGN pad = **675 B** (was 13 + 36 = 49): `FRT_MAX` 160 → 128 +512, the kind sequences / `kind_seqs` / `kind_rest` out (−455) for the cache (`seq_rows` 119 B in the pad + `seq_bytes` 256) +80, `kind_tab` −24 (`KT_FID0` / `KT_FCNT` → R6 `gu_tab`, `KT_MOD9` / `KT_DIV9` moved up, `KT_END` `$1D0` → `$1B8`), `kind_seq_ptr` / anim callers −8. `kind_tab` stays `$A100`.** Before: HOT code + static tables (3E-T0: `$A5E3` -> `$A5EE`, 9,710 B; free to `FRT` 29 -> 18 B, the `kind_tab` ALIGN pad unchanged 85 B: `sfx_msg` +11 B after `kind_tab`; SND-4a: low-RAM cold block spare 131 → 118 B (−13 in `level_descend` / `level_enter`; `stinger_wait` in bank 1, 412 B free); **SND-5b: `$8000..$A5E3`, 9,699 B incl. the pad; 29 B to `FRT` + 85 B `kind_tab` ALIGN pad (was 136: `mv_sfx` 48 B + its `call` 3 B in `logic.asm`)** (`bars_draw` 96 + `num2` 35 moved from the end of `panel2.asm` to `src/bars2.asm` after `kind_tab`: 131 B more pad for new hooks BEFORE `kind_tab`, the total bank-2 free (165 B) unchanged; `kind_tab` stays `$A100`); SND-1: `$8000..$A560`, 9,568 B; 160 B to `FRT` + 5 B `kind_tab` ALIGN pad** (+8 before `kind_tab`: `sample_input` `call snd_scan`, `intent_tick` `bit SC_SOUND, e` / `call nz, snd_hot`; +17 after: `snd_scan` / `snd_hot` in `sfx2.asm`; 5 B of pad left: the next bank-2 byte before `kind_tab` beyond that moves it a page); SND-5: `$8000..$A54E`, 9,550 B; 178 B to `FRT` + 13 B `kind_tab` ALIGN pad — 14 more bank-2 bytes BEFORE `kind_tab` move it a page (+256): +24 before it (`fx.asm` `call fx_imp_sfx` + the bounce request, its two `jr` → `jp`; `anim.asm` the two LAND requests), +87 after (`src/sfx2.asm` `sfx_req` (+ the `SFX_NEXT` loser rule) / `sfx_msg` (12-entry table) / `sfx_abl` (9-entry table) / `fx_imp_sfx`); D3-9b: `$8000..$A4D4`, 9,428 B; 300 B to `FRT` + 41 B pad; `kind_tab` stays `$A100`** (+17 B before `kind_tab`: `icon_poll`'s MP poll 13, `panel_more`'s PD_MP test; +39 B after `mark.asm`: `src/xp2.asm` — `xpn_tab` (XP_NEXT, 16 B, **the single table**, read by bank-7 `xp_turn` and bank-1 `item_info`) + `item_mp` (MP bar + number); **the heroes' `KT_ATK` / `KT_EVA` columns (ids 0 / 1) are runtime state**: `xp_turn` adds the §4.1 L4 / L8 atk and L6 eva steps there (0 T per to-hit roll), `hero_st_init` writes back `KN_ATK` / `WZ_ATK` / `KN_EVA` / `WZ_EVA` (main.asm) on a new game). **D3-8d: `$8000..$A49C`, 9,372 B; 356 B to `FRT` + 165 B pad; `kind_tab` stays `$A100`** (+460 B: `src/mark.asm` after the kind arrays (`kind_tab + KT_END` = `$A2D0`: `mark_tick`, `mk_slot` (+ the review fixes: damage test past the op cap, the `MK_WAIT` retry gate), `mk_rec` / `mk_cb(de)` / `mk_bit`, 4 B scratch); +31 B before `kind_tab` (pad 196 → 165): `cell_occ`'s mark-map test 14, `idle_phase`'s HOLD test 12, the `decor_gate` call 3). **D3-8b: `$8000..$A2CF`, 8,912 B; 816 B to `FRT` + 196 B pad; `kind_tab` `$A000` → `$A100`** (+206 B over D3-8f: `src/drip.asm` 201 — `drip_tick` (TP_FIRE exit, cover test, gates, the fall step with its row-17 guard), `drip_erase`, `drip_draw`, the 3 glyphs 22 B — `cell_occ` (decor_tick's inline occupancy loop made a shared routine, +3 net), `decor_gate` +2. Pad history: the D3-8f build reported 146 B of pad before `kind_tab` (the D3-8 figure below, 167 B, was not re-measured after D3-8c..f); the code grew past it, so `kind_tab` moved a page). **D3-8: `$8000..$A1CF`, 8,656 B; 1,072 B to `FRT` + 167 B pad; `kind_tab` `$9F00` → `$A000`** (+~140 B: the render tint, `st_tint`, `st_sig`). **D3-S2: `$8000..$A0CF`, 8,400 B; headroom 1,328 B to `FRT` + 249 B pad = 1,577 B** (was 48 + 196): −1,280 B to bank 7 (`bank7.asm`: the player turn, `end_turn` / `do_exit` / `hide_sprites`, `pause_hook`'s body, intent_tick's ICON MODE branch), −96 B to low RAM (`clear_screen`, `print_char`, `print_str`), +~25 B stubs / `far7`, Part 1 (no bitmap shadow) +11 B; `kind_tab` `$A400` → `$9F00`) (8,912 B incl. the pad, C3-3; 8,656 B, C3-2; 8,144 B, C3-1; 7,888 B, B3B-13; B3B-R2 8,144 B; B3B-10 9,680 B; incl. the ALIGN pad + the 16-B `dt_attr_tab` and the 64-B `tile_flags` before `kind_tab`; `ASSERT code_end <= FRT`). **Headroom (D3-5, build DISPLAY): 48 B to `FRT` + 174 B pad** (D3-5 +899 B: `fx.asm`, `kind_tab` `$A000` → `$A400`; "3D contracts"). Before: **(D3-0): 1,072 B to `FRT` + 108 B pad** (D3-0 −256 B code: the zap (`draw_zap` / `zap_covered` / `draw_glyph` / `dt_zap` / the anim + hide paths, ~250 B) out, `kind_tab` `$A100` → `$A000`). Before: **(C3-2b; + main's B12 merge, see the build DISPLAY): 816 B to `FRT` + 166 B pad = 982 B** (C3-2b: the ICON MODE `intent_tick` / `tpt_intent` +~250 B, paid by moving the icon state / drawing — `slot_act_tab` … `icon_state`, `slot_want`, `item_icons`, `sel_paint`, `lvl_draw`, `pot_slot` — to bank 3 (`icons3.asm`, entered by `item_icons_far` → far3); C3-3 +362 B: `icons.asm` — `slot_act_tab` / `slot_act` / `abil_rank` moved from bank 3, `icon_state`, `icon_poll` + `icon_sig`, `item_icons`, `sel_paint`, `lvl_draw`, `panel_more`, `print6x`; old `item_icons` / `pot_col` out; `kind_tab` → `$A100`. C3-2 + B11/B14 merge: 1,297 B (B11 +11 B; C3-2 alone: 1,308 B) (C3-2 +391 B: `intent_tick` + `fire_used` / `bag_msg` / `pause_hook` ~190, `tpt_intent` ~110, the `legacy_input` gates in `input_tick` / `sample_input` / `read_turn_input` / `try_player_turn` ~40, `SC_ENTER` ~6; `kind_tab` moved `$9E00` → `$A000`. C3-1: 1,699 B (C3-1 +154 B: `input_tick`, `read_stick` / `stick_tab` + the Sinclair presets (20 B), `sample_input` on `STICK` + `PLAYER_SC`; `kind_tab` moved `$9D00` → `$9E00`. C3-0: 1,853 B (C3-0 +5 B: `farb` / `far1` / `far3`, `kind_tab` stays at `$9D00`; B3B-13: 1,840 + 24 = 1,864 B; B3B-13 −151 B net: the strings `str_found/quaff/died/win/welcome` + `kind_names` / names ~160, the PROTO chest win in `end_turn` ~35 out; `tk_get` 44 + `print6t` 21 in, `item_log` → `print6t`; `kind_tab` moved down to `$9D00`, read from the `.sym`. Before: B3B-12: 1,584 B to `FRT` + 129 B pad = 1,713 B; B3B-12 +32 B: `try_climb` `EX_LEVEL` (only at `RD_EXITCOL` with `LF_GRATE_OPEN`), the `do_exit` → `level_descend` dispatch, the PROTO win gated on `LVL_DEPTH` 0; B3B-R2: 1,745 B) for code/static tables (B3B-R2 −1,538 B net: `src/turn3.asm` (monster phase, attacks, potions, impact messages; 1,558 B) out to bank 3, + the far3 call sites (5 sites, +20 B); `kind_tab` moved to `$9E00`. (The raw A/B build that kept turn3 in bank 2 was retired in B3B-12, manager decision.) Before: B3B-10: 48 B to `FRT` + 159 B pad = 207 B (B3B-10 +355 B: `decor.asm` 352 (`decor_tick` with the step inlined, `dt_zap`) + the `play_loop` call, `dt_attr_tab` 16 in the pad; `kind_tab` moved one page up to `$A400`. Before: B3B-11b: 560 B to `FRT` + 18 B pad = 578 B (B3B-11b +74 B: `item_icons` + `pot_col` moved here from `HOT_COPY` ~65, `print6g` / `p6_inline` (the print6 getter interface) ~55, `item_log` one item, no chunk state −~45; B3B-11: 652 B; B3B-11 +82 B net: `panel2.asm` 435 (`item_log` 121, `log_scroll` 183, `bars_draw` 96, `num2` 35), `str_cat` / `show_impact_msg` composer, the `panel_tick` call; out: the A7 HUD (`hud_status` / `hud_room` / `msg_begin`, `clear_row` 155, `hud_track`, `print_char_hud`, `print_dec`, 3 strings) ~350; the rest of the panel's hot code sits in `HOT_COPY`. Before: B3B-8: 560 B to `FRT` + 174 B pad = 734 B; B3B-8 −69 B net: the PROTO `room_tab` + 4 room descriptors (~105 B, now bank-3 `proto_rooms`) and the old `room_desc` / `exit_h` / list loops out; `seg_storey` 13, `room_side` 36, `try_climb` `.vexit` 20, `potion_pickup` on `FLOOR_LIST`, the `hud_room` letter 7 in. Before: B3B-5 + review + B10: 560 + 105 = 665 B; B3B-5 used 402 B of the 1,067 (B10 hardening: flyer box row clamp 6): `tile_flags` 64, `cell_addr` / `cell_blocked` / `lead_cell` / `desc_byte` 57, `box_solid` (flyer steps, jump swept box) 34, `LOCK_SHOWN` clear 3, terrain + pit + door hooks in `try_horizontal` / `try_step` ~85, jump chord + key C in `try_player_turn` / `sample_input` ~30, `M_FALL` / `M_JUMP` anim 83 + `jump_dy` 12, room descriptors +16; the rest of B3B-5 is bank-5 low RAM. Before: A7b rebased on the B8 rev 816 B to `FRT` + 251 B pad = 1,067 B; A7 review: 993 B; A7b: code −78 B net — the one-pass record render (−138 B) and the blit rewrite (−46 B) pay for the erase row stepping (+26), `stamp_rect` / the 16-bit blit entry patch (+19) and the present `.full8` path (+61); A6: 677 B; A7: 111 B after present / pmark / HUD tracking / in-place rect dedupe / paging +566 B; the review moved 1,062 B of cold code out — `build_room_map` 254 B to bank-5 low RAM, `new_game` + `init_ent_common` + `spawn_tab` and follower selection + arrival conflicts 794 B to bank 3, net of the `far3` call sites — and added the B8 flyer ladder-end rule +159 B and the bank-2 `map_cell` +21 B; the 2026-10-02 cross-or-leave flyer rule + blocked-climb wait: +4 B net), plus the 1,536 B free runtime RAM `$B200..$B7FF` below. Code bytes `$8000..kind_tab_pad` 7,439 (B3B-R2; B3B-10 8,977; B3B-11b 8,622; B3B-11 8,548; B3B-8 8,466; A7 review 8,271; A7 9,153; A6 8,587). **IC1: `$8000..$A5F3`, free to `FRT` 13 B (−5: `item_mp` sets `QS_RECHK`) + 46 B `kind_tab` ALIGN pad (was 57: `icon_poll`'s pending-pass check +10, `item_icons_far` +1).** `kind_tab` page-aligned at `$A100` (D3-8b; `$A000` D3-8; D3-S2 `$9F00`; `$A400` D3-5; D3-0 `$A000`; `$A100` C3-3; C3-2 `$A000`; C3-1 `$9E00`; B3B-13 `$9D00`; B3B-R2 `$9E00`; B3B-10 `$A400`, before `$A200`; moves with the code: tests read it from the `.sym`), **2 pages** (`KT_SIZE` `$200`): **3F-T2: 12 parallel 32-B kind arrays** (`KT_BW` .. `KT_ATTR`, then **`KT_SEQ` `$160`** — runtime, the low byte of the kind's `seq_rows` row, written per level by R6 `sq_fill`; `KT_FID0` / `KT_FCNT` are gone to R6 `gu_tab`) + `KT_MOD9` `$180` (24 B, 8 spare) / `KT_DIV9` `$1A0`, **`KT_END` `$1B8`**. Before 3F-T2: 13 parallel **32-B** kind arrays (`K_MAX` 32; ids 0..8 used, 2 = Rogue hole; **D3-4: ids 30 / 31 = the class FX kinds `K_FXW` / `K_FXM`, only their `KT_FID0` / `KT_FCNT` columns are set** — 3F's monster rows have ids 9..29) + `KT_MOD9`/`KT_DIV9` tables (n mod/div `STOREY_ROWS`, n = 0..23; B3B-3, were MOD7/DIV7 at the same offsets), `KT_END` `$1D0` (the old "48 B spare in its page (resistances, 3F)": the resistances are bank-3 `kx_tab` since D3-0; **D3-8d: `src/mark.asm` is assembled from `kind_tab + KT_END` on**, i.e. right after the arrays, so `code_end` = the end of `mark.asm`). No array crosses a page: `KFIELD` folds the page into `H`. `frame_tab` **4 B/fid** (`FT_COLS`, `FT_H`, `FT_OFFR`, `FT_OFFL`: only what the renderer reads; D3-4: 101 fids = 404 B). `far1` / `far3` / `farb` / `restore_page` / `blit_keep` / `enter_select`: the far-call trampolines (53 B, C3-0). |
| `$A689..$A6FF` (MEM-FT) | `seq_rows` | **MEM-FT: the sequence cache rows (119 B, runtime) moved from `FRT_GAP` to directly below `FRT` (`seq_rows` = `FRT` − `SQ_ROWS_LEN`, one page, ASSERTed above `seq_bytes_end`).** |
| **`$A700..$AFFF`** (MEM-FT; `$A700..$AF3F` 3F-T13bc; `$A800..$AFFF` 3F-T2; was `$A600`) | `FRT` | **MEM-FT: `FRT_MAX` 144 (129 used, 15 spare; the most the `$A700` page holds, `FRT_GAP` 0). Row = 4 variants × bank,lo,hi (bytes 0..11) + the fid's static **`frame_tab`** entry (bytes 12..15 = `FT_IN_ROW`; `frame_tab` = `FRT` + 12, `FT_STRIDE` = 16): unpacked at boot by `boot6_ft` from bank-2 `ftz_zx0`; `frt_none` / `gen_frame` write bytes 0..11 only. "MEM-FT" below.** CORPSE-ASHES: `FRT_MAX` 132, 129 used, 3 spare (for the animation items). 3F-T13bc: `FRT_MAX` 132 (all used), `FRT` = (`P_ENTITIES` − `FRT_MAX` × 16) & `$FF00` (page-aligned: `blit_sprite`'s nibble-swap fid × 16), the rest up to `P_ENTITIES` is **`FRT_GAP`** (`$AF40..$AFFF`, 192 B, runtime only): `seq_rows` (119 B, moved out of the image) + 73 B free.** Before: frame runtime table (A6: moved from `$B200`): 16 B/fid (4 variants × bank,lo,hi), **`FRT_MAX` 128** (3F-T2, was 160: 101 used + the 23 lean 3F frames of plan 3F A1 = 124, 4 spare; +512 B bank 2 and −160 B of the low-RAM descriptor growth reserve; D3-4: 101 used; 74 at C3-7); `FRT = P_ENTITIES − FRT_MAX × 16` |
| `$B000..$B1FF` | `P_ENTITIES` | 16 slots × **32 B** (layout below); slot 0 = hero |
| `$B200..$B7FF` | `BANK2_FREE` | the vacated A5 `FRT` (1,536 B, runtime RAM, not in the image/tape; `BANK2_FREE_END` = `SLOTREC`). **B3B-1 (D8): fully reserved; B3B-11 / B3B-11b use it** — **`FONT6` `$B200..$B5FF` = the PLANAR 6×8 font** (B3B-11b, for the quad printer): line *l* of char *c* (32..127) at `FONT6 + (l>>1)*256 + c + (l&1)*FONT6_WB` (`FONT6_WB` 96): 4 pages, even lines in window A (offsets 32..127), odd lines in window B (128..223); built at boot by `panel_boot` from the char-major `font6x8` (bank-1 `vdata`, via `GEN_SRC`), glyph bits 1..0 masked off. Free holes inside the planes: offsets 0..31 / 224..255 of each page (`$B200..$B21F`, `$B2E0..$B31F`, `$B3E0..$B41F`, `$B4E0..$B51F`, 32 + 3 × 64 B); (B3B-13..C3-7: `ZAP_GLYPHS` `$B200..$B20F`, gone with the zap in D3-0.) **D3-0: the holes hold the 3D runtime state** — see "3D contracts (D3-0)": `FXREC` `$B2E0..$B30F`, `ST_FLAGS` `$B310..$B31F`, `ST_T1` / `ST_T2` / `ST_X` `$B3E0..$B40F`, `FXQ` `$B410..$B41F`, `RANK_ROWS` `$B4E0..$B4FD`; free: `$B200..$B21F` (32 B), `$B4FE..$B51F` (34 B). **`HOT_COPY` `$B5E0..$B7FF`** (544 B, boot-copied hot code, risk R2): **`$B5E0..$B7D6` = the panel hot image (503 B, C3-3; was 515**: `print6` (quad printer, 4 SMC fetch sites + 8 SMC plane offsets) ~270, `log_push` / `log_push_end` / `log_drop`, `panel_tick` / `panel_step`, `item_hp`, `item_depth`; **IC1: `item_hp` +5 → 508 B, 36 B spare**, was 41), **36 B spare** (C3-3: `panel_step` polls through `icon_poll` and ends in `panel_more`, bank 2; ASSERT `HOT_COPY + PANEL_HOT_LEN <= HOT_COPY_END`; the build DISPLAY reports it). Labels in the `.sym` are the runtime addresses (`DISP`) |
| `$B800..$B8FF` | `SLOTREC` | A7b: per-slot render record, 16 slots × **16 B** (one page; record = `SLOTREC + slot*16`, fields reached by `inc l`): `R_VIS +0`, `R_FID +1` (written by `anim_tick`), `R_FPX +2`, `R_FPY +3`, `R_COL +4`, `R_ROW +5`, `R_COLS +6`, `R_ROWS +7` (`R_FID..R_ROWS` = the entity's drawn block `E_DFID..E_DROWS` in the same order: `draw_slot` copies it with one LDIR; ASSERTed), `R_LEFT +8`, `R_ATTR +9`, `R_DATTR +10`, `R_DIRTY +11`, `R_LOG +12`, **D3-8e2: `R_TINT +13`** (= `R_ATTR | 4`: the body attr — kind or status tint — last shown with no reaction pending; `render` keeps showing it while `E_REACT` is pending, game.md §6.5.1), **D3-8d: `R_MK +14` / `R_MKLO +15`** (the slot's status mark as drawn: g / frame / row >> 3, the cell's low byte; "Status marks (D3-8d)"; no spare left) (was the 13 × 16-B `SLOTVARS` arrays `N_VIS`… `$B800..$B8CF`) |
| `$B900..$B9BF` | `DMG_LIST` | per-render damage rects, 4 B each (c0,c1,r0,r1), 48 max |
| `$B9C0..$B9CF` | `PEND_DMG` | queued damage for the next render (4 rects) |
| `$BA00..$BA4F` | `LIVE_LIST` | per-turn collider list, 5 B/entry (`LL_STRIDE`: slot, ptr, w, h); `LIVE_N $BA50`; entry 0 is always the hero (B19 `box_free_mon` skips it) |
| `$BA60..$BA6F` | `RLIST` | per-tick render list (slots visible or still drawn); `RLIST_N $BA70`, `RL_IDX $BA71` |
| `$BA72..$BA79` | `PL_X/Y/W/H`, `PL_STOREY`, `PL_LADDER`, `MSG_Q`, `BLIT_CROWS` | per-turn hero cache, queued impact message, aligned-blit counter |
| `$BA80..$BA9F` | `SEL_FRT_SAVE` | 2 × 16 B: the select idles' boot FRT rows (`sel_frt_copy` saves at boot, restores on every `enter_select`; a game's `gen_kind` re-points its hero's rows above the alloc mark, which the next hero overwrites) |
| `$BAA0..$BAFF` | `PRES_MASK` | A7 present dirty-cell mask: 24 rows × 4 B (`PRES_LEN` 96), byte `row*4 + col/8`, bit `7 − col%8`; ends at the page end (`present` stops when `L` wraps); **3F-B2: must stay 32-B aligned** (`PRES_MASK & $1F == 0`, ASSERTed in gfx.asm: `present` takes a mask byte's first cell low byte as `L * 8`) |
| `$BB00..$BC00` | `ISR_VEC_TABLE` | A8 IM 2 vector table, 257 B, every byte `ISR_VEC_BYTE` `$BC` (`I` = `$BB`); filled by `isr_install` at boot (3E-T1: `boot6_init`, the boot block) (runtime only, not on tape) |
| `$BC01..$BC0B` / `$BC0C..$BC0F` | `DRIP_*` / `MK_*` | **D3-8b: the decorative drip** (11 B, `level_defs.asm`; layout under "3D contracts" → "Decorative drip (D3-8b)"); **D3-8d: the status-mark state** `MK_N` / `MK_RR` / `MK_OPS` / `MK_LEFT` (4 B, `combat_defs.asm`; "Status marks (D3-8d)"); no spare left (was 4 B; 15 B before D3-8b) |
| `$BC10` / `$BC11..$BC40` | `ANIM_N2` / `ANIM_LIST2` | B3B-10 (B3B-9 review): the decor list of a NEXT_MAP build (do_exit), same format as `ANIM_N` / `ANIM_LIST`; `room_shadow` copies the 49 B over them after the scroll. (Was the B3B-1 `OCC_MASK`, 72 B: dropped — `decor_tick` tests a due cell against the drawn footprints directly, see "As built in B3B-10") |
| `$BC41..$BC49` / `$BC4A..$BC50` / `$BC51..$BC5E` | `HERO3D` / `TURN_PEND` / — | **D3-0: `HERO3D`** (9 B: `MP_RG`, `HERO_RES` 3 B, `HERO_IMM`, `MP_SH`, `STAT_SH`, D3-6a `HERO_DEF`, `XP_UP`; "3D contracts (D3-0)"), **D3-7: the `TURN_PEND` block** (7 B: `TURN_PEND`, `ACT_ABL`, `ACT_AT`, `MON_AT`, `FX_DROP`, T7 `LOG_TURN` / `LOG_PDIR`), **3E-T2: `PAGE_OPEN` `$BC54` (1 while the bag page is up) / `PAGE_N` `$BC55` (opens, mod 256)**, **3E-T13: `PAGE_VERB` `$BC56` / `PAGE_SLOT` `$BC57`** (the page's return: "Bag page (3E-T13)") (`combat_defs.asm`, test-observable, not zeroed per level), **3E-T8: `GEAR_MP` `$BC58`, `MP_PER` `$BC59`, `FX_OP` `$BC5A`, `FX_ARG` `$BC5B`, `PAGE_VLAST` `$BC5C`** ("3E-T8"), **IC1: `QS_RECHK` `$BC5D`** (bit 7 = an icon-bar pass wanted in a 1st frame; "IC1 item icons"), **3F-T6: `WEAR_PEND` `$BC5E` (wear-event bitfield) — the HERO3D spare is now FULL (0 B)**; before: spare (1 B, `$BC5E`; IC1: 2 B; T13: 7 B; 3E-T2: 12 B; D3-8: 14 B; T6: 16 B; D3-0: 21 B; was 30 B spare, B3B-10: the `ANIM_RR` round-robin index dropped, unused — the per-entry `AL_PHASE` counters + per-tick caps need none) |
| `$BC5F` / `$BC60..$BC8F` | `ANIM_N` / `ANIM_LIST` | B3B-1 (D6; B3B-10: `ANIM_N` moved `$BC58` → `$BC5F` so count + list are one 49-B block): animated decor cells of the room in `ROOM_MAP`, 12 × 4 B (`AL_COL`, `AL_ROW`, `AL_TYPE`, `AL_PHASE`); filled by the decor deriver (B3B-9) or copied from `ANIM_LIST2`; stepped by `decor_tick` (B3B-10) |
| `$BC90..$BCBB` | `HERO_ST` | C3-0: the 3C hero / input state block (44 B, runtime RAM, `src/hero_defs.asm`; layout in "3C contracts"); full since C3-2 (`CUR_REP` .. `PAUSE_REQ`) |
| `$BCBC..$BCF3` | `ISR_ADDR` | A8 ISR, 56 B (`ISR_LEN`; 68 with `ISR_SAVE_ALT`, 42 with `ISR_ROM_CHAIN`; ASSERT end ≤ `ISR_ADDR_END` `$BD00`), copied from `isr_image` at boot; `$BCF4..$BCFF` spare |
| `$BD00..$BDFF` | `FI_GLY` | **FLOOR1** floor-item glyph cache: 8 slots × 32 B (icons16 layout, 4 quarters of 8 lines), written by R6 `fi_slot`, read by `erase_rect .item` (uncontended) — see "FLOOR1" |
| `$BE00..$BEFF` | — | stack, **512 B** (FLOOR1: was 768 from `$BD00`; SP = `$BF00`, grows down to `STACK_BOTTOM $BE00`; W20 asserts ≤ 256 B, FLOOR1 measured 66 B over the budget fights; A8: was 1 KB from `$BB00`; C3-1: `tests/world.py` W20 re-measures it: 40 B over boot, a generated D1 start and 53 random turns). **Measured max depth 40 B** (lowest byte touched `$BED8`; pattern-fill over boot, both hero starts, a room transition, the §8.2 walkthrough and both `budget.py` fights, ROM IM1 ISR included; tape path's `LD-BYTES` not covered, ~10 B). The A8 ISR adds 16 B (return address + 6 pairs) + the player's own depth to whatever is in use. **SND-2 T6:** W20 with the WZM player live (Lament) measures **44 B** (lowest byte `$BED4`) |
| `$BF00..$BFFF` | state block | below |

**Entity record** (32-B stride, `defs.asm`): `+0 KIND, +1 ROOM, +2 FLAGS
(1 ACTIVE, 2 PLAYER, 4 HOSTILE, 8 FACING_LEFT, 16 DYING, 32 WALKIN, 64 PENDING),
+3 X (body-left col), +4 Y (body-top row), +5 HP, +6 MAXHP, +7 AIDIR (±1 climb
dir), +8 POT (hero potions), +9 PX, +10 PY, +11 MODE, +12/13 SEQ ptr, +14 TMR,
+15 REACT, +16 REACTAT, +17 WPH, +18 FLT, +19 FLA, +20 MSG, +21 TGT, +22 HIT,
+23 GOLD (3F-T5: `E_GOLD` = `LEK_GOLD` $20 on a golden boss, else 0; D3-0: was ZAP; 3F-T8: read by the glow, hit_roll atk + 2, atk_mod dmg + 1, deal_hit DEF + 1 / IMMF_BOSS, room_status; MUST stay $20 / 0: lp_bank ORs it into the kind byte), +24 DVIS (bit0 drawn, bit3 facing), +25 DFID, +26 DFPX, +27 DFPY,
+28..31 drawn footprint col,row,cols,rows`. Hero HP/potions = `$B005`/`$B008`.

### Bank 5 low RAM (`$6000-$7FFF`, free after `CLEAR 24575`)

| Address | Symbol | Size | Contents |
|---------|--------|------|----------|
| `$6000` | `ROOM_MAP` | 672 | current room tile ids, 32 × `PLAY_ROWS` (B3B-3: rows 0–17 = 576 B used, `PLAY_CELLS`; 672-B buffer = `MAP_BUF_LEN`, page-aligned) |
| `$6300` | `NEXT_MAP` | 672 | destination room during a transition |
| `$6600` | `TILE_GLYPHS` | 512 | 8×8 tile glyphs, **64 ids** (A6), glyph = base + id·8; **512-aligned** so `tile_rect` forms it as `E = id·8`, `D = (base>>9) RL CF` (+8 T per cell vs 32 ids) |
| `$6800` | `BITREV_TAB` | 256 | bit-reverse table (mirroring, boot; page-aligned) |
| `$6900` | `TILE_ATTRS` | 64 | attr by tile id (one page: `ld h, TILE_ATTRS>>8`) |
| `$6940` | `GEN_SRC` | 512 | **3F-T2: the generator session's scratch (R6 `pool_hero` / `pool_proto` / `pool_list` → `gen_list` / the seq loader; dead before `panel_init`): `PL_LIST` `$6940` (≤ 25 B: pairs fid0, fcnt, `$FF` end), `SQ_PTR` `$6959` (7 words), `SQ_TOP` `$6967`, `PL_PROTO` `$6969` (6 B), `SQ_IMG` `$6980..$6B34` (the unpacked sequence masters, 437 B; ASSERTed below `TX_DEC`) — over `FI_PAD` / `FI_TSLOT` / `FI_CELL` (SQ_IMG ends at `$6B34`, below `FI_INK` `$6C00` and `GEN_MIR`; it does not run over `FI_INK`), rebuilt by `fi_full` at the following room build as after any generator run.** 3F-T1: `PL_LIST` (12 B at `$6940`, R6 `pool_list` → `level_enter`, dead before `panel_init`). B3B-11b: `pblit` (one icon, <= 54 B) stages `vdata` here (3E-T1: `panel_boot`'s font halves no more: boot6_tiles reads the boot block in place) — new game only, never during generation. C3-6: the pause overlay saves rows 7-9 here (`PAUSE_SAVE`, 864 B: it runs on into `GEN_MIR`) while paused |
| `$6B40` | `GEN_MIR` | 512 | generator: mirrored frame (`LOWRAM_END` = `LOWRAM_FREE_END` `$6D40`). D3-TX: its top 43 B `$6D15..$6D3F` = `TX_DEC` (`tx_dec`'s transient decode buffer, menu text) |
| `$6D40..$6E7F` | `LVL_STATE` | 320 | B3B-1: **3B level state** (header 16, `EDGE_TAB` 6 (+10 spare), `ROOM_DESC` 9 × 16, 16 spare → **3E-T3: `TRAP_LIST` 6 × 2 + `TRAP_N` + 3 spare** at `$6DF0`, `FLOOR_LIST` 32 × 4) — byte layout under "3B contracts" / "3E contracts". Runtime only (not on tape). Written by `level_gen` (B3B-7) or, for the PROTO rooms A–D, by `proto_level` (B3B-8, from `new_game`) |
| `$6E80..$6EBF` | `ORN_GLYPHS` | 64 | B3B-1: row-17 ornament glyphs (8 × 8 B, game.md §3.3: not tile ids, same on every level). Here, not in bank 3, because `orn_cells` (also called from the scrolls) reads it with any bank paged. Filled at boot by `init_tiles` (bank 3, from `panel_orn.asm`). `LOWRAM_END_3B` = `LOWRAM_FREE_END` = `$6EC0` |
| `$6EC0..$6F31` | `LP_STATE` | 114 | **LP (game.md §9.4, plan task LP)**: the lazy-population level budget + `ROOM_VISITS` + 9 room records (102 B persistent + 12 B `lp_enter` scratch) — byte layout under "LP contracts". Runtime only. Written by `lp_budget` (level entry) / `lp_bank` / `lp_enter` (room changes). `LOWRAM_END_3B` = `LP_END` (`$6F32`): the test stubs moved up with it |
| `$6F32..$6FE3` (3F-T2, kit) | free | 178 | **3F-T2: 135 B kept for descriptor growth (`FRT_MAX` 128 − 101 frames), 43 spare kit** (review: +7 B `SEQ_TRAP` path in `sq_load`; 50 before); before: `$6F32..$71A5`, 628, of which 295 B (D3-4, 101 frames) are kept for descriptor growth (below); **3F-T1: 29 spare kit** (−48: the level-pool block in `level_enter`, `gen_idles`; the cold block now starts at `$7076`; "Level pool (3F-T1)"); **SRC6 spike: 85 spare kit / 95 release** (+8 `zx0_frame`'s SRC6 range); **3E-T12: 93 spare kit / 103 release** (+44: `ovl_fx` / `ovl_fx_saved` deleted; after 3E-T8: 49 / 59); **3E-T6: 119 spare** (−205: `it_tab`, `item_glyph` / `item_ink`, `fl_attr`, see "3E contracts" ledger); **3E-T2: 333 spare** (−43 `page_run`); 3E-T1: 376 spare (was 118 at main `9c99ad1`: the boot code / ISR image / key table → the boot block, the table-driven tape loader, + `ovl_run` 30 B; ledger under "Boot block"); 259 spare (`LOWRAM_SPARE` DISPLAY; **D3-8b −5: `vis_room_sync` ends `ld hl, drip_room` / `jp far7`**; was 264; **D3-S2 −89 (from the measured 353): `clear_screen` / `print_char` / `print_str` moved here from bank 2**; **L2 engine −28: `pit_range` + `pit_w` reading `L2_PITW`, `jump_pit` on `pit_range`**; before: 400, measured after merging D3-4 + J1: **D3-4 −8 (`start_game` generates the class FX kind) + 101 frame descriptors; J1 −145: `try_jump` / `jump_pit`**; earlier history as before: LP −114 `LP_STATE`; D3-TX −55; B12 −21; C3-2 −1; B14 −175) |
| `$6FE4..$7FFF` (3F-T2, kit) | `lowram_code` (`start` first) | 4,124 | **3F-T2: code 3,619 B + 101 descriptors 505 B; spare after the (now `FRT_MAX` 128) descriptor reserve 135 B: 43 kit** (50 before the `SEQ_TRAP` path) (was 29: +160 reserve, code +139 net: the sequence-cache loader `sq_reset` / `sq_load` / `ksm_ptr` / `sq_fill` in, `gen_kind` + its loops → `gen_list`, `level_enter`'s FRT LDIR → R6). Before: **cold block**, ends exactly at `$8000` (`src/lowram.asm`): **3E-T2: code 3,169 B + 101 descriptors 505 B**; 3E-T1: code 3,126 B (was 3,889 at `$70CF`); before: code 3,238 B + 101 frame descriptors 505 B (D3-S2 +89 incl. the bitmap-shadow paths' removal: + `clear_screen` / `print_char` / `print_str`, − `room_show` / `room_shadow`'s shadow ornament; L2 engine +28: `pit_range` / `pit_w`; D3-4 +8: `start_game` → `gen_kind(HERO_KIND + K_FX_BASE)`; J1 +145: `try_jump` D 6 / 7 + `jump_pit` + `pit_w`; earlier: D3-TX `tx_dec` + `.txt`, B12 +21, B14 +175, C3-2 +1, C3-1 +33, C3-0 +3, B3B-13 +37) |
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
most of that margin — the alias stays. `$5B00-$5BFF` and `$5CC0-$5FFF` (~692 B after D3-6b PF_RAM $5E00..$5EFF and D3-8d MK_RAM
$5F00..$5F8B (140 B), E: free once `boot` has moved SP off the BASIC stack) are a further runtime-only (not tape-loadable)
reserve (B3B-11: `$5B00` = `LOG_TXT`; **D3-6b: `$5E00-$5EFF` = `PF_RAM`**, the
proj_fire scratch — never touched before `boot`; **3E-T3: `$5D00-$5D78` = `ITEM_RAM`**, zeroed by `new_game`;
still free: `$5CCB-$5CFF` (53 B; `$5CC0-$5CCA` is the ROM channel area, avoided), `$5D79-$5DFF` (135 B),
`$5FF4-$5FFF` (12 B; **3F-T7: `$5F8C-$5FF3` = `RG_RAM`**, the ranged-attack scratch + shot queue, "3F-T7"; **3F-T8: `$5FF4` = `BOSS_TRAP`; 3F-T9: `$5FF5-$5FFF` = `SPQ_RAM`, the spawn queue + `sp_run` scratch — the reserve after `RG_RAM` is full**, "3F-T9") — `tests/items3e.py` R1/R2 canary them through a game start, play and a descent). A8: after `boot` nothing uses the system variables but
`SYS_FRAMES` (`$5C78-$5C7A`; the IM 2 ISR does not run the ROM keyboard scan),
so most of `$5C00-$5CBF` is free too unless `ISR_ROM_CHAIN=1`.

### State block (`$BF00..`) — stable test-observable addresses

| Address | Symbol | Meaning |
|---------|--------|---------|
| `$BF00` | `GAME_STATE` | `GS_BOOT 1`, `GS_PLAYING 2`, `GS_WIN 3`, `GS_DEAD 4`, **`GS_SELECT 5`**, **`GS_TRANSITION 6`**, **`GS_LEVEL 7`** (3F-T1: `level_enter` before the room map exists — card, `level_new`, the level pool; `gen_frame` allowed; `GS_TRANSITION` from the end of the pool) |
| `$BF01` | `RNG_STATE` | xorshift16 (7,9,8); reseeded `$A55A` every new game |
| `$BF03` | `TURN_COUNTER` | word; +1 at the end of every turn's animation |
| `$BF05` / `$BF06` | `INPUT_SRC` / `KBD_MATRIX` | P3 injection contract, unchanged |
| `$BF10` | `TURN_PHASE` | 0 INPUT / 1 ANIM |
| `$BF11` | `TICK_COUNTER` | word, 25 Hz ticks |
| `$BF13` | `CUR_ROOM` | room id = 3×3 grid cell 0..8 (B3B-8; PROTO rooms A 0, B 1, D 3, C 4 — was 0..3 = A..D) |
| `$BF14` | `HERO_KIND` | 0 Knight, 1 Wizard (2 = retired Rogue: hole in the `K_*` ids) |
| `$BF15` | `POTIONS_TAKEN` | bitmask of taken `FLOOR_LIST` entries 0..7 (B3B-8; the PROTO potion ids 0..3 = entries 0..3). 3E-T11: set for every bag pickup (`pp_take`), any type — a test observable "entry i taken", never "potion i"; no engine reader |
| `$BF16` | `INPUT_REPEAT` | 1 (default) held keys repeat; poke 0 = edge-triggered |
| `$BF17` | `ANIM_FREEZE` | poke 1: resting sprites hold IDLE frame 0 (goldens) |
| `$BF18` | `PORT_7FFD_SHADOW` | last `$7FFD` value. The ROM's own shadow `BANKM` (`$5B5C`) is deliberately left stale: PROTO never returns to 128 BASIC and never calls 128-ROM paging routines |
| `$BF19` | `OVERRUN_COUNT` | word: ticks whose work exceeded 2 frames |
| `$BF1B` / `$BF20` | `ANIM_TRACE_IDX` / `ANIM_TRACE` | 32-B ring of (slot, frame_id) per drawn-frame change |
| `$BF1C..$BF1F` | `LAST_TICK_FRAME`, `TURN_TICK`, `NEED_RELEASE`, `EXIT_KIND` | loop internals |
| `$BF40` | `BLIT_MISS` | count: stationary frame requested at an ungenerated shift (debug trap, expect 0) |
| `$BF41` | `GEN_OVERFLOW` | 1 if the pre-shift pool ran out (expect 0). An allocation ending exactly at `$10000` opens the next bank for the next one |
| `$BF42..$BF4F` | allocator, damage counts, exit dest/storey/col (`$BF4B` spare since D3-0: was the zap overlay's `ZAP_LEN`; `$BF48`, `$BF4A` below) | internals |
| `$BF48` | `CLIMB_BLK_XY` | B18 word: `CLIMB_BLK_ID`'s (x, y) at its last block (`climb_blocked`): a repeat blocker that moved since (yielding) earns another wait, up to `CLIMB_SQZ_N` (4) blocks; one that did not move is squeezed past. Test-observable |
| `$BF4A` | `PHASE_TRAP` | `PHASE_SHIFT` 1 (default) / 2 only (`-DPHASE_SHIFT=0`: unused, never written): count since boot (wraps), cleared by `boot`, of walk ticks (KS_MOVE, non-flyer) whose `E_WPH` parity disagreed with `E_PX & 4` — `anim_entity .walkph` locks the drawn phase to the px parity (1) or draws the unlocked one (2: a disagreement then shows as `BLIT_MISS`). Debug trap, expect 0 |
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
| `$BF9F` | `PEND_N` | B19: PENDING bodies of `CUR_ROOM` counted by the last `build_live`; 0 = `pend_hit`'s fast path (a monster move never ends on a PENDING body it does not already overlap: `try_step`; the squeeze's foot cell too) |
| `$BF99` | `GEN_TRAP` | count (saturating): `gen_frame` ran while `GAME_STATE` = PLAYING/TRANSITION, i.e. while `GEN_SCRATCH` holds live room maps (debug trap, expect 0; `tests/game.py` #1/#40/#51) |
| `$BFFB` | `SEQ_TRAP` | 3F-T2 review: count (saturating, cleared by `boot`): `sq_load` got a kind with no master block (`ksm_tab` 0) or no free cache slot, i.e. the kind would blit the hero's sequence row (build-ASSERTed never; debug trap, expect 0; `tests/game.py` / `tests/gfx_integrity.py`) |
| `$BFA0` | `MSG_BUF` | 32 B: `show_impact_msg` / `impact_line` (B14: also the squeeze line) composes the impact line here (B3B-13: a token stream, pre + name + post, ≤ 31 B + 0 ASSERTed), then `log_push` copies it (B3B-11; tests use it as a stub result byte) |
| `$BFC0` | `TIMING_MARK` | spare |
| `$BF4B` | `GLOW_CNT` | **3F-T8**: golden-glow tick count (main.asm `.panel`: +1 on every tick that may draw a panel item, never a turn's input / TP_FIRE tick); `glow_kat` attr = `glow_tab[(GLOW_CNT >> 1) & 3]` |
| `$BFC2` | `AY_CALLS` | A8 word: `AY_PLAY` calls (`ay_play` counts every call, whatever the mailbox; = frames since boot's `EI`; `tests/game.py` #61). Test-observable |
| `$BFC4` | `JUMP_TURN` | B3B-5 word: the `TURN_COUNTER` value on which a jump is refused (= the turn after a jump; game.md §2.4 "not two turns in a row"); `$FFFF` = none (`new_game`) |
| `$BFC6` | `LOCK_SHOWN` | B3B-5: 1 = the locked-door message was printed for the key still held (once per press); `read_turn_input` clears it when no key is held |
| `$BFC7` | `CLIMB_BLK_ID` | B14: slot of the body that blocked the hero's last climb (`climb_blocked`) |
| `$BFC8` | `CLIMB_BLK_N` | B14: consecutive blocked climbs by `CLIMB_BLK_ID`; the 2nd = squeeze past (prototype §6.4 "B14 fix rules") unless the blocker moved since its last block (B18: another wait; `CLIMB_BLK_XY`); a block by another body continues the count; the `CLIMB_SQZ_N`+1th block in a row squeezes anyway. Cleared by `read_turn_input` after any other consumed turn (`CLIMB_BLK` = 0), by the squeeze and by `level_reset`. Test-observable |
| `$BFC9` | `PLAYER_SC` | C3-1 (`$BFC7` until the B14 merge): shortcut keys this sample (`sample_input`): bits 0-3 slot 1..10 (key 1..9, 0 = 10; lowest held wins; 0 = none; the selected Sinclair half of the number row is ignored), bit 4 `SC_SOUND` (S, SND-1: the hotkey edge, `intent_tick` -> `snd_hot` -> bank-1 `snd_cycle`; never a turn), bit 6 `SC_INV` (I), bit 7 `SC_BREAK` (CAPS + SPACE). Test-observable |
| `$BFCA` | `LVL_SH` | C3-3: hero level digit last drawn ((31, 19); `$FF` = never) |
| `$BFCB` | `ICON_SIG` | C3-3: `icon_sig` (SEL_SLOT, daggers 0, bow ready) as last drawn — `icon_poll` compares it, not the 10 slot states (~0.15k T a step) |
| `$BFCC` | `ICON_MODE` | C3-2b: 1 = ICON MODE (↓+FIRE): play frozen in INPUT ticks (`anim_gate` / `decor_gate`), ←/→ move the cursor, FIRE uses, ↑ / ↓ / BREAK leave |
| `$BFCD` | `DN_T` | C3-2b: ticks ↓ alone has been held (`DN_DEFER` 3: the ICON MODE window; the wait / climb-down acts at 3) |
| `$BFCE` | `DN_COMMIT` | C3-2b: 1 = a ↓ released inside the window: `tpt_intent` acts on it once |
| `$BFCF` | `PRE_N` | C3-2b: `pre_get` state (the info line's `>` prefix in ICON MODE) |
| `$BFD0..$BFFF` | **3B sub-range** (`STATE_3B`, B3B-1) | `PANEL_DIRTY $BFD0` (D5 `PD_*` bits), **`EXIT_LOCK $BFD1`** (C3-2b: directions ignored until released after leaving ICON MODE; was spare), `HUD4_EXT $BFD2` (4 B) / `HUD4_PW $BFD6` (4 B): rows 20..23 (B3B-11: the successors of `HUD_EXT`/`HUD_PW`), `LOG_QN $BFDA` (pending messages), `PANEL_POT_SH $BFDB` (potions last drawn), `P_NUMBUF $BFDC` (3 B: number / depth text), **`FIRE_LOCK $BFDF`** (C3-2b review: FIRE masked after BREAK until FIRE is released; B3B-11b: was `P_LIM`), `LOG_Q $BFE0` (8 B: `LQ_RD` +0 oldest ring slot, `LQ_DROP` +1 dropped / replaced pushes (saturating, expect 0), +2..+7 spare — B3B-11b: no chunked-print state), `PANEL_HP_SH $BFE8` (2 B: hero HP, MAXHP last drawn, `$FF` = never; B3B-11b, was `$BFD1`), **`JOY_MIRROR $BFEA`** (C3-0, see "3C contracts"), **SND-2 sound mailbox `$BFEB..$BFF0`** (below), `$BFF1` `DNG_DWELL` / `$BFF2` `DNG_CALM` (SND-3: Dangerous cue state, `mus7.asm`; `level_enter` clears both), **`$BFF3` `SFX_NEXT`** (SND-5, below), `$BFF4` `SFX_XP`, **3E-T16 `$BFF5..$BFFA` `TRP_PRE` / `TRP_WAIT` / `TRP_EV` / `TRP_STEP` / `TRP_ENT`** (below), `$BFFC..$BFFF` spare (`$BFFB` = `SEQ_TRAP`). Test-observable |
| `$BFEB` | `SND_MODE` | SND-2 (game.md §3.6): bit 0 `SND_MUSIC`, bit 1 `SND_SFX`, bit 7 `SND_HOLD` (pause). Boot = `SND_ALL` (3); per power-on: `new_game` / `hero_st_init` / `level_*` never write it. Main code: single-byte store or `set` / `res` |
| `$BFEC` | `MUS_REQ` | SND-2, **level**: the looping tune id (`MUS_*`, `MUS_FIRST` 2 ..`MUS_COUNT` 7; id 1 = the removed Dungeon Crawl, rejected like any invalid id), 0 = silence. Never consumed: `ay_play` compares it with its private `ay_loop` and (re)starts on a change. Written by main code only (SND-3: `mus_pick` is the only writer in play). Boot 0 |
| `$BFED` | `MUS_SHOT` | SND-2, **edge**: one-shot id, 0 = none. Main writes, the ISR clears (taken, or dropped while music is off / held, or an invalid id). A new shot replaces a playing one. Final cue (Y death, T win): `MUS_REQ` 0 then `MUS_SHOT` id; a stinger (R) leaves `MUS_REQ`: the loop restarts at bar 1 when the shot ends. Boot 0 |
| `$BFEE` | `MUS_STATE` | SND-2, ISR-written: bits 0-1 `MS_IDLE` 0 / `MS_LOOP` 1 / `MS_SHOT` 2; bit 7 `MS_DONE` = the last one-shot finished (set when it ends, cleared when the next shot is taken; kept through loops / idle / music off). Boot 0 |
| `$BFEF` | `MUS_CUR` | SND-2, ISR-written: the tune id sounding (the shot's while one plays), 0 = none. Boot 0 |
| `$BFF0` | `SFX_REQ` | **SND-5, edge**: the requested sound effect id (`SFX_*`, `build/sfx/sfx_ids.inc` = prio << 5 \| index 1..`SFX_COUNT`), 0 = none. Main code writes it only through **`sfx_req`** (bank 2, `ld a, SFX_x : call sfx_req`, 5 B a call site, any bank; keeps A / BC): replaced only by a request of >= priority; dropped while `SND_HOLD` or with the SFX bit off. The ISR (`sfx_step`) clears it every unheld frame (taken: >= the playing effect's priority, else dropped) and every held frame (`ay_play` `.hold`). Boot 0 |
| `$BFF5..$BFF6` / `$BFF7` / `$BFF8..$BFFA` | `TRP_PRE` / `TRP_WAIT` / `TRP_EV`, `TRP_STEP`, `TRP_ENT` | **3E-T16** (item_defs.asm): the hero's `E_X`, `E_Y` before this turn's action (`turn_input`, every try, before the held / free split: the trap trigger's "first brings it under the body"); `TRW_*` bits: bit 0 this turn's action was a Wait (`tpt_intent .srch`: DOWN without a climb, '.', a blocked climb), bit 1 the room-entry sense (`end_turn .ex`), read and cleared by `trap_chk`; the armed trap sequence: the event (`TEV_FIRE` + `TT_*` / `TEV_FIND`), the step counter, the entry's low byte. Never zeroed (written before read). `$BFFC..$BFFF` spare (`$BFFB` = `SEQ_TRAP`) |
| `$BFF4` | `SFX_XP` | **3E-T0**: the signed pitch offset (semitones, two's complement) of the next `SFX_STATUS` take. `sfx_msg` writes it before `sfx_req`; the ISR copies it to `sfx_xp` (AY-slot state, `ay_vars_end - 1`) when it takes `SFX_STATUS` and zeroes it for every other effect. Boot 0 (state block, no init needed: only read on a STATUS take). `$BFFC..$BFFF` spare (`$BFFB` = `SEQ_TRAP`) |
| `$BFF3` | `SFX_NEXT` | **SND-5**: one deferred effect id: a request of prio >= `SFX_DEFER_PRIO` (6) that lost to a pending (`sfx_req`) or playing (`sfx_step`) one of higher priority; the ISR starts it the frame the playing effect ends (and clears it; also cleared when the SFX bit is off, on a held frame with nothing playing, and by `level_enter`). The slot is overwritten only by an id of >= priority. Written by `sfx_req` and the ISR (single-byte stores). Boot 0 (`boot`, next to `SFX_REQ`); ASSERT `SFX_NEXT == DNG_CALM + 1` (`level_defs.asm`) |
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
`page_run.closed` / `page_run.post` (3E-T2, low RAM, no code) are
`tests/page.py`'s close-cost probes (page closed / copied back); the page
loop itself ticks through `select_tick` (`menu_frame`), and `PAGE_ORG` (the
overlay entry, bank 5) is P1's open-cost probe.
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
opens `tests/budget.py`'s "cast" class). D3-8e: `probe_act_prep` (a bank-2
`ret` that `act_begin` calls right before far3 `proj_pre`: `tests/abil.py` /
`abil_ammo.py` snapshot the model world and seed the RNG there, the cast's
strikes start on the input tick).
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
| `$6D4C` | `LVL_FLAGS` | `LF_GRATE_OPEN 1`, `LF_KEY_TAKEN 2`, `LF_SEAL_OPEN 4`, `LF_GATE_HINT 8` (B12: the lair's gate hint was logged this level; `lair_hint`, reset by `level_gen` rewriting the byte), `LF_UNIQUE 16` (3E-T11: the boss unique dropped this level, `mon_drop`), **`LF_PROVOKED 32`** (3F-T8: the hero's damage reached the lair boss, deal_hit `.mon`; cleared by `lp_post` when the boss is placed). **3F-T8: `level_gen` writes 0 (the grate SHUT); `grate_open` sets `LF_GRATE_OPEN`; `LF_GATE_HINT` now remembers the first-entry line `THE GATE IS BARRED`** |
| `$6D4D` | `FLOOR_N` | floor-list entries used |
| `$6D4E` | `MASTER_SEED` | word, per game |

`TRAP_LIST` `$6DF0..$6DFB` + `TRAP_N` `$6DFC` (3E-T3, the ROOM_DESC spare; `$6DFD..$6DFF` spare): see "3E contracts".

`FLOOR_LIST` `$6E00..$6E7F`, `FLOOR_MAX` 32 × `FL_STRIDE` 4: `FL_ROOM` (bits
0–3 room, bit 7 `FL_S1` storey 1; `FL_EMPTY` `$FF` = picked up / free),
`FL_COL` (item cell col; row = the storey's standing row `9s+7`), `FL_ITEM`
(3E-T6: written by the level-start generator `items_ovl.asm`: all 32 entries, unused = `FL_EMPTY` × 4; the cell's glyph = `item_glyph`(type) of the last live entry, its ink = `item_ink`(type) (`it_tab`); no ISTATE on the floor (3E rev 6); 3E-T3: the `IT_*` enum in `item_defs.asm`, ISTATE in the parallel `FL_IST`; 3B: `IT_POTION` 1; D3-7: `IT_DAGGER` 2 / `IT_ARROW` 3, `FL_QTY` = the stack's count — one entry per type and cell, an ammo stack may share a cell with another item, game.md §6.3), `FL_QTY`.

### Tile ids (64; common 0..31 FULL)

| Id | Symbol | Note |
|---|---|---|
| 0, 1 | `T_AIR`, `T_PLAT` | |
| 2 | `T_BRICK` = `T_WALL_DARK` | plain air-band wall face; re-glyphed DARK (B3B-2) |
| 3 | `T_WALLF` | wall in a floor row (blocks, lintels in row 8/17) |
| 4–6 / 7–9 | `T_LAD_L/M/R` / `T_HOLE_L/M/R` | ladder / ladder cells in a floor row |
| 10 | `T_TRAP` | **3E (user-approved glyphs, `assets/gfx/concept/grid/items3e.tiles`): the revealed trap plate**, ink `$42` default, `TILE_FLAGS` 0 (walkable, game.md §1.5). The potion moved to id 60 (`T_POTION` = `T_FLASK`). T6 generates the trap list; **3E-T16: a known unspent trap is stamped by `build_room_map` (before the decor deriver) and `TILE_ATTRS[T_TRAP]` is set to its type attr there and on a mid-room reveal (≤ 1 trap a room; see "3E-T16")** |
| 11, 14 | `T_DOOR_JAMB_L`, `T_DOOR_JAMB_R` | B10 (user option B): open-door jambs, `$A0` / `$05` × 8, ink `$06`, non-solid (the PROTO chest stand-in is gone, B3B-13) |
| 12 | `T_CHAIN` | small decor; cobweb / moss move to the per-level sets |
| 13 | `T_GRATE_SHUT` | **3F-T8 (§9.7 R2, BOSS-GUARD)**: the CLOSED lair gate (tiles_3f `grate_shut`, ink `$07`), `TF_SOLID \| TF_FLOOR`; `build_room_map` stamps it over the 3 exit cells AFTER the deriver while `LF_GRATE_OPEN` is clear; R6 `grate_open` swaps them to `T_GRATE` (+ glow) when the boss dies |
| 15–18 | `T_LECT_TL/TR/BL/BR` | **3F-T8 (§9.7 R2)**: the D8 Sanctum lectern 2×2 (tiles_3f, `$43` top / `$06` bottom), `TF_SOLID \| TF_ATTACK` (`id − 15 < 4` = attackable); glyphs + flags only, placed by T11 |
| 31 | `T_FREE31` | FREE (DEC2) |
| 19, 20 | `T_END_L` = `T_PIT_R`, `T_END_R` = `T_PIT_L` | floor edge right / left of a hole: the pit caps share them |
| 21–25 | `T_DOOR_ARCH_L/R`, `T_DOOR_L/R`, `T_DOOR_LOCK` | concept §3.1 (5 door ids) |
| 26, 27 | `T_GRATE`, `T_RUBBLE` | B12: `T_GRATE` = the **raised** gate (variant B, ink `$46` = `ATTR_GRATE`), `TF_LADDER \| TF_HOLE`, stamped over the lair's open level exit; 3F-T8: `T_GRATE_SHUT` = 13 (own id, above) |
| 28–30 | `T_WALL_DITHER/PATCH/FADE` | wall set |
| 32..59 | `T_LVL_BASE`.. | per-level decor (bank-7 tileset) |
| 60..63 | `T_ITEM0`..+3 (= `T_LVL_OBJ`) | **FLOOR1 floor-item MARKERS** (the only ids ≥ 60, so `erase_rect` tests a cell with one compare inside its ids-32..63 path): a live `FLOOR_LIST` entry's 2×2 cells hold `T_ITEM0 + 2s` on row 9s+6 and `+ 2s + 1` on row 9s+7 (cols c..c+1), written by `build_room_map` and `ap_stamp`; drawn from the glyph cache ("FLOOR1" below), never from their tile glyph (the slot bytes 28..31 still hold the old 3E class glyphs: `tile_rect` draws them for an instant before `fi_cells` overdraws, cold paths only). `TILE_FLAGS` 0 (slot bytes), `dg_bad` 0, not `is_decor`. The D8 lectern swap (3F) needs another home than 60..63 now |

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
  the large torches / braziers (per-level ids) `TF_ANIM`, the wall set (DARK = BRICK, DITHER,
  PATCH, FADE) `TF_SOLID`, RUBBLE 0, 32..59 0, 60..63 0 (FLOOR1: the item markers `T_ITEM0`..+3; the D8 lectern needs another home)
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
  3E-T11: every non-ammo entry goes to the BAG (`pu_add`, bank 3); see "3E-T11".
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
  are separate entries): `AL_TYPE` 1..15 = attr-cycle kind (1 flame:
  `dt_attr_tab`, 8 steps; DEC1 removed kind 2, the candle), ≥ `AL_GLYPH_MIN` 16 = glyph swap holding the
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
  paper: black on every attr-cycled cell (the large
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
  A = depth 1..8, DE = first log line): `GAME_STATE` = TRANSITION (3F-T1:
  `GS_LEVEL` until the level pool is generated, then TRANSITION); clear the
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
  `present_full`. Callers set `GAME_STATE` (PLAYING) and resync the tick.
  **3F-T1:** between `far3 level_new` and `stinger_wait` the **level pool**
  is generated ("Level pool (3F-T1)"; `GEN_TRAP` stays 0: `GS_LEVEL`). Measured: `level_enter` (D2, DI) **1.56M T ≈ 0.44 s**;
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

**MEM-RECLAIM w2a (2026-10-30): deduplicated.** The 8 raw 320-B slots (2,560 B)
held only 72 distinct glyphs and 4 distinct flag sets. `BANK_TSET` 7, one block
at `TSET_BASE` `$FAA0` (`tilesets..tilesets_end` = `$FAA0..$FF67`, `TSET_LEN`
1,224 B; 152 B free to `$FFFF`):
- `tset_slots`: 8 records × `TSET_STRIDE` **65** B, record = depth − 1 (PROTO
  depth 0 → 0): +`TSET_GIDX` 0: 32 `tset_pool` indices of ids 32..63 (id order),
  +`TSET_ATTRS` 32: 32 attrs, +`TSET_FSET` 64: the `tset_fsets` index;
- `tset_fsets`: `TSET_NFSET` (4) × 32 B `TILE_FLAGS` sets of ids 32..63;
- `tset_pool`: `TSET_NPOOL` (72) × 8 B distinct glyphs (≤ 256: 1-byte index).
`level_tiles7` (bank 7, `src/tiles7.asm`; far7 from the 6-B low-RAM stub
`level_load_tiles`, A = depth) gathers 32 glyphs → `TILE_LEVEL_GLYPHS`, LDIRs
32 attrs → `TILE_LEVEL_ATTRS` and the flag set → `tile_flags + 32`, then patches
`theme_ids` (low RAM) with `LVL_ATTR_FLOOR` / `LVL_ATTR_WALL`. Tests expand a
record with `tests/game_lib.py` `tset_slot()` (the old 320-B slot image).
Data: `assets/gfx/tiles/tilesets.asm` (generated by `tools/tiles_convert.py`),
assembled with `MMU 3, 7` into the `.sna` and saved as one headerless tape
block (`tape_tab`). Nothing at runtime writes `$FAA0..$FFFF`. Bytes freed:
bank 7 1,336 B (2,560 → 1,224), turned into bank-7 cold-code space by moving
`B7_CODE` `$E000` → `$DB00` (the old slots 0–3); the old `TSET_HI` tail grew
96 → 152 B free. **D6 PILLAR removed** (2 ids; never placed since decor left
the walls 2026-10-12, `tools/decor_sweep.py`: 0 of 16,163 D6 rooms over 2,000
seeds; every other per-level object and frame is placed): D6 ids after
`TORCH_SLIM` shift down 2 (D6 now 22 decor ids, 6 free tail slots),
`dg_recs` / `dg_cob` regenerated, placements identical.

### Panel (D5) and bank-2 runtime

`PANEL_DIRTY` `$BFD0` bits: `PD_HP 1`, `PD_MP 2`, `PD_FOOD 4` (bar + hunger
word), `PD_AMMO 8`, `PD_LOG 16` (scroll + newest line from `LOG_Q`), `PD_ICONS
32`, `PD_INFO 64`, `PD_DEPTH 128` (depth + key). One item per tick, never in
the input tick. `HUD4_EXT`/`HUD4_PW` (rows 20..23, one page, ASSERTed),
`LOG_Q`/`LOG_QN`, `FONT6` `$B200` (planar, 4 pages), `HOT_COPY` `$B5E0`, `ANIM_LIST` / `ANIM_LIST2`
— addresses in the bank-2 and state-block tables above.

**As built in B3B-11 / B3B-11b** (`src/panel.asm` bank 3, `src/panel_hot.asm`
`HOT_COPY` image (load image in the bank-6 boot block since 3E-T1, was bank-1 `vdata`), `src/panel2.asm` bank 2;
`tests/world.py` W15):
- Layout (concept-screen §5): rows 18–19 the 10 icon slots of the class
  (game.md §3.5; static art: ability / bag icons, quick food / scroll and the
  spare as empty outlines, slot 0 selected = PAPER blue); the quick-potion slot
  shows the `T_POTION` glyph at (col, 19) + the potion count at (col+2, 19)
  (greyed `$07` at 0; stand-in for the PROTO "POT n"); depth `Dn` at (30, 18)
  (`LVL_DEPTH`, PROTO 0 → `D1`); row 20 blank (info line: 3C); row 21 heart /
  HP bar (cols 1–4) + 2-digit number (5–6) `$42`, drop / MP bar empty (3C)
  `$45`, drumstick / FOOD bar + stage word (3E-T9: `item_food`, R6, fill FOOD / 100, word +
  attr by `HSTAGE`: FED `$44` / OK `$46` / HUNGRY `$42` / WEAK `$42`), no ammo; rows 22–23 log
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
  ANIM with `TURN_TICK` 0, in an ability's fire tick, and (D3-8e2) while
  `TURN_TICK` ≤ `COMBAT_NOT_BEFORE` ("Cast-time output gate"); also every `end_screen` tick): while the tick is
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
  Dictionary built greedily from the real strings (saving n·(L−1) − (L+1);
  w2d: capped at `DICT_MAX` 256 entry bytes).
  Streams concatenate (composition in `MSG_BUF`); numbers are literal digits.
- **Block** (`text_img`; **D3-TX: bank 0 = `BANK_TEXT`** at `TEXT_ADDR`
  `$C000`, under the pool (`POOL_START` = its end), own tape block; was bank 1
  after `vdata`, DISPed — the D3-2 strings, 2,684 B, did not fit bank 1's
  992 B; bank 0 is uncontended, so text reads got cheaper). **MEM-RECLAIM w2d
  layout:** `tx_entries` at `$C000` (≤ 256 B, one page: `tk_get` loads B =
  `$C0`) · 0-pad to `$C100` · `tx_tab` at `$C100` (page-aligned: `tx_ptr`
  loads H; DW per `TX_STRIDE` = 2 ids, the stream of the even id; an odd id
  skips its predecessor's 0-terminated stream — the streams stay in id order;
  256 ids = exactly the page) · `tx_dict` (DB per token = the entry's offset in
  the `tx_entries` page) · streams. 195 strings, 72 tokens: **2,282 B** (was
  2,547 with DW per id + DW per token: bank-0 pool +265 B; low RAM 0, bank 2
  +1 B `tk_get`). textpack fails the build if an odd log-width id would skip
  more than `HOT_SKIP_MAX` 24 B (today 19). B3B-13: 24 strings, 4 tokens, 278 B raw text (0-terminated; +48 B
  of the pointers the code used) → **277 B** incl. tables (the corpus is tiny;
  the format pays off with the 3E/3F names).
- **Z80:** `msg_push` / `msg_push_end` (A = TX_*; lowram: page `BANK_TEXT`,
  `tx_ptr`, `log_push(_end)`, hand `$C000` back), `tx_ptr` (A → HL, keeps BC/DE; string ids 0..255, `TX_COUNT ≤ 256` (textpack `MAX_STRINGS` + the emitted ASSERT); **w2d:** `tx_tab` a word per 2 ids, 17 B as before: even id 58 T, odd ~67 T + 25 T per byte of the skipped stream (hot ≤ ~0.6k T; was 86 T flat); `tx_ptr_hl` (the HL-id entry, no caller) was removed: ids > 255 need a 16-bit `tx_ptr` again),
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
| +33 | `LP_REC` | 9 records × `LR_STRIDE` 9: `LR_HDR` (bit 7 `LR_VISITED`, bits 0–2 count) + 4 × {`LE_KIND` = kind row bits 0–4 \| **`LEK_GOLD` bit 5 (3F-T5: golden boss)** \| `LEK_BRED` bit 6 \| `LEK_RESPAWN` bit 7 (= `EF_RESPAWN`), `LE_HP` exact hp, **depth-scaled since 3F-T5**}. FRESH: count = quota, no entries; VISITED: count = entries (unused entries 0) |

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
goblin, `K_BOSS_D1..8`): 3F replaces the EQUs. **3F-T3: done** — the 18 base + 12
tier rows have real ids (`defs.asm` `K_SPIDER` 9 .. `K_BONE_CALLER` 29, `K_COUNT` 30,
`K_BOSS_D1..8` = the §9.4 bosses; `tools/levelgen.py` `KROWS` asserts the same ids);
their frames / sequences are stand-ins ("Kind rows (3F-T3)" below). Weights
`lp_wt` (bank 3, by kind row, `WT_K_*`, game.md §9.1 W; 30 B).

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
line (`info1.asm`: `item_info`, `dec16`, `info_tab` (D3-9b: `xp_next` gone, it reads bank-2 `xpn_tab`), far1 from
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
| `$BCAD` | `PU_POS` | 2 | 3E-T11 (was the unused `QPIN`): the hero's x, `FL_ROOM` byte at the last `floor_pickup`; x `$FF` = none (`panel_init7`, per level) |
| `$BCAF` | `PU_ARR` | 1 | 3E-T11: != 0 = arrived on a new cell, `BAG FULL` not yet printed there (`pu_add` clears it) |
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
Boot: `JOY_MODE` = `JM_KEYS`, `KEYTAB` = `keytab_defaults` (3E-T1: the bank-6 boot block, was low RAM; macro
`KEYTAB_DEFAULTS`).

**Turn intents (C3-2; game.md §2.3 / §3.1 / §3.5; the FIRE-held cursor / FIRE+↓ bag parts are superseded by C3-2b "ICON MODE" below).** `intent_tick`
(`io.asm`, bank 2) runs every `GS_PLAYING` tick after `input_tick` (ANIM ticks
too) and calls `sample_input`; `read_turn_input` reuses its outputs. UI
events, never a turn: shortcut edges (`PLAYER_SC` vs `SC_OLD`; `SC_ENTER` bit 5
added) — BREAK → `pause_hook` + cancels a FIRE tap (priority over FIRE), I →
`NO BAG YET` (3E-T2: `INTENT` = `IN_BAG`, the bag page via `tpt_intent`), ENTER → `INTENT`, 1–0 → `sel_key`; FIRE held (`FIRE_ST`) — ←/→
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
bag `NO BAG YET` (3E-T2: opens the page instead, no turn); unlearned ability `NOT LEARNED` (throw / shot / cast with
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

**AMMO-COUNT (user 2026-10-29; game.md §8.11 "Ammo slots").** The Warrior's dagger / bow slots (3 / 4) are quick-style: `bar_knight` holds `SLOT_QDAG` / `SLOT_QBOW` (`SLOT_QFOOD` moved `$FB` -> `$F9`, classes `QS_DAG` 3 / `QS_BOW` 4 after the quick ones; `QS_COUNT` stays 3, so the 1st-frame-only rule of `item_icons` `.slow` is unchanged: an ammo slot redraw is a small item like any bar icon: measured whole slot_redraw 10.2k T dagger, 12.2k T bow with two digits, vs 9.7k T for the old 24x16 art; any frame). `slot_redraw`'s `.quick` path -> R6 `qs_draw` -> `qs_ammo` (`icons6.asm`): 16x16 icon (`ic_blit`: `ICONS16_AMMO_DAGGER` / `IT_BOW - IT_BAG_LO`, ink `item_ink` of `IT_DAGGER` / `IT_BOW`) + the count of `DAGGERS` / `ARROWS` via `qs_pd` (units row 19, tens row 18 when non-zero). **Dirty path, no tick cost:** `PD_AMMO` (raised by `abil_ammo`, `ap_take`) used to be cleared by `panel_more`; it now sets `ICON_SH + SLOT_AMMO0 / +1` = `IS_NONE` and `PD_ICONS` (17 B in `panel_more`, only reached when something is dirty). The 24x16 `ICON_DAGGERS` / `ICON_BOW` art is dropped from `icon_tab` (`tools/tiles_convert.py` BAR_ICONS: 10 icons; bank-1 vdata -108 B). Budget (rebased on main + STAFF-BONUS + LOG-FIX, 2026-10-30): R6 -66 B (release 327 -> 261 free; kit 235 -> 191; `lp_wt6` moved before the icons16 data in `r6.asm`, else its page guard padded 26 B), bank 2 -17 B (`panel_more`; `boss2a.asm` moved after `kind_tab`: the 6-B ALIGN pad could not take it; bank 2 free 149 -> 132), bank 3 -6 B (`item_icons`: 19 -> 13), bank 1 +108 B (the 24x16 dagger / bow art dropped from `panel_icons.asm`: free 148 -> 256), bank 7 unchanged. Tests: `tests/abil_ammo.py` AC1-AC5.

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
BRIGHT), the credit (SND-1: the `TX_FT_PRESS` footer is gone; item 5 `SOUND: <state>` in the menu font on rows 21-22 = `menu_snd`, bank 1). Keys: 1–5 (`PLAYER_SC` digits, so a Sinclair half is
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
| `$B310..$B31F` | `ST_FLAGS` | STATUS per slot (game.md §6.4): bits 0-1 HOLD kind (`HOLD_FROZEN` 1 / `ASLEEP` 2 / `STUNNED` 3), 2-3 MIND kind (`MIND_FEAR` 1<<2, `MIND_CONFUSED` 2<<2), 4 POISON, 5 WEAK, 6 HOLD_GUARD (game.md §6.4.1 B1), 7 reserved; 0 = fast path |
| `$B3E0..$B3EF` | `ST_T1` | STMR1: hi nibble HOLD turns, lo MIND turns |
| `$B3F0..$B3FF` | `ST_T2` | STMR2: lo nibble WEAK turns (**POIS1: the hi nibble is unused**; POISON moved to `ST_X`) |
| `$B400..$B40F` | `ST_X` | per slot byte (§6.4 "byte 3"): **POIS1: the POISON turns** (cap `PSN_CAP` 30; a full byte; read by `st_step`, added by `deal_hit`'s `.ps`, zeroed by Cure; slot 0 carries over a descend); the Vampire's fled-once bit can NOT share this byte (POISON uses all 8 bits; the Vampire cannot be poisoned, but the hero/others can): **3F-T9: per-entity once bits live in `E_RCD` bit 7 (`RCD_ONCE`, banked as `LEK_BRED`; the Rabbit Rat's bred bit, the Vampire's fled bit: "3F-T9 Vampire bat form")**. `.kill` does not zero `ST_X` (6 B, not <= 3); spawn / `lp_*` clear it |
| `$B410..$B41F` | `FXQ0` (= `FXQ`) | **D3-5:** FX queue entry 0 (FIFO head; a 16-B descriptor). D3-0's 2 × 8 B could not hold a 16-B descriptor |
| `$B4E0..$B4E5` | `CAST_ROW` | **RANK1:** the rank row of the spell being cast, `RR_STRIDE` 6 B (`RR_MP`, `RR_RANGE`, `RR_DIE`, `RR_BONUS`, `RR_BOUNCE`, `RR_EFFECT`): `abil_load` (bank 3) copies the `ab_rank` row of the highest rank the hero can pay now (auto-downcast, rank 1 floor) at every spell use. Was `RANK_ROWS` (5 rows kept by `rank_sync`, both gone); `$B4E6..$B4FD` is free FONT6 plane hole again |
| `$B4FE` / `$B4FF` | `FX_BUSY` / `FXQ_N` | **D3-5:** bit i = FX track i live or still drawn (0 = FX idle: `turn_done` waits for it) / queued descriptors 0..2 |
| `$B500..$B51F` | `FXT2` | **D3-5:** FX track 2 (32 B). No FONT6 hole is free any more |
| `$BC4A..$BC50` | `TURN_PEND` block (D3-7) | `TURN_PEND` +0 (bit 0 `TP_ACT` ability logic pending, bit 1 `TP_MON` monster phase pending, bit 2 `TP_FIRE` this is the fire tick), `ACT_ABL` +1 (`ABL_*` pending), `ACT_AT` +2 (`TURN_TICK` of the release, fire tick f = `ACT_FIRE_TICK` 2), `MON_AT` +3 (≠ 0: monster phase deferred, its earliest `TURN_TICK` f + 1; it runs once the hero's FX is idle, designer 2026-10-12), `FX_DROP` +4 (T1: descriptors `fx_start` dropped, mod 256; tests assert 0), **T7:** `LOG_TURN` +5 (log drain: bit 0 `LT_SERVED` = `item_log` drew a line since the turn started, bit 1 `LT_HOLD` = `end_turn` holds the next turn), `LOG_PDIR` +6 (T7 review: the input a hold swallowed — `PLAYER_DIR` bits 0-3, bit 7 = `DK_WAIT` — replayed when the key was released during the hold; "Log drain (T7)" under "Projectiles"). Zeroed by `level_reset_new` (`HERO3D..TURN_PEND_END`). Contract under "Projectiles" |
| `$BC41..$BC49` | `HERO3D` | `MP_RG` +0 (MP regen counter), `HERO_RES` +1 (3 B, RES format), `HERO_IMM` +4 (`IMMF_*`; ASSERT = `HERO_RES + KX_IMM`: deal_hit reads hero and kx row alike), `MP_SH` +5 (panel MP as drawn), `STAT_SH` +6 (status icons as drawn), **D3-6a:** `HERO_DEF` +7 (hero DEF = Σ worn-gear DEF; `hero_recalc` owns it, `hero_st_init` no longer sets it), `XP_UP` +8 (1 = `deal_hit` added XP; **D3-9b:** `xp_turn` (end_turn) checks the level-up and clears it), `MP_RG` counts turns to the next +1 MP (frozen while WEAK), `MP_SH` is polled by `icon_poll` (PD_MP → `item_mp`); `$BC4A..$BC50` = `TURN_PEND` (row above); **D3-8:** `HST_DONE` `$BC51` (1 = the hero's status step already ran for the turn being entered), `HELD_T` `$BC52` (held-hero INPUT-tick counter); **D3-8e2: `COMBAT_NOT_BEFORE` `$BC53`** (the §6.5.1 panel gate, "Cast-time output gate" under "Projectiles"); **3E-T2: `PAGE_OPEN` `$BC54`, `PAGE_N` `$BC55`** (the bag page, not zeroed per level); **3E-T13: `PAGE_VERB` `$BC56`, `PAGE_SLOT` `$BC57`**; **3E-T8: `GEAR_MP` `$BC58`, `MP_PER` `$BC59`, `FX_OP` / `FX_ARG` `$BC5A` / `$BC5B`, `PAGE_VLAST` `$BC5C`**; **IC1: `QS_RECHK` `$BC5D`** (not zeroed: a stale bit costs one `item_icons` pass); **3F-T6: `WEAR_PEND` `$BC5E` (a bitfield; cleared by `level_reset_new` separately) — the HERO3D spare is FULL.** `level_reset_new` zeroes `HERO3D..GEAR_MP` (3E-T8: was `..ST_HERO_END`; now incl. `PAGE_*` and `GEAR_MP`) |

`ST_*` arrays: byte = array + slot (`P_MAX_ENT` 16); `ST_FLAGS` / `ST_T1` /
`ST_T2` share page `$B3` (ASSERT). **HERO_CARRY:** slot 0 carries over a
descend; `level_reset` clears slots 1..15 of all four arrays (~1.4k T, once
per level); `level_reset_new` (new_game) also clears slot 0 and `HERO3D`.
`CAST_ROW` is written only by `abil_load` (RANK1; `rank_sync` and the per-ability `RANK_ROWS` are gone: a learn / rank-up only changes `ARANK`). The FX state is
reset by `vis_reset` (`fx_reset`) and `hide_sprites` (`fx_hide`).

**Decorative drip (D3-8b)** (game.md §6.4.1 "Decorative drip", §6.3; `src/drip.asm` bank 2 per
tick, `src/drip7.asm` bank 7 cold). Ambient only: never writes `ROOM_MAP`, the attr shadow or
`RNG_STATE` (own LFSR); not an `FXT*` track (those gate `turn_done` via `FX_BUSY`) but a
one-record overlay stepped in `decor_gate` after render, before `decor_tick`. State
(`level_defs.asm`, bank 2 `$BC01..$BC0B`, test-observable):

| Addr | Symbol | Meaning |
|---|---|---|
| `$BC01` | `DRIP_ST` | `DRS_IDLE` 0 (waiting) / `DRS_FORM` 1 (old `T_DRIP1` at the source, 16 ticks) / `DRS_DROP` 2 (old `T_DRIP2`, 3 ticks) / `DRS_FALL` 3 (the drop alone, 1 cell per tick) |
| `$BC02` | `DRIP_T` | first-frame, non-`TP_FIRE` ticks to the next step (>= 1); IDLE gap 24 + rnd & 63 |
| `$BC03` / `$BC04` | `DRIP_COL` / `DRIP_ROW` | the drop's (current / last) cell (`ld bc, (DRIP_COL)`); `drip_room` sets `DRIP_ROW` $FF (no drop formed in this room yet) |
| `$BC05` | `DRIP_DRAWN` | 1 = its glyph is on the bank-5 screen (attr `DRIP_ATTR` `$05` there only; erase = `erase_rect`) |
| `$BC06` | `DRIP_N` | sources in `CUR_ROOM` (0..2; 0 = no drip: `drip_tick` costs 45 T incl. the call) |
| `$BC07` | `DRIP_RND` | 8-bit Galois LFSR ($1D), seeded per room from `RD_SEED` lo ^ hi (never 0) |
| `$BC08..$BC0B` | `DRIP_SRC` | 2 x (col, row) |

Sources (`drip_room`, the tail of `vis_room_sync` / `vis_reset`, far7): the B3B-13b placement
(`dg_drips`, removed in D3-7 T6) without its structural ring scan — D1..D8 1, 2, 2, 1, 2, 2, 1, 0
(PROTO depth 0: none), <= 8 tries each of (col = rnd & 31, storey row = rnd & 3 if < 3, storey =
rnd bit 0): T_AIR on map row >= 1, above `T_PLAT` / `T_BRICK` / `T_WALLF`, below T_AIR, >= 6 cols
apart. Rules: a drop is drawn only into a T_AIR cell no RLIST body footprint / drawn FX covers
(`cell_occ`, shared with `decor_tick`); a covered drawn drop is forgotten that tick and its cell
`queue_damage`d (the next render restores it and repairs the body); a drop with a body / FX or a
non-air cell below, or on row 17, lands (erased). A body / FX moving onto a drawn drop overlaps
it for <= 1 tick (<= 2 across a `TP_FIRE` tick). Does nothing on the `TP_FIRE` tick (not even the
cover test); holds (cover test only) on ticks already in their 2nd frame (like `decor_tick`), so it
never lengthens a heavy tick; frozen in ICON MODE. `hide_sprites` -> `drip_hide` (erase, `DRIP_N`
0). Cost (`tests/drip.py` T / TL): idle room <= 3.0k T, mean 0.5k; next to the loaded budget
fights (4 monsters, 3 live FX tracks: two `cell_occ` passes per fall step) up to ~4.8k T in a
first-frame tick; every scenario's worst tick stays within its cap (TL). Layering vs D3-8d marks (built): `cell_occ` reports a drawn
mark's cell as covered (`MK_MAP`), so a drop never forms in, falls into or is drawn on a mark (it lands above it); a mark drawn
onto the drop's cell forgets the drop (`DRIP_DRAWN` 0, IDLE, gap `DRIP_GAP`) and overwrites the cell whole. D3-11 numbers: still to
do (count as covering cells or treat the drop like an FX).

**Status marks (D3-8d)** (game.md §6.4.1 V1-V3 "On-body cues"; `src/mark.asm` bank 2 per tick,
`src/mark7.asm` bank 7). One 8×8 glyph above every visible HOLD / MIND body (hero and monsters;
HOLD > MIND; POISON / WEAK: panel only): col = `(E_PX + 4) / 8 + (KT_BW − 1) / 2`, row = `E_PY / 8 − 1`;
none when `E_PY / 8` is a storey top row (`KT_MOD9` 0: a flyer at y = 9s) or the slot is not visible
(`R_VIS` 0); waits while a body / FX / another mark covers the cell. Glyph g (1..5 = FROZEN, ASLEEP,
STUNNED = the HOLD kind; CONFUSED 4, FEAR 5) = `status_icons[g − 1]` (frame A), attr =
`status_icons_attr[g − 1]` (`$45` / `$41` / `$07` / `$43` / `$42`); drawn as the map cell's tile glyph
OR the 8 mark lines (decor / ladder under it: accepted clash), attr on the bank-5 screen only (the
attr shadow keeps the map's; an erase is `erase_rect`). **Frame B is derived, no new art** (user
2026-10-14: frame A shifted up 1 px; manager 2026-10-14: a BRIGHT toggle for the full-height glyphs):
`MK_GLYPHS` keeps a 0 byte before each glyph and after the last, so the shift is a −1 source offset;
a glyph with a blank bottom row (FROZEN, CONFUSED, FEAR) rests one line down and rises to its panel
rows (lossless); one using all 8 rows (ASLEEP, STUNNED — the shift would clip ASLEEP's whole Z top bar)
keeps its lines and frame B toggles BRIGHT (attr XOR `MK_BRIGHT` $40: ASLEEP $41 ↔ $01, STUNNED $07 ↔
$47). Phase `(TICK_COUNTER + 3 × slot) & 8` (8 ticks A, 8 ticks B); `ANIM_FREEZE` = frame A.

| Where | Symbol | Meaning |
|---|---|---|
| SLOTREC +14 | `R_MK` | the mark as drawn: bits 0-2 g (0 = none), bit 3 frame B (`MK_FRAME`), bits 4-5 row >> 3 (`MK_THIRD`) |
| SLOTREC +15 | `R_MKLO` | its cell's low byte (row & 7) << 5 \| col (= the screen / ROOM_MAP / attr low byte) |
| `$BC0C` | `MK_N` | marks drawn (0: `cell_occ` skips the map test) |
| `$BC0D` | `MK_RR` | RLIST index the next pass starts at (the first slot denied an op in the last pass) |
| `$BC0E` | `MK_OPS` | ops done by the last `mark_tick` (draw / erase / in-place redraw / a draw attempt that found its cell covered; ≤ `MK_OPS_MAX`; test-observable; 0 on fire / 2nd-frame / idle ticks). **Forgets are not ops**: `mk_forget` (a damaged or covered mark dropped + its cell queued, ~1.5k T each incl. the far7) is uncapped and uncounted — one per drawn mark this render touched |
| `$BC0F` | `MK_LEFT` | ops left in this `mark_tick` (`MK_OPS_MAX` 2) |
| `$5F00..$5F47` | `MK_MAP` | 1 bit per playfield cell, a mark is drawn there: byte `row × 4 + col / 8`, bit `7 − col & 7` |
| `$5F48..$5F75` | `MK_GLYPHS` | 5 × (0, A0..A7) + a final 0 (stride `MK_G_STRIDE` 9) |
| `$5F76..$5F7A` | `MK_ATTRS` | the 5 mark attrs |
| `$5F7B..$5F8A` | `MK_WAIT` | per slot: 1 = its last draw attempt found the cell covered (the retry is gated, below) |
| `$5F8B` | `MK_AX` | `mk_draw`'s attr XOR (frame B BRIGHT) |
| bank-2 image | `mk_sl` / `mk_dlo` / `mk_des` / `mk_den` | the pass's scratch (slot, wanted `R_MKLO` / `R_MK`, first denied RLIST index) |

`MK_RAM` (`$5F00..$5F8B`, 140 B) is runtime only (bank 5, the BASIC area above `PF_RAM`: garbage at
boot) and is zeroed + refilled (`copy_virt3` from the bank-1 `vdata`) by **`mk_room`** on every
`vis_reset` / `vis_room_sync` (their far7 tail is now **`vis_tail`** = `mk_room` + `drip_room`): every
`R_MK` / `R_MKLO` 0, `MK_N` / `MK_RR` 0 — "room change clears all marks", the next passes rebuild them
from `ST_FLAGS`. It is safe only because `mk_room` first runs after `boot` has moved SP to `$BF00`:
`CLEAR 24575` leaves the BASIC machine stack just under `$5FFF`, i.e. on top of `MK_RAM`, until then.
`hide_sprites` → **`mk_hide`** first (erases every drawn mark before the scroll).

Per tick (`decor_gate`, after render, **before** `drip_tick` / `decor_tick`, frozen in ICON MODE):
`mark_tick` returns at once on a `TP_FIRE` tick (`MK_OPS` 0, ~40 T) and in a 2nd-frame tick (~70 T: no
op ever lengthens a heavy tick); the first-frame gate is tested **once, at the entry** (a pass that
crosses the frame boundary still finishes its ≤ 2 ops + forgets). Then it returns when no slot has
HOLD / MIND and `MK_N` = 0 (a 16-B OR, ~0.45k T). Else a pass over the whole RLIST from `MK_RR`: a slot
with HOLD / MIND or a drawn mark → `mk_slot`: the wanted mark; a drawn mark whose cell this render's
`DMG_LIST` touches (a body / FX erased or drawn over it) is forgotten (far7 `mk_forget`: `R_MK` 0, map
bit clear, `MK_N` − 1; a body / FX on the cell now → `queue_damage`, the next render restores it and
repairs what covers it) — **this damage test runs for every slot, also after the ops ran out**;
wanted ≠ drawn and an op left → far7 **`mk_op`**: one op (`MK_LEFT` − 1, `MK_OPS` + 1): none wanted →
erase; same cell → redraw in place unless a body / FX came over it (→ forget); moved → erase, then
draw if an op is left; none drawn → draw if `cell_occ` (bodies, FX, `MK_MAP`) is clear, else
`MK_WAIT` = 1 (the op is spent either way). A waiting mark retries only on its phase tick
(`(TICK + 3 × slot) & 7` = 0) or when this render's damage touches its cell (the cover left), so it
never burns an op a tick. No op left → the slot is denied; `MK_RR` = the first denied index. **Every
erase tests the cover first** (`mk_erase`: a body / FX on the cell → `queue_damage`, not
`erase_rect`): a body that came over a mark in a tick whose damage test did not run (a fire or
2nd-frame tick) keeps its pixels when the mark is later cleared, moved or swept. Every 8th tick with
`MK_N` ≠ 0, far7 `mk_sweep` erases the marks of slots with `R_VIS` 0 (out of RLIST). A 2nd-frame tick
skips the damage test: until its next toggle (≤ 8 ticks; the in-place redraw tests the cover first) a
mark a heavy render wiped stays missing, and mark pixels a body drawn over it in such a tick keeps
showing through that body's mask stay inside its cell (the toggle's cover test then forgets the mark
and queues the cell). Ops are events (apply, clear, a cell step, the 8-tick toggle) in a first-frame
tick, hence bank 7 (~0.25k T a far7) — the documented exception in conventions "Bank-7 cold code";
the per-tick pass stays in bank 2.

**V1** (`anim.asm` `idle_phase`): a HOLD body's idle phase is 0 (the idle loop stops on its first
frame; flyers' move phase too) and resumes when HOLD clears. **V3** (`combat3.asm` `dh_status`, after
the status write): an ASLEEP that lands with `E_REACT` 0 (no hit reaction pending: the typeless apply
of 3E's Sleep scroll / GAS) sets `E_FLT` = `SLEEP_FLASH` (1) / `E_FLA` = `SLEEP_FLASH_ATTR` `$4F`
(bright white on blue: every kind attr and tint has paper 0, so it differs from the body and from the
`$41` tint that follows); a damaging hit keeps its own impact as the cue (deal_hit sets the reaction
first, so no flash today).

Tests: `tests/marks.py` (S every mark status on a Goblin and on the hero: cell / glyph / attr / frame
A → B (1-px shift or BRIGHT); P priority; C clear; D death; G storey top / covered by a body; K a body
over a mark in heavy ticks, then the clear keeps its pixels; Q saturated ops still forget a damaged
mark, a waiting mark retries 1 tick in 8; F follow; X room exit A → B; R the drip (never on a mark, a
mark wins the hanging drop's cell); H pose hold (Bat, hero); V the V3 flash on the screen; B budget
"mkmix" ≤ `CAP` with ≤ 2 ops / tick, "lcastf" no op on a fire tick). `tests/game.py` `bg_mismatch`
accepts the drawn mark cells (`game_lib.mark_cells`).

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
ASSERT one page), `K_MAX` 32 rows × `KX_STRIDE` **8** B = `KX_LEN` **256 B** (MEM-1; was 6 / 192): `KX_RES`
+0 (3 B), `KX_IMM` +3, `KX_XP` +4 (KXP, game.md §4.1), `KX_DEF` +5 (0 in 3D,
§11.4), `KX_MELEE` +6..+7 (**3F-T2**: the kind's melee hit as `deal_hit`'s {C, E} — `DTY_*` | `EFX_*` << 4, chance << 4 | turns; was the separate 18-B bank-3 `kx_melee` table, folded into the old `KX_SPARE`: −20 B bank 3). Row = `kx_tab + kind * 8` (`ld h, kx_tab >> 8`, L = kind × 8: three `add a, a`, 1 B and 4 T cheaper per site than the old ×6). Read
by bank-3 combat code only. Reserved as zeros (`DS`); data rows in D3-1.
**L-RELIEF:** `dg_bad` (decor_gen.asm's 64-B, 64-aligned `dg_ring` lookup,
generated by `tools/decorgen.py --asm-bad` → `src/dg_bad3.asm`) sits right
after it at `$C100` (= `$C000` + `KX_LEN`; MEM-1, was `$C0C0`: aligned by construction, ASSERTed
in `combat_data3.asm`; the other D3-1 tables follow at `$C140`; D3-9b: `xpn_tab` moved to bank 2, `lvlup_tab` / `lvl_step_tab` deleted).
It was an `ALIGN 64` in `decor_gen.asm` whose 0..63 B pad moved with every
byte of bank-3 code before it.

**Combat core (D3-6a, `src/combat3.asm`, bank 3, after `turn3.asm`).**
`hit_roll` (IX attacker, A target slot, B signed to-hit modifier → A 1/0 +
Z; one d20; held target = eva 0) and `deal_hit` (IX attacker, A target slot,
B dmg rolled, C = `DTY_*` | `DH_NODEF` (bit 3) | `EFX_*` << 4 | `DH_HEAL`
(bit 7), E = effect param in the `RK_EFFECT` status format (hi nibble 1-in-N
chance, 0 = always; lo nibble turns) → L = HP lost; clobbers all but IX).
EQUs in `combat_defs.asm`. Data: `kx_tab` `KX_MELEE` (3F-T2; was `kx_melee`, per kind {C, E}:
the melee hit's type + on-hit effect; Ghost DRAIN + CONFUSED
4 at 1 in 4), `efx_tab` (per effect id 1..7, 6 B: immunity bit, STATUS mask
/ value, timer field, hero line, monster suffix). Scratch `dh_*` (13 B) is
bank-3 RAM next to the code (not re-entrant). Monster lines go through
`impact_line` codes `MSG_M_UNAFF` 7 .. `MSG_M_THAW` 14 (lowram `imp_pre` /
`imp_post` +16 B). `do_attack` is now hit_roll → 1dN + bonus → deal_hit.
D3-8 added the BOSS rules and WEAK's penalties ("Status effects (D3-8)"
below). Bank 3: 1,589 B free after D3-6a (was 2,324;
+735: `combat3.asm` ~765 incl. 81 B tables + 13 B scratch, `do_attack` −30);
low RAM spare 384 (was 400). Test: `tests/combat3.py` C0–C10.

**Projectiles (D3-6b, `src/proj3.asm`, bank 3, after `combat3.asm`).**
`proj_fire` (IX = caster, A = `ABL_*` with a projectile, HL = its 6-B rank
row (`CAST_ROW` / `ab_rank` / `ab_ammo`, `RK_*`), E = `FXD_DELAY`; LIVE_LIST
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
descriptor + candidate list `$5E00..$5E63` (**D3-8e2**: + `pf_ftick` right after `pf_lost` (one word store: `pf_strike`'s first-target record = HP lost + the impact tick), the block after it moved up 1; **D3-8e**: + `pf_dmc` (word: die, rng mask), `pf_tb` (`pf_tick`'s base), `pf_slim` / `pf_acc` (the accept's strike budget / mode), `pf_part` (0 / `PFP_MID` parked / `PFP_DONE` stopped), − `pf_cok` (the caster starts DONE instead); T7: + `pf_miss`, was `..$5E5C`; T7 `..$5E5D`), `PF_ROWF` `$5EE0..$5EFF` (the
flight row's flags: bit 0 TF_SOLID, bit 2 edge, bits 3-7 the count of
candidates not yet DONE on the col (`PFR_BODY1` 8: `pf_cands` +1, `pf_bdone` −1
when a body is struck / tested, `pf_reverse` +1 back; D3-8 review: was a
candidate bit, so cols of struck bodies kept calling `pf_bodies`, ~0.9k T a
cell; **D3-8 review 2**: a body struck dead on the pierce path gets candidate
flag bit 7 `PFCF_DEAD` and stays DONE through every later reversal, so its
cols stay plain; `pf_bodies` stops scanning once the col's count is used up;
`pf_cands` clamps a body's x1 to col 31, so no count can wrap past
`PF_ROWF`'s page end into `pf_left`) — the fast-forward over plain cells); **D3-7: `ABIL_DESC` `$5E68..$5E77`** (D3-8e: moved up from `$5E60`, the `pf_*` block grew; 16 B: the `ab_def` row (`ABD_*`, 10 B) then `ABIL_RK` the rank row (`RK_*`, 6 B: `ab_rank` at the hero's rank, or `ab_ammo`), filled by `abil_load` (bank 3) for the bank-7 ability code, which cannot read bank 3; D3-7 T4: also the scratch FX descriptor of `melee_bonk` (a melee turn has no ability pending); ASSERTed clear of the `pf_*` block and `PF_ROWF`; `$5E64..$5E67` / `$5E7A..$5EDF` stay free); **D3-7 T5: `ABIL_TGT` `$5E78..$5E79`** (D3-8e; was `$5E70`) (word: the power attack's target slot mask, bit s = slot s, written by `abil_melee` at the accept, read by `power_fire` on the fire tick — no second scan; ASSERTed below `PF_ROWF`). Contended, as is the bank-3 code: measured 10–30k T a typical
cast, worst seen ~66k T (Lightning r3 through 4 bodies, 3 passes, deal_hit
messages; D3-8 review: ~64k in `tests/proj3.py` with the `PF_ROWF` body count; D3-8 review 2: the
adversarial fuzz case #208, Lightning r2 with a reflecting Ghost, 4 passes, 8 hits: 94.8k → 65.6k in `tests/proj3.py` P10); D3-7 must budget the cast tick. Not done (bank 3 was full, 30 B
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
- **D3-8e: the cast is split between the input tick and the fire tick.**
  `act_begin` (accepted, lead col 1..30) far3s **`proj_pre`** (`rank3.asm`;
  A = `ABL_*`, DE = the rank row: `CAST_ROW` for spells, `ABIL_RK` for the
  dagger / bow) → **`proj_part`**: `proj_prep` (the set-up + `pf_cands`,
  ~10k T; `pf_prep` = `ABL_*` + 1, bank-3 byte) then the walk with E =
  `FXD_DELAY` = `ACT_FIRE_TICK` − `TURN_TICK` until it struck `PF_PRE_HITS` 8
  bodies (parks at a `.walk` boundary: `pf_part` = `PFP_MID`) or stopped
  (`PFP_DONE`: the result, burst and FX wait). At the release `proj_rel` sees
  `pf_prep` = A + 1 → **`proj_go`** (E = 0): the rest of the walk (or
  straight to the result), the burst, `fx_start`; any other `pf_prep` (a test
  poking `TURN_PEND`, another ability) → the whole `proj_fire`. Valid because
  nothing moves between the accept and the release (monster phase deferred,
  `LIVE_LIST` not rebuilt); `pf_tick`'s base `pf_tb` = `TURN_TICK` +
  `FXD_DELAY` + 1 is the release tick on both ticks, so every `E_REACTAT` /
  `pf_itick` / RNG draw equals the one-shot cast (`tests/proj3.py` P11 split
  cases). Seen by the player (D3-8e2): nothing early — the panel gate and
  the held tint below. Accept cost: ~10k T set-up + ~3.5k T a strike, up
  to ~60k T with 8 message-bearing strikes (input tick: no render-heavy
  work besides it); `level_reset` clears `pf_prep` (no set-up survives a
  level change).
- **Cast-time output gate (D3-8e2, game.md §6.5.1 "logic early, visible
  output at impact").** `pf_strike` records the first body's impact tick
  in `pf_ftick` (with `pf_lost`, one word store). `act_begin`, after
  `proj_pre`: `COMBAT_NOT_BEFORE` = 0 when `pf_tgt` = `$FF` (nothing
  struck: a miss sets no gate), else min(`pf_ftick`, `ACT_FIRE_TICK` +
  `CNB_MAX` 8) (the bound: a long flight). The play loop skips
  `panel_tick` (the whole queue: log, `TGT_NAME` / `TGT_HP`, HP bar, the
  rest — non-combat items lose a few ticks) in ANIM ticks with `TURN_TICK`
  ≤ the gate: a panel item drawn in tick t is presented at t + 1, the
  impact `anim_tick` computes in tick t is rendered at t + 1 and presented
  at t + 2 (RENDER_FIRST), so from t + 1 both show together. Lines are
  still pushed at resolve time (ring / `LT_HOLD` unchanged) and drain at
  the normal rate after it. `act_pend`'s log wait counts `LOG_WAIT_MAX`
  from max(`MON_AT`, the gate). `end_turn` clears it with `TURN_TICK`
  (`level_reset_new` zeroes it with `HERO3D..ST_HERO_END`). **Tints:**
  `render` keeps a body's last attr shown with no reaction pending
  (`R_TINT`) while its `E_REACT` is pending (1..$7F; a flash still wins):
  a FROZEN / CONFUSED tint applied at the accept appears at the impact, a
  killed body's tint (`deal_hit` clears its STATUS) stays until its DEATH
  starts; +13 B, ~45 T a drawn slot. Hero death needs no gate (`end_turn`
  sets `GS_DEAD` after `turn_done`, i.e. after the reactions). Not gated:
  lines pushed at the release by strikes past `PF_PRE_HITS` or a
  Firebolt burst with no accept strike (§6.5.1 accepts 1–2 ticks early on
  later targets). Tests: `tests/cast_gate.py` T1–T6.
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
  message, no turn — unlearned `TX_NOT_LEARNED`, `MP` < `CAST_ROW`'s
  `RR_MP` (RANK1: the highest rank affordable, so the rank-1 cost is the threshold) `TX_NO_MANA`, mid-ladder `TX_NO_TARGET`; `act_begin`'s lead col
  0 / 31: L = 0, no message. Accept: `act_begin`, `MP` −= `RR_MP`,
  `PANEL_DIRTY` |= `PD_MP` (`PD_MP_BIT` 1; no MP item drawn yet, the panel
  clears it), `start_seq` of the `abl_seq` row (`wz_cast`), the hero flashes
  `ABIL_DESC + ABD_AT1` (the spell ink) for `SPELL_FLASH` 5 ticks (the whole
  cast). **`spell_fire`** (the release): far3 **`proj_rel`** (bank 3,
  `rank3.asm`: A = `ABL_*`, DE = the 6-B rank row → `proj_fire` with HL = DE,
  E = 0; far3 takes HL as its target) with `CAST_ROW`; Drain Life
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
  R halves, IMMF_STUN / HOLD_GUARD refuse; the §6.4 BOSS halving comes with
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
  at most `LOG_WAIT_MAX` 8 ticks past `MON_AT` (D3-8e2: past max(`MON_AT`, `COMBAT_NOT_BEFORE`)); it draws NOTHING itself —
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
  **D3-8e scenarios "fzcast" / "fzcast2"** (gated): the ROOM_CAP-legal worst
  of a 2M-layout model search (box_free-disjoint bodies, no ladder bodies):
  a SHOCK-reflecting Ghost + 2 Bats + a Rat / Slime stacked between it and
  a wall, Lightning ping-pong through them and the caster (16 strikes, 99 HP
  each). Before D3-8e "fzcast" took **148.1k T** on its fire tick (over the
  2-frame budget: proj_fire ~97k + a ~70k render of the stack over the
  caster); now (the split cast below) "fzcast" fire tick **103.7k**, cast
  class max 103.7k, ordinary max (the input tick) 101.6k; "fzcast2" fire
  89.8k, cast max 111.2k, ordinary max 113.2k; the top 24 search geometries
  through the real cast: every tick ≤ 113.2k. The other cast scenarios
  after D3-8e (cast-class max / ordinary max): "lcast" 93.9k / 93.0k (fire
  tick 47.1k, was 98.2k), "lcastf" 93.8k / 99.7k, "lcasts" 93.9k / 96.7k
  (was 111.8k), "advcast" 81.7k / 92.0k (fire 73.3k, was 126.0k), "fcast"
  78.1k / 110.2k (its whole cast now runs on the input tick), "wcast4"
  118.6k / 120.1k, "acast" 80.0k / 82.9k.
Test: `tests/proj3.py` P0–P8
(the game.md §6.1 / §6.3 table at every rank + a 120-case fuzz vs a Python
model of the rules); P9 the split turn (`TURN_TICK` shift of `pf_itick` /
`E_REACTAT` / `set_reaction_at`, the `act_begin` / `act_fire` lead-col guard,
`FX_DROP`).

**Text ids:** ids 0..255 (`TX_COUNT` ≤ 256); w2d: `tx_tab` is sparse (a word
per 2 ids, one page) and `tx_ptr_hl` is gone — ids > 255 need a 16-bit `tx_ptr` (see "Text").

**Class FX kinds (D3-4)** (`src/frames.asm`, `defs.asm`): the projectile /
impact sprites (game.md §6.1–6.3) are two render-only kinds at the top of the
kind ids, `K_FXW` 30 (= `K_FX_BASE` + `K_KNIGHT`) and `K_FXM` 31 (=
`K_FX_BASE` + `K_WIZARD`); no entity ever has them, only their generation
units are set (3F-T2: R6 `gu_tab` units 30 / 31; was `KT_FID0` / `KT_FCNT`, `KROWFX`). `start_game` generates the hero's unit and then
unit `HERO_KIND + K_FX_BASE` (R6 `pool_hero`) above the select mark, so the pool holds
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

**Status effects (D3-8)** (game.md §6.4, §2.2, §2.3, §9.1). State = the
`ST_FLAGS` / `ST_T1` / `ST_T2` arrays only (the R3 homes above; invariant: a
group bit / kind set ⇔ its timer ≠ 0; POISON's timer is the `ST_X` byte since POIS1); the tint and the panel icons
are derived from them, never stored.
- **Apply:** `deal_hit` (bank 3, D3-6a) as before, plus the **boss flag =
  `KX_IMM` bit 7** (`IMMF_BOSS_BIT`; plan's "3rd `kind_tab` page" not
  needed: every reader is bank-3 `deal_hit`): a boss ORs `IMMF_SLEEP |
  IMMF_FEAR` into its immunity and halves HOLD / MIND durations after the R
  halving (0 = none; POISON / WEAK full). No kind sets it before 3F. WEAK
  (hero only): `hit_roll` atk −2 / eva −1 (signed), `deal_hit` dmg −1 on the DEF
  path only (D3-8f, game.md §6.4.2 R1: his DEF-path hits count DEF + 1, i.e.
  max(1, roll × mult × resist − DEF − 1), after Power Strike ×2; spells /
  Drain / his own bounced bolt carry `DH_NODEF`: unreduced). **Check order
  (D3-8f, R2):** chance roll → (1) immunity mask (+ boss SLEEP / FEAR) →
  `IS UNAFFECTED`, stop → (2) R halves → (3) boss halves → 0: silent →
  self-Frost 1 → (4) held body / HOLD_GUARD: silent;
  "no MP regen": D3-9b `xp_turn` freezes `MP_RG` while slot 0 is WEAK. **3E-T9:** the hunger
  WEAK is `ST_FLAGS` slot 0 bit 7 `STS_HWEAK` (no timer / icon / tint; Cure keeps it), synced to
  `HSTAGE == HS_WEAK` by `hunger_turn`; every WEAK test masks `STS_WEAK | STS_HWEAK` (not
  cumulative): `hit_roll` ×2, `deal_hit`, `h_jump`; `xp_turn` reads `MP_HOLD` instead ("3E-T9").
- **Step:** `st_step` (bank 7, `src/status7.asm`; IX = entity, A = slot → L =
  1 held): POISON −1 (new value ≡ 0 mod 3 incl. 0: −1 HP, never below 1, a
  sleeper wakes), WEAK / MIND −1, HOLD −1 + skip (FROZEN / STUNNED ending → HOLD_GUARD),
  else a monster's HOLD_GUARD clears (its own action cannot hold it); the
  hero's clears AFTER his action (D3-8f, game.md §6.4 step 4): `turn_input`
  after a used non-ability turn, `act_pend` before the deferred monster phase
  of an ability turn (so his own bounced / reflected Frost is refused on the
  guarded turn); a held turn keeps it; the hero's end lines / `MSG_M_WAKE` via `st_msg`.
  **Monsters:** `resolve_monsters` (bank 3) tests `ST_FLAGS[slot]` (0 = the
  fast path, ~50 T) and far7s **`mon_status`** (A = slot, IX kept → L = 1
  the action is spent): the step; then on a turn it acts (KT_PERIOD 2 rests
  on odd turns) FEAR = a step away (x), cornered → far3 `attack_if_reach`;
  CONFUSED = 1 in 2 (`rng_mod 2` = 0) a random step (walkers dx ±1, flyers
  dx / dy −1..1 through far3 `clamp_band`), else `ai_monster`. **Hero:**
  `turn_input` runs `st_step` at the start of his phase, ONCE per turn
  (`HST_DONE`: an illegal try costs no turn and does not step again; cleared
  when a turn is spent); held → the turn is a Wait without search
  (`build_live`, `ACT_SLOT` / `CLIMB_BLK` 0, the monster phase as usual).
  While HOLD is set `turn_input` ignores input (`INTENT` / `DN_COMMIT`
  dropped; Pause works) and starts that Wait on the `HELD_WAIT` (3)rd INPUT
  tick (`HELD_T`): a turn every 4 ticks with nothing moving (measured); the
  held turn sets `NEED_RELEASE` like any turn (a key held through the hold
  must be released).
- **CONFUSED hero** (`conf_roll`: `rng_mod 3` = 0, drawn only when
  CONFUSED): `h_walk` (tpt_intent's walk / bump along the facing; not
  mid-ladder), `h_jump`, and `use_icon`'s facing slots (melee, abilities but the
  Warrior's Whirlwind (D3-8f R4: never rolls; no target = NO TARGET), daggers,
  bow): turn around, act the other way; refused → `h_stumble`
  (`YOU STUMBLE`, CF / L = 1: the turn is spent). Turnarounds, climbs, waits,
  potions never roll. **FEAR hero** (`fear_chk`): bump attack (try_horizontal;
  the line once per press via `LOCK_SHOWN`), the melee icon with a target,
  Power Strike / Whirlwind → `YOU ARE TOO AFRAID TO FIGHT!`, no turn.
  **WEAK hero:** `h_jump` refuses (no turn, no line: no string exists).
- **Tint:** `render` (bank 2, `anim.asm`) — no `E_FLT` flash → `ST_FLAGS
  [ANIM_SLOT] & STS_TINTED` → `st_tint` (`st_tint_tab`: CONFUSED $43,
  FROZEN $45, ASLEEP $41, STUNNED $07; = the kind's `KT_ATTR` → XOR $40),
  else `KT_ATTR`. The existing `R_ATTR` / `R_DATTR` compare re-stamps the
  footprint once (DIRTY_ATTR). +57 T per drawn slot without a tint.
- **Panel icons:** `st_sig` (bank 2, `icons.asm`): the first two of HOLD >
  MIND > POISON > WEAK as icon index + 1 (low nibble col 30, high col 31;
  `SI_*`); `icon_poll` compares it with `STAT_SH` → `PD_ICONS`;
  `item_icons` (bank 3) stores it and far1s **`st_icons_draw`** (bank 1,
  `src/stat1.asm`): row 21 cols 30-31, the `status_icons` glyph + attr read
  in place (virtual + `TEXT_DISP`), blank = bitmap 0 / attr 0, `pmark_rect`.
  The 3E ammo text must end at col 28 (game.md §6.4).
- **Not here (3E / 3F):** typeless sources (scrolls, GAS / DART traps)
  need an apply entry without damage (factor `dh_status`'s `.sure` part);
  Cure; the Vampire's fled-once bit (`ST_X`); a confused / fearful
  monster never shoots (no shooter yet). Banked monsters (LP room records)
  lose their status; admitted followers keep it. HOLD / FEAR bodies are not
  follow candidates (`follow_select`, bank 7, D3-8f R3); CONFUSED ones are.
Tests: `tests/status.py` (30 checks: F Frost = 2 skipped actions + tint, H
held hero cadence / icons / tint, W sleeper wakes (spell, poison), G
HOLD_GUARD, P poison schedule / floor 1, C confused reversal / stumble /
confused monster, B boss halving / immunity, X FEAR / WEAK, D the D3-8f
rulings: WEAK on the DEF path, R2 order / silence, the hero's guard after his
action, confused Whirlwind, HOLD / FEAR not following); `tests/world.py`
W16's HERO_CARRY now pokes a valid WEAK 15 (the step runs on every turn).

**Status icons (D3-4, data only; D3-8 draws them):** `status_icons` in the
bank-1 `vdata` block (after `orn_glyphs`; read through `copy_virt3`), 7 × 8 B
glyphs in the order FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR, POISON, WEAK
(= `status_icons + 8i`), then `status_icons_attr` 7 B ($45, $41, $07, $43,
$42, $44, $42); 63 B ASSERTed (`assets/gfx/sprites/status_icons.asm`,
generated by `tools/svg_sprites.py` from the D3-3 sheet). **D3-8d:** glyphs / attrs 0..4 are
also the status marks' frame A + attr (`mk_room` copies them to `MK_GLYPHS` / `MK_ATTRS`, bank 5).

**Headroom after D3-8d (status cues)** (build DISPLAY, both `DEBUG_KIT` builds): bank 3 **359 B**
free (−21); bank 7 code 5,029 B, **1,115 B** free (kit 5,079 / 1,065; −469); bank 2 image
`$8000..$A49C` 9,372 B, **356 B to `FRT` + 165 B pad** (−460 `mark.asm` after `kind_tab`'s arrays, −31
before `kind_tab`; `kind_tab` stays `$A100`); bank 1, low RAM, `HOT_COPY` unchanged (`vis_room_sync`'s
far7 target is `vis_tail` now: 0 B). New RAM: `R_MK` / `R_MKLO` (SLOTREC +14 / +15), `MK_N..MK_LEFT`
`$BC0C..$BC0F`, `MK_RAM` `$5F00..$5F8B` (bank 5, runtime only). Budget (`tests/budget.py`, same
host, vs main): see the plan row D3-8d.

**Headroom after L-RELIEF (bank-3 relief)** (build DISPLAY, `-DDEBUG_KIT=0`):
bank 3 **376 B** free (+353; no `ALIGN` pad left: `dg_bad` at `$C0C0`); bank
7 code 4,195 B, **1,949 B** free (kit 4,245 / 1,899); bank 2, bank 1, low
RAM unchanged. Per-tick paths untouched (room exit / fall only; `hero_fall`'s
far3 → far7 costs +12 T (far7 = ld c / jr farb)).

**Headroom after D3-8e2 (cast-time output gate, merged with main / D3-8c)**
(build DISPLAY, `-DDEBUG_KIT=0`): bank 3 **23 B** free (the `dg_bad` ALIGN
pad down to 3 B); bank 7 code 3,841 B, **2,303 B** free (kit 3,891 /
2,253); bank 2 image +20 B (`render`'s held tint 13, the panel gate 7;
`kind_tab` pad 166 → 146 B, 1,072 B to `FRT`); `HOT_COPY` spare 41 B,
bank 1 689 B, low RAM unchanged. New RAM: `COMBAT_NOT_BEFORE` `$BC53`,
`pf_ftick` (PF_RAM, the `pf_*` block now `$5E00..$5E63`), `SLOTREC`
`R_TINT` +13.

**Headroom after D3-8e (budget fuzz)** (build DISPLAY, `-DDEBUG_KIT=0`):
bank 3 **77 B** free (−158, see the bank-3 row); bank 7 code 3,816 B,
**2,328 B** free (kit 3,866 / 2,278; +26); bank 2 image +1 B (`probe_act_prep`; `kind_tab` pad 167 → 166 B); bank 1, low RAM
unchanged; `PF_RAM`: the `pf_*` block `$5E00..$5E62`, `ABIL_DESC` /
`ABIL_TGT` moved to `$5E68` / `$5E78`. proj_fire cuts (one-shot, `tests/
proj3.py` P11 worst ~102k → ~93k T incl. the ~3k stub): `set_reaction_at` takes the strike's
tick (`dh_rtick`), `pf_strike` reaches the target through `dh_tix` (no
`ent_ix`, no `pf_react`), the caster starts DONE (no caster test per body),
`pf_bdone` inline, runs of plain cells entered in bulk, the die's rng mask
and `pf_tick`'s base once a cast; then the split (above).

**Headroom after the D3-8 review 2 fix pass** (build DISPLAY, `-DDEBUG_KIT=0`):
bank 3 **235 B** free (−123, see the bank-3 row); bank 7 code 3,790 B,
**2,354 B** free (kit 3,840 / 2,304; +9); bank 1 689 B, bank 2 image and low
RAM unchanged; no new RAM (`PFCF_DEAD` = candidate flag bit 7). Budget
(`tests/budget.py`, cast cap 128k): new gated "lcasts" (= "lcastf" with 4
ASLEEP monsters: 4 wake lines on the fire tick) and "advcast" (fuzz #208
through the real cast: Lightning r2 from x 26 facing right, Bat over the
caster, reflecting Ghost, 2 Slimes, flight-row bricks at cols 0 / 3 / 31;
151.1k T before this pass → **126.0k**); "lcasts" **111.8k** (was 126.0k
measured), "lcast" 112.1k → **98.2k**, "lcastf" 114.5k → **100.6k**, "fcast"
cast 88.0k, "wcast4" 118.6k, "acast" 87.4k; `tests/proj3.py` worst cast 65.6k
(P10). Cuts: `set_reaction_at` ×17 by
shifts (was a 17-step add loop, ~0.6k T a hit), `pf_bodies` stops at the
col's count and dead bodies stay DONE, runs of plain cells entered in bulk,
`pf_cands` reads LIVE_LIST's cached w / h, its row scan unrolled ×2,
`rsp_hl` / `deal_hit` record reads without loops / push-pop.

**Headroom after the D3-8 review fix pass** (build DISPLAY, `-DDEBUG_KIT=0`):
bank 3 **358 B** free (−57: the `PF_ROWF` body count, `panel_init`'s
`STAT_SH`); bank 7 code 3,781 B, **2,363 B** free (kit 3,831 / 2,313; +37);
bank 1 689 B, bank 2 image and low RAM unchanged. Budget: the `PF_ROWF` body
count lets the walk fast-forward over cols only struck bodies cover — "lcast"
cast 126.8k → **111.9k T**, new gated scenarios "lcastf" (4 FROZEN-1 monsters,
tinted, expiring in the deferred monster phase) **114.5k** and "fcast" (Frost
Shard r2 bounce → self-freeze) cast 88.0k / ordinary 110.2k; `tests/proj3.py`
worst cast 71.0k → 64.0k. Measured, not gated: "lcastf" with 4 sleepers
(`BUDGET_STF=2`: 4 wake lines on the fire tick) 126.0k.

**Headroom after D3-8** (build DISPLAY, `-DDEBUG_KIT=0`): bank 3 **415 B**
free (−103: `resolve_monsters`' status test + far7 ~24, `item_icons`' sig
test ~15, `deal_hit` boss + WEAK ~35, `hit_roll` WEAK ~20, the `dg_bad`
ALIGN shift); bank 7 code 3,744 B, **2,400 B** free (kit 3,794 / 2,350;
+610: `status7.asm` ~520, `turn_input` / `use_icon` / `try_horizontal` /
`ic_melee` / `ic_disp` hooks ~90); bank 1 **689 B** free (−94: `stat1.asm`);
bank 2 image `$8000..$A1D0` 8,656 B, 1,072 B to `FRT` + 167 B pad (+~140:
the render tint + `st_tint` + `st_tint_tab`, `st_sig`, `icon_poll`'s test;
`kind_tab` `$9F00` → `$A000`); low RAM unchanged. New RAM: `HST_DONE`
`$BC51`, `HELD_T` `$BC52`. Budget (`tests/budget.py`): ordinary max 121.2k T; "lcast" cast
126.8k (cap 128k; T7 126.1k: the render tint +57 T a drawn slot, `deal_hit`'s WEAK test
~40 T a hit), "wcast4" 118.6k / 120.1k, "wcast" 96.8k, "acast" 93.8k.

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
need 44,096 of 46,472 (2,376 slack). Bank 1 is the next store to run out:
R4 (ZX0-pack `font6x8` / `tiles_common`, ~0.5 KB) is the lever.

**Headroom after D3-TX** (text block → bank 0, D3-2 strings in): bank 1
free 2,168 B; bank 2 unchanged (1,072 + 108 pad); bank 3 unchanged 3,867 B;
AY slot 4,059 B; low RAM 667 B spare (−55: `tx_dec` 35, the `.txt` tape
load 20); pool `POOL_CAP` 46,472 for a need of 40,096 (6,372 slack).

**DEC2 (2026-10-26, user ruling: drop BONES and CAULDRON):** `dg_bones` / `dg_bfit` / `dg_bput` + `dg_bodds` + `dg_bids`
(the bones pass), the two CAULDRON records (D2, D4: `dg_start` / `dg_recs` -2 = 39 records, `DG_NREC` 39) and the
glyph-last-column path (flag bit 3, `F_GLAST`, cauldron only) in `dg_obj` / `dg_cell` are gone; decorgen.py mirrors it.
**Bank 3 `bank3_end` `$ED35` -> `$EC96`: 11,573 -> 11,414 B code, free to `AY_RESERVE` (`$EFA0`) 619 -> 778 B (+159 B; both
`DEBUG_KIT` builds).** Other banks unchanged (no tileset byte saved: the 32-slot sets are fixed size). Freed tile ids:
common **13, 15, 16, 31** (`T_FREE13/15/16/31`, not renumbered); per-level the cauldron slots are not reserved (the
generator packs sequentially, so D2 uses 24 of 28 decor slots and D4 25: **4 / 3 free tail slots, ids D2 56..59, D4
57..59**; later ids of D2 / D4 shifted down by the removed 3 / 3 slots, all consumers read `tileset_ids.inc`).
`dg_bad` regenerated (13 / 15 / 16 / 31 now 0). Room-build cost: `build_room_map` worst 192,733 -> 187,271 T; `decor_room` worst 161.4k T.

**DEC1 (bones, 2026-10-20):** decor menu 7 -> 4 common records (CANDLES, SKULLS, TORCH_SMALL gone;
D2/6/8 keep TORCH_SLIM), `dg_start` / `dg_recs` -3 each (41 records), new bones pass `dg_bones` /
`dg_bfit` / `dg_bput` + `dg_bodds` (8 B, gate by depth) + `dg_bids` (4 B) in `decor_gen.asm`, the attr-all /
attr-type-2 code of `dg_obj` / `dg_cell` removed: **bank 3 free to `AY_RESERVE` 205 -> 103 B (-102)**.
`dt_attr_tab` 16 -> 8 B (`DT_KINDS` 1): bank 2 image unchanged (29 B to `FRT`), the `kind_tab` ALIGN
pad 85 -> 93 B (+8). `proto_decor` is empty (the room-A torch was ids 15 / 16): -8 B bank 3 (included above).
`dg_bad` is unchanged (id 31 was already >= 28 in the ring table's decor range).
**Headroom at D3-0** (build DISPLAY): bank 1 free 992 B (was 974); bank 2
image 1,072 B to `FRT` + 108 B pad (was 816 + 110; `kind_tab` `$A100` →
`$A000`); bank 3 3,867 B to `AY_RESERVE` (was 964 to `$E400`); AY slot
4,059 B free; low RAM 722 B spare (was 723).

## 3E contracts (3E-T3) — items, ITEM_RAM, trap list

Source of truth: `src/item_defs.asm` (EQUs / one macro / ASSERTs, no bytes;
INCLUDEd by `defs.asm` after `combat_defs.asm`). `tests/items3e.py` mirrors
the layout from the `.sym` (L1–L3) and checks the runtime rules (R1–R2).
Design: game.md §1.5, §7, §8, §8.5, §8.7–§8.9; user rulings 2026-10-19/20
(no gold, scaled 8×8 floor glyphs as icons, no other-class books, light ID kept).

**Type enum (ordered by class: a class / slot test is one `IT_IN lo, hi` =
`sub lo : cp hi-lo+1`, 4 B 14 T, CF = in range, A = index in the class).**

| Ids | Class | Members |
|---|---|---|
| 0 | `IT_NONE` | free slot / no pin / grey quick slot |
| 1 | `IT_POTION` | **legacy** 3B floor potion → `E_POT` (retired by T11, then reserved) |
| 2..4 | counters `IT_CNT_*` (never in the bag) | `IT_DAGGER` 2, `IT_ARROW` 3 (`IT_AMMO_*`; ids kept from D3-7), `IT_KEY` 4 (→ `LF_KEY_TAKEN`) |
| 5..9 | food `IT_FOOD_*` | Carrot, Apple, Pear, Cheese, Meat (ascending FOOD: quick slot = lowest id) |
| 10..12 | potions `IT_POT_*` | Heal, Mana, Cure (quick priority order) |
| 13..16 | scrolls `IT_SCR_*` | Teleport, Fear, Sleep, Enchant (tie order) |
| 17 / 18 | book / tool | `IT_BOOK` (the hero's class book; a tome is a READ outcome, not an item), `IT_BOW` (replaces `HAS_BOW` at T11) |
| 19..26 | weapon `IT_WPN_*` (slot W) | Warrior 19..22 (Short, Long, Axe, Cleaver*), Mage 23..26 (Oak, Iron, Rune, Bone*) |
| 27..32 | armour `IT_ARM_*` (A) | Robe, Leather, Chain, Plate, Silk Cloak*, Gravecloak* |
| 33..36 | helmet `IT_HELM_*` (H) | Hood, Helm, King's Helm*, Mirror Helm* |
| 37..43 | charm `IT_CHARM_*` (C) | Might, Warding, Fire Ward, Amulet of Mana, Plenty, Scarab*, Ring of the Grave* |

`IT_COUNT` 44 (T4 tables); * = boss unique. `IT_ID_LO..IT_ID_HI` = 10..16:
(3E rev 6: no identification; the `IT_ID_*` / `ID_*` / `KNOWN_*` / BUC / HIDDEN EQUs
are still in `item_defs.asm` for the T8/T10 cleanup, nothing in the engine reads them.)

**Item record** (§8.9): `IR_TYPE` / `IR_QTY` / `IR_IST`, `IR_STRIDE` 3 (bag,
worn); a `FLOOR_LIST` entry keeps its 4-B layout (`FL_ITEM` / `FL_QTY`; rev 6: no
ISTATE on the floor, a pickup writes 0). Stacks merge on equal TYPE and ISTATE, `STACK_MAX` 9. ISTATE
(gear; 0 otherwise): bits 0–1 BUC (`BUC_NORMAL` 0 / `BUC_BLESSED` 1 / `BUC_CURSED`
2, 3 reserved; bit tests `IST_BLESSED_BIT` / `IST_CURSED_BIT`), bit 2 `IST_HIDDEN`
(display only), bits 3–4 enchant 0..`ENCH_MAX` 3, bits 5–7 `m` signed −4..+3
(`IST_M_P2` $40, `P1` $20, `M1` $E0, `M2` $C0, `M3` $A0). No per-item
identified bit (identification is per type, `KNOWN`). Worn slots `WS_WEAPON` 0 /
`WS_ARMOUR` 1 / `WS_HELM` 2 / `WS_CHARM` 3 = the gear range order.

**`ITEM_RAM` `$5D00..$5D50`** (81 B; 3E simplification 2026-10-20: `FL_IST` 32, `ID_MAP` 7, `KNOWN` 1 dropped, and the T6 `FL_ATTR` 32 never shipped: the floor ink is a per-draw `item_ink(type)`; was 121), bank 5, the BASIC area free after `boot`
moved SP; one page; not on tape, garbage before `new_game`):

| Addr | Symbol | Size | Lifetime |
|---|---|---|---|
| `$5D00` | `BAG` | 20 × 3 | game: zeroed by `new_game`, kept across levels |
| `$5D3C` | `WORN` | 4 × 3 | game (follows `BAG`: one 24-record scan) |
| `$5D48` | `FOOD` | 1 | game (0 after `new_game`; T9 sets `FOOD_START` 80) |
| `$5D49` | `FOOD_TMR` | 1 | game (turns since the last burn, period `FOOD_PERIOD` 6) |
| `$5D4A` | `HSTAGE` | 1 | game (`HS_FED` 0 / `OK` / `HUNGRY` / `WEAK`; thresholds 50 / 25 / 10) |
| `$5D4B` | `HP_RG` | 1 | game (3E-T9, was `QPIN` byte 0 — the QUICK pin is cut, §8.11 Q3: FED HP regen turn counter 0..11) |
| `$5D4C` | `HW_TMR` | 1 | game (3E-T9: turns in WEAK since the last faint check, 0..49; `$FF` on entering WEAK; **FAINT1: the faint clock**, rollover at 50 = `HW_REPEAT`, then `HW_REPEAT − FAINT_GAP` = 20; deferred = held at 49) |
| `$5D4D` | `MP_HOLD` | 1 | per turn (3E-T9: written by `hunger_turn` right before `xp_turn`, which skips MP regen when != 0) |
| `$5D4E` | `QS_CACHE` | 3 | game (the type each quick slot shows; `IT_NONE` = grey) |

Cleared by **`new_game`** only (bank 7, `boot7.asm`: 9-B `inc l` loop, ~2.1k T (81 B),
before `level_reset_new`); `level_reset` / `level_populate` (bank 3) and
`hero_st_init` do not touch it. Cost: bank 7 +9 B (free after 3E-T3: kit **144**, release
**194**); banks 2 / 3 / 1 / low RAM unchanged (18 to `FRT` / 103 / 1,694 / 333). ASSERTed: one page, ≥ `$5CCB`, end ≤ `PF_RAM`.
Clear of `LOG_TXT`, `PF_RAM`, `MK_RAM`, the page band (`PAGE_ORG..PAGE_LIMIT`
`$5000..$57FF`), `GEN_SCRATCH` and the stack (`$BF00`, bank 2) by address
(`tests/items3e.py` L3).

**Trap list** (§1.5): `TRAP_LIST` `$6DF0` 6 × 2 B + `TRAP_N` `$6DFC` (LVL_STATE,
the ROOM_DESC spare). Per level for free: level_gen's `attempt` zeroes
`EDGE_TAB..LVL_STATE_END` and `proto_level` the header..`FLOOR_LIST` (R2).
`TR_B0`: bits 0–3 room, bit 4 `TRF_S1`, 5 `TRF_KNOWN`, 6 `TRF_SPENT`; `TR_B1`:
bits 0–4 col, 5–7 type (**STUN1: 3 bits**, `TR_TYPE_MASK` `%11100000`; `TT_DART` 0, `TT_GAS` 1, `TT_TELEPORT` 2, `TT_ALARM` 3, `TT_STUN` 4).
Written by the 3E-T6 generator after `level_gen` (`tools/items_model.py`
`gen_traps` / `apply_block`; `tools/levelgen.py`'s 320-B block keeps them 0).

**3E-T6 generator + floor inks (built; reworked for the 3E simplification).**
`src/items_ovl.asm`, an overlay at `ITEMS_ORG` = `GEN_SCRATCH` (1,027 B raw +
53 B scratch past the image, ASSERT `ig_end` ≤ the window), ZX0 stream
`ovl_items_zx0` **881 B in `BANK_OVL_ITEMS` = bank 1 (again since MEM-1)** (defs.asm; any bank
`ovl_run` can page: move the INCBIN and the EQU together). `level_new` (bank 3)
tails `level_populate` with `ovl_run` (LG_* / `LP_CMAP` dead by then), so the
overlay runs with bank 3 paged and reuses bank-3 `rnd` / `rdp` / `hla` /
`hits` (no LG_* scratch). Spec: `tools/items_model.py` rev 6 byte for byte
(`apply_block`: FLOOR_LIST + trap list only), `tests/items_gen.py` G0 (`it_tab`
== `ITEM_INK` / `glyph`), G1 (1,000 master seeds × D1–D8 × both heroes: the
320-B block incl. the `FL_EMPTY` tail, the trap list and the restored
`GEN_RNG`), G2 (the real `level_new` path). `ITEM_RNG` lives in the `GEN_RNG`
word while the overlay runs and `GEN_RNG` is restored on its only exit, so no
GEN_RNG-derived output moves. Food / scrolls / gear share one loop over a
5-B descriptor table (`ig_grp`), the footprint / pit / mid-block spans one
helper (`ig_span`).
Floor glyph + ink = **`it_tab`** (low RAM, 44 B, one byte per type: glyph
class << 4 | BRIGHT << 3 | ink; `it_cls` 7 B class → glyph id): `item_glyph`
(`build_room_map` `.pots`, bank 3; `ap_stamp`, bank 7) and `item_ink`
(`fl_attr`). `fl_attr` (low RAM: room A, plane base C = `SCREEN_ATTR` /
`SHADOW_ATTR` high byte, signed row / col offset D / E; last entry of a cell
wins; types without a glyph skipped; SMC `.bh`) runs from `room_show` (level
start, both planes after `draw_room`), `room_shadow` (after a transition, the
shadow), `ap_stamp` (after a pickup, the shadow; a cell left empty keeps
`TILE_ATTRS[T_AIR]`), and every transition-scroll step (`scroll1.asm`: after
the step's `tile_rect`, the entering room's inks at their current screen
cells). `TILE_ATTRS` of the item glyph ids is 0 at run time
(`level_load_tiles`), so between a `tile_rect` and its `fl_attr` (inside one
scroll step) an item cell is blank, never a wrong ink; `tests/gfx_integrity.py`
R3 checks every scroll step's visible item cells and the attr shadow of every
live entry. `floor_pickup` takes `IT_P_*` potions like the legacy `IT_POTION`
(→ `E_POT`, until T11) and leaves every other new type in place; **T11 must
widen its glyph pre-filter** (today `T_POTION` / `T_AMMO` only). `POTIONS_TAKEN`
(bit = entry index 0..7, set by `pp_take` only) has no reader in the engine
(only `tests/abil_ammo.py` P9): entries 0..7 may now hold food / gear, so
nothing may read a bit as "potion i". (3E-T11: done — the pre-filter takes every
item glyph; see "3E-T11".)

**3E-T6 byte / time ledger** (tools/build.sh DISPLAY; before = main with lever
(c) + T4 + T5b): bank 1 free **1,635 → 718** (−917: `ovl_items_zx0` 881 + the
two scroll hooks 36); bank 3 free to `AY_RESERVE` **616 → 609** (−7:
`level_new` calls `level_populate` + `ovl_run` +14, `.pots` via `item_glyph`
−7); bank 7 free kit **147 → 142** (release 192; `floor_pickup` `IT_P_*` +8,
`ap_stamp` −3); low RAM `LOWRAM_SPARE` **324 → 119** (−205: `it_tab` 44 +
`it_cls` 7 + `it_byte` / `item_glyph` / `item_ink` ~40, `fl_attr` + 3 entries
~95, `room_show` / `room_shadow` / `level_load_tiles` hooks ~19); `ITEM_RAM`
121 → 81 B (runtime); bank 2 0. Time: the overlay (unpack ~69k T +
generation) **≤ 0.26M T per level start** (worst of 320 single-level runs, D7
Warrior), on top of `level_gen` (0.1–0.9M T) while the DEPTH card is shown;
`fl_attr` ~1.4k T scan + ~0.75k T per entry of the room (4.5k T measured with
4): a room transition + ≤ 19 calls ≈ **+≤ 0.1M T** on the ~2.6M T scroll;
`ap_stamp` + one call per pickup; per tick 0 (`tests/budget.py` gate passes).

**3E-T4b ledger** (item text into bank 1, dead bank-0 strings out, `feat/3e-t4b-include`):
`tools/itempack.py` now runs in the default `tools/build.sh` (before pass 1;
`--items` is the verbose report). `main.asm` INCLUDEs `build/text/items_tab.asm`
(`it_words` 229 + `it_wcx` 12 + `it_name` 132 + `it_stems` 89 = **462 B**,
ASSERTed against the generated sizes, `ITN_ROWS == IT_COUNT`, `<= ITB_RESIDENT`)
in bank 1 right before `ovl_blobs`; nothing reads it until T10 `item_name`.
Bank 1 free **718 -> 256**. The fx / page overlay stems and `it_stat` are
generated (`items_fx_stems.asm`, `items_ovl_stems.asm`) but NOT included (T8 / T13).
Bank 0 text: removed `cmb_holds_*` (3), `cmb_cling`, `cmb_cursed_no`, `cmb_lifts`,
`cmb_shat_*` (3) = 9 strings, packed **2,650 -> 2,468 B** (pool start `$CA5A` ->
`$C9A4`); `POOL_NEED` 44,096 of `POOL_CAP` **46,502 -> 46,684**, pool slack
**2,406 -> 2,588** (+182). `cmb_notch` / `cmb_acid_*` / `cmb_*_breaks` have no
user either (wear/break is not BUC) but are kept for T8/3F to decide; `found` /
`quaff` still referenced (T11 retires them). `item_defs.asm`: BUC_*, `IST_HIDDEN`,
`IT_ID_*`, `ID_*`, `KNOWN_*` EQUs gone; ISTATE bits 0-2 = `IST_RSVD_MASK`
(always 0). DEBUG_KIT only: `IT_BAD` (= the spare `TIMING_MARK` `$BFC0`) counts
`item_glyph` / `item_ink` calls with a type >= `IT_COUNT` (`it_byte_live`, +10 B
low RAM in the kit build, 0 B release; kit `LOWRAM_SPARE` 109, release 119).

**3E-T10 bag helpers + item name composer** (`feat/3e-t10-bag`; no caller until T11; `tests/bag.py`).
IX / IY never touched, no EXX; `BAG` is bank 5 (always mapped), so nothing pages.
- `item_name` (bank 1, `src/itemname1.asm`, **98 B**, inside the it_tab DISP block; far1 or a
  direct call with bank 1 paged): **In** A = type, DE = dest (outside `$C000`: `MSG_BUF`
  / page scratch), H = max chars 0..32, C = mode (bit 0 reserved, ignored). **Out** DE past
  the last char, **no terminator**, CF = 1 iff cut at H (a cut right after a space keeps the
  space). Clobbers A, BC, HL. Words from `it_name` (3 ids; the `$FF` book marker = `W_WAR +
  HERO_KIND`), lookup via `it_wcx` + <= 7-word scan, one space between words. Worst name
  (WARLORD CLEAVER) ~4.4k T (limit 6k). Types 0..4 give an empty name.
- Bank 3 (`src/bag3.asm` — **R6: now `src/bag6.asm` in the R6 region, via far6**; last INCLUDE of `bank3.asm`, **159 B**, via far3 or direct from
  bank-3 code / overlays running with bank 3 paged). `BAG` stays packed from slot 0 (a free
  slot is followed only by free ones; pickup order).
  - `bag_add` A = type, B = qty, C = ISTATE -> **L = 0 added / 1 refused** (full, or type
    < `IT_BAG_LO` incl. legacy potion 1, or >= `IT_COUNT`; BAG untouched). Food / potions /
    scrolls (`IT_FOOD_LO..IT_SCR_HI`) top up the first same-type stack that stays <= 9, else
    the first free slot; gear / book / bow never merge. Clobbers A, DE, HL (B, C kept). <= ~1.3k T.
  - `bag_find` A = type -> A = slot or `$FF` (IT_NONE = first free slot). Clobbers A, C, HL.
  - `bag_take` A = slot, B = qty -> A = QTY left; at 0 (or over-take) the slot is
    compacted away (<= 19 records shift, ~1.2k T). Clobbers A, BC, DE, HL.
  - `bag_pick` (the quick-slot pick; QUICK pin cut, so a lookup, not `qs_pick`): B = first
    type of the class, D = 2 x class size + mode (0: lowest type present = food, potion;
    1: largest stack, ties lowest type = scroll) -> A = type or `IT_NONE`; `bag_find` gives
    the slot. Clobbers A, BC, DE, HL. <= ~3.7k T (scroll class absent).
- Ledger: bank 1 free **256 -> 158** (-98), bank 3 free to `AY_RESERVE` **609 -> 450**
  (-159), bank 7 / low RAM / bank 2 unchanged (kit 142, release 192; `LOWRAM_SPARE` 109 / 119).

**3E-T11 pickup into the bag, potions from the bag, start kit, drops** (`feat/3e-t11-pickup`;
`tests/pickup3e.py`; spec game.md §8.11 "3E pickup/drop rulings", Q10, Q11).
- **Pickup** (`floor_pickup`, bank 7): pre-filter widened to every item glyph (60..63
  FLASK / FOOD / WEAPON / WORN, `T_PAGES`, `T_AMMO` for the Warrior). Ammo as before
  (`ap_take`). Any other type: `pu_add` (bank 3, far3, A = FL_ITEM): legacy `IT_POTION`
  -> `IT_P_HEAL`; `bag_add` qty 1 ISTATE 0; added -> `IT_BOW` sets `HAS_BOW`, the line
  `YOU PICK UP <name>` (`it_line`), L = 1 -> `pp_take` (bank 7: `FL_EMPTY`,
  `POTIONS_TAKEN` bit, `SFX_PICKUP`, `ap_stamp`); refused (bag full, L = 0) -> the entry
  stays; `floor_pickup` prints `BAG FULL` only when the entry's col was NOT under the
  previous body span: `floor_pickup` keeps `PU_POS` (HERO_ST +29: x, FL_ROOM byte) and
  copies the previous x into `PU_ARR` (+31; `PU_NONE` $80 after a room / storey change;
  `panel_init7` sets `PU_POS + 1` = $FF per level) — walking across one item prints it once.
  Standing on a cell keeps retrying the pickup every turn silently, and a drop landing
  under the hero is taken at the end of the turn (manager ruling, game.md §8.11 rule 4).
- **Log line composer** `it_line` (bank 1, `itemname1.asm`, far1): A = type (0: no name),
  E = `S3_*` stem offset in `it_stems` or `IL_PICK` ($FF) = bank-0 `cmb_pick` (tx_dec) ->
  stem + `item_name` (`IT_CAT_MAX` 20) into `MSG_BUF`, `log_push`. Stems: `bag_full`,
  `boss_drops` (new, `src/items.txt` [stems_resident]). Bank-0 `found` / `cmb_bow`
  deleted (no reader).
- **Quick potion** (3E-T12: now R6 `fx_quick` + `pot_eff` / `cap_add`, moved out of bank 7; the line is "YOU DRINK THE <name>"; was `ic_quaff`, bank 7): Heal -> Mana -> Cure, the first type present
  (far3 `bag_find`, C out 0 = absent) whose effect is not refused (`pot_eff`, CF):
  Heal `QUAFF_HEAL` 10 / Mana `POT_MANA` 8 (`cap_add`: HL = value, max at HL+1; refused
  when full) / Cure (`ST_FLAGS` slot 0: POISON, WEAK, MIND cleared, `ST_T1` low nibble and
  `ST_T2` 0, HOLD kept, + `POT_CURE_HP` 4; refused with none of the three); then
  `pot_take1` (far3), flash, `SFX_QUAFF`, `TX_QUAFF` (the "DRINK THE <name>" stem is the fx
  overlay's, T12). All refused -> `NO NEED` (`no_need` moved to [stems_resident], 8 B),
  `IC_REFUSED`, no turn.
- **Drops** (`mon_drop`, bank 3, from `deal_hit`'s kill path, IX = the body): EF_RESPAWN ->
  none. **Boss (STAND-IN until 3F gives bosses a kind / `IMMF_BOSS`):** the first kill of
  kind `LP_BOSS` in `LVL_LAIR` this level (`LF_UNIQUE` clear) -> `uniq_tab[depth-1]` (D4
  Mage: index 7 `IT_W_BONE`; D8 none), whole-storey search, `BOSS DROPS <name>`, no RNG
  (pushed at once, i.e. BEFORE the attacker's "YOU KILL THE <x>" impact line: deferring it
  needs a pending byte + an end-of-turn hook, ~16 B bank 7 — not done, manager to decide);
  an escort of the boss's kind killed first takes it. Else `drop_tab` (3F-T3: 12 x 4 B: kind, type,
  N, k = "k in N": the 5 base drops (k = 1) + the 7 tier rows with the base numerator
  + 1 per tier above 1 (Cheese 1/4 -> 2/4 -> 3/4, Arrows 1/2 -> 2/2); the random-food
  drop of the tiers whose base has none is T5/T6; arrows (qty 3) Warrior only),
  one `rng_mod(N)` on the gameplay RNG, dropping iff the roll < k (`tests/proj3.py` `drop_roll` models
  it), no line. `drop_put`: centre col `x + w/2` on row 9s+7, else nearest col within
  +-3 (left first) whose `ROOM_MAP` cell is `T_AIR` (= no live entry, the FLOOR_LIST
  invariant; also no wall / decor); entry = the first `FL_EMPTY` among 0..30 (ordinary)
  / 0..31 (unique: entry 31 is the last to fill, so it stays free for it); writes the
  entry, far7 `ap_stamp_a` (A = col, E = FL_ROOM byte). Arrows never merge on the floor.
  Not done (3F, with the lectern swap it guards): the D8 lair/Sanctum 60..63-glyph loss.
- **Ledger** (tools/build.sh DISPLAY, before = main f25c650 -> T11 review round): bank 3
  free **450 -> 47 release / 29 DEBUG_KIT** (`pickup3.asm` ~395 + 18 kit data, `bag3` +8,
  `combat3` +3, `level_populate` −3; the review round moved BAG FULL to bank 7 and dropped
  `pot_pick`); bank 7 **192 -> 72 release, 142 -> 22 kit** (−120: the quick potion with its
  skip rule, `pot_eff` + `cap_add` inline, the BAG FULL span test, the pickup / arrival
  code); bank 1 **158 -> 91** (`it_line` 47, stems `boss_drops` 12 + `no_need` 8); bank 0
  text 2,468 -> 2,448 (pool slack +20); low RAM / bank 2 unchanged (119 / 18). RAM:
  `PU_POS` / `PU_ARR` (the 3 spare HERO_ST bytes), `LF_UNIQUE` (LVL_FLAGS bit 4).
- **Time** (`tests/pickup3e.py` T, incl. a ~0.3k stub): `floor_pickup` with nothing ~1.7k;
  one bag pickup **~22.3k T** (`pu_add` 10.5k: bag_add + pot_sync + name + log; `ap_stamp`
  8.1k; scan + far ~3.7k); a kill with a drop 12.7k (3.4k without); the boss kill + unique
  19.2k. `tests/budget.py` "pmix" (the mix + a bag item on every 2nd col of the walk + a
  kill): ordinary work max 124.3k (cap 126k; mix 123.6k); with an item on EVERY col (13
  adjacent items, `BUDGET_PMIX_STEP=1`) 126.65k: the panel's 1st-frame loop drawing log +
  icons + info in the same tick.

**`E_POT` migration — DONE in 3E-T11 (as built; supersedes the plan table that
was here).** `E_POT` (`P_ENTITIES + E_POT`, entity byte 8 of the hero) is no
longer a counter: it is the **number of potions in `BAG`** (Heal + Mana + Cure
QTY), written ONLY by `pot_sync` (R6 `pickup6.asm`; was bank 3 `pickup3.asm`), which every BAG writer
runs: `bag_add` (on success) and `bag_take` tails, and `level_populate` (the old
descent carry is gone). So the readers did not change: `icon_poll` / `icon_state`
`.pot` / `item_icons` (`PANEL_POT_SH`), `slot_redraw` (count digit, capped 9),
`item_info` ("X n"), `ic_potion` (0 -> NO POTION). Writers:

| Site | As built (3E-T11) |
|---|---|
| `boot7.asm` `new_game` | `ld (ix+E_POT), 1` deleted; `kit_add` (far3) writes the start kit: WORN weapon + armour, BAG Heal (+ Mana for the Mage) + Apple (game.md §8.11 Q10), DEBUG_KIT extras (rev 6: Cure, Mana (Warrior), the 4 scrolls, Meat, book, Helm, + the bow for the Warrior); E_POT via `bag_add` |
| `bank3.asm` `level_populate` | carry deleted -> `call pot_sync` |
| `pickup7.asm` `floor_pickup` / `pp_take` | every non-ammo entry -> `pu_add` (far3: legacy `IT_POTION` = Heal, `bag_add` qty 1 ISTATE 0, the line); `pp_take` (bank 7) then empties the entry, sets the `POTIONS_TAKEN` bit, SFX, `ap_stamp` |
| `intent7.asm` `ic_quaff` | `pot_pick` (far3, `bag_pick` mode 0: Heal -> Mana -> Cure) + the effect inline in bank 7 (`cap_add`) + `pot_take1` (far3: `bag_find` + `bag_take` 1) |
| `HAS_BOW` | kept (readers unchanged): set by `pu_add` when the bow is taken and by `debug_kit`; the bow is also a bag item. Retiring `HAS_BOW` needs the DISCARD path (T13) to clear it — or every reader switched to `bag_find IT_BOW` |

`MAX_POTIONS` has no engine user (a test name only); `IT_POTION` (1) stays: the
PROTO rooms and the 3B levelgen step still write it (levelgen parity; the items
overlay retypes generated ones), and `pu_add` takes it as a Heal potion.

**3E-T9 hunger** (`feat/3e-t9-hunger`; `tests/hunger.py`; game.md §7, §8.11 (2)).
- **R6 `src/hunger6.asm`** (far6 only; r6.asm rules). `hunger_turn` (end_turn, bank 7: `ld hl,
  hunger_turn / call far6` right before `jp xp_turn`, not when DYING): (1) jump this turn
  (`JUMP_TURN == TURN_COUNTER`: try_jump stored counter + 1, end_turn incremented since; 0 B
  outside R6) -> FOOD −2; (2) `FOOD_TMR` +1, at `FOOD_PERIOD` 6 (12 with `IT_C_PLENTY` /
  `IT_C_SCARAB` in `WORN` charm) -> 0, FOOD −1; floor 0, never fatal; (3) `hg_stage`; (4) FED:
  `HP_RG` +1, at 12 HP +1 (to MAXHP); WEAK: `HW_TMR` +1, at 50 `hg_faint` (FAINT1; was the WEAK line again); (5)
  `MP_HOLD` = WEAK (status or hunger) ? != 0 : HUNGRY ? `TURN_COUNTER` bit 0 : 0.
  `hg_stage`: `HSTAGE` from FOOD (50 / 25 / 10), `STS_HWEAK` := WEAK, on a change `PD_FOOD`
  + at most one line through far1 `it_line` (A = 0, E = `S3_HG_*`): down into HUNGRY / WEAK,
  up into FED; into OK and WEAK -> HUNGRY none. `hunger_add` (**T12 EAT API**: A = amount,
  far6; FOOD capped at 100, then `hg_stage`; the `NO NEED` refusal at 100 is the caller's).
  `item_food` (panel FOOD item): bar (FOOD / 100, cols 15–18), bank-0 `hg_*` word padded to 6
  (cols 19–23), the stage attr over cols 15–23, `pmark_rect`. `kit_add` sets `FOOD_START` 80.
- **Lines:** `hg_hungry` / `hg_weak` / `hg_fed` moved from `[stems_fx]` to `[stems_resident]`
  in `src/items.txt` (bank-1 `it_stems`, +58 B; the bank-0 `hg_*` are the 1-word panel stage
  names, there is no bank-0 line text to reuse).
- **Penalties (all read where they apply; nothing for T8's `hero_recalc`):** `hit_roll`
  (bank 3) hero attacker: WEAK (either) atk −2, else HUNGRY atk −1; target eva −1 and
  `deal_hit` dmg −1 with `STS_WEAK | STS_HWEAK`; `h_jump` (bank 7) refuses the jump; `xp_turn`
  regen gate = `MP_HOLD` (HUNGRY: `MP_RG` advances on even turns only = period ×2; WEAK:
  frozen); FED HP regen in `hunger_turn`. Not hunger: Amulet of Mana / Scarab MP regen ×2 stays
  TODO(T8).
- **Panel:** `panel_more` (bank 2) draws `PD_FOOD` in a tick's 1st frame only (before INFO;
  `far6 item_food`); `panel_init7` queues `PD_FOOD` per level (the bank-3 full-bar + "FED"
  placeholder and `str_fed` are gone).
- **Ledger** (DISPLAY, kit / release; before = main `ab2bb89`): R6 code 582 → 892 / 564 → 874
  (free 5,121 → 4,811 / 4,829); bank 7 22 → 17 / 72 → 67 (end_turn +6, xp_turn −1; `h_jump`
  mask 0 B); bank 3 603 → 619 (placeholder −~20, `hit_roll` HUNGRY +~9); bank 2 `kind_tab` pad
  68 → 57 (`panel_more`); bank 1 1,300 → 1,242 (the 3 lines); low RAM unchanged (93 / 103).
- **Time** (`tests/hunger.py` T1, incl. far6): `hunger_turn` ~0.87k T plain, ~0.96k with a burn,
  ~3.6k with a stage line; `item_food` ~8.5k (1st frame only).

### Phase-locked walk shifts (2026-10-21, `PHASE_SHIFT` default 1)

Rule: docs/conventions.md "Walk cycles"; `-DPHASE_SHIFT=0` = the previous image
byte for byte (verified vs main `e72a957`). Ledger (tools/build.sh DISPLAY):

| Store | `PHASE_SHIFT` 0 | 1 (default) | Δ | Why |
|---|---|---|---|---|
| `POOL_NEED` (of `POOL_CAP` 46,704) | 44,096 | **37,312** | −6,784 | walk frames store one shift (monsters 22,688 → 18,592, hero max 18,528 → 15,840) |
| pool slack | 2,608 | **9,392** | +6,784 | |
| bank 2 `kind_tab` ALIGN pad (free to FRT 18 unchanged) | 98 | 72 | −26 | `anim_entity .walkph` lock + `PHASE_TRAP` bump |
| low RAM spare (`LOWRAM_SPARE`) | 109 kit | 103 kit | −6 | `gen_facing .stat`: `FF_PH4` added to the anchor shift |
| bank-6 boot block | 1,938 | 1,941 | +3 | `PHASE_TRAP` cleared at boot |
| `PHASE_TRAP` `$BF4A` | unused | debug trap | — | state block, was spare |

**3E-T8 gear: `hero_recalc`, equip / remove, Enchant API, `ovl_fx`, the stat line** (`feat/3e-t8-equip`;
`tests/equip.py`; game.md §8, §8.6, §8.11 "3E simplification").
- **`hero_recalc`** (R6 `gear6.asm`, far6; the ONLY writer of the hero's combat stats after
  `hero_st_init`, which no longer writes `kind_tab` / `HERO_DEF`): atk = `KN_ATK` / `WZ_ATK` +
  (LVL ≥ 4) + (LVL ≥ 8) + gear ATK; eva = `KN_EVA` / `WZ_EVA` + (LVL ≥ 6) + gear eva (`gx_tab`);
  `KT_DIE` = the worn weapon's die (fists `FIST_DIE` 2), `KT_BONUS` = its `m` (+1 Cleaver),
  clamped ≥ 0 (deal_hit needs dmg ≥ 1; 3F wear with m < 0 needs a max(1, ..) at the two melee
  rolls first); `HERO_DEF` = Σ DEF (+ m on armour / helm with DEF) ≥ 0; `HERO_RES` B0 / B1 =
  per-field max (`rmax`: R + I must not read X), `HERO_IMM` = OR; gear MP (+ m on Robe / Hood)
  applied as a delta `MAXMP += new − GEAR_MP` (level-ups / tomes stay in MAXMP), MP clamped
  (never raised); `MP_PER` = 8 / 6, ÷2 Mana / Scarab amulet, ×2 Plate (`xp_turn` reads it: −6 B
  bank 7); `PD_MP | PD_INFO`. Callers: `kit_add` (new game; then MP := MAXMP: Mage base
  `MAGE_MP` 10 + Robe 2 = 12; DEBUG_KIT Mage 38 + 2 = 40), the fx ops, `xp_level` (only when an
  atk / eva step was gained: the steps are no longer `inc`ed into `kind_tab`, so never twice),
  `enchant_weapon`, 3F wear. ~4.3k T incl. far6 (2 items). Not applied: Rune / Bone staff spell
  damage (no reader; the spell row is abil_load's `CAST_ROW`).
- **`enchant_weapon`** (R6, far6; T12's Enchant scroll): worn weapon `m` +1 up to +3 (`IST_M_P3`
  $60) + recalc, L = 1; fists or +3: L = 0 (caller prints NOTHING HAPPENS, consumes the scroll).
- **`fx_line`** (R6): A = type, E = `S_FX_*` → stem + bank-1 `it_line_nm` (new label inside
  `it_line`, 0 B) → `log_push`. **`it_fmt`** (R6): the page stat line, A = slot, DE = dest.
- **Ops** (`fx_ovl.asm`; 3E-T12: moved verbatim into R6 `fx6.asm`, reached by far6 `fx_main`): EQUIP (bag slot → its worn slot by type range; the old worn item takes
  the freed bag slot = swap, never fails; empty worn slot → the bag slot is compacted),
  REMOVE (→ `bag_add` with QTY / ISTATE; full → refused, `FX_OP` 0); both "YOU EQUIP / REMOVE
  <name>", recalc, `FXR_TURN`. No class lock check (floor weapons are class-only).
- **Ledger** (DISPLAY, kit / release; before = main `f0ed1d5`): R6 code 912 → 1,925 / 894 → 1,907
  (+ gear6 1,001 + `kit_add` +12), streams +175 (fx) +11 (page), R6 free 3,937 → **2,737** /
  3,955 → 2,755 (review: +3 code, −1 stream); bank 7 17 → **46** / 67 → **96** (`hero_st_init` −20, `xp_turn` −6, `xp_level`
  −8 net, `use_slot` −2); low RAM 93 → **49** / 103 → **59** (`ovl_fx` 43 + 1: review fix, the save/restore copies FX_OVL_LEN only, `ovl_fx_saved` keeps the full-map restore); bank 1 1,226 →
  **1,177** (page_post +49); bank 3 0 (+0: `level_reset_new` range only); bank 2 0.
- **Tests:** `tests/equip.py` 24 checks (N kit numbers, E / F ops + round trip + cost, U uniques,
  C deal_hit DEF / X, X enchant, L steps once, P page_post injection, S stat text, M MP clamp /
  periods / regen); `tests/page.py` P9 now expects the verbs applied (PAGE_VLAST, 1 turn) and the
  goldens `page_start` / `page_bag` re-based (panel half only: the stat line on row 19);
  `tests/xp.py` C1 gate 13.5k → 18k T (+ recalc, 1st frame only: ≤ ~89k T).

**3E-T12 effects: EAT / DRINK / READ, books, Teleport, quick use** (`feat/3e-t12-effects`;
`tests/t12.py`; game.md §5, §7, §8, §8.11 Q3 / Q6 / rulings 3 / "3E simplification").
- **Placement: R6-resident `src/fx6.asm`, no overlay.** The T8 fx overlay packed 180 → 174 B
  (ZX0 3 % on code) but cost a map save / unpack / restore per use (EQUIP measured 52.3k T,
  a no-op 38.0k); resident, EQUIP is **10.9k T**, and a quick use from a turn tick needs no
  resync / defer (the T8 note's 40-55k T is gone). Deleted: `src/fx_ovl.asm`, `ovl_fx` /
  `ovl_fx_saved` (low RAM, 44 B), `FX_ORG` / `FX_MAP_SAVE` / `BANK_OVL_FX`, `FX_TELEPORT`,
  `FX_COUNT`, `FXR_TELE*`; the `fx.zx0` stream. New: `FXR_REFUSED` $80 (= `IC_REFUSED`).
- **Entries** (far6; results in L, FX_OP mirrors fx_main's): `fx_main` (page_post: `FX_OP` /
  `FX_ARG` = `PAGE_VERB` / `PAGE_SLOT`; DRINK / EAT / READ → `fx_use`, EQUIP / REMOVE as T8),
  `fx_quick` (use_slot SA_POTION / SA_FOOD / SA_SCROLL, A = the TX_NO_* line: FOOD =
  `bag_pick` mode 0, SCROLL mode 1, POTION Heal → Mana → Cure skipping refused types; empty
  → the NO line + `SFX_NO`, `FXR_REFUSED`), `tele_pick` (do_exit), `pot_eff` (also `tests/hunger.py`).
- **Icon bar:** `pot_sync` (every BAG writer) also writes `QS_CACHE + QS_FOOD` / `+ QS_SCROLL` =
  the food / scroll stacks in the bag (PD_ICONS on a change); `icon_state` (bank 3) greys the
  FOOD / SCROLL slots on 0. **Not done (follow-up, waits for IC1's 16×16 icons):** the pick's own
  icon and the stack-count digit on those slots (≈ 40-60 B: `slot_redraw` digit for 2 more
  slots + a pick type per slot; bank 3 / R6).
- **`fx_use`** (A = bag slot) by class: food → `fx_eat` (FOOD 100: `NO NEED`; else "YOU EAT
  THE <name>", `hunger_add(it_stat amount)` — its FED line follows —, `SFX_EAT`); potion →
  `pot_eff` (CF: `NO NEED`; else the heal flash, "YOU DRINK THE <name>" + the effect line
  "YOU FEEL HEALTHIER" (bank-0 `spl_drain_heal`) / "MANA SURGES!" / "YOU ARE CURED", `SFX_QUAFF`); scroll /
  book → `fx_read` ("YOU READ THE <name>", consumed whatever happens); gear / bow / empty: L 0.
  Consumption = `bag_take(slot, 1)` (compacts an emptied slot, `pot_sync`). 1 turn
  (`FXR_TURN`); refusals 0 turns, nothing consumed.
- **Scrolls:** Teleport → `EXIT_KIND = EX_TELE` (6, defs.asm): the turn's monsters skip (an exit
  turn), end_turn → `do_exit` `.tele`; Fear / Sleep → far3 `room_status` (bank 3, A = 0 / 1:
  every active non-DYING slot of `CUR_ROOM`, skipping `KX_IMM` & (IMMF_FEAR / IMMF_SLEEP) and
  bosses (KX_IMM bit 7); FEAR: MIND := FEAR, `ST_T1` low nibble 6; ASLEEP: only an unheld body,
  `ST_T1` high nibble 8 + the V3 sleep flash; L = count) → "THEY FLEE IN TERROR!" / "THEY FALL
  ASLEEP!" / "NOTHING HAPPENS"; Enchant → `enchant_weapon` → "YOUR WEAPON GLOWS!" / "NOTHING
  HAPPENS". No per-monster lines.
- **Book** (`fx_book`, §5 rev 6, RANK1): 1. no ability known → slot 0 (0 RNG); 2. pity:
  `BOOK_DRY` (`ARANK + 1` bits 2-3 = `ARANK` bits 10-11, `BOOK_DRY_MASK` $0C, `PITY_N` 2) = 2 and
  an unlearned ability unlocked (Warrior 2k+1, Mage k+1 ≤ `LVL_DEPTH`; slot k < L) → the first
  such (0 RNG); 3. one uniform pick over `fx_cand` (≤ 5: unlearned+unlocked = k | $80, or known
  < rank 3), index = (`rng_next` byte × n) >> 8 — exactly one RNG call; `BOOK_DRY` := 0 on a
  learn, +1 on a rank-up with an unlearned ability unlocked, else 0; far7 `abil_learn` (applies
  `ARANK += 1 << 2k`, the line); 4. no candidate → the tome: Vigor HP / MAXHP +3, MP / MAXMP +1
  (Warrior), Power MP +3 / HP +1 (Mage), `TX_BK_VIGOR` / `TX_BK_POWER`, PD_MP | PD_INFO.
  Reference model: `tests/book_model.py`. **Auto-downcast (RANK1):** `abil_load` picks the
  `ab_rank` row of the highest rank ≤ the hero's with `RK_MP` ≤ `MP` (rank 1 floor); melee
  reads `ABIL_RK`, spells `CAST_ROW` (a copy). Power Strike row fields: `RK_DIE` = multiplier
  code 0/1/2 (×2 / ×2½ / ×3), `RK_BOUNCES` = extra to-hit over ab_def's +2.
- **Teleport** (Q6): `do_exit` `.tele` (bank 7): `hide_sprites` → far6 `tele_pick` (CAND_LIST
  all $FF + FOLLOW_N 0 = no followers; room uniform among present rooms ≠ CUR_ROOM / Sanctum /
  the lair unless `LF_UNIQUE`, none → CUR_ROOM; far3 `lp_cmap` of the target + its unspent
  trap cols (bit 0); ≤ 16 × (storey `rng_mod 2`, col 2 + `rng_mod 26`) with the 3 body cols
  clear (`tp_ok`), else a scan nearest col 14 over cols 2..27 on storey 1, then storey 0
  (`tp_room`; review: 41 of 27,468 generated rooms have storey 1 blocked, 2 have no spot at all);
  a room without a spot is dropped from the draw and another drawn; none left → CUR_ROOM, then
  the hero's own col / storey (test hook `tp_room.cmap` = the lp_cmap call); out EXIT_DEST / EXIT_COL / EXIT_KIND =
  EX_UP (storey 1) / EX_DOWN (storey 0); "YOU ARE TELEPORTED!") → GS_TRANSITION → far3
  `lp_transition` (banks the old room, spawns the new one against that arrival box) →
  `room_show` (bank 5 composed while bank 7 still shows the old room) → `show_bank5` → joins
  `do_exit` at `.in` (CUR_ROOM, lair_hint, the vertical arrival E_X / E_Y, snap, M_REST,
  arrival_conflicts, vis_room_sync, present_full, GS_PLAYING, resync_tick). No scroll, no
  pre-arrival flash. Arrival on an item picks it up (end_turn's floor_pickup). Reusable by T16's
  trap teleport (set EXIT_KIND = EX_TELE).
- **hunger6 `hg_stage`:** entering FED sets `HP_RG` 0 (+3 B).
- **Ledger** (DISPLAY kit / release; before = main f4a043d): R6 free 2,737 / 2,755 → **1,915 /
  1,933** (review round −128: `tp_room` + the room retry, the 2nd drink line, `pot_sync`'s
  stack counts; first pass 2,043 / 2,061) (fx6 876 B incl. the T8 ops 140 and `pot_eff` / `cap_add` 61 from bank 7, `it_fmt`
  −6 via `it_amt`, `pot_take1` −9, the fx stream −174); bank 7 46 / 96 → **142 / 192**; low RAM
  49 / 59 → **93 / 103**; bank 3 778 → **640**; bank 1 1,177 → **1,182**; bank 0 text 2,448 → **2,436**
  (`quaff` "YOU DRINK A POTION" deleted: pool slack +12, POOL_CAP 39,804); bank 2 unchanged.
- **Time** (`tests/t12.py`, DI, incl. far6): EAT 7.3k T, DRINK 8.9k, READ Enchant 9.3k, READ
  Sleep with 3 bodies 12.1k, EQUIP 10.9k; `tele_pick` 11.5-13.3k; a Teleport turn from the
  read to settled 17-26 frames (the room build + draw + present ≈ 0.6M T, frozen gameplay,
  resync_tick). `budget.py` "umix" (mix + quick potions / eats / reads): worst ordinary tick
  103.5k (cap 126k).

**3E-T16 traps runtime** (`feat/3e-t16-traps`; `tests/t16.py`, `tests/budget.py` t*; game.md
§1.5 (+ "As built"), §2.2, §2.3, §6 V3, §8.11 (3)). Review 2026-10-26 round: the work moved off
the input tick (pmix + DART was 141.4k T), flashes added (user 2026-10-26).
- **Decision (input tick).** `turn_input` saves `TRP_PRE` (hero `E_X` / `E_Y`) on every try;
  `.spent` (free and held turns) calls `trap_chk` (bank 7): `TRP_WAIT` read + cleared; nothing on
  an exit / teleport turn (`EXIT_KIND` ≠ 0) or with `TRAP_N` 0; else the first unspent entry of
  `CUR_ROOM` (≤ 1 per room), a pre-filter (its col t must be in x−6 .. x+8), then far6
  `trap_turn` (A = `TRW_*`, DE = the entry): DYING hero / other storey → nothing. Trigger iff t ∈
  x .. x+2 now and not (same storey, t ∈ px .. px+2 before) — the bits now (DART known, a one-shot
  spent); else (hidden only) Mage sense t ∈ x−2 .. x+4 (no RNG), else on a Wait the search t ∈
  x−6 .. x+8 with `rng_mod 2` = 0 → known. An event **arms the sequence** (`tr_arm`: `TRP_EV` /
  `TRP_STEP` / `TRP_ENT`, `TURN_PEND = TP_ACT | TP_MON`, `ACT_ABL = ABL_TRAP` ($80), `ACT_AT` 1,
  `MON_AT` 2): turn_input skips the monster phase (`MON_AT` ≠ 0). **Immediate mode** (no
  sequence: a find drawn in its ink at once + the line): the room-entry sense (`end_turn .ex`
  after `do_exit`, `TRW_ENTRY`, no trigger test: the transition tick) and a turn whose
  `TURN_PEND` is busy (an ability turn).
- **Sequence.** `act_pend` (bank 7) at `ACT_AT` with `ACT_ABL` bit 7 → far6 `trap_step` (no
  `probe_act_fire`: an ordinary tick for budget.py; `TP_FIRE` set: no panel item / decor step that
  tick); each step re-arms `ACT_AT = TURN_TICK + B` / `MON_AT = ACT_AT + 1`; after the last step
  `act_pend .mon` runs the monsters (skipped on an exit turn: `EXIT_KIND`). Fire: step 0 = SFX_TRAP,
  the hero flashes the type ink (`TRAP_FLASH_T` = 2), the plate shows `$47`
  (`TILE_ATTRS[T_TRAP]` + far7 `ap_put_a`), the effect — DART: "A DART HITS YOU!", far3
  `trap_hit` (1d4+1, +1 when WEAK so deal_hit's own-attacker WEAK DEF+1 cancels; `DTY_PHYS` +
  POISON 12 (POIS1; the param nibble = 6, half): DEF, immunity (Silk: "YOU ARE UNAFFECTED"), cap 30 in `ST_X`, wake, death), `E_REACTAT` =
  arrival (walk 2, jump `JA_N` + 1), the Warrior's `arrow_hit` impact (`tr_fx` → `MSG_BUF` →
  `fx_start`, delay = arrival − 2; **none for the Mage: not in his class FX pool, game.md §1.5**);
  GAS: ASLEEP 4 + both lines; TELEPORT: `tele_arm`; ALARM: the 3E bell stub (3F: the wave). Step 1
  (2 ticks on; TELEPORT `TELE_STEP_T` 4) = DART in its ink, a one-shot erased (far7
  `ap_stamp_a`). Find: step 0 the "TRAP FOUND: …" line; steps 0..3 the plate bright `$47` / off
  (attr 0), 2 ticks each; step 4 its ink.
- **Teleport** (scroll `fx_read .tp` and trap): `tele_arm` = `EXIT_KIND = EX_TELE`, hero flash
  `$43` × `TELE_FLASH_T` 5 (`tele_flash`), `SFX_DRAIN`, and (scroll: `TURN_PEND` free) `TP_MON`
  with `MON_AT = TELE_HOLD_T` 5 so the flash shows before end_turn's `do_exit`; `tele_pick` calls
  `tele_flash` again for the arrival.
- **Drawing.** Known plate = `T_TRAP` in the standing-row cell; `build_room_map` stamps every known
  unspent trap of the room before the decor deriver (decor needs T_AIR) **unless an item glyph is
  there** and writes its type attr (`tr_ink3`) to `TILE_ATTRS[T_TRAP]`; mid-room the sequence /
  `tr_show` sets TILE_ATTRS and far7 `ap_put_a`. One attr for the id works because a room holds
  ≤ 1 trap (low RAM untouched). Cosmetic: a scroll between two rooms with known traps of
  different types shows the old plate in the new ink while it scrolls out. **Item / trap
  overlap:** `drop_put` (R6) refuses a cell whose col has an unspent trap (`trap_at`, hidden or
  known); `ap_stamp` (bank 7) keeps a known plate when no item is left (far6 `trap_glyph`).
  Persistence = `TRAP_LIST` (LVL_STATE): a reveal survives exits / re-entries / teleports.
- **RANK1 ledger** (DISPLAY kit / release; before = main 785d4ad): R6 free 1,294 / 1,312 → **1,204 /
  1,222** (`fx_book` rewritten: starter / pity / one uniform pick); bank 3 492 → **496** (`rank_sync`
  −~95, `abil_load` +~40, `melee_hit` +~25, the `ab_rank` values change only); bank 7 24 / 74 →
  **49 / 94**; bank 0 text +19 B (2,436 → 2,455 packed: the rank info lines, pool need 37,312 of
  39,785, was 39,804); `RANK_ROWS` (30 B) → `CAST_ROW` (6 B, `$B4E0`). `budget.py`
  unchanged: pmix 125,015 T (cap 126k), every other scenario as before.
- **Ledger** (DISPLAY kit / release; before = main ff69718): R6 free 1,915 / 1,933 → **1,294 /
  1,312** (`TRAP6_LEN` 610 + `tele_arm` call sites); bank 7 142 / 192 → **24 / 74**; bank 3 591 →
  **492**; bank 1 1,182 → **1,122** (`tf_line`, `il_cpy`, `in_row`); low RAM **93 / 103
  unchanged**; bank 2 0; state block +6 B (`$BFF5..$BFFA`).
- **Time** (`tests/t16.py` T, DI, each incl. the probe's far7 / far6 ≈ 0.25k): `trap_chk` with
  `TRAP_N` 0 0.42k, 6 entries none in the room 0.90k, one ≥ 7 cols off 0.67k; the decision
  (incl. arming) 1.3-1.6k; steps: DART 15.1k + 5.2k, GAS 9.2k + 7.7k, ALARM 6.7k + 6.5k,
  TELEPORT 5.1k + 7.5k, find 8.0k + 4 × 5.2k. `budget.py` (PROTO room A, pmix + a trap at col 16 /
  20 / 17): tdart / tgas / ttele / talarm / tsearch / tsense ordinary work max **112,495 /
  112,495 / 112,495 / 112,495 / 112,495 / 112,569** (cap 126k; the teleport's room change =
  a transition tick, 0.62M T, reported, not gated, like a room exit); pmix 124,559 → 125,015
  (+456 T, the input tick's `TRP_PRE` / `trap_chk`); every gate green.

### IC1 item icons (`feat/ic1-wire`; `tests/ic1.py`; game.md §8.11 Q5)

- **Data (MEM-RECLAIM w2c: packed, `icpk_idx` + `icpk` 995 B; the raw table below is the
  decoded form and the tests' reference, not assembled):** `icons16` (43 × 32 B = 1,376 B raw, 1 bit, no mask; FLOOR1: 45 logical indices, Mana / Cure share Heal's shape via `ic_find`, + 2 floor-ammo icons 43 / 44, layout 4 quarters of 8 lines; index = type − `IT_BAG_LO`,
  `ICONS16_PH` 39 + worn slot = the 4 placeholders, ink `ICONS16_INK_PH` `$05`) in the **R6
  region** after `icons6.asm`. One copy; every reader is R6 code (`icons6.asm`), reached by
  far6; the ISR never reads it (R6 rules: no SMC, no data writes).
- **Blitter** (`src/icons6.asm`): `icon_slot` (far6: A = slot 0..23 BAG / WORN record, D / E =
  row / col; item → its icon, empty worn slot → its placeholder, empty bag slot or ≥ 24 → the
  4 cells' bitmap cleared, attrs kept; L = 0 cleared) → `ic_draw` (A = index, B / C = cell; the
  4 attrs = `item_ink` / `$05` on black) / `ic_clr` → `ic_blit` (the third crossing handled;
  **MEM-RECLAIM w2c**: a draw unpacks the packed icon straight onto the screen, `ic_scr`
  ~2.6k T / MIRROR ~4k; a clear zero-fills the 2x2 cells; `icon_slot` ~3.1k T incl. far6 (MIRROR ~4.5k), was ~2.45k). Callers: the page (`pg_cell` grid + worn row,
  `pg_info` description at cols 0-1 rows 18-19, `PG_DICON_ROW`), `worn_draw`, `qs_draw`.
- **Panel worn cells** (rows 22-23, cols 24/26/28/30): `worn_draw` (R6; far6 from bank-3
  `panel_init` per level, all 4, ~8.7k T, replacing the `icon_empty16` outlines — still in
  bank-1 `vdata`, 36 B, now unread); `worn_cell` (A = the gear type: its slot's cell only,
  ~2.6k T) from `fx_done` after EQUIP / REMOVE; both `pmark_rect` → the next present.
- **Quick slots** (FOOD / POTION / SCROLL): `bar_knight` / `bar_wizard` hold `SLOT_QFOOD` +
  `QS_*` ($FB..$FD); `slot_redraw` (bank 3) blanks the 3 × 2 cells and far6s `qs_draw` (A =
  class, D = col, E = state): the pick's icon in its ink — FOOD `bag_pick` mode 0, SCROLL mode 1,
  POTION `IT_P_HEAL` + the pick in state bits 2-3 (`IS_PICK_SH`) — or the representative APPLE /
  HEAL / TELEPORT when the class is empty (greyed by the existing IS_GREY stamp), and the
  count of THAT type (all stacks, capped 9) at (19, col + 2) in `ATTR_HUD`. ~6-11k T per redraw.
- **Change detection:** `pot_sync` (every BAG writer) keeps `QS_CACHE` + `QS_FOOD` / `QS_SCROLL`
  = the class's QTY sum (was the stack count; 0 = grey) and, when one changes, forces that
  slot (`QS_SLOT0` 5 + `HERO_KIND` + `QS_*`, ASSERTed against `slot_act_tab` / the bar tables)
  to redraw (`ICON_SH` := `IS_NONE`, `QS_RECHK` bit 7); `QS_CACHE` + `QS_POTION` (was unused) =
  the potion types present (bit k = `IT_P_HEAL` + k). The potion pick (`icon_state`, bank 3,
  into state bits 2-3, so a pick change is a slot redraw) = the lowest bit of `pot_need` (bank
  3: present & effect not refused — Heal HP < MAXHP, Mana MP < MAXMP, Cure a MIND / POISON /
  WEAK status: `pot_eff`'s tests), else the first present (quick-use says NO NEED). Its inputs:
  `item_hp` (HOT_COPY) and `item_mp` (bank 2) set `QS_RECHK` bit 7 when they draw (once per
  HP / MAXHP / MP / MAXMP change; not in the MP poll, which would re-set it every step until
  MP is drawn and starve the MP item behind ICONS), a status change already sets PD_ICONS
  (`STAT_SH`). The potion count change still rides on `E_POT` / `PANEL_POT_SH` (`pot_slot`
  and `panel_init7`'s slot scan are gone: the slot is `QS_SLOT0` + `QS_POTION` + `HERO_KIND`).
- **Page overlay:** `pg_icon` (the 2x scaler), `pg_glyph`, the `PAGE_G60` copy (and its
  32 B of page-time scratch) deleted; 1,365 → **1,243 B raw** (293 left), stream 1,192 →
  1,077 B.
- **Panel scheduling:** a quick-slot redraw (~15k T incl. `item_icons`' far3 + the clear) is a
  big item: `item_icons_far` passes panel_step's C (0 = the tick's 1st frame; `panel_flush`
  0) in A (`ii_frame`, bank 3); in a 2nd frame the quick slot is skipped (`ICON_SH` kept) and
  `QS_RECHK` bit 7 set; `icon_poll` (every panel step, +~30 T) turns bit 7 into PD_ICONS only
  when C = 0; `item_icons` clears it first. So no 2nd-frame tick carries a quick-slot redraw
  and no `item_icons` pass (6.2k T) repeats per 2nd-frame tick. `item_icons` sets PD_INFO for
  a redraw only when it is the selected slot's (the info line is that slot's).
- **Ledger** (DISPLAY, kit / release; before = main `d837008`): R6 free 2,085 / 2,103 → **480 /
  498**; bank 3 436 → **412** (`slot_redraw`'s potion path −, the quick path +, `panel_init`'s
  outline loop → far6, `pot_slot` → `ii_frame`, `icon_state` pick +24, `pot_need` +26,
  `item_icons` +~30); bank 7 49 / 94 → **64 / 109** (`panel_init7`'s slot scan −15); low RAM
  93 / 103 unchanged; bank 2 free to FRT 18 → **13**, `kind_tab` pad 57 → **46**; `HOT_COPY`
  spare 41 → **36** (boot block 1,941 → 1,946); bank 1 unchanged (241). State: `QS_RECHK`
  `$BC5D`.
- **Time** (`tests/ic1.py` T, DI, incl. far6): `icon_slot` 2.3k T (cleared 2.1k), `worn_draw`
  8.7k, `qs_draw` food / potion / scroll 6.9k / 5.7k / 9.1k; page open (P1, start bag)
  837,851 T, 12 frames (unchanged; per icon 2.3k vs the old 2x scaler's ~8k).
  `tests/budget.py`: see the IC1 budget line in the summary below (pmix vs main 125,015; new
  **qmix**: pmix + Heal / Mana, MP 0 — the potion pick flips on the first hit + the pickups'
  count redraws); cap 126k.

## STATUS1 (`feat/status1`; game.md §7.1 FAINT1, §1.5.1 STUN1, §6.4.3 + §7.2 POIS1; `tests/status1.py`, `tests/t16.py` S)

**Ledger** (DISPLAY, kit / release; before = main `2401565`): R6 free 480 / 498 -> **379 / 396**
(-101 / -102); bank 3 412 -> **381** (-31); bank 7 64 / 109 -> **67 / 112** (+3); bank 1 241 ->
**168** (-73: 4 stems 66 B + `tf_tab` 1, the items stream +7 packed); low RAM 93 / 103 and
bank 2 unchanged. Items overlay 1,027 -> 1,039 B raw (`ig_tord` 5 + the lookup 7).

- **Shared `hero_hold`** (R6 `trap6.asm`; In: A = `HOLD_*`, B = turns; HOLD kind + timer + the
  `TRAP_INK_GAS` flash): used by the GAS arm of `tr_eff` and by the hunger faint
  (`hunger6.asm` `hg_faint`). A STUN does not use it: it goes through `deal_hit` (`EFX_STUNNED`)
  so the immunity mask, HOLD_GUARD and the status line come for free.
- **FAINT1:** `hunger_turn` step 4, WEAK rollover -> `hg_faint`: defers (`HW_TMR := 49`, no
  line) while `ST_FLAGS & (STS_HOLD | STS_GUARD)`, a pending `E_REACT` (not `E_REACTAT`: that keeps its last tick after the reaction played, so it would defer forever after the first hit), `EXIT_KIND` or `on_ladder`
  (bank-2 `logic.asm`, called with `IX` saved); else `hero_hold(HOLD_ASLEEP, FAINT_T)`,
  `SFX_TRAP`, `HW_TMR := HW_REPEAT - FAINT_GAP`, `S3_HG_FAINT`. `FAINT_T` 5 / `FAINT_GAP` 30
  (`item_defs.asm`). The old repeat line `YOU ARE WEAK WITH HUNGER` is gone (the entry line stays).
- **STUN1:** `TT_STUN` 4; `TR_B1` type = bits 5-7 (`TR_TYPE_MASK` `%11100000`; `tr_type` `and 7`,
  bank 3's extraction already shifted all three bits); `TEV_FIND` 5 -> 6; `TRAP_INKS` 5th entry
  `$07` (`tr_ink3`, `tr_ink6` +1 B each); `tr_eff` 5th arm: stem `S3_TRAP_STONE`, far3
  `trap_stone` (bank 3 `combat3.asm`: 1d3 then `2 + rnd(2)`, both gameplay RNG, into the shared
  `th_go` = the WEAK compensation + `deal_hit` with `DTY_PHYS | EFX_STUNNED`), joins DART's
  `E_REACTAT` code, returns before the `arrow_hit` FX (`TRP_EV`). Overlay `items_ovl.asm`:
  `ig_tord` = DART GAS TELEPORT STUN ALARM, `ig_tplen` 1,2,3,4,5,5,5,5 (type = `ig_tord[rnd(len)]`,
  one draw); `tools/items_model.py` `TRAP_FIRST` has `(TT_STUN, 4)` before ALARM. D1-D3 trap
  lists are byte-identical; at D4+ only the type field changes (D4 `%3` -> `%4`, D5+ `%4` -> `%5`).
  **Behaviour fix found on the way:** `turn_input` cleared HOLD_GUARD before `trap_chk` armed the
  sequence, so the guard was gone at the stone's step. `.act` now calls `trap_chk` first and
  clears the guard only when no sequence is armed (`MON_AT` = 0); `act_pend` clears it after the
  last step as for a cast.
- **POIS1:** `ST_X` = the POISON turns (a byte, `PSN_CAP` 30, `combat_defs.asm`); `ST_T2`'s hi
  nibble is unused. `deal_hit`'s turns nibble for POISON is **half** the turns (a 4-bit field
  cannot hold 18 / 24): `.ps` (after `.ng`) doubles it, adds to `ST_X` if POISON is already on
  (else overwrites) and caps at 30; `PSN_SPIDER` / `PSN_RAT` 12, `PSN_QUEEN` 18, `PSN_WIDOW` 24
  are asserted even and <= 30 (the 3F kind-table rows store `PSN_x / 2`); `TRAP_DART_PSN` 12
  (`trap_hit` passes 6). `st_step`: `ST_X` - 1, a new value `and 3` = 0 costs 1 HP (never below
  1); Cure also zeroes `ST_X`. `fx_eat`: `ST_FLAGS` bit `STS_POISON_BIT` -> `fx_refuse` with
  `S3_TOO_SICK` (0 turns, `FXR_REFUSED`) before the FOOD 100 test; every EAT path (page verb,
  quick FOOD via `bag_pick` -> `fx_use`) ends in `fx_eat`.
- **Tests:** `tests/status1.py` (F faint, P poison, E eating, T costs: `hunger_turn` faint turn
  ~5.0k T, deferred ~1.3k), `tests/t16.py` S1-S9 (+ STUN in the type loops), `tests/budget.py`
  `tstun` / `tfaint` (gated at `CAP`).


## FLOOR1 (`feat/floor1`; game.md §8.11 "FLOOR1"; `tests/floor1.py`, `gfx_integrity` floor_check)

Floor items are drawn as their 16×16 icons on a 2×2-cell footprint (cols c..c+1,
rows 9s+6..9s+7, `ITEM_COL_LO` 2 ≤ c ≤ `ITEM_COL_LAST` 28) in their type's ink.

**Map.** A live entry's 4 cells hold the markers `T_ITEM0 + 2s` (row 9s+6) /
`T_ITEM0 + 2s + 1` (row 9s+7) (ids 60..63, the tile table above). `floor_pickup`'s
pre-filter = a marker under the body on row 9s+7; `drop_put`'s free test = 4
`T_AIR` cells + `TF_FLOOR` under both cols + no unspent trap on c / c+1.

**Glyph cache** (one room: `CUR_ROOM`, `EXIT_DEST` during a scroll; ≤ `FI_SLOTS` 8 types):

| Address | Symbol | Size | Contents |
|---|---|---|---|
| `$699F` | `FI_PAD` | 1 | always `FI_NONE` (`FI_TSLOT[FI_NONE]` reads / writes land here) |
| `$69A0` | `FI_TSLOT` | 64 | item type → slot, `FI_NONE` |
| `$69E0` | `FI_TYPE` | 8 | slot → type, `FI_NONE` |
| `$69E8` | `FI_USE` | 8 | ≠ 0 = slot mapped this room visit (no freeing on pickup; `fi_full` resets) |
| `$6A00`, `$6B00` | `FI_CELL` | 2 pages | storey s's page, indexed by the marker cell's map / screen low byte L = (row & 7) << 5 \| col (s0: `$C0..$FF`, s1: `$E0..$FF` + `$00..$1F`) → its `FI_GLY` low byte (slot × 32 + 8 × quarter) |
| `$6C00` | `FI_INK` | 256 | ink by `FI_GLY` low byte (32 × per slot) |
| `$BD00` | `FI_GLY` | 256 | **bank 2** (uncontended): 8 × 32 B icons (old stack bottom) |

All low-RAM parts sit in the play-free GEN_SRC / GEN_MIR window (pblit's ≤ 54 B at
`$6940` below; `TX_DEC` `$6D15` above, ASSERTed): the pause save, the page's map save and
the generator overwrite them, so each is followed by **`fi_full`** (bank 3, bank 2 since LAND-PENDING; far3: room_show
(level entry, start_game, teleport), `do_exit` for `EXIT_DEST` before the scroll, pause
resume, `page_post`). Per pickup / drop: bank-7 `ap_stamp` writes the 2×2 markers + attr
shadow + `queue_damage` 2×2 and far6 **`fi_add`** (R6) with the col's last live type
(`fi_slot`: a new type takes a free slot, its ink and its 32 B; `fi_put`: the 4 `FI_CELL` bytes).

**Draw.** `erase_rect` (bank 2) draws a marker cell from the cache in its normal per-cell pass
(`.item`: `FI_CELL` → `FI_GLY` 8 lines + `FI_INK` attr): each item cell drawn once, no second
pass. ids 0..31 cost 8 T less than before FLOOR1 (D hoisted), 32..59 +46 T (the marker test),
a marker cell ~+96 T over a plain tile cell (review-measured). `fi_cells` (low RAM, cold) = the same from the map for
`room_show` and the scroll strips (map page SMC `fi_cells.mp+1`: NEXT_MAP during a scroll,
`fi_mp_next` / `fi_mp_room` in scroll1.asm; offsets `fi_cell.dr+1` / `.dc+1`). `tile_rect`
moved to low RAM (cold: room draws, strips) to make the bank-2 room.

**Invariant (manager 2026-10-28, supersedes the earlier review fixes):** a room never holds more
than 8 distinct item types (`FI_SLOTS`; both storeys, tops and piles). `drop_put`'s `dp_cap` (re-marks
stale slots with `fi_gc`, ~3k T, when none is free) refuses a 9th type (monster loot is not dropped); a
boss unique first runs bank-3 `uq_fit` (`drop3.asm`): at 8 types it destroys every entry of the first
food / ammo / potion type of the room and re-stamps their cols. So every live type has a slot:
`fi_full` slots every entry of the room (a later entry of a col overdraws: the top shows), a pickup
revealing the type under a pile finds its slot, and the in-tick `fi_full` fallback (`fi_col`,
`dp_keep`) is gone (ap_stamp calls `fi_add` directly); `fi_full` runs only cold (room entry, pause,
page, `level_show`, `do_exit`). `floor_pickup` scans the list from the LAST entry (a pile's top first).
**After it: R6 90 kit / 118 release (was 16 / 43), bank 3 48 (was 148: `uq_fit` ~130 B in, `fi_full` top logic −28), bank 7 27 / 72, low RAM 77 / 77, bank 1 91.**

**Ledger (kit / release, build DISPLAY; main 3a000f5 → FLOOR1):** R6 387 / 404 → 150 / 178
(fi6 `fi_add` / `fi_slot` / `fi_put` ~150, `drop_put` 2-col search + `dp_pile` / `dp_free` /
`dp_cell` ~+110, `item_ink` + `it_tab` moved in from low RAM ~64, `ic_addr` +24, `icons16`
+64 for the 2 ammo icons −64 for the shared potion shape, `mon_drop` + tables out −144,
`trap_glyph` out −12); bank 3 381 → 174 (`drop3.asm` `mon_drop` + `drop_tab` / `uniq_tab`
~150, `fi3.asm` `fi_full` ~60); bank 7 63 / 108 → 27 / 72 (`ap_stamp` 2×2 + col type, `do_exit`
fi_full); low RAM 85 / 95 → 77 / 77 (`fi_cells` / `fi_cell` + `tile_rect` in, `fl_attr*` /
`item_glyph` / `it_cls` / `it_tab` / `item_ink` out); bank 1 168 → 91 (scroll strips, the
2 `fi_full` calls); bank 2 13 + 46 pad → 13 + 36 pad (`erase_rect .item` / `.dec`, `fi_row`, −
`tile_rect`); RAM: the cache tables above + 256 B of stack.

### 3F-B6 loop-walk (`feat/3f-b6-loopwalk`)

`anim_tick` (bank 2) and `resolve_monsters` (bank 3) walk IX by 32 / the SLOTREC pointer by 16 and skip empty slots early (no `ent_ix`, no `ANIM_SLOT` store for an empty, undrawn slot). Bank 2: +36 B (`kind_tab` pad 87 -> 51 B, free-to-FRT 549 unchanged; bank 2 free 636 -> 600). Bank 3: -1 B (10 -> 11 free; 6 merged with B4).

**Placement rule (T7/T8):** put new bank-2 code AFTER `kind_tab` (next to `mark.asm` / `xp2.asm`) so every byte comes out of the 549 free-to-FRT. The 51 B pad before `kind_tab` is only for code that must sit in that page; growth past it moves `kind_tab` a page (-256 B at once). `MON_SLOT` is no longer stored (nothing read it; `ANIM_SLOT` no longer ends at 15). Saved on the worst ticks: pmix resolve -1.8k, anim_tick -1.3k; wcast4 / lcastf anim_tick -1.2k.

### 3F-B5 AI-feet (`feat/3f-b5-aifeet`)

`ai_monster` (bank 3, `turn3.asm`) no longer computes its slot: `resolve_monsters` stores `ACT_SLOT` from its slot counter before the status step (`mon_status` stores the same value), and `ai_monster`'s contract now reads "ACT_SLOT = its slot" (its only caller). Walker path: one `KT_DIV9` / `KT_MOD9` lookup of y+h from the entry `get_box` (ASSERT `KT_DIV9 == KT_MOD9 + $20`, the table base low 6 bits <= 8, `STOREY_COUNT == 2`); `attack_if_reach.box` = the box test with BC / DE given and the body known free (ai_monster walker when standing, `ai_flyer`); `.fstep` enters bank-2 `try_step.vert` (past its on_ladder) only for a standing walker. Shared helpers (`feet_mod`, `try_step`, `cork_check`) unchanged. TMP4 (my storey) is now written before the attack test (scratch; nothing in `do_attack` reads it). Bank 3: 265 -> 250 B free (+15). No new addresses.

### 3F-T7 ranged attacks (`feat/3f-t7-ranged`)

game.md §9.2 RANGED-SPEC (Archer, Sniper, Slinger, Necromancer, Bone Caller; the Archmage row is data
for T11). Counter rule (manager-approved 2026-10-29): a shot needs the counter at 0 on the hook's entry,
then it decrements (spawn / arrival 1, N = 1 every 2nd turn, N = 2 every 3rd). Tests `tests/ranged.py`
(A: 2,400 seeded situations == `tools/ranged_model.py`), budget `rroom` / `nroom` / `rcast`.
- **Hook**: `ai_monster` (bank 3) after the melee `ret c`: `call ai_rhook` / `ret c` (review: HL and
  `TMP4` kept by the callee; nothing below reads the B5 box). `ai_rhook` (bank 2, `ranged2.asm`):
  `rk_tab[kind]` via BC (30 B, one page, ASSERTed) = the `rd_tab` row, 0 = not a shooter (66 T); a
  shooter saves HL and far6s R6 `ai_ranged` (A = row, E = standing): L = 1 the turn is used.
- **R6** `ranged6.asm`: `rd_tab` (6 × `RW_STRIDE` 8: r, N, `RWF_*`, die, bonus, deal_hit C / E, flight
  fid), `ai_ranged` (steps 1-6: counter, in line = same storey + hero not mid-ladder, gap, wall scan of
  the flight row (`rg_scan`) + `box_free` over gap cols × my rows, the DARK reflect gate, [T9 / T11
  pre-rule slot `.pre`], SHOOT / step-away / HOLD), `rg_shoot` (far3 `rs_hit` / `rs_deal`, the hero's
  E_REACTAT := impact tick I, `COMBAT_NOT_BEFORE` = max(it, min(I, R + CNB_MAX)) on a hit, E_MSG hit /
  miss at the attack's IMPACT, the attack sequence, the RS_Q entry with the whole FX descriptor),
  `rg_ri`, `rg_scan` (T9's Vampire scan can reuse it), `shot_tick`.
- **Release**: `act_pend` (bank 7) far6s `shot_tick` while `TP_SHOT` (`TURN_PEND` bit 3; holds the turn):
  `fx_start` at release tick R = phase tick + `RG_REL` 2 + (slot & 1) (a busy set of 3 tracks queues in
  FXQ, a 6th FX: `FX_DROP`) with one `sfx_req` (a DARK bolt `SFX_SPARK`, an arrow / rock `SFX_THROW`;
  existing effects, ISR contract unchanged), the hero's `ATTR_HIT` flash at I = R + gap + 1 when HP was lost; a miss /
  the Slinger's rock: no impact frame; the rock flies in `FXD_ATTR` `$06` (§9.6; `dagger_spin`'s own is `$47`). `place_follower` zeroes `E_RCD` (counter 1 on arrival).
- **Bank 3**: the hook 4 B + `rs_hit` / `rs_deal` 13 B. **`fx_meta`**: 3 B for the Necro bolt fids below
  `KFID_FXM` (fx_set indexes `fx_meta - KFID_FXM + fid`), then `DS KFID_FXM - FID_nbolt_hit - 1` zeros for
  any fids between them and the FX range (T13bc's climb pair: +2 B then).
- **RAM `RG_RAM` `$5F8C..$5FF3`** (bank 5 runtime reserve after `MK_RAM`; garbage at boot, `RS_P` reset
  whenever `TP_SHOT` is clear): `RG_ROW` 8 (the row copy), `RG_OLD`, `RG_DIR`, `RG_FIRST`, `RG_GAP`,
  `RG_F`, `RS_P` (low byte of the next free entry), `RS_Q` 4 × 18 {R ($FF started), flash tick (0 none),
  FX descriptor 16} + the overflow sink 18. `E_RCD` = `E_POT` (unused by monsters): bits 0-1 the counter
  stored XOR 1, bits 2-5 T9's summon counter S, bit 6 summon-made, bit 7 the once bit (**3F-T9**, below).
- **Not in T7**: `KF_CLIMBER` for Archer / Sniper (T13bc's kind rows: they `.seek` once the flag is set;
  the Slinger and the Necro family per their rows), the Vampire bat trigger (T9), golden atk / dmg (T8).

| Region (kit build `-DDEBUG_KIT=0`) | main `73e1479` | after 3F-T7 | Δ |
|---|---|---|---|
| R6 `R6_LEN` / free | 8,960 / 517 | **9,472 / 371** | +512 (`R6_GROW` 8 → 10), −658 `ranged6.asm` (review: +12 release SFX, +8 rock attr) |
| pool `POOL_CAP` / need / slack (D7 Warrior) | 34,980 / 32,992 / 1,988 | **34,468 / 32,992 / 1,476** | −512 (both heroes, D1-D8 asserts green; PROTO 6 kinds slack 1,188) |
| bank 2 free to FRT / pad | 293 / 215 | **240 / 212** | −53 `ranged2.asm` (`ai_rhook` 21 + `rk_tab` 30 + 2), −3 `fx_meta` |
| bank 3 free | 106 | **89** | −17 |
| bank 7 free | 53 | **36** | −17 (`act_pend` +13, `place_follower` +4) |
| low RAM / bank 1 | 37 / 99 | unchanged | 0 |

Ticks (`tests/budget.py`, worst work tick, cap 126,000): `pmix` 109,064 = main (the reject costs nothing
visible), new `rroom` 85,984, `nroom` 112,774, `rcast` ordinary 83,695 / cast 96,635; every other scenario
unchanged-to-main and gated. Hook cost over the reject (`tests/ranged.py` T, contended stub): out of line
0.83k, out of range 0.98k, full line test + HOLD at gap 9 2.3k, step-away 4.0k, a shot 8.5-8.7k (hit_roll /
deal_hit + its lines); `shot_tick` adds far7 + far6 (~0.5k) on each TP_SHOT tick, + fx_start at a release.
`tests/ai_equiv.py` (shooters re-kinded, fixed master seeds) vs main: 2,100 turns, 0 mismatches.
Review round: `sroom` (3 Slingers, 2 stacked, all shooting on one input tick, pmix items) 98,724; the ISR
peak in the ranged scenarios (5,993 T) stays under the suite's existing peak (6,194). `ai_equiv`'s full-hash
diffs vs main are only `E_SEQL` / `E_SEQH` (offsets 12 / 13: sequence pointers into the seq cache, which
starts at `code_end` and moved with the bank-2 growth), never behaviour. Not done (review item 6b): reading
`rd_tab` in place instead of the 8-B row copy (every RW_* access would need an index register; ~0.2k T).

### AI-L1 ladder queue (`feat/ai-l1-ladder`; game.md §9.2 'Ladder queue'; `tests/ladder_jam.py`)

- **R6 `lq6.asm` `lq_block`** (far6 entry, 85 B): from `turn3.asm ai_monster .sk` when a climber's
  standing step toward its shaft col failed (`.fstep` inlined there: D = dx, E = col pass in DE). Re-runs
  `box_free` over the failed step's box; no body → plain wait (no facing change: A/B-neutral without
  contention). A body: face the shaft; (review) a body on MY side in the near-end box but not at col
  (dx × (its x − col) in −2..−1) → I back off 1 cell whatever the power / my distance (the 3-climber chain:
  col c, Orc c−2 / Necro c+1 / Orc c+4 deadlocked, the Necro boxed in between two winners); else the blocker
  wins when its static `kind_tab KT_HP` is higher, or equal and its slot is lower (slot order =
  `P_ENTITIES` address order: `sbc hl, bc` vs IX); a winner blocking me with `|x − col| < FEAT_W` →
  `try_step` 1 cell away (facing kept), else wait. The hero is not special (KT_HP 24 / 16, it wins; it
  never blocks a seek step off its own climb path).
- **Mid-ladder turn-round (review, `turn3.asm .other`, bank 3 +18 B):** a mid-ladder climber whose step
  fails and whose `E_AIDIR` leads away from `PL_STOREY` (bit 7 of ai_dir == PL_STOREY on the {c,1}
  segment) negates `E_AIDIR` (the turn is spent): the hero changed storey mid-climb, a waiter at the foot
  no longer hangs it there for ever. No 'mid-ladder blocker always wins' rule.
- **J1** (climb start over the own end box) is not a bug while every `KF_CLIMBER` kind is `FEAT_W` wide:
  ASSERT in `main.asm` after `kind_tab` (a body in the near-end box overlaps the climber or sits in its
  first climb step). `.at` unchanged.
- No new RAM. Contracts kept: ACT_SLOT set by the caller (box_free skips me), nothing between `try_step`
  and `.vert`, `.ny2` untouched.
- **Known minor behaviours (not fixed, each > 6 B):** an opener backing off into a closed plank opens the
  door (`try_step` → `mon_door`; the step is spent); a STRONGER blocker that never moves (a non-climber, a
  Slime on its off turn) makes a weaker seeker in the near-end box step back and forth every 2 turns; a
  flyer (over a pit or anywhere) in the way counts as a blocker (power compare as any body); a shooter
  that arrives and stays on the far-end box (it shoots instead of walking) holds the next climber at the
  foot (pre-existing: the shaft queue). `tests/ladder_jam.py` Q6 caps x reversals at 4 a climber.
- **Cost:** `lq_block` 1,493 T (winner waits) / 3,624 T (loser backs off, a step included) per blocked
  seek step. `tests/budget.py` `lqmix` (REPORTED, not gated: 3 Skeletons jammed at room A's {23,1} top,
  the Knight walking storey 1 through the pmix items): worst tick 152,959 T, resolve_monsters 22.6k; the
  control `BUDGET_LQ_X=9,14,19` (the same 3 walking, no jam in the worst tick) is **148,088 T on main**
  (148,163 here): the over-cap tick is the render / present of 3 moving 24×48 walkers + the hero's pickup
  tick, pre-existing; AI-L1 adds ≈ +4.9k T (≈ +6.2k in resolve_monsters) on top. Main's `lqmix` (the jam
  never moves) is 84,582 T.

| Region (`-DDEBUG_KIT=0`) | main `fca0814` | after AI-L1 | Δ |
|---|---|---|---|
| bank 3 free to `AY_RESERVE` | 85 | **48** | −37 (`.sk`: the inline `.fstep` + `ld hl, lq_block` / `jp far6` 19; the mid-ladder turn-round 18) |
| R6 free (release / kit) | 317 / 247 | **232 / 162** | −85 `lq6.asm` |
| bank 2 / bank 7 / low RAM / bank 1 | — | unchanged | 0 |

### MEM-W1b ledger (dead strings + `frame_footprint`; tools/build.sh DISPLAY, release and kit identical for these rows)

| Region | Before (main `c3ae149`) | After | Δ |
|---|---|---|---|
| bank 0 text (packed) | 207 strings, 2,652 B | **193 strings, 2,520 B** | −132 (14 unreferenced ids: bang, bk_grasp, bk_crumbles, bk_destroyed, cmb_range, end_killed, m_title, none_left, paused, rk_ii, rk_iii, xp_lv, xp_xp, xp_level; the LOG-FIX / T11 groups kept) |
| pool start / pool slack (every level, 1:1) | `$CA5C` / 1,476 (PROTO 1,316) | `$C9D8` / **1,608** (PROTO 1,448) | +132 (`POOL_NEED` unchanged, per-level `LEVEL_NEED` unchanged) |
| bank 2 `frame_footprint` (no caller, no test) | 49 B | deleted | −49 |
| bank 2 free (free to FRT + `kind_tab` ALIGN pad) | 208 + 35 = 243 | 208 + **84** = **292** | +49: all in the pad (the image still ends `$A510`; free to FRT unchanged) |

### fix/archer-climb (user 2026-10-29): Archer / Sniper climb on the Skeleton's own pair; the Mummy climbs

* Frames: the Skeleton's `skeleton_climb1/2` moved ahead of `raise / collapsed / hurt`
  (`frames.asm`): Skeleton = `U_SKARCH` (walk1..4 + cut) + new **`U_SKCLIMB`** (K_MAX + 10, the
  2 climb frames, STA|SYM, 576 B) + `U_SKREST` (raise, collapsed, hurt). FIDs of those five
  frames renumber (all references are symbolic).
* `pool_gmap` 17 -> 19 records (+6 B R6): Skeleton + `U_SKCLIMB`; Archer (Sniper) `U_SKCLIMB`
  instead of `U_CLIMBH`; Mummy + `U_CLIMBH`. `ksm_ar` KS_CLIMB = `skeleton_climb1/2` (the
  Archer / Sniper ink), `ksm_mu` gets a climb cycle (shared `climb_h1/h2`, ink $06).
  `KF_CLIMBER` on K_MUMMY (13); `levelgen.CLIMBERS` + `K_MUMMY`.
* Pool need (B, Warrior / Mage): D4 31,776 -> 32,352 / 27,712 -> 28,288 (Orc keeps `U_CLIMBH`,
  the Archer adds `U_SKCLIMB`); D5 unchanged 29,792 / 25,728 (Archer shares the Skeleton's pair,
  Mummy adds the shared pair); all others unchanged. Cap 33,700. Worst level D4 32,352 (slack 1,348).
* Bytes: R6 free 162 -> 152, bank 1 free 111 -> 105 (repacked ZX0 block), bank 2 / bank 3 / low RAM 0.

### 3F-T8 bosses (`feat/3f-t8-bosses`; game.md §9.2 'Boss guard', §1.1 / §9.4.4 grate, §9.7 R1 / R2, §9.1 Ogre; `tests/boss.py`)

- **Grate** (BOSS-GUARD a): `level_gen` (both `F3_GEN` paths) and `levelgen.py generate` write `LVL_FLAGS` 0: the lair's
  level exit is SHUT (`T_GRATE_SHUT` 13, `TF_SOLID | TF_FLOOR`, tiles_3f `grate_shut` `$07`). `build_room_map` stamps
  the shut / open gate AFTER the deriver in both states (the decor never depends on the grate; `room_model.py` too).
  `try_climb` DOWN at `x == RD_EXITCOL` on the shut grate: illegal, NO turn (F4: `pop hl` drops `tpt_intent`'s
  wait; the illegal try still runs the hero's status step once, `HST_DONE`, as any illegal try). The boss's death
  (`mon_drop`'s boss branch, before the unique is placed) far6s R6 `grate_open`: `LF_GRATE_OPEN`, 3 cells -> `T_GRATE`
  (+ the depth's glow above the middle cell if air: `glow6`, a copy of bank-3 `glow_ids`), `rect_repaint` (new
  low-RAM entry = `door_paint`'s tail: attr shadow, restore_page, queue_damage), `A GATE GLEAMS, THE WAY DOWN`. A hero
  standing on the grate stays (LADDER | HOLE, no fall), DOWN at c descends. `lair_hint` (first lair entry) logs
  `THE GATE IS BARRED` (new string `gate_barred`, +19 B packed text). Teleport keeps excluding the lair while
  `LF_UNIQUE` is clear (unchanged).
- **Post** (G1 / G1a / G1b): R6 `boss6.asm` `lp_post`, far6 from `lp_enter`'s unit loop for every unit of the lair
  (FRESH and banked, no spawn-stream step); == `tools/levelgen.py lp_post` (`tests/lp.py` A2 / A7 byte-exact). The
  boss: storey 1, x = c, or (hero arriving on storey 1 with gap < 5) shifted 1 col at a time away from him to the
  first x with gap >= 5 and no `LP_CMAP` mark outside the exit's own c-1..c+3 (none in range -> lp_place); the escort
  (any other lair unit) shoulder to shoulder: door side (engineer's choice: the lair's left edge if any, else right;
  differs from L1 (7)'s BFS parent only for a through-room lair) then the other, range / gap 5 / no mark, else
  lp_place. `lp_place` lost its "boss farthest from the hero" branch (-55 B bank 3); `LP_BEST` / `LP_BX` are
  `lp_post`'s `LP_EXLO` / `LP_EXHI` scratch. The D8 Archmage (G1d) is posted like the others until T11 (F3_GEN off).
- **Guard AI** (G2): bank-2 `ai_ghook` (ranged2.asm, behind `ai_rhook`: a non-shooter jumps there, a shooter whose
  `ai_ranged` returned L = 0 falls in): only `CUR_ROOM == LVL_LAIR` and `E_KIND | E_GOLD == LP_BOSS` far6s R6
  `ai_guard` (+46 T a monster outside the lair). Archmage / mid-ladder / off storey 1: ordinary rules; ENGAGED iff
  the hero stands on storey 1 and (|PL_X - c| <= 8 or `LF_PROVOKED`); else a walker step toward c (`try_step_face`),
  at c: face the hero. **PROVOKED = `LVL_FLAGS` bit 5 `LF_PROVOKED`** (one boss a level; the HERO3D / entity spares
  were not needed): set in `deal_hit .mon` for a target matching `LP_BOSS`, cleared by `lp_post` when the boss is
  placed. The Vampire Lord's bat rules are T9 (nothing to switch off yet).
- **Never follows (user playtest bug, D4 Ogre)**: root cause: `follow_select` (bank 7) had no boss rule — the Ogre
  was an ordinary follower candidate at the lair door. Fixed: a slot in `LVL_LAIR` matching `LP_BOSS` is never a
  candidate (+19 B bank 7). The vanish after the teleport: not a data loss (tests/boss.py F2 + a follower+teleport
  probe: the follower lands in the old room's record with its hp); a followed boss sat as an ordinary entry in a
  non-lair record, where `lp_place`'s 8 random tries often find no cell for the 4-col Ogre on re-entry (kept in the
  record, invisible). Since the fix the boss is always in its lair, where `lp_post` places it. **Safety:
  `boss_chk`** (R6, far6 from `lp_transition` after `lp_enter`): while `LF_UNIQUE` is clear and the lair record is
  VISITED (or being entered), the boss must be a live slot of the lair or a lair record entry, else
  **`BOSS_TRAP`** (`$5FF4` = `RG_RAM_END`, bank 5, wraps, garbage at boot: tests read the delta) += 1; the grate
  opens only on the boss's death.
- **Golden** (§9.7 R1; E_GOLD = $20): `hit_roll` atk + `GOLD_ATK` 2 (inline), `atk_mod` dmg + 1 (bank 3, after the
  roll in `do_attack`; R6 `rg_shoot` + 1 for a golden shooter), `deal_hit .mon` DEF + 1 (the WEAK extra B), IMMF_BOSS
  for a golden target (`E_GOLD` rlca x 2 OR the KX_IMM byte: deal_hit and `room_status`). Not done: the per-depth
  boss name / XP tables (R1 data; open).
- **Glow** (§8.6): render `.kat` -> `glow_kat` (bank 2): attr `glow_tab[(GLOW_CNT >> 1) & 3]` = `$06 $46 $47 $46`;
  `GLOW_CNT` (`$BF4B`) += 1 at main.asm `.panel` (never a turn's input tick / TP_FIRE / before COMBAT_NOT_BEFORE).
  A golden DIRTY_ATTR slot adds NO damage rect (`.sa`); `draw_slot` -> `stamp_slot` -> `stamp2` writes the attrs of
  both screens (bank 5 + `SCREEN7_ATTR`, bank 7 paged, caller's bank restored): ~1.4k T for a 3x6 body. A damage
  rect over it still forces the ordinary full redraw (overlap repair).
- **Ogre SLAM** (§9.1): `E_RCD` bits 0-1 (the Ogre is no shooter) = turns since the last SLAM: `og_adv` (bank 2) 3 ->
  1, 0 -> 1, 1 -> 2, 2 stays; advanced once a turn by `ai_guard` (no blow) or `reach_ok` (a blow). At 2 the reach
  is 2 (`reach_ok`, replaces attack_if_reach's KFIELD KT_REACH) and the blow sets 3 = the SLAM: `atk_mod` x 1.5 and
  deal_hit C / E = PHYS + STUNNED 1 (always; HOLD_GUARD / boss halving rules as any STUN). The RAISE -> SLAM pose is
  the Ogre's only attack sequence (T13bc). `place_follower` zeroes E_RCD (unchanged).
- **Tiles** (§9.7 R2): common 13 = `T_GRATE_SHUT`, 15..18 = `T_LECT_TL/TR/BL/BR` (tiles_3f, `TF_SOLID | TF_ATTACK`,
  placed by T11); `tools/tiles_convert.py` reads `assets/gfx/sprites/grid/tiles_3f.grid`; boot block bytes only.

| Region (`-DDEBUG_KIT=0` unless noted) | main `602407c` | after 3F-T8 | Δ |
|---|---|---|---|
| R6 `R6_LEN` / free (release / kit) | 9,472 / 232 / 162 | **10,240 / 486 / 416** | +768 (`R6_GROW` 10 -> 13), −514 `boss6.asm` (lp_post, ai_guard, grate_open + glow6, boss_chk), +6 rg_shoot |
| pool `POOL_CAP` / need / slack (worst D3) | 33,700 / 32,224 / 1,476 | **32,918 / 32,224 / 694** | −768 R6, −14 text; PROTO slack 534; per-level asserts both heroes green |
| bank 2 free to FRT / `kind_tab` pad | 208 / 35 | **29 / 17** | −179 `boss2.asm` + `ai_ghook`; −18 before `kind_tab` (`.kat` / `.sa` hooks, `GLOW_CNT` inc) |
| bank 3 free | 48 | **23** | −25 (lp_place −55, build_room_map −12; hooks, golden, atk_mod, PROVOKED, boss_chk call) |
| bank 7 free (release / kit) | 36 / 31 | **12 / 7** | −24 (`follow_select` boss rule, `try_climb` F4) |
| low RAM / bank 1 / AY | 17 / 111 / 169 | unchanged | 0 (`rect_repaint` is a label) |
| text (bank 0) | 2,652 | 2,666 | +14 `gate_barred` |
- **Boss vanish on lair re-entry (UB6 / the D2 Spider Queen report)**: root cause on main = `lp_enter` re-placed a
  BANKED boss through `lp_place`'s 8 random tries (the "farthest" boss rule only ran for a FRESH lair) and kept it
  in the record, unspawned and invisible, when none was legal: main's `levelgen.py` model (== the Z80, lp.py A7)
  misses the boss on 5-10 % of lair re-entries (D4 10.5 %, D2 9.2 %, D1 4.7 %). `lp_post` places it at its post on
  every entry: `tests/boss.py` R0 (10,500 model re-entries, 0 misses) and R1 (Z80, D1-D6: leave, 2 rooms away, back
  x 4, exact hp, BOSS_TRAP 0).
- **Ticks** (`tests/budget.py`, worst ordinary work tick, cap 126,000): `lglow` 102,445, `omix` 108,906, `pmix`
  109,487 (main 109,064: +423 = `ai_ghook` ~46 T a monster + the `.kat` / `.sa` golden tests ~30 T a drawn slot),
  every scenario gated green; `lqmix` 146,841 (report-only, main 148k). lp_enter (A7, 300 levels) mean 19,283 /
  worst 42,439 T (<= 22k / 46k). `tests/ai_equiv.py` vs main: 2,100 turns, 0 logic / RNG / status mismatches.
  `FL=abc tests/flicker.py`: 0 flicker / tear events.
- **T8 review (2026-10-29), rebased on main `54fe574`:** `boss_chk` requires a LIVE boss slot while the hero
  ENTERS the lair (a boss left in the record there = UB7: `tests/boss.py` T1 forces it, no free slot, BOSS_TRAP + 1);
  `lp_post` also shifts the post at c when a body placed earlier in the record covers it (`lp_spawn` marks bodies
  `LPC_BODY` 2, never exempt; lp_legal ORs every bit: unchanged elsewhere; boss.py P1). KNOWN (not fixed): an item
  dropped on the shut grate (TF_FLOOR) floats above the open shaft after the grate opens. Memory relief: `atk_mod`
  bank 3 -> bank 2 (boss2.asm), `og_adv` / `glow_kat` + `glow_tab` -> `boss2a.asm` before `kind_tab` (the pad; AMMO-COUNT moved it after `kind_tab`),
  `uq_fit` + `uq_chk` bank 3 -> R6 `fi6.asm` (far6 from mon_drop), `place_follower` bank 7 -> bank 3 (plain call
  from follow_admit), `follow_select`'s boss rule without the LVL_LAIR test (only the boss matches kind | E_GOLD =
  LP_BOSS). BOSS_HERE (review item 3) not done: ~17 T a monster in ai_ghook only (the render hooks already test
  E_GOLD, 6 T dearer than a global byte), and a stale / missing entry state would silently skip the guard.

| Region (`-DDEBUG_KIT=0`; main `54fe574` -> rebased T8) | main | T8 rebased | Δ |
|---|---|---|---|
| bank 3 free | 48 | **60** | +12 |
| bank 7 free (release / kit) | 36 / 31 | **136 / 131** | +100 (place_follower 116 B out) |
| bank 2 free to FRT / pad | 208 / 84 | **40 / 21** | −168 / −63 |
| R6 free (release) | 179 | **313** (kit 224) | +768 R6_GROW 10 -> 13, −634 T8 code |
| pool slack (worst D4) | 1,672 | **890** | −768 R6, −14 text |

## CORPSE-ASHES (2026-10-29, branch `feat/corpse-ashes`; plan.md "CORPSE-ASHES" / "MEM-RECLAIM decisions")

- **One shared monster corpse:** every monster DEAD frame is `small_corpse` (ART2 C2, 32×16 STA|SYM, unit
  `U_DEADR`, fid `KFID_RATDEAD`) EXCEPT the Bat, Slime and Ghost (own `bat_dead` / `slime_dead` /
  `ghost_dead`); hero corpses (`knight_dead` / `wizard_dead`) and every HURT frame unchanged. Retired:
  `skeleton_collapsed` (the Skeleton's `U_SKREST` = raise, hurt), `goblin_dead` (role `GB_DEAD` gone),
  `dead_humanoid` (unit `U_DEADH`, group `G_DEADH` / `BH_G_DEADH`, the SRC6 block). The corpse is
  bottom-anchored (FRM) and spans px .. px + 31 in both facings (body 32, the Rat's; as wide on the right as
  `dead_humanoid` was).
- **Units** (`pool6.asm` `gu_tab_x`): `U_DEADH` removed, `U_NBOLT` .. `U_SKCLIMB` renumbered `K_MAX + 3 .. + 9`
  (symbolic everywhere). `pool_gmap` 19 → 20 records: Skeleton `U_SKCLIMB` + `U_DEADR`; new Goblin record
  (`K_GOBLIN` + `U_DEADR`); every `U_DEADH` → `U_DEADR` (dedup per unit: one corpse a level).
- **FIDs:** `FID_COUNT` 132 → **129** of `FRT_MAX` 132 (3 spare; the descriptor growth reserve keeps 15 B for them).
- **Pool need per level** (Warrior / Mage, release; `tests/zx0_pool.py` `LEVEL_NEED`):

| depth | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| saved (both heroes) | 320 | 320 | 384 | 320 | 512 | 192 | 192 | 384 |
| Warrior need | 26,880 | 26,336 | 31,264 | **31,840** | 28,704 | 28,576 | 31,072 | 30,880 |
| Mage need | 22,944 | 22,400 | 27,264 | 27,968 | 24,832 | 24,576 | 27,072 | 26,880 |

| Region (`-DDEBUG_KIT=0` unless noted; main `3f8f134`) | main | CORPSE-ASHES | Δ |
|---|---|---|---|
| pool slack (worst D4 Warrior) | 890 | **1,210** | +320 |
| PROTO slack | 1,242 | **1,754** | +512 |
| bank 1 free (sprite sources) | 30 | **160** | +130 (packed 12,198 → 11,992 incl. SRC6) |
| SRC6 free | 97 | **173** | +76 (`dead_humanoid` block) |
| R6 free (release / kit) | 313 / 224 | **319 / 231** | +6 / +7 (`gu_tab` −2 B + `pool_gmap` +3 B; packed streams −7 B) |
| bank 2 free (kind_tab pad) | 61 | **73** | +12 (`frame_tab` 3 × 4) |
| low RAM spare | 17 | 17 | `fdesc_tab` −15 B into the growth reserve |


## JUMP-ALT (2026-10-29, branch `feat/corpse-ashes`, from `exp/jump-alt` eaeff4a; plan.md "JUMP-ALT KEPT")

**SUPERSEDED by ANIM-IMPORT2 (J-a, user 2026-10-30):** JUMP2 is MOT again and drawn every airborne tick;
the parity pick in `anim_entity .jump` is removed (−3 B / −12 T an airborne tick). See "ANIM-IMPORT2" below.

- `knight_jump2` / `wizard_jump2` MOT → **WK4** (one pool shift, px & 4 = 4); `anim_entity .jump` picks the
  airborne pose from the NEW px parity (E = (px & 4) >> 2: JUMP2 shifted, JUMP1 aligned), so the two alternate
  every tick and each is drawn only at its pool shift (`PHASE_TRAP` stays 0; `tests/phase_soak.py` adds running
  jumps). Shared hero logic: the Mage alternates too. +3 B / +12 T an airborne tick (bank 2).
- Pool need −576 every level, both heroes (`LEVEL_NEED`): Warrior D1..D8 26,304 / 25,760 / 30,688 / **31,264** /
  28,128 / 28,000 / 30,496 / 30,304; Mage 22,368 / 21,824 / 26,688 / 27,392 / 24,256 / 24,000 / 26,496 / 26,304.
  Worst-level (D4 Warrior) slack 1,210 → **1,786**; PROTO slack 1,754 → 2,330; bank 2 free 73 → 70. Note (pre-existing, not from this change:
  `-DPHASE_SHIFT=0` = both shifts everywhere, where WK4 = MOT) overflows the pool (POOL_NEED / PROTO ASSERTs).


## MEM-FT (2026-10-29, branch `feat/mem-ft`): `frame_tab` into the FRT rows, `FRT_MAX` 132 → 144

- **`frame_tab` (4 B/fid: `FT_COLS`, `FT_H`, `FT_OFFR`, `FT_OFFL`) left the bank-2 image** and lives in
  each fid's FRT row tail (bytes `FT_IN_ROW` 12..15, the 4 pad bytes): `frame_tab` EQU `FRT` + 12,
  `FT_STRIDE` = `FRT_STRIDE` 16. `data.asm` assembles `frames.asm` (FRM_HOT) ORGed at `FRT` — the row
  image 12 × `FRT_NONE` + entry per fid, runtime RAM, in the `.sna` only, not on tape — so `FID_*` and
  `main.asm` LEVEL POOL NEED (`{b frame_tab + fid × FT_STRIDE}`) are unchanged. `main.asm` `ovl_raw_ft`
  reads the entries back contiguous (516 B) → `build/ovl/ft.bin` → **`ftz_zx0`** (124 B, the LAST bytes of
  the bank-2 image, after `frt2.asm`: on the CODE tape block, always mapped; its pass-1/2 size moves only
  `code_end`; not R6 — the scarcest region — nor low RAM). **`boot6_ft`** (boot block, falls out of `boot6_tiles`, before `gen_idles`): dzx0 to `FRT`,
  then spreads top-down into the row tails and sets bytes 0..11 := `FRT_NONE` (== the build image for fids
  < `FID_COUNT`; rows above untouched). Writers keep the tail: `frt_none` (R6, now 12 B / row, ~390 T a row),
  `gen_frame` (variants only); `sel_frt_copy` copies whole rows (tail unchanged).
- **Readers:** `blit_sprite` takes the entry from the same row (`L & $F0 | 12`: 22 T, was 67 T: −45 T per
  drawn sprite); `render` (`anim.asm`) / `fx_set` / `ft_ptr` use `FT_HL_A` (defs.asm: nibble swap, 60 T,
  was 54 T: +6 T a slot).
- **`seq_rows`** (119 B) `FRT_GAP` → `FRT` − 119 = `$A689..$A6FF` (FRT_GAP is 0 at 144).
- **Low RAM → bank 2:** `sel_frt_copy`, `frt_ptr`, `frt_ptr_cur` (56 B) moved to new `frt2.asm` (after
  `kind_tab`), with `ft_ptr` from `gfx.asm`, to pay the descriptor reserve (`FDESC_GROW` = (144 − 129) × 5 = 75 B).
- **Headroom:** 15 spare fids (Orc/Vampire need 6). A 145th fid needs `FRT` one page down (`$A600`, −256 B
  bank 2) and 5 B more low RAM per fid (13 spare now = 2 fids; more by moving low-RAM code to bank 2).

| Region (release `-DDEBUG_KIT=0`; kit where noted) | main `c6e2a21` | MEM-FT | Δ |
|---|---|---|---|
| `FRT_MAX` / used / spare | 132 / 129 / 3 | **144** / 129 / **15** | +12 ids |
| bank 2 free (to FRT or seq_rows + pad) | 40 + 30 = 70 (+73 unused in `FRT_GAP`) | 236 + 35 = **271** (`FRT_GAP` 0) | +201 (+128 counting the old gap; `ftz_zx0` 124 B) |
| low RAM spare after the descriptor reserve | 17 (reserve 15) | **13** (reserve 75) | −4 (code −56) |
| R6 free release / kit | 319 / 231 | **323 / 231** | +4 / 0 (`frt_none` −4 release) |
| boot block (dead after boot) | 1,949 B | 1,983 B | +34 (`boot6_ft`) |
| pool need / slack | 31,264 / 1,786 | unchanged | 0 |



## ANIM-IMPORT (2026-10-30, branch `feat/anim-import`; plan.md "ANIMATION ITEMS 1–4 GO" / "ART9 APPROVED")

- **Item 1, Spider HURT = its BITE pose** (0 B): `ksm_sp` HURT + the DEATHSEQ's hurt entry = `spider_bite`;
  KS_CLIMBREST → `sp_idle + 1` (= `spider_walk1`, never used: not a climber).
- **Item 2, Archer / Sniper HURT = `skeleton_hurt`**: the frame moved into the Skeleton's prefix
  unit `U_SKARCH` (walk1..4, cut, **hurt**; `U_SKCLIMB` climb1/2; `U_SKREST` = raise only, ASSERTed),
  so no new unit / R6 byte: +576 B pool on D4 (no Skeleton there), 0 on D5 (the Skeleton's own).
  `ksm_ar` HURT / DEATHSEQ = `SK_HURT`. Skeleton FIDs renumber (symbolic everywhere).
- **Item 3, Necromancer B4 walk**: `necro_walk4` (ART3 B4 passing, `assets/gfx/concept/art3_options`,
  WK0, fid in the `K_NECRO` unit) and `MOVECYC4 walk2, walk4, walk3, walk1` (Necro, Archmage, Bone
  Caller; the Vampire shares it until its own set): +576 B on every Necro-unit level (D3 / D6 / D7 / D8).
- `FID_COUNT` 129 → **130** of `FRT_MAX` 144 (14 spare); low RAM spare 13 (descriptor reserve 70);
  SRC6 free 173 → **160** (Necro block +13); bank 1 free 160 → **150** (Skeleton block repack);
  R6 free 323 → **327** (sqm_zx0 −4); bank 2 / bank 3 / bank 7 unchanged.

| Pool need (release) | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| Warrior before → after | 26,304 | 25,760 | 30,688 → 31,264 | 31,264 → **31,840** | 28,128 | 28,000 → 28,576 | 30,496 → 31,072 | 30,304 → 30,880 |
| Mage before → after | 22,368 | 21,824 | 26,688 → 27,264 | 27,392 → 27,968 | 24,256 | 24,000 → 24,576 | 26,496 → 27,072 | 26,304 → 26,880 |

`POOL_CAP` 33,050: worst level D4 Warrior slack 1,786 → **1,210**; PROTO slack 2,330 (unchanged).

## STAFF-BONUS (fix/staff-spell-bonus): Rune / Bone staff spell damage

No new state and no new address: `proj_prep` (bank 3, `proj3.asm`) reads the worn weapon's TYPE
(`WORN + WS_WEAPON * IR_STRIDE + IR_TYPE`, low RAM) for `pf_abl` Spark..Lightning and adds
`type - IT_W_RUNE + 1` (Rune +1, Bone +2) to `pf_bonus` (the cast's copy of RK_BONUS), so it
reaches deal_hit as part of the pre-resist damage. Direct hit only (not the Firebolt burst).
`hero_recalc` untouched. Bank 3 free to `AY_RESERVE` 60 -> **37** (-23 B; release, rebased on main
2026-10-30); bank 2 271 / R6 327 unchanged. Test: `tests/staff.py`.

## LOG-FIX (fix/log-lines): the Mage's cast / hit lines, flanking melee lines

The LOG-AUDIT found the spell lines were never written (strings existed, unreferenced) and that two
monsters hitting on one tick lost a line (`MSG_Q` is one slot). Fixed; tests `tests/log_audit.py`
(L1..L10, L12, L14, S, C; reads the ring by its write index, one sample a tick).

- **`src/strings.txt` (0 B):** reordered so the hit lines are `TX_SPL_SPARK + ABL_*` over 0..8 and the cast lines
  `TX_SPL_C_SPARK + ABL_*` (fillers for Power / Whirlwind); ASSERTed in `abil_ammo7.asm`, with
  `TXL_* + NM_LONG < 32` for every hit line. Text block unchanged (2,652 B). Only the spell half of the cast
  table is used (dagger / bow keep their single result line).
- **`spell_fire` ends in `ammo_fire.t`**: one result line per cast, as a token stream (`hit_line`, ~1.4k T, no
  tx_dec decode; the fire tick +2.2k T vs main, was +7.9k with msg_cat / msg_kind). `THE BOLT HITS YOU` when
  the caster was struck AND hurt (`pf_tgt` = 0, `pf_lost` != 0; `pf_tgt` is the FIRST body only: a bolt that
  hits a monster and then bounces onto the caster prints no self line - deferred).
- **Fix A, `log_room`** (bank 2): a RESULT line (hit / kill / parry / self-hit / burst-self) with the ring full
  replaces the newest pending line (counted in LQ_DROP) instead of being dropped. A Lightning through 3-4
  ASLEEP bodies (cast line + 3 WAKES UP lines) keeps its hit line (test S).
- **`act_begin`** pushes `YOU CAST <SPELL>` before `proj_pre`; dropped when `LOG_QN >= 3` (`CAST_LINE_MAX`).
- **`pf_burst`** (bank 3): `THE BURST SCORCHES YOU` when the burst hurt the caster (deal_hit's L != 0).
- **`do_impact`** (`anim.asm`): a second impact in a tick shows the queued one first (~1.4k T) only with the log
  ring empty (`LOG_QN` = 0), else last-wins as before. A looser test (`LOG_QN` < 3 / < 2) overflowed the
  `tfaint` stress scenario (hero asleep, 4 monsters, no panel drain for 15 ticks); even `LOG_QN` = 0 leaves one
  dropped monster line there (main 0; see the report).
- **`src/msg2.asm`** (bank 2, after `ranged2.asm`): `msg_kind` / `msg_cat` / `msg_dec` / `msg_end` moved from
  bank 7 (callers there unchanged) + `log_room` + `hit_line`.
- Deferred: kill / hit lines for pierced bodies (P3), POWER STRIKE / WHIRLWIND wording, bounce / reflect lines,
  the hunger-line retry, dead-text reclaim.

(Release, rebased on main + STAFF-BONUS, 2026-10-30.)

| Region | before | after | Δ |
|---|---|---|---|
| bank 7 free (kit / release) | 131 / 136 | **144 / 149** | +13 (the msg_* helpers out, hit_line in) |
| bank 3 free to `AY_RESERVE` | 37 | **19** | −18 (`pf_burst` self line + gates) |
| bank 2 free | 271 | **149** | −122 (`msg2.asm` 119 B, `do_impact` 23) |
| R6 / low RAM / bank 1 / text bank 0 | — | unchanged | 0 |

### fix/spider-climb (user 2026-10-29): the Spider (+ Black Widow) climbs

* `KF_CLIMBER` on K_SPIDER (9) / K_BLACK_WIDOW (22); `ksm_sp` KS_CLIMB = `sp_idle` (its rest pose
  `spider_walk1`, cell-aligned: no art, no fid, 0 B pool or sequence cache), KS_CLIMBREST = `sp_rest`
  = `sp_idle + 1` (the one fid byte anim `.crest` reads; ASSERTed == `FID_spider_walk1`, not WK4).
  **Superseded by SPIDER-CLIMB below (2026-10-30): its own climb pair.**
  J1 ASSERT (main.asm) excepts the 4-wide Spider rows. `lq6.asm` `.w` (+27 B R6): the ladder queue's
  near-end box width = the wider of the two bodies (4 with a Spider).
* Hold (from `scratch/lq-hold`): `lq_block`'s back-off leaves `E_AIDIR = LQ_HOLD` ($80) on the standing
  walker, `ai_monster .sk` holds that one seek turn (no re-approach), so a period-1 loser no longer
  phase-locks a period-2 winner (the Spider / Mummy opposite-side D5 jams; `tests/ladder_jam.py` gates
  them now, no XFAIL). +12 B bank 3 (`.sk` 11, `jr` -> `jp .patrol` 1), +4 B R6.
* `.at` climb start (bank 3): the shaft rect is the climber's `KT_BW` wide (was `FEAT_W`): the Spider
  covers col .. col + 3 all the way up, so a body in its far-end box at col + 3 must stop the start.
  Same width for every other climber (kind_tab ASSERT). +8 B bank 3.
* Bank-3 relief: `fi3.asm` (`fi_full`, 52 B, cold, far3 callers unchanged: it touches only low RAM and
  far6) moved to bank 2 after `msg2.asm`.

Release (rebased on main + STAFF-BONUS + LOG-FIX + AMMO-COUNT, 2026-10-30):

| Region | before | after | Δ |
|---|---|---|---|
| bank 3 free to `AY_RESERVE` | 13 | **45** | −20 (hold 12, `.at` 8) + 52 (`fi_full` out) |
| bank 2 free (after the image + kind_tab pad) | 98 + 34 = 132 | **46 + 34 = 80** | −52 (`fi_full` in) |
| R6 free (release / kit) | 261 / 191 | **230 / 160** | −31 (`lq6` `.w` 27, hold 4) |
| pool / sequence cache / bank 1 / bank 7 | — | unchanged | 0 |


## ANIM-IMPORT2 (2026-10-30, branch `feat/anim-40px`; plan.md "40 PX APPROVED" / "ART11 DECISIONS" / "ART12 PICKS")

The approved 40-px frames replace the 48-px ones for the heroes and the Skeleton / Orc / Mummy /
Necromancer / Vampire families. **Body boxes are unchanged (6 cells, `BH_K_*`)**: frames are drawn
bottom-anchored (FRM: `fpy = py + BH × 8 − H`), so a 40-row frame lands 8 px lower and the top body cell
row is blank; the drawn footprint (`R_ROW` / `R_ROWS`, attrs, damage rects) follows the frame (5 rows).
Ogre, Death Knight (48), Goblin (32), Ghost, Bat, Slime, Rat, Spider and the hero DEAD frames are unchanged.

- **Sources:** `assets/gfx/sprites40/<name>.asm` (+ `grid/<name>.grid`) for every name listed in
  `assets/gfx/sprites40/index40.asm`; `tools/zx0_pack.py` `sprite_asm()` resolves a frame there first
  (used by `zx0_sources.py`, `pool_spike.py`, `tests/combat.py`), else `assets/gfx/sprites/` (the 48-px
  originals stay in the tree; tag `archive/48px-sprites` = main `410c118`). ART11 asm as shipped by the
  artist; the ART12 picks and the Vampire set through `tools/import_anim40.py`.
- **(1) Heroes:** Warrior 19 + Mage 15 frames at 40 rows (Mage HURT = ART12 V3 stagger, 32 wide, ax 8);
  **J-a jump**: JUMP1 = the crouch at take-off / landing, JUMP2 = the one leap pose every airborne tick
  (MOT again, `data.asm` ASSERTs MOT; JUMP-ALT's parity pick removed: −3 B, −12 T an airborne tick).
  `POOL_FIXED` = `(knight_idle1_h + wizard_idle_h) × 12 + 3 × 576` = 2,688 (select idles 40 rows: −192).
  Hero pool B (+ class FX): Warrior 15,072 → 13,152, Mage 11,072 → 9,952.

- **(2) Skeleton family + climb pairs:** the 9 Skeleton frames (`U_SKARCH` walk1..4 / cut / hurt,
  `U_SKCLIMB` climb1/2, `U_SKREST` raise; the Archer / Sniper draw them in their inks) and the shared
  humanoid climb pair `climb_h1` / `climb_h2` (`U_CLIMBH`: Orc / Necro / Mummy families). No id / flag /
  sequence change. Pool both heroes D1..D8: 0, 0, −864, −864, −960, −96, −96, −960.
- **(3) Orc V4 Ironhide + Mummy V2 + Necromancer V2:** Orc 6 frames (ART11; **new ids `orc_walk3`
  (WK4) and `orc_hurt` (STA)** inside `K_ORC`, later fids renumber, symbolic everywhere): walk B3
  `MOVECYC4 walk2, walk1, walk3, walk1`, HURT = `orc_hurt` (also the DEATHSEQ's first pose). Mummy
  (`tools/import_anim40.py mummy`: walk1..4 + attack, same B4 flags, HURT = the rest pose) and Necromancer
  (`... necro`: walk1..4 + cast; Archmage / Bone Caller share it in their inks) art-only. New 40-px-only
  names are INCLUDEd in `sprites/index_3f.asm` (the packer's frame list) and resolved in `sprites40/`.
  Pool both heroes D1..D8: 0, 0, −448, +640, −576, +64, +64, −576. **SRC6 exactly full** (3,328 of 3,328).
- **(4) Vampire own set:** `vamp_walk1` (WK0) / `vamp_walk2` / `vamp_walk3` (WK4) / `vamp_bite` (STA,
  ART9 32×40, replaces the ART2 32×48 in place) / `vamp_hurt` (STA) = unit `K_VAMPIRE` (`KFID_VAMPIRE`,
  5 fids after `necro_cast`); walk B3 `MOVECYC4 walk2, walk1, walk3, walk1`, HURT / DEATHSEQ pose
  `vamp_hurt`; no longer draws the Necro walk. **`U_VBITE` retired** (`U_SKCLIMB` K_MAX + 9 → + 8),
  `pool_gmap` 2 Vampire records → 1. Pool both heroes D1..D8: 0, 0, −128, 0, 0, +2,112, 0, +2,112.
  `SRC6_PAGES` 13 → 15 (above). `tests/walk_feet.py` (new, static): every 40-px walk cycle keeps a foot
  planted (the next slot's sole pixels + 4 px meet the current sole; the 48-px set failed it: bob / slide).

| Region (release `-DDEBUG_KIT=0`; main `df086fc` → step) | main | (1) heroes | (2) Skeleton + climb | (3) Orc + Mummy + Necro | (4) Vampire |
|---|---|---|---|---|---|
| `POOL_CAP` | 33,050 | 33,050 | 33,050 | 33,050 | **32,538** (SRC6 15 pages) |
| pool need worst level / slack | D4 W 31,840 / 1,210 | D4 W 29,728 / **3,322** | D4/D7 W 28,864 / **4,186** | D4 W 29,504 / **3,546** | D4 W 29,504 / **3,034** |
| PROTO slack | 2,330 | 4,442 | 5,306 | 5,306 | 5,306 |
| bank 1 free (sprite sources) | 150 | 673 (packed 12,015 → 11,492) | 810 | 810 | 810 |
| bank 2 free | 271 | 267 (`ftz_zx0` 124 → 131; `.jump` −3) | 267 | 267 | 267 |
| R6 free (release / kit) | 327 / 235 | 328 | 326 (packed streams) | 332 | **327 / 230** |
| SRC6 free | 160 | 160 | 181 (climb pair block) | **0** | 39 (15 pages) |
| `FID_COUNT` / `FRT_MAX` | 130 / 144 | 130 / 144 | 130 / 144 | 132 / 144 | **136 / 144** |

Pool need per level after (4) (release; `tests/zx0_pool.py` `LEVEL_NEED`), `POOL_CAP` 32,538:

| depth | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |
|---|---|---|---|---|---|---|---|---|
| Warrior need / slack | 24,192 / 8,346 | 23,648 / 8,890 | 27,712 / 4,826 | **29,504 / 3,034** | 24,480 / 8,058 | 28,544 / 3,994 | 28,928 / 3,610 | 29,344 / 3,194 |
| Mage need / slack | 21,056 / 11,482 | 20,512 / 12,026 | 24,512 / 8,026 | **26,432 / 6,106** | 21,408 / 11,130 | 25,344 / 7,194 | 25,728 / 6,810 | 26,144 / 6,394 |

**Overlays with 40-px bodies (checked on screen, `tests/climb3f.py --png` + a scratch scene):** attrs (kind ink,
`$42` flash, golden glow, tints) follow the drawn footprint (5 rows): the blank top body row is never painted.
- **(5) Status marks above the visible head** (`mark.asm` `mk_slot`, bank 2): the mark row is the DRAWN
  frame's top row − 1 (this tick's `SLOTREC` `R_ROW`) when that frame starts below the body top (the 40-px
  sets); else the old rule (body top − 1, hidden at a storey top row via `KT_MOD9`): 48-px Ogre / DK,
  32-px Goblin, 16-px kinds unchanged. No table. +25 B (incl. one `jr` → `jp`), ~+45 T a marked slot per
  pass (≤ 1 op budget unchanged). `ranged2.asm` now INCLUDEs before `mark.asm` so `rk_tab` stays inside
  one page. Bank 2 free 267 → **243**; bank 3 (60), bank 7 (136), R6 (327) unchanged. `tests/marks.py`
  `want_cell` follows the same rule.
- **Rebased on main `6bce4bc`** (bow icon, staff bonus, log, ammo count, Spider climb; release, measured):

| Region (release) | main `6bce4bc` | + ANIM-IMPORT2 (1)..(5) | Δ |
|---|---|---|---|
| bank 2 free | 80 | **52** | −28 (image +31: `ftz_zx0` +7, `.jump` −3, `mark.asm` +25, +2 layout; kind_tab pad 34 → 37) |
| bank 1 free (sprite sources) | 256 | **916** | +660 (packed sources 8,847 → 8,187) |
| bank 3 free / bank 7 free | 45 / 149 | 45 / 149 | 0 |
| R6 free (release) | 230 | **229** | −1 (packed streams) |
| SRC6 | 13 pages, 160 free | **15 pages, 39 free** | `POOL_CAP` 33,050 → 32,538 |
| pool worst level / slack | D4 W 31,840 / 1,210 | D4 W 29,504 / **3,034** | +1,824 |
| `FID_COUNT` | 130 | **136** of 144 | +6 |

- **Revert path:** `index40.asm` is not a toggle (six 40-px-only frames); removing one of them stops the
  packer with a pointer to `docs/conventions.md` "Sprite sources"; the way back is the tag
  `archive/48px-sprites`. `tools/gen_3f_art.py` `write_index_3f` regenerates `sprites/index_3f.asm` with
  `necro_walk4` and the six names (`ANIM_FRAMES` / `ANIM40_FRAMES`).

### SPIDER-CLIMB (user 2026-10-30, `feat/spider-climb-frames`): the Spider's own climb pair

* `spider_climb1` / `spider_climb2` (ART15, `tools/gen_art15_spider_climb.py`; dorsal view, head up,
  32x16, STA|SYM, art in x 0..23 over the ladder's 3 cells, cols 24..31 transparent; ink $05, Black
  Widow $02 via KT_ATTR) are two more FRM rows of the **K_SPIDER unit** (`frames.asm`, after `spider_bite`;
  `KFCNT_SPIDER` 3 -> 5): the Spider / Black Widow levels only (D2 D4 D5; the Widow shares the Spider's
  `gu_tab` / `pool_gmap` records, no table change). `FID_COUNT` 138 -> **140** of 144 (4 spare).
* `ksm_sp` (seq_img.asm): `sp_idle` = a 1-frame idle on `spider_walk1` (4 B, as before), `sp_climb:
  CLIMBCYC FID_spider_climb1, FID_spider_climb2` as KS_CLIMB, KS_CLIMBREST = `sp_climb + 1` (anim `.crest`
  reads that one byte = climb1; ASSERTed STA/SYM, climb2 == climb1 + 1). `sp_rest` is gone. +6 B raw
  sequence master (+9 B packed in R6: release R6 free 229 -> **220**, page count untouched).
* Pool: **+256 B on D2 / D4 / D5, both heroes** (2 x 128 B); `POOL_CAP` unchanged 32,269. Slack per level
  after (Warrior / Mage; before): D2 8,365 / 11,501 (8,621 / 11,757), D4 **2,029 / 5,101** (2,285 / 5,357),
  D5 7,533 / 10,605 (7,789 / 10,861); D1 D3 D6 D7 D8 unchanged. `tests/zx0_pool.py` LEVEL_NEED +256 there.
* SRC6: K_SPIDER block +163 B packed: 15 blocks, 10,144 raw -> **4,039 of 4,096 B, 57 free** (was 220).
* The 4-wide ladder queue (`lq6.asm` `.w`) only reads `KT_BW`, never the frames; the 3-cell shaft box and
  the per-tick 4 px climb tween are unchanged. `tests/climb3f.py` C2 now wants {climb1, climb2} for the
  Spider (both seen), ladder_jam unchanged.

## MEM-RECLAIM w2d (`feat/mem-reclaim-w2d`): sparse string pointers + 1-byte dictionary offsets

Text block format change only ("Text (B3B-13)" above has the layout); every string decodes
identically (W17, textpack round trip). Release build, vs main 2162bc8:

| Region | before | after | delta |
|---|---|---|---|
| bank-0 text block (`TEXT_LEN`) | 2,547 | **2,282** | −265 (tx_tab 390 → 196, tx_dict 140 → 72, entries 247 → 255 + 1 pad, streams 1,770 → 1,758) |
| pool slack (worst level, `POOL_START` $C9F3 → $C8EA) | 2,029 | **2,294** | +265 |
| low RAM spare (`LOWRAM_SPARE`) | 94 | **94** | 0 (`tx_ptr` stays 17 B; `tx_ptr_hl` removed) |
| bank 2 free | 51 | 52 | +1 (`tk_get`: 1-byte dict index, −10 T per token) |

Net +266 B. Review: a word per 8 ids (−411 B) cost up to ~3k T per lookup and +14.1k T in the
Whirlwind r3 tick (3 impact lines = 9 lookups); a word per 2 ids bounds the skip to one stream.
W17(c') gates every impact_line combo (msg 1..15 x every named kind): compose ≤ `IMP_CAP`
4,500 T (tick work; main 3,500, w2d 3,774), compose + log item ≤ 25k (W15's 1st-frame item ceiling) + `IMP_CAP` (main 29,082, w2d 29,149).
budget.py vs main, all scenarios: Whirlwind r3 Skel+Rat+Bat −150, pmix family +176, boss kill-drop +228,
Lightning (lcast / lcastf / lcasts) ±0, lqmix ±0, worst +228.
`textpack.py` owns the layout (`layout` / `decode` / `expand`; `parse_emitted` returns the image
with `dict_off` / `tab_off`); the log-reading tests (tier6, pickup3e, abil_ammo, abil_melee) use
`textpack.expand`.

## 3F-T9 mid-room spawns (`feat/3f-t9-spawns`; game.md §9.6 Rabbit Rat / Bone Caller, §1.5 ALARM, §9.5 idle-wave placement, plan.md PHARAOH ABILITY; `tests/spawn.py`)

**Decide / make split (3F TICK-BUDGET PLAN: "input tick only DECIDES, 1-entry SPAWN_Q at end_turn").**
A producer fills the 1-entry **spawn queue** and nothing else; `end_turn` (bank 7, before the exit
test) far6s R6 `sp_run`, which makes the bodies on the turn's last tick. Never in a cast / input tick
(lcastf unchanged). A producer that finds the queue busy does nothing (S not reset: it retries).

| Symbol | Addr | |
|---|---|---|
| `SPQ_K` | `$5FF5` | queued kind byte: bits 0-4 the kind (0 = an ALARM wave: `LP_KINDS[rnd & 3]` per body), `SQF_ONCE` bit 5 (set the parent's `RCD_ONCE` when made), `SQF_SUMM` bit 6 (= `RCD_SUMMONED`), `SQF_RESP` bit 7 (= `EF_RESPAWN`); 0 = empty. Garbage at boot: `new_game` (boot7) zeroes it; `sp_run` always empties it |
| `SPQ_P` / `SPQ_N` | `$5FF6` / `$5FF7` | the parent slot (placement anchor; `SPQ_NONE` $FF = the doors) / bodies 1..2 |
| `SP_KB` `SP_Y` `SP_S` `SP_N` `SP_SIG` `SP_NS` `SP_AX` `SP_AR` | `$5FF8..$5FFF` | `sp_scan` / `sp_run` scratch (`SP_NS` = `SP_SIG` + 1: one word store) |

Producers: **`breed6`** (far6 from `deal_hit`'s survive path, bank 3, kind test inline: a Rabbit Rat hit
and alive, not `RCD_ONCE`, queue free, `rng_mod 4` = 0 -> one base Rat, `SQF_ONCE|SUMM|RESP`);
**`sp_bcall`** (`ai_ranged` `.pre`, `RWF_PRE` rows = the Bone Caller, reached in line / in range / clear /
no reflect: S > 0 -> S - 1 and on to the shot; S = 0 and < `BC_LIVE` 1 summon-made bodies in the room and a
free slot and the cap -> a base Skeleton if `K_SKELETON` in `LP_KINDS` else a Ghost, S := `BC_CD` 8, the
KS_ATTACK pose with `E_MSG` = **`MSG_M_SUMMON` 16** "THE <kind> SUMMONS!" at its IMPACT (new string
`cmb_summons`; the Bone Caller's name is "SUMMONER"), the turn used); **`ph_summon`** (far6 from bank-7
`ai_guard` for the lair boss when it is a Mummy = the Golden Pharaoh, before the leash logic: the same with
`PH_LIVE` 1 (one minion at a time, user 2026-10-30; Pharaoh 6 + minion 5 = 11 of 12 never fits a 2nd, so the old 2nd-body branch was dead and is gone) / `PH_CD` 8, then one RNG byte: bit 1 a Mummy instead of a Skeleton; L = 1 the
turn is used); the **ALARM** trap (`trap7.asm tr_eff`: a generated level (`LVL_DEPTH` != 0) with
`LF_UNIQUE` clear -> `SPQ_WAVE`, `SPQ_NONE`, 1 + (rnd & 1), `out (PORT_BORDER)` `BORDER_ALARM` 2 for
`TRAP_STEP_T` ticks (step 1 writes 0), "AN ALARM BELL RINGS!" (`S3_TRAP_ALARM`); else the 3E bell line).

`sp_run` per body: kind -> `sp_scan` (slots 1..15 of `CUR_ROOM`: `SP_N` live incl. PENDING, `SP_SIG`
Σ `lp_wt6` (+1 golden), `SP_NS` summon-made, the first free slot (E_FLAGS 0)) -> `sp_fit` (`SP_N` <
`ROOM_CAP` and Σ + w <= `LP_SIGMA_CAP`) -> the parent's storey / x / x + w (live, not PENDING / DYING,
in the room) -> `sp_init` (bytes 0..23 + the slot's `ST_*` zeroed: **the drawn record `E_DVIS..` stays**,
so a freed corpse still drawn in that slot is erased when render classifies the new body FULL) -> the spot:
**beside the parent** (`sp_place`: d = 0..`SP_R`-1 = 3, the side toward the hero first; `sp_try`: body
cols in `LP_XMIN..LP_XMAX`, `box_free` with `ACT_SLOT` = $FF (every live body, the hero included), a
flyer `box_solid`-clear in its cruise row 9s+1, a walker on floor cells `TF_FLOOR` without `TF_HOLE` /
`TF_LADDER` and standing-row cells without `TF_SOLID|TF_LADDER|TF_DOOR`), or **the door** (`sp_door`:
left door x = 1, else right x = 31 - w, on its storey, `EF_PENDING | EF_WALKIN`: it walks in as a
follower; no door: the up-exit col on storey 0, else the down-exit col on storey 1, `EF_PENDING`; every
wave body takes the same spot, materialise lets them in one by one) -> `sp_fin` (flags ACTIVE | HOSTILE |
`SQF_RESP` | the PENDING bits, facing the hero, `E_RCD` = `RCD_SUMMONED` or 0, hp = max = R6 `kind_hp`,
snap px / py, M_REST; `SQF_ONCE`: the parent's `RCD_ONCE`) -> **`build_live`** (LIVE_LIST for the next
body's `box_free`; PEND_N for the wave: the 3F-B4 rule). A body that fails (slot, cap, parent gone, no
spot) ends the run. No spawn when `EXIT_KIND` != 0 or the hero is dying (the queue is still emptied).

`E_RCD` (= `E_POT`): bits 0-1 the shot / SLAM counter (T7 / T8), bits 2-5 **S** (`RCD_SUMMON`), bit 6
**`RCD_SUMMONED`** (summon-made: Bone Caller / Pharaoh summons, Rabbit offspring; the ALARM wave is not),
bit 7 **`RCD_ONCE`**. Bank 3: `lp_bank` frees a summon-made body without banking it (§9.4.2) and writes
`RCD_ONCE` as **`LEK_BRED`** (bit 6 of the record's kind byte); `lp_spawn` restores it; `place_follower`
keeps bits 2-7 (`RCD_KEEP`; a summon that follows stays summon-made and is dropped when that room is left).

Costs (`tests/spawn.py` T, far6 incl., interrupts on): `sp_run` a summon 10.4k T, an offspring 10.5k, a
2-body wave 14.2k (gates 12k / 12k / 16k); producers: S > 0 ~80 T, a decision ~1.8k (`sp_scan`), `breed6`
~0.3k + far6 per Rabbit hit. `tests/budget.py` new **`bsum`** (nroom with the Bone Caller alone: the summon
turn + its end_turn spawn) 103,682 T worst work tick; every scenario green; new **`walarm`** (an ALARM
wave on a room already holding 2 monsters: 2 queued Goblins, `sp_run` ~14.2k at the first end_turn, then the
materialise ticks) worst work tick **122,529** T (125,170 incl. the ISR; cap 126,000); worst gated ordinary
otherwise 121,246 (main 121,018: +228 T; the Lightning / `lcastf` family +155..+407 T and the pickup scenarios ~+52 T come from
the `deal_hit` Rabbit hook, ~46 T per surviving hit; nothing is unchanged), `lqmix` (report only) 128,110.

| Region (`-DDEBUG_KIT=0`) | main `2390dec` | after 3F-T9 | Δ |
|---|---|---|---|
| R6 free | 1,468 | **655** | −813 (`spawn6.asm` 800; `ranged6.asm` +13: the `.pre` hook 10, `rg_pose` shared with `sp_summon` +3) |
| bank 3 free | 45 | **8** | −37 (`lp_bank` 14, `lp_spawn` 8, `place_follower` 4, `deal_hit` breed hook 11) |
| bank 7 free | 273 | **193** | −80 (end_turn 10, new_game 4, ALARM 44, border off 6, `ai_guard` Pharaoh 16) |
| low RAM spare | 94 | **92** | −2 (`imp_pre` / `imp_post` + 1 each) |
| bank 2 / bank 1 | 52 / 911 | unchanged | 0 |
| text (bank 0, packed) / pool slack | 2,282 / 2,294 | 2,288 / **2,288** | +6 / −6 (`cmb_summons`) |
| bank-5 runtime reserve | `$5FF5..$5FFF` free | `SPQ_RAM` | 11 B (`tests/items3e.py` canary range follows `SPQ_RAM_END`) |

**Not in this change (open):** the drain bite's `+n` floater (needs the D3-11 number system, not built).
The Vampire bat form: next section.

## 3F-T9 Vampire bat form (`feat/3f-t9-bat`; game.md §9.2 "Vampire", RANGED-SPEC cut rule; `tests/vbat.py`)

**A kind row, not a flag.** `K_VBAT` = **2** (the retired Rogue's hole; `defs.asm`): every per-kind table
gets a real row, so ai_flyer / try_step / render / the hit path need nothing new. Rows: `kind_tab` the
Bat's body (3x2) / `KF_FLYER|KF_BAT` / atk 1 eva 4 / 1d2 / period 1, the Vampire's `KT_HP` 14 (a banked
bat's max hp in `lp_spawn`) and ink $05; `kx_tab` the Vampire's resistances / `IMM_UNDEAD` / KXP 9, a
plain PHYS bite (no drain, no heal); `lp_wt` / `lp_wt6` `WT_K_VAMPIRE`; name `nm_vbat` "VAMPIRE"; `gu_tab`
= (`KFID_BAT`, `VB_FCNT` 2: flapup / glide, MOT); `ksm_tab` = `ksm_vb` (seq_img.asm: 2-frame flap, no
corpse: it fades out). A transform rewrites `E_KIND` (+ `E_Y` on a revert); hp, statuses, `E_GOLD`,
`E_RCD` stay. Never in `LP_KINDS` / spawned: only by transforming (a banked bat returns as one).

| Symbol | Where | |
|---|---|---|
| `E_RCD` bit 7 `RCD_ONCE` | entity | the Vampire has fled once (banked as `LEK_BRED`) |
| `E_RCD` bit 2 `RCD_VFLEE` | entity | this bat form is the flee one (reverts when its FEAR ends); clear = close-distance bat. `place_follower` keeps it, `lp_bank` drops it |
| `VB_S` = `SP_S` | `$5FFA` | storey scratch (end_turn after `sp_run`: SPQ_RAM is free) |
| `VB_FLEE_T` 8 / `VB_GAP` 10 / `VB_NEAR` 2 | combat_defs.asm | FEAR turns / close-distance gap / revert gap |
| `MSG_M_DRAIN` 17 | defs.asm | the Vampire's bite-hit line (impact_line remap) |

**Flow (end_turn only, never a cast / input tick).** Bank-7 `vb_turn` (bank7.asm, `call z` when no exit):
off a Vampire level (`LP_KINDS` + `LP_BOSS` without `K_VAMPIRE`) returns (~0.15k T); else picks each
body of CUR_ROOM that may change now — a Vampire at the end of an **odd** turn (its rest turn: "costs
its whole turn"), a bat at the end of an **even** one (the humanoid then rests the next turn) — active,
not PENDING / DYING / held (HOLD), sets `ACT_SLOT`, `cache_player`, `VB_S` and far6s R6 **`vb_one`**
(`vbat6.asm`): humanoid, hero on its storey: (1) flee: not `RCD_ONCE`, 3 hp <= max + 2 (5 of 14) ->
bat, `RCD_ONCE|RCD_VFLEE`, MIND := FEAR `VB_FLEE_T` (mon_status steps it away; cornered it bites);
(2) close: 1 <= gap <= 10 and `vb_cut` (a floor-row 9s+8 col with neither `TF_FLOOR` nor `TF_LADDER`,
or a `TF_SOLID` standing-row 9s+7 cell, via ranged6 `rg_scan`) -> bat. Bat: revert when (VFLEE: FEAR
over) / (else: hero on its storey, gap <= 2, no cut between) and the humanoid box at its x is legal
(spawn6 `sp_y` + `sp_try`, `box_free` skipping `ACT_SLOT`; else it stays a bat, y restored). Every
transform (`vb_bat` / `vb_fin`): `M_REST`, `snap_pxpy`, golden: **`LP_BOSS` := kind | `LEK_GOLD`** (the
Lord keeps its boss identity: guard hook, drop / grate, PROVOKED, never follows, `boss_chk`),
`build_live` (LIVE_LIST caches w / h). Turning into a bat logs "THE VAMPIRE TURNS INTO A BAT!"
(`vb_turns`, bank-0 text); the revert is silent.

**Pool / sequences.** `pool_gmap` + (`K_VAMPIRE`, `K_VBAT`, -): D6 / D8 pool the Bat's first 2 frames
(+896 B each, D8 the worst level now). On D3 (the Bat is resident) `pl_unit` **merges units with the same
fid0** (keeps the longer count; the build's `PL_KIND` sum drops `K_VBAT` when `K_BAT` is listed; the
`zx0_pool.py` model merges the same way). `pl_kinds` loads `K_VBAT`'s block with the Vampire's (D3 / D6 /
D8: 5 cache blocks, main.asm SEQ CACHE NEED counts it).

**Not built (open):** rule 2's **other-storey** case: a flyer cannot leave its storey band (ai_flyer /
clamp_band, bank 3 has 8 B free), so a Vampire whose hero is on the other storey keeps walking
(non-climber: patrols). Flee is the FEAR step (x only, away), not an erratic flight. Drain `+n`: not
built (needs D3-11); instead **`MSG_M_DRAIN` 17**: low-RAM `impact_line` (after `sfx_msg`, so the HURT
sound stays) remaps `MSG_M_HIT` of `K_VAMPIRE` to "THE VAMPIRE DRAINS YOU" (`cmb_drains`; `imp_pre` /
`imp_post` + 1 each; the bat form `K_VBAT` keeps HITS YOU).

Costs (`tests/vbat.py` T, far7 incl., interrupts on, D6): `vb_turn` no candidate 2.1k T, a Vampire that
stays 5.9k, a flee transform 7.8k (gates 2.5k / 6k / 12k).

| Region (`-DDEBUG_KIT=0`) | after 3F-T9 spawns | after bat form | Δ |
|---|---|---|---|
| R6 free | 655 | **357** | −298 (`vbat6.asm` ~225, `pl_unit` merge 8, `pl_kinds` 10, `pool_gmap` 3, `sqm_zx0` +23 packed) |
| bank 7 free | 193 | **85** | −108 (`vb_turn` + the end_turn hook) |
| low RAM spare | 92 | **78** | −14 (`impact_line` drain remap 12, `imp_pre` / `imp_post` 2) |
| bank 3 / bank 2 | 8 / 52 | unchanged | 0 (rows edited in place: `kind_tab`, `kx_tab`, `lp_wt`) |
| text (bank 0) | 2,288 | 2,311 | +23 (`nm_vbat`, `vb_turns`, `cmb_drains`; retokenised) |
| pool slack (worst level) | 2,288 (D4) | **1,785 (D8)** | −503 (D8 +896 bat frames, text +23) |
