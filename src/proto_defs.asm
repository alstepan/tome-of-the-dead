;==============================================================================
; proto_defs.asm — PROTO-only constants (docs/design/prototype.md rev B).
;
; Shared screen/port/keyboard/GS/RNG/state-block constants come from
; constants.asm (INCLUDEd first by proto.asm). Everything PROTO adds lives here
; so main.asm / spike_sideview.asm assemble byte-identically. Every fixed
; address below is recorded in docs/memory-map.md ("PROTO" section).
;==============================================================================

;------------------------------------------------------------------------------
; ROM / system variables (48K BASIC ROM = 128K ROM 1, paged via $7FFD bit 4)
;------------------------------------------------------------------------------
IY_SYSVAR       EQU $5C3A           ; conventions: IY stays here (ROM IM1 ISR)
SYS_FRAMES      EQU $5C78           ; ROM ISR 50 Hz frame counter (low byte used)
ROM_CHARSET     EQU $3D00           ; 48K ROM font, char 32 first, 8 B/char
ROM_LD_BYTES    EQU $0556           ; ROM tape loader (IX=dst, DE=len, A=flag, CF=1)

;------------------------------------------------------------------------------
; 128K paging. $7FFD is write-only: always write through PORT_7FFD_SHADOW.
;   bit 4 = 1 -> 48K BASIC ROM (IM1 ISR + charset + LD-BYTES live there)
;   bit 3 = 0 -> display normal screen (bank 5)
;------------------------------------------------------------------------------
P7FFD_ROM48     EQU %00010000
BANK_SRC_LO     EQU 1               ; sprite SOURCES, virtual $8000-$BFFF (contended)
BANK_SRC_HI     EQU 3               ; sprite SOURCES, virtual $C000-$FFFF (contended)
BANK_POOL0      EQU 0               ; pre-shift pool (uncontended), boot-generated
BANK_POOL1      EQU 4
BANK_POOL2      EQU 6
BANK_SHADOW     EQU 7               ; clean-background shadow (R-1 erase lever)
SHADOW_BITMAP   EQU $C000           ; bank 7: room tiles in screen layout (rows 0..20)
SHADOW_ATTR     EQU $D800           ; bank 7: room tile attrs in screen layout
BANK_WINDOW     EQU $C000
FT_BLOCKER      EQU $FE             ; find_target: nearest body is mid-ladder (not a slot)
PAGING_PROBE    EQU $A5             ; check_paging: bank-1 marker (bank 0 gets ~)
SRC_VIRT_BASE   EQU $8000           ; sources are assembled at virtual $8000..$FFFF

;------------------------------------------------------------------------------
; Low-RAM buffers (bank 5, $6000-$7FFF; free after the loader's CLEAR 24575).
; Contended, but only touched off the blit's inner loop (1 read/erased cell).
;------------------------------------------------------------------------------
ROOM_MAP        EQU $6000           ; 672 B: current room tile ids, 32x21 row-major
NEXT_MAP        EQU $6300           ; 672 B: destination room during a transition
BITREV_TAB      EQU $6600           ; 256 B: bit-reversed byte (page-aligned)
GEN_SRC         EQU $6700           ; 512 B: source frame copied out of its bank
GEN_MIR         EQU $6900           ; 512 B: mirrored copy (left-facing)
TILE_GLYPHS     EQU $6B00           ; 256 B: 32 tiles x 8 B (page-aligned)
TILE_ATTRS      EQU $6C00           ; 32 B : attr per tile id (page-aligned)
LOWRAM_END      EQU $6C20

ROOM_COLS       EQU 32
ROOM_ROWS       EQU 21
ROOM_CELLS      EQU ROOM_COLS * ROOM_ROWS   ; 672
HUD_ROW         EQU 21              ; rows 21..23 = HUD (never scrolled/stamped)

;------------------------------------------------------------------------------
; Bank-2 runtime storage. The image must end below ENTITIES (ASSERTed).
;------------------------------------------------------------------------------
P_ENTITIES      EQU $B000           ; 16 slots x 32 B = 512 B ($B000..$B1FF)
P_ENT_STRIDE    EQU 32
P_MAX_ENT       EQU 16
FRT             EQU $B200           ; frame runtime table: 16 B/fid, <=96 fids
FRT_STRIDE      EQU 16
FRT_MAX         EQU 96              ; $B200..$B7FF
SLOTVARS        EQU $B800           ; per-slot render scratch, 16 B per array
N_VIS           EQU SLOTVARS + $00  ; desired: 0 hidden / 1 visible
N_FID           EQU SLOTVARS + $10  ; desired frame id
N_FPX           EQU SLOTVARS + $20  ; desired frame px (top-left)
N_FPY           EQU SLOTVARS + $30  ; desired frame py (top-left)
N_ATTR          EQU SLOTVARS + $40  ; desired attr
N_DIRTY         EQU SLOTVARS + $50  ; DIRTY_* class this tick
N_COL           EQU SLOTVARS + $60  ; desired footprint
N_ROW           EQU SLOTVARS + $70
N_COLS          EQU SLOTVARS + $80
N_ROWS          EQU SLOTVARS + $90
D_ATTR          EQU SLOTVARS + $A0  ; attr last stamped
N_LEFT          EQU SLOTVARS + $B0  ; desired facing (0/EF_LEFT)
N_LOG           EQU SLOTVARS + $C0  ; 1 = log this draw in ANIM_TRACE
DMG_LIST        EQU $B900           ; damage rects: 4 B each (col,row,cols,rows)
DMG_MAX         EQU 48              ; $B900..$B9BF
PEND_DMG        EQU $B9C0           ; queued damage for next render: 4 rects ($B9C0..$B9CF)
PEND_DMG_MAX    EQU 4
LIVE_LIST       EQU $BA00           ; 16 x 5 B: colliders this turn ($BA00..$BA4F)
LIVE_N          EQU $BA50           ; entries in LIVE_LIST
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
SEL_FRT_SAVE    EQU $BA80           ; 3 x FRT_STRIDE: boot FRT rows of the select idles ($BA80..$BAAF)
MSG_Q           EQU $BA78           ; queued impact message: attacker slot + 1 (0 = none)
STACK_BOTTOM    EQU $BB00           ; stack grows down from $BF00 to here

;------------------------------------------------------------------------------
; State block $BF00.. (above initial SP). $BF00-$BF0D shared with main.asm:
; GAME_STATE, RNG_STATE, TURN_COUNTER, INPUT_SRC, KBD_MATRIX (constants.asm).
;------------------------------------------------------------------------------
TURN_PHASE      EQU $BF10           ; 0 = INPUT, 1 = ANIM          (test-observable)
TICK_COUNTER    EQU $BF11           ; word: 25 Hz ticks elapsed    (test-observable)
CUR_ROOM        EQU $BF13           ; 0..3 = A..D                  (test-observable)
HERO_KIND       EQU $BF14           ; K_KNIGHT/K_WIZARD/K_ROGUE    (test-observable)
POTIONS_TAKEN   EQU $BF15           ; bitmask of level potion ids  (test-observable)
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
ZAP_T           EQU $BF48           ; zap overlay ticks left
ZAP_ROW         EQU $BF49
ZAP_COL         EQU $BF4A
ZAP_LEN         EQU $BF4B
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
MSG_BUF         EQU $BFA0           ; 32 B message line composition
TIMING_MARK     EQU $BFC0           ; spare

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
E_ZAP           EQU 23              ; IMPACT: zap gap cells (wizard)
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

; E_MODE
M_REST          EQU 0
M_MOVE          EQU 1
M_SEQ           EQU 2
M_HOLD          EQU 3               ; player dead: hold the final frame

; E_REACT
RC_NONE         EQU 0
RC_HURT         EQU 1
RC_BLOCK        EQU 2
RC_DEATH        EQU 3

; N_DIRTY classes
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

;------------------------------------------------------------------------------
; Kinds (prototype §2/§6.3). Parallel byte tables, page-aligned (kind_tab).
;------------------------------------------------------------------------------
K_KNIGHT        EQU 0
K_WIZARD        EQU 1
K_ROGUE         EQU 2
K_SKELETON      EQU 3
K_GOBLIN        EQU 4
K_GHOST         EQU 5
K_RAT           EQU 6
K_BAT           EQU 7
K_SLIME         EQU 8
K_COUNT         EQU 9
; body height in cells per kind (single source: kind_tab KT_BH row and the FRM
; frame-height ASSERT both use these; named BH_<kind> so FRM can paste `kind`)
BH_K_KNIGHT     EQU 6
BH_K_WIZARD     EQU 6
BH_K_ROGUE      EQU 6
BH_K_SKELETON   EQU 6
BH_K_GOBLIN     EQU 4
BH_K_GHOST      EQU 4
BH_K_RAT        EQU 2
BH_K_BAT        EQU 2
BH_K_SLIME      EQU 2

; offsets of the parallel arrays inside the 256-B kind_tab page (16 B each)
KT_BW           EQU $00             ; body width, cells
KT_BH           EQU $10             ; body height, cells
KT_HP           EQU $20
KT_ATK          EQU $30
KT_EVA          EQU $40
KT_DIE          EQU $50
KT_BONUS        EQU $60
KT_REACH        EQU $70
KT_PERIOD       EQU $80
KT_FLAGS        EQU $90
KT_ATTR         EQU $A0
KT_FID0         EQU $B0             ; first frame id of the kind
KT_FCNT         EQU $C0             ; frame count of the kind
KT_MOD7         EQU $D0             ; 24 B: n mod 7   (n = y+h, 0..23)
KT_DIV7         EQU $E8             ; 24 B: n div 7

; KT_FLAGS bits
KF_FLYER        EQU %00000001
KF_CLIMBER      EQU %00000010
KF_TALL         EQU %00000100
KF_HERO         EQU %00001000
KF_BAT          EQU %00010000       ; bat jitter / wander
KF_ZAP          EQU %00100000       ; wizard zap overlay on impact

;------------------------------------------------------------------------------
; Frame table (static, in image) — 8 B/fid.
;------------------------------------------------------------------------------
FT_SRC          EQU 0               ; word: virtual source address (banks 1/3)
FT_COLS         EQU 2               ; data byte-columns (W/8)
FT_H            EQU 3               ; rows (px)
FT_OFFR         EQU 4               ; signed: frame_px = body_px + off (right)
FT_OFFL         EQU 5               ; signed: (left-facing)
FT_FLAGS        EQU 6               ; FF_*
FT_KIND         EQU 7
FT_STRIDE       EQU 8

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
T_CHEST_TL      EQU 11
T_CHEST_TR      EQU 12
T_CHEST_BL      EQU 13
T_CHEST_BR      EQU 14
T_TORCH_T       EQU 15
T_TORCH_B       EQU 16
T_ZAP1          EQU 17              ; overlay only (never in a room map)
T_ZAP2          EQU 18
T_END_L         EQU 19              ; PLATFORM_END_L: floor cell right of a hole
T_END_R         EQU 20              ; PLATFORM_END_R: floor cell left of a hole
T_COUNT         EQU 21

; attrs (prototype §4.1)
ATTR_AIR        EQU $00
ATTR_WALL       EQU $01
ATTR_FLOOR      EQU $0F
ATTR_LADDER     EQU $02
ATTR_POTION     EQU $42
ATTR_CHEST      EQU $06
ATTR_TORCH      EQU $46
ATTR_HIT        EQU $42
ATTR_HEAL       EQU $44
ATTR_ZAP        EQU $45
ATTR_HUD        EQU $47             ; bright white on black (rows 21..23)
ATTR_HUD_DIM    EQU $07

; room geometry
STOREYS         EQU 3
STOREY_H        EQU 7
MAX_POTIONS     EQU 9
QUAFF_HEAL      EQU 8
FOLLOW_GAP      EQU 4
FOLLOW_MAX      EQU 2
ROOM_CAP        EQU 4               ; monsters per room (on-screen cap)
TALL_CAP        EQU 2
ZAP_ROW_OFF     EQU 2               ; wizard staff row, body-relative (cast2 orb)
ZAP_TICKS       EQU 3
FLASH_TICKS     EQU 2
EXIT_NONE       EQU $FF
TICK_FRAMES     EQU 2               ; 25 Hz
TWEEN_STEP      EQU 4               ; px per tick

; KFIELD off — A = kind_tab[kind(IX) + off].  Clobbers: A, HL   (~45 T)
    MACRO KFIELD off
                ld   a, (ix+E_KIND)
                add  a, off
                ld   l, a
                ld   h, kind_tab >> 8
                ld   a, (hl)
    ENDM
