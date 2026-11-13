# AWARE1: monsters that notice you (D-AI1d half 2)

**Status: REJECTED after playtest (user 2026-11-13: makes the game much easier, monsters can be avoided completely).** Built on feat/aware, not merged. FOLLOW_GAP 6 shipped separately and stays.
Today every non-held, non-feared monster on the hero's storey chases (prototype §6.4, game.md §9.2);
non-climbers on the other storey patrol; ASLEEP exists only as a status (Sleep scroll, D0 Goblin).

## 1. Model: one 4-bit field, three states

`AWR` = the **high nibble of `ST_T2`** (unused since POIS1, memory-map `$B3F0`); no new RAM per slot.
`0` = today's behaviour, so every path that clears the slot (summons, waves, followers, tests) is aware;
only the resident spawn writes `$F`.

| AWR | State | Meaning |
|---|---|---|
| `0` | **CHASING** | perceives the hero now: today's AI, unchanged |
| `1..11` | **ALERT** | aware, lost sight for AWR acting turns: today's AI (still seeks, follows, closes in) |
| `$F` | **UNAWARE** | idle / pacing (§2); never seeks, follows, shoots or casts |

**Awareness step** = new step 2b of `ai_monster`: after 1 yield/anti-cork and 2 period gate, before 3
melee. Held / FEAR / CONFUSED-replaced turns never reach it (as for the ranged hook); bosses skip it.
- **UNAWARE:** sees the hero → `AWR = 0`, face him, **turn consumed** (no step, no attack). Else pace (§2).
- **Aware:** sees him → `AWR = 0`; else `AWR += 1`; at `LOSE_T` = **12** → `$F` (forgets, paces where
  it stands). Then the normal rules run.
- **Sees** (first fail wins): (a) same storey: its storey = `PL_SEG` bit 7 (mid-climb counts on the end he
  is heading to, ai_seek2.md §2.2); (b) range, `gap` = empty cols between the boxes (as for shots): UNAWARE
  needs `gap < SIGHT_F` **8** with the hero on its facing side, `gap < SIGHT_B` **2** behind (flyers 8 all
  round); aware: no limit; (c) clear: no `TF_SOLID` in the standing row `9s+7` over the gap cols (the
  Vampire cut scan, same routine). Pits and bodies do not block sight.
- **Noise** sets every UNAWARE body of the room to `AWR = 1`: any hero attack or spell (melee, bump, Power
  Strike, Whirlwind, ammo, all five spells), hit or miss; any monster attack on the hero; an ALARM plate.
  Applied **after** the hero's action resolves (Whirlwind / Lightning get the sneak roll on every unaware
  target). Not noise: walking, jumping, climbing, eating, Sleep / Teleport / Identify scrolls.
- **Wake by harm:** any HP loss, or a hero-applied FEAR / CONFUSE → `AWR = 0`. No ally alert beyond noise
  (≤ 4 monsters a room; combat already wakes the room). Losing him: 12 acting turns with the hero on the
  other storey or behind a block (non-climbers patrol, climbers keep seeking), or the room change (§3).

## 2. Unaware behaviour and the sneak rule

- **Spawn facing** unchanged (toward the hero; the Python == Z80 placement reference stays). Tries 1–4 keep
  gap ≥ 8, outside front sight; tries 5–8 (gap 5–7) may spot him on the first monster phase (accepted).
- **Pacing (walkers, Ghosts):** acts only on turns with `(TURN_COUNTER + slot) & 3 == 0`, else waits;
  `((TURN_COUNTER >> 2) + slot) & 1` = 0 → one patrol step in the facing direction (blocked / ledge / lip →
  none), 1 → turn around. Net drift 0, facing flips every 8 turns: sneak windows. No RNG, never climbs,
  flyers stay in band. **Bats** keep their wander (flyer rule 3). Yield / anti-cork still run first.
- **Sneak:** a hero attack on an UNAWARE target treats its eva as **0** (the FROZEN / ASLEEP rule, §6.4;
  one OR in the hit roll). The hit wakes it: one roll per monster. No damage bonus (§5).
- **Always aware (skip the step):** lair bosses (G2 guard is their awareness, `GUARD_R` 31), the Archmage,
  summons (Archmage, Bone Caller, Rabbit Rat breed), ALARM / idle-wave bodies, followers. Every other kind,
  undead included, uses the rule: the population is the sneak game's content.

## 3. Interactions

- **Following (prototype §3.7 rule 1):** candidates also need `AWR ≠ $F`. **Recommend FOLLOW_GAP 6, shipped
  with this:** awareness removes the far idlers 4 guarded against (game.md §9.4.8 (d)3 named this pair);
  the 2-per-exit and §9.3 caps, descent, climbing past non-climbers and the 12-turn forget keep escape real.
- **AI-SEEK2:** UNAWARE never reaches `.seek`; ALERT climbers seek ≤ 11 turns (about one ladder route).
- **ROOM-MEM:** a parked slot keeps `AWR` frozen with its statuses (A→B→A: hunters wait, idlers idle). A
  re-placed record unit (older room) returns UNAWARE: the record needs no bit. Followers keep `AWR`.
- **Spawns:** FRESH, record re-placements, §9.5 trickle entries, lair escort → `$F`. ALARM: noise for the
  room, the wave arrives at `0`; idle wave (off) → `0`. **D0 Goblin** → `0`: its scripted ASLEEP and mercy
  rules are unchanged.
- **Ranged / spitters (RANGED-SPEC hook, Widow, BOSS-RANGED):** only aware bodies reach the hook; an unaware
  Archer never fires; once aware, full range (a Sniper spotting at gap 7 backs into range). Cooldown
  untouched. Bone Caller summons and the Vampire close-distance rule run only when aware.
- **Mage spells:** every cast is noise; Firebolt (r12) / Lightning (r28) from beyond sight: sneak roll.
- **Statuses:** Sleep scroll does not wake; a sleeper skips the step (cannot notice); HP loss wakes. FEAR
  scroll → `0`. CONFUSE: the random step replaces the action 1 in 2, else the step runs (it paces).
  FROZEN / STUNNED: held, no step. **Archmage:** always aware, §9.9 unchanged.
- **Danger music (game.md §3.7):** UNAWARE bodies are not pressing → excluded from the W sum.

## 4. Cost

- **RAM:** 0 B per slot (engineer verifies `st_step`'s WEAK decrement keeps the hi nibble and spawn /
  `lp_*` clear `ST_T2`). +1 B test hook `AWR_ALL` (§6).
- **Code (estimate):** step, sight test (reuses the gap and cut-scan routines), pacing, noise loop,
  lose-track ≈ **260–320 B in `B0_CODE2`** behind the existing far-call. Banked call sites ≈ 4–8 B each:
  `ai_monster` 2b (bank 3), damage wake (beside the PROVOKED set), hit-roll OR, `follow_select` (bank 7),
  `lp_place` init, noise after hero / monster attacks, ALARM, W filter → **≈ 35–50 B in full banks**;
  reclaim per mem_reclaim.md if short (no feature cuts).
- **T (input tick only):** UNAWARE ≤ **0.7k T** per acting body, aware ≤ 0.25k, noise ≤ 0.3k per event.
  Worst 4 unaware ≈ 2.8k, but an unaware body skips walker / seek / ranged code (`seek_col` alone 1.4k):
  the typical turn gets **cheaper**. budget.py: no worst-tick regression.

## 5. Balance

- **Easier early game** (fewer attackers on entry, one eva-0 opener per monster, rooms crossable without a
  fight: slightly less XP and fewer drops); **harder fleeing** with FOLLOW_GAP 6. Expected: win rate **+3 to
  +8 pp** at D1–D3 (average / cautious), ~0 at D6–D8; Mage gains more than Warrior (ranged openers). Gate:
  bal1_final.md per-depth bands hold; overall > +5 pp → drop the sneak roll first, keep awareness.
- **`tools/balance_sim.py`:** (1) `--aware on|off`: monsters start UNAWARE, `AWARE_SPOT_P` 0.15 spotted on
  entry; the first hero attack per unaware monster uses eva 0 and wakes the room; (2) **room-exit following**
  (new): a walk-out `retreat` (not Teleport) brings ≤ 2 aware monsters with gap ≤ `FOLLOW_GAP` into the next
  fight at their hp, `--follow-gap 4|6`, gaps from `setup_geometry`; (3) rooms left ≥ 3 rooms ago return
  UNAWARE; (4) report sneak openers, followers per escape, escape success. Grid aware × gap, both heroes,
  three policies, 2000 runs a cell.

## 6. Tests

New `tests/aware.py` (seeded ZRCP, `AWR_ALL` = 0): **AW1** spawn states (FRESH / record / trickle `$F`;
follower, wave, summon, boss, Archmage, D0 Goblin `0`). **AW2** facing hero: gap 8 stays `$F` 10 turns; gap 7
→ faces, no move, no attack, `0`. **AW3** facing away: gap 2 `$F`, gap 1 notices; a flyer at gap 7 notices.
**AW4** mid-room block at gap 3 → `$F`; other storey at gap 0 → `$F`. **AW5** pacing: 16 turns, x ±1,
facing flips on schedule. **AW6** noise: melee hit / miss, each spell, ammo, ALARM → room `1`; walking and
Sleep scroll do not. **AW7** sneak: a seeded roll that misses vs eva hits `$F`, misses once aware; Whirlwind
on 2. **AW8** lose track: non-climber `$F` on the 12th acting turn; hero back at turn 11 → `0`. **AW9** follow:
`$F` at gap 1 stays; aware at `FOLLOW_GAP` follows, +1 does not. **AW10** ROOM-MEM: A→B→A keeps per body;
A→B→C→A → `$F`. **AW11** FEAR scroll → `0`; Sleep keeps `$F`, sleeper never notices; HP loss wakes.
**AW12** unaware Archer, gap 5, clear: never shoots; aware fires. **AW13** step ≤ 0.7k T (budget.py).
**AW14** `AWR_ALL` = 1 → `tests/ai_equiv.py` A/B vs pre-AWARE1 = 0 mismatches.

**Affected:** `tests/game_lib.py` sets `AWR_ALL` = 1 by default (spawn writes `0`), so `spawn`, `lp`,
`roommem`, `ai_seek2`, `ladder_jam`, `ranged`, `vbat`, `widow`, `trickle`, `boss`, `budget`, `tick_prof`
and the goldens stay unchanged. `pt_bot` / `playthrough` run with 0 and are re-baselined (routes, win
stats, any first-room goldens they capture). `tests/tut0*.py` unaffected.

## 7. Doc impacts (not edited here)

game.md §9.2 (AWARE paragraph, step 2b), §6.4 (eva 0), §9.4.2 / §9.4.3 (spawn `$F`, ROOM-MEM keeps
`AWR`), §9.5 (trickle `$F`, waves `0`), ALARM trap row (noise), §3.7 (W); prototype §3.7 rule 1 and §6.4
walker / flyer rule 0; ai_seek2.md §2 (UNAWARE does not seek); memory-map.md (`ST_T2` hi nibble,
`AWR_ALL`, B0_CODE2); plan.md (AWARE1 after UX-POLISH); balance_sim.py (§5).

## 8. Open questions (defaults in bold)

1. Ship together with FOLLOW_GAP 6 (one balance run, one playtest)? **Yes** / keep 4.
2. Sneak bonus: **eva 0 on the opening blow** / none / eva 0 + 1 damage.
3. Noise scope: **whole room** / same storey only (+~15 B).
4. Notice cue: **turn to face only** / plus `THE <NAME> SPOTS YOU!` (~20 B, log spam) / 1-tick attr flash.
5. `LOSE_T` **12**; sight **8 front / 2 behind, flyers 8 all round**.
6. Undead always aware for theme? **No** (it empties the sneak game at D3–D8).
