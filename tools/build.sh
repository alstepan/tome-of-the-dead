#!/bin/sh
# tools/build.sh — THE build entry point (A6): sprite packer, then sjasmplus.
#
#   tools/build.sh [-o OUTDIR] [extra sjasmplus args, e.g. -DPROTO_START=1]
#
# 1. tools/zx0_sources.py -> build/zx0/sprites_zx0.asm of THIS checkout (always
#    regenerated, so a build never assembles stale packed art; the file is
#    rewritten only when it changes). Needs tools/bin/zx0 (tools/setup_zx0.sh).
#    (B3B-12: the raw-sources build -DZX0_SOURCES=0 is retired; defs.asm
#    stops with an error if it is asked for.)
# 1b. tools/textpack.py -> build/text/strings.asm + strings_ids.inc (B3B-13:
#    src/strings.txt as dictionary-token streams); it re-parses its output and
#    fails on any round-trip mismatch / char outside 32..127 / > LOG_MAX.
# 1c. tools/abc2wzm.py --game -> OUTDIR/build/music_game/ (7 WZM songs + game_songs.asm),
#    INCLUDEd by src/ay.asm through the -i OUTDIR/build/music_game search path (SND-2 T2).
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
python3 "$ROOT/tools/zx0_sources.py"
python3 "$ROOT/tools/textpack.py"
mkdir -p "$OUT/build/music_game"
# SND-2: in-game songs (hps_* gate 30 + game_songs.asm) -> the AY slot (src/ay.asm, -i below)
python3 "$ROOT/tools/abc2wzm.py" --game "$OUT/build/music_game" >/dev/null
LOG="$OUT/build/sjasmplus.log"
cd "$OUT"
set +e
sjasmplus "$ROOT/src/main.asm" --fullpath \
    --lst=build/wazhack.lst --sld=build/wazhack.sld --sym=build/wazhack.sym \
    -i "$ROOT/src" -i "$OUT/build/music_game" "$@" >"$LOG" 2>&1
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
