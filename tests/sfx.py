#!/usr/bin/env python3
"""SND-5: the sound-effect layer (src/ay.asm sfx_step / sfx_out / sfx_patch, src/sfx2.asm
sfx_req / sfx_msg, tools/sfx2asm.py) over the music, frame-exact (tests/sound.py's Snd
stepper: one `run` = one ISR, stopped at isr.done; music = the menu Lament vs the oracle).

  SFX1  build: sfx_tab / effect bytes in the slot == tools/sfx2asm.py's encoding of
        assets/sfx/effects.json; ids = prio << 5 | index; boot SFX_REQ 0, nothing plays
  SFX2  sfx_req (called at isr.done, returns there): idle -> stored; a lower request does
        not replace a pending higher one, >= does; A / BC kept; dropped with SND_HOLD set,
        with the SFX bit off (mode 1 / 0); accepted in mode 2 (SFX only)
  SFX3  an effect over the Lament (prio < 6): channel A (R0/R1 when tone on, R8, R6 when
        noise on, R7 bits 0/3) == the decoded effect every frame; R2-R5, R9-R12 and R7's
        other bits == the music oracle (V1 only, no R11/R12 writes; R13 unchanged); SFX_REQ
        cleared by the ISR
  SFX4  after the effect's end: chip R0..R12 == oracle again (the V1 note restored, R6 0)
  SFX5  ISR priority: a lower request is dropped (the effect runs on), >= replaces
  SFX6  ducking while any effect plays: R9/R10 = oracle - 3 (prio >= 6: - 4; floor 0, envelope
        volumes kept), released with the effect; loudness: at each effect's peak frame its R8 >
        every fixed music volume on the chip (R9 / R10), and its peak >= 14 > the music's 13
  SFX13 KILL (7) then LEVELUP (6) in one turn, either order / LEVELUP during KILL: KILL plays all
        its frames, then LEVELUP (SFX_NEXT, one deferred slot for prio >= 6)
  SFX11 R6 mirror: a MUS_SHOT start frame mid-effect (pl_out_all) keeps the effect's noise period
        on a later frame that carries it (no noise byte)
  SFX7  SND_HOLD: effect frozen (sfx_ptr unchanged), R8-R10 0, an SFX_REQ poked while
        held is dropped; after the release the effect continues at the next frame
  SFX8  SND_MODE: 1 (music only) -> request dropped and a playing effect stops with the
        music restored; 2 (SFX only) -> the effect sounds with the music silent; 0 -> nothing
  SFX9  sfx_msg: MSG 1..5 -> HIT / MISS / KILL / HURT / MISS, 8..12 -> SFX_STATUS + its pitch offset;
        sfx_abl: ABL_* -> its effect; earlier: MSG_P_HIT / P_MISS / P_KILL / M_HIT / M_MISS -> HIT / MISS / KILL / HURT /
        MISS, other codes nothing
  SFX10 cost: worst ISR (isr -> isr.done) with effects over the Lament <= 6.5k T, reported

Build first: tools/build.sh -DDEBUG_KIT=0.  Usage: ZRCP_PORT=... python3 tests/sfx.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
from game_lib import Harness, S, EMU_ARGS  # noqa: E402
from sound import Snd, Checks, SND_MODE, DONE, HOLD, MUS_SHOT  # noqa: E402
import sfx2asm  # noqa: E402

check = Checks.check
SFX_REQ = S["SFX_REQ"]
ISR_MAX = 6500
EFF = {e["name"]: e for e in sfx2asm.load(sfx2asm.DEFAULT_SRC)}
A_REGS = (0, 1, 6, 7, 8)


def regs(z):
    return {k: int(v, 16) for k, v in re.findall(r"(\w+'?)=([0-9a-fA-F]{2,4})\b", z.cmd("get-registers"))}


def duck_of(e):
    return 0 if e["prio"] == 0 else 4 if e["prio"] >= 6 else 3


def call_at_done(s, addr, a=0, bc=0):
    """At isr.done: CALL addr with A / BC, returning to isr.done. -> registers after."""
    z = s.z
    r = regs(z)
    assert r["PC"] == DONE, hex(r["PC"])
    sp = r["SP"] - 2
    s.wb(sp, DONE & 0xFF)
    s.wb(sp + 1, DONE >> 8)
    z.cmd("set-register SP=%d" % sp)
    z.cmd("set-register A=%d" % a)
    z.cmd("set-register BC=%d" % bc)
    z.cmd("set-register PC=%d" % addr)
    s._to(DONE)
    return regs(z)


class Fx:
    def __init__(self, s):
        self.s = s
        tp = s.mem(S["wzm.pl_tp"], 192)
        self.tp = [tp[2 * i] | tp[2 * i + 1] << 8 for i in range(96)]
        self.orc = s.oracle(7, 3000)
        self.k = 0                             # the next music oracle frame

    def step(self):
        self.s.frame()
        c = self.s.chip()
        w = self.orc[self.k]
        self.k += 1
        return c, w

    def music_ok(self, c, w, duck=0):
        """All but channel A / R6 == oracle (R7: bits other than 0/3). duck: R9/R10 - duck."""
        exp = bytearray(w[:13])
        if duck:
            for r in (9, 10):
                if exp[r] < 16:
                    exp[r] = max(0, exp[r] - duck)
        ok = all(c[r] == exp[r] for r in range(13) if r not in A_REGS)
        return ok and (c[7] & ~9 & 0xFF) == (w[7] & ~9 & 0xFF)

    def a_ok(self, c, fr):
        p, vol, mix, n = fr
        ok = c[8] == vol and (c[7] & 9) == mix
        if not mix & 1:
            ok &= (c[0] | c[1] << 8) == self.tp[p]
        if not mix & 8:
            ok &= c[6] == n
        return ok

    def play(self, name, n=None, duck=None):
        """Poke the request, step the effect's frames (or n). -> (a_bad, music_bad, frames)."""
        e = EFF[name]
        frames = sfx2asm.decode(e["data"])
        self.s.wb(SFX_REQ, e["id"])
        duck = duck_of(e) if duck is None else duck
        a_bad = m_bad = None
        cnt = len(frames) if n is None else n
        for j in range(cnt):
            c, w = self.step()
            if a_bad is None and not self.a_ok(c, frames[j]):
                a_bad = (j, c.hex(), frames[j])
            if m_bad is None and not self.music_ok(c, w, duck):
                m_bad = (j, c.hex(), w[:13].hex())
        return a_bad, m_bad, frames


def sfx1():
    tab = S["sfx_tab"]
    ok = S["SFX_COUNT"] == len(EFF) and all(S["SFX_" + n] == e["prio"] << 5 | e["idx"] for n, e in EFF.items())
    check("SFX1 ids = prio << 5 | index, SFX_COUNT = %d" % len(EFF), ok)
    return tab


def run(h):
    s = Snd(h).menu_start(7)
    tab = sfx1()
    bad = []
    for n, e in EFF.items():
        w = s.mem(tab + 2 * e["idx"], 2)
        a = w[0] | w[1] << 8
        if s.mem(a, len(e["data"])) != bytes(e["data"]):
            bad.append(n)
    check("SFX1 effect bytes in the AY slot == sfx2asm encoding (%d effects)" % len(EFF), not bad, bad)
    check("SFX1 boot: SFX_REQ 0, sfx_ptr 0", s.rb(SFX_REQ) == 0 and s.mem(S["sfx_ptr"], 2) == b"\0\0")

    # ---- SFX2 sfx_req ------------------------------------------------------------
    hit, miss, cast, hurt = (S["SFX_" + n] for n in ("HIT", "MISS", "SPARK", "HURT"))
    r = call_at_done(s, S["sfx_req"], hit, 0x1234)
    v1 = s.rb(SFX_REQ)
    call_at_done(s, S["sfx_req"], miss)
    v2 = s.rb(SFX_REQ)
    call_at_done(s, S["sfx_req"], cast)
    v3 = s.rb(SFX_REQ)
    call_at_done(s, S["sfx_req"], hurt)
    v4 = s.rb(SFX_REQ)
    check("SFX2 sfx_req: idle -> stored; lower kept out; equal / higher replace",
          (v1, v2, v3, v4) == (hit, hit, cast, hurt), (v1, v2, v3, v4))
    check("SFX2 sfx_req keeps A and BC", (r["AF"] >> 8, r["BC"]) == (hit, 0x1234), (hex(r["AF"]), hex(r["BC"])))
    gate = []
    for mode in (3 | HOLD, 1, 0, 2):
        s.wb(SFX_REQ, 0)
        s.wb(SND_MODE, mode)
        call_at_done(s, S["sfx_req"], miss)
        gate.append(s.rb(SFX_REQ))
    s.wb(SFX_REQ, 0)
    s.wb(SND_MODE, 3)
    check("SFX2 sfx_req gate: held / mode 1 / mode 0 dropped, mode 2 stored", gate == [0, 0, 0, miss], gate)

    # restart from a clean music start: the oracle sync
    s.menu_start(7)
    f = Fx(s)
    for _ in range(30):
        f.step()
    r13 = s.chip()[13]
    # ---- SFX3 / SFX4: HIT (prio 4) over the Lament ----------------------------------
    a_bad, m_bad, fr = f.play("HIT")
    check("SFX3 HIT over the Lament: channel A == the effect, %d frames" % len(fr), a_bad is None, a_bad)
    check("SFX3 ... R2-R5, R9-R12, R7 other bits == music oracle (V1 only)", m_bad is None, m_bad)
    check("SFX3 ... SFX_REQ cleared by the ISR, R13 unchanged", s.rb(SFX_REQ) == 0 and s.chip()[13] == r13)
    rest = None
    for j in range(64):
        c, w = f.step()
        if rest is None and c[:13] != w[:13]:
            rest = (j, c[:13].hex(), w[:13].hex())
    check("SFX4 after the end: chip R0..R12 == oracle for 64 frames (V1 note + R6 restored)",
          rest is None and s.mem(S["sfx_ptr"], 2) == b"\0\0", rest)
    # every effect, back to back with 8 music frames between
    allbad = []
    for name in EFF:
        a_bad, m_bad, _ = f.play(name)
        if a_bad or m_bad:
            allbad.append((name, a_bad, m_bad))
        for _ in range(8):
            c, w = f.step()
            if c[:13] != w[:13]:
                allbad.append((name, "restore", c[:13].hex()))
                break
    check("SFX3 all %d effects: channel A == decode, music regs == oracle (ducked for prio >= 6), restored"
          % len(EFF), not allbad, allbad[:2])

    # ---- SFX5 priority in the ISR ---------------------------------------------------
    kill = EFF["KILL"]
    a_bad, m_bad, sfr = f.play("SPARK", n=3)
    s.wb(SFX_REQ, EFF["MISS"]["id"])            # lower (2 < 4): dropped
    c, w = f.step()
    low_ok = f.a_ok(c, sfr[3]) and s.rb(SFX_REQ) == 0 and s.rb("SFX_NEXT") == 0
    s.wb(SFX_REQ, EFF["HIT"]["id"])             # equal (4): replaces
    c, w = f.step()
    eq_ok = f.a_ok(c, sfx2asm.decode(EFF["HIT"]["data"])[0])
    s.wb(SFX_REQ, kill["id"])                   # higher (7): replaces
    kfr = sfx2asm.decode(kill["data"])
    c, w = f.step()
    hi_ok = f.a_ok(c, kfr[0]) and f.music_ok(c, w, 4)
    check("SFX5 ISR priority: lower dropped (SPARK runs on), equal replaces (HIT), higher replaces (KILL)",
          a_bad is None and low_ok and eq_ok and hi_ok, (a_bad, low_ok, eq_ok, hi_ok))
    for _ in range(len(kfr) + 1):
        f.step()

    # ---- SFX13 KILL then LEVELUP (user 2026-10-19): the kill plays fully, then the level-up
    lfr = sfx2asm.decode(EFF["LEVELUP"]["data"])
    res = {}
    for order in (("KILL", "LEVELUP"), ("LEVELUP", "KILL"), ("isr",)):
        if order == ("isr",):                   # LEVELUP requested while KILL already plays
            s.wb(SFX_REQ, kill["id"])
            seq = []
            for j in range(len(kfr) + len(lfr) + 1):
                if j == 3:
                    s.wb(SFX_REQ, EFF["LEVELUP"]["id"])
                c, w = f.step()
                seq.append(c)
        else:                                   # both in the same main-code turn (sfx_req)
            for n in order:
                call_at_done(s, S["sfx_req"], EFF[n]["id"])
            seq = []
            for j in range(len(kfr) + len(lfr) + 1):
                c, w = f.step()
                seq.append(c)
        ok = all(f.a_ok(seq[j], kfr[j]) for j in range(len(kfr)))
        ok &= all(f.a_ok(seq[len(kfr) + j], lfr[j]) for j in range(len(lfr)))
        ok &= s.rb("SFX_NEXT") == 0 and s.mem(S["sfx_ptr"], 2) == b"\0\0"
        res["+".join(order)] = ok
        for _ in range(3):
            f.step()
    check("SFX13 KILL + LEVELUP in one turn (either order, or LEVELUP while KILL plays): KILL plays all "
          "%d frames, then LEVELUP all %d" % (len(kfr), len(lfr)), all(res.values()), res)
    call_at_done(s, S["sfx_req"], EFF["LEVELUP"]["id"])
    call_at_done(s, S["sfx_req"], EFF["HURT"]["id"])
    hurt_cut = (s.rb(SFX_REQ), s.rb("SFX_NEXT")) == (EFF["HURT"]["id"], EFF["LEVELUP"]["id"])
    s.wb(SFX_REQ, 0)
    s.wb("SFX_NEXT", 0)
    check("SFX13 sfx_req: HURT over a pending LEVELUP -> REQ HURT, LEVELUP deferred to SFX_NEXT", hurt_cut)
    # the slot keeps the higher priority: KILL pending, LEVELUP loses, HURT replaces KILL ->
    # KILL (7) takes the slot over LEVELUP (6); a later LEVELUP never evicts it
    ids = {n: EFF[n]["id"] for n in ("KILL", "LEVELUP", "HURT")}
    for n in ("KILL", "LEVELUP", "HURT"):
        call_at_done(s, S["sfx_req"], ids[n])
    a1 = (s.rb(SFX_REQ), s.rb("SFX_NEXT"))
    call_at_done(s, S["sfx_req"], ids["LEVELUP"])
    a2 = (s.rb(SFX_REQ), s.rb("SFX_NEXT"))
    s.wb(SFX_REQ, 0)
    s.wb("SFX_NEXT", 0)
    s.wb(SFX_REQ, ids["HURT"])                   # ISR .defer: HURT plays, slot = KILL, LEVELUP poked
    f.step()
    s.wb("SFX_NEXT", ids["KILL"])
    s.wb(SFX_REQ, ids["LEVELUP"])
    f.step()
    a3 = s.rb("SFX_NEXT")
    for _ in range(40):
        f.step()
    s.wb("SFX_NEXT", 0)
    check("SFX13 SFX_NEXT keeps the higher priority: sfx_req (HURT, KILL) then (HURT, KILL) after a "
          "LEVELUP; ISR defer keeps KILL over LEVELUP",
          a1 == (ids["HURT"], ids["KILL"]) and a2 == a1 and a3 == ids["KILL"], (a1, a2, a3))
    # stale slot: a pending pair, then a pause before any ISR took them -> nothing replays later
    call_at_done(s, S["sfx_req"], ids["KILL"])
    call_at_done(s, S["sfx_req"], ids["LEVELUP"])
    s.wb(SND_MODE, 3 | HOLD)
    s.frames(3)
    held = (s.rb(SFX_REQ), s.rb("SFX_NEXT"))
    s.wb(SND_MODE, 3)
    for _ in range(2):
        f.step()
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    for _ in range(len(EFF["HIT"]["frames"]) + 3):
        f.step()
    after = (s.mem(S["sfx_ptr"], 2), s.rb("SFX_NEXT"))
    check("SFX13 pause with a pending pair and nothing playing: SFX_REQ / SFX_NEXT cleared, no replay "
          "after the next effect", held == (0, 0) and after == (b"\0\0", 0), (held, after))

    # ---- SFX6 ducking (part of SFX3's all-effects run; explicit here) -----------------
    duck_seen = False
    a_bad, m_bad, kfr = None, None, sfx2asm.decode(kill["data"])
    s.wb(SFX_REQ, kill["id"])
    for j in range(len(kfr)):
        c, w = f.step()
        if not f.music_ok(c, w, 4):
            m_bad = (j, c.hex(), w[:13].hex())
        duck_seen |= any(w[r] < 16 and w[r] >= 4 and c[r] == w[r] - 4 for r in (9, 10))
    check("SFX6 KILL (prio 7): R9/R10 = oracle - 4 (floor 0; envelope kept) every frame, seen ducking",
          m_bad is None and duck_seen, (m_bad, duck_seen))
    for _ in range(2):                          # KILL's END frame (still owns V1), then idle
        f.step()
    # loudness + duck 3 / release, every effect over the Lament
    loud, rel, seen3 = [], [], False
    for name, e in EFF.items():
        frs = sfx2asm.decode(e["data"])
        pk = max(v for _, v, _, _ in frs)
        if name == "STEP":                       # soft by design (user 2026-10-26): v9, below the un-ducked music
            continue
        jpk = next(j for j, x in enumerate(frs) if x[1] == pk)
        s.wb(SFX_REQ, e["id"])
        for j in range(len(frs)):
            c, w = f.step()
            if j == jpk:
                mus = [c[r] for r in (9, 10) if c[r] < 16]
                if pk < 14 or not all(c[8] > m for m in mus):
                    loud.append((name, pk, c[8:11].hex()))
            if duck_of(e) == 3:
                seen3 |= any(13 >= w[r] >= 3 and c[r] == w[r] - 3 for r in (9, 10))
        for _ in range(3):
            c, w = f.step()
            if c[9:11] != w[9:11]:
                rel.append(name)
                break
    check("SFX6 loudness: every effect but STEP (soft, v9) peaks >= 14, above the (ducked) music voices at that frame",
          not loud, loud[:3])
    check("SFX6 duck 3 seen for prio < 6, released (R9/R10 == oracle) right after every effect",
          seen3 and not rel, (seen3, rel[:3]))
    for _ in range(4):
        f.step()

    # ---- SFX7 hold --------------------------------------------------------------------
    cfr = sfx2asm.decode(EFF["SPARK"]["data"])
    f.play("SPARK", n=3)
    ptr = s.mem(S["sfx_ptr"], 2)
    s.wb(SND_MODE, 3 | HOLD)
    frozen, silent = True, True
    for i in range(20):
        if i == 5:
            s.wb(SFX_REQ, EFF["HURT"]["id"])
        s.frame()
        frozen &= s.mem(S["sfx_ptr"], 2) == ptr
        silent &= s.vol() == b"\0\0\0"
    dropped = s.rb(SFX_REQ) == 0
    check("SFX7 hold: effect frozen (sfx_ptr), R8-R10 0, a request poked while held dropped",
          frozen and silent and dropped, (frozen, silent, dropped))
    s.wb(SND_MODE, 3)
    c, w = f.step()                             # the music resumes at its frozen frame k
    check("SFX7 release: the effect continues at its next frame (SPARK frame 3), music == oracle",
          f.a_ok(c, cfr[3]) and f.music_ok(c, w, 3), c.hex())
    for _ in range(len(cfr)):
        f.step()

    # ---- SFX8 SND_MODE ----------------------------------------------------------------
    s.wb(SND_MODE, 1)
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    c, w = f.step()
    m1 = c[:13] == w[:13] and s.rb(SFX_REQ) == 0 and s.mem(S["sfx_ptr"], 2) == b"\0\0"
    s.wb(SND_MODE, 3)
    f.play("LEVELUP", n=4)
    s.wb(SND_MODE, 1)
    c, w = f.step()
    m1b = c[:13] == w[:13] and s.mem(S["sfx_ptr"], 2) == b"\0\0"
    check("SFX8 mode 1 (music only): request dropped; a playing effect stops, music restored at once",
          m1 and m1b, (m1, m1b))
    s.wb(SND_MODE, 2)
    s.frames(2)
    hfr = sfx2asm.decode(EFF["HIT"]["data"])
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    ok2 = True
    for j in range(len(hfr)):
        s.frame()
        c = s.chip()
        ok2 &= f.a_ok(c, hfr[j]) and c[9:11] == b"\0\0"
    s.frame()
    ok2 &= s.vol() == b"\0\0\0"
    check("SFX8 mode 2 (SFX only): the effect sounds over silence, silent after", ok2)
    s.wb(SND_MODE, 0)
    s.frames(2)
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    s.frame()
    check("SFX8 mode 0: request dropped, silent", s.vol() == b"\0\0\0" and s.rb(SFX_REQ) == 0
          and s.mem(S["sfx_ptr"], 2) == b"\0\0")
    s.wb(SND_MODE, 3)

    # ---- SFX9 sfx_msg -------------------------------------------------------------------
    want = {1: "HIT", 2: "MISS", 3: "KILL", 4: "HURT", 5: "MISS", 6: None, 7: None, 0: None}
    got = {}
    for code, name in want.items():
        s.wb(SFX_REQ, 0)
        r = call_at_done(s, S["sfx_msg"], 0, code << 8)
        got[code] = s.rb(SFX_REQ)
        if (r["BC"] >> 8) != code:
            got[code] = "BC lost"
    s.wb(SFX_REQ, 0)
    exp = {c: (EFF[n]["id"] if n else 0) for c, n in want.items()}
    check("SFX9 sfx_msg: MSG 1..5 -> HIT/MISS/KILL/HURT/MISS, 0/6/7 nothing, B kept", got == exp, (got, exp))
    want = {8: 7, 9: -7, 10: 0, 11: -3, 12: 4, 13: None, 14: None}   # MSG -> SFX_STATUS pitch offset
    got, exp = {}, {}
    for code, xp in want.items():
        s.wb(SFX_REQ, 0)
        s.wb(S["SFX_XP"], 0x55)
        call_at_done(s, S["sfx_msg"], 0, code << 8)
        got[code] = (s.rb(SFX_REQ), s.rb(S["SFX_XP"]))
        exp[code] = (EFF["STATUS"]["id"], xp & 255) if xp is not None else (0, 0x55)
    check("SFX9 sfx_msg: status lines 8..12 -> SFX_STATUS + SFX_XP (+7 -7 0 -3 +4), 13/14 (wake/thaw) nothing",
          got == exp, (got, exp))
    abl = ["SPARK", "FIREBOLT", "FROST", "DRAIN", "LIGHTNING", "POWER", "WHIRL", "THROW", "THROW"]
    got = []
    for k, name in enumerate(abl):
        s.wb(SFX_REQ, 0)
        r = call_at_done(s, S["sfx_abl"], k)
        got.append((s.rb(SFX_REQ) == EFF[name]["id"], r["AF"] >> 8 == k))
    s.wb(SFX_REQ, 0)
    check("SFX9 sfx_abl: ABL_SPARK .. ABL_BOW -> spell / Power Strike / Whirlwind / throw, A kept",
          all(a and b for a, b in got), got)

    # ---- SFX13 (3E-T0) SFX_STATUS pitch: SFX_XP is taken at the take, only by STATUS -----
    s.menu_start(7)
    f = Fx(s)
    sf = sfx2asm.decode(EFF["STATUS"]["data"])
    bad = []
    for xp in (7, -7, -3, 4, 0):
        s.wb(S["SFX_XP"], xp & 255)
        s.wb(SFX_REQ, EFF["STATUS"]["id"])
        for j, fr in enumerate(sf):
            c, _w = f.step()
            if not f.a_ok(c, (fr[0] + xp,) + tuple(fr[1:])):
                bad.append((xp, j))
        s.frames(2)
    s.wb(S["SFX_XP"], 7)                         # a stale mailbox pitch must not leak into HIT
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    hf = sfx2asm.decode(EFF["HIT"]["data"])
    for j, fr in enumerate(hf):
        c, _w = f.step()
        if not f.a_ok(c, fr):
            bad.append(("HIT", j))
    check("SFX13 SFX_STATUS plays at SFX_XP (+7 -7 -3 +4 0); a following HIT ignores a stale SFX_XP",
          not bad, bad[:4])

    # ---- SFX11 R6 mirror across a start frame ---------------------------------------
    s.menu_start(7)
    s.frames(10)
    hfr = sfx2asm.decode(EFF["HIT"]["data"])
    jn = next(j for j in range(1, len(hfr)) if hfr[j][2] & 8 == 0 and hfr[j][3] == hfr[j - 1][3])
    s.wb(SFX_REQ, EFF["HIT"]["id"])
    r6 = []
    for j in range(len(hfr)):
        if j == jn:
            s.wb(MUS_SHOT, 4)                   # this ISR (the carried frame) = the shot start frame
        s.frame()
        c = s.chip()
        if hfr[j][2] & 8 == 0:
            r6.append((j, c[6], hfr[j][3]))
    check("SFX11 MUS_SHOT start frame mid-effect: R6 == the effect's noise period every noise frame "
          "(incl. the carried frame %d)" % jn, all(a == b for _, a, b in r6), r6)

    # ---- SFX10 cost -------------------------------------------------------------------
    # (a) every effect over the Lament; (b) the SFX worst path every frame — a HURT taken
    # each ISR (take + pitch + noise byte + R6 OUT + ducking) — over 300 frames of the
    # Lament and of Dangerous (song 2: the music's own worst frame is its frame 251)
    s.menu_start(7)
    s.frames(10)
    worst = 0
    for name in list(EFF) * 3:
        s.wb(SFX_REQ, EFF[name]["id"])
        for _ in range(len(EFF[name]["frames"]) + 2):
            t, _ft = s.frame(timed=True)
            worst = max(worst, t)
    w_eff = worst
    hw = {}
    for song in (7, 2):
        s.menu_start(7)
        if song != 7:
            s.wb(S["MUS_REQ"], song)
            s.frame()
        m = 0
        for _ in range(300):
            s.wb(SFX_REQ, EFF["HURT"]["id"])
            t, _ft = s.frame(timed=True)
            m = max(m, t)
        hw[song] = m
    # (c) 3E-T0 review: the DEFERRED take - a KILL hits its END with SFX_NEXT set and a concurrent
    # lower-priority request stored into it (defer store + .end take + frame 0 of TRAP /
    # LEVELUP in one ISR); 13-frame cycles sweep the alignment against the song
    dw = {}
    nk = len(EFF["KILL"]["frames"])
    for song in (7, 2):
        for nxt in ("TRAP", "LEVELUP"):
            s.menu_start(7)
            if song != 7:
                s.wb(S["MUS_REQ"], song)
                s.frame()
            m = 0
            end = S["sfx_d_kill"] + len(EFF["KILL"]["data"]) - 1     # the $FF byte
            for _ in range(300):                # EVERY ISR is a deferred take (all music alignments)
                s.wb(S["sfx_ptr"], end & 255)
                s.wb(S["sfx_ptr"] + 1, end >> 8)
                s.wb(S["sfx_prio"], EFF["KILL"]["id"] & 0xE0)
                s.wb(S["SFX_NEXT"], EFF["LEVELUP" if nxt == "TRAP" else "TRAP"]["id"])
                s.wb(SFX_REQ, EFF[nxt]["id"])   # lower prio than KILL: the defer store, then the END take
                t, _ft = s.frame(timed=True)
                m = max(m, t)
            dw[(song, nxt)] = m
    print("    SFX10c deferred take at END (+ concurrent request): " + ", ".join(
        "song %d %s %d T" % (k[0], k[1], v) for k, v in dw.items()), flush=True)
    worst = max([worst] + list(hw.values()))
    print(f"    SFX10: every effect over the Lament max {w_eff} T; HURT every frame: "
          f"Lament {hw[7]} T, Dangerous {hw[2]} T", flush=True)
    check(f"SFX10 ISR with effects over the music <= {ISR_MAX} T (worst {worst})", worst <= ISR_MAX, worst)
    # the deferred take is a documented exception: proposed contract 6,550 T (manager decision,
    # 3E-T0 review; real-tick gate evidence in sound.md). Every other case stays <= ISR_MAX.
    check(f"SFX10c deferred take at END <= 6550 T (worst {max(dw.values())})", max(dw.values()) <= 6550, dw)


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        run(h)
    print(f"sfx: {'FAIL' if Checks.bad else 'PASS'} ({Checks.n - len(Checks.bad)}/{Checks.n} checks passed)"
          + (": " + ", ".join(Checks.bad) if Checks.bad else ""), flush=True)
    return 1 if Checks.bad else 0


if __name__ == "__main__":
    sys.exit(main())
