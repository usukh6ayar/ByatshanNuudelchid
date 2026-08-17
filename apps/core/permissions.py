"""The single source of truth for access to child data.

CLAUDE.md §1.1: every view, service and (later) API endpoint that touches a
child's information calls into this module. Nothing here may be duplicated
or reimplemented elsewhere — RFP §21.2, §21.3 and §21.4 are acceptance
criteria, and they all reduce to the same question:

    "May this user see this child?"

Design note (spec section 4.2). The kindergarten is derived from the child's
``Enrollment`` history, not from ``Child.kindergarten_id``. That field changes
when a child transfers, which would silently revoke a teacher's access to
observations they wrote themselves.

**Two axes, deliberately kept apart (added 2026-08-17, нэмэлт.md §13).**

The question above is *developmental* access: observations, assessments,
photographs, health notes. Money asks a different question —

    "May this user see this kindergarten's financial records?"

— and the two must not be merged. An accountant needs every invoice in the
kindergarten and no observation at all; a teacher is the exact opposite
(§13: "Багш санхүүгийн бүрэн мэдээллийг харах эрхгүй байна").

So the finance predicates below are **separate functions**, and `Role.ACCOUNTANT`
never appears in `can_access_child` or `visible_children`. Those two keep the
guarantee they already had, and the list/detail invariant in
`test_permissions.py` continues to hold unchanged for the new role: an
accountant is simply not a user of that axis.

Where a screen shows both kinds of data — the §10 finance tab on a child's
profile — the caller asks *both* predicates and needs both to pass. Composing
two narrow checks is safe; widening one to cover the other is what leaks.
"""

from django.db.models import Q
from django.http import Http404

from apps.accounts.models import Role
from apps.children.models import Child, Enrollment, Guardianship

__all__ = [
    "child_kindergarten_history",
    "is_guardian_of",
    "guardian_link_condition",
    "teacher_link_condition",
    "can_access_child",
    "can_record_for_child",
    "assert_can_access_child",
    "assert_can_record_for_child",
    "visible_kindergartens",
    "visible_children",
    # The finance axis — нэмэлт.md §13. See the module docstring for why
    # these are separate from everything above.
    "FINANCE_ROLES",
    "finance_kindergartens",
    "can_view_finance",
    "can_manage_finance",
    "can_view_child_finance",
    "assert_can_view_child_finance",
]

# Who may see money at all. `TEACHER` is absent on purpose: нэмэлт.md §13
# states a teacher has no right to full financial data, and a role added here
# by accident would hand it to every teacher in every kindergarten.
FINANCE_ROLES = [Role.ACCOUNTANT, Role.ADMIN, Role.SUPERADMIN]

# Who may *change* money, as opposed to reading it. An accountant records
# payments and issues invoices; that is their job. The split exists so that a
# future read-only auditor role has somewhere to go.
FINANCE_WRITE_ROLES = [Role.ACCOUNTANT, Role.ADMIN, Role.SUPERADMIN]


def guardian_link_condition(user) -> Q:
    """The "this user is a current guardian of the child" predicate, as a ``Q``.

    Defined once because it is needed in two shapes that look alike and
    behave differently, and keeping them in step by hand already failed:

    * :func:`is_guardian_of` asks about one child through
      ``Guardianship.objects``, whose default manager hides soft-deleted
      rows (``apps.core.managers.SoftDeleteManager``);
    * :func:`visible_children` and ``children.selectors.guardian_children``
      ask about many children by *joining* to ``guardianships``.

    **A reverse-relation join does not apply the related model's default
    manager.** Django uses the relation's base queryset, so
    ``Q(guardianships__guardian_user=user)`` matched soft-deleted rows while
    the ``objects``-based check next to it did not. A revoked guardian was
    then refused the child's detail page (404, via ``is_guardian_of``) and
    still served the parent home listing that child — measured, not
    inferred: see ``test_a_revoked_guardian_disappears_from_every_list``.

    ``deleted_at__isnull=True`` is therefore explicit here, and every
    guardian predicate in the codebase is built from this one function.
    """
    return Q(
        guardianships__guardian_user=user,
        guardianships__can_view=True,
        guardianships__deleted_at__isnull=True,
    )


def teacher_link_condition(user, *, through: str = "enrollments__group__") -> Q:
    """The "this user holds a live GroupTeacher assignment" predicate, as a ``Q``.

    The GroupTeacher counterpart of :func:`guardian_link_condition`, added
    2026-08-16 for the same defect in the same shape: ``_is_assigned_teacher``
    queried ``GroupTeacher.objects`` and so dropped soft-deleted assignments,
    while :func:`visible_children` and ``tenants.selectors.assignable_groups``
    *joined* to ``teacher_assignments`` and kept them. Unassigning a teacher
    therefore closed the child's detail page and left them in the list.

    ``through`` is the path from the queryset's model to ``Group``, because
    the same tail hangs off two different roots and Django cannot compose a
    ``Q`` across prefixes:

    * ``Child`` → ``enrollments__group__`` (the default) — used by
      :func:`visible_children`;
    * ``Group`` → ``""`` — used by ``assignable_groups``, which gates the
      §6.3 assessment grid and the §5.2 group observation screen.

    Both spellings therefore come from this one definition, so neither can
    drift from the other again. Note ``is_active`` (the membership is
    switched off) and ``deleted_at`` (the assignment was withdrawn) are
    different revocations and both have to be honoured.
    """
    return Q(**{
        f"{through}teacher_assignments__teacher_membership__user": user,
        f"{through}teacher_assignments__teacher_membership__is_active": True,
        f"{through}teacher_assignments__deleted_at__isnull": True,
    })


def child_kindergarten_history(child) -> set[int]:
    """Every kindergarten this child has ever been enrolled at."""
    ids = set(
        Enrollment.objects.filter(child=child).values_list(
            "kindergarten_id", flat=True
        )
    )
    if not ids:
        # A just-registered child has no enrollment yet, so the staff who
        # registered them would otherwise be locked out. This is the ONLY
        # place Child.kindergarten_id influences an authorization decision,
        # and it applies only while the enrollment set is empty — after a
        # transfer there are always enrollments, so the field is never read.
        ids.add(child.kindergarten_id)
    return ids


def is_guardian_of(user, child) -> bool:
    """RFP §3.5. The Guardianship row is itself the authorization.

    Deliberately independent of kindergarten: a transfer does not change
    who the parent is.

    ``deleted_at__isnull=True`` is redundant with ``Guardianship.objects``,
    which already hides soft-deleted rows — it is stated anyway so that all
    three guardian predicates read alike, and so that swapping this to
    ``all_objects`` some day cannot silently widen access. See
    :func:`guardian_link_condition` for the reverse-join half of the rule,
    where the manager does *not* apply and the same omission was a leak.
    """
    return Guardianship.objects.filter(
        child=child, guardian_user=user, can_view=True, deleted_at__isnull=True
    ).exists()


def _is_assigned_teacher(user, child) -> bool:
    """Assigned via GroupTeacher to any group the child has ever been in.

    Assignments are historical rather than overwritten, so a teacher keeps
    access to the records they created in previous school years.

    Asked of ``Child`` through :func:`teacher_link_condition` rather than of
    ``GroupTeacher`` directly, so this and :func:`visible_children` run the
    *same* predicate against the same relation. Their agreement is then
    structural rather than two similar queries maintained side by side —
    which is what failed here and, a day earlier, for guardianships.
    """
    return (
        Child.objects.filter(pk=child.pk)
        .filter(teacher_link_condition(user))
        .exists()
    )


def can_access_child(user, child) -> bool:
    """May this user see this child at all?

    Note this is not the same as "may they see every record about this
    child" — for that, filter with :func:`visible_kindergartens`.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return False

    if is_guardian_of(user, child):
        return True

    if _is_assigned_teacher(user, child):
        return True

    return user.has_membership_in(
        child_kindergarten_history(child),
        roles=[Role.ADMIN, Role.SUPERADMIN],
    )


def can_record_for_child(user, child) -> bool:
    """May this user write a *staff* record about this child?

    Reading and writing are not the same permission. A guardian passes
    ``can_access_child`` — they may read the portfolio and write their own
    half of it (§2.3) — but observations and assessments are the teacher's
    professional record (§5.1, §6.3). A guardian's own contribution goes in
    as ``source=parent`` and is reviewed by a teacher (§5.4); it never
    enters through this door.

    This is deliberately ``can_access_child`` *minus the guardian branch*,
    not "has access, and holds a staff role somewhere". The difference
    matters for a teacher whose own child attends the same kindergarten: the
    weaker rule would let them file a teacher observation about their own
    child while teaching a different group, and that record then reads as
    professional judgement in the portfolio the family receives. The
    authorization has to come from the working relationship with the child,
    which is what §2.2 means by "өөрийн хариуцсан бүлэг".
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return False

    if _is_assigned_teacher(user, child):
        return True

    return user.has_membership_in(
        child_kindergarten_history(child),
        roles=[Role.ADMIN, Role.SUPERADMIN],
    )


def assert_can_access_child(user, child) -> None:
    """Raise 404 when access is denied.

    404 rather than 403 on purpose: a 403 confirms the record exists, which
    is itself a disclosure. RFP §21.4.
    """
    if not can_access_child(user, child):
        raise Http404


def assert_can_record_for_child(user, child) -> None:
    """Raise 404 when this user may not write a staff record — RFP §21.4."""
    if not can_record_for_child(user, child):
        raise Http404


def _admin_kindergarten_ids(user) -> set[int]:
    return set(
        user.memberships.filter(
            is_active=True, role=Role.ADMIN, kindergarten__isnull=False
        ).values_list("kindergarten_id", flat=True)
    )


def _is_superadmin(user) -> bool:
    return user.memberships.filter(is_active=True, role=Role.SUPERADMIN).exists()


def visible_children(user):
    """Every child this user may see, as a queryset.

    The list-level counterpart to :func:`can_access_child`. The two must
    agree: a child that appears in a list but 404s when opened is a bug, and
    the reverse is a disclosure. ``test_permissions.py`` asserts the
    equivalence over every user and child in the fixtures rather than
    trusting that these two functions were kept in step by hand.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return Child.objects.none()

    if _is_superadmin(user):
        return Child.objects.all()

    # Guardian — the Guardianship row is the authorization. Built from the
    # shared predicate so this join and `is_guardian_of` cannot disagree.
    condition = guardian_link_condition(user)

    # Teacher — assigned to any group the child has ever been enrolled in.
    # Same predicate `_is_assigned_teacher` uses, so list and detail agree.
    condition |= teacher_link_condition(user)

    # Admin — any kindergarten in the child's enrollment history, plus the
    # newly-registered case with no enrollment yet (see
    # child_kindergarten_history).
    admin_ids = _admin_kindergarten_ids(user)
    if admin_ids:
        condition |= Q(enrollments__kindergarten_id__in=admin_ids)
        condition |= Q(kindergarten_id__in=admin_ids, enrollments__isnull=True)

    return Child.objects.filter(condition).distinct()


def visible_kindergartens(user, child) -> set[int]:
    """Which kindergartens' records about this child may this user see?

    Access to a child is not access to every record about that child. After
    a transfer, staff at the previous kindergarten keep their own history but
    must not see what is written at the new one. Every tenant-scoped table
    carries ``kindergarten_id`` (CLAUDE.md §3.2), so callers filter with:

        Observation.objects.filter(
            child=child,
            kindergarten_id__in=visible_kindergartens(request.user, child),
        )
    """
    history = child_kindergarten_history(child)

    if is_guardian_of(user, child):
        # Guardians see the child's whole history across kindergartens.
        # RFP §961 treats the portfolio as the family's record.
        return history

    if user.memberships.filter(is_active=True, role=Role.SUPERADMIN).exists():
        return history

    return history & user.kindergarten_ids


# --------------------------------------------------------------- the money axis
# нэмэлт.md §13, §14. Read the module docstring before changing anything here:
# these are separate from the predicates above on purpose, and merging them is
# the mistake this section exists to prevent.


def finance_kindergartens(user) -> set[int]:
    """Every kindergarten whose financial records this user may see.

    The finance counterpart to :func:`visible_children` — one place that
    answers "whose money", so a report, a dashboard tile and an invoice list
    cannot each decide it differently. Financial querysets filter with it:

        Invoice.objects.filter(kindergarten_id__in=finance_kindergartens(user))

    Returns an empty set for a teacher, which is what §13 requires, and for
    a guardian, whose access to their own bill runs through
    :func:`can_view_child_finance` instead.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return set()

    if _is_superadmin(user):
        from apps.tenants.models import Kindergarten

        return set(Kindergarten.objects.values_list("pk", flat=True))

    return set(
        user.memberships.filter(
            is_active=True,
            role__in=FINANCE_ROLES,
            kindergarten__isnull=False,
        ).values_list("kindergarten_id", flat=True)
    )


def can_view_finance(user, kindergarten_id: int | None) -> bool:
    """May this user see this kindergarten's financial records at all?"""
    if kindergarten_id is None:
        return False
    return kindergarten_id in finance_kindergartens(user)


def can_manage_finance(user, kindergarten_id: int | None) -> bool:
    """May this user *change* this kindergarten's financial records?

    Separate from reading because §14 requires that a confirmed financial
    transaction is never simply deleted — the write path goes through a
    reversal, and it should be reachable by fewer people than the read path
    as the roles grow.
    """
    if kindergarten_id is None:
        return False

    if user is None or not user.is_authenticated or not user.is_active:
        return False

    if _is_superadmin(user):
        return True

    return user.memberships.filter(
        is_active=True,
        role__in=FINANCE_WRITE_ROLES,
        kindergarten_id=kindergarten_id,
    ).exists()


def can_view_child_finance(user, child) -> bool:
    """May this user see *this child's* invoices, payments and funding?

    Three kinds of person, and the reasoning differs for each:

    * **The family** — a guardian sees their own child's bill. §7 exists so
      parents can be invoiced and §8 so they can pay, neither of which works
      if they cannot see what they owe.
    * **Finance staff** — an accountant or administrator of a kindergarten the
      child has been enrolled in. Read through the enrollment history for the
      same reason as CLAUDE.md §1.2: a child who transfers in March leaves a
      March invoice behind, and the kindergarten that issued it still has to
      reconcile it.
    * **Everyone else, teachers included** — no. §13 is explicit, and a
      teacher who can see a family's arrears has information about that family
      that the kindergarten never intended to give them.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return False

    if is_guardian_of(user, child):
        return True

    return bool(child_kindergarten_history(child) & finance_kindergartens(user))


def assert_can_view_child_finance(user, child) -> None:
    """Raise 404 when this user may not see the child's money — RFP §21.4.

    404 rather than 403 for the same reason as everywhere else in this
    module: a 403 confirms the record is there.
    """
    if not can_view_child_finance(user, child):
        raise Http404
