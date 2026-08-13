from django.urls import path

from . import upload_views, views

app_name = "media"

# Spec section 7.1. The ``<variant>`` segment is part of the URL from the
# first release even though ``full`` is the only one: links get stored in
# reports, and adding thumbnails in Phase 3 must not invalidate them.
urlpatterns = [
    path("media/<uuid:public_id>/<slug:variant>/", views.serve, name="serve"),

    path("hawtas/<int:child_id>/zurag/", upload_views.child_photo,
         name="child_photo"),
    path("hawtas/<int:child_id>/ajiglalt/<int:observation_id>/zurag/",
         upload_views.observation_attach, name="observation_attach"),
    path("hawtas/<int:child_id>/zurag/<uuid:public_id>/arhivlah/",
         upload_views.media_delete, name="delete"),
]
