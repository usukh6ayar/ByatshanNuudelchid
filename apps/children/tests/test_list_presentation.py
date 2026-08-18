"""The teacher children list's presentation — the parts that fail silently.

The layout is judged by looking at it. What is pinned here is the handful of
things that render fine and are wrong anyway:

* the **query count must not grow with the number of rows**. The list shows a
  photo, a group and a guardian flag per child, and each of those is a
  relation — one query per row unless the selector's ``select_related`` and
  ``prefetch_related`` stay in place (CLAUDE.md §3.5). Nothing in a rendered
  page says whether they are still there.
* the **two empty states** must not read alike: "no children yet" and "your
  search matched nothing" want opposite next actions, and offering the wrong
  one is worse than offering none.
* **authorization is unchanged.** This screen dropped a table for cards; the
  rows it may show did not change, and a presentation test that also proves
  that is cheap insurance.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"
LIST_URL = reverse("children:list")


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def test_the_list_does_not_query_once_per_row(client, world, make_child):
    """CLAUDE.md §3.5 — page cost must not scale with the number of children.

    Compared between two row counts rather than pinned to a number: the
    absolute count moves with middleware and the shell, and pinning it would
    make this fail for reasons unrelated to an N+1.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])

    with CaptureQueriesContext(connection) as first:
        client.get(LIST_URL)
    baseline = len(first.captured_queries)

    for index in range(8):
        make_child(world["naran"], world["sunflower"], first_name=f"Нэмэлт{index}")

    with CaptureQueriesContext(connection) as second:
        response = client.get(LIST_URL)

    assert response.context["page"].paginator.count == 10
    assert len(second.captured_queries) == baseline, (
        "the children list issues a query per row — check select_related / "
        "prefetch_related on children.selectors.child_list"
    )


def test_the_list_shows_the_children_a_teacher_may_see(client, world):
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert "Батаа" in body
    assert "Сараа" in body


def test_the_list_still_hides_another_kindergartens_children(client, world,
                                                             make_child):
    """The redesign changed the markup, not the rows — RFP §21.2."""
    make_child(world["och"], world["petal"], first_name="Гадны")
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert "Гадны" not in body


def test_the_no_children_state_offers_the_first_child(client, world,
                                                      make_teacher, make_group):
    """A teacher with an empty group needs the way in, not an apology."""
    empty_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    newcomer = make_teacher(world["naran"], empty_group, username="newcomer")
    login(client, newcomer)

    body = client.get(LIST_URL).content.decode()

    assert "Эхний хүүхдээ" in body
    assert reverse("children:create") in body


def test_a_search_that_matches_nothing_offers_a_way_back(client, world):
    """Different from "no children yet", and it must not claim that."""
    login(client, world["dulmaa"])

    response = client.get(LIST_URL, {"q": "байхгүйнэр"})
    body = response.content.decode()

    assert list(response.context["page"].object_list) == []
    assert "Хүүхэд олдсонгүй" in body
    assert "Шүүлтийг цэвэрлэх" in body
    # The two states are distinct: this one must not invite a first child.
    assert "Эхний хүүхдээ" not in body


def test_an_active_filter_opens_the_filter_panel(client, world):
    """A filter narrowing the list must never be doing so invisibly."""
    login(client, world["dulmaa"])

    def disclosure(html: str) -> str:
        return html.split("<details", 1)[1].split(">", 1)[0]

    plain = client.get(LIST_URL).content.decode()
    filtered = client.get(LIST_URL, {"age": "4"}).content.decode()

    assert "open" not in disclosure(plain)
    assert "open" in disclosure(filtered)


def test_a_child_with_no_guardian_is_flagged(client, world, make_child):
    """§3.5 — no guardian linked means no family reading the portfolio.

    The one thing on this screen that genuinely wants attention.
    """
    make_child(world["naran"], world["sunflower"], first_name="Ганцаардсан")
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert "Эцэг эх холбогдоогүй" in body


def test_the_search_keeps_the_other_filters(client, world):
    """Search and the filter panel are one form, so neither drops the other."""
    login(client, world["dulmaa"])

    response = client.get(LIST_URL, {"q": "Батаа", "age": "4"})

    assert response.status_code == 200
    assert response.context["filters"]["q"] == "Батаа"
    assert response.context["filters"]["age"] == "4"


# --------------------------------------------- the row menu, 2026-08-18
# The row's single "Засах" pill became a "⋮" menu, from the client's mockup.
# The row therefore gained two destinations without gaining a control, and
# both of them are pages that already existed.


def test_every_row_offers_the_three_actions(client, world):
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()
    child = world["bataa"]

    for name in ("portfolio:overview", "children:edit", "reports:request"):
        assert reverse(name, args=[child.pk]) in body, (
            f"the row menu lost its {name} entry"
        )


def test_the_row_menu_needs_no_javascript(client, world):
    """A native <details>: it opens, closes on Esc and is announced as a
    disclosure with no script and no ARIA. If it ever becomes a <button> with
    a click handler, this is what says so."""
    login(client, world["dulmaa"])

    body = client.get(LIST_URL).content.decode()

    assert '<details class="rowmenu">' in body


def test_the_row_menu_adds_no_query_per_row(client, world, make_child):
    """CLAUDE.md §3.5 — reversing three URLs per row is not a database read,
    and this is what keeps it that way if one of them ever grows a lookup."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    login(client, world["dulmaa"])

    with CaptureQueriesContext(connection) as first:
        client.get(LIST_URL)
    baseline = len(first.captured_queries)

    for index in range(5):
        make_child(world["naran"], world["sunflower"], first_name=f"Цэс{index}")

    with CaptureQueriesContext(connection) as second:
        client.get(LIST_URL)

    assert len(second.captured_queries) == baseline
