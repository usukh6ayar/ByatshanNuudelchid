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

pytestmark = pytest.mark.django_db


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
    """
    call_command("seed_demo", children=2)
    call_command("seed_demo", children=2)

    assert Child.objects.count() == 4      # two more, not a crash
    assert Term.objects.count() == 4       # and no duplicate terms


@override_settings(DEBUG=False)
def test_seed_demo_refuses_to_run_in_production():
    """RFP §707 — it must not be possible to point this at real data."""
    with pytest.raises(CommandError):
        call_command("seed_demo")

    assert not Child.objects.exists()
