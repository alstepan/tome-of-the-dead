#!/bin/sh
# tools/build.sh — THE build entry point (A6): sprite packer, then sjasmplus.
#
#   tools/build.sh [-o OUTDIR] [extra sjasmplus args, e.g. -DZX0_SOURCES=0]
#
# 1. tools/zx0_sources.py -> build/zx0/sprites_zx0.asm of THIS checkout (always
#    regenerated, so a build never assembles stale packed art; the file is
#    rewritten only when it changes). Needs tools/bin/zx0 (tools/setup_zx0.sh).
#    Skipped for -DZX0_SOURCES=0 (the raw build never includes the file).
# 2. sjasmplus src/main.asm with the project flags. Run in OUTDIR (default: the
#    repo root), so the artefacts land in OUTDIR/build/: wazhack.tap, .sna,
#    .sym, .sld, .lst.
# Fails (exit 1) on any assembler error OR warning; prints the DISPLAY lines.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT
if [ "${1:-}" = "-o" ]; then
    [ $# -ge 2 ] || { echo "build.sh: -o needs a directory" >&2; exit 2; }
    mkdir -p "$2"
    OUT=$(cd "$2" && pwd)
    shift 2
fi
# The raw build (-DZX0_SOURCES=0) does not include the packed file: no packer
# run (and no tools/bin/zx0 needed) for it.
PACK=1
for a in "$@"; do
    case "$a" in
        -DZX0_SOURCES=0) PACK=0 ;;
    esac
done
if [ $PACK -eq 1 ]; then
    python3 "$ROOT/tools/zx0_sources.py"
else
    echo "build.sh: -DZX0_SOURCES=0 -> raw sources, packer skipped"
fi
mkdir -p "$OUT/build"
LOG="$OUT/build/sjasmplus.log"
cd "$OUT"
set +e
sjasmplus "$ROOT/src/main.asm" --fullpath \
    --lst=build/wazhack.lst --sld=build/wazhack.sld --sym=build/wazhack.sym \
    -i "$ROOT/src" "$@" >"$LOG" 2>&1
RC=$?
set -e
grep -E '^>|rror|arning' "$LOG" || true
if [ $RC -ne 0 ]; then
    echo "build.sh: sjasmplus failed (exit $RC), full log: $LOG" >&2
    exit 1
fi
if ! grep -q 'Errors: 0, warnings: 0' "$LOG"; then
    echo "build.sh: assembler warnings are failures, full log: $LOG" >&2
    exit 1
fi
echo "build.sh: OK -> $OUT/build/wazhack.tap / .sna / .sym"
