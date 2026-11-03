;==============================================================================
; dnum7h.asm — D3-11 flying damage numbers, the bank-7 high-block part (far7
; from bank-3 dn_take; header in dnum0.asm). far7 rules: no SMC, no data.
;==============================================================================

; dn_evict — the live list is full: IX = the record of the oldest live number
; (the largest DL_AGE; a tie: the later entry).  Clobbers: A, BC, HL (DE kept).
dn_evict:
                ld   hl, DN_LIVE + DL_AGE
                ld   bc, DN_LIVE_N << 8        ; C = the oldest age so far
.o:             ld   a, (hl)
                cp   c
                jr   c, .on
                ld   c, a
                push hl
                pop  ix                        ; (DL_AGE = 0: the record)
.on:            ld   a, l
                add  a, DN_LIVE_STRIDE
                ld   l, a
                djnz .o
                ret
                ASSERT DL_AGE == 0 && (DN_LIVE >> 8) == ((DN_LIVE + DN_LIVE_N * DN_LIVE_STRIDE - 1) >> 8)
