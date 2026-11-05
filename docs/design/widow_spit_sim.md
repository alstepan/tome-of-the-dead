# Black Widow poison spit: simulator what-if (2026-11-05)

Question: should the Black Widow (Spider tier, D4+ rosters, bite POISON 24 + ACID) get a ranged poison spit?
Numbers only; no recommendation here.

## Method
- `tools/balance_sim.py` params `WIDOW_SPIT` (0 = the build, default), `WIDOW_POISON` (P), `WIDOW_PERIOD` (N). Off by default, so
  no existing result changes. On: the Widow gets the Spider Queen's `GOLD_ROWS` spit row (`ranged_model`): range 6 (gap < 6), keeps
  walking between shots, d20 vs EVA, 1d2 minus DEF (min 1), NO golden +1, a hit always adds POISON P (cap 30, Silk Cloak immune).
  Period N = a shot every Nth turn (row cooldown N-1, as for the Queen's 3). Bite stays as is.
- Driver `tools/widow_spit_sim.py`: 10,000 games per cell, average policy, seed 1 (same seed per variant, but RNG streams diverge
  after the first spit, so pairing is weak), image built with `tools/build.sh -DDEBUG_KIT=0`. 95% CI about +-1.0 pp.
- "HP per Widow fight" = hero HP at fight start minus at end (incl. poison ticks, other monsters in the same room, potions not
  netted out) over fights that contain a live Widow; ~3 such fights per run in every cell.

## Results (average policy, 10,000 runs per cell)
| variant | hero | win % [95% CI] | deaths % of runs D4 / D5 / D6 | reach D6 % | HP / Widow fight | killed by Widow % of runs |
|---|---|---|---|---|---|---|
| baseline | W | 41.1 [40.1,42.1] | 17.1 / 9.8 / 10.0 | 68.5 | 1.54 | 0.6 |
| P12 N3 | W | 36.9 [35.9,37.8] | 18.3 / 11.6 / 10.3 | 64.5 | 2.68 | 2.5 |
| P12 N4 | W | 37.0 [36.1,38.0] | 18.7 / 11.4 / 10.4 | 64.3 | 2.64 | 2.3 |
| P6 N3 | W | 37.7 [36.7,38.6] | 18.0 / 10.9 / 10.7 | 65.6 | 2.66 | 2.3 |
| P6 N4 | W | 37.9 [37.0,38.9] | 18.3 / 11.0 / 10.3 | 65.3 | 2.63 | 2.2 |
| baseline | M | 40.1 [39.1,41.0] | 8.6 / 0.9 / 2.7 | 78.1 | 0.27 | 0.4 |
| P12 N3 | M | 40.3 [39.4,41.3] | 8.6 / 1.0 / 2.8 | 77.9 | 0.70 | 0.5 |
| P12 N4 | M | 40.0 [39.1,41.0] | 8.6 / 1.0 / 2.8 | 77.8 | 0.69 | 0.5 |
| P6 N3 | M | 40.6 [39.7,41.6] | 8.5 / 1.0 / 2.5 | 77.9 | 0.65 | 0.5 |
| P6 N4 | M | 40.4 [39.5,41.4] | 8.5 / 1.0 / 2.5 | 77.8 | 0.64 | 0.5 |

Deaths are shares of all runs (not of deaths). Widows appear from D4 (Spider tier), so D4 and D5 deaths both include them; the
D4 column is dominated by other killers.

## Reading
- Warrior: the spit costs 3.2 to 4.2 pp win rate and 3 to 4 pp reach-D6; HP per Widow fight rises from 1.5 to about 2.65. Mage: no
  measurable change in win rate (+-0.5 pp, inside noise), HP per Widow fight 0.27 to about 0.65 (he kills it at range first).
- The four variants are indistinguishable (spread <= 1 pp, inside CI): P12 vs P6 and N3 vs N4 barely matter next to having the spit at all.
- Widow-attributed deaths stay small (W 0.6 to 2.5 % of runs); the Warrior's loss is attrition into later levels, not Widow kills.

## Caveat: `tests/balance_sim_selftest.py` test_monotone (BSIM1)
Run once on this tree: still FAILS, identically (Mage 0.378 / 0.386 / 0.242 at HP +0/+10/+30, 500 runs, SE about 2 pp; the +30 drop is
real, not noise; cause not diagnosed). It exercises `HP_BONUS`, which this comparison never sets; the baseline here (M 40.1 %) is
consistent with its HP+0 point. The spit effect (W -3 to -4 pp, M ~0) is far outside the CI, so the artefact is unlikely to flip
the sign, but a bot-policy interaction that only shows at high HP cannot be excluded from these runs.

## Decision 2026-11-05: spit = P6 N4, plus compensation search
Driver `tools/widow_comp_sim.py` (same method: 10,000 runs, average policy, seed 1, spit P6 N4 in every row but the first).
| variant | W win % | M win % | W reach D6 % | W D5 deaths % of runs |
|---|---|---|---|---|
| baseline (no spit) | 41.1 | 40.1 | 68.5 | 9.8 |
| spit P6 N4 | 37.9 | 40.4 | 65.3 | 11.0 |
| + Widow bite poison 18 | 37.9 | 40.5 | 65.6 | 11.1 |
| + Widow bite poison 12 | 38.5 | 40.6 | 66.3 | 11.0 |
| + Widow hp 9 / hp 8 | 37.2 / 37.3 | 40.9 / 40.8 | 65.0 / 65.0 | 11.9 / 12.0 |
| + Widow atk 3 | 38.2 | 40.5 | 65.9 | 10.9 |
| + bite 12 + atk 3 + hp 8 (all stacked) | 38.4 | 40.9 | 66.8 | 11.3 |
| + Warrior start HP 25 | 39.3 | 40.4 | 67.6 | 11.9 |
| + Warrior start HP 26 (+2) | 40.4 | 40.4 | 68.3 | 12.1 |
| + Warrior HP per level 5 (+1) | 40.9 | 40.4 | 69.0 | 11.7 |

Reading: no Widow-specific cut recovers the Warrior (even all three stacked: 38.4, about +0.5 pp): the loss is attrition into
later levels, which a weaker Widow does not undo (CI about +-1 pp, so single steps of 0.3 to 0.6 pp are noise). Only Warrior-global HP
reaches 40 to 42: start HP +2 (40.4) or +1 HP per level-up (40.9); start HP +1 gives 39.3, just short. The Mage is unmoved (40.1
to 40.9) in every row. Not modelled: Widow ACID (1 in 4 -> 1 in 8), so that candidate is untested. W_HP0 / W_LVL_HP are
immediates in hero_st_init / xp7 (marked CODE in `PARAMS`), so both winning options are 1 to 2 changed immediates, not table cells; I did not check whether
a table-only HP route exists. Smallest hitting 40 to 42 with M unchanged: +1 HP per level (40.9) over start HP +2 (40.4, at the edge of the band).
