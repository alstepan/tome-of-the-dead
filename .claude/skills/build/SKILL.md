---
name: build
description: Assemble the Z80 source with sjasmplus into build/wazhack.tap (+ .sld debug info). Use whenever code or data changed and you need a fresh tape/snapshot, before running or testing.
---

# build

Assemble the project for the ZX Spectrum 128K.

## Command

```sh
python3 tools/zx0_sources.py && \
sjasmplus src/main.asm \
  --fullpath \
  --lst=build/wazhack.lst \
  --sld=build/wazhack.sld \
  --sym=build/wazhack.sym \
  -i src
```

- `tools/zx0_sources.py` (A5) packs the generator's sprite frames into ZX0
  blocks → `build/zx0/sprites_zx0.asm`, which `main.asm` includes as the
  bank-1/3 sprite sources (default `ZX0_SOURCES=1`). It needs
  `tools/bin/zx0` — if missing it stops with "run tools/setup_zx0.sh" (one-time,
  needs network for the pinned clone; the build itself never does). Output is
  deterministic and rewritten only when it changes. A/B against the raw
  sources: add `-DZX0_SOURCES=0` to sjasmplus (then the packer is not needed);
  `tests/zx0_pool.py` builds both and proves the pre-shift pool identical.
- `src/main.asm` is the single entry the assembler walks (it `INCLUDE`s the rest).
- Emits `build/wazhack.tap` (BASIC loader + one CODE block = bank-5 low-RAM
  cold code + bank-2 image, then two headerless blocks: bank 1 sources, bank 3
  source tail + cold code) and `build/wazhack.sna` (128K, entry `boot`).
- `--sym` is required: `tests/game*.py` and `tests/budget.py` read every address /
  frame id from it.
- `--sld` emits Source Level Debug data consumed by the `debug` skill / DeZog.
- `--lst` listing is handy for checking byte/cycle layout and label addresses.
- The assembler prints six `DISPLAY` lines (sprite-source size, ZX0 packed
  vs raw + freed bytes (ZX0 builds only), bank-3 cold
  code + room to the AY reserve, low-RAM cold code + spare after the A5/A6
  reserves, frame count + pre-shift pool need vs 48 KB, bank-2 image end +
  headroom) — check them; the pool / image /
  table limits are ASSERTs, so an overflow fails the build.
- Sprite art comes from `assets/gfx/sprites/index.asm` (packed by the tool
  above in the default build; a changed or added frame `.asm` is picked up on
  the next build); frames/tiles that are
  missing or have an illegal anchor fall back to stand-ins automatically
  (`src/data.asm` FRM/ROLE/TSRC tables) — no code change needed when art
  lands.

## Success criteria

- Exit code 0, no errors.
- `build/wazhack.tap` exists and is newer than the sources.
- Review warnings — unexpected ones (e.g. overlapping ORG, undefined label
  defaulting to 0) are treated as failures here.

## On failure

- Read the sjasmplus error: it gives file:line. Fix at the source, do not paper
  over with `--` flags.
- If a label is "not defined", check the include order in `src/main.asm`.

## Notes

- Target device is `DEVICE ZXSPECTRUM128` — do not switch to 48K.
- Keep the build deterministic: no timestamps baked into output.
