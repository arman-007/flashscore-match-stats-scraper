"""Generate the Apify Store logo.

Constraints it is drawn against:

* It must read at **76x76**, the Store card size, and still be recognisable at
  38px: no text, no fine strokes.
* It must not resemble Flashscore's branding (dark navy, red-pink accent,
  lightning-bolt wordmark). This shares the deep indigo and teal of the other
  Flashscore Actors in this account, so they read as one family.

The mark is a pitch seen from above (outline, halfway line, centre circle)
with three rising stat bars in front of it.

Usage:  python scripts/make-logo.py [out.png] [size]
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw

BG = (30, 27, 75)
PITCH = (129, 140, 248)
BAR_LIGHT = (226, 232, 240)
ACCENT = (45, 212, 191)

SUPERSAMPLE = 4


def draw_logo(size: int) -> Image.Image:
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)

    def box(x0: float, y0: float, x1: float, y1: float) -> list[int]:
        return [int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)]

    line = max(2, int(s * 0.035))
    d.rounded_rectangle(box(0.14, 0.16, 0.86, 0.62), radius=int(s * 0.04), outline=PITCH, width=line)
    d.line(box(0.50, 0.16, 0.50, 0.62), fill=PITCH, width=line)
    d.ellipse(box(0.41, 0.30, 0.59, 0.48), outline=PITCH, width=line)

    base = 0.86
    for x, top, colour in ((0.24, 0.62, BAR_LIGHT), (0.42, 0.52, BAR_LIGHT), (0.60, 0.40, ACCENT)):
        d.rounded_rectangle(box(x, top, x + 0.15, base), radius=int(s * 0.03), fill=colour, outline=BG, width=line)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else ".actor/logo.png"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 512
    draw_logo(size).save(out)
    print(f"wrote {out} ({size}x{size})")


if __name__ == "__main__":
    main()
