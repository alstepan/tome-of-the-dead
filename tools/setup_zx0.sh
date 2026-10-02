#!/bin/sh
# Build Einar Saukas' ZX0 compressor (zx0) and reference decompressor (dzx0)
# into tools/bin/. Pinned commit; idempotent. The repo checkout (with the Z80
# decompressors dzx0_standard.asm etc.) is kept in tools/bin/ZX0-src.
set -eu
PIN=ecde3a2ae05061fe06469ed46df81a33b7de7d86
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN="$ROOT/tools/bin"
SRC="$BIN/ZX0-src"
mkdir -p "$BIN"
if [ -x "$BIN/zx0" ] && [ -x "$BIN/dzx0" ] && [ -d "$SRC/.git" ] \
   && [ "$(git -C "$SRC" rev-parse HEAD)" = "$PIN" ]; then
    echo "zx0/dzx0 already built at $PIN"; exit 0
fi
rm -rf "$SRC"
git clone https://github.com/einar-saukas/ZX0 "$SRC"
git -C "$SRC" checkout --quiet "$PIN"
CC=${CC:-cc}
$CC -O2 -o "$BIN/zx0"  "$SRC"/src/zx0.c  "$SRC"/src/compress.c "$SRC"/src/optimize.c "$SRC"/src/memory.c
$CC -O2 -o "$BIN/dzx0" "$SRC"/src/dzx0.c
echo "built $BIN/zx0 and $BIN/dzx0 at $PIN"
