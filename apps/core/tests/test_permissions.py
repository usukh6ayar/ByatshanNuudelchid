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
    can_record_for_child,
    child_kindergarten_history,
    is_guardian_of,
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


def test_revoked_guardian_is_denied(world, revoke_guardianship):
    """A soft-deleted Guardianship is a revocation — RFP §3.5, §21.3.

    Archived rather than deleted (CLAUDE.md §3.3), so every predicate has to
    honour ``deleted_at`` for the revocation to mean anything.
    """
    revoke_guardianship(world["bataa"], world["bataa_mother"])

    assert not is_guardian_of(world["bataa_mother"], world["bataa"])
    assert not can_access_child(world["bataa_mother"], world["bataa"])


def test_a_revoked_guardian_disappears_from_every_list(
    world, revoke_guardianship
):
    """The regression test for the leak fixed on 2026-08-16.

    ``is_guardian_of`` filtered soft-deleted rows through the default
    manager; the two *join*-based predicates did not, because a
    reverse-relation join ignores the related model's default manager. The
    child therefore vanished from the detail check and stayed in both lists,
    and the parent home went on rendering their name, photo, group, recent
    observations and photographs to someone whose access had been removed.

    Asserted on all three predicates rather than on the fix's shape: what
    matters is that they agree, not which clause achieves it.
    """
    from apps.children.selectors import guardian_children
    from apps.core.permissions import visible_children

    mother, bataa = world["bataa_mother"], world["bataa"]
    # Before: all three agree that access exists.
    assert is_guardian_of(mother, bataa)
    assert visible_children(mother).filter(pk=bataa.pk).exists()
    assert guardian_children(mother).filter(pk=bataa.pk).exists()

    revoke_guardianship(bataa, mother)

    assert not is_guardian_of(mother, bataa)
    assert not visible_children(mother).filter(pk=bataa.pk).exists()
    assert not guardian_children(mother).filter(pk=bataa.pk).exists()


def test_revoking_one_guardianship_leaves_the_other_guardian_alone(
    world, make_guardian, revoke_guardianship
):
    """Revocation is per-link, not per-child.

    Without this the fix could pass by breaking guardian access wholesale —
    a filter on the wrong side of the join would deny both parents.
    """
    from apps.children.selectors import guardian_children

    father = make_guardian(world["bataa"], world["naran"], username="bataa_father")
    revoke_guardianship(world["bataa"], world["bataa_mother"])

    assert can_access_child(father, world["bataa"])
    assert guardian_children(father).filter(pk=world["bataa"].pk).exists()


def test_a_revoked_guardian_keeps_access_to_a_sibling(
    world, make_child, make_guardian, revoke_guardianship
):
    """Revocation is per-child too — one link going does not take the rest."""
    from apps.children.models import Guardianship
    from apps.children.selectors import guardian_children

    sibling = make_child(world["naran"], world["sunflower"], first_name="Дүү")
    Guardianship.objects.create(
        kindergarten=world["naran"], child=sibling,
        guardian_user=world["bataa_mother"],
        relation=Guardianship.Relation.MOTHER,
    )

    revoke_guardianship(world["bataa"], world["bataa_mother"])

    listed = set(guardian_children(world["bataa_mother"]).values_list("pk", flat=True))
    assert listed == {sibling.pk}
    assert can_access_child(world["bataa_mother"], sibling)


def test_revoked_teacher_is_denied(world, revoke_group_teacher):
    """A soft-deleted GroupTeacher is a withdrawn assignment — RFP §2.2.

    The staff mirror of ``test_revoked_guardian_is_denied``.
    """
    assert can_access_child(world["dulmaa"], world["bataa"])

    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    assert not can_access_child(world["dulmaa"], world["bataa"])


def test_a_revoked_teacher_disappears_from_every_list(world,
                                                      revoke_group_teacher):
    """The regression test for the GroupTeacher half of the 2026-08-16 leak.

    ``_is_assigned_teacher`` queried ``GroupTeacher.objects`` and dropped
    soft-deleted assignments; ``visible_children`` and ``assignable_groups``
    joined to ``teacher_assignments`` and kept them. The child vanished from
    the detail check and stayed in the children list.

    Asserted across all three predicates, because agreement is the property
    under test — not the shape of the clause that achieves it.
    """
    from apps.core.permissions import visible_children
    from apps.tenants.selectors import assignable_groups

    dulmaa, bataa = world["dulmaa"], world["bataa"]
    assert visible_children(dulmaa).filter(pk=bataa.pk).exists()
    assert assignable_groups(dulmaa).filter(pk=world["sunflower"].pk).exists()

    revoke_group_teacher(dulmaa, world["sunflower"])

    assert not can_access_child(dulmaa, bataa)
    assert not visible_children(dulmaa).filter(pk=bataa.pk).exists()
    assert not assignable_groups(dulmaa).filter(pk=world["sunflower"].pk).exists()


def test_revoking_one_teacher_leaves_the_co_teacher_alone(
    world, make_teacher, revoke_group_teacher
):
    """Revocation is per-assignment.

    Without this, a fix that filtered on the wrong side of the join — or
    denied assigned teachers wholesale — would pass every test above.
    """
    from apps.core.permissions import visible_children

    co_teacher = make_teacher(world["naran"], world["sunflower"],
                              username="co_teacher")

    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    assert can_access_child(co_teacher, world["bataa"])
    assert visible_children(co_teacher).filter(pk=world["bataa"].pk).exists()
    assert can_record_for_child(co_teacher, world["bataa"])


def test_a_teacher_revoked_from_one_group_keeps_the_other(
    world, make_group, make_child, revoke_group_teacher
):
    """Revocation is per-group too — one assignment going takes only its own.

    ``dulmaa`` teaches two groups; the assignment to the first is withdrawn
    and the children of the second must be untouched.
    """
    from apps.accounts.models import Membership
    from apps.core.permissions import visible_children
    from apps.tenants.models import GroupTeacher

    second = make_group(world["naran"], world["naran_year"], "Сарнай")
    other_child = make_child(world["naran"], second, first_name="Нөгөө")
    membership = Membership.objects.get(user=world["dulmaa"],
                                        kindergarten=world["naran"])
    GroupTeacher.objects.create(kindergarten=world["naran"], group=second,
                                teacher_membership=membership)

    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    assert not can_access_child(world["dulmaa"], world["bataa"])
    assert can_access_child(world["dulmaa"], other_child)
    listed = set(visible_children(world["dulmaa"]).values_list("pk", flat=True))
    assert listed == {other_child.pk}


def test_a_revoked_teacher_may_no_longer_record(world, revoke_group_teacher):
    """Withdrawing the assignment removes the write permission with it.

    ``can_record_for_child`` is the other caller of the shared predicate, so
    it has to move in step — a teacher who cannot see the child must not be
    able to file an observation about them (RFP §5.1).
    """
    assert can_record_for_child(world["dulmaa"], world["bataa"])

    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    assert not can_record_for_child(world["dulmaa"], world["bataa"])


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


# ------------------------------------------------------------------ invariant
# visible_children (lists) and can_access_child (detail pages) must agree.
# A child in a list that 404s when opened is a bug; the reverse is a leak.

def _assert_list_and_detail_agree(users):
    """The invariant itself, so both callers below assert it identically."""
    from apps.children.models import Child
    from apps.core.permissions import visible_children

    for user in users:
        listed = set(visible_children(user).values_list("pk", flat=True))
        for child in Child.objects.all():
            assert (child.pk in listed) == can_access_child(user, child), (
                f"{user} vs {child}: list says {child.pk in listed}, "
                f"detail says {can_access_child(user, child)}"
            )


def test_visible_children_agrees_with_can_access_child(
    world, make_admin, make_child, transferred
):
    # The `transferred` fixture is here for its side effect: it puts one
    # child in two kindergartens, which is the case most likely to make the
    # list query and the detail check disagree.
    assert transferred["bataa"].kindergarten_id == world["och"].id

    # A child nobody in `world` is attached to, plus one with no enrollment.
    make_child(world["och"], world["petal"], first_name="Гадны")
    make_child(world["naran"], first_name="Бүлэггүй")

    _assert_list_and_detail_agree([
        world["dulmaa"], world["oyun"], world["bataa_mother"],
        make_admin(world["naran"], username="inv_naran_admin"),
        make_admin(world["och"], username="inv_och_admin"),
        make_admin(kindergarten=None, role=Role.SUPERADMIN, username="inv_boss"),
        # An accountant (нэмэлт.md §13). Added here because this invariant
        # only covers the users it is handed: a new role that reads child
        # data through one path and not the other would pass every test in
        # this file without appearing in this list. For an accountant both
        # sides must answer *no* — they are a user of the money axis, not
        # this one. See `test_finance_permissions.py`.
        make_admin(world["naran"], role=Role.ACCOUNTANT,
                   username="inv_naran_nyagtlan"),
    ])


def test_visible_children_agrees_after_a_guardianship_is_revoked(
    world, make_admin, make_child, make_guardian, revoke_guardianship
):
    """The invariant, over the state no fixture used to produce.

    The equivalence above is the reason to trust that lists and detail pages
    cannot disagree — but it can only cover the states its fixtures build,
    and none of them held a soft-deleted ``Guardianship``. That gap is
    precisely where the 2026-08-16 leak lived: the invariant held everywhere
    the suite looked, and broke the moment a guardian was revoked.

    A second guardian and a sibling are in scope deliberately, so a fix that
    denied too much fails here just as loudly as one that denied too little.

    The GroupTeacher equivalent is the test below.
    """
    make_guardian(world["bataa"], world["naran"], username="eq_father")
    sibling = make_child(world["naran"], world["sunflower"], first_name="Дүү")
    make_guardian(sibling, world["naran"], username="eq_sibling_parent")

    revoke_guardianship(world["bataa"], world["bataa_mother"])

    _assert_list_and_detail_agree([
        world["bataa_mother"],
        world["dulmaa"],
        make_admin(world["naran"], username="eq_naran_admin"),
    ])


# ------------------------------------------------------------- staff writes
# can_record_for_child: reading a child's record and writing a professional
# one about them are different permissions (RFP §5.1, §5.4, §6.3).

def test_a_teacher_may_record(world):
    assert can_record_for_child(world["dulmaa"], world["bataa"])


def test_an_admin_may_record(world, make_admin):
    admin = make_admin(world["naran"], username="recording_admin")

    assert can_record_for_child(admin, world["bataa"])


def test_a_guardian_may_read_but_not_record(world):
    """The guardian's own contribution goes in as source=parent (§5.4)."""
    assert can_access_child(world["bataa_mother"], world["bataa"])
    assert not can_record_for_child(world["bataa_mother"], world["bataa"])


def test_a_teacher_at_another_kindergarten_may_not_record(world):
    assert not can_record_for_child(world["oyun"], world["bataa"])


def test_a_teacher_may_not_record_about_their_own_child_in_another_group(
    world, make_group
):
    """One person, two memberships — RFP §2.2 and §2.3 both apply.

    A teacher whose own child attends the same kindergarten reaches that
    child through the guardianship, not through an assignment. Letting the
    staff role alone carry the write permission would put a parent's words
    into the portfolio as professional judgement about their own child.
    """
    from apps.accounts.models import Membership, Role
    from apps.tenants.models import GroupTeacher

    parent_who_teaches = world["bataa_mother"]
    other_group = make_group(world["naran"], world["naran_year"], "Сарнай")
    membership = Membership.objects.create(
        user=parent_who_teaches, kindergarten=world["naran"], role=Role.TEACHER
    )
    GroupTeacher.objects.create(
        kindergarten=world["naran"], group=other_group,
        teacher_membership=membership,
    )

    # They may read their own child's record — the guardianship says so.
    assert can_access_child(parent_who_teaches, world["bataa"])
    # But they teach a different group, so they may not write a staff one.
    assert not can_record_for_child(parent_who_teaches, world["bataa"])
    # And a child they neither guard nor teach is out of reach entirely.
    assert not can_record_for_child(parent_who_teaches, world["saraa"])


def test_the_same_teacher_may_record_once_assigned_to_the_group(world):
    """The mirror of the test above: the assignment is what grants it."""
    from apps.accounts.models import Membership, Role
    from apps.tenants.models import GroupTeacher

    parent_who_teaches = world["bataa_mother"]
    membership = Membership.objects.create(
        user=parent_who_teaches, kindergarten=world["naran"], role=Role.TEACHER
    )
    GroupTeacher.objects.create(
        kindergarten=world["naran"], group=world["sunflower"],
        teacher_membership=membership,
    )

    assert can_record_for_child(parent_who_teaches, world["bataa"])


def test_a_previous_teacher_may_still_record_after_a_transfer(transferred):
    """They keep the record they own — spec section 4.2."""
    assert can_record_for_child(transferred["dulmaa"], transferred["bataa"])


def test_an_anonymous_user_may_not_record(world):
    from django.contrib.auth.models import AnonymousUser

    assert not can_record_for_child(AnonymousUser(), world["bataa"])


def test_visible_children_agrees_after_an_assignment_is_revoked(
    world, make_admin, make_child, make_teacher, revoke_group_teacher
):
    """The invariant, over a withdrawn GroupTeacher assignment.

    The staff mirror of the guardianship case above, and the second half of
    the 2026-08-16 fix. A co-teacher and a second group are in scope so the
    invariant has something to hold on to: a fix that denied every assigned
    teacher would satisfy "list and detail agree" trivially, and fails here
    because the co-teacher must still see the child.
    """
    from apps.accounts.models import Membership
    from apps.tenants.models import GroupTeacher

    co_teacher = make_teacher(world["naran"], world["sunflower"],
                              username="eq_co_teacher")
    second = world["sunflower"].__class__.objects.create(
        kindergarten=world["naran"], school_year=world["naran_year"],
        name="Сарнай",
    )
    make_child(world["naran"], second, first_name="Нөгөө")
    membership = Membership.objects.get(user=world["dulmaa"],
                                        kindergarten=world["naran"])
    GroupTeacher.objects.create(kindergarten=world["naran"], group=second,
                                teacher_membership=membership)

    revoke_group_teacher(world["dulmaa"], world["sunflower"])

    _assert_list_and_detail_agree([
        world["dulmaa"],
        co_teacher,
        world["bataa_mother"],
        make_admin(world["naran"], username="eq_assign_admin"),
    ])
