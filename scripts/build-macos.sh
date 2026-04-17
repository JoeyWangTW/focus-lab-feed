#!/bin/bash
set -e

echo "=== Focus Lab Feed — macOS Build ==="

# Ensure we're in project root
cd "$(dirname "$0")/.."

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Create it first: python3 -m venv .venv"
    exit 1
fi

source .venv/bin/activate

# Install build dependencies
echo "[build] Installing build dependencies..."
pip install pyinstaller pywebview 2>&1 | tail -1

# Install app dependencies
echo "[build] Installing app dependencies..."
pip install -r requirements.txt -r requirements-app.txt 2>&1 | tail -1

# Clean previous builds
echo "[build] Cleaning previous builds..."
rm -rf build/ dist/

# Run PyInstaller
echo "[build] Building .app bundle..."
pyinstaller focus-lab.spec --noconfirm

# Check if .app was created
APP_PATH="dist/Focus Lab Feed.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: .app bundle not found at $APP_PATH"
    exit 1
fi

echo "[build] .app bundle created: $APP_PATH"

# Create DMG
echo "[build] Creating .dmg installer..."
DMG_PATH="dist/FocusLabFeed.dmg"
hdiutil create \
    -volname "Focus Lab Feed" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo ""
echo "=== Build Complete ==="
echo "  .app: $APP_PATH"
echo "  .dmg: $DMG_PATH"
echo ""
echo "To test: open \"$APP_PATH\""
echo "To distribute: share $DMG_PATH"
