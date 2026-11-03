;==============================================================================
; dnfix2.asm — DNUM-SPRITE-FIX: dn_fix, present's number pass (bank 2, the
; kind_tab ALIGN pad; the screen part is dnum2.asm).
;==============================================================================

;------------------------------------------------------------------------------
; dn_fix — present (bank 7 paged, PRES_ANY set), before its copy: every live
; number with a marked cell near its window (a coarse test: its window rows'
; two mask bytes from the first col, DL_MB: bank-0 dn_mb at the spawn) is redrawn in fix mode: its MARKED cells
; only (bank 5 | the number, bit cleared, so present leaves them), the last
; record first (fix mode draws a cell once: the same "later record on top" as
; the pass). A cell the tick drew under a number (a body walking through it, a
; hurt frame, a mark, a flame) is then shown with the rest of the tick's
; changes, the digit OR'd over it; an erased cell (a mark: expiry, rise 8, a
; replaced number) not covered by another number is copied by present itself.
; Clobbers: A, BC, DE, HL (IX kept).  ~0.1k + ~0.2k a live number; a redraw
; as dn_show (its marked cells only).
;------------------------------------------------------------------------------
dn_fix:
                push ix
                ld   a, OP_RET_Z
                ld   (dn_cel.md), a            ; fix mode
                ld   ix, DN_LIVE + (DN_LIVE_N - 1) * DN_LIVE_STRIDE
.r:             ld   a, (ix+DL_SLOT)
                inc  a
                jr   z, .n                     ; free
                ld   l, (ix+DL_MB)
                ld   h, PRES_MASK >> 8         ; HL = the row above's mask byte of the first col
                ld   a, (hl)
                inc  l
                or   (hl)                      ; + the next (w <= 3: two bytes at most)
                ld   b, a
                ld   a, l
                add  a, 3
                ld   l, a
                ld   a, (hl)
                inc  l
                or   (hl)                      ; the start row's two
                or   b
                call nz, dn_show
.n:             ld   a, ixl
                sub  DN_LIVE_STRIDE
                ld   ixl, a
                cp   (DN_LIVE - DN_LIVE_STRIDE) & $FF
                jr   nz, .r
                ld   a, OP_RET_NZ
                ld   (dn_cel.md), a            ; pass mode again
                pop  ix
                ret
                ASSERT (PRES_MASK & $FF) >= 4 && (DN_LIVE & $FF) >= DN_LIVE_STRIDE
                ASSERT (DN_LIVE >> 8) == ((DN_LIVE + DN_LIVE_N * DN_LIVE_STRIDE - 1) >> 8)
