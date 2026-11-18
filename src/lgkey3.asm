;==============================================================================
; lgkey3.asm — LARGER-D T4: the level-key lock / key selection, part 1 of 2 (bank 3,
; INCLUDEd from bank3.asm after levelgen.asm; bank3.asm rules). Bit-exact port of
; tools/levelgen.py select_keys (larger_depths.md §2.1 rev 3) together with
; lgkey0.asm (bank-0 B0_CODE2: the set enumeration / scoring, FARB0 ksel). The split
; is by size (bank 3 + B0_CODE2 together; neither had room for both halves).
;
; ktrees In : G5a in RD_EXITS, LVL_START. Out: the start room's KT_DIST / KT_PAR row
;             (kneed builds the others on demand), KS_ALL, KS_SUB. Clobbers all but IX, IY.
; kprep  In : ktrees' output, LVL_LAIR, LG_CNT (= n), LVL_DEPTH.
;        Out: KS_ONP, KS_NT, KS_CAND / KS_NC (the lock candidates, KC_SK = 1-lock key),
;             KS_V, KS_PK (2-lock key candidates, D4+ n >= 11). Clobbers all but IX, IY.
;        Both draw NO rnd.  ~0.15M T together (12 trees ~10k T each, contended).
; lkside / lk_edge: levelgen's 5c filter / the lock edge bits (after ksel).
;
; Why masks (equivalent to the Python: a model of exactly this code matched
; select_keys over 3,000 generate() runs before the port): G is a tree + <= 1 loop
; edge and every lock is a bridge of it, so
;  * the rooms reachable from start with lock set U shut = ALL & N(u) for u in U
;    (N = a lock's start side): a far side is entered only over its own bridge, so
;    the far-side bolt never matters from start: the fixpoint / route reach tests
;    are mask ANDs, no BFS;
;  * a BFS in G minus shut bridges has the same parent tree (restricted) as the full
;    BFS from the same source: each room's full-G BFS tree is built once (KT_DIST /
;    KT_PAR row s = 16 s) and the route legs walk it;
;  * bestkey's BFS in G - e from e's near room equals the full one on the near side;
;  * pi: for an edge on P, the off-P rule (the P room nearest the near room) gives the
;    near room = the lower P index of the pair; two adjacent rooms on a shortest path
;    are consecutive on it (on P = both rooms on P).
;==============================================================================
KT_DIST         EQU GEN_SCRATCH + $100 ; rows of 16: row s = the BFS from room s
KT_PAR          EQU GEN_SCRATCH + $200
KT_ROW_TMP      EQU 12 * 16            ; the scratch row (bridge tests)
KB_Q            EQU GEN_SCRATCH + $310
KB_QT           EQU GEN_SCRATCH + $31F ; queue tail (low byte, KB_Q's page)
KS_CAND         EQU GEN_SCRATCH + $320 ; 8 x 8 B lock candidates
KS_BEST         EQU GEN_SCRATCH + $360 ; 4 slots x 12 B
KC_REC          EQU GEN_SCRATCH + $390 ; the record under test
KS_ALL          EQU GEN_SCRATCH + $3A0 ; word: present rooms
KS_ONP          EQU GEN_SCRATCH + $3A2 ; word: rooms on P (BFS path start -> lair)
KS_NC           EQU GEN_SCRATCH + $3A4 ; candidates
KS_FLOOR        EQU GEN_SCRATCH + $3A5 ; n - 4
KS_I            EQU GEN_SCRATCH + $3A6
KS_J            EQU GEN_SCRATCH + $3A7
KC_M            EQU GEN_SCRATCH + $3A8 ; 1 / 2 locks
KC_F            EQU GEN_SCRATCH + $3AC
KC_USED         EQU GEN_SCRATCH + $3B0 ; word
KS_BASE         EQU GEN_SCRATCH + $3E0 ; 12 B: room r's bestkey base (0 never, 1, 17 dead end)
KS_NT           EQU GEN_SCRATCH + $3BA ; 2 B: the start tree's non-tree edge (x < y), $FF none
KS_BUILT        EQU GEN_SCRATCH + $3BC ; word: rooms whose tree is built (kneed)
KS_PKP          EQU GEN_SCRATCH + $3B4 ; word: KS_PK pointer
KS_RES          EQU GEN_SCRATCH + $3B6 ; word: the chosen record
KC_SW           EQU GEN_SCRATCH + $3B8 ; 0 / $10: the colour-0 lock is KC_L0 / KC_L1
KC_L0           EQU GEN_SCRATCH + $3C0 ; the set under test: KC_L1 = KC_L0 | $10
KC_L1           EQU GEN_SCRATCH + $3D0
KS_SUB          EQU GEN_SCRATCH + $480 ; 12 words: room masks of the start tree's subtrees
KS_V            EQU GEN_SCRATCH + $500 ; 8 rows of 16: candidate i's bestkey value per room (0 = never:
                                       ; absent / start / lair; else dist from its near room + 1, + 16 dead end)
KS_PK           EQU GEN_SCRATCH + $400 ; 28 x 4 B: pair (i < j) in loop order: lock i's 2 key
                                       ; candidates, lock j's 2 ($FF none; a 2nd equal to the 1st is $FF)
; candidate record (KS_CAND + 8 i; the first 8 B of a KC_L*)
KC_E            EQU 0                  ; EDGE_TAB index
KC_NEAR         EQU 1                  ; the start-side room
KC_FAR          EQU 2
KC_ONP          EQU 3                  ; 1 = on P
KC_PI           EQU 4                  ; P index (its branch room's for an off-P lock)
KC_NLO          EQU 5                  ; word: the start side N
KC_NHI          EQU 6
KC_SK           EQU 7                  ; its 1-lock key = best(N) ($FF: off P / none)
KL_KEY          EQU 8                  ; KC_L* only: the key room under test
KL_RND          EQU 9                  ;   the fixpoint round it opened
KL_CI           EQU 10                 ;   its candidate index
; record (KC_REC / KS_BEST + 12 slot): the 8-B compare string, then
KR_KEY0         EQU 6
KR_KEY1         EQU 7
KR_CI0          EQU 8
KR_CI1          EQU 9
KR_LEN          EQU 10
LAIR_PEN        EQU 2                  ; tools/levelgen.py LAIR_PEN / NL_BONUS 1 / KEY_FMIN_SLACK
KEY_FMIN_SLACK  EQU 4
KEY_PAIR_DEPTH  EQU 4                  ; 2 locks: depth >= 4 and n >= 11
KEY_PAIR_N      EQU 11
KS_CMAX         EQU EDGES_H            ; <= 8 candidates (horizontal edges)
                ASSERT (KT_DIST & $FF) == 0 && (KT_PAR & $FF) == 0 && KT_ROW_TMP + 16 <= 256
                ASSERT (KC_L0 & $1F) == 0 && KC_L1 == KC_L0 + $10 && KL_CI < 16 && KC_FAR == KC_NEAR + 1
                ASSERT KS_V + KS_CMAX * 16 <= GEN_SCRATCH + GEN_SCRATCH_LEN && KS_CMAX * (KS_CMAX - 1) / 2 * 4 <= 112 && ROOM_SLOTS == 12 && GRID_CELLS == 12
                ASSERT ((KS_CAND + KS_CMAX * 8 - 1) >> 8) == (KS_CAND >> 8) && ((KS_BEST + 47) >> 8) == (KS_BEST >> 8)
                ASSERT (KB_Q >> 8) == (KB_QT >> 8) && KB_Q + GRID_CELLS <= KB_QT && ((KS_SUB + 23) >> 8) == (KS_SUB >> 8) && ((KS_BASE + 11) >> 8) == (KS_BASE >> 8) && KC_L1 + 16 <= KS_BASE && KS_PK + 112 <= KS_SUB
                ASSERT (LG_KR + 4) <= KT_DIST

; tstb: A = room, HL = mask. NZ = its bit is set. Keeps BC, DE, HL. ~110 T
    MACRO KTSTB kb
                push de
                ex   de, hl
                add  a, a
                add  a, kb & $FF
                ld   l, a
                ld   h, kb >> 8
                ld   a, (hl)
                and  e
                jr   nz, .y
                inc  l
                ld   a, (hl)
                and  d
.y:             ex   de, hl
                pop  de
                ret
    ENDM
; pathm: A = source room, C = target (in the source's tree). KC_USED |= the rooms on
; the tree path source .. target (both included). Clobbers A, BC, DE, HL. ~110 T a room
    MACRO KPATHM kb
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   b, a
                ld   de, (KC_USED)
.l:             ld   a, c
                add  a, a
                add  a, kb & $FF
                ld   l, a
                ld   h, kb >> 8
                ld   a, (hl)
                or   e
                ld   e, a
                inc  l
                ld   a, (hl)
                or   d
                ld   d, a
                ld   a, b
                add  a, c
                ld   l, a
                ld   h, KT_PAR >> 8
                ld   c, (hl)
                inc  c
                jr   z, .e
                dec  c
                jr   .l
.e:             ld   (KC_USED), de
                ret
    ENDM

; (kbit / tstb: one copy for both halves in low RAM, lgkeyl.asm; PKG5+FLY-CUT reclaim, were here and in lgkey0)
pathm:          KPATHM kbit

; kexit: A = room. A = RD_EXITS & $0F, HL -> RD_EXITS. Clobbers A, HL
kexit:          add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC & $FF) + RD_EXITS
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   a, (hl)
                and  $0F
                ret

; ktree: A = source room -> its full BFS tree (lgkey0.asm ktree0, bank 0: uncontended code,
; ~30 % faster than here, and bank 3 had no room). Out: KB_Q = the BFS order. Clobbers all but IX, IY.
ktree:          ld   hl, ktree0
                ld   c, BANK_TEXT
                jp   farb

; kbest: DE = a KS_V row, HL = room mask X. A = Python bestkey (the room of X, not start /
; lair, maximising (dead end, BFS distance from the lock's near room, -id): the
; largest nonzero V, the lowest id on ties); $FF = none. Clobbers A, BC, DE, HL. ~0.6k T
kbest:          ld   bc, $FF00          ; B = best room, C = best V (0 = none)
.l:             ld   a, h
                or   l
                jr   z, .x
                srl  h
                rr   l
                jr   nc, .n
                ld   a, (de)
                cp   c
                jr   c, .n
                jr   z, .n              ; strictly better only
                ld   c, a
                ld   a, e
                and  $0F
                ld   b, a
.n:             inc  e
                jr   .l
.x:             ld   a, b
                ret

; kbit2: HL = mask -> HL |= 1 << A. Clobbers A, DE
korb:           add  a, a
                add  a, kbit & $FF
                ld   e, a
                ld   d, kbit >> 8
                ld   a, (de)
                or   l
                ld   l, a
                inc  e
                ld   a, (de)
                or   h
                ld   h, a
                ret

;==============================================================================
; ktrees / kprep (see the header): ktrees before levelgen's lair (it reads the start
; tree's distances), kprep after it
;==============================================================================
ktrees:         ld   a, (LVL_START)     ; the start tree spans G: ALL (the other trees: kneed, lazily)
                call ktree
                ld   a, (LVL_START)
                ld   hl, 0
                call korb
                ld   (KS_BUILT), hl
                ld   a, (LVL_START)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   b, a               ; B = the start row
                xor  a                  ; subtrees: reverse BFS order (KB_Q, the start tree's
                ld   hl, KS_SUB         ; queue, still intact): SUB[v] |= bit v, SUB[par v] |= SUB[v]
                ld   c, 2 * GRID_CELLS
.zs:            ld   (hl), a
                inc  l
                dec  c
                jr   nz, .zs
                ld   hl, KB_QT
                ld   l, (hl)            ; HL -> past the last room dequeued
.sr:            dec  l
                ld   c, (hl)            ; C = v
                push hl
                ld   a, c
                add  a, a
                add  a, KS_SUB & $FF
                ld   l, a
                ld   h, KS_SUB >> 8
                ld   a, c
                add  a, a
                add  a, kbit & $FF
                ld   e, a
                ld   d, kbit >> 8
                ld   a, (de)
                or   (hl)
                ld   (hl), a
                inc  l
                inc  e
                ld   a, (de)
                or   (hl)
                ld   (hl), a
                ld   d, a
                dec  l
                ld   e, (hl)            ; DE = SUB[v]
                ld   a, b
                add  a, c
                ld   l, a
                ld   h, KT_PAR >> 8
                ld   a, (hl)            ; par v
                inc  a
                jr   z, .sx             ; the root
                dec  a
                add  a, a
                add  a, KS_SUB & $FF
                ld   l, a
                ld   h, KS_SUB >> 8
                ld   a, (hl)
                or   e
                ld   (hl), a
                inc  l
                ld   a, (hl)
                or   d
                ld   (hl), a
.sx:            pop  hl
                ld   a, l
                cp   KB_Q & $FF
                jr   nz, .sr
                ld   a, (LVL_START)
                add  a, a
                add  a, KS_SUB & $FF
                ld   l, a
                ld   h, KS_SUB >> 8
                ld   e, (hl)
                inc  l
                ld   d, (hl)
                ld   (KS_ALL), de       ; ALL = SUB[start] (G is connected)
                ret
                ASSERT ((KS_SUB + 2 * GRID_CELLS - 1) >> 8) == (KS_SUB >> 8) && ((kbit + 23) >> 8) == (kbit >> 8)

; kneed: A = room: its tree is built once (KS_BUILT). Keeps BC, DE, HL, IX.
kneed:          push bc
                push de
                push hl
                ld   c, a
                ld   hl, (KS_BUILT)
                call tstb
                jr   nz, .x
                ld   a, c
                call korb
                ld   (KS_BUILT), hl
                ld   a, c
                call ktree
.x:             pop  hl
                pop  de
                pop  bc
                ret

kprep:          push ix
                ld   hl, KS_PK
                ld   (KS_PKP), hl
                ld   hl, 0
                ld   (KC_USED), hl
                ld   a, (LVL_LAIR)
                ld   c, a
                ld   a, (LVL_START)
                call pathm
                ld   hl, (KC_USED)
                ld   (KS_ONP), hl       ; P = the start tree's path to the lair
                ; the start tree's non-tree edge (G5a = tree + <= 1 loop edge): KS_NT = (x, y), x < y
                ld   hl, $FFFF
                ld   (KS_NT), hl
                ld   c, 0
.nt:            ld   a, c
                call kexit
                ld   b, a
                ld   a, 1
                bit  RDX_R_BIT, b
                call nz, .ntt
                ld   a, GRID_W
                bit  RDX_D_BIT, b
                call nz, .ntt
                inc  c
                ld   a, c
                cp   GRID_CELLS
                jr   nz, .nt
                ; lock candidates: horizontal bridges (r, r+1), r ascending (= edge index order).
                ; A tree edge with child c is a bridge iff the non-tree edge has 0 or 2 ends in
                ; SUB[c]; its start side N = ALL & ~SUB[c]
                xor  a
                ld   (KS_NC), a
                ld   c, a
.cr:            ld   a, c
                call kexit
                and  RDX_R              ; (never set in the right column)
                jr   z, .cn
                ld   hl, (KS_NT)
                ld   a, l
                cp   c
                jr   nz, .nn
                ld   a, h
                sub  c
                dec  a
                jr   z, .cn             ; the non-tree edge itself (on the cycle)
.nn:
                ld   a, (LVL_START)     ; child = r + 1 iff par[r + 1] == r
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                ld   l, a
                ld   h, KT_PAR >> 8
                inc  l
                ld   a, (hl)
                cp   c
                ld   a, c
                jr   nz, .ch
                inc  a
.ch:            add  a, a               ; HL = SUB[child]
                add  a, KS_SUB & $FF
                ld   l, a
                ld   h, KS_SUB >> 8
                ld   e, (hl)
                inc  l
                ld   d, (hl)
                ex   de, hl
                ld   a, (KS_NT)         ; on the cycle: one end of the non-tree edge inside
                cp   $FF
                jr   z, .br
                call tstb
                ld   e, a
                ld   a, (KS_NT + 1)
                call tstb
                jr   z, .c0
                ld   a, e
                or   a
                jr   z, .cn
                jr   .br
.c0:            ld   a, e
                or   a
                jr   nz, .cn
.br:            ld   a, l               ; N = ALL & ~SUB
                cpl
                ld   e, a
                ld   a, h
                cpl
                ld   d, a
                ld   hl, (KS_ALL)
                ld   a, l
                and  e
                ld   l, a
                ld   a, h
                and  d
                ld   h, a
                call kcand
.cn:            inc  c
                ld   a, c
                cp   GRID_CELLS
                jr   nz, .cr
                ; KS_BASE[r] = 0 (absent / start / lair), 1, 17 (a dead end of G5a)
                ld   de, KS_BASE
                ld   c, 0
.b:             ld   a, c
                call kexit
                jr   z, .b0             ; absent
                ld   l, a
                dec  a
                and  l
                ld   a, 1
                jr   nz, .b1
                ld   a, 17
.b1:            ld   b, a
                ld   hl, LVL_START
                ld   a, c
                cp   (hl)
                jr   z, .b0
                inc  hl                 ; LVL_LAIR
                cp   (hl)
                ld   a, b
                jr   nz, .bw
.b0:            xor  a
.bw:            ld   (de), a
                inc  e
                inc  c
                ld   a, c
                cp   GRID_CELLS
                jr   nz, .b
                ; per candidate: its KS_V row (V = BASE + its near room's dist, 0 stays 0), then its
                ; 1-lock key (on P: best(N))
                ld   a, (KS_NC)
                or   a
                jp   z, .px
                ld   b, a
                ld   ix, KS_CAND
                ld   de, KS_V
.vc:            push bc
                ld   a, (ix+KC_NEAR)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   c, a               ; C = the near room's dist row
                ld   hl, KS_BASE
                ld   b, GRID_CELLS
.vr:            ld   a, (hl)
                or   a
                jr   z, .v2
                push hl
                ld   l, c
                ld   h, KT_DIST >> 8
                add  a, (hl)
                pop  hl
.v2:            ld   (de), a
                inc  e
                inc  l
                inc  c
                djnz .vr
                ld   a, e
                sub  GRID_CELLS
                ld   e, a               ; DE = this row (stride 16: kbest takes the room from E)
                ld   a, $FF
                bit  0, (ix+KC_ONP)
                ld   l, (ix+KC_NLO)
                ld   h, (ix+KC_NHI)
                push de
                call nz, kbest
                pop  de
                ld   (ix+KC_SK), a
                ld   a, e
                add  a, 16
                ld   e, a
                ld   bc, 8
                add  ix, bc
                pop  bc
                djnz .vc
                ASSERT LVL_LAIR == LVL_START + 1 && (KS_V & $FF) == 0 && KS_V + KS_CMAX * 16 <= $10000 && KS_CMAX * 16 <= 256
                ; 2-lock key candidates, pairs i < j in ksel's loop order
                ld   a, (LVL_DEPTH)
                cp   KEY_PAIR_DEPTH
                jr   c, .px
                ld   a, (LG_CNT)
                cp   KEY_PAIR_N
                jr   c, .px
                xor  a
.pi:            ld   (KS_I), a
.pj:            inc  a
                ld   (KS_J), a
                ld   hl, KS_NC
                cp   (hl)
                jr   nc, .pin
                call kcix               ; lock i: best(Ni & ~Nj), best(Ni & Nj)
                ld   e, (ix+KC_NLO)
                ld   d, (ix+KC_NHI)
                ld   a, (KS_I)
                call kcix
                call .keys
                ld   e, (ix+KC_NLO)     ; lock j: best(Nj & ~Ni), best(Nj & Ni)
                ld   d, (ix+KC_NHI)
                ld   a, (KS_J)
                call kcix
                call .keys
                ld   a, (KS_J)
                jr   .pj
.pin:           ld   a, (KS_I)          ; another i iff i + 2 < nc
                inc  a
                ld   b, a
                inc  a
                cp   (hl)
                ld   a, b
                jr   c, .pi
.px:            ld   hl, KS_CAND + KC_SK    ; the key rooms' trees (kp3's legs): SK, then PK
                ld   a, (KS_NC)
                or   a
                jr   z, .pz
                ld   b, a
.ks:            ld   a, (hl)
                call .kn
                ld   a, l
                add  a, 8
                ld   l, a
                djnz .ks
                ld   hl, KS_PK
.kp:            ld   de, (KS_PKP)       ; (KS_PK when no pair ran: set at the V loop)
                or   a
                sbc  hl, de
                add  hl, de
                jr   nc, .pz
                ld   a, (hl)
                call .kn
                inc  hl
                jr   .kp
.pz:            pop  ix
                ret
.kn:            cp   $FF
                ret  z
                jp   kneed
.ntt:           add  a, c               ; A = delta, C = r: (r, x) is the non-tree edge unless
                ld   e, a               ; par[x] == r or par[r] == x (start tree). Keeps BC
                ld   a, (LVL_START)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   d, a
                add  a, e
                ld   l, a
                ld   h, KT_PAR >> 8
                ld   a, (hl)
                cp   c
                ret  z
                ld   a, d
                add  a, c
                ld   l, a
                ld   a, (hl)
                cp   e
                ret  z
                ld   h, e
                ld   l, c
                ld   (KS_NT), hl
                ret
.vrow:          ld   a, ixl             ; IX = candidate i -> DE = its KS_V row
                sub  KS_CAND & $FF
                add  a, a
                add  a, KS_V & $FF
                ld   e, a
                ld   d, KS_V >> 8
                ret
.keys:          ; IX = lock, DE = the other's N: 2 B at (KS_PKP)++: best(N & ~DE), best(N & DE)
                push de                 ; (a 2nd equal to the 1st: $FF, the Python set)
                ld   a, e
                cpl
                and  (ix+KC_NLO)
                ld   l, a
                ld   a, d
                cpl
                and  (ix+KC_NHI)
                ld   h, a
                call .vrow
                call kbest
                pop  de
                ld   c, a
                ld   a, e
                and  (ix+KC_NLO)
                ld   l, a
                ld   a, d
                and  (ix+KC_NHI)
                ld   h, a
                push bc
                call .vrow
                call kbest
                pop  bc
                ld   hl, (KS_PKP)
                ld   (hl), c
                inc  hl
                cp   c
                jr   nz, .k2
                ld   a, $FF
.k2:            ld   (hl), a
                inc  hl
                ld   (KS_PKP), hl
                ret
; kcix: A = candidate index -> IX = its record. Clobbers A
kcix:           add  a, a
                add  a, a
                add  a, a
                add  a, KS_CAND & $FF
                ld   ixl, a
                ld   ixh, KS_CAND >> 8
                ret

;------------------------------------------------------------------------------
; kcand: C = r (the bridge (r, r+1)), HL = its start side N. Append the record
; (KC_E, KC_NEAR, KC_FAR, KC_ONP, KC_PI, N). Keeps C. Clobbers A, B, DE, HL, IX.
;------------------------------------------------------------------------------
kcand:          ld   a, (KS_NC)
                inc  a
                ld   (KS_NC), a
                dec  a
                call kcix
                ld   (ix+KC_NLO), l
                ld   (ix+KC_NHI), h
                ld   a, c
                call tstb               ; NZ: r is on the start side
                ld   d, c
                ld   e, c
                jr   z, .rf
                inc  e                  ; near r, far r + 1
                jr   .nf
.rf:            inc  d                  ; near r + 1, far r
.nf:            ld   (ix+KC_NEAR), d
                ld   (ix+KC_FAR), e
                ld   a, c               ; edge index = r - r div 3
                call hedge
                ld   (ix+KC_E), a
                ld   hl, (KS_ONP)       ; on P: both rooms on P
                ld   b, 0
                ld   a, c
                call tstb
                jr   z, .o
                ld   a, c
                inc  a
                call tstb
                jr   z, .o
                inc  b
.o:             ld   (ix+KC_ONP), b
                ld   a, d               ; the near room's tree (pi, then its KS_V row)
                call kneed
                ld   b, $FF             ; pi = dS[p], p on P minimising (dist from near, dS[p]):
                ld   a, (LVL_LAIR)      ; P walked lair -> start on the start tree (an on-P edge: p = near)
.op:            ld   e, a               ; E = p
                ld   a, d
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e
                ld   l, a
                ld   h, KT_DIST >> 8
                ld   a, (hl)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   h, a
                ld   a, (LVL_START)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e
                ld   l, a
                ld   a, h
                ld   h, KT_DIST >> 8
                or   (hl)               ; (dist << 4) | dS[p]
                cp   b
                jr   nc, .on
                ld   b, a
.on:            inc  h                  ; KT_PAR, the same L: p's parent
                ld   a, (hl)
                cp   $FF
                jr   nz, .op
                ld   a, b
                and  $0F
                ld   (ix+KC_PI), a
                ret

; hedge: A = r (with a right neighbour) -> A = its EDGE_TAB index r - r div 3. Clobbers HL
hedge:          ld   hl, hedge_tab
                jp   idx

;------------------------------------------------------------------------------
; lkside: C = room, LG_BIT = RDX_R / RDX_D (its pair). Z = both rooms on the same side
; of every chosen lock (LG_KR + 2 / + 3: candidate index, $FF none). Keeps BC, DE.
; lk_edge: A = lock candidate index ($FF: none), C = bits: EDGE_TAB[its KC_E] |= C.
;------------------------------------------------------------------------------
lkside:         push bc
                push de
                ld   a, (LG_BIT)
                cp   RDX_D
                ld   a, c
                jr   nz, .r
                inc  a
                inc  a
.r:             inc  a
                ld   b, a               ; B = the other room
                ld   a, (LG_KR + 2)
                call .one
                jr   nz, .x
                ld   a, (LG_KR + 3)
                call .one
.x:             pop  de
                pop  bc
                ret
.one:           call kcrec
                ret  z                  ; none: the same side
                ld   e, (hl)
                inc  l
                ld   h, (hl)
                ld   l, e               ; HL = the lock's start side
                ld   a, c
                call tstb
                ld   e, 0
                jr   z, .a
                inc  e
.a:             ld   a, b
                call tstb
                ld   a, 0
                jr   z, .b
                inc  a
.b:             xor  e
                ret
kcrec:          cp   $FF                ; A = candidate index: HL -> its KC_NLO; Z = none
                ret  z
                add  a, a
                add  a, a
                add  a, a
                add  a, (KS_CAND & $FF) + KC_NLO
                ld   l, a
                ld   h, KS_CAND >> 8
                or   1                  ; NZ (the add never gives 0 here: KS_CAND low byte $20)
                ret
lk_edge:        call kcrec
                ret  z
                dec  l
                dec  l
                dec  l
                dec  l                  ; -> KC_NEAR
                ld   a, (hl)
                inc  l
                cp   (hl)               ; near - far: CF = the near room is the left one
                jr   c, .l
                set  EG_NEARR_BIT, c    ; LARGER-D T8: hero_door's far-side bolt reads it
.l:             dec  l
                dec  l                  ; -> KC_E
                ld   a, (hl)
                ld   hl, EDGE_TAB
                call hla
                ld   a, (hl)
                or   c
                ld   (hl), a
                ret
                ASSERT KC_NLO == 5 && KC_E == 0 && KC_NEAR == 1 && KC_FAR == 2 && (KS_CAND & $FF) == $20
