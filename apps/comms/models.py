"""Announcements — RFP §8.1. Spec section 6.7.

Phase 1 covers the announcement group. The §8.2 activity feed (posts, likes,
view counts) is Phase 2 — ROADMAP section 8.

The shape that matters here is the *targeting*. §8.1 lists both "хүлээн авах
бүлэг" and "сонгосон хүүхдийн эцэг эх", so one announcement can go to three
groups plus two individual children at once. That cannot be a column, which
is why ``AnnouncementTarget`` is its own table.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class Announcement(TenantScopedModel):
    """One message from a teacher to families — RFP §8.1."""

    class Status(models.TextChoices):
        # A teacher writes over several sittings; a half-written notice must
        # not reach a family. Publishing is the deliberate act.
        DRAFT = "draft", "Ноорог"
        PUBLISHED = "published", "Нийтэлсэн"

    title = models.CharField("гарчиг", max_length=200)
    body = models.TextField("үндсэн текст")

    starts_on = models.DateField(
        "эхлэх огноо", null=True, blank=True,
        help_text="Хоосон бол нийтэлсэн даруйд харагдана",
    )
    ends_on = models.DateField(
        "дуусах огноо", null=True, blank=True,
        help_text="Хоосон бол хугацаагүй",
    )
    is_important = models.BooleanField("чухал", default=False)

    status = models.CharField("төлөв", max_length=20, choices=Status.choices,
                              default=Status.DRAFT)
    published_at = models.DateTimeField("нийтэлсэн огноо", null=True,
                                        blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+",
                               verbose_name="нийтэлсэн багш")

    class Meta:
        verbose_name = "мэдэгдэл"
        verbose_name_plural = "мэдэгдлүүд"
        ordering = ["-is_important", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["kindergarten", "status", "-published_at"]),
        ]

    def __str__(self) -> str:
        return self.title


class AnnouncementTarget(TenantScopedModel):
    """Who one announcement is for — RFP §8.1.

    Exactly one of ``group`` and ``child`` is set on each row; a row with
    neither means the whole kindergarten. Enforced by the constraint below
    rather than by convention, because "everyone" and "nobody" would
    otherwise be the same record and the difference is who reads it.
    """

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE,
                                     related_name="targets")
    group = models.ForeignKey("tenants.Group", null=True, blank=True,
                              on_delete=models.CASCADE, related_name="+")
    child = models.ForeignKey("children.Child", null=True, blank=True,
                              on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = "хүлээн авагч"
        verbose_name_plural = "хүлээн авагчид"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(group__isnull=True) | models.Q(child__isnull=True)
                ),
                name="target_is_group_or_child_not_both",
            ),
        ]
        indexes = [
            models.Index(fields=["group"]),
            models.Index(fields=["child"]),
        ]

    def __str__(self) -> str:
        return str(self.group or self.child or "Бүх цэцэрлэг")


class AnnouncementRead(models.Model):
    """One reader, one announcement — RFP §8.1.

    Not a :class:`BaseModel`: there is nothing to soft-delete or to author.
    Reading a notice is a fact with a timestamp, and un-reading it is not a
    thing a user does.
    """

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE,
                                     related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "уншсан тэмдэглэл"
        verbose_name_plural = "уншсан тэмдэглэлүүд"
        constraints = [
            models.UniqueConstraint(fields=["announcement", "user"],
                                    name="uniq_read_per_user"),
        ]
        indexes = [
            models.Index(fields=["user", "-read_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.announcement}"


class AnnouncementAttachment(TenantScopedModel):
    """§8.1 — "зураг эсвэл файл"."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE,
                                     related_name="attachments")
    media_file = models.ForeignKey("media.MediaFile", on_delete=models.PROTECT,
                                   related_name="+")
    order = models.PositiveSmallIntegerField("эрэмбэ", default=0)

    class Meta:
        verbose_name = "хавсралт"
        verbose_name_plural = "хавсралтууд"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "media_file"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_attachment_per_announcement",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.announcement} — {self.media_file}"
