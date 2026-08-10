# ByatshanNuudelchid

Kindergarten child-development digital portfolio system.

Teachers record observations and assessments, parents contribute photos and
milestones, and the system produces a per-child portfolio that can be exported
as a printable PDF covering ages 2 through 5.

## Documents

| Document | What it is |
|---|---|
| [`Project_Info.md`](Project_Info.md) | The client's RFP, in Mongolian. Final authority on requirements |
| [`ROADMAP.md`](ROADMAP.md) | Phases, current status, the 10-day Phase 1 plan, open decisions |
| [`docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md`](docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md) | Architecture and data model |
| [`docs/design/INDEX.md`](docs/design/INDEX.md) | The client's UI mockups, screen by screen |
| [`CLAUDE.md`](CLAUDE.md) | **Mandatory** coding rules. Read before writing code |

Precedence on conflict: RFP > ROADMAP > spec > CLAUDE.md > existing code.

## Stack

Django 5.2 · PostgreSQL 17 · Celery + Redis · WeasyPrint · S3-compatible storage · Docker

Server-rendered templates with HTMX. A DRF API layer is added when the mobile
app starts (RFP §20-IV); the service layer is structured for it already.

## Getting started

```bash
cp .env.example .env        # then set DJANGO_SECRET_KEY
make build
make migrate
make storage                # create the MinIO bucket — uploads fail without it
make superuser
make up                     # http://localhost:8000
```

Photos are stored in MinIO, which starts empty, so `make storage` is not
optional: without a bucket the first upload fails with `NoSuchBucket` and
nothing on screen explains why. In production the bucket is provisioned with
the account and **must be private** — RFP §4.4, §21.10.

## Everyday commands

```bash
make test          # full suite
make test-perms    # authorization tests only (RFP §21.2-21.4)
make lint          # ruff
make migrations    # generate — then read the output file
make seed          # demo kindergarten, staff, children, observations
make storage       # create the media bucket if it is missing
make pdf-spike     # render the Cyrillic sample PDF
```

## Two things to know before contributing

**1. Authorization lives in one file.** Every access to child data goes through
`apps/core/permissions.py`. Never re-implement the check in a view. RFP §21.2,
§21.3 and §21.4 are acceptance criteria — if a teacher can reach another
group's child by editing a URL, the system fails.

**2. Business logic lives in `services.py`, not in views.** The mobile app will
call the same functions. Logic written inside a view gets duplicated, the two
copies drift, and the acceptance criteria stop holding.

Both rules, and the rest, are in [`CLAUDE.md`](CLAUDE.md).

## Fonts

`assets/fonts/` is copied into the container for PDF rendering. The image
installs DejaVu Sans, which covers Mongolian Cyrillic including Ө, ө, Ү and ү.
To use a different typeface, drop the file in that directory, rebuild, and
update the `@font-face` reference. Record the licence — RFP §19 requires a list
of licensed materials.

## Scope

The current milestone is **Phase 1**, the paid MVP: 10 days, 3,000,000 ₮.
Status, the day-by-day plan and the open decisions are in
[`ROADMAP.md`](ROADMAP.md).

Growth tracking, the document library, full reporting, albums and Excel are
Phase 2. Surveys, analytics, health records, attendance and payments are
Phase 3. Native mobile applications are out of scope entirely.

Do not start a later phase's work without agreeing it first.
