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
"""

from django.http import Http404

from apps.accounts.models import Role
from apps.children.models import Enrollment, Guardianship
from apps.tenants.models import GroupTeacher

__all__ = [
    "child_kindergarten_history",
    "is_guardian_of",
    "can_access_child",
    "assert_can_access_child",
    "visible_kindergartens",
]


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
    """
    return Guardianship.objects.filter(
        child=child, guardian_user=user, can_view=True
    ).exists()


def _is_assigned_teacher(user, child) -> bool:
    """Assigned via GroupTeacher to any group the child has ever been in.

    Assignments are historical rather than overwritten, so a teacher keeps
    access to the records they created in previous school years.
    """
    return GroupTeacher.objects.filter(
        teacher_membership__user=user,
        teacher_membership__is_active=True,
        group__enrollments__child=child,
    ).exists()


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


def assert_can_access_child(user, child) -> None:
    """Raise 404 when access is denied.

    404 rather than 403 on purpose: a 403 confirms the record exists, which
    is itself a disclosure. RFP §21.4.
    """
    if not can_access_child(user, child):
        raise Http404


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
