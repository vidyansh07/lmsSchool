"""Course domain services.

Business rules live here, not in serializers or views, so the same rule holds
for the API, the Django admin, the seeder and any future task.

Two rules in this module carry most of the weight:

* **Status transitions are a table, not scattered ifs.** An unreachable
  transition is rejected by ``TRANSITIONS`` rather than by whichever view
  happened to remember to check.
* **Reordering is one transaction with a deferred constraint.** Positions stay
  unique and dense; a half-applied reorder cannot be observed.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_course_code
from apps.common.uploads import normalise_course_thumbnail, validate_resource_upload

from .models import (
    Category,
    Course,
    CourseAssignment,
    Lesson,
    LessonContentType,
    LessonResource,
    Module,
    PublishStatus,
    ResourceKind,
    VideoAsset,
)

# ---------------------------------------------------------------------------
# Publishing workflow
# ---------------------------------------------------------------------------

#: Allowed status transitions. Anything absent is refused.
#:
#: DRAFT → PUBLISHED is permitted directly: requiring every course to pass
#: through review would be ceremony for a single-admin team. The review step
#: exists for authors who *cannot* publish — an assigned editor submits, and an
#: owner or administrator approves. Making review mandatory later is a one-line
#: change to this table plus a settings flag.
TRANSITIONS: dict[str, frozenset[str]] = {
    PublishStatus.DRAFT: frozenset({PublishStatus.IN_REVIEW, PublishStatus.PUBLISHED}),
    PublishStatus.IN_REVIEW: frozenset({PublishStatus.DRAFT, PublishStatus.PUBLISHED}),
    PublishStatus.PUBLISHED: frozenset({PublishStatus.ARCHIVED, PublishStatus.DRAFT}),
    PublishStatus.ARCHIVED: frozenset({PublishStatus.DRAFT}),
}

#: Transitions an author without publish rights may perform on their own course.
SUBMIT_ONLY = frozenset({PublishStatus.IN_REVIEW})


class TransitionError(ApplicationError):
    default_detail = "That status change is not allowed."
    default_code = "invalid_transition"


def _assert_transition(current: str, target: str) -> None:
    if current == target:
        raise TransitionError(f"The course is already {current}.")
    if target not in TRANSITIONS.get(current, frozenset()):
        allowed = ", ".join(sorted(TRANSITIONS.get(current, []))) or "nothing"
        raise TransitionError(
            f"A {current} course cannot move to {target}. Allowed from {current}: {allowed}."
        )


def publishing_blockers(course: Course) -> list[str]:
    """Why this course is not ready to publish. Empty means it is.

    Checked at publish time rather than on every save: a draft is *allowed* to
    be incomplete, that is what draft means.
    """
    problems: list[str] = []
    if not course.title.strip():
        problems.append("The course needs a title.")
    if not course.short_description.strip() and not course.description.strip():
        problems.append("The course needs a description.")

    published_modules = course.modules.filter(status=PublishStatus.PUBLISHED)
    # These gate the public catalogue only. A batch can run a course in any
    # state but archived (see ``Batch.clean``), so nothing about teaching
    # waits on them.
    if not published_modules.exists():
        problems.append(
            "To appear in the catalogue, the course needs at least one published module."
        )
    elif not Lesson.objects.filter(
        module__in=published_modules, status=PublishStatus.PUBLISHED
    ).exists():
        problems.append(
            "To appear in the catalogue, a published module needs at least one published lesson."
        )
    return problems


@transaction.atomic
def set_course_status(
    *, course: Course, target: str, actor: User, may_publish: bool, note: str = ""
) -> Course:
    """Move a course through the publishing workflow.

    ``may_publish`` comes from the access layer, not from the request. An author
    without it may only submit for review.
    """
    _assert_transition(course.status, target)

    if not may_publish and target not in SUBMIT_ONLY:
        raise ApplicationError(
            {
                "status": [
                    "You may submit this course for review, but only an owner or "
                    "administrator can publish or archive it."
                ]
            }
        )

    if target == PublishStatus.PUBLISHED:
        problems = publishing_blockers(course)
        if problems:
            raise ApplicationError({"status": problems})

    previous = course.status
    course.status = target
    course.updated_by = actor
    fields = ["status", "updated_by", "updated_at"]

    if target == PublishStatus.PUBLISHED and course.published_at is None:
        course.published_at = timezone.now()
        fields.append("published_at")

    course.save(update_fields=fields)

    record(
        action=AuditAction.COURSE_STATUS_CHANGED,
        actor=actor,
        resource_type="course",
        resource_id=course.pk,
        context={"code": course.code, "from": previous, "to": target, "note": note},
    )
    return course


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def _unique_slug(
    model, base: str, *, field: str = "slug", scope: dict[str, Any] | None = None
) -> str:
    """Derive a unique slug, appending a counter only when it collides."""
    candidate = slugify(base)[:150] or "item"
    queryset = model.objects.filter(**(scope or {}))
    suffix = 2
    slug = candidate
    while queryset.filter(**{field: slug}).exists():
        slug = f"{candidate[: 150 - len(str(suffix)) - 1]}-{suffix}"
        suffix += 1
    return slug


@transaction.atomic
def create_category(*, actor: User, name: str, slug: str = "", **fields: Any) -> Category:
    category = Category(name=name, slug=slug or _unique_slug(Category, name), **fields)
    category.full_clean()
    category.save()
    record(
        action=AuditAction.CATEGORY_CREATED,
        actor=actor,
        resource_type="category",
        resource_id=category.pk,
        context={"name": category.name, "slug": category.slug},
    )
    return category


@transaction.atomic
def update_category(*, category: Category, actor: User, **fields: Any) -> Category:
    changed = _apply(category, fields)
    if not changed:
        return category
    category.full_clean()
    category.save(update_fields=[*changed, "updated_at"])
    record(
        action=AuditAction.CATEGORY_UPDATED,
        actor=actor,
        resource_type="category",
        resource_id=category.pk,
        context={"changed_fields": sorted(changed)},
    )
    return category


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


def _apply(instance, fields: dict[str, Any]) -> list[str]:
    """Assign only the values that actually differ. Returns changed names."""
    changed: list[str] = []
    for name, value in fields.items():
        if getattr(instance, name) != value:
            setattr(instance, name, value)
            changed.append(name)
    return changed


@transaction.atomic
def create_course(*, actor: User, title: str, slug: str = "", **fields: Any) -> Course:
    course = Course(
        title=title,
        slug=slug or _unique_slug(Course, title),
        code=next_course_code(),
        created_by=actor,
        updated_by=actor,
        **fields,
    )
    course.full_clean(exclude=["code"])
    course.save()

    record(
        action=AuditAction.COURSE_CREATED,
        actor=actor,
        resource_type="course",
        resource_id=course.pk,
        context={"code": course.code, "title": course.title, "slug": course.slug},
    )
    return course


@transaction.atomic
def update_course(*, course: Course, actor: User, **fields: Any) -> Course:
    """Edit a course, recording what changed.

    Edits to a *published* course are recorded with their before values. §9 asks
    that published content not change silently; this is what makes an accidental
    edit visible after the fact rather than invisible forever.
    """
    was_published = course.status == PublishStatus.PUBLISHED
    before = {name: getattr(course, name) for name in fields}
    changed = _apply(course, fields)
    if not changed:
        return course

    course.updated_by = actor
    course.full_clean(exclude=["code"])
    course.save(update_fields=[*changed, "updated_by", "updated_at"])

    context: dict[str, Any] = {"code": course.code, "changed_fields": sorted(changed)}
    if was_published:
        context["published_course_edited"] = True
        context["previous_values"] = {
            name: str(before[name])[:200] for name in changed if name in before
        }

    record(
        action=AuditAction.COURSE_UPDATED,
        actor=actor,
        resource_type="course",
        resource_id=course.pk,
        context=context,
    )
    return course


@transaction.atomic
def set_course_thumbnail(*, course: Course, actor: User, uploaded_file) -> Course:
    normalised = normalise_course_thumbnail(uploaded_file)
    if course.thumbnail:
        course.thumbnail.delete(save=False)
    course.thumbnail.save(normalised.name, normalised, save=False)
    course.updated_by = actor
    course.save(update_fields=["thumbnail", "updated_by", "updated_at"])
    record(
        action=AuditAction.COURSE_UPDATED,
        actor=actor,
        resource_type="course",
        resource_id=course.pk,
        context={"code": course.code, "changed_fields": ["thumbnail"]},
    )
    return course


@transaction.atomic
def assign_author(*, course: Course, user: User, role: str, actor: User) -> CourseAssignment:
    """Grant or update someone's authoring rights on one course."""
    from apps.accounts.roles import UserRole

    if user.role not in (UserRole.TRAINER, UserRole.ADMIN):
        raise ApplicationError(
            {"user": ["Only trainers and administrators can be assigned as course authors."]}
        )

    assignment, created = CourseAssignment.objects.update_or_create(
        course=course, user=user, defaults={"role": role, "assigned_by": actor}
    )
    record(
        action=AuditAction.COURSE_AUTHOR_ASSIGNED,
        actor=actor,
        resource_type="course",
        resource_id=course.pk,
        context={
            "code": course.code,
            "assigned_user": str(user.pk),
            "assigned_email": user.email,
            "role": role,
            "created": created,
        },
    )
    return assignment


@transaction.atomic
def remove_author(*, course: Course, user: User, actor: User) -> None:
    deleted, _ = CourseAssignment.objects.filter(course=course, user=user).delete()
    if deleted:
        record(
            action=AuditAction.COURSE_AUTHOR_REMOVED,
            actor=actor,
            resource_type="course",
            resource_id=course.pk,
            context={"code": course.code, "removed_user": str(user.pk), "email": user.email},
        )


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def _next_position(queryset) -> int:
    last = queryset.order_by("-position").values_list("position", flat=True).first()
    return 0 if last is None else last + 1


@transaction.atomic
def reorder(*, parent, related_name: str, ordered_ids: list[str], actor: User, resource_type: str):
    """Apply an explicit order to a parent's children.

    The whole set must be supplied — a partial list would leave gaps and make
    "what is third?" ambiguous. Positions are rewritten densely from zero inside
    one transaction; the deferred unique constraint permits the intermediate
    states that any reshuffle necessarily passes through.
    """
    children = list(getattr(parent, related_name).all())
    existing_ids = {str(child.pk) for child in children}
    supplied_ids = [str(value) for value in ordered_ids]

    if set(supplied_ids) != existing_ids:
        raise ApplicationError(
            {
                "ordered_ids": [
                    "Send every child exactly once. Received "
                    f"{len(supplied_ids)}, expected {len(existing_ids)}."
                ]
            }
        )
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ApplicationError({"ordered_ids": ["Duplicate identifiers in the ordering."]})

    by_id = {str(child.pk): child for child in children}
    for position, child_id in enumerate(supplied_ids):
        by_id[child_id].position = position

    if children:
        type(children[0]).objects.bulk_update(children, ["position"])

    record(
        action=AuditAction.COURSE_CONTENT_REORDERED,
        actor=actor,
        resource_type=resource_type,
        resource_id=parent.pk,
        context={"order": supplied_ids},
    )
    return children


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


def _touch_course(course: Course, actor: User) -> None:
    """Mark that a published course's content moved under it."""
    course.content_updated_at = timezone.now()
    course.updated_by = actor
    course.save(update_fields=["content_updated_at", "updated_by", "updated_at"])


@transaction.atomic
def create_module(*, course: Course, actor: User, **fields: Any) -> Module:
    module = Module(course=course, position=_next_position(course.modules), **fields)
    module.full_clean()
    module.save()
    _touch_course(course, actor)
    record(
        action=AuditAction.MODULE_CREATED,
        actor=actor,
        resource_type="module",
        resource_id=module.pk,
        context={"course_code": course.code, "title": module.title},
    )
    return module


@transaction.atomic
def update_module(*, module: Module, actor: User, **fields: Any) -> Module:
    changed = _apply(module, fields)
    if not changed:
        return module
    module.full_clean()
    module.save(update_fields=[*changed, "updated_at"])
    _touch_course(module.course, actor)
    record(
        action=AuditAction.MODULE_UPDATED,
        actor=actor,
        resource_type="module",
        resource_id=module.pk,
        context={"course_code": module.course.code, "changed_fields": sorted(changed)},
    )
    return module


@transaction.atomic
def delete_module(*, module: Module, actor: User) -> None:
    course, title, module_id = module.course, module.title, module.pk
    module.delete()
    _touch_course(course, actor)
    record(
        action=AuditAction.MODULE_DELETED,
        actor=actor,
        resource_type="module",
        resource_id=module_id,
        context={"course_code": course.code, "title": title},
    )


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------


def _validate_lesson_content(lesson: Lesson) -> None:
    """A DOCUMENT lesson needs an attached file; the rest are checked by ``clean``."""
    if lesson.content_type == LessonContentType.DOCUMENT and lesson.pk:
        has_file = lesson.resources.filter(kind=ResourceKind.FILE).exists()
        if not has_file and lesson.status == PublishStatus.PUBLISHED:
            raise ApplicationError(
                {"content_type": ["A document lesson needs an attached file before publishing."]}
            )


@transaction.atomic
def create_lesson(
    *, module: Module, actor: User, video: dict[str, Any] | None = None, **fields: Any
) -> Lesson:
    video_asset = create_video_asset(**video) if video else None
    lesson = Lesson(
        module=module,
        position=_next_position(module.lessons),
        slug=fields.pop("slug", "")
        or _unique_slug(Lesson, fields.get("title", "lesson"), scope={"module": module}),
        video=video_asset,
        **fields,
    )
    lesson.full_clean()
    lesson.save()
    _touch_course(module.course, actor)
    record(
        action=AuditAction.LESSON_CREATED,
        actor=actor,
        resource_type="lesson",
        resource_id=lesson.pk,
        context={
            "course_code": module.course.code,
            "module": str(module.pk),
            "title": lesson.title,
            "content_type": lesson.content_type,
        },
    )
    return lesson


@transaction.atomic
def update_lesson(
    *, lesson: Lesson, actor: User, video: dict[str, Any] | None = None, **fields: Any
) -> Lesson:
    if video is not None:
        if lesson.video:
            update_video_asset(asset=lesson.video, **video)
        else:
            lesson.video = create_video_asset(**video)
            fields["video"] = lesson.video

    changed = _apply(lesson, fields)
    if not changed and video is None:
        return lesson

    lesson.full_clean()
    _validate_lesson_content(lesson)
    if changed:
        lesson.save(update_fields=[*changed, "updated_at"])
    _touch_course(lesson.module.course, actor)
    record(
        action=AuditAction.LESSON_UPDATED,
        actor=actor,
        resource_type="lesson",
        resource_id=lesson.pk,
        context={
            "course_code": lesson.module.course.code,
            "changed_fields": sorted(changed) + (["video"] if video is not None else []),
        },
    )
    return lesson


@transaction.atomic
def delete_lesson(*, lesson: Lesson, actor: User) -> None:
    course, title, lesson_id = lesson.module.course, lesson.title, lesson.pk
    lesson.delete()
    _touch_course(course, actor)
    record(
        action=AuditAction.LESSON_DELETED,
        actor=actor,
        resource_type="lesson",
        resource_id=lesson_id,
        context={"course_code": course.code, "title": title},
    )


# ---------------------------------------------------------------------------
# Video assets
# ---------------------------------------------------------------------------


def create_video_asset(**fields: Any) -> VideoAsset:
    asset = VideoAsset(**fields)
    asset.full_clean()
    asset.save()
    return asset


def update_video_asset(*, asset: VideoAsset, **fields: Any) -> VideoAsset:
    changed = _apply(asset, fields)
    if changed:
        asset.full_clean()
        asset.save(update_fields=[*changed, "updated_at"])
    return asset


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@transaction.atomic
def create_file_resource(
    *, lesson: Lesson, actor: User, uploaded_file, **fields: Any
) -> LessonResource:
    """Attach an uploaded file to a lesson.

    Validation lives in ``apps.common.uploads``: extension allowlist paired with
    a magic-byte check, and a server-generated storage name. The uploader's
    filename is kept for display only and never used as a path.
    """
    extension, content_type = validate_resource_upload(uploaded_file)
    original_name = (getattr(uploaded_file, "name", "") or "")[:255]

    resource = LessonResource(
        lesson=lesson,
        kind=ResourceKind.FILE,
        position=_next_position(lesson.resources),
        original_filename=original_name,
        content_type=content_type,
        size_bytes=getattr(uploaded_file, "size", None),
        uploaded_by=actor,
        **fields,
    )
    resource.file.save(f"upload{extension}", uploaded_file, save=False)
    resource.full_clean(exclude=["file"])
    resource.save()
    _touch_course(lesson.module.course, actor)

    record(
        action=AuditAction.RESOURCE_UPLOADED,
        actor=actor,
        resource_type="lesson_resource",
        resource_id=resource.pk,
        context={
            "course_code": lesson.module.course.code,
            "lesson": str(lesson.pk),
            "content_type": content_type,
            "size_bytes": resource.size_bytes,
            # The uploader's filename is recorded for traceability, not reused.
            "original_filename": original_name,
        },
    )
    return resource


@transaction.atomic
def create_link_resource(
    *, lesson: Lesson, actor: User, external_url: str, **fields: Any
) -> LessonResource:
    if not external_url.startswith("https://"):
        raise ApplicationError({"external_url": ["Resource links must use https."]})
    resource = LessonResource(
        lesson=lesson,
        kind=ResourceKind.LINK,
        external_url=external_url,
        position=_next_position(lesson.resources),
        uploaded_by=actor,
        **fields,
    )
    resource.full_clean()
    resource.save()
    _touch_course(lesson.module.course, actor)
    record(
        action=AuditAction.RESOURCE_UPLOADED,
        actor=actor,
        resource_type="lesson_resource",
        resource_id=resource.pk,
        context={"course_code": lesson.module.course.code, "kind": "link", "url": external_url},
    )
    return resource


@transaction.atomic
def delete_resource(*, resource: LessonResource, actor: User) -> None:
    course = resource.lesson.module.course
    resource_id, title = resource.pk, resource.title
    if resource.file:
        resource.file.delete(save=False)
    resource.delete()
    _touch_course(course, actor)
    record(
        action=AuditAction.RESOURCE_DELETED,
        actor=actor,
        resource_type="lesson_resource",
        resource_id=resource_id,
        context={"course_code": course.code, "title": title},
    )


__all__ = [
    "ConflictError",
    "TransitionError",
    "assign_author",
    "create_category",
    "create_course",
    "create_file_resource",
    "create_lesson",
    "create_link_resource",
    "create_module",
    "delete_lesson",
    "delete_module",
    "delete_resource",
    "publishing_blockers",
    "remove_author",
    "reorder",
    "set_course_status",
    "set_course_thumbnail",
    "update_category",
    "update_course",
    "update_lesson",
    "update_module",
]
