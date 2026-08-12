"""The narrative term report — RFP §6.4, §10.2, and the §21 rules."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

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
