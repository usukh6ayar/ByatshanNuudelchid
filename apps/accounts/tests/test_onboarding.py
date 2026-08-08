"""Account creation and activation — RFP §2.1, §3.4, §3.5, §21.3.

Nobody self-registers. Staff create the account; the person sets their own
password through an invitation, so staff never learn it.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Invitation, Membership, Role, User
from apps.accounts.services import (
    create_invitation,
    invite_teacher,
    register_guardian,
)
from apps.children.models import Guardianship
from apps.core.models import AuditAction, AuditLog
from apps.core.permissions import can_access_child

pytestmark = pytest.mark.django_db(transaction=True)

NEW_PASSWORD = "ShineNuuts99"


def activate_url(token):
    return reverse("accounts:activate_by_token", args=[token])


CODE_URL = reverse("accounts:activate")


# ------------------------------------------------------------------ teachers

def test_admin_creates_a_teacher_account(world, naran_admin_user):
    """RFP §2.1 — the administrator creates the account, not the teacher."""
    user, token, code = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа",
        username="sarantuya", email="saraa@example.mn",
    )

    assert Membership.objects.filter(
        user=user, kindergarten=world["naran"], role=Role.TEACHER
    ).exists()
    assert token and len(code) == 6


def test_a_new_teacher_cannot_log_in_before_activating(client, world,
                                                       naran_admin_user):
    """The account exists but has no usable password yet."""
    user, _, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    assert not user.has_usable_password()
    response = client.post(reverse("accounts:login"),
                           {"username": "sarantuya", "password": NEW_PASSWORD})
    assert "_auth_user_id" not in client.session
    assert response.status_code == 200


def test_teacher_activates_and_can_then_log_in(client, world, naran_admin_user):
    user, token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    client.post(activate_url(token), {"password": NEW_PASSWORD,
                                      "password_confirm": NEW_PASSWORD})

    response = client.post(reverse("accounts:login"),
                           {"username": "sarantuya", "password": NEW_PASSWORD})
    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


# ------------------------------------------------------------------ guardians

def test_teacher_attaching_a_guardian_grants_access_to_that_child_only(
    world, naran_admin_user
):
    """The Guardianship row is the §21.3 boundary, created by staff."""
    guardianship, token, code = register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )
    guardian = guardianship.guardian_user

    assert can_access_child(guardian, world["bataa"])
    assert not can_access_child(guardian, world["saraa"])
    assert token and len(code) == 6


def test_guardian_of_a_second_child_reuses_the_existing_account(
    world, naran_admin_user
):
    """One parent, several children — RFP §3.5."""
    first, _, _ = register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )
    second, token, code = register_guardian(
        actor=naran_admin_user, child=world["saraa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )

    assert first.guardian_user_id == second.guardian_user_id
    assert User.objects.filter(phone="99112233").count() == 1
    # They already have a password; a second invitation would be noise.
    assert token is None and code is None


def test_second_child_at_another_kindergarten_adds_a_membership(
    world, naran_admin_user, make_child
):
    """Spec section 4.2 — a guardian may have children at two kindergartens."""
    och_child = make_child(world["och"], world["petal"], first_name="Дүү")

    register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )
    guardianship, _, _ = register_guardian(
        actor=naran_admin_user, child=och_child,
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )
    guardian = guardianship.guardian_user

    assert guardian.kindergarten_ids == {world["naran"].id, world["och"].id}
    assert can_access_child(guardian, world["bataa"])
    assert can_access_child(guardian, och_child)


def test_registering_a_guardian_is_audited_against_the_child(
    world, naran_admin_user
):
    """RFP §971 — the trail has to be searchable by child."""
    register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )

    entry = AuditLog.objects.get(action=AuditAction.CREATE,
                                 object_type="children.Guardianship")
    assert entry.child_id == world["bataa"].id
    assert entry.actor_user_id == naran_admin_user.pk


# ------------------------------------------------------------------ the code path

def test_activation_by_identifier_and_code(client, world, naran_admin_user):
    """The paper path, for guardians with no email address."""
    guardianship, _, code = register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )

    response = client.post(CODE_URL, {
        "identifier": "99112233", "code": code,
        "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD,
    })

    assert response.status_code == 302
    guardianship.guardian_user.refresh_from_db()
    assert guardianship.guardian_user.check_password(NEW_PASSWORD)


def test_code_alone_is_not_enough(client, world, naran_admin_user):
    """Six digits is searchable; it only works with the right identifier."""
    _, _, code = register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )

    response = client.post(CODE_URL, {
        "identifier": "99999999", "code": code,
        "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD,
    })

    assert response.status_code == 200
    assert User.objects.get(phone="99112233").has_usable_password() is False


def test_code_guessing_is_throttled(client, world, naran_admin_user, settings):
    """RFP §3.1 applies here too, or the code becomes brute-forceable."""
    register_guardian(
        actor=naran_admin_user, child=world["bataa"],
        last_name="Дорж", first_name="Дулмаа",
        relation=Guardianship.Relation.MOTHER, phone="99112233",
    )

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        client.post(CODE_URL, {"identifier": "99112233", "code": "000000",
                               "password": NEW_PASSWORD,
                               "password_confirm": NEW_PASSWORD})

    response = client.post(CODE_URL, {"identifier": "99112233", "code": "000000",
                                      "password": NEW_PASSWORD,
                                      "password_confirm": NEW_PASSWORD})
    assert "түр хаагдлаа" in response.content.decode()


# ------------------------------------------------------------------ invitations

def test_an_invitation_is_single_use(client, world, naran_admin_user):
    _, token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    client.post(activate_url(token), {"password": NEW_PASSWORD,
                                      "password_confirm": NEW_PASSWORD})

    assert client.get(activate_url(token)).status_code == 400


def test_an_expired_invitation_is_rejected(client, world, naran_admin_user):
    _, token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )
    Invitation.objects.update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    assert client.get(activate_url(token)).status_code == 400


def test_reissuing_an_invitation_spends_the_previous_one(
    client, world, naran_admin_user
):
    user, first_token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    create_invitation(actor=naran_admin_user, user=user,
                      kindergarten=world["naran"])

    assert client.get(activate_url(first_token)).status_code == 400


def test_only_hashes_are_stored(world, naran_admin_user):
    """A leaked database must not yield working invitations."""
    _, token, code = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    invitation = Invitation.objects.get()
    assert invitation.token_hash != token
    assert invitation.code_hash != code
    assert code not in invitation.code_hash


def test_activation_enforces_the_password_rules(client, world, naran_admin_user):
    user, token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    response = client.post(activate_url(token), {"password": "shinenuuts99",
                                                 "password_confirm": "shinenuuts99"})

    assert response.status_code == 200
    user.refresh_from_db()
    assert not user.has_usable_password()


def test_activation_is_audited(client, world, naran_admin_user):
    _, token, _ = invite_teacher(
        actor=naran_admin_user, kindergarten=world["naran"],
        last_name="Батбаяр", first_name="Сарантуяа", username="sarantuya",
    )

    client.post(activate_url(token), {"password": NEW_PASSWORD,
                                      "password_confirm": NEW_PASSWORD})

    assert AuditLog.objects.filter(action=AuditAction.INVITE).exists()
    assert AuditLog.objects.filter(action=AuditAction.ACTIVATE).exists()
