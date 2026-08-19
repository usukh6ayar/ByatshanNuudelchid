from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.admin_site import admin_site
from apps.core.views import healthz, home

urlpatterns = [
    # The administrator's own screens — RFP §2.1, §13. These live under
    # /udirdlaga/ and must be matched BEFORE the admin site mounted below,
    # which would otherwise swallow every path in that prefix.
    path("", include("apps.tenants.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.assessment.urls")),
    # The rest of the administrator's workspace, still on Django's admin.
    # Being replaced screen by screen; what is left is the configuration
    # tables a director edits rarely.
    path("udirdlaga/", admin_site.urls),
    # Django's own site: superusers only, for development and emergency data
    # repair. Restricted or disabled in production — spec section 3.3.
    path("django-admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("", home, name="home"),
    path("", include("apps.children.urls")),
    path("", include("apps.portfolio.urls")),
    path("", include("apps.observations.urls")),
    path("", include("apps.media.urls")),
    path("", include("apps.comms.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.attendance.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
