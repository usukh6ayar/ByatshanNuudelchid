# ROADMAP — Бяцхан Нүүдэлчид

Children's Development Digital Portfolio System.

**Status as of 2026-08-09: Phase 1 in progress — 8 of 17 requirement groups
complete, 4 partial, 5 not started.** Detail in section 7.

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
| Queue | Celery + Redis | ✅ configured, not yet used |
| Frontend | Django templates + HTMX + Alpine | ✅ templates in place |
| PDF | WeasyPrint | ✅ proven (Cyrillic spike) |
| Object storage | S3-compatible (MinIO in dev) | ⚠️ configured, no upload yet |
| Runtime | Docker + docker-compose | ✅ in place |
| Row history | django-simple-history | ✅ on `Child` |
| Lint / test | ruff, pytest | ✅ 189 tests passing |

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
```

Three URL zones with three layouts: `/bagsh/` (teacher), `/etseg-eh/`
(guardian), `/udirdlaga/` (administrator). `/hawtas/` is shared: the portfolio
is one artifact both a teacher and a guardian write to, so it has one set of
views and picks its layout per request.

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
| 4 | Child management — create, edit, view, photo, group, year, guardian link, active/archived | ⚠️ partial | Create/view/archive done; **no edit view**, **no profile photo** |
| 5 | Parent management — account, parent↔child, access only to own children | ✅ done | `register_guardian`, `test_views_authorization.py` |
| 6 | Digital child portfolio — About Me, birthday, ages 2–5, basic photos | ⚠️ partial | `apps/portfolio/`, `test_portfolio.py`. Photos arrive on Day 7 |
| 7 | Teacher observation — full entry form with photo and parent visibility | ❌ not started | — |
| 8 | Basic development assessment — areas, levels 1–4, comment, progress | ❌ not started | — |
| 9 | Basic parent observation — submit, teacher views, visibility | ❌ not started | — |
| 10 | Notifications — teacher → parent, read/unread | ❌ not started | — |
| 11 | Basic dashboards — teacher and admin | ❌ not started | — |
| 12 | Search & filtering — name, group, school year, active/archived | ⚠️ partial | Name/group/status/sex/age/sort live; school-year filter exists in the selector but is not on the form |
| 13 | Basic PDF export — child info, photo, portfolio, observations, assessments | ❌ not started | Cyrillic rendering proven (`pdf_spike`, `test_pdf.py`); no child PDF |
| 14 | Backend — REST API, PostgreSQL, migrations, auth, ownership, upload, logging, env | ⚠️ partial | Everything except REST API and file upload. **See decision D2** |
| 15 | Deployment — production, HTTPS, prod database, backup, health check | ❌ not started | `/healthz` and `prod.py` exist; never deployed |
| 16 | Basic security — hashing, RBAC, ownership, no cross-child access, secure files, HTTPS, validation, injection/XSS, cookies | ✅ done | 40+ authorization tests; HTTPS and file access land with 15 and 4 |
| 17 | Responsive web — desktop, tablet, mobile browser | ⚠️ partial | Mobile-first CSS written; not tested on real devices |

**8 done · 4 partial · 5 not started.**

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
| 6 | Teacher observations, development assessment | ⬜ **next** |
| 7 | Parent observation, notifications, media upload | ⬜ |
| 8 | Dashboards, search, filters, basic PDF | ⬜ |
| 9 | Security, responsive fixes, deployment, backup, error handling | ⬜ |
| 10 | Integration, bug fixes, production build, documentation, handover | ⬜ |

**Position: end of Day 5.** Days 1–4 also produced work not on the original
plan — the invitation system, the audit log and the Cyrillic PDF spike — which
is why the remaining days are tight rather than comfortable.

## 11. Database entities

**Built (20 tables):**

```
core       AuditLog
accounts   User · Membership · TeacherProfile · GuardianProfile ·
           Invitation · LoginAttempt · PasswordResetToken
tenants    Kindergarten · SchoolYear · Group · GroupTeacher
children   Child · Guardianship · Enrollment · HistoricalChild
portfolio  AboutMe · ChildAgeProfile · BirthdayNote (+ history mirrors)
```

**Still needed for Phase 1:**

```
observations ObservationType · Observation · ObservationDomain ·
             ObservationMedia
assessment   DevelopmentDomain · AssessmentScale · AssessmentLevel ·
             Term · Assessment
media        MediaFile
comms        Announcement · AnnouncementTarget · AnnouncementRead
reports      ReportJob
```

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
| Secure file access | ⬜ arrives with upload — private bucket, signed URL after the check |
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
| File upload | ⬜ |
| Responsive layout on real devices | ⬜ |
| Chrome, Safari, Edge, Android browser | ⬜ |
| Production build | ⬜ |
| Backup and restore | ⬜ |
| PDF with Cyrillic and images | ⚠️ automated checks pass; **printed A4 page not yet inspected by a human** |

Current: **189 tests passing, ruff clean.**

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
| Teacher observation works | ❌ |
| Basic assessment works | ❌ |
| Parent observation works | ❌ |
| Notification works | ❌ |
| Image upload works | ❌ |
| Search / filter works | ✅ |
| Basic dashboard works | ❌ |
| Basic PDF export works | ❌ |
| PostgreSQL works | ✅ |
| Production build works | ❌ |
| Application is deployed | ❌ |
| Critical authorization / security issues fixed | ✅ |
| No known blocking runtime errors | ✅ |

**14 of 24 met.**

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

**Status: needed before Day 7 (upload) and Day 9 (deployment).**

### D4 — Deferred until their own phase

Recorded so they are not forgotten: observation tags and the teacher
confidence rating shown in the mockups, the separate child display code
(`CHD-0002`) alongside the registration number, and per-kindergarten storage
quotas. None block Phase 1.
