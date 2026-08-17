"""The money axis — нэмэлт.md §13.

`Role.ACCOUNTANT` is the first role in the system that reads one kind of
record and is refused another. Everything before it answered a single
question ("may this user see this child?"); these tests pin the second
question down and, just as importantly, pin the **separation** between them.

The tests that matter most are not the ones showing an accountant can see an
invoice. They are:

* an accountant must NOT gain access to a child's developmental record, and
* a teacher must NOT gain access to money,

because those are the two directions the separation can fail in, and either
one is a privacy breach in the file CLAUDE.md §1.1 calls the most important
thirty lines in the system.
"""

import pytest

from apps.accounts.models import Role
from apps.core.permissions import (
    can_access_child,
    can_manage_finance,
    can_view_child_finance,
    can_view_finance,
    finance_kindergartens,
    visible_children,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def accountant(make_admin, world):
    """A НЯГТЛАН at Наран, the kindergarten `world` is built around."""
    return make_admin(
        world["naran"], role=Role.ACCOUNTANT, username="nyagtlan_naran"
    )


@pytest.fixture
def other_accountant(make_admin, world):
    """A НЯГТЛАН at a different kindergarten — the tenant-isolation case."""
    return make_admin(
        world["och"], role=Role.ACCOUNTANT, username="nyagtlan_och"
    )


# ------------------------------------------------------- the separation itself

def test_an_accountant_cannot_see_a_childs_developmental_record(
    accountant, world
):
    """The whole point of a separate axis — §13.

    Money and observations are different kinds of record. An accountant who
    passed `can_access_child` would reach the portfolio, the health notes and
    the photographs, none of which billing requires.
    """
    assert not can_access_child(accountant, world["bataa"])


def test_an_accountant_appears_in_no_childs_list(accountant, world):
    """The list-level half of the same claim.

    `can_access_child` returning False is not enough on its own: if
    `visible_children` disagreed, every list screen would show children the
    detail page then refuses. That inconsistency is exactly the shape of the
    two authorization leaks fixed on 2026-08-16.
    """
    assert not visible_children(accountant).exists()


def test_a_teacher_cannot_see_money(world):
    """§13, stated the other way round.

    A teacher who could read invoices would know which families are behind on
    payments — information the kindergarten never intended to give them, about
    the parents of children in their own group.
    """
    teacher = world["dulmaa"]

    assert finance_kindergartens(teacher) == set()
    assert not can_view_finance(teacher, world["naran"].pk)
    assert not can_manage_finance(teacher, world["naran"].pk)
    assert not can_view_child_finance(teacher, world["bataa"])


def test_a_teacher_keeps_full_access_to_the_child(world):
    """The separation must cut one way only.

    Denying teachers money must not cost them anything they had — this is the
    regression that would turn a privacy fix into a broken product.
    """
    assert can_access_child(world["dulmaa"], world["bataa"])


# ------------------------------------------------------------ positive access

def test_an_accountant_sees_their_own_kindergartens_money(accountant, world):
    assert finance_kindergartens(accountant) == {world["naran"].pk}
    assert can_view_finance(accountant, world["naran"].pk)
    assert can_manage_finance(accountant, world["naran"].pk)


def test_an_accountant_sees_the_money_of_a_child_they_bill(accountant, world):
    assert can_view_child_finance(accountant, world["bataa"])


def test_an_administrator_sees_money_too(make_admin, world):
    """An administrator runs the kindergarten; §9's dashboard is theirs."""
    admin = make_admin(world["naran"], username="fin_admin")

    assert can_view_finance(admin, world["naran"].pk)
    assert can_manage_finance(admin, world["naran"].pk)


def test_a_guardian_sees_their_own_childs_bill(world):
    """§7 invoices the family and §8 asks them to pay it.

    Neither works if the family cannot see what they owe. Note this arrives
    through the guardian branch, not through `finance_kindergartens` — a
    parent has no kindergarten-wide financial access.
    """
    mother = world["bataa_mother"]

    assert can_view_child_finance(mother, world["bataa"])
    assert finance_kindergartens(mother) == set()
    assert not can_view_finance(mother, world["naran"].pk)


# ---------------------------------------------------------- tenant isolation

def test_an_accountant_cannot_see_another_kindergartens_money(
    other_accountant, world
):
    """RFP §3.2 — the isolation that applies to every other table.

    Financial records are the case where a leak across tenants is worst: it
    is another business's revenue, arrears and state funding claims.
    """
    assert not can_view_finance(other_accountant, world["naran"].pk)
    assert not can_manage_finance(other_accountant, world["naran"].pk)
    assert not can_view_child_finance(other_accountant, world["bataa"])


def test_an_inactive_membership_grants_nothing(accountant, world):
    """A dismissed accountant keeps nothing.

    The same shape as the two 2026-08-16 leaks: revocation has to be read at
    query time, not assumed from the row's existence.
    """
    accountant.memberships.update(is_active=False)

    assert finance_kindergartens(accountant) == set()
    assert not can_view_child_finance(accountant, world["bataa"])


def test_an_anonymous_user_gets_nothing():
    from django.contrib.auth.models import AnonymousUser

    anon = AnonymousUser()

    assert finance_kindergartens(anon) == set()
    assert not can_view_finance(anon, 1)
    assert not can_manage_finance(anon, 1)


def test_a_missing_kindergarten_is_refused_not_waved_through(accountant):
    """`None` must be a refusal, not a match.

    A caller that has not resolved the kindergarten yet passes `None`. If that
    were treated as "no restriction", an unscoped query would become a
    cross-tenant read.
    """
    assert not can_view_finance(accountant, None)
    assert not can_manage_finance(accountant, None)


# ------------------------------------------------------------------ transfers

def test_finance_follows_the_enrollment_history(make_admin, world):
    """CLAUDE.md §1.2, now with money attached.

    A child who transfers in March leaves a March invoice behind. The
    kindergarten that issued it still has to reconcile it, so financial access
    is read from the enrollment history — not from `Child.kindergarten_id`,
    which now points somewhere else.
    """
    import datetime as dt

    from apps.children.models import Enrollment

    child = world["bataa"]
    Enrollment.objects.filter(child=child).update(
        status=Enrollment.Status.TRANSFERRED, ended_on=dt.date(2026, 1, 15)
    )
    Enrollment.objects.create(
        kindergarten=world["och"],
        child=child,
        group=world["petal"],
        school_year=world["och_year"],
        started_on=dt.date(2026, 1, 16),
    )
    child.kindergarten = world["och"]
    child.save()
    assert child.kindergarten_id == world["och"].id

    previous = make_admin(
        world["naran"], role=Role.ACCOUNTANT, username="nyagtlan_prev"
    )

    assert can_view_child_finance(previous, child)
