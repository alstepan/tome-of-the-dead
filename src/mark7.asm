;==============================================================================
; mark7.asm — D3-8d status marks, bank-7 part: the ops (mk_op: draw / erase /
; in-place redraw, entered by far7 from bank-2 mk_slot at most MK_OPS_MAX
; times a tick, first-frame ticks only), mk_forget, the stale sweep, the room
; reset + glyph copy, the transition hide. The per-tick pass is bank 2
; (src/mark.asm, header there). Entered through far7 or from bank-7 code;
; no data here (the glyphs / attrs are copied into MK_RAM, bank 5).
;==============================================================================

;------------------------------------------------------------------------------
; mk_op — far7 from mk_slot: mk_sl's drawn mark (R_MK / R_MKLO) differs from
; the wanted one (mk_des / mk_dlo). One op (two for a move: erase + draw while
; ops are left): none wanted -> erase; the same cell -> redraw in place
; unless a body / FX has come over it (then forgotten + the cell repaired);
; another cell -> erase, then draw; none drawn -> draw if its cell is free.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
mk_op:
                call mk_spend
                ret  c                         ; (mark_tick checked: never)
                call mk_rec
                ld   de, (mk_dlo)
                ld   a, (hl)
                or   a
                jr   z, mk_new                 ; none drawn: draw
                inc  d
                dec  d
                jp   z, mk_erase               ; none wanted: erase
                inc  l
                ld   a, (hl)
                dec  l
                cp   e
                jr   nz, .mv                   ; moved: erase, then draw
                call mk_cb                     ; the same cell, another glyph / frame
                call cell_bf
                jp   c, mk_forget              ; a body / FX over it now
                call mk_rec
                ld   a, (mk_des)
                ld   (hl), a
                ld   de, (mk_dlo)
                jr   mk_draw
.mv:            call mk_erase
                call mk_spend
                ret  c                         ; the draw waits for the next pass
                ; fall through
;------------------------------------------------------------------------------
; mk_new — draw the wanted mark (mk_des / mk_dlo) for mk_sl unless a body,
; an FX or another mark covers its cell (then the next pass tries again; the
; op is spent). The drop in that cell is forgotten (IDLE): the mark's bytes
; overwrite it whole.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
mk_new:
                ld   de, (mk_dlo)
                call mk_cbde                   ; C, B = the cell
                call cell_occ
                ld   a, 0
                rla
                ld   d, a                      ; D = 1: covered
                ld   a, (mk_sl)                ; MK_WAIT[slot] = covered (1) / drawn (0):
                add  a, MK_WAIT & $FF          ; mk_slot gates the next try on it
                ld   l, a
                ld   h, MK_WAIT >> 8
                ld   (hl), d
                dec  d
                ret  z                         ; covered: the next try later
                ld   a, (DRIP_DRAWN)
                or   a
                jr   z, .nd
                ld   hl, (DRIP_COL)            ; L = col, H = row
                ld   a, l
                cp   c
                jr   nz, .nd
                ld   a, h
                cp   b
                jr   nz, .nd
                xor  a
                ld   (DRIP_DRAWN), a
                ld   (DRIP_ST), a              ; IDLE, a fixed gap
                ld   a, DRIP_GAP
                ld   (DRIP_T), a
.nd:            call mk_bit
                or   (hl)
                ld   (hl), a                   ; mapped
                ld   hl, MK_N
                inc  (hl)
                call mk_rec
                ld   de, (mk_dlo)
                ld   (hl), d
                inc  l
                ld   (hl), e
                ; fall through
                ASSERT DRS_IDLE == 0 && DRIP_ROW == DRIP_COL + 1
                ASSERT (MK_WAIT & $FF) + P_MAX_ENT <= 256 && (MK_AX >> 8) == (MK_GLYPHS >> 8)
;------------------------------------------------------------------------------
; mk_draw — D = R_MK (g | frame | third), E = the cell's low byte: the map
; cell's tile glyph OR the mark's 8 lines -> the bank-5 bitmap, the mark attr
; -> the bank-5 attr (the attr shadow keeps the map's: an erase restores it),
; marked for present. Pages nothing.  Clobbers: A, BC, DE, HL.  ~0.8k T
;------------------------------------------------------------------------------
mk_draw:
                push de                        ; [R_MK, low byte]
                xor  a
                ld   (MK_AX), a
                ld   a, d
                and  MK_GMASK
                dec  a
                ld   c, a                      ; C = g - 1
                ld   b, a
                add  a, a
                add  a, a
                add  a, a
                add  a, b                      ; (g - 1) * 9
                add  a, (MK_GLYPHS & $FF) + MK_G_STRIDE - 1
                ld   l, a
                ld   h, MK_GLYPHS >> 8         ; HL = its A7 (bottom row)
                ld   a, (hl)
                or   a
                ld   a, l
                jr   nz, .full
                sub  MK_G_STRIDE - 1           ; bottom row blank: the record + 0 = A one
                bit  3, d                      ; line down (lossless)
                jr   z, .a
                inc  a                         ; frame B: one line up (A at its panel rows)
                jr   .a
.full:          sub  MK_G_STRIDE - 2           ; all 8 rows (ASLEEP, STUNNED): the record
                bit  3, d                      ; + 1, both frames; frame B = BRIGHT toggled
                jr   z, .a                     ; (the 1-px shift would clip the top row:
                ld   b, MK_BRIGHT              ; ASLEEP's whole Z bar; manager 2026-10-14)
                ld   hl, MK_AX
                ld   (hl), b
                ld   h, MK_GLYPHS >> 8
.a:             ld   l, a                      ; HL = the 8 lines (one page)
                ld   a, d
                and  MK_THIRD
                rrca
                rrca
                rrca
                rrca
                ld   b, a                      ; B = third
                add  a, ROOM_MAP >> 8
                ld   d, a                      ; DE = the ROOM_MAP cell (same low byte)
                ld   a, (de)
                add  a, a
                add  a, a
                add  a, a                      ; CF = id bit 5 (ids < 64)
                push af
                ld   a, b
                add  a, a
                add  a, a
                add  a, a
                or   SCREEN_BITMAP >> 8
                ld   b, a
                ld   a, c                      ; A = g - 1
                ld   c, e                      ; BC = bitmap line 0
                ld   e, a                      ; E = g - 1 (for the attr below)
                pop  af
                push de
                ld   e, a
                ld   a, TILE_GLYPHS >> 9
                rla
                ld   d, a                      ; DE = the tile glyph (8-aligned)
.l:             ld   a, (de)
                or   (hl)
                ld   (bc), a
                inc  e
                inc  l
                inc  b
                ld   a, b
                and  7
                jr   nz, .l                    ; 8 lines (B starts on a multiple of 8)
                pop  de                        ; E = g - 1
                ld   a, e
                add  a, MK_ATTRS & $FF
                ld   l, a
                ld   h, MK_ATTRS >> 8
                ld   a, (MK_AX)
                xor  (hl)                      ; the attr (frame B of a full glyph: BRIGHT
                pop  de                        ; toggled); D = R_MK, E = low byte
                push af
                call mk_cbde                   ; C, B = the cell
                call attr_addr                 ; HL = its attr (keeps DE)
                pop  af
                ld   (hl), a
                ld   de, $0101
                jp   pmark_rect
                ASSERT (SCREEN_BITMAP & $7FF) == 0 && (ROOM_MAP & $FF) == 0
                ASSERT (TILE_GLYPHS & $1FF) == 0 && TILE_IDS <= 64

;------------------------------------------------------------------------------
; mk_forget — far7 from mk_slot (this render rewrote the cell) or mk_op (a
; body / FX came over it): mk_sl's mark leaves the books (mk_drop) without an
; erase; a body / FX on its cell now -> the cell is queued (the next render
; restores it and repairs what covers it).  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
mk_forget:
                call mk_drop
                call cell_bf
                ret  nc
                ld   de, $0101
                jp   queue_damage

;------------------------------------------------------------------------------
; mk_erase — mk_sl's drawn mark: unmapped (mk_drop); a body / FX on its cell
; now (it came over the mark in a tick whose damage test did not run: a fire /
; 2nd-frame tick) -> the cell is queued instead (the next render restores it
; and repairs what covers it: an erase_rect here would wipe that body's
; pixels); else the cell is restored from the map (erase_rect: tile glyph +
; the attr shadow) and marked for present.
; Out: bank 7 paged.  Clobbers: A, BC, DE, HL.  ~0.9k T
;------------------------------------------------------------------------------
mk_erase:
                call mk_drop
                call cell_bf                   ; (BC kept)
                jr   nc, .e
                ld   de, $0101
                jp   queue_damage
.e:             push bc
                ld   de, $0101
                call erase_rect
                pop  bc
                ld   de, $0101
                jp   pmark_rect

;------------------------------------------------------------------------------
; mk_drop — mk_sl's drawn mark leaves the books: R_MK 0, its map bit cleared,
; MK_N - 1. Out: C, B = its cell.  Clobbers: A, DE, HL
;------------------------------------------------------------------------------
mk_drop:
                call mk_rec
                call mk_cb
                ld   (hl), 0
                ld   hl, MK_N
                dec  (hl)
                call mk_bit
                cpl
                and  (hl)
                ld   (hl), a
                ret

; mk_spend — one op of this tick: CF = 1 when none is left, else MK_LEFT - 1,
; MK_OPS + 1 (CF = 0).  Clobbers: A
mk_spend:
                ld   a, (MK_LEFT)
                sub  1
                ret  c
                ld   (MK_LEFT), a
                ld   a, (MK_OPS)
                inc  a                         ; (CF still 0)
                ld   (MK_OPS), a
                ret

;------------------------------------------------------------------------------
; mk_sweep — far7 from mark_tick every 8th first-frame tick while a mark is
; drawn: a mark of a slot not visible (R_VIS 0: dead / left / hidden, maybe
; out of RLIST, which the pass walks) is erased, ops permitting.
; Clobbers: A, BC, DE, HL.  ~0.8k T + the erases
;------------------------------------------------------------------------------
mk_sweep:
                xor  a
.l:             ld   (mk_sl), a
                rlca
                rlca
                rlca
                rlca
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   a, (hl)                   ; R_VIS
                or   a
                jr   nz, .n
                call mk_rec
                ld   a, (hl)
                or   a
                jr   z, .n
                call mk_spend
                ret  c
                call mk_erase
.n:             ld   a, (mk_sl)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret

;------------------------------------------------------------------------------
; vis_tail — far7 from the tail of vis_reset / vis_room_sync (low RAM): the
; screen was redrawn for a new room / world, so the overlays start over —
; mk_room, then drip_room. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
vis_tail:
                call mk_room
                jp   drip_room

;------------------------------------------------------------------------------
; mk_room — every mark forgotten without an erase (the screen was redrawn or
; scrolled; game.md §6.4.1: "Room change clears all marks", the next passes
; rebuild them from ST_FLAGS), MK_MAP cleared, the glyph + attr copy
; refreshed: MK_GLYPHS = per glyph a 0 byte + status_icons[0..4] (bank-1
; vdata via copy_virt3, which restores bank 7), then a final 0 (frame B = a
; -1 source offset, mark.asm); MK_ATTRS = status_icons_attr[0..4]. The BASIC
; area under MK_RAM is garbage at boot: zeroed here first.
; Clobbers: A, BC, DE, HL.  Cold: ~4k T per room entry.
;------------------------------------------------------------------------------
mk_room:
                ld   hl, SLOTREC + R_MK
                ld   b, P_MAX_ENT
                xor  a
.z:             ld   (hl), a                   ; R_MK
                inc  l
                ld   (hl), a                   ; R_MKLO
                ld   a, l
                add  a, SLOTREC_STRIDE - 1
                ld   l, a
                xor  a
                djnz .z
                ld   (MK_N), a
                ld   (MK_RR), a
                ld   hl, MK_RAM
                ld   de, MK_RAM + 1
                ld   bc, MK_RAM_END - MK_RAM - 1
                ld   (hl), a
                ldir
                ld   hl, status_icons
                ld   de, MK_GLYPHS + 1
                ld   b, MK_KINDS
.g:             push bc
                push hl
                ld   bc, 8
                call copy_virt3                ; DE past the copy
                pop  hl
                ld   bc, 8
                add  hl, bc
                inc  de                        ; the next record's leading 0
                pop  bc
                djnz .g
                ld   hl, status_icons_attr
                ld   de, MK_ATTRS
                ld   bc, MK_KINDS
                jp   copy_virt3
                ASSERT R_MKLO == R_MK + 1 && (SLOTREC & $FF) == 0 && P_MAX_ENT * SLOTREC_STRIDE == 256
                ASSERT MK_ATTRS == MK_GLYPHS + MK_KINDS * MK_G_STRIDE + 1 && status_icons_attr == status_icons + 7 * 8

;------------------------------------------------------------------------------
; mk_hide — hide_sprites (before a transition): erase every drawn mark (the
; old room scrolls out with no mark on it); mk_room on the arrival forgets
; the rest. Leaves bank 7 paged.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
mk_hide:
                xor  a
.l:             ld   (mk_sl), a
                ld   a, (MK_N)
                or   a
                ret  z                         ; none (left) drawn
                call mk_rec
                ld   a, (hl)
                or   a
                call nz, mk_erase
                ld   a, (mk_sl)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret
