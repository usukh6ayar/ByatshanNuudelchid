"""Assessment writes — RFP §6.3, §6.4. All rules live here (CLAUDE.md §2.1).

The views and Django Admin call these; the DRF layer of a later phase will
call the same functions, which is why none of this is in a view.
"""

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.children.models import Enrollment
from apps.core.permissions import can_record_for_child, visible_kindergartens
from apps.core.services import save_record

from .models import Assessment, Term
from .selectors import current_term, domains_for, levels_for

__all__ = [
    "recording_enrollment",
    "assert_writable",
    "save_assessment",
    "save_group_assessments",
    "publish_term",
    "ensure_default_terms",
    "save_config",
    "save_term",
]

# RFP §6.4 splits the school year into four. The proportions below are only
# the starting point an administrator then adjusts on the Term screen.
TERM_NAMES = ["I улирал", "II улирал", "III улирал", "IV улирал"]


def recording_enrollment(child) -> Enrollment:
    """The enrollment a new record is filed under — spec section 4.2.

    Records carry the enrollment, not just the child, because that is what
    makes ``kindergarten_id`` correct after a transfer: an observation
    written last year stays attached to last year's kindergarten, so
    ``visible_kindergartens()`` keeps showing it to the teacher who wrote it
    and hides it from nobody else.

    A child with no active enrollment cannot be assessed. That is a real
    state — a just-registered child, or one who has left — and refusing with
    a message is better than filing the record against nothing.
    """
    enrollment = (
        child.enrollments.filter(status=Enrollment.Status.ACTIVE)
        .select_related("group", "school_year")
        .first()
    )
    if enrollment is None:
        raise ValidationError(
            "Хүүхэд идэвхтэй бүлэгт бүртгэлгүй байна. "
            "Эхлээд бүлэгт бүртгэнэ үү."
        )
    return enrollment


def assert_writable(actor, child, enrollment) -> None:
    """The record must land in a kindergarten this user is part of.

    ``can_record_for_child`` deliberately survives a transfer: a teacher
    keeps the right to correct the observations they wrote themselves
    (spec section 4.2). It does *not* follow that they may write *new*
    records at the child's new kindergarten — that would create a row
    inside another tenant, which is exactly what RFP §3.2 forbids.

    ``visible_kindergartens`` already answers "which kindergartens' records
    about this child may this user touch", so the write side asks it too
    rather than inventing a second rule (CLAUDE.md §1.1).
    """
    if enrollment.kindergarten_id not in visible_kindergartens(actor, child):
        raise PermissionDenied


def _guard(actor, child):
    """Assessing is a staff action — RFP §6.3 names the teacher."""
    if not can_record_for_child(actor, child):
        raise PermissionDenied


def _check_level(enrollment, level):
    """The level must come from the scale this kindergarten actually uses.

    Without this a crafted request could reference another kindergarten's
    scale, and §12.3's per-domain average would then mix two numbering
    systems.
    """
    if level is None:
        raise ValidationError("Үнэлгээний түвшинг сонгоно уу.")

    allowed = levels_for(enrollment.kindergarten_id).values_list("pk", flat=True)
    if level.pk not in set(allowed):
        raise ValidationError("Энэ цэцэрлэгт хамаарахгүй үнэлгээний түвшин байна.")


def _check_domain(enrollment, domain):
    """Same rule for the domain — §6.1's list is per kindergarten too.

    Without it another kindergarten's private domain could be attached to
    an assessment, and it would then appear on that kindergarten's own
    §12.3 averages for a child they have never met.
    """
    if domain is None:
        raise ValidationError("Хөгжлийн чиглэлийг сонгоно уу.")

    allowed = domains_for(enrollment.kindergarten_id).values_list("pk", flat=True)
    if domain.pk not in set(allowed):
        raise ValidationError("Энэ цэцэрлэгт хамаарахгүй хөгжлийн чиглэл байна.")


def _check_term(enrollment, term):
    if term.school_year_id != enrollment.school_year_id:
        raise ValidationError("Улирал нь тухайн хичээлийн жилийнх биш байна.")


@transaction.atomic
def save_assessment(*, actor, child, domain, term, level, comment="",
                    enrollment=None, request=None) -> Assessment:
    """RFP §6.3, §6.4 — record or update one domain for one term.

    Idempotent by design: a second submission for the same
    (child, enrollment, domain, term) updates the existing row rather than
    creating a second one. The database constraint of the same name is the
    backstop for the double-click §17 forbids, not the mechanism.
    """
    _guard(actor, child)

    enrollment = enrollment or recording_enrollment(child)
    if enrollment.child_id != child.pk:
        raise ValidationError("Бүртгэл нь өөр хүүхдийнх байна.")

    assert_writable(actor, child, enrollment)
    _check_term(enrollment, term)
    _check_domain(enrollment, domain)
    _check_level(enrollment, level)

    assessment = Assessment.objects.filter(
        child=child, enrollment=enrollment, domain=domain, term=term
    ).first()
    created = assessment is None
    if created:
        assessment = Assessment(
            kindergarten_id=enrollment.kindergarten_id,
            child=child, enrollment=enrollment, domain=domain, term=term,
        )

    assessment.level = level
    assessment.comment = comment
    assessment.assessed_by = actor
    assessment.assessed_at = timezone.now()

    return save_record(actor=actor, obj=assessment, created=created,
                       request=request)


@transaction.atomic
def save_group_assessments(*, actor, group, term, domain, entries,
                           request=None) -> int:
    """RFP §6.3 — the whole group from one screen, in one transaction.

    ``entries`` maps an enrollment id to a level id; ids the user may not
    reach are dropped rather than raising, because a grid submitted while
    another teacher moved a child should save the rest instead of failing
    entirely.

    Batch rather than save-on-click (§6.3 permits either): one service call,
    one transaction, one audit burst — and a teacher who changes their mind
    mid-screen has not already written five rows.
    """
    from apps.core.permissions import visible_children

    if not entries:
        return 0

    # Parsed before anything reaches the ORM: the keys are form field names
    # and the values are select-box contents, so both are attacker-supplied.
    # ``pk__in`` with a non-numeric string raises ValueError, which would be
    # a 500 on a request that should simply save nothing.
    wanted = {}
    for enrollment_id, level_id in entries.items():
        parsed = _as_id(enrollment_id), _as_id(level_id)
        if all(parsed):
            wanted[parsed[0]] = parsed[1]

    if not wanted:
        return 0

    enrollments = {
        enrollment.pk: enrollment
        for enrollment in Enrollment.objects.filter(
            pk__in=wanted.keys(),
            group=group,
            school_year=term.school_year,
            status=Enrollment.Status.ACTIVE,
            child__in=visible_children(actor),
        ).select_related("child")
    }

    levels = {level.pk: level for level in levels_for(group.kindergarten_id)}

    saved = 0
    for enrollment_id, level_id in wanted.items():
        enrollment = enrollments.get(enrollment_id)
        level = levels.get(level_id)
        if enrollment is None or level is None:
            continue

        save_assessment(
            actor=actor, child=enrollment.child, enrollment=enrollment,
            domain=domain, term=term, level=level, request=request,
        )
        saved += 1

    return saved


@transaction.atomic
def publish_term(*, actor, child, term, visible: bool, request=None) -> int:
    """RFP §2.3 — open (or close) a term's assessments to the guardians.

    §6.3's grid is a working draft filled in over several sittings. Showing
    a half-finished term to a family is worse than showing nothing, so the
    teacher decides when it is done.
    """
    _guard(actor, child)

    # Only this user's own kindergarten's rows. After a transfer the term
    # can hold assessments from both, and opening someone else's is not
    # this teacher's decision to make.
    rows = Assessment.objects.filter(
        child=child, term=term,
        kindergarten_id__in=visible_kindergartens(actor, child),
    )
    changed = 0
    for assessment in rows:
        if assessment.visible_to_parents == visible:
            continue
        assessment.visible_to_parents = visible
        save_record(actor=actor, obj=assessment, created=False, request=request)
        changed += 1
    return changed


@transaction.atomic
def ensure_default_terms(*, actor, school_year, request=None) -> list[Term]:
    """RFP §6.4 — give a school year its four terms.

    ``Assessment.term`` is required, so a year without terms means nothing
    can be assessed at all. Called when a school year is created and from
    ``seed_demo``; the dates are a starting point an administrator edits.
    """
    existing = list(Term.objects.filter(school_year=school_year).order_by("number"))
    if existing:
        return existing

    span = (school_year.ends_on - school_year.starts_on).days + 1
    step = max(span // 4, 1)

    terms = []
    for index, name in enumerate(TERM_NAMES):
        starts_on = school_year.starts_on + dt.timedelta(days=step * index)
        ends_on = (
            school_year.ends_on
            if index == len(TERM_NAMES) - 1
            else starts_on + dt.timedelta(days=step - 1)
        )
        term = Term(school_year=school_year, number=index + 1, name=name,
                    starts_on=starts_on, ends_on=ends_on,
                    kindergarten_id=school_year.kindergarten_id)
        terms.append(save_record(actor=actor, obj=term, created=True,
                                 request=request))
    return terms


@transaction.atomic
def save_term(*, actor, obj, created: bool, request=None) -> Term:
    """RFP §6.4 — validated from the administrator screen."""
    # The denormalized pointer always follows the school year; nothing else
    # may set it, or the §3.2 filter would point at the wrong tenant.
    obj.kindergarten_id = obj.school_year.kindergarten_id

    if obj.ends_on < obj.starts_on:
        raise ValidationError(
            {"ends_on": "Дуусах огноо эхлэх огнооноос хойш байх ёстой."}
        )

    year = obj.school_year
    if not (year.starts_on <= obj.starts_on and obj.ends_on <= year.ends_on):
        raise ValidationError(
            {"starts_on": "Улирал хичээлийн жилийн хугацаанд багтах ёстой."}
        )

    overlapping = (
        Term.objects.filter(school_year=year)
        .exclude(pk=obj.pk)
        .filter(starts_on__lte=obj.ends_on, ends_on__gte=obj.starts_on)
    )
    if overlapping.exists():
        # current_term() picks the first match, so overlapping terms would
        # make "which term is it?" depend on row order.
        raise ValidationError(
            {"starts_on": "Энэ хугацаа өөр улиралтай давхцаж байна."}
        )

    return save_record(actor=actor, obj=obj, created=created, request=request)


@transaction.atomic
def save_config(*, actor, obj, created: bool, request=None):
    """RFP §6.1, §6.2 — a domain, scale or level saved by an administrator.

    A director may only add to their own kindergarten's list; editing the
    shared system defaults is a superadmin action, or one kindergarten's
    rename would change the labels everywhere.
    """
    from apps.accounts.models import Role

    if obj.kindergarten_id is None and not actor.has_membership_in(
        [], roles=[Role.SUPERADMIN]
    ):
        raise ValidationError(
            "Системийн үндсэн жагсаалтыг зөвхөн системийн администратор засна."
        )

    return save_record(actor=actor, obj=obj, created=created, request=request)


def _as_id(value) -> int | None:
    """A positive integer, or ``None``. Never raises."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def resolve_term(school_year, term_id=None, on: dt.date | None = None) -> Term | None:
    """Which term a screen should show — the picked one, or today's.

    Returns ``None`` in the summer gap and before terms are configured; the
    screens render an explanation rather than raising, because a teacher
    opening the page in July is not an error.
    """
    if term_id:
        return Term.objects.filter(school_year=school_year, pk=term_id).first()
    return current_term(school_year, on)
