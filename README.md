# Tome of the Dead

A roguelike for the **ZX Spectrum 128K**, WazHack-inspired, written directly in
Z80 assembly (no compiler) by AI agents: developed agentically with Claude Code
under the author's direction and review.

## Status

Vertical slice in progress. Rendering approach & slice scope are decided by the
`game-designer` agent (see `docs/design/`).

## Toolchain

| Role            | Tool                         |
|-----------------|------------------------------|
| Assembler       | sjasmplus 1.20.x             |
| Run emulator    | Fuse for macOS               |
| Debug/test      | ZEsarUX (ZRCP remote protocol)|
| Pixel editing   | Pixelorama                   |
| Concept art     | Ollama (flux2-klein, z-image-turbo) + ComfyUI |

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

