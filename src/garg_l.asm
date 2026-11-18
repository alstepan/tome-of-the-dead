;------------------------------------------------------------------------------
; garg_l.asm - GARG-CHAIN (new_monsters.md 4.1b, user 2026-11-18): the room's perched Gargoyles wake one by one.
; Low RAM (always mapped); both are entered from bank-1 perch1 (far1, bank 1 paged), IX = the Gargoyle.
;
; stir_gate - perch1 jumps here once its box is clear (no body, PENDING included; C x, D w from get_box).
;   An armed chain (GARG_STIR = storey + 1) whose storey is mine, and no Gargoyle woke yet in this monster pass
;   (GARG_SPENT, cleared by pl_seg3): wake me (jp perch1.wk, E = the facing: the hero's side) = the first perched
;   one in slot order, one a pass, the hero always acts in between. Else perch1's own rules (hero mid-ladder: stays;
;   else storey / gap, jp perch1.st). The chain ignores the hero's position / ladder.
;   Clobbers: all but IX (A, HL, E).   ~0.2k T a perched turn with the chain off (a flag test)
; stir_arm - perch1.wk (every wake: proximity or chained) after EF_GHOST is cleared: the pass is spent (GARG_SPENT); the
;   first wake of a room arms GARG_STIR = my storey + 1 and prints "THE STATUES STIR!" once, only if another perched
;   Gargoyle (active, EF_GHOST, CUR_ROOM, PENDING ones are not statues yet) stands on my storey. A wake with the chain
;   armed returns at once. Keeps E (perch1's facing), IX.   Clobbers: A, BC, HL.   ~0.5k T once a chain (+ the msg_push)
; Only the proximity wake arms: a ghost takes no damage and is never bumped (GARG-PASS), so the HP-loss / missed-bump wakes
; (solid door arrivals) never meet a perched statue, and an arrival is no trigger by ruling.
;------------------------------------------------------------------------------
stir_gate:      ld   hl, GARG_STIR
                ld   a, (hl)
                or   a
                jr   z, .no                    ; no chain armed
                inc  l                         ; GARG_SPENT = GARG_STIR + 1 (ASSERTed)
                inc  (hl)
                dec  (hl)
                jr   nz, .no                   ; a Gargoyle already woke this pass
                call storey_ref                ; (bank 2; A, HL)
                inc  a
                ld   hl, GARG_STIR
                cp   (hl)
                jr   nz, .no                   ; the other storey: not chained
                ld   a, (PL_X)
                cp   c
                ld   e, 1                      ; facing: right when the hero's x >= mine
                jr   nc, .go
                ld   e, $FF
.go:            jp   perch1.wk
.no:            ld   a, (PL_LADDER)
                or   a
                ret  nz                        ; the hero mid-ladder: stays perched
                jp   perch1.st

stir_arm:       ld   a, 1
                ld   (GARG_SPENT), a           ; this pass has its wake
                ld   a, (GARG_STIR)
                or   a
                ret  nz                        ; already armed (a proximity wake or a chained one)
                call storey_ref
                inc  a
                ld   (GARG_STIR), a
                push ix
                push de                        ; E = the facing
                ld   ix, P_ENTITIES
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT
.l:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_GHOST | EF_DYING
                cp   EF_ACTIVE | EF_GHOST
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call storey_ref                ; (A, HL; keeps B, DE)
                inc  a
                ld   hl, GARG_STIR
                cp   (hl)
                jr   nz, .n
                ld   a, TX_STIR                ; a joiner: say it once
                call msg_push                  ; (AF, BC, DE, HL; bank 1 comes back)
                jr   .x
.n:             add  ix, de
                djnz .l
.x:             pop  de
                pop  ix
                ret
                ASSERT GARG_SPENT == GARG_STIR + 1 && (GARG_STIR >> 8) == (GARG_SPENT >> 8) && EF_GHOST != EF_PENDING
