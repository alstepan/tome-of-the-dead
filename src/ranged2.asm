;==============================================================================
; ranged2.asm — 3F-T7, bank 2 (after kind_tab: every byte from the free-to-FRT
; room, memory-map "3F-B6" placement rule): the ranged hook's cheap reject.
;==============================================================================

; rk_tab — kind -> its rd_tab row (RK_*, R6 ranged6.asm), 0 = no ranged attack.
; The Archmage stays 0: its 7 spell rows are cast by its own AI (ai_mon -> arch_ai).
; BOSS-RANGED: the Goblin (K_BOSS_D1) / Spider (K_BOSS_D2) rows shoot only when golden (ai_rhook).
rk_tab:
                DS   K_GOBLIN, 0
                DB   RK_GKING                  ; 4
                DS   K_SPIDER - K_GOBLIN - 1, 0
                DB   RK_SQUEEN                 ; 9
                DS   K_ARCHER - K_SPIDER - 1, 0
                DB   RK_ARCHER                 ; 12
                DB   0
                DB   RK_NECRO                  ; 14
                DS   K_SLINGER - K_NECRO - 1, 0
                DB   RK_SLINGER                ; 21
                DS   K_SNIPER - K_SLINGER - 1, 0
                DB   RK_SNIPER                 ; 28
                DB   RK_BONE_CALLER            ; 29
                ASSERT $ - rk_tab == K_COUNT && (rk_tab >> 8) == (($ - 1) >> 8)   ; ai_rhook adds the kind to the low byte
                ASSERT K_NECRO == K_ARCHER + 2 && K_BONE_CALLER == K_SNIPER + 1 && K_SNIPER > K_SLINGER && K_SLINGER > K_NECRO
                ASSERT K_COUNT == K_BONE_CALLER + 1 && K_BOSS_D1 == K_GOBLIN && K_BOSS_D2 == K_SPIDER && K_SPIDER < K_ARCHER

;------------------------------------------------------------------------------
; ai_mon — 3F-T11b, resolve_monsters' (bank 3) per-monster AI call: the
; Archmage (game.md §9.9 A3: its own branch, one kind test) far6s R6 arch_ai
; (arch6.asm), every other kind runs ai_monster (bank 3, paged). Same In / Out
; as ai_monster (IX = the monster, ACT_SLOT; no result; clobbers all but IX).
; Cost: +31 T a monster (the test + JP).
;------------------------------------------------------------------------------
ai_mon:         ld   a, (ix+E_KIND)
                cp   K_ARCHMAGE
                jp   nz, ai_monster
                ld   hl, arch_ai
                jp   far6

;------------------------------------------------------------------------------
; ai_rhook — ai_monster (bank 3) right after its melee test (game.md §9.2
; "Per-turn order" step 4): a kind with an rk_tab row goes to R6 ai_ranged
; (far6, ranged6.asm); every other kind pays this one lookup.
; In : IX = the monster, H = 0 iff standing (ai_monster's flag), TMP4 = its
;      storey, ACT_SLOT = its slot.
; Out: CF = 1 the turn is used (shot / step-away / hold), CF = 0 the walker
;      rules run. TMP4 and HL kept.
; BOSS-RANGED: rows >= RK_GOLD1 (the Goblin King / Spider Queen) shoot only for a
; golden body (LEK_GOLD: only the D1 / D2 lair bosses carry it, lp_dtab); an
; ordinary Goblin / Spider goes on to ai_ghook (+46 T); other shooters +19 T.
; Clobbers: A, BC, DE.  Not a shooter: 66 T incl. the call; a shooter:
;      + far6 ai_ranged
;------------------------------------------------------------------------------
ai_rhook:
                ld   a, (ix+E_KIND)
                add  a, rk_tab & $FF
                ld   c, a
                ld   b, rk_tab >> 8
                ld   a, (bc)
                or   a
                jr   z, ai_ghook               ; CF = 0: not a shooter (HL untouched)
                cp   RK_GOLD1
                jr   c, .sh
                bit  LEK_GOLD_BIT, (ix+E_GOLD)
                jr   z, ai_ghook               ; an ordinary Goblin / Spider (ai_ghook sets CF itself)
.sh:            push hl
                ld   e, h                      ; E = standing flag (far6 passes DE in)
                ld   hl, ai_ranged             ; R6: A = its rd_tab row
                call far6                      ; L = 1 used
                ld   a, l
                pop  hl
                rra                            ; CF = L bit 0
                ret  c                         ; (a shooting / holding boss is done)
;------------------------------------------------------------------------------
; ai_ghook — 3F-T8 boss guard hook (game.md §9.2 G2: after the attack rules,
; before any movement rule): only the lair boss (CUR_ROOM = LVL_LAIR and
; E_KIND | E_GOLD = LP_BOSS) far7s ai_guard (bank-7 boss7.asm). Same In / Out as
; ai_rhook (CF = 1 the turn is used; TMP4 and HL kept).
; Cost: outside the lair +46 T a monster; the boss + far7 ai_guard.
;------------------------------------------------------------------------------
ai_ghook:       ld   a, (LVL_LAIR)
                ld   b, a
                ld   a, (CUR_ROOM)
                xor  b
                ret  nz                        ; CF = 0 (xor)
                ld   a, (ix+E_KIND)
                or   (ix+E_GOLD)
                ld   b, a
                ld   a, (LP_BOSS)
                xor  b
                ret  nz
                push hl
                ld   e, h                      ; E = standing flag
                ld   hl, ai_guard              ; bank 7 boss7.asm (w2b; was R6): L = 1 used
                call far7
                ld   a, l
                pop  hl
                rra
                ret

