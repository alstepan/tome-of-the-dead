# STATS2 - end card: BOOKS and ITEMS rows (user 2026-11-05)

Extends STATS1 / ENDCARD-L1F-G1 (`ec_tab` in `src/combat3.asm`). The engineer folds this into game.md.
No feature cut; two rows, 2 new strings, 3 new per-game bytes.

## 1. Layout (same font, colours, label x, value x as KILLS/TURNS)

Rows in `ec_tab` order, no extra gap rows inside the table:

| Row | Label | Value |
|---|---|---|
| 10 | `KILLS` | n (unchanged) |
| 11 | `TURNS` | n (unchanged) |
| 12 | `BOOKS` (new, `end_books`) | `r/f`, e.g. `3/5` |
| 13 | `ITEMS` (new, `end_items`) | n |
| 14 | `BEST KILL` | kind (unchanged text; moved from 12; still absent if no kill) |
| 16 | PRESS line | moved from 14; row 15 stays blank |

- Rows 12-13 are always drawn (a 0 run shows `BOOKS 0/0`, `ITEMS 0`). BEST KILL stays last because it is the
  only conditional row, so the table never has a hole. With no kill, rows 14-15 are blank and PRESS stays on 16 (fixed).
- Labels are 5 chars (<= 6). Numbers have no leading zeros (`es_num`); BOOKS prints read, `/`, found, each 0..255,
  max `255/255` = 7 chars, fits beside the label at the existing value x.

## 2. BOOKS r/f

- **found (f):** +1 on every successful pickup of a class book or a tome item (the one `BOOK` item kind, one icon),
  from the floor or a monster drop. The D1 start-room book counts when the hero picks it up (it is not pre-counted;
  a hero who never takes it has f = 0). There is no DROP (DISCARD destroys the item, game.md §8), so every book is counted once.
- **read (r):** +1 on every completed READ of a book, whatever the outcome: starter learn, pity learn, uniform
  learn, rank-up, or the Vigor/Power tome (the book is consumed, so every read succeeds). A READ that is refused
  (no turn spent, book kept) does not count.
- Same run only: both bytes zeroed at new game with the other ST1 counters. Both saturate at 255 (no wrap).
  r <= f always (a book must be picked up before it can be read; no DROP exists).
- Books are **not** counted in ITEMS.

## 3. ITEMS

- +1 per successful pickup action through `floor_pickup` (one hook, after the item is placed in the bag/slot), for
  every non-book kind (there is no gold in the game): food, potion, scroll, weapon/armour/gear,
  ammo bundle (a stack of arrows/daggers = 1 per pickup, not per piece), unique, charm. Monster drops and floor
  items count the same.
- No DROP exists (DISCARD destroys), so every item is counted at most once. Merging into an
  existing stack still counts 1. A failed pickup (bag full, `NO ROOM`) does not count.
- Saturates at 255, zeroed at new game. Not counted: items bought/granted at class start (the starting kit is not
  picked up), items generated but never picked up.

## 4. Win and death

Both end cards go through `ec_tab`, so both show the rows identically; the win card (D8 Sanctum) shows the totals up
to the win turn. No item generates in the Sanctum (game.md D8 rule), so the win card adds no pickup edge. The death
card must not read the counters after the lethal turn changes them: counters are only touched on the hero's own
pickup/read, so nothing runs after death. Card rows stay inside the existing end-card screen (<= row 16 + 1).

## 5. Memory

3 bytes (`ST1_BKR`, `ST1_BKF`, `ST1_ITM`), zeroed with the ST1 block. ST1_CNT has 5 B reserved: if STATS1 already uses
4-5 of them the engineer allocates elsewhere (memory-map update in the same change). Strings: `end_books "BOOKS"`,
`end_items "ITEMS"`; the `/` is drawn by the row printer (no string, or a 1-char literal).

## 6. Acceptance tests (tests/stats1.py style)

1. New game, die at once: card shows `BOOKS 0/0`, `ITEMS 0`; PRESS on row 16, KILLS/TURNS rows unchanged.
2. Pick up the D1 start-room book: found 1, read 0. READ it: `1/1`; ITEMS still 0.
3. Pick up a potion, a food item and an arrow stack: ITEMS = 3, BOOKS unchanged; DISCARD the potion: ITEMS stays 3.
4. Pick up 3 books, read 2 (one rank-up, one tome case via forced state): `2/3`.
5. Poke ST1_BKR/BKF/ITM = 254, trigger one more event each, then another: all stay 255 (saturate, no wrap).
6. Bag full: refused pickup leaves ITEMS and BOOKS found unchanged.
7. Win card (poke GS_WIN with known counters): both rows show the poked values; no row overlaps the PRESS line.
8. No-kill death: BEST KILL absent, rows 14-15 blank, BOOKS/ITEMS rows present; golden screen refreshed for the card.
9. Counters zero after menu -> new game (a second run does not inherit).
