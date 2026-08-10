"""Dashboard screens — RFP §12.1, §12.2.

The teacher's dashboard becomes the landing page after login, replacing the
straight redirect into the children list: §12.1 is a list of the things a
teacher needs to notice on arriving, and a list of names is not that.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.accounts.models import Role

from . import selectors


def _roles(user) -> set[str]:
    return set(
        user.memberships.filter(is_active=True).values_list("role", flat=True)
    )


@login_required
def teacher_dashboard(request):
    """RFP §12.1."""
    roles = _roles(request.user)
    if not roles & {Role.TEACHER, Role.ADMIN, Role.SUPERADMIN}:
        raise Http404

    return render(request, "dashboard/teacher.html",
                  selectors.teacher_dashboard(request.user) | {"nav": "home"})


@login_required
def admin_dashboard(request):
    """RFP §12.2.

    A superadmin sees the whole system; a director sees their own
    kindergartens. The scope is part of the cache key, so one does not read
    the other's figures out of a shared cache entry.
    """
    roles = _roles(request.user)
    if not roles & {Role.ADMIN, Role.SUPERADMIN}:
        raise Http404

    scope = (None if Role.SUPERADMIN in roles
             else sorted(request.user.kindergarten_ids))

    return render(request, "dashboard/admin.html", {
        "figures": selectors.admin_dashboard(scope),
        "is_superadmin": Role.SUPERADMIN in roles,
        "nav": "dashboard",
    })
