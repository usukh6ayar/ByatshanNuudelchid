"""Read queries for people — RFP §2.1, §3.3, §3.5.

Scoped the same way as everything else: an administrator sees the users of
the kindergartens their ``Membership`` names, a superadmin sees all of them.
``administered_kindergartens`` is the single source of that rule
(CLAUDE.md §1.1); this module never re-derives it.
"""

from django.db.models import Prefetch, Q

from apps.tenants.selectors import administered_kindergartens

from .models import Membership, Role, User

__all__ = ["staff_rows", "user_rows", "assignable_memberships"]


def _visible_memberships(user):
    """Every membership row this administrator may look at."""
    return Membership.objects.filter(
        is_active=True,
        kindergarten__in=administered_kindergartens(user),
    )


def staff_rows(user, *, q="", kindergarten=None, role="", active=""):
    """RFP §3.3 — the teacher list a director manages.

    One row per membership rather than per user, because the same person can
    teach at two kindergartens and each posting is what a director assigns,
    edits and ends.
    """
    rows = _visible_memberships(user).select_related(
        "user", "kindergarten", "user__teacher_profile"
    )

    # The default list is staff. Guardians are people too, but they are
    # reached from the child they belong to, not from a directory.
    rows = (rows.filter(role=role) if role
            else rows.filter(role__in=[Role.TEACHER, Role.ADMIN]))

    if kindergarten:
        rows = rows.filter(kindergarten=kindergarten)
    if active == "yes":
        rows = rows.filter(user__is_active=True)
    elif active == "no":
        rows = rows.filter(user__is_active=False)
    if q:
        rows = rows.filter(
            Q(user__last_name__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__phone__icontains=q)
        )

    return rows.prefetch_related(
        Prefetch(
            "group_assignments",
            queryset=Membership.group_assignments.rel.related_model.objects
            .select_related("group"),
        )
    ).order_by("user__last_name", "user__first_name")


def user_rows(user, *, q="", role="", active=""):
    """Every account reachable from this administrator's kindergartens.

    Distinct on the user, since one person may hold several memberships and
    a directory that lists them twice is a directory nobody trusts.
    """
    memberships = _visible_memberships(user)
    if role:
        memberships = memberships.filter(role=role)

    rows = User.objects.filter(
        memberships__in=memberships
    ).prefetch_related(
        Prefetch("memberships",
                 queryset=memberships.select_related("kindergarten"))
    )

    if active == "yes":
        rows = rows.filter(is_active=True)
    elif active == "no":
        rows = rows.filter(is_active=False)
    if q:
        rows = rows.filter(
            Q(last_name__icontains=q) | Q(first_name__icontains=q)
            | Q(username__icontains=q) | Q(email__icontains=q)
            | Q(phone__icontains=q)
        )

    return rows.distinct().order_by("last_name", "first_name")


def assignable_memberships(user, kindergarten):
    """Teachers a director may put in front of a group."""
    return _visible_memberships(user).filter(
        kindergarten=kindergarten, role=Role.TEACHER
    ).select_related("user").order_by("user__last_name")
