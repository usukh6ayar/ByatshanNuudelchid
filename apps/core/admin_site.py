"""The administrator's workspace at ``/udirdlaga/`` — RFP §2.1.

Two admin surfaces, deliberately separate (spec section 3.3):

``/django-admin/``  Django's own site. Superusers only, for development and
                    emergency data repair. Not given to customers.
``/udirdlaga/``     This site. The product screen a kindergarten director
                    uses: Mongolian, scoped to their own kindergarten, and
                    routed through ``services`` so nothing skips the audit
                    log or soft delete.
"""

from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts.models import Role


class KinderAdminSite(AdminSite):
    site_title = "Удирдлага"
    site_header = "Цэцэрлэгийн удирдлагын систем"
    index_title = "Удирдлагын хэсэг"

    def login(self, request, extra_context=None):
        """Use the project's login view, not Django's admin one.

        Django's admin login is a second, independent authentication path. It
        would bypass the §3.1 lockout and the §971 audit entries entirely,
        leaving administrator accounts — the most valuable ones — as the only
        unthrottled way in.
        """
        target = request.GET.get(REDIRECT_FIELD_NAME) or request.get_full_path()
        query = urlencode({REDIRECT_FIELD_NAME: target})
        return redirect(f"{reverse('accounts:login')}?{query}")

    def logout(self, request, extra_context=None):
        """Same reasoning: one logout path, so the audit row is always written."""
        return redirect("accounts:logout")

    def has_permission(self, request) -> bool:
        """Access comes from Membership, not from ``is_staff``.

        ``is_staff`` is Django's own flag and gates ``/django-admin/``. Using
        it here would mean granting a director access to the raw superuser
        site as a side effect.
        """
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        return user.memberships.filter(
            is_active=True, role__in=[Role.ADMIN, Role.SUPERADMIN]
        ).exists()


admin_site = KinderAdminSite(name="udirdlaga")
