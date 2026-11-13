;==============================================================================
; instr_ovl.asm — the boot overlay (INSTR-BUILD; ITEM-INFO 2026-11-12 dropped the
; HOW TO PLAY pages, docs/design/item_info.md §5): the frame_tab -> FRT step, the
; loading picture + "PRESS ANY KEY", then the D0 tutorial set-up. A boot-only
; OVERLAY (main.asm "OVERLAYS"): assembled at INSTR_ORG (GEN_SCRATCH, bank 5),
; ZX0-packed into the bank-4 BOOT4 tape block (BOOT4_ORG..), run once by
; boot6_wait -> ovl_run BEFORE the boot pool (gen_idles pools over bank 4: the
; streams are dead after this). 0 resident bytes.
;
; Flow: in_ft, then the picture waits (GS_ANYKEY) for a key, counted only after
; every key was released once (the ENTER of LOAD "" may still be down); no
; timeout; Kempston is not read (input_tick: GAME_STATE != GS_PLAYING); a Sinclair
; FIRE is a key. The key is swallowed by the menu (menu_run primes its edge
; detector from the matrix). The title tune plays on throughout. Then in_tut
; (TUT0-T1): the D0 blob into bank 4 + the low-RAM stubs + the es_go patch.
; bank 3 is never paged (its pblit SMC must stay as loaded until panel_init,
; game.py #50). ovl_run gives the caller's bank back afterwards.
; Clobbers: all but IX, IY.
;==============================================================================
instr_main:
                call in_flow                   ; frame_tab, then the picture's key wait
                ; fall through: TUT0-T1 the D0 set-up

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
                ld   a, GS_ANYKEY
                ld   (GAME_STATE), a
                ld   hl, in_press              ; ROM font on the picture's blank row 22
                ld   bc, IN_PRESS_ROW << 8 | IN_PRESS_COL
                call print_str
                call in_rel                    ; all released once
                ; fall through: then any key (swallowed by the menu)
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
; Clobbers: A, BC, DE, HL.
; ~16k T (dzx0 of 576 B + ~76 T x 16 B/row; boot only)
;------------------------------------------------------------------------------
in_ft:          ld   a, BANK_INSTR
                call page_bank
                ld   hl, INSTR_FT_ZX0
                ld   de, FRT
                call dzx0_standard
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
                ret
                ASSERT FID_COUNT >= 1 && FID_COUNT <= 255

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

in_press:       DB   "PRESS ANY KEY", 0
IN_PRESS_ROW    EQU 22                         ; blank in the loading art (attrs 7)
IN_PRESS_COL    EQU (32 - 13) / 2
