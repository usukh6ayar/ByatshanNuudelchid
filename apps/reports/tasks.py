"""The report worker — RFP §549, CLAUDE.md §6.

Everything slow happens here and nothing else does. The task's whole job is
to move one ``ReportJob`` from queued to done or failed, and to leave a
readable reason on the row either way — the person watching the screen
cannot see the worker's log.
"""

import logging

from celery import shared_task

from apps.core.pdf import render_pdf_with_pages
from apps.media import services as media_services

from . import services
from .builder import build_context
from .models import ReportJob

logger = logging.getLogger(__name__)

TEMPLATES = {
    ReportJob.Type.CHILD_PORTFOLIO: "reports/child_portfolio.html",
}


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_report(self, job_id: int) -> str:
    """Render one queued report.

    Not retried on a bad job or a rendering error: both would fail again
    identically, and a retry loop only delays the message the requester
    needs. Retries exist for the storage write, which can fail for reasons
    that pass.
    """
    job = ReportJob.objects.filter(pk=job_id).select_related(
        "child", "kindergarten", "requested_by"
    ).first()

    if job is None:
        # The row was archived between the request and the worker picking it
        # up. Nothing to do and nobody to tell.
        logger.warning("Report job %s no longer exists", job_id)
        return "missing"

    if job.status not in {ReportJob.Status.QUEUED, ReportJob.Status.RUNNING}:
        return job.status

    services.mark_running(job)

    try:
        payload, page_count = _render(job)
    except Exception as exc:  # noqa: BLE001 — the reason belongs on the row
        logger.exception("Report job %s failed to render", job_id)
        services.mark_failed(job, str(exc))
        return ReportJob.Status.FAILED

    try:
        media = media_services.store_generated_file(
            actor=job.requested_by,
            child=job.child,
            payload=payload,
            mime="application/pdf",
            filename=_filename(job),
            kindergarten_id=job.kindergarten_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Report job %s failed to store", job_id)
        services.mark_failed(job, str(exc))
        raise self.retry(exc=exc) from exc

    services.mark_done(job, media=media, page_count=page_count)
    return ReportJob.Status.DONE


def _render(job: ReportJob) -> tuple[bytes, int]:
    template = TEMPLATES.get(job.type)
    if template is None:
        raise ValueError(f"Тодорхойгүй тайлангийн төрөл: {job.type}")
    if job.child is None:
        raise ValueError("Тайлан хүүхэдгүй байна.")

    context = build_context(
        # The report contains what the *requester* may see, not what the
        # worker could reach. builder.py explains why.
        viewer=job.requested_by,
        child=job.child,
        sections=job.params.get("sections", []),
    )
    return render_pdf_with_pages(template, context)


def _filename(job: ReportJob) -> str:
    """A name a family can find again in their downloads folder."""
    child = job.child
    stamp = job.requested_at.strftime("%Y%m%d")
    return f"{child.last_name}_{child.first_name}_hawtas_{stamp}.pdf"


@shared_task
def expire_reports() -> int:
    """Celery beat — spec section 8's 30-day retention."""
    return services.expire_old_reports()
