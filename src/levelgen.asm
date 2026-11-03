;==============================================================================
; levelgen.asm — B3B-7: Z80 level generator, bit-exact port of tools/levelgen.py
; (that file's header documents GEN_RNG and the exact rnd() call order; every
; routine below keeps that order). INCLUDEd from bank3.asm (cold code, bank 3
; paged at $C000, entered through far3 only).
;
; level_gen      In : A = depth 1..8; LVL_SEED / MASTER_SEED already set.
;                Out: block at LVL_STATE == levelgen.generate(depth, seed, master);
;                     LVL_SEED = seed actually used. B = 0 ok; B = 1 + CF = failed:
;                     16 reseeds exhausted, LVL_SEED left at seed + 16. With the L1
;                     level shape the lair always exists (no lair reseeds) and
;                     tools/levelgen_runs.py finds 0 failing seeds at every depth;
;                     level_new (bank3.asm) still retries from seed + 16.
;                     The reseed path is therefore unreachable under L1; it stays
;                     as a cheap guard (bit-exact with tools/levelgen.py).
;                     Clobbers all but IY, SP (far3 itself clobbers A/F on return).
; level_start_x  In : block generated.  Out: A = B = hero start col (storey 0).
;
; Scratch: LG_* below, in GEN_SCRATCH (= ROOM_MAP + NEXT_MAP, $6000..$6066).
; CONTRACT: call only before build_room_map / never mid-room (ROOM_MAP, NEXT_MAP
; and the ZX0 frame cache all live there). level_gen zeroes GEN_ZBLK on entry
; (cache invalidation); the caller re-runs alloc_* + gen_kind afterwards.
; Stack use <= ~16 B.
; No DI, no port writes. restart/reseed unwind with SP = LG_SP (set in attempt).
;
; Room desc pointer: rdp (page-aligned ROOM_DESC, L = $60 + 16 r). The adjacency
; of the DFS tree lives in RD_EXITS bits 0-3 (L,R,U,D == RDX_L/R/U/D), which is
; exactly what the exits end up as. The visited set is RDF_PRESENT.
;==============================================================================
LG_STK          EQU GEN_SCRATCH + 0     ; 9 B DFS stack
LG_DIST         EQU GEN_SCRATCH + 16    ; 9 B BFS distance (FF = unseen)
LG_Q            EQU GEN_SCRATCH + 32    ; 9 B BFS queue (page-contained: ixl compare)
LG_CAND         EQU GEN_SCRATCH + 48    ; 9 B potion room candidates
LG_N            EQU GEN_SCRATCH + 64    ; target room count
LG_CNT          EQU GEN_SCRATCH + 65    ; visited count
LG_CUR          EQU GEN_SCRATCH + 66
LG_RID          EQU GEN_SCRATCH + 67    ; picked room / neighbour id
LG_RBIT         EQU GEN_SCRATCH + 68    ; picked direction bit
LG_BIT          EQU GEN_SCRATCH + 69
LG_TRY          EQU GEN_SCRATCH + 70
LG_RES          EQU GEN_SCRATCH + 71    ; reseeds left
LG_QN           EQU GEN_SCRATCH + 72
LG_NC           EQU GEN_SCRATCH + 73    ; potion candidates
LG_PT           EQU GEN_SCRATCH + 74    ; potions to place
LG_K            EQU GEN_SCRATCH + 75
LG_X            EQU GEN_SCRATCH + 76
LG_RST          EQU GEN_SCRATCH + 77    ; restarts left this seed
LG_SP           EQU GEN_SCRATCH + 78    ; word
LG_S            EQU GEN_SCRATCH + 80    ; D8 reserved Sanctum cell (never visited), $FF = none
LG_LS           EQU GEN_SCRATCH + 81    ; first row-major cell scanned by loopc (6 = mandatory bottom edge)
LG_RNG0         EQU GEN_SCRATCH + 82    ; word: GEN_RNG before the L2 pass (restored after it)
LG_ODDS         EQU GEN_SCRATCH + 84    ; 2 B: odds wide, mid-block (1 in N)
LG_C1           EQU GEN_SCRATCH + 87    ; the room's two ladders, c1 < c2
LG_C2           EQU GEN_SCRATCH + 88
LG_P            EQU GEN_SCRATCH + 89    ; candidate p (wide pit) / b (mid-block)
LG_W            EQU GEN_SCRATCH + 90    ; candidate W / w
LG_NW           EQU GEN_SCRATCH + 91    ; wide pits placed
LG_NB           EQU GEN_SCRATCH + 92    ; mid-blocks placed (LG_NW + kind)
LG_K2           EQU GEN_SCRATCH + 93    ; kind: 0 wide, 1 mid
LG_NL           EQU GEN_SCRATCH + 94    ; the 2nd ladder added this try (0 = none)
LG_KP           EQU GEN_SCRATCH + 95    ; 7 B: the l2_kind_tab entry
LG_SVP          EQU GEN_SCRATCH + 102   ; the narrow pit col removed while trying
; L2 descriptor fields L2_PITW / L2_MIDB / L2_MIDW: level_defs.asm
L2_MAX          EQU 2                   ; per feature per level
RESEED_MAX      EQU 16
                                        ; F3_GEN (defs.asm, P3: default 1) == tools/levelgen.py generate(..., f3=True)
DOOR_ODDS       EQU 3
PIT_COL_MIN     EQU 5
PIT_COL_MAX     EQU 24
MAX_RESTARTS    EQU 64
SHAFT_MIN       EQU 5
SHAFT_N         EQU 20
LG_ROOMS_END    EQU (ROOM_DESC + GRID_CELLS * RD_STRIDE) & $FF
                ASSERT (LG_Q >> 8) == ((LG_Q + 9) >> 8) && (LG_STK >> 8) == ((LG_X + 1) >> 8)
                ASSERT RD_FLAGS == 0 && RD_EXITS == 1 && RDF_PRESENT == 1 && RDX_R == 2 && RDX_D == 8
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + 16 * 8 + 15) >> 8)

;------------------------------------------------------------------------------
; helpers (all preserve BC, DE unless noted)
;------------------------------------------------------------------------------
lg_step           EQU gen_step         ; MEM-RECLAIM w3: bank-2 gen_step (xorshift 7,9,8 -> HL, stored in GEN_RNG)
rnd:                                    ; A = n -> A = (x & $FF) mod n. Clobbers A, HL, F
                push bc                 ; n = 1 / 2 fast paths (most calls): exact, no loop
                ld   c, a
                call lg_step
rnd_mod:                                ; RECLAIM-D: decor_gen dg_rnd's tail (C = n, HL = the
                ld   a, c               ; step, BC pushed): A = L mod n, BC popped
                dec  a
                jr   z, .z
                dec  a
                jr   nz, .g
                ld   a, l
                and  1
                pop  bc
                ret
.z:             pop  bc                 ; A = 0
                ret
.g:             ld   a, l
.m:             sub  c
                jr   nc, .m
                add  a, c
                pop  bc
                ret
hla:            add  a, l               ; HL += A
                ld   l, a
                ret  nc
                inc  h
                ret
idx:            call hla                ; A = (HL + A)
                ld   a, (hl)
                ret
; gq_qtab — GEAR2 q table (items_ovl.asm q pass; model q_roll / q_to_qty): FL_QTY - 1 = q & 7 by
; s = rnd(8) + ((depth + 1) >> 2), q = -1 + (s >= Q_T0) + (s >= Q_T1) + (s >= Q_T2): s 0..9 ->
; 7 7 0 0 0 0 1 1 2 2 (FL_QTY 8 8 1 1 1 1 2 2 3 3) with the knobs 2 / 6 / 8 (tools/items_model.py Q_T0..Q_T2). In bank 3 (10 B of the
; ledger's spare) because the stored overlay image had no room (bank 1).
Q_T0            EQU 2
Q_T1            EQU 6
Q_T2            EQU 8
gq_qtab:
                DUP  10, k                     ; k = s = 0..9 (sjasmplus: a true comparison is -1)
                DB   (-1 - ((k >= Q_T0) + (k >= Q_T1) + (k >= Q_T2))) & 7
                EDUP
rdp:            add  a, a               ; A = room id -> HL = &ROOM_DESC[id]
                add  a, a
                add  a, a
                add  a, a
                add  a, ROOM_DESC & $FF
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ret
ispres:         call rdp                ; Z = room absent
                bit  0, (hl)
                ret
setpres:        call rdp
                set  0, (hl)
                ret
addexit:        call rdp                ; A = room, C = exit bits to OR in
                inc  hl
                ld   a, (hl)
                or   c
                ld   (hl), a
                ret
opp:            ld   h, a               ; opposite direction bit (1<->2, 4<->8)
                and  5
                ld   a, h
                jr   z, .r
                rlca
                ret
.r:             rrca
                ret
lg_restart:     ld   sp, (LG_SP)
                ld   a, 1
                ret
lg_reseed:      ld   sp, (LG_SP)
                ld   a, 2
                ret

; valid_tab[r]: grid-edge bits L,R,U,D that exist for cell r
valid_tab:      DB   $0A, $0B, $09, $0E, $0F, $0D, $06, $07, $05
dir_tab:        DB   RDX_L, $FF, RDX_R, 1, RDX_U, -3, RDX_D, 3, 0   ; (bit, delta), L,R,U,D
hedge_tab:      DB   0, 1, 0, 2, 3, 0, 4, 5, 0
attr_tab:       DB   $0F, $01, $27, $04, $17, $02, $28, $05, $30, $06, $38, $07, $4F, $41, $1F, $03

; dfs_done: Z = DFS finished: |visited| >= n and cell 7 and (6 or 8) visited
dfs_done:       ld   a, (LG_CNT)
                ld   hl, LG_N
                cp   (hl)
                jr   c, .no
                ld   a, 7
                call ispres
                jr   z, .no
                ld   a, 6
                call ispres
                jr   nz, .yes
                ld   a, 8
                call ispres
                jr   z, .no
.yes:           xor  a
                ret
.no:            or   1
                ret

; nbrs_free: In A = cell, B = want. Out A = number of unvisited grid neighbours;
; LG_RID/LG_RBIT = neighbour #want (L,R,U,D order).
nbrs_free:      ld   (LG_CUR), a
                ld   hl, valid_tab
                call idx
                ld   c, a
                ld   hl, dir_tab
                ld   d, 0
.l:             ld   a, (hl)
                or   a
                jr   z, .end
                inc  hl
                ld   e, (hl)
                inc  hl
                ld   (LG_BIT), a
                and  c
                jr   z, .l
                ld   a, (LG_CUR)
                add  a, e
                ld   e, a
                ld   a, (LG_S)          ; L1: the reserved Sanctum cell is never entered
                cp   e
                jr   z, .l
                ld   a, e
                push hl
                call ispres
                pop  hl
                jr   nz, .l
                ld   a, d
                cp   b
                jr   nz, .n
                ld   a, e
                ld   (LG_RID), a
                ld   a, (LG_BIT)
                ld   (LG_RBIT), a
.n:             inc  d
                jr   .l
.end:           ld   a, d
                ret

; loopc: In B = want. Out A = number of loop-edge candidates (r right/down
; present, not yet linked, r ascending, right before down); LG_RID/LG_RBIT = #want.
loopc:          ld   d, 0
                ld   a, (LG_LS)
                ld   c, a
.r:             ld   a, c
                call ispres
                jr   z, .nr
                ld   hl, valid_tab
                ld   a, c
                call idx
                ld   e, a
                ld   a, RDX_R
                call .cand
                ld   a, RDX_D
                call .cand
.nr:            inc  c
                ld   a, c
                cp   9
                jr   nz, .r
                ld   a, d
                ret
.cand:          ld   (LG_BIT), a
                and  e
                ret  z
                cp   RDX_D
                ld   a, c
                jr   nz, .d1
                inc  a
                inc  a
.d1:            inc  a
                call ispres
                ret  z
                ld   a, c
                call rdp
                inc  hl
                ld   a, (LG_BIT)
                and  (hl)
                ret  nz
                ld   a, d
                cp   b
                jr   nz, .n
                ld   a, c
                ld   (LG_RID), a
                ld   a, (LG_BIT)
                ld   (LG_RBIT), a
.n:             inc  d
                ret

; bfs: distances from LVL_START over the RD_EXITS adjacency -> LG_DIST
bfs:            ld   hl, LG_DIST
                ld   de, LG_DIST + 1
                ld   bc, 8
                ld   (hl), $FF
                ldir
                ld   a, (LVL_START)
                ld   (LG_Q), a
                ld   hl, LG_DIST
                call hla
                ld   (hl), 0
                ld   a, 1
                ld   (LG_QN), a
                ld   ix, LG_Q
.q:             ld   a, ixl
                sub  LG_Q & $FF
                ld   hl, LG_QN
                cp   (hl)
                ret  z
                ld   b, (ix+0)
                inc  ix
                ld   a, b
                call rdp
                inc  hl
                ld   c, (hl)
                ld   hl, LG_DIST
                ld   a, b
                call hla
                ld   d, (hl)
                inc  d
                ld   hl, dir_tab
.d:             ld   a, (hl)
                or   a
                jr   z, .q
                inc  hl
                ld   e, (hl)
                inc  hl
                and  c
                jr   z, .d
                push hl
                ld   a, b
                add  a, e
                ld   e, a
                ld   hl, LG_DIST
                call hla
                ld   a, (hl)
                inc  a
                jr   nz, .s
                ld   (hl), d
                ld   a, (LG_QN)
                ld   hl, LG_Q
                call hla
                ld   (hl), e
                ld   hl, LG_QN
                inc  (hl)
.s:             pop  hl
                jr   .d

; sanct: In C = room. CF = D8 Sanctum rule ok (a free horizontal neighbour cell)
sanct:          ld   hl, valid_tab
                ld   a, c
                call idx
                ld   (LG_X), a
                and  RDX_L
                jr   z, .r
                ld   a, c
                dec  a
                call ispres
                jr   z, .ok
.r:             ld   a, (LG_X)
                and  RDX_R
                jr   z, .f
                ld   a, c
                inc  a
                call ispres
                jr   nz, .f
.ok:            scf
                ret
.f:             or   a
                ret

; lair: farthest non-start room with a horizontal exit (leaf tier first), lowest
; id on ties; none -> reseed. Sets LVL_LAIR.
lair:           ld   e, 1
.pass:          ld   d, $FF
                ld   b, 0
                ld   c, 6               ; L1: bottom row only (never the start)
.r:             ld   a, c
                call rdp
                bit  0, (hl)
                jr   z, .nx
                inc  hl
                ld   a, (hl)
                ld   (LG_X), a
                and  RDX_L | RDX_R
                jr   z, .nx
                ld   a, e
                or   a
                jr   z, .nl
                ld   a, (LG_X)
                and  $0F
                ld   l, a
                dec  a
                and  l
                jr   nz, .nx
.nl:            ld   a, (LVL_DEPTH)
                cp   8
                jr   nz, .ok
                call sanct
                jr   nc, .nx
.ok:            ld   hl, LG_DIST
                ld   a, c
                call hla
                ld   a, (hl)
                cp   b
                jr   c, .nx
                jr   z, .nx
                ld   b, a
                ld   d, c
.nx:            inc  c
                ld   a, c
                cp   9
                jr   nz, .r
                ld   a, d
                inc  a
                jr   nz, .found
                ld   a, e
                or   a
                jp   z, lg_reseed
                ld   e, 0
                jr   .pass
.found:         dec  a
                ld   (LVL_LAIR), a
                ret

; legal: In A = col, B = mask (bit k-2 <-> RD offset k), IX = room.
; CF = illegal (|col - f| < FEAT_GAP for a footprint f in the mask). Preserves BC;
; the col is left in LG_X. s0 mask $75 (up,arr,lad1,lad2,pit), s1 $3A (dn,exit,lad1,lad2).
legal:          ld   (LG_X), a
                push bc
                ld   c, a
                push ix
                pop  hl
                inc  hl
                inc  hl
.l:             srl  b
                jr   nc, .n
                ld   a, (hl)
                or   a
                jr   z, .n
                sub  c
                jr   nc, .p
                neg
.p:             cp   FEAT_GAP
                jr   c, .bad
.n:             inc  hl
                ld   a, b
                or   a
                jr   nz, .l
                pop  bc
                or   a
                ret
.bad:           pop  bc
                scf
                ret

; pick_opt: In IX = room, B = mask, D = lo, E = hi. Out A = col or 0 (dropped)
pick_opt:       ld   a, FEAT_TRIES
                ld   (LG_TRY), a
.t:             ld   a, e
                sub  d
                inc  a
                call rnd
                add  a, d
                call legal
                jr   c, .no
                ld   a, (LG_X)
                ret
.no:            ld   hl, LG_TRY
                dec  (hl)
                jr   nz, .t
                xor  a
                ret
; pick_man: as pick_opt, then the first legal col lo..hi; none -> restart
pick_man:       call pick_opt
                or   a
                ret  nz
                ld   a, d
.s:             call legal
                jr   nc, .ok
                ld   a, (LG_X)
                cp   e
                jp   z, lg_restart
                inc  a
                jr   .s
.ok:            ld   a, (LG_X)
                ret

; hits: In IX = room, C = storey, D = lo, E = hi. CF = a storey-C footprint
; (f..f+2), the pit (p-1..p+3, storey 0) or the storey-C block overlaps cols
; lo..hi. Preserves BC. hits_x ignores the arrival shaft (start_x).
hits_x:         push bc
                ld   b, $31
                jr   hits_m
hits:           push bc
                ld   b, $35
                ld   a, c
                or   a
                jr   z, hits_m
                ld   b, $3A
hits_m:         push ix
                pop  hl
                inc  hl
                inc  hl
.l:             srl  b
                jr   nc, .n
                ld   a, (hl)
                or   a
                jr   z, .n
                cp   e
                jr   z, .a
                jr   nc, .n
.a:             add  a, 2
                cp   d
                jr   nc, .hit
.n:             inc  hl
                ld   a, b
                or   a
                jr   nz, .l
                ld   a, c
                or   a
                jr   nz, .blk
                ld   a, (ix+RD_PITCOL)
                or   a
                jr   z, .blk
                dec  a
                cp   e
                jr   z, .p
                jr   nc, .blk
.p:             add  a, 4
                cp   d
                jr   nc, .hit
.blk:           ld   a, (ix+RD_BLOCK)
                or   a
                jr   z, .no
                ld   b, a
                rlca
                rlca
                and  1
                cp   c
                jr   nz, .no
                ld   a, b
                and  RDB_WMASK
                ld   h, a
                bit  7, b
                jr   nz, .right
                ld   a, h
                cp   d
                jr   nc, .hit
                jr   .no
.right:         ld   a, e
                add  a, h
                cp   31
                jr   nc, .hit
.no:            pop  bc
                or   a
                ret
.hit:           pop  bc
                scf
                ret

; block_try: IX = room (after its 'try a block' roll succeeded)
block_try:      bit  1, (ix+RD_FLAGS)
                ret  nz
                bit  2, (ix+RD_FLAGS)
                ret  nz
                ld   a, FEAT_TRIES
                ld   (LG_TRY), a
.t:             ld   a, 2
                call rnd
                rrca
                ld   b, a               ; side << 7
                ld   a, 2
                call rnd
                ld   c, a               ; storey
                rrca
                rrca
                or   b
                ld   b, a
                ld   a, 2
                call rnd
                add  a, 2               ; width
                or   b
                ld   b, a               ; block byte
                rlca
                and  1
                inc  a                  ; RDX_L / RDX_R of that side
                and  (ix+RD_EXITS)
                jr   nz, .next
                ld   a, b
                and  RDB_WMASK
                ld   e, a               ; w
                ld   a, (ix+RD_PITCOL)
                or   a
                jr   z, .np
                bit  7, b               ; game.md 1.1 pit geometry (3)/(4): left needs
                jr   nz, .rp            ; p >= w+4, right needs p <= 25-w
                sub  e
                cp   4
                jr   c, .next
                jr   .np
.rp:            add  a, e
                cp   26
                jr   nc, .next
.np:            ld   d, 0
                bit  7, b
                jr   z, .go
                ld   a, 31
                sub  e
                ld   d, a
                ld   e, 31
.go:            call hits
                jr   c, .next
                ld   (ix+RD_BLOCK), b
                ret
.next:          ld   hl, LG_TRY
                dec  (hl)
                jr   nz, .t
                ret

;==============================================================================
; attempt: one generation attempt. Out A = 0 ok, 1 restart, 2 reseed.
;==============================================================================
attempt:        ld   (LG_SP), sp
                ld   hl, EDGE_TAB
                ld   de, EDGE_TAB + 1
                ld   bc, LVL_STATE_END - EDGE_TAB - 1
                ld   (hl), 0
                ldir
                ld   hl, FLOOR_LIST
                ld   de, FLOOR_LIST + 1
                ld   bc, FLOOR_MAX * FL_STRIDE - 1
                ld   (hl), FL_EMPTY
                ldir
                xor  a
                ld   (FLOOR_N), a
                ; 1. room count, start
                ld   a, 3
                call rnd
                add  a, ROOMS_MIN
                ld   (LG_N), a
                ld   a, 3               ; L1: start on the top grid row
                call rnd
                ld   (LVL_START), a
                ld   a, $FF
                ld   (LG_S), a
                ld   a, (LVL_DEPTH)
                cp   8
                jr   nz, .nos
                ld   a, (LG_N)          ; D8: n = min(n, 8), Sanctum cell S = 6 + 2 rnd(2)
                cp   9
                jr   nz, .n8
                dec  a
                ld   (LG_N), a
.n8:            ld   a, 2
                call rnd
                add  a, a
                add  a, 6
                ld   (LG_S), a
.nos:           ld   a, (LVL_START)
                ; 2. DFS
                call setpres
                ld   a, 1
                ld   (LG_CNT), a
                ld   ix, LG_STK
                ld   a, (LVL_START)
                ld   (ix+0), a
.dfs:           call dfs_done           ; n rooms AND two adjacent bottom cells
                jr   z, .dfsd
                ld   a, (ix+0)
                ld   b, $FF
                call nbrs_free
                or   a
                jr   nz, .pk
                dec  ix
                jr   .dfs
.pk:            call rnd
                ld   b, a
                ld   a, (ix+0)
                call nbrs_free
                ld   a, (LG_RBIT)
                ld   c, a
                ld   a, (ix+0)
                call addexit
                ld   a, c
                call opp
                ld   c, a
                ld   a, (LG_RID)
                ld   b, a
                call addexit
                ld   a, b
                call setpres
                inc  ix
                ld   (ix+0), b
                ld   hl, LG_CNT
                inc  (hl)
                jr   .dfs
.dfsd:          ; 3. loop edge: mandatory (bottom pairs only, no roll) when no tree
                ; edge joins 6-7 / 7-8
                ld   a, 6
                call rdp
                inc  hl
                ld   b, (hl)
                ld   a, 7
                call rdp
                inc  hl
                ld   a, (hl)
                or   b
                and  RDX_R
                ld   a, 6
                jr   z, .mand
                ld   a, 2
                call rnd
                or   a
                jr   nz, .noloop
                xor  a
.mand:          ld   (LG_LS), a
                ld   b, $FF
                call loopc
                or   a
                jr   z, .noloop
                call rnd
                ld   b, a
                call loopc
                ld   a, (LG_RBIT)
                ld   c, a
                ld   a, (LG_RID)
                ld   b, a
                call addexit
                ld   a, c
                call opp
                ld   c, a
                ld   a, b
                inc  a
                bit  0, c
                jr   nz, .o
                inc  a
                inc  a
.o:             call addexit
.noloop:        ; 4. horizontal edges
                ld   d, 0
.he:            ld   a, d
                call rdp
                inc  hl
                bit  1, (hl)
                jr   z, .hn
                ld   a, 2
                call rnd
                ld   b, a
                ld   a, DOOR_ODDS
                call rnd
                ld   c, EG_LINK
                or   a
                jr   nz, .nd
                ld   c, EG_LINK | EG_DOOR
.nd:            ld   hl, hedge_tab
                ld   a, d
                call idx
                ld   hl, EDGE_TAB
                call hla
                ld   (hl), c
                ld   a, b
                or   a
                jr   z, .hn
                ld   a, d
                call rdp
                inc  hl
                set  5, (hl)
                ld   a, d
                inc  a
                call rdp
                inc  hl
                set  4, (hl)
.hn:            inc  d
                ld   a, d
                cp   9
                jr   nz, .he
                ; 5. vertical links (col stored as DNCOL of r and UPCOL of r+3)
                ld   b, 0
.ve:            ld   a, b
                call rdp
                inc  hl
                bit  3, (hl)
                jr   z, .vn
                ld   a, SHAFT_N
                call rnd
                add  a, SHAFT_MIN
                ld   c, a
                ld   a, b
                call rdp
                inc  hl
                inc  hl
                inc  hl
                ld   (hl), c            ; RD_DNCOL
                ld   a, b
                add  a, 3
                call rdp
                inc  hl
                inc  hl
                ld   (hl), c            ; RD_UPCOL
.vn:            inc  b
                ld   a, b
                cp   6
                jr   nz, .ve
                ; 6. BFS, lair, flags
                call bfs
                call lair
                ld   a, (LVL_START)
                call rdp
                set  1, (hl)
                ld   a, (LVL_LAIR)
                call rdp
                set  2, (hl)
                ld   ix, ROOM_DESC
.fl:            bit  0, (ix+RD_FLAGS)
                jr   z, .fn
                ld   a, (ix+RD_EXITS)
                and  $0F
                ld   b, a
                dec  a
                and  b
                jr   nz, .fn
                set  3, (ix+RD_FLAGS)   ; RDF_DEADEND: exactly one link
.fn:            ld   de, RD_STRIDE
                add  ix, de
                ld   a, ixl
                cp   LG_ROOMS_END
                jr   nz, .fl
                ; arrival shaft (D2+), level exit
                ld   a, (LVL_DEPTH)
                cp   2
                jr   c, .noarr
                ld   a, (LVL_START)
                call rdp
                push hl
                pop  ix
                ld   b, $75
                ld   d, SHAFT_MIN
                ld   e, SHAFT_MIN + SHAFT_N - 1
                call pick_man
                ld   (ix+RD_ARRCOL), a
.noarr:         ld   a, (LVL_LAIR)
                call rdp
                push hl
                pop  ix
                ld   b, $3A
                ld   d, SHAFT_MIN
                ld   e, SHAFT_MIN + SHAFT_N - 1
                call pick_man
                ld   (ix+RD_EXITCOL), a
                ; 7. in-room features
                ld   ix, ROOM_DESC
.room:          bit  0, (ix+RD_FLAGS)
                jr   z, .rn
                ld   b, $7F
                ld   d, LAD_COL_MIN
                ld   e, LAD_COL_MAX
                call pick_man
                ld   (ix+RD_LAD1), a
                ld   a, 2
                call rnd
                or   a
                jr   nz, .nopit
                ld   b, $7F             ; both storeys: the fall lands on storey 1 (|c-p| >= 7)
                ld   d, PIT_COL_MIN
                ld   e, PIT_COL_MAX
                call pick_opt
                ld   (ix+RD_PITCOL), a
.nopit:         ld   a, 2
                call rnd
                or   a
                jr   nz, .nol2
                ld   b, $7F
                ld   d, LAD_COL_MIN
                ld   e, LAD_COL_MAX
                call pick_opt
                ld   (ix+RD_LAD2), a
.nol2:          ld   a, 2
                call rnd
                or   a
                call z, block_try
.rn:            ld   de, RD_STRIDE
                add  ix, de
                ld   a, ixl
                cp   LG_ROOMS_END
                jr   nz, .room
                ; 8. potions
                ld   c, 0
                ld   e, 0
.pc:            ld   a, (LVL_START)
                cp   c
                jr   z, .pn
                ld   a, c
                call ispres
                jr   z, .pn
                ld   a, e
                ld   hl, LG_CAND
                call hla
                ld   (hl), c
                inc  e
.pn:            inc  c
                ld   a, c
                cp   9
                jr   nz, .pc
                ld   a, e
                ld   (LG_NC), a
                ld   a, 2
                call rnd
                add  a, 2
                ld   (LG_PT), a
                xor  a
                ld   (LG_K), a
.pot:           ld   a, (LG_NC)
                call rnd
                ld   hl, LG_CAND
                call hla
                ld   b, (hl)
                ld   a, 2
                call rnd
                ld   c, a
                ld   a, b
                call rdp
                push hl
                pop  ix
                ld   a, (LG_K)
                cp   2
                ld   a, 32
                jr   c, .st
                ld   a, FEAT_TRIES
.st:            ld   (LG_TRY), a
.try:           ld   a, 28
                call rnd
                add  a, 2
                ld   d, a
                ld   e, a
                call hits
                jr   nc, .ok
                ld   hl, LG_TRY
                dec  (hl)
                jr   nz, .try
                ld   a, (LG_K)
                cp   2
                jp   c, lg_restart
                jr   .nk
.ok:            ld   hl, FLOOR_N
                ld   a, (hl)
                inc  (hl)
                add  a, a
                add  a, a
                ld   l, a
                ld   h, FLOOR_LIST >> 8
                ld   a, c
                rrca
                or   b
                ld   (hl), a
                inc  hl
                ld   (hl), d
                inc  hl
                ld   (hl), IT_POTION
                inc  hl
                ld   (hl), 1
.nk:            ld   hl, LG_K
                inc  (hl)
                ld   a, (LG_PT)
                cp   (hl)
                jr   nz, .pot
                ; 9. room seeds
                ld   ix, ROOM_DESC
.sd:            bit  0, (ix+RD_FLAGS)
                jr   z, .sn
                call lg_step
                ld   (ix+RD_SEED), l
                ld   (ix+RD_SEED+1), h
.sn:            ld   de, RD_STRIDE
                add  ix, de
                ld   a, ixl
                cp   LG_ROOMS_END
                jr   nz, .sd
                call l2_pass            ; L2: last pass; GEN_RNG restored (earlier output intact)
                xor  a
                ret

;==============================================================================
; L2 (game.md 1.1 "Mid-room block" / "Wide pit"), bit-exact with levelgen.l2_pass.
;==============================================================================
; l2_clear: IX = room, B = footprint mask (bit k-2 <-> RD offset k), D = left
; clearance L, E = x + width + right clearance, x = (LG_P). CF = a footprint f has
; f + L > x and f < E (too close).  Clobbers A, B, C, HL.
l2_clear:       push ix
                pop  hl
                inc  hl
                inc  hl
.l:             srl  b
                jr   nc, .n
                ld   a, (hl)
                or   a
                jr   z, .n
                cp   e
                jr   nc, .n
                add  a, d
                ld   c, a
                ld   a, (LG_P)
                cp   c
                jr   nc, .n
                scf
                ret
.n:             inc  hl
                ld   a, b
                or   a
                jr   nz, .l
                ret                     ; NC (or a from the last test)

; l2_items: IX = room, D = lo, E = hi. CF = a storey-0 floor item of the room in lo..hi.
; Clobbers A, BC, HL.
l2_items_s1:    ld   a, ixl             ; storey-1 items of the room (FL_ROOM = id | $80)
                sub  ROOM_DESC & $FF
                rrca
                rrca
                rrca
                rrca
                or   $80
                jr   l2_items_c
l2_items:       ld   a, ixl             ; storey-0 items (FL_ROOM == id)
                sub  ROOM_DESC & $FF
                rrca
                rrca
                rrca
                rrca
l2_items_c:     ld   c, a
                ld   a, (FLOOR_N)
                or   a
                ret  z
                ld   b, a
                ld   hl, FLOOR_LIST
.l:             ld   a, (hl)
                cp   c
                jr   nz, .n
                inc  hl
                ld   a, (hl)
                dec  hl
                cp   d
                jr   c, .n
                ld   a, e
                inc  hl
                cp   (hl)
                dec  hl
                jr   c, .n
                scf
                ret
.n:             inc  hl
                inc  hl
                inc  hl
                inc  hl
                djnz .l
                or   a
                ret

; l2_kind_tab: per L2 kind (0 wide pit, 1 mid-block), 8 B: N (W = base + rnd N), base,
; left clearance L, right clearance R, clear-mask (up, down, arrival, exit / up,
; arrival: the ladders fit by construction), field A, field B, pad.
l2_kind_tab:       DB   3, 4, 7, 4, $0F, RD_PITCOL, L2_PITW, 0
                DB   2, 2, 6, 3, $05, L2_MIDB, L2_MIDW, 0

; l2_kind: In A = kind, IX = room. One kind: cap, odds roll, then up to 8 tries (W, the
; added 2nd-ladder col if the room has one ladder, p are rolled in that order every
; try). A narrow pit is removed meanwhile (restored on failure).  Out CF = placed.
l2_kind:        ld   (LG_K2), a
                ld   c, a
                ld   b, 0
                ld   hl, LG_NW
                add  hl, bc
                ld   a, (hl)
                cp   L2_MAX
                ret  nc                 ; cap reached (NC)
                ld   hl, LG_ODDS
                add  hl, bc
                ld   a, (hl)
                call rnd
                or   a
                ret  nz                 ; odds missed (NC)
                ld   a, (LG_K2)
                add  a, a
                add  a, a
                add  a, a
                ld   hl, l2_kind_tab
                call hla
                ld   de, LG_KP
                ld   bc, 7
                ldir
                ld   a, (ix+RD_PITCOL)
                ld   (LG_SVP), a
                ld   (ix+RD_PITCOL), 0
                ld   a, FEAT_TRIES
                ld   (LG_TRY), a
.t:             ld   a, (LG_KP)
                call rnd
                ld   hl, LG_KP + 1
                add  a, (hl)
                ld   (LG_W), a
                xor  a
                ld   (LG_NL), a
                ld   a, (ix+RD_LAD2)
                or   a
                jr   nz, .have
                ld   a, LAD_COL_MAX - LAD_COL_MIN + 1
                call rnd
                add  a, LAD_COL_MIN
                ld   (LG_NL), a
                ld   b, $7F
                call legal              ; FEAT_GAP vs every footprint, both storeys
                jp   c, .nt
                ld   a, (LG_NL)
                ld   d, a
                add  a, 2
                ld   e, a
                call l2_items           ; nothing under the new ladder (either storey)
                jp   c, .nt
                call l2_items_s1
                jp   c, .nt
                ld   c, 0
                call hits               ; not on an edge block (footprints already clear)
                jp   c, .nt
                ld   c, 1
                call hits
                jp   c, .nt
.have:          ld   a, (ix+RD_LAD2)
                or   a
                jr   nz, .l2
                ld   a, (LG_NL)
.l2:            ld   b, a
                ld   a, (ix+RD_LAD1)
                cp   b
                jr   c, .srt
                ld   c, a               ; lad1 >= other: c1 = other
                ld   a, b
                ld   b, c
.srt:           ld   (LG_C1), a         ; A = c1 < B = c2
                ld   a, b
                ld   (LG_C2), a
                ld   a, (LG_KP + 2)
                ld   hl, LG_C1
                add  a, (hl)
                ld   d, a               ; lo = c1 + L
                ld   a, (LG_C2)
                ld   hl, LG_W
                sub  (hl)
                ld   hl, LG_KP + 3
                sub  (hl)
                ld   e, a               ; hi = c2 - W - R
                sub  d
                jp   c, .nt
                inc  a
                call rnd
                add  a, d
                ld   (LG_P), a
                ld   hl, LG_W
                add  a, (hl)
                ld   hl, LG_KP + 3
                add  a, (hl)
                ld   e, a               ; p + W + R
                ld   a, (LG_KP + 4)
                ld   b, a
                ld   a, (LG_KP + 2)
                ld   d, a
                call l2_clear
                jp   c, .nt
                ld   a, (LG_P)
                dec  a
                ld   d, a               ; p - 1
                ld   a, (LG_P)
                ld   hl, LG_W
                add  a, (hl)
                ld   e, a               ; p + W
                call l2_items
                jp   c, .nt
                ld   a, (LG_NL)
                or   a
                jr   z, .nn
                ld   (ix+RD_LAD2), a
.nn:            push ix
                pop  hl
                ld   a, (LG_KP + 5)
                call hla
                ld   a, (LG_P)
                ld   (hl), a
                push ix
                pop  hl
                ld   a, (LG_KP + 6)
                call hla
                ld   a, (LG_W)
                ld   (hl), a
                ld   a, (LG_K2)
                ld   c, a
                ld   b, 0
                ld   hl, LG_NW
                add  hl, bc
                inc  (hl)
                scf
                ret
.nt:            ld   hl, LG_TRY
                dec  (hl)
                jp   nz, .t
                ld   a, (LG_SVP)
                ld   (ix+RD_PITCOL), a
                or   a
                ret

l2_pass:        ld   a, (LVL_DEPTH)
                cp   2
                ret  c                  ; D1: none
                ld   hl, (GEN_RNG)
                ld   (LG_RNG0), hl
                ld   hl, $0804          ; odds wide 1/4, mid-block 1/8 (D2-3), tuned on a sweep
                cp   4
                jr   c, .o
                ld   hl, $0201          ; D4-8: wide 1/1, mid-block 1/2
.o:             ld   (LG_ODDS), hl
                xor  a
                ld   (LG_NW), a
                ld   (LG_NB), a
                ld   ix, ROOM_DESC
.room:          bit  0, (ix+RD_FLAGS)
                jr   z, .rn
                ld   a, (ix+RD_FLAGS)
                and  RDF_START | RDF_LAIR
                jr   nz, .rn
                xor  a
                call l2_kind
                jr   c, .rn
                ld   a, 1
                call l2_kind
.rn:            ld   de, RD_STRIDE
                add  ix, de
                ld   a, ixl
                cp   LG_ROOMS_END
                jr   nz, .room
                ld   hl, (LG_RNG0)
                ld   (GEN_RNG), hl
                ret

;==============================================================================
; level_gen (see header)
;==============================================================================
level_gen:      ld   (LVL_DEPTH), a
                ld   hl, 0
                ld   (GEN_ZBLK), hl     ; GEN_SCRATCH is about to be overwritten
                ld   a, RESEED_MAX
                ld   (LG_RES), a
.seed:          ld   a, MAX_RESTARTS
                ld   (LG_RST), a
                ld   a, (LVL_DEPTH)
                ld   hl, (LVL_SEED)
                xor  h
                ld   h, a
                ld   a, (LVL_DEPTH)
                xor  l
                ld   l, a
                or   h
                jr   nz, .nz
                inc  l                  ; x = 0 would lock the xorshift
.nz:            ld   (GEN_RNG), hl
.try:           call attempt
                cp   1
                jr   nz, .nr
                ld   hl, LG_RST         ; restart cap: treat as a reseed (never loops forever)
                dec  (hl)
                jr   nz, .try
                jr   .rs
.nr:            or   a
                jr   z, .done
.rs:                ld   hl, (LVL_SEED)
                inc  hl
                ld   (LVL_SEED), hl
                ld   hl, LG_RES
                dec  (hl)
                jr   nz, .seed
                ld   b, 1
                scf
                ret
.done:          ld   a, (LG_CNT)
                ld   (LVL_NROOMS), a
                ld   a, (LVL_DEPTH)
                dec  a
                add  a, a
                ld   hl, attr_tab
                call hla
                ld   a, (hl)
                ld   (LVL_ATTR_FLOOR), a
                inc  hl
                ld   a, (hl)
                ld   (LVL_ATTR_WALL), a
                ld   a, ROOM_NONE
                ld   (LVL_KEYROOM), a
                ld   (LVL_SANCTUM), a
    IF F3_GEN
                ld   hl, sanctum_leaf   ; 3F (bank 7, sanct7.asm; M0: was R6): LVL_FLAGS = 0, the D8 Sanctum, B = 0
                jp   far7               ; (bank 3 is full; restore_page keeps BC, callers test B)
    ELSE
                xor  a                  ; 3F-T8 (BOSS-GUARD): the grate is SHUT at generation, the
                ld   (LVL_FLAGS), a     ; boss's death opens it (grate_open); 3B opened it here
                ld   b, a
                ret
    ENDIF

;==============================================================================
; level_start_x: D1 x = 14, D2+ x = arrival col + 1 (arrival shaft exempt); if
; another storey-0 footprint touches x-1..x+1 (or x is outside 2..29) move to the
; nearest legal col, d = 0.., x-d before x+d. Out A = B = col.
;==============================================================================
level_start_x:  ld   a, (LVL_START)
                call rdp
                push hl
                pop  ix
                ld   a, (LVL_DEPTH)
                ld   b, 14
                dec  a
                jr   z, .x0
                ld   b, (ix+RD_ARRCOL)
                inc  b
.x0:            ld   c, 0
.d:             ld   a, b
                sub  c
                call .ok
                jr   nc, .f1
                ld   a, b
                add  a, c
                call .ok
                jr   nc, .f2
                inc  c
                ld   a, c
                cp   32
                jr   nz, .d
                ld   a, b
                ret
.f1:            ld   a, b
                sub  c
                jr   .r
.f2:            ld   a, b
                add  a, c
.r:             ld   b, a
                ret
.ok:            cp   2                  ; CF = illegal
                ret  c
                cp   30
                ccf
                ret  c
                push bc
                push de
                dec  a
                ld   d, a
                add  a, 2
                ld   e, a
                ld   c, 0
                call hits_x
                pop  de
                pop  bc
                ret
