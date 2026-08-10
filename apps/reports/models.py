"""Report generation — RFP §10, §549. Spec section 8.

§549: "тайлан үүсгэх үед систем гацахгүй байх." A child's portfolio can run
to twenty pages with photographs; rendering it inside a request would hold a
web worker for seconds and time out on a phone. So the request creates a
row, returns immediately, and a Celery worker does the work
(CLAUDE.md §6).

Phase 1 ships one report type — the child's portfolio (§10.2's first entry).
The others in §10.2 (term, annual, growth, group, batch) are Phase 2, which
is why ``type`` is a field rather than an assumption.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class ReportJob(TenantScopedModel):
    """One requested PDF — spec section 8."""

    class Type(models.TextChoices):
        CHILD_PORTFOLIO = "child_portfolio", "Хүүхдийн хувийн хавтас"

    class Status(models.TextChoices):
        QUEUED = "queued", "Дараалалд"
        RUNNING = "running", "Боловсруулж байна"
        DONE = "done", "Бэлэн"
        FAILED = "failed", "Амжилтгүй"
        EXPIRED = "expired", "Хугацаа дууссан"

    child = models.ForeignKey("children.Child", null=True, blank=True,
                              on_delete=models.CASCADE,
                              related_name="report_jobs")
    type = models.CharField("төрөл", max_length=32, choices=Type.choices,
                            default=Type.CHILD_PORTFOLIO)
    # §10.1 lets the requester choose which sections go in. Stored as JSON
    # rather than columns because the list grows with every report type, and
    # a report is a record of what was asked for, not a schema.
    params = models.JSONField("тохиргоо", default=dict, blank=True)

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                     blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    status = models.CharField("төлөв", max_length=20, choices=Status.choices,
                              default=Status.QUEUED, db_index=True)
    progress_percent = models.PositiveSmallIntegerField("явц", default=0)

    result_media = models.ForeignKey("media.MediaFile", null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="+")
    file_size = models.PositiveIntegerField("файлын хэмжээ", default=0)
    page_count = models.PositiveSmallIntegerField("хуудасны тоо", default=0)
    error_message = models.TextField("алдааны мэдээлэл", blank=True)

    requested_at = models.DateTimeField("хүсэлт өгсөн", auto_now_add=True)
    started_at = models.DateTimeField("эхэлсэн", null=True, blank=True)
    completed_at = models.DateTimeField("дууссан", null=True, blank=True)
    # Spec section 8: a file holding a child's complete record should not sit
    # in a bucket forever, and regenerating costs one click.
    expires_at = models.DateTimeField("хүчинтэй хугацаа", null=True, blank=True)

    class Meta:
        verbose_name = "тайлангийн хүсэлт"
        verbose_name_plural = "тайлангийн хүсэлтүүд"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["child", "-requested_at"]),
            models.Index(fields=["kindergarten", "status", "-requested_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} — {self.child or self.kindergarten}"

    @property
    def is_finished(self) -> bool:
        return self.status in {self.Status.DONE, self.Status.FAILED,
                               self.Status.EXPIRED}

    @property
    def is_downloadable(self) -> bool:
        return self.status == self.Status.DONE and self.result_media_id
