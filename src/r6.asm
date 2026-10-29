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
                INCLUDE "gear6.asm"            ; 3E-T8: hero_recalc, enchant_weapon, fx_line, it_fmt (+ fx stems, it_stat)
                INCLUDE "fx6.asm"              ; 3E-T12 (+ the T8 equip / remove): fx_main, fx_quick, the effects, tele_pick, pot_eff
                INCLUDE "trap6.asm"            ; 3E-T16: trap_turn / trap_fire (trigger, search, Mage sense, effects)
                INCLUDE "fi6.asm"              ; FLOOR1: fi_add / fi_slot / fi_put (the floor-item glyph cache)
                INCLUDE "abil6.asm"            ; 3F-T6: parry6 / mummy6 / acid6 / wear_slot / wear_apply
                INCLUDE "tier6.asm"            ; 3F-T5: lp_gen (FRESH unit loop + tier roll) / kind_hp, drop_row + drop_tab (from bank 3)
                INCLUDE "pool6.asm"            ; 3F-T1: pool_list / pool_map / pool_gmap (the level pool's kinds)
                INCLUDE "ranged6.asm"          ; 3F-T7: ai_ranged (the shooter decision, the shot + its queued FX descriptor)
    IF F3_GEN
                INCLUDE "sanct6.asm"           ; 3F-T10: sanctum_leaf (D8 Sanctum generation, only with the 3F switch)
    ENDIF
                INCLUDE "icons6.asm"           ; IC1: icon_slot / worn_draw / qs_draw (the 16x16 icon blitter)
                INCLUDE "../assets/gfx/icons/icons16.asm"   ; IC1 + FLOOR1: 45 logical icons in 1,376 B raw (potions share one shape; tools/icons16.py)
