# Tome of the Dead — Item guide (player manual)

Player-facing summary of every item, trap and status. Source of truth: `docs/design/game.md`
§1.5, §5, §6.0–6.4, §7, §8 (incl. §8.6, §8.10, §8.11 "3E simplification"), `src/items.txt`.
Names are exactly as the game prints them. If this page and game.md disagree, game.md wins.

**Terms.** `atk` = to-hit bonus (a hit lands on `d20 + atk >= 10 + target eva`). `eva` =
evasion. `DEF` = subtracted from every physical hit taken (min 1 damage). `dmg` = damage
bonus. Resistances: **R** = half damage, **I** = immune, **X** = reflect (projectiles bounce
back). `Dn+` = first found on depth n. Every item is always identified: no curses, no
unknown potions, stats are fixed by type.

## Weapons (worn: WEAPON) — class-locked; the floor only ever has your class's weapons

| Name | Class | Stats | Found |
|---|---|---|---|
| SHORT SWORD | Warrior | 1d6 | start |
| LONG SWORD | Warrior | 1d8, atk +1 | D2+ |
| WAR AXE | Warrior | 1d10, atk −1 | D4+ |
| WARLORD CLEAVER | Warrior | 1d10+1, atk +1 (unique) | D4 boss (Ogre Warlord) |
| OAK STAFF | Mage | 1d4 | start |
| IRON STAFF | Mage | 1d6 | D2+ |
| RUNE STAFF | Mage | 1d4, spells +1 dmg  | D4+ |
| BONE STAFF | Mage | 1d6, spells +2 dmg (unique) | D4 boss (Ogre Warlord) |

No weapon worn = fists, 1d2.

## Armour (worn: ARMOUR) — any class

| Name | Stats | Found |
|---|---|---|
| ROBE | max MP +2 | Mage start |
| LEATHER | DEF 1 | Warrior start |
| CHAIN MAIL | DEF 2 | D3+ |
| PLATE MAIL | DEF 3, MP regenerates half as fast | D6+ |
| SILK CLOAK | DEF 1, eva +2, immune to POISON (unique) | D2 boss (Golden Spider Queen) |
| GRAVE CLOAK | DEF 2, DRAIN R, DARK R (unique) | D3 boss (Golden Vampire Lord) |

## Helmets (worn: HELM) — any class

| Name | Stats | Found |
|---|---|---|
| HOOD | max MP +1 | D1+ |
| HELM | DEF +1 | D1+ |
| KING HELM | DEF 1, eva +1 (unique) | D1 boss (Golden Goblin King) |
| MIRROR HELM | DEF 2, DARK X: reflects Dark Bolts and Death Bolts (unique) | D7 boss (Death Knight) |

## Charms (worn: CHARM, one ring *or* amulet) — any class

| Name | Effect | Found |
|---|---|---|
| MIGHT RING | atk +1 (to-hit only, not damage) | D2+ |
| WARD RING | DEF +1 | D2+ |
| FIRE RING | FIRE R: fire damage to you is halved (*see note 1*) | D2+ |
| MANA AMULET | MP regenerates twice as fast | D3+ |
| FOOD AMULET | hunger burns half as fast | D3+ |
| SCARAB AMULET | MANA AMULET + FOOD AMULET in one (unique) | D5 boss (Golden Pharaoh) |
| GRAVE RING | max MP +2, DARK I: immune to Dark/Death Bolts and their FEAR (unique) | D6 boss (Golden High Necromancer) |

Uniques shimmer gold on the floor; the boss always drops one (`BOSS DROPS …`). D8's Archmage
drops nothing (his death opens the Sanctum).

> **How gear wear works**
> Wear is **not** random destruction and ordinary hits never wear gear. Only two special
> attacks do, and the only random part is *whether* a wear event happens:
> - **NOTCH** (weapon): Skeleton Guard, Skeleton Knight and the Death Knight can parry your
>   melee hit (incl. Power Strike, Whirlwind). Each parry notches your weapon **1 in 2**.
>   Thrown/shot ammo and fists are never notched.
> - **ACID** (armour, or the helmet if you wear no armour): each Black Widow bite that hurts
>   you corrodes **1 in 4**.
>
> Each event lowers the item's modifier by 1, shown on the page (e.g. `CHAIN MAIL -1`):
> weapon damage −1, armour/helm DEF −1 (ROBE/HOOD: max MP −1). An item **already at −3** is
> destroyed by the next event (`YOUR WEAPON BREAKS!` / `YOUR ARMOUR FALLS APART!`); the slot
> empties. Repair: the ENCHANT SCROLL raises the **weapon** modifier +1 (max +3). Armour and
> helmets cannot be repaired. Charms never wear.

## Potions (bag, stack 9) — DRINK, 1 turn

| Name (ink) | Effect |
|---|---|
| HEAL POTION (red) | +12 HP. Refused at full HP (`NO NEED`, no turn) |
| MANA POTION (cyan) | +8 MP. Refused at full MP. Necromancers drop it 1 in 3 |
| CURE POTION (green) | clears POISON, WEAK, CONFUSED, FEAR; +4 HP |

Every level has 2–3 potions, at least one HEAL.

## Scrolls (bag, stack 9) — READ, 1 turn

| Name (ink) | Effect |
|---|---|
| TELEPORT SCROLL (cyan) | to a random safe spot in another room (never the boss lair while the boss lives, never the Sanctum). Nothing follows you |
| FEAR SCROLL (yellow) | every monster in the room flees for 6 turns (bosses immune) |
| SLEEP SCROLL (green) | every monster in the room falls ASLEEP for 8 turns (bosses immune; damage wakes) |
| ENCHANT SCROLL (white) | worn weapon +1 damage, max +3. Fists or already +3: `NOTHING HAPPENS` (scroll used) |

## Food (bag, stack 9) — EAT, 1 turn. FOOD is 0–100, start 80, cap 100

| Name | FOOD | Also dropped by |
|---|---|---|
| CARROT | +10 | — |
| APPLE | +15 | Goblins 1 in 4 |
| PEAR | +20 | — |
| CHEESE | +30 | Rats 1 in 4 |
| MEAT | +40 | Orcs 1 in 3 |

Eating at FOOD 100 is refused (`NO NEED`); while poisoned you cannot eat (`TOO SICK TO EAT`).

## Other

| Name | What it is |
|---|---|
| WAR TOME / SPELL TOME | your class book (READ, 1 turn, consumed). The first one (D1 start room) teaches Power Strike / Spark; later ones teach a new ability or raise one to rank 2–3; with nothing left, Warrior gains Vigor / Mage gains Power. One per level D1–D7, sometimes two on D4–D7 |
| BOW | Warrior only. Bag item, never worn; needed to shoot arrows. Exactly one, on D2, with 6 arrows. Discarded = gone for the run |
| DAGGERS | Warrior counter (max 9, start 3). Throw: range 6, atk +1, 1d4+2 |
| ARROWS | Warrior counter (max 24). Shoot (needs the BOW): range 14, 1d6+1. Skeleton Archers drop 3, 1 in 2 |
| Lair key | counter, found automatically on entering the key room; opens the lair door |

The Mage gets no ammo; his limit is MP.

> **Bag and quick slots**
> Bag: 20 slots; potions, scrolls and food stack to 9; gear, books and the bow take one slot
> each. Pickup is automatic (end of turn, no extra turn); a full bag leaves the item on the
> floor (`BAG FULL`). Worn: weapon, armour, helm, charm. EQUIP swaps with the worn item (1
> turn), REMOVE needs a free bag slot (1 turn), DISCARD destroys the whole stack (0 turns;
> worn items cannot be discarded).
> The icon bar's three quick slots fill themselves, 1 turn per use:
> - **FOOD**: the smallest food first (Carrot → Apple → Pear → Cheese → Meat).
> - **POTION**: Heal → Mana → Cure, skipping any that would be refused (full HP, full MP,
>   nothing to cure). All refused: `NO NEED`, no turn.
> - **SCROLL**: the largest stack; ties Teleport → Fear → Sleep → Enchant.
> - Empty: `NO FOOD` / `NO POTION` / `NO SCROLL`, no turn.

## Effects and statuses (panel icons, row 21)

| Status | What it does | Ends |
|---|---|---|
| FROZEN | cannot act; easy to hit | timer; any fire damage thaws |
| ASLEEP | cannot act; easy to hit | timer or any HP loss |
| STUNNED | cannot act; easy to hit; cannot parry | timer only (damage does not wake) |
| CONFUSED | 1 in 3 moves/attacks go the wrong way (`YOU STUMBLE`) | timer; CURE |
| FEAR | no melee (spells, ranged and items still work) | timer; CURE |
| POISON | −1 HP every 4th turn (never below 1 HP); cannot eat; stacks up to 30 turns | timer; CURE |
| WEAK (curse) | atk −2, eva −1, physical dmg −1, no MP regen, no jump | timer (12); CURE |

Sources: Frost Shard rebound → FROZEN 1; GAS trap ASLEEP 4, hunger faint ASLEEP 5; STUN trap
2–3, Ogre/Bouncer/Knight slams 1; Ghost touch CONFUSED 4; Necromancer Dark Bolt FEAR 3 (1 in 3);
Spider/Giant Rat/DART 12, Spider Queen 18, Black Widow 24 POISON; Mummy curse WEAK 12 (1 in 3).

**Hunger stages** (panel word; −1 FOOD every 6 turns, a jump −2 more; never fatal):
FED 50–100: +1 HP per 12 turns · OK 25–49: no HP regen · HUNGRY 10–24: atk −1, MP regen
halved · WEAK 0–9: as the WEAK curse (not cumulative), and you **faint** (ASLEEP 5) after 50
WEAK turns, then every 30, until you eat.

## Traps (pressure plates, hidden until found)

Search = Wait (finds traps within 6 cols, 1 in 2 each). The Mage senses traps within 2 cols
automatically. A jump clears a trap. Only the hero triggers traps. Per level: D1 1, D2–D3 2,
D4–D6 3, D7–D8 4.

| Trap | From | Effect | After |
|---|---|---|---|
| DART (red) | D1 | 1d4+1 damage (DEF applies) + POISON 12 | stays, re-fires each time you step on |
| GAS (green) | D2 | ASLEEP 4 | gone |
| TELEPORT (magenta) | D3 | as the TELEPORT SCROLL | gone |
| STUN (grey) | D4 | falling stone 1d3 (DEF applies) + STUNNED 2–3 | gone |
| ALARM (yellow) | D5 | while the level boss lives, a wave of 1–2 monsters arrives; boss dead: nothing | gone |

Pending (TRAP2, after 3F): every trap stays and re-arms after triggering, as DART does now.

## Open points (designer notes, not player text)

1. **FIRE RING** has almost nothing to resist: no monster deals FIRE damage. It only halves
   the Mage's own Firebolt burst at point-blank range and a Firebolt reflected by the Death
   Knight (FIRE X). For a Warrior it does nothing. Needs a decision (BAL1).
2. **RUNE STAFF / BONE STAFF spell bonus** (+1 / +2) is built: it adds to the direct hit of
   Spark, Firebolt, Frost, Lightning and Drain (all ranks), after the dice and before resistance
   (min 1). It does not apply to the Firebolt burst, melee, thrown daggers or arrows.
3. **WEAK** names both the hunger stage and the Mummy curse status (same penalties, different
   cure: food vs CURE/timer).
4. Dagger/arrow recovery after a throw (§6.3) is designed; game.md §8.11 FLOOR1 says it is
   not built yet. Confirm before publishing the recovery rule.
5. Parry chances per monster are not stated in this guide (game.md §9.6).
