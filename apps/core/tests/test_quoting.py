"""The `unquoted` filter — RFP §5.1.

The report template wraps "хүүхдийн хэлсэн үг" in guillemets. A teacher
typing that field cannot know it will be quoted for them, so some of them
quote it themselves. The seeded demo data does exactly that, and the printed
portfolio read `««Би чадаж байна!»»` until someone rendered a page and
looked at it.
"""

import pytest

from apps.core.templatetags.quoting import unquoted


@pytest.mark.parametrize("raw, expected", [
    ("«Би чадаж байна!»", "Би чадаж байна!"),
    ('"Би чадаж байна!"', "Би чадаж байна!"),
    ("“Би чадаж байна!”", "Би чадаж байна!"),
    ("„Би чадаж байна!“", "Би чадаж байна!"),
    ("'Болно'", "Болно"),
    # Not quoted at all — the common case, and it must not be touched.
    ("Би чадаж байна!", "Би чадаж байна!"),
    # Whitespace first, so a trailing newline does not hide the closing mark.
    ("  «Би чадаж байна!»\n", "Би чадаж байна!"),
    # Doubled by hand.
    ("««Би чадаж байна!»»", "Би чадаж байна!"),
])
def test_a_surrounding_quote_is_removed(raw, expected):
    assert unquoted(raw) == expected


@pytest.mark.parametrize("raw", [
    # Quotation inside the sentence is the author's and stays.
    'Тэр "болно" гэсэн',
    "Ээж «за» гэлээ, би баярласан",
    # An opening mark with no closing one is not a wrapper.
    "«Би чадаж байна",
    "Би чадаж байна»",
])
def test_inner_and_unpaired_marks_survive(raw):
    assert unquoted(raw) == raw


def test_a_string_of_only_quotes_is_left_alone():
    """Stripping to nothing would turn «» into an empty quotation."""
    assert unquoted("«»") == "«»"
    assert unquoted('""') == '""'


def test_none_and_empty_are_safe():
    assert unquoted(None) == ""
    assert unquoted("") == ""
