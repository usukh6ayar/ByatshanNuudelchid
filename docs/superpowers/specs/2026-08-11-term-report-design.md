# Term report (`TermReport`) — RFP §6.4, §10.2

**Status:** designed 2026-08-11, not yet built.

Adds the narrative half of RFP §6.4 and the second report type §10.2 asks
for. Extends `docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md`
section 6.4, which reserved `TermReport` for Phase 2.

---

## 1. Why this is being built now

`Project_Info.md` §20-II lists **"Улирлын тайлан"** among the fourteen
mandatory MVP features, and §21.7 makes it an acceptance criterion:
"Улирлын болон нэгдсэн PDF тайлан зөв үүсдэг байх."

Decision D1 moved it to Phase 2, and the client confirmed that deferral on
2026-08-11. It is being pulled forward anyway, deliberately and at the
user's request, because the acceptance criterion reads better met than
explained. `AnnualReport` (§6.5) stays in Phase 2 — this spec does not
touch it.

**What exists already.** `Assessment` records one level per development
domain per term, and `publish_term` opens a whole term's rows to the
guardians. What is missing is the per-child, per-term narrative §6.4 asks
for: давуу тал, дэмжих шаардлагатай чадвар, дараагийн улирлын зорилго,
эцэг эхэд өгөх зөвлөмж.

## 2. Data model

```
TermReport   child, enrollment, term,
             strengths, needs_support, next_goals, advice_for_parents,
             author, status: draft|final, finalized_at
             ⚠ unique(child, enrollment, term) where deleted_at IS NULL
```

Inherits `TenantScopedModel` (CLAUDE.md §3.1), so it carries
`kindergarten_id`, the audit columns and soft delete. Lives in
`apps/assessment/`, beside the rows it summarises.

Three decisions worth the ink:

**No `teacher_comment` field**, despite the 2026-08-07 spec listing one at
line 351. `Assessment.comment` already holds the teacher's note for each
domain, and `teacher-assessment-matrix.jpeg` shows it there, under the
domain it belongs to. A second general comment box would leave the teacher
guessing which one the family reads. §6.4's "багшийн тайлбар" is satisfied
by the per-domain comments the report prints alongside these four fields.

**`enrollment` is part of the uniqueness constraint**, matching
`Assessment`. After a transfer the previous kindergarten's report stays
attached to the enrollment it was written under, so
`visible_kindergartens()` keeps showing it to its author and to nobody
else (CLAUDE.md §1.2).

**`finalized_at` is not `auto_now`.** §6.4 wants "тайлан үүсгэсэн огноо",
meaning the moment the teacher declared it done. `updated_at` moves on
every keystroke-sized save and would misreport a typo fix as a new report —
the same trap `Assessment.assessed_at` documents.

### Indexes

```
(child, term)          the child screen
(kindergarten, term)   a future group-wide list
(enrollment, term)     transfer-aware lookups
```

Mirrors `Assessment`'s three, for the same reasons (spec section 10).

## 3. Services

Three functions in `apps/assessment/services.py`.

```python
save_term_report(*, actor, child, term, strengths, needs_support,
                 next_goals, advice_for_parents,
                 enrollment=None, request=None) -> TermReport

finalize_term(*, actor, child, term, request=None) -> TermReport

reopen_term(*, actor, child, term, request=None) -> TermReport
```

`save_term_report` is idempotent on `(child, enrollment, term)`, the same
shape as `save_assessment`: a second submission updates the row rather than
creating a second one, and the database constraint is the backstop for
§17's double-click rather than the mechanism. It reuses the existing
`_guard`, `assert_writable` and `_check_term` helpers unchanged.

### One button, both effects

`finalize_term` sets `status=final` and `finalized_at`, then **calls
`publish_term(visible=True)`** rather than reimplementing it. The teacher
has one mental model — the term is finished or it is not — and the
authorization rule for opening assessments stays in exactly one place
(CLAUDE.md §1.1). `reopen_term` is the same in reverse.

The existing "Эцэг эхэд нээх" control on the assessment screen is removed:
two ways to publish the same term is how the two drift apart. That means
the `assessment:publish` **route and view go too** — an endpoint with no
screen behind it is still reachable, still needs its authorization kept
correct, and is exactly the kind of thing that survives a refactor nobody
remembered it was part of. The `publish_term` *service* stays; it is what
`finalize_term` calls.

Its two view tests (`test_publishing_opens_the_term_to_the_guardian`,
`test_a_guardian_cannot_publish`) move to the new screen rather than being
deleted: the claims they make — publishing opens the term, a guardian
cannot publish — are still true and still worth pinning, just at a
different URL.

### Two refusals

**An empty report cannot be finalized.** If all four fields are blank,
`finalize_term` raises `ValidationError`. Showing a family a report with
four empty headings is worse than showing them nothing, and D5 settled the
same question for the printed portfolio.

**Editing a final report does not silently reopen it.** A teacher fixing a
typo must not make the report the family was reading disappear. The edit
goes live and `AuditLog` records who changed what. Reverting is
`reopen_term`, which is a decision rather than a side effect.

`reopen_term` is not in the RFP. It exists because a report finalized by
mistake otherwise has no route back except the database.

## 4. Screens

One new route in `apps/assessment/urls.py`:

```
/hawtas/<child_id>/unelgee/tailan/<term_id>/    name="term_report"
```

Teacher, `GET` and `POST`. Four labelled `<textarea>`s in the order
`teacher-assessment-matrix.jpeg` draws them in its right-hand panel, the
draft/final state visible at the top, and a "Дуусгаж эцэг эхэд нээх"
button. A finalized report shows "Буцааж нээх" instead.

`assessment/child.html` gains a link per term under the existing matrix,
each showing its report's state. **Guardians read the report inside that
same page**, not on a route of their own: one screen per child per term is
what a family can hold, and `child.html` already resolves visibility
correctly.

Guardians see `status=final` only. A draft is a working document.

## 5. PDF — §10.2's second type

```python
class Type(models.TextChoices):
    CHILD_PORTFOLIO = "child_portfolio", "Хүүхдийн хувийн хавтас"
    TERM_REPORT     = "term_report", "Улирлын тайлан"      # new
```

`request_term_report(actor, child, term)` in `apps/reports/services.py`
creates a `ReportJob` with `params={"term_id": term.pk}`. Everything
downstream — `ReportJob` status, `transaction.on_commit`, the signed-URL
download, expiry — is unchanged.

`tasks.py` needs three small changes. `TEMPLATES` gains the new type, which
is the whole of the template dispatch and already refuses an unknown type.
`_render` currently calls `build_context` unconditionally, so it grows a
branch to call `build_term_report_context` with the `Term` resolved from
`params["term_id"]`; a term id that no longer resolves fails the job with a
message rather than rendering a report about nothing. And `_filename`
hardcodes `_hawtas_`, so a term report would download under the portfolio's
name — it takes the same branch.

`templates/reports/term_report.html`: the logo and the child on a short
cover, that term's domain-by-domain levels with their comments, then the
four narrative sections. Same `@page` rules as the portfolio, so §10.3's
A4, page numbers and Cyrillic hold by construction.

`builder.build_term_report_context(viewer, child, term)` scopes its reads to
the viewer, exactly as `build_context` does. **A guardian requesting a PDF
of a draft term gets 404** — the permission answer must not differ between
the screen and the report.

`reports/request.html` gains "Улирлын тайлан" as a report type with a term
selector. The full builder in `teacher-report-builder-pdf.jpeg` is **not**
being built: its section list includes Ирц, Хоол and Судалгаа, which are
Phase 2 and Phase 3.

## 6. Testing

Authorization, through the HTTP client (CLAUDE.md §4.1) — mandatory for the
new screen:

```
test_teacher_from_another_group_gets_404
test_guardian_of_another_child_gets_404
test_user_from_another_kindergarten_gets_404
```

Behaviour:

| Test | What it pins |
|---|---|
| A guardian cannot see a draft report | §2.3 |
| A guardian sees it once finalized | §2.3 |
| `finalize_term` also publishes the term's assessments | the one-button contract |
| Finalizing an empty report raises | §4's refusal |
| Editing a final report leaves it final | no silent reopen |
| `reopen_term` hides the assessments again | the reverse |
| Saving twice updates one row | §17 |
| A report for another kindergarten's term raises | §3.2 |
| The PDF contains all four sections | §21.7 |
| A guardian's PDF of a draft term is refused | screen and report agree |
| A job whose `term_id` no longer resolves fails with a message | §549 — the row carries the reason |
| The downloaded file is not named `_hawtas_` | `_filename` branched |

The PDF test asserts on text extracted from the rendered file, not on the
template — the Day 10 lesson that a template can satisfy every structural
assertion and still print the wrong thing.

## 7. Out of scope

- `AnnualReport` (§6.5) — Phase 2, unchanged by this
- The full report builder from the mockup — Phase 2 and 3 sections
- Guardian acknowledgement ("Танилцсан") — RFP appendix, Phase 3
- Per-domain indicators — `Assessment.indicator` stays NULL

## 8. Files

| File | Change |
|---|---|
| `apps/assessment/models.py` | `TermReport` |
| `apps/assessment/migrations/` | one migration, reviewed by hand (§3.4) |
| `apps/assessment/services.py` | three functions |
| `apps/assessment/selectors.py` | `term_report`, `term_reports_for` |
| `apps/assessment/views.py` | `term_report` added, `publish` removed |
| `apps/assessment/urls.py` | one route added, `publish` removed |
| `apps/assessment/admin.py` | registered via `ServiceBackedAdmin` (§2.4) |
| `templates/assessment/term_report.html` | new |
| `templates/assessment/child.html` | per-term links; publish control removed |
| `apps/reports/models.py` | `Type.TERM_REPORT` |
| `apps/reports/services.py` | `request_term_report` |
| `apps/reports/builder.py` | `build_term_report_context` |
| `apps/reports/tasks.py` | `TEMPLATES` entry, `_render` branch, `_filename` branch |
| `templates/reports/term_report.html` | new |
| `templates/reports/request.html` | report-type selector |
| `apps/assessment/tests/test_term_report.py` | new |
| `apps/assessment/tests/test_assessment.py` | two publish-view tests retargeted |
| `apps/reports/tests/test_reports.py` | PDF tests |
| `ROADMAP.md` | D1 amended: this one item pulled forward |
