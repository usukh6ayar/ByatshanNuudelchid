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


class AuditAction(models.TextChoices):
    """RFP §971 — who viewed, edited or downloaded what, and when."""

    LOGIN = "login", "Нэвтэрсэн"
    LOGIN_FAILED = "login_failed", "Нэвтрэх оролдлого амжилтгүй"
    LOGOUT = "logout", "Гарсан"
    VIEW = "view", "Үзсэн"
    CREATE = "create", "Үүсгэсэн"
    UPDATE = "update", "Зассан"
    DELETE = "delete", "Устгасан"
    RESTORE = "restore", "Сэргээсэн"
    DOWNLOAD = "download", "Татсан"
    EXPORT = "export", "Экспортолсон"
    PERMISSION_CHANGE = "permission_change", "Эрх өөрчилсөн"
    PASSWORD_RESET = "password_reset", "Нууц үг сэргээсэн"
    INVITE = "invite", "Урилга үүсгэсэн"
    ACTIVATE = "activate", "Бүртгэл идэвхжүүлсэн"


class AuditLog(models.Model):
    """Append-only. RFP §15, §16, §971.

    Deliberately not a :class:`BaseModel`: no soft delete, no ``updated_at``,
    no authorship columns. A row that can be edited or removed is not an
    audit record.

    ``view`` is recorded selectively — opening a child's portfolio, viewing a
    report, downloading a file. Not every page load, or the table grows by
    hundreds of thousands of rows a day for no investigative value.
    """

    kindergarten = models.ForeignKey(
        "tenants.Kindergarten", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    actor_role = models.CharField(max_length=20, blank=True)
    actor_label = models.CharField(
        max_length=200, blank=True,
        help_text="Хэрэглэгч устсан ч хэн байсныг мэдэхийн тулд",
    )

    action = models.CharField(max_length=32, choices=AuditAction.choices,
                              db_index=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)

    child = models.ForeignKey(
        "children.Child", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Хүүхдийн мэдээлэлд хандсан бол — §971-ээр шүүх боломж",
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "үйлдлийн бүртгэл"
        verbose_name_plural = "үйлдлийн бүртгэл"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["child", "-created_at"]),
            models.Index(fields=["actor_user", "-created_at"]),
            models.Index(fields=["kindergarten", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_label} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError(
                "AuditLog is append-only — an editable audit record is worthless."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("AuditLog is append-only.")


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
