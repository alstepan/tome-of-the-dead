;==============================================================================
; boss6.asm — 3F-T8 bosses (R6; r6.asm rules: far6 only, no SMC, no bank-3
; code / data). game.md §9.2 "Boss guard" (G1 post, G1a arrival gap, G1b
; escort, G2 guard AI), §1.1 / §9.4.4 (the lair grate), §9.1 (Ogre SLAM).
; Byte-exact reference for lp_post: tools/levelgen.py lp_post (tests/lp.py A7).
;
; Entries (far6; A and F are lost on the way back):
;   lp_post     lp_enter's unit loop (bank 3), a unit of the lair: its post.
;   (ai_guard: bank-7 boss7.asm since MEM-RECLAIM w2b)
;   (grate_open / boss_chk: bank-7 boss7.asm since MEM-RECLAIM w2b)
;==============================================================================
GUARD_R         EQU 31                      ; G2: the leash, |hero x - c| <= R: the whole storey (user 2026-11-02, was 8)
                ASSERT GUARD_R < 255                 ; boss7 .ab: cp GUARD_R + 1 must not wrap
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
                ld   a, AM_INK0                ; 3F-T11b (§9.9 A5): the Archmage's body ink at spawn = ORDER[0]'s
                ld   (kind_tab + KT_ATTR + K_ARCHMAGE), a   ; (P = 0; only a D8 body reads it)
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
.rngt:          ld   a, c                      ; (.gap's tail too: RECLAIM-D -1 B R6)
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
                jr   .rngt                     ; (A = x, BC popped; CF kept)
.gy:            ld   a, c
                pop  bc
                or   a
                ret
                ASSERT (LP_CMAP >> 8) == ((LP_CMAP + 2 * LP_CMW - 1) >> 8) && LP_XMAX + 1 < $80
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + 9 * RD_STRIDE - 1) >> 8) && FEAT_W == 3
