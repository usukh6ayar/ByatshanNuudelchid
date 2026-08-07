"""Cross-cutting service helpers — CLAUDE.md §2.1."""

from django.db import transaction
from django.utils import timezone

from .models import AuditLog


def client_ip(request) -> str | None:
    """Best-effort client IP.

    ``X-Forwarded-For`` is only trustworthy behind a proxy that overwrites it.
    Deployment must guarantee that; otherwise a client can forge the header
    and defeat the §3.1 lockout.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def audit(*, action, request=None, actor=None, kindergarten=None, child=None,
          obj=None, **metadata) -> AuditLog:
    """Write an audit row — RFP §15, §971.

    Call this from ``services``, never from a view (CLAUDE.md §8), so the
    record is written in the same transaction as the action it describes.
    """
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
        if actor is not None and not actor.is_authenticated:
            actor = None

    return AuditLog.objects.create(
        action=action,
        actor_user=actor,
        # Kept as text so the trail survives the user being deleted.
        actor_label=str(actor) if actor else metadata.pop("identifier", ""),
        kindergarten=kindergarten,
        child=child,
        object_type=obj._meta.label if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:400]
                    if request is not None else ""),
        metadata=metadata,
    )


@transaction.atomic
def soft_delete(*, actor, obj):
    """Archive a record instead of removing it — RFP §3.4, CLAUDE.md §3.3.

    ``obj.delete()`` raises, so this is the only way a record leaves the
    default queryset.
    """
    obj.deleted_at = timezone.now()
    obj.deleted_by = actor
    obj.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
    return obj


@transaction.atomic
def restore(*, actor, obj):
    """Bring an archived record back — RFP §693."""
    obj.deleted_at = None
    obj.deleted_by = None
    obj.updated_by = actor
    obj.save(update_fields=["deleted_at", "deleted_by", "updated_by", "updated_at"])
    return obj


def stamp(*, actor, obj, created: bool = False):
    """Record authorship — RFP §4.1, §5.1."""
    if created:
        obj.created_by = actor
    obj.updated_by = actor
    return obj
