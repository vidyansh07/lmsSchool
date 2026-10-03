from django.urls import path

from .views import (
    FillableFormsView,
    FormAssignmentCancelView,
    FormAssignmentDetailView,
    FormAssignmentListCreateView,
    FormAssignmentSubmitView,
    FormDefinitionDetailView,
    FormDefinitionListCreateView,
    FormFillView,
    FormPreviewView,
    FormUploadDownloadView,
    FormUploadView,
    FormVersionCreateView,
    FormVersionDetailView,
    FormVersionFieldsView,
    FormVersionPublishView,
    FormVersionUnpublishView,
    PublishedFormView,
)

app_name = "forms"

urlpatterns = [
    path("", FormDefinitionListCreateView.as_view(), name="list"),
    # Fixed segments first: `<slug:slug>/` below would otherwise swallow them.
    path("fillable/", FillableFormsView.as_view(), name="fillable"),
    path("uploads/", FormUploadView.as_view(), name="upload"),
    path("uploads/<uuid:upload_id>/", FormUploadDownloadView.as_view(), name="upload-download"),
    path("assignments/", FormAssignmentListCreateView.as_view(), name="assignment-list"),
    path(
        "assignments/<uuid:assignment_id>/",
        FormAssignmentDetailView.as_view(),
        name="assignment-detail",
    ),
    path(
        "assignments/<uuid:assignment_id>/submit/",
        FormAssignmentSubmitView.as_view(),
        name="assignment-submit",
    ),
    path(
        "assignments/<uuid:assignment_id>/cancel/",
        FormAssignmentCancelView.as_view(),
        name="assignment-cancel",
    ),
    path("published/<slug:slug>/", PublishedFormView.as_view(), name="published"),
    path("<slug:slug>/", FormDefinitionDetailView.as_view(), name="detail"),
    path("<slug:slug>/preview/", FormPreviewView.as_view(), name="preview"),
    path("<slug:slug>/fill/", FormFillView.as_view(), name="fill"),
    path("<slug:slug>/versions/", FormVersionCreateView.as_view(), name="version-create"),
    path(
        "<slug:slug>/versions/<int:number>/", FormVersionDetailView.as_view(), name="version-detail"
    ),
    path(
        "<slug:slug>/versions/<int:number>/fields/",
        FormVersionFieldsView.as_view(),
        name="version-fields",
    ),
    path(
        "<slug:slug>/versions/<int:number>/publish/",
        FormVersionPublishView.as_view(),
        name="version-publish",
    ),
    path(
        "<slug:slug>/versions/<int:number>/unpublish/",
        FormVersionUnpublishView.as_view(),
        name="version-unpublish",
    ),
]
