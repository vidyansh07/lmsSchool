# Operations

Migrations, backups, restores and rollback. Written for the person doing it at
an awkward hour, so every claim here has been executed rather than reasoned
about, and the transcript of what was checked is included.

---

## 1. Migrations

### What the schema is made of

58 migrations across 18 apps. Two properties, both verified rather than assumed:

**Nothing destructive.** There is no `RemoveField`, `DeleteModel`,
`RenameField` or `RenameModel` in the entire history:

```
$ grep -rn "migrations.RemoveField\|migrations.DeleteModel\|\
migrations.RenameField\|migrations.RenameModel" apps/*/migrations/*.py
(no output)
```

That is a property of how the project has been built so far, not a guarantee
about the future — see *Writing a destructive migration* below.

**Every hand-written migration reverses.** Nine migrations use `RunSQL` to
create the PostgreSQL sequences behind human-readable identifiers, and each one
carries a `reverse_sql`. None uses `RunPython`, so there is no data migration
whose reversal has to be reasoned about.

### Before a release

```bash
./scripts/check_migrations.sh staging
```

`check_migrations.sh` creates an empty database, migrates it from nothing,
reverses one app to zero and re-applies it, then drops the database. It touches
nothing else.

Last run, against the staging stack:

```
1. No model change is unmigrated
   ok — the models and the migrations agree
2. Fresh installation
   applied 76, pending 0
3. Reverse and re-apply
   reversed assessments to zero, re-applied assessments
4. Destructive operations in the history
   none — nothing in the history drops or renames anything
```

### Applying them in a deployment

Migrations run as `grras_migrate`, the role that owns the schema — not as the
application role, which has no DDL rights at all
(`infra/db/least-privilege.sql`). In the containers this means the **backend**
service runs them at start-up (`RUN_MIGRATIONS=true`) and the worker and
scheduler explicitly do not: two processes racing to migrate one database is how
a deployment corrupts its own schema.

### Writing a destructive migration

Don't, in one step. The pattern that keeps a rollback possible:

1. **Release A** — add the new column, write to both, read from the old.
2. **Release B** — read from the new. The old column is untouched and the code
   no longer needs it.
3. **Release C** — drop the old column, once release B has been stable long
   enough that rolling back to A is off the table.

Between A and B, and between B and C, the previous version of the application
still runs against the current schema. That is the only thing that makes a
rollback a rollback rather than a restore.

---

## 2. Backups

```bash
./scripts/backup.sh staging            # take one
./scripts/backup.sh staging --verify   # take one and prove it restores
```

The dump is PostgreSQL's custom format: compressed, and restorable
table-by-table with `pg_restore` — which is what you want when one table is the
problem and the rest of the institution is fine.

### What `--verify` does, and why it exists

A backup nobody has restored is a hope. `--verify` restores the dump into a
*separate scratch database*, counts what arrived, prints the state of every
identifier sequence, and drops the scratch database again. It never writes to
the database it dumped.

The sequences are checked explicitly because they are the failure that looks
like success: a restore that brought every table and no sequences would hand the
next student an identifier somebody already has, and nothing would complain
until two people held `GRS-S-00041`.

Verified against staging:

```
users 41 · courses 44 · batches 38 · enrolments 72 · attendance 93
assessment marks 21 · certificates 3 · audit entries 1272

student_public_id_seq at 40      certificate_number_seq at 3
batch_public_code_seq at 38      enrolment_public_code_seq at 72
course_public_code_seq at 44     trainer_public_id_seq at 5
```

### Object storage

Student files live in S3, not in the database, so a database dump does **not**
contain them. Bucket-level versioning plus a lifecycle policy is the mechanism;
this project has no bucket provisioned, so nothing here has been exercised
against a real one. It is a named gap in `docs/RELEASE_READINESS.md` rather than
a solved problem.

### Schedule and retention (to be set at deployment)

Nothing is scheduled by this repository. What a deployment needs to decide:

| | Suggested | Why |
| --- | --- | --- |
| Frequency | Nightly full, and before every release | A release is the most likely thing to need undoing |
| Retention | 30 daily, 12 monthly | An error found a month later is still findable |
| Location | A different account or project from the database | A backup in the blast radius is not a backup |
| Verification | `--verify` weekly, and always before a release | The only way to know |

---

## 3. Restore

```bash
# Into a scratch database first. Always.
docker compose -f docker-compose.staging.yml --env-file .env.staging \
  exec -T db psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE restore_target;"

docker compose -f docker-compose.staging.yml --env-file .env.staging \
  exec -T db pg_restore -U "$POSTGRES_USER" -d restore_target \
  --no-owner --no-privileges < backups/<dump>

# Look at it. Count rows, check the sequences, sign in.
# Only then repoint DATABASE_URL, and only with the application stopped.
```

Restoring over a live database is the one step worth being slow about. The
application must be stopped first — a running process holding connections to a
database being replaced under it produces errors that look like data corruption
and are not, which wastes the time you do not have.

---

## 4. Rollback

### What can be rolled back

**The application.** Deploy the previous image. Nothing in the current release
depends on schema the previous one lacks, because no migration in this project
removes anything.

**A migration.** Every migration here reverses, and `check_migrations.sh`
proves one does. `manage.py migrate <app> <number>` moves back.

### What cannot

**Data written since the backup.** A restore returns the database to the moment
the dump was taken. Everything after it is gone: registers marked, work handed
in, certificates issued. That is the cost of a restore, and it is why a restore
is the last option rather than the first.

**A destructive migration, once data is gone.** Reversing `RemoveField`
recreates an empty column, not its contents. There is no such migration in this
project today, and the three-release pattern above exists to keep it that way.

**An issued certificate that somebody has already verified.** The number is
public and may have been shared. Revoking it is the supported path — it still
verifies, and says it was withdrawn — and it is not the same as it never having
existed.

### Order of preference

1. Roll the application back. Fastest, loses nothing.
2. Reverse the migration, then roll the application back. Slower, still lossless.
3. Restore from a backup. Loses everything since the dump.

---

## 5. Environments

| | Local | Staging | Production |
| --- | --- | --- | --- |
| Compose file | `docker-compose.yml` | `docker-compose.staging.yml` | Platform-specific |
| Server | `runserver` | gunicorn | gunicorn |
| `DEBUG` | True | False | False, not configurable |
| TLS | none | Caddy, self-signed | At the ingress |
| Files | container volume | MinIO (S3 protocol) | S3 |
| Queue | Redis + worker + beat | same | same |
| Data | fake | fake, `.invalid` addresses | real |

Staging speaks https because the hardened settings mark the session cookie
`Secure`, and a browser on plain http silently refuses to store it: sign-in
appears to work and the next request is anonymous. Rather than weaken the
setting for staging — which would mean staging no longer tests what production
runs — the stack terminates TLS with a certificate Caddy issues itself.

Verify any environment with:

```bash
./scripts/verify_demo.sh staging
```
