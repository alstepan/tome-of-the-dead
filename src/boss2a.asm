;==============================================================================
; boss2a.asm — 3F-T8 bank-2 helpers (were BEFORE kind_tab in its ALIGN pad;
; AMMO-COUNT moved them after kind_tab: panel_more's +17 B overflowed the 6-B
; pad and shifted kind_tab a page). The rest: boss2.asm.
;==============================================================================

;------------------------------------------------------------------------------
; og_adv — IX = the Ogre: its SLAM counter one turn on (3 -> 1, 0 -> 1, 1 -> 2,
; 2 stays). og_put: A = the new counter. Both end NC (or).  Keeps DE, HL.
; Clobbers: A, C.   ~90 T
;------------------------------------------------------------------------------
og_adv:
                ld   a, (ix+E_RCD)
                and  RCD_MASK
                cp   OG_SLAM
                jr   nz, .n
                xor  a                         ; the turn after a SLAM counts 1
.n:             cp   OG_READY
                jr   z, og_put
                inc  a
og_put:         ld   c, a
                ld   a, (ix+E_RCD)
                and  ~RCD_MASK & $FF
                or   c
                ld   (ix+E_RCD), a
                ret

;------------------------------------------------------------------------------
; GOLDEN GLOW (game.md §8.6, 3F TICK-BUDGET PLAN): a golden body's attr cycles
; GLOW_TAB by GLOW_CNT (2 ticks a step, period 8); GLOW_CNT counts the ticks
; that may draw a panel item (main.asm .panel: never a turn's input tick, a
; TP_FIRE tick or a tick before COMBAT_NOT_BEFORE), so a step is never decided
; on a heavy tick (the render of the NEXT tick shows it). The hit flash and the
; status tints override it (render .fl / st_tint).
; glow_kat — render .kat for a golden body: A = the glow attr, back to .tsh.
;------------------------------------------------------------------------------
glow_kat:
                ld   a, (GLOW_CNT)
                rrca
                and  3
                add  a, glow_tab & $FF
                ld   e, a
                ld   d, glow_tab >> 8          ; (DE free in render .kat)
                ld   a, (de)
                jp   render.tsh
                ; glow_tab (4 B): BOSS-RANGED moved it before kind_tab's ALIGN pad (main.asm)

