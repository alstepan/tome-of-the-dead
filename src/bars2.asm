;==============================================================================
; bars2.asm — MEM-SND: panel-engine helpers moved from the end of panel2.asm
; to after kind_tab (main.asm), so the bytes before the page-aligned kind_tab
; (its ALIGN pad) are headroom for new bank-2 hooks. Bank 2, no alignment
; needs (bars_draw reads pm_tab by its own H). Any bank may call them.
;==============================================================================
;------------------------------------------------------------------------------
; bars_draw — 32-px bar (concept: frame rows 1 / 6, end caps, fill rows 2..5)
; at HL = bitmap line 0 of its first cell; fill = round(A * 32 / D), D >= 1
; (D = 0 draws an empty bar). Clobbers: A, BC, DE, HL.   ~1.4k T
;------------------------------------------------------------------------------
bars_draw:
                push hl
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; A * 32
                ld   e, d
                ld   d, 0
                ld   b, d                      ; B = quotient
                ld   a, e
                or   a
                jr   z, .q
                srl  a
                ld   c, a
                add  hl, bc                    ; + D/2: rounded (B = 0 here)
                dec  b
.dv:            inc  b
                sbc  hl, de                    ; (CF = 0 on entry / after nc)
                jr   nc, .dv
.q:             ld   a, b
                cp   BAR_CELLS * 8 + 1
                jr   c, .ok
                ld   a, BAR_CELLS * 8
.ok:            ld   c, a                      ; C = fill px left
                pop  hl
                ld   e, BAR_CELLS
.byte:          ld   a, c
                sub  8
                jr   c, .part
                ld   c, a
                ld   a, $FF
                jr   .have
.part:          push hl
                ld   a, c
                add  a, pm_tab & $FF
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, (hl)                   ; $FF >> fill
                cpl                            ; the first `fill` px
                pop  hl
                ld   c, 0
.have:          ld   b, a
                ld   a, e
                cp   BAR_CELLS
                jr   nz, .nl
                set  7, b                      ; left cap
.nl:            dec  a
                jr   nz, .nr
                set  0, b                      ; right cap
.nr:            inc  h
                ld   (hl), $FF                 ; line 1
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b                   ; lines 2..5
                inc  h
                ld   (hl), $FF                 ; line 6
                ld   a, h
                sub  6
                ld   h, a
                inc  l
                dec  e
                jr   nz, .byte
                ret

; num2 — P_NUMBUF = A (0..99, clamped) as 2 chars right-aligned + 0; HL = P_NUMBUF.
; Clobbers: A, BC, HL
num2:
                cp   100
                jr   c, .a
                ld   a, 99
.a:             ld   b, '0' - 1
.t:             inc  b
                sub  10
                jr   nc, .t
                add  a, '0' + 10
                ld   c, a
                ld   a, b
                cp   '0'
                jr   nz, .w
                ld   a, ' '
.w:             ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), c
                inc  l
                ld   (hl), 0
                ld   l, P_NUMBUF & $FF
                ret
