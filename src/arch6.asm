;==============================================================================
; arch6.asm — 3F-T11b the Necromancer Archmage's spell AI (game.md §9.9
; ARCHMAGE-SPEC A2-A6), R6 (r6.asm rules: far6 only, no SMC, no bank-3 code or
; data). Entry: arch_ai, far6 from bank-2 ai_mon (ranged2.asm), which
; resolve_monsters calls for every acting monster: the Archmage skips
; ai_monster (no yield, walker path, melee-first rule, ranged hook or boss
; guard: it never walks). State: combat_defs.asm "3F-T11b". Reference model:
; tools/ranged_model.py arch_decide (tests/archmage.py).
;==============================================================================

;------------------------------------------------------------------------------
; arch_ai — one Archmage turn (§9.9 A3; HOLD skipped it already: mon_status):
;  0. a fresh / re-entered body (ST_X bit 7 clear): P = H = 0, blinked =
;     hp <= max / 2;
;  1. H - 1, S - 1 (floor 0); C: old = C, C - 1 (rg_cnt);
;  2. old C = 0 and the hero in line (rg_line): ORDER[P] (s = P) if gap < r and
;     (not a HOLD row, or the hero neither held nor HOLD_GUARD), else Death Bolt;
;     P = (P + 1) mod 5; C = 1 (the row's N); the body ink = ORDER[P]'s;
;  3. else the first of: a. blink (hp <= max / 2, not blinked: the bit is spent
;     even when no box is legal, then b..e run); b. summon (S = 0: sp_summon,
;     a base Skeleton, < 2 live, S := 6); c. hex (H = 0, in line, gap < 12:
;     Sleep, or Venom on a held / guarded hero; H := 4, N 0 keeps C = 0, no hit
;     line); d. staff (attack_if_reach, far3) / e. wait, both facing the hero.
; In : IX = the Archmage (CUR_ROOM, active, acting), ACT_SLOT, PL_* current.
; Out: none.  Clobbers: all but IX.
; Cost (far6 incl.): the selection ~0.8-1.5k T (+ the line scan), a bolt
; ~+3k (rg_shoot + deal_hit + lines), the Mirror Helm return + ~2k, a blink
; ~3-6k (sp_try per col + build_live + the line), a summon try ~1.8k.
;------------------------------------------------------------------------------
arch_ai:
                call am_st                     ; HL = ST_X + slot
                bit  AMS_INIT_BIT, (hl)
                jr   nz, .in
                call am_half                   ; CF: hp > max / 2
                ld   a, 1 << AMS_INIT_BIT
                jr   c, .i1
                or   1 << AMS_BLINK_BIT        ; re-entered at <= half: no blink this life
.i1:            ld   (hl), a
.in:            ld   a, (hl)                   ; 1. H - 1 (floor 0)
                and  AMS_H
                jr   z, .h0
                ld   a, (hl)
                sub  AMS_H1
                ld   (hl), a
.h0:            ld   a, (ix+E_RCD)             ; S - 1 (floor 0): sp_summon's S > 0 path
                and  RCD_SUMMON                ; (S - 1, NC, A only; never a summon)
                call nz, sp_summon
                call rg_cnt                    ; RG_OLD = old C, C - 1
                call storey_ref                ; (bank 2) rg_line's TMP4
                ld   (TMP4), a
                ld   a, RK_ARCHMAGE            ; rg_line's range: Death Bolt's r 28 (any bolt
                call rg_row                    ; falls back to it) (keeps DE)
                ld   e, 0                      ; (it always stands: G1d post / blink box)
                call rg_line                   ; CF: out of line
                jr   c, .off
                ld   a, (RG_OLD)
                or   a
                jr   nz, .off
                ; --- 2. the bolt turn ---
                call am_st
                ld   a, (hl)
                and  AMS_P
                ld   d, a                      ; D = s = P
                inc  a
                cp   AM_ORDER_N
                jr   c, .p1
                xor  a
.p1:            ld   b, a                      ; B = the new P
                xor  (hl)
                and  AMS_P
                xor  (hl)
                ld   (hl), a
                push bc
                ld   e, 0                      ; the fallback: Death Bolt
                call am_pick
                call am_cast
                pop  af                        ; A = the new P: the body ink (A5)
                call am_ink
                ld   (kind_tab + KT_ATTR + K_ARCHMAGE), a   ; render re-stamps the footprint (DIRTY_ATTR)
                ret
                ; --- 3. the off-turn ---
.off:           call am_st                     ; a. blink, once a life
                bit  AMS_BLINK_BIT, (hl)
                jr   nz, .sum
                call am_half
                jr   c, .sum                   ; hp > max / 2
                set  AMS_BLINK_BIT, (hl)
                call am_blink
                ret  c
.sum:           ld   a, (ix+E_RCD)             ; b. summon (S = 0)
                and  RCD_SUMMON
                jr   nz, .hex
                ld   d, K_SKELETON | SQF_SUMM | SQF_RESP
                ld   e, AM_LIVE
                ld   bc, (1 << 8) | (AM_SUM_CD << 2)
                call sp_summon                 ; (spawn6.asm) CF = queued: the cast pose + line
                ret  c
.hex:           ld   a, RK_ARCHMAGE + AM_SLEEP ; c. hex: in line (again: the blink / summon
                call rg_row                    ; tries keep the box), gap < 12 (the Sleep
                ld   e, 0                      ; row's r), H = 0
                call rg_line
                jr   c, .stf
                call am_st
                ld   a, (hl)
                and  AMS_H
                jr   nz, .stf
                ld   a, (hl)
                or   AM_HEX_CD << 3
                ld   (hl), a
                ld   de, (AM_SLEEP << 8) | AM_VENOM
                call am_pick
                call am_cast
                ld   (ix+E_MSG), 0             ; a hex prints no hit line (A2)
                ret
.stf:           ld   a, (PL_X)                 ; d. / e. face the hero; the staff in reach
                cp   (ix+E_X)
                sbc  a, a                      ; $FF: the hero is left
                or   1
                call face_a                    ; (bank 2)
                ld   hl, attack_if_reach       ; (bank 3: hit_roll, 1d6 PHYS, the cast pose)
                jp   far3
                ASSERT AMS_H1 == 1 << 3 && AM_HEX_CD < 8 && AM_SUM_CD < 16 && AM_ORDER_N <= AMS_P + 1

; am_st — HL = ST_X + ACT_SLOT (the Archmage's state byte).  Clobbers: A
am_st:          ld   a, (ACT_SLOT)
                add  a, ST_X & $FF
                ld   l, a
                ld   h, ST_X >> 8
                ret

; am_half — CF = hp > max hp / 2 (round down).  Clobbers: A
am_half:        ld   a, (ix+E_MAXHP)
                srl  a
                cp   (ix+E_HP)
                ret

; am_ink — A = spell index -> A = its FX ink (the A2 table).  Clobbers: DE
am_ink:         add  a, am_ink_tab & $FF
                ld   e, a
                ld   d, am_ink_tab >> 8
                ld   a, (de)
                ret
am_ink_tab:     DB   $43, $45, $47, $44, $42, $41, $06   ; Death Bolt, Frost, Lightning, Drain, Firebolt, Sleep, Venom
                ASSERT (am_ink_tab >> 8) == ((am_ink_tab + AM_VENOM) >> 8) && AM_INK0 == $43

;------------------------------------------------------------------------------
; am_pick — D = spell index, E = the fallback -> A = D, or E when gap >= its r
; or it is a HOLD row and the hero is held / under HOLD_GUARD (A4 hold lock).
; Clobbers: A, BC, D, HL.
;------------------------------------------------------------------------------
am_pick:        ld   a, d
                add  a, RK_ARCHMAGE
                call rg_rp                     ; HL = the row
                ld   a, (RG_GAP)
                cp   (hl)                      ; RW_R
                jr   nc, .fb
                inc  hl
                inc  hl                        ; RW_F
                bit  RWF_HOLD_BIT, (hl)
                jr   z, .ok
                ld   a, (ST_FLAGS)             ; the hero (slot 0)
                and  STS_HOLD | STS_GUARD
                jr   z, .ok
.fb:            ld   d, e
.ok:            ld   a, d
                ret
                ASSERT RW_R == 0 && RW_F == 2

;------------------------------------------------------------------------------
; am_cast — A = spell index: rg_shoot with its row (RG_DIR / FIRST / GAP from
; rg_line), the queued FX re-inked (FXD_ATTR = the A2 ink); Death Bolt on a
; DARK X hero (Mirror Helm: deal_hit gave him 0, UNAFFECTED) -> A6: the same
; roll strikes the Archmage (rs_self: DARK, its R halves it, min 1), and a 2nd
; FX track flies back: rg_q with RG_DIR reversed (the anchor = the cell next
; to the hero), no hero flash, TURN_TICK + gap + 1 for its release (R' = I) —
; restored after; the Archmage's reaction at I2 = I + gap + 1 (rg_ri on R').
; Clobbers: all but IX.
;------------------------------------------------------------------------------
am_cast:        ld   (AM_ROW), a
                add  a, RK_ARCHMAGE
                call rg_row
                call rg_shoot                  ; DE = past the entry (the sink too)
                ld   a, (AM_ROW)
                or   a
                jr   nz, .ink
                ld   a, (HERO_RES + RES_B1)    ; Death Bolt vs DARK X (rsp_hl: type 5, bits 2-3)
                and  3 << 2
                cp   RSP_X << 2
                jr   nz, .ink
                push de
                call .ink
                ld   a, (ACT_SLOT)
                ld   e, a
                ld   a, (AM_DMG)
                ld   d, a
                ld   hl, rs_self               ; (bank 3) L = HP it lost
                call far3
                ld   c, l
                ld   hl, TURN_TICK
                ld   b, (hl)
                push bc                        ; B = TURN_TICK, C = lost
                ld   a, (RG_GAP)
                inc  a
                add  a, b
                ld   (hl), a                   ; R' = I
                call rg_ri                     ; B = I2
                pop  hl
                push hl
                inc  l
                dec  l
                jr   z, .nr
                ld   (ix+E_REACTAT), b         ; its HURT / DEATH when the bolt is back
.nr:            ld   hl, RG_DIR
                ld   a, (hl)
                neg
                ld   (hl), a
                ld   hl, RG_F
                res  RGF_FLASH_BIT, (hl)
                call rg_q                      ; (ranged6.asm) DE = past the entry
                pop  af
                ld   (TURN_TICK), a
                pop  af                        ; (the bolt's DE: re-inked already)
.ink:           ld   hl, FXD_ATTR - FXD_LEN
                add  hl, de
                ld   a, (AM_ROW)
                call am_ink
                ld   (hl), a                   ; FXD_ATTR: the spell's ink
                ret
                ASSERT DTY_DARK == 5 && RES_B1 == 1

;------------------------------------------------------------------------------
; am_hex — rg_shoot's RWF_HEX branch (the row in RG_ROW): the rider on the hero
; through the immunity mask only (A2: typeless, no resistance, no chance):
; immune -> "YOU ARE UNAFFECTED"; Sleep: HOLD := ASLEEP, the HOLD timer (ST_T1
; high nibble) := 3 (arch_ai only picks it on an unheld, unguarded hero);
; Venom: POISON on, ST_X += 12 (fresh: = 12), cap PSN_CAP; then the row's line.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
am_hex:         ld   a, (HERO_IMM)
                ld   hl, RG_ROW + RW_DIE       ; the immunity bit
                and  (hl)
                ld   a, TX_ST_UNAFFECTED
                jr   nz, .ln
                ld   a, (RG_ROW + RW_DHE)
                ld   c, a                      ; C = the turns
                ld   hl, ST_FLAGS
                ld   a, (RG_ROW + RW_DHC)
                cp   EFX_POISON << DH_EFX_SHIFT
                jr   z, .ps
                ld   a, (hl)                   ; Sleep
                and  ~STS_HOLD & $FF
                or   HOLD_ASLEEP
                ld   (hl), a
                ld   hl, ST_T1
                ld   a, (hl)
                and  $0F                       ; (the MIND timer kept)
                or   c
                ld   (hl), a
                jr   .tx
.ps:            bit  STS_POISON_BIT, (hl)      ; Venom (SET keeps the flags)
                set  STS_POISON_BIT, (hl)
                ld   hl, ST_X
                ld   a, c
                jr   z, .pw                    ; fresh: the new turns
                add  a, (hl)
                cp   PSN_CAP + 1
                jr   c, .pw
                ld   a, PSN_CAP
.pw:            ld   (hl), a
.tx:            ld   a, (RG_ROW + RW_BON)      ; the hero's line
.ln:            jp   msg_push
                ASSERT HOLD_ASLEEP == EFX_ASLEEP

;------------------------------------------------------------------------------
; am_blink — A3a: to P' = the same x on the other storey; illegal (sp_try: a
; wall, pit, body, ladder box) -> 1 .. 8 cols toward the room centre; the first
; legal box: snapped, the $47 teleport flash, build_live, S = 0, "THE ARCHMAGE
; VANISHES!", CF = 1 (the turn used). None: back to its post, CF = 0.
; In : TMP4 = its storey.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
am_blink:       ld   l, (ix+E_X)
                ld   h, (ix+E_Y)
                push hl                        ; the post
                ld   a, (TMP4)
                xor  1
                call sp_y                      ; (spawn6.asm) E_Y = the other storey's stand row
                ld   a, (ix+E_X)
                cp   ROOM_COLS / 2 - 1
                ccf
                sbc  a, a
                or   1
                ld   d, a                      ; D = +1 (left half) / -1: toward the centre
                ld   b, AM_BLINK_N + 1
                ld   a, (ix+E_X)
.t:             push bc
                push de
                call sp_try                    ; E_X := A; CF = illegal
                pop  de
                pop  bc
                jr   nc, .ok
                ld   a, (ix+E_X)
                add  a, d
                djnz .t
                pop  hl                        ; no legal box: it stays
                ld   (ix+E_X), l
                ld   (ix+E_Y), h
                or   a
                ret
.ok:            pop  hl
                call snap_pxpy                 ; (bank 2)
                ld   (ix+E_FLT), TELE_FLASH_T
                ld   (ix+E_FLA), AM_BLINK_ATTR
                ld   a, (ix+E_RCD)
                and  ~RCD_SUMMON & $FF         ; S = 0
                ld   (ix+E_RCD), a
                call build_live                ; (bank 2) LIVE_LIST: the new box
                ld   a, TX_AM_VANISH
                call msg_push
                scf
                ret
                ASSERT E_FLA == E_FLT + 1 && ROOM_COLS == 32
