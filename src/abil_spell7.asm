;==============================================================================
; abil_spell7.asm — D3-7 T4, bank 7 (bank7.asm rules: no data, no SMC): the 5
; Mage spells (game.md §6.1) as a split ability turn (act7.asm): the accept on
; the input tick, the release (proj_fire) on the fire tick.
;==============================================================================

SPELL_FLASH     EQU 5                          ; the cast's ticks (wz_cast: CAST1 2 + CAST2 3):
                                               ; the hero flashes the spell ink throughout

;------------------------------------------------------------------------------
; abil_spell — intent7 ic_disp (ABF_SPELL), IX = hero, B = ABL_SPARK ..
; ABL_LIGHTNING (= the Mage's ability index k), ABIL_DESC loaded (abil_load).
; Refused (L = 0, no turn, a message): unlearned -> NOT LEARNED; MP < the
; RANK_ROWS row's RR_MP -> NO MANA; mid-ladder (game.md §2.3) -> NO TARGET;
; act_begin's lead col 0 / 31 -> L = 0, no message.
; Accepted (input tick): act_begin (TURN_PEND, ACT_ABL = B, ACT_AT, MON_AT),
; MP -= cost, PD_MP, the abl_seq sequence (wz_cast), the hero flashes the
; spell ink (ABD_AT1) for SPELL_FLASH ticks. L = 1.
; Clobbers: A, C, DE, HL (B, IX kept; a refusal: msg_push's AF, BC, DE, HL)
;------------------------------------------------------------------------------
abil_spell:
                ld   a, b
                call abil_rank                 ; bank 2: Z = unlearned (A, C, HL)
                ld   a, TX_NOT_LEARNED
                jp   z, ic_refuse
                call spell_row                 ; HL = the rank row (RR_MP first)
                ld   a, (MP)
                cp   (hl)
                ld   a, TX_NO_MANA
                jp   c, ic_refuse
                call on_ladder                 ; Z = mid-ladder (A, HL)
                ld   a, TX_NO_TARGET
                jp   z, ic_refuse
                call act_begin                 ; L = 0: lead col 0 / 31 (A, HL; B kept)
                dec  l
                inc  l
                ret  z                         ; no turn, no message
                call spell_row
                ld   a, (MP)
                sub  (hl)                      ; (MP >= cost: checked above)
                ld   (MP), a
                ld   hl, PANEL_DIRTY
                set  PD_MP_BIT, (hl)
                call act_seq                   ; the abl_seq sequence (A, DE, HL)
                ld   a, (ABIL_DESC + ABD_AT1)
                ld   (ix+E_FLA), a
                ld   (ix+E_FLT), SPELL_FLASH
                ld   l, 1
                ret
                ASSERT RR_MP == 0 && ABL_SPARK == 0

; spell_row — B = ABL_SPARK..ABL_LIGHTNING -> HL = RANK_ROWS + B * RR_STRIDE
; (the hero's current-rank row, rank_sync).  Clobbers: A, HL
spell_row:
                ld   a, b
                add  a, a
                add  a, b
                add  a, a                      ; 6 * B (<= 24)
                add  a, RANK_ROWS & $FF        ; RANK_ROWS never crosses a page
                ld   l, a
                ld   h, RANK_ROWS >> 8
                ret
                ASSERT RR_STRIDE == 6 && (RANK_ROWS >> 8) == ((RANK_ROWS + RANK_N * RR_STRIDE - 1) >> 8)

;------------------------------------------------------------------------------
; spell_fire — the spell's release (act_fire, fire tick f): proj_fire (bank 3,
; via proj_rel: A = B, HL = its RANK_ROWS row, E = FXD_DELAY 0: the projectile
; appears now; fx_start's drop counts in FX_DROP). Drain Life: when it took
; HP from a body other than the caster (pf_lost > 0; a self-hit heals nothing,
; game.md §6 "Logic"), the hero flashes ATTR_HEAL from the release until
; FLASH_TICKS after the impact.
; In: IX = hero, B = ABL_SPARK..ABL_LIGHTNING (= ACT_ABL). Out: L = 1 fired.
; Clobbers: all but IY.   ~0.4k T + proj_fire (10-66k T, contended)
;------------------------------------------------------------------------------
spell_fire:
                call spell_row
                ex   de, hl                    ; far3 takes HL as its target: the row in DE
                ld   a, b
                ld   hl, proj_rel
                call far3                      ; L = pf_stop; IX = hero
                ld   a, (ACT_ABL)
                cp   ABL_DRAIN
                jr   nz, .out
                ld   a, (pf_tgt)
                or   a
                jr   z, .out                   ; the caster (slot 0) / none ($FF: pf_lost 0)
                ld   a, (pf_lost)
                or   a
                jr   z, .out
                ld   (ix+E_FLA), ATTR_HEAL
                ld   a, (TURN_TICK)
                ld   b, a
                ld   a, (pf_itick)
                sub  b
                add  a, FLASH_TICKS
                ld   (ix+E_FLT), a
.out:           ld   l, 1
                ret
