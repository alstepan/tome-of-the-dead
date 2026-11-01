;==============================================================================
; msg2.asm — bank 2 (always mapped), after kind_tab (main.asm): the composed
; log-line helpers the bank-7 cold code calls (abil_ammo7, pickup7, xp7), moved
; out of bank 7 by LOG-FIX (bank 7 had 3 B free), + the result-line helpers.
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

;------------------------------------------------------------------------------
; hit_line — the spell / dagger / arrow hit line as a token stream (no tx_dec
; decode: ~1.4k T vs ~5k for msg_cat + msg_kind): pre string B (TX_SPL_SPARK + ABL_*;
; LOG-DMG: or TX_YOU_KILL, ammo_fire's kill) + kind C's name, like impact_line
; (lowram.asm; no sfx_msg: the release sound is sfx_abl's, a kill's SFX_KILL is
; requested by ln_hit). LOG-DMG: bank-0 ln_hit (log0.asm) appends pf_tgt's
; " -D HP H" (D = pf_lost) and pushes. The caller made room (log_room).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
hit_line:
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                push bc
                ld   a, BANK_TEXT
                call page_bank                 ; (A, BC)
                pop  bc
                ld   de, MSG_BUF
                ld   a, b
                call impact_line.cat           ; + the pre stream
                ld   a, c
                add  a, TX_NM_KNIGHT
                call impact_line.cat           ; + the kind name
                call ln_hit                    ; LOG-DMG (bank 0): + the tail, 0, log_push
                pop  af
                jp   restore_page
