from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    """Queryset that treats ``deleted_at`` as the deletion marker.

    RFP §3.4 — deleted records are archived, never removed.
    """

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        raise NotImplementedError(
            "Hard delete is forbidden — CLAUDE.md §3.3. "
            "Use apps.core.services.soft_delete()."
        )


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager: hides soft-deleted rows.

    A developer who forgets to filter still gets correct results.
    Use ``all_objects`` when deleted rows are genuinely needed.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Escape hatch: includes soft-deleted rows (restore flows, admin, audit)."""
