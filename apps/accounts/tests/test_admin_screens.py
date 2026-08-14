"""The administrator's staff and user screens — RFP §2.1, §3.3.

These replaced the Django admin's user and membership changelists — the
screen a director was shown when they asked what the system looked like.
The admin site scoped its rows through ``TenantScopedAdmin``; these views
enforce it themselves, so every check goes through the HTTP client
(CLAUDE.md §4.1).
"""

import pytest
from django.urls import reverse

from apps.accounts.models import Membership, Role, User

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"

SCREENS = ["accounts:staff_list", "accounts:staff_invite", "accounts:user_list"]


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


# ------------------------------------------------------------------ §2.1

@pytest.mark.parametrize("name", SCREENS)
def test_a_teacher_cannot_reach_them(client, world, name):
    """§2.1 makes staff management the administrator's, not a teacher's."""
    login(client, world["dulmaa"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", SCREENS)
def test_a_guardian_cannot_reach_them(client, world, name):
    login(client, world["bataa_mother"])

    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("name", SCREENS)
def test_an_anonymous_request_goes_to_the_login_page(client, world, name):
    response = client.get(reverse(name))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_a_director_sees_only_their_own_kindergartens_staff(client, world,
                                                            make_admin):
    """RFP §3.2 — another kindergarten's teachers are not listed."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("accounts:staff_list")).content.decode()

    assert str(world["dulmaa"]) in html
    assert str(world["oyun"]) not in html


def test_a_director_sees_only_their_own_kindergartens_users(client, world,
                                                            make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))

    html = client.get(reverse("accounts:user_list")).content.decode()

    assert str(world["dulmaa"]) in html
    assert str(world["oyun"]) not in html


def test_a_director_cannot_end_another_kindergartens_posting(client, world,
                                                             make_admin):
    """The §21.4 attack, aimed at a membership id."""
    login(client, make_admin(world["naran"], username="naran_boss"))
    posting = Membership.objects.get(user=world["oyun"], role=Role.TEACHER)

    url = reverse("accounts:membership_toggle", args=[posting.pk])

    assert client.post(url).status_code == 404
    posting.refresh_from_db()
    assert posting.is_active is True


def test_the_toggle_refuses_a_get(client, world, make_admin):
    """CLAUDE.md §5 — a state change is posted and confirmed, never a link."""
    login(client, make_admin(world["naran"], username="naran_boss"))
    posting = Membership.objects.get(user=world["dulmaa"], role=Role.TEACHER)

    assert client.get(
        reverse("accounts:membership_toggle", args=[posting.pk])
    ).status_code == 404
    posting.refresh_from_db()
    assert posting.is_active is True


# ------------------------------------------------------------------ the work

def test_a_director_invites_a_teacher(client, world, make_admin):
    """§2.1 — the account is created without a usable password."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("accounts:staff_invite"), {
        "last_name": "Дорж",
        "first_name": "Сайхан",
        "kindergarten": world["naran"].pk,
        "username": "saihan",
        "email": "saihan@example.mn",
    })

    assert response.status_code == 200
    invited = User.objects.get(username="saihan")
    assert not invited.has_usable_password()
    assert Membership.objects.filter(
        user=invited, kindergarten=world["naran"], role=Role.TEACHER
    ).exists()
    # The code is shown once and only its hash is kept.
    assert "Идэвхжүүлэх код" in response.content.decode()


def test_an_invitation_without_a_name_is_refused(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))
    before = User.objects.count()

    response = client.post(reverse("accounts:staff_invite"), {
        "last_name": "Дорж",
        "first_name": "  ",
        "kindergarten": world["naran"].pk,
    })

    assert response.status_code == 200
    assert "нэрийг оруулна уу" in response.content.decode()
    assert User.objects.count() == before


def test_a_director_cannot_invite_into_another_kindergarten(client, world,
                                                            make_admin):
    """The dropdown only offers their own; this is the crafted post."""
    login(client, make_admin(world["naran"], username="naran_boss"))

    response = client.post(reverse("accounts:staff_invite"), {
        "last_name": "Халдлага",
        "first_name": "Оролдлого",
        "kindergarten": world["och"].pk,
    })

    assert response.status_code == 200
    assert not Membership.objects.filter(kindergarten=world["och"],
                                         user__first_name="Оролдлого").exists()


def test_a_director_ends_and_restores_a_posting(client, world, make_admin):
    login(client, make_admin(world["naran"], username="naran_boss"))
    posting = Membership.objects.get(user=world["dulmaa"], role=Role.TEACHER)
    url = reverse("accounts:membership_toggle", args=[posting.pk])

    assert client.post(url).status_code == 302
    posting.refresh_from_db()
    assert posting.is_active is False

    assert client.post(url).status_code == 302
    posting.refresh_from_db()
    assert posting.is_active is True


def test_a_director_cannot_end_their_own_posting(client, world, make_admin):
    """Otherwise they lock themselves out of the screen they are on."""
    director = make_admin(world["naran"], username="naran_boss")
    login(client, director)
    own = Membership.objects.get(user=director)

    response = client.post(
        reverse("accounts:membership_toggle", args=[own.pk]), follow=True
    )

    assert response.status_code == 200
    own.refresh_from_db()
    assert own.is_active is True


def test_ending_a_posting_writes_an_audit_row(client, world, make_admin):
    """RFP §971 — a permission change is exactly what an audit log is for."""
    from apps.core.models import AuditAction, AuditLog

    director = make_admin(world["naran"], username="naran_boss")
    login(client, director)
    posting = Membership.objects.get(user=world["dulmaa"], role=Role.TEACHER)

    client.post(reverse("accounts:membership_toggle", args=[posting.pk]))

    assert AuditLog.objects.filter(
        action=AuditAction.PERMISSION_CHANGE, actor_user=director,
        object_type="accounts.Membership",
    ).exists()
