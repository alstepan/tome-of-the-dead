# BAL-1 FINAL — rebalance after the feature batch

Status: PROPOSAL for the user. No game table is changed by this document; the packages are
`tools/balance_pkgFINAL_{A,B,C}.json` (each = `balance_pkgW3.json` + the extra cells listed below).
Simulator: `tools/balance_sim.py` (selftest passes). 10,000 games per cell, seeds 1 and 2 pooled
(n = 20,000 per cell, Wilson 95 % CI about +-0.7 pp), `--jobs 8`; one 6-cell sweep takes ~75 s.

## 0. Simulator verification and fixes (done before the sweep)

Checked against the build: FEAR-CAST (feared Mage: no spell and no staff melee; feared Warrior: no
melee / Power Strike / Whirlwind; daggers, arrows, items allowed; FEAR 3 turns 1 in 3 from Necromancer
and Bone Caller, Archmage Death Bolt 1 in 3), the D8 ending (Archmage -> seal -> Tome 5 hits + 1 HP
aura within 6 cols -> exit gate -> win), TRAP2 re-firing with ALARM capped by LP_RESPAWNS, GEAR1 gates /
q / random Enchant, golden-boss XP and Archmage hp 60/67: all already right. Mismatches fixed
(commit 0e0d378):

1. **Bone Caller summon had no cap** (the sim never counted live summons): a Bone Caller made a new
   body every 8 turns, 20+ Ghosts per fight on D6/D7, which produced STALLs and a huge Ghost death
   share. Now capped at the built `BC_LIVE` = 1. This alone moved W3 from W22 / M28 to W32 / M51.
2. Archmage summon: max live Skeleton and cooldown now read from the symbols (`AM_LIVE` 1, `AM_SUM_CD` 6;
   the sim allowed 2); a blink no longer resets the summon counter (arch6.asm); the summon is not limited
   by a room cap in the sim (the lair escort stays alive and is fought together with it).
3. **Boss-retreat loop (bot):** a hungry hero with an empty bag cannot rest, retreated at turn 1 of every
   lair fight 40 times and was counted as a STALL loss (up to 49 % of cautious Warrior deaths). The bot now
   commits to the fight when resting could not lift it above the retreat line.
4. New params `NECRO_FEAR_N/T`, `ARCH_FEAR_N` (defaults = rd_tab), report line "top depth x killer".

## 1. Targets and the result in one table (average policy)

Targets: average 35-45 % for both heroes, |W - M| <= 5 pp, reckless 10-20 %, cautious 60-70 % (if
reachable), no mass deaths before D5.

| Package | W avg | M avg | gap | W cautious | M cautious | W reckless | M reckless |
|---|---|---|---|---|---|---|---|
| Baseline-as-built (current tables) | 0.2 | 80.4 | -80 | 1.0 | 82.8 | 0.0 | 51.3 |
| W3 (option A + W3) | 31.6 | 51.0 | -19.4 | 41.5 | 48.8 | 12.8 | 20.6 |
| FINAL A | 41.3 | 40.3 | +1.0 | 48.9 | 39.7 | 21.2 | 13.2 |
| **FINAL B (recommended)** | **41.4** | **43.4** | **-2.0** | 46.9 | 41.8 | 18.6 | 15.5 |
| FINAL C | 39.8 | 43.1 | -3.3 | 46.1 | 41.8 | 17.6 | 15.1 |

Baseline-as-built: the Warrior cannot beat the D4 Ogre (PHYS R, 85 % of Warrior deaths) and the Mage
walks the game (Firebolt r12): this is the original BAL-1 complaint, now measured with the full rules.
W3 alone over-corrects for the Mage and leaves the Warrior at the Ogre.

## 2. Packages

All three include W3 (option A + Ogre PHYS N + Power Strike MP 2/3/4 + Firebolt MP 4/6/10 bonus 0/2/4)
and the same **Mage lever**: Firebolt rank I 4 MP 1d6 -> **5 MP 1d8** (the Mage lives on its rank-1
spells; rank II/III cells barely move the result, tested). They differ in the Warrior lever.

Where the cells live (all `src/`, table data only, no code, 0 bytes):
- `ab_rank` in `src/combat_data3.asm`, macro `RANK mp, range, die, bonus, bounces, effect`. W3 values,
  after option A, are the current target; the Firebolt rank-I row is the first `RANK` under
  `; Firebolt:` -> `mp`=col 1, `die`=col 3. Power Strike rows are the three `RANK` lines under
  `; Power Strike` (col 1 = MP).
- Ogre Warlord = column 16 of the `KROW` rows in `src/main.asm` (kind_tab, K_OGRE): hp row line 640
  (`40`), atk line 641 (`5`), die line 643 (`10`), bonus line 644 (`2`).
- The info-line strings that print MP / dice (`FIREBOLT I 5MP ...`) and `tests/combat_tables.py` follow
  the table (spell, ability, proj tests, lcastf can only get cheaper: dearer cast, same code).

### FINAL A — "cheap Power Strike III"
| Knob | old -> new |
|---|---|
| Power Strike III MP (`ab_rank` 3rd Power row, col `mp`) | 4 -> **3** (PS 2/3/3) |
| Firebolt I (`ab_rank`, 1st Firebolt row) | 4 MP 1d6 -> **5 MP 1d8** |

Results (avg, pooled): W 41.3 [40.6,41.9] / M 40.3 [39.7,41.0], gap +1.0. Reckless W 21.2 (just over 20),
M 13.2. Survival at entry D2..D8: W 100 99 97 **69** 63 55 48; M 100 100 91 75 74 72 52.
Top killers W: Ogre 44 %, Ghost 14 %, Archmage 8 %; M: Ghost 39 %, Ogre 21 %, Skeleton 8 %.
Feel: the Warrior can afford Power Strike III every fight and chains it, but the D4 Ogre is still a wall
(31 pp of all Warriors die at D4: a mass death before D5, outside the "sane" rule). Mage: Firebolt is a
5 MP decision, so Spark carries the early game and Firebolt is saved for what Spark cannot do.

### FINAL B — "tamer Ogre" (RECOMMENDED)
| Knob | old -> new |
|---|---|
| Ogre Warlord hp (kind_tab) | 40 -> **36** |
| Ogre Warlord atk | 5 -> **4** |
| Ogre Warlord dmg bonus | +2 -> **+1** (1d10+1) |
| Firebolt I | 4 MP 1d6 -> **5 MP 1d8** |
| Power Strike | stays 2/3/4 (user's W3 choice kept) |

Results: W 41.4 [40.7,42.1] / M 43.4 [42.7,44.1], gap -2.0. Cautious W 46.9 / M 41.8; reckless W 18.6 / M 15.5
(both inside 10-20). Survival D2..D8: W 100 99 97 **77** 70 59 49; M 100 100 91 81 80 78 56.
Top killers W: Ogre 29 %, Ghost 19 %, Archmage 9 %, Death Knight 7 %; M: Ghost 44 %, Ogre 11 %, Skeleton 9 %,
Vampire Lord 7 %.
Feel: Warrior - the D4 Ogre is a real fight he wins about 3 times in 4 (was nearly never), and the run
then gets steadily harder through the Ghosts of D6-D7, the Death Knight and the Archmage. Mage - spells
are slightly dearer, so he plans mana per room; he still blasts most rooms, and the Ghost (Spark reflected,
Frost half, Drain nothing) is the thing that ends his runs on D7.

### FINAL C — "even tamer Ogre, atk 5"
Ogre hp 40 -> 36, bonus +2 -> +1 (atk stays 5), Firebolt I 5 MP 1d8. W 39.8 / M 43.1, gap -3.3; cautious 46.1 / 41.8;
reckless 17.6 / 15.1; survival W 100 99 97 75 67 57 48, M 100 100 91 81 80 77 56. Same feel as B with
the Ogre hitting a little more often. B and C are within noise of each other; pick C if the Ogre's to-hit
should not change (2 cells instead of 3).

## 3. Tuning round for B (4,000 games, seed 1, one knob on the first B = hp 36 / atk 4 / bonus 0)
That B had reckless W 21.3. Restoring atk to 5 gave 19.5, hp 38 + atk 5 gave 18.6, bonus 0 -> +1 gave 17.9
(average W 42.4, M 43.0) -> adopted: B now has bonus +1, and 10k x 2 seeds shows reckless W 18.6.

## 4. Cautious: honest result
Cautious is 47 / 42 % against the 60-70 % target (gap 15-25 pp), unreachable by table changes. Findings:
- With the fixed bot, STALLs are gone; the cautious policy is barely better than average (rests at 70 % HP
  instead of 50 %; boss retreat at 40 % instead of 25 %), so the cautious/average spread in the sim is
  only +5 pp (W) / -1.6 pp (M). The Mage even does slightly worse cautious, because he dies at D3
  (Vampire Lord) while kiting and retreating from a boss that heals by biting.
- Biggest blocker: **Ghosts** (27 % of cautious Warrior deaths, 43 % of cautious Mage deaths, D6-D7), then
  the D3 Vampire Lord for the Mage (12 %). Making cautious 60+ would need the Ghost easier for both
  (Ghost PHYS R -> N alone gives W +15 / M +24 pp, tested) which then breaks the average gap and the
  Mage's early game (needs a Spark nerf that kills the Mage at D1-D3). Not recommended: keep average 40.

## 5. Table-only vs code
All of A, B, C are table-only (data cells in `combat_data3.asm` and `main.asm`'s `KROW`), 0 bytes,
no frame-tick change. Code-immediate knobs tested and NOT used: Warrior level HP 4 -> 5 (+1 pp),
Mage level MP 2 -> 3 (+24 pp), Mage regen period 6 -> 5 (+16 pp) (both measured on W3 before the Bone Caller cap fix; direction only). Ghost PHYS N (table) works but see 4.

## 6. Recommendation
**FINAL B**, confidence medium-high for the *relative* result (Warrior and Mage within a few pp, in band,
no early mass death) and medium for the absolute 41-43 % (sim is a tuning tool, not truth). After applying:
rebaseline `combat_tables`, spell/ability/proj tests, `lcastf` (dearer cast can only lower it), and run the
emulator spot-check of section 7. If the playtest says the Mage is still too strong, the next single
knob is Spark I bonus +1 -> 0 (about -17 pp on W3, early-game cost: check D1-D3 survival first); if the
Warrior is too weak, Power Strike III 4 -> 3 MP (+10 pp, package A).

## 7. Blind spots of the simulator
Two storeys and ladders (monsters arriving out of line are a flat delay), jumps over pits / low bodies,
real room geometry (1-D gaps, walls and kiting depth are random draws), trap placement (traps sit in
rooms; TELEPORT is a flat delay), the **Bone Caller / Pharaoh summon room cap (Sigma) is not modelled** (only
the live-summon count BC_LIVE / AM_LIVE; the Pharaoh summon is not modelled at all), door-closing tactics,
real AI pathing, RNG interleave and player skill (the bot is a fixed rule set; cautious vs average differ
little). Spot-check in the emulator per bal1_spells.md 4.5: D3 Vampire Lord, D4 Ogre, D7 Ghost room,
D8 lair with the Skeleton summons (jump legality at the lair arrival, the Ogre closing the gap, the Tome fight geometry).
