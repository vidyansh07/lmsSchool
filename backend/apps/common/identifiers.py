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
ASSIGNMENT_CODE_SEQUENCE = "assignment_public_code_seq"
ASSESSMENT_CODE_SEQUENCE = "assessment_public_code_seq"
PROJECT_CODE_SEQUENCE = "project_public_code_seq"
EXAM_CODE_SEQUENCE = "exam_public_code_seq"
CERTIFICATE_NUMBER_SEQUENCE = "certificate_number_seq"
RECEIPT_NUMBER_SEQUENCE = "fee_receipt_number_seq"

STUDENT_ID_PREFIX = "GRS-S"
TRAINER_ID_PREFIX = "GRS-T"
COURSE_CODE_PREFIX = "GRS-C"
BATCH_CODE_PREFIX = "GRS-B"
ENROLMENT_CODE_PREFIX = "GRS-E"
ASSIGNMENT_CODE_PREFIX = "GRS-A"
ASSESSMENT_CODE_PREFIX = "GRS-X"
PROJECT_CODE_PREFIX = "GRS-P"
EXAM_CODE_PREFIX = "GRS-F"
CERTIFICATE_NUMBER_PREFIX = "GRS-CERT"

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


def next_receipt_number() -> str:
    """e.g. ``GRS-R-00042`` — printed on the receipt a student is handed."""
    return f"GRS-R-{_next_value(RECEIPT_NUMBER_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_enrolment_code() -> str:
    """e.g. ``GRS-E-00307``."""
    return f"{ENROLMENT_CODE_PREFIX}-{_next_value(ENROLMENT_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_assignment_code() -> str:
    """e.g. ``GRS-A-00114``."""
    return f"{ASSIGNMENT_CODE_PREFIX}-{_next_value(ASSIGNMENT_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_assessment_code() -> str:
    """e.g. ``GRS-X-00058``."""
    return f"{ASSESSMENT_CODE_PREFIX}-{_next_value(ASSESSMENT_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_project_code() -> str:
    """e.g. ``GRS-P-00019``."""
    return f"{PROJECT_CODE_PREFIX}-{_next_value(PROJECT_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_exam_code() -> str:
    """e.g. ``GRS-F-00004``."""
    return f"{EXAM_CODE_PREFIX}-{_next_value(EXAM_CODE_SEQUENCE):0{_NUMBER_WIDTH}d}"


def next_certificate_number() -> str:
    """e.g. ``GRS-CERT-2026-00031``.

    The year makes a certificate legible at a glance; the sequence keeps it
    unique. Neither is what the public verification endpoint takes — see
    ``Certificate.verification_code``.
    """
    from django.utils import timezone

    number = _next_value(CERTIFICATE_NUMBER_SEQUENCE)
    return f"{CERTIFICATE_NUMBER_PREFIX}-{timezone.localdate().year}-{number:0{_NUMBER_WIDTH}d}"
