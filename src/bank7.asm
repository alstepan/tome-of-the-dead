;==============================================================================
; bank7.asm — D3-S2 bank-7 COLD code, B7_CODE ($DB00, w2a; was $E000) .. b7_end <= B7_LIMIT
; ($F800, the attr shadow): the 6 KB freed by dropping the bitmap shadow.
; Per-turn / per-event logic moved out of bank 2 (docs/memory-map.md "Cold
; code placement"): the player turn (turn_input -> try_player_turn ->
; tpt_intent / try_climb / try_horizontal / find_target), end_turn + do_exit
; + hide_sprites (room exit) + the follower scan / arrival conflicts
; (L-RELIEF, from bank 3), the pause overlay entry; D3-7: the icon bar
; logic (intent7.asm) and the ability / pickup code (abil_*7.asm, pickup7.asm).
; Rules (docs/conventions.md "Banking"):
;  - Entered only through far7 (bank 2: ld c, BANK_COLD7 / farb) — from
;    bank-2, low-RAM, or (nested) bank-3 / bank-1 code. far7 loses A and F:
;    results come back in L / memory.
;  - Bank 7 is also screen 2 ($C000..$DAFF, shown during play): paging it in
;    changes nothing on screen (that is $7FFD bit 3, kept by page_bank);
;    present / present_full / erase_rect / shadow_rect / decor_tick page
;    bank 7 themselves, so calling them from here is safe.
;  - Every callee must hand back bank 7 (or leave it paged): bank-2 / low-RAM
;    helpers that restore the caller's bank, far1 / far3 (nest), erase_rect,
;    shadow_rect, room_shadow, present_full, level_enter. NEVER call a helper
;    that leaves another bank paged (blit_sprite, render, draw_slot, the
;    generator, page_bank) — wrap it in `ld c, BANK_COLD7 / call farb`.
;  - No SMC and no data here: tests/gfx_integrity.py asserts B7_CODE..B7_LIMIT
;    == the .sna image (the canary for the freed bitmap shadow).
;  - Contended bank (7): code fetches pay ULA contention; nothing per-tick.
;==============================================================================

;------------------------------------------------------------------------------
; turn_input — INPUT phase (bank-2 read_turn_input: ld hl / jp far7). Held
; keys repeat unless INPUT_REPEAT = 0 (then a release is required between
; turns, the P3 rule). A legal action resolves the whole turn now and enters
; the ANIM phase. C3-2: intent_tick already sampled this tick; a pending icon
; use (INTENT) goes straight to try_player_turn; while FIRE is held the stick
; is the cursor's; only directions and '.' count as held. D3-7: an ability
; turn (act_begin, act7.asm: MON_AT != 0) leaves its release and the monster
; phase to act_pend (the anim_gate hook) instead.
; Clobbers: all but IY (far7: A, F lost; nothing is returned).
;------------------------------------------------------------------------------
turn_input:
                ld   hl, TRK_PHASE             ; 3F-T12: a due trickle check takes this INPUT
                bit  TRK_DUE_BIT, (hl)         ; tick ALONE (idle: no turn starts, no log line, a
                jr   z, .nd                    ; deferred level-up waits too); the input is read on
                res  TRK_DUE_BIT, (hl)         ; the next tick (40 ms, once per 48 turns). A turn
                                               ; never starts with it set: end_turn sees it clear
                ld   hl, trk_run               ; (R6 trickle6.asm)
                jp   far6
.nd:            ld   a, (XP_UP)                ; D3-9b: a level-up a heavy end_turn tick
                or   a                         ; deferred (xp_level: 1st frame only)
                call nz, xp_level
                ld   a, (ST_FLAGS)             ; D3-8 held hero (FROZEN / ASLEEP / STUNNED,
                and  STS_HOLD                  ; game.md §2.2): input ignored (Pause still
                jr   z, .free                  ; works: intent_tick), a Wait turn without
                xor  a                         ; search every 4 ticks (HELD_WAIT; a pending
                ld   (INTENT), a               ; icon use / DOWN is dropped)
                ld   (DN_COMMIT), a
                ld   hl, HELD_T
                inc  (hl)
                ld   a, (hl)
                cp   HELD_WAIT
                ret  c
                ld   (hl), 0
                jr   .go
.free:          ld   a, (INTENT)
                or   a
                jr   nz, .go
                ld   a, (ICON_MODE)            ; C3-2b: play frozen in ICON MODE
                ld   hl, FIRE_ST
                or   (hl)
                ret  nz
                ld   a, (DN_COMMIT)            ; a released DOWN: a fresh press, not
                or   a                         ; gated by NEED_RELEASE (review: the
                jr   nz, .go                   ; INPUT_REPEAT = 0 soft lock)
                ld   hl, EXIT_LOCK
                or   (hl)                      ; C3-2b: the key that left ICON MODE
                                               ; does nothing until released
                jr   z, .nlk
                ld   a, (PLAYER_DIR)
                or   a
                ret  nz
                ld   (hl), a                   ; released: unlocked
.nlk:
                ld   a, (PLAYER_DISC)
                and  DK_WAIT
                ld   hl, PLAYER_DIR
                or   (hl)
.test:          jr   nz, .held
                xor  a
                ld   (NEED_RELEASE), a
                ld   (LOCK_SHOWN), a           ; B3B-5: next bump may print again
                ld   (TURN_HOLD), a            ; C3-2: a released key ends the delay
                ld   hl, LOG_PDIR              ; T7 review: a tap released while the log
                or   (hl)                      ; hold kept the turn: replay it now
                ret  z
                and  JOY_DIRS
                ld   (PLAYER_DIR), a
                bit  7, (hl)
                jr   z, .go
                ld   hl, PLAYER_DISC
                set  DK_WAIT_BIT, (hl)
                jr   .go
                ASSERT (JOY_DIRS & $80) == 0 && DK_WAIT == 1 << 1
.held:          ld   a, (INPUT_REPEAT)
                or   a
                jr   nz, .go
                ld   a, (NEED_RELEASE)
                or   a
                ret  nz
.go:            ld   a, (LOG_TURN)             ; T7: a starved log (end_turn) holds the turn:
                and  LT_HOLD                   ; one line per tick, drawn HERE (before render:
                jr   z, .run                   ; this tick is idle, ~85-90k T worst seen + <= ~23k T
                ld   a, (LOG_QN)               ; the line < the 126k cap; budget.py "wcast"),
                or   a                         ; until the queue is empty. INTENT / the held key
                jr   z, .run                   ; are kept: the turn starts on the tick after.
                ld   a, (PLAYER_DISC)          ; latch what is held now (a short tap is
                and  DK_WAIT                   ; released before the hold ends)
                rrca
                rrca                           ; DK_WAIT -> bit 7
                ld   hl, PLAYER_DIR
                or   (hl)
                jr   z, .hl
                ld   (LOG_PDIR), a
.hl:            ld   hl, PANEL_DIRTY
                jp   item_log                  ; (bank 2; print6t restores bank 7)
.run:           ld   (LOG_TURN), a             ; A = 0: LT_SERVED / LT_HOLD clear for this turn
                ld   (LOG_PDIR), a             ; (a replayed tap is spent)
                ld   (TURN_TICK), a            ; D3-7: the input tick is TURN_TICK 0
                                               ; (set_reaction_at / pf_tick add it)
                ld   hl, (P_ENTITIES + E_X)    ; 3E-T16: the body before the action (every
                ld   (TRP_PRE), hl             ; try; trap_turn's "first brings it under")
                ASSERT E_Y == E_X + 1
                ld   hl, HST_DONE              ; D3-8: the hero's status step, at the
                or   (hl)                      ; start of his phase (game.md §6.4), once
                jr   nz, .act                  ; per turn: an illegal try (no turn) does
                inc  (hl)                      ; not step again on the next try
                ld   ix, P_ENTITIES
                ld   a, (ST_FLAGS)
                and  STS_HOLD
                push af                        ; NZ: held at the step (the held path)
                xor  a                         ; A = 0 = slot 0
                call st_step                   ; (status7.asm)
                pop  af
                jr   z, .act                   ; free: L = 0 (a step never sets HOLD)
                dec  l
                jr   z, .hw                    ; still held (or cleared now): the Wait
                ld   a, 1                      ; review: woken by the step (poison HP loss):
                ld   (NEED_RELEASE), a         ; no action this tick (the input was ignored);
                ret                            ; HST_DONE stays 1, so the next tick takes
                                               ; .free: a held key is released first unless
                                               ; INPUT_REPEAT
.hw:            call build_live                ; held: the action is skipped = a Wait
                xor  a                         ; without search (try_player_turn's
                ld   (ACT_SLOT), a             ; turn-start state for the monster phase)
                ld   (CLIMB_BLK), a
                call trap_chk                  ; 3E-T16: the held Wait: sense only (TRP_WAIT 0)
                jr   .spent
.act:           call try_player_turn
                ret  nc                        ; illegal: no turn consumed
                call trap_chk                  ; 3E-T16: trigger / search / Mage sense. BEFORE the
                                               ; guard clear (STUN1): a trap armed here keeps
                                               ; HOLD_GUARD to its step (a stone cannot stun on
                                               ; his guarded action, §1.5.1); act_pend clears it
                ld   a, (MON_AT)               ; D3-8f: he acted -> his HOLD_GUARD clears
                or   a                         ; (game.md §6.4 step 4: after the action,
                jr   nz, .spent                ; before the monster phase); an ability
                ld   hl, ST_FLAGS              ; turn resolves at its release: act_pend
                res  STS_GUARD_BIT, (hl)       ; clears it then. (.hw: no action, kept)
.spent:
                xor  a
                ld   (HST_DONE), a             ; the next turn steps again
                ld   a, (CLIMB_BLK)            ; B14: any turn but a blocked-climb
                or   a                         ; wait ends the run of blocks
                jr   nz, .blk                  ; (climb_blocked)
                ld   (CLIMB_BLK_N), a
.blk:
                ld   a, 1
                ld   (NEED_RELEASE), a
                ld   a, (EXIT_KIND)
                ld   hl, MON_AT                ; D3-7: an ability turn (act_begin) defers
                or   (hl)                      ; the monster phase to act_pend
                ld   hl, resolve_monsters      ; B3B-R2: bank 3, one far3 a turn
                call z, far3                   ; exit turn: monsters don't act
                ld   a, TP_ANIM
                ld   (TURN_PHASE), a
                ret

;------------------------------------------------------------------------------
; trap_chk — 3E-T16 (game.md §1.5): turn_input .spent (every accepted turn,
; the held Wait too) and end_turn .ex (the room-entry sense). TRP_WAIT (TRW_*)
; is read and cleared; on an exit / teleport turn (EXIT_KIND set) nothing;
; else the first unspent trap of CUR_ROOM (the generator puts <= 1 in a room)
; -> far6 trap_turn (A = TRW_*, DE = the entry): the DECISION only (trigger /
; Mage sense / search); an event arms the trap sequence (TURN_PEND, ACT_ABL =
; ABL_TRAP: act_pend runs trap_step on the next ticks, then the monsters).
; Clobbers: all but IX, IY.   no trap in the room: ~0.15-0.4k T (TRAP_N
; entries x ~50 T, bank 7 contended); one >= 7 cols off the body: + ~0.1k;
; nearer: + trap_turn (far6, ~0.9k without an event)
;------------------------------------------------------------------------------
trap_chk:
                ld   hl, TRP_WAIT
                ld   d, (hl)                   ; D = TRW_*
                ld   (hl), 0
                ld   a, (EXIT_KIND)
                or   a
                ret  nz
                ld   a, (TRAP_N)
                or   a
                ret  z
                ld   b, a
                ld   a, (CUR_ROOM)
                ld   c, a
                ld   hl, TRAP_LIST
.l:             ld   a, (hl)                   ; TR_B0
                xor  c
                and  TRF_ROOM_MASK | TRF_SPENT
                jr   z, .hit
                inc  l
                inc  l
                djnz .l
                ret
.hit:           inc  l                         ; pre-filter (no far6): the trap col t
                ld   a, (hl)                   ; outside x-6 .. x+8 can neither fire
                dec  l                         ; (x .. x+2), be sensed (x-2 .. x+4)
                and  TR_COL_MASK               ; nor be searched (x-6 .. x+8)
                ld   c, a
                ld   a, (P_ENTITIES + E_X)
                ld   b, a
                ld   a, c
                sub  b
                add  a, TRAP_SEARCH_R
                cp   2 * TRAP_SEARCH_R + TRAP_HERO_W
                ret  nc
                ld   a, d
                ex   de, hl                    ; DE = the entry
                jp   trap_turn                 ; trap7.asm (MEM-RECLAIM w2b: was far6 R6)
                ASSERT TR_B0 == 0 && TRAP_STRIDE == 2 && (TRAP_LIST & $FF) + TRAP_MAX * TRAP_STRIDE <= 256

;------------------------------------------------------------------------------
; end_turn — ANIM finished (play_loop: turn_done CF -> far7): transition (if
; exiting), TURN_COUNTER++, the floor pickup (potions + ammo), death check (B3B-11: messages via
; the log; B3B-13: msg_push), back to INPUT.  Clobbers: all but IY.
;------------------------------------------------------------------------------
LOG_HOLD_MIN    EQU 2
end_turn:
                ; T7 log drain (a heavy fight: every tick of the turn in its 2nd
                ; frame, so panel_tick never draws a line and LOG_SLOTS drops the
                ; newest; budget.py "wcast" dropped 14): LOG_HOLD_MIN+ lines
                ; pending, or any and none drawn since the turn started -> LT_HOLD: turn_input draws one per
                ; tick and starts no turn until the queue is empty. Lines this
                ; end_turn pushes (pickup, death) do not count.  ~60 T
                ld   hl, LOG_TURN
                ld   a, (LOG_QN)
                cp   LOG_HOLD_MIN
                jr   nc, .lh                   ; 2+ pending: hold anyway (the next cast's
                or   a                         ; lines would not fit)
                jr   z, .ls
                bit  0, (hl)
                jr   nz, .ls                   ; LT_SERVED: a line was drawn this turn
                ASSERT LT_SERVED == 1
.lh:            ld   (hl), LT_HOLD
.ls:
                ld   a, (SPQ_K)                ; 3F-T9: the queued spawn (summon / breed / ALARM
                or   a                         ; wave) is made now, never in the cast / input
                jr   z, .nq                    ; tick (R6 spawn6.asm; it empties the queue and
                ld   hl, TRK_PHASE             ; skips it on an exit / a dying hero). 3F-T12: the
                dec  (hl)                      ; trickle phase stands still on this turn, so a
                ld   hl, sp_run                ; check never shares the tick with sp_run (walarm
                call far6                      ; 122.5k + trk_run ~10k > the 126k cap)
.nq:
                ld   a, (EXIT_KIND)
                or   a
                call z, vb_turn                ; 3F-T9: the Vampire's bat form (+ R6 vbat6.asm)
                ld   hl, TRK_PHASE             ; 3F-T12: the level's turn count, BEFORE the exit
                inc  (hl)                      ; (a level change zeroes it: a fresh LVL_STATE)
                ld   a, (EXIT_KIND)
                or   a
                call nz, .ex
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (TURN_COUNTER), hl
                ld   hl, TRK_PHASE             ; 3F-T12: every RESPAWN_PERIOD turns of the level
                ld   a, (hl)                   ; the check is DUE (TRK_DUE = bit 7, count 0); it
                and  TRK_CNT_MASK              ; runs on the next INPUT tick (turn_input), never
                cp   RESPAWN_PERIOD            ; on this heavy turn-ending tick (review: up to
                jr   nz, .nt                   ; 115.8k + 14.1k > the 126k cap)
                ld   (hl), TRK_DUE
.nt:            call floor_pickup              ; pickup7.asm (D3-7 T6: potions + ammo, list-driven;
                                               ; HP / potions reach the panel by panel_tick's poll)
                xor  a
                ld   (TURN_PHASE), a
                ld   (TURN_TICK), a            ; D3-7: 0 throughout INPUT, so the input
                                               ; tick's set_reaction_at / pf_tick add 0
                ld   (COMBAT_NOT_BEFORE), a    ; D3-8e2: the panel gate is per turn
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                jr   nz, .dead
                ld   a, (GAME_STATE)           ; not after a win (game_win: GS_WIN
                cp   GS_PLAYING                ; returns here): the end screen owns the music
                call z, tome_aura              ; SND-3 mus_pick (Dangerous cue, mailbox only), then
                                               ; P3 the Tome's aura (lowram.asm; a kill -> .dead)
                call hunger_turn               ; 3E-T9: FOOD burn / jump cost / stage /
                                               ; FED regen / MP_HOLD (hunger7.asm; w2b: was far6)
                jp   xp_turn                   ; D3-9b: MP regen + level-up (xp7.asm)
                                               ; (B3B-13: the PROTO chest win is gone; P3: a run
                                               ; wins by the Tome's last hit, tome_strike)
.ex:            call do_exit                   ; 3E-T16: + the room-entry Mage sense
                ld   hl, HW_TMR                ; FAINT1: a faint defers across an exit / teleport
                dec  (hl)                      ; (hunger_turn's +1 restores it: the clock stands
                                               ; still on the arrival turn; EXIT_KIND is gone)
                ld   a, TRW_ENTRY              ; (immediate mode, no trigger test:
                ld   (TRP_WAIT), a             ; this is the transition tick)
                jp   trap_chk
    IF DEBUG_KIT
; DBG-1 infinite lives (kit builds only, game.md §1.4): every death reaches here (deal_hit /
; hero_fall EF_DYING, tome_aura's HP 0), so the hero is revived at the death check, 19 B
; = the release .dead: EF_DYING off, HP 1, the held DEATH pose / a pending reaction back
; to standing; no GS_DEAD, no line. The hit, its HURT / DEATH reaction and the log played
; as usual; this turn's hunger step is skipped (the level-up check still runs).
.dead:          ld   hl, P_ENTITIES + E_FLAGS
                res  EF_DYING_BIT, (hl)
                ld   l, (P_ENTITIES + E_HP) & $FF
                ld   (hl), 1
                xor  a                         ; M_REST / RC_NONE
                ld   (P_ENTITIES + E_MODE), a
                ld   (P_ENTITIES + E_REACT), a
                jp   xp_turn
                ASSERT M_REST == 0 && RC_NONE == 0 && (P_ENTITIES >> 8) == ((P_ENTITIES + E_HP) >> 8)
    ELSE
.dead:          xor  a                         ; SND-3: Game Over once (GS_DEAD never reaches
                ld   (MUS_REQ), a              ; end_turn again; end_screen only redraws): final
                ld   a, MUS_OVER               ; cue = loop off, then the shot
                ld   (MUS_SHOT), a
                ld   a, GS_DEAD
                ld   (GAME_STATE), a
                ld   a, TX_DIED
                jp   msg_push_end              ; never dropped (B3B-11b); end_screen drains it
    ENDIF

;------------------------------------------------------------------------------
; vb_turn — end_turn (3F-T9, game.md §9.2 Vampire bat form; no exit this turn):
; picks the bodies that may change form now — a Vampire at the end of an odd
; turn (its rest turn), a bat form (K_VBAT) at the end of an even one — of
; CUR_ROOM, active, not PENDING / DYING, not held (HOLD: it cannot act), the
; hero alive; prepares ACT_SLOT, PL_* (cache_player), VB_S (its storey) and
; far6s R6 vb_one (vbat6.asm), which decides and makes the change.
; Clobbers: all but IY.   ~0.15k T off a Vampire level; there ~1.8k T with no
;   candidate (15 slots, contended), + ~0.9k T and vb_one a candidate
;------------------------------------------------------------------------------
vb_turn:        ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  nz
                ld   hl, LP_KINDS              ; a Vampire level only (LP_KINDS + LP_BOSS; a bat
                ld   b, LP_GEN_N               ; form exists only there): ~0.15k T elsewhere
.g:             ld   a, (hl)
                and  LEK_KIND_MASK
                cp   K_VAMPIRE
                jr   z, .go
                inc  hl
                djnz .g
                ret
.go:
                ld   a, (TURN_COUNTER)
                rrca
                ld   c, K_VBAT                 ; even: the bat forms
                jr   nc, .k
                ld   c, K_VAMPIRE              ; odd: the humanoids
.k:             ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
.l:             ld   a, c
                cp   (ix+E_KIND)
                jr   nz, .n
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                dec  a
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   a, P_MAX_ENT
                sub  b                         ; A = the slot (B = 15 .. 1)
                ld   (ACT_SLOT), a
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_HOLD
                jr   nz, .n                    ; frozen / stunned
                push bc
                call cache_player              ; (bank 2; keeps IX)
                call storey_ref                ; (bank 2)
                ld   (VB_S), a
                ld   hl, vb_one
                call far6                      ; (IX passes back: vb_one keeps it)
                pop  bc
.n:             ld   de, P_ENT_STRIDE
                add  ix, de
                djnz .l
                ret
                ASSERT EF_ACTIVE == 1 && (ST_FLAGS & $FF) + P_MAX_ENT <= $100
                ASSERT LP_BOSS == LP_KINDS + 4

;------------------------------------------------------------------------------
; do_exit — A = EXIT_KIND. EX_LEVEL: level_descend (B3B-12). Else follower
; selection (§3.7; LP: candidates only), lp_transition (LP, game.md §9.4.3:
; bank the old room, spawn the destination's residents, admit the followers),
; frozen Cauldron transition (§3.6), arrival, arrival conflicts. A7: shows bank 5 for the scroll (bank-3 code
; scrolls $4000), then present_full copies it to bank 7 and shows bank 7.
; Clobbers: all but IY.
;------------------------------------------------------------------------------
do_exit:
                cp   EX_LEVEL                  ; A = EXIT_KIND (end_turn)
                jp   z, level_descend          ; B3B-12: the level exit (lowram)
                cp   EX_TELE
                jp   z, .tele                  ; 3E-T12: the Teleport scroll
                call follow_select             ; L-RELIEF: this bank (PROTO: far3 follow_admit)
                call hide_sprites              ; every sprite hidden, hero too
                call show_bank5                ; A7: the scroll runs on the $4000 screen
                ld   a, GS_TRANSITION          ; (state flips once none is drawn)
                ld   (GAME_STATE), a
                ld   hl, lp_transition         ; LP (bank 3): bank the old room, spawn the
                call far3                      ; new one's residents, admit the followers
                ld   h, NEXT_MAP >> 8
                ld   a, (EXIT_DEST)
                call build_room                ; B3B-8: far3 -> bank-3 build_room_map v2
                ld   a, (EXIT_DEST)            ; FLOOR1: the glyph cache follows the
                ld   hl, fi_full               ; scroll (its strips draw EXIT_DEST's
                call far3                      ; items; every sprite is erased already)
                ld   a, (EXIT_KIND)            ; scroll arg: the exit direction
                ld   hl, hscroll_room          ; both scrolls live in bank 1 (scroll1.asm)
                cp   EX_UP
                jr   c, .h
                ld   hl, vscroll_room
.h:             call far1
                call room_shadow               ; attr shadow of the new room (the scroll
                                               ; drew the screen and its row-17 ornament)
.in:            ld   a, (CUR_ROOM)             ; 3F-T12: prev_room (§9.5 limit 3), every room
                ld   (TRK_PREV), a             ; change (exit + teleport)
                ld   a, (EXIT_DEST)
                ld   (CUR_ROOM), a
                call lair_hint                 ; B12 (lowram: 3 B here, kind_tab pad)
                ld   ix, P_ENTITIES
                ld   (ix+E_ROOM), a
                ld   a, (EXIT_KIND)
                cp   EX_RIGHT
                jr   nz, .nl
                ld   (ix+E_X), 1               ; entered from the left edge
                res  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .pos
.nl:            cp   EX_LEFT
                jr   nz, .vert
                KFIELD KT_BW
                ld   b, a
                ld   a, ROOM_COLS - 1
                sub  b
                ld   (ix+E_X), a               ; 31 - w
                set  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .pos
.vert:          ld   a, (EXIT_COL)
                ld   (ix+E_X), a
                KFIELD KT_BH
                ld   b, a
                ld   a, (EXIT_KIND)
                cp   EX_UP
                ld   a, FLOOR_ROW1             ; up: stand on the bottom storey (9s+8-h, s 1)
                jr   z, .vy
                ld   a, FLOOR_ROW0             ; down: stand on storey 0
.vy:            sub  b
                ld   (ix+E_Y), a
.pos:           call snap_pxpy
                ld   (ix+E_MODE), M_REST
                call arrival_conflicts         ; L-RELIEF: this bank
                call vis_room_sync             ; B7: no old-room sprite in the next render
                call present_full              ; A7: bank 5 -> 7 (6,912 B), show bank 7
                xor  a
                ld   (EXIT_KIND), a
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                jp   resync_tick
; 3E-T12 (game.md §8.11 Q6): no followers, no scroll. tele_pick (R6) picks the
; room + spot and leaves EXIT_KIND = EX_UP / EX_DOWN + EXIT_COL, so
; lp_transition banks / spawns for that arrival box and .in places the hero
; there like a vertical arrival. The new room is composed in bank 5 (room_show:
; map, screen, attr shadow, inks, ornament) while bank 7 still shows the old
; one, then shown at once (show_bank5; present_full copies it back to 7).
.tele:          call hide_sprites
                ld   hl, tele_pick
                call far6
                ld   a, GS_TRANSITION
                ld   (GAME_STATE), a
                ld   hl, lp_transition         ; bank the old room, spawn the new one
                call far3
                ld   a, (EXIT_DEST)
                call room_show                 ; (lowram; leaves bank 7 paged)
                call show_bank5
                jp   .in

;==============================================================================
; PLAYER TURN — try_player_turn: resolve the sampled keys (PLAYER_DIR/DISC).
; Chords (§9): B3B-5: UP + LEFT / RIGHT is always a jump (game.md §2.4,
; try_jump); else vertical wins if a climb is legal, else horizontal, else
; C (close door, 3B stand-in), else G, else wait. A climb blocked by an ENTITY counts as a wait (rule by user 2026-10-02,
; §6.4: the blocker gets its turn to move off), at wait priority. Illegal
; (terrain / no ladder) -> CF = 0, nothing changed (no turn).
; Out: CF = 1 turn used.
; Clobbers: all but IY.  (IX = player on return)
;==============================================================================
try_player_turn:
                call build_live
                ld   ix, P_ENTITIES
                xor  a
                ld   (ACT_SLOT), a
                ld   (CLIMB_BLK), a            ; A = 0
                ld   a, (ix+E_FLAGS)
                and  EF_DYING
                ret  nz                        ; dead heroes don't act (CF=0)

;------------------------------------------------------------------------------
; tpt_intent — C3-2 player turn (game.md §2.3 / §3.1), from try_player_turn
; (IX = hero, live list built). Order: a pending icon use (INTENT, set by
; intent_tick) -> use_icon (intent7.asm); UP + LEFT / RIGHT -> jump; one of LEFT /
; RIGHT (DOWN ignored: a low diagonal acts as the side) -> against the
; facing: turn around, 0 turns, and a held key waits TURN_DELAY ticks before
; it walks; along it: walk / bump attack / door (try_horizontal); UP -> climb;
; DOWN -> climb, else wait; '.' -> wait. Opposite keys cancel.
; Out: CF = 1 turn used.  Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
tpt_intent:
                ld   hl, DN_COMMIT             ; a released DOWN acts on THIS turn
                ld   b, (hl)                   ; only, and only if nothing else is
                ld   (hl), 0                   ; asked (review: no stale buffer)
                ld   a, (INTENT)
                or   a
                jr   z, .move
                ld   c, a
                xor  a
                ld   (INTENT), a
                bit  1, c                      ; IN_BAG (I): the bag page, no turn (CF = 0)
                jr   nz, .bag
                call use_icon                  ; intent7.asm (D3-7 T0: bank 7): L = 1 turn used
.res:           ld   a, l
                rrca                           ; CF = L bit 0
                ret  nc                        ; refused: ICON MODE stays (§3.1)
                ld   a, (ICON_MODE)
                or   a
                call nz, mode_exit             ; a used turn returns to play
                scf
                ret
.bag:           call page_run                  ; (lowram.asm; restores bank 7)
                jr   .res                      ; 3E-T8: page_post consumed the verb (PAGE_VERB
                                               ; 0 again): L = 1 EQUIP / REMOVE spent the turn
                                               ; (fx overlay), 0 none / DISCARD / T12 verbs
                ASSERT IN_BAG == 2 && IN_FIRE == 1
.move:          ld   a, (PLAYER_DIR)
                ld   c, a
                and  (1 << DIR_E_BIT) | (1 << DIR_W_BIT)
                bit  DIR_N_BIT, c
                jr   z, .nj
                or   a
                jp   nz, h_jump                ; D3-8 (WEAK / CONFUSED) -> lowram try_jump:
                                               ; A = E/W bits; CF = 1 jumped
.nj:            ld   d, 1
                cp   1 << DIR_E_BIT
                jr   z, .side
                ld   d, $FF
                cp   1 << DIR_W_BIT
                jr   z, .side
                xor  a
                ld   (TURN_HOLD), a            ; no side held: no pending delay
                or   b                         ; B: DOWN tapped < DN_DEFER ticks
                ld   a, 1 << DIR_S_BIT         ; (released): act on it now
                jr   nz, .dc
                ld   a, c
                and  (1 << DIR_N_BIT) | (1 << DIR_S_BIT)
                cp   1 << DIR_S_BIT
                jr   nz, .dc
                ld   a, (DN_T)                 ; DOWN held: wait for the ICON MODE
                cp   DN_DEFER                  ; window (FIRE may still join)
                jr   nc, .dact
                or   a                         ; CF = 0: nothing yet
                ret
.dact:          ld   a, 1 << DIR_S_BIT
.dc:            cp   1 << DIR_N_BIT
                jr   nz, .nu
                ld   d, $FF
                call try_climb
                ret  c
                jr   .wt
.nu:            cp   1 << DIR_S_BIT
                jr   nz, .wt
                ld   d, 1
                call try_climb
                ret  c
                jr   .srch                     ; DOWN with no climb: wait (§2.3)
.wt:            ld   a, (PLAYER_DISC)
                and  DK_WAIT                   ; '.'
                jr   nz, .srch
                ld   a, (CLIMB_BLK)            ; climb blocked by an entity: wait
                or   a
                ret  z                         ; CF = 0: nothing legal
.srch:          ld   a, 1                      ; 3E-T16: every Wait searches (game.md
                ld   (TRP_WAIT), a             ; §2.3 / §1.5; the held Wait does not:
                scf                            ; turn_input .hw senses but skips the search)
                ret
.side:          ld   a, d                      ; D = dx: against the facing?
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .fr
                dec  a                         ; facing left, dx = +1
                jr   z, .turn
                jr   .along
.fr:            inc  a                         ; facing right, dx = -1
                jr   z, .turn
.along:         ld   hl, TURN_HOLD
                ld   a, (hl)
                or   a                         ; CF = 0
                jp   z, h_walk                 ; D = dx (D3-8: CONFUSED -> try_horizontal)
                dec  (hl)                      ; still in the turn-around delay
                ret
.turn:          ld   a, d
                call face_a
                ld   a, TURN_DELAY
                ld   (TURN_HOLD), a
                or   a                         ; CF = 0: no turn (anim_tick redraws)
                ret

;------------------------------------------------------------------------------
; try_climb — IX = player, D = dy ($FF up / 1 down). CF = 1 if done (§3.4).
; Standing: UP needs {x,s} ({x,0} = up-exit, no step), DOWN needs {x,s+1}
; ({x,2} = down-exit, first step animated). Mid-ladder: continue or reverse.
; Step blocked by an entity: climb_blocked (lowram, B14): the first time
; CF = 0, CLIMB_BLK = 1 (the caller turns it into a wait) and E_AIDIR = the
; attempted dy (the monster phase yields to that climb, cork_check); the 2nd
; consecutive time by the same body the hero squeezes past (CF = 1). No
; ladder: CF = 0, CLIMB_BLK untouched.
; Clobbers: A, BC, DE, HL, TMP6
;------------------------------------------------------------------------------
try_climb:
                ld   a, d
                ld   (TMP6), a                 ; dy (D is clobbered by queries)
                call is_standing
                jr   nz, .mid
                call feet_mod
                ld   b, l                      ; B = storey stood on
                ld   c, (ix+E_X)
                ld   a, (TMP6)
                cp   1
                jr   z, .down
                call ladder_exists             ; UP: {x, s}
                ret  nc
                ld   a, b
                or   a
                jr   nz, .mid
                ld   a, RDX_U                  ; {x,0}: the up-exit (player only;
                call .vexit                    ; ARR is a {c,0} without an exit)
                jr   nz, .no
                sub  GRID_W                    ; r - 3
                ld   (EXIT_DEST), a
                ld   a, EX_UP
                ld   (EXIT_KIND), a
                ld   a, (ix+E_X)
                ld   (EXIT_COL), a
                xor  a
                ld   (EXIT_STOREY), a
                scf
                ret
.no:            or   a
                ret
.down:          inc  b                         ; DOWN: {x, s+1}
                call ladder_exists
                ret  nc
                ld   a, b
                cp   STOREY_COUNT
                jr   nz, .mid
                ld   a, RDX_D                  ; {x,2}: the down-exit ...
                call .vexit
                jr   z, .dn
                call cur_room_desc             ; ... else the level exit (B3B-12), only at
                ld   a, l                      ; x == RD_EXITCOL (descriptor: one page)
                add  a, RD_EXITCOL
                ld   l, a
                ld   a, (hl)
                cp   c
                jr   nz, .no
                ld   a, (LVL_FLAGS)            ; and only through an open grate (3F-T8:
                and  LF_GRATE_OPEN             ; the boss's death). Shut: game.md §9.2 F4,
                jr   nz, .lvl                  ; illegal, NO turn: drop the caller's frame
                pop  hl                        ; (turn_input .nu's `jr .srch` wait); A = 0,
                ret                            ; CF = 0 (and) = "nothing legal"
.lvl:           ld   a, EX_LEVEL
                jr   .dk
.dn:            add  a, GRID_W                 ; dest r + 3
                ld   (EXIT_DEST), a
                ld   a, EX_DOWN
.dk:            ld   (EXIT_KIND), a
                ld   a, (ix+E_X)
                ld   (EXIT_COL), a
                ld   a, STOREY_COUNT - 1
                ld   (EXIT_STOREY), a
                call .mid                      ; animate the first step down
                ret  c
                xor  a                         ; blocked: cancel the exit
                ld   (EXIT_KIND), a
                ret
.mid:           call get_box
                ld   a, (TMP6)
                add  a, b
                ld   b, a
                call box_free
                jr   c, .blk
                ld   (ix+E_Y), b
                ld   a, (TMP6)
                ld   (ix+E_AIDIR), a
                ld   (ix+E_MODE), M_MOVE
                ld   a, SFX_LADDER             ; SND-5: a ladder step (the hero only)
                call sfx_req
                scf
                ret
.blk:           jp   climb_blocked             ; B14 (lowram): wait + forced yield,
                                               ; or the 2nd time: squeeze past
.vexit:         ; A = RDX_U / RDX_D, C = x: Z = that exit exists and its
                ; shaft col (RD_UPCOL / RD_DNCOL) == x; A = CUR_ROOM then.
                ; Clobbers: E, HL
                ld   e, a
                call cur_room_desc
                inc  l                         ; RD_EXITS
                ld   a, (hl)
                and  e
                xor  e                         ; Z iff the exit bit is set
                ret  nz
                inc  l                         ; RD_UPCOL
                bit  RDX_D_BIT, e
                jr   z, .vu
                inc  l                         ; RD_DNCOL
.vu:            ld   a, (hl)
                cp   c
                ret  nz
                ld   a, (CUR_ROOM)
                ret
                ASSERT RD_EXITS == 1 && RD_UPCOL == 2 && RD_DNCOL == 3

;------------------------------------------------------------------------------
; try_horizontal — IX = player, D = dx. Attack (bump) or move / exit.
; B3B-5: the leading cell (lead_cell) decides terrain first: a wall / block =
; no turn; a closed door plank = hero_door (open: 1 turn, no move; locked: a
; message, no turn). A step onto x == the pit col on the storey-0 floor
; falls (hero_fall, game.md §2.5).
;------------------------------------------------------------------------------
try_horizontal:
                call on_ladder
                ret  z                         ; mid-ladder: L/R illegal (CF = 0? see below)
                ld   a, d
                ld   (TMP6), a                 ; dx
                call find_target               ; A = target slot / $FF
                cp   $FF
                jr   z, .move
                ld   b, a
                call fear_chk                  ; D3-8: FEAR -> no bump attack (illegal,
                jp   z, .afraid                ; no turn, game.md §6.4)
                call face_tmp6
                ld   a, b
                ld   hl, do_attack             ; B3B-R2: bank 3 (A = target slot)
                call far3
                scf
                ret
.move:
                call get_box
                ld   a, (TMP6)
                add  a, c
                ld   c, a                      ; nx
                ld   a, (TMP6)                 ; B3B-5: terrain at the leading col
                call lead_cell
                jr   c, .solid
                ld   a, (TMP6)
                dec  a                         ; dx == 1 (WIN2: -1 B vs cp 1; both paths reload A)
                jr   z, .right
                ld   a, c
                or   a
                jr   nz, .inside               ; nx >= 1
                ; entering col 0: left exit on this storey?
                push bc
                push de
                call storey_ref
                ld   b, a
                ld   (EXIT_STOREY), a
                ld   a, EX_LEFT
                call exit_h
                pop  de
                pop  bc
                ret  nc
                ld   (EXIT_DEST), a
                ld   a, EX_LEFT
                jr   .exit
.right:         ld   a, c
                add  a, d
                dec  a                         ; right col
                cp   ROOM_COLS - 1
                jr   c, .inside
                push bc
                push de
                call storey_ref
                ld   b, a
                ld   (EXIT_STOREY), a
                ld   a, EX_RIGHT
                call exit_h
                pop  de
                pop  bc
                ret  nc
                ld   (EXIT_DEST), a
                ld   a, EX_RIGHT
.exit:          ld   (EXIT_KIND), a
.inside:
                call box_free
                jr   c, .blocked
                ld   (ix+E_X), c
                call face_tmp6
                ld   (ix+E_MODE), M_MOVE
                ld   a, SFX_STEP               ; SND-5b: the hero's step (prio 0: never cuts
                call sfx_req                   ; anything; a fall below replaces it)
                ld   a, b                      ; B3B-5 pit (game.md §2.5): standing on
                add  a, e                      ; storey 0 with the body fully over
                cp   FLOOR_ROW0                ; holes (p <= x <= p+W-3; L2 wide pit)
                jr   nz, .ok                   ; -> fall. pit_range: p = 0 = no pit
                call pit_range                 ; (B11: x == 0 never matches it)
                jp   c, hero_fall              ; lowram: CF = 1
.ok:            scf
                ret
.solid:         bit  TF_ATTACK_BIT, a          ; P3: the lectern (only the Sanctum's): a melee
                jr   nz, .tome                 ; hit on the Tome (tome7.asm), 1 turn
                and  TF_DOOR                   ; wall / block: CF = 0 (and), no turn
                ret  z
                ld   a, (TMP6)
                jp   hero_door                 ; lowram: opened (CF = 1) / locked (0)
.tome:          call face_tmp6                 ; (bank 2) the hero faces it (keeps C)
                jp   tome_rel                  ; WIN2: through the geometry: adjacent (gap 0) < C = nx
                                               ; (>= 2: the lectern is at cols 1-2 / 29-30): a hit,
                                               ; CF = 1; destroyed (TOME_HP 0): CF = 0, a wall, no turn
.blocked:       xor  a
                ld   (EXIT_KIND), a            ; CF = 0 (xor)
                ret
.afraid:        ld   hl, LOCK_SHOWN            ; once per press, as the locked door
                ld   a, (hl)                   ; (turn_input clears it on a release)
                or   a
                ret  nz                        ; CF = 0
                inc  (hl)
                ld   a, TX_ST_AFRAID
                call msg_push
                or   a                         ; CF = 0
                ret

; exit_h — A = EX_LEFT / EX_RIGHT, B = storey. CF = 1 if open; A = dest.
; Clobbers: A, BC, DE, HL
exit_h:
                ld   c, b
                call room_side
                ret  nc
                ld   e, a
                ld   a, b
                cp   c
                ld   a, e
                scf
                ret  z
                or   a                         ; another storey: CF = 0
                ret

; ladder_exists — CF = 1 if segment {col C, storey B} exists in the current room.
; Preserves BC. Clobbers: A, HL
ladder_exists:
                call cur_room_desc
                inc  l                         ; -> RD_EXITS; the loop pre-increments
.l:             inc  l
                ld   a, l
                and  RD_STRIDE - 1
                cp   RD_LAD2 + 1
                ret  nc                        ; past RD_LAD2: not found (CF = 0)
                ld   a, (hl)
                cp   c
                jr   nz, .l
                or   a
                jr   z, .l                     ; col 0 = none (C = 0 never matches)
                call seg_storey
                cp   b
                jr   nz, .l
                scf
                ret

;------------------------------------------------------------------------------
; find_target — IX = attacker, TMP6 = direction (+1/-1). Nearest hostile-to-IX
; entity in reach in that direction (prototype §6.1). A mid-ladder body is never
; a target but still ends the scan if it is the nearest (review B: nothing in
; reach passes a climber). Out: A = slot or $FF (D3-0: the gap output that only
; the PROTO zap read is gone; LAST_HIT_SLOT = the best gap is scratch). The
; player scans the LIVE_LIST for EF_HOSTILE; a monster only ever targets the
; player (slot 0), so it checks that one entity.
; Clobbers: A, BC, DE, HL (IX preserved)
;------------------------------------------------------------------------------
find_target:
                call get_box
                ld   a, c
                ld   (TMP0), a                 ; ax
                ld   a, b
                ld   (TMP1), a                 ; ay
                ld   a, d
                ld   (TMP2), a                 ; aw
                ld   a, e
                ld   (TMP3), a                 ; ah
                ld   a, 1                      ; reach 1 for every kind (MEM-RECLAIM w3: the KT_REACH column is gone; the Ogre's SLAM reach is boss2 reach_ok)
                ld   (TMP4), a
                ld   a, $FF
                ld   (TMP5), a                 ; best slot
                ld   (LAST_HIT_SLOT), a        ; best gap
                ld   a, (ix+E_FLAGS)
                push ix
                and  EF_PLAYER
                jr   nz, .player
                ld   ix, P_ENTITIES            ; monster: the hero only
                ld   c, 0
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                call z, .cand
                jr   .done
.player:        ld   a, (LIVE_N)
                or   a
                jr   z, .done
                ld   b, a
                ld   hl, LIVE_LIST
.pl:            push bc
                push hl
                ld   c, (hl)                   ; slot
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                ld   a, (ix+E_FLAGS)
                and  EF_HOSTILE | EF_DYING
                cp   EF_HOSTILE
                call z, .cand
                pop  hl
                ld   de, 5
                add  hl, de
                pop  bc
                djnz .pl
.done:          pop  ix
                ld   a, (TMP5)
                cp   FT_BLOCKER
                ret  nz
                ld   a, $FF                    ; nearest body is mid-ladder: no target
                ret

.cand:          ; IX = candidate, C = its slot
                push bc
                call on_ladder
                pop  bc
                jr   nz, .cv
                ld   c, FT_BLOCKER             ; no combat on ladders, but its body
.cv:            push bc                        ; still blocks the line (reach
                                               ; can't pass it). Vertical overlap:
                KFIELD KT_BH                   ;   ty <= ay+ah-1 && ay <= ty+th-1
                pop  bc
                add  a, (ix+E_Y)
                dec  a
                ld   hl, TMP1
                cp   (hl)
                ret  c
                ld   a, (TMP1)
                ld   hl, TMP3
                add  a, (hl)
                dec  a
                cp   (ix+E_Y)
                ret  c
                ld   a, (TMP6)                 ; gap in the facing direction
                cp   1
                jr   nz, .left
                ld   a, (TMP0)
                ld   hl, TMP2
                add  a, (hl)                   ; ax+aw
                ld   b, a
                ld   a, (ix+E_X)
                sub  b                         ; tx - (ax+aw)
                ret  c                         ; behind
                jr   .gap
.left:          push bc
                KFIELD KT_BW
                pop  bc
                add  a, (ix+E_X)               ; tx+tw
                ld   b, a
                ld   a, (TMP0)
                sub  b
                ret  c
.gap:           ld   hl, TMP4
                cp   (hl)
                jr   z, .inr
                ret  nc                        ; gap > reach
.inr:           ld   hl, LAST_HIT_SLOT
                cp   (hl)
                ret  nc                        ; not nearer (ties: lower slot)
                ld   (hl), a
                ld   a, c
                ld   (TMP5), a
                ret

;------------------------------------------------------------------------------
; hide_sprites — erase every drawn sprite + FX + queued damage (before a
; transition: "all sprites are hidden", §3.6). Clobbers: all but IY.
;------------------------------------------------------------------------------
hide_sprites:
                call mk_hide                   ; D3-8d: the status marks first (above the bodies)
                call drip_hide                 ; D3-8b: before the bodies (it is never under one)
                call fx_hide                   ; D3-5: FX erased, tracks + queue cleared
                xor  a
.l:             ld   (ANIM_SLOT), a
                call ent_ix
                ld   a, (ix+E_DVIS)
                and  1
                jr   z, .n
                ld   c, (ix+E_DCOL)
                ld   b, (ix+E_DROW)
                ld   d, (ix+E_DCOLS)
                ld   e, (ix+E_DROWS)
                call erase_rect
                ld   (ix+E_DVIS), 0
.n:             ld   a, (ANIM_SLOT)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ld   a, (PEND_DMG_COUNT)
                or   a
                ret  z
                ld   b, a
                ld   hl, PEND_DMG
.p:             push bc
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                call erase_rect
                pop  hl
                pop  bc
                djnz .p
                xor  a
                ld   (PEND_DMG_COUNT), a
                ret


;==============================================================================
; L-RELIEF (bank-3 relief): the room-exit follower code moved here from
; bank3.asm — follow_select (candidate scan), place_follower, arrival_conflicts.
;==============================================================================
;==============================================================================
; FOLLOW SELECTION (prototype §3.7) — on the player's exit turn, before the
; transition. EXIT_KIND/DEST/STOREY/COL set. No RNG; deterministic order
; (gap ascending, ties lower slot). L-RELIEF: bank 7 (was bank 3, far3 from
; do_exit): a plain call from do_exit; PROTO (LVL_DEPTH 0) admits at once
; through far3 follow_admit (bank 3: lp_wt / lp_rec), LP leaves the candidates
; to lp_transition. Cold (once per room exit): the contended fetches and the
; far3 (~0.25k T) do not touch a tick.  Clobbers: all but IY.
;==============================================================================
follow_select:
                xor  a
                ld   (FOLLOW_N), a
                ; reference box: player (horizontal) or the shaft standing box
                ld   ix, P_ENTITIES
                call get_box
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   c, .hbox
                ld   a, (EXIT_COL)
                ld   c, a
                ld   a, (EXIT_STOREY)
                MUL_STOREY b
                add  a, STOREY_AIR
                sub  e
                ld   b, a                      ; standing y on the exit storey (9s+8-h)
.hbox:          ld   a, c
                ld   (TMP0), a                 ; ref x
                ld   a, d
                ld   (TMP2), a                 ; ref w
                ; --- candidate gaps ---
                ld   a, 1
.cl:            ld   (TMP7), a
                ld   hl, CAND_LIST
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   (hl), $FF
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jp   nz, .cn
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jp   nz, .cn
                ld   a, (ix+E_KIND)            ; 3F-T8 (game.md §8.6 / §9.2): the lair boss
                or   (ix+E_GOLD)               ; NEVER follows (it was a plain candidate: the
                ld   hl, LP_BOSS               ; D4 Ogre left its lair, user playtest). Only the
                cp   (hl)                      ; boss matches kind | E_GOLD = LP_BOSS (the Ogre /
                jr   z, .cn                    ; Death Knight spawn nowhere else; PROTO: LP_BOSS 0
                ld   a, (TMP7)                 ; = the Knight's id). D3-8f (game.md §6.4.2 R3): a HOLD or                 ; D3-8f (game.md §6.4.2 R3): a HOLD or
                add  a, ST_FLAGS & $FF         ; FEAR body is not a candidate (CONFUSED
                ld   l, a                      ; may follow)
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_HOLD
                jr   nz, .cn
                ld   a, (hl)
                and  STS_MIND
                cp   MIND_FEAR
                jr   z, .cn
                call on_ladder
                jr   z, .cn                    ; must be standing / flying
                call storey_ref
                ld   hl, EXIT_STOREY
                cp   (hl)
                jr   nz, .cn
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   c, .hz
                KFIELD KT_FLAGS                ; vertical: climbers only
                and  KF_CLIMBER
                jr   z, .cn
.hz:            ; gap = |boxes| distance
                ld   a, (TMP0)
                cp   (ix+E_X)
                jr   c, .mright
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   b, a
                ld   a, (TMP0)
                sub  b                         ; ref.x - (m.x+m.w)
                jr   .g
.mright:        ld   a, (TMP0)
                ld   hl, TMP2
                add  a, (hl)
                ld   b, a
                ld   a, (ix+E_X)
                sub  b                         ; m.x - (ref.x+ref.w)
.g:             jr   c, .cn
                cp   FOLLOW_GAP + 1
                jr   nc, .cn
                ld   b, a
                ld   a, (TMP7)
                ld   e, a
                ld   d, 0
                ld   hl, CAND_GAP
                add  hl, de
                ld   (hl), b
                ld   hl, CAND_LIST
                add  hl, de
                ld   (hl), a
.cn:            ld   a, (TMP7)
                inc  a
                cp   P_MAX_ENT
                jp   c, .cl
                ld   a, (LVL_DEPTH)            ; LP (game.md §9.4.3): the candidates
                or   a                         ; wait; lp_transition admits them after
                ret  nz                        ; the destination's residents spawned
                ld   hl, follow_admit          ; PROTO: admit now (bank 3; far3 nests,
                jp   far3                      ; bank 7 comes back)

;==============================================================================
; arrival_conflicts — after a transition: any non-pending monster in CUR_ROOM
; whose box overlaps the hero's arrival box becomes PENDING in place (§3.6).
; L-RELIEF: bank 7 (was bank 3): a plain call from do_exit, far7 from lowram
; hero_fall. Bank-2 queries only (get_box, box_vs_ix).  Clobbers: A, BC, DE, IX.
;==============================================================================
arrival_conflicts:
                ld   ix, P_ENTITIES
                call get_box                   ; hero arrival box
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   a, 1
.l:             push af
                push bc
                push de
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call box_vs_ix
                jr   nc, .n
                set  EF_PENDING_BIT, (ix+E_FLAGS)
.n:             ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                pop  bc
                pop  af
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret

;------------------------------------------------------------------------------
; pause_run7 — the body of bank-2 pause_hook (far7): FIRE+UP / BREAK (outside ICON MODE): counts the request
; (PAUSE_REQ, test-observable) and runs the C3-6 pause overlay (pause_run,
; bank 1) on the shown bank-5 screen; resume -> present_full + resync_tick,
; quit -> the menu (stack reset). Clobbers: all but IX, IY.
pause_run7:     ld   hl, PAUSE_REQ
                inc  (hl)
                call show_bank5                ; C3-6: the overlay on the composed screen
                ld   hl, pause_run             ; bank 1 (menu1.asm): L = 0 resume / 1 quit
                call far1
                ld   a, l
                or   a
                jr   nz, .quit
                ld   a, FS_USED                ; the FIRE / ENTER that resumed is not a
                ld   (FIRE_ST), a              ; tap or an ENTER use back in play
                ld   a, (PLAYER_SC)
                ld   (SC_OLD), a
                call present_full              ; bank 5 (rows restored) -> screen 2, shown
                jp   resync_tick               ; the paused time is not a tick overrun
.quit:          ld   sp, WORKSTORE_TOP         ; abandon the game: back to the menu
                jp   enter_select              ; (bank 2; the far frames are dropped)

;------------------------------------------------------------------------------
; intent_icon7 — intent_tick's ICON MODE part (D3-S2: from bank-2 io.asm,
; far7; play is frozen in ICON MODE, so the far call never lands in a busy
; tick). In: D = STICK, E = pressed this tick. FIRE -> INTENT (use the
; selected icon); UP / DOWN -> mode_exit; a held side steps the cursor
; (CUR_DELAY1 then CUR_DELAY2 repeat; cursor_step, intent7.asm).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
intent_icon7:
                bit  JOY_F_BIT, e
                jr   z, .mNoF
                ld   a, FS_USED               ; the release is not a tap
                ld   (FIRE_ST), a
                ld   a, IN_FIRE
                ld   (INTENT), a
                ret
.mNoF:          bit  JOY_F_BIT, d
                jr   nz, .mF
                xor  a                        ; FIRE up: the next press is new
                ld   (FIRE_ST), a
.mF:            ld   a, e
                and  (1 << JOY_U_BIT) | (1 << JOY_D_BIT)
                jp   nz, mode_exit
                bit  JOY_F_BIT, d
                ret  nz                       ; FIRE still held from the entry
                ld   a, d
                and  (1 << JOY_R_BIT) | (1 << JOY_L_BIT)
                cp   1 << JOY_R_BIT
                ld   c, 1
                jr   z, .cur
                cp   1 << JOY_L_BIT
                ld   c, $FF
                ret  nz
.cur:           and  e                        ; the held side is new?
                ld   hl, CUR_REP
                ld   b, CUR_DELAY1
                jr   nz, .step
                dec  (hl)
                ret  nz
                ld   b, CUR_DELAY2
.step:          ld   (hl), b
                ld   a, c
                jp   cursor_step               ; intent7.asm (this bank)

;==============================================================================
; D3-7 (abilities; T0 layout: refusing stubs, T1 fills them in)
;==============================================================================
                INCLUDE "intent7.asm"          ; C3-2 icon bar (D3-7 T0: from bank 3)
                INCLUDE "abil_spell7.asm"      ; the 5 Mage spells (cast -> proj_fire)
                INCLUDE "abil_melee7.asm"      ; Power Strike, Whirlwind, the staff bonk slot
                INCLUDE "abil_ammo7.asm"       ; dagger throw, bow shot
                INCLUDE "pickup7.asm"          ; ammo pickup (end_turn)
                INCLUDE "act7.asm"             ; D3-7 T1: the split ability turn (act_begin / act_pend / act_fire)
                INCLUDE "status7.asm"          ; D3-8: the status step, held / confused / fearful hero and monsters
                INCLUDE "drip7.asm"            ; D3-8b: drip sources, spawn / let go, hide
                INCLUDE "mark7.asm"            ; D3-8d: status marks: room reset + glyph copy, hide
                INCLUDE "xp7.asm"              ; D3-9b: MP regen, level-up, learn / rank-up
                INCLUDE "mus7.asm"             ; SND-3: Dangerous (W) cue, mus_pick
                INCLUDE "hunger7.asm"          ; MEM-RECLAIM w2b: hunger_turn / hunger_add (from R6 hunger6.asm)
                INCLUDE "trap7.asm"            ; MEM-RECLAIM w2b: trap_turn / trap_step / effects (from R6 trap6.asm)
                INCLUDE "boss7.asm"            ; MEM-RECLAIM w2b: grate_open / boss_chk (from R6 boss6.asm)
                INCLUDE "tome7.asm"            ; P3: the Tome's hits, aura and the win
                ; (tiles7.asm: M0 -> the high bank-7 block after the tilesets, main.asm b7h_code)
                INCLUDE "boot7.asm"            ; MEM-SND: panel_init7, new_game (from bank 3; 3E-T1: the boot parts -> boot6.asm)
