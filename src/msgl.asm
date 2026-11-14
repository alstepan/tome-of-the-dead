;==============================================================================
; msgl.asm — NEW-MON3 T9: the low-RAM half of msg2.asm (cold, once per event; bank 2 kept msg_dec /
; log_room, which the impact / damage lines run per log event): the composed
; log-line helpers the bank-7 cold code calls (abil_ammo7, pickup7, xp7), moved
; out of bank 7 by LOG-FIX (bank 7 had 3 B free).
;==============================================================================
;------------------------------------------------------------------------------
; Composed log lines in MSG_BUF (bank 7 cannot page the text block: it runs in
; $C000, so the pieces come decoded through low-RAM tx_dec; plain ASCII is a
; valid log stream, tk_get passes chars < $80 through). Cold: once per event.
; msg_cat — append the text of string A (TX_*) at DE.  Out: DE advanced.
;           Clobbers: A, BC, HL   (~0.4k T + ~70 T per char)
; msg_kind — append kind C's name (TX_NM_KNIGHT + C).  Same.
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
msg_end:
                xor  a
                ld   (de), a
                ld   hl, MSG_BUF
                jp   log_push                  ; (any bank: the ring is bank 5)

