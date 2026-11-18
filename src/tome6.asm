;==============================================================================
; tome6.asm — P3 the Tome ending, R6 part (r6.asm rules: far6 only, no SMC, no
; bank-3 / bank-1 / bank-7 code or data). game.md §1.1 / §1.3, user rulings
; 2026-10-31. The bank-7 hits are tome7.asm, the aura low RAM (lowram.asm).
;   (seal_open: bank 1 tome1.asm since RECLAIM-SV R3)
;   tome_geo6   far6 from bank-7 tome_in / low-RAM tome_aura: the hero vs the lectern.
;==============================================================================

; (RECLAIM-SV R3: seal_open moved to bank 1, src/tome1.asm, far1 from boss7: R6 room for jump_pit6.)

;------------------------------------------------------------------------------
; tome_geo6 — IX = hero (passed through far6). The lectern stands on storey 1
; against the Sanctum's dead-end wall: cols 1-2 when the Sanctum is cell 9 (S
; bit 1 clear), 29-30 when it is cell 11 (LARGER-D T4). Out: L = the gap (empty cols between the
; hero's body and the lectern; 0 = adjacent), + $80 when he faces away from it;
; L = $FF: no Tome here (TOME_HP 0 — WIN2: destroyed, so no more hits / aura /
; bump, never twice; or off D8, never generated —, CUR_ROOM != LVL_SANCTUM, or
; the hero is not standing on storey 1: E_Y, so never mid-ladder / mid-jump).
; Clobbers: A, H, L (BC, DE, IX kept).   ~0.1k T (+ far6 ~0.25k)
;------------------------------------------------------------------------------
tome_geo6:
                ld   l, $FF
                ld   a, (TOME_HP)
                or   a
                ret  z
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
                jr   z, .l                     ; S = 9: the lectern on the left
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
                ASSERT !(GRID_BOT & 2) && ((GRID_BOT + 2) & 2) && LECT_COL_L + 2 == 3 && LECT_COL_R - TOME_HERO_W + 1 == 27
