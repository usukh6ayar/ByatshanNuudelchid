"""Report generation — RFP §10, §549, and the §21 rules that apply to a PDF.

A generated portfolio is the single most sensitive artifact the system
produces: one file holding everything recorded about one child. Most of what
follows is about who can ask for one and what ends up inside it.
"""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from apps.assessment import selectors as assessment_selectors
from apps.assessment import services as assessment_services
from apps.media.models import MediaFile
from apps.observations.models import Observation, ObservationType
from apps.observations.services import create_observation, review_observation
from apps.portfolio.services import save_about_me
from apps.reports import services
from apps.reports.builder import build_context
from apps.reports.models import ReportJob
from apps.reports.tasks import generate_report

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def request_url(child):
    return reverse("reports:request", args=[child.pk])


@pytest.fixture
def filled(world):
    """A child with something in every section, so the PDF is not blank."""
    save_about_me(actor=world["dulmaa"], child=world["bataa"],
                  introduction="Хөгжилтэй, сониуч хүүхэд.",
                  dream="Нисгэгч болно.")

    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
        activity_name="Блокоор барих",
        child_did="Найзтайгаа ээлжлэн цамхаг барив.",
        child_said="«Чи эхлээд тавь.»",
    )

    terms = assessment_services.ensure_default_terms(
        actor=world["dulmaa"], school_year=world["naran_year"]
    )
    assessment_services.save_assessment(
        actor=world["dulmaa"], child=world["bataa"],
        domain=assessment_selectors.domains_for(world["naran"].pk).first(),
        term=terms[0],
        level=assessment_selectors.levels_for(world["naran"].pk).first(),
        comment="Тогтвортой ахиц.",
    )
    return world


# ------------------------------------------------------------------ §21
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client.

def test_teacher_from_another_group_gets_404(client, world, make_teacher,
                                             make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(request_url(world["bataa"])).status_code == 404


def test_guardian_of_another_child_gets_404(client, world):
    login(client, world["bataa_mother"])

    assert client.get(request_url(world["saraa"])).status_code == 404


def test_user_from_another_kindergarten_gets_404(client, world):
    login(client, world["oyun"])

    assert client.get(request_url(world["bataa"])).status_code == 404
    assert client.post(request_url(world["bataa"]), {}).status_code == 404
    assert not ReportJob.objects.exists()


def test_a_job_belongs_to_whoever_asked_for_it(client, world):
    """Not to anyone who may see the child.

    The PDF was assembled from what the requester could read, so handing a
    teacher's copy to a guardian would hand over observations the teacher
    marked invisible to families.
    """
    login(client, world["dulmaa"])
    client.post(request_url(world["bataa"]), {"sections": ["basic"]})
    job = ReportJob.objects.get()

    login(client, world["bataa_mother"])

    assert client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).status_code == 404
    assert client.get(
        reverse("reports:download", args=[world["bataa"].pk, job.pk])
    ).status_code == 404


def test_a_service_call_for_an_unreachable_child_is_refused(world):
    with pytest.raises(PermissionDenied):
        services.request_child_portfolio(actor=world["oyun"],
                                         child=world["bataa"])


# ------------------------------------------------------------------ §549

def test_the_request_returns_without_rendering(client, world, filled):
    """§549 — "тайлан үүсгэх үед систем гацахгүй байх".

    Celery is *not* eager here, so nothing renders. The response still has
    to arrive and the job still has to be queued.
    """
    login(client, world["dulmaa"])

    response = client.post(request_url(world["bataa"]),
                           {"sections": ["basic", "about_me"]})

    assert response.status_code == 302
    job = ReportJob.objects.get()
    assert job.status == ReportJob.Status.QUEUED
    assert job.result_media is None


def test_the_worker_is_started_only_after_the_commit(client, world, filled,
                                                     django_capture_on_commit_callbacks):
    """CLAUDE.md §6.1.

    ``ATOMIC_REQUESTS`` wraps the whole request. A bare ``.delay()`` can
    reach a worker before the row it needs is committed, and the worker then
    finds nothing.
    """
    login(client, world["dulmaa"])

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        client.post(request_url(world["bataa"]), {"sections": ["basic"]})

    assert len(callbacks) == 1
    assert ReportJob.objects.get().status == ReportJob.Status.QUEUED


# ------------------------------------------------------------------ §10.3

def test_the_pdf_renders_with_cyrillic_and_page_numbers(world, filled):
    """RFP §10.3 — the whole point of the Day 1 spike, now on real data."""
    import pypdf

    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)

    job.refresh_from_db()
    assert job.status == ReportJob.Status.DONE
    assert job.page_count >= 2
    assert job.file_size > 0

    from apps.media import services as media_services

    payload = media_services.read_bytes(job.result_media)
    reader = pypdf.PdfReader(__import__("io").BytesIO(payload))
    assert len(reader.pages) == job.page_count

    text = "\n".join(page.extract_text() for page in reader.pages)
    assert world["bataa"].full_name in text
    assert "Хүүхдийн хөгжлийн цахим хувийн хавтас" in text
    # Ө and Ү exist in Mongolian but not in Russian — a font that passes a
    # naive Cyrillic check can still be missing them.
    assert "Хуудас" in text
    assert "Өрнийн орд" in text or "хөгжлийн" in text.lower()

    # The document goes to a family. Nothing addressed to whoever maintains
    # the template belongs in it — and this is not hypothetical: the header
    # comment in child_portfolio.html was written as `{# ... #}` across
    # several lines, which Django does not treat as a comment, so fourteen
    # lines of English notes were printed on page one of every portfolio
    # until 2026-08-10. The page-count and Cyrillic assertions above were
    # both satisfied the whole time; only reading the page would have shown
    # it. apps/core/tests/test_templates.py guards the source, this guards
    # the artefact the client actually receives.
    for leak in ("RFP", "{#", "CLAUDE.md", "builder.py"):
        assert leak not in text, f"internal commentary reached the PDF: {leak!r}"


def test_the_result_is_stored_as_a_protected_file(world, filled):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)
    job.refresh_from_db()

    media = job.result_media
    assert media.mime_type == "application/pdf"
    assert media.purpose == MediaFile.Purpose.REPORT
    assert media.child == world["bataa"]
    # RFP §4.4 — the storage path is a random UUID, not the child's name.
    assert world["bataa"].last_name not in media.storage_key


def test_the_download_goes_through_the_media_permission_check(client, world,
                                                              filled):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)
    login(client, world["dulmaa"])

    response = client.get(
        reverse("reports:download", args=[world["bataa"].pk, job.pk])
    )

    assert response.status_code == 302
    served = client.get(response["Location"])
    assert served.status_code == 200
    assert served["Content-Type"] == "application/pdf"


def test_an_outsider_cannot_fetch_the_finished_pdf(client, world, filled):
    """RFP §21.10 — the file is the most sensitive artifact in the system."""
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)
    job.refresh_from_db()
    login(client, world["oyun"])

    url = reverse("media:serve", args=[job.result_media.public_id, "full"])
    assert client.get(url).status_code == 404


# --------------------------------------------------------- what goes inside

def test_a_guardians_copy_omits_what_they_may_not_read(world):
    """The report is built from the *requester's* view of the child."""
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    hidden = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 2), visible_to_parents=False,
        activity_name="Зөвхөн багшид",
    )
    shown = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 3), visible_to_parents=True,
        activity_name="Эцэг эхэд харагдана",
    )

    parent_context = build_context(viewer=world["bataa_mother"],
                                   child=world["bataa"],
                                   sections=["observations"])
    teacher_context = build_context(viewer=world["dulmaa"],
                                    child=world["bataa"],
                                    sections=["observations"])

    assert hidden not in parent_context["observations"]
    assert shown in parent_context["observations"]
    assert hidden in teacher_context["observations"]


def test_an_observation_excluded_from_the_report_stays_out(world):
    """RFP §5.4 — "нэгдсэн тайланд оруулах эсэхийг шийдэх"."""
    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    excluded = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 2), include_in_report=False,
        activity_name="Тайланд орохгүй",
    )

    context = build_context(viewer=world["dulmaa"], child=world["bataa"],
                            sections=["observations"])

    assert excluded not in context["observations"]


def test_an_unreviewed_parent_note_stays_out(world):
    """§5.4 — the teacher decides, and a pending note has not been decided."""
    parent_type = ObservationType.objects.get(kindergarten=None, code="parent")
    pending = create_observation(
        actor=world["bataa_mother"], child=world["bataa"], type=parent_type,
        source=Observation.Source.PARENT, observed_on=dt.date(2025, 10, 1),
        situation="Гэртээ ном уншив.",
    )

    context = build_context(viewer=world["dulmaa"], child=world["bataa"],
                            sections=["parent_observations"])
    assert pending not in context["parent_observations"]

    review_observation(actor=world["dulmaa"], observation=pending,
                       status=Observation.ReviewStatus.APPROVED)

    context = build_context(viewer=world["dulmaa"], child=world["bataa"],
                            sections=["parent_observations"])
    assert pending in context["parent_observations"]


def test_unpublished_assessments_stay_out_of_the_familys_copy(world, filled):
    """§2.3 — a guardian sees "багшийн зөвшөөрсөн" assessments only."""
    context = build_context(viewer=world["bataa_mother"], child=world["bataa"],
                            sections=["assessments"])

    cells = [cell for row in context["assessment_matrix"]["rows"]
             for cell in row["cells"]]
    assert all(cell is None for cell in cells)


def test_only_the_requested_sections_appear(world, filled):
    context = build_context(viewer=world["dulmaa"], child=world["bataa"],
                            sections=["about_me"])

    assert "about" in context
    assert "observations" not in context
    assert "assessment_matrix" not in context


def test_sections_keep_their_declared_order(world):
    """§10.1's order, not the order the checkboxes were posted."""
    job = services.request_child_portfolio(
        actor=world["dulmaa"], child=world["bataa"],
        sections=["assessments", "basic", "about_me"],
    )

    assert job.params["sections"] == ["basic", "about_me", "assessments"]


def test_no_sections_means_all_of_them(world):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])

    assert job.params["sections"] == services.DEFAULT_SECTIONS


# ------------------------------------------------------------------ failure

def test_a_failed_render_leaves_a_reason_on_the_row(world, monkeypatch):
    """The person waiting cannot read the worker's log."""
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])

    monkeypatch.setattr(
        "apps.reports.tasks.render_pdf_with_pages",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("шрифт олдсонгүй")),
    )
    generate_report(job.pk)

    job.refresh_from_db()
    assert job.status == ReportJob.Status.FAILED
    assert "шрифт олдсонгүй" in job.error_message


def test_the_status_screen_shows_the_failure(client, world, monkeypatch):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    monkeypatch.setattr(
        "apps.reports.tasks.render_pdf_with_pages",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("алдаа гарлаа")),
    )
    generate_report(job.pk)
    login(client, world["dulmaa"])

    body = client.get(
        reverse("reports:status", args=[world["bataa"].pk, job.pk])
    ).content.decode()

    assert "алдаа гарлаа" in body


def test_a_vanished_job_does_not_crash_the_worker(world):
    assert generate_report(999999) == "missing"


def test_a_finished_job_is_not_rendered_twice(world, filled):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)
    job.refresh_from_db()
    first = job.result_media_id

    generate_report(job.pk)

    job.refresh_from_db()
    assert job.result_media_id == first


# ------------------------------------------------------------------ retention

def test_expired_reports_stop_being_downloadable(world, filled):
    """Spec section 8 — a child's complete record does not sit in a bucket
    indefinitely, and regenerating costs one click."""
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)
    job.refresh_from_db()
    media_id = job.result_media_id

    ReportJob.objects.filter(pk=job.pk).update(
        expires_at=timezone.now() - dt.timedelta(days=1)
    )
    assert services.expire_old_reports() == 1

    job.refresh_from_db()
    assert job.status == ReportJob.Status.EXPIRED
    assert not job.is_downloadable
    assert not MediaFile.objects.filter(pk=media_id).exists()


def test_a_live_report_is_left_alone(world, filled):
    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    generate_report(job.pk)

    assert services.expire_old_reports() == 0

    job.refresh_from_db()
    assert job.status == ReportJob.Status.DONE


# ------------------------------------------------------------------ screens

def test_the_screens_render(client, world, filled):
    login(client, world["dulmaa"])

    assert client.get(request_url(world["bataa"])).status_code == 200

    job = services.request_child_portfolio(actor=world["dulmaa"],
                                           child=world["bataa"])
    status = reverse("reports:status", args=[world["bataa"].pk, job.pk])
    assert client.get(status).status_code == 200

    progress = client.get(
        reverse("reports:progress", args=[world["bataa"].pk, job.pk])
    )
    assert progress.status_code == 200
    assert progress.json()["status"] == "queued"
    assert progress.json()["finished"] is False


def test_a_guardian_may_request_their_own_childs_portfolio(client, world,
                                                           filled):
    """RFP §2.3 — "PDF хэлбэрээр харах, татах"."""
    login(client, world["bataa_mother"])

    response = client.post(request_url(world["bataa"]), {"sections": ["basic"]})

    assert response.status_code == 302
    assert ReportJob.objects.get().requested_by == world["bataa_mother"]
