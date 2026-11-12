;==============================================================================
; instr_ovl.asm — INSTR-BUILD: the boot's key waits + the two-page HOW TO PLAY
; screen (game.md §3.2.1 option A flow: once per power-on, before the first
; menu; pages / wording / render spec: docs/design/instructions_screen.md /
; .txt). A boot-only OVERLAY (main.asm "OVERLAYS"): assembled at INSTR_ORG
; (GEN_SCRATCH, bank 5), ZX0-packed into the bank-4 BOOT4 tape block
; (BOOT4_ORG..; C+TUT0 merge, was bank 0 POOL_START), run once by
; boot6_wait -> ovl_run BEFORE the boot pool (gen_idles pools over bank 4:
; the streams are dead after this). 0 resident bytes.
;
; Flow: the loading picture + "PRESS ANY KEY" (GS_ANYKEY, was boot6_wait),
; then page 1 (GS_HELP1), page 2 TREASURES (GS_HELP3; GS_HELP2 unused), then
; back to boot (menu).
; A key counts only after every key was released once (the ENTER of LOAD ""
; or the previous page's key may still be down). BREAK (CAPS + SPACE, seen at
; any frame while a page's key is held) on page 1 skips page 2;
; on page 2 it is any key. No timeout;
; Kempston is not read (input_tick: GAME_STATE != GS_PLAYING); a Sinclair
; FIRE is a key. Page 2's key is swallowed by the menu (menu_run primes its
; edge detector from the matrix). The title tune plays on throughout.
;
; Page images (tools/instr_pack.py -> build/text/instr_p<n>.inc, format there)
; are unpacked to INSTR_DATA (after this code, same window): p1 straight after
; the frame_tab stream INSTR_FT_ZX0 (= BOOT4_ORG, bank 4, in_ft: RECLAIM-D), p2 straight
; after it (dzx0 leaves HL past the stream).
; TUT0-T1: the common exit (also after a BREAK skip) is in_tut: the D0 blob into
; bank 4 + the low-RAM stubs + the es_go patch.
; Drawing pages: bank 4 (BOOT4, the unpack source), bank 1 (copy_virt: the vdata bar icons and
; the key label, GEN_SRC staging), bank 6 (R6 ic_scr: the 16x16 item icons);
; bank 3 is never paged (its pblit SMC must stay as loaded until panel_init,
; game.py #50). ovl_run gives the caller's bank back afterwards.
; Clobbers: all but IX, IY.
; Cost per page: clear ~0.14M T, text ~24 rows x (~0.15k + 42 x ~0.46k) ~0.47M T,
; icons ~3k T each, unpack ~40k T: ~0.7M T (measured 10 frames) unseen (attrs 0 until the
; last pass), then the attrs (~16k T) reveal it at once.
;==============================================================================
instr_main:
                call in_flow                   ; the key waits + pages (every exit: BREAK too)
                ; fall through: TUT0-T1 the common exit

;------------------------------------------------------------------------------
; in_tut — TUT0-T1 (docs/design/tut0_split.md "Verdicts" F4): before gen_idles
; overwrites bank 4. (1) The blob stream (the LAST stream of the bank-4 BOOT4 tape
; block + a DW length trailer; the block's end = tape_tab's TT_BOOT4_REC address +
; length, so no byte here depends on a packed size) is ZX0-unpacked straight to
; BLOB_ORG (C+TUT0 merge: same bank, the block ends <= BLOB_ORG, ASSERTed, so no
; overlap and no bounce copy). (2) The stubs (in_stub, a copy of tut_stub.asm DISP'd
; at check_paging) go over check_paging (tape path only, dead now). (3) es_go :=
; ts_choice (enter_select offers the tutorial). The raw blob's tail (BLOB_ORG +
; BLOB_LEN .. $FFFF) is zeroed: bank 4 there == the .sna's on a tape boot too.
; Clobbers: A, BC, DE, HL (ovl_run gives the caller's bank back).
; Cost: dzx0 (~LDIR rate + Elias bits per raw byte) + 21 T per tail byte + ~1k T;
; boot only. ~7.7 KB blob ~0.2M T (estimate).
;------------------------------------------------------------------------------
in_tut:         ld   a, BANK_BLOB              ; = BANK_BOOT4 (main.asm ASSERT)
                call page_bank
                ld   hl, (tape_tab + TT_BOOT4_REC * TT_STRIDE + 1)
                ld   de, (tape_tab + TT_BOOT4_REC * TT_STRIDE + 3)
                add  hl, de                    ; HL = the block's end (CF = 0: <= $FFFF)
                dec  hl
                ld   b, (hl)
                dec  hl
                ld   c, (hl)                   ; BC = packed length; HL = the trailer
                sbc  hl, bc                    ; HL = blob_zx0
                ld   de, BLOB_ORG
                call dzx0_standard             ; forward, the stream below BLOB_ORG
                ld   h, d                      ; DE = BLOB_ORG + BLOB_LEN: zero the raw blob's
                ld   l, e                      ; tail to $FFFF, so bank 4 == the .sna's
                ld   (hl), 0                   ; (raw blob + zeros) for the pool checks
                inc  de
                ld   bc, BLOB_TAIL - 1
                ldir
                ld   hl, in_stub
                ld   de, check_paging
                ld   bc, TUT_STUB_LEN
                ldir
                ld   hl, ts_choice
                ld   (es_go + 1), hl           ; SMC target (main.asm enter_select)
                ret
BLOB_TAIL       EQU $10000 - BLOB_ORG - BLOB_LEN  ; the zeroed tail (ASSERTed >= 8)
                ASSERT BLOB_TAIL >= 8
in_stub:                                       ; = tut_stub.asm as assembled at check_paging (main.asm)
                DUP  TUT_STUB_LEN, tsi
                DB   {b ovl_raw_stub + tsi}
                EDUP

in_flow:
                call in_ft                     ; RECLAIM-D: frame_tab -> FRT first
                push hl                        ; HL = the page-1 stream
                ld   a, GS_ANYKEY
                ld   (GAME_STATE), a
                ld   hl, in_press              ; ROM font on the picture's blank row 22
                ld   bc, IN_PRESS_ROW << 8 | IN_PRESS_COL
                call print_str
                call in_rel                    ; all released once
                call in_key                    ; then any key
                pop  hl
                ld   a, GS_HELP1
                call in_page                   ; HL = the page-2 stream
                push hl
                call in_wait
                pop  hl                        ; (flags kept)
                ret  nc                        ; BREAK: straight to the menu
                ld   a, GS_HELP3               ; TUT0-T2: page 2 = TREASURES (GS_HELP2 unused)
                call in_page
                ; keys are all up (page 1 ended on the release): any key (BREAK
                ; counts as one here); the last key is swallowed by the menu
                ; fall through
in_key:         call in_down                   ; wait for any key down
                jr   z, in_key
                ret
in_rel:         call in_down                   ; wait until no key is down
                jr   nz, in_rel
                ret

;------------------------------------------------------------------------------
; in_ft — RECLAIM-D (was boot6.asm boot6_ft, MEM-FT): the static frame_tab into
; the FRT rows. ftz_zx0 (bank 4, the fixed BOOT4_ORG, boot only: was the last
; 132 B of the bank-2 image) holds the entries contiguous (FT_LEN B/fid);
; unpacked to FRT first, then spread from the LAST fid down to row tail FRT +
; fid*16 + FT_IN_ROW, each row's variants := FRT_NONE. Top-down is overlap-safe:
; the source of fid f (4f..4f+3) never lies above its row (16f..16f+15), and
; every lower fid's source lies below row f. Result == the build's FRT image
; (data.asm, the .sna's bytes) for fids < FID_COUNT; rows above stay untouched.
; Runs first in the overlay: before the first gen_frame (boot: gen_idles, after
; boot6_wait); nothing between boot6_tiles and here reads frame_tab.
; Out: HL = past the stream (= the page-1 stream).  Clobbers: A, BC, DE, HL.
; ~16k T (dzx0 of 576 B + ~76 T x 16 B/row; boot only)
;------------------------------------------------------------------------------
in_ft:          ld   a, BANK_INSTR
                call page_bank
                ld   hl, INSTR_FT_ZX0
                ld   de, FRT
                call dzx0_standard             ; HL = past the stream
                push hl
                ld   hl, FRT + FID_COUNT * FT_LEN - 1
                ld   de, FRT + FID_COUNT * FRT_STRIDE - 1
                ld   a, FID_COUNT
.r:             ld   bc, FT_LEN
                lddr                           ; the entry -> the row tail
                ex   de, hl                    ; HL = row byte FT_IN_ROW - 1
                ld   b, FT_IN_ROW
.n:             ld   (hl), FRT_NONE
                dec  hl
                djnz .n
                ex   de, hl                    ; DE = the row below's last byte
                dec  a
                jr   nz, .r
                pop  hl
                ret
                ASSERT FID_COUNT >= 1 && FID_COUNT <= 255

;------------------------------------------------------------------------------
; in_wait — a page's key wait: every key released once, then any key, held until
; all are released again; BREAK (CAPS + SPACE) seen at any frame while it is
; held. Out: NC = BREAK was seen, C = not.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
in_wait:        call in_rel
                call in_key
                ld   c, 1                      ; bit 0 = 0 once BREAK was seen
.hold:          ld   a, (KBD_MATRIX + KBROW_CAPSV)
                ld   hl, KBD_MATRIX + KBROW_SPACE
                or   (hl)                      ; bit 0 = 0 iff CAPS and SPACE
                and  c
                push af
                call in_down                   ; next frame; Z = all released
                pop  bc                        ; B = the BREAK bit so far (flags kept)
                ld   c, b
                jr   nz, .hold
                rr   c
                ret

;------------------------------------------------------------------------------
; in_down — one menu frame (frame sync, the select_tick probe, input_tick, the
; seed mixing), then Z = no key down in KBD_MATRIX (bits 5-7 = EAR, ignored).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
in_down:        call menu_frame
                ld   hl, KBD_MATRIX            ; AND the 8 rows (a down key = a low bit)
                ld   b, KBD_MATRIX_LEN
                ld   a, $FF
.l:             and  (hl)
                inc  l
                djnz .l
                or   $E0
                inc  a                         ; Z = all ones = nothing down
                ret
                ASSERT (KBD_MATRIX >> 8) == ((KBD_MATRIX + KBD_MATRIX_LEN - 1) >> 8)

;------------------------------------------------------------------------------
; in_page — A = GAME_STATE for the page, HL = its ZX0 stream (bank 4 BOOT4): unpack
; the page image to INSTR_DATA, clear the screen (attrs 0: nothing visible),
; print the 24 text rows (FONT6, print6 from x = 0 through the TX_DEC row
; buffer), draw the icon records, then write the attrs (the reveal).
; Out: HL = past the stream.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
in_page:        ld   (GAME_STATE), a
                push hl
                ld   a, BANK_INSTR
                call page_bank
                pop  hl
                ld   de, INSTR_DATA
                call dzx0_standard             ; HL = past the stream
                push hl
                xor  a
                out  (PORT_BORDER), a          ; border black (the spec; BASIC set it already)
                call clear_screen              ; bitmap 0, attrs 0
                ld   hl, INSTR_DATA
                ld   b, 0                      ; char row
.row:           ld   de, TX_DEC                ; decode the row: spaces expanded
.ch:            ld   a, (hl)
                inc  hl
                cp   ' '
                jr   nc, .lit
                or   a
                jr   z, .eol
                ld   c, a                      ; 1..31 spaces
                ld   a, ' '
.sp:            ld   (de), a
                inc  de
                dec  c
                jr   nz, .sp
                jr   .ch
.lit:           ld   (de), a
                inc  de
                jr   .ch
.eol:           ld   (de), a                   ; the row's 0
                push hl
                push bc
                ld   hl, TX_DEC
                ld   e, 0                      ; x = 0 (char k at 6k px)
                call print6                    ; B = row
                pop  bc
                pop  hl
                inc  b
                ld   a, b
                cp   IN_ROWS
                jr   nz, .row
                ; icon records: kind, row, col, DW arg (0 = end)
.ic:            ld   a, (hl)
                or   a
                jr   z, .att
                inc  hl
                push hl
                ld   a, BANK_R6                ; ic_scr (the others page nothing / their own)
                call page_bank
                pop  hl
                dec  hl
                ld   a, (hl)                   ; kind again
                inc  hl
                ld   b, (hl)                   ; row
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                   ; DE = arg
                inc  hl
                push hl                        ; [next record]
                ex   de, hl                    ; HL = arg
                cp   IK_BAR
                jr   z, .bar
                cp   IK_GLY
                jr   z, .gly
                call in_cell                   ; DE = bitmap line 0 of (B, C)
                cp   IK_I16
                jr   z, .i16
                add  hl, hl                    ; IK_TILE: HL = id -> TILE_GLYPHS + 8 id
                add  hl, hl
                add  hl, hl
                ld   bc, TILE_GLYPHS
                add  hl, bc
                ld   b, 8
.tl:            ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .tl
                jr   .nx
.i16:           ld   a, l                      ; logical icons16 index (attrs: below)
                call ic_scr                    ; R6, bank 6 paged
                jr   .nx
.bar:           ld   de, (2 << 8) | 3          ; 2 char rows x 3 cells
                jr   .blk
.gly:           ld   de, (1 << 8) | 1          ; 1 cell
.blk:           call in_vblk
.nx:            pop  hl
                jr   .ic
                ; attrs: (count, attr) runs over the 768 cells, 0 = end
.att:           inc  hl
                ld   de, SCREEN_ATTR
.ar:            ld   a, (hl)
                or   a
                jr   z, .done
                ld   b, a
                inc  hl
                ld   a, (hl)
                inc  hl
.af:            ld   (de), a
                inc  de
                djnz .af
                jr   .ar
.done:          pop  hl
                ret

;------------------------------------------------------------------------------
; in_vblk — a vdata cell block (bank 1, VIRTUAL address HL: D * 8 lines x E bytes,
; row-major; its attrs are not read: the page's attr runs carry them) at cell
; (B, C), copied through GEN_SRC (copy_virt pages bank 1). Not pblit / glyph8:
; their SMC would leave bank 3 != the .sna before the first panel_init (game.py #50).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
in_vblk:        ld   a, e
                ld   (in_w), a
                ld   a, d
                add  a, a
                add  a, a
                add  a, a
                ld   (in_nl), a                ; pixel lines
                push bc
                ld   bc, IN_VBLK_MAX
                ld   de, GEN_SRC
                call copy_virt
                pop  bc
                call in_cell                   ; DE = line 0 of (B, C)
                ld   hl, GEN_SRC
.ln:            push de
                ld   a, (in_w)
                ld   c, a
                ld   b, 0
                ldir
                pop  de
                inc  d                         ; next pixel line
                ld   a, d
                and  7
                jr   nz, .n8
                ld   a, e                      ; crossed into the next char row
                add  a, 32
                ld   e, a
                jr   c, .n8                    ; (next third: D already right)
                ld   a, d
                sub  8
                ld   d, a
.n8:            ld   a, (in_nl)
                dec  a
                ld   (in_nl), a
                jr   nz, .ln
                ret
in_w:           DB   0                         ; overlay RAM (GEN_SCRATCH): width in bytes
in_nl:          DB   0                         ; lines left
IN_VBLK_MAX     EQU 2 * 8 * 3                  ; the largest block (a 24x16 bar icon)
                ASSERT IN_VBLK_MAX <= 512                      ; GEN_SRC is 512 B

; in_cell — DE = bank-5 bitmap line 0 of cell (row B, col C).  Clobbers: F (A kept)
in_cell:        push af
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   d, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   e, a
                pop  af
                ret

in_press:       DB   "PRESS ANY KEY", 0
IN_PRESS_ROW    EQU 22                         ; blank in the loading art (attrs 7)
IN_PRESS_COL    EQU (32 - 13) / 2
IN_ROWS         EQU 24
