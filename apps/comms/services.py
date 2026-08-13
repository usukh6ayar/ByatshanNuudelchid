"""Announcement writes — RFP §8.1. All rules live here (CLAUDE.md §2.1)."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.services import save_record, soft_delete
from apps.tenants.selectors import assignable_groups

from .models import Announcement, AnnouncementRead, AnnouncementTarget

__all__ = [
    "can_publish_in",
    "save_announcement",
    "set_targets",
    "publish",
    "delete_announcement",
    "mark_read",
]


def can_publish_in(user, kindergarten_id) -> bool:
    """Who may address the families of a kindergarten — RFP §8.1.

    Teachers and directors, not guardians. An announcement carries the
    weight of the kindergarten speaking, which is the whole reason families
    read it.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return False

    return user.has_membership_in(
        [kindergarten_id], roles=[Role.TEACHER, Role.ADMIN, Role.SUPERADMIN]
    )


def _guard(actor, announcement):
    """Only the author, or a director of that kindergarten, may change it.

    A teacher must not edit a colleague's notice: families act on these, and
    "who said this" has to stay answerable.
    """
    if not can_publish_in(actor, announcement.kindergarten_id):
        raise PermissionDenied

    if announcement.created_by_id in (None, actor.pk):
        return

    if not actor.has_membership_in([announcement.kindergarten_id],
                                   roles=[Role.ADMIN, Role.SUPERADMIN]):
        raise PermissionDenied


@transaction.atomic
def save_announcement(*, actor, kindergarten_id, title, body,
                      announcement=None, starts_on=None, ends_on=None,
                      is_important=False, request=None) -> Announcement:
    """RFP §8.1 — create or edit. Always as a draft until published."""
    if not can_publish_in(actor, kindergarten_id):
        raise PermissionDenied

    title = (title or "").strip()
    if not title:
        raise ValidationError("Гарчиг оруулна уу.")
    if not (body or "").strip():
        raise ValidationError("Мэдэгдлийн текст оруулна уу.")
    if starts_on and ends_on and ends_on < starts_on:
        raise ValidationError("Дуусах огноо эхлэх огнооноос хойш байх ёстой.")

    created = announcement is None
    if created:
        announcement = Announcement(kindergarten_id=kindergarten_id,
                                    author=actor)
    else:
        _guard(actor, announcement)

    announcement.title = title[:200]
    announcement.body = body
    announcement.starts_on = starts_on
    announcement.ends_on = ends_on
    announcement.is_important = bool(is_important)

    return save_record(actor=actor, obj=announcement, created=created,
                       request=request)


@transaction.atomic
def set_targets(*, actor, announcement, groups=None, children=None,
                request=None) -> list[AnnouncementTarget]:
    """RFP §8.1 — which groups and which individual children.

    An empty selection means the whole kindergarten, expressed as *no rows*.
    Replacing rather than appending: the form posts the complete selection
    every time, so a group the teacher unticked has to disappear.

    Ids the actor cannot reach are refused rather than dropped. Unlike the
    §6.3 grid, where a stale row is a saved keystroke lost, a mis-addressed
    announcement is a message delivered to the wrong family.
    """
    _guard(actor, announcement)

    allowed_groups = {
        group.pk: group
        for group in assignable_groups(actor).filter(
            kindergarten_id=announcement.kindergarten_id
        )
    }
    allowed_children = {
        child.pk: child
        for child in _addressable_children(actor, announcement)
    }

    wanted_groups = [allowed_groups.get(int(pk)) for pk in (groups or [])]
    wanted_children = [allowed_children.get(int(pk)) for pk in (children or [])]

    if None in wanted_groups or None in wanted_children:
        raise ValidationError("Хүлээн авагчийн сонголт буруу байна.")

    for existing in announcement.targets.all():
        soft_delete(actor=actor, obj=existing, request=request)

    rows = []
    for group in wanted_groups:
        rows.append(AnnouncementTarget(
            kindergarten_id=announcement.kindergarten_id,
            announcement=announcement, group=group,
        ))
    for child in wanted_children:
        rows.append(AnnouncementTarget(
            kindergarten_id=announcement.kindergarten_id,
            announcement=announcement, child=child,
        ))

    return [
        save_record(actor=actor, obj=row, created=True, request=request)
        for row in rows
    ]


def _addressable_children(actor, announcement):
    from apps.core.permissions import visible_children

    return visible_children(actor).filter(
        enrollments__kindergarten_id=announcement.kindergarten_id
    ).distinct()


@transaction.atomic
def publish(*, actor, announcement, request=None) -> Announcement:
    """RFP §8.1 — make it visible to the families it is addressed to."""
    _guard(actor, announcement)

    if announcement.status == Announcement.Status.PUBLISHED:
        return announcement

    announcement.status = Announcement.Status.PUBLISHED
    announcement.published_at = timezone.now()
    if announcement.author_id is None:
        announcement.author = actor

    return save_record(actor=actor, obj=announcement, created=False,
                       request=request)


@transaction.atomic
def delete_announcement(*, actor, announcement, request=None) -> Announcement:
    """RFP §8.1, §3.4 — archived, not removed (CLAUDE.md §3.3)."""
    _guard(actor, announcement)

    for target in announcement.targets.all():
        soft_delete(actor=actor, obj=target, request=request)
    for attachment in announcement.attachments.all():
        soft_delete(actor=actor, obj=attachment, request=request)

    return soft_delete(actor=actor, obj=announcement, request=request)


def mark_read(*, actor, announcement) -> AnnouncementRead | None:
    """RFP §8.1 — "уншсан гэж автоматаар эсвэл товчоор тэмдэглэх".

    Idempotent, and outside the audit trail: an audit row per notice read
    would bury the §971 entries that matter under thousands that do not.
    The read receipt *is* the record here.
    """
    if actor is None or not actor.is_authenticated:
        return None

    entry, _ = AnnouncementRead.objects.get_or_create(
        announcement=announcement, user=actor
    )
    return entry
