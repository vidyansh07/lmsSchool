#!/usr/bin/env bash
#
# Nightly database and media backups on a host, with weekly restore checks
# (23a) and a nightly configuration export (Phase 23,
# docs/erp/BACKUP_AND_RECOVERY.md).
#
#   ./scripts/install-backup-timer.sh            # install or refresh the cron entries
#   ./scripts/install-backup-timer.sh --remove   # take them out again
#
# What it installs, in the deploying user's crontab:
#
#   02:00 every day     ./scripts/backup.sh staging            a database dump
#   02:15 every day     manage.py export_configuration          roles, permissions,
#                       > backups/config/config-<date>.json     policies, forms,
#                                                                activity types,
#                                                                automations and
#                                                                templates, reviewable
#   02:30 every day     ./scripts/backup-media.sh staging       mirror the object
#                                                                storage bucket
#   03:00 every Sunday  ./scripts/backup.sh staging --verify    a dump that is
#                                                              restored into a
#                                                              scratch database
#                                                              and checked
#   03:30 every Sunday  ./scripts/backup-media.sh staging       20 random objects,
#                       --verify                                 hash-checked against
#                                                                the source
#   04:00 every day     prune dumps older than BACKUP_KEEP_DAYS (default 14),
#                       and, when BACKUP_S3_BUCKET is set in .env.staging and
#                       the aws CLI is present, copy the newest dump to
#                       s3://$BACKUP_S3_BUCKET/db/
#
# A backup nobody has restored is a hope, not a backup; the Sunday runs are
# what make the rest of the week's dumps and mirrors worth anything. Logs go
# to backups/cron.log next to the dumps.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARK="# grras-lms backups"
LOG="$REPO/backups/cron.log"

# `grep -v` exits 1 when nothing is left (a host with no crontab yet), which
# under `pipefail` would abort the subshell before the new entries are echoed
# and install an *empty* crontab. Hence the `|| true`.
existing() { crontab -l 2>/dev/null | grep -v "$MARK" || true; }

if [[ "${1:-}" == "--remove" ]]; then
  existing | crontab -
  echo "backup cron entries removed"
  exit 0
fi

mkdir -p "$REPO/backups" "$REPO/backups/config"
PRUNE="find $REPO/backups -name '*.dump' -mtime +\${BACKUP_KEEP_DAYS:-14} -delete"
UPLOAD="if [ -n \"\${BACKUP_S3_BUCKET:-}\" ] && command -v aws >/dev/null; then aws s3 cp \"\$(ls -t $REPO/backups/*.dump | head -1)\" \"s3://\${BACKUP_S3_BUCKET}/db/\" >> $LOG 2>&1; fi"
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging"
EXPORT_CONFIG="mkdir -p $REPO/backups/config && $COMPOSE exec -T backend python manage.py export_configuration > $REPO/backups/config/config-\$(date +%Y%m%d).json"

ENTRIES=$(cat <<CRON
0 2 * * * cd $REPO && ./scripts/backup.sh staging >> $LOG 2>&1 $MARK
15 2 * * * cd $REPO && $EXPORT_CONFIG 2>> $LOG $MARK
30 2 * * * cd $REPO && ./scripts/backup-media.sh staging >> $LOG 2>&1 $MARK
0 3 * * 0 cd $REPO && ./scripts/backup.sh staging --verify >> $LOG 2>&1 $MARK
30 3 * * 0 cd $REPO && ./scripts/backup-media.sh staging --verify >> $LOG 2>&1 $MARK
0 4 * * * cd $REPO && set -a && . ./.env.staging && set +a && $PRUNE && $UPLOAD $MARK
CRON
)

(existing; echo "$ENTRIES") | crontab -
echo "backup cron entries installed for $(whoami):"
crontab -l | grep "$MARK" | sed 's/ #.*//' | sed 's/^/  /'
