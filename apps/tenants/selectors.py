"""Read queries for organizational data."""

from apps.accounts.models import Role

from .models import Group, SchoolYear


def assignable_groups(user):
    """Groups this user may register a child into.

    A teacher may only use the groups they are assigned to; an administrator
    any active group in their kindergartens. Restricting the choice here is
    what stops a teacher creating a child in someone else's group — the form
    would otherwise accept any id (RFP §21.2).
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return Group.objects.none()

    memberships = user.memberships.filter(is_active=True)

    if memberships.filter(role=Role.SUPERADMIN).exists():
        qs = Group.objects.all()
    else:
        admin_ids = set(
            memberships.filter(role=Role.ADMIN, kindergarten__isnull=False)
            .values_list("kindergarten_id", flat=True)
        )
        qs = Group.objects.filter(
            teacher_assignments__teacher_membership__user=user,
            teacher_assignments__teacher_membership__is_active=True,
        )
        if admin_ids:
            qs = qs | Group.objects.filter(kindergarten_id__in=admin_ids)

    return (
        qs.filter(status=Group.Status.ACTIVE)
        .select_related("school_year", "kindergarten")
        .distinct()
        .order_by("-school_year__starts_on", "name")
    )


def school_years_for(user):
    """The school years a user may filter by — RFP §11.

    Derived from the kindergartens their groups belong to rather than from
    ``Membership`` directly: a teacher assigned to one group at a
    kindergarten should see that kindergarten's years, and nobody should be
    offered a year belonging to a tenant they have no groups in.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return SchoolYear.objects.none()

    if user.memberships.filter(is_active=True, role=Role.SUPERADMIN).exists():
        return SchoolYear.objects.select_related("kindergarten").order_by(
            "-starts_on"
        )

    kindergarten_ids = set(
        assignable_groups(user).values_list("kindergarten_id", flat=True)
    ) | user.kindergarten_ids

    return (
        SchoolYear.objects.filter(kindergarten_id__in=kindergarten_ids)
        .select_related("kindergarten")
        .order_by("-starts_on")
    )
