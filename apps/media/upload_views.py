"""Upload screens — RFP §3.4, §5.1.

Kept apart from ``views.py``, which serves files: the two have opposite
shapes. Serving answers "may you read this", uploading answers "may you
write here", and mixing them in one module is how a check ends up on the
wrong one.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render

from apps.children import selectors as child_selectors
from apps.core.permissions import can_record_for_child, is_guardian_of
from apps.observations import selectors as observation_selectors

from . import services
from .models import MediaFile


def _child_or_404(request, child_id):
    child = child_selectors.child_detail(request.user, child_id)
    if child is None:
        raise Http404
    return child


@login_required
def child_photo(request, child_id):
    """RFP §3.4 — the child's profile photo.

    A guardian may set it too: §2.3 lists photographs among what a family
    contributes, and the picture of their own child is the least contentious
    example of that.
    """
    child = _child_or_404(request, child_id)
    guardian = is_guardian_of(request.user, child)

    context = {
        "child": child,
        "is_guardian": guardian,
        "base_template": "base_parent.html" if guardian else "base_teacher.html",
        "nav": "home" if guardian else "children",
        "max_mb": _max_mb(),
    }

    if request.method == "POST":
        upload = request.FILES.get("photo")
        if upload is None:
            context["error"] = "Зураг сонгоно уу."
            return render(request, "media/child_photo.html", context)

        try:
            services.set_child_photo(actor=request.user, child=child,
                                     upload=upload, request=request)
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            context["error"] = " ".join(exc.messages)
            return render(request, "media/child_photo.html", context)

        messages.success(request, "Зураг хадгалагдлаа.")
        return redirect("portfolio:overview", child_id=child.pk)

    return render(request, "media/child_photo.html", context)


@login_required
def observation_attach(request, child_id, observation_id):
    """RFP §5.1 — "нотлох зураг", §5.3 — a child's work, dated."""
    child = _child_or_404(request, child_id)

    if not can_record_for_child(request.user, child):
        raise Http404

    observation = observation_selectors.observation_detail(
        request.user, child, observation_id
    )
    if observation is None:
        raise Http404

    context = {
        "child": child,
        "observation": observation,
        "base_template": "base_teacher.html",
        "nav": "children",
        "max_mb": _max_mb(),
    }

    if request.method == "POST":
        upload = request.FILES.get("photo")
        if upload is None:
            context["error"] = "Зураг сонгоно уу."
            return render(request, "media/observation_attach.html", context)

        try:
            services.attach_to_observation(
                actor=request.user, observation=observation, upload=upload,
                caption=request.POST.get("caption", "").strip(),
                request=request,
            )
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            context["error"] = " ".join(exc.messages)
            return render(request, "media/observation_attach.html", context)

        messages.success(request, "Зураг хавсаргагдлаа.")
        return redirect("observations:detail", child_id=child.pk,
                        observation_id=observation.pk)

    return render(request, "media/observation_attach.html", context)


@login_required
def media_delete(request, child_id, public_id):
    """RFP §3.4 — archived, not removed (CLAUDE.md §3.3)."""
    child = _child_or_404(request, child_id)

    media = MediaFile.objects.filter(public_id=public_id, child=child).first()
    if media is None:
        raise Http404

    if request.method != "POST":
        raise Http404

    try:
        services.delete_media(actor=request.user, media=media, request=request)
    except PermissionDenied:
        raise Http404 from None

    messages.success(request, "Зураг архивлагдлаа.")
    return redirect("portfolio:overview", child_id=child.pk)


def _max_mb() -> int:
    from django.conf import settings

    return settings.MAX_UPLOAD_SIZE_MB
