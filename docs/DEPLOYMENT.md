# Deployment

A Phase 1 deliverable (`ROADMAP.md` §7). The steps work on any host that runs
Docker; where the target matters, this document names the one that was chosen.
Everything here has been run locally. What has never happened is running it
against a server.

> **The application has not been deployed.** This document is the procedure,
> not a record. The Definition-of-Done row "Application is deployed" stays ❌
> until someone follows it end to end.

**Target** (decision D3, 2026-08-11): **Hetzner Cloud, Singapore region**,
with **Cloudflare R2** for uploaded files. Singapore was measured at 93 ms
from Ulaanbaatar against 121 ms for Hetzner's German sites — the users are in
Mongolia, so the server is as close to Mongolia as this provider gets.

---

## 1. What you need first

| | |
|---|---|
| A host | Hetzner CPX21 (3 vCPU / 4 GB, **Singapore**) is comfortable for one kindergarten. Anything running Docker works |
| A domain | Registered at **iTools**. An A record pointing at the Hetzner host, served from iTools' own nameservers — **DNS only, not proxied** |
| TLS | A reverse proxy terminating HTTPS — Caddy is three lines and renews certificates itself |
| An S3-compatible bucket | Cloudflare R2. Storage is $0.015/GB and **egress is free**, which matters here because the traffic is photographs being viewed by families |

Create every account in the **client's** name, not the developer's. RFP §781
makes the client the owner of the server, the domain, the database and the
cloud storage; handover should be a transfer of credentials, not a migration.

### The domain, in the order it has to happen

Caddy requests the certificate itself the first time it starts, over HTTP on
port 80. That only works if the name already resolves, so the DNS comes
first and the deployment second:

1. **A record → the Hetzner IP**, at iTools. Wait until `dig +short
   your-domain.mn` answers with that address from somewhere other than the
   machine you set it on. Run `deploy.sh` before this and the certificate
   request fails and retries with a backoff.
2. **Port 80 and 443 open** on the host. Port 80 is not optional — it is how
   the certificate is issued and renewed.
3. `DOMAIN` in `.env` (`deploy.sh` refuses without it).
4. `DJANGO_ALLOWED_HOSTS` contains it, and `DJANGO_CSRF_TRUSTED_ORIGINS`
   contains `https://` plus it. `deploy.sh` checks both.

**Do not put Cloudflare's proxy in front of it.** The account exists for R2,
and turning the orange cloud on for this record is a different thing:
Cloudflare terminates TLS, Caddy stops being able to prove ownership on port
80, and with SSL mode "Flexible" the origin is reached over plain HTTP — so
`X-Forwarded-Proto` says `http`, `SECURE_SSL_REDIRECT` fires, and the browser
loops. DNS-only. Caddy owns the certificate.

The `Caddyfile` has one site block, `{$DOMAIN}`, so the deployment answers on
the bare domain. `www.` would need a second A record, a redirect block in the
`Caddyfile` and its own entry in `DJANGO_ALLOWED_HOSTS` — `deploy.sh`'s check
is a substring match and would not catch its absence.

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
| `AWS_*` | Bucket name, endpoint, credentials. For R2 the endpoint is `https://<account-id>.r2.cloudflarestorage.com` and `AWS_S3_REGION_NAME=auto` |
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

## 3. Deploying

One command, and the same one for the first deployment and every update
afterwards:

```bash
./scripts/deploy.sh
```

It backs the database up, builds, runs `check --deploy`, migrates, builds the
static files, starts everything and waits for `/healthz` to answer. Anything
that only works the first time gets replaced by a half-remembered sequence
typed at 23:00, so there is no separate first-run path.

**It refuses rather than guesses.** Each of these stops the deployment with a
sentence instead of producing a site that is up and broken:

| Refusal | What it would otherwise cause |
|---|---|
| `DJANGO_SETTINGS_MODULE` is not `config.settings.prod` | `DEBUG` on in production |
| `DJANGO_SECRET_KEY` still the placeholder | Forgeable sessions and CSRF tokens |
| `DOMAIN` unset | Caddy cannot request a certificate |
| `POSTGRES_PASSWORD` unset | Database starts with no password |
| `AWS_STORAGE_BUCKET_NAME` unset | Uploads fail after the site is live |
| `DJANGO_ALLOWED_HOSTS` missing the domain | Django refuses every request |
| `DJANGO_CSRF_TRUSTED_ORIGINS` missing the domain | Every form POST fails |

Afterwards, create the first account:

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

If you are running your own MinIO rather than R2, create the bucket too —
`python manage.py init_storage`. On R2 the bucket comes with the account, and
that command will not create one or guess a policy.

**Do not run `seed_demo` on a production database.** It refuses to run with
`DEBUG` off (RFP §707), but do not rely on that as the only barrier.

### What the production stack differs in

`docker-compose.prod.yml` is a separate file, not an override of the
development one. An override inherits what it does not mention, and the
development file mounts the source directory, publishes PostgreSQL on 5432
and runs `runserver` — three things that must not reach a server by being
forgotten.

| | Development | Production |
|---|---|---|
| Server | `runserver`, single-threaded | `gunicorn`, 3 workers |
| Code | Bind-mounted from disk | Baked into the image |
| Database port | Published on 5432 | Reachable only inside the network |
| Files | MinIO container | Cloudflare R2 |
| HTTPS | None | Caddy, certificate renewed automatically |
| On crash | Stays down | `restart: unless-stopped` |

## 4. The processes

| Process | Command | Why it exists |
|---|---|---|
| web | `gunicorn config.wsgi` behind the proxy | Requests |
| worker | `celery -A config worker` | PDF rendering (RFP §549). Without it, reports queue and never finish |
| beat | `celery -A config beat` | Dashboard figures every 15 min (§12.2), expired report cleanup hourly |
| postgres | | Data |
| redis | | Celery broker, and the cache the web and worker processes share |

`docker-compose.prod.yml` runs all five plus Caddy. `docker-compose.yml` in
the repository root is the development stack and must not be used on a
server: it runs `runserver`, mounts the source directory and publishes
PostgreSQL on 5432.

Beat and worker are not optional. A deployment with only `web` looks healthy,
serves every page, and silently never produces a PDF — which is why
`deploy.sh` prints the container list at the end and why it is worth reading.

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
./scripts/deploy.sh
```

The same script. It takes the backup itself before anything replaces the
running code — migrations are reviewed by hand for data-losing operations
before they are committed (CLAUDE.md §3.4), but review is not a restore
point.

## 8. Running it, month to month

A VPS is owned, not rented as a service, and that has a cost in attention.
Budget **one to two hours a month**, more when something breaks:

- security updates on the host (`unattended-upgrades` handles most of it)
- Docker and base-image upgrades when the Python or PostgreSQL image moves
- disk usage — PDFs expire after `REPORT_RETENTION_DAYS`, but logs and old
  images accumulate
- **confirming the backup actually ran**, which is the one that gets skipped
  and the one that matters
- being the person who notices when the site is down

Decision D3 records that the **developer** maintains the server, not the
kindergarten. If that ever changes, revisit the choice: an unmaintained VPS
is how systems like this get breached, and a managed platform trades money
for exactly this work.

Point an uptime check at `/healthz` from outside the host. A server that
monitors itself reports nothing when it is the thing that failed.

## 9. Not covered here

- **Creating the R2 bucket.** Provisioned with the Cloudflare account. It
  must be **private** — RFP §4.4, §21.10.
- **The reverse proxy's own configuration.** Caddy needs three lines, nginx
  rather more; both are well documented upstream. All this application
  requires is that `X-Forwarded-Proto` is set.
- **Whether Mongolian law permits children's records to be held abroad.**
  Not established, and not a question this document can answer — see D3. If
  it does not, the hosting decision changes and the rest of this procedure
  stays the same.
