"""Authentication views.

Views parse the request and render; every decision lives in ``services``
(CLAUDE.md §2.1).

``non_atomic_requests`` is required here, not stylistic: ``ATOMIC_REQUESTS``
would roll the §3.1 attempt counter back together with the failed request,
and the lockout would never engage (CLAUDE.md §6.2).
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import (
    ValidationError,
    validate_password,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from apps.core.layouts import layout_for

from . import services

logger = logging.getLogger(__name__)

# The approved design shows Багш / Эцэг эх / Админ tabs on the login screen.
#
# They are presentational only: they change which identifier the field asks
# for, nothing else. Filtering authentication by the selected tab would turn
# the form into a role oracle — an attacker could learn which role an address
# belongs to by watching which tab accepts it. The backend resolves the role
# from Membership after a successful login, as it does everywhere else.
LOGIN_TABS = {
    "teacher": ("Багш", "Нэвтрэх нэр эсвэл и-мэйл"),
    "parent": ("Эцэг эх", "Утасны дугаар эсвэл и-мэйл"),
    "admin": ("Админ", "Нэвтрэх нэр эсвэл и-мэйл"),
}
DEFAULT_LOGIN_TAB = "teacher"


def _login_tab(request) -> str:
    requested = request.POST.get("role") or request.GET.get("role")
    return requested if requested in LOGIN_TABS else DEFAULT_LOGIN_TAB


@never_cache
@csrf_protect
@transaction.non_atomic_requests
def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    tab = _login_tab(request)
    context: dict = {
        "tabs": [(key, label) for key, (label, _) in LOGIN_TABS.items()],
        "active_tab": tab,
        "identifier_label": LOGIN_TABS[tab][1],
    }

    if request.method == "POST":
        result = services.attempt_login(
            request=request,
            identifier=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )

        if result.ok:
            auth_login(request, result.user,
                       backend="apps.accounts.backends.MultiIdentifierBackend")
            return redirect(request.GET.get("next") or settings.LOGIN_REDIRECT_URL)

        if result.locked_out:
            context["error"] = (
                f"Хэт олон удаа буруу оролдсон тул түр хаагдлаа. "
                f"{settings.LOGIN_LOCKOUT_MINUTES} минутын дараа дахин оролдоно уу."
            )
        else:
            # Never say which of the two was wrong — that confirms whether
            # the account exists.
            context["error"] = "Нэвтрэх нэр эсвэл нууц үг буруу байна."
            context["retries_left"] = result.retries_left

        context["identifier"] = request.POST.get("username", "")

    return render(request, "accounts/login.html", context)


@never_cache
@transaction.non_atomic_requests
def logout_view(request):
    if request.user.is_authenticated:
        services.record_logout(request=request, user=request.user)
    auth_logout(request)
    return redirect("accounts:login")


@never_cache
@csrf_protect
def password_reset_request(request):
    """RFP §3.1.

    The response is identical whether or not the address exists.
    """
    if request.method == "POST":
        # The service issues the token *and* sends it (CLAUDE.md §2.1). The
        # link is never printed: it printed to stdout until 2026-08-17, which
        # put a working credential in the production log.
        #
        # The response is the same page whether or not the address exists,
        # and whether or not the mail server accepted it — RFP §15's spirit
        # is that this surface must not confirm an account exists. A send
        # failure is logged for an administrator instead.
        try:
            services.request_password_reset(
                request=request, identifier=request.POST.get("email", "")
            )
        except Exception:
            logger.exception("password reset request could not be delivered")

        return render(request, "accounts/password_reset_sent.html")

    return render(request, "accounts/password_reset_request.html")


@never_cache
@csrf_protect
def password_reset_confirm(request, token):
    if services.resolve_reset_token(token) is None:
        return render(request, "accounts/password_reset_invalid.html", status=400)

    context: dict = {}

    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm = request.POST.get("password_confirm", "")

        if password != confirm:
            context["error"] = "Хоёр нууц үг таарахгүй байна."
        else:
            try:
                validate_password(password)
            except ValidationError as exc:
                context["error"] = " ".join(exc.messages)
            else:
                if services.complete_password_reset(
                    request=request, raw_token=token, new_password=password
                ):
                    return redirect("accounts:password_reset_complete")
                context["error"] = "Холбоос хүчингүй болсон байна."

    return render(request, "accounts/password_reset_confirm.html", context)


def password_reset_complete(request):
    return render(request, "accounts/password_reset_complete.html")


# ---------------------------------------------------------------- activation
# RFP §2.1, §3.5. Staff create the account; the person sets their own password
# here, so staff never learn it.


def _validated_password(request, context) -> str | None:
    """Shared password checks for both activation paths."""
    password = request.POST.get("password", "")
    if password != request.POST.get("password_confirm", ""):
        context["error"] = "Хоёр нууц үг таарахгүй байна."
        return None
    try:
        validate_password(password)
    except ValidationError as exc:
        context["error"] = " ".join(exc.messages)
        return None
    return password


@never_cache
@csrf_protect
def activate_by_token(request, token):
    """Email path: a single-use link."""
    invitation = services.resolve_invitation_token(token)
    if invitation is None:
        return render(request, "accounts/activate_invalid.html", status=400)

    context: dict = {"invited_user": invitation.user}

    if request.method == "POST":
        password = _validated_password(request, context)
        if password is not None:
            services.activate_invitation(
                request=request, invitation=invitation, password=password
            )
            return redirect("accounts:activate_done")

    return render(request, "accounts/activate.html", context)


@never_cache
@csrf_protect
@transaction.non_atomic_requests
def activate_by_code(request):
    """Paper path: identifier plus the six-digit code the teacher wrote down.

    Throttled like login (RFP §3.1). Six digits alone would be searchable;
    pairing it with the identifier and counting attempts is what makes it
    safe. ``non_atomic_requests`` for the same reason as the login view —
    the counter must survive a failed request (CLAUDE.md §6.2).
    """
    context: dict = {"by_code": True}

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        code = request.POST.get("code", "").strip()
        context["identifier"] = identifier

        if services.is_locked_out(identifier, services.client_ip(request)):
            context["error"] = (
                f"Хэт олон удаа буруу оролдсон тул түр хаагдлаа. "
                f"{settings.LOGIN_LOCKOUT_MINUTES} минутын дараа оролдоно уу."
            )
            return render(request, "accounts/activate.html", context)

        invitation = services.resolve_invitation_code(identifier, code)
        if invitation is None:
            services.record_attempt(
                identifier=identifier,
                ip=services.client_ip(request),
                succeeded=False,
            )
            context["error"] = "Код буруу эсвэл хугацаа нь дууссан байна."
            return render(request, "accounts/activate.html", context)

        password = _validated_password(request, context)
        if password is not None:
            services.activate_invitation(
                request=request, invitation=invitation, password=password
            )
            return redirect("accounts:activate_done")

    return render(request, "accounts/activate.html", context)


def activate_done(request):
    return render(request, "accounts/activate_done.html")


@login_required
def profile(request):
    """RFP §3.3 — a person maintains their own details.

    No id anywhere: the subject is `request.user`, which is why this needs
    only `login_required` and none of the child-data machinery. The teacher
    fields are rendered for teachers and ignored for everyone else — the
    service decides that, not the template, since a POST body is written by
    whoever sends it.
    """
    user = request.user
    is_teacher = user.memberships.filter(
        is_active=True, role=services.Role.TEACHER
    ).exists()
    teacher_profile = getattr(user, "teacher_profile", None)

    context: dict = {
        "is_teacher": is_teacher,
        "base_template": layout_for(user),
        # Which sidebar item the shell highlights. Every other screen sets
        # this; the profile never did, so no item was marked active on it.
        "nav": "profile",
        "form": {
            "last_name": user.last_name,
            "first_name": user.first_name,
            "email": user.email or "",
            "phone": user.phone or "",
            "specialization": getattr(teacher_profile, "specialization", ""),
            "years_of_service": getattr(teacher_profile, "years_of_service", "") or "",
            "education": getattr(teacher_profile, "education", ""),
            "bio": getattr(teacher_profile, "bio", ""),
        },
    }

    if request.method == "POST":
        context["form"] = request.POST

        try:
            fields = {
                "last_name": request.POST.get("last_name", "").strip(),
                "first_name": request.POST.get("first_name", "").strip(),
                "email": request.POST.get("email", ""),
                "phone": request.POST.get("phone", ""),
            }
            if is_teacher:
                fields.update(
                    specialization=request.POST.get("specialization", "").strip(),
                    education=request.POST.get("education", "").strip(),
                    bio=request.POST.get("bio", "").strip(),
                    # Inside the try: parsing the field is as much a source of
                    # a message to the user as saving it is.
                    years_of_service=_years_or_none(
                        request.POST.get("years_of_service")
                    ),
                )

            services.update_own_profile(user=user, request=request, **fields)
        except (DjangoValidationError, ValueError) as exc:
            context["error"] = _error_message(exc)
            return render(request, "accounts/profile.html", context)

        messages.success(request, "Мэдээлэл хадгалагдлаа.")
        return redirect("accounts:profile")

    return render(request, "accounts/profile.html", context)


def _years_or_none(value):
    """An empty field means "not stated"; anything else must be a number."""
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError("Ажилласан жилийг тоогоор бичнэ үү.")
    return int(value)


def _error_message(exc) -> str:
    if isinstance(exc, DjangoValidationError):
        return " ".join(exc.messages)
    return str(exc)
