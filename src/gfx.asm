;==============================================================================
; gfx.asm — PROTO graphics layer (bank 2, hot).
;   paging + the bank-3 far-call trampoline, masked blit at any (px multiple
;   of 4, py) (§5.1), exact-footprint attr stamp (§4.2), tile-map
;   erase/restore (§4.3), HUD text, room draw. The boot-time generator and
;   the level tile load live in lowram.asm (bank 5); the transition scrolls,
;   init_tiles and build_room_map (B3B-8) in bank3.asm.
; Conventions: IX preserved unless stated; IY never touched (= $5C3A, kept for
; the optional ISR_ROM_CHAIN; the default A8 IM 2 ISR does not use it).
;==============================================================================

;==============================================================================
; page_bank — page RAM bank A (0..7) at $C000; 48K ROM; the displayed screen
; (bit 3) is KEPT (A7: set_screen patches it into the OR below, so paging costs
; nothing extra). Shadow before OUT (the A8 ISR re-OUTs the shadow after its
; AY call, so it is never stale; an interrupt between the two just makes the
; OUT below a repeat); bit 4 = 1, bit 5 never set. No DI needed.
; In : A = bank (0..7).   Clobbers: A, BC.   48 T
; SMC: .scr+1 = P7FFD_ROM48 | screen bit, patched only by set_screen.
;==============================================================================
page_bank:
.scr:           or   P7FFD_ROM48              ; SMC: | P7FFD_SCREEN7 while bank 7 is shown
                ld   (PORT_7FFD_SHADOW), a    ; port is write-only: keep the shadow
                ld   bc, PORT_7FFD
                out  (c), a
                ret

;==============================================================================
; farb — call the routine at HL with bank C paged in at $C000, then put the
; caller's $C000 bank back (saved PORT_7FFD_SHADOW value, bits 0-2). C3-0
; generalised far3 (bank in C) so the bank-1 UI code (ui1_code, far1) shares
; one trampoline; far3 / far1 / far6 (R6 region) / far7 (D3-S2: bank-7 cold
; code) are 2-byte bank loads in front of it.
; In : HL = target, A = passed to the target in A, C = bank (0..7; farb only).
;      BC is NOT passed (page_bank uses it); DE, IX pass in.
; Out: the target's BC, DE, HL, IX (passed through).  Clobbers: A, F.
; ~220 T + target (far3 / far1 / far6 / far7: +7 / +19 / +19 / +19 T). Nestable: the target may far-call
; again (each level restores its caller's bank). Paged-bank code must not page
; $C000 itself — see bank3.asm; it blits through blit_keep, and every helper
; it calls hands $C000 back as it found it (conventions.md "Banking").
;==============================================================================
far6:                                          ; R6: the bank-6 R6 region (r6.asm), +12 T vs far3
                ld   c, BANK_R6
                jr   farb
far7:                                          ; D3-S2: bank-7 cold code (bank7.asm)
                ld   c, BANK_COLD7
                jr   farb
far1:
                ld   c, BANK_UI1
                jr   farb
far3:
                ld   c, BANK_COLD3
                ; fall through
farb:
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page uses bits 0-2)
                ld   a, b
                push af                        ; target's A
                ld   a, c
                call page_bank
                pop  af
                call jp_hl
                pop  af
                ; fall through
;------------------------------------------------------------------------------
; restore_page — re-page $C000 from A = a saved PORT_7FFD_SHADOW value: only
; its bank bits 0-2 are taken (A7: the screen bit may have changed meanwhile —
; select / transitions switch it — and must not be rolled back). Through
; page_bank: shadow first, then the port. Clobbers: A, F (BC kept for far3's
; callers).   ~95 T
;------------------------------------------------------------------------------
restore_page:
                push bc
                and  7
                call page_bank
                pop  bc
                ret
jp_hl:          jp   (hl)

;------------------------------------------------------------------------------
; blit_keep — blit_sprite for code running from a paged bank (bank3.asm): the
; blit pages the pool in at $C000, so the caller's bank is re-paged before the
; return. Same In as blit_sprite.  Clobbers: A, F, BC, DE, HL.  blit + ~80 T
;------------------------------------------------------------------------------
blit_keep:
                ld   a, (PORT_7FFD_SHADOW)
                push af
                call blit_sprite
                pop  af
                jr   restore_page

;==============================================================================
; scr_addr_py — bitmap address of pixel row A (0..191), byte column C (0..31).
; Out: HL.  Clobbers: A.  Preserves BC, DE.   ~90 T
;   H = $40 | (py & $C0) >> 3 | (py & 7);  L = (py & $38) << 2 | col
;==============================================================================
scr_addr_py:
                ld   l, a
                and  7
                ld   h, a
                ld   a, l
                rra
                rra
                rra                           ; py>>3 (carry junk masked off)
                and  $18
                or   h
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, l
                rla
                rla                           ; py<<2
                and  $E0
                or   c
                ld   l, a
                ret

;==============================================================================
; attr_addr — attribute address of cell (row B, col C).
; Out: HL.  Clobbers: A.  Preserves BC, DE.   ~60 T
;==============================================================================
attr_addr:
                ld   a, b
                rrca
                rrca
                rrca
                ld   l, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   h, a
                ld   a, l
                and  $E0
                or   c
                ld   l, a
                ret

;==============================================================================
; stamp_rect — fill an attribute rectangle.
; In : A = attr, C = col (0..31), B = row, D = cols, E = rows (D,E >= 1).
; C + D > 32 is clamped to the row end and counted in CLIP_TRAP (debug trap).
; Clobbers: A, B, D, E, HL.   ~150 T + 26 T/cell + 55 T/row
; A7b: row step = add (32 - cols) to the row end (SMC) instead of push/pop +
; add hl,32 (79 -> 55 T/row); inc hl (not inc l): a row ending at col 31 of
; a third's last char row ends on a page boundary.
; SMC: .step+1 = 32 - cols, patched per call.
;==============================================================================
stamp_rect:
                push af
                ld   a, c
                add  a, d
                cp   ROOM_COLS + 1
                jr   c, .inx
                ld   a, ROOM_COLS
                sub  c
                ld   d, a
                ld   hl, CLIP_TRAP
                inc  (hl)
.inx:           call attr_addr
                ld   a, ATTR_STRIDE
                sub  d
                ld   (.step+1), a              ; SMC: 32 - cols
                pop  af
.row:           ld   b, d
.col:           ld   (hl), a
                inc  hl
                djnz .col
                ld   b, a                      ; (B free between rows: the attr)
                ld   a, l
.step:          add  a, 0                      ; SMC: 32 - cols -> next row start
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:            ld   a, b
                dec  e
                jr   nz, .row
                ret

;------------------------------------------------------------------------------
; shadow_rect — redraw rect C,B,D,E of the bank-7 ATTR shadow ($F800, screen-
; attr layout) from ROOM_MAP: TILE_ATTRS[id] (room entry, door planks, potion
; taken). D3-S2: there is no bitmap shadow (erase_rect redraws the glyphs from
; the map). Leaves bank 7 paged.
; Clobbers: A, BC, DE, HL.   ~0.2k + ~95 T/cell (cold)
;------------------------------------------------------------------------------
shadow_rect:
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
.row:           push bc
                push de
                call cell_addr                 ; HL = ROOM_MAP (B, C); keeps BC, DE
                ld   b, h                      ; B = the row's map page
.c:             ld   h, b
                ld   a, (hl)                   ; tile id
                ld   c, l
                ld   l, a
                ld   h, TILE_ATTRS >> 8
                ld   e, (hl)                   ; E = its attr
                ld   l, c                      ; same low byte in the attr shadow
                ld   a, b
                add  a, (SHADOW_ATTR - ROOM_MAP) >> 8
                ld   h, a
                ld   (hl), e
                inc  l
                dec  d
                jr   nz, .c
                pop  de
                pop  bc
                inc  b
                dec  e
                jr   nz, .row
                ret
                ASSERT (ROOM_MAP & $FF) == 0 && (SHADOW_ATTR & $FF) == 0

;==============================================================================
; erase_rect — restore a cell rect on the bank-5 screen (D3-S2, adopted from
; the D3-S spike): bitmap = TILE_GLYPHS[ROOM_MAP id] (the map is the truth:
; decor glyph swaps, door planks / jambs, potions, the B12 gate / glow, L2
; pits / blocks and the per-level ids 32..63 all live in it), attr = the
; bank-7 attr shadow ($F800: keeps the decor attr-cycle colours exactly), row
; 17 = the floor ornament (orn_cells, only when the rect reaches it);
; FLOOR1: a floor-item marker cell (id >= T_ITEM0) from the glyph cache
; instead (.item: icon quarter + slot ink, bank 2). ROOM_MAP,
; the screen bitmap / attrs and the attr shadow share the low byte
; ((row & 7) << 5 | col): per cell only high bytes change, L walks the row.
; In : C = col, B = row, D = cols, E = rows (rows 0..17).
; Out: bank 7 paged.  Clobbers: A, BC, DE, HL (IX kept)
; ~280 T + ~268 T/cell (+37 vs the old bitmap-shadow copy) + 74 T/row
; (+~110 T per third crossed; + orn_cells ~0.3k per row-17 ornament cell)
; FLOOR1 (review-measured): ids 0..31 cost 8 T less than before (D hoisted),
; ids 32..59 +46 T (the marker test + their own copy tail), a marker cell
; ~+96 T over a plain tile cell (the glyph cache).
; 3F-B1: id 0 (T_AIR) takes .air: ~64 T/cell less, every other id +7 T.
; SMC: .cols/.rows+1 per call; .mh/.bh/.ah/.dah+1 per call / third.
;==============================================================================
erase_rect:
                push bc
                ld   a, BANK_SHADOW            ; the attr shadow
                call page_bank
                pop  bc
                ld   a, b
                add  a, e
                cp   FLOOR_ROW1 + 1
                jr   c, .main                  ; rect above row 17 (nearly always)
                push bc
                push de
                call .main
                pop  de
                pop  bc
                ld   e, c                      ; logical col = screen col in play
                ld   b, FLOOR_ROW1
                ld   a, SCREEN_BITMAP >> 8
                jp   orn_cells                 ; over its PLAT / WALLF cells only
.main:          ld   a, d
                ld   (.cols+1), a
                ld   a, e
                ld   (.rows+1), a
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   (.bh+1), a
                ld   a, b
                rrca
                rrca
                rrca
                ld   e, a
                and  3
                ld   d, a
                add  a, ROOM_MAP >> 8
                ld   (.mh+1), a
                ld   a, d
                or   SCREEN_ATTR >> 8
                ld   (.ah+1), a
                add  a, (SHADOW_ATTR - SCREEN_ATTR) >> 8
                ld   (.dah+1), a
                ld   a, e
                and  $E0
                or   c
                ld   c, a                      ; C = low byte of the row's first cell
                ld   d, TILE_GLYPHS >> 8       ; FLOOR1: D stays the first glyph page (ids
.row:           ld   l, c                      ; 0..31); .dec / .item put it back
.cols:          ld   b, 0                      ; SMC: cols
.cell:
.mh:            ld   h, 0                      ; SMC: ROOM_MAP page of this third
                ld   a, (hl)                   ; tile id (< 64)
                add  a, a
                add  a, a
                add  a, a                      ; CF = id bit 5
                ld   e, a
                jr   c, .hi                    ; ids 32..63 (FLOOR1: the markers among them)
.g:                                            ; DE = TILE_GLYPHS + id*8 (ids 0..31: 8 T less
.bh:            ld   h, 0                      ; SMC: screen bitmap high (than before FLOOR1)
                jr   z, .air                   ; 3F-B1: Z still from the 3rd ADD A,A (LD / JR C keep
                                               ; flags): id 0 = T_AIR (id 32 left via .hi on CF)
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
.dah:           ld   h, 0                      ; SMC: attr shadow high
                ld   a, (hl)
.ah:            ld   h, 0                      ; SMC: screen attr high
                ld   (hl), a
.nx:            inc  l
                djnz .cell
.rows:          ld   a, 0                      ; SMC: rows left
                dec  a
                ret  z
                ld   (.rows+1), a
                ld   a, c
                add  a, 32                     ; next char row: same third ...
                ld   c, a
                jr   nc, .row
                jp   .third                    ; ... or the next one (rare; out of line so
                                               ; the JR C / JR Z below stay in range)
; .air — 3F-B1: T_AIR (id 0, glyph all zero: ASSERTed in boot6, tests/eraseair.py):
; 8 zero lines, no glyph read (the contended $66xx fetch). H = bitmap high
; already (.bh). ~64 T less than the copy per air cell; other ids pay 7 T (JR Z).
.air:           xor  a
                DUP  7
                ld   (hl), a
                inc  h
                EDUP
                ld   (hl), a
                jr   .dah
; .item — FLOOR1: A = a marker id T_ITEM0 + k (k = the item band row), L =
; the cell's low byte: its 8 lines from the glyph cache (FI_CELL, the storey's
; page, by L -> FI_GLY, bank 2) and the slot's ink (FI_INK) in place of the
; tile + shadow attr. Drawn once, in this pass.  ~0.29k T (a tile ~0.23k)
.dec:           inc  d                         ; ids 32..59: the second glyph page
                ld   a, (.bh+1)
                ld   h, a
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                dec  d                         ; (back to the first page)
                jr   .dah
.hi:            cp   (T_ITEM0 << 3) & $FF
                jr   c, .dec                   ; ids 60..63 fall through: a floor-item marker
.item:          ld   a, (hl)                   ; the id again (HL = its map cell)
                srl  a                         ; k 0 / 1 -> storey 0, 2 / 3 -> 1
                add  a, (FI_CELL >> 8) - (T_ITEM0 >> 1)
                ld   d, a
                ld   e, l
                ld   a, (de)                   ; the FI_GLY low byte (slot * 32 + 8 * quarter)
                ld   e, a
                ld   d, FI_INK >> 8
                ld   a, (.ah+1)
                ld   h, a                      ; the screen attr high
                ld   a, (de)
                ld   (hl), a                   ; the slot's ink first (FI_INK by that byte)
                ld   d, FI_GLY >> 8            ; DE = the quarter's line 0
                ld   a, (.bh+1)
                ld   h, a                      ; the screen bitmap high
                DUP  7                         ; (unrolled like the tile copy above;
                ld   a, (de)                   ; a quarter's 8 lines are contiguous)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                ld   d, TILE_GLYPHS >> 8
                jp   .nx
.third:         ld   hl, .bh+1
                ld   a, (hl)
                add  a, 8
                ld   (hl), a
                ld   hl, .mh+1
                inc  (hl)
                ld   hl, .ah+1
                inc  (hl)
                ld   hl, .dah+1
                inc  (hl)
                jp   .row
                ASSERT (FI_CELL & $FF) == 0 && (FI_GLY & $FF) == 0 && (FI_INK & $FF) == 0
                ASSERT T_ITEM0 + 4 == TILE_IDS && FI_SLOTS == 8 && (T_ITEM0 & 1) == 0 && (T_ITEM0 & 31) == 28 && (TILE_GLYPHS & $1FF) == 0
                ASSERT (TILE_GLYPHS & $1FF) == 0 && TILE_IDS <= 64 && (ROOM_MAP & $FF) == 0
                ASSERT (SCREEN_ATTR & $3FF) == 0 && (SHADOW_ATTR & $3FF) == 0 && FLOOR_ROW1 + 1 == PLAY_ROWS

;------------------------------------------------------------------------------
; fi_row — FLOOR1: an item cell's copy (erase_rect .item, lowram fi_cell),
; bank 2 (uncontended fetches): HL = the
; cell's bitmap line 0, DE = its quarter's first glyph byte (8 contiguous),
; BC = its attr, A = the ink: 8 lines + the attr. Out: E += 8, H += 8.
; Clobbers: A, H.   ~0.25k T
;------------------------------------------------------------------------------
fi_row:         push af
.ln:            DUP  4
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, h
                and  7
                jr   nz, .ln                   ; 8 lines (H starts on a multiple of 8)
                pop  af
                ld   (bc), a
                ret

;==============================================================================
; PRESENT — A7 double buffer, option A (docs/design/budget.md §3). During play
; the ULA shows bank 7's screen 2 ($C000); everything is still composed in
; bank 5 ($4000) as before, and present copies the cells changed since the
; last present from bank 5 to screen 2, so the beam never sees an erased
; sprite. Changed cells are marked in PRES_MASK (pmark_rect) by:
;   - render's damage list (pmark_dmg): erased old footprints, new / forced
;     footprints, attr-only stamps, PEND_DMG restores (potion);
;   - the panel (B3B-11, panel.asm): log rows via HUD4_PW (cols 0..PW-1 of
;     text rows 20..23), the other items by pmark_rect.
; Full-screen paths (start_game, room transitions) use present_full instead;
; select / transitions draw while bank 5 itself is shown (show_bank5).
; Invariant (tests): at the wait_tick probe screen 2 == the bank-5 screen.
;==============================================================================

;------------------------------------------------------------------------------
; pmark_rect — mark the cell rect C col, B row, D cols, E rows (D, E >= 1,
; B + E <= 24) for the next present; cols past 31 are clamped.
; Clobbers: A, HL (BC, DE kept).
; ~200 T + 46 T per row (1 mask byte) / 68 T per row (2); wider rects (HUD):
; ~85 T per mask byte + 49 T per row.
; SMC: .base+1 = low byte of the rect's first mask byte (patched per call).
;------------------------------------------------------------------------------
pmark_rect:
                push bc
                push de
                ld   a, 1
                ld   (PRES_ANY), a
                ld   hl, PRES_RMIN
                ld   a, b
                cp   (hl)
                jr   nc, .rm
                ld   (hl), a                   ; first marked row: present starts there
.rm:            ld   a, c
                add  a, d
                dec  a                         ; last col
                cp   ROOM_COLS
                jr   c, .lc
                ld   a, ROOM_COLS - 1
.lc:            ld   d, a                      ; D = last col
                ld   a, b
                add  a, a
                add  a, a
                ld   b, a                      ; B = row * 4
                ; fast paths (one row pass): the run fits 1 or 2 mask bytes
                ld   a, c
                rrca
                rrca
                rrca
                and  3
                add  a, b
                add  a, PRES_MASK & $FF
                ld   (.base+1), a              ; SMC: first mask byte of the rect
                ld   a, d
                and  7
                add  a, (pm_tab & $FF) + 1
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, d
                xor  c
                and  $18                       ; same mask byte?
                jr   nz, .two
                ld   a, (hl)                   ; $FF >> (last+1 & 7..8)
                ld   d, a
                call .lo                       ; A = $FF >> (C & 7)
                xor  d
                ld   d, a                      ; D = mask
                call .base
.r1:            ld   a, (hl)
                or   d
                ld   (hl), a
                ld   a, l
                add  a, 4
                ld   l, a
                djnz .r1
                jr   .done
.two:           ld   a, c
                or   7
                add  a, 8                      ; last col of the next mask byte
                cp   d
                jr   c, .seg                   ; >= 3 bytes (HUD rows): general loop
                ld   a, (hl)
                cpl
                ld   d, a                      ; D = mask of the 2nd byte
                call .lo
                ld   c, a                      ; C = mask of the 1st byte
                call .base
.r2:            ld   a, (hl)
                or   c
                ld   (hl), a
                inc  l
                ld   a, (hl)
                or   d
                ld   (hl), a
                ld   a, l
                add  a, 3
                ld   l, a
                djnz .r2
.done:          pop  de
                pop  bc
                ret
.lo:            ld   a, c                      ; A = $FF >> (C & 7)
                and  7
                add  a, pm_tab & $FF
                ld   l, a
                ld   a, (hl)                   ; (H = pm_tab page)
                ret
.base:          ld   l, 0                      ; SMC: HL = first mask byte, B = rows
                ld   h, PRES_MASK >> 8
                ld   b, e
                ret
.seg:           ld   a, c                      ; C = first col inside this mask byte
                and  7
                add  a, pm_tab & $FF
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, c
                or   7                         ; last col of this mask byte
                cp   d
                ld   a, (hl)                   ; $FF >> (C & 7)   (ld keeps CF)
                jr   c, .rows                  ; the run goes on into the next byte
                push af
                ld   a, d
                and  7
                add  a, (pm_tab & $FF) + 1
                ld   l, a
                pop  af
                xor  (hl)                      ; cut after the last col
.rows:          push de
                ld   d, a                      ; D = this byte's mask
                ld   a, c
                rrca
                rrca
                rrca
                and  3                         ; mask byte index C / 8
                add  a, b
                add  a, PRES_MASK & $FF
                ld   l, a
                ld   h, PRES_MASK >> 8
.row:           ld   a, (hl)
                or   d
                ld   (hl), a
                ld   a, l
                add  a, 4
                ld   l, a
                dec  e
                jr   nz, .row
                pop  de
                ld   a, c
                or   7
                cp   d                         ; this byte's last col < D: next byte
                inc  a                         ; (inc keeps CF)
                ld   c, a
                jr   c, .seg
                pop  de
                pop  bc
                ret

pm_tab:         DB   $FF, $7F, $3F, $1F, $0F, $07, $03, $01, $00   ; $FF >> n, n = 0..8
                ASSERT (pm_tab >> 8) == ((pm_tab + 8) >> 8)
                ASSERT (PRES_MASK & 3) == 0 && (PRES_MASK & $FF) + PRES_LEN == 256

;------------------------------------------------------------------------------
; pmark_dmg — mark the first DMG_PRES_N rects of render's damage list
; (c0,c1,r0,r1: PEND_DMG restores, erased old footprints, new footprints of
; changed sprites — A7b: a move's old + new footprint as ONE rect when their
; union is a rectangle) for the present at the next tick start. The overlap-repair rects appended after them
; are skipped: re-blitting an undamaged sprite in the same slot order rewrites
; the cells outside the damaged ones with the bytes already there (masked blit
; is idempotent, attr stamps repeat in the same order), so only cells inside
; the first rects can differ. (A DMG_LIST overflow in phases 1-2 makes the
; last of them the whole playfield, which is then marked.) play_loop calls
; this right after render.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
pmark_dmg:
                ld   a, (DMG_PRES_N)
                or   a
                ret  z
                ld   b, a
                ld   hl, DMG_LIST
.l:             push bc
                ld   c, (hl)                   ; c0
                inc  hl
                ld   a, (hl)
                sub  c
                ld   d, a                      ; cols = c1 - c0
                inc  hl
                ld   b, (hl)                   ; r0
                inc  hl
                ld   a, (hl)
                sub  b
                ld   e, a                      ; rows = r1 - r0
                inc  hl
                push hl
                call pmark_rect
                pop  hl
                pop  bc
                djnz .l
                ret

;------------------------------------------------------------------------------
; present — copy every marked cell (8 bitmap bytes + attr) from the bank-5
; screen to screen 2 (bank 7), rows top to bottom; clears the mask. Called
; first thing after the tick's HALT (play_loop): it starts ~13k T before the
; beam reaches line 0 and copies a char row faster than the beam scans one, so
; it stays ahead of the beam (a cell would only tear if the beam scanned it
; mid-copy). Leaves bank 7 paged at $C000.
; Clobbers: A, BC, DE, HL.
; Cost (uncontended; contended: 2 accesses per copied byte, budget §4): ~50 T
; if nothing is marked; else ~110 T entry (+~220 T if a HUD4_PW row is set),
; ~63 T per clean row, ~60 T per dirty row (+~190 T when its screen third
; differs from the last dirty row's), ~50 T per zero mask byte, ~130 T per
; non-zero one, 24 T per clear bit before a byte's last set bit, 242 T per
; copied cell (-5 T for the first of a run of set bits; the last copied cell of a
; mask byte pays a 26 T tail, was 15 T, which offsets that -5 T); a full mask byte (8
; cells side by side) ~1.5k T by LDI lines (.full8, A7b).
; 3F-B2 (measured on the B0 worst ticks; LDI-run variants priced and dropped:
; at the 3-5-cell runs of sprite footprints the per-line chain overhead eats
; the 6 T/byte LDI gain): the bit loop exits a run straight on the shift's
; flags (24 T per clear bit, was 31; 24 T between set bits, was 44), the cell
; low byte is the mask address * 8 (no per-row base), the screen highs are
; re-patched only when the screen third changes, and an all-zero HUD4_PW is
; skipped in one OR pass.
; SMC: .sbh/.dbh/.sah/.dah+1 (src/dst bitmap/attr high of the current third;
; .full8 reads them too) and .thd+1 (that third * 32; $FF = none yet).
;------------------------------------------------------------------------------
present:
                ld   a, (PRES_ANY)
                or   a
                ret  z
                ld   hl, HUD4_PW               ; B3B-11 text rows 20..23: mark cols 0..PW-1
                ld   a, (hl)
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                jr   z, .nohud                 ; (the usual case: 40 T, the loop is ~220 T)
                ld   l, HUD4_PW & $FF
                ld   b, TEXT_ROW
.hud:           ld   a, (hl)
                or   a
                jr   z, .hn
                ld   (hl), 0
                push hl
                ld   c, 0
                ld   d, a
                ld   e, 1
                call pmark_rect
                pop  hl
.hn:            inc  l
                inc  b
                ld   a, b
                cp   TEXT_ROW + TEXT_ROWS
                jr   c, .hud
.nohud:         xor  a
                ld   (PRES_ANY), a             ; (after the marks: they set it)
                ld   a, BANK_SCREEN7
                call page_bank
                ld   a, (PRES_RMIN)            ; skip the rows above the first mark
                cp   PRES_LEN / 4
                jr   c, .rmin
                xor  a                         ; (unset / garbage: scan all)
.rmin:          add  a, a
                add  a, a
                add  a, PRES_MASK & $FF
                ld   l, a
                ld   h, PRES_MASK >> 8
                ld   a, $FF
                ld   (PRES_RMIN), a
                ld   (.thd+1), a               ; no third patched yet
.rowt:          ld   a, (hl)                   ; any bit in this row's 4 bytes?
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                jr   nz, .dirty
                inc  l
                jr   nz, .rowt                 ; PRES_MASK ends at a page end
                ret
.dirty:         dec  l
                dec  l
                dec  l                         ; L = the row's mask byte 0
                ld   a, l
                sub  PRES_MASK & $FF
                ld   c, a                      ; C = row * 4
                rrca
                rrca                           ; A = row 0..23
.probe_row:                                    ; flicker probe (no code): A = row
                ld   a, c
                and  $E0                       ; third * 32 (row * 4 = third * 32 + (row & 7) * 4)
.thd:           cp   $FF                       ; SMC: the third the highs below are patched for
                jr   z, .byte
                ld   (.thd+1), a
                rlca
                rlca
                rlca                           ; A = third 0..2
                ld   c, a
                or   SCREEN_ATTR >> 8
                ld   (.sah+1), a
                add  a, (SCREEN7_ATTR - SCREEN_ATTR) >> 8
                ld   (.dah+1), a
                ld   a, c
                add  a, a
                add  a, a
                add  a, a                      ; third * 8
                or   SCREEN_BITMAP >> 8
                ld   (.sbh+1), a
                add  a, (SCREEN7_BITMAP - SCREEN_BITMAP) >> 8
                ld   (.dbh+1), a
.byte:          ld   a, (hl)
                or   a
                jr   z, .nextb
                ld   (hl), 0
                push hl
                ld   c, a                      ; C = bits left, bit 7 = this col
                ld   a, l
                add  a, a
                add  a, a
                add  a, a                      ; (L - PRES_MASK lo) * 8 mod 256 = (row & 7) << 5 | byte * 8
                ld   b, a                      ; B = low byte of the byte's col-0 cell
                inc  c
                jr   z, .full                  ; C was $FF
                dec  c
.bits:          dec  b                         ; (.bit pre-increments)
.bit:           inc  b
                sla  c
                jr   nc, .bit                  ; clear col (a set one follows): 24 T
.copy:          ld   l, b
                ld   e, b
.sbh:           ld   h, 0                      ; SMC: bank-5 bitmap high
.dbh:           ld   d, 0                      ; SMC: screen-2 bitmap high
                DUP  7
                ld   a, (hl)
                ld   (de), a
                inc  h
                inc  d
                EDUP
                ld   a, (hl)
                ld   (de), a
.sah:           ld   h, 0                      ; SMC: bank-5 attr high
.dah:           ld   d, 0                      ; SMC: screen-2 attr high
                ld   a, (hl)
                ld   (de), a
                inc  b
                sla  c
                jr   c, .copy                  ; the next col is set too: 24 T
                jr   nz, .bit                  ; clear, set bits remain (Z: C == 0, byte done)
                pop  hl
.nextb:         inc  l
                ld   a, l
                and  3
                jr   nz, .byte
.probe_row_end:                                ; flicker probe (no code)
                or   l                         ; A = 0 here: L = 0 <=> past row 23
                jp   nz, .rowt
                ret
.full:          dec  c                         ; C = $FF again
                ld   a, b
                cp   $F8                       ; (cols 24-31 of a third's last char
                jr   z, .bits                  ; row: LDI would carry into H)
                ; A7b: a full mask byte = 8 cells side by side (HUD text runs),
                ; copied line by line with LDI (16 T/byte, no per-cell setup):
                ; ~1.5k T vs ~1.9k per byte. Low byte <= $F0 here, so the 8
                ; LDIs of a line never carry into H / D.
.full8:         ld   a, (.sbh+1)
                ld   h, a
                ld   a, (.dbh+1)
                ld   d, a
                ld   a, b                      ; A = the first cell's low byte
                ld   bc, $08FF                 ; B = lines; C: 64 LDIs never borrow from B
.l8:            ld   l, a
                ld   e, a
                DUP  8
                ldi
                EDUP
                inc  h
                inc  d
                djnz .l8
                ld   l, a
                ld   e, a
                ld   a, (.sah+1)
                ld   h, a
                ld   a, (.dah+1)
                ld   d, a
                ld   bc, 8
                ldir                           ; the 8 attrs
                pop  hl
                jr   .nextb
                ASSERT (PRES_MASK & $1F) == 0  ; cell low byte = mask low byte * 8
                ASSERT TEXT_ROWS == 4 && (HUD4_PW >> 8) == ((HUD4_PW + 3) >> 8)
                ASSERT (((SCREEN_ATTR >> 8) & 3) == 0) && (((SCREEN_BITMAP >> 8) & $18) == 0)
                ASSERT SCREEN7_ATTR - SCREEN7_BITMAP == SCREEN_ATTR - SCREEN_BITMAP

;==============================================================================
; draw_room — full redraw of rows 0..17 (PLAY_ROWS) from ROOM_MAP.  ~167k T (boot/room only)
;==============================================================================
draw_room:
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   bc, 0                     ; row 0, col 0
                ld   de, (ROOM_COLS << 8) | PLAY_ROWS
                call tile_rect
                ; fall through: rebuild the attr shadow too
; shadow_room — whole-room attr-shadow rebuild (~60k T; room entry only).
shadow_room:
                ld   bc, 0
                ld   de, (ROOM_COLS << 8) | PLAY_ROWS
                jp   shadow_rect

;==============================================================================
; MASKED BLIT (prototype §5.1): frame BL_FID, facing BL_LEFT, top-left
; (BL_FPX, BL_FPY). Variant = FRT[fid][left*2 + (fpx AND 4 ? 1 : 0)].
; screen = (screen AND mask) OR data, width = cols (+1 spill if shifted).
; Clobbers: A, BC, DE, HL.  (IX/IY untouched)
;------------------------------------------------------------------------------
; A7b: DE = screen, HL = pool data (was the reverse): `and (hl)` / `or (hl)`
; read mask and data straight from the pool, so no temp register is needed
; (44 T/byte, was 52), and C keeps the line-start low byte, so a line ends
; with `ld e,c` (was ld a,l / sub w / ld l,a).
; Cost: 44 T/byte (unrolled chain, entered at (6-width)*7 by an SMC jump) +
; 31 T/line char-aligned (54 T general path) + ~680 T setup.
;   24x48 shifted  (4 cols)  : 192 B -> 8.4k + 1.5k + 0.7k = 10.6k T
;   40x48 slash    (6 cols)  : 288 B -> 12.7k + 1.5k + 0.7k = 14.9k T
; SMC: blit_jp+1 / blit_al_jp+1 (chain entry) — patched per sprite.
;==============================================================================
BLIT_BLOCK      EQU 7                   ; bytes per unrolled chain block
BLIT_MAXW       EQU 6

blit_sprite:
                ld   a, (BL_FPX)               ; variant*3 = (left ? 6 : 0) + (shifted ? 3 : 0)
                and  4
                jr   z, .s0
                ld   a, 3
.s0:            ld   e, a
                ld   a, (BL_LEFT)
                or   a
                jr   z, .r
                ld   a, 6
.r:             add  a, e
                ld   e, a
                ASSERT (FRT & $FF) == 0        ; nibble-swap lookup: FRT page-aligned
                ASSERT FRT_STRIDE == 16        ; ... and 16 B per fid
                ld   a, (BL_FID)               ; HL = FRT + fid*16 + variant*3
                rrca                           ; (fid*16 by nibble swap: 70 T, was
                rrca                           ; 4 x add hl,hl + 2 adds: 107 T)
                rrca
                rrca
                ld   l, a
                and  $0F
                add  a, FRT >> 8
                ld   h, a
                ld   a, l
                and  $F0
                add  a, e
                ld   l, a
                ld   a, (hl)                   ; bank
                cp   FRT_NONE
                jp   z, blit_miss
                inc  l                         ; (16-B rows: no carry)
                ld   e, (hl)
                inc  l
                ld   d, (hl)                   ; DE = pre-shifted frame
                push de
                call page_bank                 ; (A, BC; keeps HL)
                ld   a, l                      ; MEM-FT: frame_tab is the same FRT row's
                and  $F0                       ; tail: HL = row + FT_IN_ROW (22 T; was
                or   FT_IN_ROW + FT_COLS       ; fid*4 + frame_tab, 67 T)
                ld   l, a
                ld   c, (hl)                   ; C = data cols
                inc  hl
                ld   b, (hl)                   ; B = rows (H)
                ld   a, (BL_FPX)
                and  4
                jr   z, .ns
                inc  c                         ; spill column
.ns:            ld   a, (BL_FPX)
                rrca
                rrca
                rrca
                and  $1F
                ld   e, a                      ; E = byte col
                add  a, c                      ; debug trap: col + width > 32
                cp   ROOM_COLS + 1             ; would wrap into the next row
                jp   nc, blit_clip_pop         ; (unreachable today)
                ld   a, c
                add  a, a
                add  a, a
                add  a, a
                sub  c
                ld   d, a                      ; D = 7 * width
                ld   c, e                      ; C = byte col
                ld   a, (BL_FPY)
                ld   e, a
                and  7
                jr   nz, .gen                  ; flyer between cells: general path
                ld   a, b
                and  7
                jr   nz, .gen                  ; (all frames are 8n rows; belt+braces)
                ; char-aligned: the row fix-up only runs every 8 lines
                ld   a, b
                rrca
                rrca
                rrca
                ld   (BLIT_CROWS), a           ; char rows
                ld   a, blit_chain_al_end & $FF
                sub  d
                ld   l, a
                ld   a, blit_chain_al_end >> 8
                sbc  a, 0
                ld   h, a
                ld   (blit_al_jp+1), hl        ; SMC: entry = chain end - 7 * width
                ld   b, 8
                ld   a, e
                call scr_addr_py               ; HL = screen (BC, DE kept)
                ex   de, hl                    ; DE = screen
                pop  hl                        ; HL = pool data
                ld   c, e                      ; C = line-start low byte
                jp   blit_al_jp
.gen:           ld   a, blit_chain_end & $FF
                sub  d
                ld   l, a
                ld   a, blit_chain_end >> 8
                sbc  a, 0
                ld   h, a
                ld   (blit_jp+1), hl           ; SMC: entry = chain end - 7 * width
                ld   a, e
                call scr_addr_py
                ex   de, hl
                pop  hl
                ld   c, e
blit_rowloop:
blit_jp:        jp   blit_chain                ; SMC: entry for this width
blit_chain:
                DUP  BLIT_MAXW
                ld   a, (de)                   ; screen
                and  (hl)                      ; mask
                inc  hl
                or   (hl)                      ; data
                inc  hl
                ld   (de), a
                inc  e
                EDUP
blit_chain_end:
                ld   e, c                      ; back to the line start
                inc  d                         ; next pixel line
                ld   a, d
                and  7
                jr   nz, .nx
                ld   a, c                      ; crossed a char row
                add  a, 32
                ld   c, a
                ld   e, a
                jr   c, .nx                    ; crossed a third: D already right
                ld   a, d
                sub  8
                ld   d, a
.nx:            djnz blit_rowloop
                ret
blit_clip_pop:  pop  de                        ; (the pushed frame pointer)
blit_clip:
                ld   hl, CLIP_TRAP             ; not drawn
                inc  (hl)
                ret
blit_miss:
                ld   hl, BLIT_MISS             ; stationary frame at a missing shift
                inc  (hl)                      ; (§5.1 debug trap) -> not drawn
                ret
                ASSERT (blit_chain_end - blit_chain) == BLIT_BLOCK * BLIT_MAXW

; char-aligned continuation (31 T/line vs 54): B = lines left in this char
; row; the char-row / third fix-up runs once per 8 lines.
; SMC: blit_al_jp+1 (chain entry) per sprite.
blit_chain_al:                                 ; twin chain: falls into the
                DUP  BLIT_MAXW                 ; aligned continuation below
                ld   a, (de)
                and  (hl)
                inc  hl
                or   (hl)
                inc  hl
                ld   (de), a
                inc  e
                EDUP
blit_chain_al_end:
                ld   e, c
                inc  d
                djnz blit_al_jp
                ld   a, c                      ; next char row
                add  a, 32
                ld   c, a
                ld   e, a
                jr   c, .third
                ld   a, d
                sub  8
                ld   d, a
.third:         ld   b, 8
                ld   a, (BLIT_CROWS)
                dec  a
                ret  z
                ld   (BLIT_CROWS), a
blit_al_jp:     jp   blit_chain_al             ; SMC: entry for this width
                ASSERT (blit_chain_al_end - blit_chain_al) == BLIT_BLOCK * BLIT_MAXW

                ASSERT FT_H == FT_COLS + 1     ; blit_sprite: inc hl
                ASSERT FT_OFFR == FT_H + 1 && FT_OFFL == FT_OFFR + 1 ; render .vis: inc hl chain
