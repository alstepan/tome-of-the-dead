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
