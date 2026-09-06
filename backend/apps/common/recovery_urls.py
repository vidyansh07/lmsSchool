"""Recovery routes (mounted at /api/v1/recovery/).

The label in these paths is matched against the closed set of soft-deletable
models, never used to look one up — see `apps.common.recovery`.
"""

from django.urls import path

from .recovery import (
    DeletedRecordListView,
    PurgeRecordView,
    RecycleBinView,
    RestoreRecordView,
)

app_name = "recovery"

urlpatterns = [
    path("", RecycleBinView.as_view(), name="bin"),
    path("<str:label>/", DeletedRecordListView.as_view(), name="list"),
    path("<str:label>/<uuid:record_id>/restore/", RestoreRecordView.as_view(), name="restore"),
    path("<str:label>/<uuid:record_id>/purge/", PurgeRecordView.as_view(), name="purge"),
]
