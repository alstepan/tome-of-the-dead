;==============================================================================
; spike_sideview.asm — SIDE-VIEW FEASIBILITY SPIKE (throwaway, risk-retirement).
;
; Target : ZX Spectrum 128K   Origin : $8000   Build: SEPARATE from main.asm.
; Assemble with:  sjasmplus src/spike_sideview.asm --fullpath \
;                          --lst=build/spike.lst --sld=build/spike.sld -i src
; Emits build/spike.tap (+ .sna) — does NOT touch build/wazhack.* (P3 stays green).
;
; Proves (docs/design/sideview-renderer.md): a recognizable 16x24 MASKED sprite
; composited IN COLOUR at an arbitrary pixel X over a wider-than-screen coloured
; background that scrolls to follow it, redrawn every frame with no bitmap/colour
; trails and with attribute clash actively managed (per-cell attribute-follow),
; all inside a measurable per-frame budget on the single live screen.
;
; Design fidelity & deliberate deviations (documented per the task):
;  - Input primitives (scan_matrix/sample_keys/dirs_to_step) and the keyboard
;    mirror addresses (INPUT_SRC/KBD_MATRIX) are COPIED from main.asm so the spike
;    is a self-contained throwaway image; semantics + test-injection path are
;    identical (M2 would factor a shared src/input.asm). The chord get_action turn
;    loop is intentionally replaced by a per-frame HALT-synced loop (design §3.4).
;  - When the player is NOT moving the per-frame render is SKIPPED (no erase/blit):
;    keeps the single-buffer screen static at rest so goldens + at-rest attribute
;    assertions are deterministic. Motion frames do the full erase->move->stamp->
;    blit and DO flicker (single buffer) — that flicker is the spike's recorded
;    finding, not a bug.
;  - Border colour brackets each render phase so a scope/emulator shows the raster
;    cost (design §5.4): BLACK idle, RED erase(restore attrs+bitmap), MAGENTA
;    draw(stamp attrs+blit), CYAN scroll redraw.
;
; No $7FFD paging (design §6.1).  IY kept = $5C3A for the ROM IM1 ISR (HALT).
;==============================================================================

                DEVICE ZXSPECTRUM128

                INCLUDE "constants.asm"

;------------------------------------------------------------------------------
; Spike-only constants (not in constants.asm — throwaway).
;------------------------------------------------------------------------------
IY_SYSVAR       EQU $5C3A           ; ROM system-var base (conventions: keep in IY)

; Colour bands + sprite colour (design §2.2 / §1.7). Feature attrs equal their
; band attr by construction (pillar/doorway ink=cyan -> $05 = ATTR_AIR; floor/
; ground -> $4F = ATTR_GROUND), so the band fill colours the whole backdrop and
; the legal attribute set is exactly {ATTR_AIR, ATTR_GROUND, ATTR_SPRITE}.
ATTR_AIR        EQU COL_CYAN  | (COL_BLACK << PAPER_SHIFT)               ; $05
ATTR_GROUND     EQU COL_WHITE | (COL_BLUE  << PAPER_SHIFT) | ATTR_BRIGHT ; $4F
ATTR_SPRITE     EQU ATTR_PLAYER                                          ; $46

; Background tile ids (parallel to assets/gfx/bg_tiles.asm order).
BG_BLANK        EQU 0
BG_FLOOR        EQU 1
BG_GROUND       EQU 2
BG_PILLAR       EQU 3
BG_DOORWAY      EQU 4

; World / viewport geometry (design §3.3).
WORLD_COLS      EQU 64              ; 512 px of travel (2x the 32-col viewport)
VIEW_COLS       EQU 32
VIEW_ROWS       EQU 24
WORLD_CELLS     EQU WORLD_COLS * VIEW_ROWS   ; 1536 tile bytes
GROUND_ROW      EQU 18              ; first ground-band char row (rows 18-23)

; Sprite footprint (design §1.5/§2.3): 3 char cols x 3 char rows, rows 15-17.
SPRITE_TOP_ROW  EQU 15
SPRITE_H_ROWS   EQU 3
SPRITE_W_COLS   EQU 3
SPRITE_PY_VAL   EQU SPRITE_TOP_ROW * 8       ; 120 (char-aligned, no Y pre-shift)

; Dead-zone follow (design §3.2): sprite (left col) clamped to cols 12..18.
DEAD_L          EQU 12
DEAD_R          EQU 18
ORIGIN_MAX      EQU WORLD_COLS - VIEW_COLS    ; 32
SPRITE_PX_INIT  EQU 120             ; world px -> sc=15 at origin 0 (centre)
SPRITE_PX_MAX   EQU 488             ; keeps sprite right col <=31 at origin max
MOVE_STEP       EQU 2               ; px / frame while a direction key is held

TRACK_COL       EQU 28              ; trackable pillar (sky band, rows 12-17)

; SPIKE-2 build flag (A/B the scroll path on the SAME scene for apples-to-apples).
;   0 (default) = byte-shift scroll: shift the visible playfield 1 byte-col in
;                 place + redraw only the newly-exposed column (scroll_view_*).
;   1           = naive scroll: redraw all 768 cells every step (do_scroll_redraw)
;                 — the ~537k T baseline the reviewer measured. Flip to A/B.
USE_NAIVE_SCROLL EQU 0

; SPIKE-3 build flag (A/B the shift HEIGHT on the SAME scene). Rows 0-11 are blank
; sky and rows 0-17 attrs are a uniform ATTR_AIR band, so both are shift-invariant
; for THIS scene — a content-rows-only shift is byte-exact vs the full-height path
; (tests/scroll.py + tests/sideview.py stay green either way).
;   1 (default) = content-rows-only: shift only the 12 non-sky bitmap rows (char
;                 rows 12..23 = pixel rows 96..191, 96 scanlines) and only the 6
;                 ground-band attr rows (18..23). ~91k T -> ~1.28 frames.
;   0           = full-height SPIKE-2 path: all 192 scanlines + 24 attr rows
;                 (~146k T -> ~2.07 frames) — the A/B baseline.
SHIFT_CONTENT_ROWS_ONLY EQU 1

; Content-shift geometry (derived, no magic addresses). Bitmap content begins at
; char row 12 whose top scanline address is $4880 (high $40|(row&$18)=$48, low
; (row&7)<<5=$80). The ZX third boundary at char row 16 (pixel 128) is bitmap high
; $50, where the enumeration crosses from third 1 (rows 12-15, r'>=4) into third 2
; (rows 16-23, all r'). Ground-band attrs start at $5A40 (= SCREEN_ATTR+18*32).
CONTENT_TOP_ROW EQU 12
BMP_C_START     EQU SCREEN_BITMAP + ((CONTENT_TOP_ROW & $18) << 8) + ((CONTENT_TOP_ROW & 7) << 5) ; $4880
BMP_T2_HIGH     EQU SCREEN_BITMAP >> 8 | (16 & $18)   ; $50: bitmap high byte of third 2 (row 16)
ATTR_C_START    EQU SCREEN_ATTR + GROUND_ROW * 32     ; $5A40: first ground-band attr row

; Pre-shift table (design §1.3): 8 copies x 144 B, generated at boot.
PRESHIFT_FRAME  EQU 144             ; one 16x24 [mask,data]x3 frame
PRESHIFT_COUNT  EQU 8
PRESHIFT_SIZE   EQU PRESHIFT_FRAME * PRESHIFT_COUNT   ; 1152

;------------------------------------------------------------------------------
; Spike RAM (docs/memory-map.md "Side-view spike"). Buffers sit below the entity
; region; the test-observable bytes sit ABOVE the initial SP ($BF00) alongside
; the existing INPUT_SRC/KBD_MATRIX mirror (stack grows down, never reaches them).
;------------------------------------------------------------------------------
PRESHIFT_TABLE  EQU $A000           ; 1152 B  $A000..$A47F (boot-generated)
WORLD_BUF       EQU $A500           ; 1536 B  $A500..$AAFF (64x24 tile ids)

CUR_SC          EQU $BF10           ; byte: current sprite screen col (scratch)
CUR_DX          EQU $BF11           ; byte: this frame's dx (-1/0/+1)
SPRITE_PX       EQU $BF12           ; word: player WORLD pixel X (test-observable)
SPRITE_PY       EQU $BF14           ; byte: sprite top pixel Y (constant)
VIEW_ORIGIN_COL EQU $BF15           ; byte: world col shown at screen col 0 (t-o)
FRAME_COUNTER   EQU $BF16           ; word: per-frame liveness counter (t-o)

                ORG $8000

;==============================================================================
; spike_start — boot: state, pre-shifts, world, first full render, then loop.
;==============================================================================
spike_start:
                di
                ld   sp, WORKSTORE_TOP        ; reuse main's SP slot ($BF00)
                ld   iy, IY_SYSVAR            ; ROM ISR invariant (HALT/keyboard)

                ld   hl, SPRITE_PX_INIT
                ld   (SPRITE_PX), hl
                ld   a, SPRITE_PY_VAL
                ld   (SPRITE_PY), a
                xor  a
                ld   (VIEW_ORIGIN_COL), a
                ld   (INPUT_SRC), a           ; default: scan real keyboard
                ld   hl, 0
                ld   (FRAME_COUNTER), hl

                call init_kbd_mirror
                call gen_preshifts            ; 8 pre-shifts from the S=0 frame
                call build_world              ; 64x24 coloured side-view scene

                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                call clear_bitmap
                call fill_bands               ; air rows -> $05, ground rows -> $4F
                call redraw_view              ; blit the 32 visible cols (bitmap)
                call compute_sc               ; CUR_SC = initial screen col
                ld   a, ATTR_SPRITE
                call stamp_foot               ; colour the footprint
                call blit_current_sprite      ; composite the masked sprite
                ei                            ; ROM IM1 ISR on (HALT pacing)

;==============================================================================
; spike_loop — per-frame: sample held keys, and only if moving do the full
; erase->move/scroll->stamp->blit. Idle frames leave the screen untouched so the
; single-buffer image is stable at rest (deterministic goldens/assertions).
;==============================================================================
spike_loop:
                call read_dx                  ; D = dx (-1/0/+1)
                ld   a, d
                ld   (CUR_DX), a
                or   a
                jp   z, .idle                 ; not moving -> skip render

                ; --- erase old position (RED): restore attrs + redraw bg ------
                ld   a, COL_RED
                out  (PORT_BORDER), a
                call compute_sc               ; CUR_SC = OLD screen col
                ld   a, ATTR_AIR
                call stamp_foot               ; 9 cells -> band (restore colour)
                call erase_foot               ; 9 bg cells (restore bitmap)

                call apply_motion             ; move ±2px; scroll if at dead-zone

                ; --- draw new position (MAGENTA): stamp attrs + blit ----------
                ld   a, COL_MAGENTA
                out  (PORT_BORDER), a
                call compute_sc               ; CUR_SC = NEW screen col
                ld   a, ATTR_SPRITE
                call stamp_foot               ; 9 cells -> sprite colour
                call blit_current_sprite
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
.idle:
                ld   hl, (FRAME_COUNTER)
                inc  hl
                ld   (FRAME_COUNTER), hl
                halt                          ; 50 Hz frame sync (design §3.4)
                jp   spike_loop

;==============================================================================
; read_dx — sample held keys into a signed dx via the reused input primitives.
; Out: D = dx (-1/0/+1).  Clobbers: A, BC, DE, HL
;==============================================================================
read_dx:
                call scan_matrix              ; refresh mirror (or keep injected)
                call sample_keys              ; A = DIR_* bitset
                call dirs_to_step             ; D = dx, E = dy
                ret

;==============================================================================
; apply_motion — advance SPRITE_PX by ±MOVE_STEP, clamp to the world, and scroll
; the viewport one cell when the sprite reaches a dead-zone margin (design §3.2).
; A scroll repaints the visible columns (do_scroll_redraw). At most one cell/step
; (sprite moves 2px so PX>>3 changes by <=1 per frame).
; In : CUR_DX (-1/+1, nonzero).  Clobbers: A, BC, DE, HL
;==============================================================================
apply_motion:
                ld   a, (CUR_DX)
                bit  7, a                     ; dx<0 ($FF) -> west
                jr   nz, .west
                ld   hl, (SPRITE_PX)
                ld   de, MOVE_STEP
                add  hl, de
                ld   de, SPRITE_PX_MAX
                call clamp_hl_max
                ld   (SPRITE_PX), hl
                jr   .scrollchk
.west:
                ld   hl, (SPRITE_PX)
                ld   de, MOVE_STEP
                or   a
                sbc  hl, de
                jr   nc, .wok                 ; no borrow -> still >= 0
                ld   hl, 0
.wok:
                ld   (SPRITE_PX), hl
.scrollchk:
                call compute_sc               ; CUR_SC for the new PX
                ld   a, (CUR_SC)
                cp   DEAD_R + 1
                jr   c, .chkL                 ; sc <= DEAD_R -> within dead zone
                ld   a, (VIEW_ORIGIN_COL)
                cp   ORIGIN_MAX
                ret  nc                       ; world fully scrolled -> clamp
                inc  a
                ld   (VIEW_ORIGIN_COL), a
    IF USE_NAIVE_SCROLL
                call do_scroll_redraw         ; baseline: full 768-cell redraw
    ELSE
                call scroll_view_east         ; SPIKE-2: byte-shift left + 1 col
    ENDIF
                jp   compute_sc               ; recompute sc post-scroll (tail)
.chkL:
                cp   DEAD_L
                ret  nc                       ; sc >= DEAD_L -> within dead zone
                ld   a, (VIEW_ORIGIN_COL)
                or   a
                ret  z                        ; origin 0 -> cannot scroll left
                dec  a
                ld   (VIEW_ORIGIN_COL), a
    IF USE_NAIVE_SCROLL
                call do_scroll_redraw         ; baseline: full 768-cell redraw
    ELSE
                call scroll_view_west         ; SPIKE-2: byte-shift right + 1 col
    ENDIF
                jp   compute_sc

;==============================================================================
; clamp_hl_max — HL = min(HL, DE).  Clobbers: A flags only (HL adjusted).
;==============================================================================
clamp_hl_max:
                push hl
                or   a
                sbc  hl, de
                pop  hl
                ret  c                        ; HL < DE -> keep HL
                ld   h, d
                ld   l, e                     ; HL >= DE -> clamp to DE
                ret

;==============================================================================
; do_scroll_redraw — repaint the 32 visible columns (bitmap) and the 32x24
; attributes from the world buffer (design §3.3). For THIS scene the attrs are
; scroll-invariant (band is a pure function of row, features share band attr), so
; fill_bands rewrites identical values — included so the reviewer can MEASURE the
; per-scroll-step attribute pass the design budgets (CYAN border bracket).
;==============================================================================
do_scroll_redraw:
                ld   a, COL_CYAN
                out  (PORT_BORDER), a
                call redraw_view
                call fill_bands
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                ret

;==============================================================================
; BYTE-SHIFT HORIZONTAL SCROLL (design §3.3 / plan SPIKE-2 & SPIKE-3).
;
; Instead of redrawing all 768 cells (do_scroll_redraw, ~537k T), shift the
; visible 32-col playfield one byte-column IN PLACE and redraw ONLY the single
; newly-exposed column from WORLD_BUF. The pre-shift screen is, by induction, a
; faithful render of world cols [origin..origin+31]; the sprite is erased BEFORE
; apply_motion is called (spike_loop step 1), so the shift moves pure background.
;
; SPIKE-3 LEVER (default, SHIFT_CONTENT_ROWS_ONLY=1): shift only the 12 non-sky
; content rows. Rows 0-11 bitmap is blank sky (shift-invariant) and rows 0-17
; attrs are a uniform ATTR_AIR band (shift-invariant) for THIS scene, so the
; content-only shift is byte-exact (tests/scroll.py + sideview.py green).
;
; Per 8px EAST scroll STEP, per-instruction from build/spike.lst (uncontended;
; budget 70,908 T/frame, 128K). Content path (default):
;   shift_bitmap_left    96 scanlines : third1 rows12-15 18,762 + third2         (lst 379-411)
;                                        rows16-23 36,835 + ld ix 14       ~55,611 T
;                                        (LDI cont scanline = 570 T; 96x)
;   shift_attr_left       6 rows 18-23 : 5x570 + 565 wrap + 44 adv + 14     ~3,473 T  (lst 508-524)
;   draw_newcol_bitmap   24 cells      : ~678 T/cell (unchanged, full col)  ~17,500 T (lst 579-589)
;   set_newcol_attr      24 band wr.   : ~199 T/row (unchanged, full col)    ~4,800 T (lst 598-614)
;   ----------------------------------------------------------------------------
;   TOTAL per 8px EAST scroll step (+~164 wrapper)                   ~81,500 T
;        = 1.15 frames   vs SPIKE-2 full-height ~146,400 T = 2.07 fr  (1.80x win)
;   WEST ~+2.4k (shift_*_right add 24 T/scanline addr-arith): ~84,000 T = 1.19 fr.
;   NOTE: the SCROLL STEP is background only. The 1-in-4 scroll FRAME also erases
;   + reblits the sprite (~13.5k T, the SPIKE motion-frame cost), so the real
;   worst-case scroll frame under sustained edge-walking is ~95k T (east) / ~97.5k
;   (west) ~= 1.34/1.37 frames. The 3 intervening glide frames are ~13.5k (~0.19
;   frame). Contended (ULA, screen R/W by the LDI/LDD moves): add ~+40% on the
;   move-heavy shift phases.
; FURTHER LEVERS (not taken): skip sky rows in draw_newcol/set_newcol too (the
;   exposed col-31/0 sky is already blank/ATTR_AIR); shadow-screen double-buffer
;   to make the >1-frame scroll tear-free (M2 polish, see plan SPIKE-3 exit gate).
;
; Full-height baseline (SHIFT_CONTENT_ROWS_ONLY=0, A/B): shift_bitmap ~110,300 T
; (192 scanlines) + shift_attr ~13,800 T (24 rows) + newcol 17,500 + setattr 4,800
;   = ~146,400 T = 2.07 frames. Flip the flag for apples-to-apples measurement.
;
; Border bracket per phase so a scope shows the raster cost (design §5.4):
;   CYAN bitmap-shift, YELLOW attr-shift, WHITE new-column, BLACK done.
; Clobbers: A, BC, DE, HL, IX.  (IY kept = $5C3A; ROM ISR preserves IX/BC/etc.)
;==============================================================================

;------------------------------------------------------------------------------
; scroll_view_east — origin already incremented: shift screen LEFT 1 col, expose
; world col (origin+31) at screen col 31.
;------------------------------------------------------------------------------
scroll_view_east:
                ld   a, COL_CYAN
                out  (PORT_BORDER), a
                call shift_bitmap_left
                ld   a, COL_YELLOW
                out  (PORT_BORDER), a
                call shift_attr_left
                ld   a, COL_WHITE
                out  (PORT_BORDER), a
                ld   c, VIEW_COLS - 1         ; screen col 31 = newly exposed
                call draw_newcol_bitmap
                ld   c, VIEW_COLS - 1
                call set_newcol_attr
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                ret

;------------------------------------------------------------------------------
; scroll_view_west — origin already decremented: shift screen RIGHT 1 col, expose
; world col (origin) at screen col 0. Symmetric to east (LDD vs LDI).
;------------------------------------------------------------------------------
scroll_view_west:
                ld   a, COL_CYAN
                out  (PORT_BORDER), a
                call shift_bitmap_right
                ld   a, COL_YELLOW
                out  (PORT_BORDER), a
                call shift_attr_right
                ld   a, COL_WHITE
                out  (PORT_BORDER), a
                ld   c, 0                     ; screen col 0 = newly exposed
                call draw_newcol_bitmap
                ld   c, 0
                call set_newcol_attr
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                ret

;==============================================================================
; shift_bitmap_left — move every bitmap scanline's cols 1..31 -> 0..30 (col 31
; left stale, redrawn by draw_newcol_bitmap). Enumerates the 192 scanline bases
; directly in screen-address space ($40..$57 high x {0,32,..,224} low), so NO
; per-line y->addr formula is needed; the low-byte +32 overflow naturally counts
; the 8 lines per high page. Unrolled LDI (16 T/byte) beats LDIR (21 T) for the
; 31-byte move. Order is irrelevant for a pure horizontal shift.
; Clobbers: A, BC (via LDI), DE, HL, IX.
;==============================================================================
shift_bitmap_left:
    IF SHIFT_CONTENT_ROWS_ONLY
                ; SPIKE-3: shift only char rows 12..23 (pixel 96..191). The scanline
                ; enumeration is the SAME +32/wrap address walk, but it starts at the
                ; first content scanline ($4880) and, on each high-page advance while
                ; still in third 1 (high $49..$4F), resets low to 128 to SKIP the sky
                ; scanlines (r'=0..3, char rows 8..11) — third 2 (high>=$50) resumes
                ; at low 0 (all r'). 96 scanlines vs 192; correctness proven by the
                ; sky being blank (shift-invariant) so the omitted rows stay exact.
                ld   ix, BMP_C_START          ; $4880 = char row 12, top scanline
.scan:
                push ix
                pop  de                       ; DE = dest (col 0 of this scanline)
                ld   h, d
                ld   l, e
                inc  hl                       ; HL = source (col 1)
                DUP  31
                ldi                           ; col c+1 -> col c, 31 bytes
                EDUP
                ld   a, ixl
                add  a, 32                    ; next scanline (low += 32)
                ld   ixl, a
                jr   nc, .scan                ; no carry -> same high page
                ld   a, ixh
                inc  a                        ; low wrapped -> next high page
                ld   ixh, a
                cp   SCREEN_ATTR >> 8         ; $58: past bitmap -> done
                ret  nc
                cp   BMP_T2_HIGH              ; $50: reached third 2 (rows 16..23)?
                jr   nc, .scan                ;   yes -> keep low 0, walk all r'
                ld   a, 128                   ;   no  -> still third 1: skip sky
                ld   ixl, a                   ;          r'0..3, resume at r'4
                jr   .scan
    ELSE
                ld   ix, SCREEN_BITMAP        ; first scanline base (high $40,low 0)
.scan:
                push ix
                pop  de                       ; DE = dest (col 0 of this scanline)
                ld   h, d
                ld   l, e
                inc  hl                       ; HL = source (col 1)
                DUP  31
                ldi                           ; col c+1 -> col c, 31 bytes
                EDUP
                ld   a, ixl
                add  a, 32                    ; next scanline (low += 32)
                ld   ixl, a
                jr   nc, .scan                ; no carry -> same high page
                ld   a, ixh
                inc  a                        ; low wrapped -> next high page
                ld   ixh, a
                cp   SCREEN_ATTR >> 8         ; bitmap ends at $5800 (24 high pages)
                jr   c, .scan
                ret
    ENDIF

;==============================================================================
; shift_bitmap_right — mirror of shift_bitmap_left for westward scroll: move
; cols 0..30 -> 1..31 (col 0 left stale, redrawn). Unrolled LDD walks downward.
; Clobbers: A, BC, DE, HL, IX.
;==============================================================================
shift_bitmap_right:
    IF SHIFT_CONTENT_ROWS_ONLY
                ; SPIKE-3 mirror of shift_bitmap_left: content rows 12..23 only, LDD.
                ld   ix, BMP_C_START          ; $4880 = char row 12, top scanline
.scan:
                push ix
                pop  hl                       ; HL = base (col 0)
                ld   d, h
                ld   e, l
                ld   a, e
                add  a, VIEW_COLS - 1         ; DE = base+31 = dest (col 31)
                ld   e, a
                ld   a, l
                add  a, VIEW_COLS - 2         ; HL = base+30 = source (col 30)
                ld   l, a                     ; (low<=224, +31 <=255: no page cross)
                DUP  31
                ldd                           ; col c-1 -> col c, 31 bytes downward
                EDUP
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   nc, .scan
                ld   a, ixh
                inc  a
                ld   ixh, a
                cp   SCREEN_ATTR >> 8         ; $58: past bitmap -> done
                ret  nc
                cp   BMP_T2_HIGH              ; $50: reached third 2 (rows 16..23)?
                jr   nc, .scan                ;   yes -> keep low 0, walk all r'
                ld   a, 128                   ;   no  -> still third 1: skip sky
                ld   ixl, a
                jr   .scan
    ELSE
                ld   ix, SCREEN_BITMAP
.scan:
                push ix
                pop  hl                       ; HL = base (col 0)
                ld   d, h
                ld   e, l
                ld   a, e
                add  a, VIEW_COLS - 1         ; DE = base+31 = dest (col 31)
                ld   e, a
                ld   a, l
                add  a, VIEW_COLS - 2         ; HL = base+30 = source (col 30)
                ld   l, a                     ; (low<=224, +31 <=255: no page cross)
                DUP  31
                ldd                           ; col c-1 -> col c, 31 bytes downward
                EDUP
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   nc, .scan
                ld   a, ixh
                inc  a
                ld   ixh, a
                cp   SCREEN_ATTR >> 8
                jr   c, .scan
                ret
    ENDIF

;==============================================================================
; shift_attr_left — move the 24 attribute rows' cols 1..31 -> 0..30 (col 31 left
; stale, reset by set_newcol_attr). Same address-enumeration trick over the attr
; pages $58..$5A. For THIS scene the band attrs are scroll-invariant so the shift
; reproduces identical values — included so the reviewer measures the real attr
; pass the design §3.3 budgets and so the technique is proven general.
; Clobbers: A, BC, DE, HL, IX.
;==============================================================================
shift_attr_left:
    IF SHIFT_CONTENT_ROWS_ONLY
                ; SPIKE-3: shift only the 6 ground-band rows (18..23). Sky rows 0..17
                ; are a uniform ATTR_AIR band (features share the band attr) so their
                ; shift is a no-op — skipping them is byte-exact. Ground rows are
                ; contiguous ($5A40..$5AFF, one page) so no third-split is needed.
                ld   ix, ATTR_C_START         ; $5A40 = row 18 (first ground-band row)
    ELSE
                ld   ix, SCREEN_ATTR
    ENDIF
.scan:
                push ix
                pop  de
                ld   h, d
                ld   l, e
                inc  hl
                DUP  31
                ldi
                EDUP
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   nc, .scan
                ld   a, ixh
                inc  a
                ld   ixh, a
                cp   (SCREEN_ATTR + SCREEN_ATTR_LEN) >> 8   ; $5B (rows end $5AFF)
                jr   c, .scan
                ret

;==============================================================================
; shift_attr_right — mirror for westward scroll: attr cols 0..30 -> 1..31.
; Clobbers: A, BC, DE, HL, IX.
;==============================================================================
shift_attr_right:
    IF SHIFT_CONTENT_ROWS_ONLY
                ld   ix, ATTR_C_START         ; SPIKE-3: ground-band rows 18..23 only
    ELSE
                ld   ix, SCREEN_ATTR
    ENDIF
.scan:
                push ix
                pop  hl
                ld   d, h
                ld   e, l
                ld   a, e
                add  a, VIEW_COLS - 1
                ld   e, a
                ld   a, l
                add  a, VIEW_COLS - 2
                ld   l, a
                DUP  31
                ldd
                EDUP
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   nc, .scan
                ld   a, ixh
                inc  a
                ld   ixh, a
                cp   (SCREEN_ATTR + SCREEN_ATTR_LEN) >> 8
                jr   c, .scan
                ret

;==============================================================================
; draw_newcol_bitmap — redraw the 24 background cells of ONE screen column from
; WORLD_BUF at the current origin (world col = origin + C). Bitmap only; attrs
; owned by set_newcol_attr. Reuses the proven draw_bg_cell_bitmap path.
; In : C = screen col (0 or 31).   Clobbers: A, B, DE, HL  (C preserved)
;==============================================================================
draw_newcol_bitmap:
                ld   b, 0                     ; char row 0..23
.row:
                push bc
                call draw_bg_cell_bitmap      ; B=row, C=col (C preserved)
                pop  bc
                inc  b
                ld   a, b
                cp   VIEW_ROWS
                jr   nz, .row
                ret

;==============================================================================
; set_newcol_attr — write the band attribute (row<18 -> ATTR_AIR else
; ATTR_GROUND) into the 24 cells of ONE attribute column. Features share their
; band attr (pillar/doorway ink=cyan -> $05 = ATTR_AIR), so the band value is the
; correct attr for every cell of the exposed column.
; In : C = screen col.   Clobbers: A, B, DE, HL  (C preserved)
;==============================================================================
set_newcol_attr:
                ld   b, 0
.row:
                ld   a, b
                cp   GROUND_ROW
                ld   a, ATTR_AIR
                jr   c, .have
                ld   a, ATTR_GROUND
.have:
                ld   e, a                     ; E = attr (attr_addr clobbers A)
                call attr_addr                ; HL = attr(row B, col C); B,C,DE kept
                ld   (hl), e
                inc  b
                ld   a, b
                cp   VIEW_ROWS
                jr   nz, .row
                ret

;==============================================================================
; compute_sc — CUR_SC = (SPRITE_PX >> 3) - VIEW_ORIGIN_COL  (screen char col).
; Clobbers: A, HL
;==============================================================================
compute_sc:
                ld   hl, (SPRITE_PX)
                srl  h
                rr   l
                srl  h
                rr   l
                srl  h
                rr   l                        ; HL = PX>>3 (<=61, H=0)
                ld   a, l
                ld   hl, VIEW_ORIGIN_COL
                sub  (hl)
                ld   (CUR_SC), a
                ret

;==============================================================================
; ATTRIBUTE-FOLLOW (design §2.3). stamp_foot writes the same attr into the 3x3
; footprint (9 cells); restore (-> ATTR_AIR) and stamp (-> ATTR_SPRITE) reuse it.
; Branch-free: always 9 writes (stamping an empty cell is invisible since paper
; matches the band).  ~18 attr writes / motion frame.
; In : A = attr value, CUR_SC = left screen col.   Clobbers: A, B, DE, HL
;==============================================================================
stamp_foot:
                ld   e, a                     ; E = value (survives attr_addr)
                ld   a, (CUR_SC)
                ld   c, a                     ; C = col base (attr_addr preserves)
                ld   b, SPRITE_TOP_ROW
                ld   d, SPRITE_H_ROWS
.row:
                call attr_addr                ; HL = attr(row B, col C)
                ld   a, e
                ld   (hl), a
                inc  hl
                ld   (hl), a
                inc  hl
                ld   (hl), a                  ; 3 columns
                inc  b                        ; next char row
                dec  d
                jr   nz, .row
                ret

;==============================================================================
; attr_addr — SCREEN_ATTR + row*32 + col.
; In : B = row, C = col.   Out: HL.   Preserves B, C, DE.   Clobbers: A, HL
;==============================================================================
attr_addr:
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                   ; HL = row*32
                ld   a, l
                add  a, c
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:
                ld   a, h
                add  a, SCREEN_ATTR >> 8      ; +$58 (attr low byte is 0)
                ld   h, a
                ret

;==============================================================================
; erase_foot — redraw the 3x3 footprint's background tiles (bitmap only) from the
; world buffer, erasing the sprite with no trails (design §1.6). 9 draw_cell.
; In : CUR_SC.   Clobbers: A, BC, DE, HL
;==============================================================================
erase_foot:
                ld   e, SPRITE_H_ROWS         ; E = remaining rows
                ld   b, SPRITE_TOP_ROW        ; B = char row
.row:
                push bc                       ; save row across the col loop
                push de                       ; save row-count
                ld   a, (CUR_SC)
                ld   c, a                     ; C = col base
                ld   d, SPRITE_W_COLS
.col:
                push bc
                push de
                call draw_bg_cell_bitmap      ; B=row, C=col
                pop  de
                pop  bc
                inc  c
                dec  d
                jr   nz, .col
                pop  de
                pop  bc
                inc  b
                dec  e
                jr   nz, .row
                ret

;==============================================================================
; draw_bg_cell_bitmap — blit the background glyph at screen (row B, col C) for the
; current scroll origin. World col = VIEW_ORIGIN_COL + C. Bitmap only (attributes
; are owned by the band fill / footprint follow).
; In : B = char row, C = screen col.   Clobbers: A, B, DE, HL  (C preserved)
;==============================================================================
draw_bg_cell_bitmap:
                ld   a, (VIEW_ORIGIN_COL)
                add  a, c
                push bc                       ; save screen row+col
                ld   c, a                     ; C = world col
                call world_tile               ; A = tile id
                add  a, a
                add  a, a
                add  a, a                      ; tile*8 -> glyph offset
                ld   l, a
                ld   h, 0
                ld   de, bg_tiles
                add  hl, de                    ; HL = glyph
                pop  bc                        ; B = row, C = screen col
                jp   draw_cell                 ; tail blit

;==============================================================================
; world_tile — WORLD_BUF[row*64 + col].
; In : B = row, C = world col.   Out: A = tile id.   Preserves B,C. Clobbers DE,HL
;==============================================================================
world_tile:
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                   ; HL = row*64
                ld   a, l
                add  a, c
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:
                ld   de, WORLD_BUF
                add  hl, de
                ld   a, (hl)
                ret

;==============================================================================
; redraw_view — blit all 32x24 visible background cells (bitmap) from the world
; buffer at the current origin. Per-scroll-step cost (reviewer measures, CYAN).
; Clobbers: A, BC, DE, HL
;==============================================================================
redraw_view:
                ld   b, 0
.row:
                ld   c, 0
.col:
                push bc
                call draw_bg_cell_bitmap
                pop  bc
                inc  c
                ld   a, c
                cp   VIEW_COLS
                jr   nz, .col
                inc  b
                ld   a, b
                cp   VIEW_ROWS
                jr   nz, .row
                ret

;==============================================================================
; fill_bands — colour the backdrop: rows 0..17 -> ATTR_AIR, rows 18..23 ->
; ATTR_GROUND (design §2.2). Self-propagating LDIR fills.   Clobbers: A,BC,DE,HL
;==============================================================================
fill_bands:
                ld   hl, SCREEN_ATTR
                ld   (hl), ATTR_AIR
                ld   de, SCREEN_ATTR + 1
                ld   bc, GROUND_ROW * 32 - 1
                ldir
                ld   hl, SCREEN_ATTR + GROUND_ROW * 32
                ld   (hl), ATTR_GROUND
                ld   de, SCREEN_ATTR + GROUND_ROW * 32 + 1
                ld   bc, (VIEW_ROWS - GROUND_ROW) * 32 - 1
                ldir
                ret

;==============================================================================
; MASKED SPRITE BLIT (design §1.2). blit_current_sprite picks the pre-shift by
; SPRITE_PX AND 7, then composites 3 char rows of (screen AND mask) OR data.
;==============================================================================

;==============================================================================
; blit_current_sprite — entry = PRESHIFT_TABLE + (SPRITE_PX AND 7)*144; blit it.
; Clobbers: A, BC, DE, HL
;==============================================================================
blit_current_sprite:
                ld   a, (SPRITE_PX)           ; low byte
                and  7                        ; pre-shift index
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                   ; HL = idx*16
                ld   d, h
                ld   e, l                     ; DE = idx*16
                add  hl, hl
                add  hl, hl
                add  hl, hl                   ; HL = idx*128
                add  hl, de                   ; idx*144
                ld   de, PRESHIFT_TABLE
                add  hl, de
                ex   de, hl                   ; DE = pre-shift frame ptr
                ; fall through

;==============================================================================
; blit_sprite — composite a 144-byte pre-shift frame across 3 char rows at CUR_SC.
; In : DE = frame ptr (row-major [m0,d0,m1,d1,m2,d2]), CUR_SC = left screen col.
; Clobbers: A, BC, HL  (DE walks the frame to the end)
;==============================================================================
blit_sprite:
                ld   a, (CUR_SC)
                ld   c, a
                ld   b, SPRITE_TOP_ROW
                call scr_cell_addr
                call blit_8rows
                ld   a, (CUR_SC)
                ld   c, a
                ld   b, SPRITE_TOP_ROW + 1
                call scr_cell_addr
                call blit_8rows
                ld   a, (CUR_SC)
                ld   c, a
                ld   b, SPRITE_TOP_ROW + 2
                call scr_cell_addr
                jp   blit_8rows               ; tail

;==============================================================================
; scr_cell_addr — bitmap address of the TOP scanline of char cell (row B, col C).
; In : B = row, C = col.   Out: HL.   Preserves B, C, DE.   Clobbers: A, HL
;   high = $40 | (row & $18);  low = ((row & 7) << 5) | col
;==============================================================================
scr_cell_addr:
                ld   a, b
                and  $18
                or   $40
                ld   h, a
                ld   a, b
                and  7
                rrca
                rrca
                rrca                          ; (row & 7) << 5 (8-bit rotate)
                or   c
                ld   l, a
                ret

;==============================================================================
; blit_8rows — composite 8 scanlines x 3 byte-columns at HL: the hottest path.
;   per byte: (screen AND mask) OR data  — masked composite (design §1.2).
; In : HL = screen top-left, DE = frame ptr (8 rows of [m,d]x3).
; Out: DE advanced +48.   Clobbers: A, B, C, HL
;------------------------------------------------------------------------------
; The 3 columns sc..sc+2 never cross a char boundary (sprite clamped, sc+2<=31),
; so the next-scanline reposition is `dec l; dec l; inc h` (high+1, low back).
;==============================================================================
blit_8rows:
                ld   b, 8
.sl:
                ld   a, (de)                  ; col0 mask
                inc  de
                and  (hl)                     ; screen AND mask
                ld   c, a
                ld   a, (de)                  ; col0 data
                inc  de
                or   c
                ld   (hl), a
                inc  hl
                ld   a, (de)                  ; col1 mask
                inc  de
                and  (hl)
                ld   c, a
                ld   a, (de)                  ; col1 data
                inc  de
                or   c
                ld   (hl), a
                inc  hl
                ld   a, (de)                  ; col2 mask
                inc  de
                and  (hl)
                ld   c, a
                ld   a, (de)                  ; col2 data
                inc  de
                or   c
                ld   (hl), a                  ; (no inc: reposition below)
                dec  l
                dec  l
                inc  h                        ; next scanline (high+1, low base)
                djnz .sl
                ret

;==============================================================================
; BOOT-TIME PRE-SHIFT GENERATION (design §1.3). entry0 = the artist S=0 frame;
; entry s = entry s-1 shifted right 1 px (mask fed 1s/transparent, data fed 0s).
;==============================================================================
gen_preshifts:
                ld   hl, player               ; artist S=0 frame (144 B)
                ld   de, PRESHIFT_TABLE
                ld   bc, PRESHIFT_FRAME
                ldir                          ; entry 0 = unshifted source
                ld   b, PRESHIFT_COUNT - 1    ; generate entries 1..7
                ld   hl, PRESHIFT_TABLE       ; HL = previous entry
.gen:
                push bc
                ld   d, h
                ld   e, l
                ld   a, e
                add  a, PRESHIFT_FRAME        ; DE = prev + 144 = dst
                ld   e, a
                ld   a, d
                adc  a, 0
                ld   d, a
                ld   bc, PRESHIFT_FRAME
                ldir                          ; copy prev -> dst; HL now = dst start
                call shift_frame_right1       ; shift this entry in place (HL kept)
                pop  bc
                djnz .gen                     ; HL = dst = next iteration's prev
                ret

;==============================================================================
; shift_frame_right1 — shift a 144-byte frame right by 1 px in place. Per row the
; 3 mask bytes (offsets 0,2,4) ripple right feeding 1 (SCF); the 3 data bytes
; (offsets 1,3,5) ripple right feeding 0.
; In : HL = frame ptr.   Out: HL = frame ptr (preserved).   Clobbers: A, B, HL
;==============================================================================
shift_frame_right1:
                push hl
                ld   b, 24
.row:
                scf                           ; mask: feed 1 (transparent) at MSB
                rr   (hl)                     ; m0  (+0)
                inc  hl
                inc  hl
                rr   (hl)                     ; m1  (+2)
                inc  hl
                inc  hl
                rr   (hl)                     ; m2  (+4)
                dec  hl
                dec  hl
                dec  hl                       ; -> +1 (d0)
                or   a                        ; data: feed 0 at MSB
                rr   (hl)                     ; d0  (+1)
                inc  hl
                inc  hl
                rr   (hl)                     ; d1  (+3)
                inc  hl
                inc  hl
                rr   (hl)                     ; d2  (+5)
                inc  hl                       ; -> +6 (next row)
                djnz .row
                pop  hl
                ret

;==============================================================================
; build_world — author the 64x24 coloured side-view scene into WORLD_BUF:
;   floor line (row 18) + ground (19..23) full width; a trackable cyan pillar at
;   world col 28 (rows 12-17); decorative pillars 44/52 + a doorway at 36; the
;   rest blank sky. Gives visible scroll landmarks + a colour-follow demo.
; Clobbers: A, BC, DE, HL
;==============================================================================
build_world:
                ld   hl, WORLD_BUF
                ld   (hl), BG_BLANK
                ld   de, WORLD_BUF + 1
                ld   bc, WORLD_CELLS - 1
                ldir                          ; blank sky everywhere
                ld   hl, WORLD_BUF + GROUND_ROW * WORLD_COLS
                ld   b, WORLD_COLS
.floor:
                ld   (hl), BG_FLOOR           ; row 18 = floor line
                inc  hl
                djnz .floor
                ld   c, VIEW_ROWS - (GROUND_ROW + 1)   ; 5 ground rows
                ld   hl, WORLD_BUF + (GROUND_ROW + 1) * WORLD_COLS
.grow:
                ld   b, WORLD_COLS
.gcol:
                ld   (hl), BG_GROUND
                inc  hl
                djnz .gcol
                dec  c
                jr   nz, .grow
                ; features (col C, top row B, count D, tile E)
                ld   c, TRACK_COL
                ld   b, 12
                ld   d, 6
                ld   e, BG_PILLAR
                call vbar                     ; trackable pillar, rows 12-17
                ld   c, 44
                ld   b, 12
                ld   d, 6
                ld   e, BG_PILLAR
                call vbar
                ld   c, 52
                ld   b, 12
                ld   d, 6
                ld   e, BG_PILLAR
                call vbar
                ld   c, 36
                ld   b, 14
                ld   d, 4
                ld   e, BG_DOORWAY
                call vbar
                ret

;==============================================================================
; vbar — write tile E into WORLD_BUF column C for D rows starting at row B.
; In : B=top row, C=col, D=count, E=tile.   Clobbers: A, B, D, HL  (C,E kept)
;==============================================================================
vbar:
.l:
                push de
                push bc
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                   ; row*64
                ld   a, l
                add  a, c
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:
                ld   de, WORLD_BUF
                add  hl, de
                pop  bc
                pop  de
                ld   (hl), e                  ; tile
                inc  b
                dec  d
                jr   nz, .l
                ret

;==============================================================================
; --- Reused engine primitives, COPIED verbatim from src/main.asm so the spike
;     is a self-contained throwaway image (M2 factors a shared src/input.asm).
;     Same labels/semantics; same INPUT_SRC/KBD_MATRIX injection contract. ------
;==============================================================================

;------------------------------------------------------------------------------
; init_kbd_mirror — mirror = all released.
;------------------------------------------------------------------------------
init_kbd_mirror:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, KBD_RELEASED
.row:
                ld   (hl), a
                inc  hl
                djnz .row
                ret

;------------------------------------------------------------------------------
; scan_matrix — copy the 8 keyboard half-rows into KBD_MATRIX (skipped if test
; injection active, INPUT_SRC != 0).   Clobbers: A, BC, D, HL
;------------------------------------------------------------------------------
scan_matrix:
                ld   a, (INPUT_SRC)
                or   a
                ret  nz
                ld   hl, KBD_MATRIX
                ld   c, $FE
                ld   b, $FE
                ld   d, KBD_MATRIX_LEN
.row:
                in   a, (c)
                ld   (hl), a
                inc  hl
                rlc  b
                dec  d
                jr   nz, .row
                ret

;------------------------------------------------------------------------------
; sample_keys — held movement keys -> DIR_* bitset.   Clobbers: A, E
;------------------------------------------------------------------------------
sample_keys:
                ld   e, 0
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                bit  KB_L_BIT, a
                jr   nz, .nL
                set  DIR_E_BIT, e
.nL:
                bit  KB_K_BIT, a
                jr   nz, .nK
                set  DIR_N_BIT, e
.nK:
                bit  KB_J_BIT, a
                jr   nz, .nJ
                set  DIR_S_BIT, e
.nJ:
                bit  KB_H_BIT, a
                jr   nz, .nH
                set  DIR_W_BIT, e
.nH:
                ld   a, (KBD_MATRIX + KBROW_POIUY)
                bit  KB_P_BIT, a
                jr   nz, .nP
                set  DIR_E_BIT, e
.nP:
                bit  KB_O_BIT, a
                jr   nz, .nO
                set  DIR_W_BIT, e
.nO:
                ld   a, (KBD_MATRIX + KBROW_QWERT)
                bit  KB_Q_BIT, a
                jr   nz, .nQ
                set  DIR_N_BIT, e
.nQ:
                ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_A_BIT, a
                jr   nz, .nA
                set  DIR_S_BIT, e
.nA:
                ld   a, e
                ret

;------------------------------------------------------------------------------
; dirs_to_step — bitset -> signed (dx,dy); opposite keys cancel.
; Out: D=dx, E=dy; Z iff (0,0).   Clobbers: A, D, E
;------------------------------------------------------------------------------
dirs_to_step:
                ld   d, 0
                bit  DIR_E_BIT, a
                jr   z, .nE
                inc  d
.nE:
                bit  DIR_W_BIT, a
                jr   z, .nW
                dec  d
.nW:
                ld   e, 0
                bit  DIR_S_BIT, a
                jr   z, .nS
                inc  e
.nS:
                bit  DIR_N_BIT, a
                jr   z, .nN
                dec  e
.nN:
                ld   a, d
                or   e
                ret

;------------------------------------------------------------------------------
; clear_bitmap — blank the pixel bitmap.   Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
clear_bitmap:
                xor  a
                ld   hl, SCREEN_BITMAP
                ld   (hl), a
                ld   de, SCREEN_BITMAP + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ldir
                ret

;------------------------------------------------------------------------------
; draw_cell — blit one 8x8 glyph into char cell (row B, col C). Copied from P2.
; In : B=row, C=col, HL=glyph.   Clobbers: A, B, DE, HL  (preserves C, IX, IY)
;------------------------------------------------------------------------------
draw_cell:
                ld   a, b
                and  $18
                or   $40
                ld   d, a
                ld   a, b
                and  7
                rrca
                rrca
                rrca
                or   c
                ld   e, a
                ld   b, GLYPH_BYTES
.row:
                ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .row
                ret

spike_code_end:
SPIKE_CODE_LEN  EQU spike_code_end - spike_start

;==============================================================================
; Background + sprite asset data (artist-emitted; reused, not recreated).
;==============================================================================
                INCLUDE "../assets/gfx/bg_tiles.asm"
                INCLUDE "../assets/gfx/player.asm"

spike_data_end:
SPIKE_IMAGE_LEN EQU spike_data_end - spike_start

;==============================================================================
; Emit artefacts: an auto-running .tap + a snapshot (separate from wazhack.*).
;==============================================================================
                EMPTYTAP "build/spike.tap"
                SAVETAP  "build/spike.tap", BASIC, "spike", spk_loader, spk_loader_len, 10
                SAVETAP  "build/spike.tap", CODE,  "spike", spike_start, SPIKE_IMAGE_LEN
                SAVESNA  "build/spike.sna", spike_start

;------------------------------------------------------------------------------
; spk_loader — 10 CLEAR VAL "32767": RANDOMIZE USR VAL "32768"  (scratch ORG).
;------------------------------------------------------------------------------
                ORG  $E000
spk_loader:
                DB   0, 10
                DW   spk_line_end - spk_line_body
spk_line_body:
                DB   $FD
                DB   $B0, '"', "32767", '"'
                DB   ':'
                DB   $F9
                DB   $C0
                DB   $B0, '"', "32768", '"'
                DB   $0D
spk_line_end:
spk_loader_len  EQU  spk_line_end - spk_loader
