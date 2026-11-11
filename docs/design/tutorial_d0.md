# Depth 0 — the guided tutorial (TUT0)

Designer, 2026-11-09. Status: **proposed, for user approval**. Implements the user decisions of
2026-11-09 (mentor in-world, one D1-tier monster, flow menu → hero → TUTORIAL/START → D0 → D1,
sandbox reset, new mentor art, once per tape load). Section refs `§n` are `game.md`.

> **As built (TUT0, 2026-11-11) — where this spec and the code differ, the code + `game.md` win:**
> `TUT_AVAIL` / `TUT_ON` flags were not built: the offer is SMC (`es_go` / `pl_et`, 0 resident B), spent on D1
> entry. The talk pose is drawn at once when a group is emitted (no 16-tick blocking gesture, §4.3; playtest A1).
> Panel depth reads `D0` at row 18 col 30. Choice lines read `1  TUTORIAL - DEPTH 0` / `2  START - DEPTH 1`.
> Holds, goal line, nudges and key words: `tut0_split.md` "Playtest round 1" / "Playtest round 2 — key clarity".

**Revision 2 (playtest 2, 2026-11-09): see §13** — mentor renamed **Brother Morrow**; pointers yield
to the ICON MODE cursor; interactive icon tour; explicit bag / book / scroll steps; pit and
WEAK-no-leap lessons; soft gating + nudges (no movement block). §3, §4.1, §8, §10 are updated
in place; §13 is the authoritative delta (ids, flags, triggers, budget, impacts).

## 0. Summary

| Item | Decision |
|---|---|
| What | A fixed, hand-made 3-room level "DEPTH 0, THE OLD CRYPT". A ghost mentor, **Brother Morrow** (R2; was Aldous the Sexton), walks the hero through 16 beats; one **Goblin** teaches fighting. Leaving D0 through its grate resets the hero to the new-game state and enters a normal D1 |
| Where it lives | One **loaded-once overlay blob** (script, text, level block, mentor art, choice screen) in the empty boot-time sprite pool. Dead once D1's pool is built; `TUT_AVAIL` is then cleared and the menu flow skips the choice |
| Resident cost target | **2 hooks + 2 flag bits** (§9): START → choice, end-of-turn → script. Everything else (level build, hold, mercy, D0→D1 reset, mentor drawing) runs from the blob through existing routines |
| Budget | blob ≈ **3.3–4.0 KB packed** (§8); dialogue **61 log lines + 5 menu lines ≈ 1.8 KB raw, ≈ 1.15–1.27 KB packed** |
| The goal | Morrow names the Tome as the run's goal at the start (B1) and gives the D8 method (Archmage first, 5 hits on the Tome, its aura, the way out) as the last thing said before the grate (B14) |
| Internal depth | **`DEPTH` stays 1 during D0** (all depth-indexed tables, scaling and unlock rows stay valid); a `TUT_ON` flag selects the D0 content. The player sees "0" (card + panel digit, drawn by the blob) |

## 1. Flow

```
loading picture -> PRESS ANY KEY -> HOW TO PLAY (2 pages, §7) -> MENU (controls 3/4, hero 2)
  -> 1 START -> [TUT_AVAIL?] -> CHOICE SCREEN --1/ENTER--> D0 (TUT_ON) --grate--> reset -> D1
                     |                       \--2--------> D1 (TUT_AVAIL := 0)
                     \--no----------------------------------> D1 (as today)
```

- **Controls first:** the menu already lets the player pick KEYS/KEMPSTON/SINCLAIR and redefine
  (items 3/4) before START, so the tutorial can name the *chosen* keys (§4.3 tokens). No menu change.
- **Choice screen** (menu font, drawn by the blob, digits only like every menu screen, §3.2):
  ```
  1  TUTORIAL (DEPTH 0)
  2  START (DEPTH 1)
  BROTHER MORROW WILL TEACH YOU      (R2; was THE SEXTON WILL TEACH YOU)
  ```
  `1` or **ENTER** = TUTORIAL (ENTER nudges the newcomer; see Q1); `2` = START. Keys accepted only
  after all keys are released once (the START `1` is still held). BREAK = back to the menu.
- **Seed:** taken at the START press as today (§1). The D0→D1 reset re-runs the START init, so D1 is
  seeded from `FRAMES` at the grate step; `SEED_FIXED` keeps tests deterministic.
- **Once per tape load:** `TUT_AVAIL` is set by boot, cleared when D1's level pool is first built
  (via the tutorial *or* via `2`/no-choice START). After that, `1 START` goes straight to D1.
- **Death / Quit in D0:** see §5.3. The pool built for D0 never overlaps the blob, so D0 can be
  replayed any number of times until D1 is entered.

## 2. The level: DEPTH 0, "THE OLD CRYPT"

Fixed level block (the existing descriptor format: rooms, edges, ladders, pit, door/grate bits,
floor-item list, trap list, 9 room records). Decor is re-derived from a fixed room seed as usual.
Grid cells used: **A = 1** (top row), **B = 4** (below A), **C = 5** (right of B). Floor colour =
`ATTR_FLOOR[1]`.

### 2.1 Room A (cell 1) — arrival, movement, jump, book, ladder, panel, food

```
col  0    5    10   15   20   25   30
     |    |    |    |    |    |    |
 0   ##   [S]                         ##   S = rubble-capped arrival shaft {5,0} (cols 5-7)
 2   ##   H@  M                  m    ##   @ hero mid-ladder at y=0 (H1-ARRIVAL)
 ..  ##                               ##   M = mentor spot A1 (x=9)   m = spot A2 (x=25)
 8   ======[ ]====[ ]===...===b=[ ]=  ##   [ ] ladder L1 {12,1} cols 12-14; pit p=19 (19-21,
     ##                               ##       caps 18/22); b = BOOK col 24; L2 {26,1} cols 26-28
 11  ##        M3                     ##   M3 = mentor spot A3 (x=18, storey 1)
 17  ===[v]=======f=================  ##   v = down-exit {5,2} cols 5-7 -> room B; f = PEAR col 17
```

- Feature checks (§1.1 rules hold even though D0 is hand-made): shaft 5 / L1 12 / pit 19 / L2 26
  are pairwise `|c1 − c2| ≥ 7` on storey 0; on storey 1 down-exit 5 / L1 12 / pit landing 19 /
  L2 26 likewise. Pit `p = 19 ∈ 5..24`; take-off `x = 16` → landing `x = 22` (body 22–24, on the
  cap and floor); the BOOK at col 24 is picked up on landing.
- Reachability by walk + climb alone: storey 0 left half ↔ L1 ↔ storey 1 ↔ L2 ↔ storey 0 right
  half. The jump is only needed to reach the book *quickly*; a fall (1d4) lands on storey 1.

### 2.2 Room B (cell 4) — key, trap, poison, cure

```
 0   ##   [^]                         ##   ^ = up-exit {5,0} (cols 5-7) from room A
 2   ##   @    M          m           ##   M = spot B1 (x=10)   m = spot B2 (x=21)
 8   ==========t=====c======[ ]=====  ##   t = hidden DART trap col 13; c = CURE potion col 19;
     ##                               ##       L1 {24,1} cols 24-27
 11  ##                    M2         ##   M2 = spot B3 (x=22, storey 1)
 16  ##                            |D|     D = LOCKED door, right edge, storey 1 -> room C
 17  ===============================
```

- Room B is the level's **key room** (key found on first entry, §1.1, no floor item).
- The trap is on the only storey-0 walk path to L1; it can be jumped (or sensed by the Mage, §1.5),
  which is allowed (§3 B8 alt line).

### 2.3 Room C (cell 5) — the Goblin, the scroll, heal, the exit

```
 0   ##                               ##
 8   ======[ ]======================  ##   L1 {12,1} (decor/consistency; storey 0 is empty)
 11  ##|D|  M          G              ##   M = spot C1 (x=6); G = GOBLIN x=22, ASLEEP
 16  ##|D|  s    h                    ##   s = SLEEP scroll col 4; h = HEAL potion col 9
 17  =====================[#]=======     # = level-exit GRATE {22,2} cols 22-24, SHUT
```

- The Goblin stands on the grate (the §9.2 boss-guard picture) but is **not** BOSS-flagged (a boss
  is immune to ASLEEP, which the hold and the scroll need). **The grate opens when the Goblin dies**
  (blob calls the existing grate-open routine used on a boss death; see §9 F3).
- Entering at the door (`x = 1`): the scroll is taken at step 2–3, the Heal at step 7–8.

### 2.4 Hero state on D0 entry

Normal new-game state for the class (kit, HP, MP) **except `FOOD := 40`** (stage OK, so the
hunger word means something and any food raises it). `KEY = 0`. Hero arrives mid-ladder at the top
of room A's shaft (§2.1 H1-ARRIVAL). D0 shows its own card: `DEPTH 0` / `THE OLD CRYPT` (replaces
the `DEPTH n` card for D0; the blob draws it and the panel depth digit `0`).

## 3. Beat list

Conventions. **Triggers are polled at the end of every turn** from existing state (hero room/x/
storey/ladder flag, bag contents, `ARANK`, `FOOD`, `ST_FLAGS`/`ENT_STAT`, `KEY`, Goblin slot HP and
status, door/grate bits). Actions that cost no turn (ICON MODE, opening the page) cannot be
observed, so beats **gate only on turn-costing results** (read, eat, drink, climb, walk, kill).
Lines go to the 2-row message log (§3.3–3.4), **one group (≤ 2 lines) per turn**; further groups
of the same beat wait for the next turn end. `‹U› ‹D› ‹L› ‹R› ‹F›` = the player's chosen controls
(§4.3). Line ids `Lnn` refer to §8. "Pointer" = hardware FLASH bit set on those panel cells while
the group is current (§4.4).

| # | Beat (room) | Mentor (spot, pose) | Says (group 1 / group 2) | Player must DO (trigger) | Placed | Fail / skip |
|---|---|---|---|---|---|---|
| B0 | Arrive (A) | A1, TALK | L01 `A LIVING ONE, AT LAST. COME DOWN` / L02 `PRESS ‹D› TO CLIMB DOWN` | stand on storey 0 (2 DOWN turns) | shaft | — |
| B1 | Walk + the goal (A) | A1, IDLE → TALK | L03 `WALK TO ME: HOLD ‹L› OR ‹R›` · L04 `A TAP ONLY TURNS YOU ROUND`; on trigger: L05 `I AM BROTHER MORROW, LONG DEAD` · L06 `I TENDED THEIR GRAVES. NOW YOU` (R2); next turn **L54 `THE ARCHMAGE'S TOME RAISED THEM` · L55 `IT LIES ON DEPTH 8. END IT`** (the run's goal, §1.3); next turn L07 `WAIT (‹D›) BY ME TO HEAR AGAIN` | hero box within 3 cols of A1 | — | walking past him also fires it |
| B2 | Pit + jump (A) (R2) | blink → A2, POINT (at the pit) | G0 **L65 `THAT BLACK GAP IS A PIT` · L66 `STEP IN AND YOU FALL A FLOOR`** (hold); next turn G2 L08 `A BOOK LIES PAST THE PIT` · L09 `LEAP: PRESS ‹U›+‹R› AT ONCE` (hold) | hero on storey 0 with `x ≥ 22` → G1 **L67 `LEAPS GO LEFT TOO: ‹U›+‹L›` · L68 `WIDE PITS ARE TOO FAR TO LEAP`** (scroll) | narrow pit, BOOK | fell into the pit: **L69 `FALLS HURT AND DROP ONE FLOOR`** · L10 `CLUMSY. THE LADDER LEADS BACK` (scroll), beat stays. Reached via L2 instead: fires anyway |
| B3 | Book + bag (A) (R2) | A2, POINT_DN | on book pickup: L11 `A BOOK! READ IT FROM THE BAG` · **L60 `ICONS: PRESS ‹D›+‹F› AT ONCE`** (hold; pointer: BAG icon, retired when ICON MODE opens, §13.2). **Icon target BAG** (§13.3): L12 `PRESS ‹F› TO OPEN THE BAG` · **L61 `PRESS ‹F› ON BOOK, THEN READ`** (hold the first time) | `ARANK ≠ 0` (book READ from the bag: Starter rule, §5, 0 RNG) → L13 `SEE? A NEW ICON ON YOUR BAR` · L14W/M (class) (hold); tail **L63 `SCROLLS READ FROM BAR OR BAG` · L64 `EMPTY ICONS WAIT FOR BOOKS`** (scroll) | — | book DISCARDed unread: L15 `NO BOOK? BELOW THEY ARE RARE`, advance. Book never picked up / unread and hero leaves A: skipped, **L76** on entering B (§13.5) |
| B4 | Ladder (A) | blink → A3, IDLE | L16 `LADDER DOWN TO ME: PRESS ‹D›` | standing on storey 1 | L2 | fall from the pit also lands on storey 1: fires |
| B5 | Panel + food (A) | A3, POINT_DN | L17 `BELOW YOU: LIFE, MANA AND FOOD` · L18 `YOUR BELLY SAYS OK, NOT FED` (pointer: row 21 bars + word); next turn L19 `EAT THE PEAR: THE FOOD ICON` · L20 `EAT: ‹D›+‹F›, THEN PICK FOOD` (pointer: FOOD icon) | `FOOD` rose this turn (any EAT: quick slot or page) → L21 `FED HEALS. THE STARVED FAINT` · L22 `EAT WHEN IT SAYS HUNGRY`; next turn tail (R2) **L70 `AT WEAK YOUR LEGS WILL NOT LEAP` · L71 `A LEAP THEN JUST DOES NOTHING`** (scroll). **Icon target FOOD:** L73 | PEAR col 17 | hero leaves A uneaten: skipped, **L76** on entering B |
| B6 | Shaft (A) | A3, POINT (left) | L23 `AT THE SHAFT (LEFT) PRESS ‹D›` | room = B | down-exit | — |
| B7 | Key (B) | fade-in B1, POINT_DN | (after the engine's key-found line) L24 `YOU HAVE THE KEY. ON TO THE DOOR` · L25 `IT OPENS ONE LOCKED DOOR` (no pointer: the build has no key icon; user option a, TUT0-F2) | standing on storey 0 | key room | — |
| B8 | Trap + status (B) | B1, IDLE | — (silent: the trap must surprise) | hero POISONED → L26 `HA! A DART. YOU ARE POISONED` · L27 `SEE THE ICON? YOU CANNOT EAT` (pointer: status icon cells row 21 cols 30–31); next turn L28 `TRAPS HIDE. WAIT (‹D›) TO SEEK` | hidden DART col 13 | not poisoned and `x ≥ 17` (jumped / sensed / searched): L29 `YOU PASSED A DART TRAP. LUCKY` + L28; B9 uses L32 |
| B9 | Cure (B) | blink → B2, POINT_DN | poisoned: L30b `DRINK THE CURE: ‹D›+‹F›, BAG` (pointer: BAG icon; as built, both kits hold a Heal). **Icon target BAG (R2):** **L72 `PRESS ‹F›, THEN DRINK THE CURE`** (hold the first time) | POISON cleared (Cure, or the timer) → L31 `POTIONS: HEAL, MANA AND CURE` | CURE col 19 | not poisoned: L32 `KEEP THE CURE FOR POISON`, advance on pickup |
| B10 | Door (B) | blink → B3, POINT (right) | L33 `GO DOWN, THEN WALK INTO THE DOOR` | room = C (the bump unlocks with the key: existing lines) | locked door | — |
| B11 | The sleeping Goblin (C) | fade-in C1, POINT (right) | L34 `A GOBLIN, ASLEEP. SEE ITS HUE` · class L35/L36 W/M. **Icon target slot 2 (B11 + B12, R2):** L73 | Goblin HP < max (first damage wakes it, §6.4) | Goblin, scroll, Heal | arriving with earlier beats undone: L53 `IMPATIENT? THE GOBLIN WAITS` first |
| B12 | Fight (C) | C1, TALK | L37 `IT WAKES! WATCH THE INFO LINE` (pointer: row 20) · class L38W/M | (passive; runs until B13/B14) | — | — |
| B13 | Scroll (C) | C1, POINT_DN | when the awake Goblin is within 6 cols: L39 `IT COMES! READ THE SLEEP SCROLL` · L40 `ICONS ‹D›+‹F›, SCROLL, ‹F›` (R2 reworded; pointer: SCROLL icon). **Icon target SCROLL:** L73. The bag way (pick it → READ) also fires the trigger; L63 told it in B3 | Goblin ASLEEP → L41 `IT SLEEPS. HIT IT - IT WAKES` | — | Goblin dies first: the scroll lesson becomes L52 in B14 |
| B14 | Victory + how to end the Tome (C) | blink → beside the grate, TALK | one group per turn, in this order: G1 L42 `WELL DONE. THE GRATE IS OPEN` · **L56 `ON 8, SLAY THE ARCHMAGE FIRST`**; G2 **L57 `HIT HIS TOME FIVE TIMES, FAST` · L58 `ITS AURA BURNS THOSE NEAR IT`**; G3 **L59 `ASHED, IT OPENS THE WAY OUT`** · L43 `WHAT YOU TOOK HERE STAYS HERE`; G4 L44 `FIND THE KEY, SLAY THE BOSS` · L45 `ITS GRATE IS YOUR WAY DOWN`; G5 L46 `PAUSE: HOLD ‹F›, PRESS ‹U›` · L47 `STEP ON THE GRATE. GO, CHILD` | Goblin dead (blob opens the grate) | — | The Tome method comes first (G1–G2 are out within the 1–3 steps from the Goblin's corpse to the grate), so it is the last thing read before D1. **Manager 2026-11-09: the blob opens the grate only after G3 has been shown** (the Tome method and the sandbox warning are mandatory; the blob already owns the grate-open, F3, so this costs 0 resident B); G4–G5 not yet shown when the hero steps on the grate are dropped. HP < max and a Heal held: one extra group L48 `HURT? DRINK THE HEAL POTION` after G3; unread scroll: L52 `KEEP SCROLLS FOR BAD FIGHTS` after G4 |
| B15 | Exit (C) | FADE out | — | the grate step (exit pending at end of turn) → **sandbox reset** (§5.2) → normal D1 entry | grate | — |

**Always-on rules (all beats):**
- **Repeat:** a Wait (DOWN, no move, no other trigger) with the hero within 4 cols of the mentor
  re-shows the current beat's instruction group (L07 tells the player).
- ~~**Nag:** 60 turns with no trigger re-shows the current instruction group once.~~ **R2: replaced
  by the Nudge (§13.5); R4 (TUT0-F4):** **6** off-task turns → ONE group L75 `CHILD. FIRST, DO AS I
  SAID` + the beat's goal line (scroll, pointer re-armed; L32 in B9's unpoisoned alternative), and
  the goal line FLASHes for that turn; once more at **18**; then silent. No movement is ever
  blocked (soft gating).
- **Goal line (R4, TUT0-F4):** while a beat waits for the player (its G0 processed — a silent G0
  counts — and its trigger not fired), its instruction is pinned on **row 20 cols 0–23** in
  Morrow's ink (attr `$45`); the log scrolls freely under it, so engine lines no longer bury it.
  One line id per beat (`tut_goal`, existing lines): B0 L02, B1 L03, B2 L09, B3 L60, B4 L16, B5
  L20, B6 L23, B7/B8 L24, B9 L30b (only while POISONED), B10 L33, B11 class L35W/L35M, B12/B13 none
  (combat owns row 20), B14 and B15 L47 from the moment the grate opens to the exit. Hidden while
  the Goblin is awake and in story groups (the hold prompt is the cue). Redrawn at each turn end
  when its id changed or the engine redrew row 20; survives holds; in ICON MODE (no turn) the
  engine's `>` icon info owns row 20 and the goal returns at the next turn end. Hidden: the info
  fields' attrs (`$47/$46/$45`) are put back and the info line redraws. Row 20 cols 24–31 stay the
  info line / the hold prompt.
- **R2 icon tour + pointer rule:** §13.2–13.3 (pointers never flash in ICON MODE; the cursor's
  slot is narrated).
- **Mercy:** at the end of any D0 turn with `HP ≤ MERCY_HP` (= **8**): HP := max, statuses kept,
  L50 `ENOUGH. I MEND YOU - THIS TIME` · L51 `BELOW, NO ONE WILL` (first time; later silently plus
  L50). Worst single-turn damage in D0 is a fall 1d4 + a Goblin hit 1d4 = 8, poison never kills
  (§6.4), so with max HP ≥ 12 the hero cannot die in D0. *(Engineer: confirm the Mage's base max HP
  ≥ 12; if lower, `MERCY_HP := maxHP − 4`, still ≥ the worst case of 4 once the pit is behind him.)*
- **Hold (the Goblin acts only when the script allows):** while the Goblin's HP = max and B11 is
  not passed, the blob re-writes its status to ASLEEP with timer 15 every turn (existing HOLD
  field). The first damage wakes it (existing "any HP loss wakes"); from then on the blob never
  touches it, except that the Sleep scroll may put it back to sleep normally. Because C is a
  different room, the Goblin is also frozen while the hero is in A/B (§1 "16 slots hold only the
  current room"), and the locked door stops it in any case.
- **Overtaken beats:** each beat belongs to a room. When the hero enters a room whose first beat is
  later than the current one, the script jumps to that room's first beat; skipped beats print
  nothing.

## 4. The mentor: Brother Morrow (R2; was "Aldous the Sexton")

### 4.1 Character

**R2 (user 2026-11-09): Brother Morrow**, the shade of the old crypt's last monk. The brothers
kept the crypt above the dungeon and tended its dead; Morrow prayed over and buried the
Archmage's first victims, died at his post, and is bound to the crypt: he **cannot go below**
(why he never follows into the run). Tone unchanged: dry, grim, kindly in a gallows way, few
words; calls the hero "CHILD"; never preaches. Named in L05 (`I AM BROTHER MORROW, LONG DEAD`),
L06 (`I TENDED THEIR GRAVES. NOW YOU`) and the choice screen (`BROTHER MORROW WILL TEACH YOU`);
no other line names him. Never fights, never takes damage, never blocks: he is a ghost.
**Art unchanged:** the existing 3/4 frames (hooded robe, lantern at waist height, wisp instead of
feet) read as a monk; internal labels `sxt34_*` / `aldous34.asm` may stay (no rename churn; the
name is never shown from them). Original brief, kept for reference: tall hooded figure in a ragged
coat (now: a monk's habit), a lantern held in front at waist height, the robe fading into a wisp instead of feet; hovers
**one char row above the floor** (top at `y = 9s + 1`, so an 8-px gap of air shows under him).
Colour: ink **cyan `$05`**, black paper (distinct from FROZEN `$45`, gold `$46/$47`, hit `$42`).

### 4.2 Frames (24×48 px each, 3×6 cells, 1-bit, cell-aligned)

| # | Frame id | Purpose | Facing | Stored images |
|---|---|---|---|---|
| 1 | `SXT_IDLE1` | hover, lantern low | SYM | 1 |
| 2 | `SXT_IDLE2` | hover bob: wisp + coat hem shifted, lantern flame flickers | SYM | 1 |
| 3 | `SXT_TALK1` | speaking: hood tilted up, free hand open | SYM | 1 |
| 4 | `SXT_TALK2` | speaking: hand raised higher, jaw open | SYM | 1 |
| 5 | `SXT_POINT` | arm straight out, finger pointing (pit, shaft, door, Goblin) | **facing matters** | 2 (L, R) |
| 6 | `SXT_POINTDN` | lantern + hand lowered toward the floor/panel (items at his feet, the panel) | SYM | 1 |
| 7 | `SXT_FADE` | dithered half-dissolve, for blinking out/in | SYM | 1 |

**7 frame ids, 8 stored images, 8 × 144 B = 1,152 B raw** (no masks, no pre-shift: §9 F1 draws
him cell-aligned into the background), ≈ 0.6–0.75 KB packed in the blob. No walk cycle: he moves
only by **blinking** (FADE 2 ticks at the old spot → gone → FADE 2 ticks at the new spot → pose),
which suits a ghost and saves 2–4 frames.

### 4.3 Animation (all driven from the end-of-turn hook; no per-tick resident hook)

- **Idle:** IDLE1/IDLE2 toggle once per turn (he "breathes" as the player acts).
- **Speaking:** when a group is emitted, a short blocking gesture of **16 ticks** (TALK1/TALK2,
  4 ticks each, ×2), then the beat's pose. Accepted: like a spell flight (§2.2), the world waits
  ≈ 0.6 s. If the panel queue cannot drain during the gesture, the lines appear right after it.
- **Blink:** 4 ticks blocking (above). Spots never need to avoid the hero (he is intangible).

### 4.4 Key-name tokens and the panel pointer

- **Tokens `‹U› ‹D› ‹L› ‹R› ‹F›`** (1 B each in storage) are expanded by the blob when the line is
  queued: **KEYS** → the redefined key's name from `KEYTAB` (`Q`, `A`, `SPACE` …; ≤ 5 chars; **R4:
  the REDEFINE screen's 2-char names are spelled out: `SP` → `SPACE`, `CS` → `CAPS`, `SS` → `SYM`;
  `EN` never names a control key**);
  **KEMPSTON / SINCLAIR** → `UP` `DOWN` `LEFT` `RIGHT` `FIRE`. Every line in §8 fits 32 chars with
  each token at 5 chars and a chord `‹D›+‹F›` at 11. Name table: reuse the REDEFINE screen's if the
  blob can read it (bank 3), else a ≈ 110 B copy in the blob.
- **Pointer:** the blob sets the attr **FLASH bit** on the named panel cells while the group is
  current, and clears it on the next group/trigger (hardware flash: 0 CPU). If the panel queue
  rewrites those attrs (a bar changes), the flash simply ends early. No cursor move: the player
  still drives ICON MODE himself. **R2: pointers yield to the cursor** — no pointer flashes while
  ICON MODE is open, and a pointer retired by ICON MODE does not come back (§13.2).
- **R4 writing rule:** a line never begins with a token; `‹X›+‹Y› AT ONCE` introduces a chord (§8).
- **R4 rows:** the ROW20 pointer rect is **row 20 cols 0–23** (supersedes §14.6's 0–25); the hold
  prompt is a fixed **`▶ ANY KEY`** at **row 20 cols 24–31** (triangle col 24, blinking; text from
  x = 200), the same in every control mode, bright white; cols 24–31 go back to `$45` and blank on
  dismissal. The goal line (§3) uses cols 0–23.

## 5. Training monster, sandbox and endings

### 5.1 The Goblin (kind `Goblin`, §9.1, scaled as D1: hp 6, atk 1, eva 1, 1d4)

Why Goblin, not Rat/Slime/Bat: a Rat (3 hp) dies to one sword hit or one Spark, so the player never
sees a miss, a hit taken or a mana drain; the Slime resists PHYS (the Warrior's first fight would
feel broken) and acts every 2; the Bat is erratic and a flyer (bad first target for a facing-aimed
Spark). The Goblin takes 2–3 sword hits / 2–3 Sparks, hits back for 1d4 (the HP bar visibly
moves), is a humanoid "real enemy", and can drop an Apple (1/4: a free demo of drops). It is an
opener and climber, so the lock (key) and the room boundary hold it, and the ASLEEP hold keeps it
on the grate until the player strikes.

Scripted behaviour: asleep (hold, §3) → first damage wakes it → normal chase AI → may follow the
hero out of C like any monster. **It cannot kill the hero** (Mercy). Teaches: bump attack, the
class power (Power Strike stun / Spark), the info-line target readout (§6.5), monster status tints
(ASLEEP `$41`, STUNNED `$07`, CONFUSED `$43` from a lucky Spark), the Sleep scroll, and "kill the
guard → the grate opens".

### 5.2 Sandbox reset (D0 → D1)

At the end of the turn in which the hero steps into the D0 grate (exit pending), the blob:
clears `TUT_ON` and `TUT_AVAIL`, then calls the **same new-game init START uses** (class kit,
HP, MP, XP/level, bag, ammo, worn gear, `ENT_STAT`, `FOOD = 80`, `HW_TMR`, `ARANK` / `BOOK_DRY`,
STATS2 counters, `KILLS`, `TURN_COUNTER`, `KEY`, icon cursor, seed from `FRAMES`) and lets the
normal exit path run `level_descend` → D1 `level_enter`/`level_populate`. D1's pool build then
overwrites the blob. Nothing from D0 survives: the D1 start-room book is still the hero's first
read (Starter rule, §5).

### 5.3 Skip, death, quit

- **Leaving early: yes.** The shortest route (≈ 50–60 turns) is: down the shaft, walk/ladder (or
  fall) to the down-exit, the key is automatic in B, ladder, door, **kill the Goblin**, grate.
  The grate stays shut until the Goblin dies (the core rule of every level: kill the guard, take the
  grate). Remaining beats are discarded; the reset runs as above.
- **Faster skip:** the choice screen's `2 START` (and Pause → Quit → `1` → `2` from inside D0).
- **Death:** prevented by Mercy. If it happens anyway (an unforeseen source), the normal death
  flow runs (`YOU DIED`, end card, menu); `TUT_AVAIL` is still set, so `1 START` offers the
  tutorial again and D0 is rebuilt from the intact blob. No special code.
- **Quit (Pause):** back to the menu, tutorial still offered.

## 6. Class differences (Warrior vs Mage)

| Beat | Warrior | Mage |
|---|---|---|
| B3 book | `WAR MANUAL` → Power Strike; L14W `POWER STRIKE: A BLOW THAT STUNS` | `SPELLBOOK` → Spark; L14M `SPARK: A BOLT THAT COSTS MANA` |
| B11 attack | L35W `WALK INTO IT TO STRIKE` · L36W `OR PICK POWER STRIKE AND ‹F›` | L35M `PICK SPARK, FACE IT, PRESS ‹F›` · L36M `SPELLS FLY THE WAY YOU FACE` |
| B12 resource | L38W `STRIKES COST MANA. IT RETURNS` | L38M `NO MANA? HIT IT WITH THE STAFF` |
| Fight shape | wake hit (1d6) + 1–2 more; Power Strike likely kills or stuns (tint `$07`) | wake Spark (1d4+1) + 1–2 more at range as it approaches; 2 MP each, the MP bar visibly drains |

All other beats are shared. The Warrior's Daggers/Bow slots are not taught (discoverable; the bow
is greyed `NO BOW` anyway). *(Engineer: if a class kit already holds a Heal potion, the quick
POTION slot picks Heal first (§8 auto-fill), so B9's L30 must be done from the bag page; in that
case swap L30 for L30b `DRINK THE CURE: ‹D›+‹F›, BAG` (27).)*

## 7. Fate of the HOW TO PLAY screen

**Decision: shorten to 2 pages.** Keep page 1 (goal + controls; the only reference for players who
skip the tutorial on a later load, and it costs 0 resident bytes) and page 3 (boss treasures and
charms: D4+ content the tutorial cannot show). **Drop page 2 (items and tips):** every row of it is
now taught by doing in D0 (potion, food, scroll, book, key, grate, Wait = search, hunger/faint),
except daggers/weapons, which are self-explanatory on pickup. Add one line on page 1 row 20 (blank
today): `NEW HERE? AFTER START, PICK 1 TUTORIAL` (38 ≤ 42, `$45`). Saves ≈ 0.5 KB of tape
(≈ 3 s of loading), which partly offsets the blob's ≈ +20–25 s on tape (§11 Q6).

## 8. Text budget

Log lines are FONT6, ≤ 32 chars (tokens counted at 5, a chord at 11), upper case, no trailing full
stop (§3.4 style). Counts are worst-case display widths. **R4 (TUT0-F4, 2026-11-10) writing rule
(linted by `tools/tutpack.py`):** a line never begins with a key token; a key follows `PRESS` /
`HOLD` / `(`; a chord is introduced as `‹X›+‹Y› AT ONCE` in its first use per action (B2 leap, B3
icons). The 16 R4-5 rewordings are in the table below (same ids, no new text).

| Id | Line | Chars |
|---|---|---|
| L01 | `A LIVING ONE, AT LAST. COME DOWN` | 32 |
| L02 | `PRESS ‹D› TO CLIMB DOWN` (R4; B0 goal) | 25 |
| L03 | `WALK TO ME: HOLD ‹L› OR ‹R›` (R4; B1 goal) | 31 |
| L04 | `A TAP ONLY TURNS YOU ROUND` | 26 |
| L05 | `I AM BROTHER MORROW, LONG DEAD` (R2) | 30 |
| L06 | `I TENDED THEIR GRAVES. NOW YOU` (R2) | 30 |
| L07 | `WAIT (‹D›) BY ME TO HEAR AGAIN` (R4: names the Repeat key) | 32 |
| L08 | `A BOOK LIES PAST THE PIT` | 24 |
| L09 | `LEAP: PRESS ‹U›+‹R› AT ONCE` (R4; B2 goal) | 31 |
| L10 | `CLUMSY. THE LADDER LEADS BACK` | 29 |
| L11 | `A BOOK! READ IT FROM THE BAG` | 28 |
| L12 | `PRESS ‹F› TO OPEN THE BAG` (R2: B3 icon target BAG, line 1; R4 reworded) | 27 |
| L13 | `SEE? A NEW ICON ON YOUR BAR` | 27 |
| L14W | `POWER STRIKE: A BLOW THAT STUNS` | 31 |
| L14M | `SPARK: A BOLT THAT COSTS MANA` | 29 |
| L15 | `NO BOOK? BELOW THEY ARE RARE` | 28 |
| L16 | `LADDER DOWN TO ME: PRESS ‹D›` (R4; B4 goal) | 30 |
| L17 | `BELOW YOU: LIFE, MANA AND FOOD` | 30 |
| L18 | `YOUR BELLY SAYS OK, NOT FED` | 27 |
| L19 | `EAT THE PEAR: THE FOOD ICON` | 27 |
| L20 | `EAT: ‹D›+‹F›, THEN PICK FOOD` (R4; B5 goal) | 32 |
| L21 | `FED HEALS. THE STARVED FAINT` | 28 |
| L22 | `EAT WHEN IT SAYS HUNGRY` | 23 |
| L23 | `AT THE SHAFT (LEFT) PRESS ‹D›` (R4; B6 goal: the shaft is a ladder top, entered with ‹D›) | 31 |
| L24 | `YOU HAVE THE KEY. ON TO THE DOOR` (TUT0-F2) | 32 |
| L25 | `IT OPENS ONE LOCKED DOOR` | 24 |
| L26 | `HA! A DART. YOU ARE POISONED` | 28 |
| L27 | `SEE THE ICON? YOU CANNOT EAT` | 28 |
| L28 | `TRAPS HIDE. WAIT (‹D›) TO SEEK` (R4: every Wait searches, game.md §2.3) | 32 |
| L29 | `YOU PASSED A DART TRAP. LUCKY` | 29 |
| ~~L30~~ | ~~`DRINK THE CURE: THE POTION ICON`~~ R2: **removed** (unused since T7: both kits hold a Heal) | — |
| L30b | `DRINK THE CURE: ‹D›+‹F›, BAG` (B9 G0 + goal while poisoned; R4) | 32 |
| L31 | `POTIONS: HEAL, MANA AND CURE` | 28 |
| L32 | `KEEP THE CURE FOR POISON` | 24 |
| L33 | `GO DOWN, THEN WALK INTO THE DOOR` | 32 |
| L34 | `A GOBLIN, ASLEEP. SEE ITS HUE` | 29 |
| L35W | `WALK INTO IT TO STRIKE` | 22 |
| L36W | `OR PICK POWER STRIKE AND ‹F›` | 30 |
| L35M | `PICK SPARK, FACE IT, PRESS ‹F›` | 32 |
| L36M | `SPELLS FLY THE WAY YOU FACE` | 27 |
| L37 | `IT WAKES! WATCH THE INFO LINE` | 29 |
| L38W | `STRIKES COST MANA. IT RETURNS` | 29 |
| L38M | `NO MANA? HIT IT WITH THE STAFF` | 30 |
| L39 | `IT COMES! READ THE SLEEP SCROLL` | 31 |
| L40 | `ICONS ‹D›+‹F›, SCROLL, ‹F›` (R4; R2 was `‹D›+‹F›, SCROLL ICON, ‹F›`) | 32 |
| L41 | `IT SLEEPS. HIT IT - IT WAKES` | 28 |
| L42 | `WELL DONE. THE GRATE IS OPEN` | 28 |
| L43 | `WHAT YOU TOOK HERE STAYS HERE` | 29 |
| L44 | `FIND THE KEY, SLAY THE BOSS` | 27 |
| L45 | `ITS GRATE IS YOUR WAY DOWN` | 26 |
| L46 | `PAUSE: HOLD ‹F›, PRESS ‹U›` (R4) | 30 |
| L47 | `STEP ON THE GRATE. GO, CHILD` | 28 |
| L48 | `HURT? DRINK THE HEAL POTION` | 27 |
| L50 | `ENOUGH. I MEND YOU - THIS TIME` | 30 |
| L51 | `BELOW, NO ONE WILL` | 18 |
| L52 | `KEEP SCROLLS FOR BAD FIGHTS` | 27 |
| L53 | `IMPATIENT? THE GOBLIN WAITS` | 26 |
| L54 | `THE ARCHMAGE'S TOME RAISED THEM` (B1, the goal) | 31 |
| L55 | `IT LIES ON DEPTH 8. END IT` (B1) | 26 |
| L56 | `ON 8, SLAY THE ARCHMAGE FIRST` (B14: his death breaks the Sanctum seal, §1.3) | 30 |
| L57 | `HIT HIS TOME FIVE TIMES, FAST` (B14: `TOME_HP` 5, any attack) | 29 |
| L58 | `ITS AURA BURNS THOSE NEAR IT` (B14: 1 HP/turn within 6 cols) | 28 |
| L59 | `ASHED, IT OPENS THE WAY OUT` (B14: the gate opens, leave by it) | 27 |
| **R2 beat lines** | | |
| L60 | `ICONS: PRESS ‹D›+‹F› AT ONCE` (B3 G0 line 2 + goal; R4) | 32 |
| L61 | `PRESS ‹F› ON BOOK, THEN READ` (B3 icon target BAG, line 2; R4) | 30 |
| L63 | `SCROLLS READ FROM BAR OR BAG` (B3 tail) | 28 |
| L64 | `EMPTY ICONS WAIT FOR BOOKS` (B3 tail) | 26 |
| L65 | `THAT BLACK GAP IS A PIT` (B2 G0) | 23 |
| L66 | `STEP IN AND YOU FALL A FLOOR` (B2 G0) | 28 |
| L67 | `LEAPS GO LEFT TOO: ‹U›+‹L›` (B2 G1) | 30 |
| L68 | `WIDE PITS ARE TOO FAR TO LEAP` (B2 G1) | 29 |
| L69 | `FALLS HURT AND DROP ONE FLOOR` (B2 FH_PITFALL, with L10) | 29 |
| L70 | `AT WEAK YOUR LEGS WILL NOT LEAP` (B5 tail) | 31 |
| L71 | `A LEAP THEN JUST DOES NOTHING` (B5 tail) | 29 |
| L72 | `PRESS ‹F›, THEN DRINK THE CURE` (B9 icon target BAG; R4) | 32 |
| L73 | `THAT ONE. NOW PRESS ‹F›` (icon target confirm: B5 FOOD, B11/B12 slot 2, B13 SCROLL) | 25 |
| L75 | `CHILD. FIRST, DO AS I SAID` (Nudge, §13.5) | 26 |
| L76 | `YOU LEFT A LESSON UNDONE ABOVE` (entering B with B2–B5 open, §13.5) | 30 |
| **R2 icon tour (§13.3)** | | |
| I00a | `THE LIT ICON IS YOUR CHOICE` (first ICON MODE entry, line 1) | 27 |
| I00b | `PICK: ‹L› ‹R›. LEAVE: ‹U›` (first ICON MODE entry, line 2; R4) | 31 |
| I01W | `SWORD: ‹F› OR WALK INTO A FOE` (slot 1, Warrior) | 31 |
| I01M | `STAFF: ‹F› OR WALK INTO A FOE` (slot 1, Mage) | 31 |
| I02W | `POWER STRIKE: COSTS MANA, STUNS` (slot 2, Warrior, once learned) | 31 |
| I02M | `SPARK: FLIES THE WAY YOU FACE` (slot 2, Mage, once learned) | 29 |
| I04W | `DAGGERS: ‹F› THROWS ONE AHEAD` (slot 4, Warrior) | 31 |
| I05W | `BOW: FIND ONE, THEN ARROWS` (slot 5, Warrior, greyed) | 26 |
| I07 | `FOOD: ‹F› EATS. MIND THE BELLY` (slot 7) | 32 |
| I08 | `POTION: ‹F› DRINKS. HEAL FIRST` (slot 8; explains the auto-fill, hence the Cure from the bag) | 32 |
| I09 | `SCROLL: ‹F› READS IT ALOUD` (slot 9) | 28 |
| I10 | `BAG: ‹F› OPENS IT. OR KEY I` (slot 10; `I` is a fixed shortcut, never redefined) | 29 |
| TS_CHOICE3 | `BROTHER MORROW WILL TEACH YOU` (menu font, R2) | 29 |

(L62 and L74 were drafted and dropped; no ids. Widths above are worst case: token 5, chord 11.)

The six Tome lines (L54–L59) use no key tokens and deliberately leave out what D8 shows on the
spot: the sealed door, facing/reach, the storey rule and the gate's place in the lair.

| Text block | Lines | Raw bytes (E) | Packed (E, textpack ≈ 0.65) |
|---|---|---|---|
| Log lines above (shared 52, Warrior 4, Mage 4, kit-case 1; L49 unused id) | **61** | ≈ 1,655 (chars + terminators; tokens 1 B) | ≈ 1,075 |
| Choice screen (3) + D0 card (2) + page-1 pointer line (lives in HOW TO PLAY) | 5 (+1) | ≈ 95 | ≈ 80 |
| Key-name table (only if the REDEFINE table is unreachable) | — | ≈ 110 | ≈ 110 |
| **Dialogue total** | **66** | **≈ 1.75–1.85 KB** | **≈ 1.15–1.27 KB** (budget 1.5–2.5 KB) |

**Blob total (E):**

| Part | Packed bytes |
|---|---|
| Dialogue (above) | 1,150–1,270 |
| Beat table: 16 beats × ≈ 10 B (room, trigger kind + 2 params, spot, pose, 3 group ids, pointer mask, flags) | 160 |
| Level block: 3 room descriptors, edges, 5 floor items, 1 trap, 9 room records, start | 120–150 |
| Mentor art (8 images × 144 B raw) | 600–750 |
| Script code: trigger poll, group queue + token expand, mentor stamp/save/restore (18-cell save buffer 162 B, may live in the pool scratch), blink/talk loops, hold, mercy, reset call, choice screen, D0 card, panel digit | 1,300–1,800 |
| **Total** | **≈ 3.3–4.0 KB packed** (≈ 4.8 KB unpacked); headroom ≈ 1–2 KB in the 4–6 KB budget |

**As built (TUT0-F2):** 63 TL + 5 TS ids, 1,406 B (≈ 20.7 B per id incl. its 2-B table entry);
blob 6,423 B raw, 1,767 B free in `BLOB_RES`. **R2 delta (§13.7):** +27 TL ids, −1 (L30), 4 lines
reworded → 89 TL + 5 TS; text ≈ +540 B, tables ≈ +50 B, code ≈ +310 B → **≈ +900 B raw**
(≤ 1,000 B target), ≈ 860 B left in `BLOB_RES`.

## 9. Engine contract: resident hooks and capability flags

**Resident hooks (target ≈ 16–20 B + 1 flag byte):**

| Hook | Where | What | Est. |
|---|---|---|---|
| H-T1 | START handler (menu) | `if TUT_AVAIL: far-call blob choice` (the blob either starts D0 itself or clears `TUT_AVAIL` and returns to normal START) | ≈ 8 B |
| H-T2 | `end_turn`, **before** `do_exit` | `if TUT_ON: far-call blob tut_turn` (triggers, lines, mentor, hold, mercy, and on an exit pending at the grate the sandbox reset) | ≈ 8 B |
| flags | any free byte | `TUT_AVAIL` (boot sets), `TUT_ON` (D0 running): 2 bits | 0–1 B |

No hook at level entry and none at `level_descend`: the blob builds D0 itself (writes the level
block into the level state, then calls the post-generation part of level entry: populate from the
room records, draw, arrival), and the reset happens inside H-T2 before the normal descent. The hold
needs no hook (status rewrite in H-T2).

**Capability flags (each with the cheaper path the spec already assumes):**

- **F1 Mentor rendering (top risk).** Required: drawn in the playfield, never collides, never
  targeted or damaged, survives redraws. **Default (0 resident B): background stamp.** The blob
  saves the 18 cells (glyph + attr) under the mentor's 3×6 box, writes his frame into the clean
  background (bank 7) and the shown screen, and restores them when he blinks; hero/Goblin sprites
  draw over him by the normal background-restore path, so he cannot block or be hit by
  construction. Spots avoid ladder/door cells. Only if this cannot coexist with the A7 double
  buffer / dirty-cell restore: (2) an entity slot with a "spirit" kind (needs NOCOLLIDE/NOTARGET
  tests in collision, melee, projectile: ≈ 15–20 resident B — reclaim needed), or (3) an ambient FX
  track (must not delay Phase 2, §2.2). Unblock: `z80-architect` reads the render/restore path.
- **F2 Log lines from RAM.** Token-expanded mentor lines must be queued into the 2-row log. If the
  panel queue only takes fixed string ids, the blob needs one "RAM string" message id (a 32-B
  buffer). Cheaper fallback: no tokens; lines name the default stick words (`DOWN`, `FIRE`) only,
  which still read correctly for every control source (worse for redefined keys).
- **F3 Opening the grate on a non-boss death.** The blob calls the existing boss-death grate-open
  routine when the Goblin slot dies. If that routine is inseparable from the BOSS path: make the
  Goblin's room record "lair guard = slot n" if the guard is slot-keyed, never set BOSS (it would
  make the hold and the scroll fail: bosses are immune to ASLEEP).
- **F4 Pool vs blob.** The D0 pool (hero + class FX + Goblin frames) must be allocated so it never
  overlaps the blob, and the blob's bank must be pageable for the far calls. Unblock: memory-map
  placement by staff.
- **F5 Depth 0 numerics.** Avoided by design: `DEPTH = 1` internally (§0). The only "0" is drawn by
  the blob (card + panel digit). End card after a (Mercy-prevented) D0 death would read DEPTH 1:
  accepted.

## 10. Playability checklist (for `test` / `run`)

1. Boot → menu → `1` → the choice screen appears; `2` → D1 exactly as today (golden screen).
2. `1` → D0: hero mid-ladder at room A's shaft top, mentor at A1, card `DEPTH 0`, panel digit 0,
   `FOOD = 40`, `DEPTH = 1`, `TUT_ON = 1`.
3. Scripted run (ZRCP input, `SEED_FIXED`) passes B0→B15 in order; each beat's trigger fires and
   its first line appears in the log; both classes.
4. Skip run: shortest route without reading/eating/drinking → grate shut until the Goblin dies,
   then open → D1.
5. **Reset equality:** hero state at D1 arrival after the tutorial == hero state at D1 arrival after
   `2 START` with the same fixed seed (byte compare of hero record, `ENT_STAT`, bag, counters,
   `FOOD`, `ARANK`, `TURN_COUNTER`).
6. After D1 entry: `TUT_AVAIL = 0`; death → menu → `1` → no choice screen, straight to D1.
7. Hold: in room C, 20 Waits at the door → Goblin `x` unchanged and ASLEEP; one hit → awake, chases.
8. Mercy: poke HP 3, Wait → HP = max, L50 in the log. A Goblin can never reduce HP to 0 in D0.
9. Death fallback (poke HP 0 path) → end card → menu → `1` → choice screen offered again, D0
   rebuilt identically (blob bytes unchanged: compare to the snapshot).
10. Blob integrity: throughout D0 (incl. bag page, room changes, the fight) the blob bytes equal the
    tape image.
11. Joystick-only (Kempston selected): the whole D0 incl. bag READ, quick FOOD/POTION/SCROLL and the
    Goblin fight is completable without the keyboard; lines show stick words.
12. Redefined keys (e.g. `W S K L M`): L02 reads `PRESS S TO CLIMB DOWN`; L60
    `ICONS: PRESS S+M AT ONCE`, L12 `PRESS M TO OPEN THE BAG`, L67 `LEAPS GO LEFT TOO: W+K` (R4 wordings).
13. No softlock: from every reachable D0 cell the grate is reachable by walk + climb (pit fall
    optional); the mentor never occupies or blocks a cell for movement.
14. The mentor never appears in the D1 pool / screen after the reset.
15. The goal is told: in the scripted run, L54/L55 appear in B1, and after the Goblin's death
    L56–L58 appear in the log before the hero, walking straight to the grate, steps into it.

**R2 additions (tests/tut0.py C16–C28; both classes unless noted; `SEED_FIXED`):**

16. **Name:** L05 decodes to `I AM BROTHER MORROW, LONG DEAD`; no decoded tutorial string contains
    `ALDOUS` or `SEXTON`; the choice-screen golden (`tut0_choice.hash`) is regenerated with
    `BROTHER MORROW WILL TEACH YOU`.
17. **Pointer yields:** in B3 after G0, the BAG rect cells have FLASH (bit 7); inject DOWN+FIRE →
    while `ICON_MODE ≠ 0` no attr in rows 18–23 (bank 5 and screen) has bit 7 set; after UP exits,
    still none (retired); after the B3 Nudge re-show the BAG FLASH is back.
18. **Icon tour:** first ICON MODE entry → I00a/I00b with `TV_HQ = 1` (hold); dismiss; rest on
    slot 1 for `REST_T` (12) hook calls → I01W/I01M; RIGHT + rest on each slot → its line. Lines
    seen per class before the book: Warrior {1, 4, 5, 7, 8, 9, 10}, Mage {1, 7, 8, 9, 10} (BAG = the
    B3 target pair instead of I10); after the read, slot 2 → I02W/I02M. A second rest on a said slot
    adds no line; RIGHT held through slots (repeat 4) adds no line for the slots passed. No tour
    line ever sets `TV_HQ` except I00 and the first target hold.
19. **Target:** B3, rest on BAG → L12/L61 with a hold; a second ICON MODE session, rest on BAG →
    L12/L61 again, no hold. B5 rest on FOOD → L73 (no hold); B13 rest on SCROLL → L73.
20. **Bag READ (joystick input only):** FIRE on BAG → page; stick to the book, FIRE, FIRE (READ)
    → `ARANK ≠ 0`, B3 G1 shown. The book's bag slot is taken from the bag contents, not hard-coded.
21. **Scroll both ways:** B13 run A: ICON MODE → SCROLL → FIRE → Goblin ASLEEP, L41. Run B (same
    snapshot): `I` / BAG → the scroll → READ → Goblin ASLEEP, L41.
22. **Pit:** B2 G0 = L65/L66 (hold), next turn L08/L09 (hold). Run A: walk right into `x = 19` →
    storey 1, HP −1..4 (or Mercy), group L69/L10, beat still B2. Run B: from `x = 16`, UP+RIGHT →
    `x = 22`, storey 0, G1 L67/L68 (no hold), beat B3 on the book pickup.
23. **WEAK:** after the eat, B5 tail L70/L71 (no hold). Rule check (the line must be true): poke
    `FOOD = 5` (WEAK) at `x = 16` storey 0 → UP+RIGHT: `x`, `TURN_COUNTER` unchanged, no log line;
    poke `FOOD = 15` (HUNGRY) → the same jump lands at `x = 22`.
24. **Nudge (R4):** at B4, Waits with the hero > 4 cols from the mentor → L75 + L16 (the goal) in
    one group on off-task turn 6; again on 18; nothing more up to turn 100. No L75 in B8, B12, B15, nor while the
    Goblin is awake.
25. **Left lesson:** skip the book and the pear, take the shaft → L76 once in B, before L24; going
    back up and down again prints no second L76.
26. **Joystick-only (Kempston), extends 11:** tour lines show stick words; the in-mode hold is
    dismissed by the stick and the dismissing input neither moves the cursor nor exits ICON MODE.
27. **Hook hygiene:** after D1 entry, after Quit, after death and after choice `2`, the `pi_ic`
    operand == `intent_icon7` and `pl_et` == `end_turn`.
28. **Budget:** blob `BLOB_LEN + BLOB_DELTA ≤ BLOB_RES` with ≥ 350 B free (R4 built: the R3
    reserve); `TUT_RAM_END ≤ PF_ROWF`;
    budget.py `tut0` unchanged CAP (the hook runs only in frozen ICON MODE ticks).

**R4 key clarity (TUT0-F4, tut0_split.md "Playtest round 2"; `tests/tut0.py` K1–K5):**

- **K1 prompt:** during a hold, row 20 cols 24–31 render `▶ ANY KEY` (font-match, KEYS and
  KEMPSTON); a non-control key (`Z`) dismisses; cols 24–31 blank / `$45` afterwards.
- **K2 names:** lint (`tests/tut_text.py`): no line starts with a token, all ≤ 32 (token 5, chord
  11). Runtime: default keys → L09 = `LEAP: PRESS Q+P AT ONCE`; FIRE redefined to CAPS / SYM →
  `CAPS` / `SYM`; Kempston → `LEAP: PRESS UP+RIGHT AT ONCE`.
- **K3 goal:** sampled after every turn and inside every hold: row 20 cols 0–23 == the beat's goal
  text with attrs `$45` whenever the model says it is shown (B0–B11 and B14 seen), through engine
  log lines, holds and ICON MODE sessions (back at the first turn end); hidden with the info attrs
  restored once the Goblin wakes (B12) and after the D1 reset.
- **K4 nudge:** idle in B2 → L75 + L09 at off-task turn 6 with FLASH on row 20 cols 0–23 that turn
  only, again at 18, nothing else up to 30.
- **K5:** no FLASH cell in row 20 cols 24–31 during any hold (B12 G0 incl.); rect 6 is 24 wide.

## 11. Open questions — RESOLVED (user 2026-11-09: all defaults approved)

**Architect round (user 2026-11-09, docs/design/tut0_split.md "Status"):** mentor = tile-id stamp
(cell-aligned; POINT's 2 px body shift is baked into the frame); each line group holds until a
keypress; talk = a pose on the next turn (the 16-tick blocking gesture in §4.3 is dropped); key
names = the 2-char REDEFINE names (§4.4 width rule: token = 2); D0 items pre-identified; the
"gate barred" line on entering C stays; reset shows DEPTH 1 + WELCOME.

User 2026-11-09: questions 1–6 below take their defaults. The mentor animates **once per
turn** (§4.3; no per-tick resident hook). Manager review notes for the architect: F1 must be
settled first (the background is redrawn from tile ids — a pixel stamp may not survive a
redraw); the "post-generation part of level entry" entry point may not exist yet (resident
estimate likely 30–50 B, not 16–20); consider holding each beat's log group until a keypress
so lines cannot scroll away unread.

1. **ENTER on the choice screen** = TUTORIAL (newcomer nudge)? *Default: yes.*
2. **Mentor identity:** "Aldous the Sexton", a ghost who stays in D0? *Default: yes.* **Superseded
   R2 (user 2026-11-09): Brother Morrow, a dead monk's shade (§4.1).**
3. **Mercy** (death impossible in D0) rather than real death → menu? *Default: Mercy.*
4. **Kill to leave:** the grate opens only when the Goblin dies (no fight-free exit except Quit /
   `2 START`)? *Default: yes.*
5. **HOW TO PLAY:** drop page 2, add the pointer line? *Default: yes.*
6. **Tape time:** ≈ +3.5–4 KB on tape ≈ +20–25 s of loading. Acceptable? *Default: yes (one load
   per session).*

## 12. Doc impacts (list only; not edited here)

- **game.md §1** run structure: add the D0 row (optional tutorial, once per load, sandbox, then D1);
  §1.1: D0 is hand-made and exempt from the generator/levelcheck sweep (rules still respected).
- **game.md §2.1** H1-ARRIVAL: applies to D0's room A shaft too.
- **game.md §3.2** main menu: START → choice screen while `TUT_AVAIL`; ENTER behaviour there.
- **game.md §3.2.1 + `instructions_screen.md`/`.txt`**: page 2 dropped, page 1 row 20 pointer line,
  "1/3" page counters become "1/2".
- **game.md §3.3–3.4**: mentor lines are blob-resident log lines with control tokens; panel FLASH
  pointer exception to "no FLASH".
- **game.md §3.4 end-card / STATS2**: D0 kills, items, books, turns are not counted (reset).
- **game.md §5**: the D0 book is a sandbox read; the D1 start-room book stays the Starter read.
- **game.md §9.1 / §9.2**: Goblin as a non-boss grate guard in D0 only (or the spirit kind if F1
  falls back to option 2).
- **game.md §11.2 budget**: blob row (boot-time pool, loaded once), resident +16–20 B.
- **memory-map.md**: blob placement in the boot-time pool, tape block (`tape_tab` / `BOOT6` sizes),
  `TUT_AVAIL`/`TUT_ON`, the two hook sites, D0 pool allocation fence (F4), mentor save buffer.
- **plan.md**: new TUT series: architect read (F1–F4 costs) → staff (hooks, blob framework,
  reset) → junior (beat table, text, level block, tests §10) → graphics-artist (7 mentor frames on
  the Design canvas, §4.2) → reviewer.
- **src/strings.txt / textpack**: a tutorial string block packed into the blob; page-2 help text
  removed.

## 13. Revision 2 (playtest 2, 2026-11-09)

Designer, 2026-11-09. Inputs: user playtest 2 requests 1–8 (rename, pointer vs cursor, icon
tour, bag steps, reading scrolls / the book, movement blocking, pits, WEAK-no-leap). Baseline:
the TUT0-F2 build (memory-map "TUT0-F2": holds only on flagged groups, dismiss on key down, log
rows pulse, prompt at row 20 cols 26–31, pointers toggle FLASH only). Everything not listed here
keeps its earlier decision.

### 13.0 Beat numbering: old → new

**Unchanged: B0…B15 map 1:1.** The icon tour is a *mode overlay* (it runs whenever ICON MODE is
open, §13.3), not a beat; the pit lesson extends B2; the bag / scroll steps extend B3 / B9 / B13;
the WEAK lesson is B5's tail; the Nudge replaces the Nag. No record is inserted, so the
overtaken-beat jump, `TUT_BF_FIRST`, tests C3 and the B11/B14 code paths keep their indexes.

### 13.1 Rename

Mentor = **Brother Morrow** (§4.1). Changed strings: L05, L06, TS_CHOICE3. Every other line is
already name-free and keeps the voice (CHILD in L47, L75). Art unchanged.

### 13.2 Pointer vs cursor (request 2)

Problem: a FLASHing pointer out-shouts the ICON MODE cursor (an inverse attr), so the player does
not see where DOWN+FIRE put the cursor. **Rule: the pointer says "where", once; the cursor says
"you are here", and only the cursor speaks in ICON MODE.**

- **P1** A pointer FLASHes only while `ICON_MODE = 0` (and the bag page is closed: the page covers
  the panel anyway).
- **P2** On the first icon-hook call of an ICON MODE session (§13.3) the blob clears every FLASH it
  set (`tt_ptr` off) and marks the current group's pointer **retired**: `tt_ptr_re` no longer ORs it
  back, and leaving ICON MODE does not restore it. This applies to every rect (BAG, FOOD, POTION,
  SCROLL, STATUS, BARS, ROW20) — one rule, no per-rect exceptions.
- **P3** A retired pointer returns only with a fresh show of its group (Nudge §13.5, or Repeat by
  Waiting near Morrow), which re-arms it.
- **P4** In ICON MODE the guide is the narration: the entry pair I00a/I00b names the lit icon as the
  current choice, and the slot / target lines name what the cursor is on (§13.3). So the "DOWN+FIRE
  selected the staff" moment reads `THE LIT ICON IS YOUR CHOICE`, then `STAFF: … OR WALK INTO A FOE`.

### 13.3 Interactive icon tour (requests 3, 4, 5)

**Hook.** ICON MODE costs no turn, so `blob_turn` never sees it. New SMC site **`pi_ic`** = the
operand of `ld hl, intent_icon7` in `intent_tick` (src/io.asm ≈ line 363, followed by `jp far7`).
While D0 runs (patched / undone together with `pl_et`) it points to a new low-RAM stub **`ts_icon`**:
`call intent_icon7` (bank 7 is already paged by far7) → `ld hl, blob_icon / ld c, BANK_BLOB /
jp farb`. Blob entry table gains **`+6 blob_icon`**. 0 resident B (stub ≈ 10 B in the stub room:
29 of 58 B used). Runs once per ICON MODE input tick, only in frozen play: no tick-budget impact.

**State (TUT_RAM, 4 B; `$5EDB..$5EDE`, ≤ `PF_ROWF`):** `TV_ISLOT` (last cursor slot, $FF = no
session), `TV_IREST` (calls on that slot), `TV_ISAID` (2 B: bit 0 = entry pair said, bits 1–10 =
slot line said; persists for the whole D0).

**blob_icon logic (per call):**
1. If `ICON_MODE = 0` (UP/DOWN/BREAK just exited) or `INTENT = IN_FIRE` (a use is pending, incl.
   opening the bag): `TV_ISLOT := $FF`, return. `blob_turn` (A = 0) also sets `TV_ISLOT := $FF`.
2. If `TV_ISLOT = $FF` → **session start**: retire pointers (P2); if entry pair not said, emit
   **I00a / I00b with a hold**, set bit 0. `TV_ISLOT := cursor slot`, `TV_IREST := 0`, return.
3. If the cursor slot ≠ `TV_ISLOT`: `TV_ISLOT := slot`, `TV_IREST := 0`, return.
4. `TV_IREST += 1`; when it reaches **`REST_T` = 12** (once per rest): pick the line (below), emit it
   as one group. Nothing on later calls of the same rest.

**Line choice on a rest (target first, then the generic slot line):**

| Beat current (and its G0 shown) | Target slot | Target group | Hold |
|---|---|---|---|
| B3 | 10 BAG | L12 `PRESS ‹F› TO OPEN THE BAG` · L61 `PRESS ‹F› ON BOOK, THEN READ` | first rest in B3 only |
| B5 (after G2) | 7 FOOD | L73 `THAT ONE. NOW PRESS ‹F›` | no |
| B9 (poisoned) | 10 BAG | L72 `PRESS ‹F›, THEN DRINK THE CURE` | first rest in B9 only |
| B11, B12 | 2 class power | L73 | no |
| B13 (after G0) | 9 SCROLL | L73 | no |

A target group is emitted on **every** rest on its slot (it is what the player needs right then);
it does not set the slot's said bit. Otherwise, if the slot's said bit is clear, emit its generic
line and set the bit; if set, emit nothing.

| Slot | Warrior | Mage | Reached in D0 when |
|---|---|---|---|
| 1 | I01W `SWORD: ‹F› OR WALK INTO A FOE` | I01M `STAFF: ‹F› OR WALK INTO A FOE` | always (the default selection) |
| 2 | I02W `POWER STRIKE: COSTS MANA, STUNS` | I02M `SPARK: FLIES THE WAY YOU FACE` | after the B3 read (unlearned = skipped by the cursor) |
| 3 | — (Whirlwind unlearned: skipped) | — (unlearned) | never |
| 4 | I04W `DAGGERS: ‹F› THROWS ONE AHEAD` | — (unlearned) | W: always (3 daggers) |
| 5 | I05W `BOW: FIND ONE, THEN ARROWS` | — (unlearned) | W: greyed `NO BOW`, selectable |
| 6 | — (blank gap) | — (unlearned) | never (silent if ever selectable) |
| 7 | I07 `FOOD: ‹F› EATS. MIND THE BELLY` | same | always |
| 8 | I08 `POTION: ‹F› DRINKS. HEAL FIRST` | same | always |
| 9 | I09 `SCROLL: ‹F› READS IT ALOUD` | same | always (greyed until the C scroll) |
| 10 | I10 `BAG: ‹F› OPENS IT. OR KEY I` | same | always |

- Data: `tut_tour` 10 B (slot → line id, $FF silent; slots 1 and 2 hold class-pair ids
  `TUT_CP_I01` / `TUT_CP_I02` in `tut_cpairs`, +4 B); `tut_tgt` 5 records × 4 B (beat, slot, line
  pair index / single id, flags: hold-first, needs-G0/G2-shown).
- **Holds:** only the entry pair (once per D0) and the two bag targets' first rest (the bag page
  hides the log, so these must be read before FIRE). All other tour lines scroll. An in-mode hold
  dismissal is swallowed: the dismissing input must neither move the cursor, exit the mode nor
  count as FIRE (STICK_OLD / FIRE_ST re-synced to the released state). No talk pose for tour lines
  (play is frozen; Morrow keeps his pose).
- **End:** a session ends with ICON MODE (exit or use) — nothing is printed on exit. The tour as a
  whole ends by exhaustion (each generic line once per D0); targets keep working in their beats.
  The tour is active in every beat, so a player who opens ICON MODE early gets it early.

### 13.4 Explicit bag, book and scroll steps (requests 4, 5)

Morrow cannot speak while the bag page is up (it covers the panel and log, §8 page rules), so the
inside-the-bag steps are said **before** FIRE opens it, on the BAG rest (held the first time).

| Task | Way | Steps (what the lines say) | Lines |
|---|---|---|---|
| Open the bag | ICON MODE | ‹D›+‹F› → ‹L›/‹R› to BAG → ‹F› (keyboard: `I` at any time) | L60, I00b, I10 / L12 |
| Read the book | bag only (no quick slot holds books) | open the bag → move to the book → ‹F› → verb strip READ (the default) → ‹F› | L11, L60, L12, L61 |
| Read a scroll, quick | ICON MODE | ‹D›+‹F› → to SCROLL (slot 9) → ‹F› (or a FIRE tap if SCROLL is already selected) | L40, I09, L73 |
| Read a scroll, bag | bag | open the bag → the scroll → ‹F› → READ → ‹F› | L63 (B3 tail), L61 pattern |
| Drink the Cure | bag (quick POTION picks Heal first) | open the bag → the Cure → ‹F› → DRINK → ‹F› | L30b, I08, L72 |
| Eat | ICON MODE or bag | FOOD (slot 7) → ‹F› | L19, L20, I07, L73 |

Both scroll ways fire B13 (the trigger is "Goblin ASLEEP"). The verb strip opens on its first verb
(READ / DRINK / EAT before DISCARD, §8 Q3), so "‹F› then ‹F›" is literally correct.

### 13.5 Movement blocking (request 6): **soft gating + nudges; no hard block**

| Option | Feel | Cost | Edge cases |
|---|---|---|---|
| Hard block (only the proposed action allowed) | rails; fights the roguelike's agency; a newcomer pressing a "wrong" key gets *nothing*, which reads as a bug (the same complaint as the silent WEAK jump) | a pre-turn input filter: a new hook in the intent path (bank 2 has 9 B free) + per-beat action masks + a "blocked" line: ≈ 150–250 B blob + 7–15 B resident | a monster attacking while the hero may only "eat" (must allow attack / flee); a fall or ladder state that makes the allowed action unreachable = softlock; ICON MODE / DOWN disambiguation (blocking DOWN breaks ICON MODE entry); every joystick path needs re-proving |
| Soft gating (as built) | free; the level's own gates (shaft, key → locked door, Goblin → grate) force the essential order; beats advance only on the right action; overtaken beats jump forward | 0 B | lessons in A (book, pear) can be skipped silently |
| Gentle nudges | a voice, not a wall; tolerates exploration | ≈ 30 B over the Nag (replaces it) + one line | must stay quiet in combat and in deliberately silent beats |

**Decision: soft gating + nudges** (the physical gates already guarantee the order that matters;
nothing new in the resident input path; no softlock class; joystick completeness untouched).

**Nudge rule (replaces the 60-turn Nag; R4 / TUT0-F4: at 6 and 18, one group L75 + the goal line,
FLASH on the goal line that turn, no next-turn re-show — the goal line carries the instruction):**
- `OFF` = turns since the current beat's last instruction group was emitted, counted at
  `blob_turn` A = 0 on turns that emit no group and do not fire the trigger (the existing nag
  counter). Reset on any group of this beat and on a beat change.
- At `OFF = NUDGE_T` (**12**): emit **L75** `CHILD. FIRST, DO AS I SAID` (scroll); next turn re-emit
  the instruction group (G0, or G2 for `G2PRE` beats once G2 was shown) **without a hold**, with its
  pointer re-armed (P3). At `OFF = 36` once more; then silent (Repeat by Waiting near Morrow still
  works).
- Suppressed: B8 (the trap must surprise), B12 and B15 (passive), any turn the Goblin is awake
  (B12–B13 combat; B13's G0 is distance-gated), and while a hold is up.
- **Left lesson:** on the turn the hero enters room B while the beat is in **B2–B5** (the overtaken
  jump skips book / ladder / food), emit **L76** `YOU LEFT A LESSON UNDONE ABOVE` (scroll) once per
  D0, before B7's G0 (same mechanism as FH_IMPATIENT's L53). The up-exit back to A is open; the
  skipped beats are not revived (the overtaken jump only moves forward) — the line is information,
  not a gate.

### 13.6 Pits and the WEAK no-leap rule (requests 7, 8)

**What room A already had:** a narrow pit `p = 19` (holes 19–21) between the book (col 24) and the
arrival half, B2 asking for ‹U›+‹R›, L10 on a fall. **Added:** what a pit is and that stepping in
drops a storey (B2 G0, held), the leap in both directions and that wide pits cannot be leapt (G1,
scroll), and that a fall hurts (FH_PITFALL group L69 + L10). Facts (§2.4, §2.5): a diagonal is
always a jump, `D = 6`; the hero falls iff his body is exactly over the holes (`x = 19` here, by
walking in or by a jump from `x = 13`); a fall drops to storey 1 at the same `x`, **1d4 damage,
ignores DEF** (Mercy covers it in D0); wide pits (W 4–6, D2+) cut the arc short and the hero falls.
Take-off `x = 14…18` lands safely (`x = 16` is the clean one).

**WEAK, stated exactly (§2.4 "Not when Weak", §7, §6.4; code `h_jump`, status7.asm):** the jump
is refused when the hunger **stage is WEAK (FOOD 0–9)** or the hero has the **WEAK status** (Mummy
curse, Archmage Drain). **HUNGRY (FOOD 10–24) does not block the jump** (the user's draft "A HUNGRY
CHILD CANNOT JUMP" would be false). The refusal is **silent: no turn, no log line, the hero does
not move** (there is no string). Hence L70 `AT WEAK YOUR LEGS WILL NOT LEAP` (the panel word reads
WEAK) and L71 `A LEAP THEN JUST DOES NOTHING`, as B5's tail right after the food lesson (L22 already
says "eat when it says HUNGRY"). **No scripted demonstration:** forcing FOOD ≤ 9 would apply the
real WEAK penalties and the faint clock, and the refused jump costs no turn, so the blob cannot
even observe the attempt (no end-of-turn) — a demo would leave the player pressing a dead key.

### 13.7 Hold flag per group (R2 complete list)

| Beat | G0 | G2 (pre/post) | G1 | Tail | FH / extras | Icon target |
|---|---|---|---|---|---|---|
| B0 | no (tt_init) | — | — | — | — | — |
| B1 | hold | hold | hold | L07 no | — | — |
| B2 | **hold** (L65/L66) | **hold** (L08/L09, G2PRE) | **no** (L67/L68) | — | L69/L10 no | — |
| B3 | hold (L11/L60) | — | hold (L13/L14) | **L63/L64 no** | L15 no | L12/L61 hold first |
| B4 | no | — | — | — | — | — |
| B5 | hold | hold | hold | **L70/L71 no** | — | L73 no |
| B6, B7 | no | — | — | — | — | — |
| B8 | (silent) | hold | hold | — | L29+L28 hold (code) | — |
| B9 | no | — | no | — | L32 no | L72 hold first |
| B10 | hold | — | — | — | — | — |
| B11 | hold | hold | — | — | L53 no | L73 no |
| B12 | hold | — | — | — | — | L73 no |
| B13 | hold | — | no | — | — | L73 no |
| B14 | — | hold | hold | G3–G5 hold | L48 / L52 no | — |
| B15 | — | — | — | — | — | — |
| Tour | I00a/I00b hold (once) | generic slot lines no | | | Nudge L75 + re-show no; L76 no; mercy first hold (code) | |

### 13.8 Budget

| Part | Raw B (E) |
|---|---|
| Text: +27 ids (15 beat + 12 tour) × ≈ 20.7 B, −L30, 4 rewordings ≈ 0 | ≈ +540 |
| Tables: `tut_tour` 10, cpairs +4, `tut_tgt` 20, `tut_tail` +8 (two pairs + ends, appended so B14's indexes 2–5 stay), tail-hold mask unchanged | ≈ +45 |
| Code: `blob_icon` (session / rest / said mask / target lookup / emit / in-mode hold glue) 180–220; pointer retire 20; Nudge over Nag +30; L76 20; FH_PITFALL pair + tail-after-G1 for G2PRE beats 20; `pi_ic` patch / undo 15 | ≈ +285–325 |
| **Total** | **≈ +870–910 B** (≤ 1,000 target); `BLOB_RES` free 1,767 → ≈ 860 |
| Resident | 0 B (SMC + stub room) · `TUT_RAM` +4 B (5 free) · tape ≈ +0.6 KB packed (≈ +4 s) |

### 13.9 Impacts (staff engineer)

- **tut_beats.asm (format):** no stride change. B2 record: G0 L65/L66, G1 L67/L68, G2 L08/L09,
  flags `G2PRE | H0 | H2`; FH_PITFALL emits the pair (L69, L10). B3: G0 L11/L60, `TAIL` with p3 =
  the new B3 tail index (ARANK has no params). B5: `TAIL` → L70/L71. **Semantics fix:** for `G2PRE`
  beats the tail follows **G1** (the last post-trigger group), not G2. B13: L40 text only. Append
  `tut_tail` pairs after index 5 (B14 keeps 2–5); the new pairs 6–9 never hold, so `tut_tail_hold`
  stays 1 B with pairs ≥ 8 treated as unheld (or widen to 2 B). New tables
  `tut_tour`, `tut_tgt`; `TUT_CP_I01`, `TUT_CP_I02`.
- **No new beat trigger (TK_*).** New *events*: `blob_icon` (session start, rest) — not TK kinds.
  New constants: `REST_T` 12, `NUDGE_T` 12, nudge repeat at 36, `TUT_TF_HOLD1` (target hold-first),
  `TUT_TF_AFTER` (target needs G0 / G2 shown).
- **Code areas:** `tut_stub.asm` (+`ts_icon`), `instr_ovl.asm` stub copy size, `tut_start.asm`
  (`pi_ic` patch next to `pl_et`; `blob_choice` undoes both), `tut_turn.asm` (`tt_reset` undoes
  `pi_ic`; `tt_ptr` retire flag, `tt_ptr_re` skips retired / ICON MODE; Nag → Nudge; L76 in the
  overtaken jump into B; `TV_ISLOT := $FF` each A = 0), new `blob_icon` (+6 entry). memory-map:
  TUT_RAM `$5EDB..$5EDE`, the SMC site, the stub length.
- **Verify (risks):** (1) `tt_hold` called from inside `intent_tick` → far7 → farb: stack depth,
  `present` / `resync_tick` legal there, the ICON MODE highlight and the `>` info line survive the
  prompt at row 20 cols 26–31 (TV_HA restore; R4: cols 24–31, constant `$45` restore, TV_HA gone); the swallowed key leaves `STICK_OLD` / `FIRE_ST`
  released. **Fallback if unsafe:** the bag targets and I00 scroll (no hold); they repeat on every
  rest anyway. (2) The log queue drains in frozen ICON MODE ticks (the info line does, so
  `panel_tick` runs); if not, `blob_icon` drains it like `tt_hold`'s pre-loop. (3) The cursor slot
  variable name / numbering (1–10 vs 0–9) for `tut_tour`.
- **Text / tools:** `tut_strings.txt` (new ids, L05/L06/L12/L40/TS_CHOICE3, delete L30),
  `tests/tut_text.py` widths, golden `tut0_choice.hash` regenerated; `game.md` §3.3–3.4 TUT0 notes
  name the mentor nowhere (no change); grep docs/tests for `ALDOUS` / `SEXTON` (strings only; asset
  labels may stay).

### 13.10 Open questions (defaults apply unless the user objects)

1. **Engine refusal line for the WEAK jump** (`TOO WEAK TO LEAP`, resident text + ≈ 6 B in
   `h_jump`): it is the real UX gap behind request 8. *Default: not in TUT0 (resident, outside the
   blob); proposed to the manager as a separate small task.*
2. **In-mode holds** (I00 + bag targets). *Default: hold; scroll fallback if staff finds the
   re-entrancy unsafe (§13.9 risk 1).*
3. **Nudge numbers** 12 / 36, then silent. *Default: yes.*
4. **L06 wording** `I TENDED THEIR GRAVES. NOW YOU`. *Default: yes* (alternative: `I PRAYED OVER
   THEM. NOW, YOU` = 30).


**Revision 2 approval (user 2026-11-09):** Q1 — the engine "TOO WEAK TO LEAP" line is a separate roadmap item after C (docs/plan.md 4b); Q2–Q4 take the designer defaults (hold inside ICON MODE with scroll fallback if unsafe; nudges at 12/36 turns; L06 as written). Gear & stats lesson → Tutorial v2 after C (plan 4c).

## 14. Revision 3 (adversarial tests, 2026-11-10) — PROPOSAL

Designer, 2026-11-10. **Status: proposal; §1–§13 are not edited until it is approved** (the in-place
edits are listed in §14.9). Baseline: the TUT0-F4 build (memory-map "TUT0-R2" + "TUT0-F4": holds,
nudges L75 at 12 / 36 off-task turns, nudge count skipped in B6 / B10–B12, Repeat = "Wait near
Morrow, nothing changed this turn", mercy at A = 1 and A = 0 with `MERCY_HP` 8; 719 B free in
`BLOB_RES`; `TUT_RAM` 1 B free). Evidence: `tests/tut0_adv.py` (33 scenarios + 22 random soaks,
15.6k inputs).

| # | Finding | Severity | §14 fix |
|---|---|---|---|
| F1 | Idle at B0: L01/L02 re-shown on every turn (290× each in 330 waits); L75 never fires (the Repeat resets the nudge count) | spam | §14.1 |
| F2 | Book discarded in B3 → beat stuck at 3 until the overtaken jump; L13/L14/L63 lost; no word from Morrow. Same for food / cure / scroll | stall | §14.2 |
| F3 | FOOD 40 runs out (~turn 240): one engine `YOU ARE HUNGRY`, Morrow silent | gap | §14.3 |
| F4 | HP 1 + a pit fall killed the hero (several damage sources in one `end_turn`) | **bug** (§5.3 promise) | §14.4 |
| F5 | Scroll read after the Goblin's death: L39/L41 unseen; L44/L46/L47 dropped at the grate step | content | §14.5 |
| F6 | Mentor box glitch at A2 (box col 26 row 1, over ladder L2 cols 26–28); row-20 prompt triangle (29,20) inside pointer rect 6 does not flash | src bugs (staff) | §14.6 |

Unchanged and confirmed good by the tests: holds, BREAK/pause resume, nudge volume (≤ 2 per run),
the Goblin chase, the free `NO NEED` cure refusal. Turn counts (skip route ≈ 66 turns to C, ≈ 82
to the kill, chase ≈ 103+) keep the §13.5 nudge numbers valid.

### 14.1 Repeat throttle (F1)

**Rule R3-REP** (replaces §3 "Always-on: Repeat"):
- **Trigger** as built (a turn on which nothing changed, hero within 4 cols of Morrow, no hold
  up, not B8 / B12 / B15, Goblin not awake) **plus**: never in **B0** (the hero is on the arrival
  ladder; nothing he can press there is a Wait — B0 is served by the Nudge alone).
- **Once per window:** a Repeat fires only if flag `TFB_REP` is clear, and sets it. `TFB_REP` is
  cleared by (a) any show of the beat's instruction group by the machine or the nudge's re-show,
  (b) a beat change, (c) `TV_NAG` reaching a multiple of 32.
- **A Repeat no longer resets `TV_NAG`** (the nudge schedule runs from the machine's last show; a
  player who idles by Morrow is off-task and gets L75 at 12 and 36).
- `TV_NAG` counts past 37 (was: saturates at 37) so (c) keeps working: after 255 it continues at
  64 (never re-crosses 12 / 36). Still not counted in B6 / B10–B12 or with the Goblin awake.
- State: 1 flag bit (a free `TV_FL` bit 6/7, else `TV_ISAID` bit 15). **0 B of `TUT_RAM`.**

Idle 330 turns at B0 (worst case, as tested): tt_init show + L75 / re-show at 12 and 36 = **3
shows + 2 × L75**, 0 Repeats (was 290). Idle 330 turns beside Morrow in B1+: ≤ 1 Repeat per window
→ shows at 0, 12, 36 + ≤ 2 early Repeats + ≤ 9 later (one per 32 turns) ≈ **14 shows** (was ≈ 290).

### 14.2 Lost lesson items (F2)

DISCARD destroys and costs **0 turns** (game.md §8 bag verbs), so it is never an event; the blob
**polls the loss** at the turn end, like every other trigger.

**Rule R3-LOST.** In beats B3, B5, B9, B13, after the beat's G0 has been shown, the lesson item is
**lost** when the bag holds no item of the lesson class **and** the D0 floor list holds none (the
placed item was taken and is gone). Classes: B3 any book (`ARANK = 0` still); B5 any food (the
pear **and** the kit Apple gone; one left = not lost); B9 a Cure, only while POISONED; B13 a Sleep
scroll. Detection = **the trigger fired with an alternate group**, so the beat's existing tail /
next-beat logic runs unchanged (§13.9: the tail follows the last post-trigger group).

| Beat | Lost group (Morrow TALK, **scroll, no hold**) | Then |
|---|---|---|
| B3 | **L77** `GONE? NO MATTER, CHILD` · L15 `NO BOOK? BELOW THEY ARE RARE` | tail L63 / L64 next turn ("EMPTY ICONS WAIT FOR BOOKS" now fits), → B4 |
| B5 | L77 · L22 `EAT WHEN IT SAYS HUNGRY` | tail L70 / L71, → B6 |
| B9 | L77 · **L78** `THE POISON WILL PASS. WAIT` | → B10 (the timer cures him; L31 skipped) |
| B13 | replaces G0 (L39 / L40): **L79** `NO SCROLL? THEN FIGHT ON` · L52 `KEEP SCROLLS FOR BAD FIGHTS`; no SCROLL target | B13 behaves as "Goblin dies first"; B14 skips its L52 extra |

B3's old fail text ("book DISCARDed unread: L15, advance") was never observable as an event; R3-LOST
is how it is implemented. Item consumed early (pear eaten, scroll read before B13) is not a loss for
B5 (`FOOD` rose = the trigger) and is a loss for B13 (no scroll left: L79 path) — both correct.
Cost: one bag scan by class + one floor-list scan, on those four beats only; data `tut_lost` 4 ×
4 B (beat, class, line 1, line 2) unless the beat record has a spare byte.

### 14.3 Hunger hint (F3)

**Rule R3-HUNGER** (event, any beat, once each per D0; polled level condition, so it simply waits
for a quiet turn): when `FOOD ≤ 24` (stage HUNGRY) and `TV_ISAID` bit 13 clear, or `FOOD ≤ 9`
(WEAK) and bit 14 clear → set the bit and emit (scroll, no hold, pointer **FOOD**):

| Condition | Group |
|---|---|
| HUNGRY, food in the bag | **L80** `YOUR BELLY CALLS. EAT NOW` · I07 `FOOD: ‹F› EATS. MIND THE BELLY` |
| WEAK, food in the bag | L80 · L70 `AT WEAK YOUR LEGS WILL NOT LEAP` |
| no food in the bag (either stage) | L80 · **L81** `NO FOOD? FIND SOME BELOW` (hunger never kills, §7; D1 resets FOOD to 80) |

Deferred while a hold is up, the Goblin is awake, or in B8 (the trap's silence). FOOD 40 ≈ 6 turns
per point → HUNGRY ≈ turn 96, WEAK ≈ turn 186: a player who skipped B5 hears it about when the
Goblin fight starts; a player who ate the pear never does. Turn priority: mercy > machine group >
lost group > hunger > nudge / Repeat (one group per turn, as §3).

### 14.4 Mercy: catch the death itself (F4)

**Why the threshold alone fails.** After every mercy check HP ≥ `MERCY_HP` + 1 = 9. Damage between
the A = 1 check and `end_turn`'s death check (`bank7.asm .dead`, which every hero death reaches:
`deal_hit` / `hero_fall` set `EF_DYING`; `tt_mercy` then refuses to act on a dying hero):

| Source (one `end_turn`) | Max | Notes |
|---|---|---|
| Goblin hit 1d4 | 4 | it may follow the hero to A / B once awake |
| DART 1d4+1 (DEF applies; DEF 0 worst) | 5 | re-arms; B storey 0 |
| pit fall 1d4 (ignores DEF; `do_exit`, lands between A = 1 and A = 0) | 4 | A only, exclusive with the dart |
| poison tick | 0 | never below 1 HP (§6.4) |
| **worst stack** | **9** (dart + Goblin) ≥ 9 → **HP 0** | fall + Goblin = 8 → HP 1 (no margin) |

Raising `MERCY_HP` to 10–12 would cover it on paper but makes mercy fire on most Goblin hits on the
Mage (max HP 16), erasing the "the HP bar visibly moves" lesson and L48, and stays brittle (HUNGRY
atk, any later tuning). **Decision: keep `MERCY_HP` 8 and add a death catch.**

**Rule R3-MERCY:** while D0 runs, a hero death is **revived at the death check**: `EF_DYING` off,
HP := max HP, `E_MODE` := M_REST, `E_REACT` := RC_NONE, `ST1_KILLER` := 0, this turn's
hunger step skipped (exactly the `DEBUG_KIT` revive, bank7.asm `.dead`, but HP := max not 1), and
`TFB_MERCY` set → tt_after shows L50 (+ L51 the first time, held) as for a threshold mercy. The
killing hit's HURT / DEATH reaction and its log line still play; Morrow's "ENOUGH. I MEND YOU"
follows. **No death is possible in D0 at all**, whatever the damage sum.

**Mechanism (0 resident B; staff may choose an equivalent):** a 4th SMC operand **`pd_dv`** = the
operand of `.dead`'s `call lect_back` (present whenever `TOME_FX` = 1, i.e. every release / tut0
test build) → new low-RAM stub **`ts_dead`** while D0 runs: drop `.dead`'s return address, far-call
the blob's revive (`blob_turn` A = 2 or a `+8 blob_dead` entry), `jp xp_turn`. Set / undone with
`pl_et` / `pi_ic` (tut_d0, blob_choice, tt_reset). Stub ≈ 12 B (stub area 37 → ≈ 49 of 58 B).
`TOME_FX` = 0 (trace builds only, which never run D0 suites): no site, threshold-only mercy.
Tests: I3 legal sets gain the 4th operand; I7 must now hold under a poked HP 1.

### 14.5 Scroll read after the Goblin's death; B14 drop (F5)

- **L39 / L40 / L41: nothing added.** B13 is a combat-timing lesson; once the Goblin is dead the
  scroll has no target and the engine's own read line is honest. Reading is taught three times
  elsewhere (L63, I09, L40 via the bar), and B14's L52 covers the unread case.
- **L44 / L45 (the core loop "find the key, slay the boss / its grate is your way down") must not
  be droppable:** **the blob opens the grate after G4 has been shown** (was: after G3; manager
  2026-11-09). One more held group before the exit; 0 B (a constant). G5 (L46 pause, L47) stays
  droppable — HOW TO PLAY page 1 carries the pause key.

### 14.6 Spot A2 and the row-20 prompt (F6, interaction notes for the staff fixes)

- **Move spot A2 from x = 25 to x = 22** (box cols 22–24, rows 1–6): clears ladder L2 (cols 26–28)
  by one column, so no ladder cell redraw can ever overwrite the stamp, which is cleaner than a
  render special case. Still right of the pit (POINT left at it, as before) and directly above the
  book at col 24 (POINT_DN). The hero's landing (`x = 22`, body 22–24) overlaps the box, as walking
  past A1 / A3 already does (V1 / V2 cover it). Staff: confirm the room-A decor seed has no feature
  in cols 22–24 rows 1–6; fallback x = 21.
- **Pointer rect 6 (ROW20) := row 20 cols 0–25.** The hold prompt owns cols 26–31 (§13 baseline);
  the pointer never FLASHes prompt cells. 0 B (rect data).

### 14.7 New lines (§8 rules: ≤ 32, token 5, chord 11)

| Id | Line | Width | Used by | Hold |
|---|---|---|---|---|
| L77 | `GONE? NO MATTER, CHILD` | 22 | R3-LOST B3 / B5 / B9 line 1 | no |
| L78 | `THE POISON WILL PASS. WAIT` | 26 | R3-LOST B9 line 2 | no |
| L79 | `NO SCROLL? THEN FIGHT ON` | 24 | R3-LOST B13 line 1 (with L52) | no |
| L80 | `YOUR BELLY CALLS. EAT NOW` | 25 | R3-HUNGER line 1 (with I07 / L70 / L81) | no |
| L81 | `NO FOOD? FIND SOME BELOW` | 24 | R3-HUNGER, nothing to eat | no |

Reused as second lines: L15, L22, L52, I07, L70 (no change). Death-catch mercy reuses L50 / L51
(first held, as built). §13.7 hold table gains: lost groups no · hunger no · Repeat no (as built).

### 14.8 Budget

| Part | Raw B (E) |
|---|---|
| Text: +5 ids × ≈ 20.7 B | ≈ +105 |
| R3-REP: B0 skip, window flag, no NAG reset, NAG wrap | ≈ +25 |
| R3-LOST: class scan of bag + floor, 4-record table, alternate G0 / G1 path, B14 L52 skip | ≈ +100–120 |
| R3-HUNGER: two FOOD thresholds, food-held test, 3-way group, FOOD pointer | ≈ +35 |
| R3-MERCY: revive ≈ 22, `pd_dv` set / undo ×3 ≈ 15 | ≈ +37 |
| Grate after G4, A2 x, rect 6 | ≈ 0–2 |
| **Total** | **≈ +300–345 B** (≤ 400 target); `BLOB_RES` 719 → ≈ 375–420 free |
| **R4 note (TUT0-F4, 2026-11-10):** R4 is built first: +248 B raw (estimate was +170–190), `BLOB_RES` 706 → **458 free**; R3 (≤ 345) still fits: R3 + R4 ≤ 706 holds with ≈ 110 B margin | |
| Resident | 0 B (stub area +≈ 12 B, boot-dead); `TUT_RAM` +0 B (flag bits only) |

### 14.9 In-place edits after approval (not made yet)

- §2.1 map + text: spot A2 `x = 25` → `x = 22`.
- §3 table: B3 / B5 / B9 fail cells → R3-LOST groups; B13 fail cell + L79 path; B14 "grate after
  G4" (replaces the manager 2026-11-09 G3 rule). Always-on: Repeat → R3-REP; Mercy → threshold +
  R3-MERCY death catch (drop the "cannot die" arithmetic, keep `MERCY_HP` 8); add R3-LOST and
  R3-HUNGER; one-group-per-turn priority order.
- §4.4: ROW20 rect = cols 0–25.
- §5.1 / §5.3: "it cannot kill the hero" / "Death: prevented by Mercy" → by the death catch; the
  "if it happens anyway" fallback text removed (kept only for `TOME_FX` = 0 builds).
- §8: L77–L81 rows; as-built totals. §9: 4th SMC operand `pd_dv`, stub `ts_dead`, blob entry.
- §10 checklist adds: (a) idle 330 turns at B0 → ≤ 3 shows of L01/L02 and exactly 2 × L75;
  (b) book discarded in B3 → next turn end L77 + L15, `TV_BEAT` = 4 after the tail; pear + Apple
  discarded in B5 → L77 + L22, beat 6; Cure discarded while poisoned in B9 → L77 + L78, beat 10;
  scroll gone before B13's G0 → L79 + L52 instead of L39 / L40, no second L52 in B14;
  (c) poked FOOD 24 → L80 + I07 with the FOOD pointer on the next quiet turn; FOOD 9 → L80 + L70;
  no food → L80 + L81; (d) poked HP 1 then a pit fall / dart + Goblin hit → `GAME_STATE` PLAYING,
  HP = max, L50 shown; 0 × GS_DEAD in D0 across the soak; (e) the grate opens only after G4;
  (f) V1 / V2 clean with Morrow at A2.
- §13.5 nudge counter semantics (Repeat does not reset it; wrap past 255); §13.7 hold rows.
- Staff / docs: memory-map TUT0 (flag bits, SMC operand, stub length), conventions "TUT0 boot
  stubs + SMC operands", `tut_strings.txt` (+5 ids), `tests/tut_text.py`, `tests/tut0_adv.py` I3 / I7.

### 14.10 Open questions (defaults apply unless the user objects)

1. **Death catch vs threshold only.** *Default: catch (§14.4); fallback if staff finds the
   `pd_dv` site unsafe: `MERCY_HP` 10 (covers 9 with HP ≥ 2 left; Mage mercy then fires at 6+
   damage taken).*
2. **Grate after G4** (one more held group before the exit). *Default: yes.*
3. **Repeat window 32 turns** after the nudges. *Default: yes.*
4. **B9 lost while poisoned advances at once** (rather than waiting for the timer to clear).
   *Default: advance at once.*
