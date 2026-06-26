from django.urls import path

from apps.questions import views

app_name = 'questions'

urlpatterns = [
    # =====================================================================
    # ۱. روت‌های بخش داوطلب / کلاینت عمومی (Candidate Routes)
    # =====================================================================
    path('', views.QuestionListAPI.as_view(), name='question-list'),
    path('<int:id>/', views.QuestionDetailAPI.as_view(), name='question-detail'),
    path('random-set/', views.RandomInterviewSetAPI.as_view(), name='random-set'),
    path('categories/', views.CategoryListAPI.as_view(), name='category-list'),

    # =====================================================================
    # ۲. روت‌های پنل مدیریت و ادمین (Admin / Backoffice Routes)
    # =====================================================================
    path('admin/questions/', views.AdminQuestionListCreateAPI.as_view(), name='admin-question-list-create'),
    path('admin/questions/<int:id>/', views.AdminQuestionDetailAPI.as_view(), name='admin-question-detail-mutations'),
    path('admin/categories/', views.AdminCategoryListCreateAPI.as_view(), name='admin-category-create'),

    # =====================================================================
    # ۳. روت‌های اتوماسیون و خزنده گیت‌هاب (Automation Routes)
    # =====================================================================
    path('admin/ingest/github/', views.AdminGitHubIngestAPI.as_view(), name='admin-github-ingest'),
]
