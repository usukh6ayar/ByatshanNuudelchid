# ByatshanNuudelchid

Kindergarten child-development digital portfolio system.

Teachers record observations and assessments, parents contribute photos and
milestones, and the system produces a per-child portfolio that can be exported
as a printable PDF covering ages 2 through 5.

## Documents

| Document | What it is |
|---|---|
| [`Project_Info.md`](Project_Info.md) | The client's RFP, in Mongolian. Final authority on requirements |
| [`docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md`](docs/superpowers/specs/2026-08-07-kindergarten-portfolio-design.md) | Architecture and data model |
| [`CLAUDE.md`](CLAUDE.md) | **Mandatory** coding rules. Read before writing code |

## Stack

Django 5.2 · PostgreSQL 17 · Celery + Redis · WeasyPrint · S3-compatible storage · Docker

Server-rendered templates with HTMX. A DRF API layer is added when the mobile
app starts (RFP §20-IV); the service layer is structured for it already.

## Getting started

```bash
cp .env.example .env        # then set DJANGO_SECRET_KEY
make build
make migrate
make superuser
make up                     # http://localhost:8000
```

## Everyday commands

```bash
make test          # full suite
make test-perms    # authorization tests only (RFP §21.2-21.4)
make lint          # ruff
make migrations    # generate — then read the output file
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

The current milestone is the MVP defined in RFP §20-II. Surveys and analytics,
health records, attendance, payments and the mobile app are deferred — see
section 1.2 of the spec for the full list. Do not start deferred work without
agreeing it first.
