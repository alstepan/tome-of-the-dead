;==============================================================================
; boss7.asm — 3F-T8 the lair boss's cold events, bank-7 cold code (MEM-RECLAIM
; w2b: from R6 boss6.asm; bank7.asm rules: far7 only, A / F lost on return).
;   grate_open  far7 from mon_drop (bank 3): the lair boss died -> the gate opens.
;   boss_chk    far7 from lp_transition (bank 3): the boss-exists debug trap.
;   ai_guard    far7 from ai_ghook (bank 2): the lair boss's guard turn (G2).
; lp_post: bank-0 boss0.asm (NEW-MON3 T1; was R6 boss6.asm).
;==============================================================================
;------------------------------------------------------------------------------
; grate_open — far7 from mon_drop (bank 3; MEM-RECLAIM w2b: was R6 far6): the lair boss died (CUR_ROOM = the
; lair). game.md §9.2 "Grate": LF_GRATE_OPEN, the 3 exit cells T_GRATE_SHUT ->
; T_GRATE (raised, LADDER | HOLE: a hero standing on it stays put, DOWN at c
; descends), the depth's GLOW above the middle cell if it is air (as
; build_room_map draws an open exit), the bank-7 attr shadow + a queued
; restore of rows 16-17 (rect_repaint, low RAM), "A GATE GLEAMS, THE WAY
; DOWN". Before the unique is placed (drop_put needs TF_FLOOR: never on the
; open gate). P3 (F3_GEN): on D8 -> R6 seal_open instead, LF_GRATE_OPEN stays clear
; (any killer, the Archmage's own Mirror Helm return too). IX kept.
; grate_open.op — WIN2 (user 2026-11-01), from low-RAM tome_gone (bank 7 paged): the
; Tome is destroyed, the D8 gate opens: no XP; CUR_ROOM is the Sanctum (no exit
; col), so only LF_GRATE_OPEN + the line; the lair's next build_room_map stamps
; T_GRATE + the glow, try_climb reads the flag.
; Clobbers: A, BC, DE, HL.   ~9k T (the shadow + the line; the XP delta ~100 T)
;------------------------------------------------------------------------------
grate_open:
                ld   a, (LVL_DEPTH)            ; golden-boss XP: every boss body reaches here (D4 / D7 / D8 with delta 0); bank 3 then adds the
    IF F3_GEN
                cp   LEVELS                    ; P3: D8 has no exit (game.md §1.1): the Archmage's death
                jr   z, .seal                  ; breaks the Sanctum seal, the grate stays shut (XP delta 0)
    ENDIF
                add  a, (bxp_d - 1) & $FF      ; base kind's KXP (and clamps at XP_MAX), so the delta makes §4.1's total
                ld   l, a                      ; (0 on D4 / D7 / D8: kx_tab is already right). bxp_d: one page (ASSERT)
                ld   h, (bxp_d - 1) >> 8
                ld   e, (hl)
                ld   d, 0
                ld   hl, (XP)
                add  hl, de                    ; <= 9,999 + 70: no 16-bit wrap
                ld   (XP), hl
.op:            ld   hl, LVL_FLAGS
                set  LF_GRATE_OPEN_BIT, (hl)
                call cur_room_desc
                ld   a, l
                add  a, RD_EXITCOL
                ld   l, a
                ld   a, (hl)
                or   a
                jr   z, .msg                   ; no level exit here: only tome_gone (the Sanctum)
                ld   c, a
                ld   b, FLOOR_ROW1
                call cell_addr                 ; (bank 2; keeps BC, DE)
                ld   a, T_GRATE
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                dec  b                         ; row 16, col c + 1: the glow if air
                inc  c
                call cell_addr
                ld   a, (hl)
                or   a
                jr   nz, .ng
                ld   (hl), T_GLOW
.ng:            dec  c                         ; C, B = c, 16: 3 cols x 2 rows
                ld   de, $0302
                call rect_repaint              ; (low RAM: shadow_rect, restore_page, queue_damage)
.msg:           ld   a, TX_GATE_GLEAMS
                jp   msg_push
.seal:          ld   hl, seal_open             ; R6 tome6.asm: LF_SEAL_OPEN, EG_SEAL off, "THE SEAL BREAKS"
                jp   far6
;------------------------------------------------------------------------------
; boss_chk — far7 (w2b: was far6) from lp_transition right after lp_enter (bank 3): the lair
; boss must always exist on the level while it lives (LF_UNIQUE clear): as an
; active slot of LVL_LAIR or an entry of the lair's record (a FRESH lair that
; is not being entered has none yet); while the hero ENTERS the lair it must be a
; live slot (the record does not count: UB7). Else BOSS_TRAP += 1 (debug trap, expect
; 0; tests/boss.py). The grate opens ONLY on the boss's death (mon_drop ->
; grate_open), so a lost boss can never open it silently.
; Clobbers: A, BC, DE, HL, IX.   ~1.2k T
;------------------------------------------------------------------------------
boss_chk:
                ld   a, (LVL_FLAGS)
                and  LF_UNIQUE
                ret  nz                        ; the boss died
                ld   a, (LVL_LAIR)
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                ld   e, a
                ld   d, 0
                ld   hl, LP_REC
                add  hl, de                    ; the lair's record (LR_STRIDE 9)
                ld   a, (EXIT_DEST)
                cp   c
                jr   z, .slots                 ; entering the lair: the boss must be a LIVE slot
                ld   a, (hl)                   ; (T8 review: a boss left in the record there is
                bit  LR_VISITED_BIT, a         ; exactly UB7's invisible boss)
                ret  z                         ; FRESH, not entered now: no boss yet
                and  LR_CNT_MASK
                jr   z, .slots
                ld   b, a
.r:             inc  hl
                ld   a, (hl)
                inc  hl
                and  LEK_KIND_MASK | LEK_GOLD
                ld   e, a
                ld   a, (LP_BOSS)
                cp   e
                ret  z                         ; banked in its lair
                djnz .r
.slots:         ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
.s:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_DYING
                dec  a
                jr   nz, .n                    ; free or dying
                ld   a, (ix+E_ROOM)
                cp   c
                jr   nz, .n
                ld   a, (ix+E_KIND)
                or   (ix+E_GOLD)
                ld   hl, LP_BOSS
                cp   (hl)
                ret  z                         ; a slot of its lair
.n:             add  ix, de
                djnz .s
                ld   hl, BOSS_TRAP
                inc  (hl)
                ret
                ASSERT LR_STRIDE == 9 && EF_ACTIVE == 1

;------------------------------------------------------------------------------
; ai_guard — G2 (game.md §9.2), far7 (w2b: was far6) from ai_ghook: IX = the lair boss
; (ACT_SLOT = its slot), E = 0 iff standing, TMP4 = its storey, PL_* =
; cache_player. Runs after the melee / ranged rules found nothing to do.
;  - the Ogre: one SLAM-counter turn (og_adv; a turn with a blow advances it in
;    reach_ok instead);
;  - mid-ladder, or off storey 1 (a Vampire Lord left on storey 0 after its bat
;    flight): the ordinary rules;
;  - ENGAGED iff the hero stands on storey 1 (not mid-ladder) and (|hero x - c|
;    <= GUARD_R (31: the whole storey, user 2026-11-02) or LF_PROVOKED): the ordinary rules (L = 0);
;  - else home: x != c -> one walker step toward c (blocked: wait); x == c ->
;    wait facing the hero (L = 1). Never leaves the post (the Vampire Lord climbs only back from storey 0 via the ordinary rules; it never follows through exits).
; Out: L = 1 the turn is used, 0 the walker rules run.
; Clobbers: all but IX.   ~0.25k T + a step (far7 ~0.25k on top; contended)
;------------------------------------------------------------------------------
ai_guard:
                ld   a, (ix+E_KIND)            ; (3F-T11b: the Archmage never gets here: ai_mon -> arch_ai)
                cp   K_MUMMY                   ; 3F-T9: the Golden Pharaoh (D5's boss) summons
                jr   nz, .og                   ; (R6 spawn6.asm ph_summon: L = 1 the turn is used)
                push de
                ld   hl, ph_summon
                call far6
                pop  de
                dec  l
                jr   z, .used
                jr   .ng
.og:            cp   K_OGRE
                call z, og_adv                 ; (bank 2; keeps DE)
.ng:            ld   a, e
                or   a
                jr   nz, .ord                  ; mid-ladder
                ld   a, (TMP4)
                dec  a
                jr   nz, .ord                  ; not on storey 1
                call cur_room_desc             ; (bank 2) HL
                ld   a, l
                add  a, RD_EXITCOL
                ld   l, a
                ld   c, (hl)                   ; C = c
                ld   a, (PL_LADDER)
                or   a
                jr   nz, .home
                ld   a, (PL_STOREY)
                dec  a
                jr   nz, .home
                ld   a, (LVL_FLAGS)
                and  LF_PROVOKED
                jr   nz, .ord
                ld   a, (PL_X)
                sub  c
                jr   nc, .ab
                neg
.ab:            cp   GUARD_R + 1
                jr   c, .ord                   ; inside the leash: engaged
.home:          ld   a, c
                sub  (ix+E_X)
                jr   z, .wait
                ld   d, 1
                jr   nc, .st
                ld   d, $FF
.st:            ld   e, 0
                call try_step_face             ; (bank 2; blocked: a wait)
                jr   .used
.wait:          ld   a, (PL_X)                 ; on the post: face the hero
                sub  (ix+E_X)
                jr   z, .used
                ld   a, 1
                jr   nc, .f
                ld   a, $FF
.f:             call face_a
.used:          ld   l, 1
                ret
.ord:           ld   l, 0
                ret
                ASSERT RD_EXITCOL < RD_STRIDE
