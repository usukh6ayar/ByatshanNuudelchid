"""The error pages, exercised through the request cycle — RFP §624-635, §611.

Templates named 404.html, 500.html and 403_csrf.html are picked up by
Django's own handlers by convention: nothing imports them and no URL routes
to them, so a typo in a filename or a template that fails to compile is
invisible until a user meets it. These tests are the only thing that proves
the wiring, and they go through the test client for the same reason
CLAUDE.md §4.1 insists on it for authorization.

`settings.DEBUG` is False under test, which is what makes this possible:
with DEBUG on, Django answers a 404 with its own technical page and these
templates are never consulted.
"""

import pytest
from django.template.loader import render_to_string
from django.test import Client

pytestmark = pytest.mark.django_db


def test_an_unknown_url_renders_the_mongolian_404(client):
    response = client.get("/ene-huudas-baihgui/")

    assert response.status_code == 404
    body = response.content.decode()
    assert "Хуудас олдсонгүй" in body
    assert "Нүүр хуудас руу буцах" in body


def test_the_404_page_carries_no_navigation(client):
    """RFP §21.4.

    can_access_child() answers with 404 rather than 403 precisely so that a
    guardian editing a URL cannot tell an unrelated child from a mistyped
    address. A shared layout would undo that from the other end: a menu
    naming the review queue tells an outsider what the system contains, and
    a menu rendered for the *wrong* role tells them more still.
    """
    body = client.get("/ene-huudas-baihgui/").content.decode()

    for leak in ("Хяналтын самбар", "Хүүхдүүд", "Хянах ажиглалт", "Гарах"):
        assert leak not in body


def test_the_404_page_does_not_depend_on_being_logged_in(client, django_user_model):
    """Anonymous and authenticated visitors get the same page.

    The 404 handler renders with a request, so the context processors run.
    A badge query that assumed an authenticated user would turn a missing
    page into a 500.
    """
    anonymous = client.get("/ene-huudas-baihgui/")

    user = django_user_model.objects.create_user(
        username="ganbat", password="Nuudelchid-2026", email="g@example.mn"
    )
    client.force_login(user)
    logged_in = client.get("/ene-huudas-baihgui/")

    assert anonymous.status_code == logged_in.status_code == 404


def test_a_post_without_a_csrf_token_explains_itself(client):
    """RFP §624 — say what happened, in Mongolian, and offer the way out."""
    strict = Client(enforce_csrf_checks=True)
    response = strict.post("/nevtreh/", {"username": "x", "password": "y"})

    assert response.status_code == 403
    body = response.content.decode()
    assert "Хуудасны хугацаа дууссан" in body
    assert "Дахин нэвтрэх" in body


def test_the_500_page_renders_without_a_request():
    """django.views.defaults.server_error renders 500.html with no context.

    Anything the page needs from the request, the session or the database is
    a second failure waiting for the moment the first one happens. Rendering
    it with an empty context is exactly what Django will do.
    """
    body = render_to_string("500.html", {})

    assert "Системд алдаа гарлаа" in body
    assert "Нүүр хуудас руу буцах" in body


@pytest.mark.parametrize("template", ["400.html", "403.html", "404.html", "500.html"])
def test_no_error_page_leaks_english_internals(template):
    body = render_to_string(template, {})

    for leak in ("RFP", "CLAUDE.md", "{#", "can_access_child"):
        assert leak not in body
