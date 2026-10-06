;==============================================================================
; info1.asm — the info line item, bank 1 (C3 review "bank-3 relief": moved
; from panel.asm; entered by far1 from panel_more). The text block is this
; bank, so print6x's BANK_TEXT paging is a no-op here; print6x / print6 /
; MSG_BUF are bank 2.
;==============================================================================
;------------------------------------------------------------------------------
; item_info — far1 from panel_more (PD_INFO, 1st frame only): the info line
; (row 20, 6x8 font, <= 42 chars) of the selected slot: the row's bitmap is
; cleared whole, then its info_* string (print6x: straight from the text
; block — no log ring, no MSG_BUF for the 42-char stream), then the live
; numbers: the potion count "X n" in the numbers field; the Bag "LV n" (numbers
; field) and "XP x/next" (notes field, game.md §4.1; "XP x" at L9).
; Clobbers: all but IX, IY.   ~25k T (42 chars)
;------------------------------------------------------------------------------
INFO_BM         EQU ((SCREEN_BITMAP >> 8) | (INFO_ROW & $18)) << 8 | ((INFO_ROW & 7) << 5)
item_info:
                ld   hl, INFO_BM
                xor  a
                ld   b, 8
.cl:            DUP  ROOM_COLS
                ld   (hl), a
                inc  l
                EDUP
                ld   l, INFO_BM & $FF
                inc  h
                djnz .cl
                ld   a, ROOM_COLS              ; the whole row changed
                ld   (HUD4_EXT), a
                ld   (HUD4_PW), a
                ld   a, 1
                ld   (PRES_ANY), a
                ASSERT TEXT_ROW == INFO_ROW    ; HUD4_EXT / HUD4_PW entry 0 = row 20
                ld   a, (SEL_SLOT)
                ld   b, a
                ld   a, (HERO_KIND)
                or   a
                ld   a, b
                jr   z, .k
                add  a, ICON_SLOTS
.k:             ld   e, a
                ld   d, 0
                ld   hl, info_tab
                add  hl, de
                ld   a, (hl)
                cp   TX_NONE
                ret  z                         ; the Warrior's spare slot: blank
                ld   (INFO_TX), a
                ld   b, a
                ld   a, (ICON_MODE)            ; C3-2b: ">" prefix in ICON MODE
                ld   (PRE_N), a
                ld   a, b
                ld   b, INFO_ROW
                ld   e, 0
                call print6x
                xor  a
                ld   (PRE_N), a
                ld   a, (INFO_TX)              ; the line's id says what follows
                cp   TX_INFO_POTION
                jr   z, .pot
                cp   TX_INFO_BAG
                ret  nz
                ; Bag: LV n / XP x[/next]
                ld   hl, MSG_BUF
                ld   (hl), 'L'
                inc  l
                ld   (hl), 'V'
                inc  l
                ld   (hl), ' '
                inc  l
                ld   a, (LVL)
                add  a, '0'
                ld   (hl), a
                inc  l
                ld   (hl), 0
                call .num_at
                ld   hl, MSG_BUF
                ld   (hl), 'X'
                inc  l
                ld   (hl), 'P'
                inc  l
                ld   (hl), ' '
                inc  l
                ex   de, hl
                ld   hl, (XP)
                call dec16                     ; DE -> after the digits
                ld   a, (LVL)
                cp   LVL_MAX
                jr   nc, .xe
                ex   de, hl
                ld   (hl), '/'
                inc  l
                ex   de, hl
                dec  a                         ; LVL 1..8 -> xp_next[LVL - 1]
                add  a, a
                ld   l, a
                ld   h, 0
                ld   bc, xp_next
                add  hl, bc
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                call dec16
.xe:            xor  a
                ld   (de), a
                ld   hl, MSG_BUF
                ld   b, INFO_ROW
                ld   e, INFO_NOTE_X
                jp   print6
.pot:           ld   hl, MSG_BUF               ; "X n"
                ld   (hl), 'X'
                inc  l
                ld   a, (P_ENTITIES + E_POT)
                cp   10
                jr   c, .pd
                ld   a, 9
.pd:            add  a, '0'
                ld   (hl), a
                inc  l
                ld   (hl), 0
.num_at:        ld   hl, MSG_BUF
                ld   b, INFO_ROW
                ld   e, INFO_NUM_X
                jp   print6
INFO_NUM_X      EQU 16 * 6                     ; char 16 (96 px, a cell: print6 x rule)
INFO_NOTE_X     EQU 28 * 6                     ; char 28 (168 px)
                ASSERT (INFO_NUM_X & 7) == 0 && (INFO_NOTE_X & 7) == 0 && INFO_NOTE_X + 6 * 14 <= 256
LVL_MAX         EQU 9

; dec16 — HL = 0..65535 as decimal (no leading zeros) at (DE) .. DE out.
; Clobbers: A, BC, HL
dec16:
                push ix
                ld   ix, .pow
                ld   c, 0                      ; 0 until the first non-zero digit
.dg:            push de
                ld   e, (ix+0)
                ld   d, (ix+1)
                ld   a, '0' - 1
                or   a
.sb:            inc  a
                sbc  hl, de
                jr   nc, .sb
                add  hl, de
                pop  de
                ld   b, a
                ld   a, (ix+0)
                dec  a
                or   (ix+1)
                jr   z, .last                  ; the units digit always prints
                ld   a, b
                cp   '0'
                jr   nz, .put
                inc  c
                dec  c
                jr   z, .nx
.put:           ld   (de), a
                inc  de
                inc  c
.nx:            inc  ix
                inc  ix
                jr   .dg
.last:          ld   a, b
                ld   (de), a
                inc  de
                pop  ix
                ret
.pow:           DW   10000, 1000, 100, 10, 1

xp_next:        DW   40, 100, 200, 340, 500, 700, 920, 1150   ; game.md §4.1, L1..L8

; info line string per class x slot (TX_NONE: blank)
info_tab:       DB TX_INFO_SWORD, TX_INFO_POWER, TX_INFO_WHIRL, TX_INFO_DAGGERS, TX_INFO_BOW
                DB TX_INFO_FOOD, TX_INFO_POTION, TX_INFO_SCROLL, TX_INFO_BAG, TX_NONE
                DB TX_INFO_STAFF, TX_INFO_SPARK, TX_INFO_FIREBOLT, TX_INFO_FROST, TX_INFO_DRAIN
                DB TX_INFO_LIGHTNING, TX_INFO_FOOD, TX_INFO_POTION, TX_INFO_SCROLL, TX_INFO_BAG

