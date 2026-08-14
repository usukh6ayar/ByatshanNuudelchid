"""Dashboard figures — RFP §12.1, §12.2. Spec section 10.3.

Two dashboards with two different cost profiles, and the spec is explicit
about the difference:

* **§12.1, the teacher's** — one group, roughly twenty-five children. Direct
  queries. Caching it would mean a teacher recording an observation and not
  seeing the count move, which is worse than the query.
* **§12.2, the administrator's** — kindergarten- or system-wide. Computed by
  a Celery beat task and read from the cache (CLAUDE.md §6), because it
  counts across every table and nobody needs it to the second.

Every figure starts from ``visible_children`` or the user's own memberships,
so a dashboard tile can never become a way to count other people's children.
"""

import datetime as dt

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.assessment.models import Assessment, AssessmentLevel
from apps.assessment.selectors import current_term, domains_for
from apps.children.models import Child, Enrollment
from apps.comms.models import Announcement
from apps.core.models import AuditAction, AuditLog
from apps.core.permissions import visible_children
from apps.media.models import MediaFile
from apps.observations.models import Observation
from apps.reports.models import ReportJob
from apps.tenants.models import Group, Kindergarten
from apps.tenants.selectors import assignable_groups

__all__ = ["teacher_dashboard", "admin_dashboard", "compute_admin_dashboard"]

ADMIN_CACHE_KEY = "dashboard:admin:v1"
ADMIN_CACHE_TTL = 60 * 30      # the beat task refreshes every 15 minutes
RECENT_LIMIT = 8


# ---------------------------------------------------------------- §12.1


def teacher_dashboard(user, *, today: dt.date | None = None) -> dict:
    """Everything on the teacher's screen — RFP §12.1."""
    today = today or timezone.localdate()
    # `photo` is selected here because the §12.1 screen shows a child's
    # picture beside their name in both the birthday strip and the missing-
    # assessment list. Without it each name costs its own query, which is
    # exactly the N+1 CLAUDE.md §3.5 forbids — and on a dashboard it would be
    # twenty-five of them.
    children = visible_children(user).select_related("photo")
    child_ids = list(children.values_list("pk", flat=True))

    groups = list(assignable_groups(user))
    term = _current_term_for(groups, today)

    return {
        "child_count": len(child_ids),
        "groups": groups,
        "term": term,
        "band_track": _band_track(groups),
        "birthdays_today": _birthdays_today(children, today),
        "recent_observations": _recent_observations(child_ids),
        "recent_parent_notes": _recent_parent_notes(child_ids),
        "pending_reviews": _pending_review_count(child_ids),
        "new_announcements": _recent_announcements(user),
        "assessment_progress": _assessment_progress(child_ids, term),
        "missing_assessments": _children_missing_assessments(
            children, child_ids, term
        ),
        "domain_averages": _domain_averages(child_ids, term),
    }


def _current_term_for(groups, today):
    """The term the teacher is working in, if their year has one configured."""
    for group in groups:
        found = current_term(group.school_year, today)
        if found is not None:
            return found
    return None


def _band_track(groups):
    """The four kindergarten bands and the year this cohort meets each one.

    Mongolian kindergartens run Бага (2 нас), Дунд (3), Ахлах (4) and
    Бэлтгэл (5) — one band per year of age, the same four years RFP §4.3
    gives a page each. A cohort moves up one band every September, so
    knowing the band a group is in this year fixes every other year by
    counting.

    The years are projected, not stored: only the current one is a
    ``SchoolYear`` row. That is honest for a track whose whole job is to
    show where a group sits in a four-year run — the kindergarten has not
    created 2028-2029 yet, and should not have to for this to draw.

    Returns ``[]`` when the group has no band set, because guessing it from
    ``age_category`` free text ("3-4 нас", "холимог") would be a guess shown
    as a fact.
    """
    group = next((g for g in groups if g.age_band), None)
    if group is None:
        return []

    bands = list(Group.AgeBand)
    here = bands.index(Group.AgeBand(group.age_band))
    # "2025-2026" → 2025. The year row is the anchor; the rest are offsets.
    start = group.school_year.starts_on.year

    track = []
    for index, band in enumerate(bands):
        first = start + (index - here)
        track.append({
            "band": band,
            "label": band.label,
            "years": f"{first}–{first + 1}",
            "state": ("current" if index == here
                      else "done" if index < here
                      else "ahead"),
        })
    return track


def _birthdays_today(children, today):
    """RFP §12.1 — "тухайн өдөр төрсөн өдөртэй хүүхэд".

    Matched on month and day so it does not depend on the year, and 29
    February is shown on the 28th in a common year rather than skipped for
    three years running.
    """
    queryset = children.filter(date_of_birth__month=today.month,
                               date_of_birth__day=today.day)

    if today.month == 2 and today.day == 28:
        try:
            dt.date(today.year, 2, 29)
        except ValueError:
            queryset = children.filter(
                Q(date_of_birth__month=2, date_of_birth__day=28)
                | Q(date_of_birth__month=2, date_of_birth__day=29)
            )

    return list(queryset.order_by("last_name", "first_name"))


def _recent_observations(child_ids):
    return list(
        Observation.objects.filter(child_id__in=child_ids)
        .select_related("child", "type", "created_by")
        .order_by("-observed_on", "-created_at")[:RECENT_LIMIT]
    )


def _recent_parent_notes(child_ids):
    """RFP §12.1 — "сүүлийн үеийн эцэг эхийн оруулсан мэдээлэл"."""
    return list(
        Observation.objects.filter(
            child_id__in=child_ids, source=Observation.Source.PARENT
        )
        .select_related("child", "created_by")
        .order_by("-created_at")[:RECENT_LIMIT]
    )


def _pending_review_count(child_ids) -> int:
    return Observation.objects.filter(
        child_id__in=child_ids,
        source=Observation.Source.PARENT,
        review_status=Observation.ReviewStatus.PENDING,
    ).count()


def _recent_announcements(user):
    from apps.comms.selectors import for_staff

    return list(for_staff(user)[:5])


def _assessment_progress(child_ids, term) -> dict:
    """RFP §12.1 — "тухайн улирлын үнэлгээний явц".

    Expressed as assessments recorded out of the number expected: every
    child against every domain. Any other denominator makes the percentage
    mean nothing.
    """
    if term is None or not child_ids:
        return {"done": 0, "expected": 0, "percent": 0}

    domain_count = domains_for(term.kindergarten_id).count()
    expected = len(child_ids) * domain_count
    done = Assessment.objects.filter(child_id__in=child_ids,
                                     term=term).count()

    return {
        "done": done,
        "expected": expected,
        "percent": round(done * 100 / expected) if expected else 0,
    }


def _children_missing_assessments(children, child_ids, term):
    """RFP §12.1 — "үнэлгээ нь дутуу хүүхдүүд".

    One query with an annotation rather than a loop: the point of the tile
    is to be glanced at, and spec section 10.3 names this as the query to
    get right.
    """
    if term is None or not child_ids:
        return []

    domain_count = domains_for(term.kindergarten_id).count()
    if not domain_count:
        return []

    return list(
        children.annotate(
            done=Count("assessments",
                       filter=Q(assessments__term=term), distinct=True)
        )
        .filter(done__lt=domain_count)
        .order_by("last_name", "first_name")[:20]
    )


def _domain_averages(child_ids, term):
    """RFP §12.1, §12.3 — "хөгжлийн чиглэл тус бүрийн дундаж".

    Averaged over ``AssessmentLevel.value``, which is why that column stays
    numeric even when an administrator renames the level (§6.2).
    """
    if term is None or not child_ids:
        return []

    rows = (
        Assessment.objects.filter(child_id__in=child_ids, term=term)
        .values("domain__name", "domain__color")
        .annotate(average=Avg("level__value"), counted=Count("id"))
        .order_by("domain__order", "domain__name")
    )
    # The mockups draw each domain as a filled bar, which needs a proportion
    # rather than a mean. The top of the scale is whatever the administrator
    # configured (§6.2) — assuming 4 here would silently mis-draw every bar
    # for a kindergarten that renamed its scale to three levels or five.
    scale_ids = set(
        Assessment.objects.filter(child_id__in=child_ids, term=term)
        .values_list("level__scale_id", flat=True)
    )
    top = AssessmentLevel.objects.filter(scale_id__in=scale_ids).aggregate(
        top=Max("value")
    )["top"] or 0

    return [
        {
            "name": row["domain__name"],
            "color": row["domain__color"],
            "average": round(row["average"], 1) if row["average"] else 0,
            "percent": (
                round(row["average"] / top * 100) if row["average"] and top else 0
            ),
            "count": row["counted"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------- §12.2


def admin_dashboard(kindergarten_ids=None, *, refresh=False) -> dict:
    """RFP §12.2, read from the cache — CLAUDE.md §6.

    Computed inline on a cache miss rather than shown empty: the first
    administrator to log in after a deploy should see numbers, not a blank
    screen waiting for the next beat tick.
    """
    key = _admin_key(kindergarten_ids)
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    figures = compute_admin_dashboard(kindergarten_ids)
    cache.set(key, figures, ADMIN_CACHE_TTL)
    return figures


def _admin_key(kindergarten_ids) -> str:
    if not kindergarten_ids:
        return f"{ADMIN_CACHE_KEY}:all"
    return f"{ADMIN_CACHE_KEY}:{'-'.join(str(i) for i in sorted(kindergarten_ids))}"


def compute_admin_dashboard(kindergarten_ids=None) -> dict:
    """The actual counting. Called by the beat task and on a cache miss."""
    scoped = bool(kindergarten_ids)
    kindergartens = Kindergarten.objects.all()
    groups = Group.objects.all()
    children = Child.objects.all()
    memberships_filter = {}

    if scoped:
        kindergartens = kindergartens.filter(id__in=kindergarten_ids)
        groups = groups.filter(kindergarten_id__in=kindergarten_ids)
        children = children.filter(
            enrollments__kindergarten_id__in=kindergarten_ids
        ).distinct()
        memberships_filter = {"memberships__kindergarten_id__in": kindergarten_ids}

    def staff(role):
        return User.objects.filter(
            is_active=True, memberships__is_active=True,
            memberships__role=role, **memberships_filter,
        ).distinct().count()

    media = MediaFile.objects.all()
    reports = ReportJob.objects.all()
    audit = AuditLog.objects.all()
    if scoped:
        media = media.filter(kindergarten_id__in=kindergarten_ids)
        reports = reports.filter(kindergarten_id__in=kindergarten_ids)
        audit = audit.filter(kindergarten_id__in=kindergarten_ids)

    since = timezone.now() - dt.timedelta(days=7)

    return {
        "kindergartens": kindergartens.count(),
        "groups": groups.count(),
        "teachers": staff(Role.TEACHER),
        "children": children.count(),
        "active_guardians": staff(Role.GUARDIAN),
        "observations": _scoped_count(Observation, kindergarten_ids),
        "assessments": _scoped_count(Assessment, kindergarten_ids),
        "announcements": _scoped_count(Announcement, kindergarten_ids),
        "enrollments": Enrollment.objects.filter(
            **({"kindergarten_id__in": kindergarten_ids} if scoped else {})
        ).count(),

        # §12.2 — "хадгалалтын хэмжээ"
        "storage_bytes": sum(media.values_list("size_bytes", flat=True)),
        "file_count": media.count(),

        # §12.2 — "тайлангийн статистик"
        "reports_total": reports.count(),
        "reports_failed": reports.filter(
            status=ReportJob.Status.FAILED
        ).count(),

        # §12.2 — "алдаа болон сэжигтэй үйлдлийн мэдээлэл". Failed logins are
        # the signal worth surfacing: §3.1 already throttles them, and a
        # spike is what an administrator needs to notice.
        "failed_logins_7d": AuditLog.objects.filter(
            action=AuditAction.LOGIN_FAILED, created_at__gte=since
        ).count(),
        "logins_7d": audit.filter(action=AuditAction.LOGIN,
                                  created_at__gte=since).count(),
        "computed_at": timezone.now(),
    }


def _scoped_count(model, kindergarten_ids) -> int:
    queryset = model.objects.all()
    if kindergarten_ids:
        queryset = queryset.filter(kindergarten_id__in=kindergarten_ids)
    return queryset.count()
