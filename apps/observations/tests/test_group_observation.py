"""Recording one activity for a whole group — RFP §5.2.

The per-child form asks for eleven fields. A teacher running one activity
with eight children has the nap hour to write it up, and eight passes
through that form is most of the hour. This screen fills the shared half
once.

The authorization surface is the same as the §6.3 grid's: the group id is
the only thing the URL carries, so the check is "is this your group".
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.children.models import Enrollment
from apps.observations import services
from apps.observations.models import Observation, ObservationType

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def url_for(group):
    return reverse("observations:group", args=[group.pk])


@pytest.fixture
def daily():
    return ObservationType.objects.get(kindergarten=None, code="daily")


@pytest.fixture
def roster(world):
    """Both Naran children are in Dulmaa's group already."""
    return list(
        Enrollment.objects.filter(group=world["sunflower"], status="active")
        .select_related("child")
        .order_by("child__first_name")
    )


# ------------------------------------------------------------------ §21.4

def test_a_teacher_from_another_group_gets_404(client, world, make_teacher,
                                               make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    url = url_for(world["sunflower"])
    assert client.get(url).status_code == 404
    assert client.post(url, {}).status_code == 404
    assert not Observation.objects.exists()


def test_a_guardian_gets_404(client, world):
    """§5.2 is the teacher's record — a family's note goes in as
    source=parent through their own screen (§5.4)."""
    login(client, world["bataa_mother"])

    url = url_for(world["sunflower"])
    assert client.get(url).status_code == 404
    assert client.post(url, {}).status_code == 404
    assert not Observation.objects.exists()


def test_a_teacher_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    url = url_for(world["sunflower"])
    assert client.get(url).status_code == 404
    assert client.post(url, {}).status_code == 404
    assert not Observation.objects.exists()


# ------------------------------------------------------------------- work

def test_one_activity_becomes_one_observation_per_child(client, world, daily,
                                                        roster):
    login(client, world["dulmaa"])

    response = client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": dt.date.today().isoformat(),
        "activity_name": "Блокоор барих",
        "situation": "Өглөөний чөлөөт тоглоом",
        f"pick_{roster[0].pk}": "on",
        f"note_{roster[0].pk}": "Найзтайгаа ээлжлэн барив.",
        f"pick_{roster[1].pk}": "on",
    })

    assert response.status_code == 302
    made = Observation.objects.order_by("child__first_name")
    assert made.count() == 2
    # The shared half is on both.
    assert {o.activity_name for o in made} == {"Блокоор барих"}
    assert {o.situation for o in made} == {"Өглөөний чөлөөт тоглоом"}
    # The per-child note is only on the child it was written for.
    assert made[0].child_did == "Найзтайгаа ээлжлэн барив."
    assert made[1].child_did == ""


def test_an_unticked_child_gets_nothing(client, world, daily, roster):
    """A note typed against a child who was then unticked must not create a
    record — the tick is the decision, not the text."""
    login(client, world["dulmaa"])

    client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": dt.date.today().isoformat(),
        f"pick_{roster[0].pk}": "on",
        f"note_{roster[1].pk}": "Бичсэн ч сонгоогүй",
    })

    assert Observation.objects.count() == 1
    assert Observation.objects.get().child_id == roster[0].child_id


def test_choosing_nobody_is_refused(client, world, daily):
    login(client, world["dulmaa"])

    response = client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": dt.date.today().isoformat(),
        "activity_name": "Хэн ч сонгоогүй",
    })

    assert response.status_code == 200
    assert "хүүхдээ сонгоно уу" in response.content.decode()
    assert not Observation.objects.exists()


def test_a_missing_type_is_refused(client, world, roster):
    login(client, world["dulmaa"])

    response = client.post(url_for(world["sunflower"]), {
        "observed_on": dt.date.today().isoformat(),
        f"pick_{roster[0].pk}": "on",
    })

    assert response.status_code == 200
    assert "төрлийг сонгоно уу" in response.content.decode()
    assert not Observation.objects.exists()


def test_a_future_date_is_refused(client, world, daily, roster):
    """§5.1's rule, reached through the group screen this time."""
    login(client, world["dulmaa"])
    tomorrow = dt.date.today() + dt.timedelta(days=1)

    response = client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": tomorrow.isoformat(),
        f"pick_{roster[0].pk}": "on",
    })

    assert response.status_code == 200
    assert not Observation.objects.exists()


def test_a_posted_outsider_never_reaches_the_service(client, world, daily,
                                                     roster, make_child):
    """Through HTTP: the view builds its entries from the roster it queried,
    so an id the teacher does not hold is gone before the service runs."""
    elsewhere = make_child(world["och"], world["petal"], first_name="Гадны")
    outsider = Enrollment.objects.get(child=elsewhere)
    login(client, world["dulmaa"])

    client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": dt.date.today().isoformat(),
        f"pick_{roster[0].pk}": "on",
        f"pick_{outsider.pk}": "on",
        f"note_{outsider.pk}": "Өөр цэцэрлэгийн хүүхэд",
    })

    assert Observation.objects.count() == 1
    assert Observation.objects.get().child_id == roster[0].child_id


def test_the_service_drops_an_outsider_on_its_own(world, daily, roster,
                                                   make_child):
    """Called directly, past the view.

    Written after a mutation check: removing the service's own scoping broke
    no test, because every HTTP test hands it an already-filtered roster.
    The service is the layer a later API will call (CLAUDE.md §2.1), so its
    guard has to be proved on its own terms.
    """
    elsewhere = make_child(world["och"], world["petal"], first_name="Гадны")
    outsider = Enrollment.objects.get(child=elsewhere)

    made = services.create_group_observation(
        actor=world["dulmaa"],
        group=world["sunflower"],
        type=daily,
        observed_on=dt.date.today(),
        entries={roster[0].pk: "", outsider.pk: "Байж болохгүй"},
    )

    assert len(made) == 1
    assert made[0].child_id == roster[0].child_id
    assert not Observation.objects.filter(child=elsewhere).exists()


def test_the_domains_land_on_every_child(client, world, daily, roster):
    """§5.3 — one activity can touch several domains, and they apply to
    everyone who took part."""
    from apps.assessment.selectors import domains_for

    picked = list(domains_for(world["naran"].pk)[:2])
    login(client, world["dulmaa"])

    client.post(url_for(world["sunflower"]), {
        "type": daily.pk,
        "observed_on": dt.date.today().isoformat(),
        "domains": [d.pk for d in picked],
        f"pick_{roster[0].pk}": "on",
        f"pick_{roster[1].pk}": "on",
    })

    for observation in Observation.objects.all():
        assert observation.domain_links.count() == 2


def test_the_service_writes_one_audit_row_per_child(world, daily, roster):
    """RFP §971 — each child's record is its own entry, not one batch line."""
    from apps.core.models import AuditAction, AuditLog

    services.create_group_observation(
        actor=world["dulmaa"],
        group=world["sunflower"],
        type=daily,
        observed_on=dt.date.today(),
        activity_name="Дуулах",
        entries={roster[0].pk: "", roster[1].pk: ""},
    )

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE, object_type="observations.Observation"
    ).count() == 2
