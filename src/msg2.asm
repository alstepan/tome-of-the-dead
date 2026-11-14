;==============================================================================
; msg2.asm — bank 2 (always mapped), after kind_tab (main.asm): msg_dec + log_room (LOG-FIX / LOG-DMG; the
; impact / damage lines run them per log event: uncontended). NEW-MON3 T9: msg_kind / msg_cat / msg_end went
; to the low-RAM cold block (msgl.asm; room for the 9-slot seq_rows here).
; msg_dec — append A = 0..99 in decimal (no leading 0) at DE.  Out: DE advanced.  Clobbers: A, BC
;==============================================================================
msg_dec:
                ld   b, '0' - 1
.t:             inc  b
                sub  10
                jr   nc, .t
                add  a, '0' + 10
                ld   c, a                      ; C = the units digit
                ld   a, b
                cp   '0'
                jr   z, .u                     ; < 10: one digit
                ld   (de), a
                inc  de
.u:             ld   a, c
                ld   (de), a
                inc  de
                ret
;------------------------------------------------------------------------------
; log_room — LOG-FIX Fix A: make room for a RESULT line (a hit / kill / burst /
; self-hit line must never be the one that is lost): with the ring full
; (LOG_QN = LOG_SLOTS) the NEWEST pending line is replaced (LOG_QN - 1, counted
; in LQ_DROP; the same as log_push_end: a pending slot is never half drawn).
; log_room_d — LOG-DMG: the same, LN_VAL = A first (spell_fire's self-bolt
; line: A = pf_lost, the caster's own loss; later strikes overwrote dh_lost).
; Keeps A, BC, DE; clobbers HL, F.   ~60 T
;------------------------------------------------------------------------------
log_room_d:
                ld   (LN_VAL), a
log_room:
                ld   hl, LOG_QN
                bit  2, (hl)                   ; = LOG_SLOTS (4)
                ret  z
                dec  (hl)
                ld   hl, LOG_Q + LQ_DROP
                inc  (hl)
                ret
                ASSERT LOG_SLOTS == 4

; hit_line: NEW-MON3 T1 -> bank-0 src/nm3_b0.asm (FARB0 from bank-7 ammo_fire; A = pre, E = kind).
