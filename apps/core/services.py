"""Cross-cutting service helpers — CLAUDE.md §2.1."""

from django.db import transaction
from django.utils import timezone


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
