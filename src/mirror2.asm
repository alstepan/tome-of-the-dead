;==============================================================================
; mirror2.asm — C-T6 (option C, docs/design/mirror_c_split.md §6 T6): the
; blit-time MIRROR path of blit_sprite (bank 2, gfx.asm). A left-facing FF_MIR
; frame has no left variant of its own: its FRT left entries are the RIGHT
; entries with bank bit 7 set (gen_frame, lowram.asm). blit_sprite branches here
; on that bit (`jp m`), draws the right variant row by row from its LAST byte
; column leftwards, every mask / data byte bit-reversed through BITREV_TAB.
; Byte identity (§1): rowrev + bitrev of the right variant at shift s over its
; cols (+1 spill) bytes == the generator's left variant at s, so the screen
; footprint, the FT_OFFL anchor and the damage rects are those of a stored left.
;
; Same stack blit as the normal chains (docs/conventions.md "Stack blits"): BC is
; preloaded by blit_go_sp from the word below the frame, then only `pop bc`
; writes BC while SP is borrowed (blit_sp_on .. blit_sp_off, the same probes).
; Registers in the chain: BC = popped (C mask, B data), DE = screen, H =
; BITREV page, L = lookup index, IXL = the line's first (rightmost) screen byte,
; IXH = lines left to the next char row; BLIT_CROWS = lines after this segment.
; IX is the caller's again on exit (SMC operand blit_mix+2).
;   pop bc / ld l,c / ld a,(de) / and (hl) / ld l,b / or (hl) / ld (de),a / dec e
;   = 50 T/byte (+ BITREV contention: see BLIT_REV), 8 B
; Line: ld e,ixl / inc d / dec ixh / jp nz = 30 T; the char-row fix-up once per
; char row (~110 T) — one chain serves both the aligned and the general case
; (the first segment is 8 - (fpy & 7) lines).
; SMC: blit_mj+1 (gfx.asm: diverted here by blit_mpro, put back by blit_mset),
; blit_go+1 / blit_mdj+1 (this width's chain entry), blit_mix+2 (the caller's IX).
;==============================================================================
BLIT_MBLOCK     EQU 8                   ; bytes per unrolled mirror block

; blit_mpro (gfx.asm, falls into blit_mback) diverts blit_mj here after the clip check.

; blit_mset — the shared setup's state after the clip check: C = width (cols +
; spill), B = rows, E = byte col, A = col + width; stack: the frame pointer.
blit_mset:      ld   hl, blit_mj + 3
                ld   (blit_mj+1), hl           ; SMC: undivert (the next blit may be normal)
                ld   (blit_mix+2), ix          ; SMC: the caller's IX
                dec  a
                ld   d, c
                ld   c, a                      ; C = col + width - 1: the rightmost byte
                ld   a, d
                add  a, a
                add  a, a
                add  a, a                      ; 8 * width (<= 48: CF = 0 for the sbc)
                ld   e, a
                ld   d, 0
                ld   hl, blit_mchain_end
                sbc  hl, de                    ; HL = chain end - 8 * width
                ld   (blit_go+1), hl           ; SMC: first entry
                ld   (blit_mdj+1), hl          ; SMC: the per-line jp nz (also the char-row one)
                ld   a, (BL_FPY)
                ld   e, a
                or   $F8
                neg                            ; 8 - (fpy & 7): lines to the next char row
                ld   ixh, a
                neg
                add  a, b
                ld   (BLIT_CROWS), a           ; lines after the first segment
                ld   a, e
                call scr_addr_py               ; HL = screen (BC, DE kept)
                ex   de, hl                    ; DE = screen
                ld   ixl, e                    ; the line's first byte
                pop  hl                        ; HL = pool data
                ld   a, BLIT_REV               ; -> H (blit_go_sp's ld h,a)
                jp   blit_go_sp

blit_mchain:
                DUP  BLIT_MAXW
                pop  bc                        ; C = mask, B = data (BC = the word below SP)
                ld   l, c
                ld   a, (de)
                and  (hl)                      ; mirrored mask
                ld   l, b
                or   (hl)                      ; mirrored data
                ld   (de), a
                dec  e                         ; leftwards
                EDUP
blit_mchain_end:
                ld   e, ixl                    ; 8 back to the line's first byte
                inc  d                         ; 4 next pixel line
blit_mdec:      dec  ixh                       ; 8
blit_mdj:       jp   nz, blit_mchain           ; 10 SMC: this width's entry (30 T/line)
                ld   a, ixl                    ; next char row
                add  a, 32
                ld   ixl, a
                ld   e, a
                jr   c, .third                 ; crossed a third: D already right
                ld   a, d
                sub  8
                ld   d, a
.third:         ld   a, (BLIT_CROWS)
                sub  8
                ld   ixh, 8 + 1                ; (+1: re-enters at blit_mdec)
                jr   nc, .seg                  ; a whole char row follows
                add  a, 8                      ; the last (partial) segment, or done
                jr   z, blit_mdone
                inc  a
                ld   ixh, a
                xor  a
.seg:           ld   (BLIT_CROWS), a
                jr   blit_mdec                 ; IXH - 1 >= 1: NZ, this width's entry (3 B less
                                               ; than its own SMC jp, +20 T a char row)
blit_mdone:
blit_mix:       ld   ix, 0                     ; SMC: the caller's IX
                jp   blit_rs                   ; restore SP, return
                ASSERT (blit_mchain_end - blit_mchain) == BLIT_MBLOCK * BLIT_MAXW
                ASSERT blit_mchain_end < $C000 && (BITREV_TAB & $FF) == 0
