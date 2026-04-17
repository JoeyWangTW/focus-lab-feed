"""Build macOS .icns from assets/focuslab-icon.svg.

Pipeline: qlmanage rasterizes the SVG at 1024 (but returns opaque PNG — it
fills transparent SVG areas with white). We apply a rounded-rect alpha mask
at each iconset size so the corners are actually transparent, then iconutil
packs the result into .icns.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "focuslab-icon.svg"
OUT_ICNS = ROOT / "assets" / "focuslab.icns"

# macOS iconset layout. Tuple of (pixel_size, filename).
SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

# Apple's squircle corner radius is roughly 22.5% of width.
CORNER_RATIO = 230 / 1024


def render_master(svg: Path, size: int) -> Image.Image:
    """Rasterize the SVG to a single opaque PNG via qlmanage, return as RGBA.

    qlmanage flattens transparency to white — we undo this per-size with an
    alpha mask in `mask_squircle`, so the opaque master is fine.
    """
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(
            ["qlmanage", "-t", "-s", str(size), "-o", d, str(svg)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        rendered = Path(d) / f"{svg.name}.png"
        if not rendered.exists():
            raise RuntimeError(f"qlmanage failed to produce {rendered}")
        img = Image.open(rendered).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img


def mask_squircle(img: Image.Image) -> Image.Image:
    """Replace img's alpha channel with a rounded-rect mask — the corners
    outside the squircle become fully transparent."""
    size = img.size[0]
    radius = max(1, round(size * CORNER_RATIO))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=radius, fill=255,
    )
    out = img.copy()
    out.putalpha(mask)
    return out


def main() -> int:
    if not SRC.exists():
        print(f"Missing {SRC}", file=sys.stderr)
        return 1

    master = render_master(SRC, 1024)

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "focuslab.iconset"
        iconset.mkdir()

        for size, name in SIZES:
            if size == 1024:
                resized = master.copy()
            else:
                resized = master.resize((size, size), Image.LANCZOS)
            masked = mask_squircle(resized)
            masked.save(iconset / name, "PNG")

        OUT_ICNS.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_ICNS)],
            check=True,
        )

    size_bytes = OUT_ICNS.stat().st_size
    print(f"Wrote {OUT_ICNS} ({size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
