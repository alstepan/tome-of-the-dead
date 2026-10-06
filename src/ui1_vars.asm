;==============================================================================
; ui1_vars — every bank-1 UI variable in one block (C3-6 review: tests/game.py
; #50 masks exactly ui1_vars..ui1_vars_end when it compares bank 1 to the .sna).
;==============================================================================
ui1_vars:
menu_sel:       DB   0                         ; cursor item 0..3
menu_hero:      DB   K_KNIGHT                  ; HERO choice (persists between games)
menu_sc_old:    DB   0
torch_t:        DB   1
torch_k:        DB   0
pv_i:           DB   0
pv_c:           DB   0
pv_a:           DB   0
mk_buf:         DS   44
rd_i:           DB   0
rd_new:         DS   10
pause_sel:      DB   0
pc_dir:         DB   0
pc_cur:         DW   PAUSE_SAVE
mf_row:         DB   0                         ; (mf_row) = C col, (mf_row + 1) = B row
mf_rowh:        DB   0
mf_attr:        DB   $47
mf_lattr:       DB   $47
mf_lt:          DB   $47
mf_split:       DB   0
mf_bc:          DW   0
INFO_TX:        DB   0                         ; info1: the id printed (selects the live numbers)
ui1_vars_end:
                ASSERT mf_rowh == mf_row + 1
