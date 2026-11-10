# TUT0 work breakdown (architect, 2026-11-09; spec docs/design/tutorial_d0.md)

Status: APPROVED (user 2026-11-09). Spec-gap resolutions: (1) SMC operands + boot stubs, 0 resident B;
(2) bare D0 rooms only as fallback — try sparse-decor seeds first; (3) each line group HOLDS until a
keypress; (4) talk pose on the next turn, no 16-tick blocking gesture; (5) key names = the existing
2-char REDEFINE table (menu1.asm:649), no separate name table; (6) reset shows "DEPTH 1" + "WELCOME",
OK; (7) keep the "gate barred" line on entering C; (8) D0 potions / scroll are pre-identified; (9)
bookkeeping only. **Mentor art: the 3/4 VIEW (user 2026-11-09)** — assets/gfx/source/aldous/q34/
sxt34_*.grid, 7 right-facing frames, POINT needs no body shift. Blob data = 14 images, frame-major
(R then L): image index = 2 × frame + (left ? 1 : 0), frames IDLE1 IDLE2 TALK1 TALK2 POINT POINTDN
FADE = 0..6; the blob picks the facing (toward the hero). T8's pose byte must become the FRAME index
0..6 (T7 amends tut_beats.asm). Labels sxt34_<frame>_r / _l, `SXT34_IMAGES` EQU 14 (2,016 B raw).

## Verdicts (evidence)
- **F1 mentor rendering.** Pixel stamp dies on the first erase: erase redraws from the room's tile ids (`src/gfx.asm` erase_rect 217-308; memory-map.md bank-7 row, D3-S2). **Tile-id stamp:** 18 ids from 32..59; the blob writes their glyphs (TILE_GLYPHS $6600 + id·8), attrs ($05), flags (0), the ids into ROOM_MAP over T_AIR cells, then `rect_repaint` (lowram.asm:1066): attr shadow + restore queue; the next render redraws the box and repairs any sprite over it (logic.asm:908). A room rebuild drops him → the blob re-stamps in its after-turn handler (runs after do_exit). Constraint: D1 uses all 28 per-level ids (tilesets.asm:17) → the D0 seeds must use ≤ 10 distinct ids, or RD_SEED = 0 (bare, bank3.asm:643). Fallbacks (spirit entity, FX track) not needed.
- **F2 RAM log line.** `log_push`(HL = 0-terminated text, any bank paged) copies into LOG_TXT (panel_hot.asm:243-287); text format 32..127 literal, ≥128 = resident dictionary token. 0 resident B.
- **F3 grate on non-boss death.** far7 `grate_open.op` (boss7.asm:39-68): flag, T_GRATE ×3 + glow, rect_repaint, "gate gleams" line, no XP. D0 presets `LF_UNIQUE` (silences boss_chk boss7.asm:81 and trk_run trickle6.asm:36), LP_RESPAWNS = max.
- **F4 placement.** Bank 6's pool part is only $C000..$C7FF (SRC6_ADDR $C800 = R6 $D600 − 14 pages, defs.asm:45-67; boot block ≈ $C038..$C7FF) → no room. **BLOB in bank 4 at `BLOB_ORG $E800..$FFFF` (6,144 B).** The D0 pool (idles + hero + class FX + Goblin unit) ≤ the D2 Warrior's 22,304 B → ends ≤ bank 4 ≈ $E160. ASSERT via the existing pool simulation (PS_* macros) with a D0 unit set. Tape: the packed blob appended to the bank-0 text tape block after instr_zx0_end; the INSTR overlay copies it to the top of bank 4 via a PF_RAM bounce and ZX0-unpacks in place, at the overlay's common exit (BREAK skip too), before gen_idles overwrites bank 0. Once per power-on ("once per tape load"). The D1+ pool overwrites it; both patches are already undone by then.
- **Level entry.** `level_show` (lowram.asm:275) is the after-generation entry. Do NOT call `level_populate` (its lp_budget needs generator scratch, bank3.asm:438); the blob builds the hero itself (level_reset, level_start_x, init_ent_common, far6 pot_sync) then alloc_restore, far6 pool_list, gen_list, level_show(A=1, E=TX_NONE).
- **Reset.** Undo both patches, `ld sp, WORKSTORE_TOP` → `jp start_game` (C = HERO_KIND), as Quit (bank7.asm:1277). Exact START init → §10.5 equality by construction.
- **Resident.** 0 B in every ledgered region.
  - SMC operands in bank 2: `es_go` = enter_select's `jp start_game` (main.asm:558) → choice stub while the tutorial is available; `pl_et` = play_loop's `ld hl,end_turn` (main.asm:424) → turn stub while D0 runs.
  - Stubs (≤ 58 B) installed by the INSTR overlay over check_paging..str_lock (lowram.asm:123-145; tape-path only, dead after boot).
  - Turn stub ≈ `ld a,1 / call tfar / call end_turn / xor a / tfar: ld hl,blob_turn / ld c,BANK_BLOB / jp farb` (A=1 before end_turn, A=0 after; far7 already paged bank 7, farb restores it).
  - All D0 exits pass enter_select (death via end_screen, Quit); blob_choice undoes `pl_et` first.
  - Fallback if SMC rejected: plain flag-tested sites, 2 × 7 B in bank 2 + 8-B trampoline + 1 flag byte ≈ 14 B over bank 2's 9 free.
- **HOW TO PLAY page 2.** Frees ≈ 0.45 KB tape/boot-only bank-0 space (used by the blob's tape copy), 0 resident B.
- **Tick budget (estimate).** Before end_turn ≤ 1k T (mercy, exit check). After ≤ ~15k T (trigger poll ~3k, 2 lines ≈ 5k, 144-B glyph copy ≈ 3.5k + rect_repaint ≈ 2.5k, hold 0.3k, farb ×6 ≈ 1.5k); mentor repaint deferred if the tick is in its 2nd frame (SYS_FRAMES ≠ LAST_TICK_FRAME); the 18-cell restore (≈ 6k) lands in the next render. A D0 tick has 2 bodies vs 8 in blair/wroom. Gate: new budget.py scenario `tut0`, every tick ≤ CAP 126k work.

## Contracts shared by all tasks
- Bank 4 rules: blob code entered only via the stubs (farb, C = BANK_BLOB = 4); calls bank-3/1/6/7 via far3/far1/far6/far7 and every resident routine that pages via farb with C = BANK_BLOB; never pages $C000 itself; nothing assumed past D1's pool build.
- Blob entry table at BLOB_ORG: `+0 blob_choice` (from the choice stub; returns C = hero → start_game, or never returns), `+3 blob_turn` (A = 1 before end_turn / 0 after).
- Artist format (mentor, §4.2): images in order IDLE1, IDLE2, TALK1, TALK2, POINT_L, POINT_R, POINTDN, FADE (front-facing variant: 8; a 3/4 variant needs L+R per frame), each 24×48 1-bit, ink = 1, attr implicit $05, stored **cell-major** (cells row by row r 0..5, c 0..2; 8 B per cell top→bottom = one tile glyph; 144 B per image). Cell-aligned only — no sub-cell anchor offsets. File `assets/gfx/mentor/aldous.asm` (labels `sxt_*`), source next to it. All-blank cells allowed.
- Text ids: tutpack emits `TL_<Lnn>` EQUs (L01..L59, class pairs W/M, L30b) and `TS_*` (choice screen, card). Control tokens $01..$05 = U D L R F (expanded by the blob, never literal).
- Beat record (`TB_STRIDE` 16): +0 room, +1 trigger TK_*, +2/+3 params, +4 spot index ($FF stay), +5 pose | $80 blink | $40 fade-in, +6 G0 line pair, +8 G1 (on trigger), +10 G2 (next turn), +12/+13 pointer-rect ids (G0/G1, $FF none), +14 fail handler FH_*, +15 flags. Line id $FF = none; class pairs via a 2-entry W/M table. TK_* = STOREY(s), NEAR(cols), XGE(s,x), ARANK, FOOD_UP, ROOM(r), POISON, POISON_CLR, GOB_HURT, PASSIVE, GOB_ASLEEP(near cols), GOB_DEAD, EXIT. FH_* = PITFALL, BOOK_DISCARD, TRAP_PASSED, NOT_POISONED, IMPATIENT, VICTORY_EXTRAS. T7 may amend the format (and re-edits the table itself).

## Tasks

### T2 [junior] HOW TO PLAY: drop page 2, pointer line, 1/2 counters
Depends: none. Owns: docs/design/instructions_screen.txt/.md, tools/instr_pack.py, tools/gen_instr_mock.py, tests/instr.py, src/instr_ovl.asm (page count only), tests/game_lib.py (BOOT_WAITS).
Contract: pages = old 1 + old 3; page 1 row 20 = `NEW HERE? AFTER START, PICK 1 TUTORIAL` ($45); instr streams shrink; no resident change.
Acceptance: build clean; tests/instr.py, tape_layout.py, game.py #50 pass; DISPLAY new instr_zx0_end. Notes: GS_HELP2 may stay an unused EQU. Model: Sonnet.

### T1 [staff] Blob framework, memory map, loader, stubs
Depends: T2. Owns: src/defs.asm, src/main.asm, src/instr_ovl.asm, src/tut/tut_blob.asm (skeleton), src/tut/tut_stub.asm, tools/build.sh, docs/memory-map.md, docs/conventions.md.
Contract: BLOB_ORG $E800, BLOB_RES 6,144, BANK_BLOB 4; blob assembled at BLOB_ORG (MMU 3,4), ZX0-packed into the bank-0 text tape stream after instr_zx0_end (move tap_loader / OVL_RAW_ORG build scratch if needed). ASSERTs: packed stream fits; blob ≤ BLOB_RES; simulated D0 pool top < BLOB_ORG (new D0 unit set in PS sim); stub fits check_paging..str_lock. INSTR overlay common exit: bounce-copy + in-place unpack to bank 4, install stubs (DISP'd segment), patch `es_go`. SMC labels `es_go`, `pl_et` flagged `; SMC:`. Skeleton blob_choice = undo es_go, return C = HERO_KIND. Cost: boot +~0.3M T, play ticks 0.
Acceptance: build clean; game, instr, world, zx0_pool, gfx_integrity pass after T1b; memory-map ledger for every region (expected 0 B). Notes: stub bytes break #50's low-RAM compare after boot (mask, T1b); #61 must allow bank-4 PCs inside the blob. Model: Opus.

### T1b [junior] Harness updates for the blob
Depends: T1. Owns: tests/game_lib.py, tests/game.py, tests/tape_layout.py, tests/zx0_pool.py, tests/gfx_integrity.py.
Contract: `tut_off()` = poke es_go back to start_game after boot (default for legacy suites); #50 mask the stub range + blob bytes in bank 4 == image; #61 whitelist bank-4 PCs in BLOB_ORG..+BLOB_RES; tape_layout: bank-0 block = text + instr + blob.
Acceptance: full suite green on T1's build. Model: Sonnet.

### T3 [junior] Tutorial text + packer
Depends: none. Owns: src/tut/tut_strings.txt, tools/tutpack.py, tests/tut_text.py.
Contract: §8 lines + choice screen (3) + card (2) → build/tut/tut_text.asm: offset table + text packed with the resident dictionary (from the textpack output), TL_/TS_ EQUs; width check token = 5, chord = 11, ≤ 32; key-name table KEYTAB code → ≤ 5-char name + stick words.
Acceptance: tool self-check; tests/tut_text.py decodes every line via the getter algorithm; worst widths reported. Notes: 2- vs 5-char key names (gap 5). Model: haiku-eligible, else Sonnet.

### T4 [junior] D0 level block + spots tool
Depends: none. Owns: tools/tut0_level.py, tests/tut0_level.py.
Contract: build/tut/tut0_level.asm = byte images of LVL_STATE (16), EDGE_TAB (6), ROOM_DESC 9×16, TRAP_LIST, FLOOR_LIST (layouts from level_defs.asm / item_defs.asm via .sym/defs, not hard-coded), LF_UNIQUE set, grate shut; spot table (room, col, row-top) for A1 A2 A3 B1 B2 B3 C1 + grate spot; the 18 free tile ids; Goblin params (room C, x 22, storey 1). Seeds so decor in A/B/C uses ≤ 10 distinct ids 32..59 (tools/decorgen.py); if impossible emit RD_SEED 0 and say so.
Acceptance: tests/tut0_level.py: §1.1 rules (levelcheck), §10.13 reachability, every 3×6 spot box all T_AIR (room_model), clear of ladders/doors/items/drip columns, id budget. Model: Sonnet.

### T5 [junior] Mentor art converter + placeholder
Depends: none (final art: graphics-artist via the manager). Owns: tools/mentor_convert.py, assets/gfx/mentor/, tests/mentor_art.py.
Contract: artist grids/sheet → aldous.asm in the format above; placeholder silhouette until art arrives.
Acceptance: sizes, 144 B × N, ink-only. Model: haiku-eligible.

### T8 [junior] Beat table
Depends: none (format above; TL_ names per T3's rule). Owns: src/tut/tut_beats.asm.
Contract: 16 records B0..B15 per spec §3/§6; pointer-rect table (row, col, w, h) for BAG / FOOD / POTION / SCROLL / key icon cols 30-31 / status icon / row-21 bars / row 20 from memory-map "Panel (D5)"; W/M pair table.
Acceptance: assembles once T7 includes it; table-vs-spec review by reviewer. Model: Sonnet.

### T6 [staff] Choice screen + D0 start / level build
Depends: T1, T3, T4, T5 (placeholders OK). Owns: src/tut/tut_start.asm, src/tut/tut_blob.asm, tools/build.sh (wire T3/T4/T5).
Contract: blob_choice: undo `pl_et` first; choice screen via far1 mf_char + KBD_MATRIX poll via farb(menu_frame); release-first, 1/ENTER = tutorial, 2 = START, BREAK = `ld sp`/`jp enter_select`; "2" = undo es_go, return C. Tutorial: start_game head (gen_idles, far6 pool_hero, gen_list, alloc_mark, far7 new_game), FOOD 40; card "DEPTH 0 / THE OLD CRYPT"; write level block; hero (level_reset, level_start_x, init_ent_common, pot_sync, y 0, E_AIDIR 1); LP: kinds {Goblin}, boss none, quotas 0, respawns max; Goblin parked slot of room C, asleep, timer 15; item-identification init (investigate items_ovl); alloc_restore, pool_list, gen_list, GS_TRANSITION, level_show(1, TX_NONE), panel digit "0"; install 18 ids, stamp at A1, patch `pl_et`, play_go, `ld sp`, `jp play_loop`. Cold, ≈ the 2.2 s of a new game.
Acceptance: build clean; §10 items 1, 2, 6 (scratch ZRCP); D0 pool top < BLOB_ORG at runtime, both classes. Notes: every paging low-RAM call via farb with C = BANK_BLOB; confirm level_gen zeroes all of LVL_STATE. Model: Opus.

### T7 [staff] Turn engine (pre/post end_turn), mentor, hold, mercy, reset
Depends: T6, T8. Owns: src/tut/tut_turn.asm, src/tut/tut_beats.asm (format amendments only).
Contract: A = 1 (before end_turn): mercy HP ≤ MERCY_HP (8, or maxHP − 4; confirm Mage max HP) → HP = max, L50/L51; EXIT_KIND = EX_LEVEL → undo both patches, show_bank5, `ld sp`, `jp start_game`. A = 0 (after): triggers, overtaken beats, ≤ 1 group a turn → expand into buffer → log_push; repeat / nag (60 turns); panel FLASH pointers (bank 5 + screen-2 attrs); Goblin hold (ASLEEP timer 15 while HP = max and B11 not passed); Goblin dead → far7 grate_open.op (only after B14 G3 shown, spec §3); re-stamp after a room change; pose toggle (glyph copy + rect_repaint, skipped in a 2nd-frame tick); blink. T: before ≤ 1k, after ≤ 15k.
Acceptance: build clean; budget.py `tut0` ≤ CAP; §10 items 3, 7, 8, 13, 14, 15 pass. Notes: a blocking talk/blink loop must not erase over sprites (skip when a sprite footprint overlaps the box) and must resync_tick after. Model: Opus.

### T9 [junior] §10 test suite + budget scenario
Depends: T7, T1b. Owns: tests/tut0.py, tests/budget.py (scenario `tut0`), goldens (choice screen, D0 arrival).
Contract: §10 → C1..C15 (C3 both classes SEED_FIXED; C5 byte compare vs `2 START`; C10 blob == image at every check; C11 Kempston; C12 redefined W S K L M; C13 + T4 Python).
Acceptance: all pass; summary counts only. Model: Sonnet.

### T10 [junior] Doc sync
Depends: T7. Owns: docs/design/game.md (§1, §1.1, §2.1, §3.2, §3.3-3.4, §5, §9.1/9.2, §11.2). Acceptance: matches as built. Model: haiku.

## Order
Parallel at once: T2, T3, T4, T5, T8 (disjoint files). Then T1 → T1b. T6 after T1 + T3/T4/T5, then T7, then T9 + T10. Critical path: T2 → T1 → T6 → T7 → T9.

## Integration risks
- SMC invariant: a D0 exit path that skips enter_select would leave end_turn calling a dead blob. Known paths (death, Quit, reset, "2") covered; T9 C6/C9 test them.
- Every blob-called routine that pages $C000 must go via farb with C = BANK_BLOB; a direct call returns into the wrong bank.
- No items overlay in D0: identification / ITEM_RAM state must be consistent.
- Mentor cells vs drip7 / decor_tick / status marks / flying numbers / floor-item rows 9s+6..7: spots must avoid (T4 checks).
- Panel digit "0" may be overwritten by later panel redraws.
- Legacy tests start games via the menu: T1b's `tut_off` is mandatory.
- In-place ZX0 unpack needs a delta margin at the end of BLOB_RES.

## Spec gaps (for the designer / user)
1. SMC operands + boot-installed stubs (0 B) vs plain hooks (~23 B, needs a reclaim).
2. If no seed set leaves 18 ids free: bare D0 rooms?
3. Hold each line group until a keypress (2-row log)?
4. 16-tick blocking talk gesture → talk pose shown on the next turn instead?
5. Key names: 2 chars (REDEFINE table, menu1.asm:649) or ≤ 5 ("SPACE")?
6. Reset shows "DEPTH 1" + "WELCOME", no "YOU DESCEND DEEPER" / stinger: OK?
7. "Gate barred" line on entering C: keep (LVL_LAIR = C) or suppress?
8. Item identification of D0 potions / scroll.
9. §10.2's "TUT_ON = 1" becomes "the pl_et operand = the turn stub".

## Handover notes from the parallel junior tasks (manager, 2026-11-09)
- **T3 (text):** 68 ids (63 TL_ + 5 TS_), 1,883 B raw / 1,406 B packed (DW id table 136 B + streams 1,270 B),
  resident dictionary reused. Control bytes $01..$05 are NOT dictionary tokens: the blob's getter must
  test 1..5 BEFORE tk_get. TS_CHOICE1/2 include the digit + 2 spaces. Reset "WELCOME" = existing TX_WELCOME.
- **T4 (level):** seeds A $48F1 / B $95FB / C $0D58; decor uses ids 32..39 (8); **mentor ids 40..57**
  (`tut0_mentor_ids`). Spots (room, box-left col, map row): A1 (1,9,1) A2 (1,26,1) A3 (1,19,10) B1 (4,10,1)
  B2 (4,21,1) B3 (4,21,10) C1 (5,6,10) GRATE (5,26,10) — A2/A3/B3 shifted 1 col from the spec to clear the
  book / pear / ladder; GRATE spot is right of the grate. Copy only `TUT0_HDR_COPY` = 14 header bytes
  (MASTER_SEED is the game's). KEYROOM = B + RDF_KEY on B added by T4 (engine doesn't read them yet —
  T6 confirms how the key is placed). B–C edge LINK|DOOR|LOCK. No identification state exists in this
  build (§8.8 cut): nothing to apply. Test gaps: air row 9s+7 under a box; drips checked on the mentor's
  storey only.
- **T5 (art):** `assets/gfx/mentor/aldous34.asm`, `SXT34_IMAGES` 14, frame-major R/L (see Status).
- **T8 (beats):** 310 B; 12 encoding choices listed in the file header for T7 to confirm. Known bug: the
  key-icon pointer rect (row 19, col 30, w 2) also flashes the depth digit at (31,19) → T7 narrows it.
  Pose byte → frame index 0..6 for the 3/4 art (T7 amends).

## Playtest round 1 (user 2026-11-09, Fuse, release build)
Findings: (P1) torches flash with parts of the mentor image; (P2) the mentor half-disappears per turn
and stays partly erased while idle; (P3) unclear when the mentor speaks — no cue to look at the log;
(P4) the tutorial feels unresponsive. Joystick: lines already use UP/DOWN/LEFT/RIGHT/FIRE for
Kempston/Sinclair (tt_stick) and a stick input dismisses a hold.
P1+P2 → staff bug fix TUT0-F1 (tile-id / repaint root cause). **User decision: A + B for P3/P4:**
- A1 talk pose shown IMMEDIATELY when a group is emitted (not next turn), facing the hero;
- A2 the two log rows flash BRIGHT while a hold waits;
- A3 a blinking "▶ <FIRE|key>" prompt at the end of the last log line during a hold;
- B1 a hold is dismissed on key DOWN (the key is still swallowed — no turn starts from it);
- B2 only important groups hold: the first explanation of each control, the Tome lines (L54–L59),
  the grate lines; repeats, nags and short confirmations scroll without a hold (a per-group flag in
  the beat table).
Blob budget: lower BLOB_ORG if needed (D0 pool tops $D140 / $C5C0; keep the ASSERT margin).
Tests: tests/tut0.py gains visual checks V1 (mentor box == current pose on every sampled frame,
incl. after ~3 s idle) and V2 (no mentor fragments in animated decor cells).

## Review round 2 (T6+T7, 2026-11-09) — fix list for TUT0-F2 (with A+B above)
1. MUST: Goblin evicted on A→B→A (lpop3.asm:283-293 frees C's parked slot; tut_start.asm:252 TRK_PREV preset covers the first exit only) → at A=1 on any exit turn with EXIT_DEST ≠ C and beat ≤ B11, TRK_PREV := C. Test A→B→A→B→C: Goblin x + ASLEEP.
2. Mercy also at A=0 (tut_turn.asm:123-136; worst window 10 dmg vs 9 HP floor → Mage can die).
3. **User 2026-11-09: option (a)** — reword L24 (no key icon exists): e.g. `YOU HAVE THE KEY. ON TO THE DOOR`, drop the key pointer rect (and its ink-7 side effect / the depth-digit flash).
4. Build-time ASSERT: room C has no RDX_D exit and sits in a middle-row cell (the EX_DOWN-from-C grate rule).
5. Remove the bank-4 PC whitelist in tests/game_lib.py tick() (both loops hit select_tick now).
6. tools/build.sh: tutpack / tut0_level.py / mentor outputs go under the build's own `-o DIR`, not $ROOT/build/tut.
Then: re-review the F1 delta (mentor ids 43..59, N = 17, ANIM_LIST flame ids 40–42).
