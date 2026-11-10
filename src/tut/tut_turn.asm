;==============================================================================
; tut_turn.asm — TUT0-T7: the D0 turn engine (blob, bank 4).
; docs/design/tut0_split.md "T7"; spec docs/design/tutorial_d0.md §3 (beats),
; §4.3-4.4 (mentor, tokens, pointer), §5 (reset). Beat table: tut_beats.asm.
; Entered only by blob_turn (ts_turn: A = 1 before end_turn, A = 0 after).
; Blob rules (tut_blob.asm): every resident routine that pages $C000 goes
; through farb with C = BANK_BLOB (farb4) or is a save-shadow / restore_page
; helper (rect_repaint, copy_virt_keep, log_push / pmark_rect page nothing).
; No writable data in the blob: the state is TUT_RAM (PF_RAM's free middle,
; below), test-observable.
;
; Design notes
; - <= 1 line group a turn. TUT0-F2 (user A + B): only groups flagged in the
;   beat table (TUT_BF_H0/H1/H2, tut_tail_hold; + L29/L28, the first mercy) HOLD
;   (tt_hold): whole frames — menu_frame (busy-waits SYS_FRAMES: the ISR / music
;   keep running; its select_tick is the harness probe, hit once per frame),
;   resync_tick, panel_tick (draws the queued lines), present. Once the lines
;   are drawn the log rows pulse BRIGHT and a blinking prompt (the triangle +
;   FIRE / the FIRE key's 2-char name) sits at the end of row 20 (the info
;   line: the log rows 22-23 have no free cell, a line fills cols 0-23 and
;   cols 24-31 are the worn gear); every key up, then the first key DOWN
;   dismisses it at once (rows / row 20 restored), then every key up again
;   before play resumes (the key is swallowed: no turn starts from it).
;   TV_HOLD = 1 meanwhile. Ends with resync_tick (not an overrun).
; - The talk pose is drawn AT ONCE: a shown group sets TALK1 / TALK2 now
;   (glyph copy + queued restore); a hold renders it before its first frame,
;   an unheld group's next tick render draws it.
; - Blink: FADE at the old spot (turn n), FADE at the new spot (n + 1), the pose
;   (n + 2). A pose / spot change is skipped in a tick already in its 2nd frame
;   (retried next turn) unless a group is shown (the hold resyncs anyway).
;==============================================================================
TUT_RAM         EQU PF_RAM + $90        ; $5E90: PF_RAM's free middle ($5E7A..$5EDF)
TV_BEAT         EQU TUT_RAM + 0         ; current beat 0..15            (test-observable)
TV_STAGE        EQU TUT_RAM + 1         ; ST_*                          (test-observable)
TV_TI           EQU TUT_RAM + 2         ; tail pair index (ST_TAIL)
TV_XP           EQU TUT_RAM + 3         ; B14 extras pending: 1 = L48 check, 2 = L52 check
TV_NAG          EQU TUT_RAM + 4         ; R2 nudge: off-task WAIT turns of this beat (saturates at NUDGE_T2 + 1; not counted in B6 / B10-B12, see tt_repeat)
TV_FL           EQU TUT_RAM + 5         ; TFB_* bits
TV_PTR          EQU TUT_RAM + 6         ; the flashing pointer rect id ($FF none)
TV_SHOWN        EQU TUT_RAM + 7         ; a group was shown this turn
TV_ROOM         EQU TUT_RAM + 8         ; CUR_ROOM at the last run
TV_SPOT         EQU TUT_RAM + 9         ; the mentor's spot                (test-observable)
TV_STAMP        EQU TUT_RAM + 10        ; 1 = his ids are in ROOM_MAP
TV_IMG          EQU TUT_RAM + 11        ; image in TILE_GLYPHS (2 x frame + left; $FF none)
TV_HFC          EQU TUT_RAM + 12        ; tt_hold: the prompt's frame counter (TUT0-F2)
TV_HST          EQU TUT_RAM + 13        ; tt_hold: bit 0 log rows BRIGHT-toggled, bit 1 triangle drawn
TUT_BLINK_FR    EQU 4                   ; frames per blink stage = 2 ticks (spec §4.2)
TV_PH           EQU TUT_RAM + 14        ; turn parity (IDLE1/2, TALK1/2)
TV_HOLD         EQU TUT_RAM + 15        ; 1 while a group holds (test-observable: tap a key)
TV_MIR          EQU TUT_RAM + 16        ; tut_glyphs / tt_ptr scratch
TV_COL          EQU TUT_RAM + 17
TV_GOB          EQU TUT_RAM + 18        ; the Goblin's slot in CUR_ROOM ($FF none)
TV_CUR          EQU TUT_RAM + 19        ; 7 B: hero x, y, CUR_ROOM, HP, MP, FOOD, Goblin HP ($FF none)
TV_PRV          EQU TUT_RAM + 26        ; 7 B: the same at the previous turn
TV_SNAP         EQU 7
TV_BUF          EQU TUT_RAM + 33        ; 34 B: the expanded line (LOG_MAX + 0 + 1); tt_hold: the prompt name
TV_HQ           EQU TUT_RAM + 67        ; 1 = this turn's shown group holds (tt_group_h)  (test-observable)
TV_TRI          EQU TUT_RAM + 68        ; tt_hold: the triangle's col (right-aligned prompt)
TV_HA           EQU TUT_RAM + 69        ; tt_hold: 6 B, row 20's attrs under the prompt (restored)
TV_ISLOT        EQU TV_HA + HP_W        ; TUT0-R2 icon tour: the cursor slot of this session ($FF none)
TV_IREST        EQU TV_ISLOT + 1        ;   hook calls resting on it (saturates at REST_T)
TV_ISAID        EQU TV_ISLOT + 2        ;   2 B: bit 0 entry pair said, bit s+1 slot s's line said,
                                        ;   bits 11 / 12 the B3 / B9 bag target held once (test-observable)
TUT_RAM_END     EQU TV_ISAID + 2
TUT_RAM_LEN     EQU TUT_RAM_END - TUT_RAM
                ASSERT TUT_RAM >= ABIL_TGT + 2 + 15 && TUT_RAM_END <= PF_ROWF   ; KIT_LIST (15 B, kit builds) below
TFB_MERCY       EQU 0                   ; mercy healed this turn (A = 1): its group next (A = 0)
TFB_MSEEN       EQU 1                   ; the first mercy said L51
TFB_ALT         EQU 2                   ; B9 entered unpoisoned: L32, advance when the Cure is held
TFB_GRATE       EQU 3                   ; open the grate after this turn's hold (B14 G3 shown)
TFB_RESHOW      EQU 4                   ; R2 nudge: L75 said, the instruction group next turn
TFB_L76         EQU 5                   ; R2: L76 (a lesson left undone in A) said, once per D0

ST_PRE          EQU 0                   ; FH_IMPATIENT: L53 first
ST_G0           EQU 1
ST_G2P          EQU 2                   ; TUT_BF_G2PRE: G2 the turn after G0
ST_WAIT         EQU 3
ST_G2           EQU 4
ST_TAIL         EQU 5

TB_ROOM         EQU 0                   ; beat record fields (TUT_TB_STRIDE 16)
TB_TRIG         EQU 1
TB_P2           EQU 2
TB_P3           EQU 3
TB_SPOT         EQU 4
TB_POSE         EQU 5
TB_G0           EQU 6
TB_G1           EQU 8
TB_G2           EQU 10
TB_R0           EQU 12
TB_R1           EQU 13
TB_FH           EQU 14
TB_FL           EQU 15
TBF_FIRST_BIT   EQU 0
TBF_TAIL_BIT    EQU 1
TBF_G2PRE_BIT   EQU 2
TBF_GRATE_BIT   EQU 3
TBF_H0_BIT      EQU 4
TBF_H1_BIT      EQU 5
TBF_H2_BIT      EQU 6
                ASSERT TUT_BF_H0 == 1 << TBF_H0_BIT && TUT_BF_H1 == 1 << TBF_H1_BIT && TUT_BF_H2 == 1 << TBF_H2_BIT
                ASSERT TUT_BF_FIRST == 1 << TBF_FIRST_BIT && TUT_BF_TAIL == 1 << TBF_TAIL_BIT
                ASSERT TUT_BF_G2PRE == 1 << TBF_G2PRE_BIT && TUT_BF_GRATE == 1 << TBF_GRATE_BIT

MERCY_HP        EQU 8                   ; spec §3; Mage max HP 16 (game.md §4) >= 12: maxHP - 4 not needed
NUDGE_T         EQU 12                  ; R2 s13.5: L75 at 12 off-task turns, again at 36, then silent
NUDGE_T2        EQU 36
REST_T          EQU 12                  ; R2 s13.3: icon-hook calls resting on one slot -> its line
REPEAT_COLS     EQU 6                   ; "within 4 cols" of his box: |x - col| <= 6
TRAP_PASS_X     EQU 17                  ; B8: unpoisoned at x >= 17 = the dart was passed
TUT_B6          EQU 6                   ; the shaft walk (A: x 17 -> 5, ~12 turns)
TUT_B10         EQU 10                  ; the door walk (B: ~20 turns) .. B12 (the fight): contiguous, see tt_repeat
TUT_B11         EQU 11
TUT_B12         EQU 12
TUT_B14         EQU 14
TUT_B15         EQU 15
TUT_EDGE_BC     EQU 3                   ; EDGE_TAB index of the B-C door (tut0_level.asm: LINK|DOOR|LOCK)
TUT_EG_LOCK_BIT EQU 3
STAND_Y0        EQU FLOOR_ROW0 - BH_K_KNIGHT   ; hero E_Y standing on storey 0 / 1
STAND_Y1        EQU FLOOR_ROW1 - BH_K_KNIGHT
TUT_CTL_N       EQU 5                   ; control bytes 1..5 = U D L R F
                ASSERT EG_LOCK == 1 << TUT_EG_LOCK_BIT && BH_K_WIZARD == BH_K_KNIGHT
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1 && JM_KEYS == 0 && BANK_SRC_LO == BANK_UI1
                ASSERT TUT_TB_STRIDE == 16 && QS_POTION < QS_COUNT && P_ENT_STRIDE == 32
                ASSERT ((P_ENTITIES + E_HP) >> 8) == ((P_ENTITIES + E_FLAGS) >> 8) && E_MAXHP == E_HP + 1
                ASSERT (ST_FLAGS & $FF) + P_MAX_ENT <= $100 && (ST_T1 & $FF) + P_MAX_ENT <= $100

;------------------------------------------------------------------------------
; blob_turn — A = 1 (before end_turn): EX_LEVEL -> the sandbox reset (never
; returns; end_turn must not run level_descend with the blob live); else
; mercy (HP <= MERCY_HP, not dying: HP := max, its lines next). A = 0 (after
; end_turn): the beat engine (tt_after). Clobbers: all.
; T: A = 1 ~0.15k; A = 0 ~2-4k typical, + a group ~2k + glyphs 6-10k +
; rect_repaint ~2.5k (the 18-cell restore lands in the next render); a held
; group's frames are not tick work (resynced).
;------------------------------------------------------------------------------
blob_turn:
                or   a
                jr   z, tt_after
                ld   a, (EXIT_KIND)
                cp   EX_LEVEL
                jr   z, tt_reset
                cp   EX_DOWN                   ; room C is cell 5 (middle grid row): try_climb
                jr   nz, .nx                   ; makes the open grate's step EX_DOWN to cell 8
                ld   a, (CUR_ROOM)             ; (the level exit is only "past the grid");
                cp   TUT0_ROOM_C               ; C has no down-exit, so a DOWN exit from C
                jr   z, tt_reset               ; IS the grate step
.nx:            ld   a, (EXIT_KIND)
                or   a                         ; TUT0-F2 review 1: the Goblin's parked slot in C
                jr   z, tt_mercy               ; survives A -> B -> A (lp_bank, lpop3.asm .ev, frees
                ld   a, (EXIT_DEST)            ; every parked slot whose room is not the old one,
                cp   TUT0_ROOM_C               ; EXIT_DEST or TRK_PREV; tut_d0's TRK_PREV preset
                jr   z, tt_mercy               ; covers the first exit only): while B11 is not
                ld   a, (TV_BEAT)              ; passed, every exit not into C claims C as the
                cp   TUT_B11 + 1               ; last room left (do_exit .in rewrites TRK_PREV
                jr   nc, tt_mercy              ; after lp_bank; LF_UNIQUE: no trickle reads it)
                ld   a, TUT0_ROOM_C
                ld   (TRK_PREV), a
                ; fall through
; tt_mercy — HP <= MERCY_HP and not dying: HP := max, its group next (tt_after).
; A = 1 (before end_turn) and, TUT0-F2 review 2, A = 0 (after: do_exit's fall /
; arrival damage lands between the two). Clobbers: A, HL.
tt_mercy:
                ld   hl, P_ENTITIES + E_FLAGS
                bit  EF_DYING_BIT, (hl)
                ret  nz                        ; the normal death flow (spec §5.3)
                ld   l, (P_ENTITIES + E_HP) & $FF
                ld   a, (hl)
                cp   MERCY_HP + 1
                ret  nc
                inc  l
                ld   a, (hl)                   ; MAXHP
                dec  l
                ld   (hl), a
                ld   hl, TV_FL
                set  TFB_MERCY, (hl)
                ret
                ; TUT0-F2 review 4: the EX_DOWN-from-C = grate-step rule above needs C in the
                ; grid's middle row with no down-exit of its own
                ASSERT TUT0_ROOM_C / GRID_W == 1 && TUT0_ROOM_C < GRID_CELLS
                ASSERT ({b tut0_room_desc + TUT0_ROOM_C * RD_STRIDE + RD_EXITS} & RDX_D) == 0

; tt_reset — the D0 grate step (spec §5.2): the three SMC operands back, then
; exactly a menu START (start_game: new game, seed, D1; its pool overwrites
; the blob), as Quit does (bank7.asm pause_run7).
tt_reset:
                ld   hl, start_game
                ld   (es_go + 1), hl           ; SMC target (main.asm enter_select): no more offers
                ld   hl, end_turn
                ld   (pl_et + 1), hl           ; SMC target (main.asm play_loop)
                ld   hl, intent_icon7
                ld   (pi_ic + 1), hl           ; SMC target (io.asm intent_tick, TUT0-R2)
                call show_bank5
                ld   a, (HERO_KIND)
                ld   c, a
                ld   sp, WORKSTORE_TOP
                jp   start_game

;------------------------------------------------------------------------------
; tt_after — A = 0: snapshot, room / Goblin rules, the turn's group (mercy
; first, else the beat machine, else repeat / nag), the mentor, the hold, the
; grate. Clobbers: all.
;------------------------------------------------------------------------------
tt_after:
                ld   a, TUT_NONE               ; R2: every turn ends an icon session (blob_icon)
                ld   (TV_ISLOT), a
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                ret  nz                        ; died this turn
                xor  a
                ld   (TV_SHOWN), a
                ld   (TV_HQ), a
                call tt_mercy
                call tt_snap
                call tt_glob
                ld   hl, TV_FL
                bit  TFB_MERCY, (hl)
                jr   z, .sm
                res  TFB_MERCY, (hl)
                ld   e, TUT_NONE
                bit  TFB_MSEEN, (hl)
                jr   nz, .m1
                set  TFB_MSEEN, (hl)
                ld   e, TL_L51
                ld   a, 1                      ; the first mercy (L51) holds, later ones scroll
                ld   (TV_HQ), a
.m1:            ld   d, TL_L50
                ld   c, TUT_NONE
                call tt_group
                jr   .mn
.sm:            call tt_machine
                call tt_repeat
.mn:            ld   a, (TV_SHOWN)             ; TUT0-R2 budget: a hold follows -> the mentor's
                ld   hl, TV_HQ                 ; talk pose (glyphs + stamp, ~10-17k) and the
                and  (hl)                      ; pointer (+ the panel drain) are done inside the
                jr   nz, .hq                   ; hold (tt_holdm): frames, not this tick's work
                call tt_mentor                 ; (B5 G0 was 131.8k, the B5 eat 127k before it)
                call tt_ptr_re
.hq:            ld   hl, TV_CUR
                ld   de, TV_PRV
                ld   bc, TV_SNAP
                ldir
                ld   a, (TV_SHOWN)
                or   a
                ret  z
                ld   a, (TV_HQ)
                or   a
                call nz, tt_holdm
                ld   hl, TV_FL
                bit  TFB_GRATE, (hl)
                ret  z
                res  TFB_GRATE, (hl)
                ld   hl, grate_open.op         ; bank 7: flag, T_GRATE + glow (in C), the line
                jp   far7

;------------------------------------------------------------------------------
; tt_init — tut_d0, after level_show: the state, B0's G0 (pushed, NOT held:
; the player is idle at arrival and nothing scrolls it away until he acts),
; the mentor at A1 in TALK. Clobbers: all.
;------------------------------------------------------------------------------
tt_init:
                ld   hl, TUT_RAM
                ld   de, TUT_RAM + 1
                ld   bc, TUT_RAM_LEN - 1
                ld   (hl), 0
                ldir
                ld   a, TUT_NONE
                ld   (TV_PTR), a
                ld   (TV_IMG), a
                ld   (TV_ISLOT), a
                ld   a, (CUR_ROOM)
                ld   (TV_ROOM), a
                ld   a, ST_G0
                ld   (TV_STAGE), a
                ASSERT TUT0_SP_A1 == 0         ; TV_SPOT 0 (zeroed)
                call tt_snap
                ld   hl, TV_CUR
                ld   de, TV_PRV
                ld   bc, TV_SNAP
                ldir
                call tt_machine
                call tt_mentor
                xor  a
                ld   (TV_SHOWN), a
                ret

;------------------------------------------------------------------------------
; tt_snap — TV_GOB + TV_CUR. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
tt_snap:
                ld   hl, P_ENTITIES + P_ENT_STRIDE
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
                ld   c, TUT_NONE
.l:             ld   a, (hl)                   ; E_KIND
                cp   K_GOBLIN
                jr   nz, .n
                inc  hl
                inc  hl
                ld   a, (hl)                   ; E_FLAGS
                dec  hl
                dec  hl
                and  EF_ACTIVE | EF_DYING
                dec  a
                jr   nz, .n                    ; active (= in CUR_ROOM), not dying
                ld   a, P_MAX_ENT
                sub  b
                ld   (TV_GOB), a
                ld   de, E_HP
                add  hl, de
                ld   c, (hl)
                jr   .g
.n:             add  hl, de
                djnz .l
                ld   a, c
                ld   (TV_GOB), a
.g:             ld   a, c
                ld   (TV_CUR + 6), a
                ld   hl, P_ENTITIES + E_X
                ld   de, TV_CUR
                ldi
                ldi                            ; x, y
                ld   a, (CUR_ROOM)
                ld   (de), a
                inc  de
                ld   a, (P_ENTITIES + E_HP)
                ld   (de), a
                inc  de
                ld   a, (MP)
                ld   (de), a
                inc  de
                ld   a, (FOOD)
                ld   (de), a
                ret
                ASSERT E_KIND == 0 && E_FLAGS == 2 && E_Y == E_X + 1 && EF_ACTIVE == 1

;------------------------------------------------------------------------------
; tt_glob — a room change: the map was rebuilt (re-stamp), entering B finds
; the key (the B-C lock off: the engine has no D0 key logic; door_open reads
; the edge only), the overtaken-beat jump (unless the current beat's own
; ROOM trigger takes it); the Goblin's death jumps to B14; the Goblin hold.
; Clobbers: all but IY.
;------------------------------------------------------------------------------
tt_glob:
                ld   a, (CUR_ROOM)
                ld   hl, TV_ROOM
                cp   (hl)
                jr   z, .dead
                ld   (hl), a
                ld   c, a
                xor  a
                ld   (TV_STAMP), a
                ld   a, c
                cp   TUT0_ROOM_B
                jr   nz, .nb
                ld   hl, EDGE_TAB + TUT_EDGE_BC
                res  TUT_EG_LOCK_BIT, (hl)
.nb:            call tt_rec
                ld   a, (ix+TB_TRIG)
                cp   TUT_TK_ROOM
                jr   nz, .ov
                ld   a, (ix+TB_P2)
                cp   c
                jr   z, .dead
.ov:            ld   ix, tut_beats
                ld   de, TUT_TB_STRIDE
                ld   b, 0
.f:             ld   a, (ix+TB_ROOM)
                cp   c
                jr   nz, .fn
                bit  TBF_FIRST_BIT, (ix+TB_FL)
                jr   nz, .ff
.fn:            add  ix, de
                inc  b
                ld   a, b
                cp   TUT_B15 + 1
                jr   c, .f
                jr   .dead
.ff:            ld   a, (TV_BEAT)
                cp   b
                jr   nc, .dead                 ; not later than the current beat
                ld   e, ST_PRE
                sub  2                         ; R2 s13.5: entering B with B2..B5 open (book /
                cp   4                         ; ladder / pear skipped): L76 once per D0, before
                jr   nc, .im                   ; B7's G0 (the ST_PRE mechanism of L53)
                ld   a, c
                cp   TUT0_ROOM_B
                jr   nz, .im
                ld   hl, TV_FL
                bit  TFB_L76, (hl)
                set  TFB_L76, (hl)             ; (SET keeps the flags)
                jr   z, .st
.im:            ld   a, (ix+TB_FH)
                cp   TUT_FH_IMPATIENT
                jr   z, .st
                ld   e, ST_G0
.st:            ld   a, b
                ld   (TV_BEAT), a
                ld   a, e
                ld   (TV_STAGE), a
                call tt_nbeat
.dead:          ld   hl, ST1_KILLS             ; D0's one monster: any kill = the Goblin died
                ld   a, (hl)
                inc  hl
                or   (hl)
                jr   z, .hold
                ld   a, (TV_BEAT)
                cp   TUT_B14
                jr   nc, .hold
                ld   a, TUT_B14
                ld   (TV_BEAT), a
                ld   a, ST_G0
                ld   (TV_STAGE), a
                call tt_nbeat
.hold:          ld   a, (TV_BEAT)              ; spec §3 Hold: ASLEEP 15 while HP = max
                cp   TUT_B11 + 1               ; and B11 not passed
                ret  nc
                call tt_gobp
                ret  z
                ld   de, E_HP
                add  hl, de
                ld   a, (hl)
                inc  hl
                cp   (hl)
                ret  nz
                ld   a, (TV_GOB)
                ld   h, ST_FLAGS >> 8
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   (hl), HOLD_ASLEEP
                ld   a, l
                add  a, (ST_T1 - ST_FLAGS) & $FF
                ld   l, a
                ld   h, ST_T1 >> 8
                ld   (hl), TUT_GOB_SLEEP << 4
                ret

; tt_nbeat — a new current beat: nudge count reset, the B9 alternative and a
; pending nudge re-show off, pointer off.
tt_nbeat:
                xor  a
                ld   (TV_NAG), a
                ld   hl, TV_FL
                res  TFB_ALT, (hl)
                res  TFB_RESHOW, (hl)
                ; fall through
; tt_ptr_clr — the flashing pointer off. Clobbers: A, BC, DE, HL.
tt_ptr_clr:
                ld   a, (TV_PTR)
                cp   TUT_NONE
                ret  z
                ld   hl, TV_PTR
                ld   (hl), TUT_NONE
                or   a                         ; CF = 0: clear
                jr   tt_ptr
; tt_ptr_re — TUT0-F2 (user playtest: pointer colours): with a pointer up, the
; panel's pending items that rewrite attrs (a quick-slot / icon redraw, e.g. the
; pear picked up under the FOOD pointer; the status icons; the hunger word) are
; drawn now, as a 1st-frame panel_tick would but with the log and the info line
; held back (their PD bits masked off, then put back: they stay queued), one
; item per panel_step (<= TT_PDRAIN); then FLASH is OR'ed back over the rect
; (idempotent): every cell keeps the panel's own colour, the pointer survives.
; Clobbers: all but IX.   ~0.2k idle; + ~2.5-4.5k per item drawn + ~1-3k the rect
tt_ptr_re:
                ld   a, (TV_PTR)
                cp   TUT_NONE
                ret  z
                ld   hl, PANEL_DIRTY
                ld   a, (hl)
                and  PD_LOG | PD_INFO
                ld   (TV_MIR), a               ; (tut_glyphs' scratch: free here)
                xor  (hl)
                ld   (hl), a                   ; LOG / INFO off
                ld   b, TT_PDRAIN
.d:             push bc
                ld   c, 0                      ; any item (icon_poll + the quick slots too)
                call panel_step
                pop  bc
                ld   a, (PANEL_DIRTY)
                or   a
                jr   z, .s
                djnz .d
.s:             ld   hl, TV_MIR
                ld   a, (PANEL_DIRTY)
                or   (hl)
                ld   (PANEL_DIRTY), a          ; LOG / INFO back
                ld   a, (TV_PTR)
                scf
                jr   tt_ptr
TT_PDRAIN       EQU 12                  ; > the 10 icon slots + HP + MP + FOOD
; tt_ptr_set — A = rect id ($FF none): FLASH on. Clobbers: A, BC, DE, HL.
tt_ptr_set:
                ld   (TV_PTR), a
                cp   TUT_NONE
                ret  z
                scf
;------------------------------------------------------------------------------
; tt_ptr — A = tut_rects id, CF = 1 set / 0 clear the FLASH bit of its cells
; (bank-5 attrs; only bit 7 changes, so a clear gives back exactly what the panel
; last drew — a value rewritten under the pointer stays the panel's; panel rows
; have no attr shadow: pmark_rect -> present copies them to screen 2; a cell
; TUT0-F3: a BLANK cell (8 bitmap bytes 0, tt_cellpx) never gets FLASH, and a clear /
; set on it drops bit 7 (FLASH is only ever used by these pointers): FLASH would swap
; ink / paper into a solid block),
; pmark_rect: the next present copies them to screen 2. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
tt_ptr:
                ld   b, 0
                jr   nc, .m
                inc  b
.m:             ld   hl, TV_COL
                ld   (hl), b
                add  a, a
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, tut_rects
                add  hl, de
                ld   b, (hl)                   ; row
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   d, (hl)                   ; w
                inc  hl
                ld   e, (hl)                   ; h
                push bc
                push de
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   a, l
                or   c
                ld   l, a
                ld   a, h
                add  a, SCREEN_ATTR >> 8
                ld   h, a
.r:             push hl
                ld   b, d
.c:             ld   a, (TV_COL)
                or   a
                ld   a, (hl)
                jr   z, .cl
                call tt_cellpx                 ; TUT0-F3: a BLANK cell (no pixels) must not flash: FLASH
                jr   nz, .on                   ; swaps ink/paper = a solid block (bars row, ink 6/7)
                and  $7F                       ; blank: FLASH off (also drops a stale one)
                jr   .w
.on:            or   $80
                jr   .w
.cl:            and  $7F
.w:             ld   (hl), a
                inc  l                         ; a 32-aligned attr row: no page cross
                djnz .c
                pop  hl
                ld   bc, ROOM_COLS
                add  hl, bc
                dec  e
                jr   nz, .r
                pop  de
                pop  bc
                jp   pmark_rect
                ASSERT (SCREEN_ATTR & $FF) == 0
; tt_cellpx — TUT0-F3: HL = a panel attr cell (rows 16-23: bank-5 attrs); NZ = its 8 bitmap
; bytes (bank-5 screen, the one the panel draws to; present copies both to screen 2) hold a
; pixel, Z = blank. A = the cell's attr, in and out (parked in C); preserves HL, BC, DE.
; ~0.2k blank, less at the first non-zero byte. 26 B.
tt_cellpx:
                push hl
                push bc
                ld   c, a                      ; the attr
                ld   a, h
                sub  SCREEN_ATTR >> 8
                rlca
                rlca
                rlca                           ; third x 8 (0..2 -> 0, 8, 16)
                add  a, SCREEN_BITMAP >> 8
                ld   h, a                      ; bitmap line 0 of the same cell
                ld   b, 8
                xor  a
.l:             or   (hl)
                jr   nz, .x
                inc  h
                djnz .l
                xor  a                         ; Z (INC H left NZ)
.x:             ld   a, c                      ; (LD keeps the flags)
                pop  bc
                pop  hl
                ret

;------------------------------------------------------------------------------
; tt_machine — up to 6 beat steps while no group is shown (a step without a
; state change does nothing: triggers have no side effects). Clobbers: all.
;------------------------------------------------------------------------------
tt_machine:
                ld   b, 6
.l:             push bc
                call tt_step
                pop  bc
                ld   a, (TV_SHOWN)
                or   a
                jr   nz, .sh
                djnz .l
                ret
.sh:            xor  a                         ; R2 s13.5: a group of this beat: the nudge's
                ld   (TV_NAG), a               ; off-task count restarts
                ret

; tt_rec — IX = the current beat's record. Clobbers: A, DE.
tt_rec:
                ld   a, (TV_BEAT)
                add  a, a
                add  a, a
                add  a, a
                add  a, a                      ; x 16 (beat < 16)
                ld   e, a
                ld   d, 0
                ld   ix, tut_beats
                add  ix, de
                ret

;------------------------------------------------------------------------------
; tt_step — one step of the current beat (spec §3 timing: G0 when current,
; G1 on the trigger, G2 the turn after, then the tail pairs). Clobbers: all.
;------------------------------------------------------------------------------
tt_step:
                call tt_rec
                ld   a, (TV_STAGE)
                or   a
                jr   z, .pre
                dec  a
                jr   z, .g0
                dec  a
                jr   z, .g2p
                dec  a
                jp   z, .wait
                dec  a
                jp   z, .g2
                jp   .tail
.pre:           ld   a, ST_G0                  ; FH_IMPATIENT's L53, else (R2) L76
                ld   (TV_STAGE), a
                ld   d, TL_L53
                ld   a, (ix+TB_FH)
                cp   TUT_FH_IMPATIENT
                jr   z, .pr
                ld   d, TL_L76
.pr:            ld   e, TUT_NONE
                ld   c, e
                jp   tt_group
.g0:            ld   a, (ix+TB_FH)
                cp   TUT_FH_NOT_POISONED
                jr   nz, .g0n
                call tt_poisoned
                jr   nz, .g0n
                ld   hl, TV_FL                 ; B9 unpoisoned: L32, the Cure pickup advances
                set  TFB_ALT, (hl)
                ld   a, ST_WAIT
                ld   (TV_STAGE), a
                ld   de, (TL_L32 << 8) | TUT_NONE
                ld   c, e
                jp   tt_group
.g0n:           ld   a, ST_WAIT
                bit  TBF_G2PRE_BIT, (ix+TB_FL)
                jr   z, .g0w
                ld   a, ST_G2P
.g0w:           ld   (TV_STAGE), a
                ld   d, (ix+TB_G0)
                ld   e, (ix+TB_G0+1)
                ld   c, (ix+TB_R0)
                bit  TBF_H0_BIT, (ix+TB_FL)
                jp   nz, tt_group_h
                jp   tt_group
.g2p:           call tt_trig
                jr   c, .fire                  ; done already: G2 skipped
                ld   a, ST_WAIT
                ld   (TV_STAGE), a
                ld   d, (ix+TB_G2)
                ld   e, (ix+TB_G2+1)
                ld   c, (ix+TB_R1)
                jr   .h2
.wait:          call tt_fh
                ret  c
                call tt_trig
                ret  nc
.fire:          call tt_ptr_clr
                xor  a
                ld   (TV_NAG), a
                ld   a, ST_G2
                bit  TBF_G2PRE_BIT, (ix+TB_FL)
                jr   nz, .ng2
                ld   e, (ix+TB_G2)
                inc  e
                jr   nz, .st
.ng2:           ld   a, ST_TAIL
.st:            ld   (TV_STAGE), a
                cp   ST_TAIL
                call z, tt_tinit
                ld   c, (ix+TB_R1)
                bit  TBF_G2PRE_BIT, (ix+TB_FL)
                jr   z, .r1
                ld   c, TUT_NONE
.r1:            ld   d, (ix+TB_G1)
                ld   e, (ix+TB_G1+1)
                bit  TBF_H1_BIT, (ix+TB_FL)
                jp   nz, tt_group_h
                jp   tt_group
.g2:            ld   a, ST_TAIL
                ld   (TV_STAGE), a
                call tt_tinit
                ld   d, (ix+TB_G2)
                ld   e, (ix+TB_G2+1)
                ld   c, TUT_NONE
.h2:            bit  TBF_H2_BIT, (ix+TB_FL)
                jp   nz, tt_group_h
                jp   tt_group
.tail:          bit  TBF_TAIL_BIT, (ix+TB_FL)
                jp   z, tt_adv
                ld   hl, TV_XP
                ld   a, (hl)
                or   a
                jr   z, .tp
                ld   (hl), 0                   ; B14 extras (FH_VICTORY_EXTRAS)
                dec  a
                jr   nz, .x2
                ld   hl, (P_ENTITIES + E_HP)   ; after G3: HP < max and a Heal held -> L48
                ld   a, l
                cp   h
                ret  nc
                ld   a, (QS_CACHE + QS_POTION)
                and  1 << (IT_P_HEAL - IT_P_HEAL)
                ret  z
                ld   a, (tut_extras)
                jr   .x
.x2:            ld   a, (QS_CACHE + QS_SCROLL) ; after G4: the scroll still held -> L52
                or   a
                ret  z
                ld   a, (tut_extras + 1)
.x:             ld   d, a
                ld   e, TUT_NONE
                ld   c, e
                jp   tt_group
.tp:            ld   a, (TV_TI)
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, tut_tail
                add  hl, de
                ld   a, (hl)
                cp   TUT_NONE
                jr   z, tt_adv                 ; the end pair
                ld   d, a
                inc  hl
                ld   e, (hl)
                ld   a, (TV_TI)
                ld   b, a
                inc  b                         ; TV_TI + 1 rotations
                ld   a, (tut_tail_hold)
.th:            rrca                           ; CF = bit TV_TI: this pair holds
                djnz .th
                ld   a, 0
                adc  a, a
                ld   (TV_HQ), a                ; (= tt_group_h's flag: D != $FF here)
                ld   a, (TV_TI)
                sub  (ix+TB_P3)
                ld   b, a                      ; pair index relative to the beat's first
                ld   hl, TV_TI
                inc  (hl)
                bit  TBF_GRATE_BIT, (ix+TB_FL)
                jr   z, .ngr
                cp   (ix+TB_P2)
                jr   nz, .ngr
                ld   hl, TV_FL                 ; manager 2026-11-09: open only after G3 is shown
                set  TFB_GRATE, (hl)
.ngr:           ld   a, (ix+TB_FH)
                cp   TUT_FH_VICTORY_EXTRAS
                jr   nz, .nx
                ld   a, b
                cp   2
                jr   nc, .nx
                inc  a
                ld   (TV_XP), a
.nx:            ld   c, TUT_NONE
                jp   tt_group

; tt_adv — next beat (B15 is the last: it never advances). Clobbers: A, BC, DE, HL.
tt_adv:
                ld   a, (TV_BEAT)
                cp   TUT_B15
                ret  z
                inc  a
                ld   (TV_BEAT), a
                ld   a, ST_G0
                ld   (TV_STAGE), a
                jp   tt_nbeat

; tt_tinit — IX = record: the tail starts at pair p3, no extras pending. Clobbers: A.
tt_tinit:
                ld   a, (ix+TB_P3)
                ld   (TV_TI), a
                xor  a
                ld   (TV_XP), a
                ret

;------------------------------------------------------------------------------
; tt_fh — WAIT stage fail / skip handlers (IX = record). CF = 1: handled (a
; group shown and / or the beat advanced, or the trigger is blocked).
; Clobbers: all but IX.
;------------------------------------------------------------------------------
tt_fh:
                ld   a, (ix+TB_FH)
                cp   TUT_FH_PITFALL
                jr   z, .pit
                cp   TUT_FH_BOOK_DISCARD
                jr   z, .book
                cp   TUT_FH_TRAP_PASSED
                jr   z, .trap
                cp   TUT_FH_NOT_POISONED
                jr   z, .np
.no:            or   a
                ret
.pit:           ld   a, (TV_PRV + 1)           ; stood on storey 0, now on storey 1 in one
                call tt_sty                    ; turn = a fall (a climb passes mid-ladder)
                or   a
                jr   nz, .no
                ld   a, (TV_CUR + 1)
                call tt_sty
                dec  a
                jr   nz, .no
                ld   de, (TL_L69 << 8) | TL_L10     ; R2: falls hurt + the way back; the beat stays
                jr   .grp
.book:          call tt_arank
                jr   nz, .no                   ; read: the trigger
                ld   a, (ST2_BKF)
                or   a
                jr   z, .no                    ; never picked up
                ld   hl, BAG
                ld   de, IR_STRIDE
                ld   b, BAG_SLOTS
.bl:            ld   a, (hl)
                cp   IT_BOOK
                jr   z, .no
                add  hl, de
                djnz .bl
                ld   de, (TL_L15 << 8) | TUT_NONE   ; discarded unread: advance
                jr   .gad
.trap:          call tt_poisoned
                jr   nz, .no
                ld   a, (P_ENTITIES + E_X)
                cp   TRAP_PASS_X
                jr   c, .no
                ld   a, 1                      ; L29 + L28: the first search lesson on this path: holds
                ld   (TV_HQ), a
                ld   de, (TL_L29 << 8) | TL_L28
.gad:           ld   c, TUT_NONE
                call tt_group
                call tt_adv
                scf
                ret
.np:            ld   hl, TV_FL
                bit  TFB_ALT, (hl)
                jr   z, .no
                ld   a, (QS_CACHE + QS_POTION) ; the Cure in the bag: advance (no G1)
                and  1 << (IT_P_CURE - IT_P_HEAL)
                scf
                ret  z                         ; not yet: the POISON_CLR trigger blocked
                call tt_adv
                scf
                ret
.grp:           ld   c, TUT_NONE
                call tt_group
                scf
                ret

;------------------------------------------------------------------------------
; tt_trig — IX = record: CF = 1 if its trigger (TUT_TK_*) holds now.
; Clobbers: all but IX.
;------------------------------------------------------------------------------
tt_trig:
                ld   a, (ix+TB_TRIG)
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, tt_ttab
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   (hl)
tt_ttab:        DW   tk_storey, tk_near, tk_xge, tk_arank, tk_food, tk_room, tk_pois, tk_pclr
                DW   tk_ghurt, tk_pass, tk_gslp, tk_gdead, tt_no
                ASSERT TUT_TK_EXIT == 12 && TUT_TK_GOB_DEAD == 11 && TUT_TK_STOREY == 0
tk_storey:      ld   a, (TV_CUR + 1)
                call tt_sty
                cp   (ix+TB_P2)
                jr   z, tt_yes
tt_no:          or   a
                ret
tt_yes:         scf
                ret
tk_near:        ld   a, (ix+TB_SPOT)
                ld   c, (ix+TB_P2)
                jr   tt_near
tk_xge:         ld   a, (TV_CUR + 1)
                call tt_sty
                cp   (ix+TB_P2)
                jr   nz, tt_no
                ld   a, (P_ENTITIES + E_X)
                cp   (ix+TB_P3)
                ccf
                ret
tk_arank:       call tt_arank
                jr   nz, tt_yes
                jr   tt_no
tk_food:        ld   a, (TV_PRV + 5)
                ld   hl, TV_CUR + 5
                cp   (hl)                      ; CF: FOOD rose this turn
                ret
tk_room:        ld   a, (CUR_ROOM)
                cp   (ix+TB_P2)
                jr   z, tt_yes
                jr   tt_no
tk_pois:        call tt_poisoned
                jr   nz, tt_yes
                jr   tt_no
tk_pclr:        call tt_poisoned
                jr   z, tt_yes
                jr   tt_no
tk_ghurt:       call tt_gobp
                jr   z, tt_no
                ld   de, E_HP
                add  hl, de
                ld   a, (hl)
                inc  hl
                cp   (hl)                      ; CF: HP < MAXHP
                ret
tk_pass:        ld   c, (ix+TUT_TB_STRIDE+TB_P2)   ; B12: B13's G0 condition (awake, near)
                call tt_gobp
                jr   z, tt_no
                push hl
                call tt_gstat
                pop  hl
                jr   z, tt_no                  ; asleep
                inc  hl
                inc  hl
                inc  hl                        ; E_X
                ld   a, (P_ENTITIES + E_X)
                sub  (hl)
                jr   nc, tk_pp
                neg
tk_pp:          cp   c
                jr   z, tt_yes
                ret
tk_gslp:        call tt_gobp
                jr   z, tt_no
                call tt_gstat
                jr   z, tt_yes
                jr   tt_no
tk_gdead:       ld   hl, ST1_KILLS
                ld   a, (hl)
                inc  hl
                or   (hl)                      ; CF = 0
                ret  z
                scf
                ret
                ASSERT E_X == 3

; tt_near — A = spot, C = cols: CF = 1 if the spot is in CUR_ROOM and |hero x
; - its col| <= C. Clobbers: A, DE, HL.
tt_near:
                call tt_spot
                ld   a, (CUR_ROOM)
                cp   (hl)
                jr   nz, .n
                inc  hl
                ld   a, (P_ENTITIES + E_X)
                sub  (hl)
                jr   nc, .p
                neg
.p:             cp   c
                ret  nz                        ; CF: |dx| < C
                scf
                ret
.n:             or   a
                ret

; tt_spot — A = spot: HL = its tut0_spots entry (room, col, row). Clobbers: A, DE.
tt_spot:
                ld   l, a
                add  a, a
                add  a, l
                ld   l, a
                ld   h, 0
                ld   de, tut0_spots
                add  hl, de
                ret

; tt_sty — A = hero E_Y: A = the storey he stands on (0 / 1), $FF mid-ladder / air.
tt_sty:
                sub  STAND_Y0
                ret  z
                sub  STAND_Y1 - STAND_Y0
                ld   a, 1
                ret  z
                ld   a, $FF
                ret

; tt_poisoned — NZ: the hero is POISONED. Clobbers: A.
tt_poisoned:
                ld   a, (ST_FLAGS)
                and  STS_POISON
                ret

; tt_arank — NZ: a rank was learned (ARANK bits 0-9). Clobbers: A, HL.
tt_arank:
                ld   a, (ARANK + 1)
                and  3
                ld   hl, ARANK
                or   (hl)
                ret

; tt_gobp — NZ: the Goblin is a live slot of CUR_ROOM, HL = its slot. Clobbers: A, DE, HL.
tt_gobp:
                ld   a, (TV_GOB)
                ld   l, a
                inc  a
                ret  z
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, P_ENTITIES
                add  hl, de                    ; (Z kept: NZ)
                ret

; tt_gstat — Z: the Goblin (TV_GOB) is ASLEEP. Clobbers: A, HL.
tt_gstat:
                ld   a, (TV_GOB)
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_HOLD
                cp   HOLD_ASLEEP
                ret

;------------------------------------------------------------------------------
; tt_repeat — no group yet, WAIT stage, the beat has an instruction group
; (tt_igrp: G0, or G2 for a G2PRE beat): R2 s13.5 the NUDGE (replaces the
; 60-turn nag) — TV_NAG counts the off-task turns (no group, no trigger) since
; this beat's last group; at NUDGE_T and NUDGE_T2 L75 (scroll), the next turn
; the instruction group again (no hold, pointer re-armed); silent after that.
; Not counted in B6 / B10 / B11 (walks toward the target) / B12 (passive) nor while the Goblin is awake (combat); B8 / B15
; have no instruction group. The Repeat (a Wait near the mentor: nothing in
; TV_CUR changed, |x - his col| <= REPEAT_COLS) re-shows it too and restarts
; the count. Clobbers: all.
;------------------------------------------------------------------------------
tt_repeat:
                ld   a, (TV_SHOWN)
                or   a
                ret  nz
                ld   a, (TV_STAGE)
                cp   ST_WAIT
                ret  nz
                call tt_rec
                ld   a, (ix+TB_G0)             ; (tt_igrp's D: G2PRE beats have both)
                inc  a
                ret  z                         ; no instruction (B8 silent, B14, B15)
                ld   a, (TV_BEAT)
                cp   TUT_B6
                jr   z, .w                     ; TUT0-F4: B6 / B10 / B11 are walks (12+ turns of progress,
                sub  TUT_B10                   ; not idling), B12 passive: no count, only the Repeat
                cp   TUT_B12 - TUT_B10 + 1
                jr   c, .w
                call tt_awake
                jr   nz, .w
                ld   hl, TV_NAG
                ld   a, (hl)
                cp   NUDGE_T2 + 1
                jr   nc, .rs                   ; saturated: no more nudges
                inc  (hl)
                ld   a, (hl)
                cp   NUDGE_T
                jr   z, .l75
                cp   NUDGE_T2
                jr   z, .l75
.rs:            ld   hl, TV_FL
                bit  TFB_RESHOW, (hl)
                res  TFB_RESHOW, (hl)
                jr   nz, .show                 ; (the count is NOT restarted: 12 / 36)
.w:             ld   hl, TV_CUR
                ld   de, TV_PRV
                ld   b, TV_SNAP
.c:             ld   a, (de)
                cp   (hl)
                ret  nz
                inc  hl
                inc  de
                djnz .c
                ld   a, (TV_SPOT)
                ld   c, REPEAT_COLS
                call tt_near
                ret  nc
                xor  a                         ; a fresh show of this beat's group
                ld   (TV_NAG), a
.show:          call tt_igrp
                ld   a, (TV_FL)
                bit  TFB_ALT, a
                jr   z, tt_group
                ld   de, (TL_L32 << 8) | TUT_NONE
                ld   c, e
                jr   tt_group
.l75:           ld   hl, TV_FL
                set  TFB_RESHOW, (hl)
                ld   de, (TL_L75 << 8) | TUT_NONE
                ld   c, e
                jr   tt_group

; tt_igrp — IX = record: D, E, C = its instruction group + rect (G2 / +13 for a
; G2PRE beat, else G0 / +12). Clobbers: nothing else.
tt_igrp:
                ld   d, (ix+TB_G0)
                ld   e, (ix+TB_G0+1)
                ld   c, (ix+TB_R0)
                bit  TBF_G2PRE_BIT, (ix+TB_FL)
                ret  z
                ld   d, (ix+TB_G2)
                ld   e, (ix+TB_G2+1)
                ld   c, (ix+TB_R1)
                ret

; tt_awake — NZ: the Goblin is a live slot of CUR_ROOM and not ASLEEP. Clobbers: A, DE, HL.
tt_awake:
                call tt_gobp
                ret  z
                jp   tt_gstat                  ; Z = asleep

;------------------------------------------------------------------------------
; tt_group — D, E = line ids (D = $FF: nothing; E = $FF: one line), C = the
; pointer rect ($FF none): old pointer off, the new one on, both lines
; expanded and queued, TV_SHOWN := 1. Clobbers: all (IX: tt_frame may run).
;------------------------------------------------------------------------------
tt_group:
                ld   a, d
                cp   TUT_NONE
                ret  z
                push de
                push bc
                call tt_ptr_clr
                pop  bc
                ld   a, (TV_HQ)                ; TUT0-R2 budget: a holding group's pointer is
                or   a                         ; drawn by tt_hold after its drain (frames, not
                ld   a, c                      ; the turn tick's work); else now
                jr   z, .now
                ld   (TV_PTR), a
                jr   .ln
.now:           call tt_ptr_set
.ln:            pop  de
                push de
                ld   a, d
                call tt_line
                pop  de
                ld   a, e
                cp   TUT_NONE
                call nz, tt_line
                ld   a, 1
                ld   (TV_SHOWN), a
                ret
; tt_group_h — tt_group for a group that HOLDS (TV_HQ := 1 if it shows).
tt_group_h:
                ld   a, d
                cp   TUT_NONE
                ret  z
                ld   a, 1
                ld   (TV_HQ), a
                jr   tt_group

;------------------------------------------------------------------------------
; tt_line — A = TL_ id (bit 7: tut_cpairs class pair, W / M by HERO_KIND):
; the stream (resident-dictionary tokens, decoded at draw time by print6t) is
; copied into TV_BUF with the control bytes 1..5 (U D L R F) expanded — KEYS:
; the 2-char REDEFINE name (bank-1 key_name, far1; read by copy_virt_keep, a
; trailing space dropped), Kempston / Sinclair: UP DOWN LEFT RIGHT FIRE — then
; log_push. A full ring first drains (tt_frame) so no line is dropped.
; Clobbers: all (IX too, when it drains).
;------------------------------------------------------------------------------
tt_line:
                cp   TUT_CP
                jr   c, .p
                and  $7F
                add  a, a
                ld   hl, HERO_KIND
                add  a, (hl)
                ld   e, a
                ld   d, 0
                ld   hl, tut_cpairs
                add  hl, de
                ld   a, (hl)
.p:             add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, tut_tab
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ld   de, TV_BUF
.c:             ld   a, (hl)
                inc  hl
                or   a
                jr   z, .end
                cp   TUT_CTL_N + 1
                jr   c, .tok
                ld   (de), a
                inc  de
                jr   .c
.tok:           push hl
                call tt_tok
                pop  hl
                jr   .c
.end:           ld   (de), a
.dr:            ld   a, (LOG_QN)
                cp   LOG_SLOTS
                jr   c, .ok
                call tt_frame                  ; ring full: let the panel draw one
                jr   .dr
.ok:            ld   hl, TV_BUF
                jp   log_push
                ASSERT JOY_R_BIT == 0 && JOY_L_BIT == 1 && JOY_D_BIT == 2 && JOY_U_BIT == 3 && JOY_F_BIT == 4
tt_stick:       DB   "UP", 0, "DOWN", 0, "LEFT", 0, "RIGHT", 0, "FIRE", 0

; tt_tok — A = control byte 1..5 (U D L R F): its name -> (DE..), DE past it.
; KEYS: the 2-char REDEFINE name (trailing space dropped); sticks: tt_stick.
; Clobbers: A, BC, HL.
tt_tok:
                ld   c, a
                ld   a, (JOY_MODE)
                or   a
                jr   nz, .stk
                ld   a, 4
                sub  c                         ; U D L R -> KEYTAB entry 3 2 1 0 (= JOY bit)
                jr   nc, .e
                ld   a, JOY_F_BIT              ; F
.e:             push de
                ld   hl, key_name              ; bank 1 (menu1.asm): HL = its 2 chars
                call far1
                ld   bc, BANK_WINDOW - $8000
                or   a
                sbc  hl, bc                    ; the virtual address (copy_virt: bank 1 = $8000..)
                pop  de
                ld   bc, 2
                call copy_virt_keep            ; DE past
                dec  de
                ld   a, (de)
                cp   ' '
                ret  z
                inc  de
                ret
.stk:           ld   hl, tt_stick
                dec  c
                jr   z, .sc
.sk:            ld   a, (hl)
                inc  hl
                or   a
                jr   nz, .sk
                dec  c
                jr   nz, .sk
.sc:            ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  de
                inc  hl
                jr   .sc

;------------------------------------------------------------------------------
; tt_hold — the shown group holds until a keypress (user 2026-11-09; TUT0-F2 A + B):
; render now (A1: the talk pose tt_mentor just stamped, before the first
; presented frame), whole frames (tt_frame) until the lines and the info line
; are drawn; then the cue (A2: the log rows pulse BRIGHT, A3: the blinking
; prompt right-aligned in row 20 cols HP_COL..31, bright white, the info line's
; end — no log-row cell is free) every frame until every key is up and then one goes DOWN (B1): the
; cue comes off at once (rows: the BRIGHT bit put back; row 20: its attrs put
; back, blanked, and PD_INFO redraws its text in the same frame), then frames until every key is up
; (swallowed: STICK / STICK_OLD and the shortcut matrix see no press when play
; resumes; INTENT / DN_T / DN_COMMIT cleared, FIRE_ST := FS_USED, TUT0-F3). The
; ROW20 pointer rect stops at col HP_COL - 1: the prompt never sits on a pointer
; cell (TUT0-F3 B12). Clobbers: all.
;------------------------------------------------------------------------------
HP_COL          EQU 26                  ; the prompt area: a gap, the triangle, the name (<= 4 chars)
HP_W            EQU 32 - HP_COL
HP_ATTR20       EQU SCREEN_ATTR + INFO_ROW * 32 + HP_COL
HP_INK          EQU ATTR_HUD            ; bright white on black
HP_ROWS         EQU 2                   ; the log rows 22-23, cols 0..LOG_COLS-1 pulse
HP_BLINK        EQU 3                   ; triangle: on / off every 8 frames (bit 3 of TV_HFC)
HP_PULSE        EQU 4                   ; rows: BRIGHT / normal every 16 frames (bit 4)
HP_ATTR         EQU SCREEN_ATTR + LOG_ROW * 32
                ASSERT HP_COL + 1 + 1 + 3 <= 32 && LOG_ROW + HP_ROWS == 24
                ASSERT TUT_R20_W <= HP_COL      ; the prompt is on no ROW20 pointer cell (TUT0-F3)
tt_hold:
                ld   a, 1
                ld   (TV_HOLD), a
.go:            ld   hl, render                ; A1: the stamped pose's queued restore lands now
                call farb4
                call pmark_dmg
.drn:           call tt_frame
                ld   a, (LOG_QN)
                or   a
                jr   nz, .drn
                ld   a, (PANEL_DIRTY)
                and  PD_LOG | PD_INFO
                jr   nz, .drn
                call tt_ptr_re                 ; TUT0-R2: the group's pointer (tt_group deferred it)
                ; the prompt: its name ("FIRE" / the FIRE key's 2 chars) after the triangle
                ld   de, TV_BUF
                ld   a, TUT_CTL_N              ; F
                call tt_tok
                xor  a
                ld   (de), a
                ld   (TV_HFC), a
                ld   (TV_HST), a
                ld   a, e
                sub  TV_BUF & $FF              ; n = 1..4 chars
                ld   c, a
                add  a, a
                add  a, c
                add  a, a                      ; 6n px
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F                       ; cells = ceil(6n / 8) = 1..3
                cpl
                add  a, 32                     ; 31 - cells
                ld   (TV_TRI), a
                ld   hl, HP_ATTR20             ; the attrs saved, then bright white
                ld   de, TV_HA
                ld   bc, HP_W
                ldir
                ld   hl, HP_ATTR20
                ld   b, HP_W
.a:             ld   (hl), HP_INK
                inc  l
                djnz .a
                call hp_clr
                ld   a, (TV_TRI)
                inc  a
                add  a, a
                add  a, a
                add  a, a
                ld   e, a                      ; x = (col + 1) * 8
                ld   hl, TV_BUF
                ld   b, INFO_ROW
                call print6
.rel:           call tt_hframe
                call tt_key
                jr   nz, .rel
.prs:           call tt_hframe
                call tt_key
                jr   z, .prs
                ld   hl, TV_HST                ; B1: off at once
                bit  0, (hl)
                call nz, hp_rows
                ld   hl, TV_HA
                ld   de, HP_ATTR20
                ld   bc, HP_W
                ldir
                call hp_clr
                ld   hl, PANEL_DIRTY
                set  PD_INFO_BIT, (hl)         ; the info line back (tt_frame's panel_tick)
.up:            call tt_frame
                call tt_key
                jr   nz, .up
                call tt_ptr_re                 ; TUT0-F4: the row-20 pointer (PD_INFO's redraw dropped its FLASH)
                xor  a                         ; TUT0-F3 3: no input from before the hold acts
                ld   (TV_HOLD), a              ; after it (as pause_run7 / page_lat3): a FIRE
                ld   (INTENT), a               ; tap / ENTER queued in the last tick, a DOWN
                ld   (DN_T), a                 ; window or commit; a FIRE still counted as held
                ld   (DN_COMMIT), a            ; is not a tap
                ld   a, FS_USED
                ld   (FIRE_ST), a
                jp   resync_tick

; tt_holdm — a turn's held group (tt_after): the hold starts (TV_HOLD), then the
; mentor's pose for the turn (tt_mentor: TALK, a blink) BEFORE the first frame
; (tt_hold renders it at once), then the hold. Clobbers: all.
tt_holdm:
                ld   a, 1
                ld   (TV_HOLD), a
                call tt_mentor
                jp   tt_hold.go

; tt_hframe — the cue's step (rows on while TV_HFC bit HP_PULSE = 0, the
; triangle while bit HP_BLINK = 0: both on in the first frame), then tt_frame.
; Clobbers: all.
tt_hframe:
                ld   hl, TV_HFC
                ld   a, (hl)
                inc  (hl)
                ld   c, a
                ld   hl, TV_HST
                bit  HP_PULSE, c
                ld   a, 0
                jr   nz, .r
                inc  a
.r:             xor  (hl)
                rra
                call c, hp_rows                ; bit 0 must change
                bit  HP_BLINK, c
                ld   a, 0
                jr   nz, .t
                ld   a, 2
.t:             xor  (hl)
                and  2
                call nz, hp_tri
                jp   tt_frame

; hp_rows — the log rows' BRIGHT bit flipped (cols 0..LOG_COLS-1), TV_HST bit 0
; flipped, marked. HL = TV_HST in / out. Clobbers: A, B, DE (C kept).
hp_rows:
                ld   a, (hl)
                xor  1
                ld   (hl), a
                push hl
                push bc
                ld   hl, HP_ATTR
                ld   de, 32 - LOG_COLS
                ld   c, HP_ROWS
.l:             ld   b, LOG_COLS
.c:             ld   a, (hl)
                xor  $40
                ld   (hl), a
                inc  l                         ; (rows 22-23: one attr page)
                djnz .c
                add  hl, de
                dec  c
                jr   nz, .l
                ld   bc, LOG_ROW << 8
                ld   de, (LOG_COLS << 8) | HP_ROWS
                call pmark_rect
                pop  bc
                pop  hl
                ret
                ASSERT (HP_ATTR & $FF) + HP_ROWS * 32 <= $100

; hp_tri — the triangle drawn / blanked (TV_HST bit 1 flipped), marked.
; HL = TV_HST in / out. Clobbers: A, B, DE (C kept).
hp_tri:
                ld   a, (hl)
                xor  2
                ld   (hl), a
                push hl
                push bc
                ld   de, hp_glyph
                and  2
                jr   nz, .d
                ld   de, hp_glyph + 8          ; 8 zero bytes: blank
.d:             ld   a, (TV_TRI)
                ld   c, a
                add  a, INFO_BM & $FF
                ld   l, a
                ld   h, INFO_BM >> 8
                ld   b, 8
.l:             ld   a, (de)
                ld   (hl), a
                inc  de
                inc  h
                djnz .l
                ld   b, INFO_ROW
                ld   de, (1 << 8) | 1
                call pmark_rect
                pop  bc
                pop  hl
                ret
hp_glyph:       DB   $00, $40, $60, $70, $78, $70, $60, $40   ; a solid right-pointing triangle
                DS   8, 0

; hp_clr — row 20 cols HP_COL..31 blanked (bitmap), marked. Clobbers: A, BC, DE, HL.
hp_clr:
                ld   hl, INFO_BM + HP_COL
                ld   c, 8
.l:             ld   b, HP_W
                xor  a
.c:             ld   (hl), a
                inc  l
                djnz .c
                ld   a, l
                sub  HP_W
                ld   l, a
                inc  h
                dec  c
                jr   nz, .l
                ld   bc, (INFO_ROW << 8) | HP_COL
                ld   de, (HP_W << 8) | 1
                jp   pmark_rect
                ASSERT ((INFO_BM + HP_COL) & $FF) + HP_W <= $100 && (HP_ATTR20 & $FF) + HP_W <= $100

; tt_frame — one frame: menu_frame (the select_tick probe, input_tick), the
; panel as in a 1st-frame tick, present. Clobbers: all.
tt_frame:
                call menu_frame
                call resync_tick
                ld   hl, panel_tick
                call farb4
                ld   hl, present
                jp   farb4

; tt_key — NZ: a key (KBD_MATRIX) or a stick input (STICK) is down. Clobbers: A, B, HL.
tt_key:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, $1F
.a:             and  (hl)
                inc  hl
                djnz .a
                xor  $1F
                ld   hl, STICK
                or   (hl)
                ret

;------------------------------------------------------------------------------
; tt_mentor — the mentor's spot / pose for this turn (see the header): the
; beat's spot (a G0-less beat moves only after its trigger: B14 on victory),
; a spot change blinks (blocking: FADE / gone / FADE, TUT_BLINK_FR rendered
; frames each, ~12 frames; resynced), TALK if a group was shown, else the beat's
; frame (IDLE toggles), facing the hero; a changed image -> tut_glyphs + a
; re-stamp; not stamped and in CUR_ROOM -> stamp. Skipped in a 2nd-frame tick
; without a group. Clobbers: all.
;------------------------------------------------------------------------------
tt_mentor:
                ld   a, (TV_SHOWN)
                or   a
                jr   nz, .go
                ld   a, (SYS_FRAMES)
                ld   hl, LAST_TICK_FRAME
                cp   (hl)
                ret  nz
.go:            ld   hl, TV_PH
                inc  (hl)
                call tt_rec
                ld   a, (TV_SPOT)
                ld   d, a
                ld   a, (ix+TB_SPOT)
                cp   TUT_NONE
                jr   z, .ks
                ld   e, a
                call .defer
                jr   z, .ks
                ld   d, e
                ; TUT0-F1: the blink runs whole inside this turn (spec §4.2: FADE 2
                ; ticks at the old spot, gone 2, FADE 2 at the new, then the pose); it
                ; was one phase per turn, so an idle player saw him half-dissolved
.ks:            ld   a, (TV_SPOT)
                cp   d
                jr   z, .pose
                push de
                ld   a, (TV_STAMP)
                or   a
                jr   z, .bn                    ; not drawn: no fade-out
                call .fade
                call tt_unstamp
                call .wait
.bn:            pop  de
                ld   a, d
                ld   (TV_SPOT), a
                call tt_spot
                ld   a, (CUR_ROOM)
                cp   (hl)
                call z, .fade                  ; in another room: drawn on arrival
.pose:          ld   a, (TV_SHOWN)
                or   a
                jr   z, .bp
                ld   a, (TV_PH)
                and  1
                add  a, TUT_POSE_TALK
                ld   c, a
                jr   .img
.bp:            ld   a, (ix+TB_POSE)
                and  TUT_POSE_MASK
                ld   c, a
                call .defer
                jr   nz, .np
                ld   c, TUT_POSE_IDLE
.np:            ld   a, c
                or   a
                jr   nz, .img
                ld   a, (TV_PH)
                and  1
                ld   c, a                      ; IDLE1 / IDLE2
.img:           ld   a, (TV_SPOT)
                call tt_spot
                ld   b, (hl)                   ; room
                inc  hl
                ld   a, (P_ENTITIES + E_X)
                cp   (hl)
                sbc  a, a                      ; hero left of his box: face left
                and  MENTOR_LEFT
                sla  c
                or   c
                ld   c, a                      ; the image
                ld   a, (TV_STAMP)
                or   a
                jr   nz, .st
                ld   a, (CUR_ROOM)
                cp   b
                ret  nz                        ; another room: nothing to draw
                ld   a, c
                ld   (TV_IMG), a
                call tut_glyphs
                ld   a, 1
                ld   (TV_STAMP), a
                ld   a, (TV_SPOT)
                jp   tut_stamp
.st:            ld   a, (TV_IMG)
                cp   c
                ret  z
                ld   a, c
                ld   (TV_IMG), a
                call tut_glyphs
                ld   a, (TV_SPOT)              ; TUT0-F1: a facing change re-orders the ids
                jp   tut_stamp
; .fade — FADE stamped at TV_SPOT (in CUR_ROOM; FADE is symmetric: right),
; then .wait. Clobbers: all but IX.
.fade:          ld   a, TUT_POSE_FADE * 2
                ld   (TV_IMG), a
                call tut_glyphs
                ld   a, 1
                ld   (TV_STAMP), a
                ld   a, (TV_SPOT)
                call tut_stamp
; .wait — TUT_BLINK_FR frames: render (the box's queued restore lands: tt_frame
; only presents), a frame edge, present; then resync. No input_tick: a key
; pressed during the blink keeps its STICK edge for the next turn (the driver's
; U+R jump was lost to it). Clobbers: all but IX.
.wait:          push ix
                ld   b, TUT_BLINK_FR
.wl:            push bc
                ld   hl, render
                call farb4
                call pmark_dmg
                ld   hl, SYS_FRAMES
                ld   a, (hl)
.fw:            cp   (hl)
                jr   z, .fw
                ld   hl, present
                call farb4
                pop  bc
                djnz .wl
                pop  ix
                jp   resync_tick
; .defer — IX = record: Z = a G0-less beat before its trigger (keep spot / idle). Clobbers: A.
.defer:         ld   a, (ix+TB_G0)
                inc  a
                ret  nz
                ld   a, (TV_STAGE)
                cp   ST_WAIT + 1
                sbc  a, a                      ; stage <= WAIT: $FF
                inc  a                         ; -> 0 (Z)
                ret

; tt_box — TV_SPOT's box for rect_repaint: C = col, B = row, DE = 3 x 6. Clobbers: A, DE, HL.
tt_box:
                ld   a, (TV_SPOT)
                call tt_spot
                inc  hl
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                ld   de, (3 << 8) | 6
                ret

; tt_unstamp — his ids out of ROOM_MAP (back to T_AIR: tut_stamp wrote only
; T_AIR cells; ids = tut0_mentor_ids, contiguous) + a repaint, if stamped.
; Clobbers: all but IX.
tt_unstamp:
                ld   a, (TV_STAMP)
                or   a
                ret  z
                xor  a
                ld   (TV_STAMP), a
                call tt_box
                push bc
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   a, l
                or   c
                ld   l, a
                ld   de, ROOM_MAP
                add  hl, de
                ld   a, (tut0_mentor_ids)
                ld   e, a
                ld   b, 6
.r:             ld   c, 3
.c:             ld   a, (hl)
                sub  e
                cp   TUT0_MENTOR_N
                jr   nc, .s
                ld   (hl), T_AIR
.s:             inc  hl
                dec  c
                jr   nz, .c
                ld   a, l
                add  a, ROOM_COLS - 3
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:            djnz .r
                pop  bc
                ld   de, (3 << 8) | 6
                jp   rect_repaint

;==============================================================================
; blob_icon — TUT0-R2 the interactive icon tour (tutorial_d0.md §13.2-13.3).
; From ts_icon (pi_ic: intent_tick's ICON MODE branch, after intent_icon7) once
; per ICON MODE tick. Play is frozen there (TURN_PHASE = 0), so its work is not
; turn-tick work; a tick of a turn still animating does nothing.
;  - ICON MODE left (UP / DOWN / BREAK) or a use pending (INTENT: FIRE, the bag
;    page): the session ends (TV_ISLOT := $FF; blob_turn A = 0 does it too).
;  - session start: every pointer is retired (tt_ptr_clr: TV_PTR := $FF, so
;    tt_ptr_re has nothing to put back and leaving the mode restores nothing;
;    only a fresh show of a group re-arms one, P2 / P3); the entry pair I00a /
;    I00b once per D0, HELD (tt_hold from here: frames of menu_frame /
;    panel_tick / present, all keys up, a key, all up, resync_tick — the
;    dismissing key never reaches intent_tick: STICK_OLD / PLAYER_SC are re-read
;    released, so it neither moves the cursor, leaves the mode nor uses).
;  - the cursor resting REST_T calls on one slot: a target of the current beat
;    (tut_tgt) on every rest, held the first time where flagged; else the slot's
;    generic line (tut_tour) once per D0 (TV_ISAID). Tour lines scroll.
; Clobbers: A, BC, DE, HL (IX kept: intent_tick's contract).
; T: ~0.15k idle; a line ~2-3k (tt_line + log_push); a hold = frames (resynced).
;==============================================================================
blob_icon:
                push ix
                call .run
                pop  ix
                ret
.run:           ld   a, (ICON_MODE)
                or   a
                jr   z, .end
                ld   a, (INTENT)
                or   a
                jr   nz, .end
                ld   a, (TURN_PHASE)
                or   a
                ret  nz                        ; a turn still animating (mode entered meanwhile)
                ld   a, (SEL_SLOT)
                ld   c, a
                ld   hl, TV_ISLOT
                ld   a, (hl)
                cp   TUT_NONE
                jr   nz, .in
                ld   (hl), c                   ; session start
                xor  a
                ld   (TV_IREST), a
                call tt_ptr_clr                ; P2: the pointer yields to the cursor, retired
                ld   hl, TV_ISAID
                bit  0, (hl)
                ret  nz
                set  0, (hl)
                ld   de, (TL_I00a << 8) | TL_I00b
                jr   .hold
.in:            cp   c
                jr   z, .rest
                ld   (hl), c                   ; moved: a new rest
                xor  a
                ld   (TV_IREST), a
                ret
.end:           ld   a, TUT_NONE
                ld   (TV_ISLOT), a
                ret
.rest:          ld   hl, TV_IREST
                ld   a, (hl)
                cp   REST_T
                ret  nc                        ; said for this rest already
                inc  a
                ld   (hl), a
                cp   REST_T
                ret  nz
                ; --- a target of the current beat first ---
                ld   hl, tut_tgt
                ld   b, TUT_TGT_N
.t:             ld   a, (TV_BEAT)
                cp   (hl)
                jr   nz, .tn
                inc  hl
                ld   a, c
                cp   (hl)
                dec  hl
                jr   nz, .tn
                push hl
                pop  ix
                ld   a, (ix+4)
                and  7
                ld   e, a                      ; the lowest stage (G0 / G2 shown)
                ld   a, (TV_STAGE)
                cp   e
                jr   c, .tn
                cp   ST_WAIT + 1
                jr   nc, .tn                   ; triggered already: no target
                bit  TUT_TGF_POIS_BIT, (ix+4)
                jr   z, .tp
                call tt_poisoned
                jr   z, .tn
.tp:            ld   d, (ix+2)
                ld   e, (ix+3)
                ld   a, (ix+5)
                or   a
                jr   z, .say                   ; never holds
                ld   hl, TV_ISAID + 1
                ld   c, a
                and  (hl)
                jr   nz, .say                  ; held once in this beat already: scroll
                ld   a, c
                or   (hl)
                ld   (hl), a
.hold:          ld   a, 1                      ; (test-observable: only I00 and a first bag target)
                ld   (TV_HQ), a
                ld   c, TUT_NONE
                call tt_group
                jp   tt_holdm                  ; TUT0-F4: = tt_hold + the TALK pose (tt_mentor: TV_SHOWN set)
.tn:            ld   de, TUT_TG_STRIDE
                add  hl, de
                djnz .t
                ; --- the slot's generic line, once per D0 (bit slot + 1 of TV_ISAID) ---
                ld   b, c
                inc  b
                ld   hl, 1
.sh:            add  hl, hl
                djnz .sh
                ld   de, (TV_ISAID)
                ld   a, e
                and  l
                ret  nz
                ld   a, d
                and  h
                ret  nz
                ld   a, e
                or   l
                ld   e, a
                ld   a, d
                or   h
                ld   d, a
                ld   (TV_ISAID), de
                ld   hl, tut_tour              ; (B = 0 after the DJNZ)
                add  hl, bc
                ld   d, (hl)                   ; $FF: a silent slot (tt_group shows nothing)
                ld   e, TUT_NONE
.say:           xor  a                         ; a tour line never holds
                ld   (TV_HQ), a
                ld   c, TUT_NONE
                jp   tt_group
                ASSERT TUT_TGF_POIS == 1 << TUT_TGF_POIS_BIT && ICON_SLOTS + 1 <= 13 && TUT_TG_STRIDE == 6
