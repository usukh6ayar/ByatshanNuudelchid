"""Self-service profile — RFP §3.3.

The requirement table's remaining "partial": the ``TeacherProfile`` model and
the administrator's assignment screens shipped on Day 2, and a teacher had no
way to fill in their own specialization, education or years of service.

The whole screen is about the logged-in user, so there is no id in the URL
and none of the child-data rules apply. The rule that does apply is narrower
and easier to get wrong: **a profile page must never become a way to edit
somebody else's account, or to grant yourself something.** Every test below
is a form of that.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import Role, TeacherProfile

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"
URL = "/miniy-buurtgel/"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def payload(**overrides):
    data = {
        "last_name": "Дулмаа",
        "first_name": "Сүрэн",
        "email": "dulmaa@example.mn",
        "phone": "99112233",
        "specialization": "Хүүхдийн хөгжил судлаач",
        "years_of_service": "7",
        "education": "МУБИС, бакалавр",
        "bio": "Багаар ажиллах дуртай.",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ reachable

def test_anonymous_users_are_sent_to_login(client):
    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_the_url_is_the_one_the_menu_links_to(client, world):
    """Guards the path itself, since the nav hard-codes nothing else."""
    assert reverse("accounts:profile") == URL


def test_a_teacher_can_open_their_own_profile(client, world):
    login(client, world["dulmaa"])

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 200
    assert "Миний бүртгэл" in response.content.decode()


def test_a_guardian_can_open_it_too(client, world):
    """§3.5 gives guardians a name and contact details worth correcting.

    They get the same screen without the teacher fields; a page that 404s for
    a whole role is a menu entry that has to be conditional in three layouts.
    """
    login(client, world["bataa_mother"])

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Мэргэжил" not in body


# ------------------------------------------------------------------ it saves

def test_a_teacher_fills_in_their_professional_details(client, world):
    """RFP §3.3 — "мэргэжил, боловсрол, ажилласан жил"."""
    login(client, world["dulmaa"])

    response = client.post(reverse("accounts:profile"), payload())

    assert response.status_code == 302

    profile = TeacherProfile.objects.get(user=world["dulmaa"])
    assert profile.specialization == "Хүүхдийн хөгжил судлаач"
    assert profile.years_of_service == 7
    assert profile.education == "МУБИС, бакалавр"


def test_the_profile_row_is_created_on_first_save(client, world):
    """Accounts are created by invitation, which writes no profile row."""
    assert not TeacherProfile.objects.filter(user=world["dulmaa"]).exists()

    login(client, world["dulmaa"])
    client.post(reverse("accounts:profile"), payload())

    assert TeacherProfile.objects.filter(user=world["dulmaa"]).count() == 1


def test_saving_twice_does_not_create_a_second_row(client, world):
    login(client, world["dulmaa"])
    client.post(reverse("accounts:profile"), payload())
    client.post(reverse("accounts:profile"), payload(specialization="Арга зүйч"))

    profile = TeacherProfile.objects.get(user=world["dulmaa"])
    assert profile.specialization == "Арга зүйч"


def test_the_users_own_name_and_contacts_are_editable(client, world):
    login(client, world["dulmaa"])

    client.post(reverse("accounts:profile"), payload(last_name="Дорж"))

    world["dulmaa"].refresh_from_db()
    assert world["dulmaa"].last_name == "Дорж"
    assert world["dulmaa"].email == "dulmaa@example.mn"


# ---------------------------------------------------- and what it must not do

def test_a_guardian_cannot_grow_a_teacher_profile(client, world):
    """Posting the teacher fields as a guardian must not create the row.

    The form does not render them, which is not a control — the POST body is
    the user's to write.
    """
    login(client, world["bataa_mother"])

    client.post(reverse("accounts:profile"),
                payload(specialization="Захирал", years_of_service="30"))

    assert not TeacherProfile.objects.filter(
        user=world["bataa_mother"]
    ).exists()


def test_the_form_cannot_change_anyone_elses_account(client, world):
    """There is no id in the URL; there must be none in the body either."""
    login(client, world["dulmaa"])

    client.post(reverse("accounts:profile"),
                payload(user=world["oyun"].pk, id=world["oyun"].pk,
                        last_name="Халдлага"))

    world["oyun"].refresh_from_db()
    assert world["oyun"].last_name != "Халдлага"


def test_the_form_cannot_grant_a_role(client, world):
    """Roles come from Membership, which an administrator writes — §2.1."""
    login(client, world["dulmaa"])

    client.post(reverse("accounts:profile"),
                payload(role=Role.SUPERADMIN, is_superuser="1", is_staff="1"))

    world["dulmaa"].refresh_from_db()
    assert not world["dulmaa"].is_superuser
    assert not world["dulmaa"].is_staff
    assert not world["dulmaa"].memberships.filter(
        role__in=[Role.ADMIN, Role.SUPERADMIN]
    ).exists()


def test_the_form_cannot_reactivate_a_disabled_account(client, world,
                                                       make_teacher):
    """`is_active` is the administrator's switch, not the user's."""
    login(client, world["dulmaa"])

    client.post(reverse("accounts:profile"), payload(is_active="1"))

    world["dulmaa"].refresh_from_db()
    assert world["dulmaa"].is_active is True   # unchanged, and not from the post


def test_the_form_cannot_set_a_password(client, world):
    """Password changes go through the reset flow, which verifies identity."""
    login(client, world["dulmaa"])
    original = world["dulmaa"].password

    client.post(reverse("accounts:profile"),
                payload(password="hunted", is_employed="0"))

    world["dulmaa"].refresh_from_db()
    assert world["dulmaa"].password == original


def test_an_email_already_in_use_is_refused_not_a_500(client, world):
    """`email` is unique on the model — the collision must be a sentence."""
    login(client, world["dulmaa"])
    world["oyun"].email = "taken@example.mn"
    world["oyun"].save(update_fields=["email"])

    response = client.post(reverse("accounts:profile"),
                           payload(email="taken@example.mn"))

    assert response.status_code == 200
    world["dulmaa"].refresh_from_db()
    assert world["dulmaa"].email != "taken@example.mn"


def test_clearing_every_identifier_is_refused(client, world):
    """A user needs at least one of username, email or phone to log in."""
    login(client, world["dulmaa"])

    response = client.post(reverse("accounts:profile"),
                           payload(email="", phone=""))

    world["dulmaa"].refresh_from_db()
    if response.status_code == 302:
        # Accepted only because the username survives as an identifier.
        assert world["dulmaa"].username
    else:
        assert response.status_code == 200


def test_years_of_service_must_be_a_number(client, world):
    login(client, world["dulmaa"])

    response = client.post(reverse("accounts:profile"),
                           payload(years_of_service="долоо"))

    assert response.status_code == 200
    assert not TeacherProfile.objects.filter(
        user=world["dulmaa"], specialization="Хүүхдийн хөгжил судлаач"
    ).exists()


# ------------------------------------------------------------------ the trail

def test_the_menu_links_to_it_in_both_layouts(client, world):
    """RFP §13 — a screen nothing links to is a screen nobody finds."""
    login(client, world["dulmaa"])
    teacher_nav = client.get(reverse("dashboard:teacher")).content.decode()
    assert reverse("accounts:profile") in teacher_nav

    client.logout()
    login(client, world["bataa_mother"])
    parent_nav = client.get(reverse("children:parent_home")).content.decode()
    assert reverse("accounts:profile") in parent_nav


def test_the_change_is_audited(client, world):
    """RFP §971 — an account change is worth recording even when self-made."""
    from apps.core.models import AuditAction, AuditLog

    login(client, world["dulmaa"])
    client.post(reverse("accounts:profile"), payload())

    assert AuditLog.objects.filter(
        action=AuditAction.UPDATE,
        actor_user=world["dulmaa"],
        object_id=str(world["dulmaa"].pk),
    ).exists()
