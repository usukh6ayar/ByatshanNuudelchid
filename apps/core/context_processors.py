"""The default shell for a page — RFP §13.

Same reasoning as the unread badge next door: the layout wraps *every*
screen, so "each view must remember to pass it" is a rule that gets broken
by the first view written after the rule. A director reaching the children
list saw the teacher's menu for exactly that reason.

A view that already knows better still wins — templates read
``base_template|default:...``, and the shared screens (portfolio,
observations, assessments, reports) set it explicitly because a teacher
reading their own child's portfolio should see the family's chrome, which
their role alone cannot tell you.
"""

from apps.core.layouts import TEACHER, layout_for


def layout(request):
    """The default shell, and the teacher nav's group — one pass.

    ``nav_group`` and ``nav_groups`` live here rather than in a processor of
    their own because that one had to call ``layout_for`` to know whether the
    teacher shell was even being rendered — the same call this function was
    already making. Two processors meant two identical queries on every
    request, which `tenants`' ``assertNumQueries`` caught.

    **Why the nav needs them at all** (RFP §6.3): ``assessment:group_grid``
    takes a group id and a teacher may hold several. The sidebar links to one
    so the item has a destination; the screen it lands on renders
    ``nav_groups`` as its own selector, so nothing is silently chosen and the
    teacher can switch. A teacher with no group gets ``None`` and no link,
    rather than one that 404s.

    Only the teacher shell draws that nav, so only a teacher pays for the
    query.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return {}

    shell = layout_for(user)
    context = {"default_layout": shell}

    if shell == TEACHER:
        from apps.tenants.selectors import assignable_groups

        groups = list(assignable_groups(user))
        context |= {
            "nav_group": groups[0] if groups else None,
            "nav_groups": groups,
        }

    return context
