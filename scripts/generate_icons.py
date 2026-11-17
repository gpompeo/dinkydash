#!/usr/bin/env python3
"""One-off generator for every raster icon a browser can't take from the SVG.

Run by hand: the outputs are committed, so running the app needs no image
library. Re-run it whenever `web/static/favicon.svg` changes:

    venv/bin/python scripts/generate_icons.py     # requires Pillow

It redraws the same mark as `web/static/favicon.svg` (2x2 dashboard grid)
rather than rasterising the SVG, which avoids depending on an SVG renderer.
Keep the two in sync by hand: the shape is simple enough that this is cheaper
than adding cairosvg to the toolchain.

Writes, to `web/static/`, for the settings UI and the dashboard saved to a
phone or tablet home screen from `/settings/manifest.webmanifest`:
    apple-touch-icon.png    180 - iOS, full bleed: iOS rounds it itself
    icon-192.png            192 - Android, rounded like the favicon
    icon-512.png            512 - Android, the install and splash icon
    icon-maskable-512.png   512 - Android adaptive, drawn inside the safe circle
"""

import os

from PIL import Image, ImageDraw

ORANGE = (232, 93, 36, 255)      # --accent
CREAM = (255, 250, 245, 255)     # --bg
DOTS = [
    (232, 93, 36, 255),          # --accent
    (124, 92, 191, 255),         # --purple
    (22, 163, 74, 255),          # --green
    (59, 130, 246, 255),         # --blue
]

# Supersampling factor. The mark is drawn large and downscaled with LANCZOS,
# which is what keeps the rounded corners clean at 16px.
SS = 8
BASE = 128

# An Android maskable icon may be cropped to a circle of 80% of the width, so
# the grid has to sit inside that. At 0.72 the grid spans 50% of the width and
# its corners land at 70% — inside the safe circle with room to spare.
MASKABLE_GRID = 0.72


def draw_mark(size, radius=26, grid=1.0):
    """Render the icon at `size` px, drawn at SS x and downsampled.

    `radius` is the corner rounding in 128ths; pass 0 for a full-bleed square,
    which is what iOS and Android adaptive icons want — they apply their own
    mask, and rounded corners inside a rounded mask read as a shrunken icon.
    `grid` shrinks the four tiles about the centre without moving the edge.
    """
    px = size * SS
    scale = px / BASE
    img = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def s(v):
        return v * scale

    def g(v):
        """A 128-grid coordinate, pulled towards the centre by `grid`."""
        return s(64 + (v - 64) * grid)

    if radius:
        d.rounded_rectangle([0, 0, px - 1, px - 1], radius=s(radius), fill=ORANGE)
    else:
        d.rectangle([0, 0, px - 1, px - 1], fill=ORANGE)

    cells = [(20, 20), (68, 20), (20, 68), (68, 68)]
    for i, (x, y) in enumerate(cells):
        d.rounded_rectangle(
            [g(x), g(y), g(x + 40) - 1, g(y + 40) - 1], radius=s(9 * grid), fill=CREAM
        )
        # Dots read as colour at 32px+ and blur harmlessly at 16px.
        cx, cy, r = g(x + 20), g(y + 20), s(8 * grid)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOTS[i])

    return img.resize((size, size), Image.LANCZOS)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = os.path.join(root, 'web', 'static')
    os.makedirs(app, exist_ok=True)

    app_icons = [
        ('apple-touch-icon.png', draw_mark(180, radius=0)),
        ('icon-192.png', draw_mark(192)),
        ('icon-512.png', draw_mark(512)),
        ('icon-maskable-512.png', draw_mark(512, radius=0, grid=MASKABLE_GRID)),
    ]
    for name, img in app_icons:
        img.save(os.path.join(app, name), format='PNG')

    print(f"Wrote {', '.join(name for name, _ in app_icons)} to {app}")


if __name__ == '__main__':
    main()
