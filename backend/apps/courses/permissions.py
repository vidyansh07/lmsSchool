"""Course permission classes.

Thin wrappers over :mod:`apps.courses.access`. They exist so views declare
intent (``CanManageCourse``) instead of repeating lookups, and so the object
being authorised is always the one fetched from the database — never an
identifier the client supplied.
"""

from __future__ import annotations

from apps.common.permissions import IsActiveUser

from . import access


class CanViewCourse(IsActiveUser):
    """Object-level: may the caller know this course exists?"""

    message = "This course is not available."

    def has_object_permission(self, request, view, obj) -> bool:
        return access.can_view_course(request.user, obj)


class CanManageCourse(IsActiveUser):
    """Object-level: may the caller edit this course and its content?"""

    message = "You do not have permission to edit this course."

    def has_object_permission(self, request, view, obj) -> bool:
        return access.can_manage_course(request.user, obj)


class CanPublishCourse(IsActiveUser):
    """Object-level: may the caller change this course's status?"""

    message = "Only a course owner or an administrator can change the status."

    def has_object_permission(self, request, view, obj) -> bool:
        return access.can_publish_course(request.user, obj)
