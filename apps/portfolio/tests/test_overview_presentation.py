"""The portfolio overview's presentation — what a redesign could silently break.

This page is not only a hub. It is the **only** place a birthday note can be
written: ``portfolio:birthday_note_edit`` is POST-only and redirects back
here. So the inline editor is functionality, not decoration, and a redesign
that tidied it away would remove a §4.2 capability with nothing to catch it.

The same applies to the two edit routes it links to. §2.3 gives a family
write access here as well as a teacher, so both roles must keep every action;
``editable_age_profile_fields`` splits only ``parent_note`` from
``teacher_note``, and that split lives on the age form, not on this screen.

What is pinned:

* one birthday form per birthday, each posting to its own age
* the field name ``note`` — the endpoint reads nothing else
* About Me and every age page reachable, for **both** roles
* the query count flat as the number of filled ages grows
"""

import pytest
from django.urls import reverse

from apps.portfolio.models import BirthdayNote

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def overview_url(child):
    return reverse("portfolio:overview", args=[child.pk])


ROLES = [
    pytest.param("dulmaa", id="teacher"),
    pytest.param("bataa_mother", id="guardian"),
]


# ------------------------------------------------------------ both roles

@pytest.mark.parametrize("who", ROLES)
def test_both_roles_reach_the_about_me_editor(client, world, who):
    """§2.3 — a family writes here too. Neither role is read-only."""
    login(client, world[who])

    body = client.get(overview_url(world["bataa"])).content.decode()

    assert reverse("portfolio:about_me_edit", args=[world["bataa"].pk]) in body


@pytest.mark.parametrize("who", ROLES)
def test_both_roles_reach_every_age_page(client, world, who):
    """§4.3 — one page per year from two to five, filled or not."""
    login(client, world[who])

    body = client.get(overview_url(world["bataa"])).content.decode()

    for age in (2, 3, 4, 5):
        url = reverse("portfolio:age_profile_edit",
                      args=[world["bataa"].pk, age])
        assert url in body, f"age {age} is not reachable from the overview"


@pytest.mark.parametrize("who", ROLES)
def test_both_roles_reach_the_photo_and_the_pdf(client, world, who):
    login(client, world[who])

    body = client.get(overview_url(world["bataa"])).content.decode()

    assert reverse("media:child_photo", args=[world["bataa"].pk]) in body
    assert reverse("reports:request", args=[world["bataa"].pk]) in body


# ------------------------------------------------------- birthday notes

@pytest.mark.parametrize("who", ROLES)
def test_a_birthday_form_exists_for_each_birthday(client, world, who):
    """One form per birthday, each posting to its own age.

    A single form around all of them would make one save blank the rest,
    because the endpoint writes the note it is given for the age in its URL.
    """
    login(client, world[who])

    response = client.get(overview_url(world["bataa"]))
    body = response.content.decode()

    birthdays = response.context["birthdays"]
    assert birthdays, "the fixture child should have had at least one birthday"

    for entry in birthdays:
        action = reverse("portfolio:birthday_note_edit",
                         args=[world["bataa"].pk, entry["age"]])
        assert action in body, f"no form for the age-{entry['age']} birthday"


@pytest.mark.parametrize("who", ROLES)
def test_the_birthday_field_is_still_called_note(client, world, who):
    """The endpoint reads `request.POST["note"]` and nothing else."""
    login(client, world[who])

    body = client.get(overview_url(world["bataa"])).content.decode()

    assert 'name="note"' in body


@pytest.mark.parametrize("who", ROLES)
def test_saving_a_birthday_note_still_works(client, world, who):
    """End to end, for both roles — §4.2 is not a staff-only capability."""
    login(client, world[who])
    url = reverse("portfolio:birthday_note_edit", args=[world["bataa"].pk, 2])

    response = client.post(url, {"note": "Бүлгээрээ тэмдэглэв."})

    assert response.status_code == 302
    assert response.url == overview_url(world["bataa"])
    assert BirthdayNote.objects.get(
        child=world["bataa"], age=2
    ).note == "Бүлгээрээ тэмдэглэв."


def test_a_saved_note_comes_back_in_its_own_field(client, world):
    """The value has to land in the right form, not merely on the page."""
    login(client, world["dulmaa"])
    client.post(
        reverse("portfolio:birthday_note_edit", args=[world["bataa"].pk, 2]),
        {"note": "ХОЁР"},
    )

    body = client.get(overview_url(world["bataa"])).content.decode()
    field = body.split('id="id_note_2"', 1)[1].split(">", 1)[0]

    assert "ХОЁР" in field


# ------------------------------------------------------------ the states

def test_an_empty_about_me_offers_the_way_in(client, world):
    login(client, world["dulmaa"])

    body = client.get(overview_url(world["bataa"])).content.decode()

    assert "бөглөгдөөгүй" in body
    assert "Бөглөж эхлэх" in body


def test_an_unfilled_age_is_marked_empty_and_still_opens(client, world):
    """An empty year is one waiting to be written, not one that is missing."""
    login(client, world["dulmaa"])

    body = client.get(overview_url(world["bataa"])).content.decode()

    assert "Хоосон" in body
    assert reverse("portfolio:age_profile_edit",
                   args=[world["bataa"].pk, 2]) in body


# ---------------------------------------------------------- performance

def test_the_page_does_not_query_once_per_age(client, world):
    """CLAUDE.md §3.5 — cost must not grow as the portfolio fills up."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.portfolio import services

    login(client, world["dulmaa"])

    with CaptureQueriesContext(connection) as first:
        client.get(overview_url(world["bataa"]))
    baseline = len(first.captured_queries)

    for age in (2, 3, 4, 5):
        services.save_age_profile(
            actor=world["dulmaa"], child=world["bataa"], age=age,
            favorite_color="Ногоон",
        )

    with CaptureQueriesContext(connection) as second:
        client.get(overview_url(world["bataa"]))

    assert len(second.captured_queries) == baseline, (
        "the overview issues a query per age page — check "
        "portfolio.selectors.age_profiles"
    )


# -------------------------------------------------------- authorization

def test_a_guardian_of_another_child_gets_404(client, world):
    """CLAUDE.md §4.1 — the redesign changed the markup, not the rules."""
    login(client, world["bataa_mother"])

    assert client.get(overview_url(world["saraa"])).status_code == 404


def test_a_teacher_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(overview_url(world["bataa"])).status_code == 404
