;==============================================================================
; proj3.asm — D3-6b: proj_fire, the projectile logic resolved at cast time in
; BANK 3 (plan "3D breakdown": logic instant, rendering by the D3-5 FX tracks).
; INCLUDEd from bank3.asm after combat3.asm. Rules: game.md §6 "Logic", §6.0
; (reflect, pierce + reflect, loop guard), §6.1 / §6.3 (spell / missile rows:
; combat_data3.asm ab_def / ab_rank / ab_ammo).
;
; The walk (cell by cell along the flight row, in the caster's facing; runs
; of plain cells (PF_ROWF = 0) are skipped in one fast-forward loop):
;   * start: the caster's leading body col (not entered, not counted);
;   * range: cells entered in total (a reversal itself costs none);
;   * next cell SOLID (tile_flags TF_SOLID: wall, closed door, block, lectern,
;     room edge): reverse if a bounce is left (keeping the range), else stop
;     (PFS_WALL, impact on the free cell in front);
;   * next cell = col 0 / 31 and not solid: an open exit edge: enter it, stop
;     (PFS_EXIT, no impact);
;   * bodies (the candidate list below) whose cols contain the next cell, in
;     list order, each at most once per pass (a reversal starts a new pass):
;       - mid-ladder (on_ladder): absorbs it harmlessly (PFS_ABSORB);
;       - reflects the type (RSP_X): reverse at its front cell (the current
;         one) without using a bounce; it takes nothing;
;       - else: a spell always hits (deal_hit handles I: 0 dmg, UNAFFECTED);
;         a dagger / arrow rolls hit_roll (ab_def ABD_HIT) and on a miss flies
;         on (T7: pf_miss, the body dodges: RC_DODGE when the FX passes); a hit deals 1d(die) + bonus via deal_hit; a non-piercing
;         projectile stops there (PFS_BODY), Lightning (ABF_PIERCE) goes on;
;   * the caster is a valid target only after the first reversal (Drain Life
;     on its caster: a normal DRAIN hit, no heal — D3-7 T4, game.md §6);
;   * at most PF_MAXREV reversals (bounces + reflections), then PFS_LOOP.
; Candidates = the LIVE_LIST bodies (not dying) whose rows overlap the
; caster's body rows (the "line": find_target's vertical rule, so a short Rat
; on the caster's floor is in line), in slot order (two bodies sharing a col:
; the lower slot decides first). The FX flies at the flight row, or at the
; nearest row of the first body it interacts with (§6 "if the hit body
; doesn't cover that row").
; Firebolt (ABF_BURST): at the impact (not PFS_EXIT / PFS_ABSORB: D3-7 T4,
; game.md §6 "no Firebolt burst" after an absorb) every candidate within 1
; col of the impact cell, except the body that stopped it, takes 1d(RK_EFFECT
; low nibble) FIRE; the caster too unless RKE_SPARE (rank 3).
; Every struck body's reaction is moved to the tick the FX reaches it
; (E_REACTAT = TURN_TICK + FXD_DELAY + ceil(moves / speed) + 1, fx_start's
; formula from the cast's tick; D3-7), so
; the HURT / DEATH plays under the impact. One FX track per cast (no extra
; impact flashes on pierced bodies: bank-3 room).
; Assumes every kind's KT_BW >= 2 (all 3D kinds are 3 or 4 cells): a body
; struck right after a reversal at its own front col is still entered.
;==============================================================================

; candidate entry (pf_cand): {x0, x1, slot | PFCF_*}; x0 = $FF ends the list
PFC_STRIDE      EQU 3
PFCF_SLOT       EQU $0F
PFCF_LADDER_BIT EQU 4
PFCF_LADDER     EQU 1 << PFCF_LADDER_BIT ; mid-ladder: absorbs
PFCF_REFL       EQU $20                 ; reflects the projectile's type
PFCF_DONE_BIT   EQU 6                   ; struck / tested in the current pass
PFCF_DEAD_BIT   EQU 7                   ; struck dead this cast: DONE for good
PFR_EDGE_BIT    EQU 2                   ; PF_ROWF bits (bit 0 = TF_SOLID)
PFR_BODY1       EQU 8                   ; bits 3-7: the count of candidates not DONE
PFR_BODYM       EQU $F8
                                        ; on the col (pf_cands +1, pf_bdone -1,
                                        ; pf_reverse +1 back; <= P_MAX_ENT < 32)
                ASSERT P_MAX_ENT * PFR_BODY1 + 7 <= 255
PFP_MID         EQU 1                   ; pf_part: the accept's walk parked mid-way
PFP_DONE        EQU 2                   ;   ... stopped (result + FX at the release)
PF_PRE_HITS     EQU 8                   ; strikes the accept walks (proj_part; ~3.5k T each)
PF_NOLIM        EQU $7F                 ; no budget (> PF_MAXREV + 1 passes x P_MAX_ENT;
                                        ; .walk parks at 0 or below: bit 7)
                ASSERT (PF_MAXREV + 1) * P_MAX_ENT < PF_NOLIM
PFB_NONE        EQU 0                   ; pf_bodies results
PFB_REFLECT     EQU 1
PFB_STOP        EQU 2
                ASSERT P_MAX_ENT <= PFCF_SLOT + 1

;------------------------------------------------------------------------------
; proj_fire — resolve a projectile at cast time and start its FX.
; In : IX = caster (active, CUR_ROOM, standing), facing = EF_LEFT; LIVE_LIST
;      current (build_live: try_player_turn builds it at the hero's turn start);
;      A = ability ABL_* with a projectile (Spark .. Lightning, ABL_DAGGER,
;      ABL_BOW: its ab_def row gives type, frames, speed, flags, to-hit);
;      HL = its 6-B rank row (RK_* layout: CAST_ROW, an ab_rank row or
;      an ab_ammo row; RK_MP is not read); E = FXD_DELAY (ticks before the
;      projectile appears: the cast frames, D3-7).
; Out: L = pf_stop (PFS_*); pf_col = impact col; pf_tgt = first body that
;      lost the hit roll / took the spell ($FF none), pf_lost = its HP lost;
;      pf_miss = first body that won the hit roll (missiles; $FF none; T7);
;      pf_itick = impact tick (E_REACTAT units: TURN_TICK-based, D3-7);
;      pf_desc = the FX descriptor
;      (started: fx_start; dropped if 3 tracks + 2 queued are busy).
;      IX = caster. MP / ammo are the caller's (D3-7).
; RNG (prototype §6.2 order): per body struck, [d20 (missiles)], 1dN, then
; deal_hit's effect chance; then the burst's 1dN per burst body.
; Clobbers: all but IX (IY untouched).
; Entries (D3-8e): proj_fire = proj_prep (set-up + pf_cands, ~10k T) then the
; walk; the game splits it: proj_part on the accept (input) tick = proj_prep +
; the walk's first PF_PRE_HITS strikes, proj_go on the release (fire) tick =
; the rest + the result + the FX (rank3.asm proj_pre / proj_rel).
; Cost (measured, contended bank-3 code): ~10k T set-up + ~0.25k per run of
; plain cells + per strike ~3.5k (deal_hit's messages ~4k more each): typical
; casts 10-30k T; the ROOM_CAP worst (Lightning ping-pong through a reflector
; stack, 16 strikes) ~90k one-shot (tests/proj3.py P11; the old code ~99k).
;------------------------------------------------------------------------------
proj_prep:
                ld   (pf_abl), a
                push hl
                ld   hl, pf_tgt                ; pf_tgt, pf_stopper = $FF
                ld   b, PF_FFN
.f:             ld   (hl), $FF
                inc  hl
                djnz .f
                ld   b, PF_ZN                  ; pf_fxrow, pf_lost .. pf_desc = 0
                xor  a
.z:             ld   (hl), a
                inc  hl
                djnz .z
                ld   a, e
                ld   (pf_desc + FXD_DELAY), a
                pop  hl
                inc  hl                        ; RK_RANGE (RK_MP is the caller's)
                ld   de, pf_left
                ld   bc, 5
                ldir                           ; range, die, bonus, bounces, effect
                ASSERT RK_RANGE == 1 && RK_DIE == 2 && RK_BONUS == 3 && RK_BOUNCES == 4 && RK_EFFECT == 5
                ; --- ab_def row: type, frames, speed, flags, to-hit ---
                ld   a, (pf_abl)
                cp   ABL_LIGHTNING + 1         ; STAFF-BONUS: a damaging hero spell: the worn
                jr   nc, .nsb                  ; Rune / Bone staff adds +1 / +2 to the spell's
                ld   hl, WORN + WS_WEAPON * IR_STRIDE + IR_TYPE ; flat bonus (after the dice, before
                ld   a, (hl)                   ; DEF / resist; deal_hit; min 1 there). Direct hit
                sub  IT_W_RUNE                 ; only (not the Firebolt burst); no state.
                cp   2                         ; RUNE -> 0, BONE -> 1, else >= 2 (wraps high)
                jr   nc, .nsb2
                inc  a
                ld   hl, pf_bonus
                add  a, (hl)
                ld   (hl), a
.nsb2:          ld   a, (pf_abl)
.nsb:           ld   l, a
                add  a, a
                add  a, a
                add  a, l
                add  a, a                      ; * ABD_STRIDE
                ld   e, a
                ld   d, 0
                ld   hl, ab_def
                add  hl, de
                ASSERT IT_W_BONE == IT_W_RUNE + 1 && WS_WEAPON == 0
                inc  hl                        ; (ABD_DTY: pf_dhc_tab has it)
                ld   de, pf_desc + FXD_FIDA
                ld   bc, 4
                ldir                           ; ABD_PF1..ABD_IF2 -> FXD_FIDA..FXD_IMPB
                ; FXD_ATTR: 0 = the frame's own (fx_meta) except the thrown dagger, which flies $47 (fx_meta's
                ; dagger_spin is the monsters' ROCK_ATTR; ABD_AT1/2 are not read here: firebolt alternates per frame)
                ld   a, (pf_desc + FXD_FIDA)
                cp   FID_dagger_spin1
                ld   a, 0
                jr   nz, .at
                ld   a, THROW_ATTR
.at:            ld   (pf_desc + FXD_ATTR), a
                inc  hl
                inc  hl                        ; ABD_SPEED: 8 / 16 px
                ld   a, (hl)
                and  16
                rrca
                rrca
                rrca                           ; 16 -> FXDF_FAST
                ld   (pf_desc + FXD_FLAGS), a
                inc  hl
                ld   a, (hl)                   ; ABD_FLAGS
                ld   (pf_aflg), a
                inc  hl
                ld   a, (hl)                   ; ABD_HIT
                ld   (pf_hitm), a
                ASSERT ABD_DTY == 0 && ABD_PF1 == 1 && ABD_IF2 == 4 && ABD_SPEED == 7 && ABD_FLAGS == 8 && ABD_HIT == 9
                ASSERT ABD_STRIDE == 10 && FXD_FIDA == 0 && FXD_IMPB == 3 && FXDF_FAST == 16 >> 3
                ld   a, (pf_abl)               ; deal_hit C (pf_dhc_tab)
                ld   e, a
                ld   d, 0
                ld   hl, pf_dhc_tab
                add  hl, de
                ld   a, (hl)
                ld   (pf_dhc), a
                ld   a, PF_IMPT
                ld   (pf_desc + FXD_IMPT), a
                ld   a, (pf_die)               ; D3-8e: rng_mod's mask once a cast (the
                ld   c, a                      ; strikes call rng_mod.again: ~60 T a hit)
                dec  a
                ld   b, a
                srl  a
                or   b
                ld   b, a
                rrca
                rrca
                and  $3F
                or   b
                ld   b, a
                rrca
                rrca
                rrca
                rrca
                and  $0F
                or   b
                ld   b, a
                ld   (pf_dmc), bc
                ; --- caster: slot, line rows, flight row, start col, dir ---
                call ix_slot
                ld   (pf_cslot), a
                call get_box                   ; C x, B y, D w, E h
                ld   a, b
                ld   (pf_ly0), a
                add  a, PF_ROW_DY
                ld   (pf_row0), a
                ld   (pf_desc + FXD_ROW), a    ; (pf_row: the first body's row)
                ld   a, b
                add  a, e
                dec  a
                ld   (pf_ly1), a
                ld   a, $FF                    ; left: from col x
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   nz, .dir
                ld   a, c                      ; right: from col x + w - 1
                add  a, d
                dec  a
                ld   c, a
                ld   a, 1
.dir:           ld   (pf_dir), a
                ld   a, c
                ld   (pf_pos), a
                ld   a, (pf_abl)
                inc  a
                ld   (pf_prep), a              ; prepared for this ability (proj_rel)
                jp   pf_cands

; proj_part — D3-8e, the accept's share (far3 proj_pre, input tick): IX, A,
; HL, E as proj_fire, E = the ticks to the release (FXD_DELAY there). The
; set-up and the candidates, then the walk until it struck PF_PRE_HITS
; bodies (it parks at a .walk boundary: pf_part = PFP_MID) or stopped (the
; result and the FX wait: pf_part = PFP_DONE). Nothing moves before the
; release (the monster phase is deferred), so the state stays valid; the
; strikes' HP / status / lines change in the logic before the projectile
; shows (their E_REACTAT is the same: pf_tb), but nothing visible does: the
; panel waits for COMBAT_NOT_BEFORE (act_begin, from pf_ftick) and render
; holds a struck body's attr until its reaction (D3-8e2). The release
; (proj_rel -> proj_go) runs the rest. Splits a Lightning through 4 stacked
; bodies (~16 strikes, ~80k T) between the light input tick and the fire
; tick, whose render can be ~70k T on its own.  Clobbers: all but IX
proj_part:
                call proj_prep                 ; (pf_prep = A + 1, pf_part = 0)
                ld   a, PF_PRE_HITS
                ld   (pf_slim), a
                ld   a, 1
                ld   (pf_acc), a
                jr   proj_tb

proj_fire:
                call proj_prep
                ld   a, PF_NOLIM
                jr   proj_run

; proj_go — the release of a cast proj_prep / proj_part set up (proj_rel):
; E = FXD_DELAY (0: the projectile appears now). In / Out as proj_fire.
proj_go:
                ld   a, e
                ld   (pf_desc + FXD_DELAY), a
                ld   a, PF_NOLIM
proj_run:
                ld   (pf_slim), a              ; (no strike budget)
                xor  a
                ld   (pf_prep), a              ; (used up: a stale set-up never walks)
                ld   (pf_acc), a
proj_tb:
                ld   a, (TURN_TICK)            ; pf_tick's base, per entry (TURN_TICK +
                ld   hl, pf_desc + FXD_DELAY   ; FXD_DELAY is the release tick either
                add  a, (hl)                   ; way: the same E_REACTAT on both ticks)
                inc  a
                ld   (pf_tb), a
                ld   a, (pf_part)
                cp   PFP_DONE
                jp   z, .end                   ; the accept's walk already stopped
                ;------------------------------------------------------------
                ; the walk
                ;------------------------------------------------------------
.walk:          ld   a, (pf_slim)            ; the accept's strike budget spent (0, or
                dec  a                         ; below: a col's K bodies are struck in
                cp   PF_NOLIM                  ; one pf_bodies call) -> park
                jp   nc, .park
                ld   b, PFS_RANGE
                ld   a, (pf_left)
                or   a
                jp   z, .stop
                ; fast-forward: E = the plain cells ahead (PF_ROWF 0: no solid
                ; tile, not an edge, no candidate), at most the range left
                ld   b, a
                ld   a, (pf_dir)
                ld   c, a
                ld   a, (pf_pos)
                or   PF_ROWF & $FF
                ld   l, a
                ld   h, PF_ROWF >> 8
                ld   e, 0
.ff:            ld   a, l                      ; ~50 T a plain cell
                add  a, c                      ; (edges are flagged: L stays in the row)
                ld   l, a
                ld   a, (hl)
                or   a
                jr   nz, .ev
                inc  e
                djnz .ff
.ev:            inc  e
                dec  e
                jr   z, .cell                  ; A = flags, L = the event cell
                ; enter the E plain cells in bulk = pf_enter E times (the first
                ; one the FX anchor if nothing was entered yet), then decide the
                ; cell after them straight away (D3-8e: no pf_enter call and no
                ; re-read of the walk state: ~0.6k -> ~0.35k T a run)
                push hl                        ; the cell after the run (the event, or
                ld   b, e                      ; the last cell when the range ran out)
                ld   hl, pf_left
                ld   a, (hl)
                sub  b
                ld   (hl), a                   ; range -= E (E <= range: the .ff bound)
                ld   a, (pf_desc + FXD_NSEG)
                or   a
                jr   nz, .more
                inc  a                         ; the first cell entered: NSEG 1, SEGS[0]
                ld   (pf_desc + FXD_NSEG), a   ; = 0 (zeroed), the anchor + facing
                ld   a, (pf_pos)
                add  a, c
                ld   (pf_desc + FXD_COL), a
                ld   a, c
                rlca
                and  FXDF_LEFT                 ; dir $FF -> left
                ld   hl, pf_desc + FXD_FLAGS
                or   (hl)
                ld   (hl), a
                dec  b                         ; the other E - 1 are moves
                ld   a, 1
.more:          add  a, (pf_desc + FXD_SEGS - 1) & $FF
                ld   l, a
                ld   h, PF_RAM >> 8
                ld   a, (hl)
                add  a, b
                ld   (hl), a                   ; SEGS[NSEG - 1] += moves
                ld   hl, pf_moves
                ld   a, (hl)
                add  a, b
                ld   (hl), a                   ; moves += moves
                ld   a, c                      ; pos += E * dir (dir = +1 / $FF)
                rla
                ld   a, (pf_pos)
                jr   c, .pl
                add  a, e
                jr   .ps
.pl:            sub  e
.ps:            ld   (pf_pos), a
                pop  hl
                ld   b, PFS_RANGE
                ld   a, (pf_left)
                or   a
                jp   z, .stop                  ; the run used the range up
                ld   a, (hl)                   ; else L = the event cell (flags not 0)
                ASSERT ((pf_desc + FXD_SEGS + FXD_SEGMAX - 1) >> 8) == (PF_RAM >> 8)
                ; the next cell decides: A = its PF_ROWF flags, L = its col
.cell:          rrca
                jr   c, .solid                 ; (solid edge: a wall)
                ld   a, l
                and  ROOM_COLS - 1
                ld   c, a                      ; C = next col
                ld   (pf_next), a
                or   a
                jr   z, .exit
                cp   ROOM_COLS - 1
                jr   z, .exit
                ld   a, (pf_desc + FXD_NSEG)   ; move index of this cell (0 =
                or   a                         ; the first cell entered)
                jr   z, .m0
                ld   a, (pf_moves)
                inc  a
.m0:            ld   (pf_mnext), a
                call pf_bodies                 ; A = PFB_*
                cp   PFB_REFLECT
                jr   z, .refl
                push af
                call pf_enter
                pop  af
                or   a
                jp   z, .walk
                jr   .end                      ; PFB_STOP: pf_stop set
.exit:          call pf_enter
                ld   b, PFS_EXIT
                jr   .stop
.solid:         ld   b, PFS_WALL
                ld   hl, pf_bnc
                ld   a, (hl)
                or   a
                jr   z, .stop
                dec  (hl)
.refl:          ld   b, PFS_LOOP
                ld   a, (pf_rev)
                cp   PF_MAXREV
                jr   nc, .stop
                call pf_reverse
                jp   .walk
.stop:          ld   a, b
                ld   (pf_stop), a
                ;------------------------------------------------------------
                ; the result: FX descriptor, burst, the FX
                ;------------------------------------------------------------
.end:           ld   a, (pf_acc)
                or   a
                jr   nz, .pdone                ; the accept: result + FX at the release
                ld   a, (pf_pos)
                ld   (pf_col), a
                ld   a, (pf_desc + FXD_NSEG)
                or   a
                jr   nz, .ent
                ld   a, (pf_pos)               ; nothing entered (point-blank):
                ld   (pf_next), a              ; an impact-only FX on the
                call pf_enter                  ; caster's front col
                ld   a, FX_NONE
                ld   (pf_desc + FXD_FIDA), a
                ld   (pf_desc + FXD_FIDB), a
.ent:           ld   a, (pf_stop)
                cp   PFS_EXIT
                jr   nz, .imp
                ld   a, FX_NONE
                ld   (pf_desc + FXD_IMPA), a
.imp:           ld   a, (pf_moves)
                call pf_tick
                ld   (pf_itick), a
                ld   a, (pf_aflg)
                and  ABF_BURST
                call nz, pf_burst
                push ix
                ld   hl, pf_desc
                call fx_start                  ; (dropped if all busy: logic stands)
                pop  ix
                ld   a, (pf_stop)
                ld   l, a
                ret
.park:          ld   a, PFP_MID
                jr   .pst
.pdone:         ld   a, PFP_DONE
.pst:           ld   (pf_part), a
                ret

;------------------------------------------------------------------------------
; pf_cands — PF_ROWF (the flight row: TF_SOLID, edges, candidate cols);
; pf_cand = the bodies in line (LIVE_LIST as built at turn start, not dying, rows
; overlapping pf_ly0..pf_ly1), slot order; flags: mid-ladder, reflects the
; projectile's type. Terminated by x0 = $FF. x1 is clamped to col 31 (a
; body poked / straddling past the edge can never push a count past
; PF_ROWF's page end into PF_RAM's start).
; Clobbers: A, BC, DE, HL (IX kept).  ~2.4k T + ~1k per body in line (contended)
;------------------------------------------------------------------------------
pf_cands:
                ld   a, (pf_row0)              ; PF_ROWF = TF_SOLID of the flight row
                ld   b, a
                ld   c, 0
                call cell_addr                 ; HL = ROOM_MAP (row0, col 0)
                ld   bc, PF_ROWF
                ld   d, tile_flags >> 8
.r:             REPT 2                         ; 2 cells a pass (32 even: C wraps
                ld   a, (hl)                   ; on the 2nd inc): 53 T a cell
                add  a, tile_flags & $FF       ; (tile_flags ends on its page)
                ld   e, a
                ld   a, (de)
                and  TF_SOLID
                ld   (bc), a
                inc  l
                inc  c
                ENDR
                jr   nz, .r                    ; PF_ROWF ends its page
                ASSERT (ROOM_COLS & 1) == 0
                ld   hl, PF_ROWF               ; + the edge cols (exit or wall)
                set  PFR_EDGE_BIT, (hl)
                ld   l, (PF_ROWF + ROOM_COLS - 1) & $FF
                set  PFR_EDGE_BIT, (hl)
                ld   de, pf_cand
                ld   a, (LIVE_N)
                or   a
                jp   z, .end                   ; (jp: the x1 guard put .end out of jr range)
                push ix
                ld   b, a
                ld   hl, LIVE_LIST
.l:             push bc
                push hl
                ld   c, (hl)                   ; slot
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                bit  EF_DYING_BIT, (ix+E_FLAGS)
                jr   nz, .n
                inc  hl
                ld   b, (hl)                   ; B = w (LIVE_LIST's cached KT_BW / KT_BH)
                inc  hl
                ld   a, (pf_ly1)
                cp   (ix+E_Y)
                jr   c, .n                     ; top below the line
                ld   a, (hl)
                add  a, (ix+E_Y)
                dec  a                         ; bottom row
                ld   hl, pf_ly0
                cp   (hl)
                jr   c, .n                     ; bottom above the line
                ld   a, (ix+E_X)
                ld   (de), a                   ; x0
                inc  de
                add  a, b
                dec  a
                cp   ROOM_COLS                 ; guard: x1 > 31 would run .o / pf_bdone /
                jr   c, .x1                    ; pf_reverse past PF_ROWF's page end into
                ld   a, ROOM_COLS              ; PF_RAM: clamp to col 31 (B = 32 - x0; E_X
                                               ; <= 31 is the room invariant, x0 kept)
                sub  (ix+E_X)
                ld   b, a
                ld   a, ROOM_COLS - 1
.x1:            ld   (de), a                   ; x1
                inc  de
                sub  b
                inc  a
                or   PF_ROWF & $FF             ; PF_ROWF x0..x1: a candidate
                ld   l, a
                ld   h, PF_ROWF >> 8
                ld   a, (pf_cslot)             ; D3-8e: the caster starts DONE and not
                cp   c                         ; counted (a target only after the first
                jr   nz, .o                    ; reversal: pf_reverse counts it back) —
                set  PFCF_DONE_BIT, c          ; no caster test per body struck, and the
                jr   .cl                       ; first pass fast-forwards over its cols
.o:             ld   a, (hl)                   ; + 1 body on the col (pf_bdone: - 1)
                add  a, PFR_BODY1
                ld   (hl), a
                inc  l
                djnz .o
.cl:            call on_ladder                 ; Z = mid-ladder
                ld   a, c
                jr   nz, .nl
                or   PFCF_LADDER
.nl:            ld   c, a
                ld   a, (pf_dhc)
                and  DH_TYPE
                call pf_rsp                    ; (A, B, HL)
                cp   RSP_X
                ld   a, c
                jr   nz, .nx
                or   PFCF_REFL
.nx:            ld   (de), a                   ; slot | flags
                inc  de
.n:             pop  hl
                ld   a, l
                add  a, 5                      ; LIVE_LIST entry (one page)
                ld   l, a
                pop  bc
                djnz .l
                pop  ix
.end:           ld   a, $FF
                ld   (de), a
                ret
                ASSERT (LIVE_LIST & $FF) + 5 * P_MAX_ENT <= 256

; pf_rsp — A = IX's response (RSP_*) to type A (hero: HERO_RES, monster: its
; kx_tab row).  Clobbers: A, B, HL
; rsp_hl — A = the response of RES record HL to type B: (RES_B(t / 4) >>
; 2 (t % 4)) & 3 (deal_hit too).  Clobbers: A, B, HL
pf_rsp:
                ld   b, a
                ld   hl, HERO_RES
                ld   a, (ix+E_FLAGS)
                and  EF_PLAYER
                jr   nz, rsp_hl
                ld   a, (ix+E_KIND)            ; kx_tab + kind * 8 (one page)
                add  a, a                      ; x 8 (KX_STRIDE; kind < K_MAX = 32)
                add  a, a
                add  a, a
                add  a, kx_tab & $FF
                ld   l, a
                ld   h, kx_tab >> 8
rsp_hl:         ld   a, b
                cp   4
                jr   c, .b0
                inc  hl                        ; DRAIN / DARK: RES_B1
.b0:            and  3                         ; k = t % 4: A = (byte >> 2k) & 3
                ld   b, a
                ld   a, (hl)
                jr   z, .x                     ; k 0 (ld keeps the flags)
                djnz .k2
                rrca                           ; k 1: >> 2
                rrca
                jr   .x
.k2:            djnz .k3
                rrca                           ; k 2: >> 4
                rrca
                rrca
                rrca
                jr   .x
.k3:            rlca                           ; k 3: >> 6 = rlca x 2
                rlca
.x:             and  3                         ; (was a djnz loop: ~20 T per k saved)
                ret
                ASSERT KX_RES == 0 && RES_B0 == 0 && RES_B1 == 1

;------------------------------------------------------------------------------
; pf_bodies — the candidates containing col pf_next, in list order, not yet
; done this pass (the caster is DONE until the first reversal: pf_cands). A body struck dead (pf_strike
; on the pierce path) is marked PFCF_DEAD: it stays DONE through every later
; reversal (pf_reverse skips it), so its cols read plain and fast-forward.
; Stops scanning once the col's PF_ROWF count of bodies not DONE (K, read on
; entry) is used up (D3-8 review 2 budget: the scan was ~0.5k T a call).
; Out: A = PFB_NONE (none, missed, pierced) / PFB_REFLECT / PFB_STOP (pf_stop
; = PFS_BODY or PFS_ABSORB).  Clobbers: all but IX
; ~75 T a candidate passed + ~0.4k a body processed (+ pf_strike), contended
;------------------------------------------------------------------------------
pf_bodies:
                ld   a, (pf_next)
                ld   c, a                      ; C = col
                or   PF_ROWF & $FF
                ld   l, a
                ld   h, PF_ROWF >> 8
                ld   a, (hl)
                rrca
                rrca
                rrca
                and  PFR_BODYM >> 3
                ld   b, a                      ; B = K (>= 1: .cell's flags are not 0,
                ld   hl, pf_cand               ; and not solid / edge)
.l:             ld   a, (hl)                   ; x0
                inc  a
                jr   z, .none                  ; ($FF: only with a broken count)
                ld   a, c
                cp   (hl)
                inc  hl
                jr   c, .s1                    ; col < x0
                ld   a, (hl)
                cp   c
                jr   c, .s1                    ; x1 < col
                inc  hl                        ; HL -> slot | flags
                bit  PFCF_DONE_BIT, (hl)
                jr   z, .bd                    ; (the caster is DONE until the first
.s2:            inc  hl                        ; reversal: pf_cands)
                jr   .l
.s1:            inc  hl
                inc  hl
                jr   .l
.bd:            dec  b                         ; one of the K
                push bc
                set  PFCF_DONE_BIT, (hl)
                push hl                        ; pf_bdone (inline, D3-8e): its body count
                dec  hl                        ; off its cols, so a col only DONE bodies
                ld   a, (hl)                   ; cover reads 0 (plain) and the walk's
                dec  hl                        ; fast-forward skips it (D3-8 budget
                ld   e, (hl)                   ; review: ~0.15k T a DONE vs ~0.9k a
                sub  e                         ; pf_bodies call on each of its cells)
                inc  a
                ld   b, a                      ; w = x1 - x0 + 1
                ld   a, e
                or   PF_ROWF & $FF
                ld   l, a
                ld   h, PF_ROWF >> 8
.bdc:           ld   a, (hl)
                sub  PFR_BODY1
                ld   (hl), a
                inc  l
                djnz .bdc
                pop  hl
                ld   a, (hl)
                and  PFCF_REFL | PFCF_LADDER
                jr   z, .hit
                pop  bc                        ; (a return: K no longer needed)
                ld   c, a                      ; C = flags
                ld   a, (hl)
                and  PFCF_SLOT
                ld   (pf_cur), a
                push bc
                call pf_row                    ; the FX flies at it
                pop  bc
                bit  PFCF_LADDER_BIT, c        ; ladder wins over reflect
                ld   a, PFB_REFLECT
                ret  z
                ld   a, (pf_cur)
                ld   (pf_stopper), a
                ld   a, PFS_ABSORB
                ld   (pf_stop), a
                ld   a, PFB_STOP
                ret
.hit:           push hl
                ld   a, (hl)
                and  PFCF_SLOT
                call pf_strike                 ; A = PFB_NONE / PFB_STOP, CF = struck dead
                pop  hl
                jr   c, .dead
                or   a
                jr   nz, .ret                  ; (pop bc keeps A)
.nx:            pop  bc
                inc  b
                dec  b
                jr   nz, .s2                   ; more of the K left
.none:          xor  a                         ; PFB_NONE
                ret
.ret:           pop  bc
                ret
.dead:          set  PFCF_DEAD_BIT, (hl)       ; pierced dead: DONE for good (pf_reverse)
                jr   .nx
                ASSERT PFB_NONE == 0

; pf_nin — from candidate HL (its x0) on, the next one with x0 - D <= C <=
; x1 + D (D = 0 / 1). Out: CF = 0: HL -> its slot byte (resume at HL + 1);
; CF = 1: end of the list.  Clobbers: A
pf_nin:
.l:             ld   a, (hl)
                cp   $FF
                scf
                ret  z
                ld   a, c
                add  a, d
                cp   (hl)                      ; col + D - x0
                inc  hl
                jr   c, .s1
                ld   a, (hl)
                add  a, d
                cp   c                         ; x1 + D - col
                inc  hl
                ret  nc
                inc  hl
                jr   .l
.s1:            inc  hl
                inc  hl
                jr   .l

;------------------------------------------------------------------------------
; pf_strike — A = slot struck (IX = caster): [hit_roll], 1dN + bonus, deal_hit,
; reaction at the FX tick, first-target record; pierce: go on.
; Out: A = PFB_NONE (missed / pierced) / PFB_STOP; CF = 1: pierced and struck
; dead (D3-8e: read through dh_tix, no ent_ix).  Clobbers: all but IX
;------------------------------------------------------------------------------
pf_strike:
                ld   (pf_cur), a
                ld   hl, pf_slim               ; one strike off the accept's budget
                dec  (hl)                      ; (PF_NOLIM never reaches 0)
                ld   a, (pf_aflg)
                and  ABF_SPELL
                jr   nz, .hit
                ld   a, (pf_hitm)
                ld   b, a
                ld   a, (pf_cur)
                call hit_roll                  ; F1 (one d20); Z = miss
                jr   nz, .hit
                ; T7: a miss flies on (game.md §6 "Logic"), but visibly: the first
                ; body missed -> pf_miss (the "MISSES THE <kind>" line), and every
                ; missed body dodges (RC_DODGE: the ATTR_MISS flash) on the tick
                ; the FX passes its first col
                ld   hl, pf_miss
                ld   a, (hl)
                inc  a
                jr   nz, .m1
                ld   a, (pf_cur)
                ld   (hl), a
.m1:            ld   a, (pf_mnext)
                call pf_tick
                ld   b, a
                ld   a, (pf_cur)
                call pf_dodge
                xor  a                         ; PFB_NONE: flies on
                ret
.hit:           ld   a, (pf_fxrow)             ; pf_row's once-test inline (the FX row
                or   a                         ; is taken from the first body only)
                ld   a, (pf_cur)
                call z, pf_row
                ld   a, (pf_mnext)             ; D3-8e: the impact tick first, so
                call pf_tick                   ; deal_hit's set_reaction_at takes it
                ld   (dh_rtick), a             ; (>= 1) instead of the attacker's IMPACT
                ld   bc, (pf_dmc)              ; C = die, B = its mask (proj_fire)
                call rng_mod.again             ; 1dN - 1 (rng_mod without the mask)
                inc  a
                ld   hl, pf_bonus
                add  a, (hl)
                ld   b, a                      ; 1dN + bonus
                ld   a, (pf_dhc)
                ld   c, a
                ld   a, (pf_cslot)
                ld   hl, pf_cur
                cp   (hl)
                jr   nz, .nh
                res  DH_HEAL_BIT, c            ; Drain on its own caster: no heal (§6)
.nh:            ld   a, (pf_eff)
                ld   e, a
                ld   a, (hl)
                call deal_hit                  ; L = HP lost, IX = caster, dh_tix = target
                dec  h                         ; 3F-T6: H = 1 parried -> pf_lost $FF (ammo_fire prints the
                jr   nz, .npy                  ; PARRIES line; nothing else reads pf_lost of a PHYS shot)
                ld   l, h
                dec  l
.npy:           ld   a, (dh_rtick)             ; B = the impact tick
                ld   b, a
                ld   a, (pf_tgt)
                inc  a
                jr   nz, .nf
                ld   a, (pf_cur)
                ld   (pf_tgt), a
                ld   h, b                      ; D3-8e2: pf_lost = L, pf_ftick = the first
                ld   (pf_lost), hl             ; impact tick (act_begin's COMBAT_NB; 0 B)
.nf:            ld   hl, (dh_tix)              ; pf_react without ent_ix: a pending
                                               ; reaction plays at the impact tick (also
                                               ; the I / X path, which sets none)
                xor  a
                ld   (dh_rtick), a             ; back to the attacker's IMPACT rule
                ld   a, l
                or   E_REACT
                ld   l, a
                ld   a, (hl)
                or   a
                jr   z, .nr
                inc  l
                ld   (hl), b                   ; E_REACTAT
.nr:            ld   a, (pf_aflg)
                and  ABF_PIERCE                ; (CF = 0)
                jr   z, .stop
                ld   a, l                      ; pierce on: struck dead -> CF = 1
                and  ~(P_ENT_STRIDE - 1) & $FF
                or   E_FLAGS
                ld   l, a
                xor  a                         ; PFB_NONE
                bit  EF_DYING_BIT, (hl)
                ret  z
                scf
                ret
                ASSERT E_REACTAT == E_REACT + 1 && P_ENT_STRIDE == 32 && (P_ENTITIES & 31) == 0
.stop:          ld   a, (pf_cur)
                ld   (pf_stopper), a
                ld   a, PFS_BODY
                ld   (pf_stop), a
                ld   a, PFB_STOP
                ret

;------------------------------------------------------------------------------
; pf_burst — Firebolt: candidates within 1 col of pf_col (not the stopper; the
; caster unless RKE_SPARE) take 1d(RK_EFFECT & 15) FIRE (no DEF); reaction at
; pf_itick. Not after PFS_EXIT / PFS_ABSORB (D3-7 T4).  Clobbers: all but IX
;------------------------------------------------------------------------------
pf_burst:
                ld   a, (pf_stop)
                sub  PFS_ABSORB                ; no burst after an absorb (game.md
                cp   2                         ; §6 "Logic", designer) or an exit
                ret  c
                ASSERT PFS_EXIT == PFS_ABSORB + 1 && PFS_LOOP > PFS_EXIT && PFS_WALL < PFS_ABSORB && PFS_BODY < PFS_ABSORB
                ld   hl, pf_cand
.l:             ld   a, (pf_col)
                ld   c, a
                ld   d, 1
                call pf_nin
                ret  c
                ld   a, (hl)
                and  PFCF_SLOT
                ld   b, a
                ld   a, (pf_stopper)
                cp   b
                jr   z, .n1
                ld   a, (pf_cslot)
                cp   b
                jr   nz, .ok
                ld   a, (pf_eff)
                and  RKE_SPARE
                jr   nz, .n1
.ok:            push hl
                ld   a, b
                ld   (pf_cur), a
                ld   a, (pf_eff)
                and  $0F
                ld   c, a
                call rng_mod
                inc  a
                ld   b, a
                ld   c, DTY_FIRE | DH_NODEF
                ld   a, (pf_cur)
                call deal_hit
                ld   a, l                      ; LOG-FIX P2a: the caster in the burst, hurt (L = HP lost:
                or   a                         ; an immune hero got UNAFFECTED only)
                jr   z, .nb
                ld   a, (pf_cur)
                or   a
                jr   nz, .nb
                call log_room                  ; (the result line is never the one dropped)
                ld   a, TX_SPL_BURN_SELF
                call msg_push_d                ; "THE BURST SCORCHES YOU -D" (LN_VAL = this deal_hit's L;
                                               ; AF, BC, DE, HL)
.nb:
                ld   a, (pf_itick)
                ld   b, a
                ld   a, (pf_cur)
                call pf_react
                pop  hl
.n1:            inc  hl
                jr   .l

;------------------------------------------------------------------------------
; small helpers
;------------------------------------------------------------------------------
; pf_enter — the projectile enters col pf_next: pf_pos, range - 1, the FX path
; (first cell: anchor + facing, 1 segment of 0; else one more move).
; Clobbers: A, HL
pf_enter:
                ld   a, (pf_next)
                ld   (pf_pos), a
                ld   hl, pf_left
                dec  (hl)
                ld   hl, pf_desc + FXD_NSEG
                ld   a, (hl)
                or   a
                jr   nz, .more
                inc  (hl)                      ; NSEG 1, SEGS[0] = 0 (zeroed)
                ld   a, (pf_next)
                ld   (pf_desc + FXD_COL), a
                ld   a, (pf_dir)
                rlca
                and  FXDF_LEFT                 ; $FF -> left
                ld   hl, pf_desc + FXD_FLAGS
                or   (hl)
                ld   (hl), a
                ret
.more:          ld   hl, pf_moves
                inc  (hl)
                add  a, (pf_desc + FXD_SEGS - 1) & $FF
                ld   l, a                      ; (PF_RAM: one page, H kept)
                inc  (hl)                      ; SEGS[NSEG - 1] += 1
                ret
                ASSERT (pf_moves >> 8) == (PF_RAM >> 8) && ((pf_desc + FXD_LEN) >> 8) == (PF_RAM >> 8)
                ASSERT FXDF_LEFT == 1

; pf_reverse — a bounce / reflection: direction flips, the caster becomes a
; target, a new pass (marks cleared: a DONE body counts on its PF_ROWF cols
; again; a PFCF_DEAD one stays DONE), a new FX segment once a cell was entered.
; Clobbers: A, B, E, HL
pf_reverse:
                ld   hl, pf_rev
                inc  (hl)
                ld   a, (pf_dir)
                neg
                ld   (pf_dir), a
                ld   hl, pf_cand               ; (the caster, DONE since pf_cands, counts
                                               ; from here on: a target after a reversal)
.c:             ld   a, (hl)                   ; x0
                inc  a
                jr   z, .seg
                ld   e, (hl)
                inc  hl
                ld   a, (hl)                   ; x1
                inc  hl
                bit  PFCF_DONE_BIT, (hl)
                jr   z, .nd
                bit  PFCF_DEAD_BIT, (hl)
                jr   nz, .nd                   ; dead: DONE for good
                res  PFCF_DONE_BIT, (hl)
                push hl                        ; a DONE body counts on its cols again
                sub  e
                inc  a
                ld   b, a
                ld   a, e
                or   PF_ROWF & $FF
                ld   l, a
                ld   h, PF_ROWF >> 8
.a:             ld   a, (hl)
                add  a, PFR_BODY1
                ld   (hl), a
                inc  l
                djnz .a
                pop  hl
.nd:            inc  hl
                jr   .c
.seg:           ld   hl, pf_desc + FXD_NSEG
                ld   a, (hl)
                or   a
                ret  z                         ; nothing entered: no segment yet
                inc  (hl)
                ret

; pf_tick — A = move index -> A = TURN_TICK + FXD_DELAY + ceil(moves / speed)
; + 1 (the TURN_TICK on which the FX shows its impact there: fx_start counts
; from the next fx_tick, which runs on this TURN_TICK — D3-7: proj_fire also
; runs at a release tick f > 0, from the anim_gate hook before fx_tick).
; Clobbers: A, HL
pf_tick:
                ld   hl, pf_desc + FXD_FLAGS
                bit  FXDF_FAST_BIT, (hl)
                jr   z, .s
                inc  a
                srl  a
.s:             ld   hl, pf_tb                 ; TURN_TICK + FXD_DELAY + 1 (proj_go)
                add  a, (hl)
                ret

; pf_react — slot A: a pending reaction (deal_hit's HURT / DEATH) plays at
; tick B.  Clobbers: A, E
; pf_dodge — slot A missed by a missile (T7): RC_DODGE at tick B unless a
; reaction is already pending (a hit / death always wins: deal_hit's
; set_reaction_at overwrites a DODGE).  Clobbers: A, E
pf_react:
                push ix
                call ent_ix
                ld   a, (ix+E_REACT)
                or   a
                jr   z, pf_rx
pf_rat:         ld   (ix+E_REACTAT), b
pf_rx:          pop  ix
                ret
pf_dodge:
                push ix
                call ent_ix
                ld   a, (ix+E_REACT)
                or   a
                jr   nz, pf_rx
                ld   (ix+E_REACT), RC_DODGE
                jr   pf_rat

; pf_row — slot A: the FX row := its nearest row to pf_row0, once (the
; first body the projectile interacts with).  Clobbers: A, B, E, HL
pf_row:
                ld   b, a
                ld   hl, pf_fxrow
                ld   a, (hl)
                or   a
                ret  nz
                inc  (hl)
                ld   a, b
                call pf_rowof
                ld   (pf_desc + FXD_ROW), a
                ret

; pf_rowof — A = clamp(pf_row0, top, bottom) of slot A's body.
; Clobbers: A, E, HL
pf_rowof:
                push ix
                call ent_ix
                KFL    KT_BH
                add  a, (ix+E_Y)
                dec  a
                ld   e, a                      ; bottom
                ld   a, (pf_row0)
                cp   e
                jr   c, .lo
                ld   a, e
.lo:            cp   (ix+E_Y)
                jr   nc, .x
                ld   a, (ix+E_Y)
.x:             pop  ix
                ret

;------------------------------------------------------------------------------
; pf_dhc_tab — deal_hit C per ability ABL_* (game.md §6.0-6.3): the type
; (= ab_def ABD_DTY), DH_NODEF for spells (§6.1 "dmg ignores DEF"), DH_HEAL
; for Drain Life, the on-hit effect (Spark CONFUSED, Frost FROZEN; params =
; RK_EFFECT). Melee rows 0 (no projectile). tests/proj3.py checks it vs ab_def.
;------------------------------------------------------------------------------
pf_dhc_tab:     DB   DTY_SHOCK | DH_NODEF | (EFX_CONFUSED << DH_EFX_SHIFT)  ; Spark
                DB   DTY_FIRE | DH_NODEF                                    ; Firebolt
                DB   DTY_COLD | DH_NODEF | (EFX_FROZEN << DH_EFX_SHIFT)    ; Frost Shard
                DB   DTY_DRAIN | DH_NODEF | DH_HEAL                         ; Drain Life
                DB   DTY_SHOCK | DH_NODEF                                   ; Lightning
                DB   0, 0                                                   ; Power Strike, Whirlwind
                DB   DTY_PHYS                                               ; dagger
                DB   DTY_PHYS                                               ; bow
                ASSERT $ - pf_dhc_tab == ABL_COUNT
pf_prep:        DB   0                         ; D3-8e: ABL_* + 1 set up by proj_prep (the
                                               ; accept), 0 none: proj_rel walks only then
                ASSERT ABL_SPARK == 0 && ABL_FIREBOLT == 1 && ABL_FROST == 2 && ABL_DRAIN == 3 && ABL_LIGHTNING == 4 && ABL_DAGGER == 7 && ABL_BOW == 8

;------------------------------------------------------------------------------
; proj_fire scratch + results: runtime RAM PF_RAM (bank 5, the dead BASIC area,
; not on tape; combat_defs.asm / docs/memory-map.md). Not re-entrant.
; pf_left..pf_eff mirror RK_RANGE..RK_EFFECT (one LDIR).
;------------------------------------------------------------------------------
pf_left         EQU PF_RAM                      ; range left (cells)
pf_die          EQU pf_left + 1
pf_bonus        EQU pf_die + 1
pf_bnc          EQU pf_bonus + 1                ; wall bounces left
pf_eff          EQU pf_bnc + 1                  ; RK_EFFECT
pf_abl          EQU pf_eff + 1
pf_aflg         EQU pf_abl + 1                  ; ab_def ABF_*
pf_hitm         EQU pf_aflg + 1                 ; to-hit modifier (missiles)
pf_dhc          EQU pf_hitm + 1                 ; deal_hit C
pf_cslot        EQU pf_dhc + 1
pf_ly0          EQU pf_cslot + 1                ; caster rows (the line)
pf_ly1          EQU pf_ly0 + 1
pf_row0         EQU pf_ly1 + 1                  ; flight row
pf_dir          EQU pf_row0 + 1                 ; +1 / $FF
pf_pos          EQU pf_dir + 1                  ; current col
pf_next         EQU pf_pos + 1
pf_mnext        EQU pf_next + 1                 ; move index of pf_next
pf_cur          EQU pf_mnext + 1
pf_dmc          EQU pf_cur + 1                  ; D3-8e: word C = die, B = its rng mask
pf_tb           EQU pf_dmc + 2                  ; D3-8e: pf_tick's base (proj_go)
pf_slim         EQU pf_tb + 1                   ; D3-8e: strikes left before proj_part parks
pf_acc          EQU pf_slim + 1                 ; D3-8e: 1 = proj_part (the accept) walking
pf_stop         EQU pf_acc + 1                  ; results: PFS_*
pf_col          EQU pf_stop + 1                 ;   impact col
pf_itick        EQU pf_col + 1                  ;   impact tick
pf_tgt          EQU pf_itick + 1                ;   first body struck ($FF none)
pf_stopper      EQU pf_tgt + 1                  ;   body that stopped it ($FF none)
pf_miss         EQU pf_stopper + 1              ;   T7: first body a missile missed ($FF none)
PF_FFN          EQU 3                           ; ($FF-initialised: pf_tgt, pf_stopper, pf_miss)
pf_fxrow        EQU pf_miss + 1                 ; 1 = FXD_ROW taken from a body
pf_lost         EQU pf_fxrow + 1                ;   HP lost by pf_tgt (0: none)
pf_ftick        EQU pf_lost + 1                 ;   D3-8e2: pf_tgt's impact tick (TURN_TICK units;
                                                ;   valid when pf_tgt != $FF; one word store)
pf_rev          EQU pf_ftick + 1                ; reversals so far
pf_part         EQU pf_rev + 1                  ; D3-8e: 0 / PFP_MID / PFP_DONE (proj_part)
pf_moves        EQU pf_part + 1                 ; FX moves after the anchor
pf_desc         EQU pf_moves + 1                ; the FX descriptor
pf_cand         EQU pf_desc + FXD_LEN           ; candidates (+ $FF end)
PF_ZN           EQU pf_cand - pf_fxrow          ; (0-initialised: pf_fxrow .. pf_desc)
                ASSERT PF_ZN < 256
                ASSERT pf_stopper == pf_tgt + 1 && pf_miss == pf_tgt + 2 && pf_fxrow == pf_tgt + PF_FFN
                ASSERT pf_ftick == pf_lost + 1
PF_RAM_END      EQU pf_cand + P_MAX_ENT * PFC_STRIDE + 1
PF_ROWF         EQU PF_RAM + PF_RAM_LEN - ROOM_COLS ; the flight row's cell flags (32-aligned, ends its page)
                ASSERT PF_RAM_END <= PF_ROWF && (PF_ROWF & $FF) == $100 - ROOM_COLS && TF_SOLID == 1
                ASSERT PF_RAM_END <= ABIL_DESC && ABIL_TGT + 2 <= PF_ROWF   ; D3-7 (+ T5 ABIL_TGT)
                ASSERT ABIL_RK == ABIL_DESC + ABD_STRIDE && ABIL_DESC_LEN == ABD_STRIDE + RK_STRIDE
