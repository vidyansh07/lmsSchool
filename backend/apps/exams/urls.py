"""Examination routes."""

from __future__ import annotations

from django.urls import path

from . import views

batch_urlpatterns = [
    path("<uuid:batch_id>/exams/", views.BatchExamsView.as_view(), name="batch-exams"),
]

exam_urlpatterns = [
    path("", views.ExamListView.as_view(), name="exam-list"),
    path("mine/", views.MyExamsView.as_view(), name="exam-mine"),
    path("<uuid:exam_id>/", views.ExamDetailView.as_view(), name="exam-detail"),
    path("<uuid:exam_id>/status/", views.ExamStatusView.as_view(), name="exam-status"),
    path("<uuid:exam_id>/readiness/", views.ExamReadinessView.as_view(), name="exam-readiness"),
    path(
        "<uuid:exam_id>/results/publish/",
        views.ExamResultsPublishView.as_view(),
        name="exam-publish-results",
    ),
    path("<uuid:exam_id>/attempts/", views.ExamAttemptsView.as_view(), name="exam-attempts"),
    path("<uuid:exam_id>/marking/", views.MarkingQueueView.as_view(), name="exam-marking"),
    path("<uuid:exam_id>/start/", views.StartAttemptView.as_view(), name="exam-start"),
]

attempt_urlpatterns = [
    path("mine/", views.MyAttemptsView.as_view(), name="attempt-mine"),
    path("<uuid:attempt_id>/", views.AttemptPaperView.as_view(), name="attempt-paper"),
    path("<uuid:attempt_id>/result/", views.AttemptResultView.as_view(), name="attempt-result"),
    path("<uuid:attempt_id>/review/", views.AttemptReviewView.as_view(), name="attempt-review"),
    path("<uuid:attempt_id>/submit/", views.SubmitAttemptView.as_view(), name="attempt-submit"),
    path(
        "<uuid:attempt_id>/questions/<uuid:question_id>/answer/",
        views.SaveAnswerView.as_view(),
        name="attempt-answer",
    ),
    path("answers/<uuid:answer_id>/mark/", views.MarkAnswerView.as_view(), name="answer-mark"),
]
