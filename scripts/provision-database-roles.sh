#!/usr/bin/env bash
# Create/rotate the separate migration and runtime database roles.
# Dry-run by default. This script changes database ownership and privileges only
# when the operator supplies --apply after reviewing the named environment.
# It deliberately requires an already-migrated schema so it can protect the
# existing audit table from runtime UPDATE/DELETE grants.

set -Eeuo pipefail

ENVIRONMENT="${1:-staging}"
APPLY="${2:-}"

case "$ENVIRONMENT" in
  local)   COMPOSE=(docker compose); ENV_FILE=".env" ;;
  staging) COMPOSE=(docker compose -f docker-compose.staging.yml --env-file .env.staging); ENV_FILE=".env.staging" ;;
  *) echo "Usage: $0 [local|staging] [--apply]" >&2; exit 2 ;;
esac

[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

required=(
  POSTGRES_DB POSTGRES_USER
  MIGRATION_DATABASE_USER MIGRATION_DATABASE_PASSWORD
  APP_DATABASE_USER APP_DATABASE_PASSWORD
)
for name in "${required[@]}"; do
  [ -n "${!name:-}" ] || { echo "$name must be set in $ENV_FILE" >&2; exit 1; }
done

if [ "$MIGRATION_DATABASE_USER" = "$APP_DATABASE_USER" ] \
  || [ "$MIGRATION_DATABASE_USER" = "$POSTGRES_USER" ] \
  || [ "$APP_DATABASE_USER" = "$POSTGRES_USER" ]; then
  echo "Bootstrap, migration and application database roles must all be different." >&2
  exit 1
fi

echo "Database: $POSTGRES_DB"
echo "Migration owner: $MIGRATION_DATABASE_USER"
echo "Runtime role: $APP_DATABASE_USER"
if [ "$APPLY" != "--apply" ]; then
  echo "Dry run only. Re-run with --apply after reviewing these identifiers."
  exit 0
fi

"${COMPOSE[@]}" exec -T \
  -e POSTGRES_DB \
  -e MIGRATION_DATABASE_USER \
  -e MIGRATION_DATABASE_PASSWORD \
  -e APP_DATABASE_USER \
  -e APP_DATABASE_PASSWORD \
  db psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  < infra/db/least-privilege.sql

echo "Database roles and privileges converged. Review the boolean verification row above."
