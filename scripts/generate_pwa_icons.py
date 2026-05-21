#!/usr/bin/env python3
"""Generate PWA icons from the SVG source.

Run once after cloning: python scripts/generate_pwa_icons.py
Requires: cairosvg or use the SVG directly.
"""

from __future__ import annotations

from pathlib import Path

SVG_PATH = Path(__file__).resolve().parent.parent / "pwa" / "icons" / "icon.svg"
OUT_DIR = Path(__file__).resolve().parent.parent / "pwa" / "icons"

SIZES = [192, 512]


def main() -> None:
    """Generate PNG icons at required sizes using cairosvg if available."""
    if not SVG_PATH.exists():
        print(f"SVG icon not found at {SVG_PATH}")
        return

    try:
        import cairosvg
    except ImportError:
        print("cairosvg not installed. Install it with: pip install cairosvg")
        print("The SVG icon will be used directly (supported by modern browsers).")
        return

    for size in SIZES:
        out = OUT_DIR / f"icon-{size}.png"
        if out.exists():
            print(f"✅ icon-{size}.png already exists")
            continue
        cairosvg.svg2png(url=str(SVG_PATH), write_to=str(out), output_width=size, output_height=size)
        print(f"✅ Generated icon-{size}.png ({size}x{size})")

    print("\nDone! Icons generated in pwa/icons/")


if __name__ == "__main__":
    main()
