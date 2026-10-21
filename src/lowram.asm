;==============================================================================
; lowram.asm — COLD code + boot-only data in bank 5 low RAM (docs/memory-map.md
; "Bank 5 low RAM"). Bank 5 is always mapped at $4000-$7FFF, so code here can
; page ANY bank through $C000 — the generator reads the sprite sources in banks
; 1/3 and writes the pre-shift pool in banks 0/4/6, so it cannot live in a
; paged bank. main.asm ORGs this block so it ENDS at $8000 (lowram_code ..
; $7FFF): it is contiguous with the bank-2 image and the tape CODE block is the
; single range lowram_code .. code_end, entered at its first byte (start). The
; block ENDS with the frame descriptors (fdesc_tab, A6): new frames grow it
; downward; main.asm keeps the FRT_MAX growth reserve free below it.
;
; Contended (bank 5): every opcode fetch pays ULA contention while the screen is
; being drawn. Nothing here runs per tick (boot, hero select, game start).
; No ALIGN in here: the base is computed from this block's own size.
;==============================================================================

;------------------------------------------------------------------------------
; start — .tap entry (RANDOMIZE USR start): pull the seven headerless blocks
; off tape with the ROM loader, in `tape_tab` order (3E-T1: one table-driven
; loop, was one 15-20 B stanza per block): bank 1 = sources + vdata + UI code;
; bank 3 = source tail + bank-3 cold code; A8: bank 3 AY slot at AY_RESERVE;
; B3B-8: bank 7 tilesets at TSET_LO (+ D3-S2 the bank-7 cold code) / TSET_HI —
; nothing there is live yet: screen 2 is not shown, the 128 editor's bank-7
; workspace is abandoned with BASIC; D3-TX: the text block at the bottom of
; bank 0 — check_paging's probe byte there is overwritten; 3E-T1: the boot
; block at the top of bank 6 (boot6.asm). Then boot. The .sna enters at boot.
; Runs under the ROM IM1 ISR (LD-BYTES ends with EI; IY = $5C3A here): boot
; installs IM 2. A tape error rewinds and retries the same block.
;------------------------------------------------------------------------------
start:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR
                call check_paging              ; stops here if $7FFD is locked
                ld   hl, tape_tab
.lo:                                           ; test probe (paging OK): once per block
                push hl                        ; the record (retried on a tape error)
                ld   a, (hl)                   ; TT_BANK
                inc  hl
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                push de
                pop  ix                        ; IX = TT_ADDR
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                   ; DE = TT_LEN
                call page_bank                 ; (clobbers BC only)
                ld   a, $FF                    ; data block flag
                scf                            ; LOAD (not VERIFY)
                call ROM_LD_BYTES
                pop  hl
                jr   nc, .lo                   ; tape error: rewind + retry
                ld   de, TT_STRIDE
                add  hl, de
                ld   a, (hl)
                inc  a                         ; $FF: end of the table
                jr   nz, .lo
start_loaded:                                  ; falls straight into boot:
                ASSERT start_loaded == boot    ; nothing may be inserted here

;==============================================================================
; boot — .sna entry. Cold init, pool generation (~1 s), then hero select.
; 3E-T1: the IM 2 install, the power-on state and the tile / font / hot-image
; copies run from the boot block (boot6.asm, bank 6 tail, farb): it must run
; before alloc_reset — the pool overwrites that block later.
;==============================================================================
boot:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR             ; kept for ISR_ROM_CHAIN (conventions)
                ld   a, BANK_POOL0
                call page_bank                 ; a valid shadow for farb's restore
                ld   hl, boot6_init            ; IM 2 (EI below, once the shadow is
                ld   c, BANK_BOOT6             ; valid) + the power-on state
                call farb
                ei
                call build_bitrev
                ld   hl, boot6_tiles           ; the common set, ornament, the panel hot
                ld   c, BANK_BOOT6             ; code and the FONT6 planes (B3B-8 /
                call farb                      ; B3B-11; were bank 7 init_tiles / panel_boot)
                call alloc_reset
                ; monsters: every kind's frames, both facings (§5.2)
                ld   a, K_SKELETON
.gk:            push af
                call gen_kind
                pop  af
                inc  a
                cp   K_COUNT
                jr   c, .gk
                ; the two heroes' IDLE frames for the select screen
                ld   a, FID_knight_idle1
                call gen_frame
                ld   a, FID_wizard_idle
                call gen_frame
                or   a                         ; CF = 0: save
                call sel_frt_copy
                call alloc_mark                ; hero sets regenerate from here
                jp   enter_select              ; bank-2 trampoline -> bank 3

; tape_tab — start's blocks: bank, address, length (main.asm TAPE_BLOCKS, the
; one list the SAVETAPs expand too)
TT_STRIDE       EQU 5
tape_tab:       TAPE_BLOCKS 0                  ; main.asm: the same list the SAVETAPs use
                DB   $FF                       ; end (no bank is $FF: TAPE_BLK ASSERTs < 8)
                ASSERT $ - tape_tab == TAPE_HEADLESS_N * TT_STRIDE + 1

;------------------------------------------------------------------------------
; check_paging — 48 BASIC / USR 0 set $7FFD bit 5 (paging lock): every later
; OUT is ignored, so the two sprite banks would load over each other and the
; pool would alias. Write different bytes to bank 1 and bank 0 at $C000 and
; read bank 1 back; on a mismatch print a message and stop (DI + HALT).
; Tape path only (the .sna preloads all banks and enters at boot). Bank 0 and
; bank 1 $C000 are free here (pool / sources are written after this).
; +2A/+3 are unsupported (different paging). Clobbers: A, BC, HL (+ print).
;------------------------------------------------------------------------------
check_paging:
                ld   a, BANK_SRC_LO
                call page_bank
                ld   hl, BANK_WINDOW
                ld   (hl), PAGING_PROBE
                ld   a, BANK_POOL0
                call page_bank
                ld   (hl), ~PAGING_PROBE & $FF
                ld   a, BANK_SRC_LO
                call page_bank
                ld   a, (hl)
                cp   PAGING_PROBE
                ret  z
                ld   a, ATTR_HUD
                call clear_screen
                ld   b, 11
                ld   c, 5
                ld   hl, str_lock
                call print_str
.locked:        di                             ; test probe (paging locked)
                halt

str_lock:       DB "LOAD FROM 128 BASIC", 0     ; check_paging: $7FFD locked
; (3E-T1: keytab_defaults, isr_install and the ISR load image isr_image moved
; to the boot block, boot6.asm)

; the menu's hero idles: fid only is read (sel_frt_copy: their boot FRT rows,
; saved at boot, restored by menu_run; C3-6: the menu draws them, menu1.asm)
sel_tab:        DB   FID_knight_idle1, FID_wizard_idle

;==============================================================================
; start_game — C = hero kind. Generate its frames (§5.2: only the chosen
; hero) and its class FX kind (D3-4: K_FX_BASE + hero), new game, first level (B3B-12: a generated D1 through level_enter;
; proto_start = 1: the PROTO rooms A-D through level_show), then the play
; loop (bank 2, never returns).
;==============================================================================
start_game:
                ld   a, c
                ld   (HERO_KIND), a
                call alloc_restore
                ld   a, (HERO_KIND)
                call gen_kind
                ld   a, (HERO_KIND)            ; D3-4: + the class FX kind
                add  a, K_FX_BASE              ; (K_FXW / K_FXM: only this class's
                call gen_kind                  ; projectiles / impacts in the pool)
                ld   hl, new_game              ; bank 7 (MEM-SND; was bank 3, A7 review):
                call far7                      ; hero slot, PROTO level / master seed
                ld   de, TX_WELCOME            ; the first log line (panel_init)
                ld   a, (proto_start)
                or   a
                jr   z, .gen
                xor  a                         ; depth 0: the PROTO rooms' theme
                call level_show                ; (the D1 set)
                jr   .go
.gen:           inc  a                         ; A = 1: D1
                call level_enter
.go:            ld   a, 1
                ld   (NEED_RELEASE), a         ; the select key must be released
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                jp   play_loop

; B3B-12 run configuration (on tape, in this cold block; tests poke them right
; after the snapshot load / tape boot, docs/memory-map.md "Level entry"):
;   proto_start  1 = new games start in the PROTO rooms A-D (tests/game.py's
;                walkthrough, budget, flicker); 0 (default) = a generated D1
;   seed_fixed   1 = MASTER_SEED = seed_value (game.md §1 SEED_FIXED, F3);
;                0 (default) = SYS_FRAMES when the hero is chosen
    IFNDEF PROTO_START
PROTO_START     EQU 0                   ; -DPROTO_START=1: PROTO rooms by default
    ENDIF
    IFNDEF SEED_FIXED
SEED_FIXED      EQU 0                   ; -DSEED_FIXED=1 [-DSEED_VALUE=n]
    ENDIF
    IFNDEF SEED_VALUE
SEED_VALUE      EQU $1234
    ENDIF
proto_start:    DB   PROTO_START
seed_fixed:     DB   SEED_FIXED
seed_value:     DW   SEED_VALUE

;------------------------------------------------------------------------------
; level_enter — B3B-12: enter depth A (1..8) of the run; E = first log line
; (TX_*, TX_NONE = none; B3B-13: was a pointer in DE).
; New game (start_game, A = 1) and descend (level_descend) alike:
;   card     clear the bank-5 screen, "DEPTH n" (level_card), present_full:
;            the card stays on screen 2 while everything below is composed
;            in bank 5 (game.md §11)
;   level    far3 level_new: LVL_SEED from MASTER_SEED, level_gen (retried
;            on B = 1), the stand-in population, hero on the start (GAME_STATE
;            = TRANSITION meanwhile: a gen_frame here would count in GEN_TRAP)
;   show     level_show: tiles, first room into ROOM_MAP (so ANIM_LIST is the
;            new room's), panel, vis_reset (entity table rewritten), present
; The caller sets GAME_STATE and resyncs the tick. Leaves bank 7 paged.
; Clobbers: all but IY.   Cold: ~1.3-2.0M T (tests/world.py W16 reports)
;------------------------------------------------------------------------------
level_enter:
                push af
                ld   hl, 0                     ; SND-3: Dangerous off, calm count 0
                ld   (DNG_DWELL), hl           ; (DNG_CALM = DNG_DWELL + 1)
                xor  a
                ld   (SFX_NEXT), a             ; SND-5: no deferred effect into a new level
                ld   a, MUS_ROOM               ; same id as the menu = the tune keeps playing,
                ld   (MUS_REQ), a              ; no restart (Q rotation by depth: later)
                pop  af
                push de
                push af
                ld   a, GS_TRANSITION
                ld   (GAME_STATE), a
                ld   a, ATTR_HUD
                call clear_screen
                pop  af
                push af
                ld   hl, level_card            ; C3-6: bank 1, the menu font
                call far1
                call present_full              ; the card -> screen 2, shown
                pop  af
                ld   hl, level_new             ; bank 3: generate + populate
                call far3
                ld   hl, stinger_wait          ; SND-4a: hold while the stinger plays (bank 1;
                call far1                      ; a no-op unless MUS_CUR = MUS_LEVEL shot)
                pop  de
                ld   a, (LVL_DEPTH)
                ; fall through
;------------------------------------------------------------------------------
; level_show — A = depth (0 = PROTO), E = first log line (TX_*), CUR_ROOM + the
; level state + the entity table set: theme tiles, the room built into
; ROOM_MAP + drawn (screen + shadow), panel (depth Dn, HP, log), vis_reset
; (render-state resync after an entity-table rewrite: conventions.md), then
; present_full. Leaves bank 7 paged. Clobbers: all but IY.
;------------------------------------------------------------------------------
level_show:
                push de
                call level_load_tiles
                ld   a, ATTR_HUD
                call clear_screen
                ld   a, (CUR_ROOM)
                call room_show                 ; build + draw + ornament (screen, shadow)
                pop  de
                ld   hl, panel_init            ; B3B-11: rows 18-23 + the first log line (bank 3)
                call far3
                call vis_reset
                jp   present_full              ; A7: bank 5 -> 7, display bank 7

;------------------------------------------------------------------------------
; lair_hint — B12 (concept-screen B3B-8 #4): A = the room just entered
; (do_exit). The first entry to the level's lair logs "A GATE GLEAMS, THE WAY
; DOWN" once; LF_GATE_HINT in LVL_FLAGS remembers it (level_gen rewrites
; LVL_FLAGS, so it resets per level; PROTO: LVL_LAIR = ROOM_NONE, never a
; room). Low RAM, not do_exit itself: bank 2 has a 4-B kind_tab ALIGN pad.
; Keeps A. Clobbers: F, BC, DE, HL.   ~60 T, the one logging entry ~0.4k T + log_push
;------------------------------------------------------------------------------
lair_hint:
                ld   hl, LVL_LAIR
                cp   (hl)
                ret  nz
                ld   hl, LVL_FLAGS
                bit  LF_GATE_HINT_BIT, (hl)
                ret  nz
                set  LF_GATE_HINT_BIT, (hl)
                push af
                ld   a, TX_GATE_GLEAMS
                call msg_push
                pop  af
                ret
                ASSERT LF_GATE_HINT == 1 << LF_GATE_HINT_BIT

; level_descend — do_exit with EXIT_KIND = EX_LEVEL (the hero took the
; lair's level exit, logic.asm try_climb): D8 -> GS_WIN (game.md §1.4
; stand-in), else level_enter (depth + 1). Back in end_turn, which finishes
; the turn (potion pickup on the new level, TURN_PHASE 0).
; Clobbers: all but IY.
;------------------------------------------------------------------------------
level_descend:
                xor  a
                ld   (EXIT_KIND), a
                ld   a, (LVL_DEPTH)
                cp   LEVELS
                jr   nc, .win
                inc  a
                ld   de, TX_DESCEND
                ld   b, a
                ld   a, MUS_LEVEL              ; SND-4a: Level Complete stinger (the ISR drops it
                ld   (MUS_SHOT), a             ; with music off); level_enter holds for it
                ld   a, b
                call level_enter
                ld   a, 1                      ; like start_game: a key still held
                ld   (NEED_RELEASE), a         ; through the card must be released
                ld   a, GS_PLAYING             ; (edge-triggered input) first
                ld   (GAME_STATE), a
                jp   resync_tick
.win:           xor  a                         ; SND-4: Game Win once (like Game Over in end_turn
                ld   (MUS_REQ), a              ; .dead): loop off, then the final shot; no stinger
                ld   a, MUS_WIN                ; and no stinger_wait here (level_enter not run);
                ld   (MUS_SHOT), a             ; the ISR drops it with music off
                ld   a, GS_WIN
                ld   (GAME_STATE), a
                ld   a, TX_WIN
                jp   msg_push_end              ; never dropped; end_screen drains it

;==============================================================================
; ROOM ENTRY / THEME (B3B-8). build_room_map v2 lives in bank 3 (D7); these
; are its low-RAM ends: the far entry, the level tile-set load (pages bank 7)
; and the row-17 ornament (drawn over the map's floor cells, game.md §3.3).
;==============================================================================
;------------------------------------------------------------------------------
; build_room — A = room 0..8, H = map page (ROOM_MAP / NEXT_MAP >> 8): far3
; to the bank-3 build_room_map (which takes the page in D). Puts the caller's
; $C000 bank back. Clobbers: A, BC, DE, HL (IX, IY kept).
;------------------------------------------------------------------------------
build_room:
                ld   d, h
                ld   hl, build_room_map
                jp   far3

;------------------------------------------------------------------------------
; room_show — A = room: build it into ROOM_MAP, draw it on the bank-5 screen
; (+ the row-17 ornament) and the bank-7 attr shadow (start_game; the B3B-12
; level entry). Does not present (callers end with present_full).
; Leaves bank 7 paged. Clobbers: A, BC, DE, HL (IX, IY kept).  ~0.4M T
; (draw_room ~334k T + the build, tests/world.py W12)
;------------------------------------------------------------------------------
room_show:
                push af
                ld   h, ROOM_MAP >> 8
                call build_room
                call draw_room                 ; screen + attr shadow (leaves bank 7 paged)
                pop  af
                call fl_attr_room              ; 3E-T6: the floor items' inks over both
                ld   a, SCREEN_BITMAP >> 8
                jp   orn_row

;------------------------------------------------------------------------------
; room_shadow — do_exit after the scroll: the new room's animated-decor list
; (B3B-9 review: its NEXT_MAP build filled ANIM_N2 / ANIM_LIST2; one LDIR of
; the count + 12 entries over ANIM_N / ANIM_LIST, ~1k T), then the
; attr shadow of the new room (shadow_room; D3-S2: no bitmap shadow, so no
; ornament here — the scroll drew the screen's, orn_cells calls in
; scroll1.asm). Leaves bank 7 paged. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
room_shadow:
                ld   hl, ANIM_N2
                ld   de, ANIM_N
                ld   bc, ANIM_COPY_LEN
                ldir
                call shadow_room
                ld   a, (EXIT_DEST)            ; 3E-T6: + the new room's floor inks
                jr   fl_attr_sh
;------------------------------------------------------------------------------
; 3E-T6 floor-item glyph + ink (game.md §8.11 Q1 + "3E simplification" 2: the
; ink is a pure function of the TYPE). One byte per type in it_tab: the glyph
; class (item_glyph) and the ink (item_ink), the per-cell attr painted by
; fl_attr over the attr plane AFTER the cells were drawn from TILE_ATTRS.
; level_load_tiles sets TILE_ATTRS of the item glyph ids to 0 (ink = paper:
; blank), so a cell drawn from the map but not yet painted (the scroll's
; entering strip, the instant between tile_rect and fl_attr) shows nothing
; rather than a wrong ink.
;------------------------------------------------------------------------------
; it_byte — A = item type (< IT_COUNT): A = it_tab[type]. Keeps BC, DE. Clobbers HL.
it_byte:        ld   hl, it_tab
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
                ret

; DEBUG_KIT only (0 B in the release build): item_glyph / item_ink get a LIVE FL type, so
; a type >= IT_COUNT (a corrupt floor entry) bumps IT_BAD (expect 0) before the lookup.
    IF DEBUG_KIT
it_byte_live:   cp   IT_COUNT
                jr   c, it_byte
                ld   hl, IT_BAD
                inc  (hl)
                jr   it_byte
IT_BYTE_LIVE    EQU it_byte_live
    ELSE
IT_BYTE_LIVE    EQU it_byte
    ENDIF

; item_glyph — A = item type (a live entry's FL_ITEM): A = its floor glyph,
; 0 = none (IT_NONE, IT_KEY). Keeps BC, DE, HL.
; Callers: build_room_map .pots (bank 3), ap_stamp (bank 7).  ~0.15k T
item_glyph:     push hl
                call IT_BYTE_LIVE
                rrca
                rrca
                rrca
                rrca
                and  7
                ld   hl, it_cls
                call it_byte + 3               ; HL = it_cls + class
                pop  hl
                ret

; item_ink — A = item type: A = its floor attr (ink on black; 0 = no glyph).
; Keeps BC, DE. Clobbers HL.
item_ink:       call IT_BYTE_LIVE
                ld   h, a
                and  7
                bit  IT_BRIGHT_BIT, h
                ret  z
                or   $40                       ; BRIGHT
                ret

; it_tab: type -> class << 4 | BRIGHT << 3 | ink (paper 0). SINGLE SOURCE in
; tools/items_model.py ITEM_INK + glyph(); tests/items_gen.py G0 checks this
; table against it. Classes: it_cls index.
IT_BRIGHT_BIT   EQU 3
    MACRO ITB cls, attr
                DB   ((cls) << 4) | (((attr) >> 3) & 8) | ((attr) & 7)
    ENDM
IC_NONE         EQU 0
IC_FLASK        EQU 1
IC_AMMO         EQU 2
IC_FOOD         EQU 3
IC_PAGES        EQU 4
IC_WEAPON       EQU 5
IC_WORN         EQU 6
it_cls:         DB   0, T_FLASK, T_AMMO, T_FOOD, T_PAGES, T_WEAPON, T_WORN
it_tab:         ITB  IC_NONE, 0                ; IT_NONE
                ITB  IC_FLASK, $42             ; IT_POTION (legacy / PROTO)
                ITB  IC_AMMO, $47              ; dagger
                ITB  IC_AMMO, $46              ; arrow
                ITB  IC_NONE, 0                ; key (no floor entry)
                ITB  IC_FOOD, $06              ; carrot
                ITB  IC_FOOD, $44              ; apple
                ITB  IC_FOOD, $04              ; pear
                ITB  IC_FOOD, $46              ; cheese
                ITB  IC_FOOD, $42              ; meat
                ITB  IC_FLASK, $42             ; Heal
                ITB  IC_FLASK, $45             ; Mana
                ITB  IC_FLASK, $44             ; Cure
                ITB  IC_PAGES, $45             ; Teleport
                ITB  IC_PAGES, $46             ; Fear
                ITB  IC_PAGES, $44             ; Sleep
                ITB  IC_PAGES, $47             ; Enchant
                ITB  IC_PAGES, $43             ; book
                ITB  IC_WEAPON, $06            ; bow
                DUP  IT_WPN_W_HI - IT_WPN_W_LO + 1
                ITB  IC_WEAPON, $07            ; Warrior blades
                EDUP
                DUP  IT_WPN_M_HI - IT_WPN_M_LO + 1
                ITB  IC_WEAPON, $06            ; Mage staves
                EDUP
                DUP  IT_HELM_HI - IT_ARM_LO + 1
                ITB  IC_WORN, $07              ; armour, helmets
                EDUP
                DUP  IT_CHARM_HI - IT_CHARM_LO + 1
                ITB  IC_WORN, $06              ; charms
                EDUP
                ASSERT $ - it_tab == IT_COUNT && IT_KEY == 4 && IT_F_CARROT == 5 && IT_P_HEAL == 10
                ASSERT IT_S_TELEPORT == 13 && IT_BOOK == 17 && IT_BOW == 18 && IT_WPN_W_LO == 19
                ASSERT IT_WPN_M_LO == IT_WPN_W_HI + 1 && IT_ARM_LO == IT_WPN_M_HI + 1
                ASSERT IT_HELM_LO == IT_ARM_HI + 1 && IT_CHARM_LO == IT_HELM_HI + 1

; fl_attr_room — A = room: paint its floor inks over the screen attrs and
; the attr shadow (room entry, after draw_room: bank 7 paged).
; fl_attr_sh — A = room: the attr shadow only (bank 7 paged: room_shadow,
; ap_stamp). fl_attr_scr — D / E = row / col offset: EXIT_DEST's inks over
; the screen attrs where its cells show now (the scrolls, bank 1).
; All: Clobbers A, BC, DE, HL; pages nothing.
fl_attr_room:   push af
                ld   c, SCREEN_ATTR >> 8
                call fl_attr0
                pop  af
fl_attr_sh:     ld   c, SHADOW_ATTR >> 8
fl_attr0:       ld   de, 0
                jr   fl_attr
fl_attr_scr:    ld   a, (EXIT_DEST)
                ld   c, SCREEN_ATTR >> 8
                ; fall through
;------------------------------------------------------------------------------
; fl_attr — room A's live FLOOR_LIST entries (both storeys) -> item_ink(type)
; on an attr plane in screen layout: C = the plane's high base (SCREEN_ATTR >>
; 8, or SHADOW_ATTR >> 8 with bank 7 paged), D / E = signed row / col offset
; map -> plane; a cell landing off rows 0..PLAY_ROWS-1 / cols 0..31, or a type
; without a glyph, is skipped. List order: the last entry of a cell wins, as
; its glyph does (build_room_map, ap_stamp).
; Pages nothing. Clobbers: A, BC, HL (DE kept).
; ~32 x 33 T scan + ~0.25k T per entry of the room
; SMC: .bh+1 = the plane base, per call.
;------------------------------------------------------------------------------
fl_attr:        ld   b, a
                ld   a, c
                ld   (.bh+1), a
                ld   hl, FLOOR_LIST
.l:             ld   a, (hl)
                and  FL_ROOM_MASK              ; (FL_EMPTY -> 15: never a room)
                cp   b
                jr   nz, .n
                ld   a, (hl)
                rlca
                sbc  a, a
                and  STOREY_ROWS
                add  a, STOREY_AIR - 1         ; the standing row 9s + 7
                add  a, d
                cp   PLAY_ROWS
                jr   nc, .n
                ld   c, a                      ; C = plane row
                inc  l
                ld   a, (hl)                   ; FL_COL
                add  a, e
                cp   ROOM_COLS
                jr   nc, .n1
                push hl
                push de
                ld   e, a                      ; E = plane col
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                call item_ink
                or   a
                jr   z, .x                     ; no glyph: nothing to paint
                ld   d, a
                ld   a, c
                rrca
                rrca
                rrca
                ld   l, a
                and  3
.bh:            add  a, 0                      ; SMC: the plane's high base
                ld   h, a
                ld   a, l
                and  $E0
                or   e
                ld   l, a
                ld   (hl), d
.x:             pop  de
                pop  hl
.n1:            dec  l
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .l                     ; 32 entries: L $00..$7C
                ret
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE == $80 && FL_S1 == $80
                ASSERT FL_COL == 1 && FL_ITEM == 2
                ASSERT (SCREEN_ATTR & $FF) == 0 && (SHADOW_ATTR & $FF) == 0 && STOREY_ROWS == 9

; orn_row — the whole row 17 of ROOM_MAP, A = bitmap base high.
orn_row:
                ld   bc, FLOOR_ROW1 << 8       ; row 17, col 0
                ld   de, ROOM_COLS << 8        ; 32 cells, logical col 0
                ; fall through
;------------------------------------------------------------------------------
; orn_cells — the row-17 ornament (game.md §3.3, designer 2026-10-03): over
; the T_PLAT / T_WALLF cells of ROOM_MAP row B (the logical floor of storey 1;
; holes / grate keep their tiles), the fixed ORN_GLYPHS pattern by LOGICAL col:
; cap_l at 0, cap_r at 31, wing_l skull_l skull_r wing_r at ORN_MID_COL..+3,
; link (odd) / bar (even) elsewhere (tools/concept_r4.py). Bitmap only: the
; attr stays TILE_ATTRS[T_PLAT / T_WALLF] = LVL_ATTR_FLOOR = the ornament attr.
; In : A = bitmap base high (SCREEN_BITMAP >> 8), B = map / screen row, C = first col, D = cells, E = the
;      logical col of the first cell (the scrolls draw a room's cols at other
;      screen cols). Pages nothing: callable from bank 3 (the scrolls).
; Clobbers: A, BC, DE, HL.   ~0.3k T per ornament cell (cold: room entry)
; SMC: .bh+1 = the bitmap base high, patched per call.
;------------------------------------------------------------------------------
orn_cells:
                ld   (.bh+1), a
.c:             push de
                call cell_addr                 ; HL = ROOM_MAP (B, C); keeps BC, DE
                ld   a, (hl)
                cp   T_PLAT
                jr   z, .o
                cp   T_WALLF
                jr   nz, .n
.o:             ld   a, e                      ; logical col -> ornament glyph
                or   a
                jr   z, .g                     ; 0: ORN_CAP_L
                cp   ROOM_COLS - 1
                ld   a, ORN_CAP_R
                jr   z, .g
                ld   a, e
                sub  ORN_MID_COL
                cp   ORN_MID_N
                jr   nc, .ch
                add  a, ORN_WING_L             ; wing_l skull_l skull_r wing_r
                jr   .g
.ch:            ld   a, e
                and  1
                ld   d, a
                ld   a, ORN_BAR
                sub  d                         ; odd: ORN_LINK, even: ORN_BAR
.g:             add  a, a
                add  a, a
                add  a, a
                add  a, ORN_GLYPHS & $FF
                ld   e, a
                ld   d, ORN_GLYPHS >> 8        ; DE = the glyph
                ld   a, b
                and  $18
.bh:            or   0                         ; SMC: bitmap base high
                ld   h, a                      ; L = cell_addr's (row & 7) << 5 | col:
                push bc                        ; the screen's low byte too
                ld   b, 8
.cp:            ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                djnz .cp
                pop  bc
.n:             pop  de
                inc  c
                inc  e
                dec  d
                jr   nz, .c
                ret
                ASSERT ORN_CAP_L == 0 && ORN_BAR == ORN_LINK + 1 && ORN_LINK == 1
                ASSERT ORN_SKULL_L == ORN_WING_L + 1 && ORN_WING_R == ORN_WING_L + ORN_MID_N - 1
                ASSERT (ORN_GLYPHS >> 8) == ((ORN_GLYPHS + ORN_COUNT * 8 - 1) >> 8)
                ASSERT (SCREEN_BITMAP & $18FF) == 0

;------------------------------------------------------------------------------
; level_load_tiles — the level theme (game.md §1.2): A = depth 1..8, or 0 =
; the PROTO rooms A-D (D1's set, then the stand-in chest at T_CHEST_TL..BR =
; ids 32..35, B10; B3B-13 retires it). Copies the depth's bank-7 slot (TSET_*:
; 32 glyphs, 32 attrs, 32 TILE_FLAGS of ids 32..63) to TILE_LEVEL_GLYPHS /
; TILE_LEVEL_ATTRS / tile_flags + 32, then sets the common floor / wall ids'
; attrs to LVL_ATTR_FLOOR / LVL_ATTR_WALL (level_gen / new_game write them).
; Before the room is built and drawn. Puts the caller's $C000 bank back.
; Clobbers: A, BC, DE, HL.   11.7k T worst (measured, DI: tests/world.py W11)
;------------------------------------------------------------------------------
level_load_tiles:
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page)
                push bc                        ; B = depth
                ld   a, BANK_TSET
                call page_bank
                pop  bc
                push bc
                ld   a, b
                or   a
                jr   z, .s                     ; PROTO: slot 0 (D1)
                dec  a                         ; slot = depth - 1
.s:             ld   hl, TSET_LO
                cp   TSET_PER_HALF
                jr   c, .lo
                ld   hl, TSET_HI
                sub  TSET_PER_HALF
.lo:            ld   d, a                      ; DE = (slot & 3) * 320 = *256 + *64
                rrca
                rrca
                ld   e, a
                add  hl, de
                ld   de, TILE_LEVEL_GLYPHS
                ld   bc, TSET_ATTRS
                ldir
                ld   de, TILE_LEVEL_ATTRS
                ld   c, TILE_IDS - TILE_COMMON
                ldir
                ld   de, tile_flags + TILE_COMMON
                ld   c, TILE_IDS - TILE_COMMON
                ldir
                ld   hl, theme_ids             ; common ids that follow the depth
                ld   a, (LVL_ATTR_FLOOR)
                call .patch
                ld   a, (LVL_ATTR_WALL)
                call .patch
                xor  a                         ; 3E-T6: the item glyph ids blank
                call .patch                    ; (fl_attr paints their inks)
                pop  bc
                pop  af
                jp   restore_page
.patch:         ; A = attr -> TILE_ATTRS[id] for the ids at HL up to a 0 (T_AIR)
                ld   e, (hl)
                inc  hl
                inc  e
                dec  e
                ret  z
                ld   d, TILE_ATTRS >> 8
                ld   (de), a
                jr   .patch
                ASSERT (TILE_ATTRS & $FF) == 0 && T_AIR == 0
                ASSERT ((tile_flags + TILE_IDS - 1) >> 8) == (tile_flags >> 8)
                ASSERT TSET_PER_HALF == 4      ; (slot & 3) * 64 by two rrca
; the common ids whose attr is the depth's (tools/tiles_convert.py FLOOR_IDS /
; WALL_IDS, + rubble = ATTR_WALL, concept-screen §3.3 #12)
theme_ids:      DB T_PLAT, T_WALLF, T_END_L, T_END_R, 0
                DB T_BRICK, T_WALL_DITHER, T_WALL_PATCH, T_WALL_FADE, T_RUBBLE, 0
                DB T_AMMO, T_PAGES, T_FLASK, T_FOOD, T_WEAPON, T_WORN, 0

;==============================================================================
; TEXT (B3B-13). Message strings are dictionary-token streams in the
; BANK_TEXT text block (D3-TX: bank 0 bottom, was bank 1) (tools/textpack.py from src/strings.txt; format + layout:
; docs/memory-map.md "Text (B3B-13)"); the log ring holds streams and
; print6t (panel2.asm) decodes them when the line is drawn. These helpers
; page BANK_TEXT around the read and hand $C000 back as they found it
; (conventions.md: callable from bank-3 / bank-1 code). Low RAM: mapped
; while BANK_TEXT is at $C000.
;==============================================================================
;------------------------------------------------------------------------------
; msg_push — queue string A (TX_*) for the log: log_push copies its stream
; into the LOG_TXT ring as is. msg_push_end — the same through log_push_end
; (GS_DEAD / GS_WIN lines: never dropped). Any bank paged, any caller.
; Clobbers: A, BC, DE, HL (BC too: page_bank / log_push use it).   ~0.35k T + log_push (~25 T per stream byte)
;------------------------------------------------------------------------------
msg_push_end:
                ld   de, log_push_end
                jr   msg_go
msg_push:
                ld   de, log_push
msg_go:
                ld   h, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                ld   a, BANK_TEXT
                call page_bank                 ; (A, BC)
                ld   a, h
                call .go                       ; -> the pusher, HL = the stream
                pop  af
                jp   restore_page
.go:            push de                        ; tx_ptr's ret enters the pusher
                ; fall through
;------------------------------------------------------------------------------
; tx_ptr — HL = the stream of string A (TX_*, 0..255) in the text block
; (BANK_TEXT must be paged).  Clobbers: A.   86 T
; tx_ptr_hl — the same for a 16-bit id in HL (D3-0: the path for > 256 ids;
; no caller yet: every id is still a byte in A / DB tables, textpack caps
; TX_COUNT at 256).
; D3-0: 16-bit index (was `add a, a`: ids < 128); +31 T, +5 B; once per
; message / info line, never per tick.
;------------------------------------------------------------------------------
tx_ptr:
                ld   l, a
                ld   h, 0
tx_ptr_hl:
                add  hl, hl
                ld   a, l
                add  a, tx_tab & $FF
                ld   l, a
                ld   a, h
                adc  a, tx_tab >> 8
                ld   h, a
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ret

;------------------------------------------------------------------------------
; tx_dec — A = string id (TX_*): its decoded text, 0-terminated, in TX_DEC
; (bank 5, readable with any bank paged). D3-TX: for bank-1 UI code, which
; can no longer read the text block in place (menu1 mf_tx / tx_copy). Pages
; BANK_TEXT and hands $C000 back as it found it.
; Out: HL = TX_DEC.  Clobbers: A, BC, DE, HL.   ~0.4k T + ~60 T per char
;------------------------------------------------------------------------------
tx_dec:
                ld   h, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                ld   a, BANK_TEXT
                call page_bank                 ; (A, BC)
                ld   a, h
                call tx_ptr
                ld   b, h
                ld   c, l                      ; BC = the stream (tk_get state)
                ld   de, TX_DEC
.n:             call tk_get                    ; keeps DE
                ld   (de), a
                inc  de
                or   a
                jr   nz, .n
                pop  af
                call restore_page
                ld   hl, TX_DEC
                ret

;------------------------------------------------------------------------------
; show_impact_msg — IX = attacker at IMPACT (anim_tick, MSG_Q): queue its
; E_MSG line, composed in MSG_BUF as pre + kind name + post (imp_pre /
; imp_post): "YOU HIT THE RAT", "THE RAT MISSES". Token streams concatenate
; into a valid stream, decoded at print time. B3B-13: moved here from bank 3
; (one page switch for the 3 pieces instead of a far3).
; Clobbers: A, BC, DE, HL (IX kept).   ~1.4k T
;------------------------------------------------------------------------------
show_impact_msg:
                ld   a, (ix+E_MSG)
                or   a
                ret  z
                ld   c, (ix+E_KIND)            ; monster line: its own name
                cp   MSG_M_HIT
                jr   nc, .k
                push ix
                ld   a, (ix+E_TGT)
                call ent_ix                    ; (A, E)
                ld   c, (ix+E_KIND)            ; hero line: the target's name
                pop  ix
                ld   a, (ix+E_MSG)
.k:             ld   b, a                      ; B = E_MSG 1..5, C = kind
                ; fall through
; impact_line — B = message code (MSG_P_HIT .. MSG_SQUEEZE), C = kind: the
; line pre + kind name + post queued to the log (B14: "YOU SQUEEZE PAST THE
; RAT" uses it from the input phase). Clobbers: A, BC, DE, HL (IX kept).
impact_line:
                call sfx_msg                   ; SND-5: melee hit / miss / kill / hurt (bank 2; BC kept)
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                push bc
                ld   a, BANK_TEXT
                call page_bank
                pop  bc
                ld   de, MSG_BUF
                ld   a, b
                ld   hl, imp_pre - 1
                call .tab
                ld   a, c
                add  a, TX_NM_KNIGHT
                call .cat
                ld   a, b
                ld   hl, imp_post - 1
                call .tab
                xor  a
                ld   (de), a
                ld   hl, MSG_BUF
                call log_push                  ; (any bank: the ring is bank 5)
                pop  af
                jp   restore_page
.tab:           add  a, l                      ; A = (HL + A): the piece's id
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
.cat:           call tx_ptr                    ; append stream A at DE (no 0)
.c:             ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  hl
                inc  de
                jr   .c
; pieces by E_MSG 1..5 (MSG_P_HIT, MSG_P_MISS, MSG_P_KILL, MSG_M_HIT, MSG_M_MISS)
; D3-6a: + MSG_M_UNAFF .. MSG_M_THAW (deal_hit, combat3.asm): "THE " + name + status suffix
imp_pre:        DB   TX_YOU_HIT, TX_YOU_MISS, TX_YOU_KILL, TX_THE, TX_THE, TX_YOU_SQUEEZE
                DB   TX_THE, TX_THE, TX_THE, TX_THE, TX_THE, TX_THE, TX_THE, TX_THE
imp_post:       DB   TX_EMPTY, TX_EMPTY, TX_EMPTY, TX_HITS_YOU, TX_MISSES, TX_EMPTY
                DB   TX_CMB_UNAFFECTED, TX_ST_M_FROZEN, TX_ST_M_ASLEEP, TX_ST_M_STUNNED
                DB   TX_ST_M_FLEES, TX_ST_M_CONFUSED, TX_ST_M_WAKE, TX_ST_M_THAW
                ASSERT imp_post - imp_pre == MSG_M_THAW && $ - imp_post == MSG_M_THAW
                ASSERT MSG_M_UNAFF == 7 && MSG_M_FROZEN == 8 && MSG_M_ASLEEP == 9 && MSG_M_STUNNED == 10
                ASSERT MSG_M_FLEES == 11 && MSG_M_CONFUSED == 12 && MSG_M_WAKE == 13 && MSG_M_THAW == 14
                ASSERT TXL_THE + TXL_NM_SKELETON + TXL_CMB_UNAFFECTED < 32   ; the longest D3-6a line
                ASSERT MSG_P_HIT == 1 && MSG_P_MISS == 2 && MSG_P_KILL == 3 && MSG_M_HIT == 4 && MSG_M_MISS == 5
                ASSERT MSG_SQUEEZE == 6 && TXL_YOU_SQUEEZE + TXL_NM_SKELETON < 32
                ; K_ROGUE (kind 2) is retired: TX_NM_ROGUE is an empty string and no entity may carry
                ; that kind, else the impact line would lose its name (B3B-13b)
                ASSERT TX_NM_ROGUE == TX_NM_KNIGHT + 2 && TXL_NM_ROGUE == 0 && K_WIZARD == 1 && K_SKELETON == 3
                ; kind names: TX_NM_KNIGHT + kind (src/strings.txt order)
                ASSERT TX_NM_WIZARD == TX_NM_KNIGHT + K_WIZARD && TX_NM_SKELETON == TX_NM_KNIGHT + K_SKELETON
                ASSERT TX_NM_GOBLIN == TX_NM_KNIGHT + K_GOBLIN && TX_NM_GHOST == TX_NM_KNIGHT + K_GHOST
                ASSERT TX_NM_RAT == TX_NM_KNIGHT + K_RAT && TX_NM_BAT == TX_NM_KNIGHT + K_BAT
                ASSERT TX_NM_SLIME == TX_NM_KNIGHT + K_SLIME && K_KNIGHT == 0 && K_COUNT == 9
                ; the longest composition + its 0 fits MSG_BUF (32 B); a
                ; stream is never longer than its text, so chars bound bytes
                ASSERT TXL_NM_SKELETON >= TXL_NM_KNIGHT && TXL_NM_SKELETON >= TXL_NM_WIZARD
                ASSERT TXL_NM_SKELETON >= TXL_NM_GOBLIN && TXL_NM_SKELETON >= TXL_NM_GHOST
                ASSERT TXL_NM_SKELETON >= TXL_NM_RAT && TXL_NM_SKELETON >= TXL_NM_BAT && TXL_NM_SKELETON >= TXL_NM_SLIME
                ASSERT TXL_YOU_HIT + TXL_NM_SKELETON + TXL_EMPTY < 32 && TXL_YOU_MISS + TXL_NM_SKELETON < 32
                ASSERT TXL_YOU_KILL + TXL_NM_SKELETON < 32 && TXL_THE + TXL_NM_SKELETON + TXL_HITS_YOU < 32
                ASSERT TXL_THE + TXL_NM_SKELETON + TXL_MISSES < 32 && MSG_BUF + 32 <= TIMING_MARK

;==============================================================================
; B3B-5 DOORS, FALLS, JUMP (game.md §2.3-2.5, §9.1). They run only on the turn
; that opens / closes / falls / jumps (input tick), so they live here in
; bank-5 low RAM, not in bank 2; the per-step tests (lead_cell, the pit col)
; stay in bank 2 (logic.asm).
;==============================================================================
;------------------------------------------------------------------------------
; door_find — A = dx (1 right / $FF left): the door on that side of CUR_ROOM.
; Out: HL = its EDGE_TAB byte, C = its left col (30 / 0), B = its top plank
; row (9s + DOOR_PLANK_DY, s = that exit's storey); CF = 1 if the side has an
; edge (CF = 0: no exit there; HL / B are garbage). B3B-8: from the 3B
; descriptor via room_side (edge index from the room id).  Clobbers: A, DE.
;------------------------------------------------------------------------------
door_find:
                dec  a                         ; Z: dx = 1 (right)
                ld   a, RDX_R
                ld   c, ROOM_COLS - DOOR_COLS
                jr   z, .r
                ld   a, RDX_L
                ld   c, 0
.r:             push bc
                call room_side                 ; (bank 2) CF; B = storey, E = edge
                ld   a, b
                pop  bc                        ; C = the door col
                ret  nc
                MUL_STOREY b
                add  a, DOOR_PLANK_DY
                ld   b, a
                ld   a, e
                add  a, EDGE_TAB & $FF
                ld   l, a
                ld   h, EDGE_TAB >> 8
                scf
                ret
                ASSERT (EDGE_TAB >> 8) == ((EDGE_TAB + EDGES_H - 1) >> 8)

;------------------------------------------------------------------------------
; door_paint — the planks of the door at cols C, C+1, rows B .. B+5: A = 0
; open (jambs T_DOOR_JAMB_L / _R, non-solid) / else closed (T_DOOR_L / T_DOOR_R: never called on a locked
; door). ROOM_MAP, the bank-7 attr shadow (shadow_rect), then
; PEND_DMG so the next render restores the 2 x 6 cells (the potion-pickup
; path; a closed door's cells are free of bodies, an opened one's too).
; Clobbers: all but IX.   ~7k T (measured: tests/world.py W5)
;------------------------------------------------------------------------------
door_paint:
                or   a
                ld   de, (T_DOOR_JAMB_L << 8) | T_DOOR_JAMB_R   ; open: the jambs (B10)
                jr   z, .p
                ld   de, (T_DOOR_L << 8) | T_DOOR_R
.p:             push bc
                ld   a, DOOR_PLANK_H
.r:             push af
                call cell_addr                 ; (bank 2) HL; keeps BC, DE
                ld   (hl), d
                inc  l                         ; col 0 -> 1 / 30 -> 31: same row
                ld   (hl), e
                inc  b
                pop  af
                dec  a
                jr   nz, .r
                pop  bc
                ld   de, (DOOR_COLS << 8) | DOOR_PLANK_H
                ld   a, (PORT_7FFD_SHADOW)     ; B3B-R2: the caller's $C000 bank back
                push af                        ; after shadow_rect (bank 7): a monster
                push bc                        ; opening a door runs under the bank-3
                push de                        ; monster phase (try_step -> mon_door)
                call shadow_rect
                pop  de
                pop  bc
                pop  af
                call restore_page              ; keeps BC, DE
                jp   queue_damage

;------------------------------------------------------------------------------
; door_open — A = dx of a body whose step runs into a closed plank (that
; side's door). Locked / sealed: CF = 0, nothing changes. Else EG_OPEN is set
; (both rooms read it) and the planks become AIR: CF = 1 (the turn is spent,
; nothing moves: game.md §2.3, §9.1).  Clobbers: all but IX.
;------------------------------------------------------------------------------
door_open:
                call door_find
                ld   a, (hl)
                and  EG_LOCK | EG_SEAL
                ret  nz                        ; CF = 0 (and)
                set  EG_OPEN_BIT, (hl)
                ld   a, SFX_DOOR               ; SND-5: any opener (hero or monster)
                call sfx_req
                xor  a
                call door_paint
                scf
                ret

;------------------------------------------------------------------------------
; mon_door — try_step's step into a closed plank, IX = monster, A = dx: an
; opener (KF_OPENER, never a flyer) opens it instead of moving, spending its
; turn (CF = 1, nothing moves); a non-opener, a flyer or a locked / sealed
; door: blocked (CF = 0; its AI tries its next choice or waits, §9.1).
; Clobbers: all but IX.
;------------------------------------------------------------------------------
mon_door:
                ld   b, a
                ld   a, (YIELD_FLAG)           ; a yield step never opens a door:
                or   a                         ; blocked, so the yield tries the
                ret  nz                        ; other side (CF = 0: or a)
                KFIELD KT_FLAGS
                and  KF_OPENER | KF_FLYER
                cp   KF_OPENER
                ld   a, b
                jr   z, door_open
                or   a
                ret

;------------------------------------------------------------------------------
; hero_door — try_horizontal's bump into a closed plank, IX = hero, A = dx.
; Opens it and faces it (CF = 1: 1 turn, 2 ticks), or prints that it is
; locked (CF = 0: no turn, F4).  Clobbers: all but IX.
;------------------------------------------------------------------------------
hero_door:
                call door_open
                jr   nc, .locked
                call face_tmp6
                scf
                ret
.locked:        ld   hl, LOCK_SHOWN            ; once per press: read_turn_input
                ld   a, (hl)                   ; clears it when no key is held
                or   a
                ret  nz                        ; CF = 0
                inc  (hl)
                ld   a, TX_LOCKED
                call msg_push                  ; B3B-11: queued (panel_tick)
                or   a
                ret

;------------------------------------------------------------------------------
; try_close — key C (3B stand-in, game.md §1.4 / §2.3), IX = hero. Legal
; when standing, no hostile in reach on either side, and the faced side has
; an open (so unlocked) door on the hero's storey, adjacent (x + w = 30 /
; x = 2), its 2 x 8 cells (lintel .. planks) free of bodies. CF = 1 closed
; (1 turn), CF = 0 refused (no turn).  Clobbers: all but IX; TMP0..TMP7.
;------------------------------------------------------------------------------
try_close:
                call is_standing
                jr   nz, .no
                ld   a, 1                      ; dx = facing
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .f
                ld   a, $FF
.f:             ld   (TMP6), a
                call get_box                   ; C = x, D = w
                ld   a, d
                ld   (TMP4), a                 ; w
                ld   a, (TMP6)
                dec  a
                ld   a, c
                jr   nz, .lft
                add  a, d
                cp   ROOM_COLS - DOOR_COLS     ; right: x + w == 30
                jr   .adj
.lft:           cp   DOOR_COLS                 ; left: x == 2
.adj:           jr   nz, .no
                call storey_ref
                ld   (TMP7), a
                ld   a, (TMP6)
                call door_find                 ; HL = edge, C = door col, B = plank top
                jr   nc, .no                   ; no exit on that side
                ld   a, (hl)
                and  EG_DOOR | EG_OPEN | EG_LOCK | EG_SEAL
                cp   EG_DOOR | EG_OPEN
                jr   nz, .no
                ld   a, (TMP7)                 ; the door is on the hero's storey
                MUL_STOREY d
                add  a, DOOR_PLANK_DY
                cp   b
                jr   nz, .no
                push hl
                push bc
                ld   a, b
                sub  DOOR_PLANK_DY
                ld   b, a                      ; B = 9s (lintel row)
                ; door cells (2 x 8 from the lintel) free of EVERY body of the
                ; room, PENDING arrivals included (a follower parked at x = 1)
                ld   de, (DOOR_COLS << 8) | STOREY_AIR
                xor  a
                call room_bodies
                jr   c, .nop
                ; no living hostile within 2 cols of the hero or the door
                ; (game.md §2.3, designer 2026-10-03): gap <= 2 empty cols, so
                ; the hero + door span widened by 3 cols, over the storey's air
                ; rows (the other side of the span is the room edge)
                ld   a, c
                or   a
                ld   a, (P_ENTITIES + E_X)
                jr   z, .hl
                sub  3                         ; right door: from x - 3, 32 cols (the
                ld   c, a                      ; excess right of col 31 holds nobody)
                ld   d, ROOM_COLS
                jr   .hs
.hl:            ld   hl, TMP4                  ; left door: cols 0 .. x + w + 2
                add  a, (hl)
                add  a, 3
                ld   d, a
.hs:            ld   a, EF_HOSTILE
                call room_bodies
.nop:           pop  bc
                pop  hl
                jr   c, .no
                res  EG_OPEN_BIT, (hl)
                ld   a, 1
                call door_paint
                scf
                ret
.no:            or   a
                ret

;------------------------------------------------------------------------------
; room_bodies — CF = 1 if an entity in slots 1..15 is ACTIVE, in CUR_ROOM,
; not DYING, has every flag of A (0 = any body; PENDING ones count), and its
; box overlaps box C,B,D,E.  Keeps BC, DE.  Clobbers: A, HL, IX (= hero on
; return), TMP5.
;------------------------------------------------------------------------------
room_bodies:
                or   EF_ACTIVE
                ld   (TMP5), a
                ld   ix, P_ENTITIES
                ld   l, P_MAX_ENT - 1
.l:             push hl
                push de
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                ld   a, (TMP5)
                ld   h, a
                ld   a, (ix+E_FLAGS)
                and  h
                cp   h
                jr   nz, .n
                bit  EF_DYING_BIT, (ix+E_FLAGS)
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call box_vs_ix                 ; keeps BC, DE
                jr   c, .hit
.n:             pop  hl
                dec  l
                jr   nz, .l
                ld   ix, P_ENTITIES
                or   a
                ret
.hit:           pop  hl
                ld   ix, P_ENTITIES
                scf
                ret

;------------------------------------------------------------------------------
; climb_blocked — try_climb's step (IX = hero, box C = x, B = the NEW y,
; D = w, E = h; TMP6 = dy) overlaps a body; HL -> that body's LIVE_LIST
; entry, h byte (box_free's hit). B14 rules (prototype §6.4 "B14 fix rules",
; designer 2026-10-04):
;  - first block by this body (CLIMB_BLK_ID / CLIMB_BLK_N): a WAIT turn
;    (CLIMB_BLK = 1, CF = 0; try_player_turn makes it the wait) whose monster
;    phase yields to the climb: E_AIDIR = dy, cork_check reads CLIMB_BLK;
;  - B18: a repeat block by the same body that MOVED since its last block
;    (CLIMB_BLK_XY: it is yielding, 1 col a turn), or by another body, is
;    another such wait, up to CLIMB_SQZ_N blocks in a row (any blockers);
;  - a repeat block by the SAME body that did not move (or the CLIMB_SQZ_N + 1th
;    in a row): SQUEEZE PAST. The hero takes
;    the step (mid-ladder, M_MOVE; costs his turn, CF = 1); every body in the
;    hero's new box is moved to the standing box at the shaft col on the
;    storey the climb leaves (x = the hero's, y = 9t+8-h: "the hero's foot
;    cell") and goes PENDING in place (the §3.6 arrival-conflict mechanism:
;    hidden, collides with nothing, does not act — no free attack — and
;    materialises when that box is free; facing kept). Any kind, no exclusions.
;    B16: a FLYER of the other storey (s != t) keeps its x / y and only goes
;    PENDING — the foot cell is not in its air band; moving it there dropped
;    a ghost over the top box onto the floor below (flyers never leave their
;    band, prototype §3.5). Same storey: the foot cell is its band bottom.
;    B19: a body whose foot cell already holds a live monster (box_free_mon)
;    or a PENDING body (pend_hit) stays PENDING in place, never stacked.
;    Log: "YOU SQUEEZE PAST THE <NAME>" (impact_line, MSG_SQUEEZE).
; read_turn_input clears CLIMB_BLK_N after every other consumed turn
; (CLIMB_BLK = 0: a move, a wait, a climb that went through); level_reset
; too. (A chord DOWN + L/R whose climb is blocked keeps the count even if its
; horizontal fallback moves: the hero insisted on the climb.)
; Clobbers: all; IX = hero on return.  Cold (input tick of a blocked climb).
;------------------------------------------------------------------------------
climb_blocked:
                dec  hl
                dec  hl                        ; -> the entry's ptr hi
                push de                        ; (D, E = the hero's box: the squeeze's)
                ld   d, (hl)
                dec  hl
                ld   e, (hl)                   ; DE = the blocker's entity
                dec  hl                        ; -> the entry's slot byte
                ld   a, (hl)
                ld   hl, CLIMB_BLK_ID
                cp   (hl)
                ld   (hl), a                   ; (ld / inc rr / ex keep Z)
                inc  hl                        ; -> CLIMB_BLK_N
                ex   de, hl
                inc  hl
                inc  hl
                inc  hl                        ; -> E_X
                ld   a, (hl)
                inc  hl
                ld   h, (hl)                   ; E_Y
                ld   l, a
                ex   de, hl                    ; DE = its (x, y), HL -> CLIMB_BLK_N
                ASSERT E_X == 3 && E_Y == 4
                jr   z, .same
                ld   a, (hl)                   ; another blocker in the same run of
                or   a                         ; blocks (review: A / B alternating
                jr   z, .one                   ; blockers): the count goes on, so
                jr   .cap                      ; the cap still ends the run
.same:          ld   a, (hl)
                or   a
                jr   z, .one
                ; B18 / D-AI1a: the 2nd block squeezed even when the blocker had
                ; just stepped aside — one 1-col yield step can't clear a 3-col
                ; climb path (a body on the shaft col needs up to its width), so a
                ; yielding walker was swapped onto the other storey ("the hero
                ; lands on it", "the rat drops a storey"). Now a blocker that moved
                ; since the last block earns another wait; the squeeze fires when it
                ; did not move (it can't yield) or after CLIMB_SQZ_N blocks of any
                ; bodies (the
                ; anti-softlock guarantee stays: a yield can't oscillate for ever).
                push hl
                ld   hl, (CLIMB_BLK_XY)
                or   a
                sbc  hl, de
                pop  hl
                jr   z, .sqz                   ; no progress: it can't yield
                ld   a, (hl)
.cap:           cp   CLIMB_SQZ_N
                jr   nc, .sqz
                inc  (hl)
                jr   .wt
.one:           ld   (hl), 1
.wt:            ld   (CLIMB_BLK_XY), de
                pop  de
                ld   a, (TMP6)                 ; the climb the monster phase
                ld   (ix+E_AIDIR), a           ; yields to (cork_check)
                ld   a, 1
                ld   (CLIMB_BLK), a
                xor  a                         ; CF = 0: the caller's wait
                ret
.sqz:           pop  de
                ld   (hl), 0
                ld   a, (TMP6)
                ld   (ix+E_AIDIR), a
                inc  a                         ; Z: up ($FF)
                ld   a, (ix+E_Y)               ; down: the storey of the top row
                jr   nz, .dn
                add  a, e
                dec  a                         ; up: the storey of the bottom row
.dn:            add  a, KT_DIV9 & $FF
                ld   l, a
                ld   h, (kind_tab + KT_DIV9) >> 8
                ld   a, (hl)                   ; t (rows 0..17: 0 / 1)
                call storey_row                ; 9t+7 (keeps BC)
                inc  a
                ld   (TMP7), a                 ; the floor row the bodies stand on
                ld   (ix+E_Y), b               ; the hero's step
                ld   (ix+E_MODE), M_MOVE
                ld   a, $FF
                ld   (TMP5), a                 ; kind of the first body moved
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   a, 1
.l:             push af
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call box_vs_ix                 ; in the hero's new box?
                jr   nc, .n
                ld   (ix+E_MODE), M_REST
                set  EF_PENDING_BIT, (ix+E_FLAGS)
                KFIELD KT_FLAGS                ; B16: the foot cell is in a flyer's
                and  KF_FLYER                  ; band only on its own storey: one
                jr   z, .mv                    ; of the other storey stays PENDING
                call storey_ref                ; in place (else it was dropped onto
                call storey_row                ; the floor below / lifted above;
                inc  a                         ; flyers never leave their band,
                ld   hl, TMP7                  ; §3.5). A = 9s+8 vs 9t+8
                cp   (hl)
                jr   nz, .kind
.mv:            pop  af                        ; B19: the foot cell already holds a live
                push af                        ; monster -> PENDING in place instead: a
                ld   (ACT_SLOT), a             ; hidden body stacked under a live one
                push bc                        ; popped up on its corpse when it died
                push de                        ; (materialise: DYING bodies don't collide)
                KFIELD KT_BW
                ld   d, a
                KFIELD KT_BH
                ld   e, a
                ld   a, (TMP7)
                sub  e
                ld   b, a                      ; C = the hero's col (the foot cell)
                call box_free_mon
                call nc, pend_hit              ; (review) or one already PENDING there
                ld   a, b
                pop  de
                pop  bc
                jr   c, .kind
                ld   (ix+E_X), c
                ld   (ix+E_Y), a
.kind:          ld   a, (TMP5)
                inc  a
                jr   nz, .n
                ld   a, (ix+E_KIND)
                ld   (TMP5), a
.n:             push de
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                pop  af
                inc  a
                cp   P_MAX_ENT
                jp   c, .l                     ; (out of jr range since B19)
                xor  a
                ld   (ACT_SLOT), a             ; (the hero's turn: 0, try_player_turn)
                call build_live                ; PENDING ones stop colliding
                ld   a, (TMP5)
                ld   c, a
                ld   b, MSG_SQUEEZE
                call impact_line
                ld   ix, P_ENTITIES
                scf
                ret
                ASSERT CLIMB_BLK_N == CLIMB_BLK_ID + 1

;------------------------------------------------------------------------------
; hero_fall — try_horizontal moved the hero (IX) onto x == the pit col on the
; storey-0 floor (game.md §2.5): it lands on storey 1, same x (y += 9; the
; anim plays the step, then the 9-row drop: M_FALL), a monster in the landing
; box goes PENDING in place (arrival_conflicts, prototype §3.6), 1d4 damage
; ignoring DEF (HURT on landing, DEATH at 0 HP). CF = 1 (the walk's turn).
; Clobbers: all; IX = hero on return.
;------------------------------------------------------------------------------
hero_fall:
                ld   a, SFX_FALL               ; SND-5 (a jump into the pit: replaces JUMP)
                call sfx_req
                ld   (ix+E_MODE), M_FALL
                ld   a, (ix+E_Y)
                add  a, STOREY_ROWS
                ld   (ix+E_Y), a
                ld   hl, arrival_conflicts     ; bank 7 since L-RELIEF (the hero's new box;
                call far7                      ; far7 = far3 +12 T, its jr to farb)
                call build_live                ; PENDING ones stop colliding
                ld   ix, P_ENTITIES
                ld   c, FALL_DIE
                call rng_mod
                inc  a
                ld   b, a
                ld   a, (ix+E_HP)
                sub  b
                jr   nc, .hp
                xor  a                         ; saturating
.hp:            ld   (ix+E_HP), a
                ld   (ix+E_REACTAT), 0         ; plays on landing (anim: REST again)
                ld   c, RC_HURT
                or   a
                jr   nz, .r
                set  EF_DYING_BIT, (ix+E_FLAGS)
                ld   c, RC_DEATH
.r:             ld   (ix+E_REACT), c
                ld   a, TX_FALL
                call msg_push                  ; B3B-11: queued (panel_tick)
                scf
                ret

;------------------------------------------------------------------------------
; try_jump — UP + LEFT / RIGHT (game.md §2.4, J1 2026-10-06), IX = hero, A =
; the PLAYER_DIR E/W bits (E wins: dx 1, else -1). Legal when standing (not
; mid-ladder), not on the turn right after a jump (JUMP_TURN), and:
; - D: the box at x + 6dx free -> D = 6; holding only low bodies (jump_bodies:
;   h <= 2 rows, w <= 4 cols, standing: Slime, Rat / Spider, a Bat in the 2
;   band rows above the floor) -> D = 7, legal iff the box at x + 7dx holds
;   no body (an adjacent Rat is cleared, one at r >= x+4 blocks); any other
;   body there -> illegal.
; - x' = x + D dx inside the body limits (cols 1..30: no exit by jumping).
; - storey-0 pit p (width W, pit_w): x' in p .. p+W-3 (body fully over holes)
;   -> the hero falls at x_f = x'; a WIDE pit (W >= 4) with a hole col in the
;   cleared span (x+3 .. x'-1 / x'+3 .. x-1) cuts the arc short: x_f = p+W-3
;   (right) / p (left). Else x_f = x'.
; - the landing box at x_f free of every body, the swept box (cols x+1 ..
;   x_f+w-1 / x_f .. x+w-2, rows y-2 .. y+h-1) holding no solid cell (wall,
;   block, door / arch / lintel) and no body but low ones.
; CF = 1: x = x_f, M_JUMP, JUMP_ARC = n (2 |x_f - x| airborne ticks) | D7 |
; FALL; a fall also runs hero_fall (y += 9, 1d4, landing conflicts) with the
; mode kept M_JUMP (anim plays the arc, then M_FALL). CF = 0: no turn.
; Not modelled yet: 2 FOOD, Weak, frozen.
; Clobbers: all; IX = hero on return; TMP6 (dx), TMP7 (x_f).  Cold (once a turn).
;------------------------------------------------------------------------------
try_jump:
                ASSERT DIR_E_BIT == 0          ; the AND below yields dx 1 for E
                and  1 << DIR_E_BIT            ; A = the E/W bits: E -> dx 1, W -> $FF
                jr   nz, .dx
                dec  a
.dx:            ld   (TMP6), a
                call is_standing
                jp   nz, .no
                ld   hl, (TURN_COUNTER)
                ld   de, (JUMP_TURN)
                or   a
                sbc  hl, de
                jp   z, .no                    ; not two turns in a row
                call get_box                   ; C = x, B = y, D = w, E = h
                ld   a, (TMP6)
                ld   l, a
                add  a, a
                add  a, l
                add  a, a                      ; 6 dx
                add  a, c
                ld   (TMP7), a                 ; x + 6 dx
                ld   a, 2 * JUMP_COLS
                ld   (JUMP_ARC), a             ; D 6, no fall
                push bc
                ld   a, (TMP7)
                ld   c, a
                call box_free                  ; (keeps BC, DE, IX)
                jr   nc, .d6
                call jump_bodies               ; only low bodies there?
                ld   ix, P_ENTITIES
                jp   c, .nobc
                ld   a, (TMP6)
                add  a, c
                ld   c, a
                ld   (TMP7), a                 ; x + 7 dx
                call box_free                  ; .. must hold no body at all
                jp   c, .nobc
                ld   a, (2 * JUMP_COLS7) | (1 << JA_D7_BIT)
                ld   (JUMP_ARC), a
.d6:            pop  bc
                ld   a, (TMP7)                 ; x'
                dec  a                         ; legal: 1 <= x' <= 31 - w, i.e.
                ld   l, a                      ; x' - 1 < 31 - w unsigned (x' <= 0
                ld   a, ROOM_COLS - 1          ; wraps x' - 1 high)
                sub  d
                cp   l
                jr   c, .no
                jr   z, .no
                ld   a, b
                add  a, e
                cp   FLOOR_ROW0
                call z, jump_pit               ; storey 0: TMP7 = x_f, JUMP_ARC
                push bc
                ld   a, (TMP7)
                ld   c, a
                call box_free                  ; landing box: no body at all
                pop  bc
                jr   c, .no
                ld   a, (JUMP_ARC)
                and  JA_N
                rra                            ; |x_f - x| (n even, CF = 0)
                dec  a
                add  a, d
                ld   h, a                      ; swept cols: |x_f - x| + w - 1
                ld   a, (TMP6)
                dec  a
                ld   a, (TMP7)                 ; left: from x_f
                jr   nz, .s0
                ld   a, c
                inc  a                         ; right: from x + 1
.s0:            ld   c, a
                ld   d, h
                ld   a, b
                sub  JUMP_RISE
                ld   b, a                      ; rows y - 2 ..
                ld   a, e
                add  a, JUMP_RISE
                ld   e, a                      ; .. y + h - 1
                call box_solid                 ; (bank 2)
                jr   c, .no
                call jump_bodies
                ld   ix, P_ENTITIES
                jr   c, .no
                ld   a, (TMP7)
                ld   (ix+E_X), a
                ld   (ix+E_MODE), M_JUMP
                ld   a, SFX_JUMP               ; SND-5 (F only)
                call sfx_req
                ld   (ix+E_TMR), 0             ; arc tick
                ld   a, (TMP6)
                call face_a
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (JUMP_TURN), hl           ; the next turn may not jump
                ld   a, (JUMP_ARC)
                bit  JA_FALL_BIT, a
                scf                            ; (keeps Z)
                ret  z
                call hero_fall                 ; y += 9, 1d4, conflicts; IX = hero
                ld   (ix+E_MODE), M_JUMP       ; the arc plays first (anim)
                scf
                ret
.nobc:          pop  bc
.no:            or   a
                ret

;------------------------------------------------------------------------------
; jump_pit — try_jump on the storey-0 floor: C = x, TMP6 = dx, TMP7 = x',
; JUMP_ARC = n | D7. Pit p, width W (pit_w; game.md §2.4 "Landing in a pit",
; §2.5): x' in p .. p+W-3 -> fall at x'; else W >= 4 and a hole col in the
; cleared span -> fall at x_f = p+W-3 (right) / p (left), n = 2 |x_f - x|.
; Sets JA_FALL_BIT on a fall.  Keeps BC, DE.  Clobbers: A, HL
;------------------------------------------------------------------------------
jump_pit:
                push bc
                ld   a, (TMP7)
                ld   c, a
                call pit_range                 ; H = p, L = W - 2 (p = 0: no pit)
                pop  bc
                jr   c, .fall                  ; p <= x' <= p+W-3: x_f = x'
                inc  h
                dec  h
                ret  z                         ; no pit
                ld   a, l
                cp   2
                ret  c                         ; narrow: never cut short
                ld   a, (TMP6)
                dec  a
                jr   nz, .left
                ld   a, (TMP7)                 ; right: hole in x+3 .. x'-1 iff
                dec  a                         ; p <= x'-1 and p+W-1 >= x+3
                cp   h
                ret  c
                ld   a, h
                add  a, l
                sub  2
                cp   c
                ret  c
                ld   a, h
                add  a, l
                dec  a                         ; x_f = p+W-3
                jr   .cut
.left:          ld   a, h                      ; left: hole in x'+3 .. x-1 iff
                cp   c                         ; p <= x-1 and p+W-1 >= x'+3
                ret  nc
                add  a, l
                dec  a
                ld   l, a
                ld   a, (TMP7)
                cp   l
                ret  nc
                ld   a, h                      ; x_f = p
.cut:           ld   (TMP7), a
                sub  c
                jr   nc, .ab
                neg                            ; |x_f - x|
.ab:            add  a, a
                ld   l, a                      ; n = 2 |x_f - x|
                ld   a, (JUMP_ARC)
                and  ~JA_N & $FF
                or   l
                ld   (JUMP_ARC), a
.fall:          ld   a, (JUMP_ARC)
                set  JA_FALL_BIT, a
                ld   (JUMP_ARC), a
                ret

; pit_range — C = x of a body standing on the storey-0 floor (game.md §2.5,
; §1.1 "Wide pit" (4)): CF = 1 iff the room has a pit p and p <= x <= p+W-3
; (a 3-col hero body fully over holes: it falls; walkers refuse every such
; x). Out: H = p (0 = no pit, CF = 0), L = W - 2 (the fall-range size).
; Keeps BC, DE.  Clobbers: A, HL.   ~150 T
pit_range:
                call cur_room_desc             ; (bank 2) HL = descriptor
                ld   a, l
                add  a, RD_PITCOL
                ld   l, a
                ld   a, (hl)
                push af                        ; p
                call pit_w.d                   ; A = W
                sub  2
                ld   l, a
                pop  af
                ld   h, a
                or   a
                ret  z                         ; no pit: CF = 0
                ld   a, c
                sub  h                         ; x - p (x < p wraps high: no carry)
                cp   l
                ret

; pit_w — A = the current room's pit width W (holes p .. p+W-1): the
; descriptor's L2_PITW (4..6, the L2 wide pit), 0 there = PIT_W_NARROW.
; .d: HL -> the descriptor's RD_PITCOL byte (same 16-B page).  Clobbers: A, HL
pit_w:          call cur_room_desc
                ld   a, l
                add  a, RD_PITCOL
                ld   l, a
.d:             ld   a, l
                add  a, L2_PITW - RD_PITCOL
                ld   l, a
                ld   a, (hl)
                or   a
                ret  nz
                ld   a, PIT_W_NARROW
                ret
                ASSERT (ROOM_DESC & (RD_STRIDE - 1)) == 0 && L2_PITW < RD_STRIDE && RD_PITCOL < L2_PITW

; jump_bodies — CF = 1 if a LIVE_LIST body (not the hero, not DYING) overlaps
; box C,B,D,E and is not low (h <= 2, w <= 4 (J1: Rat / Spider), standing).
; Keeps BC, DE.  Clobbers: A, HL, IX
jump_bodies:
                ld   hl, LIVE_LIST
                ld   a, (LIVE_N)
.l:             or   a
                ret  z                         ; CF = 0
                push af
                push hl
                ld   a, (hl)
                or   a
                jr   z, .n                     ; slot 0: the hero
                inc  hl
                ld   a, (hl)
                ld   ixl, a
                inc  hl
                ld   a, (hl)
                ld   ixh, a
                bit  EF_DYING_BIT, (ix+E_FLAGS)
                jr   nz, .n
                call box_vs_ix
                jr   nc, .n
                KFIELD KT_BH
                cp   3
                jr   nc, .hit
                KFIELD KT_BW
                cp   5                         ; J1: 32-px Rat / Spider are low
                jr   nc, .hit
                call is_standing
                jr   nz, .hit
.n:             pop  hl
                ld   a, l
                add  a, 5                      ; LIVE_LIST stride (one page)
                ld   l, a
                pop  af
                dec  a
                jr   .l
.hit:           pop  hl
                pop  af
                scf
                ret
                ASSERT (LIVE_LIST & $FF) + P_MAX_ENT * 5 <= 256

;==============================================================================
; vis_reset / vis_room_sync — THE render-state resync of every "new world
; state" path. CONTRACT (A7 review, bugs B7/B7b): render runs FIRST in a tick
; (RENDER_FIRST) from the previous tick's anim_tick output (R_VIS / R_FID /
; RLIST), so any path that changes CUR_ROOM or rewrites the entity table
; must call one of these before play_loop renders again:
;   vis_reset     — the entity table was rewritten: new_game (and, Stage 3B,
;                   every level change / stairs). Every slot hidden, so a
;                   stale R_FID (the dead hero's frame, a monster of the last
;                   game) can never be drawn; the first anim_tick refills it.
;                   (B7b: new game after death drew the old game's slots and
;                   the hero with a frame of the previous hero.)
;   vis_room_sync — CUR_ROOM changed, slots kept (do_exit): hide every slot
;                   not live in CUR_ROOM (not ACTIVE, PENDING, other room);
;                   the hero keeps R_VIS / R_FID = its last frame (valid), so
;                   it is drawn at its arrival position on the first tick.
;                   (B7: every monster of the room just left was drawn at its
;                   old position on the new room for one tick.)
; Both rebuild RLIST (ascending, slot 0 first, as anim_tick does) from the
; slots still visible or drawn (E_DVIS bit 0; hide_sprites / new_game cleared
; it, so today = the visible ones), so render never walks a stale list.
; D3-8b: both end with vis_tail (far7): D3-8d mk_room (every status mark
; forgotten, rebuilt from ST_FLAGS), then drip_room (the drip sources).
; Cold (room change / new game only).  Clobbers: A, BC, DE, HL, IX.
;==============================================================================
vis_reset:
                call fx_reset                  ; D3-5: no FX track survives a world rewrite
                ld   hl, SLOTREC + R_VIS
                ld   b, P_MAX_ENT
.z:             ld   (hl), 0
                ld   a, l
                add  a, SLOTREC_STRIDE         ; SLOTREC: 16 records in one page
                ld   l, a
                djnz .z
vis_room_sync:
                ld   ix, P_ENTITIES
                ld   hl, SLOTREC + R_VIS
                ld   de, P_ENT_STRIDE
                ld   bc, (P_MAX_ENT << 8) | (RLIST & $FF)  ; C = RLIST write ptr
.l:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .hide
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   z, .chk
.hide:          ld   (hl), 0
.chk:           ld   a, (hl)
                or   a
                jr   nz, .add                  ; visible
                bit  0, (ix+E_DVIS)
                jr   z, .n                     ; neither visible nor drawn
.add:           ld   a, l
                rrca
                rrca
                rrca
                rrca                           ; slot = L / 16 (R_VIS = 0)
                push hl
                ld   l, c
                ld   h, RLIST >> 8
                ld   (hl), a
                pop  hl
                inc  c
.n:             ld   a, l
                add  a, SLOTREC_STRIDE
                ld   l, a
                add  ix, de
                djnz .l
                ld   a, c
                sub  RLIST & $FF
                ld   (RLIST_N), a
                ld   hl, vis_tail              ; D3-8b / D3-8d (bank 7): the marks forgotten,
                jp   far7                      ; the new room's drip sources (forgets a drop)
                ASSERT (SLOTREC & $FF) == 0 && R_VIS == 0 && P_MAX_ENT * SLOTREC_STRIDE == 256
                ASSERT (RLIST & $FF) + P_MAX_ENT <= 256

;==============================================================================
; clear_screen — bitmap 0, attrs = A.   Clobbers: BC, DE, HL
; (D3-S2: clear_screen / print_char / print_str moved here from bank 2 —
; cold: boot, the paging-lock message, level cards, menus.)
;==============================================================================
clear_screen:
                push af
                ld   hl, SCREEN_BITMAP
                ld   de, SCREEN_BITMAP + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ld   (hl), 0
                ldir
                pop  af
                ld   hl, SCREEN_ATTR
                ld   de, SCREEN_ATTR + 1
                ld   bc, SCREEN_ATTR_LEN - 1
                ld   (hl), a
                ldir
                ret

;==============================================================================
; TEXT (ROM charset, 48K ROM paged): the select screen and the paging-lock
; message only (both drawn on the displayed bank-5 screen, no present). Play
; text is the 6x8 panel font (print6, panel.asm; B3B-11).
; print_char — A = ASCII 32..127 at cell (row B, col C); C advances.
; Clobbers: A, DE, HL.
;==============================================================================
print_char:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, ROM_CHARSET - 32 * 8
                add  hl, de
                ex   de, hl                    ; DE = glyph
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   l, a
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e                         ; A7b: ROM glyphs are 8-aligned (-14 T/char)
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                inc  c
                ret
                ASSERT (ROM_CHARSET & 7) == 0

; print_str — HL = 0-terminated string at (row B, col C). C advances.
; Clobbers: A, C, DE, HL
print_str:
                ld   a, (hl)
                or   a
                ret  z
                push hl
                call print_char
                pop  hl
                inc  hl
                jr   print_str

;==============================================================================
; A7 display switching (cold; bank 5 low RAM is always mapped, so bank-2 and
; bank-5 callers alike reach it). page_bank / present stay in bank 2 (hot).
; set_screen — show bank 5 (A = 0) or bank 7 (A = P7FFD_SCREEN7); the $C000
; bank stays as it is. Order: page_bank SMC, shadow, port (shadow before OUT:
; the A8 ISR re-OUTs the shadow as it finds it and never reads the SMC, so an
; interrupt anywhere in here at worst shows the new screen a few T early).
; Clobbers: A, BC.   ~90 T
;==============================================================================
set_screen:
                or   P7FFD_ROM48
                ld   (page_bank.scr+1), a     ; SMC: every later page_bank keeps it
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                and  7                        ; current $C000 bank
                or   b
                ld   (PORT_7FFD_SHADOW), a
                ld   bc, PORT_7FFD
                out  (c), a
                ret

; show_bank5 — display the composed screen itself (select, transitions, A7).
; Clobbers: A, BC
show_bank5:
                xor  a
                jr   set_screen

;------------------------------------------------------------------------------
; present_full — the whole bank-5 screen to screen 2, mask cleared, then show
; bank 7 (start_game; the end of a room transition). Leaves bank 7 paged.
; Clobbers: A, BC, DE, HL.   6,912 x 21 T = 145k T + contention (cold).
;------------------------------------------------------------------------------
present_full:
                ld   a, BANK_SCREEN7
                call page_bank
                ld   hl, SCREEN_BITMAP
                ld   de, SCREEN7_BITMAP
                ld   bc, SCREEN_FRAME_LEN
                ldir
                ld   hl, PRES_MASK
                ld   b, PRES_LEN
                xor  a
.c:             ld   (hl), a
                inc  l
                djnz .c
                ld   (PRES_ANY), a
                ld   hl, HUD4_PW
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a                   ; text rows are in sync too
                dec  a
                ld   (PRES_RMIN), a            ; $FF: no marked row
                ld   a, P7FFD_SCREEN7
                jp   set_screen

;==============================================================================
; init_kbd_mirror — all released.  Clobbers: A, B, HL
;==============================================================================
init_kbd_mirror:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, KBD_RELEASED
.r:             ld   (hl), a
                inc  hl
                djnz .r
                ret

;==============================================================================
; BOOT-TIME GENERATOR (prototype §5.1/§5.2). Per frame: get the unshifted
; right-facing source out of banks 1/3 (unpack its ZX0 block into
; GEN_SCRATCH once, zx0_frame), then emit each needed variant
; (facing x shift) into the pool banks 0/4/6 with a bump allocator. No variant
; straddles a bank (allocator skips to the next bank). ~70-100 T/output byte.
;==============================================================================
pool_banks:     DB BANK_POOL0, BANK_POOL1, BANK_POOL2

; alloc_reset — pool empty; starts a generator session.   Clobbers: A, HL
; A generator SESSION = alloc_reset/alloc_restore .. the next build_room_map.
; Both entry points drop the ZX0 block cache (GEN_ZBLK): GEN_SCRATCH aliases
; the room maps, so a cached block never outlives its session (A5 review).
alloc_reset:
                xor  a
                ld   (ALLOC_IDX), a
                ld   (GEN_OVERFLOW), a
                ld   hl, POOL_START            ; D3-TX: bank 0 starts above the text
                ld   (ALLOC_PTR), hl
                ld   l, a
                ld   h, a
                ld   (GEN_ZBLK), hl            ; no cached block
                ret

; alloc_mark / alloc_restore — remember/rewind the pool top (hero regen).
; alloc_restore starts a session too (drops GEN_ZBLK). Clobbers: A, HL
alloc_mark:
                ld   a, (ALLOC_IDX)
                ld   (ALLOC_MARK_IDX), a
                ld   hl, (ALLOC_PTR)
                ld   (ALLOC_MARK_PTR), hl
                ret
alloc_restore:
                ld   a, (ALLOC_MARK_IDX)
                ld   (ALLOC_IDX), a
                ld   hl, (ALLOC_MARK_PTR)
                ld   (ALLOC_PTR), hl
                ld   hl, 0
                ld   (GEN_ZBLK), hl            ; no cached block
                ret

; alloc — reserve BC bytes. Out: A = bank, HL = addr, CF = 1 if the pool is full.
; Clobbers: A, DE, HL
alloc:
                ld   a, (ALLOC_IDX)
                cp   3
                ccf
                ret  c                         ; out of banks
                ld   hl, (ALLOC_PTR)
                push hl
                add  hl, bc                    ; end = ptr + size
                jr   nc, .fits                 ; <= $FFFF
                ld   a, h
                or   l
                jr   z, .fits                  ; exactly $10000 also fits
                pop  hl
                ld   hl, ALLOC_IDX              ; next bank, retry
                inc  (hl)
                ld   hl, BANK_WINDOW
                ld   (ALLOC_PTR), hl
                jr   alloc
.fits:
                ld   (ALLOC_PTR), hl
                ld   a, (ALLOC_IDX)
                ld   e, a
                ld   d, 0
                ld   a, h
                or   l
                jr   nz, .same
                ld   hl, BANK_WINDOW           ; ended exactly at $10000: the
                ld   (ALLOC_PTR), hl           ; next alloc opens the next bank
                ld   a, e                      ; (ptr 0 would alias the ROM)
                inc  a
                ld   (ALLOC_IDX), a
.same:          ld   hl, pool_banks
                add  hl, de
                ld   a, (hl)                   ; A = bank of THIS allocation
                pop  hl                        ; HL = start
                or   a                         ; CF = 0
                ret

; build_bitrev — BITREV_TAB[i] = i with bit order reversed.  Boot, ~20k T
build_bitrev:
                ld   hl, BITREV_TAB
.next:          ld   a, l
                ld   b, 8
                ld   c, 0
.bit:           rra
                rl   c
                djnz .bit
                ld   (hl), c
                inc  l
                jr   nz, .next
                ret

; copy_virt_keep (= copy_virt3, the B3B-11b name its bank-3 callers use) —
; copy_virt for code running from a paged bank (far3 / far1 targets: panel_boot
; / pblit read the vdata block in bank 1): hands $C000 back as it found it
; (C3-0: the caller's saved bank, was a hard-coded bank 3 — wrong from bank-1
; code). Out: DE past the copy.  Clobbers: A, F, BC, DE, HL.   copy + ~140 T
copy_virt_keep:
copy_virt3:
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page)
                call copy_virt
                pop  af
                jp   restore_page

; copy_virt — copy BC bytes from VIRTUAL sprite-source address HL (banks 1/3,
; assembled at $8000..$FFFF) to DE (bank 2/5 RAM). Handles the $C000 straddle.
; Clobbers: A, BC, DE, HL
copy_virt:
                ld   a, h
                cp   BANK_WINDOW >> 8
                jr   nc, .hi                   ; $C000.. -> bank 3 as-is
                ; $8000..$BFFF -> bank 1 at +$4000; may run past into bank 3
                push bc
                push de
                push hl
                ld   a, BANK_SRC_LO
                call page_bank
                pop  hl
                pop  de
                pop  bc
                push hl                        ; avail = $C000 - HL
                ld   a, BANK_WINDOW >> 8
                sub  h
                ld   h, a
                xor  a
                sub  l
                ld   l, a
                jr   nc, .nb
                dec  h                         ; borrow
.nb:            ; HL = avail;  n1 = min(BC, avail)
                push hl
                or   a
                sbc  hl, bc                    ; avail - BC
                pop  hl
                jr   c, .split                 ; BC > avail
                pop  hl
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                ret
.split:         ; copy avail bytes from bank 1, then the rest from bank 3 @ $C000
                push bc                        ; total
                ld   b, h
                ld   c, l                      ; BC = avail
                pop  hl                        ; HL = total
                or   a
                sbc  hl, bc                    ; HL = rest
                ex   (sp), hl                  ; stack = rest, HL = virt src
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                push de
                ld   a, BANK_SRC_HI
                call page_bank
                pop  de
                pop  bc                        ; rest
                ld   hl, BANK_WINDOW
                ldir
                ret
.hi:
                push bc
                push de
                push hl
                ld   a, BANK_SRC_HI
                call page_bank
                pop  hl
                pop  de
                pop  bc
                ldir
                ret

;------------------------------------------------------------------------------
; gen_kind — generate every frame of kind A; a kind with 0 frames (the Rogue
; hole, unused ids) returns at once (djnz with B = 0 would run 256 frames).
; Clobbers: all but IX
;------------------------------------------------------------------------------
gen_kind:
                ld   h, (kind_tab + KT_FID0) >> 8   ; KT_FID0/KT_FCNT: same page
                add  a, KT_FID0 & $FF
                ld   l, a
                ld   a, (hl)                   ; first fid
                ld   c, a
                ld   a, l
                add  a, KT_FCNT - KT_FID0
                ld   l, a
                ld   b, (hl)                   ; count
                inc  b
                dec  b
                ret  z                         ; 0-frame kind: nothing to generate
.f:             push bc
                ld   a, c
                call gen_frame
                pop  bc
                inc  c
                djnz .f
                ret

;------------------------------------------------------------------------------
; gen_frame — generate all variants of frame A into the pool; fill FRT[A].
; The frame is read from its ZX0 block unpacked in GEN_SCRATCH, which
; aliases ROOM_MAP/NEXT_MAP — callable only while no room is built (boot, hero
; start; 3F: level start before build_room_map). A call while GAME_STATE is
; PLAYING/TRANSITION bumps GEN_TRAP (saturating; tests assert 0). The block
; cache (GEN_ZBLK) is valid for one generator session only: alloc_reset /
; alloc_restore drop it (every caller starts with one of them).
; Static data: frame_tab (bank 2: cols, H, offsets) + fdesc_tab (bank 5:
; block, frame address, flags) — no banked descriptor read, no copy_virt.
; Clobbers: all but IX.
;------------------------------------------------------------------------------
gen_frame:
                ld   (GEN_FID), a
                ld   a, (GAME_STATE)           ; GEN_SCRATCH guard (A3 carry-over)
                cp   GS_PLAYING
                jr   z, .trap
                cp   GS_TRANSITION
                jr   nz, .safe
.trap:          ld   hl, GEN_TRAP
                inc  (hl)
                jr   nz, .safe
                dec  (hl)                      ; saturate at 255
.safe:
                ; FRT[fid] = all NONE
                call frt_ptr_cur               ; HL = FRT + fid*16 (A was clobbered)
                ld   b, 4
.clr:           ld   (hl), FRT_NONE
                inc  hl
                inc  hl
                inc  hl
                djnz .clr
                ; read the static entries
                ld   a, (GEN_FID)
                call ft_ptr                    ; HL = frame_tab + fid*4 (FT_COLS)
                ld   a, (hl)
                ld   (GEN_COLS), a
                inc  hl                        ; FT_H
                ld   a, (hl)
                ld   (GEN_H), a
                ; HL = fdesc_tab + fid*5
                ld   a, (GEN_FID)
                ld   l, a
                ld   h, 0
                ld   e, l
                ld   d, h
                add  hl, hl
                add  hl, hl
                add  hl, de
                ld   de, fdesc_tab
                add  hl, de
                ld   e, (hl)                   ; FD_BLK
                inc  hl
                ld   d, (hl)                   ; DE = virt block (raw: virt src)
                inc  hl
                ld   c, (hl)                   ; FD_FRM
                inc  hl
                ld   b, (hl)                   ; BC = frame in GEN_SCRATCH
                inc  hl
                ld   a, (hl)                   ; FD_FLAGS
                ld   (GEN_FLAGS), a
                call zx0_frame                 ; HL = frame in GEN_SCRATCH (no copy)
                ; --- right facing --- (GEN_BASE = the unmirrored source until
                ; mirror_src has read it; gen_variant only reads it)
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFR
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                xor  a
                call gen_facing
                ; --- left facing ---
                ld   a, (GEN_FLAGS)
                and  FF_SYM
                jr   z, .mirror
                call frt_ptr_cur               ; SYM: left = right (no copy)
                ld   d, h
                ld   e, l
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de                        ; DE = variant 2
                ld   bc, 6
                ldir
                ret
.mirror:
                call mirror_src
                ld   hl, GEN_MIR
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFL
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                ld   a, 2
                jp   gen_facing

; gen_facing — A = variant base (0 right / 2 left). Uses GEN_* state.
gen_facing:
                ld   (GEN_VAR), a
                ld   a, (GEN_FLAGS)
                and  FF_MOTION
                jr   z, .stat
                xor  a                         ; MOTION: shift 0 and shift 4
                call gen_variant
                ld   hl, GEN_VAR
                inc  (hl)
                ld   a, 4
                jp   gen_variant
.stat:
    IF PHASE_SHIFT
                ld   a, (GEN_FLAGS)            ; FF_PH4 (= 4): drawn at px & 4 = 4,
                and  FF_PH4                    ; so the shift is (anchor + 4) & 4
                ld   hl, GEN_OFF
                add  a, (hl)
    ELSE
                ld   a, (GEN_OFF)
    ENDIF
                and  7                         ; anchor implies the one shift
                jp   z, gen_variant            ; shift 0 -> variant base
                ld   hl, GEN_VAR
                inc  (hl)                      ; shift 4 -> base + 1
                ld   a, 4
                jp   gen_variant

; gen_variant — emit GEN_BASE shifted by A (0/4) into the pool as variant
; GEN_VAR of GEN_FID. Clobbers: all but IX.
gen_variant:
                ld   (GEN_SHIFT), a
                ; out bytes = (cols + (shift?1:0)) * 2 * H
                ld   a, (GEN_COLS)
                ld   c, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   z, .n
                inc  c
.n:             sla  c                         ; C = out row bytes
                ld   a, (GEN_H)
                call mul8                      ; HL = size
                ld   b, h
                ld   c, l
                call alloc                     ; A = bank, HL = addr
                jr   nc, .ok
                ld   a, 1
                ld   (GEN_OVERFLOW), a
                ret
.ok:
                push hl
                push af
                ; FRT[fid][var] = bank, addr
                call frt_ptr_cur
                ld   a, (GEN_VAR)
                ld   e, a
                add  a, a
                add  a, e
                ld   e, a
                ld   d, 0
                add  hl, de
                pop  af
                ld   (hl), a
                inc  hl
                pop  de                        ; DE = dest addr
                ld   (hl), e
                inc  hl
                ld   (hl), d
                push de
                call page_bank                 ; A = bank
                pop  de
                ld   hl, (GEN_BASE)
                ld   a, (GEN_H)
                ld   b, a
.row:
                push bc
                ld   a, (GEN_COLS)
                ld   b, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   nz, .sh
.cp:            ld   a, (hl)                   ; shift 0: straight copy
                ld   (de), a
                inc  hl
                inc  de
                ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  de
                djnz .cp
                jr   .rowdone
.sh:            ld   c, $FF                    ; prev mask  (transparent feed)
                ld   a, 0
                ld   (TMP0), a                 ; prev data  (empty feed)
.shc:           ld   a, c
                rrca
                rrca
                rrca
                rrca
                and  $F0                       ; prev_m << 4
                ld   c, a
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                and  $0F                       ; m >> 4
                or   c
                ld   (de), a
                inc  de
                ld   c, (hl)                   ; prev_m = m
                inc  hl
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (TMP1), a
                ld   a, (hl)
                ld   (TMP0), a                 ; prev_d = d
                rrca
                rrca
                rrca
                rrca
                and  $0F
                push hl
                ld   hl, TMP1
                or   (hl)
                pop  hl
                ld   (de), a
                inc  de
                inc  hl
                djnz .shc
                ld   a, c                      ; spill column
                rrca
                rrca
                rrca
                rrca
                and  $F0
                or   $0F
                ld   (de), a
                inc  de
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (de), a
                inc  de
.rowdone:
                pop  bc
                djnz .row
                ret

; mirror_src — (GEN_BASE) -> GEN_MIR, each row's columns reversed + bit-reversed.
; GEN_BASE = the frame inside GEN_SCRATCH (ZX0 block).
; Clobbers: A, BC, DE, HL
mirror_src:
                ld   hl, (GEN_BASE)
                ld   de, GEN_MIR
                ld   a, (GEN_H)
                ld   b, a
.row:           push bc
                push de
                call gen_rowbytes              ; A = cols*2
                ld   c, a
                ld   b, 0
                ex   de, hl
                add  hl, bc                    ; HL = dest row end
                ex   de, hl
                ld   a, (GEN_COLS)
                ld   b, a
.col:           dec  de
                dec  de                        ; DE = dest pair (from the right)
                push de
                ld   a, (hl)                   ; mask
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                ld   (de), a
                pop  hl
                ld   a, (hl)                   ; data
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                inc  de
                ld   (de), a
                pop  hl
                pop  de
                djnz .col
                pop  de
                call gen_rowbytes
                add  a, e
                ld   e, a
                jr   nc, .nc
                inc  d
.nc:            pop  bc
                djnz .row
                ret

gen_rowbytes:   ld   a, (GEN_COLS)
                add  a, a
                ret

; mul8 — HL = A * C (unsigned 8x8).  Clobbers: A, B, DE, HL
mul8:
                ld   hl, 0
                ld   d, 0
                ld   e, c
                ld   b, 8
.m:             add  hl, hl
                rla
                jr   nc, .n
                add  hl, de
.n:             djnz .m
                ret

;------------------------------------------------------------------------------
; zx0_frame — DE = VIRTUAL address of the frame's packed block (FD_BLK), BC =
; the frame's address in GEN_SCRATCH (FD_FRM). Unpacks the block into
; GEN_SCRATCH unless it is already there (GEN_ZBLK = one-block cache: blocks
; hold 1-4 consecutive fids of one kind, so gen_kind unpacks each block
; exactly once). The tool guarantees no packed block straddles virtual $C000,
; so the whole stream is in one bank's $C000 window.
; Out: HL = the frame's raw bytes (cols*H*2, in GEN_SCRATCH). $C000 = the
; source bank if a block was unpacked (else unchanged). Clobbers: A, BC, DE, HL.
; Cost: cache hit ~110 T (A5: ~0.4k T incl. the banked 4-B descriptor
; copy_virt, now gone); unpack (once per block) ~1.6 B packed -> raw at
; roughly LDIR speed + Elias bits, e.g. ~25-45k T for a 1.1-1.4 KB block.
;------------------------------------------------------------------------------
zx0_code:
zx0_frame:
                push bc                        ; -> HL on exit
                ld   hl, (GEN_ZBLK)
                or   a
                sbc  hl, de
                jr   z, .have                  ; already unpacked
                ex   de, hl                    ; HL = virt block
                ld   (GEN_ZBLK), hl
                ld   a, h
                cp   BANK_WINDOW >> 8
                ld   a, BANK_SRC_HI            ; (ld keeps CF)
                jr   nc, .pg                   ; virt $C000.. = bank 3 as-is
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a                      ; virt $8000.. = bank 1 at +$4000
                ld   a, BANK_SRC_LO
.pg:            push hl
                call page_bank
                pop  hl
                ld   de, GEN_SCRATCH
                call dzx0_standard
.have:          pop  hl                        ; HL = frame in GEN_SCRATCH
                ret
                INCLUDE "dzx0_standard.asm"
zx0_code_end:
                ASSERT zx0_code_end - zx0_code <= ZX0_BUDGET

;------------------------------------------------------------------------------
; ovl_run — 3E-T1: run a ZX0-packed OVERLAY in the GEN_SCRATCH window
; (docs/memory-map.md "Overlays"). Unpacks the stream into its load address
; and calls it there with the caller's $C000 bank paged; afterwards re-pages
; the caller's bank again (the overlay may page anything: it runs in bank 5).
; GEN_ZBLK is cleared: the window aliases the ZX0 frame cache, so a stale key
; can never make the next zx0_frame skip its unpack.
; Window contract: GEN_SCRATCH .. +GEN_SCRATCH_LEN aliases ROOM_MAP + NEXT_MAP
; — only while neither map is live: boot, the menu, a level start before
; level_show / build_room_map; never during a room transition. In play only
; with ROOM_MAP saved and put back around it and nothing rendering / reading
; the map meanwhile: the modal bag page (page_ovl / page_post, PAGE_MAP_SAVE).
; In : HL = packed stream (in bank C's $C000 window, or bank 2 / 5 RAM),
;      C = the bank holding it, DE = load + entry address (ASSERTed in the
;      overlay's build: load .. load + raw <= GEN_SCRATCH + GEN_SCRATCH_LEN),
;      IX passes to the overlay (A, BC do not).
; Out: the overlay's BC, DE, HL, IX; the caller's $C000 bank (bits 0-2 of the
;      shadow saved at entry; the screen bit is never rolled back).
; Clobbers: A, F (+ whatever the overlay documents).
; Cost: dzx0 (~LDIR rate + Elias bits; tests/ovl.py reports it) + ~290 T.
;------------------------------------------------------------------------------
ovl_run:
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page)
                push de                        ; entry
                ld   a, c
                call page_bank
                call dzx0_standard             ; HL -> DE
                ld   l, c                      ; dzx0_standard returns ONLY through its
                ld   h, c                      ; end marker `inc c / ret z`, so C = 0 here
                                               ; (documented there; 1 B < ld hl, 0)
                ld   (GEN_ZBLK), hl            ; no cached sprite block any more
                pop  hl                        ; HL = entry
                pop  af
                push af
                call restore_page              ; the overlay starts in the caller's bank
                call jp_hl
                pop  af
                jp   restore_page              ; keeps BC; A, F only

;------------------------------------------------------------------------------
; page_run — 3E-T2 the bag page (game.md §3.1 / §8; SPIKE: an empty page),
; from tpt_intent (INTENT = IN_BAG: the I key) or use_slot (FIRE / ENTER on
; the BAG icon): both on the turn-intent path, INPUT phase only, never while
; the hero is held (turn_input drops INTENT then); no turn.
; Play freezes; music and effects play on (not a pause). Open: present_full
; makes screen 2 the composed screen and shows it — that copy is the backup —,
; then page_ovl (bank 1) runs the page overlay in GEN_SCRATCH (ROOM_MAP saved),
; which draws the page on all 24 rows of the bank-5 screen and shows it until
; FIRE / BREAK / ENTER / I.
; Close: screen 2 is shown again at once and copied back over the bank-5
; screen, so room, bodies, panel, log, marks, FX and the cursor come back
; byte for byte (no recompose); page_post (bank 1) resets the input latches.
; Low RAM (not bank 7 / 1): it pages bank 7 for the copy-back and must hand
; any caller's bank back. Out: the caller's $C000 bank (screen 2 shown).
; Clobbers: A, BC, DE, HL (IX, IY kept: pushed here).
; Cost: open ~0.15M T (present_full) + unpack + draw; close ~0.16M T (the
; contended 6,912-B LDIR); tests/page.py measures both.
;------------------------------------------------------------------------------
page_run:
                push ix                        ; IX kept for any caller (tpt_intent: the hero)
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                call present_full              ; screen 2 := bank 5, shown; bank 7 paged
                ld   hl, page_ovl              ; bank 1: state, ovl_run -> the page
                call far1                      ; (back with bank 7 paged)
.closed:                                       ; test probe (no code): the page closed
                ld   a, P7FFD_SCREEN7          ; the backup on view at once ...
                call set_screen
                ld   hl, SCREEN7_BITMAP        ; ... then over the page
                ld   de, SCREEN_BITMAP
                ld   bc, SCREEN_FRAME_LEN
                ldir
                pop  af
                call restore_page
                pop  ix
.post:                                         ; test probe (no code): copied back
                ld   hl, page_post             ; bank 1: ROOM_MAP back, input latches,
                jp   far1                      ; resync_tick

; frt_ptr — HL = FRT + A*16 ; frt_ptr_cur uses GEN_FID.  Clobbers: A, DE, HL
;------------------------------------------------------------------------------
; sel_frt_copy — CF = 0: save the two select idles' FRT rows (boot pool,
; below the alloc mark) to SEL_FRT_SAVE; CF = 1: restore them. start_game's
; gen_kind regenerates the chosen hero's frames ABOVE the mark and re-points
; their FRT rows (incl. its select idle) there; the next hero's gen_kind then
; overwrites that pool region, so without the restore the select screen drew
; whatever the last game left there.  ~1.2k T.  Clobbers: A, BC, DE, HL, TMP0
;------------------------------------------------------------------------------
sel_frt_copy:
                sbc  a, a                      ; A = $FF restore / 0 save
                ld   (TMP0), a
                ld   hl, sel_tab
                ld   de, SEL_FRT_SAVE
                ld   b, 2
.l:             push bc
                push hl
                push de
                ld   a, (hl)                   ; fid
                call frt_ptr                   ; HL = FRT row (DE clobbered)
                pop  de                        ; DE = save cursor
                ld   a, (TMP0)
                or   a
                jr   z, .cp
                ex   de, hl                    ; restore: save -> FRT
.cp:            ld   bc, FRT_STRIDE
                ldir                           ; keeps Z
                jr   z, .nx
                ex   de, hl                    ; DE = save cursor again
.nx:            pop  hl
                inc  hl                        ; sel_tab: 1 B per hero
                pop  bc
                djnz .l
                ret

frt_ptr_cur:
                ld   a, (GEN_FID)
frt_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, FRT
                add  hl, de
                ret

;==============================================================================
; fdesc_tab — frame descriptors (A6), FDESC_STRIDE (5) B per fid, read only
; by gen_frame: FD_BLK (ZX0: virtual packed-block address / raw: virtual
; frame address), FD_FRM (ZX0: GEN_SCRATCH + in-block offset), FD_FLAGS.
; Generated from src/frames.asm (the same list as frame_tab). MUST stay the
; last thing in the cold block (ASSERTed): it is the part that grows.
;==============================================================================
fdesc_tab:
FRM_EMIT = FRM_DESC
                INCLUDE "frames.asm"
FDESC_COUNT     EQU FCTR
fdesc_end:
                ASSERT fdesc_end - fdesc_tab == FDESC_COUNT * FDESC_STRIDE
