# NEW-MON3 — Gargoyle, Fire Imp, Frost Wraith (+ pit-stuck ranged fallback)

Status: **APPROVED with manager amendments (user 2026-11-09).** Nothing is built. Amendments that
override this doc: (1) NOT plan X replacements by default — raise the per-level kind cap to **5 on
D4–D7** where the C-era pool fits (keeps Archer/Ghost/Spider); fall back to plan X only per depth where
it does not fit; (2) Imp/Wraith alias row YES, with a levelcheck/test ASSERT they never share a depth;
(3) ADD a small cold-resist item (**Frost Charm**, ring or amulet: text, icon, balance in this batch)
so the Wraith makes cold gear matter; (4) wake gap 2; (5) freeze **1 in 4** for 2 turns at first
(tune after playtest); (6) ember red; (7) the frame-table page (+256 B bank 2) is funded inside C's
joint bank-2 plan (C ≈ 130 + AI-SEEK2 ≈ 26 + frames 256 B vs ≈ 9–19 B free) — freeing bank 2 is C's
first task. Batch runs **after TUT0 and after
option C** (`mirror_c_split.md`); §2.3 explains why C is a hard prerequisite even though every
placement fits the pool on its own.
**Amendment 2026-11-12 (§12, §5): APPROVED by the user 2026-11-12; pool numbers still to be confirmed by the
engineer's pool measurement.** More kinds per level with depth (8-slot `LP_KINDS`), funded by
returning 3 KB of `B0_FREE` to the pool. It supersedes amendment (1) and Plans X/Y.
User-fixed: these three kinds, for variety; pit fallback scope (§8). No feature cuts: every
existing kind keeps at least two depths, or one depth plus its boss role.

**Decisions 2026-11-13 (user).** (1) Frost Wraith freeze **1 in 4** (not ⅓; §4.3 / §10 Q5 closed).
(2) **Frost Charm** = an **amulet**, **COLD resist only**, drops from **D5** on, normal gear weight
(§10 Q3 closed: yes, as amendment (3)). (3) P-1 pit-stuck throws only **across pits**, never across
mid-room blocks (§8.2: the refusal hook is the pit-col test only). Funding (T1 FUND, built): carve 3,200 B
(`POOL_START` `$EFBE`: X = 3,072 landed 2 B off the straddle cliff; all `LEVEL_NEED` unchanged, D8 W slack 6,176), bank-2 / bank-3 / low-RAM / R6 room moved to bank-0 `B0_CODE2`
(memory-map "NEW-MON3 T1 ledger").

Verified sources: `src/defs.asm` K_* ids (0–29 used, `K_FXW`/`K_FXM` = 30/31), `KT_FLAGS` bit 7
spare, `FRT_MAX` 144 with `src/frames.asm` FID_COUNT **144 (0 spare)**, `tests/zx0_pool.py`
LEVEL_NEED against `POOL_CAP` 31,712, `src/turn3.asm` ai_monster / ai_flyer / ai_rhook call
sites, `src/spawn6.asm` sp_y (a flyer spawns at its cruise row `9s+1`).

---

## 1. The three kinds at a glance

| | Gargoyle | Fire Imp | Frost Wraith |
|---|---|---|---|
| Role | ambusher: a perched statue that wakes when you come near | erratic flyer that spits embers; **the first fire attacker** | slow, freezing undead flyer; the Ghost's heavy cousin |
| Depths (plan X, §5) | **D5, D6** | **D4, D6** | **D5, D7** |
| Behaviour reuse | Ghost flyer chase (`ai_flyer`, non-bat path) + **PERCH** (new, §2.1 G-1) | Bat erratic flyer (`KF_BAT`) + RANGED-SPEC row on a flyer (**new, F-1**) | Ghost drift + `KF_SLOW` (act every 2) + generic on-hit HOLD (FROZEN), exactly as the Archmage Frost row hits the hero |
| Kind id | **30** | **31 (alias A, on D4/D6)** | **31 (alias B, on D5/D7)** |
| New fids | 3 | 3 | 2 | + 1 shared DEAD |
| Pool today / under C hybrid | 1,472 / 1,280 B | 1,088 / 992 B | 1,280 / 1,088 B | + 96 B dust |

---

## 2. Engine budget: what is reused, what is new

### 2.1 New-code flags (each with its cheaper alternative)

| Id | Need | Est. | Where | Cheaper alternative (and what it costs the design) |
|---|---|---|---|---|
| **G-1 PERCH** | Gargoyle statue + proximity wake | ≈ 35–40 B | bank 3: a `bit 7` test (`KF_PERCH` = the spare `KT_FLAGS` bit 7) at `ai_monster .go`, before the flyer dispatch, ≈ 6 B; the handler in R6 via `far6`, ≈ 25 B; the wake-on-damage set in the monster damage path, ≈ 8 B | **ASLEEP at spawn** (timer 15, ≈ 12 B). **Rejected:** the `$41` tint and the overhead Zz mark (§6.4.1 V2: shown at `y = 9s+1`) reveal it at once. It would read as a sleeping monster, not decor, and it has no proximity trigger. The boss guard G2 is not reusable either: `LF_PROVOKED` is one level bit, and its storey and post are boss-only |
| **F-1 FLYER SHOOTER** | Fire Imp spits from the air | ≈ 20–25 B | bank 3 ≈ 8 B: in `ai_flyer` after `attack_if_reach` (`ret c`), set TMP4 = storey and H = 0 (standing), then `call ai_rhook` / `ret c`. R6 ≈ 15 B in `ai_ranged` / `rg_line`: for a flyer, `fr = y + h − 1` (its bottom row) and the in-line test adds `fr ≥ 9s+2` (inside the standing hero's rows) | **(a) Fire-touch flyer**: melee claw 1d4 FIRE, no spit. 0 code, data only. It is still the first FIRE attacker, but it loses the ranged threat. **(b) Walker imp**: the ranged hook as-is (0 code), but it needs walker frames and loses flight. Fallback order: (a) then (b) |
| **A-1 ALIAS ROW** | a 3rd kind id (§3) | ≈ 95–110 B (≈ 15 B loop + ≈ 20 differing bytes × (2 B addr + 2 values)) | R6 (or bank-0 cold via FARB0), runs once in `level_enter` **before** `pool_list` | none at ≤ 31 ids (§3) |
| **FX-U** | move the class FX units out of ids 30/31 | ≈ 0–10 B | `pool6.asm` gu_tab_x (`U_FXW`/`U_FXM` ≥ `K_MAX`); `start_game` uses `HERO_KIND + U_FX_BASE`; the defs.asm ASSERT changes | — |
| **P-1 PIT FALLBACK** | §8 | ≈ 30–40 B + Goblin dagger ≈ 20–25 B | call site in the bank-3 walker pit-refusal branch ≈ 6 B; the rest in R6 next to `ai_ranged` | §8.6 |

**0 new code:** Frost Wraith (Ghost drift, `KF_SLOW`, the generic on-hit apply with effect
FROZEN on the hero, the existing HOLD_GUARD), Imp FIRE thaw (§6.4 rule), resistances,
immunities, shared DEAD unit (`pool_gmap`, the same mechanism as the shared humanoid DEAD).
**Verified:** the `KF_SLOW` gate runs before the flyer dispatch (`turn3.asm:290-299`).

### 2.2 Data (no code)
- `kind_tab` columns, `KX` (8 B/row, `kind*8` in one page), and `lp_wt` (the `KT_REACH` slot) are all `K_MAX`
  32 wide already: rows 30/31 cost **0 B** of new space.
- `rk_tab` (bank 2, `ranged2.asm`, K_COUNT entries, same-page ASSERT): **+2 B** (rows 30, 31).
  The P-1 pit rows reuse the existing Spider/Goblin/Orc/Skeleton entries plus a PIT bit (§8.3).
- Names, KILLED-BY strings, KXP, drop, seq rows (`ksm_tab`), gu_tab units: ≈ 60 B raw, cold.

### 2.3 The real blockers: frame ids and bank 2, not pool
- **FRT is full: `FID_COUNT` 144 = `FRT_MAX` 144.** This batch needs **9 new fids**. The 145th
  fid steps FRT down a page: **+256 B bank 2** (16 fid rows, leaving 7 spare). Low RAM: +9 ×
  `FDESC_STRIDE` 5 = **+45 B** (`LOWRAM_SPARE` must be checked).
- Bank 2 has ≈ 9 B free (`mirror_c_split.md` §7.1). Funding route: move ≥ 256 B of bank-2
  cold code to bank 0 (FARB0), which means `POOL_START` +256 and **`POOL_CAP` −256 on every
  level**. Add the new R6/bank-0 code above (≈ 0.2–0.25 KB if bank 0 takes it).
- The D8 Warrior slack is **384 B**, so that funding fails today. **Option C hybrid** (≈ 5.3 KB at
  D8) pays for it. **That is the C dependency: C funds the bank-2 page and the code, not the
  kinds' own pool.**
- R6 free space must be measured for G-1/F-1/A-1/P-1 (≈ 0.17–0.2 KB). If R6 is short, bank-0
  cold code is next, via the same `POOL_START` route.

---

## 3. Kind ids (§11.2): 0 free today, 2 cheap, the 3rd by alias

- Today: ids 0–29 = 2 heroes + `K_VBAT` (the old Rogue hole, now the bat form) + 15 base/boss
  + 12 tiers = **30 rows**. Ids 30/31 = `K_FXW`/`K_FXM`. Those are generation units only, with no
  `kind_tab` column (`data.asm:290`), but they occupy the id range of `gu_tab`. **Free ids: 0.**
- Hard ceiling **32**: room records keep the row in `LE_KIND` bits 0–4 (`LEK_KIND_MASK`), and KX
  indexes `kind*8` inside one page. `K_MAX` cannot grow.
- **FX-U** frees ids 30 and 31. **Gargoyle = 30.**
- **3rd id = A-1 alias:** row 31 is patched at `level_enter` from a 2-variant table. It is the
  **Fire Imp on D4/D6** and the **Frost Wraith on D5/D7**. Why this is safe: a level is
  generated, populated and played with one variant only, and descent discards every monster
  (§9.3 "nobody follows"), so no record or slot ever holds the other variant. The parity
  stagger, banked records and trickle all stay inside one level.
  - Patch only the bytes that differ. Both variants share weight 3, flyer, untiered and 0 tier-up,
    so the patch covers hp/atk/eva/DEF/dice, flags (`KF_BAT` vs `KF_SLOW`), `KT_BH` 2/4, attr,
    resist 3 B, immunity, on-hit, rk row, KXP, drop, name/KILLED-BY pointers, gu_tab fid0/fcnt and the seq row.
  - **Placement constraint forever after:** the Imp and the Wraith may never share a depth.
  - `tools/levelgen.py` KROWS and `balance_sim` take the depth to resolve row 31.
- Rejected: aliasing an existing row (Slime D1-only, `K_VBAT` on Vampire-free depths). That
  risks kind-specific code paths and tests. Rejected: the off-class hero row (`KF_HERO` / id < 2
  assumptions, menu, tutorial).

---

## 4. Monster specs (§9.1 format; depth scaling hp + (d−1), atk + (d−1) div 3)

| Kind | Body px | hp | atk | eva | DEF | dmg | W | Move / flags | Behaviour | Drop | Depths |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Gargoyle** | 24×32 | 9 | 3 | 1 | 0 | 1d6 | 3 | flyer, `KF_PERCH` | **perch** (§4.1), then Ghost-path chase | — | D5, D6 |
| **Fire Imp** | 24×16 | 5 | 2 | 3 | 0 | 1d3 FIRE; ember 1d4+1 FIRE r6 | 3 (small 2 + projectile 1, the Slinger rule) | flyer, `KF_BAT` (erratic) | erratic + ranged, cooldown 2, **flies on between shots** (no hold, no step-away) | Mana 1/4 | D4, D6 |
| **Frost Wraith** | 24×32 | 13 | 3 | 2 | 1 | 1d6+1 COLD | 3 | flyer, `KF_SLOW` (acts every 2) | drift (Ghost); touch **⅓ → FROZEN 2** | — | D5, D7 |

Scaled: Gargoyle D5 13/4, D6 14/4. Imp D4 8/3, D6 10/3. Wraith D5 17/4, D7 19/5.
**KXP:** Gargoyle 8, Fire Imp 6, Frost Wraith 10 (between Ghost 6 and Mummy 12; §4.1 table).
**Untiered:** like Slime/Vampire/Mummy they draw no tier byte (`tier-up` = 0).
**Names (≤ 9 for hit lines / ≤ 12 KILLED-BY):** `GARGOYLE` / `GARGOYLE`, `FIRE IMP` / `FIRE IMP`,
`ICE SHADE` / `FROST WRAITH`. (`WRAITH` is taken: it is the Poltergeist's in-game string, §9.8 D3-6.)

**Resistances** (blank = N):

| Kind | PHYS | FIRE | COLD | SHOCK | DRAIN | DARK |
|---|---|---|---|---|---|---|
| Gargoyle | **R** | | R | | **I** | |
| Fire Imp | | **I** | **W** | | | |
| Frost Wraith | | **W** | **I** | | I | I |

**Status immunity:** Gargoyle SLEEP, FEAR, POISON (a stone construct, but CONFUSE works, so Spark
has a use). Fire Imp: none. Frost Wraith SLEEP, POISON (undead set). Being COLD I, the Wraith is
also never FROZEN, so its ink can never collide with the `$45` tint.

### 4.1 Gargoyle PERCH rule (G-1)
- **Perched** = the per-slot AWAKE bit is clear. Use any per-slot bit the engineer proves free for
  non-Vampire flyers; the Vampire's fled / `RCD_VSEEN` bits are kind-exclusive and can be shared.
  Not `ST_X`: `STS_POISON ⇔ ST_X ≠ 0`. With bit = AWAKE, slot init gives "perched" at **0 B**.
- Spawn is unchanged: a flyer spawns at its cruise row `9s+1` (sp_y), which is high on the wall,
  where a gargoyle belongs. FRESH, VISITED and ROOM-MEM re-spawns are perched again (stored hp is
  kept). An admitted follower keeps AWAKE.
- **Each own turn while perched** (after the status step and the slow gate, before
  `ai_flyer`): if the hero is standing on the same storey with **box gap ≤ `PERCH_GAP` 2**, set
  AWAKE, print `THE GARGOYLE WAKES UP.` (the existing ` WAKES UP.` suffix, 0 new text) and **spend
  the turn**. Otherwise wait (CF = 1) showing the rest pose. **Any HP loss sets AWAKE** (damage
  path, ≈ 8 B) with no message. The hit flash is the cue.
- Fairness: the hero always gets 1 turn after the wake (melee reach is gap 0–1). An observant hero
  shoots or casts first from range, because damage wakes it and he keeps the first strike.
  Perched it keeps eva 1 (no eva-0 code).
- A perched Gargoyle **blocks** like any flyer at the cruise row (its rows `9s+1..9s+4` overlap
  the hero's `9s+2..9s+7`). Walking into it is a bump attack, which wakes it.
- Never wakes: hero on the other storey or mid-ladder, or gap > 2. It may stay decor all level. That
  is allowed: XP forgone.
- ALARM waves set AWAKE if ≤ 4 B, else accept (it appears perched at the door). Default: set it.
- `idle_phase` stops automatically (the rest pose is a STA|SYM single frame, nothing to cycle).

### 4.2 Fire Imp ranged row (F-1) — RANGED-SPEC table row

| Kind | Range r | Cool N | Hit rule | Damage | On hit | Step-away | Climbs | FX |
|---|---|---|---|---|---|---|---|---|
| Fire Imp | 6 | 2 (every 3rd turn) | auto-hit (the Necromancer branch: `roll × response`, no DEF) | 1d4+1 FIRE | — (FIRE thaws a frozen hero: existing rule) | **no: flies on** (the Widow / King "walks in" semantics: reloading → CF = 0 → erratic flight) | flyer | `spark_fly1/2` at **`$42`** (an ember); hit impact `spark_fizz` (class-shared, 0 B) |

- In line only when `fr = y + 1` lies in `9s+2..9s+7`, so not at `y = 9s`. The clear line,
  cooldown, reflect gate (hero FIRE X never happens today) and track rules are exactly §9.2.
- `spark_fly` is in the Mage class FX. For the Warrior it is the SPIT-SPARK extra (+64 B), already
  pooled on D4 (it moves from the Spider to the Imp) and **new on D6**.
- SHOOT pose = the Imp's spit frame (§9.7 rule: an existing attack frame).
- `Ring of Fire Ward` (FIRE R) halves both its claw and its ember. The Imp gives that ring its
  first real job.

### 4.3 Frost Wraith touch
COLD-typed melee. The §6.4 typed-rider rule applies: FROZEN only if ≥ 1 damage lands; hero I/X →
none, R → 1. **There is no COLD-resist gear today** (§8.4 gear table: only Fire Ward FIRE R), so
"cold gear matters" needs gear. See Q3. HOLD_GUARD (§6.4.1 B1) stops chain-freezing. FIRE
thaws the hero, but the Imp never shares a depth with the Wraith (alias), so there is no accidental synergy.

---

## 5. Placement (2026-11-12: 4–6 kinds + boss, 8 slots, joins only; rule in §12)

Plans X/Y and the "≤ 4 kinds, replace one" rule are retired: nothing is replaced. Slots 0..n−1 =
the distinct kinds **in fallback order**. Slots n..7 = duplicates, which set the weight (draw = count/8).
Same list for both heroes. `LP_BOSS` is unchanged per depth. **Bold** = joins or returns.

| D | n | `LP_KINDS[0..7]` | Count of 8 (in slot-0.. order) |
|---|---|---|---|
| 1 | 4 | Rat, Bat, Slime, Goblin, Rat, Bat, Slime, Goblin | 2 2 2 2 (= today) |
| 2 | 4 | Goblin, Spider, Bat, Rat, Goblin, Spider, Bat, Rat | 2 2 2 2 (= today) |
| 3 | 5 | Skeleton, Vampire, Ghost, Bat, **Goblin**, Skeleton, Vampire, Ghost | 2 2 2 1 1 |
| 4 | 5 | Orc, Rat, Spider, Archer, **Fire Imp**, Orc, Archer, Fire Imp | 2 1 1 2 2 |
| 5 | 6 | Mummy, Spider, Skeleton, Archer, **Gargoyle**, **Frost Wraith**, Mummy, Archer | 2 1 1 2 1 1 |
| 6 | 6 | Vampire, **Gargoyle**, **Fire Imp**, Ghost, Necro, Orc, Vampire, Orc | 2 1 1 1 1 2 |
| 7 | 6 | Orc, Ghost, Necro, **Frost Wraith**, **Mummy**, **Spider**, Orc, Necro | 2 1 2 1 1 1 |
| 8 | 6 | Necro, Skeleton, Ghost, Vampire, **Orc**, **Frost Wraith**, Necro, Skeleton | 2 2 1 1 1 1 |

- **Alias holds:** Imp D4/D6, Wraith D5/D7/D8 (disjoint, levelcheck ASSERT). Gargoyle D5/D6.
- **Fallback fillers** (§9.4.3, minW kind, ascending index): D3 Bat, D4 Rat, D5 Spider, D6
  **Gargoyle before Imp/Ghost** (3-unit rooms fill with statues, not ember spitters), D7 **Spider**
  (was Ghost), D8 Ghost. minW changes only on D7 (3 → 2): the engineer re-checks D7 `SIGMA_INIT`.
- **Why these returns** (§12.1): each deep list keeps melee + ranged + flyer + climber. Pool per depth: §12.3.

---

## 6. Frames and art

### 6.1 Frame list (9 new fids; pool = 2 dirs × variants; SYM = one dir)

| Fid | Size | Class | Pool | Hot/cold under C hybrid | Use |
|---|---|---|---|---|---|
| `garg_perch` | 24×32 | STA\|SYM | 192 | SYM (never mirrored) | REST = the statue; also HURT (it flinches back to stone) |
| `garg_fly` | 24×32 | MOT | 896 | **hot** | flight (the `gh_fly` sequence shape: one MOT frame) |
| `garg_claw` | 24×32 | STA | 384 → 192 | **cold** | ATTACK |
| `imp_fly1` | 24×16 | MOT | 448 | **hot** | REST + flap A |
| `imp_fly2` | 24×16 | MOT | 448 | **hot** | flap B (the Bat-style 2-cycle) |
| `imp_spit` | 24×16 | STA | 192 → 96 | **cold** | ATTACK, SHOOT, HURT (the Spider precedent) |
| `wraith_drift` | 24×32 | MOT | 896 | **hot** | REST + flight (frame 0 is MOT, so the frames.asm rest rule holds) |
| `wraith_touch` | 24×32 | STA | 384 → 192 | **cold** | ATTACK, HURT |
| `dust_dead` (shared unit) | 24×16 | STA\|SYM | 96 | SYM | DEAD for all three (a remains heap: grey rubble, red embers, cyan rime, by `KT_ATTR`) |

- HURT reuses a pose (0 B), following the ANIM-IMPORT rule "the flash alone is not acceptable".
- Cold frames add to C's T10 "lmix" scenario: several bodies in mirrored attack frames in one tick.

### 6.2 Inks (black paper, one ink per cell; avoid `$42` hit, `$46`/`$47` gold glow, tints `$41 $45 $43 $07`)
- **Gargoyle `$07`** (unbright white = weathered stone; it should read as masonry). It is the STUNNED tint
  value, so the existing twin rule shows `$47` when stunned. If the artist's D5/D6 back-wall decor ink
  differs, match the decor instead (the point is to look like the wall), as long as it stays off the
  avoid list.
- **Fire Imp `$06`** (amber; static, so it is not the gold glow). `$02` was rejected: the hit flash
  barely shows on it (D3-4), and it is the Giant Rat (D4) / Berserker (D6) ink.
- **Frost Wraith `$05`** (dim cyan). It is never frozen (COLD I), so `$45` never appears on it. The Ghost
  `$45` shares D7, but brightness and silhouette separate them. Fallback `$47` would be
  Brood Rat / Skeleton, not on D5/D7.

### 6.3 Art brief (original designs, dark-fantasy crypt, 1-bit, one ink per 8×8 cell)
- **Gargoyle:** a squat horned stone beast. `garg_perch` is front-facing and symmetric: wings folded
  like a cloak, claws gripping a broken corbel stub, head low, two hollow eye pits. It must pass for
  a wall carving. `garg_fly`: wings fully spread (span fills 24 px), body tilted forward, tail down,
  heavy and not graceful. `garg_claw`: a downward raking swipe, one wing up. Rough stone texture
  by dithered speckle, no outline glow.
- **Fire Imp:** a small wiry devil, bat wings, oversized head with a wide grin, a curled tail.
  `imp_fly1/2`: wings up / down (the Bat silhouette must stay distinct: horns plus a visible
  tail). `imp_spit`: cheeks puffed, head thrust forward, mouth open toward the front.
- **Frost Wraith:** a tall hooded shroud with no legs, its hem breaking into icicle points, a long
  thin crystalline arm. `wraith_drift`: hunched, arms trailing. `wraith_touch`: one arm thrust out,
  fingers splayed, with frost shards off the fingertips. Its silhouette must differ from the Ghost
  (hood + icicle hem vs the Ghost's round sheet).
- **`dust_dead`:** a low symmetric heap of rubble/ash with 2–3 loose chunks, 16 px tall.
- Projectile: the Imp reuses `spark_fly1/2` at `$42`. No new projectile art.

---

## 7. Balance rationale (vs BAL-1 FINAL B: W 41.4 / M 43.4, gap −2.0)

- **D4 (Imp for Spider):** a W2 melee poisoner becomes a W3 erratic ember spitter (≈ 3.5 FIRE per
  3 turns in range, halved by Fire Ward). The Mage's Firebolt is useless (I), but Frost is ×2 and
  Spark works. The Warrior's daggers/bow have a target. Expect a small loss for both, slightly more
  for the Mage (Firebolt is his main rank-1 spell).
- **D5 (Gargoyle + Wraith for Skeleton + Archer):** heavier bodies (W5/W6) become W3 ones, so
  rooms carry more but lighter monsters. Ranged pressure drops (no Archer). **The Warrior loses the
  Archer's arrow drops on D5** (Arrows ×3 at 1/2). The Gargoyle's PHYS R is the Warrior's tax,
  answered by Power Strike. Expect: D5 a bit easier for the Mage, neutral to harder for the Warrior.
- **D6 (Gargoyle + Imp for Ghost + Necro):** removes the Mage's top killer here (Ghost: 44 % of Mage
  deaths overall) and the ordinary FEAR bolts. The boss is unchanged. The Imp keeps a ranged threat
  and its Mana 1/4 drop replaces the Necro's Mana 1/3. **The gap likely moves toward the Mage (+).**
- **D7 (Wraith for one Necro entry):** half the FEAR bolts; adds a slow freezer (⅓ → FROZEN 2,
  eva 0 while frozen). Firebolt ×2 makes it a Mage target.
- **Top risk:** FROZEN 2 on the hero in a crowded D7 room (an Orc's 1d8 lands at eva 0). Knobs in
  order: chance ⅓ → ¼, then duration 2 → 1. Second risk: Imp triple-rolls in D4/D6 rooms (auto-hit
  embers, 3 tracks).

**`tools/balance_sim.py` re-sweep (FINAL B 10k × 2 seeds, targets W/M 35–45, gap ≤ 5):** new kind
rows and resistances/immunity. Row 31 must be resolved by depth. Plan X `LP_KINDS` for D4–D7 (and
the `levelgen.py` LP_TAB mirror). `tools/ranged_model.ROWS` + the Imp row (auto-hit FIRE r6 N2,
no hold; in-line approximated as always). Perch model: dormant until gap ≤ 2 or damaged, wake costs
a turn, a ranged hero opens first. `KF_SLOW` Wraith and the on-hit FROZEN on the hero (eva 0, HOLD_GUARD).
Drops: Imp Mana 1/4, D5 loses Archer arrows. P-1 pit throws (§8.5; if the sim has no pit model,
add a per-pit-escape damage term). Report Plan X and Plan Y side by side.

---

## 8. Pit-stuck ranged fallback (user addition 2026-11-09)

### 8.1 Intent
Pits stay **mostly an escape**. A walker stranded at a pit edge (§2.5: walkers never step to
`x == p`, wide pits `p ≤ x ≤ p+W−3`) may throw something weak at a hero who lingers within a few
cols on the far side, instead of waiting forever.

### 8.2 Trigger (no per-tick cost; one branch per refused step)
Hook = the walker rule that **refuses a step because of the pit-col test** and would end in a wait
(`.fstep` / `.seek` refusal). There, and only there, if the kind has a pit row (§8.3), call the
ranged hook in **pit mode**:
1. The hero is standing on the same storey (storey 0: pits exist only there), not mid-ladder.
2. Decrement the counter, then the standard RANGED-SPEC checks: in range (`gap < r`), clear line
   (wall scan on row `fr`, `box_free`; the pit holes are in the floor row, not `fr`, so they never
   block), reflect gate.
3. Counter 0 at entry → throw (face the hero, resolve now, counter = N). Else wait as today.
4. **Track limit:** if all 3 projectile tracks are busy, the thrower **waits** (no throw, counter
   unchanged). This is a live-track read (≈ 6 B), so pit throws never queue a 4th track.
- The normal step-4 hook **skips** pit rows (one PIT-bit test), so these kinds never shoot in open
  ground. The counter only runs down while stranded: counter 1 at spawn means the first stranded
  turn is free and the throw comes on the next.
- FEAR / CONFUSED / held / slow off-turns never reach it (unchanged order).

### 8.3 Per-kind pit rows (atk = the kind's own atk incl. depth scaling)

| Kind (rows covered) | Range r | Cool N | Hit | Damage | Effect | Projectile (existing art) | Ammo |
|---|---|---|---|---|---|---|---|
| Spider (base only; the Widow's open-ground spit and the Queen's row are unchanged) | 4 | 3 (every 4th turn) | F1 | 1d2 PHYS − DEF, min 1 | POISON +6 (cap 30; Silk Cloak immune) | `spark_fly` `$43` (the WIDOW-SPIT look) | ∞ |
| Goblin (base only; the Slinger and King have rows) | 6 | — | F1 | 1d3 PHYS − DEF | **one dagger per life**; it then lands as loot by §6.3 hero-dagger rules (hit: under the hero's feet; miss: at the impact cell; 1 in 4 lost; a pit col is always lost; floor list full: lost) | `dagger_spin` `$47` (the hero's dagger ink: it reads as pick-up-able) | 1 (spent bit: the same kind-exclusive per-slot bit as PERCH) |
| Orc (+ Berserker, Bouncer; no rage/stun riders on throws) | 5 | 3 | F1 | 1d6 PHYS − DEF | — | `dagger_spin` `$07` (a hand axe) | ∞ |
| Skeleton (+ Guard, Knight; no parry on throws) | 5 | 3 | F1 | 1d4 PHYS − DEF | — | `dagger_spin` `$47` (a bone) | ∞ |

- Bosses never (lair-bound, no pits in the lair rule). Archers / Necros / Slingers already shoot.
- Pool: Warrior 0 (`dagger_spin` is class FX; `spark_fly` is the SPIT-SPARK extra on Spider levels
  D2/D5). Mage: `dagger_spin` +64 B on the Orc/Skeleton levels lacking it (D3, D4, D6, D7, D8;
  Mage D8 slack ≈ 3.7 KB). 0 new fids.
- Encounter weights unchanged (a rare extra track → at worst the accepted presentation-only 3-frame
  tick, §9.3 "Overrun"); C's budget scenario list gains a "pit volley" case.

### 8.4 Balance note
A narrow pit already allows melee across it (walker at `p−1`, hero at `p+2`: gap 0). The fallback
only covers gap 2…r−1. The hero escapes by stepping 2–5 cols back from the edge. Expected cost per
pit standoff ≈ 0–1 throws ≈ 0–3 HP (Spider +6 poison ≈ 1.5 HP over time). The Goblin gives away a
dagger. Net: the pit escape is weakened by about one cheap hit per lingering hero, and not at all for
a hero who keeps walking. Bounded by short r and N = 3.

### 8.5 Code cost and location
≈ 30–40 B logic + ≈ 20–25 B Goblin dagger (it reuses the hero-dagger drop routine and the floor list)
+ 1 PIT bit per affected `rk_tab` row. **Bank 3 is nearly full:** only the ≈ 6 B call site goes in
the bank-3 refusal branch. The rest sits beside `ai_ranged` in R6 (`far6`), or in bank-0 cold code
via FARB0 if R6 is short. **The architect places it**, together with G-1/F-1/A-1 (one R6 budget).

### 8.6 Cheaper fallback if bytes run out
Drop the Goblin loot drop: its dagger is consumed like every monster shot (saves ≈ 20 B). Then drop
the track-limit read and use the existing "4th waits" FX queue (saves ≈ 6 B).

---

## 9. Tests and goldens that must change
- `tests/ai_equiv.py`: the Python == Z80 AI reference gains PERCH, the flyer shooter and the pit branch.
- `tests/ranged.py`, `tests/proj3.py`: Imp row (flyer `fr`, the `y = 9s` not-in-line case, flies on
  while reloading), pit rows (refused-step only, PIT skip at step 4, counter, track-limit wait,
  Goblin one-shot + floor dagger, poison spit).
- `tests/status.py` / `status1.py`: Wraith FROZEN on the hero (⅓, R halves, HOLD_GUARD), Imp FIRE
  thaw. Gargoyle: wake on gap 2, wake on damage, re-perch on re-entry, follower stays awake.
- `tests/lp.py`, `tests/roommem.py`, `tests/trickle.py`, levelcheck: Plan X `LP_KINDS`, row-31
  alias by depth, waits ≤ 15 %, discard 0. `tools/levelgen.py` KROWS / LP_TAB mirror.
- `tests/zx0_pool.py` LEVEL_NEED (D4–D7 both heroes, Mage `dagger_spin` extras), `tests/gfx_integrity.py`,
  `tests/frames_phase.py` (MOT rest frames, shared DEAD unit), C's `tests/mirror_equiv.py` (new fids).
- `tests/budget.py`: an Imp ember + 3-track tick, the pit volley, mirrored attack frames (lmix).
- `tests/combat_tables.py`: new rows. Goldens: seeded D4–D7 non-start rooms may change. Re-bless
  after review only.
- `tools/balance_sim.py` (§7).

---

## 10. Open questions (defaults apply if unanswered)
1. **Plan X vs Plan Y** (the Archer keeps D5 vs the Imp gets 2 depths). Default **X**.
2. **Alias row 31** (≈ 100 B), or give up a kind. Default **alias** (the only route under 32 ids).
3. **COLD-resist gear** so the Wraith "makes cold gear matter": a 6th charm "Frost Ward" (COLD R;
   item id + name ≈ 20 B + a `gear_pool` entry). Default **no**: the Wraith is tuned to be beatable
   without it. Revisit after the sim.
4. `PERCH_GAP` 2 vs 3. Default **2**.
5. Wraith freeze ⅓ / 2 turns. Default as specified; the sim may push it to ¼.
6. Fire Imp ember ink `$42` (Firebolt red) vs `$46`. Default **`$42`**.
7. FRT page funding (+256 B bank 2) from bank-0 relocation after C. Default **yes**. The architect
   picks the cold code to move.

---

## 11. Doc impacts (not edited here)
- **game.md** §9.1 roster + resistance + immunity tables (3 rows). §9.2: the shooters table (Imp row,
  4 pit rows), the flyer-shooter rule (F-1), PERCH (G-1), the pit fallback rule (P-1). §9.3 weights
  (Imp 3). §9.4 table D4–D7 + §9.4.1 `LP_KINDS` + the D7 note (one Necro entry). §9.6 untiered list.
  §9.8 D3-6 names. §4.1 KXP table. §2.5 cross-ref to the pit fallback. §6.3 "monster shots never
  drop an item": the Goblin pit-dagger exception. §6.4 source columns (FROZEN: Frost Wraith;
  FIRE sources: Imp). §6.0 sources (FIRE/COLD monster attacks). §11.1/§11.2/§11.3 fids (+9; FRT
  144 → 160), kind ids (30 Gargoyle, 31 alias, FX units out of the id range), pool per level.
- **memory-map.md**: FRT page step (+256 B bank 2) and its bank-0 funding, `POOL_START`/`POOL_CAP`,
  gu_tab_x FX units, the R6/bank-0 code for G-1/F-1/A-1/P-1, `rk_tab` +2, low-RAM descriptors
  +45 B, per-level pool ledgers.
- **mirror_c_split.md** §4/§6 T7/T10: the new hot set (garg_fly, imp_fly1/2, wraith_drift), cold set
  (garg_claw, imp_spit, wraith_touch), the lmix/pit-volley scenarios. The merge-order note
  (NEW-MON3 after C T8).
- **budget.md**: the scenarios above. **prototype.md** §3.5: flyers may shoot (Imp).
- **instructions_screen.md / instructions_treasures.md**: only if the bestiary/hint pages list
  monsters per depth or resist gear (check).
- **tools**: `levelgen.py` (KROWS by depth, LP_TAB), `ranged_model.py` ROWS, `balance_sim.py`.
- **plan.md** (manager): the task split. FX-U → A-1 → frames/art → kinds data → G-1/F-1 → P-1 → tests/sim.
  After TUT0 and C.

---

## 12. Kinds-by-depth curve (user 2026-11-12)

**Status: APPROVED (user 2026-11-12). Numbers to be confirmed by the engineer's pool measurement (X = 3,072 B, else 4,096 B).**
Curve: D1–D2 4, D3–D4 5, D5–D8 6 + boss. Deep lists reuse earlier kinds, so no new ids (§3: `K_MAX` 32).
Larger depths (`larger_depths.md`, 3×4 grid, monsters ×1.35) lands **after** this. It changes counts, not kinds or pool.

**12.1 Lists:** §5 table. Returns: **Goblin D3** (a light W3 body between Skeleton/Vampire. Its Slinger tier 2 can
roll from D3, the first ranged threat before the D4 Archer). **Mummy D7** (was D5-only: a heavy melee wall
next to Necro bolts. The climb pair is already pooled on D7). **Spider D7** (cheap W2 poisoner and climber,
status pressure that does not stack with FEAR). **Orc D8** (a brute with a Berserker tier. It replaces
the removed second Necro weight as the melee anchor). The Archer stays off D7/D8 (3F-T13bc H1). Every depth
from D4 on has melee, ranged (Archer / Imp / Necro), flyer and climber.

**12.2 Selection:** `LP_KINDS` grows **4 → 8 bytes**, pick `LP_KINDS[rnd & 7]`. Use duplicates for weights,
not `rnd mod n` (no divide, same 1-step RNG draw, so the seeded stream stays 1 draw per pick). Every
LP_KINDS consumer (pick, `pool_list`, the minW fallback scan, trickle/ALARM/respawn picks, D0 setup)
loops 8 instead of 4. `pool_list` already dedups per unit, so duplicates cost 0 pool. Cost: code ≈ 0–10 B (masks
and loop counts), `LP_TAB` +32 B (8 depths × 4), level header +4 B (`LP_BOSS` and the later header bytes move: ASSERT
users such as `tests/zx0_pool.py` read 9 B, not 5). Rejected: per-depth n + `rnd mod n` (≈ 15–20 B, uneven odds unless rejection-sampled).

**12.3 Pool and funding.** Full-C cost estimates: Gargoyle ≈ 830, Imp ≈ 540, Wraith ≈ 640, dust 96 (MOT
frames halved vs §1). Returned old kinds ≈ Goblin 0.7, Spider 0.9 (+64 W spark), Mummy / Orc 1.5 KB each. Climb pair already
pooled where added. **X = 3,072 B:** `POOL_START` $FC3E → **$F03E**, `POOL_CAP` 19,394 → **22,466**,
`B0_FREE` 11,958 → **8,886** (≈ 7.3–7.6 KB after item info 0.45 + level-state 0.1–0.3 + NEW-MON3 code/FRT ≈ 0.5). The engineer nudges ±2 B off any
bank 0→4 straddle cliff. The D0 pool only gains room.

| D | W today → new (est.) | M new (est.) | W slack @ 22,466 |
|---|---|---|---|
| 1 / 2 | 11,826 / 11,842 (=) | 10,258 / 10,242 | ≥ 10.6 K |
| 3 | 14,354 → 15,054 | 13,454 | 7.4 K |
| 4 | 15,298 → 15,934 | 14,366 | 6.5 K |
| 5 | 12,546 → 14,112 | 12,544 | 8.4 K |
| 6 | 14,978 → 16,508 | 14,844 | 6.0 K |
| 7 | 14,482 → 17,682 | 16,082 | 4.8 K |
| 8 | 16,418 → **18,654** | 17,118 | **3.8 K (binding)** |

At today's cap D8 W would have 740 B (< 1 KB), so funding is required. Even with a +30 % estimation error the binding slack stays ≥ 3 KB.
**Escalation:** if the measured binding slack is < 1,024, use X = 4,096 (B0_FREE 7,862). Never go below B0_FREE 6 KB.

**12.4 Balance (vs BAL-1 FINAL W 41.4 / M 43.4).** D3 is a bit easier (Goblin XP). D4–D6 change as §7, but they are
joins, so the D5 Archer arrows and the D6 Ghost stay (D6 is less Mage-friendly than Plan X). **D7/D8 are harder** (Mummy and Orc heavy
bodies, Wraith FROZEN next to Necro FEAR). Expect both to drop 2–5 points, the Warrior more. Gate: **both ≥ 35 % and |W − M| ≤ 3**
(this supersedes §7's ≤ 5). `tools/balance_sim.py` re-run: 8-slot `LP_TAB` with the weights, row 31 by depth (Wraith D8 too), the
new returns (Goblin D3 tier odds, Mummy/Spider D7, Orc D8), the Imp/Perch/Wraith models of §7. Knobs in order: slot weights (data
only: drop the duplicate Necro/Orc on D7/D8 first), Wraith freeze ⅓ → ¼, `TIER3_MIN_DEPTH` odds on D7/D8, ember cooldown 2 → 3.
Re-run again after larger depths (×1.35).

**12.5 Interactions.** Spawn/respawn/trickle/ALARM draw through the same 8-slot pick, so their mix follows
automatically. FRESH quotas are unchanged. **ROOM-MEM**: records keep the kind row (`LEK_KIND_MASK`, 5 bits), so there is no format
change. Only the header grows by 4 B (count it in the larger-depths level-state budget). **TUT0**: D0 is untouched, but `tut_d0`
must fill all 8 slots (Goblin ×8) or the pick reads stale bytes. Add a `tests/tut0.py` check. **Cards**: the level and end cards
show no per-depth kind list. KILLED-BY strings per kind already exist. The engineer greps `instructions_*.md` for any
bestiary-by-depth text. Tests: `tests/lp.py`, `roommem.py`, `trickle.py`, levelcheck (alias disjoint, D7 `SIGMA_INIT`, waits ≤ 15 %),
`zx0_pool.py` LEVEL_NEED, `tools/levelgen.py` LP_TAB mirror.
