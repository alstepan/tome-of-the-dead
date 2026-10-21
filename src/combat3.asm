;==============================================================================
; combat3.asm — D3-6a: the shared combat core in BANK 3 (plan "3D breakdown"
; decision D). INCLUDEd from bank3.asm after turn3.asm. Every damage source
; (melee do_attack now; proj_fire D3-6b, abilities D3-7) goes through:
;   hit_roll  F1 to-hit (game.md §7, foundations F1; §6.4 held = eva 0)
;   deal_hit  resistances, DEF, saturation, kill + XP, drain heal, wake /
;             thaw, status-effect apply (game.md §4.1, §6.0, §6.4, §11.4)
; Both are entered from bank-3 code only (do_attack is far3'd for the hero's
; bump). Callees: bank-2 rng_mod / ent_ix / KFIELD, low-RAM msg_push /
; impact_line (they restore the caller's bank: conventions "Banking").
; D3-8: the BOSS rules (KX_IMM bit 7, IMMF_BOSS_BIT: ASLEEP / FEAR immune,
; HOLD / MIND halved after R) and WEAK's hero penalties (hit_roll atk -2 /
; eva -1, deal_hit dmg -1 min 1); the status step itself is status7.asm.
;==============================================================================

;------------------------------------------------------------------------------
; kx_melee — a kind's melee hit as deal_hit arguments: {C, E} per kind id,
; stride 2 (game.md §9.1 dmg column + on-hit effects). Monster DEF is 0 in 3D;
; 3F adds the Spider's POISON 9, the Mummy's curse (WEAK 12, 1 in 3), ...
;------------------------------------------------------------------------------
KM_STRIDE       EQU 2
    MACRO KMROW dty, efx, chance, turns
                DB   (dty) | ((efx) << DH_EFX_SHIFT), ((chance) << 4) | (turns)
    ENDM
kx_melee:
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_KNIGHT (sword)
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_WIZARD (staff)
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; id 2 retired
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_SKELETON
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_GOBLIN
                KMROW DTY_DRAIN, EFX_CONFUSED, 4, 4  ; K_GHOST: 1d4 DRAIN, touch 1 in 4 -> CONFUSED 4 (no heal: §9.1)
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_RAT
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_BAT
                KMROW DTY_PHYS, EFX_NONE, 0, 0       ; K_SLIME
                ASSERT $ - kx_melee == K_COUNT * KM_STRIDE
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1 && K_SKELETON == 3 && K_GOBLIN == 4
                ASSERT K_GHOST == 5 && K_RAT == 6 && K_BAT == 7 && K_SLIME == 8

;------------------------------------------------------------------------------
; hit_roll — F1: hit iff d20 + atk + B >= 10 + eva (nat 20/1 off, game.md §7).
; In : IX = attacker, A = target slot, B = to-hit modifier (signed: melee 0,
;      Power Strike +2, dagger +1). eva counts 0 against a target with a HOLD
;      effect (FROZEN / ASLEEP / STUNNED, §6.4). atk / eva: kind_tab (the
;      hero's columns carry the §4.1 level steps: xp_turn, D3-9b). D3-8: a WEAK hero attacks at -2 and
;      his eva counts -1 (signed; §6.4 / §7).
; Out: A = 1 hit (NZ) / 0 miss (Z). IX kept.
; RNG: exactly one d20 (the first draw of an attack, prototype §6.2 order).
; Clobbers: A, BC, DE, HL.   ~0.45k T (+0.1k for a non-held target's eva)
;------------------------------------------------------------------------------
hit_roll:
                ld   e, a                      ; E = target slot
                ld   d, b                      ; D = modifier
                ld   a, (ST_FLAGS)             ; D3-8: a WEAK hero (§6.4 / §7) attacks at -2
                and  STS_WEAK                  ; (slot 0's WEAK first: 32 T when clear)
                jr   z, .nw
                bit  EF_PLAYER_BIT, (ix+E_FLAGS)
                jr   z, .nw
                dec  d
                dec  d
.nw:            ld   c, 20
                call rng_mod                   ; 0..19 (keeps C, DE)
                inc  a
                add  a, d
                ld   d, a                      ; d20 + mod
                KFIELD KT_ATK
                add  a, d
                sub  10
                ld   d, a                      ; D = d20 + atk + mod - 10 (signed, |D| < 64)
                ld   a, e
                add  a, ST_FLAGS & $FF         ; status byte of the target (one page)
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   b, 0                      ; held: eva 0
                ld   a, (hl)
                and  STS_HOLD
                jr   nz, .cmp
                ld   a, (hl)                   ; D3-8: WEAK (the hero only): eva - 1
                and  STS_WEAK
                jr   z, .e0
                dec  b
.e0:            push ix
                ld   a, e
                call ent_ix                    ; (A, E)
                KFIELD KT_EVA
                pop  ix
                add  a, b
                ld   b, a
.cmp:           ld   a, d
                sub  b                         ; >= 0 (signed) <=> hit
                jp   m, .miss
                ld   a, 1
                or   a
                ret
.miss:          xor  a
                ret

;------------------------------------------------------------------------------
; deal_hit — apply one damaging hit (game.md §6.0 / §7 / §6.4 / §4.1).
; In : IX = attacker, A = target slot, B = damage rolled (>= 1; Power Strike's
;      x 2 already applied),
;      C = DTY_* | DH_NODEF | EFX_* << DH_EFX_SHIFT | DH_HEAL, E = effect parameter
;      (high nibble: chance "1 in N", 0 = always; low nibble: turns).
; Out: L = HP the target actually lost (0: immune, or already at 0 HP).
;      IX = attacker. ATK_PTR = attacker (set_reaction_at).
; Rules, in order:
;  1. target HP 0 (dying): nothing, L = 0.
;  2. response for the type (hero: HERO_RES; monster: kx_tab row): I or X
;     (a reflected type outside proj_fire counts as I) -> 0 damage, no side
;     effect, "YOU ARE UNAFFECTED" / "THE <kind> IS UNAFFECTED".
;  3. dmg = B; R: dmg / 2, min 1; W: dmg x 2 (sat. 255); PHYS without
;     DH_NODEF: dmg - DEF (hero HERO_DEF; monster KX_DEF = 0 in 3D), min 1;
;     a WEAK hero attacker's DEF counts + 1 there (D3-8f, game.md §6.4.2 R1:
;     max(1, roll x mult x resist - DEF - 1) on his physical hits only —
;     spells, Drain, his own bounced / reflected bolt carry DH_NODEF).
;  4. HP -= dmg, saturating at 0; L = the HP lost.
;  5. HP 0: EF_DYING + RC_DEATH; status slot cleared; a monster drops its
;     item (mon_drop, 3E-T11: gameplay RNG for a kind with a drop row) and awards the
;     hero KXP (EF_RESPAWN: KXP / 2, min 1) into XP (sat. XP_MAX), XP_UP = 1.
;     Else RC_HURT; ASLEEP wakes (any HP loss); FIRE thaws FROZEN; then the
;     effect (if any): chance roll (rng_mod N, 0 = success), then the
;     game.md §6.4.2 R2 order (D3-8f): (1) the immunity mask (a boss: +
;     SLEEP / FEAR) -> UNAFFECTED, stop; (2) R halves the turns; (3) a boss
;     (KX_IMM bit 7) halves HOLD / MIND again (0 after 2-3: silent); D3-8c: a
;     Frost Shard on its own caster freezes 1; (4) no HOLD on a held body,
;     FROZEN / STUNNED refused while HOLD_GUARD (set when either ends, a FIRE
;     thaw too) — both silent; same effect -> timer max(cur, new) (POISON:
;     cur + new, cap 15), another effect of the group -> overwritten; groups
;     independent.
;  6. DH_HEAL (Drain Life, the Vampire's bite; NOT the Ghost's touch, game.md
;     §9.1): the attacker heals the HP lost (to its max; the hero also gets
;     "YOU FEEL HEALTHIER").
; Messages go to the log at once (msg_push / impact_line), i.e. BEFORE the
; attacker's E_MSG impact line, which do_attack shows at the IMPACT tick.
; RNG: only the effect chance (after the damage roll, F3 order).
; Clobbers: all but IX (IY untouched).   ~0.7k T plain hit; + ~1.5k per message
;------------------------------------------------------------------------------
deal_hit:
                ld   (ATK_PTR), ix
                ld   (dh_slot), a
                ld   d, a
                ld   a, c
                ld   (dh_flags), a
                ld   a, e
                ld   (dh_eff), a
                ld   a, b
                ld   (dh_dmg), a
                ld   b, 0                      ; B = a WEAK hero's extra DEF (D3-8f, game.md
                ld   a, (ST_FLAGS)             ; §6.4.2 R1: -1 on the DEF path only; slot 0's
                and  STS_WEAK                  ; WEAK first: ~30 T when clear). B survives
                jr   z, .wk                    ; ent_ix to .rec (dh_dmg holds the roll)
                bit  EF_PLAYER_BIT, (ix+E_FLAGS)
                jr   z, .wk
                inc  b
.wk:            xor  a
                ld   (dh_lost), a
                ld   a, d
                call ent_ix                    ; IX = target (A, E)
                ld   (dh_tix), ix              ; D3-8e: pf_strike reads the target here
                ld   a, (ix+E_HP)
                or   a
                jp   z, .out                   ; already at 0 (dying): nothing
                ; --- the target's record: RES 3 B, IMM (+ DEF) ---
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   z, .mon
                ld   a, (HERO_DEF)
                ld   hl, HERO_RES
                jr   .rec
.mon:           ld   a, (ix+E_KIND)            ; row = kx_tab + kind * 6 (one page)
                ld   l, a
                add  a, a
                add  a, l
                add  a, a
                add  a, kx_tab & $FF
                ld   l, a
                ld   h, kx_tab >> 8
                add  a, KX_DEF                 ; (D3-8 review 2: the record's fields by
                ld   e, a                      ; L + offset, no push / add hl: one page)
                ld   d, h
                ld   a, (de)
.rec:           add  a, b                      ; DEF + 1 for a WEAK hero attacker: only the
                ld   (dh_def), a               ; PHYS-without-DH_NODEF path reads dh_def
                ld   a, l
                add  a, KX_IMM
                ld   e, a
                ld   d, h
                ld   a, (de)
                bit  IMMF_BOSS_BIT, a
                jr   z, .nb
                or   IMMF_SLEEP | IMMF_FEAR    ; D3-8: bosses never sleep or fear (§6.4)
.nb:            ld   (dh_imm), a
                ld   a, c                      ; (C = the flags since the entry)
                and  DH_TYPE
                ld   c, a                      ; C = type t
                ld   a, l                      ; weak: RES_B2 bit t (dh_bit: 1 << t)
                add  a, RES_B2
                ld   e, a
                ld   a, (de)
                ld   b, a
                ld   a, c
                add  a, dh_bit & $FF
                ld   e, a
                ld   d, dh_bit >> 8
                ld   a, (de)
                and  b
                ld   (dh_weak), a              ; 0 / not 0
                ASSERT HERO_IMM == HERO_RES + KX_IMM && (HERO_RES & $FF) + KX_IMM < 256 && KX_IMM > RES_B2
                ld   b, c
                call rsp_hl                    ; response (D3-6b: shared with proj_fire)
                ld   (dh_rsp), a
                cp   RSP_I
                jr   c, .dmg
                ; --- I / X: 0 damage, no side effect ---
                ld   b, TX_ST_UNAFFECTED
                ld   c, MSG_M_UNAFF
                call dh_msg
                jp   .out
.dmg:           ld   a, (dh_dmg)
                ld   b, a
                ld   a, (dh_rsp)
                or   a                         ; RSP_N
                jr   z, .nr
                srl  b                         ; RSP_R: / 2, min 1
                jr   nz, .nr
                inc  b
.nr:            ld   a, (dh_weak)
                or   a
                jr   z, .nw
                sla  b                         ; W: x 2
                jr   nc, .nw
                ld   b, $FF
.nw:            ld   a, (dh_flags)
                and  DH_TYPE | DH_NODEF
                jr   nz, .nd                   ; DEF: PHYS without DH_NODEF only
                ASSERT DTY_PHYS == 0
                ld   a, (dh_def)
                ld   e, a
                ld   a, b
                sub  e
                jr   z, .one
                jr   nc, .def
.one:           ld   a, 1                      ; max(1, dmg - DEF)
.def:           ld   b, a
.nd:            ld   a, b
                or   a
                jr   nz, .ap
                inc  b                         ; a 0 roll still hurts 1 (min 1)
.ap:            ld   a, (ix+E_HP)
                sub  b
                jr   nc, .sat
                ld   b, (ix+E_HP)              ; overkill: lost = the HP left
                xor  a
.sat:           ld   (ix+E_HP), a
                ld   a, b
                ld   (dh_lost), a
                ld   a, (ix+E_HP)
                or   a
                jr   z, .kill
                ld   c, RC_HURT
                call set_reaction_at
                call dh_status
                jr   .heal
                ; --- kill: death sequence + XP ---
.kill:          set  EF_DYING_BIT, (ix+E_FLAGS) ; out of collision at once (§3.2.4)
                ld   c, RC_DEATH
                call set_reaction_at
                call dh_stp                    ; its status dies with it
                xor  a
                ld   (hl), a
                ld   a, l
                add  a, (ST_T1 - ST_FLAGS) & $FF
                ld   l, a
                xor  a
                ld   (hl), a
                ld   a, l
                add  a, (ST_T2 - ST_T1) & $FF
                ld   l, a
                xor  a
                ld   (hl), a
                ASSERT ST_T1 > ST_FLAGS && ST_T2 > ST_T1 && (ST_FLAGS >> 8) == (ST_T2 >> 8)
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   nz, .heal                 ; the hero's death awards nothing
                ld   hl, mon_drop              ; 3E-T11: drop / boss unique (R6 pickup6.asm;
                call far6                      ; keeps IX; pages R6 over bank 3, back after)
                ld   a, (ix+E_KIND)            ; KXP = kx_tab[kind * 6 + KX_XP]
                ld   l, a
                add  a, a
                add  a, l
                add  a, a
                add  a, (kx_tab & $FF) + KX_XP
                ld   l, a
                ld   h, kx_tab >> 8
                ld   a, (hl)
                bit  EF_RESPAWN_BIT, (ix+E_FLAGS)
                jr   z, .xp
                srl  a                         ; respawned: KXP / 2 ...
                jr   nz, .xp
                adc  a, 0                      ; ... min 1 (KXP 1 -> 1; 0 stays 0)
.xp:            or   a
                jr   z, .heal                  ; 0 XP (Archmage, heroes)
                ld   e, a
                ld   d, 0
                ld   hl, (XP)
                add  hl, de
                ld   de, XP_MAX
                or   a
                sbc  hl, de
                add  hl, de
                jr   c, .xs
                ex   de, hl                    ; saturate at XP_MAX
.xs:            ld   (XP), hl
                ld   a, 1
                ld   (XP_UP), a
                ; --- DH_HEAL: the attacker heals the HP lost ---
.heal:          ld   ix, (ATK_PTR)
                ld   a, (dh_flags)
                and  DH_HEAL
                jr   z, .ox                    ; (IX = the attacker already: -20 T a hit)
                ld   a, (ix+E_HP)
                or   a
                jr   z, .out                   ; a dying attacker stays dead
                ld   a, (dh_lost)
                add  a, (ix+E_HP)
                jr   c, .cap
                cp   (ix+E_MAXHP)
                jr   c, .hs
.cap:           ld   a, (ix+E_MAXHP)
.hs:            ld   (ix+E_HP), a
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   z, .out
                ld   a, TX_SPL_DRAIN_HEAL
                call msg_push
.out:           ld   ix, (ATK_PTR)
.ox:            ld   a, (dh_lost)
                ld   l, a
                ret

;------------------------------------------------------------------------------
; dh_status — deal_hit step 5 for a surviving target (IX = target, dh_* set):
; wake / thaw, then the effect. Clobbers: all but IX.
;------------------------------------------------------------------------------
dh_status:
                call dh_stp                    ; HL = ST_FLAGS + slot
                ld   a, (hl)
                and  STS_HOLD
                cp   HOLD_ASLEEP
                jr   z, .wake                  ; any HP loss wakes
                cp   HOLD_FROZEN
                jr   nz, .eff
                ld   a, (dh_flags)
                and  DH_TYPE
                cp   DTY_FIRE
                jr   nz, .eff                  ; FIRE >= 1 thaws
                ld   bc, (TX_ST_THAW << 8) | MSG_M_THAW
                set  STS_GUARD_BIT, (hl)       ; HOLD_GUARD: no re-freeze before it acts
                jr   .clr
.wake:          ld   bc, (TX_ST_WAKE << 8) | MSG_M_WAKE
.clr:           ld   a, (hl)
                and  ~STS_HOLD & $FF
                ld   (hl), a
                ld   a, l
                add  a, (ST_T1 - ST_FLAGS) & $FF
                ld   l, a
                ld   a, (hl)
                and  $0F                       ; HOLD timer (high nibble) 0
                ld   (hl), a
                call dh_msg
.eff:           ld   a, (dh_flags)
                and  DH_EFX
                ret  z
                rrca
                rrca
                rrca
                rrca
                ld   (dh_efx), a               ; 1..7
                ld   a, (dh_eff)               ; chance: 1 in N (0 = always)
                rrca
                rrca
                rrca
                rrca
                and  $0F
                jr   z, .sure
                ld   c, a
                call rng_mod
                or   a
                ret  nz                        ; only a 0 roll applies it
.sure:          ld   a, (dh_efx)               ; row = efx_tab + (id - 1) * EF_STRIDE
                dec  a
                ld   l, a
                add  a, a
                add  a, l
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, efx_tab
                add  hl, de
                ld   a, (dh_imm)               ; D3-8f R2 (1): immunity first, so a boss's
                and  (hl)                      ; ASLEEP / FEAR prints even when the halving
                jr   z, .notimm                ; below would reach 0 (EFR_IMM)
                ld   b, TX_ST_UNAFFECTED
                ld   c, MSG_M_UNAFF
                jp   dh_msg
.notimm:        inc  hl
                ld   b, (hl)                   ; EFR_MASK
                inc  hl
                ld   c, (hl)                   ; EFR_VAL
                inc  hl
                ld   a, (hl)
                ld   (dh_tmr), a               ; EFR_TMR
                inc  hl
                ld   a, (hl)
                ld   (dh_htx), a               ; EFR_HTX
                inc  hl
                ld   a, (hl)
                ld   (dh_mmsg), a              ; EFR_MMSG
                ld   a, (dh_eff)               ; (B, C kept to .ng)
                and  $0F
                ld   d, a                      ; D = turns
                ld   a, (dh_rsp)               ; (2) R: duration / 2 (0 = none, silent)
                cp   RSP_R
                jr   nz, .full
                srl  d
.full:          ld   a, (dh_imm)               ; (3) a boss halves HOLD / MIND again
                rla                            ; (IMMF_BOSS_BIT 7 -> CF)
                ASSERT IMMF_BOSS_BIT == 7 && EFX_POISON == EFX_CONFUSED + 1
                jr   nc, .nbh
                ld   a, (dh_efx)
                cp   EFX_POISON
                jr   nc, .nbh                  ; POISON / WEAK: full
                srl  d
.nbh:           ld   a, d
                or   a
                ret  z                         ; halved to 0: silent (R2)
                ld   a, (dh_efx)
                cp   EFX_FROZEN
                jr   nz, .nsf
                ld   hl, (ATK_PTR)             ; D3-8c: a Frost Shard on its own caster
                ld   a, ixl                    ; (bounce / reflection) freezes 1 turn
                cp   l
                jr   nz, .nsf
                ld   a, ixh
                cp   h
                jr   nz, .nsf
                ld   d, 1
.nsf:           call dh_stp                    ; HL = ST_FLAGS + slot; (4) below: silent
                ld   a, (dh_efx)
                cp   EFX_FEAR
                jr   nc, .ng                   ; MIND / POISON / WEAK: no hold rules
                ld   a, (hl)
                and  STS_HOLD
                ret  nz                        ; D3-8c: no HOLD on a held body (a sleeper
                                               ; was woken by dh_status already)
                ld   a, (dh_efx)
                cp   EFX_ASLEEP
                jr   z,  .ng                   ; ASLEEP is not guarded
                bit  STS_GUARD_BIT, (hl)
                ret  nz                        ; HOLD_GUARD: no FROZEN / STUNNED yet
.ng:            ld   a, (hl)
                and  b
                sub  c
                ld   e, a                      ; E = 0: the same effect is on
                ld   a, b
                cpl
                and  (hl)
                or   c
                ld   (hl), a                   ; kind / bit set (group overwritten)
                ld   a, (dh_tmr)
                ld   b, a
                ld   a, l                      ; the timer byte: T1 or T2 (one page)
                add  a, (ST_T1 - ST_FLAGS) & $FF
                bit  EFT_T2_BIT, b
                jr   z, .t1
                add  a, (ST_T2 - ST_T1) & $FF
.t1:            ld   l, a
                ld   a, (hl)
                bit  EFT_LO_BIT, b
                jr   nz, .lo
                rrca
                rrca
                rrca
                rrca
.lo:            and  $0F                       ; A = this field's turns now
                inc  e
                dec  e
                jr   nz, .set                  ; another effect: overwrite
                ld   c, a
                ld   a, (dh_efx)
                cp   EFX_POISON
                ld   a, c
                jr   nz, .mx
                add  a, d                      ; D3-8c: POISON adds per hit, cap 15
                cp   16
                jr   c, .pc
                ld   a, 15
.pc:            ld   d, a
                jr   .set
.mx:            cp   d
                jr   c, .set
                ld   d, a                      ; same effect: max(cur, new)
.set:           ld   a, (hl)
                bit  EFT_LO_BIT, b
                jr   nz, .wlo
                and  $0F
                ld   c, a
                ld   a, d
                rlca
                rlca
                rlca
                rlca
                or   c
                jr   .w
.wlo:           and  $F0
                or   d
.w:             ld   (hl), a
                ld   a, (dh_efx)               ; D3-8d V3 (game.md §6.4.1): an ASLEEP that
                cp   EFX_ASLEEP                ; lands with no hit reaction pending (a
                jr   nz, .nfl                  ; typeless source: Sleep scroll / GAS, 3E)
                ld   a, (ix+E_REACT)           ; flashes $4F for one tick (the $41 tint
                                               ; follows; a flash in the tint's own colour
                                               ; would not show); a hit's
                or   a                         ; own impact is its cue (the flash would
                jr   nz, .nfl                  ; show before the impact, §6.5.1)
                ld   (ix+E_FLT), SLEEP_FLASH
                ld   (ix+E_FLA), SLEEP_FLASH_ATTR
.nfl:           ld   a, (dh_htx)
                ld   b, a
                ld   a, (dh_mmsg)
                ld   c, a
                ; fall through
;------------------------------------------------------------------------------
; dh_msg — IX = target: the hero gets line B (TX_*), a monster "THE " + its
; name + suffix C (MSG_M_*; 0 = no monster line). Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
dh_msg:
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   z, .m
                ld   a, b
                jp   msg_push
.m:             ld   a, c
                or   a
                ret  z
                ld   b, a
                ld   c, (ix+E_KIND)
                jp   impact_line

; dh_stp — HL = ST_FLAGS + dh_slot.  Clobbers: A, HL
dh_stp:
                ld   a, (dh_slot)
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ret

;------------------------------------------------------------------------------
; efx_tab — per effect id 1..7 (row = (id - 1) * EF_STRIDE): immunity bit
; (0 = none: FROZEN follows COLD, WEAK is hero-only), STATUS mask + value,
; timer field (EFT_*), the hero's line, the monster suffix (0 = none).
;------------------------------------------------------------------------------
EFR_IMM         EQU 0
EFR_MASK        EQU 1
EFR_VAL         EQU 2
EFR_TMR         EQU 3
EFR_HTX         EQU 4
EFR_MMSG        EQU 5
EF_STRIDE       EQU 6
EFT_LO_BIT      EQU 0               ; low nibble (MIND / WEAK), else high (HOLD / POISON)
EFT_T2_BIT      EQU 1               ; ST_T2 (POISON / WEAK), else ST_T1
EFT_T1HI        EQU 0
EFT_T1LO        EQU 1 << EFT_LO_BIT
EFT_T2HI        EQU 1 << EFT_T2_BIT
EFT_T2LO        EQU (1 << EFT_T2_BIT) | (1 << EFT_LO_BIT)
STS_POISON      EQU 1 << STS_POISON_BIT
STS_WEAK        EQU 1 << STS_WEAK_BIT
efx_tab:
                DB   0,            STS_HOLD,   HOLD_FROZEN,   EFT_T1HI, TX_ST_FROZEN,    MSG_M_FROZEN
                DB   IMMF_SLEEP,   STS_HOLD,   HOLD_ASLEEP,   EFT_T1HI, TX_ST_ASLEEP,    MSG_M_ASLEEP
                DB   IMMF_STUN,    STS_HOLD,   HOLD_STUNNED,  EFT_T1HI, TX_ST_STUNNED,   MSG_M_STUNNED
                DB   IMMF_FEAR,    STS_MIND,   MIND_FEAR,     EFT_T1LO, TX_ST_TERRIFIED, MSG_M_FLEES
                DB   IMMF_CONFUSE, STS_MIND,   MIND_CONFUSED, EFT_T1LO, TX_ST_CONFUSED,  MSG_M_CONFUSED
                DB   IMMF_POISON,  STS_POISON, STS_POISON,    EFT_T2HI, TX_ST_POISONED,  0
                DB   0,            STS_WEAK,   STS_WEAK,      EFT_T2LO, TX_ST_CURSE,     0
                ASSERT $ - efx_tab == EFX_WEAK * EF_STRIDE
                ASSERT EFR_IMM == 0 && EFR_MASK == 1 && EFR_VAL == 2 && EFR_TMR == 3 && EFR_HTX == 4 && EFR_MMSG == 5
                ASSERT EFX_FROZEN == 1 && EFX_ASLEEP == 2 && EFX_STUNNED == 3 && EFX_FEAR == 4
                ASSERT EFX_CONFUSED == 5 && EFX_POISON == 6 && EFX_WEAK == 7

; deal_hit scratch (bank-3 RAM next to the code; deal_hit is not re-entrant)
dh_slot:        DB   0
dh_flags:       DB   0
dh_eff:         DB   0
dh_dmg:         DB   0
dh_lost:        DB   0
dh_def:         DB   0
dh_imm:         DB   0
dh_weak:        DB   0
dh_bit:         DB   1, 2, 4, 8, 16, 32, 64, 128   ; deal_hit's weak test: 1 << t
                ASSERT (dh_bit >> 8) == ((dh_bit + 7) >> 8)
dh_rsp:         DB   0
dh_efx:         DB   0
dh_tmr:         DB   0
dh_htx:         DB   0
dh_mmsg:        DB   0
dh_tix:         DW   0                         ; D3-8e: the last target's entity (no ent_ix
                                               ; again in pf_strike)
dh_rtick:       DB   0                         ; D3-8e: set_reaction_at's tick when not 0
                                               ; (pf_strike's impact tick; 0 = the attacker's
                                               ; IMPACT: every other caller; back to 0 after)
