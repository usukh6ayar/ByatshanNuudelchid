"""Every template compiles, and no internal commentary reaches the browser.

Django's `{# ... #}` is a **single-line** comment. The lexer matches it with
`{#.*?#}` and no DOTALL flag, so a comment written across several lines is
not a comment at all: the text becomes literal output, and any `{% ... %}`
inside it is parsed as a real tag.

Both failure modes are silent in the ordinary sense — nothing raises at
import time — and both are worth a test:

* the prose leaks into the page, in English, in front of Mongolian-speaking
  parents (RFP §611);
* or, if the prose happens to mention a tag, the template stops compiling and
  every view using it turns into a 500.

Rendering the templates would not catch the first case, because the text
outside a block in an extending template is discarded. Lexing does.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.template.base import Lexer, TokenType
from django.template.loader import get_template

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"


def _template_paths():
    return sorted(TEMPLATE_ROOT.rglob("*.html"))


def test_there_are_templates_to_check():
    """Guard against the glob silently finding nothing."""
    assert len(_template_paths()) > 20


@pytest.mark.parametrize(
    "path", _template_paths(), ids=lambda p: str(p.relative_to(TEMPLATE_ROOT))
)
def test_no_unterminated_comment_leaks_into_the_output(path):
    tokens = Lexer(path.read_text()).tokenize()

    leaked = [
        token
        for token in tokens
        if token.token_type is TokenType.TEXT and "{#" in token.contents
    ]

    assert not leaked, (
        f"{path.name} has a `{{# ... #}}` comment spanning more than one line, "
        f"so it renders as visible text. Use {{% comment %}} instead. "
        f"First offender: {leaked[0].contents.strip()[:90]!r}"
    )


@pytest.mark.parametrize(
    "path", _template_paths(), ids=lambda p: str(p.relative_to(TEMPLATE_ROOT))
)
def test_every_template_compiles(path):
    """Catches a tag that was only ever meant as prose.

    Compiling is not rendering. This proves that each file's own tags parse;
    it does not follow `{% extends %}` when the parent is a variable, as in
    `observations/detail.html`, and a template that compiles can still fail
    on a missing context variable at render time. What it does catch is the
    failure that hits every user of the template, always — which is the one
    the prose-mistaken-for-a-tag bug produced.
    """
    get_template(str(path.relative_to(TEMPLATE_ROOT)))
