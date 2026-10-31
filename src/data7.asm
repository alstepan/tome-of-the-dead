;==============================================================================
; data7.asm — MEM-RECLAIM w2b: read-only tables of the bank-7 cold code
; (bank7.asm keeps no data), assembled in bank 7 right after the tilesets
; (main.asm, TSET_BASE block; tape + gfx_integrity cover them).
;==============================================================================
tr_ink7:        TRAP_INKS                      ; trap7 tr_ink: the plate / hero flash attr by type (item_defs.asm)

; tr_fx — trap7's DART impact template (fx_start descriptor, FXD_LEN; read-only:
; tests/gfx_integrity.py compares this block after play):
; hidden until the impact, own attr, COL / ROW / DELAY patched in MSG_BUF.
tr_fx:          DB   FX_NONE, FX_NONE, FID_arrow_hit, FID_arrow_hit
                DB   0, 0, 0, 0, 0, PF_IMPT
                DB   1, 0, 0, 0, 0, 0          ; 1 segment of 0 cells
                ASSERT $ - tr_fx == FXD_LEN && FXD_IMPT == 9 && FXD_NSEG == 10 && FXD_IMPA == 2
                ASSERT FXD_LEN <= 32           ; MSG_BUF

; glow7 — boss7 grate_open: bank-3 glow_ids (build_room_map) again, by depth - 1 (bank 7 cannot read bank 3)
glow7:          DB   TS1_GLOW_F1_R0C0, TS2_GLOW_F1_R0C0, TS3_GLOW_F1_R0C0, TS4_GLOW_F1_R0C0
                DB   TS5_GLOW_F1_R0C0, TS6_GLOW_F1_R0C0, TS7_GLOW_F1_R0C0, TS8_GLOW_F1_R0C0
                ASSERT $ - glow7 == LEVELS && ((glow7 - 1) >> 8) == ((glow7 + LEVELS - 1) >> 8)
                ASSERT T_AIR == 0 && T_GRATE_SHUT != T_GRATE

; bxp_d — boss7 grate_open: golden-boss XP delta by depth - 1 = game.md §4.1 golden XP - the base kind's KXP
; (bank 3's death path adds kx_tab KXP after grate_open). D4 Ogre / D7 Death Knight / D8 Archmage are not
; golden (their kx_tab row is already the §4.1 value): 0.
bxp_d:          DB   17, 26, 36, 0, 53, 70, 0, 0
                ASSERT $ - bxp_d == LEVELS && ((bxp_d - 1) >> 8) == ((bxp_d + LEVELS - 1) >> 8)
                ; delta + the base KXP == game.md §4.1's golden XP (Goblin King 20, Spider Queen 30, Vampire Lord 45, Pharaoh 65, High Necro 80)
                ASSERT 17 + KXP_GOBLIN == 20 && 26 + KXP_SPIDER == 30 && 36 + KXP_VAMPIRE == 45
                ASSERT 53 + KXP_MUMMY == 65 && 70 + KXP_NECRO == 80
