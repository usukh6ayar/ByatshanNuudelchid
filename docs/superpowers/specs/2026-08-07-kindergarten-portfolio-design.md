# Child Development Digital Portfolio — Architecture & Data Model

**Date:** 2026-08-07
**Source document:** `Project_Info.md` (client RFP, in Mongolian)
**Status:** Approved design. Implementation plan is the next step.

This document covers **how** to build what the RFP specifies. The RFP defines **what**. On conflict, the RFP wins.

RFP section references appear as §N throughout.

---

## 1. Scope

### 1.1 In scope (RFP §20-II, the MVP)

- Login and authorization for admin / teacher / guardian
- Kindergarten, school year, group and teacher management
- Child registration, linking children to guardians
- Child portfolio: About Me, per-age pages (2–5), milestones, photo albums
- Teacher observations and parent-submitted observations
- Development assessment, term reports, annual reports
- Growth measurements and charts
- Announcements and activity posts
- Document library
- PDF reports generated on a background queue
- Audit log and consent records
- Backups

### 1.2 Deliberately deferred

The following are **structurally accommodated** but not implemented in this phase:

| Deferred | RFP source |
|---|---|
| Surveys, questionnaires, analytics | Module 1 |
| Safety and health incident records | Module 2 |
| Attendance, medication reminders, allergy/menu checks | Appendix |
| QR / PIN-code child pickup | Appendix |
| Voice notes (speech-to-text) | Appendix |
| Report acknowledgement (digital signature) | Appendix |
| Tuition billing, QPay/SocialPay | Appendix |
| Excel import/export, batch reports, work comparison | §20-III |
| Mobile app (Android/iOS) | §20-IV |
| Multi-language | §20-IV |

**Rationale:** the RFP bundles three products of different sizes. Payments, attendance and pickup are effectively a separate system. Starting everything at once is the most common way projects like this fail. §20 already defines the phasing.

---

## 2. Technology choices

| Layer | Choice | Rationale |
|---|---|---|
| Backend | **Django (Python)** | The existing Flask prototype is Python, so domain logic ports over. ORM + migrations + permission layer + admin scaffolding included. Covers §14 in full |
| Database | **PostgreSQL** | §14 forbids SQLite in production |
| Queue / worker | **Celery + Redis** | §549 "the system must not freeze while generating reports" — PDFs and image processing |
| Frontend | **Django templates + HTMX + Alpine.js** | §17 3-second page loads, §13 simple interface. No separate SPA |
| PDF | **WeasyPrint** | §10.3 Mongolian Cyrillic — full control over font embedding |
| Images | **Pillow / pillow-heif** | §4.4 HEIC support, §968 WebP |
| File storage | **S3-compatible object storage** (Cloudflare R2 suggested) | §14, §968 CDN |
| Runtime | **Docker + docker-compose** | §14 |
| Row history | **django-simple-history** | §4.1 "record who changed what and when" |

### 2.1 Repository layout

```
kinder-web/       ← Django. models + services + web + (later) API. ONE deployment
kinder-mobile/    ← starts in phase §20-IV. Connects over the API
```

**The API is not built now.** With the service layer in place, adding DRF when mobile starts is a matter of days.

---

## 3. Core architectural principles

### 3.1 Layering

```
models/       data structure. No logic
   │
services/     ★ ALL business rules, authorization, transactions
   │          single source of truth
   ├── views/    (web, Django templates)  → call services directly
   └── api/      (DRF, for mobile, later) → call THE SAME services
```

**Hard rule:** business logic and authorization checks never live in views. If a rule like "may this guardian see this child" hides inside a template view, mobile will get a different answer. §21.2–21.4 exist to catch exactly that.

**The web layer never calls its own API over HTTP.** Templates call `services/` as in-process Python. A self-directed network round trip doubles latency and puts the §17 3-second target at risk for no benefit.

### 3.2 URL zones

```
/                → login, public pages
/bagsh/...       → teacher screens       (base_teacher.html)
/etseg-eh/...    → guardian screens      (base_parent.html)
/udirdlaga/...   → §2.1 admin screens    (base_admin.html)
/media/...       → signed URL, issued after the permission check
/django-admin/   → superuser only. IP-restricted or disabled in production
/healthz         → §14 health check
```

Three separate layouts: §13 requires fast data entry for teachers, clarity for guardians, and dense tables for admins. One layout cannot serve all three.

### 3.3 The admin system

- **Not a separate repo, not a separate deployment** — `can_access_child()` must not exist in two places
- Inside `/udirdlaga/`, plain CRUD (kindergartens, groups, teachers, criteria configuration) is built on Django Admin, translated to Mongolian and themed
- Dashboards (§12.2), audit log browsing, password resets and account locking are **custom-built**
- Where Django Admin is used, override `save_model()` and `delete_model()` to route through `services/`. Otherwise admin actions skip the audit log and soft delete

---

## 4. Authorization and the multi-kindergarten model

### 4.1 Users and memberships

```
User        credentials (username, email, phone, password hash). No permissions.
Membership  (user, kindergarten, role, is_active, start date)
```

One person can hold several memberships. This handles real cases:

- A teacher whose own child attends the same kindergarten → both `teacher` and `guardian`
- A teacher working at two kindergartens
- A guardian with children at two kindergartens (siblings split, or a child transferred)

**Roles:**

| role | Scope | Notes |
|---|---|---|
| `superadmin` | System-wide (`kindergarten` null) | Register kindergartens, deactivate them, backups, all users |
| `admin` | One kindergarten | Create teachers, set up groups, assign staff, reports, statistics |
| `teacher` | One kindergarten | §2.2 |
| `guardian` | One kindergarten | §2.3 |

§2.1 lists system-level and kindergarten-level actions together. In a multi-tenant system the director of kindergarten A must not be able to create teachers at kindergarten B.

### 4.2 Authorization derives from enrollment history

Two separate questions. Do not conflate them.

```python
# services/permissions.py — every access goes through here

def can_access_child(user, child) -> bool:
    """May this user see this child at all?"""

    # GUARDIAN → the Guardianship row is itself the authorization.
    #            Independent of kindergarten: a transfer does not
    #            change who the parent is.
    if Guardianship.objects.filter(child=child, guardian_user=user,
                                   can_view=True).exists():
        return True

    # TEACHER → assigned via GroupTeacher to any group the child has
    #           ever been enrolled in (any school year)
    if GroupTeacher.objects.filter(
            teacher_membership__user=user,
            group__enrollment__child=child).exists():
        return True

    # ADMIN → holds an admin membership in any kindergarten the child
    #         has ever been enrolled at
    if user.has_membership_in(child_kindergarten_history(child),
                              roles=["admin", "superadmin"]):
        return True

    return False


def visible_kindergartens(user, child) -> set[int]:
    """Which kindergartens' records are visible?"""
    history = child_kindergarten_history(child)   # Enrollment → Group
                                                  #   → SchoolYear → Kindergarten
    if is_guardian_of(user, child):
        return history          # guardians see the whole history  (§961)
    return history & user.kindergarten_ids  # staff see only their own part
```

**Three rules:**

1. **The kindergarten is derived from `Enrollment` history, not from `Child.kindergarten_id`.** That field means only "currently attending" and exists for listing and filtering. It is never an authorization input. This is what lets a teacher keep access to observations they wrote after the child transfers away.

2. **Access to a child is not access to every record about that child.** A teacher at kindergarten A does **not** see observations written later at kindergarten B. Every record carries its own `kindergarten_id` (principle 1 in section 5), and queries filter through `visible_kindergartens()`. This is where that principle pays off.

3. **Never store the kindergarten in the session.** The §21.4 attack ("change the URL, read someone else's data") succeeds precisely when a page forgets to re-check a session value. Deriving from data makes the check impossible to forget.

**The guardian home screen** lists all their children grouped by kindergarten, each tagged. Announcements and posts arriving from multiple kindergartens are labelled by source. This satisfies §2.3 ("choose your child if you have more than one").

### 4.3 Authentication

- Web: session cookie with `HttpOnly`, `Secure`, `SameSite=Lax` per §15
- Mobile (later): token. Both resolve to the same `User` / `Membership` model
- §3.1: log in with username, email or phone. Not three login systems — one `User` with three unique fields

---

## 5. Seven database principles

These apply to every table.

1. **Every tenant-scoped table carries `kindergarten_id`** even when it is reachable through a relation. One filter then enforces the isolation §3.2 requires.
2. **Soft delete** — `deleted_at`, `deleted_by`. §3.4. The default manager hides deleted rows.
3. **Every row records `created_at`, `created_by`, `updated_at`, `updated_by`** — §4.1, §5.1.
4. **Configuration lives in the database, not in code** — §5.2, §6.1 and §6.2 all say "the administrator can edit this". Tables, not enums.
5. **School year is a dimension running through everything** — §4.3, §6.4, §6.5. A child's group membership is stored as history in `Enrollment`.
6. **Media lives in one table** — a single `MediaFile`, with join tables expressing where each file is used.
7. **Filenames are unguessable** — §15. `storage_key` is random; the real name sits in a separate column for display only.

---

## 6. Data model

### 6.1 Foundation (9 tables + 2 profiles)

```
Kindergarten      name, logo, photo, address, phone, email, description, status   §3.2
SchoolYear        kindergarten, name "2025-2026", start, end, is_current
Group             kindergarten, school_year, name, age category, class photo,
                  timetable, group rules, status: active|archived
GroupTeacher      group, teacher_membership, role: primary|assistant, from, to
User              username, email, phone, password hash, last name, first name,
                  avatar, last login, is_active
                  ⚠ §3.1: teachers log in by username or email, guardians by
                    phone or email → all three fields must exist and be unique
Membership        user, kindergarten(null = system-wide), role, is_active, since
Child             kindergarten, last name, first name, national ID / internal
                  code (unique), sex, date of birth, avatar, enrolled on,
                  left on, brief health notes, status                        §3.4
Guardianship      child, guardian_user, relation(mother|father|grandparent|other),
                  is_primary, can_view, created                              §3.5
Enrollment        child, group, school_year, started on, ended on,
                  status: active|transferred|graduated|archived   ★ keystone table
```

**Why `Enrollment` is the keystone:** `Child` has no "group" column. A child stays in the system for three to four years (ages 2–5) and changes group every year. Keeping this as a separate table gives us:

- §3.4 transfers → close the old row, open a new one; history survives
- §6.5 year-over-year comparison → data is already partitioned by year
- §4.3 per-age pages → we know how old the child was in each school year
- Teacher authorization → determined by that year's `GroupTeacher` record

Writing the group directly onto `Child` would make every prior year's observations and assessments appear under the wrong group after a transfer. That is the most expensive mistake available here.

**`Group` belongs to a school year.** "Sunflower group 2025-2026" and "Sunflower group 2026-2027" are two rows. §3.2 lists name, age category and school year together. Staff assignment, class photo and group rules all change annually.

**Profiles:** `TeacherProfile` (specialization, years of service, education, bio — §3.3) and `GuardianProfile` (§3.5 extras).

### 6.2 Child portfolio (7 tables)

```
AboutMe           child, introduction, meaning of name, first signature (media),
                  memorable sayings, dream, distinguishing traits,
                  height, weight, recorded on                            §4.1

ChildAgeProfile   child, age(2|3|4|5), school_year,
                  favorite: color, food, toy, book, song, story, movie,
                            clothes, activity,
                  personality, emotional traits, family members,
                  learning interests, newly acquired skills,
                  parent note, teacher note                              §4.3
                  ⚠ unique(child, age, school_year)

MilestoneType     kindergarten(null = system), name, icon, order          §4.5
Milestone         child, type (or custom name), date, description, recorded by
Album             child, name, description, school_year, cover, created by  §4.4
AlbumPhoto        album, media_file, title, description, taken on, age,
                  owner type: teacher|parent|shared, order
BirthdayNote      child, year, note, media                                §4.2
```

**Zodiac sign and Mongolian year animal are not stored.** §206 says they may be computed from the date of birth. Storing a derived value means it goes stale when the birth date is corrected. Compute them in a function.

**`ChildAgeProfile` uses 17 typed columns, not EAV.** The group analytics in §917 ("every child's favorite color") become awkward under a name/value model. Columns keep queries, reports and exports simple.

**§4.1's "record who changed what and when"** is handled by `django-simple-history` snapshots, enabled on `AboutMe`, `ChildAgeProfile`, `Assessment`, `Observation` and `Child`. This is row-level rather than field-level history, but diffing two versions shows which field changed — sufficient in practice and far simpler to operate.

### 6.3 Observations (4 tables)

```
ObservationType     kindergarten, name, code, order, is_active            §5.2
                    → Daily | Work & drawing | Activity-based | Parent-submitted

Observation         child, enrollment, type,
                    source: teacher|parent,                               §5.4
                    observed on, activity name, situation,
                    what the child did, what the child said,
                    teacher comment, next steps / support plan,
                    visible_to_parents,                                   §5.1
                    review_status: pending|approved|revision_requested,
                    reviewed_by, reviewed_at, review_note,
                    include_in_report,                                    §5.4
                    author, timestamps

ObservationDomain   observation, development domain, level (optional)
ObservationMedia    observation, media_file, caption, taken on, order
```

**Why `ObservationDomain` is its own table:** a single observation ("built a tower from blocks and explained it to a friend") belongs to Creativity, Language and Communication simultaneously. A single-column domain would make the §12.3 per-domain averages wrong.

### 6.4 Assessment (8 tables)

```
DevelopmentDomain   kindergarten(null = system default), name, color,
                    order, is_active                                      §6.1
                    → Physical, Language, Cognitive, Social, Emotional,
                      Creative, Self-care, Communication, Habits

DevelopmentIndicator domain, name, age range, order   (unused in MVP)
AssessmentScale     kindergarten, name, is_default                        §6.2
AssessmentLevel     scale, value(1..N), label, color, description
                    → 1 Needs support | 2 Developing |
                      3 At expected level | 4 Above expected level

Term                school_year, number(1-4), name, start, end            §6.4

Assessment          child, enrollment, domain, indicator(nullable),
                    term, level, comment, assessed_by, assessed_at
                    ⚠ unique(child, enrollment, domain, indicator, term)

TermReport          child, enrollment, term, teacher comment, strengths,
                    areas needing support, goals for next term,
                    advice for parents, author,
                    status: draft|final, finalized at                     §6.4

AnnualReport        child, school_year, progress, strengths,
                    skills to develop, year-end conclusion,
                    advice for parents, author, status, finalized at      §6.5
```

**`unique(child, enrollment, domain, term)`** enforces §17's "a double-click must not save the same record twice" at the database level. The §6.3 quick-assessment screen is exactly where that happens. With the constraint in the database, even a bug in the application cannot create a duplicate.

**Assessment is at the domain level.** §6.4, §6.5, §12.3 and the Module 1.4 radar chart all work per domain. The `DevelopmentIndicator` table and the `Assessment.indicator` column stay empty in the MVP — they are there so that finer-grained criteria can be added later. An unused nullable column is nearly free; restructuring `Assessment` later would require migrating all existing data.

**`TermReport.status`** — teachers write a report over several days. It must not be visible to guardians before it is finalized. PDF generation and acknowledgement both key off this status.

### 6.5 Growth (3 tables)

```
GrowthMeasurement     child, measured on, age in months, height, weight,
                      head circumference, note, recorded by               §7.1
GrowthStandardSource  name, version, source URL, published on
GrowthStandardPoint   source, sex, age in months, metric(height|weight|head),
                      p3, p15, p50, p85, p97
```

**`GrowthStandardSource` is required.** §427: "clearly display the source, version and revision date of the reference values". Hard-coding the reference numbers fails that requirement and forces a redeploy whenever the standard is updated.

The §427 disclaimer ("this system does not provide medical diagnoses") is displayed in the UI.

### 6.6 Media (2 tables)

```
MediaFile     kindergarten, child(nullable), uploaded_by,
              storage_key      ← random UUID path
              original_name    ← display only
              mime_type        ← detected from CONTENT, not the extension
              size_bytes, width, height, checksum(sha256),
              status: uploading|processing|ready|failed,
              uploaded_at, deleted_at

MediaVariant  media_file, kind: thumb|medium|full|webp_thumb|webp_medium,
              storage_key, width, height, size_bytes, format
```

### 6.7 Communication (8 tables)

```
Announcement            kindergarten, author, title, body,
                        starts at / ends at, is_important,
                        status: draft|published, published at            §8.1
AnnouncementTarget      announcement, group(nullable), child(nullable)
AnnouncementAttachment  announcement, media_file
AnnouncementRead        announcement, user, read_at  unique(announcement,user)

Post                    kindergarten, group, author, title, body, date,
                        visibility: whole group | selected children        §8.2
PostMedia               post, media_file, order
PostChild               post, child
PostLike                post, user   unique
PostView                post, user   unique  ← repeat views not counted
```

**Why `AnnouncementTarget` is separate:** §8.1 lists both "recipient group" and "guardians of selected children". One announcement can go to three groups plus two individual children at once. A single column cannot express that.

### 6.8 Documents (4 tables)

```
DocumentCategory  kindergarten, name, order                               §9
Document          kindergarten, title, category, description, cover,
                  current_version, is_active
DocumentVersion   document, version number, file, page count,
                  published at, published by, note
DocumentBookmark  document, user   unique
```

### 6.9 System (6 tables)

```
ReportJob             kindergarten, type, params JSON, requested_by,
                      status: queued|running|done|failed|expired,
                      progress_percent, result_media, file_size, page_count,
                      error_message, requested_at, started_at,
                      completed_at, expires_at                            §10

AuditLog              kindergarten(nullable), actor_user, actor_role,
                      action, object_type, object_id, child(nullable),
                      ip_address, user_agent, metadata JSON, created_at
                      ★ APPEND-ONLY. Never updated, never deleted     §15, §16

ConsentType           kindergarten, code, name, description, is_required, version
Consent               child, guardian_user, type, version, granted,
                      granted_at, revoked_at, ip_address                  §16

LoginAttempt          identifier, ip, succeeded, created_at               §3.1
PasswordResetToken    user, token_hash, expires_at, used_at               §3.1
```

**Total ≈ 53 tables plus history mirrors.**

| Group | Count |
|---|---|
| Foundation + profiles | 11 |
| Portfolio | 7 |
| Observations | 4 |
| Assessment | 8 |
| Growth | 3 |
| Media | 2 |
| Communication | 8 |
| Documents | 4 |
| System | 6 |

---

## 7. File processing pipeline

```
Photo from a phone → stored temporarily → queued, response returns IMMEDIATELY
                                      │
                                      ▼  Celery worker
                    1. Verify the real MIME type          §15
                       (a .jpg that is actually a .exe)
                    2. Strip GPS coordinates from EXIF    ★
                    3. Convert HEIC → JPEG                §4.4
                    4. Generate thumb / medium / full     §17
                    5. Generate WebP variants             §968
                    6. status = ready
```

**★ Stripping EXIF GPS** is not stated in the RFP but is mandatory. Phone photos embed location coordinates; a leaked child photo would carry the child's home address. This falls squarely under the §16 privacy principles.

### 7.1 Serving images — no public URLs

```
GET /media/<uuid>/<variant>/
      │
      ▼  can_access_child(user, media.child)
      │
   ✗ 404          ✓ S3 signed URL (TTL 5 min) → redirect
```

The signed link is created **after** the permission check. Satisfies §4.4 and §21.10.

---

## 8. Report queue (PDF)

§549: "the system must not freeze while a report is being generated."

```
Teacher clicks "Generate PDF"
   → ReportJob created (queued), response returns in ~0.2s
   → Screen: "Preparing... 40%"  (HTMX polls every 2s)
   → Worker: render HTML → WeasyPrint → PDF → S3 → done
   → "Download" button appears
   → On download: permission check → AuditLog(download) → signed URL
```

The `params` JSON holds the section selection from §10.1.

**`expires_at`:** generated PDFs are deleted automatically after 30 days. §12.2 tracks storage usage, and a file containing a child's complete record should not sit around indefinitely. Regenerating is cheap.

### 8.1 PDF technical requirements (§10.3)

- A Cyrillic-capable font is **installed into the container and referenced via `@font-face` in CSS**. Never rely on system fonts
- A4, page numbers, kindergarten logo and name
- Images are not distorted (`object-fit: contain`) and use the `medium` variant, never the original
- Output file size and page count are recorded on the `ReportJob`

---

## 9. Audit log and consent

### 9.1 AuditLog

§971 requires specifically: who viewed a child's data and when, who edited it, and who downloaded which PDF report and when.

**Recorded actions:**
`login`, `login_failed`, `logout`, `view`, `create`, `update`, `delete`, `restore`, `download`, `export`, `permission_change`, `password_reset`

**`view` is recorded selectively.** Logging every page load would produce hundreds of thousands of rows per day. Only meaningful accesses are recorded: opening a child's portfolio, viewing a report, downloading a file. Scrolling a list or opening a menu is not.

**This table follows different rules from the rest:** no soft delete, no `updated_at`. Once written a row never changes — otherwise the audit log means nothing.

**Indexes:** `(child, created_at)`, `(actor_user, created_at)`, `(kindergarten, created_at)`. Retention is set by administrator policy per §16, after which rows move to an archive.

### 9.2 Consent

Example `ConsentType` values: "data processing", "photo publication", "sharing with third parties".

**Versioning matters:** if the terms change later, an existing consent must not carry over to the new terms automatically. The version number enforces that.

**Practical effect:** before a child's photo appears in a §8.2 post visible beyond their own guardians, the system checks for photo-publication consent and warns the teacher if it is missing.

---

## 10. Lists, search and indexes (§11, §17)

RFP §11 is a full chapter: nine filter types and four sort keys. §716 requires pagination and §720 requires efficient queries. With 3,000 children and thousands of observations, these are the first things to degrade if left unplanned.

### 10.1 Rules

- **Every list view is paginated** (§716). 25–50 rows per page
- `Child` and `Observation` lists use offset pagination (fine at 3,000 rows)
- `AuditLog` uses keyset (cursor) pagination — this table reaches millions of rows
- **N+1 queries are forbidden.** Every list view uses `select_related` / `prefetch_related`. Key screens get `assertNumQueries` tests
- `django-debug-toolbar` in development

### 10.2 Indexes implied by the §11 filters

| Filter (§11) | Index |
|---|---|
| Search by child name | `pg_trgm` GIN index on `Child` (last + first name). Plain ILIKE is too slow for Cyrillic substring search |
| By group, by school year | `Enrollment(group, status)`, `Enrollment(school_year, status)` |
| By age, by sex | `Child(kindergarten, date_of_birth)`, `Child(kindergarten, sex)` |
| By observation type, by date range | `Observation(child, observed_on)`, `Observation(type, observed_on)` |
| By development domain | `ObservationDomain(domain)`, `Assessment(enrollment, domain, term)` |
| By assessment level | `Assessment(term, level)` |
| Active vs archived | `Child(kindergarten, status)` — partial index alongside soft delete |
| Sort by name / date / age / last updated | Age is inverse date of birth. Index on `updated_at` |

Per principle 1 in section 5, **`kindergarten_id` leads every composite index**.

### 10.3 Dashboard computation (§12)

| Metric | Approach |
|---|---|
| §12.1 teacher dashboard — one group, ~25 children | Direct query. No caching needed |
| "Children with missing assessments" | LEFT JOIN using the `Assessment` unique constraint. Index: `Assessment(enrollment, term)` |
| §12.2 admin dashboard — kindergarten or system wide | Celery periodic task every 15 minutes, cached. Not computed per page load |
| §12.3 charts, per-domain averages | Computed when a term closes and stored on `TermReport`. Historical charts are never recomputed |

---

## 11. Environments and deployment

```
Development   docker-compose: web, worker, postgres, redis, minio (S3 stand-in)
Staging       same shape as production, separate database
Production    web, worker, beat, postgres, redis + external object storage
```

- All configuration via environment variables (§14), with a committed `.env.example`
- `/healthz` checks database, Redis and storage connectivity (§14)
- Daily automated `pg_dump`; restore procedure documented (§14, §21.11)
- §707: production data and real child photos are never used in development. A seed data generator is provided

---

## 12. Testing strategy

Grouping the §18 checklist:

| Level | What it covers |
|---|---|
| **Authorization tests (highest priority)** | §21.2, §21.3, §21.4. A teacher accessing another group's child by ID → 404. A guardian accessing another child's portfolio, photos or reports → 404. Cross-kindergarten access → 404. **Written at two levels — see below** |
| Model / service tests | Enrollment transfers, assessment uniqueness, soft delete, consent checks |
| File tests | Wrong type, oversized file, HEIC conversion, GPS stripping, signed URL expiry |
| PDF tests | Cyrillic rendering, A4, images, page numbers, large reports |
| Integration tests | Full flow: add child → observation → assessment → report |
| Manual | Chrome, Safari, Edge, Android browser; phone and tablet responsiveness |

### 12.1 Authorization tests come in two layers

**Function level** (`apps/core/tests/test_permissions.py`) — proves the rules
in `permissions.py` are correct, including the transfer scenarios.

**View level** — proves each view actually *calls* those rules. This is the
layer §21.4 is really about: it describes what happens when someone edits a
URL, which is a claim about request handling.

The second layer is not optional. A view that never calls
`can_access_child()` passes every function-level test. Every view touching
child data ships with `client.get(url)` → `404` tests for a teacher from
another group, a guardian of another child, and a user from another
kindergarten.

---

## 13. Risks and the week-one spike

### 13.1 Highest risk: Mongolian Cyrillic in PDF

This is where projects of this shape most often fail. Discovering in month three that "the PDF renders □□□ instead of letters" is very expensive.

**Week-one spike:** generate a one-page PDF from fake data containing Mongolian text, a child photo, a kindergarten logo and a page number. Print it at A4 and check. If it works, the rest is routine engineering. If it does not, there is still time to change approach.

### 13.2 Other risks

| Risk | Mitigation |
|---|---|
| A permission check gets forgotten somewhere | All access flows through `services/permissions.py`. Authorization tests run in CI |
| Django Admin bypasses audit / soft delete | Override `save_model()` and `delete_model()` |
| Image-heavy reports are slow | Worker-based generation, `medium` variants, cleanup via `expires_at` |
| Audit log grows unbounded | Selective `view` logging, indexes, retention policy |
| Scope creep | The deferred list in §1.2. New requests go to a later phase |
| List pages degrade | The indexes in section 10, plus `assertNumQueries` tests |

---

## 14. Implementation phases (outline)

A detailed plan lives in a separate document.

1. **Foundation** — Docker environment, Django project, `User`/`Membership`, authentication, permission layer, authorization tests, Cyrillic PDF spike
2. **Organization data** — Kindergarten, SchoolYear, Group, GroupTeacher, admin screens
3. **Children** — Child, Guardianship, Enrollment, guardian home screen
4. **Media** — MediaFile pipeline, signed URLs, photo albums
5. **Portfolio** — AboutMe, ChildAgeProfile, Milestone, BirthdayNote
6. **Observations** — Observation and related tables
7. **Assessment** — configuration tables, Assessment, quick-assessment screen
8. **Reports** — ReportJob, TermReport, AnnualReport, PDF templates
9. **Communication** — Announcement, Post
10. **Growth, documents, dashboards**
11. **Hardening** — full audit log, consent, backups, load testing, security testing

---

## 15. Open questions

| Question | Needed by |
|---|---|
| After a transfer, how long do the previous kindergarten's staff retain access? (Section 4.2 sets no time limit. Should §16 retention policy bound it?) | Before phase 3 |
| Are the nine development domains in §6.1 system defaults, or does each kindergarten define its own? | Before phase 7 |
| Which growth reference standard — WHO or a national one? | Before phase 10 |
| Where do backups live and who can access them? | Before phase 11 |
| **Hosting and object storage** — VPS + Docker, or managed PaaS? Cloudflare R2 in section 2 is a **suggestion**, not a decision | Before phase 4 (media) |
| Domain name, SSL, server location | Before deployment |
