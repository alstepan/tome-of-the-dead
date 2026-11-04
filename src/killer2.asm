;==============================================================================
; killer2.asm — ENDCARD-K (user playtest 2026-11-04: "i died but the game over
; screen did not show the ghost who killed me": a Mage's Spark reflected by a
; Ghost, RSP_X, killed him and ENDCARD-G1 counted it as his own bolt = YOU DIED).
; Bank 2, after kind_tab (main.asm); ENDCARD_RK builds only (defs.asm).
;==============================================================================
;------------------------------------------------------------------------------
; dh_killer — deal_hit .kill of the HERO (bank 3 paged): ST1_KILLER := $80 | the
; killer's kind. The attacker (ATK_PTR) unless it is a hero kind; then the body
; that reflected this cast (pf_rfl: its slot, 0 none; proj_prep zeroes it per cast,
; trap_hit's th_go too), e.g. a Spark off a Ghost, a Firebolt off the Death
; Knight, a Frost Shard off the Archmage; else unchanged (0 = YOU DIED: his own
; bolt off a wall, his own Firebolt burst, a trap). Only slot 0 is a hero, so a
; reflector's kind is never < K_WIZARD + 1.
; Clobbers: A, E, HL, IX.  ~0.1k T, once a game.
;------------------------------------------------------------------------------
dh_killer:      ld   hl, (ATK_PTR)
                ld   a, (hl)                   ; attacker kind (E_KIND = 0)
                cp   K_WIZARD + 1
                jr   nc, .k
                ld   a, (pf_rfl)
                or   a
                ret  z                         ; no reflector: his own blow
                call ent_ix                    ; (A, E)
                ld   a, (ix+E_KIND)
.k:             or   $80
                ld   (ST1_KILLER), a
                ret
                ASSERT E_KIND == 0 && K_KNIGHT < K_WIZARD + 1 && K_WIZARD < $80 && K_COUNT < $80
