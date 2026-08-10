# Deployment

A Phase 1 deliverable (`ROADMAP.md` §7). Provider-neutral on purpose: the
hosting decision is still open (`ROADMAP.md`, D3), and none of the procedure
below depends on the answer. Everything here has been run locally; what has
never happened is running it against a server.

> **The application has not been deployed.** This document is the procedure,
> not a record. The Definition-of-Done row "Application is deployed" stays ❌
> until someone follows it end to end.

---

## 1. What you need first

| | |
|---|---|
| A host | Anything that runs Docker. 2 vCPU / 4 GB is comfortable for one kindergarten |
| A domain | With DNS pointing at the host |
| TLS | A reverse proxy terminating HTTPS — Caddy, nginx, or the platform's own |
| An S3-compatible bucket | Cloudflare R2, AWS S3, or MinIO you run yourself |

The bucket **must be private**. RFP §4.4 and §21.10 are explicit: children's
photographs are never reachable by URL alone. The application issues
short-lived signed URLs after checking permission, which only works if the
bucket refuses anonymous reads. A public bucket fails acceptance regardless
of what the code does.

## 2. Configuration

Every setting comes from the environment (RFP §690). Copy `.env.example` to
`.env` and fill it in — it lists every key with a comment. The ones that
**must** change from their development values:

| Variable | Why |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Session and CSRF signing. 50+ random characters. `check --deploy` warns until you replace the placeholder |
| `DJANGO_DEBUG` | Ignored under `prod.py`, which hard-codes `DEBUG = False` after importing the base settings. Set it to `False` anyway so the file does not read as if debug were on |
| `DJANGO_ALLOWED_HOSTS` | Your domain. Django refuses requests for any other Host header |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your-domain`. Without it, every form POST behind the proxy fails CSRF |
| `DATABASE_URL` | The production PostgreSQL. **Not SQLite** — RFP §14 forbids it |
| `REDIS_URL` | Celery's broker and the shared cache |
| `AWS_*` | Bucket name, endpoint, credentials |
| `MEDIA_REDIRECT_SIGNED_URL` | `true` in production, so the object store moves the bytes rather than Django |

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Never commit `.env`. It is gitignored; keep it that way.

### What `config/settings/prod.py` already enforces

You do not need to configure these — they are in the file, and the point of
listing them is so nobody adds them a second time somewhere else:

- `SECURE_SSL_REDIRECT`, HSTS for one year with subdomains and preload
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
- `SECURE_PROXY_SSL_HEADER` — reads `X-Forwarded-Proto`, so your proxy must
  set it or every request will look like plain HTTP and redirect in a loop
- S3 storage with `default_acl: private` and signed URLs
- WhiteNoise's manifest static storage

## 3. First deployment

```bash
# 1. Build
docker compose build

# 2. Schema
docker compose run --rm web python manage.py migrate

# 3. The media bucket, if you are running your own MinIO.
#    On R2 or S3 the bucket is created with the account — this command will
#    not create one and will not guess a policy.
docker compose run --rm web python manage.py init_storage

# 4. Static files. Fails loudly if a stylesheet references a missing file,
#    which is the point of running it before traffic arrives.
docker compose run --rm web python manage.py collectstatic --noinput

# 5. The first account
docker compose run --rm web python manage.py createsuperuser

# 6. Verify the configuration before starting
docker compose run --rm web python manage.py check --deploy
```

`check --deploy` should report nothing. A `SECRET_KEY` warning means step 2
of the configuration was skipped.

**Do not run `seed_demo` on a production database.** It refuses to run with
`DEBUG` off (RFP §707), but do not rely on that as the only barrier.

## 4. The processes

| Process | Command | Why it exists |
|---|---|---|
| web | `gunicorn config.wsgi` behind the proxy | Requests |
| worker | `celery -A config worker` | PDF rendering (RFP §549). Without it, reports queue and never finish |
| beat | `celery -A config beat` | Dashboard figures every 15 min (§12.2), expired report cleanup hourly |
| postgres | | Data |
| redis | | Celery broker, and the cache the web and worker processes share |

`docker-compose.yml` in the repository root runs all five and is written for
development — it uses `runserver` and mounts the source directory. For a
server, override the `web` command with gunicorn and drop the bind mount.

Beat and worker are not optional. A deployment with only `web` looks healthy,
serves every page, and silently never produces a PDF.

## 5. Health

`GET /healthz` checks the database and the cache and returns JSON:

```json
{"status": "ok", "checks": {"database": "ok", "cache": "ok"}}
```

`200` when healthy, `503` when the database is unreachable. Point the
platform's readiness probe at it. A degraded cache still returns `200` — the
application works without it, just slower.

The endpoint is deliberately unauthenticated and reveals nothing beyond
whether the two dependencies answer.

## 6. Backups

RFP §16. From cron on the host, not from inside a container:

```cron
0 2 * * *  cd /srv/kinder && BACKUP_DIR=/srv/backups RETENTION_DAYS=30 ./scripts/backup.sh
```

`backup.sh` dumps through the `db` container and then reads the archive back
with `pg_restore --list`, because a dump nobody has parsed is a file rather
than a backup.

**Copy the archives off the machine.** A backup on the same disk as the
database survives nothing that would make you want a backup.

**Rehearse the restore before you need it** — the procedure, including the
`TARGET_DB` drill against a scratch database, is in `README.md`. Do it once
after the first deployment and again after any change to either script.

Uploaded photographs are in object storage, not in the dump. Their backup is
bucket versioning plus the provider's lifecycle rules, configured when the
bucket is created.

## 7. Upgrades

```bash
git pull
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py collectstatic --noinput
docker compose up -d
```

Take a backup first. Migrations are reviewed by hand for data-losing
operations before they are committed (CLAUDE.md §3.4), but review is not the
same as a restore point.

## 8. Not covered here

- **Which provider.** Open — `ROADMAP.md`, D3.
- **Creating the bucket.** Provisioned with the object storage account, and
  the steps differ per provider. It must be private.
- **The reverse proxy's own configuration.** Caddy needs three lines, nginx
  rather more; both are well documented upstream. All this application
  requires is that `X-Forwarded-Proto` is set.
