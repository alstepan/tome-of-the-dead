;==============================================================================
; pickup7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): the
; end-of-turn floor pickup, list-driven (T6): potions (prototype §6.6; was
; potion_pickup, which looked at the map tile) and dropped daggers / arrows
; (IT_DAGGER / IT_ARROW stacks, game.md §6.3). Shared cells (§6.3): every
; entry under the hero is taken by its own rule, and the cell is re-stamped
; with the last live entry left there (ap_stamp).
;==============================================================================

DAGGERS_MAX     EQU 9                          ; game.md §6.3 stack limits
ARROWS_MAX      EQU 24

;------------------------------------------------------------------------------
; floor_pickup — end_turn (game.md §8: pickup is automatic). The hero standing,
; not DYING: every FLOOR_LIST entry of CUR_ROOM on his storey whose col his
; body covers (x .. x + w - 1), in list order:
;   IT_POTION / IT_POT_LO..HI (3E-T6: the generated potions, until T11's
;     bag): E_POT < MAX_POTIONS -> taken (pp_take; else it stays);
;   other item types (food, scrolls, books, gear, bow): ignored, left in
;     place (T11 picks them up into the BAG);
;   IT_DAGGER / IT_ARROW, the Warrior only (the Mage has no ammunition):
;     what fits under the cap (DAGGERS 9 / ARROWS 24; arrows need no bow):
;     "YOU PICK UP n DAGGERS / ARROW(S)" when n > 0; an emptied entry ->
;     FL_EMPTY, a remainder stays (FL_QTY -= n) and prints "QUIVER FULL"
;     (also when n = 0) (ap_take).
; Each taken / matched entry re-stamps its cell (ap_stamp).
; Clobbers: all but IY (IX = hero on return).
; ~0.4k T a turn with no item tile under the body (T7 pre-filter), else ~3k T
; (the 32-entry scan) + ~3-6k T per entry taken
;------------------------------------------------------------------------------
floor_pickup:
                ld   ix, P_ENTITIES
                ld   a, (ix+E_FLAGS)
                and  EF_DYING
                ret  nz
                call is_standing
                ret  nz
                call get_box                   ; C = x, D = w (A, B, E, HL)
                call storey_ref                ; A = s (A, HL)
                ; T7 pre-filter (~0.3k T, saves the ~3k T scan on almost every
                ; turn): a live entry always shows on its cell — build_room_map
                ; stamps every one, ap_stamp re-stamps the last live entry of a
                ; cell after a pickup, decor only lands on T_AIR — so no item tile
                ; under the body on the item row (9s + 7) = nothing to pick up.
                ld   e, a                      ; E = s
                call storey_row                ; A = 9s + 7 (keeps BC; B scratch)
                ld   b, a
                call cell_addr                 ; HL = (row, x) (A, HL)
                ld   b, d                      ; the body's cols (x + w <= 32: one row)
.pf:            ld   a, (hl)
                cp   T_POTION
                jr   z, .scan
                cp   T_AMMO                    ; daggers + arrows share the one glyph
                jr   nz, .pn
                ld   a, (HERO_KIND)            ; ammo: the Warrior's only (K_KNIGHT 0)
                or   a
                jr   z, .scan
.pn:            inc  l
                djnz .pf
                ret
.scan:          ld   a, e
                rrca                           ; s -> FL_S1 (bit 7)
                ld   e, a
                ld   a, (CUR_ROOM)
                or   e
                ld   e, a                      ; E = the FL_ROOM byte to match
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX
.l:             ld   a, (hl)
                and  FL_ROOM_MASK | FL_S1      ; as build_room_map: bits 4-6 ignored
                cp   e                         ; (FL_EMPTY -> $8F: never a room)
                jr   nz, .n
                inc  l
                ld   a, (hl)                   ; FL_COL
                sub  c
                cp   d
                jr   nc, .n1                   ; not under the body
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                push bc
                push de
                push hl
                cp   IT_POTION
                jr   z, .pt
                cp   IT_POT_LO                 ; 3E-T6: generated potions (Heal / Mana /
                jr   c, .am                    ; Cure) still count as E_POT until T11
                cp   IT_POT_HI + 1
                jr   nc, .nx                   ; other new types: left in place (T11)
.pt:            call pp_take
                jr   .nx
.am:            ld   a, (HERO_KIND)
                or   a
                jr   nz, .nx                   ; the Mage (K_KNIGHT == 0: the Warrior)
                ld   a, (hl)
                sub  IT_DAGGER
                cp   IT_ARROW - IT_DAGGER + 1
                call c, ap_take                ; A = 0 daggers / 1 arrows
.nx:            pop  hl
                pop  de
                pop  bc
                dec  l
.n1:            dec  l
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .l
                ret
                ASSERT FL_ROOM == 0 && FL_COL == 1 && FL_ITEM == 2 && FL_QTY == 3 && FL_S1 == $80
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE <= 256 && FL_STRIDE == 4
                ASSERT ((FL_EMPTY & (FL_ROOM_MASK | FL_S1)) & FL_ROOM_MASK) >= GRID_CELLS
                ASSERT IT_ARROW == IT_DAGGER + 1 && T_ARROWS == T_DAGGERS && K_KNIGHT == 0

; pp_take — a potion entry: HL = its &FL_ITEM, E = the FL_ROOM byte, IX =
; hero. E_POT < MAX_POTIONS: E_POT += 1, the entry -> FL_EMPTY, its
; POTIONS_TAKEN bit (entry index 0..7: the PROTO potion ids 0..3 are entries
; 0..3, new_game), "YOU PICK UP A POTION", the cell re-stamped.
; Clobbers: all but IX, IY.
pp_take:
                ld   a, (ix+E_POT)
                cp   MAX_POTIONS
                ret  nc                        ; full pack: it stays on the floor
                inc  (ix+E_POT)
                dec  l
                ld   c, (hl)                   ; C = col
                dec  l
                ld   (hl), FL_EMPTY
                ld   a, l
                rrca
                rrca                           ; the entry index (FLOOR_LIST page-aligned)
                cp   8
                jr   nc, .nb                   ; > 8 entries: no POTIONS_TAKEN bit
                push de
                call bitmask                   ; (A, D)
                pop  de
                ld   hl, POTIONS_TAKEN
                or   (hl)
                ld   (hl), a
.nb:            ld   a, SFX_PICKUP             ; SND-5b (keeps BC / DE / HL)
                call sfx_req
                push bc
                push de
                ld   a, TX_FOUND
                call msg_push                  ; queued (panel_tick; lowram, re-pages bank 7)
                pop  de
                pop  bc
                jp   ap_stamp

; ap_take — one ammo stack: A = 0 daggers / 1 arrows, HL = its &FL_ITEM, E =
; the FL_ROOM byte. Takes min(FL_QTY, cap - counter), logs, re-stamps the
; cell.  Clobbers: all but IX, IY.
ap_take:
                ld   d, a                      ; D = type
                inc  l                         ; -> FL_QTY
                push hl                        ; [&FL_QTY]
                ld   hl, DAGGERS
                add  a, l
                ld   l, a                      ; HL = DAGGERS / ARROWS (same page)
                ld   a, d
                or   a
                ld   a, DAGGERS_MAX
                jr   z, .c
                ld   a, ARROWS_MAX
.c:             sub  (hl)
                jr   nc, .s
                xor  a                         ; (over the cap, poked: nothing fits)
.s:             ld   c, a                      ; C = space
                ex   (sp), hl                  ; HL = &FL_QTY, [the counter]
                ld   a, (hl)
                cp   c
                jr   c, .f                     ; qty < space: all of it
                ld   a, c
.f:             ld   b, a                      ; B = taken
                ld   a, (hl)
                sub  b
                ld   (hl), a                   ; FL_QTY -= taken
                ld   c, a                      ; C = left on the floor
                ex   (sp), hl                  ; HL = the counter, [&FL_QTY]
                ld   a, (hl)
                add  a, b
                ld   (hl), a                   ; counter += taken
                inc  b
                dec  b
                jr   z, .p0                    ; nothing taken
                ld   a, (PANEL_DIRTY)
                or   PD_AMMO                   ; T7: the ammo count changed (no ammo item drawn
                ld   (PANEL_DIRTY), a          ; yet: the panel clears it, as abil_ammo's)
                ld   a, SFX_PICKUP             ; SND-5b (keeps BC / HL)
                call sfx_req
.p0:            pop  hl
                dec  l
                dec  l                         ; -> FL_COL
                ld   a, (hl)
                push af                        ; [col]
                dec  l                         ; -> FL_ROOM
                ld   a, c
                or   a
                jr   nz, .k
                ld   (hl), FL_EMPTY            ; all taken: the entry is gone
.k:             push de                        ; [type, room]
                push bc                        ; [taken, left]
                ld   a, b
                or   a
                jr   z, .full                  ; nothing fitted
                ; "YOU PICK UP n DAGGERS": the suffix by type and number
                dec  a
                ld   a, TX_CMB_DAGGER
                jr   z, .one
                ld   a, TX_CMB_DAGGERS
.one:           dec  d
                jr   nz, .dg
                sub  TX_CMB_DAGGER - TX_CMB_ARROW   ; (DAGGERS - DAGGER == ARROWS - ARROW)
.dg:            push af                        ; [suffix id]
                ld   de, MSG_BUF
                ld   a, TX_CMB_PICK
                call msg_cat                   ; (A, BC, HL)
                pop  af
                pop  bc
                push bc
                push af
                ld   a, b
                call msg_dec                   ; n (A, BC)
                pop  af
                call msg_cat
                call msg_end                   ; log_push (A, B, DE, HL)
.full:          pop  bc
                pop  de
                ld   a, c
                or   a
                jr   z, .st                    ; nothing left behind
                push de
                ld   a, TX_QUIVER_FULL
                call msg_push                  ; (A, BC, DE, HL)
                pop  de
.st:            pop  af
                ld   c, a                      ; C = col, E = the FL_ROOM byte
                ; fall through
; ap_stamp — C = col, E = the FL_ROOM byte (room | storey bit): the cell (col,
; 9s + 7) of ROOM_MAP <- the glyph of the last live FLOOR_LIST entry there
; (item_glyph), else T_AIR; redrawn next render + the attr shadow
; (shadow_rect leaves bank 7 paged: our bank), then the room's floor inks
; over the shadow (fl_attr_sh: the cell left falls back to TILE_ATTRS of
; its tile).  Clobbers: all but IX, IY.
ap_stamp:
                ld   d, T_AIR
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX
.l:             ld   a, (hl)
                and  FL_ROOM_MASK | FL_S1
                cp   e
                jr   nz, .n
                inc  l
                ld   a, (hl)                   ; FL_COL
                dec  l
                cp   c
                jr   nz, .n
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                dec  l
                call item_glyph                ; 3E-T6 (lowram; keeps BC, DE, HL)
                or   a
                jr   z, .n
                ld   d, a
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .l
                ld   a, e
                rlca
                and  1                         ; s
                call storey_row                ; A = 9s + 7 (keeps BC)
                ld   b, a
                ld   a, ROOM_MAP >> 8
                ld   (TMP1), a
                call map_cell                  ; HL = the cell (keeps BC, DE)
                ld   (hl), d
                ld   de, $0101
                call queue_damage              ; (keeps BC, DE)
                call shadow_rect               ; (bank 7 paged)
                ld   a, (CUR_ROOM)             ; 3E-T6: the inks of what is left
                jp   fl_attr_sh
                ASSERT TX_CMB_ARROWS - TX_CMB_ARROW == TX_CMB_DAGGERS - TX_CMB_DAGGER
                ; T7: the composed pickup line fits a log slot ("YOU PICK UP " + 2 digits +
                ; the longest suffix; ARROWS_MAX < 100) — msg_end does not cut it
                ASSERT TXL_CMB_PICK + 2 + TXL_CMB_DAGGERS <= LOG_MAX && TXL_CMB_PICK + 2 + TXL_CMB_ARROWS <= LOG_MAX
                ASSERT ARROWS_MAX < 100 && DAGGERS_MAX < 100
                ASSERT T_ARROWS == T_DAGGERS && T_DAGGERS == T_AMMO
