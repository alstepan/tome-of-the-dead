;==============================================================================
; dnwin.asm — D3-11 flying damage numbers: dn_win and dn_sl, called from
; bank-0 dnum0.asm only. Placed by build: bank 0 (dnum0.asm) in a release
; build, bank 2 (the tail, dnum2.asm) in a DEBUG_KIT build (its bank 0 holds
; kit0.asm). Both banks are uncontended. (DNUM-SPRITE-FIX: dn_cr, the bank-5
; cell-row draw, is gone: bank-2 dn_cel draws on screen 2.)
;==============================================================================

; dn_win — record IX's window: C col, B row - 1, D cols, E = 2 rows.  Clobbers: none else
dn_win:
                ld   e, 2
                ld   b, (ix+DL_ROW)
                dec  b
                ld   c, (ix+DL_COL)
                ld   d, (ix+DL_W)
                ret

; dn_sl — C = slot: IX = its entity, HL = its DN_SLOT record (DS_SEEN).
; Clobbers: A, E
dn_sl:
                ld   a, c
                call ent_ix                    ; (A, E)
                ld   a, c
                add  a, a
                add  a, a
                add  a, DN_SLOT & $FF
                ld   l, a
                ld   h, DN_SLOT >> 8
                ret
                ASSERT DS_SEEN == 0 && DS_SRC == 1 && DS_FLG == 2 && DS_SNAP == 3 && (DN_SLOT & $FF) + 4 * P_MAX_ENT <= 256
