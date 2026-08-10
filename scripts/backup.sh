#!/usr/bin/env bash
#
# Database backup — RFP §16.
#
# Dumps the PostgreSQL database to a timestamped, compressed file and then
# verifies that the file parses. A dump nobody has ever read back is not a
# backup, it is a file; `pg_restore --list` is the cheapest proof that the
# archive is intact and non-empty.
#
# Runs pg_dump inside the `db` container, so the host needs no PostgreSQL
# client and the dump is always produced by the same server version that
# wrote the data.
#
# Usage:
#   scripts/backup.sh                  # write to ./backups
#   BACKUP_DIR=/srv/backups scripts/backup.sh
#   RETENTION_DAYS=30 scripts/backup.sh
#
# Uploads: media files live in object storage (S3 / Cloudflare R2), not on
# disk, so they are not in this dump. Their backup is bucket versioning plus
# the provider's own lifecycle rules — configured at deployment time, once
# D3 is decided. See ROADMAP.md.

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
SERVICE="${DB_SERVICE:-db}"

# The credentials come from .env, the one place settings live (RFP §690).
# Reading them here rather than hard-coding "kinder" means the script works
# unchanged against a production database.
if [ ! -f .env ]; then
    echo "backup: .env not found — copy .env.example and fill it in" >&2
    exit 1
fi

DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
if [ -z "${DATABASE_URL}" ]; then
    echo "backup: DATABASE_URL is not set in .env" >&2
    exit 1
fi

# postgres://USER:PASSWORD@HOST:PORT/NAME
db_user="$(sed -E 's|^[^:]+://([^:]+):.*|\1|' <<<"${DATABASE_URL}")"
db_name="$(sed -E 's|.*/([^/?]+)(\?.*)?$|\1|' <<<"${DATABASE_URL}")"

if [ -z "${db_user}" ] || [ -z "${db_name}" ]; then
    echo "backup: could not read the user and database out of DATABASE_URL" >&2
    exit 1
fi

if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE}"; then
    echo "backup: the '${SERVICE}' service is not running — start it with 'make up'" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIR}/${db_name}-${stamp}.dump"

echo "backup: dumping ${db_name} → ${target}"

# -Fc is PostgreSQL's custom format: compressed, and pg_restore can read a
# single table out of it without replaying the whole archive.
# Write to a .part file first so an interrupted run never leaves behind
# something that looks like a finished backup.
docker compose exec -T "${SERVICE}" \
    pg_dump -U "${db_user}" -d "${db_name}" -Fc --no-owner --no-privileges \
    > "${target}.part"

mv "${target}.part" "${target}"

# Verify: does the archive parse, and does it contain any table data at all?
if ! docker compose exec -T "${SERVICE}" pg_restore --list < "${target}" > /dev/null 2>&1; then
    echo "backup: ${target} does not parse — the backup FAILED" >&2
    exit 1
fi

tables="$(docker compose exec -T "${SERVICE}" pg_restore --list < "${target}" \
          | grep -c 'TABLE DATA' || true)"
if [ "${tables}" -eq 0 ]; then
    echo "backup: ${target} parses but holds no table data — the backup FAILED" >&2
    exit 1
fi

size="$(du -h "${target}" | cut -f1)"
echo "backup: ok — ${size}, ${tables} tables"

# Retention. -mtime +N deletes strictly older than N days, so the newest
# backup is never a candidate however long the script goes unrun.
if [ "${RETENTION_DAYS}" -gt 0 ]; then
    removed="$(find "${BACKUP_DIR}" -name "${db_name}-*.dump" -type f \
               -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')"
    if [ "${removed}" -gt 0 ]; then
        echo "backup: removed ${removed} backup(s) older than ${RETENTION_DAYS} days"
    fi
fi
