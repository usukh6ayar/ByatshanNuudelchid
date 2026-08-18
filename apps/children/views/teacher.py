"""Teacher-facing child screens — RFP §2.2, §11, §21.2.

Views parse the request and render; the rules live in ``services`` and
``selectors`` (CLAUDE.md §2.1). Authorization is never re-implemented here:
every query starts from ``visible_children``, so an id outside the user's
reach is simply not found and becomes a 404 (RFP §21.4).
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from apps.assessment import selectors as assessment_selectors
from apps.children import selectors, services
from apps.children.models import Child, Guardianship
from apps.core.models import AuditAction
from apps.core.permissions import assert_can_record_for_child, can_record_for_child
from apps.core.services import audit
from apps.observations import selectors as observation_selectors
from apps.portfolio import selectors as portfolio_selectors
from apps.tenants.selectors import assignable_groups, school_years_for

# How much of each list the detail page shows before handing over to the
# screen that owns it. This page is the hub, not the archive: each section
# links to the full record rather than reproducing it.
RECENT_OBSERVATIONS = 5
RECENT_MOMENTS = 6
RECENT_ASSESSMENTS = 9


def _get_child_or_404(request, child_id) -> Child:
    child = selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404
    return child


@login_required
def child_list(request):
    """RFP §11 — search, filter, sort, paginate."""
    groups = assignable_groups(request.user)
    # RFP §11 — "хичээлийн жилээр шүүх". The years offered are the ones the
    # user's own groups belong to, so the filter cannot reach a year at a
    # kindergarten they have nothing to do with.
    school_years = school_years_for(request.user)

    group = None
    if request.GET.get("group"):
        group = groups.filter(pk=request.GET["group"]).first()

    school_year = None
    if request.GET.get("school_year"):
        school_year = school_years.filter(
            pk=request.GET["school_year"]
        ).first()

    children = selectors.child_list(
        request.user,
        search=request.GET.get("q", "").strip(),
        group=group,
        school_year=school_year,
        status=request.GET.get("status") or None,
        sex=request.GET.get("sex") or None,
        age=request.GET.get("age") or None,
        sort=request.GET.get("sort", selectors.DEFAULT_SORT),
    )

    page = Paginator(children, selectors.PAGE_SIZE).get_page(request.GET.get("page"))

    return render(request, "children/teacher/list.html", {
        # Which sidebar item is highlighted — the shell reads this.
        "nav": "children",
        "page": page,
        "groups": groups,
        "school_years": school_years,
        "selected_group": group,
        "selected_school_year": school_year,
        "filters": {
            "q": request.GET.get("q", ""),
            "status": request.GET.get("status", ""),
            "sex": request.GET.get("sex", ""),
            "age": request.GET.get("age", ""),
            "school_year": request.GET.get("school_year", ""),
            "sort": request.GET.get("sort", selectors.DEFAULT_SORT),
        },
        "statuses": Child.Status.choices,
        "sexes": Child.Sex.choices,
    })


@login_required
def child_detail(request, child_id):
    child = _get_child_or_404(request, child_id)

    # RFP §971 — opening a child's record is a meaningful access, unlike
    # scrolling a list, so it is recorded.
    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten)

    return render(request, "children/teacher/detail.html", {
        "nav": "children",
        "child": child,
        "enrollment": services.current_enrollment(child),
        "history": selectors.enrollment_history(child),
        "guardianships": child.guardianships.all(),
        # Decides which actions the page offers. Not the authorization —
        # that is the edit view's own `assert_can_record_for_child`. A
        # template that hides a link is a courtesy; a view that checks is
        # the rule (CLAUDE.md §1.1).
        "can_record": can_record_for_child(request.user, child),

        # The working context added with the 2026-08-16 redesign. Every one
        # of these is a read through a selector that already existed and is
        # already used by the parent screens; no new query, rule or endpoint.
        #
        # The three that can expose a record take the **user**, not just the
        # child, so the §5.1 and §6.4 visibility rules are applied by the
        # layer that owns them. For a teacher that returns everything about
        # this child — including the observations they marked private — which
        # is the point of the screen. The portfolio reads take only the
        # child, which is safe because `_get_child_or_404` has already
        # resolved them through `visible_children`.
        "observations": observation_selectors.child_observations(
            request.user, child
        )[:RECENT_OBSERVATIONS],
        "observation_count": observation_selectors.child_observations(
            request.user, child
        ).count(),
        "moments": observation_selectors.recent_media_for_child(
            request.user, child, limit=RECENT_MOMENTS
        ),
        "assessments": assessment_selectors.child_assessments(
            request.user, child
        )[:RECENT_ASSESSMENTS],
        "about": portfolio_selectors.about_me(child),
        "age_profiles": portfolio_selectors.age_profiles(child),

        # The client's mockup opens the note-recording action as one card per
        # kind of note rather than a single button. The kinds are §5.2's own
        # `ObservationType` rows (CLAUDE.md §2.3), not a list written into the
        # template — a kindergarten that adds its own type gets a card for it.
        "observation_types": observation_selectors.teacher_observation_types(
            child.kindergarten_id
        ),
    })


@login_required
def child_create(request):
    """RFP §2.2 — a teacher registers a child into their own group."""
    groups = assignable_groups(request.user)
    if not groups.exists():
        raise Http404

    context: dict = {"groups": groups, "sexes": Child.Sex.choices, "form": {}}

    if request.method == "POST":
        context["form"] = request.POST

        # The group must be one of this user's own — otherwise the form
        # would accept any id and create a child in another teacher's group.
        group = groups.filter(pk=request.POST.get("group")).first()
        if group is None:
            context["error"] = "Бүлгээ сонгоно уу."
            return render(request, "children/teacher/form.html", context)

        try:
            child = services.register_child(
                actor=request.user,
                group=group,
                last_name=request.POST.get("last_name", ""),
                first_name=request.POST.get("first_name", ""),
                national_id=request.POST.get("national_id", ""),
                sex=request.POST.get("sex", ""),
                date_of_birth=_parse_date(request.POST.get("date_of_birth")),
                health_notes=request.POST.get("health_notes", ""),
                request=request,
            )
        except (ValidationError, ValueError) as exc:
            context["error"] = _message(exc)
            return render(request, "children/teacher/form.html", context)

        messages.success(request, f"{child.full_name} амжилттай бүртгэгдлээ.")
        return redirect("children:detail", child_id=child.pk)

    return render(request, "children/teacher/form.html", context)


@login_required
def child_edit(request, child_id):
    """RFP §2.2 — "хүүхдийн мэдээлэл засах".

    The gate is ``can_record_for_child``, not the ``_get_child_or_404`` used
    by the read views. A guardian passes the read check — the record is her
    child's — but the national id, the enrollment date and the health notes
    are the kindergarten's record, and §2.3 gives a guardian the portfolio,
    not that. Both verbs go through it: gating GET alone leaves a view that
    still writes.

    The group is deliberately absent from the form. Moving a child is
    ``transfer_child``, which writes the Enrollment row that
    ``child_kindergarten_history`` reads for authorization (CLAUDE.md §1.2);
    reassigning it here would move the child with no history behind it.
    ``update_child`` would refuse the field anyway — this keeps the refusal
    from ever being the user's first sign of it.
    """
    child = _get_child_or_404(request, child_id)
    assert_can_record_for_child(request.user, child)

    context: dict = {
        "child": child,
        "sexes": Child.Sex.choices,
        "statuses": Child.Status.choices,
        "form": {
            "last_name": child.last_name,
            "first_name": child.first_name,
            "national_id": child.national_id,
            "sex": child.sex,
            "date_of_birth": child.date_of_birth.isoformat(),
            "health_notes": child.health_notes,
        },
    }

    if request.method == "POST":
        context["form"] = request.POST

        try:
            services.update_child(
                actor=request.user,
                child=child,
                last_name=request.POST.get("last_name", ""),
                first_name=request.POST.get("first_name", ""),
                national_id=request.POST.get("national_id", ""),
                sex=request.POST.get("sex", ""),
                date_of_birth=_parse_date(request.POST.get("date_of_birth")),
                health_notes=request.POST.get("health_notes", ""),
                request=request,
            )
        except (ValidationError, ValueError) as exc:
            context["error"] = _message(exc)
            return render(request, "children/teacher/edit_form.html", context)

        messages.success(request, f"{child.full_name} хадгалагдлаа.")
        return redirect("children:detail", child_id=child.pk)

    return render(request, "children/teacher/edit_form.html", context)


@login_required
def guardian_add(request, child_id):
    """RFP §3.5 — attach a guardian, which grants them access (§21.3)."""
    child = _get_child_or_404(request, child_id)

    context: dict = {
        "child": child,
        "relations": Guardianship.Relation.choices,
        "form": {},
    }

    if request.method == "POST":
        context["form"] = request.POST
        try:
            _, token, code = services.attach_guardian(
                actor=request.user,
                child=child,
                last_name=request.POST.get("last_name", ""),
                first_name=request.POST.get("first_name", ""),
                relation=request.POST.get("relation", ""),
                email=request.POST.get("email", "").strip() or None,
                phone=request.POST.get("phone", "").strip() or None,
                is_primary=bool(request.POST.get("is_primary")),
                request=request,
            )
        except (ValidationError, ValueError) as exc:
            context["error"] = _message(exc)
            return render(request, "children/teacher/guardian_form.html", context)

        if code:
            # Shown once. Only the hash is stored, so it cannot be looked up
            # again — a re-send issues a new invitation.
            context["activation_code"] = code
            context["activation_link"] = request.build_absolute_uri(
                f"/burtgel-idevhjuuleh/{token}/"
            )
            context["child"] = child
            return render(request, "children/teacher/guardian_invited.html", context)

        messages.success(request, "Асран хамгаалагч холбогдлоо.")
        return redirect("children:detail", child_id=child.pk)

    return render(request, "children/teacher/guardian_form.html", context)


def _parse_date(value):
    if not value:
        raise ValueError("Төрсөн огноог оруулна уу.")
    return dt.date.fromisoformat(value)


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
