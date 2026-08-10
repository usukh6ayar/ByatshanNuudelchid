"""The child edit screen — RFP §2.2, §21.2–21.4.

The last gap in the Phase 1 requirement table: `update_child` has existed in
``services.py`` since Day 3, and until now nothing reached it from a browser.
The service already owns the rules, so this is a view, a template and the
proof that the view is not reachable by the wrong person.

Editing is a **staff** action, so the gate is ``can_record_for_child`` rather
than ``can_access_child``. A guardian may read the record and write their own
part of the portfolio (§2.3); the child's registration details are the
kindergarten's. That distinction is tested below, because it is the one a
reviewer will not see just by reading the URL conf.
"""

import pytest
from django.urls import reverse

from apps.children.models import Child

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def edit_url(child):
    return reverse("children:edit", args=[child.pk])


def valid_payload(child, **overrides):
    """What the form posts back when a teacher changes one field."""
    payload = {
        "last_name": child.last_name,
        "first_name": child.first_name,
        "national_id": child.national_id,
        "sex": child.sex,
        "date_of_birth": child.date_of_birth.isoformat(),
        "health_notes": child.health_notes,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ the three
# CLAUDE.md §4.1. Through the HTTP client, both verbs: a view that gates GET
# and forgets POST is a view that still writes.

def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group):
    """RFP §21.2."""
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other_group, username="stranger")
    login(client, stranger)

    assert client.get(edit_url(world["bataa"])).status_code == 404
    assert client.post(edit_url(world["bataa"]),
                       valid_payload(world["bataa"])).status_code == 404


def test_guardian_of_another_child_gets_404(client, world):
    """RFP §21.3."""
    login(client, world["bataa_mother"])

    assert client.get(edit_url(world["saraa"])).status_code == 404
    assert client.post(edit_url(world["saraa"]),
                       valid_payload(world["saraa"])).status_code == 404


def test_user_from_another_kindergarten_gets_404(client, world):
    """RFP §21.4."""
    login(client, world["oyun"])

    assert client.get(edit_url(world["bataa"])).status_code == 404
    assert client.post(edit_url(world["bataa"]),
                       valid_payload(world["bataa"])).status_code == 404


def test_anonymous_users_are_sent_to_login(client, world):
    response = client.get(edit_url(world["bataa"]))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


# ------------------------------------------------ reading is not writing

def test_a_guardian_cannot_edit_their_own_child(client, world):
    """§2.3 gives a guardian the portfolio, not the registration record.

    ``can_access_child`` would pass here — she may open this child's page.
    The edit screen asks for the national id, the enrollment date and the
    health notes, which are the kindergarten's record of the child, so the
    gate is ``can_record_for_child``.
    """
    login(client, world["bataa_mother"])

    assert client.get(edit_url(world["bataa"])).status_code == 404

    response = client.post(edit_url(world["bataa"]),
                           valid_payload(world["bataa"], first_name="Өөрчлөв"))

    assert response.status_code == 404
    world["bataa"].refresh_from_db()
    assert world["bataa"].first_name == "Батаа"


# ------------------------------------------------------------------ granted

def test_the_assigned_teacher_can_open_the_form(client, world):
    login(client, world["dulmaa"])

    response = client.get(edit_url(world["bataa"]))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Батаа" in body
    assert "Хадгалах" in body


def test_the_assigned_teacher_can_change_a_detail(client, world):
    """RFP §2.2 — "хүүхдийн мэдээлэл засах"."""
    login(client, world["dulmaa"])

    response = client.post(edit_url(world["bataa"]), valid_payload(
        world["bataa"], first_name="Батбаяр", health_notes="Самрын харшилтай"
    ))

    assert response.status_code == 302
    assert response.url == reverse("children:detail", args=[world["bataa"].pk])

    world["bataa"].refresh_from_db()
    assert world["bataa"].first_name == "Батбаяр"
    assert world["bataa"].health_notes == "Самрын харшилтай"


def test_a_kindergarten_admin_can_edit(client, world, make_admin):
    admin = make_admin(world["naran"], username="naran_director")
    login(client, admin)

    response = client.post(edit_url(world["bataa"]),
                           valid_payload(world["bataa"], last_name="Дорж"))

    assert response.status_code == 302
    world["bataa"].refresh_from_db()
    assert world["bataa"].last_name == "Дорж"


# ------------------------------------------------------- what it must not do

def test_the_group_cannot_be_changed_through_the_edit_form(client, world,
                                                           make_group):
    """Moving a child between groups is a transfer, not an edit.

    ``transfer_child`` writes an Enrollment row, which is what
    ``child_kindergarten_history`` reads for authorization (CLAUDE.md §1.2).
    A form that quietly reassigned the group would move the child without
    that history, and the previous teacher would lose access to observations
    they wrote themselves.
    """
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    login(client, world["dulmaa"])

    client.post(edit_url(world["bataa"]),
                valid_payload(world["bataa"], group=other_group.pk))

    enrollment = world["bataa"].enrollments.get(status="active")
    assert enrollment.group == world["sunflower"]


def test_the_kindergarten_cannot_be_changed_through_the_edit_form(client, world):
    """Same reasoning, one level up — and this one crosses a tenant."""
    login(client, world["dulmaa"])

    client.post(edit_url(world["bataa"]),
                valid_payload(world["bataa"], kindergarten=world["och"].pk))

    world["bataa"].refresh_from_db()
    assert world["bataa"].kindergarten == world["naran"]


def test_an_invalid_date_is_reported_not_swallowed(client, world):
    original = world["bataa"].date_of_birth
    login(client, world["dulmaa"])

    response = client.post(edit_url(world["bataa"]),
                           valid_payload(world["bataa"], date_of_birth="огноо"))

    assert response.status_code == 200
    assert "Төрсөн огноо" in response.content.decode()

    world["bataa"].refresh_from_db()
    assert world["bataa"].date_of_birth == original


def test_a_duplicate_national_id_is_refused(client, world):
    """The model's uniqueness rule must surface as a message, not a 500.

    `uniq_child_national_id` is a partial unique constraint in PostgreSQL and
    nothing checked it before the INSERT, so a teacher who mistyped a
    registration number that already existed met a server error. Registering
    a new child had the same hole; ``test_services.py`` covers that half.
    """
    login(client, world["dulmaa"])

    response = client.post(
        edit_url(world["bataa"]),
        valid_payload(world["bataa"], national_id=world["saraa"].national_id),
    )

    assert response.status_code == 200
    assert "регистр" in response.content.decode().lower()

    world["bataa"].refresh_from_db()
    assert world["bataa"].national_id != world["saraa"].national_id


def test_the_childs_own_national_id_is_not_a_clash_with_itself(client, world):
    """Saving the form unchanged must not trip the uniqueness check."""
    login(client, world["dulmaa"])

    response = client.post(edit_url(world["bataa"]),
                           valid_payload(world["bataa"], first_name="Батбаяр"))

    assert response.status_code == 302
    world["bataa"].refresh_from_db()
    assert world["bataa"].first_name == "Батбаяр"


# ------------------------------------------------------------------ the trail

def test_an_edit_is_written_to_the_audit_log(client, world):
    """RFP §971 — who changed what."""
    from apps.core.models import AuditAction, AuditLog

    login(client, world["dulmaa"])
    client.post(edit_url(world["bataa"]),
                valid_payload(world["bataa"], first_name="Батбаяр"))

    entry = AuditLog.objects.filter(
        action=AuditAction.UPDATE,
        object_id=str(world["bataa"].pk),
        object_type=Child._meta.label,
    ).latest("created_at")

    assert entry.actor_user == world["dulmaa"]
    assert entry.kindergarten == world["naran"]


def test_the_edit_link_is_on_the_detail_page_for_staff_only(client, world):
    """A guardian is not shown a door that answers 404."""
    login(client, world["dulmaa"])
    teacher_body = client.get(
        reverse("children:detail", args=[world["bataa"].pk])
    ).content.decode()
    assert edit_url(world["bataa"]) in teacher_body

    client.logout()
    login(client, world["bataa_mother"])
    parent_body = client.get(
        reverse("children:parent_child_detail", args=[world["bataa"].pk])
    ).content.decode()
    assert edit_url(world["bataa"]) not in parent_body
