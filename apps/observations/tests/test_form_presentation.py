"""The §5.1 entry form's structure — the parts that fail silently.

Presentation tests, deliberately few. Layout is judged by looking at the
screen; what is worth pinning here is the handful of things that look fine in
a browser and are wrong anyway:

* the five sections the form is grouped into, because a future edit that
  drops one loses a whole class of field with no error;
* that the create form offers **no file input**, because
  ``media:observation_attach`` needs a saved ``observation_id`` and a
  plausible-looking upload control on a new form would be a dead end the
  teacher only discovers after typing everything;
* that a rejected form gives back what was typed, which is the difference
  between a validation message and losing five minutes of work.
"""

import datetime as dt
import re

import pytest
from django.urls import reverse

from apps.observations.models import ObservationType
from apps.observations.services import create_observation

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"

SECTIONS = [
    "Ажиглалт",
    "Нөхцөл байдал",
    "Багшийн дүгнэлт",
    "Эцэг эхэд харагдах байдал",
    "Зураг",
]


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def create_url(child):
    return reverse("observations:create", args=[child.pk])


@pytest.fixture
def observation(world):
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    return create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
    )


def test_the_create_form_shows_all_five_sections(client, world):
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    for section in SECTIONS:
        assert section in body, f"section missing from the form: {section}"


def test_the_edit_form_shows_all_five_sections(client, world, observation):
    login(client, world["dulmaa"])

    url = reverse("observations:edit",
                  args=[world["bataa"].pk, observation.pk])
    body = client.get(url).content.decode()

    for section in SECTIONS:
        assert section in body, f"section missing from the edit form: {section}"


def test_the_form_names_the_child_it_is_recording_for(client, world):
    """Reached from four screens; the subject is never left to memory."""
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    assert world["bataa"].full_name in body


def test_the_create_form_offers_no_upload_control(client, world):
    """Attaching needs a saved observation — spec section 7.1.

    ``media:observation_attach`` takes an ``observation_id``, so there is
    nothing for a file input on this page to post to. The section explains
    that instead of rendering a control that cannot work.
    """
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    assert 'type="file"' not in body
    assert "хадгалсны дараа" in body


def test_the_edit_form_links_to_the_upload_screen(client, world, observation):
    """Once the record exists, the existing pipeline is one tap away."""
    login(client, world["dulmaa"])

    url = reverse("observations:edit",
                  args=[world["bataa"].pk, observation.pk])
    body = client.get(url).content.decode()

    assert reverse("media:observation_attach",
                   args=[world["bataa"].pk, observation.pk]) in body


def test_a_rejected_form_gives_back_what_was_typed(client, world):
    """Losing the text is worse than the mistake that caused the rejection."""
    login(client, world["dulmaa"])

    response = client.post(create_url(world["bataa"]), {
        # No type: the service rejects this.
        "observed_on": "2025-10-01",
        "activity_name": "Блокоор барих",
        "situation": "Хосоороо тоглож байхад",
    })
    body = response.content.decode()

    assert response.status_code == 200
    assert "msg--error" in body
    assert "Блокоор барих" in body
    assert "Хосоороо тоглож байхад" in body


def test_a_guardian_cannot_open_the_teachers_form(client, world):
    """§5.4 gives families their own screen — CLAUDE.md §4.1."""
    login(client, world["bataa_mother"])

    assert client.get(create_url(world["bataa"])).status_code == 404


# ---------------------------------------------------------------- density
# Checkpoint 4, 2026-08-17. The form kept every field and every rule; what
# changed is how much room it takes to show them. These pin the parts of that
# which a later edit could quietly undo.


def test_the_form_is_held_to_a_reading_width(client, world):
    """A form that spans a 1440px screen puts a date field and its label at
    opposite ends of the same row, and turns every textarea into a very wide,
    very short letterbox."""
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text()
    block = css.split(".formpage {", 1)[1].split("}", 1)[0]

    assert "max-width" in block


def test_no_section_heading_is_repeated_by_its_first_field(client, world):
    """"Нөхцөл байдал" was the section title *and* its first label, so the
    words appeared twice in a row for no gain."""
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()
    form = body.split("<form", 1)[1]

    assert form.count("Нөхцөл байдал") == 1


def test_the_five_sections_survived_the_density_pass(client, world):
    """The point was less bulk, not fewer fields. If a section vanished while
    tightening spacing, this is what says so."""
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    for section in SECTIONS:
        assert section in body, f"section lost in the density pass: {section}"


def test_every_field_still_reaches_the_view(client, world):
    """The names `_posted()` reads. Renaming one while restyling would leave
    a form that looks right and drops what a teacher typed."""
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    for name in ("observed_on", "type", "activity_name", "situation",
                 "child_did", "child_said", "teacher_comment", "next_steps",
                 "visible_to_parents", "include_in_report", "domains"):
        assert f'name="{name}"' in body, f"field missing from the form: {name}"


# ------------------------------------------------ entry points, 2026-08-18
# The child page now offers one card per §5.2 type instead of a single
# "Ажиглалт нэмэх". That is only honest if the card actually lands on its own
# type, so `?type=` preselects — and the preselection must not have picked up
# any of the form's other defaults on the way.


def test_a_type_in_the_query_string_preselects_it(client, world):
    """The child page's per-type cards each carry `?type=`. Without this the
    three cards are three doors into the same room."""
    login(client, world["dulmaa"])
    artwork = ObservationType.objects.get(kindergarten=None, code="artwork")

    body = client.get(f"{create_url(world['bataa'])}?type={artwork.pk}").content.decode()
    selected = re.findall(r'<option value="(\d+)"\s+selected', body)

    assert selected == [str(artwork.pk)]


def test_a_form_opened_without_a_type_preselects_nothing(client, world):
    """Unchanged behaviour: the browser falls back to the first option, which
    is what it did before `?type=` existed."""
    login(client, world["dulmaa"])

    body = client.get(create_url(world["bataa"])).content.decode()

    assert re.findall(r'<option value="(\d+)"\s+selected', body) == []


def test_a_bogus_type_is_ignored_rather_than_answered(client, world):
    """`?type=` is not validated — an id that matches no option simply leaves
    the select alone. It must not error, and it must not select anything."""
    login(client, world["dulmaa"])

    response = client.get(f"{create_url(world['bataa'])}?type=999999")
    body = response.content.decode()

    assert response.status_code == 200
    assert re.findall(r'<option value="(\d+)"\s+selected', body) == []


def test_preselecting_a_type_does_not_tick_parent_visibility(client, world):
    """The 2026-08-16 privacy decision: a new observation is **not** visible
    to families until a teacher says so. `?type=` puts a value into `form`,
    which is the same dict the visibility checkbox reads — this is what says
    it stayed empty."""
    login(client, world["dulmaa"])
    artwork = ObservationType.objects.get(kindergarten=None, code="artwork")

    body = client.get(f"{create_url(world['bataa'])}?type={artwork.pk}").content.decode()

    assert not re.search(r'id="id_visible"[^>]*checked', body)
    # The report checkbox is ticked by default and must have stayed that way.
    assert re.search(r'id="id_report"[^>]*checked', body)
