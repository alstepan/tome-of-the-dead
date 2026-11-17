;------------------------------------------------------------------------------
; tele_hot.asm — BALANCE-PKG5 C1 (balance_v2 §7c, the safe Teleport landing): in the HOT_COPY image
; (INCLUDEd by panel_hot.asm inside its DISP; bank 2 runtime RAM, always mapped), because R6 (the
; caller) and low RAM had no room.
;
; tp_safe — R6 tele_pick's room filter (bank 6 paged), B = an otherwise eligible room:
; Z = keep it: pass 2 (tp_msk 0: today's rule, every eligible room), or pass 1 (tp_msk = TP_SAFE)
; and its LP record header == LR_VISITED exactly (entered before, 0 banked residents: no lazy spawn
; on arrival, no body near the landing). NZ = skip. Keeps BC, DE, HL.  Clobbers: A, F.   ~0.1k T
;------------------------------------------------------------------------------
tp_safe:        push hl
                ld   a, b
                add  a, a
                add  a, a
                add  a, a
                add  a, b                      ; 9 x room (LR_STRIDE), all of LP in one page
                add  a, LP_REC & $FF
                ld   l, a
                ld   h, LP_REC >> 8
                ld   a, (hl)                   ; LR_HDR: bit 7 VISITED, bits 0-2 the count
                xor  LR_VISITED
                ld   hl, tp_msk
                and  (hl)                      ; pass 2: 0 -> Z
                pop  hl
                ret
                ASSERT LR_STRIDE == 9 && LR_HDR == 0 && (LP_REC >> 8) == ((LP_REC + ROOM_SLOTS * LR_STRIDE - 1) >> 8)
tp_msk:         DB   0                         ; tele_pick C1: TP_SAFE (pass 1) / 0 (pass 2); runtime (HOT_COPY)
