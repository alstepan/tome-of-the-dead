#!/usr/bin/env python3
"""ROOM-MEM2 scripted playtest (user playtest 2026-11-14: "monsters still come back in different places").

Real do_exit on generated D1 / D2 levels (seed_fixed). For every room B with residents and every exit e
of B (side or vertical): wake B's monsters, let them chase the hero to the door (3 turns), leave through e
for real, note each body's cell (the parked slot), then come back for real:
  same-1   through the same door, at once
  same-3   through the same door after 3 more rooms (B evicted)
  other-2  through another door of B (via its room C), B left 2 rooms before
  other-3  through another door after 3+ rooms
(intermediate hops are far3 lp_transition stubs; the final entry is always a real walk / climb).
For every body not back on its cell (kind, x, y): the cause, from the Python model replay
(levelgen.lp_enter == the Z80, tests/lp.py A7): gap / box / footprint (ladder or shaft box) / pit /
occupied / flyer band / LP_POS not written / moved after entry (model placed it right, the slot moved
before the first frame) / other. Prints the restore rate and the cause counts.
Run: ZRCP_PORT=<port> python3 tests/roommem_play.py [--strict]   (--strict: exit 1 on a bug-class
cause: moved after entry / LP_POS not written / no entry)
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import room_model                                       # noqa: E402
from game_lib import Harness, S, EMU_ARGS               # noqa: E402
from lp import T, w16, parked_of, stand_y               # noqa: E402

EF_ACTIVE, EF_HOSTILE, EF_LEFT = 1, 4, S["EF_LEFT"]
GS_PLAYING = S["GS_PLAYING"]
PARK = S["LPK_PARK"]
HOLD = S["HOLD_ASLEEP"]


def run(p, seeds, depths):
    stats, causes, log = Counter(), Counter(), []
    for M in seeds:
        p.proto_start = 0
        p.load()
        p.wait_state(S["GS_SELECT"])
        p.wb("seed_fixed", 1)
        p.wmem(S["seed_value"], w16(M))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.hold("1")
        p.wait_state(GS_PLAYING)
        p.release()
        p.settle(3)
        for d in depths:
            if d > 1:
                pc0 = p.pc()
                p.code([0x3E, d - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
                p.z.cmd("set-register PC=%d" % pc0)
                p.release()
                p.settle(4)
            level(p, M, stats, causes, log)
    return stats, causes, log


def level(p, M, stats, causes, log):
    blk = p.block()
    d = p.rb("LVL_DEPTH")
    st, lair, sanct = (blk[S[k] - G.BASE] for k in ("LVL_START", "LVL_LAIR", "LVL_SANCTUM"))
    kw, kh = p.kb(S["K_KNIGHT"], "KT_BW"), p.kb(S["K_KNIGHT"], "KT_BH")
    pres = [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]]
    for r in range(6):                                  # every door open, no trickle
        p.wb(S["EDGE_TAB"] + r, p.rb(S["EDGE_TAB"] + r) | S["EG_OPEN"])
    p.wb("LP_RESPAWNS", S["RESPAWN_MAX"])

    def exits(r):
        ex = room_model.field(blk, r, "RD_EXITS")
        out = []
        if ex & S["RDX_L"]:
            out.append(("L", r - 1, 1 if ex & S["RDX_LS1"] else 0))
        if ex & S["RDX_R"]:
            out.append(("R", r + 1, 1 if ex & S["RDX_RS1"] else 0))
        if ex & S["RDX_U"]:
            out.append(("U", r - 3, 0))
        if ex & S["RDX_D"]:
            out.append(("D", r + 3, 1))
        return [e for e in out if e[1] in pres and e[1] != sanct]

    def ingame(code):
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        return ok

    def heal():
        p.set_ent(0, HP=250, MAXHP=250)

    def put_hero(r, x, s_, left):
        p.wb("CUR_ROOM", r)
        p.set_ent(0, ROOM=r, X=x, Y=stand_y(s_, kh), PX=x * 8, PY=stand_y(s_, kh) * 8,
                  FLAGS=EF_ACTIVE | 2 | (EF_LEFT if left else 0), MODE=0, DVIS=0)
        ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
               + [0xCD] + w16(S["present_full"]))
        p.settle(2)

    def xfer(dst):
        """stub hop (lp_transition as do_exit runs it), hero at x 1 storey 0."""
        src = p.rb("CUR_ROOM")
        p.set_ent(0, X=1, Y=stand_y(0, kh))
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        p.wb("FOLLOW_N", 0)
        p.wb("EXIT_DEST", dst)
        ingame([0x21] + w16(S["lp_transition"]) + [0xCD] + w16(S["far3"]))
        p.wb("TRK_PREV", src)
        p.wb("CUR_ROOM", dst)
        p.set_ent(0, ROOM=dst)

    def door_pos(r, side, s_):
        """(x, storey, key) of the hero about to leave r through `side`."""
        if side == "L":
            return 2, s_, "H"
        if side == "R":
            return 32 - 2 - kw, s_, "L"
        col = room_model.field(blk, r, "RD_UPCOL" if side == "U" else "RD_DNCOL")
        return col, (0 if side == "U" else 1), ("K" if side == "U" else "J")

    def walk(r, side, s_, dest, place=True):
        x, sh, key = door_pos(r, side, s_)
        if place:
            put_hero(r, x, sh, side == "L")
        heal()
        for _ in range(12):
            if p.rb("CUR_ROOM") == dest:
                break
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == dest

    def freeze_room():
        for s_ in range(1, 16):
            e = p.ent(s_)
            if e["FLAGS"] & EF_ACTIVE:
                p.wb(S["ST_FLAGS"] + s_, HOLD)
                p.wb(S["ST_T1"] + s_, 0x90)

    back = {"L": "R", "R": "L", "U": "D", "D": "U"}
    for B in pres:
        if B in (st, lair, sanct):
            continue
        exs = exits(B)
        for (side, A, s_) in exs:
            for case in ("same-1", "same-3", "other-2", "other-3"):
                others = [e for e in exs if e[0] != side]
                if case.startswith("other") and not others:
                    continue
                # setup: into B (stub), residents awake, the hero near the door for 3 turns
                if p.rb("CUR_ROOM") == B:
                    xfer(next(r for r in pres if r not in (B, sanct)))
                xfer(B)
                res = [s0 for s0 in range(1, 16) if p.ent(s0)["FLAGS"] & EF_ACTIVE and p.ent(s0)["ROOM"] == B]
                if not res:
                    break
                for s0 in res:
                    for a_ in ("ST_FLAGS", "ST_T1", "ST_T2"):
                        p.wb(S[a_] + s0, 0)
                x, sh, key = door_pos(B, side, s_)
                xin = x + (3 if side == "L" else -3 if side == "R" else 0)
                put_hero(B, xin, sh, side == "L")
                for _ in range(3):
                    heal()
                    p.turn("WAIT")
                    p.until(lambda: p.idle(), 300)
                if not walk(B, side, s_, A):
                    stats["setup fail"] += 1
                    continue
                saved = [(q[0], q[2], p.ent(q[4])["Y"], q[4]) for q in parked_of(p, B)]   # kind, x, y, slot
                freeze_room()
                # the way back
                if case == "same-1":
                    path, (ent_side, C, cs) = [], (back[side], A, s_)
                elif case == "same-3":
                    hops = [r for r in pres if r not in (A, B, sanct)][:2]
                    path, (ent_side, C, cs) = hops + [A], (back[side], A, s_)
                else:
                    o = others[0]
                    hops = [r for r in pres if r not in (A, B, o[1], sanct)][:2] if case == "other-3" else []
                    path, (ent_side, C, cs) = hops + [o[1]], (back[o[0]], o[1], o[2])
                for r in path:
                    xfer(r)
                    freeze_room()
                lp0, pk0 = p.lp(), parked_of(p, B)
                if not path:
                    # same-1: the hero stands on A's arrival box already
                    ok = walk(C, ent_side, cs, B, place=False)
                else:
                    ok = walk(C, ent_side, cs, B)
                if not ok:
                    stats["entry fail"] += 1
                    continue
                h = p.ent(0)
                hx, hs = h["X"], min(1, (h["Y"] + kh) // 9)
                got = [(e[1], e[3], e[4], e[0]) for e in p.slots() if e[2] == B]
                classify(p, blk, B, lp0, pk0, hs, hx, kw, saved, got, case, side, ent_side, d, M,
                         stats, causes, log)


def why(blk, r, s_, x, w, fly, hs, hx, hw, placed, gap):
    """lp_legal with the reason (levelgen.lp_legal's order)."""
    for ps, plo, phi in placed:
        if ps == s_ and plo <= x + w - 1 and x <= phi:
            return "occupied"
    ex = G._rd(blk, r, "RD_EXITS")
    if ex & G.D["RDX_L"] and bool(ex & G.D["RDX_LS1"]) == (s_ == 1) and x <= 4:
        return "box"
    if ex & G.D["RDX_R"] and bool(ex & G.D["RDX_RS1"]) == (s_ == 1) and x + w - 1 >= 27:
        return "box"
    if G.lp_hits(blk, r, s_, max(0, x - 1), x + w):
        return "footprint"
    pc = G._rd(blk, r, "RD_PITCOL")
    if s_ == 1 and pc and pc <= x + w and pc + (G._rb(blk, r, G.L2_PITW) or 3) - 1 >= x - 1:
        return "pit"
    if s_ == hs and not (x >= hx + hw + gap or x + w + gap <= hx):
        return "gap"
    return "ok"


def classify(p, blk, B, lp0, pk0, hs, hx, hw, saved, got, case, side, ent_side, d, M, stats, causes, log):
    wl, out = G.lp_enter(blk, lp0, B, hs, hx, hw, f3=True, parked=pk0)
    ro = G.lp_off("LP_REC") + B * G.D["LR_STRIDE"]
    po = G.lp_off("LP_POS") + B * G.D["LR_MAX"]
    ents = [(lp0[ro + 1 + 2 * i], lp0[po + i]) for i in range(lp0[ro] & 7)]
    left = list(got)
    placed = []
    for (k, x, y, slot) in saved:
        stats["bodies"] += 1
        stats[case] += 1
        hit = next((g for g in left if g[0] == k and g[1] == x and g[2] == y), None)
        if hit:
            left.remove(hit)
            stats["exact"] += 1
            stats[case + " exact"] += 1
            if hit[3] != slot:
                causes["(swapped slot, cell right)"] += 1
            continue
        fly = p.kb(k, "KT_FLAGS") & S["KF_FLYER"]
        w = p.kb(k, "KT_BW")
        s_ = min(1, (y + p.kb(k, "KT_BH")) // 9)
        if any(g[0] == k and min(1, (g[2] + p.kb(k, "KT_BH")) // 9) == s_ and abs(g[1] - x) <= 8 for g in left):
            stats["near"] += 1                          # same storey, <= 8 cols away (the slide)
        ent = next((e for e in ents if e[0] & 31 == k and e[1] and e[1] & 31 == x
                    and (e[1] >> 5) & 1 == s_), None)
        mo = next((o for o in out if o[0] & 31 == k and o[3] == x and o[2] == s_), None)
        if ent is None:
            c = "LP_POS not written" if any(e[0] & 31 == k and not e[1] for e in ents) else "other (no entry)"
        elif mo is not None:
            gy = next((g for g in left if g[0] == k and g[1] == x), None)
            c = "flyer band" if fly and gy else "moved after entry"
        else:
            # the bodies placed before this unit (its own slid body is the same-kind out entry nearest its cell)
            mine = [i for i, o in enumerate(out) if o[0] & 31 == k]
            me = min(mine, key=lambda i: (out[i][2] != s_, abs(out[i][3] - x))) if mine else len(out)
            pl = [(o[2], o[3], o[3] + (p.kb(o[0] & 31, "KT_BW")) - 1) for o in out[:me]]
            c = why(blk, B, s_, x, w, fly, hs, hx, hw, pl, G.D["LP_GAP2"])
            if c == "ok":
                c = "other (legal, not placed)"
            elif c == "occupied":
                c = "occupied"
        causes[c] += 1
        stats[case + " " + c] += 1
        log.append(f"seed {M:#06x} d{d} room {B} out {side} in {ent_side} {case}: kind {k} "
                   f"saved ({x},{y}) -> {[g for g in got if g[0] == k]}: {c} (hero box x{hx} s{hs})")


def main():
    strict = "--strict" in sys.argv
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        stats, causes, log = run(p, (0x2468, 0x1357, 0x0BAD), (1, 2))
    for line in log[:40]:
        print("[miss]", line)
    n, ex = stats["bodies"], stats["exact"]
    print(f"[roommem_play] bodies {n}, exact {ex} ({100 * ex / max(n, 1):.1f} %), else same storey <= 8 cols "
          f"{stats['near']}; setup/entry fails {stats['setup fail']}/{stats['entry fail']}")
    for c in ("same-1", "same-3", "other-2", "other-3"):
        print(f"[roommem_play]   {c}: {stats[c + ' exact']}/{stats[c]}")
    print("[roommem_play] causes:", dict(causes))
    if strict:                                          # no bug-class cause (entry move, LP_POS missing)
        return 1 if causes["moved after entry"] or causes["LP_POS not written"] or causes["other (no entry)"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
