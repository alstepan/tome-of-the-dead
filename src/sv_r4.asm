;------------------------------------------------------------------------------
; sv_r4.asm - RECLAIM-SV R4: the dead print code area (print_char .. print_str_end)
; Assembled DISP'd at SV_R4 (main.asm "RECLAIM-SV INSTALL BLOCKS"), copied there by the boot overlay's
; in_tut (instr_ovl.asm). ICON-FLASH: ic_learn lives here.
; Rules for code placed here (docs/conventions.md "ROM system-variable area"):
;  - it is NOT in the tape / .sna before in_tut: nothing may call or jump into it before in_tut ran
;    (boot -> in_flow -> in_tut: nothing there references it); tests never use the region as scratch;
;  - bank-5 low RAM, always mapped: callable from any $C000 bank;
;  - assemble with the label names the callers use; callers are bank-2 / low-RAM / far-called code only.
; Free room: SV_R4_END - SV_R4 - SV_R4_LEN (the build DISPLAYs it); tests/game.py #50 and tests/instr.py
; I8b3 verify the installed bytes against build/ovl/sv4.bin after a real boot.
; -DSV_TEST=1 installs a 4-byte pattern (the wiring test; never in a shipped build).
;------------------------------------------------------------------------------
; ic_learn - ICON-FLASH (user 2026-11-18): fx_book's `.learn` (A = k, the class ability index): far7 abil_learn, then,
; when it was a NEW ability (rank 0 -> 1: abil_learn's L = 1; a rank-up returns 2 / 3, rank 3 returns 0), arm
; ICON_FL = 3 * (k + 1) (the ability's bar slot, cols 3i..3i+2) + ICON_FLT = SYS_FRAMES; ic_fl does the rest.
; Not in D0: the tutorial pointer owns the icon there (item_depth's digit SMC = '0' - 1 only while D0 runs).
; Out: as abil_learn's far7 (L is not read by fx_book). Clobbers: A, BC, DE, HL.   ~0.3k T + abil_learn
ic_learn:       push af
                ld   hl, abil_learn
                call far7                      ; (A, F lost; bank 7 back)
                pop  bc                        ; B = k
                dec  l
                ret  nz                        ; a rank-up (L 2 / 3) or nothing (0): no flash
                ld   a, (item_depth.d + 1)
                cp   '0' - 1
                ret  z                         ; D0: the tutorial pointer's
                ld   a, b
                inc  a                         ; slot k + 1 (slot 0 = the weapon)
                ld   c, a
                add  a, a
                add  a, c                      ; col 3 * slot
                ld   (ICON_FL), a
                ld   hl, (SYS_FRAMES)
                ld   (ICON_FLT), hl
                ret

; ic_mark - ic_fl's tail (R4: the cold block had 3 B too few): HL = the first flashed attr cell (row 18, col + $40 in L):
; mark the 3 x 2 cells for the next present (screen 2 gets the attr change), then ic_fl's exit (pop bc / pop hl / ret).
ic_mark:        ld   c, l
                res  6, c                      ; col = L - $40 (col <= 30)
                ld   b, ICON_ROW
                ld   de, ICON_W << 8 | 2
                call pmark_rect                ; (BC, DE kept)
                pop  bc
                pop  hl
                ret

    IFDEF SV_TEST
                DB   $54, $A5, $5A, $C3
    ENDIF
