;------------------------------------------------------------------------------
; sv_r5.asm - RECLAIM-SV R5: the ISR stack slack $BE00..$BE2F
; Assembled DISP'd at SV_R5 (main.asm "RECLAIM-SV INSTALL BLOCKS"), copied there by the boot overlay's
; in_tut (instr_ovl.asm). XP-BAR2 (2026-11-19): xpb_div (the divide of R2's xp_bar) + fbar_gap.
; Rules for code placed here (docs/conventions.md "ROM system-variable area"):
;  - it is NOT in the tape / .sna before in_tut: nothing may call or jump into it before in_tut ran
;    (boot -> in_flow -> in_tut: nothing there references it); tests never use the region as scratch;
;  - bank 2, always mapped: callable from any $C000 bank;
;  - assemble with the label names the callers use; callers are bank-2 / low-RAM / far-called code only.
; Free room: SV_R5_END - SV_R5 - SV_R5_LEN (the build DISPLAYs it); tests/game.py #50 and tests/instr.py
; I8b3 verify the installed bytes against build/ovl/sv5.bin after a real boot.
; -DSV_TEST=1 installs a 4-byte pattern (the wiring test; never in a shipped build).
;------------------------------------------------------------------------------
;------------------------------------------------------------------------------
; xpb_div — XP-BAR2: the middle of R2's xp_bar (`jp xpb_div`): HL = d, DE = span (d < span <= 253, D = 0).
; HL := 23 * d, then one subtraction of the span per px (floor(23 * d / span) <= 22), each shifting a 1 into
; the 3-byte fill mask B:C:A; on to R2's xpb_draw. Here, not in R2: bank 2 is uncontended (~56 T a px).
; Clobbers: A, BC, DE, HL (+ xpb_draw's).   ~0.1k + ~56 T a px
;------------------------------------------------------------------------------
xpb_div:
                ld   b, h
                ld   c, l
                add  hl, hl
                add  hl, hl
                add  hl, bc
                add  hl, hl
                add  hl, bc
                add  hl, hl
                add  hl, bc                    ; 23 * d = ((4d + d) * 2 + d) * 2 + d (< 2^13: CF = 0)
                ld   c, b                      ; B = 0: the fill mask B:C:A = 0 px
                xor  a
.dv:            sbc  hl, de                    ; CF = 0 on entry (the adds) and after each rra
                jr   c, .o
                scf
                rr   b
                rr   c
                rra                            ; mask >> 1, a 1 in; CF out = A bit 0 = 0 (<= 22 px)
                jp   nc, .dv                   ; (always: 10 T, a jr is 12)
.o:             jp   xpb_draw

;------------------------------------------------------------------------------
; fbar_gap — XP-BAR2 (user 2026-11-19: >= 1 px between a row-21 bar and its neighbour): bank-0 item_food's
; `call bars_draw` (bank 0 paged; R5 is bank 2, always mapped; item_food runs only in play, after in_tut).
; The FOOD bar then ends at 31 px: bit 0 of its last cell (col 18, lines 1..6) cleared, the right cap moved
; to bit 1, so "FED" / "HUNGRY" (bit 7 of col 19) keeps a 1-px gap. print6 needs a byte-aligned x, so the
; word cannot move right instead. The fill scale is item_food's D = FOOD_BAR_D (~31 / 100: <= 31 px).
; Here (not in B0_CODE2) because the trace build's bank 0 had 2 B free. In: as bars_draw. Clobbers: as
; bars_draw.   bars_draw + ~0.3k T
; HPMP-GAP: also item_hp / item_mp (cols 1..4 / 8..11, numbers at cols 5 / 12), same geometry.
;------------------------------------------------------------------------------
fbar_gap:
                call bars_draw                 ; HL out = line 0 of the cell after the bar
                dec  l
                inc  h                         ; line 1 of the bar's last cell
                ld   b, 6
.g:             res  0, (hl)
                set  1, (hl)                   ; the cap (lines 1 / 6 are $FF anyway)
                inc  h
                djnz .g
                ret

    IFDEF SV_TEST
                DB   $55, $A5, $5A, $C3
    ENDIF
