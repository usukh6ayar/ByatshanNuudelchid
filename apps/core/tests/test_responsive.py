"""The handful of responsive rules that fail silently — RFP §17, §619.

Most of a mobile layout can only be judged by looking at it on a phone, and
this file does not pretend otherwise. What it does cover is the small set of
mistakes that produce no error, look fine on a laptop, and are only visible
to the person holding the device:

* a layout with no viewport meta tag renders at 980px and is scaled down,
  so every measurement below becomes meaningless;
* a form control under 16px makes mobile Safari zoom in on focus and never
  zoom back out;
* a table without ``.table-wrap`` scrolls the whole page sideways.

Each was checked by hand at 375px on 2026-08-10. These tests exist so the
next person does not have to re-derive why the numbers are what they are.
"""

from pathlib import Path

import pytest
from django.conf import settings

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

LAYOUTS = ["base_teacher.html", "base_parent.html", "base_auth.html",
           "base_error.html"]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_declares_the_viewport(layout):
    """Without this the phone renders at 980px and scales, ignoring the CSS."""
    html = (TEMPLATE_ROOT / layout).read_text()

    assert 'name="viewport"' in html, f"{layout} has no viewport meta tag"
    assert "width=device-width" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_layout_blocks_pinch_zoom(layout):
    """RFP §629-635 — accessibility. Never disable the user's zoom."""
    html = (TEMPLATE_ROOT / layout).read_text()

    assert "user-scalable=no" not in html
    assert "maximum-scale" not in html


def test_form_controls_are_at_least_16px():
    """Mobile Safari zooms on focus below 16px and does not zoom back out.

    Asserted on the source rather than a computed style because there is no
    browser here — this is a guard against the value being "tidied" back to
    a rem figure that happens to be 15.2px.
    """
    css = CSS.read_text()
    block = css.split("input[type=text]", 1)[1].split("}", 1)[0]

    assert "font-size: 16px" in block, (
        "form controls must be 16px or larger, or iOS zooms the viewport"
    )


def test_wide_content_scrolls_inside_its_own_container():
    css = CSS.read_text()

    assert ".table-wrap { overflow-x: auto; min-width: 0; }" in css, (
        "min-width:0 is what stops a flex/grid item growing to its content "
        "and scrolling the page instead of the table"
    )


def test_every_table_that_reaches_a_browser_is_wrapped():
    """A bare wide table scrolls the page, not itself.

    The report templates are excluded deliberately: they are rendered to A4
    by WeasyPrint and never opened in a browser.
    """
    print_only = {
        "reports/child_portfolio.html",
        "reports/term_report.html",
        "reports/spike.html",
    }

    unwrapped = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATE_ROOT))
        if rel in print_only:
            continue
        html = path.read_text()
        if "<table" in html and "table-wrap" not in html:
            unwrapped.append(rel)

    assert not unwrapped, f"tables with no .table-wrap: {unwrapped}"
