;==============================================================================
; intent3.asm — C3-2 icon bar logic, bank 3 (cold: entered by far3 only on an
; event — a cursor step, a slot shortcut, an icon use; game.md §3.1 / §3.5).
; The per-tick FIRE machine is intent_tick (io.asm, bank 2); the movement
; rules are tpt_intent (logic.asm).
;
; Slot actions (SA_*) by class, one byte per slot (game.md §3.5). The panel
; draws its own bars (panel.asm bar_knight / bar_wizard, C3-3); these say
; what FIRE does and whether the cursor may stop there.
;==============================================================================

; SA_* (hero_defs.asm), slot_act_tab / slot_act / abil_rank: bank 2 (icons.asm),
; shared with the panel's icon poll.

;------------------------------------------------------------------------------
; slot_ok — A = slot -> NZ if the cursor may stop there (not empty, not an
; unlearned ability: game.md §3.5; greyed icons are selectable), E = SA_*.
; Clobbers: A, BC (B kept), DE, HL
;------------------------------------------------------------------------------
slot_ok:
                call slot_act
                ld   e, a
                or   a
                ret  z                         ; SA_EMPTY
                sub  SA_ABIL
                jp   nc, abil_rank
                or   a                         ; NZ
                ret
;------------------------------------------------------------------------------
; cursor_step — far3, A = +1 / -1: move SEL_SLOT to the next selectable slot
; that way, wrapping 10 -> 1 / 1 -> 10 (none other: unchanged). No turn.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
cursor_step:
                ld   c, a
                ld   a, (SEL_SLOT)
                ld   b, ICON_SLOTS - 1
.l:             add  a, c
                cp   ICON_SLOTS
                jr   c, .in
                ld   a, ICON_SLOTS - 1         ; -1 -> 9
                bit  7, c
                jr   nz, .in
                xor  a                         ; 10 -> 0
.in:            push bc                        ; slot_ok clobbers C (abil_rank)
                push af
                call slot_ok
                pop  hl                        ; H = the slot (A of the push)
                ld   a, h
                pop  bc
                jr   nz, .set
                djnz .l
                ret
.set:           ld   (SEL_SLOT), a
                ret

;------------------------------------------------------------------------------
; sel_key — far3, A = shortcut 1..10 (key 1..9, 0): select that slot if the
; cursor may stop there; an unlearned ability prints NOT LEARNED. No turn.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
sel_key:
                dec  a
                ld   b, a
                call slot_ok
                ld   a, b
                jr   z, .no
                ld   (SEL_SLOT), a
                ret
.no:            ld   a, e
                cp   SA_ABIL
                ret  c                         ; an empty slot: nothing
                ld   a, TX_NOT_LEARNED
                jp   msg_push

;------------------------------------------------------------------------------
; use_icon — far3 from tpt_intent (IX = hero, live list built): FIRE on the
; selected slot. Out: L = 1 turn used, 0 refused (no turn; usually a message).
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
use_icon:
                ld   a, (SEL_SLOT)
                call slot_act
                cp   SA_ABIL
                jr   c, .t
                sub  SA_ABIL
                ld   (TMP7), a                 ; ability index for ic_abil
                ld   a, SA_ABIL
.t:             add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, icon_jt
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   (hl)

icon_jt:        DW ic_none, ic_melee, ic_daggers, ic_bow, ic_food
                DW ic_potion, ic_scroll, ic_bag, ic_abil
                ASSERT ($ - icon_jt) / 2 == SA_COUNT

; melee (sword / staff): the nearest hostile in reach on the faced side, else
; close the faced door (game.md §2.3, replaces the 3B key C), else NO TARGET.
; Not from mid-ladder.
ic_melee:
                call on_ladder
                jr   z, .nt
                ld   a, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .f
                ld   a, $FF
.f:             ld   (TMP6), a
                ld   hl, find_target_far       ; D3-S2: bank 7 (L = slot / $FF)
                call far7
                ld   a, l
                cp   $FF
                jr   z, .door
                call do_attack                 ; turn3.asm (this bank)
                ld   l, 1
                ret
.door:          call try_close                 ; lowram: CF = 1 closed
                ld   l, 1
                ret  c
.nt:            ld   a, TX_NO_TARGET
                jr   ic_refuse

ic_potion:
                ld   a, (ix+E_POT)
                or   a
                ld   a, TX_NO_POTION
                jr   z, ic_refuse
                jp   try_quaff                 ; L = 1 drunk / 0 (HP full: no turn)

ic_daggers:
                ld   a, (DAGGERS)
                or   a
                ld   a, TX_NO_DAGGERS
                jr   z, ic_refuse
                jr   ic_none                   ; 3D: the throw

ic_bow:
                ld   a, (HAS_BOW)
                or   a
                ld   a, TX_NO_BOW
                jr   z, ic_refuse
                ld   a, (ARROWS)
                or   a
                ld   a, TX_NO_ARROWS
                jr   z, ic_refuse
                jr   ic_none                   ; 3D: the shot

ic_food:        ld   a, TX_NO_FOOD             ; 3E: food
                jr   ic_refuse
ic_scroll:      ld   a, TX_NO_SCROLL           ; 3E: scrolls
                jr   ic_refuse
ic_bag:         ld   a, TX_NO_BAG              ; 3E: the bag page
                jr   ic_refuse

ic_abil:
                ld   a, (TMP7)
                call abil_rank
                ld   a, TX_NOT_LEARNED
                jr   z, ic_refuse
                ; 3D: cast / power attack (fall through: no turn)
ic_none:        ld   l, 0
                ret

ic_refuse:      call msg_push
                ld   l, 0
                ret

;------------------------------------------------------------------------------
; hero_st_init — new_game: the C3-2 intent state + the start kit counters the
; icon handlers read (game.md §4: Warrior 3 daggers, no bow, 0 arrows; no
; ability learned). STICK / KEYTAB / JOY_MODE persist (boot), ICON_SH is the
; panel's (C3-3), LVL / XP / MP 3D's.  Clobbers: A, B, HL
;------------------------------------------------------------------------------
hero_st_init:
                xor  a
                ld   hl, SEL_SLOT              ; SEL_SLOT, FIRE_ST, FIRE_T
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                ld   hl, CUR_REP               ; CUR_REP .. PAUSE_REQ
                ld   b, HERO_ST_USED - CUR_REP
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   (ARROWS), a
                ld   (HAS_BOW), a
                ld   (ICON_MODE), a            ; C3-2b
                ld   (END_SHOWN), a            ; C3-6
                ld   (PAUSED), a
                ld   (EXIT_LOCK), a
                ld   (DN_T), a
                ld   (DN_COMMIT), a
                ld   (ARANK), a
                ld   (ARANK + 1), a
                ld   (XP), a                   ; C3-3 shows LV / XP (reserved for 3D)
                ld   (XP + 1), a
                inc  a
                ld   (LVL), a                  ; level 1
                dec  a
                ld   a, (HERO_KIND)
                or   a
                ld   a, 0
                jr   nz, .d                    ; Mage: no daggers, DEF 0 (HERO3D zeroed)
                ld   a, WARRIOR_DEF
                ld   (HERO_DEF), a             ; D3-6a: Leather (game.md §4, §11.4)
                ld   a, WARRIOR_DAGGERS
.d:             ld   (DAGGERS), a
                ret
WARRIOR_DAGGERS EQU 3
WARRIOR_DEF     EQU 1                          ; Leather; gear replaces it in 3E
