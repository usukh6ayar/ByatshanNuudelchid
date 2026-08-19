"""The teacher's attendance register — нэмэлт.md §1.

The models, services and selectors under this app were built and tested
before any screen existed; nothing here adds a rule. This module does what
CLAUDE.md §2.1 says a view does: resolve the group and the date, hand the
marks to ``services.record_group_day``, render.

**Server-rendered, not a JSON endpoint.** The dashboard drew this panel as a
JavaScript widget fetching a roster. §2.2 rules that out — the web layer does
not call its own API over HTTP — so the group and the date are a plain GET
form and the marks come back as an ordinary POST. It works with JavaScript
off, which on a tablet in a classroom is not a hypothetical.

Authorization is `assignable_groups` and nothing else. A group id outside the
teacher's own groups is not found and answers 404, so the screen cannot be
used to discover that another kindergarten's group exists (RFP §21.4).
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render

from apps.tenants.selectors import assignable_groups

from . import selectors, services
from .models import AttendanceStatus


def _date(raw: str | None) -> dt.date:
    """The date being recorded. Today when absent or unparseable.

    Falling back to today rather than rejecting: this screen is opened to
    record the day in progress, and an error page instead of the register is
    a worse answer to a mistyped query string than simply showing today.
    """
    if raw:
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            pass
    return dt.date.today()


@login_required
def group_register(request, group_id):
    """One group, one day — нэмэлт.md §1.

    The sheet lists every active child including the ones with no mark yet,
    because an unrecorded child is the failure that produces no error
    anywhere and quietly costs a funding day (`selectors.group_day_sheet`).
    """
    group = assignable_groups(request.user).filter(pk=group_id).first()
    if group is None:
        raise Http404

    date = _date(request.GET.get("date"))

    if request.method == "POST":
        # Posted separately from the GET query string: a teacher who changes
        # the date in the form and submits must record the date they are
        # looking at, not the one the page was opened with.
        date = _date(request.POST.get("date"))

        # `status_<enrollment_id>` and the note beside it. Ids are not
        # trusted here — `record_group_day` resolves every one of them
        # against the group and drops what does not belong to it.
        marks = {
            key.removeprefix("status_"): {
                "status": value,
                "note": request.POST.get(
                    f"note_{key.removeprefix('status_')}", ""
                ).strip(),
            }
            for key, value in request.POST.items()
            if key.startswith("status_") and value
        }

        try:
            written = services.record_group_day(
                actor=request.user, group=group, date=date, marks=marks,
                request=request,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(
                request, f"{len(written)} хүүхдийн ирц бүртгэгдлээ."
            )
        return redirect(f"{request.path}?date={date.isoformat()}")

    return render(request, "attendance/group_register.html", {
        "nav": "attendance",
        "group": group,
        "groups": assignable_groups(request.user),
        "date": date,
        # `max` on the date input. The service refuses a future day (a month's
        # funding claimed before the children attended it); saying so in the
        # control is friendlier than saying it in an error.
        "today": dt.date.today(),
        "rows": selectors.group_day_sheet(group, date),
        "statuses": AttendanceStatus.choices,
        "unmarked": len(selectors.unmarked_children(group, date)),
    })


def _message(exc) -> str:
    """The first readable line out of a Django validation error."""
    if isinstance(exc, ValidationError) and getattr(exc, "messages", None):
        return exc.messages[0]
    return str(exc) or "Ирц бүртгэхэд алдаа гарлаа."
