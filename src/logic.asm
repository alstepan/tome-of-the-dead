;==============================================================================
; logic.asm — PROTO turn logic (prototype §3, §6).
;   world/room build, collision, player actions (walk / climb / bump-attack /
;   quaff / wait / exits), combat rolls, monster AI (walker / climber / flyer +
;   yield rule), pending materialise, follow selection, potions, HUD.
; All logic is cell-granular and resolved instantly at turn start; the anim
; layer only replays it. Deterministic: RNG consumed only here, in the order of
; prototype §6.2.
; Register conventions here: IX = the acting entity (documented per routine);
; IY never touched.
;==============================================================================


;==============================================================================
; ent_ix — IX = P_ENTITIES + A*32 (A = slot 0..15).  Clobbers: A, E
;==============================================================================
ent_ix:
                rrca
                rrca
                rrca                           ; bits 5-7 = slot&7, bit0 = slot>>3
                ld   e, a
                and  $E0
                ld   ixl, a                    ; P_ENTITIES low byte is 0
                ld   a, e
                and  1
                add  a, P_ENTITIES >> 8
                ld   ixh, a
                ret

; ix_slot — A = slot of IX.  Clobbers: A, E
ix_slot:
                ld   a, ixh
                sub  P_ENTITIES >> 8
                ld   e, a                      ; 0/1
                ld   a, ixl
                rlca
                rlca
                rlca                           ; (low>>5)
                and  7
                bit  0, e
                ret  z
                add  a, 8
                ret

;==============================================================================
; get_box — body box of IX: C = x, B = y, D = w, E = h.  Clobbers: A, HL
;==============================================================================
get_box:
                KFIELD KT_BW
                ld   d, a
                KFIELD KT_BH
                ld   e, a
                ld   c, (ix+E_X)
                ld   b, (ix+E_Y)
                ret

; feet_mod — A = (y+h) mod 9, L = (y+h) div 9 (raw; STOREY_ROWS).  Clobbers: A, H, L
feet_mod:
                KFIELD KT_BH
                add  a, (ix+E_Y)
                ld   l, a
                ld   h, (kind_tab + KT_MOD9) >> 8   ; KT_MOD9/KT_DIV9: one page
                push hl
                ld   a, l
                add  a, KT_DIV9 & $FF
                ld   l, a
                ld   a, (hl)
                pop  hl
                push af
                ld   a, l
                add  a, KT_MOD9 & $FF
                ld   l, a
                ld   a, (hl)
                pop  hl
                ld   l, h                      ; L = div9
                ret

; is_standing — Z if IX stands on a floor ((y+h) mod 9 == 8, game.md §2.1).  Clobbers: A, HL
is_standing:
                call feet_mod
                cp   STOREY_AIR
                ret

; on_ladder — Z if IX is mid-ladder (non-flyer, not standing).  Clobbers: A, HL
; (NZ = free: standing or flying)
on_ladder:
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   nz, .free
                call is_standing
                jr   z, .free
                xor  a                         ; Z = mid-ladder
                ret
.free:          or   1                         ; NZ
                ret

; storey_ref — A = min(1, (y+h) div 9) (prototype §6.4 on 2 storeys).  Clobbers: A, HL
storey_ref:
                call feet_mod
                ld   a, l
                cp   STOREY_COUNT
                ret  c
                ld   a, STOREY_COUNT - 1
                ret

;==============================================================================
; build_live — LIVE_LIST = the entities that can collide this turn: active, in
; CUR_ROOM, not PENDING. 5 B/entry: slot, ptr lo, ptr hi, w, h (kind body box
; cached). DYING is re-checked live (it changes mid-turn). Rebuilt at turn start
; and whenever a pending monster materialises.  ~1.3k T.  Clobbers: A, BC, DE, HL
;==============================================================================
build_live:
                push ix
                ld   de, LIVE_LIST
                ld   ix, P_ENTITIES
                ld   c, 0                      ; slot
                ld   b, 0                      ; count
.l:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   a, c
                ld   (de), a
                inc  de
                ld   a, ixl
                ld   (de), a
                inc  de
                ld   a, ixh
                ld   (de), a
                inc  de
                KFIELD KT_BW
                ld   (de), a
                inc  de
                KFIELD KT_BH
                ld   (de), a
                inc  de
                inc  b
.n:             push de
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                inc  c
                ld   a, c
                cp   P_MAX_ENT
                jr   c, .l
                ld   a, b
                ld   (LIVE_N), a
                pop  ix
                ret

;==============================================================================
; box_free — CF = 1 if box (C=x, B=y, D=w, E=h) overlaps any LIVE_LIST entity
; other than slot ACT_SLOT that is not DYING (prototype §6.1: pending/dying
; never block). Preserves: BC, DE, IX.  Clobbers: A, HL
; ~60 T + ~130 T per live entity (was ~200 T x 16 slots).
;==============================================================================
box_free:
                push ix
                ld   a, (LIVE_N)
                or   a
                jr   z, .free
                ld   hl, LIVE_LIST
.lp:            push af
                ld   a, (ACT_SLOT)
                cp   (hl)
                jr   z, .skip5
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                inc  hl                        ; -> w
                bit  EF_DYING_BIT, (ix+E_FLAGS)
                jr   nz, .skip3
                ld   a, (ix+E_X)               ; ox+ow-1 >= x
                add  a, (hl)
                dec  a
                cp   c
                jr   c, .skip3
                ld   a, c                      ; x+w-1 >= ox
                add  a, d
                dec  a
                cp   (ix+E_X)
                jr   c, .skip3
                inc  hl                        ; -> h
                ld   a, (ix+E_Y)
                add  a, (hl)
                dec  a
                cp   b
                jr   c, .skip2
                ld   a, b
                add  a, e
                dec  a
                cp   (ix+E_Y)
                jr   c, .skip2
                pop  af                        ; overlap
                pop  ix
                scf
                ret
.skip5:         inc  hl                        ; slot byte -> +5 in total
                inc  hl
                inc  hl
.skip3:         inc  hl
.skip2:         inc  hl
                pop  af
                dec  a
                jr   nz, .lp
.free:          pop  ix
                or   a
                ret

;==============================================================================
; ROOM DESCRIPTOR QUERIES (current room unless noted)
;==============================================================================
; room_desc — HL = descriptor of room A.  Clobbers: A, DE, HL
room_desc:
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, room_tab
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ret

cur_room_desc:
                ld   a, (CUR_ROOM)
                jr   room_desc

; ladder_exists — CF = 1 if segment {col C, storey B} exists in the current room.
; Preserves BC. Clobbers: A, DE, HL
ladder_exists:
                call cur_room_desc
                ld   de, RD_LADDERS
                add  hl, de
                ld   d, (hl)                   ; count
                inc  hl
                inc  d
.l:             dec  d
                jr   z, .nf
                ld   a, (hl)
                inc  hl
                cp   c
                ld   a, (hl)
                inc  hl
                jr   nz, .l
                cp   b
                jr   nz, .l
                scf
                ret
.nf:            or   a                         ; CF = 0: not found
                ret

; exit_h — A = EX_LEFT / EX_RIGHT, B = storey. CF = 1 if open; A = dest.
; Clobbers: A, DE, HL
exit_h:
                push af
                call cur_room_desc
                pop  af
                cp   EX_LEFT
                jr   z, .l
                inc  hl
                inc  hl
.l:             ld   a, (hl)                   ; exit storey
                cp   b
                jr   nz, .no
                inc  hl
                ld   a, (hl)
                scf
                ret
.no:            or   a
                ret

; map_cell — HL = map(TMP1 page) + B*32 + C (build_room_map, potion_pickup:
; bank 2 so the per-turn pickup stays uncontended).  Clobbers: A
map_cell:
                ld   a, b
                rrca
                rrca
                rrca
                ld   l, a
                and  3
                push bc
                ld   b, a
                ld   a, (TMP1)
                add  a, b
                pop  bc
                ld   h, a
                ld   a, l
                and  $E0
                or   c
                ld   l, a
                ret

;==============================================================================
; B3B-5 TERRAIN (D2): TILE_FLAGS of the room map. Input / AI path only (the
; per-tick renderer never reads it). Ladders stay on the descriptor fields.
;------------------------------------------------------------------------------
; cell_addr — HL = ROOM_MAP + B*32 + C (row B 0..17, col C 0..31). The map is
; page-aligned, so H = page + row>>3 and L = (row&7)<<5 | col (no add).
; Preserves BC, DE.  Clobbers: A.   67 T + call
;------------------------------------------------------------------------------
cell_addr:
                ld   a, b
                rrca
                rrca
                rrca                           ; bits 7-5 = row&7, bits 1-0 = row>>3
                ld   l, a
                and  3
                add  a, ROOM_MAP >> 8
                ld   h, a
                ld   a, l
                and  $E0
                or   c
                ld   l, a
                ret
                ASSERT (ROOM_MAP & $FF) == 0

;------------------------------------------------------------------------------
; cell_blocked — col C, row B: A = TILE_FLAGS of that ROOM_MAP cell, CF =
; TF_SOLID. Preserves BC, DE.  Clobbers: A, HL.   ~135 T incl. the call
;------------------------------------------------------------------------------
cell_blocked:
                call cell_addr
                ld   a, (hl)                   ; tile id 0..63
                add  a, tile_flags & $FF       ; tile_flags ends on its page: no carry
                ld   l, a
                ld   h, tile_flags >> 8
                ld   a, (hl)
                rrca                           ; CF = bit 0 = TF_SOLID
                rlca                           ; A back, CF kept (bit 7 of the rotated = bit 0)
                ret
                ASSERT TF_SOLID == 1

;------------------------------------------------------------------------------
; lead_cell — the cell a WALKER's horizontal step runs into: box C = new x,
; B = y, D = w, E = h, A = dx (1 / $FF). Leading col = C + D - 1 (right) / C
; (left), row = y + h - 1. One cell is enough for a standing body: its rows
; are 9s+8-h .. 9s+7 with h <= 6 (ASSERTed below), so it never reaches the
; arch / lintel rows 9s+1 / 9s; walls, blocks and (wall-set) wall decor span
; the whole air band and planks rows 9s+2..9s+7, so the lowest row decides.
; Flyers use box_solid (any band row). Out: A = flags, CF = TF_SOLID.
; Preserves BC, DE.  Clobbers: A, HL.   ~210 T
;------------------------------------------------------------------------------
lead_cell:
                push bc
                dec  a                         ; Z: dx = 1 (right)
                jr   nz, .row
                ld   a, c
                add  a, d
                dec  a
                ld   c, a
.row:           ld   a, b
                add  a, e
                dec  a
                ld   b, a
                call cell_blocked
                pop  bc
                ret

;------------------------------------------------------------------------------
; box_solid — CF = 1 if any cell of box C,B,D,E (in the map) is TF_SOLID.
; Flyers' steps (§9.1: a body passes an open door only through its opening
; rows) and the jump's swept box. ~60 T a cell (bat 6 cells ~0.5k T, ghost
; 12 ~0.9k T).  Keeps BC, DE.  Clobbers: A, HL
;------------------------------------------------------------------------------
box_solid:
                push bc
                push de
.row:           call cell_addr                 ; HL = the row's first cell
                push bc
                ld   b, d
.col:           ld   a, (hl)
                push hl
                add  a, tile_flags & $FF
                ld   l, a
                ld   h, tile_flags >> 8
                ld   a, (hl)
                pop  hl
                rrca                           ; CF = TF_SOLID
                jr   c, .x
                inc  l                         ; cols stay inside the row
                djnz .col
                pop  bc
                inc  b
                dec  e
                jr   nz, .row
                or   a
                jr   .out
.x:             pop  bc
.out:           pop  de
                pop  bc
                ret

                ; lead_cell's one-cell rule: every non-flyer kind has KT_BH <=
                ; STOREY_AIR - DOOR_PLANK_DY. Checked for ALL kinds by a DUP
                ; over the assembled kind_tab rows, right after kind_tab
                ; (main.asm "walker height"): a new tall walker fails the build.

; desc_byte — A = the byte at offset A of the current room's descriptor.
; Clobbers: A, DE, HL.   ~170 T
desc_byte:
                push af
                call cur_room_desc
                pop  de
                ld   e, d
                ld   d, 0
                add  hl, de
                ld   a, (hl)
                ret

; bitmask — A = 1 << A (A = 0..7).  Clobbers: A, D
bitmask:
                ld   d, a
                ld   a, 1
                inc  d
.b:             dec  d
                ret  z
                add  a, a
                jr   .b

; storey_row — A = 9*A + 7: the standing (potion / floor-item) row of storey A.
storey_row:
                push bc
                MUL_STOREY b
                add  a, STOREY_AIR - 1
                pop  bc
                ret

; snap_pxpy — px = x*8, py = y*8.  Clobbers: A
snap_pxpy:
                ld   a, (ix+E_X)
                add  a, a
                add  a, a
                add  a, a
                ld   (ix+E_PX), a
                ld   a, (ix+E_Y)
                add  a, a
                add  a, a
                add  a, a
                ld   (ix+E_PY), a
                ret

;==============================================================================
; PLAYER TURN — try_player_turn: resolve the sampled keys (PLAYER_DIR/DISC).
; Chords (§9): B3B-5: UP + LEFT / RIGHT is always a jump (game.md §2.4,
; try_jump); else vertical wins if a climb is legal, else horizontal, else
; C (close door, 3B stand-in), else G, else wait. A climb blocked by an ENTITY counts as a wait (rule by user 2026-10-02,
; §6.4: the blocker gets its turn to move off), at wait priority. Illegal
; (terrain / no ladder) -> CF = 0, nothing changed (no turn).
; Out: CF = 1 turn used.
; Clobbers: all but IY.  (IX = player on return)
;==============================================================================
try_player_turn:
                call build_live
                ld   ix, P_ENTITIES
                xor  a
                ld   (ACT_SLOT), a
                ld   (CLIMB_BLK), a            ; A = 0
                ld   a, (ix+E_FLAGS)
                and  EF_DYING
                ret  nz                        ; dead heroes don't act (CF=0)
                ld   a, (PLAYER_DIR)           ; B3B-5: UP + LEFT / RIGHT is always a
                bit  DIR_N_BIT, a              ; jump (game.md §2.4), legal or not
                jr   z, .nj
                and  (1 << DIR_E_BIT) | (1 << DIR_W_BIT)
                jp   nz, try_jump              ; lowram: A = E/W bits; CF = 1 jumped
.nj:            ld   a, (PLAYER_DIR)
                and  (1 << DIR_N_BIT) | (1 << DIR_S_BIT)
                cp   1 << DIR_N_BIT
                jr   nz, .nu
                ld   d, $FF
                call try_climb
                ret  c
                jr   .horiz
.nu:            cp   1 << DIR_S_BIT
                jr   nz, .horiz
                ld   d, 1
                call try_climb
                ret  c
.horiz:
                ld   a, (PLAYER_DIR)
                and  (1 << DIR_E_BIT) | (1 << DIR_W_BIT)
                cp   1 << DIR_E_BIT
                jr   nz, .nr
                ld   d, 1
                call try_horizontal
                ret  c
                jr   .disc
.nr:            cp   1 << DIR_W_BIT
                jr   nz, .disc
                ld   d, $FF
                call try_horizontal
                ret  c
.disc:
                ld   a, (PLAYER_DISC)
                bit  DK_CLOSE_BIT, a           ; B3B-5 stand-in key C (game.md §1.4)
                jr   z, .ncl
                call try_close                 ; lowram: CF = 1 closed
                ret  c
                ld   a, (PLAYER_DISC)
.ncl:           bit  DK_QUAFF_BIT, a
                jr   z, .nq
                call try_quaff
                ret  c
                ld   a, (PLAYER_DISC)
.nq:            bit  DK_WAIT_BIT, a
                jr   nz, .wait
                ld   a, (CLIMB_BLK)            ; climb blocked by an entity:
                or   a                         ; a wait (else CF = 0, no turn)
                ret  z
.wait:          scf                            ; WAIT: a 2-tick turn, nothing moves
                ret

;------------------------------------------------------------------------------
; try_climb — IX = player, D = dy ($FF up / 1 down). CF = 1 if done (§3.4).
; Standing: UP needs {x,s} ({x,0} = up-exit, no step), DOWN needs {x,s+1}
; ({x,2} = down-exit, first step animated). Mid-ladder: continue or reverse.
; Step blocked by an entity: CF = 0 and CLIMB_BLK = 1 (the caller turns it
; into a wait); no ladder: CF = 0, CLIMB_BLK untouched.
; Clobbers: A, BC, DE, HL, TMP6
;------------------------------------------------------------------------------
try_climb:
                ld   a, d
                ld   (TMP6), a                 ; dy (D is clobbered by queries)
                call is_standing
                jr   nz, .mid
                call feet_mod
                ld   b, l                      ; B = storey stood on
                ld   c, (ix+E_X)
                ld   a, (TMP6)
                cp   1
                jr   z, .down
                call ladder_exists             ; UP: {x, s}
                ret  nc
                ld   a, b
                or   a
                jr   nz, .mid
                call cur_room_desc             ; {x,0}: up-exit (player only)
                ld   de, RD_EXU_D
                add  hl, de
                ld   a, (hl)
                cp   EXIT_NONE
                jr   z, .no
                ld   (EXIT_DEST), a
                ld   a, EX_UP
                ld   (EXIT_KIND), a
                ld   a, (ix+E_X)
                ld   (EXIT_COL), a
                xor  a
                ld   (EXIT_STOREY), a
                scf
                ret
.no:            or   a
                ret
.down:          inc  b                         ; DOWN: {x, s+1}
                call ladder_exists
                ret  nc
                ld   a, b
                cp   STOREY_COUNT
                jr   nz, .mid
                call cur_room_desc             ; {x,2}: down-exit
                ld   de, RD_EXD_D
                add  hl, de
                ld   a, (hl)
                cp   EXIT_NONE
                jr   z, .no
                ld   (EXIT_DEST), a
                ld   a, EX_DOWN
                ld   (EXIT_KIND), a
                ld   a, (ix+E_X)
                ld   (EXIT_COL), a
                ld   a, STOREY_COUNT - 1
                ld   (EXIT_STOREY), a
                call .mid                      ; animate the first step down
                ret  c
                xor  a                         ; blocked: cancel the exit
                ld   (EXIT_KIND), a
                ret
.mid:           call get_box
                ld   a, (TMP6)
                add  a, b
                ld   b, a
                call box_free
                jr   c, .blk
                ld   (ix+E_Y), b
                ld   a, (TMP6)
                ld   (ix+E_AIDIR), a
                ld   (ix+E_MODE), M_MOVE
                scf
                ret
.blk:           ld   a, 1                      ; blocked by an entity: no step;
                ld   (CLIMB_BLK), a            ; try_player_turn makes it a wait
                xor  a                         ; CF = 0
                ret

;------------------------------------------------------------------------------
; try_horizontal — IX = player, D = dx. Attack (bump) or move / exit.
; B3B-5: the leading cell (lead_cell) decides terrain first: a wall / block =
; no turn; a closed door plank = hero_door (open: 1 turn, no move; locked: a
; message, no turn). A step onto x == the pit col on the storey-0 floor
; falls (hero_fall, game.md §2.5).
;------------------------------------------------------------------------------
try_horizontal:
                call on_ladder
                ret  z                         ; mid-ladder: L/R illegal (CF = 0? see below)
                ld   a, d
                ld   (TMP6), a                 ; dx
                call find_target               ; A = target slot / $FF
                cp   $FF
                jr   z, .move
                ld   b, a
                call face_tmp6
                ld   a, b
                call do_attack
                scf
                ret
.move:
                call get_box
                ld   a, (TMP6)
                add  a, c
                ld   c, a                      ; nx
                ld   a, (TMP6)                 ; B3B-5: terrain at the leading col
                call lead_cell
                jr   c, .solid
                ld   a, (TMP6)
                cp   1
                jr   z, .right
                ld   a, c
                or   a
                jr   nz, .inside               ; nx >= 1
                ; entering col 0: left exit on this storey?
                push bc
                push de
                call storey_ref
                ld   b, a
                ld   (EXIT_STOREY), a
                ld   a, EX_LEFT
                call exit_h
                pop  de
                pop  bc
                ret  nc
                ld   (EXIT_DEST), a
                ld   a, EX_LEFT
                jr   .exit
.right:         ld   a, c
                add  a, d
                dec  a                         ; right col
                cp   ROOM_COLS - 1
                jr   c, .inside
                push bc
                push de
                call storey_ref
                ld   b, a
                ld   (EXIT_STOREY), a
                ld   a, EX_RIGHT
                call exit_h
                pop  de
                pop  bc
                ret  nc
                ld   (EXIT_DEST), a
                ld   a, EX_RIGHT
.exit:          ld   (EXIT_KIND), a
.inside:
                call box_free
                jr   c, .blocked
                ld   (ix+E_X), c
                call face_tmp6
                ld   (ix+E_MODE), M_MOVE
                ld   a, b                      ; B3B-5 pit (game.md §2.5): standing on
                add  a, e                      ; storey 0 with x == the pit col -> fall
                cp   FLOOR_ROW0
                jr   nz, .ok
                ld   a, RD_PITCOL
                call desc_byte                 ; (0 = none; x >= 1 never matches)
                cp   c
                jp   z, hero_fall              ; lowram: CF = 1
.ok:            scf
                ret
.solid:         and  TF_DOOR                   ; wall / block: CF = 0 (and), no turn
                ret  z
                ld   a, (TMP6)
                jp   hero_door                 ; lowram: opened (CF = 1) / locked (0)
.blocked:       xor  a
                ld   (EXIT_KIND), a            ; CF = 0 (xor)
                ret

; face_tmp6 / face_dx — set facing from TMP6 / D (dx).  Clobbers: A
face_tmp6:      ld   a, (TMP6)
                jr   face_a
face_dx:        ld   a, d
face_a:         or   a
                ret  z
                bit  7, a
                jr   z, .r
                set  EF_LEFT_BIT, (ix+E_FLAGS)
                ret
.r:             res  EF_LEFT_BIT, (ix+E_FLAGS)
                ret

;------------------------------------------------------------------------------
; try_quaff — G: hp < max and potions > 0 -> heal 8 (capped), 1 turn.
;------------------------------------------------------------------------------
try_quaff:
                ld   a, (ix+E_POT)
                or   a
                ret  z                         ; CF = 0
                ld   a, (ix+E_HP)
                cp   (ix+E_MAXHP)
                ret  nc                        ; hp >= max -> refuse (CF=0)
                add  a, QUAFF_HEAL
                cp   (ix+E_MAXHP)
                jr   c, .ok
                ld   a, (ix+E_MAXHP)
.ok:            ld   (ix+E_HP), a
                dec  (ix+E_POT)
                ld   (ix+E_FLT), FLASH_TICKS
                ld   (ix+E_FLA), ATTR_HEAL
                call msg_begin
                ld   hl, str_quaff
                call print_str
                scf
                ret

;==============================================================================
; COMBAT
;------------------------------------------------------------------------------
; find_target — IX = attacker, TMP6 = direction (+1/-1). Nearest hostile-to-IX
; entity in reach in that direction (prototype §6.1). A mid-ladder body is never
; a target but still ends the scan if it is the nearest (review B: the Wizard's
; zap can't pass a climber). Out: A = slot or $FF, TMP3 = its gap. The player scans the LIVE_LIST for EF_HOSTILE; a monster
; only ever targets the player (slot 0), so it checks that one entity.
; Clobbers: A, BC, DE, HL (IX preserved)
;------------------------------------------------------------------------------
find_target:
                call get_box
                ld   a, c
                ld   (TMP0), a                 ; ax
                ld   a, b
                ld   (TMP1), a                 ; ay
                ld   a, d
                ld   (TMP2), a                 ; aw
                ld   a, e
                ld   (TMP3), a                 ; ah
                KFIELD KT_REACH
                ld   (TMP4), a
                ld   a, $FF
                ld   (TMP5), a                 ; best slot
                ld   (LAST_HIT_SLOT), a        ; best gap
                ld   a, (ix+E_FLAGS)
                push ix
                and  EF_PLAYER
                jr   nz, .player
                ld   ix, P_ENTITIES            ; monster: the hero only
                ld   c, 0
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                call z, .cand
                jr   .done
.player:        ld   a, (LIVE_N)
                or   a
                jr   z, .done
                ld   b, a
                ld   hl, LIVE_LIST
.pl:            push bc
                push hl
                ld   c, (hl)                   ; slot
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                ld   a, (ix+E_FLAGS)
                and  EF_HOSTILE | EF_DYING
                cp   EF_HOSTILE
                call z, .cand
                pop  hl
                ld   de, 5
                add  hl, de
                pop  bc
                djnz .pl
.done:          pop  ix
                ld   a, (LAST_HIT_SLOT)
                ld   (TMP3), a                 ; best gap (for the zap)
                ld   a, (TMP5)
                cp   FT_BLOCKER
                ret  nz
                ld   a, $FF                    ; nearest body is mid-ladder: no target
                ret

.cand:          ; IX = candidate, C = its slot
                push bc
                call on_ladder
                pop  bc
                jr   nz, .cv
                ld   c, FT_BLOCKER             ; no combat on ladders, but its body
.cv:            push bc                        ; still blocks the line (zap/reach
                                               ; can't pass it). Vertical overlap:
                KFIELD KT_BH                   ;   ty <= ay+ah-1 && ay <= ty+th-1
                pop  bc
                add  a, (ix+E_Y)
                dec  a
                ld   hl, TMP1
                cp   (hl)
                ret  c
                ld   a, (TMP1)
                ld   hl, TMP3
                add  a, (hl)
                dec  a
                cp   (ix+E_Y)
                ret  c
                ld   a, (TMP6)                 ; gap in the facing direction
                cp   1
                jr   nz, .left
                ld   a, (TMP0)
                ld   hl, TMP2
                add  a, (hl)                   ; ax+aw
                ld   b, a
                ld   a, (ix+E_X)
                sub  b                         ; tx - (ax+aw)
                ret  c                         ; behind
                jr   .gap
.left:          push bc
                KFIELD KT_BW
                pop  bc
                add  a, (ix+E_X)               ; tx+tw
                ld   b, a
                ld   a, (TMP0)
                sub  b
                ret  c
.gap:           ld   hl, TMP4
                cp   (hl)
                jr   z, .inr
                ret  nc                        ; gap > reach
.inr:           ld   hl, LAST_HIT_SLOT
                cp   (hl)
                ret  nc                        ; not nearer (ties: lower slot)
                ld   (hl), a
                ld   a, c
                ld   (TMP5), a
                ret

;------------------------------------------------------------------------------
; do_attack — IX = attacker, A = target slot. Rolls to-hit (d20+atk >= 10+eva)
; then damage (1dN+bonus, saturating) — prototype §6.2, foundations F1/F2.
; Sets the attacker's ATTACK sequence + IMPACT info and the target's reaction.
; TMP3 = gap (from find_target, for the wizard zap). Clobbers: all but IX.
;------------------------------------------------------------------------------
do_attack:
                ld   (ix+E_TGT), a
                ld   (TMP2), a                 ; target slot
                ld   (ATK_PTR), ix
                ld   c, 20                     ; to-hit: d20
                call rng_mod
                inc  a
                ld   b, a
                KFIELD KT_ATK
                add  a, b
                ld   (TMP0), a                 ; d20 + atk
                ld   a, (TMP2)
                call ent_ix                    ; IX = target
                KFIELD KT_EVA
                add  a, 10
                ld   b, a
                ld   a, (TMP0)
                cp   b
                jr   c, .miss
                ld   ix, (ATK_PTR)             ; damage: 1dN + bonus
                KFIELD KT_DIE
                ld   c, a
                call rng_mod
                inc  a
                ld   b, a
                KFIELD KT_BONUS
                add  a, b
                ld   b, a
                ld   a, (TMP2)
                call ent_ix
                ld   a, (ix+E_HP)
                sub  b
                jr   nc, .nz
                xor  a                         ; saturating: HP never underflows
.nz:            ld   (ix+E_HP), a
                ld   c, RC_HURT
                or   a
                jr   nz, .alive
                set  EF_DYING_BIT, (ix+E_FLAGS) ; out of collision at once (§3.2.4)
                ld   c, RC_DEATH
.alive:         call set_reaction_at
                ld   a, 1
                jr   .res
.miss:          ld   a, (ix+E_KIND)            ; IX = target
                cp   K_KNIGHT
                jr   nz, .m0
                ld   c, RC_BLOCK               ; a miss on the Knight: BLOCK (§6.5)
                call set_reaction_at
.m0:            xor  a
.res:           ld   ix, (ATK_PTR)
                ld   (ix+E_HIT), a
                ld   b, a
                ; message code
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   z, .mmsg
                ld   a, b
                or   a
                ld   a, MSG_P_MISS
                jr   z, .setm
                ld   a, (TMP2)
                call ent_ix
                ld   a, (ix+E_HP)
                ld   ix, (ATK_PTR)
                or   a
                ld   a, MSG_P_HIT
                jr   nz, .setm
                ld   a, MSG_P_KILL
                jr   .setm
.mmsg:          ld   a, b
                or   a
                ld   a, MSG_M_HIT
                jr   nz, .setm
                ld   a, MSG_M_MISS
.setm:          ld   (ix+E_MSG), a
                call kind_seq_ptr              ; attack sequence
                ld   de, KS_ATTACK
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                call start_seq
                ld   (ix+E_ZAP), 0             ; wizard zap: gap cells, staff row
                KFIELD KT_FLAGS
                and  KF_ZAP
                ret  z
                ld   a, (TMP3)                 ; gap
                or   a
                ret  z
                ld   (ZAP_LEN), a
                ld   (ix+E_ZAP), 1
                ld   a, (ix+E_Y)
                add  a, ZAP_ROW_OFF
                ld   (ZAP_ROW), a
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   nz, .zl
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   (ZAP_COL), a              ; right of the body
                ret
.zl:            ld   a, (ix+E_X)
                ld   hl, ZAP_LEN
                sub  (hl)
                ld   (ZAP_COL), a              ; left of the body
                ret

;------------------------------------------------------------------------------
; set_reaction_at — IX = target, C = RC_*, attacker = (ATK_PTR). Priority:
; DEATH > HURT > BLOCK. react_at = the attacker's IMPACT tick (so the HURT
; follows the blow). Clobbers: A, B, DE, HL
;------------------------------------------------------------------------------
set_reaction_at:
                ld   hl, (ATK_PTR)
                ld   e, (hl)                   ; attacker kind (E_KIND = 0)
                ld   d, 0
                ld   hl, kind_seqs + KS_IMPACT
                ld   b, KS_STRIDE
.m:             add  hl, de                    ; + kind * KS_STRIDE
                djnz .m
                ld   b, (hl)                   ; impact tick
                ld   a, (ix+E_REACT)
                cp   RC_DEATH
                ret  z                         ; death sticks
                ld   a, c
                cp   RC_BLOCK
                jr   nz, .set
                ld   a, (ix+E_REACT)
                or   a
                ret  nz                        ; never downgrade to BLOCK
.set:           ld   (ix+E_REACT), c
                ld   (ix+E_REACTAT), b
                ret

; kind_seq_ptr — HL = kind_seqs + kind(IX)*KS_STRIDE.  Clobbers: A, B, DE, HL
kind_seq_ptr:
                ld   e, (ix+E_KIND)
                ld   d, 0
                ld   hl, kind_seqs
                ld   a, e
                or   a
                ret  z
                ld   b, a
                ld   e, KS_STRIDE
.m:             add  hl, de
                djnz .m
                ret

; start_seq — IX mode SEQ at sequence HL.  Clobbers: A
start_seq:
                ld   (ix+E_SEQL), l
                ld   (ix+E_SEQH), h
                ld   (ix+E_TMR), 0
                ld   (ix+E_MODE), M_SEQ
                ret

;==============================================================================
; MONSTER AI (prototype §6.4). IX = monster (active, CUR_ROOM, not pending/dying).
; Clobbers: all but IX.
;==============================================================================
ai_monster:
                call ix_slot
                ld   (ACT_SLOT), a
                ; act every 2 turns (slime): act on even TURN_COUNTER
                KFIELD KT_PERIOD
                cp   2
                jr   nz, .go
                ld   a, (TURN_COUNTER)
                and  1
                ret  nz
.go:
                ; --- yield rule (§6.4): hero mid-ladder and I block its climb.
                ; Checked against the hero's whole remaining path (cork_check),
                ; not just the next step, so a monster already parked on the
                ; ladder end moves off before the hero reaches it.
                call get_box
                call cork_check
                jr   nc, .ny2
                ; mid-ladder (non-flyer): yield ALONG the ladder, away from the
                ; hero = the hero's own climb dir; never sideways off the shaft
                ; (§3.4 snap). Blocked -> wait. AIDIR follows so it keeps going.
                call on_ladder
                jr   nz, .yside
                ld   a, (P_ENTITIES + E_AIDIR)
                ld   e, a
                ld   d, 0
                ld   a, 1
                ld   (YIELD_FLAG), a
                push de
                call try_step
                pop  de
                jr   nc, .yend
                ld   (ix+E_AIDIR), e
.yend:          xor  a
                ld   (YIELD_FLAG), a
                ret
.yside:
                ld   a, (P_ENTITIES + E_X)
                ld   (TMP5), a                 ; shaft col
                ; step away from the shaft col (x only)
                ld   a, (TMP5)
                cp   (ix+E_X)
                ld   d, 1
                jr   c, .ya                    ; shaft left of me -> go right
                jr   nz, .yl
                ld   a, (TMP5)                 ; exactly on the shaft: toward
                cp   16                        ; the roomier side
                jr   c, .ya
.yl:            ld   d, $FF
.ya:            ld   e, 0
                ld   a, 1
                ld   (YIELD_FLAG), a           ; moving away may stay on the path
                push de
                call try_step_face
                pop  de
                jr   c, .yend
                ld   a, d                      ; that side blocked (a neighbour):
                neg                            ; try the other one, else wait —
                ld   d, a                      ; two monsters side by side can't
                ld   e, 0                      ; pin the hero on the ladder
                call try_step_face
                jr   .yend
.ny2:
                KFIELD KT_FLAGS
                and  KF_FLYER
                jp   nz, ai_flyer
                ; ================= WALKER =================
                call attack_if_reach
                ret  c
                call storey_ref
                ld   b, a
                ld   a, (PL_STOREY)
                ld   c, a                      ; C = player storey
                ld   a, b
                ld   (TMP4), a                 ; my storey
                cp   c
                jr   nz, .other
                call is_standing
                jr   nz, .other
                ; same storey, standing: step toward the player
                call dx_to_player              ; D = dx (0 if aligned)
                ld   a, d
                or   a
                ret  z
                ld   e, 0
                jp   try_step_face
.other:
                KFIELD KT_FLAGS
                and  KF_CLIMBER
                jr   z, .patrol
                call on_ladder
                jr   nz, .seek
                ; mid-ladder: continue in ai_dir
                ld   d, 0
                ld   e, (ix+E_AIDIR)
                jp   try_step
.seek:          ; C = player storey, TMP4 = my storey
                ld   a, (TMP4)
                ld   b, a
                ld   a, c
                cp   b
                ret  z
                jr   c, .wantup
                ; want down: segment {col, s+1}, s+1 < STOREY_COUNT (exit excluded)
                ld   a, b
                inc  a
                cp   STOREY_COUNT
                ret  nc
                ld   b, a
                ld   a, 1
                jr   .find
.wantup:        ld   a, b
                or   a
                ret  z                         ; {col,0} is an exit: excluded
                ld   a, $FF
.find:          ld   (TMP6), a                 ; climb dy
                ; nearest segment {col, B} in this room
                call nearest_ladder            ; A = col or $FF
                cp   $FF
                ret  z
                cp   (ix+E_X)
                jr   z, .at
                ld   d, 1
                jr   nc, .tw
                ld   d, $FF
.tw:            ld   e, 0
                jp   try_step_face
.at:            ; at the shaft: climb only if the segment is clear (no head-on)
                ld   c, a                      ; B = segment storey (its lower end)
                ld   a, b                      ; shaft rect: rows 9(B-1) .. 9B+7
                dec  a                         ; (upper standing top .. lower air bottom)
                MUL_STOREY b
                ld   b, a
                ld   d, FEAT_W
                ld   e, 2 * STOREY_ROWS - 1
                call box_free
                ret  c                         ; someone on it -> wait
                ld   d, 0
                ld   a, (TMP6)
                ld   e, a
                ld   (ix+E_AIDIR), a
                jp   try_step
.patrol:        ; non-climber on another storey: pace in the facing direction
                ld   d, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .p1
                ld   d, $FF
.p1:            ld   e, 0
                push de
                call try_step_face
                pop  de
                ret  c
                ld   a, d
                neg
                ld   d, a
                ld   e, 0
                jp   try_step_face

; nearest_ladder — nearest segment with storey B in the current room to IX.x.
; Out: A = col or $FF.  Preserves B.  Clobbers: A, C, DE, HL
nearest_ladder:
                push bc
                call cur_room_desc
                ld   de, RD_LADDERS
                add  hl, de
                ld   c, (hl)
                inc  hl
                ld   a, $FF
                ld   (TMP5), a                 ; best col
                ld   (TMP7), a                 ; best dist
                inc  c
.l:             dec  c
                jr   z, .done
                ld   e, (hl)                   ; col
                inc  hl
                ld   a, (hl)                   ; s
                inc  hl
                cp   b
                jr   nz, .l
                ld   a, e
                sub  (ix+E_X)
                jr   nc, .p
                neg
.p:             ld   d, a
                ld   a, (TMP7)
                cp   d
                jr   c, .l
                jr   z, .l
                ld   a, d
                ld   (TMP7), a
                ld   a, e
                ld   (TMP5), a
                jr   .l
.done:          pop  bc
                ld   a, (TMP5)
                ret

; box_vs_ix — CF = 1 if box (C,B,D,E) overlaps IX's body.  Clobbers: A, HL
box_vs_ix:
                KFIELD KT_BW
                add  a, (ix+E_X)
                dec  a
                cp   c
                jr   c, .no
                ld   a, c
                add  a, d
                dec  a
                cp   (ix+E_X)
                jr   c, .no
                KFIELD KT_BH
                add  a, (ix+E_Y)
                dec  a
                cp   b
                jr   c, .no
                ld   a, b
                add  a, e
                dec  a
                cp   (ix+E_Y)
                jr   c, .no
                scf
                ret
.no:            or   a
                ret

; dx_to_player — D = sign(player.x - x) (0 if equal).  Clobbers: A
dx_to_player:
                ld   a, (P_ENTITIES + E_X)
                ld   d, 0
                cp   (ix+E_X)
                ret  z
                ld   d, 1
                ret  nc
                ld   d, $FF
                ret

; attack_if_reach — if the player is in reach (either side) face + attack.
; CF = 1 if attacked.
attack_if_reach:
                ; Monsters only ever target the hero, whose box/state is cached
                ; for the turn (cache_player), so this is one direct test instead
                ; of two target scans (~0.6k T vs ~2k T per monster).
                ld   a, (PL_LADDER)
                or   a
                jr   nz, .no                   ; hero mid-ladder: no combat (§4.2)
                call on_ladder
                jr   z, .no                    ; I'm on a ladder: no combat
                call get_box
                ld   a, (PL_Y)                 ; vertical overlap
                ld   hl, PL_H
                add  a, (hl)
                dec  a
                cp   b
                jr   c, .no
                ld   a, b
                add  a, e
                dec  a
                ld   hl, PL_Y
                cp   (hl)
                jr   c, .no
                ld   a, (PL_X)
                cp   c
                jr   c, .left
                ld   a, c                      ; hero to the right: gap = px-(x+w)
                add  a, d
                ld   b, a
                ld   a, (PL_X)
                sub  b
                jr   c, .no
                ld   e, 1
                jr   .gap
.left:          ld   a, (PL_X)                 ; hero to the left: gap = x-(px+pw)
                ld   hl, PL_W
                add  a, (hl)
                ld   b, a
                ld   a, c
                sub  b
                jr   c, .no
                ld   e, $FF
.gap:           ld   (TMP3), a                 ; gap
                ld   b, a
                KFIELD KT_REACH
                cp   b
                jr   c, .no                    ; gap > reach
                ld   a, e
                ld   (TMP6), a
                call face_tmp6
                xor  a                         ; target = slot 0
                call do_attack
                scf
                ret
.no:            or   a
                ret

;------------------------------------------------------------------------------
; try_step_face / try_step — move IX by (D=dx, E=dy) if legal: body limits
; (cols 1..30; monsters treat 0/31 as walls), no sideways step while mid-ladder
; (§3.4 snap), box_free, cork_check, and the flyer ladder-end rule (§3.5, rule
; by user 2026-10-02): a flyer that started its turn inside a ladder-end box
; (FLY_INBOX != 0, set by ai_flyer) may only keep crossing (dx = its facing)
; or step out of the box (flyer_lcost at the new x = 0); never dx = 0 and
; never a reversal that stays inside. Entering a box is free. Yield steps
; (YIELD_FLAG) never see the rule (FLY_INBOX = 0 outside ai_flyer).
; The flyer band is NOT checked here: callers keep it by construction (chase
; targets 9s+1, wander uses clamp_band).
; try_step_face also sets facing from dx. CF = 1 if moved.
; B3B-5 (horizontal steps only): the leading cell's TILE_FLAGS (lead_cell):
; solid = blocked, except a closed door plank, which mon_door opens for an
; opener (the step is spent, CF = 1, nothing moves; game.md §9.1); and a
; walker never steps onto x == the pit col on the storey-0 floor (§2.5).
; Clobbers: A, BC, DE, HL, TMP6 (try_step_face), TMP7 (flyer_lcost)
; Cost of the flyer rule: 24 T when FLY_INBOX = 0 (the common case); B3B-5
; terrain ~300 T a horizontal step (+~250 T for a storey-0 walker).
;------------------------------------------------------------------------------
try_step_face:
                ld   a, d
                ld   (TMP6), a
                call try_step
                ret  nc
                call face_tmp6
                scf
                ret

try_step:
                ld   a, d
                or   a
                jr   z, .vert
                push de
                call on_ladder                 ; Z = mid-ladder (never for flyers)
                pop  de
                jr   z, .no                    ; sideways off a shaft: illegal
.vert:          push de
                call get_box
                pop  hl                        ; H = dx, L = dy
                ld   a, c
                add  a, h
                ld   c, a
                or   a
                jr   z, .no                    ; col 0
                cp   ROOM_COLS
                jr   nc, .no
                add  a, d
                dec  a
                cp   ROOM_COLS - 1
                jr   nc, .no                   ; right col >= 31
                ld   a, b
                add  a, l
                ld   b, a
                cp   PLAY_ROWS
                jr   nc, .no
                push hl                        ; B3B-5 terrain
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   z, .walk
                ld   a, b                      ; flyer: the new box must end in
                add  a, e                      ; the playfield (box_solid reads
                cp   PLAY_ROWS + 1             ; ROOM_MAP rows y .. y+h-1)
                jr   nc, .npop
                call box_solid                 ; flyer: every cell of the new box
                jr   c, .npop                  ; (arch / lintel of an open door, §9.1;
                jr   .tpop                     ; doors never open for flyers); no pits
.walk:          pop  hl
                push hl
                ld   a, h                      ; walkers: horizontal steps only (a
                or   a                         ; climb stays in its shaft)
                jr   z, .tpop
                call lead_cell                 ; A = dx
                jr   c, .solid
                ld   a, b                      ; walkers never step onto x == the pit
                                               ; col on storey 0 (game.md §2.5)
                add  a, e
                cp   FLOOR_ROW0
                jr   nz, .tpop
                push de
                ld   a, RD_PITCOL
                call desc_byte
                pop  de
                cp   c
                jr   z, .npop
.tpop:          pop  hl
.tok:           push hl
                call box_free
                pop  hl
                jr   c, .no
                ld   a, (FLY_INBOX)            ; flyer inside a ladder-end box?
                or   a
                jr   nz, .inbox
.cork:          ld   a, (YIELD_FLAG)
                or   a
                jr   nz, .go
                call cork_check                ; never re-cork a climbing hero
                jr   c, .no
.go:
                ld   (ix+E_X), c
                ld   (ix+E_Y), b
                ld   (ix+E_MODE), M_MOVE
                scf
                ret
.npop:          pop  hl
.no:            or   a
                ret
.solid:         and  TF_DOOR                   ; a closed door: mon_door (lowram)
                jr   z, .npop                  ; decides (game.md §9.1)
                pop  hl
                ld   a, h                      ; dx = the door's side
                jp   mon_door
.inbox:         ; H = dx. Keep crossing (dx = facing) or leave the box.
                ld   a, h
                or   a
                jr   z, .no                    ; x kept: would stay inside
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .fr
                neg                            ; facing left: dx -1 -> 1
.fr:            dec  a
                jr   z, .cork                  ; continuing the crossing
                call flyer_lcost               ; reversal: only out of the box
                or   a                         ; (C = new x, D = w)
                jr   nz, .no
                jr   .cork

;------------------------------------------------------------------------------
; cork_check — CF = 1 if box (C,B,D,E) overlaps any box on the hero's remaining
; climb path (next step .. the ladder-end standing box) while the hero is
; mid-ladder. Complements the §6.4 yield rule so a yielded monster can't step
; straight back onto the shaft end (no ladder corking, no forced waits).
; Preserves BC, DE, IX.  Clobbers: A, HL
;------------------------------------------------------------------------------
cork_check:
                ld   a, (PL_LADDER)            ; fast path: hero not mid-ladder
                or   a
                ret  z                         ; CF = 0
                push ix
                push bc
                push de
                ld   ix, P_ENTITIES
                ld   a, (ix+E_Y)
                ld   (TMP5), a                 ; saved y
.probe:         ld   a, (ix+E_Y)
                add  a, (ix+E_AIDIR)
                ld   (ix+E_Y), a               ; next box along the path
                pop  de
                pop  bc
                push bc
                push de
                call box_vs_ix
                jr   c, .hit
                call is_standing               ; reached the ladder end?
                jr   nz, .probe
                or   a
.hit:           ld   a, (TMP5)                 ; restore y (flags kept)
                ld   (ix+E_Y), a
                jr   .out
.free:          or   a
.out:           pop  de
                pop  bc
                pop  ix
                ret

;------------------------------------------------------------------------------
; ai_flyer — Bat / Ghost (prototype §6.4). Band: 9s <= y <= 9s+8-h (game.md §2.1).
; Ladder ends (§3.5, rule by user 2026-10-02): flyers may cross a shaft but
; never block the hero. FLY_INBOX = overlap with a ladder-end box at turn
; start (flyer_lcost, the turn's only call unless a reversal is tried inside
; a box); try_step enforces "keep crossing or leave". Inside a box the flyer
; moves before anything else, x only: chase dx first (0: facing), then the
; other way. Neither legal (fully boxed by entities) -> attack if in reach,
; else stay. FLY_INBOX is 0 again on return.
; Clobbers: all but IX.
;------------------------------------------------------------------------------
ai_flyer:
                call get_box
                call flyer_lcost
                ld   (FLY_INBOX), a
                call .body
                xor  a
                ld   (FLY_INBOX), a
                ret
.body:          or   a
                jr   z, .free
                call dx_to_player              ; preferred dx: the chase
                ld   a, d
                or   a
                jr   nz, .esc
                inc  d                         ; aligned: facing
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .esc
                ld   d, $FF
.esc:           ld   e, 0
                push de
                call try_step_face
                pop  de
                ret  c
                ld   a, d
                neg
                ld   d, a
                ld   e, 0
                call try_step_face
                ret  c
                jp   attack_if_reach           ; fully boxed: may attack, else stays
.free:
                call attack_if_reach
                ret  c
                call storey_ref
                ld   (TMP4), a                 ; my storey s
                ld   a, (PL_STOREY)
                ld   hl, TMP4
                cp   (hl)
                jr   nz, .wander
                ; same storey: bat jitter first (RNG order §6.2)
                KFIELD KT_FLAGS
                and  KF_BAT
                jr   z, .chase
                ld   c, 4
                call rng_mod
                or   a
                jr   z, .wander
.chase:
                call dx_to_player
                ; stop at gap 0: if the adjacent box in dx is the player, dx = 0
                ld   a, d
                or   a
                jr   z, .dy
                push de
                call get_box
                pop  hl
                ld   a, c
                add  a, h
                ld   c, a
                push hl
                push ix
                ld   ix, P_ENTITIES
                call box_vs_ix
                pop  ix
                pop  de
                jr   nc, .dy
                ld   d, 0
.dy:            ; dy = sign(9s+1 - y)
                ld   a, (TMP4)
                MUL_STOREY b
                inc  a                         ; 9s+1: the cruising row
                ld   e, 0
                cp   (ix+E_Y)
                jr   z, .try
                ld   e, 1
                jr   nc, .try
                ld   e, $FF
                jr   .try
.wander:
                KFIELD KT_FLAGS
                and  KF_BAT
                jr   z, .ghost
                ; bat: dx = facing (reverse at walls), dy = rng(3)-1
                ld   d, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .bf
                ld   d, $FF
.bf:            ld   a, (ix+E_X)
                add  a, d
                jr   z, .rev                   ; would enter col 0
                ld   c, a
                KFIELD KT_BW
                add  a, c
                dec  a
                cp   ROOM_COLS - 1
                jr   c, .bok                   ; right col <= 30
.rev:           ld   a, d
                neg
                ld   d, a
.bok:           push de
                ld   c, 3
                call rng_mod
                dec  a
                pop  de
                ld   e, a
                call clamp_band
                jr   .try
.ghost:         call dx_to_player
                ld   e, 0
.try:           ; (dx,dy) -> (dx,0) -> (0,dy) -> wait
                ld   a, d
                or   e
                ret  z
                push de
                call try_step_face
                pop  de
                ret  c
                ld   a, d
                or   a
                jr   z, .t2
                push de
                ld   e, 0
                call try_step_face
                pop  de
                ret  c
.t2:            ld   a, e
                or   a
                ret  z
                ld   d, 0
                jp   try_step

;------------------------------------------------------------------------------
; flyer_lcost — B8 (user bug: the Ghost parked on a ladder end and the hero
; could not get past; rule by user 2026-10-02, §3.5: flyers may cross a shaft
; but never wait / attack / stop / reverse inside a ladder-end box).
; A = how many of the cols C .. C+D-1 lie in a
; ladder-end box of IX's storey t = the standing box at either end of a
; segment, the box the climbers' "no head-on" rule keeps clear (§6.4): the
; bottom end of {col, t} and the top end of {col, t+1}, cols col..col+2. A
; flyer's band lies inside its storey's standing rows, so only the cols
; decide. 0 = clear. Exit shafts count ({col,0} bottom, {col,2} top); a
; stacked shaft counts twice (harmless: only 0 / non-0 is used).
; Called once per flyer turn (ai_flyer) + once per reversal tried inside a box.
; Preserves BC, DE, IX.  Clobbers: A, HL, TMP7.  ~330 T + ~75 T per segment
; (~95 T for one of this storey).
;------------------------------------------------------------------------------
flyer_lcost:
                push bc
                push de
                ld   e, d                      ; E = w
                call storey_ref                ; A = t (flyer: its band's storey)
                ld   b, a
                push de
                call cur_room_desc             ; HL = descriptor (A, DE)
                pop  de
                ld   a, l
                add  a, RD_LADDERS
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a                      ; HL -> n_ladders
                ld   d, 0                      ; D = overlap count
                ld   a, (hl)
.l:             or   a
                jr   z, .done
                ld   (TMP7), a                 ; segments left
                inc  hl
                inc  hl                        ; -> s
                ld   a, (hl)
                sub  b
                cp   2                         ; s == t or t + 1?
                jr   nc, .n
                dec  hl
                ld   a, (hl)                   ; col
                inc  hl
                sub  c                         ; k - x for k = col .. col+2:
                cp   e                         ; inside the body iff < w
                jr   nc, $+3                   ; (unsigned: k < x wraps high)
                inc  d
                inc  a
                cp   e
                jr   nc, $+3
                inc  d
                inc  a
                cp   e
                jr   nc, $+3
                inc  d
.n:             ld   a, (TMP7)
                dec  a
                jr   .l
.done:          ld   a, d
                pop  de
                pop  bc
                ret

; clamp_band — E = dy clamped so IX stays in its storey air band.  Clobbers A, B, HL
clamp_band:
                ld   a, (TMP4)                 ; storey
                MUL_STOREY b
                ld   b, a                      ; 9s
                ld   a, (ix+E_Y)
                add  a, e
                cp   b
                jr   c, .z                     ; above band top
                push af
                KFIELD KT_BH
                ld   h, a
                ld   a, b
                add  a, STOREY_AIR
                sub  h                         ; 9s+8-h
                ld   h, a
                pop  af
                cp   h
                ret  z
                ret  c
.z:             ld   e, 0
                ret

;==============================================================================
; materialise — step 3 of §3.2: PENDING monsters in CUR_ROOM whose box is free
; appear (horizontal followers walk in from the edge column; others pop in).
; Clobbers: all but IY.
;==============================================================================
materialise:
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   c, 1
.lp:            push bc
                ld   a, c
                ld   (ACT_SLOT), a
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE | EF_PENDING
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                call get_box
                call box_free
                jr   c, .next
                res  EF_PENDING_BIT, (ix+E_FLAGS)
                call build_live                ; it now collides for later checks
                call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   (ix+E_DFID), $FF
                bit  EF_WALKIN_BIT, (ix+E_FLAGS)
                jr   z, .next
                res  EF_WALKIN_BIT, (ix+E_FLAGS)
                ld   a, (ix+E_X)
                cp   1
                ld   a, 0
                jr   z, .edge                  ; left edge: from col 0
                ld   a, (ix+E_X)
                inc  a
                add  a, a
                add  a, a
                add  a, a                      ; right edge: from x+1
.edge:          ld   (ix+E_PX), a
                ld   (ix+E_MODE), M_MOVE
.next:          ld   de, P_ENT_STRIDE
                add  ix, de
                pop  bc
                inc  c
                ld   a, c
                cp   P_MAX_ENT
                jr   c, .lp
                ret

;==============================================================================
; resolve_monsters — step 2: every non-pending, living monster in CUR_ROOM acts
; in slot order. Then step 3 materialise.  Clobbers: all but IY.
;==============================================================================
resolve_monsters:
                call cache_player
                ld   a, 1
.lp:            ld   (MON_SLOT), a
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                jr   nz, .next                 ; player already dying: stand down
                call ai_monster
.next:          ld   a, (MON_SLOT)
                inc  a
                cp   P_MAX_ENT
                jr   c, .lp
                jp   materialise

;------------------------------------------------------------------------------
; cache_player — the hero's box / storey / mid-ladder flag for this turn's
; monster phase (the hero doesn't move while monsters act).  Clobbers: A,BC,DE,HL
;------------------------------------------------------------------------------
cache_player:
                push ix
                ld   ix, P_ENTITIES
                call get_box
                ld   a, c
                ld   (PL_X), a
                ld   a, b
                ld   (PL_Y), a
                ld   a, d
                ld   (PL_W), a
                ld   a, e
                ld   (PL_H), a
                call storey_ref
                ld   (PL_STOREY), a
                call on_ladder
                ld   a, 0
                jr   nz, .n
                inc  a
.n:             ld   (PL_LADDER), a
                pop  ix
                ret

;==============================================================================
; POTIONS (prototype §6.6) — end-of-turn pickup. Player standing, body cols
; cover a potion cell (row 9s+7) of its storey, potions < 9.
;==============================================================================
potion_pickup:
                ld   ix, P_ENTITIES
                ld   a, (ix+E_FLAGS)
                and  EF_DYING
                ret  nz
                call is_standing
                ret  nz
                ld   a, (ix+E_POT)
                cp   MAX_POTIONS
                ret  nc                        ; full pack: leave it on the floor
                call storey_ref
                ld   (TMP4), a
                call get_box                   ; C = x, D = w (B clobbered)
                ld   a, (TMP4)
                call storey_row
                ld   b, a
.c:             push bc
                push de
                ld   a, ROOM_MAP >> 8
                ld   (TMP1), a
                call map_cell                  ; HL = ROOM_MAP cell
                ld   a, (hl)
                cp   T_POTION
                jr   z, .take
                pop  de
                pop  bc
                inc  c
                dec  d
                jr   nz, .c
                ret
.take:          pop  de
                pop  bc
                push hl                        ; map cell: cleared only once the
                push bc                        ; id is found (else it would vanish
                ; potion id from the room list (col C, storey TMP4)   untracked)
                call cur_room_desc
                ld   de, RD_LADDERS
                add  hl, de
                ld   a, (hl)
                add  a, a
                inc  a
                ld   e, a
                ld   d, 0
                add  hl, de                    ; -> potion count
                ld   b, (hl)
                inc  hl
                ld   a, b
                or   a
                jr   z, .none                  ; empty list: djnz would run 256x
.pl:            ld   a, (hl)                   ; id
                inc  hl
                ld   e, (hl)                   ; col
                inc  hl
                ld   d, (hl)                   ; s
                inc  hl
                push af
                ld   a, e
                cp   c
                jr   nz, .pn
                ld   a, (TMP4)
                cp   d
                jr   z, .found
.pn:            pop  af
                djnz .pl
.none:          pop  bc                        ; map/list mismatch: leave the tile
                pop  hl
                ret
.found:         pop  af
                call bitmask
                ld   hl, POTIONS_TAKEN
                or   (hl)
                ld   (hl), a
                inc  (ix+E_POT)
                pop  bc
                pop  hl
                ld   (hl), T_AIR
                ld   de, $0101
                push bc
                call shadow_rect               ; the clean background loses it too
                pop  bc
                ld   de, $0101
                call queue_damage              ; redraw the cell next render
                call msg_begin
                ld   hl, str_found
                jp   print_str

; queue_damage — C = col, B = row, D = cols, E = rows -> PEND_DMG (next render
; restores tiles there and repairs overlapping sprites). Full queue: the last
; rect grows to the bounding box of itself + this one (a larger restore is
; always safe: every sprite it touches is repaired) and DMG_OVERFLOW counts it,
; so e.g. a zap-end restore can never be dropped.  Clobbers: A, HL
queue_damage:
                ld   a, (PEND_DMG_COUNT)
                cp   PEND_DMG_MAX
                jr   nc, .merge
                push de
                ld   l, a
                inc  a
                ld   (PEND_DMG_COUNT), a
                ld   a, l
                add  a, a
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, PEND_DMG
                add  hl, de
                pop  de
                ld   (hl), c
                inc  hl
                ld   (hl), b
                inc  hl
                ld   (hl), d
                inc  hl
                ld   (hl), e
                ret
.merge:         ld   hl, DMG_OVERFLOW
                inc  (hl)
                push bc
                push de
                ld   a, c
                add  a, d
                ld   d, a                      ; D = c1 (exclusive)
                ld   a, b
                add  a, e
                ld   e, a                      ; E = r1
                ld   hl, PEND_DMG + (PEND_DMG_MAX - 1) * 4
                ld   a, (hl)                   ; last c0
                inc  hl
                inc  hl
                add  a, (hl)                   ; last c1
                cp   d
                jr   c, .mc1
                ld   d, a                      ; D = max(c1)
.mc1:           dec  hl
                ld   a, (hl)                   ; last r0
                inc  hl
                inc  hl
                add  a, (hl)                   ; last r1
                cp   e
                jr   c, .mr1
                ld   e, a                      ; E = max(r1)
.mr1:           ld   hl, PEND_DMG + (PEND_DMG_MAX - 1) * 4
                ld   a, (hl)
                cp   c
                jr   nc, .mc0
                ld   c, a                      ; C = min(c0)
.mc0:           ld   (hl), c
                inc  hl
                ld   a, (hl)
                cp   b
                jr   nc, .mr0
                ld   b, a                      ; B = min(r0)
.mr0:           ld   (hl), b
                inc  hl
                ld   a, d
                sub  c
                ld   (hl), a                   ; cols
                inc  hl
                ld   a, e
                sub  b
                ld   (hl), a                   ; rows
                pop  de
                pop  bc
                ret

;==============================================================================
; HUD (PROTO text on panel rows 21..23 until B3B-11; never touched by sprites).
;==============================================================================
hud_status:
                ld   b, HUD_ROW
                ld   a, ATTR_HUD
                call clear_row
                ld   c, 0
                ld   a, (HERO_KIND)
                call kind_name                 ; HL = name
                call print_str
                ld   hl, str_hp
                call print_str
                ld   a, (P_ENTITIES + E_HP)
                call print_dec
                ld   a, '/'
                call print_char
                ld   a, (P_ENTITIES + E_MAXHP)
                call print_dec
                ld   hl, str_pot
                call print_str
                ld   a, (P_ENTITIES + E_POT)
                jp   print_dec

hud_room:
                ld   b, HUD_ROW + 2
                ld   a, ATTR_HUD_DIM
                call clear_row
                ld   c, 0
                ld   hl, str_room
                call print_str
                ld   a, (CUR_ROOM)
                add  a, 'A'
                jp   print_char_hud            ; A7: HUD tracking

; msg_begin — clear the message row; B/C = its first cell.  Clobbers: A, DE, HL
msg_begin:
                ld   b, HUD_ROW + 1
                ld   a, ATTR_HUD
                call clear_row
                ld   c, 0
                ret

; kind_name — HL = name string of kind A.  Clobbers: A, DE, HL
kind_name:
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, kind_names
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ret

; show_impact_msg — IX = attacker at IMPACT: print its E_MSG line.
show_impact_msg:
                ld   a, (ix+E_MSG)
                or   a
                ret  z
                push af
                call msg_begin
                pop  af
                cp   MSG_M_HIT
                jr   nc, .mon
                push af
                ld   hl, str_you
                call print_str
                pop  af
                ld   hl, str_hit
                cp   MSG_P_HIT
                jr   z, .pv
                ld   hl, str_miss
                cp   MSG_P_MISS
                jr   z, .pv
                ld   hl, str_kill
.pv:            call print_str
                ld   hl, str_the
                call print_str
                push ix
                ld   a, (ix+E_TGT)
                call ent_ix
                ld   a, (ix+E_KIND)
                pop  ix
                call kind_name
                jp   print_str
.mon:           push af
                ld   hl, str_the
                call print_str
                ld   a, (ix+E_KIND)
                call kind_name
                call print_str
                pop  af
                ld   hl, str_hits_you
                cp   MSG_M_HIT
                jr   z, .mv
                ld   hl, str_misses
.mv:            jp   print_str
