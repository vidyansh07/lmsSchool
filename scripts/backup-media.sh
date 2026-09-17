#!/usr/bin/env bash
#
# Object storage backup (Phase 23, §15.7 / docs/erp/BACKUP_AND_RECOVERY.md).
#
#   ./scripts/backup-media.sh staging                 # mirror the bucket
#   ./scripts/backup-media.sh staging --verify         # mirror it, then hash-check a sample
#
# Same [local|staging] [--verify] shape as scripts/backup.sh, which keeps
# doing the database (ADR-19 — backups add the bucket, not a new tool). A
# mirror nobody has spot-checked is a hope, not a backup, same as a dump
# nobody has restored.
#
# `mc mirror --overwrite --remove=false` copies new and changed objects into
# backups/media/ on the host without ever deleting anything there itself — an
# accidental delete in the live bucket does not propagate to the backup.
# `--verify` then picks 20 random objects, reads each one from the live
# bucket and from the backup copy, and compares SHA-256.
#
# There is no long-running `mc` container in either compose file — `storage-
# init` (docker-compose.staging.yml) exists only to create the bucket once and
# exits — so this script starts a throwaway one with `docker compose run`,
# reusing storage-init's own alias/credentials pattern rather than inventing a
# second way to authenticate to the bucket.

set -Eeuo pipefail

ENVIRONMENT="${1:-staging}"
VERIFY="${2:-}"
OUT_DIR="${BACKUP_DIR:-./backups}"
MEDIA_DIR="$OUT_DIR/media"

case "$ENVIRONMENT" in
  local)   COMPOSE=(docker compose); ENV_FILE=".env" ;;
  staging) COMPOSE=(docker compose -f docker-compose.staging.yml --env-file .env.staging); ENV_FILE=".env.staging" ;;
  *) echo "Usage: $0 [local|staging] [--verify]" >&2; exit 2 ;;
esac

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

# Nothing to mirror when the environment keeps files on the container's own
# filesystem instead of object storage (local development, by default) — this
# is the same "only when configured" shape backup.sh already uses for its
# off-host S3 copy, not an error.
if [ "${FILE_STORAGE_BACKEND:-local}" != "s3" ] || [ -z "${AWS_STORAGE_BUCKET_NAME:-}" ]; then
  echo "FILE_STORAGE_BACKEND is not 's3' (or no bucket is configured) for '$ENVIRONMENT' -- nothing to mirror."
  exit 0
fi

BUCKET="${AWS_STORAGE_BUCKET_NAME:?AWS_STORAGE_BUCKET_NAME must be set}"
ENDPOINT="${AWS_S3_ENDPOINT_URL:-http://storage:9000}"
ACCESS_KEY="${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID must be set}"
SECRET_KEY="${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY must be set}"

mkdir -p "$MEDIA_DIR"
# Resolved once, from inside the directory itself: `$(pwd)/$MEDIA_DIR` would
# double the path when BACKUP_DIR (like backup.sh's OUT_DIR) is already
# absolute, mounting the wrong directory into the container without error.
MEDIA_DIR="$(cd "$MEDIA_DIR" && pwd)"

# Scripts, not inline -c strings: the mirror/verify logic each has enough
# quoting of its own without also fighting docker compose's and the shell's.
# Credentials travel in as -e vars, never interpolated into the script text.
WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

cat > "$WORKDIR/mirror.sh" <<'SCRIPT'
set -e
mc alias set src "$MC_ENDPOINT" "$MC_ACCESS_KEY" "$MC_SECRET_KEY" >/dev/null
mc mirror --overwrite --remove=false "src/$MC_BUCKET" /backup
SCRIPT

echo "Mirroring bucket '$BUCKET' from the '$ENVIRONMENT' stack to $MEDIA_DIR ..."
"${COMPOSE[@]}" run --rm --no-deps -T \
  -e MC_ENDPOINT="$ENDPOINT" -e MC_ACCESS_KEY="$ACCESS_KEY" -e MC_SECRET_KEY="$SECRET_KEY" -e MC_BUCKET="$BUCKET" \
  -v "$MEDIA_DIR:/backup" \
  -v "$WORKDIR/mirror.sh:/mirror.sh:ro" \
  --entrypoint /bin/bash storage-init /mirror.sh
echo "Mirror complete."

if [ -n "${BACKUP_S3_BUCKET:-}" ] && command -v aws >/dev/null; then
  echo "Copying media backup to s3://$BACKUP_S3_BUCKET/media/…"
  aws s3 sync "$MEDIA_DIR" "s3://$BACKUP_S3_BUCKET/media/"
fi

if [ "$VERIFY" != "--verify" ]; then
  echo
  echo "Not verified. Run with --verify to prove this mirror matches the source."
  exit 0
fi

echo
echo "Verifying: picking 20 random objects and comparing SHA-256 against the source…"

cat > "$WORKDIR/verify.sh" <<'SCRIPT'
set -e
mc alias set src "$MC_ENDPOINT" "$MC_ACCESS_KEY" "$MC_SECRET_KEY" >/dev/null
mc ls --recursive "src/$MC_BUCKET" | shuf -n 20 > /tmp/sample.txt || true

if [ ! -s /tmp/sample.txt ]; then
  echo "Bucket is empty -- nothing to verify."
  exit 0
fi

mismatch=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  key="${line##* }"
  if [ ! -f "/backup/$key" ]; then
    echo "  MISSING   $key (in source, not in the backup copy)"
    mismatch=1
    continue
  fi
  src_hash="$(mc cat "src/$MC_BUCKET/$key" | sha256sum | cut -d' ' -f1)"
  backup_hash="$(sha256sum "/backup/$key" | cut -d' ' -f1)"
  if [ "$src_hash" = "$backup_hash" ]; then
    echo "  ok        $key"
  else
    echo "  MISMATCH  $key"
    mismatch=1
  fi
done < /tmp/sample.txt

exit "$mismatch"
SCRIPT

"${COMPOSE[@]}" run --rm --no-deps -T \
  -e MC_ENDPOINT="$ENDPOINT" -e MC_ACCESS_KEY="$ACCESS_KEY" -e MC_SECRET_KEY="$SECRET_KEY" -e MC_BUCKET="$BUCKET" \
  -v "$MEDIA_DIR:/backup" \
  -v "$WORKDIR/verify.sh:/verify.sh:ro" \
  --entrypoint /bin/bash storage-init /verify.sh

echo
echo "Media backup verified."
