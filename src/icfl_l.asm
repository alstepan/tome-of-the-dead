; ic_fl - ICON-FLASH (user 2026-11-18): the new ability icon flashes (hardware FLASH, attr bit 7, 0 CPU while it runs)
; for ICON_FLASH_FR frames after a book LEARNED it (ic_learn arms ICON_FL / ICON_FLT). Called first thing in
; icon_poll (every panel_step: a non-input tick, never in a modal), HL = PANEL_DIRTY and BC kept, A / DE clobbered.
; Idle (ICON_FL = 0) 33 T. Active: while SYS_FRAMES - ICON_FLT < ICON_FLASH_FR the 6 attr cells (rows 18-19, cols
; ICON_FL..+2) get bit 7 set; a redraw of the slot (item_icons / sel_paint) drops it, so the first cell is tested and
; the cells re-ORed + pmark_rect'ed (R4 ic_mark; present copies them to screen 2) only when it is missing. While PD_ICONS is
; pending nothing is touched (the slot may not be drawn yet). Once elapsed (or on a stale wrap) bit 7 is cleared
; on the cells and ICON_FL = 0. level_reset zeroes ICON_FL (panel_init redraws every icon cell; no cell keeps a
; stale FLASH); the poll never runs on the death / win / pause / bag screens, which repaint the cells.
; Clobbers: A, DE (HL, BC kept).   ~1.5k T on a (re)apply, ~0.4k T otherwise while active
ic_fl:          ld   a, (ICON_FL)
                or   a
                ret  z
                bit  PD_ICONS_BIT, (hl)
                ret  nz                        ; the icons redraw first
                push hl
                push bc
                add  a, ICON_ROW * ROOM_COLS & $FF ; = the first cell's low byte (col <= 30: no carry into the row)
                ld   e, a
                ld   hl, (SYS_FRAMES)
                ld   bc, (ICON_FLT)
                or   a
                sbc  hl, bc                    ; elapsed frames
                ld   bc, -ICON_FLASH_FR
                add  hl, bc                    ; CF = elapsed >= ICON_FLASH_FR (also a stale 16-bit wrap)
                ld   bc, $80 << 8 | $FF        ; B = OR, C = AND: FLASH on (LD keeps CF)
                jr   nc, .go
                ld   bc, $007F                 ; FLASH off, and stop for good
                xor  a
                ld   (ICON_FL), a
.go:            ld   h, (SCREEN_ATTR + ICON_ROW * ROOM_COLS) >> 8
                ld   l, e
                ld   a, (hl)
                and  c
                or   b
                cp   (hl)
                jr   z, .x                     ; the first cell is already as wanted
                push hl
                ld   d, 2
.r:             push hl
                ld   e, 3
.c:             ld   a, (hl)
                and  c
                or   b
                ld   (hl), a
                inc  l
                dec  e
                jr   nz, .c
                pop  hl
                ld   a, l
                add  a, ROOM_COLS
                ld   l, a                      ; the next attr row (rows 18 / 19 share the page)
                dec  d
                jr   nz, .r
                pop  hl
                jp   ic_mark                   ; (R4 sv_r4.asm: pmark_rect the 3 x 2 cells, then pop bc / hl / ret: -9 B here)
.x:             pop  bc
                pop  hl
                ret
                ASSERT (ICON_ROW * ROOM_COLS & $FF) + ROOM_COLS * 2 <= 256 && ((SCREEN_ATTR + ICON_ROW * ROOM_COLS) >> 8) == ((SCREEN_ATTR + (ICON_ROW + 1) * ROOM_COLS + ICON_SLOTS * ICON_W) >> 8)
