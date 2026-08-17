# Production readiness — Phase 1

**Assessed:** 2026-08-17, branch `feat/ui-redesign`, nothing committed.

Every item is **READY**, **MISSING**, **BLOCKED**, or **NEEDS CLIENT DECISION**.
READY means verified in the current working tree — not "written at some point".

**Overall: not deployable today.** Nothing is broken; four items need a value or
a decision that only the client can supply. They are listed in §9.

---

## 1. Application code

| # | Item | Status | Note |
|---|---|---|---|
| 1.1 | Test suite | **READY** | 958 passing. Run with `--create-db`; two concurrent `--reuse-db` runs collide and report false failures. |
| 1.2 | Lint (`ruff`) | **READY** | Clean. |
| 1.3 | Migration graph matches models | **READY** | `makemigrations --check --dry-run` → "No changes detected", after `accounts/0005`. |
| 1.4 | No hard deletes | **READY** | Soft delete throughout; `AuditLog` append-only by design (CLAUDE.md §3.3). |
| 1.5 | Business logic outside views | **READY** | `services.py` / `selectors.py`; the §20-IV API will reuse them. |
| 1.6 | N+1 guards | **READY** | `assertNumQueries` on the six list screens. |

## 2. Authorization

| # | Item | Status | Note |
|---|---|---|---|
| 2.1 | Single authorization module | **READY** | `apps/core/permissions.py`; CLAUDE.md §1.1. |
| 2.2 | Kindergarten from enrollment history | **READY** | One documented fallback for a child with no enrollments yet. |
| 2.3 | Unauthorized access returns 404 | **READY** | Tested through the HTTP client, per CLAUDE.md §4.1 — not by calling the predicate. |
| 2.4 | Revoked guardianship loses access | **READY** | Fixed 2026-08-16. A soft-deleted `Guardianship` was still granting access through a reverse-relation join, which does not apply the related model's default manager. 5 tests fail if reverted. |
| 2.5 | Revoked teacher assignment loses access | **READY** | Same shape, same fix, in `GroupTeacher`. 8 tests fail if reverted. |
| 2.6 | Observations default to private | **READY** | `visible_to_parents=False`; parent submissions are the deliberate exception. |
| 2.7 | No kindergarten in the session | **READY** | Always derived from the object (CLAUDE.md §1.3). |

## 3. Media

| # | Item | Status | Note |
|---|---|---|---|
| 3.1 | `MEDIA_URL` unset | **READY** | Deliberate; files are never served by Django's static handling. |
| 3.2 | Permission check before a signed URL | **READY** | `/media/<uuid>/<variant>/`, TTL 300s. |
| 3.3 | MIME sniffed from content | **READY** | `python-magic`; extension never trusted (RFP §684). |
| 3.4 | Random `storage_key` | **READY** | Real filename kept only in `original_name`, for display. |
| 3.5 | Private bucket | **NEEDS CLIENT DECISION** | `prod.py` sets `default_acl: "private"`, but **the bucket itself must be created private**. See §9.2 — this is the single highest-consequence deploy step. |
| 3.6 | HEIC | **READY (as scoped)** | Recognised and refused with a clear message. Conversion is Phase 2 by design — but iPhones shoot HEIC by default, so expect parents to hit it. See §9.4. |

## 4. Email — password reset

| # | Item | Status | Note |
|---|---|---|---|
| 4.1 | Reset actually sends | **READY** | Fixed 2026-08-17. Until then the view printed the link to stdout and sent nothing. |
| 4.2 | Link never logged | **READY** | Guarded by a test that reads the log records directly. `caplog`, `capsys` and `capfd` are all blind to this logger — each was tried and each passed against an empty string — so the test attaches its own handler and asserts the diagnostic *is* present before asserting the link is not. |
| 4.3 | No existence oracle | **READY** | Unknown address, known address and a dead mail server all return a byte-identical page. |
| 4.4 | Failure is survivable | **READY** | Logged for an administrator; a delivered link already in the user's inbox is not retired by a request whose send failed. |
| 4.5 | SMTP credentials | **MISSING** | `EMAIL_HOST` and friends are wired to the environment and documented in `.env.example`, but **no host is configured**. See §9.1. |
| 4.6 | `DEFAULT_FROM_EMAIL` | **MISSING** | Defaults to `noreply@localhost`, which most receivers will reject. Needs a real address on the client's domain. |
| 4.7 | Guardians with no email | **NEEDS CLIENT DECISION** | Phone-only guardians cannot self-reset; SMS is §20-IV. Today an administrator resets for them (RFP §2.1). Confirm that is acceptable for launch. |

## 5. Configuration and secrets

| # | Item | Status | Note |
|---|---|---|---|
| 5.1 | No secrets in source | **READY** | Everything through `os.environ`; `.env` gitignored. |
| 5.2 | `.env.example` current | **READY** | Includes the new email block. |
| 5.3 | `DJANGO_SECRET_KEY` | **READY (fails loudly)** | No default — a deployment without it stops rather than starting with a guessable key. |
| 5.4 | `DEBUG` | **READY** | Defaults to `False`; `prod.py` pins it. |
| 5.5 | `ALLOWED_HOSTS` | **MISSING** | Defaults to `[]`. Must carry the real domain. |
| 5.6 | `DJANGO_CSRF_TRUSTED_ORIGINS` | **MISSING** | Must carry the real `https://` origin or every POST fails behind the proxy. |
| 5.7 | **`DJANGO_EMAIL_BACKEND` must not be `console` in production** | **MISSING (deploy check)** | The console backend writes the full reset link to the container log — reintroducing precisely the bug 4.1 removed. Verify this on the server after deploy. |

## 6. Infrastructure

| # | Item | Status | Note |
|---|---|---|---|
| 6.1 | HTTPS, HSTS, secure cookies | **READY** | `prod.py`: SSL redirect, HSTS 1 year with preload, secure session and CSRF cookies. |
| 6.2 | Deploy script | **READY** | `scripts/deploy.sh`; same script first time and every time, refuses rather than guesses. |
| 6.3 | Backup script | **READY** | `scripts/backup.sh` dumps and reads the archive back — an unverified dump is not a backup. |
| 6.4 | Backups copied off the machine | **MISSING** | Documented in `DEPLOYMENT.md` but not automated. A backup on the database's own disk survives nothing that would make you want one. |
| 6.5 | Restore rehearsed | **MISSING** | `restore.sh` exists; it has not been run against a real archive. An untested restore is a hope. |
| 6.6 | Health check | **READY** | `/healthz`. |
| 6.7 | Celery worker and beat | **READY** | In the prod compose file; PDF generation and report expiry both depend on it. |
| 6.8 | Static files | **READY** | WhiteNoise with a manifest storage. |
| 6.9 | Log retention and access | **MISSING** | No rotation policy, and no statement of who can read production logs. Audit logs are in the database; container logs are not. |

## 7. Acceptance criteria (RFP §21)

| # | Criterion | Status |
|---|---|---|
| §21.2 | Teacher sees only their own group's children | **READY** |
| §21.3 | Guardian sees only their own child | **READY** |
| §21.4 | Changing the URL reveals nothing | **READY** |
| §21.7 | Term report generates correctly | **READY** |
| §21.8 | Cyrillic and images correct in the PDF | **READY** — verified by rasterising real PDFs with `pdftoppm`, not by reading the template. One wording risk flagged in `PDF_PHOTO_DECISION.md`. |
| §21.10 | Photos not reachable without permission | **READY** |
| §21.15 | UI matches what was approved | **NEEDS CLIENT DECISION** — see §9.3. |

## 8. Known scope boundaries (not defects)

Phase 2 by agreement, recorded so nobody reads them as gaps at acceptance:
full portfolio timeline, milestones, photo albums, growth tracking, annual
report (§6.5), document library, Excel export, activity posts, consent
records, HEIC conversion. Phase 3: surveys, analytics, attendance, health and
medication, voice notes, WebP and thumbnails, CDN, QPay. Never: native apps.

## 9. What blocks deployment

Four items. The first two are values; the last two are conversations.

### 9.1 — SMTP credentials (MISSING)
Password reset is wired end to end and tested, but no mail host is configured.
Without it the first reset raises on send. Needs a host, port, user, password
and a real `DEFAULT_FROM_EMAIL` on the client's domain.

### 9.2 — Object storage bucket (NEEDS CLIENT DECISION)
The application asks for private objects and signs every URL, but that is not
sufficient on its own: **a public bucket would expose every child's photograph
regardless of what the application does.** The bucket must be created private
and confirmed private. This is the one item where a mistake is unrecoverable —
photographs of children, published, with no way to un-publish.

### 9.3 — UI sign-off (NEEDS CLIENT DECISION)
The interface was deliberately simplified away from a literal reproduction of
the 21 approved mockups, on instruction (2026-08-16): one screen, one job; no
children × 9-domain matrix; no charts. `docs/MOCKUP_FIDELITY_AUDIT.md` records
the divergence and `docs/UI_UX_MAP.md` records what was built. **§21.15 makes
the approved UI an acceptance criterion, so the client must sign off on the
simplified direction before acceptance, not after.**

### 9.4 — HEIC uploads (NEEDS CLIENT DECISION)
iPhones shoot HEIC by default. Phase 1 refuses it with a clear message rather
than converting. Parents on iPhones will meet this on their first upload.
Confirm that a clear refusal is acceptable for launch, or pull conversion
forward from Phase 2 — which is a scope change, not a fix.

## 10. Before the first deploy

In order. None of these is optional.

1. Fill every value in `.env` from `.env.example`; confirm `DJANGO_EMAIL_BACKEND`
   is **not** the console backend (§5.7).
2. Create the object storage bucket **private**, then verify from outside that a
   known key 403s (§9.2).
3. Send one real password reset end to end, on a real device.
4. Run `scripts/backup.sh`, then **restore it into a scratch database** (§6.5).
   A backup nobody has restored is not a backup.
5. Copy an archive off the machine and confirm it arrives (§6.4).
6. Complete `docs/FINAL_DEVICE_QA.md` on a real iPhone and a real Android phone.
7. Get §21.15 sign-off in writing (§9.3).
