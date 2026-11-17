;==============================================================================
; tut_speak.asm — MORROW-SPEAK (user 2026-11-16; tutorial_d0.md §15): Brother
; Morrow's speaker cue, D0 blob only (bank 4; tut_blob.asm rules).
;  1. His log lines in their own ink (MOR_ATTR_NEW / _OLD, the cyan of his
;     sprite and of the goal line), every other line as before.
;  2. A 16x16 speech balloon (assets/gfx/mentor/balloon.asm, white on black, no
;     mask) beside his head while his latest line is the newest log line.
;
; Line ownership (review A, in-band): tt_line queues MOR_MARK + the line, so the
; owner is IN the LOG_TXT slot; blob_log, which draws every log line while D0
; runs (the il_go SMC: item_log's farb lands here instead of item_log0), tests
; the slot's first byte, strips the mark (the line one byte down: an LDIR in
; the slot), draws through item_log0, then sets the two log rows' attrs
; (row 22 = the scrolled line's ink without BRIGHT, row 23 = this line's) and
; TV_BSAY (his line is the newest). The rows' attrs need no mark: item_log0 /
; log_scroll mark every inked cell of both rows (HUD4_PW), a blank cell's ink
; never shows (paper 0 either way). An engine line that replaces the newest
; pending slot (log_room, log_push_end: the ring full) writes its own text over
; the mark: drawn as the engine's (his replaced line is lost, LOG-FIX's rule).
;
; The balloon is a TILE STAMP like Morrow himself (survives every erase: the
; engine restores the cells from ROOM_MAP): it borrows the 4 ids of the D8
; Sanctum lectern T_LECT_TL..BR (common ids 15..18; nothing places them on D0,
; their glyphs / attrs / flags are put back by tt_unhook at every D0 exit, which
; also undoes the SMC operands). Placement (tt_bal): the rows above his head
; clamped to his storey's top (a D0 spot is 1 row below it, so this is the
; storey's top 2 rows), then sideways IN FRONT of his face (facing right: the
; cols right of his box, the tail as drawn = lower left, toward him; facing
; left: left of it, mirrored), the first of BAL_TRY positions whose 4 cells are
; T_AIR (no wall, decor, ladder, item, his own box) and touch no live body's box
; (cols x-1..x+4, rows y..y+5 of every EF_ACTIVE slot); none: not shown (retried
; at the next turn end / line). Never on the HUD (rows < PLAY_ROWS).
; Hidden: an engine line drawn, a blink away (tt_mentor), a room change (tt_glob:
; the map is rebuilt), GS_PLAYING left; moved / mirrored when his spot / facing
; changes (tt_after's turn-end tt_bal).
;==============================================================================
MOR_MARK        EQU 1                   ; review A: his line's first byte in the ring (a control byte: tt_exp
                                        ; expands 1..5, the engine streams are 32..127 / tokens: never queued)
MOR_ATTR_NEW    EQU $45                 ; his newest line (row 23): bright cyan = TUT_GOAL_ATTR
MOR_ATTR_OLD    EQU $05                 ; scrolled to row 22: cyan, BRIGHT off (as ATTR_LOG_NEW -> _OLD)
BAL_ID0         EQU T_LECT_TL           ; the 4 borrowed ids: TL TR / BL BR = balloon.asm's order
BAL_TRY         EQU 3                   ; positions tried in front of him (nearest first)
BAL_GLY         EQU TILE_GLYPHS + BAL_ID0 * 8
LOG23_ATTR      EQU SCREEN_ATTR + (LOG_ROW + 1) * 32
LOG22_ATTR      EQU SCREEN_ATTR + LOG_ROW * 32
                ASSERT MOR_ATTR_NEW == TUT_GOAL_ATTR && (MOR_ATTR_NEW & $BF) == MOR_ATTR_OLD
                ASSERT (ATTR_LOG_NEW & $BF) == ATTR_LOG_OLD && (LOG22_ATTR >> 8) == (LOG23_ATTR >> 8)
                ASSERT T_LECT_TR == BAL_ID0 + 1 && T_LECT_BL == BAL_ID0 + 2 && T_LECT_BR == BAL_ID0 + 3
                ASSERT (ROOM_MAP & $FF) == 0 && (TILE_ATTRS & $FF) == 0 && (BAL_ID0 + 4) <= TILE_COMMON
                ASSERT ((tile_flags + BAL_ID0) >> 8) == ((tile_flags + BAL_ID0 + 3) >> 8)
                ASSERT {b tile_flags + BAL_ID0} == TF_SOLID | TF_ATTACK && {b tile_flags + BAL_ID0 + 3} == TF_SOLID | TF_ATTACK
                ASSERT {b tile_flags + BAL_ID0 + 1} == TF_SOLID | TF_ATTACK && {b tile_flags + BAL_ID0 + 2} == TF_SOLID | TF_ATTACK
                ASSERT balloon_count == 4

;------------------------------------------------------------------------------
; blob_log — item_log's line while D0 runs (il_go: farb, C = BANK_BLOB; LOG_QN
; != 0). Clobbers: all but IX, IY (item_log's contract).
; T: item_log0 (~23k for 32 chars) + FARB0 ~0.25k + ~0.1k the mark test (+0.7k his line's strip) + ~0.6k per log
; row whose owner changed + tt_bal (~0.3k unchanged; ~3-5k a placement, ~1.5k a hide). (A log item is drawn only in
; a tick still in its 1st frame: panel_tick.)
;------------------------------------------------------------------------------
blob_log:
                ld   a, (LOG_Q + LQ_RD)        ; the slot item_log0 draws
                rrca
                rrca                           ; x LOG_SLOT_LEN
                ld   l, a
                ld   h, LOG_TXT >> 8
                ld   a, (hl)
                cp   MOR_MARK
                ld   a, 0
                jr   nz, .own                  ; an engine line (or one written over his)
                ld   d, h
                ld   e, l
                inc  l
                ld   bc, LOG_MAX + 1
                ldir                           ; his: the mark out (the line + 0 one byte down, in the slot)
                dec  a                         ; A = $FF
.own:           or   a
                push af                        ; NZ: Morrow's line
                ASSERT LOG_SLOT_LEN == 64 && (LOG_TXT & $FF) == 0 && LOG_MAX + 2 <= LOG_SLOT_LEN
                ASSERT MOR_MARK >= 1 && MOR_MARK <= TUT_CTL_N
                FARB0 item_log0                ; scroll + the line (bank 4 back)
                ld   hl, LOG23_ATTR            ; (a row's 24 attrs are always one value: col 0 stands
                ld   a, (hl)                   ; for the row; a row already right is not rewritten,
                and  $BF                       ; -1.1k T on a run of one owner's lines)
                ld   l, LOG22_ATTR & $FF       ; the line scrolled up: its ink, BRIGHT off
                cp   (hl)
                ld   b, LOG_COLS
                call nz, r20_fill
                pop  af
                ld   (TV_BSAY), a
                ld   a, ATTR_LOG_NEW
                jr   z, .e
                ld   a, MOR_ATTR_NEW
.e:             ld   l, LOG23_ATTR & $FF
                cp   (hl)
                ld   b, LOG_COLS
                call nz, r20_fill
                ; fall through
;------------------------------------------------------------------------------
; tt_bal — the balloon to the state wanted: shown iff TV_BSAY, GS_PLAYING, he is
; stamped (TV_STAMP) in CUR_ROOM (TV_ROOM = CUR_ROOM: tt_glob has seen the room);
; kept if already placed for this spot + facing (TV_BKEY), else hidden and
; placed anew (tt_bput). Clobbers: all but IX.   ~0.3k kept / hidden-idle
;------------------------------------------------------------------------------
tt_bal:
                ld   a, (TV_BSAY)
                or   a
                jr   z, tt_bhide
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                jr   nz, tt_bhide
                ld   a, (TV_STAMP)
                or   a
                jr   z, tt_bhide
                ld   a, (CUR_ROOM)
                ld   hl, TV_ROOM
                cp   (hl)
                jr   nz, tt_bhide
                ld   c, a
                ld   a, (TV_SPOT)
                call tt_spot                   ; HL = room, col, row
                ld   a, c
                cp   (hl)
                jr   nz, tt_bhide
                ld   a, (TV_IMG)
                rrca                           ; MENTOR_LEFT -> bit 7
                and  $80
                ld   c, a
                ld   a, (TV_SPOT)
                or   c
                ld   c, a                      ; the key
                ld   a, (TV_BCOL)
                or   a
                jr   z, .new                   ; none placed (a failed try retries here)
                ld   a, (TV_BKEY)
                cp   c
                ret  z                         ; placed for this spot + facing: kept
.new:           push hl
                push bc
                call tt_bhide
                pop  bc
                pop  hl
                ld   a, c
                ld   (TV_BKEY), a
                jr   tt_bput
                ASSERT MENTOR_LEFT == 1

;------------------------------------------------------------------------------
; tt_bhide — the balloon out (if placed): its cells that still hold a balloon id
; back to T_AIR + rect_repaint (the next render draws them); inside a hold
; (TV_HOLD: its frames present without rendering; review C) also tile_rect +
; pmark_rect now, as tt_bput, unless a body touches the 2x2 (tt_bfree: then the
; queued restore after the hold draws it, under the sprite); only the state when
; the room changed under it (tt_glob not run yet). Clobbers: all but IX.
;------------------------------------------------------------------------------
tt_bhide:
                ld   hl, TV_BCOL
                ld   a, (hl)
                or   a
                ret  z
                ld   (hl), 0
                ld   c, a
                ld   a, (CUR_ROOM)
                ld   hl, TV_ROOM
                cp   (hl)
                ret  nz                        ; another map: nothing of ours in it
                ld   a, (TV_BROW)
                ld   b, a
                call tt_bmap
                call .cl
                inc  l
                call .cl
                ld   a, l
                add  a, ROOM_COLS - 1
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                call .cl
                inc  l                         ; (x <= 30: no row / page cross from col x to x + 1)
                call .cl
                ld   de, (2 << 8) | 2
                push bc
                call rect_repaint
                pop  bc
                ld   a, (TV_HOLD)
                or   a
                ret  z
                call tt_bfree                  ; CF: all 4 cells T_AIR now, no body on them
                ret  nc
                jp   tt_bdraw                  ; drawn now (a hold renders nothing)
.cl:            ld   a, (hl)
                sub  BAL_ID0
                cp   4
                ret  nc                        ; not ours (left alone)
                ld   (hl), T_AIR
                ret

;------------------------------------------------------------------------------
; tt_bput — HL = his spot (room, col, row), C = the key (bit 7 = facing left):
; the first free 2x2 (tt_bfree) beside his head gets the balloon: BAL_TRY
; positions on the side he faces, nearest first, then BAL_TRY on the other side
; (the nearest free area; the tail always points at him: as drawn = lower left
; on his right side, mirrored on his left side, so in front of him it follows
; his facing). Placed: glyphs (tt_bgly), the ids in ROOM_MAP, rect_repaint (attr
; shadow + queued restore: the next render draws it); inside a hold (TV_HOLD) also
; tile_rect + pmark_rect (a hold presents without rendering). None free: nothing.
; Clobbers: all but IX.   ~1-3k the search, ~2-4k the placement
;------------------------------------------------------------------------------
tt_bput:
                inc  hl
                ld   d, (hl)                   ; col
                inc  hl
                ld   a, (hl)                   ; row
                ld   e, 0
                cp   STOREY_ROWS
                jr   c, .s0
                ld   e, STOREY_ROWS            ; storey 1: its top row
.s0:            sub  2                         ; 2 rows above his top ..
                jr   c, .lo
                cp   e
                jr   nc, .ok
.lo:            ld   a, e                      ; .. clamped to the storey's top
.ok:            ld   b, a                      ; B = the balloon's top row
                ld   a, c
                rlca
                and  1
                ld   c, a                      ; C = the side he faces (1 = his left)
                push bc
                call .side
                pop  bc
                ret  c
                ld   a, c
                xor  1                         ; then the other side; none: skip this showing
; .side — A = side (0 his right, 1 his left), B = row, D = his col: CF = placed.
; Keeps B, D.
.side:          push de
                or   a
                ld   a, d
                ld   d, 1                      ; step right
                jr   z, .r
                sub  5                         ; his left: col - 2 (= col + 3 - 5) ..
                ld   d, -1                     ; .. stepping left
.r:             add  a, 3                      ; his right: col + 3 (past the 3-col box)
                ld   c, a
                ld   e, BAL_TRY
.try:           call tt_bfree
                jr   c, .put
                ld   a, c
                add  a, d
                ld   c, a
                dec  e
                jr   nz, .try
                pop  de
                or   a                         ; CF = 0: not on this side
                ret
.put:           ld   a, c
                ld   (TV_BCOL), a
                ld   a, b
                ld   (TV_BROW), a
                ld   a, d
                rla                            ; CF = his left side: mirrored
                sbc  a, a
                add  a, 2                      ; 2 = his right side's glyphs, 1 = his left side's
                ld   hl, TV_BGLY
                cp   (hl)
                jr   z, .gok                   ; installed already (-1..2.3k T)
                ld   (hl), a
                push bc
                rra                            ; (1: CF = 1 = mirrored; 2: CF = 0)
                call tt_bgly
                pop  bc
.gok:           call tt_bmap
                ld   (hl), BAL_ID0
                inc  l
                ld   (hl), BAL_ID0 + 1
                ld   de, ROOM_COLS - 1
                add  hl, de
                ld   (hl), BAL_ID0 + 2
                inc  l
                ld   (hl), BAL_ID0 + 3
                ld   de, (2 << 8) | 2
                push bc
                call rect_repaint              ; the bank-7 attr shadow + the queued restore (the next
                pop  bc                        ; render draws it: play ticks pay no tile_rect)
                ld   a, (TV_HOLD)
                or   a
                call nz, tt_bdraw              ; a hold presents without rendering: drawn now
                pop  de
                scf
                ret
; tt_bdraw — the 2x2 at C = col, B = row drawn from ROOM_MAP into bank 5 and
; marked for present (no body on it: the callers' tt_bfree). Clobbers: A, DE, HL.
tt_bdraw:
                push bc
                ld   de, (2 << 8) | 2
                call tile_rect
                pop  bc
                ld   de, (2 << 8) | 2
                jp   pmark_rect

; tt_bfree — C = col x, B = row: CF = 1 if x is 1..30, the 2x2's ROOM_MAP cells
; are T_AIR and neither live body's box (cols E_X-1..E_X+4, rows E_Y..E_Y+5)
; touches it. Review D: D0's only bodies are the hero (slot 0) and the Goblin
; (TV_GOB, $FF out of C; tt_snap) — LP_TOTAL 1, no trickle, no follower — so
; those two are tested, not the 16 slots (~1k T a candidate -> ~0.2k; up to 6
; candidates a placement). Clobbers: A, HL (BC, DE, IX kept).   ~0.3k T
tt_bfree:
                ld   a, c
                dec  a
                cp   ROOM_COLS - 2
                ret  nc                        ; col 0 / 31+ / a wrapped negative
                call tt_bmap
                ld   a, (hl)
                inc  l
                or   (hl)
                push de
                ld   de, ROOM_COLS
                add  hl, de
                or   (hl)
                dec  l
                or   (hl)                      ; (OR: CF = 0)
                pop  de
                ret  nz                        ; a cell not T_AIR
                ld   hl, P_ENTITIES            ; the hero
                call .one
                ret  nc                        ; busy
                push de
                call tt_gobp                   ; NZ: HL = the Goblin's slot (DE scratch)
                pop  de
                scf
                ret  z                         ; no Goblin here: free
; .one — HL = a slot: CF = 1 if it is not EF_ACTIVE or its box does not touch the 2x2. Keeps BC, DE.
.one:           inc  l
                inc  l                         ; E_FLAGS
                bit  0, (hl)                   ; EF_ACTIVE
                scf
                ret  z
                inc  l                         ; E_X
                ld   a, (hl)
                sub  c
                add  a, 4
                cp   7
                ccf
                ret  c                         ; cols apart: free
                inc  l                         ; E_Y
                ld   a, (hl)
                sub  b
                add  a, 5
                cp   7
                ccf                            ; rows touch (CF was 1): busy, CF = 0
                ret
                ASSERT EF_ACTIVE == 1 && T_AIR == 0 && PLAY_ROWS >= 2 * STOREY_ROWS
                ASSERT E_FLAGS == 2 && E_X == 3 && E_Y == 4 && (P_ENT_STRIDE & 7) == 0 && (P_ENTITIES & 7) == 0

; tt_bmap — C = col, B = row: HL = ROOM_MAP + 32 x row + col. Clobbers: A.
tt_bmap:
                ld   l, b
                ld   h, ROOM_MAP >> 13         ; HL = ROOM_MAP / 32 + row ..
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; .. x 32
                ld   a, l
                or   c
                ld   l, a
                ret
                ASSERT (ROOM_MAP & $1FFF) == 0

; tt_bgly — CF = 0: the balloon's 4 glyphs as drawn into ids BAL_ID0..+3;
; CF = 1 (on his left side): mirrored (tile k <- tile k xor 1, every byte
; through BITREV_TAB); attrs := balloon_attr, flags := 0. Clobbers: A, BC, DE, HL.
tt_bgly:
                ld   de, BAL_GLY
                jr   c, .lf
                ld   hl, balloon
                ld   bc, 32
                ldir
                jr   .af
.lf:            ld   c, 0
.k:             ld   a, c
                xor  1
                add  a, a
                add  a, a
                add  a, a
                ld   hl, balloon
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a                      ; HL = balloon + 8 x (k xor 1) (any alignment)
                ld   b, 8
.b:             ld   a, (hl)
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                pop  hl
                ld   (de), a
                inc  hl
                inc  de
                djnz .b
                inc  c
                bit  2, c
                jr   z, .k
.af:            ld   a, (balloon_attr)
                ld   hl, TILE_ATTRS + BAL_ID0
                ld   b, 4
                call r20_fill
                xor  a
                ld   hl, tile_flags + BAL_ID0  ; not solid / attackable while it is a balloon
                ld   b, 4
                jp   r20_fill
                ASSERT (BITREV_TAB & $FF) == 0 && balloon_bal_tr == balloon + 8 && balloon_bal_br == balloon + 24

;------------------------------------------------------------------------------
; tt_unhook — every D0 exit (blob_choice: death, Quit, choice 2 / BREAK, the
; first offer too; tt_reset: the grate step): the SMC operands back (pl_et,
; pi_ic, il_go, TUT-KEY item_depth's digit) and the lectern's ids as boot left
; them (glyphs = bal_lect, attrs ATTR_LECT_*, flags TF_SOLID | TF_ATTACK).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
tt_unhook:
                ld   hl, end_turn
                ld   (pl_et + 1), hl           ; SMC target (main.asm play_loop)
                ld   hl, intent_icon7
                ld   (pi_ic + 1), hl           ; SMC target (io.asm intent_tick, TUT0-R2)
                ld   hl, item_log0
                ld   (il_go + 1), hl           ; SMC target (panel2.asm item_log, MORROW-SPEAK)
                ld   a, BANK_TEXT
                ld   (il_go + 4), a
                ld   a, '0'
                ld   (item_depth.d + 1), a     ; SMC target (panel_hot.asm item_depth, HOT_COPY; TUT-KEY)
                ld   hl, bal_lect
                ld   de, BAL_GLY
                ld   bc, 32
                ldir
                ld   hl, TILE_ATTRS + BAL_ID0
                ld   (hl), ATTR_LECT_TOP
                inc  l
                ld   (hl), ATTR_LECT_TOP
                inc  l
                ld   (hl), ATTR_LECT_FOOT
                inc  l
                ld   (hl), ATTR_LECT_FOOT
                ld   a, TF_SOLID | TF_ATTACK
                ld   hl, tile_flags + BAL_ID0
                ld   b, 4
                jp   r20_fill
; tt_hook — tut_d0: item_log's farb -> blob_log (with pl_et / pi_ic); TUT-KEY:
; item_depth's `add a, '0'` operand := '0' - 1, so every panel depth redraw while
; D0 runs (PD_DEPTH: the key pickup / the unlock queue it for the key cells; D0
; runs with LVL_DEPTH 1) prints "D0" — no "D1" flash between the bump's input
; tick and the blob's turn end, 0 resident bytes. Clobbers: A, HL.
tt_hook:
                ld   hl, blob_log
                ld   (il_go + 1), hl           ; SMC target (panel2.asm item_log)
                ld   a, BANK_BLOB
                ld   (il_go + 4), a
                ld   a, '0' - 1
                ld   (item_depth.d + 1), a     ; SMC target (panel_hot.asm item_depth: "D0")
                ret
                ASSERT LVL_DEPTH == LVL_HDR    ; D0's LVL_DEPTH = 1 (tut_blob.asm ASSERTs the image): 1 + '0' - 1 = '0'
                ASSERT {b il_go} == $21 && {b il_go + 3} == $0E && {il_go + 1} == item_log0 && {b il_go + 4} == BANK_TEXT

; bal_lect — tiles_common_glyphs ids 15..18 (the Sanctum lectern), restored by
; tt_unhook (the boot block that loaded them is gone; tests/tut0.py C29 compares
; these bytes with assets/gfx/tiles/tiles_common.asm).
bal_lect:       DEFB $00,$02,$3D,$42,$5A,$42,$5A,$7E    ; 15 T_LECT_TL
                DEFB $00,$40,$BC,$42,$DA,$42,$5A,$7E    ; 16 T_LECT_TR
                DEFB $FF,$7F,$0F,$03,$03,$03,$07,$1F    ; 17 T_LECT_BL
                DEFB $FF,$FE,$F0,$C0,$C0,$C0,$E0,$F8    ; 18 T_LECT_BR

                INCLUDE "../assets/gfx/mentor/balloon.asm"   ; the balloon (4 tiles + attrs, gfx_convert --mode tile)
