;==============================================================================
; ui1.asm — bank-1 UI code (C3-0 region; plan "3C breakdown" D4): menus,
; pause and end screens. Runs at $C000.. with BANK_UI1 paged, entered ONLY
; through far1 (gfx.asm: HL = target, A = arg; the caller's $C000 bank is
; restored on return). Same rules as bank3.asm: never page $C000 here; call
; only helpers that hand $C000 back (msg_push, print6t, copy_virt_keep,
; blit_keep, far3 / far1 ...; conventions.md "Banking"). The bank-1 data
; (vdata) is readable in place at virtual + TEXT_DISP; the text block is in
; bank 0 since D3-TX: read it only through tx_dec / print6x / msg_push.
; C3 review: the transition scrolls (scroll1.asm), the info line (info1.asm).
;==============================================================================
                INCLUDE "scroll1.asm"
                INCLUDE "info1.asm"
                INCLUDE "menu1.asm"
                INCLUDE "ui1_vars.asm"
