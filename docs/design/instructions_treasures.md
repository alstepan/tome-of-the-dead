# HOW TO PLAY page 3 — TREASURES (INSTR-P3, INSTR-P3-ICONS)

Designer, 2026-11-01. User request 2026-11-01: a third HOW TO PLAY page that explains the boss
uniques and the charms. It extends `docs/design/instructions_screen.md` (Layout B) and its
render spec `instructions_screen.txt`. The grid, fonts, attribute rules and render model there
apply unchanged. INSTR-P3 (text-only page with names) is BUILT (feat/instr-p3).

**INSTR-P3-ICONS (user request + decision 2026-11-01, this revision): the page shows each
item's 16×16 ICON instead of its NAME, in the page-2 two-column grid (layout B, user-chosen).**
Rejected: layout A (one column, icon + 2 lines of up to 38 chars, charms as a row of 5 icons
with 8-char captions); its charm captions were too cramped. This document now specifies B only.
The flow (§2) is unchanged from INSTR-P3.

## 1. Grid (unchanged from instructions_screen.md §2)

- FONT6: **42 chars × 24 rows**, char k at x = 6k. It is not 32 columns. Paper and border are
  black, and there is no FLASH. All characters are ASCII 32..127.
- 16×16 item icons as on page 2: icon cells 0–1 (left) and 16–17 (right), 2 char rows tall.
  Text is in chars **3–20** (left, x 18–125 = cells 2–15) and **24–41** (right, x 144–251 =
  cells 18–31). Chars 0–2 and 21–23 of an icon row are always spaces, so no text pixel shares
  a cell with an icon (no clash).
- Every text row has one text attr in all its non-icon cells. The icon's 4 cells carry the
  icon's own attr = its item ink on black (`src/items.txt` INK, the bag page's `item_ink`).
  The colour changes at cells 2 and 18 sit in the space chars 3 / 21–23 (page 2 does the same).

## 2. Flow (3 pages; unchanged from INSTR-P3)

- Page 1 → any key → page 2 → any key → page 3 → any key → menu. A key counts only after all
  keys have been released once, on every page. There is no timeout.
- **BREAK on page 1 or page 2 skips all the remaining pages**. BREAK on page 3 counts as any key.
- `GS_HELP3` as built. Page counters `1/3`, `2/3`, `3/3` and the footers as built.

## 3. Page 3 rows (render-spec format)

Replace the `=== PAGE 3 ROWS ===` block of `instructions_screen.txt` with these 24 rows
verbatim (the engineer owns that file edit; `(blank)` = an empty line, not part of the `.txt`).
Every row is measured below; trailing spaces are not part of the row.

```
=== PAGE 3 ROWS ===
      TOME OF THE DEAD - TREASURES     3/3
                                                         (blank)
EACH LAIR BOSS DROPS ONE (D = DEPTH)
   D1 DEF 1             D2 DEF 1, DODGE +2
   DODGE +1             IMMUNE TO POISON
   D3 DEF 2, HALF DMG   D4 WARRIOR: 1D10+1
   FROM DARK + DRAIN    ATK +1
   D4 MAGE: 1D6         D5 2X MP REGEN
   SPELL DMG +2         HALF HUNGER
   D6 MP +2             D7 DEF 2
   IMMUNE TO DARK       REFLECTS DARK
                                                         (blank)
CHARMS: WEAR ONE RING OR AMULET
   ATK +1               DEF +1
                                                         (blank: icons only)
   HALF DMG             2X MP REGEN
   FROM FIRE
   HALF HUNGER
                                                         (blank: icon only)
                                                         (blank)
METAL ARMOUR OR HELM STOPS MAGE SPELLS
ROBE OR HOOD STOPS POWER ATTACKS
BOSS TREASURES AND CHARMS NEVER DO
              ANY KEY: START
```

Sketch (`[xx]` = a 2×2-cell icon; left icon cells 0–1, right icon cells 16–17):

```
    0         1         2         3         4      chars
    012345678901234567890123456789012345678901
00        TOME OF THE DEAD - TREASURES     3/3     $46
01                                                 $00
02  EACH LAIR BOSS DROPS ONE (D = DEPTH)           $06
03  [KH]D1 DEF 1          [SC]D2 DEF 1, DODGE +2   $47  King Helm | Silk Cloak
04  [  ]DODGE +1          [  ]IMMUNE TO POISON     $47
05  [GC]D3 DEF 2, HALF DMG[WC]D4 WARRIOR: 1D10+1   $45  Grave Cloak | Warlord Cleaver
06  [  ]FROM DARK + DRAIN [  ]ATK +1               $45
07  [BS]D4 MAGE: 1D6      [SA]D5 2X MP REGEN       $47  Bone Staff | Scarab Amulet
08  [  ]SPELL DMG +2      [  ]HALF HUNGER          $47
09  [GR]D6 MP +2          [MH]D7 DEF 2             $45  Grave Ring | Mirror Helm
10  [  ]IMMUNE TO DARK    [  ]REFLECTS DARK        $45
11                                                 $00
12  CHARMS: WEAR ONE RING OR AMULET                $06
13  [MR]ATK +1            [WR]DEF +1               $47  Might Ring | Ward Ring
14  [  ]                  [  ]                     $47
15  [FR]HALF DMG          [MA]2X MP REGEN          $45  Fire Ring | Mana Amulet
16  [  ]FROM FIRE         [  ]                     $45
17  [FA]HALF HUNGER                                $47  Food Amulet | (empty half)
18  [  ]                                           $47
19                                                 $00
20  METAL ARMOUR OR HELM STOPS MAGE SPELLS         $05
21  ROBE OR HOOD STOPS POWER ATTACKS               $05
22  BOSS TREASURES AND CHARMS NEVER DO             $05
23                ANY KEY: START                   $46
```
(In the sketch the icon is drawn over chars 0–2 / 21–23, which are spaces in the `.txt`.)

| Row | Text attr | Icons (cells, logical icons16 index, attr) | Text: chars / len |
|---|---|---|---|
| 00 | `$46` | — | as built, 42 |
| 01 | `$00` | — | 0 |
| 02 | `$06` | — | 0–35, 36 |
| 03–04 | `$47` | `h_king` 30 @ (3,0) `$07`; `a_silk` 26 @ (3,16) `$07` | L 3–10, R 24–41 / L 3–10, R 24–39; 42 / 40 |
| 05–06 | `$45` | `a_grave` 27 @ (5,0) `$07`; `w_cleaver` 17 @ (5,16) `$07` | L 3–20, R 24–41 / L 3–19, R 24–29; 42 / 30 |
| 07–08 | `$47` | `w_bone` 21 @ (7,0) `$06`; `c_scarab` 37 @ (7,16) `$06` | L 3–14, R 24–37 / L 3–14, R 24–34; 38 / 35 |
| 09–10 | `$45` | `c_grave` 38 @ (9,0) `$06`; `h_mirror` 31 @ (9,16) `$07` | L 3–10, R 24–31 / L 3–16, R 24–36; 32 / 37 |
| 11 | `$00` | — | 0 |
| 12 | `$06` | — | 0–30, 31 |
| 13–14 | `$47` | `c_might` 32 @ (13,0) `$06`; `c_ward` 33 @ (13,16) `$06` | L 3–8, R 24–29 / none; 30 / 0 |
| 15–16 | `$45` | `c_fire` 34 @ (15,0) `$06`; `c_mana` 35 @ (15,16) `$06` | L 3–10, R 24–34 / L 3–11; 35 / 12 |
| 17–18 | `$47` | `c_plenty` 36 @ (17,0) `$06`; right half empty | L 3–13 / none; 14 / 0 |
| 19 | `$00` | — | 0 |
| 20–22 | `$05` | — | the class-gate tip, verbatim from INSTR-P3; 38 / 32 / 34 |
| 23 | `$46` | — | footer as built, 28 |

Order: the uniques by depth, read left to right, then down. The `$47` / `$45` alternation is per
grid row (both lines of both entries share the ink; the icon tells the entries apart). Headers
`$06`, notes `$05`, title and footer `$46`: the page adds no new attr values. The icon inks are
the bag page's (items.txt INK: helms, cloaks, Cleaver `$07`; Bone Staff and all rings/amulets
`$06`), so the player sees the same picture in the same colour as in the bag.

**Class-gate tip:** stays on page 3, rows 20–22, verbatim (page 2 is full). It is what tells the
player that the King Helm and Mirror Helm do not block spells, and the cloaks do not block power
attacks.

## 4. `tools/instr_pack.py` `PAGES[3]`

```
3: {
    "fills": (_rows_fill([0, 23], 0, 31, 0x46) + _rows_fill([2, 12], 0, 31, 0x06)
              + _rows_fill([3, 4, 7, 8, 13, 14, 17, 18], 0, 31, 0x47)
              + _rows_fill([5, 6, 9, 10, 15, 16], 0, 31, 0x45)
              + _rows_fill([20, 21, 22], 0, 31, 0x05)),
    "icons": [("i16", "h_king", 3, 0, 0x07), ("i16", "a_silk", 3, 16, 0x07),
              ("i16", "a_grave", 5, 0, 0x07), ("i16", "w_cleaver", 5, 16, 0x07),
              ("i16", "w_bone", 7, 0, 0x06), ("i16", "c_scarab", 7, 16, 0x06),
              ("i16", "c_grave", 9, 0, 0x06), ("i16", "h_mirror", 9, 16, 0x07),
              ("i16", "c_might", 13, 0, 0x06), ("i16", "c_ward", 13, 16, 0x06),
              ("i16", "c_fire", 15, 0, 0x06), ("i16", "c_mana", 15, 16, 0x06),
              ("i16", "c_plenty", 17, 0, 0x06)],
},
```
The fills cover whole rows; `attr_grid` then overwrites the icon cells with the icon attr (as
on page 2). Two new static asserts in `instr_pack.py` (cheap, catch drift): (a) for every i16
icon at (r, c), every char k whose pixels x 6k..6k+5 overlap x 8c..8c+15 is a space (or past
the row's end) in rows r and r+1, i.e. chars 0–2 for col 0 and chars 21–23 for col 16; (b) the i16 attr == the item's INK
in `src/items.txt` (`IT_` + the icon name upper-cased; `c_plenty` → `IT_C_PLENTY`).

## 5. Where the icon bytes come from at boot (answer for the engineer)

- The icon data is `icpk_idx` + `icpk` (packed icons16, 995 B) in the **R6 region, bank 6**, read
  only by R6 code. `ic_scr` (A = logical index, DE = bitmap address of the UL cell) does the
  logical → physical map (`ic_find`) and the MIRROR icons itself (`h_king`, `c_ward`,
  `c_plenty`, `c_grave` here), and writes no attrs.
- The overlay already reads it at boot: `instr_ovl.asm` `.ic` pages `BANK_R6` per icon record
  and its `.i16` path calls `ic_scr`; page 2 draws 6 i16 icons this way today. So R6 is loaded
  before `boot6_wait`, and page 3 needs **0 new code bytes and no new icon path** (same `in_page`
  draw, 13 records instead of 0). Attrs are still written last by the RLE.
- Draw cost: 13 × ~2.6k T (~4k T for the 4 MIRROR ones) ≈ 40k T extra, before the attr reveal
  (unseen, boot only).

## 6. Number check (every figure against the build)

| Entry | Text | Source |
|---|---|---|
| King Helm (D1) | DEF 1, DODGE +1 | `src/items.txt` IT_H_KING `0 0 1 0 0`; `src/gear6.asm` gx_tab eva 1 |
| Silk Cloak (D2) | DEF 1, DODGE +2, IMMUNE TO POISON | items.txt DEF 1; gx_tab eva 2, `IMMF_POISON` |
| Grave Cloak (D3) | DEF 2, HALF DMG FROM DARK + DRAIN | items.txt DEF 2; gx_tab `RSP_R \| RSP_R<<2` (R = ×½, game.md §6.0) |
| Warlord Cleaver (D4, Warrior) | 1D10+1, ATK +1 | items.txt `10 1`; gear6 `gear_dec` Cleaver +1; uniq_tab D4 W |
| Bone Staff (D4, Mage) | 1D6, SPELL DMG +2 | items.txt `6 0`; `src/proj3.asm` STAFF-BONUS (Bone +2) |
| Scarab Amulet (D5) | 2X MP REGEN, HALF HUNGER | gear6 MP_PER `IT_C_SCARAB` srl; `src/hunger7.asm` PLENTY..SCARAB |
| Grave Ring (D6) | MP +2, IMMUNE TO DARK | items.txt MP 2; gx_tab `RSP_I<<2` |
| Mirror Helm (D7) | DEF 2, REFLECTS DARK | items.txt DEF 2; gx_tab `RSP_X<<2`; `ranged6.asm` .refl, `arch6.asm` am_cast |
| Might / Ward Ring | ATK +1 / DEF +1 | items.txt `0 1 0` / `0 0 1` |
| Fire Ring | HALF DMG FROM FIRE | gx_tab `RSP_R<<2` on B0 |
| Mana / Food Amulet | 2X MP REGEN / HALF HUNGER | gear6 `IT_C_MANA`; hunger7 `IT_C_PLENTY` (FOOD burn ×½) |
| Class gate | metal/helm ban spells, robe/hood ban power attacks; uniques, charms exempt | `docs/design/gear_rules.md` §1.1–1.2 |

Base values only (Enchant can raise a unique's m, GEAR3 G3-7; q = 0 for uniques), as before.
Wording: `DMG` is the only abbreviation (18-char columns); `2X` / `HALF` give the player the
number; Scarab, Mana and Food use the same words because they are the same effects. `D4
WARRIOR:` / `D4 MAGE:` say which hero the D4 boss drops each weapon for.

## 7. Budget (enc_row: chars, a run of ≥ 2 spaces = 1 B, 0 per row)

| Item | Bytes |
|---|---|
| Page 3 text (row sums 34,1,37,29,27,39,26,29,26,19,30,1,32,15,1,22,11,13,1,1,39,33,35,16) | **517** |
| Icon records (13 × 5 B + terminator) | **66** |
| Attr RLE (59 runs × 2 + terminator; rows 12/13 merge on `$06`) | **119** |
| **Page 3 raw** | **702** (was 741, −39; window 1,536 − 374 B code = 1,162 → 460 left; page 1 at 772 stays the largest) |
| Code | **0** (the i16 path exists) |
| **Packed (ZX0)** | ≈ 510–530 B (0.72–0.75; the icon records and the 2-column rows compress about like text) |
| **Expected tape delta vs main** | ≈ **0 B (−40..+20)**, bank-0 text block only; resident bytes 0; `instr_zx0_end` (`$D185`) moves by the same ± and stays far below `tap_loader` `$E000` |

The tool's figures (`instr_pack: p3 text … attrs …`) are authoritative; if they differ from 517 /
119 by more than a few bytes the `.txt` rows were not copied verbatim.

## 8. Test vectors (tests/instr.py, model = `gen_instr_mock.page(3)` from `PAGES[3]`)

- **I9** (update): page 3 (`GS_HELP3`) == page(3), all 6,912 bytes; on failure report the rows
  that differ. The mock renders i16 icons from the decoded icons16 table (MIRROR applied), as for
  page 2.
- **I9a icon cells:** for each of the 13 records, the 4 cells' 32 bitmap bytes == the decoded
  icon (incl. the 4 MIRROR icons `h_king`, `c_ward`, `c_plenty`, `c_grave`) and the 4 attrs ==
  the record attr; the 4 text cells' rows beside an icon carry the row's text attr (cell 2 and
  cell 18 of rows 3–10, 13–18).
- **I9b empty half:** rows 17–18 cells 16–31 bitmap all 0, attr `$47`; rows 14 and 18 bitmap
  all 0 outside the icon cells.
- **I9c full-width rows:** rows 03 and 05 (right text ends at char 41 = x 246–251, cell 31) and
  row 05 left (char 20 ends at x 125, cell 15; cell 16 holds only the Cleaver icon).
- **I9d plain rows:** 01/11/19 all zero (bitmap and attr `$00`); 20–22 attr `$05`; 23 == page 2's
  old row 23 bitmap (as built).
- I1–I5, I10, I11 unchanged (flow is unchanged).
- **Static** (`instr_pack.py` asserts + `gen_instr_mock.py --check`): 24 rows, each ≤ 42 chars,
  chars 32..127; the attr RLE covers 768 cells; ≤ 2 colours per cell; §4 asserts (a) and (b);
  page 3 raw ≤ `GEN_SCRATCH_LEN − code`.

Files the engineer touches: `docs/design/instructions_screen.txt` (PAGE 3 ROWS block, and its
page-3 ATTRS / ICONS notes if present), `tools/instr_pack.py` (`PAGES[3]` + the two asserts),
`tools/gen_instr_mock.py` (only if its i16 path is page-2-specific), `tests/instr.py` (I9a–d),
the regenerated `instr_p3.png` mock; memory-map INSTR-BUILD figures after the build.
