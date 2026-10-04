;==============================================================================
; PANEL ENGINE, bank-2 part (B3B-11): the log item, items, bars, numbers, the
; print6 source switch. The rest of the hot panel code is boot-copied to
; HOT_COPY (panel_hot.asm); both are uncontended bank-2 RAM, split only by
; what fits HOT_COPY.
;==============================================================================
;------------------------------------------------------------------------------
; item_log — the oldest pending message as ONE item (B3B-11b: no chunked
; steps): log_scroll (row 23 -> 22, row 23 cleared), then the whole line on
; row 23 (print6), next ring slot, LOG_QN -= 1, PD_LOG cleared at 0.
; HL = PANEL_DIRTY. Clobbers: all but IX, IY.  ~23k T for 32 chars (W15)
;------------------------------------------------------------------------------
item_log:
                ld   a, (LOG_QN)
                or   a
                jr   nz, .go
                res  PD_LOG_BIT, (hl)
                ret
.go:            call log_scroll
                ld   a, (LOG_Q + LQ_RD)
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   l, a
                ld   h, LOG_TXT >> 8
                ld   b, LOG_ROW + 1
                ld   e, 0
                call print6
                ld   a, e
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F                       ; cols holding ink now (row 23 was cleared)
                ld   hl, HUD4_EXT + 3          ; row 23
                ld   (hl), a
                ld   l, (HUD4_PW + 3) & $FF
                cp   (hl)
                jr   c, .w
                ld   (hl), a
.w:             ld   a, 1
                ld   (PRES_ANY), a
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
; item_icons — 3B: the quick-potion slot (count digit at (col+2, 19); attrs:
; glyph cell ATTR_POTION + digit ATTR_HUD, both greyed at 0). HL = PANEL_DIRTY.
; ~1k T
;------------------------------------------------------------------------------
item_icons:
                res  PD_ICONS_BIT, (hl)
                ld   a, (P_ENTITIES + E_POT)
                ld   (PANEL_POT_SH), a
                cp   10
                jr   c, .d
                ld   a, 9
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), 0
                dec  l
                ld   a, (pot_col)
                add  a, 2
                add  a, a
                add  a, a
                add  a, a
                ld   e, a                      ; x of cell col + 2
                ld   b, ICON_ROW + 1
                call print6
                ld   a, (pot_col)
                ld   c, a
                ld   b, ICON_ROW + 1
                call attr_addr                 ; HL = attr (19, col); keeps BC
                ld   de, (ATTR_POTION << 8) | ATTR_HUD
                ld   a, (PANEL_POT_SH)
                or   a
                jr   nz, .a
                ld   de, (ATTR_P_GREY << 8) | ATTR_P_GREY
.a:             ld   (hl), d
                inc  l
                inc  l
                ld   (hl), e
                ld   de, (ICON_W << 8) | 1
                jp   pmark_rect                ; (B, C = row 19, slot col)
pot_col:        DB   0                         ; quick-potion slot col (panel_init)

;------------------------------------------------------------------------------
; print6g — print6 fed by a getter (the interface kept open for B3B-13's
; dictionary-token decoder; nothing calls it yet): HL = getter (out A = next
; char, 0 = end; its state in BC; keeps DE; may clobber HL), BC = its initial
; state, A = char row, E = pixel x (x & 7 = 0). Patches print6's 4 fetch
; sites to `call getter` (print6 puts the inline fetch back by itself).
; Out / clobbers: as print6.  +23 T per char vs the inline fetch.
; p6_inline — restore the inline `ld a, (bc) / inc bc / nop` fetch sites.
; Keeps B, C, E, HL.  Clobbers: A, D.
;------------------------------------------------------------------------------
print6g:
                push af
                push bc
                push de
                ex   de, hl                    ; DE = getter
                ld   hl, P6_SITE0
                ld   c, P6_SITES
.s:             ld   (hl), $CD                 ; call getter
                inc  hl
                ld   (hl), e
                inc  hl
                ld   (hl), d
                ld   a, l
                add  a, P6_SITE_STEP - 2
                ld   l, a
                jr   nc, .n
                inc  h
.n:             dec  c
                jr   nz, .s
                pop  de
                pop  bc
                pop  af
                jp   print6_go
p6_inline:
                push hl
                push bc
                ld   hl, P6_SITE0
                ld   d, P6_SITES
.s:             ld   (hl), P6_LDBC
                inc  hl
                ld   (hl), P6_INCBC
                inc  hl
                ld   (hl), 0                   ; nop
                ld   bc, P6_SITE_STEP - 2
                add  hl, bc
                dec  d
                jr   nz, .s
                pop  bc
                pop  hl
                ret

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

