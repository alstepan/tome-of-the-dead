;==============================================================================
; mark.asm — D3-8d overhead status marks, bank-2 (per-tick) part (game.md
; §6.4.1 V2 "Status mark rules"; plan D3-8d). The ops (draw / erase / redraw
; / forget), the stale-mark sweep, the room reset + glyph copy and the
; transition hide are bank 7 (src/mark7.asm): an op is an event (apply,
; clear, a cell step, the 8-tick toggle), <= MK_OPS_MAX per tick and only in a
; tick still in its first frame, so its far7 (~0.25k T) never reaches a heavy
; tick; bank 2 keeps only the per-tick pass (wanted vs drawn, the damage test)
; and the cell_occ map test.
;
; One 8x8 glyph above every visible HOLD / MIND body (hero and monsters; HOLD >
; MIND): the body's centre column ((px + 4) / 8 + (KT_BW - 1) / 2), the row
; above its top row ((py / 8) - 1; ANIM-IMPORT2: above the DRAWN frame's top
; row R_ROW when that lies lower, e.g. a 40-px frame on a 48-px body, so the
; mark rests on the visible head); hidden when that row lies above the
; storey band (top row = 9s, a flyer at y = 9s) or when the cell is inside a
; drawn body / FX / another mark (then it waits). Glyph = the panel icon
; (status_icons 0..4, frame A), attr = the icon's (FROZEN $45, ASLEEP $41,
; STUNNED $07, CONFUSED $43, FEAR $42) on black paper; drawn as the cell's map
; glyph OR the mark (a decor / ladder cell under it is accepted clash).
;
; Frame B is DERIVED, no new art (user 2026-10-14: "frame A shifted up 1 px";
; manager 2026-10-14: BRIGHT toggle for the full-height glyphs). The glyph
; copy (MK_GLYPHS, mark7.asm mk_room) keeps a 0 byte before every glyph and
; after the last, so a 1-px vertical shift is only a -1 source offset: a
; glyph whose bottom row is blank (FROZEN, CONFUSED, FEAR) rests one line
; down (nothing clipped) and rises to its panel position for frame B; one
; using all 8 rows (ASLEEP, STUNNED: the shift would clip ASLEEP's whole Z
; top bar) keeps its lines and frame B toggles BRIGHT (attr XOR $40). Phase
; (TICK + 3 * slot) & 15: 8 ticks A, 8 ticks B, staggered per slot;
; ANIM_FREEZE (goldens) = frame A.
;
; Layering (bodies -> FX -> marks -> numbers): mark_tick runs in decor_gate,
; after this tick's render, BEFORE the drip and the decor steps: their
; cell_occ includes the drawn marks (MK_MAP), so a drop / attr step never
; lands on a mark; a mark drawn onto the drop's cell forgets the drop. A
; drawn mark whose cell this tick's render rewrote (a damage rect: a body /
; FX erased or drawn over it) is forgotten at once (mk_forget: a body / FX on
; the cell now -> queue_damage, the next render restores it and repairs what
; covers it) and re-stamped by the next op on it when its cell is clear.
;
; Budget (§6.4.1): <= MK_OPS_MAX ops a tick, round-robin over RLIST (the
; first slot denied an op starts the next pass; the rest of the pass still
; runs the damage test); a mark whose cell was covered retries only every
; 8th tick (phase per slot) or when the render touched its cell (MK_WAIT), so
; a waiting mark does not burn an op a tick; ops only in a tick still in
; its first frame (never lengthens a heavy tick; a 2nd-frame tick skips the
; pass: a mark a heavy render wiped is redrawn by its next toggle, which tests
; the cover first); nothing at all on a TP_FIRE tick; no pass while no slot
; has HOLD / MIND and no mark is drawn.
;==============================================================================

;------------------------------------------------------------------------------
; mark_tick — decor_gate, every unfrozen play tick, before drip_tick (after
; render: SLOTREC R_COL..R_ROWS and DMG_LIST are this tick's).
; The first-frame gate is tested ONCE, at the entry: a pass that runs on
; past the frame boundary still finishes its <= MK_OPS_MAX ops + forgets.
; Clobbers: all but IY. Pages nothing itself: the ops run through far7, which
; restores the caller's bank (erase_rect pages bank 7 inside them).
; Cost: fire tick ~40 T, a 2nd-frame tick ~70 T; else no HOLD / MIND + no
; mark ~0.45k; then per RLIST slot without a status / mark ~0.15k, with one
; ~0.55k (+ 45 T per damage rect while drawn); an op +~1.2k (far7, cover
; test, draw or erase); a forget (mk_forget: not an op, not capped: one per
; drawn mark this render touched) ~1.5k (far7, drop, cover test, queue).
;------------------------------------------------------------------------------
mark_tick:
                xor  a
                ld   (MK_OPS), a
                ld   a, (TURN_PEND)            ; nothing on the cast tick
                and  TP_FIRE
                ret  nz
                ld   a, (SYS_FRAMES)           ; 2nd frame already: nothing (a heavy tick
                ld   hl, LAST_TICK_FRAME       ; pays ~70 T)
                cp   (hl)
                ret  nz
                ld   hl, ST_FLAGS              ; any HOLD / MIND at all?
                ld   b, P_MAX_ENT
                xor  a
.o:             or   (hl)
                inc  l
                djnz .o
                and  STS_HOLD | STS_MIND
                ld   b, a
                ld   a, (MK_N)
                or   b
                ret  z                         ; no status, no mark: nothing to do
                ld   a, MK_OPS_MAX
                ld   (MK_LEFT), a
                ld   a, (RLIST_N)
                or   a
                jr   z, .cln
                ld   b, a
                ld   a, (MK_RR)
                cp   b
                jr   c, .r0
                xor  a
.r0:            ld   c, a                      ; C = RLIST index, B = slots left
                ld   a, $FF
                ld   (mk_den), a               ; no slot denied an op yet
.l:             ld   a, c
                add  a, RLIST & $FF
                ld   l, a
                ld   h, RLIST >> 8
                ld   e, (hl)                   ; E = slot
                ld   a, e
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_HOLD | STS_MIND
                ld   a, e
                ld   (mk_sl), a
                jr   nz, .do
                call mk_rec                    ; no status: only a drawn mark matters
                ld   a, (hl)
                or   a
                jr   z, .nx
.do:            push bc
                call mk_slot                   ; (the damage test runs with no op left too)
                pop  bc
                jr   nc, .nx
                ld   a, (mk_den)
                inc  a
                jr   nz, .nx
                ld   a, c                      ; the first slot denied an op
                ld   (mk_den), a
.nx:            inc  c
                ld   a, (RLIST_N)
                cp   c
                jr   nz, .nw
                ld   c, 0
.nw:            djnz .l
                ld   a, (mk_den)
                inc  a
                jr   z, .cln
                dec  a
                ld   (MK_RR), a                ; it starts the next pass (round robin)
                ret
.cln:           ld   a, (TICK_COUNTER)         ; every 8th tick: marks of slots out of
                and  7                         ; RLIST (neither visible nor drawn)
                ret  nz
                ld   a, (MK_N)
                or   a
                ret  z
                ld   hl, mk_sweep              ; (bank 7)
                jp   far7
                ASSERT (RLIST >> 8) == ((RLIST + P_MAX_ENT - 1) >> 8) && (ST_FLAGS & $FF) + P_MAX_ENT <= 256

;------------------------------------------------------------------------------
; mk_slot — mk_sl = a slot with a status or a drawn mark: the wanted mark
; (mk_des / mk_dlo), a drawn one this render damaged forgotten (always, ops
; or not), then one op toward the wanted state (mk_op, bank 7) if it differs
; and an op is left. CF = 1: an op was needed and none was left (denied).
; Clobbers: A, BC, DE, HL, IX.  ~0.5k T without an op
;------------------------------------------------------------------------------
mk_slot:
                ld   a, (mk_sl)
                ld   e, a
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   b, (hl)
                ld   d, 0                      ; D = wanted R_MK (0: none)
                ld   a, e
                rlca
                rlca
                rlca
                rlca
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   a, (hl)                   ; R_VIS (anim_tick: drawn next render)
                or   a
                jp   z, .want                  ; hidden: none (jp: ANIM-IMPORT2 pushed it out of jr range)
                ld   a, b
                and  STS_HOLD                  ; HOLD > MIND; g = the HOLD kind 1..3
                jr   nz, .g
                ld   a, b
                and  STS_MIND
                jr   z, .want                  ; none
                cp   MIND_FEAR
                ld   a, MK_G_FEAR
                jr   z, .g
                ld   a, MK_G_CONF
.g:             ld   d, a                      ; D = g
                ld   a, e
                call ent_ix                    ; (A, E)
                ld   a, (ix+E_PY)
                rrca
                rrca
                rrca
                and  $1F
                ld   e, a                      ; E = its top row
                ; ANIM-IMPORT2: a frame shorter than the body (the 40-px sets on a 6-cell
                ; body, bottom-anchored) starts lower: the mark sits right above the DRAWN
                ; top row (this tick's R_ROW) instead, which lies inside the body box, so
                ; never above the storey band (no KT_MOD9 test). +12 B, +~45 T a marked slot
                ld   a, (mk_sl)
                rrca
                rrca
                rrca
                rrca                           ; slot * 16 (slot < 16)
                or   R_ROW
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   a, (hl)                   ; the drawn frame's top row
                cp   e
                jr   z, .full                  ; frame top = body top (48 / 32 / 16-px art)
                jr   c, .full                  ; (above it: never today; keep the body rule)
                dec  a
                ld   e, a                      ; E = the mark row: one above the visible head
                jr   .mrow
.full:          ld   a, e
                add  a, (kind_tab + KT_MOD9) & $FF
                ld   l, a
                ld   h, (kind_tab + KT_MOD9) >> 8
                ld   a, (hl)
                or   a
                jr   z, .hide                  ; storey top row: the row above is not its band
                dec  e                         ; E = the mark row (0..16)
.mrow:
                ld   a, (ANIM_FREEZE)
                or   a
                jr   nz, .fa                   ; goldens: frame A
                ld   a, (mk_sl)
                ld   b, a
                add  a, a
                add  a, b
                ld   hl, TICK_COUNTER
                add  a, (hl)                   ; (TICK + 3 slot) & 15 >= 8: frame B
                and  MK_FRAME
                or   d
                ld   d, a
.fa:            ld   a, e
                and  $18
                add  a, a                      ; row >> 3 -> bits 4-5
                or   d
                ld   d, a                      ; D = g | frame | third
                ld   a, e
                rrca
                rrca
                rrca
                and  $E0
                ld   e, a                      ; E = (row & 7) << 5
                KFIELD KT_BW                   ; (A, HL)
                dec  a
                srl  a                         ; (w - 1) / 2
                ld   b, a
                ld   a, (ix+E_PX)
                add  a, 4                      ; rendered x rounded to a cell
                rrca
                rrca
                rrca
                and  $1F
                add  a, b
                cp   ROOM_COLS
                jr   nc, .hide
                or   e
                ld   e, a                      ; E = the cell's low byte
                jr   .want
.hide:          ld   d, 0
.want:          ld   (mk_dlo), de              ; mk_dlo = E, mk_des = D
                ld   a, d
                or   a
                jr   nz, .wd
                ld   a, (mk_sl)                ; none wanted: no retry pending
                add  a, MK_WAIT & $FF
                ld   l, a
                ld   h, MK_WAIT >> 8
                ld   (hl), d
.wd:
                call mk_rec
                ld   a, (hl)
                or   a
                jr   z, .cmp
                call mk_cb                     ; drawn: did this render rewrite its cell?
                ld   de, $0101
                call dmg_hit                   ; (BC kept)
                ld   hl, mk_forget             ; yes: forgotten (bank 7)
                call c, far7
                call mk_rec
.cmp:           ld   de, (mk_dlo)
                ld   a, (hl)
                cp   d
                jr   nz, .op
                or   a
                ret  z                         ; none wanted, none drawn (CF = 0)
                inc  l
                ld   a, (hl)
                dec  l
                cp   e
                ret  z                         ; drawn as wanted (CF = 0)
.op:            ld   a, (hl)
                or   a
                jr   nz, .go                   ; drawn: erase / redraw / move
                ; none drawn, one wanted: if the last try found its cell covered
                ; (MK_WAIT), retry only on the slot's phase tick ((TICK + 3 slot)
                ; & 7 = 0) or when this render touched the cell (a body / FX left)
                ld   a, (mk_sl)
                add  a, MK_WAIT & $FF
                ld   l, a
                ld   h, MK_WAIT >> 8
                ld   a, (hl)
                or   a
                jr   z, .go
                ld   a, (mk_sl)
                ld   b, a
                add  a, a
                add  a, b
                ld   hl, TICK_COUNTER
                add  a, (hl)
                and  7
                jr   z, .go
                call mk_cbde                   ; (D, E = wanted)
                ld   de, $0101
                call dmg_hit
                jr   c, .go
                or   a                         ; not touched: wait (CF = 0)
                ret
.go:            ld   a, (MK_LEFT)
                sub  1
                ret  c                         ; no op left: denied (CF = 1)
                ld   hl, mk_op                 ; (bank 7; it spends the op)
                call far7
                or   a
                ret
                ASSERT MK_G_CONF == 4 && MK_G_FEAR == 5 && HOLD_STUNNED == 3

; mk_rec — HL = SLOTREC record of mk_sl, field R_MK.  Clobbers: A
mk_rec:
                ld   a, (mk_sl)
                rlca
                rlca
                rlca
                rlca
                or   R_MK
                ld   l, a
                ld   h, SLOTREC >> 8
                ret
                ASSERT R_MKLO == R_MK + 1 && R_MKLO < SLOTREC_STRIDE && SLOTREC_STRIDE == 16 && (SLOTREC & $FF) == 0

; mk_cb — HL = a record's R_MK -> C = col, B = row of its cell (HL kept).
; mk_cbde — the same from D = R_MK, E = R_MKLO.  Clobbers: A (mk_cb: + DE)
mk_cb:
                ld   d, (hl)
                inc  l
                ld   e, (hl)
                dec  l
mk_cbde:
                ld   a, e
                and  $1F
                ld   c, a
                ld   a, d
                and  MK_THIRD
                rrca                           ; third * 8
                ld   b, a
                ld   a, e
                rlca
                rlca
                rlca
                and  7
                or   b
                ld   b, a
                ret
                ASSERT MK_THIRD == $30

;------------------------------------------------------------------------------
; mk_bit — cell (C col, B row) -> HL = its MK_MAP byte, A = its bit.
; cell_occ (decor.asm) and the bank-7 ops.  Clobbers: A, E, HL (BC, D kept).
; ~0.12k T
;------------------------------------------------------------------------------
mk_bit:
                ld   a, c
                and  7
                add  a, pm_tab & $FF
                ld   l, a
                ld   h, pm_tab >> 8
                ld   a, (hl)
                inc  l
                xor  (hl)                      ; ($FF >> n) ^ ($FF >> n+1) = bit 7-n
                ld   e, a
                ld   a, b
                add  a, a
                add  a, a
                ld   l, a
                ld   a, c
                rrca
                rrca
                rrca
                and  3
                add  a, l
                ld   l, a
                ld   h, MK_MAP >> 8
                ld   a, e
                ret
                ASSERT (pm_tab >> 8) == ((pm_tab + 8) >> 8) && PLAY_ROWS * 4 <= 256

; scratch (mark_tick / the ops are not re-entrant; the bank-7 ops read them)
mk_sl:          DB   0                         ; the slot in hand
mk_dlo:         DB   0                         ; wanted R_MKLO
mk_des:         DB   0                         ; wanted R_MK (0: none)
mk_den:         DB   0                         ; RLIST index of the first slot denied an op ($FF none)
                ASSERT mk_des == mk_dlo + 1
