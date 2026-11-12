#!/usr/bin/env bash
# Build the itch.io HTML5 bundle: JSSpeccy 3 + the released game tape.
# Inputs are pinned: JSSpeccy version and our release tag. Output:
#   build/web/tome-of-the-dead-web-<tag>.zip   (upload) and build/web/site/ (unzipped, for local test)
# Usage: tools/web_bundle.sh [tag]   (env: JSSPECCY_VER, GAME_EXT=tap|sna)
set -euo pipefail

TAG="${1:-v1.1}"
JSSPECCY_VER="${JSSPECCY_VER:-3.2}"
JSSPECCY_SHA256="5434b5565da96a05089491f722c8fbcd8b3b70ab0277746309d2ee1db1fdbcb9"  # jsspeccy-3.2.zip
JSSPECCY_SRC_SHA256="c3bba99eefc21dc83a48461b68a3f9a45263a535f80b6716a559a155f7704a06"  # third_party/jsspeccy3-v3.2-source.tar.gz (GitHub tarball of tag v3.2, commit 1f761ca)
GAME_EXT="${GAME_EXT:-tap}"   # tap = via the 128 ROM loader (runs check_paging); sna only as a fallback
REPO="alstepan/tome-of-the-dead"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DL="$ROOT/build/web-dl"
OUT="$ROOT/build/web"
SITE="$OUT/site"
GAME="tome-of-the-dead-${TAG}.${GAME_EXT}"
JSDIR="$DL/jsspeccy-$JSSPECCY_VER"

mkdir -p "$DL/game-$TAG" "$JSDIR"

# --- fetch pinned inputs (cached), verify checksums
if [ ! -f "$JSDIR/jsspeccy.zip" ]; then
  gh release download "v$JSSPECCY_VER" -R gasman/jsspeccy3 -p "jsspeccy-$JSSPECCY_VER.zip" \
     -O "$JSDIR/jsspeccy.zip"
fi
echo "$JSSPECCY_SHA256  $JSDIR/jsspeccy.zip" | shasum -a 256 -c - >/dev/null
# GPL-3 corresponding source: kept in the repo (third_party/) and shipped inside the zip
SRC_TGZ="$ROOT/third_party/jsspeccy3-v${JSSPECCY_VER}-source.tar.gz"
echo "$JSSPECCY_SRC_SHA256  $SRC_TGZ" | shasum -a 256 -c - >/dev/null
if [ ! -f "$DL/game-$TAG/SHA256SUMS" ]; then
  gh release download "$TAG" -R "$REPO" -D "$DL/game-$TAG" --clobber \
     -p '*.tap' -p '*.sna' -p SHA256SUMS
fi
(cd "$DL/game-$TAG" && shasum -a 256 -c SHA256SUMS >/dev/null)

# --- assemble the site
rm -rf "$SITE" "$JSDIR/x"
mkdir -p "$SITE" "$JSDIR/x"
unzip -q "$JSDIR/jsspeccy.zip" -x '__MACOSX/*' -d "$JSDIR/x"
JS="$JSDIR/x"
cp -R "$JS/jsspeccy" "$SITE/jsspeccy"
find "$SITE" \( -name .DS_Store -o -name '*.map' \) -delete
cp "$JS/COPYING" "$SITE/JSSPECCY-LICENSE-GPL3.txt"
cp "$SRC_TGZ" "$SITE/"
cp "$DL/game-$TAG/$GAME" "$SITE/$GAME"
cp "$ROOT/LICENSE" "$ROOT/LICENSE-ASSETS.md" "$ROOT/THIRD-PARTY.md" "$SITE/"

cat > "$SITE/SOURCE.txt" <<TXT
This page embeds JSSpeccy 3 (v$JSSPECCY_VER), (c) Matthew Westcott, GPL-3.0 (JSSPECCY-LICENSE-GPL3.txt).
Corresponding source (GPL-3 s6): jsspeccy3-v${JSSPECCY_VER}-source.tar.gz in this bundle;
  also https://github.com/$REPO/tree/main/third_party and upstream https://github.com/gasman/jsspeccy3/tree/v$JSSPECCY_VER
Game: Tome of the Dead $TAG, https://github.com/$REPO/releases/tag/$TAG
Game licences: LICENSE, LICENSE-ASSETS.md, THIRD-PARTY.md
TXT

# Zoom 2 = 640x480 incl. border (320x240 native); the toolbar sits above it. Page is black.
cat > "$SITE/index.html" <<HTML
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tome of the Dead</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="jsspeccy/jsspeccy.js"></script>
<style>
  html, body { margin: 0; background: #000; color: #ccc; font: 13px/1.4 monospace; }
  #wrap { width: 640px; margin: 0 auto; }
  #jsspeccy { width: 640px; background: #000; }
  #hint { padding: 6px 4px; text-align: center; }
  #hint b { color: #fff; }
  #hint small { color: #888; }
</style>
</head>
<body>
<div id="wrap">
  <div id="jsspeccy"></div>
  <div id="hint">
    <b>Click the screen, then press play.</b> Keys: <b>O P</b> walk, <b>Q</b> climb up, <b>A</b> down,
    <b>Q+O / Q+P</b> jump, <b>SPACE</b> use selected icon, <b>A+SPACE</b> choose icon, <b>I</b> inventory, <b>BREAK</b> (Shift+Space) pause.<br>
    <small>Keyboard only here (no joystick). Loads in a few seconds.
    <a href="SOURCE.txt" style="color:#888">Emulator licence and source</a></small>
  </div>
</div>
<script>
  // sandbox hides Open/Find-games (the latter calls archive.org: no external requests allowed).
  var emu = JSSpeccy(document.getElementById('jsspeccy'), {
    machine: 128, zoom: 2, sandbox: true, autoStart: false, autoLoadTapes: true,
    openUrl: '$GAME'
  });
  document.getElementById('jsspeccy').addEventListener('click', function () {
    var k = document.querySelector('#jsspeccy [tabindex]'); // JSSpeccy's keyboard root
    if (k) k.focus();
  });
</script>
</body>
</html>
HTML

# --- deterministic zip (sorted, fixed mtime), index.html at the root
mkdir -p "$OUT"
ZIP="$OUT/tome-of-the-dead-web-${TAG}.zip"
rm -f "$ZIP"
cat > "$DL/mkzip.py" <<'PY'
import os, sys, zipfile
site, out = sys.argv[1:3]
files = sorted(os.path.relpath(os.path.join(d, f), site) for d, _, fs in os.walk(site) for f in fs)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for rel in files:
        zi = zipfile.ZipInfo(rel, (2026, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, open(os.path.join(site, rel), "rb").read())
PY
python3 -I "$DL/mkzip.py" "$SITE" "$ZIP"
echo "built $ZIP ($(du -k "$ZIP" | cut -f1) KB)"
