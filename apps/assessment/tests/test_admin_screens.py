"""The administrator's configuration screens — RFP §6.1, §6.2, §6.4.

Terms and development domains, replacing the last two Django admin
changelists in the sidebar. The interesting rule here is the shared system
list: a director may read it and may not edit it, because renaming "Хэл
яриа" in one kindergarten would rename it in all of them (CLAUDE.md §2.3).
"""

import pytest
from django.urls import reverse

from apps.assessment.models import DevelopmentDomain, Term

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"

SCREENS = [
    "assessment:admin_term_list",
    "assessment:admin_domain_list",
    "assessment:admin_domain_create",
]


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


@pytest.fixture
def terms(world, naran_admin_user):
    from apps.assessment import services

    return services.ensure_default_terms(actor=naran_admin_user,
                                         school_year=world["naran_year"])


# ------------------------------------------------------------------ §2.1

@pytest.mark.parametrize("name", SCREENS)
def test_a_teacher_cannot_reach_the_configuration(client, world, name):
    """§6.1 says the administrator edits the criteria, not a teacher."""
    login(client, world["dulmaa"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", SCREENS)
def test_a_guardian_cannot_reach_the_configuration(client, world, name):
    login(client, world["bataa_mother"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", SCREENS)
def test_an_anonymous_request_goes_to_the_login_page(client, world, name):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


# ------------------------------------------------------------------- terms

def test_a_director_sees_their_years_terms(client, world, make_admin, terms):
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("assessment:admin_term_list")).content.decode()

    assert terms[0].name in html


def test_a_year_with_no_terms_offers_to_create_them(client, world,
                                                    make_admin):
    """A year without terms means nothing can be assessed at all."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("assessment:admin_term_list")).content.decode()

    assert "Дөрвөн улирлыг үүсгэх" in html


def test_a_director_creates_the_four_default_terms(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("assessment:admin_term_defaults"),
                           {"year": world["naran_year"].pk})

    assert response.status_code == 302
    assert Term.objects.filter(school_year=world["naran_year"]).count() == 4


def test_a_director_cannot_create_terms_in_another_kindergarten(
    client, world, make_admin
):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("assessment:admin_term_defaults"),
                           {"year": world["och_year"].pk})

    assert response.status_code == 404
    assert not Term.objects.filter(school_year=world["och_year"]).exists()


def test_the_defaults_button_refuses_a_get(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    assert client.get(
        reverse("assessment:admin_term_defaults")
    ).status_code == 404


def test_a_director_edits_a_term(client, world, make_admin, terms):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(
        reverse("assessment:admin_term_edit", args=[terms[0].pk]),
        {"name": "Намрын улирал",
         "starts_on": terms[0].starts_on.isoformat(),
         "ends_on": terms[0].ends_on.isoformat()},
    )

    assert response.status_code == 302
    terms[0].refresh_from_db()
    assert terms[0].name == "Намрын улирал"


def test_a_term_ending_before_it_starts_is_refused(client, world, make_admin,
                                                   terms):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(
        reverse("assessment:admin_term_edit", args=[terms[0].pk]),
        {"name": "Буруу", "starts_on": "2026-05-01", "ends_on": "2026-04-01"},
    )

    assert response.status_code == 200
    terms[0].refresh_from_db()
    assert terms[0].name != "Буруу"


def test_a_director_cannot_edit_another_kindergartens_term(
    client, world, make_admin, naran_admin_user
):
    from apps.assessment import services

    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])
    login(client, make_admin(world["naran"], username="naran_boss"))

    assert client.get(
        reverse("assessment:admin_term_edit", args=[och_terms[0].pk])
    ).status_code == 404


# ----------------------------------------------------------------- domains

def test_the_domain_list_shows_the_system_defaults_as_read_only(
    client, world, make_admin
):
    """CLAUDE.md §2.3 — a director extends the shared list, never edits it."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("assessment:admin_domain_list")).content.decode()

    assert "Системийн үндсэн" in html
    assert "Засах боломжгүй" in html


def test_a_director_cannot_open_a_system_domains_edit_form(client, world,
                                                            make_admin):
    system = DevelopmentDomain.objects.filter(kindergarten__isnull=True).first()
    login(client, make_admin(world["naran"], username="naran_boss"))

    assert client.get(
        reverse("assessment:admin_domain_edit", args=[system.pk])
    ).status_code == 404


def test_a_director_adds_a_domain_to_their_own_kindergarten(client, world,
                                                             make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("assessment:admin_domain_create"), {
        "kindergarten": world["naran"].pk,
        "name": "Хөгжим",
        "code": "music",
        "order": "10",
        "color": "#aa3366",
        "is_active": "on",
    })

    assert response.status_code == 302
    domain = DevelopmentDomain.objects.get(code="music")
    assert domain.kindergarten_id == world["naran"].pk


def test_a_director_cannot_add_a_domain_to_another_kindergarten(
    client, world, make_admin
):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("assessment:admin_domain_create"), {
        "kindergarten": world["och"].pk,
        "name": "Халдлага",
        "code": "attack",
    })

    assert response.status_code == 200
    assert not DevelopmentDomain.objects.filter(code="attack").exists()


def test_a_domain_without_a_code_is_refused(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("assessment:admin_domain_create"), {
        "kindergarten": world["naran"].pk,
        "name": "Нэртэй",
        "code": "  ",
    })

    assert response.status_code == 200
    assert "Кодыг оруулна уу" in response.content.decode()
