# Tome of the Dead

A roguelike for the **ZX Spectrum 128K**, WazHack-inspired, written directly in
Z80 assembly (no compiler) by AI agents: developed agentically with Claude Code
under the author's direction and review.

## Play

Free download (`.tap` / `.sna`): https://alstepan.itch.io/tome-of-the-dead ·
trailer: https://youtu.be/IPyLe7Bej_s · releases: see GitHub Releases.

## Compatibility

| Machine | Status |
|---|---|
| ZX Spectrum 128K ("toastrack") | tested on real hardware and in emulators |
| ZX Spectrum +2 (grey) | tested in the ZEsarUX emulator |
| ZX Spectrum +2A / +2B | tested in the ZEsarUX emulator (+2A, ROM 4.0 and 4.1; the +2B pages like the +2A) |
| ZX Spectrum +3 | tested in the ZEsarUX emulator (ROM 4.0 and 4.1); load with the **Loader** menu option (`LOAD ""` from +3 BASIC looks for a disk) |
| 48K / 128K in 48 BASIC | not supported: the game stops with "LOAD FROM 128 BASIC" |

The +2/+2A/+3 have not been tested on real hardware yet.

## Toolchain

| Role            | Tool                         |
|-----------------|------------------------------|
| Assembler       | sjasmplus 1.20.x             |
| Run emulator    | Fuse for macOS               |
| Debug/test      | ZEsarUX (ZRCP remote protocol)|
| Pixel editing   | Pixelorama                   |

## Layout

```
src/            Z80 source (sjasmplus)
assets/gfx      graphics sources + packed asm data
assets/sfx      sound data (deferred)
build/          assembler output (.tap, .sld) — gitignored
docs/           conventions, memory map, design
tools/          build/run/debug/convert helper scripts
.claude/        agents + skills driving the agentic workflow
```

## Workflow (skills)

- `build` — assemble to `build/tome-of-the-dead.tap`
- `run` — launch in Fuse
- `debug` — launch ZEsarUX + drive ZRCP
- `test` — automated assertions + golden-screen regression
- `gfx-convert` — image → attribute-legal → asm data

