# UX polish: panel flashes, bag cursors, NEW marks, book hint (UX1)

**Status: APPROVED** (user decision 2026-11-12; designer spec 2026-11-12). Lands with ITEM-INFO
(item_info.md). Auto-reading books on pickup was **REJECTED**: what a book teaches depends on the
depth at read time (game.md §5), so holding a book is a real choice. The bag-page coordinates
here are the **as-built** `page_ovl.asm` ones; game.md Q3's table is stale.

## 1. Rule: rebuild attrs from game state
- Every flash is computed from state each time its cells are drawn: hunger stage, HP, MAXHP, `MPF_T`.
- A FLASH bit is never set once and left to be remembered.
- Whoever overwrites these cells calls the same rebuild: the panel queue, the panel redraw after
  the bag page or level card, and a tutorial pointer clearing. A pointer puts back the
  *computed* attr, not "bit 7 cleared".
- All flashes use hardware FLASH (bit 7) on **text cells only** (tutorial_d0.md R4). No clash,
  0 T while flashing, no turn cost.

## 2. Panel row 21 (artist-confirmed)
- Cells: HP label col 0, bar 1–4, num **5–6**. MP label 7, bar 8–11, num **12–13**. FOOD label
  14, bar 15–18, word **19–23**.
- **Split `hg_attr`**, which stamps 15–23 with one attr today. The bar (15–18) gets the stage
  attr and never flashes; the word (19–23) gets the stage attr, plus FLASH at WEAK.

| # | Cells | Starts | Stops | Attr | Sound |
|---|---|---|---|---|---|
| F1 FOOD | word 19–23 | stage WEAK (FOOD ≤ 9) | FOOD ≥ 10 | `$42` → `$C2` | none |
| F2 HP | num 5–6 | HP ≤ max(MAXHP>>2, `HPLOW_MIN` 5), 8-bit | next HP redraw above | num attr \| `$80` | none |
| F3 MP | num 12–13 | a `NO MANA` refusal (cast or Warrior special) | 32 frames, or the next input while ICON MODE is open | num attr \| `$80` | existing UI "denied" SFX, reused |

- **F1** keeps flashing through a faint. The Mummy WEAK *status* icon (cols 30–31) never flashes:
  it is a timed curse.
- **F2** is checked on every HP draw: damage, regen, Heal, level-up, MAXHP change.
- **F3 timer:** `MPF_T` is a deadline that the main-loop tick checks against the existing frame
  counter. **The ISR does not grow** (the SFX10c/SND6 gates have 0 T margin).
- **F3 behaviour:** a repeat refusal restarts the countdown and replays the SFX. The refusal
  itself is unchanged: no turn, no MP, `NO MANA` in the log, ICON MODE stays open.

## 3. Bag grid
**C1 Cursor = the icon's 2×2 cells.**
- Bag slot: cols `9+3c`, `10+3c`, rows `4+3r`, `5+3r`.
- Worn slot: cols `11+3k`, `12+3k`, rows 16–17.
- `pg_rect` returns `DE` = 2 × 2 (was 3 × 2), and `pg_tog` xors `PG_HI` `$08` over those cells.
- The count column `11+3c` keeps black paper. `[CLOSE]` (row 0, cols 26–31) is unchanged.
- No new art: the icons already have a 1-px margin and read on blue (game.md Q5).

**C2 Open on the last pickup.**
- `LAST_PICK` (`$FF` = none) is the slot of the last successful bag pickup; a stack top-up counts.
- The page opens there if it is below the bag count, else on slot 0.
- It persists until the next pickup or compaction.
- EQUIP swapping a worn item into the bag is not a pickup.

**C3 NEW mark.**
- `NEW_MASK` has one bit per bag slot (0–19). Every successful bag pickup sets its slot's bit:
  floor, drop, unique, top-up. Ammo counters are not slots.
- Draw: FONT6 `*` via `print6` in the slot's **top-right cell** (col `11+3c`, row `4+3r`,
  x = col·8), attr `PG_A_BOX` `$47`. The QTY digit stays at row `5+3r`.
- The artist adds an 8×8 glyph only if FONT6 has no `*`.
- The bit clears when the cursor **arrives** on the slot (redraw that cell, ~60 T). Opening on
  `LAST_PICK` counts as an arrival.
- NEW is independent of identification: an unknown potion stays `UNKNOWN` on rows 18–19.

**Rows 18–19 (item_info.md):** unchanged. C1–C3 and §5 never touch cols 0–1 or rows 18–19. The
description follows the cursor, including C2's opening slot.

## 4. Compaction (bag order = pickup order, game.md §8.11)
When slot k empties and slots k+1..19 shift down:
- `NEW_MASK`: the bits above k shift down one and bit 19 becomes 0. A 3-byte shift masked at k.
- `LAST_PICK`: if it was k it becomes `$FF`; if it was greater than k it decreases by 1.

Both run inside the existing compaction routine, so there is no second path.

## 5. Item menu (verb strip, row 20) cursor
**As built:**
- `print6` (6 px/char, x must be cell-aligned) prints each label at a fixed col.
- The highlight xors `$08` over `pg_vtab`'s width (enabled `$45` → `$4D`).
- The USE slot is a **fixed 4 cells**, sized for DRINK (30 px):
  - `USE` / `EAT` (18 px) leave 14 px of blue past the text;
  - `READ` (24 px) leaves a whole empty blue cell.
- EQUIP, REMOVE, DISCARD and CLOSE are already ceil(6n/8) wide.

**Fix:** every highlight is exactly **ceil(6n/8) cells** from the label's col.

| Label | Col | px | Cells (highlighted) | Right slack |
|---|---|---|---|---|
| USE / EAT | 2 | 18 | **3 (2–4)** | 6 px |
| READ | 2 | 24 | **3 (2–4)** | 0 |
| DRINK | 2 | 30 | 4 (2–5) | 2 px |
| EQUIP | 7 | 30 | 4 (7–10) | 2 px |
| REMOVE | 12 | 36 | 5 (12–16) | 4 px |
| DISCARD | 18 | 42 | 6 (18–23) | 6 px |
| CLOSE | 25 | 30 | 4 (25–28) | 2 px |
| `[CLOSE]` row 0 | 26 | 42 | 6 (26–31), unchanged | 6 px |

**Code:**
- In `.set`, write the USE width (3, or 4 for DRINK) into `pg_vtab+1` before stamping.
- The xor toggles stay balanced: the strip is entered only after `.set`, and the slot cannot
  change while the strip is open.
- After a 3-wide word, cell 5 keeps its VON/VOFF attr over blank pixels, so it is invisible.

**Limits and scope:**
- The ≤ 6 px right slack is the limit of a cell-aligned printer. Centring would need a shifting
  `print6`, which is rejected.
- The page has **no sub-menu or confirm**: REMOVE with a full bag → row-22 message; DISCARD has
  no confirm. Pause's `QUIT? Y/N` has no cursor and is out of scope.

## 6. First-book hint
- On the **first successful `IT_BOOK` pickup of a game**, the log queues `READ IT IN THE BAG`
  (18 chars + terminator, FONT6 log table) as the group after the pickup line.
- Flag: `HINT_BOOK`, 1 bit in an existing game-flags byte.
- **D0:** a book pickup sets the flag silently (Morrow teaches READ).

## 7. Interactions
| With | Rule |
|---|---|
| ICON MODE | Its highlight is on the icon bar (rows 18–19), so F1–F3 on row 21 never overlap it. F3 ends on the next input in the mode |
| Tutorial pointers / R4 | Same bit 7 on text cells, so a shared cell looks identical. A pointer clear calls the §1 rebuild for its rect. HP cells 5–6 are never a pointer target |
| Bag page / level card | Full screen. On return the panel redraw runs §1: F1/F2 come back, and F3 is dropped if it has run out. `MPF_T` only counts down in play |
| Pause | Overlay on the playfield; panel flashes continue (harmless) |
| Death / win / quit screens | They write full attrs without bit 7. `new_game` clears `NEW_MASK`, sets `LAST_PICK` to `$FF`, zeroes `MPF_T` and clears `HINT_BOOK` |
| Mage vs Warrior | F2's floor of 5 protects the Mage's low MAXHP. F3 covers Mage casts and Power Strike/Whirlwind at the rank-1 threshold (§5 auto-downcast) |

## 8. Data, placement, estimates (E)
- **Data:** `NEW_MASK` 3 B, `LAST_PICK` 1 B, `MPF_T` 1 B, `HINT_BOOK` 1 bit, `HPLOW_MIN` equ 5.
- **Data must live outside the page overlay**, which is re-unpacked on every open. The engineer
  assigns addresses in memory-map.md.
- **Code:** the panel flashes, F3, the pickup and compaction hooks, and the hint go in
  **B0_FREE** via the B0CODE block. C1, C3's draw/clear, C2's open and §5 go in `page_ovl.asm`
  (ZX0-repacked in R6; check its packed size).

| Part | Bytes | T |
|---|---|---|
| C1 cursor 3→2 | ~0 | −2 attr writes per move |
| F1 split + WEAK bit | ~10 | ~+40 per food redraw |
| F2 threshold | ~18 | ~+80 per HP redraw |
| F3 countdown, restore, SFX, ICON MODE clear | ~30 | ~+30 per loop while running |
| C2 set + open + compaction | ~15 | — |
| C3 set / draw / clear / shift | ~55 | page draw +20 × ~60 ≈ 1.2k |
| §5 USE width | ~8 | — |
| Hint flag + string | ~12 + 19 | — |
| Data | 5 | — |
| **Total** | **≈ 175 B** | negligible |

## 9. Tests
**Rebaseline:**
- every bag-page golden (grid cursor 2×2; verb strip with USE/EAT/READ selected);
- panel goldens at WEAK or at low HP;
- `tests/page.py`, `tests/gear1..3.py` and the tutorial B3 checks that assume the page opens on
  slot 0 (set `LAST_PICK` to `$FF`, or pick up first).

**New:**
1. FOOD 9 → word `$C2`, bar `$42`; eat to 10 → no bit 7.
2. MAXHP 40: HP 10 flashes, 11 does not. MAXHP 12: HP 5 flashes, 6 does not.
3. MP 0 + cast → cols 12–13 have bit 7 and `SFX_REQ` is set; turn and MP unchanged. Bit 7 clears
   after 32 frames, or earlier on a key in ICON MODE.
4. Pick up A, then B → page opens on B (mark cleared); A shows `*` until visited.
5. Discard below a NEW slot → the mark moves down and `LAST_PICK` decreases by 1. Discarding
   `LAST_PICK` → the page opens on slot 0.
6. Verb strip: EAT/READ highlight cols 2–4, DRINK 2–5, DISCARD 18–23; row-20 attrs are back to
   the original after leaving the strip.
7. First book → hint once; second book → none. A D0 book → no hint on D1.
8. Bag open/close at WEAK → F1 is back. A pointer clearing cols 19–23 at WEAK → still flashing.
