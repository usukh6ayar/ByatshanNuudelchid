"""Observations — RFP §5.1, §5.2, §5.4, and the §21 authorization rules."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.assessment.models import DevelopmentDomain
from apps.assessment.selectors import domains_for, levels_for
from apps.core.models import AuditAction, AuditLog
from apps.observations import selectors, services
from apps.observations.models import Observation, ObservationDomain, ObservationType

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def list_url(child):
    return reverse("observations:list", args=[child.pk])


def create_url(child):
    return reverse("observations:create", args=[child.pk])


@pytest.fixture
def daily_type():
    return ObservationType.objects.get(kindergarten=None, code="daily")


@pytest.fixture
def observation(world, daily_type):
    """One observation about Bataa, written by their own teacher."""
    return services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
        activity_name="Өглөөний дасгал",
        child_did="Хөгжимд тааруулан дасгал хийв.",
    )


# ------------------------------------------------------------------ §21 first
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client.

@pytest.mark.parametrize("url_for", [list_url, create_url])
def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group, url_for):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(url_for(world["bataa"])).status_code == 404


@pytest.mark.parametrize("url_for", [list_url, create_url])
def test_guardian_of_another_child_gets_404(client, world, url_for):
    login(client, world["bataa_mother"])

    assert client.get(url_for(world["saraa"])).status_code == 404


@pytest.mark.parametrize("url_for", [list_url, create_url])
def test_user_from_another_kindergarten_gets_404(client, world, url_for):
    login(client, world["oyun"])

    assert client.get(url_for(world["bataa"])).status_code == 404


def test_detail_of_another_childs_observation_gets_404(client, world,
                                                       observation):
    """The id belongs to a real observation — just not to this child."""
    login(client, world["bataa_mother"])

    response = client.get(
        reverse("observations:detail", args=[world["saraa"].pk, observation.pk])
    )

    assert response.status_code == 404


def test_posting_an_observation_for_another_child_gets_404(client, world,
                                                           daily_type):
    login(client, world["oyun"])

    response = client.post(create_url(world["bataa"]), {
        "type": daily_type.pk,
        "observed_on": "2025-10-01",
        "child_did": "Халдлага",
    })

    assert response.status_code == 404
    assert not Observation.objects.filter(child=world["bataa"]).exists()


def test_guardian_cannot_write_a_teacher_observation(client, world, daily_type):
    """RFP §5.1 — the observation is the teacher's professional record.

    A guardian passes ``can_access_child``; that is not enough here.
    """
    login(client, world["bataa_mother"])

    response = client.post(create_url(world["bataa"]), {
        "type": daily_type.pk,
        "observed_on": "2025-10-01",
        "teacher_comment": "Багшийн нэрээр бичсэн",
    })

    assert response.status_code == 404
    assert not Observation.objects.filter(child=world["bataa"]).exists()


def test_guardian_does_not_see_a_hidden_observation(client, world, daily_type):
    """RFP §5.1 — "эцэг эхэд харагдах эсэх"."""
    hidden = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 2), visible_to_parents=False,
        child_did="Зөвхөн багшид",
    )
    login(client, world["bataa_mother"])

    assert client.get(
        reverse("observations:detail", args=[world["bataa"].pk, hidden.pk])
    ).status_code == 404
    assert hidden not in selectors.child_observations(
        world["bataa_mother"], world["bataa"]
    )


def test_teacher_sees_their_own_hidden_observation(world, daily_type):
    hidden = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 2), visible_to_parents=False,
    )

    assert hidden in selectors.child_observations(world["dulmaa"],
                                                  world["bataa"])


# ------------------------------------------------------------------ §5.1

def test_teacher_records_an_observation(client, world, daily_type):
    login(client, world["dulmaa"])
    domain = domains_for(world["naran"].pk).first()
    level = levels_for(world["naran"].pk).first()

    response = client.post(create_url(world["bataa"]), {
        "type": daily_type.pk,
        "observed_on": "2025-10-01",
        "activity_name": "Блокоор барих",
        "situation": "Хосоороо тоглож байхад",
        "child_did": "Найзтайгаа ээлжлэн блок өрөв.",
        "child_said": "«Чи эхлээд тавь.»",
        "teacher_comment": "Хамтран ажиллах чадвар сайжирч байна.",
        "next_steps": "Бүлгийн тоглоомд оролцуулах.",
        "domains": [str(domain.pk)],
        f"level_{domain.pk}": str(level.pk),
        "visible_to_parents": "on",
        "include_in_report": "on",
    })

    assert response.status_code == 302
    observation = Observation.objects.get(child=world["bataa"])
    assert observation.activity_name == "Блокоор барих"
    assert observation.source == Observation.Source.TEACHER
    assert observation.enrollment == world["bataa"].enrollments.get()
    # The record carries the kindergarten of the enrollment, not of the user.
    assert observation.kindergarten_id == world["naran"].pk

    link = ObservationDomain.objects.get(observation=observation)
    assert link.domain == domain
    assert link.level == level


def test_an_observation_may_span_several_domains(world, daily_type):
    """Spec section 6.3 — one observation, several domains."""
    domains = list(domains_for(world["naran"].pk)[:3])

    observation = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
        domains=[(domain, None) for domain in domains],
    )

    assert observation.domain_links.count() == 3


def test_unticking_a_domain_removes_the_link(world, daily_type, observation):
    domains = list(domains_for(world["naran"].pk)[:2])
    services.set_domains(actor=world["dulmaa"], observation=observation,
                         domains=domains)
    assert observation.domain_links.count() == 2

    services.set_domains(actor=world["dulmaa"], observation=observation,
                         domains=[domains[0]])

    assert observation.domain_links.count() == 1
    assert observation.domain_links.get().domain == domains[0]


def test_another_kindergartens_domain_is_rejected(world, daily_type):
    """A crafted request naming another kindergarten's configuration."""
    foreign = DevelopmentDomain.objects.create(
        kindergarten=world["och"], name="Гадны чиглэл", code="foreign"
    )

    with pytest.raises(ValidationError):
        services.create_observation(
            actor=world["dulmaa"], child=world["bataa"], type=daily_type,
            observed_on=dt.date(2025, 10, 1), domains=[foreign],
        )


def test_a_future_date_is_rejected(world, daily_type):
    with pytest.raises(ValidationError):
        services.create_observation(
            actor=world["dulmaa"], child=world["bataa"], type=daily_type,
            observed_on=dt.date.today() + dt.timedelta(days=1),
        )


def test_a_child_with_no_enrollment_cannot_be_observed(world, make_child,
                                                       daily_type):
    """The record is filed against an enrollment — spec section 4.2."""
    loose = make_child(world["naran"], first_name="Бүлэггүй")
    admin = world["dulmaa"]

    with pytest.raises((ValidationError, PermissionDenied)):
        services.create_observation(
            actor=admin, child=loose, type=daily_type,
            observed_on=dt.date(2025, 10, 1),
        )


# ------------------------------------------------------------------ §3.4

def test_delete_archives_rather_than_removes(client, world, observation):
    login(client, world["dulmaa"])

    response = client.post(
        reverse("observations:delete", args=[world["bataa"].pk, observation.pk])
    )

    assert response.status_code == 302
    assert not Observation.objects.filter(pk=observation.pk).exists()
    archived = Observation.all_objects.get(pk=observation.pk)
    assert archived.deleted_at is not None
    assert archived.deleted_by == world["dulmaa"]


def test_a_guardian_cannot_archive_an_observation(client, world, observation):
    login(client, world["bataa_mother"])

    response = client.post(
        reverse("observations:delete", args=[world["bataa"].pk, observation.pk])
    )

    assert response.status_code == 404
    assert Observation.objects.filter(pk=observation.pk).exists()


# ------------------------------------------------------------------ §5.4

def test_a_parent_submission_starts_pending(world, daily_type):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")

    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT,
        observed_on=dt.date(2025, 10, 1),
        situation="Гэртээ ном уншив.",
    )

    assert submitted.source == Observation.Source.PARENT
    assert submitted.review_status == Observation.ReviewStatus.PENDING
    assert submitted in selectors.pending_parent_observations(world["dulmaa"])


def test_a_guardian_sees_their_own_submission_before_review(world, daily_type):
    """Otherwise they cannot tell whether it saved."""
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )

    assert submitted in selectors.child_observations(world["bataa_mother"],
                                                     world["bataa"])


def test_teacher_approves_a_parent_submission(client, world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    login(client, world["dulmaa"])

    response = client.post(
        reverse("observations:review",
                args=[world["bataa"].pk, submitted.pk]),
        {"review_status": "approved", "review_note": "Баярлалаа.",
         "include_in_report": "on"},
    )

    assert response.status_code == 302
    submitted.refresh_from_db()
    assert submitted.review_status == Observation.ReviewStatus.APPROVED
    assert submitted.reviewed_by == world["dulmaa"]
    assert submitted.include_in_report is True


def test_a_guardian_cannot_review(client, world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    login(client, world["bataa_mother"])

    response = client.post(
        reverse("observations:review", args=[world["bataa"].pk, submitted.pk]),
        {"review_status": "approved"},
    )

    assert response.status_code == 404
    submitted.refresh_from_db()
    assert submitted.review_status == Observation.ReviewStatus.PENDING


def test_a_teacher_observation_cannot_be_reviewed(world, observation):
    """There is nobody above the teacher to approve it."""
    with pytest.raises(ValidationError):
        services.review_observation(
            actor=world["dulmaa"], observation=observation, status="approved"
        )


def test_a_guardian_cannot_edit_after_approval(world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    services.review_observation(actor=world["dulmaa"], observation=submitted,
                                status=Observation.ReviewStatus.APPROVED)

    with pytest.raises(ValidationError):
        services.update_observation(
            actor=world["bataa_mother"], observation=submitted,
            situation="Дараа нь өөрчилсөн",
        )


def test_a_guardian_cannot_edit_another_guardians_submission(world,
                                                             make_guardian):
    other = make_guardian(world["bataa"], world["naran"], username="father")
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )

    with pytest.raises(PermissionDenied):
        services.update_observation(actor=other, observation=submitted,
                                    situation="Өөр хүний бичсэн")


# ------------------------------------------------------------------ §971, §3.5

def test_creating_an_observation_writes_an_audit_row(world, daily_type):
    services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE,
        actor_user=world["dulmaa"],
        object_type="observations.Observation",
    ).exists()


def test_the_list_does_not_query_per_row(client, world, daily_type):
    """CLAUDE.md §3.5 — no N+1.

    Asserted as "the count does not grow with the number of rows" rather
    than against a fixed number. A fixed number breaks whenever anything
    unrelated changes, which trains people to bump it; what §3.5 actually
    forbids is a query *per row*, and that is what this measures. The type,
    the author and the domain links are all prefetched, so adding rows adds
    nothing.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])
    url = list_url(world["bataa"])

    def count_after(rows: int) -> int:
        for day in range(1, rows + 1):
            services.create_observation(
                actor=world["dulmaa"], child=world["bataa"], type=daily_type,
                observed_on=dt.date(2025, 10, day),
                domains=list(domains_for(world["naran"].pk)[:2]),
            )
        client.get(url)      # warm the session lookup
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured)

    assert count_after(3) == count_after(12)


# ------------------------------------------------------------------ rendering
# The §21 tests above all assert 404, which a broken template would also
# produce on the happy path without anyone noticing.

def test_every_screen_renders_for_a_teacher(client, world, observation):
    login(client, world["dulmaa"])
    child = world["bataa"]

    for url in [
        list_url(child),
        create_url(child),
        reverse("observations:detail", args=[child.pk, observation.pk]),
        reverse("observations:edit", args=[child.pk, observation.pk]),
        reverse("observations:delete", args=[child.pk, observation.pk]),
    ]:
        assert client.get(url).status_code == 200, url


def test_the_list_renders_for_a_guardian(client, world, observation):
    """The guardian layout is a different base template."""
    login(client, world["bataa_mother"])

    response = client.get(list_url(world["bataa"]))

    assert response.status_code == 200
    assert b"base_parent" not in response.content   # rendered, not echoed
    assert "Ажиглалт" in response.content.decode()


def test_a_guardian_editing_cannot_change_the_teachers_decisions(world):
    """RFP §5.4 — inclusion and visibility are the teacher's call.

    Posted directly, not through the form: the form never renders these
    fields for a guardian, so this is the crafted-request case.
    """
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    services.review_observation(
        actor=world["dulmaa"], observation=submitted,
        status=Observation.ReviewStatus.PENDING, include_in_report=False,
    )

    services.update_observation(
        actor=world["bataa_mother"], observation=submitted,
        situation="Засварласан текст",
        include_in_report=True, visible_to_parents=False,
    )

    submitted.refresh_from_db()
    assert submitted.situation == "Засварласан текст"
    assert submitted.include_in_report is False
    assert submitted.visible_to_parents is True


def test_a_teacher_editing_may_change_them(world, observation):
    services.update_observation(
        actor=world["dulmaa"], observation=observation,
        include_in_report=False, visible_to_parents=False,
    )

    observation.refresh_from_db()
    assert observation.include_in_report is False
    assert observation.visible_to_parents is False


# ------------------------------------------------ writes across a transfer

@pytest.fixture
def transferred(world):
    """Bataa moves from Naran to Och mid-year."""
    from apps.children.models import Enrollment

    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED, ended_on=dt.date(2026, 1, 15)
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"], group=world["petal"],
        school_year=world["och_year"], started_on=dt.date(2026, 1, 16),
    )
    world["bataa"].kindergarten = world["och"]
    world["bataa"].save()
    return world


def test_the_previous_teacher_cannot_write_at_the_new_kindergarten(
    transferred, daily_type
):
    """RFP §3.2 — the row would land inside a tenant they are not part of."""
    with pytest.raises(PermissionDenied):
        services.create_observation(
            actor=transferred["dulmaa"], child=transferred["bataa"],
            type=daily_type, observed_on=dt.date(2026, 2, 1),
        )

    assert not Observation.objects.filter(
        kindergarten=transferred["och"]
    ).exists()


def test_the_previous_teacher_may_still_edit_their_own_record(world,
                                                              daily_type):
    """Which is the whole reason access survives a transfer."""
    from apps.children.models import Enrollment

    mine = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )
    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"], group=world["petal"],
        school_year=world["och_year"], started_on=dt.date(2026, 1, 16),
    )

    services.update_observation(actor=world["dulmaa"], observation=mine,
                                teacher_comment="Тодруулга")

    mine.refresh_from_db()
    assert mine.teacher_comment == "Тодруулга"


def test_the_new_teacher_cannot_edit_the_old_kindergartens_record(world,
                                                                  daily_type):
    from apps.children.models import Enrollment

    theirs = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )
    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"], group=world["petal"],
        school_year=world["och_year"], started_on=dt.date(2026, 1, 16),
    )

    with pytest.raises(PermissionDenied):
        services.update_observation(actor=world["oyun"], observation=theirs,
                                    teacher_comment="Гадны засвар")


def test_a_guardian_editing_cannot_retag_the_domains(world):
    """§5.1's domain tagging is the teacher's professional judgement."""
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    services.set_domains(actor=world["dulmaa"], observation=submitted,
                         domains=list(domains_for(world["naran"].pk)[:1]))

    services.update_observation(
        actor=world["bataa_mother"], observation=submitted,
        situation="Засвар", domains=list(domains_for(world["naran"].pk)[:3]),
    )

    assert submitted.domain_links.count() == 1


def test_a_rejected_form_keeps_what_the_user_typed(client, world, daily_type):
    """A validation message that also empties the form is worse than useless."""
    login(client, world["dulmaa"])
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    response = client.post(create_url(world["bataa"]), {
        "type": daily_type.pk,
        "observed_on": tomorrow,        # rejected: §5.1 dates are not future
        "child_did": "Бичсэн текст",
    })

    assert response.status_code == 200
    body = response.content.decode()
    assert tomorrow in body
    assert "Бичсэн текст" in body


# ------------------------------------------------------------------ §5.4 screens

def parent_create_url(child):
    return reverse("observations:parent_create", args=[child.pk])


def test_a_guardian_submits_from_their_own_screen(client, world):
    login(client, world["bataa_mother"])

    assert client.get(parent_create_url(world["bataa"])).status_code == 200

    response = client.post(parent_create_url(world["bataa"]), {
        "observed_on": "2025-10-05",
        "situation": "Оройн хоолны дараа",
        "child_did": "Тоглоомоо өөрөө цэгцэлсэн.",
        "child_said": "«Би том болсон.»",
    })

    assert response.status_code == 302
    submitted = Observation.objects.get(child=world["bataa"])
    assert submitted.source == Observation.Source.PARENT
    assert submitted.review_status == Observation.ReviewStatus.PENDING
    assert submitted.type.code == "parent"
    assert submitted.created_by == world["bataa_mother"]


def test_a_guardian_cannot_open_the_teachers_form(client, world):
    """Not just on POST — a form offering fields the service refuses is a
    form that lies about what it will do."""
    login(client, world["bataa_mother"])

    assert client.get(create_url(world["bataa"])).status_code == 404


def test_a_teacher_cannot_use_the_parent_form(client, world):
    """Their submission is not a §5.4 parent observation."""
    login(client, world["dulmaa"])

    assert client.get(parent_create_url(world["bataa"])).status_code == 404


def test_the_parent_form_is_refused_for_another_childs_parent(client, world):
    login(client, world["bataa_mother"])

    assert client.get(parent_create_url(world["saraa"])).status_code == 404


def test_the_review_queue_shows_only_your_own_childrens_submissions(client,
                                                                    world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    mine = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
        situation="Гэрийн ажиглалт",
    )
    login(client, world["oyun"])

    response = client.get(reverse("observations:review_queue"))

    assert response.status_code == 200
    assert world["bataa"].full_name not in response.content.decode()

    login(client, world["dulmaa"])
    body = client.get(reverse("observations:review_queue")).content.decode()
    assert world["bataa"].full_name in body
    assert mine.summary in body


def test_an_approved_submission_leaves_the_queue(client, world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    submitted = services.create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
    )
    services.review_observation(actor=world["dulmaa"], observation=submitted,
                                status=Observation.ReviewStatus.APPROVED)

    assert submitted not in selectors.pending_parent_observations(
        world["dulmaa"]
    )


# ------------------------------------------------------------------ §11 filters

def test_the_date_interval_filter(client, world, daily_type):
    """RFP §11 — "огнооны интервалаар шүүх"."""
    early = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 9, 1), activity_name="Эрт",
    )
    late = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 12, 1), activity_name="Хожуу",
    )

    found = selectors.child_observations(
        world["dulmaa"], world["bataa"],
        date_from=dt.date(2025, 11, 1), date_to=dt.date(2025, 12, 31),
    )

    assert late in found
    assert early not in found


def test_the_domain_and_level_filters(world, daily_type):
    """RFP §11 — "хөгжлийн чиглэлээр", "үнэлгээний түвшнээр"."""
    domains = list(domains_for(world["naran"].pk)[:2])
    levels = list(levels_for(world["naran"].pk))

    tagged = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
        domains=[(domains[0], levels[0])],
    )
    other = services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 2),
        domains=[(domains[1], levels[3])],
    )

    by_domain = selectors.child_observations(world["dulmaa"], world["bataa"],
                                             domain=domains[0])
    assert tagged in by_domain
    assert other not in by_domain

    by_level = selectors.child_observations(world["dulmaa"], world["bataa"],
                                            level=levels[3])
    assert other in by_level
    assert tagged not in by_level


def test_a_multi_domain_observation_is_not_listed_twice(world, daily_type):
    """The link table means a naive join would duplicate the row."""
    domains = list(domains_for(world["naran"].pk)[:3])
    services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
        domains=[(domain, None) for domain in domains],
    )

    found = selectors.child_observations(world["dulmaa"], world["bataa"],
                                         level=None, domain=domains[0])

    assert found.count() == 1


def test_a_crafted_filter_value_narrows_nothing(client, world, daily_type):
    """A §11 filter is a narrowing. An unknown id must not select rows from
    somewhere else, and a malformed date must not raise."""
    services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )
    login(client, world["dulmaa"])

    response = client.get(
        list_url(world["bataa"])
        + "?domain=nonsense&level=999999&from=not-a-date&type=abc"
    )

    assert response.status_code == 200
    assert response.context["page"].paginator.count == 1


def test_another_kindergartens_domain_filters_nothing(client, world,
                                                      daily_type):
    foreign = DevelopmentDomain.objects.create(
        kindergarten=world["och"], name="Гадны", code="foreign2"
    )
    services.create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily_type,
        observed_on=dt.date(2025, 10, 1),
    )
    login(client, world["dulmaa"])

    response = client.get(f"{list_url(world['bataa'])}?domain={foreign.pk}")

    # The id is not in this kindergarten's list, so it is ignored entirely.
    assert response.status_code == 200
    assert response.context["page"].paginator.count == 1
