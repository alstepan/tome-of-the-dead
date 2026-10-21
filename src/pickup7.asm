;==============================================================================
; pickup7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): the
; end-of-turn floor pickup, list-driven (T6): dropped daggers / arrows
; (IT_DAGGER / IT_ARROW stacks, game.md §6.3) and, since 3E-T11, every bag
; item (pu_add, R6 pickup6.asm). Shared cells (§6.3): every
; entry under the hero is taken by its own rule, and the cell is re-stamped
; with the last live entry left there (ap_stamp).
;==============================================================================

PU_NONE         EQU $80                        ; "no previous span": col - $80 >= w for cols 0..31
DAGGERS_MAX     EQU 9                          ; game.md §6.3 stack limits
ARROWS_MAX      EQU 24

;------------------------------------------------------------------------------
; floor_pickup — end_turn (game.md §8: pickup is automatic). The hero standing,
; not DYING: every FLOOR_LIST entry of CUR_ROOM on his storey whose col his
; body covers (x .. x + w - 1), in list order:
;   IT_DAGGER / IT_ARROW, the Warrior only (the Mage has no ammunition):
;     what fits under the cap (DAGGERS 9 / ARROWS 24; arrows need no bow):
;     "YOU PICK UP n DAGGERS / ARROW(S)" when n > 0; an emptied entry ->
;     FL_EMPTY, a remainder stays (FL_QTY -= n) and prints "QUIVER FULL"
;     (also when n = 0) (ap_take);
;   every other type (3E-T11: potions incl. the legacy IT_POTION = Heal,
;     food, scrolls, book, bow, gear): pu_add (R6) -> BAG; taken ->
;     "YOU PICK UP <name>", the cell re-stamped; bag full -> it stays,
;     "BAG FULL" once per arrival.
; Arrival (BAG FULL only; game.md §8.11 rulings 4): an item's col that was
; NOT under the previous body span (PU_ARR = the previous x .. + w - 1; PU_NONE
; after a room / storey change, PU_POS byte 1 = $FF per level) prints "BAG
; FULL"; walking across one item prints it once. Standing on the cell keeps
; retrying the pickup every turn (the D3-7 ammo behaviour), silently.
; Clobbers: all but IY (IX = hero on return).
; ~0.5k T a turn with no item glyph under the body (T7 pre-filter), else ~3k T
; (the 32-entry scan) + ~3-6k T per ammo entry, ~6k T + ap_stamp (~4-9k T) per
; bag pickup (far6 pu_add: bag_add + pot_sync + name + log)
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
                rrca
                ld   hl, CUR_ROOM
                or   (hl)
                ld   b, a                      ; BC = FL_ROOM byte, x
                ld   hl, (PU_POS)              ; L = the previous x, H = its FL_ROOM byte
                ld   (PU_POS), bc
                ld   a, h
                cp   b
                ld   a, l
                jr   z, .same
                ld   a, PU_NONE                ; another room / storey: no previous span
.same:          ld   (PU_ARR), a               ; the previous x (BAG FULL test, .full)
                ld   a, e
                call storey_row                ; A = 9s + 7 (keeps BC; B scratch)
                ld   b, a
                call cell_addr                 ; HL = (row, x) (A, HL)
                ld   b, d                      ; the body's cols (x + w <= 32: one row)
.pf:            ld   a, (hl)
                cp   T_LVL_OBJ                 ; 60..63: FLASK FOOD WEAPON WORN
                jr   nc, .scan
                cp   T_PAGES                   ; scroll / book
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
                sub  IT_DAGGER
                cp   IT_ARROW - IT_DAGGER + 1
                jr   nc, .bag                  ; not ammo (IT_POTION 1 wraps: bag too)
                ld   b, a
                ld   a, (HERO_KIND)
                or   a                         ; the Mage (K_KNIGHT == 0: the Warrior)
                ld   a, b
                call z, ap_take                ; A = 0 daggers / 1 arrows
                jr   .nx
.bag:           ld   a, (hl)
                ld   hl, pu_add                ; R6: bag_add + the line; L = 1 taken
                call far6                      ; / 0 refused (bag full)
                dec  l
                pop  hl
                pop  de
                push de
                push hl                        ; HL = &FL_ITEM, D = w, E = the FL_ROOM byte
                jr   nz, .full
                call pp_take
                jr   .nx
.full:          dec  l
                ld   a, (hl)                   ; its col
                ld   hl, PU_ARR
                sub  (hl)
                cp   d
                jr   c, .nx                    ; under the previous body span: not an arrival
                xor  a                         ; IT_NONE: the stem alone
                ld   e, S3_BAG_FULL
                ld   hl, it_line               ; bank 1: "BAG FULL"
                call far1
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

; pp_take — a bag item taken (pu_add): HL = its &FL_ITEM, E = the FL_ROOM
; byte. The entry -> FL_EMPTY, its POTIONS_TAKEN bit (entry index 0..7: "entry
; i taken", any type since 3E-T11; the PROTO potions are entries 0..3),
; SFX_PICKUP, the cell re-stamped.  Clobbers: all but IX, IY.
pp_take:
                dec  l
                ld   c, (hl)                   ; C = col
                dec  l
                ld   (hl), FL_EMPTY
                ld   a, l
                rrca
                rrca                           ; the entry index (FLOOR_LIST page-aligned)
                cp   8
                jr   nc, .nb                   ; >= 8: no POTIONS_TAKEN bit
                push de
                call bitmask                   ; (A, D)
                pop  de
                ld   hl, POTIONS_TAKEN
                or   (hl)
                ld   (hl), a
.nb:            ld   a, SFX_PICKUP             ; SND-5b (keeps BC / DE / HL)
                call sfx_req
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
.st:            pop  af                        ; A = col, E = the FL_ROOM byte
                ; fall through
; ap_stamp — C = col, E = the FL_ROOM byte (room | storey bit): the cell (col,
; 9s + 7) of ROOM_MAP <- the glyph of the last live FLOOR_LIST entry there
; (item_glyph), else T_AIR; redrawn next render + the attr shadow
; (shadow_rect leaves bank 7 paged: our bank), then the room's floor inks
; over the shadow (fl_attr_sh: the cell left falls back to TILE_ATTRS of
; its tile). ap_stamp_a: the col in A (3E-T11: far7 from drop_put, R6:
; far7 passes A and DE in, not BC).  Clobbers: all but IX, IY.
ap_stamp_a:
                ld   c, a
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
