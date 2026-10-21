;==============================================================================
; boot6.asm — 3E-T1 (memory levers (a) + (d)): the BOOT BLOCK. Boot-only code
; and the boot-only data it copies, assembled at the TOP of pool bank 6
; (BOOT6_ADDR = $10000 - BOOT6_LEN, main.asm) and loaded as its own headerless
; tape block (the last one, `start`'s table). Run once per power-on by `boot`
; through farb (C = BANK_BOOT6), BEFORE the pre-shift pool is generated: the
; boot pool (monsters + the two select idles) ends in bank 4, and only a hero
; start (start_game) reaches the bank-6 tail — after that these bytes are pool
; frames. So nothing here may be read after boot (verified per item, see
; docs/memory-map.md "Boot block"); no SMC, no data writes into the block
; (tests/zx0_pool.py seeds its reference from the snapshot's bank 6).
;
; Rules: bank 6 stays paged while this code runs (farb), so the data is read
; in place (no copy_virt / GEN_SRC staging) and the callees must not page
; $C000 (clear_screen, init_kbd_mirror: bank 5 low RAM, they page nothing).
;   boot6_init   boot, under DI: IM 2 install + the power-on state
;   boot6_tiles  boot: common tiles + ornament, HOT_COPY image, planar FONT6
; Was: low RAM (isr_install, isr_image, boot's state init, keytab_defaults)
; and bank 7 (init_tiles, panel_boot) + bank-1 vdata (tiles_common, orn_glyphs,
; panel_hot_img, font6x8).
;==============================================================================

;------------------------------------------------------------------------------
; boot6_init — farb from boot, interrupts off. A8 IM 2 setup (was
; isr_install): fill the 257-B vector table (every byte ISR_VEC_BYTE, so
; whatever the floating bus puts on the data bus the CPU fetches ISR_ADDR),
; copy the ISR image to ISR_ADDR, I = the table page, IM 2; then the power-on
; state (was inline in boot). Interrupts stay disabled: boot's EI comes after
; (PORT_7FFD_SHADOW is valid: boot paged BANK_POOL0 before the farb).
; Placement + protocol: docs/memory-map.md "Interrupts (A8)".
; Clobbers: A, BC, DE, HL.   ~6.8k T (IM 2) + ~33k T (clear_screen etc.)
;------------------------------------------------------------------------------
boot6_init:
                ld   hl, ISR_VEC_TABLE
                ld   de, ISR_VEC_TABLE + 1
                ld   bc, ISR_VEC_LEN - 1
                ld   (hl), ISR_VEC_BYTE
                ldir
                ld   hl, isr_image
                ld   de, ISR_ADDR
                ld   bc, ISR_LEN
                ldir
                ld   a, ISR_VEC_TABLE >> 8
                ld   i, a
                im   2
                xor  a
                out  (PORT_BORDER), a
                ld   (INPUT_SRC), a
                ld   (JOY_MODE), a             ; C3-1: JM_KEYS until the menu says
                ld   (JOY_MIRROR), a           ; otherwise; nothing held
                ld   (STICK), a
                ld   (STICK_OLD), a
                ld   (ANIM_FREEZE), a
                ld   (ANIM_TRACE_IDX), a
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (GEN_TRAP), a             ; since boot (like GEN_OVERFLOW)
    IF PHASE_SHIFT
                ld   (PHASE_TRAP), a           ; since boot (walk phase lock trap)
    ENDIF
                ld   (TURN_PHASE), a
                ld   (PEND_DMG_COUNT), a
                ld   (CUR_ROOM), a
                ld   (YIELD_FLAG), a
                ld   (PANEL_DIRTY), a          ; B3B-11: no panel work / log until
                ld   (LOG_QN), a               ; panel_init (start_game)
                ld   hl, HUD4_PW               ; text rows: nothing pending
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                ld   hl, 0
                ld   (OVERRUN_COUNT), hl
                ld   (TICK_COUNTER), hl
                ld   (TURN_COUNTER), hl
                ld   (MUS_REQ), hl             ; SND-2 mailbox (before EI: the ISR
                ld   (MUS_STATE), hl           ; reads it): no tune, no shot, idle,
                ld   (SFX_REQ), a              ; nothing sounding (A = 0)
                ld   (SFX_NEXT), a             ; SND-5: no deferred effect
                ASSERT MUS_SHOT == MUS_REQ + 1 && MUS_CUR == MUS_STATE + 1
                ld   a, SND_ALL                ; game.md §3.6: ALL ON per power-on
                ld   (SND_MODE), a             ; (only boot writes it; new_game never)
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
                ld   hl, keytab_defaults       ; C3-1: Q / A / O / P / SPACE
                ld   de, KEYTAB
                ld   bc, KEYTAB_N * KEYTAB_STRIDE
                ldir
                ld   a, ATTR_HUD
                call clear_screen
                ld   hl, P_ENTITIES            ; nothing drawn / alive yet
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), 0
                ldir
                ret

;------------------------------------------------------------------------------
; boot6_tiles — farb from boot (after EI). The common tile set ids 0..31
; (B3B-2 tiles_common: glyphs + depth-1 attrs; level_load_tiles re-themes the
; floor / wall ids per level) into TILE_GLYPHS / TILE_ATTRS, the row-17
; ornament into ORN_GLYPHS, the panel hot image into HOT_COPY, then the planar
; FONT6 (level_defs.asm) from the char-major font6x8 with glyph bits 1..0
; masked off (no glyph can bleed into the next char, print6). The data is one
; run (ASSERTed below), so HL just continues. Was init_tiles + panel_boot
; (bank 7, read through copy_virt3 + GEN_SRC staging).
; Clobbers: A, BC, DE, HL.   ~30k T (boot only)
;------------------------------------------------------------------------------
boot6_tiles:
                ld   hl, tiles_common_glyphs
                ld   de, TILE_GLYPHS
                ld   bc, TILE_COMMON * 8
                ldir
                ld   de, TILE_ATTRS            ; HL = tiles_common_attrs
                ld   c, TILE_COMMON            ; B = 0 after the LDIR
                ldir
                ld   de, ORN_GLYPHS            ; HL = orn_glyphs
                ld   c, ORN_COUNT * 8
                ldir
                ld   de, HOT_COPY              ; HL = panel_hot_img
                ld   bc, PANEL_HOT_LEN
                ldir
                ld   c, FONT6_FIRST            ; HL = font6x8; C = char code
.ch:            ld   d, FONT6 >> 8
                ld   b, FONT6_PAGES
.ln:            ld   e, c                      ; even line: window A (offset = code)
                ld   a, (hl)
                and  $FC
                ld   (de), a
                inc  hl
                ld   a, c
                add  a, FONT6_WB               ; odd line: window B
                ld   e, a
                ld   a, (hl)
                and  $FC
                ld   (de), a
                inc  hl
                inc  d
                djnz .ln
                inc  c
                ld   a, c
                cp   FONT6_FIRST + FONT6X8_COUNT
                jr   nz, .ch
                ret

;==============================================================================
; boot-only data (read in place by the two routines above)
;==============================================================================
keytab_defaults:                               ; C3-1: boot -> KEYTAB (hero_defs.asm)
                KEYTAB_DEFAULTS

;------------------------------------------------------------------------------
; isr — IM 2 handler, runs at ISR_ADDR (bank 2: uncontended, always mapped),
; once per frame (50 Hz), interrupts disabled on entry. This is its load
; image (boot6_init copies it; 3E-T1: was in low RAM).
;  1. SYS_FRAMES += 1 exactly as the ROM's MASK-INT (3-byte counter; the tick
;     pacing reads the low byte) — unless ISR_ROM_CHAIN, where the ROM does it.
;  2. Pages BANK_AY at $C000 by OUT only: (PORT_7FFD_SHADOW & ~7) | BANK_AY
;     keeps the shadow's screen bit 3 and ROM bit 4; the shadow is never
;     written. Calls AY_PLAY (bank 3).
;  3. Re-OUTs PORT_7FFD_SHADOW as it is NOW (not a saved port value). Race
;     with the main code's "shadow first, then OUT" (page_bank / set_screen):
;     an interrupt between the two leaves the port already at the new value,
;     and the main code's own OUT then rewrites the same byte. No DI needed.
; Saves every register it or the player may touch: AF, BC, DE, HL, IX, IY
; (+ the alternate set if ISR_SAVE_ALT). Stack: 12 B + AY_PLAY's 6 B (CALL 2 + player 4) (+8 alt).
; Cost (measured): ISR own instructions 315 T + 19 T acknowledge = 334 T overhead,
; + AY_PLAY (SND-2: the dispatcher + WZM player, idle ~0.2k .. worst ~5k T), in the
; top border (docs/memory-map.md "Interrupts (A8)").
;------------------------------------------------------------------------------
isr_image:
                DISP ISR_ADDR
isr:
                push af
                push hl
    IF !ISR_ROM_CHAIN
                ld   hl, (SYS_FRAMES)
                inc  hl
                ld   (SYS_FRAMES), hl
                ld   a, h
                or   l
                jr   nz, .frames
                ld   hl, SYS_FRAMES + 2        ; ROM: INC (IY+$40)
                inc  (hl)
.frames:
    ENDIF
                push bc
                push de
                push ix
                push iy
    IF ISR_SAVE_ALT
                ex   af, af'
                push af
                exx
                push bc
                push de
                push hl
    ENDIF
                ld   a, (PORT_7FFD_SHADOW)
                and  ~7 & $FF                  ; keep screen bit 3 + ROM bit 4
                or   BANK_AY
                ld   bc, PORT_7FFD
                out  (c), a                    ; shadow untouched
.page:          call AY_PLAY                   ; bank 3, contended fetches
                ld   a, (PORT_7FFD_SHADOW)     ; the CURRENT shadow (see 3. above)
                ld   bc, PORT_7FFD
                out  (c), a
.done:                                         ; test probe: port == shadow here
    IF ISR_SAVE_ALT
                pop  hl
                pop  de
                pop  bc
                exx
                pop  af
                ex   af, af'
    ENDIF
                pop  iy
                pop  ix
                pop  de
                pop  bc
                pop  hl
                pop  af
    IF ISR_ROM_CHAIN
                jp   ROM_ISR                   ; FRAMES, keyboard scan, EI, RET (IY!)
    ELSE
                ei
                ret
    ENDIF
isr_end:
                ENT
ISR_LEN         EQU isr_end - isr
                ASSERT ISR_ADDR + ISR_LEN <= ISR_ADDR_END
                ASSERT (ISR_ADDR >> 8) == ISR_VEC_BYTE          ; vector byte = both address bytes
                ASSERT ISR_VEC_TABLE + ISR_VEC_LEN <= ISR_ADDR
                ASSERT (ISR_VEC_TABLE & $FF) == 0
                ASSERT (ISR_VEC_TABLE >> 8) >= $80 && (ISR_VEC_TABLE >> 8) < $C0  ; I: bank 2
                ASSERT ISR_ADDR_END <= STACK_BOTTOM

; the boot6_tiles run: tiles_common (glyphs, attrs), orn_glyphs, the HOT_COPY
; image, font6x8 — contiguous, in this order (HL continues across them)
                INCLUDE "../assets/gfx/tiles/tiles_common.asm" ; -> TILE_GLYPHS / TILE_ATTRS 0..31
                INCLUDE "../assets/gfx/panel/panel_orn.asm"    ; -> ORN_GLYPHS
                INCLUDE "panel_hot.asm"                       ; -> HOT_COPY
                INCLUDE "../assets/gfx/fonts/font6x8.asm"     ; -> FONT6 planes
                ASSERT tiles_common_attrs == tiles_common_glyphs + TILE_COMMON * 8
                ASSERT TILES_COMMON_LEN == TILE_COMMON * 9
                ASSERT orn_glyphs == tiles_common_glyphs + TILES_COMMON_LEN
                ASSERT orn_glyphs_end - orn_glyphs == ORN_COUNT * 8
                ASSERT panel_hot_img == orn_glyphs_end
                ASSERT font6x8 == panel_hot_img + PANEL_HOT_LEN
                ASSERT FONT6X8_COUNT == 96 && FONT6X8_STRIDE == 8 && FONT6_PAGES * 2 == 8
                ASSERT $ - font6x8 == FONT6X8_COUNT * FONT6X8_STRIDE
