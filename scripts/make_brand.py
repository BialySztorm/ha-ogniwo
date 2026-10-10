#!/usr/bin/env python3
"""Draw the brand icons HACS looks for in custom_components/ogniwo/brand/.

The artwork is generated rather than hand-drawn so it can be reproduced and
adjusted without a graphics editor, and so nobody has to wonder where a binary
in the repository came from:

    python scripts/make_brand.py

It needs Pillow, which the test image already has. Output is a flame on a
transparent background at the two sizes Home Assistant's brand guidelines ask
for: 256 px and 512 px square.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "ogniwo" / "brand"
SIZES = {"icon.png": 256, "icon@2x.png": 512}
# Drawn large and scaled down: cheaper than antialiasing the curves by hand.
SUPERSAMPLE = 4

OUTER_FLAME = "#e8590c"
INNER_FLAME = "#ffc93c"
GRATE_COLOUR = "#37474f"

# Flame half-outlines as cubic beziers in a unit square, y growing downwards.
# Each runs from the tip to the outer corner of a flat base; mirroring closes the
# shape across that base, which is what keeps it a flame and not a leaf.
OUTER_RIGHT = ((0.50, 0.04), (0.74, 0.26), (0.96, 0.62), (0.78, 0.86))
INNER_RIGHT = ((0.50, 0.34), (0.64, 0.48), (0.76, 0.70), (0.62, 0.86))

# The grate the flame stands on, wider than its base so the mark has a footing.
GRATE = (0.16, 0.855, 0.84, 0.955)
GRATE_RADIUS = 0.05


def bezier(control: tuple[tuple[float, float], ...], steps: int = 60):
    """Sample a cubic bezier, so a polygon can stand in for a curve."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = control
    for step in range(steps + 1):
        t = step / steps
        u = 1 - t
        a, b, c, d = u**3, 3 * u**2 * t, 3 * u * t**2, t**3
        yield (
            a * x0 + b * x1 + c * x2 + d * x3,
            a * y0 + b * y1 + c * y2 + d * y3,
        )


def flame(control: tuple[tuple[float, float], ...], size: int) -> list[tuple[float, float]]:
    """Build a closed, symmetric flame outline scaled to a square of `size`."""
    right = list(bezier(control))
    # Mirroring the sampled half costs nothing and guarantees the two sides match.
    left = [(1 - x, y) for x, y in reversed(right)]
    return [(x * size, y * size) for x, y in right + left]


def draw(size: int) -> Image.Image:
    """Render the mark at one size."""
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    pen.rounded_rectangle(
        [coordinate * canvas for coordinate in GRATE],
        radius=GRATE_RADIUS * canvas,
        fill=GRATE_COLOUR,
    )

    pen.polygon(flame(OUTER_RIGHT, canvas), fill=OUTER_FLAME)
    pen.polygon(flame(INNER_RIGHT, canvas), fill=INNER_FLAME)

    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    """Write every icon HACS and the brands repository ask for."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=BRAND_DIR, help="directory for the icons")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, size in SIZES.items():
        path = args.out / name
        draw(size).save(path, optimize=True)
        print(f"{path}: {size}x{size}, {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
