# ROADMAP — Бяцхан Нүүдэлчид

Children's Development Digital Portfolio System.

**Status as of 2026-08-10: Phase 1 in progress — 13 of 17 requirement groups
complete, 2 partial, 2 not started.** Detail in section 7.

This file is kept in sync with the codebase. Every "done" below names the file
or test that proves it.

---

## 0. Reconciling three numbering schemes

Three documents number their stages differently. When the client says "Phase 1"
they mean the commercial milestone in this file.

| Scheme | Where | Meaning |
|---|---|---|
| **Phase 1 / 2 / 3** | this file | Commercial delivery milestones, with budgets |
| Steps 1–11 | `docs/superpowers/specs/2026-08-07-…-design.md` §14 | Implementation order inside the build |
| §20 I / II / III / IV | `Project_Info.md` | The client's own RFP staging |

Rough mapping: ROADMAP Phase 1 ≈ RFP §20-II (MVP) minus growth tracking and
the document library; Phase 2 ≈ §20-II reporting plus §20-III; Phase 3 ≈ the
RFP's Module 1, Module 2 and appendix.

---

## 1. Project overview

A web system where kindergarten teachers record observations and assessments,
guardians contribute information about their child, and the system builds a
per-child development portfolio for ages 2–5 that can be exported as a
printable PDF.

`Project_Info.md` (the client's RFP, in Mongolian) is the primary source of
truth for product requirements. This roadmap schedules that work; it does not
replace it.

**Web only.** No iOS, Android, React Native or Expo application. The backend is
structured so a mobile client can be added later without rewriting business
logic, but no mobile work happens now.

## 2. Product goals

- Give teachers a fast way to record what they observe, without paperwork
- Give guardians a real window into their child's development
- Preserve a child's whole 2–5 history even across group, year and
  kindergarten changes
- Produce a printable Mongolian-language portfolio the family keeps
- Keep children's personal data safe enough to pass RFP §21

## 3. User roles

| Role | Scope | Source |
|---|---|---|
| `superadmin` | System-wide | Registers kindergartens, backups, all users |
| `admin` | One kindergarten | Teachers, groups, assignments, reports (RFP §2.1) |
| `teacher` | Own assigned groups | RFP §2.2 |
| `guardian` | Own linked children | RFP §2.3 |

Roles live on `Membership`, not on `User`, so one person can hold several —
a teacher whose own child attends the same kindergarten, or a guardian with
children at two kindergartens.

## 4. Technology stack

| Layer | Choice | Status |
|---|---|---|
| Backend | Django 5.2 (Python 3.13) | ✅ in place |
| Database | PostgreSQL 17 | ✅ in place |
| Queue | Celery + Redis | ✅ in use — report rendering, dashboard refresh, retention |
| Frontend | Django templates + HTMX + Alpine | ✅ templates in place |
| PDF | WeasyPrint | ✅ proven (Cyrillic spike) |
| Object storage | S3-compatible (MinIO in dev) | ✅ upload, signed URLs, `make storage` |
| Runtime | Docker + docker-compose | ✅ in place |
| Row history | django-simple-history | ✅ on `Child`, `AboutMe`, `ChildAgeProfile` |
| Lint / test | ruff, pytest | ✅ 397 tests passing |

## 5. Architecture overview

```
models/       data structure only
   │
services/     ALL business rules and authorization — single source of truth
   │
   ├── views/    Django templates (the web app)
   └── api/      DRF, added when a mobile client exists
```

```
apps/core/       base models, permissions, audit log, PDF, admin site
apps/accounts/   User, Membership, profiles, login, invitations
apps/tenants/    Kindergarten, SchoolYear, Group, GroupTeacher
apps/children/   Child, Guardianship, Enrollment
apps/portfolio/  AboutMe, ChildAgeProfile, BirthdayNote
apps/observations/
                 ObservationType, Observation, ObservationDomain
apps/assessment/ DevelopmentDomain, AssessmentScale, AssessmentLevel,
                 Term, Assessment
apps/media/      MediaFile, ObservationMedia — upload and signed serving
apps/comms/      Announcement, AnnouncementTarget, AnnouncementRead
apps/reports/    ReportJob — the §549 render queue
apps/dashboard/  no models; §12.1 and §12.2 figures
```

Three URL zones with three layouts: `/bagsh/` (teacher), `/etseg-eh/`
(guardian), `/udirdlaga/` (administrator). `/hawtas/` is shared: the portfolio,
the observations and the assessment record are all one artifact that a teacher
and a guardian both reach, so each has one set of views that picks its layout
per request. The §6.3 group grid is the exception — it is teacher-only and
lives under `/bagsh/`.

**The authorization rule that shapes everything:** a child's kindergarten is
derived from their `Enrollment` history, never from `Child.kindergarten_id`.
That field changes when a child transfers, which would otherwise silently
revoke the previous teacher's access to observations they wrote themselves.
Full reasoning in spec section 4.2.

## 6. Development phases

| Phase | Objective | Budget | Duration |
|---|---|---|---|
| **1 — Core MVP** | Core workflows working end to end | 3,000,000 ₮ | 10 days |
| **2 — Reporting & portfolio** | Full portfolio, gallery, growth, reports | 6,000,000 ₮ | TBC |
| **3 — Advanced SaaS** | Surveys, analytics, health, payments | 8,000,000 ₮ | TBC |

Phase 2 does not start until Phase 1 is stable and Phase 2 scope is
explicitly confirmed.

---

## 7. Phase 1 — Core MVP (current)

**Objective:** a functional, usable web MVP with the core workflows working
end to end.

**Dependencies:** hosting decision (section 15) blocks deployment.

### Status

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Authentication — admin/teacher/parent login, RBAC, hashing, logout, password reset | ✅ done | `apps/accounts/`, `test_login.py`, `test_password_reset.py` |
| 2 | Kindergarten & group management — CRUD, school year, teacher assignment | ✅ done | `apps/tenants/`, `/udirdlaga/`, `test_admin.py` |
| 3 | Teacher management — profile, assigned kindergarten/group/children | ⚠️ partial | Model + assignment done; no self-service profile edit screen |
| 4 | Child management — create, edit, view, photo, group, year, guardian link, active/archived | ⚠️ partial | Create/view/archive/photo done; **no edit view** |
| 5 | Parent management — account, parent↔child, access only to own children | ✅ done | `register_guardian`, `test_views_authorization.py` |
| 6 | Digital child portfolio — About Me, birthday, ages 2–5, basic photos | ✅ done | `apps/portfolio/`, `test_portfolio.py`; profile photo via `apps/media/` |
| 7 | Teacher observation — full entry form with photo and parent visibility | ✅ done | `apps/observations/`, `test_observations.py`; attachments in `test_media.py` |
| 8 | Basic development assessment — areas, levels 1–4, comment, progress | ✅ done | `apps/assessment/`, `test_assessment.py`; §6.3 group grid, §6.4 term matrix |
| 9 | Basic parent observation — submit, teacher views, visibility | ✅ done | Parent form, teacher review queue, §5.4 flow — `test_observations.py` |
| 10 | Notifications — teacher → parent, read/unread | ✅ done | `apps/comms/`, `test_announcements.py`; §8.1 targeting, unread badge |
| 11 | Basic dashboards — teacher and admin | ✅ done | `apps/dashboard/`, `test_dashboard.py`; §12.1 direct, §12.2 cached by Celery beat |
| 12 | Search & filtering — name, group, school year, active/archived | ✅ done | §11's full list, incl. school year, date interval, domain and level — `test_observations.py`, `test_views_authorization.py` |
| 13 | Basic PDF export — child info, photo, portfolio, observations, assessments | ✅ done | `apps/reports/`, `test_reports.py`; §549 queue, §10.3 A4 + Cyrillic verified by parsing the output |
| 14 | Backend — REST API, PostgreSQL, migrations, auth, ownership, upload, logging, env | ⚠️ partial | Everything except the REST API. **See decision D2** |
| 15 | Deployment — production, HTTPS, prod database, backup, health check | ❌ not started | `/healthz` and `prod.py` exist; never deployed |
| 16 | Basic security — hashing, RBAC, ownership, no cross-child access, secure files, HTTPS, validation, injection/XSS, cookies | ✅ done | 40+ authorization tests; HTTPS and file access land with 15 and 4 |
| 17 | Responsive web — desktop, tablet, mobile browser | ⚠️ partial | Mobile-first CSS written; not tested on real devices |

**13 done · 2 partial · 2 not started.**

> The Day 5 version of this line read "8 done · 4 partial · 5 not started",
> which did not match the table above it — the columns were never actually
> counted. The numbers here are.

### Delivered ahead of schedule

`AuditLog` (who viewed, edited and downloaded what) is a Phase 3 item in the
original brief. It was built in Phase 1 because RFP §971 requires it and
retrofitting an audit trail after data exists is painful. No extra cost.

### Deliverables

Working web application, source code, migrations, `.env.example`, seed data
command, test suite, deployment instructions, this roadmap.

### Explicitly out of scope for Phase 1

Full reporting engine · advanced gallery (HEIC, compression, albums, ordering)
· growth tracking · document library · Excel import/export · surveys ·
analytics · health & safety · attendance · medication · voice notes · CDN and
WebP · payments · smart pickup · mobile apps · AI · multi-language.

## 8. Phase 2 — Reporting & digital portfolio

**Objective:** expand the MVP into a complete web product.

Full digital portfolio (complete 2–5 history, timeline, gallery, milestones) ·
advanced gallery (multi-upload, albums, captions, categories, ordering,
HEIC/JPG/PNG, compression) · growth tracking with charts · full reporting
(child, seasonal, annual, development profile, growth, group, batch) ·
advanced PDF (A4, Cyrillic, page numbers, logo, photos, charts, print-ready,
optimized size) · teacher document library with versions and bookmarks ·
Excel import/export · improved dashboards.

**Dependencies:** Phase 1 stable; Celery worker in real use; object storage
decided and live.

**Out of scope:** everything listed under Phase 3.

## 9. Phase 3 — Advanced SaaS platform

Surveys and questionnaires · advanced analytics (start-vs-end, year-to-year,
radar, group and kindergarten comparison) · five-sheet Excel analytics ·
health & safety, attendance, allergies, vaccinations · medication management ·
daily highlights, voice notes, speech-to-text · advanced audit trail
(partially delivered in Phase 1) · WebP, thumbnails, CDN · tuition invoices,
QPay/SocialPay.

## 10. Current sprint — the 10-day Phase 1 plan

| Day | Plan | Status |
|---|---|---|
| 1 | Audit, architecture, database schema, auth foundation | ✅ done |
| 2 | Admin, kindergarten, group, school year | ✅ done |
| 3 | Teacher, child management | ✅ mostly (child edit view outstanding) |
| 4 | Parent, parent↔child, child profile | ✅ done |
| 5 | Digital portfolio — About Me, ages 2–5 | ✅ done |
| 6 | Teacher observations, development assessment | ✅ done |
| 7 | Parent observation, notifications, media upload | ⬜ **next** |
| 8 | Dashboards, search, filters, basic PDF | ⬜ |
| 9 | Security, responsive fixes, deployment, backup, error handling | ⬜ |
| 10 | Integration, bug fixes, production build, documentation, handover | ⬜ |

**Position: end of Day 8.** Days 1–8 also produced work not on the original
plan — the invitation system, the audit log, the administrator workspace and
the Cyrillic PDF spike — which is why the remaining days are tight rather than
comfortable. Full record in section 21.

## 11. Database entities

**Built — 34 models, plus 3 history mirrors:**

```
core         AuditLog
accounts     User · Membership · TeacherProfile · GuardianProfile ·
             Invitation · LoginAttempt · PasswordResetToken
tenants      Kindergarten · SchoolYear · Group · GroupTeacher
children     Child · Guardianship · Enrollment
portfolio    AboutMe · ChildAgeProfile · BirthdayNote
observations ObservationType · Observation · ObservationDomain
assessment   DevelopmentDomain · DevelopmentIndicator · AssessmentScale ·
             AssessmentLevel · Term · Assessment
media        MediaFile · ObservationMedia
comms        Announcement · AnnouncementTarget · AnnouncementRead ·
             AnnouncementAttachment
reports      ReportJob

history      HistoricalChild · HistoricalAboutMe · HistoricalChildAgeProfile
```

`DevelopmentIndicator` is built but unused: assessment is per domain in
Phase 1 (§6.4, §6.5 and §12.3 all aggregate that way). The table and the
nullable `Assessment.indicator` column exist so finer criteria can be added
later without migrating assessment rows that already exist.

**Nothing further is needed for Phase 1.** The remaining work is
deployment and hardening, not schema.

Conventions: `kindergarten_id` on every tenant-scoped table, soft delete
everywhere except `AuditLog`, authorship columns on every row, and
administrator-editable lists as tables rather than enums. Full schema in the
design spec section 6.

## 12. API modules

Phase 1 ships a server-rendered web application. Views call `services/`
directly as in-process Python — no HTTP round trip to our own API, which would
double latency for no benefit (RFP §17 wants 3-second page loads).

The service layer is the API boundary. When a mobile client exists, DRF
endpoints call the same functions, so the rules cannot drift between web and
mobile. **See decision D2.**

## 13. Security requirements

| Requirement | Status |
|---|---|
| Password hashing | ✅ Django hasher; 8+ chars with upper, lower and digit |
| Role-based authorization | ✅ from `Membership` |
| Backend ownership checks | ✅ `apps/core/permissions.py`, one place only |
| No cross-child access by changing an id | ✅ verified end to end: 200 for own, 404 for another |
| Secure file access | ✅ private bucket, permission check then signed URL — `apps/media/` |
| HTTPS | ⬜ arrives with deployment; `prod.py` already sets HSTS and secure cookies |
| Input validation | ✅ forms and service-level validation |
| Injection / XSS | ✅ ORM parameterisation, template auto-escaping |
| Secure cookies and sessions | ✅ HttpOnly, SameSite, Secure in production |
| Login throttling | ✅ 5 failures → 15 minutes, survives request rollback |
| Audit log | ✅ login, failures, views, changes, invitations, activations |
| No secrets in source | ✅ all config from the environment; `.env` gitignored |

404 rather than 403 on unauthorized access, always: a 403 confirms the record
exists, which is itself a disclosure.

## 14. File storage strategy

Child photos are sensitive (RFP §4.4, §15, §21.10).

- Files are never reachable by URL. `GET /media/<uuid>/<variant>/` runs the
  permission check, then issues a short-lived signed URL
- `storage_key` is a random UUID path; the real filename is display-only
- MIME type is detected from content, never from the extension
- Storage is behind Django's storage abstraction, so local, MinIO and S3 are
  interchangeable

**Phase 1 scope: simple secure upload only** — child profile photo and
observation attachments. HEIC conversion and compression are Phase 2; WebP,
thumbnails and CDN are Phase 3. **See decision D3.**

## 15. Deployment strategy

```
Development   docker-compose: web, worker, beat, postgres, redis, minio
Staging       same shape, separate database
Production    web, worker, beat, postgres, redis + external object storage
```

All configuration from environment variables, `/healthz` checks database and
cache, daily `pg_dump` with a documented restore procedure, and no production
data or real child photos in development (RFP §707 — `seed_demo` refuses to
run with `DEBUG` off).

> ⚠️ **Blocking unknown.** Hosting and object storage are still undecided.
> `.env.example` ships MinIO defaults as a placeholder. Deployment is a Phase 1
> Definition-of-Done item, so this needs a decision before Day 9.

## 16. Testing checklist

Formal QA is the client's. Before handover we still verify:

| Check | Status |
|---|---|
| Application runs, no obvious runtime errors | ✅ |
| Authentication and logout | ✅ 20 tests |
| Role permissions and ownership | ✅ 40+ tests, plus live HTTP verification |
| CRUD operations | ⚠️ child edit missing |
| File upload | ✅ 34 tests, incl. MIME spoofing and EXIF GPS |
| Responsive layout on real devices | ⬜ |
| Chrome, Safari, Edge, Android browser | ⬜ |
| Production build | ⬜ |
| Backup and restore | ⬜ |
| PDF with Cyrillic and images | ⚠️ a real child portfolio renders and parses back correctly; **printed A4 page not yet inspected by a human** |

Current: **397 tests passing.**

## 17. Definition of done — Phase 1

| Criterion | Status |
|---|---|
| Admin can log in | ✅ |
| Teacher can log in | ✅ |
| Parent can log in | ✅ |
| Role permissions work | ✅ |
| Admin can manage kindergarten / group / teachers | ✅ |
| Teacher can manage children | ⚠️ edit view missing |
| Parent can be linked to children | ✅ |
| Parent can only see their own children | ✅ |
| Child profile works | ✅ |
| Digital portfolio works | ✅ |
| Age 2–5 information works | ✅ |
| Teacher observation works | ✅ |
| Basic assessment works | ✅ |
| Parent observation works | ✅ |
| Notification works | ✅ |
| Image upload works | ✅ |
| Search / filter works | ✅ |
| Basic dashboard works | ✅ |
| Basic PDF export works | ✅ |
| PostgreSQL works | ✅ |
| Production build works | ❌ |
| Application is deployed | ❌ |
| Critical authorization / security issues fixed | ✅ |
| No known blocking runtime errors | ✅ |

**22 of 24 met.**

## 18. Out of scope for Phase 1

See section 7. In short: anything in Phase 2 or Phase 3, plus native mobile
applications in any form.

## 19. Future features

Beyond Phase 3, the RFP anticipates: multi-language, AI-assisted observation
suggestions, digital signatures, integration with government systems, and
push notifications.

## 20. Development rules

Binding rules are in `CLAUDE.md` and are not restated here. The ones that
shape scheduling:

- Authorization lives in exactly one file; every new view touching child data
  ships with three 404 tests written through the HTTP client
- Business logic in `services.py`, never in views — the mobile client will
  call the same functions
- No hard deletes; `AuditLog` is append-only
- Slow work (PDF, image processing) goes to Celery, never inside a request
- Never claim a feature works without running the tests and showing the output
- Update this roadmap after every major feature: mark completed items, record
  architectural decisions, record blockers

---

## 21. Progress log

What was actually delivered, in order, with the decisions and blockers each
day produced. Updated after every major feature.

### Day 1 — 2026-08-07 · Foundation
`115b08d` `0dad690`

Docker environment (web, worker, beat, PostgreSQL 17, Redis, MinIO), Django
project with split settings, `User` / `Membership`, the authorization layer,
and the Cyrillic PDF spike. Then the full authentication flow: login by
username, email or phone; lockout; password reset; `AuditLog`.

**Decisions.** Authorization derives from `Enrollment` history, not
`Child.kindergarten_id` — the field changes on transfer and would silently
revoke a teacher's access to their own observations. Roles live on
`Membership`, not `User`, so one person can be both a teacher and a guardian.
Authentication views carry `transaction.non_atomic_requests`, or
`ATOMIC_REQUESTS` rolls the lockout counter back with the failed request.

**Risk closed.** Mongolian Cyrillic renders in PDF: DejaVu Sans embedded in
the image covers Ө ө Ү ү, verified by reading the font's character map and by
parsing the generated file. A printed A4 page still needs a human's eyes.

### Day 2 — 2026-08-08 · Administrator workspace
`14bf0e4`

`/udirdlaga/` as a separate admin site: kindergartens, school years, groups,
teacher assignment. Organizational rules in `tenants/services.py`.

**Decisions.** Admin access comes from `Membership`, not `is_staff` — granting
a director `is_staff` would hand them Django's raw superuser site as a side
effect. Every list and every foreign-key dropdown is filtered by the user's
kindergartens, and object lookups go through `get_queryset` so another
kindergarten's record is *not found* rather than *forbidden*.

**Security fix.** Django's own admin login was a second authentication path
that skipped the lockout and the audit log, leaving administrator accounts as
the only unthrottled way in. It now redirects to the project's login view.

### Day 3–4 — 2026-08-08 · Children, guardians, onboarding
`c47fd67` `591a91e` `5e70335` `045587b`

Client mockups read and catalogued. Design decisions applied to the auth
screens. Invitation-based account creation. Child registration, the teacher
list and detail screens, and the guardian home.

**Decisions.** Nobody self-registers: the `Guardianship` row *is* the §21.3
authorization boundary, so it cannot be created by the person it grants access
to. Staff create the account; the person activates it and sets their own
password. Two delivery paths — an emailed link, and identifier plus a
six-digit code on paper, since Mongolian guardians frequently have no email.
The code is never checked alone; six digits is searchable, but not when the
attacker must also know the phone number and beat the attempt throttle.

`visible_children()` was added as the list-level counterpart to
`can_access_child()`, with a test asserting the two agree over every user and
child in the fixtures — a child listed but 404ing when opened is a bug, and
the reverse is a disclosure.

**Bug fixed.** `unique(child, school_year)` blocked RFP §3.4: a mid-year group
change puts two enrollments in one year. Now unique on *active* enrollments
only, which is what the rule actually means.

### Day 5 — 2026-08-09 · Portfolio and documentation alignment
`4694c8b` `c97f2f1` `323cebe` `93f5db0` `2e8c38f`

This roadmap written from the client's brief. All other documents aligned to
its phase boundaries. Then `apps/portfolio`: About Me, birthday notes, and the
four age pages.

**Decisions.** D1 and D2 resolved — growth tracking, the document library,
term and annual reports, milestones, albums, activity posts and consent move
to Phase 2; the REST API stays deferred. The media plan corrected: Phase 1
verifies the MIME type and strips EXIF GPS only, and does both inline.

Zodiac sign and year animal are computed, never stored (§206). The portfolio
has one set of views for both roles, because it is one artifact both write to;
duplicating them per role would be two copies of the same rules drifting
apart. The two notes are kept apart in the service, not the template.

**Known limitation.** The year animal uses the calendar year. Цагаан сар falls
in January or February, so January birthdays may be off by one until a lunar
table is added. Documented in `zodiac.py`.

### Day 6 — 2026-08-09 · Observations and development assessment

`apps/observations` and `apps/assessment`: the §5.1 entry form, the §5.4
parent-submission and review flow, the §6.4 term matrix on a child's page,
and the §6.3 grid that assesses a whole group from one screen. The nine
development domains, the four levels and the four observation types ship as
system defaults.

**Decisions.** The configuration lists are **system-wide with per-kindergarten
additions** — `kindergarten = NULL` is the shared default, and a kindergarten
adds rows rather than editing them. One director renaming "Хэл яриа" must not
rename it for everyone. The "system OR mine" condition lives in one selector
per app; copied into each screen it would eventually be forgotten in one, and
that screen would leak another kindergarten's configuration.

Assessment stays **per domain**, not per indicator: §6.4, §6.5 and §12.3 all
aggregate that way. `DevelopmentIndicator` and the nullable
`Assessment.indicator` are built and left empty so finer criteria can arrive
without migrating existing rows.

A school year now creates its four terms on save. `Assessment.term` is
required, so a year without terms is one in which nothing can be assessed —
a state a director would have hit before ever reaching the term screen.

**Authorization widened, deliberately and narrowly.** `can_record_for_child`
joins `can_access_child` in `permissions.py`. Reading a child's record and
writing a professional one about them are different rights: a guardian may
read the portfolio and write their own half of it (§2.3), but observations
and assessments are the teacher's record. It is defined as
`can_access_child` *minus the guardian branch* — the first draft was "has
access and holds a staff role somewhere", and a test caught what that
allows: a teacher whose own child attends the same kindergarten could file a
teacher observation about their own child while teaching a different group.

**Bug fixed, and it was ours.** The `django_db(transaction=True)` tests — the
authentication ones, which need the lockout counter to survive a rollback —
flush every table at teardown, taking migration-created rows with them. Any
test collected afterwards found an empty configuration. The system defaults
now live in `apps/assessment/defaults.py`, called both by the migrations and
by an autouse fixture in `conftest.py`. A full-suite pass before this fix was
not evidence of anything; it depended on which database happened to be reused.

**Second security fix, from review.** `can_record_for_child` surviving a
transfer is correct — but it does not follow that a teacher may write *new*
records at the kindergarten the child moved to, which is a row inside
another tenant (§3.2). Every write now also passes `assert_writable`, which
asks `visible_kindergartens` rather than inventing a second rule. The same
gate covers editing, archiving, reviewing, and opening a term to the
guardians: after a transfer a term holds rows from both sides, and each
kindergarten publishes only its own.

Three smaller ones with it: the observation domain list was validated but
the *assessment* domain was not, so a crafted request could attach another
kindergarten's private domain and pollute its §12.3 averages; `assessed_at`
was `auto_now`, so publishing a term restamped every row as if the children
had just been reassessed; and the §6.3 grid built a `pk__in` straight from
attacker-controlled form field names, where a non-numeric key was a 500
rather than a no-op. `Term` also gained the `kindergarten` column §3.2
requires on every tenant-scoped table.

**Known limitation.** An observation's evidence photo and attachment (§5.1)
and the §5.3 side-by-side comparison of a child's work both need `MediaFile`,
which arrives with upload on Day 7. The parent submission screen is Day 7 as
well; the service, the review flow and the guardian's read path are done and
tested.

### Day 7 — 2026-08-09 · Parent observations, media, announcements

Three things that had been waiting on each other. `apps/media` — upload,
storage and the signed-URL serving path. `apps/comms` — §8.1 announcements
with targeting and read receipts. And the §5.4 screens that the Day 6
service layer had no interface for.

**Files are never reachable by URL.** `GET /media/<uuid>/<variant>/` runs
`can_access_child` and only then produces a link (spec section 7.1). The path
in the URL is a `public_id` UUID, separate from both the primary key and the
storage key, so files are neither enumerable nor a map of the bucket layout.
`storage_key` is a random sharded UUID path; the real filename is display-only
and never reaches the backend, because it usually contains the child's name.

**EXIF GPS is stripped on every upload**, which the RFP does not ask for. A
phone embeds the coordinates of wherever the photo was taken, so a leaked
photo taken at home carries the child's home address. The strip is a
re-encode through Pillow, which also discards anything else a file might be
carrying. The test builds a JPEG that really has coordinates in it and reads
them back afterwards — a test that cannot create the dangerous input proves
nothing.

**MIME type is read from the content**, never the extension or the browser's
claim (§684). Three tests push a shell script, a PDF and random bytes through
as `.jpg`.

**Decisions.** Development points at MinIO through the same S3 backend
production uses, so the signing path is exercised while building rather than
discovered on deployment day; `make storage` creates the bucket, because
MinIO starts with none and the failure otherwise reads as
`NoSuchBucket` with nothing on screen to explain it. `MEDIA_REDIRECT_SIGNED_URL`
decides whether the view redirects or streams — production redirects so the
object store moves the bytes; development streams because MinIO signs for
`minio:9000`, a hostname only the containers can resolve. Both branches run
the permission check first, and both are tested.

`file_url` accepts **only absolute URLs**. A local backend answers `url()`
with a path instead of raising, and redirecting there would 404 today — or,
if anyone ever set `MEDIA_URL`, hand the file over with no check at all.

The parent's submission form is a separate screen from the teacher's rather
than the same one with fields hidden. §5.1 asks a teacher for a professional
judgement — the domains, the support plan, who may see it — and none of that
is a parent's to give. Opening the teacher's form as a guardian is now a 404
rather than a form that offers fields the service will refuse.

**Announcement targeting is a table, not a column.** §8.1 allows one notice
aimed at three groups plus two named children at once. No target rows means
the whole kindergarten. The reach rule is written once, in
`comms/selectors.py`, and starts from `visible_children`, so no targeting
choice can reach a family that is not connected to the child. Unlike the
§6.3 grid, an unreachable id here is **refused rather than dropped**: a lost
keystroke is an annoyance, a misdirected message about a child is not.

**Known limitation.** HEIC uploads are refused with a sentence in Mongolian
rather than converted — the conversion is Phase 2 (spec section 7). Thumbnails,
WebP and multi-file upload are Phase 2 and Phase 3.

### Day 8 — 2026-08-10 · PDF, dashboards, the rest of the filters

`apps/reports` and `apps/dashboard`, plus the §11 filters that were written
in a selector on Day 3 and never reached a form.

**The queue finally earns its keep.** A child's portfolio runs to several
pages with a photograph; §549 says the system must not freeze while it
renders, so the request creates a `ReportJob` and returns, and a Celery
worker does the work. The dispatch goes through `transaction.on_commit` —
`ATOMIC_REQUESTS` wraps the whole request, and a bare `.delay()` can reach a
worker before the row it needs is committed (CLAUDE.md §6.1). There is a
test for exactly that, because the failure mode is a worker that
intermittently finds nothing.

**The PDF is verified by reading it back.** The Day 1 spike proved DejaVu
Sans covers Ө and Ү; this renders a real portfolio and parses the output
with `pypdf` to confirm the child's name, the section headings and the page
counter survived. Page count comes from WeasyPrint's own layout rather than
from re-parsing the file, so production needs no PDF library for one
integer.

**A report contains what the requester may see, not what the worker could
reach.** `builder.py` scopes every queryset to `job.requested_by`: a
guardian's copy holds approved, visible observations and published
assessments, a teacher's holds theirs. Rendering everything and hiding the
rest in the template would be one forgotten `{% if %}` away from handing a
family another kindergarten's notes. A job also belongs to whoever asked for
it — a guardian opening a teacher's job id gets 404, not the teacher's copy.

**Decisions.** `CACHES` now points at Redis. §12.2's figures are computed by
a beat task and read by the web process; Django's default cache is
per-process memory, so the worker would have filled a cache nobody else
could see and every page load would have recomputed anyway. The beat
schedule lives in code, not in the database, so a fresh deployment has it
without anyone remembering to click. §12.1's teacher dashboard is *not*
cached: a teacher recording an observation and not seeing the count move is
worse than the query, and one group is twenty-five children.

Landing after login now goes to the dashboard rather than straight to a list
of names — §12.1 is a list of what a teacher needs to notice on arriving.

**Known limitation.** `ruff` was not re-run after this day's changes: Docker
Desktop died mid-session and its cache directory was left corrupted. The
test suite ran in full afterwards and passed; the lint gate is outstanding
and is the first thing to run on Day 9.

### Running totals

| | Day 1 | Day 2 | Day 4 | Day 5 | Day 6 | Day 7 | Day 8 |
|---|---|---|---|---|---|---|---|
| Tests | 64 | 93 | 156 | 189 | 278 | 346 | **397** |
| Models | 14 | 14 | 15 | 18 | 27 | 33 | **34** |
| DoD met | — | — | 12/24 | 14/24 | 16/24 | 20/24 | **22/24** |

Models excludes the three `django-simple-history` mirrors.

---

## Decisions

Recorded rather than left implicit, per the original brief's instruction to
surface ambiguity. **D3 is still open and now blocking.**

### D1 — MVP scope: growth tracking and document library ✅ resolved 2026-08-09

**Decision: this roadmap governs. Both move to Phase 2**, along with the full
portfolio timeline, milestones, photo albums, term and annual reports, Excel,
activity posts and consent records.

Design spec section 1 has been rewritten to match, with section 1.5 recording
what moved and why. `CLAUDE.md` §7.1, `README.md` and `docs/design/INDEX.md`
now point here for phase boundaries.

### D2 — "Clean REST API" as a Phase 1 item ✅ resolved 2026-08-09

**Decision: the deferral stands.** Phase 1 ships a server-rendered web
application whose views call `services/` in process. Line 72 of the original
brief requires only that the backend be *designed* to support a mobile client
later, which the service layer does.

Revisit if a third party needs to integrate before the mobile client exists;
adding DRF on top of the existing services is roughly two days.

### D3 — Hosting and object storage

Undecided, and now blocking. Deployment is a Phase 1 Definition-of-Done item
and file upload needs a storage target.

**Options:** VPS + Docker Compose (Hetzner/DigitalOcean, ~$20–40/month, full
control, matches RFP §19 ownership terms) · managed PaaS (Railway/Render,
less DevOps, ~$30–60/month) · either one paired with Cloudflare R2 for files.

**Status: no longer blocks upload.** The media layer runs against any
S3-compatible bucket through Django's storage abstraction, with MinIO
standing in locally, so the choice of provider is a deployment-time setting
rather than a code decision. **Still blocks Day 9 deployment.**

### D4 — Deferred until their own phase

Recorded so they are not forgotten: observation tags and the teacher
confidence rating shown in the mockups, the separate child display code
(`CHD-0002`) alongside the registration number, and per-kindergarten storage
quotas. None block Phase 1.
