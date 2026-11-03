;==============================================================================
; data7.asm — MEM-RECLAIM w2b: read-only tables of the bank-7 cold code
; (bank7.asm keeps no data), assembled in bank 7 right after the tilesets
; (main.asm, TSET_BASE block; tape + gfx_integrity cover them).
;==============================================================================
tr_ink7:        TRAP_INKS                      ; trap7 tr_ink: the plate / hero flash attr by type (item_defs.asm)

; pi_rects — boot7 panel_init7: the static panel's attr rects, 4 B each: attr, col, row, cols (rows = 1);
; $FF ends it. Info line fields (game.md §3.4: name chars 0-15, numbers 16-27, notes 28-41 = cols 0-11 /
; 12-20 / 21-31), the depth cell row 19 (key icon until 3F: none -> black), the level digit at (31, 19),
; row 21 bar frames' attrs (the labels' cells HP_LBL_COL / MP_LBL_COL / FOOD_LBL_COL are outside: glyph8),
; row 22 the log (cols 0..LOG_COLS-1; the gear cells: pblit).
pi_rects:       DB   ATTR_INFO_NAME, 0, INFO_ROW, INFO_NUM_COL
                DB   ATTR_INFO_NUM, INFO_NUM_COL, INFO_ROW, INFO_NOTE_COL - INFO_NUM_COL
                DB   ATTR_INFO_NOTE, INFO_NOTE_COL, INFO_ROW, ROOM_COLS - INFO_NOTE_COL
                DB   0, DEPTH_COL, ICON_ROW + 1, 2
                DB   ATTR_LVL, LVL_COL, ICON_ROW + 1, 1
                DB   ATTR_P_HP, HP_BAR_COL, STAT_ROW, HP_NUM_COL + 2 - HP_BAR_COL
                DB   ATTR_P_MP, MP_BAR_COL, STAT_ROW, MP_NUM_COL + 2 - MP_BAR_COL
                DB   ATTR_P_FED, FOOD_BAR_COL, STAT_ROW, GEAR_COL - FOOD_BAR_COL
                DB   ATTR_LOG_OLD, 0, LOG_ROW, LOG_COLS
                DB   $FF
                ASSERT HP_LBL_COL < HP_BAR_COL && HP_NUM_COL + 2 <= MP_LBL_COL && MP_LBL_COL < MP_BAR_COL
                ASSERT MP_NUM_COL + 2 <= FOOD_LBL_COL && FOOD_LBL_COL < FOOD_BAR_COL && LOG_COLS <= GEAR_COL
                ASSERT ATTR_INFO_NAME != $FF && ATTR_LOG_OLD != $FF

; tr_fx — trap7's DART impact template (fx_start descriptor, FXD_LEN; read-only:
; tests/gfx_integrity.py compares this block after play):
; hidden until the impact, own attr, COL / ROW / DELAY patched in MSG_BUF.
tr_fx:          DB   FX_NONE, FX_NONE, FID_arrow_hit, FID_arrow_hit
                DB   0, 0, 0, 0, 0, PF_IMPT
                DB   1, 0, 0, 0, 0, 0          ; 1 segment of 0 cells
                ASSERT $ - tr_fx == FXD_LEN && FXD_IMPT == 9 && FXD_NSEG == 10 && FXD_IMPA == 2
                ASSERT FXD_LEN <= 32           ; MSG_BUF

                ASSERT T_AIR == 0 && T_GRATE_SHUT != T_GRATE

; bxp_d — boss7 grate_open: golden-boss XP delta by depth - 1 = game.md §4.1 golden XP - the base kind's KXP
; (bank 3's death path adds kx_tab KXP after grate_open). D4 Ogre / D7 Death Knight / D8 Archmage are not
; golden (their kx_tab row is already the §4.1 value): 0.
bxp_d:          DB   17, 26, 36, 0, 53, 70, 0, 0
                ASSERT $ - bxp_d == LEVELS && ((bxp_d - 1) >> 8) == ((bxp_d + LEVELS - 1) >> 8)
                ; delta + the base KXP == game.md §4.1's golden XP (Goblin King 20, Spider Queen 30, Vampire Lord 45, Pharaoh 65, High Necro 80)
                ASSERT 17 + KXP_GOBLIN == 20 && 26 + KXP_SPIDER == 30 && 36 + KXP_VAMPIRE == 45
                ASSERT 53 + KXP_MUMMY == 65 && 70 + KXP_NECRO == 80
