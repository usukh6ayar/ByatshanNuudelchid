"""Base models every domain model inherits — CLAUDE.md §3.1."""

from django.conf import settings
from django.db import models

from .managers import AllObjectsManager, SoftDeleteManager


class BaseModel(models.Model):
    """Timestamps, authorship and soft delete.

    RFP §4.1 and §5.1 require every record to carry who created or changed it.
    RFP §3.4 requires deletion to be reversible.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, *args, **kwargs):
        raise NotImplementedError(
            "Hard delete is forbidden — CLAUDE.md §3.3. "
            "Use apps.core.services.soft_delete()."
        )

    def hard_delete(self, *args, **kwargs):
        """Real deletion. Only for tests and data-repair management commands."""
        return models.Model.delete(self, *args, **kwargs)


class TenantScopedModel(BaseModel):
    """Adds the denormalized kindergarten pointer — CLAUDE.md §3.2.

    RFP §3.2 requires one kindergarten's data to be invisible to another's
    users. Carrying ``kindergarten`` on every row means a single filter
    enforces that, instead of traversing three or four relations per table
    and eventually forgetting one.
    """

    kindergarten = models.ForeignKey(
        "tenants.Kindergarten",
        on_delete=models.PROTECT,
        related_name="+",
        db_index=True,
    )

    class Meta:
        abstract = True
