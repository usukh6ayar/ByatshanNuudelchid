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
    """Every icon reference in every template, with the file it is in.

    Two forms, because the components added with the 2026-08-16 redesign
    introduced one level of indirection:

    * **Literal** — `<use href="#i-children">`, written in the template.
    * **Parameterised** — a component in `components/` writes
      `<use href="#i-{{ icon }}">` and its callers pass
      `{% include "components/stat.html" with icon="children" %}`.

    The second form cannot be resolved by looking at the component alone, so
    the caller's argument is what gets checked. Without this the reference
    would simply disappear from the audit, and a typo in `icon="childrne"`
    would render nothing at all — exactly the silent failure this file
    exists to catch, just moved one file further away.
    """
    found = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATE_ROOT))
        text = markup(path)

        for icon in re.findall(r'<use\s+href="#([^"]+)"', text):
            if "{{" in icon:
                continue          # resolved through its callers, below
            found.append((rel, icon))

        # `{% include … with … icon="report" … %}` → `i-report`
        for tag in re.findall(r"\{%\s*include\s+.*?%\}", text, flags=re.DOTALL):
            for name in re.findall(r'\bicon="([^"]*)"', tag):
                found.append((rel, f"i-{name}"))

    return found


def variable_reference_files() -> set[str]:
    """Templates that build an icon id from a variable."""
    found = set()
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        for icon in re.findall(r'<use\s+href="#([^"]+)"', markup(path)):
            if "{{" in icon:
                found.add(str(path.relative_to(TEMPLATE_ROOT)))
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


def test_only_components_build_an_icon_id_from_a_variable():
    """The indirection stays where the audit can follow it.

    `references()` resolves `<use href="#i-{{ icon }}">` by reading the
    `icon="…"` argument its callers pass. That only works while the pattern
    is confined to `components/`, whose callers are all `{% include %}`
    tags. A page template building an id out of view context — say from a
    model field — would drop out of the check entirely and lose its icon
    silently, which is the failure this file exists to prevent.
    """
    stray = {
        path for path in variable_reference_files()
        if not path.startswith("components/")
    }

    assert not stray, (
        f"icon ids built from a variable outside components/: {sorted(stray)}. "
        f"Pass the name into a component instead, or write the id literally."
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
