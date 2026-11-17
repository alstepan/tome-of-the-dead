;==============================================================================
; dscl.asm — BALANCE-PKG5 (balance_v2 §8 MON_DMG_SCALE_D): the depth ramp on a
; monster's melee damage (dsc_roll), + R6's tp_ok moved here for R6 room (C1).
; Low-RAM cold block (INCLUDEd by lowram.asm): dsc_roll is called from bank-3
; dmg_roll (turn3.asm) on every monster melee roll; low RAM is mapped whatever
; bank sits at $C000 (bank 3 has no room for it).
;==============================================================================

;------------------------------------------------------------------------------
; dsc_roll — C = die N, D = bonus B of a MONSTER attacker (dmg_roll's caller
; gate: not EF_PLAYER; bosses / golden bodies included, the sim's
; MON_SCALE_NO_BOSS 0): N := round(N x s), B := round(B x s), s = the depth's
; scale, round half up = the sim's int(x * s + 0.5) per die face and bonus (die
; >= 1 holds: N >= 2 in kind_tab, s >= 1). Ranged / spell shots never come here
; (proj3 rolls its own die), so they stay unscaled like the sim. The golden +1
; and the Ogre's SLAM x 1.5 come after (atk_mod), unscaled as in the sim.
; Fixed point: w = s x 64 per depth (dsc_tab), x' = (32 + x * w) >> 6; the w
; values are the ones exact against int(x * s + 0.5) for every x in 0..15
; (tests/dsc_model.py; KT_DIE <= 10, KT_BONUS <= 3 today). D0-D2 w = 64: x unchanged.
; Keeps IX.  Clobbers: A, B, E, HL, F (do_attack keeps its on-hit byte in B across dmg_roll).
; ~0.25-0.65k T a monster melee roll (2 shift-add loops, N + B steps).
;------------------------------------------------------------------------------
dsc_roll:       ld   a, (LVL_DEPTH)
                ld   hl, dsc_tab
                add  a, l
                ld   l, a                      ; (one page: ASSERT)
                ld   a, d                      ; the bonus first: D / E are w's below
                ld   e, (hl)
                ld   d, 0                      ; DE = w
                call .mul
                push af                        ; B'
                ld   a, c
                call .mul
                ld   c, a                      ; N'
                pop  af
                ld   d, a                      ; D = B'
                ret
; A = x, DE = w -> A = (32 + x * w) >> 6 (x <= 15: x * w + 32 <= 2912, << 2 fits 16 bits). Clobbers B, HL.
.mul:           ld   hl, 32                    ; the half of 1/64: round half up
                ld   b, a
                inc  b
                jr   .e
.l:             add  hl, de
.e:             djnz .l
                add  hl, hl
                add  hl, hl                    ; H = (32 + x * w) >> 6
                ld   a, h
                ret

; w = s x 64 by LVL_DEPTH 0..8 (0 = the PROTO test rooms; sim MON_DMG_SCALE_D D1..D8 1.0 1.0 1.9 1.7 2.6 2.8
; 3.0 3.0); exact for x 0..15
dsc_tab:        DB   64, 64, 64, 122, 109, 166, 179, 192, 192
                ASSERT (dsc_tab >> 8) == ((dsc_tab + LEVELS) >> 8)

;------------------------------------------------------------------------------
; tp_ok — tele_pick's / tp_room's spot test (R6 fx6.asm, called with bank 6
; paged; moved here verbatim by BALANCE-PKG5 for R6 room: C1).
; D = storey, E = col: Z = LP_CMAP clear under cols E .. E+2.
; Keeps BC, DE.  Clobbers: A, HL.   ~90 T (+ contention: low RAM)
;------------------------------------------------------------------------------
tp_ok:          ld   hl, LP_CMAP
                inc  d
                dec  d
                jr   z, .s
                ld   l, (LP_CMAP + LP_CMW) & $FF
.s:             ld   a, l
                add  a, e
                ld   l, a
                ld   a, (hl)
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                ret
                ASSERT TELE_W == 3 && (LP_CMAP >> 8) == ((LP_CMAP + 2 * LP_CMW - 1) >> 8)
