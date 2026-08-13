"""Organizational rules — RFP §2.1, §3.2."""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Membership, Role
from apps.core.models import AuditAction, AuditLog
from apps.core.permissions import can_access_child
from apps.tenants import services
from apps.tenants.models import Group, GroupTeacher, SchoolYear

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ school year

def test_only_one_school_year_is_current(world, naran_admin_user):
    """RFP §3.2 — setting a new current year clears the previous one."""
    old = world["naran_year"]
    assert old.is_current

    new = SchoolYear(
        kindergarten=world["naran"], name="2026-2027",
        starts_on=dt.date(2026, 9, 1), ends_on=dt.date(2027, 5, 31),
        is_current=True,
    )
    services.save_school_year(actor=naran_admin_user, obj=new, created=True)

    old.refresh_from_db()
    assert not old.is_current
    assert SchoolYear.objects.filter(
        kindergarten=world["naran"], is_current=True
    ).count() == 1


def test_another_kindergartens_current_year_is_untouched(world, naran_admin_user):
    och_year = world["och_year"]

    new = SchoolYear(
        kindergarten=world["naran"], name="2026-2027",
        starts_on=dt.date(2026, 9, 1), ends_on=dt.date(2027, 5, 31),
        is_current=True,
    )
    services.save_school_year(actor=naran_admin_user, obj=new, created=True)

    och_year.refresh_from_db()
    assert och_year.is_current


def test_school_year_must_end_after_it_starts(world, naran_admin_user):
    bad = SchoolYear(
        kindergarten=world["naran"], name="2026-2027",
        starts_on=dt.date(2027, 5, 31), ends_on=dt.date(2026, 9, 1),
    )

    with pytest.raises(ValidationError):
        services.save_school_year(actor=naran_admin_user, obj=bad, created=True)


# ------------------------------------------------------------------ group

def test_group_must_belong_to_its_school_years_kindergarten(world, naran_admin_user):
    """Otherwise the denormalized kindergarten_id points at the wrong tenant."""
    bad = Group(
        kindergarten=world["naran"],
        school_year=world["och_year"],   # belongs to the other kindergarten
        name="Хольсон",
    )

    with pytest.raises(ValidationError):
        services.save_group(actor=naran_admin_user, obj=bad, created=True)


def test_saving_a_group_writes_an_audit_row(world, naran_admin_user):
    group = Group(
        kindergarten=world["naran"], school_year=world["naran_year"],
        name="Сарнай",
    )
    services.save_group(actor=naran_admin_user, obj=group, created=True)

    entry = AuditLog.objects.get(action=AuditAction.CREATE,
                                 object_type="tenants.Group")
    assert entry.kindergarten_id == world["naran"].id
    assert entry.actor_user_id == naran_admin_user.pk


def test_archiving_a_group_keeps_it_queryable(world, naran_admin_user):
    """RFP §3.2 — archived, not deleted. Enrollments still point at it."""
    group = world["sunflower"]

    services.archive_group(actor=naran_admin_user, group=group)

    group.refresh_from_db()
    assert group.status == Group.Status.ARCHIVED
    assert group.deleted_at is None
    assert Group.objects.filter(pk=group.pk).exists()


def test_archiving_a_group_does_not_revoke_teacher_access(world, naran_admin_user):
    """The whole point of archiving rather than deleting."""
    services.archive_group(actor=naran_admin_user, group=world["sunflower"])

    assert can_access_child(world["dulmaa"], world["bataa"])


# ------------------------------------------------------------------ staffing

def test_assigning_a_teacher_grants_access_to_the_groups_children(
    world, naran_admin_user, make_user
):
    """This is an authorization change, which is why it goes through a service."""
    newcomer = make_user(username="shine_bagsh")
    membership = Membership.objects.create(
        user=newcomer, kindergarten=world["naran"], role=Role.TEACHER
    )
    assert not can_access_child(newcomer, world["bataa"])

    services.assign_teacher(
        actor=naran_admin_user, group=world["sunflower"], membership=membership
    )

    assert can_access_child(newcomer, world["bataa"])


def test_cannot_assign_a_teacher_from_another_kindergarten(
    world, naran_admin_user
):
    """RFP §3.2 — otherwise cross-tenant access could be granted by mistake."""
    oyun_membership = world["oyun"].memberships.get()

    with pytest.raises(ValidationError):
        services.assign_teacher(
            actor=naran_admin_user, group=world["sunflower"],
            membership=oyun_membership,
        )


def test_cannot_assign_a_guardian_as_a_teacher(world, naran_admin_user):
    guardian_membership = world["bataa_mother"].memberships.get()

    with pytest.raises(ValidationError):
        services.assign_teacher(
            actor=naran_admin_user, group=world["sunflower"],
            membership=guardian_membership,
        )


def test_cannot_assign_an_inactive_membership(world, naran_admin_user, make_user):
    user = make_user(username="garsan_bagsh")
    membership = Membership.objects.create(
        user=user, kindergarten=world["naran"], role=Role.TEACHER,
        is_active=False,
    )

    with pytest.raises(ValidationError):
        services.assign_teacher(
            actor=naran_admin_user, group=world["sunflower"], membership=membership
        )


def test_assignment_inherits_the_groups_kindergarten(world, naran_admin_user,
                                                     make_user):
    user = make_user(username="bagsh_hoyor")
    membership = Membership.objects.create(
        user=user, kindergarten=world["naran"], role=Role.TEACHER
    )

    assignment = services.assign_teacher(
        actor=naran_admin_user, group=world["sunflower"], membership=membership
    )

    assert assignment.kindergarten_id == world["sunflower"].kindergarten_id
    assert GroupTeacher.objects.filter(pk=assignment.pk).exists()
