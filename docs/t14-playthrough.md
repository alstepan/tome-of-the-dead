# T14 — end-to-end playthrough (tests/playthrough.py)

Branch `test/t14-playthrough` (from main 10d8c3d). Build under test: release, `tools/build.sh -o DIR -DDEBUG_KIT=0`
(`WZ_BUILD_DIR=DIR/build`). Test code only: **no game source changed**.

## Files

| File | Role |
|---|---|
| `tests/playthrough.py` | CLI, new game from the menu (`seed_fixed` / `seed_value`, `proto_start = 0`), per-run report (JSON), end-card PNG (`PT_PNG=dir`) |
| `tests/pt_plan.py` | `Player`: level planner (explore all rooms, items, lair boss, exit; D8: Archmage -> seal -> Sanctum -> Tome -> gate -> exit), stuck recovery, dead variant |
| `tests/pt_bot.py` | `Bot`: map / level readers, room-graph + in-room pathing (walk, ladder, narrow-pit jump), combat (abilities, spell choice vs resistances), bag page (READ / EQUIP), survival (potions, food, god pokes) |
| `tests/pt_mon.py` | `PT` (tick driver: tick_work / wait_tick bracketing) and `Mon` (the per-tick monitor) |

Run: `ZRCP_PORT=<port> python3 tests/playthrough.py [--hero W|M] [--seed 0x1234] [--mode win|dead] [--no-god]
[--boss-fallback N] [--boss-hp1] [--start-depth N]`. Never port 10000 (the CLI refuses it). One run = one emulator,
about 25-35 emulated-and-wall minutes (30-35 ticks/s with the emulator unthrottled); several can run in parallel on
separate ports. The run is deterministic for a given code + seed; an emulator that dies mid-run is replayed
(`[EMU-DIED]`).

## What is real, what is poked

Real (the game's own code paths, through the injected keyboard matrix only): menu start, every walk / climb / jump /
room exit and re-entry (room-mem), melee, Power Strike / Whirlwind, daggers / bow, all five Mage spells, XP and
level-ups, floor pickups, the bag page (READ books -> `abil_learn`, EQUIP), quick food / potion, hunger, the lair
bosses, the Archmage (blink / summons / Death Bolts / Mirror-Helm rules), the sealed door, the Tome hits (flash /
ash / border), the D8 gate, the descent stinger, the end card.

Pokes, all counted per run (`pokes` in the report) and logged with the tick:

| Poke | When | Why |
|---|---|---|
| `god_hp` | HP < 65 % of max while a hostile is in the room (35 % otherwise) and no Heal potion in the bag | the bot is a weak player; without it most runs die on D3-D7 (a death needs no proof here; GS_DEAD has its own run) |
| `god_food` | FOOD <= 8 and no food in the bag | the bot explores every room (hundreds of turns per level): hunger outruns the floor food |
| `boss_hp` | D8 only: after 60 `god_hp` pokes (or 9,600 ticks) spent in the Archmage fight, its HP is set to 1; the kill itself, the seal break, the Tome, the gate, the win are the game's | the Archmage (60 hp + depth, 7 spells, summons) out-damages a level 6-7 hero even with heals; `--boss-fallback 0` disables it |
| `nav` | a stuck streak (90 bot steps on <= 4 positions): the hero is moved inside the CURRENT room to the planner's goal; the room change itself is then the game's walk | only stuck recovery; 0-1 per run |
| `dead_hp` | `--mode dead` only: HP set to 2 on arrival at D3, no healing from there | makes the GS_DEAD ending quick; the death is a monster's hit |
| depth skip | `--start-depth N` (debugging only; NOT used in the reported runs) | `level_descend` from N-1 |

## Monitor (every tick)

Work per tick (`tick_work` -> `wait_tick`, T-states from ZEsarUX `get-tstates-partial`) <= 141,816; room change / level
change / state change / end-card ticks and modal ticks (bag page open) are reported separately (like budget.py);
`SYS_FRAMES` delta == `AY_CALLS` delta at every sample; `GAME_STATE` sane; `GEN_OVERFLOW` 0; bank-7 code
(`B7_CODE..B7_LIMIT`) hash == the .sna's every 25 ticks; entity slots (<= 16 active, kind / room / x / y valid, no body
parked in NOWHERE, no DYING body for > 80 ticks, no non-hostile live monster slot); `TOME_HP` only decreases and is 0
off D8, `TOME_FL` <= `TOME_FL_N`; border (port $FE, `get-io-ports`) is 0 except white / yellow while the Tome hook runs
(`TOME_FL` > 0; a hit every 3rd tick keeps it lit across hits by design) and red for an ALARM trap; every log line
pushed to the ring decodes to the font charset (<= `LOG_MAX`); `ROOM_MAP` of every room entered == the generator's model
(`room_model.render_room`) outside items / doors / grate / lectern / traps / animated decor, ids < `TILE_IDS`;
`[ANOMALY]` harness lines counted. A 3-frame `SYS_FRAMES` step between two ticks is only the sampling phase moving
(the sample is taken at `wait_tick`); a play tick 4+ frames after the previous sample would be listed in `slow_sample`.

## Results (release build, `tools/build.sh -o DIR -DDEBUG_KIT=0`, 2026-11-04)

Six win runs (Warrior / Mage x master seeds 0x1234, 0x0BAD, 0x5EED, each a full D1 -> D8 -> GS_WIN from the menu) and two
GS_DEAD runs. 30,749-40,939 ticks and 3,888-5,614 turns per win run, 20-27 wall minutes each (8 runs in parallel on a busy
host; ~34 ticks/s alone). Bot revisions: W 0x0BAD, W 0x5EED, M 0x0BAD, M 0x5EED and the 2 dead runs ran on `ee0353e`;
W 0x1234 on `f619869`; M 0x1234 on the final revision (held-hero top-up added). The later revisions only changed
recovery paths of the bot, never the monitor's rules.

| run | end | D | hero lvl | turns | ticks | max work T | monitor violations | god_hp | god_food | boss_hp | nav | ping-pong guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W 0x1234 win | GS_WIN | 8 | 7 | 4,421 | 37,132 | 118,604 | 0 | 154 | 13 | 1 | 0 | 13 |
| W 0x0BAD win | GS_WIN | 8 | 7 | 4,660 | 36,622 | 119,768 | 0 | 131 | 15 | 1 | 0 | 0 |
| W 0x5EED win | GS_WIN | 8 | 7 | 3,888 | 30,749 | 123,212 | 0 | 124 | 10 | 1 | 0 | 0 |
| M 0x1234 win | GS_WIN | 8 | 7 | 5,420 | 38,814 | **145,471** | **2 (T)** | 192 | 37 | 2 | 0 | 5 |
| M 0x0BAD win | GS_WIN | 8 | 7 | 4,155 | 31,681 | 115,517 | 0 | 169 | 9 | 3 | 0 | 0 |
| M 0x5EED win | GS_WIN | 8 | 7 | 5,614 | 40,939 | 121,058 | 0 | 182 | 15 | 1 | 2 | 36 |
| W 0x5EED dead | GS_DEAD | 3 | 2 | 688 | 5,042 | 102,951 | 0 | 0 | 0 | 0 | 0 | 0 |
| M 0x1234 dead | GS_DEAD | 3 | 2 | 693 | 5,002 | 112,273 | 0 | 0 | 1 | 0 | 0 | 5 |

Win card: `YOU WIN!` / `THE TOME IS DESTROYED` / CLASS / LEVEL / DEPTH 8 / KILLS / TURNS / BEST KILL, `END_SHOWN` 2, last log
line `YOU WIN!` in every win run (PNG per run via `PT_PNG=dir`). Death card `KILLED BY <monster>` + `YOU DIED - PRESS ENTER`.

Clean in every run (all 8): `SYS_FRAMES` delta == `AY_CALLS` delta at every sample; `GAME_STATE` only 2 / 3 / 4 / 5 / 6
(+ boot waits); `GEN_OVERFLOW` 0; bank-7 code hash unchanged (1,229-1,637 checks per win run); <= 5 active slots, 0 parked
leaks, no DYING body > 80 ticks; `TOME_HP` 5 -> 0 one per hit on D8 only, `TOME_FL` 3 / 2 / 1 per hit, ash after the last;
border 0 outside the Tome flash (white, yellow on the last hit) with no stuck colour; every one of ~200 distinct log lines
inside the font charset; ROOM_MAP of 46-319 room entries per run == the generator model; 0 `[ANOMALY]` lines. Play ticks
4+ frames after the previous sample: none (the only 4+ gaps are level / room / state transitions, <= 4.68 M T).

### Finding (game, not the bot): heaviest tick over the 2-frame limit

`M 0x1234 win`, D3 room 3, run tick 5,036: work tick **145,471 T > 141,816** (and 141,966 T two ticks later); the lead-up
ticks 4,963-5,038 all run 128-136 k T. Scene: the Mage in melee with Ghosts (3 hostiles + hero; a Might Ring is picked up on
the same turn; `TURN_PHASE` 0 / 1). Synthetic check (a throw-away script, not committed): a Mage meleeing 3 / 5 Ghosts in the
D1 start room peaks at 123 k / 133 k T, so the cost scales with the Ghost count. The window includes the next frame's ISR
(budget.py adds `PRE_FLOOR` 5.3 k + 402 for the HALT-side ISR), so the real margin on such ticks is negative. An earlier
revision of the same run showed 134,513 T at tick 5,234 (same room). Other runs peak at 115-123 k. Repro:
`ZRCP_PORT=<p> python3 tests/playthrough.py --hero M --seed 0x1234` on the release build (the bot is deterministic; the
tick number moves with bot revisions; `heaviest_ticks` in the report lists the top 8 with room / depth / last log lines).

**Fixed by PERF-GHOST (`perf/ghost-tick`, docs/memory-map.md "PERF-GHOST ledger"):** the same run now peaks at 137,897 T
(tick 5,036) / 135,426 T (5,038); `tests/budget.py` gates the scene's synthetic twin `ghost3` (+ `ghost5`, reported).

### Bot notes (limits, for the next person)

* The bot is a weak player: level 6-7 at D8, so most boss fights need god top-ups (see the poke table). `god_hp` counts
  every top-up (65 % threshold with a hostile in the room); the lair-boss stalemate fallback (`boss_hp`, 60 top-ups or
  9,600 ticks against one boss) fired once per win run on the D8 Archmage and, in some runs, on a D3 / D5 boss. A run
  without it was achieved once in development (M 0x1234, Archmage killed by the bot at D8); `--boss-fallback 0` disables it.
* `god_food` is large because the bot explores every room (Mummy / Pharaoh hits drain FOOD too: M 0x1234 spent 8.9 k ticks
  on the D5 Pharaoh); the floor food does not keep up with exhaustive exploration. A balance observation, not a bug.
* Mage spell choice honours the resistance table (a Ghost reflects Spark / Lightning at the caster: the first Mage run died
  to its own reflected bolt before this was added); kiting for Firebolt's burst, MP rests against healthy targets.
* A parked flyer overlapping the hero (Wraith in a corridor / on the exit shaft) refuses every walk and melee and spells miss;
  the exit shaft still works because a climb blocked twice swaps hero and blocker (game.md 9.2). The bot used to wait on
  such a flyer for ever (fixed: it lets the plan act). A blocked-move memory that never expired also stranded the bot (fixed:
  250-tick expiry). Neither is a game fault.
* Room ping-pong guard: 7 alternating room changes within 500 ticks marks the rooms visited / skipped (36 times in M 0x5EED,
  mostly the D3 / D7 side rooms): "explore every room" is best effort; `levels[].visited / rooms / skipped` in the report
  (revisions after ee0353e) show what was skipped.
