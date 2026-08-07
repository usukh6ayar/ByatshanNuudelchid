"""Authentication services — RFP §3.1, §15.

All logic lives here; views only parse the request and render (CLAUDE.md §2.1).
"""

import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditAction
from apps.core.services import audit, client_ip

from .models import LoginAttempt, PasswordResetToken, User

TOKEN_TTL_HOURS = 2


# ---------------------------------------------------------------- throttling

def lockout_window_start():
    return timezone.now() - timezone.timedelta(
        minutes=settings.LOGIN_LOCKOUT_MINUTES
    )


def failed_attempt_count(identifier: str, ip: str | None = None) -> int:
    """Recent failures for this identifier, or from this IP.

    Counting both blocks two different attacks: repeated guesses against one
    account, and one guess each against many accounts from one source.
    """
    since = lockout_window_start()
    by_identifier = LoginAttempt.objects.filter(
        identifier__iexact=identifier, succeeded=False, created_at__gte=since
    ).count()

    if not ip:
        return by_identifier

    by_ip = LoginAttempt.objects.filter(
        ip_address=ip, succeeded=False, created_at__gte=since
    ).count()
    return max(by_identifier, by_ip)


def is_locked_out(identifier: str, ip: str | None = None) -> bool:
    return failed_attempt_count(identifier, ip) >= settings.LOGIN_MAX_ATTEMPTS


def record_attempt(*, identifier: str, ip: str | None, succeeded: bool):
    return LoginAttempt.objects.create(
        identifier=identifier[:254], ip_address=ip, succeeded=succeeded
    )


# ---------------------------------------------------------------- login

class LoginResult:
    __slots__ = ("user", "locked_out", "retries_left")

    def __init__(self, user=None, locked_out=False, retries_left=0):
        self.user = user
        self.locked_out = locked_out
        self.retries_left = retries_left

    @property
    def ok(self) -> bool:
        return self.user is not None


def attempt_login(*, request, identifier: str, password: str) -> LoginResult:
    """Authenticate, throttle and audit — RFP §3.1, §971.

    Runs outside the request transaction (the view is decorated with
    ``non_atomic_requests``) so the attempt counter survives a later failure.
    """
    identifier = (identifier or "").strip()
    ip = client_ip(request)

    if is_locked_out(identifier, ip):
        audit(action=AuditAction.LOGIN_FAILED, request=request,
              identifier=identifier, reason="locked_out")
        return LoginResult(locked_out=True)

    user = authenticate(request, username=identifier, password=password)

    if user is None:
        record_attempt(identifier=identifier, ip=ip, succeeded=False)
        audit(action=AuditAction.LOGIN_FAILED, request=request,
              identifier=identifier, reason="bad_credentials")
        remaining = settings.LOGIN_MAX_ATTEMPTS - failed_attempt_count(identifier, ip)
        return LoginResult(retries_left=max(remaining, 0))

    record_attempt(identifier=identifier, ip=ip, succeeded=True)
    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at"])
    audit(action=AuditAction.LOGIN, request=request, actor=user)
    return LoginResult(user=user)


def record_logout(*, request, user):
    audit(action=AuditAction.LOGOUT, request=request, actor=user)


# ---------------------------------------------------------------- password reset

def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@transaction.atomic
def request_password_reset(*, request, identifier: str) -> str | None:
    """Issue a reset token. Returns the raw token, or None if no such user.

    The caller must not reveal which happened: RFP §15's spirit is that the
    login surface should not confirm whether an account exists.

    Guardians who signed up with only a phone number have no email to send to.
    SMS delivery is phase §20-IV; until then the admin resets their password
    (RFP §2.1 "reset a password when necessary").
    """
    identifier = (identifier or "").strip()
    user = User.objects.filter(email__iexact=identifier).first()
    if user is None or not user.is_active:
        return None

    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(
        used_at=timezone.now()
    )

    raw = secrets.token_urlsafe(48)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=_hash(raw),
        expires_at=timezone.now() + timezone.timedelta(hours=TOKEN_TTL_HOURS),
        requested_ip=client_ip(request),
    )
    return raw


def resolve_reset_token(raw: str) -> PasswordResetToken | None:
    token = PasswordResetToken.objects.filter(token_hash=_hash(raw or "")).first()
    return token if token and token.is_usable else None


@transaction.atomic
def complete_password_reset(*, request, raw_token: str, new_password: str) -> bool:
    token = resolve_reset_token(raw_token)
    if token is None:
        return False

    token.user.set_password(new_password)
    token.user.save(update_fields=["password"])

    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])

    # Clearing the failure history is deliberate: whoever completed the reset
    # proved control of the mailbox, so the §3.1 lockout should not persist.
    LoginAttempt.objects.filter(
        identifier__iexact=token.user.email or "", succeeded=False
    ).delete()

    audit(action=AuditAction.PASSWORD_RESET, request=request, actor=token.user)
    return True
