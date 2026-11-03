;==============================================================================
; dnum6.asm — D3-11 flying damage numbers, the R6 part (far6 from bank-3
; dn_take; header in dnum0.asm). Reads bank-2 SLOTREC / kind_tab only.
;==============================================================================

;------------------------------------------------------------------------------
; dn_place — IX = record (DL_W set), DN_CUR = slot: DL_COL = centred on the
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
