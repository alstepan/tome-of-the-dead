# HOW TO PLAY page 3 — TREASURES (INSTR-P3)

Designer, 2026-11-01. User request 2026-11-01: a third HOW TO PLAY page that explains the boss
uniques and the charms. It extends `docs/design/instructions_screen.md` (Layout B) and its
render spec `instructions_screen.txt`. The grid, fonts, attribute rules and render model there
apply unchanged. BUILT (feat/instr-p3): the PAGE 3 block is in the `.txt`, the `.md` §1 flow line is updated.

## 1. Grid (unchanged from instructions_screen.md §2)

The real grid is FONT6: **42 chars × 24 rows**, char k at x = 6k. It is not 32 columns.
Paper and border are black, and there is no FLASH. Every row on this page is a full-row attr
fill (cells 0–31), so the 24-px colour boundary rule is met trivially. There are **no icons**
on page 3 (0 icon records), so `instr_ovl.asm` needs no new icon path. All characters are
ASCII 32..127, and FONT6 has all 96 of them.

Why no icons: 8 uniques with 16×16 icons would need the page-2 two-column grid. Its 18-char
columns cannot hold a name plus an effect (for example `DEF 1, DODGE +2, IMMUNE TO POISON`).
A table with an effect column 22 chars wide can, and its names match the bag page exactly.

## 2. Flow (3 pages; replaces the flow line of instructions_screen.md §1 / memory-map INSTR-BUILD)

- Page 1 → any key → page 2 → any key → page 3 → any key → menu, as today. A key counts only
  after all keys have been released once, on every page. There is no timeout.
- **BREAK on page 1 or page 2 skips all the remaining pages** and goes straight to the menu.
  BREAK on page 3 counts as any key.
- New state `GS_HELP3` (the engineer assigns the value; 11 is the next free one after
  `GS_HELP2 10`).
- Footers: page 1 `ANY KEY: NEXT PAGE   BREAK: SKIP` (unchanged). Page 2 now uses the same
  line, a byte-identical copy of page 1 row 23. Page 3 uses page 2's old footer row
  `              ANY KEY: START`, verbatim.
- Page counters change: page 1 row 00 `1/2` → `1/3`, page 2 row 00 `2/2` → `2/3`. Both stay
  at chars 39–41 and the rows stay the same length.

Edits to the existing `.txt` rows (exact):
```
P1 row 00:       TOME OF THE DEAD - HOW TO PLAY   1/3
P2 row 00:               ITEMS AND TIPS           2/3
P2 row 23:      ANY KEY: NEXT PAGE   BREAK: SKIP
```

## 3. Page 3 rows (render-spec format; attr = the fill for cells 0–31)

```
=== PAGE 3 ROWS ===
      TOME OF THE DEAD - TREASURES     3/3
                                                         (blank)
EACH LAIR BOSS DROPS ONE (D = DEPTH)
D1  KING HELM       DEF 1, DODGE +1
D2  SILK CLOAK      DEF 1, DODGE +2
                    IMMUNE TO POISON
D3  GRAVE CLOAK     DEF 2, HALF DAMAGE
                    FROM DARK AND DRAIN
D4  WARLORD CLEAVER WARRIOR 1D10+1, ATK +1
D4  BONE STAFF      MAGE 1D6, SPELL DMG +2
D5  SCARAB AMULET   MP REGEN TWICE AS FAST
                    HUNGER HALF AS FAST
D6  GRAVE RING      MP +2, IMMUNE TO DARK
D7  MIRROR HELM     DEF 2, REFLECTS DARK
                                                         (blank)
CHARMS: WEAR ONE RING OR AMULET
MIGHT RING  ATK +1      WARD RING   DEF +1
FIRE RING   HALF FIRE DAMAGE
MANA AMULET MP REGEN TWICE AS FAST
FOOD AMULET HUNGER HALF AS FAST
METAL ARMOUR OR HELM STOPS MAGE SPELLS
ROBE OR HOOD STOPS POWER ATTACKS
BOSS TREASURES AND CHARMS NEVER DO
              ANY KEY: START
```
(The `(blank)` annotations are not part of the `.txt`. Those rows are empty lines.)

| Row | Attr | Columns / notes | Len |
|---|---|---|---|
| 00 | `$46` | 6 sp, title chars 6–33, 5 sp, `3/3` chars 39–41 (as P1/P2) | 42 |
| 01 | `$00` | blank | 0 |
| 02 | `$06` | group header (as P2 row 02) | 36 |
| 03 | `$47` | table: D chars 0–1, name from char 4, effect from char 20 | 35 |
| 04, 05 | `$45` | Silk Cloak (row 05: effect column only) | 35 / 36 |
| 06, 07 | `$47` | Grave Cloak | 38 / 39 |
| 08 | `$45` | Cleaver: name chars 4–18, 1 sp, effect 20–41 (**full 42**) | 42 |
| 09 | `$47` | Bone Staff (**full 42**) | 42 |
| 10, 11 | `$45` | Scarab (row 10 **full 42**) | 42 / 39 |
| 12 | `$47` | Grave Ring | 41 |
| 13 | `$45` | Mirror Helm | 40 |
| 14 | `$00` | blank | 0 |
| 15 | `$06` | group header | 31 |
| 16 | `$47` | 2 cols: names at 0 and 24, effects at 12 and 36 (**full 42**) | 42 |
| 17 | `$45` | name 0, effect 12 | 28 |
| 18 | `$47` | name 0, effect 12 | 34 |
| 19 | `$45` | name 0, effect 12 | 31 |
| 20, 21, 22 | `$05` | class-gate note (as P1 rows 21–22: dim cyan notes) | 38 / 32 / 34 |
| 23 | `$46` | footer = P2's old row 23, byte-identical | 28 |

Attribute scheme: the `$47` / `$45` alternation is per entry, so a 2-row entry keeps one ink
(the P2 tip alternation). Group headers use `$06` (P2 row 02). Notes use `$05` (P1 rows 21–22).
Title and footer use `$46`. The page adds no new attr values.

`instr_pack.py` `PAGES[3]`:
```
"fills": _rows_fill([0, 23], 0, 31, 0x46) + _rows_fill([2, 15], 0, 31, 0x06)
       + _rows_fill([3, 6, 7, 9, 12, 16, 18], 0, 31, 0x47)
       + _rows_fill([4, 5, 8, 10, 11, 13, 17, 19], 0, 31, 0x45)
       + _rows_fill([20, 21, 22], 0, 31, 0x05),
"icons": [],
```

## 4. Number check (every figure against the build)

| Entry | Text | Source |
|---|---|---|
| KING HELM | DEF 1, eva +1 | `src/items.txt` IT_H_KING `0 0 1 0 0`; `src/gear6.asm` gx_tab eva 1 |
| SILK CLOAK | DEF 1, eva +2, poison-immune | items.txt DEF 1; gx_tab eva 2, `IMMF_POISON` |
| GRAVE CLOAK | DEF 2, DRAIN R + DARK R (R = ×½, game.md §6.0) | items.txt DEF 2; gx_tab `RSP_R \| RSP_R<<2` |
| WARLORD CLEAVER | 1d10, +1 dmg, atk +1; Warrior | items.txt `10 1`; gear6 `gear_dec` Cleaver +1; uniq_tab D4 W |
| BONE STAFF | 1d6, spells +2 dmg; Mage | items.txt `6 0`; `src/proj3.asm` STAFF-BONUS (Rune +1, Bone +2) |
| SCARAB AMULET | MP regen ×2, food burn ×½ | gear6 MP_PER `IT_C_SCARAB` srl; `src/hunger7.asm` PLENTY..SCARAB |
| GRAVE RING | MP +2, DARK I | items.txt MP 2; gx_tab `RSP_I<<2` |
| MIRROR HELM | DEF 2, DARK X | items.txt DEF 2; gx_tab `RSP_X<<2`. In the build, Necromancers and Bone Callers never fire at an X hero (`ranged6.asm` .refl), and the Archmage's Death Bolt bounces back at him (`arch6.asm` am_cast). Both are DARK (§6.0), so `REFLECTS DARK` is true |
| MIGHT / WARD RING | atk +1 / DEF +1 | items.txt `0 1 0` / `0 0 1` |
| FIRE RING | FIRE R | gx_tab `RSP_R<<2` on B0 |
| MANA / FOOD AMULET | MP regen ×2 / FOOD burn ×½ | gear6 `IT_C_MANA`; hunger7 `IT_C_PLENTY` |
| Class gate | Chain/Plate/Helm ban Mage spells; Robe/Hood ban power attacks; uniques and charms exempt | `docs/design/gear_rules.md` §1.1–1.2 |

Names are the in-game spellings (`src/items.txt`), not the design names (Goblin King's Helm →
`KING HELM`, Gravecloak → `GRAVE CLOAK`, Ring of the Grave → `GRAVE RING`, Ring of Might →
`MIGHT RING`, Amulet of Plenty → `FOOD AMULET`, and so on). The bag page shows the same words.
The figures are the base values: Enchant can still raise a unique's m (GEAR3 G3-7), and q = 0
for uniques (GEAR2). The page does not mention either.

Wording choices: `DODGE` is used for eva (no string uses EVA). `HALF DAMAGE` is used instead
of "resists", so the player sees the number. `SPELL DMG` is the only abbreviation (the row is
42 chars).

## 5. Budget

| Item | Bytes |
|---|---|
| Page 3 text (`enc_row`: chars, runs of ≥ 2 spaces = 1 B, 0 per row) | **701** |
| Attr RLE (19 runs × 2 + 0) | **39** |
| Icon list (terminator only) | 1 |
| **Page 3 raw** | **741** (window after the 359 B code: 1,177; page 1 is 772, so the biggest page still fits) |
| P2 footer change (16 → 31 B row) / P1, P2 counters | +15 / 0 |
| Code (page loop 2 → 3, `GS_HELP3`, BREAK on page 2) | ~+15 B estimate (engineer measures) |
| **Packed (ZX0)** | ≈ **540 B** for page 3 (today 1,813 raw → 1,368 = 0.75; plain text with repeated words, 0.70–0.75) + ~15 B for the edits |
| **Expected tape delta** | ≈ **+560 B** (bank 0 text block only; boot-only and dead after the help, 0 pool bytes) |

If the ~700 B raw target is binding, cut in this order: row 02 → `LAIR BOSS DROPS (D = DEPTH)`
(−9), row 22 → `TREASURES AND CHARMS NEVER DO` (−5), and drop row 05/11 continuation text
(−34 at most; this loses information, so avoid it). The hard limit is the window, and it fits.
Engineer: check that `instr_zx0_end` (+~560, M0 `$CEB8` → ≈ `$D0E8`) still sits below the next
bank-0 occupant at load time.

## 6. Test vectors (tests/instr.py, model = `gen_instr_mock.page(3)` from `PAGES[3]`)

- **I3** (update): page 2 == page(2). This covers row 00 `2/3` and row 23 (new footer).
- **I1** (update): page 1 == page(1) (row 00 `1/3`).
- **I9** page 3 (`GS_HELP3`) == page(3), all 6,912 bytes. On failure, report the rows with
  differences. Rows that need a byte-for-byte check by name: **00** (title + `3/3` at
  x 234–251), **08, 09, 10, 16** (full 42 chars: the last glyph at x 246–251, cell 31),
  **05/07/11** (text starting at char 20 = x 120, cell 15), **17** (effect at char 12),
  **20–22** attr `$05`, **01/14** all zero (bitmap and attr `$00`), **23** == page 2's old
  row 23 bitmap.
- **I10** the page-2 key held: still page 2 until it is released (as I2), then `GS_HELP3`.
- **I4** (update): page 2's key → page 3 (not the menu). Page 3's key → menu, swallowed
  (no START).
- **I5** (update): BREAK on page 1 → menu, never `GS_HELP2` or `GS_HELP3` in the states seen.
- **I11** BREAK on page 2 → menu, never `GS_HELP3`.
- **Static** (`instr_pack.py` asserts + `gen_instr_mock.py --check`): 24 rows, each ≤ 42
  chars, chars 32..127; the attr RLE covers 768 cells; ≤ 2 colours per cell; page 3 raw
  ≤ `GEN_SCRATCH_LEN − code`.

Tool changes: `instr_pack.py` `main` and `gen_instr_mock.py` loop over pages 1..3 (emits
`instr_p3.inc` / `instr_p3.png`). The stream order becomes page 1, page 2, page 3, code
(code last, as today).
