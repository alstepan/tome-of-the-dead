#!/usr/bin/env python3
"""PERF-GHOST: instruction-level profile of ONE tick (diagnostic, not a gate).

trace_tick(z, stop_pc, sld, shadow) single-steps the emulator (ZRCP cpu-step mode) from the current
PC to stop_pc, reading PC / SP / the T-state counter after every instruction, and returns
(exclusive T per routine, inclusive T per called routine, calls per routine). Routines are the
global labels of the .sld, per page, so bank-1 / 3 / 6 / 7 code at the same $C000+ address is told
apart by the paged bank (PORT_7FFD_SHADOW & 7, re-read after an OUT). A call is an executed CALL /
RST (SP - 2 and the PC left the fall-through); its frame ends when SP rises above the return slot;
a call to jp_hl (farb's dispatch) is named after the jump's target.
tests/budget.py runs it under BUDGET_TRACE=<measured tick index>; ~40k instructions a tick at 4 ZRCP
round trips each: one to two minutes.
"""
import bisect
import os
import collections
import re

CALL_OPS = {0xCD, 0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC,
            0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF}


def load_sld(path):
    """{page: ([addr], [name])} of the global code labels (key -1: addresses below $C000)."""
    pages = collections.defaultdict(set)
    for ln in open(path, errors="replace"):
        f = ln.rstrip("\n").split("|")
        if len(f) < 8 or f[6] != "L":
            continue
        d = f[7].split(",")
        loc = os.environ.get("TRACE_LOCAL", "").split(",")
        if len(d) < 3 or (d[2] and d[1] not in loc) or "+equ" in d[3:] or not d[1]:
            continue                                  # local labels (but TRACE_LOCAL=parent,..) / EQUs
        try:
            page, val = int(f[4]), int(f[5])
        except ValueError:
            continue
        name = (d[0] + "." if d[0] else "") + d[1] + ("." + d[2] if d[2] else "")
        if val < 0xC000 and page not in (5, 2):
            continue                                  # bank-1 / 3 data assembled under $C000 (DISP / slot maps)
        pages[page if val >= 0xC000 else -1].add((val, name))
    return {k: ([a for a, _ in sorted(v)], [n for _, n in sorted(v)]) for k, v in pages.items()}


def name_of(sld, pc, bank):
    key = bank if pc >= 0xC000 else -1
    if key not in sld:
        return f"?{bank}:{pc:04x}"
    addrs, names = sld[key]
    i = bisect.bisect_right(addrs, pc) - 1
    return names[i] if i >= 0 else f"?{pc:04x}"


def _regs(z):
    r = z.cmd("get-registers")
    return (int(re.search(r"PC=([0-9a-fA-F]{4})", r).group(1), 16),
            int(re.search(r"SP=([0-9a-fA-F]{4})", r).group(1), 16))


def trace_tick(z, stop_pc, sld, shadow_addr, max_steps=300000):
    excl, incl, calls = collections.Counter(), collections.Counter(), collections.Counter()
    stack = []                                        # [sp_after_call, name, t0]
    pc, sp = _regs(z)
    t_prev = int(z.cmd("get-tstates-partial"))
    bank = z.read_memory(shadow_addr, 1)[0] & 7
    for _ in range(max_steps):
        if pc == stop_pc:
            break
        op = z.read_memory(pc, 1)[0]
        here = name_of(sld, pc, bank)
        z.cmd("cpu-step")
        npc, nsp = _regs(z)
        t = int(z.cmd("get-tstates-partial"))
        excl[here] += t - t_prev
        if op in (0xD3, 0xED):                        # OUT (n),A / OUT (C),r may page
            bank = z.read_memory(shadow_addr, 1)[0] & 7
        while stack and nsp > stack[-1][0]:           # RET (or a dropped return) ends frames
            s, nm, t0 = stack.pop()
            incl[nm] += t - t0
            calls[nm] += 1
        if stack and stack[-1][1] == "jp_hl":         # farb's dispatch: name the frame by the target
            stack[-1][1] = name_of(sld, npc, bank)
        fall = pc + (3 if (op == 0xCD or op & 7 == 4) else 1)
        if op in CALL_OPS and nsp == (sp - 2) & 0xFFFF and npc != fall:
            stack.append([nsp, name_of(sld, npc, bank), t_prev])
        pc, sp, t_prev = npc, nsp, t
    return excl, incl, calls


def report(excl, incl, calls, n=45):
    lines = ["[trace] exclusive T (top %d): " % n + ", ".join(f"{k}={v}" for k, v in excl.most_common(n)),
             "[trace] inclusive T / calls (top %d): " % n
             + ", ".join(f"{k}={v}/{calls[k]}" for k, v in incl.most_common(n))]
    show = os.environ.get("TRACE_SHOW")           # a regex: every routine matching it, exclusive T
    if show:
        rx = re.compile(show)
        lines.append("[trace] matching %s: " % show + ", ".join(
            f"{k}={v}" for k, v in sorted(excl.items(), key=lambda kv: -kv[1]) if rx.search(k)))
    return "\n".join(lines)
