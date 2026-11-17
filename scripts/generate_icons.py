#!/usr/bin/env python3
"""One-off generator for every raster icon a browser can't take from the SVG.

Run by hand: the outputs are committed, so running the app needs no image
library. Re-run it whenever `web/static/favicon.svg` changes:

    venv/bin/python scripts/generate_icons.py     # requires Pillow

It redraws the same mark as `web/static/favicon.svg` (a "P" with a dash)
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

NIGHT = (26, 27, 38, 255)        # --bg, dark theme
BLUE = (122, 162, 247, 255)      # --accent, dark theme
PURPLE = (187, 154, 247, 255)    # --purple, dark theme

# Supersampling factor. The mark is drawn large and downscaled with LANCZOS,
# which is what keeps the rounded corners clean at 16px.
SS = 8
BASE = 128

# An Android maskable icon may be cropped to a circle of 80% of the width, so
# the mark has to sit inside that. At 0.72 the mark spans about 48% of the
# width and its corners land well inside the safe circle.
MASKABLE_GRID = 0.72


def draw_mark(size, radius=26, grid=1.0):
    """Render the icon at `size` px, drawn at SS x and downsampled.

    `radius` is the corner rounding in 128ths; pass 0 for a full-bleed square,
    which is what iOS and Android adaptive icons want — they apply their own
    mask, and rounded corners inside a rounded mask read as a shrunken icon.
    `grid` shrinks the lettering about the centre without moving the edge.
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
        d.rounded_rectangle([0, 0, px - 1, px - 1], radius=s(radius), fill=NIGHT)
    else:
        d.rectangle([0, 0, px - 1, px - 1], fill=NIGHT)

    # The stem, then the bowl as a ring (a filled disc with the background
    # punched out), then the dash. Same numbers as the SVG.
    d.rounded_rectangle([g(34), g(22), g(52) - 1, g(106) - 1], radius=s(9 * grid), fill=BLUE)
    cx, cy = g(70), g(52)
    for radius_128, colour in ((30, BLUE), (12, NIGHT)):
        r = s(radius_128 * grid)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)
    d.rounded_rectangle([g(62), g(94), g(100) - 1, g(106) - 1], radius=s(6 * grid), fill=PURPLE)

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
