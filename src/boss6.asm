;==============================================================================
; boss6.asm — 3F-T8 bosses (R6; r6.asm rules: far6 only, no SMC, no bank-3
; code / data). game.md §9.2 "Boss guard" (G1 post, G1a arrival gap, G1b
; escort, G2 guard AI), §1.1 / §9.4.4 (the lair grate), §9.1 (Ogre SLAM).
; Byte-exact reference for lp_post: tools/levelgen.py lp_post (tests/lp.py A7).
;
; Entries (far6; A and F are lost on the way back):
;   lp_post     lp_enter's unit loop (bank 3), a unit of the lair: its post.
;   ai_guard    ai_ghook (bank 2, ranged2.asm): the lair boss's turn after the
;               attack / ranged rules (G2).
;   grate_open  mon_drop (bank 3): the lair boss died -> the gate opens.
;==============================================================================
GUARD_R         EQU 8                       ; G2: the leash, |hero x - c| <= R (user 2026-10-29)
GUARD_GAP       EQU 5                       ; G1a / G1b: body gap to the hero's arrival box

;------------------------------------------------------------------------------
; lp_post — G1 / G1a / G1b (pure function of c, the widths, the door side, the
; hero's arrival box and the cell map: no spawn-stream step). In: LPV_RDP ->
; the unit's entry {kind byte, hp}, LP_W = its body cols, LP_HX / LP_HS /
; LP_HW, LP_CMAP (lp_cmap + the bodies lp_spawn placed so far), LPV_ROOM =
; LVL_LAIR (the caller tests it).
;  - the post bx: c = the lair's RD_EXITCOL (the boss stands ON the grate,
;    3-col body c..c+2, 4-col c..c+3). G1a: the hero arriving on storey 1
;    with a body gap < 5 to it, or (T8 review) a unit placed before it in the
;    same record already covering a body col there (LPC_BODY) -> shift 1 col at a time away from him (right
;    if hx < c, else left) to the first x with gap >= 5 whose body cols carry
;    no LP_CMAP mark outside the exit's own footprint marks c-1 .. c+3 (game.md
;    §9.2 G1: the exit is exempt, every other rule holds); none inside
;    LP_XMIN .. LP_XMAX + 1 - wb -> L = 0 (the ordinary placement; only test
;    arrival boxes no real exit makes reach it);
;  - the boss (kind | LEK_GOLD == LP_BOSS): storey 1, x = bx; LF_PROVOKED
;    cleared (G2: cleared at spawn);
;  - any other unit (the escort; banked followers too): storey 1, shoulder to
;    shoulder on the door side, x = bx - 1 - we (door left) / bx + wb + 1, then
;    the other side; legal = inside LP_XMIN .. LP_XMAX + 1 - we, gap >= 5 on
;    the hero's arrival storey, no LP_CMAP mark over its cols; both illegal (or
;    no post) -> L = 0 (lp_place).
; Door side (engineer's simplification, reported): the lair's left edge if it
; has one, else the right one (game.md §1.1 L1 (7)'s BFS-parent rule differs
; only for a through-room lair with both edges).
; Out: L = 1: C = 1 (storey), E = col; L = 0: lp_place.
; Clobbers: A, BC, DE, HL.   ~0.5k T (+ ~0.2k a shifted col) + far6
;------------------------------------------------------------------------------
LP_EXLO         EQU LP_BEST                 ; lp_post scratch (lp_place no longer uses LP_BEST / LP_BX)
LP_EXHI         EQU LP_BX
lp_post:
                ld   a, (LP_BOSS)
                ld   d, a                      ; D = LP_BOSS (row | LEK_GOLD)
                and  LEK_KIND_MASK
                add  a, (kind_tab + KT_BW) & $FF
                ld   l, a
                ld   h, (kind_tab + KT_BW) >> 8
                ld   e, (hl)                   ; E = wb
                ld   a, (LVL_LAIR)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC + RD_EXITCOL) & $FF
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   c, (hl)                   ; C = c
                ld   a, c
                dec  a
                ld   (LP_EXLO), a              ; the exit's own footprint marks: c-1 ..
                add  a, FEAT_W + 1
                ld   (LP_EXHI), a              ; .. c+3 (lp_cmap: f-1 .. f+3)
                call .post                     ; NC: A = bx
                jr   c, .none
                ld   c, a                      ; C = bx
                ld   hl, (LPV_RDP)
                ld   a, (hl)
                and  LEK_KIND_MASK | LEK_GOLD
                cp   d
                jr   nz, .esc
                ld   hl, LVL_FLAGS             ; the boss
                res  LF_PROVOKED_BIT, (hl)
                ld   e, c
.one:           ld   c, 1
                ld   l, c
                ret
.esc:           ld   a, $FF
                ld   (LP_EXLO), a              ; no exemption for anyone else
                ld   a, (LVL_LAIR)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC + RD_EXITS) & $FF
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   b, (hl)                   ; B = RD_EXITS
                ld   a, (LP_W)
                ld   d, a                      ; D = we
                ld   a, c
                sub  d
                dec  a
                ld   l, a                      ; L = left x = bx - 1 - we (may be < 0)
                ld   a, c
                add  a, e
                inc  a
                ld   h, a                      ; H = right x = bx + wb + 1
                ld   e, d                      ; E = we: the width .legal tests
                bit  RDX_L_BIT, b
                jr   nz, .lr
                ld   a, l                      ; door right: right first
                ld   l, h
                ld   h, a
.lr:            ld   a, l
                push hl
                call .legal                    ; the door side
                pop  hl
                jr   nc, .ok
                ld   a, h
                call .legal                    ; the other side
                jr   nc, .ok
.none:          ld   l, 0
                ret
.ok:            ld   e, a
                jr   .one
; .post: C = c, E = wb -> NC: A = bx; CF: no legal post. Keeps C, D, E.
.post:          ld   a, c
                call .gap
                jr   c, .sh
                call .marks
                ret  nc                        ; gap and cells hold at c: bx = c
.sh:            ld   a, (LP_HX)
                cp   c
                ld   b, 1                      ; the hero left of c: shift right
                jr   c, .pd
                ld   b, $FF
.pd:            ld   a, c
.pl:            add  a, b
                call .rng
                ret  c                         ; ran out of the room: no post
                call .gap
                jr   c, .pl
                call .marks
                jr   c, .pl
                ret
; .legal: A = x, E = width -> NC = legal (range, gap, marks). Keeps A, BC, DE.
.legal:         call .rng
                ret  c
                call .gap
                ret  c
                ; fall through
; .marks: A = x, E = width -> CF = an LP_CMAP storey-1 mark on a body col
; outside LP_EXLO .. LP_EXHI ($FF: none exempt). Keeps A, BC, DE.
.marks:         push bc
                push af
                ld   c, a
                add  a, (LP_CMAP + LP_CMW) & $FF   ; storey 1's row (one page)
                ld   l, a
                ld   h, LP_CMAP >> 8
                ld   b, e
.m1:            ld   a, (hl)
                or   a
                jr   z, .m2
                and  LPC_BODY
                jr   nz, .mb                   ; a placed body: never exempt
                ld   a, (LP_EXLO)
                dec  a
                cp   c
                jr   nc, .mb                   ; col < lo: a real mark
                ld   a, (LP_EXHI)
                cp   c
                jr   c, .mb                    ; col > hi
.m2:            inc  l
                inc  c
                djnz .m1
                pop  af
                pop  bc
                or   a
                ret
.mb:            pop  af
                pop  bc
                scf
                ret
; .rng: A = x (signed), E = width -> CF = outside LP_XMIN .. LP_XMAX + 1 - width. Keeps A, BC, DE.
.rng:           push bc
                ld   c, a
                sub  LP_XMIN                   ; (a negative x -> >= $FB: out)
                ld   b, a
                ld   a, LP_XMAX + 1 - LP_XMIN
                sub  e
                cp   b
                ld   a, c
                pop  bc
                ret
; .gap: A = x, E = width -> CF = on the hero's arrival storey 1 with a body gap < 5. Keeps A, BC, DE.
.gap:           push bc
                ld   c, a
                ld   a, (LP_HS)
                dec  a
                jr   nz, .gy                   ; arrival on storey 0
                ld   a, (LP_HX)
                ld   hl, LP_HW
                add  a, (hl)
                add  a, GUARD_GAP
                ld   b, a                      ; hx + hw + 5
                ld   a, c
                cp   b
                jr   nc, .gy                   ; right of the hero
                add  a, e
                add  a, GUARD_GAP
                ld   b, a                      ; x + w + 5
                ld   a, (LP_HX)
                cp   b                         ; CF: hx < x + w + 5, too close
                ld   a, c
                pop  bc
                ret
.gy:            ld   a, c
                pop  bc
                or   a
                ret
                ASSERT (LP_CMAP >> 8) == ((LP_CMAP + 2 * LP_CMW - 1) >> 8) && LP_XMAX + 1 < $80
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + 9 * RD_STRIDE - 1) >> 8) && FEAT_W == 3

;------------------------------------------------------------------------------
; ai_guard — G2 (game.md §9.2), far6 from ai_ghook: IX = the lair boss
; (ACT_SLOT = its slot), E = 0 iff standing, TMP4 = its storey, PL_* =
; cache_player. Runs after the melee / ranged rules found nothing to do.
;  - the Archmage (D8): G1d only, the ordinary rules (L = 0);
;  - the Ogre: one SLAM-counter turn (og_adv; a turn with a blow advances it in
;    reach_ok instead);
;  - mid-ladder, or off storey 1 (a Vampire Lord left on storey 0 after its bat
;    flight): the ordinary rules;
;  - ENGAGED iff the hero stands on storey 1 (not mid-ladder) and (|hero x - c|
;    <= GUARD_R or LF_PROVOKED): the ordinary rules (L = 0);
;  - else home: x != c -> one walker step toward c (blocked: wait); x == c ->
;    wait facing the hero (L = 1). Never climbs, never follows.
; Out: L = 1 the turn is used, 0 the walker rules run.
; Clobbers: all but IX.   ~0.25k T + a step (far6 ~0.25k on top)
;------------------------------------------------------------------------------
ai_guard:
                ld   a, (ix+E_KIND)
                cp   K_ARCHMAGE
                jr   z, .ord
                cp   K_OGRE
                call z, og_adv                 ; (bank 2; keeps DE)
                ld   a, e
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

;------------------------------------------------------------------------------
; grate_open — far6 from mon_drop (bank 3): the lair boss died (CUR_ROOM = the
; lair). game.md §9.2 "Grate": LF_GRATE_OPEN, the 3 exit cells T_GRATE_SHUT ->
; T_GRATE (raised, LADDER | HOLE: a hero standing on it stays put, DOWN at c
; descends), the depth's GLOW above the middle cell if it is air (as
; build_room_map draws an open exit), the bank-7 attr shadow + a queued
; restore of rows 16-17 (rect_repaint, low RAM), "A GATE GLEAMS, THE WAY
; DOWN". Before the unique is placed (drop_put needs TF_FLOOR: never on the
; open gate). IX kept.
; Clobbers: A, BC, DE, HL.   ~9k T (the shadow + the line)
;------------------------------------------------------------------------------
grate_open:
                ld   hl, LVL_FLAGS
                set  LF_GRATE_OPEN_BIT, (hl)
                call cur_room_desc
                ld   a, l
                add  a, RD_EXITCOL
                ld   l, a
                ld   a, (hl)
                or   a
                ret  z                         ; (no level exit here: never)
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
                ld   a, (LVL_DEPTH)
                add  a, (glow6 - 1) & $FF
                ld   e, a
                ld   d, (glow6 - 1) >> 8
                ld   a, (de)
                ld   (hl), a
.ng:            dec  c                         ; C, B = c, 16: 3 cols x 2 rows
                ld   de, $0302
                call rect_repaint              ; (low RAM: shadow_rect, restore_page, queue_damage)
                ld   a, TX_GATE_GLEAMS
                jp   msg_push
; glow6 — bank-3 glow_ids (build_room_map) again, by depth - 1 (R6 cannot read bank 3)
glow6:          DB   TS1_GLOW_F1_R0C0, TS2_GLOW_F1_R0C0, TS3_GLOW_F1_R0C0, TS4_GLOW_F1_R0C0
                DB   TS5_GLOW_F1_R0C0, TS6_GLOW_F1_R0C0, TS7_GLOW_F1_R0C0, TS8_GLOW_F1_R0C0
                ASSERT $ - glow6 == LEVELS && ((glow6 - 1) >> 8) == ((glow6 + LEVELS - 1) >> 8)
                ASSERT T_AIR == 0 && T_GRATE_SHUT != T_GRATE

;------------------------------------------------------------------------------
; boss_chk — far6 from lp_transition right after lp_enter (bank 3): the lair
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
