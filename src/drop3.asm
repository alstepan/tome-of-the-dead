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
; R6 pickup6.asm), IX = the dead monster (EF_DYING
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
                cp   (ix+E_KIND)
                jr   nz, .row
                ld   hl, LVL_FLAGS
                bit  LF_UNIQUE_BIT, (hl)
                jr   nz, .row                  ; (the boss's kind as an ordinary monster)
                set  LF_UNIQUE_BIT, (hl)
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
                call hla
                ld   a, (hl)
                push af                        ; [type]
                call uq_fit                    ; the room at 8 types: displace an ordinary item
                pop  af                        ; (uq_fit clobbers A)
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
.row:           ld   hl, drop_tab
                ld   b, DROP_ROWS
.r:             ld   a, (ix+E_KIND)
                cp   (hl)
                jr   z, .hit
                inc  hl
                inc  hl
                inc  hl
                inc  hl
                djnz .r
                ret
.hit:           inc  hl
                ld   d, (hl)                   ; D = type
                inc  hl
                ld   e, 1                      ; E = qty
                ld   a, d
                cp   IT_ARROW
                jr   nz, .q
                ld   a, (HERO_KIND)
                or   a
                ret  nz                        ; arrows: Warrior runs only
                ld   e, DROP_ARROWS
.q:             ld   c, (hl)                   ; C = N
                inc  hl                        ; 3F-T3: HL -> the numerator (a tier's "k in N", §9.6)
                push hl
                push de
                call rng_mod                   ; A = 0..N-1
                pop de
                pop hl
                cp   (hl)                      ; roll < numerator <=> drop (1 in N rows: numerator 1,
                ret  nc                        ; the same RNG draw / outcome as before)
                ld   a, d
                ld   d, e                      ; D = qty
                ld   e, DROP_NEAR
                ld   hl, drop_put              ; R6
                jp   far6

;------------------------------------------------------------------------------
; uq_fit — FLOOR1 invariant (a room holds <= FI_SLOTS = 8 distinct item types):
; before a boss unique is placed, if CUR_ROOM already holds 8 types the lowest-
; value ordinary item is DESTROYED so the unique always fits: the first live
; entry of the room (both storeys, list order) whose type is a potion / ammo /
; food (types IT_POTION..IT_P_CURE, not IT_KEY), then every entry of that type
; (the type must leave the room), each col re-stamped (ap_stamp: the pile's next
; item, else air). Always found: the generator places <= 7 entries (<= 7 types),
; so an 8th type is a monster drop, and monster drops are food / ammo / mana.
; (uq_tab types are unique ids: never already on the floor.) None found
; (poked list): nothing happens and drop_put refuses the unique (L = 0).
; Clobbers: all but IX.   fits ~0.2k T (all 8 slots marked: + ~3k T gc); a displacement ~+9k T per destroyed entry (ap_stamp)
;------------------------------------------------------------------------------
uq_fit:         call uq_chk
                ret  z                         ; a slot is unmarked: <= 7 types, it fits (~0.2k T)
                ld   a, (CUR_ROOM)
                ld   hl, fi_gc                 ; R6: FI_USE := the types the room holds (~3k T)
                call far6
                call uq_chk
                ret  z                         ; (only stale slots were in use)
                ld   a, (CUR_ROOM)
                ld   c, a
                ld   hl, FLOOR_LIST
.v:             ld   a, (hl)
                and  FL_ROOM_MASK
                cp   c
                jr   nz, .nv
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                dec  l
                ld   b, a
                cp   IT_KEY
                jr   z, .nv
                dec  a
                cp   IT_P_CURE
                jr   c, .d                     ; type 1 .. 12: the victim's type = B
.nv:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .v
                ret
.d:             ld   hl, FLOOR_LIST            ; destroy every entry of the room with type B
.dl:            ld   a, (hl)
                and  FL_ROOM_MASK
                cp   c
                jr   nz, .dn
                inc  l
                inc  l
                ld   a, (hl)
                dec  l
                dec  l
                cp   b
                jr   nz, .dn
                ld   a, (hl)
                and  FL_ROOM_MASK | FL_S1
                ld   e, a                      ; E = room | storey
                inc  l
                ld   a, (hl)                   ; A = col
                dec  l
                ld   (hl), FL_EMPTY
                push bc
                push hl
                ld   hl, ap_stamp_a            ; bank 7: map + shadow + fi_add of the col's next
                call far7
                pop  hl
                pop  bc
.dn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .dl
                ld   a, FI_TSLOT & $FF         ; the victim type's slot is free again: drop_put's dp_cap
                add  a, b                      ; finds it at once (no second fi_gc, ~3k T)
                ld   l, a
                ld   h, FI_TSLOT >> 8
                ld   a, (hl)
                add  a, FI_USE & $FF
                ld   l, a
                ld   (hl), 0
                ret
; uq_chk — Z = some FI_USE slot is 0 (free: the room holds < 8 types, as every live type is marked).
uq_chk:         ld   hl, FI_USE
                ld   b, FI_SLOTS
.c:             ld   a, (hl)
                inc  l
                or   a
                ret  z
                djnz .c
                ret                            ; NZ: all 8 marked
                ASSERT (FI_USE >> 8) == (FI_TSLOT >> 8) && FI_SLOTS < 256 - (FI_USE & $FF)
                ASSERT IT_KEY == 4 && IT_P_CURE == 12 && IT_POTION == 1 && IT_F_CARROT == IT_KEY + 1 && IT_P_HEAL == IT_F_MEAT + 1
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE == $80 && FL_COL == 1 && FL_ITEM == 2
; drop_tab (§8.11 rulings 2 + §9.6 rewards; 3F-T3: 12 rows x 4 B: kind, type, N, k = "k in
; N"): the base drops (k = 1) and the tier rows (the base numerator + 1 per tier above 1:
; Cheese 1/4 -> 2/4 -> 3/4, Arrows 1/2 -> 2/2). First match wins. NOT here (T5 / T6): the
; tier rows of a base with no drop (Screech Bat, Black Widow, Skeleton Guard / Knight,
; Poltergeist), which drop a random food (Carrot / Apple / Pear) 1 in 4.
DROP_STRIDE     EQU 4
drop_tab:       DB   K_RAT,         IT_F_CHEESE, 4, 1
                DB   K_GOBLIN,      IT_F_APPLE,  4, 1
                DB   K_ORC,         IT_F_MEAT,   3, 1
                DB   K_ARCHER,      IT_ARROW,    2, 1
                DB   K_NECRO,       IT_P_MANA,   3, 1
                DB   K_GIANT_RAT,   IT_F_CHEESE, 4, 2
                DB   K_RABBIT_RAT,  IT_F_CHEESE, 4, 3
                DB   K_SLINGER,     IT_F_APPLE,  4, 2
                DB   K_ORC_BERSERK, IT_F_MEAT,   3, 2
                DB   K_ORC_BOUNCER, IT_F_MEAT,   3, 3
                DB   K_SNIPER,      IT_ARROW,    2, 2
                DB   K_BONE_CALLER, IT_P_MANA,   3, 2
DROP_ROWS       EQU ($ - drop_tab) / DROP_STRIDE
; uniq_tab (§8.6 / §8.11: 8 B): D1..D7 by depth - 1, then the D4 Mage variant
uniq_tab:       DB   IT_H_KING, IT_A_SILK, IT_A_GRAVE, IT_W_CLEAVER
                DB   IT_C_SCARAB, IT_C_GRAVE, IT_H_MIRROR, IT_W_BONE
UNIQ_DEPTHS     EQU 7
                ASSERT DROP_ROWS == 12 && $ - uniq_tab == 8 && K_KNIGHT == 0 && K_WIZARD == 1
