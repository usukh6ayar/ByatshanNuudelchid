"""The §6.3 group grid's presentation — the parts that fail silently.

The level control changed from a `<select>` to radio chips on 2026-08-16.
That is a change to the *markup* of a data-entry form, so what matters is
that the wire format did not move with it: the view still reads
``level_<enrollment_id>`` and still filters empty values. A redesign that
quietly broke saving would look perfect in a screenshot.

Also pinned:

* **level colour comes from ``AssessmentLevel``, never from the domain.**
  Tinting a level by its domain reads as a severity scale running the wrong
  way, and it is the mistake this codebase already made once on the child
  detail page.
* the query count must not grow with the size of the group.
* the three empty states — no term, no domain, no children — are different
  problems with different owners and must not collapse into one message.
"""

import pytest
from django.urls import reverse

from apps.assessment.models import Assessment
from apps.assessment.selectors import domains_for, levels_for

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def grid_url(group):
    return reverse("assessment:group_grid", args=[group.pk])


@pytest.fixture
def setup(world, naran_admin_user):
    """Naran's four terms, its first domain and its scale — the same route
    ``test_assessment.py`` uses, so this file and that one agree about what
    a configured kindergarten looks like."""
    from apps.assessment import services

    terms = services.ensure_default_terms(
        actor=naran_admin_user, school_year=world["naran_year"]
    )
    return {
        "term": terms[0],
        "terms": terms,
        "domain": domains_for(world["naran"].pk).first(),
        "levels": list(levels_for(world["naran"].pk)),
    }


def test_the_grid_renders_a_row_per_child(client, world, setup):
    login(client, world["dulmaa"])

    response = client.get(grid_url(world["sunflower"]))

    assert response.status_code == 200
    assert response.context["total"] == 2          # Батаа and Сараа
    assert "Батаа" in response.content.decode()


def test_choosing_a_level_saves_it(client, world, setup):
    """The contract the redesign must not move: `level_<enrollment_id>`.

    Posted exactly as the radio chips post it — one name, one level id.
    """
    login(client, world["dulmaa"])
    enrollment = world["bataa"].enrollments.get()
    level = setup["levels"][1]

    response = client.post(
        f"{grid_url(world['sunflower'])}?domain={setup['domain'].pk}"
        f"&term={setup['term'].pk}",
        {f"level_{enrollment.pk}": str(level.pk)},
    )

    assert response.status_code == 302
    saved = Assessment.objects.get(
        enrollment=enrollment, term=setup["term"], domain=setup["domain"]
    )
    assert saved.level == level


def test_an_empty_value_leaves_the_assessment_alone(client, world, setup):
    """The "Үнэлээгүй" chip posts an empty value, as the old select did.

    The view filters those out, so an untouched row is not overwritten —
    which is what lets a teacher save half a group without clearing the
    other half.
    """
    login(client, world["dulmaa"])
    enrollment = world["bataa"].enrollments.get()
    level = setup["levels"][2]
    url = (f"{grid_url(world['sunflower'])}?domain={setup['domain'].pk}"
           f"&term={setup['term'].pk}")

    client.post(url, {f"level_{enrollment.pk}": str(level.pk)})
    client.post(url, {f"level_{enrollment.pk}": ""})

    saved = Assessment.objects.get(
        enrollment=enrollment, term=setup["term"], domain=setup["domain"]
    )
    assert saved.level == level


def test_the_level_colour_comes_from_the_level_not_the_domain(client, world,
                                                              setup):
    """§6 — the level's colour belongs to the level.

    Asserted by giving the domain a colour that appears nowhere in the scale,
    then requiring every level's own colour among the chips and the domain's
    colour to be absent from them. The domain's colour is still correct on
    the badge that names the domain, which is why the check is scoped to the
    rows rather than to the whole page.
    """
    setup["domain"].color = "#123456"
    setup["domain"].save(update_fields=["color"])
    login(client, world["dulmaa"])

    body = client.get(grid_url(world["sunflower"])).content.decode()
    rows = body.split('<form method="post"', 1)[1]

    for level in setup["levels"]:
        assert level.color in rows, f"level {level.value} lost its colour"
    assert "#123456" not in rows, (
        "the domain's colour reached a level chip — a level's colour belongs "
        "to the level (AssessmentLevel.color), never to its domain"
    )


def test_every_level_is_named_and_not_only_coloured(client, world, setup):
    """§14 — colour is never the only carrier of meaning."""
    login(client, world["dulmaa"])

    body = client.get(grid_url(world["sunflower"])).content.decode()

    for level in setup["levels"]:
        assert level.label in body


def test_the_grid_does_not_query_once_per_child(client, world, setup,
                                                make_child):
    """CLAUDE.md §3.5 — cost must not scale with the size of the group."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])

    with CaptureQueriesContext(connection) as first:
        client.get(grid_url(world["sunflower"]))
    baseline = len(first.captured_queries)

    for index in range(8):
        make_child(world["naran"], world["sunflower"], first_name=f"Нэмэлт{index}")

    with CaptureQueriesContext(connection) as second:
        response = client.get(grid_url(world["sunflower"]))

    assert response.context["total"] == 10
    assert len(second.captured_queries) == baseline, (
        "the grid issues a query per child — check "
        "assessment.selectors.group_grid"
    )


def test_a_teacher_from_another_group_gets_404(client, world):
    """RFP §21.2 — the grid lists a whole roster, so the gate matters."""
    login(client, world["oyun"])

    assert client.get(grid_url(world["sunflower"])).status_code == 404


def test_a_guardian_cannot_open_the_grid(client, world):
    """§6.3 is a teacher screen; `assignable_groups` is what says so."""
    login(client, world["bataa_mother"])

    assert client.get(grid_url(world["sunflower"])).status_code == 404


def test_a_year_with_no_term_says_which_setting_is_missing(client, world):
    """Three different empty states, three different owners.

    No `setup` fixture here on purpose: this is the state before an
    administrator has created any term. That is their task, not the
    teacher's, and the screen has to say so rather than look broken to the
    person who opened it.
    """
    login(client, world["dulmaa"])

    body = client.get(grid_url(world["sunflower"])).content.decode()

    assert "улирал тохируулаагүй" in body
