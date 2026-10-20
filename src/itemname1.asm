;==============================================================================
; itemname1.asm — 3E-T10 item_name, bank 1 (INCLUDEd by main.asm inside the
; it_words DISP block, after items_tab.asm). Reached by far1 from bank 7 /
; called directly by bank-1 / bank-5 overlay code with bank 1 paged. Never
; pages $C000 itself. Nothing calls it before 3E-T11.
;==============================================================================

;------------------------------------------------------------------------------
; item_name — compose a type's display name ("HEAL POTION", "WAR TOME") as raw
; ASCII words joined by single spaces. NO terminator, no article / BUC prefix.
; In : A = item type (< IT_COUNT; 0 words -> empty), DE = destination (outside
;      $C000: MSG_BUF / page scratch), H = max chars (0..32), C = mode (bit 0
;      reserved, always 0 now: ignored).
; Out: DE = past the last char written, CF = 1 iff the name was cut at H chars
;      (a cut after a space leaves that space written).
; Clobbers: A, BC, HL, F.  Keeps DE-advance only; IX, IY untouched. No exx.
; Cost: ~0.8k T per word + 16 T per char (<= 6k T: 3 words, <= 18 chars).
; B counts room+1 so one `dec b` is the room test (Z = full). The word table
; is raw ASCII with bit 7 on the last char: `or a` latches that bit in S before
; `res 7` (flags survive res / ld (de),a / inc de), `jp p` loops.
; The book's first word id ITN_HERO ($FF) is the class word: W_WAR + HERO_KIND
; (K_KNIGHT 0 -> WAR, K_WIZARD 1 -> SPELL; asserted).
;------------------------------------------------------------------------------
item_name:
                inc  h
                ld   b, h                      ; B = room + 1
                ld   l, a
                add  a, a
                add  a, l                      ; 3 * type (< 132, no carry)
                ld   l, a
                ld   h, 0
                push de
                ld   de, it_name
                add  hl, de
                pop  de                        ; HL = this type's 3 word ids
                ld   c, 3                      ; words left (3 = first word)
.word:          ld   a, (hl)
                inc  hl
                or   a
                ret  z                         ; no more words (CF = 0)
                push hl                        ; row pointer
                cp   ITN_HERO
                jr   nz, .id
                ld   a, (HERO_KIND)            ; 0 / 1
                inc  a                         ; W_WAR / W_SPELL (the dec below -> idx)
.id:            dec  a                         ; idx = id - 1 (0..ITW_COUNT-1)
                push bc
                push af                        ; idx
                rrca
                rrca
                and  $3E                       ; 2 * (idx >> 3): it_wcx DW offset
                ld   l, a
                ld   h, 0
                ld   bc, it_wcx
                add  hl, bc
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                ld   hl, it_words
                add  hl, bc                    ; the 8-word group start
                pop  af
                and  7                         ; words to skip inside the group
                jr   z, .cp
                ld   c, a
.sk:            ld   a, (hl)
                inc  hl
                rla                            ; bit 7 (last char) -> CF
                jr   nc, .sk
                dec  c
                jr   nz, .sk
.cp:            pop  bc                        ; B = room + 1, C = words left
                ld   a, c
                cp   3
                jr   z, .ch                    ; no space before the first word
                dec  b
                jr   z, .cut
                ld   a, ' '
                ld   (de), a
                inc  de
.ch:            dec  b
                jr   z, .cut
                ld   a, (hl)
                inc  hl
                or   a                         ; S = last char of the word
                res  7, a
                ld   (de), a
                inc  de
                jp   p, .ch
                pop  hl
                dec  c
                jr   nz, .word
                ret                            ; CF = 0 (the `or a` above)
.cut:           pop  hl
                scf
                ret
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1 && W_WAR == 1 && W_SPELL == 2
                ASSERT ITN_HERO == $FF
item_name_end:
ITEM_NAME_LEN   EQU item_name_end - item_name
