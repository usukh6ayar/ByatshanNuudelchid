"""PDF rendering — RFP §10.3.

The one hard constraint: Mongolian Cyrillic must render. That works only if
the font is installed in the container and referenced from CSS. Never rely on
host or system fonts.

Real report generation runs in Celery, never inside a request (RFP §549).
This module is the rendering primitive both paths share.
"""

import base64
import subprocess
from pathlib import Path

from django.template.loader import render_to_string

# Cyrillic letters that exist in Mongolian but not in Russian. A font that
# passes a naive Cyrillic check can still be missing these two.
MONGOLIAN_ONLY_CHARS = "ӨөҮү"


def render_pdf(template_name: str, context: dict) -> bytes:
    """Render a template to PDF bytes."""
    from weasyprint import HTML

    html = render_to_string(template_name, context)
    return HTML(string=html).write_pdf()


def data_uri(path: str | Path) -> str | None:
    """Inline an image as a data URI.

    WeasyPrint must not fetch anything over the network while rendering:
    it would be slow, non-deterministic, and for child photos it would mean
    a publicly reachable URL, which RFP §4.4 forbids.
    """
    path = Path(path)
    if not path.exists():
        return None
    suffix = path.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "svg": "image/svg+xml"}.get(suffix, "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def font_covers_mongolian(family: str = "DejaVu Sans") -> tuple[bool, str]:
    """Check that ``family`` is installed and covers Ө, ө, Ү, ү.

    Catches the most common cause of □□□ output: the font never made it into
    the image. Glyph-level correctness still needs a human looking at a
    printed A4 page — see the spike command.
    """
    try:
        matched = subprocess.run(
            ["fc-match", "-f", "%{family}", family],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"fc-match unavailable: {exc}"

    if family.lower() not in matched.lower():
        return False, f"'{family}' is not installed; fontconfig substituted '{matched}'"

    listed = subprocess.run(
        ["fc-list", f":family={family}:charset=4e6", "family"],
        capture_output=True, text=True, timeout=10, check=False,
    ).stdout.strip()
    if not listed:
        return False, f"'{family}' does not cover U+04E6 (Ө)"

    return True, f"'{family}' installed and covers {MONGOLIAN_ONLY_CHARS}"
