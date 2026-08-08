"""Cross-cutting views: the health check and the post-login landing page."""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect


@login_required
def home(request):
    """Send each user to the screen their role uses.

    Derived from ``Membership`` rather than stored anywhere: one person can
    hold several roles (spec section 4.1), so this picks the most capable
    one rather than assuming there is only ever one.
    """
    from apps.accounts.models import Role

    roles = set(
        request.user.memberships.filter(is_active=True).values_list(
            "role", flat=True
        )
    )

    if roles & {Role.SUPERADMIN, Role.ADMIN}:
        return redirect("/udirdlaga/")
    if Role.TEACHER in roles:
        return redirect("children:list")
    if Role.GUARDIAN in roles:
        return redirect("children:parent_home")

    # Authenticated but not a member of anything yet — an account created
    # but not attached. Say so rather than looping back to the login page.
    return redirect("children:parent_home")


def healthz(request):
    checks = {}
    ok = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — report, never crash the probe
        checks["database"] = f"error: {exc}"
        ok = False

    try:
        from django.core.cache import cache

        cache.set("healthz", "1", 5)
        checks["cache"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"

    return JsonResponse({"status": "ok" if ok else "degraded", "checks": checks},
                        status=200 if ok else 503)
