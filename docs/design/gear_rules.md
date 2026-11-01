# GEAR1 / GEAR2 / GEAR3 — gear gates, random numbers, Enchant any item (designer, 2026-11-01)

Status: **spec for implementation.** Turns the user-accepted defaults of 2026-10-31 (plan.md
"POST-3F": GEAR1, GEAR2, GEAR3) into exact rules. Supersedes, for gear only: game.md §8 Enchant
line, §8.9 `ISTATE` bits 0–2 ("reserved"), §8.11 "3E simplification" item 1 (fixed stats,
"Enchant = worn weapon only", "a floor item is always m 0") and the [stems_fx] `glows` line.
Budgets are the M0 ledger's (memory-map.md "M0 / post-3F ledger").

Shared terms:
- **m** = `ISTATE` bits 5–7, signed −4..+3 (used −3..+3). Changed only by Enchant (+1) and
  §8.10 wear (−1; a wear event at m = −3 destroys the item). Unchanged by this spec.
- **q** = `ISTATE` bits 0–2, signed 3-bit two's complement (−4..+3; used −1..+2). Set once at
  generation, never changes. New.
- **v** = m + q, the item's total offset on its main stat. Bits 3–4 (`IST_ENCH_*`) stay 0, unused.
- **Numeric gear** = types `IT_WPN_LO..IT_HELM_HI` (19..36): weapons, armour, helmets.
  Charms (37..43) are never numeric: no q, no m, never enchanted, never gated.

---

## 1. GEAR1 — class gear gate (all-or-nothing)

### 1.1 Type classes (ids from `src/item_defs.asm`)

| Slot | METAL (blocks Mage spells) | CLOTH (blocks Warrior power attacks) | NEUTRAL | UNIQUE (exempt) |
|---|---|---|---|---|
| weapon 19–26 | — | — | all (weapons are class-locked anyway) | Cleaver 22, Bone Staff 26 |
| armour 27–32 | **CHAIN 29, PLATE 30** | **ROBE 27** | LEATHER 28 | SILK 31, GRAVE 32 |
| helmet 33–36 | **HELM 34** | **HOOD 33** | — | KING 35, MIRROR 36 |
| charm 37–43 | — | — | all 7 | SCARAB 42, GRAVE RING 43 |

All uniques are exempt (incl. the King Helm, which looks like metal). Scrolls, books, potions,
food, the bow and ammo are never gated.

### 1.2 Rule

- **Mage banned** ⇔ worn armour ∈ {29, 30} **or** worn helmet = 34. A banned Mage cannot cast any
  of the 5 spells (`ABL_SPARK..ABL_LIGHTNING`). Staff melee is allowed. Test: `armour − 29 < 2`
  unsigned, `helmet == 34`.
- **Warrior banned** ⇔ worn armour = 27 **or** worn helmet = 33. A banned Warrior cannot use
  Power Strike or Whirlwind (`ABL_POWER`, `ABL_WHIRL`). Plain melee, daggers and the bow are allowed.
- Equipping is never refused, and the stats do not change. The gate only bites at use.
- **Where:** `intent7.asm ic_abil`, right after the NOT LEARNED test and before `ic_disp`. That
  is the single entry for class abilities, and daggers and the bow enter `ic_disp` directly, so
  they are not gated. Check order: **NOT LEARNED → GEAR → (abil_load) → AFRAID (melee) → NO MANA
  → NO TARGET.**
- **Refusal:** `ic_no` with `TX_GEAR_BAN`. This gives the line + `SFX_NO` (fizz) +
  `IC_REFUSED`: **no turn, no MP spent, no sequence**. There is no icon or panel cue (accepted
  default).
- **Code:** `gear_ban` in bank 7: In: nothing. Out: CF = 1 banned. Clobbers: A, F (HL allowed).
  The routine plus its one call site must be ≤ **27 B**, so that GEAR2's 3 B in `pickup7.asm`
  fit inside the ledger's GEAR1 30 B (bank 7 low has 0 B slack).

### 1.3 Generator: class-gated armour (new; needed by GEAR1)

Without this, from D3 about 20 % of the Mage's gear finds are banned junk, and the Mage has no
armour progression at all. The fix is to tag the §8 table in the same way as the weapons and
add the two start-kit armours as finds:

| `ig_gtab` / `GEAR_TABLE` row (id order) | first depth | class |
|---|---|---|
| LONG 20 · AXE 21 | 2 · 4 | W |
| IRON 24 · RUNE 25 | 2 · 4 | M |
| **ROBE 27** (new) | 1 | **M** |
| **LEATHER 28** (new) | 1 | **W** |
| CHAIN 29 · PLATE 30 | 3 · 6 | **W** (was any) |
| HOOD 33 | 1 | **M** (was any) |
| HELM 34 | 1 | **W** (was any) |
| MIGHT 37 · WARD 38 · FIRE 39 · MANA 40 · PLENTY 41 | 2 · 2 · 2 · 3 · 3 | any |

Pool sizes:
- Warrior D1 2, D2 6, D3 9, D4–5 10, D6–8 11. These are **identical to today**: Hood is swapped
  for Leather.
- Mage D1 2, D2 6, D3 8, D4–8 9.

`rnd(len)` is always one ITEM_RNG step, so every draw stays aligned. Cost: +4 B data in the
bank-1 overlay (2 rows), 0 code (`GT_W` / `GT_M` already exist).

---

## 2. GEAR2 — per-instance offset q

### 2.1 Which items get q

| Items | q |
|---|---|
| Generated floor gear, numeric types (LONG, AXE, IRON, RUNE, ROBE, LEATHER, CHAIN, PLATE, HOOD, HELM) | rolled (§2.3) |
| Generated charms (MIGHT, WARD, FIRE, MANA, PLENTY) | **0**. The draw is still consumed |
| Start kit, boss uniques, monster drops, `DEBUG_KIT` | **0** |

### 2.2 Encodings

- **Bag / worn `ISTATE`:** bits 0–2 = `q & 7` (two's complement).
  `q = ((ISTATE & 7) XOR 4) − 4` (5 B: `and 7 / xor 4 / sub 4`).
  q −1 → `$07`, 0 → `$00`, +1 → `$01`, +2 → `$02`.
- **Floor entry:** `FL_QTY = 1 + (q & 7)`, so q −1 → 8, 0 → 1, +1 → 2, +2 → 3.
- **Pickup:** for every non-ammo pickup, `ISTATE = (FL_QTY − 1) & 7`, with no type test. Every
  other non-ammo writer already stores `FL_QTY` 1, which decodes to 0: potions, food, scrolls,
  books, the bow, uniques and drops.
  - **Invariant (assert in `items_model.check` and the drop paths):** a non-ammo entry has
    `FL_QTY` 1 unless it is generated numeric gear (1..8).
  - Code: `pickup7.asm .bag` passes `FL_QTY` in C (`inc l / ld c,(hl) / dec l`, +3 B bank 7).
    `pu_add` sets `B = 1` and `C = (C − 1) & 7` (+3 B R6).
- Gear never stacks, so the merge rule (TYPE + ISTATE) is not affected. EQUIP, REMOVE and swap
  copy the whole 3-B record, so q and m travel with the item.

### 2.3 Distribution (ITEM_RNG, after the trap step)

The q pass comes after `gen_traps`. It walks the FLOOR_LIST in list order, and for every entry
with `IT_GEAR_LO ≤ type ≤ IT_GEAR_HI` (only generated gear exists at this point):

```
w = rnd(8)                       # ITEM_RNG: one step, (x & $FF) mod 8
if type < IT_CHARM_LO:           # numeric gear
    s = w + ((depth + 1) >> 2)   # band b: D1-2 -> 0, D3-6 -> 1, D7-8 -> 2
    q = -1 + (s >= Q_T0) + (s >= Q_T1) + (s >= Q_T2)    # Q_T0 2, Q_T1 6, Q_T2 8
    FL_QTY = 1 + (q & 7)
# charm: FL_QTY stays 1
```

| Band (depth) | q = −1 | 0 | +1 | +2 | mean |
|---|---|---|---|---|---|
| D1–D2 | 2/8 | 4/8 | 2/8 | 0 | 0.00 |
| D3–D6 | 1/8 | 4/8 | 2/8 | 1/8 | +0.375 |
| D7–D8 | 0 | 4/8 | 2/8 | 2/8 | +0.75 |

- The same table applies to every numeric slot (weapon, armour, helmet). `Q_T0..Q_T2` are the
  balance knobs, as named constants (overlay EQU + `items_model.py`).
- The gear entries are contiguous: the gear step appends them. The Z80 may loop over that
  index range instead of type-testing; the result is identical.
- Every earlier draw is unchanged. The traps and every non-gear entry stay byte-identical to the
  pre-GEAR model for every seed and hero. Gear entries differ only in TYPE (the §1.3 pool) and
  QTY.
- Cost: bank 1 ≈ 22–26 B. The ledger has 18 + 19 spare.

### 2.4 Effect (`gear_dec`, R6)

- `gear_dec` uses **v = m + q** wherever it uses m today:
  - weapon: dmg bonus + v (Cleaver +1 on top);
  - armour / helmet with DEF: DEF + v;
  - Robe / Hood: max MP + v.
- The existing clamps apply: the summed DEF and gear MP are ≥ 0, and a melee roll is
  max(1, 1dN + bonus). There is no per-item clamp, as today with m: a −2 Helm lowers the total.
- Rune and Bone Staff: v changes the **melee** die bonus only. The spell bonus (+1 / +2) stays
  by type.
- Range: v −4..+5, a single signed digit.

### 2.5 Display (bag page `it_fmt`, R6)

- Prefix: if m = −3, show ` WORN OUT` (unchanged); else if v ≠ 0, show ` ±v`; then the existing
  numbers, which already include v through `gear_dec`. Examples:
  - Long Sword q+1: ` +1 1D8+1 ATK+1`
  - Chain q+2: ` +2 DEF+4`
  - Robe q−1: ` -1 MP+1`
  - Helm q−1 m−3: ` WORN OUT DEF-3`
- Names, pickup, equip and log lines are unchanged: no number in a name. The floor shows nothing.
- q is visible on the page from the moment of pickup (there is no ID system).
- Cost: R6 ≈ 20 B (gear_dec ≈ 10, it_fmt ≈ 6, pu_add 3). Ledger: 26.

### 2.6 Expected power curve (hand estimate, average policy; the sim confirms)

| By D8 entry | Warrior | Mage |
|---|---|---|
| numeric finds picked up (run) | ≈ 5.9 | ≈ 4.5 |
| Σ q over the worn numeric slots | ≈ +1.8 (dmg ≈ +0.6, DEF ≈ +1.2) | ≈ +1.3 (MP ≈ +0.9, staff melee ≈ +0.4) |
| Σ m from Enchant (≈ 2.2 reads, spread by §3) | ≈ +2.2 (≈ ⅓ weapon) | ≈ +2.2 (≈ ⅔ MP) |
| vs today (all Enchant to the weapon, ≤ +3 dmg) | +≈1 point total, more defensive | +≈1 point, minus the lost Chain/Helm DEF |

- **GEAR1 nerfs the sim Mage.** `balance_sim.gear_score` equips Chain (6 > Robe 3) and Helm
  (3 > Hood 1.5) today. That is ≈ DEF 1–2 lost from mid-game, which the sim could not see before.
- Net hand estimate vs the BAL-1 post-A figures (M ≈ 60 %, W ≈ 47 %): Mage −5..−10 pp, Warrior
  +2..+4 pp. The gap closes to ≈ 0–5 pp, and both stay at or above the band, so BAL-1's knob list
  still applies.
- **Gate:** if the average win rate is outside 35–45 % or |W − M| > 5 pp, move `Q_T0..Q_T2`
  first (D7–8 mean +0.75 → +0.375 by `Q_T1` 6 → 7). Then use BAL-1 §3.2's knobs, in its order.

### 2.7 Simulator / model changes (required)

**`tools/items_model.py`:**
- the §1.3 `GEAR_TABLE`;
- the §2.3 pass after `gen_traps` (`Q_T0/1/2`);
- `check_items`: gear qty 1..8 (numeric) / 1 (charm), q within the band's support, the
  non-ammo-qty-1 invariant;
- `apply_block` unchanged (it writes qty).

**`tools/balance_sim.py`:**
- floor gear carries q (from `items_model` or the same table on the sim RNG);
- `equip_consider` never equips a type banned for the hero (§1.2);
- `gear_score` uses base + v (weapon avg + v; df + v; Robe/Hood mp + v);
- per-item m replaces `h.ench`, Enchant per §3;
- the bag fallback may be approximated as "wasted": the sim keeps no bag gear.

---

## 3. GEAR3 — Enchant hits a random worn item

### 3.1 Algorithm (`enchant_any`, R6; replaces `enchant_weapon`)

This runs inside `fx_read` **after** the line `YOU READ THE ENCHANT SCROLL` and **after**
`bag_take` has removed the scroll and compacted the bag. Bag indices are the post-take ones.

1. **Worn candidates**, in slot order WEAPON, ARMOUR, HELMET (never CHARM): TYPE ≠ `IT_NONE`
   and m ≠ +3 (`ISTATE & $E0 ≠ $60`). Uniques and banned (§1) items qualify. Fists (an empty
   weapon slot) do not.
2. If n ≥ 1: `k = rng_mod(n)` (gameplay RNG). The k-th candidate gets m + 1 (`ISTATE += $20`;
   q bits untouched; it cannot overflow because m ≠ +3). Then `hero_recalc`, then the line. Done.
3. Else **bag candidates**, in bag slot order 0..19: TYPE in `IT_WPN_LO..IT_HELM_HI` and m ≠ +3.
   Excluded: charms, the bow, books, scrolls, food, potions. If n ≥ 1: `k = rng_mod(n)`, m + 1,
   **no** `hero_recalc`, then the line. Done.
4. Else `NOTHING HAPPENS`, with 0 RNG draws.

In every case the scroll is consumed and the turn is used (`fx_turn`, 1 turn), from the page or
the quick slot alike.

- **Line:** `fx_line(A = target type, E = S_FX_ENCHANTED)` gives `ENCHANTED: <name>`.
- **Byte-exact draws (gameplay `RNG_STATE`):** none for step 4, else exactly one `rng_mod(n)`.
  `rng_mod` (io.asm) works as follows: `mask` = (n − 1) smeared to 2^k − 1; repeat
  `rng_next`, `a = L & mask`, until `a < n`.
  - n = 1 or 2: exactly 1 `rng_next`;
  - n = 3: 1 or more (rejects `a = 3`);
  - bag n ≤ 19: mask 1/3/7/15/31.
- Python model: `while True: x = step(); a = x & 0xFF & mask; if a < n: return a`.
- Cost: R6 ≈ 40 B (ledger 40). The stem change saves 7 B (§4).

### 3.2 Interactions

- **BUC / cursed:** BUC does not exist (rev 6), so there is no blessing branch.
- **m cap +3** applies to m only; q comes on top. Max v = +5 (q +2, m +3).
- **Wear (§8.10):** NOTCH and ACID still lower m by 1, and destroy at the next event when m = −3,
  whatever q is. An item at m −3 is an Enchant candidate (m → −2, and ` WORN OUT` goes away).
  Shatter does not exist.
- **Rune / Bone Staff:** Enchant raises the melee bonus only (the page shows it in `1D4+n`). The
  spell bonus stays by type.
- **Robe / Hood:** m + 1 gives max MP + 1 through `hero_recalc` (MP is not refilled; the
  existing rule).
- **GEAR1:** enchanting never changes a gate. A banned item stays banned.
- **ID / reveal:** none. q and m are always shown on the page.
- **Quick SCROLL slot:** the same `fx_read` path, so the same rules apply.

---

## 4. Strings

| Id / where | Text | Chars | Bytes |
|---|---|---|---|
| `gear_ban` (`src/strings.txt`, bank-0 `TEXT_RES`) | `YOUR GEAR FORBIDS IT` | 20 | **≤ 21 raw** of the 45 B reserve (24 left for P3 / STATS1) |
| `enchanted` (`src/items.txt` [stems_fx], R6) **replaces** `glows` `YOUR WEAPON GLOWS!` | `ENCHANTED: ` | 11 | 12 vs 19: **−7 B R6** |
| composed max | `ENCHANTED: WARLORD CLEAVER` | 26 | ≤ 31 ✓ |
| HOW TO PLAY row 22 (boot block, 0 resident) | `ENCHANT GIVES A WORN ITEM +1.` | 29 | replaces `ENCHANT MENDS A WORN WEAPON.` |

There are no other new strings. `NOTHING HAPPENS` and the `YOU READ THE` stem already exist.

---

## 5. Byte summary vs the ledger

| Region | Spend | Ledger |
|---|---|---|
| bank 7 low | GEAR1 ≤ 27 + GEAR2 pickup 3 = 30 | GEAR1 30 |
| R6 | GEAR2 ≈ 20 + GEAR3 ≈ 40 − stem 7 ≈ 53 | GEAR2 26 + GEAR3 40 = 66 |
| bank 1 overlay | GEAR2 pass ≈ 22–26 + 2 pool rows 4 | GEAR2 18 (+19 spare) |
| bank 0 text | 21 | 45 reserve |

---

## 6. Test vectors

`I` = ISTATE hex. "Draws" = gameplay `rng_next` calls. Kits are set via ZRCP pokes unless noted.

| # | Setup | Action | Expect |
|---|---|---|---|
| G1-1 | Mage, Spark learned, MP 12, armour CHAIN | cast Spark | log `YOUR GEAR FORBIDS IT`, SFX_NO; MP 12; turn counter unchanged; no sequence |
| G1-2 | Mage, helmet HELM (DEBUG_KIT Helm equipped) | cast Spark | as G1-1 |
| G1-3 | Mage, armour PLATE, Spark **unlearned** | Firebolt (unlearned) | `NOT LEARNED` (checked first) |
| G1-4 | Mage, CHAIN, MP 0 | cast Spark | GEAR line, not `NO MANA` |
| G1-5 | Mage, MIRROR HELM + GRAVE CLOAK; / SILK; / KING; / LEATHER | cast Spark | cast accepted |
| G1-6 | Mage, CHAIN | staff melee (walk into a monster) | attack happens |
| G1-7 | Warrior, armour ROBE; / helmet HOOD | Power Strike; Whirlwind | GEAR line, no MP, no turn |
| G1-8 | Warrior, ROBE, daggers 3, bow + arrows | throw dagger; shoot; sword melee | all accepted |
| G1-9 | Warrior, KING HELM + LEATHER | Power Strike | accepted |
| G2-1 | `items_model`, all seeds × both heroes | gear pass on/off | traps + all non-gear entries byte-identical; extra ITEM_RNG steps = number of gear entries |
| G2-2 | 16,000 levels | q histogram per band | within ±2 pp of 2/4/2/0, 1/4/2/1, 0/4/2/2 eighths; charms always qty 1 |
| G2-3 | floor HELM `FL_QTY` 8 | pick up | bag `I` = $07; page ` -1` only (DEF 1 − 1 = 0: `fopt` prints nothing for 0) |
| G2-4 | floor CHAIN `FL_QTY` 3, equip, Warrior otherwise plain | page; `HERO_DEF` | ` +2 DEF+4`; HERO_DEF = 4 + helm |
| G2-5 | worn LONG `I` $01 | `hero_recalc` | KT_BONUS[hero] = +1, KT_DIE 8 |
| G2-6 | worn ROBE `I` $07 | `hero_recalc` | GEAR_MP = 1 |
| G2-7 | boss unique drop / potion / food pickup | pick up | `I` = $00 |
| G2-8 | worn HELM `I` $A7 (m −3, q −1) | page | ` WORN OUT DEF-3`; total DEF clamps ≥ 0 |
| G2-9 | Warrior D1 pool / Mage D3 pool | `gear_pool` | [LEATHER, HELM] / [IRON, ROBE, HOOD, MIGHT, WARD, FIRE, MANA, PLENTY] |
| G3-1 | worn SHORT `I` 00, LEATHER `I` $60, HELM `I` 00; RNG seeded so the 1st `rng_next` L is even | read Enchant | n = 2, 1 draw, k = 0: SHORT `I` $20; `ENCHANTED: SHORT SWORD`; KT_BONUS +1 |
| G3-2 | same, L odd | read Enchant | HELM `I` $20; HERO_DEF +1 |
| G3-3 | weapon, armour, helmet all `I` $60; bag [ENCHANT, HEAL, CHAIN `I` $02] | read Enchant | scroll taken first; bag candidates [CHAIN at slot 1], 1 draw; CHAIN `I` $22; HERO_DEF unchanged; `ENCHANTED: CHAIN MAIL` |
| G3-4 | worn all `I` $60 (or empty) and the charm only; bag without gear | read Enchant | `NOTHING HAPPENS`; 0 draws; scroll gone; 1 turn |
| G3-5 | fists, no armour, no helmet, worn MIGHT RING; bag HOOD | read Enchant | the charm is not a candidate; HOOD enchanted |
| G3-6 | 3 worn candidates; RNG with 1st L & 3 = 3, 2nd = 1 | read Enchant | 2 draws, the ARMOUR item enchanted |
| G3-7 | worn MIRROR HELM `I` 00, other slots $60 | read Enchant | MIRROR `I` $20 (uniques qualify), DEF 3 |
| G3-8 | worn CHAIN `I` $A0 (m −3) only candidate | read Enchant | `I` $C0 (−2), ` WORN OUT` gone |
| G3-9 | worn HELM `I` $42 (m +2, q +2) | read Enchant | `I` $62; page ` +5 DEF+6`; a 2nd Enchant skips it |
| G3-10 | quick SCROLL slot = Enchant, G3-1 setup | use quick slot | same result as G3-1 |

---

## 7. Doc sync (with the implementation)

- game.md: §8 Enchant line and the gear table (q), §8.9 bits 0–2, §8.11 "3E simplification"
  item 1 (point to this file), the (3) messages table (`ENCHANTED:` / `YOUR GEAR FORBIDS IT`),
  §3.2.1 row 22.
- items.txt: `glows` → `enchanted`.
- item_defs.asm: `IST_Q_MASK` = `%00000111` replaces `IST_RSVD_MASK`.
- `items_model.py` docstring step 8 (q pass).
- Regression risk: tests that equip the `DEBUG_KIT` Helm on a Mage and then cast.
