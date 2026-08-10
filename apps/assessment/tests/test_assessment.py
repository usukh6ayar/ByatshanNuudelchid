"""Development assessment — RFP §6.1–§6.4, and the §21 authorization rules."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.assessment import selectors, services
from apps.assessment.models import (
    Assessment,
    AssessmentLevel,
    AssessmentScale,
    DevelopmentDomain,
    Term,
)
from apps.core.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def child_url(child):
    return reverse("assessment:child", args=[child.pk])


@pytest.fixture
def terms(world, naran_admin_user):
    """RFP §6.4 — the four terms of Naran's school year."""
    return services.ensure_default_terms(actor=naran_admin_user,
                                         school_year=world["naran_year"])


@pytest.fixture
def term(terms):
    return terms[0]


@pytest.fixture
def domain(world):
    return selectors.domains_for(world["naran"].pk).first()


@pytest.fixture
def level(world):
    return selectors.levels_for(world["naran"].pk).first()


# ------------------------------------------------------------------ §21 first
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client.

def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(child_url(world["bataa"])).status_code == 404


def test_guardian_of_another_child_gets_404(client, world):
    login(client, world["bataa_mother"])

    assert client.get(child_url(world["saraa"])).status_code == 404


def test_user_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(child_url(world["bataa"])).status_code == 404


def test_posting_an_assessment_for_another_child_gets_404(client, world, term,
                                                          domain, level):
    login(client, world["oyun"])

    response = client.post(
        reverse("assessment:child_save", args=[world["bataa"].pk]),
        {"term": term.pk, "domain": domain.pk, "level": level.pk},
    )

    assert response.status_code == 404
    assert not Assessment.objects.filter(child=world["bataa"]).exists()


def test_a_guardian_cannot_assess(client, world, term, domain, level):
    """RFP §6.3 names the teacher. Read access is not write access."""
    login(client, world["bataa_mother"])

    response = client.post(
        reverse("assessment:child_save", args=[world["bataa"].pk]),
        {"term": term.pk, "domain": domain.pk, "level": level.pk},
    )

    assert response.status_code == 404
    assert not Assessment.objects.filter(child=world["bataa"]).exists()


def test_the_group_grid_of_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    response = client.get(
        reverse("assessment:group_grid", args=[world["sunflower"].pk])
    )

    assert response.status_code == 404


# ------------------------------------------------------------------ §6.1, §6.2

def test_the_system_defaults_exist():
    """Migration 0002 — without them nothing can be assessed at all."""
    domains = DevelopmentDomain.objects.filter(kindergarten__isnull=True)
    assert domains.count() == 9

    scale = AssessmentScale.objects.get(kindergarten__isnull=True)
    assert scale.levels.count() == 4
    assert [level.value for level in scale.levels.order_by("value")] == [1, 2, 3, 4]


def test_a_kindergarten_sees_the_system_list_plus_its_own(world):
    own = DevelopmentDomain.objects.create(
        kindergarten=world["naran"], name="Хөгжим", code="music", order=20
    )

    naran = list(selectors.domains_for(world["naran"].pk))
    och = list(selectors.domains_for(world["och"].pk))

    assert own in naran
    assert own not in och
    assert len(naran) == len(och) + 1


def test_a_kindergartens_own_scale_wins(world):
    """RFP §6.2 — otherwise defining one would have no effect."""
    own = AssessmentScale.objects.create(
        kindergarten=world["naran"], name="Наран шат", is_default=True
    )
    AssessmentLevel.objects.create(scale=own, value=1, label="Эхлэл")

    assert selectors.scale_for(world["naran"].pk) == own
    assert selectors.scale_for(world["och"].pk).kindergarten_id is None


def test_a_director_may_not_edit_the_shared_list(world, naran_admin_user):
    """One kindergarten renaming a shared domain would rename it everywhere."""
    shared = DevelopmentDomain.objects.get(kindergarten=None, code="language")
    shared.name = "Өөрчилсөн"

    with pytest.raises(ValidationError):
        services.save_config(actor=naran_admin_user, obj=shared, created=False)


# ------------------------------------------------------------------ §6.4 terms

def test_a_new_school_year_gets_four_terms(world, naran_admin_user):
    """Assessment.term is required, so a year without terms is unusable."""
    from apps.tenants.models import SchoolYear
    from apps.tenants.services import save_school_year

    year = SchoolYear(
        kindergarten=world["naran"], name="2026-2027",
        starts_on=dt.date(2026, 9, 1), ends_on=dt.date(2027, 5, 31),
    )
    save_school_year(actor=naran_admin_user, obj=year, created=True)

    terms = list(Term.objects.filter(school_year=year).order_by("number"))
    assert [t.number for t in terms] == [1, 2, 3, 4]
    assert terms[0].starts_on == year.starts_on
    assert terms[-1].ends_on == year.ends_on


def test_terms_are_not_created_twice(world, naran_admin_user, terms):
    again = services.ensure_default_terms(actor=naran_admin_user,
                                          school_year=world["naran_year"])

    assert len(again) == 4
    assert Term.objects.filter(school_year=world["naran_year"]).count() == 4


def test_overlapping_terms_are_rejected(world, naran_admin_user, terms):
    """current_term() picks the first match, so an overlap makes "which term
    is it?" depend on row order."""
    clash = Term(school_year=world["naran_year"], number=1,
                 name="Давхцсан", starts_on=terms[0].starts_on,
                 ends_on=terms[0].ends_on)

    with pytest.raises(ValidationError):
        services.save_term(actor=naran_admin_user, obj=clash, created=True)


def test_a_term_must_fit_inside_its_school_year(world, naran_admin_user):
    stray = Term(school_year=world["naran_year"], number=1, name="Гадуур",
                 starts_on=dt.date(2024, 1, 1), ends_on=dt.date(2024, 3, 1))

    with pytest.raises(ValidationError):
        services.save_term(actor=naran_admin_user, obj=stray, created=True)


def test_current_term_returns_none_outside_the_year(world, terms):
    assert selectors.current_term(world["naran_year"],
                                 dt.date(2030, 7, 1)) is None
    assert selectors.current_term(
        world["naran_year"], terms[0].starts_on
    ) == terms[0]


# ------------------------------------------------------------------ §6.3, §6.4

def test_teacher_records_an_assessment(client, world, term, domain, level):
    login(client, world["dulmaa"])

    response = client.post(
        reverse("assessment:child_save", args=[world["bataa"].pk]),
        {"term": term.pk, "domain": domain.pk, "level": level.pk,
         "comment": "Тогтвортой ахиц."},
    )

    assert response.status_code == 302
    assessment = Assessment.objects.get(child=world["bataa"])
    assert assessment.level == level
    assert assessment.assessed_by == world["dulmaa"]
    assert assessment.kindergarten_id == world["naran"].pk
    assert assessment.enrollment == world["bataa"].enrollments.get()


def test_saving_twice_updates_rather_than_duplicates(world, term, domain,
                                                     level):
    """RFP §17 — "a double-click must not save the same record twice"."""
    other_level = selectors.levels_for(world["naran"].pk).last()

    first = services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain,
        term=term, level=level,
    )
    second = services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain,
        term=term, level=other_level,
    )

    assert first.pk == second.pk
    assert Assessment.objects.filter(child=world["bataa"]).count() == 1
    assert Assessment.objects.get(pk=first.pk).level == other_level


def test_the_database_refuses_a_duplicate(world, term, domain, level):
    """The constraint is the backstop, not the mechanism.

    Even a bug in the service cannot produce two rows for the same
    (child, enrollment, domain, term).
    """
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    enrollment = world["bataa"].enrollments.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        Assessment.objects.create(
            kindergarten=world["naran"], child=world["bataa"],
            enrollment=enrollment, domain=domain, term=term, level=level,
        )


def test_another_kindergartens_level_is_rejected(world, term, domain):
    """§12.3's averages would mix two numbering systems."""
    foreign_scale = AssessmentScale.objects.create(
        kindergarten=world["och"], name="Очны шат", is_default=True
    )
    foreign_level = AssessmentLevel.objects.create(
        scale=foreign_scale, value=1, label="Гадны түвшин"
    )

    with pytest.raises(ValidationError):
        services.save_assessment(
            actor=world["dulmaa"], child=world["bataa"], domain=domain,
            term=term, level=foreign_level,
        )


def test_a_term_from_another_school_year_is_rejected(world, domain, level,
                                                     naran_admin_user):
    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])

    with pytest.raises(ValidationError):
        services.save_assessment(
            actor=world["dulmaa"], child=world["bataa"], domain=domain,
            term=och_terms[0], level=level,
        )


def test_a_child_with_no_enrollment_cannot_be_assessed(world, make_child,
                                                       term, domain, level):
    loose = make_child(world["naran"], first_name="Бүлэггүй")

    with pytest.raises((ValidationError, PermissionDenied)):
        services.save_assessment(
            actor=world["dulmaa"], child=loose, domain=domain, term=term,
            level=level,
        )


# ------------------------------------------------------------------ §2.3

def test_a_guardian_sees_nothing_until_the_term_is_published(world, term,
                                                             domain, level):
    """A half-finished term is worse than an empty one."""
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)

    assert not selectors.child_assessments(world["bataa_mother"],
                                           world["bataa"]).exists()
    assert selectors.child_assessments(world["dulmaa"],
                                       world["bataa"]).count() == 1


def test_publishing_opens_the_term_to_the_guardian(client, world, term,
                                                   domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["dulmaa"])

    response = client.post(
        reverse("assessment:publish", args=[world["bataa"].pk]),
        {"term": term.pk, "visible": "on"},
    )

    assert response.status_code == 302
    assert selectors.child_assessments(world["bataa_mother"],
                                       world["bataa"]).count() == 1


def test_a_guardian_cannot_publish(client, world, term, domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["bataa_mother"])

    response = client.post(
        reverse("assessment:publish", args=[world["bataa"].pk]),
        {"term": term.pk, "visible": "on"},
    )

    assert response.status_code == 404
    assert not selectors.child_assessments(world["bataa_mother"],
                                           world["bataa"]).exists()


# ------------------------------------------------------------------ §6.3 grid

def test_the_group_grid_saves_the_whole_group(client, world, term, domain):
    login(client, world["dulmaa"])
    levels = list(selectors.levels_for(world["naran"].pk))
    grid = selectors.group_grid(world["dulmaa"], world["sunflower"], term,
                                domain)
    assert grid["total"] == 2
    assert grid["missing"] == 2

    response = client.post(
        reverse("assessment:group_grid", args=[world["sunflower"].pk])
        + f"?domain={domain.pk}&term={term.pk}",
        {f"level_{row['enrollment'].pk}": levels[2].pk for row in grid["rows"]},
    )

    assert response.status_code == 302
    assert Assessment.objects.filter(term=term, domain=domain).count() == 2
    after = selectors.group_grid(world["dulmaa"], world["sunflower"], term,
                                 domain)
    assert after["missing"] == 0


def test_the_grid_shows_the_previous_term(world, terms, domain):
    """RFP §6.3 — "өмнөх үнэлгээтэй харьцуулах"."""
    levels = list(selectors.levels_for(world["naran"].pk))
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=terms[0], level=levels[1])

    grid = selectors.group_grid(world["dulmaa"], world["sunflower"], terms[1],
                                domain)
    row = next(r for r in grid["rows"] if r["child"] == world["bataa"])

    assert row["previous"] == levels[1]
    assert row["assessment"] is None


def test_the_grid_does_not_query_per_child(world, terms, domain, make_child):
    """CLAUDE.md §3.5 — §6.3 is the screen a teacher opens most often."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def count_with(children: int) -> int:
        for index in range(children):
            make_child(world["naran"], world["sunflower"],
                       first_name=f"Хүүхэд{index}")
        with CaptureQueriesContext(connection) as captured:
            selectors.group_grid(world["dulmaa"], world["sunflower"],
                                 terms[1], domain)
        return len(captured)

    assert count_with(3) == count_with(10)


def test_the_grid_skips_ids_the_teacher_cannot_reach(world, terms, domain,
                                                     make_group, make_child):
    """A crafted post naming another group's enrollment saves nothing."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    outsider = make_child(world["naran"], other_group, first_name="Гадны")
    levels = list(selectors.levels_for(world["naran"].pk))

    saved = services.save_group_assessments(
        actor=world["dulmaa"], group=world["sunflower"], term=terms[0],
        domain=domain,
        entries={outsider.enrollments.get().pk: levels[0].pk},
    )

    assert saved == 0
    assert not Assessment.objects.filter(child=outsider).exists()


# ------------------------------------------------------------------ §971

def test_assessing_writes_an_audit_row(world, term, domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE,
        actor_user=world["dulmaa"],
        object_type="assessment.Assessment",
    ).exists()


def test_the_matrix_lays_out_domains_against_terms(world, terms, domain,
                                                   level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=terms[2], level=level)

    matrix = selectors.assessment_matrix(world["dulmaa"], world["bataa"],
                                         world["naran_year"])

    assert len(matrix["terms"]) == 4
    row = next(r for r in matrix["rows"] if r["domain"] == domain)
    assert row["cells"][2].level == level
    assert row["cells"][0] is None


# ------------------------------------------------------------------ rendering

def test_the_child_screen_renders_for_both_roles(client, world, term, domain,
                                                 level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    services.publish_term(actor=world["dulmaa"], child=world["bataa"],
                          term=term, visible=True)

    for user in [world["dulmaa"], world["bataa_mother"]]:
        login(client, user)
        response = client.get(child_url(world["bataa"]))
        assert response.status_code == 200, user
        assert domain.name in response.content.decode()


def test_the_group_grid_renders(client, world, term, domain):
    login(client, world["dulmaa"])

    response = client.get(
        reverse("assessment:group_grid", args=[world["sunflower"].pk])
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert world["bataa"].full_name in body
    assert "Түргэн үнэлгээ" in body


def test_the_child_screen_explains_a_missing_enrollment(client, world,
                                                        make_child):
    """Rather than rendering an empty grid with no explanation."""
    loose = make_child(world["naran"], first_name="Бүлэггүй")
    admin = world["dulmaa"]
    from apps.accounts.models import Membership, Role
    Membership.objects.create(user=admin, kindergarten=world["naran"],
                              role=Role.ADMIN)
    login(client, admin)

    response = client.get(child_url(loose))

    assert response.status_code == 200
    assert "бүлэгт бүртгэлгүй" in response.content.decode()


# ------------------------------------------------ writes across a transfer
# can_record_for_child survives a transfer on purpose — a teacher must be
# able to correct the records they wrote. That is not permission to write
# new ones inside the kindergarten the child moved to (RFP §3.2).

@pytest.fixture
def transferred(world, naran_admin_user):
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
    world["och_terms"] = services.ensure_default_terms(
        actor=naran_admin_user, school_year=world["och_year"]
    )
    return world


def test_the_previous_teacher_cannot_assess_at_the_new_kindergarten(
    transferred, domain
):
    """The row would land in Och, a tenant Dulmaa is not part of."""
    och_domain = selectors.domains_for(transferred["och"].pk).first()
    och_level = selectors.levels_for(transferred["och"].pk).first()

    with pytest.raises(PermissionDenied):
        services.save_assessment(
            actor=transferred["dulmaa"], child=transferred["bataa"],
            domain=och_domain, term=transferred["och_terms"][0],
            level=och_level,
        )

    assert not Assessment.objects.filter(kindergarten=transferred["och"]).exists()


def test_the_new_teacher_may_assess(transferred):
    och_domain = selectors.domains_for(transferred["och"].pk).first()
    och_level = selectors.levels_for(transferred["och"].pk).first()

    assessment = services.save_assessment(
        actor=transferred["oyun"], child=transferred["bataa"],
        domain=och_domain, term=transferred["och_terms"][0], level=och_level,
    )

    assert assessment.kindergarten_id == transferred["och"].pk


def test_publishing_only_opens_your_own_kindergartens_rows(transferred,
                                                           naran_admin_user):
    """After a transfer a term can hold rows from both sides."""
    och_domain = selectors.domains_for(transferred["och"].pk).first()
    och_level = selectors.levels_for(transferred["och"].pk).first()
    theirs = services.save_assessment(
        actor=transferred["oyun"], child=transferred["bataa"],
        domain=och_domain, term=transferred["och_terms"][0], level=och_level,
    )

    changed = services.publish_term(
        actor=transferred["dulmaa"], child=transferred["bataa"],
        term=transferred["och_terms"][0], visible=True,
    )

    assert changed == 0
    theirs.refresh_from_db()
    assert theirs.visible_to_parents is False


# ------------------------------------------------------------------ §6.4 date

def test_publishing_does_not_restamp_the_assessment_date(world, term, domain,
                                                         level):
    """§6.4 wants the date the judgement was made, not the last touch."""
    assessment = services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain, term=term,
        level=level,
    )
    original = assessment.assessed_at

    services.publish_term(actor=world["dulmaa"], child=world["bataa"],
                          term=term, visible=True)

    assessment.refresh_from_db()
    assert assessment.assessed_at == original


def test_reassessing_does_move_the_date(world, term, domain, level):
    assessment = services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain, term=term,
        level=level,
    )
    original = assessment.assessed_at

    services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain, term=term,
        level=selectors.levels_for(world["naran"].pk).last(),
    )

    assessment.refresh_from_db()
    assert assessment.assessed_at > original


# ------------------------------------------------------------------ §6.1 again

def test_another_kindergartens_domain_is_rejected(world, term, level):
    """The mirror of the level check — §12.3 averages would be polluted."""
    foreign = DevelopmentDomain.objects.create(
        kindergarten=world["och"], name="Гадны чиглэл", code="foreign"
    )

    with pytest.raises(ValidationError):
        services.save_assessment(
            actor=world["dulmaa"], child=world["bataa"], domain=foreign,
            term=term, level=level,
        )


def test_the_grid_survives_a_crafted_field_name(world, term, domain):
    """Form field names are attacker-controlled; nothing may raise a 500."""
    saved = services.save_group_assessments(
        actor=world["dulmaa"], group=world["sunflower"], term=term,
        domain=domain, entries={"'; DROP TABLE": "abc", "7": "not-a-number"},
    )

    assert saved == 0


# ------------------------------------------------------------------ §3.2

def test_a_term_carries_its_kindergarten(world, terms):
    """CLAUDE.md §3.2 — one filter enforces the isolation."""
    for row in terms:
        assert row.kindergarten_id == world["naran"].pk
