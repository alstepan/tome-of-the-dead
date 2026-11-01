# BAL-1 — Spell balance and win probability (designer, 2026-10-31)

Status: PROPOSAL (paper analysis; no sim, no emulator). Trigger: user playtest 2026-10-31,
"Firebolt seems cheating ... I can walk through the game to the end". Sources: game.md §4.0, §5
(rank table), §6.0–6.1, §9.1 (roster + resistances), §9.4, §9.6, §9.9, §10;
`src/combat_data3.asm` (`kx_tab`, `ab_rank`); `src/proj3.asm` (staff bonus, reversal rules).
On acceptance, the numbers move into game.md §5 / §6.1 / §9.1 and this file is archived.

Conventions: avg 1d4 2.5 · 1d6 3.5 · 1d8 4.5 · 1d10 5.5. Spells always hit and ignore DEF. The
Rune/Bone staff adds +1/+2 to **every direct strike** (bounce and pierce re-hits included, not
the burst), **before** the resist multiplier, so it is doubled on W. Monster hp = row + (d − 1);
golden boss = 2 × (row + d − 1) + 6. Assumed kit: D1–D3 rank 1, no staff; D4 rank 2, no staff
(the Bone Staff drops from the Ogre); D5–D6 rank 2 + Bone; D7–D8 rank 3 + Bone. Auto-downcast
(§5) means the player pays the **highest affordable** rank, so overkill is the norm.

## 1. Diagnosis

### 1.1 Per-cast numbers today (avg direct damage at +0 / +1 / +2 staff; dmg per MP at +0)

| Spell | R1 | R2 | R3 | Range | Extra | Risk to caster |
|---|---|---|---|---|---|---|
| Spark | 2 MP · 3.5/4.5/5.5 · 1.75 | 4 · 6.5/7.5/8.5 · 1.63 | 6 · 8.5/9.5/10.5 · 1.42 | 6 / 8 / 8 | confuse | none (no bounce) |
| **Firebolt** | 3 · **6.5**/7.5/8.5 · **2.17** | 5 · 9.5/10.5/11.5 · 1.90 | 8 · 12.5/13.5/14.5 · 1.56 | **12** | burst 1d4/1d6 on neighbours | burst at point-blank only (R1–R2) |
| Frost | 3 · 3.5/4.5/5.5 · 1.17 | 5 · 4.5/5.5/6.5 · 0.90 | 8 · 6.5/7.5/8.5 · 0.81 | 12 | freeze 2–4, 1–2 bounces | own bounce freezes him 1 turn |
| Drain | 3 · 4.5/5.5/6.5 · 1.50 | 5 · 6.5/7.5/8.5 · 1.30 | 8 · 9.5/10.5/11.5 · 1.19 | **5** / 8 / 8 | heal = dmg | none |
| Lightning | 5 · 7.5/8.5/9.5 · 1.50 | 8 · 10.5/11.5/12.5 · 1.31 | 12 · 12.5/13.5/14.5 · 1.04 | 28 | pierce, 2–3 bounces | **r28 + bounce: hits the caster whenever the wall is < 14 cols ahead (most rooms)** |

### 1.2 Coverage: share of each depth's 4 roster kinds (+ boss) a spell can damage (N/W/R)

| Depth | roster | Spark | Firebolt | Frost | Drain | Lightning |
|---|---|---|---|---|---|---|
| D1 | Rat Bat Slime Goblin · King | 4/4 · ✓ | 4/4 (Slime W) · ✓ | 4/4 · ✓ | 4/4 · ✓ | — |
| D2 | Goblin Spider Bat Rat · Queen | 4/4 · ✓ | 4/4 (Spider W) · **W** | 4/4 · ✓ | 4/4 · ✓ | — |
| D3 | Skel Vamp Ghost Bat · Lord | 3/4 (Ghost X) · ✓ | 4/4 (Vamp W) · **W** | **1/4 · I** | **1/4 · I** | — |
| D4 | Orc Rat Spider Archer · Ogre | 4/4 · **W** | 4/4 (Orc R) · ✓ | 3/4 · R | 3/4 · ✓ | 4/4 · W |
| D5 | Mummy Skel Archer Spider · Pharaoh | 4/4 · ✓ | 4/4 (2 W) · **W** | **1/4 · I** | **1/4 · I** | 4/4 · ✓ |
| D6 | Vamp Ghost Necro Orc · H.Necro | 3/4 · ✓ | 4/4 (Vamp W, Orc R) · ✓ | 2/4 · R | **1/4 · I** | 3/4 · ✓ |
| D7 | Orc Necro Necro Ghost · DK | 3/4 · **W** | 4/4 (Orc R) · **X** | 3/4 · I | **1/4 · I** | 3/4 · W |
| D8 | Necro Skel Ghost Vamp · Archmage | 3/4 · X | 4/4 (Vamp W) · ✓ | **1/4 · X** | **0/4 · I** | 3/4 · X |

FIRE has **one** blocker in the whole game (the Death Knight) and W on the D2/D3/D5 boss lines.
Every other type is shut out somewhere big: COLD/DRAIN by all undead (D3, D5, D8 nearly whole
levels), SHOCK by Ghosts (reflected back at the caster) and the Archmage.

### 1.3 Average MP per kill over the roster (casts × cost; "—" = ≥ half the roster I/X)

| Depth (kit) | Spark | Firebolt | Frost | Drain | Lightning |
|---|---|---|---|---|---|
| D1 (R1) | 3.0 | 3.0 | 4.5 | 4.5 | — |
| D2 (R1) | 4.0 | **3.75** | 6.8 | 4.5 | — |
| D3 (R1) | 6.7 (¾) | **5.3** | — | — | — |
| D4 (R2) | **8.0** | 10.0 | 15 (¾) | 10 (¾) | 13 (if known) |
| D5 (R2+2) | 9.0 | **7.5** (Mummy/Spider one-shot) | — | — | 12 |
| D6 (R2+2) | 10.7 (¾) | 11.3 | — | — | 16 (¾) |
| D7 (R3+2) | **12** (¾) | 16 | 35 (¾) | — | 24 (¾) |
| D8 (R3+2) | **10** (¾) | 14 | — | — | 20 (¾) |

Bosses (casts / MP, today): King 18 → Fire 3/9, Spark 6/12 · Queen 22 W → **Fire 2/6**, Spark 7/14 ·
Lord 38 W → **Fire 3/9**, Spark 11/22 · Ogre 43 → **Spark (W) 4/16**, Fire 5/25 · Pharaoh 50 W →
**Fire 3/15**, Spark 6/24 · DK 56 → Spark (W) 3/18, Lightning 2/24, Fire X · Archmage 67 →
**Fire only**, R3+2 5/40 or R2+2 6/30.

### 1.4 Verdict: why Firebolt trivialises the run

Raw efficiency is not the main cause: by D7–D8 ranked Spark beats Firebolt per MP. Four things
stack:
1. **Coverage** (1.2): the only spell that works on 4/4 kinds at every depth, plus W on the D2,
   D3 and D5 boss lines. The Mage never has to switch, read a resistance or carry a second plan.
2. **Range 12 with no self-risk**: a walker covers 1 col per turn, so r12 buys ~9–10 free casts
   before contact versus ~4 for Spark (r6) and ~3 for Drain (r5). With 1–2-cast kills, monsters
   die before they reach her: the Mage takes ~0 damage, which is what "cheating" feels like.
   Lightning, the other long spell, hits its own caster on the bounce; Frost freezes her.
3. **W × staff**: on Vampire/Mummy/Spider rows the Bone Staff's +2 becomes +4, so from D5 a
   rank-2 cast (5 MP) one-shots every Mummy, Spider and Vampire (23 vs 22/11/19 hp).
4. **Burst**: corridor packs line up, so the 1d4/1d6 splash (also W-doubled) softens the next
   body for free.
The other four are weak for structural reasons, not numbers alone: Frost (1.17/MP, worst) and
Drain (r5) are dead on the undead half of the game; Lightning arrives at D5, costs 5–12 MP and
is often a self-hit; Spark is half-range and reflected by Ghosts.

## 2. Rebalance

Targets: every damage spell's rank-1 dmg/MP in **1.5–1.85**; each spell is the best answer
somewhere and blocked somewhere; no spell covers every depth's roster; Firebolt stays the
generalist but loses the free-range and W-everywhere edges.

### 2.1 Option A — minimal (RECOMMENDED): table data only

**Rank rows (`ab_rank`, 126 B, same size):** MP · range · dmg (avg) · bounces · effect.

| Spell | R1 | R2 | R3 |
|---|---|---|---|
| Spark | 2 · r6 · 1d4+1 (3.5) · conf 1in4 4 | 4 · **r9** · 1d8+2 (6.5) | 6 · **r10** · 1d8+4 (8.5) · conf 1in2 |
| Firebolt | 3 · **r8** · **1d6+2 (5.5)** · burst 1d4 | 5 · **r8** · **1d8+4 (8.5)** · burst **1d4** | 8 · **r10** · **1d10+6 (11.5)** · burst 1d6, spares |
| Frost | 3 · **r10** · **1d6+1 (4.5)** · 1 b · frz 2 | 5 · r10 · **1d8+2 (6.5)** · 2 b · frz 3 | **7** · r12 · **1d8+4 (8.5)** · 2 b · frz 4 |
| Drain | 3 · **r6** · **1d6+2 (5.5)** | 5 · r8 · **1d8+3 (7.5)** | **7** · r8 · **1d8+6 (10.5)** |
| Lightning | 5 · **r16** · **1d8+4 (8.5)** · **1 b** · pierce | 8 · **r16** · **1d8+7 (11.5)** · **1 b** | **11** · **r20** · **1d10+9 (14.5)** · 2 b |

R1 dmg/MP: Spark 1.75 · Firebolt 1.83 (+burst) · Frost 1.5 (+freeze) · Drain 1.83 (+heal) ·
Lightning 1.7 (+pierce). Lightning r16/1 bounce: the self-hit needs the wall < 8 cols ahead.

**Resistances (`kx_tab`, same size):**

| Change | Rows | Why |
|---|---|---|
| FIRE W → N | Spider, Black Widow | removes Firebolt's free D2/D4/D5 one-shots (Queen inherits) |
| COLD I → **R** | Skeleton, Archer, Sniper, Guard, Knight; Ghost, Poltergeist | Frost works at ½ (freeze ½) on D3/D5/D8; the no-Firebolt Mage gets a Ghost answer (§10 BAL1 item) |
| DRAIN I → N | Necromancer, Bone Caller | they are living men; Drain gains D6–D8 (Necro is 2 in 4 on D7) |
| PHYS R → N | Mummy (Golden Pharaoh via its row) | Warrior parity (§3): DEF 2 + curse + food drain is enough |
| unchanged | Vampire FIRE W, Mummy FIRE W, Orc FIRE R, DK FIRE X, Ghost SHOCK X, Archmage | thematic anchors the user approved |

**Result (MP per kill, after A):** D3 Fire 7.5 vs Spark 6.7 (Frost now ¾ coverage) · D5 Mummy 2
Firebolts (10) not 1, Spider no longer one-shot · D7 Drain on 3/4 · Archmage 67: Fire R2+2
(10.5) 7 casts / 35 MP, R3+2 (13.5) 5 / 40 MP → pool 26 + a Mana potion, Mirror Helm returns or
a second visit (it never regenerates). Lord 38 W: Fire 4 casts / 12 MP of the L3 pool 16.

**Z80 impact:** 0 code, 0 tick (fewer bounces and shorter ranges can only lower the `lcastf`
worst case; P11 reflector ping-pong is loop-guard-bound, unchanged ≤ 123.7k). Info-line strings
change their range/MP digits (`FIREBOLT II  5MP RANGE 8 …`; text −/+ a few bytes, all ≤ 42).
**Tests:** `tests/combat_tables.py` (RANKS dict, KX rows, info lines) re-derived from the edited
game.md; `tests/proj3.py`, `tests/abil.py`, `tests/combat3.py` seeded outcomes rebaselined
(die sides change results, not RNG call counts); `lcastf` budget scenario re-measured.

### 2.2 Option B — fuller (A + ~40 B bank 3, after the sim confirms A is not enough)

1. **Lightning's own bounce spares the caster** (reflections still strike him): in `pf_reverse`,
   keep the caster DONE when the reversal is a wall bounce and `ABF_PIERCE` (~10 B, +~30 T per
   reversal). Then restore r28 / 2 bounces at R1–R2.
2. **Burst ignores W** (splash at ×1 max; ~8 B in the burst loop).
3. **Downcast choice** (cast key held = rank 1): lets a player trade burst for MP (~20 B; input
   path; UX ruling needed). Tests as A + proj3 bounce/burst cases + an abil downcast case.

Alternatives considered: Firebolt cooldown (new state + UI, rejected); FIRE R on Skeletons/Ghosts
(leaves Ghost R/X/I to everything: miserable); Archmage SHOCK X → R (open question Q2).

## 3. Win probability

### 3.1 Targets (decision; tune only if playtests disagree)

Competent human proxy = the sim's **average** policy. Win = `GS_WIN` (Archmage dead, Tome
destroyed). N ≥ 4,000 runs per hero × policy (Wilson 95 % CI ≈ ±1.5 pp).

| Metric | Target |
|---|---|
| Win rate, average | **40 %** (band 35–45) |
| cautious / reckless | 60–70 % / 10–20 % |
| **Parity** \|W − M\| | **≤ 5 pp** at average (gate); ≤ 8 pp at cautious and reckless |
| Survival at entry (average) D2…D8 → win | 97 · 92 · 86 · 79 · 71 · 62 · 52 → 40 (each ±5) |
| Mage spell share | no spell > 45 % of the Mage's spell damage; each known spell ≥ 8 % |

**Death budget** (share of all deaths, average policy): D1 5 · D2 8 · D3 10 · D4 12 · D5 13 ·
D6 15 · D7 17 · D8 20 %. Within a depth its boss ≤ 50 % of that depth's deaths; no single kind
> 20 % of all deaths; traps + falls ≤ 10 %; the Archmage 8–15 %.

### 3.2 First-order estimate (hand, ±15 pp; the sim replaces it)

Inputs: HP W 24→61 / M 16→37 (§4.1); FED regen +1/12 turns (~35 HP per ~450-turn level);
~2.5 potions per level, ≥ 1 Heal (+10); Mage MP regen 1 + MAXMP div 16 per 6 turns; books §5
(Firebolt by D5 93 %); Bone Staff / Cleaver at D4; Mirror Helm at D7.

| Survival per depth | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | **Win** |
|---|---|---|---|---|---|---|---|---|---|
| Mage now | .95 | .93 | .95 | .95 | .98 | .97 | .96 | .93 | **≈ 68 %** |
| Warrior now | .98 | .95 | .90 | .92 | **.82** | .90 | .85 | .88 | **≈ 43 %** |
| Mage after A | .95 | .93 | .93 | .95 | .95 | .94 | .95 | .90 | ≈ 60 % |
| Warrior after A | .98 | .95 | .90 | .92 | .90 | .90 | .85 | .88 | ≈ 47 % |

- **Mage weaker:** D1–D2 (16–19 HP, staff 1d4, Spark only; 6.5 HP lost per Goblin in melee),
  any no-Firebolt (~2 %) or no-Lightning-and-low-Spark run at D7.
- **Mage stronger:** everything from D3 once Firebolt is in: r12 kills before contact; D5 is her
  easiest level and the Warrior's hardest (gap ~16 pp there alone).
- **Warrior weaker:** every PHYS R wall — D3 Vampire Lord (drain heals it: net ~1.3 dmg/turn,
  ~29 turns), D5 Mummies/Pharaoh (today 20+ turns each through DEF 2 + R), Ghosts D6–D8, the DK
  (80 % to hit him, ~3.6/turn; needs both Power Strikes). He has no non-PHYS damage at all.
- **Warrior stronger:** steady HP, no book variance (PS III + Whirlwind III fixed by D5), bow.
- After A the gap is ~13 pp, still over tolerance, and both heroes sit above the 40 % band.
  Next knobs, in order (sim sweep, §4.4): Mage regen period 6 → 7; Ghost/Poltergeist PHYS R →
  N; DK atk 6 → 5; Warrior FED regen 12 → 10; then global difficulty (T2/T3 bases, Archmage hp).

## 4. Simulator spec — `tools/balance_sim.py`

Headless Monte Carlo, Python 3, stdlib only, `-I`-safe. Distributions, not byte-exact replay.

### 4.1 Data (single source)
- Read `kind_tab`, `kx_tab`, `ab_rank`, `ab_ammo`, `rd_tab` and `xpn_tab` from the built image
  through the same symbol/memory loader `tests/combat_tables.py` uses (build first); any knob is
  an override on top (`--set ab_rank.firebolt.1.die=6`, `--set kx.spider.fire=N`).
- Reuse: `tools/items_model.gen_level_items` (floor items, potions, gear, books per real seed),
  `tests/book_model.py` (`abil_learn` outcomes), `tools/respawn_model.py` (trickle),
  `tools/ranged_model.py` (`arch_decide`, ranged AI), tier odds §9.6, population §9.4.

### 4.2 Model
- **Level:** rooms from the level budget (count, kinds, per-room max §9.4.1); each room = an
  encounter of 0–3 monsters + its items. Lair last, boss + escort; D8 = Archmage lair then the
  Sanctum (Tome aura: fixed HP/turn × turns to destroy, from §9.9/§10).
- **Encounter geometry (1-D):** hero at col 0, monsters at gaps drawn from `GAP` (default
  uniform 3..20, knob), wall ahead at `WALL` (uniform gap+2..28), behind at 0..10; P(same
  storey, in line) `P_LINE` 0.7, else the monster spends `T_CLIMB` 4..8 turns closing.
- **Turn:** hero acts, then each monster by speed (every turn / every 2nd; Vampire bat form as
  every turn when gap > 2): step 1 col, melee in reach (F1 `d20 + atk ≥ 10 + eva`, dmg − DEF,
  resist), ranged per RANGED-SPEC (r, cooldown 2), Ogre SLAM, parry, rage, breed, summon.
- **Spells:** exact §6 projectile rules on the line: first body, pierce once per pass, bounces
  off `WALL`, caster valid after a reversal, X reverses at the front col, loop guard 4, burst ±1
  col, staff bonus before resist, auto-downcast. Statuses §6.4 with B2/HOLD_GUARD, durations.
- **Between rooms:** transit 20–60 turns; HP/MP regen, FOOD burn and stages (§7), pickups,
  equip-best (class-locked pools, GEAR1 gates, v = m + q), random Enchant (GEAR3), eat at HUNGRY.
- **Progression:** KXP, level-ups (§4.1), books via `book_model`, tomes.

### 4.3 Bot policies (same rules both heroes)

| Policy | Rest before a room if HP < | Heal at | Escape scroll at | Kite (step back at gap < 3) | Boss retreat at |
|---|---|---|---|---|---|
| cautious | 70 % (and MP < 70 % Mage) | 35 % | 25 % | always | 40 % |
| average | 50 % | 25 % | 15 % | 1 in 2 | 25 % |
| reckless | 25 % | 15 % | never | never | never |

Mage: cast the spell with the best expected damage per MP among those that can damage the target
(knows resistances), in range; staff when MP < rank-1 cost. Warrior: Power Strike when target
hp > 2 × weapon avg, Whirlwind when ≥ 2 adjacent, daggers/bow when gap ≥ 3. Resting costs FOOD.

### 4.4 Output and sweeps
- Per hero × policy: win % + Wilson 95 % CI; survival at each depth entry; death histogram by
  depth × killer kind × cause (melee/ranged/poison/trap/fall/aura); turns per depth; HP/MP/FOOD at
  entry; potions/scrolls used; Mage casts, MP and damage share per spell, overkill %; boss visits;
  `LVL` at entry vs `LVL_EXP`. CSV (`--csv`) + ≤ 30-line text summary; pass/fail vs §3.1.
- CLI: `--hero W|M --policy … --runs N --seed S --set k=v --sweep k=a:b:step`.
- Sweep knobs: every `ab_rank` cell, the §2.1 resist cells, Mage/Warrior regen periods, FED regen,
  Heal amount, potion count, PITY_N, T2/T3 bases, Archmage hp, DK atk, Mummy/Ghost PHYS response.
- Self-test: the resolve functions reproduce `tests/combat3.py` and `ranged_model` cases.

### 4.5 What the sim cannot capture → emulator spot-check (ZRCP bot)
Two storeys, ladders, pits, jumps, squeeze/wedges, door-closing tactics (flyers blocked), real
AI pathing quirks, line-of-fire from the real layout, trap placement, banking bugs (UB6/UB7),
input skill and the RNG stream interleave. Spot-check, per hero, 5 seeded scenarios (D3 Vampire
room, D5 Mummy room, D4 Ogre lair, D7 DK lair, D8 Archmage): turns-to-kill and HP lost must be
within ±25 % of the sim's prediction for the same kit, else calibrate `GAP`/`P_LINE`/`T_CLIMB`.

## 5. Open questions for the user
- Q1: accept A now (data only) and keep B for after the sim?
- Q2: Archmage stays FIRE-only for the Mage (fight costs ~35–40 MP after A: Mana potion or two
  visits) or SHOCK X → R so Spark/Lightning help at ½?
- Q3: parity also needs Warrior-side knobs (Mummy PHYS R → N in A; Ghost PHYS R → N next): OK to
  touch monster rows for the Warrior inside BAL-1?
