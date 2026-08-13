"""Each role gets its own shell — RFP §13.

Written after a director was found reading the teacher's menu on every
screen except the dashboard: "Хянах ажиглалт" for groups they do not teach,
and no route to the kindergartens they administer. The rule was duplicated
across nine views, so nine places had to agree and one of them was the
dashboard alone.

These assert on the rendered page rather than on ``layout_for`` directly.
The function returning the right string proves nothing if a view never asks
it — the same reason CLAUDE.md §4.1 insists authorization tests go through
the HTTP client.
"""

import pytest
from django.urls import reverse

from apps.core.layouts import ADMIN, PARENT, TEACHER, layout_for

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"

# The sidebar strapline is the cheapest thing that differs between the three.
MARKER = {
    ADMIN: "Админ систем",
    TEACHER: "Багшийн хэсэг",
    PARENT: "Эцэг эхийн хэсэг",
}


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def shell_of(response) -> str:
    """Which layout the response rendered, by its strapline."""
    html = response.content.decode()
    found = [shell for shell, text in MARKER.items() if text in html]
    assert len(found) == 1, f"expected exactly one shell, found {found}"
    return found[0]


def test_an_administrator_gets_the_admin_shell_on_every_screen(
    client, world, make_admin
):
    """The bug this file exists for: only the dashboard was correct."""
    director = make_admin(world["naran"], username="director")
    login(client, director)

    for url in (reverse("dashboard:admin"),
                reverse("children:list"),
                reverse("comms:list"),
                reverse("accounts:profile")):
        assert shell_of(client.get(url)) == ADMIN, url


def test_a_teacher_gets_the_teacher_shell(client, world):
    login(client, world["dulmaa"])

    for url in (reverse("children:list"),
                reverse("comms:list"),
                reverse("accounts:profile")):
        assert shell_of(client.get(url)) == TEACHER, url


def test_a_guardian_gets_the_parent_shell(client, world):
    login(client, world["bataa_mother"])

    for url in (reverse("children:parent_home"),
                reverse("comms:list"),
                reverse("accounts:profile")):
        assert shell_of(client.get(url)) == PARENT, url


def test_a_shared_screen_follows_the_role_the_request_is_made_in(client, world):
    """The portfolio is one page two roles reach.

    A teacher opening it is working; a guardian opening it is reading about
    their own child. The chrome has to follow the reader, not the URL.
    """
    url = reverse("portfolio:overview", args=[world["bataa"].pk])

    login(client, world["dulmaa"])
    assert shell_of(client.get(url)) == TEACHER

    login(client, world["bataa_mother"])
    assert shell_of(client.get(url)) == PARENT


def test_an_administrator_who_also_teaches_gets_the_admin_shell(
    client, world, make_admin
):
    """One person, two memberships. The wider menu wins — it is the one
    that reaches the whole kindergarten."""
    from apps.accounts.models import Membership, Role
    from apps.tenants.models import GroupTeacher

    director = make_admin(world["naran"], username="teaching_director")
    teaching = Membership.objects.create(
        user=director, kindergarten=world["naran"], role=Role.TEACHER
    )
    GroupTeacher.objects.create(
        kindergarten=world["naran"], group=world["sunflower"],
        teacher_membership=teaching,
    )
    login(client, director)

    assert shell_of(client.get(reverse("children:list"))) == ADMIN


def test_layout_for_falls_back_to_the_parent_shell(world):
    """An anonymous or membership-less user still renders something."""
    from django.contrib.auth.models import AnonymousUser

    assert layout_for(AnonymousUser()) == PARENT
    assert layout_for(None) == PARENT
