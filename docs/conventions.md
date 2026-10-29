# Z80 coding conventions

> Authoritative rules for all hand-written Z80 in this repo. Reviewers enforce
> these. Update here first, then the code.

## Calling conventions

- Arguments in registers, documented per routine in a header comment.
- Document **clobbers** on every routine (`; Clobbers: A, BC, HL`).
- Preserve `IX`/`IY` across routines unless a routine documents otherwise.
- Return small results in `A` / carry flag; pointers in `HL`; pairs in `DE`/`BC`.
- `HL` is the workhorse pointer/accumulator pair — prefer it for hot paths.

## Performance rules

- Prefer `inc`/`dec`/`add hl,` arithmetic over `ld`+arith where possible.
- Unroll only with a measured reason; note the cycle saving in a comment.
- `ldir`/`lddr` for block copy; `out (c)`/`in` patterns for paging.
- Self-modifying code is allowed in hot paths but MUST be flagged
  `; SMC:` with what gets patched and where, and must not live in ROM-paged space.
- Annotate hot routines with their T-state cost in the header.

## Memory & data

- No magic addresses. Define them as constants in an include and reference by name.
- Tables that the renderer/engine index into get a comment with the entry stride.
- Keep `docs/memory-map.md` authoritative; never allocate a fixed address without
  recording it there in the same change.

## Banking (128K)

- Paging port is `$7FFD` (write-only — keep a shadow byte in RAM, never read-modify
  the port). Record the current bank shadow location in `docs/memory-map.md`.
- Write order is always **shadow first, then `OUT`**, through `page_bank` /
  `set_screen` only: the IM 2 ISR pages bank 3 for the AY player and restores
  the port from the shadow (protocol under "Interrupts").
- Document which bank any far data lives in, and the bank-switch cost around it.
- Hot (per-tick) code lives in bank 2. Cold code that pages `$C000` lives in
  bank 5 low RAM (`src/lowram.asm`); cold code that needs no other `$C000`
  bank lives in bank 3 (`src/bank3.asm`) and is entered only through `far3`;
  the 3C UI (menus / pause / end screens) lives in bank 1 (`src/ui1.asm`,
  `ui1_code` after `vdata`) and is entered only through `far1`. Both are
  2-byte bank loads in front of **`farb`** (bank 2, `gfx.asm`): HL = target,
  A = arg (passed in), C = bank (`farb` only); DE / IX pass in, BC does not;
  the target's BC / DE / HL / IX pass out; clobbers A, F; restores the
  caller's bank (bits 0-2 of the saved shadow, screen bit kept). Far calls
  nest (a bank-1 target may `far3`, and vice versa). Paged-bank code (bank 1
  or 3) never pages `$C000` itself — it calls helpers that re-page it
  (`blit_keep`). See `docs/memory-map.md` "Cold code placement" / "3C
  contracts".
- **R6 region (2026-10-21).** Permanent code + data + packed overlay streams
  at the top of bank 6, `R6_ADDR..$FFFF` (`R6_LEN` is the cap, ASSERTed;
  `src/r6.asm`, main.asm "R6 REGION"; bank 6 below it is sprite pool). Code
  is entered only through **`far6`** (`ld c, BANK_R6` / `jr farb`, +12 T vs
  far3; nests from any bank). Same rules as bank 7: far6 loses A and F
  (results in BC / DE / HL / IX or memory); while it runs bank 6 is at
  `$C000`, so it never calls bank-3 / bank-1 / bank-7 code or reads their
  data directly (far3 / far1 / far7 only; e.g. `hla` is bank 3 — inline
  it); no SMC; it never pages `$C000` itself. Overlay streams there run
  through `ovl_run` with C = `BANK_R6`. New 3E / 3F code and overlay streams
  go here (memory-map "R6 region"); 3F sprite sources go to the **SRC6**
  region just below R6 (`SRC6_KINDS` in `tools/zx0_sources.py`; memory-map
  "SRC6 region").
- **Bank-7 cold code (D3-S2).** Per-turn / per-event logic that needs no
  other `$C000` bank lives in bank 7 `$E000..$F7FF` (`src/bank7.asm`, the
  space of the dropped bitmap shadow), entered only through **`far7`**
  (`ld c, BANK_COLD7` → `farb`; nests from bank 3 / bank 1 too). Rules:
  never per-tick render / present / ISR code (bank 7 is contended; a far
  call costs ~0.25k T); far7 loses A and F, so results come back in L or
  memory; every callee must return with bank 7 paged —
  helpers that restore the caller's bank, far calls, or the ones that leave
  bank 7 paged (`erase_rect`, `shadow_rect`, `room_shadow`, `present_full`,
  `level_enter`); a helper that leaves another bank paged (`blit_sprite`,
  `render`, the generator, `page_bank`) is wrapped in `ld c, BANK_COLD7` /
  `call farb`. Paging bank 7 in never changes the displayed screen (that is
  `$7FFD` bit 3, kept by `page_bank`). No SMC and no data in bank 7 code:
  `tests/gfx_integrity.py` asserts `B7_CODE..B7_LIMIT` == the .sna. Test
  probes never go there (a PC breakpoint at `$E000+` also fires in bank-3 /
  bank-1 code at the same address): keep a bank-2 stub as the probe
  (`read_turn_input`, `pause_hook`).
  **Exception (D3-8d, the status-mark ops):** `mk_op` / `mk_forget` /
  `mk_sweep` (`src/mark7.asm`) draw / erase screen cells from bank 7. They
  are events (apply, clear, a cell step, the 8-tick toggle), ≤ 2 ops a tick
  plus the forgets (one per drawn mark the render touched), entered by far7
  from the bank-2 pass, and only in a tick still in its first frame (the
  gate is tested once at `mark_tick`'s entry): the per-tick pass itself stays
  in bank 2. Do not extend this to other render code.
- **Boot block and overlays (3E-T1).** Boot-only code / data lives in the
  bank-6 boot block (`src/boot6.asm`, run by `boot` via `farb` before the pool
  is generated); nothing may read it after boot (the pool overwrites it).
  Transient code is an **overlay**: assembled at its load address, stored
  ZX0-packed in bank 1 (`main.asm` "OVERLAYS", two-pass `tools/build.sh`),
  run by `ovl_run` (HL = stream, C = bank, DE = load/entry; IX in, BC/DE/HL/IX
  out; caller's bank restored) in the `GEN_SCRATCH` window — only while no
  room map is live (boot, menu, level start before `level_show`). 3E-T2:
  the **page** also runs in `GEN_SCRATCH` while a room is live — `ROOM_MAP`
  saved to `PAGE_MAP_SAVE` and put back around it, `present_full` first (screen
  2 = the backup, copied back on close); the page may draw all 24 rows and
  page / far-call anything, must not read `ROOM_MAP`, and nothing renders /
  presents meanwhile (`page_run`). Contracts: `docs/memory-map.md` "Boot block" /
  "Overlays".
- **Helpers restore the caller's bank.** Every bank-2 / low-RAM helper that
  pages `$C000` and returns, and is reachable from paged-bank code (bank 3 or
  bank 1), saves `PORT_7FFD_SHADOW` before paging and ends with
  `restore_page` (bits 0-2 of the saved value) — never a hard-coded
  `page_bank BANK_x` (C3-0 audit: `copy_virt3` re-paged bank 3, now
  `copy_virt_keep`; the others — `msg_push(_end)`, `show_impact_msg`,
  `print6t`, `level_load_tiles`, `door_paint`, `blit_keep`, `far*` — already
  did). Helpers that leave another bank paged (`shadow_rect`, `erase_rect`,
  `blit_sprite`, `present`, `draw_room`, `present_full`, the generator) are
  forbidden from paged-bank code except as its tail jump (`ap_stamp` →
  `shadow_rect`, bank 7: `farb` re-pages; was `potion_pickup`). `tests/world.py` W18 calls `msg_push`,
  `copy_virt3` (pages bank 3) and a nested `far1` from a bank-1 target
  entered by `far1` with bank 0 paged and asserts bank 1 / bank 0 afterwards
  (it crashes with the old `copy_virt3`).
- History (B3B-R2 review), the rule as first written for bank 3: since R2 the monster phase runs in
  bank 3, so anything `try_step` can reach (today `mon_door` → `door_open` →
  `door_paint` → `shadow_rect`, which pages bank 7) saves `PORT_7FFD_SHADOW`
  before paging and `restore_page`s it before returning; otherwise the return
  lands in another bank's bytes. The same holds for any helper a far3 target
  calls. `tests/world.py` W9R runs a goblin opening a door through the real
  `resolve_monsters` and asserts bank 3 is paged afterwards (it crashes with
  the restore removed).

## World-state changes (render resync contract)

- The play loop renders FIRST in a tick, from the previous tick's `anim_tick`
  output (`SLOTREC` `R_VIS` / `R_FID` / `RLIST`). Every path that **rewrites the entity
  table** (new game; Stage 3B level change / stairs) must end with
  `vis_reset`, and every path that **changes `CUR_ROOM` with the slots kept**
  (room exit) with `vis_room_sync` (both `src/lowram.asm`, always mapped).
  Skipping it draws the previous world's slots for a tick (bugs B7 / B7b;
  `tests/game.py` #52 / #54). See `docs/memory-map.md` "Double buffer".

## Walk cycles (phase-locked shifts, `PHASE_SHIFT` default 1)

- A walker's walk phase and its px both step once per 4-px tween tick, so each
  walk-cycle slot is only ever drawn at one px parity; the pool stores that one
  shift (`src/frames.asm` WK4 / WK0) and `anim_entity .walkph` locks the drawn
  phase to the px parity (`PHASE_TRAP` counts disagreements; expect 0).
- Rules for every move cycle (write them with `MOVECYC2` / `MOVECYC4`,
  `src/data.asm`, which ASSERT them): **1 tick per entry, even length; even
  slots are drawn at shift 4 (flag WK4 or MOT), odd slots at shift 0 (WK0 /
  STA or MOT).**
- **Any walk frame also used at rest / attack / hurt / death / climb / jump
  must be MOT** (those are drawn cell-aligned, or at both parities for JUMP2):
  e.g. Skeleton / Goblin WALK1 are their REST frames — **unless it sits in an
  ODD slot** (drawn cell-aligned too): the 3F 2-frame walkers (3F-T13) write
  `MOVECYC2 walk2, walk1`, WALK1 = rest pose = `WK0` (one shift; MOT under
  `PHASE_SHIFT` 0), WALK2 = `WK4` — −576 B pool per 24×48 kind vs MOT + WK0.
  A non-climber whose move cycle has a WK4 even slot uses its idle cycle as
  KS_CLIMB (never the move cycle). A WK4 frame may appear in
  no other sequence, cycle or role (`tests/frames_phase.py`, static, no
  emulator). Climb and JUMP2 art must exist (the walk stand-ins are ASSERTed
  out under `PHASE_SHIFT`). `-DPHASE_SHIFT=0` = both shifts (escape hatch);
  `=2` = unlocked + trap (soak diagnostic).

## Style

- Labels: `snake_case`; local labels `.likeThis` under a parent.
- Constants: `UPPER_SNAKE`.
- One logical routine per block, with a banner header comment.
- Comments explain *why* and cost, not the opcode mnemonic.

## Interrupts (A8: IM 2)

Single source of truth for the setup: `docs/memory-map.md` "Interrupts (A8)".

- **IM 2**, installed by `boot` (`isr_install`, under boot's `DI`): 257-byte
  vector table `ISR_VEC_TABLE` (`I` = `$BB`, bank 2) of `ISR_VEC_BYTE`, ISR
  copied to `ISR_ADDR` `$BCBC`. The tape entry `start` runs before that under
  the ROM IM1 ISR (LD-BYTES ends with `EI`), with `IY = $5C3A`.
- **The ISR** (`isr`, `src/lowram.asm`, runs from bank 2): `SYS_FRAMES += 1`
  exactly as the ROM did (3 bytes; `wait_tick` paces on the low byte), then
  pages `BANK_AY` and calls `AY_PLAY` once per frame, then re-OUTs the shadow.
  It saves AF, BC, DE, HL, IX, IY (+ AF'..HL' with `ISR_SAVE_ALT=1`). No ROM
  chain by default: input is read straight from the ports (`scan_matrix`),
  nothing reads the ROM keyboard variables, so the ROM handler would only cost
  ~0.9k T/frame. `ISR_ROM_CHAIN=1` (assemble-only, untested at runtime: test #61's probe sets IY, invalid under ROM chain) ends the ISR with `jp $0038` instead (then
  `IY` must be `$5C3A` whenever interrupts are on — keep it there anyway: the
  engine never touches `IY`).
- **Paging protocol (race-free without `DI`).** Every `$7FFD` write in main
  code goes **shadow first, then `OUT`** (`page_bank`, `set_screen`; never a
  bare `OUT`, never "OUT then shadow"). The ISR **never writes the shadow**:
  it OUTs `(PORT_7FFD_SHADOW & ~7) | BANK_AY` (keeps screen bit 3 and ROM bit
  4), calls the player, then OUTs `PORT_7FFD_SHADOW` **as it is now**. An
  interrupt between a shadow write and its `OUT` therefore puts the new value
  on the port a few T early and the main code's `OUT` repeats it; an
  interrupt anywhere else restores exactly what was paged. The screen bit is
  never touched by the ISR (`tests/game.py` #61 checks port == shadow at every
  ISR exit across a 7 → 5 → 7 screen flip).
- **AY player slot contract** (`AY_PLAY` = `AY_RESERVE` `$EFA0`, bank 3, 4,192 B
  to `$FFFF` since MEM-SND (4 KB from `$F000` since D3-0, 7 KB from `$E400` before); `src/ay.asm`: since SND-2 the
  mailbox dispatcher `ay_play` + the WZM v0.3 player (`MODULE wzm`, buzzer, no
  echo) + the songs (`MODULE mus`)): called with interrupts off,
  bank 3 paged at `$C000`, any stack depth (it uses 8 B incl. the CALL since SND-5: `ay_play` → `ay_music` / `sfx_step` → the player's 4). The slot may clobber AF, BC, DE, HL, IX, IY
  (`ay_play` today: AF, BC, DE, HL, IX; no IY).
  Must not: write the shadow or `$7FFD`, `EI`, touch `$C000` data of other
  banks, use the alternate set unless `ISR_SAVE_ALT=1` (assemble-only, untested at runtime) (or main code never
  uses `EXX` / `EX AF,AF'` — true today), take more than ~6.5k T (budget.md
  §5: the tick keeps 13k T per 2 frames for it; measured worst ~5.2k, see
  `docs/memory-map.md` "Interrupts (A8)"). `ay_play` must keep `AY_CALLS` += 1
  per call (#61). Anything that writes an AY register outside the player
  (e.g. `ay_silence`, which keeps `wzm.pl_regs` R8-R10 in step) must follow
  with `wzm.pl_out_all`, or keep the mirror equal to the chip: the player
  writes R7 / R11 / R12 only when they differ from the mirror.
  Main code never touches the AY ports ($FFFD select / $BFFD data): the
  select+write pair is not atomic against the ISR — music and sound effects are
  requested through the mailbox (or, if ever unavoidable, DI around the pair).
- **Sound mailbox** (bank 2 `$BFEB..$BFF0`, `src/defs.asm`; semantics in
  `docs/memory-map.md` "State block"): main code writes only `SND_MODE`,
  `MUS_REQ` and `MUS_SHOT` — single-byte stores (or `set` / `res` on
  `SND_MODE`), never a 16-bit store across two of them; `MUS_REQ` is a level
  (the looping tune wanted now, 0 = silence; write it whenever it changes,
  never "consume" it), `MUS_SHOT` an edge (one-shot id; a final cue writes
  `MUS_REQ` 0 first, then `MUS_SHOT`). Only the ISR writes `MUS_STATE` /
  `MUS_CUR` and clears `MUS_SHOT`; main code only reads them. `SFX_REQ`
  (SND-5) is written only through `sfx_req` (`ld a, SFX_x : call sfx_req`,
  bank 2, keeps A / BC; priority rule + hold / SFX-bit gate inside); the ISR
  clears it. Boot initialises the block before `EI`; nothing else resets it
  (`SND_MODE` lives for the power-on).
- **No `DI` windows in runtime code** (they would stall the music). The only
  sites: `start` (tape entry; the ROM loader), `boot` (`DI` … `EI` around the
  SP reset, `isr_install` and the first shadow write — the ISR must not run
  before the shadow is valid), `check_paging.locked` (`DI` + `HALT`: the
  deliberate stop when paging is locked). The ISR itself runs with
  interrupts off (~0.6k T idle, up to ~5.5k T with a tune playing (SND-2), in the top border). New routines that need `DI`
  document the window and keep it as short as possible; SP tricks (stack
  blits) are out unless they run under `DI` with that cost accepted.
- **`IY` = `$5C3A`**: still set by `start` / `boot` and never changed — needed
  by the tape path (ROM IM1 ISR) and by `ISR_ROM_CHAIN=1`; the default IM 2
  ISR does not use it.

## Testing hook

- Anything worth asserting on (player HP, RNG state, dungeon seed, render flags)
  should live at a stable, named address so the `test` skill can read it via ZRCP.

## Test probe labels

- A label that exists only as a ZRCP breakpoint target for the tests (e.g.
  `tick_work`, `wait_tick`, `select_tick` in `src/main.asm`) is commented
  "test probe" at its definition and listed in `docs/memory-map.md`. Never place
  a probe on a `HALT`: ZEsarUX's `run` re-fires on the halted PC without progress.


## Message API (B3B-13)

- `msg_push` / `msg_push_end` (low RAM) clobber **AF, BC, DE, HL** (C is no longer preserved, unlike the old `log_push`); callers in any paged bank (bank 3, bank-1 UI code) get their bank back (restore_page; W18 checks it from bank 1).
- `tk_get` uses an SMC mode switch (`tk_get.sw`): never call the text printer from the ISR.
- D3-TX: the text block lives in bank 0 (`BANK_TEXT`, under the pool). Never read it in place —
  not even from bank-1 code: go through `msg_push`, `print6t` / `print6x`, or `tx_dec`
  (decodes a string into `TX_DEC`, bank 5) — they page `BANK_TEXT` and restore the caller's bank.
