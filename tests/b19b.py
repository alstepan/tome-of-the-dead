#!/usr/bin/env python3
"""B19b: arrival + follower PENDING on overlapping boxes, CROSS-kind (b19c
covers the same-kind follower pair). Room B holds a resident (kind Y) at the
hero's arrival box -> arrival_conflicts makes it PENDING in place; a follower
(kind X != Y) is placed PENDING on the entry box x = 1 (place_follower). They
overlap. The hero walks in, turns and kills both at the door (daggers).
Per tick (b19c.Watch plus a kind-agnostic check): a body leaving PENDING over
a corpse still DYING = bad; a live body under a fresh corpse = bad; no two live
walkers overlap. Also asserts the scene really made an overlapping PENDING pair.
Release build.  Run: ZRCP_PORT=<port> python3 tests/b19b.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
sys.argv = sys.argv[:1]
import b19c  # noqa: E402
import game  # noqa: E402
from b19c import (EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_DYING, EF_PENDING, NAME, HY,  # noqa: E402
                  NOWHERE, DAGGER_SLOT, ents, ov)
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_GOBLIN, K_SKELETON, K_RAT, K_SLIME  # noqa: E402

SEEDS = range(1, 4)


class XWatch(b19c.Watch):
    def __call__(self, *_):
        prev = self.prev
        super().__call__()
        es = self.prev
        if prev is None:
            return
        room = self.p.rb("CUR_ROOM")
        for s in range(1, 16):
            a, b = prev[s], es[s]
            if (a["FLAGS"] & EF_PENDING and b["FLAGS"] & EF_ACTIVE and not b["FLAGS"] & (EF_PENDING | EF_DYING)
                    and b["ROOM"] == room):
                for o in range(1, 16):
                    if o != s and es[o]["FLAGS"] & EF_DYING and es[o]["ROOM"] == room and \
                            ov(self.box(b), self.box(es[o])):
                        self.bad.append(("xpop", s, o, self.t, b["KIND"], es[o]["KIND"]))


def run(p, kt, check):
    fails, runs, overl = [], 0, 0
    for kx, ky in ((K_GOBLIN, K_SKELETON), (K_SKELETON, K_GOBLIN), (K_GOBLIN, K_RAT), (K_RAT, K_SKELETON),
                   (K_SLIME, K_GOBLIN), (K_SKELETON, K_SLIME)):
        for off in (0, 2):
            for n in (1, 3):
                for seed in SEEDS:
                    p.boot(K_KNIGHT)
                    p.isolate()
                    room = p.rb("CUR_ROOM")
                    for s_ in range(1, 16):
                        if p.ent(s_)["ROOM"] == room + 1:
                            p.set_ent(s_, ROOM=NOWHERE)
                    hx = 31 - kt[K_KNIGHT][0]
                    bwx, bhx, _ = kt[kx]
                    bhy = kt[ky][1]
                    p.set_ent(0, X=hx, Y=HY, PX=hx * 8, PY=HY * 8, MODE=0, HP=250, MAXHP=250,
                              FLAGS=EF_ACTIVE | EF_PLAYER)
                    y = HY + kt[K_KNIGHT][1] - bhx
                    p.set_ent(3, KIND=kx, X=hx - bwx, Y=y, PX=(hx - bwx) * 8, PY=y * 8, MODE=0, ROOM=room,
                              FLAGS=EF_ACTIVE | EF_HOSTILE, HP=kt["hp"][kx], MAXHP=kt["hp"][kx],
                              REACT=0, FLT=0, HIT=0)
                    ry = HY + kt[K_KNIGHT][1] - bhy
                    p.set_ent(5, KIND=ky, X=1 + off, Y=ry, PX=(1 + off) * 8, PY=ry * 8, MODE=0, ROOM=room + 1,
                              FLAGS=EF_ACTIVE | EF_HOSTILE, HP=kt["hp"][ky], MAXHP=kt["hp"][ky],
                              REACT=0, FLT=0, HIT=0)
                    p.wmem(S["ST_FLAGS"], [0] * 16)
                    p.wb("DAGGERS", 30)
                    p.wmem(S["RNG_STATE"], [seed & 255, (seed >> 8) | 1])
                    p.settle()
                    w = XWatch(p, kt)
                    p.turn("L", per_tick=w)
                    runs += 1
                    es = ents(p)
                    cr = p.rb("CUR_ROOM")
                    if (cr == room + 1 and es[3]["FLAGS"] & EF_PENDING and es[5]["FLAGS"] & EF_PENDING
                            and es[3]["ROOM"] == cr and es[5]["ROOM"] == cr
                            and ov(w.box(es[3]), w.box(es[5]))):
                        overl += 1
                    for _ in range(n):
                        p.turn("L", per_tick=w)
                    p.select_slot(DAGGER_SLOT)
                    for _ in range(40):
                        alive = [s for s in (3, 5) if p.ent(s)["FLAGS"] & EF_ACTIVE and
                                 not p.ent(s)["FLAGS"] & EF_DYING and p.ent(s)["ROOM"] == p.rb("CUR_ROOM")]
                        if not alive:
                            break
                        h, e = p.ent(0), p.ent(alive[0])
                        if e["FLAGS"] & EF_PENDING:
                            p.turn("WAIT", per_tick=w)
                            continue
                        left = e["X"] < h["X"]
                        if bool(h["FLAGS"] & b19c.EF_LEFT) != left:
                            p.tap("H" if left else "L")
                            p.tick()
                        if not p.turn("FIRE", per_tick=w):
                            p.turn("WAIT", per_tick=w)
                    for _ in range(3):
                        p.turn("WAIT", per_tick=w)
                    if w.bad:
                        fails.append((f"{NAME[kx]}+{NAME[ky]} off{off} n{n} seed{seed}", w.bad[:2]))
    check(f"cross-kind arrival+follower ({runs} runs, {overl} with an overlapping PENDING pair): "
          "no pop onto a corpse, no overlap", not fails and overl > runs // 4, (overl, fails[:3]))


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)
        if S.get("KIT_DEBUG", 0):
            print("[skip] b19b needs a DEBUG_KIT=0 build", flush=True)
        else:
            p.boot(K_KNIGHT)
            g = lambda f, k: p.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
            kt = {k: (g("KT_BW", k), g("KT_BH", k), bool(g("KT_FLAGS", k) & S["KF_FLYER"])) for k in range(9)}
            kt["hp"] = {k: g("KT_HP", k) for k in range(9)}
            run(p, kt, check)
        print(f"b19b: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
