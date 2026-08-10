"""Report screens — RFP §10, §549.

Three views, matching the three things a person does: ask for a PDF, wait
for it, download it. The waiting screen refreshes itself rather than holding
the connection open — §549 is about the system staying responsive, and a
page that blocks for twenty seconds fails that just as a synchronous render
would.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from apps.children import selectors as child_selectors
from apps.core.permissions import is_guardian_of

from . import services
from .models import ReportJob

POLL_SECONDS = 3


def _context(request, child_id) -> dict:
    child = child_selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404

    guardian = is_guardian_of(request.user, child)
    return {
        "child": child,
        "is_guardian": guardian,
        "base_template": "base_parent.html" if guardian else "base_teacher.html",
        "nav": "home" if guardian else "children",
    }


def _job_or_404(request, child, job_id) -> ReportJob:
    """A job belongs to the person who asked for it.

    Not merely to anyone who may see the child: the PDF was assembled from
    what the *requester* was allowed to read, so handing a teacher's copy to
    a guardian would hand over observations marked invisible to families.
    """
    job = ReportJob.objects.filter(
        pk=job_id, child=child, requested_by=request.user
    ).select_related("result_media").first()
    if job is None:
        raise Http404
    return job


@login_required
def report_request(request, child_id):
    """RFP §10.1 — choose the sections and queue the render."""
    context = _context(request, child_id)
    child = context["child"]

    context |= {
        "sections": services.SECTIONS,
        "recent": ReportJob.objects.filter(
            child=child, requested_by=request.user
        ).order_by("-requested_at")[:5],
    }

    if request.method == "POST":
        try:
            job = services.request_child_portfolio(
                actor=request.user, child=child,
                sections=request.POST.getlist("sections"),
                request=request,
            )
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            context["error"] = " ".join(exc.messages)
            return render(request, "reports/request.html", context)

        return redirect("reports:status", child_id=child.pk, job_id=job.pk)

    return render(request, "reports/request.html", context)


@login_required
def report_status(request, child_id, job_id):
    """The waiting screen — RFP §549, §626 (a loading state for slow work)."""
    context = _context(request, child_id)
    job = _job_or_404(request, context["child"], job_id)

    return render(request, "reports/status.html", context | {
        "job": job,
        "poll_seconds": POLL_SECONDS,
    })


@login_required
def report_progress(request, child_id, job_id):
    """What the waiting screen polls. JSON, so it costs one small query."""
    context = _context(request, child_id)
    job = _job_or_404(request, context["child"], job_id)

    return JsonResponse({
        "status": job.status,
        "status_display": job.get_status_display(),
        "progress": job.progress_percent,
        "finished": job.is_finished,
        "downloadable": bool(job.is_downloadable),
        "error": job.error_message,
    })


@login_required
def report_download(request, child_id, job_id):
    """Hand over the finished file.

    Redirects into the media app rather than streaming here: that view is
    the one place a file is served, and it already runs the permission check
    and writes the §971 download entry.
    """
    context = _context(request, child_id)
    job = _job_or_404(request, context["child"], job_id)

    if not job.is_downloadable:
        messages.error(request, "Тайлан бэлэн болоогүй байна.")
        return redirect("reports:status", child_id=context["child"].pk,
                        job_id=job.pk)

    return redirect("media:serve", public_id=job.result_media.public_id,
                    variant="full")
