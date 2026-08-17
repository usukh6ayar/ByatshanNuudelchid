"""The §5.1 list's presentation — the parts that fail silently.

Few, and each for a reason a screenshot would not catch:

* the **query count must not grow with the number of rows**. The list gained
  a photo indicator on 2026-08-16, and reading ``media_links`` per row is one
  query per observation — twenty on a full page (CLAUDE.md §3.5). A prefetch
  fixes it and nothing in a rendered page says whether it is still there.
* the **visibility badge is a label, not a gate**. It names a state on a row
  the reader was already allowed to see; a guardian never reaches a hidden
  observation at all. Those are different mechanisms and the badge must not
  be mistaken for the second one.
* the two **empty states** — nothing recorded yet, and a filter that matched
  nothing — are different messages, and the wrong one is worse than none.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.observations import services
from apps.observations.models import ObservationType

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def list_url(child):
    return reverse("observations:list", args=[child.pk])


@pytest.fixture
def daily_type():
    return ObservationType.objects.get(kindergarten=None, code="daily")


def make_observations(world, daily_type, count, *, visible=True):
    return [
        services.create_observation(
            actor=world["dulmaa"], child=world["bataa"], type=daily_type,
            observed_on=dt.date(2025, 10, 1) + dt.timedelta(days=index),
            activity_name=f"Ажиглалт {index}",
            visible_to_parents=visible,
        )
        for index in range(count)
    ]


def test_the_list_does_not_query_once_per_row(client, world, daily_type):
    """CLAUDE.md §3.5 — the page cost must not scale with the page size.

    Measured as a comparison between one row and ten rather than against a
    fixed number: the absolute count moves whenever middleware or the shell
    changes, and pinning it would make this fail for reasons that have
    nothing to do with an N+1.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])
    make_observations(world, daily_type, 1)

    with CaptureQueriesContext(connection) as first:
        client.get(list_url(world["bataa"]))
    baseline = len(first.captured_queries)

    make_observations(world, daily_type, 9)

    with CaptureQueriesContext(connection) as second:
        response = client.get(list_url(world["bataa"]))

    assert len(response.context["page"].object_list) == 10
    assert len(second.captured_queries) == baseline, (
        "the list issues a query per row — check the prefetches on "
        "observations.selectors.child_observations"
    )


def test_a_visible_observation_is_labelled_as_such(client, world, daily_type):
    make_observations(world, daily_type, 1, visible=True)
    login(client, world["dulmaa"])

    body = client.get(list_url(world["bataa"])).content.decode()

    assert "Эцэг эхэд харагдана" in body


def test_a_closed_observation_is_labelled_private(client, world, daily_type):
    """Since 2026-08-16 this is the common case, so it must read as normal."""
    make_observations(world, daily_type, 1, visible=False)
    login(client, world["dulmaa"])

    body = client.get(list_url(world["bataa"])).content.decode()

    assert "Хувийн" in body


def test_the_badge_is_a_label_and_not_the_access_rule(client, world, daily_type):
    """A guardian does not see a hidden row *at all* — badge or no badge.

    The teacher's list shows "Хувийн" against a row they may read. The
    family's list simply does not contain it. Asserting both together is
    what stops the badge being mistaken for the enforcement.
    """
    hidden = make_observations(world, daily_type, 1, visible=False)[0]

    login(client, world["dulmaa"])
    teacher_body = client.get(list_url(world["bataa"])).content.decode()
    assert hidden.summary in teacher_body

    login(client, world["bataa_mother"])
    guardian_body = client.get(list_url(world["bataa"])).content.decode()
    assert hidden.summary not in guardian_body


def test_the_empty_state_offers_the_first_observation(client, world):
    login(client, world["dulmaa"])

    body = client.get(list_url(world["bataa"])).content.decode()

    assert "Эхний ажиглалтаа бүртгэх" in body


def test_a_filter_that_matches_nothing_says_so_and_offers_a_way_back(
    client, world, daily_type
):
    """Different from "nothing recorded yet", and it must not claim that."""
    make_observations(world, daily_type, 1)
    login(client, world["dulmaa"])

    response = client.get(list_url(world["bataa"]), {"from": "2030-01-01"})
    body = response.content.decode()

    assert list(response.context["page"].object_list) == []
    assert "тохирох ажиглалт олдсонгүй" in body
    assert "Шүүлтийг цэвэрлэх" in body


def test_an_active_filter_opens_the_filter_panel(client, world, daily_type):
    """A filter narrowing the list must never be doing so invisibly.

    The panel is collapsed by default so the list starts near the top of a
    phone screen; the server opens it whenever a filter is applied.
    """
    make_observations(world, daily_type, 1)
    login(client, world["dulmaa"])

    plain = client.get(list_url(world["bataa"])).content.decode()
    filtered = client.get(
        list_url(world["bataa"]), {"from": "2030-01-01"}
    ).content.decode()

    def disclosure(html: str) -> str:
        """The opening `<details …>` tag, so `open` is read off that tag
        alone rather than off anything else on the page containing the
        word."""
        return html.split("<details", 1)[1].split(">", 1)[0]

    assert "open" not in disclosure(plain)
    assert "open" in disclosure(filtered)
