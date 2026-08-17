"""Attendance — нэмэлт.md §1, §14, §17.

Ordinary CRUD tests are the least of what matters here. Attendance is the
input to a state funding claim, so the tests worth writing are the ones that
pin the properties a wrong number would come from:

* a day cannot be recorded twice (double-counted funding),
* a correction says what it changed *from* (§14, and the only way a
  reconciliation can be explained),
* the group sheet cannot write outside its own group (a POST body is written
  by whoever sends it),
* the monthly counts stay free of funding policy, because that policy is not
  known yet — see `docs/FINANCE_SCOPE.md` D4.
"""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.attendance import selectors, services
from apps.attendance.models import Attendance, AttendanceStatus
from apps.children.models import Enrollment
from apps.core.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db

DAY = dt.date(2026, 3, 10)


@pytest.fixture
def enrollment(world):
    return Enrollment.objects.get(child=world["bataa"])


# ------------------------------------------------------------------ recording

def test_recording_a_day_stores_it(world, enrollment):
    row = services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )

    assert row.status == AttendanceStatus.PRESENT
    assert row.child == world["bataa"]
    assert row.kindergarten == enrollment.kindergarten


def test_the_same_day_cannot_produce_two_rows(world, enrollment):
    """Double submission is the cheapest way to double a funding claim.

    A teacher opening the sheet twice, or a form posted twice on a slow
    connection, must correct the day rather than add a second one.
    """
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.SICK,
    )

    assert Attendance.objects.filter(enrollment=enrollment, date=DAY).count() == 1
    assert Attendance.objects.get(enrollment=enrollment).status == (
        AttendanceStatus.SICK
    )


def test_the_future_cannot_be_recorded(world, enrollment):
    """Otherwise a month is claimed before it has been attended."""
    with pytest.raises(ValidationError):
        services.record_attendance(
            actor=world["dulmaa"], enrollment=enrollment,
            date=dt.date.today() + dt.timedelta(days=1),
            status=AttendanceStatus.PRESENT,
        )


def test_an_unknown_status_is_refused(world, enrollment):
    with pytest.raises(ValidationError):
        services.record_attendance(
            actor=world["dulmaa"], enrollment=enrollment, date=DAY,
            status="ирсэн_магадгүй",
        )


# ------------------------------------------------------------------ §14 audit

def test_a_correction_records_what_it_changed_from(world, enrollment):
    """§14: `Хэн → Хэзээ → Юу → Өмнөх утга → Шинэ утга`.

    "Someone edited this day" is not enough for a funding reconciliation. The
    previous value is what lets an accountant explain why a claimed figure
    and a submitted figure differ.
    """
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.ABSENT,
    )

    entry = AuditLog.objects.filter(action=AuditAction.UPDATE).latest("created_at")
    assert entry.metadata["previous_status"] == AttendanceStatus.PRESENT
    assert entry.metadata["new_status"] == AttendanceStatus.ABSENT
    assert entry.actor_user == world["dulmaa"]


def test_saving_an_unchanged_day_writes_no_audit_noise(world, enrollment):
    """A real correction must not be buried under "saved the sheet again"."""
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    before = AuditLog.objects.count()

    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )

    assert AuditLog.objects.count() == before


def test_the_row_history_is_kept(world, enrollment):
    """`simple_history` keeps the whole row, not just the audited fields."""
    row = services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.SICK,
    )

    assert row.history.count() == 2


# ------------------------------------------------------------- the group sheet

def test_a_whole_group_is_recorded_in_one_call(world):
    """§1 — the teacher marks the group from one screen."""
    enrollments = Enrollment.objects.filter(group=world["sunflower"])
    marks = {e.pk: AttendanceStatus.PRESENT for e in enrollments}

    written = services.record_group_day(
        actor=world["dulmaa"], group=world["sunflower"], date=DAY, marks=marks
    )

    assert len(written) == enrollments.count()
    assert all(row.status == AttendanceStatus.PRESENT for row in written)


def test_the_group_sheet_cannot_write_outside_its_group(world, make_child):
    """A POST body is written by whoever sends it.

    An enrollment id belonging to another group — or another kindergarten —
    must not be writable through this screen, however it arrived in the form.
    """
    # A child at the *other* kindergarten, so this covers the worst version
    # of the case: a cross-tenant write (RFP §3.2), not merely a neighbouring
    # group's.
    stranger = make_child(world["och"], world["petal"], first_name="Хөндлөн")
    outsider = Enrollment.objects.get(child=stranger)

    services.record_group_day(
        actor=world["dulmaa"], group=world["sunflower"], date=DAY,
        marks={outsider.pk: AttendanceStatus.PRESENT},
    )

    assert not Attendance.objects.filter(enrollment=outsider).exists()


def test_a_note_survives_the_group_sheet(world, enrollment):
    services.record_group_day(
        actor=world["dulmaa"], group=world["sunflower"], date=DAY,
        marks={enrollment.pk: {"status": AttendanceStatus.SICK,
                               "note": "Ханиад"}},
    )

    assert Attendance.objects.get(enrollment=enrollment).note == "Ханиад"


# ----------------------------------------------------------------- the reads

def test_the_day_sheet_shows_unmarked_children_too(world):
    """The silent failure: an unmarked child produces no error and no row.

    By the time anyone reconciles the month, the day is simply gone. The
    screen has to show who is still blank.
    """
    sheet = selectors.group_day_sheet(world["sunflower"], DAY)

    assert sheet, "the group has no active enrollments to show"
    assert all(entry["attendance"] is None for entry in sheet)
    assert len(selectors.unmarked_children(world["sunflower"], DAY)) == len(sheet)


def test_monthly_counts_report_every_status(world, enrollment):
    """Callers multiply by a weight table; a missing key would break that."""
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )

    counts = selectors.monthly_status_counts(
        child=world["bataa"], year=2026, month=3
    )

    assert set(counts) == set(AttendanceStatus.values)
    assert counts[AttendanceStatus.PRESENT] == 1
    assert counts[AttendanceStatus.SICK] == 0


def test_monthly_counts_stay_inside_their_month(world, enrollment):
    """A range that leaked into the next month would inflate every claim."""
    for day in (dt.date(2026, 3, 31), dt.date(2026, 4, 1)):
        services.record_attendance(
            actor=world["dulmaa"], enrollment=enrollment, date=day,
            status=AttendanceStatus.PRESENT,
        )

    march = selectors.monthly_status_counts(
        child=world["bataa"], year=2026, month=3
    )
    assert march[AttendanceStatus.PRESENT] == 1


def test_december_does_not_overflow_the_year(world, enrollment):
    """The month+1 arithmetic — December's end is 31 Dec, not month 13."""
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment,
        date=dt.date(2025, 12, 31), status=AttendanceStatus.PRESENT,
    )

    counts = selectors.monthly_status_counts(
        child=world["bataa"], year=2025, month=12
    )
    assert counts[AttendanceStatus.PRESENT] == 1


def test_monthly_counts_carry_no_funding_policy(world, enrollment):
    """The D4 decision must not be silently made here.

    Whether "Хагас өдөр" is worth a day, half a day or nothing is a
    government rule nobody has confirmed. This selector must report what
    happened and let the configurable funding rule decide what it is worth —
    so a half day appears under its own key, never folded into `present`.
    """
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.HALF_DAY,
    )

    counts = selectors.monthly_status_counts(
        child=world["bataa"], year=2026, month=3
    )

    assert counts[AttendanceStatus.HALF_DAY] == 1
    assert counts[AttendanceStatus.PRESENT] == 0


# ------------------------------------------------------------- authorization

def test_another_kindergartens_staff_read_nothing(world, enrollment, make_admin):
    """CLAUDE.md §4.1 at the selector level — RFP §3.2."""
    from apps.accounts.models import Role

    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    outsider = make_admin(world["och"], role=Role.ADMIN, username="att_outsider")

    assert not selectors.child_attendance(outsider, world["bataa"]).exists()


def test_a_guardian_reads_their_own_childs_attendance(world, enrollment):
    services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )

    assert selectors.child_attendance(
        world["bataa_mother"], world["bataa"]
    ).exists()


def test_soft_delete_hides_a_day(world, enrollment):
    """CLAUDE.md §3.3 — and the uniqueness constraint allows the re-record."""
    from apps.core.services import soft_delete

    row = services.record_attendance(
        actor=world["dulmaa"], enrollment=enrollment, date=DAY,
        status=AttendanceStatus.PRESENT,
    )
    soft_delete(actor=world["dulmaa"], obj=row)

    assert not Attendance.objects.filter(pk=row.pk).exists()
    assert Attendance.all_objects.filter(pk=row.pk).exists()
