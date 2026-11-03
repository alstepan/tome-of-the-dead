;==============================================================================
; drop3.asm — FLOOR1 (moved back from R6 pickup6.asm for the R6 glyph cache):
; mon_drop (deal_hit's kill path calls it directly) and its tables; the
; placement itself is R6 drop_put (far6). game.md §8.11 Q11 + pickup/drop rulings 2.
;==============================================================================
DROP_NEAR       EQU 3
DROP_WHOLE      EQU ROOM_COLS - 1
DROP_ARROWS     EQU 3
;------------------------------------------------------------------------------
; mon_drop — from deal_hit's kill path (FLOOR1: bank 3 again, drop3.asm; was
; R6 pickup6.asm; 3F-T5: the drop_tab scan is R6 drop_row), IX = the dead monster (EF_DYING
; set, still in place). game.md §8.11 Q11 + pickup/drop rulings 2:
;  - EF_RESPAWN: nothing.
;  - the lair boss: the first kill of kind LP_BOSS in LVL_LAIR on this level
;    (LF_UNIQUE; STAND-IN until 3F gives bosses their own kind / IMMF_BOSS:
;    an escort of the boss's kind killed first takes the drop) -> the depth's
;    unique (uniq_tab; D4 Mage: Bone Staff; D8 none), placed anywhere on the
;    storey, "BOSS DROPS " + name; a room at 8 item types first loses an
;    ordinary item (uq_fit).
;  - else the first drop_tab row of its kind: 1 in N on the gameplay RNG
;    (rng_mod; rolled only for a kind with a row); arrows (qty 3) only in a
;    Warrior run (no roll for the Mage). No line (the glyph appears).
; Clobbers: all but IX.   no row ~0.2k T; a drop ~12k T (placement + ap_stamp)
;------------------------------------------------------------------------------
mon_drop:
                bit  EF_RESPAWN_BIT, (ix+E_FLAGS)
                ret  nz
                ld   a, (LVL_LAIR)
                cp   (ix+E_ROOM)
                jr   nz, .row
                ld   a, (LP_BOSS)
                ld   b, a
                and  LEK_KIND_MASK             ; 3F-T5: the golden bit is not part of the kind
                cp   (ix+E_KIND)
                jr   nz, .row
                ld   a, b                      ; golden depth: only the golden body is the boss (a same-kind
                and  LEK_GOLD                  ; escort / follower is not)
                cp   (ix+E_GOLD)
                jr   nz, .row
                ld   hl, LVL_FLAGS
                bit  LF_UNIQUE_BIT, (hl)
                jr   nz, .row                  ; (the boss's kind as an ordinary monster)
                set  LF_UNIQUE_BIT, (hl)
                ld   hl, grate_open            ; 3F-T8 (bank-7 boss7.asm, w2b): the gate opens (before the
                call far7                      ; unique is placed: never on the open gate)
                ld   a, (LVL_DEPTH)
                dec  a
                cp   UNIQ_DEPTHS
                ret  nc                        ; D8: none
                cp   3
                jr   nz, .u
                ld   a, (HERO_KIND)
                add  a, a
                add  a, a                      ; Mage: 4 -> +3 below = 7
                add  a, 3
.u:             ld   hl, uniq_tab              ; uniq_tab[A]
                call idx
                push af                        ; [type]
                ld   hl, uq_fit                ; R6 (fi6.asm): the room at 8 types: displace an
                call far6                      ; ordinary item (far6 loses A)
                pop  af
                push af
                ld   de, (1 << 8) | DROP_WHOLE
                ld   hl, drop_put              ; R6: L = 0 lost (never: entry 32 is kept free, uq_fit made room)
                call far6
                pop  bc                        ; B = type
                dec  l
                ret  nz
                ld   a, b
                ld   e, S3_BOSS_DROPS          ; "BOSS DROPS " + name (bank 1)
                ld   hl, it_line
                jp   far1
.row:           ld   hl, drop_row              ; 3F-T5: the row scan + drop_tab are R6 (tier6.asm; bank 3 had 10 B free)
                jp   far6

; uniq_tab (§8.6 / §8.11: 8 B): D1..D7 by depth - 1, then the D4 Mage variant
uniq_tab:       DB   IT_H_KING, IT_A_SILK, IT_A_GRAVE, IT_W_CLEAVER
                DB   IT_C_SCARAB, IT_C_GRAVE, IT_H_MIRROR, IT_W_BONE
UNIQ_DEPTHS     EQU 7
                ASSERT $ - uniq_tab == 8 && K_KNIGHT == 0 && K_WIZARD == 1
