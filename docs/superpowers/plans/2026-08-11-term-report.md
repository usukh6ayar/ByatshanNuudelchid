# Term Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build RFP §6.4's narrative term report and §10.2's term-report PDF, so acceptance criterion §21.7 ("Улирлын болон нэгдсэн PDF тайлан зөв үүсдэг байх") passes.

**Architecture:** A new `TermReport` table in `apps/assessment/` holds four narrative fields per child per term, alongside the existing per-domain `Assessment` rows. Finalizing a report also publishes that term's assessments, through one service that calls the existing `publish_term` rather than reimplementing it. A second `ReportJob.Type` renders it as a PDF through the machinery the portfolio already uses.

**Tech Stack:** Django 5, PostgreSQL, Celery, WeasyPrint, pytest. Everything runs in Docker: prefix commands with `docker compose exec -T web`.

---

## Before you start

Read these, in this order:

1. `CLAUDE.md` — the mandatory rules. §1.1 (authorization in one place), §2.1 (logic in services, not views), §3.3 (no hard deletes), §4.1 (three authorization tests per view), §5 (all UI text in Mongolian).
2. `docs/superpowers/specs/2026-08-11-term-report-design.md` — the design this plan implements.
3. `apps/assessment/services.py` — you will be adding to it. Note `_guard`, `assert_writable`, `_check_term`, and how `save_assessment` is shaped. Your new functions match that shape.

**Language:** code, comments and commit messages in English. Every string a user sees is in Mongolian. This is RFP §611 and it is not negotiable.

**Commands:**

```bash
docker compose exec -T web pytest apps/assessment/ -q     # one app
docker compose exec -T web pytest -q                      # everything
docker compose exec -T web ruff check .                   # lint
```

The full suite takes about six minutes and currently reports **630 passed**. Run the single test you are working on while iterating; run the app's suite before each commit.

**Lint is part of green.** `ruff` fails on an import that nothing uses yet, so each task adds only the imports its own code needs — do not import ahead for a later task. Tasks 2–5 all append to `apps/assessment/tests/test_term_report.py`, and each says which imports to add to its top when it needs them.

---

## File structure

| File | Responsibility |
|---|---|
| `apps/assessment/models.py` | `TermReport` — data only, no logic (CLAUDE.md §3.1) |
| `apps/assessment/migrations/0004_termreport.py` | Generated, then read by hand (§3.4) |
| `apps/assessment/services.py` | `save_term_report`, `finalize_term`, `reopen_term` — every write |
| `apps/assessment/selectors.py` | `term_report`, `term_reports_for` — every read |
| `apps/assessment/views.py` | `term_report` view; `publish` removed |
| `apps/assessment/urls.py` | One route added, one removed |
| `apps/assessment/admin.py` | `TermReportAdmin` via `TenantScopedAdmin` (§2.4) |
| `templates/assessment/term_report.html` | The teacher's four textareas |
| `templates/assessment/child.html` | Per-term links; publish form removed |
| `apps/reports/models.py` | `Type.TERM_REPORT` |
| `apps/reports/services.py` | `request_term_report` |
| `apps/reports/builder.py` | `build_term_report_context` |
| `apps/reports/tasks.py` | `TEMPLATES` entry, `_render` branch, `_filename` branch |
| `templates/reports/term_report.html` | The PDF |
| `templates/reports/request.html` | Report-type choice |
| `apps/assessment/tests/test_term_report.py` | New |

Tasks 1–4 build the model and services. Task 5 is the screen. Tasks 6–8 are the PDF. Task 9 updates the docs. Each task ends green and committed.

---

## Task 1: The `TermReport` model

**Files:**
- Modify: `apps/assessment/models.py` (append at end of file)
- Create: `apps/assessment/migrations/0004_termreport.py` (generated)
- Create: `apps/assessment/tests/test_term_report.py`

- [ ] **Step 1: Write the failing test**

Create `apps/assessment/tests/test_term_report.py`:

```python
"""The narrative term report — RFP §6.4, §10.2, and the §21 rules."""

import pytest
from django.db import IntegrityError, transaction

from apps.assessment import selectors, services
from apps.assessment.models import TermReport

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


@pytest.fixture
def terms(world, naran_admin_user):
    return services.ensure_default_terms(actor=naran_admin_user,
                                         school_year=world["naran_year"])


@pytest.fixture
def term(terms):
    return terms[0]


@pytest.fixture
def domain(world):
    return selectors.domains_for(world["naran"].pk).first()


@pytest.fixture
def level(world):
    return selectors.levels_for(world["naran"].pk).first()


def test_a_term_report_carries_the_four_narrative_fields(world, term):
    """RFP §6.4's list, minus the per-domain comment Assessment already holds."""
    from apps.children.services import current_enrollment

    enrollment = current_enrollment(world["bataa"])
    report = TermReport.objects.create(
        kindergarten=world["naran"],
        child=world["bataa"],
        enrollment=enrollment,
        term=term,
        strengths="Гүйлт сайн",
        needs_support="Тэнцвэр алдах нь ажиглагддаг",
        next_goals="Тэнцвэрийн дасгал тогтмол хийх",
        advice_for_parents="Гэртээ тэнцвэрийн дасгал тоглоно уу",
    )

    assert report.status == TermReport.Status.DRAFT
    assert report.finalized_at is None
    assert report.deleted_at is None
```

- [ ] **Step 2: Run it and watch it fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `ImportError: cannot import name 'TermReport'`.

- [ ] **Step 3: Add the model**

Append to `apps/assessment/models.py`:

```python
class TermReport(TenantScopedModel):
    """RFP §6.4's narrative report — one per child per term.

    The per-domain levels live in ``Assessment``; this is the wrapper a
    teacher writes once the term's grid is filled in. There is deliberately
    no general ``teacher_comment`` here: ``Assessment.comment`` already
    holds the teacher's note for each domain, and the approved mockup shows
    it there, under the domain it belongs to. A second comment box would
    leave the teacher guessing which one the family reads.

    ``enrollment`` is part of the uniqueness constraint for the same reason
    ``Assessment`` carries it: after a transfer the previous kindergarten's
    report stays attached to the enrollment it was written under, so
    ``visible_kindergartens()`` keeps showing it to its author and to nobody
    else (CLAUDE.md §1.2).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Ноорог"
        FINAL = "final", "Дууссан"

    child = models.ForeignKey("children.Child", on_delete=models.CASCADE,
                              related_name="term_reports")
    enrollment = models.ForeignKey("children.Enrollment",
                                   on_delete=models.PROTECT,
                                   related_name="term_reports")
    term = models.ForeignKey(Term, on_delete=models.PROTECT,
                             related_name="reports", verbose_name="улирал")

    strengths = models.TextField("давуу тал", blank=True)
    needs_support = models.TextField("дэмжих шаардлагатай чадвар", blank=True)
    next_goals = models.TextField("дараагийн улирлын зорилго", blank=True)
    advice_for_parents = models.TextField("эцэг эхэд өгөх зөвлөмж", blank=True)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                               blank=True, on_delete=models.SET_NULL,
                               related_name="+")
    status = models.CharField("төлөв", max_length=10, choices=Status.choices,
                              default=Status.DRAFT, db_index=True)
    # Not auto_now: §6.4 wants "тайлан үүсгэсэн огноо", the moment the
    # teacher declared it done. ``updated_at`` moves on every save and would
    # report a typo fix as a freshly written report.
    finalized_at = models.DateTimeField("дуусгасан огноо", null=True,
                                        blank=True)

    class Meta:
        verbose_name = "улирлын тайлан"
        verbose_name_plural = "улирлын тайлан"
        ordering = ["-term__number"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "enrollment", "term"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_term_report_per_child_term",
            ),
        ]
        indexes = [
            models.Index(fields=["child", "term"]),
            models.Index(fields=["kindergarten", "term"]),
            models.Index(fields=["enrollment", "term"]),
        ]

    def __str__(self) -> str:
        return f"{self.child} — {self.term.name}"

    @property
    def is_final(self) -> bool:
        return self.status == self.Status.FINAL

    @property
    def is_empty(self) -> bool:
        """No narrative at all. ``finalize_term`` refuses to publish this."""
        return not any((self.strengths, self.needs_support,
                        self.next_goals, self.advice_for_parents))
```

- [ ] **Step 4: Update the module docstring**

`apps/assessment/models.py` line 3–5 currently says `TermReport` is Phase 2. Replace:

```
Phase 1 covers the configuration tables, the four terms of a school year, and
the per-domain assessment itself. ``TermReport`` and ``AnnualReport`` (§6.4's
narrative report and §6.5's annual one) are Phase 2 — see ROADMAP section 8.
```

with:

```
Phase 1 covers the configuration tables, the four terms of a school year, the
per-domain assessment, and ``TermReport`` — §6.4's narrative report, pulled
forward from Phase 2 because §20-II lists it as mandatory MVP and §21.7 makes
it an acceptance criterion. ``AnnualReport`` (§6.5) is still Phase 2 — see
ROADMAP section 8.
```

- [ ] **Step 5: Generate the migration**

```bash
docker compose exec -T web python manage.py makemigrations assessment
```

Expected: `Migrations for 'assessment': 0004_termreport.py - Create model TermReport`.

- [ ] **Step 6: Read the migration by hand**

CLAUDE.md §3.4. Open `apps/assessment/migrations/0004_termreport.py` and confirm:

- exactly one `CreateModel`, named `TermReport`
- **no** `RemoveField`, `DeleteModel`, or `AlterField` on any other model
- the `UniqueConstraint` carries `condition=models.Q(deleted_at__isnull=True)`
- three `AddIndex` operations

If anything else appears, stop and find out why before continuing.

- [ ] **Step 7: Run the test**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `1 passed`.

- [ ] **Step 8: Add the uniqueness test**

Append to `apps/assessment/tests/test_term_report.py`:

```python
def test_one_report_per_child_per_term(world, term):
    """§17 — a double-click must not produce a second report."""
    from apps.children.services import current_enrollment

    enrollment = current_enrollment(world["bataa"])
    fields = {"kindergarten": world["naran"], "child": world["bataa"],
              "enrollment": enrollment, "term": term}
    TermReport.objects.create(**fields, strengths="Эхний")

    with pytest.raises(IntegrityError), transaction.atomic():
        TermReport.objects.create(**fields, strengths="Хоёр дахь")
```

- [ ] **Step 9: Run it**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `2 passed`.

- [ ] **Step 10: Commit**

```bash
git add apps/assessment/models.py apps/assessment/migrations/0004_termreport.py apps/assessment/tests/test_term_report.py
git commit -m "Add the TermReport table for RFP 6.4's narrative report

The per-domain levels already exist in Assessment. What 6.4 also asks for is
a per-child, per-term narrative - давуу тал, дэмжих шаардлагатай чадвар,
дараагийн улирлын зорилго, эцэг эхэд зөвлөмж - and those four are not
per-domain, so nine domains would otherwise hold nine copies of the same
text with no way to say which is true.

No teacher_comment field: Assessment.comment already holds the per-domain
note and the mockup shows it there. finalized_at is not auto_now, so a typo
fix does not report itself as a freshly written report.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: `save_term_report`

**Files:**
- Modify: `apps/assessment/services.py`
- Modify: `apps/assessment/tests/test_term_report.py`

- [ ] **Step 1: Write the failing tests**

First add the exceptions these tests assert on to the imports at the top of
`apps/assessment/tests/test_term_report.py`:

```python
from django.core.exceptions import PermissionDenied, ValidationError
```

Then append:

```python
NARRATIVE = {
    "strengths": "Гүйлт сайн",
    "needs_support": "Тэнцвэр алдах нь ажиглагддаг",
    "next_goals": "Тэнцвэрийн дасгал тогтмол хийх",
    "advice_for_parents": "Гэртээ тэнцвэрийн дасгал тоглоно уу",
}


def test_saving_twice_updates_one_row(world, term):
    """Idempotent on (child, enrollment, term) — the same shape as
    save_assessment. The constraint is the backstop, not the mechanism."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    report = services.save_term_report(
        actor=world["dulmaa"], child=world["bataa"], term=term,
        **NARRATIVE | {"strengths": "Зассан"},
    )

    assert TermReport.objects.count() == 1
    assert report.strengths == "Зассан"
    assert report.author == world["dulmaa"]


def test_a_guardian_cannot_write_a_term_report(world, term):
    """§6.4 is the teacher's professional judgement — can_record_for_child."""
    with pytest.raises(PermissionDenied):
        services.save_term_report(actor=world["bataa_mother"],
                                  child=world["bataa"], term=term,
                                  **NARRATIVE)


def test_a_teacher_from_another_kindergarten_cannot_write_one(world, term):
    with pytest.raises(PermissionDenied):
        services.save_term_report(actor=world["oyun"], child=world["bataa"],
                                  term=term, **NARRATIVE)


def test_a_term_from_another_school_year_is_refused(world, term,
                                                    naran_admin_user):
    """§3.2 — a crafted request must not file a report against another
    kindergarten's term."""
    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])

    with pytest.raises(ValidationError):
        services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                                  term=och_terms[0], **NARRATIVE)


def transfer_bataa_to_och(world):
    """Bataa moves from Наран to Оч mid-year. Used by the §1.2 tests here
    and in Task 4, so it is a helper rather than a copy in each."""
    import datetime as dt

    from apps.children.models import Enrollment

    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED, ended_on=dt.date(2026, 1, 15)
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"],
        group=world["petal"], school_year=world["och_year"],
        started_on=dt.date(2026, 1, 16),
    )
    world["bataa"].kindergarten = world["och"]
    world["bataa"].save()


def test_a_transferred_childs_report_keeps_its_kindergarten(world, term):
    """CLAUDE.md §1.2 — the report stays filed against the kindergarten it
    was written in, so a transfer does not hand it to the new one.

    Whether each user can then *read* it is the selector's job, tested in
    Task 4 once ``term_report`` exists."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    transfer_bataa_to_och(world)

    report = TermReport.objects.get()
    assert report.kindergarten_id == world["naran"].pk


def test_saving_writes_an_audit_row(world, term):
    """RFP §971 — who wrote what about which child."""
    from apps.core.models import AuditAction, AuditLog

    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE, actor_user=world["dulmaa"],
        object_type="assessment.TermReport",
    ).exists()
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: six failures, `AttributeError: module 'apps.assessment.services' has no attribute 'save_term_report'`.

- [ ] **Step 3: Implement**

In `apps/assessment/services.py`, add `TermReport` to the model import:

```python
from .models import Assessment, Term, TermReport
```

Add to `__all__`, after `"publish_term"`:

```python
    "save_term_report",
    "finalize_term",
    "reopen_term",
```

Add after `publish_term`:

```python
@transaction.atomic
def save_term_report(*, actor, child, term, strengths="", needs_support="",
                     next_goals="", advice_for_parents="",
                     enrollment=None, request=None) -> TermReport:
    """RFP §6.4 — write or update the narrative for one term.

    Idempotent on ``(child, enrollment, term)``, the same shape as
    ``save_assessment``: a second submission updates the row rather than
    creating a second one, and the database constraint of the same name is
    the backstop for §17's double-click, not the mechanism.

    Editing a finalized report leaves it finalized. A teacher fixing a typo
    must not make the report a family is reading disappear; the edit goes
    live and ``AuditLog`` records it. Reverting is ``reopen_term``, which is
    a decision rather than a side effect.
    """
    _guard(actor, child)

    enrollment = enrollment or recording_enrollment(child)
    if enrollment.child_id != child.pk:
        raise ValidationError("Бүртгэл нь өөр хүүхдийнх байна.")

    assert_writable(actor, child, enrollment)
    _check_term(enrollment, term)

    report = TermReport.objects.filter(
        child=child, enrollment=enrollment, term=term
    ).first()
    created = report is None
    if created:
        report = TermReport(
            kindergarten_id=enrollment.kindergarten_id,
            child=child, enrollment=enrollment, term=term,
        )

    report.strengths = strengths
    report.needs_support = needs_support
    report.next_goals = next_goals
    report.advice_for_parents = advice_for_parents
    report.author = actor

    return save_record(actor=actor, obj=report, created=created,
                       request=request)
```

- [ ] **Step 4: Run the tests**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Lint**

```bash
docker compose exec -T web ruff check apps/assessment/
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add apps/assessment/services.py apps/assessment/tests/test_term_report.py
git commit -m "Add save_term_report

Idempotent on (child, enrollment, term), the same shape as save_assessment,
reusing _guard, assert_writable and _check_term unchanged rather than
inventing a second set of rules (CLAUDE.md 1.1).

Editing a finalized report leaves it finalized. A teacher fixing a typo must
not make the report a family is reading disappear.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `finalize_term` and `reopen_term`

This is the one-button contract: finalizing the report also opens that term's assessments to the guardians.

**Files:**
- Modify: `apps/assessment/services.py`
- Modify: `apps/assessment/tests/test_term_report.py`

- [ ] **Step 1: Write the failing tests**

These assert on the assessments the finalize publishes, so extend the model
import at the top of `apps/assessment/tests/test_term_report.py`:

```python
from apps.assessment.models import Assessment, TermReport
```

Then append:

```python
def test_finalizing_also_publishes_the_terms_assessments(world, term, domain,
                                                         level):
    """The one-button contract. A teacher has one mental model: the term is
    finished or it is not."""
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    report = services.finalize_term(actor=world["dulmaa"],
                                    child=world["bataa"], term=term)

    assert report.status == TermReport.Status.FINAL
    assert report.finalized_at is not None
    assert Assessment.objects.get(child=world["bataa"],
                                  term=term).visible_to_parents is True


def test_finalizing_an_empty_report_is_refused(world, term):
    """Four blank headings are worse than nothing — the same question D5
    settled for the printed portfolio."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term)

    with pytest.raises(ValidationError):
        services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                               term=term)

    assert TermReport.objects.get().status == TermReport.Status.DRAFT


def test_finalizing_without_a_report_is_refused(world, term):
    with pytest.raises(ValidationError):
        services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                               term=term)


def test_a_guardian_cannot_finalize(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    with pytest.raises(PermissionDenied):
        services.finalize_term(actor=world["bataa_mother"],
                               child=world["bataa"], term=term)


def test_reopening_hides_the_assessments_again(world, term, domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = services.reopen_term(actor=world["dulmaa"], child=world["bataa"],
                                  term=term)

    assert report.status == TermReport.Status.DRAFT
    assert report.finalized_at is None
    assert Assessment.objects.get(child=world["bataa"],
                                  term=term).visible_to_parents is False


def test_editing_a_final_report_leaves_it_final(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = services.save_term_report(
        actor=world["dulmaa"], child=world["bataa"], term=term,
        **NARRATIVE | {"strengths": "Үсгийн алдаа зассан"},
    )

    assert report.status == TermReport.Status.FINAL
    assert report.finalized_at is not None
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q -k "finaliz or reopen or final"
```

Expected: failures, `has no attribute 'finalize_term'`.

- [ ] **Step 3: Implement**

Add to `apps/assessment/services.py`, after `save_term_report`:

```python
def _report_for(child, term) -> TermReport:
    """The report being finalized, or a message saying to write one first."""
    report = TermReport.objects.filter(child=child, term=term).first()
    if report is None:
        raise ValidationError("Эхлээд улирлын тайланг бичнэ үү.")
    return report


@transaction.atomic
def finalize_term(*, actor, child, term, request=None) -> TermReport:
    """RFP §6.4, §2.3 — declare the term finished and open it to the family.

    One action, two effects: the report becomes final and that term's
    assessments become visible. ``publish_term`` is *called* rather than
    reimplemented, so the rule for opening a term to guardians stays in one
    place (CLAUDE.md §1.1) and the teacher has one mental model rather than
    two switches that can disagree.
    """
    _guard(actor, child)

    report = _report_for(child, term)
    if report.is_empty:
        # Four blank headings tell a family less than no report at all —
        # the same question D5 settled for the printed portfolio.
        raise ValidationError(
            "Хоосон тайланг дуусгах боломжгүй. Дор хаяж нэг хэсгийг бөглөнө үү."
        )

    report.status = TermReport.Status.FINAL
    report.finalized_at = timezone.now()
    saved = save_record(actor=actor, obj=report, created=False,
                        request=request)

    publish_term(actor=actor, child=child, term=term, visible=True,
                 request=request)
    return saved


@transaction.atomic
def reopen_term(*, actor, child, term, request=None) -> TermReport:
    """Undo :func:`finalize_term`.

    Not in the RFP. It exists because a report finalized by mistake
    otherwise has no route back except the database.
    """
    _guard(actor, child)

    report = _report_for(child, term)
    report.status = TermReport.Status.DRAFT
    report.finalized_at = None
    saved = save_record(actor=actor, obj=report, created=False,
                        request=request)

    publish_term(actor=actor, child=child, term=term, visible=False,
                 request=request)
    return saved
```

- [ ] **Step 4: Run the whole file**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `14 passed`.

- [ ] **Step 5: Prove the one-button test actually catches a break**

A passing test proves nothing until you have seen it fail for the right reason. Temporarily comment out the `publish_term(...)` call inside `finalize_term`, then:

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q -k "publishes"
```

Expected: `test_finalizing_also_publishes_the_terms_assessments` FAILS on `assert False is True`. Restore the line and re-run to confirm green.

- [ ] **Step 6: Run the app's whole suite**

```bash
docker compose exec -T web pytest apps/assessment/ -q
```

Expected: all pass. Nothing here changed `publish_term` itself, so its three existing tests still hold.

- [ ] **Step 7: Commit**

```bash
git add apps/assessment/services.py apps/assessment/tests/test_term_report.py
git commit -m "Finalizing a term report publishes its assessments

One action, two effects. publish_term is called rather than reimplemented,
so the rule for opening a term to guardians stays in one place and the
teacher has one mental model instead of two switches that can disagree.

An empty report cannot be finalized - four blank headings tell a family
less than no report, which is the same question D5 settled for the printed
portfolio. reopen_term is not in the RFP; it exists so a report finalized
by mistake has a route back that is not the database.

Verified by commenting out the publish_term call and watching the
one-button test fail.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Selectors

Reads, scoped to the viewer. A guardian sees a final report; a draft is a working document.

**Files:**
- Modify: `apps/assessment/selectors.py`
- Modify: `apps/assessment/tests/test_term_report.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/assessment/tests/test_term_report.py`:

```python
def test_a_guardian_cannot_see_a_draft_report(world, term):
    """RFP §2.3 — "багшийн зөвшөөрсөн"."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)

    assert selectors.term_report(world["dulmaa"], world["bataa"], term)
    assert selectors.term_report(world["bataa_mother"], world["bataa"],
                                 term) is None


def test_a_guardian_sees_it_once_finalized(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    report = selectors.term_report(world["bataa_mother"], world["bataa"], term)

    assert report is not None
    assert report.strengths == NARRATIVE["strengths"]


def test_another_kindergarten_sees_nothing(world, term):
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    assert selectors.term_report(world["oyun"], world["bataa"], term) is None


def test_after_a_transfer_the_author_keeps_it_and_the_new_school_does_not(
    world, term
):
    """CLAUDE.md §1.2, the read half. Task 2 pinned where the row is filed;
    this pins who can still see it."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    services.finalize_term(actor=world["dulmaa"], child=world["bataa"],
                           term=term)

    transfer_bataa_to_och(world)

    assert selectors.term_report(world["dulmaa"], world["bataa"], term)
    assert selectors.term_report(world["oyun"], world["bataa"], term) is None


def test_term_reports_for_maps_term_id_to_report(world, terms):
    """The child screen needs one lookup, not one query per term."""
    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=terms[0], **NARRATIVE)

    found = selectors.term_reports_for(world["dulmaa"], world["bataa"])

    assert set(found) == {terms[0].pk}
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q -k "guardian_cannot_see or once_finalized or another_kindergarten_sees or reports_for or after_a_transfer"
```

Expected: `AttributeError: ... has no attribute 'term_report'`.

- [ ] **Step 3: Implement**

In `apps/assessment/selectors.py`, add `TermReport` to the model import (find the existing `from .models import ...` line and extend it), then add to `__all__`:

```python
    "term_report",
    "term_reports_for",
```

Add at the end of the file:

```python
def _readable_reports(user, child):
    """Every term report about this child this user may read — §2.3.

    The guardian filter is the whole difference between the two roles, and
    it lives here so no screen has to remember it.
    """
    queryset = TermReport.objects.filter(
        child=child,
        kindergarten_id__in=visible_kindergartens(user, child),
    )
    if is_guardian_of(user, child):
        queryset = queryset.filter(status=TermReport.Status.FINAL)
    return queryset


def term_report(user, child, term) -> "TermReport | None":
    """RFP §6.4 — one term's narrative, or ``None`` if not readable."""
    return (
        _readable_reports(user, child)
        .filter(term=term)
        .select_related("term", "author")
        .first()
    )


def term_reports_for(user, child) -> dict:
    """``{term_id: TermReport}`` for the child screen.

    A dict rather than a queryset because the template looks each term up by
    id while iterating the matrix columns; a filter per column is the N+1
    CLAUDE.md §3.5 forbids.
    """
    return {
        report.term_id: report
        for report in _readable_reports(user, child).select_related("term")
    }
```

- [ ] **Step 4: Run**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: `19 passed`.

- [ ] **Step 5: Commit**

```bash
git add apps/assessment/selectors.py apps/assessment/tests/test_term_report.py
git commit -m "Add term_report and term_reports_for selectors

The guardian filter - final only, a draft is a working document - lives in
_readable_reports so no screen has to remember it, mirroring how
_readable already works for Assessment.

term_reports_for returns a dict keyed by term id because the child screen
looks each term up while iterating the matrix columns, and a filter per
column is the N+1 CLAUDE.md 3.5 forbids.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: The teacher's screen

**Files:**
- Modify: `apps/assessment/views.py`
- Modify: `apps/assessment/urls.py`
- Create: `templates/assessment/term_report.html`
- Modify: `templates/assessment/child.html`
- Modify: `apps/assessment/tests/test_term_report.py`
- Modify: `apps/assessment/tests/test_assessment.py` (retarget two tests)

- [ ] **Step 1: Write the three mandatory authorization tests**

CLAUDE.md §4.1. These go through the HTTP client, so add the URL helper to
the imports at the top of `apps/assessment/tests/test_term_report.py`:

```python
from django.urls import reverse
```

Then append:

```python
# ------------------------------------------------------------------ §21
# CLAUDE.md §4.1 — the three mandatory tests, through the HTTP client. A
# view that forgets its check passes every service-level test above.

def report_url(child, term):
    return reverse("assessment:term_report", args=[child.pk, term.pk])


def test_teacher_from_another_group_gets_404(client, world, term,
                                             make_teacher, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_guardian_of_another_child_gets_404(client, world, term,
                                            make_guardian, make_child):
    elsewhere = make_child(world["naran"], world["sunflower"],
                           first_name="Өөр")
    outsider = make_guardian(elsewhere, world["naran"],
                             username="other_mother")
    login(client, outsider)

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_user_from_another_kindergarten_gets_404(client, world, term):
    login(client, world["oyun"])

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_the_childs_own_guardian_cannot_reach_the_editor(client, world, term):
    """§6.4 is the teacher's record. This family may read the finished
    report on the assessment screen; writing it is a different permission."""
    login(client, world["bataa_mother"])

    url = report_url(world["bataa"], term)
    assert client.get(url).status_code == 404
    assert client.post(url, NARRATIVE).status_code == 404
    assert not TermReport.objects.exists()


def test_a_term_from_another_year_gets_404(client, world, term,
                                           naran_admin_user):
    """A real term id, reached through a child it does not apply to."""
    och_terms = services.ensure_default_terms(actor=naran_admin_user,
                                              school_year=world["och_year"])
    login(client, world["dulmaa"])

    url = report_url(world["bataa"], och_terms[0])
    assert client.get(url).status_code == 404
    assert not TermReport.objects.exists()


def test_the_teacher_writes_and_finalizes_from_the_screen(client, world, term,
                                                          domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["dulmaa"])
    url = report_url(world["bataa"], term)

    assert client.get(url).status_code == 200

    assert client.post(url, NARRATIVE | {"action": "save"}).status_code == 302
    assert TermReport.objects.get().status == TermReport.Status.DRAFT

    assert client.post(url, NARRATIVE | {"action": "finalize"}).status_code == 302
    assert TermReport.objects.get().status == TermReport.Status.FINAL
    assert Assessment.objects.get().visible_to_parents is True


def test_finalizing_an_empty_report_from_the_screen_explains_itself(
    client, world, term
):
    login(client, world["dulmaa"])

    response = client.post(report_url(world["bataa"], term),
                           {"action": "finalize"}, follow=True)

    assert response.status_code == 200
    assert "Хоосон" in response.content.decode()
    assert TermReport.objects.get().status == TermReport.Status.DRAFT
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q -k "404 or writes_and_finalizes or explains_itself or reach_the_editor"
```

Expected: `NoReverseMatch: 'term_report' is not a valid view function or pattern name`.

- [ ] **Step 3: Add the view**

In `apps/assessment/views.py`, **replace** the whole `publish` function (it starts at `def publish(request, child_id):` and ends at its `return`) with:

```python
@login_required
def term_report(request, child_id, term_id):
    """RFP §6.4 — the narrative a teacher writes once the grid is filled in.

    Teacher-only: ``_context`` resolves the child through the permission
    layer, and ``can_record_for_child`` is what separates reading the
    portfolio from writing the professional record (§5.1, §6.3). A guardian
    reads the finished report on the assessment screen instead.
    """
    context = _context(request, child_id)
    child = context["child"]

    if not context["can_record"]:
        raise Http404

    enrollment = current_enrollment(child)
    if enrollment is None:
        raise Http404

    term = Term.objects.filter(
        school_year=enrollment.school_year, pk=term_id
    ).first()
    if term is None:
        raise Http404

    if request.method == "POST":
        narrative = {
            field: request.POST.get(field, "").strip()
            for field in ("strengths", "needs_support", "next_goals",
                          "advice_for_parents")
        }
        try:
            services.save_term_report(actor=request.user, child=child,
                                      term=term, enrollment=enrollment,
                                      request=request, **narrative)
            if request.POST.get("action") == "finalize":
                services.finalize_term(actor=request.user, child=child,
                                       term=term, request=request)
                messages.success(request, "Тайлан дуусаж, эцэг эхэд нээгдлээ.")
            elif request.POST.get("action") == "reopen":
                services.reopen_term(actor=request.user, child=child,
                                     term=term, request=request)
                messages.success(request, "Тайлан ноорог болж хаагдлаа.")
            else:
                messages.success(request, "Тайлан хадгалагдлаа.")
        except PermissionDenied:
            raise Http404 from None
        except ValidationError as exc:
            messages.error(request, _message(exc))

        return redirect("assessment:term_report", child_id=child.pk,
                        term_id=term.pk)

    audit(action=AuditAction.VIEW, request=request, child=child, obj=child,
          kindergarten=child.kindergarten, section="term_report")

    context |= {
        "term": term,
        "report": selectors.term_report(request.user, child, term),
        "assessments": selectors.child_assessments(request.user, child, term),
    }
    return render(request, "assessment/term_report.html", context)
```

- [ ] **Step 4: Update the routes**

In `apps/assessment/urls.py`, **replace**:

```python
    path("hawtas/<int:child_id>/unelgee/niitleh/", views.publish,
         name="publish"),
```

with:

```python
    # RFP §6.4's narrative report. Finalizing it is also what opens the
    # term's assessments to the guardians, so there is no separate publish
    # route: two ways to publish the same term is how the two drift apart.
    path("hawtas/<int:child_id>/unelgee/tailan/<int:term_id>/",
         views.term_report, name="term_report"),
```

- [ ] **Step 5: Write the template**

Create `templates/assessment/term_report.html`:

```html
{% extends base_template %}
{% comment %} RFP §6.4's narrative report, laid out as the right-hand panel of
   docs/design/screens/teacher-assessment-matrix.jpeg draws it: the four
   headings in that order, with the term's domain levels above them for
   reference while writing. {% endcomment %}

{% block title %}Улирлын тайлан{% endblock %}
{% block heading %}{{ term.name }} — {{ child.full_name }}{% endblock %}

{% block content %}
  <div class="card" style="max-width:820px">
    <h2>
      {{ term.name }}
      {% if report.is_final %}
        <span class="badge badge--ok">Дууссан</span>
      {% else %}
        <span class="badge badge--muted">Ноорог</span>
      {% endif %}
    </h2>
    <p class="brand__sub" style="margin-top:-8px">
      {{ term.starts_on|date:"Y.m.d" }} – {{ term.ends_on|date:"Y.m.d" }}
      {% if report.finalized_at %}
        · Дуусгасан: {{ report.finalized_at|date:"Y.m.d" }}
      {% endif %}
    </p>

    {% if assessments %}
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Хөгжлийн чиглэл</th><th>Үнэлгээ</th><th>Тайлбар</th></tr>
          </thead>
          <tbody>
            {% for row in assessments %}
              <tr>
                <td class="name">{{ row.domain.name }}</td>
                <td>
                  <span class="badge"
                        style="background:{{ row.level.color }}1a; color:{{ row.level.color }}">
                    {{ row.level.label }}
                  </span>
                </td>
                <td>{{ row.comment|default:"—" }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <p class="empty">Энэ улиралд үнэлгээ бүртгээгүй байна.</p>
    {% endif %}

    <form method="post" novalidate>
      {% csrf_token %}

      <label for="id_strengths">Давуу тал</label>
      <textarea name="strengths" id="id_strengths" rows="3">{{ report.strengths|default:"" }}</textarea>

      <label for="id_needs_support">Дэмжих шаардлагатай чадвар</label>
      <textarea name="needs_support" id="id_needs_support" rows="3">{{ report.needs_support|default:"" }}</textarea>

      <label for="id_next_goals">Дараагийн улирлын зорилго</label>
      <textarea name="next_goals" id="id_next_goals" rows="3">{{ report.next_goals|default:"" }}</textarea>

      <label for="id_advice_for_parents">Эцэг эхэд өгөх зөвлөмж</label>
      <textarea name="advice_for_parents" id="id_advice_for_parents" rows="3">{{ report.advice_for_parents|default:"" }}</textarea>

      <div class="btn-row">
        <button type="submit" name="action" value="save" class="btn btn--ghost">
          Ноороглон хадгалах
        </button>
        {% if report.is_final %}
          <button type="submit" name="action" value="reopen" class="btn btn--ghost">
            Буцааж нээх
          </button>
        {% else %}
          <button type="submit" name="action" value="finalize" class="btn">
            Дуусгаж эцэг эхэд нээх
          </button>
        {% endif %}
        <a class="btn btn--ghost" href="{% url 'assessment:child' child.pk %}">
          Буцах
        </a>
      </div>
    </form>
  </div>
{% endblock %}
```

- [ ] **Step 6: Replace the publish form on the child screen**

In `templates/assessment/child.html`, find the block that begins:

```
      {# RFP §2.3 — a term stays closed until the teacher says it is done. #}
      <div class="card" style="max-width:820px">
        <h2>Эцэг эхэд нээх</h2>
```

and ends with that card's closing `</div>`. Replace the whole card with:

```html
      {# RFP §6.4 — the narrative report per term. Finalizing one is also
         what opens that term to the guardians, so this replaces the old
         separate "publish" control. #}
      <div class="card" style="max-width:820px">
        <h2>Улирлын тайлан</h2>
        <p class="brand__sub" style="margin-top:-8px">
          Улирал бүрийн дүгнэлт. Дуусгасны дараа эцэг эхэд харагдана.
        </p>

        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Улирал</th><th>Төлөв</th><th></th></tr>
            </thead>
            <tbody>
              {% for term in terms %}
                <tr>
                  <td class="name">{{ term.name }}</td>
                  <td>
                    {% with report=term_reports|get_item:term.pk %}
                      {% if report.is_final %}
                        <span class="badge badge--ok">Дууссан</span>
                      {% elif report %}
                        <span class="badge badge--muted">Ноорог</span>
                      {% else %}
                        <span class="badge badge--muted">Бичээгүй</span>
                      {% endif %}
                    {% endwith %}
                  </td>
                  <td>
                    <a href="{% url 'assessment:term_report' child.pk term.pk %}">
                      Нээх
                    </a>
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
```

That `get_item` filter does not exist yet — the next step decides against it.

- [ ] **Step 7: Replace the dict lookup with a list**

Django templates cannot index a dict by variable key without a custom filter, and one filter for one screen is not worth a template library. Change the view instead.

In `apps/assessment/views.py`, inside `child_assessment`, find:

```python
        "published_terms": _published_terms(request.user, child),
```

Replace with:

```python
        # Paired here rather than looked up in the template: Django cannot
        # index a dict by a variable key without a custom filter, and one
        # filter for one screen is not worth a template library.
        "term_reports": [
            (term, reports.get(term.pk)) for term in matrix["terms"]
        ],
```

and immediately above the `context |= {` line, add:

```python
    reports = selectors.term_reports_for(request.user, child)
```

Then delete the now-unused `_published_terms` helper at the bottom of the file.

In `templates/assessment/child.html`, change the loop from Step 6 to iterate the pairs:

```html
              {% for term, report in term_reports %}
                <tr>
                  <td class="name">{{ term.name }}</td>
                  <td>
                    {% if report.is_final %}
                      <span class="badge badge--ok">Дууссан</span>
                    {% elif report %}
                      <span class="badge badge--muted">Ноорог</span>
                    {% else %}
                      <span class="badge badge--muted">Бичээгүй</span>
                    {% endif %}
                  </td>
                  <td>
                    <a href="{% url 'assessment:term_report' child.pk term.pk %}">
                      Нээх
                    </a>
                  </td>
                </tr>
              {% endfor %}
```

- [ ] **Step 8: Show guardians the finished report**

Still in `templates/assessment/child.html`. The structure is:

```
{% if no_enrollment %} … {% elif not terms %} … {% else %}
    <div class="card">  the matrix table  </div>
    {% if can_record %}
      the "Үнэлгээ бүртгэх" card
      the card you replaced in Step 6        ← teacher only
    {% endif %}                              ← around line 137
  {% endif %}
{% endblock %}
```

Confirm your new card from Step 6 is inside the `can_record` branch. Then add the guardian's read-only view **between** that `{% endif %}` and the outer one:

```html
      {% if not can_record %}
        {% for term, report in term_reports %}
          {% if report %}
            <div class="card" style="max-width:820px">
              <h2>{{ term.name }} — багшийн дүгнэлт</h2>
              {% if report.strengths %}
                <h3>Давуу тал</h3><p>{{ report.strengths|linebreaksbr }}</p>
              {% endif %}
              {% if report.needs_support %}
                <h3>Дэмжих шаардлагатай чадвар</h3>
                <p>{{ report.needs_support|linebreaksbr }}</p>
              {% endif %}
              {% if report.next_goals %}
                <h3>Дараагийн улирлын зорилго</h3>
                <p>{{ report.next_goals|linebreaksbr }}</p>
              {% endif %}
              {% if report.advice_for_parents %}
                <h3>Эцэг эхэд өгөх зөвлөмж</h3>
                <p>{{ report.advice_for_parents|linebreaksbr }}</p>
              {% endif %}
            </div>
          {% endif %}
        {% endfor %}
      {% endif %}
```

The selector already filtered to `status=final` for guardians, so no status check is needed here — and adding one would put the rule in two places.

- [ ] **Step 9: Retarget the two publish-view tests**

In `apps/assessment/tests/test_assessment.py`, the tests `test_publishing_opens_the_term_to_the_guardian` and `test_a_guardian_cannot_publish` post to `assessment:publish`, which no longer exists. Their claims are still true; move them to the new URL. Replace both functions with:

```python
def test_finalizing_opens_the_term_to_the_guardian(client, world, term,
                                                   domain, level):
    """Was a POST to assessment:publish until 2026-08-11. The control moved
    into the term report — finalizing is what opens the term now."""
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["dulmaa"])

    response = client.post(
        reverse("assessment:term_report", args=[world["bataa"].pk, term.pk]),
        {"strengths": "Гүйлт сайн", "action": "finalize"},
    )

    assert response.status_code == 302
    assert selectors.child_assessments(world["bataa_mother"],
                                       world["bataa"]).count() == 1


def test_a_guardian_cannot_finalize_a_term(client, world, term, domain, level):
    services.save_assessment(actor=world["dulmaa"], child=world["bataa"],
                             domain=domain, term=term, level=level)
    login(client, world["bataa_mother"])

    response = client.post(
        reverse("assessment:term_report", args=[world["bataa"].pk, term.pk]),
        {"strengths": "Гүйлт сайн", "action": "finalize"},
    )

    assert response.status_code == 404
    assert not selectors.child_assessments(world["bataa_mother"],
                                           world["bataa"]).exists()
```

- [ ] **Step 10: Run the app's suite**

```bash
docker compose exec -T web pytest apps/assessment/ -q
```

Expected: all pass. If anything still references `assessment:publish` or `_published_terms`, the error names it.

- [ ] **Step 11: Check the template for English leaking into the page**

```bash
docker compose exec -T web pytest apps/core/tests/test_templates.py -q
```

Expected: pass. That suite guards against the Day 10 bug where `{# #}` comments printed onto the page.

- [ ] **Step 12: Lint and commit**

```bash
docker compose exec -T web ruff check apps/
git add apps/assessment/ templates/assessment/
git commit -m "Add the term report screen, replacing the separate publish control

Four textareas in the order teacher-assessment-matrix.jpeg draws them, with
the term's domain levels above for reference while writing. One button
finishes the term: it saves, finalizes and opens the assessments together.

The old 'Эцэг эхэд нээх' card is gone, and so are its route and view. An
endpoint with no screen behind it is still reachable and still needs its
authorization kept correct - exactly the thing that survives a refactor
nobody remembered it was part of. The publish_term service stays; it is
what finalize_term calls. Its two view tests moved to the new URL rather
than being deleted: the claims they make are still true.

Guardians read the finished report on the assessment screen they already
use. The selector filtered to final, so the template does not check status
again - that would put the rule in two places.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Register it in Django Admin

CLAUDE.md §2.4 — admin writes must go through services, or they skip the audit log and skip soft delete.

**Files:**
- Modify: `apps/assessment/admin.py`
- Modify: `apps/assessment/tests/test_term_report.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/assessment/tests/test_term_report.py`:

```python
def test_the_admin_soft_deletes_rather_than_dropping_the_row(world, term):
    """CLAUDE.md §2.4, §3.3 — an admin delete must not lose the record."""
    from apps.assessment.admin import TermReportAdmin
    from apps.core.admin import admin_site

    services.save_term_report(actor=world["dulmaa"], child=world["bataa"],
                              term=term, **NARRATIVE)
    report = TermReport.objects.get()

    admin = TermReportAdmin(TermReport, admin_site)
    request = type("R", (), {"user": world["dulmaa"]})()
    admin.delete_model(request, report)

    assert not TermReport.objects.filter(pk=report.pk).exists()
    assert TermReport.all_objects.get(pk=report.pk).deleted_at is not None
```

- [ ] **Step 2: Run and watch it fail**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q -k "admin_soft_deletes"
```

Expected: `ImportError: cannot import name 'TermReportAdmin'`.

- [ ] **Step 3: Implement**

In `apps/assessment/admin.py`, add `TermReport` to the model import, then append:

```python
@admin.register(TermReport, site=admin_site)
class TermReportAdmin(TenantScopedAdmin):
    """RFP §6.4. Read-mostly: the narrative is written on the teacher's
    screen, and this exists so an administrator can find and archive one.

    ``ServiceBackedAdmin`` routes save and delete through the services, so
    an admin action still writes an audit row and still soft-deletes
    (CLAUDE.md §2.4, §3.3).
    """

    list_display = ("child", "term", "status", "author", "finalized_at")
    list_filter = ("status", "term")
    search_fields = ("child__last_name", "child__first_name")
    list_select_related = ("child", "term", "author")
    exclude = ("kindergarten",)
```

- [ ] **Step 4: Run**

```bash
docker compose exec -T web pytest apps/assessment/tests/test_term_report.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/assessment/admin.py apps/assessment/tests/test_term_report.py
git commit -m "Register TermReport in the admin through ServiceBackedAdmin

Without the service-backed base an admin delete drops the row outright,
skipping both the audit log and soft delete (CLAUDE.md 2.4, 3.3).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: The PDF — job type and context

**Files:**
- Modify: `apps/reports/models.py`
- Modify: `apps/reports/services.py`
- Modify: `apps/reports/builder.py`
- Create: `apps/reports/migrations/0002_termreport_type.py` (generated)
- Modify: `apps/reports/tests/test_reports.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/reports/tests/test_reports.py`:

```python
# ------------------------------------------------------------------ §10.2

@pytest.fixture
def term_with_report(world, filled):
    """A finalized term report for Bataa — RFP §6.4.

    ``filled`` already created the four terms and one assessment in the
    first of them. ``ensure_default_terms`` returns the existing rows rather
    than making a second set, so calling it again is how you get hold of
    them without the fixture having to return them.
    """
    from apps.assessment import services as assessment_services

    terms = assessment_services.ensure_default_terms(
        actor=world["dulmaa"], school_year=world["naran_year"]
    )
    assessment_services.save_term_report(
        actor=world["dulmaa"], child=world["bataa"], term=terms[0],
        strengths="Гүйлт сайн",
        needs_support="Тэнцвэр алдах нь ажиглагддаг",
        next_goals="Тэнцвэрийн дасгал тогтмол хийх",
        advice_for_parents="Гэртээ тэнцвэрийн дасгал тоглоно уу",
    )
    assessment_services.finalize_term(actor=world["dulmaa"],
                                      child=world["bataa"], term=terms[0])
    return terms[0]


def test_requesting_a_term_report_queues_the_right_type(world,
                                                        term_with_report):
    job = services.request_term_report(actor=world["dulmaa"],
                                       child=world["bataa"],
                                       term=term_with_report)

    assert job.type == ReportJob.Type.TERM_REPORT
    assert job.params["term_id"] == term_with_report.pk
    assert job.status == ReportJob.Status.QUEUED


def test_a_stranger_cannot_request_a_term_report(world, term_with_report):
    with pytest.raises(PermissionDenied):
        services.request_term_report(actor=world["oyun"],
                                     child=world["bataa"],
                                     term=term_with_report)


def test_the_term_context_carries_the_four_sections(world, term_with_report):
    from apps.reports.builder import build_term_report_context

    context = build_term_report_context(viewer=world["dulmaa"],
                                        child=world["bataa"],
                                        term=term_with_report)

    assert context["report"].strengths == "Гүйлт сайн"
    assert context["term"] == term_with_report
    assert context["logo_data_uri"]


def test_a_guardian_gets_no_context_for_a_draft_term(world, term_with_report):
    """The screen and the report must give the same answer."""
    from apps.assessment import services as assessment_services
    from apps.reports.builder import build_term_report_context

    assessment_services.reopen_term(actor=world["dulmaa"],
                                    child=world["bataa"],
                                    term=term_with_report)

    context = build_term_report_context(viewer=world["bataa_mother"],
                                        child=world["bataa"],
                                        term=term_with_report)

    assert context["report"] is None
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/reports/tests/test_reports.py -q -k "term"
```

Expected: `AttributeError: ... has no attribute 'request_term_report'`.

- [ ] **Step 3: Add the type**

In `apps/reports/models.py`:

```python
    class Type(models.TextChoices):
        CHILD_PORTFOLIO = "child_portfolio", "Хүүхдийн хувийн хавтас"
        TERM_REPORT = "term_report", "Улирлын тайлан"
```

- [ ] **Step 4: Generate and read the migration**

```bash
docker compose exec -T web python manage.py makemigrations reports
```

Then open the generated file. A `choices` change is metadata only — expect one `AlterField` on `type` and nothing else. No data migration is needed: existing rows keep `child_portfolio`.

- [ ] **Step 5: Add the service**

In `apps/reports/services.py`, add `"request_term_report"` to `__all__` and append after `request_child_portfolio`:

```python
@transaction.atomic
def request_term_report(*, actor, child, term, request=None) -> ReportJob:
    """RFP §10.2 — queue one term's report as a PDF.

    The term is stored by id rather than as a relation because ``params``
    is a record of what was asked for, not a schema — the same reason the
    portfolio stores its section list there.
    """
    if not can_access_child(actor, child):
        raise PermissionDenied

    kindergartens = visible_kindergartens(actor, child)
    if not kindergartens:
        raise PermissionDenied

    job = ReportJob(
        kindergarten_id=(
            child.kindergarten_id if child.kindergarten_id in kindergartens
            else next(iter(kindergartens))
        ),
        child=child,
        type=ReportJob.Type.TERM_REPORT,
        params={"term_id": term.pk},
        requested_by=actor,
        status=ReportJob.Status.QUEUED,
        expires_at=timezone.now() + dt.timedelta(
            days=settings.REPORT_RETENTION_DAYS
        ),
    )
    save_record(actor=actor, obj=job, created=True, request=request)

    from .tasks import generate_report

    transaction.on_commit(lambda: generate_report.delay(job.pk))
    return job
```

- [ ] **Step 6: Add the builder**

In `apps/reports/builder.py`, extend `__all__`:

```python
__all__ = ["build_context", "build_term_report_context"]
```

and append:

```python
def build_term_report_context(*, viewer, child, term) -> dict:
    """RFP §10.2 — one term's report, scoped to whoever asked for it.

    ``report`` is ``None`` when the viewer may not see it — a guardian and a
    draft. The template prints nothing in that case and the task fails the
    job, so the PDF cannot answer differently from the screen.
    """
    return {
        "child": child,
        "kindergarten": child.kindergarten,
        "enrollment": current_enrollment(child),
        "term": term,
        "report": assessment_selectors.term_report(viewer, child, term),
        "assessments": list(
            assessment_selectors.child_assessments(viewer, child, term)
        ),
        "photo_data_uri": _photo(child),
        "logo_data_uri": _logo(),
        "generated_for": viewer,
    }
```

- [ ] **Step 7: Run**

```bash
docker compose exec -T web pytest apps/reports/tests/test_reports.py -q -k "term"
```

Expected: `4 passed`.

- [ ] **Step 8: Commit**

```bash
git add apps/reports/models.py apps/reports/services.py apps/reports/builder.py apps/reports/migrations/ apps/reports/tests/test_reports.py
git commit -m "Add the term-report job type and its PDF context

RFP 10.2's second report type. The term goes into params by id because
params is a record of what was asked for rather than a schema, which is why
the portfolio's section list lives there too.

build_term_report_context scopes its reads to the viewer, so report is None
for a guardian looking at a draft - the PDF cannot answer differently from
the screen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: The PDF — rendering

**Files:**
- Modify: `apps/reports/tasks.py`
- Create: `templates/reports/term_report.html`
- Modify: `templates/reports/request.html`
- Modify: `apps/reports/views.py`
- Modify: `apps/reports/tests/test_reports.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/reports/tests/test_reports.py`:

```python
def test_the_term_report_pdf_contains_all_four_sections(world,
                                                        term_with_report):
    """RFP §21.7. Asserted on text extracted from the rendered file, not on
    the template — Day 10's lesson that a template can satisfy every
    structural assertion and still print the wrong thing."""
    import io

    import pypdf

    job = services.request_term_report(actor=world["dulmaa"],
                                       child=world["bataa"],
                                       term=term_with_report)
    generate_report(job.pk)
    job.refresh_from_db()

    assert job.status == ReportJob.Status.DONE

    from apps.media import services as media_services

    reader = pypdf.PdfReader(
        io.BytesIO(media_services.read_bytes(job.result_media))
    )
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert "Давуу тал" in text
    assert "Дэмжих шаардлагатай чадвар" in text
    assert "Дараагийн улирлын зорилго" in text
    assert "Эцэг эхэд өгөх зөвлөмж" in text
    assert "Гүйлт сайн" in text
    assert world["bataa"].full_name in text
    assert "Хуудас" in text
    for leak in ("RFP", "{#", "CLAUDE.md", "builder.py"):
        assert leak not in text, f"internal commentary reached the PDF: {leak!r}"


def test_a_guardians_pdf_of_a_draft_term_fails_rather_than_leaking(
    world, term_with_report
):
    """The report must not answer differently from the screen."""
    from apps.assessment import services as assessment_services

    assessment_services.reopen_term(actor=world["dulmaa"],
                                    child=world["bataa"],
                                    term=term_with_report)

    job = services.request_term_report(actor=world["bataa_mother"],
                                       child=world["bataa"],
                                       term=term_with_report)
    generate_report(job.pk)
    job.refresh_from_db()

    assert job.status == ReportJob.Status.FAILED


def test_a_job_whose_term_no_longer_exists_fails_with_a_message(
    world, term_with_report
):
    job = services.request_term_report(actor=world["dulmaa"],
                                       child=world["bataa"],
                                       term=term_with_report)
    job.params = {"term_id": 999999}
    job.save(update_fields=["params"])

    generate_report(job.pk)
    job.refresh_from_db()

    assert job.status == ReportJob.Status.FAILED
    assert job.error_message


def test_the_term_report_downloads_under_its_own_name(world,
                                                      term_with_report):
    """_filename hardcoded _hawtas_, so a term report would arrive named
    like a portfolio."""
    job = services.request_term_report(actor=world["dulmaa"],
                                       child=world["bataa"],
                                       term=term_with_report)
    generate_report(job.pk)
    job.refresh_from_db()

    assert "hawtas" not in job.result_media.original_name
    assert "tailan" in job.result_media.original_name
```

- [ ] **Step 2: Run and watch them fail**

```bash
docker compose exec -T web pytest apps/reports/tests/test_reports.py -q -k "four_sections or draft_term or no_longer_exists or own_name"
```

Expected: failures — `ValueError: Тодорхойгүй тайлангийн төрөл: term_report`.

- [ ] **Step 3: Wire up the task**

In `apps/reports/tasks.py`, extend `TEMPLATES`:

```python
TEMPLATES = {
    ReportJob.Type.CHILD_PORTFOLIO: "reports/child_portfolio.html",
    ReportJob.Type.TERM_REPORT: "reports/term_report.html",
}
```

Add the import at the top, beside the existing `build_context` import:

```python
from .builder import build_context, build_term_report_context
```

Replace `_render` with:

```python
def _render(job: ReportJob) -> tuple[bytes, int]:
    template = TEMPLATES.get(job.type)
    if template is None:
        raise ValueError(f"Тодорхойгүй тайлангийн төрөл: {job.type}")
    if job.child is None:
        raise ValueError("Тайлан хүүхэдгүй байна.")

    if job.type == ReportJob.Type.TERM_REPORT:
        context = _term_report_context(job)
    else:
        context = build_context(
            # The report contains what the *requester* may see, not what the
            # worker could reach. builder.py explains why.
            viewer=job.requested_by,
            child=job.child,
            sections=job.params.get("sections", []),
        )
    return render_pdf_with_pages(template, context)


def _term_report_context(job: ReportJob) -> dict:
    """RFP §10.2. Fails the job rather than printing an empty document.

    Two ways this legitimately has nothing to render: the term was deleted
    between the request and the worker, or the requester may not read the
    report — a guardian and a draft. Both produce a paper with headings and
    no content, which looks like a bug to whoever downloads it, so the row
    carries the reason instead (§549).
    """
    from apps.assessment.models import Term

    term = Term.objects.filter(pk=job.params.get("term_id")).first()
    if term is None:
        raise ValueError("Улирал олдсонгүй.")

    context = build_term_report_context(
        viewer=job.requested_by, child=job.child, term=term
    )
    if context["report"] is None:
        raise ValueError("Тайлан бэлэн болоогүй байна.")
    return context
```

Replace `_filename` with:

```python
def _filename(job: ReportJob) -> str:
    """A name a family can find again in their downloads folder."""
    child = job.child
    stamp = job.requested_at.strftime("%Y%m%d")
    kind = ("tailan" if job.type == ReportJob.Type.TERM_REPORT
            else "hawtas")
    return f"{child.last_name}_{child.first_name}_{kind}_{stamp}.pdf"
```

- [ ] **Step 4: Write the PDF template**

Create `templates/reports/term_report.html`:

```html
{% comment %} RFP §10.2's term report, §6.4's content.

   Shares the portfolio's @page rules deliberately, so §10.3's A4, page
   numbers and Cyrillic hold here by construction rather than by being
   remembered twice. builder.py scoped every value to whoever requested the
   report; this template only lays out what it is given. {% endcomment %}
<style>
  @page {
    size: A4;
    margin: 20mm 16mm 18mm 16mm;
    @top-right {
      content: "{{ kindergarten.name }}";
      font-family: "DejaVu Sans", sans-serif;
      font-size: 8pt;
      color: #8a8a8a;
    }
    @bottom-center {
      content: "Хуудас " counter(page) " / " counter(pages);
      font-family: "DejaVu Sans", sans-serif;
      font-size: 9pt;
      color: #666;
    }
  }
  @page :first { @top-right { content: ""; } }

  body {
    font-family: "DejaVu Sans", sans-serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #1a1a1a;
  }

  h1 { font-size: 18pt; margin: 0 0 2mm; }
  h2 { font-size: 13pt; margin: 8mm 0 3mm; color: #2f5d45;
       border-bottom: 1.5pt solid #cfe0d6; padding-bottom: 2mm; }

  .head { text-align: center; margin-bottom: 10mm; }
  .head .logo {
    display: block; height: 20mm; width: auto; max-width: 50mm;
    object-fit: contain; margin: 0 auto 5mm;
  }
  .head .sub { color: #666; font-size: 10pt; margin: 1mm 0; }

  table { width: 100%; border-collapse: collapse; margin-bottom: 5mm; }
  th, td { border: 0.5pt solid #d8d8d8; padding: 2.2mm 3mm;
           text-align: left; font-size: 9.5pt; vertical-align: top; }
  th { background: #f4f7f5; font-weight: 600; }

  p { margin: 0 0 3mm; }
  .stamp { margin-top: 12mm; color: #8a8a8a; font-size: 9pt;
           text-align: center; }
</style>

<div class="head">
  {% if logo_data_uri %}
    <img class="logo" src="{{ logo_data_uri }}" alt="Бяцхан нүүдэлчид">
  {% endif %}
  <h1>{{ child.full_name }}</h1>
  <p class="sub">{{ term.name }} — улирлын тайлан</p>
  <p class="sub">{{ kindergarten.name }}</p>
  {% if enrollment %}
    <p class="sub">{{ enrollment.group.name }} · {{ enrollment.school_year.name }}</p>
  {% endif %}
  <p class="sub">
    {{ term.starts_on|date:"Y.m.d" }} – {{ term.ends_on|date:"Y.m.d" }}
  </p>
</div>

{% if assessments %}
  <h2>Хөгжлийн үнэлгээ</h2>
  <table>
    <thead>
      <tr><th>Хөгжлийн чиглэл</th><th>Үнэлгээ</th><th>Багшийн тайлбар</th></tr>
    </thead>
    <tbody>
      {% for row in assessments %}
        <tr>
          <td>{{ row.domain.name }}</td>
          <td>{{ row.level.label }}</td>
          <td>{{ row.comment|default:"—" }}</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
{% endif %}

{% if report.strengths %}
  <h2>Давуу тал</h2>
  <p>{{ report.strengths|linebreaksbr }}</p>
{% endif %}

{% if report.needs_support %}
  <h2>Дэмжих шаардлагатай чадвар</h2>
  <p>{{ report.needs_support|linebreaksbr }}</p>
{% endif %}

{% if report.next_goals %}
  <h2>Дараагийн улирлын зорилго</h2>
  <p>{{ report.next_goals|linebreaksbr }}</p>
{% endif %}

{% if report.advice_for_parents %}
  <h2>Эцэг эхэд өгөх зөвлөмж</h2>
  <p>{{ report.advice_for_parents|linebreaksbr }}</p>
{% endif %}

<p class="stamp">
  {% if report.author %}Багш: {{ report.author.get_full_name|default:report.author.username }} · {% endif %}
  {% if report.finalized_at %}{{ report.finalized_at|date:"Y.m.d" }}{% endif %}
</p>
```

Note the four `{% if %}` guards: an unfilled section prints nothing rather than a heading over blank space. That is D5's rule, applied here.

- [ ] **Step 5: Run the PDF tests**

```bash
docker compose exec -T web pytest apps/reports/tests/test_reports.py -q -k "four_sections or draft_term or no_longer_exists or own_name"
```

Expected: `4 passed`.

- [ ] **Step 6: Render one and look at it**

Structural assertions do not catch a layout that collides — that is how the portfolio cover shipped with the logo and the photograph on one line.

```bash
docker compose exec -T web python manage.py shell -c "
from apps.children.models import Child
from apps.accounts.models import User
from apps.assessment.models import Term
from apps.reports import services
from apps.reports.tasks import generate_report
from apps.media import services as ms
child = Child.objects.filter(term_reports__isnull=False).first()
term = Term.objects.filter(reports__child=child).first()
user = User.objects.filter(memberships__kindergarten=child.kindergarten,
                           memberships__role='teacher').first()
job = services.request_term_report(actor=user, child=child, term=term)
generate_report(job.id)
job.refresh_from_db()
print(job.status, job.page_count)
open('/app/assets/_term.pdf','wb').write(ms.read_bytes(job.result_media))
"
```

If no seeded child has a term report, write one first through `services.save_term_report` and `finalize_term` in the same shell.

Then rasterise on the host and read the page:

```bash
python3 -c "
import fitz
d = fitz.open('assets/_term.pdf')
print('pages', d.page_count)
d[0].get_pixmap(dpi=85).save('assets/_term1.png')"
```

Open `assets/_term1.png` and check: the logo is on its own line, the headings are in §6.4's order, no English, Ө and Ү render as letters rather than boxes. Fix anything wrong before continuing, then delete both scratch files:

```bash
rm -f assets/_term.pdf assets/_term1.png
```

- [ ] **Step 7: Offer it in the request screen**

In `apps/reports/views.py`, inside `report_request`, add the terms to the context. Find:

```python
    context |= {
        "sections": services.SECTIONS,
```

and insert before it:

```python
    from apps.assessment import selectors as assessment_selectors
    from apps.children.services import current_enrollment

    enrollment = current_enrollment(child)
    terms = (assessment_selectors.terms_for(enrollment.school_year)
             if enrollment else [])
```

then add `"terms": terms,` inside the `context |=` dict.

In the same function, the `POST` branch currently always calls `request_child_portfolio`. Replace:

```python
            job = services.request_child_portfolio(
                actor=request.user, child=child,
                sections=request.POST.getlist("sections"),
                request=request,
            )
```

with:

```python
            if request.POST.get("report_type") == "term_report":
                term = next(
                    (t for t in terms
                     if str(t.pk) == request.POST.get("term")), None
                )
                if term is None:
                    raise ValidationError("Улирлаа сонгоно уу.")
                job = services.request_term_report(
                    actor=request.user, child=child, term=term,
                    request=request,
                )
            else:
                job = services.request_child_portfolio(
                    actor=request.user, child=child,
                    sections=request.POST.getlist("sections"),
                    request=request,
                )
```

In `templates/reports/request.html`, immediately after `{% csrf_token %}`, add:

```html
      <label for="id_report_type">Тайлангийн төрөл</label>
      <select name="report_type" id="id_report_type">
        <option value="child_portfolio">Хүүхдийн хувийн хавтас</option>
        <option value="term_report">Улирлын тайлан</option>
      </select>

      {% if terms %}
        <label for="id_term">Улирал (улирлын тайлан сонгосон бол)</label>
        <select name="term" id="id_term">
          {% for term in terms %}
            <option value="{{ term.pk }}">{{ term.name }}</option>
          {% endfor %}
        </select>
      {% endif %}
```

- [ ] **Step 8: Test the request screen**

Append to `apps/reports/tests/test_reports.py`:

```python
def test_the_request_screen_queues_a_term_report(client, world,
                                                 term_with_report):
    login(client, world["dulmaa"])

    response = client.post(
        reverse("reports:request", args=[world["bataa"].pk]),
        {"report_type": "term_report", "term": term_with_report.pk},
    )

    assert response.status_code == 302
    assert ReportJob.objects.filter(
        type=ReportJob.Type.TERM_REPORT
    ).exists()


def test_a_term_report_without_a_term_explains_itself(client, world,
                                                      term_with_report):
    login(client, world["dulmaa"])

    response = client.post(
        reverse("reports:request", args=[world["bataa"].pk]),
        {"report_type": "term_report"},
    )

    assert response.status_code == 200
    assert "Улирлаа сонгоно уу" in response.content.decode()
```

- [ ] **Step 9: Run everything**

```bash
docker compose exec -T web pytest -q
docker compose exec -T web ruff check .
```

Expected: all pass, lint clean. The suite should now be around 660.

- [ ] **Step 10: Commit**

```bash
git add apps/reports/ templates/reports/
git commit -m "Render the term report as a PDF

10.2's second report type, sharing the portfolio's @page rules so 10.3's
A4, page numbers and Cyrillic hold by construction rather than by being
remembered twice. Each of the four sections is guarded, so an unfilled one
prints nothing rather than a heading over blank space - D5's rule.

Three things in tasks.py needed changing, all found by reading it rather
than assuming: TEMPLATES is the whole of the type dispatch, _render called
build_context unconditionally, and _filename hardcoded _hawtas_ so a term
report would have downloaded named like a portfolio.

The job fails rather than rendering when the term is gone or the requester
may not read the report. A paper with headings and no content looks like a
bug to whoever downloads it, and a guardian's PDF must not answer
differently from the screen.

Rendered one and read the page, not just the assertions.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Update the documents

The roadmap and spec both say this is Phase 2. Leaving them wrong is how the next reader mistrusts the whole file.

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md`

- [ ] **Step 1: Amend D1**

In `ROADMAP.md`, find decision D1 (search for `### D1 —`). After its existing text, add:

```markdown
**Amended 2026-08-11.** The client confirmed the deferral, and then asked for
`TermReport` specifically to be pulled forward: §20-II lists "Улирлын тайлан"
among the mandatory MVP features and §21.7 makes it an acceptance criterion.
Built to `docs/superpowers/specs/2026-08-11-term-report-design.md`. The rest
of D1's list — the full portfolio timeline, milestones, photo albums, growth
tracking, `AnnualReport`, Excel, activity posts and consent records — stays
in Phase 2.
```

- [ ] **Step 2: Update the Phase 1 status table**

In `ROADMAP.md` section 7, row 8 currently reads:

```
| 8 | Basic development assessment — areas, levels 1–4, comment, progress | ✅ done | `apps/assessment/`, `test_assessment.py`; §6.3 group grid, §6.4 term matrix |
```

Replace the evidence column with:

```
`apps/assessment/`, `test_assessment.py`, `test_term_report.py`; §6.3 group grid, §6.4 term matrix and narrative report
```

Row 13 reads:

```
| 13 | Basic PDF export — child info, photo, portfolio, observations, assessments | ✅ done | `apps/reports/`, `test_reports.py`; §549 queue, §10.3 A4 + Cyrillic verified by parsing the output |
```

Append to its evidence: `; §10.2 term report added 2026-08-11`.

- [ ] **Step 3: Correct the older spec**

In `docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md`, the section 6.4 heading reads:

```
### 6.4 Assessment (8 tables) — Phase 1 except TermReport and AnnualReport, which are Phase 2
```

Replace with:

```
### 6.4 Assessment (8 tables) — Phase 1 except AnnualReport, which is Phase 2

`TermReport` moved into Phase 1 on 2026-08-11 — see
`2026-08-11-term-report-design.md`, which also drops the `teacher comment`
field listed below: `Assessment.comment` already holds the per-domain note.
```

- [ ] **Step 4: Verify the count line**

`ROADMAP.md` section 7 ends with a count derived from the status column. Re-derive it rather than trusting it — that line has been wrong twice:

```bash
grep -oE '✅ done|⚠️ partial|⬜ not started' ROADMAP.md | sort | uniq -c
```

Update the summary line if the numbers moved. They should not have: this task changed evidence, not status.

- [ ] **Step 5: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/
git commit -m "Record that the term report shipped in Phase 1

D1 deferred it and the client confirmed that; they then asked for this one
item back, because 20-II lists it as mandatory MVP and 21.7 makes it an
acceptance criterion. The rest of D1's list stays in Phase 2.

The 2026-08-07 spec still described TermReport as Phase 2 and still listed a
teacher_comment field the implementation deliberately does not have.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- [ ] `docker compose exec -T web pytest -q` — all pass, roughly 660 tests
- [ ] `docker compose exec -T web ruff check .` — clean
- [ ] A term report PDF has been rendered and **looked at**, not just asserted on
- [ ] `grep -rn "assessment:publish" apps/ templates/` returns nothing
- [ ] `ROADMAP.md` and both specs agree that this is Phase 1

RFP §21.7 is then demonstrable: the portfolio PDF and the term-report PDF both render, both in Cyrillic, both on A4.
