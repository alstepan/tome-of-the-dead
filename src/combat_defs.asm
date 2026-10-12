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
; FX tracks (D3-5, src/fx.asm; game.md §6 "real sprites, render-only"):
; FX_TRACKS records of FXT_STRIDE 32 B, each in ONE FONT6 plane hole (IX +
; field): the first FXD_LEN 16 B are the caller's descriptor (fx_start copies it
; verbatim; the flight mutates FXD_COL / FXD_FLAGS / FXD_DELAY / FXD_IMPT /
; FXD_NSEG / FXD_SEGS in place), then the render state (desired FX_FID..FX_ATTR,
; drawn FX_DFID..FX_DATTR in the same order, drawn footprint FX_DCOL..).
; Queue: FXQ_MAX descriptors of FXD_LEN B (FIFO FXQ0, FXQ1).
;------------------------------------------------------------------------------
FX_TRACKS       EQU 3
FXT_STRIDE      EQU 32
FXT0            EQU $B2E0           ; $B2E0..$B2FF (page $B2 hole 224..255)
FXT1            EQU $B200           ; $B200..$B21F (page $B2 hole 0..31)
FXT2            EQU $B500           ; $B500..$B51F (page $B5 hole 0..31)
FXREC           EQU FXT0            ; (D3-0 name of the block)
FXQ_MAX         EQU 2
FXQ0            EQU $B410           ; $B410..$B41F (D3-0 FXQ)
FXQ1            EQU $B300           ; $B300..$B30F
FXQ             EQU FXQ0
FX_BUSY         EQU $B4FE           ; bit i = track i live or still drawn (0 = FX idle)
FXQ_N           EQU $B4FF           ; queued descriptors (0..FXQ_MAX)
                FONT6_HOLE FXT0, FXT_STRIDE
                FONT6_HOLE FXT1, FXT_STRIDE
                FONT6_HOLE FXT2, FXT_STRIDE
                FONT6_HOLE FXQ0, 16
                FONT6_HOLE FXQ1, 16
                FONT6_HOLE FX_BUSY, 2
                ASSERT FXQ1 + 16 <= ST_FLAGS && FXQ0 >= ST_X + ST_SLOTS
; descriptor (fx_start HL; 16 B; game.md §6, plan "3D breakdown" decision P)
FXD_FIDA         EQU 0               ; flight frame, even visible ticks
FXD_FIDB         EQU 1               ; flight frame, odd ticks (= FIDA: one frame)
FXD_IMPA         EQU 2               ; impact frame, even ticks (FX_NONE: no impact)
FXD_IMPB         EQU 3               ; impact frame, odd ticks
FXD_ATTR         EQU 4               ; 0 = each frame's own attr (fx_meta), else this attr
FXD_COL          EQU 5               ; anchor cell col (the 8-px body cell; 16-wide frames
                                    ; extend one cell AHEAD: right c..c+1, left c-1..c)
FXD_ROW          EQU 6               ; flight row (frame top = 8 row - ay, ay 0 / 8)
FXD_FLAGS        EQU 7               ; FXDF_*: direction + speed
FXD_DELAY        EQU 8               ; ticks hidden before the first frame
FXD_IMPT         EQU 9               ; impact ticks (0: none)
FXD_NSEG         EQU 10              ; segments 1..FXD_SEGMAX (a reversal between each)
FXD_SEGS         EQU 11              ; cells per segment (0 allowed)
FXD_SEGMAX       EQU 5
FXD_LEN          EQU 16
FXDF_LEFT        EQU 1               ; travelling left (bit 0; flips at each reversal)
FXDF_FAST        EQU 2               ; 16 px (2 cells) per tick (Lightning), else 8
FXDF_FAST_BIT    EQU 1
                ASSERT FXD_SEGS + FXD_SEGMAX == FXD_LEN
; render state (after the descriptor). FX frames are cell-aligned (ax, the
; left offset and ay multiples of 8: ASSERTed per frame at fx_meta), so a
; frame's position IS its footprint origin: desired / drawn = fid, attr,
; facing, footprint col, row, cols, rows (7 B each, same order).
FX_ST           EQU 16              ; FXS_*
FX_PH           EQU 17              ; frame alternation phase
FX_FID          EQU 18              ; desired: fid (FX_NONE hidden)
FX_ATTR         EQU 19              ;   attr
FX_LEFT         EQU 20              ;   facing (0 / FXDF_LEFT)
FX_COL          EQU 21              ;   footprint: frame px = 8 col, py = 8 row
FX_ROW          EQU 22
FX_COLS         EQU 23
FX_ROWS         EQU 24
FX_DFID         EQU 25              ; drawn (FX_NONE: nothing on the bank-5 screen)
FX_DATTR        EQU 26
FX_DLEFT        EQU 27
FX_DCOL         EQU 28              ; drawn footprint C, B, D, E
FX_DROW         EQU 29
FX_DCOLS        EQU 30
FX_DROWS        EQU 31
FX_STATE_LEN    EQU FX_DFID - FX_FID    ; 7
                ASSERT FX_DROWS - FX_DFID == FX_ROWS - FX_FID && FX_DROWS == FXT_STRIDE - 1
FXS_IDLE        EQU 0
FXS_WAIT        EQU 1
FXS_FLY         EQU 2
FXS_IMP         EQU 3
FX_NONE         EQU $FF
FX_SLOT0        EQU P_MAX_ENT       ; ANIM_SLOT = 16 + track while render erases / draws it (flicker.py)

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
HERO_DEF        EQU HERO3D + 7      ; D3-6a: the hero's DEF (armour; Warrior Leather 1, Mage 0: hero_st_init; gear 3E)
XP_UP           EQU HERO3D + 8      ; D3-6a: 1 = deal_hit added XP (D3-9's level-up check pending; D3-9 clears it)
HERO3D_END      EQU HERO3D + 9
                ASSERT HERO3D >= ANIM_LIST2 + ANIM_MAX * AL_STRIDE && HERO3D_END <= ANIM_N
                ASSERT (HERO3D >> 8) == ((HERO3D_END - 1) >> 8)

;------------------------------------------------------------------------------
; TURN_PEND block (D3-7) — the split ability turn, right after HERO3D in the
; same spare ($BC4A..$BC4E; level_reset_new zeroes HERO3D..TURN_PEND_END).
; Tick contract (T1, built; memory-map.md "Projectiles"): the input tick pays
; the cost, starts the hero's sequence and calls act_begin (act7.asm): no
; resolve_monsters there (turn_input skips it while MON_AT != 0). The
; anim_gate hook (TURN_PEND != 0 -> pend_far -> far7 act_pend) runs act_fire
; on TURN_TICK == ACT_AT, then the monster phase on the first tick with
; TURN_TICK >= MON_AT and FX_BUSY == 0 (designer 2026-10-12: after the hero's
; FX is idle, not at a fixed f+1), skipped if the hero is DYING; then
; TURN_PEND = MON_AT = 0. turn_done waits while TURN_PEND != 0.
;------------------------------------------------------------------------------
TURN_PEND       EQU HERO3D_END      ; TP_* bits below
ACT_ABL         EQU TURN_PEND + 1   ; ABL_* of the pending ability
ACT_AT          EQU TURN_PEND + 2   ; TURN_TICK of its release (fire tick f)
MON_AT          EQU TURN_PEND + 3   ; != 0: monster phase deferred; earliest TURN_TICK for it (f + 1)
FX_DROP         EQU TURN_PEND + 4   ; FX descriptors fx_start dropped (3 tracks + 2 queued busy),
                                    ; mod 256, zeroed per level (level_reset_new) — tests assert 0
TURN_PEND_END   EQU TURN_PEND + 5
TP_ACT_BIT      EQU 0               ; ability logic pending (act_fire at ACT_AT)
TP_MON_BIT      EQU 1               ; monster phase pending
TP_FIRE_BIT     EQU 2               ; this is the fire tick: panel item + decor_tick skipped
TP_ACT          EQU 1 << TP_ACT_BIT
TP_MON          EQU 1 << TP_MON_BIT
TP_FIRE         EQU 1 << TP_FIRE_BIT
ACT_FIRE_TICK   EQU 2               ; release tick f of every ability (game.md §6.1 "Release ticks")
                ASSERT TURN_PEND == $BC4A && TURN_PEND_END <= ANIM_N
                ASSERT (HERO3D >> 8) == ((TURN_PEND_END - 1) >> 8)

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

;------------------------------------------------------------------------------
; deal_hit (combat3.asm, D3-6a) argument C: damage type | flags | effect id.
; E = the effect parameter in the RK_EFFECT status format (combat_data3.asm):
; high nibble = chance "1 in N" (0 = always), low nibble = turns.
;------------------------------------------------------------------------------
DH_TYPE         EQU %00000111       ; DTY_* (0..5)
DH_NODEF_BIT    EQU 3               ; ignore DEF (spells; DEF applies to PHYS only anyway)
DH_NODEF        EQU 1 << DH_NODEF_BIT
DH_EFX_SHIFT    EQU 4               ; bits 4-6: EFX_* effect id applied on a non-lethal hit
DH_EFX          EQU %01110000
DH_HEAL_BIT     EQU 7               ; the attacker heals the HP lost (Drain Life, Vampire bite)
DH_HEAL         EQU 1 << DH_HEAL_BIT
; effect ids (game.md §6.4); HOLD ids == the STATUS HOLD kinds
EFX_NONE        EQU 0
EFX_FROZEN      EQU 1
EFX_ASLEEP      EQU 2
EFX_STUNNED     EQU 3
EFX_FEAR        EQU 4
EFX_CONFUSED    EQU 5
EFX_POISON      EQU 6
EFX_WEAK        EQU 7
                ASSERT EFX_FROZEN == HOLD_FROZEN && EFX_ASLEEP == HOLD_ASLEEP && EFX_STUNNED == HOLD_STUNNED
                ASSERT DTY_COUNT <= DH_TYPE + 1
XP_MAX          EQU 9999            ; game.md §4.1: XP saturates
                ASSERT HERO_IMM == HERO_RES + KX_IMM   ; deal_hit: one record layout (RES 3 B, IMM) for hero + kx row

;------------------------------------------------------------------------------
; proj_fire (proj3.asm, D3-6b; game.md §6 "Logic (instant at cast time)"):
; the projectile walk resolved at cast time, results in bank-3 scratch
; (pf_stop / pf_col / pf_tgt / pf_lost / pf_itick, read by D3-7 and the
; tests). Stop reasons (pf_stop, also returned in L):
;------------------------------------------------------------------------------
PFS_RANGE       EQU 0               ; range spent: impact on the last cell
PFS_WALL        EQU 1               ; solid cell ahead, no bounce left: impact on the free cell in front
PFS_BODY        EQU 2               ; struck a body (non-piercing): impact on its cell, pf_tgt = it
PFS_ABSORB      EQU 3               ; a mid-ladder body absorbed it harmlessly (pf_tgt stays $FF)
PFS_EXIT        EQU 4               ; flew into an open exit edge (col 0 / 31): no impact
PFS_LOOP        EQU 5               ; loop guard: PF_MAXREV reversals spent (impact on the current cell)
PF_MAXREV       EQU 4               ; game.md §6.0 "max 4 reversals per projectile"
PF_ROW_DY       EQU 2               ; flight row = caster top + 2 (staff tip / bow)
PF_IMPT         EQU 2               ; impact ticks of a projectile FX (IMPA, IMPB)
                ASSERT PF_MAXREV + 1 == FXD_SEGMAX     ; a reversal between each FX segment
; proj_fire scratch (proj3.asm pf_*: state, results, the 16-B FX descriptor,
; the candidate list): runtime RAM in bank 5's dead BASIC area (free once
; boot moved SP to $BF00; never on tape, never paged: bank 3 stays full).
PF_RAM          EQU $5E00
PF_RAM_LEN      EQU $100
                ASSERT PF_RAM >= $5CC0 && PF_RAM + PF_RAM_LEN <= $6000
; ABIL_DESC (D3-7) — the ability being used, filled by abil_load (bank 3,
; rank3.asm) for the bank-7 ability code, which cannot read bank 3: the
; ab_def row (ABD_*, 10 B) then its rank row (RK_*, 6 B: ab_rank at the
; hero's rank, or ab_ammo). In PF_RAM's free middle ($5E5D..$5EDF), clear
; of the pf_* block and PF_ROWF (ASSERTed in proj3.asm).
ABIL_DESC       EQU PF_RAM + $60    ; $5E60..$5E6F
ABIL_RK         EQU ABIL_DESC + 10  ; = + ABD_STRIDE: the rank row (proj_fire HL)
ABIL_DESC_LEN   EQU 16
