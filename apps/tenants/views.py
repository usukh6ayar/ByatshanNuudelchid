"""Administrator screens for kindergartens and groups — RFP §2.1, §3.2.

These replace the Django admin changelists a director used to land on. The
admin site is a developer's tool wearing the product's colours: its
breadcrumbs, its "Өөрчлөх X-г сонгоно уу" phrasing and its filter sidebar
belong to Django, and beside `docs/design/screens/teacher-children-list.jpeg`
they read as a different application.

Same shape as the teacher screens next door: parse the request, call a
selector to read or a service to write, render (CLAUDE.md §2.1). The scope
is `administered_kindergartens`, so a director never sees another
kindergarten's rows and a teacher never reaches these at all.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from apps.accounts.models import Role
from apps.core.layouts import ADMIN

from . import selectors, services
from .models import Group, Kindergarten, SchoolYear

PAGE_SIZE = 20


def _admin_only(user):
    """RFP §2.1 — these screens belong to a director, not to a teacher.

    A teacher reaching them gets 404 rather than 403: the rule is the same
    one CLAUDE.md §1.1 states for child data, and revealing that a screen
    exists is itself information.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        raise Http404
    if not user.memberships.filter(
        is_active=True, role__in=[Role.ADMIN, Role.SUPERADMIN]
    ).exists():
        raise Http404


def _base(nav: str) -> dict:
    return {"base_template": ADMIN, "nav": nav}


def _page(request, rows):
    return Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))


# ------------------------------------------------------------ kindergartens

@login_required
def kindergarten_list(request):
    """RFP §3.2 — the kindergartens this director administers."""
    _admin_only(request.user)

    filters = {
        "q": request.GET.get("q", "").strip(),
        "status": request.GET.get("status", ""),
    }
    rows = selectors.kindergarten_rows(request.user, **filters)

    return render(request, "tenants/kindergarten_list.html", _base("kindergartens") | {
        "page": _page(request, rows),
        "filters": filters,
        "total": rows.count(),
    })


@login_required
def kindergarten_form(request, kindergarten_id=None):
    """Create or edit — RFP §3.2's field list."""
    _admin_only(request.user)

    obj = None
    if kindergarten_id is not None:
        obj = selectors.administered_kindergartens(request.user).filter(
            pk=kindergarten_id
        ).first()
        if obj is None:
            raise Http404

    context = _base("kindergartens") | {
        "obj": obj,
        "form": {
            "name": getattr(obj, "name", ""),
            "address": getattr(obj, "address", ""),
            "phone": getattr(obj, "phone", ""),
            "email": getattr(obj, "email", ""),
            "description": getattr(obj, "description", ""),
            "is_active": getattr(obj, "is_active", True),
        },
    }

    if request.method == "POST":
        context["form"] = request.POST
        target = obj or Kindergarten()
        target.name = request.POST.get("name", "").strip()
        target.address = request.POST.get("address", "").strip()
        target.phone = request.POST.get("phone", "").strip()
        target.email = request.POST.get("email", "").strip()
        target.description = request.POST.get("description", "").strip()
        target.is_active = request.POST.get("is_active") == "on"

        if not target.name:
            context["error"] = "Цэцэрлэгийн нэрийг оруулна уу."
            return render(request, "tenants/kindergarten_form.html", context)

        try:
            services.save_kindergarten(actor=request.user, obj=target,
                                       created=obj is None, request=request)
        except (PermissionDenied, ValidationError) as exc:
            context["error"] = _message(exc)
            return render(request, "tenants/kindergarten_form.html", context)

        messages.success(request, "Цэцэрлэгийн мэдээлэл хадгалагдлаа.")
        return redirect("tenants:kindergarten_list")

    return render(request, "tenants/kindergarten_form.html", context)


# ------------------------------------------------------------------- groups

@login_required
def group_list(request):
    """RFP §3.2 — groups across the kindergartens this director runs."""
    _admin_only(request.user)

    kindergartens = list(selectors.administered_kindergartens(request.user))
    years = list(
        SchoolYear.objects.filter(kindergarten__in=kindergartens)
        .select_related("kindergarten")
        .order_by("-starts_on")
    )

    chosen_kg = next(
        (k for k in kindergartens
         if str(k.pk) == request.GET.get("kindergarten")), None
    )
    chosen_year = next(
        (y for y in years if str(y.pk) == request.GET.get("year")), None
    )
    filters = {
        "q": request.GET.get("q", "").strip(),
        "kindergarten": chosen_kg,
        "school_year": chosen_year,
        "status": request.GET.get("status", ""),
    }
    rows = selectors.group_rows(request.user, **filters)

    return render(request, "tenants/group_list.html", _base("groups") | {
        "page": _page(request, rows),
        "kindergartens": kindergartens,
        "years": years,
        "filters": filters,
        "statuses": Group.Status.choices,
        "total": rows.count(),
    })


@login_required
def group_form(request, group_id=None):
    """RFP §3.2 — name, age band, school year, timetable, rules, status."""
    _admin_only(request.user)

    kindergartens = list(selectors.administered_kindergartens(request.user))
    years = list(
        SchoolYear.objects.filter(kindergarten__in=kindergartens)
        .select_related("kindergarten")
        .order_by("-starts_on")
    )

    obj = None
    if group_id is not None:
        obj = Group.objects.filter(
            pk=group_id, kindergarten__in=kindergartens
        ).select_related("school_year").first()
        if obj is None:
            raise Http404

    context = _base("groups") | {
        "obj": obj,
        "years": years,
        "statuses": Group.Status.choices,
        "form": {
            "name": getattr(obj, "name", ""),
            "age_category": getattr(obj, "age_category", ""),
            "school_year": getattr(obj, "school_year_id", ""),
            "timetable": getattr(obj, "timetable", ""),
            "rules": getattr(obj, "rules", ""),
            "status": getattr(obj, "status", Group.Status.ACTIVE),
        },
    }

    if request.method == "POST":
        context["form"] = request.POST
        year = next(
            (y for y in years if str(y.pk) == request.POST.get("school_year")),
            None,
        )
        if year is None:
            context["error"] = "Хичээлийн жилээ сонгоно уу."
            return render(request, "tenants/group_form.html", context)

        target = obj or Group()
        target.name = request.POST.get("name", "").strip()
        target.age_category = request.POST.get("age_category", "").strip()
        target.school_year = year
        # Taken from the school year, never from the form: a crafted post
        # naming another tenant's kindergarten would put the group — and the
        # denormalized kindergarten_id every filter relies on — in the wrong
        # one (RFP §3.2). ``save_group`` refuses a mismatch as the backstop;
        # this is what makes the pair always agree.
        target.kindergarten = year.kindergarten
        target.timetable = request.POST.get("timetable", "").strip()
        target.rules = request.POST.get("rules", "").strip()
        target.status = request.POST.get("status") or Group.Status.ACTIVE

        if not target.name:
            context["error"] = "Бүлгийн нэрийг оруулна уу."
            return render(request, "tenants/group_form.html", context)

        try:
            services.save_group(actor=request.user, obj=target,
                                created=obj is None, request=request)
        except (PermissionDenied, ValidationError) as exc:
            context["error"] = _message(exc)
            return render(request, "tenants/group_form.html", context)

        messages.success(request, "Бүлгийн мэдээлэл хадгалагдлаа.")
        return redirect("tenants:group_list")

    return render(request, "tenants/group_form.html", context)


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
