;==============================================================================
; PANEL ENGINE (B3B-11) — rows 18..23 (concept-screen §5, game.md §3.3–3.5).
; INCLUDEd at the end of bank3.asm. Two parts:
;   1. bank-3 cold code (entered by far3): panel_boot (boot: FONT6 planes +
;      the hot image -> bank-2 runtime RAM), panel_init (new game: static
;      panel art + state), panel_flush, their helpers.
;   2. (B3B-11b) the boot / new-game cold DATA — font6x8, the panel icons, the
;      hot image (panel_hot.asm: print6, log_push, panel_tick, item_hp) — is
;      NOT here: main.asm `vdata` puts it in bank 1 after the ZX0 sprite
;      sources; bank-3 code reads it only through
;      copy_virt3 (lowram), into GEN_SRC or straight to its bank-2 target.
; D5 (user 2026-10-03): panel changes are queued (PANEL_DIRTY bits + the
; LOG_Q message ring) and drained ONE item per tick by panel_tick, never in a
; turn's input tick (play_loop), <= ~3 ticks latency. Logic never reads the
; panel. All drawing goes into the bank-5 screen; present copies it (HUD4_PW
; for the log rows, pmark_rect for the rest).
;==============================================================================

;------------------------------------------------------------------------------
; panel_boot — boot (far3): the hot image -> HOT_COPY, and the planar FONT6
; (level_defs.asm) built from the char-major font6x8, 48 chars at a time
; through GEN_SRC (free at boot after init_tiles). Glyph bits 1..0 are masked
; off here, so no glyph can bleed into the next char (print6).
; Clobbers: A, BC, DE, HL.   ~45k T (boot only)
;------------------------------------------------------------------------------
P6_HALF         EQU 48                         ; chars per GEN_SRC pass
panel_boot:
                ld   hl, panel_hot_img
                ld   de, HOT_COPY
                ld   bc, PANEL_HOT_LEN
                call copy_virt3
                ld   hl, font6x8
                ld   c, FONT6_FIRST            ; C = char code
.half:          push hl
                push bc
                ld   de, GEN_SRC
                ld   bc, P6_HALF * FONT6X8_STRIDE
                call copy_virt3
                pop  bc
                ld   hl, GEN_SRC
.ch:            ld   d, FONT6 >> 8
                ld   b, FONT6_PAGES
.ln:            ld   e, c                      ; even line: window A (offset = code)
                ld   a, (hl)
                and  $FC
                ld   (de), a
                inc  hl
                ld   a, c
                add  a, FONT6_WB               ; odd line: window B
                ld   e, a
                ld   a, (hl)
                and  $FC
                ld   (de), a
                inc  hl
                inc  d
                djnz .ln
                inc  c
                ld   a, c
                cp   FONT6_FIRST + P6_HALF
                jr   z, .h2
                cp   FONT6_FIRST + FONT6X8_COUNT
                jr   nz, .ch
                pop  hl
                ret
.h2:            pop  hl
                ld   de, P6_HALF * FONT6X8_STRIDE
                add  hl, de
                jr   .half
                ASSERT FONT6X8_COUNT == 2 * P6_HALF && FONT6X8_STRIDE == 8 && FONT6_PAGES * 2 == 8
                ASSERT P6_HALF * FONT6X8_STRIDE <= 512  ; GEN_SRC

;------------------------------------------------------------------------------
; panel_init — new game (far3 from start_game): the static panel of HERO_KIND
; (icon bar, labels, bar frames, placeholders, gear outlines, attrs) on rows
; 18..23 of bank 5 — the rows must be blank (start_game's clear_screen) —
; panel state reset (the *_SH "as drawn" bytes: $FF = never drawn; STAT_SH
; 0 = both status cells blank, as drawn here), then string E (TX_*, TX_NONE = none; B3B-13: was a
; pointer in DE) pushed to the log and everything
; queued drawn at once (panel_flush). The caller presents (present_full).
; Placeholders until 3C/3E: MP bar empty, FOOD bar full + "FED", no ammo, no
; info line, empty gear outlines; quick slots outlined except the potion slot
; (T_POTION glyph + count, the PROTO "POT n").  Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
panel_init:
                push de
                ld   hl, HUD4_EXT              ; HUD4_EXT, HUD4_PW: rows blank, nothing pending
                ld   b, 2 * TEXT_ROWS
                xor  a
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   (LOG_QN), a
                ld   hl, LOG_Q
                ld   b, LOG_Q_LEN
.zq:            ld   (hl), a
                inc  l
                djnz .zq
                ld   (STAT_SH), a              ; D3-8 review: sig 0 = the blank cells this
                                               ; static panel has; a status carried over
                                               ; level_show then differs and redraws
                dec  a
                ld   (PANEL_HP_SH), a          ; $FF: never drawn -> PD_HP / PD_ICONS
                ld   (PANEL_HP_SH + 1), a
                ld   (PANEL_POT_SH), a
                ld   (LVL_SH), a               ; level digit: never drawn
                ld   (ICON_SIG), a             ; (no real signature is $FF)
                ld   a, PD_HP | PD_ICONS | PD_DEPTH | PD_INFO
                ld   (PANEL_DIRTY), a
                ; C3-3: the icon bar is drawn by item_icons (icon_state vs
                ; ICON_SH): every slot "never drawn" -> slot_redraw each
                ld   hl, ICON_SH
                ld   b, ICON_SLOTS
                ld   a, IS_NONE
.ish:           ld   (hl), a
                inc  l
                djnz .ish
                ld   b, 0                      ; the quick-potion slot
.ps:            ld   a, b
                call slot_act
                cp   SA_POTION
                jr   z, .psf
                inc  b
                jr   .ps
.psf:           ld   a, b
                ld   (pot_slot), a
                ; info line fields (game.md §3.4): name chars 0-15, numbers 16-27,
                ; notes 28-41 = cols 0-11 / 12-20 / 21-31
                ld   a, ATTR_INFO_NAME
                ld   bc, INFO_ROW << 8
                ld   de, (INFO_NUM_COL << 8) | 1
                call stamp_rect
                ld   a, ATTR_INFO_NUM
                ld   bc, (INFO_ROW << 8) | INFO_NUM_COL
                ld   de, ((INFO_NOTE_COL - INFO_NUM_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_INFO_NOTE
                ld   bc, (INFO_ROW << 8) | INFO_NOTE_COL
                ld   de, ((ROOM_COLS - INFO_NOTE_COL) << 8) | 1
                call stamp_rect
                ; depth cell row 19 (key icon until 3F: none) -> black
                ld   bc, ((ICON_ROW + 1) << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                xor  a
                call stamp_rect
                ld   a, ATTR_LVL               ; C3-3: the level digit at (31, 19)
                ld   bc, ((ICON_ROW + 1) << 8) | LVL_COL
                ld   de, (1 << 8) | 1
                call stamp_rect
                ; row 21: labels + bar frames + attrs
                ld   hl, label_heart
                ld   bc, (STAT_ROW << 8) | HP_LBL_COL
                call glyph8
                ld   hl, label_drop
                ld   bc, (STAT_ROW << 8) | MP_LBL_COL
                call glyph8
                ld   hl, label_drumstick
                ld   bc, (STAT_ROW << 8) | FOOD_LBL_COL
                call glyph8
                ld   a, ATTR_P_HP
                ld   bc, (STAT_ROW << 8) | HP_BAR_COL
                ld   de, ((HP_NUM_COL + 2 - HP_BAR_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_P_MP
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL
                ld   de, ((MP_NUM_COL + 2 - MP_BAR_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_P_FED
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                call stamp_rect
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL   ; MP placeholder: empty bar
                call cell_bm
                xor  a
                ld   d, 1
                call bars_draw
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL ; FOOD placeholder: full bar
                call cell_bm
                ld   a, 1
                ld   d, a
                call bars_draw
                ld   hl, str_fed
                ld   b, STAT_ROW
                ld   e, HUNGER_COL * 8
                call print6
                ASSERT ((HUNGER_COL * 8) & 7) == 0 && HUNGER_COL * 8 + 6 * 3 <= 256  ; print6 x rule ("FED")
                ; rows 22-23: log attrs, worn-gear outlines
                ld   a, ATTR_LOG_OLD
                ld   bc, LOG_ROW << 8
                ld   de, (LOG_COLS << 8) | 1
                call stamp_rect
                ld   c, GEAR_COL
.gear:          push bc
                ld   hl, icon_empty16
                ld   b, LOG_ROW
                ld   de, (2 << 8) | 2
                call pblit
                pop  bc
                inc  c
                inc  c
                ld   a, c
                cp   ROOM_COLS
                jr   c, .gear
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
; art: the 3E quick food / scroll), the quick potion (T_POTION glyph + count,
; ATTR_POTION / ATTR_HUD) or the bar icon (pblit, its own attrs); IS_GREY
; -> all 6 attrs ATTR_P_GREY; IS_SEL -> PAPER blue (sel_paint, which marks).
; Clobbers: all but IX, IY.   ~3k T (pblit through GEN_SRC)
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
                cp   SLOT_POTION
                jr   z, .pot
                cp   SLOT_EMPTY
                jr   z, .out
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
.pot:           ld   b, ICON_ROW               ; blank 3 x 2, then the glyph + count
                call .clr
                ld   b, ICON_ROW + 1
                call .clr
                push bc
                call cell_bm                   ; (19, col)
                ex   de, hl
                ld   hl, TILE_GLYPHS + T_POTION * 8
                ld   b, 8
.pg:            ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .pg
                ld   a, (P_ENTITIES + E_POT)
                cp   10
                jr   c, .d
                ld   a, 9
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), 0
                dec  l
                pop  bc
                push bc
                ld   a, c
                add  a, 2
                add  a, a
                add  a, a
                add  a, a
                ld   e, a                      ; x of (col + 2): a cell (print6 x rule)
                ld   b, ICON_ROW + 1
                call print6
                pop  bc
                push bc
                ld   b, ICON_ROW
                ld   de, (ICON_W << 8) | 2
                xor  a
                call stamp_rect
                pop  bc
                push bc
                ld   b, ICON_ROW + 1
                call attr_addr
                ld   (hl), ATTR_POTION
                inc  l
                inc  l
                ld   (hl), ATTR_HUD
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

; item_info / dec16 / xp_next / info_tab: bank 1 since the C3 review (info1.asm).

; icon bars by class (game.md §3.5): icon ids (panel_icons.asm) / outline / potion slot
SLOT_EMPTY      EQU $FE
SLOT_POTION     EQU $FD
bar_knight:     DB ICON_SWORD, ICON_POWER, ICON_WHIRL, ICON_DAGGERS, ICON_BOW
                DB SLOT_EMPTY, SLOT_POTION, SLOT_EMPTY, ICON_BAG, SLOT_EMPTY
bar_wizard:     DB ICON_STAFF, ICON_SPARK, ICON_FIREBOLT, ICON_FROST, ICON_DRAIN
                DB ICON_LIGHTNING, SLOT_EMPTY, SLOT_POTION, SLOT_EMPTY, ICON_BAG
                ASSERT bar_wizard - bar_knight == ICON_SLOTS && ICON_COUNT < SLOT_POTION
str_fed:        DB "FED", 0

                ASSERT ICON_LEN == 54 && ICON8_LEN == 9   ; pblit: 9 B per cell, <= 6 cells
