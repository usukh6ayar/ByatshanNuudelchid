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

from apps.children import selectors, services
from apps.core.models import AuditAction
from apps.core.permissions import is_guardian_of
from apps.core.services import audit


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
    """RFP §2.3 — choose a child, then see their summary."""
    children = selectors.guardian_children(request.user)
    if not children.exists():
        return render(request, "children/parent/no_children.html")

    child = _selected_child(request, children)

    return render(request, "children/parent/home.html", {
        "children": children,
        "child": child,
        "enrollment": services.current_enrollment(child),
    })


@login_required
def child_detail(request, child_id):
    """The child's own page — the "Хүүхдийн 360° хуудас" link on the home."""
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
    })
