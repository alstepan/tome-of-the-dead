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
                INCLUDE "hunger6.asm"          ; 3E-T9: item_food (w2b: the hunger logic is bank-7 hunger7.asm)
                INCLUDE "gear6.asm"            ; 3E-T8: hero_recalc, enchant_weapon, fx_line, it_fmt (+ fx stems, it_stat)
                INCLUDE "fx6.asm"              ; 3E-T12 (+ the T8 equip / remove): fx_main, fx_quick, the effects, tele_pick, pot_eff
                INCLUDE "trap6.asm"            ; 3E-T16: tele_arm / tele_flash / trap_at (w2b: the runtime is bank-7 trap7.asm)
                INCLUDE "fi6.asm"              ; FLOOR1: fi_add / fi_slot / fi_put (the floor-item glyph cache)
                INCLUDE "abil6.asm"            ; 3F-T6: parry6 / mummy6 / acid6 / wear_slot / wear_apply
                INCLUDE "tier6.asm"            ; 3F-T5: lp_gen (FRESH unit loop + tier roll) / kind_hp, drop_row + drop_tab (from bank 3)
                INCLUDE "pool6.asm"            ; 3F-T1: pool_list / pool_map / pool_gmap (the level pool's kinds)
                INCLUDE "ranged6.asm"          ; 3F-T7: ai_ranged (the shooter decision, the shot + its queued FX descriptor)
                INCLUDE "arch6.asm"            ; 3F-T11b: arch_ai, the Archmage's spell AI (far6 from bank-2 ai_mon)
                INCLUDE "spawn6.asm"           ; 3F-T9: the spawn queue (breed6 / sp_bcall / ph_summon) + sp_run (end_turn)
                INCLUDE "trickle6.asm"         ; 3F-T12: trk_run, the respawn trickle (far6 from end_turn every RESPAWN_PERIOD turns)
                INCLUDE "vbat6.asm"            ; 3F-T9: the Vampire's bat form (vb_one: far6 from bank-7 vb_turn, end_turn)
                ; (DBG-1: debug_kit moved to bank 0, src/kit0.asm kit_b0, far from kit_add)
                ; (MEM-RECLAIM w3: lq_block, the AI-L1 ladder queue, moved to bank 3: src/lq3.asm)
                INCLUDE "boss6.asm"            ; 3F-T8: lp_post (the lair boss; w2b: ai_guard / grate_open / boss_chk -> boss7.asm)
                ; (3F-T10 sanct6.asm: M0 -> bank 7 sanct7.asm, the high block after the tilesets)
                INCLUDE "tome6.asm"            ; P3: seal_open (the Archmage's death) + tome_geo6 (hero vs lectern)
                INCLUDE "icons6.asm"           ; IC1: icon_slot / worn_draw / qs_draw (the 16x16 icon blitter)
                ; AMMO-COUNT: before the icon data (after it, qs_ammo's +66 B made the guard pad 26 B)
                ; (MEM-RECLAIM w3: lp_wt6 is gone: R6 reads the bank-2 lp_wt, kind_tab + KT_REACH)
                INCLUDE "../assets/gfx/icons/icons16.asm"   ; IC1 + FLOOR1: 45 logical icons packed in 995 B (1,376 raw; MEM-RECLAIM w2c; tools/icons16.py)
fs_worn:        DB   " WORN OUT", 0           ; it_fmt (gear6.asm): m = -3 (after the icon data)
