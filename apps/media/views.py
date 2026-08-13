"""Serving files — RFP §4.4, §15, §21.10. Spec section 7.1.

```
GET /media/<uuid>/<variant>/
      │
      ▼  can_access_child(user, media.child)
      │
   ✗ 404          ✓ signed URL (TTL 5 min) → redirect
```

The link is minted **after** the check, never before, and it expires. There
is no route by which a file reaches a browser without passing through this
function.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import redirect

from apps.core.permissions import can_access_child

from . import services
from .models import MediaFile

# Only ``full`` exists in Phase 1. The segment is in the URL from the start
# so links already stored in reports keep working when Phase 3 adds
# thumbnails (spec section 7.1).
VARIANTS = {"full"}


@login_required
def serve(request, public_id, variant="full"):
    """Hand back one file, if this user may see the child it belongs to."""
    if variant not in VARIANTS:
        raise Http404

    media = MediaFile.objects.filter(
        public_id=public_id, status=MediaFile.Status.READY
    ).select_related("child", "kindergarten").first()

    # 404 for "no such file" and for "not yours" alike: distinguishing them
    # would confirm that a given id exists (RFP §21.4).
    if media is None:
        raise Http404

    if media.child is not None:
        if not can_access_child(request.user, media.child):
            raise Http404
        # A file written before a transfer stays with the kindergarten that
        # took it — the same rule the observations follow (CLAUDE.md §1.2).
        from apps.core.permissions import visible_kindergartens

        if media.kindergarten_id not in visible_kindergartens(request.user,
                                                              media.child):
            raise Http404
    elif not request.user.has_membership_in([media.kindergarten_id]):
        raise Http404

    services.record_download(actor=request.user, media=media, request=request)

    if settings.MEDIA_REDIRECT_SIGNED_URL:
        url = services.file_url(media)
        if url:
            return redirect(url)

    # Either the deployment asked us to stream, or the backend cannot sign
    # (the in-memory one under test). The permission check has already run,
    # so streaming here is the same decision, just without the round trip.
    # ``MEDIA_URL`` stays unset in every environment, so Django never serves
    # a media directory of its own.
    return FileResponse(
        default_storage.open(media.storage_key),
        content_type=media.mime_type,
        # inline, not attachment: these are shown in the portfolio.
        filename=media.original_name or "image",
    )
