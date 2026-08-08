"""Child registration, transfers and archiving — RFP §2.2, §3.4, §3.5.

Views call these; none of this logic lives in a view (CLAUDE.md §2.1).
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.services import register_guardian
from apps.core.services import save_record, soft_delete

from .models import Child, Enrollment

__all__ = [
    "register_child",
    "update_child",
    "attach_guardian",
    "detach_guardian",
    "transfer_child",
    "archive_child",
    "current_enrollment",
]


def current_enrollment(child: Child) -> Enrollment | None:
    return (
        child.enrollments.filter(status=Enrollment.Status.ACTIVE)
        .select_related("group", "school_year")
        .first()
    )


@transaction.atomic
def register_child(*, actor, group, last_name, first_name, national_id, sex,
                   date_of_birth, enrolled_on=None, health_notes="",
                   request=None) -> Child:
    """RFP §2.2 — a teacher registers a child into their group.

    The enrollment is created in the same transaction. A child with no
    enrollment is the one case where authorization falls back to
    ``Child.kindergarten_id`` (CLAUDE.md §1.2), so leaving that window open
    across two requests would be a needless edge case.
    """
    child = Child(
        kindergarten_id=group.kindergarten_id,
        last_name=last_name.strip(),
        first_name=first_name.strip(),
        national_id=national_id.strip(),
        sex=sex,
        date_of_birth=date_of_birth,
        enrolled_on=enrolled_on or group.school_year.starts_on,
        health_notes=health_notes,
    )
    save_record(actor=actor, obj=child, created=True, request=request)

    enrollment = Enrollment(
        kindergarten_id=group.kindergarten_id,
        child=child,
        group=group,
        school_year=group.school_year,
        started_on=child.enrolled_on,
    )
    save_record(actor=actor, obj=enrollment, created=True, request=request)
    return child


@transaction.atomic
def update_child(*, actor, child, request=None, **fields) -> Child:
    """RFP §2.2 — edit a child's basic details.

    ``kindergarten`` is not editable here: it tracks the current enrollment
    and is changed only by :func:`transfer_child`.
    """
    editable = {
        "last_name", "first_name", "national_id", "sex", "date_of_birth",
        "enrolled_on", "left_on", "health_notes", "status",
    }
    unknown = set(fields) - editable
    if unknown:
        raise ValidationError(f"Засах боломжгүй талбар: {', '.join(sorted(unknown))}")

    for name, value in fields.items():
        setattr(child, name, value)
    return save_record(actor=actor, obj=child, created=False, request=request)


@transaction.atomic
def attach_guardian(*, actor, child, last_name, first_name, relation,
                    email=None, phone=None, is_primary=False, request=None):
    """RFP §3.5 — link a guardian to a child.

    Delegates to ``accounts.services.register_guardian``, which owns account
    creation and the invitation. Returns ``(guardianship, token, code)``;
    the token and code are ``None`` when an existing account was reused.
    """
    return register_guardian(
        actor=actor, child=child, last_name=last_name, first_name=first_name,
        relation=relation, email=email, phone=phone, is_primary=is_primary,
        request=request,
    )


@transaction.atomic
def detach_guardian(*, actor, guardianship, request=None):
    """Revoking access is a soft delete, so the trail survives — RFP §3.4."""
    return soft_delete(actor=actor, obj=guardianship, request=request)


@transaction.atomic
def transfer_child(*, actor, child, group, started_on, request=None) -> Enrollment:
    """RFP §3.4 — move a child to another group, year or kindergarten.

    Closes the active enrollment and opens a new one. The history is what
    keeps the previous teacher's access to the records they wrote
    (spec section 4.2), so the old row is never edited away.
    """
    active = current_enrollment(child)

    if active is not None:
        if active.group_id == group.id:
            raise ValidationError("Хүүхэд аль хэдийн энэ бүлэгт байна.")
        if started_on < active.started_on:
            raise ValidationError(
                "Шилжих огноо өмнөх бүртгэлийн эхэлсэн огнооноос өмнө байж болохгүй."
            )
        active.status = Enrollment.Status.TRANSFERRED
        active.ended_on = started_on
        save_record(actor=actor, obj=active, created=False, request=request)

    enrollment = Enrollment(
        kindergarten_id=group.kindergarten_id,
        child=child,
        group=group,
        school_year=group.school_year,
        started_on=started_on,
    )
    save_record(actor=actor, obj=enrollment, created=True, request=request)

    # Denormalized "currently attending" — for listing and filtering only.
    if child.kindergarten_id != group.kindergarten_id:
        child.kindergarten_id = group.kindergarten_id
        save_record(actor=actor, obj=child, created=False, request=request)

    return enrollment


@transaction.atomic
def archive_child(*, actor, child, left_on=None,
                  status=Child.Status.ARCHIVED, request=None) -> Child:
    """RFP §3.4 — archived, never deleted.

    Closes the active enrollment too, otherwise the child keeps appearing in
    their old group's lists.
    """
    active = current_enrollment(child)
    if active is not None:
        active.status = Enrollment.Status.ARCHIVED
        active.ended_on = left_on or active.ended_on
        save_record(actor=actor, obj=active, created=False, request=request)

    child.status = status
    child.left_on = left_on or child.left_on
    return save_record(actor=actor, obj=child, created=False, request=request)
