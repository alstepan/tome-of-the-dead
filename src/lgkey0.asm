;==============================================================================
; lgkey0.asm — LARGER-D T4: the level-key lock / key selection, part 2 of 2: the set
; enumeration and scoring (tools/levelgen.py select_keys consider() + the pick), and
; ktree0 (every BFS tree: uncontended code here, FARB0 through lgkey3's ktree).
; Bank-0 B0_CODE2 (main.asm): entered only by FARB0 ksel from bank-3 attempt
; (levelgen.asm step 5b, after lgkey3.asm kprep). B0_CODE2 rules: no SMC, no
; runtime-written bytes here (state: GEN_SCRATCH, layout + the "why masks" notes in
; lgkey3.asm), never pages $C000, calls nothing outside this file but low RAM (pathm0 is this
; bank's copy of lgkey3's pathm, the same macro; kbit / tstb / kins are low-RAM lgkeyl.asm). Draws NO rnd.
;
; ksel   In : kprep's output; LG_CNT (= n), LVL_DEPTH, LVL_START, LVL_LAIR,
;             LG_PASS (0 = pass 1, else pass 2 = final).
;        Out: B = 1: a set chosen, KS_RES (word) -> its record (KR_KEY0 / KR_KEY1 = key
;             room by colour, KR_CI0 / KR_CI1 = lock candidate index by colour, $FF =
;             none); B = 0: none (the caller runs pass 2 / Restarts). Clobbers all but IX, IY.
; Keys: the Python tuples are 8-byte strings compared by memcmp (smaller wins):
; $80 - score, $FF - F, 1 - nl, min pi, min e, max e, key colour 0, key colour 1.
; A 1-lock set runs with KC_L1 all $FF (max e = key 1 = $FF: constant within m = 1;
; rnd $FF keeps lock 0 colour 0; near / far $FF never the lair). 2 locks: KC_L0 is
; candidate i < j = KC_L1, so e0 < e1 (candidates are in edge order). Equal strings =
; equal results. Slots: 0 = 2 locks F >= floor, 1 = 1 lock F >= floor, 2 = 2 locks
; any, 3 = 1 lock any.
; Cost: ~3-6k T per tested set (worst ~40 sets a pass); ktree0 ~8k T a tree (contended data).
;==============================================================================
kcmp_tab:       DB   KL_RND, KC_PI, KC_E                          ; colour order (rnd, pi, e)
pathm0:         KPATHM kbit                                       ; (kbit / tstb: low RAM lgkeyl.asm, shared)

;------------------------------------------------------------------------------
; ktree0: A = source room (FARB0 via lgkey3 ktree). Its full BFS tree over RD_EXITS into KT_DIST / KT_PAR row
; 16 A (dist $FF = unseen, par $FF = the source), neighbours U, L, R, D (ascending
; id: the Python first-discoverer parents); KB_Q = the BFS order. Clobbers all but
; IX, IY. ~3.5k T (12 rooms, contended).
;------------------------------------------------------------------------------
ktree0:         ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                ld   e, a               ; E = row
                push ix
                ld   h, KT_DIST >> 8
                ld   l, e
                ld   b, GRID_CELLS
.f:             ld   (hl), $FF
                inc  l
                djnz .f
                ld   a, e
                add  a, c
                ld   l, a
                ld   (hl), b            ; dist = 0 (B = 0)
                inc  h
                ld   (hl), $FF          ; no parent
                ld   ix, KB_Q
                ld   (ix+0), c
                ld   a, (KB_Q & $FF) + 1
                ld   (KB_QT), a
.q:             ld   a, (KB_QT)
                cp   ixl
                jr   z, .done
                ld   b, (ix+0)          ; B = r
                inc  ix
                ld   a, b               ; C = its links (kexit inline)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC & $FF) + RD_EXITS
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   c, (hl)
                ld   a, e
                add  a, b
                ld   l, a
                ld   h, KT_DIST >> 8
                ld   d, (hl)
                inc  d                  ; D = dist[r] + 1
                ld   a, -GRID_W         ; U, L, R, D (unrolled: -0.1k T a room vs a table)
                bit  RDX_U_BIT, c
                call nz, .t
                ld   a, -1
                bit  RDX_L_BIT, c
                call nz, .t
                ld   a, 1
                bit  RDX_R_BIT, c
                call nz, .t
                ld   a, GRID_W
                bit  RDX_D_BIT, c
                call nz, .t
                jr   .q
.t:             add  a, b               ; A = neighbour delta
                add  a, e
                ld   l, a
                ld   h, KT_DIST >> 8
                ld   a, (hl)
                inc  a
                ret  nz                 ; seen
                ld   (hl), d
                inc  h
                ld   (hl), b            ; parent = r
                ld   a, l
                sub  e
                ld   hl, KB_QT
                ld   l, (hl)
                ld   (hl), a            ; enqueue
                ld   hl, KB_QT
                inc  (hl)
                ret
.done:          pop  ix
                ret

;------------------------------------------------------------------------------
; kp3: B = first key room, C = second ($FF: none). A = F of that collection order = the
; rooms on path(start, B) [u path(B, C)] u path(last, lair), each leg on its source's
; tree (Python _route_f's legs). Clobbers A, BC, DE, HL. ~2k T
;------------------------------------------------------------------------------
kp3:            ld   hl, 0
                ld   (KC_USED), hl
                push bc
                ld   c, b
                ld   a, (LVL_START)
                call pathm0
                pop  bc
                ld   a, c
                inc  a
                jr   z, .l
                push bc
                ld   a, b
                call pathm0
                pop  bc
                ld   b, c
.l:             ld   a, (LVL_LAIR)
                ld   c, a
                ld   a, b
                call pathm0
                ld   hl, (KC_USED)
                xor  a
                ld   b, 16
.pc:            add  hl, hl
                adc  a, 0
                djnz .pc
                ret

;------------------------------------------------------------------------------
; kcons: test the set KC_L0 .. (KC_M) (keys in KL_KEY; 1 lock: KC_L1 all $FF) =
; Python consider(); a valid set's record goes into the slots. Clobbers all but IX, IY.
; Closed form of _key_fix / the needed tests / _route_f (every key lies on its own
; lock's start side: kprep's best(X) pools are inside N): with Ka = key0 in N1,
; Kb = key1 in N0, n0 = near0 in N1, n1 = near1 in N0, L0 / L1 = lair in N0 / N1:
; round 1 opens lock 0 iff n0 & Ka (o0), lock 1 iff n1 & Kb (o1); the other opens in
; round 2 (its near and key are then reachable); valid iff o0 | o1, lock 0 needed iff
; not (o1 ? L0 : L0 & L1), lock 1 iff not (o0 ? L1 : L0 & L1); the order (0, 1) is
; valid iff Ka, (1, 0) iff Kb; b2 iff Ka & Kb. 1 lock (on P): always valid, needed,
; round 1, F = its one order. ~3-6k T.
;------------------------------------------------------------------------------
kcx:            pop  ix                 ; kcons' early exits (jr range)
                ret
kcons:          push ix
                ld   a, (KC_M)
                dec  a
                jr   nz, .two
                inc  a
                ld   (KC_L0 + KL_RND), a
                ld   a, (KC_L0 + KL_KEY)
                ld   b, a
                ld   c, $FF
                call kp3
                ld   (KC_F), a
                ld   c, 0               ; nl
                jp   .nl
.two:           ld   hl, (KC_L1 + KC_NLO)   ; D = L1 n0 Ka L0 n1 Kb (bits 5..0)
                ld   a, (LVL_LAIR)
                call .bit
                ld   a, (KC_L0 + KC_NEAR)
                call .bit
                ld   a, (KC_L0 + KL_KEY)
                call .bit
                ld   hl, (KC_L0 + KC_NLO)
                ld   a, (LVL_LAIR)
                call .bit
                ld   a, (KC_L1 + KC_NEAR)
                call .bit
                ld   a, (KC_L1 + KL_KEY)
                call .bit
                ld   e, 0               ; E bit 0 = o0, bit 1 = o1
                ld   a, d
                and  $18
                cp   $18
                jr   nz, .q0
                inc  e
.q0:            ld   a, d
                and  $03
                cp   $03
                jr   nz, .q1
                set  1, e
.q1:            ld   a, e
                or   a
                jp   z, kcx             ; no lock opens: the lair is out of reach (or a lock is not needed)
                ld   a, d
                and  $24
                cp   $24
                ld   b, a               ; Z(B == $24) = L0 & L1
                bit  1, e               ; lock 0 needed: walled, the reach is N0 (o1) / N0 & N1
                jr   z, .w0
                bit  2, d
                jp   nz, kcx
                jr   .w1
.w0:            ld   a, b
                cp   $24
                jp   z, kcx
.w1:            bit  0, e               ; lock 1 needed: N1 (o0) / N0 & N1
                jr   z, .w2
                bit  5, d
                jp   nz, kcx
                jr   .w3
.w2:            ld   a, b
                cp   $24
                jp   z, kcx
.w3:            ld   a, e               ; rounds: 1 if opened in round 1, else 2
                rrca
                ld   a, 2
                sbc  a, 0
                ld   (KC_L0 + KL_RND), a
                ld   a, e
                rrca
                rrca
                ld   a, 2
                sbc  a, 0
                ld   (KC_L1 + KL_RND), a
                ld   a, $FF             ; F = min over the valid orders
                ld   (KC_F), a
                push de
                bit  3, d
                ld   bc, (KC_L0 + KL_KEY)   ; (0, 1): C = key0, then key1
                ld   a, (KC_L1 + KL_KEY)
                ld   b, c
                ld   c, a
                call nz, .or2
                pop  de
                push de
                bit  0, d
                ld   a, (KC_L1 + KL_KEY)    ; (1, 0)
                ld   b, a
                ld   a, (KC_L0 + KL_KEY)
                ld   c, a
                call nz, .or2
                pop  de
                ld   c, 0               ; nl: one lock on P (b1), or Ka & Kb (b2)
                ld   a, (KC_L0 + KC_ONP)
                ld   hl, KC_L1 + KC_ONP
                xor  (hl)
                jr   nz, .nl1
                ld   a, d
                and  $09
                cp   $09
                jr   nz, .nl
.nl1:           inc  c
                jr   .nl
.or2:           call kp3                ; B, C = the order: KC_F = min(KC_F, F)
                ld   hl, KC_F
                cp   (hl)
                ret  nc
                ld   (hl), a
                ret
.bit:           call tstb               ; A = room, HL = mask: D = 2 D + (room in mask)
                add  a, $FF
                rl   d
                ret
.nl:            ld   a, (KC_F)          ; score = F + nl - LAIR_PEN (a lock on the lair door)
                add  a, c
                ld   b, a
                ld   a, (LVL_LAIR)
                ld   hl, KC_L0 + KC_NEAR
                cp   (hl)
                jr   z, .lp
                inc  l
                cp   (hl)
                jr   z, .lp
                ld   l, (KC_L1 & $FF) + KC_NEAR
                cp   (hl)
                jr   z, .lp
                inc  l
                cp   (hl)
                jr   nz, .ln
.lp:            dec  b
                dec  b
                ASSERT LAIR_PEN == 2
.ln:            ld   de, kcmp_tab       ; colour order: KC_L1 first iff (rnd, pi, e)1 < (rnd, pi, e)0
.cf:            ld   a, (de)
                inc  de
                add  a, KC_L0 & $FF
                ld   l, a
                ld   h, KC_L0 >> 8
                ld   a, (hl)
                set  4, l
                cp   (hl)
                jr   c, .ord            ; lock 0's smaller (e always differs: the loop ends)
                jr   z, .cf
                ld   a, $10
                jr   .o2
.ord:           xor  a
.o2:            ld   (KC_SW), a
                ld   hl, KC_REC
                ld   a, $80
                sub  b
                ld   (hl), a            ; $80 - score
                inc  l
                ld   a, (KC_F)
                cpl
                ld   (hl), a            ; $FF - F
                inc  l
                ld   a, 1
                sub  c
                ld   (hl), a            ; 1 - nl
                inc  l
                ld   a, (KC_L0 + KC_PI) ; min pi
                ld   bc, (KC_L1 + KC_PI)
                cp   c
                jr   c, .p1
                ld   a, c
.p1:            ld   (hl), a
                inc  l
                ld   a, (KC_L0 + KC_E)  ; min e, max e = e0, e1 (i < j; 1 lock: e1 = $FF)
                ld   (hl), a
                inc  l
                ld   a, (KC_L1 + KC_E)
                ld   (hl), a
                inc  l
                ld   a, (KC_SW)         ; key colour 0, key colour 1, candidate colour 0, 1
                add  a, (KC_L0 & $FF) + KL_KEY
                ld   e, a
                ld   d, KC_L0 >> 8
                call .kc
                inc  e
                inc  e
                call .kc
                ld   a, 4               ; slots: 2 locks (any) 2 / (ok) 0, 1 lock 3 / 1
                ld   hl, KC_M
                sub  (hl)
                push af
                call kins
                pop  af
                sub  2
                ld   b, a
                ld   a, (KC_F)
                ld   hl, KS_FLOOR
                cp   (hl)
                ld   a, b
                call nc, kins
.x:             pop  ix
                ret
.lair:          ld   a, (LVL_LAIR)
                jp   tstb
.kc:            ld   a, (de)            ; DE -> colour 0's byte: it, then colour 1's
                ld   (hl), a
                inc  l
                ld   a, e
                xor  $10
                ld   e, a
                ld   a, (de)
                ld   (hl), a
                inc  l
                ld   a, e
                xor  $10
                ld   e, a
                ret
                ASSERT ((KC_REC + KR_LEN) >> 8) == (KC_REC >> 8)

; kins / kload: LARGER-D T5 -> the low-RAM cold block (src/lgkeyl.asm: B0_CODE2 room; plain calls, GEN_SCRATCH only)

;==============================================================================
; ksel (see the header)
;==============================================================================
ksel:           push ix
                ld   hl, KS_BEST        ; slots empty
                ld   de, 12
                ld   b, 4
.se:            ld   (hl), $FF
                add  hl, de
                djnz .se
                ld   hl, KC_L1          ; 1 lock: KC_L1 = $FF
                ld   b, 16
.l1:            ld   (hl), $FF
                inc  l
                djnz .l1
                ld   a, (LG_CNT)
                sub  KEY_FMIN_SLACK
                ld   (KS_FLOOR), a
                ld   a, 1               ; 1 lock: kprep's KC_SK keys
                ld   (KC_M), a
                xor  a
.c1:            ld   (KS_I), a
                ld   hl, KS_NC
                cp   (hl)
                jr   z, .pairs
                add  a, a
                add  a, a
                add  a, a
                add  a, (KS_CAND & $FF) + KC_SK
                ld   l, a
                ld   h, KS_CAND >> 8
                ld   a, (hl)
                inc  a
                jr   z, .c1n
                dec  a
                ld   (KC_L0 + KL_KEY), a
                ld   a, (KS_I)
                ld   de, KC_L0
                call kload
                call kcons
.c1n:           ld   a, (KS_I)
                inc  a
                jr   .c1
.pairs:         ld   a, (LVL_DEPTH)     ; 2 locks: D4+ and n >= 11
                cp   KEY_PAIR_DEPTH
                jr   c, .pick
                ld   a, (LG_CNT)
                cp   KEY_PAIR_N
                jr   c, .pick
                ld   a, 2
                ld   (KC_M), a
                ld   hl, KS_PK
                ld   (KS_PKP), hl
                xor  a
.pi:            ld   (KS_I), a
.pj:            inc  a
                ld   (KS_J), a
                ld   hl, KS_NC
                cp   (hl)
                jr   nc, .pin
                ld   de, KC_L1
                call kload
                ld   a, (KS_I)
                ld   de, KC_L0
                call kload
                ld   hl, (KS_PKP)       ; lock i's 2 keys x lock j's 2 (kprep's KS_PK)
                ld   a, (hl)
                call .ta
                ld   hl, (KS_PKP)
                inc  hl
                ld   a, (hl)
                call .ta
                ld   hl, (KS_PKP)
                ld   de, 4
                add  hl, de
                ld   (KS_PKP), hl
                ld   a, (KS_J)
                jr   .pj
.pin:           ld   a, (KS_I)          ; HL = KS_NC: another i iff i + 2 < nc
                inc  a
                ld   b, a
                inc  a
                cp   (hl)
                ld   a, b
                jr   c, .pi
.pick:          ld   hl, KS_BEST        ; (2, ok), (1, ok), then pass 2: (2, any), (1, any)
                ld   de, 12
                ld   a, (LG_PASS)
                or   a
                ld   b, 2
                jr   z, .pk
                ld   b, 4
.pk:            ld   a, (hl)
                inc  a
                jr   nz, .got
                add  hl, de
                djnz .pk
                jr   .ret               ; B = 0: none
.got:           ld   (KS_RES), hl
                ld   b, 1
.ret:           pop  ix
                ret
.ta:            cp   $FF                ; A = lock i's key
                ret  z
                ld   (KC_L0 + KL_KEY), a
                ld   hl, (KS_PKP)
                inc  hl
                inc  hl
                ld   a, (hl)
                push hl
                call .tb
                pop  hl
                inc  hl
                ld   a, (hl)
.tb:            cp   $FF                ; A = lock j's key
                ret  z
                ld   hl, KC_L0 + KL_KEY
                cp   (hl)
                ret  z                  ; distinct rooms only
                ld   (KC_L1 + KL_KEY), a
                jp   kcons

; FLY-CUT: kload back from lowram lgkeyl.asm (ksel is its only caller; pure GEN_SCRATCH work, 19 B).
; kload: A = candidate index, DE = KC_L0 / KC_L1: its 8 B, KL_CI := index. Clobbers A, BC, DE, HL.
kload:          ld   hl, KL_CI
                add  hl, de
                ld   (hl), a
                add  a, a
                add  a, a
                add  a, a
                add  a, KS_CAND & $FF
                ld   l, a
                ld   h, KS_CAND >> 8
                ld   bc, 8
                ldir
                ret

