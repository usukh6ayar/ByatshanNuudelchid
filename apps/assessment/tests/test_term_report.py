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
    fields = dict(kindergarten=world["naran"], child=world["bataa"],
                  enrollment=enrollment, term=term)
    TermReport.objects.create(**fields, strengths="Эхний")

    with pytest.raises(IntegrityError), transaction.atomic():
        TermReport.objects.create(**fields, strengths="Хоёр дахь")
