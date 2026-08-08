"""Admin screens — RFP §2.1, §3.2, §21.4.

View-level tests through the HTTP client (CLAUDE.md §4.1): they prove the
admin actually enforces tenant isolation and routes writes through
``services``, not that a helper would have said the right thing.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.models import AuditAction, AuditLog
from apps.tenants.models import Group, Kindergarten, SchoolYear

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"

INDEX = "/udirdlaga/"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def changelist(model):
    return reverse(f"udirdlaga:{model._meta.app_label}_{model._meta.model_name}"
                   f"_changelist")


def change_page(obj):
    meta = obj._meta
    return reverse(
        f"udirdlaga:{meta.app_label}_{meta.model_name}_change", args=[obj.pk]
    )


@pytest.fixture
def naran_admin(world, make_admin):
    return make_admin(world["naran"], username="naran_admin")


@pytest.fixture
def boss(make_admin):
    return make_admin(kindergarten=None, role=Role.SUPERADMIN, username="boss")


# ------------------------------------------------------------------ access
# Who may reach /udirdlaga/ at all.

def test_anonymous_user_is_redirected_to_login(client):
    response = client.get(INDEX)
    assert response.status_code == 302
    assert "login" in response.url


def test_admin_login_uses_the_projects_throttled_login_page(client):
    """Django's admin login would be a second, unthrottled way in.

    RFP §3.1's lockout and §971's audit entries live in our login view; an
    administrator account must not be able to skip them.
    """
    response = client.get("/udirdlaga/login/", follow=True)

    assert response.redirect_chain
    assert response.redirect_chain[0][0].startswith(reverse("accounts:login"))
    # The role tabs only exist on the project's own login page.
    body = response.content.decode()
    assert "Хэрэглэгчийн төрөл" in body
    assert "Нууц үгээ мартсан уу?" in body


def test_admin_lockout_applies_to_administrators(client, naran_admin, settings):
    """The most valuable accounts must not be the only unthrottled ones."""
    login_url = reverse("accounts:login")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        client.post(login_url, {"username": naran_admin.username,
                                "password": "wrong-one"})

    response = client.post(login_url, {"username": naran_admin.username,
                                       "password": PASSWORD})

    assert "_auth_user_id" not in client.session
    assert "түр хаагдлаа" in response.content.decode()


def test_teacher_cannot_reach_the_admin(client, world):
    """RFP §2.1 separates administrator rights from teachers."""
    login(client, world["dulmaa"])
    response = client.get(INDEX)
    assert response.status_code == 302


def test_guardian_cannot_reach_the_admin(client, world):
    login(client, world["bataa_mother"])
    assert client.get(INDEX).status_code == 302


def test_kindergarten_admin_can_reach_the_admin(client, naran_admin):
    login(client, naran_admin)
    assert client.get(INDEX).status_code == 200


def test_admin_works_without_django_permission_rows(client, naran_admin):
    """Authorization comes from Membership, not auth.Permission.

    A director has no Permission rows at all; if the ModelAdmin deferred to
    Django's permission system every section would come back empty.
    """
    assert not naran_admin.user_permissions.exists()
    assert not naran_admin.groups.exists()

    login(client, naran_admin)
    assert client.get(changelist(Group)).status_code == 200


def test_deactivated_membership_loses_access(client, naran_admin):
    naran_admin.memberships.update(is_active=False)
    login(client, naran_admin)
    assert client.get(INDEX).status_code == 302


# ------------------------------------------------------------------ isolation
# RFP §3.2, §21.4 — one kindergarten's data is invisible to another's staff.

def test_admin_list_shows_only_own_kindergarten_groups(client, world, naran_admin):
    login(client, naran_admin)

    body = client.get(changelist(Group)).content.decode()

    assert world["sunflower"].name in body
    assert world["petal"].name not in body


def test_admin_cannot_open_another_kindergartens_group(client, world, naran_admin):
    """Editing the URL must not reveal another kindergarten's record."""
    login(client, naran_admin)

    assert client.get(change_page(world["petal"])).status_code == 302


def test_admin_cannot_see_another_kindergarten_itself(client, world, naran_admin):
    login(client, naran_admin)

    body = client.get(changelist(Kindergarten)).content.decode()

    assert "Наран" in body
    assert "Оч" not in body


def test_superadmin_sees_every_kindergarten(client, world, boss):
    login(client, boss)

    body = client.get(changelist(Kindergarten)).content.decode()

    assert "Наран" in body
    assert "Оч" in body


def test_only_superadmin_can_register_a_kindergarten(client, naran_admin, boss):
    """RFP §2.1 puts kindergarten registration at the system level."""
    add_url = reverse("udirdlaga:tenants_kindergarten_add")

    login(client, naran_admin)
    assert client.get(add_url).status_code == 403

    client.logout()
    login(client, boss)
    assert client.get(add_url).status_code == 200


def test_director_cannot_grant_the_superadmin_role(client, world, naran_admin):
    login(client, naran_admin)

    body = client.get(reverse("udirdlaga:accounts_membership_add")).content.decode()

    assert 'value="admin"' in body
    assert 'value="superadmin"' not in body


# ------------------------------------------------------------------ services
# CLAUDE.md §2.4 — admin writes must not bypass services.

def test_saving_through_the_admin_writes_an_audit_row(client, world, naran_admin):
    login(client, naran_admin)
    group = world["sunflower"]

    client.post(change_page(group), {
        "kindergarten": group.kindergarten_id,
        "school_year": group.school_year_id,
        "name": "Наранцэцэг",
        "age_category": "4-5 нас",
        "status": Group.Status.ACTIVE,
        "timetable": "",
        "rules": "",
        "teacher_assignments-TOTAL_FORMS": "0",
        "teacher_assignments-INITIAL_FORMS": "0",
        "teacher_assignments-MIN_NUM_FORMS": "0",
        "teacher_assignments-MAX_NUM_FORMS": "1000",
    })

    entry = AuditLog.objects.filter(action=AuditAction.UPDATE,
                                    object_type="tenants.Group").get()
    assert entry.actor_user_id == naran_admin.pk
    assert entry.object_id == str(group.pk)


def test_deleting_through_the_admin_soft_deletes(client, world, naran_admin):
    """RFP §3.4 — records are archived, never removed."""
    login(client, naran_admin)
    year = SchoolYear.objects.create(
        kindergarten=world["naran"], name="2099-2100",
        starts_on="2099-09-01", ends_on="2100-05-31",
    )

    client.post(
        reverse("udirdlaga:tenants_schoolyear_delete", args=[year.pk]),
        {"post": "yes"},
    )

    year.refresh_from_db()
    assert year.deleted_at is not None
    assert year.deleted_by_id == naran_admin.pk
    assert not SchoolYear.objects.filter(pk=year.pk).exists()
    assert SchoolYear.all_objects.filter(pk=year.pk).exists()


def test_bulk_delete_action_also_soft_deletes(client, world, naran_admin):
    """The bulk action bypasses delete_model and needs its own override."""
    login(client, naran_admin)
    year = SchoolYear.objects.create(
        kindergarten=world["naran"], name="2098-2099",
        starts_on="2098-09-01", ends_on="2099-05-31",
    )

    client.post(changelist(SchoolYear), {
        "action": "delete_selected",
        "_selected_action": [str(year.pk)],
        "post": "yes",
    })

    assert SchoolYear.all_objects.get(pk=year.pk).deleted_at is not None
