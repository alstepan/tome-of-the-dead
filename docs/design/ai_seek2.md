# AI-SEEK2: walkers follow the hero across storeys and halves (designer decision 2026-11-09)

Status: **APPROVED (user 2026-11-09), scheduled post-C** (docs/plan.md "POST-TUT0 ROADMAP" item 2): open questions take their defaults, except Q5: `seek_col` goes to bank 6 via far6 (bank 2 has ≈ 9–19 B free, shared with C's ≈ 130 B).

**As built (`feat/ai-seek2`):** `seek_col` is in **bank 7** behind far7 (`src/seek7.asm`, 85 B; R6 had 2 B free and cannot grow, bank 2 had 4 B);
`PL_SEG` is computed by bank-3 `pl_seg3` (called by `resolve_monsters` after `cache_player`, which encodes `PL_LADDER` = 2 for a
mid-climb on an internal ladder); `ROOM_CUT` is written by `build_room_map`. seek_col returns `L = $FF` for STRANDED (far7 loses A / CF).
Ledger: `docs/memory-map.md` "AI-SEEK2 ledger". Tests: `tests/ai_seek2.py`.

User request 2026-11-09: monsters must follow the hero smarter; a monster must not climb into a
part of the room that is cut off from him. This doc is the spec. It does not edit game.md;
the impacts on other docs are listed in §7.

Scope: **standing walkers with `KF_CLIMBER`** (the `.seek` path of `ai_monster`), plus the
hero-target byte every walker reads. Unchanged and still run first, in this order: yield
(`cork_check`), period gate, melee, ranged hook, boss guard (game.md §9.2 "Per-turn order").
Flyers are unchanged (§6 Q3).

---

## 1. How it works today (src/turn3.asm, bank 3; helpers in bank 2 logic.asm)

### 1.1 The hero's storey
`cache_player` (bank 2, once per monster phase) stores `PL_STOREY = min(1, (y+h) div 9)` and
`PL_LADDER` (1 = mid-ladder). So a hero **mid-climb on an internal ladder `{c,1}` is always
storey 1** (feet rows 9..16), whichever way he is going and however close to the top he is.
On an up-exit shaft he is storey 0, on a down-exit shaft storey 1.

### 1.2 The walker branch (`ai_monster`, after the ranged hook)
- Monster standing **and** `TMP4` (its storey) == `PL_STOREY` → `dx_to_player` and one step
  toward the hero's x (`.fstep`). Blocked by terrain (pit lip, block face) → it just stands.
- Otherwise `.other`:
  - non-climber → `.patrol`: pace in the facing direction, reverse when blocked;
  - climber mid-ladder → keep going in `E_AIDIR`; if blocked **and** `E_AIDIR` leads away from
    `PL_STOREY`, reverse (the AI-L1 turn-round);
  - climber standing → `.seek`: wanted segment = `{col,1}` (both "up from storey 1" and "down
    from storey 0" use the internal ladders; exits are excluded) → `nearest_ladder` →
    walk toward `col` (a blocked step goes to `lq_block`, the AI-L1 queue) → at `col`, `.at`
    climbs if the shaft rect is free (`box_free`), else waits.
- `nearest_ladder` (26 B): loops the 6 col bytes `RD_UPCOL..RD_LAD2`, keeps those whose
  `seg_storey` (bank 2, ~45 T) matches, picks the smallest `|col − x|`, tie = first (LAD1).
  **It looks only at the monster's x. It never looks at where the hero is, nor at pits or
  blocks.** ~0.65k T per call.

### 1.3 What splits a room for a walker
Storey 1 is never split (wide-pit landings are plain floor; a storey-1 dead-end block is at an
edge). Storey 0 has **at most one cut** (§1.1 L2: one L2 feature per room, L2 removes a narrow
pit):
- **narrow pit** `p` (3 cols): walkers refuse `x == p` and cannot jump, so it IS a cut for
  monsters (the hero jumps it);
- **wide pit** `p`, `W` 4..6: walkers refuse `p..p+W−3`;
- **mid-room block** `b`, `w` 2..3: solid cols `b..b+w−1`.
A dead-end block sits at an exitless edge: it shortens a storey, never splits it. Wide pits
and mid-blocks guarantee a ladder in each half; **a narrow-pit room may have a half with no
internal ladder** (the hero reaches it by jumping).

### 1.4 Failure cases (geometry in cols; walkers 3 wide unless noted)
- **F1 Wrong-half climb (the user's case).** Mid-block room `c1 = 4, b = 15, w = 2, c2 = 20`.
  Hero standing on storey 0 at x 6 (left half). Goblin on storey 1 at x 19 → nearest ladder =
  LAD2 (20) → climbs into the right half → now "same storey" → steps left until its face hits
  the block at x 17 → **stands there for ever** (same-storey branch never climbs). Same with a
  wide pit (presses at the lip `p+W−2`) or a narrow pit.
- **F2 Wrong-half descent target.** Same room, Goblin on storey 0 at x 12 (left half, body
  12..14), hero on storey 1. `|4 − 12| = 8`, `|20 − 12| = 8` → tie keeps LAD1: fine. Move
  the block to `b = 16, c2 = 21`, Goblin at x 13: LAD1 9, LAD2 8 → picks LAD2, walks right,
  the step to x 14 is blocked by the block face → `lq_block` sees no body → **waits for ever
  facing the block**, although LAD1 is in its own half. Wide pit: same, frozen at the lip.
- **F3 Across the cut on the same storey.** Hero on storey 0 right half, climber on storey 0
  left half: same-storey branch → presses at the cut for ever, even though "down LAD1, across,
  up LAD2" exists (always exists for wide pits / mid-blocks).
- **F4 Chasing a hero mid-climb.** Room without a cut, `c1 = 6, c2 = 22`. Hero climbs LAD1 up
  from storey 1; a Skeleton on storey 0 at x 20 sees `PL_STOREY = 1` → descends LAD2 (9 turns)
  while he arrives at the top of LAD1 → now it must climb back (9 more). Mirror: Skeletons on
  storey 1 walk to LAD1's foot and wait there (yield keeps them off his path) while he is
  already leaving at the top.
- **F5 Oscillation.** A hero who climbs 3 rows up then 3 rows down stays "storey 1" all along,
  so nothing flips there; the flip happens at the storey change: climbers in the other half
  alternate seek-up / seek-down each time he stands on a different storey. Pick itself is
  stable (distance to the target ladder shrinks as the monster walks).
- **F6 Bunching.** Every climber picks the nearest ladder to itself, so a pack on one side
  queues at one shaft (AI-L1 strongest-first makes this legal and deadlock-free; it is a
  pacing issue, not a bug). Not changed here (§6 Q2).
- **F7 Ladderless half (narrow pit).** Hero jumps into a narrow-pit half that has no ladder;
  climbers on storey 1 climb the only ladder and wait at the pit lip across from him. This is
  actually the best they can do; the new rules keep it on purpose (§2 R5).

---

## 2. Rules (AI-SEEK2)

### 2.1 Segments
A **segment id** is one byte: **bit 7 = storey** (0 / 1), **bit 0 = half** (storey 0 only).
Values: `$00` storey-0 left, `$01` storey-0 right, `$80` storey 1.

**Cut col `K`** (one per room, from the descriptor; stored at room build, §3):
- `RD_PITCOL = p ≠ 0` (narrow or wide) → `K = p`;
- else `L2_MIDB = b ≠ 0` → `K = b − 1`;
- else `K = $FF` (no cut: every x is the left half).

`seg0(x) = (x > K) ? 1 : 0`. This one compare is exact for every legal standing x of any
body width: narrow pit (x == p never stands), wide pit (p..p+W−3 never stands; right half
x ≥ p+W−2 > p), block (left x ≤ b−3, Spider b−4; right x ≥ b+w > b−1). A ladder's top end is
`seg0(c)` (climbers stand at x == c to climb; footprint clearances keep `c` off the cut).

### 2.2 The hero's target segment `PL_SEG` (computed in `cache_player`)
- Standing, or on an exit shaft: storey = `PL_STOREY` (as today).
- **Mid-climb on an internal ladder** (`PL_LADDER` and raw `(y+h) div 9 == 1`): storey = **the
  end he is heading to**: hero `E_AIDIR` up (`$FF`) → storey 0, down (+1) → storey 1. (Hero
  `E_AIDIR` is already kept as his climb direction: the yield rule reads it.)
- Storey 0 → `PL_SEG = seg0(hero x)`; storey 1 → `PL_SEG = $80`.

### 2.3 Walker decision (replaces the `PL_STOREY` test and `.seek`'s ladder pick)
Let `M` = the monster's segment (`TMP4` storey, `seg0(x)` on storey 0), `H = PL_SEG`.

- **R1 Same segment** (`M == H`, monster standing) → step toward the hero's x (today's
  `.fstep`). Includes a hero mid-climb **heading into M**: it walks to the shaft lip and the
  existing `try_step` cork test keeps it off his path, so it waits beside the hole and strikes
  when he stands. Fixes F4.
- **R2 Non-climber, different segment:** same storey (only across a cut) → step toward the
  hero's x (today: it stands at the lip facing him); other storey → `.patrol` (today). The
  only visible change for non-climbers: a hero mid-climb heading away now counts as gone
  (patrol instead of waiting at the foot).
- **R3 (as built, S4b fix):** the blocked reversal sets `ai_dir` to the end in the hero's destination segment: up iff `H == seg0(x)`, else down. A 1-hop descent (hero in the other storey-0 half) is therefore kept, not reversed (it ping-ponged on a body at the foot).
- **R3 Climber mid-ladder:** unchanged (continue `E_AIDIR`; blocked and leading away → reverse),
  but "away" is now read from `PL_SEG` bit 7 (destination storey) instead of `PL_STOREY`.
- **R4 Climber standing, different segment → pick a ladder** among LAD1 / LAD2 only (as today
  in effect), nearest `|c − x|`, tie = LAD1, restricted by the wanted top segment `T`:
  - `M = $80` (storey 1), `H` on storey 0 → `T = H`, climb up.
  - `M` on storey 0, `H = $80` → `T = M` (a ladder in my own half), climb down. Fixes F2.
  - `M`, `H` both storey 0, different halves (the **1-hop route**) → only if some ladder has
    top `H` **and** some ladder has top `M`: `T = M`, climb down; on storey 1 R4 then sends it
    up the ladder into `H`. Fixes F3. Otherwise → R6.
- **R5 Fallback pick (storey 1 only):** `M = $80` and no ladder has top `H` (hero in a
  ladderless narrow-pit half) → nearest ladder of any top: it climbs to the lip across the pit
  from him (keeps F7's good outcome; also puts it in a throwing line, §5).
- **R6 Stranded** (no ladder matches and R5 does not apply) → **step toward the hero's x**
  (R1's step). Terrain stops it at the lip / block face / under him; it then waits there,
  facing him. No pacing, no state. This is also the **trigger for the pit-stuck ranged
  fallback** of `new_monsters.md` (§5).
- After a pick, everything is today's code: walk to `c` (blocked by a body → `lq_block`),
  `.at` climbs when the shaft rect is free.

### 2.4 Properties
- **Stateless and deterministic:** a pure function of (descriptor, hero box + `E_AIDIR`,
  monster box). No RNG draws, no per-slot memory, so AI equivalence and seeded tests hold.
- **No dithering in the pick:** the target only changes when `H` changes, and a standing hero
  changes half only by a jump (narrow pit) or a climb. A hero hopping a narrow pit every turn
  can make a storey-1 climber walk between two ladders; he pays a turn per hop. Accepted.
- **"Lost the hero":** inside the room there is no lost state: R6 waits at the nearest point
  and the next turn re-decides, so it resumes the moment a route exists. Leaving the room is
  the follow / bank system (unchanged).
- **Hero-protecting rules first:** the yield, forced yield, squeeze-past and B16 rules are not
  touched; R1's approach to a busy shaft relies on the existing cork test in `try_step`.

---

## 3. Cost

| Part | Where | Bytes | When |
|---|---|---|---|
| `ROOM_CUT` byte (K) | low RAM vars, beside `PL_STOREY` ($BA76) | 1 B RAM | written at room build |
| `PL_SEG` byte | same | 1 B RAM | `cache_player` |
| K derivation (2 descriptor reads, `dec` for block, `$FF` default) | room build (`build_room_map`'s bank, GS_TRANSITION) | ≈ 14 B code | once per room entry, < 0.1k T |
| `PL_SEG` in `cache_player` (internal-ladder test, `E_AIDIR` sign, `seg0`) | bank 2 | ≈ 26 B | once per monster phase, ≈ 0.15k T |
| `seek_col` (M, compare, R4/R5/R6 table, LAD1/LAD2 loop with best-match + best-any) + `seg0` | **bank 2** if ≥ 80 B free, else **R6 behind far6** | ≈ 65–75 B | climbers in another segment only |
| `ai_monster` walker branch | bank 3 | **net ≈ −30 B** (`nearest_ladder` 26 B and the `.seek` storey compare leave; a call + the `M == H` test stay); R3 −1 B | per walker turn |

**No per-room record bytes and no segment table:** with one cut per storey-0 at most, the
whole segment map is `K`, and each ladder end's segment is one compare. (If a future feature
allows two cuts on one storey, `K` becomes 2 bytes and `seg0` a 2-compare; still no table.)

**Per-turn T:** `cache_player` +0.15k once; each climber in another segment **measured ~1.37k worst case as built (bank 7, contended, far7 ~0.5k included; the 1-hop two-pass case; U1 bound 1.5k)**, vs `nearest_ladder` ≈ 0.65k (the original estimate 0.3k + 0.2k far6 assumed uncontended code). Same-segment
walkers +≈ 40 T (the `M` computation). Worst case 8 climbers ≈ +1.5k T per turn, far under
the 126k tick cap; nothing per frame.

Bank 3 (7–13 B free) ends **positive**. If bank 2 and R6 are both short, the fallback
is to keep `seek_col` in bank 3 at ≈ +40 B net: then reclaim first (user rule: no cuts).

---

## 4. Test plan

**New `tests/ai_seek2.py`** (emulator, same harness pattern as `tests/ladder_jam.py`: seeded
generated room, room cleared, bodies poked, hero waits; build `-DDEBUG_KIT=0`). Each case
asserts the outcome within a turn bound, no body overlap at any turn end, and x-reversals
≤ 2 per monster (no pacing):

| Id | Geometry | Setup | Expect |
|---|---|---|---|
| S1 | mid-block `c1 4, b 15, w 2, c2 20` | Goblin storey 1 x 19; hero storey 0 x 6 | climbs LAD1, adjacent to hero ≤ 30 turns; never stands on storey 0 at x ≥ 15 (F1) |
| S2 | wide pit, mirror of S1 | Skeleton storey 1 under the left half; hero right half | climbs LAD2 (F1, pit) |
| S3 | mid-block `b 16, c2 21` | Goblin storey 0 x 13; hero storey 1 | descends LAD1, never steps to x 14 (F2 regression) |
| S4 | mid-block | climber storey 0 left, hero storey 0 right, standing still | down LAD1, across, up LAD2, adjacent ≤ 9+9+walk+10 turns (F3) |
| S5 | mid-block | non-climber (Mummy) as S4 | reaches the block face, then x constant for 20 turns, faces hero |
| S6 | narrow pit, 1 ladder, hero in the ladderless half | climber storey 1 | climbs the ladder, waits at the far lip facing hero (R5) |
| S7 | narrow pit, 1 ladder | climber storey 0 ladderless half, hero storey 1 | waits at the pit lip (R6), x constant after arrival |
| S8 | no cut, `c1 6, c2 22` | hero climbing LAD1 up from storey 1 (turn 3 of 9); Skeleton storey 0 x 20 | does NOT enter LAD2; walks to LAD1 lip, off the climb path every turn; attacks the turn he stands (F4) |
| S9 | no cut | hero climbing LAD1 down; climber storey 1 | waits at the foot, off the path (R1) |
| S10 | narrow pit, 2 ladders | hero jumps the pit 6 times; 2 climbers | no softlock, no overlap, every move legal |
| U1 | stub | `seek_col` called with poked `ROOM_CUT` / `PL_SEG` / x over a 12-row (M, H, ladders) table | col / stranded as §2.3; T ≤ 1.5k as built (bank 7, far7 incl.; measured ~1.37k) |
| U2 | stub | `cache_player` with the hero mid-ladder up / down / on an exit shaft | `PL_SEG` as §2.2 |

**Levelcheck / tools:** `tools/levelgen.py` gets `room_cut(desc)` (Python twin of K); levelcheck
asserts over the 1000-seed sweep: ≤ 1 cut per room, no ladder col `c` on a cut (`seg0(c)` well
defined), and Z80 `ROOM_CUT` == Python for a sample of room entries.

**Suites that change:** `tests/ai_equiv.py` A/B vs the pre-SEEK2 base is **expected to
diverge** in cut rooms and on hero mid-climb turns (both runs, incl. `AI_EQUIV_LADDER=1`);
triage every first mismatch to one of R1–R6, then re-baseline. `tests/ladder_jam.py` must
pass unchanged (no-cut rooms, hero standing on storey 0: same picks). `tests/status.py` yield
case and `tests/archmage.py` non-lock note: re-run, expected unchanged. Goldens: none expected
(no golden plays monsters through a cut room); any golden diff must be traced to a cut room
or a mid-climb turn before re-baselining.

---

## 5. Interactions

- **`new_monsters.md` (pit-stuck ranged fallback):** use R6 ("stranded") as the trigger rather
  than a second pit scan: `seek_col` returns STRANDED (e.g. CF, or A = `$FF`) and the fallback
  hook runs there. Line rules are theirs; note that across a narrow / wide pit the line is
  open (holes are in the floor row), across a mid-block it is not (solid), and R5 parks
  storey-1 climbers at the far pit lip, i.e. in line. Non-climbers across a cut reach R2's lip
  step, not R6: if the fallback must cover them too, call it from R2's same-storey case as
  well (one extra call, ≈ 3 B).
- **`decor_rules2.md`:** decor is non-solid and does not change segments. If it adds any solid
  or unwalkable decor on a storey floor, it must not create a second cut (or `K` grows, §3).
- **Vampire close-distance** (game.md §9.2 rule 2) scans for a cut between bodies; it could
  read `ROOM_CUT` instead (later reclaim, not part of this task).
- **Boss guard:** runs before the walker rules; an engaged boss uses R1–R6 like anyone, but
  never climbs by G2 (golden Goblin King loses climbing in its lair). No change.

## 6. Recommended scope and open questions (defaults in bold)

**Recommended scope (best behaviour per byte): all of R1–R6 + `PL_SEG`.** R4 (own-half /
hero-half filter) and `PL_SEG` destination fix F1, F2, F4 and are the core; R4's 1-hop and
R5 cost ≈ 10 B more and fix F3 / keep F7. Bank 3 ends with more free space than today.

- **Q1** Mid-ladder climber reverses as soon as the hero's destination storey flips (not only
  when blocked)? **No**: it needs a segment check on the reversed end too; revisit after
  playtest if climbers visibly overshoot.
- **Q2** Spread a pack over two ladders of the same target segment (take the other ladder when
  the nearest shaft is busy)? **No** for now: AI-L1 queue handles it; ≈ 15 B if wanted.
- **Q3** Flyers vs a mid-room block (solid in storey-0 rows 0..7): not checked here. **Keep
  the flyer rules**; the engineer reports if a flyer can be pinned at a block face, then a
  flyer fix is a separate item.
- **Q4** Non-climbers when the hero climbs away: **patrol** (R2, consistent with
  "gone"). Alternative "wait at the foot" costs a raw-storey special case (≈ 6 B).
- **Q5** Placement: **bank 2** for `seek_col` if it has ≥ 80 B free, else R6 via far6.
  Unblocked by the engineer's current free-byte figures in `docs/memory-map.md`.

## 7. Impacts on other docs (not edited here)

- `docs/design/game.md` §9.2: add an "AI-SEEK2" paragraph after "Ladder queue" pointing here;
  §1.1 "Reachability" / mid-block / wide-pit rows: "walkers may be cut off (intended)" becomes
  "climbers route around a cut via storey 1 when both halves own a ladder (AI-SEEK2)".
- `docs/design/prototype.md` §6.4 walker rule 3 (`.seek`): ladder pick by segment.
- `docs/memory-map.md`: `ROOM_CUT`, `PL_SEG`; `nearest_ladder` removed from bank 3,
  `seek_col` added (bank 2 or R6); free-byte deltas.
- `docs/plan.md`: task entry (staff, Sonnet-contracted is enough for the code; tests junior).
- `tools/levelgen.py` / `tools/levelcheck.py`: `room_cut` + invariant.
