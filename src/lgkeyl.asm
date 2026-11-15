;==============================================================================
; lgkeyl.asm — LARGER-D T5: kins / kload of the level-key selection (T4 src/lgkey0.asm), moved to the low-RAM
; cold block (INCLUDEd by lowram.asm) for B0_CODE2 room. Pure GEN_SCRATCH work: bank-0 ksel calls them
; directly (low RAM is always mapped); the data is in contended RAM anyway (level_gen only, behind the card).
;==============================================================================
; kins: A = slot. The slot := KC_REC when KC_REC's 8-B string is smaller. Clobbers A, BC, DE, HL.
kins:           ld   c, a
                add  a, a
                add  a, c
                add  a, a
                add  a, a               ; 12 * slot
                add  a, KS_BEST & $FF
                ld   e, a
                ld   d, KS_BEST >> 8
                push de
                ld   hl, KC_REC
                ld   b, 8
.c:             ld   a, (de)
                cp   (hl)
                jr   nz, .d
                inc  hl
                inc  de
                djnz .c
.d:             pop  de                 ; (equal: the same result, copied again: harmless)
                ret  c                  ; slot < new
                ld   hl, KC_REC
                ld   bc, KR_LEN
                ldir
                ret

; kload: A = candidate index, DE = KC_L0 / KC_L1: its 8 B, KL_CI := index. Clobbers A, BC, DE, HL.
kload:          ld   hl, KL_CI
                add  hl, de
                ld   (hl), a
                add  a, a
                add  a, a
                add  a, a
                add  a, KS_CAND & $FF
                ld   l, a
                ld   h, KS_CAND >> 8
                ld   bc, 8
                ldir
                ret

