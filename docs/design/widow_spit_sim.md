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
