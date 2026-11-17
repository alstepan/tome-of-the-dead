# TUT-GEAR: the bag-page and equip beat (room B) — designer proposal 2026-11-16

Status: **user-approved 2026-11-16, built (TUT-GEAR)**; merged into `tutorial_d0.md` §3 (beat table) / §8 (strings) and
`tut_strings.txt`; this file stays the beat's design record. As built: the beat is record 10 (`TUT_B9G`; B10..B15 are
records 11..16), the spot stays col 16 (no clash with TUT-KEY's key at cols 8–9 / B7's L77), memory-map "TUT-GEAR ledger".
Gear rules used: `game.md` §8 table, §8.11 "3E simplification" (no blessed/cursed, no curse warning),
`gear_rules.md` §1 (class gates), `item_info.md` §2–3 (page rows 18–19), `game.md` Q3 (page keys).

## 1. Item (one floor piece, class-picked at D0 build; plain, q = 0, m = 0)

| Class | Floor item | Row 18 / 19 on the page | Panel change on EQUIP | Gate |
|---|---|---|---|---|
| Warrior | `H_HELM` (type 34) | `HELM DEF+1` / `BLOCKS MAGE SPELLS` | DEF 1 -> 2 (Leather 1 + Helm 1) | METAL: harmless to a Warrior |
| Mage | `H_HOOD` (type 33) | `HOOD MP+1` / `BLOCKS POWER ATTACKS` | max MP 12 -> 13 (bar number row 21) | CLOTH: harmless to a Mage |

Both start kits wear **no helmet**, so the piece is a pure gain (no swap, nothing lost), not merely a
"better" item. **Never swap the pair**: a Mage in the Helm cannot cast Spark in B11 (GEAR1), a Warrior in the
Hood cannot Power Strike. Armour was rejected: Chain (D3+) would swap out the Mage's Robe (loses MP+2) and is
gated; uniques (King Helm) break the "found on D3+/boss" tier story and add a second item type.

## 2. Placement (room B)

Storey 0, **col 16** (footprint cols 16–17, rows 6–7; FLOOR1: c in 2..28, no other item in 15..17, trap col 13
is not 16/17, CURE col 19 footprint 19–20 and L1 {24..27} are clear, not under the B2 mentor spot x = 21).
The walk path (arrival -> KEY (TUT-KEY) -> trap col 13 -> gear 16 -> CURE 19 -> L1) crosses it; a leap over the
trap may overfly it (the beat's skip path covers that). Room B item types: key, gear, cure = 3 (cap 8).

## 3. Beat record `B9G` (new, inserted between B9 and B10)

| Field | Value |
|---|---|
| Room / spot / pose | B; stays at B2 (x = 21) from B9; POINT_DN, no blink |
| Becomes current | B9 advanced (poison cleared, or L32 skip path) |
| G0 (hold; fires the first turn end with the gear in the bag **and** the beat current) | **L80** `NEW GEAR! OPEN THE BAG` · L60 `ICONS: PRESS {D}+{F} AT ONCE` (existing); pointer BAG icon (retired by ICON MODE, §13.2 P1–P3) |
| Icon target BAG (`tut_tgt`, no hold; as built said on every rest, like B5 FOOD) | **L73** `THAT ONE. NOW PRESS {F}` (existing) |
| G1 (next turn, hold) | **L81** `CURSOR: {L} {R} {U} {D}` · **L82** `READ ITS STATS BELOW. EQUIP IT` |
| Goal line (row 20, from G1) | L82 (as built from G0, as every G2PRE beat: `tt_gvis` shows it at ST_G2P / ST_WAIT) |
| Trigger / goal check | **worn helmet slot is not empty**: `WORN + WS_HELM*IR_STRIDE` TYPE != `IT_NONE` (checked at turn end; EQUIP costs 1 turn and closes the page, so the poll sees it) |
| G2 on trigger (no hold; pointer rect HELM) | class pair **L83W** `WORN! DEF +1: BLOWS HURT LESS` / **L83M** `WORN! MAX MP +1: MORE SPELLS` |
| Pointer | G0 BAG icon; G2 new rect `TUT_PR_HELM` = panel cells rows 22–23, cols 28–29 (the helmet icon, FLASH for the turn) |

What the player does: pick up (walk), take the hold, open the bag (BAG icon FIRE, or key I), the page opens on the
new item (`LAST_PICK`, NEW `*`), reads name/stats on rows 18–19, FIRE -> verb strip -> choose EQUIP -> FIRE (page
verbs, Q3). Movement keys are taught as the page's cursor keys (`1`–`0` etc. are not used). The cursor already
sits on the new item; browsing (down to the WORN row, up to [CLOSE]) is invited, not gated (no-turn, unobservable).

Fail / skip paths (same style as the §3 table):
- **Item never picked up** (leapt over it, left B): beat skipped; entering C prints L76 (existing §13.5), no pointer.
- **Picked up, not equipped, hero leaves B**: skipped, L76 on entering C; he can still equip later (no penalty).
- **Gear DISCARDed before equip**: advance silently (`TUT_FH_GEAR_DISCARD`, no line; the bag no longer holds it).
- **Equipped before G0** (cleared a hold, opened the bag early): goal met, G0/G1 skipped, G2 only.
- **Poisoned when the gear is picked up**: G0 waits for B9 to clear (a group per turn; B8/B9 own the log).
- **Nudge** (§13.5) counts only after G0 was shown; reuses L82 as the goal line. Not shown with the Goblin awake.
- **Key beat (B7)**: the key is picked up before col 16 on the walk, so L24/L25 are long past; the one-group-
  per-turn rule defers G0 if the cure/key lines land the same turn. B10 (door, L33) fires after B9G; its
  trigger (room = C) is unchanged.

## 4. New strings (`tut_strings.txt`; L80–L83 chosen to avoid the proposed L77–L79 of §14.7; token = 5 width)

| id | text | chars | bytes (token = 1 B) |
|---|---|---|---|
| TL_L80 | `NEW GEAR! OPEN THE BAG` | 22 | 22 |
| TL_L81 | `CURSOR: {L} {R} {U} {D}` | 31 | 15 |
| TL_L82 | `READ ITS STATS BELOW. EQUIP IT` | 30 | 30 |
| TL_L83W | `WORN! DEF +1: BLOWS HURT LESS` | 29 | 29 |
| TL_L83M | `WORN! MAX MP +1: MORE SPELLS` | 28 | 28 |

All upper case, none begins with a token, no trailing full stop; L83W/M one class pair (`TUT_CP_L83`).

## 5. Byte estimate (all in the D0 pool overlay / blob, 0 B resident)

Strings 124 B + 5 terminators = 129 · beat record 16 · `tut_tgt` BAG row 6 · rect HELM ~4 · two trigger kinds
(gear in bag / helmet slot filled) ~25 · class pick + one floor entry (type, col, storey) ~9 · discard handler ~6.
**Total ~195 B.** The beat table grows 256 -> 272 B (17 records; B10–B15 renumber to B11–B16, or the engineer
keeps ids and adds a "sub-beat after B9" slot).

## 6. Open questions (defaults apply unless the user objects)

1. **No DEF number on the panel** (only worn-icon cells and, for the Mage, the MP bar number). The Warrior's
   "stat change" is the helm icon appearing and row 18 `DEF+1`; default: accept, L83W says it in words.
2. Page opens on the new item, so "move to the new item" is incidental; default: teach browsing, do not gate it.
   (As built: on the taught route the Cure is picked up after the helmet, so `LAST_PICK` is the Cure's slot; the page
   opens there and the cursor must move to the helmet: the L81 lesson is real.)
3. Sandbox reset (§5.2) must clear the worn helmet (start kit has none); engineer to confirm. **Confirmed:** the grate
   step runs `start_game` -> `new_game` (bank 0), which zeroes all of `ITEM_RAM` (BAG + WORN + ...) before `kit_add`;
   tests/tut0.py C5 compares the D1 after D0 with a plain START (ITEM_RAM incl.).
4. Rows 19 shows the gate phrase of the OTHER class (e.g. `BLOCKS MAGE SPELLS` to the Warrior): true and harmless;
   default: leave it (it previews the gear gate).
