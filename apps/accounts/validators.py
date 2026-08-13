"""Password rules taken from the approved design.

`docs/design/screens/auth-login-and-password-reset.jpeg` states them on screen,
so RFP §21.15 makes them part of what the build is measured against:

    8+ тэмдэгт · Том үсэг · Жижиг үсэг · Тоо

Django's own validators cover length and a few weak-password heuristics but
not the character-class mix, hence this one.

Messages are user-facing and therefore in Mongolian — RFP §611.
"""

import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """Requires an upper-case letter, a lower-case letter and a digit."""

    def validate(self, password, user=None):
        problems = []

        if not re.search(r"[A-ZА-ЯЁӨҮ]", password):
            problems.append("том үсэг")
        if not re.search(r"[a-zа-яёөү]", password):
            problems.append("жижиг үсэг")
        if not re.search(r"\d", password):
            problems.append("тоо")

        if problems:
            raise ValidationError(
                "Нууц үгэнд %(missing)s орсон байх шаардлагатай.",
                code="password_missing_character_classes",
                params={"missing": ", ".join(problems)},
            )

    def get_help_text(self):
        return "Нууц үг том үсэг, жижиг үсэг болон тоо агуулсан байх ёстой."
