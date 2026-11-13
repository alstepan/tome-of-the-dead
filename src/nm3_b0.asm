;==============================================================================
; nm3_b0.asm — NEW-MON3 T1 FUND (2026-11-13; docs/design/new_monsters.md §2 / §12,
; memory-map "NEW-MON3 T1 ledger"): cold code moved into bank-0 B0_CODE2 to fund the
; batch's bank-2 FRT page step, the bank-3 A-1 hook, the low-RAM descriptors and the
; R6 F-1 / P-1 code. Behaviour byte-identical. B0CODE rules: entered by FARB0 (or a
; direct call from code already in bank 0); never pages $C000 itself (far3 / far6 /
; far7 / far1 and the restoring helpers hand bank 0 back); no SMC, no runtime-written
; bytes; data read only with bank 0 paged. Everything here is per event (a level, a
; lair unit, a log line, a panel redraw, a key press, an end-screen tick).
;==============================================================================

;------------------------------------------------------------------------------
; lp_hdr0 — lp_budget's header (FARB0 from bank 3, once a level, right after
; level_gen): LP_STATE zeroed, then the depth row lp_dtab[LVL_DEPTH - 1] ->
; LP_KINDS, LP_BOSS, LP_TOTAL. Was inline in lp_budget with lp_dtab in bank 3
; (-74 B there). A-1 (the row-31 alias) hooks in here.
; Clobbers: A, BC, DE, HL.   ~0.6k T (+ FARB0 ~0.25k)
;------------------------------------------------------------------------------
lp_hdr0:
                ld   hl, LP_STATE
                ld   de, LP_STATE + 1
                ld   bc, LP_LEN - 1
                ld   (hl), 0
                ldir
                ld   a, (LVL_DEPTH)
                ld   b, a
                add  a, a
                add  a, b
                add  a, a                      ; 6 d (row d - 1 from lp_dtab - 6)
                ld   hl, lp_dtab - LP_DROW
                ld   e, a
                ld   d, 0
                add  hl, de                    ; (hla is bank 3: inline)
                ld   de, LP_KINDS
                ld   bc, LP_DROW
                ldir                           ; LP_KINDS, LP_BOSS, LP_TOTAL
                ret
                ASSERT LP_BOSS == LP_KINDS + 4 && LP_TOTAL == LP_KINDS + 5
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 4) >> 8)    ; lp_enter .mw: inc e

;------------------------------------------------------------------------------
; Per-depth budget rows (game.md §9.4 table): 4 kinds in table order, boss,
; count incl. boss (3F-T3: real kind ids, defs.asm). 3F-T5: the golden depths (D1-D3, D5, D6, §9.7
; R1) carry LEK_GOLD in the boss byte (levelgen.py k3_boss); the entity bit is E_GOLD.
; NEW-MON3 T1: bank 0 (was bank-3 lpop3.asm); read by lp_hdr0 and the assembler's pool /
; seq-cache sims (main.asm, MMU 3 = BANK_TEXT), tests/endcard_k.py (.sna bank 0).
;------------------------------------------------------------------------------
lp_dtab:        DB   K_RAT, K_BAT, K_SLIME, K_GOBLIN,          K_BOSS_D1 | LEK_GOLD, 13
                DB   K_GOBLIN, K_SPIDER, K_BAT, K_RAT,         K_BOSS_D2 | LEK_GOLD, 14
                DB   K_SKELETON, K_VAMPIRE, K_GHOST, K_BAT,    K_BOSS_D3 | LEK_GOLD, 14
                DB   K_ORC, K_RAT, K_SPIDER, K_ARCHER,         K_BOSS_D4, 15
                DB   K_MUMMY, K_SKELETON, K_ARCHER, K_SPIDER,  K_BOSS_D5 | LEK_GOLD, 16
                DB   K_VAMPIRE, K_GHOST, K_NECRO, K_ORC,       K_BOSS_D6 | LEK_GOLD, 15
                DB   K_ORC, K_NECRO, K_GHOST, K_NECRO,         K_BOSS_D7, 15   ; 3F-T13bc ARCHER-DEPTHS H1: the 2nd Necro replaces the Archer (weight 6 = 6)
                DB   K_NECRO, K_SKELETON, K_GHOST, K_VAMPIRE,  K_BOSS_D8, 12
LP_DROW         EQU 6
                ASSERT $ - lp_dtab == LEVELS * LP_DROW

;------------------------------------------------------------------------------
; lp_post (boss0.asm, was R6 boss6.asm): FARB0 from bank-3 lp_enter, once per lair unit.
;------------------------------------------------------------------------------
                INCLUDE "boss0.asm"

;------------------------------------------------------------------------------
; The panel items (bars + 2-digit numbers): item_hp (was HOT_COPY), item_mp (was bank-2
; xp2.asm), item_food (hunger0.asm, was R6 hunger6.asm), their helpers bars_draw / num2
; (bars0.asm, was bank-2 bars2.asm, called directly here). Entries by FARB0 from
; panel_step / panel_more (any frame for HP / MP, a 1st frame for FOOD).
;------------------------------------------------------------------------------
;------------------------------------------------------------------------------
; item_hp — HP bar + 2-digit number (row 21, cols 1..6). FARB0 from HOT_COPY item_hp_far
; (panel_step). Clobbers: all but IX, IY.   ~4.5k T (+ FARB0 ~0.25k)
;------------------------------------------------------------------------------
item_hp:
                ld   hl, PANEL_DIRTY           ; (farb took HL for the target)
                res  PD_HP_BIT, (hl)
                ld   a, $80                    ; IC1: HP / MAXHP moved -> the quick potion
                ld   (QS_RECHK), a             ; pick may (icon_poll: a 1st-frame pass)
                ld   hl, (P_ENTITIES + E_HP)
                ld   (PANEL_HP_SH), hl         ; HP and MAXHP as drawn
                ld   d, h
                ld   a, l
                ld   hl, HP_BAR_ADDR
                call bars_draw
                ld   a, (PANEL_HP_SH)
                call num2
                ld   b, STAT_ROW
                ld   e, HP_NUM_COL * 8
                call print6
                ASSERT ((HP_NUM_COL * 8) & 7) == 0 && HP_NUM_COL * 8 + 6 * 2 <= 256   ; print6 x rule
                ld   bc, (STAT_ROW << 8) | HP_BAR_COL   ; (UX1 F2: the HP number's FLASH is rebuilt
                ld   de, ((HP_NUM_COL + 2 - HP_BAR_COL) << 8) | 1   ; from state by bank-0 ux_tick,
                jp   pmark_rect                ; every 1st-frame tick: W15's 2nd-frame HP item cap)

;------------------------------------------------------------------------------
; item_mp — D3-9b: MP bar (fill MP / MAXMP) + 2-digit MP (row 21, cols 8..13),
; like item_hp. MP_SH = MP as drawn (icon_poll compares it). FARB0 from panel_more.
; Clobbers: all but IX, IY.   ~4.5k T (+ FARB0 ~0.25k)
;------------------------------------------------------------------------------
item_mp:
                ld   hl, PANEL_DIRTY           ; (farb took HL for the target)
                res  PD_MP_BIT, (hl)
                ld   a, $80                    ; IC1: MP / MAXMP moved -> the quick potion
                ld   (QS_RECHK), a             ; pick may (icon_poll: a 1st-frame pass; set
                                               ; here, once per draw: the poll would re-set
                                               ; it every step until MP is drawn, starving it)
                ld   a, (MAXMP)
                ld   d, a                      ; (MAXMP 0 draws an empty bar)
                ld   a, (MP)
                ld   (MP_SH), a
                ld   hl, MP_BAR_ADDR
                call bars_draw
                ld   a, (MP_SH)
                call num2
                ld   b, STAT_ROW
                ld   e, MP_NUM_COL * 8
                call print6
                ASSERT ((MP_NUM_COL * 8) & 7) == 0 && MP_NUM_COL * 8 + 6 * 2 <= FOOD_LBL_COL * 8   ; print6 x rule
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL
                ld   de, ((MP_NUM_COL + 2 - MP_BAR_COL) << 8) | 1
                jp   pmark_rect
MP_BAR_ADDR     EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | MP_BAR_COL

                INCLUDE "hunger0.asm"
                INCLUDE "bars0.asm"

;------------------------------------------------------------------------------
; item_log0 — item_log's line (bank 2 keeps the empty-queue test and FARB0s here; the
; FARB0 replaces the old FARB0 log_scroll: same per-line cost). log_scroll (row 23 ->
; 22, row 23 cleared), then the whole line on row 23 (print6t: it pages BANK_TEXT and
; hands bank 0 back), next ring slot, LOG_QN -= 1, PD_LOG cleared at 0.
; Clobbers: all but IX, IY.   ~23k T for 32 chars (W15)
;------------------------------------------------------------------------------
item_log0:
                call log_scroll                ; (b0_code logsc0.asm: bank 0 is paged, a direct call)
                ld   a, (LOG_Q + LQ_RD)
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   l, a
                ld   h, LOG_TXT >> 8
                ld   b, LOG_ROW + 1
                ld   e, 0                      ; (x 0: a multiple of 8; 32 chars = 192 px)
                call print6t
                ASSERT LOG_ROW + 1 < 24 && 6 * LOG_MAX <= 256
                ld   a, e
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F                       ; cols holding ink now (row 23 was cleared)
                ld   hl, HUD4_EXT + 3          ; row 23
                ld   (hl), a
                ld   l, (HUD4_PW + 3) & $FF
                cp   (hl)
                jr   c, .w
                ld   (hl), a
.w:             ld   a, 1
                ld   (PRES_ANY), a
                ld   hl, LOG_TURN              ; T7: LT_SERVED (end_turn: the log was
                set  0, (hl)                   ; not starved this turn)
                ASSERT LT_SERVED == 1
                ld   hl, LOG_Q + LQ_RD
                ld   a, (hl)
                inc  a
                and  LOG_SLOTS - 1
                ld   (hl), a
                ld   hl, LOG_QN
                dec  (hl)
                ret  nz
                ld   hl, PANEL_DIRTY
                res  PD_LOG_BIT, (hl)
                ret
                ASSERT (HUD4_EXT >> 8) == ((HUD4_PW + 3) >> 8)


;------------------------------------------------------------------------------
; end_scr0 — end_screen's body (GS_DEAD / GS_WIN, every end-screen tick; FARB0 from bank-2
; end_screen): L = 0 the next tick (play_loop), L = 1 ENTER -> the menu (enter_select).
; panel_tick / keys_down are bank 2, end_card bank 1 (far1): all hand bank 0 back.
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
end_scr0:
                ; END-WAIT (user 2026-11-04): the final scene stays up first and the card waits for a key.
                ; END_SHOWN (start_game sets END_DELAY; bit 7 = ES_CARD, the card is up): the low nibble
                ; is a quiet countdown, one per tick with no key down, a key reloads it (a panicked press at
                ; death neither skips the scene nor ends the wait early). 0 + a key: the card is drawn
                ; (ES_CARD | END_DELAY: the same quiet again, so a key that is still down never reaches
                ; the menu); the card's 0 + a key: the menu. add a,a: Z = 0 / $80 (terminal), C = card.
                ; panel_tick (clobbers all) draws the lethal turn's log line / HP 0; once everything is
                ; drawn it only polls, so it is harmless over the card too (3 B instead of a card test).
                call panel_tick
                call keys_down                 ; raw 1..0 / ENTER (not FIRE: a held FIRE cannot skip)
                ld   hl, END_SHOWN
                ld   a, (hl)
                jr   z, .nokey
                add  a, a
                jr   z, .act
                ld   a, (hl)
                or   END_DELAY                 ; = $0F: the countdown restarts, the card bit stays
                ld   (hl), a
                jr   .pl
.nokey:         add  a, a
                jr   z, .pl                    ; terminal: waiting for a key
                dec  (hl)
.pl:            ld   l, 0                      ; the next tick (end_screen: jp play_loop)
                ret
.card:          ld   (hl), ES_CARD | END_DELAY
                ld   hl, end_card              ; bank 1 (menu1.asm)
                call far1
                jr   .pl
.act:           jr   nc, .card
                ld   l, 1                      ; ENTER: the menu (end_screen falls into enter_select)
                ret

;------------------------------------------------------------------------------
; hit_line — the spell / dagger / arrow hit line as a token stream (no tx_dec
; decode: ~1.4k T vs ~5k for msg_cat + msg_kind): pre string A (TX_SPL_SPARK + ABL_*;
; LOG-DMG: or TX_YOU_KILL, ammo_fire's kill) + kind E's name, like impact_line
; (lowram.asm; no sfx_msg: the release sound is sfx_abl's, a kill's SFX_KILL is
; requested by ln_hit). LOG-DMG: bank-0 ln_hit (log0.asm) appends pf_tgt's
; " -D HP H" (D = pf_lost) and pushes. The caller made room (log_room).
; NEW-MON3 T1: bank 0 (was bank-2 msg2.asm with B = pre, C = kind and its own BANK_TEXT
; page / restore): FARB0 from bank-7 ammo_fire, BANK_TEXT already paged.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
hit_line:
                ld   c, e                      ; C = kind (impact_line.cat keeps BC)
                ld   de, MSG_BUF
                call impact_line.cat           ; + the pre stream (A)
                ld   a, c
                add  a, TX_NM_KNIGHT
                call impact_line.cat           ; + the kind name
                jp   ln_hit                    ; LOG-DMG (bank 0): + the tail, 0, log_push

;------------------------------------------------------------------------------
; try_close — key C (3B stand-in, game.md §1.4 / §2.3), IX = hero. Legal
; when standing, no hostile in reach on either side, and the faced side has
; an open (so unlocked) door on the hero's storey, adjacent (x + w = 30 /
; x = 2), its 2 x 8 cells (lintel .. planks) free of bodies. NEW-MON3 T1: bank 0, the tail
; of bank-7 ic_melee (FARB0, once a C-key press): L = 1 closed (1 turn), L = IC_NOTGT refused
; (no turn; was CF out from low RAM).  Clobbers: all but IX; TMP0..TMP7.
;------------------------------------------------------------------------------
try_close:
                call is_standing
                jr   nz, .no
                ld   a, 1                      ; dx = facing
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .f
                ld   a, $FF
.f:             ld   (TMP6), a
                call get_box                   ; C = x, D = w
                ld   a, d
                ld   (TMP4), a                 ; w
                ld   a, (TMP6)
                dec  a
                ld   a, c
                jr   nz, .lft
                add  a, d
                cp   ROOM_COLS - DOOR_COLS     ; right: x + w == 30
                jr   .adj
.lft:           cp   DOOR_COLS                 ; left: x == 2
.adj:           jr   nz, .no
                call storey_ref
                ld   (TMP7), a
                ld   a, (TMP6)
                call door_find                 ; HL = edge, C = door col, B = plank top
                jr   nc, .no                   ; no exit on that side
                ld   a, (hl)
                and  EG_DOOR | EG_OPEN | EG_LOCK | EG_SEAL
                cp   EG_DOOR | EG_OPEN
                jr   nz, .no
                ld   a, (TMP7)                 ; the door is on the hero's storey
                MUL_STOREY d
                add  a, DOOR_PLANK_DY
                cp   b
                jr   nz, .no
                push hl
                push bc
                ld   a, b
                sub  DOOR_PLANK_DY
                ld   b, a                      ; B = 9s (lintel row)
                ; door cells (2 x 8 from the lintel) free of EVERY body of the
                ; room, PENDING arrivals included (a follower parked at x = 1)
                ld   de, (DOOR_COLS << 8) | STOREY_AIR
                xor  a
                call room_bodies
                jr   c, .nop
                ; no living hostile within 2 cols of the hero or the door
                ; (game.md §2.3, designer 2026-10-03): gap <= 2 empty cols, so
                ; the hero + door span widened by 3 cols, over the storey's air
                ; rows (the other side of the span is the room edge)
                ld   a, c
                or   a
                ld   a, (P_ENTITIES + E_X)
                jr   z, .hl
                sub  3                         ; right door: from x - 3, 32 cols (the
                ld   c, a                      ; excess right of col 31 holds nobody)
                ld   d, ROOM_COLS
                jr   .hs
.hl:            ld   hl, TMP4                  ; left door: cols 0 .. x + w + 2
                add  a, (hl)
                add  a, 3
                ld   d, a
.hs:            ld   a, EF_HOSTILE
                call room_bodies
.nop:           pop  bc
                pop  hl
                jr   c, .no
                res  EG_OPEN_BIT, (hl)
                ld   a, 1
                call door_paint                ; (low RAM: restores bank 0)
                ld   l, 1                      ; closed: the turn
                ret
.no:            ld   l, IC_NOTGT               ; refused: ic_melee's .nt
                ret

;------------------------------------------------------------------------------
; room_bodies — CF = 1 if an entity in slots 1..15 is ACTIVE, in CUR_ROOM,
; not DYING, has every flag of A (0 = any body; PENDING ones count), and its
; box overlaps box C,B,D,E.  Keeps BC, DE.  Clobbers: A, HL, IX (= hero on
; return), TMP5.
;------------------------------------------------------------------------------
room_bodies:
                or   EF_ACTIVE
                ld   (TMP5), a
                ld   ix, P_ENTITIES
                ld   l, P_MAX_ENT - 1
.l:             push hl
                push de
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                ld   a, (TMP5)
                ld   h, a
                ld   a, (ix+E_FLAGS)
                and  h
                cp   h
                jr   nz, .n
                bit  EF_DYING_BIT, (ix+E_FLAGS)
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call box_vs_ix                 ; keeps BC, DE
                jr   c, .hit
.n:             pop  hl
                dec  l
                jr   nz, .l
                ld   ix, P_ENTITIES
                or   a
                ret
.hit:           pop  hl
                ld   ix, P_ENTITIES
                scf
                ret

