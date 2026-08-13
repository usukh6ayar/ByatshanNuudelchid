"""Assessment reads — RFP §6.1, §6.2, §6.3, §6.4.

Two rules run through this module.

**The configuration lookup is written once.** ``kindergarten IS NULL`` means a
system default and a row with a kindergarten belongs to that one alone, so
every read is "the system list, plus mine". That condition lives in
:func:`_visible_config` and nowhere else — copied into each screen it would
eventually be forgotten in one of them, and that screen would leak another
kindergarten's configuration.

**Reading a child's assessments is filtered twice.** ``can_access_child``
answers "may this user see this child at all"; it does not answer "may they
see *this record* about the child". After a transfer the previous
kindergarten's teacher still reaches the child but must not see what is
written at the new one, so every read filters on
``visible_kindergartens()`` (CLAUDE.md §1.2). For a guardian there is a
second gate on top: RFP §2.3 gives them "багшийн зөвшөөрсөн" assessments
only.
"""

import datetime as dt

from django.db.models import Q

from apps.core.permissions import is_guardian_of, visible_kindergartens

from .models import (
    Assessment,
    AssessmentLevel,
    AssessmentScale,
    DevelopmentDomain,
    Term,
    TermReport,
)

__all__ = [
    "domains_for",
    "scale_for",
    "levels_for",
    "terms_for",
    "current_term",
    "child_assessments",
    "assessment_matrix",
    "group_grid",
    "term_report",
    "term_reports_for",
]


def _visible_config(queryset, kindergarten):
    """The system list plus this kindergarten's own additions."""
    kindergarten_id = getattr(kindergarten, "pk", kindergarten)
    return queryset.filter(
        Q(kindergarten__isnull=True) | Q(kindergarten_id=kindergarten_id)
    )


def domains_for(kindergarten):
    """RFP §6.1 — the development domains this kindergarten assesses against."""
    return _visible_config(
        DevelopmentDomain.objects.filter(is_active=True), kindergarten
    ).order_by("order", "name")


def scale_for(kindergarten) -> AssessmentScale | None:
    """RFP §6.2 — the scale new assessments are recorded on.

    A kindergarten's own default wins over the system one, which is the
    point of letting an administrator define a scale at all.
    """
    scales = _visible_config(
        AssessmentScale.objects.filter(is_default=True), kindergarten
    )
    own = scales.filter(kindergarten__isnull=False).first()
    return own or scales.first()


def levels_for(kindergarten):
    """The steps of :func:`scale_for`, lowest first."""
    scale = scale_for(kindergarten)
    if scale is None:
        return AssessmentLevel.objects.none()
    return scale.levels.order_by("value")


def terms_for(school_year):
    """RFP §6.4 — the four terms of a school year."""
    return Term.objects.filter(school_year=school_year).order_by("number")


def current_term(school_year, on: dt.date | None = None) -> Term | None:
    """The term covering ``on``, or ``None``.

    Returns ``None`` over the summer and before any term is configured.
    Callers must handle that rather than assume a term exists — the
    assessment screens fall back to an explicit dropdown.
    """
    on = on or dt.date.today()
    return (
        Term.objects.filter(
            school_year=school_year, starts_on__lte=on, ends_on__gte=on
        )
        .order_by("number")
        .first()
    )


def _readable(user, child):
    """Every assessment about this child this user is allowed to read."""
    queryset = Assessment.objects.filter(
        child=child,
        kindergarten_id__in=visible_kindergartens(user, child),
    )
    if is_guardian_of(user, child):
        # RFP §2.3 — "багшийн зөвшөөрсөн ... үнэлгээ".
        queryset = queryset.filter(visible_to_parents=True)
    return queryset


def child_assessments(user, child, term=None):
    """RFP §6.4 — one child's assessments, newest term first."""
    queryset = _readable(user, child).select_related(
        "domain", "level", "term", "term__school_year"
    )
    if term is not None:
        queryset = queryset.filter(term=term)
    return queryset.order_by("-term__number", "domain__order", "domain__name")


def assessment_matrix(user, child, school_year) -> dict:
    """Domains down the side, terms across the top — RFP §6.5's comparison.

    Built in Python from one query rather than a query per cell, which is
    what a template loop over ``domains × terms`` would otherwise produce
    (CLAUDE.md §3.5).
    """
    domains = list(domains_for(child.kindergarten_id))
    terms = list(terms_for(school_year))

    existing = {
        (row.domain_id, row.term_id): row
        for row in _readable(user, child)
        .filter(term__school_year=school_year)
        .select_related("level")
    }

    return {
        "terms": terms,
        "rows": [
            {
                "domain": domain,
                "cells": [existing.get((domain.pk, term.pk)) for term in terms],
            }
            for domain in domains
        ],
    }


def group_grid(user, group, term, domain) -> dict:
    """RFP §6.3 — every child in a group assessed on one domain, one screen.

    Three queries whatever the group size: the children, their assessments,
    and the levels to choose from. ``test_assessment.py`` pins that with
    ``assertNumQueries`` — §6.3 is the screen a teacher opens most often and
    a per-child query here is what makes it slow (RFP §17).
    """
    from apps.children.models import Enrollment
    from apps.core.permissions import visible_children

    # Evaluated once: the two lookups below both iterate it, and leaving it
    # lazy would run the same query twice.
    enrollments = list(
        Enrollment.objects.filter(
            group=group,
            school_year=term.school_year,
            status=Enrollment.Status.ACTIVE,
            child__in=visible_children(user),
        )
        .select_related("child")
        .order_by("child__last_name", "child__first_name")
    )

    existing = {
        row.enrollment_id: row
        for row in Assessment.objects.filter(
            term=term, domain=domain, enrollment__in=enrollments
        ).select_related("level")
    }
    previous = _previous_term_levels(enrollments, term, domain)

    rows = [
        {
            "enrollment": enrollment,
            "child": enrollment.child,
            "assessment": existing.get(enrollment.pk),
            # §6.3 — "өмнөх үнэлгээтэй харьцуулах", resolved here so the
            # template renders a value instead of doing a lookup.
            "previous": previous.get(enrollment.child_id),
        }
        for enrollment in enrollments
    ]

    return {
        "rows": rows,
        "levels": list(levels_for(group.kindergarten_id)),
        # §6.3 — "хийгдээгүй үнэлгээг ялгаж харуулах".
        "missing": sum(1 for row in rows if row["assessment"] is None),
        "total": len(rows),
    }


def _previous_term_levels(enrollments, term, domain) -> dict:
    """§6.3 — "өмнөх үнэлгээтэй харьцуулах", keyed by child id.

    One extra query for the whole grid, not one per row, and none at all in
    the first term of the year.
    """
    if term.number <= 1:
        return {}

    return {
        row.child_id: row.level
        for row in Assessment.objects.filter(
            child__in=[enrollment.child_id for enrollment in enrollments],
            term__school_year=term.school_year,
            term__number=term.number - 1,
            domain=domain,
        ).select_related("level")
    }


def _readable_reports(user, child):
    """Every term report about this child this user may read — §2.3.

    The guardian filter is the whole difference between the two roles, and
    it lives here so no screen has to remember it.
    """
    queryset = TermReport.objects.filter(
        child=child,
        kindergarten_id__in=visible_kindergartens(user, child),
    )
    if is_guardian_of(user, child):
        queryset = queryset.filter(status=TermReport.Status.FINAL)
    return queryset


def term_report(user, child, term) -> "TermReport | None":
    """RFP §6.4 — one term's narrative, or ``None`` if not readable."""
    return (
        _readable_reports(user, child)
        .filter(term=term)
        .select_related("term", "author")
        .first()
    )


def term_reports_for(user, child) -> dict:
    """``{term_id: TermReport}`` for the child screen.

    A dict rather than a queryset because the template looks each term up by
    id while iterating the matrix columns; a filter per column is the N+1
    CLAUDE.md §3.5 forbids.
    """
    return {
        report.term_id: report
        for report in _readable_reports(user, child).select_related("term")
    }
