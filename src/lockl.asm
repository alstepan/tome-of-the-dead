;==============================================================================
; lockl.asm — LARGER-D T8: the level-key runtime (larger_depths.md §2.1 rev 2 / rev 3, §6; user
; decisions 2026-11-16). Low-RAM cold block (INCLUDEd by lowram.asm): callable from any bank, pages
; nothing. Callers: hero_door (lowram, the bump), lair_hint (lowram, every room entry), build_room_map
; (bank 3, every door it stamps), fi_cells (lowram, room draws + scroll strips), room_show /
; room_shadow (lowram), item_depth (HOT_COPY, the panel).
; State: LF_KEYC / LF_KEYM in LVL_FLAGS = the keys HELD; LVL_KEYROOM / LVL_KEYROOM2 := ROOM_NONE when
; that key is taken; EG_LOCK cleared on unlock (key) or far-side bolt. All of it is level state, so a
; new level / new game (level_gen) resets it. D0 (tutorial) / PROTO (LVL_DEPTH 0): no engine pickup
; (the tutorial keeps its own B-room key, tut_turn.asm tt_glob).
;==============================================================================

;------------------------------------------------------------------------------
; key_find — lair_hint (A = the room just entered, every entry: exit / teleport). The first entry
; into a key room takes its key: held bit set, the key room forgotten (ROOM_NONE: never twice), the
; line, the panel key cell queued (PD_DEPTH). Keeps nothing. Clobbers: AF, BC, DE, HL.
; ~70 T (no key), ~0.5k T + msg_push on a pickup
;------------------------------------------------------------------------------
key_find:
                ld   c, a
                ld   a, (LVL_DEPTH)
                or   a
                ret  z                         ; D0 / PROTO: keyless engine
                ld   a, c
                ld   hl, LVL_KEYROOM
                ld   de, str_key_c
                ld   b, LF_KEYC
                cp   (hl)
                jr   z, .got
                ld   hl, LVL_KEYROOM2
                ld   de, str_key_m
                ld   b, LF_KEYM
                cp   (hl)
                ret  nz
.got:           ld   (hl), ROOM_NONE
                ld   hl, LVL_FLAGS
                ld   a, (hl)
                or   b
                ld   (hl), a
                ld   hl, PANEL_DIRTY
                set  PD_DEPTH_BIT, (hl)
                ex   de, hl
                jp   log_push                  ; (HOT; plain ASCII is a log stream: msgl.asm)

;------------------------------------------------------------------------------
; key_door — hero_door's bump into a closed plank that door_open refused (locked or sealed).
; In : HL = the edge byte, B / C = the planks (door_find), A = dx, IX = hero.
; Sealed (D8): CF = 0 (no key ever opens it). Locked, its colour's key held: the key is used (held bit
; cleared, panel queued), EG_LOCK cleared, the door opens (1 turn), "YOU UNLOCK THE DOOR": CF = 1.
; Locked, no matching key, bumped from its FAR side (the hero's room is not the lock's start-side room,
; EG_NEARR, set by level_gen from the start-side component): the bolt, EG_LOCK cleared and an ordinary
; open, no line: CF = 1. Else CF = 0 (the caller prints THE DOOR IS LOCKED, 0 turns). Never relocks:
; EG_LOCK is gone for the level. A teleport past a lock needs nothing more.
; Clobbers: all but IX.   ~0.15k T + door_open's ~7k
;------------------------------------------------------------------------------
key_door:
                bit  EG_LOCK_BIT, (hl)
                ret  z                         ; sealed: CF = 0 (bit leaves CF; door_open's and cleared it)
                ld   d, LF_KEYC
                bit  EG_LOCKC_BIT, (hl)
                jr   z, .c
                ld   d, LF_KEYM
.c:             ld   e, a                      ; E = dx
                ld   a, (LVL_FLAGS)
                and  d
                jr   z, .nokey
                ld   a, (LVL_FLAGS)
                xor  d                         ; the key is used up
                ld   (LVL_FLAGS), a
                ld   a, (PANEL_DIRTY)
                or   PD_DEPTH
                ld   (PANEL_DIRTY), a
                call .unl
                ld   hl, str_unlock
                call log_push
                scf
                ret
.nokey:         ld   a, e                      ; far side: dx = +1 (the hero in the left room) and the
                inc  a                         ; near room is the right one (EG_NEARR), or dx = -1 and
                ld   a, (hl)                   ; it is the left one
                jr   nz, .p
                xor  EG_NEARR
.p:             and  EG_NEARR
                ret  z                         ; the start side: locked (CF = 0: and)
.unl:           res  EG_LOCK_BIT, (hl)
                jp   door_open.op              ; EG_OPEN, SFX, the planks -> jambs: CF = 1
                ASSERT PD_DEPTH == 1 << PD_DEPTH_BIT

; The T8 log lines: plain ASCII streams in low RAM (the text block had 22 B headroom, 8 in the
; F3_GEN=0 build; tokenised the three lines took 49 B there): log_push copies a stream from any
; address, tk_get passes chars < $80 through.
str_key_c:      DB   "YOU FIND A CYAN KEY", 0
str_key_m:      DB   "YOU FIND A MAGENTA KEY", 0
str_unlock:     DB   "YOU UNLOCK THE DOOR", 0
                ASSERT str_unlock - str_key_m - 1 <= LOG_MAX

;------------------------------------------------------------------------------
; lk_stamp — build_room_map's tail after a door's planks (bank 3; jp here, its ret is ours).
; In : LK_EDGE = the edge byte, HL = the plank-R cell of the door's LAST plank row (9s + 7),
;      C = the door's left col (0 / ROOM_COLS - DOOR_COLS).
; A closed LOCKED door: plank row DOOR_PLATE_DY becomes the plate T_DOOR_LOCK (build_room_map drew
; T_DOOR_R there); LK_TAB[side] := its key colour, else ATTR_PLANK (a sealed column, any other door:
; TILE_ATTRS' own value, so lk_cell / lk_shadow change nothing for it).
; Clobbers: A, DE, HL.   ~0.1k T a door
;------------------------------------------------------------------------------
lk_stamp:
                ld   a, (dr_edge)
                ld   e, ATTR_PLANK
                bit  EG_LOCK_BIT, a            ; (never with EG_OPEN: an unlock clears it first)
                jr   z, .st
                ld   e, ATTR_KEY_C
                and  EG_LOCKC
                jr   z, .c
                ld   e, ATTR_KEY_M
.c:             push de
                ld   de, (DOOR_PLATE_DY - DOOR_PLANK_H + 1) * 32 & $FFFF
                add  hl, de
                pop  de
                ld   (hl), T_DOOR_LOCK
.st:            ld   hl, dr_tab
                ld   a, c
                or   a
                jr   z, .w
                inc  hl
.w:             ld   (hl), e
                ret
dr_edge:        DB   0                         ; build_room_map: the edge byte of the door being drawn
dr_tab:         DB   ATTR_PLANK, ATTR_PLANK    ; plate attr of the last built map's left / right door
                ASSERT DOOR_PLATE_DY < DOOR_PLANK_H && ROOM_COLS == 32

;------------------------------------------------------------------------------
; lk_cell — fi_cells' hook: A = T_DOOR_LOCK at map cell (B, C) (room coords; the screen cell is
; (B + fi_cell.dr, C + fi_cell.dc), as fi_cell): its attr on the bank-5 screen := dr_tab[C >= 16]
; (the last built map is the drawn one: room_show's, or the scroll's NEXT_MAP). Out: A = 0 (< T_ITEM0).
; Keeps BC, DE, HL. Clobbers: A, F.   ~0.2k T (2 or 12 cells a room)
;------------------------------------------------------------------------------
lk_cell:
                push hl
                push bc
                ld   hl, dr_tab
                bit  4, c                      ; C >= 16: the right door
                jr   z, .l
                inc  hl
.l:             ld   a, (fi_cell.dr + 1)
                add  a, b
                ld   b, a
                ld   a, (fi_cell.dc + 1)
                add  a, c
                ld   c, a
                ld   a, (hl)
                push af
                ld   a, b                      ; HL = SCREEN_ATTR + B * 32 + C
                rrca
                rrca
                rrca
                ld   l, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   h, a
                ld   a, l
                and  $E0
                or   c
                ld   l, a
                pop  af
                ld   (hl), a
                pop  bc
                pop  hl
                xor  a
                ret
                ASSERT (SCREEN_ATTR & $3FF) == 0 && T_ITEM0 > 0

;------------------------------------------------------------------------------
; lk_shadow — room_show / room_shadow, bank 7 paged, ROOM_MAP = the room on screen: every T_DOOR_LOCK
; cell of the plank-R cols (1, 31) copies its screen attr (lk_cell's) into the bank-7 attr shadow, so
; erase_rect restores the plate's colour after a sprite crossed it.
; Clobbers: A, B, DE, HL.   ~2.3k T
;------------------------------------------------------------------------------
lk_shadow:
                ld   hl, ROOM_MAP + DOOR_COLS - 1
                ld   b, PLAY_ROWS * 2
.lp:            ld   a, (hl)
                cp   T_DOOR_LOCK
                jr   nz, .n
                push hl
                ld   de, SCREEN_ATTR - ROOM_MAP
                add  hl, de
                ld   a, (hl)
                ld   de, SHADOW_ATTR - SCREEN_ATTR
                add  hl, de
                ld   (hl), a
                pop  hl
.n:             ld   de, ROOM_COLS - DOOR_COLS ; col 1 -> 31 (B even), 31 -> the next row's 1 (B odd)
                bit  0, b
                jr   z, .s
                ld   e, DOOR_COLS
.s:             add  hl, de
                djnz .lp
                ret
                ASSERT (ROOM_MAP & $FF) == 0 && DOOR_COLS == 2

