;==============================================================================
; abil_ammo7.asm — D3-7 T6, bank 7 (bank7.asm rules: no data, no SMC): the
; Warrior's dagger throw and bow shot (game.md §6.3) as a split ability turn
; (act7.asm: the accept on the input tick, the release on the fire tick f = 2:
; kn_throw WIND-UP 2 -> THROW 3, kn_bow BOW 4). The flight is proj_fire's
; (bank 3, via proj_rel): the ab_ammo row, to-hit ABD_HIT (dagger +1), PHYS,
; a miss flies on. 3D: the spent dagger / arrow is consumed (game.md §11.4:
; the floor drop + 1-in-4 loss of §6.3 is 3E, with the floor-item records).
; Also the composed log lines (msg_cat / msg_kind / msg_end, shared with
; pickup7.asm).
;==============================================================================

PD_AMMO_BIT     EQU 3
                ASSERT PD_AMMO == 1 << PD_AMMO_BIT
                ASSERT ARROWS == DAGGERS + 1 && (ARROWS >> 8) == (DAGGERS >> 8)

;------------------------------------------------------------------------------
; abil_ammo — intent7 ic_disp (ABF_AMMO; ic_daggers / ic_bow already refused
; DAGGERS = 0 -> NO DAGGERS, no bow -> NO BOW, ARROWS = 0 -> NO ARROWS), IX =
; hero, B = ABL_DAGGER / ABL_BOW, ABIL_DESC loaded (abil_load: ABIL_RK = the
; ab_ammo row).
; Refused (L = IC_REFUSED with its line, 0 silent; no turn, nothing spent): mid-ladder (game.md §2.3) -> NO
; TARGET (as the spells); act_begin's lead col 0 / 31 -> L = 0, no message.
; Accepted (input tick): act_begin (TURN_PEND, ACT_ABL = B, ACT_AT, MON_AT),
; DAGGERS / ARROWS -= 1, PD_AMMO, the abl_seq sequence (kn_throw / kn_bow).
; L = 1.  Clobbers: A, C, DE, HL (B, IX kept; a refusal: msg_push's AF, BC,
; DE, HL).   ~1k T
;------------------------------------------------------------------------------
abil_ammo:
                call on_ladder                 ; Z = mid-ladder (A, HL)
                ld   a, TX_NO_TARGET
                jp   z, ic_refuse
                call act_begin                 ; L = 0: lead col 0 / 31 (A, HL; B kept)
                dec  l
                inc  l
                ret  z                         ; no turn, no message
                ld   hl, DAGGERS
                ld   a, b
                sub  ABL_DAGGER                ; 0 dagger / 1 bow
                add  a, l
                ld   l, a                      ; -> DAGGERS / ARROWS (same page)
                dec  (hl)                      ; (> 0: ic_daggers / ic_bow checked it)
                ld   hl, PANEL_DIRTY
                set  PD_AMMO_BIT, (hl)         ; (no ammo item drawn yet: the panel clears it;
                                               ; the icons grey through icon_poll's ICON_SIG)
                call act_seq                   ; (A, DE, HL)
                ld   l, 1
                ret
                ASSERT ABL_BOW == ABL_DAGGER + 1

;------------------------------------------------------------------------------
; ammo_fire — the release (act_fire, fire tick f = 2): proj_fire via far3
; proj_rel (A = B, DE = ABIL_RK, the ab_ammo row abil_load copied; E = 0: the
; projectile appears now; fx_start's drop counts in FX_DROP). Then the lines
; (T7: a miss used to be one generic line, easy to lose in a busy log — the
; user's "flies through the Goblin" report was a designed missed roll):
;   pf_miss a monster (the first body that won its roll; the missile flew on,
;   proj_fire made it dodge) and not the body hit -> "YOUR DAGGER / ARROW
;   MISSES THE <kind>";
;   pf_tgt a monster -> "YOUR DAGGER / ARROW HITS THE <kind>", killed -> "YOU
;   KILL THE <kind>"; none ($FF) and no named miss -> "YOUR DAGGER / ARROW
;   MISSES" (absorbed / range / wall / exit); the hero (slot 0, after a
;   reflection) -> deal_hit's own hero line only.
; In: IX = hero, B = ABL_DAGGER / ABL_BOW (= ACT_ABL), C = 1 the Tome was struck (P3, act_fire),
; else 0. Out: L = 1 fired.
; Clobbers: all but IY (IX kept).   ~2-6k T + proj_fire (10-30k T, contended)
;------------------------------------------------------------------------------
ammo_fire:
                push bc
                ld   de, ABIL_RK               ; far3 takes HL as its target: the row in DE
                ld   a, b
                ld   hl, proj_rel
                call far3                      ; L = pf_stop; IX = hero
                pop  bc                        ; C = 1: a named miss line went out (P3: act_fire's
                                               ; C = 1 when the release struck the Tome: no MISSES)
                ld   a, (pf_miss)
                or   a
                jr   z, .t                     ; the hero (a reflection): no line
                inc  a
                jr   z, .t                     ; $FF: nothing missed
                dec  a
                ld   hl, pf_tgt
                cp   (hl)
                jr   z, .t                     ; missed, then hit on a later pass
                push bc
                call ent_kind                  ; C = its kind
                ld   a, b
                call miss_pre                  ; DE = MSG_BUF + "YOUR ARROW MISSES"
                ld   a, ' '
                ld   (de), a
                inc  de
                ld   a, TX_THE
                push bc
                call msg_cat                   ; + "THE "
                pop  bc
                call msg_kind
                call msg_end
                pop  bc
                ld   c, 1                      ; (P3: not inc c — act_fire's C = 1 (the Tome struck) would
                                               ; make it 2 and .none would print a 2nd MISSES line)
.t:             ld   a, (pf_tgt)
                or   a
                jr   z, .out                   ; the hero: deal_hit logged it
                inc  a
                jr   z, .none                  ; $FF: nothing struck
                dec  a
                call log_room                  ; LOG-FIX Fix A: the result line below replaces the
                push bc                        ; newest pending one rather than being dropped
                call ent_kind                  ; C = kind, A = HP
                pop  de
                ld   b, d                      ; B = ABL_*
                or   a
                jr   nz, .hit
                ld   b, TX_YOU_KILL            ; LOG-DMG: through hit_line (pf_lost, not dh_lost:
                call hit_line                  ; "YOU KILL <kind> -D"; ln_hit requests SFX_KILL)
                jr   .out
.hit:           ld   a, (pf_lost)              ; 3F-T6: $FF = the hit was parried (deal_hit H = 1)
                inc  a
                jr   nz, .nph
                ld   b, MSG_P_PARRY
                call impact_line               ; "THE <kind> PARRIES!" (C = kind)
                jr   .out
.nph:           ld   a, b                      ; LOG-FIX: spells share the tail: the hit line =
                add  a, TX_SPL_SPARK           ; TX_SPL_SPARK + ABL (ASSERTed below), as a token
                ld   b, a                      ; stream (msg2.asm hit_line, ~1.4k T)
                call hit_line                  ; "DAGGER HITS <kind> -D HP H" / "FIRE BURNS ..." (LOG-DMG)
                jr   .out
.none:          dec  c
                jr   z, .out                   ; the named miss line said it
                ld   a, b
                cp   ABL_DAGGER
                jr   c, .out                   ; a spell: act_begin logged "YOU CAST <SPELL>" already
                call miss_pre
                call msg_end                   ; "YOUR DAGGER / ARROW MISSES"
.out:           ld   l, 1
                ret

; ent_kind — slot A -> C = its E_KIND, A = its E_HP.  Clobbers: A, C, E (IX kept)
ent_kind:
                push ix
                call ent_ix                    ; (A, E)
                ld   c, (ix+E_KIND)
                ld   a, (ix+E_HP)
                pop  ix
                ret

                ASSERT TX_SPL_FIRE == TX_SPL_SPARK + ABL_FIREBOLT && TX_SPL_FROST == TX_SPL_SPARK + ABL_FROST
                ASSERT TX_SPL_DRAIN == TX_SPL_SPARK + ABL_DRAIN && TX_SPL_LIGHT == TX_SPL_SPARK + ABL_LIGHTNING
                ASSERT TX_CMB_POWER == TX_SPL_SPARK + ABL_POWER && TX_CMB_WHIRL == TX_SPL_SPARK + ABL_WHIRL
                ASSERT TX_CMB_DAG_HIT == TX_SPL_SPARK + ABL_DAGGER && TX_CMB_ARR_HIT == TX_SPL_SPARK + ABL_BOW
                ; the cast lines (act_begin): TX_SPL_C_SPARK + ABL_*; POWER / WHIRL slots are fillers
                ASSERT TX_SPL_C_FIRE == TX_SPL_C_SPARK + ABL_FIREBOLT && TX_SPL_C_FROST == TX_SPL_C_SPARK + ABL_FROST
                ASSERT TX_SPL_C_DRAIN == TX_SPL_C_SPARK + ABL_DRAIN && TX_SPL_C_LIGHT == TX_SPL_C_SPARK + ABL_LIGHTNING
                ASSERT TX_CMB_THROW == TX_SPL_C_SPARK + ABL_DAGGER && TX_CMB_SHOOT == TX_SPL_C_SPARK + ABL_BOW
                ASSERT TX_SPL_C_SPARK == TX_CMB_ARR_HIT + 1

; miss_pre — A = ABL_DAGGER / ABL_BOW -> MSG_BUF = "YOUR DAGGER / ARROW
; MISSES", DE = its end.  Clobbers: A, DE, HL (BC kept)
miss_pre:
                cp   ABL_DAGGER
                ld   a, TX_CMB_DAG_MISS
                jr   z, .m
                ld   a, TX_CMB_ARR_MISS
.m:             ld   de, MSG_BUF
                push bc
                call msg_cat
                pop  bc
                ret

; Composed log lines in MSG_BUF: msg_cat / msg_kind / msg_dec / msg_end live in bank 2
; (src/msg2.asm, LOG-FIX: always mapped, 45 B off bank 7), shared with pickup7 / xp7.
                ; LOG-DMG (log_damage.md §3): + the worst tail " -99 HP 99" (10 chars) <= 31
                ASSERT TXL_CMB_ARR_HIT + NM_LONG + 10 <= 31 && TXL_CMB_DAG_HIT + NM_LONG + 10 <= 31
                ASSERT TXL_SPL_SPARK + NM_LONG + 10 <= 31 && TXL_SPL_FIRE + NM_LONG + 10 <= 31 && TXL_SPL_FROST + NM_LONG + 10 <= 31
                ASSERT TXL_SPL_DRAIN + NM_LONG + 10 <= 31 && TXL_SPL_LIGHT + NM_LONG + 10 <= 31
                ASSERT TXL_YOU_KILL + NM_LONG + 4 <= 31   ; the kill line through hit_line
                ; msg_push_d / _h / _t lines (+ " -99" / " +99" / " -1 HP 5")
                ASSERT TXL_SPL_HIT_SELF + 4 <= 31 && TXL_SPL_BURN_SELF + 4 <= 31 && TXL_FALL + 4 <= 31
                ASSERT TXL_SPL_DRAIN_HEAL + 4 <= 31 && TXL_TOME_HIT + 8 <= 31 && TOME_MAX <= 9
                ASSERT TXL_SPL_C_FROST <= LOG_MAX && TXL_SPL_C_DRAIN <= LOG_MAX && TXL_SPL_C_FIRE <= LOG_MAX
                ASSERT TXL_SPL_C_LIGHT <= LOG_MAX && TXL_SPL_C_SPARK <= LOG_MAX && TXL_CMB_SHOOT <= LOG_MAX
                ASSERT TXL_CMB_DAG_MISS + 1 + TXL_THE + NM_LONG <= LOG_MAX && TXL_CMB_ARR_MISS <= TXL_CMB_DAG_MISS
