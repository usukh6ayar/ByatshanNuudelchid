# CLAUDE.md — ByatshanNuudelchid

Kindergarten child-development digital portfolio system. Django + PostgreSQL + Celery.

## THE RULES IN THIS FILE ARE MANDATORY

The rules below are not suggestions. Read them before writing code and verify against them after.

Code that violates a rule **does not get written**. If a rule blocks the task at hand, do not work around it — **stop and ask the user**. Every rule derives from a specific requirement in the RFP and maps directly to the acceptance criteria in §21.

**Required reading:**
- `Project_Info.md` — the client's RFP, in Mongolian. Final authority on requirements.
- `ROADMAP.md` — what ships in which phase, and current status.
- `docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md` — architecture and data model.

Precedence on conflict: RFP > ROADMAP > spec > CLAUDE.md > existing code.

**Language policy:** documentation and code (comments, identifiers, commit messages) in English. All user-facing UI text in Mongolian — RFP §611. `Project_Info.md` stays in Mongolian; it is the client's document.

---

## 1. Security rules (violating these means the system fails acceptance)

### 1.1 Authorization lives in exactly one place

Every access to child data goes through `apps/core/permissions.py`.

```python
# ✅ CORRECT
from apps.core.permissions import can_access_child, visible_kindergartens

def child_detail(request, child_id):
    child = get_object_or_404(Child, pk=child_id)
    if not can_access_child(request.user, child):
        raise Http404          # 404, not 403 — do not reveal existence
    ...

# ❌ WRONG — authorization logic inside the view
def child_detail(request, child_id):
    child = Child.objects.get(pk=child_id)
    if request.user.role == "teacher" and child.group in request.user.groups:
        ...
```

**Why:** RFP §21.2, §21.3, §21.4. If the logic exists in two places, the mobile API will answer differently. These are the most important 30 lines in the system.

### 1.2 Resolve the kindergarten from enrollment history, never from `Child.kindergarten_id`

`Child.kindergarten_id` is a denormalized "currently attending" field for listing and filtering only.

There is exactly one place it influences authorization: `child_kindergarten_history()` falls back to it when the child has **no enrollments at all**, so the staff who just registered a child are not locked out. Once any enrollment exists, the field is never read. Do not add a second exception.

```python
# ❌ WRONG — after a transfer, the previous teacher loses access to
#            observations they wrote themselves
if not user.has_membership(child.kindergarten_id):
    raise Http404

# ✅ CORRECT
if not can_access_child(user, child):   # reads the Enrollment history internally
    raise Http404
```

### 1.3 Never store the kindergarten in the session

There is no `request.session["kindergarten_id"]`. The kindergarten is always derived from the object being accessed. Session-trusted checks are exactly the attack surface RFP §21.4 targets.

### 1.4 Files are never directly reachable

```python
# ✅ CORRECT — signed URL issued only AFTER the permission check
GET /media/<uuid>/<variant>/  →  can_access_child()  →  signed URL (TTL 5 min)

# ❌ WRONG
MEDIA_URL = "/media/"                              # Django serving files directly
<img src="{{ photo.file.url }}">
<img src="https://bucket.s3.amazonaws.com/...">    # public bucket
```

`storage_key` is a random UUID path. The real filename lives only in `original_name`, for display. RFP §4.4, §15, §21.10.

### 1.5 No secrets in source

All configuration comes from `os.environ`. `.env` is gitignored. Every new setting gets a line in `.env.example`. RFP §690, §14.

### 1.6 Never trust a file's extension

Detect the real MIME type from content (`python-magic`). A `.jpg` can be an `.exe`. RFP §684.

---

## 2. Architecture rules

### 2.1 Business logic goes in `services.py`, not in views

```
apps/<domain>/
    models.py       data structure only, no logic
    services.py     ★ writes: create, update, transfer, finalize
    selectors.py    ★ reads: lists, filters, aggregates
    views/          Django template views → call services/selectors
    api/            DRF (phase §20-IV) → call THE SAME services
    admin.py
    tests/
```

A view's job: parse the request, call a service, return a response. Nothing else.

```python
# ✅ CORRECT
def observation_create(request, child_id):
    child = get_object_or_404(Child, pk=child_id)
    form = ObservationForm(request.POST)
    if form.is_valid():
        obs = observation_services.create_observation(
            actor=request.user, child=child, **form.cleaned_data)
        return redirect(obs)

# ❌ WRONG — logic in the view
def observation_create(request, child_id):
    obs = Observation.objects.create(...)
    obs.enrollment = Enrollment.objects.filter(child=child, status="active").first()
    AuditLog.objects.create(...)
    obs.save()
```

**Why:** the mobile app will call the same `services`. Logic written inside a view gets duplicated for mobile, the two drift, and §21 fails.

### 2.2 The web layer never calls its own API over HTTP

Template views call services as plain Python functions. There is no `requests.get("http://localhost:8000/api/...")`. RFP §17 (3-second page loads).

### 2.3 Configuration belongs in the database, not in code

Anything an administrator can edit is a **table**, not a `TextChoices` enum:

| Thing | Table | RFP |
|---|---|---|
| Development domains | `DevelopmentDomain` | §6.1 |
| Assessment levels | `AssessmentScale` / `AssessmentLevel` | §6.2 |
| Observation types | `ObservationType` | §5.2 |
| Milestone types | `MilestoneType` | §4.5 |
| Document categories | `DocumentCategory` | §9 |
| Consent types | `ConsentType` | §16 |

System-level values (user roles, record states) may remain `TextChoices`.

### 2.4 Django Admin must not bypass `services`

Every model registered in Django Admin:

```python
class SomeAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        some_services.save_from_admin(actor=request.user, obj=obj, ...)

    def delete_model(self, request, obj):
        some_services.soft_delete(actor=request.user, obj=obj)
```

Without this, admin actions skip the audit log and skip soft delete.

---

## 3. Database rules

### 3.1 Every model inherits a base class

```python
from apps.core.models import TenantScopedModel

class Observation(TenantScopedModel):    # kindergarten_id + timestamps
    ...                                  # + created_by/updated_by
                                         # + deleted_at/deleted_by
                                         # + manager that hides deleted rows
```

Models with no kindergarten (e.g. `GrowthStandardPoint`) inherit `BaseModel`.

### 3.2 `kindergarten_id` on every tenant-scoped table

Denormalized even when reachable through a relation. It lets a single filter enforce the isolation RFP §3.2 requires.

### 3.3 No hard deletes

```python
obj.delete()                      # ❌ never
services.soft_delete(actor, obj)  # ✅ sets deleted_at, deleted_by
```

`AuditLog` is the single exception: append-only, never updated, never deleted.

### 3.4 Review migrations by hand

After `makemigrations`, **read** the generated file. Check for accidental `RemoveField` or any data-losing operation. Production migrations must be reversible.

### 3.5 N+1 queries are forbidden

Every list view uses `select_related` / `prefetch_related`. Key screens get an `assertNumQueries` test. Every list is paginated (RFP §716).

When adding a filter, check the index table in spec section 10.

---

## 4. Testing rules

### 4.1 Authorization tests are mandatory

Every **new view** that touches child data requires these three tests:

```python
def test_teacher_from_another_group_gets_404()
def test_guardian_of_another_child_gets_404()
def test_user_from_another_kindergarten_gets_404()
```

**These must go through the HTTP client, not call the permission function directly:**

```python
# ✅ CORRECT — proves the view actually checks
response = client.get(reverse("children:detail", args=[other_child.id]))
assert response.status_code == 404

# ❌ INSUFFICIENT — passes even if the view never calls it
assert not can_access_child(user, other_child)
```

RFP §21.4 is a claim about request handling ("changing the URL must not
reveal another child's data"), not about a function's return value. A view
that forgets to call `can_access_child` passes every function-level test in
`apps/core/tests/test_permissions.py`. Those tests are necessary; they are
not sufficient.

No exceptions. RFP §21.2, §21.3, §21.4 are acceptance criteria — untested means not done.

### 4.2 Never claim a feature works without running the tests

Before saying "this works", **run** the tests and show the output. If tests fail, say so immediately.

---

## 5. UI rules

- All user-facing text in Mongolian (RFP §611). Code and identifiers in English
- Three separate layouts: `base_teacher.html`, `base_parent.html`, `base_admin.html` (RFP §13)
- Confirm before delete, toast after save, loading state for slow actions (RFP §624–626)
- Every form field has a `label`, every image an `alt`, every button a clear purpose (RFP §629–635)
- Mobile-first. It must work on a phone before it works anywhere else

---

## 6. Slow work goes to Celery

Never inside a request:

| Work | Where |
|---|---|
| PDF generation | Celery, tracked via `ReportJob` status (RFP §549) |
| Image conversion, thumbnails, WebP | Celery (RFP §17, §968) — Phase 2 and 3 |
| Excel export | Celery |
| Bulk notifications | Celery |
| Kindergarten-wide statistics | Celery beat, cached |

Phase 1 image upload is the exception: verifying the MIME type and stripping
EXIF are millisecond operations on a single photo, so they run inline. The
queue starts earning its keep once conversion arrives (spec section 7).

### 6.1 Always enqueue with `transaction.on_commit`

`ATOMIC_REQUESTS = True` wraps every request in a transaction. A bare
`.delay()` fires immediately, so the worker can start before the row it needs
has been committed — and then fails to find it.

```python
# ✅ CORRECT
job = ReportJob.objects.create(...)
transaction.on_commit(lambda: generate_report.delay(job.id))

# ❌ WRONG — race with the transaction
job = ReportJob.objects.create(...)
generate_report.delay(job.id)
```

### 6.2 Records that must survive a rollback

`AuditLog` rows for `login_failed` and `LoginAttempt` counters (RFP §3.1,
§971) exist precisely to record things that went wrong. If the surrounding
request raises, `ATOMIC_REQUESTS` rolls them back with it and the lockout
counter silently resets.

Authentication views therefore carry `@transaction.non_atomic_requests` and
manage their own transactions. Do not remove that decorator.

---

## 7. Working agreements

### 7.1 Scope

`ROADMAP.md` decides what belongs to which phase. Phase 1 is listed in its
section 7; spec section 1 mirrors it.

**Do not build a later phase's work on your own initiative.** Not in Phase 1:

- **Phase 2** — full portfolio timeline, milestones, photo albums, growth
  tracking, the annual report (§6.5), document library, Excel, activity posts,
  consent records, HEIC conversion. **The term report (§6.4) is not on this
  list**: it was pulled into Phase 1 on 2026-08-12, because §20-II makes it
  mandatory MVP and §21.7 an acceptance criterion — see ROADMAP D1
- **Phase 3** — surveys, analytics, health and safety, attendance, medication,
  voice notes, WebP and thumbnails, CDN, QPay payments
- **Never** — native mobile applications

If the user asks for one, it can be built — but first say which phase it
belongs to and ask whether to pull it forward. Pulling work forward without
saying so is how a ten-day delivery becomes a twenty-day one.

### 7.2 Commits

- Work on a feature branch, never commit directly to `main`
- Commit only when the user asks
- Reference the relevant RFP section in the commit message where useful

### 7.3 Reporting

- If tests fail, say they failed and show the output
- If a step was skipped, say it was skipped
- When something is done, say so plainly and without hedging

---

## 8. Common mistakes (do not make these)

| Mistake | Correct approach |
|---|---|
| `Child.objects.get(pk=id)` without a permission check | `can_access_child()` immediately after |
| Using `Child.kindergarten_id` for authorization | `can_access_child()` — it reads enrollments |
| Returning `403` when unauthorized | Return `404`. Do not reveal existence |
| `obj.delete()` | `services.soft_delete()` |
| `AuditLog.objects.create()` in a view | Inside the service, in the same transaction as the action |
| Generating a PDF inside a request | Celery + `ReportJob` |
| Defining development domains as `TextChoices` | The `DevelopmentDomain` table |
| Serving images by direct URL | `/media/<uuid>/<variant>/` + signed URL |
| Storing the kindergarten in the session | Derive it from the object |
| Saying "done" without running tests | Run them, show the output |
