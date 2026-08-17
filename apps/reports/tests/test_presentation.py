"""The report screens' presentation — RFP §10, §549.

The redesign touched two forms and a PDF stylesheet. What matters is that the
wire format did not move with the markup: the request view reads
``report_type``, ``term`` and a multi-valued ``sections``, and the waiting
screen's polling depends on two element ids and three data attributes. A
redesign that quietly broke any of those would look perfect in a screenshot
and produce no report at all.

Authorization is already covered by ``test_reports.py`` — who may request,
whose job it is, and who may fetch the finished file. This file does not
repeat it; it adds the one case that redesign could newly affect: that the
request screen offers nothing for a child the viewer cannot reach.
"""

import pytest
from django.urls import reverse

from apps.reports.models import ReportJob
from apps.reports.services import SECTIONS

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def request_url(child):
    return reverse("reports:request", args=[child.pk])


# ------------------------------------------------------- the form contract

def test_every_section_is_offered_with_its_backend_code(client, world):
    """`services.SECTIONS` is the source; the template must not fork it."""
    login(client, world["dulmaa"])

    body = client.get(request_url(world["bataa"])).content.decode()

    for code, label in SECTIONS:
        assert f'value="{code}"' in body, f"section {code} is not offered"
        assert label in body, f"section {code} has no label on screen"


def test_the_sections_field_is_still_multi_valued(client, world):
    """The view reads `request.POST.getlist("sections")`."""
    login(client, world["dulmaa"])

    body = client.get(request_url(world["bataa"])).content.decode()

    assert body.count('name="sections"') == len(SECTIONS)


def test_requesting_a_portfolio_queues_a_job(client, world):
    """End to end: the redesigned form still produces a ReportJob."""
    login(client, world["dulmaa"])

    response = client.post(request_url(world["bataa"]), {
        "report_type": "child_portfolio",
        "sections": ["basic", "about_me"],
    })

    job = ReportJob.objects.get(child=world["bataa"])
    assert response.status_code == 302
    assert response.url == reverse("reports:status",
                                   args=[world["bataa"].pk, job.pk])
    assert job.type == ReportJob.Type.CHILD_PORTFOLIO
    assert job.params["sections"] == ["basic", "about_me"]


def test_a_guardian_can_request_their_own_childs_report(client, world):
    """§10.1 — the family's printable copy is theirs to ask for."""
    login(client, world["bataa_mother"])

    response = client.post(request_url(world["bataa"]),
                           {"report_type": "child_portfolio"})

    assert response.status_code == 302
    assert ReportJob.objects.filter(
        child=world["bataa"], requested_by=world["bataa_mother"]
    ).exists()


def test_the_request_screen_names_the_child(client, world):
    """Reached from three screens; the subject is never left to memory."""
    login(client, world["dulmaa"])

    body = client.get(request_url(world["bataa"])).content.decode()

    assert world["bataa"].full_name in body


def test_a_child_the_viewer_cannot_reach_offers_nothing(client, world):
    """CLAUDE.md §4.1 — the redesign changed the markup, not the rules."""
    login(client, world["oyun"])

    assert client.get(request_url(world["bataa"])).status_code == 404


# ------------------------------------------------------- the waiting screen

def _job(world, **kwargs):
    return ReportJob.objects.create(
        kindergarten=world["naran"], child=world["bataa"],
        requested_by=world["dulmaa"], **kwargs,
    )


def test_the_waiting_screen_keeps_its_polling_contract(client, world):
    """The script reads three data attributes and writes to `#job-status`.

    Renaming any of them leaves a screen that renders and never updates.
    """
    job = _job(world, status=ReportJob.Status.QUEUED)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).content.decode()

    assert 'id="job"' in body
    assert 'id="job-status"' in body
    assert "data-progress-url" in body
    assert "data-download-url" in body
    assert "data-poll" in body
    assert reverse("reports:progress", args=[world["bataa"].pk, job.pk]) in body


@pytest.mark.parametrize("status,expected", [
    pytest.param(ReportJob.Status.QUEUED, "бэлдэж байна", id="queued"),
    pytest.param(ReportJob.Status.RUNNING, "бэлдэж байна", id="running"),
    pytest.param(ReportJob.Status.EXPIRED, "Хугацаа дууссан", id="expired"),
    pytest.param(ReportJob.Status.FAILED, "чадсангүй", id="failed"),
])
def test_each_job_state_says_what_happened(client, world, status, expected):
    """The four states are the ReportJob's own — no second state machine."""
    job = _job(world, status=status)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).content.decode()

    assert expected in body


def test_an_unfinished_job_polls_and_a_finished_one_does_not(client, world):
    """The script is only emitted while there is something to wait for."""
    login(client, world["dulmaa"])

    def status_body(job):
        url = reverse("reports:status", args=[world["bataa"].pk, job.pk])
        return client.get(url).content.decode()

    waiting = _job(world, status=ReportJob.Status.QUEUED)
    body = status_body(waiting)
    assert "data-progress-url" in body and "setTimeout" in body

    failed = _job(world, status=ReportJob.Status.FAILED,
                  error_message="Алдаа гарлаа")
    assert "setTimeout" not in status_body(failed)


def test_a_failed_job_shows_its_reason_and_a_retry(client, world):
    job = _job(world, status=ReportJob.Status.FAILED,
               error_message="Зураг уншиж чадсангүй")
    login(client, world["dulmaa"])

    body = client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).content.decode()

    assert "Зураг уншиж чадсангүй" in body
    assert reverse("reports:request", args=[world["bataa"].pk]) in body


def test_the_progress_bar_carries_an_accessible_value(client, world):
    """§15 — status is never colour or motion alone."""
    job = _job(world, status=ReportJob.Status.RUNNING, progress_percent=40)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).content.decode()

    assert 'role="progressbar"' in body
    assert 'aria-valuenow="40"' in body
