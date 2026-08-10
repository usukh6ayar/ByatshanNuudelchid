"""Every icon reference resolves to an icon that exists.

The sprite in `templates/_icons.html` is referenced as
`<svg class="ic"><use href="#i-children"></use></svg>`. A reference to an id
that was renamed, or never defined, renders **nothing at all** — no error, no
console warning, no broken-image marker. The nav item keeps its label and
quietly loses its picture, and nobody notices until a screenshot.

Two other things are asserted here because they fail the same silent way:

* `viewBox` on every symbol. Without it the referencing 20×20 box crops the
  24-unit artwork instead of scaling it — which is what the first version of
  this sprite did, using `<g>` where it needed `<symbol>`.
* The sprite host must not be `display:none`. Several browsers refuse to
  render symbols out of a hidden subtree; the safe pattern is a zero-sized
  absolutely positioned element, which is what is used.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"
SPRITE = TEMPLATE_ROOT / "_icons.html"


def markup(path: Path) -> str:
    """Template source with `{% comment %}` blocks removed.

    These files document themselves by quoting the markup they describe —
    `_icons.html` opens by showing an example `<use>` tag — and a checker
    that reads its own documentation as code finds icons nobody renders.
    """
    return re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
        "",
        path.read_text(),
        flags=re.DOTALL,
    )


def defined_ids() -> set[str]:
    return set(re.findall(r'<symbol\s+id="([^"]+)"', markup(SPRITE)))


def references() -> list[tuple[str, str]]:
    """Every `<use href="#…">` in every template, with the file it is in."""
    found = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        for icon in re.findall(r'<use\s+href="#([^"]+)"', markup(path)):
            found.append((str(path.relative_to(TEMPLATE_ROOT)), icon))
    return found


def test_the_sprite_defines_icons():
    """Guard against the regex silently matching nothing."""
    assert len(defined_ids()) >= 10


def test_the_templates_reference_icons():
    assert len(references()) >= 10


def test_every_reference_resolves():
    known = defined_ids()
    missing = [(where, icon) for where, icon in references() if icon not in known]

    assert not missing, (
        f"icons referenced but not defined in _icons.html: {missing}. "
        f"Defined: {sorted(known)}"
    )


@pytest.mark.parametrize("symbol_id", sorted(defined_ids()))
def test_every_symbol_carries_a_viewbox(symbol_id):
    """No viewBox means the artwork is cropped, not scaled."""
    block = re.search(
        rf'<symbol\s+id="{re.escape(symbol_id)}"[^>]*>', markup(SPRITE)
    )

    assert block is not None
    assert "viewBox=" in block.group(0), f"{symbol_id} has no viewBox"


def test_the_sprite_host_is_not_display_none():
    """Hidden subtrees stop some browsers rendering referenced symbols.

    The root element is found by matching the `<svg …>` that opens the
    sprite, not by splitting on the first `>` — the file starts with a
    `{% comment %}` block whose own angle brackets would match first.
    """
    host = re.search(r"<svg\b[^>]*>", markup(SPRITE)).group(0)
    compact = host.replace(" ", "")

    assert "display:none" not in compact
    assert "position:absolute" in compact


@pytest.mark.parametrize("layout", ["base_teacher.html", "base_parent.html"])
def test_a_layout_that_uses_icons_includes_the_sprite(layout):
    """`<use>` resolves within the document, so the sprite has to be in it."""
    html = markup(TEMPLATE_ROOT / layout)

    if "<use " in html:
        assert '{% include "_icons.html" %}' in html, (
            f"{layout} references icons but never includes the sprite"
        )
