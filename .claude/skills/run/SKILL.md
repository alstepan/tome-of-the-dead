---
name: run
description: Launch the built tape in Fuse for macOS to see the game running interactively. Use for visual/manual confirmation. For automated assertions or screenshots use the debug/test skills (ZEsarUX) instead — Fuse on macOS is GUI-only.
---

# run

Run the current build in **Fuse for macOS** (the primary runtime emulator).

## Prerequisites

- A fresh `build/tome-of-the-dead.tap` (run the `build` skill first).

## Command

```sh
open "/Applications/Fuse for macOS/Fuse.app" build/tome-of-the-dead.tap
```

Controls (128K model; keys 1/2/3 pick a hero, H/L walk+attack, K/J climb, G quaff,
SPACE wait, ENTER on the end screens).
Load it from the **128 BASIC / Tape Loader**: in 48 BASIC (or after `USR 0`)
`$7FFD` paging is locked and `start` stops with "LOAD FROM 128 BASIC"
(`check_paging`). +2A/+3 are unsupported (different paging); use a 128K/+2.

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
