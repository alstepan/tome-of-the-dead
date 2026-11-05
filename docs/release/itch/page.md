# Tome of the Dead: itch.io page draft (v1.0)

Paste each block into the matching itch.io field. Text in [square brackets] is for you to fill in or decide.

---

## 1. Title and short description

**Title:** Tome of the Dead

**Short description / tagline (92 chars):**
Eight depths, one cursed book. A WazHack-inspired roguelike for the ZX Spectrum 128K.

---

## 2. Description (paste into the rich editor)

The Tome of the Dead lies in the Sanctum beneath eight dark depths, and it hurts all who stand near it. There is no way back up and no saving. Find the key, unlock each lair, break its boss, and take the grate down.

**Tome of the Dead** is a turn-based, side-view dungeon crawler written entirely in hand-coded Z80 assembly for the ZX Spectrum 128K. Pick a Warrior or a Mage, descend, and see how far you get. Death is permanent.

### What you get

- **Two classes.** The Warrior fights with sword, throwing daggers, a bow found on depth 2, and mana-fuelled power attacks. The Mage fights with a staff and five spells: Spark, Firebolt, Frost Shard, Drain Life and Lightning.
- **Eight depths**, each freshly generated every run from a 3x3 grid of rooms, with doors, ladders, pits you can jump, and traps you can search for.
- **A boss on every depth.** Each guards a lair and a locked grate. Kill it to open the way down. Each drops a unique treasure, from the Goblin King's Helm on depth 1 to the Mirror Helm of the Death Knight on depth 7.
- **A final fight.** On depth 8 you must slay the Necromancer Archmage, then destroy the Tome itself before its aura destroys you.
- **A varied bestiary.** Rats, bats, slimes, goblins, spiders, skeletons, vampires, ghosts, orcs, archers, mummies, necromancers, an Ogre Warlord and a Death Knight, plus the Archmage.
- **Items and gear.** Potions, scrolls, food, skill and spell books, weapons, armour, helmets, rings and amulets. Hunger, poison, fear, confusion and other status effects all matter.
- **XP and levels**, and books that teach or strengthen your abilities.
- **AY-3-8912 music and sound effects** (128K sound chip), with switchable sound options: all on, effects only, or off.
- **Joystick-only play.** Kempston, Sinclair 1 and Sinclair 2 are supported, or use the keyboard with fully redefinable keys.
- **A built-in how-to-play screen** on first start.

### Controls

Every action works with a joystick alone (four directions, diagonals and FIRE). Keyboard players use the default keys **Q A O P SPACE** (up, down, left, right, fire), or redefine them from the main menu. A joystick and the keys work together.

**Moving**

| Action | Keys | Joystick |
|---|---|---|
| Walk, turn round, attack by walking into a monster, open a door | O / P | Left / Right |
| Climb a ladder up / down | Q / A | Up / Down |
| Jump a narrow pit | Q+O / Q+P | Up+Left / Up+Right |
| Wait a turn and search for traps | A with no ladder below, or **.** (SYMBOL SHIFT+M) | Down |

A tap turns you round without spending a turn; holding the direction walks.

**Icons (attacks, spells, items)**

The icon bar along the bottom holds your attacks, spells, quick items and the BAG.

| Action | Keys | Joystick |
|---|---|---|
| Use the selected icon, towards the way you face | SPACE or ENTER | tap FIRE |
| Select an icon directly | **1**-**9**, **0** (slot 10) | - |
| Icon mode: pick an icon with the game paused | A+SPACE | Down+FIRE together |
| In icon mode: move / use / leave | O P / SPACE / Q, A or BREAK | Left Right / FIRE / Up or Down |
| Close the door you face, or strike the Tome | use the sword or staff icon | same |

Using an icon that is not ready (no arrows, no mana, no bow yet) costs no turn and tells you why.

**Bag (inventory)**

| Action | Keys | Joystick |
|---|---|---|
| Open the bag | **I**, or use the BAG icon | FIRE on the BAG icon |
| Move / choose an action (eat, drink, read, equip, discard) / confirm / back | Q A O P / O P / SPACE / A+SPACE | directions / Left Right / FIRE / Down+FIRE |

Items on the floor are picked up automatically at the end of your turn.

**Pause and sound**

| Action | Keys | Joystick |
|---|---|---|
| Pause (Resume, Sound, Quit) | BREAK | hold FIRE + Up |
| Cycle sound: all on, effects only, off | **S** | via Pause, Sound |
| Quit confirmation | Y or FIRE = yes, anything else = no | FIRE = yes |

**Main menu** (number keys only)

**1** Start (or ENTER) - **2** Hero: Warrior / Mage - **3** Controls: Keys, Kempston, Sinclair 1, Sinclair 2 - **4** Redefine keys - **5** Sound: all on, effects only, off.

- **Sinclair 1** uses keys 6-0, **Sinclair 2** keys 1-5 (Interface 2 / +2 joystick ports). Kempston is read only once selected.
- **Redefine** asks for UP, DOWN, LEFT, RIGHT, FIRE. ENTER, 1-0, I, S, CAPS SHIFT and SYMBOL SHIFT are reserved; BREAK cancels and keeps your old keys.
- The how-to-play pages: any key for the next page, BREAK skips them.
- After death or victory, press a number key or ENTER to return to the menu.

### How to load

- **Emulators (Fuse, ZEsarUX, others):** set the machine to ZX Spectrum 128K, then either open `tome-of-the-dead-v1.0.tap` and let it load (type `LOAD ""` or choose Tape Loader), or open `tome-of-the-dead-v1.0.sna` directly for an instant start.
- **Real 128K or +2 (grey) hardware:** play the `.tap` through a tape interface, TZXDuino, divMMC or similar, and load it from the 128 tape loader. Tested on a real ZX Spectrum 128K (the original "toastrack").

### System requirements

- ZX Spectrum 128K or +2 (grey), or an emulator in Spectrum 128K mode. The +2A / +3 are untested (different memory paging and contention). 48K is not supported.
- **48K machines are not supported.** The game needs the extra RAM banks and the AY sound chip.
- Keyboard; joystick optional (Kempston, Sinclair 1 or 2).

### Credits

- By alstepan.
- WazHack-inspired (https://www.wazhack.com/).
- Built with sjasmplus. Data compression by ZX0 by Einar Saukas and Urusergi (BSD 3-Clause; the ZX0 decompressor is included in the game).
- Licence: code MIT, art, music and text CC BY 4.0. Source: https://github.com/alstepan/tome-of-the-dead
- Developed agentically: the Z80 code, tools and tests were written by AI agents under the author's direction and review.
- Music composed with Google Flow Music (AI) and arranged for the AY chip.

### Version history

- **v1.0**: first public release.

---

## 3. Metadata to set

- **Kind of project:** Downloadable
- **Classification:** Game
- **Release status:** Released
- **Pricing:** No payments (free download, no donation prompt)
- **Genre:** Role Playing (secondary: Adventure, if itch lets you pick more than one)
- **Tags (10, lowercase):** `roguelike`, `zx-spectrum`, `retro`, `z80`, `8-bit`, `dungeon-crawler`, `turn-based`, `permadeath`, `homebrew`, `fantasy`
- **Platforms:** tick none (the files are emulator and hardware images, not native Windows, macOS or Linux builds). If you must pick something, use "Other".
- **Community:** enable comments (the simplest option, no moderation of a forum). Add a discussion board only if you want bug reports in one place.
- **Licence / content:** code MIT, art/music/text CC BY 4.0 (`LICENSE`, `LICENSE-ASSETS.md`); third-party notices in `THIRD-PARTY.md`.
- **Embed / browser play:** none.

---

## 4. Upload list

| File | Display name on itch |
|---|---|
| `tome-of-the-dead-v1.0.tap` | Tape image (.tap), recommended for real hardware and emulators |
| `tome-of-the-dead-v1.0.sna` | Snapshot (.sna), instant start in emulators |
| `SHA256SUMS` | Checksums (SHA-256) |
| `LICENSE`, `LICENSE-ASSETS.md`, `THIRD-PARTY.md` | Licences and third-party notices (required: ZX0's BSD notice must ship with the game) |

Mark none as "executable for a platform"; leave platform tags unset.

**Cover image:** `img/cover_b.png` (630x500). **Screenshots:** `img/shot1_menu.png` … `img/shot5_deeper_d5.png`, plus `img/walk_fight.gif`.

---

## 5. Devlog post: "v1.0 released"

**Tome of the Dead v1.0 is out.**

It is a turn-based roguelike for the ZX Spectrum 128K, written in hand-coded Z80 assembly. Choose a Warrior or a Mage and descend through eight randomly generated depths. Each has a locked lair with a boss that guards the grate down. On depth 8 the Necromancer Archmage waits, and beyond the Archmage, the Tome itself.

This first release has two classes, a full bestiary with a boss on every depth, spells, gear, boss treasures, hunger and status effects, AY music and effects, and Kempston, Sinclair or redefinable-key control. There is no saving, so every run counts.

Download the `.tap` for tape-style loading or the `.sna` for an instant start in an emulator, and check the `SHA256SUMS` file if you like. It needs a 128K machine: 48K is not supported. It has been tested on a real ZX Spectrum 128K "toastrack".

Bug reports and run stories are very welcome in the comments. Thank you for playing.
