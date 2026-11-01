;==============================================================================
; tome6.asm — P3 the Tome ending, R6 part (r6.asm rules: far6 only, no SMC, no
; bank-3 / bank-1 / bank-7 code or data). game.md §1.1 / §1.3, user rulings
; 2026-10-31. The bank-7 hits are tome7.asm, the aura low RAM (lowram.asm).
;   seal_open   far6 from bank-7 grate_open on D8 (the Archmage died).
;   tome_geo6   far6 from bank-7 tome_in / low-RAM tome_aura: the hero vs the lectern.
;==============================================================================

;------------------------------------------------------------------------------
; seal_open — far6 from bank-7 grate_open on D8 (F3_GEN; the D8 grate never
; opens: game.md §1.1 "D8 has no exit"): the Archmage died — by any hand, its own Mirror Helm return
; included (deal_hit's kill -> mon_drop -> grate_open). Resident: nothing is
; unpacked on the death tick. LF_SEAL_OPEN; EG_SEAL off the lair<->Sanctum edge
; (EDGE_TAB + 4 = 6-7 or + 5 = 7-8: both bits cleared, cheaper than finding S's;
; the other edge never carries a seal), so the door is an ordinary closed door:
; it keeps its T_DOOR_LOCK plank on screen until a bump opens it (door_open reads
; the edge only; the planks then go as for any door). "THE SEAL BREAKS".
; Clobbers: A, BC, DE, HL.   ~1.5k T (the line)
;------------------------------------------------------------------------------
seal_open:
                ld   hl, LVL_FLAGS
                set  LF_SEAL_OPEN_BIT, (hl)
                ld   l, (EDGE_TAB + 4) & $FF
                res  EG_SEAL_BIT, (hl)
                inc  l
                res  EG_SEAL_BIT, (hl)
                ld   a, TX_SEAL_BREAKS
                jp   msg_push
                ASSERT (LVL_FLAGS >> 8) == ((EDGE_TAB + 5) >> 8) && LF_SEAL_OPEN == 1 << LF_SEAL_OPEN_BIT
                ASSERT EG_SEAL == 1 << EG_SEAL_BIT

;------------------------------------------------------------------------------
; tome_geo6 — IX = hero (passed through far6). The lectern stands on storey 1
; against the Sanctum's dead-end wall: cols 1-2 when the Sanctum is cell 6 (S
; bit 1 set), 29-30 when it is cell 8. Out: L = the gap (empty cols between the
; hero's body and the lectern; 0 = adjacent), + $80 when he faces away from it;
; L = $FF: no Tome here (CUR_ROOM != LVL_SANCTUM — always off D8, ROOM_NONE — or
; the hero is not standing on storey 1: E_Y, so never mid-ladder / mid-jump).
; Clobbers: A, H, L (BC, DE, IX kept).   ~0.1k T (+ far6 ~0.25k)
;------------------------------------------------------------------------------
tome_geo6:
                ld   l, $FF
                ld   a, (ix+E_Y)
                cp   TOME_HERO_Y
                ret  nz
                ld   a, (LVL_SANCTUM)
                ld   h, a
                ld   a, (CUR_ROOM)
                cp   h
                ret  nz
                ld   a, (ix+E_X)
                bit  1, h
                jr   nz, .l                    ; S = 6: the lectern on the left
                cpl                            ; right: gap = 26 - x (x <= 26: the lectern
                add  a, LECT_COL_R - TOME_HERO_W + 1    ; is solid) = (255 - x) + 27
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .t                     ; facing right = it
.aw:            or   $80
.t:             ld   l, a
                ret
.l:             sub  LECT_COL_L + 2            ; left: gap = x - 3 (x >= 3)
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   nz, .t                    ; facing left = it
                jr   .aw
                ASSERT (6 & 2) && !(8 & 2) && LECT_COL_L + 2 == 3 && LECT_COL_R - TOME_HERO_W + 1 == 27
