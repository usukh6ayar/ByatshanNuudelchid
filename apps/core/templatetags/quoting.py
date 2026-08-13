"""Quote handling for text the template wraps in «» itself.

RFP §5.1 asks a teacher to record "хүүхдийн хэлсэн үг". The report template
presents that as a quotation, so it supplies the guillemets — but the teacher
typing the field has no way to know that, and a fair number of people quote
what a child said the way they would in a sentence. The result is `««Би чадаж
байна!»»`, which is what the seeded portfolio actually printed.

Stripping in the template rather than on save is deliberate: the field holds
what the teacher typed, and a service that quietly edited their punctuation
would be lying about its own contents. Presentation is where presentation
gets decided.
"""

from django import template

register = template.Library()

# Guillemets, curly and straight quotes, in both directions. A teacher may
# type any of these depending on their keyboard layout.
_QUOTES = "«»“”„‟\"'‘’"


@register.filter
def unquoted(value) -> str:
    """Strip one layer of surrounding quote marks, if there is one.

    Only touches the ends, so quotation inside the sentence survives:
    ``«Тэр "болно" гэсэн»`` keeps its inner marks. Whitespace is stripped
    first, so a trailing newline does not hide the closing mark.
    """
    if value is None:
        return ""

    text = str(value).strip()
    while len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES:
        stripped = text[1:-1].strip()
        if not stripped:
            break
        text = stripped
    return text
