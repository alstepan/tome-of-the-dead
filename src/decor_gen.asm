;==============================================================================
; decor_gen.asm — B3B-9: the decor deriver (bank 3, cold). INCLUDEd by
; src/bank3.asm as the body of `decor_room`; the algorithm, the object menu and
; the ANIM_LIST contract for B3B-10 are specified in tools/decorgen.py (the
; Python reference; test W13 compares ROOM_MAP + ANIM_LIST byte for byte).
;
; decor_room: A = room (unused), IX = descriptor (kept), (TMP1) = map page.
;   Re-derived from RD_SEED only (own xorshift state dg_rng, never GEN_RNG /
;   RNG_STATE), so re-entry rebuilds the identical map. The animated cells go
;   to the list build_room_map chose by the map page (dg_dst, count already
;   zeroed): ROOM_MAP -> ANIM_N / ANIM_LIST, NEXT_MAP -> ANIM_N2 / ANIM_LIST2
;   (B3B-9 review: do_exit's room_shadow copies it over ANIM_LIST after the
;   scroll; before, the NEXT_MAP build left the old room's list live).
;   D1 (concept-screen 3.3 "Decor placement (D1)"): (1) dg_patches: >= 1 back-wall
;   patch (+ a 2nd at 50 %), (2) dg_cobwebs: corner cobwebs, (3) 12 menu attempts x 4 rnd
;   calls (o, col, storey, r0; the row comes from the object class: mount row 1, ceiling
;   row 0, floor row 7 at the bottom, patch / brick 1 + r0), (4) dg_drips. An attempt
;   places one object iff the budgets (<= 2 large animated, 4 glyph + 8 attr cells, 6
;   patch / brick cells), the footprint (T_AIR; T_BRICK for the pillar), the class
;   support (T_PLAT / T_WALLF above a ceiling object / below a floor object) and the ring
;   (no ladder, no other decor: dg_bad) allow. ANIM_LIST contract: see tools/decorgen.py.
; Clobbers: A, BC, DE, HL.  Cold path (room entry): D1 measured ~120k T (W13 profile,
; DI, contended): patches ~24k, cobwebs ~10k, menu ~64k, drips ~23k.
;==============================================================================
F_MOSS          EQU 1               ; record flags (tools/decorgen.py)
F_TILED         EQU 2
DG_TRIES        EQU 12
DG_MAX_LARGE    EQU 2
DG_MAX_GLYPH    EQU 4
DG_MAX_ATTR     EQU 8
DG_MAX_WALL     EQU 6
DG_PTRIES       EQU 8
DG_MAX_COB      EQU 2
DC_CEIL         EQU 1               ; object classes (record wh byte bits 5..7)
DC_FLOOR        EQU 2
DC_PATCH        EQU 3
DC_BRICK        EQU 4
DC_COMP         EQU 5
                ld   l, (ix + RD_SEED)
                ld   h, (ix + RD_SEED + 1)
                ld   (dg_rng), hl
                xor  a
                ld   (dg_nl), a
                ld   (dg_ng), a
                ld   (dg_na), a
                ld   (dg_nw), a
                ld   a, (LVL_DEPTH)
                dec  a
                ld   e, a
                ld   d, 0
                ld   hl, dg_start
                add  hl, de
                ld   a, (hl)
                ld   (dg_first), a
                ld   c, a
                inc  hl
                ld   a, (hl)
                sub  c
                add  a, DG_NCOM
                ld   (dg_n), a                 ; menu size = common + this depth's
                call dg_patches                ; D1: patches, then cobwebs, then the menu
                call dg_cobwebs
                ld   b, DG_TRIES
.t:             push bc
                call dg_try
                pop  bc
                djnz .t
                jp   dg_drips                  ; B3B-13b: drips go last (same dg_rng)

; dg_rec — A = record index -> HL = &dg_recs[A] (3 B records). Clobbers A, C, DE.
dg_rec:
                ld   c, a
                add  a, a
                add  a, c
                ld   e, a
                ld   d, 0
                ld   hl, dg_recs
                add  hl, de
                ret

; dg_try — one menu attempt (the 4 rnd calls always happen: o, col, s, r0).
dg_try:
                ld   a, (dg_n)
                call dg_rnd
                cp   DG_NCOM
                jr   c, .cm
                sub  DG_NCOM
                ld   hl, dg_first
                add  a, (hl)
.cm:            call dg_rec

; dg_obj — HL = record: load it, 3 more rnd calls (col, storey, r0), place it if
; the budgets, footprint, class support and ring allow (dg_ok = 1 then).
dg_obj:
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
                ld   a, (dg_cls)
                cp   DC_COMP
                ld   a, b
                jr   nz, .ar2
                ld   a, 3                      ; the composite patch writes 3 of its 4 cells
.ar2:           ld   (dg_area), a
                ld   a, c
                ld   (dg_fl), a
                ; col = cmin + rnd(33 - w - 2 * cmin)
                ld   a, (dg_cls)
                ld   e, a
                ld   d, 0
                ld   hl, dg_cmin
                add  hl, de
                ld   b, (hl)                   ; B = cmin
                ld   a, 33
                ld   hl, dg_w
                sub  (hl)
                sub  b
                sub  b
                call dg_rnd                    ; (keeps BC, DE)
                add  a, b
                ld   (dg_col), a
                ld   a, 2
                call dg_rnd
                ld   e, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e                      ; 9 * storey
                ld   e, a
                ld   a, 6
                ld   hl, dg_h
                sub  (hl)
                ld   c, a                      ; r0 (patch / brick / composite only): else the
                ld   a, (dg_cls)               ; step is taken without the mod loop
                cp   DC_PATCH
                jr   c, .nr0
                ld   a, c
                call dg_rnd
                inc  a                         ; patch / brick / composite: row 1 + r0
                jr   .o
.nr0:           ld   a, 2                      ; the value is unused: n = 2 skips the mod loop
                call dg_rnd
                ld   a, (dg_cls)
                jr   .nr
.nr:            or   a
                ld   a, 1                      ; mount: top row 1
                jr   z, .o
                ld   a, (dg_cls)
                dec  a
                ld   a, 0                      ; ceiling: row 0
                jr   z, .o
                ld   a, 8                      ; floor: bottom row 7 -> top 8 - h
                ld   hl, dg_h
                sub  (hl)
.o:             add  a, e
                ld   (dg_row), a
                ; per-object constants (the rest is set once the object fits)
                ld   a, (dg_cls)
                xor  DC_BRICK
                sub  1
                sbc  a, a
                and  T_BRICK
                ld   (dg_req), a               ; T_BRICK for the brick class, else T_AIR
                ; budget cost: B = glyph cells, C = attr cells
                ld   a, (dg_fl)
                ld   e, a
                ld   bc, 0
                ld   a, (dg_w)
                ld   d, a
                bit  2, e
                jr   z, .g2
                ld   b, d
.g2:            bit  3, e
                jr   z, .g3
                ld   b, 1
.g3:            bit  4, e
                jr   z, .g4
                ld   c, d
.g4:            bit  5, e
                jr   z, .g5
                ld   a, (dg_area)
                ld   c, a
.g5:            ld   (dg_da), bc               ; dg_da = C, dg_dg = B
                ld   a, e
                rlca                           ; CF = large animated
                ld   a, (dg_nl)
                adc  a, 0
                cp   DG_MAX_LARGE + 1
                ret  nc
                ld   a, (dg_ng)
                add  a, b
                cp   DG_MAX_GLYPH + 1
                ret  nc
                ld   a, (dg_na)
                add  a, c
                cp   DG_MAX_ATTR + 1
                ret  nc
                ld   a, (dg_cls)
                cp   DC_PATCH
                jr   c, .fit
                ld   a, (dg_nw)
                ld   hl, dg_area
                add  a, (hl)
                cp   DG_MAX_WALL + 1
                ret  nc
                ; fit test: the footprint must be the base tile ...
.fit:           ld   a, (dg_row)
                ld   b, a
                ld   a, (dg_col)
                ld   c, a
                call map_cell
                ld   a, (dg_req)
                ld   c, a
                ld   a, (dg_h)
                ld   d, a
.ir:            push hl
                ld   a, (dg_w)
                ld   b, a
.ic:            ld   a, (hl)
                cp   c
                jp   nz, dg_rf
                inc  hl
                djnz .ic
                pop  hl
                call dg_nr
                dec  d
                jr   nz, .ir
                ; ... class support: a ceiling object hangs from T_PLAT / T_WALLF (or the
                ; screen top, map row 0; not moss), a floor object stands on them ...
                ld   a, (dg_cls)
                dec  a
                cp   2
                jr   nc, .sup_ok               ; classes 1 (ceiling) and 2 (floor) only
                ld   a, (dg_row)
                ld   b, a
                ld   a, (dg_cls)
                dec  a
                jr   nz, .fl
                ld   a, b
                or   a
                jr   nz, .c1
                ld   a, (dg_fl)
                and  F_MOSS
                ret  nz                        ; row 0: a chain may, moss may not
                jr   .sup_ok
.c1:            dec  b                         ; the row above
                ld   e, 1
                jr   .sup
.fl:            ld   a, (dg_h)
                add  a, b
                ld   b, a                      ; the row below the bottom row
                ld   a, (dg_w)
                ld   e, a
.sup:           ld   a, (dg_col)
                ld   c, a
.sl:            call map_cell
                ld   a, (hl)
                and  $FD                       ; T_WALLF (3) -> T_PLAT (1)
                cp   T_PLAT
                ret  nz
                inc  c
                dec  e
                jr   nz, .sl
.sup_ok:        ; ... and the ring holds no ladder and no other decor
                call dg_ring
                ret  nz
                ld   a, 1
                ld   (dg_ok), a
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
                jr   .nw
                ; place: row-major ids, ANIM entries per cell (dg_cell)
.pk:
                ld   a, (dg_fl)
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
.pl:            ld   a, (dg_row)
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
                ld   a, (dg_nl)
                adc  a, 0
                ld   (dg_nl), a
                ld   hl, dg_dg
                ld   a, (dg_ng)
                add  a, (hl)
                ld   (dg_ng), a
                dec  hl                        ; dg_da
                ld   a, (dg_na)
                add  a, (hl)
                ld   (dg_na), a
.nw:            ld   a, (dg_cls)
                cp   DC_PATCH
                ret  c                         ; only patch / brick / composite cells count
                ld   a, (dg_nw)
                ld   hl, dg_area
                add  a, (hl)
                ld   (dg_nw), a
                ret

; dg_ring — the 1-cell ring around the dg_row / dg_col / dg_h / dg_w box holds no ladder
; cell (ids 4..9) and no decor (12, 13, 15..18, >= 28) -> Z ok, NZ blocked. The ring is
; clipped to the map (only the low sides / col 31 can leave it; the last row row+h is
; <= 17), then walked by pointer (~60 T per cell). Clobbers A, BC, DE, HL.
dg_ring:
                ld   a, (dg_row)
                or   a
                jr   z, .rl
                dec  a
.rl:            ld   b, a                      ; B = first row
                ld   a, (dg_row)
                ld   hl, dg_h
                add  a, (hl)
                sub  b
                inc  a
                ld   d, a                      ; D = rows
                ld   a, (dg_col)
                or   a
                jr   z, .cl
                dec  a
.cl:            ld   c, a                      ; C = first col
                ld   a, (dg_col)
                ld   hl, dg_w
                add  a, (hl)
                cp   ROOM_COLS
                jr   c, .ch
                dec  a                         ; clip to col 31
.ch:            sub  c
                inc  a
                ld   (dg_cc), a                ; columns of the ring box
                call map_cell
.rr:            push hl
                ld   a, (dg_cc)
                ld   e, a
                ld   b, dg_bad >> 8
.rc:            ld   a, (hl)
                or   dg_bad & $FF              ; id < 64, table 64-aligned: the OR is the add
                ld   c, a
                ld   a, (bc)                   ; 1 = ladder / hole / decor id (table, ~55 T per cell)
                or   a
                jr   nz, .bad
                inc  hl
                dec  e
                jr   nz, .rc
                pop  hl
                call dg_nr
                dec  d
                jr   nz, .rr
                xor  a
                ret
.bad:           pop  hl
                or   1
                ret

; dg_patches — (1) >= 1 back-wall patch: up to DG_PTRIES attempts (4 rnd calls each) from
; the level's PATCH_A/B records (the first dg_pk of its records; none: the composite
; record), first legal wins; then rnd(2) == 0 gives a 2nd patch the same way.
dg_patches:
                ld   a, (LVL_DEPTH)
                dec  a
                ld   e, a
                ld   d, 0
                ld   hl, dg_pk
                add  hl, de
                ld   a, (hl)
                ld   (dg_k), a
                call .one
                ld   a, 2
                call dg_rnd
                or   a
                ret  nz
.one:           ld   b, DG_PTRIES
.t:             push bc
                xor  a
                ld   (dg_ok), a
                ld   a, (dg_k)
                or   a
                jr   nz, .k
                inc  a                         ; composite: rnd(1) keeps the call count
.k:             call dg_rnd
                ld   c, a
                ld   a, (dg_k)
                or   a
                ld   hl, dg_crec
                jr   z, .go
                ld   a, (dg_first)
                add  a, c
                call dg_rec
.go:            call dg_obj
                pop  bc
                ld   a, (dg_ok)
                or   a
                ret  nz
                djnz .t
                ret

; dg_cobwebs — (2) a level with a COBWEB: corner candidates scanned storey 0 then 1,
; cols 1..30; each takes one rnd(2) and is placed on 0; <= DG_MAX_COB per room.
dg_cobwebs:
                ld   a, (LVL_DEPTH)
                dec  a
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, dg_cob
                add  hl, de
                ld   a, (hl)
                or   a
                ret  z
                ld   (dg_cl), a
                inc  hl
                ld   a, (hl)
                ld   (dg_cr), a
                xor  a
                ld   (dg_nc), a
                ld   b, 0                      ; row 9s
.s:             ld   c, 1
                call map_cell                  ; HL = (row, 1): the row is walked by pointer
.c:             ld   a, (hl)
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
                ld   a, 2
                call dg_rnd
                or   a
                jr   nz, .x
                pop  bc
                pop  hl
                ld   a, (dg_cg)
                ld   (hl), a
                ld   a, (dg_nc)
                inc  a
                ld   (dg_nc), a
                cp   DG_MAX_COB
                ret  nc
                jr   .n
.x:             pop  bc
                pop  hl
.n:             inc  hl
                inc  c
                ld   a, c
                cp   ROOM_COLS - 1
                jr   c, .c
                ld   a, b
                or   a
                ret  nz
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
; dg_drips — B3B-13b (concept-screen 3.3 "Drip placement"; mirror of
; decorgen.drips): after the 12 decor attempts, DG_DRIP_N[depth-1] drips
; (D1/4/7 1, D2/3/5/6 2, D8 0), each skipped when the room already has 4
; glyph-swap cells. A drip = up to DG_DTRIES attempts of 3 rnd calls
; (col = rnd 32, storey = rnd 2, storey row = rnd 3), stopping at the first
; that fits: the cell is T_AIR, storey row 0..2 of a map row >= 1 (so never a
; floor row / the 2 above it), the cell above is T_PLAT / T_BRICK / T_WALLF
; (solid base ids 1..3), the cell below T_AIR, no ladder / hole / jamb / pit
; cap / door / lock / grate / rubble cell in cols col-1..col+1 of the whole
; storey (9 rows), and >= 6 cols from an earlier drip. Spawns are never in
; storey rows 0..2 (feet on the floor), so they need no test. The map keeps
; T_DRIP1, the entry's AL_TYPE is T_DRIP2, phase (col + row) & 7.
; decor_tick holds drip entries 16 ticks per frame (steps at AL_PHASE & 15 == 0).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
DG_DTRIES       EQU 8
DG_DMIN         EQU 6                ; min col distance between drips
dg_drips:
                ld   a, (LVL_DEPTH)
                dec  a
                ld   e, a
                ld   d, 0
                ld   hl, dg_dn
                add  hl, de
                ld   b, (hl)
                xor  a
                ld   (dg_np), a
                inc  b
                dec  b
                ret  z                         ; D8: none
.d:             push bc
                ld   a, (dg_ng)
                cp   DG_MAX_GLYPH
                jr   nc, .sk                   ; room already at 4 glyph-swap cells
                ld   b, DG_DTRIES
.t:             push bc
                call dg_dat
                pop  bc
                or   a
                jr   nz, .sk                   ; placed
                djnz .t
.sk:            pop  bc
                djnz .d
                ret

; dg_dat — one drip attempt (always 3 rnd calls) -> A = 1 placed, 0 not.
dg_dat:
                ld   a, 32
                call dg_rnd
                ld   (dg_dcol), a
                ld   a, 2
                call dg_rnd
                ld   e, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e                      ; 9 * storey
                ld   e, a
                ld   a, 3
                call dg_rnd
                add  a, e
                ld   (dg_drow), a
                jp   z, dg_dno                 ; row 0: nothing above it on the map
                ld   b, a
                ld   a, (dg_dcol)
                ld   c, a
                call map_cell
                ld   a, (hl)
                or   a
                jp   nz, dg_dno                ; cell must be T_AIR
                ld   de, ROOM_COLS
                or   a
                sbc  hl, de
                ld   a, (hl)
                dec  a
                cp   3
                jp   nc, dg_dno                ; above: T_PLAT / T_BRICK / T_WALLF
                add  hl, de
                add  hl, de
                ld   a, (hl)
                or   a
                jp   nz, dg_dno                ; below must be T_AIR
                ld   a, (dg_np)
                or   a
                jr   z, .far
                ld   b, a
                ld   hl, dg_dcs
.f:             ld   a, (dg_dcol)
                sub  (hl)
                jr   nc, .p
                neg
.p:             cp   DG_DMIN
                jp   c, dg_dno
                inc  hl
                djnz .f
.far:           ; structural scan: 9 rows of the storey x cols col-1..col+1 (clipped)
                ld   a, (dg_drow)
                ld   b, 0
                cp   STOREY_ROWS
                jr   c, .s0
                ld   b, STOREY_ROWS
.s0:            ld   a, (dg_dcol)
                or   a
                jr   z, .c0
                dec  a
.c0:            ld   c, a                      ; C = first col
                ld   a, (dg_dcol)
                inc  a
                cp   ROOM_COLS
                jr   c, .c1
                dec  a                         ; clip to col 31
.c1:            sub  c
                inc  a
                ld   e, a                      ; E = cols
                ld   d, STOREY_ROWS
                call map_cell
.sr:            push hl
                ld   b, e
.sc:            ld   a, (hl)
                sub  T_LAD_L
                cp   T_HOLE_R - T_LAD_L + 1
                jr   c, .bad                   ; ladder / hole 4..9
                cp   T_DOOR_JAMB_L - T_LAD_L
                jr   z, .bad
                cp   T_DOOR_JAMB_R - T_LAD_L
                jr   z, .bad
                sub  T_END_L - T_LAD_L         ; pit caps .. rubble 19..27
                cp   T_RUBBLE - T_END_L + 1
                jr   c, .bad
                inc  hl
                djnz .sc
                pop  hl
                call dg_nr
                dec  d
                jr   nz, .sr
                ; place
                ld   a, (dg_drow)
                ld   b, a
                ld   a, (dg_dcol)
                ld   c, a
                call map_cell
                ld   (hl), T_DRIP1
                ld   a, c
                add  a, b
                and  7
                ld   (dg_ph), a
                ld   a, (dg_ng)
                inc  a
                ld   (dg_ng), a
                ld   a, (dg_np)
                ld   e, a
                inc  a
                ld   (dg_np), a
                ld   d, 0
                ld   hl, dg_dcs
                add  hl, de
                ld   (hl), c
                ld   a, T_DRIP2
                call dg_cell.em
                ld   a, 1
                ret
.bad:           pop  hl
dg_dno:         xor  a
                ret

; drips per room by depth 1..8; scratch (dg_dcs = columns of the placed drips)
dg_dn:          DEFB 1, 2, 2, 1, 2, 2, 1, 0
dg_np:          DB   0
dg_dcol:        DB   0
dg_drow:        DB   0
dg_dcs:         DB   0, 0

; .rf-style exit of the fit loops (one row pointer pushed) and the row step.
dg_rf:          pop  hl
                ret
dg_nr:          ld   a, l                      ; HL += 32 (next map row, same col)
                add  a, ROOM_COLS
                ld   l, a
                ret  nc
                inc  h
                ret

; dg_cell — B = row, C = col, D = dy, E = dx of a just-placed cell: append its
; ANIM_LIST entry (col, row, type, phase) if the object animates it.
; Keeps BC, DE.
dg_cell:
                ld   a, (dg_fl)
                ld   l, a
                ld   a, d
                or   a
                jr   nz, .r1
                bit  2, l                      ; row 0: glyph swap (all cells / last col)
                jr   nz, .gl
                bit  3, l
                jr   z, .at
                ld   a, (dg_w)
                dec  a
                cp   e
                jr   nz, .at
.gl:            ld   hl, dg_alt
                ld   a, (hl)                   ; type = alternate tile id (>= 16)
                inc  (hl)
                jr   .em
.r1:            dec  a
                jr   nz, .at
                bit  4, l                      ; row 1: flame body, attr cycle 1
                jr   z, .at
                ld   a, 1
                jr   .em
.at:            bit  5, l                      ; every cell attr cycle (1 flame / 2 candle)
                ret  z
                ld   a, 1
                bit  6, l
                jr   z, .em
                inc  a
.em:            push de
                ld   d, a
                ld   a, (dg_dst)               ; ANIM_N or ANIM_N2 (build_room_map)
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

; dg_rnd — A = n -> A = (step & $FF) mod n; keeps BC, DE; clobbers HL.
dg_rnd:
                push bc
                ld   c, a
                ld   hl, (dg_rng)              ; xorshift 7,9,8 (= levelgen lg_step)
                ld   a, h
                rra
                ld   a, l
                rra
                xor  h
                ld   h, a
                ld   a, l
                rra
                ld   a, h
                rra
                xor  l
                ld   l, a
                xor  h
                ld   h, a
                ld   (dg_rng), hl
                ld   a, c
                cp   2
                ld   a, l
                jr   nz, .m
                and  1                         ; n = 2 (storey): no 127-step loop
                pop  bc
                ret
.m:             sub  c
                jr   nc, .m
                add  a, c
                pop  bc
                ret

; GENERATED by tools/decorgen.py --asm (edit the tool, re-run, paste)
; record (3 B): base id | w + h*4 + class*32 | flags (bit0 moss, 1 tiled, 2 glyph row 0, 3 glyph last
;                 col, 4 attr row 1, 5 attr all, 6 attr type 2, 7 large animated)
; class 0 mount, 1 ceiling, 2 floor, 3 patch, 4 brick, 5 composite patch
dg_start:       ; first per-level record of depth 1..8, then the end
                DEFB 7, 11, 19, 23, 27, 30, 37, 40, 44
dg_pk:          ; PATCH_A/B records at the head of each level's records (0 = composite)
                DEFB 0, 2, 1, 1, 1, 2, 1, 0
dg_cob:         ; COBWEB left / right corner id per depth (0 = none)
                DEFB  56,  58
                DEFB  55,  57
                DEFB  57,  58
                DEFB   0,   0
                DEFB   0,   0
                DEFB  52,  54
                DEFB   0,   0
                DEFB  57,  58
                ALIGN 64                   ; dg_ring's lookup: 1 = ladder / hole / decor id (never crosses a page)
dg_bad:
                DEFB 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1
                DEFB 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1
                DEFB 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1
                DEFB 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1
dg_crec:        ; the composite patch record (D1 / D8)
                DEFB 0, 170, 0
dg_recs:
                DEFB  31,  69, $60      ;  0 common CANDLES
                DEFB  13,  69, $00      ;  1 common SKULLS
                DEFB  12,  41, $02      ;  2 common CHAIN
                DEFB  15,   9, $20      ;  3 common TORCH_SMALL
                DEFB  28, 101, $00      ;  4 common WALL_DITHER
                DEFB  29, 101, $00      ;  5 common WALL_PATCH
                DEFB  30, 101, $00      ;  6 common WALL_FADE
                DEFB  32,  18, $94      ;  7 D1 TORCH_TALL
                DEFB  42,  19, $00      ;  8 D1 WINDOW_ARCH
                DEFB  54,   9, $00      ;  9 D1 BANNER
                DEFB  57,  37, $01      ; 10 D1 MOSS
                DEFB  32, 106, $00      ; 11 D2 PATCH_A
                DEFB  36, 107, $00      ; 12 D2 PATCH_B
                DEFB  42,  13, $94      ; 13 D2 TORCH_SLIM
                DEFB  46,  70, $88      ; 14 D2 CAULDRON
                DEFB  49,  73, $84      ; 15 D2 BRAZIER
                DEFB  52,  10, $02      ; 16 D2 WINDOW_BAR
                DEFB  53,   9, $00      ; 17 D2 BANNER
                DEFB  56,  37, $01      ; 18 D2 MOSS
                DEFB  52, 106, $00      ; 19 D3 PATCH_A
                DEFB  32,  82, $94      ; 20 D3 BRAZIER_BIG
                DEFB  42,  22, $00      ; 21 D3 BANNER_TALL
                DEFB  56,  10, $02      ; 22 D3 BOOKSHELF
                DEFB  55, 106, $00      ; 23 D4 PATCH_A
                DEFB  32,  18, $94      ; 24 D4 TORCH_TALL
                DEFB  42,  22, $00      ; 25 D4 BANNER_TALL
                DEFB  52,  70, $88      ; 26 D4 CAULDRON
                DEFB  54, 106, $00      ; 27 D5 PATCH_A
                DEFB  32,  82, $94      ; 28 D5 BRAZIER_BIG
                DEFB  42,  19, $00      ; 29 D5 WINDOW_ARCH
                DEFB  41, 106, $00      ; 30 D6 PATCH_A
                DEFB  45, 107, $00      ; 31 D6 PATCH_B
                DEFB  32,  13, $94      ; 32 D6 TORCH_SLIM
                DEFB  38,  10, $02      ; 33 D6 BOOKSHELF
                DEFB  39,   9, $00      ; 34 D6 BANNER
                DEFB  51,  10, $02      ; 35 D6 WINDOW_BAR
                DEFB  53,  37, $01      ; 36 D6 MOSS
                DEFB  52, 107, $00      ; 37 D7 PATCH_B
                DEFB  32,  18, $94      ; 38 D7 TORCH_TALL
                DEFB  42,  22, $00      ; 39 D7 BANNER_TALL
                DEFB  32,  82, $94      ; 40 D8 BRAZIER_BIG
                DEFB  42,  10, $02      ; 41 D8 BOOKSHELF
                DEFB  43,  22, $00      ; 42 D8 BANNER_TALL
                DEFB  53,  13, $94      ; 43 D8 TORCH_SLIM
DG_NCOM         EQU 7
DG_NREC         EQU 44

; state (bank 3 is RAM). dg_da before dg_dg (one `ld (dg_da), bc`).
dg_cmin:        DEFB 1, 1, 1, 2, 0, 2     ; col minimum by class (mount ceiling floor patch brick composite)
dg_rng:         DW   0
dg_cls:         DB   0
dg_cc:          DB   0
dg_ok:          DB   0
dg_k:           DB   0
dg_nc:          DB   0
dg_cl:          DB   0
dg_cr:          DB   0
dg_cg:          DB   0
dg_dst:         DB   0                 ; low byte of the list's count: ANIM_N / ANIM_N2
dg_first:       DB   0
dg_n:           DB   0
dg_nl:          DB   0
dg_ng:          DB   0
dg_na:          DB   0
dg_nw:          DB   0
dg_base:        DB   0
dg_row:         DB   0
dg_h:           DB   0
dg_col:         DB   0
dg_w:           DB   0
dg_fl:          DB   0
dg_area:        DB   0
dg_step:        DB   0
dg_req:         DB   0
dg_id:          DB   0
dg_alt:         DB   0
dg_ph:          DB   0
dg_da:          DB   0
dg_dg:          DB   0
                ASSERT T_AIR == 0 && T_BRICK == 2 && F_MOSS == 1 && F_TILED == 2 && T_CHAIN + 1 == T_SKULLS && T_TORCH_B == T_TORCH_T + 1 && T_TORCH_T == 15
                ASSERT T_HOLE_R == T_LAD_L + 5 && ANIM_MAX == 12 && AL_STRIDE == 4
                ASSERT (ANIM_N >> 8) == ((ANIM_LIST + ANIM_MAX * AL_STRIDE) >> 8) && PLAY_ROWS < 32
                ASSERT (ANIM_N2 >> 8) == ((ANIM_LIST2 + ANIM_MAX * AL_STRIDE) >> 8) && ANIM_LIST2 == ANIM_N2 + 1
                ASSERT dg_dg == dg_da + 1
                ASSERT T_END_L == 19 && T_RUBBLE == 27 && T_DOOR_JAMB_L == 11 && T_DOOR_JAMB_R == 14 && T_DRIP2 == T_DRIP1 + 1
                ASSERT T_PLAT == 1 && T_WALLF == 3 && STOREY_ROWS == 9
                ASSERT (dg_bad & 63) == 0 && TILE_IDS == 64 && DG_NREC * 3 < 256 && (dg_recs - dg_crec) == 3
