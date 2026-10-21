;==============================================================================
; r6.asm — the R6 region's resident code (2026-10-21; main.asm "R6 REGION",
; bank 6 R6_ADDR..$FFFF, docs/memory-map.md "R6 region"). ORGed at its
; runtime $C000+ address; the packed overlay streams follow it (main.asm).
;
; Rules (as for bank 3 / bank 7 cold code, conventions.md "Banking"):
;  - entered ONLY through far6 (gfx.asm; any bank's caller: farb restores the
;    caller's $C000 bank) — A, F are clobbered on the way back, so an R6
;    routine reached from another bank returns its results in BC / DE / HL /
;    IX (or memory), never in A / F;
;  - while R6 code runs, bank 6 is at $C000: it may call bank-2 / bank-5 code
;    directly and anything banked only through far1 / far3 / far7 (bank 3 is
;    NOT paged: no direct call into bank-3 code or data);
;  - no SMC; its variables (dp_*) are written in play: tests/game.py #50
;    compares the block at the menu (before any write) only;
;  - it never pages $C000 itself (helpers hand the bank back).
;==============================================================================
                INCLUDE "pickup6.asm"          ; 3E-T11: pu_add, pot_take1, kit_add, mon_drop / drop_put (was bank 3)
                INCLUDE "bag6.asm"             ; 3E-T10: bag_add / bag_find / bag_take / bag_pick, pot_sync user (was bank 3)
                INCLUDE "hunger6.asm"          ; 3E-T9: hunger_turn / hunger_add / item_food
