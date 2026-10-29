# MEM-RECLAIM audit (2026-10-29, read-only; measured on 86ff3ff = main 557819a, release `-DDEBUG_KIT=0`)

Method (scripts in the session scratchpad, repo untouched): SLD `+used` flags for unreferenced labels; a Python
replica of main.asm "LEVEL POOL NEED" (it reproduces the `-DPOOL_LVL_VERBOSE=1` figures exactly, 16/16 hero x depth);
`zx0_sources.partition` re-run with frames removed (packed bytes); ≥10 B duplicate-run search over all 8 banks of the .sna;
mirror/blank-band scan of every frame grid. **M** = measured, **E** = estimated. The binding case is the **Warrior**: Knight need 32224 (D3 13504), Mage 28032. The Mage has 4.2 KB headroom, so every Knight-only byte comes 1:1 off POOL_NEED.
Second-worst level: **D4 12736 after any D3 fix** (Orc, Rat, Spider, Archer + Ogre). D3 alone can free at most 768.
## 1. TOP ITEM: shared corpse ("ashes"), user idea 2026-10-29 (M)
Corpse frames today: skeleton_collapsed 576 B pool (24x48, 32 blank rows), goblin_dead 320, ghost_dead 384, bat_dead 192,
slime_dead 96, dead_humanoid 320 (Orc/Archer/Mummy/Necro/Vampire/Ogre/DK/Archmage + tiers), small_corpse 128 SYM (Rat/Spider/
Giant Rat/Brood Rat), knight_dead 320, wizard_dead 320. A DEAD pose shows for 12 ticks (DEATHSEQ HURT 3 -> DEAD 12).
Ashes = 32x16 SYM = 128 B. Cheapest form: **reuse small_corpse (U_DEADR) as the ashes**. No new art, no new fid, and 0 extra on Rat/Spider levels.

| variant (A0/C0/B0 = small_corpse is the ashes) | pool saved W=M D1..D8 | POOL_NEED (slack, was 1476) | fids freed | packed freed |
|---|---|---|---|---|
| A0 all monsters | 608 512 **1344** 320 896 576 576 1152 | 31456 (2244, +768; D4 binds) | 6 | bank1 314, SRC6 76 |
| A0 + hero corpses (knight/wizard_dead) | same + hero 320 | **31136 (2564, +1088)** | 8 | + bank1 159 |
| A new 32x16 SYM ashes frame (not small_corpse) | 608 512 1344 320 896 576 576 1152 | 31456 (+768) | 6 (7 out, 1 in) | bank1 314+62, SRC6 76 − ~70 new |
| C0 keep Skeleton bones / Goblin / small_corpse | 288 192 768 320 320 576 576 576 | 31456 (+768) | 4 | bank1 181, SRC6 76 |
| B0 humanoid only (dead_humanoid -> small_corpse) | 0 0 192 320 320 192 192 192 | 32032 (+192) | 1 | SRC6 76 |

Each freed fid is one spare FRT slot (FRT_MAX 132 is full; a 133rd fid costs 16 B FRT + 5 B fdesc low RAM + 4 B frame_tab).
Sequences: **0 B** (DEATHSEQ keeps its shape). D3 is freed first by A0 (−1344); C0 gives the same POOL_NEED because D4 binds. **Recommendation: C0 + the skeleton trim (§3 #1):** it keeps the bone pile, goblin and rat/spider corpses and gives the same +768 as A0 (+1088 with hero corpses). Downside: the Ghost dissolve,
Bat, Slime puddle and humanoid body all become one heap. Hero corpse: it stays on screen until ENTER, so it is the most visible
loss and needs a user call. Guards: tests/frames_phase.py, zx0_pool.py, gfx_integrity.py, game.py/world.py (death paths), combat_tables (FIDS).

## 2. Unreferenced code / data (M: SLD `+used` + grep src/tests/tools)
- **Dead strings (bank 0, under the pool: 1:1 pool slack)**: 34 ids, **≈329 B** (stream + 2-B pointer, before re-tokenising):
  bang, bk_read*, bk_grasp, bk_crumbles, bk_destroyed, cmb_throw/shoot/power/whirl/range, end_killed, m_title, none_left,
  paused, rk_ii/iii, xp_lv/xp/level, spl_c_* (5), spl_spark..light (5), spl_burn_self/hit_self/bounce/reflect/reflect_m.
  *strings.txt bk_read is dead. The live one is items.txt bk_read (tests/itemtab.py). The TX_INFO_*2/3 and TX_AB_* entries look
  unused but are reached by arithmetic (info1.asm:56, xp7.asm:231): **keep**. The spl_reflect/bounce/self group (60 B) is held until T11 (Archmage reflect lines). Guard: world.py W17 (all strings decode), textpack round-trip.
- `frame_footprint` (gfx.asm:1025) **49 B bank 2**: no caller, no test. Safe. Release has no DEBUG_KIT code (IF-guarded).
- Not dead (fall-through / test probe / base + n): tpt_intent, fx_qpop, tr_erase, hg_weak_line, tick_work, select_tick, probe_*, icon/tileset sub-labels.
- **PROTO fixture** ≈ 190 B bank 3 (proto_level/hdr/floor/rooms/spawn) + 35 B R6
  (pool_proto). 24 test files poke `proto_start` in the release image: **do not touch** unless the tests move to a PROTO build.
- Reserved SFX ids BOSS_ROAR/BOSS_DEATH/SPARE3F have no data yet (0 B). xp thresholds are already one table (D3-9b; combat_tables pins it).

## 3. Duplicates / trims / compressible (M unless marked E)
1. **skeleton_collapsed trim 48->16 rows** (top 32 rows blank, bottom-anchored, pixel-identical): −384 pool on D3/D5/D8, **POOL_NEED −384**. Subsumed by A0.
2. **knight_windup trim 5->4 cols** (right column blank): Knight −192 B pool = **POOL_NEED −192** (binding hero). Check the offsets (FT_OFFL ≤ 16 ASSERT).
3. **Tilesets, bank 7**: 8 slots x 32 glyphs = 256 glyphs, only **74 unique** (2048 B -> 592 B pool + 8 x 32 B index).
   **≈ −1.2 KB bank 7** (E net of ~20 B gather loop in level_load_tiles, 11.7k T -> ~+5k T once a level). TILE_FLAGS: 4 distinct of 8 (−128 B more, E).
   Changes tools/tiles_convert.py + the TSET split. Guard: world.py W11, gfx_integrity (B7 region), goldens.
4. **icons16 1376 B raw in R6**: ZX0 whole 901 (−475), groups of 8 icons 1025 (−351, 256-B decode buffer). Readers: icons6 ic_blit, fi6 -> FI_GLY.
   **E ≈ −300..−450 R6** net of the decode path. Medium risk (qs_draw during play needs a buffer). Guard: page/ic1 goldens.
5. **Text tables**: tx_tab 207 x 2 = 414 B -> a pointer every 8th string + a ≤7-string 0-byte skip: **E −360 B pool** (+≤2k T per message).
   Dict pointers 76 x 2 -> 1-B offsets (dict 254 B < 256): **−76 B pool** (M). Guard: world.py W17, log goldens.
6. **Song instruments** inst_hps13/hpsaw are copied into all 6 songs: ≈ **−100 B AY slot** (abc2wzm shared instruments). Guard: snd tests.
7. **AY slot slack 169 B** (ay_code_end $FF57): raise AY_RESERVE by up to 169 (+100 with #6) -> **bank-3 cold 48 -> ≤ 317 B**.
   Trade-off: this spends the reserve meant for the 3 boss SFX (≈ 20-40 B each, E). Guard: sound.py, snd*.py, gfx_integrity.
8. **KT_REACH column is all 1** (32 B, kind_tab page 0 $0E0, 2 readers: bank7:788, turn3:530 -> `ld a,1`). The freed slot fits
   `rk_tab` (30 B, same-page ASSERT) -> **bank 2 −30 B** (the "free to FRT" figure). Confirm T11 needs no reach > 1. Guard: combat_tables kind_tab rows.
9. **lp_wt (bank 3) / lp_wt6 (R6)**, 30 B each (LP_WT_ROWS): one copy in bank 2/low RAM -> bank 3 −30, R6 −30, bank 2 +30 (E).
10. **xorshift core x4** (rng_next b2, lg_step + dg_rnd b3, gen_step b6; 13 B identical): `HL -> HL` core in bank 2 -> **bank 3 ≈ −18, R6 ≈ −9** (E).
11. Small duplicates found by the run search (E, ≤ 15 B each, low value): get_box(b2) / climb_blocked.mv(lowram) 20 B;
    cell_addr / fi_cells.r 15 B; do_attack / melee_hit.h 26 B (bank 3); do_exit.nl / place_follower 20 B (bank 7). **Do not touch** erase_rect's 34-B twin (deliberate DUP-7 unroll, hot path).
12. Pads ≥ 8 B (M): kind_tab ALIGN pad 35 B (bank 2, already counted free: it can hold rk_tab), FRT_GAP 73 B free (runtime),
    kx_tab zero rows 24 B (id 2 + FX ids; pinned by combat_tables "kx 256"), rk_tab 12-B zero prefix, KT_SEQ/tile DS = runtime.

## 4. Pool side (M)
- **SYM candidates: 0** (no unflagged frame is symmetric about its body axis, even within 6 px); identical frames 0/144; icons 0 duplicates.
- MOT frames (both shifts): knight/wizard_jump2 1344 each, ghost_float2 896, rat_run1 576, bat x3 448, slime_squash 448.
  All are pinned by frames_phase.py (drawn at both parities). **E −768 Knight**: if the jump tween alternated JUMP1 (px&4=0) with
  JUMP2 (WK4), POOL_NEED would drop 768. That is a design/visual call.
- **HURT -> $42 flash** (the 3F rule) for the 6 old kinds: per level 1024 832 1152 256 576 384 384 960 -> POOL_NEED −704. Plus knight/wizard_hurt
  (768 each, Knight binding) -> −1472 together. A design call (the old kinds lose their hurt poses).
- Units never drawn on a level: none found (gu_tab/pool_gmap load only what the seqs reach).

## 5. Tightest level (D3 13504 W/M)
D3 = Skeleton, Vampire, Ghost, Bat + Vampire boss. In order: skeleton trim −384 (pixel-identical) -> C0/A0 corpses −768/−1344
-> hurt flash −1152. POOL_NEED stops at D4 12736 (−768) unless the Knight levers are used too (windup −192, corpse −320, jump2 −768, hurt −768).

## Top 10 by bytes per risk
| # | item | saves | risk | owner |
|---|---|---|---|---|
| 1 | skeleton_collapsed trim | pool −384 (NEED) + ~bank1 | very low, art-identical | junior (Sonnet) |
| 2 | dead strings (excluding the T11 spl group) | pool +269 | low | junior (haiku ok) |
| 3 | frame_footprint | bank 2 −49 | very low | junior (Sonnet) |
| 4 | knight_windup col trim | NEED −192 | low | junior + reviewer |
| 5 | corpse C0 (+hero corpses on user OK) | NEED −768 (−1088), 4-6 fids, bank1 181-340, SRC6 76 | low-med (visual) | staff (Sonnet) + artist none |
| 6 | dict 1-B offsets | pool −76 | low | junior (Sonnet, textpack + tk_get) |
| 7 | song instrument share + AY_RESERVE raise | bank 3 +169..+269 | low-med (SFX reserve) | staff (Sonnet) |
| 8 | tileset glyph dedup | bank 7 −1.2 KB | medium (loader + tool + layout) | staff (Opus) |
| 9 | KT_REACH -> rk_tab slot, lp_wt single copy, xorshift core | bank2 −30, b3 −48, R6 −39 | low-med | junior (Sonnet) |
| 10 | icons16 ZX0 groups / sparse tx_tab | R6 −300..450 / pool −360 | medium (decode paths, CPU) | staff (Opus) |

Split: wave 1 juniors in parallel (#1, #2+#6, #3, #4: disjoint files). Staff (Sonnet) does #5 after the user picks C0 vs A0 (and hero corpses) and #7. Staff (Opus) does #8 and #10 (layout/paging). Reviewer: Sonnet for wave 1, Opus for #8/#10.
**R6 is the real shortfall** (T9+T11+T12 ≈ 1.3 KB + Archmage 345 B). Direct R6 items give only ≈ 340-490 B (#9/#10); the rest must come from pool slack
converted by R6_GROW (as T8 does): wave 1 + #5 frees ≈ +1.1..1.6 KB of slack for that.
