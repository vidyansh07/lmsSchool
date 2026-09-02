"""§14.8 — constraints, indexes, migrations and transactions.

These are the guarantees a code review does not catch. A missing index is
invisible until the table is large; a redundant one is invisible always, and
quietly taxes every write. A missing constraint looks fine until two requests
arrive at once.

Run against the real schema of the test database, so what is asserted is what
PostgreSQL actually has — not what the models say it should have.
"""

from __future__ import annotations

import pytest
from django.db import connection


def _schema_rows(sql: str, params: tuple = ()) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_index_duplicates_another():
    """Two indexes on the same columns cost two writes and serve one read.

    Django creates an index for every foreign key automatically, so declaring
    ``models.Index(fields=["enrollment"])`` on top of one is pure overhead —
    seven of those had accumulated by the end of Phase 8. Django's own
    ``varchar_pattern_ops`` companions (``…_like``) are excluded: those support
    a different operator class and are not duplicates.
    """
    rows = _schema_rows(
        """
        SELECT t.relname, array_agg(i.relname ORDER BY i.relname)
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND NOT x.indisprimary
          AND NOT x.indisunique
          AND i.relname NOT LIKE '%%\\_like'
        GROUP BY t.relname, x.indkey, pg_get_expr(x.indpred, x.indrelid)
        HAVING count(*) > 1
        """
    )
    assert not rows, "redundant indexes: " + "; ".join(f"{t}: {names}" for t, names in rows)


#: The columns every cohort-sized query filters or groups on. Each one is a
#: sequential scan over a table that grows with the institution if it is not
#: indexed, and each is exercised by `tests/test_performance.py`.
HOT_COLUMNS = [
    ("attendance_attendancerecord", "enrollment_id"),
    ("attendance_attendancerecord", "session_id"),
    ("enrollments_lessonprogress", "enrollment_id"),
    ("enrollments_enrollment", "batch_id"),
    ("enrollments_enrollment", "student_id"),
    ("assessments_assessmentresult", "enrollment_id"),
    ("assignments_assignmentsubmission", "enrollment_id"),
    ("class_sessions_classsession", "batch_id"),
    ("audit_auditlog", "actor_id"),
    ("notifications_notification", "recipient_id"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("table", "column"), HOT_COLUMNS, ids=[f"{t}.{c}" for t, c in HOT_COLUMNS])
def test_every_hot_column_is_indexed(table, column):
    rows = _schema_rows(
        """
        SELECT i.relname
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.indkey[0]
        WHERE t.relname = %s AND a.attname = %s
        """,
        (table, column),
    )
    assert rows, f"{table}.{column} leads no index"


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

#: Rules that must be the database's, not the application's. Each one is a race
#: an application check loses: two requests both see "no row yet" and both
#: write. Named individually so removing one fails here rather than in
#: production at enrolment time.
REQUIRED_CONSTRAINTS = [
    "attendance_one_per_session_enrollment",
    "result_one_per_student_per_assessment",
    "progress_one_per_enrollment_lesson",
    "session_unique_per_batch_slot",
    "session_end_after_start",
    "result_marks_not_negative",
    "result_absent_has_no_marks",
]


@pytest.mark.django_db
@pytest.mark.parametrize("name", REQUIRED_CONSTRAINTS)
def test_the_database_enforces_the_rule_itself(name):
    rows = _schema_rows(
        "SELECT conname FROM pg_constraint WHERE conname = %s "
        "UNION SELECT indexrelid::regclass::text FROM pg_index "
        "WHERE indexrelid::regclass::text = %s",
        (name, name),
    )
    assert rows, f"{name} is not enforced by the database"


@pytest.mark.django_db
def test_every_foreign_key_is_declared_to_the_database():
    """An orphan row is a bug the application cannot fix after the fact."""
    rows = _schema_rows(
        """
        SELECT c.relname, a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND a.attname LIKE '%%\\_id'
          AND a.attname <> 'id'
          AND NOT EXISTS (
              SELECT 1 FROM pg_constraint k
              WHERE k.conrelid = c.oid AND k.contype = 'f' AND a.attnum = ANY (k.conkey)
          )
        """
    )
    # A handful of `*_id` columns are deliberately not foreign keys: human
    # identifiers such as `student_id` and `trainer_id`, and the audit log's
    # `resource_id`, which points at whatever the action touched and must
    # survive that record being deleted.
    allowed = {
        ("students_studentprofile", "student_id"),
        ("trainers_trainerprofile", "trainer_id"),
        # These point at "whatever the action touched", across several tables,
        # and must survive that record being deleted — a foreign key would take
        # the history with it.
        ("audit_auditlog", "resource_id"),
        ("audit_auditlog", "request_id"),
        ("notifications_notification", "resource_id"),
        ("django_admin_log", "object_id"),
    }
    unexpected = {(table, column) for table, column in rows} - allowed
    assert not unexpected, f"columns that look like keys but are not: {sorted(unexpected)}"


# ---------------------------------------------------------------------------
# Transactions and migrations
# ---------------------------------------------------------------------------


def test_every_request_runs_in_a_transaction(settings):
    """`ATOMIC_REQUESTS` is what makes a half-applied write impossible."""
    assert settings.DATABASES["default"]["ATOMIC_REQUESTS"] is True


def test_the_application_never_connects_as_a_superuser(settings):
    """Documented in `docs/security.md`; checked here so it cannot be forgotten.

    Not asserted against the live role — a developer's local database is
    reasonably owned by the developer. What is asserted is that nothing in the
    configuration *names* a superuser, which is how the wrong URL gets copied
    into a deployment.
    """
    url = settings.DATABASES["default"]
    assert url["USER"] not in ("postgres", "root", "rds_superuser")
