;==============================================================================
; dnum3.asm — D3-11 flying damage numbers, the bank-3 part (header in
; dnum0.asm): the spawn (far3 from bank-0 dn_scan, <= 1 a pass): value +
; colour, the live list (merge / replace / free / evict), text, placement
; (dn_place, here since WIDOW-SPIT: was R6 dnum6.asm), compose (straight from the FONT6 planes: no screen
; touched, DNUM-SPRITE-FIX). RAM + bank-2 reads only; erases through FARB0
; dn_erase (bank 0, a present mark), draws through far7 dn_show (bank 2,
; screen 2). Pages nothing.
;==============================================================================

;------------------------------------------------------------------------------
; dn_take — far3 from dn_scan: A = the number (-99..99, 0 = "0", DNV_MISS) for
; slot DN_CUR, kind DN_BT: its colour, the live list (the body's live
; number: same sign summed, else replaced; else a free entry; else the oldest
; ends; the entry's old rows marked for present), then text, placement,
; compose. Out: IX = the record (dn_scan draws it: dn_mb).
; SMC: .pd+1 = the pad (px), patched per call (.tx).
; Clobbers: all but IY.  ~4k T (the 8-line compose ~1.3k, the draw)
;------------------------------------------------------------------------------
dn_take:
                ld   d, a                      ; D = value; the colour (game.md §6.5):
                ld   e, DNA_MISS
                add  a, a
                jr   z, .s                     ; 0 / MISS: cyan
                ld   e, DNA_HEAL
                jr   nc, .s                    ; HP gained: green
                ld   e, DNA_MDMG
                ld   a, (DN_CUR)
                or   a
                jr   nz, .s                    ; a monster: white
                ld   e, DNA_HDMG
                ld   a, (DN_BT)
                rla
                jr   nc, .s                    ; the hero struck: red (DN_BT bit 7: DNT_HP)
                ld   a, (ST_X)                 ; unreacted while poisoned: magenta
                or   a
                jr   z, .s
                ld   e, DNA_PSN
.s:             ld   a, (DN_CUR)               ; D = value, E = attr
                call dn_find
                jr   z, .own
                ld   a, $FF                    ; a free entry?
                call dn_find
                jr   z, .go
                ld   hl, dn_evict              ; full: the oldest ends (bank 7: IX out, DE kept)
                call far7
                jr   .ers
.own:           ld   a, d                      ; x + x = 0 only for 0 and MISS: replaced
                add  a, a
                jr   z, .ers
                ld   a, (ix+DL_VAL)
                ld   c, a
                add  a, a
                jr   z, .ers
                ld   a, c
                xor  d
                jp   m, .ers                   ; opposite sign: replaced (no netting)
                ld   a, d                      ; same sign: |sum| capped 99, the sign kept
                rla
                sbc  a, a
                ld   h, a                      ; H = the sign mask
                xor  c
                sub  h
                ld   b, a                      ; |live|
                ld   a, d
                xor  h
                sub  h                         ; |new|
                add  a, b
                cp   100
                jr   c, .a3
                ld   a, 99
.a3:            xor  h
                sub  h
                ld   d, a
.ers:           push de
                FARB0 dn_erase                 ; its rows marked: the next present copies bank 5
                                               ; back (dn_fix draws the new number's there first)
                pop  de
.go:            ld   a, (DN_CUR)
                ld   (ix+DL_SLOT), a
                ld   (ix+DL_VAL), d
                ld   (ix+DL_ATTR), e
                ld   (ix+DL_AGE), 1            ; drawn at once (k = 0), below
                ; --- the text: sign + 1-2 digits, "0", "MISS"
                ld   a, d
                ld   de, DN_TXT
                cp   DNV_MISS
                jr   nz, .nm
                ld   a, (DN_TXT + 5)           ; dn_lvt (bank 2) filled DN_TXT: "MISS" / "+LVL", 0, its attr
                ld   (ix+DL_ATTR), a
                cp   DNA_LVL
                jr   nz, .nl
                set  7, (ix+DL_SLOT)           ; LVL-KEEP: "+LVL" is filed as slot | $80: dn_find never
                                               ; matches it, so a later number takes its own free entry
                                               ; (or ends the oldest) instead of replacing "+LVL"
.nl:            ld   bc, 3 << 8 | 0            ; 24 px = 3 cells, no pad
                jr   .tx
.nm:            or   a
                jr   z, .dg                    ; "0": no sign
                ex   de, hl
                ld   (hl), '+'
                jp   p, .ps
                ld   (hl), '-'
                neg
.ps:            inc  hl
                ex   de, hl
.dg:            call msg_dec                   ; (bank 2: 1-2 digits at DE)
                ld   a, e
                sub  DN_TXT & $FF              ; n chars: n cells, n px pad (1 / 2 / 3)
                ld   b, a
                ld   c, a
                ld   a, ' '                    ; the composer reads 4 chars: pads up to
                ld   (de), a                   ; DN_TXT + 3 (n <= 3: DN_TXT is 6 B)
                inc  e
                ld   (de), a
                inc  e
                ld   (de), a
.tx:            ld   (ix+DL_W), b
                ld   a, c
                ld   (.pd+1), a                ; SMC: the pad (px) for the compose below
                call dn_place                  ; DL_COL / DL_ROW (WIDOW-SPIT: bank 3, was a far6 to R6; IX kept)
                ; --- compose (DNUM-SPRITE-FIX: from the FONT6 planes, bank 2; no screen
                ; byte touched, bank 5 stays the composed truth): per pixel line the 4 chars
                ; at 6 px pitch (print6's quad merge), shifted right by the pad, cell-major
                ; into DL_GLY (a cell past w is never drawn). Line l of char c: FONT6 +
                ; (l >> 1) * 256 + c + (l & 1) * FONT6_WB.  ~1.3k T
                push ix
                ld   hl, FONT6                 ; H = the line pair's page
                ld   c, l                      ; C = the plane: 0 even line / FONT6_WB odd
.cl:            ld   a, (DN_TXT + 3)
                add  a, c
                ld   l, a
                ld   a, (hl)
                rrca
                rrca                           ; g3 >> 2 (glyph bits 1..0 are 0)
                ld   e, a
                ld   a, (DN_TXT + 2)
                add  a, c
                ld   l, a
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                ld   d, a                      ; D = r2 = g2 rrc 4
                and  $F0
                or   e
                ld   e, a                      ; E = byte 2 = g2 << 4 | g3 >> 2
                ld   a, (DN_TXT + 1)
                add  a, c
                ld   l, a
                ld   a, (hl)
                rlca
                rlca
                ld   b, a                      ; B = r1 = g1 rlc 2
                xor  d
                and  $F0
                xor  d
                ld   d, a                      ; D = byte 1 = g1 << 2 | g2 >> 4
                ld   a, (DN_TXT)
                add  a, c
                ld   l, a
                ld   a, b
                and  3
                or   (hl)
                ld   l, a                      ; L = byte 0 = g0 | g1 >> 6
.pd:            ld   b, 0                      ; SMC: the pad (.tx)
                inc  b
                jr   .s1
.s0:            srl  l
                rr   d
                rr   e
.s1:            djnz .s0
                ld   (ix+DL_GLY), l
                ld   (ix+DL_GLY + 8), d
                ld   (ix+DL_GLY + 16), e
                inc  ix
                ld   a, c
                xor  FONT6_WB
                ld   c, a
                jr   nz, .cl                   ; the odd line: same page
                inc  h
                ld   a, h
                cp   (FONT6 >> 8) + 4
                jr   nz, .cl
                pop  ix                        ; (IX out: bank-0 dn_scan's dn_mb draws it)
                ret
                ASSERT (FONT6 & $FF) == 0 && FONT6_WB != 0

;------------------------------------------------------------------------------
; dn_place — WIDOW-SPIT: moved from R6 dnum6.asm (R6 -59, bank 3 +56: the far6 is a
; direct call). IX = record (DL_W set), DN_CUR = slot: DL_COL = centred on the
; drawn footprint (SLOTREC R_COL / R_COLS: this tick's anim_tick), clamped to
; 0..32 - w; DL_ROW = the drawn top row - 1, at least 9s + 1 (both window rows
; inside the storey: a body that tops the storey is overdrawn, game.md §6.5;
; rows 9s .. 9s + 8 always, never off the playfield).
; Clobbers: A, BC, E, HL (IX kept).  ~0.25k T
;------------------------------------------------------------------------------
dn_place:
                ld   b, (ix+DL_W)
                ld   a, (DN_CUR)
                rlca
                rlca
                rlca
                rlca
                or   R_COL
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   c, (hl)                   ; C = footprint col
                inc  l
                ld   e, (hl)                   ; E = its top row (R_ROW)
                inc  l
                ld   a, (hl)                   ; R_COLS
                sub  b
                sra  a                         ; (cols - w) / 2, signed
                add  a, c
                jp   p, .c0
                xor  a
.c0:            ld   c, a
                ld   a, ROOM_COLS
                sub  b                         ; 32 - w
                cp   c
                jr   c, .c1
                ld   a, c
.c1:            ld   (ix+DL_COL), a
                ld   a, e
                add  a, (kind_tab + KT_MOD9) & $FF
                ld   l, a
                ld   h, (kind_tab + KT_MOD9) >> 8
                ld   a, e
                sub  (hl)                      ; 9s
                inc  a
                ld   c, a                      ; C = 9s + 1
                ld   a, c                      ; DL_ROW = max(top - 1, 9s + 1): compare before the
                cp   e                         ; dec (review: top = 0, a storey-0 flyer, gave $FF and
                jr   nc, .r                    ; the window wrote bank-7 code at rows $FE / $FF)
                ld   a, e
                dec  a                         ; the row above the drawn top (top > 9s + 1 here)
.r:             ld   (ix+DL_ROW), a
                ret
                ASSERT R_ROW == R_COL + 1 && R_COLS == R_COL + 2 && SLOTREC_STRIDE == 16 && (SLOTREC & $FF) == 0
