"""Child portfolio — RFP §4.1, §4.2, §4.3, and the §21 authorization rules."""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.core.models import AuditAction, AuditLog
from apps.portfolio import selectors, services
from apps.portfolio.models import AboutMe, BirthdayNote, ChildAgeProfile
from apps.portfolio.zodiac import year_animal, zodiac_sign

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def overview(child):
    return reverse("portfolio:overview", args=[child.pk])


def about_url(child):
    return reverse("portfolio:about_me_edit", args=[child.pk])


def age_url(child, age):
    return reverse("portfolio:age_profile_edit", args=[child.pk, age])


# ------------------------------------------------------------------ §21 first
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client.

@pytest.mark.parametrize("url_for", [overview, about_url])
def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group, url_for):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(url_for(world["bataa"])).status_code == 404


@pytest.mark.parametrize("url_for", [overview, about_url])
def test_guardian_of_another_child_gets_404(client, world, url_for):
    login(client, world["bataa_mother"])

    assert client.get(url_for(world["saraa"])).status_code == 404


@pytest.mark.parametrize("url_for", [overview, about_url])
def test_user_from_another_kindergarten_gets_404(client, world, url_for):
    login(client, world["oyun"])

    assert client.get(url_for(world["bataa"])).status_code == 404


def test_posting_to_another_childs_portfolio_gets_404(client, world):
    """Writing is access too, so it goes through the same check."""
    login(client, world["bataa_mother"])

    response = client.post(about_url(world["saraa"]), {"dream": "Халдлага"})

    assert response.status_code == 404
    assert not AboutMe.objects.filter(child=world["saraa"]).exists()


# ------------------------------------------------------------------ About Me

def test_teacher_can_fill_in_about_me(client, world):
    login(client, world["dulmaa"])

    response = client.post(about_url(world["bataa"]), {
        "introduction": "Хөгжилтэй, найрсаг хүүхэд.",
        "name_meaning": "Бат бөх гэсэн утгатай.",
        "dream": "Нисгэгч болох",
        "height_cm": "104.5", "weight_kg": "17.20",
        "recorded_on": "2026-05-01",
    })

    assert response.status_code == 302
    about = AboutMe.objects.get(child=world["bataa"])
    assert about.dream == "Нисгэгч болох"
    assert about.kindergarten_id == world["bataa"].kindergarten_id


def test_guardian_can_fill_in_about_me(client, world):
    """RFP §2.3 lists this as a guardian capability, not only a teacher one."""
    login(client, world["bataa_mother"])

    client.post(about_url(world["bataa"]), {"dream": "Эмч болох"})

    assert AboutMe.objects.get(child=world["bataa"]).dream == "Эмч болох"


def test_saving_twice_updates_rather_than_duplicates(client, world):
    login(client, world["dulmaa"])

    client.post(about_url(world["bataa"]), {"dream": "Эхний"})
    client.post(about_url(world["bataa"]), {"dream": "Хоёр дахь"})

    assert AboutMe.objects.filter(child=world["bataa"]).count() == 1
    assert AboutMe.objects.get(child=world["bataa"]).dream == "Хоёр дахь"


def test_about_me_records_who_changed_it(world, naran_admin_user):
    """RFP §4.1 requires the change history."""
    services.save_about_me(actor=naran_admin_user, child=world["bataa"],
                           dream="Эхний")
    services.save_about_me(actor=world["dulmaa"], child=world["bataa"],
                           dream="Засварласан")

    about = AboutMe.objects.get(child=world["bataa"])
    assert about.created_by_id == naran_admin_user.pk
    assert about.updated_by_id == world["dulmaa"].pk
    assert about.history.count() == 2


def test_unknown_field_is_rejected(world, naran_admin_user):
    with pytest.raises(ValidationError):
        services.save_about_me(actor=naran_admin_user, child=world["bataa"],
                               kindergarten_id=999)


def test_service_refuses_an_unauthorized_actor(world):
    with pytest.raises(PermissionDenied):
        services.save_about_me(actor=world["oyun"], child=world["bataa"],
                               dream="Халдлага")


# ------------------------------------------------------------------ ages 2–5

def test_age_profile_is_created_per_age(client, world):
    login(client, world["dulmaa"])

    client.post(age_url(world["bataa"], 3), {"favorite_color": "Улаан"})
    client.post(age_url(world["bataa"], 4), {"favorite_color": "Ногоон"})

    assert ChildAgeProfile.objects.filter(child=world["bataa"]).count() == 2
    assert selectors.age_profile(world["bataa"], 3).favorite_color == "Улаан"


def test_age_outside_two_to_five_is_rejected(client, world):
    login(client, world["dulmaa"])

    assert client.get(age_url(world["bataa"], 7)).status_code == 404


def test_overview_shows_all_four_ages_even_when_empty(client, world):
    """An empty page should read as "not filled in", not "does not exist"."""
    login(client, world["dulmaa"])

    profiles = client.get(overview(world["bataa"])).context["age_profiles"]

    assert sorted(profiles) == [2, 3, 4, 5]
    assert all(value is None for value in profiles.values())


# ------------------------------------------------------------------ two voices
# §4.3 keeps эцэг эхийн and багшийн тэмдэглэл apart.

def test_guardian_may_write_only_the_parent_note(world):
    editable = services.editable_age_profile_fields(
        world["bataa_mother"], world["bataa"]
    )
    assert "parent_note" in editable
    assert "teacher_note" not in editable


def test_teacher_may_write_only_the_teacher_note(world):
    editable = services.editable_age_profile_fields(
        world["dulmaa"], world["bataa"]
    )
    assert "teacher_note" in editable
    assert "parent_note" not in editable


def test_guardian_cannot_overwrite_the_teacher_note(world, naran_admin_user):
    """Reached only by a crafted request — the form never renders the field."""
    services.save_age_profile(actor=world["dulmaa"], child=world["bataa"],
                              age=3, teacher_note="Багшийн ажиглалт")

    with pytest.raises(ValidationError):
        services.save_age_profile(
            actor=world["bataa_mother"], child=world["bataa"], age=3,
            teacher_note="Дарж бичих оролдлого",
        )

    profile = selectors.age_profile(world["bataa"], 3)
    assert profile.teacher_note == "Багшийн ажиглалт"


def test_the_two_notes_coexist(world):
    services.save_age_profile(actor=world["dulmaa"], child=world["bataa"],
                              age=3, teacher_note="Багшийнх")
    services.save_age_profile(actor=world["bataa_mother"], child=world["bataa"],
                              age=3, parent_note="Эцэг эхийнх")

    profile = selectors.age_profile(world["bataa"], 3)
    assert profile.teacher_note == "Багшийнх"
    assert profile.parent_note == "Эцэг эхийнх"


def test_the_form_hides_the_other_sides_note(client, world):
    login(client, world["bataa_mother"])

    body = client.get(age_url(world["bataa"], 3)).content.decode()

    assert 'name="parent_note"' in body
    assert 'name="teacher_note"' not in body


# ------------------------------------------------------------------ §4.2

def test_birthday_facts_are_computed_not_stored(world):
    """§206 — a stored copy goes stale when a birth date is corrected."""
    child = world["bataa"]
    child.date_of_birth = dt.date(2021, 4, 15)
    child.save()

    facts = selectors.birth_facts(child)

    assert facts["year_animal"] == "Үхэр"      # 2021
    assert facts["zodiac_sign"] == "Хонь"      # 15 April
    assert "year_animal" not in [f.name for f in child._meta.get_fields()]


@pytest.mark.parametrize(("year", "animal"), [
    (2020, "Хулгана"), (2021, "Үхэр"), (2024, "Луу"), (2019, "Гахай"),
])
def test_year_animal_cycle(year, animal):
    assert year_animal(dt.date(year, 6, 1)) == animal


@pytest.mark.parametrize(("month", "day", "sign"), [
    (1, 5, "Матар"), (1, 25, "Хумх"), (4, 15, "Хонь"), (12, 31, "Матар"),
])
def test_zodiac_boundaries(month, day, sign):
    assert zodiac_sign(dt.date(2021, month, day)) == sign


def test_birthday_note_is_saved_per_age(client, world):
    login(client, world["dulmaa"])
    url = reverse("portfolio:birthday_note_edit", args=[world["bataa"].pk, 3])

    client.post(url, {"note": "Гэр бүлээрээ тэмдэглэсэн."})

    assert BirthdayNote.objects.get(child=world["bataa"], age=3).note


def test_birthday_list_stops_at_the_current_age(world):
    child = world["bataa"]
    child.date_of_birth = dt.date(2021, 4, 15)
    child.save()

    ages = [entry["age"] for entry in selectors.birthdays(child)]

    assert ages == list(range(1, max(ages) + 1))
    assert max(ages) == selectors.birth_facts(child)["age"]


# ------------------------------------------------------------------ audit

def test_opening_the_portfolio_is_audited(client, world):
    """RFP §971 — a portfolio view is a meaningful access."""
    login(client, world["dulmaa"])

    client.get(overview(world["bataa"]))

    entry = AuditLog.objects.filter(action=AuditAction.VIEW).latest("created_at")
    assert entry.child_id == world["bataa"].pk
    assert entry.metadata["section"] == "portfolio"
