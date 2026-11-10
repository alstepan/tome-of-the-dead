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
BANK_BOOT6      EQU BANK_POOL2      ; 3E-T1: the boot block BOOT6_ADDR..SRC6_ADDR-1 (boot6.asm), dead after boot
; R6 (2026-10-21, user-approved carve of the pool slack): a PERMANENT code +
; data region at the top of bank 6, R6_ADDR..$FFFF, own tape block (main.asm
; "R6 REGION", src/r6.asm). The pool's bank-6 part ends at R6_ADDR (alloc;
; POOL_CAP - R6_LEN). Code there is ORGed at its $C000+ address and entered
; through far6 (gfx.asm); packed overlay streams there run through ovl_run
; with C = BANK_R6. R6_LEN is THE cap (ASSERTed, free bytes DISPLAYed).
BANK_R6         EQU BANK_POOL2
; 3F-T2 (MEM-3F): + R6_GROW pages from the 3F-T1 pool slack (27 -> 27 + R6_GROW
; pages): the kind sequence masters, the generation-unit table, the seq cache
; loader, and >= 1.5 KB free for 3F code.
R6_GROW         EQU 15                  ; 3F-T11b: +1 page (the Archmage spell AI, arch6.asm; pool -256); MEM-RECLAIM w4: +1 page for T11 (paid by MEM-PS2's exact pool need); 3F-T8: +3 pages (bosses: grate / guard / post / glow / SLAM); 3F-T7: 8 -> 10
R6_LEN          EQU (27 + R6_GROW) * 256   ; was $1B00 (27 pages, 2026-10-21)
R6_ADDR         EQU $10000 - R6_LEN ; $D600 (3F-T11b, R6_GROW 15)
                ASSERT (R6_ADDR & $FF) == 0
; SRC6 (3F memory plan; SRC6 spike 2026-10-27): a PERMANENT bank-6 SPRITE-SOURCE
; region just BELOW R6, SRC6_ADDR..R6_ADDR-1 (SRC6_LEN = SRC6_PAGES x 256: the
; size parameter), carved out of the pool 1:1 (POOL_CAP - SRC6_LEN). ZX0 blocks
; only (build/zx0/src6_zx0.asm, tools/zx0_sources.py), read by zx0_frame. Their
; FD_BLK is VIRTUAL like banks 1 / 3, in the free $4000..$7FFF range: SRC6 real
; address - SRC6_VDELTA (banks 1 / 3 use $8000..$FFFF), so the GEN_ZBLK cache
; key stays unique and no FD_FLAGS bit is spent. Its tape bytes ride on the
; boot block's tape block (BOOT6_TAPE_LEN, main.asm).
    IFNDEF SRC6_PAGES
SRC6_PAGES      EQU 14              ; MEM-RECLAIM w3: 16 -> 14 (K_MUMMY + G_NBOLT, 470 B packed, back to bank 1 sources: 3,569 B used, 15 free; +512 B POOL_CAP); ANIM-X12: 15 -> 16 (Orc + Vampire 4th walk pose, +75 B packed; 3,876 B, 220 free); ANIM-IMPORT2: 13 -> 15 (the Vampire's own set, 2 blocks 675 B; 14 blocks 3,801 B, 39 free; -512 B POOL_CAP, R6 untouched); 3F-T13bc: 10 -> 13 (+ the ART2 / ART3 frames, 12 blocks, 3,173 B, dk_block out); 3F-T13: the 3F-A1 sources (8 blocks, 2,393 B packed; was 1 = the spike's Spider stand-in)
    ENDIF
    IFNDEF SRC6_STANDIN
SRC6_STANDIN    EQU 0               ; bit mask of the zx0_sources.py stand-in groups assembled into SRC6 (3F-T13: none, the real art replaced them)
    ENDIF
BANK_SRC6       EQU BANK_POOL2
SRC6_LEN        EQU SRC6_PAGES * 256
SRC6_ADDR       EQU R6_ADDR - SRC6_LEN
SRC6_VDELTA     EQU $8000           ; FD_BLK = real - $8000: virt $4000..$7FFF = bank 6
POOL6_END       EQU SRC6_ADDR       ; the pool's bank-6 part ends here (alloc)
                ASSERT SRC6_PAGES >= 1 && SRC6_ADDR >= BANK_WINDOW + $0800   ; 3F-T13: was + $1000; the boot block below
                                                ; SRC6 is ASSERTed to fit bank 6 in main.asm (boot6_code)
                ASSERT (POOL6_END & $FF) == 0   ; alloc's bank-6 limit test reads only the high byte
BANK_SHADOW    EQU 7               ; D3-S2: the ATTR shadow ($F800, erase_rect's attrs)
BANK_COLD7      EQU 7               ; D3-S2: bank-7 cold code B7_CODE..B7_LIMIT (via far7)
BANK_SCREEN7    EQU 7               ; A7: the displayed screen during play, $C000..$DAFF
BANK_COLD3      EQU BANK_SRC_HI     ; bank-3 cold code (select, scrolls) after the source tail; via far3
AY_RESERVE      EQU $F048           ; D3-11: $F040 -> $F048 (+8 B bank-3 cold code; the AY slot keeps 1 B, user 2026-11-02); RECLAIM-C (a): $F010 -> $F040 (+48 B bank-3 cold code; the AY slot keeps 9 B, user 2026-11-02: the spare reserve only, no sound cut); M0 (L3): $EFD0 -> $F010 (+64 B bank-3 cold code; the AY slot keeps 57 B for 3G SFX); MEM-RECLAIM w3: $EFA0 -> $EFD0 (+48 B bank-3 cold code for lq_block; 121 B SFX slack kept); was: A8 / D3-0 / MEM-SND / 3E lever (c): bank 3 $EFA0..$FFFF = 4192 B AY player/music/FX
                                    ;     reserve (game.md §11.2, user 2026-10-06: 7 KB -> 4 KB at $F000,
                                    ;     was $E400; MEM-SND: -608 B after 406 B of bank-3 cold code went
                                    ;     to bank 7, ~200 B bank-3 slack kept; 3E lever (c): +512 B
                                    ;     back to bank-3 cold code, 167 B SFX slack kept); cold code + sources end below
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
SFX_IDX_MASK    EQU $1F             ; bits 0-4 = index 0..SFX_COUNT-1 into sfx_tab
SFX_DUCK_PRIO   EQU 6 << 5          ; prio >= 6 ducks deeper
SFX_DUCK_LO     EQU 3               ; any effect: the music's V2 / V3 fixed volumes - 3 (floor 0)
SFX_DUCK_HI     EQU 4               ; prio >= SFX_DUCK_PRIO: - 4
DNG_DWELL       EQU $BFF1           ; SND-3 (mus7.asm): turns since W entered (sat. 255), 0 = W off
DNG_CALM        EQU $BFF2           ; SND-3: consecutive turns without the danger condition
SFX_NEXT        EQU $BFF3           ; SND-5: ONE deferred SFX id (prio >= SFX_DEFER_PRIO that lost to
                                    ; a pending / playing higher one); the ISR takes it when the
                                    ; playing effect ends. sfx_req and the ISR write it, 0 = none
SFX_XP          EQU $BFF4           ; 3E-T0: transpose (signed semitones, two's complement) for the NEXT SFX_STATUS
                                    ; take; sfx_msg writes it before sfx_req, the ISR copies it to sfx_xp
                                    ; at the take (only for SFX_STATUS; every other effect plays at 0)
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
; 3E-T2 page window (docs/memory-map.md "Overlays", page-fullscreen rev): while
; the bag page is up, screen 2 holds the composed screen (the backup,
; present_full), the bank-5 screen shows the page on all 24 rows, and the page
; overlay runs in GEN_SCRATCH ($6000, 1,536 B): page_ovl saves the live room
; map (ROOM_MAP, PLAY_CELLS B) to PAGE_MAP_SAVE first and page_post puts it back
; (NEXT_MAP, the ZX0 frame cache and the LG_* / LP_CMAP scratch hold nothing
; that lives across the modal page).
PAGE_ORG        EQU GEN_SCRATCH
PAGE_LIMIT      EQU GEN_SCRATCH + GEN_SCRATCH_LEN
PAGE_MAP_SAVE   EQU GEN_SRC             ; GEN_SRC.. (no pause save / pblit / generator meanwhile)
; 3E-T13 page-time scratch after the map save (free while the page is up; below TX_DEC):
; (IC1: the 32-B PAGE_G60 glyph copy is gone: the page draws the R6 16x16 icons)
PAGE_BUF        EQU PAGE_MAP_SAVE + PLAY_CELLS  ; PAGE_BUF_LEN B: a composed text line (print6)
PAGE_BUF_LEN    EQU 40                          ; WEAR-UI: 39 chars + 0 (the row-19 line from x 16 is 40 chars wide; the longest gear line, the Cleaver at m -3, is 37)
PAGE_SCR_END    EQU PAGE_BUF + PAGE_BUF_LEN
; 3E-T6: the level-start item / trap generator overlay (items_ovl.asm) runs
; in the same window at a level start (after level_populate: the LG_* /
; LP_CMAP scratch is dead), its packed stream in bank BANK_OVL_ITEMS (main.asm
; bank 1 tail, MEM-1; any bank ovl_run can page: move the INCBIN + this EQU together).
ITEMS_ORG       EQU GEN_SCRATCH
BANK_OVL_ITEMS  EQU BANK_UI1       ; MEM-1: back in bank 1 (main.asm, after the it_text block)
BANK_OVL_PAGE   EQU BANK_R6         ; R6: the page stream (page_ovl, menu1.asm)
; INSTR-BUILD: the HOW TO PLAY screen (game.md §3.2.1 option A flow, docs/design/
; instructions_screen.md / .txt pages): boot-only overlay instr_ovl.asm at INSTR_ORG,
; its page images (tools/instr_pack.py) unpacked by it to INSTR_DATA (right after its
; code, same window). All four ZX0 streams sit in bank 0 right after the text block
; (POOL_START.., on the text tape block; the boot pool overwrites them after the help).
INSTR_ORG       EQU GEN_SCRATCH
; D3-11: the PROTO rooms test fixture (src/proto_fix.asm, build/ovl/proto.bin, never in
; the image): run in the bank-5 screen bitmap (the menu's, cleared by level_show) once
; tests/game_lib.py has poked it there at start_game's proto_hook.
PROTO_FIX_ORG   EQU SCREEN_BITMAP
BANK_INSTR      EQU BANK_TEXT
; TUT0-T1: the D0 tutorial BLOB (docs/design/tut0_split.md "Verdicts" F4; memory-map
; "TUT0 blob"): code + data assembled at BLOB_ORG in bank 4 (src/tut/tut_blob.asm), its
; ZX0 stream the LAST stream of the bank-0 text tape block (blob_zx0, + a DW length
; trailer). The INSTR overlay's common exit bounce-copies the stream (PF_RAM) to the top
; of bank 4 and unpacks it in place to BLOB_ORG (once per power-on). Entered only through
; the two low-RAM stubs (src/tut/tut_stub.asm over check_paging, farb with C = BANK_BLOB).
; Pool bytes: the D1+ pool overwrites it (both SMC patches are undone by then); the D0
; pool must end below BLOB_ORG (main.asm "LEVEL POOL NEED", D0 session ASSERT).
BANK_BLOB       EQU BANK_POOL1      ; 4
BLOB_ORG        EQU $E000           ; TUT0-F2: was $E800 (2 KB more; D0 pool tops $D140 W / $C5C0 M,
                                    ; overlay scratch OVL_RAW_END $D930: both ASSERTed below it)
BLOB_RES        EQU 8192            ; BLOB_ORG..$FFFF: raw image + the in-place ZX0 delta
                ASSERT BLOB_ORG + BLOB_RES == $10000
BLOB_CHOICE     EQU BLOB_ORG + 0    ; entry table (tut_blob.asm): A = menu hero kind -> C = hero
BLOB_TURN       EQU BLOB_ORG + 3    ;   A = 1 before end_turn, 0 after
BLOB_ICON       EQU BLOB_ORG + 6    ;   TUT0-R2: the ICON MODE tour (ts_icon, after intent_icon7)
IK_I16          EQU 1               ; page icon record kinds (instr_pack.py): R6 ic_scr, logical index
IK_BAR          EQU 2               ; 24x16 bar icon, vdata label (bank-3 pblit)
IK_GLY          EQU 3               ; 8x8 label, vdata label (bank-3 glyph8)
IK_TILE         EQU 4               ; a common tile id (TILE_GLYPHS, 1 cell)
; (3E-T8's fx overlay is gone since 3E-T12: ZX0 packed its code only 3 %, so the
; effects are R6-resident code, src/fx6.asm, entered by far6.)
B7_CODE         EQU $DB00           ; bank 7: cold code b7_code..b7_end (src/bank7.asm), right
                                    ;     after screen 2 (MEM-RECLAIM w2a: was $E000, above tilesets 0..3)
B7_LIMIT        EQU $F800           ; ... up to the attr shadow (ASSERTed)
SHADOW_ATTR     EQU $F800           ; bank 7: room tile attrs in screen layout ($F800..$FA3F = rows 0..17;
                                    ;     M0 (L2): the 3 spare PROTO rows $FA40..$FA9F went to TSET_BASE)
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
; M0 (lever L4, user 2026-10-31): POOL_START is FIXED above a shared reserve for the
; text block (TEXT_LEN 2,326 B at M0 + 45 B of post-3F strings) and the bank-0 cold
; code (b0_code, main.asm). ASSERT b0_code_end <= POOL_START (main.asm): text and code
; may trade bytes. The pool slack is QUANTISED here (memory-map "M0 / post-3F ledger"):
; the worst level (D8 Warrior) leaves a ~74-B tail at bank 0's end, so a reserve of
; 45 + 29 B costs 0 slack (1,264 kept), but 45 + 30..250 B costs one 240-B variant
; (slack 1,024) and 45 + 260 B 880. M1 (user 2026-11-01) took the 240-B step: total reserve 2,624 B
; (cliff measured: B0_CODE_RES 206 -> slack 1,024, 207 -> 384, with TEXT_RES 2,418).
TEXT_RES        EQU 2367 + 33                  ; RECLAIM-B T1: DP-parsed text 2372 B + 28 B headroom (was 2384 + 28; LOG-DMG: 2367 + 45)
B0_CODE_RES     EQU 704                        ; D3-11 (user 2026-11-02, the pool-slack step): log0.asm 212 + dnum0.asm;
                                               ; the D8 Warrior slack 1,024 -> 384 (cliff measured with TEXT_RES 2,400:
                                               ; 704 -> 384, 708 -> the pool no longer fits). LOG-DMG: 212 (M1: 206)
; LOG-DMG + DBG-1: kit builds only — kit0.asm (83 B) + log0.asm (212 B) exceed the release reserve by
; ~38 B: the kit image takes the next pool-slack variant (D8 Warrior slack 1,024 -> 384, kit only;
; tests/kit.py runs it). The RELEASE layout (POOL_START $CA40, slack 1,024) is unchanged.
B0_KIT_RES      EQU 0                          ; D3-11: 0 (was 80 x DEBUG_KIT): the slack step's 704-B code reserve holds kit0.asm too
POOL_START      EQU TEXT_ADDR + TEXT_RES + B0_CODE_RES + B0_KIT_RES  ; $CA40 (release): alloc_reset's first bank-0 pool byte
    MACRO FARB0 target                  ; call a bank-0 cold-code routine (8 B; A / DE / IX pass in;
                ld   hl, target         ;   C lost to the bank, B to farb's A): farb pages BANK_TEXT
                ld   c, BANK_TEXT
                call farb
    ENDM
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
GEN_SRC         EQU $6940           ; 512 B: staging for vdata reads (pblit, copy_virt; 3E-T1: boot no longer)
MENU_TORCH_BUF  EQU GEN_SRC           ; RECLAIM-C (d): 48 B, menu_static only (title menu: no room live, no pause /
                                    ; page / generator meanwhile): the torch's static cells fetched from bank 7 (ldir7)
MENU_TORCH_FBUF EQU GEN_SRC + 48      ; RECLAIM-C (d) + LOOK-1: 16 B, menu_torch: a flame frame's 2 cells (ldir7, used at once)
GEN_MIR         EQU $6B40           ; 512 B: mirrored copy (left-facing)
LOWRAM_END      EQU $6D40
; FLOOR1 floor-item glyph cache (docs/memory-map.md "FLOOR1"). One room (<= FI_SLOTS
; distinct types). The bytes erase_rect reads per drawn item line are UNCONTENDED
; bank 2: FI_GLY (the icons, $BD00: the bottom of the old 768-B stack; the
; stack keeps 512 B, W20 asserts its depth <= 256 B, measured 66 B). The rest
; (FI_TSLOT .. FI_INK, $699F..$6CFF) is low RAM in the play-free GEN_SRC /
; GEN_MIR window (pblit stages <= 54 B below it; TX_DEC above): the pause save /
; the page's map save / the generator overwrite it,
; so each of them is followed by fi_full (bank 3). Built by fi_full from
; FLOOR_LIST, kept by fi_add (R6: one col, a pickup / a drop), read by
; erase_rect (bank 2, the T_ITEM0..3 marker cells) and fi_cells (lowram: room
; draw, scroll strips).
FI_SLOTS        EQU 8               ; distinct item types drawn per room
FI_NONE         EQU $FF             ; FI_TSLOT: type not cached; FI_TYPE: slot free
FI_PAD          EQU $699F           ; 1 B: FI_NONE always (FI_TSLOT[FI_NONE]: the "no type" read / write)
FI_TSLOT        EQU $69A0           ; 64 B: item type -> its slot, FI_NONE
FI_TYPE         EQU FI_TSLOT + 64   ; 8 B: slot -> its type, FI_NONE (contiguous: fi_full fills both)
FI_USE          EQU FI_TYPE + FI_SLOTS  ; 8 B: != 0 = a live entry of the room has the slot's type
FI_CELL         EQU $6A00           ; 2 pages: storey s's at FI_CELL + 256 s, indexed by the map /
                                    ;   screen low byte L of a marker cell ((row & 7) << 5 | col:
                                    ;   s0 rows 6 / 7 = $C0.. / $E0.., s1 rows 15 / 16 = $E0.. / $00..)
                                    ;   = its FI_GLY low byte (slot * 32 + 8 * quarter); valid where
                                    ;   the map holds T_ITEM0 + k; the rest of the 2 pages unused
FI_END          EQU FI_CELL + 512
FI_GLY          EQU $BD00           ; 256 B bank 2: slot s's 16x16 icon at FI_GLY + 32 s (icons16 layout:
                                    ;   4 quarters UL, UR, LL, LR of 8 contiguous lines)
FI_INK          EQU $6C00           ; 256 B: the ink of the slot of FI_GLY byte b at FI_INK + b (32 x
                                    ;   per slot: one read with the glyph pointer's low byte); GEN_MIR,
                                    ;   below TX_DEC (play-free)
; D3-TX: tx_dec's decode buffer (a whole string, 0-terminated, readable with any
; bank paged: bank-1 UI code can no longer read the text in place). The top of
; GEN_MIR: transient (filled and consumed inside one menu call), above the
; pause overlay's save (PAUSE_SAVE..+PAUSE_LEN, ASSERTed in menu1.asm); the
; generator (its other user) never runs inside a menu text call.
TX_DEC_LEN      EQU 43              ; textpack WIDE_MAX 42 + the 0
TX_DEC          EQU LOWRAM_END - TX_DEC_LEN   ; $6D15..$6D3F
TILE_IDS        EQU 64              ; tile id capacity (glyphs/attrs above)
TILE_COMMON     EQU 32              ; ids 0..31: engine/common tiles (boot6_tiles)
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
FRT_MAX         EQU 144             ; MEM-FT: 132 -> 144, the most the $A700 page holds (FRT_GAP 0; a
                                    ; 145th fid steps FRT down a page, -256 B bank 2); 129 used, 15 spare.
                                    ; Each fid also reserves FDESC_STRIDE (5) B of low RAM (main.asm fit).
                                    ; 3F-T13bc: 128 -> 132; CORPSE-ASHES: 129 used; 3F-T2: 160 -> 128
FRT             EQU (P_ENTITIES - FRT_MAX * FRT_STRIDE) & $FF00   ; page-aligned (blit_sprite's nibble swap):
                                    ; MEM-FT $A700..$AFFF; frame runtime table, 16 B/fid: 4 variants
                                    ; x bank,lo,hi (0..11) + the fid's frame_tab entry (FT_IN_ROW..15,
                                    ; static: instr_ovl in_ft unpacks it, nothing rewrites it); directly below
                                    ; ENTITIES; seq_rows sits directly below it (main.asm)
FRT_GAP         EQU P_ENTITIES - (FRT + FRT_MAX * FRT_STRIDE)   ; free bank-2 RAM between the FRT and
                                    ; ENTITIES (MEM-FT: 0; 3F-T13bc 192 held seq_rows, now below FRT)
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
R_LOG           EQU 12              ; 1 = log this draw in ANIM_TRACE (ANIM_TRACE_ON only:
                                    ; unwritten / unread in a release build)
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
STACK_BOTTOM    EQU $BE00           ; stack grows down from $BF00 to here (512 B; FLOOR1: $BD00.. = FI_GLY)
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
    IFNDEF ANIM_TRACE_ON                        ; RECLAIM-C2: 1 = render logs (slot, fid) per drawn
ANIM_TRACE_ON   EQU 0                           ;     frame change in ANIM_TRACE (test observable);
    ENDIF                                       ;     default 0 (D3-11 trace relief: was DEBUG_KIT,
                                                ;     the kit build pays bank 2 / bank 7 for the
                                                ;     flying numbers); the release tape never had it.
                                                ;     tests/game.py builds -DDEBUG_KIT=0
                                                ;     -DANIM_TRACE_ON=1 privately when build/ lacks it
                ASSERT ANIM_TRACE_ON == 0 || ANIM_TRACE_ON == 1
    IFNDEF TOME_FX                              ; TOME-FX (user 2026-11-03, game.md §1.3): the Tome's hit flash /
TOME_FX         EQU 1 - ANIM_TRACE_ON           ;     ash + sounds (tome7.asm). 0 only in a trace test build
    ENDIF                                       ;     (bank 7 has 6 B and bank 2 4 B left there: it would not fit)
                ASSERT TOME_FX == 0 || TOME_FX == 1
    IFNDEF TOME_FX2                             ; TOME-FX2 (user 2026-11-03: faster flash / border flash): the Tome
TOME_FX2        EQU TOME_FX * (1 - DEBUG_KIT)   ;     hit effect is timed by a bank-0 per-tick hook (dnum0.asm dn_tm,
    ENDIF                                       ;     21 B, 43 B with the border): the kit image has only 10 B left
                                                ;     in bank 0 (kit0.asm), so a kit build keeps the TOME-FX timing
                                                ;     (restore on the first INPUT tick) until the bank-0 reclaim
                                                ;     exists; -DTOME_FX2=1 there fails the b0_code_end ASSERT
                ASSERT TOME_FX2 == 0 || TOME_FX2 == 1
    IFNDEF ENDCARD_RK                           ; ENDCARD-K (user playtest 2026-11-04): 1 = a hero killed by
ENDCARD_RK      EQU (1 - DEBUG_KIT) * (1 - ANIM_TRACE_ON)   ; his own bolt a body reflected is "KILLED BY"
    ENDIF                                       ;     the reflector (bank-2 killer2.asm dh_killer, 25 B after
                                                ;     kind_tab). 0 in the kit (infinite lives: the revive clears
                                                ;     ST1_KILLER; bank 2 has 0 B after kind_tab there) and the
                                                ;     trace test build (bank 2 4 B): the ENDCARD-G1 rule
                ASSERT ENDCARD_RK == 0 || ENDCARD_RK == 1
    IFNDEF TOME_BORDER                          ; TOME-FX2: 1 = every Tome hit also flashes the border (white; yellow
TOME_BORDER     EQU 1                           ;     on the last hit) for the 2 ticks the lectern is white; 0 = the
    ENDIF                                       ;     fast lectern flash only (22 B less)
                ASSERT TOME_BORDER == 0 || TOME_BORDER == 1
    IFNDEF F3_GEN                               ; 3F switch == tools/levelgen.py generate(..., f3=True):
F3_GEN          EQU 1                           ;     LVL_FLAGS = 0 (grate shut, all depths), the D8
    ENDIF                                       ;     Sanctum leaf + the Tome ending (P3: default 1);
                                                ;     0 = the 3B D8 stand-in (descend from D8 = win)
    IFNDEF PHASE_SHIFT                          ; phase-locked walk shifts (2026-10-21 default):
PHASE_SHIFT     EQU 1                           ;     a walker's walk frame is only ever drawn
    ENDIF                                       ;     at one px parity -> one stored shift
                                                ;     (WK4 / WK0, frames.asm); anim_entity
                                                ;     .walkph locks it. 0 = escape hatch (both
                                                ;     shifts, pre-lock image); 2 = soak
                                                ;     diagnostic (unlocked + PHASE_TRAP)
                ASSERT PHASE_SHIFT >= 0 && PHASE_SHIFT <= 2

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
    IF ANIM_TRACE_ON                ; (release: $BF1B and $BF20..$BF3F unused, no symbol)
ANIM_TRACE_IDX  EQU $BF1B           ; next write offset into ANIM_TRACE (0..30, even)
    ENDIF
LAST_TICK_FRAME EQU $BF1C           ; SYS_FRAMES low byte at the current tick start
TURN_TICK       EQU $BF1D           ; ticks elapsed in the current ANIM phase
NEED_RELEASE    EQU $BF1E           ; edge-trigger latch (INPUT_REPEAT = 0)
EXIT_KIND       EQU $BF1F           ; pending exit after this turn's anim (EX_*)
    IF ANIM_TRACE_ON
ANIM_TRACE      EQU $BF20           ; 32 B ring: (slot, frame_id) per drawn change
ANIM_TRACE_LEN  EQU 32
    ENDIF
BLIT_MISS       EQU $BF40           ; count: stationary frame asked at a missing shift
GEN_OVERFLOW    EQU $BF41           ; 1 if the pre-shift pool ran out (build bug)
ALLOC_IDX       EQU $BF42           ; pool bank index 0..2
ALLOC_PTR       EQU $BF43           ; word: next free byte in the paged pool bank
ALLOC_MARK_IDX  EQU $BF45           ; 3F-T1: the LEVEL mark (start_game, after idles + hero + FX; level_enter rewinds)
ALLOC_MARK_PTR  EQU $BF46           ; word
CLIMB_BLK_XY    EQU $BF48           ; B18 word: CLIMB_BLK_ID's (x, y) at its last block (climb_blocked)
PHASE_TRAP      EQU $BF4A           ; PHASE_SHIFT 1 / 2 (default 1): count (since boot, wraps) of walk ticks whose
                                    ; E_WPH parity disagreed with px parity (lock changed the frame; expect 0)
GLOW_CNT        EQU $BF4B           ; 3F-T8: golden-glow tick count (main.asm .panel ticks; boss2.asm glow_kat); D3-0: was ZAP_LEN
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
SEQ_TRAP        EQU $BFFB           ; count (saturating): sq_load got a kind with no master block (ksm_tab 0) or no free cache slot
                                    ;   (the kind would blit the hero's sequences; build-ASSERTed never; debug trap, expect 0)
; LOG-DMG (docs/design/log_damage.md §4): the log-number carriers, always mapped (the bank-0
; composer log0.asm reads them with BANK_TEXT paged). Were the bank-3 deal_hit scratch dh_lost /
; dh_eff (combat3.asm EQUs them here: bank 3 -2 B).
LN_VAL          EQU $BFFC           ; = dh_lost: the HP the last deal_hit target lost (melee_strike / self /
                                    ;   burst lines; log_room_d: the self-bolt's pf_lost; hero_fall)
LN_G            EQU $BFFD           ; the HP gained by the hero's last heal (deal_hit drain, cap_add)
DH_EFF          EQU $BFFE           ; deal_hit's effect parameter (combat3 dh_eff; scratch)
GEN_TRAP       EQU $BF99           ; count: gen_frame ran while PLAYING/TRANSITION (GEN_SCRATCH = live room maps; debug trap, expect 0)
MSG_BUF         EQU $BFA0           ; 32 B: impact message composition (show_impact_msg -> log_push)
TIMING_MARK     EQU $BFC0           ; spare
IT_BAD          EQU TIMING_MARK     ; DEBUG_KIT only: count of item_glyph / item_ink calls with a type >= IT_COUNT (expect 0)
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
END_SHOWN       EQU $BF9D           ; end flow (main.asm end_screen, END-WAIT): bit 7 ES_CARD = the card is drawn; low nibble = quiet countdown (END_DELAY reload, 0 = wait for a key)
END_DELAY       EQU $0F             ; ticks of key-free quiet (before the card, and again before a key leaves the card)
ES_CARD         EQU $80
PEND_N          EQU $BF9F           ; B19: PENDING bodies of CUR_ROOM at the last build_live (pend_hit); an upper bound. RULE (3F-B4): whatever sets PENDING in CUR_ROOM before the monster phase (ALARM wave, summon, respawn) must call build_live
MENU_IN_SIG     EQU $BF9E           ; C3-6 review: last input fold seen by menu_frame           ; C3-6: 1 = the death / win card is drawn
LVL_SH          EQU $BFCA           ; C3-3: hero level digit last drawn ($FF = never)
LOCK_SHOWN      EQU $BFC6           ; B3B-5: 1 = the locked-door message was printed for the key
                                    ;   still held (read_turn_input clears it on release)
JUMP_TURN       EQU $BFC4           ; B3B-5 word: TURN_COUNTER value on which a jump is refused (the turn
                                    ;   right after a jump: "not two turns in a row", game.md §2.4); $FFFF = none

; Game states (GAME_STATE). 2/3/4 shared with constants.asm.
GS_SELECT       EQU $05
GS_TRANSITION   EQU $06
GS_LEVEL        EQU $07             ; 3F-T1: level_enter before the room map exists (card,
                                    ;   level_new, the level pool): gen_frame allowed (GEN_TRAP off)
GS_ANYKEY       EQU $08             ; INSTR-BUILD: instr_main (was boot6_wait): the loading picture waits for a key
GS_HELP1        EQU $09             ; INSTR-BUILD: HOW TO PLAY page 1 up (instr_main; boot only, before the menu)
GS_HELP2        EQU $0A             ; INSTR-BUILD: HOW TO PLAY page 2 up
GS_HELP3        EQU $0B             ; INSTR-P3: HOW TO PLAY page 3 (TREASURES) up (menu_run replaces it)

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
EX_TELE         EQU 6               ; 3E-T12: the Teleport scroll (fx6.asm; T16: the trap): do_exit's
                                    ; tele branch, tele_pick rewrites it to EX_UP / EX_DOWN

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
E_POT           EQU 8               ; player: potions in BAG (3E-T11: written only by pot_sync)
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
E_HIT           EQU 22              ; IMPACT: LOG-DMG: the HP the blow took (0 = none: no flash; < 128, a body's
                                    ;   hp); bit 7 set = a ranged shot's (rg_shoot $80 | L): no flash at the IMPACT
E_GOLD          EQU 23              ; 3F-T5: LEK_GOLD ($20) on a golden boss, else 0 (set by lp_spawn, banked back by lp_bank;
                                    ; D3-0: was E_ZAP, the PROTO wizard zap). Other readers: the T8 glow / atk / DEF flag
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
RC_PARRY        EQU 5               ; 3F-T13bc: the Death Knight parried: no sequence (the rest pose),
                                    ; the ATTR_PARRY flash at E_REACTAT (anim .dodge; was RC_BLOCK + dk_block)
                ASSERT RC_PARRY == RC_DODGE + 1 && RC_DEATH < RC_DODGE && RC_BLOCK < RC_DODGE

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
MSG_P_PARRY     EQU 15              ; 3F-T6: the hero's blow was parried: "THE <target> PARRIES!" (the target's name,
                                    ; like MSG_P_HIT..KILL; do_attack / melee_strike set it, show_impact_msg / impact_line)
MSG_M_SUMMON    EQU 16              ; 3F-T9: "THE <kind> SUMMONS!" (spawn6.asm sp_summon: the caster's IMPACT line)
; (MSG_M_DRAIN 17 retired by LOG-DMG: log0.asm ln_imp recomposes the Vampire's MSG_M_HIT as
; "THE VAMPIRE DRAINS YOU -D"; its bite heals it, game.md §9.1)

;------------------------------------------------------------------------------
; Kinds (prototype §2/§6.3). Parallel byte tables, page-aligned (kind_tab).
;------------------------------------------------------------------------------
K_KNIGHT        EQU 0
K_WIZARD        EQU 1
                                ; id 2 retired (Rogue removed, G1 budget 2): hole kept so
                                ; K_* ids / HERO_KIND semantics stay stable
K_VBAT          EQU 2           ; 3F-T9: the hole's row = the Vampire's BAT FORM (game.md §9.2;
                                ; vbat6.asm): never in LP_KINDS / spawned, an entity gets it only
                                ; by transforming (and a banked bat comes back as one). Bat body /
                                ; flags / 1d2 bite, the Vampire's hp row, resistances, KXP, weight,
                                ; name and ink; frames = the Bat's first VB_FCNT (pool6.asm gu_tab)
K_SKELETON      EQU 3
K_GOBLIN        EQU 4
K_GHOST         EQU 5
K_RAT           EQU 6
K_BAT           EQU 7
K_SLIME         EQU 8
; 3F-T3: the real 3F rows (game.md §9.1 roster, §9.6 tiers): 18 base ids (2 heroes,
; the id-2 hole, 15 monsters / bosses) + 12 tier rows = 30; a golden boss is a per-entity
; flag on its base row (§9.7 R1), never a row. tools/levelgen.py KROWS carries the SAME ids
; (levelgen.py asserts them against this file). 3F-T13: the new kinds draw the real 3F-A1
; frames (frames.asm; units / sharing: pool6.asm gu_tab / pool_gmap, seq_img.asm ksm_tab).
K_SPIDER        EQU 9
K_VAMPIRE       EQU 10
K_ORC           EQU 11
K_ARCHER        EQU 12              ; Skeleton Archer
K_MUMMY         EQU 13
K_NECRO         EQU 14              ; Necromancer
K_OGRE          EQU 15              ; unique boss D4
K_DKNIGHT       EQU 16              ; unique boss D7
K_ARCHMAGE      EQU 17              ; unique boss D8
; tier rows, §9.6 table order (tier 2 / tier 3 of their base kind)
K_GIANT_RAT     EQU 18
K_RABBIT_RAT    EQU 19
K_SCREECH       EQU 20              ; Screech Bat
K_SLINGER       EQU 21              ; Goblin Slinger
K_BLACK_WIDOW   EQU 22
K_SKEL_GUARD    EQU 23
K_SKEL_KNIGHT   EQU 24
K_POLTERGEIST   EQU 25
K_ORC_BERSERK   EQU 26
K_ORC_BOUNCER   EQU 27
K_SNIPER        EQU 28              ; Skeleton Sniper
K_BONE_CALLER   EQU 29
K_COUNT         EQU 30
K_BOSS_D1       EQU K_GOBLIN        ; Golden Goblin King (golden = flag, T8)
K_BOSS_D2       EQU K_SPIDER        ; Golden Spider Queen
K_BOSS_D3       EQU K_VAMPIRE       ; Golden Vampire Lord
K_BOSS_D4       EQU K_OGRE          ; Ogre Warlord
K_BOSS_D5       EQU K_MUMMY         ; Golden Pharaoh
K_BOSS_D6       EQU K_NECRO         ; Golden High Necromancer
K_BOSS_D7       EQU K_DKNIGHT       ; Death Knight
K_BOSS_D8       EQU K_ARCHMAGE      ; Archmage
; §9.3 encounter weights (game.md §9.1 W column): lp_wt (bank 3) per kind row; a tier
; keeps its base kind's weight except the Slinger (3 + 1, §9.6)
WT_K_KNIGHT     EQU 0
WT_K_WIZARD     EQU 0
WT_K_SKELETON   EQU 5
WT_K_GOBLIN     EQU 3
WT_K_GHOST      EQU 3
WT_K_RAT        EQU 2
WT_K_BAT        EQU 2
WT_K_SLIME      EQU 2
WT_K_SPIDER     EQU 2
WT_K_VAMPIRE    EQU 5
WT_K_ORC        EQU 5
WT_K_ARCHER     EQU 6
WT_K_MUMMY      EQU 5
WT_K_NECRO      EQU 6
WT_K_OGRE       EQU 6
WT_K_DKNIGHT    EQU 5
WT_K_ARCHMAGE   EQU 6
WT_K_GIANT_RAT  EQU WT_K_RAT
WT_K_RABBIT_RAT EQU WT_K_RAT
WT_K_SCREECH    EQU WT_K_BAT
WT_K_SLINGER    EQU WT_K_GOBLIN + 1
WT_K_BLACK_WIDOW EQU WT_K_SPIDER
WT_K_SKEL_GUARD EQU WT_K_SKELETON
WT_K_SKEL_KNIGHT EQU WT_K_SKELETON
WT_K_POLTERGEIST EQU WT_K_GHOST
WT_K_ORC_BERSERK EQU WT_K_ORC
WT_K_ORC_BOUNCER EQU WT_K_ORC
WT_K_SNIPER     EQU WT_K_ARCHER
WT_K_BONE_CALLER EQU WT_K_NECRO
    MACRO LP_WT_ROWS                           ; emitted once, in kind_tab's KT_REACH slot (main.asm)
                DB   WT_K_KNIGHT, WT_K_WIZARD, WT_K_VAMPIRE, WT_K_SKELETON, WT_K_GOBLIN   ; 3F-T9: id 2 = K_VBAT keeps the Vampire's weight
                DB   WT_K_GHOST, WT_K_RAT, WT_K_BAT, WT_K_SLIME
                DB   WT_K_SPIDER, WT_K_VAMPIRE, WT_K_ORC, WT_K_ARCHER, WT_K_MUMMY
                DB   WT_K_NECRO, WT_K_OGRE, WT_K_DKNIGHT, WT_K_ARCHMAGE
                DB   WT_K_GIANT_RAT, WT_K_RABBIT_RAT, WT_K_SCREECH, WT_K_SLINGER
                DB   WT_K_BLACK_WIDOW, WT_K_SKEL_GUARD, WT_K_SKEL_KNIGHT, WT_K_POLTERGEIST
                DB   WT_K_ORC_BERSERK, WT_K_ORC_BOUNCER, WT_K_SNIPER, WT_K_BONE_CALLER
    ENDM
K_MAX           EQU 32              ; A6: kind_tab capacity (game.md §11.2: 30 used, ids 30 / 31 = the class FX kinds)
; D3-4: the class FX kinds (render-only projectile / impact frames, game.md §6;
; never an entity's kind): the LAST two kind ids, so 3F's monster rows grow
; up from K_COUNT without moving them (3F-T3: the monster rows now fill 0..29). Generated
; with the hero only (start_game: R6 pool_hero -> unit HERO_KIND + K_FX_BASE), so the
; pool holds the current class's FX only. Their fid ranges OVERLAP in
; frames.asm (spark_fizz1/2: Spark impact and Whirlwind impact): K_FXM =
; [mage-only | shared], K_FXW = [shared | warrior-only].
K_FXW           EQU K_MAX - 2       ; Warrior FX (= K_FX_BASE + K_KNIGHT)
K_FXM           EQU K_MAX - 1       ; Mage FX    (= K_FX_BASE + K_WIZARD)
K_FX_BASE       EQU K_FXW - K_KNIGHT
                ASSERT K_FXM == K_FX_BASE + K_WIZARD && K_FXW >= K_COUNT
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
; 3F-T13: the real 3F bodies (game.md §9.1): Spider 32x16, Ogre 32x48 (KT_BW 4), the rest 24x48;
; the tiers / shared rows use their base's (main.asm KROW KT_BH)
BH_K_SPIDER     EQU 2
BH_K_VAMPIRE    EQU 6
BH_K_ORC        EQU 6
BH_K_ARCHER     EQU 6
BH_K_MUMMY      EQU 6
BH_K_NECRO      EQU 6
BH_K_OGRE       EQU 6
BH_K_DKNIGHT    EQU 6
BH_K_ARCHMAGE   EQU 6
                                    ; 3F-T13 frame groups with no kind (frames.asm FRM ASSERT only;
                                    ; CORPSE-ASHES: G_DEADH retired, every DEAD but Bat / Slime / Ghost
                                    ; and the heroes is small_corpse):
BH_G_CLIMBH     EQU 6               ; 3F-T13bc: the shared humanoid climb pair (24x48)
BH_G_NBOLT      EQU 2               ; the Necro bolt (<= 16 px)
BH_K_FXW       EQU 2               ; D3-4: FX frames are <= 16 px tall (FRM ASSERT only)
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
KT_REACH        EQU $0E0            ; MEM-RECLAIM w3: now the lp_wt weights (the old all-1 reach column is gone)
                                    ; RECLAIM-C (b): the KT_PERIOD column ($100, all 1 but three 2s) is gone:
                                    ; "acts every 2 turns" is KF_SLOW in KT_FLAGS (bank 2 +32 B)
KT_FLAGS        EQU $100            ;                            (page 1)
KT_ATTR         EQU $120
                                    ; RECLAIM-C (b): DIV9 / MOD9 / SEQ (was SEQ $160, MOD9 $180, DIV9 $1A0)
                                    ; reordered so the 32 B come off the END: turn3's DIV9 -> MOD9 row step
                                    ; is `set 5, l` (was `res 5, l`), and KT_SEQ (a K_MAX array) sits
                                    ; right after MOD9's 24 B — off the $20 grid, still inside page 1 (KFIELD's
                                    ; 8-bit add never carries: $78 + 31 < $100)
KT_DIV9         EQU $140            ; 24 B: n div STOREY_ROWS      (same page as KT_MOD9: feet_mod) + 8 B spare
KT_MOD9         EQU $160            ; 24 B: n mod STOREY_ROWS (9)  (n = y+h or a row, 0..23)
KT_SEQ          EQU $178            ; 3F-T2: RUNTIME, the low byte of the kind's SEQ_ROWS row
                                    ; (lowram.asm (sq_load / sq_fill) writes it per level; tiers share their base's)
                                    ; (was KT_FID0 / KT_FCNT: generator-only, now R6 gu_tab)
KT_END          EQU $198            ; RECLAIM-C (b): was $1B8; D3-8d: mark.asm code follows from here (3F-T2: was $1D0)
KT_SIZE         EQU $200

; KT_FLAGS bits
KF_FLYER        EQU %00000001
KF_CLIMBER      EQU %00000010
KF_TALL         EQU %00000100
KF_HERO         EQU %00001000
KF_BAT          EQU %00010000       ; bat jitter / wander
KF_SLOW         EQU %00100000       ; RECLAIM-C (b): acts every 2 turns (rests on odd TURN_COUNTER) — the old KT_PERIOD 2
                                    ; (Slime, Vampire, Mummy); D3-0..RECLAIM-C spare (was KF_ZAP, the PROTO wizard zap)
KF_SLOW_BIT     EQU 5
KF_OPENER       EQU %01000000       ; B3B-5: opens closed unlocked doors by bumping (game.md §9.1)

;------------------------------------------------------------------------------
; Frame table (static, frame_tab) — MEM-FT: the 4-B entry lives in the fid's
; FRT row (bytes FT_IN_ROW..FT_IN_ROW+3, the row's spare tail), so
; frame_tab = FRT + FT_IN_ROW and FT_STRIDE = FRT_STRIDE (16). Not in the
; bank-2 image: instr_ovl in_ft unpacks ftz_zx0 (bank 0 POOL_START, boot only; RECLAIM-D) (contiguous 4 B/fid) and spreads
; it into the rows at boot; frt_none / gen_frame write bytes 0..11 only.
; A6: only what the per-tick renderer reads (blit, footprint, frame offsets);
; the generator-only part is the bank-5 descriptor (FD_*).
;------------------------------------------------------------------------------
FT_COLS         EQU 0               ; data byte-columns (W/8)
FT_H            EQU 1               ; rows (px)
FT_OFFR         EQU 2               ; signed: frame_px = body_px + off (right)
FT_OFFL         EQU 3               ; signed: (left-facing)
FT_LEN          EQU 4               ; bytes per entry (the packed stream: contiguous)
FT_IN_ROW       EQU 4 * 3           ; after the 4 variants (bank, lo, hi)
FT_STRIDE       EQU FRT_STRIDE
frame_tab       EQU FRT + FT_IN_ROW
                ASSERT FT_IN_ROW + FT_LEN == FRT_STRIDE

; FT_HL_A — HL = frame_tab + A * FT_STRIDE + ofs (A = fid). FRT page-aligned:
; fid*16 by nibble swap, 60 T / 16 B, keeps DE / BC (4 x add hl,hl: 76 T).
; Clobbers: A, HL.
    MACRO FT_HL_A ofs
                rrca
                rrca
                rrca
                rrca
                ld   l, a
                and  $0F
                add  a, FRT >> 8
                ld   h, a
                ld   a, l
                and  $F0
                or   FT_IN_ROW + (ofs)
                ld   l, a
    ENDM

;------------------------------------------------------------------------------
; Frame descriptor (A6; bank 5 low RAM, fdesc_tab at the end of the cold block,
; read only by gen_frame) — 5 B/fid:
;   FD_BLK   word: VIRTUAL address of the frame's packed block
;                  ($8000.. bank 1 / $C000.. bank 3 / SRC6: $4000..$7FFF =
;                  bank 6 at +SRC6_VDELTA; also the GEN_ZBLK cache key)
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
FF_PH4          EQU %00000100       ; PHASE_SHIFT: STATIONARY frame drawn at px & 4 = 4 (a
                                    ; parity-locked walk frame): its one shift = (anchor + 4) & 4
                ASSERT FF_PH4 == 4                  ; gen_facing / POOLACC add the flag as the 4 px

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
; 3F-T2 per-level sequence cache (docs/memory-map.md "Sequence cache (3F-T2)").
; The masters (every kind's sequences) are a ZX0 stream in R6 (pool6.asm);
; R6 copies the hero's block into slot 0 at a game start and the level's
; monster blocks into slots 1.. at each level entry, then writes kind_tab
; KT_SEQ (the row's low byte) for every kind. Rows: SEQ_ROWS (bank 2, one
; page), KS_STRIDE each; the sequence bytes they point to: SEQ_BYTES.
SQ_SLOTS        EQU 7               ; hero + <= 6 monster blocks (PROTO: all 6 original kinds)
SQ_ROWS_LEN     EQU SQ_SLOTS * KS_STRIDE
SEQB_LEN        EQU 256             ; SEQ_BYTES: >= hero + the level's blocks (ASSERTed per depth). 3F-T13bc: 256 -> 288;
                                    ; D3-11 review: back to 256 (+32 B bank 2): the need is 253 (the PROTO
                                    ; fixture's 6 kinds; the worst real level D8 245), ASSERTed below seq_rows
; master block (the unpacked image at SQ_IMG): KSM_LEN (sequence bytes n),
; KSM_IMP (= KS_IMPACT), KSM_OFF + 8 offsets (KS_IDLE..KS_DEATH order) from
; KSM_SEQ, then the n sequence bytes (position-independent: no pointer inside)
KSM_LEN         EQU 0
KSM_IMP         EQU 1
KSM_OFF         EQU 2
KSM_SEQ         EQU 10

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
; (B3B-13: the PROTO chest stand-in T_CHEST_* (per-level ids 32..35) and the
; zap tile ids T_ZAP1/2 (now T_DRIP1/2) are gone; D3-0: the zap itself too.)
; (DEC2's free common ids 13 / 15 / 16: 3F-T8 T_GRATE_SHUT / the lectern, level_defs.asm; 31 stays free)
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
MAX_POTIONS     EQU 9               ; (3E-T11: no engine user; the bag caps potions)
QUAFF_HEAL      EQU 12              ; game.md §8: Heal +12 HP (MORE-MON knob 2026-11-04; was 10, 3E-T11 8)
FOLLOW_GAP      EQU 4
FOLLOW_MAX      EQU 2
ROOM_CAP        EQU 4               ; monsters per room (on-screen cap)
TALL_CAP        EQU 2
FLASH_TICKS     EQU 2
PARRY_FLASH     EQU 3               ; 3F-T13bc: the Death Knight parry flash (3 ticks of ATTR_PARRY, as MISS_FLASH: the hero overlaps the DK's columns; review 2026-10-29)
ATTR_PARRY      EQU $46             ; bright yellow (= ATTR_MISS): visible on the DK's $47 body
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

; KFL off — RECLAIM-B: KFIELD as a call to the low-RAM `kfl` (6 B per site vs 9,
; +27 T): only for COLD sites (spawn / level / room-exit / one-off lookups). Same
; result and clobbers as KFIELD (A, HL = kind_tab + off + kind, F from the add).
; Hot sites (the AI pass, hit_roll, anim / logic / mark, render) keep KFIELD.
    MACRO KFL off
                ld   hl, kind_tab + (off)
                call kfl
    ENDM

;------------------------------------------------------------------------------
; FRM name, kind, body_w_px, flags — one frame of the frame list (src/frames.asm).
; The list is INCLUDEd twice (A6):
;   FRM_EMIT = FRM_DESC  lowram.asm fdesc_tab (bank 5): the generator's 5-B
;                        descriptor FD_BLK, FD_FRM, FD_FLAGS (defs.asm FD_*)
;   FRM_EMIT = FRM_HOT   data.asm: the FRT row image (MEM-FT: 12 x FRT_NONE + the
;                        renderer's 4-B frame_tab entry FT_COLS, FT_H, FT_OFFR,
;                        FT_OFFL; assembled at FRT, not on tape); defines FID_<name> and
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
FFL_nm EQU (flg)                               ; the FF_* flags (data.asm MOVECYC checks)
FCTR = FCTR + 1
        ; bottom-anchored frames must fit the body rows and be whole cells
        ; (fpy = py + bh*8 - H stays inside the body, row fix-up every 8 lines)
        ASSERT (nm_h <= BH_kind * 8) && ((nm_h & 7) == 0)
        DS   FT_IN_ROW, FRT_NONE                ; MEM-FT: the FRT row's variants (none yet)
        DB   nm_cols, nm_h, low(0 - nm_ax), low(0 - (nm_w - nm_ax - bwpx))
        IF (flg) & FF_MOTION
          IF (flg) & FF_SYM
POOLACC = POOLACC + nm_h * 2 * (2 * nm_cols + 1)
          ELSE
POOLACC = POOLACC + 2 * nm_h * 2 * (2 * nm_cols + 1)
          ENDIF
        ELSE
POOLACC = POOLACC + nm_h * 2 * (nm_cols + ((((nm_ax + ((flg) & FF_PH4)) & 7) != 0) & 1))
          IF ((flg) & FF_SYM) == 0
POOLACC = POOLACC + nm_h * 2 * (nm_cols + ((((nm_w - nm_ax - bwpx + ((flg) & FF_PH4)) & 7) != 0) & 1))
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
; PHASE_SHIFT walk-cycle flags (frames.asm): a walker's KS_MOVE frame at phase p
; is drawn only at px & 4 = (p even ? 4 : 0) (anim_entity .walkph locks it), so
; WK4 (WALK1/3) = one shift, the px & 4 = 4 one; WK0 (WALK2/4) = the aligned one.
; A walk frame also drawn at rest / climb / attack at the other parity stays MOT.
; Rule (docs/conventions.md "Walk cycles"): move cycles via MOVECYC2/4 only (1
; tick per entry, even length; even slots MOT or WK4, odd slots MOT or WK0 —
; ASSERTed there); every other use draws at px & 4 = 0 (cell-aligned), so a
; WK4 frame must appear in no other seq / role / cycle (tests/frames_phase.py).
    IF PHASE_SHIFT
WK4             EQU FF_PH4
WK0             EQU STA
    ELSE
WK4             EQU MOT
WK0             EQU MOT
    ENDIF

;------------------------------------------------------------------------------
; Stage 3B data contracts (B3B-1): EQUs + ASSERTs only, no bytes.
;------------------------------------------------------------------------------
                INCLUDE "level_defs.asm"
                INCLUDE "hero_defs.asm"         ; C3-0: Stage 3C contracts (HERO_ST, JOY_MIRROR, KEYTAB)
                INCLUDE "combat_defs.asm"       ; D3-0: Stage 3D state homes + layouts (ST_*, FXREC, KX, ...)
                INCLUDE "item_defs.asm"         ; 3E-T3: item types / record / ITEM_RAM / trap list
; B3B-13: message string ids TX_* / decoded lengths TXL_* (+ ASSERT <= LOG_MAX),
; generated from src/strings.txt by tools/textpack.py (tools/build.sh)
                INCLUDE "../build/text/strings_ids.inc"
; 3F-T3: the longest kind name (the composed log lines are sized with it; every name is
; ASSERTed <= NM_LONG in lowram.asm)
NM_LONG         EQU TXL_NM_GIANT_RAT

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
