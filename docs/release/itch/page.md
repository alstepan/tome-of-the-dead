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

Defaults shown. You can pick a joystick or redefine the keys from the main menu.

| Action | Keys (default) | Joystick |
|---|---|---|
| Walk, turn, attack, open door | O / P | Left / Right |
| Climb a ladder | Q / A | Up / Down |
| Jump a narrow pit | Q+O / Q+P | Up-Left / Up-Right |
| Wait a turn and search for traps | A (when no ladder below), or SYMBOL SHIFT+M | Down |
| Use the selected icon | SPACE (or ENTER) | FIRE tap |
| Choose an icon | 1–0 directly, or A+SPACE, then O / P, then SPACE | Down+FIRE, then Left / Right, then FIRE (Up exits) |
| Inventory | I, or FIRE on the BAG icon | FIRE on the BAG icon |
| Pause (resume, sound, quit) | BREAK | FIRE held + Up |

Main menu keys: **1** Start, **2** Hero (Warrior or Mage), **3** Controls (Keys, Kempston, Sinclair 1, Sinclair 2), **4** Redefine keys, **5** Sound. The number keys 1-0 also jump to icon slots in game.

### How to load

- **Emulators (Fuse, ZEsarUX, others):** set the machine to ZX Spectrum 128K, then either open `tome-of-the-dead-v1.0.tap` and let it load (type `LOAD ""` or choose Tape Loader), or open `tome-of-the-dead-v1.0.sna` directly for an instant start.
- **Real 128K, +2, +2A or +3 hardware:** play the `.tap` through a tape interface, TZXDuino, divMMC or similar, and load it from the 128 tape loader. Tested on real hardware.

### System requirements

- ZX Spectrum 128K, +2, +2A or +3 (or an emulator in 128K mode).
- **48K machines are not supported.** The game needs the extra RAM banks and the AY sound chip.
- Keyboard; joystick optional (Kempston, Sinclair 1 or 2).

### Credits

- Design and code: [YOUR NAME]
- WazHack-inspired.
- Built with sjasmplus. Data compression by ZX0 by Einar Saukas.
- Developed with AI assistance. [Edit this line as you prefer.]

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
- **Licence / content:** leave "All rights reserved" unless you decide otherwise.
- **Embed / browser play:** none.

---

## 4. Upload list

| File | Display name on itch |
|---|---|
| `tome-of-the-dead-v1.0.tap` | Tape image (.tap), recommended for real hardware and emulators |
| `tome-of-the-dead-v1.0.sna` | Snapshot (.sna), instant start in emulators |
| `SHA256SUMS` | Checksums (SHA-256) |

Mark none as "executable for a platform"; leave platform tags unset.

---

## 5. Devlog post: "v1.0 released"

**Tome of the Dead v1.0 is out.**

It is a turn-based roguelike for the ZX Spectrum 128K, written in hand-coded Z80 assembly. Choose a Warrior or a Mage and descend through eight randomly generated depths. Each has a locked lair with a boss that guards the grate down. On depth 8 the Necromancer Archmage waits, and beyond him the Tome itself.

This first release has two classes, a full bestiary with a boss on every depth, spells, gear, boss treasures, hunger and status effects, AY music and effects, and Kempston, Sinclair or redefinable-key control. There is no saving, so every run counts.

Download the `.tap` for tape-style loading or the `.sna` for an instant start in an emulator, and check the `SHA256SUMS` file if you like. It needs a 128K machine: 48K is not supported. It has been tested on real hardware.

Bug reports and run stories are very welcome in the comments. Thank you for playing.

---

## 6. Open questions for you

1. Author name or handle for the Credits line, and do you want a contact or source link?
2. Is the "developed with AI assistance" wording acceptable, or do you want it stronger, softer or removed?
3. Licence: keep "All rights reserved", or choose a permissive one (e.g. a Creative Commons licence) for the game?
4. Screenshots and cover image (itch wants a 630x500 cover plus 3-5 screenshots): which captures should I plan, e.g. menu, a play room, a boss fight and the Tome?
5. Should the page say "tested on real hardware" for specific models (which 128K, +2 or +3 machines you used), or stay generic as drafted?
