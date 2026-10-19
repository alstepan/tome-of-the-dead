;==============================================================================
; page_ovl.asm — 3E-T2 bag page overlay (SPIKE: an EMPTY page, placeholder
; text only; game.md §8 / §3.1, Q3 layout still open). Assembled at PAGE_ORG
; (main.asm "OVERLAYS"), stored ZX0-packed in bank 1 (ovl_page_zx0), run by
; ovl_run from page_ovl (bank 1) with BANK_UI1 paged, so it calls the bank-1
; menu helpers (mcell, row 0 .. 15 only) and the bank-2 / low-RAM ones
; (print6, stamp_rect, menu_frame, sample_input, show_bank5) directly.
; Contract (docs/memory-map.md "Overlays", the page window): the caller
; (page_run) has made screen 2 the composed screen (present_full) and shows
; it; this code lives in the bank-5 bitmap of char rows PAGE_BAND_ROW..23,
; which it blacks out first (attr 0) and never draws over; it draws the page
; in rows 0..PAGE_BAND_ROW-1 of the bank-5 screen, shows bank 5, and returns
; on a NEW press of FIRE, BREAK, ENTER or I (keys held at open are ignored
; until released). Out: nothing (the caller restores the screen from screen
; 2). Clobbers: A, BC, DE, HL (IX, IY kept).
; Cost (measured, tests/page.py): see docs/memory-map.md.
;==============================================================================
PG_A_BG         EQU $07             ; page body: white ink on black
PG_A_HEAD       EQU $46             ; header row: bright yellow
PG_A_VERB       EQU $45             ; verb row: bright cyan
PG_GRID_ROW     EQU 2               ; 5 x 4 bag grid, 16x16 boxes 3 cells apart
PG_GRID_COL     EQU 1
PG_WORN_ROW     EQU 13              ; 4 worn boxes (rows 13..14)
PG_WORN_COL     EQU 6
PG_VERB_ROW     EQU 15
PG_KEYS         EQU (1 << SC_ENTER_BIT) | (1 << SC_INV_BIT) | (1 << SC_BREAK_BIT)
                ASSERT JOY_F_BIT == 4 && (PG_KEYS & (1 << JOY_F_BIT)) == 0 && (PG_KEYS & SC_SLOT_MASK) == 0
                ASSERT PG_VERB_ROW < PAGE_BAND_ROW

page_main:
                ; the band first: black, so the code under it never shows
                ld   hl, SCREEN_ATTR + PAGE_BAND_ROW * 32
                ld   bc, (24 - PAGE_BAND_ROW) * 32
                xor  a
                call .fill
                ld   hl, SCREEN_BITMAP         ; rows 0 .. band-1: bitmap 0 (one LDIR-
                ld   bc, PAGE_BAND_ROW * 256   ; sized fill, ~86k T)
                call .fill                     ; (A = 0)
                ld   hl, SCREEN_ATTR
                ld   bc, PAGE_BAND_ROW * 32
                ld   a, PG_A_BG
                call .fill
                ld   a, PG_A_HEAD
                ld   bc, 0
                ld   de, (32 << 8) | 1
                call stamp_rect
                ld   a, PG_A_VERB
                ld   bc, PG_VERB_ROW << 8
                ld   de, (32 << 8) | 1
                call stamp_rect
                ; text (raw ASCII, print6: 6x8, x on a cell)
                ld   hl, pg_strs
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
.gc:            call pg_box
                inc  c
                inc  c
                inc  c
                dec  d
                jr   nz, .gc
                pop  bc
                inc  b
                inc  b
                inc  b
                dec  e
                jr   nz, .gr
                ld   bc, (PG_WORN_ROW << 8) | PG_WORN_COL
                ld   d, 4
.gw:            call pg_box
                inc  c
                inc  c
                inc  c
                dec  d
                jr   nz, .gw
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

; text: row, pixel x, ASCII, 0 ... $FF (placeholders until Q3 / T13-T14)
pg_strs:        DB   0, 8, "BAG  0/20", 0
                DB   0, 136, "PAGE PLACEHOLDER", 0
                DB   PG_GRID_ROW, 136, "(EMPTY)", 0
                DB   PG_WORN_ROW, 8, "WORN", 0
                DB   PG_VERB_ROW, 8, "USE  EQUIP  DROP  QUICK   FIRE: BACK", 0
                DB   $FF
