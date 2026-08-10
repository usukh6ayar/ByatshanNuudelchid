#!/usr/bin/env bash
#
# Deploy, or update, the production stack — RFP §14, §15.
#
#   scripts/deploy.sh
#
# Safe to re-run: it is the same script for the first deployment and for
# every update afterwards. Anything that only works once gets replaced by a
# half-remembered sequence of commands typed at 23:00.
#
# It refuses rather than guesses. A missing SECRET_KEY, a database that is
# not up, a static build that fails — each stops the deployment with a
# sentence, because the alternative is a site that is up and broken.

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"

say() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
die() { printf '\n\033[31mdeploy: %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------- checks

[ -f .env ] || die ".env not found — copy .env.example and fill it in"

# `set -a` exports everything the file defines, so the checks below can read
# it. Done in a subshell-free way because the compose commands need it too.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

[ "${DJANGO_SETTINGS_MODULE:-}" = "config.settings.prod" ] \
  || die "DJANGO_SETTINGS_MODULE must be config.settings.prod"

case "${DJANGO_SECRET_KEY:-}" in
  ""|change-me-in-production|django-insecure-*)
    die "DJANGO_SECRET_KEY is still the placeholder. Generate one:
       python -c 'import secrets; print(secrets.token_urlsafe(64))'" ;;
esac

[ -n "${DOMAIN:-}" ] || die "DOMAIN is not set — Caddy needs it for the certificate"
[ -n "${POSTGRES_PASSWORD:-}" ] || die "POSTGRES_PASSWORD is not set"
[ -n "${AWS_STORAGE_BUCKET_NAME:-}" ] || die "AWS_STORAGE_BUCKET_NAME is not set"

case "${DJANGO_ALLOWED_HOSTS:-}" in
  *"$DOMAIN"*) ;;
  *) die "DJANGO_ALLOWED_HOSTS does not include $DOMAIN — Django will refuse every request" ;;
esac

case "${DJANGO_CSRF_TRUSTED_ORIGINS:-}" in
  *"$DOMAIN"*) ;;
  *) die "DJANGO_CSRF_TRUSTED_ORIGINS does not include https://$DOMAIN — every form POST will fail" ;;
esac

# ---------------------------------------------------------------- backup

# Before anything replaces the running code. Migrations are reviewed by hand
# (CLAUDE.md §3.4), but review is not a restore point.
if $COMPOSE ps --status running --services 2>/dev/null | grep -qx db; then
    say "Backing up first"
    ./scripts/backup.sh
else
    say "No database running yet — first deployment, nothing to back up"
fi

# ---------------------------------------------------------------- build

say "Building"
$COMPOSE build

say "Starting the database"
$COMPOSE up -d db redis

# `depends_on: service_healthy` covers the containers, but the commands below
# run before them.
say "Waiting for PostgreSQL"
for _ in $(seq 1 30); do
    if $COMPOSE exec -T db pg_isready -U "${POSTGRES_USER}" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
$COMPOSE exec -T db pg_isready -U "${POSTGRES_USER}" >/dev/null 2>&1 \
  || die "PostgreSQL did not come up"

# ---------------------------------------------------------------- release

say "Checking the production configuration"
$COMPOSE run --rm web python manage.py check --deploy

say "Migrating"
$COMPOSE run --rm web python manage.py migrate --noinput

# Fails loudly when a stylesheet references a file that is not there, which
# is the point of running it before any traffic arrives.
say "Building static files"
$COMPOSE run --rm web python manage.py collectstatic --noinput

say "Starting everything"
$COMPOSE up -d

# ---------------------------------------------------------------- verify

say "Waiting for the health check"
ok=""
for _ in $(seq 1 30); do
    if $COMPOSE exec -T web python -c "
import urllib.request, sys
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        ok="yes"
        break
    fi
    sleep 2
done

[ -n "$ok" ] || die "the application did not become healthy — check: $COMPOSE logs web"

say "Deployed"
$COMPOSE ps --format 'table {{.Service}}\t{{.Status}}'

cat <<NOTE

  https://${DOMAIN}

  First deployment? Create the first account:
      $COMPOSE run --rm web python manage.py createsuperuser

  The worker and beat containers are not optional: without the worker no PDF
  is ever produced (RFP §549), and the site looks perfectly healthy while it
  happens. Both are in the list above — check they say "Up".

NOTE
