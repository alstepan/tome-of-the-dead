;==============================================================================
; ay.asm — A8 AY player slot: bank 3, AY_RESERVE..AY_RESERVE_END (7 KB, game.md
; §11.2) = player + songs + FX. Loaded by its own headerless tape block
; (AY_LEN from AY_RESERVE, `start`).
;
; Slot contract (docs/conventions.md "Interrupts"): the IM 2 ISR (lowram.asm
; `isr`, running from bank 2) pages BANK_AY in by OUT only and calls AY_PLAY
; once per frame with interrupts disabled, then re-OUTs PORT_7FFD_SHADOW.
; The player may clobber AF, BC, DE, HL, IX, IY (the ISR saves them; the
; alternate set only with ISR_SAVE_ALT). It must NOT: write PORT_7FFD_SHADOW
; or $7FFD, enable interrupts, read/write $C000 data outside bank 3, or
; assume anything about the interrupted code's state. Budget (budget.md §5):
; ~6.5k T per call; the tick keeps 13k T per 2 frames for it.
;==============================================================================

;------------------------------------------------------------------------------
; ay_play — SILENT STUB (until the real player): counts the call in AY_CALLS
; (test-observable) and writes a silent AY state — mixer all off (R7), volumes
; A/B/C = 0 (R8..R10). Clobbers: AF, BC, DE, HL.   286 T measured (+ contention)
;------------------------------------------------------------------------------
ay_play:
                ASSERT ay_play == AY_PLAY
                ld   hl, (AY_CALLS)
                inc  hl
                ld   (AY_CALLS), hl
                ld   bc, AY_REG_PORT
                ld   a, AY_R_MIXER
                out  (c), a
                ld   b, AY_DATA_PORT >> 8
                ld   a, AY_MIX_OFF
                out  (c), a
                ld   de, AY_R_VOL_A << 8 | 3   ; D = register, E = channels left
                xor  a
.vol:           ld   b, AY_REG_PORT >> 8
                out  (c), d
                ld   b, AY_DATA_PORT >> 8
                out  (c), a
                inc  d
                dec  e
                jr   nz, .vol
                ret
