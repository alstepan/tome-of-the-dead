;==============================================================================
; abil_ammo7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): the
; dagger throw and the bow shot (game.md §6.3). T0: refusing stub, T1
; implements them.
;==============================================================================

;------------------------------------------------------------------------------
; abil_ammo — intent7 ic_disp (ABF_AMMO; ic_daggers / ic_bow checked the
; counters), IX = hero, B = ABL_DAGGER / ABL_BOW, ABIL_DESC loaded (abil_load).
; Out: L = 1 turn used / 0 refused (no turn).
; T0 stub: L = 0.  Clobbers: L
;------------------------------------------------------------------------------
abil_ammo:
                ld   l, 0
                ret

;------------------------------------------------------------------------------
; ammo_fire — the dagger / arrow release (act_fire, fire tick): proj_fire via
; far3 + the drop rule (game.md §6.3). In: IX = hero, B = ABL_DAGGER / ABL_BOW.
; Out: L = 1 fired.  T1 stub (T6 implements): L = 1.  Clobbers: L
;------------------------------------------------------------------------------
ammo_fire:
                ld   l, 1
                ret
