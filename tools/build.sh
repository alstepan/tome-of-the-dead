#!/bin/sh
# tools/build.sh — THE build entry point (A6): sprite packer, then sjasmplus.
#
#   tools/build.sh [-o OUTDIR] [extra sjasmplus args, e.g. -DPROTO_START=1]
#   tools/build.sh --items        3E-T4 item text only, verbose (tools/itempack.py)
#
# 1. tools/zx0_sources.py -> build/zx0/sprites_zx0.asm of THIS checkout (always
#    regenerated, so a build never assembles stale packed art; the file is
#    rewritten only when it changes). Needs tools/bin/zx0 (tools/setup_zx0.sh).
#    (B3B-12: the raw-sources build -DZX0_SOURCES=0 is retired; defs.asm
#    stops with an error if it is asked for.)
# 1b. tools/textpack.py -> build/text/strings.asm + strings_ids.inc (B3B-13:
#    src/strings.txt as dictionary-token streams); it re-parses its output and
#    fails on any round-trip mismatch / char outside 32..127 / > LOG_MAX.
# 1b''. tools/instr_pack.py -> build/text/instr_p{1,2,3}.inc (INSTR-BUILD HOW TO PLAY pages).
# 1c. tools/abc2wzm.py --game -> OUTDIR/build/music_game/ (7 WZM songs + game_songs.asm),
#    INCLUDEd by src/ay.asm through the -i OUTDIR/build/music_game search path (SND-2 T2).
# 1d. tools/sfx2asm.py -> OUTDIR/build/sfx/ (sfx_ids.inc + sfx_data.asm, SND-5; -i path).
# 2. sjasmplus src/main.asm with the project flags. Run in OUTDIR (default: the
#    repo root), so the artefacts land in OUTDIR/build/: wazhack.tap, .sna,
#    .sym, .sld, .lst.
# Fails (exit 1) on any assembler error OR warning; prints the DISPLAY lines.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
# 3E-T4 stand-alone target (verbose itempack report; the default build also runs it): writes build/text/items_tab.asm, items_fx_stems.asm, items_ovl_stems.asm,
# items_ids.inc.
if [ "${1:-}" = "--items" ]; then
    shift
    exec python3 "$ROOT/tools/itempack.py" "$@"
fi
OUT=$ROOT
if [ "${1:-}" = "-o" ]; then
    [ $# -ge 2 ] || { echo "build.sh: -o needs a directory" >&2; exit 2; }
    mkdir -p "$2"
    OUT=$(cd "$2" && pwd)
    shift 2
fi
# DBG-1: the extra args go to sjasmplus as -D defines; a double-dash one (e.g.
# --DEBUG_KIT=0) was only an "unrecognized option" line of sjasmplus while the
# build went on with the default flags. Refuse it before anything runs.
for a in "$@"; do
    case "$a" in
        --*) echo "build.sh: unknown option '$a' (defines are single-dash: use -D${a#--})" >&2
             exit 2 ;;
    esac
done
python3 "$ROOT/tools/zx0_sources.py"
python3 "$ROOT/tools/textpack.py"
# INSTR-BUILD: the HOW TO PLAY page images (docs/design/instructions_screen.txt + the
# PAGES table) -> build/text/instr_p1..3.inc (src/main.asm "OVERLAYS")
python3 "$ROOT/tools/instr_pack.py"
# 1b'. 3E-T4b: item text (src/items.txt) -> build/text/items_tab.asm + items_ids.inc; the
# RESIDENT part is INCLUDEd in bank 1 before ovl_blobs (main.asm); the fx / page overlay
# streams (items_fx_stems.asm, items_ovl_stems.asm) are generated but not included yet.
python3 "$ROOT/tools/itempack.py" >/dev/null
mkdir -p "$OUT/build/music_game"
# SND-2: in-game songs (hps_* gate 30 + game_songs.asm) -> the AY slot (src/ay.asm, -i below)
python3 "$ROOT/tools/abc2wzm.py" --game "$OUT/build/music_game" >/dev/null
# SND-5: sound effects (assets/sfx/effects.json) -> sfx_ids.inc (main.asm) + sfx_data.asm (ay.asm)
python3 "$ROOT/tools/sfx2asm.py" "$OUT/build/sfx" >/dev/null
LOG="$OUT/build/sjasmplus.log"
cd "$OUT"
# 3E-T1 overlays (main.asm "OVERLAYS"): pass 1 (-DOVL_PASS=1) assembles the
# raw overlay images to build/ovl/*.bin (its other outputs are overwritten);
# each is packed with tools/bin/zx0; pass 2 (the real build) INCBINs the
# packed streams (-i build/ovl) and writes the raw images again, which must
# equal pass 1's (else an overlay depends on the packed sizes: fail).
OVL="$OUT/build/ovl"
rm -rf "$OVL"
# no stale artefacts survive a failed build (pass 1 writes none: OVL_PASS 1
# skips main.asm's SAVETAP / SAVESNA; pass 2 writes them only on success paths)
rm -f build/wazhack.tap build/wazhack.sna build/wazhack.sym
mkdir -p "$OVL"
set +e
sjasmplus "$ROOT/src/main.asm" --fullpath --sym="$OVL/pass1.sym" \
    -i "$ROOT/src" -i "$OUT/build/music_game" -i "$OUT/build/sfx" -i "$OUT/build" -i "$OVL" \
    -DOVL_PASS=1 "$@" >"$OVL/pass1.log" 2>&1
RC=$?
set -e
if [ $RC -ne 0 ] || ! grep -q 'Errors: 0, warnings: 0' "$OVL/pass1.log"; then
    grep -E 'rror|arning' "$OVL/pass1.log" || true
    echo "build.sh: overlay pass 1 failed, full log: $OVL/pass1.log" >&2
    exit 1
fi
for f in "$OVL"/*.bin; do
    [ -e "$f" ] || continue
    "$ROOT/tools/bin/zx0" -f "$f" "${f%.bin}.zx0" >/dev/null 2>&1 || {
        echo "build.sh: zx0 failed on $f (run tools/setup_zx0.sh)" >&2; exit 1; }
    mv "$f" "${f%.bin}.raw1"
done
set +e
sjasmplus "$ROOT/src/main.asm" --fullpath \
    --lst=build/wazhack.lst --sld=build/wazhack.sld --sym=build/wazhack.sym \
    -i "$ROOT/src" -i "$OUT/build/music_game" -i "$OUT/build/sfx" -i "$OUT/build" -i "$OVL" "$@" >"$LOG" 2>&1
RC=$?
set -e
grep -E '^>|rror|arning' "$LOG" || true
fail() {   # a failed pass 2 leaves no tape / snapshot / symbols behind
    rm -f build/wazhack.tap build/wazhack.sna build/wazhack.sym
    echo "build.sh: $1" >&2
    exit 1
}
[ $RC -eq 0 ] || fail "sjasmplus failed (exit $RC), full log: $LOG"
grep -q 'Errors: 0, warnings: 0' "$LOG" || fail "assembler warnings are failures, full log: $LOG"
for f in "$OVL"/*.raw1; do
    [ -e "$f" ] || continue
    cmp -s "$f" "${f%.raw1}.bin" || fail "overlay ${f%.raw1}.bin differs between the passes"
done
echo "build.sh: OK -> $OUT/build/wazhack.tap / .sna / .sym"
