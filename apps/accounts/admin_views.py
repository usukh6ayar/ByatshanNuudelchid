"""Administrator screens for staff and accounts — RFP §2.1, §3.3.

Kept apart from ``views.py``, which is authentication: logging in, resetting
a password, activating an invitation. Those are the screens an anonymous
visitor reaches; these are the ones only a director does. Mixing them in one
module is how a ``@login_required`` ends up on the wrong one.

Replaces the Django admin's user and membership changelists.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core.layouts import ADMIN
from apps.tenants.selectors import administered_kindergartens

from . import selectors, services
from .models import Membership, Role

PAGE_SIZE = 20


def _admin_only(user):
    """RFP §2.1. 404 rather than 403 — CLAUDE.md §1.1."""
    if user is None or not user.is_authenticated or not user.is_active:
        raise Http404
    if not user.memberships.filter(
        is_active=True, role__in=[Role.ADMIN, Role.SUPERADMIN]
    ).exists():
        raise Http404


def _page(request, rows):
    return Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))


@login_required
def staff_list(request):
    """RFP §3.3 — the teachers a director manages."""
    _admin_only(request.user)

    kindergartens = list(administered_kindergartens(request.user))
    chosen = next(
        (k for k in kindergartens
         if str(k.pk) == request.GET.get("kindergarten")), None
    )
    filters = {
        "q": request.GET.get("q", "").strip(),
        "kindergarten": chosen,
        "role": request.GET.get("role", ""),
        "active": request.GET.get("active", ""),
    }
    rows = selectors.staff_rows(request.user, **filters)

    return render(request, "accounts/staff_list.html", {
        "base_template": ADMIN,
        "nav": "staff",
        "page": _page(request, rows),
        "kindergartens": kindergartens,
        "filters": filters,
        "roles": [(Role.TEACHER, "Багш"), (Role.ADMIN, "Администратор")],
        "total": rows.count(),
    })


@login_required
def staff_invite(request):
    """RFP §2.1 — "Багшийн бүртгэл үүсгэх".

    The account is created without a usable password and an invitation is
    issued; the teacher sets their own on activation. A director typing a
    colleague's password for them is the habit that ends with one password
    shared by a staff room.
    """
    _admin_only(request.user)

    kindergartens = list(administered_kindergartens(request.user))
    context = {
        "base_template": ADMIN,
        "nav": "staff",
        "kindergartens": kindergartens,
        "form": {},
    }

    if request.method == "POST":
        context["form"] = request.POST
        kindergarten = next(
            (k for k in kindergartens
             if str(k.pk) == request.POST.get("kindergarten")), None
        )
        if kindergarten is None:
            context["error"] = "Цэцэрлэгээ сонгоно уу."
            return render(request, "accounts/staff_form.html", context)

        last_name = request.POST.get("last_name", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        if not first_name:
            context["error"] = "Багшийн нэрийг оруулна уу."
            return render(request, "accounts/staff_form.html", context)

        try:
            user, token, code = services.invite_teacher(
                actor=request.user,
                kindergarten=kindergarten,
                last_name=last_name,
                first_name=first_name,
                username=request.POST.get("username", "").strip() or None,
                email=request.POST.get("email", "").strip() or None,
                phone=request.POST.get("phone", "").strip() or None,
                request=request,
            )
        except (PermissionDenied, ValidationError) as exc:
            context["error"] = _message(exc)
            return render(request, "accounts/staff_form.html", context)

        # Shown once, on the next screen. The code is how the teacher
        # activates the account, and there is no second chance to read it —
        # only its hash is stored (§3.1).
        context |= {"created": user, "code": code, "token": token}
        return render(request, "accounts/staff_invited.html", context)

    return render(request, "accounts/staff_form.html", context)


@login_required
def user_list(request):
    """RFP §2.1 — "Системийн нийт хэрэглэгчийг удирдах"."""
    _admin_only(request.user)

    filters = {
        "q": request.GET.get("q", "").strip(),
        "role": request.GET.get("role", ""),
        "active": request.GET.get("active", ""),
    }
    rows = selectors.user_rows(request.user, **filters)

    return render(request, "accounts/user_list.html", {
        "base_template": ADMIN,
        "nav": "users",
        "page": _page(request, rows),
        "filters": filters,
        "roles": Role.choices,
        "total": rows.count(),
    })


@login_required
def membership_toggle(request, membership_id):
    """Deactivate or restore a posting — RFP §3.3's "ажиллаж байгаа эсэх".

    A membership is ended rather than deleted: the observations that teacher
    wrote stay attributed, and CLAUDE.md §3.3 forbids the hard delete anyway.
    """
    _admin_only(request.user)

    if request.method != "POST":
        raise Http404

    membership = Membership.objects.filter(
        pk=membership_id,
        kindergarten__in=administered_kindergartens(request.user),
    ).select_related("user").first()
    if membership is None:
        raise Http404

    # A director removing their own last posting would lock themselves out
    # of the screen they are standing on.
    if membership.user_id == request.user.pk:
        messages.error(request, "Өөрийн эрхийг өөрчлөх боломжгүй.")
        return redirect("accounts:staff_list")

    membership.is_active = not membership.is_active
    services.save_membership_state(actor=request.user, membership=membership,
                                   request=request)

    messages.success(
        request,
        "Багш идэвхжлээ." if membership.is_active else "Багш идэвхгүй боллоо."
    )
    return redirect("accounts:staff_list")


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
