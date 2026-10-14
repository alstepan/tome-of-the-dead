---
name: test
description: Run automated regression checks against a build by driving ZEsarUX over ZRCP — assert registers/memory at breakpoints and compare a hash of the screen frame against committed golden values. Use after any change that touches running behaviour, and to gate "done".
---

# test

Automated, reproducible verification — the regression mechanism the reviewer
relies on. Built on the `debug` skill's ZRCP plumbing.

## What a test is

A test is a script that:
1. launches ZEsarUX headless with ZRCP (see `debug` skill),
2. `smartload`s `build/wazhack.tap`,
3. drives to a known point (breakpoint or fixed frame count),
4. asserts:
   - **state**: `get-registers` / `read-memory` at named addresses
     (the stable test-observable addresses in `docs/memory-map.md`), and/or
   - **screen**: hash of `read-memory 16384 6912` vs a committed golden hash.
5. exits non-zero on any mismatch.

## Layout (create on first real test)

```
tools/test_harness.py     # ZRCP socket client + assert helpers
tests/<name>.py           # individual scenarios
tests/golden/<name>.hash  # committed golden screen hashes
```

## Golden-screen workflow

- Capture: read the 6912-byte frame, hash it (e.g. sha256), write to
  `tests/golden/<name>.hash`.
- Verify: re-read, re-hash, compare. A diff = regression → fail and report which
  scenario, with a short dump of the differing attribute cells if feasible.
- Regenerate a golden ONLY when the visual change is intended and reviewed; note
  why in the commit.

## State-assertion workflow

- Prefer asserting on named, stable addresses (player HP, RNG state, dungeon
  seed, render flags) over screen hashes where a value is what matters — screen
  hashes are brittle to cosmetic changes.

## Gating rule

A change is not "done" until `test` passes. A new golden hash without a stated,
reviewed reason is itself a failure.

## Game suites (`build/wazhack.sna` + `.sym`: build first with `tools/build.sh`)

```sh
python3 tests/game.py                 # prototype.md §11.3 checklist (1-40) + 41-51 extras (50 = real tape load, 51 = select/2nd hero)
python3 tests/game.py 5 9 30          # only the listed checklist items
python3 tests/game.py --update-golden # refresh game_select / game_start hashes
python3 tests/budget.py          # per-tick T-state budget (exit 1 if > 2 frames)
GAME_PROFILE=1 python3 tests/budget.py   # + per-phase split of the worst tick
python3 tests/zx0_pool.py       # pool banks 0/4/6 + FRT + SEL_FRT_SAVE + allocator bit-exact vs a Python reference generator over the RAW frame data (B3B-12; the raw -DZX0_SOURCES=0 build is retired) at boot / each hero start / hero regen after a game / regen over a poked STALE GEN_ZBLK + garbage GEN_SCRATCH; GEN_TRAP 0; prints cold-path T-states (--baseline DIR: an old checkout against the same reference)
python3 tests/sound.py          # SND-2 sound slot via the mailbox (SND1-SND9), frame-exact: ISR-stepped (breakpoints isr / isr.done), chip R0..R12 == tools/wzm_ref.py oracle (menu Lament through its loop, MUS_REQ / SND_MODE edges, real pause_run freeze + resume, MUS_SHOT stinger / final cue, music off <= 0.5k T), slot layout from the .sym, per-song ISR cost <= 6.5k T (reports worst single / adjacent pair); needs the DEBUG_KIT=0 build
python3 tests/world.py [W16 ...] # 3B world suite; W16 = level change (generated D1, descend D1->D8, win), W9R = door opened in the bank-3 monster phase
python3 tests/gfx_integrity.py   # every runtime graphics table (tile glyphs / attrs / flags, ORN, FONT6 planes, vdata, menu art, bank-7 tilesets, bank-0 text, sprite pool + FRT) == its assembled source, at the menu and D1..D8 entry + play; playfield == ROOM_MAP in source glyphs (fix/3d-artefacts)
python3 tests/zx0_roundtrip.py   # A4: every frame / kind block packs + unpacks bit-exact with the reference dzx0
python3 tests/drip.py           # D3-8b decorative drip: sources == model, never over a body / FX, ROOM_MAP + RNG untouched, cover / land, hide, cost <= 4k T
python3 tests/marks.py          # D3-8d status cues: overhead marks per status (hero + monsters, frame A/B), clear / death / room exit / covered / drip, V1 pose hold, V3 sleep flash, budget "mkmix" (<= 2 ops / tick) + "lcastf"
FL=abc python3 tests/flicker.py  # E0 raster-beam flicker events per tick (scenarios a/b/c); MEASUREMENT, not a pass/fail gate; A/B the order with -DRENDER_FIRST=0
```

- **Controls (C3-8a)**: every suite boots through the C3-6 menu (`Proto.boot` ->
  `menu_start`: `2` toggles HERO, `1` starts) and plays the default KEYTAB
  (Q/A/O/P, SPACE = FIRE). `Proto.hold/turn` keep the scenario aliases
  L/H/K/J = P/O/Q/A and `WAIT` = `.`; `turn()` adds a 0-turn tap when the key
  opposes the facing, `C` = FIRE on the melee icon, `G` = select the potion
  slot + FIRE. The `legacy_input` flag / `GAME_LEGACY_INPUT` switch are gone.
- **Tick-exact**: `tests/game_lib.py` keeps ZEsarUX in cpu-step mode with
  breakpoints on the test-probe labels (`wait_tick`, `select_tick`) and advances
  one 25 Hz tick per `run`, so scenarios are deterministic (no sleeps, no racing
  the renderer). Frames sampled "mid-turn" are read with the tick's render
  complete.
- Addresses and frame ids come from `build/wazhack.sym`; the entity layout is in
  `docs/memory-map.md` (PROTO).
- **No wall-clock anywhere.** `Proto.load()` never leaves cpu-step mode
  (smartload in step mode is synchronous) and verifies the reload: all 128K
  RAM == the .sna, PC = `boot`, `$C000` bank as saved — else it raises. The
  old exit-cpu-step / sleep / enter-cpu-step reload raced the emulator thread
  under host load (reloads silently not taking → scenarios starting from the
  previous one's state). `tick()` checks every `run` returned on a probe PC;
  anything else is logged `[ANOMALY]`, re-run, and fails after 3 in a row.
- `build/wazhack.sna` is copied to a private temp file at startup (sha256
  printed) so a concurrent assemble can't feed a torn file; `.sna` entry must
  equal `.sym` `boot` or the suite refuses to run.
- ZEsarUX runs `--emulatorspeed 1000 --vo null --ao null` for these suites
  (`GAME_EMU_ARGS=""` to watch in the window). Per-command timeout 30 s
  (`GAME_CMD_TIMEOUT`): a stuck `run` fails in seconds.
- Output is flushed per line; `[time] load #n` lines give per-scenario wall
  time. Full run ≈ 70 s idle, ≈ 2 min with 8 busy cores; the §8.2
  walkthrough is played twice (determinism #38).
- `budget.py` gates the "mix" scenario (every tick <= 2 frames) and
  reports the review-A1 "heavy" mix (hero + 2 skeletons + goblin + ghost,
  ~109% today) without gating on it.
- #50 loads a private copy of `build/wazhack.tap` through ZEsarUX's 128K Tape
  Loader autoload (the only test of the real `start` path; the .sna enters at
  `boot`): GS_SELECT, select golden, GEN_OVERFLOW 0, banks 1/3 == .sna, then a
  game start golden. It free-runs briefly (polls GAME_STATE, 60 s cap).
- Regression gate: `game.py` + `world.py` + `budget.py` + `zx0_pool.py` green.
- **D3-7: build the suites' snapshot with `tools/build.sh -DDEBUG_KIT=0`.**
  The default build carries the designer's debug start kit (`DEBUG_KIT` 1,
  game.md §1.4); `tests/game_lib.py` refuses such a `.sna` (`.sym`
  `KIT_DEBUG` = 1; `GAME_ALLOW_DEBUG_KIT=1` overrides for kit scenarios), and
  `zx0_pool.py` builds its private copy with `DEBUG_KIT=0`.
- **B3B-12 start mode:** new games start on a generated D1 by default.
  `game_lib.Proto.load()` pokes `proto_start = 1` after every load (and #50
  after the tape boot), so every PROTO-room scenario keeps rooms A-D; set
  `p.proto_start = 0` for a generated start (W16 also pokes `seed_fixed` /
  `seed_value` for a reproducible master seed).
