"""Password reset — RFP §3.1, §15."""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PasswordResetToken
from apps.accounts.services import _hash, request_password_reset
from apps.core.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db(transaction=True)

# Satisfies the design's rules: 8+ characters, upper case, lower case, digit.
NEW_PASSWORD = "ShineNuuts99"


@pytest.fixture
def user_with_email(make_user):
    return make_user(username="bagsh1", email="bagsh@example.mn")


@pytest.fixture
def raw_token(rf, user_with_email):
    return request_password_reset(
        request=rf.post("/"), identifier=user_with_email.email
    )


def confirm_url(token):
    return reverse("accounts:password_reset_confirm", args=[token])


# ------------------------------------------------------------------ requesting

def test_request_creates_a_token(client, user_with_email):
    client.post(reverse("accounts:password_reset"),
                {"email": user_with_email.email})

    assert PasswordResetToken.objects.filter(user=user_with_email).count() == 1


def test_only_the_hash_is_stored(rf, user_with_email):
    """A leaked database must not yield working reset links."""
    raw = request_password_reset(request=rf.post("/"),
                                 identifier=user_with_email.email)

    token = PasswordResetToken.objects.get()
    assert token.token_hash != raw
    assert token.token_hash == _hash(raw)


def test_response_is_identical_for_unknown_addresses(client, user_with_email):
    """Otherwise the form confirms which addresses are registered."""
    url = reverse("accounts:password_reset")

    known = client.post(url, {"email": user_with_email.email})
    unknown = client.post(url, {"email": "hen-ch-bish@example.mn"})

    assert known.status_code == unknown.status_code == 200
    assert known.content == unknown.content


def test_requesting_again_invalidates_the_previous_token(rf, user_with_email):
    first = request_password_reset(request=rf.post("/"),
                                   identifier=user_with_email.email)
    request_password_reset(request=rf.post("/"),
                           identifier=user_with_email.email)

    assert PasswordResetToken.objects.get(token_hash=_hash(first)).used_at


# ------------------------------------------------------------------ completing

def test_valid_token_resets_the_password(client, user_with_email, raw_token):
    response = client.post(confirm_url(raw_token),
                           {"password": NEW_PASSWORD,
                            "password_confirm": NEW_PASSWORD})

    assert response.status_code == 302
    user_with_email.refresh_from_db()
    assert user_with_email.check_password(NEW_PASSWORD)


def test_new_password_works_for_login(client, user_with_email, raw_token):
    client.post(confirm_url(raw_token),
                {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})

    response = client.post(reverse("accounts:login"),
                           {"username": "bagsh1", "password": NEW_PASSWORD})

    assert response.status_code == 302


def test_token_cannot_be_reused(client, user_with_email, raw_token):
    url = confirm_url(raw_token)
    client.post(url, {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})

    assert client.get(url).status_code == 400


def test_expired_token_is_rejected(client, user_with_email, raw_token):
    PasswordResetToken.objects.update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    assert client.get(confirm_url(raw_token)).status_code == 400


def test_unknown_token_is_rejected(client):
    assert client.get(confirm_url("not-a-real-token")).status_code == 400


def test_mismatched_passwords_are_rejected(client, user_with_email, raw_token):
    response = client.post(confirm_url(raw_token),
                           {"password": NEW_PASSWORD,
                            "password_confirm": "something-else-entirely"})

    assert response.status_code == 200
    user_with_email.refresh_from_db()
    assert not user_with_email.check_password(NEW_PASSWORD)


def test_weak_password_is_rejected(client, user_with_email, raw_token):
    """AUTH_PASSWORD_VALIDATORS requires at least 10 characters."""
    response = client.post(confirm_url(raw_token),
                           {"password": "123", "password_confirm": "123"})

    assert response.status_code == 200
    user_with_email.refresh_from_db()
    assert not user_with_email.check_password("123")


def test_reset_clears_the_lockout(client, user_with_email, raw_token, settings):
    """Whoever completed the reset proved control of the mailbox."""
    login_url = reverse("accounts:login")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        client.post(login_url, {"username": user_with_email.email,
                                "password": "wrong-one"})

    client.post(confirm_url(raw_token),
                {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})

    response = client.post(login_url, {"username": user_with_email.email,
                                       "password": NEW_PASSWORD})
    assert response.status_code == 302


def test_reset_is_audited(client, user_with_email, raw_token):
    client.post(confirm_url(raw_token),
                {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})

    entry = AuditLog.objects.get(action=AuditAction.PASSWORD_RESET)
    assert entry.actor_user_id == user_with_email.pk
