;==============================================================================
; fx.asm — D3-5 FX engine (bank 2, hot): render-only projectile / impact
; tracks (game.md §6: real masked sprites, no entity slot, cell-aligned,
; 8 px/tick or 16 px/tick, STATIONARY frames with one shift, bursts SYM;
; <= FX_TRACKS at once, more queued). Plan "3D breakdown" decision P: the
; LOGIC is resolved at cast time (proj_fire, D3-6b); a track only replays the
; precomputed path (segments with a reversal between each) and its impact.
;
; Per tick:
;   render (phase 2 end)  fx_erase: a drawn FX whose desired state changed is
;                         erased from the clean background (erase_rect) and the
;                         rect joins the damage list BEFORE DMG_PRES_N (so it is
;                         presented and the bodies under it are repaired).
;   render (after bodies) fx_draw: FX are drawn LAST: a changed FX is blitted,
;                         stamped and pmark'ed; an unchanged one is re-blitted
;                         only if a damage rect touches it (a body redrawn
;                         under it); its new footprint joins the damage list
;                         so a later track overlapping it is redrawn on top.
;   anim_gate             fx_tick: advance every live track (after anim_tick:
;                         like R_VIS / R_FID, the desired state is drawn by the
;                         next tick's render).
; Records: combat_defs.asm FXT* / FXD_* / FX_* (docs/memory-map.md "3D
; contracts"). FX_BUSY bit i = track i live OR still drawn; turn_done waits
; for 0; hide_sprites / vis_reset clear everything (fx_hide / fx_reset).
;==============================================================================

fx_trk:         DW   FXT0, FXT1, FXT2           ; track i record (bit 1 << i of FX_BUSY)
                ASSERT FX_TRACKS == 3

;------------------------------------------------------------------------------
; fx_meta — per FX fid (KFID_FXM .. FID_COUNT-1): bits 0-6 = the frame's own
; attr (the sprite sheet's ATTR_SPRITE, assets/gfx/sprites/<name>.asm header;
; black paper), bit 7 = ay 8 (the frame top sits one cell above the flight
; row: the 16x16 bursts centred on it). ay is taken from the art's _ay EQU.
;------------------------------------------------------------------------------
    MACRO FXMETA nm, attr
                ASSERT FID_nm == KFID_FXM + ($ - fx_meta)
                ASSERT nm_ay == 0 || nm_ay == 8
                ASSERT (nm_ax & 7) == 0 && ((nm_w - nm_ax - 8) & 7) == 0 && (nm_h & 7) == 0  ; cell-aligned
                DB   (attr) | ((nm_ay >> 3) << 7)
    ENDM
fx_meta:        FXMETA spark_fly1,      $43
                FXMETA spark_fly2,      $43
                FXMETA firebolt_fly1,   $46
                FXMETA firebolt_fly2,   $42
                FXMETA firebolt_burst1, $46
                FXMETA firebolt_burst2, $42
                FXMETA frost_fly,       $45
                FXMETA frost_crack,     $45
                FXMETA drain_fly1,      $43
                FXMETA drain_fly2,      $43
                FXMETA drain_hit,       $43
                FXMETA lightning_fly1,  $47
                FXMETA lightning_fly2,  $47
                FXMETA lightning_flash, $47
                FXMETA staff_bonk,      $46
                FXMETA spark_fizz1,     $43
                FXMETA spark_fizz2,     $43
                FXMETA power_burst,     $47
                FXMETA dagger_spin1,    $47
                FXMETA dagger_spin2,    $47
                FXMETA arrow_fly1,      $07
                FXMETA arrow_fly2,      $07
                FXMETA arrow_hit,       $07
                ASSERT $ - fx_meta == FID_COUNT - KFID_FXM   ; every FX fid, nothing after
                ASSERT FX_NONE == FXF_NONE

;==============================================================================
; fx_start — queue an FX (proj_fire, D3-6b; tests via ZRCP). Callable from
; any bank (pages nothing).
; In : HL = descriptor (FXD_LEN 16 B, combat_defs.asm FXD_*; copied, so it may
;      be transient). FXD_NSEG must be 1..FXD_SEGMAX.
; Out: CF = 1 accepted, CF = 0 dropped (3 tracks live + FXQ_MAX queued).
;      Started now: A = impact tick = FXD_DELAY + ceil(cells / speed) + 1, counted
;      in fx_tick calls from the next one (0 = the next fx_tick; a turn's input
;      tick runs read_turn_input BEFORE anim_gate, so A = the TURN_TICK on which
;      the impact frame is set: the E_REACTAT of the target's reaction).
;      Queued: A = FX_NONE (it starts on the tick a track frees).
; Clobbers: all but IY.   ~0.9k T
;==============================================================================
fx_start:
                push hl
                call fx_free                   ; IX = idle track, C = its bit
                pop  hl
                jr   c, .queue
                call fx_load
                ; eta: delay + ceil(sum(segs) / cells per tick) + 1
                ld   b, (ix+FXD_NSEG)
                push ix
                pop  hl
                ld   de, FXD_SEGS
                add  hl, de
                xor  a
.sum:           add  a, (hl)
                inc  hl
                djnz .sum
                bit  FXDF_FAST_BIT, (ix+FXD_FLAGS)
                jr   z, .slow
                inc  a
                srl  a                         ; (cells + 1) / 2
.slow:          add  a, (ix+FXD_DELAY)
                inc  a
                scf
                ret
.queue:         ld   a, (FXQ_N)
                cp   FXQ_MAX
                ret  nc                        ; CF = 0: dropped
                ld   de, FXQ0
                or   a
                jr   z, .q0
                ld   de, FXQ1
.q0:            inc  a
                ld   (FXQ_N), a
                ld   bc, FXD_LEN
                ldir
                ld   a, FX_NONE
                scf
                ret
                ASSERT FXQ_MAX == 2

; fx_free — IX = the first idle track (FX_ST 0; it may still be drawn: render
; erases that), C = its FX_BUSY bit, CF = 0; CF = 1 if none.  Clobbers: A, DE, HL
fx_free:
                ld   hl, fx_trk
                ld   c, 1
.l:             ld   e, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                push de
                pop  ix
                ld   a, (ix+FX_ST)
                or   a
                ret  z                         ; CF = 0
                sla  c
                bit  FX_TRACKS, c
                jr   z, .l
                scf
                ret

; fx_load — start descriptor HL in idle track IX (bit C): copy, WAIT state,
; hidden; the drawn part is kept (render erases a previous sprite).
; Clobbers: A, BC, DE, HL
fx_load:
                ld   a, (FX_BUSY)
                or   c
                ld   (FX_BUSY), a
                push ix
                pop  de
                ld   bc, FXD_LEN
                ldir
                ld   (ix+FX_ST), FXS_WAIT
                ld   (ix+FX_PH), 0
                ld   (ix+FX_FID), FX_NONE
                ret

;------------------------------------------------------------------------------
; fx_iter — call the routine at HL for every track whose FX_BUSY bit is set
; (snapshot taken on entry): IX = the record, C = its bit (1 / 2 / 4; track
; index = C >> 1). The routine may clobber A, BC, DE, HL, IX.
; Clobbers: all but IY.  ~95 T + 16 T per idle track + ~60 T per busy one
; (unrolled: the D3-5 measurement had the HL-table loop at ~370 T a pass).
; SMC: .f0/.f1/.f2+1 = the per-track routine (patched per call).
;------------------------------------------------------------------------------
fx_iter:
                ld   (.f0+1), hl               ; SMC
                ld   (.f1+1), hl               ; SMC
                ld   (.f2+1), hl               ; SMC
                ld   a, (FX_BUSY)
                rra
                jr   nc, .t1
                push af
                ld   ix, FXT0
                ld   c, 1
.f0:            call 0                         ; SMC: per-track routine
                pop  af
.t1:            rra
                jr   nc, .t2
                push af
                ld   ix, FXT1
                ld   c, 2
.f1:            call 0                         ; SMC
                pop  af
.t2:            rra
                ret  nc
                ld   ix, FXT2
                ld   c, 4
.f2:            jp   0                         ; SMC (tail call)
                ASSERT FX_TRACKS == 3

;==============================================================================
; fx_tick — advance every live track one tick (anim_gate, after anim_tick),
; then start queued descriptors in the tracks that went idle.
; Timeline of a track started before fx_tick #0 (FXD_DELAY d, n cells, s cells
; per tick, F = ceil(n / s)): #0..#d-1 hidden; #d the first flight frame at
; FXD_COL; #d+1..#d+F one step each (2 cells for FXDF_FAST; a segment end
; reverses the direction, mid-tick if need be); #d+F+1 the impact frame
; (FXD_IMPA) on the last cell, FXD_IMPT ticks alternating IMPA / IMPB; then
; idle (hidden: the next render erases it). No impact (FXD_IMPA = FX_NONE or
; FXD_IMPT = 0): idle at #d+F+1.
; Clobbers: all but IY.  Idle 45 T (incl. the call); ~0.7k T per live track
; (+0.15k per reversal).
;==============================================================================
fx_tick:
                ld   a, (FX_BUSY)
                or   a
                ret  z
                ld   hl, fx_trk_tick
                call fx_iter
                ld   a, (FXQ_N)
                or   a
                ret  z
                ; fall through
; fx_qpop — move queued descriptors (FIFO) into idle tracks.  Clobbers: all but IY
fx_qpop:
.l:             ld   a, (FXQ_N)
                or   a
                ret  z
                call fx_free
                ret  c
                ld   hl, FXQ0
                call fx_load
                ld   hl, FXQ1
                ld   de, FXQ0
                ld   bc, FXD_LEN
                ldir
                ld   hl, FXQ_N
                dec  (hl)
                jr   .l

; fx_trk_tick — one track (IX). Clobbers: A, BC, DE, HL
fx_trk_tick:
                ld   a, (ix+FX_ST)
                or   a
                ret  z                         ; idle (maybe still drawn)
                dec  a
                jr   nz, .live
                ld   a, (ix+FXD_DELAY)          ; WAIT
                or   a
                jr   z, .appear
                dec  (ix+FXD_DELAY)
                ret
.appear:        ld   (ix+FX_ST), FXS_FLY
                jr   .fly
.live:          dec  a
                jr   nz, .imp
                call fx_step                   ; FLY
                jr   c, .land                  ; no cell left: the impact
                bit  FXDF_FAST_BIT, (ix+FXD_FLAGS)
                call nz, fx_step               ; (a 1-cell remainder ends there)
.fly:           ld   a, (ix+FX_PH)
                inc  (ix+FX_PH)
                rra
                ld   a, (ix+FXD_FIDA)
                jr   nc, fx_set
                ld   a, (ix+FXD_FIDB)
                jr   fx_set
.land:          ld   a, (ix+FXD_IMPA)
                inc  a
                jr   z, .fin                   ; FX_NONE: no impact sprite
                ld   a, (ix+FXD_IMPT)
                or   a
                jr   z, .fin
                ld   (ix+FX_ST), FXS_IMP
                ld   (ix+FX_PH), 0
                jr   .ishow
.imp:           dec  (ix+FXD_IMPT)
                jr   z, .fin
.ishow:         ld   a, (ix+FX_PH)
                inc  (ix+FX_PH)
                rra
                ld   a, (ix+FXD_IMPA)
                jr   nc, fx_set
                ld   a, (ix+FXD_IMPB)
                jr   fx_set
.fin:           ld   (ix+FX_ST), FXS_IDLE
                ld   (ix+FX_FID), FX_NONE
                ret

;------------------------------------------------------------------------------
; fx_step — move track IX one cell along its path: a finished segment (0 cells
; left) is dropped and the direction reversed first. CF = 1: no cell left on
; the path (nothing moved).  Clobbers: A
;------------------------------------------------------------------------------
fx_step:
.chk:           ld   a, (ix+FXD_SEGS)
                or   a
                jr   nz, .mv
                ld   a, (ix+FXD_NSEG)
                dec  a
                scf
                ret  z                         ; last segment done: landed
                ld   (ix+FXD_NSEG), a
                ld   a, (ix+FXD_SEGS + 1)       ; next segment (bounce / reflect)
                ld   (ix+FXD_SEGS), a
                ld   a, (ix+FXD_SEGS + 2)
                ld   (ix+FXD_SEGS + 1), a
                ld   a, (ix+FXD_SEGS + 3)
                ld   (ix+FXD_SEGS + 2), a
                ld   a, (ix+FXD_SEGS + 4)
                ld   (ix+FXD_SEGS + 3), a
                ld   a, (ix+FXD_FLAGS)
                xor  FXDF_LEFT
                ld   (ix+FXD_FLAGS), a
                jr   .chk
.mv:            dec  (ix+FXD_SEGS)
                ld   a, (ix+FXD_FLAGS)
                rra                            ; CF = FXDF_LEFT (bit 0)
                ld   a, (ix+FXD_COL)
                jr   nc, .r
                dec  a
                dec  a
.r:             inc  a
                ld   (ix+FXD_COL), a
                or   a                         ; CF = 0
                ret
                ASSERT FXDF_LEFT == 1

;------------------------------------------------------------------------------
; fx_set — desired state of track IX = frame A at its cell: FX_FID, FX_ATTR
; (FXD_ATTR or fx_meta), FX_LEFT, footprint FX_COL = FXD_COL + FT_OFFR/8 or
; FT_OFFL/8 (left-facing 16-wide frames: col - 1), FX_ROW = FXD_ROW - ay/8,
; FX_COLS = FT_COLS, FX_ROWS = FT_H/8. A frame that would leave the screen
; columns or the playfield rows is hidden (FX_NONE; proj_fire keeps paths
; inside, this is the guard). A = FX_NONE: hidden (an impact-only FX, e.g. a
; melee burst, has FXD_FIDA = FXD_FIDB = FX_NONE).
; Clobbers: A, BC, DE, HL   ~0.4k T
;------------------------------------------------------------------------------
fx_set:
                ld   (ix+FX_FID), a
                cp   FX_NONE
                ret  z
                ld   e, a
                ld   l, a
                ld   h, 0
                ld   bc, fx_meta - KFID_FXM
                add  hl, bc
                ld   d, (hl)                   ; D = meta (bit 7: ay 8)
                ld   a, (ix+FXD_ATTR)
                or   a
                jr   nz, .at
                ld   a, d
                and  $7F
.at:            ld   (ix+FX_ATTR), a
                ld   l, e
                ld   h, 0
                add  hl, hl
                add  hl, hl
                ld   bc, frame_tab + FT_COLS
                add  hl, bc
                ld   c, (hl)                   ; C = cols
                inc  hl
                ld   a, (hl)                   ; H px -> rows
                rrca
                rrca
                rrca
                ld   b, a                      ; B = rows (H = 8n)
                ld   (ix+FX_COLS), c
                ld   (ix+FX_ROWS), b
                ld   a, d
                rlca
                and  1                         ; ay / 8
                ld   d, a
                ld   a, (ix+FXD_ROW)
                sub  d
                jr   c, .hide                  ; above row 0
                ld   (ix+FX_ROW), a
                add  a, b
                cp   PLAY_ROWS + 1
                jr   nc, .hide                 ; below the playfield
                inc  hl                        ; FT_OFFR
                ld   a, (ix+FXD_FLAGS)
                and  FXDF_LEFT
                ld   (ix+FX_LEFT), a
                jr   z, .r
                inc  hl                        ; FT_OFFL
.r:             ld   a, (hl)
                sra  a
                sra  a
                sra  a                         ; offset / 8 (signed)
                add  a, (ix+FXD_COL)
                cp   ROOM_COLS                 ; < 0 wraps to >= $F8: out
                jr   nc, .hide
                ld   (ix+FX_COL), a
                add  a, c
                cp   ROOM_COLS + 1
                ret  c
.hide:          ld   (ix+FX_FID), FX_NONE
                ret

;==============================================================================
; fx_erase — render, end of phase 2 (before DMG_PRES_N): erase every drawn FX
; whose desired state (FX_FID..FX_ROWS) differs from the drawn one, damage
; rect = its footprint (presented; bodies under it repaired by phase 3).
; Clobbers: all but IY.  ~1.3k T per erased 2-cell FX (+ the body repairs it
; causes); unchanged ~0.35k.
;==============================================================================
fx_erase:
                ld   hl, fx_trk_erase
                jp   fx_iter

fx_trk_erase:
                ld   a, (ix+FX_DFID)
                inc  a
                ret  z                         ; not drawn
                push ix
                pop  hl
                ld   de, FX_FID
                add  hl, de
                ld   b, FX_STATE_LEN
.cmp:           ld   e, (hl)
                ld   a, l
                add  a, FX_STATE_LEN           ; (records never cross a page)
                ld   l, a
                ld   a, e
                cp   (hl)
                jr   nz, .er
                ld   a, l
                sub  FX_STATE_LEN - 1
                ld   l, a
                djnz .cmp
                ret                            ; unchanged: keep it
.er:            ld   a, c
                rra                            ; C 1 / 2 / 4 -> track 0 / 1 / 2
                add  a, FX_SLOT0
                ld   (ANIM_SLOT), a            ; (flicker.py: slot 16 + track)
                ld   c, (ix+FX_DCOL)
                ld   b, (ix+FX_DROW)
                ld   d, (ix+FX_DCOLS)
                ld   e, (ix+FX_DROWS)
                push bc
                push de
                call erase_rect
.probe_ret:                                    ; flicker probe (no code)
                pop  de
                pop  bc
                call dmg_add
                ld   (ix+FX_DFID), FX_NONE
                ret

;==============================================================================
; fx_draw — render, after every body (the player too): FX are drawn last.
; Changed (not drawn): blit + attr stamp + present mark + damage rect, drawn
; state := desired. Unchanged: re-blit only if a damage rect touches it.
; Hidden and idle: the track's FX_BUSY bit is cleared (turn_done waits on it).
; Clobbers: all but IY.  ~3.5k T for an 8x8 / 16x8 FX, ~5k for 16x16.
;==============================================================================
fx_draw:
                ld   hl, fx_trk_draw
                jp   fx_iter

fx_trk_draw:
                ld   a, (ix+FX_FID)
                cp   FX_NONE
                jr   nz, .vis
                ld   a, (ix+FX_ST)             ; hidden: free once idle (not drawn:
                or   a                         ; fx_erase just erased it)
                ret  nz
                ld   a, c
                cpl
                ld   hl, FX_BUSY
                and  (hl)
                ld   (hl), a
                ret
.vis:           ld   a, c
                add  a, a
                neg                            ; bits of the later tracks
                ld   (.later+1), a             ; SMC: used by .new
                ld   a, c
                rra
                add  a, FX_SLOT0
                ld   (ANIM_SLOT), a
                ld   a, (ix+FX_DFID)
                inc  a
                jr   z, .new
                ld   c, (ix+FX_DCOL)           ; unchanged: a body redrawn under it?
                ld   b, (ix+FX_DROW)
                ld   d, (ix+FX_DCOLS)
                ld   e, (ix+FX_DROWS)
                call dmg_hit
                ret  nc
                jr   fx_blit                   ; same bytes outside the damage: no mark
.new:           call fx_blit                   ; C,B,D,E = footprint
                call pmark_rect                ; (BC, DE kept)
                ld   a, (FX_BUSY)              ; a later busy track redraws over it:
.later:         and  0                         ; SMC: its bits; damage rect only then
                call nz, dmg_add
                push ix
                pop  hl
                ld   de, FX_FID
                add  hl, de
                ld   d, h
                ld   a, l
                add  a, FX_STATE_LEN
                ld   e, a
                ld   bc, FX_STATE_LEN
                ldir                           ; drawn := desired (7 B)
                ret

; fx_blit — blit track IX's desired frame, stamp its attr. Out: C,B,D,E = its
; footprint (FX_COL..FX_ROWS).  Clobbers: A, BC, DE, HL
fx_blit:
                ld   a, (ix+FX_FID)
                ld   (BL_FID), a
                ld   a, (ix+FX_COL)
                add  a, a
                add  a, a
                add  a, a
                ld   (BL_FPX), a
                ld   a, (ix+FX_ROW)
                add  a, a
                add  a, a
                add  a, a
                ld   (BL_FPY), a
                ld   a, (ix+FX_LEFT)
                ld   (BL_LEFT), a
                call blit_sprite
.probe_ret:                                    ; flicker probe (no code)
                ld   a, (ix+FX_ATTR)
                ld   c, (ix+FX_COL)
                ld   b, (ix+FX_ROW)
                ld   d, (ix+FX_COLS)
                ld   e, (ix+FX_ROWS)
                push bc
                push de
                call stamp_rect
                pop  de
                pop  bc
                ret

;==============================================================================
; fx_occ — CF = 1 if cell (col C, row B) is inside a drawn FX footprint
; (decor_tick: an animated decor step must not paint over an FX).
; Clobbers: A, DE, HL (BC, IX kept).  Idle 28 T; ~0.15k per track
;==============================================================================
fx_occ:
                ld   a, (FX_BUSY)
                or   a
                ret  z                         ; CF = 0
                ld   hl, fx_trk
                ld   e, FX_TRACKS
.l:             ld   a, (hl)
                inc  hl
                push hl
                ld   h, (hl)
                add  a, FX_DFID
                ld   l, a                      ; (records never cross a page)
                ld   a, (hl)
                inc  a
                jr   z, .n                     ; not drawn
                ld   a, l
                add  a, FX_DCOL - FX_DFID
                ld   l, a
                ld   a, c
                sub  (hl)
                jr   c, .n
                inc  l
                inc  l                         ; FX_DCOLS
                cp   (hl)
                jr   nc, .n
                dec  l                         ; FX_DROW
                ld   a, b
                sub  (hl)
                jr   c, .n
                inc  l
                inc  l                         ; FX_DROWS
                cp   (hl)
                jr   c, .hit
.n:             pop  hl
                inc  hl
                dec  e
                jr   nz, .l
                or   a
                ret
.hit:           pop  hl
                scf
                ret

;==============================================================================
; fx_hide — hide_sprites (before a transition): erase every drawn FX, then
; fx_reset. Leaves bank 7 paged if it erased.  Clobbers: all but IY
; fx_reset — vis_reset (the screen was redrawn): every track idle and not
; drawn, queue empty, FX_BUSY 0.  Clobbers: A, B, DE, HL, IX
;==============================================================================
fx_hide:
                ld   hl, fx_trk_hide
                call fx_iter
fx_reset:
                ld   hl, fx_trk
                ld   b, FX_TRACKS
.l:             ld   e, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                push de
                pop  ix
                ld   (ix+FX_ST), FXS_IDLE
                ld   (ix+FX_FID), FX_NONE
                ld   (ix+FX_DFID), FX_NONE
                djnz .l
                xor  a
                ld   (FX_BUSY), a
                ld   (FXQ_N), a
                ret

fx_trk_hide:
                ld   a, (ix+FX_DFID)
                inc  a
                ret  z
                ld   c, (ix+FX_DCOL)
                ld   b, (ix+FX_DROW)
                ld   d, (ix+FX_DCOLS)
                ld   e, (ix+FX_DROWS)
                jp   erase_rect
