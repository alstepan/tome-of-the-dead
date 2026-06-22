---
name: debug
description: Launch ZEsarUX with the ZRCP remote protocol and drive it over TCP — read/write registers and memory, set breakpoints, single-step, dump the screen. Use to inspect a running build, diagnose a crash/hang, or verify a routine's effect on memory.
---

# debug

Drive **ZEsarUX** via the **ZRCP** (ZEsarUX Remote Command Protocol) over TCP.
This is the foundation for agentic verification: it lets an agent observe the
real machine state instead of guessing from source.

## 1. Launch ZEsarUX listening for ZRCP

```sh
/Applications/zesarux.app/Contents/MacOS/zesarux \
  --machine 128k \
  --enable-remoteprotocol \
  --remoteprotocol-port 10000 \
  --tape build/wazhack.tap &
```

(Standard ZEsarUX flags; default ZRCP port is 10000. If the connection in step 2
is refused, verify the flag names in this ZEsarUX build via its docs/settings.)

## 2. Talk to it

ZRCP is a line-based text protocol. Each command is one line; responses end at a
`command> ` prompt. Quick one-shot from the shell:

```sh
printf 'get-registers\nread-memory 16384 16\nquit\n' | nc localhost 10000
```

For multi-step sessions, write a tiny Python helper that opens the socket, sends
commands, and reads until the prompt (commit it under `tools/` once first used).

## Key ZRCP commands

| Command                         | Purpose                                  |
|---------------------------------|------------------------------------------|
| `get-registers`                 | all regs + flags                         |
| `read-memory <addr> <len>`      | dump bytes (decimal addr)                |
| `write-memory <addr> <b> [..]`  | poke bytes                               |
| `set-breakpoint <n> PC=0x8000`  | breakpoint on condition                  |
| `enable-breakpoint <n>` / `run` | arm + continue                           |
| `enter-cpu-step` / `cpu-step`   | enter step mode / step one instruction   |
| `disassemble <addr> <count>`    | disassemble                              |
| `smartload <file>`              | load a tape/snapshot without relaunch    |
| `quit`                          | close the ZRCP session                   |

## Reading the screen

There is no AI vision needed: the screen is memory. Read the bitmap + attributes
and hash or decode them:

```sh
printf 'read-memory 16384 6912\nquit\n' | nc localhost 10000
```

`$4000` (16384) for 6912 bytes = 6144 bitmap + 768 attributes = the full frame.
The `test` skill builds golden-screen regression on top of exactly this.

## Tips

- Breakpoint at a routine entry, `run`, then `get-registers` to validate the
  contract (args in / clobbers / result) from `docs/conventions.md`.
- Compare a memory region before/after a routine to confirm the intended write
  set and nothing else (this is how regressions are caught).
