;------------------------------------------------------------------------------
; sv_r4.asm - RECLAIM-SV R4: the dead print code area (print_char .. print_str_end)
; Assembled DISP'd at SV_R4 (main.asm "RECLAIM-SV INSTALL BLOCKS"), copied there by the boot overlay's
; in_tut (instr_ovl.asm). EMPTY today: no LDIR is assembled until this file holds code.
; Rules for code placed here (docs/conventions.md "ROM system-variable area"):
;  - it is NOT in the tape / .sna before in_tut: nothing may call or jump into it before in_tut ran
;    (boot -> in_flow -> in_tut: nothing there references it); tests never use the region as scratch;
;  - bank-5 low RAM, always mapped: callable from any $C000 bank;
;  - assemble with the label names the callers use; callers are bank-2 / low-RAM / far-called code only.
; Free room: SV_R4_END - SV_R4 - SV_R4_LEN (the build DISPLAYs it); tests/game.py #50 and tests/instr.py
; I8b3 verify the installed bytes against build/ovl/sv4.bin after a real boot.
; -DSV_TEST=1 installs a 4-byte pattern (the wiring test; never in a shipped build).
;------------------------------------------------------------------------------
    IFDEF SV_TEST
                DB   $54, $A5, $5A, $C3
    ENDIF
