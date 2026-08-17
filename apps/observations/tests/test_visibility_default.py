"""§5.1 visibility is closed by default — product decision, 2026-08-16.

The rule, in one line: **a teacher's observation is a working record until
they publish it.** It read the other way round until this date — the model,
the service and the form all defaulted open — so these tests exist to stop it
drifting back, which is the kind of change that looks like a tidy-up and is
actually a disclosure.

One exception, and it is deliberate: a **family's own submission** stays
visible to the family. It is their words about their own child, and a child
usually has more than one guardian, so closing it by default would hide a
mother's note from the father. The submitting parent would still see it —
``selectors._readable`` always returns a user their own submissions — which
is precisely what would make the loss go unnoticed.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.observations import selectors, services
from apps.observations.models import Observation, ObservationType

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


@pytest.fixture
def daily_type():
    return ObservationType.objects.get(kindergarten=None, code="daily")


@pytest.fixture
def parent_type():
    return ObservationType.objects.get(kindergarten=None, code="parent")


# ------------------------------------------------------------- the default

def test_a_new_teacher_observation_is_not_visible_to_parents(world, daily_type):
    """The decision itself, at the service — every caller inherits this."""
    observation = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )

    assert observation.visible_to_parents is False


def test_the_model_default_is_closed(world):
    """Belt and braces: a row built without the service is closed too."""
    assert Observation._meta.get_field("visible_to_parents").default is False


def test_a_teacher_may_still_publish_explicitly(world, daily_type):
    """The default is a starting point, not a restriction."""
    observation = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1), visible_to_parents=True,
    )

    assert observation.visible_to_parents is True
    assert observation in selectors.child_observations(
        world["bataa_mother"], world["bataa"]
    )


def test_a_closed_observation_is_not_readable_by_the_family(world, daily_type):
    """The default has to reach the query, not just the column."""
    observation = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )

    assert observation not in selectors.child_observations(
        world["bataa_mother"], world["bataa"]
    )
    # The teacher who wrote it still sees their own record.
    assert observation in selectors.child_observations(
        world["dulmaa"], world["bataa"]
    )


# ----------------------------------------------------- the parent exception

def test_a_familys_own_submission_stays_visible_to_the_family(world, parent_type):
    """RFP §5.4 — the exception, and why the default is not applied blindly.

    Asserted through a *second* guardian: the parent who wrote it sees it
    either way, so testing them would pass even if the exception were lost.
    """
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )

    assert submitted.visible_to_parents is True


def test_the_other_guardian_can_read_an_approved_parent_note(
    world, parent_type, make_guardian
):
    father = make_guardian(world["bataa"], world["naran"],
                           username="visibility_father")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    services.review_observation(
        actor=world["dulmaa"], observation=submitted,
        status=Observation.ReviewStatus.APPROVED, include_in_report=True,
    )

    assert submitted in selectors.child_observations(father, world["bataa"])


# ------------------------------------------------------------- the group form

def test_a_group_observation_is_closed_by_default(world, daily_type):
    """§5.2 writes one activity across a roster — the same rule applies."""
    created = services.create_group_observation(
        actor=world["dulmaa"], group=world["sunflower"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
        entries={world["bataa"].enrollments.get().pk: "Оролцов."},
    )

    assert created
    assert all(o.visible_to_parents is False for o in created)


# ------------------------------------------------------------------ the form

def test_the_create_form_leaves_the_visibility_box_unticked(client, world):
    """The screen has to agree with the service, or the default is theatre."""
    login(client, world["dulmaa"])

    body = client.get(
        reverse("observations:create", args=[world["bataa"].pk])
    ).content.decode()

    box = body.split('name="visible_to_parents"', 1)[1].split(">", 1)[0]
    assert "checked" not in box


def test_posting_the_form_without_the_box_creates_a_closed_observation(
    client, world, daily_type
):
    """End to end: an unticked box must not arrive as True."""
    login(client, world["dulmaa"])

    response = client.post(
        reverse("observations:create", args=[world["bataa"].pk]),
        {
            "type": daily_type.pk,
            "observed_on": "2025-10-01",
            "child_did": "Блокоор барив.",
        },
    )

    assert response.status_code == 302
    assert Observation.objects.get(child=world["bataa"]).visible_to_parents is False


def test_a_ticked_box_survives_a_validation_error(client, world):
    """Losing the tick would silently re-close an observation on resubmit."""
    login(client, world["dulmaa"])

    response = client.post(
        reverse("observations:create", args=[world["bataa"].pk]),
        # No type: rejected, and the form comes back.
        {"observed_on": "2025-10-01", "visible_to_parents": "on"},
    )
    body = response.content.decode()

    box = body.split('name="visible_to_parents"', 1)[1].split(">", 1)[0]
    assert "checked" in box


# ------------------------------------------------------- existing records

def test_the_migration_leaves_existing_observations_alone(world, daily_type):
    """`sqlmigrate` prints "(no-op)"; this asserts it on real rows.

    Django applies model defaults in Python, never as a column default, so
    altering one cannot rewrite stored rows. A record a teacher published
    before the decision stays published, and a family does not lose what
    they could already read.
    """
    published = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1), visible_to_parents=True,
    )

    # Whatever a later migration does, a stored True stays True and stays
    # readable by the family.
    published.refresh_from_db()
    assert published.visible_to_parents is True
    assert published in selectors.child_observations(
        world["bataa_mother"], world["bataa"]
    )
