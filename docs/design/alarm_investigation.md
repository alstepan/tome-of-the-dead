# ALARM trap investigation (user playtest: "monsters appear one per room enter/exit, no way to escape without a fight")

Date 2026-11-09. Investigation only, no fix applied (the one prototype edit below was reverted).
Build: main `313ff60`, release `-DDEBUG_KIT=0`. Harness: ZEsarUX / ZRCP port 10790, `tests/game_lib.py` + `tests/spawn.py`
helpers (`Lair`, `hero_at`, `Lines`, `heal`), probe `tests/_alarm_probe.py` (untracked, scenario scripts `s2/s3/s4` in the
agent scratchpad; the numbers below are reproducible with seed `0x7A01`, D5, rooms 3-4-5 in a row, plate poked into
`TRAP_LIST` as `tests/spawn.py` alarm() does, `LF_UNIQUE` clear, `heal()` each turn).

## Verdict

There is **no bug in the wave itself**: one fire = exactly one `1 + (rnd & 1)` wave, `LP_RESPAWNS` +1 per fire (cap 6), nothing is
spawned by a room entry or exit, the trickle does not react to rooms. What the player feels is the **interplay of four rules that
each match the spec** (the classification below), i.e. a design problem, not a code defect:

| # | Cause | Evidence | Rule | Verdict |
|---|---|---|---|---|
| (2) | The plate **re-arms and re-fires on every step off / on** | s4: hero stepping on / off the plate: wave at turns 1, 7, 22, 26, 35 (`RESP` 1,2,3,4,5; 5 rings in 35 turns, 4 + 1 bodies live at once, room cap 4). s2: turning back over the plate near the door = a second wave at once (turn 31, 2 bodies). | game.md §1.5 "re-arms (stays)", TRAP2 cap `RESPAWN_MAX` 6 | **expected, main cause**: the plate is a 1-col strip in the corridor, so every pass through the trap room (and every retreat across it) rings again; worst case 6 waves = up to 12 bodies |
| (1) | Awake wave bodies **follow through every exit** and keep following | s3 (goblins): body 7 cols behind, hero leaves right -> turn 34 the goblin is in room 5 `fle5` (PENDING, on the arrival box); hero goes back (turn 40) -> it is in room 4 again `fled`; again at turns 46, 51. Each exit: the body is a candidate (gap 0 for a PENDING body on the arrival box, ROOM-MEM F), so it follows. Archer (ranged, keeps distance) never followed (s3 first run, s2). | prototype §3.7 follow rule (gap <= `FOLLOW_GAP` 4, `FOLLOW_MAX` 2 per exit, §9.3 cap), game.md §9.5 "may follow like any monster" | **expected, but the cause of "no escape"**: a walker at hero speed never drops out of the 4-col gap, and a PENDING follower rides along on every transition |
| door camp | The wave arrives **at the room's doors/exits, the left door first**, on the route the hero is taking | s1/s2: archer on the left door x=1 blocked the only/leftward exit for 25 turns, hero fought at x=5. `sp_door` takes RDX_L first, else RDX_R, else the ladder end. Two bodies stack on the same spot and arrive one at a time (s2: second body PENDING 14 turns, until the first left x=1) = "one per ..." | game.md §1.5 / §9.5 "at the room's doors/exits" | **expected**, and in a dead-end room (one exit) the wave is on the only way out |
| (3) | Trickle shares `LP_RESPAWNS` | s3: `RESP` 1 -> 2 at level turn 49 with no ring (trickle period 48, appended to a record: the body appears on the next entry of *that* room) | game.md §9.5 | expected; independent of the alarm. It makes the cap of 6 waves smaller, and a trickle body does "appear on room entry", which may add to the impression, but it is ~1 per 128 turns |
| (4) | Spawn-on-entry treats wave bodies differently | none: the banked wave body keeps `F_RESPAWN` (record `('k12','f80',12)`), comes back at its stored cell, `LP_RESPAWNS` unchanged on bank / re-entry | §9.4.2 / ROOM-MEM | no difference, no extra body per entry |
| (5) | Real bug (a wave per entry, cap not counted) | none found. `LP_RESPAWNS` +1 per wave, `cp RESPAWN_MAX` gate present (`trap7.asm:278`); boss-dead and cap give `.bell` | - | none |

Unfixed leftovers that are not the complaint: a non-following wave body is **banked** (`lp_bank`, wave is not `RCD_SUMMONED`),
so it waits in the trap room's record and is back at its cell on every re-entry (first run: archer banked, re-spawned at x=7
on return). It is one body, not a new one per entry.

## Code map (file:line)

- `src/trap7.asm:48` `trap_turn`, `:80` `.fire`: trigger when the plate col is under the body now and **not** under it before
  the action (`TRP_PRE`); standing / turning / waiting on it never re-fires, walking off and on does. The room entry
  (`TRW_ENTRY`) never fires. `set TRF_KNOWN` only; no "spent" state (TRAP2 retired `TRF_SPENT`, `item_defs.asm` = 0).
- `src/trap7.asm:256` `tr_eff` ALARM arm (`:272..:292`): depth/boss check, `cp RESPAWN_MAX` gate on `LP_RESPAWNS` (`:278`), `inc`,
  `SPQ_K = SPQ_WAVE`, `SPQ_N = 1 + rnd & 1`, red border, line.
- `src/spawn6.asm:248` `sp_run` (one body per loop, `sp_scan` / `sp_fit` = the §9.3 cap, a body that does not fit ends the run),
  `:508` `sp_door` (left door x=1, else right door, else up / down exit col; every body the same spot, PENDING | WALKIN),
  `:557` `sp_fin` (E_RCD = `SQF_SUMM` bit only; wave: `SQF_RESP` only).
- `src/combat_defs.asm:168` `SPQ_WAVE EQU SQF_RESP` (summon bit **not** set: the wave is banked like anyone).
- `src/bank7.asm:1116` `follow_select` (candidate filter: not the boss, not HOLD / FEAR, standing, same storey, gap <= `FOLLOW_GAP`;
  `E_FLAGS` mask `EF_ACTIVE | EF_DYING` so PENDING bodies qualify, overlap = gap 0), `src/bank3.asm:161` `follow_admit`
  (`FOLLOW_MAX` 2, §9.3 cap), `src/defs.asm:1002` `FOLLOW_GAP` 4 / `FOLLOW_MAX` 2.
- `src/lpop3.asm:241` `lp_bank` (`:265` summon-made bodies are freed, others banked with `EF_RESPAWN`).
- `src/trickle6.asm:32` `trk_run` (shares `LP_RESPAWNS`).

## Fix options (regions: bank 7 cold 1 B free, R6 1, bank 3 7, bank 0 14, bank 2 9 on the release build)

**A. Wave bodies are summon-made (`SPQ_WAVE EQU SQF_RESP | SQF_SUMM`).  0 B, 0 T.**  Prototyped and run (then reverted): the
left-behind archer is not in the trap room's record after the hero leaves and is not there on return; `lp_bank` frees it
(§9.4.2 "discarded"). The room is clean on re-entry, so leaving the room is an escape unless the body is within the follow gap.
Side effects: wave bodies count in `sp_scan` `SP_NS` (Bone Caller `BC_LIVE`, Pharaoh `PH_LIVE`: a Bone Caller in the same room
summons a little less while a wave body lives); `tests/spawn.py` A2 asserts `not e["POT"] & SUMM`: flip it. Does **not** touch
the re-fire (2) or the follow ping-pong (1) of an adjacent chaser.

**B. Wave bodies never follow.  ~+6 B bank 7 (`follow_select`: `bit RCD_SUMMONED_BIT,(ix+E_RCD) / jr nz,.cn`, needs A so the
wave is summon-made) or `bit EF_RESPAWN_BIT,(ix+E_FLAGS) / jr nz,.cn`, +6 B but also stops trickle bodies (changes §9.5
"may follow") and Bone Caller / Rabbit offspring following.  ~+60 T per candidate slot, cold (room exit only).**  Bank 7 has 1 B
free: 5 B of cold reclaim needed (e.g. trap7 `.bell` / `.gas` tails, which already share `hg_line`, are the nearest cold
neighbours; no reclaim spike done here). With A + B an alarm chaser can be shaken by any exit.

**C. One wave per plate (disarm after the first ring).  ~+6 B bank 7, ~+30 T per ALARM fire, cold:** in `tr_eff` after the
boss check and before `ld hl, LP_RESPAWNS` (HL = the entry there): `bit 6,(hl) / jr nz,.bell / set 6,(hl)`. TR_B0 bit 6 is a spare
bit; every reader masks (`TRF_ROOM_MASK | TRF_S1 | TRF_SPENT`, trap6.asm:59, bank7.asm:219, fx6.asm:730, bank3.asm:679
`| TRF_KNOWN`, items_ovl.asm:635) so the bit is inert for them (a new `TRF_RUNG EQU %01000000` in `item_defs.asm`, the
`TRAP_LIST` model in tools / tests must keep bytes 0 at generation). The plate stays visible; a second step prints the existing
"A BELL RINGS. NOTHING COMES" line. Contradicts §1.5 "re-arms (stays)" for ALARM only (that row was written for the user's
free-escape TELEPORT / DART farming reasons; the TRAP2 note already limits ALARM through the cap): game.md must be updated.
Fixes (2) fully. A cooldown ("one wave per N turns") needs a turn stamp: +~15 B, not recommended.

**D. Wave at the door farthest from the hero (not left-first).  ~+12 B R6 `sp_door` (R6 free 1), ~+60 T once per wave.**  Removes
the door-camp on the hero's route. Needs 11 B R6 reclaim: expensive for a partial effect; not recommended now.

## Recommendation

**A + C** (0 + ~6 B): the wave becomes a one-time, room-local ambush per plate (fixes the re-fire farming, "monsters per
crossing") and leaving the room sheds anything that is not on the hero's heels; fund C's 5 B from bank-7 cold reclaim.
Add **B** (+6 B) only if playtesting still shows the follow ping-pong of the first-wave bodies to be unfair (it is the
unmodified core follow rule, so ordinary monsters keep it; the manager should confirm that "alarm bodies never follow" is
wanted before spending bytes). If no bytes can be found at all, **A alone (0 B)** is shippable and already removes the
"every entry the wave is waiting at the door" effect; (2) then stays bounded by `RESPAWN_MAX` 6.
Open question for the user: is a re-arming bell (up to 6 waves) intended, or "ONE wave"? The doc text (§1.5) says both
"one wave" (per fire) and "re-arms"; the playtest report reads the second as the bug.
