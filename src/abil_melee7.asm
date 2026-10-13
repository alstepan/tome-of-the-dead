;==============================================================================
; abil_melee7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): the
; Warrior's power attacks (Power Strike, Whirlwind; game.md §6.2) as a split
; ability turn (act7.asm: the accept on the input tick, the strike on the fire
; tick f = 2, the POWER_STRIKE / WHIRL frame's SF_IMPACT tick) and the Mage
; staff bonk. The blows themselves are bank 3 (melee_hit, rank3.asm: hit_roll
; + deal_hit).
;==============================================================================

EF_HOSTILE_BIT  EQU 2
                ASSERT EF_HOSTILE == 1 << EF_HOSTILE_BIT

;------------------------------------------------------------------------------
; abil_melee — intent7 ic_disp (ABF_MELEE), IX = hero, B = ABL_POWER /
; ABL_WHIRL, ABIL_DESC loaded (abil_load: ABIL_RK = the hero's rank row).
; Refused (L = IC_REFUSED with its line, 0 silent; no turn, a message, game.md §6.2 / §2.3): unlearned -> NOT
; LEARNED; MP < RK_MP -> NO MANA; mid-ladder or no target (melee_scan) ->
; L = IC_NOTGT, no line ("a power attack with no target is illegal: no turn,
; no MP"; use_icon pushes NO TARGET, or a reversed CONFUSED hero stumbles).
; Accepted (input tick): ABIL_TGT = the mask, act_begin_ok (TURN_PEND,
; ACT_ABL = B, ACT_AT, MON_AT), MP -= RK_MP, PD_MP, the abl_seq sequence
; (kn_power / kn_whirl).
; L = 1.  Clobbers: A, C, DE, HL (B, IX kept; a refusal: msg_push's)
; ~4-20k T (melee_scan: ~4k per find_target, contended; Power Strike 1-2, Whirlwind
; 2 + targets)
;------------------------------------------------------------------------------
abil_melee:
                ld   a, b
                sub  ABL_POWER                 ; the Warrior's k (ARANK bits 2k..)
                call abil_rank                 ; bank 2: Z = unlearned (A, C, HL)
                ld   a, TX_NOT_LEARNED
                jp   z, ic_refuse
                ld   a, (MP)
                ld   hl, ABIL_RK + RK_MP
                cp   (hl)
                ld   a, TX_NO_MANA
                jp   c, ic_refuse
                call on_ladder                 ; Z = mid-ladder (A, HL)
                jr   z, .nt
                push bc
                call melee_scan                ; DE = the target mask
                pop  bc
                ld   a, d
                or   e
                jr   z, .nt
                ld   (ABIL_TGT), de            ; power_fire strikes these
                call act_begin_ok              ; (A, HL)
                ld   a, (ABIL_RK + RK_MP)
                ld   c, a
                ld   a, (MP)
                sub  c                         ; (MP >= cost: checked above)
                ld   (MP), a
                ld   hl, PANEL_DIRTY
                set  PD_MP_BIT, (hl)
                call act_seq                   ; the abl_seq sequence (A, DE, HL)
                ld   l, 1
                ret
.nt:            ld   l, IC_NOTGT               ; use_icon pushes NO TARGET (or the
                ret                            ; reversed hero stumbles)

;------------------------------------------------------------------------------
; melee_scan — IX = hero (LIVE_LIST current: built at the turn start; nothing
; moves before the strike, the monster phase is deferred), B = ABL_POWER /
; ABL_WHIRL -> DE = the slot mask of the targets (bit s = slot s; 0 = none),
; by find_target's rules (reach, the body-row overlap, a nearer mid-ladder
; body blocks): Power Strike the nearest in the facing; Whirlwind every one
; on both sides (several bodies can share a side: a Bat over a Rat). A found
; body leaves the scan by a cleared EF_HOSTILE (restored before the return:
; find_target skips non-hostiles), so the next find_target gets the next one.
; Clobbers: A, BC, DE, HL (IX kept).  ~(1 + targets + 1) x find_target
;------------------------------------------------------------------------------
melee_scan:
                ld   de, 0
                ld   a, b
                sub  ABL_WHIRL
                ld   c, a                      ; C != 0: one target (Power Strike)
                ld   b, 2                      ; sides (Whirlwind)
                ld   a, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .f
                neg
.f:             ld   (TMP6), a                 ; the facing first
.l:             push bc
                push de
                call find_target               ; A = slot / $FF (A, BC, DE, HL)
                pop  de
                pop  bc
                cp   $FF
                jr   z, .side
                ld   hl, 1                     ; HL = 1 << slot (slot 1..15)
.sh:            add  hl, hl
                dec  a
                jr   nz, .sh
                ld   a, l
                or   e
                ld   e, a
                ld   a, h
                or   d
                ld   d, a
                ld   a, 1
                call mask_hostile              ; res EF_HOSTILE: the new one (and the
                inc  c                         ; ones before: already clear)
                dec  c
                jr   z, .l                     ; Whirlwind: the next on this side
                jr   .done
.side:          inc  c
                dec  c
                jr   nz, .done                 ; Power Strike: the facing only
                ld   a, (TMP6)
                neg
                ld   (TMP6), a
                djnz .l
.done:          xor  a                         ; set EF_HOSTILE again on all
                ; fall through
; mask_hostile — DE = slot mask, A = 0: set EF_HOSTILE on every masked slot,
; A != 0: clear it.  Clobbers: A, HL (BC, DE, IX kept)
mask_hostile:
                push bc
                push de
                push ix
                ld   c, a
                ld   b, 0                      ; slot
.m:             srl  d
                rr   e
                jr   nc, .n
                push de
                ld   a, b
                call ent_ix                    ; (A, E)
                pop  de
                res  EF_HOSTILE_BIT, (ix+E_FLAGS)
                inc  c
                dec  c
                jr   nz, .n
                set  EF_HOSTILE_BIT, (ix+E_FLAGS)
.n:             inc  b
                ld   a, d
                or   e
                jr   nz, .m
                pop  ix
                pop  de
                pop  bc
                ret

;------------------------------------------------------------------------------
; power_fire — the power attack's strike (act_fire, fire tick f = 2, before
; anim_tick runs the POWER_STRIKE / WHIRL entry's SF_IMPACT): IX = hero,
; B = ABL_POWER / ABL_WHIRL. The targets = ABIL_TGT (the accept's
; melee_scan: nothing moved since; a slot that is DYING / HP 0 meanwhile —
; none can be today — is skipped: no roll, no line), one melee_strike each in slot order
; (RNG order: per target d20, 1dN, the effect chance). The hero's E_MSG /
; E_HIT are cleared: each blow logs its own line, so do_impact adds none.
; FX (impact-only, the strike tick + 1 more, from ab_def ABD_IF1 / IF2):
; Power Strike: power_burst on a target that lost HP (melee_strike);
; Whirlwind: spark_fizz on each side of the hero (the sweep, hit or not), at
; the col just outside its body, the staff / bow row (top + PF_ROW_DY).
; Out: L = 1 struck.  Clobbers: all but IY (IX kept).
; ~1k T + ~6-9k per target (melee_hit + deal_hit + the line) + ~1.5k per FX;
; budget "cast" (tests/budget.py "wcast")
;------------------------------------------------------------------------------
power_fire:
                ld   de, (ABIL_TGT)
                xor  a
                ld   (ix+E_MSG), a
                ld   (ix+E_HIT), a
                ld   c, a                      ; slot 0 (the hero: never a target)
.l:             srl  d
                rr   e
                jr   nc, .n
                push de                        ; T7: skip a slot that died since the
                ld   a, c                      ; accept (none can today: nothing
                call slot_live                 ; acts in between) — no d20, no line
                pop  de
                jr   z, .n
                push bc
                push de
                ld   a, c
                call melee_strike
                pop  de
                pop  bc
                ; Power Strike has ONE target (melee_scan stops at the first) and
                ; its melee_strike -> imp_fx (power_burst) overwrites ABIL_DESC
                ; (ABD_* / ABIL_RK) with the FX descriptor: a second melee_hit would
                ; read garbage. Stop here (T7 review: made explicit). Whirlwind
                ; strikes them all first; its imp_fx calls come after the loop.
                ld   a, b
                cp   ABL_POWER
                jr   z, .out
.n:             inc  c
                ld   a, d
                or   e
                jr   nz, .l
                ld   a, b
                cp   ABL_WHIRL
                jr   nz, .out
                ld   bc, (ABIL_DESC + ABD_IF1) ; C = IF1, B = IF2 (read before imp_fx's
                ld   a, (ix+E_Y)               ; descriptor overwrites them)
                add  a, PF_ROW_DY
                ld   d, a                      ; D = the row
                ld   a, (ix+E_X)
                dec  a
                ld   e, a                      ; E = x - 1 (x 0: off screen, fx_set hides it)
                push de
                push bc
                ld   hl, ABIL_IMPT_DELAY
                ld   a, FXDF_LEFT
                call imp_fx
                pop  bc
                pop  de
                push bc
                KFIELD KT_BW
                pop  bc
                inc  a
                add  a, e
                ld   e, a                      ; x + w
                ld   hl, ABIL_IMPT_DELAY
                xor  a                         ; facing right
                call imp_fx
.out:           ld   l, 1
                ret
                ASSERT ABD_IF2 == ABD_IF1 + 1
                ASSERT P_MAX_ENT <= 16                    ; ABIL_TGT: a 16-bit slot mask
                ; (hazard, not asserted: imp_fx's descriptor spans ABIL_DESC +
                ; 0..FXD_LEN-1, over ABD_FLAGS and ABIL_RK — hence Power Strike's
                ; break after its one target above, and Whirlwind's FX after the loop)

; slot_live — slot A -> NZ: not DYING and HP > 0.  Clobbers: A, E (IX kept)
slot_live:
                push ix
                call ent_ix                    ; (A, E)
                ld   a, (ix+E_FLAGS)
                and  EF_DYING
                jr   nz, .x                    ; NZ -> make it Z below
                ld   a, (ix+E_HP)
                or   a
                pop  ix
                ret
.x:             xor  a
                pop  ix
                ret
ABIL_IMPT_DELAY EQU (1 << 8) | 0               ; H = FXD_IMPT 1, L = FXD_DELAY 0: the
                                               ; flight frame IF1 on the strike tick, IF2 the next

;------------------------------------------------------------------------------
; melee_strike — one power blow on slot A (IX = hero, ABIL_DESC loaded):
; melee_hit (bank 3), then the impact the anim would give a melee blow, on
; this tick (the strike frame's SF_IMPACT tick): HP lost -> the target
; flashes ATTR_HIT and its HURT / DEATH (deal_hit) starts now (E_REACTAT =
; TURN_TICK: set_reaction_at added the Knight's KS_IMPACT to it); the line
; "YOU HIT / MISS / KILL THE <kind>"; Power Strike: power_burst on it
; (front_cell; FIDA = IF1, IMPA = IF2: set on this tick and the next).
; Clobbers: all but IY (IX kept)
;------------------------------------------------------------------------------
melee_strike:
                ld   (ix+E_TGT), a
                push af
                ld   hl, melee_hit
                call far3                      ; L = HP lost, H = 1 hit; IX = hero
                pop  af
                push ix
                push af
                push hl
                call ent_ix                    ; IX = target (A, E)
                pop  hl
                ld   b, MSG_P_MISS
                dec  h
                jr   nz, .msg
                ld   b, MSG_P_HIT
                ld   a, (ix+E_HP)
                or   a
                jr   nz, .al
                ld   b, MSG_P_KILL
.al:            ld   a, l
                or   a
                jr   z, .msg                   ; nothing lost (immune): no flash
                ld   (ix+E_FLT), FLASH_TICKS
                ld   (ix+E_FLA), ATTR_HIT
                ld   a, (TURN_TICK)
                ld   (ix+E_REACTAT), a
.msg:           ld   c, (ix+E_KIND)
                push hl
                call impact_line               ; (A, BC, DE, HL; any bank)
                pop  hl
                pop  af                        ; A = slot
                pop  ix
                inc  l
                dec  l
                ret  z                         ; no HP lost: no burst
                ld   hl, ABIL_DESC + ABD_FLAGS
                bit  ABF_DMGX2_BIT, (hl)
                ret  z                         ; Whirlwind: its fizz is per side
                ld   bc, (ABIL_DESC + ABD_IF1) ; C = IF1, B = IF2
                push bc
                call front_cell                ; E col, D row, A flags
                pop  bc
                ld   hl, ABIL_IMPT_DELAY
                jr   imp_fx
ABF_DMGX2_BIT   EQU 4
                ASSERT ABF_DMGX2 == 1 << ABF_DMGX2_BIT

;------------------------------------------------------------------------------
; melee_bonk — intent7 ic_melee, right after the melee blow (do_attack, far3),
; IX = hero, (ix+E_TGT) = the target slot, (ix+E_HIT) = 1 the blow took HP.
; D3-7 T4, the Mage staff bonk (game.md §6.1 "Release ticks" / §6.2): every
; Mage swing plays wz_bonk (CAST1 2 -> STAFF_SWING 3, replacing do_attack's
; KS_ATTACK; same KS_IMPACT, so the target's reaction tick stands); a hit
; also starts an impact-only FX, staff_bonk (imp_fx): at front_cell,
; FXD_DELAY = WZ_WIND - 1: an impact-only FX shows its impact at fx_tick
; #delay + 1, i.e. on KS_IMPACT, with the STAFF_SWING and the HURT.
; The caller sets L = 1 after.  Clobbers: A, BC, DE, HL (IX kept)
;------------------------------------------------------------------------------
melee_bonk:
                ld   a, (ix+E_KIND)
                cp   K_WIZARD
                ret  nz
                ld   hl, wz_bonk
                call start_seq                 ; bank 2 (A)
                ld   a, (ix+E_HIT)
                or   a
                ret  z                         ; a miss / no HP lost: no bonk
                ld   a, (ix+E_TGT)
                call front_cell                ; E col, D row, A flags
                ld   bc, (FID_staff_bonk << 8) | FX_NONE   ; no flight sprite
                ld   hl, (PF_IMPT << 8) | (WZ_WIND - 1)
                ; fall through
;------------------------------------------------------------------------------
; imp_fx — start an impact-only FX, its descriptor built in ABIL_DESC (the
; ability's row is spent by then; fx_start copies it): E = FXD_COL, D =
; FXD_ROW, A = FXD_FLAGS, C = FXD_FIDA = FIDB (FX_NONE: hidden until the
; impact), B = FXD_IMPA = IMPB, L = FXD_DELAY, H = FXD_IMPT; 1 segment of 0
; cells, the frames' own attr.  Clobbers: all but IY (IX kept).  ~1.2k T
;------------------------------------------------------------------------------
imp_fx:
                ld   (ABIL_DESC + FXD_FLAGS), a
                ld   (ABIL_DESC + FXD_COL), de
                ld   (ABIL_DESC + FXD_DELAY), hl
                ld   l, c
                ld   h, c
                ld   (ABIL_DESC + FXD_FIDA), hl
                ld   l, b
                ld   h, b
                ld   (ABIL_DESC + FXD_IMPA), hl
                ld   hl, 1                     ; 1 segment of 0 cells
                ld   (ABIL_DESC + FXD_NSEG), hl
                xor  a
                ld   (ABIL_DESC + FXD_ATTR), a ; the frame's own attr
                push ix
                ld   hl, ABIL_DESC
                call fx_start                  ; bank 2 (all but IY)
                pop  ix
                ret
                ASSERT FXD_ROW == FXD_COL + 1 && FXD_IMPT == FXD_DELAY + 1 && FXD_SEGS == FXD_NSEG + 1
                ASSERT FXD_FIDB == FXD_FIDA + 1 && FXD_IMPB == FXD_IMPA + 1
                ASSERT ABIL_DESC_LEN >= FXD_LEN && WZ_WIND >= 1

;------------------------------------------------------------------------------
; front_cell — IX = hero, A = target slot -> the cell of a 16x16 FX on the
; target: E = its front col (the one facing the hero; the frame reaches one
; col into the body), D = the staff row (hero top + PF_ROW_DY) clamped so
; both 8-px rows lie in the target's body, A = FXDF_LEFT if the hero faces
; left, else 0.  Clobbers: A, BC, DE, HL (IX kept)
;------------------------------------------------------------------------------
front_cell:
                push ix
                ld   e, a
                ld   a, (ix+E_Y)
                add  a, PF_ROW_DY
                ld   h, a                      ; H = the staff row
                ld   a, (ix+E_FLAGS)
                and  EF_LEFT
                rrca
                rrca
                rrca                           ; EF_LEFT -> FXDF_LEFT
                ld   l, a
                push hl
                ld   a, e
                call ent_ix                    ; IX = target (A, E)
                call get_box                   ; C x, B y, D w, E h (A, HL)
                pop  hl                        ; H = staff row, L = flags
                ld   a, b
                add  a, e
                sub  2                         ; the target's last-but-one row
                cp   h
                jr   c, .lo
                ld   a, h                      ; min(staff row, y + h - 2)
.lo:            cp   b
                jr   nc, .row
                ld   a, b                      ; max(.., y)
.row:           ld   h, a
                ld   a, l
                or   a
                ld   a, c                      ; facing right: the target's left col
                jr   z, .c
                add  a, d
                dec  a                         ; facing left: its right col
.c:             ld   e, a
                ld   d, h
                ld   a, l
                pop  ix
                ret
                ASSERT FXDF_LEFT == EF_LEFT >> 3
