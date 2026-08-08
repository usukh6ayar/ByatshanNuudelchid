"""The mandatory authorization tests — CLAUDE.md §4.1, RFP §21.2–21.4.

Every assertion goes through the HTTP client. §21.4 is a claim about request
handling ("changing the URL must not reveal another child's data"), not about
what a helper returns: a view that forgets to call the permission layer passes
every function-level test in ``apps/core/tests/test_permissions.py``.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def child_urls(child):
    """Every teacher-facing URL that exposes one child."""
    return [
        reverse("children:detail", args=[child.pk]),
        reverse("children:guardian_add", args=[child.pk]),
    ]


# ------------------------------------------------------------------ the three
# Required for every new view touching child data.

@pytest.mark.parametrize("url_index", [0, 1])
def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group, url_index):
    """RFP §21.2 — a teacher sees only the children they are responsible for."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other_group, username="stranger")
    login(client, stranger)

    response = client.get(child_urls(world["bataa"])[url_index])

    assert response.status_code == 404


@pytest.mark.parametrize("url_index", [0, 1])
def test_guardian_of_another_child_gets_404(client, world, url_index):
    """RFP §21.3 — a guardian sees only children linked to them."""
    login(client, world["bataa_mother"])

    response = client.get(child_urls(world["saraa"])[url_index])

    assert response.status_code == 404


@pytest.mark.parametrize("url_index", [0, 1])
def test_user_from_another_kindergarten_gets_404(client, world, url_index):
    """RFP §21.4 — no cross-tenant access, whatever the URL says."""
    login(client, world["oyun"])

    response = client.get(child_urls(world["bataa"])[url_index])

    assert response.status_code == 404


# ------------------------------------------------------------------ parent side

def test_guardian_cannot_open_another_childs_parent_page(client, world):
    login(client, world["bataa_mother"])

    url = reverse("children:parent_child_detail", args=[world["saraa"].pk])

    assert client.get(url).status_code == 404


def test_switching_to_a_child_that_is_not_theirs_gets_404(client, world):
    """The ?child= parameter is an id in a URL like any other."""
    login(client, world["bataa_mother"])

    response = client.get(reverse("children:parent_home"),
                          {"child": world["saraa"].pk})

    assert response.status_code == 404


def test_teacher_cannot_use_the_parent_child_page(client, world):
    """The parent page is guardian-only, even for a teacher who may see the child."""
    login(client, world["dulmaa"])

    url = reverse("children:parent_child_detail", args=[world["bataa"].pk])

    assert client.get(url).status_code == 404


# ------------------------------------------------------------------ lists leak too

def test_list_does_not_show_another_kindergartens_children(client, world,
                                                           make_child):
    """A list is a disclosure surface as much as a detail page is."""
    make_child(world["och"], world["petal"], first_name="Дүү")
    login(client, world["dulmaa"])

    body = client.get(reverse("children:list")).content.decode()

    assert "Батаа" in body
    assert "Дүү" not in body


def test_search_cannot_reach_outside_the_users_scope(client, world, make_child):
    """Filters narrow what is visible; they must never widen it.

    Asserts on the result set rather than the page text: the form echoes the
    search term back into its own input, which is the user's own keystrokes,
    not a disclosure.
    """
    make_child(world["och"], world["petal"], first_name="Дүү")
    login(client, world["dulmaa"])

    response = client.get(reverse("children:list"), {"q": "Дүү"})

    assert list(response.context["page"].object_list) == []
    assert "Хүүхэд олдсонгүй" in response.content.decode()


def test_teacher_cannot_register_a_child_into_another_teachers_group(
    client, world, make_teacher, make_group
):
    """The form would otherwise accept any group id — RFP §21.2."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other_group, username="stranger")
    login(client, stranger)

    response = client.post(reverse("children:create"), {
        "group": world["sunflower"].pk,      # not theirs
        "last_name": "Овог", "first_name": "Оролдлого",
        "national_id": "XX99999999", "sex": "male",
        "date_of_birth": "2021-05-05",
    })

    assert response.status_code == 200
    from apps.children.models import Child
    assert not Child.objects.filter(first_name="Оролдлого").exists()


# ------------------------------------------------------------------ anonymous

@pytest.mark.parametrize("name", [
    "children:list", "children:create", "children:parent_home",
])
def test_anonymous_users_are_sent_to_login(client, name):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


# ------------------------------------------------------------------ granted

def test_assigned_teacher_can_open_the_child(client, world):
    login(client, world["dulmaa"])

    response = client.get(reverse("children:detail", args=[world["bataa"].pk]))

    assert response.status_code == 200
    assert "Батаа" in response.content.decode()


def test_guardian_can_open_their_own_child(client, world):
    login(client, world["bataa_mother"])

    response = client.get(
        reverse("children:parent_child_detail", args=[world["bataa"].pk])
    )

    assert response.status_code == 200


def test_kindergarten_admin_can_open_the_child(client, world, make_admin):
    admin = make_admin(world["naran"], username="naran_admin")
    login(client, admin)

    response = client.get(reverse("children:detail", args=[world["bataa"].pk]))

    assert response.status_code == 200
