"""Portfolio writes — RFP §4.1, §4.2, §4.3.

Both a guardian and a teacher may edit a child's portfolio: §2.3 gives
guardians "Миний тухай"-г оруулах, засах, and §4.3 keeps a note from each
side. Which fields each may touch is decided here, not in a view.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core.permissions import can_access_child, is_guardian_of
from apps.core.services import save_record

from .models import AboutMe, BirthdayNote, ChildAgeProfile

__all__ = [
    "editable_age_profile_fields",
    "save_about_me",
    "save_age_profile",
    "save_birthday_note",
]

ABOUT_ME_FIELDS = {
    "introduction", "name_meaning", "memorable_sayings", "dream",
    "distinguishing_traits", "height_cm", "weight_kg", "recorded_on",
}

SHARED_AGE_FIELDS = {
    "favorite_color", "favorite_food", "favorite_toy", "favorite_book",
    "favorite_song", "favorite_story", "favorite_movie", "favorite_clothes",
    "favorite_activity", "personality", "emotional_traits", "family_members",
    "learning_interest", "new_skills",
}


def editable_age_profile_fields(user, child) -> set[str]:
    """Which age-profile fields this user may write.

    §4.3 lists эцэг эхийн тэмдэглэл and багшийн тэмдэглэл separately. They
    are two voices in the record, so neither side may overwrite the other's.
    """
    fields = set(SHARED_AGE_FIELDS)
    if is_guardian_of(user, child):
        fields.add("parent_note")
    else:
        fields.add("teacher_note")
    return fields


def _guard(user, child):
    """Editing is a form of access, so it goes through the same check."""
    if not can_access_child(user, child):
        raise PermissionDenied


@transaction.atomic
def save_about_me(*, actor, child, request=None, **fields) -> AboutMe:
    """RFP §4.1. Creates the row on first save."""
    _guard(actor, child)

    unknown = set(fields) - ABOUT_ME_FIELDS
    if unknown:
        raise ValidationError(
            f"Засах боломжгүй талбар: {', '.join(sorted(unknown))}"
        )

    about = AboutMe.all_objects.filter(child=child).first()
    created = about is None
    if created:
        about = AboutMe(child=child, kindergarten_id=child.kindergarten_id)
    elif about.deleted_at is not None:
        about.deleted_at = None
        about.deleted_by = None

    for name, value in fields.items():
        setattr(about, name, value)

    return save_record(actor=actor, obj=about, created=created, request=request)


@transaction.atomic
def save_age_profile(*, actor, child, age, school_year=None, request=None,
                     **fields) -> ChildAgeProfile:
    """RFP §4.3 — the page for one age."""
    _guard(actor, child)

    if age not in ChildAgeProfile.Age.values:
        raise ValidationError("Нас 2–5 хооронд байх ёстой.")

    allowed = editable_age_profile_fields(actor, child)
    rejected = set(fields) - allowed
    if rejected:
        # Reached only by a crafted request: the form never renders the
        # other side's note field.
        raise ValidationError(
            f"Энэ талбарыг засах эрхгүй: {', '.join(sorted(rejected))}"
        )

    profile = ChildAgeProfile.objects.filter(child=child, age=age).first()
    created = profile is None
    if created:
        profile = ChildAgeProfile(
            child=child, age=age, kindergarten_id=child.kindergarten_id
        )
    if school_year is not None:
        profile.school_year = school_year

    for name, value in fields.items():
        setattr(profile, name, value)

    return save_record(actor=actor, obj=profile, created=created,
                       request=request)


@transaction.atomic
def save_birthday_note(*, actor, child, age, note, request=None) -> BirthdayNote:
    """RFP §4.2."""
    _guard(actor, child)

    entry = BirthdayNote.objects.filter(child=child, age=age).first()
    created = entry is None
    if created:
        entry = BirthdayNote(
            child=child, age=age, kindergarten_id=child.kindergarten_id
        )
    entry.note = note

    return save_record(actor=actor, obj=entry, created=created, request=request)
