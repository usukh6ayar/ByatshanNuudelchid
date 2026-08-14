"""Authentication services — RFP §3.1, §15.

All logic lives here; views only parse the request and render (CLAUDE.md §2.1).
"""

import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditAction
from apps.core.services import audit, client_ip

from .models import (
    Invitation,
    LoginAttempt,
    Membership,
    PasswordResetToken,
    Role,
    TeacherProfile,
    User,
)

TOKEN_TTL_HOURS = 2

# Longer than a password reset on purpose: a guardian may not visit the
# kindergarten for a week or more after their child is registered.
INVITATION_TTL_DAYS = 14


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


# ---------------------------------------------------------------- own profile

# Everything a person may change about themselves. Written as an allow-list
# rather than an exclude-list because the failure modes are not symmetric:
# forgetting to add a field here means someone cannot edit their bio, while
# forgetting to exclude one on a model that grows a field later could mean
# `is_active`, `is_superuser` or `password` are writable from a form the user
# controls entirely. §2.1 puts roles and account state with the administrator.
EDITABLE_USER_FIELDS = frozenset({"last_name", "first_name", "email", "phone"})
EDITABLE_TEACHER_FIELDS = frozenset(
    {"specialization", "years_of_service", "education", "bio"}
)


@transaction.atomic
def update_own_profile(*, user, request=None, **fields):
    """RFP §3.3 — a teacher maintains their own professional details.

    The actor and the subject are the same person by construction: there is
    no ``actor``/``user`` pair to get the wrong way round, and no id comes
    from the request. A caller that wants to edit somebody else is using the
    wrong function.

    The ``TeacherProfile`` row is created on first save. Accounts are made by
    invitation (``invite_teacher``), which deliberately writes no profile —
    an empty row for every invited teacher would say "this person filled
    nothing in", which is not the same as "this person has not been here yet".

    Teacher fields are ignored for anyone who is not a teacher, rather than
    refused: the form does not offer them, so a guardian posting them is
    either noise or an attempt, and neither deserves a row.
    """
    unknown = set(fields) - EDITABLE_USER_FIELDS - EDITABLE_TEACHER_FIELDS
    if unknown:
        raise ValidationError(
            f"Засах боломжгүй талбар: {', '.join(sorted(unknown))}"
        )

    for name in EDITABLE_USER_FIELDS & set(fields):
        value = fields[name]
        if name in ("email", "phone"):
            # unique=True with null=True: two users may both have no email,
            # but not both have "". Empty means absent, and absent is NULL.
            value = (value or "").strip() or None
        setattr(user, name, value)

    user.full_clean(
        exclude=[f.name for f in user._meta.fields
                 if f.name not in EDITABLE_USER_FIELDS]
    )
    user.save(update_fields=sorted(EDITABLE_USER_FIELDS))

    profile = None
    teacher_fields = EDITABLE_TEACHER_FIELDS & set(fields)
    if teacher_fields and _is_teacher(user):
        profile, _ = TeacherProfile.objects.get_or_create(user=user)
        for name in teacher_fields:
            setattr(profile, name, fields[name])
        profile.full_clean(
            exclude=[f.name for f in profile._meta.fields
                     if f.name not in EDITABLE_TEACHER_FIELDS]
        )
        profile.save()

    audit(action=AuditAction.UPDATE, request=request, actor=user, obj=user)
    return user, profile


def _is_teacher(user) -> bool:
    return user.memberships.filter(is_active=True, role=Role.TEACHER).exists()


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


# ---------------------------------------------------------------- invitations
# RFP §2.1, §3.5. Nobody self-registers: staff create the account, the person
# activates it and chooses their own password, so staff never learn it.


def _six_digit_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@transaction.atomic
def create_invitation(*, actor, user, kindergarten=None,
                      delivery=Invitation.Delivery.BOTH,
                      request=None) -> tuple[str, str]:
    """Issue an invitation. Returns ``(raw_token, raw_code)``.

    Only the hashes are stored, so a re-send is a new invitation rather than
    a lookup — the previous one is spent immediately.
    """
    Invitation.objects.filter(user=user, used_at__isnull=True).update(
        used_at=timezone.now()
    )

    raw_token = secrets.token_urlsafe(48)
    raw_code = _six_digit_code()

    invitation = Invitation.objects.create(
        user=user,
        kindergarten=kindergarten,
        token_hash=_hash(raw_token),
        code_hash=_hash(raw_code),
        delivery=delivery,
        expires_at=timezone.now() + timezone.timedelta(days=INVITATION_TTL_DAYS),
        created_by=actor,
    )
    audit(action=AuditAction.INVITE, request=request, actor=actor,
          kindergarten=kindergarten, obj=invitation, invited=str(user))
    return raw_token, raw_code


def resolve_invitation_token(raw: str) -> Invitation | None:
    invitation = Invitation.objects.filter(token_hash=_hash(raw or "")).first()
    return invitation if invitation and invitation.is_usable else None


def resolve_invitation_code(identifier: str, raw_code: str) -> Invitation | None:
    """Paper path: the code is only valid together with the identifier.

    Six digits is a million combinations — searchable on its own. Requiring
    the phone number or email as well means an attacker has to know both,
    and :func:`is_locked_out` still applies on top.
    """
    identifier = (identifier or "").strip()
    if not identifier or not raw_code:
        return None

    from django.db.models import Q

    user = User.objects.filter(
        Q(username__iexact=identifier)
        | Q(email__iexact=identifier)
        | Q(phone=identifier)
    ).first()
    if user is None:
        return None

    invitation = Invitation.objects.filter(
        user=user, code_hash=_hash(raw_code)
    ).first()
    return invitation if invitation and invitation.is_usable else None


@transaction.atomic
def activate_invitation(*, request, invitation: Invitation, password: str) -> User:
    """Set the password and spend the invitation."""
    user = invitation.user
    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    invitation.used_at = timezone.now()
    invitation.save(update_fields=["used_at"])

    audit(action=AuditAction.ACTIVATE, request=request, actor=user,
          kindergarten=invitation.kindergarten, obj=invitation)
    return user


# ---------------------------------------------------------------- onboarding


@transaction.atomic
def invite_teacher(*, actor, kindergarten, last_name, first_name,
                   username=None, email=None, phone=None,
                   request=None) -> tuple[User, str, str]:
    """RFP §2.1 — the administrator creates the teacher account."""
    user = User.objects.create_user(
        password=None,          # unusable until the invitation is activated
        username=username or None,
        email=email or None,
        phone=phone or None,
        last_name=last_name,
        first_name=first_name,
    )
    membership = Membership.objects.create(
        user=user, kindergarten=kindergarten, role=Role.TEACHER,
        created_by=actor, updated_by=actor,
    )
    audit(action=AuditAction.CREATE, request=request, actor=actor,
          kindergarten=kindergarten, obj=membership)

    token, code = create_invitation(
        actor=actor, user=user, kindergarten=kindergarten, request=request
    )
    return user, token, code


@transaction.atomic
def register_guardian(*, actor, child, last_name, first_name, relation,
                      email=None, phone=None, is_primary=False,
                      request=None) -> tuple[object, str | None, str | None]:
    """RFP §3.4, §3.5 — the teacher attaches a guardian to a child.

    The ``Guardianship`` row is the §21.3 authorization boundary, so it is
    created here by staff who know the family, never by the guardian.

    An existing account is reused when the phone or email already matches —
    the second-child case. That person already has a password, so no new
    invitation is issued and the returned token and code are ``None``.
    """
    from django.db.models import Q

    from apps.children.models import Guardianship

    user = None
    if email or phone:
        lookup = Q()
        if email:
            lookup |= Q(email__iexact=email)
        if phone:
            lookup |= Q(phone=phone)
        user = User.objects.filter(lookup).first()

    is_new = user is None
    if is_new:
        user = User.objects.create_user(
            password=None,
            email=email or None,
            phone=phone or None,
            last_name=last_name,
            first_name=first_name,
        )

    Membership.objects.get_or_create(
        user=user, kindergarten=child.kindergarten, role=Role.GUARDIAN,
        defaults={"created_by": actor, "updated_by": actor},
    )

    guardianship, _ = Guardianship.objects.get_or_create(
        child=child, guardian_user=user,
        defaults={
            "kindergarten": child.kindergarten,
            "relation": relation,
            "is_primary": is_primary,
            "created_by": actor,
            "updated_by": actor,
        },
    )
    audit(action=AuditAction.CREATE, request=request, actor=actor,
          kindergarten=child.kindergarten, child=child, obj=guardianship)

    if not is_new:
        return guardianship, None, None

    token, code = create_invitation(
        actor=actor, user=user, kindergarten=child.kindergarten, request=request
    )
    return guardianship, token, code


@transaction.atomic
def save_membership_state(*, actor, membership, request=None) -> Membership:
    """Activate or end a posting — RFP §3.3's "ажиллаж байгаа эсэх".

    Ends the posting rather than deleting it: the observations that teacher
    wrote stay attributed to them, and their access follows the membership,
    so switching this off is what actually revokes it. CLAUDE.md §3.3
    forbids the hard delete in any case.
    """
    membership.updated_by = actor
    membership.save(update_fields=["is_active", "updated_by", "updated_at"])
    audit(
        action=AuditAction.PERMISSION_CHANGE, request=request, actor=actor,
        kindergarten=membership.kindergarten, obj=membership,
    )
    return membership
