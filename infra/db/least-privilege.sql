-- Least-privilege database roles for a deployed Grass LMS.
-- §14.8. Run once per environment, as a superuser, before the first deploy.
--
-- Why two roles
-- -------------
-- The application connects all day with credentials that live in a container's
-- environment. Migrations run rarely, from a controlled place. Giving the
-- everyday connection the power to DROP TABLE means a leaked application
-- password is a leaked ability to destroy the institution's records — and
-- nothing the application does needs that power.
--
--   grras_migrate  owns the schema. Used only by `manage.py migrate`.
--   grras_app      reads and writes rows. Used by the web workers and the
--                  Celery worker. Cannot create, alter or drop anything.
--
-- Set DATABASE_URL to the grras_app role and MIGRATION_DATABASE_URL to
-- grras_migrate. Passwords come from the secret manager; the placeholders below
-- are deliberately invalid so this file cannot be run unedited.
--
-- Verify afterwards with:
--   \du
--   SELECT has_table_privilege('grras_app', 'accounts_user', 'DELETE');   -- t
--   SELECT has_schema_privilege('grras_app', 'public', 'CREATE');         -- f

\set ON_ERROR_STOP on

-- --------------------------------------------------------------------------
-- Roles
-- --------------------------------------------------------------------------

CREATE ROLE grras_migrate LOGIN PASSWORD 'SET-ME-FROM-THE-SECRET-MANAGER';
CREATE ROLE grras_app     LOGIN PASSWORD 'SET-ME-FROM-THE-SECRET-MANAGER';

-- Neither role may create databases or other roles, and neither is a superuser.
ALTER ROLE grras_migrate NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE grras_app     NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- --------------------------------------------------------------------------
-- Schema ownership
-- --------------------------------------------------------------------------

ALTER DATABASE grras_lms OWNER TO grras_migrate;
ALTER SCHEMA public OWNER TO grras_migrate;

-- Nobody gets anything by default. PostgreSQL 15 and later already revoke
-- CREATE on public from PUBLIC; this is explicit so the file is correct on 14.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE grras_lms FROM PUBLIC;

GRANT CONNECT ON DATABASE grras_lms TO grras_app, grras_migrate;
GRANT USAGE ON SCHEMA public TO grras_app;

-- --------------------------------------------------------------------------
-- What the application may do
-- --------------------------------------------------------------------------

-- Rows: yes. Schema: no. DELETE is included because the application really does
-- delete rows — a module, a bookmark, a draft — and withholding it would only
-- push those into soft deletes that no longer look like deletions.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO grras_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO grras_app;

-- Tables created by future migrations inherit the same grants, so a new model
-- does not silently arrive unreadable.
ALTER DEFAULT PRIVILEGES FOR ROLE grras_migrate IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO grras_app;
ALTER DEFAULT PRIVILEGES FOR ROLE grras_migrate IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO grras_app;

-- --------------------------------------------------------------------------
-- What it may not
-- --------------------------------------------------------------------------

-- No DDL. A SQL-injection hole that reaches this connection can read and write
-- rows — bad, and bounded — but cannot drop a table or add one.
REVOKE CREATE ON SCHEMA public FROM grras_app;

-- The audit log is append-only from the application's point of view. Editing
-- history is not something the application ever needs to do, and it is the
-- first thing an intruder would want to.
--
-- Revoked on this table by name, and NOT through ALTER DEFAULT PRIVILEGES.
-- Default privileges apply to every future table, so revoking UPDATE and DELETE
-- there would make the next model a migration adds read-only to the
-- application — which fails at runtime, long after the deploy that caused it,
-- with a permission error nobody expects. `audit_auditlog` exists already and
-- is never recreated, so naming it once is enough.
REVOKE UPDATE, DELETE ON TABLE audit_auditlog FROM grras_app;
