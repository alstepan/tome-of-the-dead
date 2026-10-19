;==============================================================================
; main.asm — WazHack/ZX: first playable fighting prototype.
;             Spec: docs/design/prototype.md (rev B, authoritative).
;
; Target : ZX Spectrum 128K.   Build:
;   tools/build.sh   (zx0_sources.py, then sjasmplus src/main.asm --fullpath
;                     --lst/--sld/--sym=build/wazhack.* -i src; fails on warnings)
;   -> build/wazhack.tap (BASIC loader + CODE lowram_code..code_end + 3
;      headerless blocks: bank 1 sources, bank 3 source tail + cold code,
;      bank 3 AY slot)
;   -> build/wazhack.sna (128K snapshot; entry = boot, all banks preloaded)
;
; Memory (docs/memory-map.md "PROTO"): HOT code+tables $8000..(< FRT, bank
; 2); frame runtime table FRT $A600..$AFFF; runtime entity/render tables
; $B000..$BAFF; stack $BB00..$BEFF; state block $BF00..$BFFF; room maps, tiles
; + generator buffers $6000..$6D3F and the COLD block lowram_code..$7FFF (bank
; 5: boot, generator, game start, frame descriptors);
; COLD paged code in bank 3 after the source tail (select, transition scrolls,
; via far3); unshifted sprite SOURCES in banks 1/3 (assembled at virtual
; $8000..$FFFF); mirrored + pre-shifted sprite POOL generated at boot into
; banks 0/4/6.
;
; Loop: 25 Hz tick (2 frames of SYS_FRAMES, bumped by the A8 IM 2 ISR). TURN_PHASE INPUT samples
; keys and resolves a whole turn instantly (player, then monsters in slot order,
; then pending materialise); TURN_PHASE ANIM replays it (tweens, attack /
; reaction / death sequences) until every queue is done (>= 2 ticks).
;==============================================================================

                DEVICE ZXSPECTRUM128
    IFNDEF OVL_PASS
OVL_PASS        EQU 2                   ; tools/build.sh: -DOVL_PASS=1 first (3E-T1 overlays)
    ENDIF

                INCLUDE "constants.asm"
                INCLUDE "defs.asm"
                INCLUDE "sfx_ids.inc"                         ; SND-5 SFX_* ids (tools/sfx2asm.py, build/sfx)
                INCLUDE "../assets/gfx/tiles/tileset_ids.inc" ; TS<d>_* ids (EQUs only; B12 glow_ids)

;------------------------------------------------------------------------------
; TAPE_BLOCKS — 3E-T1 review: THE list of headerless tape blocks (bank, $C000-
; window address, length), in tape order. Expanded twice so the loader and the
; tape can never disagree: mode 0 = `start`'s tape_tab records (lowram.asm,
; TT_STRIDE B each), mode 1 = the SAVETAPs (Artefacts, end of this file).
;------------------------------------------------------------------------------
    MACRO TAPE_BLK mode, bank, addr, len
      IF mode == 0
                DB   bank
                DW   addr, len
      ELSE
                MMU  3, bank
                SAVETAP  "build/wazhack.tap", HEADLESS, addr, len
      ENDIF
                ASSERT bank < 8 && addr >= BANK_WINDOW && len > 0 && addr + len <= $10000
    ENDM
    MACRO TAPE_BLOCKS mode
                TAPE_BLK mode, BANK_SRC_LO, BANK_WINDOW, SRC_LEN_LO       ; sources, vdata, UI code, overlays
                TAPE_BLK mode, BANK_COLD3, BANK_WINDOW, BANK3_LEN         ; source tail + bank-3 cold code
                TAPE_BLK mode, BANK_COLD3, AY_RESERVE, AY_LEN             ; A8 AY slot (BANK_AY = 3)
                TAPE_BLK mode, BANK_TSET, TSET_LO, B7_TAPE_LEN            ; B3B-8 tilesets 0-3 + D3-S2 bank-7 code
                TAPE_BLK mode, BANK_TSET, TSET_HI, TSET_HALF_LEN          ; tilesets 4-7
                TAPE_BLK mode, BANK_TEXT, TEXT_ADDR, TEXT_LEN             ; D3-TX text block (bank 0 bottom)
                TAPE_BLK mode, BANK_BOOT6, BOOT6_ADDR, BOOT6_LEN          ; 3E-T1 boot block (bank 6 top)
    ENDM
TAPE_HEADLESS_N EQU 7                   ; = the TAPE_BLK lines above (tape_tab ASSERTs its size)

;==============================================================================
; SPRITE SOURCES — banks 1 and 3, assembled contiguously at virtual $8000..$FFFF
; (slot 2 = page 1, slot 3 = page 3). Read only by the boot generator via
; copy_virt (B3B-8: init_tiles no longer reads the raw items / tiles) (virtual < $C000 -> bank 1 at +$4000, else bank 3
; as-is). The generator frames are ZX0 blocks
; (build/zx0/sprites_zx0.asm, written by tools/zx0_sources.py — tools/build.sh
; runs it); their per-frame block/offset are EQUs folded into the bank-5
; fdesc_tab (A6); items/tiles stay raw.
; (B3B-12: the raw index.asm A/B build is retired; tests/zx0_pool.py checks the
; pool against a Python reference made from the raw frame data.)
;==============================================================================
                MMU  2, BANK_SRC_LO
                MMU  3, BANK_SRC_HI
                ORG  SRC_VIRT_BASE
sprite_src:
                INCLUDE "../build/zx0/sprites_zx0.asm"
sprite_src_end:
SRC_TOTAL       EQU sprite_src_end - sprite_src
; B3B-11b (bank-3 relief): boot / new-game cold DATA, read only through
; copy_virt / copy_virt3 (virtual address -> bank 1 or 3), right after the
; sources, in bank 1. Same tape blocks.
; 3E-T1 (lever a): the boot-only part (font6x8, the HOT_COPY image,
; tiles_common, orn_glyphs) moved to the boot block (boot6.asm, bank 6 tail).
vdata:
                INCLUDE "../assets/gfx/panel/panel_icons.asm" ; panel_init (pblit via GEN_SRC)
                ; D3-4: the 7 status icons (game.md §6.4; panel row 21 cols 30-31,
                ; tints): 8 B glyph each (FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR,
                ; POISON, WEAK = status_icons + 8 * i), then 7 attrs
                ; (status_icons_attr). Data only; D3-8 draws them (copy_virt3).
                INCLUDE "../assets/gfx/sprites/status_icons.asm"
                ASSERT status_icons_count == 7 && status_icons_attr - status_icons == 7 * 8
                ASSERT $ - status_icons == 7 * 9                ; 63 B
                ; (D3-TX: the text block moved out to bank 0, see TEXT below)
vdata_end:
VDATA_LEN       EQU vdata_end - vdata
; C3-0 (plan "3C breakdown" D4): bank-1 UI code (menus / pause / end screens),
; right after vdata, entered only through far1 (gfx.asm). Assembled at its
; runtime $C000.. address (DISP by TEXT_DISP, like the text block); the bytes
; stay in the bank-1 tape block. Bank-1 code obeys the bank-3 rules: it never
; pages $C000 itself, the helpers it calls hand $C000 back.
ui1_img:
                DISP $ + TEXT_DISP
ui1_code:
                INCLUDE "ui1.asm"
ui1_end:
                ENT
ui1_img_end:
UI1_LEN         EQU ui1_img_end - ui1_img
                ASSERT ui1_img_end <= BANK_WINDOW              ; all in bank 1 (virtual < $C000)
                ASSERT ui1_code == ui1_img + TEXT_DISP && ui1_end <= UI1_LIMIT
; 3E-T1: the packed OVERLAY streams (ovl_run; "OVERLAYS" below), last in bank 1
; so their sizes move nothing an overlay can reference. Labels = runtime
; $C000-window addresses (ovl_run: HL = label, C = BANK_OVL). Pass 1 of
; tools/build.sh (OVL_PASS 1) has no packed files yet: the streams are empty.
ovl_img:
                DISP $ + TEXT_DISP
ovl_blobs:
    IF OVL_PASS == 2
ovl_test_zx0:   INCBIN "ovl_test.zx0"                 ; 3E-T1 self-test overlay (tests/ovl.py)
    ENDIF
ovl_blobs_end:
                ENT
ovl_img_end:
OVL_BLOBS_LEN   EQU ovl_img_end - ovl_img
                ASSERT ovl_img_end <= BANK_WINDOW && ovl_blobs_end <= UI1_LIMIT
VIRT_TOTAL      EQU ovl_img_end - sprite_src
    IF VIRT_TOTAL > $4000
SRC_LEN_LO      EQU $4000
    ELSE
SRC_LEN_LO      EQU VIRT_TOTAL
    ENDIF
SRC_LEN_HI      EQU VIRT_TOTAL - SRC_LEN_LO
                ASSERT VIRT_TOTAL <= $8000
                DISPLAY "GAME sprite sources: ", /D, SRC_TOTAL, " B + vdata ", /D, VDATA_LEN, " B (bank1 ", /D, SRC_LEN_LO, ", free ", /D, $4000 - SRC_LEN_LO, "; bank3 ", /D, SRC_LEN_HI, ")"
                DISPLAY "GAME bank-1 UI code: ", /H, ui1_code, "..", /H, ui1_end, " (", /D, UI1_LEN, " B), overlay streams ", /D, OVL_BLOBS_LEN, " B, bank 1 free: ", /D, UI1_LIMIT - ovl_blobs_end
                DISPLAY "GAME ZX0 sources: ", /D, ZX0_FRAMES, " frames in ", /D, ZX0_BLOCKS, " blocks, ", /D, ZX0_PACKED_RAW, " -> ", /D, ZX0_PACKED_TOTAL, " B packed; total ", /D, SRC_TOTAL, " vs raw ", /D, ZX0_RAW_SRC_TOTAL, ": freed ", /D, ZX0_RAW_SRC_TOTAL - SRC_TOTAL, " B"


;==============================================================================
; BANK-3 COLD CODE — hero select + transition scrolls (bank3.asm), assembled
; straight after the source tail in bank 3 (never below $C000), ending below
; the AY reserve. Loaded by the bank-3 tape block (BANK3_LEN from $C000).
;==============================================================================
    IF $ < BANK_WINDOW
                ORG  BANK_WINDOW               ; sources all in bank 1
    ENDIF
bank3_code:
                INCLUDE "bank3.asm"
bank3_end:
BANK3_LEN       EQU bank3_end - BANK_WINDOW
BANK3_CODE_LEN  EQU bank3_end - bank3_code
                ASSERT bank3_end <= AY_RESERVE
                DISPLAY "GAME bank-3 cold code: ", /H, bank3_code, "..", /H, bank3_end - 1, " (", /D, BANK3_CODE_LEN, " B), free to AY reserve: ", /D, AY_RESERVE - bank3_end

;==============================================================================
; AY PLAYER SLOT (A8) — bank 3 AY_RESERVE..$FFFF (4 KB since D3-0, 4704 B since MEM-SND): called by the IM 2
; ISR once per frame. SND-2: ay_play (mailbox dispatcher) + the WZM player
; (MODULE wzm) + its state block ay_vars + the songs (MODULE mus), in that
; order (ay.asm). Own headerless tape block.
;==============================================================================
                ORG  AY_RESERVE
ay_code:
                INCLUDE "ay.asm"
ay_code_end:
AY_LEN          EQU ay_code_end - AY_RESERVE
                ASSERT ay_code == AY_PLAY && ay_play == AY_PLAY
                ASSERT ay_vars > ay_play && ay_vars_end <= mus.mus_songs
                ASSERT ay_code_end <= AY_RESERVE_END
                DISPLAY "GAME AY slot (bank 3): ", /H, AY_RESERVE, "..", /H, ay_code_end - 1, " (", /D, AY_LEN, " B of ", /D, AY_RESERVE_END - AY_RESERVE, "), free: ", /D, AY_RESERVE_END - ay_code_end, "; ISR ", /D, ISR_LEN, " B at ", /H, ISR_ADDR

;==============================================================================
; LEVEL TILESETS (B3B-8) — the 8 per-level tile sets (tools/tiles_convert.py,
; slot format TSET_* in level_defs.asm) in the bank-7 spare: slots 0-3 above
; screen 2 (TSET_LO), 4-7 above the shadow attrs (TSET_HI; TSET_SPLIT, a
; macro the generated file invokes between D4 and D5). Two headerless tape
; blocks (`start` .t7lo / .t7hi); level_load_tiles copies one slot per level.
;==============================================================================
                MMU  3, BANK_TSET
    MACRO TSET_SPLIT
tsets_lo_end:
                ORG  TSET_HI
    ENDM
                ORG  TSET_LO
                INCLUDE "../assets/gfx/tiles/tilesets.asm"
                ASSERT tileset_d1 == TSET_LO && tileset_d5 == TSET_HI
                ASSERT tileset_d2 - tileset_d1 == TSET_STRIDE && TILESET_SLOT_LEN == TSET_STRIDE
                ASSERT tsets_lo_end == TSET_LO + TSET_HALF_LEN && tilesets_end == TSET_HI + TSET_HALF_LEN
                ASSERT tsets_lo_end <= B7_CODE && tilesets_end <= $10000

;==============================================================================
; BANK-7 COLD CODE (D3-S2) — B7_CODE ($E000, right after tileset slot 3)
; .. B7_LIMIT ($F800, the attr shadow): the 6 KB the dropped bitmap shadow
; freed. Entered only through far7 (rules: src/bank7.asm). On tape it is ONE
; block with the low tilesets (TSET_LO .. b7_end, start .t7lo).
;==============================================================================
                ORG  B7_CODE
b7_code:
                INCLUDE "bank7.asm"
b7_end:
B7_LEN          EQU b7_end - b7_code
B7_TAPE_LEN     EQU b7_end - TSET_LO           ; tilesets 0..3 + the code, one tape block
                ASSERT tsets_lo_end == B7_CODE && b7_end <= B7_LIMIT && B7_LIMIT == SHADOW_ATTR
                DISPLAY "GAME bank-7 cold code: ", /H, b7_code, "..", /H, b7_end - 1, " (", /D, B7_LEN, " B), free to the attr shadow: ", /D, B7_LIMIT - b7_end

;==============================================================================
; TEXT (B3B-13; D3-TX: bank 1 -> bank 0) — the text block (tools/textpack.py
; from src/strings.txt: string table, dictionary, token streams) at the BOTTOM
; of pool bank 0, TEXT_ADDR..POOL_START; the pre-shift pool starts above it
; (alloc_reset), so the pool never overwrites it. Read at runtime only with
; BANK_TEXT paged (msg_push / impact_line / print6t / print6x / tx_dec). Own
; headerless tape block (`start` .txt).
;==============================================================================
                MMU  3, BANK_TEXT
                ORG  TEXT_ADDR
text_img:
                INCLUDE "../build/text/strings.asm"
text_img_end:
TEXT_LEN        EQU text_img_end - text_img
POOL_START      EQU text_img_end               ; alloc_reset: first pool byte in bank 0
                ASSERT text_base == TEXT_ADDR && TEXT_LEN == TEXT_PACKED
                ASSERT text_img_end <= tap_loader      ; the BASIC loader scratch ($E000, page 0)
                DISPLAY "GAME text (bank 0): ", /D, TX_COUNT, " strings, ", /D, TX_TOKENS, " tokens, raw ", /D, TEXT_RAW, " -> ", /D, TEXT_PACKED, " B packed at ", /H, text_base, "; pool from ", /H, POOL_START

;==============================================================================
; BANK-5 LOW-RAM COLD CODE — tape entry, boot, generator, init_tiles, game
; start (lowram.asm). ORGed so it ends exactly at $8000 (no ALIGN inside, so
; its size does not depend on its base): contiguous with the bank-2 image.
;==============================================================================
                MMU  1, 5
                ORG  $8000 - (lowram_code_end - lowram_code)
lowram_code:                                   ; = start (ASSERTed): the USR target
                INCLUDE "lowram.asm"
lowram_code_end:
LOWRAM_CODE_LEN EQU lowram_code_end - lowram_code
                ASSERT lowram_code_end == $8000
                ; the descriptors are the tail of the cold block: room for the
                ; remaining FRT_MAX - FDESC_COUNT ones is kept free below it
FDESC_GROW      EQU (FRT_MAX - FDESC_COUNT) * FDESC_STRIDE
LOWRAM_SPARE    EQU lowram_code - FDESC_GROW - LOWRAM_FREE_END
                ASSERT lowram_code - FDESC_GROW >= LOWRAM_FREE_END
                ASSERT fdesc_end == lowram_code_end
                ASSERT GEN_SCRATCH + GEN_SCRATCH_LEN <= TILE_GLYPHS  ; the lowest buffer above the alias
                ASSERT GEN_SCRATCH + GEN_SCRATCH_LEN <= BITREV_TAB
                ASSERT (TILE_GLYPHS & $1FF) == 0                    ; tile_rect glyph addressing
                ASSERT (TILE_ATTRS & $FF) + TILE_IDS <= 256          ; one page
                DISPLAY "GAME low-RAM cold block: ", /H, lowram_code, "..0x7FFF (", /D, LOWRAM_CODE_LEN, " B = code ", /D, fdesc_tab - lowram_code, " + ", /D, FDESC_COUNT, " frame descriptors ", /D, fdesc_end - fdesc_tab, " B); spare after the descriptor growth reserve (", /D, FDESC_GROW, " B): ", /D, LOWRAM_SPARE

;==============================================================================
; MAIN IMAGE — bank 2 at $8000. Hot code + tables only.
;==============================================================================
                MMU  2, 2
                MMU  3, 0
                ORG  $8000
image_start:


;==============================================================================
; play_loop — one 25 Hz tick per iteration (prototype §3.2).
; A7 double buffer (option A): bank 7 is displayed during play; render composes
; in bank 5 and pmark_dmg marks the cells it changed. The NEXT tick starts with
; present, right after the HALT: it copies everything marked during the
; previous tick (render + HUD / messages of the turn logic) top to bottom while
; the beam is still in the top border, so it stays ahead of the beam (no tear)
; and runs mostly uncontended. Cost: +1 tick display latency (user, A7).
; At probe_presented bank 7 == bank 5 (tests/flicker.py asserts it per tick).
;==============================================================================
play_loop:
                call wait_tick
tick_work:                                     ; budget probe: tick work starts here
                call present                   ; A7: last tick's changes -> bank 7
probe_presented:                               ; test probe (no code): bank 7 == bank 5
                ld   hl, (TICK_COUNTER)
                inc  hl
                ld   (TICK_COUNTER), hl
                call input_tick                ; C3-1: STICK / STICK_OLD once per tick
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                jp   nz, end_screen
                call intent_tick               ; C3-2: FIRE / cursor / shortcuts, every tick
    IF RENDER_FIRST
                ; E0 experiment: draw right after the HALT sync, so the erase->draw
                ; window of every sprite sits at a fixed early point of the frame
                ; (beam is still in the top border/first rows) instead of wherever
                ; input+anim happened to end. Costs one tick of display latency.
                call render
                call pmark_dmg                 ; A7: presented at the next tick start
probe_render_done:
                ld   a, (TURN_PHASE)
                or   a
                call z, read_turn_input        ; INPUT: maybe start a turn
                call anim_gate                 ; C3-2b: frozen in ICON MODE
    ELSE
                ld   a, (TURN_PHASE)
                or   a
                call z, read_turn_input        ; INPUT: maybe start a turn
                call anim_gate                 ; C3-2b: frozen in ICON MODE
                call render
                call pmark_dmg
probe_render_done:
    ENDIF
                ; B3B-10: animated decor. After this tick's render (the drawn
                ; footprints R_COL..R_ROWS it tests are render's; anim_tick only
                ; rewrites R_VIS / R_FID) and, with RENDER_FIRST, after the turn
                ; logic: a heavy input tick is then usually in its 2nd frame,
                ; where decor_tick holds (it never lengthens such a tick)
                call decor_gate                ; C3-2b: frozen in ICON MODE
                ; B3B-11 (D5, user 2026-10-03): one panel item per tick, in ANIM
                ; ticks >= 1 and idle ticks, never in a turn's input tick (TURN_PHASE
                ; = ANIM with TURN_TICK still 0: read_turn_input just started it)
                ld   a, (TURN_PHASE)
                or   a
                jr   z, .panel
                ld   a, (TURN_TICK)
                or   a
                jr   z, panel_done
                dec  a                         ; D3-8e2 (game.md §6.5.1): nor up to the
                ld   hl, COMBAT_NOT_BEFORE     ; cast's first impact tick — the whole queue
                cp   (hl)                      ; (log, target readout, HP bar) waits; 0 = no
                jr   c, panel_done             ; gate; end_turn clears it. TURN_TICK <= the
                                               ; gate (dec): a panel item drawn in tick t is
                                               ; presented at t + 1, the impact anim_tick
                                               ; computes in tick t is rendered at t + 1 and
                                               ; presented at t + 2 (RENDER_FIRST): from t + 1
                                               ; both show together (+7 B, 28 T)
                ld   a, (TURN_PEND)            ; D3-7: nor in an ability's fire tick
                and  TP_FIRE                   ; (act_fire + its proj_fire: the cast tick)
                jr   nz, panel_done
.panel:         call panel_tick
panel_done:                                    ; test probe (no code): panel item done
                ld   a, (TURN_PHASE)
                or   a
                jr   z, play_loop
                ld   hl, TURN_TICK
                inc  (hl)
                call turn_done
                jr   nc, play_loop
                ld   hl, end_turn              ; D3-S2: bank 7 (bank7.asm)
                call far7
                jr   play_loop

;------------------------------------------------------------------------------
; anim_gate / decor_gate — C3-2b (game.md §3.1): in ICON MODE between turns
; (INPUT phase) nothing animates and no decor timer runs; a mode entered
; during a turn's animation lets that turn finish first.  Clobbers: as callee
; D3-7: anim_gate first runs the split ability turn while TURN_PEND != 0
; (act_pend: the release at ACT_AT, then the deferred monster phase), before
; anim_tick / fx_tick, so what it starts animates from this tick as on the
; input tick. Idle cost 27 T. decor_gate holds the decor on the fire tick.
;------------------------------------------------------------------------------
anim_gate:      ld   a, (TURN_PEND)
                or   a
                call nz, pend_far
                call frozen
                ret  z
                call anim_tick
                jp   fx_tick                   ; D3-5: FX tracks advance with the bodies
decor_gate:     call frozen
                ret  z
                call mark_tick                 ; D3-8d status marks: before the drip / decor
                                               ; (their cell_occ sees the marks); nothing on
                                               ; the fire tick
                call drip_tick                 ; D3-8b (nothing at all on the fire tick)
                ld   a, (TURN_PEND)            ; D3-7: no decor step on the fire tick
                and  TP_FIRE
                ret  nz
                jp   decor_tick
; pend_far — the TURN_PEND hook's far entry (act7.asm act_pend, bank 7).
; Clobbers: all but IY.
pend_far:       ld   hl, act_pend
                jp   far7
; probe_act_fire — test probe (budget.py "cast" class): act_pend calls it on
; the fire tick, right before act_fire (bank-7 code cannot carry a probe).
probe_act_fire: ret
; probe_act_prep — test probe (D3-8e): act_begin calls it on the input tick,
; right before far3 proj_pre (the accept's share of the cast: the abil /
; abil_ammo suites seed the RNG and snapshot the model there).
probe_act_prep: ret
frozen:         ld   a, (ICON_MODE)            ; Z = frozen (ICON MODE, INPUT phase)
                or   a
                jr   z, .n
                ld   a, (TURN_PHASE)
                or   a
                ret
.n:             inc  a                         ; NZ
                ret
                ASSERT TP_INPUT == 0

;------------------------------------------------------------------------------
; wait_tick — pace to 2 frames per tick (SYS_FRAMES: the A8 IM 2 ISR bumps it at
; every frame start, like the ROM IM1 ISR did). Arriving with >= 2 frames already gone
; means this tick blew its 141.8k T budget: OVERRUN_COUNT++ (presentation only).
; Clobbers: A, B, HL
;------------------------------------------------------------------------------
wait_tick:
                ld   a, (LAST_TICK_FRAME)
                ld   b, a
                ld   a, (SYS_FRAMES)
                sub  b
                cp   TICK_FRAMES
                jr   c, .wait
                ld   hl, (OVERRUN_COUNT)
                inc  hl
                ld   (OVERRUN_COUNT), hl
                jr   .go
.wait:          halt
                ld   a, (SYS_FRAMES)
                sub  b
                cp   TICK_FRAMES
                jr   c, .wait
.go:            ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ret

; resync_tick — forget elapsed time (after a transition / long cold path).
resync_tick:
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ret

;------------------------------------------------------------------------------
; read_turn_input — INPUT phase, from play_loop (TURN_PHASE 0, every such
; tick). D3-S2: the body is bank-7 turn_input (bank7.asm, far7); this label
; stays the budget phase probe. Clobbers: all but IY.
;------------------------------------------------------------------------------
read_turn_input:
                ld   hl, turn_input
                jp   far7

;------------------------------------------------------------------------------
; end_screen — GS_DEAD / GS_WIN: wait for 1..0 / ENTER -> menu (new game uses
; the same fixed seed, §6.5).
;------------------------------------------------------------------------------
end_screen:
                ld   a, (END_SHOWN)            ; C3-6: the death / win card, once
                or   a
                jr   nz, .shown
                inc  a
                ld   (END_SHOWN), a
                ld   a, (GAME_STATE)
                ld   hl, end_card              ; bank 1 (menu1.asm)
                call far1
.shown:         call panel_tick                ; B3B-11: the death / win line, HP 0
                call keys_down                 ; C3-6b: raw 1..0 / ENTER (not FIRE: a
                ld   hl, END_SHOWN             ; held FIRE / joystick cannot skip it)
                jr   z, .none
                bit  1, (hl)                   ; END_SHOWN 2 = armed (all released once)
                jr   nz, .go
                jp   play_loop
.none:          ld   (hl), 2                   ; released: from now on a key returns
                jp   play_loop
.go:
                ; ENTER: fall through into enter_select

;==============================================================================
; enter_select — the C3-6 main menu (bank 1: menu_run via far1), then
; start_game (bank 5 low RAM) with C = the chosen kind. Reached by jp only (boot, end_screen),
; so the stack is at its base level here.
;==============================================================================
enter_select:
                call show_bank5                ; A7: the menu draws on (and shows) bank 5
                ld   hl, menu_run              ; C3-6: bank 1 (menu1.asm)
                call far1                      ; C = hero kind
                jp   start_game


                INCLUDE "io.asm"
                INCLUDE "gfx.asm"
                INCLUDE "logic.asm"
                INCLUDE "anim.asm"
                INCLUDE "data.asm"
                INCLUDE "panel2.asm"            ; B3B-11 panel engine, bank-2 part
                INCLUDE "icons.asm"             ; C3-3 icon bar state, info / level items
                INCLUDE "decor.asm"             ; B3B-10 animated decor (decor_tick)
                INCLUDE "fx.asm"                ; D3-5 FX tracks (fx_start / fx_tick / fx_render)
                INCLUDE "drip.asm"              ; D3-8b decorative drip (drip_tick, per tick)

;==============================================================================
; kind_tab — page-aligned parallel byte arrays (KT_*), prototype §6.3. A6: two
; pages, K_MAX (32) B per array; no array crosses a page (KFIELD, feet_mod).
;==============================================================================
kind_tab_pad:                                  ; ALIGN padding starts here (headroom)
                DS   (-($ + TILE_IDS + DT_ATTR_LEN)) & $FF, 0    ; B3B-5: tile_flags ends on the page
;------------------------------------------------------------------------------
; dt_attr_tab — B3B-10 decor_tick attr cycles, 8 steps per kind (concept-screen
; §3.3): kind 1 flame (DT_HOT -> DT_RED -> DT_DIM: tall / slim torch bodies, braziers).
; (DEC1: kind 2, the candle flicker, is gone with the candles.) Whole attr bytes: they override the cell's
; paper (black on every cycled cell, see decor.asm DT_HOT). In the pad below
; tile_flags: never crosses a page.
;------------------------------------------------------------------------------
dt_attr_tab:
                DB   DT_HOT, DT_RED, DT_DIM, DT_HOT, DT_RED, DT_DIM, DT_HOT, DT_RED   ; 1 flame
DT_ATTR_LEN     EQU  DT_KINDS * 8
                ASSERT $ - dt_attr_tab == DT_ATTR_LEN && (dt_attr_tab >> 8) == (($ - 1) >> 8)
;------------------------------------------------------------------------------
; tile_flags — TILE_FLAGS[64] (D2, level_defs.asm TF_*), static, by tile id;
; the 64 B right below kind_tab (low byte $C0: cell_blocked adds the id with
; no carry, H constant). Placed in the ALIGN pad, so it costs no bank-2 bytes
; beyond its 64. Per-level ids 32..59 = 0 (decor), 60..63 = lectern / Book
; until the first level_load_tiles (B3B-8) overwrites 32..63 from the slot.
; Solidity belongs to the cell class (game.md §1.2 "Solidity of decor",
; designer 2026-10-03): the wall set (DARK = T_BRICK, DITHER, PATCH, FADE) is
; SOLID and only ever replaces wall cells; rubble / bones / moss / cobweb /
; chain / floor items are not. Per-level wall variants (pillar,
; plaster patches in 32..59) carry TF_SOLID in their tileset slot's flags.
;------------------------------------------------------------------------------
tile_flags:
                DB 0                                   ;  0 T_AIR
                DB TF_FLOOR                            ;  1 T_PLAT
                DB TF_SOLID                            ;  2 T_BRICK (wall, lintel, block)
                DB TF_SOLID | TF_FLOOR                 ;  3 T_WALLF
                DB TF_LADDER, TF_LADDER, TF_LADDER     ;  4-6 T_LAD_L/M/R
                DB TF_LADDER | TF_HOLE, TF_LADDER | TF_HOLE, TF_LADDER | TF_HOLE ; 7-9 T_HOLE_*
                DB 0                                   ; 10 T_POTION (floor item)
                DB 0, 0, 0, 0                          ; 11 / 14 door jambs (open door), 12-13 chain, bones 0
                DB 0, 0                                ; 15-16 T_BONES_1/2 (DEC1: static)
                DB 0, 0                                ; 17-18 T_DAGGERS / T_ARROWS (floor items, D3-7)
                DB TF_FLOOR, TF_FLOOR                  ; 19-20 T_END_L/R = pit caps
                DB TF_SOLID, TF_SOLID                  ; 21-22 T_DOOR_ARCH_L/R
                DB TF_SOLID | TF_DOOR, TF_SOLID | TF_DOOR   ; 23-24 T_DOOR_L/R (closed planks)
                DB TF_SOLID | TF_DOOR | TF_LOCK        ; 25 T_DOOR_LOCK
                DB TF_LADDER | TF_HOLE                 ; 26 T_GRATE (B12: raised = the open exit hole)
                DB 0                                   ; 27 T_RUBBLE (decor at a block's foot)
                DB 0, 0, 0                             ; 28-30 T_WALL_DITHER / PATCH / FADE:
                                                       ; non-solid back-wall patches (D1 decor rule)
                DB 0                                   ; 31 T_BONES_3
                DS T_LVL_OBJ - TILE_COMMON, 0          ; 32-59 per-level decor
                DS T_LVL_OBJ_N, TF_SOLID | TF_ATTACK   ; 60-63 lectern / Book
                ASSERT $ - tile_flags == TILE_IDS
                ASSERT (tile_flags & $FF) + TILE_IDS == $100     ; one page, ends on it
                ALIGN 256
; the heroes' base atk / eva (D3-9b: xp_turn adds the §4.1 level steps to the
; kind_tab columns at runtime; hero_st_init writes these back on a new game)
KN_ATK          EQU 3
WZ_ATK          EQU 1
KN_EVA          EQU 2
WZ_EVA          EQU 1
kind_tab:
                ASSERT K_COUNT <= K_MAX            ; A6 review: every kind has a column
                ASSERT K_COUNT <= KROW_W           ; ... and KROW emits it (widen KROW first)
                ;     KN  WZ  RG  SK  GB  GH  RT  BT  SL
                KROW   3,  3,  3,  3,  3,  3,  4,  3,  3          ; KT_BW (cells)
                KROW BH_K_KNIGHT, BH_K_WIZARD, 0, BH_K_SKELETON, BH_K_GOBLIN, BH_K_GHOST, BH_K_RAT, BH_K_BAT, BH_K_SLIME ; KT_BH
                KROW  24, 16, 18, 10,  6,  7,  3,  3,  5          ; KT_HP
                KROW KN_ATK, WZ_ATK, 5, 2, 1, 2, 0, 1, 0          ; KT_ATK (hero columns: + level steps at runtime, D3-9b)
                KROW KN_EVA, WZ_EVA, 3, 2, 1, 3, 1, 4, 0          ; KT_EVA (hero_st_init restores KN_* / WZ_*)
                KROW   6,  4,  4,  4,  3,  4,  2,  2,  3          ; KT_DIE
                KROW   0,  0,  1,  0,  0,  0,  0,  0,  0          ; KT_BONUS
                KROW   1,  1,  1,  1,  1,  1,  1,  1,  1          ; KT_REACH (D3-0: the Mage's PROTO reach-3 zap is gone, game.md §11.4)
                KROW   1,  1,  1,  1,  1,  1,  1,  1,  2          ; KT_PERIOD
                ; B3B-5: skeleton + goblin are openers (game.md §9.1); the heroes
                ; open by bump in try_horizontal, not through KF_OPENER
                KROW KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER, KF_CLIMBER|KF_TALL|KF_OPENER, KF_CLIMBER|KF_OPENER, KF_FLYER, 0, KF_FLYER|KF_BAT, 0  ; KT_FLAGS
                KROW $47,$45,$44,$47,$44,$45,$06,$43,$44          ; KT_ATTR
                ; D3-4: + the class FX kinds K_FXW / K_FXM (ids 30 / 31, overlapping ranges)
                KROWFX KFID_KNIGHT, KFID_WIZARD, 0, KFID_SKELETON, KFID_GOBLIN, KFID_GHOST, KFID_RAT, KFID_BAT, KFID_SLIME, KFID_FXW, KFID_FXM     ; KT_FID0
                KROWFX KFCNT_KNIGHT, KFCNT_WIZARD, 0, KFCNT_SKELETON, KFCNT_GOBLIN, KFCNT_GHOST, KFCNT_RAT, KFCNT_BAT, KFCNT_SLIME, KFCNT_FXW, KFCNT_FXM ; KT_FCNT
                ASSERT K_FXW == K_MAX - 2 && K_FXM == K_MAX - 1    ; KROWFX: the last two columns
                ASSERT $ - kind_tab == KT_MOD9
                ; walker height (B3B-5 lead_cell, logic.asm): a non-flyer body
                ; never reaches a door's arch / lintel rows. Reads the bytes
                ; just assembled ({b}), so it covers every kind automatically.
                DUP K_COUNT, n
                ASSERT ({b kind_tab + KT_FLAGS + n} & KF_FLYER) || ({b kind_tab + KT_BH + n} <= STOREY_AIR - DOOR_PLANK_DY)
                EDUP
                ASSERT (KT_MOD9 >> 8) == ((KT_DIV9 + 23) >> 8)    ; feet_mod: one H for both
                ASSERT (KT_FID0 >> 8) == (KT_FCNT >> 8)            ; gen_kind: one H for both
                DUP 24, n
                DB   n % STOREY_ROWS           ; KT_MOD9
                EDUP
                ASSERT $ - kind_tab == KT_DIV9
                DUP 24, n
                DB   n / STOREY_ROWS           ; KT_DIV9
                EDUP
                ASSERT $ - kind_tab == KT_END
                ASSERT KT_END <= KT_SIZE           ; (the old "$1D0..$1FF spare, resistances 3F":
                                                   ; the resistances are bank-3 kx_tab since D3-0)
;------------------------------------------------------------------------------
; D3-8d: per-tick code right after kind_tab's arrays (code added before
; kind_tab beyond its ALIGN pad would move kind_tab a page; MEM-SND moved
; bars2.asm here to widen that pad for new hooks). No alignment needed.
;------------------------------------------------------------------------------
                INCLUDE "mark.asm"              ; D3-8d status marks (mark_tick, per tick)
                INCLUDE "xp2.asm"               ; D3-9b XP_NEXT table + item_mp (MP bar)
                INCLUDE "sfx2.asm"              ; SND-5 sfx_req / sfx_msg (any bank calls them)
                INCLUDE "bars2.asm"             ; MEM-SND bars_draw / num2 (from panel2.asm: pad headroom)

code_end:
IMAGE_LEN       EQU code_end - image_start
TAPE_CODE_LEN   EQU code_end - lowram_code     ; one CODE block: low-RAM cold + bank 2
                ASSERT start == lowram_code    ; USR target = first byte of the block
                ASSERT FDESC_COUNT == FID_COUNT    ; fdesc_tab and frame_tab: same frames
                ASSERT image_start == $8000
                ASSERT code_end <= FRT         ; the image ends below the frame runtime table
                ASSERT FRT + FRT_MAX * FRT_STRIDE <= P_ENTITIES
                ASSERT P_ENTITIES + P_MAX_ENT * P_ENT_STRIDE <= BANK2_FREE
                ASSERT DMG_LIST + DMG_MAX * 4 <= PEND_DMG
                ASSERT LOWRAM_END <= LOWRAM_FREE_END
                ASSERT lowram_code > TAPE_CLEAR    ; above the loader's RAMTOP
                DISPLAY "GAME image: $8000..", /H, code_end, " (", /D, IMAGE_LEN, " B), free to FRT: ", /D, FRT - code_end, " (+", /D, dt_attr_tab - kind_tab_pad, " B kind_tab ALIGN pad); HOT_COPY ", /H, HOT_COPY, ".. ", /D, PANEL_HOT_LEN, " B of ", /D, HOT_COPY_END - HOT_COPY, ", spare ", /D, HOT_COPY_END - HOT_COPY - PANEL_HOT_LEN

;==============================================================================
; BOOT BLOCK (3E-T1, memory levers a + d) — boot-only code + data at the TOP
; of pool bank 6 (boot6.asm): own headerless tape block (the last in `start`'s
; tape_tab), run by boot through farb before the pool is generated; the hero
; start's pool overwrites it later (dead after boot by contract).
;==============================================================================
                MMU  3, BANK_BOOT6
                ORG  $10000 - (boot6_end - boot6_code)
boot6_code:
                INCLUDE "boot6.asm"
boot6_end:
BOOT6_ADDR      EQU boot6_code
BOOT6_LEN       EQU boot6_end - boot6_code
                ASSERT boot6_end == $10000
                ; the boot pool (every monster kind + the 2 select idles, from
                ; POOL_START) must end below bank 6: boot6_tiles runs before it,
                ; but tests/game.py #50 checks the block after boot, at the menu
POOL_BOOT_NEED  EQU POOL_MONSTERS + 2 * 576 + 2 * 576   ; + 2 idles, + straddle waste
                ASSERT POOL_BOOT_NEED <= ($10000 - POOL_START) + $4000
                DISPLAY "GAME boot block (bank 6 tail): ", /H, boot6_code, "..$FFFF (", /D, BOOT6_LEN, " B: code ", /D, keytab_defaults - boot6_code, " + data ", /D, boot6_end - keytab_defaults, "), dead after boot"
                MMU  3, 0

;==============================================================================
; OVERLAYS (3E-T1) — code assembled at its runtime load address, stored
; ZX0-packed (bank 1 `ovl_blobs`), unpacked + called by ovl_run (lowram.asm;
; the GEN_SCRATCH window; the screen-2 window is 3E-T2's, docs/memory-map.md
; "Overlays"). Two assembler passes (tools/build.sh): OVL_PASS 1 assembles each
; raw image here — bank 0 scratch above tap_loader, pool at runtime, never
; loaded — and SAVEBINs it to build/ovl/<name>.bin; build.sh packs each .bin
; with tools/bin/zx0 -> <name>.zx0; pass 2 (OVL_PASS 2, the real build)
; INCBINs the streams and SAVEBINs the raw images again: build.sh fails if one
; changed between the passes. Rules for an overlay: no data the caller needs
; after it returns (the window is reused); returns like a routine; ASSERT its
; end against the window.
;==============================================================================
OVL_RAW_ORG     EQU $E100                       ; bank 0 scratch (after tap_loader, ASSERTed)
                ORG  OVL_RAW_ORG
ovl_raw_test:
                DISP GEN_SCRATCH
ovl_test:
                INCLUDE "ovl_test.asm"
ovl_test_end:
                ENT
OVL_TEST_LEN    EQU ovl_test_end - ovl_test
                ASSERT ovl_test_end <= GEN_SCRATCH + GEN_SCRATCH_LEN
                SAVEBIN "build/ovl/ovl_test.bin", ovl_raw_test, OVL_TEST_LEN
OVL_RAW_END     EQU $
                ASSERT OVL_RAW_END <= $10000

;------------------------------------------------------------------------------
; tap_loader — 10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "<start>"
; CLEAR 24575 frees $6000..$7FFF for the room maps / generator buffers and the
; low-RAM cold code. The USR address is emitted as 5 ASCII digits of `start`.
; Tokenised in a scratch ORG (page 0 at $E000; not part of the runtime image —
; bank 0 is overwritten by the pre-shift pool at boot; D3-TX: above the text
; block at the bottom of bank 0, ASSERTed).
;------------------------------------------------------------------------------
TAPE_CLEAR      EQU 24575
                ORG  $E000
tap_loader:
                DB   0, 10
                DW   tap_l10_end - tap_l10_body
tap_l10_body:   DB   $FD, $B0, '"', "24575", '"', $0D
tap_l10_end:
                DB   0, 20
                DW   tap_l20_end - tap_l20_body
tap_l20_body:   DB   $EF, $22, $22, $AF, $0D
tap_l20_end:
                DB   0, 30
                DW   tap_l30_end - tap_l30_body
tap_l30_body:   DB   $F9, $C0, $B0, '"'
                DB   '0' + (start / 10000) % 10, '0' + (start / 1000) % 10
                DB   '0' + (start / 100) % 10, '0' + (start / 10) % 10, '0' + start % 10
                DB   '"', $0D
tap_l30_end:
tap_loader_len  EQU  $ - tap_loader
                ASSERT $ <= OVL_RAW_ORG        ; 3E-T1: the overlay raw images follow

;==============================================================================
; Artefacts. SAVETAP dumps device memory at this point in source order (see
; main.asm's note), so it comes after every byte is assembled. Slot 1 = page 5
; and slot 2 = page 2 here, so the CODE block spans low-RAM cold + bank 2. The
; banked blocks are saved by mapping each bank into slot 3 ($C000) in turn.
;==============================================================================
    IF OVL_PASS == 2                    ; pass 1 (overlay images only) writes no tape / snapshot
                EMPTYTAP "build/wazhack.tap"
                SAVETAP  "build/wazhack.tap", BASIC, "wazhack", tap_loader, tap_loader_len, 10
                SAVETAP  "build/wazhack.tap", CODE,  "wazhack", lowram_code, TAPE_CODE_LEN
                TAPE_BLOCKS 1                  ; the headerless blocks = start's tape_tab
                MMU  3, 0
                SAVESNA  "build/wazhack.sna", boot
    ENDIF
