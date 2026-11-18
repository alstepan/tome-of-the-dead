;------------------------------------------------------------------------------
; sv_r2.asm - RECLAIM-SV R2: the sysvar hole $5C7B..$5CDA
; Assembled DISP'd at SV_R2 (main.asm "RECLAIM-SV INSTALL BLOCKS"), copied there by the boot overlay's
; in_tut (instr_ovl.asm). XP-BAR (2026-11-18): depth_tail + xp_bar live here (95 of 96 B).
; Rules for code placed here (docs/conventions.md "ROM system-variable area"):
;  - it is NOT in the tape / .sna before in_tut: nothing may call or jump into it before in_tut ran
;    (boot -> in_flow -> in_tut: nothing there references it); tests never use the region as scratch;
;  - bank-5 low RAM, always mapped: callable from any $C000 bank;
;  - assemble with the label names the callers use; callers are bank-2 / low-RAM / far-called code only.
; Free room: SV_R2_END - SV_R2 - SV_R2_LEN (the build DISPLAYs it); tests/game.py #50 and tests/instr.py
; I8b3 verify the installed bytes against build/ovl/sv2.bin after a real boot.
; -DSV_TEST=1 installs a 4-byte pattern (the wiring test; never in a shipped build; it no longer fits R2 next to xp_bar, 1 B free:
; use it on R4 / R5 only).
;------------------------------------------------------------------------------
; depth_tail — XP-BAR: the tail of item_depth (was `jp far6` of key_pan; item_depth now `jp depth_tail`):
; key_pan (far6, A = LVL_FLAGS passes through), then xp_bar. Low RAM (this R2 hole: always mapped, no far1).
; xp_bar — XP-BAR (user 2026-11-18): the 8-px XP progress bar in the free panel cell (XPB_COL, XPB_ROW) =
; (30, 19), under "Dn", beside the level digit. Boot-installed in R2 (in_tut): reads bank-2 xpn_tab / pm_tab, writes the bank-5 screen;
; it must never run before in_tut (item_depth runs only after the menu: panel_init is level_enter's). PD_DEPTH is set
; by xp_level on every XP gain / level-up and by panel_init). Fill = floor(8 * (XP - T(LVL-1)) / (T(LVL) -
; T(LVL-1))) px from the left, T = xpn_tab (bank 2, always mapped; T(0) = 0): both XP deltas fit a byte
; (<= 253), so the divide is <= 8 subtractions of the span from 8 * d. Max level: full. A transient
; XP >= T(LVL) (the level-up is a turn end later) clamps at 8. Style = the FOOD bar's: frame lines 1 / 6 and
; the fill on lines 2..5 (no side caps: the fill's width is exact, 0..8), ink ATTR_LVL (the digit's gold, the
; attr rect of panel_init7). Lines 0 / 7 stay blank (never written, like the key cells). item_depth marks it.
; Clobbers: A, BC, DE, HL.   ~0.5k T (no far1: -0.1k)
;------------------------------------------------------------------------------
XPB_BM          EQU SCREEN_BITMAP + ((XPB_ROW & $18) << 8) + ((XPB_ROW & 7) << 5) + XPB_COL
depth_tail:
                ld   hl, key_pan
                call far6                      ; A = LVL_FLAGS passes through; bank 1 comes back
xp_bar:
                ld   c, 8                      ; fill px (max level: full)
                ld   a, (LVL)
                cp   LVL_MAX
                jr   nc, .draw
                ld   l, a
                ld   h, 0
                add  hl, hl
                ld   de, xpn_tab - 2           ; row LVL - 1 = T(LVL)
                add  hl, de
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                   ; DE = T(LVL)
                ld   bc, 0                     ; T(0) = 0
                dec  a
                jr   z, .p0
                dec  hl
                dec  hl
                dec  hl
                ld   c, (hl)
                inc  hl
                ld   b, (hl)                   ; BC = T(LVL - 1)
.p0:            ex   de, hl
                or   a
                sbc  hl, bc
                ex   de, hl                    ; DE = the span (<= 253)
                ld   hl, (XP)
                sbc  hl, bc                    ; HL = XP - T(LVL - 1) (CF = 0 from the span's sbc: no borrow)
                ld   c, 8
                ld   a, h
                or   a
                jr   nz, .draw                 ; transient: past the span (level-up pending)
                ld   c, a                      ; 0
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; 8 * d (< 2,048)
.dv:            and  a
                sbc  hl, de
                jr   c, .draw
                inc  c
                ld   a, c
                cp   8
                jr   nz, .dv                   ; (d >= span: stops at 8)
.draw:          ld   a, pm_tab & $FF
                add  a, c
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, (hl)                   ; $FF >> fill
                cpl
                ld   b, a                      ; B = the first `fill` px
                ld   hl, XPB_BM + $100
                ld   (hl), $FF                 ; line 1
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b
                inc  h
                ld   (hl), b                   ; lines 2..5
                inc  h
                ld   (hl), $FF                 ; line 6
                ret
                ASSERT (pm_tab >> 8) == ((pm_tab + 8) >> 8) && (XPB_BM & $700) == 0 && XPB_COL == DEPTH_COL

    IFDEF SV_TEST
                DB   $52, $A5, $5A, $C3
    ENDIF
