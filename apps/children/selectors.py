"""Read queries for children — RFP §11, §17.

Every function starts from ``visible_children``, so a filter can never widen
what a user sees. Filters and ordering come from RFP §11; the indexes they
rely on are listed in spec section 10.2.
"""

import datetime as dt

from django.db.models import Prefetch, Q

from apps.core.permissions import visible_children

from .models import Child, Enrollment, Guardianship

PAGE_SIZE = 25

SORT_FIELDS = {
    "name": ["last_name", "first_name"],
    "-name": ["-last_name", "-first_name"],
    # Age sorts by date of birth inverted: the oldest child has the earliest
    # birth date, so "youngest first" is "-date_of_birth".
    "age": ["-date_of_birth"],
    "-age": ["date_of_birth"],
    "enrolled": ["enrolled_on"],
    "-enrolled": ["-enrolled_on"],
    "updated": ["updated_at"],
    "-updated": ["-updated_at"],
}
DEFAULT_SORT = "name"


def _active_enrollments():
    return Prefetch(
        "enrollments",
        queryset=Enrollment.objects.filter(status=Enrollment.Status.ACTIVE)
        .select_related("group", "school_year"),
        to_attr="active_enrollments",
    )


def _guardianships():
    return Prefetch(
        "guardianships",
        queryset=Guardianship.objects.select_related("guardian_user"),
    )


def child_list(user, *, search="", group=None, school_year=None, status=None,
               sex=None, age=None, sort=DEFAULT_SORT):
    """RFP §11 — the filters and sort keys the children list offers.

    CLAUDE.md §3.5: the prefetches below are not optional. Without them the
    list issues a query per row for the group and again for the guardians.
    """
    # `photo` joins here because the list shows each child's picture beside
    # their name, as the mockup draws it. Left to the template it would be a
    # query per row — the N+1 CLAUDE.md §3.5 forbids, on the screen a teacher
    # opens most.
    qs = visible_children(user).select_related("photo").prefetch_related(
        _active_enrollments(), _guardianships()
    )

    if search:
        qs = qs.filter(
            Q(last_name__icontains=search)
            | Q(first_name__icontains=search)
            | Q(national_id__icontains=search)
        )

    if group is not None:
        qs = qs.filter(enrollments__group=group,
                       enrollments__status=Enrollment.Status.ACTIVE)

    if school_year is not None:
        qs = qs.filter(enrollments__school_year=school_year)

    if status:
        qs = qs.filter(status=status)

    if sex:
        qs = qs.filter(sex=sex)

    if age is not None:
        qs = qs.filter(**_age_range(int(age)))

    return qs.order_by(*SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT]))


def _age_range(age: int) -> dict:
    """Children who are exactly ``age`` years old today.

    Expressed as a date-of-birth window so the query uses the
    ``(kindergarten, date_of_birth)`` index instead of computing an age per
    row (spec section 10.2).
    """
    today = dt.date.today()

    def shift(years: int) -> dt.date:
        try:
            return today.replace(year=today.year - years)
        except ValueError:      # 29 February
            return today.replace(year=today.year - years, day=28)

    return {
        "date_of_birth__gt": shift(age + 1),
        "date_of_birth__lte": shift(age),
    }


def guardian_children(user):
    """The children shown on the parent home screen — RFP §2.3.

    Ordered so the switcher is stable between visits.
    """
    return (
        Child.objects.filter(
            guardianships__guardian_user=user,
            guardianships__can_view=True,
        )
        .select_related("kindergarten", "photo")
        .prefetch_related(_active_enrollments())
        .distinct()
        .order_by("-date_of_birth")
    )


def child_detail(user, child_id) -> Child | None:
    """One child, or ``None`` when this user may not see them.

    Resolving through ``visible_children`` rather than fetching and then
    checking means an unauthorized id is simply not found — the view turns
    that into a 404 rather than a 403 (RFP §21.4).
    """
    return (
        visible_children(user)
        .select_related("kindergarten", "photo")
        .prefetch_related(_active_enrollments(), _guardianships())
        .filter(pk=child_id)
        .first()
    )


def enrollment_history(child):
    """RFP §3.4 — the child's full group history, newest first."""
    return (
        child.enrollments.select_related("group", "school_year", "kindergarten")
        .order_by("-started_on")
    )
