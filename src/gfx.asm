;==============================================================================
; gfx.asm — PROTO graphics layer (bank 2, hot).
;   paging + the bank-3 far-call trampoline, masked blit at any (px multiple
;   of 4, py) (§5.1), exact-footprint attr stamp (§4.2), tile-map
;   erase/restore (§4.3), HUD text, room draw. The boot-time generator and
;   init_tiles live in lowram.asm (bank 5); the transition scrolls in
;   bank3.asm.
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
; far3 — call the bank-3 cold routine at HL with bank 3 paged in at $C000, then
; put the caller's $C000 bank back (saved PORT_7FFD_SHADOW value, bits 0-2).
; In : HL = target (bank3.asm), A = passed to the target in A.
; Out: the target's BC, DE, HL, IX (passed through).  Clobbers: A, F.
; ~220 T + target. Not re-entrant into another bank (bank-3 code must not page
; $C000 itself — see bank3.asm; it blits through blit_keep).
;==============================================================================
far3:
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page uses bits 0-2)
                ld   a, b
                push af                        ; target's A
                ld   a, BANK_COLD3
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

;==============================================================================
; tile_rect — draw the background tiles (glyph AND attr) of a cell rect from
; the tile map (prototype §4.3). Target = the screen, or the bank-7 clean-
; background shadow (set_tile_target). Used for room draws, transition columns
; and shadow upkeep; per-tick sprite erase uses the faster erase_rect below.
; In : C = col, B = row, D = cols, E = rows (inside 0..31 x 0..20).
; Clobbers: A, BC, DE, HL.   ~290 T/cell (listing: 8 glyph rows unrolled).
;------------------------------------------------------------------------------
; Screen bitmap, attrs and the page-aligned map share the low byte
; ((row&7)<<5 | col) — so per row we patch three high bytes (SMC) and walk C.
; SMC: .mh+1 (map high), .ah+1 (attr high), .sh+1 (bitmap high) patched per row.
;==============================================================================
tile_rect:
                ld   a, e
                ld   (.rows+1), a             ; SMC: rows remaining
                ld   a, d
                ld   (.cols+1), a             ; SMC: cols per row
.row:
                ld   a, b                     ; B = row
                rrca
                rrca
                rrca
                ld   e, a                     ; E = row rotated
                and  3
                ld   d, a                     ; D = row >> 3
.mhi:           add  a, ROOM_MAP >> 8         ; SMC: map page (ROOM_MAP / NEXT_MAP)
                ld   (.mh+1), a
                ld   a, d
.aor:           or   SCREEN_ATTR >> 8          ; SMC: $58 screen / $F8 shadow (A7)
                ld   (.ah+1), a
                ld   a, b
                and  $18
.bor:           or   SCREEN_BITMAP >> 8        ; SMC: $40 screen / $E0 shadow (A7)
                ld   (.sh+1), a
                ld   a, e
                and  $E0
                or   c
                push bc                        ; keep row/col for the next row
                ld   c, a                      ; C = low byte of this row's first cell
.cols:          ld   b, 0                      ; SMC: cols
.cell:
                ld   l, c
.mh:            ld   h, 0                      ; SMC: map high
                ld   a, (hl)                   ; tile id
                ld   d, a
                ld   l, a
                ld   h, TILE_ATTRS >> 8
                ld   a, (hl)                   ; tile attr
                ld   l, c
.ah:            ld   h, 0                      ; SMC: attr high
                ld   (hl), a
                ld   a, d
                add  a, a
                add  a, a
                add  a, a                      ; CF = id bit 5 (ids < TILE_IDS = 64)
                ld   e, a
                ld   d, TILE_GLYPHS >> 9
                rl   d                         ; DE = TILE_GLYPHS + id*8 (512-aligned base; +8 T vs 32 ids)
.sh:            ld   h, 0                      ; SMC: bitmap high (L = C still)
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                inc  c
                djnz .cell
                pop  bc
                inc  b                         ; next row
.rows:          ld   a, 0                      ; SMC: rows remaining
                dec  a
                ld   (.rows+1), a
                jr   nz, .row
                ret

; select which map tile_rect reads (A = high byte of ROOM_MAP or NEXT_MAP)
set_tile_map:
                ld   (tile_rect.mhi+1), a
                ret

; set_tile_target — A = 0: tile_rect draws to the screen; else to the shadow
; (bank 7 $E000/$F800 — the caller pages bank 7).
; Clobbers: A
set_tile_target:
                or   a
                ld   a, SCREEN_ATTR >> 8
                jr   z, .s
                ld   a, SHADOW_ATTR >> 8
.s:             ld   (tile_rect.aor+1), a
                sub  (SCREEN_ATTR - SCREEN_BITMAP) >> 8
                ld   (tile_rect.bor+1), a
                ret
                ; tile_rect ORs the row bits into these bases
                ASSERT SHADOW_ATTR - SHADOW_BITMAP == SCREEN_ATTR - SCREEN_BITMAP
                ASSERT (SHADOW_BITMAP & $17FF) == 0 && (SHADOW_ATTR & $3FF) == 0

; shadow_rect — redraw rect C,B,D,E of the clean-background shadow (bank 7)
; from ROOM_MAP (room entry, potion taken).  Clobbers: A, BC, DE, HL
shadow_rect:
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   a, 1
                call set_tile_target
                call tile_rect
                xor  a
                jp   set_tile_target

;==============================================================================
; erase_rect — restore a cell rect (bitmap + attrs) from the clean-background
; shadow in bank 7 (prototype R-1 lever: "clean-background copy for erase").
; Shadow = the room's tiles in screen layout at $E000/$F800 (A7: rebased above
; screen 2), so source and destination share the low byte and differ by +$A0
; in the high byte.
; In : C = col, B = row, D = cols, E = rows.  Clobbers: A, BC, DE, HL (IX kept)
; ~280 T + 231 T/cell + 74 T/row (+~110 T per third crossed). A7b: the row
; addresses step incrementally (low byte += 32; a carry = next third: bitmap
; high += 8, attr high += 1) instead of being rebuilt from the row number
; (218 -> 74 T per row; heavy fight: 26 rows/tick).
; SMC: .cols+1, .rows+1 per call; .bh/.dh/.ah/.dah+1 per call / third.
;==============================================================================
erase_rect:
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
                ld   a, d
                ld   (.cols+1), a
                ld   a, e
                ld   (.rows+1), a
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   (.bh+1), a
                add  a, (SHADOW_BITMAP - SCREEN_BITMAP) >> 8
                ld   (.dh+1), a
                ld   a, b
                rrca
                rrca
                rrca
                ld   e, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   (.ah+1), a
                add  a, (SHADOW_ATTR - SCREEN_ATTR) >> 8
                ld   (.dah+1), a
                ld   a, e
                and  $E0
                or   c
                ld   c, a                      ; C = low byte of the row's first cell
.row:           ld   e, c
.cols:          ld   b, 0                      ; SMC: cols
.cell:          ld   l, e
.bh:            ld   h, 0                      ; SMC: screen bitmap high
.dh:            ld   d, 0                      ; SMC: shadow bitmap high
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  h
                inc  d
                EDUP
                ld   a, (de)
                ld   (hl), a
.ah:            ld   h, 0                      ; SMC: screen attr high
.dah:           ld   d, 0                      ; SMC: shadow attr high
                ld   a, (de)
                ld   (hl), a
                inc  e
                djnz .cell
.rows:          ld   a, 0                      ; SMC: rows left
                dec  a
                ret  z
                ld   (.rows+1), a
                ld   a, c
                add  a, 32                     ; next char row: same third ...
                ld   c, a
                jr   nc, .row
                ld   hl, .bh+1                 ; ... or the next one (rare)
                ld   a, (hl)
                add  a, 8
                ld   (hl), a
                ld   hl, .dh+1
                ld   a, (hl)
                add  a, 8
                ld   (hl), a
                ld   hl, .ah+1
                inc  (hl)
                ld   hl, .dah+1
                inc  (hl)
                jr   .row

;==============================================================================
; PRESENT — A7 double buffer, option A (docs/design/budget.md §3). During play
; the ULA shows bank 7's screen 2 ($C000); everything is still composed in
; bank 5 ($4000) as before, and present copies the cells changed since the
; last present from bank 5 to screen 2, so the beam never sees an erased
; sprite. Changed cells are marked in PRES_MASK (pmark_rect) by:
;   - render's damage list (pmark_dmg): erased old footprints, new / forced
;     footprints, attr-only stamps, PEND_DMG restores (potion, zap end);
;   - draw_zap (the overlay is not in the damage list);
;   - the HUD rows (clear_row + print_char keep HUD_EXT / HUD_PW per row: only
;     the cols that held or now hold text are copied, not all 32).
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
; Cost: ~50 T if nothing is marked; else ~65 T per clean row + ~200 T per
; dirty row + ~75 T per non-zero mask byte + 251 T per copied cell (contended:
; 2 accesses per byte, budget §4) + 31 T per clear bit before a byte's last;
; a full mask byte (8 cells: HUD text) ~1.5k T by LDI lines (.full8, A7b).
; SMC: .sbh/.dbh/.sah/.dah+1 (src/dst bitmap/attr high; .full8 reads them
; too) and .rb+1 (the row's low-byte base) patched per dirty row.
;------------------------------------------------------------------------------
present:
                ld   a, (PRES_ANY)
                or   a
                ret  z
                ld   hl, HUD_PW                ; HUD rows: mark cols 0..PW-1
                ld   b, HUD_ROW
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
                cp   HUD_ROW + HUD_ROWS
                jr   c, .hud
                xor  a
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
                rrca
                rrca                           ; A = row 0..23
.probe_row:                                    ; flicker probe (no code): A = row
                ld   b, a
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   (.sbh+1), a
                add  a, (SCREEN7_BITMAP - SCREEN_BITMAP) >> 8
                ld   (.dbh+1), a
                ld   a, b
                rrca
                rrca
                rrca
                ld   c, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   (.sah+1), a
                add  a, (SCREEN7_ATTR - SCREEN_ATTR) >> 8
                ld   (.dah+1), a
                ld   a, c
                and  $E0
                ld   (.rb+1), a                ; (row & 7) << 5
.byte:          ld   a, (hl)
                or   a
                jr   z, .nextb
                ld   (hl), 0
                push hl
                ld   c, a                      ; C = bits left, bit 7 = this col
                ld   a, l
                and  3                         ; mask byte index in the row
                add  a, a
                add  a, a
                add  a, a
.rb:            or   0                         ; SMC: row low base
                ld   b, a                      ; B = low byte of the cell
                ld   a, c
                inc  a
                jr   nz, .bits
                ld   a, b
                cp   $F8                       ; (cols 24-31 of a third's last char
                jr   nz, .full8                ; row: LDI would carry into H)
.bits:          dec  b                         ; (.bit pre-increments)
.bit:           inc  b
                sla  c
                jr   c, .copy
                jr   .bit                      ; clear bit, set bits remain: 31 T
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
                inc  c
                dec  c
                jr   nz, .bit                  ; more set bits in this byte
                pop  hl
.nextb:         inc  l
                ld   a, l
                and  3
                jr   nz, .byte
.probe_row_end:                                ; flicker probe (no code)
                or   l                         ; A = 0 here: L = 0 <=> past row 23
                jp   nz, .rowt
                ret
                ; A7b: a full mask byte = 8 cells side by side (HUD text runs),
                ; copied line by line with LDI (16 T/byte, no per-cell setup):
                ; ~1.5k T vs ~2.1k per byte. Low byte <= $F0 here, so the 8
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
                ASSERT SCREEN7_ATTR - SCREEN7_BITMAP == SCREEN_ATTR - SCREEN_BITMAP

;==============================================================================
; draw_room — full redraw of rows 0..20 from ROOM_MAP.  ~195k T (boot/room only)
;==============================================================================
draw_room:
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   bc, 0                     ; row 0, col 0
                ld   de, (ROOM_COLS << 8) | ROOM_ROWS
                call tile_rect
                ; fall through: rebuild the clean-background shadow too
; shadow_room — whole-room shadow rebuild (~195k T; room entry only).
shadow_room:
                ld   bc, 0
                ld   de, (ROOM_COLS << 8) | ROOM_ROWS
                jp   shadow_rect

;==============================================================================
; clear_screen — bitmap 0, attrs = A.   Clobbers: BC, DE, HL
;==============================================================================
clear_screen:
                push af
                ld   hl, SCREEN_BITMAP
                ld   de, SCREEN_BITMAP + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ld   (hl), 0
                ldir
                pop  af
                ld   hl, SCREEN_ATTR
                ld   de, SCREEN_ATTR + 1
                ld   bc, SCREEN_ATTR_LEN - 1
                ld   (hl), a
                ldir
                ret

;==============================================================================
; TEXT (ROM charset, 48K ROM paged).
; print_char — A = ASCII 32..127 at cell (row B, col C); C advances. A7: no
; HUD tracking here (callers end with hud_track: print_str, print_dec,
; print_char_hud).  Clobbers: A, DE, HL.
;==============================================================================
print_char:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, ROM_CHARSET - 32 * 8
                add  hl, de
                ex   de, hl                    ; DE = glyph
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   l, a
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e                         ; A7b: ROM glyphs are 8-aligned (-14 T/char)
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                inc  c
                ret
                ASSERT (ROM_CHARSET & 7) == 0

;------------------------------------------------------------------------------
; hud_track — after text ending at (row B, col C-1): on a HUD row widen
; HUD_EXT / HUD_PW to C (A7: present copies the row's first HUD_PW cells).
; Called once per string (print_str end, print_dec, print_char_hud), not per
; char.  Clobbers: A, HL.   ~22 T off the HUD, ~85 T on it.
;------------------------------------------------------------------------------
; print_char_hud — print_char + hud_track (a lone char ending a HUD line).
print_char_hud:
                call print_char
hud_track:
                ld   a, b
                sub  HUD_ROW
                ret  c                         ; not a HUD row
                add  a, HUD_EXT & $FF
                ld   l, a
                ld   h, HUD_EXT >> 8
                ld   a, c
                cp   (hl)
                jr   c, .pw
                ld   (hl), a                   ; EXT = max(EXT, C)
.pw:            ld   a, l
                add  a, HUD_ROWS
                ld   l, a                      ; -> HUD_PW of the row
                ld   a, c
                cp   (hl)
                ret  c
                ld   (hl), a                   ; PW = max(PW, C)
                ld   a, 1
                ld   (PRES_ANY), a
                ret
                ASSERT HUD_PW == HUD_EXT + HUD_ROWS && HUD_ROW + HUD_ROWS == 24
                ASSERT (HUD_EXT >> 8) == ((HUD_PW + HUD_ROWS - 1) >> 8)

; print_str — HL = 0-terminated string at (row B, col C). C advances.
; Clobbers: A, C, DE, HL
print_str:
                ld   a, (hl)
                or   a
                jr   z, hud_track              ; A7: once per string
                push hl
                call print_char
                pop  hl
                inc  hl
                jr   print_str

; print_dec — A (0..255) in decimal, no leading zeros, at (B, C). C advances.
; Clobbers: A, DE, HL
print_dec:
                ld   l, 0                      ; L = "printed a digit" flag
                ld   h, 100
                call .digit
                ld   h, 10
                call .digit
                add  a, '0'
                call print_char
                jp   hud_track                 ; A7
.digit:
                ld   e, '0' - 1
.sub:           inc  e
                sub  h
                jr   nc, .sub
                add  a, h                      ; A = remainder
                ld   d, a
                ld   a, e
                cp   '0'
                jr   nz, .out
                bit  0, l
                jr   z, .skip                  ; leading zero -> nothing
.out:           ld   l, 1
                push hl
                push de
                ld   a, e
                call print_char
                pop  de
                pop  hl
.skip:          ld   a, d
                ret

; clear_row — blank the bitmap of char row B and set its 32 attrs to A; tells
; present what changed (A7, hud_clear_mark). A7: on a HUD row only the cols
; that can hold ink (HUD_EXT) are blanked — the rest is blank already.
; Unrolled fill: ~0.4k + 88 T per blanked col (3.3k for a whole row).
; Clobbers: A, DE, HL (BC kept)
; SMC: .lj+1 = entry into the unrolled blanking chain (32 - cols stores in).
clear_row:
                push bc
                ld   c, 0
                push af
                call hud_clear_mark            ; A7: A = cols to blank (low RAM)
                ld   e, a
                ld   a, ROOM_COLS
                sub  e
                add  a, a                      ; 2 B per store (ld (hl),a / inc l)
                ld   l, a
                ld   h, 0
                ld   de, .chain
                add  hl, de
                ld   (.lj+1), hl
                call attr_addr
                pop  af
                DUP  32
                ld   (hl), a
                inc  l
                EDUP
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                ld   e, a                      ; E = row low byte
                ld   c, 8
                xor  a
.line:          ld   l, e
.lj:            jp   .chain                    ; SMC: chain entry
.chain:         DUP  32
                ld   (hl), a
                inc  l
                EDUP
                inc  h
                dec  c
                jr   nz, .line
                pop  bc
                ret

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
                call page_bank                 ; (A, BC)
                ld   a, (BL_FID)
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl                    ; fid*FT_STRIDE (4; ASSERTed at ft_ptr)
                ld   de, frame_tab + FT_COLS
                add  hl, de
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

;==============================================================================
; frame_footprint — exact cell footprint of frame A at (fpx E, fpy D).
; Out: C = col, B = row, D = cols, E = rows.  Clobbers: A, HL
;   cols = (fpx&7 + W + 7) >> 3 ; rows = (fpy&7 + H + 7) >> 3   (§4.2 exact)
;==============================================================================
frame_footprint:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl                    ; fid*FT_STRIDE
                push de
                ld   de, frame_tab + FT_COLS
                add  hl, de
                pop  de
                ld   a, e
                and  4
                ld   a, (hl)                   ; cols
                jr   z, .c0
                inc  a                         ; shifted -> +1 spill col
.c0:            ld   c, a                      ; C = cols (temp)
                inc  hl
                ld   a, d
                and  7
                add  a, (hl)                   ; + H
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F
                ld   l, a                      ; L = rows
                ld   a, d
                rrca
                rrca
                rrca
                and  $1F
                ld   b, a                      ; B = row
                ld   d, c                      ; D = cols
                ld   a, e
                rrca
                rrca
                rrca
                and  $1F
                ld   c, a                      ; C = col
                ld   e, l                      ; E = rows
                ret

; ft_ptr — HL = frame_tab + A*FT_STRIDE (4).  Clobbers: A, DE, HL
                ASSERT FT_STRIDE == 4          ; blit_sprite / frame_footprint / ft_ptr: 2 x add hl,hl
                ASSERT FT_H == FT_COLS + 1     ; blit_sprite / frame_footprint: inc hl
                ASSERT FT_OFFR == FT_H + 1 && FT_OFFL == FT_OFFR + 1 ; render .vis: inc hl chain
ft_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                ld   de, frame_tab
                add  hl, de
                ret
