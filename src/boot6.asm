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
;                (RECLAIM-D: the MEM-FT frame_tab -> FRT step is instr_ovl.asm in_ft)
;   boot6_wait   boot: the picture's key wait + D0 set-up (INSTR-BUILD overlay, bank-4 BOOT4 stream)
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
    IF ISR_SAVE_ALT
                ld   hl, isr_alt_image
                ld   de, ISR_ALT_ADDR
                ld   bc, ISR_ALT_LEN
                ldir
    ENDIF
                ld   a, ISR_VEC_TABLE >> 8
                ld   i, a
                im   2
                xor  a                         ; (the border and the screen are the loading
                ld   (INPUT_SRC), a            ; picture's: boot6_wait leaves them alone)
                ld   (JOY_MODE), a             ; C3-1: JM_KEYS until the menu says
                ld   (JOY_MIRROR), a           ; otherwise; nothing held
                ld   (STICK), a
                ld   (STICK_OLD), a
                ld   (ANIM_FREEZE), a
    IF ANIM_TRACE_ON
                ld   (ANIM_TRACE_IDX), a
    ENDIF
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (GEN_TRAP), a             ; since boot (like GEN_OVERFLOW)
                ld   (SEQ_TRAP), a             ; since boot (sequence cache trap)
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
                ld   a, MUS_LAMENT             ; the title tune from the first EI: it plays over
                ld   (MUS_REQ), a              ; the loading picture; menu_run asks for the same
                                               ; id = no restart
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   a, 1
                ld   (INPUT_REPEAT), a         ; play default: held keys repeat
                ld   a, GS_BOOT
                ld   (GAME_STATE), a
    IF ANIM_TRACE_ON
                ld   hl, ANIM_TRACE
                ld   de, ANIM_TRACE + 1
                ld   bc, ANIM_TRACE_LEN - 1
                ld   (hl), $FF
                ldir
    ENDIF
                call init_kbd_mirror
                ld   hl, keytab_defaults       ; C3-1: Q / A / O / P / SPACE
                ld   de, KEYTAB
                ld   bc, KEYTAB_N * KEYTAB_STRIDE
                ldir
                ld   hl, P_ENTITIES            ; nothing drawn / alive yet
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), 0
                ldir
                ld   hl, DN_ZCOL               ; D3-11: the number window's zero pads (a FONT6
                ld   b, 24                     ; hole, runtime RAM: garbage after a tape load);
.zc:            ld   (hl), c                   ; only its middle 8 B are written after this
                inc  l                         ; (C = 0 after the LDIR)
                djnz .zc
                ld   hl, DN_KEY                ; D3-11: the spawn queue empty (garbage after a
                ld   b, P_MAX_ENT              ; tape load: dn_q2 may run before the first scan)
.dk:            ld   (hl), $FF
                inc  l
                djnz .dk
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
                ret                            ; RECLAIM-D: boot6_ft (frame_tab -> the FRT rows)
                                               ; is instr_ovl.asm in_ft now (its stream: bank 0)

;------------------------------------------------------------------------------
; boot6_wait — farb from boot after boot6_tiles, BEFORE the boot pool: the
; INSTR-BUILD overlay (instr_ovl.asm, unpacked from the bank-4 BOOT4 block into GEN_SCRATCH):
; the loading picture (L3d SCREEN$, still on the bank-5 screen) + "PRESS ANY
; KEY" with the title tune until a key (BOOT-ANYKEY, GS_ANYKEY; ITEM-INFO: no
; HOW TO PLAY pages), then the D0 set-up. Returns to boot (gen_idles, menu);
; ovl_run hands bank 6 back for farb's return.   Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
boot6_wait:
                ld   hl, instr_zx0
                ld   c, BANK_INSTR
                ld   de, INSTR_ORG
                jp   ovl_run

;==============================================================================
; boot-only data (read in place by the two routines above)
;==============================================================================
keytab_defaults:                               ; C3-1: boot -> KEYTAB (hero_defs.asm)
                KEYTAB_DEFAULTS

;------------------------------------------------------------------------------
; isr — IM 2 handler, runs at ISR_ADDR (bank 2: uncontended, always mapped),
; once per frame (50 Hz), interrupts disabled on entry. This is its load
; image (boot6_init copies it; 3E-T1: was in low RAM).
;  0. C-T3 (SP-safe, option C): the handler never pushes on the interrupted
;     stack. Entry swaps the return address out of the word the CPU's own
;     push just wrote ((S..S+1), S = interrupted SP - 2), writes BC back over
;     that word and switches to its own stack ISR_STK; the exit reloads SP =
;     S + 2 and leaves by `jp` (SMC). So an interrupt during a pop-based blit
;     (SP walking up through the sprite pool, BC = the word just popped =
;     the word at S: the "word below SP == BC" invariant, conventions.md
;     "Interrupts") leaves the pool byte-identical, and the ISR's own
;     pushes land in bank 2, not in whatever bank is paged at $C000.
;     The write-back is UNCONDITIONAL (no "in a blit" flag): outside a blit
;     the word below SP is free stack — nothing in the game keeps live data
;     below SP (the only `ld sp` sites: boot, levelgen LG_SP, bank7 .quit) —
;     so replacing the stale return address there with BC is harmless, and a
;     flag would cost a test on every ISR plus a store pair around every blit.
;     It runs first, before step 2 pages BANK_AY: the word at S may be in the
;     pool bank at $C000 (a frame at $C000 makes S = $BFFE, DH_EFF scratch).
;  1. SYS_FRAMES += 1 exactly as the ROM's MASK-INT (3-byte counter; the tick
;     pacing reads the low byte).
;  2. Pages BANK_AY at $C000 by OUT only: (PORT_7FFD_SHADOW & ~7) | BANK_AY
;     keeps the shadow's screen bit 3 and ROM bit 4; the shadow is never
;     written. Calls AY_PLAY (bank 3).
;  3. Re-OUTs PORT_7FFD_SHADOW as it is NOW (not a saved port value). Race
;     with the main code's "shadow first, then OUT" (page_bank / set_screen):
;     an interrupt between the two leaves the port already at the new value,
;     and the main code's own OUT then rewrites the same byte. No DI needed.
; Saves every register it or the player may touch: AF, BC, DE, HL, IX (BC in the write-back word
; at S, popped back at the exit: S is in bank 2 / 5, or in the $C000 bank of a stack blit, which
; never writes $7FFD while SP is borrowed, so the exit reads the bank the entry wrote); IY is
; neither used here nor by AY_PLAY (ay.asm + the WZM player: no IY, verified by grep
; and by tests/isr_rate.py's IY-across-ISR check) so it is NOT saved (ISR-RATE, -29 T).
; (+ the alternate set if ISR_SAVE_ALT, out of line in isr_alt). Flags preserved
; (pop af before the exit; ld sp / ei / jp touch none).
; Stack: the interrupted stack only (S..S+1), rewritten to BC; own stack ISR_STK:
; 8 B + AY_PLAY's 8 B (CALL 2 + the player's 6) = ISR_STK_NEED (+10 alt).
; Cost (measured): ISR own instructions 261 T + 19 T acknowledge = 280 T overhead (was 315 + 19);
; C-T3 +85 T: entry ex / ld / pop / push / ld / ld sp 86 T, push bc dropped -11 (isr -> isr.done
; +75 T); exit ld sp / pop bc / ei / jp 34 T vs pop bc / ei / ret 24 T (+10); + AY_PLAY (SND-2: the dispatcher + WZM player, idle ~0.2k .. worst ~5k T), in the
; top border (docs/memory-map.md "Interrupts (A8)").
; SMC: isr_rs+1 (the resume SP) and isr_jp+1 (the return address), written at
;      every entry before use.
;------------------------------------------------------------------------------
isr_image:
                DISP ISR_ADDR
isr:
                ex   (sp), hl                  ; 19 HL = return address, (S) = HL (scratch)
                ld   (isr_jp + 1), hl          ; 16 SMC: the exit's jp target
                pop  hl                        ; 10 HL back; SP = S + 2
                push bc                        ; 11 write-back: (S..S+1) = BC; the only
                                               ;    write to the interrupted stack; SP = S
                ld   (isr_rs + 1), sp          ; 20 SMC: the exit's ld sp (= S)
                ld   sp, ISR_STK               ; 10 own stack (bank 2) from here on
                push af
                push hl
                ld   hl, SYS_FRAMES            ; ROM: INC (IY+$40) chain; ISR-RATE: 33 T common path
                inc  (hl)                      ; (was 58: ld hl,(nn) / inc hl / ld (nn),hl / ld a,h / or l)
                jr   nz, .frames
                inc  l                         ; same page: SYS_FRAMES $5C78..$5C7A
                inc  (hl)
                jr   nz, .frames
                inc  l
                inc  (hl)
.frames:
                ASSERT (SYS_FRAMES & $FF) + 2 <= $FF
                                               ; (no push bc: the exit pops BC back from
                                               ;  the write-back word, -11 T here, -10 T there)
                push de
                push ix                        ; ISR-RATE: no IY (ay.asm / the player never use it)
                ld   a, (PORT_7FFD_SHADOW)
                and  ~7 & $FF                  ; keep screen bit 3 + ROM bit 4
                or   BANK_AY
                ld   bc, PORT_7FFD
                out  (c), a                    ; shadow untouched
    IF ISR_SAVE_ALT
.page:          call isr_alt                   ; saves AF'..HL' around AY_PLAY (out of line:
                                               ; the window has no room for the 12 B)
    ELSE
.page:          call AY_PLAY                   ; bank 3, contended fetches
    ENDIF
                ld   a, (PORT_7FFD_SHADOW)     ; the CURRENT shadow (see 3. above)
                ld   bc, PORT_7FFD
                out  (c), a
.done:                                         ; test probe: port == shadow here
                pop  ix
                pop  de
                pop  hl
                pop  af
isr_rs:         ld   sp, 0                     ; 10 SMC: S (set at entry)
                pop  bc                        ; 10 BC from the write-back word; SP = S + 2
                ei                             ; 4 the next interrupt waits for the jp
isr_jp:         jp   0                         ; 10 SMC: the return address (set at entry)
isr_end:
                ENT
ISR_LEN         EQU isr_end - isr
                ASSERT ISR_ADDR + ISR_LEN <= ISR_ADDR_END
                ASSERT (ISR_ADDR >> 8) == ISR_VEC_BYTE          ; vector byte = both address bytes
                ASSERT ISR_VEC_TABLE + ISR_VEC_LEN <= ISR_ADDR
                ASSERT (ISR_VEC_TABLE & $FF) == 0
                ASSERT (ISR_VEC_TABLE >> 8) >= $80 && (ISR_VEC_TABLE >> 8) < $C0  ; I: bank 2
                ASSERT ISR_ADDR_END <= STACK_BOTTOM

    IF ISR_SAVE_ALT
; isr_alt — the alternate set saved around AY_PLAY (ISR_SAVE_ALT=1 only,
; assemble-only like before): copied to ISR_ALT_ADDR (the bottom of the ISR
; stack area, below its deepest byte). +27 T (call / ret) over inline saves.
isr_alt_image:
                DISP ISR_ALT_ADDR
isr_alt:
                ex   af, af'
                push af
                exx
                push bc
                push de
                push hl
                call AY_PLAY
                pop  hl
                pop  de
                pop  bc
                exx
                pop  af
                ex   af, af'
                ret
isr_alt_end:
                ENT
ISR_ALT_LEN     EQU isr_alt_end - isr_alt
    ELSE
ISR_ALT_LEN     EQU 0
    ENDIF
                ; the ISR stack area STACK_BOTTOM..ISR_STK holds isr_alt (if any) + the ISR's
                ; deepest use; the main stack must stay above ISR_STK (W20 measures it)
                ASSERT ISR_ALT_ADDR + ISR_ALT_LEN <= ISR_STK - ISR_STK_NEED
                ASSERT WORKSTORE_TOP - ISR_STK >= STACK_MAIN_MAX

; the boot6_tiles run: tiles_common (glyphs, attrs), orn_glyphs, the HOT_COPY
; image, font6x8 — contiguous, in this order (HL continues across them)
                INCLUDE "../assets/gfx/tiles/tiles_common.asm" ; -> TILE_GLYPHS / TILE_ATTRS 0..31
                INCLUDE "../assets/gfx/panel/panel_orn.asm"    ; -> ORN_GLYPHS
                INCLUDE "panel_hot.asm"                       ; -> HOT_COPY
                INCLUDE "../assets/gfx/fonts/font6x8.asm"     ; -> FONT6 planes
                ASSERT tiles_common_attrs == tiles_common_glyphs + TILE_COMMON * 8
                ; TRAP-OR: tr_cell3 (bank 3) ORs only lines 6 / 7 of the plate into the cell under it
TRG             EQU tiles_common_glyphs + T_TRAP * 8
                ASSERT {b TRG} == 0 && {b TRG+1} == 0 && {b TRG+2} == 0 && {b TRG+3} == 0 && {b TRG+4} == 0 && {b TRG+5} == 0
                ASSERT {b TRG+6} == TRAP_GLY6 && {b TRG+7} == TRAP_GLY7
                ; 3F-B1: erase_rect's air path writes 8 zero lines without reading the glyph
                ASSERT T_AIR == 0 && ({b tiles_common_glyphs}|{b tiles_common_glyphs+1}|{b tiles_common_glyphs+2}|{b tiles_common_glyphs+3}|{b tiles_common_glyphs+4}|{b tiles_common_glyphs+5}|{b tiles_common_glyphs+6}|{b tiles_common_glyphs+7}) == 0
                ASSERT TILES_COMMON_LEN == TILE_COMMON * 9
                ASSERT orn_glyphs == tiles_common_glyphs + TILES_COMMON_LEN
                ASSERT orn_glyphs_end - orn_glyphs == ORN_COUNT * 8
                ASSERT panel_hot_img == orn_glyphs_end
                ASSERT font6x8 == panel_hot_img + PANEL_HOT_LEN
                ASSERT FONT6X8_COUNT == 96 && FONT6X8_STRIDE == 8 && FONT6_PAGES * 2 == 8
                ASSERT $ - font6x8 == FONT6X8_COUNT * FONT6X8_STRIDE
