#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploy the staging stack to a host over SSH.
#
#   ./scripts/deploy.sh ubuntu@ec2-….amazonaws.com [--key vidyansh.pem] \
#       [--branch feat/x] [--seed] [--import-sitp DIR]
#
# What it does, in order, stopping at the first failure:
#   1. backs the database up on the host — a deploy that cannot be undone is a
#      deploy nobody should run;
#   2. fetches and checks out the branch on the host — the host pulls from the
#      repository's origin, so push first;
#   3. builds and starts the stack; migrations apply on backend start
#      (RUN_MIGRATIONS=true in docker-compose.staging.yml);
#   4. waits for the backend to report ready;
#   5. optionally seeds the demo accounts and imports the SITP workbooks.
#
# It edits nothing on the host: hostname, ports and secrets live in the host's
# own .env.staging. If the host has local edits it stops and says so, rather
# than pulling over them.
# ---------------------------------------------------------------------------
set -euo pipefail

TARGET="${1:?usage: $0 user@host [--key pem] [--branch name] [--seed] [--import-sitp DIR]}"
shift
KEY=""
BRANCH=""
SEED=false
IMPORT_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --key) KEY="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --seed) SEED=true; shift ;;
    --import-sitp) IMPORT_DIR="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
[ -n "$KEY" ] && SSH_OPTS+=(-i "$KEY")
COMPOSE='docker compose -f docker-compose.staging.yml --env-file .env.staging'

# Every remote step runs inside the checkout, whichever directory that is.
remote() {
  ssh "${SSH_OPTS[@]}" "$TARGET" \
    "set -euo pipefail; cd \"\$(dirname \"\$(find ~ /srv /opt -maxdepth 3 -name docker-compose.staging.yml 2>/dev/null | head -1)\")\"; $*"
}

echo "▶ host: $TARGET"
remote 'echo "  checkout: $(pwd) @ $(git rev-parse --abbrev-ref HEAD) $(git rev-parse --short HEAD)"'

echo "▶ 1/5 backup"
remote './scripts/backup.sh staging 2>&1 | tail -2'

echo "▶ 2/5 code"
remote 'test "$(git status --short | wc -l)" -eq 0 || { echo "  the host has local edits; resolve them first:"; git status --short; exit 1; }'
if [ -n "$BRANCH" ]; then
  remote "git fetch -q --prune origin && git checkout -q '$BRANCH' && git pull -q --ff-only origin '$BRANCH'"
else
  remote 'git pull -q --ff-only'
fi
remote 'echo "  now at $(git rev-parse --short HEAD): $(git log -1 --format=%s | cut -c1-72)"'

echo "▶ 3/5 build and start"
remote "$COMPOSE up -d --build --remove-orphans 2>&1 | grep -E 'Built|Started|Created|Recreated|rror' | tail -12"

echo "▶ 4/5 ready?"
remote "for i in \$(seq 1 60); do
  if $COMPOSE exec -T backend curl -fsS http://localhost:8000/health/ready/ >/dev/null 2>&1; then echo '  backend ready'; break; fi
  if [ \$i -eq 60 ]; then echo '  backend never became ready'; $COMPOSE logs --tail=40 backend; exit 1; fi
  sleep 3
done"
remote "$COMPOSE ps --format '  {{.Service}}\t{{.Status}}'"

if [ "$SEED" = true ]; then
  echo "▶ 5/5 seed: demo accounts"
  remote "$COMPOSE exec -T backend python manage.py seed_demo_data 2>&1 | grep -v grras.audit | tail -3"
fi

if [ -n "$IMPORT_DIR" ]; then
  echo "▶ 5/5 seed: SITP workbooks from $IMPORT_DIR"
  ACTOR=$(remote "$COMPOSE exec -T backend python manage.py shell -c \"from apps.accounts.models import User; print(User.objects.filter(role='admin').order_by('email').values_list('email', flat=True).first())\" 2>/dev/null | tail -1")
  echo "  as $ACTOR"
  STAGE=$(mktemp -d)
  rsync -a --include='*/' --include='*.xlsx' --exclude='*' "$IMPORT_DIR/" "$STAGE/"
  rsync -az -e "ssh ${SSH_OPTS[*]}" "$STAGE/" "$TARGET:/tmp/sitp-import/"
  rm -rf "$STAGE"
  # The production image mounts no source tree and runs as an unprivileged
  # user for whom /app is read-only, so the files go to /tmp inside the
  # running container for the duration of the import.
  remote "$COMPOSE cp /tmp/sitp-import backend:/tmp/sitp-import >/dev/null"
  remote "$COMPOSE exec -T backend python manage.py import_sitp_workbooks /tmp/sitp-import --actor '$ACTOR' --report /tmp/sitp-import-report.json 2>&1 | grep -v 'grras.audit\|UserWarning\|warn(msg)' | tail -4"
  remote "$COMPOSE cp backend:/tmp/sitp-import-report.json ./backups/sitp-import-report-\$(date +%Y%m%dT%H%M%SZ).json >/dev/null && echo '  report kept under backups/ on the host'"
fi

echo "▶ done"
