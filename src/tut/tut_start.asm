;==============================================================================
; tut_start.asm — TUT0-T6: the choice screen + the D0 start (blob, bank 4).
; docs/design/tut0_split.md "T6"; spec docs/design/tutorial_d0.md §1, §2.4, §5.2.
; Blob rules (tut_blob.asm header): every resident routine that pages $C000
; is reached through farb with C = BANK_BLOB (or is a save-shadow /
; restore_page helper: rect_repaint); never pages $C000 itself, except the
; final tail jump into page_bank (the blob is not executed after it).
; No writable data in the blob (tests compare it to the image): scratch
; lives in PF_RAM (free at menu / level-start time: no turn is running).
;==============================================================================
TUT_FOOD        EQU 40                  ; spec §2.4: FOOD := 40 (stage OK)
TUT_GOB_SLOT    EQU 1                   ; the parked Goblin's entity slot
TUT_GOB_SLEEP   EQU STS_MAX_TURNS       ; ASLEEP timer (hi nibble of ST_T1)
MENTOR_ATTR     EQU $05                 ; F1: the mentor's tile attr (cyan on black)
MENTOR_IMG_LEN  EQU 144                 ; one image: 18 cells x 8 B (aldous34.asm)
MENTOR_LEFT     EQU 1                   ; image index = 2 x frame + MENTOR_LEFT
; choice screen / card layout (menu font, 8x16: 2 cell rows per line)
TC_ROW1         EQU 8
TC_ROW2         EQU 11
TC_ROW3         EQU 15
TC_COL          EQU 5                   ; "1  TUTORIAL (DEPTH 0)" (21 chars)
TC_COL3         EQU 2                   ; "BROTHER MORROW WILL TEACH YOU" (29, R2), cols 2..30
TD_ROW1         EQU 10                  ; "DEPTH 0": level_card's col 12
TD_COL1         EQU 12
TD_ROW2         EQU 13                  ; "THE OLD CRYPT" (13 chars), centred
TD_COL2         EQU 9
TD_A_NAME       EQU $46

;------------------------------------------------------------------------------
; blob_choice — from ts_choice (enter_select's es_go) with A = menu_run's hero.
; pl_et and pi_ic (TUT0-R2) are put back FIRST (every D0 exit — death, Quit —
; comes through here). Choice screen; release-first (all keys up once), then
; 1 / ENTER = the tutorial (never returns), 2 = START (es_go := start_game,
; C = hero: ts_choice jumps to start_game, exactly as before T6), BREAK =
; back to the menu (es_go kept: the tutorial is offered again).
; The loop paces on menu_frame = the select_tick test probe.
; Out (START only): C = hero.  Clobbers: all.
;------------------------------------------------------------------------------
blob_choice:
                ld   hl, end_turn
                ld   (pl_et + 1), hl           ; SMC target (main.asm play_loop): undo FIRST
                ld   hl, intent_icon7
                ld   (pi_ic + 1), hl           ; SMC target (io.asm intent_tick, TUT0-R2): undo FIRST
                push af                        ; the hero
                xor  a
                call clear_screen              ; bank 5, shown (enter_select's show_bank5)
                call tsp_install
                ld   bc, (MENU_A_LABEL << 8) | MENU_A_DIGIT
                ld   a, TS_CHOICE1
                ld   de, (TC_ROW1 << 8) | TC_COL
                call tut_line
                ld   bc, (MENU_A_LABEL << 8) | MENU_A_DIGIT
                ld   a, TS_CHOICE2
                ld   de, (TC_ROW2 << 8) | TC_COL
                call tut_line
                ld   bc, (MENU_A_SUB << 8) | MENU_A_SUB
                ld   a, TS_CHOICE3
                ld   de, (TC_ROW3 << 8) | TC_COL3
                call tut_line
                xor  a
                ld   (TSP_REL), a
.w:             call menu_frame                ; frame wait + select_tick probe + input
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, $1F
.all:           and  (hl)                      ; a 0 bit = a key down
                inc  hl
                djnz .all
                cp   $1F
                ld   hl, TSP_REL
                jr   nz, .dn
                ld   (hl), 1                   ; everything released once: presses count
                jr   .w
.dn:            ld   a, (hl)
                or   a
                jr   z, .w                     ; the START key is still held
                ld   a, (KBD_MATRIX + KBROW_CAPSV)
                ld   hl, KBD_MATRIX + KBROW_SPACE
                or   (hl)
                rra
                jr   nc, .brk                  ; CAPS + SPACE
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                rra
                jr   nc, .tut                  ; ENTER
                ld   a, (KBD_MATRIX + KBROW_12345)
                rra
                jr   nc, .tut                  ; 1
                rra
                jr   c, .w                     ; not 2
                call .blip
                ld   hl, start_game
                ld   (es_go + 1), hl           ; SMC target (main.asm enter_select): no offer
                pop  af
                ld   c, a
                ret
                ASSERT KB_ENTER_BIT == 0 && KB_1_BIT == 0 && KB_2_BIT == 1
.brk:           ld   sp, WORKSTORE_TOP         ; as Quit (bank7.asm): the far frames dropped
                jp   enter_select
.tut:           call .blip
                pop  af
                jr   tut_d0
.blip:          ld   a, SFX_MENU
                jp   sfx_req

;------------------------------------------------------------------------------
; tut_d0 — A = hero: start_game's head, the D0 card, the hand-made level, the
; hero, the LP state, the pool, level_show, the "D0" digit, the mentor at A1,
; pl_et := ts_turn, pi_ic := ts_icon (TUT0-R2), then play_loop (never returns). es_go stays = ts_choice
; for the whole D0 run. Cold: ~ a new game.
;------------------------------------------------------------------------------
tut_d0:
                ld   (HERO_KIND), a
                ; --- start_game's head (lowram.asm) ---
                ld   hl, gen_idles             ; pages the pool banks
                call farb4
                ld   hl, pool_hero
                call far6
                ld   hl, gen_list
                call farb4
                call alloc_mark                ; the LEVEL mark
                FARB0 new_game                 ; B0CODE: bank-0 B0_CODE2 (was far7; +2 B)
                ld   a, TUT_FOOD               ; spec §2.4: FOOD 40, stage OK (no line)
                ld   (FOOD), a
                ld   a, HS_OK
                ld   (HSTAGE), a
                ASSERT TUT_FOOD < HS_OK_BELOW && TUT_FOOD >= HS_HUNGRY_BELOW
                ; --- level_enter's head ---
                ld   hl, 0
                ld   (DNG_DWELL), hl
                xor  a
                ld   (SFX_NEXT), a
                ld   a, MUS_ROOM
                ld   (MUS_REQ), a
                ld   a, GS_LEVEL
                ld   (GAME_STATE), a
                ; --- the card: "DEPTH 0" / "THE OLD CRYPT" ---
                ld   a, ATTR_HUD
                call clear_screen
                call tsp_install
                ld   bc, (ATTR_HUD << 8) | ATTR_HUD
                ld   a, TS_CARD_DEPTH
                ld   de, (TD_ROW1 << 8) | TD_COL1
                call tut_line
                ld   bc, (TD_A_NAME << 8) | TD_A_NAME
                ld   a, TS_CARD_NAME
                ld   de, (TD_ROW2 << 8) | TD_COL2
                call tut_line
                ld   hl, present_full
                call farb4
                ; --- the level block (tut0_level.asm; LVL_DEPTH stays 1) ---
                ld   hl, tut0_lvl_state        ; the header less MASTER_SEED (new_game's)
                ld   de, LVL_STATE
                ld   bc, TUT0_HDR_COPY
                ldir
                ld   hl, EDGE_TAB              ; as level_gen's attempt: EDGE_TAB's spare
                ld   de, EDGE_TAB + 1          ; (TRK_*, TOME_*, DN_QN) := 0
                ld   bc, ROOM_DESC - EDGE_TAB - 1
                ld   (hl), 0
                ldir
                ld   hl, tut0_edge_tab
                ld   de, EDGE_TAB
                ld   bc, 6
                ldir
                ld   hl, tut0_room_desc        ; ROOM_DESC + TRAP_LIST + FLOOR_LIST: one run
                ld   de, ROOM_DESC
                ld   bc, LVL_STATE_END - ROOM_DESC
                ldir
                ASSERT tut0_trap_list - tut0_room_desc == TRAP_LIST - ROOM_DESC
                ASSERT tut0_floor_list - tut0_room_desc == FLOOR_LIST - ROOM_DESC
                ASSERT FLOOR_LIST + FLOOR_MAX * FL_STRIDE == LVL_STATE_END
                ; --- the hero (level_populate's part, bank3.asm) ---
                ld   ix, P_ENTITIES
                ld   l, (ix+E_HP)
                ld   h, (ix+E_MAXHP)
                push hl
                ld   a, (ix+E_FLAGS)
                and  HERO_CARRY
                push af
                ld   hl, level_reset
                call far3
                ld   hl, level_start_x         ; B = col (far3 loses A)
                call far3
                ld   ix, P_ENTITIES
                ld   (ix+E_X), b
                ld   a, (LVL_START)
                ld   (CUR_ROOM), a
                ld   (ix+E_ROOM), a
                ld   a, (HERO_KIND)
                ld   (ix+E_KIND), a
                ld   hl, pot_sync              ; R6 (keeps DE, IX)
                call far6
                pop  af
                or   EF_ACTIVE | EF_PLAYER
                ld   (ix+E_FLAGS), a
                ld   (ix+E_Y), 0               ; H1-ARRIVAL: mid-ladder at the shaft top,
                ld   (ix+E_AIDIR), 1           ; heading down
                ld   hl, init_ent_common
                call far3
                pop  hl
                ld   (ix+E_HP), l
                ld   (ix+E_MAXHP), h
                ; --- LP: kinds {Goblin}, no boss, quotas 0, respawns used up ---
                ld   hl, LP_STATE
                ld   de, LP_STATE + 1
                ld   bc, LP_LEN - 1
                ld   (hl), 0
                ldir
                ld   hl, LP_KINDS
                ld   b, 4
.k:             ld   (hl), K_GOBLIN
                inc  l
                djnz .k
                ld   (hl), K_GOBLIN | LEK_GOLD ; LP_BOSS: matches no body (E_GOLD 0): no
                inc  l                         ; guard AI / provoke / follow ban, pool = Goblin
                ld   (hl), 1                   ; LP_TOTAL
                ASSERT LP_BOSS == LP_KINDS + 4 && LP_TOTAL == LP_KINDS + 5
                ld   a, (LVL)
                ld   (LP_LVL), a
                ld   a, RESPAWN_MAX            ; no trickle (LF_UNIQUE silences it too)
                ld   (LP_RESPAWNS), a
                ld   a, ROOM_MAX
                ld   (LP_RMAX), a
                ld   a, LR_VISITED             ; the start room entered (quota 0)
                ld   (LP_REC + TUT0_ROOM_A * LR_STRIDE), a
                ld   a, 1
                ld   (ROOM_VISITS + TUT0_ROOM_A), a
                ; the Goblin: room C's record (VISITED, 1 entry, D1 hp) + its parked
                ; slot (asleep; lp_enter restores it in place at the lair post)
                ld   a, (kind_tab + KT_HP + K_GOBLIN)   ; D1 hp: + depth - 1 = + 0 (kind_hp)
                ld   c, a
                ld   hl, LP_REC + TUT0_GOB_ROOM * LR_STRIDE
                ld   (hl), LR_VISITED | 1
                inc  hl
                ld   (hl), K_GOBLIN
                inc  hl
                ld   (hl), c
                ld   ix, P_ENTITIES + TUT_GOB_SLOT * P_ENT_STRIDE
                ld   (ix+E_KIND), K_GOBLIN
                ld   (ix+E_ROOM), TUT0_GOB_ROOM | LPK_PARK
                ld   (ix+E_FLAGS), EF_HOSTILE  ; parked: EF_ACTIVE clear, != 0
                ld   (ix+E_X), TUT0_GOB_X
                ld   (ix+E_HP), c
                ld   (ix+E_MAXHP), c
                ld   a, (kind_tab + KT_BH + K_GOBLIN)
                ld   b, a
                ld   a, TUT0_GOB_S * STOREY_ROWS + STOREY_AIR
                sub  b
                ld   (ix+E_Y), a
                ld   a, HOLD_ASLEEP
                ld   (ST_FLAGS + TUT_GOB_SLOT), a
                ld   a, TUT_GOB_SLEEP << 4
                ld   (ST_T1 + TUT_GOB_SLOT), a
                ld   a, TUT0_GOB_ROOM          ; lp_bank keeps TRK_PREV's parked slots: the
                ld   (TRK_PREV), a             ; Goblin's survives the first exit A -> B
                ; --- the level pool (level_enter's middle) ---
                call alloc_restore
                ld   hl, pool_list
                call far6
                ld   hl, gen_list
                call farb4
                ld   a, GS_TRANSITION
                ld   (GAME_STATE), a
                ld   a, 1
                ld   e, TX_NONE
                ld   hl, level_show            ; leaves bank 7: farb gives bank 4 back
                call farb4
                ; --- panel depth "D0" (item_depth's draw; its dirty bit dropped) ---
                ld   hl, PANEL_DIRTY
                res  PD_DEPTH_BIT, (hl)
                ld   hl, P_NUMBUF
                ld   (hl), 'D'
                inc  l
                ld   (hl), '0'
                inc  l
                ld   (hl), 0
                ld   l, P_NUMBUF & $FF
                ld   b, ICON_ROW
                ld   e, DEPTH_COL * 8
                call print6
                ld   bc, (ICON_ROW << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                call pmark_rect
                ; --- the turn engine's state, B0's lines, the mentor at A1 (T7) ---
                call tt_init
                ; --- run ---
                ld   hl, ts_turn
                ld   (pl_et + 1), hl           ; SMC target: end_turn -> the turn stub
                ld   hl, ts_icon
                ld   (pi_ic + 1), hl           ; SMC target: intent_icon7 -> the icon stub (R2)
                call play_go
                ld   sp, WORKSTORE_TOP
                ld   hl, play_loop
                push hl
                ld   a, BANK_COLD7             ; as start_game (level_enter leaves bank 7):
                jp   page_bank                 ; tail jump, returns into play_loop

; farb4 — farb with C = BANK_BLOB (A, DE, IX pass in). Clobbers: as farb.
farb4:          ld   c, BANK_BLOB
                jp   farb

;------------------------------------------------------------------------------
; tut_glyphs — A = image index (2 x frame + left; aldous34.asm stores the 7
; RIGHT-facing frames only): source cell i's glyph -> TILE_GLYPHS + id x 8 for
; id i of tut0_mentor_ids (the first TUT0_MENTOR_N = 17: cell 17 is blank in
; every image and takes no id, TUT0-F1), TILE_ATTRS[id] := MENTOR_ATTR,
; tile_flags[id] := 0. LEFT (T7, -1,008 B raw): every byte through BITREV_TAB;
; the column swap is tut_stamp's (tut0_mentor_ids_l), so a facing change needs
; a re-stamp. After level_show (level_load_tiles rewrites 32..63).
; Clobbers: A, BC, DE, HL; TV_MIR.   right ~6k T, left ~10k T
;------------------------------------------------------------------------------
tut_glyphs:
                ld   c, a
                and  MENTOR_LEFT
                ld   (TV_MIR), a
                ld   a, c
                srl  a                         ; frame
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; x 16
                ld   d, h
                ld   e, l
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, de                    ; x 144
                ld   de, sxt34_idle1_r
                add  hl, de                    ; HL = image + 8 x cell (running)
                ld   bc, tut0_mentor_ids
.l:             push bc
                push hl
                ld   a, (bc)                   ; id
                ld   e, a
                ld   d, TILE_ATTRS >> 8
                ld   a, MENTOR_ATTR
                ld   (de), a
                ld   a, e
                add  a, tile_flags & $FF       ; (64 B ending on its page: no carry)
                ld   l, a
                ld   h, tile_flags >> 8
                ld   (hl), 0
                ld   l, e
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   bc, TILE_GLYPHS
                add  hl, bc
                ex   de, hl                    ; DE = the glyph
                pop  hl                        ; HL = source cell i (both paths leave it
                ld   a, (TV_MIR)               ; at cell i + 1)
                or   a
                jr   nz, .m
                ld   bc, 8
                ldir
                jr   .nx
.m:             ld   b, 8
.rv:            ld   a, (hl)
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                pop  hl
                ld   (de), a
                inc  hl
                inc  de
                djnz .rv
.nx:            pop  bc
                inc  bc
                ld   a, c                      ; (low byte only: a page cross is fine, N < 256)
                cp   (tut0_mentor_ids + TUT0_MENTOR_N) & $FF
                jr   nz, .l
                ret
                ASSERT (TILE_ATTRS & $FF) == 0 && (tile_flags & $FF) + TILE_IDS == $100 && (BITREV_TAB & $FF) == 0
                ASSERT SXT34_IMAGES == 7 && SXT34_IMAGES * MENTOR_IMG_LEN == sxt34_fade_r + MENTOR_IMG_LEN - sxt34_idle1_r
                ASSERT TUT0_MENTOR_N == 17
                ASSERT tut0_mentor_ids_l == tut0_mentor_ids + 18

;------------------------------------------------------------------------------
; tut_stamp — A = spot index (tut0_spots): if its room is CUR_ROOM, its 3 x 6
; box's T_AIR / mentor-id cells in ROOM_MAP := the ids of tut0_mentor_ids (or
; tut0_mentor_ids_l if TV_IMG faces left; the blank cell's entry is T_AIR), then
; rect_repaint (attr shadow + queued restore: the next render draws him; it
; restores the caller's bank itself). Re-stamping in place re-orders the ids
; (facing change). Other rooms: nothing. Clobbers: all but IX.   ~4k T + rect_repaint
;------------------------------------------------------------------------------
tut_stamp:
                ld   l, a
                add  a, a
                add  a, l
                ld   l, a
                ld   h, 0
                ld   de, tut0_spots
                add  hl, de
                ld   a, (CUR_ROOM)
                cp   (hl)
                ret  nz
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   b, (hl)                   ; row
                push bc
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; row x 32
                ld   a, l
                or   c
                ld   l, a
                ld   de, ROOM_MAP
                add  hl, de
                ld   de, tut0_mentor_ids
                ld   a, (TV_IMG)
                and  MENTOR_LEFT
                jr   z, .rt
                ld   de, tut0_mentor_ids_l     ; (TUT0-R2: may sit on another page than _r)
.rt:            ld   b, 6
.r:             ld   c, 3
.c:             ld   a, (hl)
                or   a
                jr   z, .w
                sub  TUT0_MENTOR_ID0
                cp   TUT0_MENTOR_N
                jr   nc, .s                    ; neither T_AIR nor his: left alone
.w:             ld   a, (de)
                ld   (hl), a
.s:             inc  de
                inc  hl
                dec  c
                jr   nz, .c
                push de
                ld   de, ROOM_COLS - 3
                add  hl, de
                pop  de
                djnz .r
                pop  bc
                ld   de, (3 << 8) | 6
                jp   rect_repaint
                ASSERT T_AIR == 0

;------------------------------------------------------------------------------
; tut_line — A = TS_/TL_ id, D = row, E = col, C = the first char's attr, B =
; the rest's: the decoded string in the menu font (tsp, PF_RAM; tsp_install
; first). Clobbers: all but IX.
;------------------------------------------------------------------------------
tut_line:
                ld   (TSP_A), bc
                ld   hl, tsp
                jp   farb4

; tsp_install — the PF_RAM helper (below) into place. Clobbers: BC, DE, HL.
tsp_install:
                ld   hl, tsp_img
                ld   de, PF_RAM
                ld   bc, TSP_LEN
                ldir
                ret

;------------------------------------------------------------------------------
; tsp — PF_RAM helper (copied there by tsp_install; PF_RAM is free while no
; turn runs): the blob's text is packed with the RESIDENT dictionary (bank 0)
; and the menu font is bank 1, while the stream is in bank 4: one $C000 bank at
; a time, so: copy the stream to TSP_RAW (bank 4 paged), page BANK_TEXT and
; tk_get it into TX_DEC, page BANK_UI1 and mf_char it, restore the caller's
; bank (a save-shadow / restore_page helper, like msg_push). Control tokens
; 1..5 are not expected here (choice / card strings only; mf_char shows them
; as spaces). In: A = id, D = row, E = col, (TSP_A) = attrs; entered by farb.
; Clobbers: all but IX.   ~2k T + ~1.4k T per char
;------------------------------------------------------------------------------
tsp_img:
                DISP PF_RAM
tsp:            ld   (TSP_POS), de
                ld   l, a
                ld   h, 0
                add  hl, hl
                ld   de, tut_tab
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a                      ; HL = the stream (bank 4)
                ld   de, TSP_RAW
.c:             ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  de
                or   a
                jr   nz, .c
                ld   a, (PORT_7FFD_SHADOW)
                ld   (TSP_SH), a
                ld   a, BANK_TEXT
                call page_bank
                ld   bc, TSP_RAW               ; tk_get state
                ld   de, TX_DEC
.d:             call tk_get
                ld   (de), a
                inc  de
                or   a
                jr   nz, .d
                ld   a, BANK_UI1
                call page_bank
                ld   hl, TX_DEC
                ld   a, (hl)
                or   a
                jr   z, .x
                inc  hl
                push hl
                ld   bc, (TSP_A)
                ld   e, c
                ld   bc, (TSP_POS)             ; C = col, B = row
                call mf_char
                ld   a, (TSP_A + 1)
                ld   (mf_attr), a              ; bank-1 var (paged)
                pop  hl
.n:             ld   a, (hl)
                or   a
                jr   z, .x
                inc  hl
                push hl
                call mf_char_e
                pop  hl
                jr   .n
.x:             ld   a, (TSP_SH)
                jp   restore_page
TSP_POS:        DW   0
TSP_A:          DW   0                         ; low = the first char's attr, high = the rest
TSP_SH:         DB   0
TSP_REL:        DB   0                         ; blob_choice: keys released once
TSP_RAW_AT:
                ENT
tsp_img_end:
TSP_LEN         EQU tsp_img_end - tsp_img
TSP_RAW         EQU TSP_RAW_AT                 ; the raw stream copy (<= TSP_RAW_MAX B)
TSP_RAW_MAX     EQU 64
                ASSERT TSP_RAW + TSP_RAW_MAX <= PF_RAM + PF_RAM_LEN
