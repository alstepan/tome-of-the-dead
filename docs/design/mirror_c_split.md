# Option C: mirror at blit time — feasibility + split (architect, 2026-11-09)

Status: APPROVED to start AFTER the TUT0 merge (user 2026-11-09: "new monsters approved after C is done"; manager recommendations taken for §8: 1 amend the stack-blit rule, 2 drop ISR_ROM_CHAIN=1, 3 HYBRID, 4 freed pages → bank 0 via POOL_START, 5 ≈ 1 KB slack, 6 IXL/IXH allowed). Then docs/design/new_monsters.md (Gargoyle, Fire Imp, Frost Wraith).

**Verdict: go-with-conditions, as a HYBRID.** Full C (every left frame mirrored) is a no-go on today's
tick margins. Hybrid: keep hot frames (walk WK4/WK0, MOT, hurt) pre-mirrored, mirror the cold STA set.

## 1. Memory
- **Parity: 0 B extra.** Right/left POOLACC terms (defs.asm:1097/1099) differ only in the anchor
  (`nm_ax` vs `nm_w-nm_ax-bwpx`); every `_w` is a multiple of 8, every `bwpx` ∈ {8,24,32}, `ax` ∈ {0,4,8}
  (FRM_OK, defs.asm:1069) → the left shift always equals the right shift (STA/WK4/WK0).
- **Byte identity:** rowrev+bitrev of a shift-4 right variant over cols+1 bytes == the shift-4 variant of
  the mirrored source (gen_variant lowram.asm:2560-2619, `$FF` mask / 0 data feed, spill `(m<<4)|$0F`;
  mirror_src lowram.asm:2628) → screen footprint, FT_OFFL anchors, damage rects unchanged; goldens must
  NOT change (a diff = a bug). FF_SYM frames already reuse the right variant (lowram.asm:2441-2455).
  PERF-GHOST even-address rule is irrelevant to `pop`.
- **Binding level D8 Warrior:** need 31,328 of POOL_CAP 31,712, slack 384 (tests/zx0_pool.py:133); SYM
  frames ≈ 1.7 KB; margin/straddle ≈ 0.25 KB.
  - Full C ≈ (31,328 − 1,950)/2 ≈ **14.7 KB**.
  - Hybrid ≈ **5.3 KB** (≈ 6.6 KB if hurt is mirrored too). Hand estimates; T1 measures.
- **FRT encoding:** a mirrored left entry = the right entry with bank byte bit 7 set; FRT_NONE ($FF)
  tested first. ec_port (menu1.asm:1266) and sel_frt_copy unaffected.

## 2. ISR (boot6.asm:219-276)
Today the ISR pushes onto the interrupted stack — inside a pop blit that is the pool.
1. Entry: `ld (isr_rs+1),sp / ld sp,ISR_STK` (+30 T) before any push.
2. After the pushes, before `ld bc,PORT_7FFD` / paging bank 3:
   `ld hl,(isr_rs+1) / ld e,(hl) / ld (hl),c / inc hl / ld d,(hl) / ld (hl),b / ld (isr_jp+1),de` (+70 T)
   — writes BC back over the word the CPU's interrupt push overwrote.
3. Exit: `isr_rs: ld sp,0 / inc sp / inc sp / ei / isr_jp: jp 0` (+22 T over `ei/ret`), flags untouched.
- Cost **+122 T/ISR, ≈ +26 B**. ISR 49 → 75 B vs the 68-B window $BCBC..$BCFF → relocate or jump out.
  Worst single ISR 6,243 → ≈ 6,365 T (contract 6.5k). Real gate PRE_MAX +122; up to 2 ISRs/tick ≈ +244 T.
- **Write-back unconditional** (no flag): outside a blit the word below SP is free stack; nothing keeps
  data below SP (only `ld sp` sites: levelgen LG_SP, bank7 .quit, boot).
- ISR stack 18 B (26 with ISR_SAVE_ALT) at the bottom of the main stack ($BE00..): 0 B new; staff
  measures main-stack depth.
- **ISR_ROM_CHAIN=1 unsupported** (ROM $0038 pushes on the current stack) → ASSERT. The tape path (ROM
  IM1) runs before `isr_install` and never blits. NMI: no handler; a hardware NMI during a blit corrupts
  the pool — accepted.
- **Invariant "word below SP == BC" at every instruction boundary:** preload BC from frame start−2
  (≈ 30 T) before the SP switch; a frame at $C000 reads $BFFE (DH_EFF scratch, defs.asm:533) — safe only
  because the ISR write-back runs first. Line code uses A, D, E, IX only, never BC. After SP is restored
  the word below SP is free stack.

## 3. Other paths
- Single chokepoint: every pool draw goes through blit_sprite (anim.asm:1118, fx.asm:528, menu1.asm:508,
  blit_keep gfx.asm:86 → ec_port).
- page_bank / scr_addr_py / blit_clip_pop / blit_miss all run before the SP switch (gfx.asm:887-915); no
  call/push after it.
- Not pool users: shadow_rect, present, erase_rect; icons6 has its own rev8.
- Main code never uses EXX (conventions.md:247); the mirror chain must not either (swaps BC).

## 4. Tick budget
| Chain | T/byte | T/line (aligned) | setup |
|---|---|---|---|
| Today | 42 | 21 | — |
| Normal pop `pop bc/ld a,(de)/and c/or b/ld (de),a/inc e` | 36 | 22 (L = line start, H = counter) | +~70 |
| Mirror | 50 | 30 (`ld e,ixl / dec ixh / jp nz`) | +~120 |
Mirror excludes contention on BITREV_TAB $6800 (bank 5, contended): worst 2 contended reads/byte in display.

| Sprite | Normal pop | Mirror |
|---|---|---|
| 24×48 shifted (192 B) | −1.0k | +2.1k |
| 40×48 slash | −1.6k | +2.9k |
| 24×32 | −0.67k | +1.4k |
| bat | −0.3k | +0.8k |
| rat | −0.4k | +0.9k |
Margins today: blair real 138,871 (2,945 left); wroom 126,696 work / 135,511 real; mage 119,232; dnum ~121k;
lqmix 120,638; walarm 114,308; wcast4 112,793.
- Full C: blair ≈ +3.5k → FAILS; all-left 4–5-body ticks in wroom/dnum/lqmix at risk.
- Hybrid: walk ticks stay on normal pop → blair −3.0k + 0.24k ISR ≈ **−2.7k (better)**.
- Hybrid risk: several bodies in mirrored attack frames in one tick (pmix/mage/lqmix) — T1 policy +
  budget.py decide the hot set.

## 5. Where the freed pool goes
- NOT R6: SRC6_ADDR = $10000 − 42×256 − 14×256 = $C800, exactly at the boot-block ASSERT (defs.asm:68).
- (a) bank 0 by raising POOL_START (more B0_CODE_RES/text, cold code via FARB0; watch 0→4 straddle);
  (b) a new permanent region at the top of bank 4 — CONFLICTS with the TUT0 blob (BLOB_ORG $E800);
  (c) more SRC6 — blocked (needs bank 6).
- Hybrid ≈ 20 pages; keep ≈ 1 KB slack.
- TUT0: C shrinks the D0 pool (helps the blob gap). Both edit tests/zx0_pool.py LEVEL_NEED,
  memory-map.md, alloc layout → serial merge, the second rebaselines.

## 6. Tasks
- **T1 [junior] Pool-mirror ledger tool** — tools/pool_mirror.py: per level/hero right/left/SYM bytes by
  class (walk, MOT, hurt, other STA) + what-if policies; ASSERT `_w%8==0`, `bwpx%8==0`, `ax∈{0,4,8}`.
  Accept: totals within straddle + 64 of LEVEL_NEED for 16 rows. Deps: none.
- **T2 [junior] Mirror-equivalence test** — tests/mirror_equiv.py: per level pool (zx0_pool Run harness)
  D1..D8 × both heroes + PROTO + boot: rowrev+bitrev(right @ s) == left @ s for every non-SYM fid, over
  ZRCP. Accept: 0 mismatches. Deps: none.
- **T3 [staff] SP-safe ISR** — §2; on exit `(S..S+1) == BC`, SP = S+2, regs preserved, ≤ +130 T;
  ISR_STK measured; ASSERT `!(ISR_ROM_CHAIN && BLIT_POP)`. Owns boot6.asm, defs.asm, conventions.md,
  memory-map.md (+ bank-2 cold code moves). Accept: isr_rate, game #61, sfx/snd, budget all gates, ZRCP
  write-back check. Deps: decisions 1, 2.
- **T4 [staff] Pop-based normal blit** (general + aligned chains) — blit_sprite I/O, clobbers A,BC,DE,HL,
  IX/IY unchanged, SP restored; probes `blit_sp_on`/`blit_sp_off`; 36 T/byte, ≤ 22 T/aligned line; BC
  preloaded from frame start−2; chain entry offset 6 × width. Owns gfx.asm (blit), defs.asm (BLIT_SAVSP),
  memory-map.md. Accept: goldens unchanged, budget all gates (deltas), T5. Deps: T3.
- **T5 [junior] ISR-boundary fuzz** — tests/blit_isr.py: inject an IM2 at every boundary between the
  probes (PC → SP−2, SP −= 2, PC = ISR_ADDR, run to return); compare pool bank, screen, regs vs a clean
  run; all boundaries of a small sprite + sampled 40×48; all chains (`--mirror` after T6). Accept: 0
  mismatches. Deps: T4 labels.
- **T6 [staff] Mirror chains + generator + FF_MIR + bank-2 funding** — bank byte bit 7 = mirror; 8-B
  blocks, H = BITREV page, IX saved/restored in memory; first column = col + w − 1, `dec e`; FF_MIR
  %00001000: left FRT = right | $80, no mirror_src/left generation; POOLACC counts only the right term;
  fund ≈ +100 B bank 2 (raise POOL_START, cold code → b0); BITREV placement measured ($6800 vs one copy
  per pool bank, 768 B). Owns gfx.asm, lowram.asm (gen_frame), defs.asm, data.asm, memory-map.md.
  Accept: goldens unchanged, T2 adapted, T5 --mirror, budget all gates, zx0_pool. Deps: T1, T3, T4, decision 3.
- **T7 [junior] Mark the cold set** STA|MIR in src/frames.asm per T1's policy; move frames back to hot
  until budget passes. Deps: T6.
- **T8 [staff] Carve + layout** — freed pages to the chosen region; new POOL_CAP; ledger. Owns defs.asm,
  data.asm, memory-map.md. Accept: per-level ASSERTs, zx0_pool, ovl, tape_layout. Deps: T7, decision 4.
- **T9 [junior] Rebaselines + doc sync** — tests/zx0_pool.py LEVEL_NEED, gfx_integrity.py,
  docs/design/budget.md. Deps: T8.
- **T10 [junior] Budget scenario "lmix"** — hero facing right, 4 bodies to its right in mirrored attack
  frames at once; ≤ CAP, real ≤ 141,816. Deps: T7.
Order: T1 ∥ T2 → T3 → T4 (T5 in parallel) → T6 → T7 ∥ T10 → T8 → T9.

## 7. Integration risks
1. Bank 2 full (9 B free); T3 + T6 need ≈ 130 B.
2. The ISR write-back must run before the BANK_AY page and the `ld bc`.
3. BC invariant at line fix-ups, setup and SP restore — T5 guards it.
4. BITREV contention may push mirror above 50 T/byte.
5. Merge order with TUT0 (zx0_pool.py, memory-map.md, alloc layout).
6. The CPC fork has a different interrupt scheme → its own write-back.

## 8. Decisions for the user
1. Amend the "no stack blits" rule (conventions.md:276, budget.md:131) under the ISR write-back invariant.
2. Drop ISR_ROM_CHAIN=1 (assemble-only today).
3. Hybrid (≈ 5–6.5 KB) vs full C (≈ 14.7 KB; needs ≈ +6–9k T of perf work first).
4. Where the freed pages go: bank 0 / new bank-4 region / other (not R6).
5. Slack to keep.
6. Undocumented IXL/IXH opcodes (fine on all Z80s; sjasmplus supports them).
