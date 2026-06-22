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
