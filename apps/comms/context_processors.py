"""The unread badge — RFP §8.1 "шинэ мэдэгдлийн тоог харах".

A context processor rather than a value each view remembers to pass: the
badge lives in the layout, so every screen a guardian opens needs it, and
"every view must remember" is a rule that gets broken on the first new view.

Costs a few queries per request for guardians and none for anyone else.
"""

from .selectors import unread_count


def announcements(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return {}

    # Staff see the announcements they wrote; the badge is for families.
    if user.kindergarten_ids and _is_staff(user):
        return {}

    return {"unread_announcements": unread_count(user)}


def _is_staff(user) -> bool:
    from apps.accounts.models import Role

    return user.memberships.filter(
        is_active=True,
        role__in=[Role.TEACHER, Role.ADMIN, Role.SUPERADMIN],
    ).exists()
