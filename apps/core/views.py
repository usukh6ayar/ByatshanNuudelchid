"""RFP §657 — health check endpoint."""

from django.db import connection
from django.http import JsonResponse


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
