"""What a built report can be built from.

Each dataset names three things and nothing else: where its rows come from
(a `source` the shared scoped resolver already understands), what it is
willing to show, and what it is willing to be asked. A column or a filter
that is not declared here does not exist as far as the builder is concerned,
however it is spelled in a request.

The filter lists deliberately reuse the `FilterField`s the list screens
already declare, rather than a second set written out beside them. One list
per screen that drifts from the other is how "the export does not match what
I was looking at" starts, and these are exactly the questions those screens
have already decided are safe to answer.

Six to begin with -- students, enrolments, fee payments, batches, trainers
and class reports -- because those are the six an operations question
actually lands on. Adding a seventh is a dataclass, not a feature.
"""

from __future__ import annotations

from apps.common.filtering import FilterField

from .builder import Column, Dataset, Measure, person_name

#: Datasets reach columns through ORM paths that never leave the server. A
#: caller asks for `course`; the database is asked for `batch__course__title`.

STUDENTS = Dataset(
    key="students",
    label="Students",
    description="Everybody on the roll, with where they came from and what they owe.",
    source="students",
    columns=(
        Column("student_id", "Student ID", "student_id"),
        Column("name", "Name", "person_name", person_name("user")),
        Column("email", "Email", "user__email"),
        Column("phone", "Phone", "user__phone"),
        Column("city", "City", "city"),
        Column("state", "State", "state"),
        Column("institution", "College or employer", "institution"),
        Column("fee_status", "Fee status", "fee_status"),
        Column("centre", "Centre", "branch__name"),
        Column("registered_on", "Registered on", "created_at"),
    ),
    filters=(
        FilterField("fee_status", kind="choice", label="Fee status"),
        FilterField("city", kind="text", label="City"),
        FilterField("state", kind="text", label="State"),
        FilterField("institution", kind="text", label="College or employer"),
        FilterField("student_id", kind="text", label="Student ID"),
        FilterField("branch", kind="uuid", path="branch_id", label="Centre"),
        FilterField("created_at", kind="date", label="Registered on"),
        FilterField("is_active", kind="boolean", path="user__is_active", label="Account active"),
        FilterField("open_to_placement", kind="boolean", label="Open to placement"),
    ),
    measures=(Measure("count", "Students", "count"),),
)

ENROLMENTS = Dataset(
    key="enrolments",
    label="Enrolments",
    description="Who is on which batch, and what state that enrolment is in.",
    source="enrollments",
    columns=(
        Column("code", "Enrolment", "code"),
        Column("student", "Student", "student_name", person_name("student__user")),
        Column("student_id", "Student ID", "student__student_id"),
        Column("course", "Course", "batch__course__title"),
        Column("batch", "Batch", "batch__name"),
        Column("trainer", "Trainer", "trainer_name", person_name("batch__trainer__user")),
        Column("status", "Status", "status"),
        Column("centre", "Centre", "batch__branch__name"),
        Column("enrolled_on", "Enrolled on", "created_at"),
    ),
    filters=(
        FilterField("status", kind="choice", label="Status"),
        FilterField("code", kind="text", label="Enrolment code"),
        FilterField("course", kind="uuid", path="batch__course_id", label="Course"),
        FilterField("batch", kind="uuid", path="batch_id", label="Batch"),
        FilterField("centre", kind="uuid", path="batch__branch_id", label="Centre"),
        FilterField("created_at", kind="date", label="Enrolled on"),
    ),
    measures=(Measure("count", "Enrolments", "count"),),
)

FEE_PAYMENTS = Dataset(
    key="fee_payments",
    label="Fee payments",
    description="Every receipt: what was taken, from whom, by whom, and how.",
    source="fee_payments",
    columns=(
        Column("receipt", "Receipt", "receipt_number"),
        Column(
            "student",
            "Student",
            "student_name",
            person_name("plan__enrollment__student__user"),
        ),
        Column("course", "Course", "plan__enrollment__batch__course__title"),
        Column("amount", "Amount", "amount"),
        Column("method", "Method", "method"),
        Column("paid_on", "Paid on", "paid_on"),
        Column("taken_by", "Taken by", "taken_by_name", person_name("recorded_by")),
        Column("centre", "Centre", "plan__enrollment__batch__branch__name"),
    ),
    filters=(
        FilterField("method", kind="choice", label="Method"),
        FilterField("paid_on", kind="date", label="Paid on"),
        FilterField("amount", kind="number", label="Amount"),
        FilterField("taken_by", kind="uuid", path="recorded_by_id", label="Taken by"),
        FilterField(
            "course", kind="uuid", path="plan__enrollment__batch__course_id", label="Course"
        ),
        FilterField(
            "centre", kind="uuid", path="plan__enrollment__batch__branch_id", label="Centre"
        ),
    ),
    measures=(
        Measure("count", "Receipts", "count"),
        Measure("total", "Collected", "sum", "amount"),
    ),
)

BATCHES = Dataset(
    key="batches",
    label="Batches",
    description="Classes, when they run and who teaches them.",
    source="batches",
    columns=(
        Column("code", "Batch code", "code"),
        Column("name", "Batch", "name"),
        Column("course", "Course", "course__title"),
        Column("trainer", "Trainer", "trainer_name", person_name("trainer__user")),
        Column("status", "Status", "status"),
        Column("starts_on", "Starts on", "start_date"),
        Column("ends_on", "Ends on", "end_date"),
        Column("centre", "Centre", "branch__name"),
    ),
    filters=(
        FilterField("status", kind="choice", label="Status"),
        FilterField("course", kind="uuid", path="course_id", label="Course"),
        FilterField("trainer", kind="uuid", path="trainer_id", label="Trainer"),
        FilterField("start_date", kind="date", label="Starts on"),
        FilterField("centre", kind="uuid", path="branch_id", label="Centre"),
    ),
    measures=(Measure("count", "Batches", "count"),),
)

TRAINERS = Dataset(
    key="trainers",
    label="Trainers",
    description="Who teaches here, and what they are set up to teach.",
    source="trainers",
    columns=(
        Column("trainer_id", "Trainer ID", "trainer_id"),
        Column("name", "Name", "person_name", person_name("user")),
        Column("email", "Email", "user__email"),
        Column("title", "Title", "professional_title"),
        Column("experience", "Years of experience", "years_of_experience"),
        Column("centre", "Centre", "branch__name"),
    ),
    filters=(
        FilterField("trainer_id", kind="text", label="Trainer ID"),
        FilterField("centre", kind="uuid", path="branch_id", label="Centre"),
        FilterField("is_active", kind="boolean", path="user__is_active", label="Account active"),
        FilterField("years_of_experience", kind="number", label="Years of experience"),
    ),
    measures=(Measure("count", "Trainers", "count"),),
)

CLASS_REPORTS = Dataset(
    key="class_reports",
    label="Class reports",
    description="What was taught, by whom, and whether the report arrived.",
    source="dsrs",
    columns=(
        Column("batch", "Batch", "batch__name"),
        Column("course", "Course", "batch__course__title"),
        Column("trainer", "Trainer", "trainer_name", person_name("trainer__user")),
        Column("status", "Status", "status"),
        Column("written_on", "Written on", "created_at"),
    ),
    filters=(
        FilterField("status", kind="choice", label="Status"),
        FilterField("trainer", kind="uuid", path="trainer_id", label="Trainer"),
        FilterField("batch", kind="uuid", path="batch_id", label="Batch"),
        FilterField("created_at", kind="date", label="Written on"),
    ),
    measures=(Measure("count", "Reports", "count"),),
)

DATASETS: dict[str, Dataset] = {
    dataset.key: dataset
    for dataset in (STUDENTS, ENROLMENTS, FEE_PAYMENTS, BATCHES, TRAINERS, CLASS_REPORTS)
}


def catalogue() -> list[dict]:
    """Every dataset a report can be built from, as a browser needs it."""
    return [dataset.describe() for dataset in DATASETS.values()]
