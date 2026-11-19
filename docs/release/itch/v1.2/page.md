# Tome of the Dead: itch.io page draft (v1.2 "Major Update")

Paste each block into the matching itch.io field. Text in [square brackets] is for you to fill in or decide. Draft only: nothing here is public until you approve it.

---

## 1. Title and short description

**Title:** Tome of the Dead

**Short description / tagline (57 chars):**
ZX Spectrum 128K roguelike. Eight depths, one cursed book.

(Platform and genre first: itch search cards cut the tagline after about 45 characters; the full text shows on hover.)

---

## 2. Description (paste into the rich editor)

A cursed book lies under eight dark depths. It hurts everyone who comes near it. There is no way back and no saving. Find the keys, kill the boss of each depth and go down.

**Tome of the Dead** is a turn-based dungeon game for the ZX Spectrum 128K. Choose a Warrior or a Mage. The depths are new every game. If you die, you start again. **Play it here in your browser**, or download it for an emulator or a real 128K.

### Features

- **Two heroes.** The Warrior uses a sword, daggers, a bow and power attacks. The Mage uses a staff and five spells.
- **New depths every game.** Eight depths, 10 to 12 rooms each, with doors, ladders, pits to jump and hidden traps.
- **Keys and locked doors.** Find the key of the right colour to open the way on.
- **A boss on every depth.** Each one guards the way down and drops a treasure. The last boss guards the Tome.
- **Many monsters.** From rats and goblins to vampires, ghosts and the Deathlord.
- **Items.** Potions, scrolls, food, books, weapons, armour, rings and amulets. The bag shows what each item does.
- **Music and sound** on the 128K sound chip.
- **Joystick or keyboard.** Kempston, Sinclair 1 and 2, or your own keys. (The browser version is keyboard only.)

### New in v1.2

- **Bigger depths**: 10 to 12 rooms instead of 9.
- **Keys and locked doors** in two colours.
- **Three new monsters**:
  - a **Gargoyle** that looks like a statue until you come close;
  - a **Fire Imp** that spits fire;
  - an **Ice Shade** (Frost Wraith) that can freeze you.
- **A tutorial** with Brother Morrow, who shows you how to play.
- **Item details** in the bag.
- **Smarter monsters**: they follow you further.
- **More things in the rooms**, and an **XP bar** on the screen.
- **Balance changes**: slower hunger, a safer Teleport, stronger monsters deeper down.

### Controls

Keys: **Q A O P** to move, **SPACE** to fire. You can change them in the menu. Everything also works with a joystick.

**Moving**

| Action | Keys | Joystick |
|---|---|---|
| Walk, turn round, attack by walking into a monster, open a door | O / P | Left / Right |
| Climb a ladder up / down | Q / A | Up / Down |
| Jump a narrow pit | Q+O / Q+P | Up+Left / Up+Right |
| Wait a turn and search for traps | A with no ladder below, or **.** (SYMBOL SHIFT+M) | Down |

Tap to turn round. Hold to walk.

**Icons (attacks, spells, items)**

The icon bar holds your attacks, spells, items and the bag.

| Action | Keys | Joystick |
|---|---|---|
| Use the selected icon, towards the way you face | SPACE or ENTER | tap FIRE |
| Select an icon directly | **1**-**9**, **0** (slot 10) | - |
| Icon mode: pick an icon with the game paused | A+SPACE | Down+FIRE together |
| In icon mode: move / use / leave | O P / SPACE / Q, A or BREAK | Left Right / FIRE / Up or Down |
| Close the door you face, or strike the Tome | use the sword or staff icon | same |

If an icon can't be used yet, the game tells you why and you lose no turn.

**Bag (inventory)**

| Action | Keys | Joystick |
|---|---|---|
| Open the bag | **I**, or use the BAG icon | FIRE on the BAG icon |
| Move / choose an action (eat, drink, read, equip, discard) / confirm / back | Q A O P / O P / SPACE / A+SPACE | directions / Left Right / FIRE / Down+FIRE |

You pick up items by walking over them.

**Pause and sound**

| Action | Keys | Joystick |
|---|---|---|
| Pause (Resume, Sound, Quit) | BREAK | hold FIRE + Up |
| Cycle sound: all on, effects only, off | **S** | via Pause, Sound |
| Quit confirmation | Y or FIRE = yes, anything else = no | FIRE = yes |

**Main menu** (number keys only)

**1** Start (or ENTER) - **2** Hero: Warrior / Mage - **3** Controls: Keys, Kempston, Sinclair 1, Sinclair 2 - **4** Redefine keys - **5** Sound: all on, effects only, off.

- New players: after Start, choose **1 TUTORIAL**. Choose **2 START** to skip it.
- **Sinclair 1** uses keys 6-0, **Sinclair 2** keys 1-5 (Interface 2 / +2 joystick ports). Kempston works only when selected.
- **Redefine** asks for UP, DOWN, LEFT, RIGHT, FIRE. ENTER, 1-0, I, S, CAPS SHIFT and SYMBOL SHIFT are reserved; BREAK cancels and keeps your old keys.
- After death or victory, press 1-5 or ENTER to return to the menu.

### How to play

- **Browser:** press Play on this page. Keyboard only.
- **Emulator:** set it to ZX Spectrum 128K. Open the `.tap` file and choose Tape Loader, or open the `.sna` file to start at once.
- **Real Spectrum:** load the `.tap` with a tape interface, TZXDuino or divMMC. Choose **Tape Loader** on a 128K or +2, **Loader** on a +2A, +2B or +3. v1.2 was tested on a real ZX Spectrum 128K.

### System requirements

- ZX Spectrum 128K, +2, +2A, +2B or +3, or an emulator set to one of them.
- **Not for the 48K.**
- Browser version: a desktop browser and a keyboard.

### Credits

- By alstepan.
- WazHack-inspired (https://www.wazhack.com/).
- Built with sjasmplus. Data compression by ZX0 by Einar Saukas and Urusergi (BSD 3-Clause; the ZX0 decompressor is included in the game).
- Browser play uses JSSpeccy 3 (GPL-3, unmodified; its licence and corresponding source are inside the web build).
- Licence: code MIT, art, music and text CC BY 4.0. Source: https://github.com/alstepan/tome-of-the-dead
- The code, tools and tests were written by AI agents. The author directed and checked the work.
- Music composed with Google Flow Music (AI) and arranged for the AY chip.

### Version history

- **v1.2**: bigger depths, keys and locked doors, three new monsters, tutorial, item details, smarter monsters, XP bar, balance changes.
- **v1.1**: text fixes.
- **v1.0**: first public release.

---

## 3. Metadata to set

Changes from v1.1 only; everything else stays.

- **Kind of project:** HTML (browser build) is already live alongside the downloads [CONFIRM how the v1.1 page is configured; the browser zip is re-uploaded as `tome-of-the-dead-web-v1.2.zip`, keep "played in the browser"].
- **Embed / browser play:** JSSpeccy 3, 660x600, fullscreen button on (replaces v1.1's "none").
- **Tags:** unchanged (`roguelike`, `zx-spectrum`, `retro`, `z80`, `8-bit`, `dungeon-crawler`, `turn-based`, `permadeath`, `homebrew`, `fantasy`).

---

## 4. Upload list

| File | Display name on itch |
|---|---|
| `tome-of-the-dead-v1.2.tap` | Tape image (.tap), recommended for real hardware and emulators |
| `tome-of-the-dead-v1.2.sna` | Snapshot (.sna), instant start in emulators |
| `tome-of-the-dead-web-v1.2.zip` | Browser build (`tools/web_bundle.sh v1.2`) |
| `SHA256SUMS` | Checksums (SHA-256) |
| `LICENSE`, `LICENSE-ASSETS.md`, `THIRD-PARTY.md` | Licences and third-party notices |

Hide the v1.1 files after v1.2 is uploaded. Screenshots: see `screenshots.md` (most in-game shots need re-capturing).
