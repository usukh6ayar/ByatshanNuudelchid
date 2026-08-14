"""Administrator screens for the assessment configuration — RFP §6.1, §6.4.

Two things a director sets up once a year and then leaves alone: the school
year's four terms, and the development domains children are assessed
against. Both were Django admin changelists.

Kept apart from ``views.py``, which is the teacher's daily work — the grid,
the matrix, the term report. These are configuration, reached from the
administrator's sidebar, and a teacher has no business on them.

The shared system defaults (``kindergarten IS NULL``) are visible here but
read-only for a director: renaming "Хэл яриа" in one kindergarten would
rename it in every kindergarten. ``save_config`` enforces that; the screens
show it, so the refusal arrives before the typing rather than after.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

from apps.accounts.models import Role
from apps.core.layouts import ADMIN
from apps.tenants.models import SchoolYear
from apps.tenants.selectors import administered_kindergartens

from . import selectors, services
from .models import DevelopmentDomain, Term


def _admin_only(user):
    """RFP §2.1 — configuration belongs to the director. 404, not 403."""
    if user is None or not user.is_authenticated or not user.is_active:
        raise Http404
    if not user.memberships.filter(
        is_active=True, role__in=[Role.ADMIN, Role.SUPERADMIN]
    ).exists():
        raise Http404


def _is_superadmin(user) -> bool:
    return user.memberships.filter(
        is_active=True, role=Role.SUPERADMIN
    ).exists()


# -------------------------------------------------------------------- terms

@login_required
def term_list(request):
    """RFP §6.4 — the four terms of each school year."""
    _admin_only(request.user)

    kindergartens = list(administered_kindergartens(request.user))
    years = list(
        SchoolYear.objects.filter(kindergarten__in=kindergartens)
        .select_related("kindergarten")
        .order_by("-starts_on")
    )
    chosen = next(
        (y for y in years if str(y.pk) == request.GET.get("year")),
        next((y for y in years if y.is_current), years[0] if years else None),
    )

    terms = (list(selectors.terms_for(chosen)) if chosen else [])

    return render(request, "assessment/admin_term_list.html", {
        "base_template": ADMIN,
        "nav": "terms",
        "years": years,
        "year": chosen,
        "terms": terms,
    })


@login_required
def term_create_defaults(request):
    """RFP §6.4 — give a year its four terms in one action.

    A school year with no terms means nothing can be assessed at all, so the
    common case is one button rather than four forms. The dates are a
    starting point the director then adjusts.
    """
    _admin_only(request.user)

    if request.method != "POST":
        raise Http404

    year = SchoolYear.objects.filter(
        pk=request.POST.get("year"),
        kindergarten__in=administered_kindergartens(request.user),
    ).first()
    if year is None:
        raise Http404

    try:
        created = services.ensure_default_terms(actor=request.user,
                                                school_year=year,
                                                request=request)
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, _message(exc))
    else:
        messages.success(request, f"{len(created)} улирал үүслээ.")

    return redirect(f"{reverse('assessment:admin_term_list')}?year={year.pk}")


@login_required
def term_edit(request, term_id):
    """RFP §6.4 — a term's name and dates."""
    _admin_only(request.user)

    term = Term.objects.filter(
        pk=term_id,
        kindergarten__in=administered_kindergartens(request.user),
    ).select_related("school_year").first()
    if term is None:
        raise Http404

    context = {
        "base_template": ADMIN,
        "nav": "terms",
        "term": term,
        "form": {
            "name": term.name,
            "starts_on": term.starts_on.isoformat(),
            "ends_on": term.ends_on.isoformat(),
        },
    }

    if request.method == "POST":
        context["form"] = request.POST
        term.name = request.POST.get("name", "").strip()

        if not term.name:
            context["error"] = "Улирлын нэрийг оруулна уу."
            return render(request, "assessment/admin_term_form.html", context)

        # Parsed here, not handed to the model as a string: ``save_term``
        # compares the dates against the school year's, and a str would
        # crash it rather than fail validation.
        starts = parse_date(request.POST.get("starts_on", ""))
        ends = parse_date(request.POST.get("ends_on", ""))
        if starts is None or ends is None:
            context["error"] = "Огноог зөв оруулна уу."
            return render(request, "assessment/admin_term_form.html", context)
        term.starts_on = starts
        term.ends_on = ends

        try:
            services.save_term(actor=request.user, obj=term, created=False,
                               request=request)
        except (PermissionDenied, ValidationError) as exc:
            context["error"] = _message(exc)
            return render(request, "assessment/admin_term_form.html", context)

        messages.success(request, "Улирал хадгалагдлаа.")
        return redirect(f"{reverse('assessment:admin_term_list')}"
                        f"?year={term.school_year_id}")

    return render(request, "assessment/admin_term_form.html", context)


# ------------------------------------------------------------------ domains

@login_required
def domain_list(request):
    """RFP §6.1 — the development domains, system and own."""
    _admin_only(request.user)

    kindergartens = list(administered_kindergartens(request.user))
    chosen = next(
        (k for k in kindergartens
         if str(k.pk) == request.GET.get("kindergarten")),
        kindergartens[0] if kindergartens else None,
    )

    domains = (list(selectors.domains_for(chosen.pk)) if chosen else [])
    levels = (list(selectors.levels_for(chosen.pk)) if chosen else [])

    return render(request, "assessment/admin_domain_list.html", {
        "base_template": ADMIN,
        "nav": "domains",
        "kindergartens": kindergartens,
        "kindergarten": chosen,
        "domains": domains,
        "levels": levels,
        "scale": selectors.scale_for(chosen.pk) if chosen else None,
        "is_superadmin": _is_superadmin(request.user),
    })


@login_required
def domain_form(request, domain_id=None):
    """RFP §6.1 — add or rename one of this kindergarten's own domains."""
    _admin_only(request.user)

    kindergartens = list(administered_kindergartens(request.user))
    superadmin = _is_superadmin(request.user)

    obj = None
    if domain_id is not None:
        obj = DevelopmentDomain.objects.filter(pk=domain_id).first()
        if obj is None:
            raise Http404
        # A director may read the shared list but not edit it — the same
        # rule save_config enforces, applied before the form is drawn.
        own = obj.kindergarten_id in {k.pk for k in kindergartens}
        if not own and not superadmin:
            raise Http404

    context = {
        "base_template": ADMIN,
        "nav": "domains",
        "obj": obj,
        "kindergartens": kindergartens,
        "form": {
            "name": getattr(obj, "name", ""),
            "code": getattr(obj, "code", ""),
            "color": getattr(obj, "color", "#5b4bd6"),
            "order": getattr(obj, "order", 0),
            "description": getattr(obj, "description", ""),
            "is_active": getattr(obj, "is_active", True),
            "kindergarten": getattr(obj, "kindergarten_id", ""),
        },
    }

    if request.method == "POST":
        context["form"] = request.POST
        kindergarten = next(
            (k for k in kindergartens
             if str(k.pk) == request.POST.get("kindergarten")), None
        )
        if obj is None and kindergarten is None:
            context["error"] = "Цэцэрлэгээ сонгоно уу."
            return render(request, "assessment/admin_domain_form.html", context)

        target = obj or DevelopmentDomain()
        if obj is None:
            target.kindergarten = kindergarten
        target.name = request.POST.get("name", "").strip()
        target.code = request.POST.get("code", "").strip()
        target.color = request.POST.get("color", "").strip() or "#5b4bd6"
        target.order = _as_int(request.POST.get("order"), 0)
        target.description = request.POST.get("description", "").strip()
        target.is_active = request.POST.get("is_active") == "on"

        if not target.name:
            context["error"] = "Чиглэлийн нэрийг оруулна уу."
            return render(request, "assessment/admin_domain_form.html", context)
        if not target.code:
            context["error"] = "Кодыг оруулна уу."
            return render(request, "assessment/admin_domain_form.html", context)

        try:
            services.save_config(actor=request.user, obj=target,
                                 created=obj is None, request=request)
        except (PermissionDenied, ValidationError) as exc:
            context["error"] = _message(exc)
            return render(request, "assessment/admin_domain_form.html", context)

        messages.success(request, "Хөгжлийн чиглэл хадгалагдлаа.")
        return redirect("assessment:admin_domain_list")

    return render(request, "assessment/admin_domain_form.html", context)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
