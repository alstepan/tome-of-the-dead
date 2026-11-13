;==============================================================================
; newgame0.asm — B0CODE (2026-11-12): the B0_CODE2 proof routine. new_game moved
; from bank 7 (boot7.asm) to the bank-0 region B0_CODE2 (B0_FREE_START.., main.asm;
; on the text tape block). Rules (docs/memory-map.md "B0CODE ledger"): runs with
; BANK_TEXT = bank 0 at $C000; never pages $C000 itself (far3 / far6 / far7 restore
; bank 0); no SMC (the block is compared with the .sna, game.py #50 / gfx_integrity);
; reads bank-0 data only with bank 0 paged. Once per game (start_game, FARB0).
;==============================================================================
;==============================================================================
; NEW GAME (prototype §6.5: fixed gameplay RNG seed; all rooms, monsters,
; potions re-initialised). HERO_KIND already set. B0CODE: bank 0 B0_CODE2
; (FARB0 from start_game; was bank 7 since MEM-SND, bank 3 since A7). Hero slot 0: kind, flags, HP; the start
; kit (kit_add, 3E-T11: WORN + BAG; E_POT follows the bag).
; B3B-12 / D3-11: proto_start = 1 (test path) no longer branches here: the
; PROTO fixture (src/proto_fix.asm, run by start_game's proto_hook) rewrites the
; level state and the slots after it. MASTER_SEED = SYS_FRAMES
; at the hero choice (game.md §1 "Seed"; seed_fixed = 1 forces seed_value)
; and nothing else — start_game's level_enter generates D1, populates it and
; ends with vis_reset. Clobbers: all but IY.
;==============================================================================
new_game:
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   hl, 0
                ld   (TURN_COUNTER), hl
                ld   (TICK_COUNTER), hl        ; per-game test observables
    IF ANIM_TRACE_ON                          ; (OVERRUN_COUNT, GEN_OVERFLOW
                ld   hl, ANIM_TRACE            ; stay "since boot")
                ld   b, ANIM_TRACE_LEN         ; RECLAIM-D: a 10-B loop (was the 13-B LDIR)
.trc:           ld   (hl), $FF
                inc  l                         ; (one page: trace_log ASSERTs it)
                djnz .trc
    ENDIF
                xor  a
    IF ANIM_TRACE_ON
                ld   (ANIM_TRACE_IDX), a
    ENDIF
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (CUR_ROOM), a
                ld   (TURN_PHASE), a
                ld   (NEED_RELEASE), a
                ; UX1 (ux_polish.md §6 / §7): the first-book hint survives the D0 grate only (tt_reset ->
                ; start_game while GAME_STATE is still GS_PLAYING; a menu START comes from GS_SELECT)
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                ld   a, (UX_FL)
                jr   z, .kh
                xor  a
.kh:            and  1 << UXF_HINT_B
                ld   c, a
                xor  a
                ld   hl, ITEM_RAM              ; 3E-T3: bag, worn,
                ld   b, ITEM_RAM_LEN           ; hunger, quick slots, ST1_CNT, ST2_CNT, UX_RAM := 0 (95 B, one
.ir:            ld   (hl), a                   ; page: 9 B, ~2.2k T; level changes keep it)
                inc  l
                djnz .ir
                ld   a, c
                ld   (UX_FL), a                ; UX1: NEW_MASK 0, MPF_T 0, the hint kept or cleared
                dec  b                         ; (B = 0 after the djnz)
                ld   a, b
                ld   (LAST_PICK), a            ; $FF = none
                ld   hl, level_reset_new      ; bank 3 (pf_prep is bank-3 data):
                call far3                      ; per-level state + the entity table (+ hero 3D state)
                ; --- hero, slot 0 ---
                ld   ix, P_ENTITIES
                ld   a, (HERO_KIND)
                ld   (ix+E_KIND), a
                ld   (ix+E_ROOM), ROOM_A
                ld   (ix+E_FLAGS), EF_ACTIVE | EF_PLAYER
                ld   (ix+E_X), HERO_START_COL
                KFL    KT_BH
                ld   b, a
                ld   a, HERO_START_S * STOREY_ROWS + STOREY_AIR
                sub  b                         ; 9s+8-h
                ld   (ix+E_Y), a
                ld   hl, init_ent_common       ; bank 3 (shared with spawn_one /
                call far3                      ; level_populate; IX passes in)
                ld   hl, hero_st_init          ; C3-2 (intent7.asm, bank 7; B0CODE: was a
                call far7                      ; direct call, +3 B / ~0.25k T once a game)
                ld   hl, kit_add               ; 3E-T11: worn + bag start kit (R6;
                call far6                      ; E_POT = its potions via pot_sync)
                xor  a                         ; 3F-T9: the spawn queue is garbage at boot
                ld   (SPQ_K), a                ; (end_turn empties it after that)
                ld   hl, (seed_value)          ; (D3-11: a PROTO fixture game rewrites it)          ; generated: the master seed
                ld   a, (seed_fixed)
                or   a
                jr   nz, .ms
                ld   hl, (SYS_FRAMES)          ; frames since boot at the choice
                ld   de, (MENU_SPIN)           ; C3-6: + the menu's busy-wait count
                add  hl, de
                ld   a, r                      ; + R (B3B-12 review): little extra entropy
                xor  h                         ; (the select loop is HALT-synchronised),
                ld   h, a                      ; the 20 ms keypress frame is the real source
.ms:            ld   (MASTER_SEED), hl
                ret
