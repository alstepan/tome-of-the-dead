# HOW TO PLAY screen (INSTR1) — proposed wording, for user approval

Designer, 2026-10-30. Supersedes the text, flow and 32-col layout in game.md §3.2.1 (that
section now points here). Exact render spec (rows, cells, attrs, icon coordinates):
`docs/design/instructions_screen.txt`. Implementation waits for 3F to finish.

## 1. Flow (user ruling 2026-10-30)

- **Shown every game: after START, before D1** (the seed is already taken at START). Page 1 →
  any key → page 2 → any key → play. **BREAK on page 1 skips page 2** (repeat players: 1 press).
- A key counts only after all keys have been released once (the START `1`/ENTER is still held).
- The selected controls are live from START, so the selected joystick's FIRE also counts.
  Kempston is read only if it is selected (§3.2).
- Fallback if no memory is found after 3F: Option A of §3.2.1 (once per power-on, before the
  menu); then the footer reads `PRESS ANY KEY` and Kempston is not read.

## 2. Grid rules (FONT6, attribute-legal)

- 42 chars × 24 rows; char `k` at x = 6k px; paper black, border black, no FLASH.
- A colour change inside a text row only at chars 0, 4, 8 … (24-px boundaries).
- Page 1 fields: STICK chars 0–11 (cells 0–8) `$45`, ACTION chars 12–31 (cells 9–23) `$47`,
  KEY chars 32–41 (cells 24–31) `$46`.
- 24×16 bar icons: cells 0–2, text from char 4. 16×16 item icons: cells 0–1 / 16–17, text in
  chars 3–20 / 24–41 (18 chars each); no text char shares a cell with an icon.

## 3. Layout B — two pages (main proposal, recommended)

Page 1: the goal and the controls. `[..]` = icon (not text); attr per row on the right.

```
    0         1         2         3         4
    012345678901234567890123456789012345678901
00        TOME OF THE DEAD - HOW TO PLAY   1/2   $46
01                                               -
02  FIND THE KEY, UNLOCK THE LAIR, KILL ITS      $47
03  BOSS: ITS GRATE IS THE WAY DOWN              $47
04  ON DEPTH 8 SLAY THE ARCHMAGE, THEN   [lect]  $47 + lectern tiles cells 30-31
05  DESTROY THE TOME OF THE DEAD      [ern ]  $47
06                                               -
07  STICK       ACTION              KEY          $06
08  LEFT/RIGHT  WALK, HIT, OPEN DOOR             F
09  UP/DOWN     CLIMB A LADDER                   F
10  UP+L/R      JUMP NARROW PITS                 F
11  DOWN        WAIT, SEARCH TRAPS  SYM+M        F
12  FIRE TAP    USE SELECTED ICON   ENTER        F
13  DOWN+FIRE   CHOOSE AN ICON      1-0          F
14              L/R MOVE, FIRE USE, UP EXIT      $47
15  FIRE+UP     PAUSE: SOUND, QUIT  BREAK        F
16  [bag]FIRE ON BAG: INVENTORY      I           icon $06, $47, KEY $46
17  [   ]EAT, DRINK, READ, EQUIP, DISCARD        icon $06, $07
18  [swd]FIRE ON SWORD/STAFF: HIT, OR CLOSE      icon $47, $47
19  [   ]THE OPEN DOOR YOU FACE                  icon $47, $07
20                                               -
21  Q A O P SPACE = UP DOWN LEFT RIGHT FIRE      $05
22  MENU: 3 PICKS JOYSTICK, 4 REDEFINES KEYS     $05
23       ANY KEY: NEXT PAGE   BREAK: SKIP        $46
```
`F` = the 3 fields (§2). (Icon rows: the text starts at char 4; in the .txt the icon area is spaces.)

Page 2: things you find, and tips.

```
    012345678901234567890123456789012345678901
00                ITEMS AND TIPS           2/2   $46
02  WALK OVER ITEMS TO TAKE THEM                 $06
03  [P]POTION - DRINK IT    [M]FOOD - EAT IT     $47   P = p_heal, M = f_meat
04  [ ]HEAL, MANA, CURE     [ ]OR GROW WEAK      $07
05  [S]SCROLL - READ IT     [B]BOOK - READ IT    $47   S = s_teleport, B = book
06  [ ]SLEEP FEAR ENCHANT   [ ]NEW SPELL OR SKILL $07
07  [D]DAGGERS, ARROWS      [W]WEAPON, ARMOUR    $47   D = ammo_dagger, W = w_long
08  [ ]WARRIOR AMMO         [ ]EQUIP IN THE BAG  $07
09  [K]KEY                  [G]GRATE - WAY DOWN  $47   K = label_key, G = grate tiles
10  [ ]OPENS THE LAIR       [ ]OPENS IF BOSS DIES $07
12  TIPS                                         $46
13  * DOWN WAITS A TURN AND SEARCHES FOR TRAPS   $47
15  * HUNGER NEVER KILLS, BUT THE WEAK FAINT      $45
17  * NO WAY BACK UP: LOOT EACH DEPTH FIRST       $47
19  * SWARMED? READ SLEEP, FEAR OR TELEPORT       $45
21  * STANDING NEAR THE TOME HURTS YOU            $47
23                 ANY KEY: START                  $46
```
Rows 01, 11, 14, 16, 18, 20 and 22 are blank (tips are bulleted `* `, only the 5 most important kept). (Here `[X]` is drawn 3 chars wide to keep the text columns
visible; the real 16×16 icon fills cells 0–1 / 16–17 and the text starts at char 4 / 24.)

**Icons used (all exist; nothing new needed):** bar icons `icon_bag`, `icon_sword`
(`assets/gfx/panel/panel_icons.asm`, 24×16); `icons16` `p_heal`, `f_meat`, `s_teleport`,
`book`, `ammo_dagger`, `w_long` (16×16); `label_key` (8×8, panel labels); map tiles
`T_GRATE_SHUT` (common 13, 2×2 repeat) and the lectern (common 15–18). **Optional, missing:**
a 16×16 key icon (today only the 8×8 label exists; the key row works without it).
Hero/monster sprites are not used: one 24×48 sprite costs 6 rows of a 24-row page and
explains nothing the text does not.

**Budget:** ≈ 1.2 KB of printable text over both pages (padding stored as column offsets),
less after `textpack` tokenising. Natural home: two `@long` blocks in `src/strings.txt`
(`help1`, `help2`) replacing the obsolete placeholder. Trim order if needed: tips 21, 18, 14.

## 4. Layout A — one dense screen (alternative)

```
00        TOME OF THE DEAD - HOW TO PLAY         $46
01  FIND THE KEY, UNLOCK THE LAIR, KILL ITS      $47
02  BOSS: ITS GRATE IS THE WAY DOWN. ON DEPTH    $47
03  8 SLAY THE ARCHMAGE, DESTROY THE BOOK        $47
04  STICK       ACTION              KEY          $06
05  LEFT/RIGHT  WALK, HIT, OPEN DOOR             F
06  UP/DOWN     CLIMB A LADDER                   F
07  UP+L/R      JUMP NARROW PITS                 F
08  DOWN        WAIT, SEARCH TRAPS  SYM+M        F
09  FIRE TAP    USE SELECTED ICON   ENTER        F
10  DOWN+FIRE   CHOOSE AN ICON      1-0          F
11              L/R MOVE, FIRE USE, UP EXIT      $47
12  FIRE+UP     PAUSE: SOUND, QUIT  BREAK        F
13  FIRE ON BAG INVENTORY               I        F
14  FIRE ON SWORD/STAFF: CLOSE A FACED DOOR      $07
15  Q A O P SPACE = UP DOWN LEFT RIGHT FIRE      $05
16  WALK OVER ITEMS TO TAKE THEM                 $44
17  HUNGER NEVER KILLS, BUT THE WEAK FAINT       $44
18  NO WAY BACK UP: LOOT EACH DEPTH FIRST        $44
19  BOSSES NEVER LEAVE THEIR LAIR                $44
20  SWARMED? READ SLEEP, FEAR OR TELEPORT        $44
21  ENCHANT GIVES A WORN ITEM +1                 $44
22  STANDING NEAR THE TOME HURTS YOU             $44
23               PRESS ANY KEY                   $46
```
No icons, no item list, no blank rows: ≈ 0.85 KB, one key press.

**Recommendation: B.** It has room for the item icons (the player learns what a potion,
scroll, key and the exit grate look like), keeps blank rows so it can be read at a glance,
and BREAK keeps it to one press for repeat players. A is the fallback if 3F leaves < 1 KB.

## 5. Non-obvious controls that must appear (verified)

| Control | Behaviour | Source |
|---|---|---|
| DOWN + FIRE, either first, within 3 ticks | ICON MODE: L/R move, FIRE use, UP/DOWN/BREAK exit | `src/io.asm` `intent_tick` `.fd`/`.enter`, header; §3.1 |
| `1`–`0` | move the icon cursor only (no use) | `io.asm` `sel_key`; §3.1 |
| FIRE tap (released, no direction) / ENTER | use the selected icon toward the facing | `io.asm` `.play`, `SC_ENTER`; §3.1 |
| FIRE held, then UP / BREAK | Pause (Resume / Sound / Quit) | `io.asm` `.nfu`, `pause_hook` |
| UP + LEFT/RIGHT | always a jump | `src/bank7.asm` `tpt_intent`; §2.4 |
| DOWN with no ladder below / `.` (SYM+M) | Wait, which also searches for traps | `bank7.asm` `tpt_intent`; `io.asm` `.nDot`; `src/trap6.asm` |
| FIRE on the BAG icon / `I` | bag page (eat, drink, read, equip, discard) | `io.asm` `IN_BAG`; §8 |
| FIRE on sword/staff, no foe in reach | closes the faced open door | `src/intent7.asm` `ic_melee` `.door` |
| Walk into a door | opens it; locked = needs the key | `src/lowram.asm` `hero_door` |
| Pickups | automatic | §8 |
| Defaults Q A O P SPACE; menu `3` controls, `4` redefine | — | §3.2, `menu1.asm` |

Left out on purpose: tap-to-turn (0 turns), `S` sound hotkey (Pause has SOUND), the Mage's
automatic trap sense.

## 6. Conflicts with the game or the brief (flagged)

1. **The hero cannot parry.** Only Boneguard, Revenant and Deathlord parry (and notch your
   weapon, §8.10). The screen says only `ENCHANT GIVES A WORN ITEM +1` (GEAR3, 2026-11-01).
2. **There are no stairs.** You climb ladders and leave by the lair grate; the text says so.
3. **The name of the goal.** The title says TOME; the game says `THE BOOK IS DESTROYED`
   (Book of Absolute Death Magic). The screen uses BOOK OF DEATH MAGIC. **User:** keep BOOK,
   or rename the Book to the Tome everywhere?
4. **The key.** The panel key icon arrives in 3F (`panel_hot.asm`), and lair-door key gating
   is from 3F (§1.1 (7)). `FIND THE KEY, UNLOCK THE LAIR` is true only once 3F is in;
   check this before shipping. The key is taken on entering the key room, not picked up.
5. **`src/strings.txt` `@long help` placeholder is wrong** (FIRE+L/R moves the cursor,
   FIRE+DOWN opens the inventory: both obsolete). Replace it with this text.
6. **Sinclair 1/2** turn off the `1`–`0` keys on their half of the number row (§3.1), so `1-0`
   in the KEY column is only partly true for them. Accepted.
7. **FIRE+UP order:** FIRE must be held first (UP first means climb). DOWN+FIRE works in either
   order. The labels follow that order.
8. **Jumping:** wide pits (4–6 cols) cannot be jumped, so the text says NARROW PITS. Low foes
   can also be jumped; that is left out.
9. **§3.2.1 is out of date** (32 cols, once per boot, 0.7 KB in the boot block). It now points
   here; its budget and tests must be redone for "after START" when 3F is done.
