"""``seed_demo`` — RFP §707.

The command is how anyone new gets a working system to look at, so a break
in it is a break in the first five minutes of the project. Run against the
test database, which is empty, because the command is not idempotent: it
invites teachers by a fixed username and a second run collides.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.assessment.models import Assessment, Term
from apps.children.models import Child
from apps.comms.models import Announcement
from apps.observations.models import Observation

# Every test here runs the whole seeding command — four children with photos,
# observations and assessments — so the file is 15 of the suite's slowest
# seconds. Marked slow as a group: `make test-fast` skips it, `make test`
# does not.
pytestmark = [pytest.mark.django_db, pytest.mark.slow]


@override_settings(DEBUG=True)
def test_seed_demo_produces_a_working_system():
    call_command("seed_demo", children=4)

    assert Child.objects.count() == 4
    # RFP §6.4 — a school year without terms is one in which nothing can be
    # assessed, so the seed has to produce them.
    assert Term.objects.count() == 4
    assert Observation.objects.exists()
    assert Assessment.objects.exists()
    # RFP §8.1 — one for everyone and one aimed at a group, so the parent
    # screen shows the targeting doing something.
    assert Announcement.objects.count() == 2

    # Every record is filed against an enrollment (spec section 4.2).
    assert not Observation.objects.filter(enrollment__isnull=True).exists()
    assert not Assessment.objects.filter(enrollment__isnull=True).exists()


@override_settings(DEBUG=True)
def test_seed_demo_can_be_run_twice():
    """A command that only works on an empty database is one nobody trusts.

    The first version invited teachers unconditionally and died on the
    username unique constraint the second time.

    This used to assert that a second run left *four* children — it tolerated
    the demo growing by a class every time anyone re-ran it, which is how a
    development database ends up with thirty-two children nobody asked for.
    ``--children`` now reads as "make sure there are this many", so a re-run
    tops up towards the number and otherwise leaves the data alone.
    """
    call_command("seed_demo", children=2)
    call_command("seed_demo", children=2)

    assert Child.objects.count() == 2      # topped up, not doubled
    assert Term.objects.count() == 4       # and no duplicate terms


@override_settings(DEBUG=True)
def test_seed_demo_tops_up_to_the_requested_number():
    call_command("seed_demo", children=2)
    call_command("seed_demo", children=5)

    assert Child.objects.count() == 5


@override_settings(DEBUG=True)
def test_seed_demo_does_not_repeat_a_childs_observations():
    """`create_observation` always creates, so a re-run would double them."""
    call_command("seed_demo", children=2)
    first = Observation.objects.count()
    call_command("seed_demo", children=2)

    assert Observation.objects.count() == first


@override_settings(DEBUG=True)
def test_the_demo_year_has_a_term_containing_today():
    """Otherwise §12.1, §6.3 and §6.4 all report "no term configured".

    That is not hypothetical: the seeded year ran to 31 May 2026, and from
    June onwards the dashboard showed no assessment progress while several
    hundred assessments sat in the table.
    """
    import datetime as dt

    call_command("seed_demo", children=2)
    today = dt.date.today()

    assert Term.objects.filter(starts_on__lte=today, ends_on__gte=today).exists()


@override_settings(DEBUG=False)
def test_seed_demo_refuses_to_run_in_production():
    """RFP §707 — it must not be possible to point this at real data."""
    with pytest.raises(CommandError):
        call_command("seed_demo")

    assert not Child.objects.exists()
