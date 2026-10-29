;==============================================================================
; boss2.asm — 3F-T8 bank-2 helpers (after kind_tab): the golden boss's stats
; (game.md §9.7 R1: atk + 2, dmg + 1, DEF + 1, the BOSS immunity bit), the
; Ogre SLAM (§9.1), PROVOKED (§9.2 G2) and the golden glow's attr-only repaint
; (§8.6). The callers are bank-3 combat code (hit_roll, do_attack,
; attack_if_reach, deal_hit, room_status) and the renderer: helpers here keep
; their call sites to 3 B (bank 3 is the tight region).
;==============================================================================

;------------------------------------------------------------------------------
; atk_mod — 3F-T8 (bank 2 since the T8 review: bank-3 relief), do_attack's rolled damage (a hit): A = dmg (>= 1), C / E =
; the attacker's deal_hit pair (kx_tab KX_MELEE), IX = attacker. A golden boss
; hits + 1 (§9.7 R1); the Ogre's SLAM (counter OG_SLAM, set by reach_ok this
; turn: game.md §9.1) x 1.5 (dmg + dmg / 2) and C / E = PHYS + STUNNED
; OG_STUN turns, always.  Out: A, C, E.  Clobbers: L.   ~70 T (not the Ogre)
;------------------------------------------------------------------------------
atk_mod:
                bit  LEK_GOLD_BIT, (ix+E_GOLD)
                jr   z, .ng
                inc  a
.ng:            ld   l, a
                ld   a, (ix+E_KIND)
                cp   K_OGRE
                ld   a, l
                ret  nz
                ld   a, (ix+E_RCD)
                and  RCD_MASK
                cp   OG_SLAM
                ld   a, l
                ret  nz
                srl  a
                add  a, l                      ; x 1.5 (rounded down)
                ld   c, DTY_PHYS | (EFX_STUNNED << DH_EFX_SHIFT)
                ld   e, OG_STUN                ; chance nibble 0: always
                ret

;------------------------------------------------------------------------------
; reach_ok — attack_if_reach's reach test (was KFIELD KT_REACH / cp b): IX =
; attacker, B = the gap -> CF = out of reach. The Ogre: reach OG_REACH at
; counter OG_READY (and a blow there is the SLAM: counter := OG_SLAM), else
; reach 1 (a blow advances the counter: og_adv). Keeps DE (E = the side).
; Clobbers: A, C, HL.   ~70 T (not the Ogre)
;------------------------------------------------------------------------------
reach_ok:
                ld   a, (ix+E_KIND)
                cp   K_OGRE
                jr   z, .og
                add  a, (kind_tab + KT_REACH) & $FF
                ld   l, a
                ld   h, (kind_tab + KT_REACH) >> 8
                ld   a, (hl)
                cp   b                         ; CF = reach < gap
                ret
.og:            ld   a, (ix+E_RCD)
                and  RCD_MASK
                cp   OG_READY
                jr   z, .rd
                ld   a, 1
                cp   b
                ret  c                         ; out of reach: ai_guard's og_adv this turn
                jp   og_adv                    ; an ordinary blow (NC from og_put)
.rd:            ld   a, OG_REACH
                cp   b
                ret  c
                ld   a, OG_SLAM
                jp   og_put
                ASSERT OG_READY == 2 && OG_SLAM == 3 && RCD_MASK == 3

;------------------------------------------------------------------------------
; stamp_slot — draw_slot's attr stamp (was `jp stamp_rect`): A = attr, C,B,D,E
; = the footprint, HL = R_DATTR, IX = the entity. A golden body re-stamped in
; place (R_DIRTY = DIRTY_ATTR: render .sa added NO damage rect for it, and
; the overlap repair found none over it) is the attr-only repaint: stamp2
; writes both screens' attrs (bank 5 and SCREEN7_ATTR) and present has nothing
; to copy (~1.4k T for a 3x6 body vs ~5-7k T through a damage rect). Any other
; slot: stamp_rect (bank 5; present copies its damage rect).
;------------------------------------------------------------------------------
stamp_slot:
                inc  l                         ; R_DIRTY
                bit  LEK_GOLD_BIT, (ix+E_GOLD)
                jp   z, stamp_rect
                push af
                ld   a, (hl)
                cp   DIRTY_ATTR
                jr   z, .two
                pop  af
                jp   stamp_rect
.two:           pop  af
                ; fall through
;------------------------------------------------------------------------------
; stamp2 — A = attr, C,B,D,E = rect (inside the screen): the attrs of BOTH
; screens (bank 5 $5800, bank 7 SCREEN7_ATTR = $5800 + $8000), the caller's
; $C000 bank restored. Clobbers: A, BC, DE, HL.   ~0.35k + 47 T/cell + ~45 T/row
;------------------------------------------------------------------------------
stamp2:
                push af
                call attr_addr                 ; HL (keeps BC, DE)
                pop  bc                        ; B = attr
                ld   a, (PORT_7FFD_SHADOW)
                push af
                push bc
                ld   a, BANK_SCREEN7
                call page_bank                 ; (A, BC)
                pop  bc
                ld   c, b                      ; C = attr
.row:           push hl
                ld   b, d
.col:           ld   (hl), c                   ; bank 5
                set  7, h
                ld   (hl), c                   ; bank 7 (+ $8000)
                res  7, h
                inc  l
                djnz .col
                pop  hl
                ld   a, l
                add  a, ATTR_STRIDE
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:            dec  e
                jr   nz, .row
                pop  af
                jp   restore_page
                ASSERT SCREEN7_ATTR == SCREEN_ATTR + $8000 && BANK_SCREEN7 == 7
