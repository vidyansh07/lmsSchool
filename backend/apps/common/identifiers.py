"""Human-facing sequential identifiers.

Records are keyed internally by UUID so nothing leaks from a URL. People,
however, need something they can read out over a phone call — a student ID on
an admission form, a trainer ID on a timetable. This module produces those.

Allocation uses a PostgreSQL sequence rather than ``MAX(id) + 1``: sequences are
atomic and non-blocking, so two concurrent admissions cannot be handed the same
number. A gap after a rolled-back transaction is expected and harmless.
"""

from __future__ import annotations

from django.db import connection

STUDENT_ID_SEQUENCE = "student_public_id_seq"
TRAINER_ID_SEQUENCE = "trainer_public_id_seq"
COURSE_CODE_SEQUENCE = "course_public_code_seq"
BATCH_CODE_SEQUENCE = "batch_public_code_seq"
ENROLMENT_CODE_SEQUENCE = "enrolment_public_code_seq"

STUDENT_ID_PREFIX = "GRS-S"
TRAINER_ID_PREFIX = "GRS-T"
COURSE_CODE_PREFIX = "GRS-C"
BATCH_CODE_PREFIX = "GRS-B"
ENROLMENT_CODE_PREFIX = "GRS-E"

_NUMBER_WIDTH = 5


def _next_value(sequence_name: str) -> int:
    with connection.cursor() as cursor:
        # The sequence name is a module constant, never user input.
        cursor.execute(f"SELECT nextval('{sequence_name}')")
        return cursor.fetchone()[0]


def next_student_id() -> str:
    """e.g. ``GRS-S-00042``."""
    return f"{STUDENT_ID_PREFIX}-{_next_value(STUDENT_ID_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_trainer_id() -> str:
    """e.g. ``GRS-T-00007``."""
    return f"{TRAINER_ID_PREFIX}-{_next_value(TRAINER_ID_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_course_code() -> str:
    """e.g. ``GRS-C-00013``."""
    return f"{COURSE_CODE_PREFIX}-{_next_value(COURSE_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_batch_code() -> str:
    """e.g. ``GRS-B-00021``."""
    return f"{BATCH_CODE_PREFIX}-{_next_value(BATCH_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_enrolment_code() -> str:
    """e.g. ``GRS-E-00307``."""
    return f"{ENROLMENT_CODE_PREFIX}-{_next_value(ENROLMENT_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"
