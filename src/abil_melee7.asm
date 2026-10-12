;==============================================================================
; abil_melee7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): the
; Warrior's power attacks (Power Strike, Whirlwind; game.md §6.2) and the
; Mage staff bonk slot. T0: refusing stubs, T1 implements them.
;==============================================================================

;------------------------------------------------------------------------------
; abil_melee — intent7 ic_disp (ABF_MELEE), IX = hero, B = ABL_*, ABIL_DESC
; loaded (abil_load). Out: L = 1 turn used / 0 refused (no turn).
; T0 stub: L = 0.  Clobbers: L
;------------------------------------------------------------------------------
abil_melee:
                ld   l, 0
                ret

;------------------------------------------------------------------------------
; melee_bonk — intent7 ic_melee, right after the melee blow (do_attack, far3),
; IX = hero, (ix+E_TGT) = the target slot, (ix+E_HIT) = 1 the blow took HP.
; D3-7 T4, the Mage staff bonk (game.md §6.1 "Release ticks" / §6.2): every
; Mage swing plays wz_bonk (CAST1 2 -> STAFF_SWING 3, replacing do_attack's
; KS_ATTACK; same KS_IMPACT, so the target's reaction tick stands); a hit
; also starts an impact-only FX, staff_bonk, built in ABIL_DESC (free during
; a melee turn; fx_start copies it): anchor = the target's front col (the one
; facing the hero; the 16-px frame reaches one col into the body), row = the
; staff row (top + PF_ROW_DY) clamped so both 8-px rows lie in the target's
; body, FXD_DELAY = WZ_WIND - 1: an impact-only FX shows its impact at
; fx_tick #delay + 1, i.e. on KS_IMPACT, with the STAFF_SWING and the HURT.
; The caller sets L = 1 after.  Clobbers: A, BC, DE, HL (IX kept)
;------------------------------------------------------------------------------
melee_bonk:
                ld   a, (ix+E_KIND)
                cp   K_WIZARD
                ret  nz
                ld   hl, wz_bonk
                call start_seq                 ; bank 2 (A)
                ld   a, (ix+E_HIT)
                or   a
                ret  z                         ; a miss / no HP lost: no bonk
                push ix
                ld   a, (ix+E_Y)
                add  a, PF_ROW_DY
                ld   b, a                      ; B = the staff row
                ld   a, (ix+E_FLAGS)
                and  EF_LEFT
                ld   c, a                      ; C = the hero's facing
                ld   a, (ix+E_TGT)
                push bc
                call ent_ix                    ; IX = target (A, E)
                call get_box                   ; C x, B y, D w, E h (A, HL)
                pop  hl                        ; H = staff row, L = facing
                ld   a, l
                rrca
                rrca
                rrca                           ; EF_LEFT -> FXDF_LEFT
                ld   (ABIL_DESC + FXD_FLAGS), a
                or   a
                ld   a, c                      ; facing right: the target's left col
                jr   z, .c
                add  a, d
                dec  a                         ; facing left: its right col
.c:             ld   (ABIL_DESC + FXD_COL), a
                ld   a, b
                add  a, e
                sub  2                         ; the target's last-but-one row
                cp   h
                jr   c, .lo
                ld   a, h                      ; min(staff row, y + h - 2)
.lo:            cp   b
                jr   nc, .row
                ld   a, b                      ; max(.., y)
.row:           ld   (ABIL_DESC + FXD_ROW), a
                ld   hl, FX_NONE * $101        ; no flight sprite
                ld   (ABIL_DESC + FXD_FIDA), hl
                ld   hl, FID_staff_bonk * $101
                ld   (ABIL_DESC + FXD_IMPA), hl
                ld   hl, (PF_IMPT << 8) | (WZ_WIND - 1)
                ld   (ABIL_DESC + FXD_DELAY), hl
                ld   hl, 1                     ; 1 segment of 0 cells
                ld   (ABIL_DESC + FXD_NSEG), hl
                xor  a
                ld   (ABIL_DESC + FXD_ATTR), a ; the frame's own attr
                ld   hl, ABIL_DESC
                call fx_start                  ; bank 2 (all but IY)
                pop  ix
                ret
                ASSERT FXDF_LEFT == EF_LEFT >> 3 && FXD_FIDB == FXD_FIDA + 1 && FXD_IMPB == FXD_IMPA + 1
                ASSERT FXD_IMPT == FXD_DELAY + 1 && FXD_SEGS == FXD_NSEG + 1 && WZ_WIND >= 1
                ASSERT ABIL_DESC_LEN >= FXD_LEN

;------------------------------------------------------------------------------
; power_fire — the power attack's strike (act_fire, fire tick): Power Strike /
; Whirlwind (game.md §6.2). In: IX = hero, B = ABL_POWER / ABL_WHIRL.
; Out: L = 1 struck.  T1 stub: L = 1.  Clobbers: L
;------------------------------------------------------------------------------
power_fire:
                ld   l, 1
                ret
