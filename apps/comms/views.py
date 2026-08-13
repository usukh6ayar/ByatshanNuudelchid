"""Announcement screens — RFP §8.1.

One list for staff and one for families, because they answer different
questions: a teacher asks "who has read this", a parent asks "what is new".
Both read through ``selectors``, which is where the targeting rule lives.
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core.permissions import visible_children
from apps.tenants.selectors import assignable_groups

from . import selectors, services


def _is_staff(user) -> bool:
    return bool(user.kindergarten_ids) and any(
        services.can_publish_in(user, kindergarten_id)
        for kindergarten_id in user.kindergarten_ids
    )


@login_required
def announcement_list(request):
    """RFP §8.1. The same URL for both roles; the queryset differs."""
    staff = _is_staff(request.user)

    if staff:
        queryset = selectors.for_staff(request.user)
    else:
        queryset = selectors.with_read_flag(
            selectors.for_guardian(request.user), request.user
        )

    page = Paginator(queryset, selectors.PAGE_SIZE).get_page(
        request.GET.get("page")
    )

    return render(request, "comms/list.html", {
        "page": page,
        "is_staff": staff,
        "base_template": "base_teacher.html" if staff else "base_parent.html",
        "nav": "announcements",
        "unread": 0 if staff else selectors.unread_count(request.user),
    })


@login_required
def announcement_detail(request, announcement_id):
    """RFP §8.1 — reading one marks it read."""
    announcement = selectors.announcement_detail(request.user, announcement_id)
    if announcement is None:
        raise Http404

    staff = _is_staff(request.user)
    if not staff:
        # §8.1 allows "автоматаар" — opening it is the acknowledgement.
        services.mark_read(actor=request.user, announcement=announcement)

    return render(request, "comms/detail.html", {
        "announcement": announcement,
        "is_staff": staff,
        "base_template": "base_teacher.html" if staff else "base_parent.html",
        "nav": "announcements",
        "readers": selectors.readers(announcement) if staff else None,
        "can_edit": staff and services.can_publish_in(
            request.user, announcement.kindergarten_id
        ),
    })


@login_required
def announcement_form(request, announcement_id=None):
    """RFP §8.1 — create or edit, always landing as a draft."""
    announcement = None
    if announcement_id is not None:
        announcement = selectors.for_staff(request.user).filter(
            pk=announcement_id
        ).first()
        if announcement is None:
            raise Http404

    groups = assignable_groups(request.user)
    if announcement is not None:
        groups = groups.filter(kindergarten_id=announcement.kindergarten_id)

    kindergarten_id = (
        announcement.kindergarten_id if announcement
        else _default_kindergarten(request.user, groups)
    )
    if kindergarten_id is None:
        raise Http404

    context = {
        "announcement": announcement,
        "groups": groups,
        "children": visible_children(request.user).filter(
            enrollments__kindergarten_id=kindergarten_id
        ).distinct().order_by("last_name", "first_name"),
        "selected_groups": set(),
        "selected_children": set(),
        "base_template": "base_teacher.html",
        "nav": "announcements",
    }

    if announcement is not None:
        context["selected_groups"] = {
            target.group_id for target in announcement.targets.all()
            if target.group_id
        }
        context["selected_children"] = {
            target.child_id for target in announcement.targets.all()
            if target.child_id
        }

    if request.method == "POST":
        try:
            announcement = services.save_announcement(
                actor=request.user, kindergarten_id=kindergarten_id,
                announcement=announcement,
                title=request.POST.get("title", ""),
                body=request.POST.get("body", ""),
                starts_on=_date(request.POST.get("starts_on")),
                ends_on=_date(request.POST.get("ends_on")),
                is_important=request.POST.get("is_important") == "on",
                request=request,
            )
            services.set_targets(
                actor=request.user, announcement=announcement,
                groups=request.POST.getlist("groups"),
                children=request.POST.getlist("children"),
                request=request,
            )
            if request.POST.get("publish") == "on":
                services.publish(actor=request.user,
                                 announcement=announcement, request=request)
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, ValueError) as exc:
            context |= {
                "error": _message(exc), "form": request.POST,
                "selected_groups": {int(pk) for pk
                                    in request.POST.getlist("groups")
                                    if pk.isdigit()},
                "selected_children": {int(pk) for pk
                                      in request.POST.getlist("children")
                                      if pk.isdigit()},
            }
            return render(request, "comms/form.html", context)

        messages.success(request, "Мэдэгдэл хадгалагдлаа.")
        return redirect("comms:detail", announcement_id=announcement.pk)

    context["form"] = announcement or {}
    return render(request, "comms/form.html", context)


@login_required
def announcement_publish(request, announcement_id):
    """RFP §8.1."""
    if request.method != "POST":
        raise Http404

    announcement = selectors.for_staff(request.user).filter(
        pk=announcement_id
    ).first()
    if announcement is None:
        raise Http404

    try:
        services.publish(actor=request.user, announcement=announcement,
                         request=request)
    except PermissionDenied:
        raise Http404 from None

    messages.success(request, "Мэдэгдэл нийтлэгдлээ.")
    return redirect("comms:detail", announcement_id=announcement.pk)


@login_required
def announcement_delete(request, announcement_id):
    """RFP §8.1, §3.4."""
    announcement = selectors.for_staff(request.user).filter(
        pk=announcement_id
    ).first()
    if announcement is None:
        raise Http404

    if request.method != "POST":
        return render(request, "comms/delete_confirm.html", {
            "announcement": announcement,
            "base_template": "base_teacher.html",
            "nav": "announcements",
        })

    try:
        services.delete_announcement(actor=request.user,
                                     announcement=announcement,
                                     request=request)
    except PermissionDenied:
        raise Http404 from None

    messages.success(request, "Мэдэгдэл архивлагдлаа.")
    return redirect("comms:list")


@login_required
def mark_read(request, announcement_id):
    """RFP §8.1 — the explicit "уншсан" button."""
    if request.method != "POST":
        raise Http404

    announcement = selectors.for_guardian(request.user).filter(
        pk=announcement_id
    ).first()
    if announcement is None:
        raise Http404

    services.mark_read(actor=request.user, announcement=announcement)
    return redirect("comms:list")


# ---------------------------------------------------------------- helpers


def _default_kindergarten(user, groups):
    """Which kindergarten a new announcement belongs to.

    Almost everyone belongs to exactly one. Someone who works at two picks
    it implicitly by the group they address; until then the first is used,
    and ``set_targets`` refuses anything outside it.
    """
    group = groups.first()
    if group is not None:
        return group.kindergarten_id
    ids = user.kindergarten_ids
    return next(iter(ids), None)


def _date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError("Огноо буруу форматтай байна.") from None


def _message(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)
