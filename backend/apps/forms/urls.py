from django.urls import path

from .views import (
    FormDefinitionDetailView,
    FormDefinitionListCreateView,
    FormPreviewView,
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
    path("published/<slug:slug>/", PublishedFormView.as_view(), name="published"),
    path("<slug:slug>/", FormDefinitionDetailView.as_view(), name="detail"),
    path("<slug:slug>/preview/", FormPreviewView.as_view(), name="preview"),
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
