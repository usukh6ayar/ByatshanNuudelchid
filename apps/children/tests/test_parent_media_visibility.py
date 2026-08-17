"""The parent screens must not leak what a teacher marked private.

Written with the 2026-08-16 presentation redesign (docs/UI_AUDIT.md), which
added a "Сүүлийн мөчүүд" strip of photographs to
``children/parent/detail.html`` and then to ``children/parent/home.html``.
Both are covered here, and every media assertion runs against both: they
call the same selector today, and a future change that gives one screen its
own query must not be able to open a hole in the other silently.

That strip is a read path returning image URLs
to a guardian, and it is the most dangerous thing in the redesign: the §5.1
"эцэг эхэд харагдах эсэх" flag lives on the **observation**, not on the file,
so a photo section built from ``MediaFile`` filtered by child would hand the
family every picture attached to observations the teacher deliberately kept
back, and every parent submission still waiting for review.

``recent_media_for_child`` goes through the same ``_readable`` gate as every
other observation read, which is why it is correct. This file is why it is
*proven* — CLAUDE.md §4.1: the gate returning the right rows means nothing if
the view or the template reaches around it. Both assertions go through the
HTTP client and look at what actually reached the browser.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.media import services as media_services
from apps.media.tests.test_media import make_jpeg
from apps.observations.models import Observation, ObservationType
from apps.observations.services import create_observation

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def profile_url(child):
    return reverse("children:parent_child_detail", args=[child.pk])


def home_url(child):
    """The home screen renders the selected child, chosen by query string."""
    return f"{reverse('children:parent_home')}?child={child.pk}"


# Every parent screen that renders a photograph. Parametrised rather than
# duplicated so adding a third screen means adding one line here, and
# forgetting to cover it becomes the visible omission.
MEDIA_SCREENS = [
    pytest.param(profile_url, id="profile"),
    pytest.param(home_url, id="home"),
]


def observation_with_photo(world, *, visible_to_parents):
    """One observation about Батаа, carrying one photograph."""
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    observation = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
        visible_to_parents=visible_to_parents,
    )
    link = media_services.attach_to_observation(
        actor=world["dulmaa"], observation=observation, upload=make_jpeg(),
        caption="Барьсан цамхаг",
    )
    return observation, link.media_file


@pytest.mark.parametrize("url_for", MEDIA_SCREENS)
def test_a_guardian_sees_a_photo_from_a_visible_observation(client, world, url_for):
    """The control. Without this the tests below pass on an empty page."""
    _, media = observation_with_photo(world, visible_to_parents=True)

    login(client, world["bataa_mother"])
    body = client.get(url_for(world["bataa"])).content.decode()

    assert str(media.public_id) in body


@pytest.mark.parametrize("url_for", MEDIA_SCREENS)
def test_a_guardian_never_sees_a_photo_from_a_hidden_observation(client, world,
                                                                 url_for):
    """RFP §5.1, §21.3 — the flag the teacher set has to reach the picture."""
    _, media = observation_with_photo(world, visible_to_parents=False)

    login(client, world["bataa_mother"])
    body = client.get(url_for(world["bataa"])).content.decode()

    assert str(media.public_id) not in body, (
        "a photograph attached to an observation marked invisible to families "
        "reached a parent screen — the §5.1 flag is on the observation, so "
        "media must be read through the observations the user may see"
    )


@pytest.mark.parametrize("url_for", MEDIA_SCREENS)
def test_a_guardian_never_sees_a_photo_awaiting_review(client, world,
                                                       make_guardian, url_for):
    """A parent submission is not approved until a teacher says so (§5.4).

    Separate from the flag above: ``_readable`` requires *both* visible and
    approved, and a filter that checked only one of them would pass the
    previous test and fail this one.
    """
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    pending = create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 2),
        source=Observation.Source.PARENT,
    )
    # Marked visible, but still pending — the review is what is missing.
    pending.visible_to_parents = True
    pending.save(update_fields=["visible_to_parents"])
    link = media_services.attach_to_observation(
        actor=world["dulmaa"], observation=pending, upload=make_jpeg(),
    )

    # A second guardian of the same child, created here rather than reused
    # from the fixture: ``_readable`` lets someone see their *own* pending
    # submission, so asking the submitting parent would prove nothing. This
    # one did not write it.
    father = make_guardian(world["bataa"], world["naran"], username="bataa_father")

    login(client, father)
    body = client.get(url_for(world["bataa"])).content.decode()

    assert str(link.media_file.public_id) not in body


def test_a_guardian_of_another_child_gets_404(client, world):
    """CLAUDE.md §4.1 — the profile is a view that touches child data."""
    login(client, world["bataa_mother"])

    assert client.get(profile_url(world["saraa"])).status_code == 404


def test_the_home_switcher_rejects_a_child_that_is_not_this_guardians(
    client, world
):
    """``?child=`` is user input and is the home's only way in to a child.

    404 rather than a redirect back to the first child: an id outside this
    guardian's list must not be confirmed to exist (RFP §21.4).
    """
    login(client, world["bataa_mother"])

    assert client.get(home_url(world["saraa"])).status_code == 404


def test_a_teacher_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(profile_url(world["bataa"])).status_code == 404
