#!/bin/bash
# Build macOS .icns from assets/focuslab-icon.svg.
# Thin wrapper around scripts/build_icon.py so the .venv's Pillow is active.
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Create it first: python3 -m venv .venv && pip install pillow"
    exit 1
fi

source .venv/bin/activate

# Ensure Pillow is present (idempotent).
python3 -c "import PIL" 2>/dev/null || pip install pillow >/dev/null

python3 scripts/build_icon.py
