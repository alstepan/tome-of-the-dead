;==============================================================================
; bank7.asm — D3-S2 bank-7 COLD code, B7_CODE ($E000) .. b7_end <= B7_LIMIT
; ($F800, the attr shadow): the 6 KB freed by dropping the bitmap shadow.
; Per-turn / per-event logic moved out of bank 2 (docs/memory-map.md "Cold
; code placement"): the player turn (turn_input -> try_player_turn ->
; tpt_intent / try_climb / try_horizontal / find_target), end_turn + do_exit
; + hide_sprites (room exit), the pause overlay entry.
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
; is the cursor's; only directions and '.' count as held.
; Clobbers: all but IY (far7: A, F lost; nothing is returned).
;------------------------------------------------------------------------------
turn_input:
                ld   a, (INTENT)
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
                ret
.held:          ld   a, (INPUT_REPEAT)
                or   a
                jr   nz, .go
                ld   a, (NEED_RELEASE)
                or   a
                ret  nz
.go:            call try_player_turn
                ret  nc                        ; illegal: no turn consumed
                ld   a, (CLIMB_BLK)            ; B14: any turn but a blocked-climb
                or   a                         ; wait ends the run of blocks
                jr   nz, .blk                  ; (climb_blocked)
                ld   (CLIMB_BLK_N), a
.blk:
                ld   a, 1
                ld   (NEED_RELEASE), a
                ld   a, (EXIT_KIND)
                or   a
                ld   hl, resolve_monsters      ; B3B-R2: bank 3, one far3 a turn
                call z, far3                   ; exit turn: monsters don't act
                ld   a, TP_ANIM
                ld   (TURN_PHASE), a
                xor  a
                ld   (TURN_TICK), a
                ret

;------------------------------------------------------------------------------
; end_turn — ANIM finished (play_loop: turn_done CF -> far7): transition (if
; exiting), TURN_COUNTER++, potion pickup, death check (B3B-11: messages via
; the log; B3B-13: msg_push), back to INPUT.  Clobbers: all but IY.
;------------------------------------------------------------------------------
end_turn:
                ld   a, (EXIT_KIND)
                or   a
                call nz, do_exit
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (TURN_COUNTER), hl
                ld   hl, potion_pickup         ; B3B-R2: bank 3 (B3B-11: HP / potions
                call far3                      ; reach the panel by
                xor  a                         ; panel_tick's poll, not from here)
                ld   (TURN_PHASE), a
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  z                         ; (B3B-13: the PROTO chest win is gone; a run
                                               ; wins by descending from D8, level_descend)
                ld   a, GS_DEAD
                ld   (GAME_STATE), a
                ld   a, TX_DIED
                jp   msg_push_end              ; never dropped (B3B-11b); end_screen drains it

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
                ld   hl, follow_select         ; bank 3 (cold)
                call far3
                call hide_sprites              ; every sprite hidden, hero too
                call show_bank5                ; A7: the scroll runs on the $4000 screen
                ld   a, GS_TRANSITION          ; (state flips once none is drawn)
                ld   (GAME_STATE), a
                ld   hl, lp_transition         ; LP (bank 3): bank the old room, spawn the
                call far3                      ; new one's residents, admit the followers
                ld   h, NEXT_MAP >> 8
                ld   a, (EXIT_DEST)
                call build_room                ; B3B-8: far3 -> bank-3 build_room_map v2
                ld   a, (EXIT_KIND)            ; scroll arg: the exit direction
                ld   hl, hscroll_room          ; both scrolls live in bank 1 (scroll1.asm)
                cp   EX_UP
                jr   c, .h
                ld   hl, vscroll_room
.h:             call far1
                call room_shadow               ; attr shadow of the new room (the scroll
                                               ; drew the screen and its row-17 ornament)
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
                ld   hl, arrival_conflicts     ; bank 3 (cold)
                call far3
                call vis_room_sync             ; B7: no old-room sprite in the next render
                call present_full              ; A7: bank 5 -> 7 (6,912 B), show bank 7
                xor  a
                ld   (EXIT_KIND), a
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                jp   resync_tick

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
; intent_tick) -> use_icon (bank 3); UP + LEFT / RIGHT -> jump; one of LEFT /
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
                xor  a
                ld   (INTENT), a
                ld   hl, use_icon              ; bank 3: L = 1 turn used
                call far3
                ld   a, l
                rrca                           ; CF = L bit 0
                ret  nc                        ; refused: ICON MODE stays (§3.1)
                ld   a, (ICON_MODE)
                or   a
                call nz, mode_exit             ; a used turn returns to play
                scf
                ret
.move:          ld   a, (PLAYER_DIR)
                ld   c, a
                and  (1 << DIR_E_BIT) | (1 << DIR_W_BIT)
                bit  DIR_N_BIT, c
                jr   z, .nj
                or   a
                jp   nz, try_jump              ; lowram: A = E/W bits; CF = 1 jumped
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
                scf                            ; DOWN with no climb: wait (§2.3)
                ret
.wt:            ld   a, (PLAYER_DISC)
                and  DK_WAIT                   ; '.'
                scf
                ret  nz
                ld   a, (CLIMB_BLK)            ; climb blocked by an entity: wait
                or   a
                ret  z                         ; CF = 0: nothing legal
                scf
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
                jp   z, try_horizontal         ; D = dx
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
                ld   a, (LVL_FLAGS)            ; ... else the level exit (B3B-12):
                and  LF_GRATE_OPEN             ; only through an open grate (3B: always
                jr   z, .no                    ; open, game.md §1.4; 3F: the boss's death)
                call cur_room_desc             ; and only at x == RD_EXITCOL
                ld   a, l
                add  a, RD_EXITCOL             ; (descriptor: one page)
                ld   l, a
                ld   a, (hl)
                cp   c
                jr   nz, .no
                ld   a, EX_LEVEL
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
                cp   1
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
                ld   a, b                      ; B3B-5 pit (game.md §2.5): standing on
                add  a, e                      ; storey 0 with the body fully over
                cp   FLOOR_ROW0                ; holes (p <= x <= p+W-3; L2 wide pit)
                jr   nz, .ok                   ; -> fall. pit_range: p = 0 = no pit
                call pit_range                 ; (B11: x == 0 never matches it)
                jp   c, hero_fall              ; lowram: CF = 1
.ok:            scf
                ret
.solid:         and  TF_DOOR                   ; wall / block: CF = 0 (and), no turn
                ret  z
                ld   a, (TMP6)
                jp   hero_door                 ; lowram: opened (CF = 1) / locked (0)
.blocked:       xor  a
                ld   (EXIT_KIND), a            ; CF = 0 (xor)
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
                KFIELD KT_REACH
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

; find_target_far — find_target for bank-3 callers (intent3 ic_melee): far7
; loses A, so the slot comes back in L.  Clobbers: as find_target + L.
find_target_far:
                call find_target
                ld   l, a
                ret

;------------------------------------------------------------------------------
; hide_sprites — erase every drawn sprite + FX + queued damage (before a
; transition: "all sprites are hidden", §3.6). Clobbers: all but IY.
;------------------------------------------------------------------------------
hide_sprites:
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
; (CUR_DELAY1 then CUR_DELAY2 repeat; cursor_step, bank 3).
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
                ld   hl, cursor_step
                jp   far3
