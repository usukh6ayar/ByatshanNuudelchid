#!/usr/bin/env bash
#
# Database restore — RFP §16.
#
# The other half of scripts/backup.sh. A backup procedure that has never been
# restored is an assumption, so this exists and is meant to be exercised
# against a scratch database before it is ever needed against a real one.
#
# This DESTROYS the current contents of the target database. It therefore
# refuses to run unless the database name is repeated back on the command
# line — the one confirmation that cannot be given by accident.
#
# Usage:
#   scripts/restore.sh backups/kinder-20260810T090000Z.dump kinder
#
# Uploads are not in the dump; see the note in scripts/backup.sh.

set -euo pipefail

cd "$(dirname "$0")/.."

archive="${1:-}"
confirm_db="${2:-}"
SERVICE="${DB_SERVICE:-db}"

if [ -z "${archive}" ] || [ -z "${confirm_db}" ]; then
    echo "usage: scripts/restore.sh <archive.dump> <database-name>" >&2
    echo "       the database name must be repeated to confirm the overwrite" >&2
    exit 1
fi

if [ ! -f "${archive}" ]; then
    echo "restore: ${archive} not found" >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "restore: .env not found" >&2
    exit 1
fi

DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
db_user="$(sed -E 's|^[^:]+://([^:]+):.*|\1|' <<<"${DATABASE_URL}")"

# TARGET_DB exists so the procedure can be rehearsed against a scratch
# database — the only way to find out whether the restore below actually
# works is to run it, and running it against the live database to find out
# is not a drill. It does not weaken the confirmation: the name typed on the
# command line must match whatever is about to be destroyed, which is the
# invariant that matters. Defaults to the database in .env.
db_name="${TARGET_DB:-$(sed -E 's|.*/([^/?]+)(\?.*)?$|\1|' <<<"${DATABASE_URL}")}"

if [ "${confirm_db}" != "${db_name}" ]; then
    echo "restore: refusing — target is '${db_name}', you typed '${confirm_db}'" >&2
    exit 1
fi

if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE}"; then
    echo "restore: the '${SERVICE}' service is not running — start it with 'make up'" >&2
    exit 1
fi

echo "restore: this will REPLACE every row in '${db_name}'."
echo "restore: restoring from ${archive}"

# --clean --if-exists drops each object before recreating it, so a restore
# over a populated database leaves no rows from before. --no-owner keeps the
# restore working when the production role differs from the one that dumped.
# --exit-on-error: a restore that reports success after skipping half the
# archive is worse than one that stops.
docker compose exec -T "${SERVICE}" \
    pg_restore -U "${db_user}" -d "${db_name}" \
    --clean --if-exists --no-owner --no-privileges --exit-on-error \
    < "${archive}"

echo "restore: ok"
echo "restore: run 'make migrate' — the code may be newer than the dump."
