;==============================================================================
; spike_sideview.asm — SIDE-VIEW FEASIBILITY SPIKE (throwaway, risk-retirement).
;
; Target : ZX Spectrum 128K   Origin : $8000   Build: SEPARATE from main.asm.
; Assemble with:  sjasmplus src/spike_sideview.asm --fullpath \
;                          --lst=build/spike.lst --sld=build/spike.sld -i src
; Emits build/spike.tap (+ .sna) — does NOT touch build/wazhack.* (P3 stays green).
;
; SPIKE-5 (2026-08-10): the sprite path is now GEOMETRY-PARAMETERISED. Build flag
; USE_HERO_32X48 (default 0 = the committed 16x24 `player` scene the goldens were
; captured from; 1 = the design §1.1 32x48 `wizard_ai_test` hero) switches the
; pre-shift generator, footprint attr-follow, erase and masked blit together via
; SPRITE_TOP_ROW / SPRITE_H_ROWS / SPRITE_W_COLS / SPRITE_SRC_COLS. There is ONE
; body of code for both sizes (DUP-unrolled at assembly time), so the legacy path
; cannot rot. The hero build is:
;   sjasmplus src/spike_sideview.asm -DUSE_HERO_32X48=1 --fullpath \
;             --lst=build/spike_hero.lst -i src
; and it emits build/spike_hero.tap/.sna — a SEPARATE artefact, so it can never
; shadow the build/spike.* the regression tests assert against.
;
; SPIKE-6 (2026-08-10): WALK-CYCLE ANIMATION on the hero path. ANIM_COUNT artist
; frames (3 for the hero, 1 = no animation for the legacy asset), each with its
; own boot-generated 8-entry pre-shift table; the blit selects the active table by
; SMC (blit_ptr_base). The cycle advances every ANIM_PERIOD moving frames and snaps
; back to the neutral pose on the moving->idle edge. All animation code is inside
; `IF ANIM_COUNT > 1`, so the legacy 16x24 build renders exactly as before
; (tests/sideview.py golden sideview_start.hash unchanged, bit-identical).
;
; Proves (docs/design/sideview-renderer.md): a recognizable MASKED sprite
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
; ATTR_SPRITE is the LEGACY 16x24 sprite colour and is kept only as the documented
; expected value of the `player` asset's descriptor byte (tests/sideview.py asserts
; it). The renderer no longer hard-codes it: it reads the descriptor out of the
; asset at boot into SPRITE_ATTR (design §1.7), so swapping the sprite file swaps
; the colour. wizard_ai_test's descriptor is $45 (bright cyan on black).
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

; SPIKE-5 build flag — HERO SPRITE SIZE. Selects which artist frame the whole
; sprite path (pre-shift gen, footprint attr-follow, erase, masked blit) is built
; for. Both paths are the SAME code, parameterised by the geometry EQUs below;
; nothing is duplicated, so the 16x24 path cannot rot.
;   0 (default) = LEGACY 16x24 `player` (2 data cols + 1 artist pad col = 3 cols
;                 x 24 rows = 144 B/frame). This is the committed spike scene the
;                 goldens in tests/golden/sideview_start.hash were captured from —
;                 keeping it the default keeps tests/sideview.py + scroll.py green.
;   1           = HERO 32x48 `wizard_ai_test`, the design §1.1/§1.4 contract: the
;                 artist emits 4 data cols x 48 rows = 384 B (+1 descriptor) and
;                 the engine BOOT-GENs the 5th (spill) column, so the in-RAM
;                 pre-shift frame is 5 cols x 48 rows = 480 B (design §1.3).
; Override from the command line (no source edit):
;   sjasmplus src/spike_sideview.asm -DUSE_HERO_32X48=1 ...
    IFNDEF USE_HERO_32X48
USE_HERO_32X48  EQU 0
    ENDIF

; Sprite geometry (design §1.1/§1.4/§1.5). SPRITE_W_COLS is the BLIT/footprint
; span in char cols = the in-RAM pre-shift width; SPRITE_SRC_COLS is what the
; artist file actually contains. They differ only for the hero, where the engine
; appends the transparent spill column at boot (design §1.3).
    IF USE_HERO_32X48
SPRITE_TOP_ROW  EQU 12              ; 6 char rows 12..17, feet on the ground band
SPRITE_H_ROWS   EQU 6
SPRITE_W_COLS   EQU 5               ; 4 data cols + 1 boot-generated spill col
SPRITE_SRC_COLS EQU 4               ; artist frame: 8 B/row, no pad column
    ELSE
SPRITE_TOP_ROW  EQU 15              ; 3 char rows 15..17
SPRITE_H_ROWS   EQU 3
SPRITE_W_COLS   EQU 3               ; 2 data cols + the artist's pad col
SPRITE_SRC_COLS EQU 3               ; artist frame already carries the pad col
    ENDIF
SPRITE_ROWS_PX  EQU SPRITE_H_ROWS * 8        ; 24 / 48 scanlines
SPRITE_PY_VAL   EQU SPRITE_TOP_ROW * 8       ; char-aligned, no Y pre-shift
SPRITE_SRC_FRAME EQU SPRITE_ROWS_PX * SPRITE_SRC_COLS * 2  ; 144 / 384 B on tape

; Dead-zone follow (design §3.2): sprite (left col) clamped to cols 12..18.
DEAD_L          EQU 12
DEAD_R          EQU 18
ORIGIN_MAX      EQU WORLD_COLS - VIEW_COLS    ; 32
SPRITE_PX_INIT  EQU 120             ; world px -> sc=15 at origin 0 (centre)
; Right-edge clamp: keeps the sprite's RIGHTMOST blit col <= 31 at origin max.
;   16x24 -> 488 (sc 29, cols 29..31);  32x48 -> 472 (sc 27, cols 27..31).
SPRITE_PX_MAX   EQU (ORIGIN_MAX + VIEW_COLS - SPRITE_W_COLS) * 8
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

; SPIKE-4 build flag (shadow-screen double-buffer). Erase the residual 1-in-4
; ~1.34-frame scroll burst SPIKE-3 left by SPREADING the scroll work across the
; 4-frame inter-scroll window into a HIDDEN back buffer (bank 7), then revealing
; it with an atomic $7FFD bit-3 flip. A plain flip only hides tearing; the spread
; is what keeps every frame sub-frame.
;   1 (default) = double-buffer: front = displayed buffer, back = hidden buffer;
;                 the scroll is a cross-buffer byte-shift-COPY (bank5<->bank7, both
;                 mapped simultaneously) spread over 4 frames + atomic flip. Uses
;                 a camera-lock follow (scroll 1 col / 4 moving frames) — a
;                 deliberate spike simplification of SPIKE-3's dead-zone follow, so
;                 the 4-frame prep aligns naturally with the 8px byte boundary.
;   0           = SPIKE-3 single-buffer path (dead-zone follow + in-place byte-
;                 shift scroll) for A/B. All render still targets bank 5 only.
USE_SHADOW_DOUBLEBUFFER EQU 1

; --- 128K paging ($7FFD) for the double buffer -------------------------------
; bits0-2 = bank at $C000 (kept = 7 always: bank 7 is the shadow screen, drawn as
;           the back buffer via the $C000 window regardless of what ULA displays).
; bit3    = display select (0 = bank 5 @ $4000, 1 = bank 7). The ONLY bit we flip.
; bit4    = ROM select — MUST stay 1 (48K ROM, $10): its IM1 ISR at $0038 is the
;           simple keyboard/FRAMES handler the `halt` frame-sync relies on. The
;           128K editor ROM (bit4=0) has a complex $0038 handler that derails the
;           loop on the first interrupt.
; bit6    = paging-disable — MUST stay 0.
P7FFD_BANK7     EQU 7                 ; bits0-2 = 7 -> bank 7 paged at $C000
P7FFD_SCR7      EQU %00001000         ; bit3 = 1 -> display bank 7
P7FFD_BASE      EQU P7FFD_BANK7 | %00010000  ; boot: bank7@$C000, display bank5, 48K ROM

; Bank-7 screen (the $C000 window). Bitmap $C000, attrs $D800. The whole screen
; is +$8000 from the bank-5 window ($4000/$5800), so the render base is one added
; high-byte offset of $80 (front hi | $80). Named so no magic addresses appear.
BACK_BMP_BASE   EQU $C000
BACK_ATTR_BASE  EQU $D800
BANK_HI_OFF     EQU (BACK_BMP_BASE - SCREEN_BITMAP) >> 8   ; $80

; Content-shift geometry (derived, no magic addresses). Bitmap content begins at
; char row 12 whose top scanline address is $4880 (high $40|(row&$18)=$48, low
; (row&7)<<5=$80). The ZX third boundary at char row 16 (pixel 128) is bitmap high
; $50, where the enumeration crosses from third 1 (rows 12-15, r'>=4) into third 2
; (rows 16-23, all r'). Ground-band attrs start at $5A40 (= SCREEN_ATTR+18*32).
CONTENT_TOP_ROW EQU 12
BMP_C_START     EQU SCREEN_BITMAP + ((CONTENT_TOP_ROW & $18) << 8) + ((CONTENT_TOP_ROW & 7) << 5) ; $4880
BMP_T2_HIGH     EQU SCREEN_BITMAP >> 8 | (16 & $18)   ; $50: bitmap high byte of third 2 (row 16)
ATTR_C_START    EQU SCREEN_ATTR + GROUND_ROW * 32     ; $5A40: first ground-band attr row

; Pre-shift table (design §1.3): 8 copies of the blit-width frame, boot-generated.
;   16x24: 24 rows x 3 cols x 2 =  144 B/frame -> 1152 B per ANIM frame
;   32x48: 48 rows x 5 cols x 2 =  480 B/frame -> 3840 B per ANIM frame
PRESHIFT_FRAME  EQU SPRITE_ROWS_PX * SPRITE_W_COLS * 2
PRESHIFT_COUNT  EQU 8
PRESHIFT_SIZE   EQU PRESHIFT_FRAME * PRESHIFT_COUNT

; SPIKE-6 — WALK-CYCLE ANIMATION (hero path only).
; ANIM_COUNT artist frames, each with its OWN full 8-entry pre-shift table.
;   16x24 legacy : 1 frame  (no animation; byte-identical to the pre-SPIKE-6 path)
;   32x48 hero   : 3 frames (wizard_ai_test_f0/f1/f2), cycled while moving.
; ANIM_PERIOD = moving frames between advances. 50 Hz / 6 = 8.33 walk steps/s,
; i.e. a full 3-frame cycle every 18 frames (~0.36 s) — reads as a walk, and 6 is
; a cheap `cp` constant with no division anywhere on the path.
    IF USE_HERO_32X48
ANIM_COUNT      EQU 3
    ELSE
ANIM_COUNT      EQU 1
    ENDIF
ANIM_PERIOD     EQU 6
ANIM_FRAME_BYTES EQU SPRITE_SRC_FRAME + 1   ; artist frame + colour descriptor

;------------------------------------------------------------------------------
; Spike RAM (docs/memory-map.md "Side-view spike"). Buffers sit below the entity
; region; the test-observable bytes sit ABOVE the initial SP ($BF00) alongside
; the existing INPUT_SRC/KBD_MATRIX mirror (stack grows down, never reaches them).
;------------------------------------------------------------------------------
    IF USE_HERO_32X48
; --- SPIKE-6 pre-shift memory TRADEOFF (hero, 3 walk frames) -----------------
; 3 anim frames x 8 pre-shifts x 480 B = 11,520 B. That does NOT fit in one run
; between the image top (~$8D50) and WORLD_BUF ($A500) — only ~6.1 KB is free
; there. Options considered:
;   (a) FIND THE ROOM  <- CHOSEN. Three 3840-B tables placed in the two free
;       runs that DO exist: the "$5CCB..$7FFF free RAM" region (memory-map) at
;       $6000/$7000, and the run above the image at $9000. Costs zero cycles on
;       the hot path: a frame change is one SMC pointer patch (set_anim_frame).
;       Safe because the BASIC loader does CLEAR 32767 (RAMTOP $7FFF) and
;       spike_start immediately does `di` + `ld sp,WORKSTORE_TOP` and never
;       returns to BASIC, so BASIC's area/stack below $7FFF is dead from boot.
;       Boot cost: 3 x gen_preshifts (~360k T, ~5 frames) — boot only.
;   (b) Regenerate the active frame's 8 pre-shifts on every frame CHANGE:
;       ~120k T (7 x 480-B LDIR + 7 x shift_frame_right1) = ~1.7 FRAMES of hitch
;       every 6th moving frame. Rejected — it turns a smooth walk into a stutter.
;   (c) Keep only the 4 EVEN pre-shifts (SPRITE_PX is provably even: init 120,
;       MOVE_STEP 2, clamps 0/472) -> 5760 B, fits in one run. Rejected as a
;       correctness landmine: it silently breaks if MOVE_STEP ever becomes odd.
; The tables are NOT contiguous, so blit indexing goes through a per-anim-frame
; 8-word pointer table (preshift_ptrs_fN) selected by SMC, not by arithmetic.
PRESHIFT_TABLE  EQU $6000           ; anim frame 0: 3840 B  $6000..$6EFF
PRESHIFT_TABLE1 EQU $7000           ; anim frame 1: 3840 B  $7000..$7EFF
PRESHIFT_TABLE2 EQU $9400           ; anim frame 2: 3840 B  $9400..$A2FF
                                    ; (f2 sits above the image — $9400 not $9000
                                    ; to leave ~1.6 KB of image growth headroom;
                                    ; both ends ASSERTed below)
    ELSE
PRESHIFT_TABLE  EQU $A000           ; 1152 B  $A000..$A47F (boot-generated)
    ENDIF
WORLD_BUF       EQU $A500           ; 1536 B  $A500..$AAFF (64x24 tile ids)

CUR_SC          EQU $BF10           ; byte: current sprite screen col (scratch)
CUR_DX          EQU $BF11           ; byte: this frame's dx (-1/0/+1)
SPRITE_PX       EQU $BF12           ; word: player WORLD pixel X (test-observable)
SPRITE_PY       EQU $BF14           ; byte: sprite top pixel Y (constant)
VIEW_ORIGIN_COL EQU $BF15           ; byte: world col shown at screen col 0 (t-o)
FRAME_COUNTER   EQU $BF16           ; word: per-frame liveness counter (t-o)

; SPIKE-4 double-buffer state (all above the initial SP $BF00; stack grows down).
PORT_7FFD_SHADOW EQU $BF18          ; byte: last value written to $7FFD (WO port);
                                    ;       RMW ONLY via this shadow (t-observable)
PREP_PHASE      EQU $BF19           ; byte: back-prep phase 0..3 within a scroll
                                    ;       cycle (increments per moving+scrolling
                                    ;       frame; flip when it wraps 3->0)
PREP_DIR        EQU $BF1A           ; byte: cycle scroll direction (+1 east/-1 west);
                                    ;       phase resets if dx flips
PREP_SRC        EQU $BF1B           ; word: front bitmap scanline addr for the next
                                    ;       shift-copy chunk (walk state saved here)
SPRITE_ATTR     EQU $BF1D           ; byte: the sprite's colour DESCRIPTOR (design
                                    ;       §1.7), copied at boot from the artist
                                    ;       frame's trailing byte. $46 (16x24
                                    ;       player) / $45 (32x48 wizard_ai_test).
                                    ;       test-observable.
ANIM_FRAME      EQU $BF1E           ; SPIKE-6, test-observable: current walk-cycle
                                    ;       frame index 0..ANIM_COUNT-1. 0 = the
                                    ;       neutral/idle pose.
ANIM_TICK       EQU $BF1F           ; SPIKE-6: moving frames since the last advance
                                    ;       (0..ANIM_PERIOD-1)

                ORG $8000

;==============================================================================
; spike_start — boot: state, pre-shifts, world, first full render, then loop.
;==============================================================================
spike_start:
                di
                ld   sp, WORKSTORE_TOP        ; reuse main's SP slot ($BF00)
                ld   iy, IY_SYSVAR            ; ROM ISR invariant (HALT/keyboard)

                ; PORT_7FFD_SHADOW seeded so the display-buffer read (bit3) is
                ; valid even in the flag=0 single-buffer build (bit3=0 -> bank5).
                ld   a, P7FFD_BASE            ; bit3=0: boot displays bank5
                ld   (PORT_7FFD_SHADOW), a
    IF USE_SHADOW_DOUBLEBUFFER
                ld   bc, PORT_7FFD            ; page bank 7 @ $C000 (bit4/6 = 0:
                out  (c), a                  ;   keep 128K ROM + paging enabled)
                xor  a
                ld   (PREP_PHASE), a
                ld   (PREP_DIR), a
    ENDIF

                ld   hl, SPRITE_PX_INIT
                ld   (SPRITE_PX), hl
                ld   a, SPRITE_PY_VAL
                ld   (SPRITE_PY), a
                xor  a
                ld   (VIEW_ORIGIN_COL), a
                ld   (INPUT_SRC), a           ; default: scan real keyboard
                ld   hl, 0
                ld   (FRAME_COUNTER), hl

                ; Sprite colour comes from the ASSET, not a hard-coded EQU: the
                ; descriptor byte the converter appends after the frame (design
                ; §1.7). Its address is frame + SPRITE_SRC_FRAME by contract.
                ld   a, (sprite_frame + SPRITE_SRC_FRAME)
                ld   (SPRITE_ATTR), a

                ; SPIKE-6: walk cycle starts on the neutral pose, tick reset.
                xor  a
                ld   (ANIM_FRAME), a
                ld   (ANIM_TICK), a
                call set_anim_frame           ; point the blit at frame 0's table

                call init_kbd_mirror
                ; One 8-entry pre-shift table PER anim frame (design §1.3). Boot
                ; only: ~120k T each, so ~5 frames of boot for the 3-frame hero.
                ld   hl, sprite_frame
                ld   de, PRESHIFT_TABLE
                call gen_preshifts
    IF ANIM_COUNT > 1
                ld   hl, sprite_frame + ANIM_FRAME_BYTES
                ld   de, PRESHIFT_TABLE1
                call gen_preshifts
                ld   hl, sprite_frame + 2 * ANIM_FRAME_BYTES
                ld   de, PRESHIFT_TABLE2
                call gen_preshifts
    ENDIF
                call build_world              ; 64x24 coloured side-view scene

                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                call clear_bitmap
                call fill_bands               ; air rows -> $05, ground rows -> $4F
                call redraw_view              ; blit the 32 visible cols (bitmap)
                call compute_sc               ; CUR_SC = initial screen col
                call stamp_sprite_colour      ; colour the footprint
                call blit_current_sprite      ; composite the masked sprite
    IF USE_SHADOW_DOUBLEBUFFER
                call init_back_buffer         ; render an identical frame into bank7
                                              ; so the FIRST flip reveals a valid
                                              ; complete frame; leaves target=bank5
    ENDIF
                ei                            ; ROM IM1 ISR on (HALT pacing)

;==============================================================================
; spike_loop — per-frame: sample held keys, and only if moving do the full
; erase->move/scroll->stamp->blit. Idle frames leave the screen untouched so the
; single-buffer image is stable at rest (deterministic goldens/assertions).
;==============================================================================
spike_loop:
    IF USE_SHADOW_DOUBLEBUFFER
                jp   spike_loop_dbuf          ; SPIKE-4 double-buffer path
    ENDIF
                call read_dx                  ; D = dx (-1/0/+1)
                ld   a, d
                ld   (CUR_DX), a
                or   a
                jp   z, .idlestop             ; not moving -> skip render

                call anim_advance             ; SPIKE-6: cycle the walk frame

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
                call stamp_sprite_colour      ; footprint -> asset descriptor
                call blit_current_sprite
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                jr   .idle
.idlestop:
                call anim_idle                ; SPIKE-6: settle onto the neutral pose
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
; ATTRIBUTE-FOLLOW (design §2.3). stamp_foot writes the same attr into the whole
; SPRITE_W_COLS x SPRITE_H_ROWS footprint; restore (-> ATTR_AIR) and stamp
; (-> the asset descriptor) reuse it. Branch-free: always the full rectangle
; (stamping an empty cell is invisible since paper matches the band).
;   16x24: 3x3 =  9 cells -> 18 attr writes / motion frame
;   32x48: 5x6 = 30 cells -> 60 attr writes / motion frame (design §2.3 budget)
; stamp_sprite_colour is the same routine with A pre-loaded from the descriptor.
; In : A = attr value, CUR_SC = left screen col.   Clobbers: A, B, DE, HL
;==============================================================================
stamp_sprite_colour:
                ld   a, (SPRITE_ATTR)         ; asset descriptor (design §1.7)
                ; fall through
stamp_foot:
                ld   e, a                     ; E = value (survives attr_addr)
                ld   a, (CUR_SC)
                ld   c, a                     ; C = col base (attr_addr preserves)
                ld   b, SPRITE_TOP_ROW
                ld   d, SPRITE_H_ROWS
.row:
                call attr_addr                ; HL = attr(row B, col C)
                ld   a, e
                ; Unrolled by SPRITE_W_COLS at assembly time: identical bytes to
                ; the old hand-unrolled 3-col loop, so the legacy path is unchanged.
                DUP  SPRITE_W_COLS - 1
                ld   (hl), a
                inc  hl
                EDUP
                ld   (hl), a                  ; last column (no step needed)
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
attr_base_add:
                add  a, SCREEN_ATTR >> 8      ; SMC: attr base hi ($58 bank5 /
                                              ;      $D8 bank7); patched by
                                              ;      set_target_* (attr_base_add+1)
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
; SPRITE_PX AND 7, then composites SPRITE_H_ROWS char rows of
; (screen AND mask) OR data.
;==============================================================================

;==============================================================================
; blit_current_sprite — entry = preshift_ptrs[SPRITE_PX AND 7]; blit it.
; A table lookup rather than an idx*PRESHIFT_FRAME multiply: 144 and 480 need
; different shift-add chains, and the 16-byte table is both smaller and ~40 T
; cheaper than either. Table entries are assemble-time constants.
; Clobbers: A, BC, DE, HL
;==============================================================================
blit_current_sprite:
                ld   a, (SPRITE_PX)           ; low byte
                and  7                        ; pre-shift index
                add  a, a                     ; *2 (word entries)
                ld   l, a
                ld   h, 0
blit_ptr_base:
                ld   de, preshift_ptrs_f0     ; SMC: the CURRENT anim frame's 8-word
                                              ;      pre-shift pointer table; patched
                                              ;      by set_anim_frame (blit_ptr_base+1).
                                              ;      SMC (not idx arithmetic) because
                                              ;      the 3 hero tables are NOT contiguous
                                              ;      in RAM — and it costs 0 T here.
                add  hl, de
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                  ; DE = pre-shift frame ptr
                ; fall through

;==============================================================================
; blit_sprite — composite one pre-shift frame across SPRITE_H_ROWS char rows at
; CUR_SC. Row-looped rather than unrolled: ~40 T/row of loop overhead against
; ~2k T/row of blit_8rows work (<2%), and it serves 3 and 6 rows from one body.
; In : DE = frame ptr (row-major [m,d] x SPRITE_W_COLS), CUR_SC = left screen col.
; Clobbers: A, BC, HL  (DE walks the frame to the end)
;==============================================================================
blit_sprite:
                ld   b, SPRITE_TOP_ROW
.row:
                ld   a, (CUR_SC)
                ld   c, a
                push bc                       ; blit_8rows clobbers B and C
                call scr_cell_addr            ; HL = top scanline of (B,C)
                call blit_8rows               ; DE += 8 * SPRITE_W_COLS * 2
                pop  bc
                inc  b
                ld   a, b
                cp   SPRITE_TOP_ROW + SPRITE_H_ROWS
                jr   nz, .row
                ret

;==============================================================================
; scr_cell_addr — bitmap address of the TOP scanline of char cell (row B, col C).
; In : B = row, C = col.   Out: HL.   Preserves B, C, DE.   Clobbers: A, HL
;   high = $40 | (row & $18);  low = ((row & 7) << 5) | col
;==============================================================================
scr_cell_addr:
                ld   a, b
                and  $18
scell_bmp_or:
                or   $40                      ; SMC: bitmap base hi (dcell twin;
                                              ;      scell_bmp_or+1)
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
; blit_8rows — composite 8 scanlines x SPRITE_W_COLS byte-columns at HL: the
; hottest path.  per byte: (screen AND mask) OR data — masked composite (§1.2).
; In : HL = screen top-left, DE = frame ptr (8 rows of [m,d] x SPRITE_W_COLS).
; Out: DE advanced +8*SPRITE_W_COLS*2 (48 / 80).   Clobbers: A, B, C, HL
;------------------------------------------------------------------------------
; The columns sc..sc+W-1 never cross a 256-byte boundary (the sprite is clamped
; so sc+W-1 <= 31 and a scanline's 32 bytes are contiguous), so the next-scanline
; reposition is just `l -= W-1; h += 1`. `dec l` x (W-1) costs 4 T each and is
; unrolled at assembly time — for the legacy 3-col build this emits exactly the
; previous `dec l; dec l; inc h`.
;==============================================================================
blit_8rows:
                ld   b, 8
.sl:
                DUP  SPRITE_W_COLS - 1
                ld   a, (de)                  ; col mask
                inc  de
                and  (hl)                     ; screen AND mask
                ld   c, a
                ld   a, (de)                  ; col data
                inc  de
                or   c
                ld   (hl), a
                inc  hl                       ; next byte-column
                EDUP
                ld   a, (de)                  ; last col mask
                inc  de
                and  (hl)
                ld   c, a
                ld   a, (de)                  ; last col data
                inc  de
                or   c
                ld   (hl), a                  ; (no inc: reposition below)
                DUP  SPRITE_W_COLS - 1
                dec  l
                EDUP
                inc  h                        ; next scanline (high+1, low base)
                djnz .sl
                ret

;==============================================================================
; BOOT-TIME PRE-SHIFT GENERATION (design §1.3). entry0 = the artist S=0 frame;
; entry s = entry s-1 shifted right 1 px (mask fed 1s/transparent, data fed 0s).
;==============================================================================
; In : HL = artist S=0 frame, DE = destination table base (PRESHIFT_SIZE bytes).
; Clobbers: A, BC, DE, HL.   Boot only (~120k T per anim frame).
gen_preshifts:
                push de                       ; keep the table base for the shift pass
                ; --- entry 0 = the artist S=0 frame, WIDENED to the blit width --
                ; The 32x48 contract (design §1.3/§1.4) ships 4 data columns and
                ; makes the ENGINE add the 5th "spill" column that shifts 1..7 need;
                ; it is all-transparent at S=0 (mask $FF / data $00). For the 16x24
                ; asset the artist already ships its pad column, so SPRITE_W_COLS ==
                ; SPRITE_SRC_COLS and the IF below emits nothing — a plain copy.
                ld   b, SPRITE_ROWS_PX        ; 24 / 48 rows
.widen:
                push bc
                ld   bc, SPRITE_SRC_COLS * 2
                ldir                          ; the artist's bytes for this row
    IF SPRITE_W_COLS > SPRITE_SRC_COLS
                ld   a, $FF
                ld   (de), a                  ; spill col mask = fully transparent
                inc  de
                xor  a
                ld   (de), a                  ; spill col data = empty
                inc  de
    ENDIF
                pop  bc
                djnz .widen

                pop  hl                       ; HL = table base = entry 0 (prev)
                ld   b, PRESHIFT_COUNT - 1    ; generate entries 1..7
.gen:
                push bc
                push hl                       ; save src (prev entry)
                ld   de, PRESHIFT_FRAME       ; 16-bit: PRESHIFT_FRAME is 480 for
                add  hl, de                   ; the hero, so no 8-bit add here
                ex   de, hl                   ; DE = dst = prev + frame
                pop  hl                       ; HL = src
                ld   bc, PRESHIFT_FRAME
                ldir                          ; copy prev -> dst; HL now = dst start
                call shift_frame_right1       ; shift this entry in place (HL kept)
                pop  bc
                djnz .gen                     ; HL = dst = next iteration's prev
                ret

;==============================================================================
; preshift_ptrs_fN — entry pointers for blit_current_sprite (assemble-time
; constants). Stride is PRESHIFT_FRAME; entry s = the frame shifted right s px.
; One table per ANIM frame; blit_ptr_base's SMC operand selects which.
;==============================================================================
preshift_ptrs_f0:
                DW   PRESHIFT_TABLE + 0 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 1 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 2 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 3 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 4 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 5 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 6 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE + 7 * PRESHIFT_FRAME
    IF ANIM_COUNT > 1
preshift_ptrs_f1:
                DW   PRESHIFT_TABLE1 + 0 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 1 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 2 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 3 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 4 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 5 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 6 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE1 + 7 * PRESHIFT_FRAME
preshift_ptrs_f2:
                DW   PRESHIFT_TABLE2 + 0 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 1 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 2 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 3 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 4 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 5 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 6 * PRESHIFT_FRAME
                DW   PRESHIFT_TABLE2 + 7 * PRESHIFT_FRAME

; anim_frame_tabs[i] = the pre-shift pointer table of anim frame i (2 B stride).
anim_frame_tabs:
                DW   preshift_ptrs_f0
                DW   preshift_ptrs_f1
                DW   preshift_ptrs_f2
    ENDIF

;==============================================================================
; SPIKE-6 — WALK-CYCLE ANIMATION (design: no prior spec; pattern established here)
;
; Model: the walk cycle is driven by MOVING FRAMES, not by world X, because the
; existing loops already gate everything on `dx != 0` (spike_loop / spike_loop_dbuf
; jump straight to .idle when dx == 0), and dx != 0 is exactly "the sprite's world
; X is advancing" — except at the world clamps, where the pose keeps cycling as a
; walk-on-the-spot. That is the cheapest correct hook and needs no extra state.
;
;   moving : ANIM_TICK++; every ANIM_PERIOD (6) frames advance ANIM_FRAME 0->1->2->0
;            (~8.3 steps/s at 50 Hz; a full cycle every ~0.36 s).
;   idle   : snap back to ANIM_FRAME 0 (neutral pose) and, ONCE on the moving->idle
;            edge, repaint the sprite so the screen matches the state (idle frames
;            are otherwise not rendered at all — see the loop header). Steady-state
;            idle touches nothing, so the at-rest goldens stay deterministic.
;
; Colour is NOT animated: all three artist frames carry the same $45 descriptor
; (ASSERTed at assembly time below), so SPRITE_ATTR is read once at boot and the
; footprint stamp is frame-independent — no colour flicker across the cycle.
;==============================================================================

;------------------------------------------------------------------------------
; set_anim_frame — point blit_current_sprite at anim frame A's pre-shift table.
; In : A = frame index (0..ANIM_COUNT-1).   Clobbers: A, DE, HL
; Cost: ~60 T, paid once per frame CHANGE (1-in-6 moving frames), never per blit.
;------------------------------------------------------------------------------
set_anim_frame:
    IF ANIM_COUNT > 1
                add  a, a                     ; *2 (word entries)
                ld   l, a
                ld   h, 0
                ld   de, anim_frame_tabs
                add  hl, de
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                ld   (blit_ptr_base + 1), de  ; SMC: swap the pre-shift ptr table
    ENDIF
                ret

;------------------------------------------------------------------------------
; anim_advance — one MOVING frame of the walk cycle. Call before any blit.
; Clobbers: A, DE, HL   (must NOT disturb CUR_DX/SPRITE_PX — it does not)
; Cost: 5 frames in 6 -> ~40 T (inc + cp + ret c); the 6th -> ~120 T.
;------------------------------------------------------------------------------
anim_advance:
    IF ANIM_COUNT > 1
                ld   hl, ANIM_TICK
                inc  (hl)
                ld   a, (hl)
                cp   ANIM_PERIOD
                ret  c                        ; not time yet (the common path)
                ld   (hl), 0
                ld   hl, ANIM_FRAME
                ld   a, (hl)
                inc  a
                cp   ANIM_COUNT
                jr   c, .store
                xor  a                        ; wrap 2 -> 0
.store:
                ld   (hl), a
                jp   set_anim_frame           ; tail: patch the SMC pointer
    ELSE
                ret
    ENDIF

;------------------------------------------------------------------------------
; anim_idle — moving->idle edge: return to the neutral pose (frame 0) and repaint
; the sprite ONCE so the displayed pose matches ANIM_FRAME. Idle frames render
; nothing otherwise, so without this repaint the wizard would freeze mid-stride
; while the observable said 0. No-op (early ret) once already neutral, which is
; what keeps steady-state idle byte-stable for the goldens.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
anim_idle:
    IF ANIM_COUNT > 1
                xor  a
                ld   (ANIM_TICK), a           ; every walk starts a FRESH cadence,
                                              ; even if we stopped ON frame 0 (17 T,
                                              ; unconditional: cheaper than testing)
                ld   hl, ANIM_FRAME
                cp   (hl)                     ; A = 0 -> Z iff already neutral
                ret  z                        ; already neutral -> screen untouched
                ld   (hl), a                  ; frame 0 (A still 0)
                call set_anim_frame           ; A = 0
    IF USE_SHADOW_DOUBLEBUFFER
                call set_target_front         ; repaint the DISPLAYED buffer only
    ENDIF
                call compute_sc
                ld   a, ATTR_AIR
                call stamp_foot               ; restore the footprint colour
                call erase_foot               ; restore the footprint bitmap
                call stamp_sprite_colour
                jp   blit_current_sprite      ; tail: neutral pose, same position
    ELSE
                ret
    ENDIF

;==============================================================================
; shift_frame_right1 — shift one PRESHIFT_FRAME in place right by 1 px. Per row
; the SPRITE_W_COLS mask bytes (even offsets) ripple right feeding 1 (SCF), then
; the data bytes (odd offsets) ripple right feeding 0. Two passes because the Z80
; carry can only carry ONE ripple chain at a time; the mid-row reposition is a
; 16-bit add so it is safe across a 256-byte boundary inside a 480-B frame.
; Boot-only (design §1.3) — ~7 x (frame copy + this) once, off the hot path.
; In : HL = frame ptr.   Out: HL = frame ptr (preserved).   Clobbers: A, B, DE, HL
;==============================================================================
shift_frame_right1:
                push hl
                ld   b, SPRITE_ROWS_PX        ; 24 / 48 rows
.row:
                scf                           ; mask: feed 1 (transparent) at MSB
                DUP  SPRITE_W_COLS - 1
                rr   (hl)                     ; mask col (even offset)
                inc  hl
                inc  hl
                EDUP
                rr   (hl)                     ; last mask col: HL = base+(W-1)*2
                ld   de, -(SPRITE_W_COLS * 2 - 3)
                add  hl, de                   ; -> base+1 = first data col
                or   a                        ; data: feed 0 at MSB (clears carry)
                DUP  SPRITE_W_COLS - 1
                rr   (hl)                     ; data col (odd offset)
                inc  hl
                inc  hl
                EDUP
                rr   (hl)                     ; last data col: HL = base+2W-1
                inc  hl                       ; -> next row base
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
dcell_bmp_or:
                or   $40                      ; SMC: bitmap base hi ($40 bank5 /
                                              ;      $C0 bank7); patched by
                                              ;      set_target_* (dcell_bmp_or+1)
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

;==============================================================================
; SPIKE-4 — SHADOW-SCREEN DOUBLE-BUFFER (plan SPIKE-4). Guarded, throwaway.
;
; Model (camera-lock follow; deliberate spike simplification of SPIKE-3's dead-
; zone follow so the 4-frame prep aligns with the 8px byte boundary):
;  - FRONT = the buffer ULA displays (bank5 if $7FFD bit3=0, else bank7). Each
;    moving frame the sprite glides 2px on the FRONT only (no scroll) -> smooth.
;  - BACK  = the hidden buffer. Over the 4 frames a scroll cycle spans, we
;    incrementally build the NEXT scrolled frame in it: a cross-buffer byte-shift
;    COPY of the front background (+/-1 col), the newly-exposed column, and the
;    sprite; then reveal it with an ATOMIC $7FFD bit3 flip (single OUT via the
;    shadow byte). No half-prepared buffer is ever displayed (the buffer is hidden
;    until the flip; all draws complete before the OUT).
;  - The cross-buffer copy sources the LIVE front each cycle, so no buffer is ever
;    "2 scrolls behind" (the classic leapfrog trap) -> exactly ONE shift/cycle.
;  - Bank5 ($4000) and bank7 ($C000) are BOTH mapped at once (bits0-2=7 always),
;    so LDI/LDD copy directly bank<->bank. bit4/6 stay 0 (ROM + paging).
;
; Per-frame work under sustained edge-walking (all sub-frame; see plan SPIKE-4):
;   every moving frame : front glide (~13.5k) + 1/4 shift-copy (24 scanlines,
;                        ~12k) [+ phase1: newcol ~17.5k] [+ phase3: flip = erase-
;                        wide ~12k + sprite ~13.5k + OUT]. Worst = the flip frame.
;
; Base-relative rendering (sub-problem 1): draw_cell/scr_cell_addr/attr_addr take
; their high-byte base from SMC operands (dcell_bmp_or+1 / scell_bmp_or+1 /
; attr_base_add+1), patched by set_target_front/back — the SAME per-cell routines
; render to EITHER buffer. Cost of the abstraction: ~0 in the hot loop (the OR/ADD
; immediate is unchanged); ~40 T to re-point per phase (set_target_*). copy_chunk
; is base-agnostic (walks PREP_SRC, back = front hi XOR $80) with 2 SMC compares
; (copy_end_cp/ copy_t2_cp) re-pointed at phase 0 to the CURRENT front's bank.
;==============================================================================

;------------------------------------------------------------------------------
; spike_loop_dbuf — per-frame double-buffer loop.
;------------------------------------------------------------------------------
spike_loop_dbuf:
                call read_dx                  ; D = dx (-1/0/+1)
                ld   a, d
                ld   (CUR_DX), a
                or   a
                jp   z, .idlestop             ; at rest -> untouched (stable golden)

                ; restart the prep cycle if the scroll direction changed
                ld   hl, PREP_DIR
                cp   (hl)
                jr   z, .samedir
                ld   (hl), a
                xor  a
                ld   (PREP_PHASE), a
.samedir:
                ; SPIKE-6: advance the walk frame BEFORE any blit this frame, so the
                ; front glide and (on phase 3) the back-buffer blit agree on the pose.
                call anim_advance
                ; --- FRONT glide (RED erase / MAGENTA draw) on the DISPLAYED buf -
                call set_target_front
                ld   a, COL_RED
                out  (PORT_BORDER), a
                call compute_sc               ; OLD sc (front origin, constant/cycle)
                ld   a, ATTR_AIR
                call stamp_foot
                call erase_foot
                call move_px_only             ; PX += dx*2, clamp; NO origin change
                ld   a, COL_MAGENTA
                out  (PORT_BORDER), a
                call compute_sc               ; NEW sc
                call stamp_sprite_colour
                call blit_current_sprite
                ; --- BACK prep: 1/4 of the scroll; atomic flip on cycle wrap -----
                call back_prep_step
                ld   a, COL_BLACK
                out  (PORT_BORDER), a
                jr   .idle
.idlestop:
                call anim_idle                ; SPIKE-6: settle onto the neutral pose
.idle:
                ld   hl, (FRAME_COUNTER)
                inc  hl
                ld   (FRAME_COUNTER), hl
                halt
                jp   spike_loop_dbuf

;------------------------------------------------------------------------------
; move_px_only — advance SPRITE_PX by ±MOVE_STEP with world clamp; NO scroll.
; In: CUR_DX (nonzero).  Clobbers: A, DE, HL
;------------------------------------------------------------------------------
move_px_only:
                ld   a, (CUR_DX)
                bit  7, a
                jr   nz, .west
                ld   hl, (SPRITE_PX)
                ld   de, MOVE_STEP
                add  hl, de
                ld   de, SPRITE_PX_MAX
                call clamp_hl_max
                ld   (SPRITE_PX), hl
                ret
.west:
                ld   hl, (SPRITE_PX)
                ld   de, MOVE_STEP
                or   a
                sbc  hl, de
                jr   nc, .wok
                ld   hl, 0
.wok:
                ld   (SPRITE_PX), hl
                ret

;------------------------------------------------------------------------------
; back_prep_step — do one phase (1/4) of the scroll into the hidden buffer; on
; the 4th, finish + flip. Camera-lock: only when the origin can still advance in
; the current direction (else the sprite just glides to the screen edge on FRONT).
; Clobbers: A, BC, DE, HL, IX
;------------------------------------------------------------------------------
back_prep_step:
                ld   a, (CUR_DX)
                bit  7, a
                jr   nz, .west
                ld   a, (VIEW_ORIGIN_COL)     ; east: need origin < ORIGIN_MAX
                cp   ORIGIN_MAX
                ret  nc                        ; world fully scrolled -> no prep
                jr   .active
.west:
                ld   a, (VIEW_ORIGIN_COL)      ; west: need origin > 0
                or   a
                ret  z
.active:
                ld   a, (PREP_PHASE)
                or   a
                jr   nz, .chunk
                call prep_phase0_setup        ; PREP_SRC + copy compares -> front bank
.chunk:
                call copy_chunk               ; 24 content scanlines front->back
                ld   a, (PREP_PHASE)
                cp   1
                jr   nz, .nonewcol
                call prep_newcol_back         ; draw the exposed bg column on back
.nonewcol:
                ld   a, (PREP_PHASE)
                inc  a
                cp   4
                jr   z, .flip
                ld   (PREP_PHASE), a
                ret
.flip:
                xor  a
                ld   (PREP_PHASE), a
                jp   do_flip

;------------------------------------------------------------------------------
; prep_phase0_setup — point the shift-copy walk (PREP_SRC) and its two end-compare
; SMC operands at the CURRENT front buffer's bitmap bank (bank5 or bank7).
; Clobbers: A, HL
;------------------------------------------------------------------------------
prep_phase0_setup:
                ld   hl, BMP_C_START          ; bank5 content start $4880
                ld   a, SCREEN_ATTR >> 8      ; $58 end / $50 third2 (bank5)
                ld   d, a                     ; stash end-hi
                ld   e, BMP_T2_HIGH
                ld   a, (PORT_7FFD_SHADOW)
                and  P7FFD_SCR7               ; bit3 -> front is bank7?
                jr   z, .set
                ld   a, h                     ; front=bank7: +$80 to every hi
                add  a, BANK_HI_OFF
                ld   h, a
                ld   a, d
                add  a, BANK_HI_OFF
                ld   d, a
                ld   a, e
                add  a, BANK_HI_OFF
                ld   e, a
.set:
                ld   (PREP_SRC), hl
                ld   a, d
                ld   (copy_chunk.end_cp + 1), a  ; SMC: front bitmap-end hi
                ld   a, e
                ld   (copy_chunk.t2_cp + 1), a   ; SMC: front third2 hi
                ret

;------------------------------------------------------------------------------
; copy_chunk — shift-copy up to 24 content scanlines from FRONT to BACK, offset
; by one char column (east: back[c]=front[c+1] via LDI; west: back[c]=front[c-1]
; via LDD). back addr = front addr with hi XOR $80. Walk state persists in
; PREP_SRC so the 4 chunks cover all 96 content scanlines (rows 12..23), skipping
; blank sky exactly as shift_bitmap_left. Clobbers: A, BC, DE, HL, IX
;------------------------------------------------------------------------------
copy_chunk:
                ld   ix, (PREP_SRC)
                ld   b, 24                     ; scanlines this chunk
.sl:
                ld   a, (CUR_DX)
                bit  7, a
                jr   nz, .wcopy
                push ix                        ; EAST: LDI front[+1] -> back[+0]
                pop  hl
                inc  hl                        ; HL = front col1 (src)
                push ix
                pop  de
                ld   a, d
                xor  BANK_HI_OFF               ; DE = back col0 (dest), hi^$80
                ld   d, a
                ld   c, $FF                    ; prevent LDI borrow into B ($FF≥31)
                DUP  31
                ldi
                EDUP
                jr   .adv
.wcopy:
                push ix                        ; WEST: LDD front[-1] -> back[+0]
                pop  hl
                ld   a, l
                add  a, VIEW_COLS - 2          ; HL = front col30 (src)
                ld   l, a
                push ix
                pop  de
                ld   a, e
                add  a, VIEW_COLS - 1          ; back col31 (dest) low
                ld   e, a
                ld   a, d
                xor  BANK_HI_OFF               ; back hi ^$80
                ld   d, a
                ld   c, $FF                    ; prevent LDD borrow into B ($FF≥31)
                DUP  31
                ldd
                EDUP
.adv:
                ld   a, ixl                    ; next content scanline (verified walk)
                add  a, 32
                ld   ixl, a
                jr   nc, .cont
                ld   a, ixh
                inc  a
                ld   ixh, a
.end_cp:
                cp   $58                       ; SMC: past bitmap content -> done
                jr   nc, .done
.t2_cp:
                cp   $50                       ; SMC: reached third2 -> walk all r'
                jr   nc, .cont
                ld   a, 128                     ; still third1: skip sky (r'0..3)
                ld   ixl, a
.cont:
                dec  b                          ; (djnz out of range: body > 127 B)
                jp   nz, .sl
                ld   (PREP_SRC), ix
                ret
.done:
                ld   (PREP_SRC), ix
                ret

;------------------------------------------------------------------------------
; prep_newcol_back — draw the newly-exposed background column (bitmap) into the
; BACK buffer. The back represents origin±1 but VIEW_ORIGIN_COL still holds the
; front origin, so temporarily bump it for the correct world col. Bitmap only
; (back bands are static — set once in init_back_buffer). Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
prep_newcol_back:
                call set_target_back
                ld   hl, VIEW_ORIGIN_COL
                ld   a, (CUR_DX)
                bit  7, a
                jr   nz, .west
                inc  (hl)                      ; temp origin = O+1 (east)
                ld   c, VIEW_COLS - 1          ; screen col 31 -> world O+32
                call draw_newcol_bitmap
                ld   hl, VIEW_ORIGIN_COL
                dec  (hl)
                ret
.west:
                dec  (hl)                      ; temp origin = O-1 (west)
                ld   c, 0                       ; screen col 0 -> world O-1
                call draw_newcol_bitmap
                ld   hl, VIEW_ORIGIN_COL
                inc  (hl)
                ret

;------------------------------------------------------------------------------
; do_flip — finish the back buffer (advance origin, clear the stale shifted sprite
; the copy carried, blit the fresh sprite + footprint attr) and reveal it with an
; atomic $7FFD bit3 flip. The single OUT is the tear-free reveal; no di needed
; (the ROM ISR never writes $7FFD, and the shadow RMW completes before the OUT).
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
do_flip:
                ld   hl, VIEW_ORIGIN_COL       ; new displayed origin (= back origin)
                ld   a, (CUR_DX)
                bit  7, a
                jr   nz, .worg
                inc  (hl)                      ; east: O -> O+1
                jr   .draw
.worg:
                dec  (hl)                      ; west: O -> O-1
.draw:
                call set_target_back           ; draw into the hidden (soon-front) buf
                call compute_sc                ; CUR_SC = sprite col at new origin
                call erase_wide                ; clear stale shifted sprite (rows15-17)
                call stamp_sprite_colour                ; footprint colour on back
                call blit_current_sprite       ; fresh sprite on back
                ld   a, (PORT_7FFD_SHADOW)      ; ATOMIC reveal: toggle display bit3
                xor  P7FFD_SCR7
                ld   (PORT_7FFD_SHADOW), a
                ld   bc, PORT_7FFD
                out  (c), a
                ret

;------------------------------------------------------------------------------
; erase_wide — redraw bg bitmap + reset attr to ATTR_AIR over a 6-col window
; (CUR_SC-2..CUR_SC+3), rows 15..17, on the CURRENT target. Clears the stale
; shifted sprite the cross-buffer copy carried into the back's sprite band and the
; prior cycle's footprint colour. Sprite is camera-pinned near screen centre, so
; the window stays on-screen (0..31). Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
; 2 cols of left margin + the sprite span + 1 col of right margin: the stale
; sprite the cross-buffer copy carried in is offset by at most one column either
; way, so W+3 covers it for both sprite sizes (6 cols legacy, 8 cols hero).
ERASE_WIDE_COLS EQU SPRITE_W_COLS + 3
erase_wide:
                ld   b, SPRITE_TOP_ROW         ; first sprite char row
                ld   e, SPRITE_H_ROWS          ; 3 / 6 rows
.row:
                push bc
                push de
                ld   a, (CUR_SC)
                sub  2                          ; start col = sc-2 (pinned -> >=0)
                ld   c, a
                ld   d, ERASE_WIDE_COLS
.col:
                push bc
                push de
                call attr_addr                 ; HL = attr(B,C) on target
                ld   (hl), ATTR_AIR
                call draw_bg_cell_bitmap        ; bg bitmap (B=row,C=col; C preserved)
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

;------------------------------------------------------------------------------
; set_target_front / set_target_back — point the render-base SMC at the displayed
; / hidden buffer (per $7FFD bit3). set_target_bank5/7 do the actual patch.
; Clobbers: A
;------------------------------------------------------------------------------
set_target_front:
                ld   a, (PORT_7FFD_SHADOW)
                and  P7FFD_SCR7                ; bit3=0 -> bank5 displayed
                jr   z, set_target_bank5
                jr   set_target_bank7
set_target_back:
                ld   a, (PORT_7FFD_SHADOW)
                and  P7FFD_SCR7                ; bit3=0 -> back is bank7
                jr   z, set_target_bank7
                ; fall through: bit3=1 -> back is bank5
set_target_bank5:
                ld   a, SCREEN_BITMAP >> 8      ; $40
                ld   (dcell_bmp_or + 1), a
                ld   (scell_bmp_or + 1), a
                ld   a, SCREEN_ATTR >> 8        ; $58
                ld   (attr_base_add + 1), a
                ret
set_target_bank7:
                ld   a, BACK_BMP_BASE >> 8      ; $C0
                ld   (dcell_bmp_or + 1), a
                ld   (scell_bmp_or + 1), a
                ld   a, BACK_ATTR_BASE >> 8     ; $D8
                ld   (attr_base_add + 1), a
                ret

;------------------------------------------------------------------------------
; init_back_buffer — render an identical initial frame into bank7 so the first
; flip reveals a valid, complete frame. Leaves target = bank5 (displayed).
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
init_back_buffer:
                call set_target_bank7
                ld   hl, BACK_BMP_BASE          ; clear bank7 bitmap
                ld   (hl), 0
                ld   de, BACK_BMP_BASE + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ldir
                ld   hl, BACK_ATTR_BASE          ; air band (rows 0..17)
                ld   (hl), ATTR_AIR
                ld   de, BACK_ATTR_BASE + 1
                ld   bc, GROUND_ROW * 32 - 1
                ldir
                ld   hl, BACK_ATTR_BASE + GROUND_ROW * 32   ; ground band (18..23)
                ld   (hl), ATTR_GROUND
                ld   de, BACK_ATTR_BASE + GROUND_ROW * 32 + 1
                ld   bc, (VIEW_ROWS - GROUND_ROW) * 32 - 1
                ldir
                call redraw_view                ; bg bitmap into bank7
                call compute_sc
                call stamp_sprite_colour
                call blit_current_sprite
                jp   set_target_bank5           ; restore target -> displayed (tail)

spike_code_end:
SPIKE_CODE_LEN  EQU spike_code_end - spike_start

;==============================================================================
; Background + sprite asset data (artist-emitted; reused, not recreated).
;==============================================================================
                INCLUDE "../assets/gfx/bg_tiles.asm"

; The selected hero frames, back to back. `sprite_frame` is the single name the
; renderer uses; anim frame i starts at sprite_frame + i*ANIM_FRAME_BYTES and its
; colour descriptor is the byte at +SPRITE_SRC_FRAME (the converter appends it
; right after the frame — design §1.7 / tools/gfx_convert.py emit_sprite_asm).
; The converter emits every frame at identical size, so the stride is a constant.
sprite_frame:
    IF USE_HERO_32X48
                INCLUDE "../assets/gfx/wizard_ai_test_f0.asm"  ; walk f0, 385 B, $45
                INCLUDE "../assets/gfx/wizard_ai_test_f1.asm"  ; walk f1, 385 B, $45
                INCLUDE "../assets/gfx/wizard_ai_test_f2.asm"  ; walk f2, 385 B, $45
    ELSE
                INCLUDE "../assets/gfx/player.asm"           ; 16x24, 145 B, attr $46
    ENDIF

spike_data_end:
SPIKE_IMAGE_LEN EQU spike_data_end - spike_start

;------------------------------------------------------------------------------
; Layout guards — the boot-generated pre-shift table must not overlap the image
; below it or WORLD_BUF above it, and the asset must match the geometry EQUs.
;------------------------------------------------------------------------------
                ASSERT spike_data_end - sprite_frame == ANIM_COUNT * ANIM_FRAME_BYTES
    IF USE_HERO_32X48
                ; f0/f1 live in the "$5CCB..$7FFF free RAM" run (dead once we take
                ; control — see the PRESHIFT_TABLE tradeoff note); f2 in the run
                ; above the image, below WORLD_BUF.
                ASSERT PRESHIFT_TABLE  + PRESHIFT_SIZE <= PRESHIFT_TABLE1
                ASSERT PRESHIFT_TABLE1 + PRESHIFT_SIZE <= $8000
                ASSERT spike_data_end <= PRESHIFT_TABLE2
                ASSERT PRESHIFT_TABLE2 + PRESHIFT_SIZE <= WORLD_BUF
                ; No colour flicker across the cycle: every walk frame must carry
                ; the SAME colour descriptor, since SPRITE_ATTR is read once at boot.
                ASSERT {b sprite_frame + 1 * ANIM_FRAME_BYTES + SPRITE_SRC_FRAME} == {b sprite_frame + SPRITE_SRC_FRAME}
                ASSERT {b sprite_frame + 2 * ANIM_FRAME_BYTES + SPRITE_SRC_FRAME} == {b sprite_frame + SPRITE_SRC_FRAME}
    ELSE
                ASSERT spike_data_end <= PRESHIFT_TABLE
                ASSERT PRESHIFT_TABLE + PRESHIFT_SIZE <= WORLD_BUF
    ENDIF

;------------------------------------------------------------------------------
; spk_loader — 10 CLEAR VAL "32767": RANDOMIZE USR VAL "32768"  (scratch ORG).
;------------------------------------------------------------------------------
                ORG  $E000
spk_loader:
                ; Line 10: CLEAR VAL "32767"
                DB   0, 10
                DW   spk_l10_end - spk_l10_body
spk_l10_body:
                DB   $FD
                DB   $B0, '"', "32767", '"'
                DB   $0D
spk_l10_end:

                ; Line 20: LOAD "" CODE — without this, RANDOMIZE USR jumps
                ; into memory the tape never actually loaded (see main.asm's
                ; tap_loader for the full explanation of this gotcha).
                DB   0, 20
                DW   spk_l20_end - spk_l20_body
spk_l20_body:
                DB   $EF
                DB   $22, $22
                DB   $AF
                DB   $0D
spk_l20_end:

                ; Line 30: RANDOMIZE USR VAL "32768"
                DB   0, 30
                DW   spk_l30_end - spk_l30_body
spk_l30_body:
                DB   $F9
                DB   $C0
                DB   $B0, '"', "32768", '"'
                DB   $0D
spk_l30_end:
spk_loader_len  EQU  $ - spk_loader

;==============================================================================
; Emit artefacts: an auto-running .tap + a snapshot (separate from wazhack.*).
;==============================================================================
; The hero build writes DIFFERENT filenames so it can never silently shadow the
; artefacts tests/sideview.py + tests/scroll.py assert against.
; MUST come after spk_loader's bytes are assembled — SAVETAP dumps the
; assembler's memory image at the point it executes in source order; calling
; it earlier silently emits an all-zero BASIC data block (see main.asm for
; the full explanation of this sjasmplus gotcha).
    IF USE_HERO_32X48
                EMPTYTAP "build/spike_hero.tap"
                SAVETAP  "build/spike_hero.tap", BASIC, "spikeh", spk_loader, spk_loader_len, 10
                SAVETAP  "build/spike_hero.tap", CODE,  "spikeh", spike_start, SPIKE_IMAGE_LEN
                SAVESNA  "build/spike_hero.sna", spike_start
    ELSE
                EMPTYTAP "build/spike.tap"
                SAVETAP  "build/spike.tap", BASIC, "spike", spk_loader, spk_loader_len, 10
                SAVETAP  "build/spike.tap", CODE,  "spike", spike_start, SPIKE_IMAGE_LEN
                SAVESNA  "build/spike.sna", spike_start
    ENDIF
