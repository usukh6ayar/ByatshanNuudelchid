"""Assessment screens — RFP §6.3, §6.4.

Two screens. The child view is the term-by-term matrix a teacher and a
guardian both read; the group grid is §6.3's "assess a whole group from one
screen", which is teacher-only.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render

from apps.children import selectors as child_selectors
from apps.children.services import current_enrollment
from apps.core.layouts import layout_for
from apps.core.models import AuditAction
from apps.core.permissions import can_record_for_child, is_guardian_of
from apps.core.services import audit
from apps.tenants.selectors import assignable_groups

from . import selectors, services
from .models import Term


def _context(request, child_id) -> dict:
    child = child_selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404

    guardian = is_guardian_of(request.user, child)
    return {
        "child": child,
        "is_guardian": guardian,
        "can_record": can_record_for_child(request.user, child),
        "base_template": layout_for(request.user, guardian_view=guardian),
        "nav": "home" if guardian else "children",
    }


@login_required
def child_assessment(request, child_id):
    """RFP §6.4 — one child's domains across the four terms."""
    context = _context(request, child_id)
    child = context["child"]

    enrollment = current_enrollment(child)
    if enrollment is None:
        # A registered child with no group cannot be assessed yet. Saying so
        # is more useful than an empty grid with no explanation.
        return render(request, "assessment/child.html",
                      context | {"no_enrollment": True})

    school_year = enrollment.school_year
    matrix = selectors.assessment_matrix(request.user, child, school_year)

    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten, section="assessment")

    reports = selectors.term_reports_for(request.user, child)
    context |= {
        "school_year": school_year,
        "matrix": matrix,
        "terms": matrix["terms"],
        "levels": selectors.levels_for(child.kindergarten_id),
        "group": enrollment.group,
        # Paired here rather than looked up in the template: Django cannot
        # index a dict by a variable key without a custom filter, and one
        # filter for one screen is not worth a template library.
        "term_reports": [
            (term, reports.get(term.pk)) for term in matrix["terms"]
        ],
    }
    return render(request, "assessment/child.html", context)


@login_required
def child_assessment_save(request, child_id):
    """RFP §6.4 — record one domain for one term, from the child screen."""
    context = _context(request, child_id)
    child = context["child"]

    if request.method != "POST":
        raise Http404

    enrollment = current_enrollment(child)
    if enrollment is None:
        raise Http404

    domains = {
        str(domain.pk): domain
        for domain in selectors.domains_for(child.kindergarten_id)
    }
    levels = {
        str(level.pk): level
        for level in selectors.levels_for(child.kindergarten_id)
    }
    term = Term.objects.filter(
        school_year=enrollment.school_year, pk=request.POST.get("term") or 0
    ).first()

    if term is None:
        raise Http404

    try:
        services.save_assessment(
            actor=request.user, child=child, enrollment=enrollment,
            domain=domains.get(request.POST.get("domain", "")),
            term=term,
            level=levels.get(request.POST.get("level", "")),
            comment=request.POST.get("comment", "").strip(),
            request=request,
        )
    except PermissionDenied:
        raise Http404 from None
    except (ValidationError, AttributeError) as exc:
        messages.error(request, _message(exc))
        return redirect("assessment:child", child_id=child.pk)

    messages.success(request, "Үнэлгээ хадгалагдлаа.")
    return redirect("assessment:child", child_id=child.pk)


@login_required
def term_report(request, child_id, term_id):
    """RFP §6.4 — the narrative a teacher writes once the grid is filled in.

    Teacher-only: ``_context`` resolves the child through the permission
    layer, and ``can_record_for_child`` is what separates reading the
    portfolio from writing the professional record (§5.1, §6.3). A guardian
    reads the finished report on the assessment screen instead.
    """
    context = _context(request, child_id)
    child = context["child"]

    if not context["can_record"]:
        raise Http404

    enrollment = current_enrollment(child)
    if enrollment is None:
        raise Http404

    term = Term.objects.filter(
        school_year=enrollment.school_year, pk=term_id
    ).first()
    if term is None:
        raise Http404

    if request.method == "POST":
        narrative = {
            field: request.POST.get(field, "").strip()
            for field in ("strengths", "needs_support", "next_goals",
                          "advice_for_parents")
        }
        try:
            services.save_term_report(actor=request.user, child=child,
                                      term=term, enrollment=enrollment,
                                      request=request, **narrative)
            if request.POST.get("action") == "finalize":
                services.finalize_term(actor=request.user, child=child,
                                       term=term, request=request)
                messages.success(request, "Тайлан дуусаж, эцэг эхэд нээгдлээ.")
            elif request.POST.get("action") == "reopen":
                services.reopen_term(actor=request.user, child=child,
                                     term=term, request=request)
                messages.success(request, "Тайлан ноорог болж хаагдлаа.")
            else:
                messages.success(request, "Тайлан хадгалагдлаа.")
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            messages.error(request, _message(exc))

        return redirect("assessment:term_report", child_id=child.pk,
                        term_id=term.pk)

    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten, section="term_report")

    context |= {
        "term": term,
        "report": selectors.term_report(request.user, child, term),
        "assessments": selectors.child_assessments(request.user, child, term),
    }
    return render(request, "assessment/term_report.html", context)


@login_required
def group_grid(request, group_id):
    """RFP §6.3 — the whole group, one domain, one screen.

    Teacher-only by construction: ``assignable_groups`` returns the groups
    this user is assigned to, so a group id outside it is not found (§21.4).
    """
    group = assignable_groups(request.user).filter(pk=group_id).first()
    if group is None:
        raise Http404

    domains = selectors.domains_for(group.kindergarten_id)
    domain = None
    if request.GET.get("domain"):
        domain = domains.filter(pk=request.GET["domain"]).first()
    domain = domain or domains.first()

    terms = selectors.terms_for(group.school_year)
    term = services.resolve_term(group.school_year, request.GET.get("term"))
    term = term or terms.first()

    context = {
        "group": group,
        "domains": domains,
        "domain": domain,
        "terms": terms,
        "term": term,
        "nav": "children",
    }

    if term is None or domain is None:
        # No terms configured yet, or no domains. Both are administrator
        # tasks, so the screen says which one is missing.
        return render(request, "assessment/group_grid.html", context)

    if request.method == "POST":
        entries = {
            key.removeprefix("level_"): value
            for key, value in request.POST.items()
            if key.startswith("level_") and value
        }
        try:
            saved = services.save_group_assessments(
                actor=request.user, group=group, term=term, domain=domain,
                entries=entries, request=request,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f"{saved} хүүхдийн үнэлгээ хадгалагдлаа.")
        return redirect(
            f"{request.path}?domain={domain.pk}&term={term.pk}"
        )

    context |= selectors.group_grid(request.user, group, term, domain)
    return render(request, "assessment/group_grid.html", context)


# ---------------------------------------------------------------- helpers


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
