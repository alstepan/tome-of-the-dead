# MORE-MON — more monsters per level (PROPOSAL, designer 2026-11-04; nothing is built)
Scope: more monsters in **total** per level. ROOM_CAP 4, the 16 slots, Σ ≤ 12, the tick budget and low RAM do not change.

## 1. Today (game.md §9.4 / §9.4.1, `src/lpop3.asm:40-47` `lp_dtab`, mirror `tools/levelgen.py:695` `LP_TAB`, `tools/balance_sim.py:110` `MON_COUNT`)
| D | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Total incl. boss (`LP_TOTAL`) | 11 | 12 | 12 | 13 | 13 | 14 | 14 | 11 (10 + Archmage) |
| N = total − boss − escort, split over R | 9 | 10 | 10 | 11 | 11 | 12 | 12 | 9 |
| `ROOM_MAX` (`level_defs.asm:297-298`) | 2 | 2 | 3 | 3 | 3 | 3 | 3 | 3 |
| Capacity 5 × ROOM_MAX (smallest R) | 10 | **10 = full** | 15 | 15 | 15 | 15 | 15 | 15 |
- Generation (`lp_budget`, `lpop3.asm:84-183`): R = the 7–9 rooms minus start and lair (D8 also minus the Sanctum), so |R| = 5–7. Each room in R gets 1. The rest goes one unit at a time by a weighted pick (weight = BFS distance from the start) to rooms below ROOM_MAX. So a room in R holds 1–2 on D1–D2 and 1–3 on D3–D8. The start room holds 0, the lair holds the boss + 1 escort, the Sanctum holds 0. Anything left over goes to `LP_DISCARD`, and levelcheck asserts that is 0 (`levelcheck.py:401-427`).
- Kinds are rolled at first entry: `LP_KINDS[rnd&3]`, then the §9.6 tier roll (`T2_BASE` 24…96 and `T3_BASE` 0…48 of 256, D4+). Then the **reservation fit**: Σ + w + left × minW ≤ `SIGMA_INIT` = max(8, ROOM_MAX × minW) (`tier6.asm:53-64`). Consequence: **a room with 3 units holds only light kinds.** D3 = Ghost/Bat, D4 = Rat/Spider, D5 = Spider ×3, **D6–D8 = Ghost ×3** (minW 3, SIGMA 9; weights `defs.asm:749-775`).
- Awake vs asleep: there is no sleeping population. Every resident spawns idle and wakes when the hero enters (§9.5 "Placement"). ASLEEP comes only from the Sleep scroll or the GAS trap.
- On top of that: the trickle adds ≤ `RESPAWN_MAX` 6 per level (half XP, no drops, §9.5), plus summons (Bone Caller and Archmage, 1 live each).

## 2. Proposal: change only the count byte; kinds and the pool stay as they are
| D | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| LIGHT (data only) | 12 (+1) | 12 (0) | 14 (+2) | 15 (+2) | 15 (+2) | 15 (+1) | 15 (+1) | 13 (+2) |
| **MEDIUM (rec.)** | **13 (+2)** | **14 (+2)** | **14 (+2)** | **15 (+2)** | **16 (+3)** | **15 (+1)** | **15 (+1)** | **12 (+1)** |
| HEAVY | 14 (+3) | 15 (+3) | 16 (+4) | 16 (+3) | 17 (+4) | 17 (+3) | 17 (+3) | 14 (+3) |
Hard limit: N ≤ 5 × ROOM_MAX, so total ≤ 12 on D1–D2 (≤ 17 if ROOM_MAX_LO becomes 3) and ≤ 17 on D3–D8. MEDIUM and HEAVY raise `ROOM_MAX_LO` from 2 to 3. With 3 units on D1–D2, Σ still fits 8 because minW = 2. **Why late levels get only +1 in MEDIUM:** any unit beyond 2 per room on D6–D8 is forced to be a Ghost (§1). The Ghost is already the top killer: 44 % of Mage deaths and 19 % of Warrior deaths (bal1_final.md §2 B). Kind sets do not change, so `POOL_NEED` and SEQ-cache need are identical, and the D8 Warrior pool slack floor of 384 B is untouched.

## 3. Effects (MEDIUM; XP is my estimate from the §4.1 KXP table with the light-kind fit applied)
- **XP:** added XP per level ≈ D1 5, D2 5, D3 8, D4 6, D5 12, D6–D8 7 each. At level entry the hero has D2 53, D3 126, D4 261, D5 423, D6 625, D7 870, D8 1,122 (§4.1 today: 48 / 116 / 243 / 399 / 589 / 827 / 1,072). Every entry still sits below the next `XP_NEXT`, so the expected `LVL` at entry stays = d and tier Δ stays 0. The change: L9 comes early on D8 instead of "near the end", and a skipper has more slack.
- **Win rate:** bal1 FINAL B is W 41.4 / M 43.4 (target 35–45, gap ≤ 5). About 14 % more fights in total. D3–D5 extras are light kinds, so the cost there is mostly HP, potions and turns. D6–D8 add 1 Ghost-heavy unit, which hits the Mage harder. Direction: both heroes lose a few pp and the gap moves toward W. Size: unknown until the sim runs (`MON_COUNT`/`ROOM_MAX` are sim params). HEAVY likely leaves the band.
- **Food/loot:** D1, D2 and D4 extras include droppers (Rat Cheese 1/4, Goblin Apple 1/4; tiers +1/4, §9.6). Extra turns ≈ +20–40 per level ≈ 3–7 FOOD, against the §8.11 margin of ≈ 100 in vs 75 burned. Floor list ≤ 32: surplus drops are lost, uniques are always kept (§8.11 Q11).
- **Caps:** first-entry ≤ ROOM_MAX = 3 < ROOM_CAP 4, so LR_MAX 4, the follower headroom, ROOM-MEM parking ≤ 12 slots (2 × 4 + 4) and the worst-case transition (≤ 70k T, spawn ≤ 46k) are unchanged. Only the mean cost rises, because more rooms place 3 units. **Risk:** placement waits are 12.1 % today against a 15 % ceiling (§9.4.3, `levelcheck.py:515`). More 3-unit rooms push that number up, so levelcheck must pass this.
- **Exits/ladders:** more 3-unit rooms means more follower refusals (escape gets easier) and more head-on ladder jams (D-AI1(b), §9.4.8). Bone Caller summons get refused more often (room fuller). Trickle eligibility drops slightly (record < 4, Σ + minW ≤ 12), but `RESPAWN_MAX` is unchanged.

## 4. What changes and what to re-run
- Data, 0 B: the 8 count bytes in `lp_dtab` and the `LP_TAB` mirror. `lp_budget` copies GEN_RNG and restores it, so the L2 pass and items/traps (`ITEM_RNG`) stay byte-identical. Only quotas, and with them room contents, change.
- MEDIUM/HEAVY also change code, ≈ −5 B: in `lpop3.asm:104-109` the `cp 3 / sbc` and `ASSERT ROOM_MAX_HI == ROOM_MAX_LO + 1` become a single `ld a, ROOM_MAX`, plus the mirrors `levelgen.py:845`, `levelcheck.py:401` and `balance_sim.py:109`. HEAVY's optional `SIGMA_INIT` change is a constant, but it eats follower Σ headroom: not recommended.
- Re-run: levelcheck seed sweep (quota ≤ ROOM_MAX, Σ = N, discard 0, waits ≤ 15 %), `tests/lp.py`/`roommem.py` (the Python == Z80 spawn reference), `tier_respawn_model_test`, `trickle.py`, the balance_sim FINAL B 10k × 2 sweep, and the full `test`. Goldens: the start room has quota 0, so only goldens of seeded non-start rooms can shift; re-bless after review. Docs: §9.4 table, §9.4.1 N text, §4.1 expected XP, §10.

## 5. Recommendation and open questions
**MEDIUM**, gated on balance_sim keeping both heroes in 35–45 with gap ≤ 5. If it does not, fall back to LIGHT. Questions:
Q1: Is a Ghost-heavy late game acceptable? If yes, use HEAVY on D6–D8. If you want non-Ghost extras on D6–D8, that needs a per-depth `SIGMA_INIT` (≥ 11) or a fit-rule change: code, and it eats follower headroom.
Q2: Should D8 grow at all, given the Archmage fight runs with summons in the lair?
Q3: If the sim drops below 35 %, should we compensate with a knob (Heal amount, §10 knob 1) or cut the counts back?
