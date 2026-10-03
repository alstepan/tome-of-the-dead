# WazHack/ZX — Stage 2 budget (G1)

> z80-architect, 2026-10-01, from `build/wazhack.sym`, `src/*.asm`,
> `assets/gfx/sprites/index.asm`, `docs/memory-map.md`, `docs/design/prototype.md`.
> **M** = measured (sym/listing/memory-map/ASSERT formula), **E** = estimate.
> 128K frame = 70,908 T; tick = 2 frames = 141,816 T; target 95% = **134.7k T**.
> A3/A5 (2026-10-02) measured: bank-2 headroom 3,170 B, low-RAM spare 1,308 B,
> sources 7,219 B packed. E2 replaces the E numbers (per-phase tick split, contention factor, stack
> depth, AY player cost) with measurements.

## 1. Usage per bank (today)

| Region | Size | Used | Free | |
|---|---|---|---|---|
| Banks 0/4/6 pre-shift pool | 49,152 | 38,752 (`POOL_NEED`: monsters 22,688 + hero max 12,608 Knight + 3 select idles 1,728 + straddle 1,728) | **10,400** | M |
| Bank 1 sources (low) | 16,384 | 16,384 | **0** | M |
| Bank 3 sources (high) | 16,384 | 4,227 | **12,157** | M |
| Bank 2 `$8000-$BFFF` | 16,384 | code+data `$8000-$AC72` 11,379; pad 141; `kind_tab` 256 @`$AD00`; tables `$B000-$BAAF`; stack 1,024; state 256 | code headroom **653** (to `$AF00`); table gaps ~180 | M |
| Bank 5 `$6000-$7FFF` | 8,192 | 3,104 (`LOWRAM_END=$6C20`) | **5,088** | M |
| Bank 5 `$5B00-$5FFF` | 1,280 | sysvars + dead BASIC loader | ~1,000 | E |
| Bank 7 | 16,384 | clean background 6,048 (span `$C000-$DA9F`) | **9,568** | M |

## 2. Rogue removal

| Item | Reclaimed | |
|---|---|---|
| Sprite sources | **3,712 B** → `SRC_TOTAL` 20,611 → 16,899; bank 3 then 15,869 free | M |
| Pre-shift pool | **576 B** only (Rogue select idle). Only the chosen hero is resident, so Rogue's set was never additive. Pool free 10,400 → **10,976** | M |
| Frame ids | 12 → `FID_COUNT` 80 → **68 / `FRT_MAX` 96** | M |
| Bank 2 | ~**220 B** (`frame_tab`, role/seq tables, names, select entry) | M+E |
| Code | select loops 2 heroes; keep a hole in `K_*` ids (renumbering breaks `HERO_KIND` + tests) | M |

## 3. Flicker fix — double buffer

**Clean background stays in bank 7**, rebased to `$E000` (bitmap `$E000-$F79F`,
attrs `$F800-$FA9F`, high-byte offset +`$A0`). Screen 2 = `$C000-$DAFF`. Bank 7
spare after: **2,656 B**. Cost to the sprite-source budget: **0** (moving it to
bank 3 would cost 6,816 B).

| | A: compose in 5, copy changed cells to displayed 7 | B: true flip 5/7 |
|---|---|---|
| Display | bank 7 always (bit 3 = 1) | alternates per tick |
| Blit | as today | bank-7 ticks: pool and bank 7 both need `$C000` → stage each frame in fixed RAM (+21 T/byte, ≤576 B) |
| Extra work | copy merged dirty cells 5→7, ~231 T/cell | every change drawn twice over 2 ticks; 2nd drawn-footprint record per slot (+128–256 B); catch-up render after each turn |
| Extra T, B1 tick | **+30–40k** E | **+30–40k** on bank-7 ticks E |
| Artefact | no flicker; a cell can tear for one frame if the beam passes it mid-copy | none (flip at HALT) |

Architect recommends **A** (no staging buffer, no duplicated state; cheap pause
pages: draw inventory in 5, clear bit 3, on exit copy 7→5). Manager decision (E1).

Constraints either way: `page_bank` must OR in the current screen bit (today
`or P7FFD_ROM48` clears bit 3); bit 4 stays 1 (48K ROM); never set bit 5; write
the shadow before the `OUT`; after a room transition rebuild bank 5 from bank 7
(6,912 B copy, ~145k T, once per room change).

## 4. Contention (128K/+2: banks 1, 3, 5, 7)

| Hot loop | Contended accesses | |
|---|---|---|
| Blit | 2 per screen byte (pool reads uncontended) | bank 5 |
| `erase_rect` | 18 per cell | 7 → 5 |
| Present copy (A) | 18 per cell | 5 → 7 |
| `stamp_rect` | 1 per cell | 5 |
| `tile_rect` | ~11 per cell | 5 |
| Sprite sources | generator only (boot/select) | 1/3 |
| Code, stack, entities | none | bank 2 |

Model (E): contention window 24,576 T/frame (34.7%); ≈ **1.2 T average per
contended access** (0.9–1.4). The old "+20%" guess is too pessimistic.

| B1 worst tick (hero + 2 skeletons + goblin + ghost) | Uncontended | Contended | % of tick |
|---|---|---|---|
| Today | **154,852 M** | 160–166k E | 113–117% |
| + double buffer (A) | ~190k E | 195–210k E | 138–148% |
| + AY reserve | — | ~210–223k E | **~150% (≈3 frames)** |

Only ~89k of the 154,852 is explained by the per-sprite model; **~66k is turn
logic + overlap repair + HUD message**, split unknown → E2 measures per phase
(`tests/budget.py` probes `read_turn_input`, `anim_tick`, `render`).

Per-sprite cost per tick after double buffer, contended (E):

| Sprite | T/tick |
|---|---|
| 24×48 walker | 27.7k |
| 24×48 jump (general blit path, +1 footprint row) | ~30.5k |
| 32×48 / 40×48 cast or attack (stationary) | ~29–30k |
| 24×32 walker | 18.9k |
| 24×16 / 32×16 small or flyer | ~12k |
| 8×8 projectile | ~4k |

Sprite budget per tick: first tick of a turn 134.7k − AY 13k − logic ~40k =
**~82k**; later ticks 134.7k − 13k − 8k = **~114k**.

| Combination | First tick (82k) | Later (114k) |
|---|---|---|
| hero + 1 tall + 1 short (≈77k) | fits | fits |
| hero + 2 tall (≈85k) | just over | fits |
| hero + 3 short (≈85k) | just over | fits |
| hero + 4 small (≈78k) | fits | fits |
| hero + 3 tall (≈111k) | over | at limit |

→ **hero + 2 moving monsters (≤ 1 tall) or hero + 4 small, + 1 projectile.**
With double buffering an overrun only stretches the tick to 3 frames (no
flicker). Lever: resolve turn logic in the input tick (+40 ms latency) so ~40k
of logic leaves the heaviest render tick.

## 5. AY player reserve (E, typical public players)

| Item | Bytes | T per 50 Hz call |
|---|---|---|
| PT3 player (Vortex Tracker II) | 1.6–2.0 KB + ~200 vars | 3–6k (worst ~8k) |
| PT2/STC (lighter) | 1.0–1.5 KB | 2–4k |
| AYFX effects player | 0.2–0.3 KB | 0.5–1k |
| Song data | 1.5–6 KB/song (in-game loops 1–3 KB) | — |
| FX bank | 20–60 B/effect (~1 KB for 30) | — |

- **IM2 required** (ROM IM1 can't be hooked; ticks run 2+ frames without a HALT).
- Vector table 257 B, `I` in `$80-$BF` → bank 2 (`$40-$7F` = 128K snow/crash;
  `$C0-$FF` paged).
- ISR stub ~40 B in bank 2: save regs (+alt set if the player uses `EXX`) → `OUT`
  music bank (shadow untouched) → call player → `OUT (PORT_7FFD_SHADOW)` →
  restore → `jp $0038` (ROM keeps `SYS_FRAMES`, keyboard scan, `IY`, `EI`).
  `wait_tick` unchanged. Overhead ≈ 0.5k + ROM ≈ 1k.
- Placement: vector table + stub from the 1 KB stack reservation (measure depth
  first). **Player + songs + FX: 7 KB at bank 3 `$E400-$FFFF`** (user-approved, game.md §11.2; contended
  fetches ~+10%).
- **Hold back 13k T per tick** (2 calls × ~6.5k ≈ 9% of the tick).
- Trap: `DI` windows stall music → no SP-trick blits.

## 6. Headroom for Stage 2 content (after Rogue removal, E1 option A, AY reserve)

| Store | Free | For | |
|---|---|---|---|
| Pre-shift pool 0/4/6 | **10,976** | hero frames beyond 12,608, new monsters, boss, projectiles/FX | M |
| Sources banks 1+3 | 32,768 − 16,899 − 7,168 = **8,701** (AY 7 KB) | unshifted source of every new frame | M+E |
| ↳ **after A3+A5 (measured 2026-10-02)** | ZX0 sources 7,219 B (68 frames, 23 blocks, 2.40×): **bank 1 9,165 free**, **bank 3 8,256 free** below the AY reserve (`$E400`, 7 KB per user; 7,232 was measured to `$E000`) | new frame sources (packed), menus/menu font, strings, icons | M |
| Frame ids | **28** | all new frames together | M |
| Bank 2 | ~**870 B** (+~2.1 KB if cold code moves out → ~3 KB) | hot code only | M+E |
| Bank 5 low RAM | 5,088 + ~1,000 | cold code (menu, inventory, generator), font, level state, item tables, tiles | M+E |
| Bank 7 spare | 2,656 | cold data (strings); never data drawn into bank 7 | M |

Per item (pool by the `POOLACC` formula, M; every new frame also costs 24 B in bank 2):

| Content | Source | Pool stationary / moving | T/tick (E) |
|---|---|---|---|
| Hero 24×48 (jump, idle) | 288 | 576 / 1,344 (+192 if 4-px anchor) | 27.7k / jump ~30.5k |
| Hero 32×48 (cast, ranged) | 384 | 768 / 1,728 | ~29k |
| Hero 40×48 (power attack; max width) | 480 | 960 / 2,112 | ~30k |
| Projectile 8×8 / 16×8 | 16 / 32 | 96 / 160 | ~4k / ~5k each |
| FX burst 16×16 / 24×24 (stationary) | 64 / 144 | 128 / 288 | ~7k / ~11k while shown |
| Static decor tile | 9 B (bank 5) | — | 0 |
| Animated decor | 9 B per anim frame per cell | — | glyph swap ~0.55k/cell/step; **attr-only colour cycle ~0.12k**; sprite overlap forces a re-blit (12–28k) |
| Door | ~54 B + 1 state bit | — | ~10–15k one-off open/close |
| HUD bars + selected-icon panel | code ~0.6 KB; 16×16 icons 33 B × 8 ≈ 270 | — | 2–4k when a value changes |
| Inventory page | code ~1.2 KB; 32 icons ≈ 1.1 KB; text ~0.4 KB | — | paused; ~145k copy on exit |
| Menu + redefine keys + joystick | code ~1.5 KB; strings ~0.5 KB; title art optional (~3 KB compressed) | — | cold |
| Font | ROM 0 B; custom 96 chars 768 B (fixed RAM) | — | — |
| Level state (2-storey rooms, doors, dead ends) | 24–32 B/room → ~1 KB/level; floor items 4 B each | — | — |
| Persistent monsters | 16 slots × 32 B → **15 monsters/level** incl. followers | — | — |
| Item/spell tables | ~256 B; inventory 16–24 × 2 B | — | — |

Animated decor: **≤ 4k T/tick** → ~7 glyph cells/tick (staggered) or ~30
attribute-only cells.

Pool pressure: Warrior additions (2 jump + 3 power attack) ≈ +4.5 KB; Mage
additions (4 spells × 2 cast frames) ≈ +6–7 KB; only max(Warrior, Mage) counts.
Boss ≈ 8–10 KB. **Does not fit 10,976 together with new monsters.** Levers:
(1) generate only the monster kinds present on the current level (regenerate
the pool at level start, ~1 s per 13 KB); (2) compress sprite sources (read only
by the generator) for ~1.7–2× source capacity.

## 7. Two storeys vs three

| | 3 storeys (PROTO) | 2 storeys: 9 / **10** / 11 rows each |
|---|---|---|
| Playfield / HUD rows | 21 / 3 | 18/6 · **20/4** · 22/2 |
| Room map | 672 B | 576 / **640** / 704 |
| Free rows above a 48-px hero (max jump) | 0 | 2 / **3** / 4 |
| Climb turns per storey | 7 | 9 / **10** / 11 |
| Flyer vertical range | bat 5, ghost 3 | +2 / **+3** / +4 |
| On-screen cap | hero + 4 (asserted) | tick-bound: **hero + 2–3** |
| `draw_room` / vertical scroll | ~195k | × rows/21 |

## 8. Hard limits for the designer

- Pool 49,152 B; **10,976 free** after Rogue removal.
- Sprite sources ≤ 32,768 B; **8,701 free** with the 7 KB AY reserve (`$E400-$FFFF`) in bank 3.
- **≤ 28 new frame ids** (`FRT_MAX` 96; raising costs 16 B/id in bank 2).
- Frame width ≤ 40 px, multiple of 8; source frame ≤ 512 B; anchors multiple of 4.
- 16 entity slots per level incl. hero (projectiles count if they are entities).
- 16 kinds (8 used after Rogue removal). 32 tile ids (13 used; 64 costs +288 B).
- `DMG_LIST` 48 rects/tick; render list 16.
- Moving sprites per tick ≈ **82k T** contended on a turn's first tick, ≈ **114k** later.
- Sprites/projectiles/FX only on black-paper cells (F9); jumps stay in the air
  band; no combat on ladders.
- Bank-2 hot-code headroom ~870 B; other Stage-2 code runs from bank 5 / paged.
- Fonts/icons drawn into bank 7 must live in fixed RAM.
- 128K / +2 only (+2A/+3 paging not supported).

**Top 3 designer decisions:** (1) encounter cap and simultaneous movers incl.
projectiles; (2) frames per hero/spell and monster kinds per level (decides
per-level pool generation — needed with a boss + new monsters); (3) storey
height / HUD rows (9/10/11) and animated-decor density.

**Open for manager / E2:** E1 option A vs B; per-phase B1 split, stack depth,
real contention factor; AY player choice and measured cost.
