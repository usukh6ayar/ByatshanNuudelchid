"""Guardian-facing screens — RFP §2.3, §21.3.

The parent home is the screen in `docs/design/screens/parent-home.jpeg`.

One deviation from that mockup, and it is deliberate: the kindergarten name
and logo follow the **selected child** rather than sitting fixed in the
chrome. Spec section 4.2 lets a guardian have children at two kindergartens
and resolves the tenant from the child, never from the session. For the
common case — one kindergarten — the screen looks exactly as drawn.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.assessment import selectors as assessment_selectors
from apps.children import selectors, services
from apps.comms import selectors as comms_selectors
from apps.core.models import AuditAction
from apps.core.permissions import is_guardian_of
from apps.core.services import audit
from apps.observations import selectors as observation_selectors
from apps.portfolio import selectors as portfolio_selectors

# How much of each list a screen shows before handing over to the screen that
# owns it. Short on purpose: both of these are overviews, and a family
# scrolling twenty observations here would never reach the sections below.
#
# The home's counts are deliberately smaller than the profile's. The two
# screens are one journey and they overlap: the home answers "what happened
# lately", the profile answers "who is my child". Showing the same four
# observations on both would make the home read as a worse copy of the
# profile rather than the way into it.
RECENT_OBSERVATIONS = 4
RECENT_MOMENTS = 8
RECENT_ASSESSMENTS = 6

HOME_OBSERVATIONS = 3
HOME_MOMENTS = 6
HOME_ANNOUNCEMENTS = 3


def _selected_child(request, children):
    """The child in the switcher — from the query string, else the first."""
    requested = request.GET.get("child")
    if requested:
        child = children.filter(pk=requested).first()
        if child is None:
            # Not "forbidden": the id is simply not among this guardian's
            # children, and saying so would confirm it exists (RFP §21.4).
            raise Http404
        return child
    return children.first()


@login_required
def home(request):
    """RFP §2.3 — choose a child, then see what has happened lately.

    Redesigned 2026-08-16 alongside the child profile (docs/UI_AUDIT.md).
    Same wiring rule as ``child_detail`` below: every addition is a read
    through a selector that already existed, and each one that can expose a
    record takes the **user**, not just the child, so the §5.1 and §8.1
    visibility rules are applied by the layer that owns them.

    ``_selected_child`` has already resolved the child out of
    ``guardian_children``, so reaching this line means this user is a
    guardian of this child. The announcements are the exception that proves
    the rule: they are scoped to the *user*, not the selected child, because
    ``for_guardian`` starts from ``visible_children`` and a notice about a
    sibling at another kindergarten still belongs on this family's home.
    """
    children = selectors.guardian_children(request.user)
    if not children.exists():
        return render(request, "children/parent/no_children.html")

    child = _selected_child(request, children)

    announcements = comms_selectors.with_read_flag(
        comms_selectors.for_guardian(request.user), request.user
    )[:HOME_ANNOUNCEMENTS]

    return render(request, "children/parent/home.html", {
        "children": children,
        "child": child,
        "enrollment": services.current_enrollment(child),
        "announcements": announcements,
        "observations": observation_selectors.child_observations(
            request.user, child
        )[:HOME_OBSERVATIONS],
        "moments": observation_selectors.recent_media_for_child(
            request.user, child, limit=HOME_MOMENTS
        ),
        "nav": "home",
    })


@login_required
def child_detail(request, child_id):
    """The child's own page — the "Хүүхдийн 360° хуудас" link on the home.

    Redesigned 2026-08-16 (docs/UI_AUDIT.md) from a registration record into
    the family's view of their child. The extra context is all reads through
    selectors that already existed; no new model, endpoint or rule.

    Order matters and is not incidental: the child is resolved through
    ``child_detail`` and ``is_guardian_of`` **first**, and only then is
    anything else read. The portfolio selectors take a child and carry no
    permission check of their own, which is safe exactly because nothing
    reaches them until this user has been proven to be this child's
    guardian.

    The observation and media reads are the opposite case — they take the
    user, because the §5.1 "visible to parents" flag is theirs to apply and
    a guardian must not see an observation a teacher marked private, nor a
    photograph attached to one.
    """
    child = selectors.child_detail(request.user, child_id)
    if child is None or not is_guardian_of(request.user, child):
        raise Http404

    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten)

    return render(request, "children/parent/detail.html", {
        "child": child,
        "enrollment": services.current_enrollment(child),
        "history": selectors.enrollment_history(child),
        "children": selectors.guardian_children(request.user),
        "about": portfolio_selectors.about_me(child),
        "birth": portfolio_selectors.birth_facts(child),
        "age_profiles": portfolio_selectors.age_profiles(child),
        "observations": observation_selectors.child_observations(
            request.user, child
        )[:RECENT_OBSERVATIONS],
        "moments": observation_selectors.recent_media_for_child(
            request.user, child, limit=RECENT_MOMENTS
        ),
        "assessments": assessment_selectors.child_assessments(
            request.user, child
        )[:RECENT_ASSESSMENTS],
        "nav": "home",
    })
