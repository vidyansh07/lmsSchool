# Backup and recovery

What is backed up, how it is verified, and exactly how to get it back.
Nothing here claims readiness that has not been exercised; the drill log
at the end records each real restore.

## What exists (verified 15 September 2026)

| Item | Mechanism | Schedule | Verified by |
| --- | --- | --- | --- |
| Database | `scripts/backup.sh staging` → `pg_dump --format=custom` to `backups/` on the host | 02:00 daily (cron, installed by `deploy.sh`) | `backup.sh --verify` restores into a scratch database and prints row counts and every sequence (D-088) |
| Database verify | `scripts/backup.sh staging --verify` | 03:00 Sundays | log in `backups/cron.log` |
| Retention | prune `*.dump` older than `BACKUP_KEEP_DAYS` (14) | 04:00 daily | |
| Off-host copy | `aws s3 cp` newest dump to `s3://$BACKUP_S3_BUCKET/db/` | 04:00 daily, **only when the bucket is configured — it is not yet** | |
| Object storage (student files, exports, resumes) | **none** | — | — |

## What the ERP adds

### Object storage backup (Phase 23 — built and scratch-tested)
`scripts/backup-media.sh [local|staging] [--verify]`:
- `mc mirror --overwrite --remove=false` from the application bucket
  (MinIO in this stack, reusing `storage-init`'s own alias/credentials
  pattern) to `backups/media/` on the host, then `aws s3 sync` to
  `s3://$BACKUP_S3_BUCKET/media/` when that variable is configured — it is
  not yet, same as the database's off-host copy above.
- `--verify` picks 20 random objects, reads each from the live bucket and
  from the backup copy, and compares SHA-256.
- Cron: 02:30 daily; verify 03:30 Sundays; same retention.
- Bucket versioning is enabled by `storage-init` (`mc version enable`) so an
  overwrite or delete is recoverable for 30 days independent of the mirror.

### Configuration backup
Roles, permissions, policies, forms, activity types, automations and
templates are rows — they are in the database dump. In addition,
`manage.py export_configuration > config-<date>.json` (Phase 23 — built)
writes them as a reviewable file nightly (02:15, cron) to `backups/config/`,
so a bad configuration change can be diffed and reverted without a full
restore.

### Encryption
Dumps at rest on the host are on an encrypted volume (EBS default); the S3
copy uses SSE-S3. `MFA_ENCRYPTION_KEY` is **not** in any backup; it lives
in the environment and must be restored from the secret store — a restore
without it makes every TOTP device unusable (users fall back to email OTP
and recovery codes; documented in the runbook).

## Objectives

| Objective | Value | Reason |
| --- | --- | --- |
| RPO (data loss) | 24 h for database and media; 0 for configuration changes made through the API (they are audited and can be replayed from the audit log) | nightly dumps |
| RTO (time to restore) | 2 h to a working stack on the same host; 4 h to a new host | measured in the drill |

To reach RPO 1 h later: enable WAL archiving to the bucket (`archive_command`
in the db container) — recorded as a follow-up, not part of this programme.

## Restore runbook (database)

1. Stop the application containers (`backend`, `worker`, `beat`), leave `db`.
2. Pick the dump: newest `backups/<db>-<stamp>.dump` or the S3 copy.
3. Restore to a **scratch** database first: `scripts/backup.sh staging --verify --from <file>` (`--from`, Phase 23, restores that named file instead of taking a fresh dump) and read the row counts and sequences.
4. If they match expectation, `pg_restore --clean --if-exists` into the live database **inside a maintenance window**, then `manage.py migrate` (no-op unless the dump predates the release), then `manage.py sync_permissions`.
5. Start the containers; `scripts/verify_demo.sh staging`; sign in; open the activity review to confirm the last audited action is the one expected.
6. Record the drill below.

## Restore runbook (media)

1. `mc mirror` / `aws s3 sync` from `backups/media/` (or the S3 copy) to the application bucket.
2. Spot-check five resources through the application (downloads go through the app, D-067).

## Disaster recovery (new host)

`scripts/deploy.sh <new-host> --branch <release>` builds the stack;
copy `.env.staging` from the secret store; restore database then media as
above; repoint DNS; run `verify_demo.sh`. Measured target 4 h.

## Backup implications per phase

| Phase | Implication |
| --- | --- |
| 1–3 | configuration rows in the dump; `export_configuration` covers them |
| 4–6 | `MFA_ENCRYPTION_KEY` outside the dump; OTP rows are short-lived and not needed |
| 8 | file-typed form values are objects in the bucket → media backup required before Phase 8 goes live |
| 19 | provider credentials outside the dump; Delivery rows in the dump |
| 20 | export files expire; they are not backed up (regenerable) |

## Drill log

| Date | Type | Source | Result | Time to restore | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-09-02 | database → scratch | staging dump | rows and sequences matched | 4 min | recorded in RELEASE_READINESS |
| 2026-09-14 | database → scratch (cron) | staging dump | pending first Sunday run (2026-09-20) | — | cron installed on deploy |
| (Phase 23) | database → live, media → bucket, new-host DR | | | | to be run and recorded before Phase 25 |

Recovery readiness is claimed only for rows in this table with a result.
