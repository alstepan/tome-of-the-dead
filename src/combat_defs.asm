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
ST_T2           EQU $B3F0           ; STMR2: lo nibble WEAK turns (hi nibble unused since POIS1)
ST_X            EQU $B400           ; per slot: POISON turns (POIS1, a full byte, cap PSN_CAP); the rest spare
                                    ;   (§6.4 "byte 3", e.g. the Vampire's fled-once)
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
STS_GUARD_BIT   EQU 6               ; HOLD_GUARD (game.md §6.4.1 B1)
STS_GUARD       EQU 1 << STS_GUARD_BIT
STS_HWEAK_BIT   EQU 7               ; 3E-T9: hunger WEAK (slot 0 only; HSTAGE == HS_WEAK, hunger6.asm)
STS_HWEAK       EQU 1 << STS_HWEAK_BIT
STS_MAX_TURNS   EQU 15              ; one nibble per timer
; POIS1 (game.md §6.4.3): POISON turns per application (x2 of B5), summed per hit up to
; PSN_CAP, in ST_X. deal_hit's turns nibble carries HALF the turns (a 4-bit field cannot hold
; 18 / 24): the kind-table rows (3F) store PSN_x / 2 and deal_hit doubles it.
PSN_CAP         EQU 30
PSN_SPIDER      EQU 12
PSN_RAT         EQU 12              ; Giant Rat (K_RAT)
PSN_QUEEN       EQU 18              ; Spider Queen
PSN_WIDOW       EQU 24              ; Black Widow
                ASSERT PSN_CAP < 256 && PSN_QUEEN / 2 <= STS_MAX_TURNS && PSN_WIDOW / 2 <= STS_MAX_TURNS
                ASSERT (PSN_SPIDER | PSN_RAT | PSN_QUEEN | PSN_WIDOW | PSN_CAP) % 2 == 0
; D3-8 sprite tints (game.md §6.4 "Indication"): HOLD kind 1..3, else CONFUSED.
; render (anim.asm) derives the tint from ST_FLAGS every tick (no tint state);
; a tint equal to the body's KT_ATTR uses its BRIGHT twin (attr XOR $40).
; Priority: the E_FLT flash > HOLD > CONFUSED > the kind attr. FEAR / POISON /
; WEAK: no tint.
TINT_FROZEN     EQU $45
TINT_ASLEEP     EQU $41
TINT_STUNNED    EQU $07
TINT_CONFUSED   EQU $43
STS_TINTED      EQU STS_HOLD | MIND_CONFUSED   ; flags & this != 0 -> a tint (MIND 3 is reserved, never set)
; D3-8 hero status icons (game.md §6.4: row 21, cols 30-31, priority HOLD >
; MIND > POISON > WEAK): st_sig (icons.asm) packs the first two as icon index
; + 1 (status_icons order FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR, POISON,
; WEAK; 0 = blank): low nibble -> col 30, high nibble -> col 31. STAT_SH =
; the sig as drawn (icon_poll sets PD_ICONS on a change; item_icons draws).
SI_FEAR         EQU 5               ; icon index + 1
SI_CONFUSED     EQU 4
SI_POISON       EQU 6
SI_WEAK         EQU 7
ST_ICON_COL     EQU 30
; D3-8d status marks (game.md §6.4.1 V2; src/mark.asm bank 2, src/mark7.asm
; bank 7): one 8x8 glyph above each visible HOLD / MIND body (HOLD > MIND),
; glyph g = status_icons index + 1 (FROZEN 1, ASLEEP 2, STUNNED 3 = the HOLD
; kind; CONFUSED 4, FEAR 5), its own attr on black paper, frame A / B every 8
; ticks. Per slot: SLOTREC R_MK / R_MKLO (the mark as drawn). State bytes in
; the bank-2 spare after DRIP_SRC (test-observable):
MK_N            EQU $BC0C           ; marks drawn now (0: cell_occ skips the map test)
MK_RR           EQU $BC0D           ; RLIST index the next pass starts at (round robin)
MK_OPS          EQU $BC0E           ; mark ops (draw / erase / redraw / a draw attempt whose cell
                                    ; was covered) done by the last mark_tick: <= MK_OPS_MAX; 0 on
                                    ; fire / 2nd-frame ticks. NOT counted: forgets (mk_forget, a
                                    ; damaged / covered mark dropped + its cell queued, ~1.5k T
                                    ; each, uncapped: one per drawn mark a render touched)
MK_LEFT         EQU $BC0F           ; ops left in this mark_tick
MK_OPS_MAX      EQU 2               ; game.md §6.4.1 "<= 2 mark operations per tick"
                ASSERT MK_N == DRIP_SRC + 2 * DRIP_SRC_MAX && MK_LEFT < ANIM_N2
; Runtime RAM in bank 5 ($5F00.., runtime only: the BASIC area above PF_RAM,
; never touched before boot): the drawn-mark cell map (cell_occ: a drop /
; decor step never lands on a mark) and the glyph copy (frame B derived).
MK_RAM          EQU $5F00
MK_MAP          EQU MK_RAM          ; PLAY_ROWS x 4 B: bit (7 - col & 7) of byte row * 4 + col / 8
MK_GLYPHS       EQU MK_MAP + PLAY_ROWS * 4  ; $5F48: per glyph (0, A0..A7), then a final 0
MK_G_STRIDE     EQU 9
MK_KINDS        EQU 5               ; FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR (status_icons 0..4)
MK_ATTRS        EQU MK_GLYPHS + MK_KINDS * MK_G_STRIDE + 1   ; $5F76: the 5 attrs (status_icons_attr)
MK_WAIT         EQU MK_ATTRS + MK_KINDS                      ; $5F7B: 16 B, per slot 1 = its last
                                    ; draw attempt found the cell covered (retry gated, mark.asm)
MK_AX           EQU MK_WAIT + P_MAX_ENT                      ; $5F8B: mk_draw's attr XOR (frame B BRIGHT)
MK_RAM_END      EQU MK_AX + 1                                ; $5F8C
                ASSERT (MK_MAP & $FF) == 0 && ((MK_RAM_END - 1) >> 8) == (MK_RAM >> 8)
                ASSERT MK_RAM >= PF_RAM + PF_RAM_LEN && MK_RAM_END <= $6000

;------------------------------------------------------------------------------
; 3F-T7 ranged attacks (game.md §9.2 RANGED-SPEC; src/ranged6.asm, R6; bank-2
; ranged2.asm ai_rhook + rk_tab). Runtime RAM RG_RAM right after MK_RAM (bank 5,
; runtime only, garbage at boot: ai_ranged writes the scratch before reading it,
; RS_N is reset whenever TP_SHOT is clear).
;------------------------------------------------------------------------------
RG_RAM          EQU MK_RAM_END      ; $5F8C
RG_ROW          EQU RG_RAM          ; 8 B: the shooter's rd_tab row (RW_*), copied per hook call
RG_OLD          EQU RG_ROW + 8      ; the cooldown counter at the hook's entry (before the decrement)
RG_DIR          EQU RG_OLD + 1      ; +1 hero to the right / $FF left
RG_FIRST        EQU RG_DIR + 1      ; the lowest gap col
RG_GAP          EQU RG_FIRST + 1    ; empty cols between the boxes
RG_F            EQU RG_GAP + 1      ; the shot: RGF_IMP (impact frame) / RGF_FLASH (HP lost)
RS_P            EQU RG_F + 1        ; low byte of the next free RS_Q entry (valid while TP_SHOT)
RS_Q            EQU RS_P + 1        ; RS_MAX x RS_STRIDE: {release tick R ($FF: started), the flash's
                                    ; impact tick (0: none / done), the FX descriptor (FXD_LEN)}
RS_STRIDE       EQU 2 + FXD_LEN
RS_MAX          EQU 4               ; shooters in one monster phase (Σ12, weight >= 4: <= 3); a 5th: FX_DROP
RS_SINK         EQU RS_Q + RS_MAX * RS_STRIDE   ; the overflow entry: written, never run
RG_RAM_END      EQU RS_SINK + RS_STRIDE
                ASSERT RG_RAM_END <= $6000 && (RG_RAM >> 8) == ((RG_RAM_END - 1) >> 8)
RS_R            EQU 0               ; RS_Q entry fields
RS_FL           EQU 1
RS_D            EQU 2
RS_STARTED      EQU $FF
RGF_IMP_BIT     EQU 0
RGF_FLASH_BIT   EQU 1
RG_REL          EQU 2               ; release tick = the monster phase's tick + RG_REL + (slot & 1)
; rd_tab row (R6 ranged6.asm), RW_STRIDE B per shooter; rk_tab[kind] (bank 2) = its row 1.., 0 = none
RW_R            EQU 0               ; range r: in range iff gap < r
RW_N            EQU 1               ; cooldown N: the counter := N on a shot (N = 1 every 2nd turn, 2 every 3rd)
RW_F            EQU 2               ; RWF_*
RW_DIE          EQU 3               ; damage 1dDIE + BON
RW_BON          EQU 4
RW_DHC          EQU 5               ; deal_hit C (DTY_* | DH_NODEF | EFX << DH_EFX_SHIFT)
RW_DHE          EQU 6               ; deal_hit E (on-hit effect: chance 1 in N << 4 | turns)
RW_FX           EQU 7               ; flight fid A; fid + 1 = B, fid + 2 = the impact frame (unless RWF_NOIMP)
RW_STRIDE       EQU 8
RWF_SPELL       EQU %00000001       ; auto-hit (no d20; Necro / Bone Caller / Archmage)
RWF_AWAY        EQU %00000010       ; steps away from the hero at gap 2 (not the Sniper)
RWF_NOIMP       EQU %00000100       ; no impact frame (dagger_spin rock)
RWF_PRE         EQU %00001000       ; T9 / T11: the caster pre-rule slot runs first (summon / teleport)
RWF_NOREFL      EQU %00010000       ; ignores the reflect gate (Archmage, T11)
RWF_BNC1        EQU %01000000       ; bits 6-7: wall bounces (Archmage 1; T11, unread)
RK_ARCHER       EQU 1               ; rd_tab rows
RK_SNIPER       EQU 2
RK_SLINGER      EQU 3
RK_NECRO        EQU 4
RK_BONE_CALLER  EQU 5
RK_ARCHMAGE     EQU 6               ; T11: data only (rk_tab[K_ARCHMAGE] stays 0 until the Archmage AI)
RK_ROWS         EQU 6
; E_RCD (= E_POT, unused by monsters): bits 0-1 the cooldown counter stored XOR 1 (the
; zeroed spawn slot (lp_spawn) / place_follower's 0 = counter 1: no shot on the first
; monster phase after the room entry); bits 2-5 T9's Bone Caller summon counter (unused yet)
E_RCD           EQU E_POT
RCD_MASK        EQU %00000011
RCD_SUMMON      EQU %00111100       ; T9
MK_G_CONF       EQU 4               ; glyph g of CONFUSED / FEAR (HOLD: g = the HOLD kind)
MK_G_FEAR       EQU 5
MK_FRAME        EQU %00001000       ; R_MK bit 3: frame B (A shifted up 1 px)
MK_THIRD        EQU %00110000       ; R_MK bits 4-5: row >> 3
MK_GMASK        EQU %00000111       ; R_MK bits 0-2: g (0 = no mark)
SLEEP_FLASH     EQU 1               ; V3: a typeless ASLEEP apply flashes SLEEP_FLASH_ATTR 1 tick
SLEEP_FLASH_ATTR EQU $4F            ; bright white on blue: no kind attr / tint uses a paper
                                    ; (all are paper 0), so it differs from every body and the
                                    ; $41 ASLEEP tint that follows it
MK_BRIGHT       EQU $40             ; frame B of a glyph using all 8 rows (ASLEEP, STUNNED): attr
                                    ; XOR BRIGHT instead of the 1-px shift (manager 2026-10-14)
; Boss flag (game.md §6.4 / §9.1; D3-8): bit 7 of the kind's KX_IMM byte
; (bank 3, read by deal_hit only). A boss is immune to ASLEEP and FEAR (deal_hit
; ORs IMMF_SLEEP | IMMF_FEAR in) and HOLD / MIND durations are halved (round
; down, 0 = none) after the R halving. No kind sets it before 3F (tests poke it).
IMMF_BOSS_BIT   EQU 7               ; (deal_hit tests it with rla: must stay bit 7)
EF_PLAYER_BIT   EQU 1
; 3F-T6 (game.md §9.1 / §9.6 / §9.8 D3-7): parry chance /256 by kind id in deal_hit (no data byte)
PARRY_GUARD     EQU 64              ; Skeleton Guard 1 in 4
PARRY_KNIGHT    EQU 85              ; Skeleton Knight + Death Knight ~1 in 3
FOOD_MUMMY      EQU 5               ; the Mummy's hit drains this much FOOD (game.md §9.1)
RAGE_ATK        EQU 2               ; Orc Berserker at hp <= max / 2 (§9.6)
                ASSERT EF_PLAYER == 1 << EF_PLAYER_BIT

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
; CAST_ROW (RANK1; was RANK_ROWS, 5 rows kept by rank_sync) — the rank row of
; the spell being cast: abil_load (bank 3) copies the ab_rank row of the
; highest rank the hero can afford now (auto-downcast, game.md §5; rank 1 is
; the floor) there at every spell use; abil_spell (cost check + payment), the
; accept's proj_pre and the release's proj_rel read it. One row, RR_STRIDE B.
;------------------------------------------------------------------------------
CAST_ROW        EQU $B4E0           ; $B4E0..$B4E5 ($B4E6..$B4FD free: FONT6 plane hole)
RANK_N          EQU 5               ; abilities per class (Mage 5 spells; Warrior uses 2)
RR_STRIDE       EQU 6
RR_MP           EQU 0               ; MP cost
RR_RANGE        EQU 1               ; cells
RR_DIE          EQU 2               ; damage die N (1dN)
RR_BONUS        EQU 3               ; + damage
RR_BOUNCE       EQU 4               ; wall bounces
RR_EFFECT       EQU 5               ; effect duration / chance
                FONT6_HOLE CAST_ROW, RR_STRIDE

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
HERO_DEF        EQU HERO3D + 7      ; D3-6a: the hero's DEF (sum over worn gear; hero_recalc owns it, 3E-T8)
XP_UP           EQU HERO3D + 8      ; D3-6a: 1 = deal_hit added XP; xp_turn (end_turn, xp7.asm) checks the level-up and clears it
HERO3D_END      EQU HERO3D + 9
                ASSERT HERO3D >= ANIM_LIST2 + ANIM_MAX * AL_STRIDE && HERO3D_END <= ANIM_N
                ASSERT (HERO3D >> 8) == ((HERO3D_END - 1) >> 8)

;------------------------------------------------------------------------------
; TURN_PEND block (D3-7) — the split ability turn, right after HERO3D in the
; same spare ($BC4A..$BC50; level_reset_new zeroes HERO3D..TURN_PEND_END).
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
LOG_TURN        EQU TURN_PEND + 5   ; T7 log drain: bit 0 LT_SERVED (item_log drew a line since the
                                    ; last end_turn), bit 1 LT_HOLD (end_turn: a turn passed with lines
                                    ; pending and none drawn -> turn_input holds the next turn until
                                    ; item_log draws one; that idle tick drains in its 1st frame)
LOG_PDIR        EQU TURN_PEND + 6   ; T7 review: the input a log hold swallowed (PLAYER_DIR bits 0-3,
                                    ; bit 7 = DK_WAIT): a tap released during the hold is replayed
TURN_PEND_END   EQU TURN_PEND + 7
; D3-8 hero status step state (right after TURN_PEND, same spare; zeroed by
; level_reset_new with HERO3D..GEAR_MP, 3E-T8):
HST_DONE        EQU TURN_PEND_END   ; 1 = the hero's status step already ran for the turn being
                                    ; entered (turn_input runs it before the action, once:
                                    ; an illegal try costs no turn and must not step twice);
                                    ; 0 again once a turn is spent
HELD_T          EQU TURN_PEND_END + 1   ; held hero: INPUT-phase ticks counted; the Wait turn
                                    ; starts on the HELD_WAIT-th (game.md §2.2 "one turn per 4
                                    ; ticks": a Wait turn with nothing moving spans 2 ticks, input +
                                    ; turn_done; measured, tests/status.py H1)
COMBAT_NOT_BEFORE EQU TURN_PEND_END + 2   ; D3-8e2 (game.md §6.5.1): != 0: panel_tick draws
                                    ; nothing (log, target readout, HP bar) while TURN_TICK <= it.
                                    ; act_begin: a cast that struck a body at the accept = min(the
                                    ; first impact tick pf_ftick, ACT_FIRE_TICK + CNB_MAX), a miss 0;
                                    ; end_turn: 0 (with TURN_TICK); act_pend's log wait counts from
                                    ; max(MON_AT, it)
CNB_MAX         EQU 8               ; ticks past the release the gate holds at most (§6.5.1 "Bound")
ST_HERO_END     EQU TURN_PEND_END + 3
; 3E-T2 bag page state (same spare, after ST_HERO_END; runtime RAM, garbage at
; boot: page_ovl / page_post write PAGE_OPEN, PAGE_N only counts — tests diff it)
PAGE_OPEN       EQU ST_HERO_END     ; 1 while the bag page is up (page_ovl / page_post, test-observable)
PAGE_N          EQU ST_HERO_END + 1 ; bag page opens, mod 256 (test-observable)
PAGE_VERB       EQU ST_HERO_END + 2 ; 3E-T13: the verb chosen on the page (VB_*, item_defs.asm; VB_NONE
                                    ; = closed without one), written by the overlay at every open
PAGE_SLOT       EQU ST_HERO_END + 3 ; 3E-T13: its slot: 0..19 bag, 20..23 worn (BAG + 3 * slot; test-observable)
PAGE_END        EQU ST_HERO_END + 4
; 3E-T8 (same spare, after PAGE_*; level_reset_new zeroes HERO3D..GEAR_MP incl. PAGE_*):
GEAR_MP         EQU PAGE_END        ; the gear MP hero_recalc has added into MAXMP (0 at new_game;
                                    ; recalc: MAXMP += new - GEAR_MP, so level-ups / tomes stay)
MP_PER          EQU PAGE_END + 1    ; MP regen period (turns) for xp_turn: class 8 / 6, x 1/2 with
                                    ; the Mana / Scarab amulet, x 2 with Plate (hero_recalc)
FX_OP           EQU PAGE_END + 2    ; fx_main (R6): in = the op (FX_*), out = the FXR_* result flags
FX_ARG          EQU PAGE_END + 3    ; fx_main: the op's argument (a slot: BAG + 3 * arg)
PAGE_VLAST      EQU PAGE_END + 4    ; the verb page_post last consumed (VB_*; test-observable only)
QS_RECHK        EQU PAGE_END + 5    ; IC1: bit 7 = the icon bar needs an item_icons pass in a tick's 1st
                                    ; frame (icon_poll): a quick slot left undrawn (2nd frame) / forced by
                                    ; pot_sync, or HP / MP changed (the potion pick); bits 0-6 0. No init:
                                    ; a stale bit costs one pass
WEAR_PEND       EQU PAGE_END + 6    ; 3F-T6 (game.md §8.10): bitfield of the wear events decided this turn
                                    ; (abil6.asm wear_slot ORs it on the input tick: the item's m is already -1 /
                                    ; the slot already empty): bit 2 s = notch / acid, bit 2 s + 1 = broke, slot s =
                                    ; WS_WEAPON / ARMOUR / HELM. hunger_turn (end_turn, R6) wear_apply: hero_recalc
                                    ; once, per slot its line (break preferred) + worn cell, then 0. Cleared by
                                    ; level_reset_new (not in the HERO3D..MP_PER zeroing run)
HERO_T8_END     EQU PAGE_END + 7
HELD_WAIT       EQU 3
LT_SERVED       EQU 1
LT_HOLD_BIT     EQU 1
LT_HOLD         EQU 1 << LT_HOLD_BIT
TP_ACT_BIT      EQU 0               ; ability logic pending (act_fire at ACT_AT)
TP_MON_BIT      EQU 1               ; monster phase pending
TP_FIRE_BIT     EQU 2               ; this is the fire tick: panel item + decor_tick skipped
TP_ACT          EQU 1 << TP_ACT_BIT
TP_MON          EQU 1 << TP_MON_BIT
TP_FIRE         EQU 1 << TP_FIRE_BIT
TP_SHOT_BIT     EQU 3               ; 3F-T7: monster shots queued (RS_Q): act_pend far6s shot_tick each
TP_SHOT         EQU 1 << TP_SHOT_BIT ; tick (FX start at the release, hero flash at the impact); holds the turn
ACT_FIRE_TICK   EQU 2              ; release tick f of every ability (game.md §6.1 "Release ticks")
                ASSERT TURN_PEND == $BC4A && HERO_T8_END <= ANIM_N
                ASSERT (HERO3D >> 8) == ((HERO_T8_END - 1) >> 8) && FX_ARG == FX_OP + 1

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
; K_MAX rows, one page (ASSERTed at the table: `ld h` + kind * 8 in L).
; Data: D3-1 (zeros until then = N everywhere, no immunity, 0 XP, DEF 0).
;------------------------------------------------------------------------------
KX_STRIDE       EQU 8
KX_RES          EQU 0               ; 3 B, RES_* format
KX_IMM          EQU 3               ; IMMF_* mask
KX_XP           EQU 4               ; KXP: XP awarded on death (game.md §4.1)
KX_DEF          EQU 5               ; monster DEF (0 in 3D, game.md §11.4)
KX_MELEE        EQU 6               ; 2 B: the kind's melee hit as deal_hit's {C, E} (3F-T2: was
                                    ; combat3.asm's kx_melee table, folded into the old KX_SPARE):
                                    ; +0 dty | efx << DH_EFX_SHIFT, +1 chance << 4 | turns
KX_LEN          EQU K_MAX * KX_STRIDE   ; 256 B (MEM-1: was 6 x 32 = 192)
                ASSERT KX_RES + RES_LEN == KX_IMM && KX_LEN <= 256 && KX_STRIDE == 8 && KX_MELEE + 2 == KX_STRIDE

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
LVL_MAX         EQU 9               ; game.md §4.1: levels 1..9 (D3-9b: from info1.asm)
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
; hero's rank, or ab_ammo). In PF_RAM's free middle ($5E63..$5EDF; D3-8e: was
; $5E60, the pf_* block grew to $5E62), clear
; of the pf_* block and PF_ROWF (ASSERTed in proj3.asm).
ABIL_DESC       EQU PF_RAM + $68    ; $5E68..$5E77 (D3-8e; was $5E60)
ABIL_RK         EQU ABIL_DESC + 10  ; = + ABD_STRIDE: the rank row (proj_fire HL)
ABIL_DESC_LEN   EQU 16
; ABIL_TGT (D3-7 T5) — word: the power attack's target slot mask (bit s =
; slot s), found by melee_scan at the accept (abil_melee7.asm) and struck by
; power_fire on the fire tick (nothing moves in between: the monster phase is
; deferred), so the fire tick does not scan again. Right after ABIL_DESC.
ABIL_TGT        EQU ABIL_DESC + ABIL_DESC_LEN   ; $5E78..$5E79 (D3-8e; was $5E70)
