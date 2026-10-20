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
| `$5CCB-$7FFF`| Free RAM (after BASIC reclaim)              | program + working storage; **D3-6b: `$5E00-$5EFF` = `PF_RAM`** (proj_fire scratch, runtime only — "3D contracts"); **D3-8d: `$5F00-$5F8B` = `MK_RAM`** (status-mark cell map + glyph / attr copy, runtime only — "Status marks (D3-8d)"); **3E-T3: `$5D00-$5D50` = `ITEM_RAM`** (bag, worn, hunger, quick slots; 81 B since the 3E simplification; runtime only — "3E contracts") |
| `$8000-$BFFF`| Program origin region                       | `ORG $8000` for now           |
| `$C000-$FFFF`| Paged bank window                           | bank selected by $7FFD bits0-2|

## 128K banks ($C000 window)

| Bank | Planned use                       | Status   |
|------|-----------------------------------|----------|
| 0    | **D3-TX: the text block** (`TEXT_ADDR` `$C000..POOL_START`, own tape block), then the pre-shift sprite pool | PROTO    |
| 1    | PROTO: sprite sources (virtual $8000-$BFFF), ZX0-packed since A5: 6,947 of 16,384 B (A6); + `vdata` (D3-TX: the text block moved to bank 0; **3E-T1: its boot-only part moved to the bank-6 boot block**); **C3-0: `ui1_code` (3C UI code, via `far1`)** after it; **3E-T1: then the packed overlay streams `ovl_blobs`** | PROTO |
| 2    | (also $8000 fixed)                | system   |
| 3    | PROTO: sprite sources tail (virtual $C000-; empty since A5) + **cold code** (select, transition scrolls, follower selection; new game → bank 7 since MEM-SND); **`$EFA0-$FFFF` AY player slot** (A8; **3E lever (c): 4,192 B** from `$EFA0` (+512 B to bank-3 cold code); MEM-SND: 4,704 B from `$EDA0`, was 4 KB at `$F000` since D3-0 (user 2026-10-06), 7 KB from `$E400` before; called by the IM 2 ISR) | PROTO |
| 4    | PROTO: pre-shift sprite pool      | PROTO    |
| 5    | normal screen (also $4000 fixed); low RAM `$6000-$7FFF` buffers + **cold code** (boot, generator) + frame descriptors (A6) | system   |
| 6    | PROTO: pre-shift sprite pool; **3E-T1: until the hero start, its top `BOOT6_ADDR..$FFFF` = the boot block** (boot-only code + data, own tape block, dead after boot — "Boot block") | PROTO    |
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
| 1 | sprite **sources** at *virtual* `$8000..` (MMU slot 2 = page 1): `build/zx0/sprites_zx0.asm` (see "Sprite sources (ZX0)" below; B3B-12 retired the raw `index.asm` A/B build) | ZX0: `SRC_TOTAL` **6,947 B** (`$C000..$DB22` in bank 1), then (B3B-11b, bank-3 relief) the **`vdata` block** 2,704 B (B3B-13 measured) (`vdata..vdata_end`: `font6x8` 768, `panel_icons` 774, the `HOT_COPY` load image `panel_hot_img` 515, `tiles_common` 288 + `orn_glyphs` 64 (D3-0: the 16 B of PROTO zap glyphs `tiles_fx.asm` are no longer assembled; `VDATA_LEN` 3,563 B) — boot / new-game cold data, read only through `copy_virt` / `copy_virt3`; B3B-13: + the **text block** `text_img` 277 B, DISPed to its runtime `$C000..` address — **D3-TX: moved to bank 0**, see the bank-0 row and "Text (B3B-13)" below); **C3-0: then `ui1_img..ui1_img_end` = `ui1_code..ui1_end`** (bank-1 UI code, `src/ui1.asm`, DISPed by `TEXT_DISP` to its runtime `$C000..` address, ASSERTed in bank 1 and `ui1_end <= UI1_LIMIT` `$10000`; empty in C3-0 at `$E4AC`; the build DISPLAYs `bank 1 free`); **3E-T1: `vdata` 837 B (`panel_icons` 774 + `status_icons` 63; −1,623 boot-only B → the boot block), UI code `$E611..$F80D`, then `ovl_blobs` 30 B, bank-1 block 14,379 B, 2,005 B free** (was 412); **3E-T2: UI code `$E611..$F851`, `ovl_blobs` 273 B (the page), 1,694 B free**; bank-1 block `SRC_LEN_LO` 9,388 B (C3-0 measured), **6,996 B free** (B3B-13: −265 raw items / tiles, +277 text; **C3-7 measured: bank 1 free 861 B** after the UI code (**SND-4a: 412 B free**, −62 `stinger_wait` (Kempston via read_stick, 512-frame cap) in `menu1.asm`; SND-1: 474 B free, −169 (−124 + 45 for the log line's replace-pending rule): `snd_cycle` / `snd_id` / `menu_snd`, the 3-item pause box, `S` reserved, key 5; bank 0 text −4 B net: 3 SOUND strings, `ft_press` dropped; bank 7 and low RAM unchanged) — the 6 hero frames took 904 B of packed sources, was 1,765; **D3-TX: 2,168 B free**, was 992 at D3-0: the text block (1,166 B at D3-0) out to bank 0; `VDATA_LEN` 2,397 B; **D3-4: 783 B free** — +1,322 B packed sources (27 frames) + the 63-B `status_icons` in `vdata` (`VDATA_LEN` 2,460 B); **D3-9b: 650 B free** — −16 `xp_next` (now bank-2 `xpn_tab`), +35 `item_info`'s rank-2/3 line pick (D3-9a); **D3-8: 689 B free** — +94 B `stat1.asm` (`st_icons_draw`) in the UI code) (A6: the 272 B of banked descriptors moved to bank 5) | tape block 3 / .sna |
| 3 | sprite sources tail, virtual `$C000..` (MMU slot 3 = page 3) — **empty** with ZX0, then the **bank-3 cold code** (`bank3_code..bank3_end`, below) | 0 B sources + code + cold data = `BANK3_LEN` (**3E lever (c): `AY_RESERVE` `$EDA0` -> `$EFA0` (+512 B): 11,576 B code, 616 B free to `AY_RESERVE`**; DEC1: 11,577 B, 103 B free to `AY_RESERVE` `$EDA0` (was MEM-SND 11,475 / 205) (both `DEBUG_KIT` builds; −406 B → bank 7 `src/boot7.asm`: `init_tiles` (36) and `panel_boot` (73, boot), `new_game` minus its PROTO tail (now bank-3 `new_game_proto`: `proto_level` + `spawn_tab` + `vis_reset`, kept for the tests' `proto_start` = 1 path), `panel_init`'s bank-2-only half `panel_init7` (state reset, the 9 attr stamps, the potion-slot scan; `pot_slot` stays bank-3 data, written from L); then `AY_RESERVE` −608 B (`$F000` → `$EDA0`), ~200 B kept as bank-3 growth slack for 3E/3F; `level_start_x` and the PROTO cluster stay (A-returning / bank-3 data / test probe `level_new`, tests use `proto_start`); D3-9b: 11,881 B, 407 B free (−48: `xpn_tab` → bank 2, `lvlup_tab` / `lvl_step_tab` → `xp_turn` immediates, `panel_init`'s MP placeholder bar gone); D3-8d: 11,929 B, 359 B free (both `DEBUG_KIT` builds; +21: `dh_status`'s V3 sleep flash — an ASLEEP landing with no reaction pending sets `E_FLT` / `E_FLA`); D3-8f: 11,908 B, 380 B free (both `DEBUG_KIT` builds; −4: `deal_hit`'s WEAK −1 moved onto the DEF path (B → `dh_def`, the old dec / min-1 gone), `dh_status` reads the `efx_tab` row before the halving (R2 order; no push / pop)); L-RELIEF: 11,912 B, 376 B free (both `DEBUG_KIT` builds; −353: `follow_select` (the candidate scan, 186 B), `place_follower` (112) and `arrival_conflicts` (56) → bank 7, +1: `follow_admit` far7s `place_follower` (+3, its `jr .pick` → `jp`) ; `dg_bad` moved to `$C0C0` right after `kx_tab` (`src/dg_bad3.asm`), the 3-B `ALIGN 64` pad gone — **no alignment pad left in bank 3**: code size changes no longer cost 64 B steps); D3-8e2: 12,265 B, 23 B free (both `DEBUG_KIT` builds; +3 `level_reset` clears `pf_prep`, `pf_strike`'s `pf_ftick` record 0 B — absorbed by the `dg_bad` ALIGN 64 pad, which now has **3 B** of slack: 4 more bytes of bank-3 code before `decor_gen.asm` cost 64); D3-8e merged with D3-8c: 12,265 B, 23 B free (both `DEBUG_KIT` builds; D3-8c +54: `deal_hit` HOLD_GUARD / held-body refusal, self-freeze, POISON add (bank 7 −4 B); D3-8e alone: 12,211 B, 77 B free, +158: `proj3.asm` — the split cast (`proj_part` / `proj_go` / `proj_run` entries, the strike budget + park, `pf_prep` 1 B), the bulk run entry, the inline `pf_bdone`, `pf_strike` through `dh_tix`, the caster DONE in `pf_cands`, the die mask; `rank3.asm` `proj_rel`'s prep test + `proj_pre`; `deal_hit` `dh_tix` / `dh_rtick` 3 B; `set_reaction_at`'s `dh_rtick` test); D3-8 review 2: 12,053 B, 235 B free (both `DEBUG_KIT` builds; +123: `proj3.asm` — `pf_cands`' x1 clamp, `pf_bodies` rewritten (count early exit, `PFCF_DEAD`), the bulk fast-forward entry, `rsp_hl` without the loop; `deal_hit`'s page-local record reads + `dh_bit` 8 B; `set_reaction_at` × 17 by shifts); D3-8 review: 11,930 B, 358 B free (both `DEBUG_KIT` builds; −57: `proj3.asm`'s `PF_ROWF` body count — `pf_bdone`, the count in `pf_cands` / `pf_reverse` — and `panel_init`'s `STAT_SH` reset); **D3-8: 11,873 B, 415 B free** (both `DEBUG_KIT` builds; −103: the monster status test + far7 `mon_status`, `item_icons`' status sig, `deal_hit` boss + WEAK, `hit_roll` WEAK); **D3-7 T7: 11,770 B, 518 B free** (both `DEBUG_KIT` builds) — +44: `pf_miss` + `pf_dodge` in `pf_strike` (`proj3.asm`), +4 (review): `set_reaction_at` lets a BLOCK replace a pending `RC_DODGE`; **D3-7 T6: 11,722 B, 566 B free** (both `DEBUG_KIT` builds) — −~190 `dg_drips` + its scratch (the drips are gone), +~10 `build_room_map` stamps the ammo stacks, `dg_bad` regenerated (ids 17/18 no longer decor); **D3-7 T5: 11,978 B, 310 B free** (both `DEBUG_KIT` builds; T4 left 216 B / 171 B with the kit) — +92 `melee_hit` (`rank3.asm`), −~150 `potion_pickup` (→ bank-7 `pickup7.asm`), −~34 `try_quaff` (→ bank-7 `intent7.asm` `ic_quaff`), −~36 `debug_kit` in kit builds (→ `intent7.asm`); **D3-7 T1: 11,982 B, 306 B free** — +8: `set_reaction_at` / `pf_tick` add `TURN_TICK`; note the `dg_bad` ALIGN 64 has only ~2 B of slack: 3 more bytes in bank-3 code before `decor_gen.asm` cost 64; **D3-7 T0: 11,974 B, 314 B free** — −284: `intent3.asm` → bank 7 (`intent7.asm`), `slot_act_tab` / `slot_act` / `abil_rank` + the `icons3.asm` page pad → bank 2, `rank3.asm` `abil_load` +~80; **D3-6b: 12,258 B, 30 B free** — +1,046: `proj3.asm` ~1,060 B, `deal_hit` −14 (shares `rsp_hl`); D3-6a: 11,212 B, 1,076 free; the figures that follow are older) **9,893 B, 2,395 B free** (merged with D3-1 / D3-TX; LP alone: 9,637 B, 2,651 B free) to `AY_RESERVE $F000` (**LP +1,216**: `src/lpop3.asm` 1,302 B (`lp_dtab` 48, `lp_wt` 9, `lp_budget`, `lp_append`, `lp_bank`, `lp_transition`, `lp_enter`, `lp_fit`, `lp_place`, `lp_cmap` / `lp_mark`, `lp_legal`, `lp_spawn`), `follow_admit` / `dest_counts` LP paths ~+70, the stand-in `pop_one` / `pop_kinds` / `pop_cols` −~150, an `icons3.asm` page pad for `slot_act_tab`; before LP: 8,421 B, 3,867 B free (**D3-0**: AY reserve 7 → 4 KB = +3,072 B; the PROTO zap out −87 B: `init_tiles`' zap-glyph copy, `do_attack`'s zap tail + `wz_zap`; `kx_tab` +192 B (R2, zeros until D3-1); the `ST_*` clear in `level_reset` + `level_reset_new` +64 B; before: 8,252 B, 964 B free to `$E400` (C3-7)). Earlier: 8,369 B, 847 B free to `$E400` (B12, measured: 8,305 → 8,369 = +64 incl. the `dg_bad` ALIGN 64 shift: `glow_ids` 8 + the `.gate` stamp in `build_room_map` ~42; the D1 decor rework before it was not itemised here). Before: 7,744 B, 1,472 B free (B11/B14 +44 (measured: 7,700 → 7,744, incl. `level_reset` clearing `CLIMB_BLK_N`; the row's older figures below were not re-measured): the B14 yield — on the shaft col the facing side instead of the roomier one, the flyer's vertical fallback that must end off the path; B3B-13 −196: `show_impact_msg` + `kind_name` / `str_cat` + the 7 combat words → low RAM / the text block, `str_descend`, the room-D chest decor entries out; + `sel_nm_knight` / `sel_nm_wizard` 14 (select-screen names, ROM charset) in; before: B3B-12 +469 incl. the review fixes: `level_card` + strings, `level_new` (seed + level_gen retry), `level_populate` / `pop_one` + `pop_kinds` / `pop_cols` (the stand-in population), `level_reset` / `spawn_one` factored out of `new_game`; before: 7,157 B, 2,059 free; B3B-R2 +1,558: `src/turn3.asm`, the monster phase / attacks / potions moved out of bank 2, see "Cold code placement"; before R2: 5,599 B, 3,617 free; B3B-10 −1: `build_room_map` picks + empties the decor list of its map page (`dg_dst`), the deriver's ROOM_MAP-only test gone; the B3B-9 deriver `decor_room` (`src/decor_gen.asm`, ~1.0 KB incl. its 56 object records) came with the B3B-9 merge; B3B-11b −2,534: font, icons, hot image, `tiles_common` / ornament / zap data out to bank-1 `vdata`, `panel_boot` builds the planar font, `pblit` / `init_tiles` read through `copy_virt3`; before: 8,134 B, 1,082 free after the B3B-9 merge; B3B-11 +2,687: `src/panel.asm` cold code 437 (`panel_boot`, `panel_init` / `panel_flush`, `pblit` / `glyph8` / `cell_bm`, bar tables), the 6×8 font 768 (`font6x8`, boot-copied to `FONT6`), the panel icons 774 (`panel_icons.asm`), the `HOT_COPY` image 708 (`panel_hot_img`, boot-copied); B3B-8 +1,149: `build_room_map` v2 524, `init_tiles` 39 + its cold data 370 (`tiles_common` 288, `orn_glyphs` 64, the zap glyphs 18), `proto_level` + its tables ~150, the scroll ornament hooks ~45, `decor_room` stub 1 (B3B-9: the real deriver); B3B-7 merge: `level_gen` / `level_start_x` ~1.7 KB; B3B-5 +22: `edge_init` + the `EDGE_TAB` / `JUMP_TURN` init in `new_game`; raw: 515 + 1,760 = 2,275, 6,941 free before B3B-5; A7 review: + `new_game`/`init_ent_common`/`spawn_tab` and the follower selection / arrival conflicts, 794 B, out of bank 2). ASSERT `bank3_end <= AY_RESERVE` | tape block 4 / .sna |
| 3 | **AY player slot** `AY_RESERVE..$FFFF` (A8; **3E lever (c): 4,192 B at `$EFA0` (was 4,704 B at `$EDA0`), 4,025 B used, 167 B free** (3 reserved 3F ids + EAT/pickup tweaks need ~160); `ay_vars` now `$F5DD..$F645`; all else symbolic; **MEM-SND: 4,704 B at `$EDA0`, 3,987 B used, 717 B free; SND-5b: 4,055 B used, 649 B free (+5 effects +10 B table, 32 effects); 3E-T0: 4,025 B used, 679 B free (5 status variants -> one STATUS effect with a pitch offset, +TRAP, GOLD removed, 28 effects + 3 reserved ids; net +33 B vs 646 before)** (was 109 B free at `$F000`: the SFX room for SND-4a / SND-5b; tape block 5 = `AY_LEN` from `AY_RESERVE`, loader / tests / #50 all symbolic; ISR contract unchanged); **D3-0: 4 KB** = 4,096 B at `$F000`, user 2026-10-06, game.md §11.2; was 7 KB `$E400`, before that 8 KB `$E000`): `ay_code..ay_code_end` (`src/ay.asm`), entry `AY_PLAY` = `AY_RESERVE`. **SND-2 T2**, in this order: `ay_play` (208 B, the mailbox dispatcher + `ay_silence`; ASSERT `ay_play == AY_PLAY`), the WZM v0.3 player `MODULE wzm` (`src/music/player.asm`, `DEFINE WZM_BUZZER`, no echo; 1,082 B = code + period table 990 + state 92: `wzm.pl_regs` .. `wzm.player_end`), the dispatcher state `ay_mode` / `ay_loop` (2 B) right after it, then `MODULE mus` (`build/music_game/game_songs.asm`, generated by `tools/build.sh`, found through `-i OUTDIR/build/music_game`): the 7 harpsichord songs + `mus.mus_tab` (`DW` song, id order `MUS_CRAWL` 1 .. `MUS_LAMENT` 7; ASSERT `2 * MUS_COUNT` B), 1,947 B. **`ay_vars` .. `ay_vars_end`** (= `wzm.pl_regs` .. the dispatcher state, 94 B, ASSERTed contiguous) is the only runtime-written part of the slot (`tests/game.py` #50 masks it; no SMC). Was the silent stub (37 B). **SND-5 (sound effects; review round + the full set, 2026-10-19):** `ay_play` 247 B (+39: `.hold` clears `SFX_NEXT` when nothing plays, the SFX fast-path test, the `sfx_step` / `ay_music` / `sfx_out` calls; `MUS_FIRST` id checks), player 1,106 B (+24: the `WZM_SFX` hooks — V1 not stored while an effect plays, `sfx_ran`, `sfx_dk`, `sfx_mix` merged into R7; ASSERTs: the smallest period != 0, `WZM_SFX` needs `WZM_BUZZER`), the SFX engine `sfx_step` / `sfx_out` / `sfx_dk` 318 B (+47: the `SFX_NEXT` deferral, slot keeps the higher priority) right after `ay_silence` (before the player), the dispatcher state 12 B (`ay_mode`, `ay_loop` + `sfx_ptr` 2, `sfx_prio`, `sfx_duck`, `sfx_per` 2, `sfx_vol`, `sfx_mix`, `sfx_ran` 2; inside `ay_vars`, now 104 B), the songs **6, 1,794 B** (Dungeon Crawl removed by the user 2026-10-19: −151 B + its table entry; `mus.mus_tab_first` = ids 2..7, `mus.mus_tab` EQU first − 2), and after them `build/sfx/sfx_data.asm` (`tools/sfx2asm.py` from `assets/sfx/effects.json`, `-i OUTDIR/build/sfx`): `sfx_tab` (`DW`, stride 2, index order) + **27 effects = 510 B**. SFX total 891 B (engine 381 + data 510) | `AY_LEN` **SND-5: 3,987 B, 109 B free** (SND-2: 3,239 B, 857 B free); ASSERT `ay_code_end <= $10000` | tape block 5 (headerless, `start` `.ay`) / .sna |
| 0 | **text block** (D3-TX; B3B-13 format, "Text" below) `text_img..text_img_end` = `TEXT_ADDR` `$C000` .. `POOL_START` (`TEXT_LEN` = `TEXT_PACKED`; ASSERTed below the `tap_loader` scratch `$E000`). The pool's bank-0 part starts at `POOL_START` (`alloc_reset`), so the pool never overwrites it | SND-1 strings: 200 strings, 79 tokens, **2,680 B** (`$C000..$CA77`, pool from `$CA78`; was D3-2: 198 / 82 / 2,684 B) | tape block 8 (headerless, `start` `.txt`) / .sna |
| 0, 4, 6 | **pre-shift pool**: every frame variant (facing × shift), boot-generated by a bump allocator (no variant straddles a bank); bank 0 from `POOL_START` (D3-TX), banks 4 / 6 from `$C000` | need **44,096** of `POOL_CAP` 46,472 B (D3-4; was 40,096) (D3-TX: 49,152 − the text block; ASSERT `POOL_NEED <= POOL_CAP`) (monsters 22,688 + largest hero **with its class FX kind** 18,528 = the Knight 18,176 (D3-4: +3,648 for THROW / BOW / WHIRL / POWER_STRIKE) + `K_FXW` 352 (the Wizard: 13,184 + `K_FXM` 1,152 = 14,336); before D3-4 the largest hero 14,528 = the Knight (C3-7: +1,920 for JUMP1/2; the Wizard 9,728 → 13,184 with JUMP1/2 + STAFF_RAISE/SWING) + 2 select idles + straddle slack; ASSERTed) | `gen_kind` / `gen_frame` at boot and at hero select |
| 7 | **level tilesets** (B3B-8): slots 0–3 `TSET_LO` `$DB00..$DFFF`, slots 4–7 `TSET_HI` `$FAA0..$FF9F`, 320 B each (`tools/tiles_convert.py` → `assets/gfx/tiles/tilesets.asm`, slot format under "Bank-7 tileset slots") | 2 × 1,280 B (`TSET_HALF_LEN`) | tape blocks 6 / 7 (headerless, `start` `.t7lo` / `.t7hi`) / .sna |
| 7 | **screen 2** `$C000..$DAFF` (A7): the screen the ULA shows during play, a copy of the bank-5 screen kept by `present` / `present_full`; **attr shadow** `SHADOW_ATTR` `$F800..$FA3F` (the room's tile attrs in screen-attr layout, rows 0–17; high byte = screen attr + `$A0`; `$FA40..$FA9F` = 3 spare PROTO rows). **D3-S2 (2026-10-12): the bitmap shadow (`$E000..$F7FF`, R-1 erase lever since A7) is gone** — `erase_rect` redraws `TILE_GLYPHS[ROOM_MAP]` (+ the row-17 ornament) and takes attrs from the attr shadow (decor attr cycles) | 6,912 + 576 B; `$DB00..$DFFF` + `$FAA0..$FF9F` = the tilesets (row above) | screen 2: `present*`; attr shadow: `shadow_rect` / `shadow_room` on room entry, door planks, potion pickup; `decor_tick` steps |
| 7 | **bank-7 cold code** (D3-S2) `b7_code..b7_end` = `B7_CODE` `$E000` .. ≤ `B7_LIMIT` `$F800` (`src/bank7.asm`, entered only through `far7`; rules under "Cold code placement") | **3E-T2: 5,931 B (kit 5,981), 213 B free (kit 163)** (+13: `use_slot` calls `page_run`, `tpt_intent`'s `IN_BAG`); 3E-T1: 5,918 B (kit 5,968), 226 B free (kit 176) (−109: `init_tiles` / `panel_boot` → the bank-6 boot block); SND-5b: 6,027 B (kit 6,077), 117 B free (kit 67) (MEM-SND: 5,998 B, 146 B free; SND-5b hooks +29 B: hero step 5, pickup 2x5, quaff 5, `ic_no` +2, cursor MENU +7) (+423: `src/boot7.asm` — `init_tiles`, `panel_boot` (far7 from `boot`), `panel_init7` (far7 nested from bank-3 `panel_init`, ~0.3k T per level start), `new_game` (far7 from `start_game`; far3s `level_reset_new` / `init_ent_common` / `new_game_proto`, ~0.5-0.8k T once per game); no data, no SMC); **SND-5: 5,575 B (kit 5,625), 569 B free (kit 519)** (+36: `ic_no_mana` (the NO MANA refusal + `SFX_FIZZ`; the two `ld a, TX_NO_MANA : jp c, ic_refuse` sites → `jp c, ic_no_mana`), `act_fire` → `sfx_abl` (the release sound by `ABL_*`, after the lead-col guard; a fizzled release sounds FIZZ), `xp_level` `SFX_LEVELUP`, `try_climb` `SFX_LADDER`; SND-5 elsewhere: bank 2 +122 (image free to FRT 300 → 178, `kind_tab` pad 41 → 13, see `$8000` row), low RAM +25 (`impact_line` → `sfx_msg`, `hero_fall` FALL, the jump JUMP, `door_open` DOOR, boot and `level_enter` (new game / descent) clear `SFX_NEXT`; spare 156 → 131), bank 1 +7 (`menu_run` `SFX_MENU`; free 650 → 643), bank-3 cold code 0 (no bank-3 call site; 407 B free)); SND-3: 5,539 B (kit 5,589), 605 B free (kit 555) (+146: `src/mus7.asm` — `mus_pick`, the Dangerous (W) cue from the `LIVE_LIST`, called from `end_turn`; the death branch writes the Y cue; `level_enter` (low RAM, +6 B: spare 162 → 156) clears `DNG_DWELL` / `DNG_CALM`); D3-9b: 5,393 B (kit 5,443), 751 B free (kit 701) (+364: `src/xp7.asm` — `xp_turn` (end_turn's MP regen, then `xp_level`), `xp_level` (the level-up + its log lines + `LT_HOLD`, **only in a tick's 1st frame**: else `XP_UP` stays set and `turn_input`'s entry retries it each INPUT tick, +7 B), `abil_learn` (the read-time learn / rank-up entry for 3E); `hero_st_init` +14 (restores the heroes' `KT_ATK` / `KT_EVA` columns); `end_turn` tail `jp z, xp_turn`); D3-8d: 5,029 B (kit 5,079), 1,115 B free (kit 1,065) (+469 (review fixes incl.: `mk_erase` cover test, `MK_WAIT`, BRIGHT frame B): `src/mark7.asm` — `mk_op` (draw / erase / in-place redraw, the drip hand-over), `mk_new`, `mk_draw`, `mk_forget`, `mk_erase`, `mk_drop`, `mk_spend`, `mk_sweep`, `vis_tail`, `mk_room` (reset + glyph / attr copy), `mk_hide`; `hide_sprites` +3); D3-8b: 4,560 B (kit 4,610), 1,584 B free (kit 1,534) (+312: `src/drip7.asm` — `drip_room` (the room's drip sources, from `vis_room_sync`; `DRIP_ROW` $FF), `drip_idle` / `drip_rnd` / `drip_try`, `drip_step` (spawn / let go, with a T_AIR re-check), `drip_cover` / `drip_land`, `drip_hide`; `hide_sprites` +3); D3-8f: 4,248 B (kit 4,298), 1,896 B free (kit 1,846) (+53: `follow_select`'s HOLD / FEAR filter 20, `use_icon`'s Whirlwind no-roll 11, `turn_input`'s post-action hero HOLD_GUARD clear 11, `act_pend`'s 5, `st_step`'s hero skip 6); L-RELIEF: 4,195 B (kit 4,245), 1,949 B free (kit 1,899) (+354: `follow_select` / `place_follower` / `arrival_conflicts` from bank 3 (+4: `follow_select`'s PROTO tail `jp far3` `follow_admit`), `do_exit`'s two `ld hl` / `call far3` → plain calls (−6)); before: **3,781 B** (`B7_LEN`, `-DDEBUG_KIT=0`; 3,831 B with the kit; **D3-8 review +37**: the held-path wake return in `turn_input`, `use_icon`'s refusal split (`IC_REFUSED`), `conf_roll`'s mid-ladder test, `mon_status`' cork yield; **2,363 B free** (kit 2,313)); **D3-8e2: 3,841 B (kit 3,891), 2,303 B free (kit 2,253)** (+29 over the D3-8c merge's 3,812: `act_begin` sets `COMBAT_NOT_BEFORE`, `act_pend`'s log wait from max(`MON_AT`, it), `end_turn` clears it); D3-8e: 3,816 B (kit 3,866), 2,328 B free (kit 2,278) (+26: `act_begin`'s `probe_act_prep` + far3 `proj_pre` with the spell / ammo rank row); D3-8 review 2: 3,790 B (kit 3,840), 2,354 B free (kit 2,304) (+9: `use_icon`'s `IC_NOTGT` (NO TARGET) handling: the line on the plain path, a stumble on the reversed one); D3-8: 3,744 B (**+610**: `status7.asm` (`st_step`, `mon_status`, the confused / fearful hero), the `turn_input` held-hero / step hooks, `use_icon` / `ic_melee` / `ic_disp` / `try_horizontal` FEAR + CONFUSED hooks; 2,400 B free (kit 2,350)); D3-7 T7: 3,134 B; T7 review +50: the swallowed-tap latch `LOG_PDIR`, the Mage-aware pre-filter, `act_pend`'s wait-only drain; **D3-7 T7: +193** (3,084 B) = the named miss line / `ent_kind` / `miss_pre` (`abil_ammo7.asm`), the log drain (`end_turn` / `turn_input` / `act_pend`), `power_fire`'s `slot_live` + Power break, the `floor_pickup` pre-filter + `PD_AMMO`; T6: 2,891 B (2,941 kit), +318 = `abil_ammo7.asm` (`abil_ammo` / `ammo_fire` + the `msg_*` line composer) and the list-driven `floor_pickup` (replaces `potion_pickup` + the `ammo_pickup` stub); T5: 2,573 B (2,623 kit, measured at T7; was written 2,620), +546 = the power attacks (`abil_melee7.asm`), `potion_pickup` / `ic_quaff` / `debug_kit` from bank 3, `act_seq` / `act_begin_ok`; T4: 2,027; T1: 1,773, +157 = `act7.asm` + the fire stubs; T0: 1,616, +336 = `intent7.asm` + the D3-7 stubs; D3-S2: 1,280); free to the attr shadow: the current figure is the bold one above (history: T7 3,010 B (2,960 with the kit); T7 first pass: 3,060 / 3,010; T6: 3,253 / 3,203; T5: 3,571 / 3,521; T1: 4,371); ASSERT `b7_end <= B7_LIMIT` | tape block 6 together with tilesets 0–3 (`B7_TAPE_LEN` = `TSET_LO..b7_end`, `start` `.t7lo`) / .sna; `tests/gfx_integrity.py` asserts `B7_CODE..B7_LIMIT` == the .sna (no SMC, no data: the canary for the freed shadow) |

Sources are read only at generation time via `copy_virt` (virtual < `$C000` →
bank 1 at +`$4000`, else bank 3; a frame straddling `$C000` is split) — with
ZX0 only the raw items/tiles (`init_tiles`; 3E-T1: gone, boot6_tiles reads the boot block in place) go through `copy_virt` (A6: the
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
growth to `FRT_MAX`). Then six (3E-T1: seven)
**headerless** blocks (flag `$FF`) that `start` loads with ROM `LD-BYTES`
(each with its own rewind-and-retry loop; 3E-T1: one loop over `tape_tab`, 5 B
per block: bank, address, length, `$FF` end — retries the failed block) before falling into `boot`: bank 1
(`SRC_LEN_LO`), bank 3 from `$C000` (`BANK3_LEN` = source tail + bank-3 cold
code) and (A8) bank 3 from `AY_RESERVE` (`AY_LEN`: the AY slot, a separate
block so the gap below it is not on tape), (B3B-8) bank 7 from `TSET_LO` and from
`TSET_HI` (`TSET_HALF_LEN` 1,280 B each: the level tilesets; two blocks so the
screen-2 / attr-shadow gap between them is not on tape; **D3-S2: the `TSET_LO`
block runs on through the bank-7 cold code**, `B7_TAPE_LEN` = 1,280 + `B7_LEN`;
`#50` checks it after a real tape load), (D3-TX) bank 0 from
`TEXT_ADDR` (`TEXT_LEN`: the text block; `check_paging`'s bank-0 probe byte,
written before it, is overwritten), (3E-T1, last) bank 6 from `BOOT6_ADDR`
(`BOOT6_LEN`: the boot block). Nothing in bank 7 is live
while `start` runs: screen 2 is not displayed (`$7FFD` bit 3 = 0 from BASIC),
the attr shadow / screen 2 are written only after `boot`, and the 128 editor's
bank-7 workspace is abandoned with BASIC (PROTO never returns to it). The
`.sna` enters at `boot` (all banks preloaded). `tests/game.py` #50 checks bank
1, bank 3 (whole `BANK3_LEN`), the AY slot (`AY_LEN`), both bank-7 tileset
blocks, the bank-0 text block (D3-TX), (3E-T1) the bank-6 boot block — at the menu, after
boot, still intact: the boot pool ends in bank 4 (`ALLOC_IDX` < 2 checked; `POOL_BOOT_NEED`
ASSERTed), so it is compared, not masked — and the low-RAM cold block byte-equal to the `.sna` after a real tape
load, and IM 2 installed.

### Boot block (3E-T1, memory levers (a) + (d))

`src/boot6.asm`, assembled by `main.asm` at the **top of pool bank 6**:
`BOOT6_ADDR..$FFFF` = `$F86E..$FFFF`, `BOOT6_LEN` **1,938 B** (code 249 + data
1,689; ASSERT `boot6_end == $10000`; `BANK_BOOT6` = `BANK_POOL2`). Own
headerless tape block, the last in `start`'s `tape_tab`; in the `.sna`
preloaded. `boot` runs it through `farb` (C = `BANK_BOOT6`) twice, both before
`alloc_reset`: `boot6_init` (under DI: the IM 2 install — vector table, ISR
image → `ISR_ADDR`, I, IM 2 — and the power-on state + `KEYTAB`, the screen
clear, the entity table clear) and `boot6_tiles` (after EI + `build_bitrev`:
`tiles_common` → `TILE_GLYPHS` / `TILE_ATTRS` 0..31, `orn_glyphs` →
`ORN_GLYPHS`, `panel_hot_img` → `HOT_COPY`, `font6x8` → the `FONT6` planes, all
read in place: no `copy_virt3`, no `GEN_SRC` staging, ~30k T). **Dead after
boot by contract:** the boot pool (every monster kind + the 2 select idles,
`POOL_BOOT_NEED` ASSERTed ≤ bank 0 + bank 4) never reaches bank 6, the hero
start's pool may overwrite the block — so it costs the pool nothing
(`POOL_NEED` 44,096 of `POOL_CAP` 46,472 unchanged, slack 2,376 B kept for 3F; 3E-T4b: slack now 2,588, see its ledger),
and **nothing may read it after `boot`** (`tests/game.py` #61: bank-6 code may
run only below the select screen; no SMC / data writes in the block,
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

### Overlays (3E-T1) — `ovl_run`, the GEN_SCRATCH window; screen-2 window contract

**Build** (`main.asm` "OVERLAYS", `tools/build.sh`): each overlay is source
INCLUDEd at its runtime load address (`DISP`) into the bank-0 scratch
`OVL_RAW_ORG` `$E100..` (above `tap_loader`; bank 0 is pool at runtime, never
loaded) and SAVEBINed to `build/ovl/<name>.bin`. `build.sh` runs sjasmplus
twice: pass 1 (`-DOVL_PASS=1`, no packed streams) writes the raw images, each
is packed with `tools/bin/zx0` → `<name>.zx0`; pass 2 (`OVL_PASS` 2, the real
build) INCBINs the streams (`-i build/ovl`) into bank 1 **after the UI code**
(`ovl_blobs..ovl_blobs_end`, labels = runtime `$C000`-window addresses, bank
`BANK_UI1`; last in bank 1, so their sizes move nothing an overlay can
reference) and writes the raw images again: **build.sh fails if any differs
from pass 1**. Today: **`page`** (3E-T2, `src/page_ovl.asm` at `PAGE_ORG`,
300 B raw → 273 B `ovl_page_zx0`; `tests/page.py` P1 round-trips it) and
**`items`** (3E-T6, `src/items_ovl.asm` at `ITEMS_ORG`, 1,027 B raw → 881 B
`ovl_items_zx0`, bank `BANK_OVL_ITEMS`; run by `level_new`, see "3E contracts"). The
3E-T1 `ovl_test` (30 B) is dropped: `tests/ovl.py` O1 assembles the same
self-test overlay in Python and pokes it into the free bank-1 tail.

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
back in the first). Free page-time RAM besides the window (verify before
use): `GEN_SRC` + `PLAY_CELLS`.. `TX_DEC` `$6B80..$6D14` (405 B).
**Silent in-play overlay (contract, not built):** the same window (map
saved / restored the same way, ~25k T + the unpack) serves any cold in-play
event that neither renders nor reads `ROOM_MAP` (3E item effects,
`hero_recalc`, ...): no `present_full` needed (nothing on screen changes
while it runs); ~1 frame per use. (The old bank-5 band window is retired:
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
do nothing. Placeholder layout (Q3 open; golden `tests/golden/page_empty.hash`):
rows 0-1 title `BAG` (menu font, col 2) + `ITEMS 0/20` (row 1, right), row 2
the menu ornament (`menu_orn_b`, `MENU_A_SUB`), rows 4..14 the 5×4 grid of
16×16 boxes (cols 9..22, centred), rows 16..17 `WORN` + 4 boxes (cols
11..21), row 19 the description, row 20 the verbs (placeholder `USE EQUIP REMOVE DISCARD`, game.md §8.11), **row 22 the page's
message row**, row 23 the ornament; 6×8 text from raw ASCII in the overlay
(no text-block strings; `NO BAG YET` dropped from `strings.txt`, −7 B bank 0).

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
`GEN_SRC` stays as the `vdata` staging buffer (`pblit`; 3E-T1: `panel_boot` is gone). Decompressor =
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
| `$8000..$A5EE` | `image_start`…`code_end` | HOT code + static tables (3E-T0: `$A5E3` -> `$A5EE`, 9,710 B; free to `FRT` 29 -> 18 B, the `kind_tab` ALIGN pad unchanged 85 B: `sfx_msg` +11 B after `kind_tab`; SND-4a: low-RAM cold block spare 131 → 118 B (−13 in `level_descend` / `level_enter`; `stinger_wait` in bank 1, 412 B free); **SND-5b: `$8000..$A5E3`, 9,699 B incl. the pad; 29 B to `FRT` + 85 B `kind_tab` ALIGN pad (was 136: `mv_sfx` 48 B + its `call` 3 B in `logic.asm`)** (`bars_draw` 96 + `num2` 35 moved from the end of `panel2.asm` to `src/bars2.asm` after `kind_tab`: 131 B more pad for new hooks BEFORE `kind_tab`, the total bank-2 free (165 B) unchanged; `kind_tab` stays `$A100`); SND-1: `$8000..$A560`, 9,568 B; 160 B to `FRT` + 5 B `kind_tab` ALIGN pad** (+8 before `kind_tab`: `sample_input` `call snd_scan`, `intent_tick` `bit SC_SOUND, e` / `call nz, snd_hot`; +17 after: `snd_scan` / `snd_hot` in `sfx2.asm`; 5 B of pad left: the next bank-2 byte before `kind_tab` beyond that moves it a page); SND-5: `$8000..$A54E`, 9,550 B; 178 B to `FRT` + 13 B `kind_tab` ALIGN pad — 14 more bank-2 bytes BEFORE `kind_tab` move it a page (+256): +24 before it (`fx.asm` `call fx_imp_sfx` + the bounce request, its two `jr` → `jp`; `anim.asm` the two LAND requests), +87 after (`src/sfx2.asm` `sfx_req` (+ the `SFX_NEXT` loser rule) / `sfx_msg` (12-entry table) / `sfx_abl` (9-entry table) / `fx_imp_sfx`); D3-9b: `$8000..$A4D4`, 9,428 B; 300 B to `FRT` + 41 B pad; `kind_tab` stays `$A100`** (+17 B before `kind_tab`: `icon_poll`'s MP poll 13, `panel_more`'s PD_MP test; +39 B after `mark.asm`: `src/xp2.asm` — `xpn_tab` (XP_NEXT, 16 B, **the single table**, read by bank-7 `xp_turn` and bank-1 `item_info`) + `item_mp` (MP bar + number); **the heroes' `KT_ATK` / `KT_EVA` columns (ids 0 / 1) are runtime state**: `xp_turn` adds the §4.1 L4 / L8 atk and L6 eva steps there (0 T per to-hit roll), `hero_st_init` writes back `KN_ATK` / `WZ_ATK` / `KN_EVA` / `WZ_EVA` (main.asm) on a new game). **D3-8d: `$8000..$A49C`, 9,372 B; 356 B to `FRT` + 165 B pad; `kind_tab` stays `$A100`** (+460 B: `src/mark.asm` after the kind arrays (`kind_tab + KT_END` = `$A2D0`: `mark_tick`, `mk_slot` (+ the review fixes: damage test past the op cap, the `MK_WAIT` retry gate), `mk_rec` / `mk_cb(de)` / `mk_bit`, 4 B scratch); +31 B before `kind_tab` (pad 196 → 165): `cell_occ`'s mark-map test 14, `idle_phase`'s HOLD test 12, the `decor_gate` call 3). **D3-8b: `$8000..$A2CF`, 8,912 B; 816 B to `FRT` + 196 B pad; `kind_tab` `$A000` → `$A100`** (+206 B over D3-8f: `src/drip.asm` 201 — `drip_tick` (TP_FIRE exit, cover test, gates, the fall step with its row-17 guard), `drip_erase`, `drip_draw`, the 3 glyphs 22 B — `cell_occ` (decor_tick's inline occupancy loop made a shared routine, +3 net), `decor_gate` +2. Pad history: the D3-8f build reported 146 B of pad before `kind_tab` (the D3-8 figure below, 167 B, was not re-measured after D3-8c..f); the code grew past it, so `kind_tab` moved a page). **D3-8: `$8000..$A1CF`, 8,656 B; 1,072 B to `FRT` + 167 B pad; `kind_tab` `$9F00` → `$A000`** (+~140 B: the render tint, `st_tint`, `st_sig`). **D3-S2: `$8000..$A0CF`, 8,400 B; headroom 1,328 B to `FRT` + 249 B pad = 1,577 B** (was 48 + 196): −1,280 B to bank 7 (`bank7.asm`: the player turn, `end_turn` / `do_exit` / `hide_sprites`, `pause_hook`'s body, intent_tick's ICON MODE branch), −96 B to low RAM (`clear_screen`, `print_char`, `print_str`), +~25 B stubs / `far7`, Part 1 (no bitmap shadow) +11 B; `kind_tab` `$A400` → `$9F00`) (8,912 B incl. the pad, C3-3; 8,656 B, C3-2; 8,144 B, C3-1; 7,888 B, B3B-13; B3B-R2 8,144 B; B3B-10 9,680 B; incl. the ALIGN pad + the 16-B `dt_attr_tab` and the 64-B `tile_flags` before `kind_tab`; `ASSERT code_end <= FRT`). **Headroom (D3-5, build DISPLAY): 48 B to `FRT` + 174 B pad** (D3-5 +899 B: `fx.asm`, `kind_tab` `$A000` → `$A400`; "3D contracts"). Before: **(D3-0): 1,072 B to `FRT` + 108 B pad** (D3-0 −256 B code: the zap (`draw_zap` / `zap_covered` / `draw_glyph` / `dt_zap` / the anim + hide paths, ~250 B) out, `kind_tab` `$A100` → `$A000`). Before: **(C3-2b; + main's B12 merge, see the build DISPLAY): 816 B to `FRT` + 166 B pad = 982 B** (C3-2b: the ICON MODE `intent_tick` / `tpt_intent` +~250 B, paid by moving the icon state / drawing — `slot_act_tab` … `icon_state`, `slot_want`, `item_icons`, `sel_paint`, `lvl_draw`, `pot_slot` — to bank 3 (`icons3.asm`, entered by `item_icons_far` → far3); C3-3 +362 B: `icons.asm` — `slot_act_tab` / `slot_act` / `abil_rank` moved from bank 3, `icon_state`, `icon_poll` + `icon_sig`, `item_icons`, `sel_paint`, `lvl_draw`, `panel_more`, `print6x`; old `item_icons` / `pot_col` out; `kind_tab` → `$A100`. C3-2 + B11/B14 merge: 1,297 B (B11 +11 B; C3-2 alone: 1,308 B) (C3-2 +391 B: `intent_tick` + `fire_used` / `bag_msg` / `pause_hook` ~190, `tpt_intent` ~110, the `legacy_input` gates in `input_tick` / `sample_input` / `read_turn_input` / `try_player_turn` ~40, `SC_ENTER` ~6; `kind_tab` moved `$9E00` → `$A000`. C3-1: 1,699 B (C3-1 +154 B: `input_tick`, `read_stick` / `stick_tab` + the Sinclair presets (20 B), `sample_input` on `STICK` + `PLAYER_SC`; `kind_tab` moved `$9D00` → `$9E00`. C3-0: 1,853 B (C3-0 +5 B: `farb` / `far1` / `far3`, `kind_tab` stays at `$9D00`; B3B-13: 1,840 + 24 = 1,864 B; B3B-13 −151 B net: the strings `str_found/quaff/died/win/welcome` + `kind_names` / names ~160, the PROTO chest win in `end_turn` ~35 out; `tk_get` 44 + `print6t` 21 in, `item_log` → `print6t`; `kind_tab` moved down to `$9D00`, read from the `.sym`. Before: B3B-12: 1,584 B to `FRT` + 129 B pad = 1,713 B; B3B-12 +32 B: `try_climb` `EX_LEVEL` (only at `RD_EXITCOL` with `LF_GRATE_OPEN`), the `do_exit` → `level_descend` dispatch, the PROTO win gated on `LVL_DEPTH` 0; B3B-R2: 1,745 B) for code/static tables (B3B-R2 −1,538 B net: `src/turn3.asm` (monster phase, attacks, potions, impact messages; 1,558 B) out to bank 3, + the far3 call sites (5 sites, +20 B); `kind_tab` moved to `$9E00`. (The raw A/B build that kept turn3 in bank 2 was retired in B3B-12, manager decision.) Before: B3B-10: 48 B to `FRT` + 159 B pad = 207 B (B3B-10 +355 B: `decor.asm` 352 (`decor_tick` with the step inlined, `dt_zap`) + the `play_loop` call, `dt_attr_tab` 16 in the pad; `kind_tab` moved one page up to `$A400`. Before: B3B-11b: 560 B to `FRT` + 18 B pad = 578 B (B3B-11b +74 B: `item_icons` + `pot_col` moved here from `HOT_COPY` ~65, `print6g` / `p6_inline` (the print6 getter interface) ~55, `item_log` one item, no chunk state −~45; B3B-11: 652 B; B3B-11 +82 B net: `panel2.asm` 435 (`item_log` 121, `log_scroll` 183, `bars_draw` 96, `num2` 35), `str_cat` / `show_impact_msg` composer, the `panel_tick` call; out: the A7 HUD (`hud_status` / `hud_room` / `msg_begin`, `clear_row` 155, `hud_track`, `print_char_hud`, `print_dec`, 3 strings) ~350; the rest of the panel's hot code sits in `HOT_COPY`. Before: B3B-8: 560 B to `FRT` + 174 B pad = 734 B; B3B-8 −69 B net: the PROTO `room_tab` + 4 room descriptors (~105 B, now bank-3 `proto_rooms`) and the old `room_desc` / `exit_h` / list loops out; `seg_storey` 13, `room_side` 36, `try_climb` `.vexit` 20, `potion_pickup` on `FLOOR_LIST`, the `hud_room` letter 7 in. Before: B3B-5 + review + B10: 560 + 105 = 665 B; B3B-5 used 402 B of the 1,067 (B10 hardening: flyer box row clamp 6): `tile_flags` 64, `cell_addr` / `cell_blocked` / `lead_cell` / `desc_byte` 57, `box_solid` (flyer steps, jump swept box) 34, `LOCK_SHOWN` clear 3, terrain + pit + door hooks in `try_horizontal` / `try_step` ~85, jump chord + key C in `try_player_turn` / `sample_input` ~30, `M_FALL` / `M_JUMP` anim 83 + `jump_dy` 12, room descriptors +16; the rest of B3B-5 is bank-5 low RAM. Before: A7b rebased on the B8 rev 816 B to `FRT` + 251 B pad = 1,067 B; A7 review: 993 B; A7b: code −78 B net — the one-pass record render (−138 B) and the blit rewrite (−46 B) pay for the erase row stepping (+26), `stamp_rect` / the 16-bit blit entry patch (+19) and the present `.full8` path (+61); A6: 677 B; A7: 111 B after present / pmark / HUD tracking / in-place rect dedupe / paging +566 B; the review moved 1,062 B of cold code out — `build_room_map` 254 B to bank-5 low RAM, `new_game` + `init_ent_common` + `spawn_tab` and follower selection + arrival conflicts 794 B to bank 3, net of the `far3` call sites — and added the B8 flyer ladder-end rule +159 B and the bank-2 `map_cell` +21 B; the 2026-10-02 cross-or-leave flyer rule + blocked-climb wait: +4 B net), plus the 1,536 B free runtime RAM `$B200..$B7FF` below. Code bytes `$8000..kind_tab_pad` 7,439 (B3B-R2; B3B-10 8,977; B3B-11b 8,622; B3B-11 8,548; B3B-8 8,466; A7 review 8,271; A7 9,153; A6 8,587). `kind_tab` page-aligned at `$A100` (D3-8b; `$A000` D3-8; D3-S2 `$9F00`; `$A400` D3-5; D3-0 `$A000`; `$A100` C3-3; C3-2 `$A000`; C3-1 `$9E00`; B3B-13 `$9D00`; B3B-R2 `$9E00`; B3B-10 `$A400`, before `$A200`; moves with the code: tests read it from the `.sym`), **2 pages** (`KT_SIZE` `$200`): 13 parallel **32-B** kind arrays (`K_MAX` 32; ids 0..8 used, 2 = Rogue hole; **D3-4: ids 30 / 31 = the class FX kinds `K_FXW` / `K_FXM`, only their `KT_FID0` / `KT_FCNT` columns are set** — 3F's monster rows have ids 9..29) + `KT_MOD9`/`KT_DIV9` tables (n mod/div `STOREY_ROWS`, n = 0..23; B3B-3, were MOD7/DIV7 at the same offsets), `KT_END` `$1D0` (the old "48 B spare in its page (resistances, 3F)": the resistances are bank-3 `kx_tab` since D3-0; **D3-8d: `src/mark.asm` is assembled from `kind_tab + KT_END` on**, i.e. right after the arrays, so `code_end` = the end of `mark.asm`). No array crosses a page: `KFIELD` folds the page into `H`. `frame_tab` **4 B/fid** (`FT_COLS`, `FT_H`, `FT_OFFR`, `FT_OFFL`: only what the renderer reads; D3-4: 101 fids = 404 B). `far1` / `far3` / `farb` / `restore_page` / `blit_keep` / `enter_select`: the far-call trampolines (53 B, C3-0). |
| `$A600..$AFFF` | `FRT` | frame runtime table (A6: moved from `$B200`): 16 B/fid (4 variants × bank,lo,hi), **`FRT_MAX` 160** (101 used, D3-4; 74 at C3-7); `FRT = P_ENTITIES − FRT_MAX × 16` |
| `$B000..$B1FF` | `P_ENTITIES` | 16 slots × **32 B** (layout below); slot 0 = hero |
| `$B200..$B7FF` | `BANK2_FREE` | the vacated A5 `FRT` (1,536 B, runtime RAM, not in the image/tape; `BANK2_FREE_END` = `SLOTREC`). **B3B-1 (D8): fully reserved; B3B-11 / B3B-11b use it** — **`FONT6` `$B200..$B5FF` = the PLANAR 6×8 font** (B3B-11b, for the quad printer): line *l* of char *c* (32..127) at `FONT6 + (l>>1)*256 + c + (l&1)*FONT6_WB` (`FONT6_WB` 96): 4 pages, even lines in window A (offsets 32..127), odd lines in window B (128..223); built at boot by `panel_boot` from the char-major `font6x8` (bank-1 `vdata`, via `GEN_SRC`), glyph bits 1..0 masked off. Free holes inside the planes: offsets 0..31 / 224..255 of each page (`$B200..$B21F`, `$B2E0..$B31F`, `$B3E0..$B41F`, `$B4E0..$B51F`, 32 + 3 × 64 B); (B3B-13..C3-7: `ZAP_GLYPHS` `$B200..$B20F`, gone with the zap in D3-0.) **D3-0: the holes hold the 3D runtime state** — see "3D contracts (D3-0)": `FXREC` `$B2E0..$B30F`, `ST_FLAGS` `$B310..$B31F`, `ST_T1` / `ST_T2` / `ST_X` `$B3E0..$B40F`, `FXQ` `$B410..$B41F`, `RANK_ROWS` `$B4E0..$B4FD`; free: `$B200..$B21F` (32 B), `$B4FE..$B51F` (34 B). **`HOT_COPY` `$B5E0..$B7FF`** (544 B, boot-copied hot code, risk R2): **`$B5E0..$B7D6` = the panel hot image (503 B, C3-3; was 515**: `print6` (quad printer, 4 SMC fetch sites + 8 SMC plane offsets) ~270, `log_push` / `log_push_end` / `log_drop`, `panel_tick` / `panel_step`, `item_hp`, `item_depth`), **41 B spare** (C3-3: `panel_step` polls through `icon_poll` and ends in `panel_more`, bank 2; ASSERT `HOT_COPY + PANEL_HOT_LEN <= HOT_COPY_END`; the build DISPLAY reports it). Labels in the `.sym` are the runtime addresses (`DISP`) |
| `$B800..$B8FF` | `SLOTREC` | A7b: per-slot render record, 16 slots × **16 B** (one page; record = `SLOTREC + slot*16`, fields reached by `inc l`): `R_VIS +0`, `R_FID +1` (written by `anim_tick`), `R_FPX +2`, `R_FPY +3`, `R_COL +4`, `R_ROW +5`, `R_COLS +6`, `R_ROWS +7` (`R_FID..R_ROWS` = the entity's drawn block `E_DFID..E_DROWS` in the same order: `draw_slot` copies it with one LDIR; ASSERTed), `R_LEFT +8`, `R_ATTR +9`, `R_DATTR +10`, `R_DIRTY +11`, `R_LOG +12`, **D3-8e2: `R_TINT +13`** (= `R_ATTR | 4`: the body attr — kind or status tint — last shown with no reaction pending; `render` keeps showing it while `E_REACT` is pending, game.md §6.5.1), **D3-8d: `R_MK +14` / `R_MKLO +15`** (the slot's status mark as drawn: g / frame / row >> 3, the cell's low byte; "Status marks (D3-8d)"; no spare left) (was the 13 × 16-B `SLOTVARS` arrays `N_VIS`… `$B800..$B8CF`) |
| `$B900..$B9BF` | `DMG_LIST` | per-render damage rects, 4 B each (c0,c1,r0,r1), 48 max |
| `$B9C0..$B9CF` | `PEND_DMG` | queued damage for the next render (4 rects) |
| `$BA00..$BA4F` | `LIVE_LIST` | per-turn collider list, 5 B/entry (`LL_STRIDE`: slot, ptr, w, h); `LIVE_N $BA50`; entry 0 is always the hero (B19 `box_free_mon` skips it) |
| `$BA60..$BA6F` | `RLIST` | per-tick render list (slots visible or still drawn); `RLIST_N $BA70`, `RL_IDX $BA71` |
| `$BA72..$BA79` | `PL_X/Y/W/H`, `PL_STOREY`, `PL_LADDER`, `MSG_Q`, `BLIT_CROWS` | per-turn hero cache, queued impact message, aligned-blit counter |
| `$BA80..$BA9F` | `SEL_FRT_SAVE` | 2 × 16 B: the select idles' boot FRT rows (`sel_frt_copy` saves at boot, restores on every `enter_select`; a game's `gen_kind` re-points its hero's rows above the alloc mark, which the next hero overwrites) |
| `$BAA0..$BAFF` | `PRES_MASK` | A7 present dirty-cell mask: 24 rows × 4 B (`PRES_LEN` 96), byte `row*4 + col/8`, bit `7 − col%8`; ends at the page end (`present` stops when `L` wraps) |
| `$BB00..$BC00` | `ISR_VEC_TABLE` | A8 IM 2 vector table, 257 B, every byte `ISR_VEC_BYTE` `$BC` (`I` = `$BB`); filled by `isr_install` at boot (3E-T1: `boot6_init`, the boot block) (runtime only, not on tape) |
| `$BC01..$BC0B` / `$BC0C..$BC0F` | `DRIP_*` / `MK_*` | **D3-8b: the decorative drip** (11 B, `level_defs.asm`; layout under "3D contracts" → "Decorative drip (D3-8b)"); **D3-8d: the status-mark state** `MK_N` / `MK_RR` / `MK_OPS` / `MK_LEFT` (4 B, `combat_defs.asm`; "Status marks (D3-8d)"); no spare left (was 4 B; 15 B before D3-8b) |
| `$BC10` / `$BC11..$BC40` | `ANIM_N2` / `ANIM_LIST2` | B3B-10 (B3B-9 review): the decor list of a NEXT_MAP build (do_exit), same format as `ANIM_N` / `ANIM_LIST`; `room_shadow` copies the 49 B over them after the scroll. (Was the B3B-1 `OCC_MASK`, 72 B: dropped — `decor_tick` tests a due cell against the drawn footprints directly, see "As built in B3B-10") |
| `$BC41..$BC49` / `$BC4A..$BC50` / `$BC51..$BC5E` | `HERO3D` / `TURN_PEND` / — | **D3-0: `HERO3D`** (9 B: `MP_RG`, `HERO_RES` 3 B, `HERO_IMM`, `MP_SH`, `STAT_SH`, D3-6a `HERO_DEF`, `XP_UP`; "3D contracts (D3-0)"), **D3-7: the `TURN_PEND` block** (7 B: `TURN_PEND`, `ACT_ABL`, `ACT_AT`, `MON_AT`, `FX_DROP`, T7 `LOG_TURN` / `LOG_PDIR`), **3E-T2: `PAGE_OPEN` `$BC54` (1 while the bag page is up) / `PAGE_N` `$BC55` (opens, mod 256)** (`combat_defs.asm`, test-observable, not zeroed per level), then spare (12 B; D3-8: 14 B; T6: 16 B; D3-0: 21 B; was 30 B spare, B3B-10: the `ANIM_RR` round-robin index dropped, unused — the per-entry `AL_PHASE` counters + per-tick caps need none) |
| `$BC5F` / `$BC60..$BC8F` | `ANIM_N` / `ANIM_LIST` | B3B-1 (D6; B3B-10: `ANIM_N` moved `$BC58` → `$BC5F` so count + list are one 49-B block): animated decor cells of the room in `ROOM_MAP`, 12 × 4 B (`AL_COL`, `AL_ROW`, `AL_TYPE`, `AL_PHASE`); filled by the decor deriver (B3B-9) or copied from `ANIM_LIST2`; stepped by `decor_tick` (B3B-10) |
| `$BC90..$BCBB` | `HERO_ST` | C3-0: the 3C hero / input state block (44 B, runtime RAM, `src/hero_defs.asm`; layout in "3C contracts"); full since C3-2 (`CUR_REP` .. `PAUSE_REQ`) |
| `$BCBC..$BCF3` | `ISR_ADDR` | A8 ISR, 56 B (`ISR_LEN`; 68 with `ISR_SAVE_ALT`, 42 with `ISR_ROM_CHAIN`; ASSERT end ≤ `ISR_ADDR_END` `$BD00`), copied from `isr_image` at boot; `$BCF4..$BCFF` spare |
| `$BD00..$BEFF` | — | stack, **768 B** (SP = `$BF00`, grows down to `STACK_BOTTOM $BD00`; A8: was 1 KB from `$BB00`; C3-1: `tests/world.py` W20 re-measures it: 40 B over boot, a generated D1 start and 53 random turns). **Measured max depth 40 B** (lowest byte touched `$BED8`; pattern-fill over boot, both hero starts, a room transition, the §8.2 walkthrough and both `budget.py` fights, ROM IM1 ISR included; tape path's `LD-BYTES` not covered, ~10 B). The A8 ISR adds 16 B (return address + 6 pairs) + the player's own depth to whatever is in use. **SND-2 T6:** W20 with the WZM player live (Lament) measures **44 B** (lowest byte `$BED4`) |
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
| `$6940` | `GEN_SRC` | 512 | B3B-11b: `pblit` (one icon, <= 54 B) stages `vdata` here (3E-T1: `panel_boot`'s font halves no more: boot6_tiles reads the boot block in place) — new game only, never during generation. C3-6: the pause overlay saves rows 7-9 here (`PAUSE_SAVE`, 864 B: it runs on into `GEN_MIR`) while paused |
| `$6B40` | `GEN_MIR` | 512 | generator: mirrored frame (`LOWRAM_END` = `LOWRAM_FREE_END` `$6D40`). D3-TX: its top 43 B `$6D15..$6D3F` = `TX_DEC` (`tx_dec`'s transient decode buffer, menu text) |
| `$6D40..$6E7F` | `LVL_STATE` | 320 | B3B-1: **3B level state** (header 16, `EDGE_TAB` 6 (+10 spare), `ROOM_DESC` 9 × 16, 16 spare → **3E-T3: `TRAP_LIST` 6 × 2 + `TRAP_N` + 3 spare** at `$6DF0`, `FLOOR_LIST` 32 × 4) — byte layout under "3B contracts" / "3E contracts". Runtime only (not on tape). Written by `level_gen` (B3B-7) or, for the PROTO rooms A–D, by `proto_level` (B3B-8, from `new_game`) |
| `$6E80..$6EBF` | `ORN_GLYPHS` | 64 | B3B-1: row-17 ornament glyphs (8 × 8 B, game.md §3.3: not tile ids, same on every level). Here, not in bank 3, because `orn_cells` (also called from the scrolls) reads it with any bank paged. Filled at boot by `init_tiles` (bank 3, from `panel_orn.asm`). `LOWRAM_END_3B` = `LOWRAM_FREE_END` = `$6EC0` |
| `$6EC0..$6F31` | `LP_STATE` | 114 | **LP (game.md §9.4, plan task LP)**: the lazy-population level budget + `ROOM_VISITS` + 9 room records (102 B persistent + 12 B `lp_enter` scratch) — byte layout under "LP contracts". Runtime only. Written by `lp_budget` (level entry) / `lp_bank` / `lp_enter` (room changes). `LOWRAM_END_3B` = `LP_END` (`$6F32`): the test stubs moved up with it |
| `$6F32..$71A5` | free | 628 | of which 295 B (D3-4, 101 frames) are kept for descriptor growth (below); **3E-T6: 119 spare** (−205: `it_tab`, `item_glyph` / `item_ink`, `fl_attr`, see "3E contracts" ledger); **3E-T2: 333 spare** (−43 `page_run`); 3E-T1: 376 spare (was 118 at main `9c99ad1`: the boot code / ISR image / key table → the boot block, the table-driven tape loader, + `ovl_run` 30 B; ledger under "Boot block"); 259 spare (`LOWRAM_SPARE` DISPLAY; **D3-8b −5: `vis_room_sync` ends `ld hl, drip_room` / `jp far7`**; was 264; **D3-S2 −89 (from the measured 353): `clear_screen` / `print_char` / `print_str` moved here from bank 2**; **L2 engine −28: `pit_range` + `pit_w` reading `L2_PITW`, `jump_pit` on `pit_range`**; before: 400, measured after merging D3-4 + J1: **D3-4 −8 (`start_game` generates the class FX kind) + 101 frame descriptors; J1 −145: `try_jump` / `jump_pit`**; earlier history as before: LP −114 `LP_STATE`; D3-TX −55; B12 −21; C3-2 −1; B14 −175) |
| `$71A6..$7FFF` | `lowram_code` (`start` first) | 3,674 | **cold block**, ends exactly at `$8000` (`src/lowram.asm`): **3E-T2: code 3,169 B + 101 descriptors 505 B**; 3E-T1: code 3,126 B (was 3,889 at `$70CF`); before: code 3,238 B + 101 frame descriptors 505 B (D3-S2 +89 incl. the bitmap-shadow paths' removal: + `clear_screen` / `print_char` / `print_str`, − `room_show` / `room_shadow`'s shadow ornament; L2 engine +28: `pit_range` / `pit_w`; D3-4 +8: `start_game` → `gen_kind(HERO_KIND + K_FX_BASE)`; J1 +145: `try_jump` D 6 / 7 + `jump_pit` + `pit_w`; earlier: D3-TX `tx_dec` + `.txt`, B12 +21, B14 +175, C3-2 +1, C3-1 +33, C3-0 +3, B3B-13 +37) |
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
`$5F8C-$5FFF` (116 B) — `tests/items3e.py` R1/R2 canary them through a game start, play and a descent). A8: after `boot` nothing uses the system variables but
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
| `$BF42..$BF4F` | allocator, damage counts, exit dest/storey/col (`$BF4A..$BF4B` spare since D3-0: were the zap overlay's `ZAP_COL/LEN`; `$BF48` below) | internals |
| `$BF48` | `CLIMB_BLK_XY` | B18 word: `CLIMB_BLK_ID`'s (x, y) at its last block (`climb_blocked`): a repeat blocker that moved since (yielding) earns another wait, up to `CLIMB_SQZ_N` (4) blocks; one that did not move is squeezed past. Test-observable |
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
| `$BFA0` | `MSG_BUF` | 32 B: `show_impact_msg` / `impact_line` (B14: also the squeeze line) composes the impact line here (B3B-13: a token stream, pre + name + post, ≤ 31 B + 0 ASSERTed), then `log_push` copies it (B3B-11; tests use it as a stub result byte) |
| `$BFC0` | `TIMING_MARK` | spare |
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
| `$BFD0..$BFFF` | **3B sub-range** (`STATE_3B`, B3B-1) | `PANEL_DIRTY $BFD0` (D5 `PD_*` bits), **`EXIT_LOCK $BFD1`** (C3-2b: directions ignored until released after leaving ICON MODE; was spare), `HUD4_EXT $BFD2` (4 B) / `HUD4_PW $BFD6` (4 B): rows 20..23 (B3B-11: the successors of `HUD_EXT`/`HUD_PW`), `LOG_QN $BFDA` (pending messages), `PANEL_POT_SH $BFDB` (potions last drawn), `P_NUMBUF $BFDC` (3 B: number / depth text), **`FIRE_LOCK $BFDF`** (C3-2b review: FIRE masked after BREAK until FIRE is released; B3B-11b: was `P_LIM`), `LOG_Q $BFE0` (8 B: `LQ_RD` +0 oldest ring slot, `LQ_DROP` +1 dropped / replaced pushes (saturating, expect 0), +2..+7 spare — B3B-11b: no chunked-print state), `PANEL_HP_SH $BFE8` (2 B: hero HP, MAXHP last drawn, `$FF` = never; B3B-11b, was `$BFD1`), **`JOY_MIRROR $BFEA`** (C3-0, see "3C contracts"), **SND-2 sound mailbox `$BFEB..$BFF0`** (below), `$BFF1` `DNG_DWELL` / `$BFF2` `DNG_CALM` (SND-3: Dangerous cue state, `mus7.asm`; `level_enter` clears both), **`$BFF3` `SFX_NEXT`** (SND-5, below), `$BFF4..$BFFF` spare. Test-observable |
| `$BFEB` | `SND_MODE` | SND-2 (game.md §3.6): bit 0 `SND_MUSIC`, bit 1 `SND_SFX`, bit 7 `SND_HOLD` (pause). Boot = `SND_ALL` (3); per power-on: `new_game` / `hero_st_init` / `level_*` never write it. Main code: single-byte store or `set` / `res` |
| `$BFEC` | `MUS_REQ` | SND-2, **level**: the looping tune id (`MUS_*`, `MUS_FIRST` 2 ..`MUS_COUNT` 7; id 1 = the removed Dungeon Crawl, rejected like any invalid id), 0 = silence. Never consumed: `ay_play` compares it with its private `ay_loop` and (re)starts on a change. Written by main code only (SND-3: `mus_pick` is the only writer in play). Boot 0 |
| `$BFED` | `MUS_SHOT` | SND-2, **edge**: one-shot id, 0 = none. Main writes, the ISR clears (taken, or dropped while music is off / held, or an invalid id). A new shot replaces a playing one. Final cue (Y death, T win): `MUS_REQ` 0 then `MUS_SHOT` id; a stinger (R) leaves `MUS_REQ`: the loop restarts at bar 1 when the shot ends. Boot 0 |
| `$BFEE` | `MUS_STATE` | SND-2, ISR-written: bits 0-1 `MS_IDLE` 0 / `MS_LOOP` 1 / `MS_SHOT` 2; bit 7 `MS_DONE` = the last one-shot finished (set when it ends, cleared when the next shot is taken; kept through loops / idle / music off). Boot 0 |
| `$BFEF` | `MUS_CUR` | SND-2, ISR-written: the tune id sounding (the shot's while one plays), 0 = none. Boot 0 |
| `$BFF0` | `SFX_REQ` | **SND-5, edge**: the requested sound effect id (`SFX_*`, `build/sfx/sfx_ids.inc` = prio << 5 \| index 1..`SFX_COUNT`), 0 = none. Main code writes it only through **`sfx_req`** (bank 2, `ld a, SFX_x : call sfx_req`, 5 B a call site, any bank; keeps A / BC): replaced only by a request of >= priority; dropped while `SND_HOLD` or with the SFX bit off. The ISR (`sfx_step`) clears it every unheld frame (taken: >= the playing effect's priority, else dropped) and every held frame (`ay_play` `.hold`). Boot 0 |
| `$BFF4` | `SFX_XP` | **3E-T0**: the signed pitch offset (semitones, two's complement) of the next `SFX_STATUS` take. `sfx_msg` writes it before `sfx_req`; the ISR copies it to `sfx_xp` (AY-slot state, `ay_vars_end - 1`) when it takes `SFX_STATUS` and zeroes it for every other effect. Boot 0 (state block, no init needed: only read on a STATUS take). `$BFF5..$BFFF` spare |
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
| `$6D4C` | `LVL_FLAGS` | `LF_GRATE_OPEN 1`, `LF_KEY_TAKEN 2`, `LF_SEAL_OPEN 4`, `LF_GATE_HINT 8` (B12: the lair's gate hint was logged this level; `lair_hint`, reset by `level_gen` rewriting the byte) |
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
| 10 | `T_TRAP` | **3E (user-approved glyphs, `assets/gfx/concept/grid/items3e.tiles`): the revealed trap plate**, ink `$42` default (per-type ink = T16), `TILE_FLAGS` 0 (walkable, game.md §1.5). The potion moved to id 60 (`T_POTION` = `T_FLASK`). T6 generates the trap list; nothing stamps the plate yet (T16: revealed traps) |
| 11, 14 | `T_DOOR_JAMB_L`, `T_DOOR_JAMB_R` | B10 (user option B): open-door jambs, `$A0` / `$05` × 8, ink `$06`, non-solid (the PROTO chest stand-in is gone, B3B-13) |
| 12 | `T_CHAIN` | small decor; cobweb / moss move to the per-level sets |
| 13, 15, 16, 31 | `T_BONES_0..3` | **DEC1 (user-approved 2026-10-20): the dead-skeleton floor pile**, screen order left to right = ids 13, 15, 16, 31 (`BONES_IDS` / `dg_bids`, not contiguous), ink `$47`, static (`TILE_FLAGS` 0, no `TF_ANIM`); were `T_SKULLS`, `T_TORCH_T/B` (small torch) and `T_CANDLES`, all removed. Glyphs: concept `bones.tiles` via `tools/tiles_convert.py` (`("cell", file, block, k)` source) |
| 17, 18 | `T_AMMO` (= `T_DAGGERS` = `T_ARROWS`) / `T_PAGES` | **3E (game.md §8.11 Q1, user-approved `items3e.tiles`): 17 = the merged AMMO bundle** (daggers AND arrows, one glyph); **18 = PAGES** (scrolls, books). TILE_FLAGS 0 (floor items), not decor for the deriver's ring (`dg_bad` 0). **3E-T6 inks:** at run time `TILE_ATTRS` of 17, 18, 60..63 is **0** (`level_load_tiles`' third `theme_ids` list: ink = paper, blank) and the real ink is painted per cell as `item_ink(type)` by `fl_attr` (see "3E contracts"); the source attrs (`$47` / `$07` / slot bytes) are unused. `ap_stamp` / `build_room_map` store `item_glyph(type)`; `floor_pickup` tests `T_AMMO` / `T_POTION`. (D3-7 T6 history: the B3B-13b drips are no longer placed.) |
| 19, 20 | `T_END_L` = `T_PIT_R`, `T_END_R` = `T_PIT_L` | floor edge right / left of a hole: the pit caps share them |
| 21–25 | `T_DOOR_ARCH_L/R`, `T_DOOR_L/R`, `T_DOOR_LOCK` | concept §3.1 (5 door ids) |
| 26, 27 | `T_GRATE`, `T_RUBBLE` | B12: `T_GRATE` = the **raised** gate (variant B, ink `$46` = `ATTR_GRATE`), `TF_LADDER \| TF_HOLE`, stamped over the lair's open level exit; `T_GRATE_SHUT` = `T_GRATE` until 3F gives the closed gate its own id (TODO 3F, level_defs.asm) |
| 28–30 | `T_WALL_DITHER/PATCH/FADE` | wall set |
| 32..59 | `T_LVL_BASE`.. | per-level decor (bank-7 tileset) |
| 60..63 | `T_LVL_OBJ` | **3E floor-item class glyphs on EVERY depth (slot bytes 28..31 of all 8 tilesets, flags 0)**: 60 `T_FLASK` = `T_POTION` (the old potion glyph bytes), 61 `T_FOOD`, 62 `T_WEAPON`, 63 `T_WORN` (runtime `TILE_ATTRS` 0, inks per cell: 3E-T6, row 17/18 above). `dg_bad` 0 for 60..63 (items, not decor: `is_decor` = 28..59 + chain/bones). **D8:** the lectern + Book are NOT in the D8 slot any more (they were unstamped); the Sanctum swap must supply them (source `LECTERN` in `tools/tiles_convert.py`, ids `TS8_LECTERN_*` still emitted in `tileset_ids.inc`). **3E-T6: NOT built** — no Sanctum room is generated yet (`LVL_SANCTUM` = `ROOM_NONE`), so the swap is deferred to the Sanctum's generation (3F); proposal: the 2×2 lectern glyphs + attrs + flags (40 B) at bank 7 `$FFA0` (tileset tail, 96 B free) via `tools/tiles_convert.py`, swapped into ids 60..63 by a low-RAM hook in `room_show` / `do_exit` when the room is the Sanctum (and back on leaving), ASSERT `T_LVL_OBJ_N == 4` |

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
  PATCH, FADE) `TF_SOLID`, RUBBLE 0, 32..59 0, 60..63 0 (3E floor items; the D8 lectern flags come with T6's swap)
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
`HOT_COPY` image (load image in the bank-6 boot block since 3E-T1, was bank-1 `vdata`), `src/panel2.asm` bank 2;
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
| `$BCAD` | spare | 3 | was `QPIN` (never used; 3E-T3 moved it to `ITEM_RAM`, "3E contracts") |
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
| `$B3F0..$B3FF` | `ST_T2` | STMR2: hi nibble POISON turns, lo WEAK turns |
| `$B400..$B40F` | `ST_X` | spare byte per slot (§6.4 "byte 3") |
| `$B410..$B41F` | `FXQ0` (= `FXQ`) | **D3-5:** FX queue entry 0 (FIFO head; a 16-B descriptor). D3-0's 2 × 8 B could not hold a 16-B descriptor |
| `$B4E0..$B4FD` | `RANK_ROWS` | the hero's current-rank rows, `RANK_N` 5 × `RR_STRIDE` 6 B (`RR_MP`, `RR_RANGE`, `RR_DIE`, `RR_BONUS`, `RR_BOUNCE`, `RR_EFFECT`), row k = ability k (ARANK bits 2k..2k+1); copied from the bank-3 rank table on learn / rank-up (D3-9b) |
| `$B4FE` / `$B4FF` | `FX_BUSY` / `FXQ_N` | **D3-5:** bit i = FX track i live or still drawn (0 = FX idle: `turn_done` waits for it) / queued descriptors 0..2 |
| `$B500..$B51F` | `FXT2` | **D3-5:** FX track 2 (32 B). No FONT6 hole is free any more |
| `$BC4A..$BC50` | `TURN_PEND` block (D3-7) | `TURN_PEND` +0 (bit 0 `TP_ACT` ability logic pending, bit 1 `TP_MON` monster phase pending, bit 2 `TP_FIRE` this is the fire tick), `ACT_ABL` +1 (`ABL_*` pending), `ACT_AT` +2 (`TURN_TICK` of the release, fire tick f = `ACT_FIRE_TICK` 2), `MON_AT` +3 (≠ 0: monster phase deferred, its earliest `TURN_TICK` f + 1; it runs once the hero's FX is idle, designer 2026-10-12), `FX_DROP` +4 (T1: descriptors `fx_start` dropped, mod 256; tests assert 0), **T7:** `LOG_TURN` +5 (log drain: bit 0 `LT_SERVED` = `item_log` drew a line since the turn started, bit 1 `LT_HOLD` = `end_turn` holds the next turn), `LOG_PDIR` +6 (T7 review: the input a hold swallowed — `PLAYER_DIR` bits 0-3, bit 7 = `DK_WAIT` — replayed when the key was released during the hold; "Log drain (T7)" under "Projectiles"). Zeroed by `level_reset_new` (`HERO3D..TURN_PEND_END`). Contract under "Projectiles" |
| `$BC41..$BC49` | `HERO3D` | `MP_RG` +0 (MP regen counter), `HERO_RES` +1 (3 B, RES format), `HERO_IMM` +4 (`IMMF_*`; ASSERT = `HERO_RES + KX_IMM`: deal_hit reads hero and kx row alike), `MP_SH` +5 (panel MP as drawn), `STAT_SH` +6 (status icons as drawn), **D3-6a:** `HERO_DEF` +7 (hero DEF: Warrior 1 Leather / Mage 0, set by `hero_st_init`; gear in 3E), `XP_UP` +8 (1 = `deal_hit` added XP; **D3-9b:** `xp_turn` (end_turn) checks the level-up and clears it), `MP_RG` counts turns to the next +1 MP (frozen while WEAK), `MP_SH` is polled by `icon_poll` (PD_MP → `item_mp`); `$BC4A..$BC50` = `TURN_PEND` (row above); **D3-8:** `HST_DONE` `$BC51` (1 = the hero's status step already ran for the turn being entered), `HELD_T` `$BC52` (held-hero INPUT-tick counter); **D3-8e2: `COMBAT_NOT_BEFORE` `$BC53`** (the §6.5.1 panel gate, "Cast-time output gate" under "Projectiles"); **3E-T2: `PAGE_OPEN` `$BC54`, `PAGE_N` `$BC55`** (the bag page, not zeroed per level); `$BC56..$BC5E` free. `level_reset_new` zeroes `HERO3D..ST_HERO_END` |

`ST_*` arrays: byte = array + slot (`P_MAX_ENT` 16); `ST_FLAGS` / `ST_T1` /
`ST_T2` share page `$B3` (ASSERT). **HERO_CARRY:** slot 0 carries over a
descend; `level_reset` clears slots 1..15 of all four arrays (~1.4k T, once
per level); `level_reset_new` (new_game) also clears slot 0 and `HERO3D`.
`RANK_ROWS` rows are written by `rank_sync` (bank 3) on a learn / rank-up (`abil_learn`, D3-9b) and by `debug_kit`; rows of unlearned abilities are garbage and never read. The FX state is
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
ASSERT one page), `K_MAX` 32 rows × `KX_STRIDE` 6 B = `KX_LEN` 192 B: `KX_RES`
+0 (3 B), `KX_IMM` +3, `KX_XP` +4 (KXP, game.md §4.1), `KX_DEF` +5 (0 in 3D,
§11.4). Row = `kx_tab + kind * 6` (`ld h, kx_tab >> 8`, L = kind × 6). Read
by bank-3 combat code only. Reserved as zeros (`DS`); data rows in D3-1.
**L-RELIEF:** `dg_bad` (decor_gen.asm's 64-B, 64-aligned `dg_ring` lookup,
generated by `tools/decorgen.py --asm-bad` → `src/dg_bad3.asm`) sits right
after it at `$C0C0` (= `$C000` + `KX_LEN`: aligned by construction, ASSERTed
in `combat_data3.asm`; the other D3-1 tables follow at `$C100`; D3-9b: `xpn_tab` moved to bank 2, `lvlup_tab` / `lvl_step_tab` deleted).
It was an `ALIGN 64` in `decor_gen.asm` whose 0..63 B pad moved with every
byte of bank-3 code before it.

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
D3-8 added the BOSS rules and WEAK's penalties ("Status effects (D3-8)"
below). Bank 3: 1,589 B free after D3-6a (was 2,324;
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
  A = `ABL_*`, DE = the rank row: `spell_row` for spells, `ABIL_RK` for the
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

**Status effects (D3-8)** (game.md §6.4, §2.2, §2.3, §9.1). State = the
`ST_FLAGS` / `ST_T1` / `ST_T2` arrays only (the R3 homes above; invariant: a
group bit / kind set ⇔ its timer nibble ≠ 0); the tint and the panel icons
are derived from them, never stored. `ST_X` stays unused (spare).
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
  "no MP regen": D3-9b `xp_turn` freezes `MP_RG` while slot 0 is WEAK; the hunger WEAK (3E) must
  share these tests (not cumulative) and gate the regen too.
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
| `$5D4B` | `QPIN` | 3 | game (pinned type per quick slot `QS_FOOD` / `QS_POTION` / `QS_SCROLL`; moved from `HERO_ST` +29, never used there) |
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
bits 0–4 col, 5–6 type (`TT_DART` 0, `TT_GAS` 1, `TT_TELEPORT` 2, `TT_ALARM` 3).
Written by the 3E-T6 generator after `level_gen` (`tools/items_model.py`
`gen_traps` / `apply_block`; `tools/levelgen.py`'s 320-B block keeps them 0).

**3E-T6 generator + floor inks (built; reworked for the 3E simplification).**
`src/items_ovl.asm`, an overlay at `ITEMS_ORG` = `GEN_SCRATCH` (1,027 B raw +
53 B scratch past the image, ASSERT `ig_end` ≤ the window), ZX0 stream
`ovl_items_zx0` **881 B in `BANK_OVL_ITEMS` = bank 1** (defs.asm; any bank
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
nothing may read a bit as "potion i".

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

**`E_POT` migration (today's potion count → `BAG`; do NOT migrate before
T10/T11).** Every reader / writer of `E_POT` (`P_ENTITIES + E_POT`, hero slot 0):

| Site | Role | Switches in |
|---|---|---|
| `boot7.asm` `new_game` (`ld (ix+E_POT), 1`) | start kit: 1 potion | T11: start kit → `bag_add` (Heal ×1 + gear in `WORN`); `KNOWN` bit Heal (+ Mana for the Mage) |
| `bank3.asm` `level_populate` (carry `E_POT` over `level_reset`) | descent carry | T11: delete the carry (the bag is outside the entity table) |
| `pickup7.asm` `floor_pickup` / `pp_take` (`IT_POTION` → `E_POT` + 1, `MAX_POTIONS`, `POTIONS_TAKEN`) | pickup | T11: `IT_BAG_LO..` → `bag_add` (T10) with ISTATE 0, `BAG FULL.`; ammo / key stay counters |
| `intent7.asm` `ic_potion` / `ic_quaff` (the old `try_quaff`) | quick-slot drink | T11: `QS_CACHE[QS_POTION]` → the potion effect (T12), decrement the bag stack |
| `icons.asm` `icon_poll` (`E_POT` vs `PANEL_POT_SH`), `icons3.asm` `icon_state` `.pot` / `item_icons` (`pot_slot` redraw), `panel.asm` `slot_redraw` (count digit) | icon / count | T11: read the quick-slot stack count (`qs_pick`, T10) instead of `E_POT`; `PANEL_POT_SH` keeps its role |
| `boot7.asm` `panel_init7` (`PANEL_POT_SH` = $FF; `pot_slot` scan) | panel reset | unchanged (shadow semantics kept) |
| `info1.asm` `item_info` (potion count on the info line) | info line | T11 (with `item_name`, T10) |
| `intent7.asm` `debug_kit` (DEBUG_KIT: `HAS_BOW`, `ARROWS`, `DAGGERS`; no `E_POT`) | kit | T11: `HAS_BOW` → `IT_BOW` in the bag; then `HAS_BOW` (`HERO_ST` +28) retires with every reader |

Order: T10 lands the bank-1 helpers (`bag_add`, `item_name`, `qs_pick`,
`id_learn`) reading `BAG` with no caller; T11 switches the writers first
(`new_game` start kit, `pp_take`, `level_populate` carry) and the readers
(`ic_potion`/`ic_quaff`, icon_poll / icon_state / item_icons / slot_redraw,
`item_info`) in one change, then deletes `E_POT` (entity byte 8 freed),
`MAX_POTIONS`, `POTIONS_TAKEN` and `IT_POTION`. Goldens showing the potion
count move then, not before.
