;==============================================================================
; main.asm — WazHack/ZX engine entry point.
;
; Target : ZX Spectrum 128K
; Origin : $8000 (see docs/memory-map.md)
;
; P3 — the heartbeat: read input -> resolve one turn -> render dirty cells ->
; bump the turn counter, on a hand-authored static map. No procgen, monsters,
; combat, or items yet (those are P4). Built on the P2 skeleton's own glyph
; blitter (draw_cell) — no ROM print/CLS dependency (those no-op from a bare
; snapshot; the engine owns rendering per design §1).
;
; Boot: stack/state -> entities -> render map+player -> turn loop.
; Logic is keypress-paced (design §4.1): the loop blocks in get_action until a
; fresh keypress. Interrupts stay on (IM1 ROM ISR) only so HALT works for the
; one-frame chord capture window.
;==============================================================================

                DEVICE ZXSPECTRUM128

                INCLUDE "constants.asm"

;------------------------------------------------------------------------------
; Test-observable state lives at STABLE ADDRESSES (docs/memory-map.md). These
; are RUNTIME storage (EQU, no image bytes); init_game writes their boot values
; so the tape/snapshot stays a single clean CODE block.
;------------------------------------------------------------------------------

                ORG $8000

start:
                di                      ; quiet window while we set up the stack
                ld   sp, WORKSTORE_TOP   ; stack grows down from the state block
                call init_game
                ei                       ; ROM IM1 ISR on — only so HALT works

;------------------------------------------------------------------------------
; game_loop — the P3 turn loop (design §4.1, reduced).
;   read input -> resolve action -> (if a turn was consumed) bump turn counter.
; resolve_action renders the dirty cells itself; an illegal move costs no turn.
;------------------------------------------------------------------------------
game_loop:
                call get_action          ; A = action; for ACT_MOVE: D=dx, E=dy
                call resolve_action      ; CF set iff a turn was consumed
                jr   nc, game_loop       ; no turn (illegal move / no-op) -> reread
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (TURN_COUNTER), hl   ; one chord/keypress = exactly one turn
                jr   game_loop

;==============================================================================
; init_game — boot-time state + first full render.
; In : —   Clobbers: everything (cold path)
;==============================================================================
init_game:
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl      ; fixed seed (design §5.6); test-observable
                ld   hl, 0
                ld   (TURN_COUNTER), hl
                xor  a
                ld   (INPUT_SRC), a       ; default: scan real keyboard
                call init_kbd_mirror
                call init_entities

                ld   a, COL_BLUE
                out  (PORT_BORDER), a
                call clear_bitmap         ; blank pixels (status/message rows stay 0)
                call fill_attr            ; flood all 768 attrs to ATTR_MAP
                call draw_map             ; blit every terrain cell once
                jp   draw_player          ; @ over the start cell (tail call)

;==============================================================================
; init_kbd_mirror — set the 8-byte keyboard mirror to "all released".
;==============================================================================
init_kbd_mirror:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, KBD_RELEASED
.row:
                ld   (hl), a
                inc  hl
                djnz .row
                ret

;==============================================================================
; init_entities — zero the 16-slot array, then set up the player (slot 0).
; P3 only needs x/y/flags, but hp/atk are filled so P4 inherits sane defaults.
;==============================================================================
init_entities:
                ld   hl, ENTITIES
                ld   de, ENTITIES + 1
                ld   bc, ENT_ARRAY_LEN - 1
                ld   (hl), 0
                ldir                       ; whole array -> 0 (all slots inactive)

                ; player slot 0 — kind already 0
                ld   a, PLAYER_START_X
                ld   (PLAYER_X), a
                ld   a, PLAYER_START_Y
                ld   (PLAYER_Y), a
                ld   a, PLAYER_START_HP
                ld   (ENTITIES + ENT_HP), a
                ld   (ENTITIES + ENT_MAX_HP), a
                ld   a, PLAYER_START_ATK
                ld   (ENTITIES + ENT_ATK), a
                ld   a, EF_ACTIVE | EF_PLAYER
                ld   (ENTITIES + ENT_FLAGS), a
                ret

;==============================================================================
; INPUT LAYER (design §3, REVISED 4-key-chordable scheme).
;==============================================================================

;==============================================================================
; scan_matrix — copy the 8 keyboard half-rows into KBD_MATRIX.
; If INPUT_SRC != 0 the mirror is left untouched (test injection path).
; In : —   Out: KBD_MATRIX[0..7] updated   Clobbers: A, BC, D, HL
;------------------------------------------------------------------------------
; B holds the half-row select on A8..A15; a single 0 bit rotates through it
; ($FE,$FD,$FB,... back to $FE), giving the 8 half-rows in mirror-index order.
;==============================================================================
scan_matrix:
                ld   a, (INPUT_SRC)
                or   a
                ret  nz                    ; test mode: keep the poked mirror
                ld   hl, KBD_MATRIX
                ld   c, $FE                ; ULA low address byte (A0 = 0)
                ld   b, $FE                ; first half-row select (rotates)
                ld   d, KBD_MATRIX_LEN
.row:
                in   a, (c)                ; B on A8..A15 selects the half-row
                ld   (hl), a
                inc  hl
                rlc  b                     ; move the 0 bit to the next half-row
                dec  d
                jr   nz, .row
                ret

;==============================================================================
; sample_keys — fold the held movement keys into a direction bitset.
; In : KBD_MATRIX   Out: A = DIR_* bitset (primary hjkl + secondary QAOP)
; Clobbers: A, E
;==============================================================================
sample_keys:
                ld   e, 0                  ; accumulator
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                bit  KB_L_BIT, a
                jr   nz, .nL
                set  DIR_E_BIT, e
.nL:
                bit  KB_K_BIT, a
                jr   nz, .nK
                set  DIR_N_BIT, e
.nK:
                bit  KB_J_BIT, a
                jr   nz, .nJ
                set  DIR_S_BIT, e
.nJ:
                bit  KB_H_BIT, a
                jr   nz, .nH
                set  DIR_W_BIT, e
.nH:
                ld   a, (KBD_MATRIX + KBROW_POIUY)
                bit  KB_P_BIT, a
                jr   nz, .nP
                set  DIR_E_BIT, e
.nP:
                bit  KB_O_BIT, a
                jr   nz, .nO
                set  DIR_W_BIT, e
.nO:
                ld   a, (KBD_MATRIX + KBROW_QWERT)
                bit  KB_Q_BIT, a
                jr   nz, .nQ
                set  DIR_N_BIT, e
.nQ:
                ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_A_BIT, a
                jr   nz, .nA
                set  DIR_S_BIT, e
.nA:
                ld   a, e
                ret

;==============================================================================
; sample_discrete — first non-movement action key held, if any.
; In : KBD_MATRIX   Out: A = ACT_WAIT/QUAFF/DESCEND/CONFIRM or ACT_NONE
; Clobbers: A
;==============================================================================
sample_discrete:
                ld   a, (KBD_MATRIX + KBROW_SPACE)
                bit  KB_SPACE_BIT, a
                jr   nz, .nSpace
                ld   a, ACT_WAIT
                ret
.nSpace:
                ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_G_BIT, a
                jr   nz, .nG
                ld   a, ACT_QUAFF
                ret
.nG:
                bit  KB_D_BIT, a
                jr   nz, .nD
                ld   a, ACT_DESCEND
                ret
.nD:
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                bit  KB_ENTER_BIT, a
                jr   nz, .nEnter
                ld   a, ACT_CONFIRM
                ret
.nEnter:
                xor  a                     ; ACT_NONE
                ret

;==============================================================================
; any_key_down — is any movement OR discrete key currently held?
; Out: NZ if something held, Z if nothing.   Clobbers: A, E
;==============================================================================
any_key_down:
                call sample_keys
                or   a
                ret  nz
                call sample_discrete        ; A = action or ACT_NONE
                or   a                       ; sample_discrete's `ld a` leaves stale
                ret                          ; flags, so re-test A here (NZ = held)

;==============================================================================
; dirs_to_step — bitset -> signed step. Opposite keys cancel.
; In : A = DIR_* bitset   Out: D = dx, E = dy (each -1/0/+1); Z set iff (0,0)
; Clobbers: A, D, E
;==============================================================================
dirs_to_step:
                ld   d, 0
                bit  DIR_E_BIT, a
                jr   z, .nE
                inc  d                     ; +1
.nE:
                bit  DIR_W_BIT, a
                jr   z, .nW
                dec  d                     ; sum -> 0 if both, $FF if only west
.nW:
                ld   e, 0
                bit  DIR_S_BIT, a
                jr   z, .nS
                inc  e
.nS:
                bit  DIR_N_BIT, a
                jr   z, .nN
                dec  e
.nN:
                ld   a, d
                or   e                     ; Z iff dx==0 && dy==0
                ret

;==============================================================================
; get_action — block until a fresh action; debounce one press = one action.
; Out: A = action code; for ACT_MOVE, D = dx, E = dy.
; Clobbers: A, BC, D, E, HL
;------------------------------------------------------------------------------
; Debounce: wait for all keys released, then for a press (design §3: one chord =
; one turn, release required between). Chord capture window: on the first
; movement edge, HALT one frame (~20ms) and re-sample, OR-ing the two reads, so a
; near-simultaneous second key still registers as a diagonal.
;==============================================================================
get_action:
.release:
                call scan_matrix
                call any_key_down
                jr   nz, .release          ; hold here until everything is up
.press:
                call scan_matrix
                call sample_keys
                or   a
                jr   nz, .have_move
                call sample_discrete
                or   a
                jr   z, .press             ; nothing actionable -> keep waiting
                ret                        ; discrete action (A set)
.have_move:
                push af                     ; save first movement sample
                halt                        ; chord capture window: ~1 frame
                call scan_matrix
                call sample_keys
                pop  bc                     ; B = first sample
                or   b                      ; combined held set
                call dirs_to_step
                jr   z, .press             ; opposite keys cancelled -> no action
                ld   a, ACT_MOVE
                ret

;==============================================================================
; resolve_action — apply the player's action for one turn.
; In : A = action; D = dx, E = dy (ACT_MOVE only)
; Out: CF set iff a turn was consumed.   Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
; Illegal move into a wall (or off-map) = position unchanged AND no turn (§6.5).
; Diagonal-vs-wall rule (P3): a step is legal iff the DESTINATION cell is
; walkable; corner-cutting between two diagonal walls is NOT blocked (documented
; simplification — cheapest correct rule for the slice).
;==============================================================================
resolve_action:
                cp   ACT_MOVE
                jr   z, .move
                cp   ACT_WAIT
                jr   z, .wait
                or   a                      ; QUAFF/DESCEND/CONFIRM: no-op, no turn
                ret
.wait:
                scf                         ; WAIT consumes a turn (design §4.1)
                ret
.move:
                ld   a, (PLAYER_X)
                add  a, d                   ; nx = x + dx (8-bit two's complement)
                cp   MAP_W
                jr   nc, .blocked           ; off-map (incl. wrap to $FF) -> illegal
                ld   c, a                   ; C = nx (map col)
                ld   a, (PLAYER_Y)
                add  a, e
                cp   MAP_H
                jr   nc, .blocked
                ld   b, a                   ; B = ny (map row)
                call map_tile               ; A = terrain at (nx,ny); preserves BC
                or   a
                jr   z, .blocked            ; T_WALL = 0 -> not walkable
                ; --- legal move: redraw old cell as terrain, then player at new
                push bc                     ; save new (ny,nx)
                call draw_player_terrain    ; restore terrain under old position
                pop  bc
                ld   a, c
                ld   (PLAYER_X), a
                ld   a, b
                ld   (PLAYER_Y), a
                call draw_player
                scf                         ; turn consumed
                ret
.blocked:
                or   a                      ; CF = 0: no turn
                ret

;==============================================================================
; RENDER (dirty-cell, design §1/§6.18). draw_cell (P2) is the per-cell blitter.
;==============================================================================

;==============================================================================
; map_tile — terrain byte at map (mx,my).
; In : B = my (row), C = mx (col)   Out: A = tile byte   Preserves BC
; Clobbers: A, DE, HL
;------------------------------------------------------------------------------
; addr = map_data + my*MAP_W + mx, MAP_W=30 = (my<<5) - (my<<1).
;==============================================================================
map_tile:
                ld   l, b
                ld   h, 0                   ; HL = my
                add  hl, hl                 ; my*2
                ld   e, l
                ld   d, h                   ; DE = my*2
                add  hl, hl                 ; *4
                add  hl, hl                 ; *8
                add  hl, hl                 ; *16
                add  hl, hl                 ; *32
                or   a
                sbc  hl, de                 ; my*32 - my*2 = my*30
                ld   e, c
                ld   d, 0
                add  hl, de                 ; + mx
                ld   de, map_data
                add  hl, de
                ld   a, (hl)
                ret

;==============================================================================
; cell_attr_addr — attribute-byte address of screen char cell (col,row).
; In : B = screen row (0..23), C = screen col (0..31)   Out: HL = attr addr
; Preserves BC, DE   Clobbers: A, HL
;------------------------------------------------------------------------------
; addr = SCREEN_ATTR + row*32 + col. row<<5 via 5 adds (no DE needed so callers
; can keep a glyph pointer in DE across the call).
;==============================================================================
cell_attr_addr:
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                 ; HL = row*32
                ld   a, l
                add  a, c
                ld   l, a
                jr   nc, .noCarry
                inc  h
.noCarry:
                ld   a, h
                add  a, (SCREEN_ATTR >> 8)  ; SCREEN_ATTR low byte is 0
                ld   h, a
                ret

;==============================================================================
; blit_cell — draw a glyph + attribute into a MAP cell (applies viewport offset).
; In : A = attr, B = my, C = mx, HL = 8-byte glyph
; Clobbers: A, B, DE, HL   (C ends as screen col)
;==============================================================================
blit_cell:
                inc  b                      ; map my -> screen row (+VIEW_ROW_OFF)
                inc  c                      ; map mx -> screen col (+VIEW_COL_OFF)
                ex   de, hl                 ; DE = glyph ptr (parked over attr calc)
                push af                      ; save attr
                call cell_attr_addr          ; HL = attr addr (BC, DE preserved)
                pop  af
                ld   (hl), a                 ; write the cell's single attribute
                ex   de, hl                  ; HL = glyph ptr again
                jp   draw_cell               ; blit 8 bitmap rows (tail call)

;==============================================================================
; draw_map_cell — draw the terrain glyph for map (mx,my) with ATTR_MAP.
; In : B = my, C = mx   Clobbers: A, B, DE, HL  (C ends as screen col)
;==============================================================================
draw_map_cell:
                call map_tile               ; A = terrain (BC preserved)
                add  a, a                    ; tile*8 -> glyph offset (tile <= 3)
                add  a, a
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, tile_glyphs
                add  hl, de                  ; HL = glyph ptr
                ld   a, ATTR_MAP
                jp   blit_cell

;==============================================================================
; draw_map — render the whole map once (cold; boot only). ~630 cell blits.
;==============================================================================
draw_map:
                ld   b, 0                    ; my
.row:
                ld   c, 0                    ; mx
.col:
                push bc
                call draw_map_cell
                pop  bc
                inc  c
                ld   a, c
                cp   MAP_W
                jr   nz, .col
                inc  b
                ld   a, b
                cp   MAP_H
                jr   nz, .row
                ret

;==============================================================================
; draw_player — draw the @ glyph at the player's current cell.
; draw_player_terrain — restore the terrain glyph at the player's current cell
;                       (used to erase the old position before a move).
; Clobbers: A, BC, DE, HL
;==============================================================================
draw_player_terrain:
                ld   a, (PLAYER_Y)
                ld   b, a
                ld   a, (PLAYER_X)
                ld   c, a
                jp   draw_map_cell

draw_player:
                ld   a, (PLAYER_Y)
                ld   b, a
                ld   a, (PLAYER_X)
                ld   c, a
                ld   hl, glyph_player
                ld   a, ATTR_PLAYER
                jp   blit_cell

;==============================================================================
; clear_bitmap — blank the whole pixel bitmap to 0 (cold; boot only).
; Out: $4000..$57FF = 0   Clobbers: A, BC, DE, HL
;==============================================================================
clear_bitmap:
                xor  a
                ld   hl, SCREEN_BITMAP
                ld   (hl), a
                ld   de, SCREEN_BITMAP + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ldir
                ret

;==============================================================================
; fill_attr — flood the attribute grid with ATTR_MAP (status/spare/message rows
; included; map cells overwrite their own attrs in draw_map). Cold; boot only.
; Out: $5800..$5AFF = ATTR_MAP   Clobbers: A, BC, DE, HL
;==============================================================================
fill_attr:
                ld   a, ATTR_MAP
                ld   hl, SCREEN_ATTR
                ld   (hl), a
                ld   de, SCREEN_ATTR + 1
                ld   bc, SCREEN_ATTR_LEN - 1
                ldir
                ret

;==============================================================================
; draw_cell — blit one 8x8 glyph into char cell (col,row). REUSED FROM P2 — the
; dirty-cell render primitive. In one char cell the 8 pixel rows share the low
; byte and differ only in bits of the high byte, so we compute the base once and
; `inc d` per row (no per-row address recompute).
;
; In : B = cell row (0..23), C = cell col (0..31), HL = 8-byte glyph
; Out: 8 glyph bytes written; HL advanced past the glyph
; Clobbers: A, B, DE, HL  (preserves C, IX, IY)
;------------------------------------------------------------------------------
;   high = $40 | (row & $18);  low = ((row & 7) << 5) | col
;==============================================================================
draw_cell:
                ld   a, b
                and  $18
                or   $40
                ld   d, a                    ; D = high byte of the cell's top row
                ld   a, b
                and  7
                rrca                          ; (row & 7) << 5 (8-bit rot: <<5 == >>3)
                rrca
                rrca
                or   c                        ; | col
                ld   e, a                     ; E = low byte (constant down the cell)
                ld   b, GLYPH_BYTES
.row:
                ld   a, (hl)
                ld   (de), a                  ; write one pixel row
                inc  hl
                inc  d                        ; next scanline = high+1
                djnz .row
                ret

;==============================================================================
; STATIC MAP (design §4.2) — 30x21, row-major, one byte/cell. Hand-authored:
; a solid border, a vertical wall divider at col 15 splitting two rooms, and a
; single corridor tile (15,10) joining them. Player starts at (1,5).
;
; Layout (#=wall '.'=floor '+'=corridor), rows top->bottom:
;   row 0  : ##############################
;   rows1-9: #..............#.............#   (left room | wall | right room)
;   row 10 : #..............+.............#   (corridor links the rooms)
;   rows11-19 #..............#.............#
;   row 20 : ##############################
;==============================================================================
map_data:
                DEFS MAP_W, T_WALL            ; row 0
                DUP 9                         ; rows 1..9
                  DB  T_WALL
                  DEFS 14, T_FLOOR
                  DB  T_WALL
                  DEFS 13, T_FLOOR
                  DB  T_WALL
                EDUP
                ; row 10 — corridor gap in the divider
                DB  T_WALL
                DEFS 14, T_FLOOR
                DB  T_CORR
                DEFS 13, T_FLOOR
                DB  T_WALL
                DUP 9                         ; rows 11..19
                  DB  T_WALL
                  DEFS 14, T_FLOOR
                  DB  T_WALL
                  DEFS 13, T_FLOOR
                  DB  T_WALL
                EDUP
                DEFS MAP_W, T_WALL            ; row 20

;==============================================================================
; TILESET (placeholder, design §6 P5 replaces with artist data). 8 bytes/glyph,
; MSB = leftmost pixel. Indexed by terrain id (T_WALL..T_STAIRS). One ink/paper
; per cell => clash-free by construction (§6.17).
;==============================================================================
tile_glyphs:
gl_wall:        DB  $00,$24,$7E,$24,$24,$7E,$24,$00   ; '#'
gl_floor:       DB  $00,$00,$00,$18,$18,$00,$00,$00   ; centre dot
gl_corr:        DB  $00,$18,$18,$00,$18,$18,$00,$00   ; ':'
gl_stairs:      DB  $00,$40,$70,$7C,$70,$40,$00,$00   ; '>'

glyph_player:   DB  $3C,$42,$5A,$56,$5C,$40,$3E,$00   ; '@'

code_end:                                       ; first free byte past emitted code
CODE_LEN        EQU code_end - start

;------------------------------------------------------------------------------
; tap_loader — tokenised BASIC autoloader:
;   10 CLEAR VAL "32767": RANDOMIZE USR VAL "32768"
; Tokenised in a scratch ORG (not part of the runtime image).
;------------------------------------------------------------------------------
                ORG  $E000
tap_loader:
                ; Line 10: CLEAR VAL "32767"
                DB   0, 10                   ; line number 10 (big-endian)
                DW   tap_l10_end - tap_l10_body
tap_l10_body:
                DB   $FD                      ; CLEAR
                DB   $B0, '"', "32767", '"'   ; VAL "32767"
                DB   $0D                      ; ENTER
tap_l10_end:

                ; Line 20: LOAD "" CODE — without this, RANDOMIZE USR jumps
                ; into memory the tape never actually loaded (real tape-load
                ; semantics only auto-loads the BASIC block; ZEsarUX's
                ; smartload bypasses this, which is why this was invisible
                ; to automated ZRCP tests but crashes/resets on real Fuse).
                DB   0, 20
                DW   tap_l20_end - tap_l20_body
tap_l20_body:
                DB   $EF                      ; LOAD
                DB   $22, $22                  ; ""
                DB   $AF                      ; CODE
                DB   $0D
tap_l20_end:

                ; Line 30: RANDOMIZE USR VAL "32768"
                DB   0, 30
                DW   tap_l30_end - tap_l30_body
tap_l30_body:
                DB   $F9                      ; RANDOMIZE
                DB   $C0                      ; USR
                DB   $B0, '"', "32768", '"'   ; VAL "32768"
                DB   $0D                      ; ENTER
tap_l30_end:
tap_loader_len  EQU  $ - tap_loader

;==============================================================================
; Emit artefacts (unchanged from P2): a two-block autoloader .tap and a snapshot.
; MUST come after tap_loader's bytes are assembled — SAVETAP dumps the
; assembler's memory image at the point it executes in source order, not at
; end of file, so calling it before the loader's ORG block silently emits an
; all-zero BASIC data block (assembles clean, checksums clean, "Nonsense in
; BASIC" only on a real tape-load — ZEsarUX's smartload bypasses this
; entirely, which is how this went undetected).
;==============================================================================
                EMPTYTAP "build/wazhack.tap"
                SAVETAP  "build/wazhack.tap", BASIC, "wazhack", tap_loader, tap_loader_len, 10
                SAVETAP  "build/wazhack.tap", CODE,  "wazhack", start, CODE_LEN
                SAVESNA "build/wazhack.sna", start
