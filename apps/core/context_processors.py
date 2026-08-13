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

from apps.core.layouts import layout_for


def layout(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return {}
    return {"default_layout": layout_for(user)}
