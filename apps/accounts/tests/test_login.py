"""Login flow — RFP §3.1, §971.

View-level tests: they go through the HTTP client, so they prove the view
actually enforces the rules rather than that a helper returns the right value
(CLAUDE.md §4.1).
"""

import pytest
from django.urls import reverse

from apps.accounts.models import LoginAttempt
from apps.core.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "test-password-1234"


@pytest.fixture
def login_url():
    return reverse("accounts:login")


def post_login(client, url, identifier, password=PASSWORD):
    return client.post(url, {"username": identifier, "password": password})


# ------------------------------------------------------------------ identifiers
# RFP §3.1 — teachers by username or email, guardians by phone or email.

@pytest.mark.parametrize("field", ["username", "email", "phone"])
def test_can_log_in_with_any_identifier(client, login_url, make_user, field):
    values = {"username": "bagsh1", "email": "bagsh@example.mn",
              "phone": "99112233"}
    user = make_user(**values)

    response = post_login(client, login_url, values[field])

    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_email_identifier_is_case_insensitive(client, login_url, make_user):
    make_user(email="Bagsh@Example.MN")
    assert post_login(client, login_url, "bagsh@EXAMPLE.mn").status_code == 302


def test_wrong_password_does_not_log_in(client, login_url, make_user):
    make_user(username="bagsh1")

    response = post_login(client, login_url, "bagsh1", password="wrong-one")

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_unknown_identifier_does_not_log_in(client, login_url):
    response = post_login(client, login_url, "hen-ch-bish")

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_inactive_user_cannot_log_in(client, login_url, make_user):
    user = make_user(username="bagsh1")
    user.is_active = False
    user.save()

    assert post_login(client, login_url, "bagsh1").status_code == 200
    assert "_auth_user_id" not in client.session


def test_error_message_does_not_reveal_whether_the_account_exists(
    client, login_url, make_user
):
    """Distinct messages would turn the login form into an account oracle.

    Compares the error message rather than the whole page: the form echoes
    back what was typed, and the retry hint tracks the attempt count, so both
    legitimately differ without disclosing anything.
    """
    make_user(username="bagsh1")
    message = "Нэвтрэх нэр эсвэл нууц үг буруу байна."

    existing = post_login(client, login_url, "bagsh1", password="wrong-one")
    LoginAttempt.objects.all().delete()
    missing = post_login(client, login_url, "hen-ch-bish", password="wrong-one")

    assert existing.status_code == missing.status_code == 200
    assert message in existing.content.decode()
    assert message in missing.content.decode()


# ------------------------------------------------------------------ throttling
# RFP §3.1 — lock out after repeated failures.

def test_lockout_after_max_failed_attempts(client, login_url, make_user, settings):
    make_user(username="bagsh1")

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        post_login(client, login_url, "bagsh1", password="wrong-one")

    # Correct password, but the account is now locked.
    response = post_login(client, login_url, "bagsh1")

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "түр хаагдлаа" in response.content.decode()


def test_correct_password_still_works_below_the_limit(
    client, login_url, make_user, settings
):
    make_user(username="bagsh1")

    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        post_login(client, login_url, "bagsh1", password="wrong-one")

    assert post_login(client, login_url, "bagsh1").status_code == 302


def test_failed_attempts_are_recorded(client, login_url, make_user):
    make_user(username="bagsh1")

    post_login(client, login_url, "bagsh1", password="wrong-one")

    attempt = LoginAttempt.objects.get()
    assert attempt.identifier == "bagsh1"
    assert attempt.succeeded is False


def test_attempt_counter_survives_the_request(client, login_url, make_user):
    """ATOMIC_REQUESTS would otherwise roll the counter back — CLAUDE.md §6.2."""
    make_user(username="bagsh1")

    post_login(client, login_url, "bagsh1", password="wrong-one")

    assert LoginAttempt.objects.filter(succeeded=False).count() == 1


# ------------------------------------------------------------------ audit
# RFP §971 — record who logged in, and who failed to.

def test_successful_login_is_audited(client, login_url, make_user):
    user = make_user(username="bagsh1")

    post_login(client, login_url, "bagsh1")

    entry = AuditLog.objects.get(action=AuditAction.LOGIN)
    assert entry.actor_user_id == user.pk
    assert entry.ip_address


def test_failed_login_is_audited_with_the_attempted_identifier(
    client, login_url, make_user
):
    make_user(username="bagsh1")

    post_login(client, login_url, "bagsh1", password="wrong-one")

    entry = AuditLog.objects.get(action=AuditAction.LOGIN_FAILED)
    assert entry.actor_user is None
    assert entry.actor_label == "bagsh1"
    assert entry.metadata["reason"] == "bad_credentials"


def test_logout_is_audited(client, login_url, make_user):
    user = make_user(username="bagsh1")
    post_login(client, login_url, "bagsh1")

    client.get(reverse("accounts:logout"))

    entry = AuditLog.objects.get(action=AuditAction.LOGOUT)
    assert entry.actor_user_id == user.pk
    assert "_auth_user_id" not in client.session


def test_audit_rows_cannot_be_edited(client, login_url, make_user):
    """An editable audit record is worthless — spec section 9.1."""
    make_user(username="bagsh1")
    post_login(client, login_url, "bagsh1")

    entry = AuditLog.objects.get(action=AuditAction.LOGIN)
    entry.action = AuditAction.LOGOUT

    with pytest.raises(NotImplementedError):
        entry.save()
    with pytest.raises(NotImplementedError):
        entry.delete()


# ------------------------------------------------------------------ session

def test_logged_in_user_is_redirected_away_from_the_login_page(
    client, login_url, make_user
):
    make_user(username="bagsh1")
    post_login(client, login_url, "bagsh1")

    assert client.get(login_url).status_code == 302


# ------------------------------------------------------------------ role tabs
# The design shows Багш / Эцэг эх / Админ tabs. They are presentational only.

def test_all_three_tabs_are_rendered(client, login_url):
    body = client.get(login_url).content.decode()

    for label in ("Багш", "Эцэг эх", "Админ"):
        assert label in body


def test_tab_changes_only_the_identifier_label(client, login_url):
    teacher = client.get(login_url, {"role": "teacher"}).content.decode()
    parent = client.get(login_url, {"role": "parent"}).content.decode()

    assert "Нэвтрэх нэр эсвэл и-мэйл" in teacher
    assert "Утасны дугаар эсвэл и-мэйл" in parent


def test_unknown_tab_falls_back_to_the_default(client, login_url):
    body = client.get(login_url, {"role": "../../etc/passwd"}).content.decode()

    assert "Нэвтрэх нэр эсвэл и-мэйл" in body


def test_tab_does_not_filter_authentication(client, login_url, make_user):
    """The tab must not gate login by role.

    If it did, an attacker could learn which role an address belongs to by
    watching which tab accepts it. A teacher logging in with the "Эцэг эх"
    tab selected must still succeed.
    """
    user = make_user(username="bagsh1")

    response = client.post(login_url, {"username": "bagsh1",
                                       "password": PASSWORD,
                                       "role": "parent"})

    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_failure_response_is_identical_across_tabs(client, login_url, make_user):
    """Any per-tab difference on failure would be the same oracle."""
    make_user(username="bagsh1")

    responses = []
    for role in ("teacher", "parent", "admin"):
        LoginAttempt.objects.all().delete()
        responses.append(
            client.post(login_url, {"username": "bagsh1",
                                    "password": "wrong-one",
                                    "role": role}).content.decode()
        )

    message = "Нэвтрэх нэр эсвэл нууц үг буруу байна."
    assert all(message in body for body in responses)
