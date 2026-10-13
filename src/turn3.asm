;==============================================================================
; turn3.asm — once-per-turn / per-event turn logic in BANK 3 (B3B-R2, bank-2
; relief; docs/memory-map.md "Cold code placement"). INCLUDEd at the end of
; bank3.asm. Moved verbatim from logic.asm except for the entry glue noted at
; each routine; the bank-2 helpers they call (try_step / try_step_face /
; cork_check / box_free / box_vs_ix / get_box / on_ladder /
; is_standing / storey_ref / build_live / snap_pxpy / rng_mod / ent_ix /
; kind_seq_ptr / start_seq / queue_damage / msg_push ...) stay in bank 2 / 5 and
; page nothing, so they run fine under bank 3. The one exception reachable
; from here — try_step -> mon_door -> door_open -> door_paint -> shadow_rect
; (pages bank 7) — re-pages the caller's bank (door_paint, lowram.asm).
; Data read: kind_tab / kind_seqs / P_ENTITIES / LIVE_LIST / TMP* (bank 2),
; ROOM_MAP / ROOM_DESC / FLOOR_LIST (bank 5): none at $C000.
;
; Entries (far3 from bank 2; far3 clobbers AF, so nothing returns in A/F):
;   resolve_monsters  read_turn_input (ONE far3 per turn: the per-monster
;                     ai_monster calls, materialise and the monster attacks'
;                     do_attack stay inside bank 3)
;   do_attack         try_horizontal (the hero's bump attack; A = target slot)
; Contention: bank 3 is contended, so these bodies pay ULA contention on code
; fetches (measured in tests/budget.py; the bank-2 helpers they call do not).
;==============================================================================

; (try_quaff: D3-7 T5 moved into bank-7 intent7.asm ic_potion.)

;------------------------------------------------------------------------------
; do_attack — IX = attacker, A = target slot: one melee blow (D3-6a: on the
; shared core, combat3.asm). hit_roll (F1, the d20 first), then damage 1dN +
; bonus (kind_tab, prototype §6.2 / F2) dealt by deal_hit with the attacker's
; kx_melee row (type + on-hit effect: PHYS; the Ghost's DRAIN touch, CONFUSED
; 4 at 1 in 4). Sets the attacker's ATTACK sequence + IMPACT info (E_HIT = 1
; iff HP was lost: an immune target does not flash; E_MSG hit / miss / kill)
; and the target's reaction (deal_hit: HURT / DEATH; a missed Knight: BLOCK).
; Clobbers: all but IX.
; Entered by far3 from try_horizontal (hero) and directly from attack_if_reach
; (monsters, already in bank 3).
;------------------------------------------------------------------------------
do_attack:
                ld   (ix+E_TGT), a
                ld   (TMP2), a                 ; target slot
                ld   (ATK_PTR), ix
                ld   b, 0                      ; melee: no to-hit modifier
                call hit_roll
                ld   (TMP0), a                 ; 1 hit / 0 miss (message)
                jr   z, .miss
                ld   a, (ix+E_KIND)            ; C / E = the kind's melee row
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, kx_melee
                add  hl, de
                ld   c, (hl)
                inc  hl
                ld   e, (hl)
                push bc
                KFIELD KT_DIE                  ; damage: 1dN + bonus
                ld   c, a
                call rng_mod                   ; (keeps DE)
                inc  a
                ld   d, a
                KFIELD KT_BONUS
                add  a, d
                pop  bc
                ld   b, a
                ld   a, (TMP2)
                call deal_hit                  ; L = HP lost; IX = attacker
                ld   a, l
                or   a
                jr   z, .res                   ; nothing lost (immune): no flash
                ld   a, 1
                jr   .res
.miss:          ld   a, (TMP2)
                call ent_ix                    ; IX = target
                ld   a, (ix+E_KIND)
                cp   K_KNIGHT
                jr   nz, .m0
                ld   c, RC_BLOCK               ; a miss on the Knight: BLOCK (§6.5)
                call set_reaction_at
.m0:            xor  a
.res:           ld   ix, (ATK_PTR)
                ld   (ix+E_HIT), a
                ld   a, (TMP0)
                ld   b, a                      ; B = hit (message), as before
                ; message code
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   z, .mmsg
                ld   a, b
                or   a
                ld   a, MSG_P_MISS
                jr   z, .setm
                ld   a, (TMP2)
                call ent_ix
                ld   a, (ix+E_HP)
                ld   ix, (ATK_PTR)
                or   a
                ld   a, MSG_P_HIT
                jr   nz, .setm
                ld   a, MSG_P_KILL
                jr   .setm
.mmsg:          ld   a, b
                or   a
                ld   a, MSG_M_HIT
                jr   nz, .setm
                ld   a, MSG_M_MISS
.setm:          ld   (ix+E_MSG), a
                call kind_seq_ptr              ; attack sequence
                ld   de, KS_ATTACK
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   start_seq

;------------------------------------------------------------------------------
; set_reaction_at — IX = target, C = RC_*, attacker = (ATK_PTR). Priority:
; DEATH > HURT > BLOCK. react_at = the attacker's IMPACT tick (so the HURT
; follows the blow) + TURN_TICK (D3-7: a blow struck in a later tick of the
; turn, the deferred monster phase / a power attack at its release; 0 on the
; input tick). D3-8e: dh_rtick != 0 (proj_fire's strike) = that tick instead.
; Clobbers: A, B, DE, HL
;------------------------------------------------------------------------------
set_reaction_at:
                ld   a, (dh_rtick)             ; D3-8e: proj_fire's strike passes its
                ld   b, a                      ; impact tick (the attacker-kind lookup
                or   a                         ; below would be overwritten: ~0.15k T a
                jr   nz, .tick                 ; projectile hit); +24 T otherwise
                ld   hl, (ATK_PTR)
                ld   a, (hl)                   ; attacker kind (E_KIND = 0)
                ld   e, a
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e                      ; kind * 17 (was a 17-step add loop:
                ld   e, a                      ; ~0.4k T, ~0.6k contended, a hit)
                ld   d, 0
                ld   hl, kind_seqs + KS_IMPACT
                add  hl, de
                ASSERT KS_STRIDE == 17 && (K_COUNT - 1) * KS_STRIDE < 256 && E_KIND == 0
                ld   a, (TURN_TICK)
                add  a, (hl)
                ld   b, a                      ; impact tick (TURN_TICK units)
.tick:          ld   a, (ix+E_REACT)
                cp   RC_DEATH
                ret  z                         ; death sticks
                ld   a, c
                cp   RC_BLOCK
                jr   nz, .set
                ld   a, (ix+E_REACT)
                cp   RC_DODGE                  ; T7: a pending missile dodge is no real
                jr   z, .set                   ; reaction: a BLOCK replaces it
                or   a
                ret  nz                        ; never downgrade to BLOCK
.set:           ld   (ix+E_REACT), c
                ld   (ix+E_REACTAT), b
                ret

;==============================================================================
; MONSTER AI (prototype §6.4). IX = monster (active, CUR_ROOM, not pending/dying).
; Clobbers: all but IX.
;==============================================================================
ai_monster:
                call ix_slot
                ld   (ACT_SLOT), a
                ; act every 2 turns (slime): act on even TURN_COUNTER
                KFIELD KT_PERIOD
                cp   2
                jr   nz, .go
                ld   a, (TURN_COUNTER)
                and  1
                ret  nz
.go:
                ; --- yield rule (§6.4): hero mid-ladder and I block its climb.
                ; Checked against the hero's whole remaining path (cork_check),
                ; not just the next step, so a monster already parked on the
                ; ladder end moves off before the hero reaches it.
                call get_box
                call cork_check
                jr   nc, .ny2
                ; mid-ladder (non-flyer): yield ALONG the ladder, away from the
                ; hero = the hero's own climb dir; never sideways off the shaft
                ; (§3.4 snap). Blocked -> wait. AIDIR follows so it keeps going.
                call on_ladder
                jr   nz, .yside
                ld   a, (P_ENTITIES + E_AIDIR)
                ld   e, a
                ld   d, 0
                ld   a, 1
                ld   (YIELD_FLAG), a
                push de
                call try_step
                pop  de
                jr   nc, .yend
                ld   (ix+E_AIDIR), e
.yend:          xor  a
                ld   (YIELD_FLAG), a
                ret
.yside:
                ; step away from the shaft col (x only). Exactly on the shaft
                ; col: the facing side (B14: was "the roomier side", which
                ; sent a monster that had just fallen back across the shaft
                ; from a wall straight back toward that wall: x c+1 -> c ->
                ; c+1 ... for ever; the fallback step below sets the facing,
                ; so the crossing now goes on out of the other side)
                ld   a, (P_ENTITIES + E_X)     ; shaft col
                cp   (ix+E_X)
                ld   d, 1
                jr   c, .ya                    ; shaft left of me -> go right
                jr   nz, .yl
                bit  EF_LEFT_BIT, (ix+E_FLAGS) ; on the shaft col: facing
                jr   z, .ya
.yl:            ld   d, $FF
.ya:            ld   e, 0
                ld   a, 1
                ld   (YIELD_FLAG), a           ; moving away may stay on the path
                push de
                call try_step_face
                pop  de
                jr   c, .yend
                ld   a, d                      ; that side blocked (a neighbour):
                neg                            ; try the other one —
                ld   d, a                      ; two monsters side by side can't
                ld   e, 0                      ; pin the hero on the ladder
                call try_step_face
                jr   c, .yend
                ; B14 / §6.4 rule 2 ("flyers may use any in-band move that
                ; leaves the path"): both x steps blocked (a wall / block on
                ; one side, a body on the other) -> a flyer tries up, then
                ; down, inside its band; these steps must END off the path
                ; (YIELD_FLAG 0: try_step's cork_check). Else wait. (A Ghost,
                ; 4 rows in a 5-row band, can't clear a 6-row path that way;
                ; a Bat can.)
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   z, .yend
                xor  a
                ld   (YIELD_FLAG), a
                call storey_ref
                ld   (TMP4), a                 ; clamp_band's storey
                ld   e, $FF
                call .yv
                jr   c, .yend
                ld   e, 1
                call .yv
                jr   .yend
.yv:            call clamp_band                ; E = 0: out of the band
                ld   a, e
                or   a
                ret  z                         ; CF = 0
                ld   d, 0
                jp   try_step
.ny2:
                KFIELD KT_FLAGS
                and  KF_FLYER
                jp   nz, ai_flyer
                ; ================= WALKER =================
                call attack_if_reach
                ret  c
                call storey_ref
                ld   b, a
                ld   a, (PL_STOREY)
                ld   c, a                      ; C = player storey
                ld   a, b
                ld   (TMP4), a                 ; my storey
                cp   c
                jr   nz, .other
                call is_standing
                jr   nz, .other
                ; same storey, standing: step toward the player
                call dx_to_player              ; D = dx (0 if aligned)
                ld   a, d
                or   a
                ret  z
                ld   e, 0
                jp   try_step_face
.other:
                KFIELD KT_FLAGS
                and  KF_CLIMBER
                jr   z, .patrol
                call on_ladder
                jr   nz, .seek
                ; mid-ladder: continue in ai_dir
                ld   d, 0
                ld   e, (ix+E_AIDIR)
                jp   try_step
.seek:          ; C = player storey, TMP4 = my storey
                ld   a, (TMP4)
                ld   b, a
                ld   a, c
                cp   b
                ret  z
                jr   c, .wantup
                ; want down: segment {col, s+1}, s+1 < STOREY_COUNT (exit excluded)
                ld   a, b
                inc  a
                cp   STOREY_COUNT
                ret  nc
                ld   b, a
                ld   a, 1
                jr   .find
.wantup:        ld   a, b
                or   a
                ret  z                         ; {col,0} is an exit: excluded
                ld   a, $FF
.find:          ld   (TMP6), a                 ; climb dy
                ; nearest segment {col, B} in this room
                call nearest_ladder            ; A = col or $FF
                cp   $FF
                ret  z
                cp   (ix+E_X)
                jr   z, .at
                ld   d, 1
                jr   nc, .tw
                ld   d, $FF
.tw:            ld   e, 0
                jp   try_step_face
.at:            ; at the shaft: climb only if the segment is clear (no head-on)
                ld   c, a                      ; B = segment storey (its lower end)
                ld   a, b                      ; shaft rect: rows 9(B-1) .. 9B+7
                dec  a                         ; (upper standing top .. lower air bottom)
                MUL_STOREY b
                ld   b, a
                ld   d, FEAT_W
                ld   e, 2 * STOREY_ROWS - 1
                call box_free
                ret  c                         ; someone on it -> wait
                ld   d, 0
                ld   a, (TMP6)
                ld   e, a
                ld   (ix+E_AIDIR), a
                jp   try_step
.patrol:        ; non-climber on another storey: pace in the facing direction
                ld   d, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .p1
                ld   d, $FF
.p1:            ld   e, 0
                push de
                call try_step_face
                pop  de
                ret  c
                ld   a, d
                neg
                ld   d, a
                ld   e, 0
                jp   try_step_face

; nearest_ladder — nearest segment with storey B in the current room to IX.x
; (descriptor order RD_UPCOL..RD_LAD2; a tie keeps the first, as the PROTO
; list did: rooms A-D keep LAD1/LAD2 in their old list order).
; Out: A = col or $FF.  Preserves B.  Clobbers: A, C, DE, HL
nearest_ladder:
                call cur_room_desc
                inc  l                         ; -> RD_EXITS; the loop pre-increments
                ld   de, $FFFF                 ; D = best col, E = best dist
.l:             inc  l
                ld   a, l
                and  RD_STRIDE - 1
                cp   RD_LAD2 + 1
                jr   nc, .done
                call seg_storey
                cp   b
                jr   nz, .l
                ld   a, (hl)                   ; col
                or   a
                jr   z, .l                     ; none
                ld   c, a
                sub  (ix+E_X)
                jr   nc, .p
                neg
.p:             cp   e
                jr   nc, .l                    ; not strictly nearer
                ld   e, a
                ld   d, c
                jr   .l
.done:          ld   a, d
                ret

; dx_to_player — D = sign(player.x - x) (0 if equal).  Clobbers: A
dx_to_player:
                ld   a, (P_ENTITIES + E_X)
                ld   d, 0
                cp   (ix+E_X)
                ret  z
                ld   d, 1
                ret  nc
                ld   d, $FF
                ret

; attack_if_reach — if the player is in reach (either side) face + attack.
; CF = 1 if attacked.
attack_if_reach:
                ; Monsters only ever target the hero, whose box/state is cached
                ; for the turn (cache_player), so this is one direct test instead
                ; of two target scans (~0.6k T vs ~2k T per monster).
                ld   a, (PL_LADDER)
                or   a
                jr   nz, .no                   ; hero mid-ladder: no combat (§4.2)
                call on_ladder
                jr   z, .no                    ; I'm on a ladder: no combat
                call get_box
                ld   a, (PL_Y)                 ; vertical overlap
                ld   hl, PL_H
                add  a, (hl)
                dec  a
                cp   b
                jr   c, .no
                ld   a, b
                add  a, e
                dec  a
                ld   hl, PL_Y
                cp   (hl)
                jr   c, .no
                ld   a, (PL_X)
                cp   c
                jr   c, .left
                ld   a, c                      ; hero to the right: gap = px-(x+w)
                add  a, d
                ld   b, a
                ld   a, (PL_X)
                sub  b
                jr   c, .no
                ld   e, 1
                jr   .gap
.left:          ld   a, (PL_X)                 ; hero to the left: gap = x-(px+pw)
                ld   hl, PL_W
                add  a, (hl)
                ld   b, a
                ld   a, c
                sub  b
                jr   c, .no
                ld   e, $FF
.gap:           ld   (TMP3), a                 ; gap
                ld   b, a
                KFIELD KT_REACH
                cp   b
                jr   c, .no                    ; gap > reach
                ld   a, e
                ld   (TMP6), a
                call face_tmp6
                xor  a                         ; target = slot 0
                call do_attack
                scf
                ret
.no:            or   a
                ret

;------------------------------------------------------------------------------
; ai_flyer — Bat / Ghost (prototype §6.4). Band: 9s <= y <= 9s+8-h (game.md §2.1).
; Ladders are ordinary air (J1, user 2026-10-06, prototype §3.5: the B8
; ladder-end rule is gone); only try_step's anti-cork protects a climb.
; Clobbers: all but IX.
;------------------------------------------------------------------------------
ai_flyer:
                call attack_if_reach
                ret  c
                call storey_ref
                ld   (TMP4), a                 ; my storey s
                ld   a, (PL_STOREY)
                ld   hl, TMP4
                cp   (hl)
                jr   nz, .wander
                ; same storey: bat jitter first (RNG order §6.2)
                KFIELD KT_FLAGS
                and  KF_BAT
                jr   z, .chase
                ld   c, 4
                call rng_mod
                or   a
                jr   z, .wander
.chase:
                call dx_to_player
                ; stop at gap 0: if the adjacent box in dx is the player, dx = 0
                ld   a, d
                or   a
                jr   z, .dy
                push de
                call get_box
                pop  hl
                ld   a, c
                add  a, h
                ld   c, a
                push hl
                push ix
                ld   ix, P_ENTITIES
                call box_vs_ix
                pop  ix
                pop  de
                jr   nc, .dy
                ld   d, 0
.dy:            ; dy = sign(9s+1 - y)
                ld   a, (TMP4)
                MUL_STOREY b
                inc  a                         ; 9s+1: the cruising row
                ld   e, 0
                cp   (ix+E_Y)
                jr   z, .try
                ld   e, 1
                jr   nc, .try
                ld   e, $FF
                jr   .try
.wander:
                KFIELD KT_FLAGS
                and  KF_BAT
                jr   z, .ghost
                ; bat: dx = facing (reverse at walls), dy = rng(3)-1
                ld   d, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .bf
                ld   d, $FF
.bf:            ld   a, (ix+E_X)
                add  a, d
                jr   z, .rev                   ; would enter col 0
                ld   c, a
                KFIELD KT_BW
                add  a, c
                dec  a
                cp   ROOM_COLS - 1
                jr   c, .bok                   ; right col <= 30
.rev:           ld   a, d
                neg
                ld   d, a
.bok:           push de
                ld   c, 3
                call rng_mod
                dec  a
                pop  de
                ld   e, a
                call clamp_band
                jr   .try
.ghost:         call dx_to_player
                ld   e, 0
.try:           ; (dx,dy) -> (dx,0) -> (0,dy) -> wait
                ld   a, d
                or   e
                ret  z
                push de
                call try_step_face
                pop  de
                ret  c
                ld   a, d
                or   a
                jr   z, .t2
                push de
                ld   e, 0
                call try_step_face
                pop  de
                ret  c
.t2:            ld   a, e
                or   a
                ret  z
                ld   d, 0
                jp   try_step

; clamp_band — E = dy clamped so IX stays in its storey air band.  Clobbers A, B, HL
clamp_band:
                ld   a, (TMP4)                 ; storey
                MUL_STOREY b
                ld   b, a                      ; 9s
                ld   a, (ix+E_Y)
                add  a, e
                cp   b
                jr   c, .z                     ; above band top
                push af
                KFIELD KT_BH
                ld   h, a
                ld   a, b
                add  a, STOREY_AIR
                sub  h                         ; 9s+8-h
                ld   h, a
                pop  af
                cp   h
                ret  z
                ret  c
.z:             ld   e, 0
                ret

;==============================================================================
; materialise — step 3 of §3.2: PENDING monsters in CUR_ROOM whose box is free
; appear (horizontal followers walk in from the edge column; others pop in).
; Clobbers: all but IY.
;==============================================================================
materialise:
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   c, 1
.lp:            push bc
                ld   a, c
                ld   (ACT_SLOT), a
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE | EF_PENDING
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                call get_box
                call box_free
                jr   c, .next
                res  EF_PENDING_BIT, (ix+E_FLAGS)
                call build_live                ; it now collides for later checks
                call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   (ix+E_DFID), $FF
                bit  EF_WALKIN_BIT, (ix+E_FLAGS)
                jr   z, .next
                res  EF_WALKIN_BIT, (ix+E_FLAGS)
                ld   a, (ix+E_X)
                cp   1
                ld   a, 0
                jr   z, .edge                  ; left edge: from col 0
                ld   a, (ix+E_X)
                inc  a
                add  a, a
                add  a, a
                add  a, a                      ; right edge: from x+1
.edge:          ld   (ix+E_PX), a
                ld   (ix+E_MODE), M_MOVE
.next:          ld   de, P_ENT_STRIDE
                add  ix, de
                pop  bc
                inc  c
                ld   a, c
                cp   P_MAX_ENT
                jr   c, .lp
                ret

;==============================================================================
; resolve_monsters — step 2: every non-pending, living monster in CUR_ROOM acts
; in slot order (D3-8: after its status step, mon_status, unless STATUS = 0).
; Then step 3 materialise.  Clobbers: all but IY.
; far3 from read_turn_input (B3B-R2): one bank switch per turn, not per monster.
;==============================================================================
resolve_monsters:
                call cache_player
                ld   a, 1
.lp:            ld   (MON_SLOT), a
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                jr   nz, .next                 ; player already dying: stand down
                ld   a, (MON_SLOT)             ; D3-8: the status step at the start of its
                add  a, ST_FLAGS & $FF         ; phase (game.md §2.2 / §6.4); STATUS 0 =
                ld   l, a                      ; the fast path (~50 T)
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                or   a
                jr   z, .ai
                ld   a, (MON_SLOT)
                ld   hl, mon_status            ; bank 7 (status7.asm): L = 1 the action is
                call far7                      ; spent (held / confused step / fear)
                ld   a, l
                or   a
                jr   nz, .next
.ai:            call ai_monster
.next:          ld   a, (MON_SLOT)
                inc  a
                cp   P_MAX_ENT
                jr   c, .lp
                jp   materialise

; (POTIONS: potion_pickup moved to bank-7 pickup7.asm, D3-7 T5; T6: floor_pickup.)

; (B3B-13: show_impact_msg + kind_name / str_cat and the combat message words
; moved to lowram.asm / src/strings.txt: the strings are token streams in bank 1.)
