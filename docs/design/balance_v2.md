# BALANCE-V2: magic evenness + retune to the 2026-11-16 targets (designer recommendation, 2026-11-16)

Status: **recommendation, nothing built.** Targets (user 2026-11-16, `balance_sim.py --ld-pkg`, 10k × 2 seeds): **best
expert 30–40 %, average 15–25 %, |W − M| ≤ 3 in each band.** Today: average W 32.5 / M 36.3, best expert
(`expert+charm_food+rest_fed-no_rest_full-no_jump_p`) W 72.5 / M 81.1. The average must drop ~10–14 pts, the expert
~35–45: we need levers whose effect grows with play skill. The skilled exploit is one loop: **food → FED → regen →
HP**, stretched ×2 by Plenty/Scarab. The package taxes that loop first and touches monster density last.
Constraints kept: no cuts, no stealth, monsters keep hunting, prefer table/constant edits.

## 1. Magic evenness

Why Firebolt dominates: per MP it is *not* the best spell (rank 1: Frost 4.5 dmg / 3 MP + freeze beats Firebolt 4.5 /
5 MP + burst). It wins because COLD is resisted (R/I/X) by 10 of the 16 resist-table rows and SHOCK is reflected by the Ghost line and the
Archmage, while FIRE is N or W almost everywhere. So the fix is mostly **fewer COLD/SHOCK walls**, plus two FIRE
trims. "Viable" = N or W (R counts only as a fallback).

| Kind (row) | Today | Proposed | Viable answers after | Reason |
|---|---|---|---|---|
| Ghost, Poltergeist (2 rows) | COLD R | **COLD N** | Firebolt, Frost Shard (+ freeze 2) | the no-Firebolt Mage gets a real answer; SHOCK X (the Ghost's identity) stays |
| Archmage | SHOCK X | **SHOCK R** | Firebolt; Lightning/Spark at ½ | BAL1 option (a); Lightning still pierces summons into it. COLD X stays |
| Vampire (+ Vampire Lord, same row) | FIRE W | **FIRE N** | Firebolt, Spark, Lightning | removes the most common FIRE W; Mummy / Wraith / Slime keep W (thematic) |
| Gargoyle | FIRE N, COLD R | **FIRE R, COLD N** | Frost Shard, Spark, Lightning | stone: Frost cracks it, fire barely warms it |
| Necromancer, Bone Caller | COLD R | **COLD N** | all four non-DARK types | a living caster had no reason to resist COLD; freezing a shooter is Frost's job |

Unchanged rows already pass (≥ 2 types): Skeleton line (FIRE, SHOCK), Mummy, Wraith (FIRE, SHOCK), Imp (COLD W,
SHOCK, DRAIN), Orc (SHOCK, DRAIN, COLD), Ogre. **Death Knight** stays SHOCK-only (Spark + Lightning; Spark is always
known): accepted. Optional extra Firebolt trim if Mage stays > W + 3 after §2: Firebolt rank 1 burst 1d4 → 1d3
(`ab_rank` byte).

Niche per spell after the change:
- **Spark** — cheap opener, confuse, Bat / Ogre / Death Knight W; the guaranteed spell.
- **Firebolt** — Mummy / Wraith / Slime W, group burst, the Archmage's main answer; no longer the default for Vampires.
- **Frost Shard** — control: Ghosts, Necromancers, Gargoyles, Imps (W); freeze is the defence vs flyers and casters.
- **Drain Life** — sustain vs every living kind (Orc, Spider, Goblin, Necro, Imp); food-free healing.
- **Lightning** — pierce packs, Skeleton line, Death Knight W, Archmage summons + Archmage at ½.

Bytes: **all pure data** — `kx_tab` resist bits in place, 7 rows (Ghost, Poltergeist, Archmage, Vampire, Gargoyle,
Necromancer, Bone Caller), **0 code bytes, 0 net bytes**. game.md §9.1 resist table + design intent and §10 answer
table to be synced. The Warrior is unaffected (he has no typed damage), so this is a clean **W/M-gap lever**: expected
Mage −2…−4 pts all policies (Vampire/Gargoyle nerf outweighs the late Ghost/Archmage buff on average; the no-Firebolt
tail improves).

## 2. Retune package (ordered; apply cumulatively, stop when the gate passes)

| # | Knob (game constant → sim key) | Change | Expected Δ (avg / best expert) | Why it hits experts harder |
|---|---|---|---|---|
| K1 | Plenty / Scarab burn: `ld b, 2*FOOD_PERIOD` (hunger7.asm) → new `PLENTY_PERIOD` EQU → `gear.<Amulet of Plenty / Scarab>.food` | ×½ → **×¾** (period 12 → **8**) | −1 / **W −3, M −15…−20** | only `charm_food` play seeks the amulet; it was worth M +37. Still a useful charm |
| K2 | `HP_REG_FED` → `param.FED_REGEN` | 12 → **16** turns | −3…−5 / −8…−12 | food per regen HP ×1.33; the expert rests far more (rest_fed, 70 % thresholds) |
| K3 | time trickle on D1–D8 at ⅓ rate while the boss lives (`trk_run` exists, D0-only today) → `param.RESP_MODE=progress+time` | off → **on** | −2…−4 / −5…−8 | long rests now cost monsters, not just food; "monsters keep hunting" literally |
| K4 | floor food per level → `param.FOOD_N` | 4–5 → **3–4** (then [3,5]) | −3…−5 / −5…−8 | food is the expert's binding resource; average dies to monsters before starving |
| K5 | §1 magic delta → `kx.*` | on | M −2…−4 / M −2…−4 | evens W/M (Mage leads by 4–9 in every policy) |
| K6 | potions → `param.POT_N` / `param.HEAL_AMT` | 3–4 → **3**, or Heal 12 → 11 | −3 / −2 | average trim only if the average is still > 25 |
| K7 | `HP_FED_DIV` → `param.FED_REGEN_K` | 40 → **56** | W −2 / W −3 | Warrior-only regen trim if W stays > M + 3 (MAXHP 56+ keeps +2) |
| K8 | monster counts → `param.MON_COUNT` | ×1.05 | −3 / −3 | last resort: flat tax, does not narrow the skill gap |

Back-of-envelope K1–K5: average W ≈ 32.5 − 12 ≈ 20, M ≈ 36.3 − 15 ≈ 21; expert M ≈ 81 − 40 ≈ 41, W ≈ 72.5 − 28 ≈ 45.
So **expect W expert to need K7 and possibly FED_REGEN 18**; the sim decides. Do not use XP_NEXT (it slows both
classes equally and lengthens runs, which raises food pressure unpredictably).

## 3. Sim plan (junior, Sonnet; ~1 spawn)

**Step 0, fix the baseline (blocking).** `--ld-pkg` does **not** set `param.NEWMON3=1`, so the reported numbers may
lack Gargoyle / Fire Imp / Frost Wraith and the 8-slot lists the game ships. Re-run the baseline with
`--overrides tools/balance_nm3.json` (or `--set param.NEWMON3=1`) and confirm which one matches the build; all steps
below include it. If the baseline moves > 3 pts, re-scale §2 from the new numbers before sweeping.

**Policies (each cell = W and M):** `average`, `cautious` (report only), and the expert set
E1 `expert+charm_food+rest_fed-no_rest_full-no_jump_p`, E2 `expert+charm_food+rest_fed`, E3
`expert+charm_food+rest_fed-no_rest_full`. **Gate the expert band on max(E1..E3)** (the user's "expert" is the best
play we can find); `+avoid` variants are reported, not gated (room skipping borders on avoidance).

**Gear knobs need a JSON file** (`--set` rejects `gear.*`): scratch `bv2_k1.json` =
`{"gear": {"Amulet of Plenty": {"food": 0.75}, "Scarab": {"food": 0.75}}}`; magic = `kx.Ghost.COLD=N`,
`kx.Poltergeist.COLD=N`, `kx.Archmage.SHOCK=R`, `kx.Vampire.FIRE=N`, `kx.Gargoyle.FIRE=R`, `kx.Gargoyle.COLD=N`,
`kx.Necromancer.COLD=N`, `kx.Bone_Caller.COLD=N` (check the kid names in the image; kx overrides do reach the NEWKINDS
rows). Run each seed separately (`--seed 1`, then `--seed 2`; the comma list is only for `--larger-d`).

- **A. slopes** (2k runs, seed 1, one knob at a time vs baseline): K1 {0.75, 0.667}, K2 {14, 16, 18}, K3 on, K4
  {[3,5], [3,4]}, K5 on, K7 {48, 56}. Output: Δ per knob for average and E1 → re-order the ladder by
  (expert Δ / average Δ).
- **B. ladder** (5k, seed 1): cumulative K1→K5, then K6/K7/K8 only as needed; at each rung report average, E1–E3,
  W/M gap, top 5 killers, mean death depth, share of deaths while not FED.
- **C. gate** (10k × seeds 1 and 2, pooled): **average W, M ∈ [15, 25]; max-expert W, M ∈ [30, 40]; |W − M| ≤ 3 in
  both bands; no killer > 30 % of a class's deaths; STALL < 1 %.** Also report the no-Firebolt-Mage subset win rate
  (books stat) — it must not be < ½ of the Mage average.

**Sim gaps that weaken trust (state them next to the result):**
1. NEWMON3 flag (Step 0). 2. **Door play:** flyers (Ghost, Gargoyle, Imp, Wraith) are blocked by closed doors in the
game, not in the sim — real Ghost lethality for a skilled player is lower than the sim's 21–30 %. 3. **Spell choice
is dmg-per-MP**: Frost's freeze has no value in the bot's pick, so K5's Ghost/Necro buff is under-measured. 4. **Faints
are not modelled**: K1/K2/K4 starvation costs are slightly optimistic for the bot. 5. K3 in the sim is a flat 1/3-rate
trickle; the game version must match (period 48, chance 32 of 256, same `RESPAWN_MAX` 6 cap shared with progress).
6. Floor items are collected per room clear (no item hunting), so K4 is exact in count but not in timing.
After the gate: emulator spot-check one D3 and one D6 Mage seed (Ghost room, Frost Shard kills).

## 4. Byte / code estimate

| Change | Kind | Bytes |
|---|---|---|
| K5 magic delta (7 `kx_tab` rows) | data | 0 |
| K1 Plenty/Scarab period 8 | constant (`ld b, PLENTY_PERIOD`) | 0 |
| K2 `HP_REG_FED` 16 | constant | 0 |
| K4 food count | generator constant / range table | 0–2 |
| K6 potions / Heal | constant (`QUAFF_HEAL`, pot range) | 0 |
| K7 `HP_FED_DIV` 56 | constant | 0 |
| K8 `lp_dtab` counts | data | 0 |
| K3 time trickle D1–D8 | code: un-gate `trk_run` from D0, `TRK_PHASE` count in `end_turn`, chance const | ~12–20 B (bank 7) |
| Firebolt burst 1d3 (optional) | `ab_rank` data | 0 |

Only K3 is code. If K1+K2+K4+K5 alone pass the gate, skip K3 (0 bytes total). Docs to sync on adoption: game.md §7
food table / FED row, §8 charm row, §9.1 resist table + intent, §9.5, §10 (answers table, BAL1 No-Firebolt item →
resolved by (a)).

## Open questions for the user

1. Ghost COLD R → N reverses part of the BAL-1 FINAL B intent ("Frost halved on Ghosts"): accept?
2. K3 brings time respawns back on D1–D8 (code, ~15 B): acceptable, or keep LARGER-D's pure progress respawns?
3. Gate the expert band on the best expert variant (max E1..E3), or on E1 only?

## 5. Sim results (junior sweep, 2026-11-16) and PACKAGE 4

Sim changes (tools/balance_sim.py, on top of PR #68): `--ld-pkg` now includes NEWMON3 + tools/balance_nm3.json (`--set param.NEWMON3=0` = old
preset); `--ld-pkg4` = `--ld-pkg` + `PKG4`; `--set gear.<Name>.<field>`; params `FED_STEP` (period of the K/L regen step, 12 = today),
`FED_REGEN_K_W` (Warrior-only k), `AVG_V1` (1 = old average bot); the **average bot now wears Plenty/Scarab and eats to FED before resting**
(user decision; `AVG_V1=1` reproduces the old one); gear_score regen/food terms linear (exact == 0.5 matches silently changed the bot's charm
choice for any swept value). RESP_MODE `progress+time` = 1/3-rate trickle, shared cap 6: matches the plan.

Baselines (10k x seeds 1+2, W / M):
- package 3, no NM3 (old preset): average 32.5 / 36.3, E1 72.6 / 81.1.
- package 3 + NEWMON3 (new `--ld-pkg`), old average bot: average 32.2 / 40.7, cautious 32.1 / 42.7, E1 71.6 / 81.0, E2 59.7 / 72.6, E3 70.1 / 78.9.
- same, **new average bot** (4k, seed 1): average 52.7 / 75.8 (E1 unchanged 70.5 / 80.7). The sensible average is almost the expert.

**PACKAGE 4 result (`--ld-pkg4`, 10k x 2):** average **20.6 / 25.2** (gap 4.6), cautious 9.0 / 6.8 (report only; it lacks charm/rest_fed),
E1 **34.3 / 28.2** (gap 6.1), E2 23.0 / 19.2, E3 33.0 / 25.4. E1 is the best expert combo. Targets: average W in band, M at the edge (25.2);
E1 W in band, M 1.8 under 30; gaps 4.6 / 6.1 vs the <= 3 goal. **Near miss, not a pass.** The Mage's average and expert numbers sit only
1-3 pts apart (the sensible average copies the expert's food habits), so average M <= 25 and E1 M >= 30 cannot both hold with scalar knobs.

Package 4 (knob -> sim key -> game constant / file):
| Knob | Value | Game constant / file | Bytes |
|---|---|---|---|
| FED regen step | 12 -> 16 turns (Warrior MAXHP 56 gets +2 per step) | `HP_REG_FED` src/item_defs.asm:254 (the div-40 term rides on it) | 0 |
| Floor food per level | 4-5 -> 3-5 | the level item generator's food count range (items model `FOOD_N`; staff to locate) | 0-2 |
| Time respawn on D1-D8 at 1/3 rate | on (period 48, chance 32/256, shared `RESPAWN_MAX` 6) | `trk_run` src/trickle6.asm:32 (D0-only gate), `end_turn` TRK_PHASE count | ~12-20 B bank 7 |
| Mage MP regen | 5 -> 7 turns | `MP_REG_M` src/xp7.asm:13 | 0 |
| Mage HP per level | 3 -> 2 | `LUP_M_HP` src/xp7.asm:16 | 0 |
| Warrior HP per level | 5 -> 6 | `LUP_W_HP` src/xp7.asm:14 | 0 |
| Scarab MP regen bonus | x1/2 -> x5/8 (food x1/2 kept) | gear6.asm `.h2: srl c` is shared with Amulet of Mana; Scarab needs its own `c = c/2 + c/8` | ~8-12 B code + strings.txt `ie_scarab` ("2X MP REGEN" wording) |
| Magic rows | Ghost+Poltergeist SHOCK X->R, Archmage SHOCK X->R, Vampire FIRE W->N, Gargoyle FIRE N->R + COLD R->N, Necromancer+Bone Caller COLD R->N | `kx_tab` src/combat_data3.asm:51 | 0 |
| Firebolt burst | rank 1-2 1d4 -> 1d3, rank 3 1d6 -> 1d5 | `ab_rank` effect low 3 bits, src/combat_data3.asm:142 | 0 |
Total code: ~20-32 B (time respawn + Scarab); everything else data / constants.

Which knobs did the work (4k, seed 1, on the new-average base): FED_STEP 16 (average W -27, E1 W -31); Mage regen 7 (Mage -30 / -25, the Mage's
tax); floor food 3-5 (-8..-10 both); Warrior HP +1/level (+3 average W, +6 E1 W); Mage HP -1/level (-2 / -1). Time respawn: -8 average, -5 E1.
**Magic rows hurt the Mage-lead:** all rows are Mage buffs in the sim (Ghost SHOCK R alone: average M +23 old-bot, +11 for the whole set on the new
average, E1 M +10); Necro/Bone Caller COLD N +3.7, Archmage SHOCK R +5 E1. Vampire / Gargoyle rows ~0. The Firebolt burst nerf is ~0 in the
sim (burst only hits neighbours / self). If the Mage must come down further, the first row to drop is Ghost/Poltergeist SHOCK (user decision to keep it) and
second the Archmage SHOCK R; Mage regen / Scarab buy it back at ~-5 per MP-regen turn.
Warrior vs Ghost: Ghost PHYS R->N lifts W +14 average / +10 E1 and Mage +9 / +7 (not Mage-neutral); Warrior-only regen k 32 lifts W +17 / +14, Mage 0.
Warrior HP/level 6 was chosen for the package (W-only, smaller). Hurt the wrong population: Warrior-only k 56 (plan K7), FED_STEP (W 3x the Mage's hit).

Sim gaps: bot charm choice drives Mage numbers; Mage average ~ E1 (small spread); doors / faints / frost-freeze value not modelled; cautious bot is
now below the average bot (not updated); Firebolt burst nerf unmeasurable (burst rarely hits). Spot-check in the emulator not done.
