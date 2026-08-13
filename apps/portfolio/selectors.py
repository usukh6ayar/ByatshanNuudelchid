"""Portfolio reads — RFP §4.1, §4.2, §4.3."""

from .models import AboutMe, BirthdayNote, ChildAgeProfile
from .zodiac import age_on, year_animal, zodiac_sign

AGES = [2, 3, 4, 5]


def about_me(child) -> AboutMe | None:
    return AboutMe.objects.filter(child=child).first()


def age_profiles(child) -> dict[int, ChildAgeProfile | None]:
    """Every age from 2 to 5, whether or not a page exists yet.

    Returning the gaps as ``None`` lets the template show all four tabs, so
    an empty page reads as "not filled in" rather than "does not exist".
    """
    existing = {p.age: p for p in ChildAgeProfile.objects.filter(child=child)}
    return {age: existing.get(age) for age in AGES}


def age_profile(child, age) -> ChildAgeProfile | None:
    return ChildAgeProfile.objects.filter(child=child, age=age).first()


def birthdays(child) -> list[dict]:
    """RFP §4.2 — one entry per birthday the child has had.

    Sign and animal are computed, never stored (§206).
    """
    notes = {n.age: n for n in BirthdayNote.objects.filter(child=child)}
    current = age_on(child.date_of_birth)

    return [
        {
            "age": age,
            "date": child.date_of_birth.replace(
                year=child.date_of_birth.year + age
            ),
            "note": notes.get(age),
        }
        for age in range(1, current + 1)
    ]


def birth_facts(child) -> dict:
    """RFP §4.2 — the header of the birthday section."""
    return {
        "date_of_birth": child.date_of_birth,
        "age": age_on(child.date_of_birth),
        "zodiac_sign": zodiac_sign(child.date_of_birth),
        "year_animal": year_animal(child.date_of_birth),
    }


def completeness(child) -> dict:
    """How much of the portfolio is filled in.

    Drives the progress hint on the portfolio screen, and later the
    "missing information" tile on the teacher dashboard (§12.1).
    """
    about = about_me(child)
    filled_ages = sum(1 for p in age_profiles(child).values() if p is not None)
    return {
        "about_me": about is not None,
        "ages_filled": filled_ages,
        "ages_total": len(AGES),
    }
