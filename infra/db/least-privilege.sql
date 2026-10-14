-- Least-privilege PostgreSQL roles for a deployed GRRAS LMS.
--
-- Run through scripts/provision-database-roles.sh. Role names and passwords
-- come from environment variables via psql's \getenv command; they never live
-- in this file or appear as command-line arguments.

\set ON_ERROR_STOP on
\getenv database_name POSTGRES_DB
\getenv migration_role MIGRATION_DATABASE_USER
\getenv migration_password MIGRATION_DATABASE_PASSWORD
\getenv app_role APP_DATABASE_USER
\getenv app_password APP_DATABASE_PASSWORD

-- This is a convergence step for an existing migrated schema. On a brand-new
-- database, run the initial migration once with the bootstrap owner, then run
-- this script before any application process starts. Refusing an empty schema
-- is safer than granting broad default privileges and silently missing the
-- audit-table exception below.
DO $guard$
BEGIN
    IF to_regclass('public.audit_auditlog') IS NULL THEN
        RAISE EXCEPTION
            'audit_auditlog is missing; apply the initial schema with the bootstrap role first.';
    END IF;
END
$guard$;

-- Create once, then converge the security attributes and password on every
-- approved run. Re-running the script rotates credentials without duplicating
-- roles or weakening them.
SELECT format('CREATE ROLE %I LOGIN', :'migration_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_role')
\gexec
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'migration_role', :'migration_password'
)
\gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
    :'app_role', :'app_password'
)
\gexec

-- The migration role owns the database objects. Transfer existing objects as
-- well as setting defaults for objects created by future migrations.
SELECT format('ALTER DATABASE %I OWNER TO %I', :'database_name', :'migration_role')
\gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', :'migration_role')
\gexec
SELECT format('ALTER TABLE %I.%I OWNER TO %I', schemaname, tablename, :'migration_role')
FROM pg_tables
WHERE schemaname = 'public'
\gexec
SELECT format('ALTER SEQUENCE %I.%I OWNER TO %I', schemaname, sequencename, :'migration_role')
FROM pg_sequences
WHERE schemaname = 'public'
\gexec
SELECT format('ALTER VIEW %I.%I OWNER TO %I', schemaname, viewname, :'migration_role')
FROM pg_views
WHERE schemaname = 'public'
\gexec
SELECT format('ALTER MATERIALIZED VIEW %I.%I OWNER TO %I', schemaname, matviewname, :'migration_role')
FROM pg_matviews
WHERE schemaname = 'public'
\gexec

REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database_name')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'app_role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'migration_role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_role')
\gexec

-- Runtime: row operations only. No schema creation, role management or RLS
-- bypass. DELETE remains because the service layer legitimately deletes some
-- drafts and dependent rows.
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I',
    :'app_role'
)
\gexec
SELECT format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I',
    :'app_role'
)
\gexec
SELECT format('REVOKE CREATE ON SCHEMA public FROM %I', :'app_role')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'migration_role', :'app_role'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'migration_role', :'app_role'
)
\gexec

-- Security history is append-only to the everyday application connection.
-- The application can insert and read audit rows but cannot rewrite or erase
-- them. A dedicated retention process, if approved later, must use a separate
-- role and leave its own external audit trail.
SELECT format('REVOKE UPDATE, DELETE ON TABLE audit_auditlog FROM %I', :'app_role')
\gexec

-- Verification output contains role names and booleans only, never passwords.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
FROM pg_roles
WHERE rolname IN (:'migration_role', :'app_role')
ORDER BY rolname;
SELECT
    has_schema_privilege(:'app_role', 'public', 'USAGE') AS app_schema_usage,
    has_schema_privilege(:'app_role', 'public', 'CREATE') AS app_schema_create,
    has_table_privilege(:'app_role', 'audit_auditlog', 'INSERT') AS audit_insert,
    has_table_privilege(:'app_role', 'audit_auditlog', 'UPDATE') AS audit_update,
    has_table_privilege(:'app_role', 'audit_auditlog', 'DELETE') AS audit_delete;
