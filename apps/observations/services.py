"""Observation writes — RFP §5.1, §5.2, §5.4. All rules live here.

A teacher's observation and a parent's are the same table with different
defaults, not two code paths: §5.4 asks the teacher to review, include or
exclude a parent's submission, which only works if both are the same record
with a ``source`` column to tell them apart.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.assessment.selectors import levels_for
from apps.core.permissions import (
    can_access_child,
    can_record_for_child,
    is_guardian_of,
    visible_kindergartens,
)
from apps.core.services import save_record, soft_delete

from .models import Observation, ObservationDomain
from .selectors import types_for

__all__ = [
    "assert_own_record",
    "create_observation",
    "create_group_observation",
    "update_observation",
    "delete_observation",
    "review_observation",
    "set_domains",
]

# §5.1's own list of what an observation holds. Named here so a view cannot
# quietly write a field the service never validated.
TEXT_FIELDS = {
    "activity_name", "situation", "child_did", "child_said",
    "teacher_comment", "next_steps",
}


def _recording_enrollment(child):
    """Shared with assessment — spec section 4.2 explains why."""
    from apps.assessment.services import recording_enrollment

    return recording_enrollment(child)


def assert_own_record(actor, observation) -> None:
    """The record must belong to a kindergarten this user is part of.

    A teacher keeps access to a transferred child (spec section 4.2), which
    is what lets them correct their own history. It must not also let them
    edit what the *new* kindergarten's staff wrote about that child.
    """
    if observation.kindergarten_id not in visible_kindergartens(
        actor, observation.child
    ):
        raise PermissionDenied


def _check_type(enrollment, type):
    """The type must belong to the system list or this kindergarten's."""
    if type is None:
        raise ValidationError("Ажиглалтын төрлийг сонгоно уу.")

    allowed = types_for(enrollment.kindergarten_id).values_list("pk", flat=True)
    if type.pk not in set(allowed):
        raise ValidationError("Энэ цэцэрлэгт хамаарахгүй ажиглалтын төрөл байна.")


def _guard(actor, child, source):
    """Who may file which kind of observation — RFP §5.1, §5.4.

    A guardian submits ``source=parent`` and nothing else. Letting them post
    a teacher observation would put words in a teacher's mouth in the record
    the family later receives as a PDF.
    """
    if source == Observation.Source.PARENT:
        if not can_access_child(actor, child):
            raise PermissionDenied
        return

    if not can_record_for_child(actor, child):
        raise PermissionDenied


@transaction.atomic
def create_observation(*, actor, child, type, observed_on,
                       source=Observation.Source.TEACHER,
                       domains=None, visible_to_parents=None,
                       include_in_report=True, enrollment=None,
                       request=None, **fields) -> Observation:
    """RFP §5.1 — record an observation.

    A parent's submission starts as ``pending``: §5.4 gives the teacher the
    decisions about revision and about inclusion in the report, and a record
    that is already approved has skipped both.
    """
    _guard(actor, child, source)

    unknown = set(fields) - TEXT_FIELDS
    if unknown:
        raise ValidationError(
            f"Тодорхойгүй талбар: {', '.join(sorted(unknown))}"
        )

    enrollment = enrollment or _recording_enrollment(child)
    if enrollment.child_id != child.pk:
        raise ValidationError("Бүртгэл нь өөр хүүхдийнх байна.")

    from apps.assessment.services import assert_writable

    assert_writable(actor, child, enrollment)
    _check_type(enrollment, type)

    if observed_on is None:
        raise ValidationError("Ажиглалтын огноог оруулна уу.")
    if observed_on > timezone.localdate():
        raise ValidationError("Ажиглалтын огноо ирээдүйд байж болохгүй.")

    is_parent = source == Observation.Source.PARENT

    observation = Observation(
        kindergarten_id=enrollment.kindergarten_id,
        child=child,
        enrollment=enrollment,
        type=type,
        source=source,
        observed_on=observed_on,
        # A parent's own note is visible to them by definition; a teacher
        # chooses, and §5.1's default is open.
        visible_to_parents=(
            True if visible_to_parents is None else bool(visible_to_parents)
        ),
        include_in_report=bool(include_in_report),
        review_status=(
            Observation.ReviewStatus.PENDING if is_parent
            else Observation.ReviewStatus.APPROVED
        ),
    )
    for name, value in fields.items():
        setattr(observation, name, value)

    save_record(actor=actor, obj=observation, created=True, request=request)

    if domains:
        set_domains(actor=actor, observation=observation, domains=domains,
                    request=request)

    return observation


@transaction.atomic
def update_observation(*, actor, observation, domains=None,
                       visible_to_parents=None, include_in_report=None,
                       type=None, observed_on=None, request=None,
                       **fields) -> Observation:
    """RFP §5.1 — edit an observation.

    Only its author, or staff at the kindergarten it belongs to, may edit
    it. A guardian may correct their own submission while it waits for
    review; once a teacher has approved it, editing would change a record
    that has already been judged.
    """
    child = observation.child
    assert_own_record(actor, observation)
    staff = can_record_for_child(actor, child)

    if not staff:
        if observation.source != Observation.Source.PARENT or not is_guardian_of(
            actor, child
        ):
            raise PermissionDenied
        if observation.created_by_id != actor.pk:
            raise PermissionDenied
        if observation.review_status == Observation.ReviewStatus.APPROVED:
            raise ValidationError(
                "Багш баталсан ажиглалтыг засах боломжгүй. "
                "Багштайгаа холбогдоно уу."
            )
        # §5.4 gives the teacher these decisions — whether the note reaches
        # the family's report, whether it is visible at all, and which
        # development domains it evidences. A guardian editing their own
        # text must not be able to change them, even by posting the fields
        # directly.
        visible_to_parents = None
        include_in_report = None
        domains = None

    unknown = set(fields) - TEXT_FIELDS
    if unknown:
        raise ValidationError(
            f"Тодорхойгүй талбар: {', '.join(sorted(unknown))}"
        )

    if type is not None:
        _check_type(observation.enrollment, type)
        observation.type = type

    if observed_on is not None:
        if observed_on > timezone.localdate():
            raise ValidationError("Ажиглалтын огноо ирээдүйд байж болохгүй.")
        observation.observed_on = observed_on

    if visible_to_parents is not None:
        observation.visible_to_parents = bool(visible_to_parents)
    if include_in_report is not None:
        observation.include_in_report = bool(include_in_report)

    for name, value in fields.items():
        setattr(observation, name, value)

    save_record(actor=actor, obj=observation, created=False, request=request)

    if domains is not None:
        set_domains(actor=actor, observation=observation, domains=domains,
                    request=request)

    return observation


@transaction.atomic
def delete_observation(*, actor, observation, request=None) -> Observation:
    """RFP §3.4 — archived, never removed (CLAUDE.md §3.3)."""
    assert_own_record(actor, observation)
    if not can_record_for_child(actor, observation.child):
        raise PermissionDenied

    for link in observation.domain_links.all():
        soft_delete(actor=actor, obj=link, request=request)

    return soft_delete(actor=actor, obj=observation, request=request)


@transaction.atomic
def review_observation(*, actor, observation, status, note="",
                       include_in_report=None, request=None) -> Observation:
    """RFP §5.4 — the teacher approves, or asks for a revision.

    Only applies to what a parent submitted: a teacher's own observation has
    nobody above them to approve it, and a review trail there would be
    theatre.
    """
    assert_own_record(actor, observation)
    if not can_record_for_child(actor, observation.child):
        raise PermissionDenied

    if observation.source != Observation.Source.PARENT:
        raise ValidationError("Зөвхөн эцэг эхийн ажиглалтыг хянана.")

    if status not in Observation.ReviewStatus.values:
        raise ValidationError("Тодорхойгүй төлөв.")

    observation.review_status = status
    observation.review_note = note
    observation.reviewed_by = actor
    observation.reviewed_at = timezone.now()

    if include_in_report is not None:
        observation.include_in_report = bool(include_in_report)

    return save_record(actor=actor, obj=observation, created=False,
                       request=request)


@transaction.atomic
def set_domains(*, actor, observation, domains, request=None) -> list:
    """Replace the observation's development domains — spec section 6.3.

    ``domains`` is an iterable of ``(domain, level_or_None)`` pairs, or bare
    domains. Replacing rather than appending: the form posts the complete
    set every time, so a domain the teacher unticked has to disappear.
    """
    from apps.assessment.selectors import domains_for

    allowed_domains = {
        domain.pk: domain
        for domain in domains_for(observation.kindergarten_id)
    }
    allowed_levels = {
        level.pk: level for level in levels_for(observation.kindergarten_id)
    }

    wanted = {}
    for entry in domains:
        domain, level = entry if isinstance(entry, tuple) else (entry, None)
        if domain is None or domain.pk not in allowed_domains:
            raise ValidationError("Энэ цэцэрлэгт хамаарахгүй хөгжлийн чиглэл байна.")
        if level is not None and level.pk not in allowed_levels:
            raise ValidationError("Энэ цэцэрлэгт хамаарахгүй үнэлгээний түвшин байна.")
        wanted[domain.pk] = level

    existing = {link.domain_id: link for link in observation.domain_links.all()}

    for domain_id, link in existing.items():
        if domain_id not in wanted:
            soft_delete(actor=actor, obj=link, request=request)

    links = []
    for domain_id, level in wanted.items():
        link = existing.get(domain_id)
        created = link is None
        if created:
            link = ObservationDomain(
                kindergarten_id=observation.kindergarten_id,
                observation=observation,
                domain=allowed_domains[domain_id],
            )
        link.level = level
        links.append(
            save_record(actor=actor, obj=link, created=created, request=request)
        )

    return links


@transaction.atomic
def create_group_observation(*, actor, group, type, observed_on, entries,
                             domains=None, visible_to_parents=None,
                             include_in_report=True, request=None,
                             **fields) -> list[Observation]:
    """RFP §5.2's "үйл ажиллагаанд суурилсан ажиглалт", written once.

    A teacher runs one activity — "Блокоор барих" — with eight children and
    then has the nap hour to record it. Writing the same activity, date and
    domains eight times is most of that hour; the §6.3 grid already solved
    the same shape for assessments and this is its counterpart.

    ``entries`` maps an enrollment id to that child's own note, which is the
    part that genuinely differs per child. Everything else is shared.

    Ids the teacher may not reach are dropped rather than raising, matching
    ``save_group_assessments``: a form submitted while another teacher moved
    a child should record the rest instead of failing whole.
    """
    from apps.assessment.services import _as_id
    from apps.children.models import Enrollment
    from apps.core.permissions import visible_children

    if not entries:
        return []

    # Both halves are attacker-supplied — the keys are form field names and
    # the values are free text. Parse before anything reaches the ORM.
    wanted = {}
    for enrollment_id, note in entries.items():
        parsed = _as_id(enrollment_id)
        if parsed:
            wanted[parsed] = (note or "").strip()

    if not wanted:
        return []

    enrollments = (
        Enrollment.objects.filter(
            pk__in=wanted,
            group=group,
            status=Enrollment.Status.ACTIVE,
            child__in=visible_children(actor),
        )
        .select_related("child")
        .order_by("child__last_name", "child__first_name")
    )

    created = []
    for enrollment in enrollments:
        note = wanted[enrollment.pk]
        # The per-child note lands in child_did — §5.1's "хүүхдийн хийсэн
        # үйлдэл" is what a teacher writes about one child in a shared
        # activity. A blank note still records that the child took part.
        per_child = dict(fields)
        if note:
            per_child["child_did"] = note

        created.append(create_observation(
            actor=actor,
            child=enrollment.child,
            enrollment=enrollment,
            type=type,
            observed_on=observed_on,
            domains=domains,
            visible_to_parents=visible_to_parents,
            include_in_report=include_in_report,
            request=request,
            **per_child,
        ))

    return created
