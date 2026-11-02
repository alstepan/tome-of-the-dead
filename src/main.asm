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
; 2); frame runtime table FRT $A800..$AFFF; runtime entity/render tables
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
                TAPE_BLK mode, BANK_TSET, B7_CODE, B7_LEN                 ; D3-S2 bank-7 cold code
                TAPE_BLK mode, BANK_TSET, TSET_BASE, B7D_LEN              ; level tilesets (w2a: dedup) + data7 (w2b), one block
                TAPE_BLK mode, BANK_TEXT, TEXT_ADDR, TEXT_TAPE_LEN        ; D3-TX text block (bank 0 bottom) + INSTR streams (boot only)
                TAPE_BLK mode, BANK_BOOT6, BOOT6_ADDR, BOOT6_TAPE_LEN     ; 3E-T1 boot block + SRC6 sources (bank 6, below R6)
                TAPE_BLK mode, BANK_R6, R6_ADDR, R6_USED                  ; R6 region (bank 6 top, permanent)
    ENDM
TAPE_HEADLESS_N EQU 8                   ; = the TAPE_BLK lines above (tape_tab ASSERTs its size)

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
; 3E-T4b: the RESIDENT item text (tools/itempack.py): it_words / it_wcx / it_name /
; it_stems. Nothing reads them yet (T10 item_name does); the fx / page overlay streams
; and it_stat are generated but not included (T8 / T13).
                DISP $ + TEXT_DISP
                INCLUDE "../build/text/items_tab.asm"
it_text_end:
                INCLUDE "itemname1.asm"         ; 3E-T10: item_name (no caller until T11)
IT_TEXT_LEN     EQU it_text_end - it_words
                ASSERT IT_TEXT_LEN == ITW_BYTES + 2 * ITW_WCX_N + ITN_BYTES + ITS_LEN && IT_TEXT_LEN <= ITB_RESIDENT
                ASSERT ITN_ROWS == IT_COUNT && it_stems_end - it_stems == ITS_LEN
                ASSERT it_wcx - it_words == ITW_BYTES && it_stems - it_name == ITN_BYTES
; MEM-1: the T6 items stream is back in bank 1 (was R6; BANK_OVL_ITEMS = BANK_UI1).
; Runtime $C000-window address, run by bank-3 level_new via ovl_run (C = bank 1).
; The page stream stays in R6 ("R6 REGION" below).
ovl_items_zx0:                                        ; 3E-T6 item / trap generator (items_ovl.asm, ITEMS_ORG)
    IF OVL_PASS == 2
                INCBIN "items.zx0"
    ENDIF
ovl_items_end:
; bank1_end = the end of the bank-1 block (runtime $C000-window address;
; tests/ovl.py uses the free tail above it).
bank1_end:
                ENT
bank1_img_end:
                ASSERT bank1_img_end <= BANK_WINDOW && bank1_end <= UI1_LIMIT
VIRT_TOTAL      EQU bank1_img_end - sprite_src
    IF VIRT_TOTAL > $4000
SRC_LEN_LO      EQU $4000
    ELSE
SRC_LEN_LO      EQU VIRT_TOTAL
    ENDIF
SRC_LEN_HI      EQU VIRT_TOTAL - SRC_LEN_LO
                ASSERT VIRT_TOTAL <= $8000
                DISPLAY "GAME sprite sources: ", /D, SRC_TOTAL, " B + vdata ", /D, VDATA_LEN, " B (bank1 ", /D, SRC_LEN_LO, ", free ", /D, $4000 - SRC_LEN_LO, "; bank3 ", /D, SRC_LEN_HI, ")"
                DISPLAY "GAME bank-1 UI code: ", /H, ui1_code, "..", /H, ui1_end, " (", /D, UI1_LEN, " B), bank 1 free: ", /D, UI1_LIMIT - bank1_end
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
; LEVEL TILESETS (B3B-8; MEM-RECLAIM w2a: deduplicated, 2,560 -> TSET_LEN B) —
; the 8 per-level tile sets (tools/tiles_convert.py, format TSET_* in
; level_defs.asm) in bank 7 above the shadow attrs (M0: from $FA40, the 3 spare
; PROTO attr rows), then (M0, levers L1 + L2) the HIGH bank-7 cold code
; b7h_code..b7h_end (same rules as bank7.asm: far7 only, no SMC, no data
; written; tests/gfx_integrity.py compares TSET_BASE..$FFFF after play) up to
; $10000. One headerless tape block TSET_BASE..b7h_end (B7D_LEN).
;==============================================================================
                MMU  3, BANK_TSET
                ORG  TSET_BASE
                INCLUDE "../assets/gfx/tiles/tilesets.asm"
TSET_LEN        EQU tilesets_end - tilesets
                MENU_TORCH_CHECK tset_pool     ; RECLAIM-C (d) + LOOK-1: the menu torch's glyphs (static run + the 2 flame
                                               ; frames) are these tset_pool glyphs (menu1 reads them, ldir7): byte-equal
b7h_code:
                INCLUDE "tiles7.asm"           ; MEM-RECLAIM w2a: level_tiles7 (M0: from the low bank-7 block)
    IF F3_GEN
                INCLUDE "sanct7.asm"           ; 3F-T10: sanctum_leaf (M0 L1: from R6, far7 from level_gen)
    ENDIF
b7h_end:
B7D_LEN         EQU b7h_end - TSET_BASE        ; tilesets + the high bank-7 code: one tape block
B7H_FREE        EQU $10000 - b7h_end
                ASSERT tilesets == TSET_BASE && tset_slots == TSET_BASE
                ASSERT tileset_d2 - tileset_d1 == TSET_STRIDE && tset_fsets - tset_slots == LEVELS * TSET_STRIDE
                ASSERT tset_pool - tset_fsets == TSET_NFSET * (TILE_IDS - TILE_COMMON) && TSET_NPOOL <= 256
                ASSERT b7h_end <= $10000

;==============================================================================
; BANK-7 COLD CODE (D3-S2; MEM-RECLAIM w2a: from $DB00, the old tileset slots
; 0..3) — B7_CODE (right after the screen-2 attrs) .. B7_LIMIT ($F800, the attr
; shadow): data7 (MEM-RECLAIM w2b read-only tables; M0: moved here from after
; the tilesets, first so its page ASSERTs never move), then the code. Entered
; only through far7 (rules: src/bank7.asm). One tape block B7_CODE..b7_end.
;==============================================================================
                ORG  B7_CODE
data7:
                INCLUDE "data7.asm"
data7_end:
b7_code:
                INCLUDE "bank7.asm"
b7_end:
B7_LEN          EQU b7_end - B7_CODE
                ASSERT B7_CODE == SCREEN7_ATTR + SCREEN_ATTR_LEN && b7_end <= B7_LIMIT && B7_LIMIT == SHADOW_ATTR
                DISPLAY "GAME bank-7 cold code: ", /H, B7_CODE, "..", /H, b7_end - 1, " (", /D, B7_LEN, " B incl. data7 ", /D, data7_end - data7, "), free to the attr shadow: ", /D, B7_LIMIT - b7_end
                DISPLAY "GAME bank-7 tilesets + high code (M0): ", /H, tilesets, "..", /H, b7h_end - 1, " (tilesets ", /D, TSET_LEN, " B, ", /D, TSET_NPOOL, " glyphs; code ", /D, b7h_end - b7h_code, " B), free to $10000: ", /D, B7H_FREE

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
; M0 (lever L4): the bank-0 cold code — cold event code right after the text,
; entered by farb with C = BANK_TEXT (FARB0, defs.asm), then a zero pad up to
; the FIXED POOL_START (defs.asm: TEXT_RES + B0_CODE_RES), so text or code
; growth inside the reserve moves no pool byte. Rules = bank3.asm's (no page_bank
; of $C000; blit_keep; helpers that page BANK_TEXT hand it back), no SMC: the
; block is compared with the .sna after play (tests/gfx_integrity.py, game.py #50).
b0_code:
                INCLUDE "log0.asm"             ; LOG-DMG: the log-line damage / HP tails (direct calls,
                                               ; BANK_TEXT already paged by impact_line / hit_line / msg_go)
    IF DEBUG_KIT
                INCLUDE "kit0.asm"                      ; DBG-1: the debug kit, kit builds only (keep LAST)
    ENDIF
b0_code_end:
B0_CODE_LEN     EQU b0_code_end - b0_code
B0_FREE         EQU POOL_START - b0_code_end
                ASSERT b0_code_end <= POOL_START        ; text + b0 code stay below the pool
    IF B0_FREE > 0
                DS   B0_FREE, 0                         ; the reserve (on the text tape block)
    ENDIF
; INSTR-BUILD: the HOW TO PLAY streams (page 1, 2, 3, then the overlay code:
; the code stream is last so no address an overlay reads depends on a packed
; size — instr_main reaches page n+1 as "past page n"). Boot only: on the text
; tape block (TEXT_TAPE_LEN), read by boot6_wait -> ovl_run before gen_idles,
; then the boot pool overwrites them (0 pool bytes; M0: POOL_START is fixed at $C960, defs.asm).
instr_p1_zx0:
    IF OVL_PASS == 2
                INCBIN "instr1.zx0"
    ENDIF
instr_p2_zx0:
    IF OVL_PASS == 2
                INCBIN "instr2.zx0"
    ENDIF
instr_p3_zx0:
    IF OVL_PASS == 2
                INCBIN "instr3.zx0"
    ENDIF
instr_zx0:
    IF OVL_PASS == 2
                INCBIN "instr.zx0"
    ENDIF
instr_zx0_end:
INSTR_P1_ZX0    EQU instr_p1_zx0
TEXT_TAPE_LEN   EQU instr_zx0_end - TEXT_ADDR
                ASSERT instr_p1_zx0 == POOL_START && instr_zx0_end <= tap_loader
                ASSERT text_base == TEXT_ADDR && TEXT_LEN == TEXT_PACKED
                ASSERT (tx_entries & $FF) == 0         ; w2d: tk_get's B = tx_entries >> 8
                ASSERT text_img_end <= tap_loader      ; the BASIC loader scratch ($E000, page 0)
                DISPLAY "GAME text (bank 0): ", /D, TX_COUNT, " strings, ", /D, TX_TOKENS, " tokens, raw ", /D, TEXT_RAW, " -> ", /D, TEXT_PACKED, " B packed at ", /H, text_base, "; pool from ", /H, POOL_START
                DISPLAY "GAME bank-0 cold code (M0 L4): ", /H, b0_code, " ", /D, B0_CODE_LEN, " B of ", /D, B0_CODE_RES, "; text ", /D, TEXT_LEN, " of TEXT_RES ", /D, TEXT_RES, " (headroom ", /D, TEXT_RES - TEXT_LEN, "); text + code reserve ", /D, POOL_START - TEXT_ADDR, " B, free to POOL_START: ", /D, B0_FREE

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
.panel:         ld   hl, GLOW_CNT              ; 3F-T8: the golden glow steps only on
                inc  (hl)                      ; ticks that may draw a panel item (boss2.asm)
                call panel_tick
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
.shown:         call keys_down                 ; C3-6b: raw 1..0 / ENTER (not FIRE: a
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
; glow_tab — boss2a.asm glow_kat's GOLDEN GLOW attr steps (BOSS-RANGED: moved out of the
; image tail into the kind_tab ALIGN pad, 4 of its 8 B, for ai_rhook's golden gate)
glow_tab:       DB   $06, $46, $47, $46
                ASSERT (glow_tab >> 8) == ((glow_tab + 3) >> 8)
kind_tab_pad:                                  ; ALIGN padding starts here (headroom)
                DS   (-($ + TILE_IDS)) & $FF, 0    ; B3B-5: tile_flags ends on the page
;------------------------------------------------------------------------------
; SEQ_ROWS — 3F-T2 the per-level sequence cache's rows (RUNTIME, written by R6
; pool6.asm / lowram.asm at a game start / level entry before any kind animates):
; SQ_SLOTS rows of KS_STRIDE (the old kind_seqs row: 8 sequence pointers +
; KS_IMPACT), slot 0 = the hero, 1.. = the level's monster kinds. One page
; (kind_tab KT_SEQ holds the row's low byte: kind_seq_ptr = 2 table reads, no
; multiply). 3F-T13bc: moved out of the image (was 119 zero bytes of the kind_tab
; ALIGN pad) into FRT_GAP; MEM-FT (FRT_MAX 144 fills the FRT page, FRT_GAP 0):
; directly BELOW the page-aligned FRT, runtime RAM above seq_bytes (ASSERTed).
;------------------------------------------------------------------------------
seq_rows        EQU FRT - SQ_ROWS_LEN
                ASSERT (seq_rows >> 8) == ((seq_rows + SQ_ROWS_LEN - 1) >> 8)
;------------------------------------------------------------------------------
; tile_flags — TILE_FLAGS[64] (D2, level_defs.asm TF_*), static, by tile id;
; the 64 B right below kind_tab (low byte $C0: cell_blocked adds the id with
; no carry, H constant). Placed in the ALIGN pad, so it costs no bank-2 bytes
; beyond its 64. Per-level ids 32..59 = 0 (decor), 60..63 = the FLOOR1 item markers T_ITEM0..+3 (flags 0)
; until the first level_load_tiles (B3B-8) overwrites 32..63 from the slot.
; Solidity belongs to the cell class (game.md §1.2 "Solidity of decor",
; designer 2026-10-03): the wall set (DARK = T_BRICK, DITHER, PATCH, FADE) is
; SOLID and only ever replaces wall cells; rubble / moss / cobweb /
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
                DB 0                                   ; 10 T_TRAP (revealed plate: walkable, game.md §1.5)
                DB 0, 0                                ; 11 door jamb (open door), 12 chain
                DB TF_SOLID | TF_FLOOR                 ; 13 T_GRATE_SHUT (3F-T8: the closed lair gate)
                DB 0                                   ; 14 door jamb
                DB TF_SOLID | TF_ATTACK, TF_SOLID | TF_ATTACK   ; 15-18 the Sanctum lectern (3F-T8, §9.7 R2;
                DB TF_SOLID | TF_ATTACK, TF_SOLID | TF_ATTACK   ; P3: build_room_map stamps them in the Sanctum)
                DB TF_FLOOR, TF_FLOOR                  ; 19-20 T_END_L/R = pit caps
                DB TF_SOLID, TF_SOLID                  ; 21-22 T_DOOR_ARCH_L/R
                DB TF_SOLID | TF_DOOR, TF_SOLID | TF_DOOR   ; 23-24 T_DOOR_L/R (closed planks)
                DB TF_SOLID | TF_DOOR | TF_LOCK        ; 25 T_DOOR_LOCK
                DB TF_LADDER | TF_HOLE                 ; 26 T_GRATE (B12: raised = the open exit hole)
                DB 0                                   ; 27 T_RUBBLE (decor at a block's foot)
                DB 0, 0, 0                             ; 28-30 T_WALL_DITHER / PATCH / FADE:
                                                       ; non-solid back-wall patches (D1 decor rule)
                DB 0                                   ; 31 free (DEC2)
                DS T_LVL_OBJ - TILE_COMMON, 0          ; 32-59 per-level decor
                DS T_LVL_OBJ_N, 0                      ; 60-63 FLOOR1 item markers T_ITEM0..+3 (the slot loads 0)
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
                ; 3F-T3: ids 0..8 | 9..17 (Spider Vampire Orc Archer Mummy Necro Ogre DK Archmage) |
                ; 18..29 (the tiers: Giant Rat, Rabbit Rat, Screech Bat, Slinger, Black Widow, Skel
                ; Guard, Skel Knight, Poltergeist, Orc Berserker, Orc Bouncer, Sniper, Bone Caller).
                ; The new rows follow game.md §9.1 / §9.6 (hp / atk / eva are the table values before
                ; depth scaling; die/bonus = the dmg column); 3F-T13: their BODY (BW/BH, defs.asm
                ; BH_K_*) and base inks are the real 3F-A1 art's. Legacy ids 0..8 are unchanged.
                ; 3F-T9: id 2 = K_VBAT, the Vampire's bat form: the Bat's body / flags / atk 1 eva 4 /
                ; 1d2 bite, every turn; the Vampire's hp row 14 (a banked bat's max hp, lp_spawn); VBAT-ART:
                ; the Bat's ink $43 (user: the bat form looks like a Bat).
                KROW   3,  3,  3,  3,  3,  3,  4,  3,  3,   4,  3,  3,  3,  3,  3,  4,  3,  3,   4,  4,  3,  3,  4,  3,  3,  3,  3,  3,  3,  3          ; KT_BW (cells; 3F-T13: Spider / Black Widow 32x16, Ogre 32x48)
                KROW BH_K_KNIGHT, BH_K_WIZARD, BH_K_BAT, BH_K_SKELETON, BH_K_GOBLIN, BH_K_GHOST, BH_K_RAT, BH_K_BAT, BH_K_SLIME, BH_K_SPIDER, BH_K_VAMPIRE, BH_K_ORC, BH_K_ARCHER, BH_K_MUMMY, BH_K_NECRO, BH_K_OGRE, BH_K_DKNIGHT, BH_K_ARCHMAGE, BH_K_RAT, BH_K_RAT, BH_K_BAT, BH_K_GOBLIN, BH_K_SPIDER, BH_K_SKELETON, BH_K_SKELETON, BH_K_GHOST, BH_K_ORC, BH_K_ORC, BH_K_ARCHER, BH_K_NECRO ; KT_BH
                KROW  24, 16, 14, 10,  6,  8,  3,  3,  6,   7, 14, 14,  8, 18, 12, 36, 50, 60,   5,  8,  5,  8, 10, 14, 18, 11, 18, 24, 10, 14          ; KT_HP
                KROW KN_ATK, WZ_ATK, 1, 2, 1, 2, 0, 1, 0,   3, 2, 3, 2, 3, 2, 4, 6, 4,   1, 2, 2, 2, 4, 3, 4, 3, 4, 5, 3, 3          ; KT_ATK (hero columns: + level steps at runtime, D3-9b)
                KROW KN_EVA, WZ_EVA, 4, 2, 1, 3, 1, 4, 0,   3, 1, 1, 2, 0, 2, 1, 3, 3,   1, 3, 4, 1, 3, 2, 2, 3, 0, 1, 2, 2          ; KT_EVA (hero_st_init restores KN_* / WZ_*)
                KROW   6,  4,  2,  4,  4,  4,  2,  2,  3,   4,  6,  8,  4,  8,  4, 10, 10,  6,   3,  4,  3,  4,  4,  6,  8,  4,  8, 10,  4,  4          ; KT_DIE
                KROW   0,  0,  0,  0,  0,  0,  0,  0,  0,   0,  0,  0,  0,  0,  0,  1,  3,  0,   0,  0,  0,  0,  0,  0,  0,  0,  2,  0,  0,  0          ; KT_BONUS
lp_wt:                                         ; MEM-RECLAIM w3: the old KT_REACH column (all 1: reach_ok / the hero's reach are literals) holds the §9.3
                LP_WT_ROWS                     ; weights, ONE copy read by bank 3 (kind_wt / levelgen) and R6 (lp_wt6 is gone): H = kind_tab page, L = $E0 + row
                DS   K_MAX - K_COUNT, 0
                ASSERT lp_wt == kind_tab + KT_REACH && K_COUNT <= K_MAX && (lp_wt & $FF) + K_COUNT <= $100
                ; RECLAIM-C (b): no KT_PERIOD column — KF_SLOW (acts every 2) on the Slime, Vampire, Mummy
                ; B3B-5: skeleton + goblin are openers (game.md §9.1); the heroes
                ; open by bump in try_horizontal, not through KF_OPENER. 3F-T3: climbers were only
                ; the Goblin, Skeleton (+ tiers) and the heroes (§9.7 R3); 3F-T13bc (user 2026-10-29):
                ; + the Orc (Berserker, Bouncer), Necro (Bone Caller), Archer (Sniper) on the shared
                ; climb pair; VAMP-BOSS (user 2026-11-02): + the Vampire (and the Lord) on the shared pair; not Archmage / DK / Ogre / Mummy; Mummy / Ogre / DK do not open doors
                KROW KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER, KF_FLYER|KF_BAT, KF_CLIMBER|KF_TALL|KF_OPENER, KF_CLIMBER|KF_OPENER, KF_FLYER, 0, KF_FLYER|KF_BAT, KF_SLOW, KF_CLIMBER, KF_CLIMBER|KF_OPENER|KF_TALL|KF_SLOW, KF_CLIMBER|KF_OPENER|KF_TALL, KF_CLIMBER|KF_OPENER|KF_TALL, KF_CLIMBER|KF_TALL|KF_SLOW, KF_CLIMBER|KF_OPENER|KF_TALL, KF_TALL, KF_TALL, KF_TALL, 0, 0, KF_FLYER|KF_BAT, KF_CLIMBER|KF_OPENER, KF_CLIMBER, KF_CLIMBER|KF_TALL|KF_OPENER, KF_CLIMBER|KF_TALL|KF_OPENER, KF_FLYER, KF_CLIMBER|KF_OPENER|KF_TALL, KF_CLIMBER|KF_OPENER|KF_TALL, KF_CLIMBER|KF_OPENER|KF_TALL, KF_CLIMBER|KF_OPENER|KF_TALL  ; KT_FLAGS
                KROW $47,$45,$43,$47,$44,$45,$06,$43,$44,   $05,$05,$04,$03,$06,$03,$44,$47,$04,   $02,$47,$05,$06,$02,$05,$44,$03,$02,$03,$04,$06          ; KT_ATTR (3F-T13: the 3F-A1 base inks — Spider $05, Orc $04, Necro $03, Mummy $06, Ogre $44, DK $47; Archer $03 (§9.8 D3-4); Vampire $05 / Archmage $04 differ from the Necro frames' other users; tiers §9.6)
                ; 3F-T2: KT_SEQ (runtime: lowram.asm (sq_load / sq_fill) writes the kind's SEQ_ROWS row
                ; low byte per level; 0 until the first game start). The old
                ; KT_FID0 / KT_FCNT columns are the R6 generation-unit table gu_tab.
                ASSERT $ - kind_tab == KT_DIV9          ; RECLAIM-C (b): DIV9, MOD9, then KT_SEQ
                ; walker height (B3B-5 lead_cell, logic.asm): a non-flyer body
                ; never reaches a door's arch / lintel rows. Reads the bytes
                ; just assembled ({b}), so it covers every kind automatically.
                DUP K_COUNT, n
                ASSERT ({b kind_tab + KT_FLAGS + n} & KF_FLYER) || ({b kind_tab + KT_BH + n} <= STOREY_AIR - DOOR_PLANK_DY)
                EDUP
                ; AI-L1 J1 proof (turn3.asm .at): every climber is FEAT_W wide, so the
                ; climb-start check over the whole shaft rect never sees a body in the
                ; climber's own end box that does not already overlap the climber
                DUP K_COUNT, n
                ASSERT !({b kind_tab + KT_FLAGS + n} & KF_CLIMBER) || ({b kind_tab + KT_BW + n} == FEAT_W) || (n == K_SPIDER) || (n == K_BLACK_WIDOW)   ; the 4-wide Spider (+ tier): fix/spider-climb
                EDUP
                ASSERT (KT_MOD9 >> 8) == ((KT_DIV9 + 23) >> 8) && (KT_DIV9 >> 8) == ((KT_MOD9 + 23) >> 8)  ; feet_mod: one H for both
                DUP 24, n
                DB   n / STOREY_ROWS           ; KT_DIV9
                EDUP
                DS   KT_MOD9 - KT_DIV9 - 24, 0 ; 8 B spare (3F-T2)
                ASSERT $ - kind_tab == KT_MOD9
                DUP 24, n
                DB   n % STOREY_ROWS           ; KT_MOD9
                EDUP
                ASSERT $ - kind_tab == KT_SEQ
                DS   K_MAX, 0                  ; KT_SEQ
                ASSERT ((kind_tab + KT_SEQ) & $FF) + K_MAX <= $100   ; KFIELD: no carry out of L
                ASSERT $ - kind_tab == KT_END
                ASSERT KT_END <= KT_SIZE           ; (the old "$1D0..$1FF spare, resistances 3F":
                                                   ; the resistances are bank-3 kx_tab since D3-0)
;------------------------------------------------------------------------------
; D3-8d: per-tick code right after kind_tab's arrays (code added before
; kind_tab beyond its ALIGN pad would move kind_tab a page; MEM-SND moved
; bars2.asm here to widen that pad for new hooks). No alignment needed.
;------------------------------------------------------------------------------
                ; ANIM-IMPORT2: ranged2 first (rk_tab must not straddle a page; mark.asm grew)
                INCLUDE "ranged2.asm"           ; 3F-T7 ai_rhook + rk_tab (the ranged hook's reject)
                INCLUDE "mark.asm"              ; D3-8d status marks (mark_tick, per tick)
                INCLUDE "xp2.asm"               ; D3-9b XP_NEXT table + item_mp (MP bar)
                INCLUDE "sfx2.asm"              ; SND-5 sfx_req / sfx_msg (any bank calls them)
                INCLUDE "bars2.asm"             ; MEM-SND bars_draw / num2 (from panel2.asm: pad headroom)
                INCLUDE "boss2a.asm"            ; 3F-T8 og_adv / glow_kat (AMMO-COUNT: after kind_tab, its pad was 6 B)
                INCLUDE "boss2.asm"             ; 3F-T8 golden stats / Ogre SLAM / PROVOKED / the glow's attr-only repaint
                INCLUDE "frt2.asm"              ; MEM-FT ft_ptr / frt_ptr / sel_frt_copy (were low RAM / gfx.asm)
                INCLUDE "msg2.asm"              ; LOG-FIX: msg_cat / msg_end (from bank 7), log_room, hit_line
                INCLUDE "fi3.asm"               ; FLOOR1 fi_full (cold; far3 callers unchanged): from bank 3 (LAND-PENDING relief)
                INCLUDE "ldir2.asm"             ; RECLAIM-C (d): ldir7 (bank-1 menu_static reads a bank-7 tileset run)
ftz_zx0:                                       ; MEM-FT frame_tab, FT_LEN B/fid contiguous, ZX0 (boot6_ft;
    IF OVL_PASS == 2                            ; bank 2: always mapped, on the CODE tape block; LAST in the
                INCBIN "ft.zx0"                 ; image so its pass-1/2 size moves only code_end)
    ENDIF
ftz_zx0_end:

code_end:
; 3F-T2: the sequence cache's bytes (RUNTIME only, not on tape: R6 pool6.asm / lowram.asm
; copies the hero's and the level's sequence blocks here; seq_rows point in)
seq_bytes       EQU code_end
seq_bytes_end   EQU seq_bytes + SEQB_LEN
IMAGE_LEN       EQU code_end - image_start
TAPE_CODE_LEN   EQU code_end - lowram_code     ; one CODE block: low-RAM cold + bank 2
                ASSERT start == lowram_code    ; USR target = first byte of the block
                ASSERT FDESC_COUNT == FID_COUNT    ; fdesc_tab and frame_tab: same frames
                ASSERT image_start == $8000
                ASSERT seq_bytes_end <= seq_rows   ; the image (+ the seq cache bytes) ends below seq_rows, then the FRT
                ASSERT FRT + FRT_MAX * FRT_STRIDE <= P_ENTITIES
                ASSERT P_ENTITIES + P_MAX_ENT * P_ENT_STRIDE <= BANK2_FREE
                ASSERT DMG_LIST + DMG_MAX * 4 <= PEND_DMG
                ASSERT LOWRAM_END <= LOWRAM_FREE_END
                ASSERT lowram_code > TAPE_CLEAR    ; above the loader's RAMTOP
                DISPLAY "GAME image: $8000..", /H, code_end, " (", /D, IMAGE_LEN, " B), seq cache bytes ", /D, SEQB_LEN, ", free to seq_rows: ", /D, seq_rows - seq_bytes_end, " (+", /D, tile_flags - kind_tab_pad, " B kind_tab ALIGN pad; bank 2 free ", /D, seq_rows - seq_bytes_end + tile_flags - kind_tab_pad, "; seq_rows ", /H, seq_rows, " ", /D, SQ_ROWS_LEN, " B, FRT ", /H, FRT, " ", /D, FRT_MAX, " rows (", /D, FRT_MAX - FID_COUNT, " spare), FRT_GAP ", /D, FRT_GAP, "); HOT_COPY ", /H, HOT_COPY, ".. ", /D, PANEL_HOT_LEN, " B of ", /D, HOT_COPY_END - HOT_COPY, ", spare ", /D, HOT_COPY_END - HOT_COPY - PANEL_HOT_LEN

;==============================================================================
; BOOT BLOCK (3E-T1, memory levers a + d) — boot-only code + data in pool
; bank 6 just BELOW the SRC6 region (boot6.asm; SRC6 spike: was just below R6;
; R6: was the top of bank 6): own headerless tape block, which runs on through
; the SRC6 sources (BOOT6_TAPE_LEN: one block, no extra pilot), run by boot
; through farb before the pool is generated; the hero start's pool overwrites
; it later (dead after boot by contract).
;==============================================================================
                MMU  3, BANK_BOOT6
                ORG  SRC6_ADDR - (boot6_end - boot6_code)
boot6_code:
                INCLUDE "boot6.asm"
boot6_end:
BOOT6_ADDR      EQU boot6_code
BOOT6_LEN       EQU boot6_end - boot6_code
                ASSERT boot6_end == SRC6_ADDR && boot6_code >= BANK_WINDOW   ; (3F-T13: a test build's 18 SRC6 pages still fit)
                ; the boot pool (3F-T1: the 2 select idles only, from POOL_START)
                ; must end below bank 6: boot6_tiles runs before it, but
                ; tests/game.py #50 checks the block after boot, at the menu
POOL_BOOT_NEED  EQU 2 * 576 + 576                        ; 2 idles + straddle waste
                ASSERT POOL_BOOT_NEED <= ($10000 - POOL_START) + $4000
                DISPLAY "GAME boot block (bank 6, below SRC6): ", /H, boot6_code, "..", /H, boot6_end - 1, " (", /D, BOOT6_LEN, " B: code ", /D, keytab_defaults - boot6_code, " + data ", /D, boot6_end - keytab_defaults, "), dead after boot"

;==============================================================================
; SRC6 REGION (SRC6 spike, 3F memory plan) — PERMANENT bank-6 sprite SOURCES,
; SRC6_ADDR..R6_ADDR-1 (SRC6_LEN = SRC6_PAGES pages, defs.asm), carved out of
; the pool 1:1 (POOL_CAP - SRC6_LEN; alloc stops at POOL6_END = SRC6_ADDR).
; ZX0 blocks only, generated by tools/zx0_sources.py (build/zx0/src6_zx0.asm;
; until 3F art exists: the 3F pool-spike STAND-IN blocks picked by the
; SRC6_STANDIN mask). Read only by zx0_frame (FD_BLK = real - SRC6_VDELTA);
; never written at runtime (tests/zx0_pool.py compares it at every point).
; Tape: the tail of the boot block's tape block (BOOT6_TAPE_LEN); the free
; bytes SRC6_FREE above the blocks are not on tape.
;==============================================================================
                ORG  SRC6_ADDR
src6_blocks:
                INCLUDE "../build/zx0/src6_zx0.asm"
src6_end:
SRC6_USED       EQU src6_end - SRC6_ADDR
SRC6_FREE       EQU R6_ADDR - src6_end
BOOT6_TAPE_LEN  EQU src6_end - BOOT6_ADDR
    IF src6_end > R6_ADDR
                DISPLAY "SRC6 OVERFLOW: ", /D, src6_end - R6_ADDR, " B over SRC6_LEN ", /D, SRC6_LEN
    ENDIF
                ASSERT src6_end <= R6_ADDR && SRC6_USED > 0
                DISPLAY "GAME SRC6 sources (bank 6): ", /H, SRC6_ADDR, "..", /H, R6_ADDR - 1, " (", /D, SRC6_USED, " of ", /D, SRC6_LEN, " B: ", /D, SRC6_BLOCKS, " blocks, ", /D, SRC6_RAW, " raw), SRC6 free: ", /D, SRC6_FREE, " (pool slack: the GAME frames line)"

;==============================================================================
; R6 REGION (2026-10-21) — PERMANENT code + data at the top of bank 6,
; R6_ADDR..$FFFF (R6_LEN, defs.asm), carved out of the pool (POOL_CAP -
; R6_LEN; alloc stops below R6_ADDR in bank 6). Own headerless tape block
; (the last; R6_USED bytes). Resident code first (r6.asm, entered through
; far6), then the packed overlay streams LAST (r6_blobs; ovl_run C = BANK_R6),
; so their sizes move nothing an overlay can reference (2-pass overlay build).
; Later tasks put their code / overlay streams / sprite sources here: R6_LEN
; is the cap (the ASSERT below; the DISPLAY prints the free bytes).
;==============================================================================
                ORG  R6_ADDR
r6_code:
                INCLUDE "r6.asm"
r6_code_end:
r6_blobs:
ovl_page_zx0:                                         ; 3E-T2 bag page (page_ovl.asm, PAGE_ORG)
    IF OVL_PASS == 2
                INCBIN "page.zx0"
    ENDIF
sqm_zx0:                                              ; 3F-T2 sequence masters (seq_img.asm, SQ_IMG)
    IF OVL_PASS == 2
                INCBIN "seq.zx0"
    ENDIF
sqm_zx0_end:
r6_blobs_end:
r6_end:
R6_USED         EQU r6_end - R6_ADDR
R6_FREE         EQU $10000 - r6_end
    IF r6_end > $10000
                DISPLAY "R6 OVERFLOW: ", /D, r6_end - $10000, " B over R6_LEN ", /D, R6_LEN
    ENDIF
                ASSERT r6_end <= $10000 && R6_USED > 0
                DISPLAY "GAME R6 region (bank 6): ", /H, R6_ADDR, "..", /H, r6_end - 1, " (", /D, R6_USED, " of ", /D, R6_LEN, " B: code ", /D, r6_code_end - r6_code, " + overlay streams ", /D, r6_blobs_end - r6_blobs, "), R6 free: ", /D, R6_FREE
                MMU  3, 0

;==============================================================================
; LEVEL POOL NEED (3F-T1) — the worst depth's monster pool, computed from the
; ASSEMBLED bytes (sjasmplus {b}: every table below is emitted earlier in the
; pass), so it cannot drift from what level_enter generates:
;   lp_dtab (bank 3: LP_KINDS + LP_BOSS per depth) -> pool_gmap (R6, the
;   generation map, pool_map's rule) + pool_xmap (3F-T2 hero extras; 3F-T3: counted PER HERO — the
;   level need is computed for the Warrior and the Mage separately, POOL_NEED = the larger) -> the set of generation units (dedup per unit, as
;   pool_list) -> R6 gu_tab fid0 / fcnt (3F-T2; was kind_tab) -> per fid
;   frame_tab cols / H / offsets + fdesc_tab FD_FLAGS -> the exact bytes
;   gen_frame allocates (variant choice as gen_facing); MEM-PS2: the per-bank
;   straddle waste is SIMULATED exactly (PS_* below; was POOL_FIXED's 3 x 576).
; POOL_NEED = max over hero x depth of the simulated pool top + POOL_SIM_MARGIN.
; -DPOOL_LVL_VERBOSE=1 DISPLAYs every depth.
;==============================================================================
    MACRO PL_FRAME_ADD fid                     ; PLN += gen_frame's pool bytes for fid
PLF_C = {b frame_tab + (fid) * FT_STRIDE + FT_COLS}
PLF_H = {b frame_tab + (fid) * FT_STRIDE + FT_H}
PLF_R = {b frame_tab + (fid) * FT_STRIDE + FT_OFFR}
PLF_L = {b frame_tab + (fid) * FT_STRIDE + FT_OFFL}
PLF_F = {b fdesc_tab + (fid) * FDESC_STRIDE + FD_FLAGS}
      IF PLF_F & FF_MOTION                     ; both shifts per facing
        IF PLF_F & FF_SYM
PLN = PLN + PLF_H * 2 * (2 * PLF_C + 1)
        ELSE
PLN = PLN + 2 * PLF_H * 2 * (2 * PLF_C + 1)
        ENDIF
      ELSE                                     ; one shift per facing (+1 col if shifted)
PLN = PLN + PLF_H * 2 * (PLF_C + ((((PLF_R + (PLF_F & FF_PH4)) & 7) != 0) & 1))
        IF (PLF_F & FF_SYM) == 0
PLN = PLN + PLF_H * 2 * (PLF_C + ((((PLF_L + (PLF_F & FF_PH4)) & 7) != 0) & 1))
        ENDIF
      ENDIF
    ENDM
    MACRO PL_UNIT u                            ; PLM / PLX |= unit u (units < 64)
      IF (u) < 32
PLM = PLM | (1 << (u))
      ELSE
PLX = PLX | (1 << ((u) - 32))
      ENDIF
    ENDM
    MACRO PL_KIND k                            ; kind k's generation units (pool6.asm pl_kinds)
                ASSERT (k) < K_MAX
PLK_HIT = 0
      IF PGMAP_N
        DUP PGMAP_N, plr                       ; 3F-T13: every record of the kind applies
          IF {b pool_gmap + 3 * plr} == (k)
PLK_HIT = 1
                PL_UNIT {b pool_gmap + 3 * plr + 1}
            IF {b pool_gmap + 3 * plr + 2} != PG_NONE
                PL_UNIT {b pool_gmap + 3 * plr + 2}
            ENDIF
          ENDIF
        EDUP
      ENDIF
      IF PLK_HIT == 0
                PL_UNIT k
      ENDIF
      IF PXMAP_N                               ; 3F-T3 hero extras: only the records of the hero
        DUP PXMAP_N, plx                       ; being computed (PL_HERO): a Mage's arrow frames
          IF ({b pool_xmap + 3 * plx} == (k)) && ({b pool_xmap + 3 * plx + 1} == PL_HERO)
                PL_UNIT {b pool_xmap + 3 * plx + 2}   ; never inflate the Warrior's need
          ENDIF
        EDUP
      ENDIF
    ENDM
    MACRO PL_UNITS_ADD m, ubase                ; PLN += the frames of every unit in mask m
                DUP  32, plk
      IF ((m) >> plk) & 1
PLK_F0 = {b gu_tab + GU_STRIDE * ((ubase) + plk)}
PLK_FN = {b gu_tab + GU_STRIDE * ((ubase) + plk) + 1}
        IF PLK_FN
                DUP  PLK_FN, plf
                PL_FRAME_ADD PLK_F0 + plf
                EDUP
        ENDIF
      ENDIF
                EDUP
    ENDM
;------------------------------------------------------------------------------
; MEM-PS2: the POOL SIMULATION — alloc / gen_frame / gen_facing / pl_unit /
; gen_list replayed variant by variant at build time, in the real session order:
;   gen_idles (alloc_reset: POOL_START; knight_idle1, wizard_idle), pool_hero
;   (the hero unit, then its class FX unit), alloc_mark; per level alloc_restore
;   + pool_list (LP_KINDS[0..3] + LP_BOSS = the lp_dtab row: each kind's pool_gmap
;   records in order, else its own unit, then its pool_xmap extras; a unit whose
;   fid0 is listed already is skipped, the listed range takes the longest count:
;   pl_unit .same); PROTO: pool_proto after the mark (bank-6 limit R6_ADDR).
; Every variant goes through PS_ALLOC = alloc (a variant that does not fit the
; bank's rest skips to the next bank; bank 6 ends at the limit; ending exactly at
; $10000 opens the next bank). The result PS_USED = the linear pool top (bank 0
; from POOL_START, a skipped tail counts as used) = what tests/zx0_pool.py reads
; back as ALLOC_IDX / ALLOC_PTR: replaces POOL_FIXED's 3 x 576 straddle guess.
; Final pass only ({b}); no bytes emitted.
;------------------------------------------------------------------------------
    MACRO PS_ALLOC n                           ; alloc BC = n (PS_IDX / PS_PTR / PS_OVF)
PSA_N = (n)
PSA_D = 0
                DUP  3
      IF PSA_D == 0 && PS_IDX < 3
        IF PS_IDX == 2
PSA_L = PS_LIM6
        ELSE
PSA_L = $10000
        ENDIF
        IF PS_PTR + PSA_N <= PSA_L
PS_PTR = PS_PTR + PSA_N
PSA_D = 1
          IF PS_PTR == $10000                  ; alloc .same: the next alloc opens the next bank
PS_PTR = BANK_WINDOW
PS_IDX = PS_IDX + 1
          ENDIF
        ELSE                                   ; alloc_next
PS_IDX = PS_IDX + 1
PS_PTR = BANK_WINDOW
        ENDIF
      ENDIF
                EDUP
      IF PSA_D == 0
PS_OVF = 1                                     ; GEN_OVERFLOW
      ENDIF
    ENDM
    MACRO PS_FRAME fid                         ; gen_frame: right facing, then left unless FF_SYM
PSF_C = {b frame_tab + (fid) * FT_STRIDE + FT_COLS}
PSF_H = {b frame_tab + (fid) * FT_STRIDE + FT_H}
PSF_R = {b frame_tab + (fid) * FT_STRIDE + FT_OFFR}
PSF_L = {b frame_tab + (fid) * FT_STRIDE + FT_OFFL}
PSF_F = {b fdesc_tab + (fid) * FDESC_STRIDE + FD_FLAGS}
      IF PHASE_SHIFT                           ; gen_facing .stat: (anchor + FF_PH4) & 7
PSF_P = PSF_F & FF_PH4
      ELSE
PSF_P = 0
      ENDIF
      IF PSF_F & FF_MOTION                     ; shift 0 then shift 4 (+1 col)
                PS_ALLOC 2 * PSF_H * PSF_C
                PS_ALLOC 2 * PSF_H * (PSF_C + 1)
        IF (PSF_F & FF_SYM) == 0
                PS_ALLOC 2 * PSF_H * PSF_C
                PS_ALLOC 2 * PSF_H * (PSF_C + 1)
        ENDIF
      ELSE
                PS_ALLOC 2 * PSF_H * (PSF_C + ((((PSF_R + PSF_P) & 7) != 0) & 1))
        IF (PSF_F & FF_SYM) == 0
                PS_ALLOC 2 * PSF_H * (PSF_C + ((((PSF_L + PSF_P) & 7) != 0) & 1))
        ENDIF
      ENDIF
    ENDM
    MACRO PS_INMASK m, x, v                    ; PSV_IN = bit v of the 64-bit unit set m / x
      IF (v) < 32
PSV_IN = ((m) >> (v)) & 1
      ELSE
PSV_IN = ((x) >> ((v) - 32)) & 1
      ENDIF
    ENDM
    MACRO PS_UNIT u                            ; pl_unit u, then gen_list's frames for it
PSU_F0 = {b gu_tab + GU_STRIDE * (u)}
PSU_N = {b gu_tab + GU_STRIDE * (u) + 1}
PSU_GO = PSU_N != 0                            ; 0-frame unit: nothing
      IF PSU_GO
                DUP  GU_N, psv                 ; listed already (a done unit, same fid0)
                PS_INMASK PSD_M, PSD_X, psv
        IF PSV_IN
          IF {b gu_tab + GU_STRIDE * psv} == PSU_F0
PSU_GO = 0
          ENDIF
        ENDIF
                EDUP
      ENDIF
      IF PSU_GO
                DUP  GU_N, psv                 ; pl_unit .same: the range = the session's longest
                PS_INMASK PSS_M, PSS_X, psv    ; unit with this fid0 (all later: this is the first)
        IF PSV_IN
          IF {b gu_tab + GU_STRIDE * psv} == PSU_F0 && {b gu_tab + GU_STRIDE * psv + 1} > PSU_N
PSU_N = {b gu_tab + GU_STRIDE * psv + 1}
          ENDIF
        ENDIF
                EDUP
PSU_F = PSU_F0
                DUP  PSU_N
                PS_FRAME PSU_F
PSU_F = PSU_F + 1
                EDUP
      ENDIF
      IF (u) < 32
PSD_M = PSD_M | (1 << (u))
      ELSE
PSD_X = PSD_X | (1 << ((u) - 32))
      ENDIF
    ENDM
    MACRO PS_KIND k                            ; pl_kinds for kind k (PL_KIND's walk, in order)
PSK_HIT = 0
      IF PGMAP_N
        DUP PGMAP_N, psr
          IF {b pool_gmap + 3 * psr} == (k)
PSK_HIT = 1
PSK_U2 = {b pool_gmap + 3 * psr + 2}
PSK_U = {b pool_gmap + 3 * psr + 1}
                PS_UNIT PSK_U
            IF PSK_U2 != PG_NONE
PSK_U = PSK_U2
                PS_UNIT PSK_U
            ENDIF
          ENDIF
        EDUP
      ENDIF
      IF PSK_HIT == 0
                PS_UNIT k
      ENDIF
      IF PXMAP_N
        DUP PXMAP_N, psx
          IF ({b pool_xmap + 3 * psx} == (k)) && ({b pool_xmap + 3 * psx + 1} == PL_HERO)
PSK_U = {b pool_xmap + 3 * psx + 2}
                PS_UNIT PSK_U
          ENDIF
        EDUP
      ENDIF
    ENDM
    MACRO PS_LINEAR                            ; PS_USED = the linear pool top (+ $10000 on overflow)
      IF PS_IDX == 0
PS_USED = PS_PTR - POOL_START
      ELSE
        IF PS_IDX == 1
PS_USED = ($10000 - POOL_START) + (PS_PTR - BANK_WINDOW)
        ELSE
PS_USED = ($10000 - POOL_START) + $4000 + (PS_PTR - BANK_WINDOW)
        ENDIF
      ENDIF
      IF PS_OVF
PS_USED = PS_USED + $10000
      ENDIF
    ENDM
POOL_NEED = 0
POOL_LVL_MAX = 0
POOL_LVL_WORST = 0
POOL_SIM_PROTO = 0                             ; the worst simulated PROTO top (both heroes, 6 kinds)
                DUP  2, plh                    ; 3F-T3: per hero (K_KNIGHT = 0, K_WIZARD = 1)
PL_HERO = plh
      IF plh == K_KNIGHT
PL_HERO_B = POOL_KNIGHT + POOL_FXW
      ELSE
PL_HERO_B = POOL_WIZARD + POOL_FXM
      ENDIF
PL_MAX = 0
PL_WORST = 0
                MMU  3, BANK_R6
                ; MEM-PS2 hero session: gen_idles + pool_hero + gen_list, then alloc_mark
PS_IDX = 0
PS_PTR = POOL_START
PS_OVF = 0
PS_LIM6 = POOL6_END
                PS_FRAME FID_knight_idle1
                PS_FRAME FID_wizard_idle
PSS_M = (1 << plh) | (1 << (plh + K_FX_BASE))
PSS_X = 0
PSD_M = 0
PSD_X = 0
                PS_UNIT plh
                PS_UNIT plh + K_FX_BASE
                ASSERT {b gu_tab + GU_STRIDE * plh} != {b gu_tab + GU_STRIDE * (plh + K_FX_BASE)}
                ASSERT PS_OVF == 0
PSM_IDX = PS_IDX                               ; the LEVEL mark
PSM_PTR = PS_PTR
                ; MEM-PS2 PROTO fixture (pool_proto after the mark, bank-6 limit R6_ADDR; 6 kinds =
                ; proto_start 3, the 5-kind default without the Slime is DISPLAYed too for the test)
                DUP  2, psp
PLM = 0
PLX = 0
                DUP  K_PROTO_END - K_SKELETON - 1 + psp, psk
                PL_KIND K_SKELETON + psk
                EDUP
PSS_M = PLM
PSS_X = PLX
PSD_M = 0
PSD_X = 0
PS_IDX = PSM_IDX
PS_PTR = PSM_PTR
PS_LIM6 = R6_ADDR
                DUP  K_PROTO_END - K_SKELETON - 1 + psp, psk
                PS_KIND K_SKELETON + psk
                EDUP
                PS_LINEAR
      IFDEF POOL_LVL_VERBOSE
                DISPLAY "GAME pool sim PROTO kinds ", /D, K_PROTO_END - K_SKELETON - 1 + psp, " hero ", /D, plh, ": top idx ", /D, PS_IDX, " ptr ", /D, PS_PTR, " used ", /D, PS_USED, " of ", /D, POOL_CAP + SRC6_LEN
      ENDIF
      IF psp && PS_USED > POOL_SIM_PROTO
POOL_SIM_PROTO = PS_USED
      ENDIF
                EDUP
PS_LIM6 = POOL6_END
                DUP  LEVELS, pld
                MMU  3, BANK_COLD3
PLK0 = {b lp_dtab + pld * LP_DROW + 0}
PLK1 = {b lp_dtab + pld * LP_DROW + 1}
PLK2 = {b lp_dtab + pld * LP_DROW + 2}
PLK3 = {b lp_dtab + pld * LP_DROW + 3}
PLK4 = {b lp_dtab + pld * LP_DROW + 4} & LEK_KIND_MASK   ; (3F-T5: the golden bit is not part of the kind)
                MMU  3, BANK_R6
PLM = 0
PLX = 0
                PL_KIND PLK0
                PL_KIND PLK1
                PL_KIND PLK2
                PL_KIND PLK3
                PL_KIND PLK4
                ; MEM-PS2: the level session replayed (PSS = the full unit set, before the
                ; VBAT strip below: PS_UNIT merges same-fid0 units itself)
PSS_M = PLM
PSS_X = PLX
PSD_M = 0
PSD_X = 0
PS_IDX = PSM_IDX                               ; alloc_restore
PS_PTR = PSM_PTR
PS_OVF = 0
                PS_KIND PLK0
                PS_KIND PLK1
                PS_KIND PLK2
                PS_KIND PLK3
                PS_KIND PLK4
                PS_LINEAR
PS_NEED = PS_USED + POOL_SIM_MARGIN
      IF (PLM >> K_BAT) & 1                    ; 3F-T9: the bat form's frames lie inside the Bat's
PLM = PLM & ~(1 << K_VBAT)                     ; unit (same fid0: pl_unit merges them)
      ENDIF
                ASSERT {b gu_tab + GU_STRIDE * K_VBAT} == {b gu_tab + GU_STRIDE * K_BAT} && {b gu_tab + GU_STRIDE * K_VBAT + 1} <= {b gu_tab + GU_STRIDE * K_BAT + 1}
PLN = 0
                PL_UNITS_ADD PLM, 0
      IF PLX
                PL_UNITS_ADD PLX, 32
      ENDIF
PLU = 0                                        ; 3F-T13: the level's units fit PL_LIST
                DUP  32, plb
PLU = PLU + ((PLM >> plb) & 1) + ((PLX >> plb) & 1)
                EDUP
                ASSERT 2 * PLU + 1 <= PL_CAP
      IFDEF POOL_LVL_VERBOSE
                DISPLAY "GAME level pool D", /D, pld + 1, " hero ", /D, plh, ": units mask ", /H, PLM, " / ", /H, PLX, ", ", /D, PLN, " B; need ", /D, PS_NEED, " of ", /D, POOL_CAP, " (sim top idx ", /D, PS_IDX, " ptr ", /D, PS_PTR, " used ", /D, PS_USED, ", straddle waste ", /D, PS_USED - PLN - PL_HERO_B - 2 * (knight_idle1_h + wizard_idle_h) * 2 * 3, ")"
      ENDIF
      IF PS_NEED > PL_MAX
PL_MAX = PS_NEED
PL_WORST = pld + 1
PL_LVLB = PLN
      ENDIF
                EDUP
      IF PL_MAX > POOL_NEED
POOL_NEED = PL_MAX
POOL_LVL_MAX = PL_LVLB
POOL_LVL_WORST = PL_WORST
      ENDIF
                EDUP
                MMU  3, 0
                ASSERT LP_DROW == 6 && K_MAX <= 32 && GU_N <= 64
    IF POOL_NEED > POOL_CAP
                DISPLAY "POOL FULL: need ", /D, POOL_NEED, " (worst D", /D, POOL_LVL_WORST, ") > POOL_CAP ", /D, POOL_CAP, " (SRC6_LEN ", /D, SRC6_LEN, ")"
    ENDIF
    ; 3F-T13: -DPOOL_LVL_CHECK=0 = a TEST build that never descends (tests/zx0_pool.py's src6
    ; variant: 18 SRC6 pages; the D7 need is then over POOL_CAP, its D1 sessions fit)
    IFNDEF POOL_LVL_CHECK
POOL_LVL_CHECK  EQU 1
    ENDIF
                ASSERT POOL_NEED <= POOL_CAP || !POOL_LVL_CHECK
    ; 3F-T2: -DPOOL_PROTO_CHECK=0 = a TEST build that never enters the PROTO
    ; rooms (tests/zx0_pool.py's src6 variant: 9 SRC6 pages; the PROTO need is
    ; then over POOL_CAP and a PROTO start would overflow the pool)
    IFNDEF POOL_PROTO_CHECK
POOL_PROTO_CHECK EQU 1
    ENDIF
    ; 3F-T3: the PROTO fixture's default pool omits the Slime (proto_start bit PS_SLIME_BIT, pool_proto);
    ; tests poke proto_start = 3 (all six kinds). 3F-T13: a PROTO game pools over the SRC6 sources too
    ; (pool_proto moves alloc's bank-6 limit to R6_ADDR: rooms A-D hold no 3F kind and no stairs), so
    ; its cap is POOL_CAP + SRC6_LEN and the 6-kind fixture's conservative bound is asserted again.
POOL_CAP_PROTO  EQU POOL_CAP + SRC6_LEN
PLN = 0
                DUP  KFCNT_SLIME, pls
                PL_FRAME_ADD KFID_SLIME + pls
                EDUP
POOL_SLIME_B = PLN
POOL_NEED_PROTO5 = POOL_NEED_PROTO - POOL_SLIME_B
    IF POOL_NEED_PROTO > POOL_CAP_PROTO
                DISPLAY "PROTO POOL FULL: the PROTO rooms (6 kinds) need ", /D, POOL_NEED_PROTO, " > POOL_CAP + SRC6_LEN ", /D, POOL_CAP_PROTO
    ENDIF
                ASSERT POOL_NEED_PROTO <= POOL_CAP_PROTO || !POOL_PROTO_CHECK
                ASSERT POOL_SIM_PROTO + POOL_SIM_MARGIN <= POOL_CAP_PROTO || !POOL_PROTO_CHECK   ; MEM-PS2 (the static bound above is the looser)
                DISPLAY "GAME frames: ", /D, FID_COUNT, "  pool need: ", /D, POOL_NEED, " of ", /D, POOL_CAP, " (MEM-PS2 simulated top + margin ", /D, POOL_SIM_MARGIN, "; worst level D", /D, POOL_LVL_WORST, " ", /D, POOL_LVL_MAX, ", hero max ", /D, POOL_HERO_MAX, "; text ", /D, POOL_START - BANK_WINDOW, " B under bank 0); slack ", /D, POOL_CAP - POOL_NEED, " after SRC6 ", /D, SRC6_LEN, " B; PROTO rooms (6 kinds, over SRC6) ", /D, POOL_NEED_PROTO, " of ", /D, POOL_CAP_PROTO, " (slack ", /D, POOL_CAP_PROTO - POOL_NEED_PROTO, "; 5 kinds ", /D, POOL_NEED_PROTO5, ")"

;==============================================================================
; OVERLAYS (3E-T1) — code assembled at its runtime load address, stored
; ZX0-packed (R6 `r6_blobs`, bank 6), unpacked + called by ovl_run (lowram.asm;
; the GEN_SCRATCH window: at boot / menu / level start, or — ROOM_MAP saved
; to PAGE_MAP_SAVE — while the modal bag page is up; docs/memory-map.md
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
ovl_raw_page:
                DISP PAGE_ORG
page_ovl_main:
                INCLUDE "page_ovl.asm"
page_ovl_end:
                ENT
PAGE_OVL_LEN    EQU page_ovl_end - page_ovl_main
                ASSERT page_ovl_end <= PAGE_LIMIT
                ASSERT PAGE_MAP_SAVE + PLAY_CELLS <= TX_DEC     ; mf_tx decodes into TX_DEC on the page
                ASSERT PAGE_MAP_SAVE >= GEN_SCRATCH + GEN_SCRATCH_LEN
                SAVEBIN "build/ovl/page.bin", ovl_raw_page, PAGE_OVL_LEN
ovl_raw_items:
                DISP ITEMS_ORG
items_ovl_main:
                INCLUDE "items_ovl.asm"
                ENT
ITEMS_OVL_LEN   EQU ig_image_end - items_ovl_main
                ASSERT ig_end <= GEN_SCRATCH + GEN_SCRATCH_LEN
                SAVEBIN "build/ovl/items.bin", ovl_raw_items, ITEMS_OVL_LEN
                DISPLAY "GAME items overlay (3E-T6): ", /D, ITEMS_OVL_LEN, " B raw (+ ", /D, ig_end - ig_image_end, " B scratch) at ", /H, ITEMS_ORG, ", packed ", /D, ovl_items_end - ovl_items_zx0, " B in bank ", /D, BANK_OVL_ITEMS
                DISPLAY "GAME page overlay: ", /D, PAGE_OVL_LEN, " B raw (", /D, PAGE_LIMIT - page_ovl_end, " left)"
;------------------------------------------------------------------------------
; 3F-T2 sequence masters (seq_img.asm): raw image DISPed at SQ_IMG, packed into
; R6 sqm_zx0 (pool6.asm unpacks it per pool_* call). Ends below TX_DEC (the
; GEN_SRC / GEN_MIR window it borrows; pool6.asm header).
;------------------------------------------------------------------------------
ovl_raw_seq:
                DISP SQ_IMG
seq_img_main:
                INCLUDE "seq_img.asm"
seq_img_end:
                ENT
SEQ_IMG_LEN     EQU seq_img_end - seq_img_main
                ASSERT SQ_IMG + SEQ_IMG_LEN <= TX_DEC
                SAVEBIN "build/ovl/seq.bin", ovl_raw_seq, SEQ_IMG_LEN
                DISPLAY "GAME sequence masters (3F-T2): ", /D, SEQ_IMG_LEN, " B raw at ", /H, SQ_IMG, " (", /D, TX_DEC - SQ_IMG - SEQ_IMG_LEN, " left), packed ", /D, sqm_zx0_end - sqm_zx0, " B in R6"
;------------------------------------------------------------------------------
; MEM-FT frame_tab stream: the entries read back ({b}, slot 2 = page 2) from the
; FRT row image data.asm assembled at FRT, contiguous FT_LEN B per fid; packed
; into R6 ftz_zx0, boot6_ft spreads it into the FRT rows. (124 B packed vs 516.)
;------------------------------------------------------------------------------
ovl_raw_ft:
                DUP  FID_COUNT, ftf
                DB   {b frame_tab + ftf * FT_STRIDE + 0}, {b frame_tab + ftf * FT_STRIDE + 1}
                DB   {b frame_tab + ftf * FT_STRIDE + 2}, {b frame_tab + ftf * FT_STRIDE + 3}
                EDUP
                ASSERT $ - ovl_raw_ft == FID_COUNT * FT_LEN && FT_LEN == 4
                SAVEBIN "build/ovl/ft.bin", ovl_raw_ft, FID_COUNT * FT_LEN
                DISPLAY "GAME frame_tab stream (MEM-FT): ", /D, FID_COUNT * FT_LEN, " B raw -> packed ", /D, ftz_zx0_end - ftz_zx0, " B in bank 2 (boot6_ft -> the FRT rows)"
;------------------------------------------------------------------------------
; INSTR-BUILD: the HOW TO PLAY overlay (instr_ovl.asm at INSTR_ORG) + its three
; page images (tools/instr_pack.py, DISPed at INSTR_DATA = right after the code);
; streams in bank 0 after the text block ("TEXT" above), boot only.
;------------------------------------------------------------------------------
ovl_raw_instr:
                DISP INSTR_ORG
instr_ovl_main:
                INCLUDE "instr_ovl.asm"
instr_ovl_end:
                ENT
INSTR_OVL_LEN   EQU instr_ovl_end - instr_ovl_main
INSTR_DATA      EQU instr_ovl_end
                SAVEBIN "build/ovl/instr.bin", ovl_raw_instr, INSTR_OVL_LEN
ovl_raw_instr1:
                DISP INSTR_DATA
instr_p1_img:
                INCLUDE "../build/text/instr_p1.inc"
instr_p1_end:
                ENT
ovl_raw_instr2:
                DISP INSTR_DATA
instr_p2_img:
                INCLUDE "../build/text/instr_p2.inc"
instr_p2_end:
                ENT
ovl_raw_instr3:
                DISP INSTR_DATA
instr_p3_img:
                INCLUDE "../build/text/instr_p3.inc"
instr_p3_end:
                ENT
INSTR_P1_LEN    EQU instr_p1_end - instr_p1_img
INSTR_P2_LEN    EQU instr_p2_end - instr_p2_img
INSTR_P3_LEN    EQU instr_p3_end - instr_p3_img
                ASSERT instr_p1_end <= GEN_SCRATCH + GEN_SCRATCH_LEN && instr_p2_end <= GEN_SCRATCH + GEN_SCRATCH_LEN && instr_p3_end <= GEN_SCRATCH + GEN_SCRATCH_LEN
                SAVEBIN "build/ovl/instr1.bin", ovl_raw_instr1, INSTR_P1_LEN
                SAVEBIN "build/ovl/instr2.bin", ovl_raw_instr2, INSTR_P2_LEN
                SAVEBIN "build/ovl/instr3.bin", ovl_raw_instr3, INSTR_P3_LEN
                DISPLAY "GAME HOW TO PLAY overlay (INSTR-BUILD, boot only): code ", /D, INSTR_OVL_LEN, " + page 1 ", /D, INSTR_P1_LEN, " / page 2 ", /D, INSTR_P2_LEN, " / page 3 ", /D, INSTR_P3_LEN, " B raw at ", /H, INSTR_ORG, " (", /D, GEN_SCRATCH + GEN_SCRATCH_LEN - instr_p1_end, " / ", /D, GEN_SCRATCH + GEN_SCRATCH_LEN - instr_p2_end, " / ", /D, GEN_SCRATCH + GEN_SCRATCH_LEN - instr_p3_end, " left); packed ", /D, instr_zx0_end - instr_p1_zx0, " B in bank 0 after the text (", /H, instr_p1_zx0, "..", /H, instr_zx0_end - 1, ")"
OVL_RAW_END     EQU $
                ASSERT OVL_RAW_END <= $10000

;==============================================================================
; SEQ CACHE NEED (3F-T2) — per depth (lp_dtab, as LEVEL POOL NEED) and for the
; PROTO rooms (K_SKELETON .. K_PROTO_END - 1): the distinct master blocks of
; the level's kinds (ksm_tab, dedup by block as sq_load) must fit the cache:
; <= SQ_SLOTS - 1 monster blocks, and the largest hero block + their bytes <=
; SEQB_LEN. Read from the raw image just assembled above ({b} at its bank-0
; scratch address: SQB_PHYS), final pass only (DEFL, as POOL_NEED).
;==============================================================================
    MACRO SQ_KIND k                            ; SQN / SQB += kind k's block, once
SQ_P = {ovl_raw_seq + ksm_tab - SQ_IMG + 2 * (k)}
                ASSERT SQ_P != 0                ; every kind of every depth / PROTO has a master block
      IF SQ_P
SQ_DUP = 0
        IF SQ_P == SQ_P0
SQ_DUP = 1
        ENDIF
        IF SQ_P == SQ_P1
SQ_DUP = 1
        ENDIF
        IF SQ_P == SQ_P2
SQ_DUP = 1
        ENDIF
        IF SQ_P == SQ_P3
SQ_DUP = 1
        ENDIF
        IF SQ_P == SQ_P4
SQ_DUP = 1
        ENDIF
        IF SQ_P == SQ_P5
SQ_DUP = 1
        ENDIF
        IF SQ_DUP == 0
          IF SQN == 0
SQ_P0 = SQ_P
          ELSEIF SQN == 1
SQ_P1 = SQ_P
          ELSEIF SQN == 2
SQ_P2 = SQ_P
          ELSEIF SQN == 3
SQ_P3 = SQ_P
          ELSEIF SQN == 4
SQ_P4 = SQ_P
          ELSE
SQ_P5 = SQ_P
          ENDIF
SQN = SQN + 1
SQB = SQB + {b ovl_raw_seq + SQ_P - SQ_IMG + KSM_LEN}
        ENDIF
      ENDIF
    ENDM
    MACRO SQ_RESET
SQN = 0
SQB = 0
SQ_P0 = -1
SQ_P1 = -1
SQ_P2 = -1
SQ_P3 = -1
SQ_P4 = -1
SQ_P5 = -1
    ENDM
SQ_HERO = {b ovl_raw_seq + ksm_kn - SQ_IMG + KSM_LEN}
    IF {b ovl_raw_seq + ksm_wz - SQ_IMG + KSM_LEN} > SQ_HERO
SQ_HERO = {b ovl_raw_seq + ksm_wz - SQ_IMG + KSM_LEN}
    ENDIF
SQ_MAX = 0
SQ_NMAX = 0
                DUP  LEVELS, sqd
                MMU  3, BANK_COLD3
SQK0 = {b lp_dtab + sqd * LP_DROW + 0}
SQK1 = {b lp_dtab + sqd * LP_DROW + 1}
SQK2 = {b lp_dtab + sqd * LP_DROW + 2}
SQK3 = {b lp_dtab + sqd * LP_DROW + 3}
SQK4 = {b lp_dtab + sqd * LP_DROW + 4} & LEK_KIND_MASK
                MMU  3, 0
                SQ_RESET
                SQ_KIND SQK0
                SQ_KIND SQK1
                SQ_KIND SQK2
                SQ_KIND SQK3
                SQ_KIND SQK4
      IF (SQK0 == K_VAMPIRE) || (SQK1 == K_VAMPIRE) || (SQK2 == K_VAMPIRE) || (SQK3 == K_VAMPIRE) || (SQK4 == K_VAMPIRE)
                SQ_KIND K_VBAT                  ; 3F-T9: pl_kinds loads the bat form's block with the Vampire's
      ENDIF
                DISPLAY "GAME sequence cache D", /D, sqd + 1, ": ", /D, SQN, " blocks, ", /D, SQB, " B + hero ", /D, SQ_HERO, " = ", /D, SQB + SQ_HERO, " of ", /D, SEQB_LEN   ; 3F-T13bc
      IF SQB > SQ_MAX
SQ_MAX = SQB
      ENDIF
      IF SQN > SQ_NMAX
SQ_NMAX = SQN
      ENDIF
                EDUP
                SQ_RESET                       ; the PROTO rooms (pool_proto)
                DUP  K_PROTO_END - K_SKELETON, sqk
                SQ_KIND K_SKELETON + sqk
                EDUP
      IF SQB > SQ_MAX
SQ_MAX = SQB
      ENDIF
      IF SQN > SQ_NMAX
SQ_NMAX = SQN
      ENDIF
SEQB_NEED = SQ_HERO + SQ_MAX
                ASSERT SQ_NMAX <= SQ_SLOTS - 1 && SEQB_NEED <= SEQB_LEN
                DISPLAY "GAME sequence cache: ", /D, SQ_SLOTS, " rows (", /D, SQ_ROWS_LEN, " B) + bytes need ", /D, SEQB_NEED, " of SEQB_LEN ", /D, SEQB_LEN, " (hero ", /D, SQ_HERO, " + monsters ", /D, SQ_MAX, ", <= ", /D, SQ_NMAX, " blocks a level)"

;------------------------------------------------------------------------------
; tap_loader — 10 CLEAR/BORDER 0../POKE: 15 LOAD "" SCREEN$: 20 LOAD "" CODE: 30 RANDOMIZE USR VAL "<start>"
; CLEAR 24575 frees $6000..$7FFF for the room maps / generator buffers and the
; low-RAM cold code. The USR address is emitted as 5 ASCII digits of `start`.
; Tokenised in a scratch ORG (page 0 at $E000; not part of the runtime image —
; bank 0 is overwritten by the pre-shift pool at boot; D3-TX: above the text
; block at the bottom of bank 0, ASSERTed).
;------------------------------------------------------------------------------
TAPE_CLEAR      EQU 24575
LOAD_SCR_LEN    EQU 6912
                ORG  $E000
tap_loader:
                DB   0, 10
                DW   tap_l10_end - tap_l10_body
tap_l10_body:   DB   $FD, $B0, '"', "24575", '"', ':'                   ; CLEAR (also CLSes: must precede the picture)
                DB   $E7, $B0, '"0"', ':', $DA, $B0, '"0"', ':', $D9, $B0, '"0"', ':', $FB, ':'  ; BORDER/PAPER/INK 0: CLS
                DB   $F4, $B0, '"23739"', ',', $B0, '"111"', $0D       ; POKE 23739,111: drop the ROM's "Bytes:" header text
                ; NB the game CODE header's CLS_LOWER still blanks rows 22-23 of the picture (DF_SZ tricks scroll it)
tap_l10_end:
                DB   0, 15
                DW   tap_l15_end - tap_l15_body
tap_l15_body:   DB   $EF, $22, $22, $AA, $0D                    ; LOAD "" SCREEN$ (loading picture, 6912 B at $4000)
tap_l15_end:
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
                ; loading picture: slot 1 ($4000) holds game image bytes here, so park them in
                ; a scratch file, INCBIN the .scr over them for SAVETAP, then restore (the .sna and
                ; the CODE block below see the original bytes; 0 game bytes).
                SAVEBIN  "build/slot1_park.bin", $4000, LOAD_SCR_LEN
                ORG  $4000
                INCBIN   "../assets/gfx/loading/loading_l3d.scr"
                SAVETAP  "build/wazhack.tap", CODE,  "wazhack", $4000, LOAD_SCR_LEN
                ORG  $4000
                INCBIN   "slot1_park.bin"                 ; found via build.sh -i OUTDIR/build
                SAVETAP  "build/wazhack.tap", CODE,  "wazhack", lowram_code, TAPE_CODE_LEN
                TAPE_BLOCKS 1                  ; the headerless blocks = start's tape_tab
                MMU  3, 0
                SAVESNA  "build/wazhack.sna", boot
    ENDIF
