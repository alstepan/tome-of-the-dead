;==============================================================================
; frt2.asm — MEM-FT bank-2 FRT helpers (NEW-MON3 T1: in the kind_tab ALIGN pad, before
; kind_tab, so the T1 free bytes gather at the image tail; was after kind_tab). Were low RAM (bank 5:
; sel_frt_copy, frt_ptr, frt_ptr_cur) and gfx.asm (ft_ptr); moved so the low-RAM
; cold block keeps room for the FRT_MAX descriptor reserve (main.asm fit).
; Bank 2 is always mapped at $8000, so every caller (low RAM gen_frame, bank 1
; menu, boot) reaches them with any $C000 bank; uncontended, so a bit faster.
;==============================================================================

;------------------------------------------------------------------------------
; ft_ptr — HL = frame_tab + A*FT_STRIDE (MEM-FT: the fid's FRT row tail).
; gen_frame only (cold).  Clobbers: A, HL (keeps DE, BC).   77 T incl. ret
;------------------------------------------------------------------------------
ft_ptr:
                FT_HL_A 0
                ret

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
