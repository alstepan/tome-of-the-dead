;==============================================================================
; trap6.asm — 3E-T16 the trap helpers R6 code calls, R6 region (r6.asm rules;
; far6 only). MEM-RECLAIM w2b: the traps runtime (trap_turn / trap_step / the
; effects) is bank-7 trap7.asm; tele_arm / tele_flash (R6 fx6, and far6 from
; trap7 tr_eff) and trap_at (R6 pickup6 drop_put) stay here.
;==============================================================================

;------------------------------------------------------------------------------
; tele_arm — the Teleport scroll (fx_read) and trap (tr_eff): EXIT_KIND =
; EX_TELE, the hero flashes TELE_FLASH_ATTR for TELE_FLASH_T ticks, SFX_DRAIN;
; a free TURN_PEND holds the turn (TP_MON, MON_AT = TELE_HOLD_T: the flash
; plays before end_turn's do_exit; act_pend skips the monsters on an exit
; turn). tele_pick repeats the flash on arrival.  Clobbers: A, HL.
;------------------------------------------------------------------------------
tele_arm:
                ld   a, EX_TELE
                ld   (EXIT_KIND), a
                call tele_flash
                ld   a, SFX_DRAIN
                call sfx_req
                ld   hl, TURN_PEND
                ld   a, (hl)
                or   a
                ret  nz                        ; the trap sequence holds it already
                ld   (hl), TP_MON
                ld   a, TELE_HOLD_T
                ld   (MON_AT), a
                ret
tele_flash:     ld   hl, P_ENTITIES + E_FLT
                ld   (hl), TELE_FLASH_T
                inc  l
                ld   (hl), TELE_FLASH_ATTR
                ret
                ASSERT TELE_HOLD_T >= TELE_FLASH_T

;------------------------------------------------------------------------------
; trap_at — E = an FL_ROOM-style byte (room | FL_S1), C = col: Z = an unspent
; TRAP_LIST entry there (HL = it), NZ = none. Callers: drop_put (pickup6: a
; drop's footprint never covers a trap col, hidden or known).
; Keeps BC, DE. Clobbers: A, HL.   ~40 T + TRAP_N x ~60 T
;------------------------------------------------------------------------------
trap_at:        push bc
                push de
                ld   a, e
                and  FL_ROOM_MASK
                bit  7, e
                jr   z, .k
                or   TRF_S1
.k:             ld   b, a                      ; B = the TR_B0 key (room | storey, not spent)
                ld   a, (TRAP_N)
                add  a, a
                add  a, TRAP_LIST & $FF
                ld   d, a                      ; D = the end (low byte)
                ld   hl, TRAP_LIST
.l:             ld   a, l
                cp   d
                jr   z, .no
                ld   a, (hl)
                and  TRF_ROOM_MASK | TRF_S1 | TRF_SPENT
                cp   b
                jr   nz, .n
                inc  l
                ld   a, (hl)
                dec  l
                and  TR_COL_MASK
                cp   c
                jr   z, .x                     ; Z: found
.n:             inc  l
                inc  l
                jr   .l
.no:            or   h                         ; NZ (H != 0)
.x:             pop  de
                pop  bc
                ret
                ASSERT FL_S1 == $80 && TRF_ROOM_MASK == FL_ROOM_MASK && (TRAP_LIST >> 8) == ((TRAP_LIST + 12) >> 8)
