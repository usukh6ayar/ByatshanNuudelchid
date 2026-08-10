"""Announcement reads — RFP §8.1.

The whole difficulty is one question: **which announcements is this family
entitled to see?** §8.1 allows an announcement to be aimed at groups, at
individual children, or at nobody in particular (the whole kindergarten), so
the answer is a union rather than a filter.

It is written once, here. A second copy on the dashboard would eventually
disagree with this one, and the disagreement would be a family reading a
notice about someone else's child.
"""

import datetime as dt

from django.db.models import Exists, OuterRef, Q

from apps.accounts.models import Role
from apps.children.models import Enrollment
from apps.core.permissions import visible_children

from .models import Announcement, AnnouncementRead

__all__ = [
    "for_guardian",
    "for_staff",
    "unread_count",
    "readers",
    "announcement_detail",
]

PAGE_SIZE = 20


def _live(queryset, on: dt.date | None = None):
    """Published, and inside its own date window — RFP §8.1.

    An announcement with no dates runs from the moment it is published until
    someone deletes it; that is the common case and must not need two blank
    fields to be filled in.
    """
    on = on or dt.date.today()
    return queryset.filter(
        Q(status=Announcement.Status.PUBLISHED)
        & (Q(starts_on__isnull=True) | Q(starts_on__lte=on))
        & (Q(ends_on__isnull=True) | Q(ends_on__gte=on))
    )


def for_guardian(user, on: dt.date | None = None):
    """Everything a guardian may read — RFP §2.3, §8.1.

    Starts from ``visible_children``, so a family can never be reached by an
    announcement about a child they are not connected to, whatever targeting
    the author chose.
    """
    children = visible_children(user)
    child_ids = list(children.values_list("pk", flat=True))
    if not child_ids:
        return Announcement.objects.none()

    group_ids = list(
        Enrollment.objects.filter(
            child_id__in=child_ids, status=Enrollment.Status.ACTIVE
        ).values_list("group_id", flat=True)
    )
    kindergarten_ids = list(
        Enrollment.objects.filter(child_id__in=child_ids)
        .values_list("kindergarten_id", flat=True)
        .distinct()
    )

    reaches_me = (
        Q(targets__group_id__in=group_ids)
        | Q(targets__child_id__in=child_ids)
        # No targets at all means the whole kindergarten. Expressed as
        # "has no target rows" rather than a nullable flag, so adding a
        # target later cannot leave a stale "everyone" marker behind.
        | Q(targets__isnull=True)
    )

    return (
        _live(Announcement.objects.filter(kindergarten_id__in=kindergarten_ids),
              on)
        .filter(reaches_me)
        .select_related("author", "kindergarten")
        .distinct()
        .order_by("-is_important", "-published_at", "-created_at")
    )


def for_staff(user):
    """What a teacher or director sees on the announcements screen.

    Published notices from anyone in their kindergartens, plus their own
    drafts. Another teacher's unfinished draft is not theirs to read: §8.1
    makes publishing the deliberate act, and a draft is by definition not
    yet what its author means to say.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return Announcement.objects.none()

    memberships = user.memberships.filter(is_active=True)
    if memberships.filter(role=Role.SUPERADMIN).exists():
        queryset = Announcement.objects.all()
    else:
        queryset = Announcement.objects.filter(
            kindergarten_id__in=user.kindergarten_ids
        )

    return (
        queryset.filter(
            Q(status=Announcement.Status.PUBLISHED) | Q(created_by=user)
        )
        .select_related("author", "kindergarten")
        .prefetch_related("targets__group", "targets__child")
        .distinct()
        .order_by("-is_important", "-published_at", "-created_at")
    )


def with_read_flag(queryset, user):
    """Annotate ``is_read`` so the list does not query once per row.

    CLAUDE.md §3.5. The unread badge is the reason a parent opens this
    screen, so it is on every row.
    """
    return queryset.annotate(
        is_read=Exists(
            AnnouncementRead.objects.filter(announcement=OuterRef("pk"),
                                            user=user)
        )
    )


def unread_count(user, on: dt.date | None = None) -> int:
    """RFP §8.1 — "шинэ мэдэгдлийн тоог харах"."""
    return (
        for_guardian(user, on)
        .exclude(reads__user=user)
        .distinct()
        .count()
    )


def announcement_detail(user, announcement_id) -> Announcement | None:
    """One announcement, or ``None`` when this user may not read it.

    Resolved through the same querysets as the lists, so an id outside the
    user's reach is not found and the view answers 404 (RFP §21.4).
    """
    for queryset in (for_staff(user), for_guardian(user)):
        found = queryset.filter(pk=announcement_id).first()
        if found is not None:
            return found
    return None


def readers(announcement):
    """RFP §8.1 — "хэн уншсаныг харах"."""
    return (
        AnnouncementRead.objects.filter(announcement=announcement)
        .select_related("user")
        .order_by("-read_at")
    )
