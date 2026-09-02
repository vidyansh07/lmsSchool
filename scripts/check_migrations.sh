#!/usr/bin/env bash
#
# §15.6 — prove the schema can be built from nothing, and stepped back.
#
#   ./scripts/check_migrations.sh [local|staging]
#
# Three questions, none of which a long-lived development database can answer:
#
#   1. Does a *fresh* installation migrate cleanly? A migration that quietly
#      depends on state an old database happens to have works for everyone who
#      has been here a while and fails for the first new deployment.
#   2. Does a migration reverse and re-apply? That is what a rollback is.
#   3. Is anything in the models unmigrated?
#
# Everything happens in a scratch database that is dropped at the end. The real
# database is never touched.

set -Eeuo pipefail

ENVIRONMENT="${1:-staging}"

case "$ENVIRONMENT" in
  local)
    COMPOSE=(docker compose); ENV_FILE=".env"; SETTINGS="config.settings.local" ;;
  staging)
    COMPOSE=(docker compose -f docker-compose.staging.yml --env-file .env.staging)
    ENV_FILE=".env.staging"; SETTINGS="config.settings.staging" ;;
  *)
    echo "Usage: $0 [local|staging]" >&2; exit 2 ;;
esac

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

DB_USER="${POSTGRES_USER:?POSTGRES_USER must be set}"
DB_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
SCRATCH="migration_check_$(date -u +%H%M%S)"
SCRATCH_URL="postgres://${DB_USER}:${DB_PASSWORD}@db:5432/${SCRATCH}"

psql_admin() {
  "${COMPOSE[@]}" exec -T db psql --username "$DB_USER" --dbname postgres "$@"
}

manage_scratch() {
  "${COMPOSE[@]}" exec -T \
    -e DJANGO_SETTINGS_MODULE="$SETTINGS" \
    -e DATABASE_URL="$SCRATCH_URL" \
    backend python manage.py "$@"
}

cleanup() {
  psql_admin -c "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo
echo "Migration safety check against the '$ENVIRONMENT' stack"
echo

# --- 1. Nothing in the models is unmigrated ---------------------------------

echo "1. No model change is unmigrated"
if "${COMPOSE[@]}" exec -T -e DJANGO_SETTINGS_MODULE="$SETTINGS" backend \
    python manage.py makemigrations --check --dry-run >/dev/null 2>&1; then
  echo "   ok — the models and the migrations agree"
else
  echo "   FAIL — a model changed with no migration for it" >&2
  exit 1
fi

# --- 2. Fresh installation ---------------------------------------------------

echo
echo "2. Fresh installation"
psql_admin -c "CREATE DATABASE $SCRATCH;" >/dev/null
APPLIED="$(manage_scratch migrate --no-input 2>&1 | grep -c "OK$" || true)"
PENDING="$(manage_scratch showmigrations --plan 2>&1 | grep -c '^\[ \]' || true)"
echo "   applied $APPLIED, pending $PENDING"
[ "$PENDING" = "0" ] || { echo "   FAIL — migrations remain unapplied after a fresh migrate" >&2; exit 1; }

# --- 3. Reverse and re-apply -------------------------------------------------

echo
echo "3. Reverse and re-apply"
# `assessments` is chosen because it is one of the apps carrying a hand-written
# RunSQL migration, so this exercises a reverse_sql rather than only the
# auto-generated operations Django can always undo.
if manage_scratch migrate assessments zero --no-input >/dev/null 2>&1; then
  echo "   reversed assessments to zero"
else
  echo "   FAIL — assessments would not reverse" >&2
  exit 1
fi
if manage_scratch migrate assessments --no-input >/dev/null 2>&1; then
  echo "   re-applied assessments"
else
  echo "   FAIL — assessments would not re-apply after being reversed" >&2
  exit 1
fi

# --- 4. Destructive operations ----------------------------------------------

echo
echo "4. Destructive operations in the history"
DESTRUCTIVE="$(grep -rn \
  "migrations.RemoveField\|migrations.DeleteModel\|migrations.RenameField\|migrations.RenameModel" \
  backend/apps/*/migrations/*.py 2>/dev/null || true)"
if [ -z "$DESTRUCTIVE" ]; then
  echo "   none — nothing in the history drops or renames anything"
else
  # Not a failure. Dropping a column is sometimes right; doing it without
  # noticing is not, and a release that contains one needs the three-release
  # pattern in docs/operations.md rather than a shrug.
  echo "   REVIEW — these remove or rename schema:"
  echo "$DESTRUCTIVE" | sed 's/^/     /'
  echo "   Confirm the rollback story in docs/operations.md before releasing."
fi

echo
echo "Migration safety check passed. The scratch database is being dropped."
