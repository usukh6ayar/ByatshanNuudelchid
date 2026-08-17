"""Reads for attendance — нэмэлт.md §1, §17.

The important function here is :func:`monthly_status_counts`. It is what
turns attendance into money, and it is written to be **unopinionated about
policy**: it returns how many days fell in each status and stops there.

That is not indecision, it is the fix for an open question. Whether "Хагас
өдөр" counts as a funding day, half a day or nothing — and whether "Чөлөөтэй"
counts at all — is a government rule nobody has confirmed yet (see
`docs/FINANCE_SCOPE.md` D4). If this function returned a single
`funding_days` integer it would have to answer that, and a guessed answer
produces a claim that is precise, confident and wrong.

So the counts come out per status, and the funding rule — which an
administrator configures, per нэмэлт.md §4 — supplies the weights. When the
real rule arrives, nothing in this file changes.
"""

import datetime as dt

from django.db.models import Count

from apps.children.models import Enrollment
from apps.core.permissions import visible_children

from .models import Attendance, AttendanceStatus


def group_day_sheet(group, date: dt.date) -> list[dict]:
    """Every active child in the group, with that day's mark if it exists.

    Returns children *without* a mark too — the teacher's screen has to show
    who is still unrecorded, since an unmarked child is the one failure mode
    that produces no error anywhere and simply loses a funding day.
    """
    enrollments = (
        Enrollment.objects.filter(group=group, status=Enrollment.Status.ACTIVE)
        .select_related("child")
        .order_by("child__last_name", "child__first_name")
    )

    marked = {
        row.enrollment_id: row
        for row in Attendance.objects.filter(
            enrollment__in=enrollments, date=date
        )
    }

    return [
        {
            "enrollment": enrollment,
            "child": enrollment.child,
            "attendance": marked.get(enrollment.pk),
        }
        for enrollment in enrollments
    ]


def child_attendance(user, child, *, start=None, end=None):
    """One child's attendance, filtered to what this user may see.

    Goes through `visible_children` rather than taking the child on trust, so
    a caller that forgot its own permission check still cannot read another
    child's days (CLAUDE.md §1.1).
    """
    if not visible_children(user).filter(pk=child.pk).exists():
        return Attendance.objects.none()

    qs = Attendance.objects.filter(child=child).select_related("enrollment")
    if start is not None:
        qs = qs.filter(date__gte=start)
    if end is not None:
        qs = qs.filter(date__lte=end)
    return qs


def monthly_status_counts(*, child=None, group=None, kindergarten=None,
                          year: int, month: int) -> dict:
    """How many days fell in each status, for one month.

    The input to every downstream calculation — meal cost (§3), state funding
    (§4–6) and the monthly report. Returns every status as a key, including
    those with no days, so a caller can multiply by a weight table without
    checking for missing keys:

        {"present": 18, "sick": 2, "half_day": 1, "absent": 0, ...}

    Exactly one of ``child``, ``group`` or ``kindergarten`` scopes the query.
    """
    start = dt.date(year, month, 1)
    end = (
        dt.date(year + 1, 1, 1) if month == 12
        else dt.date(year, month + 1, 1)
    ) - dt.timedelta(days=1)

    qs = Attendance.objects.filter(date__gte=start, date__lte=end)

    if child is not None:
        qs = qs.filter(child=child)
    elif group is not None:
        qs = qs.filter(enrollment__group=group)
    elif kindergarten is not None:
        qs = qs.filter(kindergarten=kindergarten)
    else:
        raise ValueError(
            "monthly_status_counts needs a child, a group or a kindergarten"
        )

    counted = {
        row["status"]: row["n"]
        for row in qs.values("status").annotate(n=Count("id"))
    }

    # Every status present, so callers never branch on a missing key.
    return {status: counted.get(status, 0) for status in AttendanceStatus.values}


def unmarked_children(group, date: dt.date) -> list:
    """Children in the group with no attendance recorded for the date.

    Surfaced on the dashboard because a missing mark is silent: it produces no
    error, no warning and no row, and the day is simply gone by the time
    anyone reconciles the month.
    """
    return [
        entry["child"]
        for entry in group_day_sheet(group, date)
        if entry["attendance"] is None
    ]
