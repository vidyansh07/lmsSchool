#!/usr/bin/env bash
#
# Nightly database backups on a host, with a weekly restore check (23a).
#
#   ./scripts/install-backup-timer.sh            # install or refresh the cron entries
#   ./scripts/install-backup-timer.sh --remove   # take them out again
#
# What it installs, in the deploying user's crontab:
#
#   02:00 every day     ./scripts/backup.sh staging            a dump
#   03:00 every Sunday  ./scripts/backup.sh staging --verify   a dump that is
#                                                              restored into a
#                                                              scratch database
#                                                              and checked
#   04:00 every day     prune dumps older than BACKUP_KEEP_DAYS (default 14),
#                       and, when BACKUP_S3_BUCKET is set in .env.staging and
#                       the aws CLI is present, copy the newest dump to
#                       s3://$BACKUP_S3_BUCKET/db/
#
# A backup nobody has restored is a hope, not a backup; the Sunday run is what
# makes the rest of the week's dumps worth anything. Logs go to
# backups/cron.log next to the dumps.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARK="# grras-lms backups"
LOG="$REPO/backups/cron.log"

if [[ "${1:-}" == "--remove" ]]; then
  (crontab -l 2>/dev/null | grep -v "$MARK") | crontab -
  echo "backup cron entries removed"
  exit 0
fi

mkdir -p "$REPO/backups"
PRUNE="find $REPO/backups -name '*.dump' -mtime +\${BACKUP_KEEP_DAYS:-14} -delete"
UPLOAD="if [ -n \"\${BACKUP_S3_BUCKET:-}\" ] && command -v aws >/dev/null; then aws s3 cp \"\$(ls -t $REPO/backups/*.dump | head -1)\" \"s3://\${BACKUP_S3_BUCKET}/db/\" >> $LOG 2>&1; fi"

ENTRIES=$(cat <<CRON
0 2 * * * cd $REPO && ./scripts/backup.sh staging >> $LOG 2>&1 $MARK
0 3 * * 0 cd $REPO && ./scripts/backup.sh staging --verify >> $LOG 2>&1 $MARK
0 4 * * * cd $REPO && set -a && . ./.env.staging && set +a && $PRUNE && $UPLOAD $MARK
CRON
)

(crontab -l 2>/dev/null | grep -v "$MARK"; echo "$ENTRIES") | crontab -
echo "backup cron entries installed for $(whoami):"
crontab -l | grep "$MARK" | sed 's/ #.*//' | sed 's/^/  /'
