"""Authentication views.

Views parse the request and render; every decision lives in ``services``
(CLAUDE.md §2.1).

``non_atomic_requests`` is required here, not stylistic: ``ATOMIC_REQUESTS``
would roll the §3.1 attempt counter back together with the failed request,
and the lockout would never engage (CLAUDE.md §6.2).
"""

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.password_validation import (
    ValidationError,
    validate_password,
)
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from . import services

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
        raw = services.request_password_reset(
            request=request, identifier=request.POST.get("email", "")
        )

        if raw is not None:
            link = request.build_absolute_uri(
                reverse("accounts:password_reset_confirm", args=[raw])
            )
            # Email delivery lands with the notification work in phase 9.
            # Until then dev uses the console backend and production staff
            # reset passwords through the admin (RFP §2.1).
            print(f"[password reset] {link}")  # noqa: T201

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
