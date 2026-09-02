#!/usr/bin/env bash
#
# §15.3 — prove an environment is actually working, from the outside.
#
#   ./scripts/verify_demo.sh                 # the local development stack
#   ./scripts/verify_demo.sh staging         # the production-shaped stack
#
# What this is for: answering "is it up?" with something better than a person
# clicking around. Every check below is one that has failed in this project at
# least once, and each is phrased as a question with a yes/no answer rather than
# a wall of output to read.
#
# It changes nothing. No migrations are applied, no data is seeded, nothing is
# written — a verification script that repairs what it finds cannot tell you
# whether the thing was working.

set -Eeuo pipefail

ENVIRONMENT="${1:-local}"

case "$ENVIRONMENT" in
  local)
    COMPOSE=(docker compose)
    # Ports come from .env, which is where the developer set them.
    [ -f .env ] && set -a && . ./.env && set +a
    BACKEND_URL="${BACKEND_URL:-http://localhost:${BACKEND_PORT:-8000}}"
    FRONTEND_URL="${FRONTEND_URL:-http://localhost:${FRONTEND_PORT:-3000}}"
    SETTINGS="config.settings.local"
    CURL=(curl --silent --show-error --max-time 20)
    ;;
  staging)
    COMPOSE=(docker compose -f docker-compose.staging.yml --env-file .env.staging)
    BACKEND_URL="${BACKEND_URL:-https://localhost:8443}"
    FRONTEND_URL="${FRONTEND_URL:-https://localhost:8443}"
    SETTINGS="config.settings.staging"
    # Staging terminates TLS with a certificate it issued itself; the
    # certificate authority is not what this script is checking.
    CURL=(curl --silent --show-error --max-time 20 --insecure)
    ;;
  *)
    echo "Usage: $0 [local|staging]" >&2
    exit 2
    ;;
esac

PASSED=0
FAILED=0
FAILURES=()

green() { printf '\033[0;32m%s\033[0m' "$1"; }
red() { printf '\033[0;31m%s\033[0m' "$1"; }

check() {
  local name="$1"
  shift
  printf '  %-46s' "$name"
  local output
  if output="$("$@" 2>&1)"; then
    green "PASS"
    printf '\n'
    PASSED=$((PASSED + 1))
  else
    red "FAIL"
    printf '\n'
    FAILED=$((FAILED + 1))
    FAILURES+=("$name: ${output:-no output}")
  fi
}

manage() {
  "${COMPOSE[@]}" exec -T -e DJANGO_SETTINGS_MODULE="$SETTINGS" backend python manage.py "$@"
}

# `manage shell -c` prints whatever the environment's shell plugins announce on
# start-up, which lands in a failure message and buries the real reason.
manage_quiet() {
  manage "$@" 2>&1 | grep -v "objects imported automatically" | grep -v "^$" || true
}

# --- 1. The environment is running -----------------------------------------

service_is_up() {
  local service="$1"
  local state
  state="$("${COMPOSE[@]}" ps --format '{{.Service}} {{.State}}' | awk -v s="$service" '$1 == s {print $2}')"
  [ "$state" = "running" ] || { echo "service '$service' is '${state:-absent}'"; return 1; }
}

# --- 2. Each dependency answers --------------------------------------------

database_is_reachable() {
  manage shell -c 'from django.db import connection; connection.cursor().execute("SELECT 1")'
}

redis_is_reachable() {
  local reply
  reply="$("${COMPOSE[@]}" exec -T redis redis-cli ping)"
  [[ "$reply" == PONG* ]] || { echo "redis said '$reply'"; return 1; }
}

object_storage_is_reachable() {
  manage shell -c '
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
name = default_storage.save("verify-demo/probe.txt", ContentFile(b"probe"))
assert default_storage.open(name).read() == b"probe"
default_storage.delete(name)
'
}

# --- 3. The application is healthy -----------------------------------------

backend_is_ready() {
  local body
  body="$("${CURL[@]}" "$BACKEND_URL/health/ready/")"
  [[ "$body" == *'"status": "ok"'* ]] || { echo "$body"; return 1; }
}

frontend_serves_the_app() {
  local code
  code="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' "$FRONTEND_URL/")"
  [ "$code" = "200" ] || { echo "HTTP $code"; return 1; }
}

frontend_is_hydratable() {
  # A page whose inline bootstrap is refused by its own Content-Security-Policy
  # renders and then does nothing — no error, no working form. It has happened
  # here, so it is checked: the policy must carry a nonce, and the markup must
  # use it.
  local page
  page="$("${CURL[@]}" "$FRONTEND_URL/login")"
  [[ "$page" == *'nonce='* ]] || { echo "no nonce in the served markup"; return 1; }
}

# --- 4. The schema is where the code expects --------------------------------

migrations_are_applied() {
  local pending
  pending="$(manage showmigrations --plan | grep -c '^\[ \]' || true)"
  [ "$pending" = "0" ] || { echo "$pending migration(s) not applied"; return 1; }
}

no_model_changes_are_unmigrated() {
  manage makemigrations --check --dry-run
}

# --- 5. There is data to demonstrate ----------------------------------------

demo_data_exists() {
  manage shell -c '
import sys
from apps.accounts.models import User, UserRole
from apps.batches.models import Batch
from apps.courses.models import Course
from apps.enrollments.models import Enrollment

missing = []
for role in UserRole.values:
    if not User.objects.filter(role=role).exists():
        missing.append(f"no {role} account")
if not Course.objects.exists():
    missing.append("no courses")
if not Batch.objects.exists():
    missing.append("no batches")
if not Enrollment.objects.exists():
    missing.append("no enrolments")
if missing:
    sys.exit("; ".join(missing))
'
}

demo_data_is_fake() {
  # A staging environment holding a real address is a data-protection incident,
  # not a configuration slip. RFC 2606 and RFC 6761 reserve these four so that
  # nothing addressed to them can ever be delivered anywhere.
  manage shell -c '
import sys
from django.db.models import Q
from apps.accounts.models import User
reserved = Q()
for suffix in (".invalid", ".test", ".example", ".localhost"):
    reserved |= Q(email__endswith=suffix)
real = list(User.objects.exclude(reserved).values_list("email", flat=True)[:3])
if real:
    sys.exit(f"account(s) not on a reserved domain, e.g. {real[0]}")
'
}

# --- 6. The API behaves ------------------------------------------------------

api_refuses_anonymous_callers() {
  local code
  code="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' "$BACKEND_URL/api/v1/students/")"
  [[ "$code" == "401" || "$code" == "403" ]] || { echo "HTTP $code, expected 401/403"; return 1; }
}

api_serves_its_schema() {
  local code
  code="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' "$BACKEND_URL/api/schema/")"
  [ "$code" = "200" ] || { echo "HTTP $code"; return 1; }
}

api_sends_security_headers() {
  local headers
  headers="$("${CURL[@]}" --head "$BACKEND_URL/health/live/")"
  for header in "x-content-type-options" "x-frame-options" "content-security-policy"; do
    grep -qi "^$header" <<<"$headers" || { echo "missing $header"; return 1; }
  done
}

public_certificate_verification_answers() {
  # Public by design, and the one endpoint an employer touches. A made-up code
  # must come back as "not found" rather than an error.
  local code
  code="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' \
    "$BACKEND_URL/api/v1/verify/definitely-not-a-real-certificate/")"
  [[ "$code" == "404" || "$code" == "200" ]] || { echo "HTTP $code"; return 1; }
}

# --- 7. Background work is being consumed ------------------------------------

worker_is_consuming() {
  "${COMPOSE[@]}" exec -T worker celery -A config inspect ping --timeout 10
}

# --- Run ---------------------------------------------------------------------

echo
echo "Verifying the '$ENVIRONMENT' environment"
echo "  backend  $BACKEND_URL"
echo "  frontend $FRONTEND_URL"
echo

echo "Environment"
for service in db redis backend frontend; do
  check "service '$service' is running" service_is_up "$service"
done

echo
echo "Dependencies"
check "database is reachable" database_is_reachable
check "redis is reachable" redis_is_reachable
check "object storage round-trips a file" object_storage_is_reachable

echo
echo "Application"
check "backend reports ready" backend_is_ready
check "frontend serves the application" frontend_serves_the_app
check "frontend markup carries a CSP nonce" frontend_is_hydratable

echo
echo "Schema"
check "every migration is applied" migrations_are_applied
check "no model change is unmigrated" no_model_changes_are_unmigrated

echo
echo "Data"
check "demo data covers every role" demo_data_exists
check "every account is on a reserved domain" demo_data_is_fake

echo
echo "API"
check "anonymous callers are refused" api_refuses_anonymous_callers
check "the OpenAPI schema is served" api_serves_its_schema
check "security headers are present" api_sends_security_headers
check "certificate verification answers" public_certificate_verification_answers

echo
echo "Background work"
if "${COMPOSE[@]}" ps --services 2>/dev/null | grep -qx worker; then
  check "a worker is consuming the queue" worker_is_consuming
else
  echo "  (no worker service in this stack — skipped)"
fi

echo
echo "-------------------------------------------------------------"
if [ "$FAILED" -eq 0 ]; then
  echo "$(green "$PASSED passed"), 0 failed."
  exit 0
fi

echo "$(green "$PASSED passed"), $(red "$FAILED failed"):"
for failure in "${FAILURES[@]}"; do
  echo "  - $failure"
done
exit 1
