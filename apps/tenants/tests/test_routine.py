"""The group's daily routine — Үлгэрчилсэн дүрэм §7.8.

§7.8 requires each group to keep its own routine and §7.8.1 makes the
durations the group's own decision, because a Бага бүлэг naps longer than a
Бэлтгэл бүлэг. So this hangs off Group, is editable, and is seeded from the
regulation's example rather than fixed to it.
"""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.tenants import selectors, services
from apps.tenants.models import RoutineSlot

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def url_for(group):
    return reverse("tenants:group_routine", args=[group.pk])


@pytest.fixture
def routine(world, naran_admin_user):
    return services.apply_default_routine(actor=naran_admin_user,
                                          group=world["sunflower"])


# ------------------------------------------------------------------ §21.4

def test_a_teacher_from_another_group_gets_404(client, world, make_teacher,
                                               make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(url_for(world["sunflower"])).status_code == 404


def test_a_guardian_gets_404(client, world):
    login(client, world["bataa_mother"])

    assert client.get(url_for(world["sunflower"])).status_code == 404


def test_a_teacher_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(url_for(world["sunflower"])).status_code == 404


def test_the_groups_own_teacher_may_edit_it(client, world):
    """§7.8.1 makes the timings the group's decision, and the person who
    knows when these children settle is the one in the room."""
    login(client, world["dulmaa"])

    assert client.get(url_for(world["sunflower"])).status_code == 200


def test_a_director_may_edit_it(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    assert client.get(url_for(world["sunflower"])).status_code == 200


def test_a_director_cannot_edit_another_kindergartens_routine(
    client, world, make_admin
):
    login(client, make_admin(world["naran"], username="naran_boss"))

    assert client.get(url_for(world["petal"])).status_code == 404


# --------------------------------------------------------------- the rules

def test_the_defaults_are_the_regulations_day(world, routine):
    assert len(routine) == 10
    activities = [slot.activity for slot in routine]
    assert "Унтлага" in activities
    assert activities[0] == "Хүүхэд хүлээн авах"
    # Ordered by the clock, not by insertion.
    starts = [slot.starts_at for slot in selectors.routine_for(world["sunflower"])]
    assert starts == sorted(starts)


def test_the_defaults_refuse_a_second_pass(world, naran_admin_user, routine):
    """Merging would collide with what the teacher has already adjusted, and
    silently skipping would look like the button did nothing."""
    with pytest.raises(ValidationError):
        services.apply_default_routine(actor=naran_admin_user,
                                       group=world["sunflower"])

    assert RoutineSlot.objects.filter(group=world["sunflower"]).count() == 10


def test_a_block_ending_before_it_starts_is_refused(world, naran_admin_user):
    slot = RoutineSlot(
        kindergarten=world["naran"], group=world["sunflower"],
        starts_at=dt.time(11, 0), ends_at=dt.time(10, 0), activity="Буруу",
    )

    with pytest.raises(ValidationError):
        services.save_routine_slot(actor=naran_admin_user, obj=slot,
                                   created=True)


def test_an_overlapping_block_is_refused(world, naran_admin_user, routine):
    """A day where 13:00 belongs to two blocks has no answer to "what is
    happening now", which is the one question this exists to answer."""
    clash = RoutineSlot(
        kindergarten=world["naran"], group=world["sunflower"],
        starts_at=dt.time(13, 0), ends_at=dt.time(14, 0), activity="Давхцал",
    )

    with pytest.raises(ValidationError):
        services.save_routine_slot(actor=naran_admin_user, obj=clash,
                                   created=True)


def test_a_block_touching_another_at_its_edge_is_allowed(world,
                                                          naran_admin_user):
    """End-exclusive: 10:00–11:00 and 11:00–12:00 do not overlap."""
    first = RoutineSlot(kindergarten=world["naran"], group=world["sunflower"],
                        starts_at=dt.time(10, 0), ends_at=dt.time(11, 0),
                        activity="Эхнийх")
    services.save_routine_slot(actor=naran_admin_user, obj=first, created=True)

    second = RoutineSlot(kindergarten=world["naran"], group=world["sunflower"],
                         starts_at=dt.time(11, 0), ends_at=dt.time(12, 0),
                         activity="Дараагийнх")
    services.save_routine_slot(actor=naran_admin_user, obj=second, created=True)

    assert RoutineSlot.objects.filter(group=world["sunflower"]).count() == 2


def test_the_kindergarten_follows_the_group(world, naran_admin_user):
    """§3.2 — a block filed against the wrong tenant is invisible to every
    screen's filter, so nothing but the group may set it."""
    slot = RoutineSlot(
        kindergarten=world["och"],          # wrong on purpose
        group=world["sunflower"],
        starts_at=dt.time(9, 0), ends_at=dt.time(10, 0), activity="Тест",
    )

    services.save_routine_slot(actor=naran_admin_user, obj=slot, created=True)

    slot.refresh_from_db()
    assert slot.kindergarten_id == world["naran"].pk


# ------------------------------------------------------------------- "now"

@pytest.mark.parametrize("clock,expected", [
    ("07:00", None),                 # before the day starts
    ("09:00", "Өглөөний дасгал"),
    ("13:45", "Унтлага"),
    ("15:20", None),                 # the gap the regulation leaves
    ("22:00", None),                 # after the day ends
])
def test_routine_now_answers_only_inside_a_block(world, routine, clock,
                                                 expected):
    """``None`` is a real answer. A screen that invents a current activity
    for 07:00 lies to a teacher who can see the room is empty."""
    found = selectors.routine_now(world["sunflower"],
                                  dt.time.fromisoformat(clock))

    assert (found.activity if found else None) == expected


def test_a_group_with_no_routine_has_no_now(world):
    assert selectors.routine_now(world["sunflower"]) is None


# ------------------------------------------------------------------ screens

def test_the_screen_lists_the_day(client, world, routine):
    login(client, world["dulmaa"])

    html = client.get(url_for(world["sunflower"])).content.decode()

    assert "Унтлага" in html
    assert "13:30" in html


def test_a_teacher_adds_a_block(client, world):
    login(client, world["dulmaa"])

    response = client.post(url_for(world["sunflower"]), {
        "starts_at": "09:00", "ends_at": "09:30",
        "activity": "Усан сан", "note": "Даваа гарагт",
    })

    assert response.status_code == 302
    slot = RoutineSlot.objects.get(group=world["sunflower"])
    assert slot.activity == "Усан сан"
    assert slot.kindergarten_id == world["naran"].pk


def test_an_overlapping_block_is_explained_not_crashed(client, world, routine):
    login(client, world["dulmaa"])

    response = client.post(url_for(world["sunflower"]), {
        "starts_at": "13:00", "ends_at": "14:00", "activity": "Давхцал",
    })

    assert response.status_code == 200
    assert "давхцаж" in response.content.decode()
    assert not RoutineSlot.objects.filter(activity="Давхцал").exists()


def test_a_block_is_archived_not_dropped(client, world, routine):
    """CLAUDE.md §3.3 — no hard deletes anywhere."""
    login(client, world["dulmaa"])
    slot = RoutineSlot.objects.filter(group=world["sunflower"]).first()

    client.post(url_for(world["sunflower"]),
                {"action": "delete", "slot": slot.pk})

    assert not RoutineSlot.objects.filter(pk=slot.pk).exists()
    assert RoutineSlot.all_objects.get(pk=slot.pk).deleted_at is not None


def test_a_teacher_cannot_delete_another_groups_block(client, world, routine,
                                                       make_group,
                                                       make_teacher):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)
    slot = RoutineSlot.objects.filter(group=world["sunflower"]).first()

    assert client.post(url_for(other),
                       {"action": "delete", "slot": slot.pk}).status_code == 302
    assert RoutineSlot.objects.filter(pk=slot.pk).exists()
