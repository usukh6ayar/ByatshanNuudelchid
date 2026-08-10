"""Shared fixtures.

The scenario below is the one the authorization rules must get right, so
every permission test builds on it:

    Kindergarten "Naran"           Kindergarten "Och"
      └ Sunflower group              └ Petal group
          ├ teacher Dulmaa               └ teacher Oyun
          ├ child Bataa
          └ child Saraa
"""

import datetime as dt

import pytest

from apps.accounts.models import Membership, Role, User
from apps.assessment.defaults import install as install_system_defaults
from apps.children.models import Child, Enrollment, Guardianship
from apps.tenants.models import Group, GroupTeacher, Kindergarten, SchoolYear


@pytest.fixture(autouse=True)
def local_cache(settings):
    """Keep the test suite out of the shared Redis.

    Production caches the §12.2 dashboard in Redis so the beat worker and
    the web process share it. Tests do not need that, and pointing them at
    a real Redis would let one test's cached figures leak into the next —
    which is exactly the bug a dashboard test is looking for.
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test",
        },
    }
    from django.core.cache import cache

    cache.clear()


@pytest.fixture(autouse=True)
def in_memory_storage(settings):
    """Keep uploads out of MinIO and out of the developer's disk.

    Development points ``default_storage`` at the MinIO container so the
    signed-URL path is exercised for real (``config/settings/dev.py``). A
    test suite that did the same would need the container running, would
    leave objects behind, and would be slow for no gain — the thing worth
    testing here is the pipeline, not S3's API.

    ``InMemoryStorage`` cannot sign a URL, which is deliberate: it puts the
    serving view down its streaming branch, so both halves of spec section
    7.1 are covered by the suite rather than only the one production uses.
    """
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture(autouse=True)
def system_defaults(db):
    """Reinstall the §5.2, §6.1 and §6.2 configuration before every test.

    The data migrations create these rows, but a test marked
    ``django_db(transaction=True)`` — the authentication tests are, because
    the §3.1 lockout has to survive a rollback — flushes every table at
    teardown and takes migration-created data with it. Every test collected
    after one of those would then find an empty configuration and fail for a
    reason that has nothing to do with what it is testing.

    Autouse rather than opt-in: which tests need it is not obvious from
    reading them, and a fixture you have to remember is a fixture that gets
    forgotten.
    """
    install_system_defaults()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(**kwargs):
        counter["n"] += 1
        kwargs.setdefault("username", f"user{counter['n']}")
        return User.objects.create_user(password="test-password-1234", **kwargs)

    return _make


@pytest.fixture
def make_kindergarten(db):
    def _make(name):
        kg = Kindergarten.objects.create(name=name)
        year = SchoolYear.objects.create(
            kindergarten=kg,
            name="2025-2026",
            starts_on=dt.date(2025, 9, 1),
            ends_on=dt.date(2026, 5, 31),
            is_current=True,
        )
        return kg, year

    return _make


@pytest.fixture
def make_group(db):
    def _make(kindergarten, school_year, name):
        return Group.objects.create(
            kindergarten=kindergarten, school_year=school_year, name=name
        )

    return _make


@pytest.fixture
def make_teacher(db, make_user):
    def _make(kindergarten, group=None, **kwargs):
        user = make_user(**kwargs)
        membership = Membership.objects.create(
            user=user, kindergarten=kindergarten, role=Role.TEACHER
        )
        if group is not None:
            GroupTeacher.objects.create(
                kindergarten=kindergarten,
                group=group,
                teacher_membership=membership,
            )
        return user

    return _make


@pytest.fixture
def make_admin(db, make_user):
    def _make(kindergarten=None, role=Role.ADMIN, **kwargs):
        user = make_user(**kwargs)
        Membership.objects.create(user=user, kindergarten=kindergarten, role=role)
        return user

    return _make


@pytest.fixture
def make_child(db):
    counter = {"n": 0}

    def _make(kindergarten, group=None, school_year=None, first_name="Хүүхэд"):
        counter["n"] += 1
        child = Child.objects.create(
            kindergarten=kindergarten,
            last_name="Овог",
            first_name=first_name,
            national_id=f"AA{counter['n']:08d}",
            sex=Child.Sex.MALE,
            date_of_birth=dt.date(2021, 4, 15),
        )
        if group is not None:
            Enrollment.objects.create(
                kindergarten=kindergarten,
                child=child,
                group=group,
                school_year=school_year or group.school_year,
                started_on=dt.date(2025, 9, 1),
            )
        return child

    return _make


@pytest.fixture
def make_guardian(db, make_user):
    def _make(child, kindergarten, can_view=True, **kwargs):
        user = make_user(**kwargs)
        Membership.objects.create(
            user=user, kindergarten=kindergarten, role=Role.GUARDIAN
        )
        Guardianship.objects.create(
            kindergarten=kindergarten,
            child=child,
            guardian_user=user,
            relation=Guardianship.Relation.MOTHER,
            can_view=can_view,
        )
        return user

    return _make


@pytest.fixture
def world(make_kindergarten, make_group, make_teacher, make_child, make_guardian):
    """The two-kindergarten scenario described in this module's docstring."""
    naran, naran_year = make_kindergarten("Наран")
    och, och_year = make_kindergarten("Оч")

    sunflower = make_group(naran, naran_year, "Наранцэцэг")
    petal = make_group(och, och_year, "Дэлбээ")

    bataa = make_child(naran, sunflower, first_name="Батаа")
    saraa = make_child(naran, sunflower, first_name="Сараа")

    return {
        "naran": naran, "naran_year": naran_year, "sunflower": sunflower,
        "och": och, "och_year": och_year, "petal": petal,
        "bataa": bataa, "saraa": saraa,
        "dulmaa": make_teacher(naran, sunflower, username="dulmaa"),
        "oyun": make_teacher(och, petal, username="oyun"),
        "bataa_mother": make_guardian(bataa, naran, username="bataa_mother"),
    }


@pytest.fixture
def naran_admin_user(world, make_admin):
    """A director of the Naran kindergarten. Used as ``actor`` in services."""
    return make_admin(world["naran"], username="naran_director")
