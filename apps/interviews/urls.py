from django.urls import path

from apps.interviews import views

app_name = "interviews"

urlpatterns = [
    # =========================================================================
    # ۱. روت‌های مدیریت جلسات کاربر (User Session Endpoints)
    # =========================================================================
    path(
        "", views.InterviewSessionListCreateView.as_view(), name="session-list-create"
    ),
    path("active/", views.ActiveSessionView.as_view(), name="session-active"),
    path("stats/", views.UserInterviewStatsView.as_view(), name="user-stats"),
    path(
        "<uuid:uuid>/",
        views.InterviewSessionDetailView.as_view(),
        name="session-detail-mutations",
    ),
    path(
        "<uuid:uuid>/report/",
        views.InterviewReportView.as_view(),
        name="session-report",
    ),
    # =========================================================================
    # ۲. روت‌های کنترل و نظارت مدیریت (Admin / Backoffice Endpoints)
    # =========================================================================
    path(
        "admin/sessions/",
        views.AdminSessionListView.as_view(),
        name="admin-session-list",
    ),
    path(
        "admin/sessions/<uuid:uuid>/",
        views.AdminSessionDetailView.as_view(),
        name="admin-session-detail",
    ),
    path(
        "admin/answers/<int:pk>/",
        views.AdminAnswerDetailView.as_view(),
        name="admin-answer-detail",
    ),
    path(
        "admin/answers/<int:pk>/retrigger/",
        views.AdminRetriggerEvaluationView.as_view(),
        name="admin-evaluation-retrigger",
    ),
]
