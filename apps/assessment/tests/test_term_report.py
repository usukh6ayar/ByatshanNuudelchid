"""The narrative term report — RFP §6.4, §10.2, and the §21 rules."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.assessment import selectors, services
from apps.assessment.models import Assessment, TermReport

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


@pytest.fixture
def terms(world, naran_admin_user):
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


def test_a_term_report_carries_the_four_narrative_fields(world, term):
    """RFP §6.4's list, minus the per-domain comment Assessment already holds."""
    from apps.children.services import current_enrollment

    enrollment = current_enrollment(world["bataa"])
    report = TermReport.objects.create(
        kindergarten=world["naran"],
        child=world["bataa"],
        enrollment=enrollment,
        term=term,
        strengths="Гүйлт сайн",
        needs_support="Тэнцвэр алдах нь ажиглагддаг",
        next_goals="Тэнцвэрийн дасгал тогтмол хийх",
        advice_for_parents="Гэртээ тэнцвэрийн дасгал тоглоно уу",
    )

    assert report.status == TermReport.Status.DRAFT
    assert report.finalized_at is None
    assert report.deleted_at is None


def test_one_report_per_child_per_term(world, term):
    """§17 — a double-click must not produce a second report."""
    from apps.children.services import current_enrollment

    enrollment = current_enrollment(world["bataa"])
    fields = {"kindergarten": world["naran"], "child": world["bataa"],
              "enrollment": enrollment, "term": term}
    TermReport.objects.create(**fields, strengths="Эхний")

    with pytest.raises(IntegrityError), transaction.atomic():
        TermReport.objects.create(**fields, strengths="Хоёр дахь")


NARRATIVE = {
    "strengths": "Гүйлт сайн",
    "needs_support": "Тэнцвэр алдах нь ажиглагддаг",
    "next_goals": "Тэнцвэрийн дасгал тогтмол хийх",
    "advice_for_parents": "Гэртээ тэнцвэрийн дасгал тоглоно уу",
}


def test_saving_twice_updates_one_row(world, term):
    """Idempotent on (child, enrollment, term) — the same shape as
    save_assessment. The constraint is the backstop, not the mechanism."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    report = services.save_term_report(
        actor=world["dulmaa"], child=world["bataa"], term=term,
        **NARRATIVE | {"strengths": "Зассан"},
    )

    assert TermReport.objects.count() == 1
    assert report.strengths == "Зассан"
    assert report.author == world["dulmaa"]


def test_a_guardian_cannot_write_a_term_report(world, term):
    """§6.4 is the teacher's professional judgement — can_record_for_child."""
    with pytest.raises(PermissionDenied):
        services.save_term_report(actor=world["bataa_mother"],
                                  child=world["bataa"], term=term,
                                  **NARRATIVE)


def test_a_teacher_from_another_kindergarten_cannot_write_one(world, term):
    with pytest.raises(PermissionDenied):
        services.save_term_report(actor=world["oyun"], child=world["bataa"],
                                  term=term, **NARRATIVE)


def test_a_term_from_another_school_year_is_refused(world, term,
                                                    naran_admin_user):
    """§3.2 — a crafted request must not file a report against another
    kindergarten's term."""
    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])

    with pytest.raises(ValidationError):
        services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                                  term=och_terms[0], **NARRATIVE)


def transfer_bataa_to_och(world):
    """Bataa moves from Наран to Оч mid-year. Used by the §1.2 tests here
    and in Task 4, so it is a helper rather than a copy in each."""
    import datetime as dt

    from apps.children.models import Enrollment

    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED, ended_on=dt.date(2026, 1, 15)
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"],
        group=world["petal"], school_year=world["och_year"],
        started_on=dt.date(2026, 1, 16),
    )
    world["bataa"].kindergarten = world["och"]
    world["bataa"].save()


def test_a_transferred_childs_report_keeps_its_kindergarten(world, term):
    """CLAUDE.md §1.2 — the report stays filed against the kindergarten it
    was written in, so a transfer does not hand it to the new one.

    Whether each user can then *read* it is the selector's job, tested in
    Task 4 once ``term_report`` exists."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    transfer_bataa_to_och(world)

    report = TermReport.objects.get()
    assert report.kindergarten_id == world["naran"].pk


def test_saving_writes_an_audit_row(world, term):
    """RFP §971 — who wrote what about which child."""
    from apps.core.models import AuditAction, AuditLog

    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE, actor_user=world["dulmaa"],
        object_type="assessment.TermReport",
    ).exists()


def test_finalizing_also_publishes_the_terms_assessments(world, term, domain,
                                                         level):
    """The one-button contract. A teacher has one mental model: the term is
    finished or it is not."""
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    report = services.finalize_term(actor=world["dulmaa"],
                                    child=world["bataa"], term=term)

    assert report.status == TermReport.Status.FINAL
    assert report.finalized_at is not None
    assert Assessment.objects.get(child=world["bataa"],
                                  term=term).visible_to_parents is True


def test_finalizing_an_empty_report_is_refused(world, term):
    """Four blank headings are worse than nothing — the same question D5
    settled for the printed portfolio."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term)

    with pytest.raises(ValidationError):
        services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                               term=term)

    assert TermReport.objects.get().status == TermReport.Status.DRAFT


def test_finalizing_without_a_report_is_refused(world, term):
    with pytest.raises(ValidationError):
        services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                               term=term)


def test_a_guardian_cannot_finalize(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    with pytest.raises(PermissionDenied):
        services.finalize_term(actor=world["bataa_mother"],
                               child=world["bataa"], term=term)


def test_reopening_hides_the_assessments_again(world, term, domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = services.reopen_term(actor=world["dulmaa"], child=world["bataa"],
                                  term=term)

    assert report.status == TermReport.Status.DRAFT
    assert report.finalized_at is None
    assert Assessment.objects.get(child=world["bataa"],
                                  term=term).visible_to_parents is False


def test_editing_a_final_report_leaves_it_final(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = services.save_term_report(
        actor=world["dulmaa"], child=world["bataa"], term=term,
        **NARRATIVE | {"strengths": "Үсгийн алдаа зассан"},
    )

    assert report.status == TermReport.Status.FINAL
    assert report.finalized_at is not None


def test_a_guardian_cannot_see_a_draft_report(world, term):
    """RFP §2.3 — "багшийн зөвшөөрсөн"."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    assert selectors.term_report(world["dulmaa"], world["bataa"], term)
    assert selectors.term_report(world["bataa_mother"], world["bataa"],
                                 term) is None


def test_a_guardian_sees_it_once_finalized(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = selectors.term_report(world["bataa_mother"], world["bataa"], term)

    assert report is not None
    assert report.strengths == NARRATIVE["strengths"]


def test_another_kindergarten_sees_nothing(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    assert selectors.term_report(world["oyun"], world["bataa"], term) is None


def test_after_a_transfer_the_author_keeps_it_and_the_new_school_does_not(
    world, term
):
    """CLAUDE.md §1.2, the read half. Task 2 pinned where the row is filed;
    this pins who can still see it."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    transfer_bataa_to_och(world)

    assert selectors.term_report(world["dulmaa"], world["bataa"], term)
    assert selectors.term_report(world["oyun"], world["bataa"], term) is None


def test_term_reports_for_maps_term_id_to_report(world, terms):
    """The child screen needs one lookup, not one query per term."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=terms[0], **NARRATIVE)

    found = selectors.term_reports_for(world["dulmaa"], world["bataa"])

    assert set(found) == {terms[0].pk}


# ------------------------------------------------------------------ §21
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client. A
# view that forgets its check passes every service-level test above.

def report_url(child, term):
    return reverse("assessment:term_report", args=[child.pk, term.pk])


def test_teacher_from_another_group_gets_404(client, world, term,
                                             make_teacher, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_guardian_of_another_child_gets_404(client, world, term,
                                            make_guardian, make_child):
    elsewhere = make_child(world["naran"], world["sunflower"],
                           first_name="Өөр")
    outsider = make_guardian(elsewhere, world["naran"],
                             username="other_mother")
    login(client, outsider)

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_user_from_another_kindergarten_gets_404(client, world, term):
    login(client, world["oyun"])

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_the_childs_own_guardian_cannot_reach_the_editor(client, world, term):
    """§6.4 is the teacher's record. This family may read the finished
    report on the assessment screen; writing it is a different permission."""
    login(client, world["bataa_mother"])

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_a_term_from_another_year_gets_404(client, world, term,
                                           naran_admin_user):
    """A real term id, reached through a child it does not apply to."""
    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])
    login(client, world["dulmaa"])

    url = report_url(world["bataa"], och_terms[0])
    assert client.get(url).status_code == 404
    assert not TermReport.objects.exists()


def test_the_teacher_writes_and_finalizes_from_the_screen(client, world, term,
                                                          domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["dulmaa"])
    url = report_url(world["bataa"], term)

    assert client.get(url).status_code == 200

    assert client.post(url, NARRATIVE | {"action": "save"}).status_code == 302
    assert TermReport.objects.get().status == TermReport.Status.DRAFT

    assert client.post(url, NARRATIVE | {"action": "finalize"}).status_code == 302
    assert TermReport.objects.get().status == TermReport.Status.FINAL
    assert Assessment.objects.get().visible_to_parents is True


def test_finalizing_an_empty_report_from_the_screen_explains_itself(
    client, world, term
):
    login(client, world["dulmaa"])

    response = client.post(report_url(world["bataa"], term),
                           {"action": "finalize"}, follow=True)

    assert response.status_code == 200
    assert "Хоосон" in response.content.decode()
    assert TermReport.objects.get().status == TermReport.Status.DRAFT


def test_a_guardian_sees_the_finished_report_on_the_child_screen(client, world,
                                                                 term):
    """§2.3 — the family reads it where they already read the matrix."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    login(client, world["bataa_mother"])
    child_screen = reverse("assessment:child", args=[world["bataa"].pk])

    assert NARRATIVE["strengths"] not in client.get(child_screen).content.decode()

    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    assert NARRATIVE["strengths"] in client.get(child_screen).content.decode()
