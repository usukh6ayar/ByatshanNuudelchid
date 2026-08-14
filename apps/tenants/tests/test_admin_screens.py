"""The administrator's own kindergarten and group screens — RFP §2.1, §3.2.

These replaced Django admin changelists. The admin site enforced its scoping
through ``TenantScopedAdmin``; these views have to enforce the same rule
themselves, and a view that forgets is exactly what CLAUDE.md §4.1 exists to
catch — so every check below goes through the HTTP client.
"""

import pytest
from django.urls import reverse

from apps.tenants.models import Group, Kindergarten

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


LIST_URLS = ["tenants:kindergarten_list", "tenants:group_list"]
CREATE_URLS = ["tenants:kindergarten_create", "tenants:group_create"]


# ------------------------------------------------------------------ §21, §2.1
# A teacher is staff but not an administrator. RFP §2.1 lists kindergarten,
# group and teacher management as the administrator's, and §21.4 says an
# unauthorized URL must not reveal that it exists — hence 404, not 403.

@pytest.mark.parametrize("name", LIST_URLS + CREATE_URLS)
def test_a_teacher_cannot_reach_the_admin_screens(client, world, name):
    login(client, world["dulmaa"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", LIST_URLS + CREATE_URLS)
def test_a_guardian_cannot_reach_the_admin_screens(client, world, name):
    login(client, world["bataa_mother"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", LIST_URLS)
def test_an_anonymous_request_is_sent_to_the_login_page(client, world, name):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_a_director_sees_only_their_own_kindergarten(client, world,
                                                     make_admin):
    """RFP §3.2 — one kindergarten's data is invisible to another's staff."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("tenants:kindergarten_list")).content.decode()

    assert world["naran"].name in html
    assert world["och"].name not in html


def test_a_director_cannot_open_another_kindergartens_edit_form(
    client, world, make_admin
):
    """A real id, reached by someone with no membership for it."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    url = reverse("tenants:kindergarten_edit", args=[world["och"].pk])

    assert client.get(url).status_code == 404
    assert client.post(url, {"name": "Хулгайлсан"}).status_code == 404
    world["och"].refresh_from_db()
    assert world["och"].name == "Оч"


def test_a_director_cannot_open_another_kindergartens_group(client, world,
                                                            make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    url = reverse("tenants:group_edit", args=[world["petal"].pk])

    assert client.get(url).status_code == 404


def test_a_director_sees_only_their_own_groups(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("tenants:group_list")).content.decode()

    assert world["sunflower"].name in html
    assert world["petal"].name not in html


# ------------------------------------------------------------------ the work

def test_a_director_creates_a_kindergarten(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("tenants:kindergarten_create"), {
        "name": "Шинэ цэцэрлэг",
        "address": "УБ, СБД",
        "phone": "70001234",
        "is_active": "on",
    })

    assert response.status_code == 302
    assert Kindergarten.objects.filter(name="Шинэ цэцэрлэг").exists()


def test_a_kindergarten_without_a_name_is_refused(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))
    before = Kindergarten.objects.count()

    response = client.post(reverse("tenants:kindergarten_create"),
                           {"name": "   "})

    assert response.status_code == 200
    assert "нэрийг оруулна уу" in response.content.decode()
    assert Kindergarten.objects.count() == before


def test_a_director_edits_their_own_kindergarten(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(
        reverse("tenants:kindergarten_edit", args=[world["naran"].pk]),
        {"name": "Наран шинэчилсэн", "phone": "70009999", "is_active": "on"},
    )

    assert response.status_code == 302
    world["naran"].refresh_from_db()
    assert world["naran"].name == "Наран шинэчилсэн"


def test_a_director_creates_a_group_in_their_own_year(client, world,
                                                      make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("tenants:group_create"), {
        "name": "Сарнай",
        "age_category": "3–4 нас",
        "school_year": world["naran_year"].pk,
        "status": Group.Status.ACTIVE,
    })

    assert response.status_code == 302
    group = Group.objects.get(name="Сарнай")
    # The kindergarten comes from the school year, not from the form.
    assert group.kindergarten_id == world["naran"].pk


def test_a_group_cannot_be_filed_against_another_kindergartens_year(
    client, world, make_admin
):
    """§3.2 — the crafted post the form's own dropdown cannot produce."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("tenants:group_create"), {
        "name": "Халдлага",
        "school_year": world["och_year"].pk,
        "status": Group.Status.ACTIVE,
    })

    assert response.status_code == 200
    assert not Group.objects.filter(name="Халдлага").exists()


def test_the_list_counts_children_without_a_query_per_row(
    client, world, make_admin, django_assert_num_queries, make_child
):
    """CLAUDE.md §3.5 — the counts are annotated, not looked up per row."""
    for i in range(6):
        make_child(world["naran"], world["sunflower"], first_name=f"Хүүхэд{i}")
    login(client, make_admin(world["naran"], username="naran_boss"))

    with django_assert_num_queries(13):
        client.get(reverse("tenants:kindergarten_list"))

    # The real claim: the count does not grow with the rows. Six more
    # children and six more groups must not cost anything.
    for i in range(6):
        make_child(world["naran"], world["sunflower"], first_name=f"Дахин{i}")

    with django_assert_num_queries(13):
        client.get(reverse("tenants:kindergarten_list"))
