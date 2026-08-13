"""Light is the default, dark is a choice — RFP §21.15, §629-635.

The approved mockups are light. Tying the palette to `prefers-color-scheme`
would mean a teacher whose laptop is set to dark opens the system and sees
something that does not match the design the client signed off, with no way
back. So the dark palette applies only when the person asks for it.

Two of the three assertions below guard mistakes that look like tidying:
re-adding the media query, and moving the pre-paint script out of `<head>`
into a bundle at the end of the body, which reintroduces the flash of light
before the repaint.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"
CSS = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text()
LAYOUTS = ["base_teacher.html", "base_parent.html"]


def test_the_palette_does_not_follow_the_operating_system():
    assert "prefers-color-scheme" not in CSS, (
        "the mockups are light; dark must be opt-in, not inherited from the OS"
    )


def test_a_dark_palette_exists():
    assert ':root[data-theme="dark"]' in CSS


def test_dark_overrides_the_core_colours():
    """A half-applied dark theme is worse than none — dark text on dark card."""
    block = CSS.split(':root[data-theme="dark"]', 1)[1].split("}", 1)[0]

    for token in ("--ink", "--bg", "--card", "--line", "--muted"):
        assert token in block, f"dark theme does not override {token}"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_theme_is_applied_before_the_page_paints(layout):
    html = (TEMPLATE_ROOT / layout).read_text()
    head = html.split("</head>", 1)[0]

    assert '{% include "_theme_head.html" %}' in head, (
        f"{layout} must apply the stored theme inside <head>, or the page "
        f"paints light and then repaints dark"
    )


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_offers_the_switch(layout):
    html = (TEMPLATE_ROOT / layout).read_text()

    assert '{% include "_theme.html" %}' in html


def test_the_switch_is_a_real_checkbox():
    """Reachable by keyboard and announces its own state, with no ARIA."""
    toggle = (TEMPLATE_ROOT / "_theme.html").read_text()

    assert "<label" in toggle
    assert 'type="checkbox"' in toggle


def test_the_stored_value_is_read_defensively():
    """localStorage throws in Safari private mode rather than returning null."""
    head = (TEMPLATE_ROOT / "_theme_head.html").read_text()

    assert "try" in head and "catch" in head


@pytest.mark.django_db
def test_a_page_renders_light_by_default(client, world):
    """No data-theme attribute means the light `:root` values apply."""
    assert client.login(username="dulmaa", password="test-password-1234")

    body = client.get("/bagsh/").content.decode()

    assert re.search(r"<html[^>]*data-theme", body) is None
