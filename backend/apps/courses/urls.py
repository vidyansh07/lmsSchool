"""Course routes.

Mounted as four groups under /api/v1/, matching the domains in the brief:
``courses/``, ``categories/``, ``modules/``, ``lessons/`` and ``resources/``.
Child collections hang off their parent (``courses/<id>/modules/``) because that
is the only place they make sense; individual records are addressable directly
so the editor can update one without walking the tree.
"""

from django.urls import path

from .views import (
    CategoryDetailView,
    CategoryListCreateView,
    CourseAuthorDetailView,
    CourseAuthorsView,
    CourseDetailView,
    CourseListCreateView,
    CourseModuleReorderView,
    CourseModulesView,
    CoursePublishChecklistView,
    CourseStatusView,
    CourseThumbnailView,
    LessonDetailView,
    LessonResourceLinkView,
    LessonResourcesView,
    LessonStatusView,
    LessonVideoPlaybackView,
    ModuleDetailView,
    ModuleLessonReorderView,
    ModuleLessonsView,
    ModuleStatusView,
    MyCoursesView,
    ResourceDetailView,
    ResourceDownloadView,
)

course_patterns = [
    path("", CourseListCreateView.as_view(), name="list"),
    # Declared before the identifier route so it can never be shadowed.
    path("mine/", MyCoursesView.as_view(), name="mine"),
    path("<uuid:course_id>/status/", CourseStatusView.as_view(), name="status"),
    path(
        "<uuid:course_id>/publish-checklist/",
        CoursePublishChecklistView.as_view(),
        name="publish-checklist",
    ),
    path("<uuid:course_id>/thumbnail/", CourseThumbnailView.as_view(), name="thumbnail"),
    path("<uuid:course_id>/authors/", CourseAuthorsView.as_view(), name="authors"),
    path(
        "<uuid:course_id>/authors/<uuid:user_id>/",
        CourseAuthorDetailView.as_view(),
        name="author-detail",
    ),
    path("<uuid:course_id>/modules/", CourseModulesView.as_view(), name="modules"),
    path(
        "<uuid:course_id>/modules/reorder/",
        CourseModuleReorderView.as_view(),
        name="module-reorder",
    ),
    # Accepts a UUID or a slug, so student-facing URLs can be readable.
    path("<str:identifier>/", CourseDetailView.as_view(), name="detail"),
]

category_patterns = [
    path("", CategoryListCreateView.as_view(), name="list"),
    path("<uuid:category_id>/", CategoryDetailView.as_view(), name="detail"),
]

module_patterns = [
    path("<uuid:module_id>/", ModuleDetailView.as_view(), name="detail"),
    path("<uuid:module_id>/status/", ModuleStatusView.as_view(), name="status"),
    path("<uuid:module_id>/lessons/", ModuleLessonsView.as_view(), name="lessons"),
    path(
        "<uuid:module_id>/lessons/reorder/",
        ModuleLessonReorderView.as_view(),
        name="lesson-reorder",
    ),
]

lesson_patterns = [
    path("<uuid:lesson_id>/", LessonDetailView.as_view(), name="detail"),
    path("<uuid:lesson_id>/status/", LessonStatusView.as_view(), name="status"),
    path("<uuid:lesson_id>/video/", LessonVideoPlaybackView.as_view(), name="video"),
    path("<uuid:lesson_id>/resources/", LessonResourcesView.as_view(), name="resources"),
    path(
        "<uuid:lesson_id>/resources/link/", LessonResourceLinkView.as_view(), name="resource-link"
    ),
]

resource_patterns = [
    path("<uuid:resource_id>/", ResourceDetailView.as_view(), name="detail"),
    path("<uuid:resource_id>/download/", ResourceDownloadView.as_view(), name="download"),
]
