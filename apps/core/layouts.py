"""Which shell a screen renders inside — RFP §13.

§13 asks for three: one for teachers, one for guardians, one for
administrators. Deciding that per view meant nine copies of the same
expression and, until 2026-08-13, a director seeing the teacher's menu
everywhere except the dashboard — "Хянах ажиглалт" for groups they do not
teach, and no way to reach the kindergartens they administer.

This is presentation, not authorization. It answers "what chrome goes
around this page", never "may this user see it" — that stays in
``permissions.py`` (CLAUDE.md §1.1). A wrong answer here shows the wrong
menu; a wrong answer there leaks a child's records.
"""

from apps.accounts.models import Role

__all__ = ["layout_for", "ADMIN", "TEACHER", "PARENT"]

ADMIN = "base_admin.html"
TEACHER = "base_teacher.html"
PARENT = "base_parent.html"

ADMIN_ROLES = frozenset({Role.ADMIN, Role.SUPERADMIN})


def layout_for(user, *, guardian_view: bool = False) -> str:
    """The base template for ``user``.

    ``guardian_view`` is for the screens a family and a teacher both reach —
    the portfolio, the observations, the assessment record. There the caller
    has already worked out which role the *request* is being made in, and a
    teacher reading their own child's portfolio should see it as a parent
    does.

    Roles are checked administrator-first: someone who is both a director
    and a teacher gets the administrator's menu, because it is the one that
    reaches the whole kindergarten.
    """
    if guardian_view:
        return PARENT

    if user is None or not user.is_authenticated:
        return PARENT

    roles = set(
        user.memberships.filter(is_active=True).values_list("role", flat=True)
    )
    if roles & ADMIN_ROLES:
        return ADMIN
    if Role.TEACHER in roles:
        return TEACHER
    return PARENT
