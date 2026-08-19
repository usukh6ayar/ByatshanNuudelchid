"""The attendance register screen — нэмэлт.md §1, CLAUDE.md §4.1.

`test_attendance.py` already pins the rules: a day cannot be double-counted,
a correction records what it changed from, and the group sheet cannot write
outside its own group. None of that proves a *request* is handled correctly.

This file is about the view. The three authorization tests are mandatory for
any new screen that touches child data (CLAUDE.md §4.1) and they go through
the HTTP client on purpose: a view that forgets its check passes every
function-level test in the module next door.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.attendance.models import Attendance, AttendanceStatus
from apps.children.models import Enrollment

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"
DAY = dt.date(2026, 3, 10)


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def register_url(group):
    return reverse("attendance:group_register", args=[group.pk])


# ------------------------------------------------------- §4.1 authorization


def test_a_teacher_from_another_group_gets_404(client, world):
    """`oyun` teaches at a different kindergarten's group entirely."""
    login(client, world["oyun"])

    assert client.get(register_url(world["sunflower"])).status_code == 404


def test_a_guardian_gets_404(client, world):
    """§2.2 — recording attendance is staff work. A guardian reaching the URL
    must not learn that the group exists."""
    login(client, world["bataa_mother"])

    assert client.get(register_url(world["sunflower"])).status_code == 404


def test_a_user_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(register_url(world["petal"])).status_code == 200
    assert client.get(register_url(world["sunflower"])).status_code == 404


def test_posting_to_another_groups_register_gets_404(client, world):
    """The GET check is not the whole screen — the POST writes."""
    login(client, world["oyun"])
    enrollment = Enrollment.objects.get(child=world["bataa"])

    response = client.post(register_url(world["sunflower"]), {
        "date": DAY.isoformat(),
        f"status_{enrollment.pk}": AttendanceStatus.PRESENT,
    })

    assert response.status_code == 404
    assert not Attendance.objects.filter(enrollment=enrollment).exists()


# ------------------------------------------------------------- the register


def test_the_sheet_lists_every_active_child_including_unmarked(client, world):
    """An unmarked child is the one failure that writes no row and raises no
    error, so the sheet has to show them."""
    login(client, world["dulmaa"])

    response = client.get(register_url(world["sunflower"]), {"date": DAY.isoformat()})
    body = response.content.decode()

    assert response.status_code == 200
    assert world["bataa"].full_name in body
    assert world["saraa"].full_name in body
    assert len(response.context["rows"]) == 2
    assert response.context["unmarked"] == 2


def test_saving_the_sheet_records_the_marks(client, world):
    login(client, world["dulmaa"])
    bataa = Enrollment.objects.get(child=world["bataa"])
    saraa = Enrollment.objects.get(child=world["saraa"])

    client.post(register_url(world["sunflower"]), {
        "date": DAY.isoformat(),
        f"status_{bataa.pk}": AttendanceStatus.PRESENT,
        f"status_{saraa.pk}": AttendanceStatus.SICK,
        f"note_{saraa.pk}": "Ханиад",
    })

    assert Attendance.objects.get(enrollment=bataa, date=DAY).status == "present"
    sick = Attendance.objects.get(enrollment=saraa, date=DAY)
    assert sick.status == "sick"
    assert sick.note == "Ханиад"


def test_saving_the_same_day_twice_corrects_rather_than_duplicates(client, world):
    """`record_attendance` uses the (enrollment, date) constraint. A teacher
    who fixes a mistake must not produce a second funded day."""
    login(client, world["dulmaa"])
    enrollment = Enrollment.objects.get(child=world["bataa"])
    url = register_url(world["sunflower"])

    client.post(url, {"date": DAY.isoformat(),
                      f"status_{enrollment.pk}": AttendanceStatus.ABSENT})
    client.post(url, {"date": DAY.isoformat(),
                      f"status_{enrollment.pk}": AttendanceStatus.PRESENT})

    rows = Attendance.objects.filter(enrollment=enrollment, date=DAY)
    assert rows.count() == 1
    assert rows.first().status == "present"


def test_a_child_from_another_group_cannot_be_marked_through_this_sheet(
    client, world, make_child,
):
    """The ids come from a POST body, which is written by whoever sends it.
    `record_group_day` resolves each one against the group."""
    login(client, world["dulmaa"])
    make_child(world["och"], world["petal"], first_name="Хөрш")
    outsider = Enrollment.objects.get(group=world["petal"])

    client.post(register_url(world["sunflower"]), {
        "date": DAY.isoformat(),
        f"status_{outsider.pk}": AttendanceStatus.PRESENT,
    })

    assert not Attendance.objects.filter(enrollment=outsider).exists()


def test_a_future_day_is_refused(client, world):
    """Recording the future is how a month's funding is claimed before the
    children have attended it — the service refuses, and the screen has to
    surface that rather than swallow it."""
    login(client, world["dulmaa"])
    enrollment = Enrollment.objects.get(child=world["bataa"])
    tomorrow = dt.date.today() + dt.timedelta(days=1)

    client.post(register_url(world["sunflower"]), {
        "date": tomorrow.isoformat(),
        f"status_{enrollment.pk}": AttendanceStatus.PRESENT,
    })

    assert not Attendance.objects.filter(date=tomorrow).exists()


def test_the_sheet_does_not_query_once_per_child(client, world, make_child):
    """CLAUDE.md §3.5 — the register is the screen opened every morning, and
    its cost must not scale with the size of the group."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])
    url = register_url(world["sunflower"])

    with CaptureQueriesContext(connection) as first:
        client.get(url)
    baseline = len(first.captured_queries)

    for index in range(6):
        make_child(world["naran"], world["sunflower"], first_name=f"Ирц{index}")

    with CaptureQueriesContext(connection) as second:
        response = client.get(url)

    assert len(response.context["rows"]) == 8
    assert len(second.captured_queries) == baseline
