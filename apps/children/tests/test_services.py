"""Child registration, transfers and archiving — RFP §2.2, §3.4."""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.children import services
from apps.children.models import Child, Enrollment
from apps.core.models import AuditAction, AuditLog
from apps.core.permissions import can_access_child, visible_kindergartens

pytestmark = pytest.mark.django_db


def register(world, actor, group=None, **kwargs):
    defaults = {
        "last_name": "Овог", "first_name": "Шинэ",
        "national_id": "XX00000001", "sex": Child.Sex.MALE,
        "date_of_birth": dt.date(2021, 3, 3),
    }
    defaults.update(kwargs)
    return services.register_child(
        actor=actor, group=group or world["sunflower"], **defaults
    )


# ------------------------------------------------------------------ registration

def test_registering_creates_the_enrollment_in_the_same_transaction(
    world, naran_admin_user
):
    """A child with no enrollment is the one authorization edge case."""
    child = register(world, naran_admin_user)

    enrollment = services.current_enrollment(child)
    assert enrollment is not None
    assert enrollment.group_id == world["sunflower"].id
    assert enrollment.kindergarten_id == world["naran"].id


def test_registered_child_is_visible_to_the_groups_teacher(world, naran_admin_user):
    child = register(world, naran_admin_user)

    assert can_access_child(world["dulmaa"], child)
    assert not can_access_child(world["oyun"], child)


def test_registration_is_audited(world, naran_admin_user):
    child = register(world, naran_admin_user)

    entry = AuditLog.objects.get(action=AuditAction.CREATE,
                                 object_type="children.Child")
    assert entry.object_id == str(child.pk)
    assert entry.kindergarten_id == world["naran"].id


def test_duplicate_code_in_the_same_kindergarten_is_rejected(world,
                                                             naran_admin_user):
    from django.db import IntegrityError

    register(world, naran_admin_user, national_id="AA12345678")

    with pytest.raises(IntegrityError):
        register(world, naran_admin_user, national_id="AA12345678",
                 first_name="Хоёрдугаар")


def test_update_rejects_fields_it_does_not_own(world, naran_admin_user):
    """kindergarten follows the enrollment; changing it here would desync it."""
    child = register(world, naran_admin_user)

    with pytest.raises(ValidationError):
        services.update_child(actor=naran_admin_user, child=child,
                              kindergarten_id=world["och"].id)


# ------------------------------------------------------------------ transfers

def test_transfer_within_the_same_school_year(world, naran_admin_user,
                                              make_group):
    """RFP §3.4 — a mid-year group change keeps both rows in one school year."""
    child = register(world, naran_admin_user)
    rose = make_group(world["naran"], world["naran_year"], "Сарнай")

    services.transfer_child(actor=naran_admin_user, child=child, group=rose,
                            started_on=dt.date(2026, 1, 15))

    assert Enrollment.objects.filter(child=child).count() == 2
    assert services.current_enrollment(child).group_id == rose.id
    old = Enrollment.objects.get(child=child, group=world["sunflower"])
    assert old.status == Enrollment.Status.TRANSFERRED
    assert old.ended_on == dt.date(2026, 1, 15)


def test_transfer_to_another_kindergarten_keeps_the_previous_teachers_access(
    world, naran_admin_user
):
    """Spec section 4.2 — the whole reason enrollment history exists."""
    child = register(world, naran_admin_user)

    services.transfer_child(actor=naran_admin_user, child=child,
                            group=world["petal"],
                            started_on=dt.date(2026, 1, 16))

    child.refresh_from_db()
    assert child.kindergarten_id == world["och"].id      # denormalized pointer
    assert can_access_child(world["dulmaa"], child)      # previous teacher
    assert can_access_child(world["oyun"], child)        # new teacher


def test_previous_teacher_sees_only_their_own_kindergartens_records(
    world, naran_admin_user
):
    child = register(world, naran_admin_user)
    services.transfer_child(actor=naran_admin_user, child=child,
                            group=world["petal"],
                            started_on=dt.date(2026, 1, 16))

    assert visible_kindergartens(world["dulmaa"], child) == {world["naran"].id}
    assert visible_kindergartens(world["oyun"], child) == {world["och"].id}


def test_transfer_into_the_same_group_is_rejected(world, naran_admin_user):
    child = register(world, naran_admin_user)

    with pytest.raises(ValidationError):
        services.transfer_child(actor=naran_admin_user, child=child,
                                group=world["sunflower"],
                                started_on=dt.date(2026, 1, 15))


def test_transfer_cannot_start_before_the_current_enrollment(world,
                                                             naran_admin_user):
    child = register(world, naran_admin_user)

    with pytest.raises(ValidationError):
        services.transfer_child(actor=naran_admin_user, child=child,
                                group=world["petal"],
                                started_on=dt.date(2020, 1, 1))


# ------------------------------------------------------------------ archiving

def test_archiving_closes_the_enrollment(world, naran_admin_user):
    """Otherwise the child keeps appearing in their old group's lists."""
    child = register(world, naran_admin_user)

    services.archive_child(actor=naran_admin_user, child=child,
                           left_on=dt.date(2026, 5, 31))

    child.refresh_from_db()
    assert child.status == Child.Status.ARCHIVED
    assert services.current_enrollment(child) is None
    # Archived, not deleted — RFP §3.4
    assert Child.objects.filter(pk=child.pk).exists()


def test_archiving_does_not_remove_the_history(world, naran_admin_user):
    child = register(world, naran_admin_user)
    services.archive_child(actor=naran_admin_user, child=child)

    assert Enrollment.objects.filter(child=child).count() == 1
