---
name: build
description: Assemble the Z80 source with sjasmplus into build/wazhack.tap (+ .sld debug info). Use whenever code or data changed and you need a fresh tape/snapshot, before running or testing.
---

# build

Assemble the project for the ZX Spectrum 128K.

## Command

```sh
sjasmplus src/main.asm \
  --fullpath \
  --lst=build/wazhack.lst \
  --sld=build/wazhack.sld \
  --sym=build/wazhack.sym \
  -i src
```

- `src/main.asm` is the single entry the assembler walks (it `INCLUDE`s the rest).
- Emits `build/wazhack.tap` (BASIC loader + CODE + two headerless sprite-bank
  blocks) and `build/wazhack.sna` (128K, entry `boot`).
- `--sym` is required: `tests/game*.py` and `tests/budget.py` read every address /
  frame id from it.
- `--sld` emits Source Level Debug data consumed by the `debug` skill / DeZog.
- `--lst` listing is handy for checking byte/cycle layout and label addresses.
- The assembler prints three `DISPLAY` lines (sprite-source size, frame count +
  pre-shift pool need vs 48 KB, image end) — check them; the pool / image /
  table limits are ASSERTs, so an overflow fails the build.
- Sprite art comes from `assets/gfx/sprites/index.asm`; frames/tiles that are
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
