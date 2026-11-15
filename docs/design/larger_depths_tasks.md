# LARGER-D work breakdown (z80-architect, read-only, 2026-11-15, main fe83e10)

Spec: `larger_depths.md` (approved defaults). The budget figures in §5 there are stale; the free bytes below come from memory-map F1/F2/SIZE T4. There is no minimap. spawn6, tier6 and pool6 don't depend on the grid, so the pool grows by 0 B.

## Low-RAM layout (resolves survey gap 1; T2 implements it, staff may adjust)

The header leaves page $6D, so ROOM_DESC gets the whole page.

| Addr | Item |
|---|---|
| `$6D40` | ROOM_DESC 12 × 16 = LVL_STATE (`rdp` L = $40 + 16r ≤ $F0) |
| `$6E00` | FLOOR_LIST 32 × 4 (unchanged) |
| `$6E80` | header 16 B (same internal offsets) |
| `$6E90` | EDGE_TAB 8 B |
| `$6E98..$6E9C` | TRK_PHASE, TRK_PREV, TOME_HP, TOME_FL, DN_QN (same order) |
| `$6E9D` | TRAP_N (2 B spare after it) |
| `$6EA0` | TRAP_LIST 8 × 2 |
| `$6EB0` | **DG_PLAN 16 B** (DECOR2 plan; drops the `$6DF0` claim; per-build scratch, so zeroing on level gen is harmless) |
| `$6EC0` | LVL_STATE_END = ORN_GLYPHS |
| `$6F00` | LP_STATE 199 B (was 154), ends `$6FC7`. TRK_W 12 B at +19..+30, ROOM_VISITS +31, LP_REC +43, LP_POS +151, all within one page |

Cost: low RAM 844 → ~735 free (LVL_STATE +64, LP +45). Manager decision: DG_PLAN at $6EB0.

## Tasks

| # | Owner | Depends | Scope | Bytes |
|---|---|---|---|---|
| T1 | junior | — | Balance gate + item sweep (`balance_sim.py`, `items_model.py`): 12-room levels, regen k ∈ {16, 24, 32}, 10k × 2 seeds, FLOOR_LIST loss 32 vs 40 | 0 |
| T2 | staff Opus | — | Behaviour-neutral layout refactor, grid stays 3×3: `ROOM_SLOTS` 12, `GRID_CELLS` 9, TRAP_MAX 8, `attempt` zeroing, tut_start / proto_fix / tut0_level copy 9 + zero 9–11, asserts; hex-address tests (endwait, endcard_k) | low RAM −109, bank 3 +~8, blob +2..10, proto +2 |
| T3 | junior | — (block-model run needs T2) | Python 3×4 reference: `levelgen.py` §2 rules, LP `range(12)`, potions 3 + rnd(2) in level-gen step 8, `levelcheck`, decor_sweep / density, `levelgen_test` | 0 |
| T4 | staff Sonnet-ok | T2, T3 | Z80 generator 3×4, bit-exact with T3: valid/hedge tabs, bottom row 9, dfs_done, D8 `cp 12`, S = 9 + 2·rnd, sanct7 pairs, **tome6/7 invert `bit 1`** (9 left, 11 right), fx_cand 11, GRID_H 4, ROOMS 10–12, LP_N_MIN 16, RESPAWN_MAX 8 | bank 3 +~20, R6 +3, bank 7 ±2 |
| T5 | staff Sonnet-ok | T1 | Pacing (package 2, user 2026-11-15): lp_dtab = today × 1.5 half-up 20/21/21/23/24/23/23/18 (was ×1.35 18/19/19/20/22/20/20/16, superseded), xpn_tab ×1.35, FED regen 1 + MAXHP div 24 (DN_SLOT+DS_SNAP grows by the HP actually gained), Mage MP period alternating 4/5 (Warrior 8), respawns progress-tied per larger_depths §3.2 (p 0.75 per first room entry, cap 6, time trickle disabled on larger depths) | bank 7 +15–20 |
| T6 | junior | T1, T2 | Item generator: food 4–5, scrolls 2, arrows 1d4+6, traps ×4/3 cap 8; `.fe` `bit 7, l` assumes 32 entries | B0 overlay +10–30 |
| T7 | junior | T4–T6 | Tests / goldens re-baseline, doc sync (game.md §8, budget.md §6, decor_rules2 §3, larger_depths §5); re-check the trickle budget (+33 %) | 0 |

| T3b | junior | T3 | Python level key per `larger_depths.md` §2.1: lock sets on bridge edges of the start→lair path, key placement, F_min = n − 4 with Warnsdorff-bias restart, levelcheck no-softlock proof + coverage report (300 seeds) | 0 |
| T8 | staff Sonnet-ok | T4 | Z80 key runtime: key found on key-room first entry (count 0–2, `YOU FIND A KEY`), locked door = wall to all monsters, bump 0 turns `THE DOOR IS LOCKED` / with key 1 turn opens for the level (`YOU UNLOCK THE DOOR`), bag KEY slot shows the count | bank 3/7 + 19 B text |

User 2026-11-15: level key goes live in LARGER-D (§2.1, decisions Q1–Q5). T4 ports T3+T3b bit-exact (lock/key generation in levelgen).

Waves: T1 ∥ T2 ∥ T3 → T3b → T4 ∥ T5, then T6 ∥ T8 → T7.

## Acceptance highlights

- T2: everything byte-identical: levelgen_z80, tut0, items3e, world W13/W14/W16, roommem ADV, budget.
- T4: levelgen_z80 D1–D8 bit-exact with T3; level-gen worst ≤ +50 %; roommem ADV ≤ 70,000; A2 ≤ 22,000 (headroom 296 T).
- T1: gate is both classes ≥ 35 % and ±3. If it fails, apply the knobs in spec order; no Z80 until it passes (user rule).

## Risks / gaps

- A2 headroom is 296 T. If it goes over, that's a perf task, not a relaxed budget (no-cut rule).
- tut0's 9 rooms sit in a 12-slot grid, so rooms 9–11 must be zero or LP and trickle see ghost rooms.
- ST2_ITM is 1 byte (~110 items per run?). TURN_COUNTER and the end-card TURNS width need checking for ~4,900 turns (T5).
- Bank 4 has 38 B free and Tutorial v2 loses 2–10 B of it. There is no cap on per-level generation time.
