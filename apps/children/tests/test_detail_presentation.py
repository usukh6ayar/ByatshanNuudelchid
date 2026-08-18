"""The teacher child detail's presentation — the parts that fail silently.

The screen gained five reads on 2026-08-16 (observations, media, assessments,
About Me, the age pages), all through selectors the parent screens already
used. What is pinned here:

* the **query count must not grow with how much each section shows**. Five
  related reads on one page is exactly where an N+1 arrives (CLAUDE.md §3.5).
* **authorization is unchanged.** The page now surfaces observations and
  photographs it did not before, and a teacher must see their own private
  notes while a guardian must not reach the page at all.
* the **empty states** render — this is the screen a newly registered child
  lands on, and every section will be empty on it.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.media import services as media_services
from apps.media.tests.test_media import make_jpeg
from apps.observations import services as observation_services
from apps.observations.models import ObservationType

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def detail_url(child):
    return reverse("children:detail", args=[child.pk])


@pytest.fixture
def daily_type():
    return ObservationType.objects.get(kindergarten=None, code="daily")


def make_observations(world, daily_type, count, *, visible=True):
    return [
        observation_services.create_observation(
            actor=world["dulmaa"], child=world["bataa"], type=daily_type,
            observed_on=dt.date(2025, 10, 1) + dt.timedelta(days=index),
            activity_name=f"Ажиглалт {index}",
            visible_to_parents=visible,
        )
        for index in range(count)
    ]


def test_the_page_does_not_query_once_per_row(client, world, daily_type):
    """CLAUDE.md §3.5 — five related sections must stay a fixed cost.

    Compared between two data volumes rather than pinned to a number: the
    absolute count moves with middleware and the shell, and pinning it would
    make this fail for reasons unrelated to an N+1.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])
    make_observations(world, daily_type, 1)

    with CaptureQueriesContext(connection) as first:
        client.get(detail_url(world["bataa"]))
    baseline = len(first.captured_queries)

    for observation in make_observations(world, daily_type, 6):
        media_services.attach_to_observation(
            actor=world["dulmaa"], observation=observation, upload=make_jpeg(),
        )

    with CaptureQueriesContext(connection) as second:
        client.get(detail_url(world["bataa"]))

    assert len(second.captured_queries) == baseline, (
        "the child detail issues a query per row — check the selectors it "
        "calls in apps/children/views/teacher.py::child_detail"
    )


def test_the_page_shows_recent_observations(client, world, daily_type):
    make_observations(world, daily_type, 2)
    login(client, world["dulmaa"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Ажиглалт 0" in body
    assert "Сүүлийн ажиглалт" in body


def test_a_teacher_sees_their_own_private_observation_here(client, world,
                                                           daily_type):
    """The point of the screen: it is the teacher's working record.

    The parent profile hides a closed observation; this one must not.
    """
    make_observations(world, daily_type, 1, visible=False)
    login(client, world["dulmaa"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Ажиглалт 0" in body
    assert "Хувийн" in body


def test_only_a_recent_subset_is_shown(client, world, daily_type):
    """§6 — the hub links to the archive rather than reproducing it."""
    import apps.children.views.teacher as view_module

    make_observations(world, daily_type, view_module.RECENT_OBSERVATIONS + 3)
    login(client, world["dulmaa"])

    response = client.get(detail_url(world["bataa"]))

    shown = response.context["observations"]
    assert len(shown) == view_module.RECENT_OBSERVATIONS
    assert response.context["observation_count"] > len(shown)
    assert "ажиглалтыг харах" in response.content.decode()


def test_a_newly_registered_child_renders_every_empty_state(client, world,
                                                            make_child):
    """The screen a child lands on the moment they are registered."""
    fresh = make_child(world["naran"], world["sunflower"], first_name="Шинэхэн")
    login(client, world["dulmaa"])

    response = client.get(detail_url(fresh))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Эхний ажиглалтаа бүртгэх" in body          # no observations
    assert "үнэлгээ хараахан хийгдээгүй" in body       # no assessment
    assert "Асран хамгаалагч холбогдоогүй" in body     # no guardian
    # No media section at all rather than an empty gallery.
    assert "Сүүлийн зургууд" not in body


def test_a_guardian_of_another_child_gets_404(client, world):
    """CLAUDE.md §4.1 — the redesign changed the markup, not the rules."""
    login(client, world["bataa_mother"])

    assert client.get(detail_url(world["saraa"])).status_code == 404


def test_a_teacher_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(detail_url(world["bataa"])).status_code == 404


def test_the_edit_action_is_hidden_from_a_guardian(client, world):
    """A link that answers 404 teaches the reader the page exists.

    Presentation only — `children:edit` runs its own
    `assert_can_record_for_child`, which is the actual rule.
    """
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert reverse("children:edit", args=[world["bataa"].pk]) not in body


# ------------------------------------------ record a note, 2026-08-18
# The single "Ажиглалт нэмэх" button became one card per §5.2 type, from the
# client's mockup. The cards come from `ObservationType`, so what is worth
# pinning is that they follow the table rather than a list in the template —
# and that the one a guardian's own submission is filed under is not offered
# to a teacher as something to write.


def test_the_page_offers_a_card_for_each_teacher_observation_type(client, world):
    login(client, world["dulmaa"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    for code in ("daily", "artwork", "activity"):
        name = ObservationType.objects.get(kindergarten=None, code=code).name
        assert name in body, f"no entry point for observation type: {code}"


def test_the_parent_submission_type_is_not_offered_to_a_teacher(client, world):
    """§5.2 — a teacher's own note is never "an observation the parent
    entered". Offering it as an entry point would misfile the record."""
    login(client, world["dulmaa"])

    body = client.get(detail_url(world["bataa"])).content.decode()
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")

    assert f"?type={parent_type.pk}" not in body


def test_a_kindergartens_own_type_gets_a_card_without_a_template_change(
    client, world,
):
    """CLAUDE.md §2.3 — the types are a table an administrator edits."""
    login(client, world["dulmaa"])
    own = ObservationType.objects.create(
        kindergarten=world["naran"], code="interview", name="Ярилцлага",
    )

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Ярилцлага" in body
    assert f"?type={own.pk}" in body


def test_a_guardian_is_offered_no_note_cards(client, world):
    """§5.4 gives families their own screen; `observations:create` answers
    404 for them, so a card here would be a link into a refusal."""
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Тэмдэглэл бүртгэх" not in body
