;==============================================================================
; PANEL ENGINE, bank-2 part (B3B-11): the log steps, bars and numbers. The
; rest of the hot panel code is boot-copied to HOT_COPY (panel.asm); both are
; uncontended bank-2 RAM, split only by what fits HOT_COPY's 768 B.
;==============================================================================
;------------------------------------------------------------------------------
; item_log — the oldest pending message: step 0 scrolls row 23 -> 22 and
; clears row 23 (log_scroll); then print6n on row 23 from LQ_PTR / LQ_X, at
; most P_LIM chars (0 = all). With P_LIM = 0 both steps run in this tick.
; Message done: next ring slot, LOG_QN -= 1, PD_LOG cleared at 0.
; HL = PANEL_DIRTY.
;------------------------------------------------------------------------------
item_log:
                ld   a, (LOG_QN)
                or   a
                jr   nz, .go
                res  PD_LOG_BIT, (hl)
                ret
.go:            ld   a, (LOG_Q + LQ_STEP)
                or   a
                jr   nz, .print
                call log_scroll
                ld   a, 1
                ld   (LOG_Q + LQ_STEP), a
                xor  a
                ld   (LOG_Q + LQ_X), a
                ld   a, (LOG_Q + LQ_RD)
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   l, a
                ld   h, LOG_TXT >> 8
                ld   (LOG_Q + LQ_PTR), hl
                ld   a, (P_LIM)
                or   a
                ret  nz                        ; 2nd frame: the scroll was this tick's step
.print:         ld   hl, (LOG_Q + LQ_PTR)
                ld   a, (LOG_Q + LQ_X)
                ld   e, a
                ld   b, LOG_ROW + 1
                ld   a, (P_LIM)
                call print6n
                ld   (LOG_Q + LQ_PTR), hl
                ld   a, e
                ld   (LOG_Q + LQ_X), a
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F                       ; cols holding ink now
                ld   b, a
                ld   de, HUD4_EXT + 3          ; row 23
                ld   a, (de)
                cp   b
                jr   nc, .e
                ld   a, b
                ld   (de), a
.e:             ld   e, (HUD4_PW + 3) & $FF
                ld   a, (de)
                cp   b
                jr   nc, .w
                ld   a, b
                ld   (de), a
.w:             ld   a, 1
                ld   (PRES_ANY), a
                ld   a, (hl)
                or   a
                ret  nz                        ; chunk limit: more next tick
                xor  a                         ; message done
                ld   (LOG_Q + LQ_STEP), a
                ld   hl, LOG_Q + LQ_RD
                ld   a, (hl)
                inc  a
                and  LOG_SLOTS - 1
                ld   (hl), a
                ld   hl, LOG_QN
                dec  (hl)
                ret  nz
                ld   hl, PANEL_DIRTY
                res  PD_LOG_BIT, (hl)
                ret
                ASSERT (HUD4_EXT >> 8) == ((HUD4_PW + 3) >> 8)

;------------------------------------------------------------------------------
; log_scroll — row 23 -> row 22 (n = max(EXT22, EXT23) cols: row 23 is blank
; past EXT23, so this also wipes row 22's longer old line), then row 23 cols
; 0..EXT23-1 cleared; EXT22 = EXT23, EXT23 = 0; HUD4_PW widened for both.
; Rows 22 / 23 share their bitmap third: same H, L $C0 / $E0 + col.
; Clobbers: A, BC, DE, HL.  ~0.2k + 8 x (16 T per col copied + 11 per col cleared)
; SMC: .cj+1 / .zj+1 = entries into the unrolled LDI / clear chains.
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
                ld   a, LOG_COLS
                sub  b
                add  a, a                      ; LDI = 2 B
                ld   l, a
                ld   h, 0
                ld   de, .copy
                add  hl, de
                ld   (.cj+1), hl
                ld   a, LOG_COLS
                sub  c
                add  a, a                      ; ld (hl),a / inc l = 2 B
                ld   l, a
                ld   h, 0
                ld   de, .zero
                add  hl, de
                ld   (.zj+1), hl
                ld   a, LOG_BM_H
                ld   bc, $08FF                 ; B = lines; C: 8 x 24 LDIs never borrow from B
.line:          ld   h, a
                ld   d, a
                ld   l, LOG23_L
                ld   e, LOG22_L
.cj:            jp   .copy                     ; SMC
.copy:          DUP  LOG_COLS
                ldi
                EDUP
                xor  a
                ld   l, LOG23_L
.zj:            jp   .zero                     ; SMC
.zero:          DUP  LOG_COLS
                ld   (hl), a
                inc  l
                EDUP
                ld   a, d                      ; (D = H: LDI never carries into D)
                inc  a
                djnz .line
                ret

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

