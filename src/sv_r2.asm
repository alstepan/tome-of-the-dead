;------------------------------------------------------------------------------
; sv_r2.asm - RECLAIM-SV R2: the sysvar hole $5C7B..$5CDA
; Assembled DISP'd at SV_R2 (main.asm "RECLAIM-SV INSTALL BLOCKS"), copied there by the boot overlay's
; in_tut (instr_ovl.asm). XP-BAR (2026-11-18) / XP-BAR2 (2026-11-19): depth_tail + xp_bar (+ its draw xpb_draw; the divide is R5's).
; Rules for code placed here (docs/conventions.md "ROM system-variable area"):
;  - it is NOT in the tape / .sna before in_tut: nothing may call or jump into it before in_tut ran
;    (boot -> in_flow -> in_tut: nothing there references it); tests never use the region as scratch;
;  - bank-5 low RAM, always mapped: callable from any $C000 bank;
;  - assemble with the label names the callers use; callers are bank-2 / low-RAM / far-called code only.
; Free room: SV_R2_END - SV_R2 - SV_R2_LEN (the build DISPLAYs it); tests/game.py #50 and tests/instr.py
; I8b3 verify the installed bytes against build/ovl/sv2.bin after a real boot.
; -DSV_TEST=1 installs a 4-byte pattern (the wiring test; never in a shipped build; XP-BAR2 left R2 10 B free, so it fits again).
;------------------------------------------------------------------------------
; depth_tail — XP-BAR: the tail of item_depth (was `jp far6` of key_pan; item_depth now `jp depth_tail`):
; key_pan (far6, A = LVL_FLAGS passes through), then xp_bar. Low RAM (this R2 hole: always mapped, no far1).
; xp_bar — XP-BAR2 (user 2026-11-19; XP-BAR 2026-11-18 was 8 px at (30, 19)): the 23-px XP progress bar on
; row STAT_ROW, cols XPB_COL..+2 = 25..27, between the level digit (24) and "Dn" (28-29). Boot-installed in R2
; (in_tut): reads bank-2 xpn_tab / pm_tab, writes the bank-5 screen; it must never run before in_tut
; (item_depth runs only after the menu: panel_init is level_enter's). PD_DEPTH is set by xp_level on every XP
; gain / level-up and by panel_init. Fill = floor(23 * d / span) px from the left, d = XP - T(LVL-1), span =
; T(LVL) - T(LVL-1), T = xpn_tab (bank 2, always mapped; T(0) = 0): both fit a byte (<= 253, xp2.asm
; ASSERTs), so 23 * d < 2^13 and the divide is <= 22 subtractions. Max level, or a transient d >= span (the
; level-up is a turn end later): full (23). Style = the FOOD bar's: frame lines 1 / 6, the fill on lines 2..5,
; end caps at bit 7 of col 25 / bit 1 of col 27 (so fills 0 / 1 and 22 / 23 look alike); bit 0 of col 27 is never set (frame $FE, fill <= 23 px): a 1-px gap
; before "D". Lines 0 / 7 stay blank (never written). Attr = pi_rects' ATTR_LVL, never written here (a tutorial
; BARS pointer's FLASH survives a redraw). item_depth marks the cells.
; Split (R2 has no room for all): the multiply + divide loop xpb_div is R5's (sv_r5.asm, bank 2: uncontended,
; ~56 T a px instead of ~90 here), the draw xpb_draw stays here (it falls out of .full).
; Clobbers: A, BC, DE, HL.   L9 ~0.35k T; a fill of n px ~0.6k + ~56 T * n (worst 22 px ~1.85k T)
;------------------------------------------------------------------------------
depth_tail:
                ld   hl, key_pan
                call far6                      ; A = LVL_FLAGS passes through; bank 1 comes back
xp_bar:
                ld   a, (LVL)
                cp   LVL_MAX
                jr   nc, .full
                ld   l, a
                ld   h, 0
                add  hl, hl
                ld   de, xpn_tab - 2           ; row LVL - 1 = T(LVL)
                add  hl, de
                ld   e, (hl)                   ; T(LVL) low (the span fits a byte: low bytes suffice)
                ld   bc, 0                     ; T(0) = 0
                dec  a
                jr   z, .p0
                dec  hl
                ld   b, (hl)
                dec  hl
                ld   c, (hl)                   ; BC = T(LVL - 1)
.p0:            ld   a, e
                sub  c
                ld   e, a
                ld   d, 0                      ; DE = the span (<= 253)
                ld   hl, (XP)
                or   a
                sbc  hl, bc                    ; HL = d = XP - T(LVL - 1) (>= 0: CF = 0)
                sbc  hl, de
                jr   nc, .full                 ; d >= span: a transient (the level-up is a turn end later)
                add  hl, de                    ; d again (< span <= 253: H = 0)
                jp   xpb_div                   ; R5: 23 * d / span -> the mask, then back to xpb_draw
.full:          ld   bc, $FFFF
                ld   a, $FE                    ; 23 px (bit 0 of the last cell: the gap)
;------------------------------------------------------------------------------
; xpb_draw — XP-BAR2: B / C / A = the fill mask of the 3 bar cells (25..27, row STAT_ROW; A bit 0 = 0: the gap
; before "D"). Writes lines 1..6 of each cell: frame D on lines 1 / 6 ($FF, the last cell $FE), the mask on
; lines 2..5 with the FOOD bar's end caps ORed in (bit 7 of col 25, bit 1 of col 27: a closed box at a low fill;
; a full bar is unchanged, its mask already has both bits). Never the attrs (ATTR_LVL by pi_rects). From .full
; above or R5's xpb_div.
; Clobbers: A, BC, DE, HL.   ~0.4k T
;------------------------------------------------------------------------------
XPB_BM          EQU SCREEN_BITMAP + ((STAT_ROW & $18) << 8) + ((STAT_ROW & 7) << 5) + XPB_COL
xpb_draw:
                ld   hl, XPB_BM + $100         ; line 1 of the first cell
                ld   d, $FF                    ; D = the frame byte
                set  7, b                      ; XP-BAR2 caps (user 2026-11-19, as bars_draw / fbar_gap): left cap bit 7
                or   2                         ; of col 25, right cap bit 1 of col 27 (lines 2..5; 1 / 6 are frame)
                ld   e, a                      ; E = the last cell's mask
                call .cl                       ; cell 0: B
                ld   b, c
                call .cl                       ; cell 1
                ld   b, e
                dec  d                         ; the last cell's frame $FE
.cl:            ld   (hl), d                   ; line 1
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b                   ; lines 2..5
                inc  h
                ld   (hl), d                   ; line 6
                ld   h, (XPB_BM + $100) >> 8
                inc  l
                ret
                ASSERT (XPB_BM & $700) == 0 && (XPB_BM & $FF) + XPB_CELLS <= $100 && XPB_CELLS == 3 && XPB_PX == 23

    IFDEF SV_TEST
                DB   $52, $A5, $5A, $C3
    ENDIF
