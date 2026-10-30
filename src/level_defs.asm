;==============================================================================
; level_defs.asm — Stage 3B data contracts (B3B-1). EQUs + ASSERTs only: this
; file emits NO bytes. B3B-3: the engine runs on the geometry below (the PROTO
; STOREYS / STOREY_H / ROOM_ROWS / ROOM_CELLS / KT_MOD7 names are gone).
;
; INCLUDEd once, at the end of defs.asm. Every fixed address below is recorded
; in docs/memory-map.md "3B contracts" (the tables juniors code against).
; Design refs: game.md §1.1 / §1.2 / §2.1 / §2.5 / §3.3–3.5 / §8.5 / §9.1,
; concept-screen.md §3.1 / §3.3 / §5, plan.md "3B breakdown" D1–D10.
;
; Naming: the 3B geometry has permanent names (STOREY_COUNT, PLAY_ROWS…);
; B3B-3 switched the engine to them and deleted the PROTO ones.
;==============================================================================

;------------------------------------------------------------------------------
; D3/D4 geometry: 2 storeys x 9 rows (game.md §2.1), playfield rows 0–17,
; panel rows 18–23 (concept-screen §5).
;   storey s in {0,1}: air rows 9s .. 9s+7, floor row 9s+8 (8, 17).
;   s = 0 is the TOP storey; falling (pits) only leads to s = 1.
;------------------------------------------------------------------------------
STOREY_COUNT    EQU 2               ; (PROTO: 3 storeys)
STOREY_ROWS     EQU 9               ; 8 air + 1 floor (PROTO: 7)
STOREY_AIR      EQU 8               ; air rows per storey
FLOOR_ROW0      EQU 8               ; storey-0 floor (PLATFORM glyph, pit caps, ladder holes)
FLOOR_ROW1      EQU 17              ; storey-1 floor (row-17 ornament, down-exit hole / grate)
PLAY_ROWS       EQU STOREY_COUNT * STOREY_ROWS  ; 18 (PROTO ROOM_ROWS: 21)
PLAY_CELLS      EQU ROOM_COLS * PLAY_ROWS       ; 576 (PROTO: 672)
PANEL_ROW       EQU PLAY_ROWS       ; 18: first panel row (never stamped / scrolled)
PANEL_ROWS      EQU 6               ; rows 18..23
ICON_ROW        EQU 18              ; rows 18–19: 10 icons 24x16 (cols 3i..3i+2), depth/key cols 30–31
INFO_ROW        EQU 20              ; info line (6x8 text, 42 chars)
STAT_ROW        EQU 21              ; HP/MP/FOOD bars, hunger word, ammo
LOG_ROW         EQU 22              ; rows 22–23: 2-row log (cols 0–23) + worn gear (cols 24–31)
TEXT_ROW        EQU INFO_ROW        ; first text row tracked by HUD4_EXT / HUD4_PW
TEXT_ROWS       EQU 4               ; rows 20..23
                ASSERT FLOOR_ROW0 == STOREY_AIR && FLOOR_ROW1 == STOREY_ROWS + STOREY_AIR
                ASSERT PANEL_ROW + PANEL_ROWS == 24 && TEXT_ROW + TEXT_ROWS == 24
                ASSERT PLAY_CELLS <= MAP_BUF_LEN         ; 3B maps fit the 672-B map buffers
                ; MOD9/DIV9 (D3): KT_MOD9 / KT_DIV9 (defs.asm, n = 0..23, offsets
                ; $1A0/$1B8 where KT_MOD7/KT_DIV7 were); kind_tab $1D0..$1FF stays
                ; the 3F resistance spare.

;------------------------------------------------------------------------------
; D1 room grid: 3x3 cells, room id r = gy*3 + gx (0..8).
;   neighbours: left r-1 (gx > 0), right r+1 (gx < 2), up r-3 (gy > 0),
;   down r+3 (gy < 2). "Up" = the grid row above = reached by the up-exit
;   {c,0} (rows 0–7); "down" = by the down-exit hole {c,2} in row 17.
;------------------------------------------------------------------------------
GRID_W          EQU 3
GRID_H          EQU 3
GRID_CELLS      EQU GRID_W * GRID_H ; 9 room ids
ROOMS_MIN       EQU 7               ; game.md §1.1 (DFS tree, + 0–1 loop edge)
ROOMS_MAX       EQU 9
LEVELS          EQU 8               ; D1..D8 (LVL_DEPTH 1..8)
ROOM_NONE       EQU $FF             ; "no room" in LVL_KEYROOM / LVL_SANCTUM

; Features: every ladder, shaft and pit is a 3-col footprint c..c+2 identified
; by its LEFT col c (game.md §1.1 "Ladder/pit placement"). A col byte of 0
; means "none": every legal feature col is >= 1 (internal ladders 3..26).
FEAT_W          EQU 3               ; footprint width (ladder / shaft / pit holes)
FEAT_GAP        EQU 7               ; same-storey footprints: |c1 - c2| >= 7 (>= 4 clear cols)
LAD_COL_MIN     EQU 3               ; internal ladder {c,1}: c in 3..26
LAD_COL_MAX     EQU 26
PIT_CLEAR       EQU 3               ; pit: >= 3 clear cols on each side (game.md §1.1)
FEAT_TRIES      EQU 8               ; optional feature dropped after 8 seeded tries
BLOCK_W_MIN     EQU 2               ; dead-end block: 2–3 wall cols at an exitless edge
BLOCK_W_MAX     EQU 3
COL_NONE        EQU 0
                ASSERT LAD_COL_MAX + FEAT_W <= ROOM_COLS - 3   ; leaves the door/block cols 29..31
                ASSERT LAD_COL_MIN > COL_NONE

;------------------------------------------------------------------------------
; Room descriptor (D1): 16 B per room id, ROOM_DESC + r*16 (one page: H is
; constant, L = (ROOM_DESC & $FF) + r*16; ASSERTed). All 9 entries exist;
; RDF_PRESENT = 0 means the grid cell has no room. Written by the generator
; (B3B-7, == tools/levelgen.py B3B-6), read by build_room_map v2 (B3B-8),
; collision (B3B-5) and the decor deriver (B3B-9).
;------------------------------------------------------------------------------
RD_FLAGS        EQU 0               ; RDF_* below
RD_EXITS        EQU 1               ; RDX_* below (exit bits + L/R exit storey)
RD_UPCOL        EQU 2               ; up-exit shaft {c,0} left col (0 = none); == RD_DNCOL of r-3
RD_DNCOL        EQU 3               ; down-exit hole {c,2} left col (0 = none); == RD_UPCOL of r+3
RD_ARRCOL       EQU 4               ; D2+ start room: arrival shaft {c,0}, rubble-capped (0 = none)
RD_EXITCOL      EQU 5               ; lair: level-exit down-shaft {c,2} under the GRATE (0 = none)
RD_LAD1         EQU 6               ; internal ladder {c,1} left col (>= 1 per room: reachability)
RD_LAD2         EQU 7               ; 2nd internal ladder (0 = none)
RD_PITCOL       EQU 8               ; pit: left HOLE col p (holes p..p+2 in row FLOOR_ROW0,
                                    ;      caps at p-1 / p+3); 0 = none. Storey-0 floor only
                                    ;      (game.md §2.5), so no storey byte
PIT_W_NARROW    EQU 3               ; J1: pit width W (holes p..p+W-1) when L2_PITW = 0 (pit_w)
RD_BLOCK        EQU 9               ; dead-end block: RDB_* below (0 = none)
RD_SEED         EQU 10              ; word: room seed (decor re-derived from it; never 0)
RD_SPARE        EQU 12              ; 12..15: the L2 fields below + 1 spare (zeroed by the generator)
; L2 (game.md §1.1 "Mid-room block" / "Wide pit"; written by the generator's
; last pass, read by build_room_map, pit_w / pit_range, lp_cmap)
L2_PITW         EQU RD_SPARE + 0    ; wide-pit width W 4..6 (holes RD_PITCOL .. +W-1, caps p-1 / p+W);
                                    ;      0 = RD_PITCOL is the ordinary 3-col pit (PIT_W_NARROW)
L2_MIDB         EQU RD_SPARE + 1    ; mid-room block left col b, storey 0 only (0 = none): cols
                                    ;      b..b+w-1 rows 0..7 WALL, row 8 WALLF, RUBBLE at row 7
                                    ;      cols b-1 and b+w (both faces)
L2_MIDW         EQU RD_SPARE + 2    ; mid-room block width w 2..3
RD_STRIDE       EQU 16

; RD_FLAGS
RDF_PRESENT     EQU %00000001       ; the cell holds a room
RDF_START       EQU %00000010       ; DFS root: hero arrives here, 0 monsters
RDF_LAIR        EQU %00000100       ; farthest leaf with a horizontal tree edge: boss + level exit
RDF_DEADEND     EQU %00001000       ; tree leaf
RDF_KEY         EQU %00010000       ; key room (unused in 3B: no key, game.md §1.4)
RDF_SANCTUM     EQU %00100000       ; D8 Sanctum (unused in 3B)
RDF_SEEN        EQU %01000000       ; runtime: hero has entered (set by level code; free to use)
RDF_PRESENT_BIT EQU 0
RDF_START_BIT   EQU 1
RDF_LAIR_BIT    EQU 2

; RD_EXITS: an exit bit means "a room is connected that way" (grid edges only;
; the arrival shaft / level exit have their own col bytes and no exit bit).
; Horizontal exits sit on ONE storey; the storey bit must equal the
; neighbour's opposite storey bit (checker invariant).
RDX_L           EQU %00000001
RDX_R           EQU %00000010
RDX_U           EQU %00000100
RDX_D           EQU %00001000
RDX_LS1         EQU %00010000       ; left exit is on storey 1 (0 = storey 0)
RDX_RS1         EQU %00100000       ; right exit is on storey 1
RDX_L_BIT       EQU 0
RDX_R_BIT       EQU 1
RDX_U_BIT       EQU 2
RDX_D_BIT       EQU 3
RDX_LS1_BIT     EQU 4
RDX_RS1_BIT     EQU 5

; RD_BLOCK: width in bits 0–1 (0 = none, 2 or 3 cols), storey bit 6, side bit 7.
; Cols 0..w-1 (left) or 32-w..31 (right), rows 9s..9s+7 WALL + floor row
; 9s+8 WALLF; RUBBLE at its foot (row 9s+7, col w resp. 31-w).
RDB_WMASK       EQU %00000011
RDB_S1          EQU %01000000       ; block on storey 1
RDB_RIGHT       EQU %10000000       ; block on the right edge (0 = left)
RDB_S1_BIT      EQU 6
RDB_RIGHT_BIT   EQU 7

;------------------------------------------------------------------------------
; EDGE_TAB: the 6 HORIZONTAL grid edges, 1 B each. Edge index
;   e = gy*2 + gx  between room r = gy*3+gx and r+1  (gx in {0,1})
;   => right edge of r: e = r - gy ; left edge of r: e = r - gy - 1.
; Vertical connections need NO table: they carry no door/state (doors are on
; horizontal edges only, concept-screen §3.1); they are the RDX_U/RDX_D bits
; + RD_UPCOL/RD_DNCOL of the two rooms (invariant: same col).
; Byte = bit set; 0 = no connection. The door belongs to the CONNECTION:
; one byte, drawn in both rooms (cols 30–31 / 0–1 of the exit storey).
;------------------------------------------------------------------------------
EDGES_H         EQU 6
EG_NONE         EQU 0
EG_LINK         EQU %00000001       ; rooms connected (open passage unless EG_DOOR)
EG_DOOR         EQU %00000010       ; a door stands on the connection
EG_OPEN         EQU %00000100       ; door open (runtime: set by bump/opener, cleared by close)
EG_LOCK         EQU %00001000       ; locked: needs the level key (lair edge; never set in 3B)
EG_SEAL         EQU %00010000       ; sealed: opens on the Archmage's death (D8; never set in 3B)
EG_LINK_BIT     EQU 0
EG_DOOR_BIT     EQU 1
EG_OPEN_BIT     EQU 2
; States the task names: none = 0, open passage = LINK, closed door =
; LINK|DOOR, open door = LINK|DOOR|OPEN, locked = LINK|DOOR|LOCK,
; sealed = LINK|DOOR|SEAL.

; Door geometry (concept-screen §3.1): 2 cols at the room edge (0–1 / 30–31),
; on storey s: lintel WALL row 9s, arch row 9s+1, planks rows 9s+2..9s+7.
; Open = planks drawn as AIR, the arch stays.
DOOR_COLS       EQU 2
DOOR_ARCH_DY    EQU 1
DOOR_PLANK_DY   EQU 2
DOOR_PLANK_H    EQU 6

;------------------------------------------------------------------------------
; FLOOR_LIST (game.md §8.5): <= 32 entries x 4 B, FLOOR_N used (header).
; Entry: FL_ROOM bits 0–3 room id, bit 7 = storey 1; FL_EMPTY ($FF) = taken /
; free slot (pickups mark, never compact mid-level). FL_COL = item cell col;
; the row is the storey's standing row 9s+7. FL_ITEM = item type (IT_*,
; item_defs.asm; no ISTATE on the floor: m 0, 3E rev 6). FL_QTY = stack count.
; INVARIANT (T7; floor_pickup's pre-filter relies on it): every live entry of
; the current room shows on its cell (FL_COL, row 9s+7) in ROOM_MAP — the
; glyph (item_glyph, lowram.asm; 3E-T6) of the LAST live entry of that cell
; in list order, with its item_ink(type) (fl_attr) in the screen / attr shadow. Kept by build_room_map (stamps every entry), ap_stamp
; (re-stamps a cell after any pickup), decor landing on T_AIR only, and the
; 3E-T11 drops (drop_put, R6 pickup6.asm: a T_AIR cell only, then ap_stamp_a).
; Any new writer of an entry (§6.3 ammo landing) or of row 9s+7 must keep it. Checked: tests/gfx_integrity.py floor_check (D1..D8, entry + play).
;------------------------------------------------------------------------------
FLOOR_MAX       EQU 32
FL_STRIDE       EQU 4
FL_ROOM         EQU 0
FL_COL          EQU 1
FL_ITEM         EQU 2
FL_QTY          EQU 3
FL_ROOM_MASK    EQU %00001111
FL_S1           EQU %10000000
FL_S1_BIT       EQU 7
FL_EMPTY        EQU $FF
; FL_ITEM ids (IT_*): item_defs.asm (3E-T3; 1..3 keep their 3B / 3D values).
; A pickup writes ISTATE 0 into the bag (game.md §8.11 3E simplification).

;------------------------------------------------------------------------------
; Level state block — bank 5 low RAM, LVL_STATE..LVL_STATE_END (320 B), right
; above the fixed buffers (LOWRAM_END). Covered by the low-RAM fit ASSERT
; (main.asm) through LOWRAM_FREE_END = LOWRAM_END_3B. Not on tape (runtime).
;------------------------------------------------------------------------------
LVL_STATE       EQU LOWRAM_END      ; $6D40
; header, 16 B
LVL_DEPTH       EQU LVL_STATE + 0   ; 1..8 (0 = no level generated)          (test-observable)
LVL_SEED        EQU LVL_STATE + 1   ; word: level seed = f(MASTER_SEED, depth) (test-observable)
GEN_RNG         EQU LVL_STATE + 3   ; word: generator RNG (D9; NOT RNG_STATE)  (test-observable)
LVL_ATTR_FLOOR  EQU LVL_STATE + 5   ; ATTR_FLOOR[depth] (game.md §1.2)
LVL_ATTR_WALL   EQU LVL_STATE + 6   ; ATTR_WALL[depth]
LVL_START       EQU LVL_STATE + 7   ; start room id
LVL_LAIR        EQU LVL_STATE + 8   ; lair room id
LVL_KEYROOM     EQU LVL_STATE + 9   ; key room id (ROOM_NONE in 3B)
LVL_SANCTUM     EQU LVL_STATE + 10  ; D8 Sanctum room id (ROOM_NONE in 3B)
LVL_NROOMS      EQU LVL_STATE + 11  ; 7..9
LVL_FLAGS       EQU LVL_STATE + 12  ; LF_* below
FLOOR_N         EQU LVL_STATE + 13  ; FLOOR_LIST entries used (0..32)
MASTER_SEED     EQU LVL_STATE + 14  ; word: per game (FRAMES at START / SEED_FIXED)
LVL_HDR_LEN     EQU 16
EDGE_TAB        EQU LVL_STATE + $10 ; 6 B ($6D50..$6D55); $6D56..$6D5F spare
ROOM_DESC       EQU LVL_STATE + $20 ; 9 x 16 = 144 B ($6D60..$6DEF); $6DF0..$6DFF spare
FLOOR_LIST      EQU LVL_STATE + $C0 ; 32 x 4 = 128 B ($6E00..$6E7F, page-aligned)
LVL_STATE_END   EQU LVL_STATE + $140
; row-17 ornament glyphs (game.md §3.3: 8 fixed glyphs x 8 B, NOT tile ids,
; same on every level; read by build_room_map v2 AND the transition scrolls,
; which run without bank 3 — hence a fixed low-RAM home). Filled at boot.
ORN_GLYPHS      EQU LVL_STATE_END   ; 64 B ($6E80..$6EBF)
ORN_COUNT       EQU 8
ORN_MID_COL     EQU 14              ; wing_l skull_l skull_r wing_r at cols 14..17 (concept_r4)
ORN_MID_N       EQU 4               ; (glyph indices ORN_* = panel_orn.asm, bank 3)
;------------------------------------------------------------------------------
; LP — lazy monster population (game.md §9.4.1-9.4.7, user 2026-10-06). Per
; level: a budget header + ROOM_VISITS + 9 room records; the 16 entity slots
; hold only the current room's monsters. Built by lp_budget (bank 3) after
; level_gen, read / written by lp_bank / lp_enter on every room change.
; Runtime only, bank 5 (always mapped: ZRCP reads it directly).
;   record r = LP_REC + r * LR_STRIDE:
;     +0 LR_HDR   bit 7 LR_VISITED (0 = FRESH), bits 0-2 = count 0..4
;                 (FRESH: the quota, no entries; VISITED: entries used)
;     +1 4 x {LE_KIND, LE_HP}: kind row (bits 0-4) | LEK_GOLD | LEK_RESPAWN | LEK_BRED, exact hp
;------------------------------------------------------------------------------
LP_STATE        EQU ORN_GLYPHS + ORN_COUNT * 8   ; $6EC0
LP_KINDS        EQU LP_STATE + 0    ; 4 B: the depth's kinds (game.md §9.4 table order)  (test-observable)
LP_BOSS         EQU LP_STATE + 4    ; boss kind row | LEK_GOLD on the golden depths (3F-T5)
LP_TOTAL        EQU LP_STATE + 5    ; the table count incl. boss (tests / levelcheck)
LP_LVL          EQU LP_STATE + 6    ; hero LVL at level entry (§9.6 tier input, 3F)
LP_RESPAWNS     EQU LP_STATE + 7    ; trickle spawns this level (§9.5, RESPAWN_MAX; 3F)
LP_DISCARD      EQU LP_STATE + 8    ; units lost to the split / the sum cap / a full record (tests)
LP_RMAX         EQU LP_STATE + 9    ; ROOM_MAX[depth] (2 / 3)
LP_RNG          EQU LP_STATE + 10   ; word: the spawn stream's seed of the last entry (test-observable)
; lp_enter / lp_budget scratch (+12 .. +23)
LP_HX           EQU LP_STATE + 12   ; hero arrival col
LP_HS           EQU LP_STATE + 13   ;   ... storey
LP_HW           EQU LP_STATE + 14   ;   ... body width
LP_SIG          EQU LP_STATE + 15   ; sum weight of the room's units so far
LP_RECP         EQU LP_STATE + 16   ; word: the record being entered
LP_W            EQU LP_STATE + 18   ; unit body width
LP_GAPV         EQU LP_STATE + 19   ; arrival gap of the current try (LP_GAP / LP_GAP2)
LP_BEST         EQU LP_STATE + 20   ; boss: best distance + 1 (0 = none yet)
LP_BS           EQU LP_STATE + 21   ; boss: best storey
LP_BX           EQU LP_STATE + 22   ; boss: best col
LP_RES          EQU LP_STATE + 23   ; reservation: units still to roll x minW (lp_fit)
ROOM_VISITS     EQU LP_STATE + 24   ; 9 B: entries per room this level (spawn-stream input)  (test-observable)
LP_REC          EQU LP_STATE + 33   ; 9 records x LR_STRIDE                                   (test-observable)
LR_STRIDE       EQU 9
LR_HDR          EQU 0
LR_ENT          EQU 1               ; first entry
LE_KIND         EQU 0
LE_HP           EQU 1
LE_STRIDE       EQU 2
LR_MAX          EQU 4               ; entries per record (= ROOM_CAP)
LR_VISITED      EQU %10000000
LR_VISITED_BIT  EQU 7
LR_CNT_MASK     EQU %00000111
LEK_KIND_MASK   EQU %00011111
LEK_GOLD        EQU %00100000       ; golden boss (3F-T5, §9.7 R1): base row + this bit; hp 2 x scaled + 6, weight + 1
LEK_GOLD_BIT    EQU 5
LEK_RESPAWN     EQU %10000000       ; F_RESPAWN (§9.5): no drops, half XP (3F); = EF_RESPAWN (ASSERTed)
LEK_BRED        EQU %01000000       ; the once bit (3F-T9): a Rabbit Rat has bred (§9.6); = the entity's RCD_ONCE
LEK_BRED_BIT    EQU 6               ; (lp_bank writes it, lp_spawn restores it)
LP_LEN          EQU 33 + GRID_CELLS * LR_STRIDE  ; 114 B
LP_END          EQU LP_STATE + LP_LEN            ; $6F32
; budget constants (game.md §9.3 / §9.4.1)
ROOM_MAX_LO     EQU 2               ; D1-D2 monsters per room (initial population)
ROOM_MAX_HI     EQU 3               ; D3-D8
LP_SIGMA_INIT   EQU 8               ; sum weight cap of a FRESH room: max(8, ROOM_MAX x minW)
LP_SIGMA_CAP    EQU 12              ; §9.3 phase-2 cap: lair, follow admission, trickle
LP_TRIES        EQU 8               ; candidate cells per monster (§9.4.3)
LP_GAP          EQU 8               ; body gap to the hero's arrival box, arrival storey, tries 1-4
LP_GAP2         EQU 5               ;   ... tries 5-8 (designer decision 2026-10-06)
LP_XMIN         EQU 2               ; body cols 2 .. 29: clear of the door cells 0-1 / 30-31
LP_XMAX         EQU 29
; lp_enter's cell map (lp_cmap): 2 storeys x LP_CMW cols, bit 0 = a footprint
; (ladder / shaft / its end box, pit + caps, the storey-1 landing cols, the
; block), bit 1 = a body may not cover it (arrival box, the hero's 8-col gap
; zone, a body placed this entry). In NEXT_MAP's unused tail (rows 18..20 of
; the 672-B buffer): lp_enter runs before do_exit builds NEXT_MAP, and before
; any room exists at level start (GEN_SCRATCH's LG_* sit at $6000..$6051).
LP_CMW          EQU 33              ; cols 0..32 (a flyer's margin reaches col 32)
LP_CMAP         EQU NEXT_MAP + PLAY_CELLS        ; $6540..$6581
LPC_BAD         EQU 1               ; a body may not cover the col
LPC_BODY        EQU 2               ; 3F-T8 review: a body lp_spawn placed this entry (lp_legal ORs every bit;
                                    ; lp_post exempts only LPC_BAD marks of the exit's own footprint)
                ASSERT LP_CMAP + 2 * LP_CMW <= NEXT_MAP + MAP_BUF_LEN
RESPAWN_MAX     EQU 6               ; §9.5 trickle cap per level (3F)
                ASSERT LR_MAX * LE_STRIDE + 1 == LR_STRIDE && LP_REC == ROOM_VISITS + GRID_CELLS

LOWRAM_END_3B   EQU LP_END          ; = LOWRAM_FREE_END (defs.asm); test stubs run here

LF_GRATE_OPEN   EQU %00000001       ; lair grate open (3F-T8: set by grate_open when the boss dies; 3B: at level start)
LF_GRATE_OPEN_BIT EQU 0
LF_KEY_TAKEN    EQU %00000010       ; (3E+)
LF_SEAL_OPEN    EQU %00000100       ; (3F)
LF_GATE_HINT    EQU %00001000       ; B12 / 3F-T8: the first-lair-entry line ("THE GATE IS BARRED")
                                    ; logged this level (do_exit; level_gen rewrites LVL_FLAGS)
LF_GATE_HINT_BIT EQU 3
LF_UNIQUE       EQU %00010000       ; 3E-T11: the boss unique dropped this level (mon_drop)
LF_UNIQUE_BIT   EQU 4
LF_PROVOKED     EQU %00100000       ; 3F-T8 (§9.2 G2 PROVOKED): the hero's damage reached the lair boss;
LF_PROVOKED_BIT EQU 5               ; cleared when lp_post places the boss (every lair entry). ONE bit:
                                    ; one boss a level (the per-entity choice of the spec, engineer's call)

; B3B-12 level seed (game.md §1 "Seed"): LVL_SEED = MASTER_SEED + depth * LVL_SEED_MUL
; (16-bit). Additive with an ODD constant, NOT an XOR with depth * $0101: level_gen
; seeds GEN_RNG = LVL_SEED ^ (depth * $0101), so an XOR mix would cancel and give
; every depth of a game the same GEN_RNG (= MASTER_SEED). For a fixed depth the map
; master -> seed is a bijection (the whole 16-bit seed space is reachable, incl. the
; reseed-exhausting seeds), and the 8 depths of one game never share a seed
; (d * MUL mod 65536 differs for d = 1..8 because MUL is odd).
LVL_SEED_MUL    EQU $9E37           ; 2^16 / golden ratio, odd
                ASSERT (LVL_SEED_MUL & 1) == 1

                ASSERT LVL_STATE == LOWRAM_END
                ASSERT EDGE_TAB >= LVL_STATE + LVL_HDR_LEN
                ASSERT EDGE_TAB + EDGES_H <= ROOM_DESC
                ASSERT ROOM_DESC + GRID_CELLS * RD_STRIDE <= FLOOR_LIST
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + GRID_CELLS * RD_STRIDE - 1) >> 8)  ; one page
                ASSERT (ROOM_DESC & (RD_STRIDE - 1)) == 0
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE <= 256           ; one page
                ASSERT FLOOR_LIST + FLOOR_MAX * FL_STRIDE == LVL_STATE_END
                ASSERT LVL_STATE_END - LVL_STATE <= 320
                ASSERT (ORN_GLYPHS & 7) == 0
                ASSERT RD_SPARE + 4 == RD_STRIDE

;------------------------------------------------------------------------------
; Tile ids (8x8, attr = TILE_ATTRS[id]). 0..31 common (TILE_COMMON), 32..63
; per level (TILE_LEVEL_GLYPHS / _ATTRS, loaded from the bank-7 tileset slot).
; Existing ids KEEP their values (T_AIR..T_END_R in defs.asm, T_COUNT 21).
; Retired PROTO ids (T_POTION 10, T_CHEST_* 11–14, T_ZAP1/2 17–18) are reused
; by small decor ONLY after their last user is gone (B3B-13 / floor items off
; the tile path) — the aliases below share the value deliberately.
; Common-id budget is FULL (32/32), see docs/memory-map.md "3B contracts".
;------------------------------------------------------------------------------
T_WALL_DARK     EQU T_BRICK         ; 2: wall set DARK = the plain air-band wall face (re-glyphed, B3B-2)
T_PIT_R         EQU T_END_L         ; 19: pit right cap at p+3 = "floor cell right of a hole"
T_PIT_L         EQU T_END_R         ; 20: pit left cap  at p-1 = "floor cell left of a hole"
; new structural ids
T_DOOR_ARCH_L   EQU 21              ; door arch (row 9s+1), solid
T_DOOR_ARCH_R   EQU 22
T_DOOR_L        EQU 23              ; closed plank, left col
T_DOOR_R        EQU 24              ; closed plank, right col
T_DOOR_LOCK     EQU 25              ; plank-R with lock plate (locked / sealed; sealed attr $02)
T_GRATE         EQU 26              ; B12: the RAISED gate (variant B, ink $46) over the lair's
                                    ; open level-exit hole in row 17 (3 cells, 1 glyph; LADDER|HOLE)
T_GRATE_SHUT    EQU 13              ; 3F-T8 (§9.7 R2, BOSS-GUARD): the CLOSED gate over the lair's level
                                    ; exit while the boss lives (tiles_3f grate_shut, ink $07), TF_SOLID |
                                    ; TF_FLOOR; build_room_map stamps it after the deriver, grate_open
                                    ; swaps the 3 cells to T_GRATE when the boss dies
T_RUBBLE        EQU 27              ; block foot, arrival-shaft cap, ash of the Book
T_WALL_DITHER   EQU 28              ; wall set (concept-screen §3.3)
T_WALL_PATCH    EQU 29
T_WALL_FADE     EQU 30
T_FREE31        EQU 31              ; DEC2: free (was bones tile 3)
; B10 (user option B, designer 2026-10-03): open-door jambs on ids 11 / 14,
; non-solid, ink $06; cobweb / moss move to the per-level sets.
T_DOOR_JAMB_L   EQU 11              ; `#.#.....` x 8: the left arch's outer strokes, continued
T_CHAIN         EQU 12              ; small decor (valid after B3B-13)
; 3F-T8 (§9.7 R2): 13 = T_GRATE_SHUT (above); 15..18 = the D8 Sanctum lectern 2x2
; (TL TR / BL BR, TF_SOLID | TF_ATTACK: `id - T_LECT_TL < 4` is the attackable test;
; placed by T11 only)
T_LECT_TL       EQU 15
T_LECT_TR       EQU 16
T_LECT_BL       EQU 17
T_LECT_BR       EQU 18
T_DOOR_JAMB_R   EQU 14              ; `.....#.#` x 8
; 3E (game.md §8.11 Q1, user-approved glyphs): common 10 = T_TRAP (revealed trap plate).
; FLOOR1 (2026-10-26): the class glyphs 17 (AMMO) / 18 (PAGES) / 60..63 are no longer
; placed (floor items = T_ITEM + the 16x16 icon); 17 / 18 keep their glyph bytes, unused.
T_TRAP          EQU 10              ; ink $42 (type ink = T6)
; D3-7 T6: the B3B-13b drips (T_DRIP1/2) are no longer placed (the per-level
; sets have no free ids; "if they are ever placed": per-level decor).
T_COMMON_USED   EQU 32
T_LVL_BASE      EQU TILE_COMMON     ; 32: first per-level id
T_LVL_OBJ       EQU 60              ; 60..63: per-level slots 28..31 (the slot bytes still hold the
T_LVL_OBJ_N     EQU 4               ;   3E class glyphs, unreferenced); decor uses 32..59 only
; FLOOR1: the floor-item MARKERS, one id per item band row k (the 2x2 cells of a
; live FLOOR_LIST entry: cols c..c+1; k = 2s on row 9s+6, 2s+1 on row 9s+7).
; The only ids >= T_ITEM0, so erase_rect tests a cell with one compare; it draws
; them from the glyph cache (FI_CELL / FI_GLY / FI_INK), never their tile glyph.
T_ITEM0         EQU T_LVL_OBJ
                ASSERT T_COUNT <= T_DOOR_ARCH_L        ; new ids start after the live PROTO ids
                ASSERT T_COMMON_USED <= TILE_COMMON
                ASSERT T_FREE31 < TILE_COMMON
                ASSERT T_LVL_OBJ + T_LVL_OBJ_N == TILE_IDS

; TILE_FLAGS[64] (D2) bit meanings. The table itself is B3B-5 data:
; `tile_flags`, 64 B indexed by tile id, inside one 256-B page (B3B-5
; ASSERTs it), STATIC (per-level ids 32..59 = 0, 60..63 = TF_SOLID|TF_ATTACK).
TF_SOLID        EQU %00000001       ; blocks bodies + projectiles (walls, block, arch, closed planks, lectern)
TF_DOOR         EQU %00000010       ; closed door plank: bump opens it (hero / opener) unless TF_LOCK
TF_LOCK         EQU %00000100       ; locked or sealed plank: never opened by a bump without key / seal
TF_LADDER       EQU %00001000       ; climbable segment (LAD_*, HOLE_*)
TF_HOLE         EQU %00010000       ; floor-row cell passable vertically (HOLE_*; open grate -> HOLE_*)
TF_ATTACK       EQU %00100000       ; attackable tile object (lectern / Book, game.md §1.3)
TF_ANIM         EQU %01000000       ; animated decor: the deriver puts the cell in ANIM_LIST
TF_FLOOR        EQU %10000000       ; floor support (PLAT, WALLF, END/PIT caps, GRATE; not pit AIR)
TF_SOLID_BIT    EQU 0
TF_DOOR_BIT     EQU 1
TF_LOCK_BIT     EQU 2
TF_LADDER_BIT   EQU 3
TF_HOLE_BIT     EQU 4
TF_ATTACK_BIT   EQU 5
TF_ANIM_BIT     EQU 6
TF_FLOOR_BIT    EQU 7

;------------------------------------------------------------------------------
; Bank-7 tilesets (game.md §1.2/§11.2), MEM-RECLAIM w2a deduplicated format
; (tools/tiles_convert.py -> assets/gfx/tiles/tilesets.asm), one block at
; TSET_BASE (above the shadow attrs):
;   tset_slots  8 records x TSET_STRIDE (65 B), record = depth - 1 (PROTO: 0):
;               +TSET_GIDX 32 tset_pool indices of ids 32..63, +TSET_ATTRS 32
;               attrs, +TSET_FSET the tset_fsets index of their TILE_FLAGS
;   tset_fsets  TSET_NFSET x 32 B TILE_FLAGS sets of ids 32..63
;   tset_pool   TSET_NPOOL x 8 B distinct glyphs
; level_tiles7 (tiles7.asm, far7 from the low-RAM level_load_tiles) gathers
; one record into TILE_LEVEL_GLYPHS / TILE_LEVEL_ATTRS / tile_flags + 32.
; Cold data, one headerless tape block, never written at runtime.
;------------------------------------------------------------------------------
BANK_TSET       EQU 7
TSET_GIDX       EQU 0
TSET_ATTRS      EQU 32
TSET_FSET       EQU 64
TSET_STRIDE     EQU 65
TSET_BASE       EQU $FAA0           ; right above the shadow attrs (PROTO rows 0–20; 3B 0–17)
                ASSERT TSET_ATTRS == TILE_IDS - TILE_COMMON && TSET_FSET == 2 * TSET_ATTRS
                ASSERT TSET_STRIDE == TSET_FSET + 1   ; level_tiles7: slot * 65 = slot * 64 + slot
                ASSERT TSET_BASE >= SHADOW_ATTR + PLAY_ROWS * ATTR_STRIDE   ; (+3 PROTO rows of slack)
                ASSERT BANK_TSET == BANK_SCREEN7 && BANK_TSET == BANK_SHADOW

;------------------------------------------------------------------------------
; Bank-2 runtime RAM (D6/D8). Uncontended, always mapped, not in the image.
;------------------------------------------------------------------------------
; D8: BANK2_FREE $B200..$B7FF is now fully reserved:
; B3B-11b: FONT6 is PLANAR for the quad printer (print6): line l of char c
; (32..127) at FONT6 + (l >> 1) * 256 + c + (l & 1) * FONT6_WB, i.e. 4 pages,
; two 96-B windows per page (even lines at offsets 32..127, odd at 128..223),
; so a line's 4 chars are reached with `ld l, code` under one H. Built at boot
; by panel_boot from the char-major font6x8 (bits 1..0 masked off). Free in
; the planes: offsets 0..31 / 224..255 of each page; the last 32 B
; ($B5E0..$B5FF) start HOT_COPY.
FONT6           EQU BANK2_FREE      ; $B200
FONT6_FIRST     EQU 32
FONT6_WB        EQU 96              ; odd-line window: code + 96 (128..223)
FONT6_PAGES     EQU 4
HOT_COPY        EQU FONT6 + (FONT6_PAGES - 1) * 256 + FONT6_FIRST + FONT6_WB + 96   ; $B5E0
HOT_COPY_END    EQU BANK2_FREE_END      ; = SLOTREC
                ASSERT FONT6 == $B200 && HOT_COPY == $B5E0 && HOT_COPY_END == $B800
                ASSERT (FONT6 & $FF) == 0 && FONT6_FIRST + 95 + FONT6_WB <= 255
; (B3B-13..C3-7: ZAP_GLYPHS sat in the first plane hole FONT6+0..15; D3-0
; removed the zap: the plane holes are the 3D state homes, combat_defs.asm.)

; D6: the animated-decor lists, in the spare after the IM 2 vector table
; ($BC01..$BCBB, 187 B; the ISR starts at ISR_ADDR $BCBC). Each list = its
; count byte followed by up to 12 entries (one LDIR copies N2 + LIST2 over
; N + LIST). B3B-10: the occupancy test is direct (decor_tick tests a due cell
; against the drawn SLOTREC footprints, ~50-90 T per sprite, only for the <= 3
; cells tested per tick), so the B3B-1 OCC_MASK (72 B, cleared + rebuilt per
; tick: ~0.9k + ~0.5k per sprite) was dropped; its bytes hold ANIM_N2/LIST2.
; D3-8b: the decorative drip (game.md §6.4.1 "Decorative drip"; src/drip.asm
; bank 2, src/drip7.asm bank 7) in the 15-B spare $BC01..$BC0F (bank 2,
; uncontended; runtime only). Test-observable.
DRIP_ST         EQU $BC01           ; DRS_* (0 idle: waiting DRIP_T ticks for the next drop)
DRIP_T          EQU $BC02           ; first-frame ticks to the next step (>= 1)
DRIP_COL        EQU $BC03           ; the drop's cell (ld bc, (DRIP_COL): C = col, B = row)
DRIP_ROW        EQU $BC04
DRIP_DRAWN      EQU $BC05           ; 1 = its glyph is on the bank-5 screen at DRIP_COL / ROW
DRIP_N          EQU $BC06           ; sources in CUR_ROOM (0..DRIP_SRC_MAX; 0 = no drip here)
DRIP_RND        EQU $BC07           ; own 8-bit LFSR (never 0): the game RNG is never touched
DRIP_SRC        EQU $BC08           ; DRIP_SRC_MAX x (col, row) of the room's sources
DRIP_SRC_MAX    EQU 2
DRS_IDLE        EQU 0
DRS_FORM        EQU 1               ; the hanging drop (old T_DRIP1) at the source
DRS_DROP        EQU 2               ; let go (old T_DRIP2) at the source
DRS_FALL        EQU 3               ; the drop alone, one cell down per tick
                ASSERT DRIP_SRC + 2 * DRIP_SRC_MAX <= ANIM_N2 && DRIP_ST >= ISR_VEC_TABLE + ISR_VEC_LEN
                ASSERT DRIP_ROW == DRIP_COL + 1
ANIM_N2         EQU $BC10           ; B3B-10: entries of the NEXT_MAP build's list
ANIM_LIST2      EQU ANIM_N2 + 1     ;   ($BC11..$BC40): do_exit (room_shadow) copies it
ANIM_N          EQU $BC5F           ; ANIM_LIST entries used (0..12)
ANIM_LIST       EQU $BC60           ; 12 x 4 B = 48 B ($BC60..$BC8F)
ANIM_MAX        EQU 12
AL_STRIDE       EQU 4
ANIM_COPY_LEN   EQU 1 + ANIM_MAX * AL_STRIDE   ; count + entries (49 B)
AL_COL          EQU 0
AL_ROW          EQU 1
AL_TYPE         EQU 2               ; 1..15 attr-cycle kind (1 flame); >= 16 glyph swap:
                                    ;   the OTHER tile id (decor_tick swaps it with the map cell)
AL_PHASE        EQU 3               ; tick counter (initial value = stagger (col+row)&7 of the
                                    ;   object): steps when & 3 == 0 (glyph swaps / drips: & 15 == 0, i.e. they
                                    ;   hold 16 ticks), cycle index = bits 4..2
AL_GLYPH_MIN    EQU 16              ; AL_TYPE >= this: glyph swap
                ASSERT ANIM_N2 > ISR_VEC_TABLE + ISR_VEC_LEN - 1
                ASSERT ANIM_LIST2 + ANIM_MAX * AL_STRIDE <= ANIM_N && ANIM_LIST == ANIM_N + 1
                ASSERT (ANIM_N2 >> 8) == (ANIM_N >> 8)
                ASSERT ANIM_LIST + ANIM_MAX * AL_STRIDE <= ISR_ADDR
                ASSERT (ANIM_LIST >> 8) == ((ANIM_LIST + ANIM_MAX * AL_STRIDE - 1) >> 8)

;------------------------------------------------------------------------------
; State block, 3B sub-range $BFD0..$BFFF (A8 owns $BFC0..$BFC3; $BFC4..$BFCF
; stays general spare). Test-observable.
;------------------------------------------------------------------------------
STATE_3B        EQU $BFD0
PANEL_DIRTY     EQU $BFD0           ; D5 queue bits PD_* (one item drained per non-input tick)
HUD4_EXT        EQU $BFD2           ; 4 B, rows 20..23: ink extent (replaces HUD_EXT in B3B-11)
HUD4_PW         EQU $BFD6           ; 4 B, rows 20..23: cols changed since present (replaces HUD_PW)
LOG_QN          EQU $BFDA           ; pending log messages in LOG_Q
LOG_Q           EQU $BFE0           ; 8 B: pending log messages (layout: B3B-11)
LOG_Q_LEN       EQU 8
STATE_3B_END    EQU $C000           ; $BFFC..$BFFF spare ($BFFB SEQ_TRAP, defs.asm; 3E-T16: TRP_PRE $BFF5, TRP_WAIT $BFF7, TRP_EV/STEP/ENT $BFF8..$BFFA, item_defs.asm; $BFF4 3E-T0 SFX_XP; $BFF3 SND-5 SFX_NEXT; $BFF1/$BFF2 SND-3 DNG_*; C3-0: JOY_MIRROR $BFEA, hero_defs.asm; C3-2b: EXIT_LOCK $BFD1, FIRE_LOCK $BFDF; SND-2: sound mailbox SND_MODE $BFEB..SFX_REQ $BFF0, defs.asm)
                ASSERT SND_MODE == JOY_MIRROR + 1 && SFX_REQ == SND_MODE + 5 && SFX_REQ < STATE_3B_END
                ASSERT DNG_DWELL == SFX_REQ + 1 && DNG_CALM == DNG_DWELL + 1 && SFX_NEXT == DNG_CALM + 1 && SFX_NEXT < STATE_3B_END
                ASSERT MUS_REQ == SND_MODE + 1 && MUS_SHOT == MUS_REQ + 1 && MUS_STATE == MUS_SHOT + 1 && MUS_CUR == MUS_STATE + 1
                ASSERT AY_CALLS + 2 <= STATE_3B
                ASSERT HUD4_PW == HUD4_EXT + TEXT_ROWS
                ASSERT (HUD4_EXT >> 8) == ((HUD4_PW + TEXT_ROWS - 1) >> 8)
                ASSERT HUD4_PW + TEXT_ROWS <= LOG_QN && LOG_QN < LOG_Q
                ASSERT LOG_Q + LOG_Q_LEN <= STATE_3B_END

; PANEL_DIRTY bits (D5): set by logic, drained one per tick, never in the
; input tick (game.md §3.3). Logic reads real values, never the panel.
PD_HP           EQU %00000001       ; HP bar + number
PD_MP           EQU %00000010       ; MP bar + number
PD_FOOD         EQU %00000100       ; FOOD bar + hunger word
PD_AMMO         EQU %00001000       ; Warrior ammo (row 21 cols 24–31)
PD_LOG          EQU %00010000       ; log: scroll 23 -> 22 + newest line (LOG_Q non-empty)
PD_ICONS        EQU %00100000       ; icon states (select / grey)
PD_INFO         EQU %01000000       ; info line
PD_DEPTH        EQU %10000000       ; depth + key icon (cols 30–31, rows 18–19)

;------------------------------------------------------------------------------
; B3B-11 panel engine (concept-screen §5, game.md §3.3–3.5; src/panel.asm).
;------------------------------------------------------------------------------
; State bytes in the 3B sub-range (test-observable):
PANEL_HP_SH     EQU $BFE8           ; 2 B: hero HP, MAXHP last drawn ($FF = never: forces PD_HP)
PANEL_POT_SH    EQU $BFDB           ; hero potions last drawn ($FF = never: forces PD_ICONS)
P_NUMBUF        EQU $BFDC           ; 3 B: num2 / depth text ("NN", 0)
                ASSERT E_MAXHP == E_HP + 1          ; one 16-bit poll / store
; LOG_Q layout (8 B): the ring of pending messages is LOG_TXT; LOG_QN counts them.
; One message = one panel item (scroll + whole line, B3B-11b).
LQ_RD           EQU 0               ; ring slot of the oldest pending message (0..LOG_SLOTS-1)
LQ_DROP         EQU 1               ; saturating count of messages dropped / replaced (ring full; expect 0)
                ASSERT LQ_DROP < LOG_Q_LEN
; Message text ring: bank-5 printer buffer (runtime-only RAM, free after boot;
; contended, but read once per char).
LOG_TXT         EQU $5B00           ; LOG_SLOTS x LOG_SLOT_LEN, page-aligned
LOG_SLOTS       EQU 4
LOG_SLOT_LEN    EQU 64              ; slot = LOG_TXT + idx * 64 (idx rrca rrca)
LOG_MAX         EQU 32              ; chars per message (game.md §3.4), + 0 terminator
LOG_COLS        EQU 24              ; log text cols 0..23 (32 chars x 6 px = 192 px)
                ASSERT (LOG_TXT & $FF) == 0 && LOG_SLOTS * LOG_SLOT_LEN <= 256
                ASSERT LOG_MAX * 6 == LOG_COLS * 8 && LOG_MAX < LOG_SLOT_LEN
                ASSERT LOG_SLOTS == 4 && LOG_SLOT_LEN == 64     ; slot address = idx rrca rrca
                ASSERT (P_NUMBUF >> 8) == ((P_NUMBUF + 2) >> 8)
; Row 21 fields (concept-screen §5): label cell, 32-px bar (4 cells), number (2 cells)
HP_LBL_COL      EQU 0
HP_BAR_COL      EQU 1
HP_NUM_COL      EQU 5
MP_LBL_COL      EQU 7
MP_BAR_COL      EQU 8
MP_NUM_COL      EQU 12
FOOD_LBL_COL    EQU 14
FOOD_BAR_COL    EQU 15
HUNGER_COL      EQU 19              ; hunger stage word, cols 19–23
BAR_CELLS       EQU 4
GEAR_COL        EQU 24              ; worn gear 4 x 16x16, cols 24–31, rows 22–23
DEPTH_COL       EQU 30              ; "Dn", row 18
ICON_SLOTS      EQU 10              ; slot i at cols 3i..3i+2, rows 18–19
ICON_W          EQU 3
ATTR_P_HP       EQU $42
ATTR_P_MP       EQU $45
ATTR_P_FED      EQU $44             ; FOOD bar + stage word per HSTAGE (game.md §7; 3E-T9 item_food,
ATTR_P_OK       EQU $46             ;   hunger6.asm hg_attr): FED / OK / HUNGRY / WEAK
ATTR_P_HUNGRY   EQU $42
ATTR_P_WEAK     EQU $42
ATTR_LOG_OLD    EQU $07             ; row 22
ATTR_LOG_NEW    EQU $47             ; row 23
ATTR_P_GREY     EQU $07             ; greyed slot (concept-screen §5 icon states)
ATTR_P_SEL      EQU $08             ; OR: selected slot = PAPER blue
                ASSERT LOG_ROW + 1 == 23 && (LOG_ROW & $18) == (23 & $18)   ; rows 22/23 share a bitmap third
PD_HP_BIT       EQU 0
PD_MP_BIT       EQU 1               ; D3-9b: item_mp (icons.asm); also polled (MP vs MP_SH)
PD_FOOD_BIT     EQU 2               ; 3E-T9: item_food (hunger6.asm, R6; 1st frame only)
PD_LOG_BIT      EQU 4
PD_ICONS_BIT    EQU 5
PD_INFO_BIT     EQU 6
PD_DEPTH_BIT    EQU 7
                ASSERT PD_HP == 1 << PD_HP_BIT && PD_LOG == 1 << PD_LOG_BIT
                ASSERT PD_ICONS == 1 << PD_ICONS_BIT && PD_DEPTH == 1 << PD_DEPTH_BIT
                ASSERT PD_INFO == 1 << PD_INFO_BIT && PD_MP == 1 << PD_MP_BIT && PD_FOOD == 1 << PD_FOOD_BIT
; C3-3 info line fields (game.md §3.4: name chars 0-15, numbers 16-27, notes 28-41)
INFO_NUM_COL    EQU 12              ; char 16 = 96 px
INFO_NOTE_COL   EQU 21              ; char 28 = 168 px
ATTR_INFO_NAME  EQU $47
ATTR_INFO_NUM   EQU $46
ATTR_INFO_NOTE  EQU $45
ATTR_LVL        EQU $46             ; the level digit at (31, 19) (game.md §4.1)
