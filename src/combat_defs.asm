;==============================================================================
; combat_defs.asm — Stage 3D contracts (D3-0; plan "3D breakdown" R2 / R3).
; Addresses + layouts only (EQU / ASSERT: no image bytes). INCLUDEd once, by
; defs.asm after hero_defs.asm. docs/memory-map.md "3D contracts (D3-0)" is
; the authoritative table; change both together.
;
; Homes (R3): the 3D runtime state lives in bank-2 runtime RAM that is free
; today, so the image / tape do not grow: the FONT6 plane holes (offsets
; 0..31 / 224..255 of each font page, level_defs.asm; the planes use
; FONT6_FIRST..223 only) and the spare $BC41..$BC5E after ANIM_LIST2. Runtime
; RAM, not on tape: garbage at boot; the owner code initialises it (new_game /
; level_reset do the status arrays + HERO3D, see bank3.asm).
;==============================================================================

; FONT6_HOLE addr, len — len bytes at addr sit in ONE plane-hole page (never in a font
; window, never in HOT_COPY): one H for the whole record, `inc l` walks it.
    MACRO FONT6_HOLE addr, len
                ASSERT (addr) >= FONT6 && (addr) + (len) <= HOT_COPY
                ASSERT ((addr) >> 8) == (((addr) + (len) - 1) >> 8)
                ASSERT (((addr) & $FF) + (len) <= FONT6_FIRST) || (((addr) & $FF) >= FONT6_FIRST + 2 * FONT6_WB)
    ENDM

;------------------------------------------------------------------------------
; Status effects (game.md §6.4): 4 parallel per-slot arrays, index = entity
; slot 0..15 (slot 0 = hero). byte = array + slot (one `ld l` per field).
; Slot 0 CARRIES across levels (HERO_CARRY rule, bank3.asm level_populate):
; level_reset clears slots 1..15 only; new_game clears slot 0 too.
;------------------------------------------------------------------------------
ST_SLOTS        EQU P_MAX_ENT       ; 16
ST_FLAGS        EQU $B310           ; STATUS (layout below); 0 = fast path
ST_T1           EQU $B3E0           ; STMR1: hi nibble HOLD turns, lo nibble MIND turns
ST_T2           EQU $B3F0           ; STMR2: hi nibble POISON turns, lo nibble WEAK turns
ST_X            EQU $B400           ; spare per slot (§6.4 "byte 3", e.g. the Vampire's fled-once)
                FONT6_HOLE ST_FLAGS, ST_SLOTS
                FONT6_HOLE ST_T1, ST_SLOTS
                FONT6_HOLE ST_T2, ST_SLOTS
                FONT6_HOLE ST_X, ST_SLOTS
                ASSERT (ST_FLAGS >> 8) == (ST_T1 >> 8) && (ST_T1 >> 8) == (ST_T2 >> 8)  ; level_reset: one H
; STATUS bits (invariant: a group's kind/bit set <=> its timer nibble != 0)
STS_HOLD        EQU %00000011       ; HOLD kind (2 bits):
HOLD_FROZEN     EQU 1
HOLD_ASLEEP     EQU 2
HOLD_STUNNED    EQU 3
STS_MIND        EQU %00001100       ; MIND kind (2 bits, << 2):
MIND_FEAR       EQU 1 << 2
MIND_CONFUSED   EQU 2 << 2          ; (3 << 2 reserved)
STS_POISON_BIT  EQU 4
STS_WEAK_BIT    EQU 5
STS_GUARD_BIT   EQU 6               ; STUN_GUARD
STS_MAX_TURNS   EQU 15              ; one nibble per timer

;------------------------------------------------------------------------------
; FX tracks (render-only projectile / impact tracks, D3-5 owns the fields):
; FX_TRACKS records of FXREC_STRIDE B; record i = FXREC + i * 16 (linear;
; each record inside one page). FX queue: FXQ_N descriptors of FXQ_STRIDE B
; (proj_fire -> fx_render hand-off; D3-5 owns the fields).
;------------------------------------------------------------------------------
FXREC           EQU $B2E0           ; $B2E0..$B30F
FX_TRACKS       EQU 3
FXREC_STRIDE    EQU 16
                FONT6_HOLE FXREC, FXREC_STRIDE
                FONT6_HOLE FXREC + FXREC_STRIDE, FXREC_STRIDE
                FONT6_HOLE FXREC + 2 * FXREC_STRIDE, FXREC_STRIDE
                ASSERT FX_TRACKS == 3 && FXREC + FX_TRACKS * FXREC_STRIDE <= ST_FLAGS
FXQ             EQU $B410           ; $B410..$B41F
FXQ_N           EQU 2
FXQ_STRIDE      EQU 8
                FONT6_HOLE FXQ, FXQ_N * FXQ_STRIDE
                ASSERT FXQ >= ST_X + ST_SLOTS

;------------------------------------------------------------------------------
; RANK_ROWS — the hero's current-rank rows (game.md §5 "Data / cost"): one
; row per ability index k (ARANK bits 2k..2k+1), copied from the bank-3 rank
; table on learn / rank-up (D3-9b), read by the cast path. RR_STRIDE B/row.
;------------------------------------------------------------------------------
RANK_ROWS       EQU $B4E0           ; $B4E0..$B4FD
RANK_N          EQU 5               ; abilities per class (Mage 5 spells; Warrior uses 2)
RR_STRIDE       EQU 6
RR_MP           EQU 0               ; MP cost
RR_RANGE        EQU 1               ; cells
RR_DIE          EQU 2               ; damage die N (1dN)
RR_BONUS        EQU 3               ; + damage
RR_BOUNCE       EQU 4               ; wall bounces
RR_EFFECT       EQU 5               ; effect duration / chance
                FONT6_HOLE RANK_ROWS, RANK_N * RR_STRIDE

;------------------------------------------------------------------------------
; HERO3D — hero 3D state in the spare after ANIM_LIST2 ($BC41..$BC5E, 30 B;
; one page with HERO_ST). new_game zeroes HERO3D..HERO3D_END.
;------------------------------------------------------------------------------
HERO3D          EQU $BC41
MP_RG           EQU HERO3D + 0      ; MP regen turn counter
HERO_RES        EQU HERO3D + 1      ; 3 B: the hero's resistances (RES_* format below; OR of gear, 3E)
HERO_IMM        EQU HERO3D + 4      ; status immunity mask (IMMF_*; OR of gear, 3E)
MP_SH           EQU HERO3D + 5      ; panel: MP as last drawn (PD_MP item, like PANEL_HP_SH)
STAT_SH         EQU HERO3D + 6      ; panel: status icons as last drawn (row 21, cols 30-31)
HERO3D_END      EQU HERO3D + 7
                ASSERT HERO3D >= ANIM_LIST2 + ANIM_MAX * AL_STRIDE && HERO3D_END <= ANIM_N
                ASSERT (HERO3D >> 8) == ((HERO3D_END - 1) >> 8)

;------------------------------------------------------------------------------
; Damage types (game.md §6.0) and the 3-B resistance record (KX_RES /
; HERO_RES): a 2-bit response per type + a weak mask.
;   RES_B0: PHYS bits 1-0, FIRE 3-2, COLD 5-4, SHOCK 7-6
;   RES_B1: DRAIN bits 1-0, DARK 3-2 (bits 7-4 zero)
;   RES_B2: W mask, bit t = weak (x2) to type t
; Response: field = (RES_B(t / 4) >> 2 * (t % 4)) & 3. Note: the hero's
; "best response wins" combine (3E gear) is a per-field max, not an OR
; (OR of R = 1 and I = 2 would read X = 3).
;------------------------------------------------------------------------------
DTY_PHYS        EQU 0
DTY_FIRE        EQU 1
DTY_COLD        EQU 2
DTY_SHOCK       EQU 3
DTY_DRAIN       EQU 4
DTY_DARK        EQU 5
DTY_COUNT       EQU 6
RSP_N           EQU 0               ; x1
RSP_R           EQU 1               ; x1/2, round down, min 1
RSP_I           EQU 2               ; 0, no side effect
RSP_X           EQU 3               ; reflect
RES_B0          EQU 0
RES_B1          EQU 1
RES_B2          EQU 2
RES_LEN         EQU 3
; status immunity mask (game.md §6.4 / §9.1)
IMMF_SLEEP      EQU %00000001
IMMF_STUN       EQU %00000010
IMMF_CONFUSE    EQU %00000100
IMMF_FEAR       EQU %00001000
IMMF_POISON     EQU %00010000

;------------------------------------------------------------------------------
; KX — per-kind extension table (R2), bank 3 (`kx_tab`, bank3.asm; read by
; the bank-3 combat code, never by bank 2). Row = kx_tab + kind * KX_STRIDE,
; K_MAX rows, one page (ASSERTed at the table: `ld h` + kind * 6 in L).
; Data: D3-1 (zeros until then = N everywhere, no immunity, 0 XP, DEF 0).
;------------------------------------------------------------------------------
KX_STRIDE       EQU 6
KX_RES          EQU 0               ; 3 B, RES_* format
KX_IMM          EQU 3               ; IMMF_* mask
KX_XP           EQU 4               ; KXP: XP awarded on death (game.md §4.1)
KX_DEF          EQU 5               ; monster DEF (0 in 3D, game.md §11.4)
KX_LEN          EQU K_MAX * KX_STRIDE   ; 192 B
                ASSERT KX_RES + RES_LEN == KX_IMM && KX_LEN <= 256
