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
;   12 attempts x 4 rnd calls; an attempt places one object iff the budgets
;   (<= 2 large animated, 4 glyph + 8 attr cells, 6 wall-class cells) and the
;   fit test (footprint == T_AIR (air-class) / T_BRICK (wall-class), no ladder
;   cell in the 1-cell ring) allow; objects sit in rows 9s..9s+5 only.
; Clobbers: A, BC, DE, HL.  Cold path (room entry): measured 47-72k T
; (W13, DI, contended: build with decor - build with RD_SEED 0).
;==============================================================================
F_WALL          EQU 1               ; record flags (tools/decorgen.py)
F_TILED         EQU 2
DG_TRIES        EQU 12
DG_MAX_LARGE    EQU 2
DG_MAX_GLYPH    EQU 4
DG_MAX_ATTR     EQU 8
DG_MAX_WALL     EQU 6
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
                ld   b, DG_TRIES
.t:             push bc
                call dg_try
                pop  bc
                djnz .t
                ret

; dg_try — one attempt (the 4 rnd calls always happen, in this order).
dg_try:
                ld   a, (dg_n)
                call dg_rnd
                cp   DG_NCOM
                jr   c, .cm
                sub  DG_NCOM
                ld   hl, dg_first
                add  a, (hl)
.cm:            ld   c, a                      ; record index * 3
                add  a, a
                add  a, c
                ld   e, a
                ld   d, 0
                ld   hl, dg_recs
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   (dg_base), a
                ld   a, (hl)                   ; w | h << 2
                inc  hl
                ld   c, (hl)                   ; flags
                ld   b, a
                and  3
                ld   (dg_w), a
                ld   d, a
                ld   a, b
                rrca
                rrca
                and  7
                ld   (dg_h), a
                ld   b, a
                xor  a
.ar:            add  a, d                      ; area = w * h
                djnz .ar
                ld   (dg_area), a
                ld   a, c
                ld   (dg_fl), a
                and  F_WALL
                ld   c, a                      ; C = rmin (wall = 1)
                xor  1
                ld   b, a                      ; B = cmin (air = 1)
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
                ld   a, 7
                ld   hl, dg_h
                sub  (hl)
                sub  c
                call dg_rnd
                add  a, c
                add  a, e
                ld   (dg_row), a
                ; per-object constants
                ld   a, c
                add  a, a
                ld   (dg_req), a               ; T_BRICK (2) for wall-class, T_AIR (0)
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
                bit  0, e
                jr   z, .fit
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
                ; ... and the 1-cell ring around it holds no ladder cell. The ring is
                ; clipped to the map (only the low sides / col 31 can leave it; the
                ; last row row+h is <= 15), then walked by pointer (~50 T per cell).
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
                ld   e, a                      ; E = cols
                call map_cell
.rr:            push hl
                ld   b, e
.rc:            ld   a, (hl)
                sub  T_LAD_L
                cp   T_HOLE_R - T_LAD_L + 1
                jp   c, dg_rf
                inc  hl
                djnz .rc
                pop  hl
                call dg_nr
                dec  d
                jr   nz, .rr
                ; place: row-major ids, ANIM entries per cell (dg_cell)
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
                ld   a, (dg_fl)
                rrca
                ret  nc
                ld   a, (dg_nw)
                ld   hl, dg_area
                add  a, (hl)
                ld   (dg_nw), a
                ret

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
; record (3 B): base id | w + h*4 | flags (bit0 wall, 1 tiled, 2 glyph row 0, 3 glyph last col,
;                 4 attr row 1, 5 attr all, 6 attr type 2, 7 large animated)
dg_start:       ; first per-level record of depth 1..8, then the end
                DEFB 7, 13, 22, 28, 33, 37, 46, 50, 56
dg_recs:
                DEFB  31,   5, $60      ;  0 common CANDLES
                DEFB  13,   5, $00      ;  1 common SKULLS
                DEFB  12,   9, $02      ;  2 common CHAIN
                DEFB  15,   9, $20      ;  3 common TORCH_SMALL
                DEFB  28,   5, $01      ;  4 common WALL_DITHER
                DEFB  29,   5, $01      ;  5 common WALL_PATCH
                DEFB  30,   5, $01      ;  6 common WALL_FADE
                DEFB  32,  18, $94      ;  7 D1 TORCH_TALL
                DEFB  42,  19, $00      ;  8 D1 WINDOW_ARCH
                DEFB  54,   6, $01      ;  9 D1 PILLAR
                DEFB  56,   9, $00      ; 10 D1 BANNER
                DEFB  58,   5, $00      ; 11 D1 COBWEB
                DEFB  59,   5, $00      ; 12 D1 MOSS
                DEFB  32,  10, $01      ; 13 D2 PATCH_A
                DEFB  36,  11, $01      ; 14 D2 PATCH_B
                DEFB  42,  13, $94      ; 15 D2 TORCH_SLIM
                DEFB  46,   6, $88      ; 16 D2 CAULDRON
                DEFB  49,   9, $84      ; 17 D2 BRAZIER
                DEFB  52,  10, $02      ; 18 D2 WINDOW_BAR
                DEFB  53,   9, $00      ; 19 D2 BANNER
                DEFB  55,   5, $00      ; 20 D2 COBWEB
                DEFB  56,   5, $00      ; 21 D2 MOSS
                DEFB  32,  18, $94      ; 22 D3 BRAZIER_BIG
                DEFB  42,  22, $00      ; 23 D3 BANNER_TALL
                DEFB  52,  10, $01      ; 24 D3 PATCH_A
                DEFB  56,   6, $01      ; 25 D3 PILLAR
                DEFB  58,  10, $02      ; 26 D3 BOOKSHELF
                DEFB  59,   5, $00      ; 27 D3 COBWEB
                DEFB  32,  18, $94      ; 28 D4 TORCH_TALL
                DEFB  42,  22, $00      ; 29 D4 BANNER_TALL
                DEFB  52,  10, $02      ; 30 D4 WINDOW_BAR
                DEFB  53,   6, $88      ; 31 D4 CAULDRON
                DEFB  56,  10, $01      ; 32 D4 PATCH_A
                DEFB  32,  18, $94      ; 33 D5 BRAZIER_BIG
                DEFB  42,  19, $00      ; 34 D5 WINDOW_ARCH
                DEFB  54,   6, $01      ; 35 D5 PILLAR
                DEFB  56,  10, $01      ; 36 D5 PATCH_A
                DEFB  32,  13, $94      ; 37 D6 TORCH_SLIM
                DEFB  36,   6, $01      ; 38 D6 PILLAR
                DEFB  38,  10, $02      ; 39 D6 BOOKSHELF
                DEFB  39,   9, $00      ; 40 D6 BANNER
                DEFB  41,  10, $01      ; 41 D6 PATCH_A
                DEFB  45,  11, $01      ; 42 D6 PATCH_B
                DEFB  51,  10, $02      ; 43 D6 WINDOW_BAR
                DEFB  52,   5, $00      ; 44 D6 COBWEB
                DEFB  53,   5, $00      ; 45 D6 MOSS
                DEFB  32,  18, $94      ; 46 D7 TORCH_TALL
                DEFB  42,   6, $01      ; 47 D7 PILLAR
                DEFB  44,  22, $00      ; 48 D7 BANNER_TALL
                DEFB  54,  11, $01      ; 49 D7 PATCH_B
                DEFB  32,  18, $94      ; 50 D8 BRAZIER_BIG
                DEFB  42,   6, $01      ; 51 D8 PILLAR
                DEFB  44,  10, $02      ; 52 D8 BOOKSHELF
                DEFB  45,  22, $00      ; 53 D8 BANNER_TALL
                DEFB  55,  13, $94      ; 54 D8 TORCH_SLIM
                DEFB  59,   5, $00      ; 55 D8 COBWEB
DG_NCOM         EQU 7
DG_NREC         EQU 56

; state (bank 3 is RAM). dg_da before dg_dg (one `ld (dg_da), bc`).
dg_rng:         DW   0
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
                ASSERT T_AIR == 0 && T_BRICK == 2 && F_WALL == 1 && F_TILED == 2
                ASSERT T_HOLE_R == T_LAD_L + 5 && ANIM_MAX == 12 && AL_STRIDE == 4
                ASSERT (ANIM_N >> 8) == ((ANIM_LIST + ANIM_MAX * AL_STRIDE) >> 8) && PLAY_ROWS < 32
                ASSERT (ANIM_N2 >> 8) == ((ANIM_LIST2 + ANIM_MAX * AL_STRIDE) >> 8) && ANIM_LIST2 == ANIM_N2 + 1
                ASSERT dg_dg == dg_da + 1
                ASSERT (dg_recs - dg_start) == 9 && DG_NREC * 3 < 256
