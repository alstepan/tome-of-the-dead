# Code-size survey (z80-architect, read-only, 2026-11-15, main 86c607b)

User-approved 2026-11-13, to run after NEW-MON3. Project rule: no feature cuts; space comes from reclaim.

**Where the numbers come from.** Per-file sizes come from the NEW-MON3 T9-era listing (FRT 153). Each file was measured as its close address minus its open address. Ledger changes since then: bank 3 −19, bank 7 −22, R6 −1,149 (ROOM-MEM2 and T10a/b). Low RAM gained ~190 when the sequence loader moved out, offset by `seq2_bytes` +112 and fdesc +50.

Free bytes today (memory-map):

| Bank | Free (B) |
|---|---|
| bank 3 | 60 |
| R6 | 91 |
| bank 2 | 10 |
| bank 7 | 52 |
| bank 1 | 7 |
| low RAM | 72 |
| B0_CODE2 | 3,041 |

## 1. Size by subsystem

Heat key: H = per frame/tick, T = per turn, R = per room entry, L = per level, B = boot/screen.

| # | Subsystem | Bank: files (bytes) | Total | Heat |
|---|---|---|---|---|
| 1 | Packed sprite sources | b1 9,056 · SRC6 3,565 · B0 SRC0 1,879 | 14,500 | L |
| 2 | Render core | b2: anim 1,820, gfx 1,357, logic 1,163, fx 898, io 747, mark 484, decor 279, dnum2 207, drip 194, mirror2 159 | 7,300 | H |
| 3 | AY slot | b3 top: player 1,106, songs 1,794, sfx 862, ay_play 248 | 4,023 | H (ISR) |
| 4 | Player turn | b7: core 2,104, abil_* 866, intent7 492, pickup7 405, act7 335 | 4,200 | T |
| 5 | Icons/panel/UX | R6 icons6 651 + icons16 1,013; b3 icons3 433, panel 339; b2 icons 352, panel2 138; B0 ux0 544, bars0 131 | 3,600 | T/UI |
| 6 | Combat + projectiles | b3: proj3 1,455, combat3 1,385, dnum3 338, rank3 257 | 3,435 | T |
| 7 | Menu / select / end card | b1: menu1 2,430, menu_font 656, title 278 | 3,364 | B |
| 8 | Low-RAM helpers | generator+alloc+zx0 ~1,000 (L), climb/jump/fall ~610 (T), room draw ~340 (R), messages ~310 (T), boot/loader 221 (B) | 3,300 | mixed |
| 9 | Text | B0 2,766 packed + log0 212, logsc0 209 | 3,190 | T |
| 10 | Items/gear | R6 fx6 1,084, gear6 1,069, pickup6 544, fi6 329, bag6 202; b1 items_tab 620, itemname1 ~206 | 4,050 | event/UI |
| 11 | Spawns / tiers | R6: spawn6 804, tier6 580, pool6 455, trickle6 308, vbat6 270 | 2,420 | L/T |
| 12 | Status/traps/hunger/XP | b7: trap7 576, mark7 503, status7 486, xp7 344, hunger7 284, drip7 309; B0 hunger0 130 | 2,630 | T |
| 13 | Level generator | b3 levelgen 2,185 + level_reset..populate 688 | 2,873 | L |
| 14 | Room entry / LP | b3: lpop3 1,246, decor_gen 1,189, build_room_map 644 (+ dg_bad 64) | 3,143 | R |
| 15 | Monster AI | b3 turn3 1,199, lq3 116; R6 ranged6 811, arch6 498; b7 seek7 84, boss7 288 | 3,000 | T |
| 16 | Frame descriptors `fdesc_tab` | low RAM 815 (163×5); read only by `gen_frame` | 815 | L |
| — | Boot-only / D0-only | boot6 1,967, BOOT4 5,850, TUT blob 7,718 raw (bank 4) | — | B |

## 2. Levers, ranked

1. **F1: move `fdesc_tab` to B0_CODE2.**
   - Gain: low RAM +~800 (B0 −815). Effort S, risk L.
   - Cycles: ~+80 T per generated frame (~3k T per level start); 0 on every cap.
2. **F2: move the decor deriver (`decor_gen` + `dg_bad`, plus a copy of `rnd_mod`) to B0_CODE2.**
   - Gain: bank 3 +~1,230 (B0 −~1,260). Effort M, risk M.
   - Cycles: one FARB0 per room entry, offset by running from uncontended bank 0. Re-run the budget gate.
3. **G: grow the tutorial blob down toward the D0 pool top** (pool top $D460, BLOB_ORG $E1B2).
   - Gain: up to +3.3 KB raw in bank 4; needs in-place ZX0. Effort M, risk M.
   - Cycles: boot +~70k T once; tape +~2.5 KB.
4. **H (reserve): move POOL_START up in 256-B steps.**
   - Gain: +256…1,024 B in B0. Each step costs the binding pool slack (D8 Warrior 2,320). Effort S.
5. **E: font trim.**
   - `menu_font` rows 0, 1 and 15 are blank in all 41 glyphs: bank 1 +120.
   - FONT6 lowercase holes: up to 256 B in bank 2, but only as 32-B holes.
6. **C: re-roll the `scroll1` unrolls.**
   - Gain: bank 1 +~270.
   - Cost: room transitions get visibly slower (+0.1–0.2 s). User call.
7. **A: ZX0 overlays** (ratio 0.85).
   - levelgen: ~310 B net more than a plain move to B0, at +~35k T per level.
   - menu1: ~750 B in bank 1, but needs splitting.
   - Effort L. Use only if B0 runs out.
8. **D: table packing.**
   - Estimate 50–150 B. The `items_fx_stems` route is blocked by text headroom (17 B).
9. **B: dedupe helpers** (`hla`/`rnd_mod` copies, 4 print variants, 2 msg composers, `ldir2` included twice).
   - Estimate 50–150 B; only pays in an always-visible bank. Measure first (T1).

## 3. Which bank each lever frees vs what the features need

- **LARGER-D:** low RAM +90–125 B (F1); bank 3 +40–80 B (F2); B0 ~20.
- **DECOR2:**
  - P1 is self-funded.
  - P2 needs ~300 B in B0 plus a ≥300 B bank-3 reclaim. F2 frees that and puts the deriver next to the planner.
- **Tutorial v2:** bank-4 blob space (38 B free). Only G helps.
- **B0 budget:**

  | After | B0 free (B) |
  |---|---|
  | F1 + F2 | ≈ 966 |
  | DECOR2 P2 | ≈ 640 |

  H is the fallback.

## 4. Task cards (recommended order: T1 ∥ T2 ∥ T4, then T3; T5 waits for the Tutorial v2 spec)

- **T1 [junior] `tools/size_report.py`:** per-bank/per-file sizes plus a cross-bank duplicate-run scan (runs ≥ 12 B).
  - Acceptance: bank-3 sizes match the build DISPLAY ±0.
- **T2 [staff, sonnet ok] F1:** `fdesc_tab` → B0_CODE2. `gen_frame` fetches the descriptor with BANK_TEXT paged; the `{b fdesc_tab+…}` macros need bank 0 mapped or a mirror table.
  - Acceptance: zx0_pool, gfx_integrity, tut0, game, budget; LOWRAM_SPARE ≥ 850.
- **T3 [staff] F2:** the decor deriver → B0_CODE2 via FARB0 from `build_room_map`.
  - Acceptance: world W13/W14, decor goldens byte-identical, A2 ≤ 22,000, roommem ADV ≤ 70,000, tut0 worst ≤ cap, bank 3 free ≥ 1,250.
- **T4 [staff, sonnet ok] E:** 13-row `menu_font` glyphs.
  - Acceptance: menu/select goldens identical; bank 1 +~120.
- **T5 [staff] G:** blob grow-down, once the Tutorial v2 size is known.
  - Acceptance: tut0 suites; keep ≥ 256 B between the D0 pool top and BLOB_ORG.

Deferred: C (user call on scroll speed), A (only if B0 runs out), B/D (after T1 data), H (reserve).

**Spec gaps:**
1. DECOR2's plan buffer at $6DF0..$6DFF collides with LARGER-D's ROOM_DESC page ($6D40..$6DFF). T2 frees low RAM to move it.
2. decor_rules2 §3 bank placement needs re-deciding if T3 lands.
3. The Tutorial v2 blob byte estimate is missing.
4. C changes transition speed.
5. No policy yet on spending pool slack (H vs future art).
6. larger_depths.md §5 still quotes B0_FREE 11,958; it is now 3,041.
