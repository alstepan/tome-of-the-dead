# LOG-DMG — damage and remaining HP in the message log

Designer spec, 2026-11-01. Implements the user ruling of 2026-11-01: **every hit puts its damage
number in the log line; a hit on an enemy also shows the enemy's remaining HP.** This ships
before the flying numbers (game.md §6.5 D3-11 stays a prototype). It amends game.md §3.4
"Message limits" and the impact pieces approved there (B3B-13); everything else in §3.4, §6.5
and §6.5.1 (gate, ring, `LT_HOLD`, readout) is unchanged.

## 1. Rules

1. **Numbers ride on existing lines.** LOG-DMG adds **no new log lines**. It appends a tail to
   lines that already exist, so the ring load, `log_room`, `CAST_LINE_MAX`, `LOG_WAIT_MAX`
   and the §6.5.1 gate are unchanged.
2. **Tail grammar.** The tail is ` -D` for HP lost, or ` +G` for HP gained. A hit on an enemy
   that survives adds ` HP H`. A kill shows ` -D` only.
   - `D` = the HP the body actually lost: `deal_hit`'s `L` / `dh_lost`, after
     resist/weak/DEF, **clamped to the HP it had**. Overkill is not shown, which matches §6.5's
     `-n`. A 3-HP Rat hit for 7 prints `-3`.
   - `H` = the target's `E_HP` when the line is composed (the logic HP: already reduced).
   - `G` = the HP actually gained after the max-HP clamp.
3. **Zero prints nothing.** If D = 0 or G = 0, the line has **no tail at all** (no `-0`, no
   `HP`). Immune, reflect and parry already have their own lines (`IS UNAFFECTED`,
   `PARRIES!`). A heal at full HP prints the bare line.
4. **The hero gets the number only.** The panel shows his HP, so his lines have no `HP`
   part.
5. **Bosses, uniques, the Archmage and golden monsters** show `HP H` like any enemy. Nothing
   is hidden.
6. **Timed trickles are silent**, by the §6.5 rule: poison ticks, the Tome aura's 1 HP per
   turn, FED regen, level-up and the Vigor/Power tome max-HP raises. They print no new line
   and get no tail. The panel HP bar carries them.
7. **Number format.** Unsigned decimal, 1–2 digits, no leading zeros, **clamped to 99** (a
   value ≥ 99 prints `99`, the same cap as §6.5). No current value reaches it: the largest
   monster hp is 60 (Archmage), and the largest single hit is about 40. So the clamp is a
   guard, not a rule the player meets. Upper case only; the font already has `+`, `-` and
   digits.
8. **Line length ≤ 31 chars** (one char under `LOG_MAX` 32). Worst tail = ` -99 HP 99` =
   **10 chars**. Every hit prefix that is followed by a kind name is therefore **≤ 12 chars**
   (12 + `NM_LONG` 9 + 10 = 31). This is guaranteed by build ASSERTs, so there is no runtime
   length guard, no abbreviation table and no dropping of the HP part.
9. **No article on hero-attack lines.** `THE ` is dropped from every line where the hero
   strikes (the 3E rule "no article in composed lines"). This frees the 4 chars and saves
   text. Lines where the monster is the subject keep `THE` (`THE GOBLIN HITS YOU -3`), and so
   do the status suffix lines (`THE RAT IS FROZEN`).

## 2. Line formats (per event)

`N` = kind name (≤ 9). The lengths are the worst case with N = 9 and two-digit numbers.

| Event | Line | Max len | Source |
|---|---|---|---|
| hero melee hit (sword / staff / Whirlwind blow) | `YOU HIT N -D HP H` | 27 | `impact_line` MSG_P_HIT |
| Power Strike hit | `YOU SMASH N -D HP H` | 29 | new MSG_P_SMASH (cut 1 → `YOU HIT`) |
| hero kill, any source | `YOU KILL N -D` | 22 | MSG_P_KILL |
| hero melee miss | `YOU MISS N` | 18 | MSG_P_MISS (no number) |
| dagger hit | `DAGGER HITS N -D HP H` | 31 | `hit_line` |
| arrow hit | `ARROW HITS N -D HP H` | 30 | `hit_line` |
| Spark | `SPARK HITS N -D HP H` | 30 | `hit_line` |
| Firebolt | `FIRE BURNS N -D HP H` | 30 | `hit_line` |
| Frost Shard | `FROST HITS N -D HP H` | 30 | `hit_line` |
| Drain Life | `YOU DRAIN N -D HP H` | 29 | `hit_line` |
| Lightning | `BOLT HITS N -D HP H` | 29 | `hit_line` |
| dagger / arrow miss | `YOUR DAGGER MISSES THE N` (unchanged) | 32* | existing; no number |
| parry / immune | `THE N PARRIES!` / `THE N IS UNAFFECTED` (unchanged) | 27 | no number |
| monster melee or ranged hit on the hero (incl. Ghost touch, Necromage bolt, Archer arrow) | `THE N HITS YOU -D` | 26 | MSG_M_HIT |
| Vampire bite | `THE VAMPIRE DRAINS YOU -D` | 26 | MSG_M_DRAIN (its own heal: no line, rule 6 spirit; readout shows it) |
| monster miss | `THE N MISSES` (unchanged) | 20 | no number |
| own Lightning bounce / reflected spell | `THE BOLT HITS YOU -D` | 21 | `spl_hit_self` |
| own Firebolt burst | `THE BURST SCORCHES YOU -D` | 26 | `spl_burn_self` |
| dart trap | `A DART HITS YOU! -D` | 20 | trap line |
| stone trap | `A STONE FALLS ON YOU! -D` | 25 | trap line |
| pit fall (only if it costs HP) | `YOU FALL INTO A PIT -D` | 23 | `fall` |
| Tome hit (P3) | `THE TOME SHUDDERS -1 HP H`; the last hit prints `THE TOME IS DESTROYED`, no tail | 25 | P3 site, H = `TOME_HP` |
| Heal potion, Drain Life caster heal | `YOU FEEL HEALTHIER +G` | 22 | `spl_drain_heal` |
| Cure potion (+4 HP) | `YOU ARE CURED +G` | 16 | `cure` |
| poison tick, Tome aura, regen | silent | — | rule 6 |
| enemy on enemy | does not exist (summons only add bodies; nothing hits a monster except the hero's actions). A Mirror-Helm return on the Archmage prints whatever line it already prints; if that line is a `hit_line`, it gets the tail for free. | — | |

\* `YOUR DAGGER MISSES THE ` + 9 = 32, the existing 3F-D3 maximum. It carries no number, so it
is left alone.

**Whirlwind:** **one line per struck target**, in slot order, as today (each blow is its own
`melee_strike` → `impact_line`). No summary line. With more results than ring slots, the
LOG-FIX rule applies unchanged: `log_room` replaces the newest pending line and counts it in
`LQ_DROP`. The info-line readout still points at the surviving struck monster with the lowest
HP (§6.5).

**Multi-target bolts (Lightning pierce/bounce, Firebolt burst):** today `ammo_fire` prints the
line for `pf_tgt` only, and LOG-DMG keeps that. The tail must use **`pf_tgt`'s own** HP lost
and HP left, not those of the last strike (§4, `LN_*`). Secondary targets: see §7 (UB3).

**Order quirk (accepted, 0 B):** Drain Life pushes `YOU FEEL HEALTHIER +5` from `deal_hit`
**before** `ammo_fire` pushes `YOU DRAIN ORC -5 HP 9`. Both lines carry their numbers, so the
order is readable.

## 3. Strings

Packed sizes are textpack's. Char deltas are exact. Byte savings are estimates: `THE ` is
probably a single dictionary token, so each drop saves about 1–2 packed B, not 4.

| id | old | new | chars |
|---|---|---|---|
| `you_hit` | `YOU HIT THE ` | `YOU HIT ` | −4 |
| `you_miss` | `YOU MISS THE ` | `YOU MISS ` | −4 |
| `you_kill` | `YOU KILL THE ` | `YOU KILL ` | −4 |
| `spl_spark` | `SPARK HITS THE ` | `SPARK HITS ` | −4 |
| `spl_fire` | `FIREBOLT BURNS THE ` | `FIRE BURNS ` | −8 |
| `spl_frost` | `FROST HITS THE ` | `FROST HITS ` | −4 |
| `spl_drain` | `YOU DRAIN THE ` | `YOU DRAIN ` | −4 |
| `spl_light` | `LIGHTNING HITS THE ` | `BOLT HITS ` | −9 |
| `cmb_dag_hit` | `YOUR DAGGER HITS THE ` | `DAGGER HITS ` | −9 |
| `cmb_arr_hit` | `YOUR ARROW HITS THE ` | `ARROW HITS ` | −9 |
| `cmb_power` (today a filler in the hit-pre table) | `YOU POWER STRIKE THE ` | `YOU SMASH ` | −11 |

- **Total −70 chars. Estimated −25..−40 packed B**, which goes back to the bank-0 text/code
  reserve.
- **Kept as they are (0 B):** `the`, `hits_you`, `misses`, `cmb_drains`, `cmb_parries`,
  `cmb_unaffected`, `spl_hit_self`, `spl_burn_self`, `spl_drain_heal`, the trap lines,
  `fall`, `cure`, and the P3 Tome lines.
- **New text: 0 B.** The ` HP ` piece is 4 ASCII bytes of code data next to the helper (see
  §4). Plain ASCII is a valid log stream, because `tk_get` passes chars below $80 through.
- **Build ASSERTs** (replace the current ones in `lowram.asm` / `abil_ammo7.asm`):
  - `TXL_<pre> + NM_LONG + 10 <= 31` for every hit/smash pre.
  - `TXL_YOU_KILL + NM_LONG + 4 <= 31`.
  - `TXL_THE + NM_LONG + TXL_HITS_YOU + 4 <= 31`, and the same with `TXL_CMB_DRAINS`.
  - `TXL_<id> + 4 <= 31` for every `msg_push_d` / `msg_push_h` id.
  - `MSG_BUF` is 32 B. A composed stream is ≤ its char count, so ≤ 31 + the terminator. ASSERT
    the worst char count, not the stream length.
- **Tests:** golden screens and ZRCP string asserts that expect `YOU HIT THE` / `YOU KILL THE`
  / `YOU MISS THE` / `… HITS THE` must be updated in the same change.

## 4. Implementation sketch (minimal bytes)

**Value carriers: 0 B of new RAM.**
- `LN_VAL` (1 B) = an alias of `deal_hit`'s `dh_lost`: the line's D or G.
- `LN_TIX` (2 B) = an alias of `dh_tix`: the struck body, whose `E_HP` gives H.

The helpers read these globals, so **bank-7 call sites only swap a call target and do not
grow** (bank 7 low has 0 B left). Fresh `deal_hit` callers get both values for free
(`melee_strike`, the immediate self/trap lines). Every other producer sets them just before
its line:

- **`show_impact_msg` (low RAM, melee lines shown at IMPACT):** it sets `LN_VAL` =
  attacker `E_HIT & $7F` and `LN_TIX` = the target IX (it already looks that IX up for hero
  lines).
- **`E_HIT` becomes "HP lost" instead of "1".** `do_attack` stores `L` at `.lost`
  (`ld a, 1` → `ld a, l`, same size). `do_impact` and `melee_bonk` only test it for
  non-zero, so their meaning is kept.
  - **Ranged monster shots** (`rg_pose`, E_HIT 0 today so the flash waits for the bolt)
    store `$80 | L`.
  - `do_impact` treats bit 7 as "no flash": `jp m, .nohit` after `or a`, +3 B in bank 2.
  - **Invariant:** melee `L` < 128. The largest hit is about 40, so no clamp is needed;
    note it in a comment.
- **`ammo_fire` kill / hit lines:** `LN_VAL` / `LN_TIX` must hold **`pf_tgt`'s** strike.
  - `proj_rel` (bank 3) restores them from `pf_lost` and the `pf_tgt` IX when later strikes
    have overwritten them. That is about 6 B, or 0 if `pf_tgt` is always the last strike
    resolved; the engineer checks.
  - `pf_lost == $FF` (parry) never reaches a tailed line.

**Routines.** They live in **bank 0 `b0_code`**, running while `BANK_TEXT` is paged, which
`impact_line`, `hit_line` and `msg_go` already do. They are called directly: no `farb`.
1. **`ln_tail`** (DE = write pointer, A = message class).
   - It returns at once if `LN_VAL` = 0.
   - Then it writes `' '`, the sign, and `msg_dec(min(LN_VAL, 99))`. `msg_dec` is in bank 2,
     always mapped.
   - If the class has HP and the target's `E_HP` ≠ 0, it adds `" HP "` + `msg_dec(min(E_HP, 99))`.
   - About 26 B including the clamp and the 4-B `" HP "` data.
2. **Class select in `impact_line`.** A compare chain on B decides the tail:
   - P_HIT and P_SMASH get `-D HP H`.
   - P_KILL, M_HIT and M_DRAIN get `-D`.
   - Every other code (miss, squeeze, status, parry, summon) gets nothing.
   - About 12 B, plus the call in `impact_line` (3 B low RAM).
   - **P_SMASH** is a new E_MSG code: `imp_pre`/`imp_post` gain 1 entry each (2 B), and
     `melee_strike` selects it when `ABF_DMGX2` is set (the flag is already read there).
     About 6 B in bank 7, so it must be found inside P3/GEAR slack or cut (cut 1).
3. **`hit_line` (bank 2):** add `call ln_tail` with the "HP" class before the terminator
   (+3 B).
4. **`msg_push_d` / `msg_push_h` (low RAM, 5 B each).**
   - `msg_push_d: ld de, ln_push_d / jr msg_go`, and `msg_push_h` likewise.
   - `ln_push_d` / `ln_push_h` live in bank 0 (≈ 16 B for both). They copy the stream HL to
     `MSG_BUF`, call `ln_tail` with the sign `-` / `+` and no HP, add the 0, and `jp log_push`.
   - Sites swap `call msg_push` for `msg_push_d` (0 B each): self bolt (`abil_spell7`),
     burst self (`proj3`), dart, stone, pit fall.
   - Heal sites compute G = new − old into `LN_VAL`, then call `msg_push_h`:
     - `deal_hit .heal`, bank 3: ~6 B.
     - Heal potion, `fx6` R6: ~6 B.
     - Cure, R6: ~4 B.
5. **Tome (P3):** the P3 hit site sets `LN_VAL` = 1 and points `LN_TIX`'s HP read at
   `TOME_HP`. If `ln_tail` cannot read a non-entity cheaply, use a third class "HP from
   (`LN_HPP`)" or let P3 append its own ` HP ` + `msg_dec`. About 4–8 B inside P3's
   bank-7 hits budget (55).

**Byte estimate.**

| Item | Bytes | Where |
|---|---|---|
| Core helpers (`ln_tail` 26, class select 12, `ln_push_d`/`_h` 16) | **~54** | bank 0 |
| Hooks (`show_impact_msg` loads ~10, `impact_line` call 3, `msg_push_d`/`_h` 10) | ~23 | low RAM (38 free) |
| `hit_line` 3, `do_impact` sign test 3 | ~6 | bank 2 (14 free) |
| Drain-heal G 6, `proj_rel` restore 0–6 | ~6–12 | bank 3 (25 free) |
| Potion 6, Cure 4, ranged `$80` 4 | ~14 | R6 (70 unassigned) |
| SMASH | ~6 | bank 7 |
| Tome | ~4–8 | P3 budget |
| **Total code** | **≈ 105–120 B** | |
| **Text** | **−25..−40 B** | packed |

- **Core only** (melee/spell/ammo/monster lines with tails, no heals/SMASH/Tome/ranged):
  **≈ 75 B code**.
- **Bank 0 is the pinch.** The 74-B text+code reserve is about 0 free. The string shrink
  pays roughly 25–40 B of the ~54. The rest needs the manager's **240-B pool-slack step**
  (`B0_CODE_RES` up to ~250 at the same cost, memory-map "M0 / post-3F ledger" L4), or the
  cut order below. If the step is taken, it covers LOG-DMG and the remaining L4 cold code
  together.

## 5. Cut order (cut from the top while bytes are short)

1. **SMASH:** Power Strike prints `YOU HIT N -D HP H` (−6 B bank 7, −2 B tables). The
   `cmb_power` shrink still happens, as a filler.
2. **Cure `+G`** (−4 B R6).
3. **Heal-potion `+G`** (−6 B R6).
4. **Drain Life caster `+G`** (−6 B bank 3). After cuts 2–4, heals print the bare line,
   and `msg_push_h` / `ln_push_h` go (−~10 B).
5. **Tome `HP H`:** keep `THE TOME SHUDDERS -1`, or no tail at all (−4–8 B).
6. **Ranged monster hit number:** `THE ARCHER HITS YOU` stays bare. This drops the
   `E_HIT` bit-7 code (−7 B).
7. **Hero self/trap/fall numbers** (`msg_push_d`, `ln_push_d`: −~13 B).
8. **Never cut (the core of the ruling):**
   - hero melee/kill `-D` with `HP H`;
   - spell/ammo `hit_line` `-D` with `HP H`;
   - monster melee `THE N HITS YOU -D`.

## 6. Test vectors

Deterministic setups for `tests/game.py`. "Ring line" = the decoded text pushed to the log
(assert it in the ring or on screen after the gate).

| # | Setup | Expected ring line(s) |
|---|---|---|
| 1 | Warrior hits Goblin hp 6 for 4 | `YOU HIT GOBLIN -4 HP 2` |
| 2 | same, Goblin hp 2, roll 5 (overkill) | `YOU KILL GOBLIN -2` |
| 3 | Rat hp 3, any hit ≥ 3 | `YOU KILL RAT -3` |
| 4 | hero misses Orc | `YOU MISS ORC` |
| 5 | Goblin hits hero for 3 | `THE GOBLIN HITS YOU -3` (no HP part) |
| 6 | Vampire bite for 4 | `THE VAMPIRE DRAINS YOU -4` |
| 7 | Goblin misses | `THE GOBLIN MISSES` |
| 8 | Spark on Orc hp 14, 5 dmg | `YOU CAST SPARK`, `SPARK HITS ORC -5 HP 9` |
| 9 | Firebolt on Boneguard hp 30, 12 dmg | `YOU CAST FIREBOLT`, `FIRE BURNS BONEGUARD -12 HP 18` (30) |
| 10 | Lightning, Deathlord hp 50, 14 dmg | `BOLT HITS DEATHLORD -14 HP 36` |
| 11 | dagger on Boneguard, forced HP 99 / dmg 99 (ASSERT case) | `DAGGER HITS BONEGUARD -99 HP 99` (31) |
| 12 | Power Strike on Ogre Lord hp 40, 15 dmg | `YOU SMASH OGRE LORD -15 HP 25` (after cut 1: `YOU HIT …`) |
| 13 | Whirlwind: Goblin hp 6 (3 dmg) left, Rat hp 2 (4 dmg) right | `YOU HIT GOBLIN -3 HP 3`, `YOU KILL RAT -2` (slot order) |
| 14 | Death Knight parries | `THE DEATHLORD PARRIES!` (no tail) |
| 15 | immune target (I) | `THE WRAITH IS UNAFFECTED`, then the impact line **without** tail (D = 0) |
| 16 | Drain Life, Orc hp 14, 5 dmg, hero 3 below max | `YOU FEEL HEALTHIER +3`, `YOU DRAIN ORC -5 HP 9` |
| 17 | Drain Life at full HP | `YOU FEEL HEALTHIER` (bare), `YOU DRAIN …` |
| 18 | Heal potion, hero 20/30, heal 8 | `YOU FEEL HEALTHIER +8` |
| 19 | Cure potion, hero at max | `YOU ARE CURED` (bare) |
| 20 | own Firebolt burst, 4 dmg | `THE BURST SCORCHES YOU -4` |
| 21 | Lightning bounce onto hero, 6 dmg | `THE BOLT HITS YOU -6` |
| 22 | dart trap, 3 dmg | `A DART HITS YOU! -3` |
| 23 | Archer arrow hits hero for 4 | `THE ARCHER HITS YOU -4`; the hero flashes on the bolt tick, not at the attack IMPACT (bit-7 rule) |
| 24 | Tome hit, `TOME_HP` 5 → 4 | `THE TOME SHUDDERS -1 HP 4`; 5th hit `THE TOME IS DESTROYED` |
| 25 | poisoned hero, tick | no new line |
| 26 | Lightning pierces A (pf_tgt) then B | the line's numbers are A's, not B's |
| 27 | `dh_lost` 120 (synthetic, test probe) | `-99` |
| 28 | `YOU SQUEEZE PAST THE RAT` (input phase) | unchanged, no tail |

Regression: every composed line ≤ 31 (ASSERT plus a test sweep of all kinds × all pres),
`LQ_DROP` unchanged on the existing 4-monster faint and Whirlwind scenarios.

## 7. UB3 log-line gaps to fix in the same pass

From the plan's UB3 (Firebolt cast missing). LOG-DMG touches the same composers, so these
are fixed or ruled on here:

1. **`YOU CAST FIREBOLT` missing.**
   - `act_begin` drops the cast line when `LOG_QN >= CAST_LINE_MAX` (3), and `log_room` can
     replace it when it is the newest pending line and the ring is full (burst-self + hit +
     status lines).
   - **Ruling:** the cast line is never the line that is replaced. `log_room` replaces the
     newest pending line **unless it is the cast line pushed this action**; then it drops the
     incoming non-result line instead. If that costs > 8 B, keep it simpler: lower nothing,
     but make the Firebolt burst-self line (`THE BURST SCORCHES YOU`) the droppable one.
   - The engineer first confirms the cause with a ZRCP ring trace (push counter + `LQ_DROP`)
     on a Firebolt into a 2-body cluster next to the hero. The 2-row log scrolling a
     pushed-but-shown-for-1-tick cast line also looks "missing": `LT_HOLD` must hold it ≥
     `LOG_HOLD_MIN` ticks. The test asserts the ring, not the screen.
2. **Secondary bolt targets** (Lightning pierce/bounce, Firebolt burst) print no line.
   - **Ruling:** non-lethal secondary hits stay silent (the readout and later the flying
     numbers show them).
   - A **secondary kill** prints `YOU KILL N -D` through `log_room` (XP must be explained).
     About 8–10 B in bank 3, **outside** the LOG-DMG core: it goes in the cut order after
     item 7.
3. **Whirlwind with no target** (if it can fire at all): `YOU SPIN IN A WHIRLWIND` (existing
   `cmb_whirl`, 0 text B, ~5 B code). If it cannot fire without a target, nothing to do.
4. **Power Strike / Whirlwind cast lines:** none, by design (their per-target lines name the
   act; the hit-pre filler slots stay fillers).
5. **Everything else in the UB3 audit** (pickup/drop, status apply, level-up, traps, hunger):
   no gap found in game.md §3.4/3E tables; the junior's audit lists any event whose code
   path never calls a push, against those tables.
