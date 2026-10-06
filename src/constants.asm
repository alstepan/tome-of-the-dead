;==============================================================================
; constants.asm — named ROM routines, ports, and fixed addresses.
;
; No magic numbers anywhere in code. Every fixed address used by the engine is
; declared here and recorded in docs/memory-map.md. Keep the two in sync.
;==============================================================================

;------------------------------------------------------------------------------
; Screen memory (bank 5, fixed window)
;------------------------------------------------------------------------------
SCREEN_BITMAP       EQU $4000           ; 6144 bytes, 256x192 1-bit pixels
SCREEN_BITMAP_LEN   EQU 6144
SCREEN_ATTR         EQU $5800           ; 768 bytes, 32x24 attribute cells
SCREEN_ATTR_LEN     EQU 768
SCREEN_FRAME_LEN    EQU 6912            ; bitmap + attributes (golden-screen unit)

;------------------------------------------------------------------------------
; I/O ports
;------------------------------------------------------------------------------
PORT_BORDER         EQU $FE             ; ULA: bits 0-2 = border colour
PORT_7FFD           EQU $7FFD           ; 128K paging (write-only)

;------------------------------------------------------------------------------
; Attribute colour bits (for building an attribute byte)
;   attr = FLASH(bit7) | BRIGHT(bit6) | PAPER(bits5-3) | INK(bits2-0)
;------------------------------------------------------------------------------
COL_BLACK           EQU 0
COL_BLUE            EQU 1
COL_RED             EQU 2
COL_MAGENTA         EQU 3
COL_GREEN           EQU 4
COL_CYAN            EQU 5
COL_YELLOW          EQU 6
COL_WHITE           EQU 7

ATTR_BRIGHT         EQU %01000000       ; bit 6
ATTR_FLASH          EQU %10000000       ; bit 7
PAPER_SHIFT         EQU 3               ; paper occupies bits 5-3

; The P2 skeleton deliberately does NOT call ROM CLS / RST 16 print: from a bare
; snapshot entered at $8000 the ROM print channels / system vars are not set up,
; so those paths silently no-op. The engine (P3+) owns its own glyph blitter
; anyway (design §1), so the skeleton renders via direct screen writes only.

GLYPH_BYTES         EQU 8               ; one 8x8 glyph = 8 bitmap rows

;==============================================================================
; P3 — core loop (input -> turn -> render). Design refs in comments.
;==============================================================================

;------------------------------------------------------------------------------
; Map (design §4.2/§4.4) — 30x21 row-major byte array, one tile/cell.
;------------------------------------------------------------------------------
MAP_W               EQU 30              ; viewport width  (design §4.4)
MAP_H               EQU 21              ; viewport height (design §4.4)
MAP_CELLS           EQU MAP_W * MAP_H   ; 630 bytes

; Terrain encoding (design §4.2). Walkable = terrain != T_WALL.
T_WALL              EQU 0
T_FLOOR             EQU 1
T_CORR              EQU 2               ; corridor (functionally floor)
T_STAIRS            EQU 3               ; down-stairs (unused in P3)

; Map viewport sits at rows 1..21, cols 1..30 (design §2.4): row 0 = status,
; row 23 = message. Map tile (mx,my) -> screen char cell (mx+OFF, my+OFF).
VIEW_COL_OFF        EQU 1
VIEW_ROW_OFF        EQU 1

;------------------------------------------------------------------------------
; Entity record (design §4.3) — fixed 16-byte stride for cheap slot indexing
; (slot*16 = 4 shifts). Slot 0 is always the player. P3 uses x/y/flags only;
; the rest are laid out now so P4 monsters/combat slot in without churn.
;------------------------------------------------------------------------------
ENT_KIND            EQU 0               ; entity kind (0 = player)
ENT_X               EQU 1               ; tile column 0..MAP_W-1
ENT_Y               EQU 2               ; tile row    0..MAP_H-1
ENT_HP              EQU 3
ENT_MAX_HP          EQU 4
ENT_ATK             EQU 5
ENT_DMG             EQU 6
ENT_FLAGS           EQU 7               ; EF_* bitfield
ENT_GLYPH           EQU 8
ENT_ATTR            EQU 9
ENT_WPN_BONUS       EQU 10              ; player-only (P4); spare in slot 0
ENT_POTIONS         EQU 11              ; player-only (P4)
ENT_GOLD            EQU 12              ; player-only word (12-13)
ENT_XP              EQU 14              ; player-only (P4)
ENT_LEVEL           EQU 15              ; player-only (P4)
ENT_STRIDE          EQU 16
MAX_ENTITIES        EQU 16              ; design §4.4 (slot 0 player + 15 monsters)
ENT_ARRAY_LEN       EQU MAX_ENTITIES * ENT_STRIDE   ; 256 bytes

; flags bitfield (design §4.3)
EF_ACTIVE           EQU %00000001
EF_PLAYER           EQU %00000010
EF_HOSTILE          EQU %00000100
EF_DIRTY            EQU %00001000

; Player starting position/stats (design §5.4). Start (1,5) sits against the
; left border wall: west = wall (wall-block test), east/NE = floor (move +
; diagonal-chord tests).
PLAYER_START_X      EQU 1
PLAYER_START_Y      EQU 5
PLAYER_START_HP     EQU 12
PLAYER_START_ATK    EQU 1

;------------------------------------------------------------------------------
; Render attributes — one attr byte per cell (clash-free by construction, §1).
;------------------------------------------------------------------------------
ATTR_MAP            EQU COL_WHITE | (COL_BLACK << PAPER_SHIFT)               ; $07
ATTR_PLAYER         EQU COL_YELLOW | (COL_BLACK << PAPER_SHIFT) | ATTR_BRIGHT ; $46

;------------------------------------------------------------------------------
; Input (design §3, REVISED: 4 keys chordable to diagonals).
; The sampler sums held movement keys into a bitset; dirs_to_step turns the
; bitset into a signed (dx,dy), each component in {-1,0,+1}.
;------------------------------------------------------------------------------
; C3-1: the JOY_* (Kempston) bit order, so PLAYER_DIR = STICK & JOY_DIRS
; (hero_defs.asm ASSERTs the match; N / S swapped vs PROTO).
DIR_E_BIT           EQU 0               ; east  (JOY_R)
DIR_W_BIT           EQU 1               ; west  (JOY_L)
DIR_S_BIT           EQU 2               ; south (JOY_D)
DIR_N_BIT           EQU 3               ; north (JOY_U)

; Action codes returned by get_action (design §3 engine contract).
ACT_NONE            EQU 0
ACT_MOVE            EQU 1
ACT_WAIT            EQU 2
ACT_QUAFF           EQU 3               ; reserved (no behaviour in P3)
ACT_DESCEND         EQU 4               ; reserved (no behaviour in P3)
ACT_CONFIRM         EQU 5               ; reserved (no behaviour in P3)

;------------------------------------------------------------------------------
; Keyboard matrix mirror. scan_matrix copies the 8 hardware half-rows (read via
; IN A,(C), active-low: bit clear = pressed) into KBD_MATRIX so the sampler reads
; RAM, not the port. This lets `test` inject keys by poking the mirror (see
; INPUT_SRC). Half-row order is the scan order (B = $FE rotated left 8x).
;------------------------------------------------------------------------------
KBROW_CAPSV         EQU 0               ; CAPS Z X C V        (port $FEFE)
KBROW_ASDFG         EQU 1               ; A S D F G           (port $FDFE)
KBROW_QWERT         EQU 2               ; Q W E R T           (port $FBFE)
KBROW_12345         EQU 3               ; 1 2 3 4 5           (port $F7FE)
KBROW_09876         EQU 4               ; 0 9 8 7 6           (port $EFFE)
KBROW_POIUY         EQU 5               ; P O I U Y           (port $DFFE)
KBROW_HJKL          EQU 6               ; ENTER L K J H       (port $BFFE)
KBROW_SPACE         EQU 7               ; SPACE SYM M N B     (port $7FFE)
KBD_MATRIX_LEN      EQU 8

; key bit positions within their half-row byte (bit clear = pressed)
KB_ENTER_BIT        EQU 0               ; KBROW_HJKL
KB_L_BIT            EQU 1
KB_K_BIT            EQU 2
KB_J_BIT            EQU 3
KB_H_BIT            EQU 4
KB_P_BIT            EQU 0               ; KBROW_POIUY
KB_O_BIT            EQU 1
KB_Q_BIT            EQU 0               ; KBROW_QWERT
KB_A_BIT            EQU 0               ; KBROW_ASDFG
KB_D_BIT            EQU 2               ; KBROW_ASDFG (descend)
KB_G_BIT            EQU 4               ; KBROW_ASDFG (quaff)
KB_SPACE_BIT        EQU 0               ; KBROW_SPACE (wait)
KB_I_BIT            EQU 2               ; KBROW_POIUY (C3-1: inventory shortcut)
KB_CAPS_BIT         EQU 0               ; KBROW_CAPSV (C3-1: BREAK = CAPS + SPACE)

KBD_RELEASED        EQU $FF             ; mirror byte with no key held

;------------------------------------------------------------------------------
; Game-state byte values (test-observable; see docs/memory-map.md)
;------------------------------------------------------------------------------
GS_BOOT             EQU $01             ; skeleton reached its halt-loop (P2)
GS_PLAYING          EQU $02             ; reserved: in-game turn loop
GS_WIN              EQU $03             ; reserved: descended level 2
GS_DEAD             EQU $04             ; reserved: player died

;------------------------------------------------------------------------------
; RNG seed (fixed compile-time seed; non-zero per xorshift16, design §5.6)
;------------------------------------------------------------------------------
RNG_SEED            EQU $A55A           ; known non-zero word for reproducibility

;------------------------------------------------------------------------------
; Test-observable working storage — STABLE ADDRESSES (docs/memory-map.md).
; Reserved as EQU so no image bytes are emitted; start: initialises at runtime.
;------------------------------------------------------------------------------
GAME_STATE          EQU $BF00           ; byte: current game-state enum (GS_*)
RNG_STATE           EQU $BF01           ; word: xorshift16 state (design §5.6)
TURN_COUNTER        EQU $BF03           ; word: turns elapsed (design §4.1)
INPUT_SRC           EQU $BF05           ; byte: 0 = scan keyboard; !=0 = use mirror
                                        ;       as-is (test injection, see scan_matrix)
KBD_MATRIX          EQU $BF06           ; 8-byte keyboard half-row mirror ($BF06-$BF0D)
WORKSTORE_TOP       EQU $BF00           ; initial SP; working storage grows down

; Entity array — 256 bytes well below the stack region (design §4.3/§4.4).
; Player is slot 0; its x/y are the stable test-observable PLAYER_X/PLAYER_Y.
ENTITIES            EQU $B000           ; $B000..$B0FF (ENT_ARRAY_LEN = 256)
PLAYER_X            EQU ENTITIES + ENT_X    ; $B001 — test-observable
PLAYER_Y            EQU ENTITIES + ENT_Y    ; $B002 — test-observable
