"""Writes for attendance — нэмэлт.md §1, §14, §17.

CLAUDE.md §2.1: views parse and render, this module decides. The §20-IV
mobile API will record attendance too, and a rule written inside a view would
be absent from that path.

Two things here are stricter than the rest of the system, both because this
table feeds a funding claim:

* **Every change records what it changed from.** §14 asks for
  `Хэн → Хэзээ → Юу → Өмнөх утга → Шинэ утга`. Creating a row is an
  ordinary audit entry; *altering* one carries the previous status in the
  audit metadata, because that is the edit a funding reconciliation has to be
  able to explain.
* **A day is written at most once.** `update_or_create` against the
  `(enrollment, date)` constraint, so re-submitting the group sheet corrects
  the existing rows rather than adding a second set.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.children.models import Enrollment
from apps.core.models import AuditAction
from apps.core.services import audit

from .models import Attendance, AttendanceStatus


def _validate(status: str, date: dt.date) -> None:
    if status not in AttendanceStatus.values:
        raise ValidationError(f"Ирцийн төлөв буруу байна: {status}")
    if date > dt.date.today():
        # Recording the future is how a month's funding gets claimed before
        # the children have attended it.
        raise ValidationError("Ирээдүйн өдрийн ирц бүртгэхгүй.")


@transaction.atomic
def record_attendance(*, actor, enrollment: Enrollment, date: dt.date,
                      status: str, note: str = "", request=None) -> Attendance:
    """Record — or correct — one child's day.

    Returns the row either way. The caller cannot tell from the return value
    whether it was created or amended, which is deliberate: both are "this is
    the attendance for that day", and the audit trail is where the difference
    is recorded.
    """
    _validate(status, date)

    existing = Attendance.objects.filter(
        enrollment=enrollment, date=date
    ).first()

    if existing is None:
        row = Attendance.objects.create(
            kindergarten=enrollment.kindergarten,
            enrollment=enrollment,
            child=enrollment.child,
            date=date,
            status=status,
            note=note,
            created_by=actor,
            updated_by=actor,
        )
        audit(action=AuditAction.CREATE, request=request, actor=actor,
              kindergarten=enrollment.kindergarten, child=enrollment.child,
              obj=row, date=date.isoformat(), new_status=status)
        return row

    if existing.status == status and existing.note == note:
        # Nothing changed. Writing an audit row here would bury the real
        # corrections under a pile of "saved the sheet again".
        return existing

    previous_status = existing.status
    previous_note = existing.note

    existing.status = status
    existing.note = note
    existing.updated_by = actor
    existing.save(update_fields=["status", "note", "updated_by", "updated_at"])

    # §14: the previous value is the whole point of the entry. A funding
    # reconciliation that finds a changed day needs to see what it was
    # before, not merely that someone touched it.
    audit(action=AuditAction.UPDATE, request=request, actor=actor,
          kindergarten=enrollment.kindergarten, child=enrollment.child,
          obj=existing, date=date.isoformat(),
          previous_status=previous_status, new_status=status,
          previous_note=previous_note, new_note=note)
    return existing


@transaction.atomic
def record_group_day(*, actor, group, date: dt.date, marks: dict,
                     request=None) -> list[Attendance]:
    """Record a whole group's day in one call — нэмэлт.md §1.

    ``marks`` maps ``enrollment_id`` to either a status string or a
    ``{"status": ..., "note": ...}`` mapping.

    The teacher's screen submits every child at once, so this runs in a single
    transaction: a sheet that saved eleven of twelve children would leave the
    twelfth silently unfunded, and the teacher would have no way to tell.

    Enrollment ids are resolved **against the group**, not taken on trust.
    A POST body is written by whoever sends it, so an id from another group —
    or another kindergarten — must not be writable through this screen.
    """
    enrollments = {
        e.pk: e
        for e in Enrollment.objects.filter(
            group=group, status=Enrollment.Status.ACTIVE
        ).select_related("child", "kindergarten")
    }

    written = []
    for raw_id, mark in marks.items():
        enrollment = enrollments.get(int(raw_id))
        if enrollment is None:
            # Not an error the teacher can act on: it means the posted id is
            # not in this group. Ignoring it is the safe half of the choice —
            # the alternative writes attendance for someone else's child.
            continue

        if isinstance(mark, dict):
            status, note = mark.get("status", ""), mark.get("note", "")
        else:
            status, note = mark, ""

        if not status:
            continue

        written.append(record_attendance(
            actor=actor, enrollment=enrollment, date=date,
            status=status, note=note, request=request,
        ))

    return written
