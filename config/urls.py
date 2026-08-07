from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz

urlpatterns = [
    # Superuser tooling only. Restricted or disabled in production — CLAUDE.md §3.3
    path("django-admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("", include("apps.accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
