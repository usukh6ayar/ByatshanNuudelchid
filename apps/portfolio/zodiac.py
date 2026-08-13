"""Zodiac sign and Mongolian year animal — RFP §4.2.

§206 says these may be computed from the date of birth, so they are not
stored. A stored copy goes stale the moment someone corrects a birth date.
"""

import datetime as dt

# The 12-year cycle, aligned so that 2020 is the year of the mouse.
YEAR_ANIMALS = [
    "Хулгана", "Үхэр", "Бар", "Туулай", "Луу", "Могой",
    "Морь", "Хонь", "Бич", "Тахиа", "Нохой", "Гахай",
]

# (month, day) is the first day of each sign.
ZODIAC_SIGNS = [
    ((1, 20), "Хумх"),
    ((2, 19), "Загас"),
    ((3, 21), "Хонь"),
    ((4, 20), "Үхэр"),
    ((5, 21), "Ихэр"),
    ((6, 21), "Мэлхий"),
    ((7, 23), "Арслан"),
    ((8, 23), "Охин"),
    ((9, 23), "Жинлүүр"),
    ((10, 23), "Хилэнц"),
    ((11, 22), "Нум"),
    ((12, 22), "Матар"),
]


def year_animal(date_of_birth: dt.date) -> str:
    """The Mongolian year animal.

    ⚠ Uses the calendar year. The lunar new year (Цагаан сар) falls in
    January or February, so a child born before it belongs to the previous
    animal. Getting that exactly right needs a lunar calendar table; until
    one is added, January and early-February birthdays may be off by one.
    """
    return YEAR_ANIMALS[(date_of_birth.year - 2020) % 12]


def zodiac_sign(date_of_birth: dt.date) -> str:
    """The Western zodiac sign."""
    key = (date_of_birth.month, date_of_birth.day)
    sign = ZODIAC_SIGNS[-1][1]          # Capricorn wraps the year end
    for start, name in ZODIAC_SIGNS:
        if key >= start:
            sign = name
    return sign


def age_on(date_of_birth: dt.date, on: dt.date | None = None) -> int:
    """Completed years of age."""
    on = on or dt.date.today()
    return on.year - date_of_birth.year - (
        (on.month, on.day) < (date_of_birth.month, date_of_birth.day)
    )
