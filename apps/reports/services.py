"""Report requests — RFP §10, §549. Spec section 8."""

import datetime as dt

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.permissions import can_access_child, visible_kindergartens
from apps.core.services import save_record

from .models import ReportJob

__all__ = [
    "SECTIONS",
    "request_child_portfolio",
    "mark_running",
    "mark_done",
    "mark_failed",
    "expire_old_reports",
]

# RFP §10.1's list, minus the entries whose data is Phase 2 — growth charts,
# photo albums, term and annual reports, work comparison, milestones. A
# checkbox for a section that renders empty teaches people the report is
# broken, so those arrive with the features behind them.
SECTIONS = [
    ("basic", "Хүүхдийн үндсэн мэдээлэл"),
    ("about_me", "Миний тухай"),
    ("birthdays", "Төрсөн өдөр"),
    ("age_profiles", "Нас тус бүрийн мэдээлэл"),
    ("observations", "Багшийн ажиглалт"),
    ("parent_observations", "Эцэг эхийн ажиглалт"),
    ("assessments", "Хөгжлийн үнэлгээ"),
]
DEFAULT_SECTIONS = [code for code, _ in SECTIONS]


def _clean_sections(sections) -> list[str]:
    """Keep only the sections that exist, in the order §10.1 lists them.

    Order comes from ``SECTIONS`` rather than from the request: a portfolio
    whose pages come out in whatever order the checkboxes were posted is not
    a document anyone wants to print.
    """
    if not sections:
        return list(DEFAULT_SECTIONS)

    chosen = set(sections)
    ordered = [code for code, _ in SECTIONS if code in chosen]
    if not ordered:
        raise ValidationError("Тайланд оруулах хэсгээ сонгоно уу.")
    return ordered


@transaction.atomic
def request_child_portfolio(*, actor, child, sections=None,
                            request=None) -> ReportJob:
    """RFP §10.1 — queue a child's portfolio PDF.

    Returns as soon as the row exists (§549). The worker is started with
    ``transaction.on_commit`` and not before: ``ATOMIC_REQUESTS`` wraps the
    whole request, so a bare ``.delay()`` can reach a worker that then looks
    for a job the database has not committed yet (CLAUDE.md §6.1).
    """
    if not can_access_child(actor, child):
        raise PermissionDenied

    # The report is assembled from what this user may read, so it has to be
    # filed against a kindergarten they are actually part of.
    kindergartens = visible_kindergartens(actor, child)
    if not kindergartens:
        raise PermissionDenied

    job = ReportJob(
        kindergarten_id=(
            child.kindergarten_id if child.kindergarten_id in kindergartens
            else next(iter(kindergartens))
        ),
        child=child,
        type=ReportJob.Type.CHILD_PORTFOLIO,
        params={"sections": _clean_sections(sections)},
        requested_by=actor,
        status=ReportJob.Status.QUEUED,
        expires_at=timezone.now() + dt.timedelta(
            days=settings.REPORT_RETENTION_DAYS
        ),
    )
    save_record(actor=actor, obj=job, created=True, request=request)

    from .tasks import generate_report

    transaction.on_commit(lambda: generate_report.delay(job.pk))
    return job


def mark_running(job: ReportJob) -> ReportJob:
    job.status = ReportJob.Status.RUNNING
    job.started_at = timezone.now()
    job.progress_percent = 10
    job.save(update_fields=["status", "started_at", "progress_percent",
                            "updated_at"])
    return job


def mark_done(job: ReportJob, *, media, page_count: int) -> ReportJob:
    job.status = ReportJob.Status.DONE
    job.result_media = media
    job.file_size = media.size_bytes
    job.page_count = page_count
    job.progress_percent = 100
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "result_media", "file_size",
                            "page_count", "progress_percent", "completed_at",
                            "updated_at"])
    return job


def mark_failed(job: ReportJob, message: str) -> ReportJob:
    """Record the failure on the row rather than only in the log.

    The person waiting on the screen is the one who needs to know, and they
    cannot read the worker's stderr.
    """
    job.status = ReportJob.Status.FAILED
    job.error_message = message[:2000]
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "error_message", "completed_at",
                            "updated_at"])
    return job


def expire_old_reports(*, now=None) -> int:
    """Spec section 8 — generated PDFs do not live forever.

    Marks the job expired and archives the file. The bytes stay in the
    bucket until a retention job removes them; what matters here is that the
    download link stops working, because the file holds a child's complete
    record.
    """
    from apps.core.services import soft_delete

    now = now or timezone.now()
    expired = ReportJob.objects.filter(
        status=ReportJob.Status.DONE, expires_at__lt=now
    ).select_related("result_media")

    count = 0
    for job in expired:
        if job.result_media_id:
            soft_delete(actor=None, obj=job.result_media)
        job.status = ReportJob.Status.EXPIRED
        job.save(update_fields=["status", "updated_at"])
        count += 1
    return count
