;==============================================================================
; decor.asm — B3B-10 animated decor (plan D6, concept-screen §3.3), bank 2.
;   ANIM_LIST (level_defs.asm; filled by the B3B-9 deriver for the room in
;   ROOM_MAP, or copied from ANIM_LIST2 by do_exit's room_shadow): per entry
;   AL_COL, AL_ROW, AL_TYPE (1..15 attr-cycle kind: 1 flame, 2 candle; >= 16
;   glyph swap: the OTHER tile id), AL_PHASE (tick counter, starts at the
;   object's stagger (col + row) & 7). The attr tables (dt_attr_tab) sit in
;   main.asm's kind_tab ALIGN pad.
;==============================================================================
DT_STEP_MASK    EQU 3               ; an entry steps when AL_PHASE & 3 == 0: every 4th tick
DT_GLYPH_HOLD   EQU 16              ; glyph swaps (drips) step every 16th tick (designer ~12)
DT_MAX_GLYPH    EQU 1               ; per tick: <= 1 glyph swap and <= 2 attr steps (D6
DT_MAX_ATTR     EQU 2               ; allows 2 + 3; measured ~1.2k / ~0.75k T per step, so
                                    ; 1 + 2 keeps a tick <= ~3.5k T). The deriver's maxima
                                    ; (4 glyph + 8 attr cells, all due once per 4 ticks)
                                    ; still fit 4 ticks; a same-stagger bunch spreads
DT_MAX_TRIES    EQU 3               ; per tick: <= 3 due entries reach the occupancy test
                                    ; (~0.1k per RLIST slot each); the rest wait a tick
DT_KINDS        EQU 2               ; attr-cycle kinds in dt_attr_tab (1 flame, 2 candle)
; dt_attr_tab colours (main.asm). A step writes the WHOLE attr byte, so the
; cell's paper becomes black: fine, every attr-cycled cell (candles 31, small
; torch 15/16, the large torches' / braziers' row-1 cells in all 8 tileset
; slots) already has paper 0 in its TILE_ATTRS / tileset attr (checked
; 2026-10-04: $46 or $06), and the deriver never puts decor on floor rows.
DT_HOT          EQU ATTR_TORCH      ; $46 bright yellow on black (the base attr)
DT_RED          EQU $42             ; bright red on black
DT_DIM          EQU $06             ; yellow on black (no BRIGHT)
                ASSERT DT_HOT == $46 && (DT_HOT & $38) == 0 && (DT_RED & $38) == 0 && (DT_DIM & $38) == 0
DT_CAPS         EQU (DT_MAX_TRIES << 6) | (DT_MAX_GLYPH << 4) | DT_MAX_ATTR   ; C: tries
                                    ; left (bits 7-6), glyph steps (5-4), attr steps (1-0)

;------------------------------------------------------------------------------
; decor_tick — play_loop, after this tick's render (+ pmark_dmg; with
; RENDER_FIRST also after read_turn_input / anim_tick, which leave R_COL..
; R_ROWS alone) and before panel_tick: SLOTREC's R_COL..R_ROWS are the
; footprints on the bank-5 screen. Every entry's AL_PHASE += 1; a
; due entry (AL_PHASE & 3 == 0; glyph swaps only when AL_PHASE & 15 == 0,
; i.e. drips hold 16 ticks per frame) steps: attr kinds take the next colour of
; their 8-step cycle (index = AL_PHASE bits 4..2), glyph swaps exchange the
; map id with AL_TYPE and draw the new glyph + its TILE_ATTRS attr. Each step
; writes the bank-5 cell AND the bank-7 clean-background shadow (else the next
; erase would restore a stale frame) and marks the cell for present.
; ROOM_MAP keeps the shown id, so the shadow / screens stay == the map
; (glyphs; attrs follow the cycle).
; A due entry WAITS a tick (AL_PHASE - 1, due again next tick) when the tick's
; cap for its kind (DT_MAX_GLYPH / DT_MAX_ATTR) or its occupancy tries
; (DT_MAX_TRIES) are spent: a same-stagger bunch spreads over ticks. A tried
; entry whose cell is under a drawn sprite (RLIST footprints, R_COL..R_ROWS)
; SKIPS this step: the cell holds (nothing written), the
; next try comes at its next due tick (a stationary sprite costs one test per
; entry per 4 ticks, not one per tick). Panel rows are never touched (the
; deriver's rows are 9s..9s+5).
; Skipped entirely: ANIM_N = 0 (PROTO rooms / rooms without animated decor)
; and ticks already in their 2nd frame (heavy render; the panel_tick test):
; the decor holds there, so it never adds to a tick that is already long.
; Leaves bank 7 paged if it stepped anything (every later user pages itself).
; Clobbers: A, BC, DE, HL.
; Cost (contended): ~0.1k + ~60 T per entry; per step ~0.75k (attr) / ~1.2k
; (glyph) incl. ~90 T per RLIST slot (occupancy; 1 slot) and the present mark
; (~0.2k); + ~0.1k to page bank 7 once. Measured per tick: tests/world.py W14
; (D1 room, its 8 real entries, hero only) max 3,534 / mean 2,458 T;
; tests/budget.py (synthetic full list, 12 entries, 5 sprites; incl. the call
; and the panel test) max 5,364 T, mean 2,487 T (mix) / 1,117 T (heavy).
;------------------------------------------------------------------------------
decor_tick:
                ld   a, (ANIM_N)
                or   a
                ret  z
                ld   b, a
                ld   a, (SYS_FRAMES)           ; 2nd frame already: hold everything
                ld   hl, LAST_TICK_FRAME
                cp   (hl)
                ret  nz
                ld   c, DT_CAPS
                ld   hl, ANIM_LIST + AL_PHASE
.e:             inc  (hl)
                ld   a, (hl)
                and  DT_STEP_MASK
                jr   z, .due
.nx:            ld   a, l
                add  a, AL_STRIDE
                ld   l, a
                djnz .e
                ret
.capd:          dec  (hl)                      ; cap spent: due again next tick
                jr   .nx
.due:           dec  l
                ld   a, (hl)                   ; AL_TYPE
                inc  l
                cp   AL_GLYPH_MIN
                ld   a, c
                jr   c, .ka
                ld   a, (hl)                   ; drips hold DT_GLYPH_HOLD ticks: step only
                and  DT_GLYPH_HOLD - 1         ; when AL_PHASE & 15 == 0 (the staggered
                jr   nz, .nx                   ; phase keeps them apart); no cap spent
                ld   a, c
                and  $30
                jr   z, .capd
                ld   a, -$10 - $40
                jr   .go
.ka:            and  $03
                jr   z, .capd
                ld   a, -1 - $40
.go:            bit  7, c
                jr   nz, .try
                bit  6, c
                jr   z, .capd                  ; no tries left this tick
.try:           add  a, c
                ld   c, a                      ; spend a try + the kind's cap (.skip
                push bc                        ; gives the cap back)
                push hl                        ; [count, caps][AL_PHASE]
                dec  l
                dec  l
                ld   b, (hl)                   ; B = row
                dec  l
                ld   c, (hl)                   ; C = col
                ; ---- occupancy: every RLIST footprint ----
                ld   a, (RLIST_N)
                or   a
                jr   z, .free
                ld   d, a
                ld   e, RLIST & $FF
.s:             ld   h, RLIST >> 8             ; (no R_VIS test: a slot hidden this
                ld   l, e                      ; tick keeps its last footprint, at
                ld   a, (hl)                   ; worst a 1-tick hold)
                rlca
                rlca
                rlca
                rlca                           ; slot * SLOTREC_STRIDE
                or   R_COL
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   a, c
                sub  (hl)
                jr   c, .ns                    ; left of it
                inc  l
                inc  l                         ; R_COLS
                cp   (hl)
                jr   nc, .ns                   ; right of it
                dec  l                         ; R_ROW
                ld   a, b
                sub  (hl)
                jr   c, .ns                    ; above
                inc  l
                inc  l                         ; R_ROWS
                cp   (hl)
                jr   c, .skip                  ; inside
.ns:            inc  e
                dec  d
                jr   nz, .s
.free:          call fx_occ                    ; D3-5: never paint over a drawn FX
                jr   c, .skip
                ld   a, (PORT_7FFD_SHADOW)     ; the shadow: bank 7 at $C000 (paged
                and  7                         ; once per tick: render paged a pool
                cp   BANK_SHADOW               ; bank since)
                jr   z, .p7
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
.p7:            ld   a, b                      ; row -> D = third, E = cell low byte
                rrca                           ; (the same low byte in the screen,
                rrca                           ; its attrs, the shadow and ROOM_MAP:
                rrca                           ; 32-B rows, page-aligned thirds)
                ld   d, a
                and  $E0
                or   c
                ld   e, a
                ld   a, d
                and  3
                ld   d, a
                pop  hl
                push hl
                ld   a, (hl)                   ; AL_PHASE
                dec  l
                ld   c, (hl)                   ; C = AL_TYPE
                rrca
                rrca
                and  7                         ; cycle index
                ld   l, a
                ld   a, c
                cp   AL_GLYPH_MIN
                jr   nc, .glyph
                dec  a                         ; attr kind 1..DT_KINDS
                add  a, a
                add  a, a
                add  a, a
                add  a, l
                add  a, dt_attr_tab & $FF
                ld   l, a
                ld   h, dt_attr_tab >> 8
                ld   c, (hl)                   ; C = the cycle's attr
                jr   .attr
.skip:          pop  hl                        ; under a sprite: this step is skipped
                pop  bc                        ; (the cell holds; next try 4 ticks on)
                dec  l
                ld   a, (hl)
                inc  l
                cp   AL_GLYPH_MIN              ; give the cap back
                ld   a, 1
                jr   c, .hb
                ld   a, $10
.hb:            add  a, c
                ld   c, a
                jp   .nx
.glyph:         ld   a, d                      ; swap the map id with AL_TYPE
                add  a, ROOM_MAP >> 8
                ld   h, a
                ld   l, e
                ld   a, (hl)
                ld   (hl), c
                pop  hl
                push hl
                dec  l
                ld   (hl), a                   ; AL_TYPE = the id swapped out
                ld   a, c                      ; HL = TILE_GLYPHS + new id * 8
                add  a, a
                add  a, a
                add  a, a                      ; CF = id bit 5 (ids < 64)
                ld   l, a
                ld   a, TILE_GLYPHS >> 9
                rla
                ld   h, a
                push bc                        ; B = row, C = new id
                push de                        ; D = third, E = low byte
                ld   a, d
                add  a, a
                add  a, a
                add  a, a
                or   SCREEN_BITMAP >> 8
                ld   d, a                      ; DE = bank-5 bitmap, line 0
                add  a, (SHADOW_BITMAP - SCREEN_BITMAP) >> 8
                ld   b, a
                ld   c, e                      ; BC = the shadow's
.ln:            DUP  4                         ; 33 T/line to both screens; the glyph
                ld   a, (hl)                   ; is 8-aligned: L & 7 = 0 after 8 lines
                ld   (de), a
                ld   (bc), a
                inc  l
                inc  d
                inc  b
                EDUP
                ld   a, l
                and  7
                jr   nz, .ln
                pop  de
                pop  bc
                ld   l, c
                ld   h, TILE_ATTRS >> 8
                ld   c, (hl)                   ; C = the new id's attr
.attr:          ld   a, d                      ; C -> the attr cell of bank 5 + shadow
                add  a, SCREEN_ATTR >> 8
                ld   h, a
                ld   l, e
                ld   (hl), c
                add  a, (SHADOW_ATTR - SCREEN_ATTR) >> 8
                ld   h, a
                ld   (hl), c
                ; mark the cell for present (pmark_rect's 1-cell case inline,
                ; ~150 vs ~250 T): PRES_MASK byte row*4 + col/8, bit 7 - col%8
                ld   a, e
                and  7
                add  a, pm_tab & $FF
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, (hl)
                inc  l
                xor  (hl)                      ; ($FF >> n) ^ ($FF >> n+1) = bit 7-n
                ld   c, a
                ld   a, e
                and  $18
                rrca
                rrca
                rrca                           ; col / 8
                ld   l, a
                ld   a, b
                add  a, a
                add  a, a
                add  a, l
                add  a, PRES_MASK & $FF
                ld   l, a
                ld   h, PRES_MASK >> 8
                ld   a, (hl)
                or   c
                ld   (hl), a
                ld   a, 1
                ld   (PRES_ANY), a
                ld   hl, PRES_RMIN
                ld   a, b
                cp   (hl)
                jr   nc, .done
                ld   (hl), a                   ; present starts at the first marked row
.done:          pop  hl
                pop  bc
                jp   .nx
                ASSERT (pm_tab >> 8) == ((pm_tab + 8) >> 8)
                ASSERT (TILE_GLYPHS & $1FF) == 0 && TILE_IDS <= 64
                ASSERT (ROOM_MAP & $FF) == 0 && (SCREEN_ATTR & $FF) == 0 && (SHADOW_ATTR & $FF) == 0
                ASSERT (SHADOW_BITMAP & $FF) == 0 && (SHADOW_BITMAP - SCREEN_BITMAP) == (SHADOW_ATTR - SCREEN_ATTR)
                ASSERT PLAY_ROWS * 4 <= PRES_LEN && (ANIM_LIST & 3) == 0
                ASSERT R_COL == 4 && R_ROW == 5 && R_COLS == 6 && R_ROWS == 7
                ASSERT SLOTREC_STRIDE == 16 && (SLOTREC & $FF) == 0
                ASSERT (RLIST >> 8) == ((RLIST + P_MAX_ENT - 1) >> 8)
                ASSERT DT_MAX_GLYPH <= 3 && DT_MAX_ATTR <= 3 && DT_MAX_TRIES <= 3 && DT_MAX_TRIES >= 1

