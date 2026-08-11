#!/usr/bin/env python
"""Derive the served logo files from ``assets/logo.jpeg``.

Run inside the web container, which already has Pillow:

    docker compose exec web python scripts/build_logo.py

Committed rather than run once and forgotten, because the two PNGs in
``static/img/`` are derived artefacts. Without this, replacing the logo means
reverse-engineering a cutout threshold from a file nobody has the source for.

The source is a JPEG of a 3-D render on paper. Two consequences drive
everything below:

* The paper is not white. Sampling the border ring puts its darkest channel
  at 238-248, so a naive "remove pure white" leaves the whole background at a
  ghost alpha and the drop shadow with it. ``LO`` sits above that range.
* JPEG rings the high-contrast edges, so a hard threshold leaves a halo. The
  alpha ramps between ``LO`` and ``HI`` instead of switching.

Two outputs, because one image cannot do both jobs:

* ``logo-160.png`` — the whole mark including the wordmark. Login page, and
  inlined into the portfolio PDF (RFP §10.3).
* ``mark-96.png`` — the arc and the two children, cut above the lettering.
  The sidebar tile is 40px and "БЯЦХАН НҮҮДЭЛЧИД" is unreadable there.
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "logo.jpeg"
STATIC = ROOT / "static" / "img"

# Distance-from-white at which the ramp starts and ends. See the module
# docstring for where 22 comes from; it is measured, not chosen.
LO, HI = 22, 48

# Where the wordmark begins, as a fraction of the trimmed height. Found from
# the alpha coverage profile — the row between the children and the lettering
# is a local minimum — not eyeballed.
WORDMARK_TOP = 335 / 512


def cut_out(image: Image.Image) -> Image.Image:
    """Replace the paper with transparency, then trim to the ink."""
    width, height = image.size
    pixels = image.load()

    alpha = Image.new("L", (width, height))
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            distance = 255 - min(r, g, b)
            if distance <= LO:
                alpha_pixels[x, y] = 0
            elif distance >= HI:
                alpha_pixels[x, y] = 255
            else:
                alpha_pixels[x, y] = int((distance - LO) * 255 / (HI - LO))

    out = image.convert("RGBA")
    out.putalpha(alpha)
    return out.crop(out.getbbox())


def to_height(image: Image.Image, height: int) -> Image.Image:
    """Resize to ``height``, keeping the aspect ratio."""
    width = round(image.width * height / image.height)
    return image.resize((width, height), Image.LANCZOS)


def main() -> int:
    if not SOURCE.exists():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1

    full = cut_out(Image.open(SOURCE).convert("RGB"))
    STATIC.mkdir(parents=True, exist_ok=True)

    to_height(full, 160).save(STATIC / "logo-160.png", optimize=True)

    mark = full.crop((0, 0, full.width, round(full.height * WORDMARK_TOP)))
    to_height(mark.crop(mark.getbbox()), 96).save(
        STATIC / "mark-96.png", optimize=True
    )

    for path in (STATIC / "logo-160.png", STATIC / "mark-96.png"):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
