"""Portfolio screens — RFP §4.1, §4.2, §4.3.

One set of views serves both roles. The portfolio is a single artifact that a
teacher and a guardian both write to (§2.3, §4.3), so duplicating the views
per role would be two copies of the same rules drifting apart — the failure
CLAUDE.md §2.1 exists to prevent. The layout is chosen per request instead.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render

from apps.children import selectors as child_selectors
from apps.core.models import AuditAction
from apps.core.permissions import is_guardian_of
from apps.core.services import audit

from . import selectors, services
from .models import ChildAgeProfile


def _context(request, child_id) -> dict:
    """Resolve the child through the permission layer, or 404."""
    child = child_selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404

    guardian = is_guardian_of(request.user, child)
    return {
        "child": child,
        "is_guardian": guardian,
        "base_template": "base_parent.html" if guardian else "base_teacher.html",
        "nav": "home" if guardian else "children",
    }


@login_required
def portfolio(request, child_id):
    """The child's portfolio: About Me, birthdays, and the four age pages."""
    context = _context(request, child_id)
    child = context["child"]

    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten, section="portfolio")

    context |= {
        "about": selectors.about_me(child),
        "birth": selectors.birth_facts(child),
        "birthdays": selectors.birthdays(child),
        "age_profiles": selectors.age_profiles(child),
        "completeness": selectors.completeness(child),
    }
    return render(request, "portfolio/overview.html", context)


@login_required
def about_me_edit(request, child_id):
    """RFP §4.1. Guardians may edit this too — §2.3."""
    context = _context(request, child_id)
    child = context["child"]
    about = selectors.about_me(child)

    if request.method == "POST":
        try:
            services.save_about_me(
                actor=request.user, child=child, request=request,
                introduction=request.POST.get("introduction", ""),
                name_meaning=request.POST.get("name_meaning", ""),
                memorable_sayings=request.POST.get("memorable_sayings", ""),
                dream=request.POST.get("dream", ""),
                distinguishing_traits=request.POST.get("distinguishing_traits", ""),
                height_cm=_decimal(request.POST.get("height_cm")),
                weight_kg=_decimal(request.POST.get("weight_kg")),
                recorded_on=_date(request.POST.get("recorded_on")),
            )
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, ValueError) as exc:
            context |= {"error": _message(exc), "form": request.POST}
            return render(request, "portfolio/about_me_form.html", context)

        messages.success(request, "«Миний тухай» хадгалагдлаа.")
        return redirect("portfolio:overview", child_id=child.pk)

    context |= {"form": about, "about": about}
    return render(request, "portfolio/about_me_form.html", context)


@login_required
def age_profile_edit(request, child_id, age):
    """RFP §4.3 — one page per age."""
    context = _context(request, child_id)
    child = context["child"]

    if age not in ChildAgeProfile.Age.values:
        raise Http404

    editable = services.editable_age_profile_fields(request.user, child)

    if request.method == "POST":
        submitted = {
            name: request.POST.get(name, "") for name in editable
        }
        try:
            services.save_age_profile(
                actor=request.user, child=child, age=age,
                school_year=_current_school_year(child), request=request,
                **submitted,
            )
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            context |= {"error": _message(exc), "form": request.POST,
                        "age": age, "editable": editable}
            return render(request, "portfolio/age_profile_form.html", context)

        messages.success(request, f"{age} насны мэдээлэл хадгалагдлаа.")
        return redirect("portfolio:overview", child_id=child.pk)

    context |= {
        "age": age,
        "form": selectors.age_profile(child, age),
        "editable": editable,
    }
    return render(request, "portfolio/age_profile_form.html", context)


@login_required
def birthday_note_edit(request, child_id, age):
    """RFP §4.2."""
    context = _context(request, child_id)
    child = context["child"]

    if request.method == "POST":
        try:
            services.save_birthday_note(
                actor=request.user, child=child, age=age,
                note=request.POST.get("note", ""), request=request,
            )
        except PermissionDenied:
            raise Http404 from None

        messages.success(request, "Төрсөн өдрийн тэмдэглэл хадгалагдлаа.")

    return redirect("portfolio:overview", child_id=child.pk)


# ---------------------------------------------------------------- helpers


def _decimal(value):
    return value.strip() or None if isinstance(value, str) else value


def _date(value):
    import datetime as dt

    value = (value or "").strip()
    return dt.date.fromisoformat(value) if value else None


def _current_school_year(child):
    enrollment = child.enrollments.filter(status="active").first()
    return enrollment.school_year if enrollment else None


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
