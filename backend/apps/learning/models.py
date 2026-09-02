"""Bookmarks and personal notes — §7.5 and §7.8.

Both are private to one student on one enrolment. That is the whole security
model, and it is why neither has an "access" module: a bookmark is only ever
readable by the person who made it, so there is no scoping question to answer —
the queryset is filtered by enrolment and there is no staff view at all.

Keyed on the enrolment rather than the user, like `LessonProgress`: a student
retaking a course on a later batch starts fresh, and their earlier notes stay
attached to the run they were made in.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class LessonBookmark(BaseModel):
    """A lesson a student marked to come back to."""

    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="bookmarks"
    )
    lesson = models.ForeignKey("courses.Lesson", on_delete=models.CASCADE, related_name="bookmarks")
    note = models.CharField(
        _("note"), max_length=200, blank=True, help_text=_("Why it was worth coming back to.")
    )

    class Meta:
        verbose_name = _("lesson bookmark")
        verbose_name_plural = _("lesson bookmarks")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "lesson"], name="bookmark_one_per_lesson"
            ),
        ]
        indexes = [
            models.Index(fields=["enrollment", "-created_at"], name="bookmark_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_id}/{self.lesson_id}"


class LessonNote(BaseModel):
    """A student's own notes on a lesson.

    One note per lesson, edited in place. A thread of timestamped notes sounds
    richer and is worse: people want the note they wrote, not an archive of
    every version of it.
    """

    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="notes"
    )
    lesson = models.ForeignKey("courses.Lesson", on_delete=models.CASCADE, related_name="notes")
    body = models.TextField(_("note"))

    class Meta:
        verbose_name = _("lesson note")
        verbose_name_plural = _("lesson notes")
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "lesson"], name="note_one_per_lesson"),
        ]
        indexes = [
            models.Index(fields=["enrollment", "-updated_at"], name="note_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_id}/{self.lesson_id}"
