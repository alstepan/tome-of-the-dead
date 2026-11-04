;==============================================================================
; dnum2.asm — D3-11 flying damage numbers, the bank-2 SCREEN part (header in
; dnum0.asm; DNUM-SPRITE-FIX, user 2026-11-03: a number ORs over what is on
; screen, sprite pixels kept). After ldir2.asm (the image tail); dn_fix is
; dnfix2.asm in the kind_tab ALIGN pad. Always mapped; entered with bank 7
; (screen 2) paged at $C000: by far7 from bank-0 dn_tick / bank-3 dn_take
; (farb pages bank 7 and hands the caller's bank back), from present (dn_fix).
;
; The numbers live on the DISPLAYED screen only. The bank-5 composed screen
; never holds one (map + sprites + marks + FX + drips: the truth), so a number
; cell = its bank-5 lines | the number's lines; its attr = the number's only on
; a bare cell (the bank-5 attr == the room's, SHADOW_ATTR), else the bank-5 one
; (the digit in the sprite's / mark's ink). An erase is a PRES_MASK mark
; (pmark_rect: the next present copies bank 5 back, exact).
; PRES_MASK rule: a cell already marked for the next present (render / a mark /
; decor / an erase drew it) is not drawn by the pass (pass mode, the present
; would copy bank 5 over it): the next present's dn_fix draws it right before
; the copy (fix mode: marked cells only, their bit cleared), so a body walking
; under a number shows in its cells with the rest of the body, the digit OR'd.
; DEBUG_KIT builds also hold dnwin.asm here (release: in bank 0).
;==============================================================================
OP_RET_NZ       EQU $C0                        ; dn_cel.md: pass mode
OP_RET_Z        EQU $C8                        ; dn_cel.md: fix mode (dn_fix)
OP_CALL_NN      EQU $CD                        ; present.dnf: a number live (dn_fix called)
OP_LD_BC_NN     EQU $01                        ; present.dnf: none live (dn_fix skipped, 10 T)

;------------------------------------------------------------------------------
; dn_show — IX = a live record: its rows drawn on screen 2 (k = age - 1, capped
; 8: the row above from DN_ZCOL + k for k >= 1, the start row from DN_ZCOL +
; 8 + k for k <= 7; the other row (source DN_ZCOL + 0 / + 16: dn_cel leaves
; it) is not touched: an overlapping number's cells there survive).
; Clobbers: A, BC, DE, HL (IX kept).
; ~0.3k + per cell ~0.25k (its lines to DN_ZCOL) + per drawn cell ~0.55k
;------------------------------------------------------------------------------
dn_show:
                ld   a, (ix+DL_AGE)
                dec  a
                cp   DN_RISE
                jr   c, .k
                ld   a, DN_RISE
.k:             add  a, DN_ZCOL & $FF
                ld   d, a                      ; D = the row above's source (k = 0: + 0, left)
                add  a, 8
                ld   e, a                      ; E = the start row's (k = 8: + 16, left)
                ld   (DN_SRC), de
                ; fall through
;------------------------------------------------------------------------------
; dn_walk — record IX col by col: the cell's 8 lines between DN_ZCOL's zero
; pads, then its row above (source DN_SRC + 1) and its start row (DN_SRC).
; Clobbers: A, BC, DE, HL (IX kept).
;------------------------------------------------------------------------------
dn_walk:
                ld   a, ixl
                add  a, DL_GLY
                ld   l, a
                ld   h, DN_LIVE >> 8           ; HL = cell 0's lines
                ld   c, (ix+DL_COL)
                ld   b, (ix+DL_W)
.cell:          push bc
                ld   de, DN_ZCOL + 8
                ld   bc, 8
                ldir
                pop  bc
                push hl                        ; (the next cell's lines)
                push bc
                ld   b, (ix+DL_ROW)
                dec  b
                ld   a, (DN_SRC + 1)
                call dn_cel                    ; (B, C kept)
                inc  b
                ld   a, (DN_SRC)
                call dn_cel
                pop  bc
                pop  hl
                inc  c
                djnz .cell
                ret
                ASSERT (DN_LIVE & 31) == 0 && DL_GLY + 24 <= DN_LIVE_STRIDE
                ASSERT ((DN_ZCOL + 24) >> 8) == (DN_ZCOL >> 8) && (DN_ZCOL & $FF) != 0

;------------------------------------------------------------------------------
; dn_cel — one cell on screen 2 (bank 7 paged): B = row (< PLAY_ROWS), C = col,
; A = the source's low byte (8 lines, DN_ZCOL page; DN_ZCOL + 0 / + 16, the
; zero pads = this row left: dn_show's k = 0 / 8), IX =
; the record (DL_ATTR). Pass mode: a marked cell is left (the next present's
; dn_fix draws it); fix mode: an unmarked one is left, a marked one drawn and
; its bit cleared. Screen-2 line = bank-5 line | source line; attr = DL_ATTR on
; a bare cell (bank-5 attr == the attr shadow's), else the bank-5 attr.
; Clobbers: A, DE, HL (B, C, IX kept).  ~0.12k left; ~0.4k drawn (trace builds ~0.55k)
; SMC: .md = RET NZ (pass) / RET Z (fix), patched by dn_fix only.
;------------------------------------------------------------------------------
dn_cel:
                cp   DN_ZCOL & $FF
                ret  z                         ; the row above at k = 0: left
                cp   (DN_ZCOL + 16) & $FF
                ret  z                         ; the start row at k = 8: left
                ld   d, a                      ; D = the source's low byte
                call dn_mbit                   ; (HOT_COPY) HL = mask byte, E = bit, A = marked
.md:            ret  nz                        ; SMC: RET NZ pass / RET Z fix
                xor  (hl)
                ld   (hl), a                   ; fix: the bit cleared (pass: A = 0, unchanged)
                ld   a, b
                rrca
                rrca
                rrca
                push af                        ; (bits 1..0 = the third, for the attr)
                and  $E0
                or   c
                ld   l, a                      ; L = the cell's low byte (bitmap / attr)
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a                      ; HL = the bank-5 cell, line 0
                ld   e, d
                ld   d, DN_ZCOL >> 8           ; DE = the source lines
    IF ANIM_TRACE_ON                           ; (trace builds: the bank-2 tail has no room)
.l:             ld   a, (de)
                or   (hl)                      ; over the composed line (sprite pixels kept)
                set  7, h                      ; screen 2 = bank 5 + $8000
                ld   (hl), a
                res  7, h
                inc  e
                inc  h
                ld   a, h
                and  7
                jr   nz, .l
    ELSE
                ; PERF-GHOST: BC = the screen-2 line (B, C saved), 2 lines a pass: 44.5 T a
                ; line (was 68), ~-0.15k T a drawn cell incl. the setup, +10 B
                push bc
                ld   c, l
                ld   a, h
                or   $80                       ; screen 2 = bank 5 + $8000
                ld   b, a
.l:             ld   a, (de)
                or   (hl)                      ; over the composed line (sprite pixels kept)
                ld   (bc), a
                inc  e
                inc  h
                inc  b
                ld   a, (de)
                or   (hl)
                ld   (bc), a
                inc  e
                inc  h
                inc  b
                ld   a, h
                and  7
                jr   nz, .l
                pop  bc
    ENDIF
                pop  af
                and  3
                or   SCREEN_ATTR >> 8
                ld   h, a                      ; HL = the bank-5 attr
                add  a, (SHADOW_ATTR - SCREEN_ATTR) >> 8
                ld   d, a
                ld   e, l                      ; DE = the room's attr (shadow, bank 7)
                ld   a, (de)
                cp   (hl)
                ld   a, (hl)
                jr   nz, .a                    ; a sprite / mark / FX / drip coloured it: keep
                ld   a, (ix+DL_ATTR)           ; bare: the number's colour
.a:             set  7, h
                ld   (hl), a
                ret
                ASSERT SCREEN7_BITMAP - SCREEN_BITMAP == $8000 && SCREEN7_ATTR - SCREEN_ATTR == $8000
                ASSERT (SCREEN_BITMAP & $7FF) == 0 && (SCREEN_ATTR & $3FF) == 0 && (SHADOW_ATTR & $3FF) == 0
                ASSERT (DN_ZCOL >> 8) == ((DN_ZCOL + 23) >> 8)

    IF DEBUG_KIT
                INCLUDE "dnwin.asm"            ; dn_win / dn_sl (release builds: in bank 0, dnum0.asm)
    ENDIF
