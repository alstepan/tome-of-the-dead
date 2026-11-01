;==============================================================================
; log0.asm — LOG-DMG (docs/design/log_damage.md, user 2026-11-01): the damage /
; HP tails of the composed log lines, in the bank-0 cold-code room (b0_code,
; main.asm; M1). Every routine here runs with BANK_TEXT paged at $C000, inside
; a helper that paged it and restores the caller's bank afterwards
; (impact_line, hit_line: lowram.asm / msg2.asm; msg_go: msg_push_d / _h / _t),
; and is CALLED DIRECTLY by it (no farb). Rules = bank3.asm's: no page_bank, no
; SMC, no RAM in the block (gfx_integrity compares it with the .sna); callees
; are low-RAM / bank-2 code only (impact_line.cat / .c, ent_ix, msg_dec,
; log_push, sfx_msg). Cold: once per log line.
;
; Tail grammar (§1): " -D" (HP lost) / " +G" (HP gained), then " HP H" for an
; enemy that survives; D / G = 0 -> no tail at all; values clamped to 99.
;   D sources: melee at IMPACT (show_impact_msg, IX = the attacker) = E_HIT & $7F
;   (do_attack's L; a ranged shot's $80 | L); melee_strike (IX = the target) =
;   LN_VAL (= deal_hit's dh_lost); hit_line = pf_lost (pf_tgt's own strike, not
;   the last one: a pierce / burst); msg_push_d = LN_VAL; msg_push_h = LN_G.
;==============================================================================

;------------------------------------------------------------------------------
; ln_imp — impact_line's end: B = message code, C = kind, DE = MSG_BUF past pre
; + name + post, IX = impact_line's caller's (show_impact_msg: the attacker;
; melee_strike: the target; others: unread). Adds the tail by the code, then 0
; + log_push (was impact_line's own end, low RAM -5 B):
;   MSG_P_HIT (Power Strike: recomposed "YOU SMASH N")  -D HP H
;   MSG_P_KILL                                           -D
;   MSG_M_HIT (the Vampire: recomposed "THE VAMPIRE DRAINS YOU")  -D
;   any other code (miss, squeeze, status, parry, summon): nothing.
; Clobbers: A, BC, DE, HL (IX kept).   ~0.15k T no tail, ~0.4-0.6k T a tail
;------------------------------------------------------------------------------
ln_imp:
                ld   a, b
                cp   MSG_M_HIT
                jr   z, .m
                cp   MSG_P_KILL + 1
                jr   nc, ln_end                ; 5..16: no tail
                cp   MSG_P_MISS
                jr   z, ln_end
                bit  EF_PLAYER_BIT, (ix+E_FLAGS)
                jr   nz, .h                    ; show_impact_msg: IX = the hero
                dec  a                         ; melee_strike (power_fire): IX = the target
                jr   nz, .k                    ; (P_KILL)
                ld   a, (ABIL_DESC + ABD_FLAGS)
                and  ABF_DMGX2
                ld   a, TX_CMB_POWER           ; Power Strike: "YOU SMASH N" (cut-order 1)
                call nz, ln_re
.k:             ld   h, (ix+E_HP)              ; H = its HP left (0: a kill, no HP part)
                ld   a, (LN_VAL)               ; D = deal_hit's (melee_hit just ran)
                jr   ln_tm
.h:             push ix
                push de
                ld   a, (ix+E_TGT)
                call ent_ix                    ; (A, E)
                pop  de
                ld   h, (ix+E_HP)              ; the logic HP (already reduced at do_attack)
                pop  ix
                jr   .v
.m:             ld   a, c                      ; 3F-T9: the Vampire's bite drains (heals it);
                cp   K_VAMPIRE                 ; its bat form K_VBAT bites plainly
                jr   nz, .m0
                ld   a, TX_THE
                call ln_re
                ld   a, TX_CMB_DRAINS
                call impact_line.cat           ; "THE VAMPIRE DRAINS YOU"
.m0:            ld   h, 0                      ; the hero's line: his HP is on the panel
.v:             ld   a, (ix+E_HIT)             ; IX = the attacker: D = its E_HIT
                and  $7F                       ; (bit 7: rg_shoot's no-flash flag)
                ; fall through
;------------------------------------------------------------------------------
; ln_tm — the tail " -A" (+ " HP H" if H != 0), 0, log_push MSG_BUF.
; ln_tl — the same with L = the sign char. A = 0: no tail at all (rule 3).
; In: A = the value, H = the HP left (0 = none), DE = the write pointer.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
ln_tm:          ld   l, '-'
ln_tl:          or   a
                jr   z, ln_end
                ld   c, a
                ld   a, ' '
                ld   (de), a
                inc  de
                ld   a, l
                ld   (de), a
                inc  de
                ld   a, c
                call ln_dec                    ; (A, BC; H kept)
                ld   a, h
                or   a
                jr   z, ln_end
                ld   hl, ln_hp
                ld   bc, 4
                ldir                           ; " HP " (A kept)
                call ln_dec
ln_end:         xor  a
                ld   (de), a
                ld   hl, MSG_BUF
                jp   log_push                  ; (bank 2; the ring is bank 5)
ln_hp:          DB   " HP "
;------------------------------------------------------------------------------
; ln_hit — hit_line's end (ammo_fire's spell / dagger / arrow / kill line):
; DE = MSG_BUF past pre + name. pf_tgt's " -D HP H" (D = pf_lost: its own
; strike, not a later pierce / burst one); a kill (HP 0) requests SFX_KILL (was
; impact_line's sfx_msg for ammo_fire's MSG_P_KILL line). 0 + log_push.
; Clobbers: A, BC, DE, HL (IX kept).   ~0.5-0.7k T
;------------------------------------------------------------------------------
ln_hit:         push ix
                push de
                ld   a, (pf_tgt)
                call ent_ix                    ; (A, E)
                ld   a, (ix+E_HP)
                pop  de
                pop  ix
                or   a
                jr   nz, .al
                push de
                ld   b, MSG_P_KILL
                call sfx_msg                   ; (AF, DE, HL; BC, IX kept)
                pop  de
                xor  a
.al:            ld   h, a
                ld   a, (pf_lost)
                jr   ln_tm

;------------------------------------------------------------------------------
; ln_push_d / ln_push_h / ln_push_t — msg_go's pushers (lowram.asm msg_push_d /
; _h / _t): HL = the stream of the string; copied to MSG_BUF + " -LN_VAL" /
; " +LN_G" / " -1 HP TOME_HP" (P3, the Tome: 1 hp a hit; the last hit is
; game_win's line, so TOME_HP >= 1 here), 0, log_push.
; Clobbers: A, BC, DE, HL.   ~0.25k T + 25 T a stream byte
;------------------------------------------------------------------------------
ln_push_h:      ld   a, (LN_G)
                ld   bc, '+'                   ; B = 0: no HP part, C = the sign
                jr   ln_push
ln_push_t:      ld   a, (TOME_HP)
                ld   b, a
                ld   a, 1
                jr   ln_pm
ln_push_d:      ld   a, (LN_VAL)
                ld   b, 0
ln_pm:          ld   c, '-'
ln_push:        ld   de, MSG_BUF
                push af
                call impact_line.c             ; the stream (A, DE, HL; BC kept)
                pop  af
                ld   h, b
                ld   l, c
                jr   ln_tl

; ln_dec — A = 1..255 -> its decimal at DE, >= 99 printed as 99 (rule 7).
ln_dec:         cp   99
                jp   c, msg_dec                ; (bank 2: A, BC)
                ld   a, 99
                jp   msg_dec

;------------------------------------------------------------------------------
; ln_re — recompose MSG_BUF as pre A + kind C's name (the SMASH / DRAINS lines).
; Out: DE past the name.  Clobbers: A, HL (BC kept).
;------------------------------------------------------------------------------
ln_re:          ld   de, MSG_BUF
                call impact_line.cat
                ld   a, c
                add  a, TX_NM_KNIGHT
                jp   impact_line.cat
