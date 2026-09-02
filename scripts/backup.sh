#!/usr/bin/env bash
#
# §15.7 — take a backup, and be able to prove it restores.
#
#   ./scripts/backup.sh staging                     # write a dump
#   ./scripts/backup.sh staging --verify            # write it, then restore it
#                                                   # into a scratch database and
#                                                   # check what came back
#
# A backup nobody has restored is a hope, not a backup. `--verify` is the whole
# point of this script: it restores into a *separate* database, counts what
# arrived, and drops it again. It never touches the database it dumped.

set -Eeuo pipefail

ENVIRONMENT="${1:-staging}"
VERIFY="${2:-}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${BACKUP_DIR:-./backups}"

case "$ENVIRONMENT" in
  local)   COMPOSE=(docker compose); ENV_FILE=".env" ;;
  staging) COMPOSE=(docker compose -f docker-compose.staging.yml --env-file .env.staging); ENV_FILE=".env.staging" ;;
  *) echo "Usage: $0 [local|staging] [--verify]" >&2; exit 2 ;;
esac

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

DB_NAME="${POSTGRES_DB:?POSTGRES_DB must be set}"
DB_USER="${POSTGRES_USER:?POSTGRES_USER must be set}"
DUMP="$OUT_DIR/${DB_NAME}-${STAMP}.dump"

mkdir -p "$OUT_DIR"

echo "Dumping $DB_NAME from the '$ENVIRONMENT' stack…"
# Custom format: compressed, and restorable table-by-table with pg_restore,
# which is what you want at 3am when one table is the problem.
"${COMPOSE[@]}" exec -T db pg_dump \
  --username "$DB_USER" \
  --dbname "$DB_NAME" \
  --format=custom \
  --no-owner \
  --no-privileges \
  > "$DUMP"

SIZE="$(wc -c < "$DUMP" | tr -d ' ')"
echo "Wrote $DUMP (${SIZE} bytes)"
[ "$SIZE" -gt 1000 ] || { echo "The dump is suspiciously small. Stopping." >&2; exit 1; }

if [ "$VERIFY" != "--verify" ]; then
  echo
  echo "Not verified. Run with --verify to prove this dump restores."
  exit 0
fi

SCRATCH="restore_check_${STAMP//[^0-9]/}"
echo
echo "Restoring into '$SCRATCH' to prove the dump is usable…"

cleanup() {
  "${COMPOSE[@]}" exec -T db psql --username "$DB_USER" --dbname postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${COMPOSE[@]}" exec -T db psql --username "$DB_USER" --dbname postgres \
  -c "CREATE DATABASE $SCRATCH;" >/dev/null

# pg_restore exits non-zero on ignorable notices, so its output is inspected
# rather than its status alone.
if ! "${COMPOSE[@]}" exec -T db pg_restore \
  --username "$DB_USER" \
  --dbname "$SCRATCH" \
  --no-owner \
  --no-privileges \
  < "$DUMP" > /tmp/restore.log 2>&1; then
  if grep -qiE "error|fatal" /tmp/restore.log; then
    echo "Restore reported errors:" >&2
    tail -20 /tmp/restore.log >&2
    exit 1
  fi
fi

echo
echo "What came back:"
"${COMPOSE[@]}" exec -T db psql --username "$DB_USER" --dbname "$SCRATCH" --tuples-only --no-align -c "
SELECT 'users            ' || count(*) FROM accounts_user
UNION ALL SELECT 'courses          ' || count(*) FROM courses_course
UNION ALL SELECT 'batches          ' || count(*) FROM batches_batch
UNION ALL SELECT 'enrolments       ' || count(*) FROM enrollments_enrollment
UNION ALL SELECT 'attendance       ' || count(*) FROM attendance_attendancerecord
UNION ALL SELECT 'assessment marks ' || count(*) FROM assessments_assessmentresult
UNION ALL SELECT 'certificates     ' || count(*) FROM certificates_certificate
UNION ALL SELECT 'audit entries    ' || count(*) FROM audit_auditlog
" | sed 's/^/  /'

# The sequences behind human-readable identifiers are objects in their own
# right. A restore that brought the tables and not the sequences would hand the
# next student an identifier somebody already has.
echo
echo "Identifier sequences:"
"${COMPOSE[@]}" exec -T db psql --username "$DB_USER" --dbname "$SCRATCH" --tuples-only --no-align -c "
SELECT '  ' || sequencename || ' at ' || COALESCE(last_value::text, 'unused')
FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename
"

echo
echo "Restore verified. The scratch database is being dropped."
