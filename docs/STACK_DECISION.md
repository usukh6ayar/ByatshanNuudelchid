# Stack decision — Option C

**Status:** approved and in force, 2026-08-16.
**Applies to:** the MVP (ROADMAP Phase 1) and everything shipped under it.

The existing Django project at the repository root **is** the official MVP
codebase. There is no rebuild, no second repository, no framework migration.

---

## 1. The decision

**Keep the application. Replace the presentation layer only.**

### Kept, unchanged

| | |
|---|---|
| Backend | Django 5.2.6 on Python 3.13.15 |
| Database | PostgreSQL 17, `ATOMIC_REQUESTS = True` |
| Models and migrations | 34 models, all existing migration history |
| Authentication | `apps/accounts/` — multi-identifier login, lockout, invitations |
| Authorization | `apps/core/permissions.py` — the single source of truth |
| Service layer | `services.py` / `selectors.py` in every app |
| Queue | Celery + Redis, with beat schedules |
| Media pipeline | private bucket, UUID keys, signed URLs, MIME sniffing, EXIF stripping |
| PDF | WeasyPrint, Cyrillic-verified |
| Runtime | Docker + docker-compose, dev and prod |
| Operations | `scripts/deploy.sh`, `scripts/backup.sh`, `scripts/restore.sh` |
| Tests | the full suite |

### Changed

Only the presentation layer: templates, CSS, layout, responsive behaviour.

### Explicitly rejected for the MVP

- **No Next.js**
- **No NestJS**
- **No Prisma**
- **No Puppeteer**
- **No React**

The Option-B planning documents describing a Next.js / NestJS / Prisma /
Puppeteer system are **Phase-2 reference material only**. They are not an
implementation plan and nothing in them is scheduled. They are kept because
the reasoning in them may be worth revisiting if a separate mobile or SPA
client is ever commissioned — which is RFP §20-IV territory, not MVP.

---

## 2. Why — the evidence

This was decided on what the repository demonstrably already does, verified
by running the checks rather than by reading the roadmap.

### 2.1 The suite is green and substantial

**785 tests passing, 0 failures**, in 2m25s across four workers. `ruff check`
clean. Every one of those tests is a behaviour a rebuild would have to
reproduce before reaching parity — and would reproduce without the benefit of
having found the defects that produced them.

### 2.2 Authorization and IDOR coverage already exists

The hardest and most consequential part of this system is that a teacher must
not read another kindergarten's child, and a guardian must not read another
family's. That is RFP §21.2–§21.4, and it is an acceptance criterion.

`apps/core/permissions.py` is the only place the question is answered, and the
kindergarten is resolved from `Enrollment` history rather than from the
denormalized `Child.kindergarten_id` — so a transfer does not silently revoke
the previous teacher's access to observations they wrote themselves.

Crucially the tests exercise this **through the HTTP client**, not by calling
the permission function directly (CLAUDE.md §4.1): 40+ authorization tests
that prove each view actually performs the check, rather than proving a
function returns `False`. A rewrite starts this coverage at zero, and the
failure mode of getting it wrong is disclosing children's records.

### 2.3 The private media pipeline works

No `MEDIA_URL`. Files are never reachable by direct URL. Every request goes
`/media/<uuid>/<variant>/` → permission check → short-lived signed URL, with
`storage_key` a random UUID and the real filename kept only for display. The
MIME type is detected from content, not from the extension, and EXIF GPS is
stripped on upload. 34 tests cover it, including deliberate MIME spoofing and
a JPEG carrying real GPS coordinates read back to prove removal.

This satisfies RFP §4.4, §15, §21.10 and §684 today.

### 2.4 PDF generation works, in Mongolian

WeasyPrint renders A4 with correct Cyrillic — Ө ө Ү ү verified by rendering a
real portfolio to PNG and reading it, not by grepping bytes. Rendering runs in
a Celery worker tracked by `ReportJob`, as RFP §549 requires.

This is precisely where the Option-B path was weakest: Puppeteer means running
headless Chrome, and the §549 requirement means it must run outside the
request in a persistent worker anyway.

### 2.5 Deployment and backup tooling is written and rehearsed

`docker-compose.prod.yml`, `Caddyfile` and `scripts/deploy.sh` exist and their
refusals have been exercised. `check --deploy` under `config.settings.prod`
reports nothing but the placeholder `SECRET_KEY` from the development `.env`.
`collectstatic` post-processes 640 files through the manifest storage.
`backup.sh` has been run against the live database and `restore.sh` end to end
against a scratch database, twice, with row counts compared table by table.

### 2.6 The remaining MVP work is not backend work

What is actually left before handover:

1. **Deployment** — a server, a domain, a real secret key, an R2 bucket
2. **Device testing** — nobody has opened this on a physical phone
3. **UI polish** — the presentation-layer refresh this decision authorises

None of the three is made easier by changing framework, and a rebuild would
add all of the backend work back in front of them. The Definition of Done
stands at 23 of 24, and the one open row is "Application is deployed."

---

## 3. What this decision does not claim

- It is **not** a claim that the UI is finished. It is not; that is why the
  presentation layer is in scope.
- It is **not** a claim that the system is production-ready. Four blockers are
  open and tracked separately: password-reset delivery, one pending migration,
  the deployment itself, and device testing.
- It does **not** rule out a DRF API or a separate client later. The service
  layer is already structured so both call the same functions (CLAUDE.md
  §2.1). That is RFP §20-IV and decision D2, not MVP.

---

## 4. Consequences for anyone working in this repository

- Build inside `apps/`. Do not start a parallel project.
- The presentation-layer work starts from plain server-rendered templates and
  one 669-line stylesheet — there is no HTMX and no Alpine, despite what
  ROADMAP §4 said until 2026-08-16. See the correction there.
- Introducing a frontend framework, a build step or a CDN dependency is a
  change to this decision, not an implementation detail. Raise it first.
- CLAUDE.md continues to govern. Precedence is unchanged:
  **RFP > ROADMAP > spec > CLAUDE.md > existing code.**

---

## 5. Related

- [`ROADMAP.md`](../ROADMAP.md) §4 technology stack, §7 Phase 1 status
- [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) — the deployment procedure
- [`CLAUDE.md`](../CLAUDE.md) — mandatory coding rules
- `Project_Info.md` — the client's RFP, the final authority on requirements
