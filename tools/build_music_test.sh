#!/bin/sh
# tools/build_music_test.sh — SND-0 S1a standalone music test tape (not the game).
#
#   tools/build_music_test.sh [-o OUTDIR]
#
# 1. tools/abc2wzm.py --batch -> OUTDIR/build/music/*.asm (WZM v0.2 song data
#    from the tracked tsx JSON sources assets/sfx/music/src; always regenerated,
#    build/ is not in git). $WZM_BPM overrides the Lament's tempo (default 74;
#    key 8 stays at 96).
# 2. sjasmplus src/music/testtape.asm -> OUTDIR/build/music_test.tap / .sna /
#    .sym / .lst. Fails on any assembler error OR warning (like tools/build.sh).
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT
if [ "${1:-}" = "-o" ]; then
    [ $# -ge 2 ] || { echo "build_music_test.sh: -o needs a directory" >&2; exit 2; }
    mkdir -p "$2"
    OUT=$(cd "$2" && pwd)
    shift 2
fi
mkdir -p "$OUT/build/music"
python3 "$ROOT/tools/abc2wzm.py" --batch "$OUT/build/music" ${WZM_BPM:+--bpm "$WZM_BPM"} >/dev/null
LOG="$OUT/build/music_test.log"
cd "$OUT"
set +e
sjasmplus "$ROOT/src/music/testtape.asm" --fullpath \
    --lst=build/music_test.lst --sym=build/music_test.sym \
    -i "$ROOT/src/music" -i "$OUT/build/music" "$@" >"$LOG" 2>&1
RC=$?
set -e
grep -E '^>|rror|arning' "$LOG" || true
if [ $RC -ne 0 ]; then
    echo "build_music_test.sh: sjasmplus failed (exit $RC), full log: $LOG" >&2
    exit 1
fi
if ! grep -q 'Errors: 0, warnings: 0' "$LOG"; then
    echo "build_music_test.sh: assembler warnings are failures, full log: $LOG" >&2
    exit 1
fi
echo "build_music_test.sh: OK -> $OUT/build/music_test.tap / .sna / .sym"
