# Secure staging release runbook

Last updated: 14 October 2026

This is the operational source of truth for the current staging preparation.
It deliberately separates code readiness from changes to the live AWS host.

## Current release state

| Area | State | Meaning |
| --- | --- | --- |
| Naming and navigation | Implemented locally | Plain-language labels, one destination per sidebar tree, and custom-role navigation no longer falls back to a broader base role |
| Logging | Implemented locally | Structured security fields and redaction for credentials, tokens, request bodies and exception text |
| Upload scanning | Implemented locally | ClamAV streams file bytes on the private Compose network and fails closed |
| Database privileges | Implemented locally, not applied | Separate bootstrap, migration-owner and runtime roles; audit rows are append-only to the runtime role |
| Administrator provisioning | Implemented locally, not run | Repeat-safe command; normal password setup and email verification only |
| Backups | Code corrected, live proof pending | Cron date escaping fixed; media script executable; off-host copies require SSE-KMS |
| AWS cleanup | **Not run** | Requires a current read-only inventory, verified restore, exact delete list and separate approval |
| Live deployment | **Not run** | This branch has not changed the staging host |

## Architecture in scope

- Django/DRF backend with PostgreSQL, Redis and Celery.
- Next.js frontend behind Caddy on a single HTTPS origin.
- Private S3-compatible object storage for uploads.
- Docker Compose staging deployment on EC2.
- Capability-based server authorization with centre and object-level scopes.
- Application audit records in PostgreSQL and operational logs on stdout.

The frontend is never an authorization boundary. Sidebar visibility is only a
convenience; Django permissions and object-scoping remain authoritative.

## Roles and workflow boundaries

| Role | Normal workflow | Enforced scope |
| --- | --- | --- |
| Counsellor | Enquiries, registration, enrolment, fees, follow-ups and transfers | Centre-scoped capabilities |
| Manager | Batches, trainers, schedules, reviews, performance and academic operations | Centre-scoped capabilities; additionally holds trainer create/update, requirement management and policy view |
| Trainer | Today's classes, attendance, reports, assignments, tests, projects and exams | Assigned courses, batches, sessions and students |
| Administrator | Accounts, roles, centres, policies, forms, automation, templates, exports and recovery | Application-wide capabilities; not a Django staff user or superuser |
| Superadmin | Platform configuration, permission locking and permanent purge | Explicitly reserved irreversible/platform actions |

Important product fact: the built-in counsellor and manager roles still share
most centre-scoped capabilities. The labels now express job ownership, but the
server does not yet enforce a strict “counsellor writes admissions only,
manager writes academics only” split. Narrowing those existing rights would be
a breaking permission change and needs a separate approved capability matrix.

## Navigation and wording contract

- Route namespaces remain stable: `/admissions`, `/manage`, `/teaching`,
  `/admin` and `/my-*`.
- Stored role values, capability slugs and API paths are not renamed for a
  cosmetic change.
- User-facing labels use familiar nouns and actions: **Admissions**,
  **Academic operations**, **Today's class**, **Class schedule**,
  **User accounts**, **Course catalogue**, **Results and reports**,
  **Rules and policies**, **Form builder**, **Form inbox** and
  **Message templates**.
- A user with a custom role sees only its explicit capabilities. Built-in
  assignment-scoped trainer fallbacks do not widen a custom role.

## Logging policy

Operational logs answer whether a service is healthy. Audit records answer who
changed a security- or business-relevant record.

Log:

- successful and failed authentication;
- authorization denials and suspicious access;
- administrative actions and permission changes;
- important create, update, export and delete events;
- security configuration changes and background-job failures;
- timestamp, level, event type, request ID, actor ID and resource identifiers.

Never log:

- passwords, password hashes, OTPs or recovery/verification codes;
- access/refresh tokens, cookies, API secrets, database URLs or private keys;
- signed URLs, full request bodies or full records containing personal data;
- payment credentials or bank account values.

The log filter redacts structured context, interpolated message arguments and
exception text. JSON logs expose optional `event_type`, `actor_id`,
`resource_type` and `resource_id` fields. Keep log access restricted and set
retention in the host/cloud log destination; database audit retention must use
a separately authorized process because the runtime role cannot update or
delete audit rows.

## Database role rollout

The live database must already contain the migrated schema before role
convergence. The guard in `infra/db/least-privilege.sql` refuses an empty schema
so the audit-table exception cannot be skipped silently.

PostgreSQL row-level policies were not added in this pass. The application is
single-institution with centre/object boundaries spread across related models,
not a database shared by independent organisations; an incomplete table-by-
table RLS rollout would create false confidence and break valid joins. Current
isolation is enforced by server capabilities and scoped querysets. Both new
database roles are nevertheless `NOBYPASSRLS`, so a future reviewed RLS design
cannot be bypassed by these connections. Do not place another organisation's
data in this staging database; a multi-organisation deployment needs its own
approved tenant model, migration and policy tests first.

1. Put unique values for `POSTGRES_USER`, `MIGRATION_DATABASE_USER` and
   `APP_DATABASE_USER` in the staging secret store. Never send their passwords
   in chat or place them in command history.
2. Confirm a verified database backup exists.
3. Review identifiers without changing the database:

   ```bash
   ./scripts/provision-database-roles.sh staging
   ```

4. During the approved maintenance window, converge ownership and grants:

   ```bash
   ./scripts/provision-database-roles.sh staging --apply
   ```

5. Confirm the printed booleans: neither role is superuser, the application
   role has schema usage but no schema create, and it has audit insert but no
   audit update/delete.
6. Deploy. Migrations run once with `MIGRATION_DATABASE_URL`; web and Celery use
   the lower-privilege `DATABASE_URL`.

Rollback: restore the previous environment file, re-grant the former runtime
role only if service restoration requires it, redeploy the previous commit,
and record every temporary grant. Do not make the application role a
superuser.

## Administrator provisioning

Approved email spellings are held exactly as supplied at the command boundary:

- `DeepRatan@GrrasSolutions.In`
- `Ritesh@Grrassolutions.In`

The user model normalizes email case for uniqueness. The command creates an
application `admin`, not a Django `is_staff`/`is_superuser` account. It refuses
to silently promote or alter an existing mismatched account.

Run each command without `--apply` first, replacing the name and centre
placeholders only after they are confirmed:

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T backend \
  python manage.py provision_staging_admin \
  --email 'DeepRatan@GrrasSolutions.In' \
  --first-name '<confirmed-first-name>' --last-name '<confirmed-last-name>' \
  --branch-code '<confirmed-centre-code>'

docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T backend \
  python manage.py provision_staging_admin \
  --email 'Ritesh@Grrassolutions.In' \
  --first-name '<confirmed-first-name>' --last-name '<confirmed-last-name>' \
  --branch-code '<confirmed-centre-code>'
```

After reviewing the dry-run output, repeat with `--apply`. The command sends
the ordinary password-setup and verification messages. It never accepts a
password, marks an email verified or bypasses the normal verification flow.
Check delivery in the SMTP provider; a successful command means the mail was
requested, not that it arrived or was opened.

## Backup gate before cleanup

All of these must pass in the same maintenance window:

```bash
./scripts/backup.sh staging --verify
./scripts/backup-media.sh staging --verify
docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T backend \
  python manage.py export_configuration
```

Required evidence:

- database dump path, size, UTC timestamp and scratch-restore result;
- media mirror path, object count and sampled SHA-256 result;
- configuration export path and non-zero size;
- off-host S3 object versions encrypted with the approved KMS key;
- EBS volume/snapshot encryption status and snapshot/recovery-point IDs;
- who can decrypt/restore, plus a tested restoration procedure;
- RPO, RTO and retention owner.

Local-only backups are not enough for destructive cleanup. The corrected cron
escapes `%` in the configuration-export date and requires
`BACKUP_KMS_KEY_ID` whenever `BACKUP_S3_BUCKET` is configured.

## AWS cleanup approval boundary

Known host from the last audit: EC2 instance
`i-0e4141f6e0ec4a115` (`t2.large`, `us-east-1f`), security group
`sg-031d2d3bcc598f3bd`, VPC `vpc-08061ad3042f7bd26`, subnet
`subnet-02f40caeb181b1746`. This is not a complete current inventory and must be
re-verified after AWS login.

Classify the exact resources before any delete command is proposed:

| Class | Examples | Action |
| --- | --- | --- |
| A — reset | Application rows, queued jobs, cache keys, search data, staging uploads | Delete only after dependency order and backup proof are approved |
| B — retain | Schema, migrations, roles/capabilities, centres needed for login, secrets, network, TLS and infrastructure | Preserve |
| C — retain/protect | Audit/security logs, backup verification records and incident evidence | Preserve according to retention policy |
| D — preserve backup | Database dumps/snapshots, media mirror, configuration export, KMS metadata | Protect and test before Class A changes |

Do not delete the EC2 instance, EBS volume, database volume, bucket, backup,
KMS key, IAM identity, log group or shared resource merely to reset application
data. A data-only reset inside a transaction or maintenance command is safer
than infrastructure destruction.

No cleanup command is authorized by approval of this runbook. The next cleanup
proposal must name every database, Docker volume, bucket/prefix, queue/cache and
log target; show exact commands and dependency order; state what remains; and
receive a separate explicit approval.

## Deployment and verification

### Local verification recorded on 14 October 2026

| Check | Result |
| --- | --- |
| Backend regression | 3,769 passed; 4 documented skips |
| Frontend unit/component tests | 157 files; 1,477 passed |
| Frontend lint and TypeScript | Passed |
| Next.js production build | Passed with the webpack builder |
| Django migration drift and deployment checks | No changes; no deployment warnings |
| Ruff and Bandit | Passed; no Bandit findings |
| Dependency audit | Python clean; production npm tree clean at high severity |
| Secret scan | No findings across 201 Git commits |
| Database-role scratch test | Runtime audit INSERT allowed; audit UPDATE/DELETE and schema CREATE denied; repeat run idempotent |

These checks do not prove the target AWS host. A role-by-role browser journey,
real SMTP delivery, ClamAV scan, backup/restore drill, monitoring checks and the
approved data reset must still be exercised against staging after deployment.

Preflight:

- protect `.env.staging` as owner-readable only (`chmod 600`);
- use SMTP, shared Redis, HTTPS, secure cookies, explicit CORS/CSRF origins and
  a unique MFA encryption key;
- configure `UPLOAD_SCANNER=clamav` and keep port 3310 private;
- confirm enough host memory for the scanner before enabling it;
- run lint, types, unit tests, backend tests, Bandit, dependency audits,
  migration drift and `manage.py check --deploy`;
- prove production dependencies have no high/critical advisories;
- use synthetic data except the two approved administrator identities.

Deployment:

1. verified backup;
2. reviewed database-role convergence;
3. build immutable images;
4. run the one-shot migration service;
5. start lower-privilege services;
6. verify health, schema, anonymous denial, CSP/headers, private storage,
   ClamAV, worker and scheduler;
7. dry-run then apply administrator provisioning;
8. confirm SMTP delivery and let each recipient complete password setup and
   email verification themselves;
9. run the role-by-role browser journeys.

Rollback:

- redeploy the previous image/commit;
- apply a reviewed reverse migration only when Django provides a safe one;
- otherwise restore the verified database backup and matching media version;
- rotate any credential that may have reached a log or unauthorized party;
- validate health and authorization again before reopening staging.

## Remaining approvals and inputs

- First and last name for each administrator.
- Centre/branch code for each administrator.
- Confirmation that application `admin`—not Django superuser—is intended.
- SMTP provider/sender configuration and permission to inspect delivery status
  (never send passwords, API keys or private keys in chat).
- Staging hostname and whether access is public, VPN-only or IP-restricted.
- AWS login for the current read-only inventory.
- Backup bucket, KMS key, retention, RPO/RTO and restore owner.
- Product decision on whether counsellor and manager permissions should be
  strictly separated or remain overlapping centre-scoped roles.
- A separate approval for the final exact cleanup resource list and commands.
