"""Observation screens — RFP §5.1, §5.2, §5.4.

Views parse the request and render. Every rule is in ``services`` and every
query in ``selectors`` (CLAUDE.md §2.1), so the DRF layer of a later phase
answers identically.

The child is always resolved through ``child_selectors.child_detail``, which
starts from ``visible_children``: an id outside the user's reach is not found
rather than forbidden (RFP §21.4).
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.assessment.selectors import domains_for, levels_for
from apps.children import selectors as child_selectors
from apps.core.models import AuditAction
from apps.core.permissions import can_record_for_child, is_guardian_of
from apps.core.services import audit

from . import selectors, services
from .models import Observation


def _context(request, child_id) -> dict:
    """Resolve the child through the permission layer, or 404."""
    child = child_selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404

    guardian = is_guardian_of(request.user, child)
    return {
        "child": child,
        "is_guardian": guardian,
        "can_record": can_record_for_child(request.user, child),
        "base_template": "base_parent.html" if guardian else "base_teacher.html",
        "nav": "home" if guardian else "children",
    }


@login_required
def observation_list(request, child_id):
    """RFP §5.1 — one child's observations."""
    context = _context(request, child_id)
    child = context["child"]

    types = selectors.types_for(child.kindergarten_id)
    domains = domains_for(child.kindergarten_id)
    levels = levels_for(child.kindergarten_id)

    # Resolved against this kindergarten's own configuration, so an id from
    # somewhere else simply matches nothing instead of filtering by it.
    selected_type = _pick(types, request.GET.get("type"))
    selected_domain = _pick(domains, request.GET.get("domain"))
    selected_level = _pick(levels, request.GET.get("level"))

    observations = selectors.child_observations(
        request.user, child,
        type=selected_type,
        source=request.GET.get("source") or None,
        date_from=_optional_date(request.GET.get("from")),
        date_to=_optional_date(request.GET.get("to")),
        domain=selected_domain,
        level=selected_level,
    )

    page = Paginator(observations, selectors.PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    context |= {
        "page": page,
        "types": types,
        "domains": domains,
        "levels": levels,
        "selected_type": selected_type,
        "sources": Observation.Source.choices,
        "filters": {
            "type": request.GET.get("type", ""),
            "source": request.GET.get("source", ""),
            "domain": request.GET.get("domain", ""),
            "level": request.GET.get("level", ""),
            "from": request.GET.get("from", ""),
            "to": request.GET.get("to", ""),
        },
    }
    return render(request, "observations/list.html", context)


@login_required
def observation_detail(request, child_id, observation_id):
    """RFP §5.1."""
    context = _context(request, child_id)
    child = context["child"]

    observation = selectors.observation_detail(request.user, child,
                                               observation_id)
    if observation is None:
        raise Http404

    # RFP §971 — opening one child's record is a meaningful access.
    audit(action=AuditAction.VIEW, request=request, child=child,
          obj=observation, kindergarten=child.kindergarten,
          section="observation")

    context |= {"observation": observation}
    return render(request, "observations/detail.html", context)


@login_required
def observation_create(request, child_id):
    """RFP §5.1 — the teacher's entry form.

    A guardian reaching this URL gets a 404 from the service, not a
    redirect: §5.4 gives them their own submission screen, and this is the
    teacher's professional record.
    """
    context = _context(request, child_id)
    child = context["child"]

    if not context["can_record"]:
        # A guardian has their own screen (§5.4). Rendering the teacher's
        # form for them would offer fields the service then refuses.
        raise Http404

    context |= _form_context(child)

    if request.method == "POST":
        try:
            observation = services.create_observation(
                actor=request.user, child=child, request=request,
                **_posted(request, child),
            )
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, ValueError) as exc:
            context |= {
                "error": _message(exc), "form": request.POST,
                "domain_rows": _domain_rows(child, posted=request.POST),
                "observed_on_value": _observed_on_value(posted=request.POST),
            }
            return render(request, "observations/form.html", context)

        messages.success(request, "Ажиглалт бүртгэгдлээ.")
        return redirect("observations:detail", child_id=child.pk,
                        observation_id=observation.pk)

    context |= {"form": {}, "domain_rows": _domain_rows(child),
                "observed_on_value": _observed_on_value()}
    return render(request, "observations/form.html", context)


@login_required
def observation_edit(request, child_id, observation_id):
    """RFP §5.1."""
    context = _context(request, child_id)
    child = context["child"]

    observation = selectors.observation_detail(request.user, child,
                                               observation_id)
    if observation is None:
        raise Http404

    context |= _form_context(child) | {"observation": observation}

    if request.method == "POST":
        try:
            services.update_observation(
                actor=request.user, observation=observation, request=request,
                **_posted(request, child),
            )
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, ValueError) as exc:
            context |= {
                "error": _message(exc), "form": request.POST,
                "domain_rows": _domain_rows(child, posted=request.POST),
                "observed_on_value": _observed_on_value(posted=request.POST),
            }
            return render(request, "observations/form.html", context)

        messages.success(request, "Ажиглалт шинэчлэгдлээ.")
        return redirect("observations:detail", child_id=child.pk,
                        observation_id=observation.pk)

    context |= {
        "form": observation,
        "domain_rows": _domain_rows(child, observation=observation),
        "observed_on_value": _observed_on_value(observation=observation),
    }
    return render(request, "observations/form.html", context)


@login_required
def parent_observation_create(request, child_id):
    """RFP §5.4 — "эцэг эх гэрт ажигласан мэдээллээ системд оруулна".

    A separate screen from the teacher's rather than the same one with
    fields hidden: §5.1's form asks for a professional judgement — the
    development domains, the support plan, whether the family may see it —
    and none of those are a parent's to give. The service refuses them
    anyway; not rendering them is what stops the form from asking.
    """
    context = _context(request, child_id)
    child = context["child"]

    if not context["is_guardian"]:
        # Staff use §5.1's own form. Their submission is not a "parent
        # observation" and must not enter the §5.4 review queue.
        raise Http404

    type = selectors.parent_observation_type(child.kindergarten_id)
    if type is None:
        raise Http404

    context |= {"today": timezone.localdate(), "type": type}

    if request.method == "POST":
        try:
            observation = services.create_observation(
                actor=request.user, child=child, request=request,
                source=Observation.Source.PARENT,
                type=type,
                observed_on=_date(request.POST.get("observed_on")),
                situation=request.POST.get("situation", "").strip(),
                child_did=request.POST.get("child_did", "").strip(),
                child_said=request.POST.get("child_said", "").strip(),
            )
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, ValueError) as exc:
            context |= {
                "error": _message(exc), "form": request.POST,
                "observed_on_value": _observed_on_value(posted=request.POST),
            }
            return render(request, "observations/parent_form.html", context)

        messages.success(
            request,
            "Ажиглалт илгээгдлээ. Багш хянасны дараа хүүхдийн хавтсанд нэмэгдэнэ.",
        )
        return redirect("observations:detail", child_id=child.pk,
                        observation_id=observation.pk)

    context |= {"form": {}, "observed_on_value": _observed_on_value()}
    return render(request, "observations/parent_form.html", context)


@login_required
def review_queue(request):
    """RFP §5.4 — "багш эцэг эхийн ажиглалтыг харах".

    Across every child the teacher is responsible for, not one child at a
    time: a submission nobody has looked at is the thing that goes stale,
    and finding it would otherwise mean opening thirty portfolios.
    """
    pending = selectors.pending_parent_observations(request.user)
    page = Paginator(pending, selectors.PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    return render(request, "observations/review_queue.html", {
        "page": page,
        "nav": "review",
    })


@login_required
def observation_delete(request, child_id, observation_id):
    """RFP §3.4 — archived, not removed."""
    context = _context(request, child_id)
    child = context["child"]

    observation = selectors.observation_detail(request.user, child,
                                               observation_id)
    if observation is None:
        raise Http404

    if request.method != "POST":
        return render(request, "observations/delete_confirm.html",
                      context | {"observation": observation})

    try:
        services.delete_observation(actor=request.user,
                                    observation=observation, request=request)
    except PermissionDenied:
        raise Http404 from None

    messages.success(request, "Ажиглалт архивлагдлаа.")
    return redirect("observations:list", child_id=child.pk)


@login_required
def observation_review(request, child_id, observation_id):
    """RFP §5.4 — the teacher approves or asks for a revision."""
    context = _context(request, child_id)
    child = context["child"]

    observation = selectors.observation_detail(request.user, child,
                                               observation_id)
    if observation is None:
        raise Http404

    if request.method != "POST":
        raise Http404

    try:
        services.review_observation(
            actor=request.user, observation=observation,
            status=request.POST.get("review_status", ""),
            note=request.POST.get("review_note", ""),
            include_in_report=request.POST.get("include_in_report") == "on",
            request=request,
        )
    except PermissionDenied:
        raise Http404 from None
    except ValidationError as exc:
        messages.error(request, _message(exc))
        return redirect("observations:detail", child_id=child.pk,
                        observation_id=observation.pk)

    messages.success(request, "Ажиглалтын төлөв шинэчлэгдлээ.")
    return redirect("observations:detail", child_id=child.pk,
                    observation_id=observation.pk)


# ---------------------------------------------------------------- helpers


def _form_context(child) -> dict:
    return {
        "types": selectors.types_for(child.kindergarten_id),
        "levels": levels_for(child.kindergarten_id),
        "today": timezone.localdate(),
    }


def _observed_on_value(*, observation=None, posted=None) -> str:
    """What the date input should show, as ``YYYY-MM-DD``.

    Computed here because the two sources have different types: a saved
    observation holds a ``date``, a rejected form holds the raw string the
    user typed. Formatting a string with Django's ``date`` filter yields an
    empty box, which throws away what they entered — on a form that has
    just told them something is wrong.
    """
    if posted is not None:
        return posted.get("observed_on", "")
    if observation is not None:
        return observation.observed_on.isoformat()
    return timezone.localdate().isoformat()


def _domain_rows(child, *, observation=None, posted=None) -> list[dict]:
    """The domain checkboxes, with what is already ticked.

    Computed here rather than in the template: working out "is this domain
    selected, and at which level" from two dictionaries is logic, and a
    template that does logic is a template nobody can test (CLAUDE.md §2.1).
    """
    if posted is not None:
        chosen = set(posted.getlist("domains"))
        return [
            {
                "domain": domain,
                "checked": str(domain.pk) in chosen,
                "level_id": _int_or_none(posted.get(f"level_{domain.pk}")),
            }
            for domain in domains_for(child.kindergarten_id)
        ]

    existing = (
        {link.domain_id: link.level_id for link in observation.domain_links.all()}
        if observation is not None
        else {}
    )
    return [
        {
            "domain": domain,
            "checked": domain.pk in existing,
            "level_id": existing.get(domain.pk),
        }
        for domain in domains_for(child.kindergarten_id)
    ]


def _posted(request, child) -> dict:
    """Turn the form into service arguments.

    Ids are resolved against the kindergarten's own configuration, so a
    crafted request naming another kindergarten's domain finds nothing here
    and the service rejects it as well.
    """
    types = selectors.types_for(child.kindergarten_id)
    return {
        "type": types.filter(pk=request.POST.get("type") or 0).first(),
        "observed_on": _date(request.POST.get("observed_on")),
        "activity_name": request.POST.get("activity_name", "").strip(),
        "situation": request.POST.get("situation", "").strip(),
        "child_did": request.POST.get("child_did", "").strip(),
        "child_said": request.POST.get("child_said", "").strip(),
        "teacher_comment": request.POST.get("teacher_comment", "").strip(),
        "next_steps": request.POST.get("next_steps", "").strip(),
        "visible_to_parents": request.POST.get("visible_to_parents") == "on",
        "include_in_report": request.POST.get("include_in_report") == "on",
        "domains": _domains(request, child),
    }


def _domains(request, child) -> list[tuple]:
    """The ticked domains, each with an optional level — §5.1's үнэлгээ.

    The form posts ``domain`` checkboxes and a ``level_<id>`` select beside
    each one.
    """
    chosen = request.POST.getlist("domains")
    if not chosen:
        return []

    domains = {
        str(domain.pk): domain for domain in domains_for(child.kindergarten_id)
    }
    levels = {
        str(level.pk): level for level in levels_for(child.kindergarten_id)
    }

    pairs = []
    for domain_id in chosen:
        domain = domains.get(domain_id)
        if domain is None:
            # Silently dropped here; the service raises if it is reached
            # with an unknown domain, so nothing gets written either way.
            continue
        pairs.append((domain, levels.get(request.POST.get(f"level_{domain_id}"))))
    return pairs


def _pick(queryset, raw):
    """One row from a queryset the user is already entitled to, or ``None``.

    Both the value and the absence of a match end in the same place: no
    filter. A §11 filter is a narrowing, so an unrecognised id must never
    become a way to select rows from somewhere else.
    """
    if not raw:
        return None
    return queryset.filter(pk=raw).first() if str(raw).isdigit() else None


def _optional_date(value):
    """A §11 date-interval bound. A malformed date filters nothing."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _int_or_none(value):
    """Form field names are attacker-controlled, so this never raises."""
    try:
        return int(value) or None
    except (TypeError, ValueError):
        return None


def _date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError("Огноо буруу форматтай байна.") from None


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)

