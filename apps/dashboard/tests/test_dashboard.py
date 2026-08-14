"""Dashboards — RFP §12.1, §12.2.

A dashboard is a place where a counting mistake becomes a disclosure: a tile
that says "26 children" to a teacher responsible for 12 has told them
something about the other 14.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.assessment import selectors as assessment_selectors
from apps.assessment import services as assessment_services
from apps.comms import services as comms_services
from apps.dashboard import selectors
from apps.dashboard.tasks import refresh_admin_dashboards
from apps.observations.models import Observation, ObservationType
from apps.observations.services import create_observation

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


@pytest.fixture
def terms(world, naran_admin_user):
    return assessment_services.ensure_default_terms(
        actor=naran_admin_user, school_year=world["naran_year"]
    )


# ------------------------------------------------------------------ §21

def test_a_guardian_cannot_open_the_teacher_dashboard(client, world):
    login(client, world["bataa_mother"])

    assert client.get(reverse("dashboard:teacher")).status_code == 404


def test_a_teacher_cannot_open_the_admin_dashboard(client, world):
    """§12.2 counts across the whole kindergarten — that is a director's view."""
    login(client, world["dulmaa"])

    assert client.get(reverse("dashboard:admin")).status_code == 404


def test_the_teacher_count_is_their_own_children_only(world, make_group,
                                                      make_child):
    """RFP §21.2 — a tile must not count children they cannot see."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    make_child(world["naran"], other_group, first_name="Гадны")
    make_child(world["och"], world["petal"], first_name="Очны")

    figures = selectors.teacher_dashboard(world["dulmaa"])

    assert figures["child_count"] == 2      # Bataa and Saraa only


def test_a_director_sees_only_their_kindergarten(world, make_child):
    make_child(world["och"], world["petal"], first_name="Очны")

    scoped = selectors.compute_admin_dashboard([world["naran"].pk])
    everything = selectors.compute_admin_dashboard(None)

    assert scoped["children"] == 2
    assert everything["children"] == 3
    assert scoped["kindergartens"] == 1
    assert everything["kindergartens"] == 2


def test_the_two_scopes_do_not_share_a_cache_entry(world, make_child):
    """One director must not read another kindergarten's figures."""
    make_child(world["och"], world["petal"], first_name="Очны")

    naran = selectors.admin_dashboard([world["naran"].pk])
    och = selectors.admin_dashboard([world["och"].pk])

    assert naran["children"] == 2
    assert och["children"] == 1


# ------------------------------------------------------------------ §12.1

def test_todays_birthdays_are_listed(world, make_child):
    today = dt.date.today()
    birthday_child = make_child(world["naran"], world["sunflower"],
                                first_name="Төрсөн")
    birthday_child.date_of_birth = today.replace(year=today.year - 4)
    birthday_child.save()

    figures = selectors.teacher_dashboard(world["dulmaa"], today=today)

    assert birthday_child in figures["birthdays_today"]
    assert world["bataa"] not in figures["birthdays_today"]


def test_children_missing_assessments_are_named(world, terms):
    """RFP §12.1 — "үнэлгээ нь дутуу хүүхдүүд"."""
    domain = assessment_selectors.domains_for(world["naran"].pk).first()
    level = assessment_selectors.levels_for(world["naran"].pk).first()
    assessment_services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain,
        term=terms[0], level=level,
    )

    figures = selectors.teacher_dashboard(
        world["dulmaa"], today=terms[0].starts_on
    )

    # Bataa has one of nine domains, so both children are still short.
    assert world["bataa"] in figures["missing_assessments"]
    assert world["saraa"] in figures["missing_assessments"]
    assert figures["assessment_progress"]["done"] == 1
    assert figures["assessment_progress"]["expected"] == 18   # 2 × 9


def test_a_fully_assessed_child_drops_off_the_missing_list(world, terms):
    domains = list(assessment_selectors.domains_for(world["naran"].pk))
    level = assessment_selectors.levels_for(world["naran"].pk).first()
    for domain in domains:
        assessment_services.save_assessment(
            actor=world["dulmaa"], child=world["bataa"], domain=domain,
            term=terms[0], level=level,
        )

    figures = selectors.teacher_dashboard(world["dulmaa"],
                                          today=terms[0].starts_on)

    assert world["bataa"] not in figures["missing_assessments"]
    assert world["saraa"] in figures["missing_assessments"]


def test_domain_averages_use_the_level_value(world, terms):
    """§6.2 lets an administrator rename a level; the number is what averages."""
    domain = assessment_selectors.domains_for(world["naran"].pk).first()
    levels = list(assessment_selectors.levels_for(world["naran"].pk))

    assessment_services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain,
        term=terms[0], level=levels[0],       # value 1
    )
    assessment_services.save_assessment(
        actor=world["dulmaa"], child=world["saraa"], domain=domain,
        term=terms[0], level=levels[2],       # value 3
    )

    figures = selectors.teacher_dashboard(world["dulmaa"],
                                          today=terms[0].starts_on)
    row = next(r for r in figures["domain_averages"] if r["name"] == domain.name)

    assert row["average"] == 2.0
    assert row["count"] == 2


def test_a_year_without_terms_does_not_crash_the_screen(client, world):
    """A director who has not configured terms yet still gets a dashboard."""
    login(client, world["dulmaa"])

    response = client.get(reverse("dashboard:teacher"))

    assert response.status_code == 200
    assert "улирал тохируулаагүй" in response.content.decode()


def test_pending_parent_notes_are_counted(world):
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
        situation="Гэрийн ажиглалт",
    )

    figures = selectors.teacher_dashboard(world["dulmaa"])

    assert figures["pending_reviews"] == 1
    assert len(figures["recent_parent_notes"]) == 1


def test_recent_observations_are_this_teachers_children(world, make_group,
                                                        make_child,
                                                        make_teacher):
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    outsider_child = make_child(world["naran"], other_group,
                                first_name="Гадны")
    other_teacher = make_teacher(world["naran"], other_group,
                                 username="other_teacher")
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    theirs = create_observation(
        actor=other_teacher, child=outsider_child, type=daily,
        observed_on=dt.date(2025, 10, 1), activity_name="Өөр бүлэг",
    )

    figures = selectors.teacher_dashboard(world["dulmaa"])

    assert theirs not in figures["recent_observations"]


# ------------------------------------------------------------------ §12.2

def test_the_admin_figures_come_from_the_cache(world, make_child):
    """CLAUDE.md §6 — not recomputed on every page load."""
    first = selectors.admin_dashboard([world["naran"].pk])
    make_child(world["naran"], world["sunflower"], first_name="Шинэ")

    cached = selectors.admin_dashboard([world["naran"].pk])
    assert cached["children"] == first["children"]

    refreshed = selectors.admin_dashboard([world["naran"].pk], refresh=True)
    assert refreshed["children"] == first["children"] + 1


def test_the_beat_task_warms_every_scope(world):
    from django.core.cache import cache

    cache.clear()

    assert refresh_admin_dashboards() == 3      # system-wide + two kindergartens
    assert cache.get(selectors._admin_key(None)) is not None
    assert cache.get(selectors._admin_key([world["naran"].pk])) is not None


def test_storage_and_report_figures_are_present(world):
    figures = selectors.compute_admin_dashboard([world["naran"].pk])

    for key in ["storage_bytes", "file_count", "reports_total",
                "reports_failed", "failed_logins_7d", "logins_7d"]:
        assert key in figures


# ------------------------------------------------------------------ screens

def test_the_teacher_dashboard_renders(client, world, terms):
    comms_services.publish(
        actor=world["dulmaa"],
        announcement=comms_services.save_announcement(
            actor=world["dulmaa"], kindergarten_id=world["naran"].pk,
            title="Эцэг эхийн хурал", body="Пүрэв гарагт.",
        ),
    )
    login(client, world["dulmaa"])

    body = client.get(reverse("dashboard:teacher")).content.decode()

    assert "Хяналтын самбар" in body
    assert "Эцэг эхийн хурал" in body


def test_the_admin_dashboard_renders(client, world, naran_admin_user):
    login(client, naran_admin_user)

    response = client.get(reverse("dashboard:admin"))

    assert response.status_code == 200
    assert "Удирдлагын самбар" in response.content.decode()


def test_login_lands_on_the_right_dashboard(client, world, naran_admin_user):
    login(client, world["dulmaa"])
    assert client.get("/").url == reverse("dashboard:teacher")

    login(client, naran_admin_user)
    assert client.get("/").url == reverse("dashboard:admin")

    login(client, world["bataa_mother"])
    assert client.get("/").url == reverse("children:parent_home")


# ------------------------------------------------------------------ §6.4

def test_the_term_track_marks_past_current_and_future(world, terms):
    """RFP §6.4 — the year's four terms, and where it has got to.

    The dashboard used to name only the open term, which is the smaller
    half of what a teacher wants to know.
    """
    import datetime as dt

    # A day inside the second term, whatever dates ensure_default_terms
    # chose for this year.
    inside_second = terms[1].starts_on + dt.timedelta(days=1)

    track = selectors.teacher_dashboard(world["dulmaa"],
                                        today=inside_second)["term_track"]

    assert [step["state"] for step in track] == [
        "done", "current", "ahead", "ahead",
    ]
    assert [step["term"].pk for step in track] == [t.pk for t in terms]


def test_the_track_survives_the_summer_gap(world, terms):
    """Between years there is no current term. The strip still has to draw:
    a teacher opening the dashboard in August should see the year's shape,
    not an empty panel."""
    import datetime as dt

    after_the_year = terms[-1].ends_on + dt.timedelta(days=20)

    track = selectors.teacher_dashboard(world["dulmaa"],
                                        today=after_the_year)["term_track"]

    assert len(track) == 4
    assert {step["state"] for step in track} == {"done"}


def test_a_year_with_no_terms_has_no_track(world):
    """Nothing configured yet — the template hides the card rather than
    drawing an empty line."""
    assert selectors.teacher_dashboard(world["dulmaa"])["term_track"] == []


def test_the_track_reaches_the_dashboard(client, world, terms):
    """Through the HTTP client, because a selector returning the right list
    proves nothing if the template never draws it.

    Asserts on four steps rather than on a current one: the fixture's school
    year is fixed and today eventually walks past its end, which is the
    summer case the test above covers deliberately."""
    login(client, world["dulmaa"])

    html = client.get(reverse("dashboard:teacher")).content.decode()

    assert "Хичээлийн жилийн явц" in html
    assert html.count("track__step track__step--") == 4
