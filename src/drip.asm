;==============================================================================
; drip.asm — D3-8b decorative drip, bank-2 (per-tick) part (game.md §6.4.1
; "Decorative drip", §6.3 drips-as-decor; plan D3-8b). Ambient only: no
; gameplay effect, never touches ROOM_MAP, the attr shadow or RNG_STATE.
;
; One drop at a time per room, from the room's sources (DRIP_SRC, derived on
; room entry by drip_room, src/drip7.asm, from the old B3B-13b drip placement
; rules): IDLE (wait DRIP_T ticks) -> FORM (old T_DRIP1 at the source,
; DRIP_FORM_T ticks) -> DROP (old T_DRIP2, DRIP_DROP_T ticks) -> FALL (the drop
; alone, one cell = 8 px down per tick while the cell below is T_AIR) -> erased
; on landing -> IDLE (a random gap). Attr DRIP_ATTR $05 (dim water; never a
; status / heal / poison colour).
;
; Layering ("bodies -> FX tracks (incl. the drip) -> marks -> numbers"): the
; drip is stepped after render (decor_gate, like decor_tick) and is only ever
; DRAWN into a T_AIR cell no body or FX footprint covers (cell_occ), so it is
; never drawn on top of a body. A body / FX that later moves onto the drawn
; drop is drawn over it (the drop's pixels may show through its mask for <= 1
; tick); the same tick's drip_tick sees the cover, forgets the drop and queues
; the cell (queue_damage): the next render restores it from the map and
; repairs whatever covers it — no drop pixels stay inside a body's cell.
; Does nothing on the TP_FIRE tick (review: not even the cover test, so the
; cast tick is untouched; a body covering the drop then is caught the tick
; after: <= 2 ticks of overlap there); holds (no step, only the cover test) in
; a tick already in its 2nd frame (as decor_tick: it never lengthens a heavy
; tick); frozen with the decor in ICON MODE (decor_gate).
;==============================================================================
DRIP_ATTR       EQU $05             ; cyan on black, no BRIGHT (designer: $01 or $05)
                ASSERT DRIP_ATTR == $01 || DRIP_ATTR == $05
DRIP_FORM_T     EQU 16              ; the hanging drop holds 16 ticks (the old glyph-swap hold)
DRIP_DROP_T     EQU 3               ; the let-go frame
DRIP_GAP        EQU 24              ; IDLE: 24 + (rnd & DRIP_GAP_RND) ticks between drops
DRIP_GAP_RND    EQU 63
DRIP_TRIES      EQU 8               ; drip_room: tries per source (the old DG_DTRIES)
DRIP_DMIN       EQU 6               ; min col distance between the 2 sources (DG_DMIN)

;------------------------------------------------------------------------------
; drip_tick — decor_gate, every unfrozen play tick, before decor_tick (after
; render: R_COL..R_ROWS and the FX drawn state are this tick's).
; Clobbers: A, BC, DE, HL (all but IY on the far7 paths). Leaves bank 7 paged
; if it erased (every later user pages itself).
; Cost: no source 45 T (incl. the call from decor_gate); drawn + waiting ~0.2k + ~90 T per RLIST slot; a fall
; step ~1.6k + the cover tests; a far7 step (spawn / let go) ~1.3k.
;------------------------------------------------------------------------------
drip_tick:
                ld   a, (DRIP_N)
                or   a
                ret  z                         ; no source in this room
                ld   a, (TURN_PEND)            ; nothing on the cast tick
                and  TP_FIRE
                ret  nz
                ld   a, (DRIP_DRAWN)
                or   a
                jr   z, .gate
                ld   bc, (DRIP_COL)            ; C = col, B = row
                call cell_occ
                jr   nc, .gate
                ld   hl, drip_cover            ; covered: forget it (bank 7)
                jp   far7
.gate:          ld   a, (SYS_FRAMES)           ; 2nd frame already: hold
                ld   hl, LAST_TICK_FRAME
                cp   (hl)
                ret  nz
                ld   hl, DRIP_T
                dec  (hl)
                ret  nz
                ld   a, (DRIP_ST)
                cp   DRS_DROP
                jr   nc, .fall
                ld   hl, drip_step             ; IDLE -> FORM, FORM -> DROP (bank 7)
                jp   far7
.fall:          ld   bc, (DRIP_COL)
                ld   a, b
                cp   PLAY_ROWS - 1
                jr   nc, .land                 ; on the last playfield row (an air
                inc  b                         ; cell in row 17, e.g. a pit): lands
                call cell_addr                 ; the cell below
                ld   a, (hl)
                or   a
                jr   nz, .land                 ; floor / item / ladder below
                call cell_occ
                jr   c, .land                  ; it falls onto a body / FX: gone
                push bc
                call drip_erase
                pop  bc
                ld   (DRIP_COL), bc
                ld   hl, DRIP_T
                inc  (hl)                      ; (0 -> 1: the next tick)
                ld   a, DRS_FALL
                ld   (DRIP_ST), a
                ld   hl, drip_g_fall
                jr   drip_draw
.land:          ld   hl, drip_land             ; erase + IDLE (bank 7)
                jp   far7

;------------------------------------------------------------------------------
; drip_erase — restore the drawn drop's cell from the map (erase_rect: glyph
; of the ROOM_MAP id + the attr shadow) and mark it for present; DRIP_DRAWN 0.
; Only called while no body / FX covers the cell. Out: bank 7 paged.
; Clobbers: A, BC, DE, HL.  ~0.9k T
;------------------------------------------------------------------------------
drip_erase:
                ld   bc, (DRIP_COL)
                ld   de, $0101
                push bc
                call erase_rect
                pop  bc
                xor  a
                jr   drip_mark                 ; RECLAIM-D: drip_draw's tail (-7 B, +12 T)

;------------------------------------------------------------------------------
; drip_draw — glyph HL (8 B, bank 2) at (DRIP_COL, DRIP_ROW) on the bank-5
; screen, attr DRIP_ATTR on the bank-5 attrs only (the shadow keeps the map's:
; erase_rect restores the cell), marked for present; DRIP_DRAWN = 1. A whole-
; byte write: the cell is T_AIR (blank glyph) whenever it is drawn.
; Pages nothing (bank-7 callers keep bank 7). Clobbers: A, BC, DE, HL.  ~0.7k T
;------------------------------------------------------------------------------
drip_draw:
                ld   bc, (DRIP_COL)
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   d, a                      ; D = the third's bitmap page, line 0
                ld   a, b
                rrca
                rrca
                rrca
                push af                        ; bits 1-0 = row >> 3 (the attr page)
                and  $E0
                or   c
                ld   e, a                      ; E = (row & 7) << 5 | col
.l:             ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                ld   a, d
                and  7
                jr   nz, .l                    ; 8 lines (D starts on a multiple of 8)
                pop  af
                and  3
                or   SCREEN_ATTR >> 8
                ld   d, a
                ld   a, DRIP_ATTR
                ld   (de), a
                ld   a, 1
drip_mark:      ld   (DRIP_DRAWN), a           ; (drip_erase's tail too: A = 0)
                ld   de, $0101
                jp   pmark_rect
                ASSERT (SCREEN_BITMAP & $7FF) == 0 && (SCREEN_ATTR & $3FF) == 0

; The B3B-13b drip art (git 95f6740 tiles_common ids 17 / 18, concept decor.tiles
; drip1 / drip2), 8 B each, MSB = left. drip_g_fall = drip2's drop alone; it
; shares its first 2 bytes with drip_g_form's last two ($00, $00).
drip_g_drop:    DB   $3C, $18, $00, $00, $10, $38, $38, $10    ; T_DRIP2: the tip, the drop let go
drip_g_form:    DB   $3C, $18, $18, $3C, $3C, $18              ; T_DRIP1: the drop hangs ...
drip_g_fall:    DB   $00, $00, $00, $00, $10, $38, $38, $10    ; ... ($00, $00 shared) / falling
