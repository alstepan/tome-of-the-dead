;------------------------------------------------------------------------------
; log_scroll — row 23 -> row 22 (n = max(EXT22, EXT23) cols: row 23 is blank
; past EXT23, so this also wipes row 22's longer old line), then row 23 cols
; 0..EXT23-1 cleared; EXT22 = EXT23, EXT23 = 0; HUD4_PW widened for both.
; Rows 22 / 23 share their bitmap third: same H, L $C0 / $E0 + col.
; C-T6: moved from bank-2 panel2.asm to the bank-0 cold-code block (b0_code,
; FARB0 from item_log: once per log line) to fund the mirror blit. Rules =
; bank3.asm's, so NO SMC: the two unrolled chains are entered through IX (the
; LDI copy) and a word on the stack (the clear; `pop hl / push hl / jp (hl)`),
; both computed once; the clear runs through DE (HL is the entry).
; Clobbers: A, BC, DE, HL (IX kept).
; ~0.3k + 8 x (16 T per col copied + 11 per col cleared + ~60) (+ FARB0 ~0.25k)
;------------------------------------------------------------------------------
LOG_BM_H        EQU (SCREEN_BITMAP >> 8) | (LOG_ROW & $18)
LOG22_L         EQU (LOG_ROW & 7) << 5
LOG23_L         EQU ((LOG_ROW + 1) & 7) << 5
log_scroll:
                ld   hl, HUD4_EXT + 2
                ld   a, (hl)                   ; EXT22
                inc  l
                ld   c, (hl)                   ; EXT23
                ld   (hl), 0
                dec  l
                ld   (hl), c                   ; EXT22 = EXT23
                cp   c
                jr   nc, .n
                ld   a, c
.n:             or   a
                ret  z                         ; both rows blank
                ld   b, a                      ; B = n
                ld   l, (HUD4_PW + 2) & $FF
                cp   (hl)
                jr   c, .p22
                ld   (hl), a
.p22:           inc  l
                ld   a, c
                cp   (hl)
                jr   c, .p23
                ld   (hl), a
.p23:           ld   a, 1
                ld   (PRES_ANY), a
                push ix
                ld   a, LOG_COLS
                sub  b
                add  a, a                      ; LDI = 2 B
                ld   e, a
                ld   d, 0
                ld   ix, .copy
                add  ix, de                    ; IX = the copy entry
                ld   a, LOG_COLS
                sub  c
                add  a, a                      ; ld (de),a / inc e = 2 B
                ld   e, a
                ld   hl, .zero
                add  hl, de
                push hl                        ; (SP) = the clear entry
                ld   a, LOG_BM_H
                ld   bc, $08FF                 ; B = lines; C: 8 x 24 LDIs never borrow from B
.line:          ld   h, a
                ld   d, a
                ld   l, LOG23_L
                ld   e, LOG22_L
                jp   (ix)
.copy:          DUP  LOG_COLS
                ldi
                EDUP
                xor  a
                ld   e, LOG23_L                ; (D = H: LDI never carries into D)
                pop  hl
                push hl
                jp   (hl)
.zero:          DUP  LOG_COLS
                ld   (de), a
                inc  e
                EDUP
                ld   a, d
                inc  a
                djnz .line
                pop  hl
                pop  ix
                ret
                ASSERT (LOG23_L & $1F) == 0 && LOG_COLS <= 32 && 8 * LOG_COLS < 256

;------------------------------------------------------------------------------
; gen_lshare — gen_frame's left facing without a left variant (C-T6; was the
; low-RAM SYM copy): A = FD_FLAGS & (FF_SYM | FF_MIR), != 0. Copies the fid's
; right entries (variants 0..1) to the left ones (2..3); FF_MIR without FF_SYM
; then sets bit 7 of both left bank bytes (FRT_NONE = $FF stays $FF), which
; makes blit_sprite mirror the right variant (mirror2.asm). Entered through
; farb from gen_frame (low RAM), bank 0 paged; touches only the FRT (bank 2).
; Clobbers: A, BC, DE, HL.  ~0.2k T (+ farb)
;------------------------------------------------------------------------------
gen_lshare:     cp   FF_MIR                    ; Z: mirrored at blit time (SYM wins)
                call frt_ptr_cur               ; HL = the row (ld / add hl only: Z kept)
                ld   d, h
                ld   e, l
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de                        ; DE = variant 2 (inc de: Z kept)
                ld   bc, 6
                ldir                           ; (Z kept) HL = variant 2's bank byte
                ret  nz
                set  7, (hl)
                inc  hl
                inc  hl
                inc  hl
                set  7, (hl)                   ; variant 3's
                ret
                ASSERT FRT_NONE == $FF && FF_MIR == 8 && (FF_MIR & (FF_SYM | FF_MOTION | FF_PH4)) == 0
