;==============================================================================
; PANEL ENGINE (B3B-11) — rows 18..23 (concept-screen §5, game.md §3.3–3.5).
; INCLUDEd at the end of bank3.asm. Two parts:
;   1. bank-3 cold code (entered by far3): panel_boot (boot: FONT6 + the hot
;      image -> bank-2 runtime RAM), panel_init (new game: static panel art +
;      state), panel_flush, their helpers and cold data (font, icons).
;   2. the hot image, assembled for HOT_COPY ($B500, bank 2, uncontended,
;      always mapped) and copied there by panel_boot: print6, log_push,
;      panel_tick and its items, bars_draw, num2.
; D5 (user 2026-10-03): panel changes are queued (PANEL_DIRTY bits + the
; LOG_Q message ring) and drained ONE item per tick by panel_tick, never in a
; turn's input tick (play_loop), <= ~3 ticks latency. Logic never reads the
; panel. All drawing goes into the bank-5 screen; present copies it (HUD4_PW
; for the log rows, pmark_rect for the rest).
;==============================================================================

;------------------------------------------------------------------------------
; panel_boot — boot (far3): FONT6 and the hot image into bank-2 runtime RAM.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
panel_boot:
                ld   hl, font6x8
                ld   de, FONT6
                ld   bc, FONT6_LEN
                ldir
                ld   hl, panel_hot_img
                ld   de, HOT_COPY
                ld   bc, PANEL_HOT_LEN
                ldir
                ret
                ASSERT FONT6X8_COUNT * FONT6X8_STRIDE == FONT6_LEN && FONT6X8_STRIDE == 8
                ASSERT (FONT6 & $FF) == 0                   ; print6 glyph addressing

;------------------------------------------------------------------------------
; panel_init — new game (far3 from start_game): the static panel of HERO_KIND
; (icon bar, labels, bar frames, placeholders, gear outlines, attrs) on rows
; 18..23 of bank 5 — the rows must be blank (start_game's clear_screen) —
; panel state reset, then DE (0 = none) pushed to the log and everything
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
                dec  a
                ld   (PANEL_HP_SH), a          ; $FF: never drawn -> PD_HP / PD_ICONS
                ld   (PANEL_POT_SH), a
                ld   a, PD_HP | PD_ICONS | PD_DEPTH
                ld   (PANEL_DIRTY), a
                ; icon bar (rows 18-19): 10 slots of 3 x 2 cells
                ld   hl, bar_knight
                ld   a, (HERO_KIND)
                or   a
                jr   z, .bar
                ld   hl, bar_wizard
.bar:           ld   c, 0                      ; C = slot col
.slot:          ld   a, (hl)
                inc  hl
                push hl
                push bc
                cp   SLOT_POTION
                jr   z, .pot
                ld   hl, icon_empty24
                cp   SLOT_EMPTY
                jr   z, .blit
                ld   hl, icon_tab              ; icon_tab + id * ICON_LEN (cold)
                ld   de, ICON_LEN
                or   a
                jr   z, .blit
                ld   b, a
.mul:           add  hl, de
                djnz .mul
.blit:          ld   b, ICON_ROW
                ld   de, (2 << 8) | ICON_W
                call pblit
                jr   .snext
.pot:           ld   b, ICON_ROW + 1           ; T_POTION glyph (bitmap only; attrs:
                call cell_bm                   ; item_icons) in the slot's bottom-left cell
                ex   de, hl
                ld   hl, TILE_GLYPHS + T_POTION * 8
                ld   b, 8
.pg:            ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .pg
                pop  bc
                push bc
                ld   a, c
                ld   (pot_col), a              ; item_icons draws the count / attrs here
                ld   b, ICON_ROW
                ld   de, (ICON_W << 8) | 2
                xor  a                         ; the slot's attrs: black until item_icons
                call stamp_rect
.snext:         pop  bc
                pop  hl
                ld   a, c
                add  a, ICON_W
                ld   c, a
                cp   ICON_SLOTS * ICON_W
                jr   c, .slot
                ; slot 0 (melee) selected: PAPER blue over its 3 x 2 cells
                ld   bc, ICON_ROW << 8
                call attr_addr
                ld   de, ATTR_STRIDE - ICON_W
                ld   c, 2
.sr:            ld   b, ICON_W
.sc:            ld   a, (hl)
                or   ATTR_P_SEL
                ld   (hl), a
                inc  l
                djnz .sc
                add  hl, de
                dec  c
                jr   nz, .sr
                ; depth cell row 19 (key icon until 3F: none) -> black
                ld   bc, ((ICON_ROW + 1) << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                xor  a
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
                pop  hl                        ; the first message
                ld   a, h
                or   l
                call nz, log_push
                ; fall through
;------------------------------------------------------------------------------
; panel_flush — drain the whole queue now, whole log lines (cold: new game).
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
panel_flush:
                xor  a
                ld   (P_LIM), a
                call panel_step
                ld   a, (PANEL_DIRTY)
                or   a
                jr   nz, panel_flush
                ret

;------------------------------------------------------------------------------
; pblit — opaque cell block: HL = source (D*8 pixel lines x E bytes, row-major,
; then D*E attrs), B = top char row, C = col, D = char rows, E = width (cells).
; Clobbers: A, BC, DE, HL.   (cold: panel_init only)
; SMC: .w+1 / .wa+1 = width (LDIR counts), .ra+1 = rows (attr pass).
;------------------------------------------------------------------------------
pblit:
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

; icon bars by class (game.md §3.5): icon ids (panel_icons.asm) / outline / potion slot
SLOT_EMPTY      EQU $FE
SLOT_POTION     EQU $FD
bar_knight:     DB ICON_SWORD, ICON_POWER, ICON_WHIRL, ICON_DAGGERS, ICON_BOW
                DB SLOT_EMPTY, SLOT_POTION, SLOT_EMPTY, ICON_BAG, SLOT_EMPTY
bar_wizard:     DB ICON_STAFF, ICON_SPARK, ICON_FIREBOLT, ICON_FROST, ICON_DRAIN
                DB ICON_LIGHTNING, SLOT_EMPTY, SLOT_POTION, SLOT_EMPTY, ICON_BAG
                ASSERT bar_wizard - bar_knight == ICON_SLOTS && ICON_COUNT < SLOT_POTION
str_fed:        DB "FED", 0

; cold data: the 6x8 text font (boot-copied to FONT6) and the panel icons
                INCLUDE "../assets/gfx/fonts/font6x8.asm"
                INCLUDE "../assets/gfx/panel/panel_icons.asm"

;==============================================================================
; HOT IMAGE — assembled for HOT_COPY (bank 2 runtime RAM), copied by panel_boot.
;==============================================================================
panel_hot_img:
                DISP HOT_COPY
panel_hot:

;------------------------------------------------------------------------------
; print6 — 6x8 text (FONT6, 6-px pitch) into the bank-5 bitmap. HL = string
; (ASCII 32..127, 0-terminated), B = char row, E = pixel x (even; x + 6*len
; <= 256). print6n: A = max chars (0 = 256).
; A char at x writes its cells with x & 7 = 0 / 2 / 4 / 6: the byte holding
; its left edge is STORED at phase 0 and ORed otherwise; a spill byte (phase
; 4 / 6) is STORED. So a run that starts on a byte boundary (the colour rule
; puts every field on one, game.md §3.4) overwrites its own bytes completely:
; no pre-clear; only cells past the new end keep old ink (callers clear).
; Attrs untouched, nothing marked for present (callers do it).
; Out: HL -> the terminator / first unprinted char, E = x after the last char.
; Clobbers: A, BC, D, HL, E (out).
; SMC: .hb+1 / .rl+1 = the row's bitmap high byte / low base (per call).
; Cost (bank 5 contended at display time): per char ~130 T setup + 8 lines of
; 21 (phase 0) / 37 (2) / 86 (4) / 74 (6) T -> ~400 T average (measured: W15).
;------------------------------------------------------------------------------
print6:
                xor  a
print6n:
                ld   (p6_cnt), a
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   (.hb+1), a                ; SMC: bitmap high of the row
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                ld   (.rl+1), a                ; SMC: (row & 7) << 5
                ld   c, e                      ; C = x
.ch:            ld   a, (hl)
                or   a
                jp   z, .end
                push hl
                ; glyph = FONT6 + (ch - 32) * 8 = (FONT6 - $100) + ch * 8
                rlca
                rlca
                rlca
                ld   b, a
                and  $F8
                ld   e, a
                xor  b
                add  a, (FONT6 >> 8) - 1
                ld   d, a
                ld   a, c
                rrca
                rrca
                rrca
                and  $1F
.rl:            or   0                         ; SMC
                ld   l, a
.hb:            ld   h, 0                      ; SMC
                ld   a, c
                add  a, 6
                ld   c, a                      ; next x
                sub  6
                and  6                         ; phase (x even)
                jp   z, .p0
                cp   4
                jp   c, .p2
                jp   z, .p4
                ; phase 6: bits 7..6 -> this byte's bits 1..0 (OR), bits 5..2 ->
                ; the next byte's bits 7..4 (store): rot left 2 splits them
                DUP  7
                ld   a, (de)
                rlca
                rlca
                ld   b, a
                and  3
                or   (hl)
                ld   (hl), a
                inc  l
                ld   a, b
                and  $F0
                ld   (hl), a
                dec  l
                inc  e                         ; glyphs are 8-aligned
                inc  h
                EDUP
                ld   a, (de)
                rlca
                rlca
                ld   b, a
                and  3
                or   (hl)
                ld   (hl), a
                inc  l
                ld   a, b
                and  $F0
                ld   (hl), a
                jp   .next
.p0:            DUP  7                         ; phase 0: store
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                jp   .next
.p2:            DUP  7                         ; phase 2: bits 5..0 (OR)
                ld   a, (de)
                rrca
                rrca
                or   (hl)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                rrca
                rrca
                or   (hl)
                ld   (hl), a
                jp   .next
.p4:            DUP  7                         ; phase 4: bits 7..4 -> bits 3..0 (OR),
                ld   a, (de)                   ; bits 3..2 -> next byte 7..6 (store)
                rrca
                rrca
                rrca
                rrca
                ld   b, a
                and  $0F
                or   (hl)
                ld   (hl), a
                inc  l
                ld   a, b
                and  $F0
                ld   (hl), a
                dec  l
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                rrca
                rrca
                rrca
                rrca
                ld   b, a
                and  $0F
                or   (hl)
                ld   (hl), a
                inc  l
                ld   a, b
                and  $F0
                ld   (hl), a
.next:          pop  hl
                inc  hl
                ld   a, (p6_cnt)
                dec  a
                ld   (p6_cnt), a
                jp   nz, .ch
.end:           ld   e, c
                ret
p6_cnt:         DB   0

;------------------------------------------------------------------------------
; log_push — queue message HL (0-terminated, upper case, <= LOG_MAX chars;
; longer ones are cut) for the log: copied into the LOG_TXT ring, LOG_QN += 1,
; PANEL_DIRTY |= PD_LOG. Ring full (LOG_SLOTS pending): dropped, LQ_DROP += 1.
; Any tick, any bank paged. Clobbers: A, B, DE, HL.   ~0.5k T (20 chars)
;------------------------------------------------------------------------------
log_push:
                ld   a, (LOG_QN)
                cp   LOG_SLOTS
                jr   c, .ok
                ld   hl, LOG_Q + LQ_DROP
                inc  (hl)
                ret  nz
                dec  (hl)                      ; saturate at 255
                ret
.ok:            ld   b, a
                inc  a
                ld   (LOG_QN), a
                ld   a, (LOG_Q + LQ_RD)
                add  a, b
                and  LOG_SLOTS - 1
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   e, a
                ld   d, LOG_TXT >> 8
                ld   b, LOG_MAX
.c:             ld   a, (hl)
                or   a
                jr   z, .t
                ld   (de), a
                inc  hl
                inc  e
                djnz .c
                xor  a
.t:             ld   (de), a
                ld   a, (PANEL_DIRTY)
                or   PD_LOG
                ld   (PANEL_DIRTY), a
                ret

;------------------------------------------------------------------------------
; panel_tick — play_loop / end_screen, once per tick except a turn's input
; tick (D5). Budget rule: it works only while the tick is still in its FIRST
; frame (SYS_FRAMES == LAST_TICK_FRAME: < 70.9k T used so far), and then does
; one whole item (a log message = scroll + the whole line, <= ~28k T). A tick
; already in its second frame skips the panel: the heavy ticks are the render-
; bound ones (~121k T before any panel work, budget.py), where even a 12-char
; chunk + its present overran the 126k T cap; the queue drains in the light
; ticks (idle / late ANIM ticks), at most one item per tick.
; panel_step — poll the hero's HP / potions against what is drawn (sets
; PD_HP / PD_ICONS), then draw the dirty item first in this order: HP, LOG,
; ICONS, DEPTH (MP / FOOD / AMMO / INFO: nothing to draw until 3C/3E, their
; bits are just cleared). P_LIM = the log print limit (0 = whole line; the
; budget-step variant LOG_CHUNK is kept for tests / later tuning).
; Clobbers: all but IX, IY.
; Cost: ~150 T idle; HP ~2.2k; potion slot ~1k; depth ~1k; log: scroll up to
; ~7.7k (24 cols), print ~650 T/char (W15, contended) -> 32 chars + scroll 27.5k.
;------------------------------------------------------------------------------
panel_tick:
                ld   a, (SYS_FRAMES)
                ld   hl, LAST_TICK_FRAME
                sub  (hl)
                ret  nz                        ; 2nd frame: no panel work this tick
                ld   (P_LIM), a                ; 0: whole items
panel_step:
                ld   a, (P_ENTITIES + E_HP)
                ld   hl, PANEL_HP_SH
                cp   (hl)
                ld   hl, PANEL_DIRTY
                jr   z, .p1
                set  PD_HP_BIT, (hl)
.p1:            ld   a, (P_ENTITIES + E_POT)
                ld   hl, PANEL_POT_SH
                cp   (hl)
                ld   hl, PANEL_DIRTY
                jr   z, .p2
                set  PD_ICONS_BIT, (hl)
.p2:            ld   a, (hl)
                or   a
                ret  z
                rrca
                jp   c, item_hp
                bit  PD_LOG_BIT, (hl)
                jp   nz, item_log
                bit  PD_ICONS_BIT, (hl)
                jp   nz, item_icons
                bit  PD_DEPTH_BIT, (hl)
                jp   nz, item_depth
                ld   (hl), 0                   ; MP / FOOD / AMMO / INFO: 3C / 3E
                ret

;------------------------------------------------------------------------------
; item_hp — HP bar + 2-digit number (row 21, cols 1..6). HL = PANEL_DIRTY.
;------------------------------------------------------------------------------
item_hp:
                res  PD_HP_BIT, (hl)
                ld   a, (P_ENTITIES + E_MAXHP)
                ld   d, a
                ld   a, (P_ENTITIES + E_HP)
                ld   (PANEL_HP_SH), a
                ld   hl, HP_BAR_ADDR
                call bars_draw
                ld   a, (PANEL_HP_SH)
                call num2
                ld   b, STAT_ROW
                ld   e, HP_NUM_COL * 8
                call print6
                ld   bc, (STAT_ROW << 8) | HP_BAR_COL
                ld   de, ((HP_NUM_COL + 2 - HP_BAR_COL) << 8) | 1
                jp   pmark_rect

;------------------------------------------------------------------------------
; item_icons — 3B: the quick-potion slot (count digit at (col+2, 19); attrs:
; glyph cell ATTR_POTION + digit ATTR_HUD, both greyed at 0). HL = PANEL_DIRTY.
;------------------------------------------------------------------------------
item_icons:
                res  PD_ICONS_BIT, (hl)
                ld   a, (P_ENTITIES + E_POT)
                ld   (PANEL_POT_SH), a
                cp   10
                jr   c, .d
                ld   a, 9
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), 0
                dec  l
                ld   a, (pot_col)
                add  a, 2
                add  a, a
                add  a, a
                add  a, a
                ld   e, a                      ; x of cell col + 2
                ld   b, ICON_ROW + 1
                call print6
                ld   a, (pot_col)
                ld   c, a
                ld   b, ICON_ROW + 1
                call attr_addr                 ; HL = attr (19, col); keeps BC
                ld   de, (ATTR_POTION << 8) | ATTR_HUD
                ld   a, (PANEL_POT_SH)
                or   a
                jr   nz, .a
                ld   de, (ATTR_P_GREY << 8) | ATTR_P_GREY
.a:             ld   (hl), d
                inc  l
                inc  l
                ld   (hl), e
                ld   de, (ICON_W << 8) | 1
                jp   pmark_rect                ; (B, C = row 19, slot col)
pot_col:        DB   0                         ; quick-potion slot col (panel_init)

;------------------------------------------------------------------------------
; item_depth — "Dn" at (30, 18) (LVL_DEPTH; the PROTO level 0 shows D1; the
; key icon at (30, 19) arrives with the key in 3F). HL = PANEL_DIRTY.
;------------------------------------------------------------------------------
item_depth:
                res  PD_DEPTH_BIT, (hl)
                ld   a, (LVL_DEPTH)
                or   a
                jr   nz, .d
                inc  a
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), 'D'
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), 0
                ld   l, P_NUMBUF & $FF
                ld   b, ICON_ROW
                ld   e, DEPTH_COL * 8
                call print6
                ld   bc, (ICON_ROW << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                jp   pmark_rect

panel_hot_end:
                ENT
PANEL_HOT_LEN   EQU panel_hot_end - panel_hot
                ASSERT HOT_COPY + PANEL_HOT_LEN <= HOT_COPY_END
HP_BAR_ADDR     EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | HP_BAR_COL
