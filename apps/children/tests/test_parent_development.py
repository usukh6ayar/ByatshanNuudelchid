"""The parent's development summary — RFP §6.4, added 2026-08-17.

"How is my child developing?" on the child detail screen. It reads
``assessment.selectors.child_assessments``, which for a guardian filters
``visible_to_parents=True`` — so the interesting tests are about what does
**not** appear.

Also pinned: the level's *label*, not a `name` attribute. The template read
`assessment.level.name` until today; `AssessmentLevel` has no such field, and
Django resolves a missing attribute to the empty string rather than raising.
Every parent saw a blank badge and nothing failed.
"""

import pytest
from django.urls import reverse

from apps.assessment import selectors as assessment_selectors
from apps.assessment import services as assessment_services

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def detail_url(child):
    return reverse("children:parent_child_detail", args=[child.pk])


@pytest.fixture
def assessed(world, naran_admin_user):
    """One assessment on Батаа, **published** to the family.

    `Assessment.visible_to_parents` defaults to False — §6.3's grid is a
    working draft a teacher fills in over several sittings, and
    `publish_term` is the deliberate act that opens it. So the fixture takes
    that step rather than setting the flag by hand: a test that wrote the
    column directly would pass even if publishing broke.
    """
    terms = assessment_services.ensure_default_terms(
        actor=naran_admin_user, school_year=world["naran_year"]
    )
    domain = assessment_selectors.domains_for(world["naran"].pk).first()
    level = list(assessment_selectors.levels_for(world["naran"].pk))[2]

    assessment = assessment_services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"], domain=domain,
        term=terms[0], level=level,
    )
    assessment_services.publish_term(
        actor=world["dulmaa"], child=world["bataa"], term=terms[0],
        visible=True,
    )
    assessment.refresh_from_db()
    return {"assessment": assessment, "domain": domain, "level": level,
            "term": terms[0]}


def test_the_domain_and_level_are_named_from_the_configuration(
    client, world, assessed
):
    """§6.1, §6.2 — both are admin-editable, so neither may be hardcoded."""
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Хөгжлийн тойм" in body
    assert assessed["domain"].name in body
    assert assessed["level"].label in body


def test_the_level_label_is_rendered_not_a_missing_attribute(
    client, world, assessed
):
    """The bug this section was carrying until 2026-08-17.

    `AssessmentLevel` has `label`, not `name`. Django resolves a missing
    attribute to "" in a template, so the badge rendered empty and no test
    noticed. Asserted on the badge's own markup rather than on the page, so
    the label being present *somewhere* does not satisfy it.
    """
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()
    section = body.split("Хөгжлийн тойм", 1)[1]

    assert assessed["level"].label in section
    assert str(assessed["level"].value) in section


def test_the_level_colour_comes_from_the_level(client, world, assessed):
    """A domain-tinted level badge reads as a severity scale run backwards."""
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()
    section = body.split("Хөгжлийн тойм", 1)[1].split("</section>", 1)[0]

    assert assessed["level"].color in section


def test_an_assessment_hidden_from_families_does_not_appear(
    client, world, assessed
):
    """RFP §2.3, §6.4 — the teacher decides when a term is shown.

    The gate lives in `child_assessments`; this proves the screen honours it.
    """
    assessment_services.publish_term(
        actor=world["dulmaa"], child=world["bataa"], term=assessed["term"],
        visible=False,
    )

    login(client, world["bataa_mother"])
    body = client.get(detail_url(world["bataa"])).content.decode()

    assert assessed["level"].label not in body
    assert "бүртгэгдээгүй" in body


def test_a_child_with_no_visible_assessment_gets_the_empty_state(client, world):
    """Nothing assessed, or nothing published — the family reads the same.

    Naming the difference would expose that a working draft exists.
    """
    login(client, world["bataa_mother"])

    body = client.get(detail_url(world["bataa"])).content.decode()

    assert "Хөгжлийн тойм" in body
    assert "Одоогоор хөгжлийн үнэлгээ бүртгэгдээгүй байна." in body


def test_the_section_does_not_query_once_per_domain(client, world, assessed,
                                                    naran_admin_user):
    """CLAUDE.md §3.5 — the domain, level and term are all relations."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["bataa_mother"])

    with CaptureQueriesContext(connection) as first:
        client.get(detail_url(world["bataa"]))
    baseline = len(first.captured_queries)

    terms = assessment_selectors.terms_for(world["naran_year"])
    level = list(assessment_selectors.levels_for(world["naran"].pk))[1]
    for domain in list(assessment_selectors.domains_for(world["naran"].pk))[1:5]:
        assessment_services.save_assessment(
            actor=world["dulmaa"], child=world["bataa"], domain=domain,
            term=terms[0], level=level,
        )
    # Published, or the family sees one row in both measurements and the
    # comparison proves nothing.
    assessment_services.publish_term(
        actor=world["dulmaa"], child=world["bataa"], term=terms[0],
        visible=True,
    )

    with CaptureQueriesContext(connection) as second:
        client.get(detail_url(world["bataa"]))

    assert len(second.captured_queries) == baseline, (
        "the development summary issues a query per row — check the "
        "select_related on assessment.selectors.child_assessments"
    )


def test_a_guardian_of_another_child_still_gets_404(client, world):
    """The section changed; the rules did not — CLAUDE.md §4.1."""
    login(client, world["bataa_mother"])

    assert client.get(detail_url(world["saraa"])).status_code == 404
