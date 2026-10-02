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

## Game suites (`build/wazhack.sna`, build it first with `--sym`)

```sh
python3 tests/game.py                 # prototype.md §11.3 checklist (1-40) + 41-51 extras (50 = real tape load, 51 = select/2nd hero)
python3 tests/game.py 5 9 30          # only the listed checklist items
python3 tests/game.py --update-golden # refresh game_select / game_start hashes
python3 tests/budget.py          # per-tick T-state budget (exit 1 if > 2 frames)
GAME_PROFILE=1 python3 tests/budget.py   # + per-phase split of the worst tick
python3 tests/zx0_pool.py       # A5: builds ZX0_SOURCES=1 and =0 itself, pool banks 0/4/6 + FRT byte-identical at boot / each hero start / hero regen after a game; GEN_TRAP 0; prints cold-path T-states (--baseline DIR: also an old checkout)
python3 tests/zx0_roundtrip.py   # A4: every frame / kind block packs + unpacks bit-exact with the reference dzx0
FL=abc python3 tests/flicker.py  # E0 raster-beam flicker events per tick (scenarios a/b/c); MEASUREMENT, not a pass/fail gate; A/B the order with -DRENDER_FIRST=0
```

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
- Regression gate: `game.py` + `budget.py` green.
