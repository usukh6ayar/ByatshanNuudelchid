"""Uploaded files — RFP §4.4, §15, §21.10. Spec sections 6.6 and 7.

Every rule about child photos comes down to one sentence: **a file is never
reachable by URL**. That shapes this table.

* ``storage_key`` is a random UUID path. Guessing another child's photo means
  guessing a UUID, and even then the request still fails the permission
  check — the key is not a secret, it is just not a hint either.
* ``original_name`` exists for display only. It frequently contains the
  child's name, so it never reaches the storage backend.
* ``mime_type`` is detected from the file's *content*. A ``.jpg`` can be an
  executable (CLAUDE.md §1.6, RFP §684).
* ``child`` is what ``can_access_child`` is asked about when the file is
  served. A file with no child — a kindergarten logo, later — is readable by
  anyone in that kindergarten.

``MediaVariant`` (thumbnails, WebP) is Phase 3; the ``<variant>`` segment is
already in the serving URL so links stored in reports do not break when it
arrives.
"""

import uuid

from django.db import models

from apps.core.models import TenantScopedModel


def new_storage_key(extension: str = "") -> str:
    """A random path, sharded two levels deep.

    Flat prefixes make listing slow on S3 and make a stray ``ls`` reveal the
    whole collection. The extension is carried for content-type sniffing by
    the storage backend, never for trusting the file's type.
    """
    token = uuid.uuid4().hex
    return f"{token[:2]}/{token[2:4]}/{token}{extension}"


class MediaFile(TenantScopedModel):
    """One uploaded file — spec section 6.6."""

    class Status(models.TextChoices):
        # Phase 1 uploads land READY: the MIME check and the EXIF strip are
        # millisecond operations done inline (spec section 7). PROCESSING
        # exists for Phase 2, when HEIC conversion moves to Celery.
        UPLOADING = "uploading", "Хуулж байна"
        PROCESSING = "processing", "Боловсруулж байна"
        READY = "ready", "Бэлэн"
        FAILED = "failed", "Амжилтгүй"

    class Purpose(models.TextChoices):
        """What the file is for, so a screen can ask for its own files."""

        CHILD_PHOTO = "child_photo", "Хүүхдийн зураг"
        OBSERVATION = "observation", "Ажиглалтын хавсралт"
        ANNOUNCEMENT = "announcement", "Мэдэгдлийн хавсралт"
        REPORT = "report", "Үүсгэсэн тайлан"
        OTHER = "other", "Бусад"

    # What appears in /media/<public_id>/<variant>/. Separate from
    # ``storage_key`` so the URL does not leak the storage layout, and from
    # ``pk`` so files are not enumerable by counting up from 1.
    public_id = models.UUIDField("нийтийн ID", default=uuid.uuid4,
                                 unique=True, editable=False)

    child = models.ForeignKey(
        "children.Child", null=True, blank=True,
        on_delete=models.CASCADE, related_name="media_files",
        help_text="Хүүхдэд хамаарахгүй файл бол хоосон",
    )
    purpose = models.CharField("зориулалт", max_length=20,
                               choices=Purpose.choices,
                               default=Purpose.OTHER)

    storage_key = models.CharField("хадгалалтын түлхүүр", max_length=200,
                                   unique=True)
    original_name = models.CharField(
        "файлын нэр", max_length=255, blank=True,
        help_text="Зөвхөн харуулах зориулалттай. Хадгалалтад хэрэглэхгүй.",
    )
    mime_type = models.CharField("төрөл", max_length=100)
    size_bytes = models.PositiveIntegerField("хэмжээ (байт)", default=0)
    width = models.PositiveIntegerField("өргөн", null=True, blank=True)
    height = models.PositiveIntegerField("өндөр", null=True, blank=True)
    checksum = models.CharField(
        "sha256", max_length=64, blank=True,
        help_text="Ижил файлыг таних, эвдэрсэн эсэхийг шалгах",
    )

    status = models.CharField("төлөв", max_length=20, choices=Status.choices,
                              default=Status.READY)
    caption = models.CharField("тайлбар", max_length=255, blank=True)
    uploaded_at = models.DateTimeField("хуулсан огноо", auto_now_add=True)

    class Meta:
        verbose_name = "файл"
        verbose_name_plural = "файлууд"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["child", "purpose", "-uploaded_at"]),
            models.Index(fields=["kindergarten", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return self.original_name or self.storage_key

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")


class ObservationMedia(TenantScopedModel):
    """A file attached to an observation — RFP §5.1, spec section 6.3.

    Its own table rather than a foreign key on ``Observation`` because §5.3
    wants several pieces of a child's work in one observation, each with its
    own date and caption, ordered so they can be compared side by side. The
    comparison screen itself is Phase 2; the shape it needs is here.
    """

    observation = models.ForeignKey("observations.Observation",
                                    on_delete=models.CASCADE,
                                    related_name="media_links")
    media_file = models.ForeignKey(MediaFile, on_delete=models.PROTECT,
                                   related_name="observation_links")
    caption = models.CharField("тайлбар", max_length=255, blank=True)
    taken_on = models.DateField("зургийн огноо", null=True, blank=True)
    order = models.PositiveSmallIntegerField("эрэмбэ", default=0)

    class Meta:
        verbose_name = "ажиглалтын хавсралт"
        verbose_name_plural = "ажиглалтын хавсралтууд"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["observation", "media_file"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_media_per_observation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.observation} — {self.media_file}"
