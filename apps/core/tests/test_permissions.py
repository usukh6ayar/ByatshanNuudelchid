"""Authorization tests — RFP §21.2, §21.3, §21.4.

These are acceptance criteria, not ordinary unit tests. If any of them fails,
the system does not ship.
"""

import datetime as dt

import pytest
from django.http import Http404

from apps.accounts.models import Role
from apps.children.models import Enrollment
from apps.core.permissions import (
    assert_can_access_child,
    can_access_child,
    child_kindergarten_history,
    visible_kindergartens,
)

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ granted

def test_assigned_teacher_can_access_child(world):
    assert can_access_child(world["dulmaa"], world["bataa"])


def test_guardian_can_access_own_child(world):
    assert can_access_child(world["bataa_mother"], world["bataa"])


def test_kindergarten_admin_can_access_child(world, make_admin):
    admin = make_admin(world["naran"], username="naran_admin")
    assert can_access_child(admin, world["bataa"])


def test_superadmin_can_access_any_child(world, make_admin):
    boss = make_admin(kindergarten=None, role=Role.SUPERADMIN, username="boss")
    assert can_access_child(boss, world["bataa"])


# ------------------------------------------------------------------ denied
# The three mandatory tests from CLAUDE.md §4.1

def test_teacher_from_another_group_is_denied(world, make_teacher):
    """RFP §21.2 — a teacher sees only the children they are responsible for."""
    other_group = world["sunflower"].__class__.objects.create(
        kindergarten=world["naran"],
        school_year=world["naran_year"],
        name="Сарнай",
    )
    stranger = make_teacher(world["naran"], other_group, username="stranger")

    assert not can_access_child(stranger, world["bataa"])


def test_guardian_of_another_child_is_denied(world):
    """RFP §21.3 — a guardian sees only children linked to them."""
    assert not can_access_child(world["bataa_mother"], world["saraa"])


def test_user_from_another_kindergarten_is_denied(world):
    """RFP §21.4 — no cross-tenant access, whatever the URL says."""
    assert not can_access_child(world["oyun"], world["bataa"])


def test_admin_of_another_kindergarten_is_denied(world, make_admin):
    admin = make_admin(world["och"], username="och_admin")
    assert not can_access_child(admin, world["bataa"])


def test_guardian_without_view_right_is_denied(world, make_guardian):
    """can_view=False covers court-ordered restrictions — RFP §3.5."""
    restricted = make_guardian(
        world["bataa"], world["naran"], can_view=False, username="restricted"
    )
    assert not can_access_child(restricted, world["bataa"])


def test_inactive_user_is_denied(world):
    world["dulmaa"].is_active = False
    world["dulmaa"].save()
    assert not can_access_child(world["dulmaa"], world["bataa"])


def test_inactive_membership_is_denied(world):
    world["dulmaa"].memberships.update(is_active=False)
    assert not can_access_child(world["dulmaa"], world["bataa"])


def test_assert_raises_404_not_403(world):
    """404 rather than 403: a 403 would confirm the record exists."""
    with pytest.raises(Http404):
        assert_can_access_child(world["oyun"], world["bataa"])


# ------------------------------------------------------------------ transfers
# Spec section 4.2. Resolving the kindergarten from Child.kindergarten_id
# instead of the enrollment history breaks every test below.

@pytest.fixture
def transferred(world):
    """Bataa transfers from Naran to Och mid-year."""
    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED, ended_on=dt.date(2026, 1, 15)
    )
    Enrollment.objects.create(
        kindergarten=world["och"],
        child=world["bataa"],
        group=world["petal"],
        school_year=world["och_year"],
        started_on=dt.date(2026, 1, 16),
    )
    # The denormalized "currently attending" pointer follows the child.
    world["bataa"].kindergarten = world["och"]
    world["bataa"].save()
    return world


def test_previous_teacher_keeps_access_after_transfer(transferred):
    """Otherwise a teacher loses access to observations they wrote themselves."""
    assert can_access_child(transferred["dulmaa"], transferred["bataa"])


def test_new_teacher_gains_access_after_transfer(transferred):
    assert can_access_child(transferred["oyun"], transferred["bataa"])


def test_guardian_keeps_access_after_transfer(transferred):
    assert can_access_child(transferred["bataa_mother"], transferred["bataa"])


def test_history_spans_both_kindergartens(transferred):
    assert child_kindergarten_history(transferred["bataa"]) == {
        transferred["naran"].id,
        transferred["och"].id,
    }


def test_previous_teacher_sees_only_their_own_kindergarten(transferred):
    """Access to the child is not access to records written elsewhere."""
    assert visible_kindergartens(transferred["dulmaa"], transferred["bataa"]) == {
        transferred["naran"].id
    }


def test_guardian_sees_the_whole_history(transferred):
    """RFP §961 treats the portfolio as the family's record."""
    assert visible_kindergartens(
        transferred["bataa_mother"], transferred["bataa"]
    ) == {transferred["naran"].id, transferred["och"].id}


# ------------------------------------------------------------------ edge cases

def test_newly_registered_child_without_enrollment_is_reachable_by_admin(
    world, make_admin, make_child
):
    """The only case where Child.kindergarten_id affects authorization."""
    fresh = make_child(world["naran"], first_name="Шинэ")
    admin = make_admin(world["naran"], username="fresh_admin")

    assert Enrollment.objects.filter(child=fresh).count() == 0
    assert can_access_child(admin, fresh)


def test_anonymous_user_is_denied(world):
    from django.contrib.auth.models import AnonymousUser

    assert not can_access_child(AnonymousUser(), world["bataa"])


def test_none_user_is_denied(world):
    assert not can_access_child(None, world["bataa"])
