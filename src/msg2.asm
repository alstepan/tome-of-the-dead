;==============================================================================
; msg2.asm — bank 2 (always mapped), after kind_tab (main.asm): the composed
; log-line helpers the bank-7 cold code calls (abil_ammo7, pickup7, xp7), moved
; out of bank 7 by LOG-FIX (bank 7 had 3 B free), + log_room (hit_line: bank 0, NEW-MON3 T1).
;==============================================================================
;------------------------------------------------------------------------------
; Composed log lines in MSG_BUF (bank 7 cannot page the text block: it runs in
; $C000, so the pieces come decoded through low-RAM tx_dec; plain ASCII is a
; valid log stream, tk_get passes chars < $80 through). Cold: once per event.
; msg_cat — append the text of string A (TX_*) at DE.  Out: DE advanced.
;           Clobbers: A, BC, HL   (~0.4k T + ~70 T per char)
; msg_kind — append kind C's name (TX_NM_KNIGHT + C).  Same.
; msg_dec — append A = 0..99 in decimal (no leading 0).  Clobbers: A, BC
; msg_end — 0-terminate at DE and log_push MSG_BUF.  Clobbers: A, B, DE, HL
;------------------------------------------------------------------------------
msg_kind:
                ld   a, c
                add  a, TX_NM_KNIGHT
msg_cat:
                push de
                call tx_dec                    ; HL = TX_DEC (A, BC, DE, HL)
                pop  de
.c:             ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  hl
                inc  de
                jr   .c
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
msg_end:
                xor  a
                ld   (de), a
                ld   hl, MSG_BUF
                jp   log_push                  ; (any bank: the ring is bank 5)

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
