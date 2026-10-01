---
name: gfx-convert
description: Import the user's claude.ai Design-canvas sprite sheet (tools/svg_sprites.py) or hand-authored .grid pixels into ZX Spectrum attribute-legal masked Z80 DEFB tables via tools/gfx_convert.py, with clash + round-trip validation; also exports grids back to canvas SVG for review. Use to turn graphics into engine-ready asm; never ship AI-generated raster directly.
---

# gfx-convert

Turn an image into Spectrum-legal **asm byte data**. This skill exists because
AI/raster images are NOT usable on the Spectrum: the screen is 1-bit bitmap +
a 32×24 grid where each 8×8 cell has only 2 colours ("attribute clash").

## Primary path: Design canvas → svg_sprites.py → gfx_convert.py

The user's claude.ai Design canvas is the source of sprite art. The manager
vendors it to `assets/gfx/source/*.dc.html`; then:

```
python3 tools/svg_sprites.py import      # sheet -> grid/*.grid -> gfx_convert
                                          #   --layout native -> sprites/*.asm,
                                          #   index.asm, contact_sheet.png, table
python3 tools/svg_sprites.py roundtrip   # import->export->import, must be 0 mismatches
python3 tools/svg_sprites.py export G.grid [--ink #RRGGBB --caption NAME] --out f.html
                                          # grid -> canvas artboard for user review
```

Draft frames/tiles not yet on the canvas: `tools/gen_missing_frames.py` builds
them deterministically from existing canvas frames and writes the canvas-format
fragment `assets/gfx/source/draft3_frames.html` (+ `sprites/draft3_sheet.png`,
`sprites/preview/*.gif`, `preview/room_mock.png`). `import` also reads every
file in `svg_sprites.DRAFT_SHEETS`, appending draft frames after each
character's canvas frames (indices stay stable); once pasted on the canvas the
identical draft copy is skipped, a differing one is fatal. Per-frame policy
tables in `svg_sprites.py`: `ANCHOR_X` (declared §5.3 anchors), `REPAD`
(shift art inside the box), `DATA_ONLY_MASK_ROWS` (ghost dither exception),
`MOTION_FRAMES`/`SYMMETRIC_FRAMES` (→ `<char>_flags`), `TILE_SECTIONS` +
`TILE_ATTR` (`<h2>FX TILES</h2>` / `<h2>BG TILES</h2>` 8×8 artboards →
`tiles_fx.asm` / `tiles_bg.asm`). Every sprite's anchor is validated against
prototype.md §5.3 (ax%4, 0..8, ax_L 0..16).

The SVG convention the importer requires (one black rect, one fill path of
`Mx yhNv1h-Nz` runs, one known ink, `NAME · W×H` caption) is specified in
`.claude/agents/graphics-artist.md`; the importer rejects anything else.

## gfx_convert.py (the only packer)

- `--mode sprite --layout native` — W ∈ 8/16/24/32/40, W/8 `[mask,data]`
  columns, no pad, 3-state grid (`#` ink, `+` opaque paper, `.` transparent),
  `--anchor-x/-y`, `--note`, `--date`, `--src-path`. Emits `_len/_w/_h/_cols
  /_ax/_ay` EQUs. This is what svg_sprites drives.
- `--mode sprite` (legacy, default) — 16×H (+ transparent pad column) or 32×H,
  2-state grid or image input (image path = concept reduction only). Output
  must stay byte-identical; other assets and goldens depend on it.
- `--mode tile` — `=== name ink:c paper:c [bright]` + 8 rows per tile → 8 bytes
  + 1 attr per tile (e.g. `bg_tiles.grid`, `sprites/grid/tiles_ladder.grid`).

Bytes: MSB = leftmost pixel; mask bit 1 = transparent; composite
`screen = (screen AND mask) OR data`; descriptor PAPER must equal band paper
(black) — docs/design/sideview-renderer.md §1.4/§1.7.

## Validation (must pass before committing data)

- **Clash check**: every 8×8 cell resolves to exactly one attribute (≤2 colours).
  Reject and report any cell needing 3+ colours — the artist must redraw it.
- **Round-trip**: decode the emitted bytes (data AND mask) back; they must
  match the source grid. svg_sprites additionally re-parses the emitted DEFB
  text and compares against the canvas bitmap and derived mask.
- **Byte-identity** when touching gfx_convert: regenerate existing
  `assets/gfx/*.asm` with the old and new tool and diff — must be identical.

## Rules

- The committed artifact is the `.asm` byte table, not the PNG. Keep the source
  image under `assets/gfx/` for re-derivation, but code references the asm labels.
- Concept art from Ollama/ComfyUI is an *input* to redraw against — never a
  direct input to this converter expecting good output.
