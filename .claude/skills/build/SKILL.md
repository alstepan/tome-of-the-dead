---
name: build
description: Assemble the Z80 source with sjasmplus into build/wazhack.tap (+ .sld debug info). Use whenever code or data changed and you need a fresh tape/snapshot, before running or testing.
---

# build

Assemble the project for the ZX Spectrum 128K.

## Command

```sh
tools/build.sh                       # pack sprites + assemble into build/
tools/build.sh -DSEED_FIXED=1        # extra args -> sjasmplus (B3B-12 run flags below)
tools/build.sh -o DIR [-D...]        # artefacts into DIR/build/ (tests use this)
```

`tools/build.sh` (A6) is the ONLY build entry point — skills, tests and humans
all use it, so a build can never assemble stale packed art. It runs:

1. `tools/zx0_sources.py` — packs the generator's sprite frames into ZX0
   blocks → `build/zx0/sprites_zx0.asm` of the checkout, which `main.asm`
   includes as the bank-1/3 sprite sources. Needs
   `tools/bin/zx0`: if missing it stops with "run tools/setup_zx0.sh"
   (one-time, needs network for the pinned clone; the build itself never
   does). Deterministic; rewritten only when it changes. Strict input
   parsing: a frame `.asm` line that is not `DEFB $xx,...` (or a sub-label /
   comment) fails the build.
2. `sjasmplus src/main.asm --fullpath --lst=build/wazhack.lst
   --sld=build/wazhack.sld --sym=build/wazhack.sym -i src [args]`, run in the
   output dir. Exit 1 on any error **or warning**; prints the `DISPLAY`
   lines (full log: `build/sjasmplus.log`). 3E-T1: run TWICE — pass 1
   (`-DOVL_PASS=1`, log `build/ovl/pass1.log`) writes the raw overlay images
   `build/ovl/*.bin`, `tools/bin/zx0` packs each, pass 2 (the real build)
   INCBINs them (`-i build/ovl`); a raw image that differs between the passes
   fails the build (`docs/memory-map.md` "Overlays").

`tests/zx0_pool.py` builds with it and proves the pre-shift pool bit-exact to
a Python reference made from the raw frame data. B3B-12 retired the raw-sources
build (`-DZX0_SOURCES=0` now stops with an assembler ERROR).

Run flags (B3B-12, `src/lowram.asm`; bytes in the cold block, tests poke the
labels `proto_start` / `seed_fixed` / `seed_value` instead of rebuilding):
`proto_start` != 0 starts new games in the PROTO rooms A-D — tests only
(D3-11: the rooms are the test fixture `src/proto_fix.asm` -> `build/ovl/proto.bin`,
poked by `tests/game_lib.py` at `proto_hook`; `-DPROTO_START=1` is an assembler
ERROR); `-DSEED_FIXED=1 [-DSEED_VALUE=n]` fixed master seed (default:
`SYS_FRAMES` when the hero is chosen).
`-DANIM_TRACE_ON=1` builds only with `-DDEBUG_KIT=0` (D3-11 review: the kit + trace
combination is 59 B over bank 2 and fails `seq_bytes_end <= seq_rows`).
`-DDEBUG_KIT=0` (D3-7): no debug start kit — the build the test suites and
goldens need (default 1 = the designer's debug kit, never in a release tape).
- `src/main.asm` is the single entry the assembler walks (it `INCLUDE`s the rest).
- Emits `build/wazhack.tap` (BASIC loader + the loading-picture SCREEN$ block (6,912 B CODE @ $4000,
  tape-only, see memory-map "Tape") + one CODE block = bank-5 low-RAM
  cold code + bank-2 image, then two headerless blocks: bank 1 sources, bank 3
  source tail + cold code) and `build/wazhack.sna` (128K, entry `boot`).
- `--sym` is required: `tests/game*.py` and `tests/budget.py` read every address /
  frame id from it.
- `--sld` emits Source Level Debug data consumed by the `debug` skill / DeZog.
- `--lst` listing is handy for checking byte/cycle layout and label addresses.
- The assembler prints six `DISPLAY` lines (sprite-source size, ZX0 packed
  vs raw + freed bytes (ZX0 builds only), bank-3 cold
  code + room to the AY reserve, low-RAM cold block (code + frame
  descriptors) + spare after the `FRT_MAX` descriptor growth reserve, frame
  count + pre-shift pool need vs 48 KB, bank-2 image end + room to `FRT` +
  free runtime RAM `$B200..$B7FF`) — check them; the pool / image /
  table limits are ASSERTs, so an overflow fails the build.
- Sprite art comes from `assets/gfx/sprites/index.asm` (packed by the tool
  above in the default build; a changed or added frame `.asm` is picked up on
  the next build); frames/tiles that are
  missing or have an illegal anchor fall back to stand-ins automatically
  (`src/frames.asm` FRM list, `src/data.asm` ROLE, `src/lowram.asm` TSRC
  tables) — no code change needed when art lands.
- **40-px override (ANIM-IMPORT2):** every name INCLUDEd in
  `assets/gfx/sprites40/index40.asm` is read from `assets/gfx/sprites40/<name>.asm`
  instead (`tools/zx0_pack.py` `sprite_asm`), so editing or re-importing
  (`tools/svg_sprites.py`, which writes `assets/gfx/sprites/`) a frame listed
  there changes NOTHING in the build — edit the `sprites40/` copy. index40 is
  not an on/off switch (six frames exist only at 40 px); the 48-px set comes
  back only from the tag `archive/48px-sprites` (`docs/conventions.md`
  "Sprite sources").

## Success criteria

- `tools/build.sh` exit 0 (it already fails on any error or warning).
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
