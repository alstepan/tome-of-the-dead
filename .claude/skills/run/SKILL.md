---
name: run
description: Launch the built tape in Fuse for macOS to see the game running interactively. Use for visual/manual confirmation. For automated assertions or screenshots use the debug/test skills (ZEsarUX) instead — Fuse on macOS is GUI-only.
---

# run

Run the current build in **Fuse for macOS** (the primary runtime emulator).

## Prerequisites

- A fresh `build/wazhack.tap` (run the `build` skill first).

## Command

```sh
open -a "Fuse for macOS" build/wazhack.tap
```

Fuse on macOS is a Cocoa GUI app — it has no useful headless/CLI text mode, so:
- it's for **human-in-the-loop visual checks**, not automated verification;
- it auto-loads and auto-runs the tape (the loader does `RANDOMIZE USR`).

## Set the model (first run only)

In Fuse: Machine → Select → **Spectrum 128K**. Confirm the title screen shows
the 128K menu. This is a one-time per-machine setting Fuse remembers.

## When to use which emulator

- `run` (Fuse) → "does it look right when I drive it by hand?"
- `debug` / `test` (ZEsarUX + ZRCP) → "assert exact memory/registers/screen,
  set breakpoints, capture reproducible screenshots."
