;==============================================================================
; defs.asm — PROTO-only constants (docs/design/prototype.md rev B).
;
; Shared screen/port/keyboard/GS/RNG/state-block constants come from
; constants.asm (INCLUDEd first by main.asm). Everything else fixed lives here;
; every fixed address below is recorded in docs/memory-map.md ("PROTO" section).
;==============================================================================

;------------------------------------------------------------------------------
; ROM / system variables (48K BASIC ROM = 128K ROM 1, paged via $7FFD bit 4)
;------------------------------------------------------------------------------
IY_SYSVAR       EQU $5C3A           ; conventions: IY stays here (tape path IM1; ISR_ROM_CHAIN)
SYS_FRAMES      EQU $5C78           ; 50 Hz frame counter, 3 B (low byte paces the tick); A8: the
                                    ; IM2 ISR increments it exactly as the ROM ISR did
ROM_ISR         EQU $0038           ; 48K ROM IM1 handler (ISR_ROM_CHAIN=1 jumps there)
ROM_CHARSET     EQU $3D00           ; 48K ROM font, char 32 first, 8 B/char
ROM_LD_BYTES    EQU $0556           ; ROM tape loader (IX=dst, DE=len, A=flag, CF=1)

;------------------------------------------------------------------------------
; 128K paging. $7FFD is write-only: always write through PORT_7FFD_SHADOW.
;   bit 4 = 1 -> 48K BASIC ROM (charset, LD-BYTES, ISR_ROM_CHAIN handler)
;   bit 3     -> displayed screen: 0 = bank 5 ($4000; boot, select, transition
;                scrolls), 1 = bank 7 (A7 double buffer: during play). Only
;                set_screen changes it (also via show_bank5 / present_full);
;                page_bank / restore_page keep it.
;   bit 5 (paging lock) is never set.
P7FFD_ROM48     EQU %00010000
P7FFD_SCREEN7   EQU %00001000
BANK_SRC_LO     EQU 1               ; sprite SOURCES, virtual $8000-$BFFF (contended)
BANK_SRC_HI     EQU 3               ; sprite SOURCES, virtual $C000-$FFFF (contended)
BANK_POOL0      EQU 0               ; pre-shift pool (uncontended), boot-generated
BANK_POOL1      EQU 4
BANK_POOL2      EQU 6
BANK_SHADOW     EQU 7               ; D3-S2: the ATTR shadow ($F800, erase_rect's attrs)
BANK_COLD7      EQU 7               ; D3-S2: bank-7 cold code B7_CODE..B7_LIMIT (via far7)
BANK_SCREEN7    EQU 7               ; A7: the displayed screen during play, $C000..$DAFF
BANK_COLD3      EQU BANK_SRC_HI     ; bank-3 cold code (select, scrolls) after the source tail; via far3
AY_RESERVE      EQU $EDA0           ; A8 / D3-0 / MEM-SND: bank 3 $EDA0..$FFFF = 4704 B AY player/music/FX
                                    ;     reserve (game.md §11.2, user 2026-10-06: 7 KB -> 4 KB at $F000,
                                    ;     was $E400; MEM-SND: -608 B after 406 B of bank-3 cold code went
                                    ;     to bank 7, ~200 B bank-3 slack kept); cold code + sources end below
AY_RESERVE_END  EQU $10000
BANK_AY         EQU BANK_COLD3      ; the ISR pages it in around every AY_PLAY call
AY_PLAY         EQU AY_RESERVE      ; A8 player slot entry, called once per frame by the ISR
                                    ; (contract: docs/conventions.md "Interrupts")
; AY-3-8912 (128K): select a register on $FFFD, write it on $BFFD
AY_REG_PORT     EQU $FFFD
AY_DATA_PORT    EQU $BFFD
AY_R_VOL_A      EQU 8               ; R8..R10: channel volumes A, B, C (ay_silence)
; SND-2 sound mailbox (bank 2, STATE_3B spare; docs/conventions.md "Interrupts":
; main code writes only SND_MODE / MUS_REQ / MUS_SHOT (+ SFX_REQ via sfx_req), single-byte stores or
; set/res on SND_MODE; only the ISR (ay_play) writes MUS_STATE / MUS_CUR and
; clears MUS_SHOT). Boot initialises it; new_game never touches it.
SND_MODE        EQU $BFEB           ; game.md §3.6 sound setting (per power-on)
SND_MUSIC_BIT   EQU 0
SND_SFX_BIT     EQU 1
SND_HOLD_BIT    EQU 7               ; pause: volumes 0, the sequencer frozen
SND_MUSIC       EQU 1 << SND_MUSIC_BIT
SND_SFX         EQU 1 << SND_SFX_BIT
SND_HOLD        EQU 1 << SND_HOLD_BIT
SND_ALL         EQU SND_MUSIC | SND_SFX ; boot default (ALL ON)
MUS_REQ         EQU $BFEC           ; LEVEL: looping tune id (MUS_*), 0 = silence; never consumed
MUS_SHOT        EQU $BFED           ; EDGE: one-shot id, 0 = none; main writes, the ISR clears
MUS_STATE       EQU $BFEE           ; ISR: bits 0-1 MS_*, bit 7 MS_DONE
MUS_CUR         EQU $BFEF           ; ISR: id sounding (0 = none)
SFX_REQ         EQU $BFF0           ; SND-5 EDGE: SFX id (SFX_*, sfx_ids.inc), 0 = none; written
                                    ; only by sfx_req (keeps the higher prio), cleared by the ISR
SFX_PRIO_MASK   EQU $E0             ; SFX id bits 5-7 = priority 0..7 (sfx2asm.py)
SFX_IDX_MASK    EQU $1F             ; bits 0-4 = index 1..SFX_COUNT into sfx_tab
SFX_DUCK_PRIO   EQU 6 << 5          ; prio >= 6 ducks deeper
SFX_DUCK_LO     EQU 3               ; any effect: the music's V2 / V3 fixed volumes - 3 (floor 0)
SFX_DUCK_HI     EQU 4               ; prio >= SFX_DUCK_PRIO: - 4
DNG_DWELL       EQU $BFF1           ; SND-3 (mus7.asm): turns since W entered (sat. 255), 0 = W off
DNG_CALM        EQU $BFF2           ; SND-3: consecutive turns without the danger condition
SFX_NEXT        EQU $BFF3           ; SND-5: ONE deferred SFX id (prio >= SFX_DEFER_PRIO that lost to
                                    ; a pending / playing higher one); the ISR takes it when the
                                    ; playing effect ends. sfx_req and the ISR write it, 0 = none
SFX_DEFER_PRIO  EQU 6 << 5          ; LEVELUP (6) behind KILL / HURT (7) is played after, not lost
MS_IDLE         EQU 0               ; MUS_STATE bits 0-1
MS_LOOP         EQU 1
MS_SHOT         EQU 2
MS_MASK         EQU 3
MS_DONE         EQU $80             ; a one-shot finished; cleared when the next shot is taken
; tune ids (= the S1e tape keys, sound.md §S1f; order of game_songs.asm's mus_tab)
                                    ; id 1 (Q Dungeon Crawl) removed 2026-10-19 (user):
                                    ; reserved, the ISR rejects it (an invalid id)
MUS_FIRST       EQU 2               ; the lowest song id (mus_tab has no entry below it)
MUS_DANGER      EQU 2               ; W  Dangerous          loop
MUS_BOSS        EQU 3               ; E  Boss Fight         loop
MUS_LEVEL       EQU 4               ; R  Level Complete     one-shot (stinger)
MUS_WIN         EQU 5               ; T  Game Win           one-shot (final)
MUS_OVER        EQU 6               ; Y  Game Over          one-shot (final)
MUS_LAMENT      EQU 7               ; U  Lament IIb         loop
MUS_COUNT       EQU 7               ; the highest song id (6 songs: MUS_FIRST .. 7)
MUS_ROOM        EQU MUS_LAMENT      ; the in-play room tune (SND-3: Q rotation replaces it)
; Bank 7 (A7): screen 2 at $C000 (what the ULA shows during play; written only
; by present / present_full) and the room's ATTR shadow at $F800 (screen-attr
; layout: screen attr -> shadow attr is +$A0 in the high byte, low bytes
; equal). D3-S2: the bitmap shadow ($E000..$F7FF) is gone — erase_rect redraws
; TILE_GLYPHS[ROOM_MAP] — and its 6 KB hold the bank-7 cold code (far7).
SCREEN7_BITMAP  EQU $C000           ; bank 7: displayed bitmap (copy of $4000)
SCREEN7_ATTR    EQU $D800           ; bank 7: displayed attrs  (copy of $5800)
B7_CODE         EQU $E000           ; bank 7: cold code b7_code..b7_end (src/bank7.asm), tape
                                    ;     block joined to the TSET_LO tilesets below it
B7_LIMIT        EQU $F800           ; ... up to the attr shadow (ASSERTed)
SHADOW_ATTR     EQU $F800           ; bank 7: room tile attrs in screen layout ($F800..$FA3F used)
BANK_WINDOW     EQU $C000
FT_BLOCKER      EQU $FE             ; find_target: nearest body is mid-ladder (not a slot)
PAGING_PROBE    EQU $A5             ; check_paging: bank-1 marker (bank 0 gets ~)
SRC_VIRT_BASE   EQU $8000           ; sources are assembled at virtual $8000..$FFFF
; D3-TX: the text block (strings + dictionary, B3B-13) moved out of bank 1 to
; the BOTTOM of pool bank 0 (TEXT_ADDR..POOL_START, own headerless tape block);
; the pre-shift pool starts above it (alloc_reset: ALLOC_PTR = POOL_START).
; Read only through the helpers that page BANK_TEXT and hand $C000 back
; (msg_push, impact_line, print6t, print6x, tx_dec); never in place.
BANK_TEXT       EQU BANK_POOL0      ; uncontended (bank 1 was contended)
TEXT_ADDR       EQU BANK_WINDOW     ; text_base (ASSERTed in main.asm)
TEXT_DISP       EQU BANK_WINDOW - SRC_VIRT_BASE   ; virtual bank-1 address -> runtime ($C000..): vdata, ui1_code
BANK_UI1        EQU BANK_SRC_LO     ; C3-0: bank-1 UI code (ui1_code, after vdata; via far1)
UI1_LIMIT       EQU $10000          ; ui1_code runs at $C000.. (DISPed by TEXT_DISP), ends below this
TX_NONE         EQU $FF             ; level_enter / level_show / panel_init: E = no first line

;------------------------------------------------------------------------------
; Low-RAM buffers (bank 5, $6000-$7FFF; free after the loader's CLEAR 24575).
; Contended, but only touched off the blit's inner loop (1 read/erased cell).
;------------------------------------------------------------------------------
ROOM_MAP        EQU $6000           ; 672 B buffer: current room tile ids, 32 x PLAY_ROWS (18)
NEXT_MAP        EQU $6300           ; 672 B buffer: destination room during a transition
                                    ; (B3B-3: 576 B used per map, PLAY_CELLS; rows 0..17)
; A6: tile ids 32 -> 64. TILE_GLYPHS is 512-ALIGNED so glyph(id) = base + id*8
; is formed as E = id*8 (low 8 bits), D = (base >> 9) RL carry (= id bit 5):
; +8 T per drawn cell vs the 32-id `ld d, base>>8` (tile_rect).
TILE_GLYPHS     EQU $6600           ; 512 B: 64 tiles x 8 B ($6600..$67FF)
BITREV_TAB      EQU $6800           ; 256 B: bit-reversed byte (page-aligned)
TILE_ATTRS      EQU $6900           ; 64 B : attr per tile id (one page: ld h, TILE_ATTRS>>8)
GEN_SRC         EQU $6940           ; 512 B: staging for vdata reads (panel_boot / pblit, copy_virt)
GEN_MIR         EQU $6B40           ; 512 B: mirrored copy (left-facing)
LOWRAM_END      EQU $6D40
; D3-TX: tx_dec's decode buffer (a whole string, 0-terminated, readable with any
; bank paged: bank-1 UI code can no longer read the text in place). The top of
; GEN_MIR: transient (filled and consumed inside one menu call), above the
; pause overlay's save (PAUSE_SAVE..+PAUSE_LEN, ASSERTed in menu1.asm); the
; generator (its other user) never runs inside a menu text call.
TX_DEC_LEN      EQU 43              ; textpack WIDE_MAX 42 + the 0
TX_DEC          EQU LOWRAM_END - TX_DEC_LEN   ; $6D15..$6D3F
TILE_IDS        EQU 64              ; tile id capacity (glyphs/attrs above)
TILE_COMMON     EQU 32              ; ids 0..31: engine/common tiles (init_tiles)
; ids 32..63: per-level slots (game.md §1.2). B3B-8: level_load_tiles copies
; the depth's bank-7 slot (TSET_*, level_defs.asm: 32 glyphs + 32 attrs + 32
; flags) to TILE_LEVEL_GLYPHS / TILE_LEVEL_ATTRS / tile_flags + 32 — the glyph
; half is exactly the second page of TILE_GLYPHS (one 256-B LDIR).
TILE_LEVEL_GLYPHS EQU TILE_GLYPHS + TILE_COMMON * 8
TILE_LEVEL_ATTRS  EQU TILE_ATTRS + TILE_COMMON
; Bank-5 low-RAM fit (ASSERTed in main.asm, docs/memory-map.md "Bank 5 low RAM"):
;   fixed buffers ROOM_MAP..LOWRAM_END; then free RAM (level state, 3B);
;   then the cold block lowram_code..$7FFF, which ends with the frame
;   descriptors (fdesc_tab, FID_COUNT x FDESC_STRIDE). The cold block grows
;   DOWN, so the fit ASSERT keeps room for (FRT_MAX - FID_COUNT) more
;   descriptors: adding frames can never collide with the buffers.
;   A5 ZX0 decompressor:  dzx0 + zx0_frame inside lowram.asm (<= ZX0_BUDGET B,
;                         ASSERTed); A5 ZX0 scratch aliases ROOM_MAP..NEXT_MAP
;                         ($6000..$65FF, 1,536 B) — the generator only runs
;                         while no room is built
LOWRAM_FREE_END EQU LOWRAM_END_3B   ; B3B-1: end of the fixed low-RAM buffers incl. the 3B level
                                    ; state + ornament glyphs ($6D40..$6EBF, level_defs.asm)
ZX0_BUDGET      EQU 128             ; A5: decompressor (68 B) + glue, max
; B3B-12: the raw-sources A/B build (-DZX0_SOURCES=0) is retired; tests/zx0_pool.py
; checks the pools against a Python reference built from the raw frame data.
    IFDEF ZX0_SOURCES
      IF ZX0_SOURCES == 0
        ERROR "ZX0_SOURCES=0 (raw sprite sources) was retired in B3B-12"
      ENDIF
    ENDIF
GEN_SCRATCH     EQU ROOM_MAP        ; A5: 1,536 B generator-time scratch (alias, rooms dead)
GEN_SCRATCH_LEN EQU NEXT_MAP + $300 - ROOM_MAP

ROOM_COLS       EQU 32
ATTR_STRIDE     EQU 32              ; bytes per attribute row (screen layout)
MAP_BUF_LEN     EQU $2A0            ; 672 B per map buffer (PROTO 32x21; B3B-3 uses PLAY_CELLS)
; B3B-3: playfield = rows 0..PLAY_ROWS-1 (0..17), panel = rows 18..23 (level_defs.asm;
; B3B-11 panel engine: panel.asm).

;------------------------------------------------------------------------------
; Bank-2 runtime storage. The image must end below ENTITIES (ASSERTed).
;------------------------------------------------------------------------------
P_ENTITIES      EQU $B000           ; 16 slots x 32 B = 512 B ($B000..$B1FF)
P_ENT_STRIDE    EQU 32
P_MAX_ENT       EQU 16
FRT_STRIDE      EQU 16
FRT_MAX         EQU 160             ; A6 (game.md §11.2): 101 used (D3-4)
FRT             EQU P_ENTITIES - FRT_MAX * FRT_STRIDE   ; $A600..$AFFF: frame runtime
                                    ; table, 16 B/fid (4 variants x bank,lo,hi + 4 pad);
                                    ; directly below ENTITIES, the image ends below it
BANK2_FREE      EQU $B200           ; A6: vacated old FRT ($B200..$B7FF, 1,536 B):
BANK2_FREE_END  EQU SLOTREC         ;     free bank-2 runtime RAM (docs/memory-map.md)
SLOTREC         EQU $B800           ; A7b: per-slot render record, 16 B per slot ($B800..$B8FF,
SLOTREC_STRIDE  EQU 16              ;     one page): record = SLOTREC + slot*16, fields by inc l
R_VIS           EQU 0               ; desired: 0 hidden / 1 visible (anim_tick)
R_FID           EQU 1               ; desired frame id (anim_tick)      } R_FID..R_ROWS: same
R_FPX           EQU 2               ; desired frame px (top-left)      } order as the entity's
R_FPY           EQU 3               ; desired frame py (top-left)      } drawn block E_DFID..
R_COL           EQU 4               ; desired footprint (cells)        } E_DROWS: draw_slot
R_ROW           EQU 5               ;                                  } copies it with one
R_COLS          EQU 6               ;                                  } LDIR
R_ROWS          EQU 7
R_LEFT          EQU 8               ; desired facing (0 / EF_LEFT)
R_ATTR          EQU 9               ; desired attr
R_DATTR         EQU 10              ; attr last stamped
R_DIRTY         EQU 11              ; DIRTY_* class this tick
R_LOG           EQU 12              ; 1 = log this draw in ANIM_TRACE
R_TINT          EQU 13              ; D3-8e2: the body attr (kind / status tint) last shown with
                                    ; no reaction pending: kept while one is (render; R_ATTR | 4)
R_MK            EQU 14              ; D3-8d: the slot's status mark as drawn (0 = none; mark.asm:
                                    ; bits 0-2 glyph 1..5, bit 3 frame B, bits 4-5 row >> 3)
R_MKLO          EQU 15              ; D3-8d: its cell's low byte ((row & 7) << 5 | col)
DMG_LIST        EQU $B900           ; damage rects: 4 B each (col,row,cols,rows)
DMG_MAX         EQU 48              ; $B900..$B9BF
PEND_DMG        EQU $B9C0           ; queued damage for next render: 4 rects ($B9C0..$B9CF)
PEND_DMG_MAX    EQU 4
LIVE_LIST       EQU $BA00           ; 16 x 5 B: colliders this turn ($BA00..$BA4F)
LIVE_N          EQU $BA50           ; entries in LIVE_LIST
LL_STRIDE       EQU 5               ; LIVE_LIST entry: slot, ptr lo, ptr hi, w, h
RLIST           EQU $BA60           ; render list: slots drawn or visible ($BA60..$BA6F)
RLIST_N         EQU $BA70
RL_IDX          EQU $BA71
PL_X            EQU $BA72           ; cache_player: hero box / state for the monster phase
PL_Y            EQU $BA73
PL_W            EQU $BA74
PL_H            EQU $BA75
PL_STOREY       EQU $BA76
PL_LADDER       EQU $BA77           ; 1 = hero mid-ladder
BLIT_CROWS      EQU $BA79           ; aligned blit: char rows left
SEL_FRT_SAVE    EQU $BA80           ; 2 x FRT_STRIDE: boot FRT rows of the select idles ($BA80..$BA9F)
MSG_Q           EQU $BA78           ; queued impact message: attacker slot + 1 (0 = none)
PRES_MASK       EQU $BAA0           ; A7: present dirty-cell mask, 24 rows x 4 B ($BAA0..$BAFF);
PRES_LEN        EQU 24 * 4          ;     byte row*4 + col/8, bit 7 - col%8 (bit 7 = leftmost)
; A8 IM2 (docs/memory-map.md "Interrupts"): carved from the bottom of the old
; 1 KB stack reservation (measured max depth 40 B). Bank 2 = uncontended and
; always mapped; I = $BB is outside $40-$7F (128K snow) and $C0-$FF (paged).
ISR_VEC_TABLE   EQU $BB00           ; 257 B, every byte = ISR_VEC_BYTE ($BB00..$BC00):
ISR_VEC_LEN     EQU 257             ;     works whatever byte the floating bus supplies
ISR_ADDR        EQU $BCBC           ; the ISR (copied here at boot from isr_image, lowram.asm)
ISR_VEC_BYTE    EQU ISR_ADDR & $FF
ISR_ADDR_END    EQU $BD00           ; ISR bytes end below this (ASSERTed)
STACK_BOTTOM    EQU $BD00           ; stack grows down from $BF00 to here (768 B)
    IFNDEF ISR_ROM_CHAIN                        ; A8: 1 = the ISR ends with jp ROM_ISR (ROM
ISR_ROM_CHAIN   EQU 0                           ;     FRAMES + keyboard scan, needs IY = $5C3A,
    ENDIF                                       ;     ~+0.92k T/frame (measured 1.54k vs 0.62k)); 0 = FRAMES only (default)
    IFNDEF ISR_SAVE_ALT                         ; A8: 1 = the ISR also saves AF'/BC'/DE'/HL'
ISR_SAVE_ALT    EQU 0                           ;     (needed once BOTH the player and main
    ENDIF                                       ;     code use EXX / EX AF,AF'; neither does yet)
    IFNDEF DEBUG_KIT                            ; D3-7: 1 = new games get the designer's debug
DEBUG_KIT       EQU 1                           ;     start kit (game.md §1.4 "Start kit", never in a
    ENDIF                                       ;     release tape); suites + goldens run on -DDEBUG_KIT=0
KIT_DEBUG       EQU DEBUG_KIT                   ; (.sym: tests/game_lib.py refuses a kit build)

;------------------------------------------------------------------------------
; State block $BF00.. (above initial SP). $BF00-$BF0D shared with main.asm:
; GAME_STATE, RNG_STATE, TURN_COUNTER, INPUT_SRC, KBD_MATRIX (constants.asm).
;------------------------------------------------------------------------------
TURN_PHASE      EQU $BF10           ; 0 = INPUT, 1 = ANIM          (test-observable)
TICK_COUNTER    EQU $BF11           ; word: 25 Hz ticks elapsed    (test-observable)
CUR_ROOM        EQU $BF13           ; room id = grid cell 0..8 (B3B-8; A 0 B 1 D 3 C 4) (test-observable)
HERO_KIND       EQU $BF14           ; K_KNIGHT/K_WIZARD (2 = retired)   (test-observable)
POTIONS_TAKEN   EQU $BF15           ; bitmask of taken FLOOR_LIST entries 0..7 (test-observable)
INPUT_REPEAT    EQU $BF16           ; 1 = hold repeats (default); 0 = edge-triggered
ANIM_FREEZE     EQU $BF17           ; 1 = resting sprites hold IDLE frame 0
PORT_7FFD_SHADOW EQU $BF18          ; last value written to $7FFD
OVERRUN_COUNT   EQU $BF19           ; word: ticks that exceeded 2 frames (t-o)
ANIM_TRACE_IDX  EQU $BF1B           ; next write offset into ANIM_TRACE (0..30, even)
LAST_TICK_FRAME EQU $BF1C           ; SYS_FRAMES low byte at the current tick start
TURN_TICK       EQU $BF1D           ; ticks elapsed in the current ANIM phase
NEED_RELEASE    EQU $BF1E           ; edge-trigger latch (INPUT_REPEAT = 0)
EXIT_KIND       EQU $BF1F           ; pending exit after this turn's anim (EX_*)
ANIM_TRACE      EQU $BF20           ; 32 B ring: (slot, frame_id) per drawn change
ANIM_TRACE_LEN  EQU 32
BLIT_MISS       EQU $BF40           ; count: stationary frame asked at a missing shift
GEN_OVERFLOW    EQU $BF41           ; 1 if the pre-shift pool ran out (build bug)
ALLOC_IDX       EQU $BF42           ; pool bank index 0..2
ALLOC_PTR       EQU $BF43           ; word: next free byte in the paged pool bank
ALLOC_MARK_IDX  EQU $BF45           ; allocator mark after monsters+hero idles
ALLOC_MARK_PTR  EQU $BF46           ; word
CLIMB_BLK_XY    EQU $BF48           ; B18 word: CLIMB_BLK_ID's (x, y) at its last block (climb_blocked)
; $BF4A..$BF4B: spare (D3-0: $BF48..$BF4B were ZAP_T / ZAP_ROW / ZAP_COL / ZAP_LEN, the PROTO zap)
DMG_COUNT       EQU $BF4C           ; rects in DMG_LIST this render
PEND_DMG_COUNT  EQU $BF4D
EXIT_DEST       EQU $BF4E           ; destination room of the pending exit
EXIT_STOREY     EQU $BF4F           ; storey the player exited from
EXIT_COL        EQU $BF50           ; ladder col for vertical exits
BL_FID          EQU $BF51           ; blit params
BL_LEFT         EQU $BF52
BL_FPX          EQU $BF53
BL_FPY          EQU $BF54
DMG_OVERFLOW    EQU $BF55           ; count: DMG_LIST / PEND_DMG full -> fallback (expect 0)
GEN_FID         EQU $BF56           ; generator scratch
GEN_COLS        EQU $BF57
GEN_H           EQU $BF58
GEN_FLAGS       EQU $BF59
GEN_OFF         EQU $BF5A
GEN_BASE        EQU $BF5B           ; word
GEN_VAR         EQU $BF5D           ; variant index 0..3
GEN_SHIFT       EQU $BF5E
FOLLOW_N        EQU $BF5F           ; followers admitted this exit
CAND_LIST       EQU $BF60           ; 16 B: candidate slot or $FF (processed)
CAND_GAP        EQU $BF70           ; 16 B: candidate gap
CLIP_TRAP       EQU $BF80           ; count: blit/stamp would cross col 31 (debug trap, expect 0)
RENDER_PASS     EQU $BF81           ; force-pass changed flag
LAST_HIT_SLOT   EQU $BF82           ; scratch
TMP0            EQU $BF83
TMP1            EQU $BF84
TMP2            EQU $BF85
TMP3            EQU $BF86
TMP4            EQU $BF87
TMP5            EQU $BF88
TMP6            EQU $BF89
TMP7            EQU $BF8A
ACT_SLOT        EQU $BF8B           ; slot currently resolving
PLAYER_DIR      EQU $BF8C           ; sampled direction bits this tick
PLAYER_DISC     EQU $BF8D           ; sampled discrete keys this tick
ATK_PTR         EQU $BF8E           ; word: attacker entity during do_attack
MON_SLOT        EQU $BF90           ; resolve_monsters slot counter
ANIM_SLOT       EQU $BF91           ; anim/render slot counter
YIELD_FLAG      EQU $BF92           ; 1 while a monster takes a yield step
GEN_ZBLK        EQU $BF93           ; word: virtual addr of the ZX0 block now unpacked in GEN_SCRATCH
                                    ; (0 = none; cleared by alloc_reset / alloc_restore)
PRES_ANY        EQU $BF95           ; A7: 1 = PRES_MASK has a bit set (present has work)
DMG_PRES_N      EQU $BF96           ; A7: DMG_LIST rects pmark_dmg marks (before overlap repair)
PRES_RMIN       EQU $BF97           ; A7: first marked row ($FF = none); present starts there
JUMP_ARC        EQU $BF98           ; J1: the hero's jump arc for anim (try_jump writes it; was FLY_INBOX, B8):
JA_N            EQU $1F             ;   bits 0-4: airborne ticks n = 2 |x_f - x| (12 / 14, less when cut short)
JA_D7_BIT       EQU 6               ;   set: D = 7 arc shape (N = 14), else D = 6 (N = 12)
JA_FALL_BIT     EQU 7               ;   set: the jump ends in a pit fall (E_Y already = storey 1)
; $BF9A..$BF9F: B3B-11 freed them (were the A7 HUD_EXT / HUD_PW); now MENU_SPIN, PAUSED, END_SHOWN,
; MENU_IN_SIG, PEND_N (below)
GEN_TRAP        EQU $BF99           ; count: gen_frame ran while PLAYING/TRANSITION (GEN_SCRATCH = live room maps; debug trap, expect 0)
MSG_BUF         EQU $BFA0           ; 32 B: impact message composition (show_impact_msg -> log_push)
TIMING_MARK     EQU $BFC0           ; spare
CLIMB_BLK_ID    EQU $BFC7           ; B14: slot of the last entity that blocked the hero's climb
CLIMB_BLK_N     EQU $BFC8           ; B14: consecutive blocked climbs by CLIMB_BLK_ID (0 = none)
CLIMB_SQZ_N     EQU 4               ; B18: the squeeze at the 2nd block when the blocker did not move,
                                    ; at the (CLIMB_SQZ_N + 1)th anyway (a 4-wide body on the shaft col
                                    ; clears a 3-col climb path in <= 4 yield steps)
CLIMB_BLK       EQU $BFC1           ; 1 = this input's climb was blocked by an entity (-> wait turn)
AY_CALLS        EQU $BFC2           ; A8 word: AY_PLAY calls (ay_play counts every call; test-observable)
PLAYER_SC       EQU $BFC9           ; C3-1: shortcut keys this tick (SC_* bits, io.asm)
                ASSERT PLAYER_SC != CLIMB_BLK_ID && PLAYER_SC != CLIMB_BLK_N
ICON_SIG        EQU $BFCB           ; C3-3: icon_sig as last drawn (icon_poll)
ICON_MODE       EQU $BFCC           ; C3-2b: 1 = ICON MODE (play frozen, cursor on the stick)
DN_T            EQU $BFCD           ; C3-2b: ticks DOWN alone has been held (ICON MODE window)
DN_COMMIT       EQU $BFCE           ; C3-2b: 1 = a DOWN released inside the window: act once
PRE_N           EQU $BFCF           ; C3-2b: info line ">" prefix getter state (pre_get)
EXIT_LOCK       EQU $BFD1           ; C3-2b: 1 = directions ignored until released (ICON MODE exit)
FIRE_LOCK       EQU $BFDF           ; C3-2b review: 1 = FIRE masked after BREAK until released
MENU_SPIN       EQU $BF9A           ; C3-6: word, frames x busy-wait passes in the menu (seed entropy)
PAUSED          EQU $BF9C           ; C3-6: 1 while the pause overlay is up (test-observable)
END_SHOWN       EQU $BF9D
PEND_N          EQU $BF9F           ; B19: PENDING bodies of CUR_ROOM at the last build_live (pend_hit)
MENU_IN_SIG     EQU $BF9E           ; C3-6 review: last input fold seen by menu_frame           ; C3-6: 1 = the death / win card is drawn
LVL_SH          EQU $BFCA           ; C3-3: hero level digit last drawn ($FF = never)
LOCK_SHOWN      EQU $BFC6           ; B3B-5: 1 = the locked-door message was printed for the key
                                    ;   still held (read_turn_input clears it on release)
JUMP_TURN       EQU $BFC4           ; B3B-5 word: TURN_COUNTER value on which a jump is refused (the turn
                                    ;   right after a jump: "not two turns in a row", game.md §2.4); $FFFF = none

; Game states (GAME_STATE). 2/3/4 shared with constants.asm.
GS_SELECT       EQU $05
GS_TRANSITION   EQU $06

; TURN_PHASE
TP_INPUT        EQU 0
TP_ANIM         EQU 1

; Pending exit kinds (EXIT_KIND)
EX_NONE         EQU 0
EX_LEFT         EQU 1
EX_RIGHT        EQU 2
EX_UP           EQU 3
EX_DOWN         EQU 4
EX_LEVEL        EQU 5               ; B3B-12: down the lair's level exit {EXITCOL,2} -> next depth

;------------------------------------------------------------------------------
; Entity record — 32-byte stride (prototype §11.1; the 16 B P3 stride doesn't
; fit the render/anim fields). slot*32 = 5 shifts. IX = entity pointer in the
; logic/anim layers (documented per routine).
;------------------------------------------------------------------------------
E_KIND          EQU 0
E_ROOM          EQU 1
E_FLAGS         EQU 2
E_X             EQU 3               ; body-left col
E_Y             EQU 4               ; body-top row
E_HP            EQU 5
E_MAXHP         EQU 6
E_AIDIR         EQU 7               ; climb direction (+1 down / $FF up)
E_POT           EQU 8               ; player: potions carried (0..9)
E_PX            EQU 9               ; body px (tweened)
E_PY            EQU 10              ; body py (tweened)
E_MODE          EQU 11              ; M_*
E_SEQL          EQU 12              ; one-shot sequence entry pointer
E_SEQH          EQU 13
E_TMR           EQU 14              ; ticks left in the current entry (0 = not started)
E_REACT         EQU 15              ; RC_* reaction pending
E_REACTAT       EQU 16              ; earliest TURN_TICK for the reaction
E_WPH           EQU 17              ; motion-cycle phase (ticks moved)
E_FLT           EQU 18              ; flash ticks left
E_FLA           EQU 19              ; flash attr
E_MSG           EQU 20              ; message code shown at IMPACT
E_TGT           EQU 21              ; IMPACT target slot
E_HIT           EQU 22              ; IMPACT: 1 = hit (flash)
; +23 spare (D3-0: was E_ZAP, the PROTO wizard zap)
E_DVIS          EQU 24              ; drawn: bit0 visible, bit3 = facing left (EF_LEFT)
E_DFID          EQU 25              ; drawn frame id
E_DFPX          EQU 26              ; drawn frame px
E_DFPY          EQU 27              ; drawn frame py
E_DCOL          EQU 28              ; drawn footprint (cells)
E_DROW          EQU 29
E_DCOLS         EQU 30
E_DROWS         EQU 31

; E_FLAGS bits
; EF_ACTIVE (1), EF_PLAYER (2), EF_HOSTILE (4) come from constants.asm (same
; bit values as P3's record, so the meaning is shared).
EF_LEFT         EQU %00001000       ; FACING_LEFT
EF_DYING        EQU %00010000
EF_WALKIN       EQU %00100000       ; horizontal follower: walk in on materialise
EF_PENDING      EQU %01000000
EF_LEFT_BIT     EQU 3
EF_PENDING_BIT  EQU 6
EF_DYING_BIT    EQU 4
EF_WALKIN_BIT   EQU 5
EF_RESPAWN      EQU %10000000       ; LP: F_RESPAWN (game.md §9.5; no drops / half XP = 3F),
EF_RESPAWN_BIT  EQU 7               ; carried through the room records (LEK_RESPAWN)

; E_MODE
M_REST          EQU 0
M_MOVE          EQU 1
M_SEQ           EQU 2
M_HOLD          EQU 3               ; player dead: hold the final frame
M_FALL          EQU 4               ; B3B-5: walk step (4 px/tick) then the drop (FALL_STEP px/tick, game.md §2.5)
M_JUMP          EQU 5               ; B3B-5: the §2.4 arc, E_TMR = arc tick 0..n+1 (JUMP_ARC)
                ASSERT M_FALL > M_HOLD && M_JUMP > M_HOLD   ; anim_entity: cp M_FALL / jr nc

; E_REACT
RC_NONE         EQU 0
RC_HURT         EQU 1
RC_BLOCK        EQU 2
RC_DEATH        EQU 3
RC_DODGE        EQU 4               ; T7: a missile missed it: no sequence, the ATTR_MISS flash at E_REACTAT

; R_DIRTY classes
DIRTY_NONE      EQU 0
DIRTY_ATTR      EQU 1
DIRTY_FULL      EQU 2               ; erase old + blit new
DIRTY_FORCE     EQU 3               ; blit again (no erase): overlap repair

; message codes (E_MSG)
MSG_NONE        EQU 0
MSG_P_HIT       EQU 1
MSG_P_MISS      EQU 2
MSG_P_KILL      EQU 3
MSG_M_HIT       EQU 4
MSG_M_MISS      EQU 5
MSG_SQUEEZE     EQU 6               ; B14 squeeze past (impact_line, never an E_MSG)
; D3-6a: deal_hit's monster lines "THE " + name + suffix (impact_line only, never an E_MSG)
MSG_M_UNAFF     EQU 7               ; " IS UNAFFECTED"
MSG_M_FROZEN    EQU 8
MSG_M_ASLEEP    EQU 9
MSG_M_STUNNED   EQU 10
MSG_M_FLEES     EQU 11              ; FEAR
MSG_M_CONFUSED  EQU 12
MSG_M_WAKE      EQU 13
MSG_M_THAW      EQU 14

;------------------------------------------------------------------------------
; Kinds (prototype §2/§6.3). Parallel byte tables, page-aligned (kind_tab).
;------------------------------------------------------------------------------
K_KNIGHT        EQU 0
K_WIZARD        EQU 1
                                ; id 2 retired (Rogue removed, G1 budget 2): hole kept so
                                ; K_* ids / HERO_KIND semantics stay stable
K_SKELETON      EQU 3
K_GOBLIN        EQU 4
K_GHOST         EQU 5
K_RAT           EQU 6
K_BAT           EQU 7
K_SLIME         EQU 8
K_COUNT         EQU 9
; LP (game.md §9.4) stand-in aliases: the per-depth kind / boss rows that do not
; exist yet map onto today's kinds of a similar body (3F adds the real rows and
; replaces these EQUs; the LP tables in bank3.asm and tools/levelgen.py use the
; names, so only this block changes).
K_SPIDER        EQU K_RAT           ; small walker
K_VAMPIRE       EQU K_SKELETON      ; tall walker
K_ORC           EQU K_GOBLIN
K_ARCHER        EQU K_SKELETON
K_MUMMY         EQU K_SKELETON
K_NECRO         EQU K_GOBLIN
K_BOSS_D1       EQU K_GOBLIN        ; Golden Goblin King
K_BOSS_D2       EQU K_SPIDER        ; Golden Spider Queen
K_BOSS_D3       EQU K_VAMPIRE       ; Golden Vampire Lord
K_BOSS_D4       EQU K_SKELETON      ; Ogre Warlord
K_BOSS_D5       EQU K_MUMMY         ; Golden Pharaoh
K_BOSS_D6       EQU K_NECRO         ; Golden High Necromancer
K_BOSS_D7       EQU K_SKELETON      ; Death Knight
K_BOSS_D8       EQU K_SKELETON      ; Archmage
; §9.3 encounter weights (game.md §9.1 W column): lp_wt (bank 3) per kind row
WT_K_KNIGHT     EQU 0
WT_K_WIZARD     EQU 0
WT_K_SKELETON   EQU 5
WT_K_GOBLIN     EQU 3
WT_K_GHOST      EQU 3
WT_K_RAT        EQU 2
WT_K_BAT        EQU 2
WT_K_SLIME      EQU 2
K_MAX           EQU 32              ; A6: kind_tab capacity (game.md §11.2: 18 needed)
; D3-4: the class FX kinds (render-only projectile / impact frames, game.md §6;
; never an entity's kind): the LAST two kind ids, so 3F's monster rows grow
; up from K_COUNT without moving them (3F has 30 ids left: 0..29). Generated
; with the hero only (start_game: gen_kind(HERO_KIND + K_FX_BASE)), so the
; pool holds the current class's FX only. Their fid ranges OVERLAP in
; frames.asm (spark_fizz1/2: Spark impact and Whirlwind impact): K_FXM =
; [mage-only | shared], K_FXW = [shared | warrior-only].
K_FXW           EQU K_MAX - 2       ; Warrior FX (= K_FX_BASE + K_KNIGHT)
K_FXM           EQU K_MAX - 1       ; Mage FX    (= K_FX_BASE + K_WIZARD)
K_FX_BASE       EQU K_FXW - K_KNIGHT
                ASSERT K_FXM == K_FX_BASE + K_WIZARD && K_FXW > K_COUNT
; body height in cells per kind (single source: kind_tab KT_BH row and the FRM
; frame-height ASSERT both use these; named BH_<kind> so FRM can paste `kind`)
BH_K_KNIGHT     EQU 6
BH_K_WIZARD     EQU 6
BH_K_SKELETON   EQU 6
BH_K_GOBLIN     EQU 4
BH_K_GHOST      EQU 4
BH_K_RAT        EQU 2
BH_K_BAT        EQU 2
BH_K_SLIME      EQU 2
BH_K_FXW        EQU 2               ; D3-4: FX frames are <= 16 px tall (FRM ASSERT only)
BH_K_FXM        EQU 2

; offsets of the parallel arrays inside kind_tab: 2 pages, 32 B per array
; (K_MAX). An array never crosses a page (kind < 32, offsets multiple of $20),
; so KFIELD keeps its 8-bit add: H = page of the array, L = low(off) + kind.
KT_BW           EQU $000            ; body width, cells          (page 0)
KT_BH           EQU $020            ; body height, cells
KT_HP           EQU $040
KT_ATK          EQU $060
KT_EVA          EQU $080
KT_DIE          EQU $0A0
KT_BONUS        EQU $0C0
KT_REACH        EQU $0E0
KT_PERIOD       EQU $100            ;                            (page 1)
KT_FLAGS        EQU $120
KT_ATTR         EQU $140
KT_FID0         EQU $160            ; first frame id of the kind
KT_FCNT         EQU $180            ; frame count of the kind
KT_MOD9         EQU $1A0            ; 24 B: n mod STOREY_ROWS (9)  (n = y+h or a row, 0..23)
KT_DIV9         EQU $1B8            ; 24 B: n div STOREY_ROWS      (same page as KT_MOD9: feet_mod)
KT_END          EQU $1D0            ; D3-8d: mark.asm code follows from here (was 48 B spare)
KT_SIZE         EQU $200

; KT_FLAGS bits
KF_FLYER        EQU %00000001
KF_CLIMBER      EQU %00000010
KF_TALL         EQU %00000100
KF_HERO         EQU %00001000
KF_BAT          EQU %00010000       ; bat jitter / wander
; %00100000 spare (D3-0: was KF_ZAP, the PROTO wizard zap)
KF_OPENER       EQU %01000000       ; B3B-5: opens closed unlocked doors by bumping (game.md §9.1)

;------------------------------------------------------------------------------
; Frame table (static, bank 2 image, frame_tab) — FT_STRIDE (4) B/fid.
;------------------------------------------------------------------------------
; A6: only what the per-tick renderer reads (blit, footprint, frame offsets)
; stays in bank 2; the generator-only part is the bank-5 descriptor (FD_*).
FT_COLS         EQU 0               ; data byte-columns (W/8)
FT_H            EQU 1               ; rows (px)
FT_OFFR         EQU 2               ; signed: frame_px = body_px + off (right)
FT_OFFL         EQU 3               ; signed: (left-facing)
FT_STRIDE       EQU 4

;------------------------------------------------------------------------------
; Frame descriptor (A6; bank 5 low RAM, fdesc_tab at the end of the cold block,
; read only by gen_frame) — 5 B/fid:
;   FD_BLK   word: VIRTUAL address of the frame's packed block
;                  (banks 1/3; also the GEN_ZBLK cache key)
;   FD_FRM   word: the frame's address inside GEN_SCRATCH once its
;                  block is unpacked (GEN_SCRATCH + in-block offset)
;   FD_FLAGS byte: FF_*
;------------------------------------------------------------------------------
FD_BLK          EQU 0
FD_FRM          EQU 2
FD_FLAGS        EQU 4
FDESC_STRIDE    EQU 5
FDESC_RESERVE   EQU FRT_MAX * FDESC_STRIDE  ; 800 B at FRT_MAX (game.md budgeted <= 12 B x 160)

FF_MOTION       EQU %00000001       ; store both shifts (0 and 4)
FF_SYM          EQU %00000010       ; symmetric: left = right (no mirror)

; FRT variant: v = facing_left*2 + (shift4 ? 1 : 0); 3 B each (bank, lo, hi)
FRT_NONE        EQU $FF             ; bank byte for "variant not generated"

;------------------------------------------------------------------------------
; Sequences: 3 B/entry (fid, ticks, flags); fid $FF = end.
; Cycles: first byte = total ticks, then 2 B/entry (fid, ticks), fid $FF = end.
;------------------------------------------------------------------------------
SF_IMPACT       EQU %00000001
SF_HIDE         EQU %00000010
SEQ_END         EQU $FF

; kind sequence-block layout (DW pointers), 2 B each
KS_IDLE         EQU 0               ; cycle
KS_MOVE         EQU 2               ; cycle
KS_CLIMB        EQU 4               ; cycle
KS_CLIMBREST    EQU 6               ; DB fid, DB 0 (resting on a ladder)
KS_ATTACK       EQU 8               ; seq
KS_HURT         EQU 10              ; seq
KS_BLOCK        EQU 12              ; seq
KS_DEATH        EQU 14              ; seq
KS_IMPACT       EQU 16              ; DB ticks before IMPACT in KS_ATTACK
KS_STRIDE       EQU 17

;------------------------------------------------------------------------------
; Tiles (8x8 background, cell-aligned). attr = TILE_ATTRS[id] always.
;------------------------------------------------------------------------------
T_AIR           EQU 0
T_PLAT          EQU 1
T_BRICK         EQU 2               ; wall in an air band
T_WALLF         EQU 3               ; wall in a floor row
T_LAD_L         EQU 4
T_LAD_M         EQU 5
T_LAD_R         EQU 6
T_HOLE_L        EQU 7               ; ladder cells in a floor row
T_HOLE_M        EQU 8
T_HOLE_R        EQU 9
T_POTION        EQU 10
; (B3B-13: the PROTO chest stand-in T_CHEST_* (per-level ids 32..35) and the
; zap tile ids T_ZAP1/2 (now T_DRIP1/2) are gone; D3-0: the zap itself too.)
T_TORCH_T       EQU 15
T_TORCH_B       EQU 16
T_END_L         EQU 19              ; PLATFORM_END_L: floor cell right of a hole
T_END_R         EQU 20              ; PLATFORM_END_R: floor cell left of a hole
T_COUNT         EQU 21

; attrs (prototype §4.1)
ATTR_AIR        EQU $00
ATTR_WALL       EQU $01
ATTR_FLOOR      EQU $0F
ATTR_LADDER     EQU $02
ATTR_POTION     EQU $42
ATTR_TORCH      EQU $46
ATTR_HIT        EQU $42
ATTR_HEAL       EQU $44
ATTR_MISS       EQU $46             ; T7: dodge flash (bright yellow: no kind uses it)
ATTR_HUD        EQU $47             ; bright white on black (screen clear; panel text, depth)

; room geometry: STOREY_COUNT / STOREY_ROWS / PLAY_ROWS ... (level_defs.asm, B3B-3)
MAX_POTIONS     EQU 9
QUAFF_HEAL      EQU 8
FOLLOW_GAP      EQU 4
FOLLOW_MAX      EQU 2
ROOM_CAP        EQU 4               ; monsters per room (on-screen cap)
TALL_CAP        EQU 2
FLASH_TICKS     EQU 2
MISS_FLASH      EQU 3               ; T7: dodge flash ticks (the 1-cell/tick arrow crosses a 3-cell body)
EXIT_NONE       EQU $FF
TICK_FRAMES     EQU 2               ; 25 Hz
    IFNDEF RENDER_FIRST                         ; E0: 1 = render right after wait_tick
RENDER_FIRST    EQU 1                           ;     (build with -DRENDER_FIRST=0 for the old order)
    ENDIF
TWEEN_STEP      EQU 4               ; px per tick
FALL_STEP       EQU 8               ; B3B-5: px per tick of a pit fall (game.md §2.5: 9 rows, 9 ticks)
FALL_DIE        EQU 4               ; fall damage 1d4, ignores DEF
JUMP_COLS       EQU 6               ; B3B-5 jump (game.md §2.4): body x..x+2 -> x+6..x+8
JUMP_COLS7      EQU 7               ; J1: the low-body extension (Rat / Spider adjacent, game.md §2.4)
JUMP_RISE       EQU 2               ; swept box rows top-2 .. bottom
JUMP_APEX       EQU 4               ; J1: arc steps of 4 px to the 16-px apex (dy = -4 min(t, N-t, 4))
ATTR_DOOR       EQU $06             ; door arch / planks (concept-screen §3.1)
ATTR_RUBBLE     EQU ATTR_WALL       ; concept-screen §3.3 #12
ATTR_GRATE      EQU $46             ; lair gate, raised (B12 variant B; tiles_common id 26)

; KFIELD off — A = kind_tab[kind(IX) + off].  Clobbers: A, HL   (~45 T)
; off is a KT_* constant: its page is folded into H at assembly time.
    MACRO KFIELD off
                ld   a, (ix+E_KIND)
                add  a, (off) & $FF
                ld   l, a
                ld   h, (kind_tab + (off)) >> 8
                ld   a, (hl)
    ENDM

;------------------------------------------------------------------------------
; FRM name, kind, body_w_px, flags — one frame of the frame list (src/frames.asm).
; The list is INCLUDEd twice (A6):
;   FRM_EMIT = FRM_DESC  lowram.asm fdesc_tab (bank 5): the generator's 5-B
;                        descriptor FD_BLK, FD_FRM, FD_FLAGS (defs.asm FD_*)
;   FRM_EMIT = FRM_HOT   data.asm frame_tab (bank 2): the renderer's 4-B entry
;                        FT_COLS, FT_H, FT_OFFR, FT_OFFL; defines FID_<name> and
;                        accumulates POOLACC = bytes this frame costs in the
;                        pre-shift pool (both facings; MOTION = shifts 0+4,
;                        STATIONARY = the one shift its anchor implies; SYM =
;                        one facing shared).
; STAND-IN RULE (prototype §10): a frame is included only if its label EXISTS in
; the sprite sources AND its anchor is legal (§5.3: ax mod 4 == 0, 0 <= ax <= 8,
; 0 <= ax_L <= 16); otherwise FID_<name> = -1 and the ROLE tables fall back.
; Both passes apply the same rule, so fid n is entry n of both tables
; (ASSERTed: FDESC_COUNT == FID_COUNT).
;------------------------------------------------------------------------------
FRM_DESC        EQU 0
FRM_HOT         EQU 1

    MACRO FRM nm, kind, bwpx, flg
FRM_OK = 0
    IF EXIST nm
      IF ((nm_ax & 3) == 0) && (nm_ax <= 8) && ((nm_w - nm_ax - bwpx) >= 0) && ((nm_w - nm_ax - bwpx) <= 16)
FRM_OK = 1
      ENDIF
    ENDIF
    IF FRM_EMIT == FRM_DESC
      IF FRM_OK
FCTR = FCTR + 1
        DW   nm                                ; FD_BLK
        DW   GEN_SCRATCH + nm_zoff             ; FD_FRM
        DB   flg                               ; FD_FLAGS
      ENDIF
    ELSE
      IF FRM_OK
FID_nm EQU FCTR
FCTR = FCTR + 1
        ; bottom-anchored frames must fit the body rows and be whole cells
        ; (fpy = py + bh*8 - H stays inside the body, row fix-up every 8 lines)
        ASSERT (nm_h <= BH_kind * 8) && ((nm_h & 7) == 0)
        DB   nm_cols, nm_h, low(0 - nm_ax), low(0 - (nm_w - nm_ax - bwpx))
        IF (flg) & FF_MOTION
          IF (flg) & FF_SYM
POOLACC = POOLACC + nm_h * 2 * (2 * nm_cols + 1)
          ELSE
POOLACC = POOLACC + 2 * nm_h * 2 * (2 * nm_cols + 1)
          ENDIF
        ELSE
POOLACC = POOLACC + nm_h * 2 * (nm_cols + (((nm_ax & 7) != 0) & 1))
          IF ((flg) & FF_SYM) == 0
POOLACC = POOLACC + nm_h * 2 * (nm_cols + ((((nm_w - nm_ax - bwpx) & 7) != 0) & 1))
          ENDIF
        ENDIF
      ELSE
FID_nm EQU -1
      ENDIF
    ENDIF
    ENDM

MOT             EQU FF_MOTION
STA             EQU 0
SYM             EQU FF_SYM

;------------------------------------------------------------------------------
; Stage 3B data contracts (B3B-1): EQUs + ASSERTs only, no bytes.
;------------------------------------------------------------------------------
                INCLUDE "level_defs.asm"
                INCLUDE "hero_defs.asm"         ; C3-0: Stage 3C contracts (HERO_ST, JOY_MIRROR, KEYTAB)
                INCLUDE "combat_defs.asm"       ; D3-0: Stage 3D state homes + layouts (ST_*, FXREC, KX, ...)
; B3B-13: message string ids TX_* / decoded lengths TXL_* (+ ASSERT <= LOG_MAX),
; generated from src/strings.txt by tools/textpack.py (tools/build.sh)
                INCLUDE "../build/text/strings_ids.inc"

; MUL_STOREY r — A = A * STOREY_ROWS (A = storey 0..2), r = the old A.  Clobbers: r.
; ld r,a + 8a + a: 5 ops, 20 T (the PROTO 7a was 8a - a at the same cost).
                ASSERT STOREY_ROWS == 9
    MACRO MUL_STOREY r
                ld   r, a
                add  a, a
                add  a, a
                add  a, a
                add  a, r
    ENDM
