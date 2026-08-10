"""Observation reads — RFP §5.1, §5.2, §5.4.

Every read filters twice, for the reasons set out in
``apps.assessment.selectors``: ``visible_kindergartens()`` because access to
a child is not access to every record about that child (CLAUDE.md §1.2), and
for a guardian the §5.1 "эцэг эхэд харагдах эсэх" flag on top.
"""

from django.db.models import Prefetch, Q

from apps.core.permissions import is_guardian_of, visible_children, visible_kindergartens

from .models import Observation, ObservationDomain, ObservationType

__all__ = [
    "types_for",
    "parent_observation_type",
    "child_observations",
    "observation_detail",
    "recent_for_teacher",
    "pending_parent_observations",
]

PAGE_SIZE = 20


def types_for(kindergarten):
    """RFP §5.2 — the system list plus this kindergarten's own additions."""
    kindergarten_id = getattr(kindergarten, "pk", kindergarten)
    return ObservationType.objects.filter(
        Q(kindergarten__isnull=True) | Q(kindergarten_id=kindergarten_id),
        is_active=True,
    ).order_by("order", "name")


def parent_observation_type(kindergarten) -> ObservationType | None:
    """The type a guardian's own submission is filed under — RFP §5.2.

    §5.2 lists "Эцэг эхийн оруулсан ажиглалт" as one of the four starting
    types, so a guardian never picks one: the form would be asking them to
    classify their own note against a list written for teachers. A
    kindergarten that defined its own row with this code wins over the
    system one, the same rule the rest of the configuration follows.
    """
    types = types_for(kindergarten).filter(code="parent")
    return types.filter(kindergarten__isnull=False).first() or types.first()


def _domain_links():
    return Prefetch(
        "domain_links",
        queryset=ObservationDomain.objects.select_related("domain", "level"),
    )


def _media_links():
    """The detail screen renders every attachment — CLAUDE.md §3.5."""
    from apps.media.models import ObservationMedia

    return Prefetch(
        "media_links",
        queryset=ObservationMedia.objects.select_related("media_file"),
    )


def _readable(user, child):
    """Every observation about this child this user may read."""
    queryset = Observation.objects.filter(
        child=child,
        kindergarten_id__in=visible_kindergartens(user, child),
    )
    if is_guardian_of(user, child):
        # RFP §2.3, §5.1 — approved and marked visible. A guardian always
        # sees what they submitted themselves, including while it waits for
        # review, or they could not tell whether it saved.
        queryset = queryset.filter(
            Q(visible_to_parents=True,
              review_status=Observation.ReviewStatus.APPROVED)
            | Q(source=Observation.Source.PARENT, created_by=user)
        )
    return queryset


def child_observations(user, child, *, type=None, source=None,
                       date_from=None, date_to=None, domain=None, level=None):
    """RFP §5.1 — one child's observations, newest first.

    The filters are §11's: type, date interval, development domain and
    assessment level. Applied on top of ``_readable``, never instead of it,
    so no combination of them can widen what the user sees.
    """
    queryset = _readable(user, child).select_related(
        "type", "created_by", "enrollment__group"
    ).prefetch_related(_domain_links())

    if type is not None:
        queryset = queryset.filter(type=type)
    if source:
        queryset = queryset.filter(source=source)
    if date_from is not None:
        queryset = queryset.filter(observed_on__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(observed_on__lte=date_to)

    # An observation belongs to several domains (spec section 6.3), so these
    # two join through the link table and need the distinct.
    if domain is not None:
        queryset = queryset.filter(domain_links__domain=domain)
    if level is not None:
        queryset = queryset.filter(domain_links__level=level)
    if domain is not None or level is not None:
        queryset = queryset.distinct()

    return queryset.order_by("-observed_on", "-created_at")


def observation_detail(user, child, observation_id) -> Observation | None:
    """One observation, or ``None`` when this user may not see it.

    Resolved through the same filtered queryset as the list, so an id the
    user cannot reach is simply not found and the view returns 404 rather
    than 403 (RFP §21.4).
    """
    return (
        _readable(user, child)
        .select_related("type", "created_by", "reviewed_by", "enrollment__group")
        .prefetch_related(_domain_links(), _media_links())
        .filter(pk=observation_id)
        .first()
    )


def recent_for_teacher(user, *, limit=10):
    """RFP §12.1 — "сүүлийн ажиглалтууд" on the teacher dashboard.

    Starts from ``visible_children`` so the tile can never widen what its
    owner may see. The dashboard itself is Day 8; this is the query it will
    call.
    """
    return (
        Observation.objects.filter(child__in=visible_children(user))
        .select_related("child", "type", "created_by")
        .order_by("-observed_on", "-created_at")[:limit]
    )


def pending_parent_observations(user):
    """RFP §5.4 — what a teacher still has to review.

    The submission screen itself is Day 7; the queue is defined here so the
    review action and the dashboard tile read the same thing.
    """
    return (
        Observation.objects.filter(
            child__in=visible_children(user),
            source=Observation.Source.PARENT,
            review_status=Observation.ReviewStatus.PENDING,
        )
        .select_related("child", "type", "created_by")
        .order_by("-observed_on")
    )
