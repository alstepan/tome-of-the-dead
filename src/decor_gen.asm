;==============================================================================
; decor_gen.asm — DECOR2 (P1 + P2, docs/design/decor_rules2.md §2 R1..R8, §5a / §5b): the decor
; deriver, bank-0 B0_CODE2 (SIZE T3 lever F2; FARB0 from the 11-B bank-3 `decor_room` stub,
; A = (dg_dst)). Python reference: tools/decorgen2.py `decorate` (W13 compares ROOM_MAP +
; ANIM_LIST byte for byte). Levels with no key room (LVL_KEYROOM = ROOM_NONE: D0 and PROTO; every
; generated level has one) keep the B3B-9 / D1 deriver tools/decorgen.py (the legacy path below),
; so the D0 tutorial's searched RD_SEEDs (tools/tut0_level.py) stay valid untouched.
;
; decor_b0: A = dg_dst (low byte of ANIM_N / ANIM_N2), IX = descriptor (kept; room id =
;   (IXL - ROOM_DESC) / 16; role = RD_FLAGS + LVL_KEYROOM / LVL_KEYROOM2), (TMP1) = map page.
;   B0_CODE2 rules: no SMC, no runtime-written bytes here (state = the low-RAM DS block `dg_vars`,
;   the per-query run list = DG_PLAN), never pages $C000; calls only bank-2 map_cell / xs_core.
;   Re-derived from RD_SEED only (private xorshift dg_rng, never GEN_RNG / RNG_STATE).
; Pass order (= decorgen2.decorate; every draw from dg_rng in the model's order):
;   mood (rnd 24, R4) -> compose (FRAME / CENTRE / GALLERY / SINGLE, R5) -> light lock (nl :=
;   MAX) -> pools (R6) -> wall-anchored patches (R7) -> cobwebs (odds by storey / mood) -> chain
;   cluster (DIM / DARK) -> moss strip (DARK) -> fill (R8: tries by mood, D2 +3, cols 3..28, 3-col
;   halo, near-duplicate veto, pit jump zone) -> no empty storey (§5b).
; Atomic groups (pairs, galleries, chain clusters) are CHECKED item by item with the budgets bumped,
; then written: no map snapshot (~12k T a group). The items of a group never sit in each other's
; footprint or ring (pair / flank gap >= 3, gallery gap >= 2, chains pitch 2), so the check sees
; what the model's sequential write sees.
; The structure the planner reads (row-3 runs, faces, focal list, widest span) is re-scanned from
; the live map with "air-like" = T_AIR or a decor id: decor sits only on T_AIR, so that equals the
; model's pre-decor analyze().
; Clobbers: A, BC, DE, HL. Cold path (room build), measured in docs/memory-map.md "DECOR2 ledger".
;==============================================================================
F_MOSS          EQU 1               ; record flags (tools/decorgen.py)
F_TILED         EQU 2
DG_MAX_LARGE    EQU 2
DG_MAX_GLYPH    EQU 4
DG_PTRIES       EQU 8
DG_LEG_TRIES    EQU 12              ; decorgen.tries_of(1): the legacy menu loop
DC_CEIL         EQU 1               ; object classes (record wh byte bits 5..7)
DC_FLOOR        EQU 2
DC_PATCH        EQU 3
DC_COMP         EQU 5
DM_LIT          EQU 0               ; moods (dg_mood)
DM_DIM          EQU 1
DM_DARK         EQU 2
DM_CALM         EQU 3
DM_LEG          EQU 4               ; the legacy deriver (D0 / PROTO)
DG_HALO_FILL    EQU 3               ; R3: a fill mount / floor object keeps 3 clear cols
DG_DEDUP        EQU 6               ; §5a 1: the same record within 6 empty cols = a near-duplicate
PIT_BEFORE      EQU 4               ; R3 pit jump zone: cols p-4 .. p+W+3
PIT_AFTER       EQU 3
FK_LAD          EQU 1               ; focal kinds (dg_foc mask)
FK_BLOCK        EQU 2
FK_ARR          EQU 4
FK_SHAFT        EQU 8
FK_PIT          EQU 16
RB_LAD          EQU 2               ; dg_bad bit: ladder / hole (bit 0 = decor); dg_rmask 3 = both
DG_ID_LO        EQU 28              ; decor ids: 12 (chain) and 28..59 except 31 (T_GLOW)
DG_DEADEND_BIT  EQU 3

decor_b0:
                ld   (dg_dst0), a
                ld   l, (ix + RD_SEED)
                ld   h, (ix + RD_SEED + 1)
                ld   (dg_rng), hl
                ld   hl, dg_zero
                ld   b, DG_ZERO_N
                xor  a
.z:             ld   (hl), a
                inc  hl
                djnz .z
                ld   a, (LVL_DEPTH)
                dec  a
                ld   e, a
                add  a, a
                add  a, a
                add  a, a
                sub  e                         ; 7 (depth - 1)
                ld   e, a
                ld   d, 0
                ld   hl, dg_dtab
                add  hl, de
                ld   de, dg_wmax
                ld   bc, DG_DTAB
                ldir                           ; dg_wmax .. dg_nlev
                ld   bc, (dg_first)            ; C = the depth's first record, B = its count
                ; the depth's lights (F_LARGE), plain mount objects and first moss strip record
.ls:            ld   a, c
                call dg_rec
                inc  hl
                ld   d, (hl)                   ; wh
                inc  hl
                ld   e, (hl)                   ; flags
                ld   hl, dg_nlt
                bit  7, e
                jr   nz, .ap
                ld   hl, dg_npl
                ld   a, d
                and  $E0
                jr   z, .ap                    ; class 0 (mount), not large
                bit  0, e
                jr   z, .nx
                ld   a, (dg_mossi)
                or   a
                jr   nz, .nx
                ld   a, c
                ld   (dg_mossi), a
                jr   .nx
.ap:            inc  (hl)                      ; the count, then its list
                ld   a, (hl)
                add  a, l
                ld   l, a
                ld   (hl), c
.nx:            inc  c
                djnz .ls
                ; the pit: the last T_AIR run of the storey-0 floor row, cols 1..30
                ld   bc, FLOOR_ROW0 << 8 | 1
                call map_cell
                ld   d, 1
.p:             ld   a, (hl)
                or   a
                jr   nz, .pn
                or   d
                jr   z, .pc                    ; the run goes on
                ld   a, c
                ld   (dg_pit), a
                xor  a
                ld   (dg_pitw), a
.pc:            ld   a, (dg_pitw)
                inc  a
                ld   (dg_pitw), a
                xor  a
.pn:            ld   d, a
                inc  hl
                inc  c
                ld   a, c
                cp   ROOM_COLS - 1
                jr   c, .p
                ld   a, (LVL_KEYROOM)
                inc  a
                jr   nz, .d2
                ; legacy (no key room: D0 / PROTO) = tools/decorgen.py: >= 1 patch (+ 1/2), cobwebs, 12 tries
                ld   a, DM_LEG
                ld   (dg_mood), a
                ld   a, DG_LEG_FIRST
                ld   (dg_first), a
                ld   (dg_ncom), a
                ld   (dg_nlev), a
                call dg_pfb
                ld   a, 2
                call dg_rnd
                or   a
                call z, dg_pfb
                call dg_cobwebs
                ld   b, DG_LEG_TRIES
                jp   dg_fill
.d2:            ld   a, 1
                ld   (dg_ncom), a              ; menu2: CHAIN + the depth's records
                call dg_mdraw
                call dg_compose
                ld   a, DG_MAX_LARGE
                ld   (dg_nl), a                ; light lock (C10)
                call dg_pools
                ld   a, $FF
                call nz, dg_apatch             ; no pool: one wall-anchored patch
                ld   a, 4
                call dg_rnd
                ld   c, a
                ld   a, (dg_mood)
                cp   DM_DARK
                ld   a, 2
                jr   nz, .p2
                inc  a
.p2:            ld   b, a
                ld   a, c
                cp   b
                ld   a, $FF
                call c, dg_apatch              ; a 2nd one: rnd(4) < 2 (DARK 3)
                call dg_cobwebs
                ld   a, (dg_mood)
                dec  a
                cp   2
                ld   a, $FF
                call c, dg_chains              ; DIM / DARK: a chain cluster
                ld   a, (dg_mood)
                cp   DM_DARK
                call z, dg_moss
                ld   a, (dg_mood)
                cp   DM_DIM
                ld   b, 6
                jr   nz, .f1
                ld   b, 8
.f1:            ld   a, (LVL_DEPTH)
                cp   2
                jr   nz, .f2
                inc  b                         ; FILL_BONUS: D2 +3
                inc  b
                inc  b
.f2:            call dg_fill
                ; no empty storey (§5b): patch, unlit centrepiece, chain cluster, moss, one chain
                xor  a
                call .es
                ld   a, 1
.es:            ld   (dg_es), a
                call .emp
                ret  nz
                ld   a, (dg_es)
                call dg_apatch
                call .emp
                ret  nz
                ld   a, (dg_mood)
                cp   DM_CALM
                jr   nz, .c
                ld   a, (dg_es)
                or   a
                jr   nz, .ch                   ; the CALM start room's storey 1: no object
.c:             ld   a, (dg_es)
                ld   (dg_s), a
                xor  a
                call dg_centre
                call .emp
                ret  nz
.ch:            ld   a, (dg_es)
                call dg_chains
                call .emp
                ret  nz
                ld   a, (dg_es)
                or   a
                jr   z, .lc
                call dg_moss
                call .emp
                ret  nz
.lc:            xor  a
                call dg_ld                     ; CHAIN
                ld   a, (dg_es)
                call dg_rowof
                ld   a, 3
.lcl:           ld   (dg_col), a
                call dg_place
                ret  z
                ld   a, (dg_col)
                inc  a
                cp   29
                jr   c, .lcl
                ret
.emp:           ld   a, (dg_es)                ; NZ = storey dg_es holds decor
                inc  a
                ld   hl, dg_used
                and  (hl)
                ret

; dg_mdraw — R4 mood: rnd(24) always; START CALM, LAIR / key LIT, dead end DARK 2/3 DIM 1/3, else
; by depth (LIT / DIM / DARK under the thresholds D1-3 6 / 18, D4-7 6 / 15, D8 12 / 24).
dg_mdraw:
                ld   a, 24
                call dg_rnd
                ld   c, a
                ld   b, (ix + RD_FLAGS)
                ld   a, DM_CALM
                bit  RDF_START_BIT, b
                jr   nz, .st
                xor  a
                bit  RDF_LAIR_BIT, b
                jr   nz, .st
                call dg_iskey
                ld   a, DM_LIT
                jr   z, .st
                bit  DG_DEADEND_BIT, b
                jr   z, .dep
                ld   a, c
                cp   16
                ld   a, DM_DARK
                jr   c, .st
                dec  a
                jr   .st
.dep:           ld   de, 6 << 8 | 18
                ld   a, (LVL_DEPTH)
                cp   4
                jr   c, .t
                ld   e, 15
                cp   8
                jr   c, .t
                ld   de, 12 << 8 | 24
.t:             ld   a, c
                cp   d
                ld   a, DM_LIT
                jr   c, .st
                ld   a, c
                cp   e
                ld   a, DM_DIM
                jr   c, .st
                inc  a
.st:            ld   (dg_mood), a
                ret

; dg_iskey — Z = a key room (LVL_KEYROOM / LVL_KEYROOM2; the descriptor's RDF_KEY is never set).
; dg_rid — A = the room id from IX (ROOM_DESC + 16 r). Clobber A, HL.
dg_iskey:
                call dg_rid
                ld   hl, LVL_KEYROOM
                cp   (hl)
                ret  z
                ld   hl, LVL_KEYROOM2
                cp   (hl)
                ret
dg_rid:
                ld   a, ixl
                sub  ROOM_DESC & $FF
                rrca
                rrca
                rrca
                rrca
                ret

; dg_compose — R5 per mood (decorgen2.compose).
dg_compose:
                ld   a, (dg_mood)
                cp   DM_DIM
                jr   z, .dim
                cp   DM_CALM
                jr   z, .calm
                or   a
                ret  nz                        ; DARK: no lights
                bit  RDF_LAIR_BIT, (ix + RD_FLAGS)
                jr   z, .lit
                ld   a, 1                      ; lair: FRAME on the grate (storey 1), then storey 0
                ld   (dg_s), a
                xor  a
                ld   c, FK_SHAFT
                call dg_lit
                ld   hl, dg_s
                ld   (hl), 0
                ld   a, 1
                jp   z, dg_gallery             ; on the pair's axis (dg_gc, dg_lw)
                jp   dg_unlit
.lit:           call dg_iskey
                ld   a, 1
                jr   z, .t                     ; key room: CENTRE, no draw
                ld   a, 3
                call dg_rnd
                ld   b, a
                call dg_rid
                add  a, b
.m3:            sub  3
                jr   nc, .m3
                add  a, 3
.t:             ld   (dg_t1), a
                ld   a, 2
                call dg_rnd
                ld   (dg_s), a
                ld   a, (dg_t1)
                cp   2
                jr   nz, .t01
                xor  a
                call dg_gallery
                call dg_sflip
                xor  a
                ld   c, a
                jp   dg_lit
.t01:           ld   c, 0                      ; A = 0 FRAME, 1 CENTRE
                call dg_lit
                call dg_sflip
                jp   dg_unlit
.dim:           ld   a, 2
                call dg_rnd
                ld   (dg_s), a
                ld   a, 1
                call dg_single
                ret  z
                call dg_sflip
                ld   a, 1
                jp   dg_single
.calm:          xor  a                         ; start room: FRAME on the arrival shaft, else a centrepiece
                ld   (dg_s), a
                call dg_scan
                xor  a
                ld   c, FK_ARR
                call dg_foc
                jr   nc, .cc
                ld   (dg_fc), a
                ld   a, b
                ld   (dg_fw), a
                jp   dg_frame
.cc:            xor  a
                jp   dg_centre
dg_sflip:       ld   hl, dg_s
                ld   a, (hl)
                xor  1
                ld   (hl), a
                ret

; dg_unlit — the unlit storey dg_s: rnd(2) ? GALLERY : unlit CENTRE.
dg_unlit:
                ld   a, 2
                call dg_rnd
                or   a
                ld   a, 0
                jp   nz, dg_gallery
                jp   dg_centre

; dg_lit — A = 0 FRAME (C = role focal mask, 0 = any) / else CENTRE, storey dg_s; a storey left
; without a light gets a wall / ladder single. -> Z = the FRAME's mirrored pair (dg_gc).
dg_lit:
                or   a
                jr   nz, .cen
                call dg_pickf
                jr   nc, .cen
                call dg_frame
                cp   2
                ret  z
                or   a
                jr   nz, .nz
.cen:           ld   a, 1
                call dg_centre
                call dg_lons
                jr   z, .nz
                ld   a, 1
                call dg_single
.nz:            or   1
                ret

; dg_lons — Z = a placed light stands on storey dg_s. Clobbers A, BC, HL.
dg_lons:
                ld   a, (dg_nlr)
                or   a
                jr   z, .no
                ld   b, a
                ld   hl, dg_lr + 1             ; the row of light 0
.l:             ld   a, (hl)
                cp   STOREY_ROWS
                ccf
                ld   a, 0
                rla
                ld   c, a
                ld   a, (dg_s)
                cp   c
                ret  z
                inc  hl
                inc  hl
                inc  hl
                djnz .l
.no:            or   1
                ret

; dg_pickf — C = role mask (0 = none), storey dg_s: the first focal of the role, else a random one of
; the interior obstacles / arrival / pit (a pit only for a mount pair light) -> CF: dg_fc, dg_fw.
dg_pickf:
                push bc
                call dg_scan
                pop  bc
                ld   a, c
                or   a
                jr   z, .gen
                xor  a
                call dg_foc
                jr   c, .got
.gen:           ld   c, FK_LAD | FK_BLOCK | FK_ARR
                ld   a, (dg_pr)
                rlca
                jr   c, .np
                ld   c, FK_LAD | FK_BLOCK | FK_ARR | FK_PIT
.np:            push bc
                ld   a, $FF
                call dg_foc
                pop  bc
                or   a
                ret  z                         ; none (NC)
                call dg_rnd
                call dg_foc
.got:           ld   (dg_fc), a
                ld   a, b
                ld   (dg_fw), a
                scf
                ret

; dg_frame — FRAME on dg_fc / dg_fw: the pair, else one light beside it. -> A = 2 pair (Z), 1 single, 0.
dg_frame:
                call dg_lpair
                ld   a, 2
                ret  z
                xor  a
                call dg_single
                ld   a, 1
                ret  z
                xor  a
                ret

; dg_lpair — the depth's pair light mirrored around dg_fc / dg_fw on storey dg_s, gap g = 1 + rnd(2),
; then the other gap (PAIR_RETRY). -> Z placed (dg_gc = its cols, dg_lw = its width).
dg_lpair:
                ld   a, (dg_pr)
                and  $7F
                call dg_ld
                ld   a, (dg_w)
                ld   (dg_lw), a
                ld   a, 2
                call dg_rnd
                inc  a
                ld   (dg_g), a
                ld   a, (dg_s)
                call dg_rowof
                call dg_pair2
                ret  z
                ld   hl, dg_g
                ld   a, 3
                sub  (hl)
                ld   (hl), a
; dg_pair2 — the loaded object at dg_row, cols dg_fc - g - w and dg_fc + dg_fw + g, atomic -> Z placed.
dg_pair2:
                ld   a, (dg_fc)
                ld   hl, dg_g
                sub  (hl)
                ld   hl, dg_w
                sub  (hl)
                ld   (dg_gc), a
                ld   a, (dg_fc)
                ld   hl, dg_fw
                add  a, (hl)
                ld   hl, dg_g
                add  a, (hl)
                ld   (dg_gc + 1), a
                ld   a, 2
                ld   (dg_gn), a
                jp   dg_group

; dg_single — A = 0: beside the focal dg_fc / dg_fw; else anchored (a ladder of the storey, and / or a
; wall face of a run >= 6); storey dg_s; light = lights[rnd(n)] if n > 1. The candidates are drawn
; first, then tried in order. -> Z placed.
dg_single:
                ld   (dg_t1), a
                xor  a
                ld   (dg_gn), a                ; the candidate list = dg_gc
                ld   a, (dg_nlt)
                cp   2
                ld   a, 0
                jr   c, .one
                ld   a, (dg_nlt)
                call dg_rnd
.one:           ld   hl, dg_lts
                call dg_idx
                call dg_ld
                ld   a, (dg_s)
                call dg_rowof
                ld   a, (dg_t1)
                or   a
                jr   nz, .anc
                ld   a, (dg_fw)
                ld   b, a
                ld   a, (dg_fc)
                call dg_side2
                jr   .try
.anc:           call dg_scan
                ld   a, $FF
                ld   c, FK_LAD
                call dg_foc
                ld   (dg_t2), a                ; ladders
                ld   hl, 1 << 8 | 6
                ld   (dg_fmin), hl             ; dg_fmin 6, dg_fwall 1
                ld   a, $FF
                call dg_face
                ld   (dg_t3), a                ; wall faces
                ld   a, 2
                call dg_rnd                    ; pick
                ld   c, a
                ld   a, (dg_t2)
                or   a
                jr   z, .wl
                ld   a, c
                or   a
                jr   nz, .ld
                ld   a, (dg_t3)
                or   a
                jr   nz, .wl
.ld:            ld   a, (dg_t2)
                call dg_rnd
                ld   c, FK_LAD
                call dg_foc
                call dg_side2
.wl:            ld   a, (dg_t3)
                or   a
                jr   z, .try
                call dg_rnd
                call dg_face                   ; A = edge, B = side
                push af
                ld   a, 3
                call dg_rnd
                ld   (dg_t1), a                ; off
                ld   a, 1
                ld   (dg_fd), a                ; L: max(edge + 1, 3) + off, R: min(edge - 1, 28) - off - w + 1
                pop  af
                call dg_fcol
.ad:            call dg_cadd
.try:           ld   hl, dg_gc
                ld   a, (dg_gn)
                or   a
                jr   z, .no
                ld   b, a
.tl:            ld   a, (hl)
                ld   (dg_col), a
                push hl
                push bc
                call dg_place
                pop  bc
                pop  hl
                ret  z
                inc  hl
                djnz .tl
.no:            or   1
                ret

; dg_side2 — A = col, B = width of a focal: candidates col - 1 - w and col + width + 1 (rnd(2): the
; other order) appended to dg_gc. dg_cadd — A -> dg_gc[dg_gn++] (keeps DE).
dg_side2:
                ld   c, a
                add  a, b
                inc  a
                ld   e, a
                ld   a, c
                dec  a
                ld   hl, dg_w
                sub  (hl)
                ld   d, a
                ld   a, 2
                call dg_rnd
                or   a
                jr   z, .n
                ld   a, d
                ld   d, e
                ld   e, a
.n:             ld   a, d
                call dg_cadd
                ld   a, e
dg_cadd:
                ld   hl, dg_gn
                ld   c, (hl)
                inc  (hl)
                ld   b, 0
                ld   hl, dg_gc
                add  hl, bc
                ld   (hl), a
                ret

; dg_centre — A = 0 unlit / 1 lit, storey dg_s: a plain object in the middle of the widest span;
; lit: the mirrored pair around it (else a single beside it); unlit: 1/2 a flanking pair of another
; plain object.
dg_centre:
                ld   (dg_t1), a
                call dg_scan
                call dg_span
                ret  c
                push de
                ld   a, (dg_npl)
                call dg_rnd
                ld   (dg_ci), a
                ld   hl, dg_pls
                call dg_idx
                call dg_ld
                pop  de
                ld   a, e
                sub  d
                inc  a
                ld   hl, dg_w
                sub  (hl)
                ret  c                         ; the span is narrower than the object
                rra                            ; (hi - lo + 1 - w) // 2 (CF = 0)
                add  a, d
                ld   (dg_col), a
                ld   (dg_fc), a
                ld   a, (hl)
                ld   (dg_fw), a
                ld   a, (dg_s)
                call dg_rowof
                call dg_place
                ret  nz
                ld   a, (dg_t1)
                or   a
                jr   z, .ul
                call dg_lpair
                ret  z
                xor  a
                jp   dg_single
.ul:            ld   a, (dg_npl)
                dec  a
                ret  z                         ; no other plain object
                ld   a, 2
                call dg_rnd
                or   a
                ret  z
                ld   a, (dg_npl)
                dec  a
                call dg_rnd
                ld   hl, dg_ci
                cp   (hl)
                jr   c, .f
                inc  a                         ; flank[k] = plain[k + (k >= the centre's index)]
.f:             ld   hl, dg_pls
                call dg_idx
                call dg_ld
                ld   a, 2
                call dg_rnd
                inc  a
                ld   (dg_g), a
                ld   a, (dg_s)
                call dg_rowof
                jp   dg_pair2

; dg_gallery — A = 0: k copies (3 if w = 1, else 2) of a plain object at pitch w + 3 + rnd(2),
; centred in the widest span; A != 0: 2 copies on the lair pair's axis (dg_gc + (dg_lw - w) // 2).
dg_gallery:
                ld   (dg_t1), a
                call dg_scan
                call dg_span
                ret  c
                push de
                ld   a, (dg_npl)
                call dg_rnd
                ld   hl, dg_pls
                call dg_idx
                call dg_ld
                ld   a, (dg_s)
                call dg_rowof
                pop  de
                ld   a, (dg_t1)
                or   a
                jr   z, .n
                ld   a, (dg_lw)
                ld   hl, dg_w
                sub  (hl)
                sra  a                         ; floor division (Python //)
                ld   b, a
                ld   hl, dg_gc
                ld   a, (hl)
                add  a, b
                ld   (hl), a
                inc  hl
                ld   a, (hl)
                add  a, b
                ld   (hl), a
                ld   a, 2
                jr   .g
.n:             ld   a, 2
                call dg_rnd
                ld   hl, dg_w
                add  a, (hl)
                add  a, 3
                ld   c, a                      ; pitch
                ld   a, (hl)
                dec  a
                ld   b, 3
                jr   z, .k
                dec  b                         ; k
.k:             ld   a, (hl)
                push bc
                dec  b
.tt:            add  a, c
                djnz .tt
                pop  bc                        ; A = total = (k - 1) * pitch + w
                ld   l, a
                ld   a, e
                sub  d
                inc  a
                sub  l
                ret  c                         ; the span is too short
                rra
                add  a, d                      ; c0
                ld   hl, dg_gc
                push bc
.gl:            ld   (hl), a
                inc  hl
                add  a, c
                djnz .gl
                pop  bc
                ld   a, b
.g:             ld   (dg_gn), a
                jp   dg_group

; dg_pools — R6: one patch cluster on a light's outer side (pair: 1/2, one light, its own side;
; single: 1/2 (DIM always), side rnd(2) then the other). -> Z = a pool placed.
dg_pools:
                ld   a, (dg_nlr)
                or   a
                jr   z, .no
                dec  a
                jr   z, .sg
                ld   a, 2
                call dg_rnd
                or   a
                jr   nz, .no
                ld   a, 2
                call dg_rnd
                ld   c, a                      ; light 0 = the left one: its outer side is left
                jr   dg_pool
.sg:            ld   a, (dg_mood)
                cp   DM_DIM
                jr   z, .s1
                ld   a, 2
                call dg_rnd
                or   a
                jr   nz, .no
.s1:            ld   a, 2
                call dg_rnd
                ld   (dg_t1), a
                ld   c, a
                xor  a
                call dg_pool
                ret  z
                ld   a, (dg_t1)
                xor  1
                ld   c, a
                xor  a
                jr   dg_pool
.no:            or   1
                ret
; dg_pool — A = light index, C = side (0 left) -> Z placed: pats[rnd] at col lc - pw - 1 / lc + lw + 1,
; row min(light row + rnd(2), storey row 6 - ph); the ring checks ladders only.
dg_pool:
                ld   b, a
                add  a, a
                add  a, b
                ld   e, a
                ld   d, 0
                ld   hl, dg_lr
                add  hl, de
                push hl
                push bc
                call dg_pat
                pop  bc
                pop  hl
                ld   e, (hl)                   ; light col
                inc  hl
                ld   d, (hl)                   ; light row
                inc  hl
                ld   a, c
                or   a
                ld   a, e
                jr   z, .l
                add  a, (hl)
                inc  a
                jr   .c
.l:             ld   hl, dg_w
                sub  (hl)
                dec  a
.c:             ld   (dg_col), a
                ld   a, 2
                call dg_rnd
                add  a, d
                ld   b, a
                ld   a, d
                cp   STOREY_ROWS
                ld   a, 6
                jr   c, .s
                ld   a, 6 + STOREY_ROWS
.s:             ld   hl, dg_h
                sub  (hl)
                cp   b
                jr   c, .m
                ld   a, b
.m:             ld   (dg_row), a
                ld   a, RB_LAD
                ld   (dg_rmask), a
                jp   dg_place

; dg_pat — load pats[rnd(len)]: the depth's PATCH_A/B records, else the composite (rnd(1)).
dg_pat:
                ld   a, (dg_pkn)
                or   a
                jr   nz, .k
                inc  a
.k:             call dg_rnd
                ld   b, a
                ld   a, (dg_pkn)
                or   a
                ld   hl, dg_crec
                jp   z, dg_load
                ld   a, (dg_first)
                add  a, b
                jp   dg_ld

; dg_apatch — A = storey (or $FF: rnd(2)): R7 wall-anchored patch (pats[rnd], top 1 + rnd(6 - h),
; within 3 cols of a wall face of a run >= w + 2, faces from rnd(n), off rnd(3)), else the random
; loop dg_pfb. -> Z placed.
dg_apatch:
                inc  a
                jr   nz, .s
                ld   a, 2
                call dg_rnd
                inc  a
.s:             dec  a
                ld   (dg_s), a
                call dg_pat
                ld   a, (dg_h)
                neg
                add  a, 6
                call dg_rnd
                inc  a
                ld   b, a
                ld   a, (dg_s)
                call dg_9s
                add  a, b
                ld   (dg_row), a
                call dg_scan
                ld   a, (dg_w)
                add  a, 2
                ld   l, a
                ld   h, 1
                ld   (dg_fmin), hl             ; run >= w + 2, wall faces
                ld   a, $FF
                call dg_face
                or   a
                jr   z, dg_pfb
                ld   (dg_t2), a                ; n
                xor  a
                ld   (dg_fd), a                ; L: max(edge, 2) + off, R: min(edge, 29) - off - w + 1
                ld   a, 3
                ld   hl, dg_apl
                call dg_fwalk
                ret  z
                jr   dg_pfb
dg_apl:         ld   (dg_col), a
                jp   dg_place
; dg_pfb — the random patch loop (DG_PTRIES x pats[rnd], col 2 + rnd(29 - w), storey rnd(2), r0
; rnd(6 - h)); also the legacy patch pass. -> Z placed.
dg_pfb:
                ld   b, DG_PTRIES
.t:             push bc
                call dg_pat
                ld   a, 29
                ld   hl, dg_w
                sub  (hl)
                call dg_rnd
                add  a, 2
                ld   (dg_col), a
                ld   a, 2
                call dg_rnd
                call dg_9s
                ld   b, a
                ld   a, (dg_h)
                neg
                add  a, 6
                call dg_rnd
                inc  a
                add  a, b
                ld   (dg_row), a
                call dg_place
                pop  bc
                ret  z
                djnz .t
                ret

; dg_chains — A = storey (or $FF: rnd(2)): R7 chain cluster, k = 2 + rnd(2) (drawn first) chains at
; pitch 2 from a face of a run >= 8 (faces from rnd(n), off rnd(2)), atomic. -> Z placed.
dg_chains:
                ld   c, a
                ld   a, 2
                call dg_rnd
                add  a, 2
                ld   (dg_gn), a
                ld   a, c
                inc  a
                jr   nz, .s
                ld   a, 2
                call dg_rnd
                inc  a
.s:             dec  a
                ld   (dg_s), a
                call dg_scan
                ld   hl, 0 << 8 | 8
                ld   (dg_fmin), hl             ; run >= 8, any face
                ld   a, $FF
                call dg_face
                or   a
                jr   z, .no
                ld   (dg_t2), a
                xor  a
                call dg_ld                     ; CHAIN (w 1: dg_fcol's R col = min(edge - 1, 28) - off)
                ld   a, (dg_s)
                call dg_rowof
                ld   a, 1
                ld   (dg_fd), a                ; L: max(edge + 1, 3) + off + 2 i, R: min(edge - 1, 28) - off - 2 i
                ld   a, 2
                ld   hl, dg_chl
                jp   dg_fwalk
.no:            or   1
                ret
dg_chl:         ld   c, 2                      ; A = the first col, B = side: pitch +2 / -2
                dec  b
                jr   nz, .g
                ld   c, -2
.g:             ld   e, a
                ld   a, (dg_gn)
                ld   b, a
                ld   a, e
                ld   hl, dg_gc
.gl:            ld   (hl), a
                inc  hl
                add  a, c
                djnz .gl
                jp   dg_group

; dg_fwalk — A = off range, HL = action (A = col, B = side -> Z done), dg_t2 = n faces (> 0, dg_face's
; filter set), dg_fd = d: k0 = rnd(n), off = rnd(range), then faces (k0 + j) mod n, j < n, each at
; dg_fcol's col -> Z = an action succeeded.
dg_fwalk:
                ld   (dg_fn), hl
                push af
                ld   a, (dg_t2)
                call dg_rnd
                ld   (dg_t3), a                ; k0
                pop  af
                call dg_rnd
                ld   (dg_t1), a                ; off
                ld   a, (dg_t2)
                ld   b, a
.f:             push bc
                ld   a, (dg_t3)
                call dg_face
                call dg_fcol
                ld   hl, (dg_fn)
                call dg_jphl
                pop  bc
                ret  z
                ld   hl, dg_t3
                inc  (hl)
                ld   a, (dg_t2)
                cp   (hl)
                jr   nz, .n
                ld   (hl), 0
.n:             djnz .f
                or   1
                ret
dg_jphl:        jp   (hl)
; dg_fcol — A = edge, B = side (0 L), dg_fd = d, dg_t1 = off -> A = L: max(edge + d, 2 + d) + off,
; R: min(edge - d, 29 - d) - off - w + 1 (the loaded object). Keeps B.
dg_fcol:
                ld   c, a
                ld   a, (dg_fd)
                ld   d, a
                ld   a, b
                or   a
                ld   a, c
                jr   nz, .r
                add  a, d
                ld   c, a
                ld   a, 2
                add  a, d
                cp   c
                jr   nc, .l
                ld   a, c
.l:             ld   hl, dg_t1
                add  a, (hl)
                ret
.r:             sub  d
                ld   c, a
                ld   a, 29
                sub  d
                cp   c
                jr   c, .r1
                ld   a, c
.r1:            ld   hl, dg_t1
                sub  (hl)
                ld   hl, dg_w
                sub  (hl)
                inc  a
                ret

; dg_moss — R2 moss strip (DARK; the no-empty-storey chain): MOSS w = 2 + rnd(2) on map row 9 at
; candidates[rnd(n)] of the cols 2 .. 30 - w that fit (cmin 2). -> Z placed.
dg_moss:
                ld   a, (dg_mossi)
                or   a
                jr   z, .no
                ld   a, 2
                call dg_rnd
                ld   hl, dg_mossi
                add  a, (hl)
                call dg_ld
                ld   a, 2
                ld   (dg_cmin), a
                ld   a, STOREY_ROWS
                ld   (dg_row), a
                ld   a, $FF
                call dg_msw
                or   a
                jr   z, .no
                call dg_rnd
                call dg_msw
                ld   (dg_col), a
                jp   dg_place
.no:            or   1
                ret
; dg_msw — A = k ($FF counts): one sweep of map rows 8..10 = can_place of the loaded moss strip at row
; 9 for every col at once (~0.3k T a col instead of ~1.8k T of dg_chk): a col's state is 00 (a ladder
; / decor id in rows 8..10: the ring), 01 (ring ok) or 11 (also footprint T_AIR + T_PLAT / T_WALLF
; above); col c fits iff the states of c-1 .. c+w read 01 (11)^w 01 (moss has no budget). -> CF: A =
; the k-th fitting col; NC: A = count. (Rows 8..10 of either map share one page: ASSERT below.)
dg_msw:
                ld   (dg_k), a
                ld   bc, STOREY_ROWS << 8 | 1
                call map_cell
                ld   b, dg_bad >> 8
                xor  a
                ld   (dg_win), a
                ld   (dg_win + 1), a
.x:             ld   a, l
                sub  ROOM_COLS
                ld   l, a                      ; row 8
                ld   a, (hl)
                add  a, dg_bad & $FF
                ld   c, a
                ld   a, (bc)
                ld   e, a                      ; ring bits
                ld   a, (hl)
                and  $FD
                sub  T_PLAT
                ld   d, a                      ; 0 = floor above
                ld   a, l
                add  a, ROOM_COLS
                ld   l, a                      ; row 9
                ld   a, (hl)
                or   d
                ld   d, a                      ; 0 = the footprint cell is ok
                ld   a, (hl)
                add  a, dg_bad & $FF
                ld   c, a
                ld   a, (bc)
                or   e
                ld   e, a
                ld   a, l
                add  a, ROOM_COLS
                ld   l, a                      ; row 10
                ld   a, (hl)
                add  a, dg_bad & $FF
                ld   c, a
                ld   a, (bc)
                or   e
                ld   e, a
                ld   a, l
                sub  ROOM_COLS
                ld   l, a                      ; row 9
                push hl
                ld   hl, (dg_win)
                add  hl, hl
                add  hl, hl
                ld   a, e
                and  3                         ; ladder / decor (not the air bit)
                jr   nz, .st
                inc  l
                ld   a, d
                or   a
                jr   nz, .st
                inc  l
                inc  l
.st:            ld   (dg_win), hl
                ld   a, (dg_w)
                cp   3
                ld   de, $007D                 ; w 2: 01 11 11 01
                jr   c, .pt
                ld   de, $01FD                 ; w 3: 01 11 11 11 01
.pt:            ld   a, l
                and  e
                cp   e
                jr   nz, .nc
                ld   a, h
                and  d
                cp   d
                jr   nz, .nc
                pop  hl
                push hl
                ld   a, l
                and  ROOM_COLS - 1             ; x = the window's last col (<= 30 by the loop)
                ld   c, a
                ld   a, (dg_w)
                ld   e, a
                ld   a, c
                sub  e                         ; candidate c = x - w >= 2
                cp   2
                jr   c, .nc
                call dg_kth
                jr   c, .hit
.nc:            pop  hl
                inc  l
                ld   a, l
                and  ROOM_COLS - 1
                cp   ROOM_COLS - 1
                jr   c, .x
                ld   a, (dg_k)
                cpl
                and  a
                ret
.hit:           pop  hl
                ret

; dg_fill — B = tries: R8 (legacy: the B3B-9 menu loop): o = rnd(n), col = cmin + rnd(33 - w - 2 cmin),
; s = rnd(2), r0 = rnd(6 - h) always; CALM: no mount / floor on storey 1; near-duplicate veto;
; 3-col halo for mount / floor; cmin 3 (moss 2; legacy 1).
dg_fill:
.t:             push bc
                ld   a, (dg_ncom)
                ld   hl, dg_nlev
                add  a, (hl)
                call dg_rnd
                ld   hl, dg_ncom
                cp   (hl)
                jr   c, .cm
                sub  (hl)
                ld   hl, dg_first
                add  a, (hl)
.cm:            call dg_ld
                ld   a, (dg_cls)
                cp   DC_PATCH
                jr   nc, .cx                   ; patch classes: the table's cmin
                ld   a, (dg_mood)
                cp   DM_LEG
                ld   a, 1
                jr   z, .cs
                ld   a, (dg_fl)
                and  F_MOSS
                jr   z, .cx
                ld   a, 2
.cs:            ld   (dg_cmin), a
.cx:            ld   a, (dg_cmin)
                ld   b, a
                add  a, a
                ld   c, a
                ld   a, 33
                ld   hl, dg_w
                sub  (hl)
                sub  c
                call dg_rnd
                add  a, b
                ld   (dg_col), a
                ld   a, 2
                call dg_rnd
                ld   (dg_s), a
                ld   a, (dg_h)
                neg
                add  a, 6
                call dg_rnd
                ld   c, a                      ; r0
                ld   a, (dg_mood)
                cp   DM_CALM
                jr   nz, .k
                ld   a, (dg_s)
                or   a
                jr   z, .k
                ld   a, (dg_cls)
                and  ~DC_FLOOR & $FF
                jr   z, .nx                    ; mount (0) / floor (2)
.k:             ld   a, (dg_s)
                push bc
                call dg_rowof
                pop  bc
                ld   a, (dg_cls)
                cp   DC_PATCH
                jr   c, .r
                ld   a, (dg_row)
                add  a, c
                ld   (dg_row), a
                jr   .go
.r:             ld   a, (dg_mood)
                cp   DM_LEG
                jr   z, .go
                call dg_dedup
                jr   z, .nx
                ld   a, (dg_cls)
                cp   DC_CEIL
                jr   z, .go
                ld   a, DG_HALO_FILL
                ld   (dg_halo), a
.go:            call dg_place
.nx:            pop  bc
                dec  b
                jp   nz, .t
                ret

; dg_dedup — Z = an id of the loaded record (top row: base .. base + w - 1, tiled: base) lies on dg_row
; in cols col - 7 .. col + w + 6: the same record within DG_DEDUP empty cols (same record = same row).
dg_dedup:
                ld   a, (dg_col)
                sub  DG_DEDUP + 1
                jr   nc, .a
                xor  a
.a:             ld   c, a
                ld   a, (dg_col)
                ld   hl, dg_w
                add  a, (hl)
                add  a, DG_DEDUP
                cp   ROOM_COLS
                jr   c, .b
                ld   a, ROOM_COLS - 1
.b:             sub  c
                inc  a
                ld   e, a
                ld   a, (dg_fl)
                and  F_TILED
                ld   a, 1
                jr   nz, .c
                ld   a, (hl)
.c:             ld   d, a
                ld   a, (dg_row)
                ld   b, a
                call map_cell
                ld   a, (dg_base)
                ld   c, a
.l:             ld   a, (hl)
                sub  c
                cp   d
                jr   c, .hit
                inc  hl
                dec  e
                jr   nz, .l
                or   1
                ret
.hit:           xor  a
                ret

; dg_cobwebs — R7: corner candidates scanned storey 0 then 1, cols 1..30; a candidate is placed unless
; rnd(odds) != 0 (odds 1: no draw): storey 0 1/2 (DARK always), storey 1 1/4 (DARK 1/2, LIT none,
; legacy 1/2); cap 2 (DARK 3).
dg_cobwebs:
                ld   a, (dg_cl)
                or   a
                ret  z
                ld   bc, 4 << 8 | 2
                ld   e, 2
                ld   a, (dg_mood)
                cp   DM_DARK
                jr   nz, .a
                ld   bc, 2 << 8 | 1
                inc  e
.a:             or   a
                jr   nz, .b
                ld   b, a
.b:             cp   DM_LEG
                jr   nz, .c
                ld   b, 2
.c:             ld   (dg_o0), bc               ; dg_o0 = C, dg_o1 = B
                ld   a, e
                ld   (dg_cap), a
                xor  a
                ld   (dg_nc), a
                ld   hl, 3 << 8 | 1
                ld   (dg_halo), hl             ; dg_halo 1, dg_rmask 3 (dg_cand's ring)
                ld   b, 0
.s:             ld   c, 1
                call map_cell                  ; HL = (row, 1): the row is walked by pointer
.cl:            ld   a, (hl)
                or   a
                jr   nz, .n                    ; T_AIR only
                dec  hl
                ld   a, (hl)
                inc  hl
                cp   T_BRICK
                jr   z, .t
                inc  hl
                ld   a, (hl)
                dec  hl
                cp   T_BRICK
                jr   nz, .n                    ; no brick beside it: not a corner (cheap reject)
.t:             push hl
                push bc
                call dg_cand
                or   a
                jr   z, .x
                ld   (dg_cg), a
                pop  bc
                push bc
                ld   a, b
                or   a
                ld   a, (dg_o0)
                jr   z, .o
                ld   a, (dg_o1)
.o:             cp   2
                jr   c, .pl
                call dg_rnd
                or   a
                jr   nz, .x
.pl:            pop  bc
                pop  hl
                ld   a, (dg_cg)
                ld   (hl), a
                push hl
                ld   a, b
                call dg_mark
                ld   a, (dg_cap)
                ld   e, a
                ld   hl, dg_nc
                inc  (hl)
                ld   a, (hl)
                pop  hl
                cp   e
                ret  nc
                jr   .n
.x:             pop  bc
                pop  hl
.n:             inc  hl
                inc  c
                ld   a, c
                cp   ROOM_COLS - 1
                jr   c, .cl
                ld   a, b
                or   a
                ret  nz
                ld   a, (dg_o1)
                or   a
                ret  z                         ; LIT: storey 0 only
                ld   b, STOREY_ROWS
                jr   .s

; dg_cand — B = row 9s, C = col -> A = the cobweb id if (B, C) is a corner candidate, else 0:
; T_AIR, ceiling above (map row 0 or T_PLAT / T_WALLF), col c-1 (left glyph) or else c+1
; (right glyph) T_BRICK in rows 9s..9s+2, ring free. Clobbers BC, DE, HL.
dg_cand:
                call map_cell
                ld   a, (hl)
                or   a
                jr   nz, .no
                ld   a, b
                or   a
                jr   z, .sup
                ld   de, -ROOM_COLS
                add  hl, de
                ld   a, (hl)
                and  $FD
                cp   T_PLAT
                jr   nz, .no
.sup:           push bc
                dec  c
                call dg_brk3
                pop  bc
                ld   a, (dg_cl)
                jr   z, .ring
                push bc
                inc  c
                call dg_brk3
                pop  bc
                jr   nz, .no
                ld   a, (dg_cr)
.ring:          push af
                ld   a, b
                ld   (dg_row), a
                ld   a, c
                ld   (dg_col), a
                ld   a, 1
                ld   (dg_h), a
                ld   (dg_w), a
                call dg_ring
                jr   nz, .nop
                pop  af
                ret
.nop:           pop  af
.no:            xor  a
                ret

; dg_brk3 — B = row, C = col: Z if (B..B+2, C) are all T_BRICK. Keeps BC.
dg_brk3:
                call map_cell
                ld   d, 3
.l:             ld   a, (hl)
                cp   T_BRICK
                ret  nz
                call dg_nr
                dec  d
                jr   nz, .l
                ret

;------------------------------------------------------------------------------
; the structure queries (row 3 of storey dg_s)
;------------------------------------------------------------------------------
; dg_scan — the air-like runs of row 3 of storey dg_s -> DG_PLAN (a, b) pairs x dg_nrun (<= 8;
; real rooms have <= 3), dg_r3 = its map row. Clobbers A, BC, DE, HL.
dg_scan:
                ld   a, (dg_s)                 ; the runs of the storey already in DG_PLAN: kept (they are the
                inc  a                         ; pre-decor structure, so a rescan gives the same list)
                ld   hl, dg_scs
                cp   (hl)
                ret  z
                ld   (hl), a
                dec  a
                call dg_9s
                add  a, 3
                ld   (dg_r3), a
                ld   b, a
                ld   c, 0
                call map_cell                  ; row 3 / 12: L & 31 = the col (rows are 32-aligned)
                ld   de, DG_PLAN
                xor  a
                ld   (dg_nrun), a
                ld   b, dg_bad >> 8
.l:             ld   a, (hl)                   ; air-like = dg_bad bit 2 (T_AIR or a decor id)
                add  a, dg_bad & $FF
                ld   c, a
                ld   a, (bc)
                and  4
                jr   z, .nx
                ld   a, l
                and  ROOM_COLS - 1
                ld   (de), a                   ; a
                inc  de
.r:             inc  l
                ld   a, l
                and  ROOM_COLS - 1
                jr   z, .e
                ld   a, (hl)
                add  a, dg_bad & $FF
                ld   c, a
                ld   a, (bc)
                and  4
                jr   nz, .r
.e:             ld   a, l
                dec  a
                and  ROOM_COLS - 1
                ld   (de), a                   ; b
                inc  de
                ld   a, (dg_nrun)
                inc  a
                ld   (dg_nrun), a
                cp   DG_PLAN_LEN / 2
                ret  z
                ld   a, l
                and  ROOM_COLS - 1
                ret  z
.nx:            inc  l
                ld   a, l
                and  ROOM_COLS - 1
                jr   nz, .l
                ret

; dg_face — A = k ($FF counts): the faces of the dg_scan runs in the model's order (per run: L = its
; first col if a >= 1, R = its last if b <= 30) of runs >= dg_fmin cols; dg_fwall: wall kind only (the
; cell beyond is no ladder) -> CF: A = edge col, B = side (0 L, 1 R); NC: A = count.
dg_face:
                ld   (dg_k), a
                ld   hl, DG_PLAN
                ld   a, (dg_nrun)
.run:           or   a
                jr   z, .cnt
                push af
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                push hl
                ld   a, d
                sub  e
                inc  a
                ld   hl, dg_fmin
                cp   (hl)
                jr   c, .nx
                ld   a, e
                or   a
                jr   z, .r
                dec  a
                call dg_fok
                jr   c, .r
                ld   a, e
                ld   b, 0
                call dg_kth
                jr   c, .hit
.r:             ld   a, d
                cp   ROOM_COLS - 1
                jr   nc, .nx
                inc  a
                call dg_fok
                jr   c, .nx
                ld   a, d
                ld   b, 1
                call dg_kth
                jr   c, .hit
.nx:            pop  hl
                pop  af
                dec  a
                jr   .run
.hit:           pop  hl
                pop  hl
                ret
.cnt:           ld   a, (dg_k)
                cpl
                and  a
                ret
; dg_fok — A = the row-3 col beside a run: CF = refused (dg_fwall and a ladder cell). Keeps DE.
dg_fok:
                ld   c, a
                ld   a, (dg_fwall)
                or   a
                ret  z
                ld   a, (dg_r3)
                ld   b, a
                call map_cell
                ld   a, (hl)
                sub  T_LAD_L
                cp   6
                ret

; dg_foc — A = k ($FF counts), C = FK_* kinds: the focal list in the model's order (the interior
; obstacles of row 3 = the gaps between the dg_scan runs, ladder if one of its cells is; storey 0: 3
; T_RUBBLE in map row 0 = the arrival, storey 1: T_HOLE_L/M/R in row 17 = the shaft, cols 1..28;
; storey 0: the pit) -> CF: A = col, B = width; NC: A = count.
dg_foc:
                ld   (dg_k), a
                ld   a, c
                ld   (dg_fmask), a
                ld   a, (dg_nrun)
                or   a
                jr   z, .ex
                dec  a
                jr   z, .ex
                ld   hl, DG_PLAN + 1           ; b of run 0
.g:             push af
                ld   a, (hl)
                inc  a
                ld   c, a                      ; gap start
                inc  hl
                ld   a, (hl)
                inc  hl                        ; HL -> b of the next run
                sub  c
                ld   b, a                      ; width
                push hl
                push bc
                ld   a, (dg_r3)
                ld   b, a
                call map_cell
                pop  bc
                push bc
                ld   e, FK_BLOCK
.lk:            ld   a, (hl)
                sub  T_LAD_L
                cp   6
                jr   nc, .nl
                ld   e, FK_LAD
.nl:            inc  hl
                djnz .lk
                pop  bc
                ld   a, (dg_fmask)
                and  e
                jr   z, .ng
                ld   a, c
                call dg_kth
                jr   c, .hit2
.ng:            pop  hl
                pop  af
                dec  a
                jr   nz, .g
.ex:            ld   a, (dg_s)
                or   a
                ld   bc, FK_ARR << 8 | 0       ; B = kind, C = map row
                ld   de, T_RUBBLE << 8 | 0     ; D = first id, E = id step
                jr   z, .as
                ld   bc, FK_SHAFT << 8 | (PLAY_ROWS - 1)
                ld   de, T_HOLE_L << 8 | 1
.as:            ld   a, (dg_fmask)
                and  b
                jr   z, .pit
                ld   b, c
                ld   c, 1
.al:            call map_cell
                ld   a, d
                cp   (hl)
                jr   nz, .an
                add  a, e
                inc  hl
                cp   (hl)
                jr   nz, .an
                add  a, e
                inc  hl
                cp   (hl)
                jr   nz, .an
                ld   a, c
                push bc
                call dg_kth
                pop  bc
                jr   nc, .an
                ld   b, 3
                ret
.an:            inc  c
                ld   a, c
                cp   ROOM_COLS - 3
                jr   c, .al
.pit:           ld   a, (dg_s)
                or   a
                jr   nz, .cnt
                ld   a, (dg_fmask)
                and  FK_PIT
                jr   z, .cnt
                ld   a, (dg_pitw)
                or   a
                jr   z, .cnt
                ld   b, a
                ld   a, (dg_pit)
                call dg_kth
                ret  c
.cnt:           ld   a, (dg_k)
                cpl
                and  a
                ret
.hit2:          pop  hl
                pop  hl
                ret

; dg_span — the widest dg_scan run clipped to cols 3..28 (>= 3 cols; the first widest), shrunk by 1
; -> NC: D = lo, E = hi; CF = none.
dg_span:
                ld   a, (dg_nrun)
                or   a
                scf
                ret  z
                ld   b, a
                ld   c, 1                      ; best hi - lo (a run needs >= 2)
                ld   hl, DG_PLAN
.l:             ld   a, (hl)
                inc  hl
                cp   3
                jr   nc, .a
                ld   a, 3
.a:             ld   (dg_t3), a                ; lo
                ld   a, (hl)
                inc  hl
                cp   29
                jr   c, .b
                ld   a, 28
.b:             push hl
                ld   hl, dg_t3
                sub  (hl)
                jr   c, .n
                cp   c
                jr   c, .n
                jr   z, .n
                ld   c, a
                ld   d, (hl)
                add  a, d
                ld   e, a
.n:             pop  hl
                djnz .l
                ld   a, c
                dec  a
                scf
                ret  z
                inc  d
                dec  e
                and  a
                ret

; dg_kth — A = a candidate: CF if it is the k-th (dg_k counts down; A kept). Clobbers C, HL.
dg_kth:
                ld   hl, dg_k
                ld   c, a
                ld   a, (hl)
                dec  (hl)
                cp   1
                ld   a, c
                ret

;------------------------------------------------------------------------------
; placement: check (bounds, budgets, footprint, support, pit zone, ring), then write
;------------------------------------------------------------------------------
; dg_group — the loaded object at dg_row, cols dg_gc[0 .. dg_gn-1], all or none: every item is
; checked with the earlier items' budgets counted, then all are written. -> Z placed.
dg_group:
                ld   hl, (dg_nl)               ; dg_nl, dg_ng
                push hl
                ld   a, (dg_nw)
                push af
                ld   hl, dg_gc
                ld   a, (dg_gn)
                ld   b, a
.c:             push bc
                push hl
                ld   a, (hl)
                ld   (dg_col), a
                call dg_chk
                jr   nz, .f
                call dg_cnt
                pop  hl
                pop  bc
                inc  hl
                djnz .c
                pop  af
                pop  hl
                ld   hl, dg_gc
                ld   a, (dg_gn)
                ld   b, a
.w:             push bc
                push hl
                ld   a, (hl)
                ld   (dg_col), a
                call dg_cells
                pop  hl
                pop  bc
                inc  hl
                djnz .w
                xor  a
                ret
.f:             pop  hl
                pop  bc
                pop  af
                ld   (dg_nw), a
                pop  hl
                ld   (dg_nl), hl
                or   1
                ret

; dg_place — the loaded object at (dg_row, dg_col) if it fits -> Z placed.
dg_place:
                call dg_chk
                ret  nz
                call dg_cnt
                call dg_cells
                xor  a
                ret

; dg_chk — bounds (cmin .. 31 - cmin), budgets (<= 2 large, 4 glyph cols, the wall budget), footprint
; T_AIR, support (ceiling: every cell under T_PLAT / T_WALLF, map row 0 not for moss; floor: every cell
; on them + the R3 pit jump zone), ring (dg_halo cols, dg_rmask) -> Z fits. Clobbers A, BC, DE, HL.
dg_chk:
                ld   a, (dg_cmin)
                ld   b, a
                ld   a, (dg_col)
                cp   b
                jr   c, .no
                ld   c, a
                ld   a, ROOM_COLS
                sub  b
                ld   hl, dg_w
                sub  (hl)
                cp   c
                jr   c, .no                    ; col > 32 - cmin - w (a "negative" col too)
                ld   a, (dg_fl)
                rlca
                ld   a, (dg_nl)
                adc  a, 0
                cp   DG_MAX_LARGE + 1
                jr   nc, .no
                ld   a, (dg_dg)
                ld   hl, dg_ng
                add  a, (hl)
                cp   DG_MAX_GLYPH + 1
                jr   nc, .no
                ld   a, (dg_cls)
                cp   DC_PATCH
                jr   c, .fit
                ld   a, (dg_nw)
                ld   hl, dg_area
                add  a, (hl)
                ld   hl, dg_wmax
                cp   (hl)
                jr   c, .fit
.no:            or   1
                ret
.fit:           ld   a, (dg_row)
                ld   b, a
                call map_cell
                ld   a, (dg_h)
                ld   d, a
.ir:            push hl
                ld   a, (dg_w)
                ld   b, a
.ic:            ld   a, (hl)
                or   a
                jr   nz, .nop
                inc  hl
                djnz .ic
                pop  hl
                call dg_nr
                dec  d
                jr   nz, .ir
                ld   a, (dg_cls)
                dec  a
                jr   z, .ce
                dec  a
                jr   nz, dg_ring
                ld   a, (dg_row)               ; floor
                ld   hl, dg_h
                add  a, (hl)
                call dg_sup
                ret  nz
                ld   a, (dg_pitw)
                or   a
                jr   z, dg_ring
                ld   e, a
                ld   a, (dg_row)
                cp   STOREY_ROWS
                jr   nc, dg_ring
                ld   a, (dg_pit)
                ld   d, a
                add  a, e
                add  a, PIT_AFTER
                ld   e, a                      ; p + W + 3
                ld   a, (dg_col)
                ld   hl, dg_w
                add  a, (hl)
                add  a, PIT_BEFORE - 1
                cp   d
                jr   c, dg_ring                ; col + w - 1 < p - 4
                ld   a, e
                ld   hl, dg_col
                cp   (hl)
                jr   c, dg_ring                ; col > p + W + 3
                or   1                         ; in the jump zone
                ret
.nop:           pop  hl
                ret
.ce:            ld   a, (dg_row)
                or   a
                jr   nz, .c1
                ld   a, (dg_fl)
                and  F_MOSS
                ret  nz                        ; row 0: a chain may, moss may not
                jr   dg_ring
.c1:            dec  a
                call dg_sup
                ret  nz
; dg_ring — rows row-1 .. row+h, cols col-halo .. col+w-1+halo (clipped to the map) hold no id with
; dg_bad & dg_rmask -> Z ok (~55 T a cell). Clobbers A, BC, DE, HL.
dg_ring:
                ld   a, (dg_row)
                or   a
                jr   z, .rl
                dec  a
.rl:            ld   b, a
                ld   a, (dg_row)
                ld   hl, dg_h
                add  a, (hl)
                sub  b
                inc  a
                ld   (dg_rows), a
                ld   a, (dg_halo)
                ld   e, a
                ld   a, (dg_col)
                sub  e
                jr   nc, .cl
                xor  a
.cl:            ld   c, a
                ld   a, (dg_col)
                ld   hl, dg_w
                add  a, (hl)
                dec  a
                add  a, e
                cp   ROOM_COLS
                jr   c, .ch
                ld   a, ROOM_COLS - 1
.ch:            sub  c
                inc  a
                ld   (dg_cc), a
                call map_cell
                ld   a, (dg_rmask)
                ld   d, a
.rr:            push hl
                ld   a, (dg_cc)
                ld   e, a
                ld   b, dg_bad >> 8
.rc:            ld   a, (hl)
                add  a, dg_bad & $FF           ; id < 64, the table does not cross a page (ASSERT)
                ld   c, a
                ld   a, (bc)
                and  d
                jr   nz, .bad
                inc  hl
                dec  e
                jr   nz, .rc
                pop  hl
                call dg_nr
                ld   a, (dg_rows)
                dec  a
                ld   (dg_rows), a
                jr   nz, .rr
                ret
.bad:           pop  hl
                ret
; dg_sup — A = row: Z if cols dg_col .. +w-1 of it are T_PLAT / T_WALLF.
dg_sup:
                ld   b, a
                ld   a, (dg_col)
                ld   c, a
                call map_cell
                ld   a, (dg_w)
                ld   b, a
.l:             ld   a, (hl)
                and  $FD                       ; T_WALLF (3) -> T_PLAT (1)
                cp   T_PLAT
                ret  nz
                inc  hl
                djnz .l
                ret

; dg_cnt — count the loaded object into the budgets (large, glyph cols, wall cells).
dg_cnt:
                ld   a, (dg_fl)
                rlca
                ld   a, (dg_nl)
                adc  a, 0
                ld   (dg_nl), a
                ld   hl, dg_dg
                ld   a, (dg_ng)
                add  a, (hl)
                ld   (dg_ng), a
                ld   a, (dg_cls)
                cp   DC_PATCH
                ret  c
                ld   a, (dg_nw)
                ld   hl, dg_area
                add  a, (hl)
                ld   (dg_nw), a
                ret

; dg_cells — write the loaded object at (dg_row, dg_col): row-major ids (tiled: one id), the ANIM
; entries (dg_cell), the storey's decor bit, a light's record (col, row, w) for the pools.
dg_cells:
                ld   a, (dg_row)
                call dg_mark
                ld   a, (dg_cls)
                cp   DC_COMP
                jr   nz, .pk
                ld   a, (dg_row)               ; composite: PATCH FADE / DITHER
                ld   b, a
                ld   a, (dg_col)
                ld   c, a
                call map_cell
                ld   (hl), T_WALL_PATCH
                inc  hl
                ld   (hl), T_WALL_FADE
                dec  hl
                call dg_nr
                ld   (hl), T_WALL_DITHER
                ret
.pk:            ld   a, (dg_fl)
                and  F_TILED
                xor  F_TILED
                rrca
                ld   (dg_step), a              ; id step per cell: 1, tiled 0
                ld   a, (dg_base)
                ld   (dg_id), a
                ld   hl, dg_area
                add  a, (hl)
                ld   (dg_alt), a               ; first glyph-swap alternate id
                ld   a, (dg_col)
                ld   hl, dg_row
                add  a, (hl)
                and  7
                ld   (dg_ph), a
                ld   a, (dg_row)
                ld   b, a
                ld   d, 0                      ; dy
.pr:            ld   a, (dg_col)
                ld   c, a
                ld   e, 0                      ; dx
.pc:            call map_cell
                ld   a, (dg_id)
                ld   (hl), a
                ld   hl, dg_step
                add  a, (hl)
                ld   (dg_id), a
                call dg_cell
                inc  c
                inc  e
                ld   a, (dg_w)
                cp   e
                jr   nz, .pc
                inc  b
                inc  d
                ld   a, (dg_h)
                cp   d
                jr   nz, .pr
                ld   a, (dg_fl)
                rlca
                ret  nc
                ld   hl, dg_nlr
                ld   a, (hl)
                inc  (hl)
                ld   c, a
                add  a, a
                add  a, c
                inc  a                         ; dg_lr follows dg_nlr (one page: ASSERT)
                add  a, l
                ld   l, a
                ld   a, (dg_col)
                ld   (hl), a
                inc  l
                ld   a, (dg_row)
                ld   (hl), a
                inc  l
                ld   a, (dg_w)
                ld   (hl), a
                ret

; dg_mark — A = map row: set its storey's bit in dg_used (bit 0 storey 0, bit 1 storey 1). Clobbers A, HL.
dg_mark:
                cp   STOREY_ROWS
                ld   a, 2
                sbc  a, 0
                ld   hl, dg_used
                or   (hl)
                ld   (hl), a
                ret

; dg_cell — B = row, C = col, D = dy, E = dx of a just-placed cell: append its
; ANIM_LIST entry (col, row, type, phase) if the object animates it. Keeps BC, DE.
dg_cell:
                ld   a, (dg_fl)
                bit  2, a                      ; flag bit 2: the object swaps glyphs at all (row 0)
                ret  z
                ld   l, a
                ld   a, d
                or   a
                jr   z, .go                    ; row 0: every cell swaps
                dec  a
                ret  nz                        ; only the top two cell rows ever animate
                ld   a, l                      ; half-row flames: row 1 (2-wide objects only):
                bit  3, a                      ;   flag bit 3 = the whole lower flame row,
                jr   nz, .go
                bit  4, a                      ;   bit 4 = only its left cell (dx = 0)
                ret  z
                ld   a, e
                or   a
                ret  nz
.go:            ld   hl, dg_alt
                ld   a, (hl)                   ; type = alternate tile id (>= 16)
                inc  (hl)
                push de
                ld   d, a
                ld   a, (dg_dst0)              ; ANIM_N or ANIM_N2
                ld   l, a
                ld   h, ANIM_N >> 8
                ld   a, (hl)
                inc  (hl)
                add  a, a
                add  a, a
                inc  a                         ; the entries follow their count byte
                add  a, l                      ; <= 12 entries: no carry (ASSERT)
                ld   l, a
                ld   (hl), c
                inc  l
                ld   (hl), b
                inc  l
                ld   (hl), d
                inc  l
                ld   a, (dg_ph)
                ld   (hl), a
                pop  de
                ret

;------------------------------------------------------------------------------
; small helpers
;------------------------------------------------------------------------------
; dg_rowof — A = storey: dg_row = the loaded object's row (mount / patch 9s + 1, ceiling 9s, floor
; 9s + 8 - h). Clobbers A, B, C, HL.
dg_rowof:
                call dg_9s
                ld   b, a
                ld   a, (dg_cls)
                cp   DC_CEIL
                jr   z, .c
                cp   DC_FLOOR
                ld   a, 1
                jr   nz, .c1
                ld   a, 8
                ld   hl, dg_h
                sub  (hl)
.c1:            add  a, b
                ld   b, a
.c:             ld   a, b
                ld   (dg_row), a
                ret
; dg_9s — A = storey -> A = 9 * storey. Clobbers C.
dg_9s:
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                ret
; dg_idx — A = index, HL = byte list -> A = list[index]. Clobbers HL.
dg_idx:
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
                ret
; dg_ld — A = record index: dg_rec + dg_load. dg_rec — A -> HL = &dg_recs[A] (3 B). Clobbers A, HL.
dg_ld:
                call dg_rec
                jr   dg_load
dg_rec:
                ld   l, a
                add  a, a
                add  a, l
                add  a, dg_recs & $FF
                ld   l, a
                adc  a, dg_recs >> 8
                sub  l
                ld   h, a
                ret
; dg_load — HL = record: dg_base / w / h / cls / fl / area / dg (glyph cols); defaults dg_halo 1,
; dg_rmask 3, dg_cmin = dg_cmint[cls]. Clobbers A, BC, DE, HL.
dg_load:
                ld   a, (hl)
                inc  hl
                ld   (dg_base), a
                ld   a, (hl)                   ; w | h << 2 | class << 5
                inc  hl
                ld   c, (hl)                   ; flags
                ld   b, a
                and  3
                ld   (dg_w), a
                ld   d, a
                ld   a, b
                rlca
                rlca
                rlca
                and  7
                ld   (dg_cls), a
                ld   e, a
                ld   a, b
                rrca
                rrca
                and  7
                ld   (dg_h), a
                ld   b, a
                xor  a
.ar:            add  a, d                      ; area = w * h
                djnz .ar
                ld   b, a
                ld   a, e
                cp   DC_COMP
                ld   a, b
                jr   nz, .ar2
                ld   a, 3                      ; the composite patch writes 3 of its 4 cells
.ar2:           ld   (dg_area), a
                ld   a, c
                ld   (dg_fl), a
                xor  a
                bit  2, c
                jr   z, .g
                ld   a, d                      ; glyph-swap objects cost w columns
.g:             ld   (dg_dg), a
                ld   hl, 3 << 8 | 1
                ld   (dg_halo), hl             ; dg_halo 1, dg_rmask 3
                ld   d, 0
                ld   hl, dg_cmint
                add  hl, de
                ld   a, (hl)
                ld   (dg_cmin), a
                ret
; dg_nr — HL += 32 (next map row, same col).
dg_nr:          ld   a, ROOM_COLS
                add  a, l
                ld   l, a
                ret  nc
                inc  h
                ret

; dg_rnd — A = n -> A = (step & $FF) mod n; keeps BC, DE; clobbers HL.
dg_rnd:
                push bc
                ld   c, a
                ld   hl, (dg_rng)              ; xorshift 7,9,8 (= levelgen lg_step; bank-2 xs_core)
                call xs_core
                ld   (dg_rng), hl
                ld   a, c                      ; levelgen rnd_mod: n = 1 -> 0, n = 2 -> L & 1, else L mod n
                dec  a
                jr   z, .z
                dec  a
                jr   nz, .g
                ld   a, l
                and  1
                pop  bc
                ret
.z:             pop  bc                        ; A = 0
                ret
.g:             ld   a, c                      ; n < 32: subtract 8n first (<= ~19 subtractions, was <= 85)
                cp   32
                ld   a, l
                jr   nc, .m
                ld   a, c
                add  a, a
                add  a, a
                add  a, a
                ld   b, a
                ld   a, l
.m8:            sub  b
                jr   nc, .m8
                add  a, b
.m:             sub  c
                jr   nc, .m
                add  a, c
                pop  bc
                ret

; SIZE T3: dg_ring adds the id (< 64) to dg_bad's low byte with B = its page, so the 64-B table
; must not cross a page: it goes before the generated tables if it fits there, else after them.
DGB_EARLY = (($ & $FF) <= 256 - TILE_IDS)
    IF DGB_EARLY
                INCLUDE "dg_bad2.asm"           ; GENERATED: tools/decorgen2.py --asm-bad
    ENDIF
; GENERATED by tools/decorgen2.py --asm (edit the tool, re-run, paste)
; record (3 B): base id | w + h*4 + class*32 | flags (bit0 moss, 1 tiled, 2 glyph row 0, 3 glyph row 1 too,
;                 4 only its col 0, 7 large animated); class 0 mount, 1 ceiling, 2 floor, 3 patch, 5 composite
; records 0..3 = the legacy commons (CHAIN + the 3 1x1 patches), 4..7 = the legacy D1 block (D0 / PROTO
; levels: LVL_KEYROOM = ROOM_NONE, tools/decorgen.py); then per depth menu2 minus CHAIN (MOSS = w 2, w 3)
DG_LEG_FIRST    EQU 4
DG_LEG_N        EQU 8
dg_dtab:        ; per depth (DG_DTAB B, = the dg_vars order dg_wmax .. dg_nlev): wall budget + 1,
;                 PATCH_A/B records (0 = composite), pair light record (| $80 floor class),
;                 cobweb left / right id (0 = none), first record, record count
                DEFB   7,   0,   8,  57,  59,   8,   5     ; D1
                DEFB  14,   2, 144,  52,  54,  13,   8     ; D2
                DEFB   7,   1, 150,  58,  59,  21,   4     ; D3
                DEFB   7,   1,  26,   0,   0,  25,   3     ; D4
                DEFB   7,   1, 157,   0,   0,  28,   3     ; D5
                DEFB   7,   2,  33,  50,  52,  31,   8     ; D6
                DEFB   7,   1,  40,   0,   0,  39,   3     ; D7
                DEFB   7,   0, 170,  58,  59,  42,   4     ; D8
DG_DTAB         EQU 7
dg_crec:        ; the composite patch record (D1 / D8)
                DEFB 0, 170, 0
dg_recs:
                DEFB  12,  41, $02      ;  0 common CHAIN
                DEFB  28, 101, $00      ;  1 common WALL_DITHER
                DEFB  29, 101, $00      ;  2 common WALL_PATCH
                DEFB  30, 101, $00      ;  3 common WALL_FADE
                DEFB  32,  18, $94      ;  4 legacy D1 TORCH_TALL
                DEFB  43,  19, $00      ;  5 legacy D1 WINDOW_ARCH
                DEFB  55,   9, $00      ;  6 legacy D1 BANNER
                DEFB  58,  37, $01      ;  7 legacy D1 MOSS
                DEFB  32,  18, $94      ;  8 D1 TORCH_TALL
                DEFB  43,  19, $00      ;  9 D1 WINDOW_ARCH
                DEFB  55,   9, $00      ; 10 D1 BANNER
                DEFB  58,  38, $03      ; 11 D1 MOSS2
                DEFB  58,  39, $03      ; 12 D1 MOSS3
                DEFB  32, 106, $00      ; 13 D2 PATCH_A
                DEFB  36, 107, $00      ; 14 D2 PATCH_B
                DEFB  42,  13, $84      ; 15 D2 TORCH_SLIM
                DEFB  46,  73, $84      ; 16 D2 BRAZIER
                DEFB  49,  10, $02      ; 17 D2 WINDOW_BAR
                DEFB  50,   9, $00      ; 18 D2 BANNER
                DEFB  53,  38, $03      ; 19 D2 MOSS2
                DEFB  53,  39, $03      ; 20 D2 MOSS3
                DEFB  53, 106, $00      ; 21 D3 PATCH_A
                DEFB  32,  82, $94      ; 22 D3 BRAZIER_BIG
                DEFB  43,  22, $00      ; 23 D3 BANNER_TALL
                DEFB  57,  10, $02      ; 24 D3 BOOKSHELF
                DEFB  53, 106, $00      ; 25 D4 PATCH_A
                DEFB  32,  18, $94      ; 26 D4 TORCH_TALL
                DEFB  43,  22, $00      ; 27 D4 BANNER_TALL
                DEFB  55, 106, $00      ; 28 D5 PATCH_A
                DEFB  32,  82, $94      ; 29 D5 BRAZIER_BIG
                DEFB  43,  19, $00      ; 30 D5 WINDOW_ARCH
                DEFB  39, 106, $00      ; 31 D6 PATCH_A
                DEFB  43, 107, $00      ; 32 D6 PATCH_B
                DEFB  32,  13, $84      ; 33 D6 TORCH_SLIM
                DEFB  36,  10, $02      ; 34 D6 BOOKSHELF
                DEFB  37,   9, $00      ; 35 D6 BANNER
                DEFB  49,  10, $02      ; 36 D6 WINDOW_BAR
                DEFB  51,  38, $03      ; 37 D6 MOSS2
                DEFB  51,  39, $03      ; 38 D6 MOSS3
                DEFB  53, 107, $00      ; 39 D7 PATCH_B
                DEFB  32,  18, $94      ; 40 D7 TORCH_TALL
                DEFB  43,  22, $00      ; 41 D7 BANNER_TALL
                DEFB  32,  82, $94      ; 42 D8 BRAZIER_BIG
                DEFB  43,  10, $02      ; 43 D8 BOOKSHELF
                DEFB  44,  22, $00      ; 44 D8 BANNER_TALL
                DEFB  54,  13, $84      ; 45 D8 TORCH_SLIM
DG_NREC         EQU 46
dg_cmint:       DEFB 3, 3, 3, 2, 0, 2     ; R3 col minimum by class (mount ceiling floor patch brick composite)
    IF !DGB_EARLY
                INCLUDE "dg_bad2.asm"           ; GENERATED: tools/decorgen2.py --asm-bad
    ENDIF
                ASSERT (dg_bad >> 8) == ((dg_bad + TILE_IDS - 1) >> 8)
; state: the low-RAM DS block dg_vars (lowram.asm; B0_CODE2 holds no runtime-written bytes).
                ASSERT T_AIR == 0 && T_BRICK == 2 && F_MOSS == 1 && F_TILED == 2
                ASSERT T_HOLE_R == T_LAD_L + 5 && ANIM_MAX == 12 && AL_STRIDE == 4
                ASSERT (ANIM_N >> 8) == ((ANIM_LIST + ANIM_MAX * AL_STRIDE) >> 8) && PLAY_ROWS == 18
                ASSERT (ANIM_N2 >> 8) == ((ANIM_LIST2 + ANIM_MAX * AL_STRIDE) >> 8) && ANIM_LIST2 == ANIM_N2 + 1
                ASSERT T_PLAT == 1 && T_WALLF == 3 && STOREY_ROWS == 9 && FLOOR_ROW0 == 8
                ASSERT TILE_IDS == 64 && DG_NREC * 3 < 256 && (dg_recs - dg_crec) == 3
                ASSERT T_CHAIN == 12 && T_GLOW == 31 && T_LVL_OBJ == 60 && T_WALL_DITHER == DG_ID_LO
                ASSERT RDF_DEADEND == 1 << DG_DEADEND_BIT && ROOM_NONE == $FF && DG_LEG_N == 2 * DG_LEG_FIRST
                ASSERT (ROOM_DESC & $0F) == 0 && RD_STRIDE == 16 && ROOM_SLOTS <= 16
                ASSERT (ROOM_MAP & $FF) == 0 && (NEXT_MAP & $FF) == 0 && 11 * ROOM_COLS <= 2 * 256 && 8 * ROOM_COLS >= 256
                ASSERT DG_PLAN_LEN == 16
