from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.admin_site import admin_site
from apps.core.views import healthz, home

urlpatterns = [
    # The administrator's workspace — RFP §2.1. Access comes from Membership.
    path("udirdlaga/", admin_site.urls),
    # Django's own site: superusers only, for development and emergency data
    # repair. Restricted or disabled in production — spec section 3.3.
    path("django-admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.children.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
