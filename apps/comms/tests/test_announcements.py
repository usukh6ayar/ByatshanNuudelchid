"""Announcements — RFP §8.1, and the §21 targeting rules.

The dangerous mistake here is not a broken screen. It is an announcement
about one family reaching another, so most of what follows is about who a
message reaches rather than about what it says.
"""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.comms import selectors, services
from apps.comms.models import Announcement, AnnouncementRead, AnnouncementTarget

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def make(world, actor=None, *, publish=True, groups=None, children=None,
         title="Эцэг эхийн хурал", important=False):
    actor = actor or world["dulmaa"]
    announcement = services.save_announcement(
        actor=actor, kindergarten_id=world["naran"].pk,
        title=title, body="Пүрэв гарагт 18:00 цагт.", is_important=important,
    )
    if groups or children:
        services.set_targets(actor=actor, announcement=announcement,
                             groups=[g.pk for g in (groups or [])],
                             children=[c.pk for c in (children or [])])
    if publish:
        services.publish(actor=actor, announcement=announcement)
    return announcement


# ------------------------------------------------------------------ targeting

def test_an_untargeted_announcement_reaches_the_whole_kindergarten(world):
    """No target rows means everyone — the common case needs no controls."""
    announcement = make(world)

    assert announcement in selectors.for_guardian(world["bataa_mother"])


def test_a_group_announcement_reaches_that_groups_families(world):
    announcement = make(world, groups=[world["sunflower"]])

    assert announcement in selectors.for_guardian(world["bataa_mother"])


def test_a_group_announcement_does_not_reach_another_group(world, make_group,
                                                           make_child,
                                                           make_guardian):
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    other_child = make_child(world["naran"], other_group, first_name="Гадны")
    other_parent = make_guardian(other_child, world["naran"],
                                 username="other_parent")
    announcement = make(world, groups=[world["sunflower"]])

    assert announcement not in selectors.for_guardian(other_parent)


def test_a_child_announcement_reaches_only_that_family(world, make_guardian):
    saraa_parent = make_guardian(world["saraa"], world["naran"],
                                 username="saraa_mother")
    announcement = make(world, children=[world["bataa"]])

    assert announcement in selectors.for_guardian(world["bataa_mother"])
    assert announcement not in selectors.for_guardian(saraa_parent)


def test_another_kindergartens_families_never_see_it(world, make_child,
                                                     make_guardian):
    och_child = make_child(world["och"], world["petal"], first_name="Очны")
    och_parent = make_guardian(och_child, world["och"], username="och_parent")
    announcement = make(world)

    assert announcement not in selectors.for_guardian(och_parent)


def test_a_draft_reaches_nobody(world):
    announcement = make(world, publish=False)

    assert announcement not in selectors.for_guardian(world["bataa_mother"])


def test_a_future_announcement_is_not_shown_yet(world):
    """§8.1's эхлэх огноо — written on Monday, shown on Thursday."""
    announcement = services.save_announcement(
        actor=world["dulmaa"], kindergarten_id=world["naran"].pk,
        title="Ирээдүйн", body="Дараа сарын хуваарь.",
        starts_on=dt.date.today() + dt.timedelta(days=7),
    )
    services.publish(actor=world["dulmaa"], announcement=announcement)

    assert announcement not in selectors.for_guardian(world["bataa_mother"])
    assert announcement in selectors.for_guardian(
        world["bataa_mother"], on=dt.date.today() + dt.timedelta(days=8)
    )


def test_an_expired_announcement_drops_off(world):
    announcement = services.save_announcement(
        actor=world["dulmaa"], kindergarten_id=world["naran"].pk,
        title="Өнгөрсөн", body="Өчигдрийн хурал.",
        starts_on=dt.date.today() - dt.timedelta(days=10),
        ends_on=dt.date.today() - dt.timedelta(days=1),
    )
    services.publish(actor=world["dulmaa"], announcement=announcement)

    assert announcement not in selectors.for_guardian(world["bataa_mother"])


# ------------------------------------------------------------------ §21 views

def test_a_guardian_cannot_open_another_kindergartens_announcement(
    client, world, make_child, make_guardian
):
    och_child = make_child(world["och"], world["petal"], first_name="Очны")
    och_parent = make_guardian(och_child, world["och"], username="och_parent")
    announcement = make(world)
    login(client, och_parent)

    response = client.get(reverse("comms:detail", args=[announcement.pk]))

    assert response.status_code == 404


def test_a_guardian_cannot_open_a_draft(client, world):
    announcement = make(world, publish=False)
    login(client, world["bataa_mother"])

    assert client.get(
        reverse("comms:detail", args=[announcement.pk])
    ).status_code == 404


def test_a_guardian_cannot_create_one(client, world):
    """§8.1 — an announcement is the kindergarten speaking."""
    login(client, world["bataa_mother"])

    response = client.post(reverse("comms:create"), {
        "title": "Эцэг эхийн зарлал", "body": "Текст",
    })

    assert response.status_code == 404
    assert not Announcement.objects.exists()


def test_a_teacher_cannot_publish_into_another_kindergarten(world):
    with pytest.raises(PermissionDenied):
        services.save_announcement(
            actor=world["oyun"], kindergarten_id=world["naran"].pk,
            title="Гаднаас", body="Текст",
        )


def test_a_teacher_cannot_edit_a_colleagues_announcement(world, make_teacher):
    colleague = make_teacher(world["naran"], world["sunflower"],
                             username="colleague")
    announcement = make(world)

    with pytest.raises(PermissionDenied):
        services.save_announcement(
            actor=colleague, kindergarten_id=world["naran"].pk,
            announcement=announcement, title="Өөрчилсөн", body="Текст",
        )


def test_a_director_may_edit_any_of_their_kindergartens(world,
                                                        naran_admin_user):
    announcement = make(world)

    services.save_announcement(
        actor=naran_admin_user, kindergarten_id=world["naran"].pk,
        announcement=announcement, title="Захирал зассан", body="Текст",
    )

    announcement.refresh_from_db()
    assert announcement.title == "Захирал зассан"


def test_targeting_a_child_you_cannot_reach_is_refused(world, make_child):
    """A mis-addressed announcement is a message delivered to the wrong
    family, so a bad id fails loudly rather than being dropped."""
    och_child = make_child(world["och"], world["petal"], first_name="Очны")
    announcement = make(world, publish=False)

    with pytest.raises(ValidationError):
        services.set_targets(actor=world["dulmaa"], announcement=announcement,
                             children=[och_child.pk])

    assert not AnnouncementTarget.objects.filter(
        announcement=announcement
    ).exists()


def test_unticking_a_group_removes_the_target(world, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    world["dulmaa"].memberships.get()      # already assigned to sunflower
    announcement = make(world, publish=False, groups=[world["sunflower"]])
    assert announcement.targets.count() == 1

    services.set_targets(actor=world["dulmaa"], announcement=announcement,
                         groups=[])

    assert announcement.targets.count() == 0
    assert other  # kept for the assertion above to be meaningful


# ------------------------------------------------------------------ read state

def test_reading_marks_it_read(client, world):
    announcement = make(world)
    login(client, world["bataa_mother"])

    assert selectors.unread_count(world["bataa_mother"]) == 1

    client.get(reverse("comms:detail", args=[announcement.pk]))

    assert selectors.unread_count(world["bataa_mother"]) == 0
    assert AnnouncementRead.objects.filter(
        announcement=announcement, user=world["bataa_mother"]
    ).exists()


def test_marking_read_twice_is_harmless(world):
    announcement = make(world)

    services.mark_read(actor=world["bataa_mother"], announcement=announcement)
    services.mark_read(actor=world["bataa_mother"], announcement=announcement)

    assert AnnouncementRead.objects.filter(announcement=announcement).count() == 1


def test_the_explicit_button_marks_it_read(client, world):
    announcement = make(world)
    login(client, world["bataa_mother"])

    response = client.post(reverse("comms:mark_read", args=[announcement.pk]))

    assert response.status_code == 302
    assert selectors.unread_count(world["bataa_mother"]) == 0


def test_a_teacher_reading_does_not_consume_the_families_badge(client, world):
    announcement = make(world)
    login(client, world["dulmaa"])
    client.get(reverse("comms:detail", args=[announcement.pk]))

    assert selectors.unread_count(world["bataa_mother"]) == 1


def test_the_teacher_sees_who_read_it(client, world):
    announcement = make(world)
    services.mark_read(actor=world["bataa_mother"], announcement=announcement)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("comms:detail", args=[announcement.pk])
    ).content.decode()

    assert str(world["bataa_mother"]) in body
    # The count moved from the heading ("Уншсан — 1") into a badge beneath it
    # with the 2026-08-16 redesign. Same fact, stated in words rather than
    # punctuation; the assertion is no weaker.
    assert "1 хүн уншсан" in body


def test_the_unread_count_does_not_query_per_announcement(world):
    """CLAUDE.md §3.5 — the badge is on every page a guardian opens."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def count_with(extra: int) -> int:
        for index in range(extra):
            make(world, title=f"Мэдэгдэл {index}")
        with CaptureQueriesContext(connection) as captured:
            selectors.unread_count(world["bataa_mother"])
        return len(captured)

    assert count_with(2) == count_with(10)


# ------------------------------------------------------------------ §3.4

def test_archiving_hides_it_from_families(world):
    announcement = make(world)

    services.delete_announcement(actor=world["dulmaa"],
                                 announcement=announcement)

    assert announcement not in selectors.for_guardian(world["bataa_mother"])
    assert not Announcement.objects.filter(pk=announcement.pk).exists()
    assert Announcement.all_objects.get(pk=announcement.pk).deleted_at


# ------------------------------------------------------------------ screens

def test_the_screens_render_for_both_roles(client, world):
    announcement = make(world, groups=[world["sunflower"]], important=True)

    for user in [world["dulmaa"], world["bataa_mother"]]:
        login(client, user)
        assert client.get(reverse("comms:list")).status_code == 200, user
        assert client.get(
            reverse("comms:detail", args=[announcement.pk])
        ).status_code == 200, user


def test_a_teacher_creates_one_end_to_end(client, world):
    login(client, world["dulmaa"])

    assert client.get(reverse("comms:create")).status_code == 200

    response = client.post(reverse("comms:create"), {
        "title": "Ангийн аялал",
        "body": "Баасан гарагт 09:00 цагт цугларна.",
        "groups": [str(world["sunflower"].pk)],
        "is_important": "on",
        "publish": "on",
    })

    assert response.status_code == 302
    announcement = Announcement.objects.get()
    assert announcement.status == Announcement.Status.PUBLISHED
    assert announcement.is_important is True
    assert announcement.author == world["dulmaa"]
    assert announcement in selectors.for_guardian(world["bataa_mother"])


def test_saving_without_publishing_leaves_a_draft(client, world):
    login(client, world["dulmaa"])

    client.post(reverse("comms:create"), {
        "title": "Ноорог", "body": "Дараа дуусгана.",
    })

    announcement = Announcement.objects.get()
    assert announcement.status == Announcement.Status.DRAFT
    assert announcement not in selectors.for_guardian(world["bataa_mother"])


def test_an_empty_title_is_refused(client, world):
    login(client, world["dulmaa"])

    response = client.post(reverse("comms:create"), {"title": "  ",
                                                     "body": "Текст"})

    assert response.status_code == 200
    assert not Announcement.objects.exists()


def test_the_badge_appears_in_the_parent_layout(client, world):
    make(world)
    login(client, world["bataa_mother"])

    body = client.get(reverse("children:parent_home")).content.decode()

    assert "Мэдэгдэл" in body
