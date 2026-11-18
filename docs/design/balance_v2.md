# BALANCE-V2: magic evenness + retune to the 2026-11-16 targets (designer recommendation, 2026-11-16)

Status: **package 4 (section 5) BUILT 2026-11-16 (`feat/balance-pkg4`); sections 1-4 are the original recommendation (history).** Original status: recommendation, nothing built. Targets (user 2026-11-16, `balance_sim.py --ld-pkg`, 10k × 2 seeds): **best
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

## 6. D3 spike (package 5) (designer recommendation, 2026-11-17; nothing built)

**Problem.** User playtest: "killed almost always on D3"; "the feel should be that you have a chance to win". Sim `--ld-pkg4`
(400 runs/cell): **D3 takes 27–54 % of all deaths** in every policy (D2 11–25, D4 9–18). Food at D3 entry is 43–50, so this is
not starvation. Top killers: Ghost 11–16 % of all deaths, Vampire Lord 4–15 % (mostly Mage), Poltergeist, Vampire. Cause by
the §9.4 table: D3 is the first undead depth, and **Ghost holds 3 of the 8 `LP_KINDS` slots** (37.5 % of 21 bodies plus the
respawns). The Ghost is a DEF 3 flyer whose touch confuses 1 in 4 (CONFUSED 4). Confusion takes away the one escape the
player has, which is walking away. Deaths that come from that feel unavoidable. Doors block flyers in the game but not in the
sim, so the sim overstates the Ghost (§3 gap 2). Even so, 3/8 is the heaviest single-kind weight on any depth.

**The "expert/cautious do worse" anomaly: partly confirmed.** By §9.5 the time trickle gives 32/256 per 48 turns, about one
spawn per ~384 level turns. It shares `RESPAWN_MAX` 6, and `LP_RESPAWNS` only counts up (§9.5 step 10). Progress respawns
(0.75 × ~14 first entries ≈ 10 events) fill the cap by mid-level in any case. So the trickle mostly changes **where and when**
monsters come back, not how many: it adds them early, into VISITED rooms, weighted toward rooms with items left on the floor.
That is exactly the path of a hero walking back to regen. The trickle is not the main tax, though. The `rest_full` habit cost
the same before and after package 4 (E2 vs E1: W −12 / M −8 in package 3, −11 / −9 in package 4). The plain `expert` and
`cautious` bots also lack `rest_fed` and `charm_food`. They rest while not FED, which gains no HP at all, and FED step 16 was
the single biggest knob (E1 W −31). Read: **the un-FED rest loop is what gets punished; the trickle adds ambushes on the way back.**
Test: `--set param.RESP_MODE=progress` on cautious + expert against the package-4 base. If they gain ≥ 5 pts more than the
average bot does, option B is worth more than estimated below.

**Principle: move difficulty, don't remove it.** Average M (25.8) is already at the top of its band. Whatever D3 gives back is
taken again at D4–D5, so the threat curve rises smoothly instead of hitting a wall.

| Rank | Option | Change | Sim knobs | Cost |
|---|---|---|---|---|
| **1** | **A. D3 mix + Ghost telegraph** | D3 `LP_KINDS` Ghost 3 → **2**, Goblin 1 → **2** (the Goblin is the D2 bridge kind). Ghost confuse touch 1 in 4 → **1 in 8** on every depth. The Ghost keeps its role, but being confused is now the exception: you get a turn to back off through a door. Pay it back: D4 monsters 23 → **24**. | D3 row in `tools/balance_nm3.json` (pool slot counts); `kind.Ghost` confuse probability 0.25 → 0.125 (junior adds the key if it is missing, ~5 lines); `lp` count D4 | **0 B**: `LP_KINDS` D3 row data; the confuse mask constant (`and 3` → `and 7`, same size); the D4 count byte |
| 2 | B. No time trickle on D1–D3 | `trk_run` returns below D4 (today it returns on D0 only). Progress respawns are unchanged, so monsters keep hunting and keep coming back. Only the early-depth ambushes on the walk back go. Resting at D3 costs food again, not surprise bodies. | new `param.TRK_MIN_DEPTH` = 4 (junior, sim) | **+1 B** bank 7: the D0 gate `or a / ret z` becomes `cp 4 / ret c`. Check that the D0 preset `LP_RESPAWNS = RESPAWN_MAX` stays (it does). |
| 3 | C. D3 supplies (the user's "more food") | D3 floor food 3–5 → **4–5**, plus one **guaranteed Heal** on D3 (on top of the ≥ 1 Heal rule). Golden Vampire Lord: drain-bite self-heal **½ of the damage** (the base Vampire keeps full). | `param.FOOD_N` per-depth override for D3; `param.POT_N` D3; `kind.Vampire_Lord` drain heal 0.5 | ~6–10 B for a per-depth food/potion range (the generator range is flat today); ~6–8 B for a golden-only `srl` on the heal (a `LEK_GOLD` test) |

**Recommendation: A + B as package 5** (≈ 1 B of code, everything else is data). A goes after the two biggest killers at
their source: Ghost density and the confuse lock that blocks escape. That gives the user's "telegraphed threats and escape
options" without making any monster stop hunting. B removes the one package-4 effect that punishes the eat → walk → regen
play the user actually does. Take C only if, after A + B, D3 still holds > 35 % of deaths or the Mage's Vampire Lord share is
still > 10 %. Food alone does not fix the cause, because deaths at D3 are not starvation.
Expected (back-of-envelope; the sim decides): D3 share of deaths 42–54 → **~28–35 %**, Ghost share ~7–10 %; average +2…+4,
cautious/expert +4…+8.
**Gate (§3 C rules, 10k × seeds 1+2):** average W, M ∈ [15, 25]; E1 W, M ∈ [30, 40]; |W − M| ≤ 3; **no depth > 35 % of a
class's deaths** (new, this is the "feels winnable" criterion); no killer > 30 %. If average M goes above 25: D5 monsters
24 → 25 first, then put the D4 count back (keep the spike moved, not raised).
**Sweep order** (2k, seed 1, one knob at a time, then cumulative): Ghost slots 3 → 2; confuse 1/8; `TRK_MIN_DEPTH` 4; D4 +1;
then C's three knobs separately. Report the death-by-depth row and the top 5 killers per class at every rung.
Docs to sync on adoption: game.md §9.4 D3 row, the §11 Ghost row (confuse 1 in 8), §9.5 lead paragraph (trickle from D4),
larger_depths.md §3 package line.

## 7. Package 5 v2: food ample, monsters + counterplay (designer recommendation, 2026-11-17; nothing built)

**User direction.** Food must stop killing ("death because of lack of the food makes game not so interesting"). Difficulty
comes from monsters, stronger or more numerous, and a careful player gets real ways to "trick them with scrolls, etc.".
Bad luck is allowed, but a run must never feel 100 % lost. Fixed constraints: monsters keep hunting (no stealth or
avoidance mechanic), no feature cuts, targets as in §6 (average 15–25, E1 30–40, |W − M| ≤ 3, no depth > 35 % of deaths).

**Why this also fixes the package-4 near miss.** Package 4 failed because average M ≈ E1 M: the sensible average copies the
expert's food habits, and scalar knobs move both bots together. Food play is a habit that anyone copies. Counterplay is a
**decision**: when to read Teleport, when to open with Sleep, when to Fear and leave. Moving difficulty from food to
monsters + escapes is what opens the expert–average gap the targets ask for. So the gate's expert becomes
**E1 + `avoid_pro`** (below), and the average bot keeps today's emergency-only escape use.

### 7a. Food target: "ample"

Definition, measured on the **average bot at the 75 % pickup rate** (the census-matched human proxy), 10k × seeds 1+2:
- **runs that ever reach HUNGRY before D5 ≤ 15 %**; runs that ever reach WEAK ≤ 3 %;
- **deaths with hunger stage ≥ HUNGRY ≤ 5 %** of all deaths (that is starvation as a contributing cause, not only as the killer);
- food at D3 entry ≥ 50 and food at D6 entry ≥ 40 (medians).

Knobs (apply in order; stop at the first rung that passes):
| Rung | Change | Sim knob | Game constant | Asm |
|---|---|---|---|---|
| F1 | hunger 1 food per 6 → **8** turns | `param.FOOD_BURN` 8 | the hunger period constant (staff to locate; if it is a counter compare, same size; if it becomes a power-of-2 mask, −1..−2 B) | **0 B** |
| F2 | floor food 3–5 → **4–5** (undo package 4's food cut: ~90 → ~105 value per level) | `param.FOOD_N` [4, 5] | the generator's food count range | **0–2 B** |
| F3 | start food 80 → **100** (only if F1 + F2 fail the D3 median) | `param.FOOD_START` 100 | the START food init | **0 B** |
`FED_STEP` stays **16**: walk-to-heal still costs something, just less (≈ 30 food per 30 HP at L3 under F1 instead of ≈ 40).
Arithmetic check: at 75 % pickup F1 + F2 supply ~79 per level against ~75 burned on a ~600-turn level, so a human finishes
roughly even and keeps the starting 80 as a buffer. Today it is ~67 supplied against ~100 burned.
Sim additions (junior, ~15 lines): stats `hungry_before_d5`, `weak_ever`, `death_hungry` (the hunger stage at death), and the
food medians at entry to each depth.

### 7b. Monster pressure (the payback)

F1 + F2 together will lift wins a lot (package 4's food knobs cost 8–31 pts). Take it back at **D4–D8 with bodies, not HP**,
keeping §6's D3 fix (option A: Ghost 3 → 2 slots, confuse 1 in 8) and its "move, don't raise" rule. Rungs, applied cumulatively
until the average bot is back in its band (2k, seed 1 per rung, then 10k × 2 to confirm):
| Rung | Change | Sim knob | Asm |
|---|---|---|---|
| M1 | monster count D4 23 → **25**, D5 24 → **26**, D6–D7 23 → **25**, D8 17 → **18** (D1–D3 unchanged) | `lp` count per depth (`tools/balance_nm3.json`) | **0 B** (count bytes) |
| M2 | `RESPAWN_MAX` 6 → **8** on D4+ (more hunters come back; they still hunt) | `param.RESPAWN_MAX_D4` (new, ~3 lines) | **~4 B** (depth test before the cap compare); 0 B if applied flat to D1+ (then rerun D3's share) |
| M3 | HP +1 die-face on the D5–D8 bruisers (Mummy, Orc, Vampire, Frost Wraith): ~+10 % | `kind.<Name>.hp` | **0 B** (kind table) |
| M4 | dmg +1 on Orc, Mummy (only if M1–M3 cannot reach the band) | `kind.<Name>.dmg` | **0 B** |
Room cap ≤ 4 per room (§9.3) holds, so M1 gives more full rooms and more respawns rather than bigger swarms. That pressure
is exactly what Sleep / Fear / Teleport answer.

### 7c. Counterplay: making "trick them" real

Today: 2 scrolls per level, type uniform from 4, so **Teleport 0.5, Fear 0.5, Sleep 0.5, Enchant 0.5 per level**. At 75 %
pickup P(no Teleport by D3 entry) ≈ 44 %, and the whole escape stock at D3 is ~1.7 scrolls against 21 bodies plus respawns.
The worse problem is efficacy. Teleport lands in a **random room**, which can be an unvisited room whose residents spawn on
arrival (lazy population), so the escape can drop the hero into a fresh fight. The sim treats Teleport as a clean retreat,
so **the sim overstates the game's escape value**. Fear 6 often runs out before a hero crossing a 28-col room reaches an exit.
| Rank | Change | Sim knob | Asm |
|---|---|---|---|
| **C1** | **Safe Teleport landing** (scroll and trap share it): pick a random **VISITED room with no live residents** (not the current room, not the lair while the boss lives). None → today's rule. Land ≥ 6 cols from any body. The time trickle and progress respawns can still refill the room later, so monsters keep hunting. This is no stealth: they come back | new `param.TELE_AMBUSH` = chance a landing starts a fresh-room fight (today ≈ unvisited-room share, ~0.4 mid-level; C1 → 0.05) | **~20–30 B** in the shared landing routine (room-record filter loop + fallback) |
| **C2** | **Scroll weights**: an 8-slot table like `LP_KINDS`, **Teleport 3, Fear 2, Sleep 2, Enchant 1**, and `SCR_N` 2 → **2–3**. Per level: Teleport 0.94, Fear 0.63, Sleep 0.63, Enchant 0.31 (Enchant still exists and still repairs; gate: weapon-destroyed rate must not rise > 5 pts) | `param.SCR_W` [3,2,2,1], `SCR_N` [2, 3] | **~10–12 B** (8 B table + `and 7` lookup replacing `and 3`) |
| **C3** | **Guaranteed Teleport on D2** (like the ≥ 1 Heal rule; it counts inside `SCR_N`) | `param.SCR_GUAR_D2` 1 | **~8–12 B** (copy of the Heal-guarantee pattern) |
| **C4** | **Fear 6 → 9 turns** (4-bit timer, max 15; bosses stay immune). Enough to cross a room to an exit or to throw daggers into backs | `param.FEAR_SCR_T` (today hard-coded 6 in two places) | **0 B** |
| C5 | Doors (they block flyers in the game) and jumps: already free counterplay, unmodelled. No change; the §3 gap 2 door model stays the sim's known underestimate of the hero | — | 0 B |
Sim expert: `avoid` = 1 mixes in **room skipping**, which is not a game mechanic (in the game, monsters in a room you avoid
still hunt and respawn). Add **`avoid_pro`** (~10 lines): the proactive Teleport / Fear disengage only, with no skipping, and
make **E1 + avoid_pro** the gate's expert. Report `tele_scrolls`, `avoid_tele`, `avoid_fear` per run, plus scrolls still
unread at death (target: median 0 for E1, so the expert is not hoarding).
Tutorial: D0 already teaches "READ FEAR OR SLEEP WHEN SWARMED" (§3 help row 21). Nothing to add.

### 7d. Fixed book order

It does **not** fit well. Rev 6 made the uniform pick a user choice for variety, and the user vetoed the keystone rule
(2026-10-26). A fixed order removes the Mage's build variety to fix one symptom, Firebolt timing, which is ½ by D2 and ⅔ by D3.
The Warrior's path is already near-deterministic, so it gains nothing. The "100 % bad luck" feeling comes from food and
inescapable rooms, which 7a + 7c remove for both classes. **Recommendation: keep the uniform pick.** Use the sweep's
fixed-order cell only as a measurement. If fixed order is worth ≥ 4 pts of Mage E1 **and** ≥ 5 pts of the Mage's D3 death
share **after** 7a–7c, offer the user the narrow version: **Firebolt-first on the first uniform read** (Mage only, D2+;
all other picks stay uniform). It is a keystone variant, so it needs the user's explicit OK. Sim `param.MAGE_FB_FIRST`;
asm ~6–10 B in the book reader. A full fixed order is ~0 B net (a table replaces the RNG pick).

### 7e. Recommended package 5 v2 and gate

**Package = F1 + F2 + §6 option A + C1 + C2 + C3 + C4, then M1 (+ M2/M3 as needed to land the band).** Code ≈ **40–55 B**
(C1 20–30, C2 10–12, C3 8–12, M2 4, F2 0–2), the rest data and constants. §6 option B (no trickle on D1–D3) becomes optional:
with F1 the walk back is cheap, so add it only if D3 is still > 35 % of deaths.
Ranking by value per byte: F1 (0 B, removes the killer) > C4 (0 B) > M1 (0 B) > C1 (makes every escape work) > C2 > C3 > F2 > M2 > M3.
**Gate (10k × seeds 1+2):** the §6 gate (average 15–25, **E1 + avoid_pro** 30–40, |W − M| ≤ 3, no depth > 35 %, no killer > 30 %)
**plus** the 7a food criteria at 75 % pickup **plus** the expert–average spread ≥ 10 pts per class (counterplay must reward skill).
Sweep order (2k, seed 1): F1; F1 + F2; + A; + C4; + C1 (`TELE_AMBUSH` 0.4 → 0.05); + C2; + C3; then M1 → M2 → M3 until the
average is back in band. Report the death-by-depth row, top 5 killers, the 7a food stats and the 7c scroll-use stats at every rung.
Docs to sync on adoption: game.md §7 hunger period, §8 scroll pool + Fear 6 → 9 + Teleport landing, §8.5 food/scroll counts and the
D2 guarantee, §6.4 FEAR row, §9.4 counts, §9.5 `RESPAWN_MAX`; larger_depths.md §3.

## 8. Package 5 final: sim results and constant-to-asm map (junior sweep, 2026-11-17; BUILT as BALANCE-PKG5, see the end of this section)

Final combo = `tools/balance_pkg5_final.json` (run: `--ld-pkg4 --overrides tools/balance_pkg5_final.json --set param.PICKUP=0.75`).
It is the §7 ladder (F1, A, C1–C4, M1) plus a damage ramp, a food shift from the floor to monster drops, and a Mage tune.
10 000 runs per cell, seed 1; W / M win %. E1 = `expert+charm_food+rest_fed-no_rest_full-no_jump_p+avoid_pro`.

| PICKUP | average | cautious | E1 | largest depth share of deaths (avg W / M) | starving deaths | HUNGRY + empty bag before D5 | food median D3 / D6 entry | eaten from drops |
|---|---|---|---|---|---|---|---|---|
| 0.75 | 16.4 / 16.4 | 22.4 / 27.2 | 37.6 / 43.6 | D4 46 % / D3 41 % | 12 % | 13 % | 56 / 52 | 56 % |
| 1.0 | 18.1 / 17.7 | 24.4 / 30.3 | 38.6 / 45.0 | D4 49 % / D3 40 % | 11 % | 12 % | 57 / 53 | 55 % |

E1 largest depth share: W D7 44 %, M D4 31 %. E1 reaches D5 in 79 % (W) / 69 % (M); the Mage has Firebolt at D3 entry in 48 %.
Cautious: starving deaths 16 %; it eats more food per run than average (862 vs 720), not less, because it rests more.

**Gates (PICKUP 0.75).** Pass: average 15–25 (both), average gap 0.0, E1 W 37.6, E1 gap 6.0 (≤ 8), E1 − average ≥ 10 (21 / 27),
food median at D3 ≥ 50, HUNGRY + empty bag before D5 ≤ 15 %, drop share 40–55 % (56, one point over).
**Fail:** E1 M 43.6 (band 30–40); no depth > 35 % (D4 46 % and D3 41 % for average, D7 44 % for the W expert); starving deaths 12 % (target ≤ 5 %).

Known sim gaps. The Ogre Warlord boss and the D3 Vampire Lord drive the D4 / D3 shares. The sim has no door or flyer-block model. The
average Mage is a weak bot, so any Mage nerf hits it harder than the expert (E1 M barely moves with `M_LVL_HP`, average M drops about 13 pts per HP point).
M1 asks D5 = 26 bodies, but `lp_dtab` caps the count at 24 (`lpop3.asm`: min room capacity 8 x ROOM_MAX 3). The sim does not model that cap, so the
real D5 pressure will be lower than measured unless ROOM_MAX or the layout changes. Weapon-destroyed % is not modelled.
The "starving" stat is HUNGRY (food < 25) with an empty bag at death. WEAK while carrying food (6 % of runs) is the bot not eating in time:
eating is blocked while poisoned and happens only between rooms and in rests, never inside a fight.

**Mage levers tried** (ramp-3 base, average M / E1 M): MAGE_REGEN 9: 13.9 / 46.2; LUP_M_HP 1: 12.9 / 52.2; both: 4.7 / 33.5;
Spark and Lightning bonus nerf: 16.1 / 45.8. Every nerf hit the average Mage about twice as hard as the expert. Final: MP regen period 9,
`LUP_M_HP` 4 (raises the average Mage back, no effect on E1), Firebolt bonus −1 per rank, Frost r2 / r3 −1. E1 M is still ~4 pts above the band;
the next lever to try is a Mage-only spell MP cost, not HP or regen.

**Constant to asm map** ("table" = data edit, 0 B code):

| Sim knob | Value | Z80 constant / table |
|---|---|---|
| FOOD_BURN | 6 → 8 | `FOOD_PERIOD` `src/item_defs.asm:245` (the x2 for Food / Scarab stays) |
| FOOD_START | 80 → 100 | `FOOD_START` `src/item_defs.asm:244` |
| FOOD_N floor | 3–5 → 3–4 | `ig_grps` food row `src/items_ovl.asm:758` (range byte 3 → 2 items spread) |
| DROP_ALL_P | 0.08 on every kill | new roll in `mon_drop` `src/drop3.asm` (non-boss, non-respawn): `rnd < 8/100`, then `rnd(5)` into the food items; ~12–16 B. Cheaper variant: raise the Rat / Goblin / Orc `drop_tab` 1-in-N rows (data) |
| FEAR_SCR_T | 6 → 9 | `SCR_FEAR_T` `src/fx6.asm:311` |
| SCR_W [3,2,2,1], SCR_N 2–3 | | scroll pool 8-slot table, `ig_grps` scroll row (`$80 \| 2` exactly 2 → 2–3) |
| SCR_GUAR_D2 | 1 | D2 item generator, copy of the Heal-guarantee pattern in `items_ovl.asm` |
| TELE_AMBUSH | 0.4 → 0.05 | Teleport landing routine (scroll and trap): choose a visited, empty room; ~20–30 B |
| NM3_LISTS D3 | Ghost 3 → 2, Goblin 1 → 2 | `LP_KINDS` D3 row (data) |
| Ghost confuse | 1 in 4 → 1 in 8 | Ghost `kx_tab` on-hit chance nibble (4 → 8) |
| MON_COUNT | D4 25, D5 26, D6 25, D7 25, D8 18 (D1–D3 20 / 21 / 21) | `lp_dtab` count bytes (see the cap warning above); `LP_N_MIN` `src/level_defs.asm:60` stays 18 |
| MON_DMG_SCALE_D | D3 1.9, D4 1.7, D5 2.6, D6 2.8, D7 3.0, D8 3.0 | `kind_tab` `KT_DIE` / `KT_BONUS` per kind (melee only; faces and bonus x scale, round half up; bosses too). `kind_tab` is per kind, not per depth: either (a) one per-kind die for the average depth and a flat ramp, or (b) a depth-indexed damage adder in `mon_melee` (~10–14 B) |
| MAGE_REGEN | 7 → 9 | `MP_REG_M` `src/xp7.asm:13` (9 * MP_RG_STEP) |
| M_LVL_HP | 2 → 4 | `LUP_M_HP` `src/xp7.asm:16` |
| Firebolt / Frost bonus | Firebolt r1 0 → −1, r2 2 → 1, r3 4 → 3; Frost r2 2 → 1, r3 4 → 3 | `ab_rank` rows `src/combat_data3.asm:142` |
| RESPAWN_MAX_D4 | not used in the final | – |

Docs to sync on adoption: game.md §7 hunger period, §8 scrolls / Teleport / Fear 9, §8.5 counts and the D2 guarantee, §9.4 counts and the D3 row, §11 Ghost row, §4.1 level-up HP.

**As built (BALANCE-PKG5, `feat/balance-pkg5`, 2026-11-17; memory-map "BALANCE-PKG5 ledger").** Every row above is in the asm
with the sim's semantics, with these notes:
- `MON_DMG_SCALE_D`: option (b), per hit, exact. Bank-3 `dmg_roll` calls low-RAM `dsc_roll` (`src/dscl.asm`) for a monster
  attacker: die N and bonus B each become `(32 + x · w) >> 6` with w = s × 64 per depth (64 64 64 122 109 166 179 192 192 for
  LVL_DEPTH 0..8), which equals the sim's `int(x · s + 0.5)` for every x in 0..15 (checked in Python; KT_DIE ≤ 10,
  KT_BONUS ≤ 3). Golden +1 and SLAM ×1.5 after it (atk_mod), as the sim. 47 B low RAM + 7 B bank 3; ~0.3–0.7k T a monster
  melee roll. No model deviation.
- `DROP_ALL_P`: bank-0 `drop_any` (`src/drop0.asm`), after the kind's drop row: `rng_mod(25) < 2` (8 % exact), food
  `rnd(5)`. EF_RESPAWN bodies (and so every summon) and the lair boss never roll; a same-kind escort of a boss does (the sim's
  `m.boss` excludes it; negligible).
- C1: `tp_safe` (HOT_COPY `src/tele_hot.asm`) — pass 1 takes rooms whose LP record header is exactly `LR_VISITED` (visited, 0
  banked residents); no such room with a free spot → the old rule. "≥ 6 cols from any body" holds trivially (no body).
- C2 / C3: `items_ovl.asm` `ig_grp`: scroll type `max(0, rnd(8) − 1) >> 1`; on D2 the LAST scroll is forced to Teleport if
  none came before (the sim forces `scr[0]`: the same distribution for i.i.d. types). A dropped (unplaceable) scroll can take
  the guarantee with it (rare; the sim has no placement).
- M1: D4 / D6 / D7 25, **D5 kept 24** (manager: keep the cap). `LP_N_MAX` 24 → 25: the split places count − 2 units (boss +
  escort in the lair), so 25 leaves 23 for the 8 × 3 = 24 slots of the smallest room set; 26 would also fit (24 = 24, zero
  slack) but is not taken. tools/levelcheck.py LP waits 14.5 % → 15.05 % (gate 15 % → 16 %).
- Firebolt r1 bonus −1 is signed in `ab_rank` (`$FF`); a 0 roll hurts 1 (deal_hit), and the sim now floors a spell's final
  damage at 1 the same way (`strike`) and reads RK_BONUS signed.


## 9. FOOD-7 (user ruling 2026-11-18, playtest of package 5: "a little less food")

`FOOD_PERIOD` 8 -> 7 (`src/item_defs.asm:245`); the 8 % kill drop, start 100 and everything else are unchanged. 0 B. Sim: `tools/balance_food7.json`
= `balance_pkg5_final.json` with `FOOD_BURN` 7 (`--ld-pkg4 --overrides tools/balance_food7.json --set param.PICKUP=0.75`, 10 000 runs, seed 1, `--jobs 4`).
Starving = died HUNGRY with an empty bag, as a share of deaths (the §8 definition).

| Period | average W / M | E1 W / M | largest depth share (avg W / M) | starving deaths (avg W / M) | HUNGRY + empty bag before D5 (avg W / M) | food median D3 / D6 entry (avg W) |
|---|---|---|---|---|---|---|
| 8 (§8) | 16.4 / 16.7 | 37.6 / 44.0 | D4 46 % / D3 41 % | 8 / 15 % (12 % mean) | 11 / 15 % | 56 / 52 |
| 7 | 9.0 / 11.1 | 24.2 / 29.2 | D4 38 % / D3 51 % | 22 / 36 % (29 % mean) | 31 / 36 % | 55 / 50 |

Interpretation: one turn of period is a cliff, not a nudge. The median food level barely moves, but the tail with an empty bag at HUNGRY grows 2.5x and
costs 7-12 pts of average win rate and 12-15 pts of E1, so period 7 leaves the average band (15-25) and the E1 W band (30-40 had E1 M above it; now E1 M is in it).
If the player feels food is still too plentiful, trim it through the floor food count or the drop rate rather than the period. (The E1 M row of §8 reads 43.6 there, 44.0 on re-run.)

**FOOD-7B (user ruling 2026-11-18, second playtest: "still too much food").** Period stays 7 and the 8 % drop stays; floor food per level 3-4 -> 2-3
(`ig_grps` food row `n_lo` 3 -> 2, `src/items_ovl.asm`; `FOOD_N` [2, 3] in `tools/balance_food7.json`; `tools/items_model.py` `FOOD_N_MIN` 2). Same sim setup.
The playtest outranks the sim; the numbers are reported, not a gate.

| Config | average W / M | E1 W / M | largest depth share (avg W / M) | starving deaths (avg W / M) | HUNGRY + empty bag before D5 (avg W / M) | food median D3 / D6 entry (avg W) |
|---|---|---|---|---|---|---|
| period 7 + floor 2-3 | 3.9 / 5.8 | 12.5 / 15.6 | D3 35 % / D3 64 % | 38 / 58 % | 54 / 60 % | 51 / 48 |

Interpretation: the sim bot cannot live on this food budget (starvation is now the main killer, about half of all deaths), so it is far below every target band; it is a
bot that eats only between rooms, and the playtest says a human still finds food plentiful, so treat the sim as a lower bound of how much slack the budget has left.
