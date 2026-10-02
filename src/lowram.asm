;==============================================================================
; lowram.asm — COLD code + boot-only data in bank 5 low RAM (docs/memory-map.md
; "Bank 5 low RAM"). Bank 5 is always mapped at $4000-$7FFF, so code here can
; page ANY bank through $C000 — the generator reads the sprite sources in banks
; 1/3 and writes the pre-shift pool in banks 0/4/6, so it cannot live in a
; paged bank. main.asm ORGs this block so it ENDS at $8000 (lowram_code ..
; $7FFF): it is contiguous with the bank-2 image and the tape CODE block is the
; single range lowram_code .. code_end, entered at its first byte (start). The
; block ENDS with the frame descriptors (fdesc_tab, A6): new frames grow it
; downward; main.asm keeps the FRT_MAX growth reserve free below it.
;
; Contended (bank 5): every opcode fetch pays ULA contention while the screen is
; being drawn. Nothing here runs per tick (boot, hero select, game start).
; No ALIGN in here: the base is computed from this block's own size.
;==============================================================================

;------------------------------------------------------------------------------
; start — .tap entry (RANDOMIZE USR start): pull the two headerless blocks off
; tape with the ROM loader (bank 1 = sources; bank 3 = source tail + bank-3
; cold code), then boot. The .sna enters at boot.
;------------------------------------------------------------------------------
start:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR
                call check_paging              ; stops here if $7FFD is locked
.lo:            ld   a, BANK_SRC_LO            ; test probe (paging OK)
                call page_bank
                ld   ix, BANK_WINDOW
                ld   de, SRC_LEN_LO
                ld   a, $FF                    ; data block flag
                scf                            ; LOAD (not VERIFY)
                call ROM_LD_BYTES
                jr   nc, .lo                   ; tape error: rewind + retry
.hi:            ld   a, BANK_COLD3             ; = BANK_SRC_HI: tail + cold code
                call page_bank
                ld   ix, BANK_WINDOW
                ld   de, BANK3_LEN
                ld   a, $FF
                scf
                call ROM_LD_BYTES
                jr   nc, .hi
start_loaded:                                  ; falls straight into boot:
                ASSERT start_loaded == boot    ; nothing may be inserted here

;==============================================================================
; boot — .sna entry. Cold init, pool generation (~1 s), then hero select.
;==============================================================================
boot:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR             ; ROM ISR invariant (conventions)
                im   1
                ld   a, BANK_POOL0
                call page_bank
                xor  a
                out  (PORT_BORDER), a
                ld   (INPUT_SRC), a
                ld   (ANIM_FREEZE), a
                ld   (ANIM_TRACE_IDX), a
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (GEN_TRAP), a             ; since boot (like GEN_OVERFLOW)
                ld   (TURN_PHASE), a
                ld   (ZAP_T), a
                ld   (PEND_DMG_COUNT), a
                ld   (CUR_ROOM), a
                ld   (YIELD_FLAG), a
                ld   hl, HUD_PW                ; A7 HUD tracking: nothing pending,
                ld   (hl), a                   ; ink extents unknown (= whole rows)
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                ld   a, ROOM_COLS
                ld   hl, HUD_EXT
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                xor  a
                ld   hl, 0
                ld   (OVERRUN_COUNT), hl
                ld   (TICK_COUNTER), hl
                ld   (TURN_COUNTER), hl
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   a, 1
                ld   (INPUT_REPEAT), a         ; play default: held keys repeat
                ld   a, GS_BOOT
                ld   (GAME_STATE), a
                ld   hl, ANIM_TRACE
                ld   de, ANIM_TRACE + 1
                ld   bc, ANIM_TRACE_LEN - 1
                ld   (hl), $FF
                ldir
                call init_kbd_mirror
                ld   a, ATTR_HUD
                call clear_screen
                ld   hl, P_ENTITIES            ; nothing drawn / alive yet
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), 0
                ldir
                ei
                call build_bitrev
                call init_tiles
                call alloc_reset
                ; monsters: every kind's frames, both facings (§5.2)
                ld   a, K_SKELETON
.gk:            push af
                call gen_kind
                pop  af
                inc  a
                cp   K_COUNT
                jr   c, .gk
                ; the two heroes' IDLE frames for the select screen
                ld   a, FID_knight_idle1
                call gen_frame
                ld   a, FID_wizard_idle
                call gen_frame
                or   a                         ; CF = 0: save
                call sel_frt_copy
                call alloc_mark                ; hero sets regenerate from here
                jp   enter_select              ; bank-2 trampoline -> bank 3

;------------------------------------------------------------------------------
; check_paging — 48 BASIC / USR 0 set $7FFD bit 5 (paging lock): every later
; OUT is ignored, so the two sprite banks would load over each other and the
; pool would alias. Write different bytes to bank 1 and bank 0 at $C000 and
; read bank 1 back; on a mismatch print a message and stop (DI + HALT).
; Tape path only (the .sna preloads all banks and enters at boot). Bank 0 and
; bank 1 $C000 are free here (pool / sources are written after this).
; +2A/+3 are unsupported (different paging). Clobbers: A, BC, HL (+ print).
;------------------------------------------------------------------------------
check_paging:
                ld   a, BANK_SRC_LO
                call page_bank
                ld   hl, BANK_WINDOW
                ld   (hl), PAGING_PROBE
                ld   a, BANK_POOL0
                call page_bank
                ld   (hl), ~PAGING_PROBE & $FF
                ld   a, BANK_SRC_LO
                call page_bank
                ld   a, (hl)
                cp   PAGING_PROBE
                ret  z
                ld   a, ATTR_HUD
                call clear_screen
                ld   b, 11
                ld   c, 5
                ld   hl, str_lock
                call print_str
.locked:        di                             ; test probe (paging locked)
                halt

str_lock:       DB "LOAD FROM 128 BASIC", 0     ; check_paging: $7FFD locked

; select-screen entries: fid, body col, attr, name (5 B; read by sel_run in
; bank 3 and by sel_frt_copy at boot -> must be in always-mapped RAM)
sel_tab:        DB   FID_knight_idle1, 8,  $47
                DW   nm_knight
                DB   FID_wizard_idle,  21, $45
                DW   nm_wizard

;==============================================================================
; start_game — C = hero kind. Generate its frames (§5.2: only the chosen
; hero), new game, first render, then the play loop (bank 2, never returns).
;==============================================================================
start_game:
                ld   a, c
                ld   (HERO_KIND), a
                call alloc_restore
                ld   a, (HERO_KIND)
                call gen_kind
                call new_game
                ld   h, ROOM_MAP >> 8
                ld   a, (CUR_ROOM)
                call build_room_map
                ld   a, ATTR_HUD
                call clear_screen
                call draw_room
                call hud_status
                call hud_room
                call msg_begin
                ld   hl, str_welcome
                call print_str
                call present_full              ; A7: bank 5 -> 7, display bank 7
                ld   a, 1
                ld   (NEED_RELEASE), a         ; the select key must be released
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                jp   play_loop

;==============================================================================
; hud_clear_mark — clear_row's A7 hook: A = the new attr, B = row, C = 0.
; Out: A = cols clear_row must blank (0..32: the old ink extent; 32 if the
; attr changes or the row is not a HUD row).
; HUD row: the cols present must copy grow to the old ink extent (HUD_EXT) —
; or to the whole row if the row's attr changes (compared with bank 5 col 0) —
; and HUD_EXT restarts at 0 (print_char widens both again). Any other row:
; the whole row is marked (unused in play). Cold-ish (≤ 3 per turn), so it
; lives here, not in bank 2.  Clobbers: A, DE, HL (BC kept).
;==============================================================================
hud_clear_mark:
                ld   d, a                      ; D = new attr
                ld   a, b
                sub  HUD_ROW
                jr   c, .whole
                ld   e, a                      ; E = HUD row index
                call attr_addr                 ; HL = attr of (B, 0); keeps BC, DE
                ld   a, (hl)
                sub  d
                ld   d, a                      ; D = 0: same attr
                ld   a, e
                add  a, HUD_EXT & $FF
                ld   l, a
                ld   h, HUD_EXT >> 8
                ld   a, (hl)                   ; old ink extent
                ld   (hl), 0
                cp   ROOM_COLS + 1             ; clamp: clear_row's chain entry
                jr   c, .ext                   ; must stay inside the chain
                ld   a, ROOM_COLS
.ext:
                inc  d
                dec  d
                jr   z, .same
                ld   a, ROOM_COLS              ; attr changes: every cell
.same:          or   a
                ret  z                         ; row was blank, attr unchanged
                ld   e, a
                ld   a, l
                add  a, HUD_ROWS
                ld   l, a                      ; -> HUD_PW
                ld   a, e
                cp   (hl)
                ret  c
                ld   (hl), a                   ; PW = max(PW, extent)
                ld   a, 1
                ld   (PRES_ANY), a
                ld   a, e
                ret
.whole:         ld   de, (ROOM_COLS << 8) | 1
                call pmark_rect
                ld   a, ROOM_COLS
                ret

;==============================================================================
; vis_room_sync — after a room change (do_exit): hide (N_VIS = 0) every slot
; that anim_tick would not show in CUR_ROOM (not ACTIVE, PENDING, or another
; room). Bug B7: render runs first in a tick (RENDER_FIRST), so the first
; render after do_exit used the previous tick's anim_tick output — the OLD
; room's desired state — and drew every monster of the room just left at its
; old position on the new room for one tick (any monster: not follower
; logic). hide_sprites already cleared E_DVIS, so a hidden slot is simply
; skipped (DIRTY_NONE); the hero (and nothing else) is drawn at its arrival
; position with its last frame, as before. Cold (room change only).
; Clobbers: A, B, DE, HL, IX.
;==============================================================================
vis_room_sync:
                ld   ix, P_ENTITIES
                ld   hl, N_VIS
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT
.l:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .hide
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   z, .n
.hide:          ld   (hl), 0
.n:             inc  l                         ; N_VIS: 16 B inside one page
                add  ix, de
                djnz .l
                ret
                ASSERT (N_VIS & $FF) + P_MAX_ENT <= 256

;==============================================================================
; A7 display switching (cold; bank 5 low RAM is always mapped, so bank-2 and
; bank-5 callers alike reach it). page_bank / present stay in bank 2 (hot).
; set_screen — show bank 5 (A = 0) or bank 7 (A = P7FFD_SCREEN7); the $C000
; bank stays as it is. Order: page_bank SMC, shadow, port (shadow before OUT;
; no ISR pages $C000, so SMC vs shadow can never be seen out of step).
; Clobbers: A, BC.   ~90 T
;==============================================================================
set_screen:
                or   P7FFD_ROM48
                ld   (page_bank.scr+1), a     ; SMC: every later page_bank keeps it
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                and  7                        ; current $C000 bank
                or   b
                ld   (PORT_7FFD_SHADOW), a
                ld   bc, PORT_7FFD
                out  (c), a
                ret

; show_bank5 — display the composed screen itself (select, transitions, A7).
; Clobbers: A, BC
show_bank5:
                xor  a
                jr   set_screen

;------------------------------------------------------------------------------
; present_full — the whole bank-5 screen to screen 2, mask cleared, then show
; bank 7 (start_game; the end of a room transition). Leaves bank 7 paged.
; Clobbers: A, BC, DE, HL.   6,912 x 21 T = 145k T + contention (cold).
;------------------------------------------------------------------------------
present_full:
                ld   a, BANK_SCREEN7
                call page_bank
                ld   hl, SCREEN_BITMAP
                ld   de, SCREEN7_BITMAP
                ld   bc, SCREEN_FRAME_LEN
                ldir
                ld   hl, PRES_MASK
                ld   b, PRES_LEN
                xor  a
.c:             ld   (hl), a
                inc  l
                djnz .c
                ld   (PRES_ANY), a
                ld   hl, HUD_PW
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a                   ; HUD rows are in sync too
                dec  a
                ld   (PRES_RMIN), a            ; $FF: no marked row
                ld   a, P7FFD_SCREEN7
                jp   set_screen

;==============================================================================
; init_kbd_mirror — all released.  Clobbers: A, B, HL
;==============================================================================
init_kbd_mirror:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, KBD_RELEASED
.r:             ld   (hl), a
                inc  hl
                djnz .r
                ret

;==============================================================================
; BOOT-TIME GENERATOR (prototype §5.1/§5.2). Per frame: get the unshifted
; right-facing source out of banks 1/3 (ZX0_SOURCES: unpack its block into
; GEN_SCRATCH once, zx0_frame; raw: copy_virt to GEN_SRC), then emit each needed variant
; (facing x shift) into the pool banks 0/4/6 with a bump allocator. No variant
; straddles a bank (allocator skips to the next bank). ~70-100 T/output byte.
;==============================================================================
pool_banks:     DB BANK_POOL0, BANK_POOL1, BANK_POOL2

; alloc_reset — pool empty; starts a generator session.   Clobbers: A, HL
; A generator SESSION = alloc_reset/alloc_restore .. the next build_room_map.
; Both entry points drop the ZX0 block cache (GEN_ZBLK): GEN_SCRATCH aliases
; the room maps, so a cached block never outlives its session (A5 review).
alloc_reset:
                xor  a
                ld   (ALLOC_IDX), a
                ld   (GEN_OVERFLOW), a
                ld   hl, BANK_WINDOW
                ld   (ALLOC_PTR), hl
    IF ZX0_SOURCES
                ld   l, a
                ld   h, a
                ld   (GEN_ZBLK), hl            ; no cached block
    ENDIF
                ret

; alloc_mark / alloc_restore — remember/rewind the pool top (hero regen).
; alloc_restore starts a session too (drops GEN_ZBLK). Clobbers: A, HL
alloc_mark:
                ld   a, (ALLOC_IDX)
                ld   (ALLOC_MARK_IDX), a
                ld   hl, (ALLOC_PTR)
                ld   (ALLOC_MARK_PTR), hl
                ret
alloc_restore:
                ld   a, (ALLOC_MARK_IDX)
                ld   (ALLOC_IDX), a
                ld   hl, (ALLOC_MARK_PTR)
                ld   (ALLOC_PTR), hl
    IF ZX0_SOURCES
                ld   hl, 0
                ld   (GEN_ZBLK), hl            ; no cached block
    ENDIF
                ret

; alloc — reserve BC bytes. Out: A = bank, HL = addr, CF = 1 if the pool is full.
; Clobbers: A, DE, HL
alloc:
                ld   a, (ALLOC_IDX)
                cp   3
                ccf
                ret  c                         ; out of banks
                ld   hl, (ALLOC_PTR)
                push hl
                add  hl, bc                    ; end = ptr + size
                jr   nc, .fits                 ; <= $FFFF
                ld   a, h
                or   l
                jr   z, .fits                  ; exactly $10000 also fits
                pop  hl
                ld   hl, ALLOC_IDX              ; next bank, retry
                inc  (hl)
                ld   hl, BANK_WINDOW
                ld   (ALLOC_PTR), hl
                jr   alloc
.fits:
                ld   (ALLOC_PTR), hl
                ld   a, (ALLOC_IDX)
                ld   e, a
                ld   d, 0
                ld   a, h
                or   l
                jr   nz, .same
                ld   hl, BANK_WINDOW           ; ended exactly at $10000: the
                ld   (ALLOC_PTR), hl           ; next alloc opens the next bank
                ld   a, e                      ; (ptr 0 would alias the ROM)
                inc  a
                ld   (ALLOC_IDX), a
.same:          ld   hl, pool_banks
                add  hl, de
                ld   a, (hl)                   ; A = bank of THIS allocation
                pop  hl                        ; HL = start
                or   a                         ; CF = 0
                ret

; build_bitrev — BITREV_TAB[i] = i with bit order reversed.  Boot, ~20k T
build_bitrev:
                ld   hl, BITREV_TAB
.next:          ld   a, l
                ld   b, 8
                ld   c, 0
.bit:           rra
                rl   c
                djnz .bit
                ld   (hl), c
                inc  l
                jr   nz, .next
                ret

; copy_virt — copy BC bytes from VIRTUAL sprite-source address HL (banks 1/3,
; assembled at $8000..$FFFF) to DE (bank 2/5 RAM). Handles the $C000 straddle.
; Clobbers: A, BC, DE, HL
copy_virt:
                ld   a, h
                cp   BANK_WINDOW >> 8
                jr   nc, .hi                   ; $C000.. -> bank 3 as-is
                ; $8000..$BFFF -> bank 1 at +$4000; may run past into bank 3
                push bc
                push de
                push hl
                ld   a, BANK_SRC_LO
                call page_bank
                pop  hl
                pop  de
                pop  bc
                push hl                        ; avail = $C000 - HL
                ld   a, BANK_WINDOW >> 8
                sub  h
                ld   h, a
                xor  a
                sub  l
                ld   l, a
                jr   nc, .nb
                dec  h                         ; borrow
.nb:            ; HL = avail;  n1 = min(BC, avail)
                push hl
                or   a
                sbc  hl, bc                    ; avail - BC
                pop  hl
                jr   c, .split                 ; BC > avail
                pop  hl
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                ret
.split:         ; copy avail bytes from bank 1, then the rest from bank 3 @ $C000
                push bc                        ; total
                ld   b, h
                ld   c, l                      ; BC = avail
                pop  hl                        ; HL = total
                or   a
                sbc  hl, bc                    ; HL = rest
                ex   (sp), hl                  ; stack = rest, HL = virt src
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                push de
                ld   a, BANK_SRC_HI
                call page_bank
                pop  de
                pop  bc                        ; rest
                ld   hl, BANK_WINDOW
                ldir
                ret
.hi:
                push bc
                push de
                push hl
                ld   a, BANK_SRC_HI
                call page_bank
                pop  hl
                pop  de
                pop  bc
                ldir
                ret

;------------------------------------------------------------------------------
; gen_kind — generate every frame of kind A; a kind with 0 frames (the Rogue
; hole, unused ids) returns at once (djnz with B = 0 would run 256 frames).
; Clobbers: all but IX
;------------------------------------------------------------------------------
gen_kind:
                ld   h, (kind_tab + KT_FID0) >> 8   ; KT_FID0/KT_FCNT: same page
                add  a, KT_FID0 & $FF
                ld   l, a
                ld   a, (hl)                   ; first fid
                ld   c, a
                ld   a, l
                add  a, KT_FCNT - KT_FID0
                ld   l, a
                ld   b, (hl)                   ; count
                inc  b
                dec  b
                ret  z                         ; 0-frame kind: nothing to generate
.f:             push bc
                ld   a, c
                call gen_frame
                pop  bc
                inc  c
                djnz .f
                ret

;------------------------------------------------------------------------------
; gen_frame — generate all variants of frame A into the pool; fill FRT[A].
; ZX0_SOURCES: the frame is read from its block unpacked in GEN_SCRATCH, which
; aliases ROOM_MAP/NEXT_MAP — callable only while no room is built (boot, hero
; start; 3F: level start before build_room_map). A call while GAME_STATE is
; PLAYING/TRANSITION bumps GEN_TRAP (saturating; tests assert 0). The block
; cache (GEN_ZBLK) is valid for one generator session only: alloc_reset /
; alloc_restore drop it (every caller starts with one of them).
; Static data: frame_tab (bank 2: cols, H, offsets) + fdesc_tab (bank 5:
; block, frame address, flags) — no banked descriptor read, no copy_virt.
; Clobbers: all but IX.
;------------------------------------------------------------------------------
gen_frame:
                ld   (GEN_FID), a
                ld   a, (GAME_STATE)           ; GEN_SCRATCH guard (A3 carry-over)
                cp   GS_PLAYING
                jr   z, .trap
                cp   GS_TRANSITION
                jr   nz, .safe
.trap:          ld   hl, GEN_TRAP
                inc  (hl)
                jr   nz, .safe
                dec  (hl)                      ; saturate at 255
.safe:
                ; FRT[fid] = all NONE
                call frt_ptr_cur               ; HL = FRT + fid*16 (A was clobbered)
                ld   b, 4
.clr:           ld   (hl), FRT_NONE
                inc  hl
                inc  hl
                inc  hl
                djnz .clr
                ; read the static entries
                ld   a, (GEN_FID)
                call ft_ptr                    ; HL = frame_tab + fid*4 (FT_COLS)
                ld   a, (hl)
                ld   (GEN_COLS), a
                inc  hl                        ; FT_H
                ld   a, (hl)
                ld   (GEN_H), a
                ; HL = fdesc_tab + fid*5
                ld   a, (GEN_FID)
                ld   l, a
                ld   h, 0
                ld   e, l
                ld   d, h
                add  hl, hl
                add  hl, hl
                add  hl, de
                ld   de, fdesc_tab
                add  hl, de
                ld   e, (hl)                   ; FD_BLK
                inc  hl
                ld   d, (hl)                   ; DE = virt block (raw: virt src)
                inc  hl
                ld   c, (hl)                   ; FD_FRM
                inc  hl
                ld   b, (hl)                   ; BC = frame in GEN_SCRATCH
                inc  hl
                ld   a, (hl)                   ; FD_FLAGS
                ld   (GEN_FLAGS), a
    IF ZX0_SOURCES
                call zx0_frame                 ; HL = frame in GEN_SCRATCH (no copy)
    ELSE
                ; source bytes = cols * H * 2
                push de
                call gen_rowbytes              ; A = cols*2
                ld   c, a
                ld   a, (GEN_H)
                call mul8                      ; HL = A * C
                ld   b, h
                ld   c, l
                pop  hl                        ; HL = virt src
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC
    ENDIF
                ; --- right facing --- (GEN_BASE = the unmirrored source until
                ; mirror_src has read it; gen_variant only reads it)
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFR
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                xor  a
                call gen_facing
                ; --- left facing ---
                ld   a, (GEN_FLAGS)
                and  FF_SYM
                jr   z, .mirror
                call frt_ptr_cur               ; SYM: left = right (no copy)
                ld   d, h
                ld   e, l
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de                        ; DE = variant 2
                ld   bc, 6
                ldir
                ret
.mirror:
                call mirror_src
                ld   hl, GEN_MIR
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFL
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                ld   a, 2
                jp   gen_facing

; gen_facing — A = variant base (0 right / 2 left). Uses GEN_* state.
gen_facing:
                ld   (GEN_VAR), a
                ld   a, (GEN_FLAGS)
                and  FF_MOTION
                jr   z, .stat
                xor  a                         ; MOTION: shift 0 and shift 4
                call gen_variant
                ld   hl, GEN_VAR
                inc  (hl)
                ld   a, 4
                jp   gen_variant
.stat:
                ld   a, (GEN_OFF)
                and  7                         ; anchor implies the one shift
                jp   z, gen_variant            ; shift 0 -> variant base
                ld   hl, GEN_VAR
                inc  (hl)                      ; shift 4 -> base + 1
                ld   a, 4
                jp   gen_variant

; gen_variant — emit GEN_BASE shifted by A (0/4) into the pool as variant
; GEN_VAR of GEN_FID. Clobbers: all but IX.
gen_variant:
                ld   (GEN_SHIFT), a
                ; out bytes = (cols + (shift?1:0)) * 2 * H
                ld   a, (GEN_COLS)
                ld   c, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   z, .n
                inc  c
.n:             sla  c                         ; C = out row bytes
                ld   a, (GEN_H)
                call mul8                      ; HL = size
                ld   b, h
                ld   c, l
                call alloc                     ; A = bank, HL = addr
                jr   nc, .ok
                ld   a, 1
                ld   (GEN_OVERFLOW), a
                ret
.ok:
                push hl
                push af
                ; FRT[fid][var] = bank, addr
                call frt_ptr_cur
                ld   a, (GEN_VAR)
                ld   e, a
                add  a, a
                add  a, e
                ld   e, a
                ld   d, 0
                add  hl, de
                pop  af
                ld   (hl), a
                inc  hl
                pop  de                        ; DE = dest addr
                ld   (hl), e
                inc  hl
                ld   (hl), d
                push de
                call page_bank                 ; A = bank
                pop  de
                ld   hl, (GEN_BASE)
                ld   a, (GEN_H)
                ld   b, a
.row:
                push bc
                ld   a, (GEN_COLS)
                ld   b, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   nz, .sh
.cp:            ld   a, (hl)                   ; shift 0: straight copy
                ld   (de), a
                inc  hl
                inc  de
                ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  de
                djnz .cp
                jr   .rowdone
.sh:            ld   c, $FF                    ; prev mask  (transparent feed)
                ld   a, 0
                ld   (TMP0), a                 ; prev data  (empty feed)
.shc:           ld   a, c
                rrca
                rrca
                rrca
                rrca
                and  $F0                       ; prev_m << 4
                ld   c, a
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                and  $0F                       ; m >> 4
                or   c
                ld   (de), a
                inc  de
                ld   c, (hl)                   ; prev_m = m
                inc  hl
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (TMP1), a
                ld   a, (hl)
                ld   (TMP0), a                 ; prev_d = d
                rrca
                rrca
                rrca
                rrca
                and  $0F
                push hl
                ld   hl, TMP1
                or   (hl)
                pop  hl
                ld   (de), a
                inc  de
                inc  hl
                djnz .shc
                ld   a, c                      ; spill column
                rrca
                rrca
                rrca
                rrca
                and  $F0
                or   $0F
                ld   (de), a
                inc  de
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (de), a
                inc  de
.rowdone:
                pop  bc
                djnz .row
                ret

; mirror_src — (GEN_BASE) -> GEN_MIR, each row's columns reversed + bit-reversed.
; GEN_BASE = GEN_SRC (raw sources) or the frame inside GEN_SCRATCH (ZX0).
; Clobbers: A, BC, DE, HL
mirror_src:
                ld   hl, (GEN_BASE)
                ld   de, GEN_MIR
                ld   a, (GEN_H)
                ld   b, a
.row:           push bc
                push de
                call gen_rowbytes              ; A = cols*2
                ld   c, a
                ld   b, 0
                ex   de, hl
                add  hl, bc                    ; HL = dest row end
                ex   de, hl
                ld   a, (GEN_COLS)
                ld   b, a
.col:           dec  de
                dec  de                        ; DE = dest pair (from the right)
                push de
                ld   a, (hl)                   ; mask
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                ld   (de), a
                pop  hl
                ld   a, (hl)                   ; data
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                inc  de
                ld   (de), a
                pop  hl
                pop  de
                djnz .col
                pop  de
                call gen_rowbytes
                add  a, e
                ld   e, a
                jr   nc, .nc
                inc  d
.nc:            pop  bc
                djnz .row
                ret

gen_rowbytes:   ld   a, (GEN_COLS)
                add  a, a
                ret

; mul8 — HL = A * C (unsigned 8x8).  Clobbers: A, B, DE, HL
mul8:
                ld   hl, 0
                ld   d, 0
                ld   e, c
                ld   b, 8
.m:             add  hl, hl
                rla
                jr   nc, .n
                add  hl, de
.n:             djnz .m
                ret

    IF ZX0_SOURCES
;------------------------------------------------------------------------------
; zx0_frame — DE = VIRTUAL address of the frame's packed block (FD_BLK), BC =
; the frame's address in GEN_SCRATCH (FD_FRM). Unpacks the block into
; GEN_SCRATCH unless it is already there (GEN_ZBLK = one-block cache: blocks
; hold 1-4 consecutive fids of one kind, so gen_kind unpacks each block
; exactly once). The tool guarantees no packed block straddles virtual $C000,
; so the whole stream is in one bank's $C000 window.
; Out: HL = the frame's raw bytes (cols*H*2, in GEN_SCRATCH). $C000 = the
; source bank if a block was unpacked (else unchanged). Clobbers: A, BC, DE, HL.
; Cost: cache hit ~110 T (A5: ~0.4k T incl. the banked 4-B descriptor
; copy_virt, now gone); unpack (once per block) ~1.6 B packed -> raw at
; roughly LDIR speed + Elias bits, e.g. ~25-45k T for a 1.1-1.4 KB block.
;------------------------------------------------------------------------------
zx0_code:
zx0_frame:
                push bc                        ; -> HL on exit
                ld   hl, (GEN_ZBLK)
                or   a
                sbc  hl, de
                jr   z, .have                  ; already unpacked
                ex   de, hl                    ; HL = virt block
                ld   (GEN_ZBLK), hl
                ld   a, h
                cp   BANK_WINDOW >> 8
                ld   a, BANK_SRC_HI            ; (ld keeps CF)
                jr   nc, .pg                   ; virt $C000.. = bank 3 as-is
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a                      ; virt $8000.. = bank 1 at +$4000
                ld   a, BANK_SRC_LO
.pg:            push hl
                call page_bank
                pop  hl
                ld   de, GEN_SCRATCH
                call dzx0_standard
.have:          pop  hl                        ; HL = frame in GEN_SCRATCH
                ret
                INCLUDE "dzx0_standard.asm"
zx0_code_end:
                ASSERT zx0_code_end - zx0_code <= ZX0_BUDGET
    ENDIF

; frt_ptr — HL = FRT + A*16 ; frt_ptr_cur uses GEN_FID.  Clobbers: A, DE, HL
;------------------------------------------------------------------------------
; sel_frt_copy — CF = 0: save the two select idles' FRT rows (boot pool,
; below the alloc mark) to SEL_FRT_SAVE; CF = 1: restore them. start_game's
; gen_kind regenerates the chosen hero's frames ABOVE the mark and re-points
; their FRT rows (incl. its select idle) there; the next hero's gen_kind then
; overwrites that pool region, so without the restore the select screen drew
; whatever the last game left there.  ~1.2k T.  Clobbers: A, BC, DE, HL, TMP0
;------------------------------------------------------------------------------
sel_frt_copy:
                sbc  a, a                      ; A = $FF restore / 0 save
                ld   (TMP0), a
                ld   hl, sel_tab
                ld   de, SEL_FRT_SAVE
                ld   b, 2
.l:             push bc
                push hl
                push de
                ld   a, (hl)                   ; fid
                call frt_ptr                   ; HL = FRT row (DE clobbered)
                pop  de                        ; DE = save cursor
                ld   a, (TMP0)
                or   a
                jr   z, .cp
                ex   de, hl                    ; restore: save -> FRT
.cp:            ld   bc, FRT_STRIDE
                ldir                           ; keeps Z
                jr   z, .nx
                ex   de, hl                    ; DE = save cursor again
.nx:            pop  hl
                ld   bc, 5                     ; sel_tab stride
                add  hl, bc
                pop  bc
                djnz .l
                ret

frt_ptr_cur:
                ld   a, (GEN_FID)
frt_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, FRT
                add  hl, de
                ret

;==============================================================================
; init_tiles — TILE_GLYPHS / TILE_ATTRS in RAM. Stand-ins (below, this file) +
; bg_tiles_floor; potion/chest/torch glyphs extracted from the sheet's item
; frames (masked source: data byte = offset 1 of each [mask,data] pair).
; Clobbers: all but IX.  Boot only.
;==============================================================================
init_tiles:
                ; all TILE_IDS glyphs + attrs zeroed (A6: 64 ids; the per-level
                ; half 32..63 stays blank until 3B loads a level tileset)
                ld   hl, TILE_GLYPHS
                ld   de, TILE_GLYPHS + 1
                ld   bc, TILE_IDS * 8 - 1
                ld   (hl), 0
                ldir
                ld   hl, TILE_ATTRS
                ld   de, TILE_ATTRS + 1
                ld   bc, TILE_IDS - 1
                ld   (hl), 0
                ldir
                ld   hl, tile_attr_src
                ld   de, TILE_ATTRS
                ld   bc, T_COUNT
                ldir
                ld   hl, tile_src_tab
                ld   b, TILE_SRC_N
.ts:            push bc
                ld   a, (hl)                   ; tile id
                inc  hl
                add  a, a
                add  a, a
                add  a, a
                ld   e, a
                ld   d, TILE_GLYPHS >> 8       ; DE = glyph slot
                ld   a, (hl)                   ; banked?
                inc  hl
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                push hl
                ld   h, b
                ld   l, c
                ld   bc, 8
                or   a
                jr   z, .img
                call copy_virt                 ; artist tile in bank 1/3
                jr   .tn
.img:           ldir                           ; engine stand-in in the image
.tn:            pop  hl
                pop  bc
                djnz .ts
                ; items from the sheet (banked source -> GEN_SRC, then pick data)
                ld   hl, item_potion
                ld   bc, item_potion_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_POTION
                ld   c, 2                      ; 1 col: stride 2
                call .pick
                ld   hl, item_torch
                ld   bc, item_torch_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_TORCH_T
                ld   c, 2
                call .pick
                ld   hl, GEN_SRC + 1 + 16
                ld   a, T_TORCH_B
                ld   c, 2
                call .pick
                ld   hl, item_chest
                ld   bc, item_chest_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_CHEST_TL
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 3
                ld   a, T_CHEST_TR
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 1 + 32
                ld   a, T_CHEST_BL
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 3 + 32
                ld   a, T_CHEST_BR
                ld   c, 4
                jp   .pick
.pick:          ; 8 bytes from HL with stride C into tile A
                add  a, a
                add  a, a
                add  a, a
                ld   e, a
                ld   d, TILE_GLYPHS >> 8
                ld   b, 8
                push bc
                ld   b, 0
.pk:            ld   a, (hl)
                ld   (de), a
                inc  e
                add  hl, bc
                ex   (sp), hl
                dec  h
                ex   (sp), hl
                jr   nz, .pk
                pop  bc
                ret

;------------------------------------------------------------------------------
; Stand-in tile glyphs (engine placeholders until the artist's PLATFORM/WALL/
; LADDER_L/M/R/ZAP tiles land — prototype §10.2 #33-41). PLATFORM reuses
; assets/gfx/bg_tiles.asm (bg_tiles_floor). Items (potion/chest/torch) are
; extracted at boot from the sheet frames (item_*), see init_tiles.
;------------------------------------------------------------------------------
gl_wall:        DB $FF,$84,$84,$84,$FF,$10,$10,$10   ; brick course
gl_lad_l:       DB $C0,$FF,$C0,$C0,$C0,$FF,$C0,$C0   ; left rail + rungs (every 4 px)
gl_lad_m:       DB $00,$FF,$00,$00,$00,$FF,$00,$00   ; rungs
gl_lad_r:       DB $03,$FF,$03,$03,$03,$FF,$03,$03   ; right rail + rungs
gl_zap1:        DB $00,$00,$08,$D4,$23,$00,$00,$00   ; bolt, staff row
gl_zap2:        DB $00,$00,$10,$2B,$C4,$00,$00,$00

; TILE_ATTRS source (copied to the page-aligned RAM table at boot)
tile_attr_src:  DB ATTR_AIR, ATTR_FLOOR, ATTR_WALL, ATTR_FLOOR
                DB ATTR_LADDER, ATTR_LADDER, ATTR_LADDER
                DB ATTR_LADDER, ATTR_LADDER, ATTR_LADDER
                DB ATTR_POTION, ATTR_CHEST, ATTR_CHEST, ATTR_CHEST, ATTR_CHEST
                DB ATTR_TORCH, ATTR_TORCH, ATTR_ZAP, ATTR_ZAP
                DB ATTR_FLOOR, ATTR_FLOOR
                ASSERT $ - tile_attr_src == T_COUNT
                ASSERT T_COUNT <= TILE_COMMON  ; init_tiles/.pick/zap: id*8 < 256

;------------------------------------------------------------------------------
; Tile glyph sources, stand-in rule: the artist's tile (banked sheet source,
; prototype §10.2 #33-41) if its label exists, else the engine stand-in above.
;   DB tile_id, banked(1)/image(0) ; DW src
;------------------------------------------------------------------------------
    MACRO TSRC q_id, q_art, q_std
      IF EXIST q_art
        DB q_id, 1
        DW q_art
      ELSE
        DB q_id, 0
        DW q_std
      ENDIF
    ENDM
tile_src_tab:
                TSRC T_PLAT,    tiles_bg_platform,      bg_tiles_floor
                TSRC T_BRICK,   tiles_bg_wall,          gl_wall
                TSRC T_WALLF,   tiles_bg_wall,          gl_wall
                TSRC T_LAD_L,   tiles_bg_ladder_l,      gl_lad_l
                TSRC T_LAD_M,   tiles_bg_ladder_m,      gl_lad_m
                TSRC T_LAD_R,   tiles_bg_ladder_r,      gl_lad_r
                TSRC T_HOLE_L,  tiles_bg_ladder_l,      gl_lad_l
                TSRC T_HOLE_M,  tiles_bg_ladder_m,      gl_lad_m
                TSRC T_HOLE_R,  tiles_bg_ladder_r,      gl_lad_r
                TSRC T_ZAP1,    tiles_fx_zap1,          gl_zap1
                TSRC T_ZAP2,    tiles_fx_zap2,          gl_zap2
                TSRC T_END_L,   tiles_bg_platform_end_l, bg_tiles_floor
                TSRC T_END_R,   tiles_bg_platform_end_r, bg_tiles_floor
TILE_SRC_N      EQU ($ - tile_src_tab) / 4

; bg_tiles_floor: the PLATFORM stand-in glyph (init_tiles only)
                INCLUDE "../assets/gfx/bg_tiles.asm"

;==============================================================================
; fdesc_tab — frame descriptors (A6), FDESC_STRIDE (5) B per fid, read only
; by gen_frame: FD_BLK (ZX0: virtual packed-block address / raw: virtual
; frame address), FD_FRM (ZX0: GEN_SCRATCH + in-block offset), FD_FLAGS.
; Generated from src/frames.asm (the same list as frame_tab). MUST stay the
; last thing in the cold block (ASSERTed): it is the part that grows.
;==============================================================================
fdesc_tab:
FRM_EMIT = FRM_DESC
                INCLUDE "frames.asm"
FDESC_COUNT     EQU FCTR
fdesc_end:
                ASSERT fdesc_end - fdesc_tab == FDESC_COUNT * FDESC_STRIDE
