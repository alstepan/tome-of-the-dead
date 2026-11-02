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
; Data read: kind_tab / seq_rows / P_ENTITIES / LIVE_LIST / TMP* (bank 2),
; ROOM_MAP / ROOM_DESC / FLOOR_LIST (bank 5): none at $C000.
;
; Entries (far3 from bank 2; far3 clobbers AF, so nothing returns in A/F):
;   (resolve_monsters: bank 2 since BLAIR-FIX, logic.asm; it pages bank 3 once
;                     per turn, so the per-monster ai_monster calls, materialise
;                     and the monster attacks' do_attack still run in bank 3)
;   do_attack         try_horizontal (the hero's bump attack; A = target slot)
; Contention: bank 3 is contended, so these bodies pay ULA contention on code
; fetches (measured in tests/budget.py; the bank-2 helpers they call do not).
;==============================================================================

; (try_quaff: D3-7 T5 moved into bank-7 intent7.asm ic_potion.)

;------------------------------------------------------------------------------
; dmg_roll — RECLAIM-B: the shared melee / ability damage roll (do_attack,
; rank3 abil_hit). In : IX = attacker.  Out: A = 1d(KT_DIE) + KT_BONUS (signed: the
; hero's weapon m, gear6 hero_recalc), F from that add (Z / S for the max(1, ..)
; clamp), C = N, D = the bonus.  Keeps E.  Clobbers: A, B, C, D, HL, F.
; One rng_mod (the RNG order is unchanged). The bonus is read first so the die
; column is reached from the same HL (KT_DIE / KT_BONUS share page 0):
; 105 T + rng_mod (+1 T vs the two inline KFIELDs it replaces).
;------------------------------------------------------------------------------
dmg_roll:
                KFIELD KT_BONUS
                ld   d, a
                ld   a, l
                sub  KT_BONUS - KT_DIE         ; L = kind + KT_DIE (no borrow: kind < 32)
                ld   l, a
                ld   c, (hl)
                call rng_mod                   ; 0..N-1 (keeps C, DE)
                inc  a
                add  a, d
                ret
                ASSERT (KT_DIE >> 8) == (KT_BONUS >> 8) && KT_BONUS > KT_DIE

;------------------------------------------------------------------------------
; do_attack — IX = attacker, A = target slot: one melee blow (D3-6a: on the
; shared core, combat3.asm). hit_roll (F1, the d20 first), then damage 1dN +
; bonus (kind_tab, prototype §6.2 / F2) dealt by deal_hit with the attacker's
; kx_tab KX_MELEE pair (type + on-hit effect: PHYS; the Ghost's DRAIN touch, CONFUSED
; 4 at 1 in 4). Sets the attacker's ATTACK sequence + IMPACT info (E_HIT = the
; HP lost, LOG-DMG: the line's -D; 0: an immune target does not flash; E_MSG hit / miss / kill)
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
                ld   a, (ix+E_KIND)            ; C / E = the kind's melee pair
                add  a, a                      ; (kx_tab KX_MELEE, 3F-T2: was the
                add  a, a                      ; kx_melee table)
                add  a, a
                add  a, (kx_tab & $FF) + KX_MELEE
                ld   l, a
                ld   h, kx_tab >> 8
                ld   c, (hl)
                inc  l
                ld   e, (hl)
                push bc
                call dmg_roll                  ; damage: 1dN + bonus (keeps E)
                jr   z, .one                   ; 3F-T6: max(1, 1dN + bonus) (a worn weapon at m < 0)
                jp   p, .pos
.one:           ld   a, 1
.pos:           pop  bc
                call atk_mod                   ; 3F-T8: golden + 1; the Ogre's SLAM x 1.5 + STUN
                ld   b, a
                ld   a, (TMP2)
                call deal_hit                  ; L = HP lost; IX = attacker; H = 1: parried (3F-T6)
                ld   a, l
                or   a
                jr   nz, .lost
                dec  h
                jr   nz, .res                  ; nothing lost (immune): no flash
                ld   (ix+E_HIT), a             ; parried: no flash (A = 0), IX = the attacker (deal_hit's
                                               ; contract); the line "THE <kind> PARRIES!" at IMPACT
                ld   a, MSG_P_PARRY
                jr   .setm
.lost:          push af                        ; LOG-DMG: A = L, the E_HIT (the line's -D; < 128: a hp)
                ld   a, (ix+E_KIND)            ; 3F-T6: an on-hit side effect of the Mummy (FOOD) / Black Widow
                ld   hl, mummy6                ; (ACID, 1 in 4): R6, only on a hit that cost HP
                cp   K_MUMMY
                jr   z, .fx
                ld   hl, acid6
                cp   K_BLACK_WIDOW
                jr   nz, .nfx
.fx:            call far6
.nfx:           pop  af                        ; (was ld a, 1: 0 B)
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
                add  a, KT_SEQ & $FF           ; 3F-T2: its seq_rows row (kind_tab KT_SEQ,
                ld   l, a                      ; the per-level cache) + KS_IMPACT: no
                ld   h, (kind_tab + KT_SEQ) >> 8   ; multiply (was kind * 17)
                ld   a, (hl)
                add  a, KS_IMPACT              ; a row never crosses the page (seq_rows)
                ld   l, a
                ld   h, seq_rows >> 8
                ASSERT E_KIND == 0
                ld   a, (TURN_TICK)
                add  a, (hl)
                ld   b, a                      ; impact tick (TURN_TICK units)
.tick:          ld   a, (ix+E_REACT)
                cp   RC_DEATH
                ret  z                         ; death sticks
                ld   a, c
                cp   RC_BLOCK
                jr   z, .blk
                cp   RC_PARRY                  ; 3F-T13bc: a parry flash never downgrades either
                jr   nz, .set
.blk:
                ld   a, (ix+E_REACT)
                cp   RC_DODGE                  ; T7: a pending missile dodge is no real
                jr   z, .set                   ; reaction: a BLOCK replaces it
                or   a
                ret  nz                        ; never downgrade to BLOCK
.set:           ld   (ix+E_REACT), c
                ld   (ix+E_REACTAT), b
                ret

;==============================================================================
; MONSTER AI (prototype §6.4). IX = monster (active, CUR_ROOM, not pending/dying),
; ACT_SLOT = its slot (3F-B5: the caller, resolve_monsters, stores it; was an
; ix_slot here, ~0.1k T). No result.  Clobbers: all but IX.
; 3F-B5 walker path: get_box once (cork_check keeps BC / DE), the feet row y+h
; looked up once (was feet_mod x3 + get_box again in attack_if_reach), and a
; known-standing step enters try_step past its on_ladder (~0.3k T a step).
;==============================================================================
ai_monster:
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
                ; act every 2 turns (slime): act on even TURN_COUNTER. B18: after
                ; the yield (§6.4 "checked first, all kinds"): a slime on the
                ; climb path skipped every other yield, so the 2nd block found it
                ; unmoved and the squeeze swapped it onto the other storey. Cost: a
                ; slime's off turn now runs ai_monster's get_box + cork_check
                ; first (~0.2k T; cork_check's fast path 30 T off a climb)
                ; RECLAIM-C (b): KF_SLOW in the flags byte (was the KT_PERIOD column):
                ; one KFIELD for both tests, HL kept for the reload (-8 B, -~40 T)
                KFIELD KT_FLAGS
                bit  KF_SLOW_BIT, a
                jr   z, .go
                ld   a, (TURN_COUNTER)
                and  1
                ret  nz
                ld   a, (hl)                   ; HL = the KT_FLAGS byte still
.go:
                and  KF_FLYER
                jp   nz, ai_flyer
                ; ================= WALKER =================
                ; BC / DE = the box still (get_box above; cork_check keeps BC,
                ; DE, KFIELD clobbers A / HL only). n = y+h (= feet_mod's n):
                ; storey_ref and is_standing from one KT_DIV9 / KT_MOD9 pair.
                ASSERT KT_MOD9 == KT_DIV9 + $20 && ((kind_tab + KT_DIV9) & $3F) <= 8   ; RECLAIM-C (b): bit 5 clear on the DIV9 row
                ld   a, b
                add  a, e
                add  a, (kind_tab + KT_DIV9) & $FF
                ld   l, a
                ld   h, (kind_tab + KT_DIV9) >> 8
                ld   a, (hl)                   ; n div 9 (0..2)
                ASSERT STOREY_COUNT == 2       ; min(div, 1) as 0 -> 0, else 1:
                cp   1                         ; CF iff 0
                sbc  a, a                      ; $FF / 0
                inc  a                         ; 0 / 1 (4 B, 15 T vs cp / jr / ld 6 B)
                ld   (TMP4), a                 ; my storey (storey_ref; TMP4 is scratch
                set  5, l                      ; nothing in the attack reads) -> KT_MOD9 row
                ld   a, (hl)
                xor  STOREY_AIR                ; Z / A = 0: standing (CF = 0)
                push af
                call z, attack_if_reach.box    ; walker: on_ladder Z = not standing -> no attack
                pop  hl                        ; H = 0 iff standing (flags kept)
                ret  c
                call ai_rhook                  ; 3F-T7 ranged hook (game.md §9.2 step 4): bank-2 rk_tab
                ret  c                         ; reject (~66 T), a shooter far6s R6 ai_ranged; CF = the turn
                                               ; is used. HL / TMP4 kept (the B5 box in BC / DE is not:
                                               ; nothing below reads it)
                ld   a, (PL_STOREY)
                ld   c, a                      ; C = player storey
                ld   a, (TMP4)
                xor  c
                or   h
                jr   nz, .other                ; another storey, or not standing
                ; same storey, standing: step toward the player
                call dx_to_player              ; D = dx (0 if aligned)
                ld   a, d
                or   a
                ret  z
.fstep:         ld   e, 0                      ; try_step_face for a STANDING walker:
                ld   a, d                      ; enters try_step past its on_ladder test
                ld   (TMP6), a                 ; (Z only mid-ladder; ~0.3k T). No result:
                call try_step.vert             ; ai_monster's caller reads none (CF of
                ret  nc                        ; face_tmp6 is not try_step_face's)
                jp   face_tmp6
.other:
                ld   b, h                      ; B = 0 iff standing
                KFIELD KT_FLAGS
                and  KF_CLIMBER
                jp   z, .patrol
                ld   a, b                      ; (on_ladder: walker -> NZ iff standing)
                or   a
                jr   z, .seek
                ; mid-ladder: continue in ai_dir
                ld   d, 0
                ld   e, (ix+E_AIDIR)
                call try_step
                ret  c
                ; AI-L1 review: blocked, and ai_dir leads AWAY from the hero's storey
                ; (it changed storey mid-climb): turn round (the turn is spent), else
                ; it hangs over a waiter at the foot for ever. Away <=> bit 7 of
                ; ai_dir (up) == PL_STOREY (segment {c,1}: 0 above, 1 below)
                ld   a, (PL_STOREY)
                rrca
                xor  (ix+E_AIDIR)
                ret  m                         ; it leads toward the hero: keep waiting
                ld   a, (ix+E_AIDIR)
                neg
                ld   (ix+E_AIDIR), a
                ret
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
                ld   e, a                      ; E = col (lq_block)
                ld   d, 1
                jr   nc, .sk                   ; (.seek: standing)
                ld   d, $FF
.sk:            ld   a, (ix+E_AIDIR)           ; scratch/lq-hold: lq_block's back-off left LQ_HOLD
                xor  LQ_HOLD                   ; ($80; a standing walker's E_AIDIR is free): hold
                jr   nz, .sk1                  ; this turn (no re-approach: a period-1 loser no
                ld   (ix+E_AIDIR), a           ; longer phase-locks a period-2 winner). 38 T
                ret
.sk1:           push de                        ; AI-L1: .fstep inline, but a failed step
                ld   e, 0                      ; goes on to the ladder queue (bank 3 lq3.asm,
                ld   a, d                      ; game.md §9.2 'Ladder queue': strongest
                ld   (TMP6), a                 ; first; the loser near the shaft backs
                call try_step.vert             ; off 1 cell). +19 B here; the queue runs
                pop  de                        ; only on a blocked seek step
                jp   c, face_tmp6
                jp   lq_block                  ; (bank 3 since MEM-RECLAIM w3: was `ld hl, lq_block` / far6, R6)
.at:            ; at the shaft: climb only if the segment is clear (no head-on).
                ; AI-L1 J1 (game.md §9.2): the rect also covers my own end box, which
                ; is harmless because every climber is FEAT_W wide (main.asm kind_tab
                ; ASSERT): a body overlapping the near-end box on my storey overlaps
                ; me (same feet row) or sits above my head in my first climb step.
                ; fix/spider-climb: the 4-wide Spider (2 rows tall) is the one exception, so the
                ; rect is the climber's KT_BW wide (FEAT_W for every other climber): the Spider
                ; at col covers col .. col + 3 all the way up, and a body in its far-end box at
                ; col + 3 must stop the start (+8 B vs ld d, FEAT_W; ~30 T, at the shaft only).
                ; A body overlapping the near-end box overlaps the Spider on its storey; only
                ; one above its 2-row head (a flyer) can wait the start (it moves on). lq3
                ; LQ_W: its queue box is 4 wide.
                ld   c, a                      ; B = segment storey (its lower end)
                ld   a, b                      ; shaft rect: rows 9(B-1) .. 9B+7
                dec  a                         ; (upper standing top .. lower air bottom)
                MUL_STOREY b
                ld   b, a
                KFIELD KT_BW                   ; (A, HL; B / C kept)
                ld   d, a
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

; rs_hit / rs_deal — 3F-T7: far3 entries for R6 ai_ranged (ranged6.asm), which
; cannot call bank 3. rs_hit: A = 0 (the hero), IX = the shooter -> L = 1 hit /
; 0 miss (hit_roll, modifier 0). rs_deal: A = deal_hit C, D = damage, E = the
; effect parameter, IX = the shooter -> L = HP the hero lost (deal_hit).
; Clobbers: all but IX.
rs_hit:         ld   b, 0
                call hit_roll
                ld   l, a
                ret
rs_deal:        ld   c, a
                xor  a                         ; target = the hero
rs_dl:          ld   b, d
                jp   deal_hit
; rs_self — 3F-T11b (arch6.asm am_cast, game.md §9.9 A6): the Mirror Helm return, D
; = the roll, E = the Archmage's slot, IX = it: a DARK hit on itself (no rider).
rs_self:        ld   c, DTY_DARK | DH_NODEF
                ld   a, e
                jr   rs_dl

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
; IX = monster. CF = 1 if attacked.  Clobbers: all but IX.
; .box (3F-B5, ai_monster / ai_flyer): BC / DE = IX's get_box, IX known not
; mid-ladder (a flyer, or a standing walker): skips on_ladder + get_box (the
; two pure tests only reorder: either fails -> no attack).
attack_if_reach:
                ; Monsters only ever target the hero, whose box/state is cached
                ; for the turn (cache_player), so this is one direct test instead
                ; of two target scans (~0.6k T vs ~2k T per monster).
                call on_ladder
                jr   z, .no                    ; I'm on a ladder: no combat
                call get_box
.box:           ld   a, (PL_LADDER)
                or   a
                jr   nz, .no                   ; hero mid-ladder: no combat (§4.2)
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
                call reach_ok                  ; CF: gap > reach (3F-T8: the Ogre's SLAM reach 2)
                jr   c, .no
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
ai_flyer:                                      ; BC / DE = the box (ai_monster's get_box)
                call attack_if_reach.box       ; 3F-B5: a flyer is never mid-ladder
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
                ld   a, (PEND_N)               ; 3F-B4: nothing PENDING in CUR_ROOM -> done
                or   a                         ; (was a 15-slot walk, ~2.2k T). PEND_N is as of
                ret  z                         ; the last build_live; every route that sets
                                               ; PENDING (squeeze, arrival_conflicts) rebuilds,
                                               ; and the turn starts with build_live: an UPPER bound
                                               ; (kills only leave it too high: harmless). RULE: anything
                                               ; that sets PENDING in CUR_ROOM or moves a PENDING body
                                               ; into it before the monster phase must call build_live
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   c, 1
.lp:            ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE | EF_PENDING
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                push bc                        ; (only a pending body pays the save + slot)
                ld   a, c
                ld   (ACT_SLOT), a
                call get_box
                call box_free
                jr   c, .nextp
                call corpse_hit                ; B19c: a corpse still in the box holds it
                jr   c, .nextp
                res  EF_PENDING_BIT, (ix+E_FLAGS)
                call build_live                ; it now collides for later checks
                call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   (ix+E_DFID), $FF
                bit  EF_WALKIN_BIT, (ix+E_FLAGS)
                jr   z, .nextp
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
.nextp:         pop  bc
.next:          ld   de, P_ENT_STRIDE
                add  ix, de
                inc  c
                ld   a, c
                cp   P_MAX_ENT
                jr   c, .lp
                ret

;------------------------------------------------------------------------------
; corpse_hit — B19c: CF = 1 if a DYING body of CUR_ROOM (not PENDING)
; overlaps box C,B,D,E. prototype §3.7 materialises a pending body
; when its box is "free of all non-pending entities"; box_free skips DYING
; ones (the movement rule, §6.1), so a follower hidden under the first one
; through the door (both PENDING on the same entry box, B19b) popped up on its
; corpse the turn it was killed — the user's "dagger kill comes back" (same
; kind, death animation, then alive and attacking). It now waits until the
; death sequence has freed the slot, then walks in from the edge.
; Walks LIVE_LIST (CUR_ROOM, not PENDING; DYING re-checked live, as box_free;
; a slot freed mid-turn reads flags 0 = no corpse). Only called for a pending
; body whose box is otherwise free (materialise; 0 T in the common turn).
; Preserves BC, DE, IX.  Clobbers: A, HL.   ~50 T + ~173 T per live entry (≈2.8k T at LIVE_N 16; runs once per materialise attempt whose box is otherwise free)
;------------------------------------------------------------------------------
corpse_hit:
                push ix
                ld   a, (LIVE_N)
                ld   hl, LIVE_LIST
.l:             or   a                         ; CF = 0
                jr   z, .out
                push af
                push hl
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                bit  EF_DYING_BIT, (ix+E_FLAGS) ; (BIT / INC HL keep CF = 0)
                call nz, box_vs_ix             ; CF = 1: overlaps (A, HL)
                pop  hl
                jr   c, .hit
                ld   a, l
                add  a, LL_STRIDE              ; (LIVE_LIST: one page, ASSERTed)
                ld   l, a
                pop  af
                dec  a
                jr   .l
.hit:           pop  af
                scf                            ; CF = 1: a corpse in the box
.out:           pop  ix
                ret

; (BLAIR-FIX: resolve_monsters, the step-2 loop, moved to bank 2 logic.asm: its
; 15-slot walk runs uncontended and its callers reach it without far3.)

; (POTIONS: potion_pickup moved to bank-7 pickup7.asm, D3-7 T5; T6: floor_pickup.)

; (B3B-13: show_impact_msg + kind_name / str_cat and the combat message words
; moved to lowram.asm / src/strings.txt: the strings are token streams in bank 1.)
