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


def administered_kindergartens(user):
    """The kindergartens this user may manage — RFP §2.1.

    A superadmin manages all of them; a director only the ones their
    ``Membership`` names. This is the read side of the same rule
    ``TenantScopedAdmin`` enforces, written once so the new screens and the
    admin site cannot drift (CLAUDE.md §1.1).
    """
    from apps.tenants.models import Kindergarten

    if user is None or not user.is_authenticated or not user.is_active:
        return Kindergarten.objects.none()

    memberships = user.memberships.filter(is_active=True)
    if memberships.filter(role=Role.SUPERADMIN).exists():
        return Kindergarten.objects.all().order_by("name")

    ids = set(
        memberships.filter(role=Role.ADMIN, kindergarten__isnull=False)
        .values_list("kindergarten_id", flat=True)
    )
    return Kindergarten.objects.filter(pk__in=ids).order_by("name")


def kindergarten_rows(user, *, q="", status=""):
    """The administrator's kindergarten list — RFP §3.2.

    Counts come from one annotated query rather than a property per row:
    the list is small, but "children per kindergarten" in a template loop is
    the N+1 CLAUDE.md §3.5 forbids and the habit is what matters.
    """
    from django.db.models import (
        Count,
        IntegerField,
        OuterRef,
        Q,
        Subquery,
    )

    from apps.children.models import Child

    rows = administered_kindergartens(user)
    if q:
        rows = rows.filter(Q(name__icontains=q) | Q(address__icontains=q))
    if status == "active":
        rows = rows.filter(is_active=True)
    elif status == "inactive":
        rows = rows.filter(is_active=False)

    # ``TenantScopedModel.kindergarten`` uses related_name="+", so there is
    # no reverse accessor to aggregate over — deliberate, since a reverse
    # manager that ignores soft deletes is a trap. Subqueries instead.
    return rows.annotate(
        group_count=Subquery(
            Group.objects.filter(kindergarten=OuterRef("pk"))
            .values("kindergarten")
            .annotate(n=Count("pk"))
            .values("n")[:1],
            output_field=IntegerField(),
        ),
        child_count=Subquery(
            Child.objects.filter(kindergarten=OuterRef("pk"),
                                 status=Child.Status.ACTIVE)
            .values("kindergarten")
            .annotate(n=Count("pk"))
            .values("n")[:1],
            output_field=IntegerField(),
        ),
    )


def group_rows(user, *, q="", kindergarten=None, school_year=None, status=""):
    """The administrator's group list — RFP §3.2's group management."""
    from django.db.models import Count, Q

    from apps.children.models import Enrollment

    rows = Group.objects.filter(
        kindergarten__in=administered_kindergartens(user)
    ).select_related("kindergarten", "school_year")

    if q:
        rows = rows.filter(name__icontains=q)
    if kindergarten:
        rows = rows.filter(kindergarten=kindergarten)
    if school_year:
        rows = rows.filter(school_year=school_year)
    if status:
        rows = rows.filter(status=status)

    return rows.annotate(
        child_count=Count(
            "enrollments", distinct=True,
            filter=Q(enrollments__status=Enrollment.Status.ACTIVE,
                     enrollments__deleted_at__isnull=True),
        ),
    ).order_by("-school_year__starts_on", "name")


def routine_for(group):
    """A group's day, in order — Үлгэрчилсэн дүрэм §7.8."""
    from .models import RoutineSlot

    return RoutineSlot.objects.filter(group=group).order_by("starts_at")


def routine_now(group, moment=None):
    """The block a group is in, or ``None``.

    ``None`` is a real answer, not a missing one: before 08:30, after 18:00,
    and in the gaps the regulation leaves between blocks. A screen that
    invents a "current" activity for 07:00 is lying to a teacher who can
    see the room is empty.
    """
    from django.utils import timezone

    moment = moment or timezone.localtime().time()
    for slot in routine_for(group):
        if slot.covers(moment):
            return slot
    return None
