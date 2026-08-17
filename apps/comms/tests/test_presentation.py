"""The announcement screens' presentation — RFP §8.1.

The dangerous mistakes on these two templates are not visual. An announcement
is addressed, so what matters is that a redesign did not widen who sees what,
and that the read state a family relies on still means what it says.

What is pinned:

* **the unread state is not carried by colour alone** (§13) — the word
  "Шинэ" is on the row, so it survives greyscale and a screen reader;
* **targeting is rendered to staff only.** `for_staff` prefetches
  `targets__group` and `targets__child`; `for_guardian` does not. Drawing the
  audience on a family's list would be a query per row *and* would tell them
  which other groups were written to;
* **the template never marks anything read.** `services.mark_read` runs in
  the view for non-staff only, so a staff preview must leave the count alone;
* the query count stays flat as the list grows.
"""

import pytest
from django.urls import reverse

from apps.comms import selectors, services
from apps.comms.models import AnnouncementRead

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"
LIST_URL = reverse("comms:list")


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def make(world, *, title="Эцэг эхийн хурал", publish=True, groups=None):
    announcement = services.save_announcement(
        actor=world["dulmaa"], kindergarten_id=world["naran"].pk,
        title=title, body="Пүрэв гарагт 18:00 цагт.",
    )
    if groups:
        services.set_targets(actor=world["dulmaa"], announcement=announcement,
                             groups=[g.pk for g in groups])
    if publish:
        services.publish(actor=world["dulmaa"], announcement=announcement)
    return announcement


# ------------------------------------------------------------ unread state

def test_an_unread_notice_says_so_in_words(client, world):
    """§13 — never colour alone. The badge is the accessible carrier."""
    make(world)
    login(client, world["bataa_mother"])

    body = client.get(LIST_URL).content.decode()

    assert "Шинэ" in body
    assert "note--new" in body


def test_a_read_notice_is_no_longer_marked_new(client, world):
    announcement = make(world)
    services.mark_read(actor=world["bataa_mother"], announcement=announcement)
    login(client, world["bataa_mother"])

    body = client.get(LIST_URL).content.decode()

    assert "note--new" not in body


def test_opening_a_notice_marks_it_read_exactly_once(client, world):
    """§8.1's "автоматаар" — and the view, not the template, does it."""
    announcement = make(world)
    login(client, world["bataa_mother"])

    client.get(reverse("comms:detail", args=[announcement.pk]))
    client.get(reverse("comms:detail", args=[announcement.pk]))

    assert AnnouncementRead.objects.filter(
        announcement=announcement, user=world["bataa_mother"]
    ).count() == 1


def test_a_teacher_opening_a_notice_does_not_mark_it_read(client, world):
    """Staff preview must not pollute the §8.1 read count."""
    announcement = make(world)
    login(client, world["dulmaa"])

    client.get(reverse("comms:detail", args=[announcement.pk]))

    assert not AnnouncementRead.objects.filter(announcement=announcement).exists()


# -------------------------------------------------------------- targeting

def test_the_audience_is_shown_to_staff(client, world):
    """§8.1 — a teacher needs to know who a notice reached."""
    make(world, groups=[world["sunflower"]])
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert world["sunflower"].name in body


def test_the_audience_is_not_shown_to_a_family(client, world):
    """Two reasons, and either alone would be enough.

    A family has no use for the routing, and `for_guardian` does not prefetch
    `targets` — so rendering it would be a query per row as well as telling
    one family which other groups were written to.
    """
    make(world, groups=[world["sunflower"]])
    login(client, world["bataa_mother"])

    body = client.get(LIST_URL).content.decode()

    assert world["sunflower"].name not in body


def test_a_family_never_sees_another_groups_notice(client, world, make_group,
                                                   make_child, make_guardian):
    """RFP §21 — the list is a disclosure surface like any other."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    other_child = make_child(world["naran"], other_group, first_name="Гадны")
    outsider = make_guardian(other_child, world["naran"], username="outsider")
    make(world, title="Зөвхөн Наранцэцэгт", groups=[world["sunflower"]])
    login(client, outsider)

    body = client.get(LIST_URL).content.decode()

    assert "Зөвхөн Наранцэцэгт" not in body


def test_a_family_never_sees_a_draft(client, world):
    make(world, title="Ноорог мэдэгдэл", publish=False)
    login(client, world["bataa_mother"])

    body = client.get(LIST_URL).content.decode()

    assert "Ноорог мэдэгдэл" not in body


# ------------------------------------------------------------ staff view

def test_a_teacher_sees_the_publish_status(client, world):
    make(world, title="Ноорог", publish=False)
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert "Ноорог" in body
    assert reverse("comms:create") in body


def test_a_draft_offers_the_publish_action(client, world):
    announcement = make(world, publish=False)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("comms:detail", args=[announcement.pk])
    ).content.decode()

    assert reverse("comms:publish", args=[announcement.pk]) in body
    assert reverse("comms:edit", args=[announcement.pk]) in body
    assert reverse("comms:delete", args=[announcement.pk]) in body


def test_a_family_is_offered_no_staff_actions(client, world):
    announcement = make(world)
    login(client, world["bataa_mother"])

    body = client.get(
        reverse("comms:detail", args=[announcement.pk])
    ).content.decode()

    assert reverse("comms:edit", args=[announcement.pk]) not in body
    assert reverse("comms:delete", args=[announcement.pk]) not in body
    assert "Уншсан" not in body          # the reader list is staff-only


# ---------------------------------------------------------- empty states

def test_a_family_with_nothing_gets_a_calm_empty_state(client, world):
    login(client, world["bataa_mother"])

    body = client.get(LIST_URL).content.decode()

    assert "мэдэгдэл алга" in body


def test_a_teacher_with_nothing_is_offered_the_first_notice(client, world):
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert "хараахан үүсгээгүй" in body
    assert reverse("comms:create") in body


# ---------------------------------------------------------- performance

@pytest.mark.parametrize("who,expected_rows", [
    pytest.param("bataa_mother", 7, id="guardian"),
    pytest.param("dulmaa", 7, id="teacher"),
])
def test_the_list_does_not_query_once_per_notice(client, world, who,
                                                 expected_rows):
    """CLAUDE.md §3.5 — on the screen a family opens for the badge.

    Both measurements are taken with targeted announcements already present.
    `for_staff` prefetches `targets__group` and `targets__child`, and those
    two sub-queries only run once some target row exists — so a baseline
    taken on an untargeted list is two queries short and the comparison
    reads as an N+1 that is not there. What matters is that the count does
    not move as *rows* are added, which is what this measures.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for index in range(3):
        make(world, title=f"Эхний {index}", groups=[world["sunflower"]])
    login(client, world[who])

    with CaptureQueriesContext(connection) as first:
        client.get(LIST_URL)
    baseline = len(first.captured_queries)

    for index in range(4):
        make(world, title=f"Мэдэгдэл {index}", groups=[world["sunflower"]])

    with CaptureQueriesContext(connection) as second:
        response = client.get(LIST_URL)

    assert response.context["page"].paginator.count == expected_rows
    assert len(second.captured_queries) == baseline, (
        "the announcement list issues a query per row — check the prefetches "
        "on comms.selectors.for_staff / for_guardian"
    )


def test_the_unread_badge_matches_the_selector(client, world):
    """The badge is why a family opens this screen; it must not drift."""
    make(world, title="Нэг")
    make(world, title="Хоёр")
    login(client, world["bataa_mother"])

    response = client.get(LIST_URL)

    assert response.context["unread"] == selectors.unread_count(
        world["bataa_mother"]
    )
