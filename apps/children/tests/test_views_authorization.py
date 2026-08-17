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


def test_the_school_year_filter_is_on_the_form(client, world):
    """RFP §11 — "хичээлийн жилээр шүүх".

    The selector supported it from Day 3; until Day 8 the form did not
    render it, so the filter existed and nobody could use it.
    """
    assert client.login(username="dulmaa", password="test-password-1234")

    response = client.get(reverse("children:list"))

    assert response.status_code == 200
    assert world["naran_year"] in list(response.context["school_years"])
    assert world["och_year"] not in list(response.context["school_years"])


def test_filtering_by_school_year_narrows_the_list(client, world):
    assert client.login(username="dulmaa", password="test-password-1234")

    response = client.get(
        reverse("children:list") + f"?school_year={world['naran_year'].pk}"
    )
    assert response.context["page"].paginator.count == 2

    response = client.get(
        reverse("children:list") + f"?school_year={world['och_year'].pk}"
    )
    # Not their year: the option is not offered, so it selects nothing and
    # the filter is skipped rather than silently applied.
    assert response.context["selected_school_year"] is None


# ------------------------------------------------------- revoked guardianship
# A soft-deleted Guardianship is how access is taken away (RFP §3.5) — a court
# order, a change of custody, a link created by mistake. These go through the
# HTTP client because that is the claim §21.3 makes: a revoked guardian must
# not be *served* the child, whatever any helper returns. The function-level
# half is in apps/core/tests/test_permissions.py.

def test_a_revoked_guardian_cannot_open_the_child_page(client, world,
                                                       revoke_guardianship):
    revoke_guardianship(world["bataa"], world["bataa_mother"])
    login(client, world["bataa_mother"])

    url = reverse("children:parent_child_detail", args=[world["bataa"].pk])

    assert client.get(url).status_code == 404


def test_a_revoked_guardian_no_longer_sees_the_child_on_the_home_screen(
    client, world, revoke_guardianship
):
    """The bug fixed on 2026-08-16, at the surface where it was visible.

    The detail page already refused — it goes through ``is_guardian_of``,
    which honours the soft delete. The home screen resolved its child
    through a *join*, which did not, so it went on rendering the child's
    name, photo, group and recent observations to a revoked guardian while
    the page one tap away returned 404.

    Asserted on the response body, not on a queryset: what leaked was the
    rendered page.
    """
    revoke_guardianship(world["bataa"], world["bataa_mother"])
    login(client, world["bataa_mother"])

    response = client.get(reverse("children:parent_home"))
    body = response.content.decode()

    assert response.status_code == 200          # they still have an account
    assert "Батаа" not in body
    # And the screen says so plainly rather than rendering an empty shell.
    assert "Хүүхэд холбогдоогүй байна" in body


def test_a_revoked_guardian_cannot_reach_the_child_through_the_switcher(
    client, world, make_child, revoke_guardianship
):
    """``?child=`` is the home screen's only way in to a specific child.

    The guardian keeps a second child on purpose. With every link revoked
    the view short-circuits to the "no children" page before it ever reads
    the query string, so a single-child version of this test would pass
    without the switcher being checked at all. Here the screen is live and
    the revoked id has to be rejected on its own.
    """
    from apps.children.models import Guardianship

    sibling = make_child(world["naran"], world["sunflower"], first_name="Дүү")
    Guardianship.objects.create(
        kindergarten=world["naran"], child=sibling,
        guardian_user=world["bataa_mother"],
        relation=Guardianship.Relation.MOTHER,
    )
    revoke_guardianship(world["bataa"], world["bataa_mother"])
    login(client, world["bataa_mother"])

    response = client.get(reverse("children:parent_home"),
                          {"child": world["bataa"].pk})

    assert response.status_code == 404


def test_an_active_guardian_still_reaches_their_child(client, world,
                                                      make_guardian,
                                                      revoke_guardianship):
    """The control: revoking one link must not deny the other guardian.

    Without this, a fix that filtered on the wrong side of the join — or
    denied guardians wholesale — would pass every test above.
    """
    father = make_guardian(world["bataa"], world["naran"], username="live_father")
    revoke_guardianship(world["bataa"], world["bataa_mother"])
    login(client, father)

    detail = client.get(
        reverse("children:parent_child_detail", args=[world["bataa"].pk])
    )
    home = client.get(reverse("children:parent_home"))

    assert detail.status_code == 200
    assert "Батаа" in home.content.decode()


# --------------------------------------------------------- revoked assignment
# A soft-deleted GroupTeacher is how staff access is taken away (RFP §2.2) — a
# teacher leaves, or moves to another group. Same rigour as the guardianship
# block above: §21.2 is a claim about what the server *serves*, so these go
# through the HTTP client. The function-level half lives in
# apps/core/tests/test_permissions.py.

def test_a_revoked_teacher_gets_404_on_the_child_detail(client, world,
                                                        revoke_group_teacher):
    revoke_group_teacher(world["dulmaa"], world["sunflower"])
    login(client, world["dulmaa"])

    response = client.get(reverse("children:detail", args=[world["bataa"].pk]))

    assert response.status_code == 404


def test_a_revoked_teacher_no_longer_sees_the_child_in_the_list(
    client, world, revoke_group_teacher
):
    """The bug fixed on 2026-08-16, at the surface where it was visible.

    The detail page already refused — it went through ``GroupTeacher.objects``
    and honoured the soft delete. The list joined to ``teacher_assignments``
    and did not, so a teacher whose assignment had been withdrawn kept the
    whole roster on screen while every name on it 404'd when clicked.
    """
    revoke_group_teacher(world["dulmaa"], world["sunflower"])
    login(client, world["dulmaa"])

    response = client.get(reverse("children:list"))
    body = response.content.decode()

    assert response.status_code == 200          # they still have an account
    assert "Батаа" not in body
    assert "Сараа" not in body


def test_a_revoked_teacher_cannot_reach_the_child_through_query_parameters(
    client, world, revoke_group_teacher
):
    """Filters narrow what is visible; they must never widen it (RFP §11).

    The search box and the group filter are the two ways a name can be asked
    for by hand once it is off the page.
    """
    revoke_group_teacher(world["dulmaa"], world["sunflower"])
    login(client, world["dulmaa"])

    url = reverse("children:list")
    by_search = client.get(url, {"q": "Батаа"})
    by_group = client.get(url, {"group": world["sunflower"].pk})

    assert list(by_search.context["page"].object_list) == []
    assert list(by_group.context["page"].object_list) == []
    assert "Батаа" not in by_group.content.decode()


def test_a_revoked_teacher_cannot_reach_the_group_screens(client, world,
                                                          revoke_group_teacher):
    """The §6.3 grid and the §5.2 group form both list a whole roster.

    Neither is reached through ``visible_children``; both are gated by
    ``assignable_groups``, which carried the same missing ``deleted_at``.
    """
    revoke_group_teacher(world["dulmaa"], world["sunflower"])
    login(client, world["dulmaa"])

    grid = client.get(reverse("assessment:group_grid",
                              args=[world["sunflower"].pk]))
    group_form = client.get(reverse("observations:group",
                                    args=[world["sunflower"].pk]))

    assert grid.status_code == 404
    assert group_form.status_code == 404


def test_a_co_teacher_still_reaches_the_child(client, world, make_teacher,
                                              revoke_group_teacher):
    """The control: withdrawing one assignment must not deny the other.

    Without this, a fix that denied assigned teachers wholesale would pass
    every test above.
    """
    co_teacher = make_teacher(world["naran"], world["sunflower"],
                              username="http_co_teacher")
    revoke_group_teacher(world["dulmaa"], world["sunflower"])
    login(client, co_teacher)

    detail = client.get(reverse("children:detail", args=[world["bataa"].pk]))
    listing = client.get(reverse("children:list"))

    assert detail.status_code == 200
    assert "Батаа" in listing.content.decode()


def test_list_and_detail_agree_over_http_after_a_revocation(
    client, world, make_teacher, revoke_group_teacher
):
    """The equivalence invariant, asserted through real requests.

    ``test_permissions.py`` proves ``visible_children`` and
    ``can_access_child`` agree. This proves the *views* built on them agree
    too — every child the list shows opens, and every child it hides 404s.
    """
    from apps.children.models import Child

    co_teacher = make_teacher(world["naran"], world["sunflower"],
                              username="agree_co")
    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    # Both sides of the revocation: the teacher who lost the assignment must
    # see nothing, the one who kept it must still see the roster. Checking
    # only the revoked user would pass on a fix that denied everybody.
    for user in (world["dulmaa"], co_teacher):
        login(client, user)
        listed = {
            child.pk
            for child in client.get(reverse("children:list"))
                              .context["page"].object_list
        }
        for child in Child.objects.all():
            status = client.get(
                reverse("children:detail", args=[child.pk])
            ).status_code
            assert (child.pk in listed) == (status == 200), (
                f"{user} vs {child}: listed={child.pk in listed}, "
                f"detail HTTP {status}"
            )
