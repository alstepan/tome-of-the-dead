;==============================================================================
; ux0.asm — ITEM-INFO + UX-POLISH (UX1), bank-0 B0_CODE2 (docs/design/item_info.md,
; docs/design/ux_polish.md). Rules (memory-map "B0CODE ledger"): runs with BANK_TEXT
; = bank 0 at $C000, entered by FARB0 (or a direct call from b0_code: dn_tick); never
; pages $C000 itself (print6x / tx_dec / msg_push hand bank 0 back); no SMC, no
; runtime-written bytes here (the state is ITEM_RAM's UX_RAM, item_defs.asm).
;   ie_line     the bag page's row 19: the item's effect phrase[, gate phrase]
;   ux_tick / ux_mpset / ux_mpkey / ux_ptr   panel flashes F2-F3 (+ F1's rebuild; item_food: R6)
;   ux_pick / ux_compact   NEW_MASK / LAST_PICK (C2 / C3), the first-book hint (§6)
;   mn_sub0     the main menu's subtitle / footer attrs + the tutorial pointer (row 10)
;==============================================================================

HPLOW_MIN       EQU 5               ; F2: HP <= max(MAXHP >> 2, HPLOW_MIN) flashes
MPF_TICKS       EQU 16              ; F3: 16 game ticks = >= 32 frames (see ux_polish.md s2)
UX_A_ROW        EQU SCREEN_ATTR + STAT_ROW * 32                 ; row 21 attrs ($5AA0)
UX_B_ROW        EQU SCREEN_BITMAP + ((STAT_ROW & $18) << 8) + ((STAT_ROW & 7) << 5)   ; row 21 line 0
HG_WORD_CELLS   EQU GEAR_COL - HUNGER_COL                       ; the FOOD word, cols 19..23
                ASSERT (UX_A_ROW & $FF) + 32 <= 256 && (UX_B_ROW & $FF) + 32 <= 256
                ASSERT E_MAXHP == E_HP + 1

;------------------------------------------------------------------------------
; ie_line — ITEM-INFO §2-3: FARB0 from page_ovl pg_info, A = a bag type: row 19
; from x 16 = its effect phrase (ie_map bits 0-4, TX_IE_CURE + k - 1), then ", "
; + the gate phrase (bit 6 METAL / bit 7 CLOTH); blank when neither (the row was
; cleared). Composed in IE_BUF (<= 40 chars + 0, pack-time checked: itemtab).
; Clobbers: A, BC, DE, HL.   ~1-3k T per phrase (tx_dec) + print6 ~0.46k T/char
;------------------------------------------------------------------------------
ie_line:        sub  IT_BAG_LO
                ret  c
                cp   IT_COUNT - IT_BAG_LO
                ret  nc
                ld   l, a
                ld   h, 0
                ld   de, ie_map
                add  hl, de
                ld   a, (hl)
                ld   de, IE_BUF
                push af                        ; the map byte
                and  IEM_PHR
                jr   z, .g
                add  a, TX_IE_CURE - 1
                call ie_cat
.g:             pop  af
                and  IEM_METAL | IEM_CLOTH
                jr   z, .out
                ld   b, TX_IE_METAL
                rlca                           ; CF = CLOTH (bit 7)
                jr   nc, .m
                inc  b                         ; TX_IE_CLOTH
.m:             ld   a, e
                cp   IE_BUF & $FF
                jr   z, .n                     ; no phrase before it: no ", "
                ld   a, ','
                ld   (de), a
                inc  de
                ld   a, ' '
                ld   (de), a
                inc  de
.n:             ld   a, b
                call ie_cat
.out:           xor  a
                ld   (de), a                   ; (IE_BUF = "" when there is nothing: test-observable)
                ld   a, e
                cp   IE_BUF & $FF
                ret  z                         ; nothing to say
                ld   hl, IE_BUF
                ld   b, IE_ROW
                ld   e, IE_X
                jp   print6
; ie_cat — A = TX id: its decoded text at DE, DE advanced (no 0). Clobbers: A, BC, HL
ie_cat:         push de
                call tx_dec                    ; HL = TX_DEC (bank 0 handed back)
                pop  de
.c:             ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  hl
                inc  de
                jr   .c
                ASSERT TX_IE_CLOTH == TX_IE_METAL + 1 && (IE_BUF >> 8) == ((IE_BUF + IE_BUF_LEN - 1) >> 8)
IE_ROW          EQU 19
IE_X            EQU 16
IEM_PHR         EQU $1F             ; ie_map: phrase k + 1 (TX_IE_CURE + k), 0 = none
IEM_METAL       EQU $40             ; the gate phrases (gear_rules.md §1.1 classes)
IEM_CLOTH       EQU $80
; ie_map — 1 B per bag type IT_BAG_LO..IT_COUNT-1 (tests/itemtab.py checks it against the spec table)
ie_map:         DB   0, 0, 0, 0, 0                                     ; food 5..9
                DB   0, 0, TX_IE_CURE - TX_IE_CURE + 1                 ; potions: Heal, Mana, Cure
                DB   TX_IE_TELEPORT - TX_IE_CURE + 1, TX_IE_FEAR - TX_IE_CURE + 1
                DB   TX_IE_SLEEP - TX_IE_CURE + 1, TX_IE_ENCHANT - TX_IE_CURE + 1   ; scrolls 13..16
                DB   TX_IE_BOOK - TX_IE_CURE + 1, TX_IE_BOW - TX_IE_CURE + 1         ; 17 book, 18 bow
                DB   0, 0, 0, 0, 0, 0                                  ; 19..24 weapons (Cleaver: gear_dec only)
                DB   TX_IE_RUNE - TX_IE_CURE + 1, TX_IE_BONE - TX_IE_CURE + 1        ; 25 / 26 staves
                DB   IEM_CLOTH, 0, IEM_METAL                           ; 27 Robe, 28 Leather, 29 Chain
                DB   TX_IE_PLATE - TX_IE_CURE + 1 | IEM_METAL          ; 30 Plate
                DB   TX_IE_SILK - TX_IE_CURE + 1, TX_IE_GCLOAK - TX_IE_CURE + 1      ; 31 / 32 unique cloaks
                DB   IEM_CLOTH, IEM_METAL, 0                           ; 33 Hood, 34 Helm, 35 King Helm
                DB   TX_IE_MIRROR - TX_IE_CURE + 1                     ; 36 Mirror Helm
                DB   0, 0, TX_IE_FIRE - TX_IE_CURE + 1                 ; 37 Might, 38 Ward, 39 Fire Ring
                DB   TX_IE_MANA - TX_IE_CURE + 1, TX_IE_PLENTY - TX_IE_CURE + 1      ; 40 / 41 amulets
                DB   TX_IE_SCARAB - TX_IE_CURE + 1, TX_IE_GRING - TX_IE_CURE + 1     ; 42 / 43 uniques
ie_map_end:
                ASSERT ie_map_end - ie_map == IT_COUNT - IT_BAG_LO && IT_COUNT == 44
                ASSERT TX_IE_GRING - TX_IE_CURE + 1 <= IEM_PHR && TX_IE_METAL == TX_IE_GRING + 1

;------------------------------------------------------------------------------
; Panel flashes (UX §1-2): every flash is REBUILT from game state when its cells
; are drawn, never remembered. ux_grp is the one writer of the flash cells.
; ux_grp — row 21 cells C..C+B-1 := (bar cell D's attr & $7F) | FLASH, FLASH if
; (A bit 7 = the state wants it, or the bar has FLASH = a tutorial pointer over the
; row) and the cell holds an ink pixel (R4: text cells only; a blank cell would
; flash as a solid block).  Clobbers: A, BC, DE, HL.   ~60 + ~0.2k T a cell
;------------------------------------------------------------------------------
ux_grp:         ld   e, a
                ld   h, UX_A_ROW >> 8
                ld   a, d
                add  a, UX_A_ROW & $FF
                ld   l, a
                ld   a, (hl)                   ; the bar's attr (the bars never flash)
                ld   d, a
                and  $80
                or   e
                ld   e, a                      ; E = $80 wanted / 0
                res  7, d                      ; D = the base attr
.c:             push bc
                ld   a, d
                inc  e
                dec  e
                jr   z, .w                     ; no FLASH wanted: the base, no pixel test
                ld   a, c
                add  a, UX_B_ROW & $FF
                ld   l, a
                ld   h, UX_B_ROW >> 8
                xor  a
                ld   b, 8
.p:             or   (hl)
                inc  h
                djnz .p
                or   a                         ; Z = a blank cell
                ld   a, d
                jr   z, .w
                or   e
.w:             ld   b, a
                ld   a, c
                add  a, UX_A_ROW & $FF
                ld   l, a
                ld   h, UX_A_ROW >> 8
                ld   (hl), b
                pop  bc
                inc  c
                djnz .c
                ret

; ux_hpg — F2: HP number cells 5-6 flash iff HP <= max(MAXHP >> 2, HPLOW_MIN) (8-bit)
ux_hpg:         call ux_hpw
                ld   bc, (2 << 8) | HP_NUM_COL
                ld   d, HP_BAR_COL
                jr   ux_grp
; ux_hpw — A = $80 if the HP number AS DRAWN (PANEL_HP_SH: the panel never shows a turn's
; result in its input tick, D5 / W15) should flash, else 0.  Clobbers: F, HL
ux_hpw:         ld   hl, (PANEL_HP_SH)         ; L = HP, H = MAXHP as drawn ($FF $FF: never -> off)
                ld   a, h
                srl  a
                srl  a
                cp   HPLOW_MIN
                jr   nc, .t
                ld   a, HPLOW_MIN
.t:             cp   l                         ; CF = HP above the threshold
                sbc  a, a
                cpl
                and  $80
                ret
; ux_mpg — F3: MP number cells 12-13 flash while MPF_T != 0
ux_mpg:         ld   a, (MPF_T)
                or   a
                jr   z, .g
                ld   a, $80
.g:             ld   bc, (2 << 8) | MP_NUM_COL
                ld   d, MP_BAR_COL
                jr   ux_grp
; ux_foodg — F1: the FOOD word cells 19-23 flash at stage WEAK (the bar 15-18 never)
ux_foodg:       ld   a, (HSTAGE)
                cp   HS_WEAK
                ld   a, 0
                jr   nz, .g
                ld   a, $80
.g:             ld   bc, (HG_WORD_CELLS << 8) | HUNGER_COL
                ld   d, FOOD_BAR_COL
                jr   ux_grp

;------------------------------------------------------------------------------
;------------------------------------------------------------------------------
; ux_tick — dn_tick (b0_code, direct; GS_PLAYING ticks whose work ended in the 1st
; frame): F3's countdown (MPF_T -> 0 = off), then F2 rebuilt from the drawn HP / MAXHP
; every such tick (item_hp only draws; W15 caps its 2nd-frame cost), the HP number cells
; marked for the present only when their attrs changed.
; Clobbers: A, BC, DE, HL.   ~0.15k T idle; ~0.6k T while the HP number flashes
;------------------------------------------------------------------------------
ux_tick:        ld   a, (MPF_T)
                or   a
                call nz, ux_mptick
                call ux_hpw
                ld   hl, UX_A_ROW + HP_BAR_COL
                ld   e, (hl)                   ; the bar's attr (bit 7: a tutorial pointer)
                or   e
                and  $80
                jr   nz, .f                    ; a FLASH is wanted: rebuild, then compare
                res  7, e                      ; E = the base attr
                ld   l, (UX_A_ROW + HP_NUM_COL) & $FF
                ld   a, (hl)
                cp   e
                jr   nz, .f
                inc  l
                ld   a, (hl)
                cp   e
                ret  z                         ; both plain already: nothing to do
.f:             ld   hl, (UX_A_ROW + HP_NUM_COL)
                push hl                        ; the old pair
                call ux_hpg
                pop  de
                ld   hl, (UX_A_ROW + HP_NUM_COL)
                or   a
                sbc  hl, de
                ret  z                         ; unchanged: no present work
                ld   bc, (STAT_ROW << 8) | HP_NUM_COL
                ld   de, (2 << 8) | 1
                jp   pmark_rect
; ux_mpset — FARB0 from bank-7 ic_no_mana (a NO MANA refusal): F3 for MPF_TICKS.
; ux_mptick — ux_tick while MPF_T != 0: the countdown; 0 = F3 off.
; ux_mpkey — FARB0 from bank-7 intent_icon7 on a new press in ICON MODE: F3 off.
;            Keeps DE (D / E = the stick, pressed).
; ux_ptr — FARB0 from the D0 blob's tt_ptr after a pointer set / clear: F1-F3
;          rebuilt (the pointer's own pmark_rect follows).
; Clobbers: A, BC, DE, HL (ux_mpkey: DE kept).   ~0.6-1.5k T + farb
;------------------------------------------------------------------------------
ux_mpset:       ld   a, MPF_TICKS
                ld   (MPF_T), a
ux_mp:          call ux_mpg
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL
                ld   de, ((MP_NUM_COL + 2 - MP_BAR_COL) << 8) | 1
                jp   pmark_rect
ux_mptick:      ld   hl, MPF_T
                dec  (hl)
                ret  nz
                jr   ux_mp
ux_mpkey:       ld   hl, MPF_T
                ld   a, (hl)
                or   a
                ret  z
                ld   (hl), 0
                push de
                call ux_mp
                pop  de
                ret
ux_ptr:         call ux_hpg
                call ux_mpg
                jp   ux_foodg

;------------------------------------------------------------------------------
; ux_pick — FARB0 from R6 pu_add after a successful bag pickup (its log line is
; queued): A = type, E = 3 * slot. C3: NEW_MASK bit; C2: LAST_PICK := slot (a
; stack top-up too); §6: the first IT_BOOK of a game sets UXF_HINT_B and queues
; READ IT IN THE BAG, silently in D0 (Morrow teaches READ: pl_et = ts_turn).
; Clobbers: A, BC, DE, HL.   ~0.2k T (+ msg_push once a game)
;------------------------------------------------------------------------------
ux_pick:        push af
                ld   a, e
                call ux_div3                   ; A = slot
                ld   (LAST_PICK), a
                call ux_bit
                or   (hl)
                ld   (hl), a
                pop  af
                cp   IT_BOOK
                ret  nz
                ld   hl, UX_FL
                bit  UXF_HINT_B, (hl)
                ret  nz
                set  UXF_HINT_B, (hl)
                ld   hl, (pl_et + 1)           ; the D0 tutorial's turn stub while it runs
                ld   de, ts_turn
                or   a
                sbc  hl, de
                ret  z
                ld   a, TX_HINT_BOOK
                jp   msg_push
; ux_div3 — A = 3k (k <= 23) -> A = k.  Clobbers: C, F
ux_div3:        ld   c, $FF
.d:             inc  c
                sub  3
                jr   nc, .d
                ld   a, c
                ret
; ux_bit — A = slot 0..23 -> HL = its NEW_MASK byte, A = its bit mask.  Clobbers: B, F
ux_bit:         ld   b, a
                rrca
                rrca
                rrca
                and  $1F
                add  a, NEW_MASK & $FF
                ld   l, a
                ld   h, NEW_MASK >> 8
                ld   a, b
                and  7
                ld   b, a
                inc  b
                ld   a, $80
.r:             rlca
                djnz .r
                ret
                ASSERT (NEW_MASK >> 8) == ((NEW_MASK + 2) >> 8)

;------------------------------------------------------------------------------
; ux_compact — FARB0 from R6 bag_take when slot k empties (before the shift),
; A = 3k (UX §4): LAST_PICK k -> $FF, > k -> -1; NEW_MASK bits above k shift down
; one (bit 19 := bit 20 = 0): byte i := M_i ^ ((M_i ^ S_i) & ~keep_i), S = M >> 1,
; keep = the bits below k.  Clobbers: A, BC, DE, HL.   ~0.4k T
;------------------------------------------------------------------------------
ux_compact:     call ux_div3
                ld   c, a                      ; C = k
                ld   hl, LAST_PICK
                ld   a, (hl)
                inc  a
                jr   z, .nm                    ; none
                dec  a
                cp   c
                jr   c, .nm                    ; below k: stays
                jr   nz, .dc
                ld   (hl), $FF                 ; k itself: gone
                jr   .nm
.dc:            dec  (hl)
.nm:            ld   hl, NEW_MASK
                ld   d, 3
.y:             ld   a, c
                sub  8
                jr   c, .p
                ld   c, a                      ; k -= 8: this byte is all kept
                ld   e, 0
                jr   .q
.p:             ld   b, c
                inc  b
                ld   a, $FF
                jr   .m1
.m:             add  a, a
.m1:            djnz .m
                ld   e, a                      ; E = ~keep = $FF << k
                ld   c, b                      ; (B = 0) the next bytes shift whole
.q:             ld   a, d
                dec  a
                jr   z, .z                     ; the top byte: shifts in 0
                inc  l
                ld   a, (hl)
                dec  l
                rra                            ; CF = the next byte's bit 0
                jr   .s
.z:             or   a
.s:             ld   a, (hl)
                ld   b, a
                rra                            ; S_i
                xor  b
                and  e
                xor  b
                ld   (hl), a
                inc  l
                dec  d
                jr   nz, .y
                ret

;------------------------------------------------------------------------------
; mn_sub0 — FARB0 from bank-1 menu_static (ITEM-INFO: moved out of bank 1 with the
; new line): the subtitle (row 5) + its attrs (rows 5-6), the footer attrs (rows
; 22-23), and, only while the tutorial is offered (es_go = ts_choice, TUT0), the
; pointer NEW HERE? START > 1 TUTORIAL on row 10 cols 0-20 (attr $45, item_info.md §5).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
MN_TUT_ROW      EQU 10
MN_TUT_ATTR     EQU $45
mn_sub0:        ld   a, TX_FT_SUBTITLE
                ld   b, 5
                ld   e, 9 * 8                  ; 19 chars x 6 = 114 px: centred at x=71 ~ 72 (E: multiple of 8)
                call print6x
                ld   a, MENU_A_SUB
                ld   bc, 5 << 8
                ld   de, (32 << 8) | 2         ; rows 5-6
                call stamp_rect
                ld   a, MENU_A_LABEL
                ld   bc, 22 << 8
                ld   de, (32 << 8) | 2
                call stamp_rect
                ld   hl, (es_go + 1)
                ld   de, ts_choice
                or   a
                sbc  hl, de
                ret  nz                        ; no offer: row 10 stays blank (attrs 0)
                ld   a, TX_MN_TUT
                ld   b, MN_TUT_ROW
                ld   e, 0
                call print6x
                ld   a, MN_TUT_ATTR
                ld   bc, MN_TUT_ROW << 8
                ld   de, (MN_TUT_W << 8) | 1
                jp   stamp_rect
MN_TUT_W        EQU (TXL_MN_TUT * 6 + 7) / 8   ; 28 chars = 21 cells (cols 0-20, the previews start at 21)
                ASSERT MN_TUT_W <= 21
