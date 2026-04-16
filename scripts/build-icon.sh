#!/bin/bash
# Build macOS .icns icon from assets/focuslab-logo.svg.
# Uses only tools shipped with macOS: qlmanage, sips, iconutil.
set -e

cd "$(dirname "$0")/.."

SRC="assets/focuslab-logo.svg"
OUT_ICNS="assets/focuslab.icns"
ICONSET="$(mktemp -d)/focuslab.iconset"

[ -f "$SRC" ] || { echo "Missing $SRC"; exit 1; }

mkdir -p "$ICONSET"
TMP_DIR="$(mktemp -d)"

# Step 1: rasterize SVG at 1024 via Quick Look.
qlmanage -t -s 1024 -o "$TMP_DIR" "$SRC" >/dev/null
MASTER="$TMP_DIR/$(basename "$SRC").png"
[ -f "$MASTER" ] || { echo "qlmanage failed to produce $MASTER"; exit 1; }

# Step 2: sips-resize to the canonical iconset sizes.
for spec in \
    "16    icon_16x16.png" \
    "32    icon_16x16@2x.png" \
    "32    icon_32x32.png" \
    "64    icon_32x32@2x.png" \
    "128   icon_128x128.png" \
    "256   icon_128x128@2x.png" \
    "256   icon_256x256.png" \
    "512   icon_256x256@2x.png" \
    "512   icon_512x512.png" \
    "1024  icon_512x512@2x.png"; do
    size="$(echo "$spec" | awk '{print $1}')"
    name="$(echo "$spec" | awk '{print $2}')"
    sips -z "$size" "$size" "$MASTER" --out "$ICONSET/$name" >/dev/null
done

# Step 3: build .icns.
iconutil -c icns "$ICONSET" -o "$OUT_ICNS"
echo "Wrote $OUT_ICNS ($(stat -f%z "$OUT_ICNS") bytes)"
