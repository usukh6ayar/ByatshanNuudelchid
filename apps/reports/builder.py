"""Assembling a child's portfolio for rendering — RFP §10.1.

Kept out of ``tasks.py`` so the thing that decides *what goes in the PDF* can
be read and tested without a worker, and out of the template so the template
only lays out what it is given.

**Every read is scoped to the person who asked for the report**, not to the
worker running it. A guardian's copy contains what a guardian may see —
approved observations, published assessments — and a teacher's contains
theirs. The alternative, rendering everything and trusting the template to
hide the rest, is one forgotten ``{% if %}`` away from handing a family
another kindergarten's notes.
"""

from apps.assessment import selectors as assessment_selectors
from apps.children.services import current_enrollment
from apps.core.pdf import data_uri_from_bytes
from apps.media import services as media_services
from apps.observations import selectors as observation_selectors
from apps.observations.models import Observation
from apps.portfolio import selectors as portfolio_selectors

__all__ = ["build_context"]

# Photographs dominate the file size (§10.3 wants a small file at good
# quality). One inlined photo per report is the profile picture; observation
# attachments are listed but not embedded until Phase 2's album work, where
# the medium variant exists to embed instead of the original.
MAX_INLINE_BYTES = 4 * 1024 * 1024


def build_context(*, viewer, child, sections) -> dict:
    """Everything the portfolio template renders, and nothing else."""
    wanted = set(sections)
    enrollment = current_enrollment(child)

    context = {
        "child": child,
        "kindergarten": child.kindergarten,
        "enrollment": enrollment,
        "sections": wanted,
        "photo_data_uri": _photo(child),
        "generated_for": viewer,
    }

    if "basic" in wanted:
        context["guardianships"] = list(
            child.guardianships.select_related("guardian_user")
        )
        context["enrollment_history"] = list(
            child.enrollments.select_related("group", "school_year",
                                             "kindergarten")
            .order_by("started_on")
        )

    if "about_me" in wanted:
        context["about"] = portfolio_selectors.about_me(child)

    if "birthdays" in wanted:
        context["birth"] = portfolio_selectors.birth_facts(child)
        context["birthdays"] = portfolio_selectors.birthdays(child)

    if "age_profiles" in wanted:
        context["age_profiles"] = [
            (age, profile)
            for age, profile in portfolio_selectors.age_profiles(child).items()
            if profile is not None
        ]

    if "observations" in wanted or "parent_observations" in wanted:
        readable = observation_selectors.child_observations(viewer, child)
        # §5.4 — only what the teacher marked for inclusion reaches the
        # family's report, and a parent's note only once it is approved.
        readable = readable.filter(include_in_report=True)

        if "observations" in wanted:
            context["observations"] = list(
                readable.filter(source=Observation.Source.TEACHER)
            )
        if "parent_observations" in wanted:
            context["parent_observations"] = list(
                readable.filter(
                    source=Observation.Source.PARENT,
                    review_status=Observation.ReviewStatus.APPROVED,
                )
            )

    if "assessments" in wanted and enrollment is not None:
        context["assessment_matrix"] = assessment_selectors.assessment_matrix(
            viewer, child, enrollment.school_year
        )

    # Decided last, once every section knows whether it has anything to say.
    context["sections"] = _sections_with_content(context, wanted)
    return context


def _sections_with_content(context: dict, wanted: set[str]) -> set[str]:
    """Drop the sections that would print a heading and nothing else — D5.

    Each §10.1 section starts on its own page, which is right for a document
    that gets printed and punched: a section split across a fold is
    unreadable. The consequence is that an empty section also gets a page,
    and for a newly enrolled child that was five of eight pages carrying one
    grey line reading "Бөглөгдөөгүй байна."

    ``basic`` is never dropped. It is the registration record — name, date of
    birth, guardians — and a portfolio without it is not a portfolio. It also
    cannot be empty: the child exists.

    Decided here rather than in the template because the template's job is to
    lay out what it is given (CLAUDE.md §2.1), and because "is this section
    empty" is the same question the request form will need when it stops
    offering checkboxes for sections that would render blank.
    """
    filled = {"basic"} & wanted

    checks = {
        "about_me": lambda: context.get("about") is not None,
        "birthdays": lambda: bool(context.get("birthdays")),
        "age_profiles": lambda: bool(context.get("age_profiles")),
        "observations": lambda: bool(context.get("observations")),
        "parent_observations": lambda: bool(context.get("parent_observations")),
        # A matrix with no assessment recorded in any term is a grid of
        # dashes, which tells a family nothing they did not already know.
        "assessments": lambda: _matrix_has_a_value(
            context.get("assessment_matrix")
        ),
    }

    for code, has_content in checks.items():
        if code in wanted and has_content():
            filled.add(code)

    return filled


def _matrix_has_a_value(matrix) -> bool:
    if not matrix:
        return False
    return any(
        cell is not None
        for row in matrix.get("rows", [])
        for cell in row.get("cells", [])
    )


def _photo(child) -> str | None:
    """The child's photo, inlined — §10.3 wants the picture in the PDF.

    Inlined rather than linked because WeasyPrint would otherwise fetch it
    over the network, which for a child's photo would require a URL that
    works without a permission check (RFP §4.4).
    """
    media = child.photo
    if media is None or media.size_bytes > MAX_INLINE_BYTES:
        return None

    payload = media_services.read_bytes(media)
    if payload is None:
        # The object is missing from the bucket. A portfolio without the
        # photograph is still worth printing; a failed render is not.
        return None

    return data_uri_from_bytes(payload, media.mime_type)
