"""Password rules — taken from the approved design, so RFP §21.15 applies.

The design states on screen: 8+ characters, upper case, lower case, digit.
"""

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.services import request_password_reset

pytestmark = pytest.mark.django_db


ACCEPTED = [
    "ShineNuuts99",
    "Bagsh2026",
    "Ariunaa1x",
]

REJECTED = [
    ("Short1a", "seven characters"),
    ("shinenuuts99", "no upper case"),
    ("SHINENUUTS99", "no lower case"),
    ("ShineNuutsUg", "no digit"),
    ("12345678", "digits only"),
]


@pytest.mark.parametrize("password", ACCEPTED)
def test_valid_passwords_are_accepted(password):
    validate_password(password)   # raises on failure


@pytest.mark.parametrize(("password", "reason"), REJECTED)
def test_invalid_passwords_are_rejected(password, reason):
    with pytest.raises(ValidationError):
        validate_password(password)


def test_eight_characters_is_the_boundary():
    """The design says 8+, so 8 must pass and 7 must not."""
    validate_password("Nuuts12a")            # 8
    with pytest.raises(ValidationError):
        validate_password("Nuuts1a")         # 7


def test_reset_form_rejects_a_password_without_an_upper_case_letter(
    client, rf, make_user
):
    """The rule has to hold through the view, not only in the validator."""
    user = make_user(username="bagsh1", email="bagsh@example.mn")
    token = request_password_reset(request=rf.post("/"), identifier=user.email)

    response = client.post(
        reverse("accounts:password_reset_confirm", args=[token]),
        {"password": "shinenuuts99", "password_confirm": "shinenuuts99"},
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert not user.check_password("shinenuuts99")


def test_reset_form_states_the_rules(client, rf, make_user):
    """RFP §626 — tell the user what is expected before they guess."""
    user = make_user(username="bagsh1", email="bagsh@example.mn")
    token = request_password_reset(request=rf.post("/"), identifier=user.email)

    body = client.get(
        reverse("accounts:password_reset_confirm", args=[token])
    ).content.decode()

    assert "8-аас доошгүй тэмдэгт" in body
    assert "Том үсэг орсон байх" in body
    assert "Тоо орсон байх" in body
