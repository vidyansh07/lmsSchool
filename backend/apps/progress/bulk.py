"""Everything the progress calculation needs, fetched for many enrolments at once.

Why this exists
---------------
:mod:`apps.progress.reports` is the one progress calculation, and it is written
for one student. That is the right shape for a student's own screen and the
wrong shape for a cohort report: called four hundred times it issues four
hundred times the queries, which is exactly the N+1 §14.9 asks for.

The fix is not a second copy of the arithmetic — that is how two parts of a
product come to disagree about whether somebody has finished. It is this: one
object that gathers the *inputs* for a set of enrolments, and section functions
that read from it. A report gathers once and shapes four hundred rows; a single
student's screen gathers for a list of one. The arithmetic is untouched and
lives in exactly one place either way.

Laziness
--------
Every group is a ``cached_property``, so asking for lesson progress does not
fetch exam attempts. A caller that wants one section still pays for one section,
which is why adding the bulk path did not make the single-student path slower.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any


class ProgressInputs:
    """The database reads behind a progress report, done once for a cohort.

    Constructed from a list of enrolments — already-loaded objects, not a
    queryset, because every group below needs their ids and their course and
    batch ids, and re-evaluating a queryset per group would defeat the point.
    """

    def __init__(self, enrollments: list) -> None:
        self.enrollments = list(enrollments)
        self.ids = [enrollment.pk for enrollment in self.enrollments]
        self.course_ids = {enrollment.course_id for enrollment in self.enrollments}
        self.batch_ids = {enrollment.batch_id for enrollment in self.enrollments}

    @classmethod
    def for_one(cls, enrollment) -> ProgressInputs:
        return cls([enrollment])

    # -- lessons ------------------------------------------------------------

    @cached_property
    def published_lessons(self) -> dict[Any, list]:
        """Published lessons of published modules, per course."""
        from apps.courses.models import Lesson, PublishStatus

        grouped: dict[Any, list] = {course_id: [] for course_id in self.course_ids}
        rows = Lesson.objects.filter(
            module__course_id__in=self.course_ids,
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        ).select_related("module")
        for lesson in rows:
            grouped.setdefault(lesson.module.course_id, []).append(lesson)
        return grouped

    @cached_property
    def published_modules(self) -> dict[Any, list]:
        from apps.courses.models import Module, PublishStatus

        grouped: dict[Any, list] = {course_id: [] for course_id in self.course_ids}
        rows = Module.objects.filter(
            course_id__in=self.course_ids, status=PublishStatus.PUBLISHED
        ).order_by("position", "created_at")
        for module in rows:
            grouped.setdefault(module.course_id, []).append(module)
        return grouped

    @cached_property
    def lesson_progress_rows(self) -> dict[Any, list]:
        """Every lesson-progress row for these enrolments, newest access first."""
        from apps.enrollments.models import LessonProgress

        grouped: dict[Any, list] = {key: [] for key in self.ids}
        rows = (
            LessonProgress.objects.filter(enrollment_id__in=self.ids)
            .select_related("lesson", "lesson__module")
            .order_by("-last_accessed_at")
        )
        for row in rows:
            grouped.setdefault(row.enrollment_id, []).append(row)
        return grouped

    # -- attendance ---------------------------------------------------------

    @cached_property
    def attendance(self) -> dict[Any, dict[str, Any]]:
        from apps.attendance.models import attendance_summaries

        return attendance_summaries(self.ids)

    # -- assignments --------------------------------------------------------

    @cached_property
    def assignments(self) -> dict[Any, list]:
        from apps.assignments.models import Assignment

        grouped: dict[Any, list] = {course_id: [] for course_id in self.course_ids}
        for assignment in Assignment.objects.student_visible().filter(
            course_id__in=self.course_ids
        ):
            grouped.setdefault(assignment.course_id, []).append(assignment)
        return grouped

    @cached_property
    def submissions(self) -> dict[Any, list]:
        from apps.assignments.models import AssignmentSubmission

        grouped: dict[Any, list] = {key: [] for key in self.ids}
        rows = AssignmentSubmission.objects.filter(enrollment_id__in=self.ids).select_related(
            "assignment"
        )
        for row in rows:
            grouped.setdefault(row.enrollment_id, []).append(row)
        return grouped

    # -- weekly tests -------------------------------------------------------

    @cached_property
    def assessments(self) -> dict[Any, list]:
        from apps.assessments.models import Assessment

        grouped: dict[Any, list] = {batch_id: [] for batch_id in self.batch_ids}
        for assessment in Assessment.objects.student_visible().filter(batch_id__in=self.batch_ids):
            grouped.setdefault(assessment.batch_id, []).append(assessment)
        return grouped

    @cached_property
    def results(self) -> dict[Any, list]:
        from apps.assessments.models import AssessmentResult

        grouped: dict[Any, list] = {key: [] for key in self.ids}
        rows = AssessmentResult.objects.filter(enrollment_id__in=self.ids).select_related(
            "assessment"
        )
        for row in rows:
            grouped.setdefault(row.enrollment_id, []).append(row)
        return grouped

    # -- projects -----------------------------------------------------------

    @cached_property
    def required_projects(self) -> dict[Any, list]:
        from apps.projects.models import Project

        grouped: dict[Any, list] = {course_id: [] for course_id in self.course_ids}
        for project in Project.objects.student_visible().filter(
            course_id__in=self.course_ids, is_required=True
        ):
            grouped.setdefault(project.course_id, []).append(project)
        return grouped

    @cached_property
    def student_projects(self) -> dict[Any, list]:
        from apps.projects.models import StudentProject

        grouped: dict[Any, list] = {key: [] for key in self.ids}
        for row in StudentProject.objects.filter(enrollment_id__in=self.ids):
            grouped.setdefault(row.enrollment_id, []).append(row)
        return grouped

    # -- final examination --------------------------------------------------

    @cached_property
    def exams(self) -> dict[Any, list]:
        from apps.exams.models import Exam

        grouped: dict[Any, list] = {batch_id: [] for batch_id in self.batch_ids}
        for exam in Exam.objects.student_visible().filter(batch_id__in=self.batch_ids):
            grouped.setdefault(exam.batch_id, []).append(exam)
        return grouped

    @cached_property
    def attempts(self) -> dict[Any, list]:
        from apps.exams.models import AttemptStatus, ExamAttempt

        grouped: dict[Any, list] = {key: [] for key in self.ids}
        rows = ExamAttempt.objects.filter(
            enrollment_id__in=self.ids, status=AttemptStatus.GRADED
        ).select_related("exam")
        for row in rows:
            grouped.setdefault(row.enrollment_id, []).append(row)
        return grouped

    # -- completion ---------------------------------------------------------

    @cached_property
    def completions(self) -> dict[Any, Any]:
        from apps.progress.models import CourseCompletion

        return {
            row.enrollment_id: row
            for row in CourseCompletion.objects.filter(enrollment_id__in=self.ids)
        }
