from django.urls import path

from .views import ActivityFeedView, ActivityScorecardsView

app_name = "activity"

urlpatterns = [
    path("feed/", ActivityFeedView.as_view(), name="feed"),
    path("scorecards/", ActivityScorecardsView.as_view(), name="scorecards"),
]
