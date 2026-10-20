;==============================================================================
; page_ovl.asm — 3E-T2 bag page overlay (SPIKE: an EMPTY page, placeholder
; text only; game.md §8 / §3.1, Q3 layout still open). Assembled at PAGE_ORG
; = GEN_SCRATCH (main.asm "OVERLAYS"), stored ZX0-packed in bank 1
; (ovl_page_zx0), run by ovl_run from page_ovl (bank 1) with BANK_UI1 paged,
; so it calls the bank-1 menu helpers (mcell, mf_char, menu_orn_b) and the
; bank-2 / low-RAM ones (print6, stamp_rect, menu_frame, sample_input,
; show_bank5) directly.
; Contract (docs/memory-map.md "Overlays", the page window): the caller
; (page_run) has made screen 2 the composed screen (present_full) and shows
; it, and page_ovl has saved ROOM_MAP; this code draws the page over all 24
; rows of the bank-5 screen, shows bank 5, and returns on a NEW press of FIRE,
; BREAK, ENTER or I (keys held at open are ignored until released). Music and
; effects play on (no SND_HOLD). Out: nothing (the caller restores the screen
; from screen 2 and the room map). Clobbers: A, BC, DE, HL (IX, IY kept).
; Layout (rows): 0-1 header (menu font) + counts, 2 ornament, 4-14 the 5 x 4
; grid of 16x16 boxes (cols 9..22, centred), 16-17 WORN (4 boxes, centred),
; 19 description, 20 verbs, 22 the page's message row, 23 ornament.
;==============================================================================
PG_A_BG         EQU $07             ; page body: white ink on black
PG_A_HEAD       EQU $46             ; title: bright yellow (menu font)
PG_A_ORN        EQU MENU_A_SUB      ; ornament rows: the menu's subtitle / ornament attr
PG_A_BOX        EQU $47             ; grid / worn boxes: bright white
PG_A_VERB       EQU $45             ; verb row: bright cyan
PG_A_MSG        EQU $46             ; message row: bright yellow
PG_ORN_TOP      EQU 2
PG_GRID_ROW     EQU 4               ; 5 x 4 bag grid, 16x16 boxes 3 cells apart
PG_GRID_COL     EQU 9               ; cols 9..22 (centred: 14 wide)
PG_WORN_ROW     EQU 16              ; 4 worn boxes (rows 16..17), cols 11..21 (centred)
PG_WORN_COL     EQU 11
PG_DESC_ROW     EQU 19
PG_VERB_ROW     EQU 20
PG_MSG_ROW      EQU 22              ; T13: refusals / prompts (panel + log are hidden)
PG_ORN_BOT      EQU 23
PG_KEYS         EQU (1 << SC_ENTER_BIT) | (1 << SC_INV_BIT) | (1 << SC_BREAK_BIT)
                ASSERT JOY_F_BIT == 4 && (PG_KEYS & (1 << JOY_F_BIT)) == 0 && (PG_KEYS & SC_SLOT_MASK) == 0

page_main:
                ld   hl, SCREEN_BITMAP         ; bitmap 0 (~0.13M T contended)
                ld   bc, SCREEN_BITMAP_LEN
                xor  a
                call .fill
                ld   hl, SCREEN_ATTR
                ld   bc, SCREEN_ATTR_LEN
                ld   a, PG_A_BG
                call .fill
                ; attr bands: (attr, row, rows) ... 0
                ld   hl, pg_attrs
.at:            ld   a, (hl)
                or   a
                jr   z, .orn
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                ld   c, 0
                ld   d, 32
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
                ; 6x8 text (raw ASCII, print6, x on a cell)
.tx0:           ld   hl, pg_strs
.tx:            ld   b, (hl)                   ; row ($FF = end)
                inc  b
                jr   z, .grid
                dec  b
                inc  hl
                ld   e, (hl)                   ; pixel x
                inc  hl
                push hl
                call print6
                pop  hl
                xor  a
                ld   b, a
                ld   c, a
                cpir                           ; HL past the string's 0
                jr   .tx
                ; the 5 x 4 grid, then the 4 worn slots
.grid:          ld   bc, (PG_GRID_ROW << 8) | PG_GRID_COL
                ld   e, 4                      ; rows
.gr:            push bc
                ld   d, 5
                call pg_boxes
                pop  bc
                inc  b
                inc  b
                inc  b
                dec  e
                jr   nz, .gr
                ld   bc, (PG_WORN_ROW << 8) | PG_WORN_COL
                ld   d, 4
                call pg_boxes
                call show_bank5                ; the page is up
                ; keys: close on a new press only
                call .keys
.loop:          ld   (menu_sc_old), a
                call menu_frame
                call sample_input
                call .keys
                ld   hl, menu_sc_old
                ld   c, a
                ld   a, (hl)
                cpl
                and  c                         ; pressed since the last frame
                ld   a, c
                jr   z, .loop
                ret
; .keys — A = the close keys held now (PG_KEYS of PLAYER_SC + FIRE).
.keys:          ld   a, (STICK)
                and  1 << JOY_F_BIT
                ld   b, a
                ld   a, (PLAYER_SC)
                and  PG_KEYS
                or   b
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
; pg_boxes — D boxes from row B, col C, 3 cols apart. Keeps B, E.
; Clobbers: A, C, D, HL
;------------------------------------------------------------------------------
pg_boxes:       call pg_box
                inc  c
                inc  c
                inc  c
                dec  d
                jr   nz, pg_boxes
                ret

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

; attr bands over PG_A_BG: attr, row, rows ... 0
pg_attrs:       DB   PG_A_ORN, PG_ORN_TOP, 1
                DB   PG_A_BOX, PG_GRID_ROW, 11
                DB   PG_A_BOX, PG_WORN_ROW, 2
                DB   PG_A_VERB, PG_VERB_ROW, 1
                DB   PG_A_MSG, PG_MSG_ROW, 1
                DB   PG_A_ORN, PG_ORN_BOT, 1
                DB   0
                ASSERT PG_A_ORN != 0 && PG_A_BOX != 0 && PG_A_VERB != 0 && PG_A_MSG != 0
pg_title:       DB   "BAG", 0
; text: row, pixel x, ASCII, 0 ... $FF (placeholders until Q3 / T13-T14)
pg_strs:        DB   1, 168, "ITEMS 0/20", 0
                DB   PG_WORN_ROW, 48, "WORN", 0
                DB   PG_DESC_ROW, 16, "(EMPTY SLOT)", 0
                DB   PG_VERB_ROW, 16, "USE   EQUIP   REMOVE   DISCARD", 0
                DB   PG_MSG_ROW, 176, "FIRE: BACK", 0
                DB   $FF
