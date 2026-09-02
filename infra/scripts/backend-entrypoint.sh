#!/usr/bin/env sh
# ---------------------------------------------------------------------------
# Backend container entrypoint.
#
# Waits for PostgreSQL, optionally applies migrations, then execs the chosen
# process. Migrations are opt-in (RUN_MIGRATIONS=true) because in a real
# deployment they are a separate, reviewed release step rather than something
# every replica races to run on boot.
# ---------------------------------------------------------------------------
set -eu

WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"

wait_for_database() {
  echo "[entrypoint] waiting for the database (timeout ${WAIT_TIMEOUT}s)"
  elapsed=0
  until python -c "
import sys
import django
django.setup()
from django.db import connections
try:
    connections['default'].ensure_connection()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    elapsed=$((elapsed + 2))
    if [ "${elapsed}" -ge "${WAIT_TIMEOUT}" ]; then
      echo "[entrypoint] database did not become available in ${WAIT_TIMEOUT}s" >&2
      exit 1
    fi
    sleep 2
  done
  echo "[entrypoint] database is available"
}

case "${1:-}" in
  runserver|gunicorn|migrate|seed)
    wait_for_database
    ;;
esac

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "[entrypoint] applying migrations"
  python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-false}" = "true" ]; then
  echo "[entrypoint] collecting static files"
  python manage.py collectstatic --noinput
fi

case "${1:-}" in
  runserver)
    exec python manage.py runserver 0.0.0.0:8000
    ;;
  gunicorn)
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --threads "${GUNICORN_THREADS:-2}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --graceful-timeout 30 \
      --max-requests 1000 \
      --max-requests-jitter 100 \
      --access-logfile - \
      --error-logfile -
    ;;
  migrate)
    exec python manage.py migrate --noinput
    ;;
  seed)
    exec python manage.py seed_demo_data
    ;;
  *)
    exec "$@"
    ;;
esac
