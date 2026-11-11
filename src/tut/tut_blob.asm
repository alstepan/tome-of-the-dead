;==============================================================================
; tut_blob.asm — TUT0: the D0 tutorial BLOB (docs/design/tut0_split.md; spec
; docs/design/tutorial_d0.md). Assembled at BLOB_ORG in bank 4 (BANK_BLOB,
; main.asm "TUT0 BLOB"), shipped ZX0-packed as the last stream of the bank-0
; text tape block, unpacked in place by the INSTR overlay's common exit (once
; per power-on). Lives until the D1+ pool overwrites it.
;
; Rules (tut0_split.md "Contracts shared by all tasks"): entered only via the
; low-RAM stubs (tut_stub.asm: farb with C = BANK_BLOB); calls bank 3 / 1 / 6
; / 7 via far3 / far1 / far6 / far7 and every resident routine that pages
; $C000 via farb with C = BANK_BLOB; never pages $C000 itself. SMC on the
; three operands only: es_go / pl_et (bank 2) and pi_ic (bank 7) (conventions.md "TUT0 boot stubs").
;
; T6: blob_choice = the choice screen + the D0 start (tut_start.asm); T7:
; blob_turn = the turn engine (tut_turn.asm) on the beat table (tut_beats.asm).
;==============================================================================
blob_base:
                jp   blob_choice               ; +0 (BLOB_CHOICE)
                jp   blob_turn                 ; +3 (BLOB_TURN)
                jp   blob_icon                 ; +6 (BLOB_ICON, TUT0-R2: the icon tour)
                ASSERT blob_base == BLOB_ORG && blob_choice != blob_turn && BLOB_ICON == blob_base + 6

                INCLUDE "tut/tut_start.asm"    ; T6: blob_choice (choice screen), tut_d0 (the D0 start)

                INCLUDE "tut/tut_turn.asm"     ; T7: blob_turn (the turn engine, the hold, mercy, reset)
                INCLUDE "tut/tut_beats.asm"    ; T8 (+ T7 amendments): the beat table

;------------------------------------------------------------------------------
; data (generated): text (tools/tutpack.py), the D0 level block + spots + mentor
; ids (tools/tut0_level.py), the 3/4 mentor art (tools/mentor_convert.py --variant 34)
;------------------------------------------------------------------------------
                INCLUDE "tut/tut_text.asm"     ; TUT0-F2: from -i$OUT/build (tools/build.sh), the
                INCLUDE "tut/tut0_level.asm"   ; build's own copy (src/tut/ has no such files)
                INCLUDE "../assets/gfx/mentor/aldous34.asm"
