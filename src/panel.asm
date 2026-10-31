;==============================================================================
; PANEL ENGINE (B3B-11) — rows 18..23 (concept-screen §5, game.md §3.3–3.5).
; INCLUDEd at the end of bank3.asm. Two parts:
;   1. bank-3 cold code (entered by far3): panel_init (new game: static
;      panel art + state), panel_flush, their helpers. MEM-SND: panel_boot
;      (boot: FONT6 planes + the hot image -> bank-2 runtime RAM) and
;      panel_init7 (panel_init's bank-2-only half) are bank 7 (boot7.asm).
;   2. (B3B-11b) the new-game cold DATA — the panel icons — is NOT here:
;      main.asm `vdata` puts it in bank 1 after the ZX0 sprite sources;
;      bank-3 code reads it only through copy_virt3 (lowram), into GEN_SRC.
;      3E-T1: the boot-only data (font6x8, the hot image panel_hot.asm:
;      print6, log_push, panel_tick, item_hp) is in the boot block (boot6.asm).
; D5 (user 2026-10-03): panel changes are queued (PANEL_DIRTY bits + the
; LOG_Q message ring) and drained ONE item per tick by panel_tick, never in a
; turn's input tick (play_loop), <= ~3 ticks latency. Logic never reads the
; panel. All drawing goes into the bank-5 screen; present copies it (HUD4_PW
; for the log rows, pmark_rect for the rest).
;==============================================================================

; panel_boot: bank 7 since MEM-SND, the boot block since 3E-T1 (boot6.asm boot6_tiles).

;------------------------------------------------------------------------------
; panel_init — new game / level (far3 from level_show): the static panel of HERO_KIND
; (icon bar, labels, bar frames, placeholders, gear outlines, attrs) on rows
; 18..23 of bank 5 — the rows must be blank (start_game's clear_screen) —
; panel state reset (the *_SH "as drawn" bytes: $FF = never drawn; STAT_SH
; 0 = both status cells blank, as drawn here), then string E (TX_*, TX_NONE = none; B3B-13: was a
; pointer in DE) pushed to the log and everything
; queued drawn at once (panel_flush). The caller presents (present_full).
; Placeholders until 3C/3E: (3E-T9: FOOD is item_food's now) no ammo, no
; info line, empty gear outlines; quick slots outlined except the potion slot
; (T_POTION glyph + count, the PROTO "POT n").  Clobbers: all but IX, IY.
; MEM-SND: the bank-2-only half (state reset, attr stamps, potion-slot scan)
; is panel_init7 in bank 7 (boot7.asm); the stamped rects are disjoint from
; the label / gear cells drawn here, so stamping them first changes nothing.
;------------------------------------------------------------------------------
panel_init:
                push de
                ld   hl, panel_init7           ; MEM-SND: the state reset, every attr
                call far7                      ; stamp (boot7.asm; +~0.3k T once per level)
                ; row 21: labels (glyph8 / pblit: bank-3 SMC + vdata via GEN_SRC)
                ld   hl, label_heart
                ld   bc, (STAT_ROW << 8) | HP_LBL_COL
                call glyph8
                ld   hl, label_drop
                ld   bc, (STAT_ROW << 8) | MP_LBL_COL
                call glyph8
                ld   hl, label_drumstick
                ld   bc, (STAT_ROW << 8) | FOOD_LBL_COL
                call glyph8
                                               ; (D3-9b: the MP bar is item_mp's, PD_MP set;
                                               ; 3E-T9: the FOOD bar + word item_food's, PD_FOOD)
                ; rows 22-23: the worn cells (IC1: worn item icons / slot placeholders,
                ; R6 icons6.asm; the log attrs: panel_init7)
                ld   hl, worn_draw
                call far6
                pop  hl                        ; L = the first message (TX_*)
                ld   a, l
                cp   TX_NONE
                call nz, msg_push              ; (lowram: re-pages bank 3)
                ; fall through
;------------------------------------------------------------------------------
; panel_flush — drain the whole queue now, whole log lines (cold: new game).
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
panel_flush:
                ld   c, 0                      ; any item, whole log lines
                call panel_step
                ld   a, (PANEL_DIRTY)
                or   a
                jr   nz, panel_flush
                ret

;------------------------------------------------------------------------------
; pblit — opaque cell block: HL = VIRTUAL source (vdata: D*8 pixel lines x E
; bytes, row-major, then D*E attrs; first copied to GEN_SRC by copy_virt3),
; B = top char row, C = col, D = char rows, E = width (cells), D*E <= 6.
; Clobbers: A, BC, DE, HL.   (cold: panel_init only)
; SMC: .w+1 / .wa+1 = width (LDIR counts), .ra+1 = rows (attr pass).
;------------------------------------------------------------------------------
pblit:
                push bc
                push de
                xor  a
.m:             add  a, e
                dec  d
                jr   nz, .m                    ; A = cells
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c                      ; 9 B per cell (8 lines + attr)
                ld   c, a
                ld   b, 0
                ld   de, GEN_SRC
                call copy_virt3
                ld   hl, GEN_SRC
                pop  de
                pop  bc
                ld   a, e
                ld   (.w+1), a
                ld   (.wa+1), a
                ld   a, d
                ld   (.ra+1), a
                push bc
.crow:          push de                        ; D = char rows left
                push hl
                call cell_bm                   ; HL = bitmap line 0 of (B, C)
                ex   de, hl
                pop  hl
                ld   a, 8
.line:          push bc
                push de
.w:             ld   bc, 0                     ; SMC: width
                ldir
                pop  de
                pop  bc
                inc  d
                dec  a
                jr   nz, .line
                pop  de
                inc  b
                dec  d
                jr   nz, .crow
                pop  bc                        ; top-left again
.ra:            ld   a, 0                      ; SMC: rows
.arow:          push af
                push hl
                call attr_addr                 ; HL = attr (B, C)
                ex   de, hl
                pop  hl
                push bc
.wa:            ld   bc, 0                     ; SMC: width
                ldir
                pop  bc
                inc  b
                pop  af
                dec  a
                jr   nz, .arow
                ret

; glyph8 — HL = 8x8 label (8 B + attr, ICON8_LEN) at cell (B, C).  Clobbers: A, BC, DE, HL
glyph8:
                ld   de, (1 << 8) | 1
                jr   pblit
                ASSERT ICON8_LEN == 9

; cell_bm — HL = bank-5 bitmap line 0 of cell (row B, col C).  Clobbers: A (BC, DE kept)
cell_bm:
                call attr_addr
                ld   a, h
                and  3
                rlca
                rlca
                rlca
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ret

;------------------------------------------------------------------------------
; slot_redraw — far3 from item_icons: A = slot, E = its state (IS_* | IS_SEL).
; Draws the slot's 3 x 2 cells from scratch: an outline (IS_HIDDEN or no icon
; art), a quick FOOD / POTION / SCROLL slot (IC1: R6 qs_draw — the pick's
; 16x16 icon in its ink + the count of that type) or the bar icon (pblit, its
; own attrs); IS_GREY -> all 6 attrs ATTR_P_GREY; IS_SEL -> PAPER blue
; (sel_paint, which marks).
; Clobbers: all but IX, IY.   ~3k T (pblit through GEN_SRC); quick ~6-11k T
;------------------------------------------------------------------------------
slot_redraw:
                ld   b, a
                push de                        ; E = state
                push bc                        ; B = slot
                ld   a, b
                add  a, a
                add  a, b
                ld   c, a                      ; C = col
                ld   hl, bar_knight
                ld   a, (HERO_KIND)
                or   a
                jr   z, .k
                ld   hl, bar_wizard
.k:             ld   a, b
                add  a, l
                ld   l, a
                jr   nc, .k2
                inc  h
.k2:            ld   a, e
                and  3
                ld   a, (hl)                   ; A = icon id / SLOT_*
                jr   z, .out                   ; IS_HIDDEN
                cp   SLOT_EMPTY
                jr   z, .out
                cp   SLOT_QFOOD
                jr   nc, .quick
                ld   hl, icon_tab              ; icon_tab + id * ICON_LEN (cold)
                ld   de, ICON_LEN
                or   a
                jr   z, .blit
                ld   b, a
.mul:           add  hl, de
                djnz .mul
                jr   .blit
.out:           ld   hl, icon_empty24
.blit:          ld   b, ICON_ROW
                ld   de, (2 << 8) | ICON_W
                push bc
                call pblit
                pop  bc
                jr   .attrs
.quick:         sub  SLOT_QFOOD                ; A = QS_* (IC1)
                ld   d, a                      ; D = class, E = state
                push de
                ld   b, ICON_ROW               ; blank 3 x 2: bitmap, attrs 0
                call .clr
                ld   b, ICON_ROW + 1
                call .clr
                ld   b, ICON_ROW
                ld   de, (ICON_W << 8) | 2
                xor  a
                push bc
                call stamp_rect                ; (C kept)
                pop  bc
                pop  hl                        ; H = class, L = state
                push bc
                ld   a, h
                ld   e, l
                ld   d, c                      ; D = col
                ld   hl, qs_draw               ; R6 (icons6.asm): icon + count
                call far6
                pop  bc
.attrs:         pop  af                        ; A = slot (B of the push)
                pop  de                        ; E = state
                push af
                ld   a, e
                and  3
                cp   IS_GREY
                jr   nz, .ng
                push de
                ld   b, ICON_ROW
                ld   de, (ICON_W << 8) | 2
                ld   a, ATTR_P_GREY
                call stamp_rect                ; (C kept)
                pop  de
.ng:            pop  bc                        ; B = slot
                ld   d, 0                      ; drawn fresh: plain attrs
                jp   sel_paint                 ; E: PAPER blue / inverse; marks the slot
; .clr — 3 cells of char row B from col C: bitmap 0.  Keeps BC.
.clr:           push bc
                call cell_bm
                ld   c, 8
.cl:            xor  a
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                dec  l
                dec  l
                inc  h
                dec  c
                jr   nz, .cl
                pop  bc
                ret

; item_info / dec16 / info_tab: bank 1 since the C3 review (info1.asm).

; icon bars by class (game.md §3.5): icon ids (panel_icons.asm) / outline /
; IC1 quick slots (SLOT_QFOOD + QS_*: R6 qs_draw)
SLOT_EMPTY      EQU $FE
SLOT_QFOOD      EQU $F9
SLOT_QPOT       EQU SLOT_QFOOD + QS_POTION
SLOT_QSCR       EQU SLOT_QFOOD + QS_SCROLL
QS_DAG          EQU QS_COUNT                   ; AMMO-COUNT: the Warrior's dagger / bow slots are
QS_BOW          EQU QS_COUNT + 1               ; quick-style (16x16 icon + count cell): R6 qs_ammo
SLOT_AMMO0      EQU 3                          ; the Warrior's dagger slot (the bow follows): icons.asm panel_more
SLOT_QDAG       EQU SLOT_QFOOD + QS_DAG
SLOT_QBOW       EQU SLOT_QFOOD + QS_BOW
bar_knight:     DB ICON_SWORD, ICON_POWER, ICON_WHIRL, SLOT_QDAG, SLOT_QBOW
                DB SLOT_EMPTY, SLOT_QFOOD, SLOT_QPOT, SLOT_QSCR, ICON_BAG   ; UB5: food..bag at the Mage's slots 6..9
bar_wizard:     DB ICON_STAFF, ICON_SPARK, ICON_FIREBOLT, ICON_FROST, ICON_DRAIN
                DB ICON_LIGHTNING, SLOT_QFOOD, SLOT_QPOT, SLOT_QSCR, ICON_BAG
                ASSERT bar_wizard - bar_knight == ICON_SLOTS && ICON_COUNT < SLOT_QFOOD && SLOT_QBOW < SLOT_EMPTY
                ASSERT {b bar_knight + SLOT_AMMO0} == SLOT_QDAG && {b bar_knight + SLOT_AMMO0 + 1} == SLOT_QBOW
                ASSERT {b bar_knight + QS_SLOT0 + QS_POTION} == SLOT_QPOT && {b bar_wizard + QS_SLOT0 + QS_POTION} == SLOT_QPOT

                ASSERT ICON_LEN == 54 && ICON8_LEN == 9   ; pblit: 9 B per cell, <= 6 cells
