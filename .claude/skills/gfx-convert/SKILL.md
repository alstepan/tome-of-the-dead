---
name: gfx-convert
description: Convert a source image (concept art or hand-drawn pixels) into ZX Spectrum attribute-legal data and emit it as Z80 DEFB byte tables, validating against attribute clash. Use to turn graphics into engine-ready asm; never ship AI-generated raster directly.
---

# gfx-convert

Turn an image into Spectrum-legal **asm byte data**. This skill exists because
AI/raster images are NOT usable on the Spectrum: the screen is 1-bit bitmap +
a 32×24 grid where each 8×8 cell has only 2 colours ("attribute clash").

## Pipeline

```
source image  →  resize/crop to target cell grid  →  quantise to 1-bit per cell
              →  enforce ≤2 colours per 8×8 cell    →  pack to bitmap+attr bytes
              →  emit Z80 DEFB tables               →  validate (round-trip)
```

## Targets

- **UDG / tile (8×8)**: one cell, 8 bytes bitmap + 1 attribute byte.
- **Sprite (W×H cells)**: bitmap bytes row-major + optional mask + attr block.
  (Whether sprites are used at all depends on the rendering approach the
  `game-designer` agent selects — check `docs/design/`.)

## Implementation

Create `tools/gfx_convert.py` (Pillow) on first use:
- input: PNG + target cell dimensions + ink/paper palette choice.
- per 8×8 cell: pick the 2 dominant colours, map to nearest Spectrum palette
  entries (15 colours: 8 normal + 7 bright), threshold pixels to ink/paper.
- output: `assets/gfx/<name>.asm` with labelled `DEFB` bitmap + attr tables, and
  a header comment recording source file, dimensions, and the chosen palette.

## Validation (must pass before committing data)

- **Clash check**: every 8×8 cell resolves to exactly one attribute (≤2 colours).
  Reject and report any cell needing 3+ colours — the artist must redraw it.
- **Round-trip**: decode the emitted bytes back to an image; it must match the
  quantised target. This catches packing bugs.

## Rules

- The committed artifact is the `.asm` byte table, not the PNG. Keep the source
  image under `assets/gfx/` for re-derivation, but code references the asm labels.
- Concept art from Ollama/ComfyUI is an *input* to redraw against — never a
  direct input to this converter expecting good output.
