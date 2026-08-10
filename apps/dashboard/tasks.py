"""Dashboard refresh — CLAUDE.md §6, spec section 10.3.

§12.2's figures count across every table in the system. Computing them on
each page load would make the administrator's screen the slowest one in the
product, so a beat task fills the cache instead.
"""

import logging

from celery import shared_task

from apps.tenants.models import Kindergarten

from .selectors import admin_dashboard

logger = logging.getLogger(__name__)


@shared_task
def refresh_admin_dashboards() -> int:
    """Recompute the system-wide figures and each kindergarten's own.

    Every scope an administrator can ask for is refreshed, because a cache
    entry nobody warms is a cache entry that is always computed inline by
    whoever opens the page first — which is exactly the slow request this
    task exists to prevent.
    """
    scopes = [None] + [
        [kindergarten_id]
        for kindergarten_id in Kindergarten.objects.values_list("id", flat=True)
    ]

    for scope in scopes:
        admin_dashboard(scope, refresh=True)

    logger.info("Refreshed %s dashboard scopes", len(scopes))
    return len(scopes)
