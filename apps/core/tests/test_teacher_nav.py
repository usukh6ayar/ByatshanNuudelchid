"""The teacher shell's navigation — approved 2026-08-17.

Six items, every one pointing at a route that already exists. What is worth
pinning is not the wording but the two rules the navigation has to keep:

* **no dead links.** Every entry is resolved through the HTTP client and must
  answer 200 for the teacher looking at it. A menu item that 404s teaches
  users the rest of the system is broken too.
* **nothing is silently chosen.** ``assessment:group_grid`` needs a group and
  a teacher may hold several; the shell links to one, and the screen it lands
  on has to offer the others.

Portfolio and Reports are deliberately absent — both are child-scoped, and
inventing an index screen to fill a menu slot was ruled out.
"""

import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def nav_links(client) -> list[str]:
    """Every real destination in the teacher sidebar.

    `#i-…` is filtered out: those are `<use>` references into the icon
    sprite, not links, and treating them as URLs makes this test pass on a
    redirect to the login page.
    """
    body = client.get(reverse("dashboard:teacher")).content.decode()
    nav = body.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
    return [h for h in re.findall(r'<a href="([^"]+)"', nav)
            if not h.startswith("#")]


def test_the_teacher_nav_has_no_dead_links(client, world):
    """Every entry must exist, load, and be authorized for a teacher."""
    login(client, world["dulmaa"])

    links = nav_links(client)
    assert len(links) == 6, f"expected six navigation items, got {links}"

    for href in links:
        assert client.get(href).status_code == 200, f"dead nav link: {href}"


def test_the_nav_reaches_every_approved_destination(client, world):
    login(client, world["dulmaa"])

    links = set(nav_links(client))

    for name in ("dashboard:teacher", "children:list",
                 "observations:review_queue", "comms:list",
                 "accounts:profile"):
        assert reverse(name) in links, f"{name} is not in the teacher nav"

    # The assessment link carries a group id, so it is matched by prefix.
    assert any("turgen-unelgee" in href for href in links)


def test_a_teacher_with_no_group_gets_no_assessment_link(client, world,
                                                         make_teacher):
    """A link that 404s is worse than no link.

    `assessment:group_grid` needs a group. A teacher who holds none — newly
    created, or between assignments — must not be offered it.
    """
    stranger = make_teacher(world["naran"], username="groupless")
    login(client, stranger)

    links = nav_links(client)

    assert all("turgen-unelgee" not in href for href in links)
    for href in links:
        assert client.get(href).status_code == 200, f"dead nav link: {href}"


def test_the_assessment_screen_offers_the_teachers_other_groups(
    client, world, make_group, naran_admin_user
):
    """Navigation picks one group; the screen must not hide the rest.

    This is the whole reason the sidebar is allowed to link to a single
    group — the destination lets the teacher see which one they are on and
    switch.
    """
    from apps.accounts.models import Membership
    from apps.assessment import services
    from apps.tenants.models import GroupTeacher

    services.ensure_default_terms(actor=naran_admin_user,
                                  school_year=world["naran_year"])
    second = make_group(world["naran"], world["naran_year"], "Сарнай")
    membership = Membership.objects.get(user=world["dulmaa"],
                                        kindergarten=world["naran"])
    GroupTeacher.objects.create(kindergarten=world["naran"], group=second,
                                teacher_membership=membership)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("assessment:group_grid", args=[world["sunflower"].pk])
    ).content.decode()

    assert 'name="group"' in body, "no group selector on the assessment screen"
    assert second.name in body, "the teacher's other group is not offered"


def test_the_active_item_is_marked_for_assistive_technology(client, world):
    """§13 — the active state is not carried by colour alone."""
    login(client, world["dulmaa"])

    body = client.get(reverse("children:list")).content.decode()
    nav = body.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]

    assert nav.count('aria-current="page"') == 1


def test_the_shell_does_not_offer_deferred_features(client, world):
    """Phase 2 and 3 entries the mockups draw must not appear."""
    login(client, world["dulmaa"])

    body = client.get(reverse("dashboard:teacher")).content.decode()
    nav = body.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]

    for deferred in ("Ирц", "Эрүүл мэнд", "Хоол", "Санхүү", "Судалгаа",
                     "Төлбөр"):
        assert deferred not in nav, f"deferred feature in the nav: {deferred}"
