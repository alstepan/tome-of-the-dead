;==============================================================================
; page_ovl.asm — 3E-T13/T14 the bag page (game.md §8.11 Q3; layout = the
; approved 3E-T2 placeholder, see the table below). Assembled at PAGE_ORG =
; GEN_SCRATCH (main.asm "OVERLAYS"), stored ZX0-packed in the R6 region
; (ovl_page_zx0, BANK_OVL_PAGE), run by ovl_run from page_ovl (bank 1) with
; BANK_UI1 paged, so it calls the bank-1 helpers (mcell, mattr, mf_char,
; menu_orn_b, row_clear, item_name, it_stems) and the bank-2 / low-RAM ones
; (print6, stamp_rect, menu_frame, sample_input, show_bank5) directly; IC1:
; the 16x16 icons through far6 icon_slot (R6 icons6.asm, the icon table's
; bank).
; Contract (docs/memory-map.md "Overlays", the page window + "Bag page"): the
; caller (page_run) has made screen 2 the composed screen and shows it, and
; page_ovl has saved ROOM_MAP; this code draws the page over all 24 rows of
; the bank-5 screen from BAG / WORN (read only), shows bank 5, runs the modal
; cursor loop and returns when the page closes. The page changes NO game
; state: its only outputs are PAGE_VERB (VB_*, item_defs.asm; VB_NONE = closed
; without a verb) and PAGE_SLOT (0..19 bag, 20..23 worn), applied after the
; close (page_post: VB_DISCARD; T8 / T12: the rest). Music and effects play on.
; Clobbers: A, BC, DE, HL (IX, IY kept).
;
; Layout (cells)                         | Input (new presses only; keys held
;  0     title BAG (menu font, cols 2-4,  |   at the open wait for a release)
;        rows 0-1); ITEMS n/20 (x 48);    |  BREAK / I   close (VB_NONE), any mode
;        [CLOSE] cols 26-31 (selectable)  |  FIRE / ENTER grid: an item -> the verb
;  1     DAGGERS d  ARROWS a (Warrior),   |               strip (first enabled verb);
;        KEY at col 26 (LF_KEY_TAKEN)     |               [CLOSE] -> close; empty: -
;  2/23  ornament                         |               strip: confirm (CLOSE ->
;  4-14  bag 5 x 4: icon 2x2 at row       |               close; REMOVE with a full
;        4+3r, col 9+3c; QTY digit (>= 2) |               bag -> BAG FULL, stays)
;        at row 5+3r, col 11+3c           |  directions  grid: the cursor (wrap rules
;  15    W A H C over the worn icons      |               below); strip: L / R the
;  16-17 WORN + 4 icons, cols 11+3k       |               next enabled verb (wraps),
;  18-19 icon (cols 0-1, IC1); row 19:  |               U / D back to the grid
;        item_name (+ " Xn") + stat line  |
;  20    verbs USE-word EQUIP REMOVE      |
;        DISCARD CLOSE (enabled bright    | Cursor rows: 0 [CLOSE], 1-4 bag rows,
;        cyan, disabled dim blue)         | 5 worn. U / D step the row and wrap
;  22    help / refusal (message row)     | (worn <-> [CLOSE]); L / R wrap inside
; Cursor = paper blue over the slot's     | the row (5 bag / 4 worn / 1 [CLOSE]);
; 3 x 2 cells (icon + count column),      | the column is remembered across rows
; [CLOSE]'s 6 cells, the chosen verb.     | (worn shows min(col, 3)). Opens on slot 0.
;==============================================================================
PG_A_BG         EQU $07             ; page body: white ink on black
PG_A_HEAD       EQU $46             ; title: bright yellow (menu font)
PG_A_ORN        EQU MENU_A_SUB      ; ornament rows: the menu's subtitle / ornament attr
PG_A_BOX        EQU $47             ; grid / worn band: empty frames + count digits
PG_A_VON        EQU $45             ; enabled verb, [CLOSE]: bright cyan
PG_A_VOFF       EQU $01             ; disabled verb: dim blue
PG_A_MSG        EQU $46             ; message row: bright yellow
PG_HI           EQU $08             ; the cursor: paper blue, by xor (every page attr has paper 0)
PG_ORN_TOP      EQU 2
PG_TXT_X        EQU 48              ; rows 0 / 1 counters, WORN label (pixel x)
PG_CLOSE_ROW    EQU 0
PG_CLOSE_COL    EQU 26
PG_CLOSE_W      EQU 6               ; "[CLOSE]" = 42 px
PG_GRID_ROW     EQU 4               ; 5 x 4 bag grid, 16x16 icons 3 cells apart
PG_GRID_COL     EQU 9               ; cols 9..23 (with the count column)
PG_WLAB_ROW     EQU 15
PG_WORN_ROW     EQU 16              ; 4 worn icons (rows 16..17), cols 11..21
PG_WORN_COL     EQU 11
PG_DESC_ROW     EQU 19
PG_DICON_ROW    EQU PG_DESC_ROW - 1     ; IC1: the description icon, cols 0-1, rows 18-19
PG_DESC_X       EQU 16
PG_NAME_MAX     EQU 26              ; + " X9" <= 29 chars from x 16; 3E-T8: real names <= 15, + it_fmt <= 14 (stacks: food / potions <= 11 + 3 + 8) <= 30; WEAR-UI gear lines <= 37 (test WU2) < PAGE_BUF_LEN 40
PG_VERB_ROW     EQU 20
PG_MSG_ROW      EQU 22              ; refusals / help (panel + log are hidden)
PG_ORN_BOT      EQU 23
PG_ROWS         EQU 6               ; cursor rows: [CLOSE], 4 bag rows, worn
PG_SL_CLOSE     EQU PG_SLOT_WORN + WORN_SLOTS   ; 24: the [CLOSE] button
; verb strip index (pg_vtab order) = enable bit
PG_V_USE        EQU 0               ; DRINK / EAT / READ (pg_use = VB_DRINK..VB_READ)
PG_V_EQUIP      EQU 1               ; -> VB_EQUIP
PG_V_REMOVE     EQU 2               ; -> VB_REMOVE
PG_V_DISCARD    EQU 3               ; -> VB_DISCARD
PG_V_CLOSE      EQU 4               ; -> close, VB_NONE (always enabled)
; pg_keys bits: STICK's JOY_* (0-4) | PLAYER_SC's ENTER / I / BREAK (5-7)
PG_K_CLOSE      EQU (1 << SC_INV_BIT) | (1 << SC_BREAK_BIT)
PG_K_FIRE       EQU (1 << JOY_F_BIT) | (1 << SC_ENTER_BIT)
                ASSERT JOY_MASK == $1F && SC_ENTER_BIT == 5 && SC_INV_BIT == 6 && SC_BREAK_BIT == 7
                ASSERT PG_V_EQUIP + VB_EQUIP - 1 == VB_EQUIP && PG_V_DISCARD + VB_EQUIP - 1 == VB_DISCARD
                ASSERT PG_V_REMOVE + VB_EQUIP - 1 == VB_REMOVE && VB_NONE == 0
                ASSERT VB_EAT == VB_DRINK + 1 && VB_READ == VB_EAT + 1
                ASSERT (BAG & $FF) == 0 && WORN == BAG + PG_SLOT_WORN * IR_STRIDE && IR_QTY == 1

page_main:
                xor  a
                ld   (PAGE_VERB), a            ; VB_NONE unless a verb is confirmed
                ld   hl, SCREEN_BITMAP         ; bitmap 0 (~0.13M T contended)
                ld   bc, SCREEN_BITMAP_LEN
                xor  a
                call .fill
                ld   hl, SCREEN_ATTR
                ld   bc, SCREEN_ATTR_LEN
                ld   a, PG_A_BG
                call .fill
                ; attr rects: attr, row, col, cols, rows ... 0
                ld   hl, pg_attrs
.at:            ld   a, (hl)
                or   a
                jr   z, .orn
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   c, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                call stamp_rect
                pop  hl
                jr   .at
.orn:           ld   b, PG_ORN_TOP
                call menu_orn_b
                ld   b, PG_ORN_BOT
                call menu_orn_b
                ; title (menu font, 2 rows)
                ld   hl, pg_title
                ld   bc, 2                     ; row 0, col 2
                ld   e, PG_A_HEAD
                ld   a, (hl)
                inc  hl
                push hl
                call mf_char
.ti:            pop  hl
                ld   a, (hl)
                inc  hl
                or   a
                jr   z, .tx0
                push hl
                call mf_char_e
                jr   .ti
                ; fixed 6x8 text: row, pixel x (a cell), ASCII, 0 ... $FF
.tx0:           ld   hl, pg_strs
.tx:            ld   b, (hl)
                inc  b
                jr   z, .cnt
                dec  b
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                call print6
                pop  hl
                xor  a
                ld   b, a
                ld   c, a
                cpir                           ; HL past the string's 0
                jr   .tx
                ; row 0: ITEMS n/20 (BAG is packed: the first free slot ends it)
.cnt:           ld   hl, BAG
                ld   bc, BAG_SLOTS << 8
.cn:            ld   a, (hl)
                or   a
                jr   z, .cd
                inc  c
                inc  l
                inc  l
                inc  l
                djnz .cn
.cd:            ld   a, c
                ld   (pg_n), a
                ld   de, PAGE_BUF
                ld   hl, pg_s_items
                call pg_cat
                ld   a, (pg_n)
                call pg_num
                ld   hl, pg_s_of
                call pg_cat
                ld   bc, (PG_CLOSE_ROW << 8) | PG_TXT_X
                call pg_out
                ; row 1: the counters outside the bag
                ld   de, PAGE_BUF
                ld   a, (HERO_KIND)
                or   a
                jr   nz, .nk                   ; Mage: no ammo (K_KNIGHT == 0)
                ld   hl, pg_s_dag
                call pg_cat
                ld   a, (DAGGERS)
                call pg_num
                ld   hl, pg_s_arr
                call pg_cat
                ld   a, (ARROWS)
                call pg_num
.nk:            ld   bc, ((PG_CLOSE_ROW + 1) << 8) | PG_TXT_X
                call pg_out
                ld   a, (LVL_FLAGS)
                and  LF_KEY_TAKEN
                jr   z, .nky
                ld   hl, pg_s_key              ; KEY under [CLOSE]
                ld   b, PG_CLOSE_ROW + 1
                ld   e, PG_CLOSE_COL * 8
                call print6
.nky:
                ; the 20 bag + 4 worn cells
                xor  a
.cl:            push af
                call pg_cell
                pop  af
                inc  a
                cp   PG_SL_CLOSE
                jr   c, .cl
                xor  a                         ; help line (no message up)
                ld   hl, pg_s_help
                call pg_say
                call pg_hl                     ; the cursor on slot 0
                call pg_info
                call show_bank5                ; the page is up
                call pg_keys
.loop:          ld   (pg_old), a
.wait:          call menu_frame
                call sample_input
                call pg_keys
                ld   hl, pg_old
                ld   c, a
                ld   a, (hl)
                ld   (hl), c
                cpl
                and  c                         ; pressed since the last frame
                jr   z, .wait
                ld   c, a
                ld   a, (pg_msgf)
                or   a
                jr   z, .nm
                push bc                        ; a refusal is up: back to the help
                xor  a
                ld   hl, pg_s_help
                call pg_say
                pop  bc
.nm:            ld   a, c
                and  PG_K_CLOSE
                ret  nz                        ; BREAK / I: close, VB_NONE
                ld   a, (pg_mode)
                or   a
                jr   nz, .verb
                ld   a, c
                and  PG_K_FIRE
                jr   nz, .fire
                call pg_move
                jr   .wait
                ; grid FIRE: [CLOSE] closes; an item opens the verb strip
.fire:          call pg_cur
                cp   PG_SL_CLOSE
                ret  z
                ld   a, (pg_en)
                and  ~(1 << PG_V_CLOSE) & $FF
                jr   z, .wait                  ; empty slot: nothing to do
                ld   b, $FF
.fb:            inc  b
                rrca
                jr   nc, .fb                   ; B = the first enabled verb
                ld   a, b
                ld   (pg_vsel), a
                ld   a, 1
                ld   (pg_mode), a
                call pg_vtog
                jr   .wait
                ; the verb strip
.verb:          ld   a, c
                and  PG_K_FIRE
                jr   nz, .conf
                ld   a, c
                and  (1 << JOY_U_BIT) | (1 << JOY_D_BIT)
                jr   nz, .back
                ld   a, c
                and  (1 << JOY_L_BIT) | (1 << JOY_R_BIT)
                jr   z, .wait
                push bc
                call pg_vtog                   ; off
                pop  bc
                ld   a, (pg_vsel)
.vs:            bit  JOY_R_BIT, c
                jr   z, .vl
                inc  a
                cp   PG_V_CLOSE + 1
                jr   c, .vt
                xor  a
                jr   .vt
.vl:            dec  a
                jp   p, .vt
                ld   a, PG_V_CLOSE
.vt:            ld   e, a
                ld   b, a
                inc  b
                ld   a, (pg_en)
.vb:            rrca
                djnz .vb                       ; CF = verb E's enable bit
                ld   a, e
                jr   nc, .vs                   ; disabled: step on (CLOSE always ends it)
                ld   (pg_vsel), a
                call pg_vtog
                jp   .wait
.back:          call pg_vtog
                xor  a
                ld   (pg_mode), a
                jp   .wait
.conf:          ld   a, (pg_vsel)
                cp   PG_V_CLOSE
                ret  z                         ; CLOSE: no verb
                ld   b, a
                call pg_cur
                ld   c, a                      ; C = slot
                ld   a, b
                cp   PG_V_REMOVE
                jr   nz, .ok
                ld   a, (pg_n)
                cp   BAG_SLOTS
                jr   c, .ok
                ld   hl, it_stems + S3_BAG_FULL   ; bank-1 resident stem: refused, stay
                ld   a, 1
                call pg_say
                jp   .wait
.ok:            ld   a, c
                ld   (PAGE_SLOT), a
                ld   a, b
                or   a
                ld   a, (pg_use)               ; USE word = VB_DRINK / VB_EAT / VB_READ
                jr   z, .vset
                ld   a, b
                add  a, VB_EQUIP - 1
.vset:          ld   (PAGE_VERB), a
                ret
; .fill — BC bytes (>= 2) at HL = A.  Clobbers: BC, DE, HL
.fill:          ld   (hl), a
                ld   d, h
                ld   e, l
                inc  de
                dec  bc
                ldir
                ret

;------------------------------------------------------------------------------
; pg_keys — A = the page keys held now (STICK JOY_* | ENTER / I / BREAK).
; Clobbers: A, B
;------------------------------------------------------------------------------
pg_keys:        ld   a, (STICK)
                and  JOY_MASK
                ld   b, a
                ld   a, (PLAYER_SC)
                and  PG_K_CLOSE | (1 << SC_ENTER_BIT)
                or   b
                ret

;------------------------------------------------------------------------------
; pg_move — the grid cursor by the new presses in C (rules in the header).
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
pg_move:        ld   a, c
                and  JOY_DIRS
                ret  z
                push bc
                call pg_hl                     ; off
                pop  bc
                ld   hl, (pg_rc)               ; L = row, H = remembered col
                ld   a, c
                and  (1 << JOY_U_BIT) | (1 << JOY_D_BIT)
                jr   z, .h
                ld   a, l
                bit  JOY_D_BIT, c
                jr   z, .up
                inc  a
                cp   PG_ROWS
                jr   c, .v
                xor  a
                jr   .v
.up:            dec  a
                jp   p, .v
                ld   a, PG_ROWS - 1
.v:             ld   l, a
                jr   .set
.h:             push hl
                ld   a, l
                ld   hl, pg_wid
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   e, (hl)                   ; E = the row's width
                pop  hl
                ld   a, h
                cp   e
                jr   c, .in
                ld   a, e
                dec  a                         ; clamp the remembered col (worn: 3)
.in:            bit  JOY_R_BIT, c
                jr   z, .lf
                inc  a
                cp   e
                jr   c, .hs
                xor  a
                jr   .hs
.lf:            dec  a
                jp   p, .hs
                ld   a, e
                dec  a
.hs:            ld   h, a
.set:           ld   (pg_rc), hl
                call pg_hl                     ; on
                ; fall through
;------------------------------------------------------------------------------
; pg_info — the cursor slot's description (row 19; IC1: its icon at cols 0-1,
; rows 18-19: the item, an empty worn slot's placeholder, blank for [CLOSE] /
; an empty bag slot), verb enables + USE word (pg_en / pg_use) and the verb
; strip (row 20).  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
pg_info:        ld   b, PG_DESC_ROW
                call row_clear
                call pg_cur                    ; A = slot (PG_SL_CLOSE: icon_slot clears)
                ld   de, (PG_DICON_ROW << 8) | 0
                ld   hl, icon_slot             ; R6 (icons6.asm)
                call far6
                call pg_cur                    ; A = slot, HL = its record
                ld   bc, 1 << PG_V_CLOSE       ; B = USE word 0 ("USE"), C = enables
                cp   PG_SL_CLOSE
                jr   z, .set                   ; [CLOSE]: no description
                ld   d, a
                ld   a, (hl)
                or   a
                jr   nz, .it
                ld   hl, pg_s_empty
                push bc
                ld   b, PG_DESC_ROW
                ld   e, PG_DESC_X
                call print6
                pop  bc
                jr   .set
.it:            ld   e, a                      ; E = type
                ld   a, d
                cp   PG_SLOT_WORN
                jr   c, .bag
                set  PG_V_REMOVE, c            ; worn: REMOVE only (never DISCARD)
                jr   .nm
.bag:           set  PG_V_DISCARD, c
                ld   a, e
                cp   IT_BOW
                jr   z, .nm                    ; the bow: DISCARD only
                jr   c, .use
                set  PG_V_EQUIP, c             ; gear
                jr   .nm
.use:           set  PG_V_USE, c
                ld   b, VB_DRINK
                cp   IT_POT_LO
                jr   c, .eat                   ; food
                cp   IT_SCR_LO
                jr   c, .nm                    ; potion
                inc  b                         ; scroll / book: READ
.eat:           inc  b
.nm:            push bc
                push de                        ; D = the slot
                push hl
                ld   a, e
                ld   de, PAGE_BUF
                ld   h, PG_NAME_MAX
                ld   c, 0
                call item_name                 ; DE past the name
                pop  hl
                inc  l
                ld   a, (hl)                   ; QTY
                cp   2
                jr   c, .one
                ld   hl, pg_s_x
                push af
                call pg_cat
                pop  af
                call pg_num
.one:           pop  af                        ; A = the slot
                ld   hl, it_fmt                ; 3E-T8: the stat line (R6, gear6.asm)
                call far6                      ; DE past it
                ld   bc, (PG_DESC_ROW << 8) | PG_DESC_X
                call pg_out
                pop  bc
.set:           ld   a, c
                ld   (pg_en), a
                ld   a, b
                ld   (pg_use), a
                add  a, a
                ld   c, a
                add  a, a
                add  a, c                      ; * 6
                ld   e, a
                ld   d, 0
                ld   hl, pg_uw
                add  hl, de
                ld   b, PG_VERB_ROW
                ld   e, PG_VC0 * 8
                call print6                    ; the USE word (5 chars: clears the old one)
                ld   hl, pg_vtab
                ld   a, (pg_en)
.va:            ld   c, (hl)                   ; col (0 = end)
                inc  c
                dec  c
                ret  z
                inc  hl
                ld   d, (hl)                   ; cols
                inc  hl
                rrca                           ; CF = this verb's enable
                push af
                push hl
                ld   a, PG_A_VON
                jr   c, .von
                ld   a, PG_A_VOFF
.von:           ld   b, PG_VERB_ROW
                ld   e, 1
                call stamp_rect
                pop  hl
                pop  af
                jr   .va

;------------------------------------------------------------------------------
; pg_cur — A = the cursor slot (0..19 bag, 20..23 worn, PG_SL_CLOSE), HL = its
; record BAG + 3 * slot (meaningless for PG_SL_CLOSE).  Clobbers: F
;------------------------------------------------------------------------------
pg_cur:         ld   hl, (pg_rc)               ; L = row, H = col
                ld   a, l
                or   a
                ld   a, PG_SL_CLOSE
                ret  z
                ld   a, l
                cp   PG_ROWS - 1
                ld   a, h
                jr   nz, .bag
                cp   WORN_SLOTS
                jr   c, .w
                ld   a, WORN_SLOTS - 1
.w:             add  a, PG_SLOT_WORN
                jr   .rec
.bag:           dec  l
                jr   z, .rec
                add  a, 5
                jr   .bag
.rec:           ld   h, a
                add  a, a
                add  a, h
                ld   l, a
                ld   a, h
                ld   h, HIGH BAG
                ret

;------------------------------------------------------------------------------
; pg_hl — toggle the cursor over the current slot.  Clobbers: A, BC, DE, HL
; pg_vtog — toggle the cursor over verb pg_vsel.  Clobbers: A, BC, DE, HL
; pg_tog — xor PG_HI over the attr rect: B = row, C = col, D = cols, E = rows.
;          Clobbers: A, B, E, HL (C, D kept)
;------------------------------------------------------------------------------
pg_hl:          call pg_cur
                call pg_rect
                jr   pg_tog
pg_vtog:        ld   a, (pg_vsel)
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, pg_vtab
                add  hl, de
                ld   c, (hl)
                inc  hl
                ld   d, (hl)
                ld   b, PG_VERB_ROW
                ld   e, 1
pg_tog:         push de
                call mattr                     ; DE = attr of (B, C)
                ex   de, hl
                pop  de
                push de
.c:             ld   a, (hl)
                xor  PG_HI
                ld   (hl), a
                inc  l
                dec  d
                jr   nz, .c
                pop  de
                inc  b
                dec  e
                jr   nz, pg_tog
                ret

;------------------------------------------------------------------------------
; pg_rect — A = slot: B = row, C = col of its rect, D = cols, E = rows (bag /
; worn: the 2x2 icon + the count column; PG_SL_CLOSE: the [CLOSE] text).
; Clobbers: A, H, F
;------------------------------------------------------------------------------
pg_rect:        ld   de, (3 << 8) | 2
                cp   PG_SL_CLOSE
                jr   nz, .n
                ld   bc, (PG_CLOSE_ROW << 8) | PG_CLOSE_COL
                ld   de, (PG_CLOSE_W << 8) | 1
                ret
.n:             ld   bc, (PG_WORN_ROW << 8) | PG_WORN_COL
                sub  PG_SLOT_WORN
                jr   nc, .c
                add  a, PG_SLOT_WORN
                ld   bc, (PG_GRID_ROW << 8) | PG_GRID_COL
.r:             cp   5
                jr   c, .c
                sub  5
                inc  b
                inc  b
                inc  b
                jr   .r
.c:             ld   h, a
                add  a, a
                add  a, h
                add  a, c
                ld   c, a
                ret

;------------------------------------------------------------------------------
; pg_cell — draw slot A (0..23): an empty bag slot = a 16x16 frame; else (IC1)
; its 16x16 icon in its ink — an empty worn slot its placeholder — (R6
; icon_slot) + the QTY digit (stacks >= 2) right of it.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
pg_cell:        push af
                call pg_rect                   ; B, C
                pop  af
                push bc
                push af
                ld   d, b
                ld   e, c
                ld   hl, icon_slot             ; R6 (icons6.asm); L = 0: cleared
                call far6
                pop  af
                pop  bc
                inc  l
                dec  l
                jr   z, pg_box                 ; an empty bag slot
                ld   h, a
                add  a, a
                add  a, h
                inc  a                         ; + IR_QTY
                ld   l, a
                ld   h, HIGH BAG
                ld   a, (hl)                   ; QTY (an empty worn slot: 0)
                cp   2
                ret  c
                add  a, '0'
                ld   de, PAGE_BUF
                ld   (de), a
                inc  de
                inc  b                         ; the icon's lower row
                ld   a, c
                add  a, 2                      ; the count column
                add  a, a
                add  a, a
                add  a, a
                ld   c, a                      ; pixel x
                ; fall through
;------------------------------------------------------------------------------
; pg_out — print PAGE_BUF..DE (0 written at DE) at row B, pixel x C.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
pg_out:         xor  a
                ld   (de), a
                ld   e, c
                ld   hl, PAGE_BUF
                jp   print6

;------------------------------------------------------------------------------
; pg_box — a 16x16 outline over the 2 x 2 cells at row B, col C (bitmap only;
; the cells start clear). Keeps BC, DE.  Clobbers: A, HL
;------------------------------------------------------------------------------
pg_box:         push de
                push bc
                call mcell                     ; DE = line 0 of (B, C)
                call .edge
                call .side
                inc  b
                call mcell
                call .side                     ; D ends one line past the cell
                dec  d
                call .edge
                pop  bc
                pop  de
                ret
.edge:          ld   a, $FF
                ld   (de), a
                inc  e
                ld   (de), a
                dec  e
                ret
.side:          ld   h, 8
.s:             ld   a, (de)
                or   $80
                ld   (de), a
                inc  e
                ld   a, (de)
                or   $01
                ld   (de), a
                dec  e
                inc  d
                dec  h
                jr   nz, .s
                ret

;------------------------------------------------------------------------------
; pg_say — A = pg_msgf (1 = a refusal: the next press restores the help),
; HL = text: row 22 cleared, then the text at x 16.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
pg_say:         ld   (pg_msgf), a
                push hl
                ld   b, PG_MSG_ROW
                call row_clear
                pop  hl
                ld   e, PG_DESC_X
                jp   print6

;------------------------------------------------------------------------------
; pg_cat — copy the 0-terminated HL to DE (no 0), DE advanced. Clobbers: A, HL
; pg_num — A = 0..99 as 1-2 digits at DE, DE advanced.  Clobbers: A, BC
;------------------------------------------------------------------------------
pg_cat:         ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  hl
                inc  de
                jr   pg_cat
pg_num:         ld   b, '0' - 1
.t:             inc  b
                sub  10
                jr   nc, .t
                add  a, '0' + 10
                ld   c, a
                ld   a, b
                cp   '0'
                jr   z, .u
                ld   (de), a
                inc  de
.u:             ld   a, c
                ld   (de), a
                inc  de
                ret

;------------------------------------------------------------------------------
; data (unpacked fresh on every open: the variables start at these values)
;------------------------------------------------------------------------------
pg_rc:          DB   1, 0                      ; cursor row (1 = bag row 0), remembered col
pg_mode:        DB   0                         ; 0 grid, 1 verb strip
pg_vsel:        DB   0                         ; the chosen verb (strip index)
pg_en:          DB   0                         ; enabled verbs of the cursor slot (bit = index)
pg_use:         DB   0                         ; its USE word: 0 "USE" or VB_DRINK..VB_READ
pg_old:         DB   0                         ; keys held last frame
pg_msgf:        DB   0                         ; 1 = a refusal on row 22
pg_n:           DB   0                         ; used bag slots
pg_wid:         DB   1, 5, 5, 5, 5, WORN_SLOTS ; cursor row widths
; verb strip: col, cols per verb (strip index order), 0
PG_VC0          EQU 2
pg_vtab:        DB   PG_VC0, 4, 7, 4, 12, 5, 18, 6, 25, 4, 0
; USE words, 6 B each (5 chars: a shorter word clears the longer one's cells)
pg_uw:          DB   "USE  ", 0, "DRINK", 0, "EAT  ", 0, "READ ", 0
; attr rects over PG_A_BG: attr, row, col, cols, rows ... 0
pg_attrs:       DB   PG_A_ORN, PG_ORN_TOP, 0, 32, 1
                DB   PG_A_BOX, PG_GRID_ROW, 0, 32, 11
                DB   PG_A_BOX, PG_WORN_ROW, 0, 32, 2
                DB   PG_A_MSG, PG_MSG_ROW, 0, 32, 1
                DB   PG_A_ORN, PG_ORN_BOT, 0, 32, 1
                DB   PG_A_VON, PG_CLOSE_ROW, PG_CLOSE_COL, PG_CLOSE_W, 1
                DB   0
                ASSERT PG_A_ORN != 0 && PG_A_BOX != 0 && PG_A_VON != 0 && PG_A_MSG != 0
pg_title:       DB   "BAG", 0
; text: row, pixel x (a cell), ASCII, 0 ... $FF
pg_strs:        DB   PG_CLOSE_ROW, PG_CLOSE_COL * 8, "[CLOSE]", 0
                DB   PG_WORN_ROW, PG_TXT_X, "WORN", 0
                DB   PG_WLAB_ROW, (PG_WORN_COL + 0) * 8, "W", 0
                DB   PG_WLAB_ROW, (PG_WORN_COL + 3) * 8, "A", 0
                DB   PG_WLAB_ROW, (PG_WORN_COL + 6) * 8, "H", 0
                DB   PG_WLAB_ROW, (PG_WORN_COL + 9) * 8, "C", 0
                DB   PG_VERB_ROW, 7 * 8, "EQUIP", 0
                DB   PG_VERB_ROW, 12 * 8, "REMOVE", 0
                DB   PG_VERB_ROW, 18 * 8, "DISCARD", 0
                DB   PG_VERB_ROW, 25 * 8, "CLOSE", 0
                DB   $FF
pg_s_items:     DB   "ITEMS ", 0
pg_s_of:        DB   "/20", 0
pg_s_dag:       DB   "DAGGERS ", 0
pg_s_arr:       DB   "  ARROWS ", 0
pg_s_key:       DB   "KEY", 0
pg_s_x:         DB   " X", 0
pg_s_empty:     DB   "EMPTY", 0
pg_s_help:      DB   "FIRE: SELECT   I: CLOSE", 0
                ASSERT BAG_SLOTS == 20 && PAGE_SCR_END <= TX_DEC
