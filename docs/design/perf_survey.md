# Tick-cost survey (architect, 2026-11-10, read-only; code = feat/mirror-c worktree)

Goals: (a) full Option C (walk/MOT/hurt mirrored, ≈ +15–25k T worst tick, unmeasured), (b) more bodies per room,
(c) margin. Limits: real ≤ 141,816 T, work CAP 126,000. Worst real today 137,265 (`blair`). M = measured, E = estimate.

## Where the worst tick goes (RENDER_FIRST=1)
Input tick = present (last 5-body walk) + render + try_player_turn (~11k M) + resolve_monsters (16–23k M; blair + King
shot ~9k). Per walking 24×48 body: erase ~8k, blit ~8.8k, present ~7k, stamp ~1k. Panel/decor/marks/drip/dnum already
deferred. ISR uncontended (top border). Blit loops near-optimal (36 / 50 T/B).

## Ranked candidates (worst-tick)
| # | Candidate | Saving (worst) | Bytes | Risk | Lvl |
|---|---|---|---|---|---|
| 1 | Defer monster phase of ordinary turns 1 tick (bank7.asm:183 → MON_AT/act_pend path, own gate, not LOG_MON_MAX) | −12..20k input ticks | ±5 B bank 7 | monsters start 40 ms after hero; trace rebaselines | staff |
| 1b | Defer whole turn logic 1 tick (budget.md §4 lever) | −27..35k | 10–20 B | +40 ms input latency | staff |
| 2 | Erase each cell once (anim.asm:983, mask-driven single erase) | −1..3k blair, −3..6k stacks | 100–150 B bank 2 | PRES_MASK pre-marks, PEND_DMG/FX rects | staff |
| 3 | Clip forced re-blits to damaged rows (anim.asm:1004-1045, setup before blit_sp_on) | −2..5k attack/stand ticks | 40–60 B bank 2 | mirror chain needs same row start | staff |
| 4 | Skip empty cells in erase/present (per-frame occupancy mask) | −3..5k per tall walker (−12..20k 5-body) | 0.4–0.6 KB/level pool or B0; ~100 B bank 2 | HIGH: damage/present invariants | staff (L) |
| 5 | Hot AI (turn3.asm:205-713, ~0.6 KB) bank 3 → B0_FREE (uncontended) | −1.5..3k (0 after #1) | B0 +0.6 KB, frees bank 3 | B0 no SMC / no $C000 paging | staff |
| 6 | try_player_turn/find_target bank 7 → B0 | −0.5..1k | B0 ~0.5 KB | as #5 | staff |
| 7 | farb inlines page_bank | <0.3k (avg 0.3–0.5k/turn) | +10 B bank 2 | low | junior |

Bank 2 has 4 B: #2/#3/#4/#7 need a funding task first (move page-free cold bank-2 code to B0_FREE).

## Structural options
- Page-flip: not feasible (pool and screen 7 share $C000; all writers ×2; no buffer room).
- Fused restore-blit: not feasible (registers while SP is borrowed).
- Edge-trimmed frames: −0.5k / −1.5k mirrored per blit; saves pool; low tick value.
- **Mirror cache**: on room entry mirror the room's ≤ 4 kinds' walk/MOT/hurt into freed pool/B0 → full C memory at 0 tick
  cost; mid-room arrivals (summons/followers) need a deferred fill (~10k/frame). Feasible, staff, medium.
- Animation LOD (far bodies step every other tick): halves their render; walk parity (WK4/WK0) suffers — design call.
- Runtime shift: worse (+20–30 T/B); keep pre-shift.

## Reaching the goals
- (a) Full C: #1 (or 1b) for input ticks; mid-walk all-left ticks (wroom 135.5k real) need #2 + #3 (+ #4). Or the
  mirror cache instead (no tick work).
- (b) +1 body: ~12k/walk tick + ~4k AI (small), ~28k + 5k (tall). #1 covers AI; walk ticks need #4 + #2. Small extra
  body reachable; tall only with LOD. Check DMG_MAX 48 overflow at 6 bodies.

## Measure first
1. GAME_PROFILE=1 phase split of blair / wroom / lmixw / mage on the C build (doc splits predate C).
2. What-if full C: walk/MOT/hurt |MIR + new `lwalk` scenario (hero + 4 left walkers) → the real gap.
3. Python: per frame share of fully transparent 8×8 cells (decides #4, edge trim).
4. Double-erased cell count per worst tick (decides #2).

## Open decisions (user)
1-tick monster lag (#1) vs +40 ms input latency (1b) vs neither; is LOD acceptable at all.

## Measurements (junior, 2026-11-10; copy: scratchpad/perfcopy, perfcopy_h, perfcopy_c; ±3k tick-to-tick noise)
- **M1 phase split (worst tick, kT):** present+erase+blit = 45–65% of every worst tick except wroom4 (resolve_monsters
  42.1k). blair 130.9 total: present 24.0, erase 16.3, blit 26.0, resolve 19.9. wroom 127.4: resolve 23.8. lmixw:
  blit_mchain 24.7k. dn_gate/pend_far up to 11.8k (lmixw, mage).
- **wcast anomaly = NOT mirror cost.** One mirrored 32×48 blit ≈ +1k. The +15.5k was dn_gate (12.8k vs 0.1k): a tick that
  crosses into its 2nd frame with numbers queued runs dn_q2; slightly slower hurt ticks flip that choice and the timeline
  drifts chaotically → heavy dn work + heavy render in one tick. **dn_gate scheduling is itself a worst-tick lever.**
- **M2 full C (walk+MOT+skeleton_hurt |MIR):** of 64 scenarios only blair (work 130.8k, real 140.5k: 1.4k margin) and
  wroom (work 127.1k) exceed CAP. `lwalk` (5 bodies walking left every tick) 168k real, but its right-facing control
  `rwalk` is 155.6k → over budget TODAY independent of C; full C adds ≈ 2k per mirrored body. Full C frees +6,928 B at
  D8 Warrior (range 3,952–6,928 B) beyond the hybrid.
- **M3 empty cells:** ~10% of cells transparent, but only 1 cell transparent in both old and new frame per 5-body walk
  tick → #4 saves ≈ 0.3k realistic. **Drop #4 and edge trimming.** Tool: tools/frame_cells.py (copy).
- **M4 double erase:** 0 cells in every worst tick (max 20 on non-worst ticks). Erase ≈ 315 T/cell. **Drop #2.**

## Revised conclusion
- Full C is reachable with #1 (monster phase 1 tick later): blair/wroom are input ticks carrying resolve 20–24k.
  Plus a dn_gate fix (never run dn_q2 in a tick that already carries a full render) to remove the chaotic spikes.
- Dropped: #2, #4, edge trim. Kept: #1/1b, dn_gate scheduling, #3 (attack/stand ticks), #5/#6 (average).
- More bodies per room: rwalk shows 5 always-walking bodies already exceed budget → needs #1 + render-side work or LOD.

## Adaptive defer (2026-11-12, user decision)
#1 (MON-DEFER) now fires only when the input tick is already in its 3rd frame (practically never): the monster phase
runs on the input tick as on main, and an input tick may spill into a 3rd frame (+1 frame) instead of costing a
whole extra tick (+2 frames). Budget: monster-phase ticks gated at 3 frames, render ticks at 2 (budget.md
"ADAPT-DEFER"). Next lever for the 3-frame share: input-tick logic out of contended banks (#5 / #6 below).
