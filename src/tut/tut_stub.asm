;==============================================================================
; tut_stub.asm — TUT0-T1: the two low-RAM trampolines into the D0 blob (bank 4).
; Assembled DISP'd at check_paging (main.asm "TUT0 STUBS": check_paging ..
; sel_tab, the tape-path-only paging check + its message, dead after boot) and
; copied there by the INSTR overlay's common exit (instr_ovl.asm in_tut) —
; 0 resident bytes. conventions.md "TUT0 boot stubs".
;
; ts_choice — es_go's target (enter_select: `jp start_game` patched while the
;   tutorial is offered). In: C = menu_run's hero kind. blob_choice returns
;   C = the hero for start_game (or never returns).
; ts_turn — pl_et's target (play_loop: `ld hl, end_turn` patched while D0
;   runs; entered by far7, so bank 7 is paged): blob_turn with A = 1, end_turn,
;   blob_turn with A = 0; farb gives bank 7 back after each blob call.
;   Clobbers: as end_turn + the blob (far7's caller keeps nothing anyway).
;   Cost: 2 x farb (~0.45k T) + the blob's work, on turn ticks only.
; ts_icon — TUT0-R2: pi_ic's target (intent_tick: `ld hl, intent_icon7` patched
;   while D0 runs; entered by far7 = bank 7 paged, D / E = STICK / pressed pass
;   in): the real intent_icon7 first, then blob_icon (the icon tour) via farb,
;   which gives bank 7 back. Clobbers: A, BC, DE, HL (+ the blob's: all but IX / IY;
;   intent_tick's caller keeps nothing). Cost: 1 farb (~0.25k T) + blob_icon,
;   ICON MODE ticks only (play frozen).
;==============================================================================
ts_choice:
                ld   a, c                      ; farb passes A, not BC
                ld   hl, BLOB_CHOICE
                ld   c, BANK_BLOB
                call farb                      ; C = hero
                jp   start_game
ts_turn:
                ld   a, 1
                call .far                      ; before end_turn
                call end_turn                  ; bank 7 (far7 paged it; farb restored it)
                xor  a                         ; after
.far:           ld   hl, BLOB_TURN
.farc:          ld   c, BANK_BLOB
                jp   farb
ts_icon:
                call intent_icon7              ; bank 7 (far7 paged it): the cursor / FIRE / exit
                ld   hl, BLOB_ICON
                jr   ts_turn.farc
