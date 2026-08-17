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


# ------------------------------------------------------- delivery (§3.1)
# Added 2026-08-17. The token machinery below was always correct; nothing
# sent it. The view printed the link to stdout, so in production the reset
# flow told the user to check their email, sent nothing, and left a working
# credential in the container log.


def test_requesting_a_reset_sends_an_email(client, mailoutbox, make_user):
    user = make_user(username="mailed", email="parent@example.mn")

    client.post(reverse("accounts:password_reset"), {"email": user.email})

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [user.email]


def test_the_email_carries_a_working_reset_link(client, mailoutbox, make_user):
    """The link in the message must be the one that actually resets.

    Extracted from the body and followed, rather than asserting the body
    merely contains a URL — a message with a stale or malformed link would
    satisfy the weaker check and help nobody.
    """
    import re

    user = make_user(username="follows", email="follow@example.mn")
    client.post(reverse("accounts:password_reset"), {"email": user.email})

    body = mailoutbox[0].body
    match = re.search(r"https?://\S+/nuuts-ug-sergeeh/[^\s]+", body)
    assert match, f"no reset link in the message body: {body!r}"

    assert client.get(match.group(0)).status_code == 200


def test_the_reset_link_is_never_printed(client, mailoutbox, make_user, capsys):
    """RFP §15 — a reset link in a log is a credential in a log."""
    user = make_user(username="quiet", email="quiet@example.mn")

    client.post(reverse("accounts:password_reset"), {"email": user.email})

    captured = capsys.readouterr()
    assert "nuuts-ug-sergeeh" not in captured.out
    assert "nuuts-ug-sergeeh" not in captured.err


def test_an_unknown_address_sends_nothing_and_says_nothing(client, mailoutbox):
    """The response must not reveal whether the account exists."""
    known = reverse("accounts:password_reset")

    response = client.post(known, {"email": "nobody@example.mn"})

    assert response.status_code == 200
    assert len(mailoutbox) == 0


class _Records(list):
    """Everything the application logged, as formatted text."""

    @property
    def text(self) -> str:
        return "\n".join(self)


@pytest.fixture
def logged():
    """Capture what the app logs, without going through pytest's streams.

    Neither `caplog`, `capsys` nor `capfd` can see these records, and each
    fails by returning an empty string — an assertion that cannot fail:

      * `caplog` attaches to the root logger, but settings.LOGGING gives
        `apps` its own handler with `propagate = False`, so nothing reaches it;
      * `capsys` patches `sys.stderr`, but the handler was built during Django
        setup and holds the stream object from before that patch;
      * `capfd` reads a per-test file descriptor, while the handler holds the
        session-wide one pytest installed at start-up.

    All three were written, run, and observed passing against `''`. Attaching
    a handler to the `apps` logger sidesteps the question entirely: it reads
    the records themselves, which is what the assertions are about.
    """
    import logging

    records = _Records()

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = Collect()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("apps")
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _break_the_mail_server(monkeypatch):
    """Make every send raise, the way an unreachable SMTP host does.

    Patched on the mail backend rather than on `send_mail` itself: the
    service imports the function inside its own body, so replacing the
    module attribute after import would miss it — and would leak into every
    later test in the session.
    """
    def explode(*args, **kwargs):
        raise OSError("smtp unreachable")

    monkeypatch.setattr(
        "django.core.mail.backends.locmem.EmailBackend.send_messages", explode
    )


def test_a_broken_mail_server_does_not_leak_or_crash(client, make_user,
                                                     monkeypatch, logged):
    """A misconfigured host must not take the screen down with it.

    What matters is that the screen stays an unusable oracle: the body is
    identical to a successful request, so watching the response cannot tell
    an attacker whether the address exists *or* whether delivery worked.

    The token row is rolled back with the failed send, and that is correct
    rather than something to work around. The raw token exists in exactly
    one place — the message — and is stored only as a hash. A token whose
    message was never delivered is unusable by everyone, an administrator
    included, so keeping it would leave a live credential nobody can reach.
    """
    user = make_user(username="broken", email="broken@example.mn")
    _break_the_mail_server(monkeypatch)

    response = client.post(reverse("accounts:password_reset"),
                           {"email": user.email})
    working = client.post(reverse("accounts:password_reset"),
                          {"email": "nobody@example.mn"})

    assert response.status_code == 200
    # No oracle: a send failure looks exactly like an address that is unknown.
    assert response.content == working.content

    # The diagnostic must name the account and nothing else. `caplog` is
    # checked alongside `capsys` because the failure path logs an exception —
    # a future `logger.exception("... %s", reset_url)` would put the
    # credential straight back into the log this fix took it out of.
    # The positive assertion comes first, and it is not decoration: "the link
    # is absent from the log" proves nothing unless the log is being read at
    # all. This pins the channel open, so the check below is able to fail.
    assert "password reset email failed" in logged.text

    # And the diagnostic carries the account, never the credential.
    assert "nuuts-ug-sergeeh" not in logged.text


def test_a_failed_send_does_not_invalidate_a_link_already_in_use(
    client, mailoutbox, make_user, monkeypatch
):
    """Requesting a second reset while SMTP is down must not strand the user.

    `request_password_reset` retires any outstanding token before issuing a
    new one. If that retirement survived a failed send, a user who already
    had a working link in their inbox would lose it and receive nothing to
    replace it — locked out by a request that was meant to help them. The
    rollback is what keeps the first link alive.
    """
    from apps.accounts import models

    user = make_user(username="second", email="second@example.mn")
    client.post(reverse("accounts:password_reset"), {"email": user.email})
    first = models.PasswordResetToken.objects.get(user=user)
    assert first.is_usable

    _break_the_mail_server(monkeypatch)
    client.post(reverse("accounts:password_reset"), {"email": user.email})

    first.refresh_from_db()
    assert first.is_usable, "the delivered link was retired for a send that failed"
