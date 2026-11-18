;==============================================================================
; lgkeyl.asm — LARGER-D T5: kins (FLY-CUT: kload went back to lgkey0) of the level-key selection (T4 src/lgkey0.asm), moved to the low-RAM
; cold block (INCLUDEd by lowram.asm) for B0_CODE2 room. Pure GEN_SCRATCH work: bank-0 ksel calls them
; directly (low RAM is always mapped); the data is in contended RAM anyway (level_gen only, behind the card).
;==============================================================================
; kbit: 1 << r (word), r = 0..11; tstb (macro KTSTB, lgkey3.asm): A = room, HL = mask -> NZ = its bit set.
; PKG5+FLY-CUT reclaim: the ONE copy for bank-3 lgkey3 (contended either way) and bank-0 lgkey0 (were
; kbit / tstb in lgkey3 and kbit0 / tstb0 in lgkey0: 42 B each); pathm / pathm0 read this kbit. Bank-0 callers pay
; ULA contention on tstb's fetches now (level generation only, behind the card: ~+10 T a call worst).
kbit:           DUP  12, k
                DW   1 << k
                EDUP
                ASSERT (kbit >> 8) == ((kbit + 23) >> 8)
tstb:           KTSTB kbit
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
; (FLY-CUT: kload moved to bank-0 lgkey0.asm, its only caller: low RAM for fly_cut2.)
