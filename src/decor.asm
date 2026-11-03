;==============================================================================
; decor.asm — B3B-10 animated decor (plan D6, concept-screen §3.3), bank 2.
;   ANIM_LIST (level_defs.asm; filled by the B3B-9 deriver for the room in
;   ROOM_MAP, or copied from ANIM_LIST2 by do_exit's room_shadow): per entry
;   AL_COL, AL_ROW, AL_TYPE (>= 16: glyph swap, the OTHER tile id), AL_PHASE
;   (tick counter, starts at the object's stagger (col + row) & 7).
;   LOOK-1 (user 2026-11-02): the flame attr cycle (kind 1, dt_attr_tab, the
;   $46 / $42 / $06 steps) is gone: the flame cells keep the fixed $42 of
;   their tile; only the glyph A/B swap animates.
;==============================================================================
DT_STEP_MASK    EQU 3               ; an entry steps when AL_PHASE & 3 == 0: every 4th tick
; FLAME-RATE (user 2026-11-02): flame glyph A/B swap every 4th tick (160 ms; was 16 = 640 ms). The
; hold equals the step period, so there is no separate hold test (-5 B). The D3-8b drip is its own
; system (drip.asm), not in ANIM_LIST since D3-7 T6: no entry needs the old 16-tick hold.
DT_MAX_GLYPH    EQU 2               ; per tick: <= 2 glyph swaps (~1.2k T per step; LOWER-FLAME exp.: was 1)
DT_MAX_TRIES    EQU 3               ; per tick: <= 3 due entries reach the occupancy test
                                    ; (~0.1k per RLIST slot each); the rest wait a tick
DT_CAPS         EQU (DT_MAX_TRIES << 6) | (DT_MAX_GLYPH << 4)   ; C: tries left (bits 7-6),
                                    ; glyph steps left (5-4)

;------------------------------------------------------------------------------
; decor_tick — play_loop, after this tick's render (+ pmark_dmg; with
; RENDER_FIRST also after read_turn_input / anim_tick, which leave R_COL..
; R_ROWS alone) and before panel_tick: SLOTREC's R_COL..R_ROWS are the
; footprints on the bank-5 screen. Every entry's AL_PHASE += 1; a
; due entry (AL_PHASE & 3 == 0: a flame frame lasts 4 ticks) steps: it exchanges the map id with
; AL_TYPE and draws the new glyph + its TILE_ATTRS attr. Each step
; writes the bank-5 cell (glyph / attr) AND the bank-7 attr shadow (else the
; next erase would restore a stale colour) and marks the cell for present.
; ROOM_MAP keeps the shown id (erase_rect redraws its glyph, D3-S2), so the
; screens stay == the map.
; A due entry WAITS a tick (AL_PHASE - 1, due again next tick) when the tick's
; glyph cap (DT_MAX_GLYPH) or its occupancy tries
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
; Cost (contended): ~0.1k + ~60 T per entry; per step ~1.2k incl. ~90 T per RLIST slot (occupancy; 1 slot) and the present mark
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
.due:           ld   a, c
                and  $30
                jr   z, .capd
                ld   a, -$10 - $40
                bit  7, c
                jr   nz, .try
                bit  6, c
                jr   z, .capd                  ; no tries left this tick
.try:           add  a, c
                ld   c, a                      ; spend a try + the glyph cap (.skip
                push bc                        ; gives the cap back)
                push hl                        ; [count, caps][AL_PHASE]
                dec  l
                dec  l
                ld   b, (hl)                   ; B = row
                dec  l
                ld   c, (hl)                   ; C = col
                call cell_occ                  ; a drawn sprite / FX there: skip
                jr   nc, .free                 ; (D3-8b: shared with the drip)
.skip:          pop  hl                        ; under a sprite: this step is skipped
                pop  bc                        ; (the cell holds; next try 4 ticks on)
                ld   a, $10                    ; give the glyph cap back
                add  a, c
                ld   c, a
                jp   .nx
.free:
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
                dec  l
                ld   c, (hl)                   ; C = AL_TYPE: the id to show now
                ld   a, d                      ; swap the map id with AL_TYPE
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
                push de                        ; D = third, E = low byte (B = row,
                ld   a, d                      ; C = new id: kept)
                add  a, a
                add  a, a
                add  a, a
                or   SCREEN_BITMAP >> 8
                ld   d, a                      ; DE = bank-5 bitmap, line 0
.ln:            DUP  4                         ; the glyph is 8-aligned: L & 7 = 0
                ld   a, (hl)                   ; after 8 lines. D3-S2: no bitmap
                ld   (de), a                   ; shadow (erase_rect redraws the
                inc  l                         ; map id swapped above)
                inc  d
                EDUP
                ld   a, l
                and  7
                jr   nz, .ln
                pop  de
                ld   l, c
                ld   h, TILE_ATTRS >> 8
                ld   c, (hl)                   ; C = the new id's attr
                ld   a, d                      ; C -> the attr cell of bank 5 + shadow
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

;------------------------------------------------------------------------------
; cell_occ — CF = 1 if cell (col C, row B) holds a drawn D3-8d status mark
; (MK_MAP; skipped while MK_N = 0, +31 T) or is inside a drawn body footprint
; (every RLIST slot's R_COL..R_ROWS: no R_VIS test, a slot hidden this tick
; keeps its last footprint — at worst a 1-tick hold) or a drawn FX (fx_occ).
; decor_tick (B3B-10, was inline), the D3-8b drip, mk_new.
; cell_bf — the same without the mark test (bodies + FX only).
; Clobbers: A, DE, HL (BC, IX kept).  ~60 T + ~90 T per RLIST slot + fx_occ
; (+ ~0.15k for the map test while a mark is drawn)
;------------------------------------------------------------------------------
cell_occ:
                ld   a, (MK_N)
                or   a
                jr   z, cell_bf
                call mk_bit
                and  (hl)
                jr   z, cell_bf
                scf
                ret
cell_bf:
                ld   a, (RLIST_N)
                or   a
                jr   z, .fx
                ld   d, a
                ld   e, RLIST & $FF
.s:             ld   h, RLIST >> 8
                ld   l, e
                ld   a, (hl)
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
                ret  c                         ; inside
.ns:            inc  e
                dec  d
                jr   nz, .s
.fx:            jp   fx_occ                    ; D3-5: never paint over a drawn FX

                ASSERT (pm_tab >> 8) == ((pm_tab + 8) >> 8)
                ASSERT (TILE_GLYPHS & $1FF) == 0 && TILE_IDS <= 64
                ASSERT (ROOM_MAP & $FF) == 0 && (SCREEN_ATTR & $FF) == 0 && (SHADOW_ATTR & $FF) == 0
                ASSERT PLAY_ROWS * 4 <= PRES_LEN && (ANIM_LIST & 3) == 0
                ASSERT R_COL == 4 && R_ROW == 5 && R_COLS == 6 && R_ROWS == 7
                ASSERT SLOTREC_STRIDE == 16 && (SLOTREC & $FF) == 0
                ASSERT (RLIST >> 8) == ((RLIST + P_MAX_ENT - 1) >> 8)
                ASSERT DT_MAX_GLYPH <= 3 && DT_MAX_TRIES <= 3 && DT_MAX_TRIES >= 1

