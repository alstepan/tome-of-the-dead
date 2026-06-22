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
  -i src
```

- `src/main.asm` is the single entry the assembler walks (it `INCLUDE`s the rest).
- `SAVETAP` inside the source writes `build/wazhack.tap` (auto-running BASIC loader).
- `--sld` emits Source Level Debug data consumed by the `debug` skill / DeZog.
- `--lst` listing is handy for checking byte/cycle layout and label addresses.

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
