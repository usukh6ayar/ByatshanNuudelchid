"""Upload and file access — RFP §4.4, §15, §684, §21.10. Spec section 7.

Phase 1 does two of the pipeline's five steps, and does them inline because
both are millisecond operations on a single photo:

    1. verify the real MIME type      §15, §684
    2. strip EXIF, including GPS      ★

Steps 3–5 (HEIC conversion, thumbnails, WebP) are Phase 2 and Phase 3 and
belong in Celery; at that point an upload returns with ``status=processing``
instead of ``ready``.

★ Stripping EXIF is not asked for in the RFP. It is done anyway, from the
first upload: a phone embeds GPS coordinates in every photo, so a leaked
child photo would otherwise carry the child's home address. It cannot be
added later — by then the coordinates are already in the bucket.
"""

import hashlib
import io

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.core.models import AuditAction
from apps.core.permissions import can_access_child, can_record_for_child
from apps.core.services import audit, save_record, soft_delete

from .models import MediaFile, ObservationMedia, new_storage_key

__all__ = [
    "upload_image",
    "store_generated_file",
    "attach_to_observation",
    "set_child_photo",
    "delete_media",
    "file_url",
    "read_bytes",
]

# Spec section 7: Phase 1 accepts JPEG and PNG. HEIC is recognised so an
# iPhone upload gets a sentence rather than a broken image — the conversion
# is Phase 2.
ACCEPTED = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
}
HEIC_TYPES = {"image/heic", "image/heif"}

# A 25 MB file can still decode to gigabytes of pixels. Pillow warns above
# its own threshold; this refuses outright, because the only images that
# reach it are photographs.
MAX_PIXELS = 50_000_000


def _detect_mime(payload: bytes) -> str:
    """The real type, read from the content — CLAUDE.md §1.6, RFP §684.

    Never the extension and never ``UploadedFile.content_type``: both are
    supplied by the client, and a ``.jpg`` can be an executable.
    """
    import magic

    return magic.from_buffer(payload[:2048], mime=True)


def _clean_image(payload: bytes, mime: str) -> tuple[bytes, int, int, str]:
    """Re-encode the image, dropping every metadata block.

    Pillow does not carry EXIF across a re-encode unless it is passed
    explicitly, so decoding and re-saving is the whole of the strip — and it
    also discards any other chunk a file might be smuggling. The colour
    profile is the one thing kept: without it, photographs shift visibly.
    """
    from PIL import Image, UnidentifiedImageError

    format, extension = ACCEPTED[mime]

    try:
        image = Image.open(io.BytesIO(payload))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(
            "Зургийг уншиж чадсангүй. Файл эвдэрсэн байж магадгүй."
        ) from exc

    if image.width * image.height > MAX_PIXELS:
        raise ValidationError("Зургийн хэмжээ хэт том байна.")

    buffer = io.BytesIO()
    options = {}
    if icc := image.info.get("icc_profile"):
        options["icc_profile"] = icc
    if format == "JPEG":
        options |= {"quality": 90, "optimize": True}
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

    image.save(buffer, format=format, **options)
    return buffer.getvalue(), image.width, image.height, extension


def _guard_upload(actor, child, purpose):
    """Who may attach a file to whose record.

    A guardian may add to their own child's portfolio (§2.3 lists photos
    among their capabilities). An observation attachment is part of the
    teacher's record, so it follows the same rule the observation does.
    """
    if child is None:
        raise ValidationError("Файлыг хүүхэдтэй холбох шаардлагатай.")

    if purpose == MediaFile.Purpose.OBSERVATION:
        if not can_record_for_child(actor, child):
            raise PermissionDenied
    elif not can_access_child(actor, child):
        raise PermissionDenied


@transaction.atomic
def upload_image(*, actor, child, upload, purpose=MediaFile.Purpose.OTHER,
                 caption="", kindergarten_id=None, request=None) -> MediaFile:
    """Store one image — RFP §4.4, §15, §684.

    ``upload`` is a Django ``UploadedFile``. Nothing it claims about itself
    is believed: not the name, not the content type, not the extension.
    """
    _guard_upload(actor, child, purpose)

    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > limit:
        raise ValidationError(
            f"Файл {settings.MAX_UPLOAD_SIZE_MB} МБ-аас бага байх ёстой."
        )
    if upload.size == 0:
        raise ValidationError("Файл хоосон байна.")

    payload = upload.read()
    mime = _detect_mime(payload)

    if mime in HEIC_TYPES:
        # Spec section 7: the conversion is Phase 2. Until then, say so.
        raise ValidationError(
            "HEIC зургийг одоогоор дэмжихгүй байна. "
            "Утсандаа JPEG хэлбэрээр хадгалаад дахин оруулна уу."
        )
    if mime not in ACCEPTED:
        raise ValidationError("Зөвхөн JPEG болон PNG зураг оруулна уу.")

    cleaned, width, height, extension = _clean_image(payload, mime)

    # The kindergarten comes from the child's *current* enrollment, via the
    # same helper every other record uses, so a file written after a
    # transfer lands in the same tenant the observation would.
    if kindergarten_id is None:
        from apps.assessment.services import assert_writable, recording_enrollment

        enrollment = recording_enrollment(child)
        assert_writable(actor, child, enrollment)
        kindergarten_id = enrollment.kindergarten_id

    storage_key = new_storage_key(extension)
    default_storage.save(storage_key, ContentFile(cleaned))

    media = MediaFile(
        kindergarten_id=kindergarten_id,
        child=child,
        purpose=purpose,
        storage_key=storage_key,
        # Kept for display only, and truncated: the name often contains the
        # child's own name and is attacker-controlled.
        original_name=(upload.name or "")[:255],
        mime_type=mime,
        size_bytes=len(cleaned),
        width=width,
        height=height,
        checksum=hashlib.sha256(cleaned).hexdigest(),
        caption=caption[:255],
        status=MediaFile.Status.READY,
    )
    return save_record(actor=actor, obj=media, created=True, request=request)


@transaction.atomic
def store_generated_file(*, actor, child, payload: bytes, mime: str,
                         filename: str, kindergarten_id,
                         purpose=MediaFile.Purpose.REPORT,
                         request=None) -> MediaFile:
    """Store bytes the system produced itself — RFP §10, spec section 8.

    Separate from :func:`upload_image` because the two have different
    threats. An upload is hostile until proved otherwise: its type is
    sniffed, its pixels are re-encoded, its metadata is thrown away. A
    rendered PDF came from our own template, so none of that applies — but
    it lands in the same table and behind the same permission check, because
    a child's portfolio as a PDF is the most sensitive file in the system.

    No permission check here: the caller is a Celery task acting on a job
    whose request was already authorized. Adding one would mean deciding
    what a background worker's "actor" may do, which is a question with no
    good answer.
    """
    if not payload:
        raise ValidationError("Хоосон файл үүссэн байна.")

    extension = {"application/pdf": ".pdf"}.get(mime, "")
    storage_key = new_storage_key(extension)
    default_storage.save(storage_key, ContentFile(payload))

    media = MediaFile(
        kindergarten_id=kindergarten_id,
        child=child,
        purpose=purpose,
        storage_key=storage_key,
        original_name=filename[:255],
        mime_type=mime,
        size_bytes=len(payload),
        checksum=hashlib.sha256(payload).hexdigest(),
        status=MediaFile.Status.READY,
    )
    return save_record(actor=actor, obj=media, created=True, request=request)


@transaction.atomic
def attach_to_observation(*, actor, observation, upload, caption="",
                          taken_on=None, request=None) -> ObservationMedia:
    """RFP §5.1 — "нотлох зураг", §5.3 — a child's work over time."""
    from apps.observations.services import assert_own_record

    assert_own_record(actor, observation)
    if not can_record_for_child(actor, observation.child):
        raise PermissionDenied

    media = upload_image(
        actor=actor, child=observation.child, upload=upload,
        purpose=MediaFile.Purpose.OBSERVATION, caption=caption,
        kindergarten_id=observation.kindergarten_id, request=request,
    )

    link = ObservationMedia(
        kindergarten_id=observation.kindergarten_id,
        observation=observation,
        media_file=media,
        caption=caption[:255],
        taken_on=taken_on or observation.observed_on,
        order=observation.media_links.count(),
    )
    return save_record(actor=actor, obj=link, created=True, request=request)


@transaction.atomic
def set_child_photo(*, actor, child, upload, request=None) -> MediaFile:
    """RFP §3.4 — the child's profile photo.

    The previous photo is archived rather than replaced in place, so the
    portfolio keeps the picture that was current in each year.
    """
    media = upload_image(
        actor=actor, child=child, upload=upload,
        purpose=MediaFile.Purpose.CHILD_PHOTO, request=request,
    )

    child.photo = media
    save_record(actor=actor, obj=child, created=False, request=request)
    return media


@transaction.atomic
def delete_media(*, actor, media, request=None) -> MediaFile:
    """Archive the row — RFP §3.4, CLAUDE.md §3.3.

    The object itself stays in the bucket. Removing it would break a PDF
    already generated from it, and §16's retention rules decide when bytes
    actually go, not a click in the interface.
    """
    if media.child is not None and not can_record_for_child(actor, media.child):
        raise PermissionDenied

    for link in media.observation_links.all():
        soft_delete(actor=actor, obj=link, request=request)

    # A child pointing at an archived photo would render a broken image on
    # every screen. Cleared here rather than in the view, so the admin and a
    # later API get the same behaviour (CLAUDE.md §2.1).
    child = media.child
    if child is not None and child.photo_id == media.pk:
        child.photo = None
        save_record(actor=actor, obj=child, created=False, request=request)

    return soft_delete(actor=actor, obj=media, request=request)


def file_url(media: MediaFile) -> str | None:
    """A short-lived signed link to the object, or ``None``.

    On S3 this is a URL that expires; the caller has already run the
    permission check, and the TTL bounds how long the result of that check
    stays usable (RFP §21.10).

    Only an **absolute** URL counts. A local backend answers ``url()`` with
    a path like ``/ab/cd/….jpg`` rather than raising, and redirecting a
    browser there would 404 — ``MEDIA_URL`` is deliberately unset, so
    Django serves no media directory. Worse, if anyone ever set it, that
    path would hand the file over with no permission check at all. Refusing
    everything that is not an off-site signed URL keeps both failures out.
    """
    try:
        url = default_storage.url(media.storage_key)
    except (NotImplementedError, ValueError):
        return None

    if url and url.startswith(("http://", "https://")):
        return url
    return None


def read_bytes(media: MediaFile) -> bytes | None:
    """The file's contents, for embedding rather than serving.

    Used by the PDF renderer: WeasyPrint must not fetch anything over the
    network (spec section 8.1), so a child's photo is inlined as a data URI.
    Returns ``None`` when the object has gone missing from the bucket — a
    report with a placeholder beats a report that fails to render.
    """
    try:
        with default_storage.open(media.storage_key) as handle:
            return handle.read()
    except (FileNotFoundError, OSError):
        return None


def record_download(*, actor, media, request=None) -> None:
    """RFP §971 — who downloaded which child's photo, and when."""
    audit(action=AuditAction.DOWNLOAD, request=request, actor=actor,
          child=media.child, obj=media, kindergarten=media.kindergarten)
