# WazHack/ZX — Game mechanics (M1, Stage 2)

> Game-designer deliverable. **Authoritative mechanics for Stage 3.**
> **Rev 2 (2026-10-01):** user answers applied. 8 levels; 2 unique bosses + golden bosses;
> monster resistances and Drain Life; projectiles and impacts are real sprites; black walls
> with dithered brick patches (concept-screen §3.3).
> It supersedes `prototype.md` wherever they differ. Anything not restated here keeps the
> PROTO rule: turn phases §3.2, ladders §3.4, the follow and materialise rules §3.7, F9
> zoning §4, frame rules §5.1–§5.4, line of attack §6.1, AI §6.4, the animation state
> machine §7. `foundations.md` F1–F9 still bind.
> Inputs: `plan.md` Stage 2, `budget.md`, E0 (logic runs in the input tick; heavy fight
> 125k T = 88 %), the user decisions (ZX0 sources, cold code out of bank 2, per-level pool)
> and the artist's round-2 measurements. Layout: `concept-screen.md`. The engineer assigns
> bytes and addresses in `memory-map.md`. **E** = estimate, **M** = measured.

---

## 1. Run structure

| Item | Decision | Why |
|---|---|---|
| Levels | **8** (D1–D8), each freshly generated, one way down | user wants it longer: ~65 rooms, **~60–65 min**; one level resident at a time |
| Level | **3×3 grid of room cells, 7–9 rooms** | ~1 KB of level state (budget §6) |
| Room | one screen, **2 storeys of 9 rows** (8 air + 1 floor) + 6-row panel (§2.1) | user decision; 2 jump rows |
| Going back up | **no**; the arrival shaft top is rubble | the previous level is discarded with its pool |
| Save | **none; permadeath**. Death → death screen (`KILLED BY … ON D5, TURN n`) → main menu | user |
| Seed | master seed = `FRAMES` when START is pressed; level seed = f(master, depth). Test flag `SEED_FIXED` forces the compile-time seed (F3) | a fixed seed would replay the same dungeon every game |
| Win | D8: kill the **Necromancer Archmage** → the Sanctum seal opens → **destroy the Book of Absolute Death Magic** (§1.3) → `GS_WIN` | user |

### 1.1 Generation rules (F6, per level, deterministic from the level seed)

| Step | Rule |
|---|---|
| Tree | random DFS spanning tree over the 3×3 cells from a random start, 7–9 rooms, + 0–1 extra edge (a loop). Leaves = **dead-end rooms** |
| Edges | horizontal: open edge on storey `s ∈ {0,1}`; **1 in 3 carry a door** (§2.3). Vertical: up-exit `{c,0}` below + down-exit hole `{c,2}` above, same `c` |
| Start | the DFS root, 0 monsters. D2–D8: arrival shaft from above, rubble-capped |
| Lair | the farthest leaf (BFS) with a horizontal tree edge: boss + **level exit** = down-shaft `{c,2}` under a **GRATE** that opens when the boss dies |
| Key room | the farthest other leaf (else the farthest non-start room): holds the **level key**. The lair edge is a **locked door** |
| D8 Sanctum | an extra leaf off the lair behind a **sealed door** (opens on the Archmage's death); holds the Book. D8 has no exit |
| In-room | 1–2 internal ladders `{c,1}`, `c ∈ 3..26`, ≥ 4 cols from ladders/pits · optional **pit** (3 cols, storey-0 floor, ≥ 3 clear cols on each side) · optional **dead-end block** (2–3 wall cols at an exitless edge, rubble at its foot) · decor **re-derived from the room seed** (never stored; rules in concept-screen §3.3) |
| Reachability | storeys span the full width except pits and edge blocks; ≥ 1 internal ladder; a pit is always jumpable, and falling only leads to storey 1. The hero can reach every exit; monsters may be cut off by a pit (intended) |
| Stored per level | room descriptors (exits, ladders, pits, blocks, door/grate bits), the floor-item list, the 16 entity slots. Population §9.4, items §8.5 |

### 1.2 Level themes: colours and decor tilesets (attr-only; floor rows never under sprites)

| Depth | Scheme | `ATTR_FLOOR` | `ATTR_WALL` (air band) | Tileset |
|---|---|---|---|---|
| D1 | Blue Keep | `$0F` | `$01` | 1 |
| D2 | Green Caves | `$27` | `$04` | 2 |
| D3 | Red Crypt | `$17` | `$02` | 3 |
| D4 | Orc Warrens (cyan) | `$28` | `$05` | 4 |
| D5 | Sandstone Tombs | `$30` | `$06` | 5 |
| D6 | Bone Catacombs (white) | `$38` | `$07` | 6 |
| D7 | Iron Fortress (bright blue) | `$4F` | `$41` | 7 |
| D8 | Sanctum (magenta) | `$1F` | `$03` | 8 (incl. lectern) |

- The legality set (prototype §4.3) becomes per-level: `ATTR_FLOOR[depth]`, `ATTR_WALL[depth]`.
- **Tile ids:** 64 = **32 common + 32 per-level decor slots**. At level start, a level's
  glyphs and attrs (32 × 9 B) are copied in from cold storage. 8 sets = 2,304 B, stored in
  bank 7 spare (§11.2).
- Walls are **black-background** with occasional dithered brick patches (concept-screen §3.3).

### 1.3 The Book of Absolute Death Magic

- The Book lies on a **2×2 lectern tile object** in the Sanctum. It **cannot be picked up**.
- **BOOK_HP = 5.** Every hit whose line reaches the Book removes 1: melee, power attack,
  spell, arrow or dagger.
  - It **ignores resistances** and is never missed.
  - Each hit flashes the lectern `$43` and prints a message.
- **Aura:** while the hero is within 6 cols on its storey, it deals 1 HP per turn (end of
  turn, ignores DEF).
- At 0 it turns to ash (rubble glyph) → `THE BOOK IS DESTROYED` → `GS_WIN`.
- It is a tile with an `ATTACKABLE` flag, not an entity.

---

## 2. Geometry and turn model

### 2.1 Storeys (replaces prototype §3.3)

- For storey `s ∈ {0,1}`: air rows `9s … 9s+7`, floor row `9s+8` (rows 8 and 17).
- Standing top for body height `h`: `y = 9s+8−h`. An entity stands iff `(y+h) mod 9 == 8`.
- Hero rows: 2–7 and 11–16. **Headroom over a 48-px body = 2 rows (16 px).** The panel is
  rows 18–23.
- Room map: 32×18 = 576 B, 6-bit tile ids.
- Ladder segments: `{c,0}` up-exit (rows 0–7), `{c,1}` internal (hole in row 8, rows 8–16),
  `{c,2}` down-exit hole (row 17). **A climb between storeys takes 9 turns.**
- Flyers: `9s ≤ y ≤ 9s+8−h`.

### 2.2 Turn loop (prototype §3.2 + E0)

- **Turn logic resolves in the input tick**: the player first, then monsters in slot order.
- Presentation keeps 25 Hz, 4 px tweens, 2 ticks per cell and hold-to-repeat.
- **Phase 1:** the player's action plays, including its projectile, any reflections, and its
  impacts and target reactions. **Phase 2:** all monster actions play concurrently, monster
  projectiles included. **Why:** logic resolved the player first, so a target must not
  visibly walk away from a bolt that already hit it. It also keeps monsters static, at zero
  render cost, while the player's spell flies (§9.3).
- End of turn, in order: pickups → aura → poison → hunger → regen → panel.

### 2.3 Actions and costs

| Action | Turns | Ticks (E) | Legal when |
|---|---|---|---|
| Walk 1 cell | 1 | 2 | standing; the box is free and inside the body limits; monsters never onto `x == pit col` |
| **Turn around** | **0** | 1 | always. The first ←/→ against your facing only turns you; held, the key then walks or attacks |
| Climb 1 row | 1 | 2 | prototype §3.4. **No attacks, casts, throws or shots while mid-ladder** |
| **Jump** (↖/↗) | 1 | 14 | §2.4 |
| Bump attack | 1 | 6–7 | a hostile in reach, facing it (prototype §6.1) |
| Use icon (FIRE tap) | 1 | per action | §3, §6 |
| Open door (bump it) | 1 | 2 | a closed door is adjacent in the facing direction. Locked: needs the key (consumed) |
| Close door (FIRE on the melee icon) | 1 | 2 | an open door is adjacent and faced, and no hostile is in reach |
| Wait (↓ where no ladder goes down) | 1 | 2 | always |
| Eat / drink (quick slot) | 1 | 2 | refused, at no turn, at FOOD = 100 (food) or HP = max (Heal) |
| Page verb (eat, read, equip…) | 1, applied on return to play | — | play is paused on the page |
| Fall (stepping onto a pit) | part of the walk | 2 + 9 | §2.5 |
| Exit room | part of the walk/climb | — | prototype §3.6 |

Illegal actions cost no turn (F4). A **frozen** entity skips its action.

### 2.4 Jump (user: agreed)

| Rule | Value |
|---|---|
| Input | ↖ / ↗ (keyboard: chord UP+LEFT / UP+RIGHT). A diagonal is **always** a jump |
| Distance | **6 cols**: body `x … x+2` → `x+6 … x+8` |
| Clears | cols `x+3 … x+5`: air, **a pit**, floor items, or a **low body** (`body_h ≤ 16`, ≤ 3 cols wide: Slime, or a Bat in the bottom 2 band rows) |
| Swept box | cols `x+1 … x+8`, rows `top−2 … bottom`. It must be free of walls, door/arch/lintel, blocks and non-low bodies |
| Landing | box `x+6 … x+8` free of bodies, inside the body limits (no exit by jumping), `x+6 ≠ pit col` |
| Cost | 1 turn + **2 FOOD** |
| Restrictions | standing only. **Not from a ladder** (landing on a hole is fine). Not when Weak. **Not two turns in a row**. Not while frozen |
| Arc | tick 0: JUMP1 (aligned). Ticks 1–12: JUMP2, x += 4 px/tick, y offsets −4,−8,−12,−16,−16,−16,−16,−16,−12,−8,−4,0. Tick 13: JUMP1 (aligned) |
| F9 | the body only rises inside its own storey's air rows (top ≥ `9s`) |

**Why 6:** the smallest jump that clears a 3-col pit and a 3-col low monster. "Not twice
in a row" caps flight speed at 7 cols per 2 turns.

### 2.5 Pits and falls (user: agreed)

- A pit is **3 cols** of black-paper cells in the **storey-0 floor only**, with
  `PIT_L`/`PIT_R` caps.
- The hero falls when its body is **exactly** over it (`x == pit col`).
- **Fall:** 9 rows at 8 px/tick to storey 1, same x, **1d4 damage** (ignores DEF). An
  occupied landing box puts that monster PENDING in place (prototype §3.6).
- Walkers never step onto `x == pit col`. Flyers ignore pits.
- F9: `px = col×8` while falling (snap invariant).

---

## 3. Controls

### 3.1 Joystick-only completeness (4 directions + diagonals + FIRE)

| Action | Joystick | Keyboard default (redefinable U/D/L/R/F) | Shortcut (never required) |
|---|---|---|---|
| Walk / turn / bump attack / open door | ← → | O P | — |
| Climb | ↑ ↓ at a ladder | Q A | — |
| Jump | ↖ ↗ | Q+O, Q+P | — |
| Wait | ↓ with no ladder below | A | `.` |
| Use the selected icon toward your facing | FIRE **tap** (fires on release, no direction pressed while held) | SPACE | ENTER |
| Move the icon cursor (no turn passes) | FIRE held + ← → (repeat after 10 ticks, then every 4) | — | `1`–`8` |
| Inventory page | FIRE held + ↓ (Warrior also: FIRE on the BAG icon) | — | `I` |
| Pause (Resume / Quit) | FIRE held + ↑ | — | BREAK |
| Page: move / verb / confirm / back | directions / ← → / FIRE / FIRE held + ↓ | same | — |
| Close door, hit the Book | FIRE on the melee icon / bump | — | — |
| Pickups | automatic at the end of a turn | — | — |

- ↙/↘ act as ←/→. Opposite keys cancel (F7). The cursor **skips unlearned slots**.
- **The Mage bar has no BAG icon:** its 8 slots are full (§6). The gesture is taught by the
  first-turn message `FIRE+DOWN: BAG`.

### 3.2 Main menu (bank 3, cold)

```
WAZHACK   1 START   2 HERO: WARRIOR|MAGE   3 CONTROLS: KEYS|KEMPSTON|SINCLAIR 1|SINCLAIR 2   4 REDEFINE KEYS
```

- **Number keys + ENTER always work.** Once a joystick is chosen, ↑/↓ + FIRE also work.
- **Kempston** (port `$1F`: bit 0 R, 1 L, 2 D, 3 U, 4 F) is read **only after it is
  selected**, because the port floats on a bare machine.
- **Sinclair 1** = keys 6 L, 7 R, 8 D, 9 U, 0 F. **Sinclair 2** = keys 1 L, 2 R, 3 D, 4 U, 5 F.
- Redefine asks for UP, DOWN, LEFT, RIGHT, FIRE (no duplicates).
- START seeds the RNG → generates D1 → play.

---

## 4. Classes

| Stat | **Warrior** (Knight art, `$47`) | **Mage** (Wizard art, `$45`) |
|---|---|---|
| HP / MP at start | 24 / 6 | 16 / 12 (10 + Robe 2) |
| atk / eva / DEF | 3 / 2 / 1 (Leather) | 1 / 1 / 0 |
| Melee | Short Sword 1d6, reach 1 | Oak Staff 1d4, reach 1, own **STAFF_SWING** frame. Never greys out (the 0-MP fallback) |
| MP regen | +1 per 8 turns | +1 per 5 turns |
| Mana use | 2 power attacks (§6.2) | 5 spells (§6.1) |
| Ranged | **throwing daggers** (range 6) + **bow** (range 14), §6.3 | spells |
| Start kit | 3 daggers, 8 arrows, 1 Heal, 1 Apple | 1 Heal, 1 Mana, 1 Apple |
| Class book per level | D1 Power Strike · D2 Vigor · D3 Whirlwind · D4–D7 Vigor | D1 Spark · D2 Firebolt · D3 Frost Shard · D4 **Drain Life** · D5 Lightning · D6–D7 Tome of Power |

- **Growth: no XP.** Progress comes from books, gear and boss kills.
- Each **boss kill: +3 max HP, +1 max MP** (current values too).
- **Tome of Vigor:** +3 HP, +1 MP. **Tome of Power:** +3 MP, +1 HP.
- **Why +3/+1, not rev 1's +4/+2:** there are 7 boss kills in 8 levels, and +4/+2 would
  overshoot (§10).

---

## 5. Learning from books

| Rule | Decision |
|---|---|
| Source | Abilities come **only** from books. Melee is always available |
| Placement | **Exactly 1 class book per level, D1–D7** (class-aware, table §4). **The D1 book lies in the start room.** D8 has none |
| Reading | Page verb `READ`, 1 turn on return. Learns the ability (fills its bar slot); the book is consumed |
| Other class's book | 50 % per level. `READ` → "YOU GRASP LITTLE OF IT": Warrior +1 max MP, Mage +2 max HP; the book crumbles |

---

## 6. Abilities, projectiles, damage types

**Projectiles and impacts are real sprites** (user preference). They are masked and
pre-shifted like any frame, but drawn under three restrictions:
- **spawned cell-aligned and moving in whole cells** (8 px/tick; Lightning 16), so each
  frame needs **one shift only**, class STATIONARY, pool = 2 × source;
- symmetric bursts skip the mirror;
- they are **render-only**: no entity slot, 0 kind ids. An FX track list holds
  `{frame, px, py, attr, path}`.

Arrows, daggers and the staff bonk are sprites too (the budget allows it, §11). Black
paper only (F9). They are drawn **after** bodies, and are redrawn on overlap like any
sprite. **≤ 3 tracks at once**; more are queued.

**Logic (instant at cast time):**
- The projectile travels cell by cell along its row in the facing direction, up to
  `range` cells in total.
- **Flight row** = caster top + 2 (staff tip / bow). If the hit body doesn't cover that
  row, it flies at the nearest row of that body.
- The **first body** whose box contains the row is struck. A mid-ladder body absorbs it
  harmlessly.
- At a **solid cell** (wall, closed door, block, lectern, room edge) it reverses if bounces
  remain (keeping the remaining range), else stops. An open exit edge ends it.
- **After any reversal, the caster is a valid target.**
- **Spells always hit unless the target is immune or reflects** (user); arrows and daggers
  roll F1.

### 6.0 Damage types and resistances (user)

| Type | Sources |
|---|---|
| **PHYS** | melee, power attacks, arrows, daggers, monster melee |
| **FIRE** | Firebolt (+ burst) |
| **COLD** | Frost Shard |
| **SHOCK** | Spark, Lightning |
| **DRAIN** | Drain Life, Ghost touch |
| **DARK** | Dark Bolt, Death Bolt |

| Response | Effect |
|---|---|
| N | ×1 |
| **R** resist | ×½, round down, min 1 |
| **I** immune | 0 and no side effect (no freeze, no heal); `UNAFFECTED` |
| **W** weak | ×2 |
| **X** reflect | 0 damage. A projectile **reverses at the reflector's front cell** and continues with its remaining range. This does **not** use a bounce, and it can strike the caster or others. A reflected type in **melee** counts as I |

- **Pierce + reflect:** Lightning stops piercing at a reflector and reverses there.
- **Loop guard:** max 4 reversals per projectile. Range is finite in any case.
- **Encoding (engineer):** per kind 6 × 2 bits {N, R, I, X} + a 6-bit W mask ≈ 3 B.
- **The hero uses the same format**, OR-combined from worn gear (best response wins).
- Falls and the Book's aura ignore resistances.

### 6.1 Mage spells (dmg ignores DEF)

| Spell | Book | MP | Range | Dmg / type | Bounces | Effect | Projectile → impact sprites |
|---|---|---|---|---|---|---|---|
| **Spark** | D1 | 1 | 6 | 1d4+1 SHOCK | 0 | — | spark_fly1/2 8×8 `$43` → spark_fizz1/2 8×8 |
| **Firebolt** | D2 | 3 | 12 | 1d8+2 FIRE | 0 | **burst**: bodies within 1 col of impact take 1d4 FIRE, **caster included** at point-blank | firebolt_fly1/2 16×8 `$46` → firebolt_burst1/2 16×16 |
| **Frost Shard** | D3 | 3 | 12 | 1d6 COLD | **1** | **freeze 2 turns** (bosses 1); can freeze the caster after a bounce | frost_fly 8×8 `$45` → frost_crack 16×16 |
| **Drain Life** | D4 | 3 | 5 | 1d6+1 DRAIN | 0 | **caster heals the damage dealt** (to max HP); useless on undead (I) | **drain_fly1/2 16×8 `$43` → drain_hit 16×16 (new art)**; the caster flashes `$44` |
| **Lightning** | D5 | 5 | 28 | 1d8+3 SHOCK | **2** | **pierces** (each body once per pass) | lightning_fly1/2 16×8 `$47` (16 px/tick) → lightning_flash 16×16 |

- Cast: CAST1 2 → CAST2 3 ticks, with the hero flashing the spell ink. The projectile spawns
  on the CAST2 tick. No per-spell cast frames.
- **Mage bar = staff + 5 spells + food + potion** (8 slots). Drain Life is **added**, not
  swapped for anything; the BAG icon leaves the Mage bar (§3.1).

### 6.2 Warrior power attacks (MP) and melee

| Ability | Book | MP | Target | Effect | Frames |
|---|---|---|---|---|---|
| Melee | — | 0 | in reach | F1/F2, weapon die, PHYS | Warrior WIND-UP → SLASH → FOLLOW; Mage CAST1 → **STAFF_SWING** + staff_bonk 16×16 |
| **Power Strike** | D1 | 3 | in reach | to-hit +2, **damage ×2** | WIND-UP → **POWER_STRIKE** 40×48 + power_burst 16×16 |
| **Whirlwind** | D3 | 4 | **every** hostile in reach, both sides | to-hit each, dmg +1 | **WHIRL** 40×48 + spark_fizz each side |

A power attack with no target is illegal (no turn, no MP).

### 6.3 Warrior ranged

| | Throw dagger | Bow |
|---|---|---|
| Ammo | `DAGGERS` 0–9 (counter) | `ARROWS` 0–30 (counter) |
| Range / to-hit / dmg | 6 / atk+1 / 1d4+2 PHYS | 14 / atk / 1d6+1 PHYS |
| Recovery | **always**: it lands under the impact cell or at the range end | consumed |
| Frames | WIND-UP → **THROW** 32×48 | **BOW** 32×48 |
| Projectile sprites | dagger_spin1/2 8×8 `$47` | arrow1/2 16×8 `$07` → arrow_hit 8×8 |

Both are legal with no target. Axe throwing is dropped (daggers only).

---

## 7. Stats, hunger, food

**Combat and mana:**
- To-hit: `d20 + atk ≥ 10 + eva` (F1).
- Physical damage: `max(1, roll × resist − DEF)`. Spells: `roll × resist`, no DEF.
- Nat-20/1 stays off.
- MP regen as §4, halted when Weak. Mana potion +8. Amulet of Mana / Scarab halve the regen
  interval.

**Hunger** (`FOOD` 0–100, start 80): burns −1 per **6 turns**, a jump −2 extra. **Never fatal.**

| Stage | FOOD | Effects | Bar attr |
|---|---|---|---|
| Fed | 50–100 | **HP +1 per 12 turns** (user: agreed) | `$44` |
| Peckish | 25–49 | no HP regen | `$46` |
| Hungry | 10–24 | atk −1, MP regen halved | `$42` |
| Weak | 0–9 | atk −2, eva −1, dmg −1 (min 1), no MP regen, no jump | `$42` + message every 50 turns |

| Food | FOOD | Source |
|---|---|---|
| Meat | +40 | floor (D2+), Orc drop 1/3 |
| Cheese | +30 | floor, Rat drop 1/4 |
| Pear | +20 | floor |
| Apple | +15 | floor, Goblin drop 1/4 |
| Carrot | +10 | floor |

Per level (E): ~450 turns ≈ 75 FOOD burned. Supply: 3–4 floor items + drops ≈ 100.

---

## 8. Items and inventory

- **Bag: 20 slots** (5×4 page grid), same-type stacks to 9.
- Ammo and the **level key** are counters outside the bag.
- Pickup is automatic. A full bag prints `BAG FULL`.

**Worn slots: 4** (user: agreed): weapon · armour · helmet · **charm** (ring *or* amulet).

| Item | Slot | Effect | Found |
|---|---|---|---|
| Short Sword / Long Sword / War Axe | weapon (W) | 1d6 / 1d8 atk+1 / 1d10 atk−1 | start / D2+ / D4+ |
| Oak / Iron / Rune Staff | weapon (M) | 1d4 / 1d6 / 1d4 + spells +1 dmg | start / D2+ / D4+ |
| Robe / Leather / Chain Mail / Plate | armour | MP+2 / DEF 1 / DEF 2 / DEF 3, MP regen ×½ | M start / W start / D3+ / D6+ |
| Hood / Helm | helmet | MP+1 / DEF+1 | D1+ |
| Ring of Might / Warding / Fire Ward | charm | atk+1 / DEF+1 / FIRE R | D2+ |
| Amulet of Mana / Plenty | charm | MP regen ×2 / FOOD burn ×½ | D3+ |

Weapons are class-locked; everything else is not.

**Consumables:**
- Potions: **Heal** +10 HP · **Mana** +8 MP · **Cure** (poison off, +4 HP).
- Scrolls (read on the page): **Teleport** (random free spot in a random room, never the lair
  while its boss lives) · **Fear** (the room's monsters flee 6 turns) · **Enchant** (weapon
  dmg +1, max +3).
- The **key** opens the lair door and is consumed.

**Quick slots auto-fill** (user):
- FOOD: the smallest FOOD value first.
- POTION: Heal, else Mana, else Cure.
- `QUICK` on the page pins a type until its stack runs out.
- Scrolls get no quick slot.

**Per level** (floor list ≤ 32 entries): food 3–4 · potions 2–3 (≥ 1 Heal) · scroll 1 ·
gear 1–2 (depth-gated) · class book 1 (D1–D7) · other-class book 0–1 · key 1 ·
Warrior ammo 2 stacks.

### 8.6 Bosses and unique gear (every level; never follow; death opens the grate)

| Depth | Boss | Kind | Unique drop |
|---|---|---|---|
| D1 | Golden Goblin King | golden Goblin | **Goblin King's Helm**: helmet DEF 1, eva +1 |
| D2 | Golden Spider Queen | golden Spider | **Silk Cloak**: armour DEF 1, eva +2, poison-immune |
| D3 | Golden Rotting Lord | golden Zombie | **Gravecloak**: armour DEF 2, DRAIN R, DARK R |
| D4 | **Ogre Warlord** | **unique** | **Warlord's Cleaver** (W: 1d10+1, atk+1) / **Bone Staff** (M: 1d6, spells +2) |
| D5 | Golden Pharaoh | golden Mummy | **Scarab Amulet**: charm, MP regen ×2, FOOD burn ×½ |
| D6 | Golden High Necromancer | golden Necromancer | **Ring of the Grave**: charm, DARK I, MP+2 |
| D7 | **Death Knight** | **unique** | **Mirror Helm**: helmet DEF 2, **DARK X** (reflects Dark/Death Bolts) |
| D8 | **Necromancer Archmage** | unique | none; its death unseals the Sanctum |

**Golden bosses** are a level kind with the `BOSS` flag.
- **Stats:** hp = 2×hp + 6, atk +2, dmg +1, DEF +1, resistances of the kind.
- **0 new frames, 0 pool.**
- **Gold glow:** the stamp attr cycles **`$06 → $46 → $47 → $46`**, 2 ticks per step
  (period 8 ticks ≈ 0.32 s).
  - On ticks when the boss is redrawn anyway, the stamp simply uses the current gold attr,
    at **0 extra cost**.
  - When it is stationary, only its **footprint attrs** are rewritten at ~0.12k T/cell
    (**M**, incl. the attr-only present copy): **~2.2k T per step** for a 3×6 boss, ≤ 2.9k
    for a 4×6 one. That is ≤ 1.5k T/tick on average.
  - Pattern: SYNC (all cells together) or a diagonal SWEEP. The artist picks; the cost is
    the same.
  - The hit flash overrides it. `$06`/`$46`/`$47` join the legality set.
  - Weight +1 (§9.3).

Uniques on the floor shimmer with the same cycle (it counts toward the room's attr-cycle
cells). Panel and page use hardware FLASH.

---

## 9. Monsters

### 9.1 Roster (13 kinds + 2 unique bosses + Archmage → `kind_tab` 32, §11.2)

Every monster gains **depth scaling**: hp + (depth − 1), atk + (depth − 1) div 3.

| Kind | Body px | hp | atk | eva | DEF | dmg | W | Move / flags | Behaviour | Drop | Depths |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Rat | 32×16 | 3 | 0 | 1 | 0 | 1d2 | 2 | walker | chase | Cheese 1/4 | D1, D2, D4 |
| Bat | 24×16 | 3 | 1 | 4 | 0 | 1d2 | 2 | flyer | erratic | — | D1–D3 |
| Slime | 24×16 | 6 | 0 | 0 | 1 | 1d3 | 2 | walker, acts every 2 | chase | — | D1 |
| Goblin | 24×32 | 6 | 1 | 1 | 0 | 1d4 | 3 | walker, climber, opener | chase | Apple 1/4 | D1, D2 |
| Spider | 32×16 | 7 | 3 | 3 | 0 | 1d4 | 2 | walker | hit **poisons** (−1 HP / 3 turns, ×3) | — | D2, D4, D5 |
| Skeleton | 24×48 | 10 | 2 | 2 | 1 | 1d6 | 5 | walker, climber, opener | chase | — | D3, D5, D8 |
| Zombie | 24×48 | 14 | 1 | 0 | 0 | 1d6 | 5 | walker, acts every 2 | hit poisons 1/4 | — | D3, D6, D8 |
| Ghost | 24×32 | 8 | 2 | 3 | 0 | 1d4 DRAIN | 3 | flyer | drift | — | D3, D6–D8 |
| Orc | 24×48 | 14 | 3 | 1 | 1 | 1d8 | 5 | walker, climber, opener | chase | Meat 1/3 | D4, D6, D7 |
| Skeleton Archer | 24×48 | 8 | 2 | 2 | 0 | 1d4; arrow 1d6 PHYS r10 | **6** | walker, climber, opener | ranged | Arrows ×3 1/2 (W) | D4, D5, D7 |
| Mummy | 24×48 | 18 | 3 | 0 | 2 | 1d8 | 5 | walker, acts every 2 | hit drains 5 FOOD | — | D5 |
| Necromancer | 24×48 | 12 | 2 | 2 | 0 | 1d4; Dark Bolt 1d6+1 DARK r8 | **6** | walker, opener | ranged, cooldown 2 | Mana 1/3 | D6–D8 |
| **Ogre Warlord** (unique) | **32×48** | 40 | 5 | 1 | 2 | 1d10+2 | **6** | walker, lair only | chase; every 3rd turn **SLAM**: reach 2, ×1.5 dmg | unique | D4 |
| **Death Knight** (unique) | 24×48 | 50 | 6 | 3 | 3 | 1d10+3 | 5 | walker, climber, lair only | chase; **parries** 1 in 3 PHYS hits (BLOCK frame, 0 dmg) | unique | D7 |
| **Necromancer Archmage** | 24×48 | 40 | 4 | 3 | 1 | 1d6; Death Bolt 1d8+3 DARK r28, 1 bounce | **6** | teleports, never walks | boss caster | — | D8 |

Opener = it can open closed doors (1 turn). Locked/sealed doors stop all monsters. The
Ogre and Death Knight scale by depth like the rest.

**Resistances** (N blank; R resist, I immune, W weak, X reflect):

| Kind | PHYS | FIRE | COLD | SHOCK | DRAIN | DARK |
|---|---|---|---|---|---|---|
| Rat, Goblin | | | | | | |
| Bat | | | | W | | |
| Slime | R | W | | | | |
| Spider | | W | | | | |
| Skeleton, Skeleton Archer | | | **I** | | **I** | I |
| Zombie | | W | **I** | | **I** | I |
| Ghost | R | | I | **X** | I | I |
| Orc | | R | | | | |
| Mummy | R | W | I | | I | I |
| Necromancer | | | R | | I | I |
| Ogre Warlord | R | | R | W | | |
| Death Knight | | **X** | I | W | I | I |
| Archmage | | | **X** | **X** | I | R |

Design intent:
- Undead shut off Frost and Drain, but burn.
- The Ghost bounces Lightning and Spark back at you.
- The Death Knight reflects Firebolt.
- The Archmage reflects Frost and Lightning, so the Mage must fight it with Firebolt and
  the staff, and the Warrior with steel.
- Reflected Death Bolts (Mirror Helm) deal ½ to the Archmage.

### 9.2 Behaviours (on top of prototype §6.4)

**Ranged** (Archer, Necromancer), first match:
1. In melee reach → melee.
2. Hero in line (vertical overlap, not mid-ladder), `gap ≤ range`, the first body in line
   is the hero, cooldown 0 → **shoot** (cooldown: Archer 1, Necro 2).
3. `gap < 3` → step away.
4. Otherwise, walker rules.

**AI and resistances:** a monster never fires at a body that reflects its type.

**Archmage** (never leaves the lair), first match:
1. Summon cooldown 0, < 2 summoned Skeletons, a slot free, and the cap allows → **summon a
   Skeleton** (cooldown 6).
2. Hero in line → **Death Bolt** (cooldown 2).
3. Hero adjacent → **teleport** to the other storey (cooldown 4; attr flash).
4. Melee, else wait.

**Ogre:** a SLAM turn plays RAISE → SLAM.
**Death Knight:** a parry plays BLOCK and prints `PARRIED`.

### 9.3 Encounter cap (budget §4 + E0; projectiles included)

- Render budget for a non-input tick ≈ 114k T. Contended cost after the double buffer:
  tall 27.7k, medium 18.9k, small ~12k, projectile 8×8/16×8 ~4–5k, 16×16 impact ~7k.
- **Weights (≈ 6k T per unit):** small 2 · medium 3 · tall 5 · **ranged shooter 6** (5 + its
  in-flight projectile) · Ogre 6 · **golden +1**.

| Rule | Value |
|---|---|
| **Phase 2** (monsters + their projectiles) | room **Σ weight ≤ 12 and ≤ 4 monsters**, current room, alive, incl. pending → ≤ 72k + hero idle |
| **Phase 1** (hero action + its projectile/impacts + reacting targets) | hero ~30k + projectile ~5k + impact ~7k + 1 reacting tall ~28k ≈ 70k. Lightning piercing several targets staggers the reactions by impact tick. A rare overlap → one 3-frame tick (no flicker with the double buffer) |
| Initial population | Σ ≤ 8 per room; start room 0; lair = boss + ≤ 1 escort, Σ ≤ 12 |
| Enforced at | generation, follow admission (prototype §3.7 step 3), summons, fear/teleport arrivals |
| Projectile tracks | ≤ 3 at once (queued beyond) |
| Overrun | presentation-only 3-frame tick; logic unaffected |

Followers: prototype §3.7 + this cap. **Bosses never follow.**

### 9.4 Per-level population (≤ 4 kinds + boss; hero + ≤ 15 slots)

| Depth | Kinds | Monsters (incl. boss) | Boss |
|---|---|---|---|
| D1 | Rat, Bat, Slime, Goblin | 11 | Golden Goblin King |
| D2 | Goblin, Spider, Bat, Rat | 12 | Golden Spider Queen |
| D3 | Skeleton, Zombie, Ghost, Bat | 12 | Golden Rotting Lord |
| D4 | Orc, Rat, Spider, Skeleton Archer | 13 | **Ogre Warlord** |
| D5 | Mummy, Skeleton, Skeleton Archer, Spider | 13 | Golden Pharaoh |
| D6 | Zombie, Ghost, Necromancer, Orc | 14 | Golden High Necromancer |
| D7 | Orc, Skeleton Archer, Ghost, Necromancer | 14 | **Death Knight** |
| D8 | Necromancer, Skeleton, Ghost, Zombie | 10 + Archmage (+ ≤ 2 summons) | Archmage |

---

## 10. Balance sketch

Monster hp × count rises ~25 % per depth (depth scaling + kinds). Boss and book growth
keeps pace.

| Depth | Hero at entry W HP/MP · M HP/MP | Threat | Key answer |
|---|---|---|---|
| D1 | 24/6 · 16/12 | soft | the D1 book in the start room |
| D2 | 27/7 · 19/13 | poison | Cure; Firebolt (Spider W) |
| D3 | 33/9 · 22/14 | first undead: Frost/Drain are useless | Firebolt (Zombie W); Whirlwind |
| D4 | 36/10 · 25/15 | archers, Ogre 43 hp | Drain Life on living Orcs/Ogre; close doors; bow |
| D5 | 42/12 · 28/16 | Mummy PHYS R, curse | Lightning; fire on Mummies; Scarab next |
| D6 | 48/14 · 31/17 | casters, ghost reflecting Lightning | Ring of the Grave; Firebolt on ghosts |
| D7 | 54/16 · 35/21 | Death Knight (parry, fire reflect) | Lightning (W); Power Strike through parries |
| D8 | 60/18 · 39/25 | Archmage + summons + bouncing bolt; reflects Frost/Lightning | Mirror Helm; Firebolt; potions saved |

**Sample duel (D1, Warrior vs Goblin):** 65 % to hit, 3.5 avg → ~2.6 turns, ~2.3 HP lost.
**Mage:** opening with 2 Sparks at range costs ~0 HP. Mana economy is ~90 MP per level.

**Run:** ~450 turns per level, ~3,600 turns ≈ 60–65 min.

**Tuning knobs, in order:** Heal amount, food per level, depth scaling, boss multiplier.
Verify with ≥ 5 seeds × 2 heroes before Stage 3 exit.

---

## 11. Asset and budget reconciliation

- Source = `W/8 × H × 2`. Pool: stationary = 2 × source; moving = 2 × source + 2 × source ×
  (cols+1)/cols; projectiles = 2 × source (one shift).
- Sources ZX0 ~1.7× (E).

### 11.1 Frame ids and bytes (new)

| Owner | Frames | Ids | Source raw | Pool |
|---|---|---|---|---|
| Monsters drawn **M**: Zombie, Mummy, Orc, Necromancer, Spider 5 each; Archer 4 (HURT/DEAD = Skeleton) | WALK×2, ATTACK, HURT, DEAD | 29 | ~8,000 **M** | 4.2–4.6 KB per kind, Spider 2.75 **M** |
| Mage drawn **M** | STAFF_SWING **40×48** | 1 | 480 | 960 |
| Warrior **M** (round 3) | JUMP1, JUMP2 24×48, POWER_STRIKE 40×48 (ax 4), WHIRL 40×48 (ax 8), THROW 32×48, BOW 32×48 | 6 | 2,304 | **5,568** |
| Mage **M** | JUMP1, JUMP2 | 2 | 576 | 1,920 |
| Archmage **M** | IDLE 24×48, CAST 40×48 (HURT = flash, DEAD = Necro) | 2 | 768 | 1,536 |
| **Ogre Warlord**, to draw | WALK1/2 32×48 (M), RAISE 40×48, SLAM 40×48, HURT 32×48, DEAD 40×16 | 6 | 2,272 | 6,464 |
| **Death Knight**, to draw | WALK1/2 24×48 (M), WIND-UP 32×48, CLEAVE 40×48, BLOCK 32×48, DEAD 40×16 (HURT = flash) | 6 | 1,984 | 5,504 |
| **Spell sprites, lean set M** (round 3) | Spark fly ×2 + fizz, Firebolt fly ×2 + burst, Frost fly + crack, Lightning fly ×2 + flash, Drain fly ×2 + hit (11 already drawn) | 14 | 464 | 1,696 |
| Other projectile/impact sprites **M** | power burst 1, necro bolt 3 (Death Bolt = same frames, `$43`), arrow 2 + hit 1, dagger spin 2 (4 → 2), staff bonk 1 | 10 | ~370 | ~740 |
| Golden bosses | recolour + glow | 0 | 0 | 0 |
| **Total new** | | **76** | **~17.2K raw → ~10.1K ZX0 (E)** | projectiles ~2.4 KB resident on every level |

### 11.2 Limits vs need

| Store | Budget limit | Need | Verdict / change |
|---|---|---|---|
| Frame ids | 28 free (`FRT_MAX` 96, 68 used) | 68 + 76 = **144** | **`FRT_MAX` → 160**: +64 × 16 B = **+1,024 B bank 2**. 16 spare |
| Kind ids | 16 | 2 heroes + Rogue hole + 12 monster kinds + Archmage + Ogre + Death Knight = **18** | **`kind_tab` → 32**: **+256 B bank 2**. The resistance table adds ~60 B (3 B/kind) |
| Bank 2 | ~0.87K + ~2.1K freed by the cold-code move ≈ 3.0K | FRT +1,024, kinds +256, resist ~60 = **1.34K** | Fits, ~1.6K left for new hot code. **The static frame descriptors (24 B/frame) must leave bank 2**: 146 × 24 = 3.5K. The engineer trims them to ≤ 12 B (W, H, ax, class/sym, source bank+offset) → 144 × 12 ≈ 1.75K, moved to **bank 5** next to the generator that alone reads them |
| Bank 5 low RAM | ~6.1K | generator + boot ~2.1K, ZX0 + `GEN_SRC` 0.6K, tile glyphs 0.6K, level state 0.6K, frame descriptors ~1.75K | ~5.65K, fits, **0.45K margin** |
| Sources + cold data (banks 1+3) | 32,768 − AY reserve | existing 16,899 → ~9.9K ZX0 + new ~10.1K ZX0 + menus code ~2.0K + icons ~2.7K → 1.6K ZX0 + strings ~2.9K → 1.7K ZX0 = **25.3K** | With AY at 8 KB (24.6K free): **0.7K over**. **Change: AY reserve 8 → 7 KB** (player ~2K + in-game music ~4K + FX ~1K still fit, budget §5) → 25.6K, ~0.3K margin |
| Bank 7 spare | 2,656 | **8 per-level tilesets 2,304** | Fits (cold, copied at level start; never drawn into bank 7) |
| Pool per level (0/4/6) | 49,152 − hero **18,176** (Knight 12,608 + Warrior 5,568 **M**) − straddle 1,728 − projectiles ~2.4K = **26.8K** | max **D7 22.8K** (§11.3) | **Fits, ≥ 4.0K slack** on every level. Build ASSERT per level |
| Tile ids | 64 | 29 common + ≤ 32 per level | fits (§1.2) |
| Render tick | ~114k T | §9.3 weights incl. projectiles; gold glow ≤ 1.5k/tick | by construction; E2 measures |

**Risk.** Sources are the tightest store, and the ZX0 ratio is an estimate. At 1.5× instead
of 1.7×, sources grow by ~2.3K. The levers, cheapest first:
1. Arrows/daggers/bonk back to 8×8 glyph cells: −6 ids, ~0.3K.
2. Monster HURT → flash: −5 ids, ~1.4K source, ~2.9K pool.
3. Shared DEAD frame: −5 ids, ~0.6K.
4. AY reserve 7 → 6 KB.

### 11.3 Pool per level (KB; existing kinds E scaled from the measured 22,688; new **M**)

| Depth | Kind sets | Total |
|---|---|---|
| D1 | Rat 2.0 + Bat 2.0 + Slime 1.8 + Goblin 5.6 | 11.4 |
| D2 | Goblin 5.6 + Spider 2.75 + Bat 2.0 + Rat 2.0 | 12.4 |
| D3 | Skeleton 8.4 + Zombie 4.6 + Ghost 2.9 + Bat 2.0 | 17.9 |
| D4 | Orc 4.6 + Rat 2.0 + Spider 2.75 + Archer 4.4 + Skel HURT/DEAD 0.9 + **Ogre 6.5** | 21.2 |
| D5 | Mummy 4.6 + Skeleton 8.4 + Archer 4.4 + Spider 2.75 | 20.2 |
| D6 | Zombie 4.6 + Ghost 2.9 + Necro 4.48 + Orc 4.6 | 16.6 |
| D7 | Orc 4.6 + Archer 4.4 + Skel HURT/DEAD 0.9 + Ghost 2.9 + Necro 4.48 + **Death Knight 5.5** | **22.8** |
| D8 | Necro 4.48 + Skeleton 8.4 + Ghost 2.9 + Zombie 4.6 + Archmage 1.54 | 21.9 |

Level-start regeneration (≤ 23 KB) takes ≈ 1.8 s (E), behind a `DEPTH n` card.

---

## 12. Open questions for the user

1. **Mage bar:** adding Drain Life means the BAG icon leaves the Mage bar (inventory via
   FIRE+↓ / `I`). The Warrior keeps it. OK, or should Spark make room instead?
2. **AY reserve 8 → 7 KB** to fit 8 levels, unique bosses and sprite projectiles. OK?
3. **Unique bosses:** Ogre Warlord (D4) and Death Knight (D7). OK?
4. The **8 colour schemes** (§1.2): the 4 new ones are D4 cyan, D6 white, D7 bright blue
   and D8 magenta. Confirm on the canvas.
